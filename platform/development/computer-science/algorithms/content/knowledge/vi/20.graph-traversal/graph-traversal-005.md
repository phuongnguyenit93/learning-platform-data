# Thời điểm đánh dấu đã thăm và tránh đưa đỉnh vào nhiều lần

**Thời điểm đánh dấu một đỉnh là đã thăm (visited)** quyết định cách thuật toán duyệt đồ thị quản lý hàng đợi, ngăn xếp và các cạnh đi tới cùng một đỉnh. Trong **BFS (breadth-first search)** chuẩn trên đồ thị không trọng số, quy tắc an toàn và tiết kiệm là: **đánh dấu ngay khi đỉnh được phát hiện và đưa vào hàng đợi (enqueue)**, không đợi tới lúc lấy đỉnh ra (dequeue). Nhờ vậy, mỗi đỉnh được đưa vào hàng đợi **tối đa một lần**, ngay cả khi có nhiều đường tới nó, nhiều cạnh song song, cạnh tự khép hoặc chu trình.

Trong **DFS (depth-first search)**, nguyên tắc tương ứng là đánh dấu một đỉnh **ngay khi quyết định bắt đầu khám phá nó**, trước khi mở rộng các cạnh đi ra. Với DFS đệ quy, đó là khi vừa vào lời gọi; với DFS dùng ngăn xếp, có thể đánh dấu khi đưa đỉnh vào stack. Tuy nhiên, **DFS stack đơn giản đánh dấu khi push không mặc nhiên tái tạo đúng thứ tự và cây cha của DFS đệ quy**. Nếu cần khớp chính xác với đệ quy theo thứ tự danh sách kề, hãy dùng **stack gồm các khung duyệt (frames)** có vị trí cạnh tiếp theo, như chương trình Java 17+ ở dưới.

Bài thuộc chủ đề **Duyệt đồ thị**. Trọng tâm là phân biệt **chưa phát hiện**, **đã phát hiện nhưng chưa xử lý xong**, và **đã hoàn tất xử lý**; hiểu vì sao phát hiện sớm giúp tránh đưa đỉnh vào cấu trúc chờ nhiều lần; nắm bất biến BFS/DFS, chứng minh tính đúng, các ca có cạnh lặp và chu trình, sự khác biệt với Dijkstra và những lỗi triển khai thường gặp.

**Mục tiêu học tập:** chọn được thời điểm cập nhật visited; biết vì sao BFS cho đường đi ngắn nhất theo số cạnh khi đánh dấu lúc enqueue; phân tích chính xác số lần enqueue và bộ nhớ; triển khai BFS một nguồn, BFS nhiều nguồn, DFS mô phỏng đệ quy; phân biệt trạng thái discovered/finished; kiểm thử các ca nhiều cha, song song, self-loop, disconnected và khôi phục đường đi.

## 1. Một đỉnh có thể được gặp từ nhiều cạnh

Cho đồ thị có hướng `G=(V,E)`, trong đó `V` là tập đỉnh và `E` là các cạnh. Ta lưu bằng **danh sách kề**: `adj[v]` chứa các đỉnh mà có cạnh `v→u`. Nếu là đồ thị vô hướng, mỗi cạnh `{v,u}` thường xuất hiện trong hai danh sách kề `adj[v]` và `adj[u]`; vòng lặp thuật toán không thay đổi về nguyên lý.

Xét cấu trúc hình thoi:

~~~text
      0
     / \
    v   v
    1   2
     \ /
      v
      3
~~~

Hai cạnh `1→3` và `2→3` đều dẫn tới đỉnh 3. Nếu BFS từ 0 đưa 1,2 vào queue và chỉ đánh dấu mỗi đỉnh khi **lấy khỏi queue**, thì lúc đang mở rộng 1 và 2, cả hai đều có thể thấy đỉnh 3 “chưa được đánh dấu” và cùng đưa 3 vào queue.

Điều này không có nghĩa rằng tồn tại hai đỉnh 3 khác nhau. Queue chứa **hai bản ghi cho cùng một đỉnh**, làm tăng bộ nhớ và số lần lấy ra. Với đồ thị có nhiều cạnh hội tụ hoặc nhiều cạnh song song, mức lãng phí có thể đáng kể.

**Điểm phân biệt:** “đỉnh đã được phát hiện” không đồng nghĩa “đã xử lý xong danh sách kề”. Ta có thể đánh dấu nó đã phát hiện dù nó vẫn đang **chờ trong queue**. Về mặt tránh lặp, đây chính là thông tin cần thiết.

## 2. Ba trạng thái khái niệm của một đỉnh

Mặc dù BFS cơ bản chỉ cần một mảng boolean, nên hiểu ba trạng thái sau:

| Trạng thái | Ý nghĩa | BFS | DFS |
|---|---|---|---|
| **WHITE / chưa phát hiện** | Chưa được đưa vào cấu trúc tìm kiếm | `visited[v]=false` | `color[v]=WHITE` |
| **GRAY / đã phát hiện** | Đã lên lịch duyệt nhưng chưa hoàn tất mọi cạnh | Đang chờ queue hoặc đang mở rộng | Đang nằm trên stack đệ quy/khung |
| **BLACK / đã hoàn tất** | Đã xét xong mọi cạnh đi ra | Đã mở rộng xong hàng kề | Đã quay lui khỏi khung |

Nếu bài toán chỉ hỏi “đỉnh này có được lên lịch lần nào chưa?”, **GRAY và BLACK đều được tính là visited=true**. Không phải chờ BLACK mới cấm đưa đỉnh vào queue/stack lần nữa.

Trong BFS, có thể không lưu GRAY và BLACK riêng: dùng `seen[v]` từ lúc enqueue là đủ cho reachability và khoảng cách ngắn nhất không trọng số. Trong một số bài DFS như phát hiện chu trình có hướng, phân biệt GRAY với BLACK là **cần thiết**: một cạnh hướng tới đỉnh GRAY trên ngăn xếp đệ quy là back edge, còn cạnh tới BLACK không có cùng ý nghĩa.

**Lưu ý thuật ngữ:** tài liệu khác nhau có thể dùng tên `visited` để chỉ discovered hoặc processed. Trước khi sao chép mã, hãy xác định nó được bật **ở thời điểm nào**. Đặt tên `discovered` hoặc `seen` giúp tránh hiểu nhầm.

## 3. Quy tắc BFS: đánh dấu trước khi enqueue

BFS duyệt theo từng **lớp khoảng cách** tính bằng số cạnh từ nguồn. Mã lõi cho một nguồn s:

~~~text
seen[s] = true
distance[s] = 0
queue.add(s)

while queue is not empty:
    v = queue.remove()
    for each u in adj[v]:
        if seen[u]:
            continue
        seen[u] = true        // ĐÁNH DẤU NGAY!
        distance[u] = distance[v] + 1
        parent[u] = v
        queue.add(u)
~~~

Thứ tự trong một lần phát hiện đỉnh u là:

**kiểm tra chưa phát hiện → đánh dấu seen[u] → gán distance/parent → enqueue(u).**

Với thực thi tuần tự thông thường, có thể gán thông tin và đánh dấu trước khi queue.add, miễn sao **đỉnh được đặt vào queue đúng một lần** và không có đoạn mở rộng khác thấy nó ở trạng thái chưa phát hiện. Mã Java dùng rõ thứ tự đánh dấu trước enqueue để minh họa.

### Nguồn cũng phải được đánh dấu trước

Ngay khi bắt đầu BFS:

`seen[s]=true` và `queue.add(s)`.

Nếu quên bước này, một vòng khép hoặc cạnh đi về nguồn có thể khiến s bị enqueue thêm lần nữa. Chẳng hạn có cạnh `s→s` (self-loop). Nếu nguồn chưa được đánh dấu, khi xử lý nó ta sẽ thấy chính nó “chưa được thăm”, rồi enqueue lại.

Trong BFS nhiều nguồn, phải đánh dấu **từng nguồn khi cho vào queue lần đầu**. Nếu danh sách nguồn chứa trùng một đỉnh, không thêm trùng; các nguồn khác nhau ban đầu đều có khoảng cách 0.

### Tại sao kiểm tra nằm bên trong vòng lặp cạnh?

Một đỉnh v có thể có nhiều hàng xóm. Mỗi hàng xóm u cần một phép `if (!seen[u])` riêng. Không thể chỉ đánh dấu v một lần rồi enqueue mọi u vô điều kiện: khi một cạnh khác đi vào cùng u, queue sẽ lại chứa u.

**Đánh dấu u là công việc diễn ra tại thời điểm phát hiện u qua cạnh v→u, không chờ đến lượt xử lý hàng kề của u.**

## 4. Ví dụ cụ thể có cạnh lặp, hội tụ và chu trình

Xét đồ thị **có hướng** 7 đỉnh, đánh số 0..6, với danh sách kề được duyệt đúng thứ tự hiển thị:

~~~text
0: [1, 2, 1]   // Hai cạnh 0→1, một cạnh 0→2.
1: [3, 4]
2: [3, 4]
3: [5]
4: [5]
5: [2]         // Tạo chu trình 2→3→5→2.
6: []          // Không nối với các đỉnh còn lại.
~~~

Đỉnh 3 có thể được gặp từ cả 1 và 2; đỉnh 4 tương tự; đỉnh 5 từ cả 3 và 4; đỉnh 1 còn có **hai cạnh song song** đi từ 0. Đỉnh 6 không thể tới từ 0.

### BFS từ 0: đánh dấu ngay lúc enqueue

- Ban đầu: `queue=[0]`, seen={0}, distance[0]=0.
- Lấy 0: phát hiện 1, đánh dấu và enqueue 1; phát hiện 2, đánh dấu và enqueue 2; cạnh 0→1 thứ hai thấy 1 đã seen nên bỏ. Queue còn `[1,2]`.
- Lấy 1: phát hiện 3 rồi 4. Queue còn `[2,3,4]`.
- Lấy 2: cả 3 và 4 đã được phát hiện, không enqueue lại.
- Lấy 3: phát hiện 5, enqueue 5.
- Lấy 4: cạnh tới 5 đã seen, bỏ.
- Lấy 5: cạnh tới 2 đã seen, bỏ, nên không lặp vô tận trong chu trình.
- Queue rỗng; đỉnh 6 chưa được phát hiện.

Thứ tự lấy ra:

**`[0,1,2,3,4,5]`.**

Mảng khoảng cách:

**`[0,1,1,2,2,3,-1]`**,

trong đó -1 nghĩa là chưa tới được từ nguồn 0. Mảng cha:

**`[-1,0,0,1,1,3,-1]`**.

Đỉnh 3 nhận cha 1 vì 1 được lấy ra và phát hiện 3 trước 2. Nếu đổi thứ tự danh sách kề, một đường đi ngắn nhất khác có thể được chọn, nhưng **độ dài ngắn nhất vẫn không đổi**.

### Đếm số lần thêm queue

Có 6 đỉnh tới được từ 0, và mỗi đỉnh được enqueue đúng một lần:

**`enqueueCount=6`**.

Đây là số lần enqueue **tổng cộng**, gồm cả lần thêm nguồn 0. Đỉnh 6 không được enqueue trong BFS từ 0.

## 5. Nếu đánh dấu lúc dequeue thì sao?

Một phiên bản khác có thể thực hiện:

~~~text
queue.add(source)
while queue is not empty:
    v = queue.remove()
    if seen[v]:
        continue          // BẮT BUỘC nếu đã để trùng trong queue.
    seen[v] = true
    process(v)
    for each u in adj[v]:
        queue.add(u)       // Có thể thêm cùng u nhiều lần.
~~~

Với phiên bản có `if seen[v] continue` trước khi mở rộng, mỗi đỉnh được **mở rộng danh sách kề tối đa một lần**, nên cách này vẫn có thể cho reachability đúng. Tuy nhiên, **queue có thể chứa nhiều bản ghi cho cùng một đỉnh**, tốn thêm số lần enqueue/dequeue và bộ nhớ.

### Đếm chính xác trên ví dụ 7 đỉnh

Duyệt cùng thứ tự danh sách kề như phần trên:

| Đỉnh được lấy lần đầu | Các bản ghi được thêm tiếp | Tổng số lần enqueue sau đó |
|---|---|---:|
| Khởi tạo | 0 | 1 |
| 0 | 1, 2, 1 | 4 |
| 1 | 3, 4 | 6 |
| 2 | 3, 4 | 8 |
| 3 | 5 | 9 |
| 4 | 5 | 10 |
| 5 | 2 | 11 |

Các bản ghi 1,3,4,5,2 xuất hiện lặp trong queue khi chúng đã/đang được chờ xử lý. Sau khi kiểm tra `seen[v]` ở dequeue, các bản ghi lặp được bỏ. Tổng:

- Mark-on-enqueue: **6 lần enqueue, 6 lần dequeue**.
- Mark-on-dequeue với bỏ bản ghi lặp: **11 lần enqueue, 11 lần dequeue**, nhưng vẫn chỉ mở rộng hàng kề của 6 đỉnh.

**Không khẳng định mark-on-dequeue luôn sai về kết quả.** Khi có kiểm tra bỏ trùng thật sự và xử lý khoảng cách/cha nhất quán, nó vẫn có thể tính reachability; vấn đề là thừa bản ghi và dễ sai nếu thiết kế thông tin đường đi không cẩn thận.

### Khi nào bản mark-on-dequeue thực sự gây lỗi nặng?

Nếu dequeue một đỉnh đã visited mà **không bỏ qua việc mở rộng cạnh**, một đỉnh có thể sinh thêm các bản ghi lặp, tạo vòng lặp vô hạn trên chu trình. Nếu ghi đè `parent[u]` hoặc `distance[u]` ở mỗi lần enqueue mà không kiểm tra lần phát hiện đầu, có thể mất thông tin đường đi ngắn nhất.

Phân tích chính xác với danh sách kề:

- Mark-on-enqueue: tổng enqueue tối đa số đỉnh tới được, O(V); queue tối đa O(V).
- Mark-on-dequeue **có skip trước khi mở rộng**: mỗi đỉnh vẫn chỉ mở rộng một lần, mỗi cạnh trong danh sách kề được duyệt một lần; số lần enqueue tối đa `1+E_reachable`, nên **vẫn O(V+E) thời gian** theo cận thông thường, nhưng queue có thể lên tới O(E) bản ghi.
- Mark-on-dequeue **không skip trước khi mở rộng**: không có bất biến mỗi đỉnh mở rộng một lần, và chu trình có thể khiến thuật toán không kết thúc.

Điểm học thuật là **đúng đắn, hằng số vận hành và bộ nhớ**; không nên tuyên bố bản có skip ở dequeue mặc nhiên chạy thời gian hàm mũ nếu mỗi cạnh chỉ được mở rộng một lần.

## 6. Vì sao BFS mark-on-enqueue vẫn tìm đường đi ngắn nhất?

Với đồ thị **không trọng số** hoặc mọi cạnh có cùng chi phí một đơn vị, định nghĩa `dist[v]` là số cạnh ít nhất từ s đến v.

**Bất biến 1: hàng đợi FIFO xử lý các lớp khoảng cách theo thứ tự không giảm.** Ban đầu nguồn có khoảng cách 0. Khi đang lấy v ở lớp d, mọi đỉnh u mới phát hiện qua v được gán d+1 và thêm vào **cuối** queue. Không có đỉnh thuộc lớp lớn hơn bị xử lý trước một đỉnh lớp nhỏ hơn còn đang chờ.

**Bất biến 2: lần đầu một đỉnh được phát hiện là qua đường đi có số cạnh nhỏ nhất.** Giả sử u được phát hiện với khoảng cách d+1 từ v. Nếu tồn tại đường ngắn hơn, tiền nhiệm của u trên đường ấy phải thuộc một lớp nhỏ hơn d và đã được xử lý trước v; khi đó u đã được phát hiện sớm hơn — mâu thuẫn.

Vì vậy sau lần phát hiện đầu:

- `seen[u]=true` là an toàn: không cần cho u vào queue lần nữa chỉ để xét một đường dài hơn hoặc bằng.
- `dist[u]=dist[v]+1` là khoảng cách ngắn nhất.
- `parent[u]=v` xác định một đường đi ngắn nhất từ s tới u.

**Quan trọng:** bằng chứng dựa vào cấu trúc **FIFO và độ dài cạnh bằng nhau**. Không tự áp dụng “mark ngay khi thấy” cho mọi thuật toán đường đi ngắn nhất có trọng số.

### Cách dựng đường đi từ parent

Nếu `dist[target]==-1`, không có đường từ source tới target. Nếu có:

~~~text
path = []
v = target
while v != -1:
    prepend v to path
    v = parent[v]
~~~

Với parent nguồn bằng -1, chuỗi ngược dừng đúng ở source. Trên đồ thị ví dụ, từ 0 tới 5 sẽ có một đường đi ngắn nhất:

**`[0,1,3,5]`**, dài **3 cạnh**.

Nếu source=target, đường đi chỉ gồm một đỉnh. Nếu muốn thứ tự đường đi từ source tới target, có thể ghi theo chiều target→source rồi đảo ngược danh sách.

## 7. DFS: đánh dấu lúc bắt đầu khám phá đỉnh

DFS ưu tiên đi sâu theo một nhánh trước khi quay lại. Trong DFS đệ quy chuẩn, một lời gọi:

~~~text
dfs(v):
    seen[v] = true            // Ngay khi vào v.
    processOnEntry(v)
    for each u in adj[v]:
        if not seen[u]:
            parent[u] = v
            dfs(u)
    processOnExit(v)
~~~

Đánh dấu **ngay lúc bắt đầu dfs(v)** giúp ngăn một cạnh quay lại v tạo thêm lời gọi dfs(v) trong khi v còn nằm trên stack, tránh lặp vô tận trên chu trình.

Một DFS không đệ quy đơn giản có thể dùng `stack.push` để đưa các đỉnh được phát hiện vào stack; khi ấy thường đánh dấu **trước hoặc ngay lúc push**. Điều này đảm bảo không có hai bản ghi của cùng đỉnh trong stack, giống quy tắc mark-on-enqueue của BFS.

**Nhưng có một khác biệt quan trọng về thứ tự DFS.** Nếu một vòng lặp stack đơn giản **push tất cả hàng xóm** (đánh dấu ngay khi push), những đỉnh được push sớm có thể bị xem là đã phát hiện **trước khi khám phá xong nhánh của hàng xóm khác**. Cây cha và thứ tự vào đỉnh có thể khác DFS đệ quy.

## 8. “Đảo thứ tự push” chưa chắc tái tạo DFS đệ quy

Xét đồ thị:

~~~text
0: [1,2]
1: [2]
2: []
~~~

DFS đệ quy theo thứ tự danh sách kề:

1. Vào 0.
2. Từ 0 gọi DFS(1).
3. Từ 1 phát hiện 2 rồi gọi DFS(2).
4. Quay lui; cạnh 0→2 sau đó thấy 2 đã visited.

**Cha của 2 là 1**, thứ tự vào đỉnh là `[0,1,2]`.

Nếu DFS stack đơn giản từ 0 **push các hàng xóm theo thứ tự ngược** để khi pop được 1 trước 2:

- Push 2 và **đánh dấu 2 ngay**.
- Push 1 và **đánh dấu 1 ngay**.
- Pop 1; cạnh 1→2 thấy 2 đã seen nên không đi tiếp.
- Pop 2 sau đó.

Thứ tự pop có thể vẫn là `[0,1,2]`, nhưng **cha của 2 là 0, không phải 1**. Vì vậy “đảo thứ tự hàng xóm khi push” chỉ có thể mô phỏng một số thứ tự thăm, **không đảm bảo trùng cây DFS đệ quy trên đồ thị tổng quát**.

Điều này đặc biệt quan trọng nếu kết quả cần **cạnh cây DFS, thời điểm vào/ra, phát hiện chu trình, articulation points, bridges, hoặc thứ tự hậu duyệt**. Một “stack DFS” phát hiện trước toàn bộ hàng xóm không thể thay thế trực tiếp khung đệ quy mà không xem lại bất biến.

## 9. Stack gồm khung: mô phỏng đúng DFS đệ quy

Muốn bảo toàn chính xác thứ tự DFS đệ quy theo `adj[v]`, mỗi khung stack lưu:

- `v`: đỉnh đang được khám phá.
- `nextNeighbor`: chỉ số của **cạnh kề tiếp theo** chưa xét trong `adj[v]`.

Thuật toán:

~~~text
seen[source] = true
recordEntry(source)
stack.push(Frame(source, nextNeighbor=0))

while stack is not empty:
    frame = stack.peek()
    v = frame.vertex

    if frame.nextNeighbor == adj[v].length:
        recordExit(v)
        stack.pop()
        continue

    u = adj[v][frame.nextNeighbor]
    frame.nextNeighbor++     // Ghi nhớ vị trí trước khi vào u.

    if seen[u]:
        continue

    parent[u] = v
    seen[u] = true
    recordEntry(u)
    stack.push(Frame(u, nextNeighbor=0))
~~~

Vòng lặp chỉ xem **một cạnh kề mỗi lần**. Khi gặp đỉnh u chưa thấy, nó đánh dấu u và đẩy **một khung mới**; các cạnh còn lại của v sẽ được xét **sau khi khung u đã hoàn tất** — đúng hành vi DFS đệ quy.

**Bất biến stack frames:** những khung trên stack chính là đường đi đệ quy đang mở. Mỗi frame nhớ đã xét bao nhiêu cạnh, nên khi con hoàn tất, frame cha tiếp tục từ vị trí cũ. Mỗi đỉnh được push tối đa một lần vì đánh dấu trước push; mỗi cạnh trong danh sách kề được xét một lần.

Thời gian O(V+E) và bộ nhớ phụ O(V) cho seen/parent/frames trong đồ thị đã lưu bằng danh sách kề; độ sâu stack không vượt số đỉnh tới được.

### Truy vết trên đồ thị 7 đỉnh

Với `adj` ở phần 4 và DFS bắt đầu ở 0, khung DFS lần lượt đi:

`0→1→3→5→2→4`.

Thứ tự **vào đỉnh** là:

**`[0,1,3,5,2,4]`**.

Mảng parent:

**`[-1,0,5,1,2,3,-1]`**.

Đỉnh 2 có parent=5 vì 2 được phát hiện **từ cạnh 5→2** trước khi DFS quay về 0 và xem cạnh 0→2. Ngược lại BFS có parent[2]=0 vì BFS phát hiện 2 trực tiếp từ nguồn. Do đó **đường đi cha của DFS không nhất thiết là đường đi ngắn nhất**.

## 10. DFS ba màu: khi cần phân biệt đang mở và hoàn tất

Một mảng boolean có thể đủ cho reachability. Nhưng một số tác vụ phụ thuộc vào **trạng thái đang nằm trên stack**:

- **WHITE:** chưa khám phá.
- **GRAY:** đã vào DFS nhưng còn trên stack đệ quy/frames.
- **BLACK:** đã xét xong toàn bộ cạnh ra.

Trong đồ thị **có hướng**, cạnh từ đỉnh v đang GRAY tới một đỉnh u cũng đang GRAY biểu thị **back edge** và cho biết có một chu trình có hướng. Cạnh tới BLACK có thể là cạnh chéo hoặc xuôi, **không tự chứng minh chu trình**.

Với đồ thị **vô hướng**, một cạnh ngược về parent là bình thường, nên phát hiện chu trình phải phân biệt cạnh parent. Khi có **nhiều cạnh song song**, chỉ kiểm tra “u != parent[v]” có thể chưa đủ để phân biệt đúng từng **cạnh**; thuật toán tinh tế có thể cần **edge ID** thay vì chỉ vertex ID.

**Không đánh đồng** “đã visited” với “đã finished”. Cấm enqueue lại một đỉnh là một mục tiêu; nhận diện cạnh ngược trên stack là mục tiêu khác. Hãy chọn số trạng thái tối thiểu nhưng đủ cho chứng minh của bài toán.

## 11. BFS nhiều nguồn: đánh dấu từng nguồn khi khởi tạo

Nếu muốn khoảng cách ngắn nhất từ **một trong nhiều nguồn** tới mọi đỉnh trong đồ thị không trọng số, dùng multi-source BFS:

~~~text
for each vertex v:
    seen[v] = false
    dist[v] = -1

for each source s:
    if not seen[s]:
        seen[s] = true
        dist[s] = 0
        queue.add(s)

while queue not empty:
    v = queue.remove()
    for each u in adj[v]:
        if not seen[u]:
            seen[u] = true
            dist[u] = dist[v] + 1
            parent[u] = v
            queue.add(u)
~~~

Tất cả nguồn hợp lệ có khoảng cách 0. Nguồn bị lặp trong danh sách chỉ được đưa vào queue một lần. Khi một đỉnh lần đầu được phát hiện, đường đi đó có số cạnh ngắn nhất tính từ **tập nguồn**.

Với đồ thị mẫu và `sources=[0,6,0]`:

- Queue khởi tạo chứa 0,6; phần tử 0 lặp không được thêm.
- Thứ tự dequeue là **`[0,6,1,2,3,4,5]`**.
- Khoảng cách tới tập nguồn là **`[0,1,1,2,2,3,0]`**.
- Tổng số lần enqueue là **7**: cả 7 đỉnh đều được phát hiện một lần.

Nếu `sources=[]`, không có đỉnh nào được phát hiện và tất cả khoảng cách giữ -1. Nếu nguồn ngoài miền 0..V−1, API nên từ chối; không bỏ qua âm thầm một chỉ số không hợp lệ trừ khi hợp đồng quy định.

### Duyệt tất cả thành phần

BFS/DFS từ một nguồn chỉ tới các đỉnh **có đường đi từ nguồn**. Muốn duyệt tất cả đỉnh, đặt vòng lặp ngoài:

~~~text
for s from 0 to V-1:
    if not seen[s]:
        seen[s] = true
        queue.add(s)
        run the standard BFS expansion from s
~~~

Mảng `seen` phải **tồn tại xuyên suốt các thành phần**. Trong đồ thị có hướng, vòng lặp này tạo một rừng duyệt theo các lần đạt tới; nó **không tự tìm strong connected components**. Để tìm SCC, dùng thuật toán chuyên biệt như Kosaraju hoặc Tarjan.

## 12. Đánh dấu sớm không áp dụng nguyên xi cho Dijkstra

Đây là một giới hạn quan trọng: quy tắc **“đánh dấu ngay khi đưa vào queue”** là đúng cho BFS đường đi ngắn nhất **không trọng số**. Với Dijkstra trên đồ thị có **trọng số không âm**, lần đầu phát hiện một đỉnh **chưa chắc** là khi đã biết đường đi rẻ nhất tới nó.

Phản ví dụ:

~~~text
s --10--> A
 \         ^
  \--1--> B --1--> A
~~~

Từ s, ta có thể phát hiện A với chi phí 10 và B với chi phí 1. Nhưng đường `s→B→A` có chi phí **2**, tốt hơn 10.

Nếu đánh dấu A là “đã chốt” ngay lúc đưa nó vào **priority queue**, rồi cấm mọi cập nhật tới A, thuật toán sẽ giữ sai chi phí 10. Dijkstra chuẩn cho phép **relax** một đỉnh nhiều lần; nó **chốt (settle/finalize)** khoảng cách khi lấy ra đỉnh có khoảng cách tạm nhỏ nhất phù hợp từ priority queue, với điều kiện trọng số không âm. Với heap không hỗ trợ decrease-key, có thể có nhiều bản ghi cho cùng đỉnh và **bỏ bản ghi lỗi thời (stale)** khi pop.

Do đó:

| Thuật toán | Thời điểm đánh dấu chính | Vì sao |
|---|---|---|
| BFS không trọng số | **Lần đầu enqueue** | FIFO theo lớp số cạnh, lần đầu đã tối ưu |
| DFS reachability | **Lúc bắt đầu khám phá / push frame** | Tránh lặp, mô tả nhánh đang mở |
| DFS phát hiện chu trình có hướng | GRAY khi vào, BLACK khi ra | Phân biệt đang trên stack với đã xong |
| Dijkstra trọng số không âm | Chốt khi lấy được khoảng cách nhỏ nhất hợp lệ từ PQ | Một đỉnh có thể được cải thiện sau lần phát hiện đầu |
| Bellman-Ford | Không dùng visited kiểu “cấm relax” | Cạnh cần được relax nhiều lượt |

Không chuyển một mẫu visited từ BFS sang Dijkstra, 0-1 BFS, A* hoặc thuật toán khác mà không kiểm tra **bất biến tối ưu** và mục tiêu của nó. Trong một số thuật toán tìm đường, đưa một trạng thái vào cấu trúc chờ nhiều lần **là chủ đích** khi tìm được giá trị tốt hơn.

## 13. Java 17+ hoàn chỉnh: BFS, DFS frames, multi-source và đối chứng

Chương trình sau minh họa ba kỹ thuật có chủ đích:

1. **`bfs`:** mark-on-enqueue, tìm thứ tự duyệt, khoảng cách, parent và số lần enqueue.
2. **`dfsRecursiveOrderWithFrames`:** dùng stack khung, đánh dấu ngay khi push khung, tái hiện thứ tự vào đỉnh và cây cha của DFS đệ quy theo đúng `adj[v]`.
3. **`multiSourceBfs`:** khởi tạo các nguồn không trùng, tất cả ở distance 0.
4. **`countEnqueuesMarkOnDequeue`:** chỉ là **đối chứng số thao tác**; đánh dấu khi dequeue và bỏ các bản ghi trùng trước khi mở rộng, để thấy chi phí dư thừa nhưng không sinh vòng vô hạn.

**Hợp đồng đầu vào:** đồ thị được lưu bằng `int[][]` danh sách kề có hướng; các hàng phải khác null, mọi hàng xóm phải thuộc `0..V−1`; cạnh trùng, self-loop và chu trình được chấp nhận. BFS/DFS một nguồn yêu cầu source hợp lệ. Multi-source yêu cầu mảng nguồn không null; danh sách nguồn rỗng được chấp nhận. Mọi khoảng cách là **số cạnh**, không phải tổng trọng số.

Lưu thành **`VisitTimingGraphDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Deque;
import java.util.List;

public final class VisitTimingGraphDemo {
    record BfsResult(
            List<Integer> order,
            int[] distances,
            int[] parents,
            long enqueues) {}

    record DfsResult(List<Integer> order, int[] parents) {}

    private static final class Frame {
        final int vertex;
        int nextNeighbor;

        Frame(int vertex) {
            this.vertex = vertex;
            this.nextNeighbor = 0;
        }
    }

    private static void validateGraph(int[][] graph) {
        if (graph == null) {
            throw new IllegalArgumentException("Null graph");
        }
        int n = graph.length;
        for (int[] neighbors : graph) {
            if (neighbors == null) {
                throw new IllegalArgumentException("Null adjacency row");
            }
            for (int u : neighbors) {
                if (u < 0 || u >= n) {
                    throw new IllegalArgumentException(
                            "Neighbor outside graph: " + u);
                }
            }
        }
    }

    private static void checkVertex(int n, int v) {
        if (v < 0 || v >= n) {
            throw new IllegalArgumentException("Invalid vertex: " + v);
        }
    }

    // BFS chuẩn: đánh dấu ngay lúc phát hiện, trước enqueue.
    static BfsResult bfs(int[][] graph, int source) {
        validateGraph(graph);
        int n = graph.length;
        checkVertex(n, source);

        boolean[] seen = new boolean[n];
        int[] dist = new int[n];
        int[] parent = new int[n];
        Arrays.fill(dist, -1);
        Arrays.fill(parent, -1);

        Deque<Integer> queue = new ArrayDeque<>();
        List<Integer> order = new ArrayList<>();

        seen[source] = true;
        dist[source] = 0;
        queue.addLast(source);
        long enqueues = 1L;

        while (!queue.isEmpty()) {
            int v = queue.removeFirst();
            order.add(v);

            for (int u : graph[v]) {
                if (seen[u]) {
                    continue;
                }
                seen[u] = true;      // Trước khi đưa vào queue.
                dist[u] = dist[v] + 1;
                parent[u] = v;
                queue.addLast(u);
                enqueues++;
            }
        }
        return new BfsResult(
                List.copyOf(order), dist, parent, enqueues);
    }

    // Đối chứng: bỏ bản ghi lặp khi dequeue, nhưng enqueue dư.
    static long countEnqueuesMarkOnDequeue(
            int[][] graph, int source) {
        validateGraph(graph);
        checkVertex(graph.length, source);

        boolean[] seen = new boolean[graph.length];
        Deque<Integer> queue = new ArrayDeque<>();
        queue.addLast(source);
        long enqueues = 1L;

        while (!queue.isEmpty()) {
            int v = queue.removeFirst();
            if (seen[v]) {
                continue; // Phải bỏ qua trước khi mở rộng hàng kề.
            }
            seen[v] = true;
            for (int u : graph[v]) {
                queue.addLast(u);
                enqueues++;
            }
        }
        return enqueues;
    }

    // Stack frame giữ đúng vị trí cạnh kế tiếp của DFS đệ quy.
    static DfsResult dfsRecursiveOrderWithFrames(
            int[][] graph, int source) {
        validateGraph(graph);
        int n = graph.length;
        checkVertex(n, source);

        boolean[] seen = new boolean[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);
        List<Integer> order = new ArrayList<>();
        Deque<Frame> stack = new ArrayDeque<>();

        seen[source] = true;
        order.add(source);
        stack.push(new Frame(source));

        while (!stack.isEmpty()) {
            Frame frame = stack.peek();
            int v = frame.vertex;

            if (frame.nextNeighbor == graph[v].length) {
                stack.pop(); // Tương đương kết thúc dfs(v).
                continue;
            }

            int u = graph[v][frame.nextNeighbor];
            frame.nextNeighbor++;

            if (seen[u]) {
                continue;
            }
            seen[u] = true;
            parent[u] = v;
            order.add(u);
            stack.push(new Frame(u));
        }
        return new DfsResult(List.copyOf(order), parent);
    }

    // Nhiều nguồn, mỗi nguồn khác nhau chỉ enqueue một lần.
    static BfsResult multiSourceBfs(
            int[][] graph, int[] sources) {
        validateGraph(graph);
        if (sources == null) {
            throw new IllegalArgumentException("Null sources");
        }
        int n = graph.length;
        for (int s : sources) {
            checkVertex(n, s);
        }

        boolean[] seen = new boolean[n];
        int[] dist = new int[n];
        int[] parent = new int[n];
        Arrays.fill(dist, -1);
        Arrays.fill(parent, -1);

        Deque<Integer> queue = new ArrayDeque<>();
        List<Integer> order = new ArrayList<>();
        long enqueues = 0L;

        for (int s : sources) {
            if (seen[s]) {
                continue;
            }
            seen[s] = true;
            dist[s] = 0;
            queue.addLast(s);
            enqueues++;
        }

        while (!queue.isEmpty()) {
            int v = queue.removeFirst();
            order.add(v);

            for (int u : graph[v]) {
                if (seen[u]) {
                    continue;
                }
                seen[u] = true;
                dist[u] = dist[v] + 1;
                parent[u] = v;
                queue.addLast(u);
                enqueues++;
            }
        }
        return new BfsResult(
                List.copyOf(order), dist, parent, enqueues);
    }

    public static void main(String[] args) {
        // Đồ thị có hướng; 0→1 xuất hiện hai lần,
        // 2→3→5→2 là một chu trình; 6 đứng riêng.
        int[][] graph = {
            {1, 2, 1}, // 0
            {3, 4},    // 1
            {3, 4},    // 2
            {5},       // 3
            {5},       // 4
            {2},       // 5
            {}         // 6
        };

        BfsResult breadth = bfs(graph, 0);
        System.out.println("BFS order: " + breadth.order());
        System.out.println("BFS distances: "
                + Arrays.toString(breadth.distances()));
        System.out.println("BFS parents: "
                + Arrays.toString(breadth.parents()));
        System.out.println("Mark-on-enqueue enqueues: "
                + breadth.enqueues());
        System.out.println("Mark-on-dequeue enqueues: "
                + countEnqueuesMarkOnDequeue(graph, 0));

        DfsResult depth = dfsRecursiveOrderWithFrames(graph, 0);
        System.out.println("DFS recursive-order frames: "
                + depth.order());
        System.out.println("DFS parents: "
                + Arrays.toString(depth.parents()));

        BfsResult multi = multiSourceBfs(
                graph, new int[] {0, 6, 0});
        System.out.println("Multi-source order: " + multi.order());
        System.out.println("Multi-source distances: "
                + Arrays.toString(multi.distances()));
        System.out.println("Multi-source enqueues: "
                + multi.enqueues());
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac VisitTimingGraphDemo.java
java VisitTimingGraphDemo
~~~

**Đầu ra chính xác (danh sách kề và thứ tự duyệt như mã):**

~~~text
BFS order: [0, 1, 2, 3, 4, 5]
BFS distances: [0, 1, 1, 2, 2, 3, -1]
BFS parents: [-1, 0, 0, 1, 1, 3, -1]
Mark-on-enqueue enqueues: 6
Mark-on-dequeue enqueues: 11
DFS recursive-order frames: [0, 1, 3, 5, 2, 4]
DFS parents: [-1, 0, 5, 1, 2, 3, -1]
Multi-source order: [0, 6, 1, 2, 3, 4, 5]
Multi-source distances: [0, 1, 1, 2, 2, 3, 0]
Multi-source enqueues: 7
~~~

### Đọc các kết quả

**BFS:** đỉnh 3 và 4 thuộc lớp khoảng cách 2; đỉnh 5 thuộc lớp 3; đỉnh 6 không tới được từ nguồn 0 nên có distance và parent là -1.

**Enqueue count:** 6 lần khi mark-on-enqueue; 11 lần với bản đối chứng chỉ mark khi dequeue và kiểm tra bỏ trùng. Bản đối chứng không đo thời gian CPU, mà đo **số bản ghi đưa vào queue** trên chính đồ thị này.

**DFS:** thứ tự `[0,1,3,5,2,4]` khác BFS vì DFS đi sâu qua 1→3→5→2 trước khi quay lại cạnh 0→2. Các parent DFS cũng khác, và chúng không nhằm tối ưu số cạnh.

**Multi-source:** hai nguồn thực sự khác nhau là 0 và 6 (0 lặp lại bị bỏ). Queue đầu là [0,6], vì vậy order đưa 6 vào ngay sau 0, và mọi đỉnh đều được khám phá một lần.

## 14. Độ phức tạp: thứ gì giảm khi đánh dấu sớm?

Giả sử đồ thị biểu diễn bằng danh sách kề, có V đỉnh, E phần tử cạnh. Với đồ thị vô hướng lưu hai chiều, E trong công thức có thể hiểu là số **mục danh sách kề**, khoảng 2 lần số cạnh vô hướng.

### BFS mark-on-enqueue

- Mỗi đỉnh được enqueue/dequeue tối đa một lần.
- Mỗi hàng kề của đỉnh được khám phá được quét một lần.
- Tổng công việc **O(V+E)** nếu bao gồm khởi tạo mảng `seen/dist/parent` cho V đỉnh.
- Bộ nhớ phụ: mảng trạng thái, distance, parent và queue, tất cả **O(V)**; nếu lưu thứ tự duyệt cũng O(V).
- Các cạnh song song làm tăng E và số lần kiểm tra `seen[u]` nhưng **không làm tăng số lần enqueue một đỉnh**.

Nếu chỉ thăm một thành phần, chính xác hơn có thể nói quét các cạnh đi ra từ các đỉnh đạt tới và vẫn tốn O(V) khi cấp phát/khởi tạo mảng dài V.

### Bản mark-on-dequeue có bỏ trùng

Nếu mỗi đỉnh chỉ được mở rộng **ở lần dequeue đầu**, số lần quét cạnh vẫn O(E) và thời gian tổng thể thường vẫn **O(V+E)**. Nhưng có thể enqueue mỗi mục cạnh đi ra từ các đỉnh được mở rộng, tức O(E) bản ghi, khiến queue chiếm **O(V+E)** bộ nhớ theo cận trên tổng quát, không còn bảo đảm O(V) bản ghi trong hàng đợi.

Ví dụ có nhiều cạnh song song cùng đi tới một đỉnh: queue có thể chứa rất nhiều bản ghi giống nhau trước khi bất kỳ bản nào được dequeue. Mark-on-enqueue tránh hoàn toàn tình huống này.

### DFS frames

Mỗi đỉnh được đánh dấu và push frame tối đa một lần; mỗi cạnh kề được xét một lần; **O(V+E)** thời gian, O(V) bộ nhớ phụ cho seen/parent/stack/order. Stack chỉ chứa **đường đi DFS đang mở**, độ sâu tối đa số đỉnh tới được. Đây là lý do DFS đệ quy cũng dùng O(V) stack trong trường hợp xấu và có nguy cơ `StackOverflowError` khi đường đi rất sâu.

### Biểu diễn bằng ma trận kề

Nếu dùng ma trận V×V và với mỗi đỉnh phải quét **toàn bộ V cột** để tìm hàng xóm, duyệt có thể mất **O(V²)** thay vì O(V+E). Mark-on-enqueue vẫn quan trọng để không đưa lặp đỉnh, nhưng **không thể tự giảm chi phí quét ma trận** xuống O(V+E) nếu thuật toán vẫn duyệt mọi ô của từng hàng.

## 15. Kiểm thử và các bất biến dễ xác nhận

Một bài kiểm thử tốt cần kiểm tra **không chỉ thứ tự in ra**, mà cả các đặc tính cơ bản:

1. Với BFS mark-on-enqueue, **không có đỉnh lặp** trong order, và `enqueues==order.size()`.
2. Đỉnh nguồn có `distance[source]=0`, `parent[source]=-1`.
3. Đỉnh không đạt tới có `distance[v]=-1` và `parent[v]=-1`.
4. Với mọi đỉnh v đạt tới, v khác nguồn, parent[v] phải có cạnh `parent[v]→v` trong đồ thị và `distance[parent[v]]+1==distance[v]`.
5. Độ dài ngắn nhất độc lập với thứ tự duyệt các cạnh kề, mặc dù parent và thứ tự khám phá có thể khác.
6. Với DFS frames, order không lặp đỉnh; parent mô tả cạnh thực và cây DFS trùng DFS đệ quy theo thứ tự hàng kề.
7. Với multi-source, mọi nguồn phân biệt có distance=0, mỗi đỉnh enqueue tối đa một lần và khoảng cách là min của khoảng cách từ các nguồn.
8. Với self-loop và chu trình, thuật toán vẫn kết thúc nhờ seen được đánh dấu trước lịch duyệt.
9. Với đồ thị không có cạnh, BFS từ một nguồn chỉ trả một đỉnh; multi-source trả các nguồn phân biệt.
10. Đồ thị có đỉnh ngoài thành phần của source thì BFS không tự động thăm chúng.

### Oracle độc lập cho khoảng cách

Với đồ thị nhỏ, có thể tính khoảng cách ngắn nhất bằng **lặp thư giãn theo số cạnh** (dùng V−1 lượt trên các cạnh; hoặc Floyd–Warshall cho mọi cặp). So mảng distance của BFS với kết quả này. Với multi-source, khởi tạo tất cả nguồn có khoảng cách 0 rồi thực hiện các lượt thư giãn. Đây là kiểm thử độc lập hơn việc chỉ chạy hai phiên bản BFS giống nhau.

### Oracle độc lập cho DFS frames

Viết một DFS **đệ quy trực tiếp** cho đồ thị nhỏ, đánh dấu khi vào hàm và đi lần lượt các cạnh `adj[v]`. So **order và parent** với bản stack frames. Thử:
- Đồ thị hình cây (không có cạnh chéo).
- Đồ thị có nhiều cạnh hội tụ.
- Đồ thị có chu trình.
- Hai hoặc nhiều cạnh song song.
- Self-loop `v→v`.
- Đồ thị nhiều thành phần và nguồn bất kỳ.

### Tạo ca ngẫu nhiên

Với V từ 1 tới 10, sinh các danh sách kề gồm cạnh ngẫu nhiên (cho phép trùng và tự khép), rồi:

- Chọn nguồn s ngẫu nhiên.
- Chạy BFS mark-on-enqueue, kiểm tra order không trùng và enqueue count bằng số đỉnh được phát hiện.
- So distance với oracle relax V−1 vòng.
- Chạy DFS frames và DFS đệ quy trực tiếp, so toàn bộ order/parent.
- Chọn một tập nguồn ngẫu nhiên có thể chứa lặp, so multi-source distances với oracle đa nguồn.
- Kiểm tra số lần enqueue của bản đối chứng mark-on-dequeue **không nhỏ hơn** bản mark-on-enqueue, và xác nhận bản đối chứng kết thúc.

**Cẩn thận với số đỉnh bằng 0:** graph rỗng là biểu diễn hợp lệ của đồ thị không đỉnh, nhưng không có source hợp lệ cho BFS một nguồn/DFS một nguồn. API trong mã ném lỗi nếu gọi `bfs(empty,0)`; multi-source với nguồn rỗng vẫn có thể trả mảng kết quả rỗng. Điều này là một **hợp đồng API**, không phải mâu thuẫn với lý thuyết đồ thị.

## 16. Các lỗi phổ biến và cách sửa

1. **Đánh dấu khi dequeue nhưng không bỏ bản ghi lặp:** dễ mở rộng một đỉnh nhiều lần; trên chu trình có thể không kết thúc.
2. **Không đánh dấu source trước enqueue:** self-loop/cạnh quay về source có thể enqueue lại source.
3. **Dùng `visited[v]` thay cho `visited[u]` trong vòng hàng xóm:** đánh dấu sai đỉnh mới phát hiện.
4. **Enqueue trước, đánh dấu sau một đoạn xử lý dài:** nhiều cạnh khác có thể nhận u là chưa phát hiện; trong mã tuần tự đơn giản, nên đặt sát nhau và đánh dấu trước.
5. **Ghi đè parent/distance dù u đã discovered:** phá cây đường đi ngắn nhất của BFS.
6. **Bỏ toàn bộ cạnh song song vì chúng “không có ý nghĩa”:** về reachability có thể không đổi, nhưng thuật toán vẫn phải xử lý đúng nếu đầu vào chứa chúng.
7. **Không kiểm tra chỉ số cạnh hợp lệ:** `adj[v]` chứa u âm hoặc ≥V làm truy cập mảng sai.
8. **Tạo lại visited ở mỗi vòng lặp thành phần:** mất thông tin duyệt cũ, mở rộng lặp nhiều đỉnh.
9. **Cho rằng DFS stack push ngược hàng xóm luôn trùng DFS đệ quy:** thứ tự và parent có thể khác do đánh dấu các hàng xóm trước khi khám phá nhánh.
10. **Đánh dấu DFS quá muộn:** một đỉnh đang nằm trên stack vẫn có thể bị thêm lần nữa qua chu trình.
11. **Dùng một boolean để phát hiện mọi loại chu trình:** DFS có hướng cần phân biệt GRAY/BLACK; vô hướng cần xem parent và có thể cần edge ID với cạnh song song.
12. **Dùng BFS cho đồ thị có trọng số không đều rồi tin khoảng cách tối ưu theo tổng trọng số:** BFS chỉ tối ưu số cạnh khi các cạnh có cùng trọng số.
13. **Đánh dấu Dijkstra đã chốt lúc push vào priority queue:** một đường tốt hơn có thể được tìm thấy sau đó.
14. **Nói mark-on-dequeue có skip luôn có thời gian hàm mũ:** không đúng với mỗi đỉnh được mở rộng một lần; nó thường vẫn O(V+E) nhưng tốn bản ghi và bộ nhớ.
15. **Không tính biểu diễn đồ thị:** O(V+E) cho danh sách kề, nhưng quét ma trận có thể O(V²).
16. **Nhầm distance=-1 với một khoảng cách thực:** -1 là sentinel “chưa tới được” theo hợp đồng code.
17. **Không phân biệt đường đi có hướng và vô hướng:** cạnh `v→u` không ngụ ý `u→v` trong đồ thị có hướng.
18. **Dùng order duyệt làm đường đi tối ưu:** order là thứ tự phát hiện/hoàn tất, không phải đường path từ source tới target; cần parent.
19. **Cần kiểm soát đồng thời nhưng dùng boolean không đồng bộ:** khi nhiều luồng khám phá song song, kiểm tra và đánh dấu phải là thao tác đồng bộ/atomic để giữ “enqueue một lần”. Bài này xét phiên bản tuần tự.
20. **Tái sử dụng seen không reset giữa những lần duyệt độc lập:** một lượt BFS mới từ nguồn khác cần trạng thái mới hoặc cơ chế thế hệ (timestamp) có quy tắc reset rõ ràng.

## 17. Checklist trước khi nộp lời giải BFS/DFS

- Đề bài là **reachability, shortest unweighted path, DFS order, detect cycle** hay một mục tiêu khác?
- `visited` có nghĩa là **đã phát hiện** hay **đã xử lý xong**?
- Source có được đánh dấu trước khi enqueue/push không?
- Trong BFS, hàng xóm u có được đánh dấu **tại lần phát hiện đầu**, trước enqueue không?
- Một đỉnh có thể đi vào queue/stack **hơn một lần** không? Nếu có, đó là chủ đích hay lỗi?
- Nếu mark-on-dequeue, đã `continue` ngay khi lấy được bản ghi lặp chưa?
- Có xử lý duplicate edges, self-loop, chu trình và đồ thị không liên thông không?
- `parent[u]` và `distance[u]` có được ghi **một lần khi phát hiện** trong BFS chuẩn không?
- DFS iterative có cần **trùng thứ tự/cây cha** DFS đệ quy không? Nếu cần, đã dùng stack frames hoặc cơ chế tương đương chưa?
- Nếu tìm chu trình có hướng, có phân biệt GRAY và BLACK không?
- Nếu dùng priority queue và trọng số, có kiểm tra điều kiện Dijkstra thay vì sao chép quy tắc BFS không?
- Đã tính đúng thời gian **O(V+E)** và bộ nhớ **O(V)** cho bản mark-on-enqueue với danh sách kề chưa?
- Có kiểm thử độc lập khoảng cách BFS và thứ tự/cha DFS không?
- Các chỉ số, nguồn rỗng, graph rỗng và cạnh ngoài miền có được xử lý theo hợp đồng không?

**Ghi nhớ:** với **BFS trên đồ thị không trọng số**, đánh dấu đỉnh **ngay khi đưa vào hàng đợi** bảo đảm mỗi đỉnh được enqueue tối đa một lần và lần phát hiện đầu đã cho khoảng cách ngắn nhất. Với **DFS**, đánh dấu ngay khi bắt đầu khám phá ngăn lặp; nếu muốn mô phỏng chính xác đệ quy, lưu **khung duyệt và vị trí hàng xóm kế tiếp**. Việc chọn thời điểm đánh dấu phải xuất phát từ **bất biến của thuật toán**, không từ một quy tắc thuộc lòng áp dụng cho mọi cấu trúc dữ liệu chờ xử lý.
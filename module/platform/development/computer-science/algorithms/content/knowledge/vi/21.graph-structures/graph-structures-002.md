# Sắp xếp tô-pô bằng thứ tự kết thúc DFS

**Sắp xếp tô-pô (topological sorting)** là cách sắp xếp các đỉnh của một **đồ thị có hướng không có chu trình** (*Directed Acyclic Graph – DAG*) sao cho mọi cạnh `u→v` đều đi **từ đỉnh xuất hiện trước tới đỉnh xuất hiện sau** trong thứ tự. Kỹ thuật này rất quan trọng khi những công việc, mô-đun, môn học, bước biên dịch hoặc trạng thái quy hoạch động có **quan hệ phụ thuộc trước–sau**.

Một phương pháp cổ điển để tạo thứ tự tô-pô là **DFS và thứ tự kết thúc**:

> Chạy DFS qua **mọi đỉnh**; mỗi lần DFS xử lý xong toàn bộ các đỉnh đi tiếp từ `u`, đưa `u` vào danh sách **theo thứ tự kết thúc**. Nếu đồ thị không có chu trình, **đảo ngược danh sách đó** sẽ cho một thứ tự tô-pô hợp lệ.

Điều kiện “nếu không có chu trình” là cốt lõi: **đảo thứ tự kết thúc của DFS trên đồ thị có chu trình không biến nó thành DAG**. Bộ giải đúng phải nhận diện chu trình, báo không có thứ tự tô-pô, và không trả một danh sách sai dưới nhãn “kết quả”.

Bài học thuộc nhóm **Cấu trúc đồ thị**. Ta sẽ làm rõ thời điểm **phát hiện/kết thúc** của DFS, cách chứng minh mọi cạnh đi đúng hướng, ba màu **WHITE/GRAY/BLACK** để phát hiện chu trình, DFS lặp bằng **stack frame** tránh tràn ngăn xếp Java, cách xử lý các đỉnh cô lập hoặc nhiều nhánh rời nhau, so sánh với **Kahn**, và chương trình Java 17+ có kiểm chứng độc lập trên **4.166 đồ thị có hướng** kích thước nhỏ.

## 1. Định nghĩa toán học của thứ tự tô-pô

Cho đồ thị có hướng `G=(V,E)`, trong đó `V={0,1,...,n−1}` và một cạnh `(u,v)∈E` có nghĩa `u→v`. Một **thứ tự tô-pô** là một **hoán vị** `order[0..n−1]` của tất cả `n` đỉnh thỏa:

```text
Với mọi cạnh u -> v:
    position[u] < position[v]
```

Trong đó `position[x]` là vị trí của đỉnh `x` trong mảng `order`.

Hai yêu cầu bắt buộc:

1. **Có đủ tất cả đỉnh, mỗi đỉnh đúng một lần.** Một danh sách thiếu đỉnh cô lập chưa phải thứ tự tô-pô của toàn đồ thị.
2. **Mỗi cạnh đi từ trái sang phải** trong danh sách. Chỉ kiểm tra danh sách là hoán vị vẫn chưa đủ.

Ví dụ:

```text
0 -> 2
0 -> 3
1 -> 3
1 -> 4
2 -> 5
3 -> 5
4 -> 6
5 -> 6
7 là đỉnh cô lập
```

Cả hai thứ tự dưới đây đều hợp lệ:

```text
[0, 1, 2, 3, 4, 5, 6, 7]
[7, 1, 4, 0, 3, 2, 5, 6]
```

Trong cả hai, mọi đầu `u` của một cạnh `u→v` xuất hiện trước `v`. Đỉnh `7` không có ràng buộc với ai, nên có thể đứng ở nhiều vị trí khác nhau.

**Thứ tự tô-pô có thể không duy nhất.** Nếu đề chỉ yêu cầu “một thứ tự hợp lệ”, không nên đòi code phải khớp một thứ tự mẫu duy nhất. Nếu đề yêu cầu **thứ tự nhỏ nhất theo từ điển**, DFS đảo finish order thông thường **không đảm bảo** điều đó; có thể dùng phiên bản Kahn với **min-priority queue**.

### Cách hiểu bằng quan hệ phụ thuộc

Nếu `u→v` nghĩa là “phải hoàn thành `u` trước khi bắt đầu `v`”, thứ tự tô-pô là lịch trình thực hiện tuần tự tôn trọng mọi phụ thuộc. Các ứng dụng:

- Chọn thứ tự học môn khi môn A là điều kiện tiên quyết của môn B.
- Biên dịch các mô-đun phần mềm theo dependency graph.
- Lên lịch các công việc có ràng buộc trước–sau.
- Duyệt trạng thái DAG trong quy hoạch động.
- Tính đường đi dài nhất/ngắn nhất trên DAG theo thứ tự tô-pô thích hợp.

Đồ thị ở đây là **có hướng**. Không tự bỏ hướng cạnh: nếu bỏ hướng, thông tin bắt buộc “trước–sau” sẽ biến mất.

## 2. Khi nào tồn tại thứ tự tô-pô? Chính xác là DAG

Một định lý cơ bản:

> **Một đồ thị có hướng hữu hạn có thứ tự tô-pô nếu và chỉ nếu nó không có chu trình có hướng.**

### Nếu có chu trình thì không thể sắp xếp

Giả sử có chu trình:

```text
a -> b -> c -> a
```

Một thứ tự tô-pô sẽ buộc:

```text
position[a] < position[b]
position[b] < position[c]
position[c] < position[a]
```

Suy ra `position[a]<position[a]`, mâu thuẫn. Chu trình dài hơn cũng tương tự. Một **self-loop `u→u`** đã là chu trình dài 1 và đòi `position[u]<position[u]`, cũng bất khả thi.

### Nếu không có chu trình thì có thể sắp xếp

Trong mọi DAG không rỗng, luôn tồn tại ít nhất một đỉnh **không có cạnh đi vào** (*indegree* bằng 0). Nếu mọi đỉnh đều có cạnh đi vào, bắt đầu từ một đỉnh bất kỳ rồi liên tục đi theo cạnh đi vào, vì hữu hạn đỉnh sẽ có đỉnh lặp, tạo chu trình, trái giả thiết.

Ta có thể lấy đỉnh indegree 0 ra đầu thứ tự, bỏ đỉnh/các cạnh ra và lặp lại. Đây là ý tưởng của **Kahn**. DFS đảo thứ tự kết thúc cho một chứng minh khác, trình bày ở mục 5.

### Bài toán phát hiện chu trình khác với “cố sắp xếp”

Không trả thứ tự tô-pô khi đồ thị có chu trình; kể cả một danh sách trông đủ `n` đỉnh cũng không thể đáp ứng mọi cạnh. Một API rõ ràng có thể trả:

```text
DAG: order = một hoán vị hợp lệ của tất cả đỉnh
Cyclic: order = [] và cycle = ví dụ chu trình có hướng
```

Với đồ thị rỗng `n=0`, tồn tại một hoán vị rỗng, nên đồ thị rỗng là **DAG**, và thứ tự tô-pô hợp lệ là `[]`. Vì vậy **chỉ dùng order rỗng để suy đoán có chu trình là sai** khi `n=0`; nên trả cả cờ `isDAG` hoặc so độ dài order với `n`.

## 3. DFS có hai thời điểm: phát hiện và kết thúc

Trong **Depth-First Search (DFS)**, một đỉnh `u` trải qua ba trạng thái:

1. **WHITE (0):** chưa được phát hiện.
2. **GRAY (1):** đã vào DFS của `u` nhưng **chưa kết thúc**; `u` còn nằm trên ngăn xếp đường đi DFS hiện hành.
3. **BLACK (2):** toàn bộ cạnh kề của `u` đã được xét và mọi lời gọi DFS con từ `u` đã kết thúc.

Nếu gắn thời gian tăng dần, ta có:

```text
discover[u] = thời điểm chuyển WHITE -> GRAY
finish[u]   = thời điểm chuyển GRAY -> BLACK

discover[u] < finish[u]
```

**Thứ tự phát hiện** khác **thứ tự kết thúc**. Sắp xếp topo bằng DFS phải lấy **đảo ngược thứ tự kết thúc**, không phải chỉ lấy thứ tự các đỉnh được phát hiện lần đầu.

### Ví dụ đường dài

```text
A -> B -> C
```

DFS bắt đầu ở A:

```text
Phát hiện:  A, B, C
Kết thúc:  C, B, A
Đảo finish: A, B, C
```

Nếu khi **vừa phát hiện** một đỉnh đã đưa nó vào kết quả rồi đảo lại, ta sẽ nhận `C,B,A`, sai toàn bộ phụ thuộc. Phải thêm đỉnh vào danh sách **sau** khi xử lý hết các cạnh outgoing của nó.

### Postorder và reverse postorder

- **Postorder/finish order:** đỉnh được ghi vào danh sách tại thời điểm kết thúc DFS.
- **Reverse postorder:** đảo thứ tự danh sách postorder, tương đương sắp đỉnh theo **thời gian kết thúc giảm dần**.

Trong DAG, reverse postorder là một thứ tự tô-pô hợp lệ. Khi các cạnh có hướng tạo nhiều nhánh và nhiều gốc DFS, kết quả vẫn đúng nếu chạy DFS phủ **toàn bộ tập đỉnh**.

## 4. Mẫu thuật toán DFS topo đệ quy

Giả sử đồ thị đã được biết là DAG, khuôn đơn giản:

```text
visited[0..n-1] = false
finishOrder = []

dfs(u):
    visited[u] = true
    for v in adj[u]:
        if not visited[v]:
            dfs(v)
    finishOrder.add(u)     // SAU khi xử lý xong mọi hàng xóm

for root = 0..n-1:
    if not visited[root]:
        dfs(root)

topologicalOrder = reverse(finishOrder)
```

**Điều kiện:** Khuôn trên chỉ tự nó tạo thứ tự tô-pô đáng tin khi **đã có bảo đảm DAG từ input hoặc từ một bước kiểm tra khác**. Để vừa tìm thứ tự vừa phát hiện chu trình, thay `visited` đơn giản bằng **ba màu** (mục 6).

### Vì sao có vòng lặp ngoài qua mọi đỉnh?

Một lần `dfs(0)` chỉ đi theo các cạnh có hướng xuất phát từ 0. Nó không thể tự đi tới các đỉnh không reachable từ 0, kể cả những đỉnh có cạnh đi **vào** 0, các nhánh độc lập hoặc đỉnh cô lập.

Nếu đề yêu cầu sắp toàn bộ đồ thị, phải:

```text
for root = 0..n-1:
    if WHITE:
        DFS(root)
```

Khi bắt đầu từ một đỉnh chưa thăm, DFS tạo **một cây mới trong rừng DFS**. Không nên đồng nhất các cây trong **rừng DFS có hướng** với thành phần liên thông yếu/mạnh; mục tiêu ở đây là **bao phủ toàn bộ đỉnh** và xây thứ tự kết thúc, không phải phân nhóm liên thông.

### Cần khởi tạo gì trước khi DFS?

- `color[v]=WHITE` cho tất cả đỉnh.
- `parent[v]=-1` nếu muốn dựng lại một chu trình.
- `finishOrder=[]` rỗng.
- `clock=0` nếu ghi thời điểm phát hiện và kết thúc.
- `stack=[]` trước mỗi DFS từ gốc mới; hoặc bảo đảm stack cũ đã rỗng.

**Không reset màu trong từng lượt root**: nếu làm vậy, một đỉnh có thể được khám phá nhiều lần, finish order chứa lặp, và độ phức tạp không còn `O(V+E)`.

## 5. Chứng minh đảo thứ tự kết thúc là topo trong DAG

Điều cần chứng minh: với **mọi cạnh `u→v` trong DAG**, `finish[u]>finish[v]`. Nếu đúng, xếp các đỉnh theo thời điểm kết thúc giảm dần sẽ đặt `u` trước `v`.

Xét lúc DFS đang kiểm tra cạnh `u→v`, có ba trường hợp cho `v`:

**Trường hợp 1 — `v` còn WHITE.**

DFS đi sâu vào `v`, khám phá và kết thúc toàn bộ nhánh con của `v` **trước khi** kết thúc `u`. Vì vậy:

```text
finish[v] < finish[u]
```

**Trường hợp 2 — `v` đã BLACK.**

`v` đã kết thúc trước khi cạnh từ `u` được xem xét, trong khi `u` còn GRAY và chưa kết thúc. Do đó:

```text
finish[v] < finish[u]
```

**Trường hợp 3 — `v` đang GRAY.**

`v` đang nằm trên đường đi DFS hiện tại từ một tổ tiên tới `u`. Cạnh `u→v` tạo thành **chu trình có hướng**: đường trên cây DFS từ `v` xuống `u`, rồi cạnh `u→v`. Trường hợp này **không thể xảy ra trong DAG**.

Vậy, nếu đồ thị là DAG, với mọi cạnh `u→v` ta đều có:

```text
finish[u] > finish[v]
```

Sắp theo finish giảm dần cho `position[u]<position[v]`. Đồng thời mỗi đỉnh được kết thúc đúng một lần, nên danh sách là hoán vị đủ `n` đỉnh. Suy ra đó là **thứ tự tô-pô**.

**Đây là chứng minh cho toàn đồ thị**, không chỉ một cây DFS. Nếu `u` và `v` thuộc các cây DFS khác nhau, với một cạnh `u→v`, khi cạnh được xét thì `v` không thể GRAY nếu DAG. Nó hoặc đã BLACK hoặc sẽ được thăm từ `u`, do đó quan hệ finish vẫn đúng.

### Liên hệ với phân loại cạnh DFS

Trong đồ thị có hướng, các cạnh có thể thuộc:

- **Tree edge:** tới đỉnh WHITE, trở thành cạnh cây DFS.
- **Back edge:** tới đỉnh GRAY, chứng minh tồn tại chu trình có hướng.
- **Forward edge / cross edge:** tới đỉnh BLACK; tuy khác quan hệ tổ tiên, đều không cản trở thứ tự topo trong DAG.

Đừng suy ra “có cạnh tới một đỉnh đã thăm nghĩa là có chu trình”. Chỉ cạnh tới đỉnh **đang GRAY**, tức đang ở trên đường DFS hiện hành, mới là chứng cứ tức thì cho chu trình.

## 6. Phát hiện chu trình bằng ba màu và dựng một chu trình cụ thể

Giả sử DFS đang xét cạnh `u→v`.

| Màu của `v` | Xử lý | Ý nghĩa |
| --- | --- | --- |
| WHITE | Đánh dấu GRAY và DFS(v) | Đây là lần đầu phát hiện v |
| GRAY | Báo **chu trình có hướng** | Cạnh quay về một tổ tiên đang hoạt động |
| BLACK | Bỏ qua cho DFS (không cần mở lại) | v đã được xử lý xong |

Trong cách cài đặt này, **GRAY là trạng thái của ngăn xếp đệ quy / frame đang hoạt động**, không có nghĩa “đã từng được thăm” chung chung.

### Ví dụ chu trình

```text
0 -> 1 -> 2 -> 0
          |
          v
          3
```

Khi đang DFS ở 2 và gặp cạnh `2→0`, đỉnh 0 còn GRAY. Đường cha trong cây DFS là:

```text
0 -> 1 -> 2
```

Thêm cạnh `2→0` sẽ khép thành chu trình:

```text
[0,1,2,0]
```

Có thể dựng witness như sau:

1. Bắt đầu từ `u=2`.
2. Đi ngược `parent[2]=1`, `parent[1]=0` đến `v=0`.
3. Đảo chuỗi ngược thành `[0,1,2]`.
4. Thêm `0` cuối cùng để biểu diễn cạnh `2→0`.

Mọi cặp đỉnh liên tiếp trong witness đều phải có cạnh **đúng hướng**. Hai đầu giống nhau vì biểu diễn một đường đi khép kín.

### Self-loop và cạnh song song

- Với self-loop `u→u`, tại lúc duyệt `u` nó còn GRAY; có chu trình `[u,u]`. Một đồ thị chỉ có một self-loop **không có topo**.
- Hai bản sao của một cạnh `u→v` **không tự tạo chu trình**; nếu `v` đã BLACK, cả hai có thể được bỏ qua. Nếu `v` là WHITE ở bản sao đầu, DFS đi vào v rồi quay về; bản sao kế thường gặp v BLACK.
- Nếu có cả `u→v` và `v→u`, đó là chu trình hai đỉnh `[u,v,u]`.

**Không thể áp nguyên quy tắc “cạnh tới GRAY = chu trình” cho đồ thị vô hướng** mà không xét cạnh ngược về cha: cạnh vô hướng được lưu hai chiều, nên đỉnh con sẽ thấy cha đang GRAY dù đó chỉ là một cạnh cây. Bài này chuyên về **đồ thị có hướng**.

### Điều gì nên trả khi có chu trình?

Trả rõ:

```text
dag = false
order = []
cycle = một witness đóng, ví dụ [0,1,2,0]
```

Thứ tự kết thúc tại thời điểm phát hiện chu trình có thể **chưa đầy đủ**. Không được lấy phần đã finish, đảo lại rồi gán nhãn topo. Trong chương trình Java, khi phát hiện chu trình, danh sách topo và finish order trong kết quả được đặt **rỗng** có chủ ý; mảng thời gian chỉ là trace chưa hoàn tất và không được diễn giải thành một thứ tự topo.

## 7. DFS lặp với stack frame: tránh tràn call stack Java

DFS đệ quy ngắn gọn nhưng trên đồ thị hình đường đi rất dài (ví dụ vài trăm nghìn đỉnh), số lần lồng hàm có thể khiến Java ném `StackOverflowError`.

Ta có thể mô phỏng quá trình vào/ra hàm bằng **ngăn xếp frame** trên heap. Mỗi frame lưu:

```text
vertex       // Đỉnh đang nằm trên stack DFS
nextNeighbor // Chỉ số hàng xóm tiếp theo chưa kiểm tra
```

Cách vận hành:

```text
for root = 0..n-1:
    nếu root BLACK: bỏ qua
    nếu root WHITE:
        color[root] = GRAY
        discover[root] = ++clock
        stack.push(Frame(root,0))

        while stack còn frame:
            frame = stack.peek()
            u = frame.vertex

            nếu frame.nextNeighbor == adj[u].size:
                color[u] = BLACK
                finish[u] = ++clock
                finishOrder.add(u)
                stack.pop()
                continue

            v = adj[u][frame.nextNeighbor]
            frame.nextNeighbor++

            nếu color[v] == WHITE:
                parent[v] = u
                color[v] = GRAY
                discover[v] = ++clock
                stack.push(Frame(v,0))

            ngược lại nếu color[v] == GRAY:
                phát hiện chu trình và trả kết quả thất bại

sau mọi root:
    topo = reverse(finishOrder)
```

**Vì sao phải lưu `nextNeighbor`?** Khi đi sâu vào đỉnh con, frame cha phải “tạm dừng” đúng tại vị trí hàng xóm kế tiếp. Khi con hoàn thành, thuật toán tiếp tục xét phần còn lại của danh sách kề của cha. Chỉ khi tất cả hàng xóm đã được xét, frame cha mới kết thúc và được thêm vào finish order.

### Một kiểu stack chỉ chứa đỉnh có thể gây lỗi finish order

Nếu dùng:

```text
pop u từ stack
finishOrder.add(u)
push các neighbor vào stack
```

thì `u` đang được ghi “kết thúc” **trước khi các đỉnh con hoàn thành**. Đó không phải postorder của DFS; đảo thứ tự có thể vi phạm cạnh. Cần dùng **frame với vị trí hàng xóm** hoặc kỹ thuật **sự kiện vào/ra (enter/exit events)** có bảo đảm màu và finish đúng.

### Khi nào đánh màu?

- Vừa phát hiện đỉnh → `WHITE→GRAY`, ngay trước khi push frame.
- Khi frame đã xét hết hàng xóm → `GRAY→BLACK`, ngay trước khi pop và ghi finish.
- Đừng chuyển thẳng WHITE→BLACK ở thời điểm push: khi gặp một cạnh trở lại đường đi hiện hành, sẽ không còn thông tin GRAY để phát hiện chu trình.

Mỗi đỉnh được push frame đúng một lần, và mỗi mục cạnh được xét đúng một lần. Vì vậy cấu trúc này vẫn có thời gian `O(n+m)` cho DFS khi đã có adjacency list.

## 8. Vết tính chi tiết trên DAG có nhánh và đỉnh cô lập

Xét lại đồ thị 8 đỉnh:

```text
0 -> 2, 0 -> 3
1 -> 3, 1 -> 4
2 -> 5
3 -> 5
4 -> 6
5 -> 6

Đỉnh 7 không có cạnh.
```

Chương trình còn thêm **một bản sao của `2→5`** để kiểm tra cạnh song song; việc đó không thay đổi DAG.

Quy ước:

- Duyệt root theo thứ tự `0,1,...,7`.
- Danh sách kề của mỗi đỉnh **được sort tăng dần**.
- Chỉ số thời gian bắt đầu ở `0`; tăng một lần khi phát hiện và một lần khi kết thúc.

### Diễn biến DFS

Bắt đầu `root=0`:

```text
0 -> 2 -> 5 -> 6
                   finish 6, rồi 5, rồi 2

quay lại 0 -> 3
                 3 thấy 5 đã BLACK, nên không mở lại
                 finish 3, rồi finish 0
```

Tiếp tục vòng root: `1` còn WHITE.

```text
1 -> 3 đã BLACK, bỏ qua
1 -> 4 -> 6 đã BLACK, finish 4, rồi finish 1
```

Cuối cùng `root=7` còn WHITE, là đỉnh cô lập nên phát hiện và kết thúc ngay.

**Thứ tự kết thúc (postorder):**

```text
[6, 5, 2, 3, 0, 4, 1, 7]
```

**Đảo ngược (reverse postorder = thứ tự tô-pô):**

```text
[7, 1, 4, 0, 3, 2, 5, 6]
```

Mảng thời điểm phát hiện/kết thúc:

| Đỉnh | `discover[v]` | `finish[v]` |
| ---: | ---: | ---: |
| 0 | 1 | 10 |
| 1 | 11 | 14 |
| 2 | 2 | 7 |
| 3 | 8 | 9 |
| 4 | 12 | 13 |
| 5 | 3 | 6 |
| 6 | 4 | 5 |
| 7 | 15 | 16 |

Ví dụ `0→2`: `finish[0]=10>finish[2]=7`, nên 0 đứng trước 2 trong thứ tự giảm finish. Tương tự, `3→5`: `9>6`; `5→6`: `6>5`. Mọi cạnh đều có quan hệ finish giảm như vậy.

Đỉnh 7 được thêm vào cuối finish order, vì nó là gốc cuối cùng theo vòng quét; sau đảo, nó đứng **đầu topo**. Điều này vẫn đúng: 7 không có phụ thuộc với bất kỳ đỉnh nào nên có thể đặt ở đầu hoặc cuối.

### Thứ tự Kahn của cùng DAG có thể khác

Nếu dùng Kahn với **hàng đợi ưu tiên nhỏ nhất** cho các đỉnh có indegree 0, một kết quả là:

```text
[0, 1, 2, 3, 4, 5, 6, 7]
```

Cả hai thứ tự đều hợp lệ. Việc hai thuật toán in khác nhau **không chứng minh một trong hai sai**. Muốn so kết quả, hãy kiểm tra điều kiện **`position[u]<position[v]` cho mọi cạnh** chứ không so mảng từng phần tử.

## 9. So sánh DFS finish order và thuật toán Kahn

Hai cách giải cùng bài toán nhưng nhìn từ hai hướng:

| Khía cạnh | DFS đảo finish order | Kahn indegree |
| --- | --- | --- |
| Ý tưởng | Hoàn tất những đỉnh phụ thuộc đi tiếp trước, rồi đảo danh sách | Đưa đỉnh chưa có phụ thuộc đi vào ra trước |
| Dữ liệu phụ | Color 0/1/2, stack DFS, finish order | Indegree, queue hoặc priority queue |
| Phát hiện chu trình | Cạnh tới đỉnh GRAY | Không lấy đủ `n` đỉnh ra khỏi queue |
| Một thứ tự xác định? | Nếu cố định thứ tự root và adjacency | Nếu cố định chính sách chọn indegree 0 |
| Đường chứng minh topo | Với mọi `u→v`, `finish[u]>finish[v]` | Khi lấy u, mọi cạnh đi vào u đã được gỡ |
| Thời gian cơ bản | `O(n+m)` | `O(n+m)` với queue thông thường |
| Thời gian khi muốn nhỏ nhất từ điển | DFS thường không trực tiếp đảm bảo | `O((n+m)log n)` với min-priority queue |
| Vết lỗi khi có chu trình | Có thể trả **witness** bằng parent | Có thể kết luận còn đỉnh chưa được lấy ra |

**Kahn đơn giản:**

```text
indegree[v] = số cạnh đi vào v
queue = mọi đỉnh có indegree 0

while queue không rỗng:
    lấy một đỉnh u
    ghi u vào order
    với mọi cạnh u -> v:
        indegree[v]--
        nếu indegree[v] trở thành 0: đưa v vào queue

nếu order.size == n:
    order là thứ tự topo
ngược lại:
    đồ thị có chu trình
```

Trong **đa đồ thị có cạnh song song**, indegree phải **đếm từng cạnh thực sự lưu** và lúc xử lý `u` phải **giảm tương ứng từng cạnh**. Nếu khởi tạo indegree có tính cạnh trùng nhưng bước giảm tự ý khử trùng, một đỉnh có thể không bao giờ đạt 0 dù DAG hợp lệ.

### Khi nào chọn cách nào?

- **DFS finish order:** thuận tiện khi đang cần DFS khác, muốn hiểu chính xác quan hệ sau/trước của cạnh, hoặc muốn dựng một chu trình bằng parent.
- **Kahn với queue:** mô hình rõ “làm việc nào đủ điều kiện trước”; dễ ứng dụng vào scheduling.
- **Kahn với priority queue:** phù hợp khi đề cần thứ tự tô-pô **nhỏ nhất theo từ điển**. Nhiều đáp án tô-pô khác nhau đều hợp lệ nếu đề không quy định thứ tự.
- **Cần phát hiện SCC:** không nên gọi DFS topo trên đồ thị có chu trình và tiếp tục; hãy phân rã SCC bằng Tarjan/Kosaraju nếu bài toán yêu cầu nén đồ thị thành DAG.

## 10. Java 17+ — DFS ba màu, stack frame, chu trình và kiểm thử

Chương trình **TopoDFSFinishDemo.java** được thiết kế để đọc được như một dự án nhỏ độc lập:

1. `fromEdges` nhận số đỉnh và danh sách **cạnh có hướng**; xác thực đầu mút và tạo danh sách kề **đã sort** để stdout xác định. Hỗ trợ self-loop và cạnh song song.
2. `topologicalByDFS` dùng **DFS lặp bằng frame**, phát hiện chu trình ngay khi gặp cạnh tới GRAY; trên DAG trả thứ tự topo, finish order và mảng thời gian.
3. `kahnMin` là một cách tính độc lập sử dụng **indegree và min-priority queue**.
4. `validTopological` kiểm tra một danh sách là hoán vị đầy đủ và mọi cạnh `u→v` thỏa `position[u]<position[v]`.
5. `validCycleWitness` kiểm tra đường chu trình trả về thực sự đi theo các cạnh có hướng.
6. `existsTopologicalByPermutations` là **oracle brute force** cho input cực nhỏ: thử các hoán vị đỉnh và dùng `validTopological` để biết có tồn tại thứ tự hay không; không dùng DFS/Kahn để suy đoán đáp án.
7. `verifyAllSmallDigraphs` thử **mọi đồ thị có hướng đơn không có self-loop với `n=0..4`**, đối chiếu ba góc nhìn: DFS, Kahn, brute force, đồng thời xác minh mọi cạnh đều có finish time đúng trong DAG.

**Với đồ thị có chu trình**, dữ liệu topo và finish order được trả **rỗng**, có một witness chu trình. Các mảng thời gian có thể chỉ chứa thông tin đang tính dở và **không được dùng** như thứ tự kết thúc hoàn chỉnh.

### Mã nguồn đầy đủ

Lưu thành **TopoDFSFinishDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.PriorityQueue;

public class TopoDFSFinishDemo {
    record Graph(int n, List<List<Integer>> out) {}

    record Result(
        boolean dag,
        List<Integer> order,
        List<Integer> finishOrder,
        List<Integer> cycle,
        int[] discover,
        int[] finish
    ) {}

    record Counts(int graphs, int dags, int cyclic) {}

    // DFS frame giữ vị trí neighbor tiếp theo chưa xét.
    static final class Frame {
        final int vertex;
        int nextIndex;

        Frame(int vertex) {
            this.vertex = vertex;
        }
    }

    // Chỉ đồ thị có hướng. Không thay đổi mảng edges của caller.
    static Graph fromEdges(int n, int[][] edges) {
        if (n < 0 || edges == null) {
            throw new IllegalArgumentException("bad n or edges");
        }

        List<List<Integer>> out = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            out.add(new ArrayList<>());
        }
        for (int[] e : edges) {
            if (e == null || e.length != 2) {
                throw new IllegalArgumentException("need a directed edge");
            }
            int u = e[0], v = e[1];
            if (u < 0 || v < 0 || u >= n || v >= n) {
                throw new IllegalArgumentException("edge outside [0,n)");
            }
            out.get(u).add(v);
        }

        // Sort trên các danh sách MỚI, không sửa edges.
        for (int u = 0; u < n; u++) {
            Collections.sort(out.get(u));
            out.set(u, List.copyOf(out.get(u)));
        }
        return new Graph(n, List.copyOf(out));
    }

    static Result topologicalByDFS(Graph g) {
        int n = g.n();
        // 0=WHITE, 1=GRAY, 2=BLACK.
        byte[] color = new byte[n];
        int[] parent = new int[n];
        int[] discover = new int[n];
        int[] finish = new int[n];
        Arrays.fill(parent, -1);

        List<Integer> finished = new ArrayList<>(n);
        int clock = 0;

        for (int root = 0; root < n; root++) {
            if (color[root] != 0) {
                continue;
            }

            ArrayDeque<Frame> stack = new ArrayDeque<>();
            color[root] = 1;
            discover[root] = ++clock;
            stack.push(new Frame(root));

            while (!stack.isEmpty()) {
                Frame current = stack.peek();
                int u = current.vertex;
                List<Integer> neighbors = g.out().get(u);

                if (current.nextIndex == neighbors.size()) {
                    // FINISH chỉ khi mọi cạnh outgoing đã xét.
                    color[u] = 2;
                    finish[u] = ++clock;
                    finished.add(u);
                    stack.pop();
                    continue;
                }

                int v = neighbors.get(current.nextIndex++);

                if (color[v] == 0) {
                    parent[v] = u;
                    color[v] = 1;
                    discover[v] = ++clock;
                    stack.push(new Frame(v));
                } else if (color[v] == 1) {
                    // Back edge u->v, trong đó v là tổ tiên
                    // đang GRAY trên stack: dựng v..u..v.
                    List<Integer> backward = new ArrayList<>();
                    int x = u;
                    backward.add(x);

                    while (x != v) {
                        x = parent[x];
                        if (x < 0) {
                            throw new IllegalStateException(
                                "broken DFS parent chain");
                        }
                        backward.add(x);
                    }
                    Collections.reverse(backward);
                    backward.add(v);

                    // Với chu trình, không cung cấp topo/finish
                    // order chưa hoàn thiện như một kết quả.
                    return new Result(
                        false, List.of(), List.of(),
                        List.copyOf(backward), discover, finish);
                }
                // color[v]==2: đã BLACK, không mở lại.
            }
        }

        ArrayList<Integer> order = new ArrayList<>(finished);
        Collections.reverse(order);
        return new Result(
            true, List.copyOf(order), List.copyOf(finished),
            List.of(), discover, finish);
    }

    // Kiểm tra tính hợp lệ, KHÔNG so với một order mẫu.
    static boolean validTopological(Graph g, List<Integer> order) {
        if (order == null || order.size() != g.n()) {
            return false;
        }

        int[] position = new int[g.n()];
        Arrays.fill(position, -1);
        for (int index = 0; index < order.size(); index++) {
            int u = order.get(index);
            if (u < 0 || u >= g.n() || position[u] != -1) {
                return false;
            }
            position[u] = index;
        }

        for (int u = 0; u < g.n(); u++) {
            for (int v : g.out().get(u)) {
                if (position[u] >= position[v]) {
                    return false;
                }
            }
        }
        return true;
    }

    // Kahn + min-priority queue. Một nghiệm khác có thể
    // hợp lệ và khác reverse finish order của DFS.
    static List<Integer> kahnMin(Graph g) {
        int n = g.n();
        int[] indegree = new int[n];
        for (int u = 0; u < n; u++) {
            for (int v : g.out().get(u)) {
                indegree[v]++;      // Đếm cả cạnh song song.
            }
        }

        PriorityQueue<Integer> ready = new PriorityQueue<>();
        for (int v = 0; v < n; v++) {
            if (indegree[v] == 0) {
                ready.add(v);
            }
        }

        ArrayList<Integer> order = new ArrayList<>(n);
        while (!ready.isEmpty()) {
            int u = ready.remove();
            order.add(u);
            for (int v : g.out().get(u)) {
                indegree[v]--;
                if (indegree[v] == 0) {
                    ready.add(v);
                }
            }
        }
        return order.size() == n
            ? List.copyOf(order) : List.of();
    }

    // Kiểm tra witness của một chu trình có hướng đơn.
    // Self-loop được biểu diễn bằng [u,u].
    static boolean validCycleWitness(Graph g, List<Integer> cycle) {
        if (cycle == null || cycle.size() < 2
                || !cycle.get(0).equals(
                    cycle.get(cycle.size() - 1))) {
            return false;
        }

        boolean[] seen = new boolean[g.n()];
        for (int i = 0; i + 1 < cycle.size(); i++) {
            int u = cycle.get(i), v = cycle.get(i + 1);
            if (u < 0 || v < 0 || u >= g.n() || v >= g.n()
                    || seen[u] || !g.out().get(u).contains(v)) {
                return false;
            }
            seen[u] = true;
        }
        return true;
    }

    // Oracle độc lập: duyệt hoán vị, chỉ dành cho n<=4.
    static boolean existsTopologicalByPermutations(Graph g) {
        int[] permutation = new int[g.n()];
        boolean[] used = new boolean[g.n()];
        return tryPermutation(g, permutation, used, 0);
    }

    static boolean tryPermutation(Graph g, int[] permutation,
                                  boolean[] used, int depth) {
        if (depth == g.n()) {
            ArrayList<Integer> order = new ArrayList<>(g.n());
            for (int v : permutation) {
                order.add(v);
            }
            return validTopological(g, order);
        }

        for (int v = 0; v < g.n(); v++) {
            if (used[v]) {
                continue;
            }
            used[v] = true;
            permutation[depth] = v;
            boolean found = tryPermutation(
                g, permutation, used, depth + 1);
            used[v] = false;
            if (found) {
                return true;
            }
        }
        return false;
    }

    // Thử n<=4: DFS vs Kahn vs brute-force hoán vị.
    static void verifySmallGraph(Graph g) {
        Result dfs = topologicalByDFS(g);
        List<Integer> kahn = kahnMin(g);
        boolean brute = existsTopologicalByPermutations(g);
        boolean kahnFound = kahn.size() == g.n();

        if (dfs.dag() != brute || kahnFound != brute) {
            throw new AssertionError("DAG classification differs");
        }

        if (brute) {
            if (!validTopological(g, dfs.order())
                    || !validTopological(g, kahn)
                    || dfs.finishOrder().size() != g.n()) {
                throw new AssertionError("bad topological order");
            }

            // Tính chất trung tâm: mọi cạnh u->v có f[u]>f[v].
            for (int u = 0; u < g.n(); u++) {
                for (int v : g.out().get(u)) {
                    if (dfs.finish()[u] <= dfs.finish()[v]) {
                        throw new AssertionError("finish-time proof");
                    }
                }
            }
        } else {
            if (!dfs.order().isEmpty()
                    || !validCycleWitness(g, dfs.cycle())) {
                throw new AssertionError("cycle witness is invalid");
            }
        }
    }

    // n=0:1, n=1:1, n=2:4, n=3:64, n=4:4096.
    static Counts verifyAllSmallDigraphs() {
        int checked = 0, dags = 0, cyclic = 0;
        for (int n = 0; n <= 4; n++) {
            List<int[]> possible = new ArrayList<>();
            for (int u = 0; u < n; u++) {
                for (int v = 0; v < n; v++) {
                    if (u != v) {
                        possible.add(new int[]{u, v});
                    }
                }
            }

            int graphs = 1 << possible.size();
            for (int bits = 0; bits < graphs; bits++) {
                ArrayList<int[]> selected = new ArrayList<>();
                for (int i = 0; i < possible.size(); i++) {
                    if ((bits & (1 << i)) != 0) {
                        selected.add(possible.get(i));
                    }
                }
                Graph g = fromEdges(
                    n, selected.toArray(new int[0][]));
                verifySmallGraph(g);
                checked++;
                if (topologicalByDFS(g).dag()) {
                    dags++;
                } else {
                    cyclic++;
                }
            }
        }
        return new Counts(checked, dags, cyclic);
    }

    public static void main(String[] args) {
        Graph sample = fromEdges(8, new int[][]{
            {0,2}, {0,3}, {1,3}, {1,4}, {2,5},
            {3,5}, {4,6}, {5,6}, {2,5}
        });
        Result r = topologicalByDFS(sample);
        if (!r.dag() || !validTopological(sample, r.order())) {
            throw new AssertionError("sample must be a DAG");
        }
        System.out.println("Sample finish order: "
                           + r.finishOrder());
        System.out.println("Sample topo by DFS: "
                           + r.order());
        System.out.println("Sample topo by Kahn: "
                           + kahnMin(sample));
        System.out.println("Sample DFS valid: "
                           + validTopological(sample, r.order()));
        System.out.println("Sample finish times: "
                           + Arrays.toString(r.finish()));

        Graph cyclic = fromEdges(4, new int[][]{
            {0,1}, {1,2}, {2,0}, {2,3}
        });
        Result ring = topologicalByDFS(cyclic);
        System.out.println("Cycle graph DAG: " + ring.dag());
        System.out.println("Cycle witness: " + ring.cycle());

        Result selfLoop = topologicalByDFS(
            fromEdges(2, new int[][]{{0,0}}));
        System.out.println("Self-loop witness: "
                           + selfLoop.cycle());

        Result isolated = topologicalByDFS(
            fromEdges(4, new int[0][]));
        System.out.println("Isolated topo: " + isolated.order());

        Result empty = topologicalByDFS(
            fromEdges(0, new int[0][]));
        System.out.println("Empty DAG: " + empty.dag());

        Counts counts = verifyAllSmallDigraphs();
        System.out.println(
            "Exhaustive directed graphs n<=4: "
            + counts.graphs() + " OK ("
            + counts.dags() + " DAG, "
            + counts.cyclic() + " cyclic)");
    }
}
```

### Biên dịch và chạy

Dùng **JDK 17 trở lên** và lưu đúng tên file public class:

```bash
javac -encoding UTF-8 TopoDFSFinishDemo.java
java TopoDFSFinishDemo
```

**Stdout dự kiến:**

```text
Sample finish order: [6, 5, 2, 3, 0, 4, 1, 7]
Sample topo by DFS: [7, 1, 4, 0, 3, 2, 5, 6]
Sample topo by Kahn: [0, 1, 2, 3, 4, 5, 6, 7]
Sample DFS valid: true
Sample finish times: [10, 14, 7, 9, 13, 6, 5, 16]
Cycle graph DAG: false
Cycle witness: [0, 1, 2, 0]
Self-loop witness: [0, 0]
Isolated topo: [3, 2, 1, 0]
Empty DAG: true
Exhaustive directed graphs n<=4: 4166 OK (573 DAG, 3593 cyclic)
```

### Phân tích từng thành phần của chương trình

**`Graph/fromEdges`:** Mọi cạnh `(u,v)` được thêm **chỉ theo chiều `u→v`**. Không tự thêm cạnh ngược như đồ thị vô hướng. Hàm tạo adjacency list mới và sort bản đó; không sửa `edges[][]` của caller. Cạnh trùng có thể lặp trong adjacency nhưng không làm sai DFS/Kahn.

**`Result`:** Khi `dag=true`, `order` là topo, `finishOrder` là thứ tự kết thúc DFS, `discover[]/finish[]` là vết thời gian hoàn chỉnh. Khi `dag=false`, chỉ `cycle` là kết quả ý nghĩa; hai danh sách order/finishOrder rỗng theo hợp đồng để tránh dùng nhầm bản không hoàn chỉnh. Mảng thời gian có thể chứa các ô chưa tính, không nên diễn giải nếu phát hiện chu trình.

**`Frame`:** Mỗi frame chứa đỉnh và chỉ số cạnh outgoing kế tiếp. Nó mô phỏng **trạng thái lời gọi DFS đệ quy**, cho phép xác định chính xác lúc một đỉnh kết thúc.

**`topologicalByDFS`:** Đỉnh WHITE trở thành GRAY trước khi push; khi xét xong adjacency trở thành BLACK và được thêm vào `finished`. Bắt gặp cạnh tới GRAY → dựng một chu trình bằng `parent[]`; không giả tạo topo từ đồ thị có chu trình.

**`validTopological`:** Chỉ cần xây mảng `position[]` rồi kiểm tra mỗi cạnh `u→v`. Bản thân cách kiểm tra **không phụ thuộc** thứ tự DFS, nên giúp phát hiện lỗi code sinh topo.

**`kahnMin`:** Dùng **indegree và priority queue**, khác hoàn toàn DFS finish time. Có nhiều thứ tự hợp lệ; chọn đỉnh có ID nhỏ nhất trong các đỉnh hiện indegree 0 cho thứ tự topo **nhỏ nhất theo từ điển**. Chi phí hàng đợi ưu tiên là thêm `log n` vào các thao tác đưa/lấy đỉnh.

**`validCycleWitness`:** Kiểm tra witness có ít nhất hai phần tử, khép về điểm đầu, mỗi cạnh đi đúng hướng, và không lặp đỉnh giữa đường (trừ việc lặp đầu ở cuối). Self-loop `[u,u]` được chấp nhận.

**`existsTopologicalByPermutations`:** Thử mọi hoán vị trong bài cực nhỏ; một hoán vị được chấp nhận nếu mọi cạnh đi trái sang phải. Vì không dựa trên DFS hay Kahn, đây là **oracle độc lập về sự tồn tại topo**, dù thời gian tăng theo `n!`.

**`verifyAllSmallDigraphs`:** Với `n` đỉnh không xét self-loop, có `n(n−1)` cặp đỉnh có hướng khác nhau có thể làm cạnh. Mỗi cạnh được chọn hoặc không, nên có `2^{n(n−1)}` đồ thị. Từ `n=0..4`:

```text
n=0 : 1 đồ thị
n=1 : 1 đồ thị
n=2 : 4 đồ thị
n=3 : 64 đồ thị
n=4 : 4096 đồ thị
Tổng: 4166 đồ thị

DAG: 573
Có chu trình: 3593
```

Mỗi đồ thị được kiểm tra đồng thời bởi ba cách. Với DAG, còn kiểm tra **`finish[u]>finish[v]` trên mọi cạnh**. Với đồ thị có chu trình, kiểm tra witness thật sự tạo thành chu trình có hướng. Những trường hợp **self-loop và cạnh song song** được kiểm tra trong ví dụ riêng, vì tập exhaustive nói trên chỉ chứa các cạnh giữa **hai đỉnh khác nhau**, và không có cạnh trùng.

### Độ tin cậy và giới hạn kiểm thử

Bộ test exhaustive 4.166 đồ thị nhỏ giúp bắt lỗi dấu so sánh finish, thiếu vòng ngoài, cập nhật màu sai, nhận nhầm cạnh tới BLACK là chu trình và sai đường parent của witness. Tuy nhiên:

- Không thể suy ra hiệu năng thực tế trên đồ thị có hàng triệu đỉnh từ test n≤4.
- Mã Java được thiết kế theo giới hạn tài nguyên đầu vào; không có cơ chế đọc từ stdin cho đồ thị khổng lồ.
- Tính đúng tổng quát đến từ chứng minh ở mục 5–6, còn kiểm thử xác nhận triển khai trên miền hữu hạn.
- Nếu bài yêu cầu topological order có tie-break riêng hoặc cần in kết quả bằng nhãn string, phải điều chỉnh chính sách chọn/sắp đỉnh mà không phá điều kiện topo.

## 11. Độ phức tạp và cách tối ưu bộ nhớ

Với `n=|V|`, `m=|E|` là số cạnh có hướng được lưu:

**DFS topo cơ bản (đã có adjacency list):**

- Khởi tạo màu, parent, thời gian: `O(n)`.
- Mỗi đỉnh được phát hiện và kết thúc đúng một lần: `O(n)`.
- Mỗi cạnh outgoing được xét đúng một lần: `O(m)`.
- Đảo finish order: `O(n)`.
- **Tổng `O(n+m)` thời gian**, **`O(n)` bộ nhớ phụ** cho màu/parent/stack/finish order và mảng thời gian, không tính adjacency list.

**Xây và sort danh sách kề để output xác định:**

```text
O(n+m) để tạo danh sách,
O(sum_v degreeOut(v) * log(max(1,degreeOut(v)))) để sort
```

Vì vậy chương trình mẫu có thêm overhead sắp adjacency; bước sort **không bắt buộc** cho tính đúng của topo, chỉ để output ổn định.

**Kahn:**

- Với queue FIFO: `O(n+m)` thời gian và `O(n)` bộ nhớ phụ.
- Với **min-priority queue**: thường `O(n+m+nlog n)` hoặc cận dễ dùng **`O((n+m)log n)`** khi đếm các thao tác ưu tiên theo số đỉnh; số lần push/remove đỉnh là `O(n)`, mỗi cạnh vẫn được xét đúng một lần. Việc duyệt cạnh và cập nhật indegree là `O(m)`, còn priority queue tổng `O(nlog n)`. Kahn với min-heap cho topo nhỏ nhất theo từ điển, không nhất thiết nhanh hơn DFS.

**Oracle hoán vị:**

```text
Tối đa n! hoán vị × O(n+m) để kiểm một hoán vị
```

Do vậy brute force chỉ nên dùng để kiểm thử **n rất nhỏ**, không phải thuật toán giải bài thực tế khi n lớn.

### Độ sâu stack

DFS đệ quy có thể sâu tới `n` trên đường đi dài `0→1→...→n−1` và gây `StackOverflowError` trong JVM. Phiên bản frame stack trên heap cũng dùng **`O(n)` bộ nhớ** nhưng không tiêu thụ call stack Java tỷ lệ với chiều sâu đồ thị.

Tuy nhiên, dùng `ArrayDeque<Frame>` vẫn tạo object Frame; nếu `n,m` cực lớn và RAM chặt, có thể tối ưu bằng hai mảng nguyên `stackVertex[]` và `stackNextNeighbor[]` hoặc cấu trúc CSR. Cần giữ nguyên semantics “kết thúc sau khi xét hết adjacency” khi tối ưu bộ nhớ.

## 12. Bẫy thường gặp và cách tự kiểm tra

**1. Nhầm thứ tự vào DFS với thứ tự kết thúc.** Cần ghi đỉnh khi **thoát DFS**, sau đó đảo. Ghi lúc phát hiện rồi đảo không đúng.

**2. Không đảo finish order.** Thứ tự kết thúc thường đặt đỉnh bị phụ thuộc ở trước; topo cần thứ tự **ngược lại**.

**3. Chạy duy nhất `dfs(0)`.** Đồ thị có thể có nhiều nhánh độc lập hoặc đỉnh cô lập. Duyệt vòng ngoài qua mọi `0..n−1`.

**4. Chỉ dùng `visited[]` rồi không kiểm tra chu trình.** Đảo finish order chỉ hợp lệ với DAG. Muốn phát hiện chu trình trong cùng lượt DFS, cần ba màu hoặc bộ trạng thái active stack tương đương.

**5. Gọi mọi cạnh tới visited là chu trình.** Một cạnh tới đỉnh BLACK trong đồ thị có hướng có thể là forward/cross edge hoàn toàn bình thường. Chỉ cạnh tới **GRAY** mới cho back edge gây chu trình.

**6. Đánh BLACK ngay khi push DFS frame.** Cần giữ GRAY tới khi xử lý hết hàng xóm; nếu không sẽ bỏ lỡ chu trình.

**7. Dùng stack các đỉnh nhưng kết thúc ngay khi pop.** Lúc đó các con có thể chưa xử lý xong. Dùng frame chỉ số hàng xóm hoặc sự kiện exit đúng nghĩa.

**8. Trả topo khi đồ thị chứa self-loop.** Cạnh `u→u` là chu trình; witness `[u,u]` đủ để bác bỏ topo.

**9. Tưởng hai cạnh song song tạo chu trình.** Hai bản sao `u→v` không tạo đường từ v về u; vẫn DAG nếu không có đường quay lại.

**10. Xây đồ thị có hướng thành vô hướng.** Tự thêm cạnh `v→u` sẽ tạo chu trình 2 đỉnh giả từ bất kỳ cạnh `u→v`, làm kết quả sai.

**11. Quên gán/reset state trước một lần giải đồ thị mới.** Không tái sử dụng màu/time từ input trước nếu chưa reset; trong code mẫu mỗi lời gọi topo tạo mảng mới.

**12. Kiểm thử bằng so mảng kết quả với một ví dụ duy nhất.** DAG có thể có nhiều topo hợp lệ. Hãy xây `position[]` và kiểm tra **mọi cạnh**; chỉ so đúng chuỗi nếu đề yêu cầu tie-break đó.

**13. Tưởng DFS đảo finish luôn ra topo nhỏ nhất từ điển.** Kết quả phụ thuộc thứ tự root và adjacency. Nếu đề yêu cầu nhỏ nhất từ điển, dùng min-priority queue của Kahn hoặc chứng minh chiến lược khác.

**14. Nhầm finish time với discover time.** Với cạnh `u→v` trong DAG, cần `finish[u]>finish[v]`, không nhất thiết `discover[u]<discover[v]` trên mọi cạnh do có cross edge.

**15. Không xác thực đầu mút cạnh.** Với `n=4`, chỉ số đỉnh hợp lệ là 0..3. Cạnh chứa 4 phải bị báo lỗi trước khi truy cập mảng.

**16. Không phân biệt `n=0` với cyclic.** Đồ thị rỗng có topo rỗng hợp lệ. Dùng cờ DAG hoặc so độ dài order với n.

**17. Truy vết chu trình sai chiều.** Chuỗi parent đi từ u ngược về v cần đảo rồi mới thêm v cuối; nếu không các cặp liên tiếp có thể không phải cạnh có hướng thực tế.

**18. Không tính cạnh song song đúng trong Kahn.** Tăng indegree cho mỗi cạnh lưu thì phải giảm cho mỗi cạnh lưu khi xử lý u.

**19. Áp logic màu directed cho đồ thị vô hướng mà quên cạnh về cha.** Trong đồ thị vô hướng lưu cạnh hai chiều, gặp cha GRAY là bình thường; không phải topo bài này.

**20. Đưa finish order chưa đầy đủ ra như topo khi vừa phát hiện cycle.** Phải báo thất bại và không tuyên bố có thứ tự hợp lệ.

## 13. Ứng dụng và biến thể cần lưu ý

### Lập lịch môn học hoặc công việc

Đồ thị dependency `u→v` biểu diễn `u` phải trước `v`. Nếu có một chu trình phụ thuộc, lịch trình không thể thực hiện tuần tự thỏa mọi ràng buộc. Một hệ thống thực tế nên hiển thị **witness chu trình** để người nhập dữ liệu biết những ràng buộc nào cần sửa.

### Quy hoạch động trên DAG

Giả sử có trạng thái `dp[v]` phụ thuộc các đỉnh `u` có cạnh `u→v`. Khi đã có một topo order, duyệt `v` **theo order** bảo đảm mọi predecessor đã được tính trước (nếu công thức chuyển đúng theo cạnh). Đây là cơ sở của bài đường ngắn nhất/dài nhất trên DAG.

Không nhất thiết dùng topo order đảo ngược cho mọi bài: nếu công thức `dp[u]` phụ thuộc các **successor `v`** qua cạnh `u→v`, có thể cần duyệt **reverse topo order**. Thứ tự phải theo **quan hệ phụ thuộc thực tế của trạng thái**, không theo tên thuật toán.

### Xác định sự tồn tại hay một thứ tự cụ thể

- Chỉ muốn biết có topo không: kiểm tra có chu trình (DFS ba màu hoặc Kahn có lấy đủ n đỉnh).
- Muốn một topo: trả DFS reverse finish hoặc Kahn.
- Muốn nhỏ nhất từ điển: Kahn min-heap.
- Muốn liệt kê **tất cả** topo: đó là bài toán khó hơn rất nhiều; cần quay lui chọn các đỉnh indegree 0 ở mỗi bước, và số kết quả có thể tăng giai thừa, ví dụ đồ thị không cạnh có `n!` topo.

### Duy nhất hay không duy nhất

Nếu trong quá trình Kahn có **nhiều hơn một đỉnh indegree 0** sẵn sàng ở một bước, ta có thể chọn một trong nhiều đỉnh, chứng tỏ có hơn một thứ tự tô-pô. Nếu **mọi bước chỉ có đúng một lựa chọn**, topo là duy nhất. Phát biểu này dựa trên quá trình loại đỉnh trong DAG, không phải trên cách DFS tình cờ trả một thứ tự ổn định.

### Tô-pô sau khi nén SCC

Nếu đồ thị có chu trình, chưa có topo trên **từng đỉnh**. Nhưng có thể tìm các **strongly connected components – SCC** bằng Tarjan/Kosaraju, rồi co mỗi SCC thành một siêu đỉnh. **Đồ thị ngưng tụ (condensation graph)** giữa các SCC luôn là DAG, nên có thể sắp topo các **nhóm SCC**, không phải các đỉnh ban đầu như thể chu trình đã biến mất.

## 14. Bài tập tự luyện

**Bài 1 — Kiểm tra topo bằng vị trí.** Với DAG ở mục 8, xây mảng `position[]` của `[7,1,4,0,3,2,5,6]` và xác minh mọi cạnh `u→v` có `position[u]<position[v]`.

**Bài 2 — Trace DFS.** Với `0→1, 0→2, 1→3, 2→3`, quét root tăng và adjacency tăng. Ghi lần lượt thời điểm vào/ra DFS, finish order và reverse finish order. Giải thích vì sao không thể chỉ đảo discovery order.

**Bài 3 — Đỉnh cô lập.** Với `n=5`, chỉ có cạnh `0→2,1→3`, hãy tìm một topo order đầy đủ có cả đỉnh 4. Nếu gọi một lần `dfs(0)`, thiếu những đỉnh nào?

**Bài 4 — Cycle witness.** Với cạnh `0→1,1→2,2→0`, mô phỏng ba màu và parent. Khi DFS ở 2 thấy 0 GRAY, dựng witness `[0,1,2,0]`.

**Bài 5 — Self-loop.** Tại sao graph chỉ có cạnh `(3,3)` đã vô topo, dù mọi đỉnh khác độc lập? Chu trình có thể in như thế nào?

**Bài 6 — Cạnh song song.** Với `n=3`, các cạnh `0→1` hai lần và `1→2` một lần, hãy chạy DFS topo và Kahn. Vì sao Kahn phải giảm indegree[1] đúng hai lần khi xử lý 0?

**Bài 7 — Hai topo khác nhau.** Cho hai đỉnh độc lập, không có cạnh. Liệt kê mọi topo. Giải thích vì sao việc DFS trả `[1,0]` còn Kahn min-heap trả `[0,1]` không tạo mâu thuẫn.

**Bài 8 — DAG versus cyclic.** Dùng phép kiểm “mỗi cạnh u→v có finish[u]>finish[v]” trong một DAG, rồi chỉ ra tại sao với chu trình sẽ tồn tại cạnh vi phạm quan hệ nếu vẫn cố dùng finish order chưa đảm bảo.

**Bài 9 — DFS lặp.** Cài lại DFS topo dùng hai loại sự kiện `ENTER` và `EXIT` trên stack thay vì frame vị trí hàng xóm. Bảo đảm một đỉnh được ghi finish **chỉ sau khi** các cạnh outgoing được xử lý và vẫn phát hiện cycle qua màu GRAY.

**Bài 10 — Kahn và thứ tự từ điển.** Viết Kahn bằng queue thường rồi bằng `PriorityQueue<Integer>`. So sánh output và độ phức tạp; chứng minh min-heap chọn topo nhỏ nhất theo từ điển.

**Bài 11 — Kiểm tra trên mọi đồ thị nhỏ.** Sinh tất cả đồ thị có hướng đơn n=4 không có self-loop (`2^{12}=4096` đồ thị). Dùng brute force mọi hoán vị để kiểm tra tồn tại topo, so với DFS ba màu.

**Bài 12 — Đồ thị trọng số.** Nếu cạnh `u→v` có trọng số `w(u,v)` và graph là DAG, hãy dùng topo order để tính đường dài nhất từ một nguồn. Vì sao thứ tự theo cạnh là điều kiện để DP có giá trị predecessor đúng?

**Bài 13 — Chu trình trong dependency.** Tạo danh sách môn học `A→B, B→C, C→A`. Viết cách hiển thị witness dễ hiểu cho người dùng; sau khi bỏ một ràng buộc làm graph thành DAG, chạy lại topo.

**Bài 14 — SCC.** Trên graph có chu trình, tìm SCC rồi nén thành DAG. Vì sao topo của DAG nén chỉ thứ tự **các nhóm**, không khẳng định mọi đỉnh của một SCC có thể được sắp theo tất cả cạnh nội bộ?

## 15. Checklist trước khi nộp lời giải

1. **Đã xác định hướng cạnh?** `u→v` có nghĩa u trước v, không được tự đảo/hợp nhất hướng.
2. **Đầu vào được xác thực?** `n≥0` và mọi cạnh có đỉnh thuộc 0..n−1?
3. **Đã duyệt toàn bộ n đỉnh?** Kể cả đỉnh cô lập và các nhánh không reachable từ root đầu?
4. **Màu được khởi tạo đúng?** 0/1/2 nhất quán với WHITE/GRAY/BLACK?
5. **Lúc ghi finish đúng?** Chỉ sau khi xử lý toàn bộ neighbor của đỉnh?
6. **Có phát hiện back edge?** Cạnh tới GRAY trong directed DFS báo một chu trình?
7. **Không nhầm cạnh tới BLACK?** Đỉnh đã kết thúc không cần duyệt lại và không tự chứng minh cycle.
8. **Kết quả khi cyclic?** Báo không có topo, không xuất finish order chưa hoàn chỉnh như kết quả hợp lệ?
9. **Thứ tự topo đúng?** Đảo finish order và xác minh `position[u]<position[v]` cho mọi cạnh?
10. **Thứ tự kết quả có bắt buộc cụ thể không?** Nếu đề chỉ cần một topo, không yêu cầu trùng mẫu; nếu nhỏ nhất từ điển, dùng min-heap Kahn.
11. **Có phụ thuộc vào thứ tự adjacency?** Sort nếu cần output xác định, nhưng đừng tính sort là phần bắt buộc của `O(V+E)` DFS cơ bản.
12. **Có nguy cơ StackOverflowError?** Với đường đi rất dài, cân nhắc DFS lặp bằng frame hoặc enter/exit events đúng nghĩa.
13. **Đã thử edge cases?** `n=0`, `n=1`, không cạnh, cạnh song song, self-loop, vòng 2 đỉnh, DAG nhiều nhánh, chu trình nằm ở thành phần khác?
14. **Tài nguyên và độ phức tạp đúng?** DFS `O(n+m)` sau khi có adjacency list, `O(n)` phụ; Kahn min-heap có thêm `O(nlog n)`.
15. **Có oracle kiểm thử?** Với graph nhỏ, brute force hoán vị + validTopological, Kahn indegree và witness cycle có đủ để phát hiện lỗi không?

**Tiêu chí hoàn thành:** Bạn có thể chứng minh DAG có thứ tự tô-pô, chạy DFS ba màu phủ tất cả đỉnh, ghi **thời điểm kết thúc** và đảo **postorder** đúng chỗ, phát hiện chu trình qua cạnh tới GRAY, viết DFS lặp có frame và phục dựng một cycle witness, phân biệt kết quả có thể không duy nhất và kiểm chứng Java 17+ bằng thuật toán độc lập.

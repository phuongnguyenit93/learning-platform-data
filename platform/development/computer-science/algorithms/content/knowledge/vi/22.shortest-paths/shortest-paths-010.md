# 0–1 BFS cho trọng số bằng không hoặc một

**0–1 BFS (zero-one breadth-first search)** là thuật toán tìm **đường đi ngắn nhất theo tổng trọng số** trên đồ thị có hướng hoặc vô hướng khi **mọi cạnh có trọng số đúng bằng 0 hoặc 1**. Thuật toán dùng **deque (hàng đợi hai đầu)** thay vì hàng đợi FIFO thuần túy hay hàng đợi ưu tiên tổng quát:

- Đi qua cạnh có trọng số **0**: đẩy đỉnh được cải thiện vào **đầu deque** (`addFirst`).
- Đi qua cạnh có trọng số **1**: đẩy đỉnh được cải thiện vào **cuối deque** (`addLast`).
- Chỉ cập nhật khi tìm thấy **tổng chi phí nhỏ hơn** khoảng cách đã biết, và bỏ qua các mục trong deque đã lỗi thời.

Nhờ hai loại trọng số đặc biệt, deque giữ thứ tự xử lý giống một dạng Dijkstra tối giản nhưng không cần heap. Với danh sách kề, 0–1 BFS có thời gian **O(V+E)** và bộ nhớ **O(V+E)** nếu tính cả danh sách kề và các mục trong deque; mảng khoảng cách/cha dùng O(V). Bài học thuộc nhóm **Đường đi ngắn nhất** của Computer Science Algorithms.

Bài này giải thích vì sao BFS thường sai khi có cạnh trọng số 0, chứng minh nguyên lý đưa đầu/đưa cuối, cách tránh cập nhật sai hoặc lặp vô hạn, phục dựng đường đi, 0–1 BFS nhiều nguồn, đồ thị có hướng/vô hướng, lưới có di chuyển miễn phí, trường hợp không tới được, đối chiếu với Dijkstra và Bellman–Ford, ví dụ Java 17+ chạy độc lập, kiểm thử và bài tập có lời giải.

## 1. Phát biểu bài toán

Cho đồ thị `G=(V,E)`. Mỗi cạnh/cung `e` có trọng số `w(e)∈{0,1}`. Với một đỉnh nguồn `s`, cần tìm khoảng cách:

`dist(s,v) = min_{P:s→v} Σ_{e∈P} w(e)`

Trong đó `P` là đường đi hợp lệ theo chiều các cạnh. **Đây là tổng trọng số, không phải số cạnh.** Đường đi có 10 cạnh trọng số 0 có tổng chi phí 0, còn đường đi chỉ có một cạnh trọng số 1 có tổng chi phí 1.

**Quy ước trong chương trình:**

- Các đỉnh đánh số `0..n-1`.
- Nguồn `s` có khoảng cách 0 tới chính nó.
- Đỉnh không thể tới được có `distance=-1` (thay cho vô cùng).
- Trọng số **chỉ được là 0 hoặc 1**; trọng số 2, -1, 100 hoặc một giá trị thập phân nằm ngoài phạm vi thuật toán này.
- Có thể có **cạnh song song** và **khuyên tự nối**; chúng không làm sai thuật toán.
- Bài toán có thể có hướng hoặc vô hướng; phải xây danh sách kề theo đúng đề.
- Mục tiêu chính là **khoảng cách có tổng trọng số nhỏ nhất** và có thể phục dựng **một đường đi đạt chi phí ấy**, không mặc định chọn ít cạnh nhất trong các đường đồng chi phí.

### Ví dụ trọng yếu: ít cạnh nhất khác ít chi phí nhất

Xét ba cung:

~~~text
0 -> 1     weight 1
0 -> 2     weight 0
2 -> 1     weight 0
~~~

Đường `0→1` chỉ có **1 cạnh** nhưng chi phí **1**. Đường `0→2→1` có **2 cạnh** nhưng chi phí **0+0=0**. Nếu đề yêu cầu tổng trọng số nhỏ nhất, đáp án từ 0 đến 1 là **0**, với đường đi qua 2.

Một BFS không trọng số thông thường có thể phát hiện đỉnh 1 trước qua cạnh trực tiếp và gán khoảng cách **1 cạnh**; kết quả ấy đúng cho **số cạnh**, nhưng **không đúng cho tổng trọng số**. Vì vậy không thể chỉ thay số 1 trong công thức BFS thành trọng số mà vẫn giữ quy tắc “phát hiện rồi không bao giờ xét lại”.

## 2. Vì sao deque đủ, không cần priority queue?

Trong Dijkstra tổng quát, ta chọn đỉnh đang có khoảng cách tạm thời nhỏ nhất bằng **hàng đợi ưu tiên**. Với trọng số chỉ 0/1, xét một đỉnh u được xử lý ở khoảng cách d:

- Qua cạnh 0, khoảng cách đề xuất cho v là **d**.
- Qua cạnh 1, khoảng cách đề xuất cho v là **d+1**.

Nếu các mục deque đang được lấy theo khoảng cách **không giảm**, những mục mới được phát hiện sẽ chỉ có mức **d** hoặc **d+1**. Vì thế:

- Mục khoảng cách d được đưa vào **đầu** để xử lý cùng lớp hiện tại.
- Mục khoảng cách d+1 được đưa vào **cuối** để xử lý sau các mục thuộc lớp d.

Bằng cách này, deque luôn hỗ trợ lấy ứng viên có khoảng cách nhỏ nhất trong số các ứng viên hợp lệ đang chờ mà không cần sắp xếp toàn bộ bằng heap.

### Quy tắc cập nhật (relaxation)

Cho `distance[u]=d` và cạnh `u→v` có trọng số w. Tính:

`candidate = distance[u] + w`

Nếu v chưa có khoảng cách hoặc `candidate < distance[v]`, cập nhật:

~~~text
distance[v] = candidate
parent[v] = u

if weight == 0:
    deque.addFirst(v)
else:
    deque.addLast(v)
~~~

Nếu `candidate==distance[v]`, **không cập nhật** trong bài chỉ cần một đường ngắn nhất. Nếu cứ cập nhật bằng dấu `<=`, các chu trình trọng số 0 có thể đẩy mục vào deque liên tục mà không cải thiện kết quả.

### Cần hiểu chính xác “deque không giảm”

Một cách cài đặt an toàn lưu **cặp (đỉnh, khoảng cách tại lúc đưa vào deque)** thay vì chỉ lưu số đỉnh. Ví dụ `Entry(vertex, snapshotDistance)`.

Nếu sau đó đỉnh ấy được tìm ra với khoảng cách nhỏ hơn, bản ghi cũ là **stale (lỗi thời)**. Khi lấy đầu deque:

~~~text
entry = deque.removeFirst()

if entry.snapshotDistance != distance[entry.vertex]:
    continue                 // Bỏ mục cũ.
~~~

Cách này cho phép cùng một đỉnh xuất hiện tạm thời nhiều lần trong deque mà vẫn giữ phép xử lý đúng. Những mục hợp lệ còn chờ được xử lý theo thứ tự mức khoảng cách không giảm; mục cũ bị bỏ mà không duyệt các cạnh của nó. Có thể triển khai bằng deque chỉ lưu đỉnh với một invariant phù hợp, nhưng cặp snapshot rõ ràng và dễ kiểm thử hơn.

**Không dùng mảng visited để khóa đỉnh ngay khi vừa enqueue.** Đỉnh có thể được phát hiện trước qua đường chi phí 1, rồi được cải thiện còn 0 qua một cạnh miễn phí. Nếu chặn mọi lần cập nhật sau phát hiện đầu tiên, đáp án sẽ sai.

## 3. Một ví dụ đầy đủ có đỉnh cô lập

Xét đồ thị **có hướng** 8 đỉnh và các cung sau, theo thứ tự được khai báo:

| Cung | Trọng số |
| --- | ---: |
| 0→1 | 1 |
| 0→2 | 0 |
| 2→1 | 0 |
| 1→3 | 1 |
| 2→4 | 1 |
| 4→3 | 0 |
| 3→5 | 0 |
| 4→5 | 1 |
| 5→6 | 1 |
| 1→6 | 1 |

Đỉnh **7 không có cạnh**. Nguồn là `s=0`.

### Bước khởi đầu

~~~text
distance = [0,-1,-1,-1,-1,-1,-1,-1]
deque = [(0,0)]
~~~

Lấy đỉnh 0:

- Xét `0→1` có w=1: `distance[1]=1`, đưa `(1,1)` vào cuối.
- Xét `0→2` có w=0: `distance[2]=0`, đưa `(2,0)` vào đầu.

Deque sau bước này:

~~~text
front [(2,0), (1,1)] back
~~~

Vì `(2,0)` ở đầu, thuật toán xử lý 2 trước 1 dù 1 được phát hiện sớm hơn.

Lấy đỉnh 2, xét:

- `2→1` có w=0, tạo `candidate=0` **nhỏ hơn** khoảng cách cũ `distance[1]=1`. Cập nhật `distance[1]=0`, `parent[1]=2` và thêm `(1,0)` vào đầu deque.
- `2→4` có w=1, gán `distance[4]=1`, đưa `(4,1)` vào cuối.

Lúc này deque chứa cả bản ghi mới `(1,0)` lẫn bản ghi cũ `(1,1)`. Khi `(1,1)` được lấy ra sau, kiểm tra snapshot phát hiện nó lỗi thời và **bỏ qua**.

Tiếp tục xử lý các cung còn lại sẽ cho:

~~~text
distance = [0,0,0,1,1,1,1,-1]
parent   = [-1,2,0,1,2,3,1,-1]
~~~

Đường ngắn nhất từ 0 đến 1 theo chi phí là `0→2→1`, có **2 cạnh** nhưng **chi phí 0**. Đường 0→2→1→6 có **3 cạnh**, tổng chi phí **1**. Đỉnh 7 không thể tới nên `distance[7]=-1` và đường đi trả về là `[]`.

### Bảng so sánh với BFS thường

| Đích | Khoảng cách theo tổng trọng số 0/1 | Ít cạnh nhất (bỏ qua trọng số) |
| ---: | ---: | ---: |
| 0 | 0 | 0 |
| 1 | 0 | 1 |
| 2 | 0 | 1 |
| 3 | 1 | 2 |
| 4 | 1 | 2 |
| 5 | 1 | 3 |
| 6 | 1 | 2 |
| 7 | Không thể tới | Không thể tới |

**Hai câu hỏi khác nhau, hai kết quả có thể khác nhau.** Đừng dùng kết quả BFS thường để kiểm chứng trực tiếp tổng chi phí tối ưu, trừ khi **tất cả trọng số đều bằng 1**.

## 4. Giả mã 0–1 BFS một nguồn

~~~text
ALGORITHM ZERO_ONE_BFS(graph, source)
    REQUIRE every edge weight is 0 or 1

    distance[v] <- INF for every vertex v
    parent[v] <- NONE for every vertex v

    distance[source] <- 0
    deque <- empty deque
    PUSH_FRONT(deque, (source, 0))

    WHILE deque is not empty DO
        (u, snapshot) <- POP_FRONT(deque)

        IF snapshot != distance[u] THEN
            CONTINUE
        END IF

        FOR EACH edge (u -> v, weight w) DO
            candidate <- distance[u] + w

            IF candidate < distance[v] THEN
                distance[v] <- candidate
                parent[v] <- u

                IF w == 0 THEN
                    PUSH_FRONT(deque, (v, candidate))
                ELSE
                    PUSH_BACK(deque, (v, candidate))
                END IF
            END IF
        END FOR
    END WHILE

    RETURN distance, parent
END ALGORITHM
~~~

**INF** biểu thị khoảng cách chưa biết. Trong Java ở mục 8, để tiện in kết quả, ta dùng **-1** là “chưa tới được” và kiểm tra riêng `old==-1` trước phép so sánh. Với trọng số 0/1 không âm, mọi khoảng cách hợp lệ đều không âm nên -1 không gây lẫn lộn.

Điều kiện cải thiện:

~~~text
old == -1 OR candidate < old
~~~

Nếu không cải thiện, không đưa thêm một mục deque; nếu bằng nhau, không sửa parent. Phương pháp này tìm **một** nghiệm ngắn nhất; nếu cần **tất cả đường đi ngắn nhất**, phải dùng thêm logic và chú ý chu trình 0.

### Có nên đánh dấu đã thăm khi nào?

BFS thường (mọi cạnh chi phí 1) có thể đánh dấu ngay khi enqueue, vì lần khám phá đầu đã là tối ưu. Nhưng **0–1 BFS không được khóa một đỉnh tại lần enqueue đầu**: đường `0→1` chi phí 1 và `0→2→1` chi phí 0 là phản ví dụ.

Có thể sử dụng trạng thái “đã chốt” khi **lấy ra theo thứ tự khoảng cách tối thiểu** đúng kiểu Dijkstra; khi đó cần bảo đảm invariant chốt và không làm sai quá trình relax. Ví dụ Java không cần `visited`: nó cập nhật khi giảm được khoảng cách và loại bản ghi stale.

## 5. Chứng minh đúng

### 5.1. Khoảng cách được gán luôn có đường đi thực

Ban đầu nguồn s có khoảng cách 0 ứng với đường đi rỗng. Mỗi lần relax từ đỉnh u theo cạnh `u→v` có trọng số w, nếu có một đường đi đến u với chi phí `distance[u]`, nối thêm cạnh sẽ tạo đường đến v với chi phí `distance[u]+w`. Vì vậy mọi giá trị hữu hạn `distance[v]` được gán đều là **chi phí của một đường đi hợp lệ**, không thể tự nhiên thấp hơn tối ưu thật.

### 5.2. Các mục hợp lệ được xử lý theo khoảng cách không giảm

Giả sử mục hợp lệ được lấy ở mức d. Vì mọi trọng số chỉ 0/1, các cập nhật từ đó có mức **d hoặc d+1**. Mục mức d đặt vào đầu deque, mục mức d+1 đặt vào cuối. Khi bắt đầu, deque chỉ có mức 0, nên bằng quy nạp deque duy trì thứ tự các mức không giảm cho các mục đang có hiệu lực; những bản ghi stale không thay đổi thứ tự xử lý của các mục hợp lệ vì chúng bị bỏ qua.

Chính tính chất này làm deque thay được heap: nó xử lý các mức chi phí theo thứ tự giống Dijkstra, trong đó các cạnh 0 không tăng mức và các cạnh 1 chỉ chuyển sang mức tiếp theo.

### 5.3. Khi một đỉnh được xử lý ở mức nhỏ nhất, không thể còn đường tốt hơn

Giả sử u được lấy khỏi deque ở khoảng cách d và tồn tại đường đi từ s đến u có chi phí `d'<d`. Trên đường ấy, xét lần đầu một đỉnh chưa được xử lý ở mức khoảng cách tối ưu; đỉnh đứng trước nó đã có khoảng cách tối ưu và được xử lý trước theo thứ tự không giảm, nên đã relax cạnh dẫn tới nó với chi phí không lớn hơn chi phí của tiền tố đường tối ưu. Lặp lập luận cho các tiền tố cho thấy u phải được phát hiện/được xử lý ở mức không quá `d'` trước khi đến d. Mâu thuẫn.

Do đó, cách lấy đầu deque cùng phép relax là hợp lệ: mọi đỉnh tới được cuối cùng nhận khoảng cách tối ưu.

### 5.4. Tính đầy đủ và kết thúc

Mỗi đường đi hợp lệ từ s có thể được xem như chuỗi cạnh. Từ nguồn, các cạnh đi ra được xét; mỗi lần cải thiện khoảng cách của một đỉnh thì đỉnh được đưa vào deque, vì thế các đường có thể mang lại cải thiện sẽ được xét tiếp. Đỉnh không tới được không bao giờ được relax và giữ -1.

Các trọng số không âm, khoảng cách hữu hạn được cập nhật **giảm nghiêm ngặt**, nên thuật toán không cập nhật lặp vô hạn chỉ vì chu trình trọng số 0. Trong 0–1 BFS, thứ tự deque theo mức làm mỗi đỉnh được xử lý ở mức tối ưu và các lần đề xuất cải thiện là hữu hạn; quá trình kết thúc.

### 5.5. Khi nào có thể dừng sớm?

Nếu chỉ cần **giá trị khoảng cách từ nguồn s tới đích t**, có thể dừng khi t được **lấy khỏi deque với snapshot còn đúng** (và trở thành mục có khoảng cách tối thiểu). Không được dừng đơn giản ngay **khi lần đầu enqueue t**, vì t có thể bị cải thiện từ 1 về 0 sau đó.

Nếu trả cả mảng khoảng cách của tất cả đỉnh hoặc cần phân tích mọi đường ngắn nhất, hãy chạy cho tới khi deque rỗng. Các mảng tại thời điểm dừng sớm có thể chứa khoảng cách **chưa tối ưu** cho đỉnh khác.

## 6. Độ phức tạp: vì sao O(V+E)?

Gọi `V` là số đỉnh và `E` là số cạnh/cung.

- Tạo danh sách kề: **O(V+E)** thời gian và bộ nhớ.
- Khởi tạo khoảng cách, cha: **O(V)**.
- Thêm/lấy đầu hay cuối `ArrayDeque`: **O(1) trung bình mỗi thao tác**.
- Với quy tắc relax đúng và thứ tự deque khi trọng số 0/1, mỗi đỉnh được xử lý hữu ích ở khoảng cách tối ưu; các mục cũ bị phát hiện stale, tổng số mục phát sinh chỉ tương ứng với các lần relax thành công, bị chặn bởi O(V+E).
- Mỗi danh sách kề chỉ cần được duyệt ở các lần xử lý hữu ích; tổng là **O(E)**.
- Tổng thuật toán: **O(V+E)** thời gian, **O(V+E)** bộ nhớ tính cả đồ thị và deque; riêng hai mảng `distance,parent` có **O(V)**.

Một cách nhìn khác: 0–1 BFS là **Dijkstra chuyên biệt** với tập trọng số {0,1}. Không phải dùng cây heap có chi phí O(log V) cho từng thao tác vì khoảng cách của các ứng viên chờ chỉ nằm ở hai lớp liên tiếp.

### Các cạm bẫy khi phân tích

**Không kết luận rằng queue luôn chứa đúng một mục cho mỗi đỉnh** trong phiên bản dùng snapshot. Một đỉnh có thể tồn tại tạm thời dưới hai mức chi phí; mục cũ sẽ bị bỏ. Do đó hãy tính cả chi phí deque chứ không mặc định nó luôn dài ≤V ở từng thời điểm.

**Đếm một trạng thái hay một đỉnh:** đồ thị có cạnh song song tạo nhiều phép xem cạnh, nhưng chỉ relax khi cải thiện nghiêm ngặt. Các cạnh có trọng số 0 nối thành chu trình không làm khoảng cách giảm âm.

**Không nhầm O(V+E) với O(V²):** nếu duyệt hàng xóm bằng ma trận kề V×V, chi phí đọc các vị trí có thể tăng thành O(V²). Với đồ thị thưa và danh sách kề, O(V+E) là lợi thế lớn.

**Bộ nhớ đỉnh lớn:** danh sách kề Java có nhiều danh sách và đối tượng; nếu V,E rất lớn có thể dùng CSR hoặc các mảng cạnh để tiết kiệm overhead, nhưng cách relax 0–1 BFS vẫn vậy.

## 7. Phục dựng đường đi ngắn nhất

Mỗi khi relax `u→v` thành công, đặt `parent[v]=u`. Sau khi thuật toán chạy xong, nếu `distance[t]>=0`, bắt đầu từ t rồi lần ngược parent cho tới -1; đảo dãy để có một đường từ nguồn tới t.

~~~text
FUNCTION PATH_TO(target)
    IF distance[target] == -1 THEN
        RETURN []
    END IF

    reversed <- []
    cur <- target
    WHILE cur != -1 DO
        APPEND cur TO reversed
        cur <- parent[cur]
    END WHILE

    REVERSE(reversed)
    RETURN reversed
END FUNCTION
~~~

Với ví dụ, `parent[1]=2` và `parent[2]=0` nên `pathTo(1)=[0,2,1]`. Chi phí đường này là `w(0,2)+w(2,1)=0`, khớp `distance[1]=0`.

**Trường hợp nguồn trùng đích:** `pathTo(s)=[s]`, có 1 đỉnh, **0 cạnh** và tổng chi phí 0. **Đỉnh không tới được:** trả `[]`. Đây là hai tình huống khác nhau.

**Nhiều đường tối ưu:** nếu có một đường chi phí 1 qua ba cạnh và đường chi phí 1 qua năm cạnh, hai đường đều tối ưu theo **chi phí**. Quy tắc cập nhật nghiêm ngặt `candidate<old` giữ đường xuất hiện trước; nó **không bảo đảm đường ít cạnh nhất trong các đường cùng chi phí** hoặc từ điển nhỏ nhất.

**Chu trình trọng số 0:** vẫn có thể tồn tại vô số *walks* chi phí tối ưu do đi vòng nhiều lần qua chu trình 0. 0–1 BFS với parent chỉ trả **một đường đi cụ thể**, không liệt kê mọi walk. Nếu đề yêu cầu đếm đường ngắn nhất, phải định nghĩa đường đơn, walk hoặc đếm đường theo cạnh và xem xét chu trình 0; cách cộng số đường của BFS không trọng số **không được áp dụng máy móc**.

## 8. Java 17+: 0–1 BFS chạy độc lập và kiểm thử

Chương trình sau dùng:

- `Graph` với danh sách kề, có lựa chọn **directed/undirected** và kiểm tra đầu mút cùng trọng số `0/1`.
- `Entry(vertex,snapshot)` để loại mục deque lỗi thời.
- `solve(graph,source)` trả khoảng cách và mảng cha; `pathTo` dựng một đường chi phí nhỏ nhất.
- `multiSourceDistances` khởi tạo nhiều nguồn cùng chi phí 0.
- `hopDistances` là BFS thường bỏ qua trọng số để cho thấy **mục tiêu ít cạnh nhất khác tổng chi phí nhỏ nhất**.
- `bellmanFordReference` sử dụng phép nới lỏng lặp n-1 vòng để kiểm tra khoảng cách độc lập trên đồ thị nhỏ.
- `crossCheck` dùng seed cố định tạo 200 đồ thị có thể có hướng/vô hướng, khuyên, cạnh song song, kiểm tra khoảng cách và tính hợp lệ của đường đi.

Tạo tệp **`ZeroOneBfsDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public class ZeroOneBfsDemo {
    record Edge(int to, int weight) {}
    record Entry(int vertex, int snapshot) {}

    record Result(int[] distance, int[] parent) {
        List<Integer> pathTo(int target) {
            if (target < 0 || target >= distance.length) {
                throw new IllegalArgumentException("Invalid target");
            }
            if (distance[target] == -1) {
                return List.of();
            }
            List<Integer> reversed = new ArrayList<>();
            for (int cur = target; cur != -1; cur = parent[cur]) {
                reversed.add(cur);
                if (reversed.size() > distance.length) {
                    throw new IllegalStateException("Parent cycle");
                }
            }
            Collections.reverse(reversed);
            return List.copyOf(reversed);
        }
    }

    static final class Graph {
        final List<List<Edge>> adjacency = new ArrayList<>();

        Graph(int n, int[][] arcs, boolean directed) {
            Objects.requireNonNull(arcs, "arcs");
            if (n < 0) {
                throw new IllegalArgumentException("Negative n");
            }
            for (int i = 0; i < n; i++) {
                adjacency.add(new ArrayList<>());
            }

            for (int[] arc : arcs) {
                if (arc == null || arc.length != 3) {
                    throw new IllegalArgumentException("Need {u,v,w}");
                }
                int u = arc[0], v = arc[1], w = arc[2];
                if (u < 0 || u >= n || v < 0 || v >= n ||
                        (w != 0 && w != 1)) {
                    throw new IllegalArgumentException(
                            "Invalid endpoint/weight");
                }
                adjacency.get(u).add(new Edge(v, w));
                if (!directed) {
                    adjacency.get(v).add(new Edge(u, w));
                }
            }
        }

        int size() {
            return adjacency.size();
        }
    }

    private static Result run(Graph g, int[] sources) {
        Objects.requireNonNull(g, "graph");
        Objects.requireNonNull(sources, "sources");

        int n = g.size();
        int[] distance = new int[n];
        int[] parent = new int[n];
        Arrays.fill(distance, -1);
        Arrays.fill(parent, -1);
        ArrayDeque<Entry> deque = new ArrayDeque<>();

        for (int s : sources) {
            if (s < 0 || s >= n) {
                throw new IllegalArgumentException("Invalid source");
            }
            if (distance[s] == -1) {
                distance[s] = 0;
                deque.addFirst(new Entry(s, 0));
            }
        }

        while (!deque.isEmpty()) {
            Entry entry = deque.removeFirst();
            int u = entry.vertex();

            if (entry.snapshot() != distance[u]) {
                continue; // Khoảng cách của mục cũ đã lỗi thời.
            }

            for (Edge edge : g.adjacency.get(u)) {
                int v = edge.to();
                int next = distance[u] + edge.weight();

                if (distance[v] == -1 || next < distance[v]) {
                    distance[v] = next;
                    parent[v] = u;

                    Entry candidate = new Entry(v, next);
                    if (edge.weight() == 0) {
                        deque.addFirst(candidate);
                    } else {
                        deque.addLast(candidate);
                    }
                }
            }
        }
        return new Result(distance, parent);
    }

    public static Result solve(Graph graph, int source) {
        return run(graph, new int[]{source});
    }

    public static int[] multiSourceDistances(
            Graph graph, int[] sources) {
        return run(graph, sources).distance();
    }

    // BFS thường: MỖI cạnh được tính là 1 bước.
    private static int[] hopDistances(Graph g, int source) {
        int n = g.size();
        if (source < 0 || source >= n) {
            throw new IllegalArgumentException("Invalid source");
        }
        int[] hops = new int[n];
        Arrays.fill(hops, -1);
        ArrayDeque<Integer> queue = new ArrayDeque<>();
        hops[source] = 0;
        queue.addLast(source);

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            for (Edge e : g.adjacency.get(u)) {
                if (hops[e.to()] == -1) {
                    hops[e.to()] = hops[u] + 1;
                    queue.addLast(e.to());
                }
            }
        }
        return hops;
    }

    // Oracle độc lập: n-1 vòng relax cạnh, dùng bản sao đồng thời.
    private static int[] bellmanFordReference(
            Graph g, int source) {
        int n = g.size();
        int[] dist = new int[n];
        Arrays.fill(dist, -1);
        dist[source] = 0;

        for (int round = 0; round < n - 1; round++) {
            int[] next = dist.clone();
            for (int u = 0; u < n; u++) {
                if (dist[u] == -1) {
                    continue;
                }
                for (Edge e : g.adjacency.get(u)) {
                    int candidate = dist[u] + e.weight();
                    if (next[e.to()] == -1 ||
                            candidate < next[e.to()]) {
                        next[e.to()] = candidate;
                    }
                }
            }
            dist = next;
        }
        return dist;
    }

    private static void verifyPaths(
            Graph g, int source, Result r) {
        for (int target = 0; target < g.size(); target++) {
            List<Integer> path = r.pathTo(target);
            int cost = r.distance()[target];

            if (cost == -1) {
                if (!path.isEmpty()) {
                    throw new AssertionError("Unreachable path");
                }
                continue;
            }
            if (path.isEmpty() || path.get(0) != source ||
                    path.get(path.size() - 1) != target ||
                    path.size() > g.size()) {
                throw new AssertionError("Wrong path endpoints");
            }

            int totalCost = 0;
            for (int i = 1; i < path.size(); i++) {
                int u = path.get(i - 1);
                int v = path.get(i);
                int expectedWeight =
                        r.distance()[v] - r.distance()[u];

                boolean foundEdge = false;
                for (Edge e : g.adjacency.get(u)) {
                    if (e.to() == v &&
                            e.weight() == expectedWeight) {
                        foundEdge = true;
                        totalCost += e.weight();
                        break;
                    }
                }
                if (!foundEdge) {
                    throw new AssertionError("Invalid parent edge");
                }
            }

            if (totalCost != cost) {
                throw new AssertionError("Wrong path cost");
            }
        }
    }

    private static void crossCheck() {
        Random random = new Random(2026L);

        for (int test = 0; test < 200; test++) {
            int n = 1 + random.nextInt(8);
            boolean directed = random.nextBoolean();
            int m = random.nextInt(2 * n * n + 1);
            int[][] arcs = new int[m][3];

            for (int i = 0; i < m; i++) {
                arcs[i][0] = random.nextInt(n);
                arcs[i][1] = random.nextInt(n);
                arcs[i][2] = random.nextInt(2);
            }

            Graph g = new Graph(n, arcs, directed);
            int source = random.nextInt(n);
            Result found = solve(g, source);
            int[] expected = bellmanFordReference(g, source);

            if (!Arrays.equals(found.distance(), expected)) {
                throw new AssertionError(
                        "Distance mismatch at test " + test);
            }
            verifyPaths(g, source, found);

            int source2 = random.nextInt(n);
            int[] multiple = multiSourceDistances(
                    g, new int[]{source, source2, source});
            int[] fromSecond = bellmanFordReference(g, source2);

            for (int v = 0; v < n; v++) {
                int x = expected[v], y = fromSecond[v];
                int best = x < 0 ? y : (y < 0 ? x : Math.min(x, y));
                if (multiple[v] != best) {
                    throw new AssertionError(
                            "Multi-source mismatch at test " + test);
                }
            }
        }
        System.out.println("crossCheck=PASS (200 graphs)");
    }

    public static void main(String[] args) {
        Graph directed = new Graph(8, new int[][]{
            {0,1,1}, {0,2,0}, {2,1,0}, {1,3,1},
            {2,4,1}, {4,3,0}, {3,5,0}, {4,5,1},
            {5,6,1}, {1,6,1}
        }, true);

        Result fromZero = solve(directed, 0);
        System.out.println("mainDist=" +
                Arrays.toString(fromZero.distance()));
        System.out.println("mainPath1=" + fromZero.pathTo(1));
        System.out.println("mainPath6=" + fromZero.pathTo(6));
        System.out.println("mainPath7=" + fromZero.pathTo(7));
        System.out.println("mainMulti=" +
                Arrays.toString(multiSourceDistances(
                        directed, new int[]{0,4})));
        System.out.println("fewestEdgesTo1=" +
                hopDistances(directed, 0)[1]);
        System.out.println("zeroOneCostTo1=" +
                fromZero.distance()[1]);

        Graph undirected = new Graph(5, new int[][]{
            {0,1,1}, {1,2,0}, {2,3,0},
            {3,4,1}, {0,4,1}
        }, false);
        Result undirectedResult = solve(undirected, 0);
        System.out.println("undirectedDist=" +
                Arrays.toString(undirectedResult.distance()));
        System.out.println("undirectedPath3=" +
                undirectedResult.pathTo(3));

        Graph loops = new Graph(3, new int[][]{
            {0,0,0}, {0,1,1}, {0,1,0},
            {1,2,0}, {2,1,0}
        }, true);
        Result loopResult = solve(loops, 0);
        System.out.println("loopsAndParallelDist=" +
                Arrays.toString(loopResult.distance()));
        System.out.println("loopsAndParallelPath2=" +
                loopResult.pathTo(2));

        System.out.println("reverseFrom6To0=" +
                solve(directed, 6).distance()[0]);
        System.out.println("emptyGraphSize=" +
                new Graph(0, new int[0][3], true).size());

        crossCheck();
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac ZeroOneBfsDemo.java
java ZeroOneBfsDemo
~~~

**Đầu ra xác định:**

~~~text
mainDist=[0, 0, 0, 1, 1, 1, 1, -1]
mainPath1=[0, 2, 1]
mainPath6=[0, 2, 1, 6]
mainPath7=[]
mainMulti=[0, 0, 0, 0, 0, 0, 1, -1]
fewestEdgesTo1=1
zeroOneCostTo1=0
undirectedDist=[0, 1, 1, 1, 1]
undirectedPath3=[0, 1, 2, 3]
loopsAndParallelDist=[0, 0, 0]
loopsAndParallelPath2=[0, 1, 2]
reverseFrom6To0=-1
emptyGraphSize=0
crossCheck=PASS (200 graphs)
~~~

### Giải thích kết quả Java

**`mainDist`:** 0 đến 1 có chi phí 0 qua hai cạnh miễn phí `0→2→1`. Các đỉnh 3,4,5,6 có chi phí nhỏ nhất là 1. Đỉnh 7 cô lập, do đó -1.

**`mainPath6`:** `0→2→1→6` có các trọng số `0+0+1=1`; đường đi hợp lệ và đạt `distance[6]=1`.

**`mainMulti`:** chọn các nguồn 0 và 4. Vì `4→3` có trọng số 0 và `3→5` có trọng số 0, các đỉnh 3 và 5 đạt khoảng cách 0 tới nguồn gần nhất; đỉnh 6 vẫn cần 1.

**`fewestEdgesTo1=1` vs `zeroOneCostTo1=0`:** cùng một đồ thị nhưng hai mục tiêu khác nhau, đúng như ví dụ đầu bài.

**`undirectedDist`:** danh sách cạnh vô hướng được thêm ở **hai chiều**, nên kết quả khoảng cách từ 0 tới tất cả đỉnh là `[0,1,1,1,1]`. Đường `0→1→2→3` dùng 3 cạnh nhưng chi phí chỉ 1.

**`loopsAndParallelDist`:** khuyên 0→0 trọng số 0 và cung 2→1 trọng số 0 tạo chu trình miễn phí; không được đưa vào deque mãi do chỉ cập nhật khi `candidate<old`. Hai cung song song 0→1 có trọng số 1 và 0; cạnh 0 giúp giảm khoảng cách của 1 xuống 0.

**`reverseFrom6To0=-1`:** đồ thị có hướng, từ 6 không có đường quay về 0.

**`crossCheck`:** 200 đồ thị nhỏ dùng seed cố định, có thể có khuyên và cạnh song song; chương trình so khoảng cách một nguồn với Bellman–Ford tham chiếu, kiểm tra các cạnh của đường `parent` và chi phí đường, rồi so kết quả multi-source với min của hai lần Bellman–Ford. Nếu sai, chương trình ném `AssertionError` trước khi in PASS.

### Những giới hạn triển khai

Đồ thị n=0 có thể tạo và in kích thước 0, nhưng **không thể gọi `solve(graph,0)`** vì không có đỉnh nguồn hợp lệ. Hàm `multiSourceDistances` nhận mảng nguồn rỗng và trả tất cả -1; với đồ thị rỗng và nguồn rỗng, trả mảng rỗng.

Mọi trọng số phải đúng 0/1. Constructor cố ý ném `IllegalArgumentException` khi có đầu mút ngoài phạm vi hoặc trọng số không hợp lệ; không âm thầm sửa 2 thành 1 hay -1 thành 0.

## 9. Vì sao oracle Bellman–Ford dùng n−1 vòng là đủ?

Trên đồ thị có **trọng số không âm**, bất kỳ đường đi ngắn nhất nào cũng có thể thay bằng một **đường đi đơn** (không lặp đỉnh) mà **không tăng chi phí**: nếu có chu trình, bỏ chu trình với tổng trọng số ≥0 sẽ không tệ hơn. Một đường đi đơn có tối đa **n−1 cạnh**.

Hàm tham chiếu dùng một mảng trước vòng và một bản sao cập nhật đồng thời:

`d_next[v] = min(d_previous[v], d_previous[u]+w(u,v))`

cho các cạnh `u→v`. Sau vòng thứ k, các chi phí đúng cho các đường dùng **không quá k cạnh**; n-1 vòng đủ cho tối ưu. Trong ví dụ có trọng số 0, nếu có đường đi chu trình 0 cho cùng chi phí, vẫn tồn tại đường đơn không tệ hơn, nên lập luận còn đúng.

Đây là **oracle kiểm thử** với độ phức tạp có thể O(V(V+E)), chậm hơn 0–1 BFS. Việc hai thuật toán đồng ý ở 200 đồ thị là tín hiệu tốt về triển khai; **chứng minh tính đúng** vẫn dựa vào invariant deque và relaxation.

## 10. 0–1 BFS nhiều nguồn

Nếu cần khoảng cách từ **nguồn gần nhất** trong một tập S, không phải chạy BFS riêng cho từng nguồn rồi cộng kết quả. Khởi tạo **tất cả nguồn có distance 0** và đưa chúng vào deque trước khi relax:

~~~text
distance[v] <- INF for every vertex
deque <- empty

FOR s IN sources:
    IF distance[s] == INF:
        distance[s] <- 0
        PUSH_FRONT(deque,(s,0))
    END IF

WHILE deque not empty:
    apply usual zero-one BFS relaxation
~~~

Vì tất cả nguồn bắt đầu ở mức 0, kết quả là:

`distance[v]=min_{s∈S} dist(s,v)`

Thứ tự đưa các nguồn vào deque không làm thay đổi giá trị khoảng cách nhỏ nhất; nó có thể thay đổi đường đi được chọn khi hòa.

**Nguồn trùng:** chỉ đưa một lần. **Tập nguồn rỗng:** không có đỉnh nào được phát hiện, mọi khoảng cách là -1. **Nguồn ngoài phạm vi:** báo lỗi đầu vào.

Nếu có k nguồn, khởi tạo tốn O(k), phần duyệt vẫn O(V+E). Nhiều nguồn giúp tiết kiệm khi cần khoảng cách tới nguồn gần nhất trên cùng một đồ thị.

**Khác biệt giữa “một đường từ nguồn bất kỳ” và “đi qua mọi nguồn”:** multi-source giải câu hỏi **min trên các nguồn**, không tìm đường phải đi qua hết các nguồn.

## 11. Áp dụng trên lưới, mê cung và chuyển trạng thái

Nhiều bài toán lưới có hai kiểu di chuyển:

- Đi sang ô kề phải trả **1** đơn vị.
- Di chuyển theo một loại đường đặc biệt được **miễn phí (0)**, ví dụ đi theo băng chuyền, cổng dịch chuyển có phí 0, hoặc dùng thao tác đảo hướng không mất điểm.

Mỗi **ô hoặc trạng thái** là một đỉnh, mỗi thao tác hợp lệ sinh một cạnh có trọng số 0 hoặc 1. Chạy 0–1 BFS từ trạng thái bắt đầu để tìm tổng chi phí ít nhất.

Ví dụ trên lưới có R hàng, C cột, nếu chỉ đi bốn hướng:

~~~text
dr = [-1, 1, 0, 0]
dc = [0, 0, -1, 1]

For each state (r,c):
    For k from 0 to 3:
        nr = r + dr[k]
        nc = c + dc[k]
        If (nr,nc) inside grid and not blocked:
            weight = 0 or 1 according to move rule
            relax((r,c) -> (nr,nc), weight)
~~~

Nếu có hướng quay, chìa khóa hoặc số lần dùng kỹ năng miễn phí, **trạng thái có thể phải là `(r,c,direction,mask,...)`**, không chỉ tọa độ ô. Hai lần đứng trên cùng ô nhưng khác chìa khóa có thể có khả năng tiếp tục khác nhau; gộp nhầm chúng thành một đỉnh sẽ sai.

### Ví dụ chuyển cạnh đặc biệt

Ở một trò chơi, di chuyển qua cửa bình thường tốn 1, còn di chuyển theo “đường trượt” tốn 0. Một lộ trình qua nhiều cửa trượt có thể cần nhiều bước hơn nhưng tổng chi phí thấp hơn đường đi ngắn về số cạnh. Đó là bài toán 0–1 BFS đúng nghĩa, không phải BFS thường.

Nếu mỗi thao tác có chi phí **0,1,2** hoặc lớn hơn, không dùng 0–1 BFS trực tiếp: cần Dijkstra hoặc kỹ thuật phù hợp khác. Nếu “miễn phí” thực chất sử dụng một phiếu giới hạn số lần, hãy đưa số phiếu còn lại vào trạng thái hoặc mô hình đúng điều kiện tiêu thụ tài nguyên.

## 12. So sánh 0–1 BFS, BFS thường, Dijkstra và các biến thể

| Đặc điểm | BFS thường | 0–1 BFS | Dijkstra với heap |
| --- | --- | --- | --- |
| Trọng số cạnh để tối ưu tổng chi phí | Tất cả =1 | Chỉ {0,1} | Không âm tổng quát |
| Cấu trúc lấy đỉnh | FIFO queue | Deque hai đầu | Priority queue |
| Quy tắc đưa vào | Cuối queue | 0→đầu, 1→cuối | Theo khoảng cách tạm thời |
| Được relax cải thiện đỉnh đã phát hiện? | Không cần nếu chỉ cạnh 1 | **Có** | Có nếu tìm đường tốt hơn |
| Chi phí điển hình bằng danh sách kề | O(V+E) | O(V+E) | O((V+E)log V) |
| Phục dựng đường | Parent | Parent | Parent |
| Khi dễ dùng sai | Áp dụng cho cạnh 0 | Áp dụng cho trọng số khác 0/1 | Dùng khi có trọng số âm |

**Dijkstra** là lựa chọn đúng cho trọng số bất kỳ **không âm**, chẳng hạn 0,1,5,100. Nó cũng giải được trường hợp 0/1 nhưng thường tốn heap không cần thiết.

**Bellman–Ford** xử lý được cạnh trọng số âm nếu không có chu trình âm làm khoảng cách không bị chặn dưới; có chi phí cao hơn. 0–1 BFS không dành cho trọng số âm.

**Dial's algorithm / bucket shortest paths** tổng quát hóa một phần ý tưởng xử lý theo lớp cho các trọng số nguyên nhỏ không âm. Nhưng với bài chỉ có hai mức 0/1, deque là cấu trúc rất đơn giản.

### Phản ví dụ khi có trọng số 2

~~~text
s -> t       weight 2
s -> a -> t  weights 1 and 0
~~~

Đường qua a có tổng 1, tốt hơn cạnh trực tiếp có tổng 2. Nếu coi trọng số 2 như 1 và đưa nó vào cuối deque theo quy tắc 0/1, thuật toán **không còn bảo đảm thứ tự deque đúng**. Không được “ép” 2 thành 1 chỉ để tái sử dụng 0–1 BFS.

## 13. Những lỗi thường gặp

1. **Dùng BFS thường** và đánh dấu đỉnh khi enqueue khi có cạnh trọng số 0.
2. **Dùng stack LIFO** thay deque, phá thứ tự xử lý theo mức chi phí.
3. **Cho cả cạnh 0 và cạnh 1 vào cuối deque**, bỏ mất ưu tiên của cạnh 0.
4. **Cho cả hai vào đầu deque**, xử lý sai thứ tự các mức khác nhau.
5. **Đưa đỉnh vào deque dù không có cải thiện**, làm nhiều công việc không cần thiết.
6. **Dùng điều kiện `candidate<=distance[v]`** và thêm lại khi bằng nhau, dễ lặp vô hạn trong chu trình 0.
7. **Khóa đỉnh tại lần phát hiện đầu**, ngăn cập nhật từ 1 xuống 0.
8. **Không bỏ stale entry** trong cài đặt dùng snapshot, làm duyệt cạnh thừa hoặc khó chứng minh giới hạn.
9. **Nhầm ít cạnh nhất với tổng trọng số nhỏ nhất**; có thể trả đường nhiều cạnh nhưng chi phí tốt hơn.
10. **Nhầm 0–1 BFS với BFS hai nguồn**; tên 0–1 nói về **trọng số**, không phải số nguồn.
11. **Quên đặt khoảng cách nguồn = 0**, khiến không có phép relax đúng.
12. **Dùng -1 làm khoảng cách thật rồi cộng trọng số**, không phân biệt sentinel chưa tới.
13. **Nhầm đỉnh không tới (-1) với đỉnh có chi phí 0**, nhất là khi có nhiều cạnh 0.
14. **Cho rằng mọi cạnh trọng số 0 làm toàn bộ đồ thị có chi phí 0**, dù có những vùng chỉ qua cạnh 1 mới tới được.
15. **Áp dụng thuật toán cho trọng số âm hoặc ≥2** mà không thay cấu trúc/tính đúng.
16. **Tạo đồ thị vô hướng nhưng chỉ thêm một chiều**, khiến kết quả không khớp đề.
17. **Tự thêm cạnh ngược trong đồ thị có hướng**, tạo đường không tồn tại.
18. **Không kiểm tra ID đỉnh/trọng số trong đầu vào**, gây truy cập sai hoặc giải bài khác.
19. **Dừng ngay khi thấy đích lần đầu**, dù còn đường miễn phí có thể cải thiện.
20. **Không đảo chuỗi parent** khi phục dựng đường đi từ đích về nguồn.
21. **Trả đường nguồn→nguồn là danh sách rỗng**, nhầm với đỉnh không tới.
22. **Giả định đường ít cạnh nhất trong các đường có chi phí bằng nhau**, dù không có tie-break.
23. **Đếm số đường ngắn nhất bằng parent duy nhất**, bỏ sót những đường đồng chi phí.
24. **Đếm walk trên chu trình 0 mà không xác định rõ nghĩa**, có thể có vô hạn walk đồng chi phí.
25. **Đọc ma trận kề nhưng tuyên bố tự động có O(V+E)**, bỏ qua chi phí quét ma trận.
26. **Chạy BFS riêng từng nguồn khi chỉ cần nguồn gần nhất**, bỏ qua multi-source deque.
27. **Cho rằng PriorityQueue bắt buộc** trong mọi bài shortest path không âm; 0–1 BFS có thể nhanh hơn cho đúng tập trọng số.
28. **Không kiểm thử cạnh song song/khuyên/cạnh 0**, dẫn đến lỗi xuất hiện ở dữ liệu thực.
29. **Nhầm chi phí thuật toán với số lần push vào deque** và kết luận cứ trùng đỉnh là sai.
30. **Bỏ qua kiểm tra đường đi trả về có các cạnh thực và đúng tổng trọng số**, chỉ so mảng distance chưa đủ.

## 14. Các trường hợp biên và kiểm thử

| Đầu vào | Điều mong đợi |
| --- | --- |
| Chỉ một đỉnh, không cạnh | Khoảng cách nguồn tới chính nó bằng 0, `pathTo=[source]`. |
| Đỉnh không thể tới | Khoảng cách -1 và đường đi `[]`. |
| Toàn cạnh trọng số 1 | Trùng khoảng cách BFS thường theo số cạnh. |
| Toàn cạnh trọng số 0 trong vùng tới được | Mọi đỉnh trong vùng ấy có chi phí 0. |
| Cạnh trực tiếp 1 vs hai cạnh 0+0 | Chọn đường 0+0 dù nhiều cạnh hơn. |
| Hai cạnh song song trọng số 1 và 0 | Đường chi phí 0 tốt hơn. |
| Khuyên trọng số 0 | Không làm giảm dưới 0, không lặp vô hạn. |
| Chu trình trọng số 0 | Không cập nhật khi bằng, thuật toán kết thúc. |
| Đồ thị có hướng một chiều | Không tự đi ngược cung. |
| Đồ thị vô hướng | Phải thêm mỗi cạnh ở hai phía. |
| Nguồn trùng trong multi-source | Chỉ khởi tạo một lần cho mỗi đỉnh. |
| Danh sách nguồn rỗng | Toàn bộ khoảng cách -1. |
| Đồ thị n=0, nguồn rỗng | Trả mảng rỗng theo API multi-source. |
| Đồ thị n=0, nguồn 0 | Báo lỗi đầu vào vì không tồn tại đỉnh 0. |
| Trọng số 2 hoặc -1 | Từ chối tại khởi tạo đồ thị. |
| Nhiều đường đồng chi phí | Khoảng cách đúng; parent chỉ ghi một đường. |

**Đối chiếu độc lập:** với n nhỏ, dùng thuật toán nới lỏng n-1 vòng như Bellman–Ford để tính khoảng cách chi phí tối ưu, so với 0–1 BFS ở từng đỉnh. Cần kiểm tra cả **các đường parent**, tổng trọng số, nguồn/đích, khả năng tới và multi-source. Chương trình Java thực hiện đúng các nhóm kiểm tra này trên 200 đồ thị ngẫu nhiên tái lập.

## 15. Bài tập có lời giải

**Bài 1.** Cung `0→1` trọng số 1, `0→2` trọng số 0, `2→1` trọng số 0. Tổng chi phí nhỏ nhất từ 0 đến 1? **Lời giải:** 0 qua `0→2→1`, dù dùng hai cạnh.

**Bài 2.** Một đường có 5 cạnh đều trọng số 0. Chi phí? **Lời giải:** 0; số cạnh vẫn là 5.

**Bài 3.** Khi relax cạnh trọng số 0 thành công, đưa đỉnh mới vào đầu hay cuối deque? **Lời giải:** đầu deque vì khoảng cách đề xuất không tăng.

**Bài 4.** Khi relax cạnh trọng số 1 thành công? **Lời giải:** cuối deque vì khoảng cách tăng một mức.

**Bài 5.** Đỉnh 1 được phát hiện lần đầu với chi phí 1, sau đó có đường chi phí 0. Có được cập nhật? **Lời giải:** phải cập nhật 0; đánh dấu visited khóa ngay lần đầu sẽ sai.

**Bài 6.** Nếu một phép relax cho chi phí đúng bằng khoảng cách hiện tại, có enqueue không? **Lời giải:** không trong thuật toán chỉ tìm một đường ngắn nhất; dùng dấu `<` nghiêm ngặt, tránh lặp chu trình 0.

**Bài 7.** Vì sao mục cũ có snapshot 1 của đỉnh đã giảm xuống 0 cần bỏ? **Lời giải:** nó không còn biểu diễn khoảng cách hiện tại; xử lý lại chỉ gây dư thừa, invariant xử lý theo mức trở nên khó theo dõi.

**Bài 8.** Với đồ thị mẫu, mảng khoảng cách từ 0? **Lời giải:** `[0,0,0,1,1,1,1,-1]`.

**Bài 9.** Với đồ thị mẫu, đường từ 0 đến 6 theo parent có chi phí bao nhiêu? **Lời giải:** `0→2→1→6` có trọng số 0+0+1=1.

**Bài 10.** Đỉnh 7 cô lập có khoảng cách bao nhiêu? **Lời giải:** -1 theo quy ước không thể tới.

**Bài 11.** Trong đồ thị mẫu, BFS thường tính ít cạnh nhất từ 0 tới 1 bằng mấy? **Lời giải:** 1 nhờ cạnh trực tiếp, khác chi phí tối ưu 0 theo 0–1 BFS.

**Bài 12.** Một khuyên `u→u` có trọng số 0 có làm thuật toán chạy mãi không? **Lời giải:** không; chi phí đề xuất bằng chi phí hiện tại, không đạt điều kiện cải thiện nghiêm ngặt.

**Bài 13.** Với mọi cạnh đều trọng số 1, 0–1 BFS có trả khoảng cách như BFS thường không? **Lời giải:** có, vì tổng trọng số bằng số cạnh.

**Bài 14.** Nếu trọng số chỉ là 0 và 2, có áp dụng code 0–1 BFS nguyên xi không? **Lời giải:** không theo đặc tả. Cần mô hình/thuật toán đúng như Dijkstra; không tự ép 2 thành 1.

**Bài 15.** Tại sao `pathTo(source)` chứa một đỉnh, không rỗng? **Lời giải:** đường đi rỗng cạnh từ nguồn đến chính nó vẫn có đỉnh nguồn và chi phí 0.

**Bài 16.** Có thể dừng ngay khi enqueue đích t lần đầu không? **Lời giải:** không; t có thể còn được cải thiện qua đường trọng số 0. Dừng an toàn khi lấy mục hợp lệ có khoảng cách tối thiểu của t.

**Bài 17.** Với hai nguồn s1,s2, khởi tạo khoảng cách hai nguồn? **Lời giải:** cùng bằng 0 rồi chạy một lượt 0–1 BFS; kết quả là min khoảng cách tới một trong hai nguồn theo **chiều đi từ nguồn tới đích**.

**Bài 18.** Đồ thị vô hướng có cạnh `(0,1,w=0)`. Khoảng cách từ 1 đến 0? **Lời giải:** 0 vì cạnh được đi cả hai chiều, không cần cạnh ngược riêng trong input.

**Bài 19.** Đồ thị có hướng chỉ có `0→1` trọng số 0. Khoảng cách từ 1 đến 0? **Lời giải:** -1 nếu không còn cung khác đưa về 0.

**Bài 20.** Tại sao 0–1 BFS có thể O(V+E) trong khi Dijkstra heap thường O((V+E)logV)? **Lời giải:** với trọng số 0/1, các mức ứng viên chờ chỉ lệch một, deque đủ duy trì thứ tự không giảm mà không cần heap.

**Bài 21.** Nếu bài yêu cầu đường ít cạnh nhất trong số các đường có tổng chi phí tối ưu, chỉ lưu parent theo lần cải thiện chi phí có đủ không? **Lời giải:** không mặc nhiên; cần thêm tiêu chí phụ, chẳng hạn tối ưu cặp (chi phí, số cạnh) bằng thuật toán/mô hình phù hợp.

**Bài 22.** Vì sao khi muốn đếm mọi walk có chi phí nhỏ nhất trên đồ thị có chu trình 0 phải cẩn thận? **Lời giải:** có thể lặp chu trình 0 vô hạn lần mà không tăng chi phí, tạo vô hạn walk; cần quy định chỉ đếm đường đơn hoặc loại nghiệm tương đương.

**Bài 23.** Trên lưới, một bước trượt miễn phí nối hai ô có phải là cạnh chi phí 0 không? **Lời giải:** có nếu đúng mô hình của đề: mỗi thao tác trượt ấy có tổng phí bằng 0, còn bước thường phí 1.

**Bài 24.** Với V đỉnh E cung và danh sách kề, thời gian 0–1 BFS? **Lời giải:** O(V+E) với trọng số hợp lệ, phép relax đúng và deque; chi phí xây danh sách kề cũng O(V+E).

## 16. Checklist khi giải bài 0–1 BFS

1. **Tất cả trọng số thật sự thuộc {0,1} chưa?** Nếu không, chọn phương pháp khác.
2. **Mục tiêu là tổng trọng số nhỏ nhất hay ít cạnh nhất?** Hai mục tiêu có thể khác nhau.
3. **Đồ thị có hướng/vô hướng?** Xây cạnh đúng chiều và đúng trọng số.
4. **Khoảng cách khởi tạo rõ chưa?** Nguồn 0, đỉnh chưa tới -1 hoặc INF.
5. **Có dùng deque thật sự không?** Cạnh 0 đẩy đầu, cạnh 1 đẩy cuối.
6. **Có kiểm tra cải thiện nghiêm ngặt?** Chỉ relax khi `candidate<old` hoặc chưa từng tới.
7. **Có cho phép cải thiện đỉnh đã được phát hiện trước đó?** Không khóa visited tại enqueue.
8. **Nếu deque lưu snapshot, đã bỏ mục stale khi lấy ra chưa?**
9. **Có lưu parent nếu cần đường đi và kiểm tra tổng trọng số đường trả về không?**
10. **Có xử lý chu trình trọng số 0 mà không enqueue khi bằng nhau không?**
11. **Có phân biệt nguồn→nguồn, đỉnh không tới và đường có chi phí 0 với nhiều cạnh không?**
12. **Nếu chỉ cần một đích, có dừng khi lấy mục hợp lệ thay vì khi enqueue lần đầu không?**
13. **Nếu nhiều nguồn, có khởi tạo tất cả nguồn ở chi phí 0 trong một lượt?**
14. **Đã kiểm tra trọng số 0/1, cạnh song song, khuyên, đồ thị rời rạc, hướng một chiều và nguồn trùng chưa?**
15. **Nếu cần đếm nghiệm/đường ít cạnh nhất khi đồng chi phí, đã mô hình hóa yêu cầu phụ chưa?**
16. **Đã đối chiếu với Bellman–Ford/Dijkstra trên dữ liệu nhỏ và đánh giá O(V+E) chưa?**

**Ghi nhớ:** 0–1 BFS là thuật toán shortest path đặc biệt hiệu quả khi mọi cạnh có trọng số **0 hoặc 1**. Mấu chốt không phải “thấy đỉnh lần đầu” mà là **relax khoảng cách**, **đưa đầu khi phí 0, đưa cuối khi phí 1**, và **bỏ các trạng thái deque lỗi thời**. Thuật toán trả tổng trọng số nhỏ nhất, không mặc định trả đường ít cạnh nhất.

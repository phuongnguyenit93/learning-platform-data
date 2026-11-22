# Duyệt theo chiều rộng (BFS)

## 1. BFS là gì?

**Breadth-First Search (BFS), hay duyệt theo chiều rộng**, là thuật toán duyệt đồ thị bằng cách khám phá các đỉnh theo từng lớp tính từ một hoặc nhiều đỉnh xuất phát. Thuật toán sử dụng **hàng đợi FIFO (First In, First Out)**: đỉnh vào hàng đợi trước được lấy ra xử lý trước. Cấu trúc ấy khác với stack/đệ quy thường dùng trong DFS, và chính nó tạo nên tính chất khoảng cách quan trọng của BFS.

Những bài toán điển hình:

- Kiểm tra một đỉnh có **đi tới được** từ đỉnh nguồn không.
- Liệt kê các đỉnh có thể đi tới và tính **số cạnh ít nhất** từ nguồn tới từng đỉnh.
- Tìm và khôi phục **một đường đi ngắn nhất** trong đồ thị không trọng số.
- Duyệt các **thành phần liên thông** của đồ thị vô hướng, bao gồm đỉnh cô lập.
- Tìm khoảng cách tới **nguồn gần nhất** khi có nhiều điểm xuất phát (multi-source BFS).
- Tìm đường trên lưới, mê cung hoặc không gian trạng thái mà mỗi chuyển động tốn cùng một đơn vị.
- Kiểm tra đồ thị vô hướng có hai phía, phân lớp đỉnh, lan truyền theo thời gian từng bước.

BFS bảo đảm đường ngắn nhất **tính theo số cạnh** trên đồ thị không trọng số hoặc đồ thị có mọi cạnh cùng chi phí dương. Nếu cạnh có trọng số khác nhau, đường ít cạnh nhất có thể **đắt hơn** một đường nhiều cạnh; BFS thông thường không thay thế Dijkstra hay thuật toán xử lý trọng số.

### Hình dung bằng các lớp

Từ một đỉnh xuất phát s:

~~~text
Lop 0: chinh s
Lop 1: cac dinh ke s chua tham
Lop 2: cac dinh moi can hai canh tu s
Lop 3: cac dinh moi can ba canh tu s
...
~~~

BFS lần lượt giải quyết các lớp 0, 1, 2... Hàng đợi giữ các đỉnh đã phát hiện nhưng chưa kiểm tra xong láng giềng. Vì chỉ có một đơn vị chi phí trên mỗi cạnh, các đỉnh ở lớp d luôn được xử lý trước khi thuật toán bắt đầu lấy ra các đỉnh thuộc lớp d+1.

Đừng nhầm **duyệt hết đồ thị** với **BFS từ một nguồn**: nếu đồ thị không liên thông thì một BFS chỉ tới được một phần của đồ thị.

## 2. Biểu diễn đồ thị để duyệt

Một đồ thị G=(V,E) gồm tập đỉnh V và tập cạnh E. Thông thường các đỉnh được gán chỉ số 0..n-1 với n=|V|. BFS cần phép toán “tìm các đỉnh kề của u”.

**Danh sách kề (adjacency list):** với mỗi u, lưu tập hoặc danh sách các v có cạnh u→v. Đây là cách phù hợp với đồ thị thưa, tiết kiệm O(V+E) bộ nhớ. Mỗi đỉnh chỉ bị xử lý một lần, nên tổng số cạnh kề được duyệt là O(E), tính cả hai bản ghi của cạnh vô hướng.

**Ma trận kề (adjacency matrix):** matrix[u][v] cho biết có cạnh hay không. Cần O(V²) bộ nhớ; muốn tìm mọi láng giềng của u có thể phải quét cả V cột. Khi duyệt toàn bộ đồ thị, BFS bằng ma trận thường có O(V²) thời gian.

### Cạnh có hướng và vô hướng

Với cạnh **vô hướng** (u,v), khi tạo adjacency list phải thêm:

~~~text
adj[u].add(v)
adj[v].add(u)
~~~

Với cạnh **có hướng** u→v, chỉ thêm v vào adj[u] trừ khi có thêm cạnh v→u trong input. BFS luôn tôn trọng hướng cạnh. Chẳng hạn đồ thị chỉ chứa 0→1 thì BFS từ 0 tới được 1, còn BFS từ 1 không tới được 0.

BFS trên đồ thị có hướng cho biết **reachability** từ nguồn, không tự động tìm **thành phần liên thông mạnh (SCC)**. Để tìm SCC có thể dùng Kosaraju hoặc Tarjan; phải phân biệt với component của đồ thị vô hướng.

### Đồ thị dùng xuyên suốt bài

Ta xét 7 đỉnh 0..6 và 6 cạnh vô hướng được thêm theo thứ tự:

~~~text
(0,1) (0,2) (1,3) (2,3) (2,4) (4,5)
~~~

Danh sách kề tương ứng:

~~~text
0: [1,2]
1: [0,3]
2: [0,3,4]
3: [1,2]
4: [2,5]
5: [4]
6: []
~~~

Đỉnh 6 cô lập. Đồ thị có hai thành phần: {0,1,2,3,4,5} và {6}. BFS từ 0 sẽ không nhìn thấy đỉnh 6 nếu không có vòng lặp ngoài duyệt các nguồn khác.

**Thứ tự láng giềng có tác động tới thứ tự BFS**, nhưng không làm thay đổi khoảng cách ngắn nhất. Nếu cần kết quả có thứ tự chính xác, hãy nêu rõ thứ tự xây adjacency list hoặc sắp danh sách kề.

## 3. Các biến trạng thái của BFS

Một triển khai thông dụng giữ:

- **queue:** hàng đợi FIFO các đỉnh đã phát hiện và đang chờ mở rộng.
- **visited[v]:** true nếu đỉnh v đã được phát hiện.
- **distance[v]:** số cạnh ít nhất từ nguồn đến v; có thể dùng -1 để biểu diễn chưa tới được.
- **parent[v]:** đỉnh dẫn đến lần phát hiện đầu tiên v; dùng để dựng lại một đường đi ngắn nhất.

Có thể dùng distance[v] khác -1 **thay cho** visited[v] riêng để tránh lưu thừa một mảng.

Thuật toán:

~~~text
bfs(adj, source):
    for v in all vertices:
        distance[v] = -1
        parent[v] = -1

    distance[source] = 0
    queue = FIFO()
    queue.addLast(source)

    while not queue.isEmpty():
        u = queue.removeFirst()

        for v in adj[u]:
            if distance[v] != -1:
                continue

            distance[v] = distance[u] + 1
            parent[v] = u
            queue.addLast(v)

    return distance, parent
~~~

**Điểm quan trọng:** đánh dấu visited hoặc gán distance **ngay khi thêm v vào queue**, không đợi tới khi v được lấy ra. Điều này bảo đảm mỗi đỉnh chỉ được enqueue một lần, parent không bị ghi đè bởi nhiều láng giềng, và queue không phình to vì các đỉnh trùng.

Ví dụ đồ thị có vòng 0–1–2–0. Nếu cứ gặp một cạnh lại enqueue mà không kiểm tra visited, thuật toán có thể quay vòng mãi; nếu đánh dấu khi dequeue nhưng không kiểm tra trạng thái đã phát hiện, cùng một đỉnh có thể bị thêm nhiều lần.

BFS thông thường là thuật toán **lặp**, không cần dùng đệ quy. Trong Java, ArrayDeque<Integer> cung cấp addLast và removeFirst với ngữ nghĩa hàng đợi; dùng Stack hay push/pop ở cùng một đầu sẽ không còn là BFS theo lớp.

## 4. Mô phỏng queue, distance và parent

BFS bắt đầu từ 0 trên đồ thị 7 đỉnh:

~~~text
queue = [0]
distance[0] = 0
parent[0] = -1
~~~

Các bước dequeue:

| Đỉnh lấy ra | Đỉnh mới được phát hiện | Queue sau khi xử lý | Ghi nhận |
| --- | --- | --- | --- |
| 0 | 1,2 | [1,2] | d[1]=1, d[2]=1 |
| 1 | 3 | [2,3] | d[3]=2 |
| 2 | 4 | [3,4] | d[4]=2 |
| 3 | không có | [4] | — |
| 4 | 5 | [5] | d[5]=3 |
| 5 | không có | [] | — |

Kết quả với đúng thứ tự adjacency list ở trên:

~~~text
order    = [0,1,2,3,4,5]
distance = [0,1,1,2,2,3,-1]
parent   = [-1,0,0,1,2,4,-1]
~~~

Các lớp là:

~~~text
Lop 0: [0]
Lop 1: [1,2]
Lop 2: [3,4]
Lop 3: [5]
Unreachable: [6]
~~~

Đỉnh 3 được phát hiện qua 1 trước khi BFS kiểm tra cạnh 2–3; vì vậy parent[3]=1. Nhưng đường 0→2→3 cũng dài hai cạnh và cũng là đường ngắn nhất. Nếu đổi thứ tự láng giềng, parent[3] có thể đổi; distance[3]=2 vẫn giữ nguyên.

**Thứ tự thăm là một kết quả phụ thuộc tie-breaking**, trong khi khoảng cách và tập reachable là kết quả toán học của đồ thị và nguồn.

### Lưu mức bằng kích thước queue

Một cách thay thế cho distance khi chỉ cần duyệt theo tầng:

~~~text
level = 0
while queue not empty:
    countThisLevel = queue.size()
    repeat countThisLevel times:
        u = queue.removeFirst()
        process u at level
        enqueue unseen neighbors
    level++
~~~

Điểm tinh tế là lấy queue.size() **trước** khi bắt đầu mức và chỉ xử lý đúng số đỉnh đó. Các đỉnh được thêm trong quá trình xử lý phải thuộc mức **tiếp theo**. Tuy nhiên, nếu đã lưu distance, cách gán distance[v]=distance[u]+1 thường đơn giản hơn.

## 5. Tại sao BFS bảo đảm khoảng cách ngắn nhất?

Giả sử mỗi cạnh có chi phí một đơn vị. Ta xét số cạnh trên đường từ s tới v.

**Cơ sở:** source có distance=0, không có đường nào ít hơn 0 cạnh.

**Bước quy nạp theo lớp:** giả sử tất cả đỉnh ở lớp nhỏ hơn hoặc bằng d đã được phát hiện với khoảng cách chính xác. Khi BFS lấy ra u với distance[u]=d, mỗi láng giềng chưa được phát hiện v nhận distance[v]=d+1. Điều đó tạo ra một đường đi thật sự dài d+1 cạnh. Nếu v có đường ngắn hơn, độ dài của đường ấy tối đa d; các đỉnh theo đường ngắn hơn phải đã được khám phá qua các lớp trước, nên v đã được đánh dấu, mâu thuẫn với việc v mới được phát hiện.

Do FIFO giữ thứ tự lớp không giảm, thuật toán không bỏ qua một đường ít cạnh hơn khi lần đầu gán distance. Vì thế **distance[v] được gán ở lần enqueue đầu tiên là tối ưu**.

Một cách nhìn khác: mọi đường đi từ s tới một đỉnh cách d+1 cạnh phải có đỉnh ngay trước ở khoảng cách tối đa d. BFS đã mở rộng toàn bộ đỉnh lớp ≤d trước khi mở rộng lớp lớn hơn, nên v không thể chỉ được phát hiện lần đầu ở khoảng cách >d+1.

**Tính kết thúc:** với V hữu hạn, mỗi đỉnh được enqueue tối đa một lần, mỗi lần dequeue xử lý hữu hạn cạnh kề, nên vòng lặp kết thúc. Nếu còn một đỉnh reachable chưa được phát hiện, xét một đường đi từ source tới nó: điểm đầu đã được thăm, mỗi lần mở rộng cạnh tới đỉnh tiếp theo sẽ đưa đỉnh ấy vào queue, dẫn đến mâu thuẫn.

Chứng minh này **không áp dụng nguyên xi** khi mỗi cạnh có trọng số khác nhau. Ví dụ s→t một cạnh chi phí 100, s→a chi phí 1, a→t chi phí 1. BFS ưu tiên đường s→t vì chỉ có một cạnh, mặc dù tổng chi phí 100 lớn hơn 2 của s→a→t. Để tối ưu tổng trọng số, dùng thuật toán trọng số thích hợp.

## 6. Khôi phục một đường đi ngắn nhất

Mỗi khi BFS lần đầu phát hiện v từ u, ghi:

~~~text
distance[v] = distance[u] + 1
parent[v] = u
~~~

Sau khi BFS kết thúc, để tìm một path từ source tới target:

1. Nếu distance[target]=-1, không có đường đi: trả danh sách rỗng hoặc thông báo unreachable.
2. Nếu reachable, bắt đầu tại target và lần lượt lấy parent[v] cho tới -1.
3. Đảo danh sách vì quá trình này thu các đỉnh từ đích về nguồn.

Ví dụ target=5:

~~~text
parent[5]=4
parent[4]=2
parent[2]=0
parent[0]=-1

Truy vet nguoc: [5,4,2,0]
Dao thu tu:     [0,2,4,5]
So canh:         3
~~~

Với target=6, distance[6]=-1 và path rỗng. Với target=source, distance=0 và path chỉ có [source]; **đừng** dùng điều kiện parent[target]==-1 để kết luận không reachable vì chính source cũng có parent=-1.

Bảng parent tạo một **cây BFS** trên các đỉnh reachable, chứa một đường ngắn nhất tới mỗi đỉnh (trừ nguồn). Nếu có nhiều đường cùng độ dài, nó chỉ giữ một đường. Muốn **đếm hoặc liệt kê toàn bộ các đường ngắn nhất**, cần lưu thêm thông tin và không thể dựa vào một parent duy nhất.

## 7. Duyệt toàn bộ đồ thị và thành phần liên thông

Nếu chỉ chạy BFS từ source=0 thì đỉnh 6 cô lập không xuất hiện. Để xử lý mọi đỉnh của **đồ thị vô hướng**, thêm một vòng ngoài:

~~~text
visited[v] = false for all vertices
components = []

for start in vertices:
    if visited[start]:
        continue

    component = []
    mark visited[start]
    queue.addLast(start)

    while queue not empty:
        u = queue.removeFirst()
        component.add(u)
        for v in adj[u]:
            if not visited[v]:
                mark visited[v]
                queue.addLast(v)

    components.add(component)
~~~

Mỗi lượt BFS mở rộng đúng một thành phần liên thông vô hướng vì mọi đỉnh trong thành phần có đường đi tới nhau; các đỉnh của thành phần khác không có cạnh nối. Với đồ thị mẫu, kết quả là:

~~~text
[[0,1,2,3,4,5],[6]]
~~~

Đỉnh cô lập tạo thành một thành phần gồm một đỉnh. Đồ thị rỗng có danh sách thành phần rỗng; khái niệm “đồ thị rỗng có liên thông không” có thể phụ thuộc quy ước, nên bài toán liên thông Boolean phải nêu rõ quy ước đó.

**Chú ý đồ thị có hướng:** vòng ngoài này không cho SCC. SCC là một tập đỉnh trong đó mọi cặp đỉnh có đường đi theo hướng cả hai chiều. BFS reachable thông thường chỉ xác nhận được một chiều. Không được đổi nhãn kết quả thành “SCC” nếu chưa dùng thuật toán phù hợp.

## 8. BFS đa nguồn (multi-source BFS)

Khi có nhiều nguồn xuất phát và tất cả cạnh có cùng chi phí, ta thường muốn:

~~~text
distance[v] = min(distance(s,v)) voi moi s thuoc sources
~~~

Thay vì chạy từng BFS rồi lấy min, **seed tất cả nguồn vào queue ở lớp 0**:

~~~text
distance[v] = -1 for all v
parent[v] = -1 for all v
queue = empty

for s in sources:
    if distance[s] == -1:
        distance[s] = 0
        queue.addLast(s)

run the usual FIFO BFS
~~~

Đây là một lần BFS duy nhất. Khi khoảng cách tới v được gán lần đầu, v đã được khám phá từ nguồn gần nhất theo số cạnh. Nếu hai nguồn cùng gần, nguồn nào có đường được mở rộng trước có thể được chọn làm cha/nguồn sở hữu; **khoảng cách tối thiểu không thay đổi**.

Với đồ thị mẫu và nguồn [0,5]:

~~~text
source 0, source 5: distance=0
dinh 1,2 cach 0 mot canh
dinh 4 cach 5 mot canh
dinh 3 cach nguon gan nhat hai canh
dinh 6 khong reachable

distance = [0,1,1,2,1,0,-1]
~~~

**Không chạy BFS từ 0 tới hết rồi mới từ 5 trên cùng visited mà không cho phép cập nhật.** Cách ấy có thể giữ khoảng cách từ 0 dù nguồn 5 gần hơn. Đa nguồn đúng bắt đầu đồng thời từ mọi nguồn.

Nếu các nguồn có thời điểm khởi hành khác nhau hoặc cạnh có trọng số khác nhau, việc đặt mọi source distance=0 có thể không biểu diễn đúng câu hỏi; cần mô hình hóa chi phí và chọn thuật toán khác.

## 9. BFS trên lưới và mê cung

Một lưới R×C là một **đồ thị ngầm**. Mỗi ô đi được là một đỉnh; hai ô có cạnh nếu theo quy định có thể di chuyển trực tiếp từ ô này sang ô kia. Không cần tạo danh sách kề đầy đủ; chỉ sinh các ô láng giềng khi dequeue một ô.

Bốn hướng phổ biến:

~~~text
dr = [ 1, 0,-1, 0]   // xuong, phai, len, trai
dc = [ 0, 1, 0,-1]

for k in 0..3:
    nr = r + dr[k]
    nc = c + dc[k]

    if inBounds(nr,nc) AND notWall(nr,nc)
       AND distance[nr][nc] == -1:
        distance[nr][nc] = distance[r][c] + 1
        parent[nr][nc] = (r,c)
        queue.add((nr,nc))
~~~

**Phải kiểm tra trong biên trước khi truy cập grid[nr][nc].** Với mỗi bước chi phí 1, BFS tìm được số bước ít nhất. Nếu ô có chi phí khác nhau, hoặc có phép dịch chuyển đặc biệt với chi phí khác 1, cần xem lại đồ thị trạng thái/thuật toán.

Ví dụ lưới ba hàng, bốn cột:

~~~text
S..#
.#..
...T
~~~

S ở (0,0), T ở (2,3), dấu # là tường. Với thứ tự thử hướng **xuống, phải, lên, trái**, một đường ngắn nhất là:

~~~text
(0,0) -> (1,0) -> (2,0) -> (2,1) -> (2,2) -> (2,3)
~~~

Đường gồm **6 ô và 5 bước**. Chênh lệch Manhattan giữa hai ô đầu/cuối là |2-0|+|3-0|=5 nên không có đường đi bốn hướng nào ít hơn 5 bước; đường trên đạt đúng cận dưới.

Nếu điểm đầu hoặc cuối bị chặn, trả -1 và path rỗng; nếu S=T và không bị chặn, số bước bằng 0 và path chứa đúng một ô. Nếu đi 8 hướng hoặc cấm đi chéo xuyên góc tường, quy tắc sinh láng giềng phải nêu rõ.

## 10. BFS trên không gian trạng thái ngầm

Không phải bài BFS nào cũng có tập đỉnh được liệt kê sẵn. Có thể xem mỗi **cấu hình hợp lệ** là một đỉnh:

- Giá trị nguyên x có phép biến đổi x→x+1, x→x-1, x→2x trong một miền hữu hạn.
- Vị trí nhân vật trên lưới kèm trạng thái đã nhặt chìa khóa.
- Trạng thái bài ghép hình, xâu ký tự, cấu hình đèn bật/tắt.
- Vị trí robot kèm hướng quay, số bước nhảy còn lại hoặc loại phương tiện đang dùng.

Mỗi thao tác hợp lệ là một cạnh. Nếu **mỗi thao tác tốn cùng một đơn vị**, BFS tìm số thao tác ít nhất tới trạng thái đích.

### Khóa visited phải đủ thông tin

Giả sử mê cung có cửa chỉ mở khi đã lấy được chìa. Hai lần đến cùng ô (r,c) có thể khác nhau:

~~~text
(r,c,hasKey=false)
(r,c,hasKey=true)
~~~

Chúng có tập bước đi tiếp theo khác nhau. Nếu chỉ đánh dấu visited[r][c], lượt tới sau có chìa có thể bị bỏ nhầm, khiến thuật toán không tìm được đường hợp lệ. Khóa của trạng thái cần gồm vị trí **và** thông tin ảnh hưởng tương lai, ví dụ (row,col,hasKey).

Với K chìa khóa độc lập, có thể dùng bitmask K bit, làm số state tiềm năng tới R×C×2^K. BFS không còn O(RC) nếu mỗi ô có nhiều trạng thái công cụ khác nhau; phải phân tích không gian thực sự được duyệt.

### BFS hai đầu

Khi tìm đường giữa một nguồn và một đích, và **có thể sinh chuyển trạng thái theo cả hai chiều phù hợp**, bidirectional BFS mở rộng từ hai phía và tìm điểm gặp. Nó có thể giảm số trạng thái phải thăm trên không gian phân nhánh lớn, nhưng cần đúng cơ chế giao hai frontier, đồ thị ngược tương ứng với cạnh có hướng, và điều kiện dừng giữ tính tối ưu. Không được tùy tiện chạy hai BFS rồi cộng hai khoảng cách đến các điểm khác nhau.

## 11. Độ phức tạp thời gian và bộ nhớ

Với danh sách kề, BFS chuẩn có:

~~~text
Thoi gian: O(V + E)
Bo nho phu: O(V) cho queue, distance, parent/visited
Bo nho de luu danh sach ke: O(V + E)
~~~

Lý do: mỗi đỉnh vào queue tối đa một lần, nên có tối đa V lượt dequeue. Khi dequeue một đỉnh u, BFS duyệt danh sách láng giềng của u. Tổng độ dài các danh sách kề là E trên đồ thị có hướng hoặc 2E trên đồ thị vô hướng. Cộng với khởi tạo các mảng V phần tử ta có O(V+E).

Đồ thị không liên thông với vòng ngoài duyệt mọi thành phần vẫn tốn O(V+E), vì **visited toàn cục** bảo đảm một đỉnh không bị mở rộng hai lần; không phải O(V×(V+E)).

Với ma trận kề, quét V ô trên mỗi hàng cho tối đa V đỉnh có thể tốn O(V²). Với lưới R×C và 4 láng giềng mỗi ô, thời gian/bộ nhớ phụ là O(RC), không tính các trạng thái mở rộng như hasKey.

### Chi phí output

Lần theo parent cho một đường dài d cạnh tốn O(d+1) thời gian và O(d+1) bộ nhớ để lưu các đỉnh. Nếu có nhiều truy vấn đích trên cùng nguồn, chạy BFS một lần O(V+E), rồi mỗi truy vấn chỉ cần O(1) để lấy distance và O(d+1) nếu cần xuất path.

Lưu tất cả path trong queue là không cần thiết và dễ tốn O(length of path) cho mỗi lần mở rộng. Mảng parent lưu một quan hệ tiền nhiệm trên từng đỉnh, đủ dựng một đường ngắn nhất.

### Thực tế Java

ArrayDeque<Integer> có boxing đối tượng Integer; với đồ thị cực lớn, overhead GC có thể đáng kể. Queue mảng int cùng head/tail đôi khi hiệu quả hơn nhưng cần cài đặt ranh giới chính xác. BFS tránh stack đệ quy sâu nên thường phù hợp với đồ thị lớn hơn kiểu DFS đệ quy nếu bộ nhớ queue cho phép.

Nếu đồ thị có V đỉnh nhưng số trạng thái ngầm tăng theo bitmask, chi phí không được ghi nhầm thành O(V+E) của đồ thị vật lý ban đầu. V và E ở đây phải là **số trạng thái và chuyển trạng thái thực sự** của mô hình đã chọn.

## 12. Java 17 – chương trình hoàn chỉnh

Tệp Java dưới đây trình bày bốn thao tác: BFS đơn nguồn, BFS đa nguồn, liệt kê các thành phần vô hướng, và tìm đường ngắn nhất trên lưới. Mọi ví dụ dùng **chỉ số đỉnh bắt đầu từ 0**. Các đầu vào được thiết kế để kết quả có thứ tự ổn định.

Lưu toàn bộ mã vào **BfsTraversalDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class BfsTraversalDemo {

    record BfsResult(List<Integer> order, int[] distance,
                     int[] parent) {}

    record GridResult(int steps, List<String> path) {}

    // Tao danh sach ke cho do thi VO HUONG.
    static List<List<Integer>> undirectedGraph(
            int n, int[][] edges) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be nonnegative");
        }
        Objects.requireNonNull(edges, "edges");

        List<List<Integer>> graph = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            graph.add(new ArrayList<>());
        }
        for (int[] edge : edges) {
            if (edge == null || edge.length != 2) {
                throw new IllegalArgumentException("invalid edge");
            }
            int u = edge[0], v = edge[1];
            if (u < 0 || u >= n || v < 0 || v >= n) {
                throw new IllegalArgumentException("vertex out of range");
            }
            graph.get(u).add(v);
            graph.get(v).add(u);
        }
        return graph;
    }

    private static void checkSource(int n, int source) {
        if (source < 0 || source >= n) {
            throw new IllegalArgumentException("source out of range");
        }
    }

    static BfsResult bfs(List<List<Integer>> graph, int source) {
        return multiSourceBfs(graph, new int[]{source});
    }

    static BfsResult multiSourceBfs(
            List<List<Integer>> graph, int[] sources) {
        Objects.requireNonNull(graph, "graph");
        Objects.requireNonNull(sources, "sources");

        int n = graph.size();
        int[] distance = new int[n];
        int[] parent = new int[n];
        Arrays.fill(distance, -1);
        Arrays.fill(parent, -1);

        ArrayDeque<Integer> queue = new ArrayDeque<>();
        List<Integer> order = new ArrayList<>();

        for (int source : sources) {
            checkSource(n, source);
            if (distance[source] != -1) {
                continue;
            }
            distance[source] = 0;
            queue.addLast(source);
        }

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            order.add(u);
            for (int v : graph.get(u)) {
                if (distance[v] != -1) {
                    continue;
                }
                distance[v] = distance[u] + 1;
                parent[v] = u;
                queue.addLast(v);
            }
        }
        return new BfsResult(List.copyOf(order), distance, parent);
    }

    static List<Integer> restorePath(
            BfsResult result, int target) {
        Objects.requireNonNull(result, "result");
        int[] distance = result.distance();
        if (target < 0 || target >= distance.length) {
            throw new IllegalArgumentException("target out of range");
        }
        if (distance[target] == -1) {
            return List.of();
        }

        List<Integer> reversed = new ArrayList<>();
        for (int v = target; v != -1; v = result.parent()[v]) {
            reversed.add(v);
        }
        Collections.reverse(reversed);
        return List.copyOf(reversed);
    }

    // Chi goi ham nay cho do thi VO HUONG.
    static List<List<Integer>> connectedComponentsUndirected(
            List<List<Integer>> graph) {
        Objects.requireNonNull(graph, "graph");
        int n = graph.size();
        boolean[] visited = new boolean[n];
        List<List<Integer>> components = new ArrayList<>();

        for (int start = 0; start < n; start++) {
            if (visited[start]) {
                continue;
            }
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            List<Integer> component = new ArrayList<>();
            visited[start] = true;
            queue.addLast(start);

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                component.add(u);
                for (int v : graph.get(u)) {
                    if (!visited[v]) {
                        visited[v] = true;
                        queue.addLast(v);
                    }
                }
            }
            components.add(List.copyOf(component));
        }
        return List.copyOf(components);
    }

    // '#' la tuong, cac o con lai deu co the di qua.
    // Thu hang xom theo thu tu: xuong, phai, len, trai.
    static GridResult shortestGridPath(
            char[][] grid, int sr, int sc, int tr, int tc) {
        Objects.requireNonNull(grid, "grid");
        if (grid.length == 0 || grid[0] == null
                || grid[0].length == 0) {
            throw new IllegalArgumentException("empty grid");
        }

        int rows = grid.length;
        int cols = grid[0].length;
        for (char[] row : grid) {
            if (row == null || row.length != cols) {
                throw new IllegalArgumentException("nonrectangular grid");
            }
        }
        if (sr < 0 || sr >= rows || tr < 0 || tr >= rows
                || sc < 0 || sc >= cols || tc < 0 || tc >= cols) {
            throw new IllegalArgumentException("cell out of range");
        }
        if (grid[sr][sc] == '#' || grid[tr][tc] == '#') {
            return new GridResult(-1, List.of());
        }

        int[][] distance = new int[rows][cols];
        int[][] parent = new int[rows][cols];
        for (int r = 0; r < rows; r++) {
            Arrays.fill(distance[r], -1);
            Arrays.fill(parent[r], -1);
        }

        int[] dr = {1, 0, -1, 0};
        int[] dc = {0, 1, 0, -1};
        ArrayDeque<Integer> queue = new ArrayDeque<>();

        distance[sr][sc] = 0;
        queue.addLast(sr * cols + sc);

        while (!queue.isEmpty()) {
            int current = queue.removeFirst();
            int r = current / cols;
            int c = current % cols;
            if (r == tr && c == tc) {
                break;
            }
            for (int k = 0; k < 4; k++) {
                int nr = r + dr[k];
                int nc = c + dc[k];
                if (nr < 0 || nr >= rows || nc < 0 || nc >= cols
                        || grid[nr][nc] == '#'
                        || distance[nr][nc] != -1) {
                    continue;
                }
                distance[nr][nc] = distance[r][c] + 1;
                parent[nr][nc] = current;
                queue.addLast(nr * cols + nc);
            }
        }

        if (distance[tr][tc] == -1) {
            return new GridResult(-1, List.of());
        }
        List<String> reversed = new ArrayList<>();
        int current = tr * cols + tc;
        while (current != -1) {
            int r = current / cols;
            int c = current % cols;
            reversed.add("(" + r + "," + c + ")");
            current = parent[r][c];
        }
        Collections.reverse(reversed);
        return new GridResult(
                distance[tr][tc], List.copyOf(reversed));
    }

    public static void main(String[] args) {
        List<List<Integer>> graph = undirectedGraph(7,
                new int[][]{
                        {0, 1}, {0, 2}, {1, 3},
                        {2, 3}, {2, 4}, {4, 5}
                });

        BfsResult single = bfs(graph, 0);
        System.out.println("BFS order = " + single.order());
        System.out.println("distance = " +
                Arrays.toString(single.distance()));
        System.out.println("parent = " +
                Arrays.toString(single.parent()));
        System.out.println("path 0->5 = " + restorePath(single, 5));
        System.out.println("path 0->6 = " + restorePath(single, 6));
        System.out.println("components = " +
                connectedComponentsUndirected(graph));

        BfsResult multi = multiSourceBfs(graph, new int[]{0, 5});
        System.out.println("multi-source distance = " +
                Arrays.toString(multi.distance()));

        char[][] maze = {
                {'S', '.', '.', '#'},
                {'.', '#', '.', '.'},
                {'.', '.', '.', 'T'}
        };
        GridResult grid = shortestGridPath(maze, 0, 0, 2, 3);
        System.out.println("grid steps = " + grid.steps());
        System.out.println("grid path = " + grid.path());

        try {
            bfs(graph, 7);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid source: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac BfsTraversalDemo.java
java BfsTraversalDemo
~~~

**Stdout chính xác:**

~~~text
BFS order = [0, 1, 2, 3, 4, 5]
distance = [0, 1, 1, 2, 2, 3, -1]
parent = [-1, 0, 0, 1, 2, 4, -1]
path 0->5 = [0, 2, 4, 5]
path 0->6 = []
components = [[0, 1, 2, 3, 4, 5], [6]]
multi-source distance = [0, 1, 1, 2, 1, 0, -1]
grid steps = 5
grid path = [(0,0), (1,0), (2,0), (2,1), (2,2), (2,3)]
invalid source: source out of range
~~~

### Giải thích kết quả và hợp đồng API

- BfsResult.order chứa thứ tự **dequeue**. Với thứ tự thêm cạnh trên, kết quả là [0,1,2,3,4,5].
- BfsResult.distance dùng -1 cho unreachable. Đỉnh nguồn có distance=0 và parent=-1; đỉnh 6 có distance=-1 và parent=-1, nên restorePath phải kiểm tra **distance**.
- BFS từ 0 tạo parent[3]=1, dù cũng có một đường ngắn nhất tới 3 qua 2.
- connectedComponentsUndirected chỉ dành cho graph **vô hướng** như được tạo trong main; không phải thuật toán SCC.
- Multi-source gán đồng thời khoảng cách 0 cho 0 và 5; đỉnh 4 vì thế chỉ cách nguồn gần nhất một cạnh.
- GridPath có 5 bước trên 6 ô, đúng với cận dưới Manhattan. Mọi ô khác ký tự '#' đều được coi là có thể đi.
- Nguồn 7 nằm ngoài miền [0,6], nên bfs ném IllegalArgumentException và main in thông báo.

**Giới hạn đáng chú ý:** BFS và multiSourceBfs giả định danh sách kề được truyền vào đã chứa các chỉ số đỉnh hợp lệ; builder undirectedGraph có kiểm tra mọi cạnh, nhưng một graph được tự dựng từ nguồn không tin cậy nên được kiểm tra riêng trước khi duyệt. BfsResult chứa mảng int[] có thể bị sửa bởi người gọi; ví dụ chỉ đọc các mảng. Muốn API bất biến, trả bản sao của mảng khi truy cập hoặc cung cấp view không sửa được.

Các nguồn trùng nhau được seed một lần; nguồn rỗng trả mảng distance toàn -1. Đồ thị rỗng có component rỗng nhưng bfs(graph,0) sẽ từ chối nguồn 0. GridPath kiểm tra lưới hình chữ nhật và tọa độ; nếu ô đích không tới được, trả -1 bước và path rỗng.

## 13. So sánh BFS với DFS, Dijkstra và 0–1 BFS

| Thuật toán | Cách ưu tiên mở rộng | Bảo đảm tối ưu | Phạm vi tiêu biểu |
| --- | --- | --- | --- |
| BFS | Queue FIFO | Số cạnh ít nhất khi mọi cạnh cùng chi phí | Đồ thị không trọng số |
| DFS | Stack hoặc đệ quy | Không tối ưu khoảng cách nói chung | Duyệt sâu, chu trình, nhiều bài cấu trúc |
| Multi-source BFS | Queue, mọi nguồn lớp 0 | Khoảng cách tới nguồn gần nhất | Lan truyền và khoảng cách |
| 0–1 BFS | Deque hai đầu | Tổng chi phí nhỏ nhất với cạnh có trọng số 0 hoặc 1 | Đồ thị trọng số nhị phân |
| Dijkstra | Priority queue theo distance | Tổng chi phí nhỏ nhất với trọng số không âm | Đồ thị trọng số |
| Bellman–Ford | Relax cạnh lặp lại | Xử lý cạnh âm nếu không có chu trình âm reachable gây mất nghiệm hữu hạn | Đồ thị có cạnh âm |

DFS có thể đi một nhánh rất sâu trước khi quay lại một nhánh dẫn tới đích gần hơn. BFS xét lớp khoảng cách nên phù hợp với bài hỏi số bước tối thiểu.

**0–1 BFS** không phải BFS FIFO thông thường: cạnh chi phí 0 đưa vào **đầu deque**, cạnh chi phí 1 đưa vào **cuối deque**, và phải cập nhật distance khi tìm được đường tốt hơn. Nếu mọi cạnh có trọng số 2,5,100..., 0–1 BFS cũng không phải thuật toán phù hợp.

Dijkstra dùng độ ưu tiên theo tổng chi phí chứ không theo số cạnh. Bellman–Ford có thể nhận diện ảnh hưởng của chu trình âm trong miền reachable; khi có chu trình âm có thể lặp trước đích, “đường đi ngắn nhất” theo tổng trọng số có thể không có giá trị hữu hạn.

## 14. Các biến thể quan trọng

### Đếm số đường đi ngắn nhất

Nếu muốn biết có bao nhiêu đường ngắn nhất từ source tới v, có thể duy trì ways[v]:

~~~text
distance[source] = 0
ways[source] = 1

while queue not empty:
    u = dequeue
    for v in adj[u]:
        if distance[v] == -1:
            distance[v] = distance[u] + 1
            ways[v] = ways[u]
            enqueue(v)
        else if distance[v] == distance[u] + 1:
            ways[v] += ways[u]
~~~

Điều kiện thứ hai cộng thêm các đường ngắn nhất qua một cha khác có cùng độ dài. Không enqueue v lần nữa; chỉ tăng ways. Nếu đồ thị có **cạnh song song**, công thức đếm những chuỗi cạnh khác nhau; nếu đề đếm đường theo chuỗi đỉnh, cần loại trùng cạnh tương ứng. Số đường có thể rất lớn, nên dùng BigInteger hoặc modulo đúng yêu cầu.

Nếu đề chỉ hỏi một đường, parent[v] là đủ; muốn đếm tất cả thì một parent duy nhất **không đủ**.

### Kiểm tra đồ thị hai phía

Với đồ thị **vô hướng**, gán màu 0/1 cho mỗi đỉnh, dùng BFS:

1. Chọn một đỉnh chưa tô màu ở một thành phần, tô màu 0 và enqueue.
2. Với cạnh u–v, nếu v chưa màu thì gán color[v]=1-color[u].
3. Nếu v đã màu mà color[v]==color[u], đồ thị **không hai phía**.
4. Nếu không có xung đột ở mọi thành phần, đồ thị hai phía.

Một self-loop làm xung đột ngay vì đỉnh không thể có màu khác chính nó; một chu trình lẻ cũng làm xung đột. Phải xét **mọi thành phần**, không chỉ thành phần chứa source=0.

### Dừng BFS sớm ở một đích

Nếu chỉ cần distance hoặc một path tới target, có thể dừng **ngay khi target được khám phá và enqueue lần đầu**, vì lúc ấy distance đã tối ưu; dừng khi target được dequeue cũng đúng. Nhưng nếu đang tính khoảng cách tới mọi đỉnh, duyệt toàn bộ thành phần hoặc đếm tất cả đường đi ngắn nhất, dừng sớm có thể làm thiếu thông tin.

Khi đếm các đường ngắn nhất tới target, cần xử lý đầy đủ các cạnh từ các đỉnh ở lớp distance[target]-1, vì chúng có thể đóng góp thêm đường cùng độ dài.

### Bắt đầu từ nhiều điểm và truy vấn nhiều đích

Với cùng một source và nhiều đích, chạy BFS một lần và tra distance[target] O(1) mỗi truy vấn; khôi phục path tốn theo chiều dài. Với nhiều nguồn cần tìm **nguồn gần nhất**, dùng multi-source BFS một lần. Với nhiều cặp nguồn–đích độc lập, có thể cần nhiều BFS hoặc thuật toán tiền xử lý khác tùy kích thước và cấu trúc đồ thị.

## 15. Những sai sót phổ biến

| Sai sót | Hậu quả | Cách tránh |
| --- | --- | --- |
| Dùng stack thay queue | Duyệt sâu, không giữ thứ tự lớp | Dùng FIFO |
| Đánh dấu visited khi dequeue | Enqueue trùng, tốn bộ nhớ | Đánh dấu ngay khi enqueue |
| Không khởi tạo distance[source]=0 | Sai khoảng cách gốc | Seed nguồn trước vòng while |
| Gán mọi distance=0 | Không nhận ra unreachable | Dùng -1 cho chưa thăm |
| Ghi lại parent mỗi khi gặp cạnh | Parent/path có thể không nhất quán | Chỉ gán khi phát hiện lần đầu |
| Dựa vào parent=-1 để kết luận unreachable | Nhầm chính source | Kiểm tra distance |
| Quên đảo path từ đích về nguồn | Path ngược | Reverse |
| Bỏ qua đỉnh cô lập | Thiếu component | Vòng ngoài trên mọi đỉnh khi cần |
| Thêm cạnh ngược vào đồ thị có hướng | Reachability giả | Tôn trọng hướng cạnh |
| Dùng BFS làm SCC | Nhóm đỉnh sai | Tarjan/Kosaraju |
| Dùng BFS FIFO cho trọng số tùy ý | Tối ưu số cạnh thay vì chi phí | Chọn thuật toán trọng số phù hợp |
| Chạy nhiều nguồn tuần tự với visited chung | Không có khoảng cách tới nguồn gần nhất | Seed đồng thời tất cả nguồn |
| Dùng visited chỉ theo vị trí khi có chìa khóa | Bỏ sót trạng thái khác | Đưa hasKey vào state |
| Truy cập grid trước khi kiểm tra biên | Lỗi chỉ số mảng | Kiểm tra r,c trước |
| Xem số ô trên path là số bước | Lệch 1 | Số bước = số cạnh = số ô - 1 |
| Dừng sớm khi đếm mọi đường ngắn nhất | Đếm thiếu | Xử lý đủ lớp tiền nhiệm |
| Đưa toàn bộ path vào từng mục queue | Cấp phát lớn không cần thiết | Lưu parent cho từng đỉnh |

Kiểm tra tính nhất quán sau khi chạy: với mỗi v reachable trừ nguồn, parent[v] phải là một láng giềng hợp lệ có distance[parent[v]]=distance[v]-1; order không chứa đỉnh lặp và khoảng cách của queue không giảm theo thời điểm dequeue.

## 16. Kiểm thử theo thuộc tính và trường hợp biên

**Tính chất chung:**

- Với source hợp lệ, distance[source]=0; source luôn reachable.
- Mọi đỉnh trong order xuất hiện đúng một lần.
- Nếu parent[v]=u thì có cạnh u→v và distance[v]=distance[u]+1.
- Nếu distance[v]=-1 thì không có đường đi từ source tới v theo hướng cạnh.
- Với một cạnh vô hướng (u,v) mà cả hai reachable, độ chênh |distance[u]-distance[v]| không vượt 1.
- Thay thứ tự adjacency có thể đổi order/parent nhưng không đổi distance.
- Mỗi path trả về bắt đầu từ source, kết thúc tại target, đi qua các cạnh hợp lệ và có số cạnh bằng distance[target].
- Nếu không tới được target, trả path rỗng.

**Multi-source:**

- Mọi nguồn phân biệt có khoảng cách 0.
- Khoảng cách của v bằng min khoảng cách từ mọi nguồn tới v.
- Nguồn trùng lặp không làm thay đổi khoảng cách.
- Sources rỗng thì không có đỉnh nào reachable từ một nguồn được seed.

**Lưới:**

- Mỗi ô trong path ở trong biên và khác tường.
- Hai ô liên tiếp cách nhau đúng một bước theo quy tắc di chuyển.
- Path có k ô thì số bước là k-1 khi reachable.
- Start=target cho 0 bước; đường bị chặn trả -1 và path rỗng.
- Thay thứ tự hướng có thể đổi path nhưng không đổi số bước.

### Bảng ca mẫu

| Ca | Kết quả |
| --- | --- |
| BFS từ 0 trên đồ thị 7 đỉnh | distance [0,1,1,2,2,3,-1] |
| Path 0→5 | [0,2,4,5] |
| Path 0→6 | Không tới được, [] |
| Components vô hướng | [[0,1,2,3,4,5],[6]] |
| Multi-source [0,5] | [0,1,1,2,1,0,-1] |
| Một đỉnh 0 không có cạnh | distance [0], path [0] |
| Đồ thị rỗng, components | [] |
| Đồ thị rỗng, bfs(0) | Từ chối source ngoài miền |
| Một self-loop tại 0 | Không enqueue 0 lần hai |
| Hai cạnh song song 0–1 | Distance của 1 vẫn là 1 |
| Đồ thị có hướng 0→1 | BFS từ 1 không tới 0 |
| Lưới 3×4 trong bài | 5 bước, path như stdout |
| Lưới start=target | 0 bước |
| Lưới không có đường | -1 và path [] |
| BFS với nguồn 7 trên đồ thị 7 đỉnh | IllegalArgumentException |

**Đối chứng độc lập:** với đồ thị nhỏ, so distance của BFS từ từng source với ma trận khoảng cách được tính bằng Floyd–Warshall (khởi tạo cạnh chi phí 1, đường chéo 0, không có cạnh là vô cực). Trên lưới nhỏ, có thể duyệt mọi đường đi đơn và so số bước tối thiểu; không dùng brute force cho lưới lớn. Khi có nhiều path ngắn nhất, chỉ kiểm tra **độ dài và tính hợp lệ**, không ép một parent/path duy nhất nếu đề không quy định thứ tự láng giềng.

## 17. Bài tập thực hành

1. Tự dựng danh sách kề và mô phỏng queue từng bước trên đồ thị mẫu. Nêu các lớp, distance và parent. Tại sao đỉnh 3 không được enqueue hai lần?
2. Đảo thứ tự hai cạnh (0,1) và (0,2). Theo đó thứ tự dequeue và parent[3] thay đổi thế nào? Vì sao khoảng cách tối ưu giữ nguyên?
3. Chuyển các cạnh mẫu thành **cạnh có hướng** u→v. Chạy BFS từ 0 và từ 5, so sánh reachable; không gọi kết quả là SCC.
4. Viết hàm trả danh sách các đỉnh theo **từng lớp** dưới dạng List<List<Integer>>, dựa trên distance hoặc kích thước queue ở đầu mỗi lượt.
5. Mở rộng đồ thị vô hướng bằng một đỉnh cô lập và một self-loop. Viết BFS có vòng ngoài để đếm component, kiểm tra mọi đỉnh được đặt đúng một nhóm.
6. Sửa multi-source BFS để lưu **nguồn sở hữu gần nhất** của mỗi đỉnh. Khi có hai nguồn cùng khoảng cách, quy định tie-breaking và kiểm thử.
7. Thêm đường đi 8 hướng trên lưới. Giải thích khi nào được đi chéo qua góc tường, và việc thay tập cạnh có thể đổi số bước tối ưu.
8. Tạo một mê cung có chìa khóa và cửa. Chứng minh vì sao visited[row][col] thiếu thông tin; thiết kế visited[row][col][hasKey].
9. Đếm số đường ngắn nhất từ đỉnh 0 tới 3 trong đồ thị hình thoi 0→1,0→2,1→3,2→3. Viết biến ways[] và giải thích xử lý cạnh song song.
10. Dùng BFS tô màu để xác định đồ thị chu trình 3 đỉnh và chu trình 4 đỉnh có hai phía không.
11. So sánh BFS với Dijkstra trên đồ thị có cạnh trực tiếp chi phí 100 và đường hai cạnh chi phí 1+1. Phân biệt tối ưu số cạnh và tổng trọng số.
12. Với một nguồn và 100 truy vấn đích, phân tích lợi ích của chạy một BFS rồi truy xuất distance/path so với chạy BFS 100 lần.
13. Viết bộ test ngẫu nhiên trên đồ thị nhỏ để so BFS từ mọi nguồn với Floyd–Warshall; kiểm tra cả đồ thị có hướng và vô hướng.
14. Đếm số lần enqueue và dequeue trên đồ thị có nhiều cạnh song song. Chứng minh mỗi số không vượt lượng đỉnh reachable nếu mark on enqueue.
15. Mở rộng state lưới bằng 10 bit chìa khóa. Ước lượng số state tiềm năng R×C×2^10 và bộ nhớ queue/visited.
16. Nếu yêu cầu xuất **tất cả đường ngắn nhất**, thiết kế cách lưu nhiều cha hợp lệ và thảo luận chi phí xuất kết quả có thể tăng rất nhanh.

**Kết luận:** BFS duyệt bằng **queue FIFO**, đánh dấu đỉnh ngay khi enqueue và khám phá các lớp khoảng cách không giảm. Với đồ thị không trọng số, lần phát hiện đầu cho khoảng cách ít cạnh nhất; parent giúp dựng một đường đi ngắn nhất. Muốn duyệt cả đồ thị vô hướng phải xét các thành phần, còn muốn tìm nguồn gần nhất phải seed nhiều nguồn đồng thời. Khi cạnh có trọng số hoặc trạng thái phụ thuộc lịch sử, phải chọn mô hình trạng thái và thuật toán phù hợp.

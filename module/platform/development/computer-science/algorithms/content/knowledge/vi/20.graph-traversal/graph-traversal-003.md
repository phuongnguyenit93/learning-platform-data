# Duyệt theo chiều sâu (DFS)

**Duyệt theo chiều sâu** (*Depth-First Search – DFS*) là một kỹ thuật khám phá đồ thị bằng cách **đi tiếp theo một nhánh sâu nhất có thể**, rồi **quay lui** khi không còn đỉnh kề chưa được thăm. DFS có thể viết tự nhiên bằng **đệ quy** hoặc cài bằng **stack tường minh**. Khi biểu diễn đồ thị bằng danh sách kề, một lượt DFS trên toàn đồ thị có thời gian **O(V+E)**, với V là số đỉnh và E là số cạnh.

DFS là nền tảng cho nhiều bài toán: kiểm tra một đỉnh có tới được từ nguồn hay không, tìm **một đường đi**, phân chia thành phần liên thông của **đồ thị vô hướng**, phát hiện **chu trình có hướng**, tạo thứ tự tô-pô trên DAG, phân loại cạnh, và các thuật toán nâng cao như tìm thành phần liên thông mạnh, cầu và đỉnh khớp. Tuy nhiên **DFS không tự bảo đảm đường đi ít cạnh nhất** trên đồ thị không trọng số; đó thường là vai trò của BFS.

Bài học tập trung vào cơ chế chọn đỉnh, đánh dấu đã thăm, lúc khám phá/lúc hoàn tất, cách quản lý stack, chứng minh tính đúng, xử lý đồ thị không liên thông, và những điểm rất dễ sai khi đổi giữa đồ thị vô hướng và có hướng. Phần thực hành là một chương trình **Java 17+** có thể chạy độc lập, minh họa DFS đệ quy, DFS lặp giữ đúng thứ tự đệ quy, truy vết đường đi, thành phần liên thông vô hướng, phát hiện chu trình có hướng và thứ tự tô-pô.

## 1. DFS đang duyệt cái gì?

Cho đồ thị \(G=(V,E)\). Một **đỉnh** là một trạng thái/vị trí; một **cạnh** cho biết có thể đi từ đỉnh này tới đỉnh khác.

- **Đồ thị vô hướng:** cạnh \(\{u,v\}\) cho phép đi từ u tới v và ngược lại.
- **Đồ thị có hướng:** cạnh \(u\to v\) chỉ bảo đảm có thể đi từ u tới v. Không được tự đi ngược nếu không tồn tại cạnh \(v\to u\).
- **Danh sách kề:** `adj[u]` lưu các đỉnh v có cạnh đi từ u tới v. Với đồ thị vô hướng, mỗi cạnh thường được thêm vào danh sách kề của **cả hai đầu mút**.
- **Đỉnh đã thăm:** `visited[u]` cho biết thuật toán đã **khám phá** u hay chưa, nhằm tránh xử lý lặp và chặn vòng lặp vô hạn trên đồ thị có chu trình.

Xét đồ thị có hướng:

~~~text
0 -> 1 -> 3 -> 4
|              ^
+----> 2 ------+
|
+----------> 4

5 -> 6
~~~

Các cạnh chính xác là:

~~~text
0 -> 1
0 -> 2
0 -> 4
1 -> 3
2 -> 3
3 -> 4
5 -> 6
~~~

Nếu khám phá các đỉnh kề theo **thứ tự xuất hiện trong danh sách kề**, DFS từ 0 lần lượt tìm thấy:

~~~text
0, 1, 3, 4, 2
~~~

Diễn biến: từ 0 sang 1, từ 1 sang 3, từ 3 sang 4; đỉnh 4 hết lối đi mới, quay về 3, 1, 0; sau đó xét cạnh 0→2. Đỉnh 2 có cạnh 2→3 nhưng 3 **đã thăm**, nên không đi sâu lại.

Các đỉnh **5 và 6 không thể tới từ 0**, vì không có đường đi theo hướng cạnh từ thành phần chứa 0 tới chúng. DFS bắt đầu ở 0 **không tự đi thăm mọi đỉnh của đồ thị**.

### Một thứ tự DFS có duy nhất không?

**Không.** Thứ tự khám phá phụ thuộc vào **thứ tự liệt kê các đỉnh kề**. Nếu `adj[0]` bắt đầu bằng 2 thay vì 1, DFS từ 0 có thể khám phá 2 và 3 trước 1. Nhiều thứ tự hợp lệ cùng mô tả DFS trên một đồ thị.

Vì vậy khi đề yêu cầu một **thứ tự cụ thể**, phải công bố cách duyệt neighbor (theo thứ tự đầu vào, tăng dần, giảm dần...). Mã Java trong bài **giữ nguyên thứ tự các cạnh được thêm** vào danh sách kề; không âm thầm sắp xếp lại.

## 2. Ý tưởng DFS đệ quy

Khi DFS đang ở u:

1. **Đánh dấu u đã thăm ngay khi khám phá**.
2. Xử lý công việc tại u, chẳng hạn ghi u vào thứ tự duyệt.
3. Xét lần lượt các v trong `adj[u]`.
4. Nếu v chưa thăm, gọi đệ quy DFS(v).
5. Khi tất cả neighbor đã xét xong, **trả về** cho lời gọi cha.

Mã giả:

~~~text
dfs(u):
    visited[u] = true
    discoveryOrder.append(u)

    for v in adj[u]:
        if not visited[v]:
            parent[v] = u       // nếu cần khôi phục đường đi
            dfs(v)
~~~

Để duyệt **mọi đỉnh**, kể cả những đỉnh không tới được từ một nguồn duy nhất:

~~~text
for u = 0 .. V-1:
    if not visited[u]:
        dfs(u)
~~~

Vòng lặp ngoài tạo nên một **rừng DFS** (*DFS forest*): mỗi lần tìm thấy một đỉnh chưa thăm, ta bắt đầu một cây DFS mới. Riêng ở **đồ thị có hướng**, số cây trong rừng DFS **không nhất thiết** bằng số thành phần liên thông yếu hay thành phần liên thông mạnh; không được dùng nó như thuật toán đếm SCC.

### Vì sao đánh dấu ngay khi thăm?

Với chu trình `0→1→2→0`, nếu DFS không kiểm tra/đánh dấu, nó có thể gọi liên tiếp 0→1→2→0→... mà không dừng. Đánh dấu **trước khi duyệt hàng xóm** bảo đảm không một đỉnh nào bị mở đệ quy thành một lời gọi mới nhiều hơn một lần.

Ở DFS đệ quy, trạng thái của lời gọi (đỉnh hiện tại, vị trí neighbor đang xét, nơi quay về) được lưu trong **call stack** của Java. Vì vậy ta không tự viết thao tác push/pop nhưng thuật toán vẫn hoạt động theo nguyên tắc ngăn xếp **LIFO – Last In, First Out**.

## 3. Khám phá và hoàn tất: hai thời điểm khác nhau

Một đỉnh u có hai sự kiện quan trọng:

- **Khám phá** (*discovery / entry*): u vừa được thăm lần đầu, trước khi đi sâu vào con DFS.
- **Hoàn tất** (*finish / exit*): toàn bộ neighbor có thể khám phá từ u đã được xử lý, lời gọi tại u chuẩn bị trả về.

Nếu cần ghi thời gian logic, ta có thể dùng một bộ đếm tăng ở mỗi sự kiện:

~~~text
enter[u] = ++timer
... xử lý các neighbor ...
exit[u] = ++timer
~~~

Ví dụ một phần cây DFS:

~~~text
0
|
1
|
3
|
4
~~~

Thứ tự khám phá dọc chuỗi có thể là `0,1,3,4` nhưng thứ tự hoàn tất lại là `4,3,1,0`. Trực giác “vào trước, ra sau” chính là tính chất stack.

**Thứ tự khám phá** hữu ích cho liệt kê đỉnh, truy vết cây DFS. **Thứ tự hoàn tất** đặc biệt hữu ích cho sắp xếp tô-pô và nhiều thuật toán đồ thị nâng cao. Không được lấy thứ tự khám phá rồi mặc nhiên coi đó là thứ tự tô-pô: trên đồ thị có hướng, các cạnh nối chéo có thể làm thứ tự khám phá không thỏa điều kiện mọi cạnh đi từ trước tới sau.

### Trạng thái trắng–xám–đen

Khi chỉ cần reachability, mảng `visited` dạng boolean thường đủ. Khi cần phân biệt đỉnh **đang ở trên stack đệ quy** với đỉnh đã xử lý xong, dùng ba màu:

| Màu | Giá trị minh họa | Ý nghĩa |
|---|---:|---|
| **Trắng – WHITE** | 0 | Chưa khám phá |
| **Xám – GRAY** | 1 | Đã khám phá, đang xử lý; **chưa hoàn tất** |
| **Đen – BLACK** | 2 | Đã hoàn tất toàn bộ neighbor |

Khi DFS bắt đầu ở u: `color[u]=GRAY`. Khi toàn bộ neighbor đã được xét: `color[u]=BLACK`.

Đối với **đồ thị có hướng**, gặp cạnh \(u\to v\) với **v đang GRAY** là một **cạnh ngược (back edge)** vào một tổ tiên trên stack DFS, do đó tồn tại **chu trình có hướng**. Gặp v BLACK thì không tự kết luận có chu trình; v đã hoàn tất từ trước.

**Cẩn thận với đồ thị vô hướng:** cạnh dẫn ngược về **cha DFS** là bình thường, vì một cạnh vô hướng được biểu diễn ở cả hai danh sách kề. Nếu áp nguyên quy tắc “thấy GRAY là chu trình” vào đồ thị vô hướng, ngay cạnh `0—1` cũng có thể bị nhận nhầm là chu trình. Với đồ thị vô hướng đơn, cần bỏ qua **cạnh về cha**, còn cạnh tới đỉnh đã thăm khác cha báo chu trình. Nếu có **cạnh song song**, cần phân biệt **ID cạnh** khi bỏ qua cạnh cha, không chỉ bỏ qua mọi cạnh về cùng một đỉnh.

## 4. DFS dùng stack tường minh

DFS đệ quy dễ hiểu, nhưng trên một đường dài có hàng chục nghìn hoặc hàng trăm nghìn đỉnh, **độ sâu đệ quy lớn** có thể gây `StackOverflowError` trong Java. Một phương án khác là dùng `ArrayDeque` làm stack.

Cách đơn giản thường gặp:

~~~text
stack.push(start)
while stack chưa rỗng:
    u = stack.pop()
    if visited[u]: continue
    visited[u] = true
    for v in adj[u]:
        if not visited[v]:
            stack.push(v)
~~~

Cách này vẫn có thể tạo một **DFS hợp lệ**. Tuy nhiên vì stack là LIFO, các neighbor được push theo thứ tự 1,2,3 sẽ thường được pop theo thứ tự **3,2,1**. Mỗi đỉnh cũng có thể bị đưa vào stack **nhiều lần** trước khi được đánh dấu lúc pop; số mục chờ có thể tăng theo số cạnh trong một số đồ thị.

Một cách khác là **đánh dấu khi push** và push neighbor theo thứ tự đảo, nhưng trên đồ thị có các cạnh chéo, các đỉnh có thể bị đánh dấu quá sớm và làm thứ tự khám phá khác DFS đệ quy. **Đảo neighbor thôi chưa bảo đảm** kết quả giống hoàn toàn đệ quy với mọi đồ thị.

### Mô phỏng chính xác khung đệ quy bằng frame

Muốn DFS lặp có **cùng thứ tự khám phá như DFS đệ quy**, ta lưu một **frame** cho mỗi lời gọi đang hoạt động:

~~~text
Frame:
    vertex      // đỉnh hiện tại
    nextIndex   // neighbor tiếp theo chưa xét

mark start visited
record start
push Frame(start, 0)

while stack chưa rỗng:
    f = stack.peek()
    if f.nextIndex == adj[f.vertex].size:
        stack.pop()    // đỉnh hoàn tất
        continue

    v = adj[f.vertex][f.nextIndex]
    f.nextIndex++

    if not visited[v]:
        visited[v] = true
        record v
        stack.push(Frame(v, 0))
~~~

Frame của u **vẫn nằm trên stack** khi DFS đi vào v; khi v hoàn tất và pop, ta quay lại đúng vị trí neighbor tiếp theo của u. Đây là điều mà lời gọi đệ quy Java làm tự động.

Ưu điểm của frame:

- Đỉnh được **đánh dấu ngay khi khám phá**.
- Mỗi đỉnh tạo **tối đa một frame**.
- Cạnh kề của mỗi đỉnh được đọc **đúng một lần**.
- Thứ tự khám phá khớp DFS đệ quy nếu cả hai dùng cùng thứ tự neighbor.
- Stack chủ động có kích thước O(V) và không phụ thuộc ngưỡng call stack đệ quy của JVM.

Bản Java phía dưới sử dụng phương án frame này.

## 5. Tìm một đường đi bằng cây cha DFS

Khi lần đầu khám phá v từ u, đặt:

\[
parent[v]=u.
\]

Mỗi đỉnh được khám phá (trừ nguồn s) có một **cha DFS**. Sau khi duyệt từ s, nếu đích t đã thăm, có thể lần theo:

~~~text
t -> parent[t] -> parent[parent[t]] -> ... -> s
~~~

rồi đảo ngược để nhận một đường đi **từ s tới t**, với cạnh đi theo đúng hướng đồ thị.

Với đồ thị minh họa, nếu duyệt neighbor theo thứ tự đầu vào:

~~~text
DFS path 0 -> 4 = [0, 1, 3, 4]
~~~

Nhưng đồ thị **có cạnh trực tiếp 0→4**, nên đường đi ngắn nhất theo **số cạnh** là `[0,4]`, chỉ dài 1 cạnh. Đường DFS tìm thấy dài 3 cạnh; nó là **một đường đi hợp lệ**, **không phải** đường ngắn nhất.

Để tìm đường ngắn nhất theo số cạnh trên **đồ thị không trọng số**, nên dùng **BFS**, vì BFS khám phá theo khoảng cách số cạnh tăng dần. Nếu đồ thị có trọng số, cần xét loại trọng số và thuật toán thích hợp (Dijkstra khi trọng số không âm, Bellman–Ford cho một số trường hợp có âm, DP tô-pô trên DAG...), không thể chỉ dùng DFS.

### Trường hợp không tới được

Nếu từ s không đi tới t, `visited[t]=false`. Hàm tìm một đường đi có thể trả **danh sách rỗng**, nhưng cần phân biệt rõ với trường hợp `s==t`: khi ấy đường đi độ dài 0 vẫn có thể được biểu diễn bởi danh sách chỉ chứa `s`.

Không được lần theo `parent[t]` ở đỉnh chưa từng khám phá mà coi một số mặc định nào đó là một đường đi. Ví dụ mã dùng `-1` làm ký hiệu **không có cha** và chỉ dựng đường đi khi `visited[target]` là true.

## 6. Duyệt một thành phần hay toàn bộ đồ thị?

Nếu đề hỏi “những đỉnh nào tới được từ nguồn s?”, chỉ cần **một DFS(s)**. Nếu hỏi một tính chất của **toàn bộ đồ thị**, cần lặp qua mọi đỉnh và gọi DFS tại các đỉnh chưa thăm.

### Thành phần liên thông của đồ thị vô hướng

Một **thành phần liên thông** (*connected component*) trong đồ thị vô hướng là tập đỉnh lớn nhất mà mọi cặp đỉnh đều có đường đi nối nhau.

Ví dụ:

~~~text
0 -- 1 -- 2       3 -- 4 -- 5        6
~~~

Có ba thành phần:

~~~text
[0,1,2]
[3,4,5]
[6]
~~~

Thuật toán:

~~~text
visited[*] = false
components = []

for u = 0 .. V-1:
    if not visited[u]:
        component = []
        dfsCollect(u, component)
        components.add(component)
~~~

Mỗi lần DFS bắt đầu ở một đỉnh chưa thăm, nó khám phá **toàn bộ thành phần liên thông vô hướng** chứa đỉnh đó và không sang được thành phần khác. Đếm số lần bắt đầu DFS chính là đếm số thành phần.

### Đồ thị có hướng: ba khái niệm không được đánh đồng

- **Reachability từ s:** những v có đường có hướng từ s tới v.
- **Thành phần liên thông yếu:** coi các cạnh có hướng như vô hướng rồi tìm thành phần liên thông.
- **Thành phần liên thông mạnh (SCC):** hai đỉnh u,v cùng thành phần nếu có **đường có hướng u→v và v→u**.

Ví dụ chỉ có cạnh `0→1`: DFS từ 0 thăm cả 0 và 1, nhưng DFS từ 1 không thăm 0. Đây là một **thành phần liên thông yếu** gồm cả hai đỉnh, nhưng có **hai SCC riêng**.

Không thể lấy số cây trong một rừng DFS tùy ý của đồ thị có hướng để kết luận số SCC. Muốn tìm SCC có thể dùng **Kosaraju** hoặc **Tarjan** (đều dựa trên DFS với thông tin bổ sung), chứ không chỉ lặp DFS đơn giản.

## 7. Phát hiện chu trình có hướng bằng DFS ba màu

Cho đồ thị có hướng. Dùng mảng `color[u]` với ba trạng thái:

~~~text
WHITE = chưa khám phá
GRAY  = đang trong stack
BLACK = đã hoàn tất
~~~

Mã giả:

~~~text
cycleDfs(u):
    color[u] = GRAY
    for v in adj[u]:
        if color[v] == GRAY:
            return true          // có cạnh ngược -> chu trình
        if color[v] == WHITE and cycleDfs(v):
            return true
    color[u] = BLACK
    return false

for u in 0 .. V-1:
    if color[u] == WHITE and cycleDfs(u):
        return true
return false
~~~

Nếu gặp cạnh \(u\to v\) với v GRAY, v là tổ tiên đang hoạt động của u trong cây DFS. Đường đi trong cây từ v tới u, cộng cạnh u→v, tạo thành một chu trình có hướng. Ngược lại, một chu trình có hướng phải tạo ít nhất một cạnh ngược trong một lượt DFS toàn đồ thị, nên thuật toán phát hiện được.

**Đừng chỉ dùng `visited[v]` để phát hiện chu trình có hướng.** Gặp một đỉnh đã thăm **BLACK** không chứng minh có chu trình. Ví dụ DAG `0→1`, `0→2`, `1→3`, `2→3`: khi đi từ 2 tới 3, có thể thấy 3 đã thăm, nhưng không có chu trình nào.

Nếu muốn **phát hiện chu trình vô hướng**, thay bằng logic riêng theo cha/cạnh cha như ở phần 3. Không tái sử dụng nguyên hàm ba màu cho đồ thị vô hướng.

## 8. Thứ tự tô-pô từ thời điểm hoàn tất

Với **DAG** – đồ thị có hướng không chu trình – một **thứ tự tô-pô** là dãy đỉnh sao cho với mọi cạnh \(u\to v\), u xuất hiện **trước** v.

DFS có thể tạo thứ tự này bằng cách:

1. Duyệt toàn bộ các đỉnh (khởi động DFS từ mọi đỉnh chưa thăm).
2. **Chỉ thêm u vào `finishOrder` sau khi đã duyệt xong mọi neighbor của u**.
3. Nếu gặp cạnh tới đỉnh GRAY, báo đồ thị **có chu trình**, không tạo thứ tự tô-pô hợp lệ.
4. Đảo ngược `finishOrder` để được thứ tự tô-pô.

~~~text
topoDfs(u):
    color[u] = GRAY

    for v in adj[u]:
        if color[v] == GRAY:
            báo lỗi: có chu trình
        if color[v] == WHITE:
            topoDfs(v)

    color[u] = BLACK
    finishOrder.append(u)

for mọi đỉnh u chưa thăm:
    topoDfs(u)
reverse(finishOrder)
return finishOrder
~~~

### Vì sao đảo finish order lại đúng?

Với mọi cạnh \(u\to v\) trên một DAG:

- Nếu DFS từ u đi vào v chưa thăm, v **phải hoàn tất trước u** vì là hậu duệ trong cây DFS.
- Nếu v đã hoàn tất trước khi cạnh u→v được xét, v cũng **hoàn tất trước u**.
- Trường hợp v đang GRAY sẽ tạo chu trình và **không thể xảy ra trong DAG**.

Vì vậy trên DAG, thời điểm hoàn tất của u luôn **sau** thời điểm hoàn tất của v đối với cạnh u→v. Đảo danh sách hoàn tất đặt u **trước** v, thỏa yêu cầu tô-pô.

Trong đồ thị 7 đỉnh phần đầu, một thứ tự tô-pô do mã Java sinh ra là:

~~~text
[5, 6, 0, 2, 1, 3, 4]
~~~

Thứ tự này hợp lệ dù 5 và 6 không tới được từ nguồn 0: thuật toán tô-pô phải xét **toàn bộ đỉnh**. Các thứ tự tô-pô khác có thể cũng đúng. Một đồ thị có hướng có chu trình **không có** thứ tự tô-pô của toàn bộ đồ thị; không thể chỉ đảo finish order rồi bỏ qua kiểm tra chu trình.

### Ứng dụng

Thứ tự tô-pô hữu ích khi các công việc có quan hệ **phải hoàn thành trước**, hoặc DP trên DAG yêu cầu mọi tiền nhiệm đã tính trước khi xét một đỉnh. Tùy bài, có thể dùng **Kahn** (đếm bậc vào) thay cho DFS: cả hai đều chạy O(V+E) trên danh sách kề, nhưng có cách tổ chức bộ nhớ và kiểm tra chu trình khác nhau.

## 9. Java 17+: DFS đệ quy, stack frame và các ứng dụng

Chương trình bên dưới cài đặt:

- **`buildGraph`:** xây danh sách kề cho đồ thị có hướng hoặc vô hướng; kiểm tra chỉ số đỉnh và cạnh.
- **`dfsRecursive`:** ghi thứ tự khám phá từ một nguồn.
- **`dfsIterative`:** dùng `Frame(vertex,nextIndex)` để mô phỏng lời gọi đệ quy; giữ **đúng cùng thứ tự khám phá** trên một danh sách kề.
- **`dfsPath`:** xây cây cha để trả một đường đi có hướng từ nguồn tới đích.
- **`componentsUndirected`:** gom các thành phần liên thông khi đồ thị đầu vào là **vô hướng**.
- **`hasDirectedCycle`:** phát hiện chu trình có hướng bằng DFS ba màu.
- **`topologicalOrder`:** dùng thứ tự hoàn tất đảo ngược và từ chối đồ thị có chu trình.

Chương trình không sắp neighbor tự động, vì vậy thứ tự kết quả dựa trên **thứ tự cạnh được truyền vào**; tất cả kết quả sau đây có thể tái lập với dữ liệu mẫu.

Lưu thành **DfsGraphDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class DfsGraphDemo {
    static List<List<Integer>> buildGraph(
        int vertices, int[][] edges, boolean directed
    ) {
        Objects.requireNonNull(edges, "edges");
        if (vertices < 0) {
            throw new IllegalArgumentException("negative vertex count");
        }
        List<List<Integer>> g = new ArrayList<>();
        for (int u = 0; u < vertices; u++) {
            g.add(new ArrayList<>());
        }
        for (int[] edge : edges) {
            if (edge == null || edge.length != 2 ||
                    edge[0] < 0 || edge[0] >= vertices ||
                    edge[1] < 0 || edge[1] >= vertices) {
                throw new IllegalArgumentException("invalid edge");
            }
            int u = edge[0];
            int v = edge[1];
            g.get(u).add(v);
            if (!directed && u != v) {
                g.get(v).add(u);
            }
        }
        return g;
    }

    static void checkVertex(List<List<Integer>> g, int v) {
        Objects.requireNonNull(g, "graph");
        if (v < 0 || v >= g.size()) {
            throw new IllegalArgumentException("invalid vertex");
        }
    }

    static List<Integer> dfsRecursive(
        List<List<Integer>> g, int start
    ) {
        checkVertex(g, start);
        boolean[] visited = new boolean[g.size()];
        List<Integer> order = new ArrayList<>();
        visit(start, g, visited, order);
        return List.copyOf(order);
    }

    private static void visit(
        int u, List<List<Integer>> g,
        boolean[] visited, List<Integer> order
    ) {
        visited[u] = true;
        order.add(u);
        for (int v : g.get(u)) {
            if (!visited[v]) {
                visit(v, g, visited, order);
            }
        }
    }

    // A frame is an active recursive call plus its next neighbor.
    static final class Frame {
        final int vertex;
        int nextIndex;

        Frame(int vertex) {
            this.vertex = vertex;
        }
    }

    static List<Integer> dfsIterative(
        List<List<Integer>> g, int start
    ) {
        checkVertex(g, start);
        boolean[] visited = new boolean[g.size()];
        List<Integer> order = new ArrayList<>();
        ArrayDeque<Frame> stack = new ArrayDeque<>();

        visited[start] = true;
        order.add(start);
        stack.push(new Frame(start));

        while (!stack.isEmpty()) {
            Frame f = stack.peek();
            List<Integer> next = g.get(f.vertex);
            if (f.nextIndex >= next.size()) {
                stack.pop();
                continue;
            }

            int v = next.get(f.nextIndex++);
            if (!visited[v]) {
                visited[v] = true;
                order.add(v);
                stack.push(new Frame(v));
            }
        }
        return List.copyOf(order);
    }

    static List<Integer> dfsPath(
        List<List<Integer>> g, int start, int target
    ) {
        checkVertex(g, start);
        checkVertex(g, target);
        boolean[] visited = new boolean[g.size()];
        int[] parent = new int[g.size()];
        Arrays.fill(parent, -1);
        visitWithParent(start, g, visited, parent);

        if (!visited[target]) {
            return List.of();
        }
        List<Integer> path = new ArrayList<>();
        for (int v = target; v != -1; v = parent[v]) {
            path.add(v);
        }
        Collections.reverse(path);
        return List.copyOf(path);
    }

    private static void visitWithParent(
        int u, List<List<Integer>> g,
        boolean[] visited, int[] parent
    ) {
        visited[u] = true;
        for (int v : g.get(u)) {
            if (!visited[v]) {
                parent[v] = u;
                visitWithParent(v, g, visited, parent);
            }
        }
    }

    // Use ONLY on an undirected graph.
    static List<List<Integer>> componentsUndirected(
        List<List<Integer>> g
    ) {
        Objects.requireNonNull(g, "graph");
        boolean[] visited = new boolean[g.size()];
        List<List<Integer>> components = new ArrayList<>();

        for (int u = 0; u < g.size(); u++) {
            if (!visited[u]) {
                List<Integer> component = new ArrayList<>();
                visit(u, g, visited, component);
                components.add(List.copyOf(component));
            }
        }
        return List.copyOf(components);
    }

    static boolean hasDirectedCycle(List<List<Integer>> g) {
        Objects.requireNonNull(g, "graph");
        int[] color = new int[g.size()];
        for (int u = 0; u < g.size(); u++) {
            if (color[u] == 0 && cycleVisit(u, g, color)) {
                return true;
            }
        }
        return false;
    }

    private static boolean cycleVisit(
        int u, List<List<Integer>> g, int[] color
    ) {
        color[u] = 1; // GRAY: currently on recursion stack.
        for (int v : g.get(u)) {
            if (color[v] == 1) {
                return true; // Back edge => directed cycle.
            }
            if (color[v] == 0 && cycleVisit(v, g, color)) {
                return true;
            }
        }
        color[u] = 2; // BLACK: fully processed.
        return false;
    }

    static List<Integer> topologicalOrder(List<List<Integer>> g) {
        Objects.requireNonNull(g, "graph");
        int[] color = new int[g.size()];
        List<Integer> finishOrder = new ArrayList<>();
        for (int u = 0; u < g.size(); u++) {
            if (color[u] == 0) {
                topoVisit(u, g, color, finishOrder);
            }
        }
        Collections.reverse(finishOrder);
        return List.copyOf(finishOrder);
    }

    private static void topoVisit(
        int u, List<List<Integer>> g, int[] color,
        List<Integer> finishOrder
    ) {
        color[u] = 1;
        for (int v : g.get(u)) {
            if (color[v] == 1) {
                throw new IllegalArgumentException(
                    "graph has directed cycle"
                );
            }
            if (color[v] == 0) {
                topoVisit(v, g, color, finishOrder);
            }
        }
        color[u] = 2;
        finishOrder.add(u);
    }

    public static void main(String[] args) {
        int[][] dagEdges = {
            {0, 1}, {0, 2}, {0, 4},
            {1, 3}, {2, 3}, {3, 4},
            {5, 6}
        };
        List<List<Integer>> dag = buildGraph(7, dagEdges, true);

        System.out.println("Recursive DFS from 0: "
            + dfsRecursive(dag, 0));
        System.out.println("Iterative DFS from 0: "
            + dfsIterative(dag, 0));
        System.out.println("DFS path 0 -> 4: "
            + dfsPath(dag, 0, 4));
        System.out.println("DFS path 0 -> 6: "
            + dfsPath(dag, 0, 6));
        System.out.println("Topological order: "
            + topologicalOrder(dag));
        System.out.println("Directed cycle in DAG: "
            + hasDirectedCycle(dag));

        int[][] undirectedEdges = {
            {0, 1}, {1, 2}, {3, 4}, {4, 5}
        };
        List<List<Integer>> undirected =
            buildGraph(7, undirectedEdges, false);
        System.out.println("Undirected components: "
            + componentsUndirected(undirected));

        List<List<Integer>> cyclic = buildGraph(3, new int[][] {
            {0, 1}, {1, 2}, {2, 0}
        }, true);
        System.out.println("Directed cycle in triangle: "
            + hasDirectedCycle(cyclic));
        try {
            topologicalOrder(cyclic);
        } catch (IllegalArgumentException ex) {
            System.out.println("Cycle rejected: " + ex.getMessage());
        }
    }
}
~~~

Lệnh biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac DfsGraphDemo.java
java DfsGraphDemo
~~~

**Stdout chính xác:**

~~~text
Recursive DFS from 0: [0, 1, 3, 4, 2]
Iterative DFS from 0: [0, 1, 3, 4, 2]
DFS path 0 -> 4: [0, 1, 3, 4]
DFS path 0 -> 6: []
Topological order: [5, 6, 0, 2, 1, 3, 4]
Directed cycle in DAG: false
Undirected components: [[0, 1, 2], [3, 4, 5], [6]]
Directed cycle in triangle: true
Cycle rejected: graph has directed cycle
~~~

### Phân tích thiết kế của chương trình

**Đọc cạnh có kiểm tra.** `buildGraph` từ chối số đỉnh âm, cạnh thiếu hai đầu mút hoặc chỉ số vượt `[0,V-1]`. Với `directed=false`, nó thêm cạnh ngược; self-loop vô hướng được thêm một lần vào danh sách kề của chính đỉnh. Các hàm sau giả định danh sách kề đã xây có chỉ số hợp lệ.

**Đệ quy và stack frame cho cùng thứ tự.** `dfsRecursive` đánh dấu khi bắt đầu thăm; `dfsIterative` đánh dấu khi push frame và lưu `nextIndex` cho từng lời gọi còn hoạt động. Khi frame của con kết thúc, frame của cha tiếp tục đúng neighbor chưa xét. Vì cả hai đọc cùng danh sách kề, hai danh sách khám phá trong stdout **giống nhau**.

**Đường đi có hướng, không nhất thiết ngắn nhất.** `dfsPath` chỉ đặt `parent[v]` khi lần đầu khám phá v. Với cạnh trực tiếp 0→4 có sẵn, nó vẫn trả đường `[0,1,3,4]` vì theo thứ tự neighbor, DFS đi sâu qua 1 trước. Muốn số cạnh nhỏ nhất nên dùng BFS.

**Thành phần liên thông vô hướng.** `componentsUndirected` dùng cùng DFS cơ bản nhưng khởi động từ tất cả đỉnh chưa thăm. Từ kết quả `[[0,1,2],[3,4,5],[6]]`, có **3 thành phần**; đỉnh 6 là thành phần một đỉnh. Hàm chỉ có ý nghĩa “connected components” theo cách này khi **đồ thị vô hướng**.

**Kiểm tra chu trình có hướng.** `hasDirectedCycle` dùng ba màu `0,1,2`. Với DAG, mọi cạnh trỏ tới đỉnh đã hoàn tất hoặc chưa thăm, không có cạnh dẫn về GRAY. Với vòng `0→1→2→0`, cạnh 2→0 trỏ tới GRAY nên báo true.

**Thứ tự tô-pô.** `topologicalOrder` thêm đỉnh vào danh sách **sau khi hoàn tất**, rồi đảo thứ tự. Nó đi qua tất cả 7 đỉnh, kể cả 5,6 không tới được từ 0; kết quả vẫn tôn trọng mọi cạnh. Nếu gặp chu trình, hàm ném `IllegalArgumentException` thay vì trả một danh sách tưởng hợp lệ.

**Giới hạn của đệ quy.** Ba chức năng `dfsRecursive`, `dfsPath` và phân tích chu trình/tô-pô hiện dùng lời gọi đệ quy, nên trên đồ thị rất sâu có nguy cơ `StackOverflowError`. Chỉ `dfsIterative` minh họa bản không phụ thuộc call stack. Khi dữ liệu có thể chứa chuỗi cạnh rất dài, có thể chuyển **cả** các chức năng còn lại sang frame tường minh và giữ đúng quy tắc enter/exit.

## 10. Phân tích độ phức tạp

Ký hiệu V là số đỉnh và E là số cạnh trong đồ thị (cạnh vô hướng được lưu hai lần trong danh sách kề nhưng vẫn là O(E)).

| Thao tác | Thời gian | Bộ nhớ phụ (ngoài dữ liệu đồ thị) |
|---|---:|---:|
| Tạo danh sách kề | **O(V+E)** | **O(V+E)** để chứa đồ thị |
| DFS từ một nguồn | O(V_r+E_r) | O(V) visited và tối đa O(V) stack |
| DFS toàn đồ thị | **O(V+E)** | **O(V)** visited + stack |
| DFS truy vết một đường | **O(V+E)** cận trên | **O(V)** parent, visited + stack |
| Tìm các thành phần liên thông vô hướng | **O(V+E)** | **O(V)** visited, stack; O(V) lưu kết quả |
| Phát hiện chu trình có hướng | **O(V+E)** | **O(V)** color + stack |
| Thứ tự tô-pô bằng DFS | **O(V+E)** | **O(V)** color, thứ tự, stack |

Ở dòng DFS từ nguồn, \(V_r\) là số đỉnh có thể tới từ nguồn, \(E_r\) là số cạnh **xuất phát từ các đỉnh ấy được thuật toán kiểm tra**. Nếu tính luôn chi phí cấp phát mảng `visited[V]` trong chương trình Java, tổng thời gian thực thi hàm là **O(V+V_r+E_r)**, do cần khởi tạo mảng dài V; cận O(V+E) vẫn đúng. Cách viết \(O(V_r+E_r)\) thường mô tả **công việc duyệt** sau phần khởi tạo.

**Vì sao là O(V+E)?** Mỗi đỉnh được đánh dấu khám phá tối đa một lần. Khi DFS xử lý một đỉnh u, nó xét lần lượt các mục trong `adj[u]`; trong toàn lượt, mỗi mục danh sách kề được xét một lần. Tổng số lần xét neighbor là O(E) cho đồ thị có hướng hoặc O(2E)=O(E) cho đồ thị vô hướng.

**Độ sâu đệ quy:** với đồ thị dạng đường dài V đỉnh, độ sâu có thể là O(V), nên bộ nhớ call stack O(V) và có thể vượt stack thực tế của JVM. Cài đặt lặp bằng frame sử dụng O(V) bộ nhớ tường minh, tránh lỗi giới hạn call stack ở cùng độ sâu.

**Lưu toàn bộ thứ tự/kết quả:** nếu ta ghi một danh sách có V phần tử, bản thân danh sách đầu ra cần O(V) bộ nhớ. Nếu chỉ hỏi một điều kiện boolean, có thể bỏ một số cấu trúc lưu kết quả; mảng visited vẫn cần thiết trong các bài tổng quát để không lặp vô hạn.

Lưu ý: nếu biểu diễn đồ thị bằng **ma trận kề V×V**, mỗi lần tìm neighbor có thể phải quét V cột, nên duyệt toàn đồ thị thường tốn **O(V²)** thay vì O(V+E); lợi thế O(V+E) ở đây gắn với **danh sách kề**.

## 11. DFS khác BFS ở đâu?

| Tiêu chí | DFS | BFS |
|---|---|---|
| Cấu trúc điều khiển | Stack / đệ quy | Queue |
| Cách khám phá | Đi sâu theo một nhánh, rồi quay lui | Duyệt theo số cạnh từ nguồn tăng dần |
| Một đường đi có hướng | Có thể tìm được | Có thể tìm được |
| Đường ít cạnh nhất trên đồ thị không trọng số | **Không bảo đảm** | **Bảo đảm** khi đánh dấu đúng |
| Kiểm tra reachability | Có | Có |
| Thành phần liên thông vô hướng | Có | Có |
| Phát hiện chu trình có hướng bằng GRAY/BACK | Phù hợp | Cần cách tổ chức khác |
| Sắp topo bằng reverse finish | Phù hợp trên DAG | Có thể dùng phương pháp khác như Kahn với queue |
| Độ phức tạp danh sách kề | O(V+E) | O(V+E) |

Không có câu trả lời “DFS luôn tốt hơn BFS”. Chọn theo đại lượng cần tìm: DFS phù hợp cấu trúc **quan hệ tổ tiên–hậu duệ, vào/ra, quay lui**; BFS phù hợp khi cần **khoảng cách ít cạnh nhất** hoặc tìm theo lớp.

Trong bài có trọng số, cả DFS lẫn BFS đơn giản có thể không giải đúng bài đường đi ngắn nhất theo tổng trọng số; cần thuật toán phù hợp với trọng số và tính chất đồ thị.

## 12. Trường hợp biên và những giả định cần chốt

| Tình huống | Kết quả/xử lý đúng |
|---|---|
| Đồ thị không đỉnh, V=0 | Duyệt mọi thành phần có thể trả danh sách rỗng; không có đỉnh nguồn hợp lệ cho DFS(s) |
| Một đỉnh không cạnh | DFS từ đỉnh đó trả một phần tử; topo cũng có một phần tử |
| Đỉnh cô lập trong đồ thị nhiều đỉnh | DFS từ nguồn khác không tới được; là một thành phần vô hướng riêng |
| Đồ thị vô hướng có một cạnh | Có đường đi hai chiều nhưng **không phải chu trình** chỉ vì cạnh được lưu hai lượt |
| Cạnh tự nối u→u (directed self-loop) | Có chu trình có hướng |
| Đồ thị có hướng chỉ chứa cạnh 0→1 | 0 tới được 1; 1 không chắc tới được 0; có thể là hai SCC |
| DAG có nhiều cạnh hội tụ vào cùng một v | v chỉ khám phá một lần; không có chu trình chỉ vì nhiều cha |
| Đồ thị có nhiều cạnh trùng u→v | Reachability và topo vẫn có nghĩa; thứ tự neighbor có thể lặp nhưng visited tránh mở lại v |
| Nguồn bằng đích | Đường đi độ dài 0 `[source]` hợp lệ |
| Đích không tới được | Trả `[]`; không dựng parent từ giá trị chưa xác định |
| Thứ tự neighbor khác | Thứ tự khám phá/parent có thể khác; tính reachability giữ nguyên |
| Chuỗi cạnh rất dài | Đệ quy Java có thể tràn stack; ưu tiên DFS lặp |
| Đồ thị có hướng có chu trình | Không có topo cho toàn đồ thị; phải từ chối hoặc đổi yêu cầu |
| Dữ liệu chứa ID ngoài `0..V-1` | Phải kiểm tra hoặc ánh xạ nhãn sang ID hợp lệ |

**Đỉnh cô lập là trường hợp dễ bị bỏ sót** khi code chỉ bắt đầu từ những đỉnh có xuất hiện trong danh sách cạnh. Ví dụ đồ thị có V=7 nhưng danh sách cạnh không nhắc tới đỉnh 6: nếu cần tính tất cả thành phần hoặc thứ tự topo, vẫn phải chứa đỉnh 6 trong cấu trúc đồ thị và vòng lặp ngoài.

### Đồ thị vô hướng có cạnh song song

Trong một **multigraph** vô hướng, hai cạnh độc lập nối cùng một cặp u,v có thể tạo chu trình độ dài 2 theo định nghĩa chu trình cho phép phân biệt **cạnh**. Nếu phát hiện chu trình bằng DFS, cách chỉ bỏ qua mọi lần gặp `v==parent[u]` sẽ bỏ qua cả **cạnh thứ hai về cha**, dẫn đến không nhận ra chu trình này.

Nếu đề cho phép multigraph và cần xử lý chu trình/cầu/đỉnh khớp, nên gán **ID cạnh** khi xây danh sách kề và chỉ bỏ qua **chính cạnh cây đã đưa đến u**; không bỏ mọi cạnh có cùng đỉnh kề. Mã Java hiện dùng ba màu chỉ cho **đồ thị có hướng**, tránh tình huống lẫn lộn này.

## 13. Lỗi thường gặp

1. **Không đánh dấu visited trước khi đệ quy**, khiến đồ thị có chu trình gọi lặp không dừng.
2. **Không kiểm tra visited khi duyệt neighbor**, xử lý một đỉnh nhiều lần và có thể tràn stack.
3. **Chỉ gọi DFS từ đỉnh 0** rồi kết luận đã duyệt toàn đồ thị, bỏ các thành phần không tới được.
4. **Đồng nhất reachability có hướng với thành phần liên thông vô hướng**, làm sai khi cạnh không có chiều ngược.
5. **Dùng số cây DFS để đếm SCC**, trong khi đồ thị có hướng có các đỉnh chỉ tới được một chiều.
6. **Dùng `visited` boolean để kết luận chu trình có hướng**, nhầm cạnh tới một đỉnh hoàn tất với cạnh ngược.
7. **Dùng phát hiện chu trình ba màu cho đồ thị vô hướng mà không xử lý cạnh về cha**.
8. **Đảo danh sách khám phá để làm topo**, thay vì đảo danh sách **hoàn tất** và kiểm tra đồ thị không có chu trình.
9. **Thử topo cho đồ thị có chu trình** mà không báo lỗi.
10. **Dùng DFS để tìm đường ít cạnh nhất**, mặc dù DFS có thể đi đường vòng dài trước cạnh trực tiếp.
11. **Xây `parent[v]` ở mọi lần gặp v**, thay vì khi v **mới được khám phá**, có thể phá cây cha và gây vòng lặp khi truy vết.
12. **Không kiểm tra đích đã thăm** trước khi lần theo parent ở đỉnh không tới được.
13. **Nhầm stack LIFO với queue FIFO** hoặc dùng `ArrayDeque` ở đầu sai, làm kết quả thành BFS/khác thứ tự mong muốn.
14. **Push neighbor cùng thứ tự rồi yêu cầu thứ tự y hệt DFS đệ quy**, quên rằng stack đảo thứ tự pop.
15. **Đánh dấu mọi neighbor ngay khi push ở bản stack đơn giản** mà tưởng thứ tự luôn giống đệ quy, kể cả đồ thị có cạnh chéo.
16. **Không reset visited giữa hai yêu cầu DFS độc lập**, khiến lượt sau thấy các đỉnh “đã thăm” của lượt trước.
17. **Bỏ đỉnh cô lập khỏi đồ thị** do chỉ tạo danh sách kề cho những ID xuất hiện trong cạnh.
18. **Tự sắp xếp neighbor mà không công bố**, dẫn tới stdout khác đặc tả thứ tự duyệt.
19. **Không để ý giới hạn đệ quy Java**, lỗi StackOverflowError trên đường dài.
20. **Cho rằng thời gian O(V+E) với mọi biểu diễn**, quên rằng ma trận kề có thể khiến quét neighbor O(V) mỗi đỉnh.
21. **Đồng nhất cạnh song song với một cạnh** trong các bài cần phân biệt ID cạnh, làm sai phân tích chu trình/cầu.
22. **Tính thời gian chỉ theo số đỉnh**, bỏ qua tổng số cạnh phải duyệt.

## 14. Khi nào mở rộng DFS lên thuật toán khác?

DFS cơ bản chỉ đánh dấu, ghi thứ tự, duyệt và quay lại. Nhiều thuật toán thêm đúng một vài biến:

- **Chu trình có hướng:** thêm màu WHITE/GRAY/BLACK, tìm cạnh về GRAY.
- **Tô-pô trên DAG:** ghi vào kết quả tại **thời điểm hoàn tất**, sau đó đảo thứ tự và từ chối chu trình.
- **Cầu và đỉnh khớp trong đồ thị vô hướng:** thêm thời điểm khám phá `tin[u]` và giá trị `low[u]`, phân biệt cạnh cây/cạnh ngược, kiểm tra điều kiện cắt kết nối; cần đặc biệt cẩn thận với cạnh song song.
- **SCC:** Kosaraju dùng thứ tự hoàn tất DFS và đồ thị chuyển vị; Tarjan giữ chỉ số khám phá/lowlink cùng một stack thành phần. Đây là bài toán nâng cao, không thể thay chỉ bằng visited boolean.
- **Tìm đường và truy vết:** thêm `parent[v]` cho đỉnh vừa khám phá; chỉ trả một đường đi, không bảo đảm tối ưu.
- **Đồ thị trạng thái của bài toán khác:** nếu mỗi cấu hình là một đỉnh, DFS kiểm tra khả năng tới được; phải thiết kế cách đánh dấu trạng thái để tránh lặp.

Những mở rộng này dùng chung cơ chế **đi sâu rồi hoàn tất**, nhưng mỗi bài có **bất biến và điều kiện đúng riêng**. Không nên sao chép mẫu DFS rồi bỏ qua ý nghĩa của `low`, `color`, `parent` hoặc thời điểm hoàn tất.

## 15. Quy trình giải bài DFS mới

1. **Đọc đặc tả đồ thị:** có hướng hay vô hướng, đơn hay đa cạnh, có self-loop không, nhãn đỉnh từ đâu đến đâu?
2. **Chọn biểu diễn:** danh sách kề thường hiệu quả với đồ thị thưa và cho O(V+E); cần quyết định thứ tự neighbor.
3. **Xác định phạm vi:** chỉ từ nguồn s hay tất cả đỉnh? Trường hợp đỉnh cô lập có được xét không?
4. **Xác định kết quả cần thu:** reachability, thứ tự khám phá, đường đi, thành phần, chu trình, topo... mỗi bài cần trạng thái riêng.
5. **Chọn DFS đệ quy hay lặp:** tính tới chiều sâu tối đa và giới hạn stack JVM.
6. **Phát biểu bất biến visited:** chỉ đánh dấu một lần tại sự kiện khám phá; mọi neighbor được xem xét theo đúng hướng cạnh.
7. **Nếu cần parent:** chỉ gán khi gặp một đỉnh chưa thăm, giữ nguyên cho đến khi truy vết.
8. **Nếu cần finish/color:** ghi sự kiện đúng lúc, phân biệt GRAY và BLACK trong đồ thị có hướng.
9. **Nếu cần trả một đường:** kiểm tra đích tới được và đảo chuỗi parent; không gắn nhãn “ngắn nhất” khi dùng DFS.
10. **Kiểm thử đồ thị có chu trình, nhiều thành phần, đỉnh cô lập, cạnh tự nối và nhiều cạnh hội tụ**.
11. **So sánh đầu ra với một oracle nhỏ:** kiểm tra mỗi đỉnh khám phá một lần, mọi cạnh của đường đã trả thật sự tồn tại, thứ tự topo tôn trọng mọi cạnh.
12. **Đếm chi phí trên V và E**, kể cả biểu diễn đồ thị, mảng visited, stack và danh sách kết quả.

## 16. Bài tập tự kiểm tra

**Bài 1 — Thứ tự DFS.** Với các cạnh `0→1`, `0→2`, `1→3`, `2→3` và danh sách kề `adj[0]=[1,2]`, DFS đệ quy từ 0 khám phá theo thứ tự nào?

*Đáp án:* **[0,1,3,2]**. Từ 0 đi vào 1 trước, tới 3; khi quay lại 0 mới xét 2. Cạnh 2→3 không tạo lần khám phá 3 thứ hai.

**Bài 2 — Đường đi không tối ưu.** Trong ví dụ chính có cạnh trực tiếp 0→4. Vì sao `dfsPath(0,4)` vẫn có thể trả `[0,1,3,4]`?

*Đáp án:* Vì DFS thăm neighbor 1 trước neighbor 4, nên 4 được khám phá lần đầu qua 1→3. Parent lưu đường theo cây khám phá, không tối ưu hóa số cạnh.

**Bài 3 — Đồ thị không liên thông.** Nếu DFS từ 0 chỉ thăm 5 trong 7 đỉnh, muốn phân tích toàn đồ thị phải làm gì?

*Đáp án:* Duyệt mọi u từ 0 tới V-1; ở mỗi u **chưa thăm**, khởi động DFS mới. Riêng với đồ thị có hướng, số cây DFS không nhất thiết là số SCC.

**Bài 4 — GRAY và BLACK.** Trong đồ thị có hướng, cạnh tới v GRAY và cạnh tới v BLACK khác nhau thế nào khi tìm chu trình?

*Đáp án:* Cạnh tới **GRAY** quay về tổ tiên đang hoạt động, xác nhận chu trình có hướng. Cạnh tới **BLACK** chỉ tới một đỉnh hoàn tất; không đủ để kết luận có chu trình.

**Bài 5 — Topological sort.** Có thể lấy danh sách khám phá rồi đảo để tạo topo không? Cần dùng danh sách nào?

*Đáp án:* **Không nói chung.** Phải dùng **danh sách hoàn tất** (đỉnh được ghi khi toàn bộ neighbor đã xử lý), đảo danh sách đó; nếu gặp chu trình thì không có topo hợp lệ.

**Bài 6 — Stack lặp.** Vì sao push các neighbor 1,2,3 rồi pop bằng stack có thể đưa ra thứ tự 3,2,1?

*Đáp án:* Stack theo **LIFO**, đỉnh push sau được pop trước. Muốn khớp DFS đệ quy chắc chắn cả trên đồ thị có cạnh chéo, dùng frame ghi **neighbor tiếp theo** như mã Java, thay vì chỉ đảo thứ tự push.

**Bài 7 — Thành phần vô hướng.** Đồ thị gồm cạnh 0—1, 1—2, 3—4 và đỉnh 5 cô lập có mấy thành phần liên thông?

*Đáp án:* **3**: `{0,1,2}`, `{3,4}`, `{5}`.

**Bài 8 — Hai chiều.** Đồ thị có hướng chỉ có cạnh 0→1. Hai đỉnh có thuộc cùng SCC không?

*Đáp án:* **Không.** Có đường 0→1 nhưng không có đường 1→0. Chúng cùng thành phần liên thông **yếu** khi bỏ hướng cạnh.

**Bài 9 — Độ phức tạp.** Vì sao DFS dùng danh sách kề mất O(V+E) mà không phải O(VE)?

*Đáp án:* Mỗi đỉnh được mở xử lý một lần; tất cả danh sách kề cộng lại có O(E) mục (hoặc 2E ở vô hướng), và mỗi mục được kiểm tra một lần. Tổng cộng O(V+E), chưa kể đầu ra tỷ lệ số đỉnh.

**Bài 10 — Chuỗi cạnh sâu.** Nếu graph là một đường có hàng trăm nghìn đỉnh, nên cân nhắc phiên bản DFS nào trong Java?

*Đáp án:* **DFS lặp với stack tường minh**, vì DFS đệ quy có thể gây `StackOverflowError`. Nếu phải bảo toàn thứ tự DFS đệ quy, dùng stack frame lưu vị trí neighbor.

**Tổng kết:** DFS khám phá đồ thị theo chiến lược **đi sâu trước, quay lại sau**, với quy tắc quan trọng nhất là **đánh dấu đỉnh ngay khi khám phá**. Đệ quy và stack frame đều duyệt trong **O(V+E)** trên danh sách kề; chỉ DFS từ nguồn chưa đủ để mô tả toàn đồ thị không liên thông. **Parent** trả một đường đi chứ không bảo đảm đường ngắn nhất; **GRAY/BLACK** giúp phát hiện chu trình có hướng; **đảo thứ tự hoàn tất** cho thứ tự tô-pô trên DAG. Muốn dùng DFS đúng, luôn chốt **hướng cạnh, thứ tự neighbor, thời điểm khám phá/hoàn tất, và ý nghĩa trạng thái visited**.
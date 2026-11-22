# Cây duyệt, đỉnh cha và khôi phục đường đi

Khi **BFS** (*Breadth-First Search*) hoặc **DFS** (*Depth-First Search*) khám phá các đỉnh của đồ thị, ta không chỉ biết đỉnh nào đã được thăm. Nếu ghi lại **đỉnh cha** (*parent / predecessor*) tại **lần đầu** khám phá mỗi đỉnh, những cạnh cha–con tạo thành một **cây duyệt** (*traversal tree / search tree*). Dựa trên cây này, có thể **khôi phục một đường đi có thật** từ đỉnh xuất phát tới một đỉnh đích bằng cách lần theo các con trỏ cha ngược về gốc.

Đây là ý tưởng nền tảng trong nhiều bài thuật toán đồ thị: tìm đường trong mê cung, truy vết một chuỗi trạng thái, xác định cách đi tới một đỉnh, xuất chứng cứ về reachability, hoặc khôi phục lời giải sau một quá trình duyệt. Tuy nhiên phải phân biệt rất rõ:

- **Cây duyệt là một tập cạnh được thuật toán chọn khi khám phá đỉnh lần đầu, không nhất thiết là toàn bộ đồ thị.**
- **DFS** cung cấp một đường đi theo cây khám phá; nó **không bảo đảm ít cạnh nhất**.
- **BFS** trên đồ thị **không trọng số / mỗi cạnh có cùng chi phí** tạo cây đường đi ngắn nhất **theo số cạnh** từ nguồn.
- **Một đồ thị không liên thông có thể tạo rừng duyệt** khi khởi động nhiều lượt BFS/DFS; riêng với đồ thị có hướng, rừng duyệt không mặc nhiên là phân hoạch thành phần liên thông mạnh.
- **Đỉnh nguồn** và **đỉnh chưa tới được** có thể đều có `parent=-1`, nhưng mang ý nghĩa khác nhau. Phải có `visited` hoặc `distance/depth` để phân biệt.

Bài học xây từ định nghĩa đến bất biến, chứng minh tính đúng, mã giả, chương trình Java 17+ chạy được, bảng kiểm thử và các lỗi thường gặp. Mục tiêu là không chỉ “in ra đường đi”, mà hiểu **vì sao đường đi được khôi phục là hợp lệ** và **khi nào nó tối ưu**.

## 1. Những khái niệm cần tách biệt

Cho đồ thị \(G=(V,E)\) với các đỉnh được đánh số từ 0 đến \(V-1\).

**Đường đi (path)** từ s tới t là dãy đỉnh:

\[
s=v_0,v_1,\ldots,v_k=t,
\]

trong đó mỗi cặp liên tiếp \(v_{i-1}\to v_i\) là một cạnh hợp lệ theo **chiều** của đồ thị. Số cạnh trên đường đi này là **k**, còn số đỉnh trong dãy là **k+1**.

Trong **đồ thị vô hướng**, cạnh \(\{u,v\}\) có thể đi theo cả hai chiều. Trong **đồ thị có hướng**, cạnh \(u\to v\) không tự động cho phép đi từ v về u.

**Cây duyệt từ nguồn s** là tập các cạnh dùng để **lần đầu khám phá** những đỉnh có thể tới từ s. Đỉnh s là **gốc**, không có cha; mỗi đỉnh khác s được khám phá có **đúng một cha**, là đỉnh mà từ đó thuật toán lần đầu đi tới nó.

**Rừng duyệt (traversal forest)** là tập nhiều cây duyệt khi thuật toán bắt đầu một lượt mới tại những đỉnh chưa được thăm của toàn đồ thị.

**Cây duyệt không nhất thiết chứa mọi cạnh của đồ thị.** Ví dụ nếu có cạnh tạo chu trình hoặc cạnh nối hai đỉnh đã được thăm, cạnh đó vẫn thuộc đồ thị gốc nhưng không trở thành cạnh cha–con trong cây duyệt.

### Quy ước đường đi độ dài 0

Đường đi từ s tới chính s có **0 cạnh**, biểu diễn bằng danh sách **`[s]`**. Khi `source==target`, một hàm khôi phục đường đi đúng có thể trả ngay `[source]` nếu nguồn hợp lệ. **Danh sách rỗng `[]`** sẽ được dùng để báo **không tồn tại đường đi** từ nguồn đến đích.

Cần thống nhất quy ước này trước khi viết mã, vì nhiều lỗi kiểm thử phát sinh từ việc nhầm **0 cạnh** với **không có đường đi**.

## 2. Biểu diễn đồ thị: danh sách kề và hướng cạnh

Ví dụ đồ thị **có hướng** gồm 8 đỉnh `0..7`, với các cạnh **theo đúng thứ tự bổ sung**:

| Cạnh | Ý nghĩa |
|---|---|
| 0 → 1 | Một lựa chọn đầu từ nguồn 0 |
| 0 → 4 | Cạnh trực tiếp tới 4 |
| 1 → 2 | Nhánh sâu đi từ 1 |
| 1 → 5 | Nhánh khác từ 1 |
| 2 → 3 | Tiếp tục nhánh sâu |
| 3 → 4 | Đến 4 bằng đường vòng |
| 5 → 6 | Đi tới 6 |
| Đỉnh 7 | Cô lập, không cạnh vào/ra |

Danh sách kề:

~~~text
adj[0] = [1, 4]
adj[1] = [2, 5]
adj[2] = [3]
adj[3] = [4]
adj[4] = []
adj[5] = [6]
adj[6] = []
adj[7] = []
~~~

Có hai đường đi đáng chú ý từ 0 tới 4:

~~~text
0 -> 4                   (1 cạnh)
0 -> 1 -> 2 -> 3 -> 4     (4 cạnh)
~~~

Cả hai đều hợp lệ. Nhưng nếu cần đường **ít cạnh nhất**, chỉ đường trực tiếp là tối ưu. Nếu cần **một đường bất kỳ**, thuật toán có thể trả một trong hai.

**Đỉnh 7** xuất hiện trong tập V dù không nằm trong bất kỳ cạnh nào. Nếu xây đồ thị chỉ từ các đầu mút xuất hiện trong danh sách cạnh mà quên số lượng đỉnh V, ta có thể bỏ sót đỉnh cô lập, làm sai kết quả duyệt toàn đồ thị.

## 3. Đỉnh cha: ghi khi khám phá, không ghi mỗi khi gặp cạnh

Dùng mảng:

~~~text
parent[v] = đỉnh đã lần đầu dẫn thuật toán tới v
~~~

Quy tắc khởi tạo thường dùng:

~~~text
parent[*] = -1
visited[*] = false

visited[source] = true
parent[source] = -1
~~~

Khi xem cạnh \(u\to v\):

~~~text
if not visited[v]:
    visited[v] = true
    parent[v] = u
    đưa v vào lịch duyệt BFS/DFS
~~~

**Điểm mấu chốt là chỉ gán `parent[v]` khi v được khám phá lần đầu.** Nếu liên tục ghi lại cha của một đỉnh đã thăm, cây cha có thể không còn phản ánh đường duyệt ban đầu; nghiêm trọng hơn, các con trỏ cha có thể tạo chu trình và khiến việc truy vết không kết thúc.

Với ví dụ có cạnh `0→4` và `3→4`, nếu DFS đi qua `0→1→2→3→4` trước, nó đặt `parent[4]=3`. Sau đó quay về đỉnh 0 và xem cạnh `0→4`, v=4 đã thăm, nên **không** đổi cha thành 0. Kết quả khôi phục theo cây DFS vẫn là đường vòng.

Trong khi đó BFS khám phá đỉnh 4 **ngay khi xử lý các cạnh đi ra từ 0** và đặt `parent[4]=0`. Khi thấy `3→4` sau đó, nó cũng không đổi cha.

### Vì sao không được đổi cha tùy tiện?

Mỗi liên kết \(parent[v]=u\) được tạo ở thời điểm u đã thuộc cây và v vừa được thêm vào cây. Do đó các cạnh cha luôn nối một đỉnh mới vào một cấu trúc đã có. Một đỉnh không thể trở thành tổ tiên của chính nó theo chuỗi parent được xây theo nguyên tắc **first discovery** này.

Nếu đổi cha sau khám phá mà không có một thuật toán cập nhật tính chất rõ ràng, ta mất bất biến ấy. Các thuật toán đường ngắn nhất có trọng số như Dijkstra hoặc Bellman–Ford **có thể cập nhật predecessor khi tìm được khoảng cách tốt hơn**, nhưng phải tuân theo bất biến của thuật toán tương ứng; đó là chuyện khác với cây BFS/DFS chỉ gán cha một lần.

## 4. Mảng độ sâu và trạng thái không tới được

Để mô tả đường đi theo cây, có thể lưu:

\[
depth[source]=0,
\]

\[
depth[v]=depth[u]+1
\quad\text{khi v được khám phá lần đầu từ u}.
\]

Với các đỉnh chưa tới được, dùng:

\[
depth[v]=-1.
\]

Khi đó:

- `depth[v]>=0` nghĩa là đã khám phá v và có đường trong cây từ nguồn tới v.
- `depth[source]=0`, `parent[source]=-1` nghĩa là nguồn hợp lệ, đường đi có 0 cạnh.
- `depth[v]=-1`, `parent[v]=-1` nghĩa là chưa tới được từ nguồn trong lượt duyệt này.
- Với v khác nguồn đã khám phá: `parent[v]>=0` và `depth[parent[v]]=depth[v]-1`.

**Chỉ nhìn `parent[v]==-1` là chưa đủ** để kết luận không tới được: nguồn cũng không có cha. Vì thế ví dụ Java dùng `depth=-1` để biểu thị chưa khám phá; mảng `parent` chỉ làm nhiệm vụ truy vết.

Đừng nhầm **độ sâu trong cây DFS** với **khoảng cách ngắn nhất của đồ thị**. Với DFS, `depth[4]=4` trong ví dụ, mặc dù đồ thị có cạnh 0→4 nên khoảng cách ít cạnh nhất chỉ là 1. Với BFS trên đồ thị không trọng số, `depth` mới đúng là khoảng cách ngắn nhất theo số cạnh.

## 5. Cây duyệt BFS và tính chất đường đi ít cạnh nhất

**BFS** dùng hàng đợi FIFO, khám phá các đỉnh theo từng lớp số cạnh tính từ nguồn.

~~~text
BFS(source):
    for mọi v:
        parent[v] = -1
        distance[v] = -1

    distance[source] = 0
    queue.addLast(source)

    while queue không rỗng:
        u = queue.removeFirst()
        for v in adj[u]:
            if distance[v] != -1:
                continue
            distance[v] = distance[u] + 1
            parent[v] = u
            queue.addLast(v)
~~~

**Đánh dấu ngay khi đưa v vào hàng đợi**, không đợi tới khi lấy v ra. Nếu một v có nhiều cạnh đi vào, thao tác đánh dấu sớm bảo đảm v chỉ được enqueue một lần, và `parent[v]` không bị đổi bởi những cạnh khác.

### Mô phỏng BFS trên đồ thị ví dụ

Bắt đầu tại 0:

| Lượt lấy khỏi queue | Đỉnh u | Đỉnh mới khám phá | Queue sau khi xử lý |
|---:|---:|---|---|
| Khởi tạo | — | 0 | `[0]` |
| 1 | 0 | 1, 4 | `[1,4]` |
| 2 | 1 | 2, 5 | `[4,2,5]` |
| 3 | 4 | Không | `[2,5]` |
| 4 | 2 | 3 | `[5,3]` |
| 5 | 5 | 6 | `[3,6]` |
| 6 | 3 | Không; 4 đã thăm | `[6]` |
| 7 | 6 | Không | `[]` |

Thứ tự khám phá là:

~~~text
[0, 1, 4, 2, 5, 3, 6]
~~~

Bảng kết quả:

| v | parent BFS | distance BFS từ 0 | Đường khôi phục |
|---:|---:|---:|---|
| 0 | -1 | 0 | `[0]` |
| 1 | 0 | 1 | `[0,1]` |
| 2 | 1 | 2 | `[0,1,2]` |
| 3 | 2 | 3 | `[0,1,2,3]` |
| 4 | 0 | **1** | **`[0,4]`** |
| 5 | 1 | 2 | `[0,1,5]` |
| 6 | 5 | 3 | `[0,1,5,6]` |
| 7 | -1 | -1 | `[]` |

Cây BFS (chỉ các cạnh cha):

~~~text
         0
        / \
       1   4
      / \
     2   5
     |   |
     3   6

7 không thuộc cây từ nguồn 0
~~~

Cạnh gốc `3→4` không xuất hiện trong cây BFS vì 4 đã được khám phá từ 0 trước khi xử lý 3.

### Vì sao BFS cho ít cạnh nhất?

BFS đưa các đỉnh vào queue theo lớp: nguồn có khoảng cách 0; khi xử lý u ở lớp d, các đỉnh mới khám phá qua cạnh u→v nhận lớp d+1. Do queue FIFO, **mọi đỉnh ở lớp d được xử lý trước đỉnh lớp d+1**. Lần đầu gặp v không thể có đường ít hơn `distance[v]` cạnh chưa được xử lý, vì nếu tồn tại đường ngắn hơn, tiền nhiệm ở lớp thấp hơn đã được xử lý trước và đã khám phá v.

Theo quy nạp trên các lớp, `distance[v]` là **số cạnh ít nhất** từ nguồn tới v. Vì `parent[v]` được gán từ một đỉnh có khoảng cách nhỏ hơn đúng một, lần theo parent cho một đường đi có đúng `distance[v]` cạnh.

**Điều kiện áp dụng:** các cạnh không trọng số hoặc **đồng nhất một chi phí**; mục tiêu là **ít cạnh nhất**, không phải tổng trọng số nhỏ nhất với các cạnh có chi phí khác nhau. Nếu có trọng số thay đổi, BFS thường không giải đúng bài đường đi trọng số tối ưu.

## 6. Cây duyệt DFS và khác biệt với BFS

**DFS** đi sâu theo neighbor đầu tiên chưa thăm, quay lui khi một nhánh không thể đi tiếp.

~~~text
DFS(u):
    mark u visited
    record u

    for v in adj[u]:
        if not visited[v]:
            parent[v] = u
            depth[v] = depth[u] + 1
            DFS(v)
~~~

Với danh sách kề của ví dụ, bắt đầu 0:

~~~text
0 -> 1 -> 2 -> 3 -> 4
          quay về 1 -> 5 -> 6
quay về 0: cạnh 0 -> 4 đã được thăm
~~~

Thứ tự DFS:

~~~text
[0, 1, 2, 3, 4, 5, 6]
~~~

Cây DFS:

~~~text
0
|
1
|\
2 5
| |
3 6
|
4
~~~

Bảng parent DFS cho các đỉnh đã khám phá:

| v | parent DFS | depth DFS |
|---:|---:|---:|
| 0 | -1 | 0 |
| 1 | 0 | 1 |
| 2 | 1 | 2 |
| 3 | 2 | 3 |
| 4 | **3** | **4** |
| 5 | 1 | 2 |
| 6 | 5 | 3 |
| 7 | -1 | -1 |

DFS trả một đường đi tới 4 là:

~~~text
[0,1,2,3,4]   (4 cạnh)
~~~

BFS trả:

~~~text
[0,4]         (1 cạnh)
~~~

**Cả hai đường đều tồn tại trong đồ thị**, nhưng chỉ cây BFS chứng minh đường ít cạnh nhất trong trường hợp không trọng số này. Một bài chỉ yêu cầu **tìm bất kỳ đường đi** có thể dùng BFS hoặc DFS; nếu bài yêu cầu **đường ngắn nhất theo số cạnh**, chọn BFS.

### Thứ tự neighbor có ảnh hưởng tới parent không?

Có. Nếu `adj[0]` liệt kê đỉnh 4 trước đỉnh 1, ngay DFS cũng có thể khám phá 4 từ 0 và đặt `parent[4]=0`. Trong một đồ thị có nhiều đường đi, **cây DFS và cây BFS không nhất thiết duy nhất**. Điều được bảo đảm là:

- Cây DFS/BFS có cạnh đúng hướng và không có chu trình cha.
- BFS bảo toàn **độ dài đường ngắn nhất theo số cạnh**, dù đường cụ thể có thể khác khi có nhiều đường ngắn nhất.
- DFS không bảo toàn độ dài ngắn nhất; thứ tự neighbor có thể ảnh hưởng mạnh tới đường tìm thấy.

Nếu cần kết quả tái lập, hãy xác định thứ tự neighbor, ví dụ theo thứ tự input hoặc theo ID tăng dần.

## 7. Thuật toán khôi phục đường đi từ mảng cha

Giả sử đã chạy BFS/DFS từ một nguồn `source` và có `parent[]`, `visited[]` hoặc `depth[]`.

Cách truy vết:

1. Kiểm tra `target` có thuộc miền đỉnh hợp lệ.
2. Nếu `target` **chưa được khám phá**, trả **`[]`** (không có đường đi từ nguồn).
3. Nếu tới được, bắt đầu từ target và đi ngược theo `parent[target]`, `parent[parent[target]]`,... cho đến khi gặp `source`.
4. Danh sách thu được đang theo thứ tự **đích → nguồn**, nên phải **đảo ngược**.
5. Trả danh sách **nguồn → đích**, gồm cả hai đầu mút.

Mã giả:

~~~text
restorePath(source, target, parent, depth):
    if target ngoài miền:
        báo lỗi

    if depth[target] == -1:
        return []            // unreachable

    backwards = []
    v = target

    while v != -1:
        backwards.add(v)
        if v == source:
            break
        v = parent[v]

    if backwards.last != source:
        báo dữ liệu cây cha không hợp lệ

    reverse(backwards)
    return backwards
~~~

Ví dụ với cây DFS:

~~~text
target = 4
4 -> parent[4]=3
3 -> parent[3]=2
2 -> parent[2]=1
1 -> parent[1]=0
0 = source

backwards = [4,3,2,1,0]
reverse    = [0,1,2,3,4]
~~~

### Ba trường hợp trả về cần phân biệt

| Tình huống | Giá trị hợp lệ | Lý do |
|---|---|---|
| `source == target` | `[source]` | Một đường đi có 0 cạnh |
| Đích tới được, khác nguồn | Dãy ít nhất 2 đỉnh | Mỗi bước parent tương ứng một cạnh khám phá |
| Đích không tới được | `[]` | Không có đường trong lượt duyệt từ nguồn |

Hàm nên nêu rõ nó nhận **cây tìm kiếm từ một nguồn xác định**. Nếu lấy `parent` của lượt BFS từ nguồn 0 rồi cố khôi phục đường từ nguồn 5, ta không có quyền coi các con trỏ cha ấy là cây gốc 5. Muốn truy vấn từ nguồn mới, cần chạy lượt duyệt mới hoặc dùng một cấu trúc phù hợp cho nhiều truy vấn.

### Cách tránh vòng lặp khi dữ liệu cha bị hỏng

Với cây cha hợp lệ do BFS/DFS tạo, mỗi bước về cha giảm `depth` đúng một, nên vòng lặp **chắc chắn kết thúc** ở nguồn. Nếu mảng cha bị sửa sai, có thể xuất hiện vòng `parent[2]=3, parent[3]=2`. Mã sử dụng cho dữ liệu ngoài không đáng tin nên có kiểm tra điều kiện và giới hạn số bước tối đa V để tránh lặp vô hạn.

Trong ví dụ Java, `SearchTree` chỉ được dựng từ BFS/DFS nội bộ; `restorePath` còn kiểm tra số bước và xác nhận chuỗi parent kết thúc ở nguồn để phát hiện trạng thái không hợp lệ.

## 8. Chứng minh cây duyệt là cây và đường khôi phục hợp lệ

Giả sử BFS/DFS từ nguồn s khám phá được tập đỉnh \(R\).

### 8.1. Mỗi đỉnh khác gốc có đúng một cha

Nguồn s được đánh dấu trước khi duyệt, có `parent[s]=-1`. Khi một đỉnh v khác s **lần đầu được khám phá**, nó được thêm qua một cạnh \(u\to v\) có thật của đồ thị; ta đặt `parent[v]=u`. Do `visited[v]` từ đó không trở lại false trong cùng lượt, `parent[v]` **không được gán lần thứ hai**.

Vì vậy mọi đỉnh trong \(R\setminus\{s\}\) có **đúng một cha**; s không có cha.

### 8.2. Không có chu trình trong quan hệ cha

Tại thời điểm gán `parent[v]=u`, u **đã được khám phá**, còn v **chưa**. Mỗi cạnh cha vì thế nối một đỉnh mới vào tập đỉnh đã khám phá. Không thể tạo chu trình bằng cách nối một đỉnh hoàn toàn mới làm con của một đỉnh cũ.

Tương đương, `depth[v]=depth[u]+1`. Nếu lần ngược từ v qua cha, depth giảm đúng một mỗi bước, không thể quay lại v vì độ sâu không thể giảm rồi trở về giá trị ban đầu theo cạnh cha.

### 8.3. Liên thông về gốc theo cạnh cha

Nguồn s có đường đi độ dài 0 tới chính nó. Mỗi đỉnh v khác s được khám phá từ một u đã thuộc cây, nên đường theo cha từ s tới u nối thêm cạnh \(u\to v\) tạo đường hợp lệ tới v. Quy nạp theo thời điểm khám phá cho thấy mọi đỉnh trong R nối được về s.

Tập cạnh cha có đúng \(|R|-1\) cạnh, không có chu trình và nối mọi đỉnh R về một gốc; vì vậy nó tạo thành một **cây duyệt gốc s**. Trong đồ thị có hướng, các cạnh cha hướng ra từ s; có thể gọi cấu trúc này là một **out-arborescence** trên tập đỉnh tới được.

### 8.4. Vì sao đảo chuỗi cha là một đường đi hợp lệ?

Tại mọi bước truy vết từ v lên u=parent[v], cạnh \(u\to v\) chắc chắn từng được dùng để khám phá v. Đảo chuỗi cha cho dãy đi **từ nguồn theo đúng các cạnh đã lưu** tới đích. Vì các cha không tạo chu trình và luôn tiến dần về nguồn, đường đi là một đường hợp lệ, không lặp đỉnh.

**Chú ý phạm vi kết luận:** chứng minh này bảo đảm **tồn tại và hợp lệ** của đường khôi phục. Tính chất **ít cạnh nhất** cần thêm lập luận lớp BFS ở phần 5; không suy ra từ riêng việc `parent` tạo thành cây.

## 9. Rừng duyệt và nhiều thành phần

Khi cần phân tích **mọi đỉnh**, thuật toán duyệt thường có vòng lặp ngoài:

~~~text
visited[*] = false
for s = 0 .. V-1:
    if not visited[s]:
        bắt đầu một cây duyệt mới gốc s
~~~

Đỉnh chưa thăm trở thành gốc của cây mới, có `parent[s]=-1`. Nếu có nhiều gốc, cấu trúc kết quả không còn là một cây duy nhất mà là **rừng duyệt**.

### Ví dụ đồ thị vô hướng

Cho 7 đỉnh với các cạnh:

~~~text
0 -- 2 -- 3      1 -- 4 -- 5      6
~~~

Các thành phần liên thông:

~~~text
[0,2,3]
[1,4,5]
[6]
~~~

Nếu duyệt các đỉnh theo thứ tự `0..6`, BFS tạo rừng gồm ba cây gốc:

~~~text
roots = [0,1,6]

Cây 0: 0 -> 2 -> 3
Cây 1: 1 -> 4 -> 5
Cây 6: chỉ đỉnh 6
~~~

Với đồ thị vô hướng, mỗi lần khởi động BFS/DFS ở một đỉnh chưa thăm, thuật toán đi được tới **toàn bộ thành phần liên thông** của đỉnh ấy; do đó số cây trong rừng bằng số thành phần liên thông vô hướng.

### Tại sao rừng duyệt có hướng không phải SCC?

Đồ thị có hướng chỉ chứa cạnh `0→1`:

- Từ 0 có thể tới 1.
- Từ 1 **không** có đường tới 0.

Nếu vòng lặp toàn đồ thị bắt đầu từ 0, DFS có thể tạo **một cây chứa 0 và 1**. Nhưng hai đỉnh đó **không thuộc cùng thành phần liên thông mạnh (SCC)**, vì không có đường 1→0.

Vì vậy không được gọi số cây của một rừng duyệt **đồ thị có hướng** là “số thành phần liên thông mạnh”. SCC yêu cầu thuật toán như **Tarjan** hoặc **Kosaraju**, không chỉ duyệt và gom theo gốc tùy ý. Trong đồ thị có hướng, một rừng duyệt vẫn đúng như **rừng của các cạnh khám phá**, nhưng các cây phụ thuộc thứ tự khởi động và không phải phân hoạch SCC.

### Cha của nhiều gốc

Nếu dùng một mảng `parent[]` cho toàn rừng, **mỗi gốc cây** có `parent=-1`. Muốn biết đỉnh v thuộc cây nào, nên lưu thêm `rootOf[v]` hoặc `componentId[v]`. Với rừng vô hướng từ ví dụ, `componentId` có thể là:

~~~text
v:             0  1  2  3  4  5  6
componentId:   0  1  0  0  1  1  2
~~~

Chỉ mảng parent không nhất thiết đủ tiện dụng để trả nhanh nhiều truy vấn “hai đỉnh có cùng cây không?”. Có thể lần cha để tìm gốc (O(chiều sâu)) hoặc lưu thông tin gốc/thành phần trong lúc duyệt.

## 10. Java 17+: BFS, DFS, truy vết và rừng duyệt

Chương trình độc lập dưới đây giải thích cùng một đồ thị bằng cả **BFS** và **DFS**, để thấy parent khác nhau. Nó còn dựng rừng duyệt cho đồ thị **vô hướng**, minh họa đỉnh cô lập, hướng cạnh và đồ thị có chu trình.

**Quy ước chương trình:**

- Đỉnh là số nguyên `0..vertices-1`.
- Cạnh được duyệt theo **thứ tự cung cấp**, không tự sắp.
- `depth[v]=-1` nghĩa là chưa tới được từ nguồn.
- `parent[source]=-1` nghĩa là nguồn không có cha.
- `restorePath` trả `[]` nếu không tới được, `[source]` nếu nguồn bằng đích, hoặc một danh sách từ nguồn tới đích.
- BFS/DFS tìm đường theo hướng cạnh; riêng `undirectedForest` chỉ có hợp đồng ý nghĩa thành phần liên thông khi **đầu vào được xây vô hướng**.

Lưu tệp **TraversalTreeDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class TraversalTreeDemo {
    record SearchTree(
        int source, List<Integer> order, int[] parent, int[] depth
    ) {}

    record Forest(
        List<Integer> roots, List<List<Integer>> components,
        int[] parent, int[] componentId
    ) {}

    static List<List<Integer>> buildGraph(
        int vertices, int[][] edges, boolean directed
    ) {
        Objects.requireNonNull(edges, "edges");
        if (vertices < 0) {
            throw new IllegalArgumentException("negative vertex count");
        }
        List<List<Integer>> graph = new ArrayList<>();
        for (int v = 0; v < vertices; v++) {
            graph.add(new ArrayList<>());
        }
        for (int[] edge : edges) {
            if (edge == null || edge.length != 2
                    || edge[0] < 0 || edge[0] >= vertices
                    || edge[1] < 0 || edge[1] >= vertices) {
                throw new IllegalArgumentException("invalid edge");
            }
            int u = edge[0];
            int v = edge[1];
            graph.get(u).add(v);
            if (!directed && u != v) {
                graph.get(v).add(u);
            }
        }
        return graph;
    }

    static void checkSource(List<List<Integer>> graph, int source) {
        Objects.requireNonNull(graph, "graph");
        if (source < 0 || source >= graph.size()) {
            throw new IllegalArgumentException("invalid source");
        }
    }

    static SearchTree bfs(List<List<Integer>> graph, int source) {
        checkSource(graph, source);
        int n = graph.size();
        int[] parent = new int[n];
        int[] depth = new int[n];
        Arrays.fill(parent, -1);
        Arrays.fill(depth, -1);

        List<Integer> order = new ArrayList<>();
        ArrayDeque<Integer> queue = new ArrayDeque<>();
        depth[source] = 0;
        queue.addLast(source);

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            order.add(u);

            for (int v : graph.get(u)) {
                if (depth[v] != -1) {
                    continue; // Already discovered.
                }
                depth[v] = depth[u] + 1;
                parent[v] = u; // Set only on first discovery.
                queue.addLast(v);
            }
        }
        return new SearchTree(
            source, List.copyOf(order), parent, depth
        );
    }

    static SearchTree dfs(List<List<Integer>> graph, int source) {
        checkSource(graph, source);
        int n = graph.size();
        int[] parent = new int[n];
        int[] depth = new int[n];
        Arrays.fill(parent, -1);
        Arrays.fill(depth, -1);

        List<Integer> order = new ArrayList<>();
        depth[source] = 0;
        dfsVisit(source, graph, parent, depth, order);
        return new SearchTree(
            source, List.copyOf(order), parent, depth
        );
    }

    private static void dfsVisit(
        int u, List<List<Integer>> graph, int[] parent,
        int[] depth, List<Integer> order
    ) {
        order.add(u);
        for (int v : graph.get(u)) {
            if (depth[v] == -1) {
                parent[v] = u;
                depth[v] = depth[u] + 1;
                dfsVisit(v, graph, parent, depth, order);
            }
        }
    }

    static List<Integer> restorePath(SearchTree tree, int target) {
        Objects.requireNonNull(tree, "tree");
        if (target < 0 || target >= tree.parent().length) {
            throw new IllegalArgumentException("invalid target");
        }
        if (tree.depth()[target] < 0) {
            return List.of(); // Unreachable from tree.source().
        }

        List<Integer> reversed = new ArrayList<>();
        int v = target;
        for (int steps = 0; v != -1
                && steps < tree.parent().length; steps++) {
            reversed.add(v);
            if (v == tree.source()) {
                break;
            }
            v = tree.parent()[v];
        }

        if (reversed.isEmpty()
                || reversed.get(reversed.size() - 1) != tree.source()) {
            throw new IllegalStateException("invalid parent chain");
        }
        Collections.reverse(reversed);
        return List.copyOf(reversed);
    }

    // Run on an UNDIRECTED adjacency list when asking for
    // connected components.
    static Forest undirectedForest(List<List<Integer>> graph) {
        Objects.requireNonNull(graph, "graph");
        int n = graph.size();
        int[] parent = new int[n];
        int[] componentId = new int[n];
        Arrays.fill(parent, -1);
        Arrays.fill(componentId, -1);

        List<Integer> roots = new ArrayList<>();
        List<List<Integer>> components = new ArrayList<>();

        for (int start = 0; start < n; start++) {
            if (componentId[start] != -1) {
                continue;
            }
            int id = components.size();
            roots.add(start);

            ArrayDeque<Integer> queue = new ArrayDeque<>();
            List<Integer> vertices = new ArrayList<>();
            componentId[start] = id;
            queue.addLast(start);

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                vertices.add(u);

                for (int v : graph.get(u)) {
                    if (componentId[v] != -1) {
                        continue;
                    }
                    componentId[v] = id;
                    parent[v] = u;
                    queue.addLast(v);
                }
            }
            components.add(List.copyOf(vertices));
        }

        return new Forest(
            List.copyOf(roots), List.copyOf(components),
            parent, componentId
        );
    }

    public static void main(String[] args) {
        int[][] directedEdges = {
            {0, 1}, {0, 4}, {1, 2}, {1, 5},
            {2, 3}, {3, 4}, {5, 6}
        };
        List<List<Integer>> directed =
            buildGraph(8, directedEdges, true);
        SearchTree fromBfs = bfs(directed, 0);
        SearchTree fromDfs = dfs(directed, 0);

        System.out.println("BFS order: " + fromBfs.order());
        System.out.println("DFS order: " + fromDfs.order());
        System.out.println("BFS path 0 to 4: "
            + restorePath(fromBfs, 4));
        System.out.println("DFS path 0 to 4: "
            + restorePath(fromDfs, 4));
        System.out.println("BFS edges to 4: " + fromBfs.depth()[4]);
        System.out.println("DFS tree depth of 4: "
            + fromDfs.depth()[4]);
        System.out.println("BFS path 0 to 6: "
            + restorePath(fromBfs, 6));
        System.out.println("BFS path 0 to 7: "
            + restorePath(fromBfs, 7));
        System.out.println("BFS self path: "
            + restorePath(fromBfs, 0));

        List<List<Integer>> undirected = buildGraph(
            7, new int[][] {
                {0, 2}, {2, 3}, {1, 4}, {4, 5}
            }, false
        );
        Forest forest = undirectedForest(undirected);
        System.out.println("Forest roots: " + forest.roots());
        System.out.println("Forest components: " + forest.components());
        System.out.println("Forest parent of 3: " + forest.parent()[3]);

        List<List<Integer>> oneWay = buildGraph(
            2, new int[][] {{0, 1}}, true
        );
        System.out.println("Reverse-directed path 1 to 0: "
            + restorePath(bfs(oneWay, 1), 0));

        List<List<Integer>> cyclic = buildGraph(
            3, new int[][] {{0, 1}, {1, 2}, {2, 0}}, true
        );
        System.out.println("Cyclic graph BFS: "
            + bfs(cyclic, 0).order());
        System.out.println("Cyclic graph path 0 to 2: "
            + restorePath(bfs(cyclic, 0), 2));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac TraversalTreeDemo.java
java TraversalTreeDemo
~~~

**Stdout chính xác:**

~~~text
BFS order: [0, 1, 4, 2, 5, 3, 6]
DFS order: [0, 1, 2, 3, 4, 5, 6]
BFS path 0 to 4: [0, 4]
DFS path 0 to 4: [0, 1, 2, 3, 4]
BFS edges to 4: 1
DFS tree depth of 4: 4
BFS path 0 to 6: [0, 1, 5, 6]
BFS path 0 to 7: []
BFS self path: [0]
Forest roots: [0, 1, 6]
Forest components: [[0, 2, 3], [1, 4, 5], [6]]
Forest parent of 3: 2
Reverse-directed path 1 to 0: []
Cyclic graph BFS: [0, 1, 2]
Cyclic graph path 0 to 2: [0, 1, 2]
~~~

### Những lựa chọn quan trọng trong mã

**Tính nhất quán của parent và depth:** cả BFS/DFS khởi tạo mọi `parent=-1` và `depth=-1`. Đỉnh nguồn có depth 0. Đỉnh được khám phá qua cạnh u→v nhận cha u và độ sâu của u cộng một. Không có bước thay cha sau lần khám phá đầu tiên.

**BFS dùng queue FIFO:** xử lý các đỉnh theo lớp và đánh dấu ngay lúc enqueue. Vì vậy parent BFS bảo toàn đường ít cạnh nhất trong đồ thị không trọng số.

**DFS dùng đệ quy:** với thứ tự neighbor đầu vào, đi sâu 0→1→2→3→4 trước khi xét 0→4, nên parent DFS của 4 là 3. Đây là bằng chứng trực quan rằng DFS không tự tạo đường tối ưu về số cạnh.

**Kết quả SearchTree chứa mảng:** `record` trong Java tạo các accessor `parent()`, `depth()` nhưng **không tự sao chép phòng vệ** các mảng. Ví dụ chỉ đọc chúng sau khi giải. Nếu dùng làm API công cộng và có nguy cơ người gọi sửa mảng, nên phòng vệ bằng bản sao khi xây/trả hoặc một thiết kế bất biến khác, để không làm hỏng parent chain.

**Truy vết có kiểm tra:** `restorePath` không đọc parent của đỉnh chưa tới được. Với đích đã thăm, nó lần ngược tối đa V bước và xác nhận kết thúc ở source; sai lệch cha sẽ báo lỗi thay vì tạo một đường vô hạn. Nó trả danh sách từ nguồn tới đích đã sao chép, không cung cấp danh sách mutable nội bộ.

**Rừng vô hướng:** `undirectedForest` khởi động từ mọi đỉnh chưa thuộc thành phần nào, và giữ đồng thời `componentId`, `parent`, các nhóm đỉnh và gốc. Đỉnh 6 cô lập vẫn được tính; mỗi gốc có parent=-1.

**Đồ thị có hướng một chiều:** hàm duyệt từ 1 trên `0→1` trả `[]` cho đích 0; thuật toán không tự tạo cạnh 1→0.

**Chu trình trong đồ thị gốc:** `0→1→2→0` là một chu trình, nhưng BFS đánh dấu mỗi đỉnh đúng một lần và cây cha chỉ có hai cạnh 0→1, 1→2; **cây duyệt không có chu trình**. Chu trình gốc không làm thuật toán truy vết parent bị lặp vô hạn nếu parent được gán đúng.

### Giới hạn cần công bố

- `dfs` đệ quy có thể gặp `StackOverflowError` trên đường rất dài; với V lớn, nên dùng DFS stack tường minh có frame lưu neighbor tiếp theo, hoặc BFS nếu phù hợp mục tiêu.
- Các hàm duyệt giả sử danh sách kề được xây hợp lệ. `buildGraph` kiểm tra các cạnh từ input; nếu truyền vào một danh sách kề bên ngoài bị sửa hỏng, cần thêm kiểm tra hợp lệ theo yêu cầu ứng dụng.
- `undirectedForest` **không tự kiểm tra tính đối xứng** của danh sách kề, nên người gọi phải truyền biểu diễn đồ thị vô hướng khi muốn các nhóm là thành phần liên thông vô hướng.
- Các danh sách `SearchTree.order()` và `Forest.components()` là bản sao bất biến theo `List.copyOf`; còn mảng parent/depth/componentId vẫn có thể sửa qua accessor như đã nói.
- Chỉ số đỉnh là `int` liên tiếp 0..V-1. Nếu dữ liệu là nhãn như tên thành phố hoặc UUID, phải ánh xạ tới ID số hoặc dùng cấu trúc `Map` tương ứng.
- Các cạnh có thể trùng; BFS/DFS vẫn đánh dấu mỗi đỉnh lần đầu, nên không tạo nhiều cha cho cùng một đỉnh.

## 11. Một nguồn hay nhiều truy vấn nguồn–đích?

Có ba tình huống cần phân biệt.

### 11.1. Một nguồn cố định, nhiều đích

Nếu nhiều truy vấn hỏi đường từ **cùng s** tới các t khác nhau, chạy **một BFS(s)** rồi giữ `parent[]`, `depth[]`. Mỗi truy vấn chỉ cần lần cha để khôi phục đường, tốn thời gian tỷ lệ độ dài đường:

\[
O(L),
\]

trong đó L là số đỉnh được xuất ra (có thể tới V). Đầu tư ban đầu cho BFS là **O(V+E)**; không cần chạy lại BFS cho từng đích khi graph và nguồn không đổi.

### 11.2. Nhiều nguồn khác nhau

Mảng cha sinh từ nguồn s không tự áp dụng cho một nguồn s' khác. Có thể:

- Chạy lại BFS/DFS cho từng nguồn khi số nguồn ít.
- Tiền tính từ nhiều nguồn nếu số truy vấn đủ lớn và chi phí bộ nhớ cho phép.
- Với đồ thị có tính chất đặc biệt (cây vô hướng, DAG, nhiều truy vấn trên cây), dùng thuật toán/tiền xử lý chuyên biệt.

Không thể đơn giản sửa trường `source` của `SearchTree` cũ rồi mong `parent` tương ứng với nguồn mới.

### 11.3. Tìm từ một tập nhiều nguồn

Nếu câu hỏi là **đường gần nhất tới bất kỳ nguồn nào** trong tập `S`, BFS **đa nguồn** có thể đưa tất cả nguồn vào queue từ đầu với `distance=0`, `parent=-1`. Mỗi đỉnh v được gắn với nguồn đã khám phá nó đầu tiên; nên lưu thêm `rootOf[v]` để biết đường được khôi phục bắt đầu ở nguồn nào.

Trong đa nguồn, không nên giả định chỉ có một gốc cho tất cả các chuỗi parent. Nghiệm trả về là một đường bắt đầu từ **một nguồn của S**, thường là nguồn gần nhất theo số cạnh nếu mọi cạnh không trọng số.

## 12. Cây duyệt không đồng nghĩa cây khung tối ưu

Một **cây duyệt** chỉ giữ các cạnh dùng để khám phá đỉnh. Có những cấu trúc cũng là cây nhưng tối ưu theo mục tiêu khác:

| Cấu trúc | Mục tiêu / bất biến |
|---|---|
| **Cây DFS** | Giữ quan hệ cha do đi sâu trước; đường từ gốc tới v có thật nhưng không ngắn nhất nói chung |
| **Cây BFS** | Mọi đường từ nguồn đến đỉnh tới được có **ít cạnh nhất** trên graph không trọng số |
| **Cây đường đi ngắn nhất có trọng số** | Mỗi đường gốc→v có **tổng trọng số nhỏ nhất** theo điều kiện của thuật toán (ví dụ Dijkstra) |
| **Cây khung nhỏ nhất (MST)** | Trên đồ thị vô hướng có trọng số, giảm **tổng trọng số các cạnh của cả cây**, không nhằm làm từng đường từ gốc ngắn nhất |
| **Rừng duyệt** | Tập các cây do duyệt toàn đồ thị; ở graph vô hướng, mỗi cây ứng với một thành phần liên thông |

Không được thay thuật toán chỉ vì cả hai đầu ra đều là “một cây”. Ví dụ cây khung nhỏ nhất và cây đường ngắn nhất khác mục tiêu: **tổng trọng số cạnh của cây nhỏ** không bảo đảm đường gốc→v là ngắn nhất cho từng v.

Cây BFS trên đồ thị có hướng vẫn có cạnh đi ra theo chiều khám phá từ nguồn và tối ưu số cạnh tới các đỉnh có thể tới, nhưng nó **không** phải một cây khung vô hướng của toàn bộ đồ thị nếu có đỉnh không tới được.

## 13. Độ phức tạp thời gian và bộ nhớ

Giả sử danh sách kề được dùng với V đỉnh và E cạnh.

| Công đoạn | Thời gian | Bộ nhớ phụ |
|---|---:|---:|
| Xây adjacency list | **O(V+E)** | **O(V+E)** lưu đồ thị |
| BFS từ một nguồn | **O(V+E)** cận trên | O(V) queue, parent, depth, order |
| DFS đệ quy từ một nguồn | **O(V+E)** cận trên | O(V) parent, depth, order + call stack O(V) |
| Duyệt rừng cho toàn graph vô hướng | **O(V+E)** | O(V) visited/componentId, queue, parent, kết quả |
| Khôi phục đường đi tới một đích | **O(L)** | O(L) danh sách đường, với L≤V |
| Nhiều đích, một nguồn BFS đã tính | O(L) mỗi truy vấn | O(L) output mỗi truy vấn |

**Lý do:** mỗi đỉnh được khám phá tối đa một lần và được xử lý hàng xóm tối đa một lần; tổng kích thước mọi danh sách kề là E với graph có hướng và 2E với graph vô hướng, vẫn là O(E). Queue hoặc call stack chứa tối đa O(V) đỉnh; mỗi đỉnh có đúng một ô parent và depth.

Ở trường hợp chỉ những đỉnh thuộc tập R tới được từ nguồn được duyệt, công việc duyệt sau khi khởi tạo có thể mô tả là **O(|R| + số cạnh đi ra từ R)**. Tuy nhiên mã Java tạo mảng parent/depth kích thước V, nên tổng thời gian còn có **O(V)** cho khởi tạo, và cận O(V+E) luôn đúng.

**Truy vết:** nếu đường trả có k cạnh, cần ghi k+1 đỉnh và đảo danh sách, nên thời gian và bộ nhớ **O(k+1)**. Không thể xuất đầy đủ một đường dài mà tốn o(k) thời gian; độ dài đầu ra đã là một giới hạn dưới thực tế.

**Ma trận kề:** nếu dùng ma trận V×V, mỗi lần xét neighbor có thể quét V cột. Duyệt toàn đồ thị thường tốn **O(V²)**; vì vậy khi nói O(V+E), phải hiểu đó là phân tích với **danh sách kề**.

**Đệ quy Java:** độ sâu của cây DFS có thể tới V, gây `StackOverflowError` trong JVM. Cây BFS dùng queue rõ ràng, không có lời gọi đệ quy sâu; khi cần duyệt sâu bằng DFS, có thể triển khai stack frame tường minh.

## 14. Những tình huống biên dễ nhầm

| Tình huống | Xử lý đúng |
|---|---|
| `source==target` | Trả **`[source]`**, đường 0 cạnh |
| Target chưa thăm | Trả `[]`, không lần theo parent |
| Đỉnh nguồn có parent=-1 | **Bình thường**; dùng depth=0 để phân biệt không tới được |
| Đỉnh cô lập không phải nguồn | Không tới được; có thể là gốc cây riêng khi duyệt toàn graph |
| Đồ thị có chu trình | BFS/DFS dùng visited nên chỉ khám phá mỗi đỉnh một lần; cây cha vẫn không có chu trình |
| Đồ thị có nhiều đường đi cùng độ dài | BFS có thể chọn **một** đường ngắn nhất dựa vào thứ tự neighbor |
| Có cạnh trực tiếp source→target nhưng DFS đi đường khác trước | DFS có thể trả đường dài hơn; không được gắn nhãn shortest |
| Chỉ có cạnh u→v | Không mặc nhiên có đường từ v tới u |
| Có nhiều cạnh song song u→v | Không sinh nhiều cha; parent chỉ đặt lần đầu |
| Đồ thị vô hướng có self-loop | Visited ngăn self-loop thành cạnh cha mới của chính đỉnh |
| Graph không đỉnh | Không có nguồn hợp lệ; `buildGraph(0,...)` có thể tạo danh sách kề rỗng |
| Target vượt miền chỉ số | Báo lỗi chỉ số thay vì dựng đường giả |
| Nhiều nguồn, cùng đích | Cần cây theo từng nguồn hoặc giải pháp đa nguồn thích hợp |
| Parent do bên ngoài sửa hỏng | Phải kiểm tra vòng lặp/đích nguồn hoặc dùng API bất biến |
| DFS quá sâu | Dùng stack tường minh nếu có nguy cơ tràn call stack Java |

## 15. Lỗi thường gặp

1. **Gán parent trước khi biết v mới được thăm**, làm thay cha của đỉnh đã khám phá.
2. **Chỉ đọc parent=-1 để kết luận “không có đường”**, nhầm nguồn với đỉnh không tới được.
3. **Không đánh dấu lúc enqueue/push**, khiến một đỉnh có thể được thêm nhiều lần và ghi cha nhiều lần.
4. **Không dùng visited/depth**, dễ lặp vô hạn trên đồ thị có chu trình.
5. **Quên đảo danh sách truy vết**, in đường `target→source` thay vì `source→target`.
6. **Bỏ nguồn hoặc bỏ đích** trong đường xuất ra, làm số đỉnh không khớp số cạnh.
7. **Cho rằng `depth` DFS là khoảng cách ít cạnh nhất**, sai với các cạnh tắt trong graph.
8. **Dùng BFS không trọng số để tối ưu tổng trọng số bất kỳ**, sai khi cạnh khác chi phí.
9. **Khôi phục đường từ nguồn khác cây đã lưu**, parent không còn mang ý nghĩa cho truy vấn đó.
10. **Không kiểm tra target đã tới được** trước khi lần parent từ một giá trị mặc định.
11. **Đặt parent[source]=source rồi viết vòng `while(parent[v]!=-1)`**, có thể lặp vô hạn nếu không có điều kiện dừng riêng.
12. **Không lưu thứ tự neighbor nhưng yêu cầu stdout cố định**, khiến parent và đường khôi phục khác kỳ vọng.
13. **Duyệt chỉ từ 0 rồi quên đỉnh cô lập** trong bài yêu cầu rừng/toàn đồ thị.
14. **Dùng forest của đồ thị có hướng như SCC**, sai vì reachability một chiều không phải liên thông mạnh.
15. **Xem cây duyệt chứa tất cả cạnh đồ thị**, nhầm cạnh khám phá với cạnh chéo/ngược.
16. **Không xử lý đồ thị có hướng đúng chiều cạnh**, vô tình thêm cạnh ngược khi dữ liệu không cho phép.
17. **Trộn khoảng cách trong BFS với độ sâu DFS** trong một mảng chung giữa hai lượt độc lập.
18. **Giữ visited của lượt gọi trước** khi đổi nguồn, làm các đỉnh “đã thăm” không đúng trạng thái truy vấn mới.
19. **Không phòng vệ các mảng parent/depth khi chia sẻ qua API**, người gọi có thể sửa làm hỏng invariant.
20. **Giả định một cây khung tối thiểu cũng cho đường ngắn nhất từ nguồn**, nhầm hai mục tiêu khác nhau.
21. **Không cân nhắc StackOverflowError của DFS đệ quy** khi đồ thị có đường cực sâu.
22. **Báo O(V+E) cho ma trận kề mà không đếm chi phí quét hàng**, sai phân tích theo biểu diễn.

## 16. Quy trình giải một bài cần xuất đường đi

1. **Chốt graph:** có hướng hay vô hướng, có trọng số hay không, số đỉnh có bao gồm đỉnh cô lập không?
2. **Chốt mục tiêu:** chỉ cần **một đường hợp lệ**, hay cần **đường ít cạnh nhất**, hay **tổng trọng số tối ưu**?
3. **Chọn thuật toán:** DFS/BFS cho reachability; BFS cho ít cạnh nhất không trọng số; thuật toán khác cho trọng số.
4. **Khởi tạo mảng trạng thái:** `parent=-1`, `visited=false` hoặc `depth=-1`; đánh dấu nguồn.
5. **Chỉ gán parent khi khám phá lần đầu:** với mỗi cạnh u→v, kiểm tra v trước khi đưa vào lịch xử lý.
6. **Không đổi cha sau đó** trừ khi đang dùng thuật toán thư giãn khoảng cách có bất biến riêng.
7. **Sau duyệt, kiểm tra target có tới được không.**
8. **Truy vết target→source và đảo lại**; với target==source trả [source].
9. **Kiểm tra tính hợp lệ:** mọi cặp liên tiếp của đường trả có cạnh đúng hướng trong graph.
10. **Kiểm tra độ dài:** nếu là BFS, số cạnh trên đường trả bằng depth[target] và là tối thiểu theo lớp.
11. **Nếu nhiều truy vấn cùng nguồn:** giữ cây tìm kiếm để trả nhiều đích; nếu đổi nguồn thì tính lại hoặc dùng tiền xử lý phù hợp.
12. **Nếu yêu cầu toàn bộ graph:** duyệt rừng; lưu componentId/rootOf khi cần phân biệt các cây.

Một cách kiểm thử cơ bản là với mỗi đỉnh v đã thăm và v khác nguồn, xác nhận `parent[v]` là một đỉnh hợp lệ, có cạnh `parent[v]→v`, và `depth[v]=depth[parent[v]]+1`. Sau đó khôi phục từng đường và kiểm tra số cạnh bằng depth. Với BFS, so sánh thêm với một phép đo khoảng cách độc lập trên đồ thị nhỏ.

## 17. Bài tập tự kiểm tra

**Bài 1 — Khác biệt BFS/DFS.** Trên đồ thị phần 2 có cạnh trực tiếp `0→4`. Vì sao DFS có thể trả `[0,1,2,3,4]`, trong khi BFS trả `[0,4]`?

*Đáp án:* DFS đi sâu theo neighbor 1 trước rồi mới xét cạnh trực tiếp, vì vậy khám phá 4 qua 3. BFS khám phá các neighbor của 0 ở lớp 1, gồm 4, nên tìm được đường ít cạnh nhất.

**Bài 2 — Nguồn hay không tới được?** Cả `parent[0]` và `parent[7]` đều bằng -1 trong ví dụ. Làm sao phân biệt?

*Đáp án:* `depth[0]=0` vì 0 là nguồn; `depth[7]=-1` vì 7 không tới được. Không được suy luận chỉ từ `parent=-1`.

**Bài 3 — Truy vết.** Nếu `parent[6]=5`, `parent[5]=1`, `parent[1]=0`, `parent[0]=-1`, đường từ 0 tới 6 là gì?

*Đáp án:* Lần ngược được `[6,5,1,0]`, đảo lại thành **`[0,1,5,6]`**.

**Bài 4 — Khởi tạo.** Khi đổi nguồn từ 0 sang 5, có thể giữ nguyên `parent[]` và `depth[]` của BFS từ 0 không?

*Đáp án:* **Không**. Cây cha đã được tính theo nguồn 0. Muốn đường từ nguồn 5, phải chạy lại truy vấn hoặc có một cấu trúc/thuật toán khác đáp ứng nhiều nguồn.

**Bài 5 — Cạnh chéo.** Nếu BFS đã có `parent[4]=0`, rồi gặp cạnh `3→4`, có đổi `parent[4]=3` không?

*Đáp án:* **Không**. Đỉnh 4 đã khám phá; parent chỉ gán lúc khám phá lần đầu. Đổi cha sẽ phá bất biến cây BFS và có thể làm đường dài hơn.

**Bài 6 — Thành phần vô hướng.** Với các cạnh `0—2`, `2—3`, `1—4`, `4—5` và đỉnh 6 cô lập, rừng duyệt có mấy cây nếu duyệt mọi đỉnh?

*Đáp án:* **3** cây ứng với các thành phần `{0,2,3}`, `{1,4,5}`, `{6}`. Với thứ tự khởi động tăng dần, gốc là 0, 1, 6.

**Bài 7 — Đồ thị có hướng.** Với cạnh `0→1` duy nhất, DFS từ 0 thăm cả hai đỉnh. Hai đỉnh có chắc cùng SCC không?

*Đáp án:* **Không**; không có đường có hướng từ 1 tới 0. Rừng DFS không phải thuật toán SCC.

**Bài 8 — Chu trình gốc.** Đồ thị có chu trình `0→1→2→0` nhưng parent của BFS từ 0 là `parent[1]=0`, `parent[2]=1`. Có chu trình trong cây cha không?

*Đáp án:* **Không**. Cạnh `2→0` không trở thành cạnh cha vì 0 đã thăm; chuỗi cha vẫn kết thúc ở nguồn.

**Bài 9 — Tính đúng.** Vì sao mỗi cạnh cha `parent[v]→v` chắc chắn tồn tại thật trong graph?

*Đáp án:* Vì parent[v] chỉ được gán từ u khi thuật toán đang xét **cạnh thật u→v** ở thời điểm khám phá v.

**Bài 10 — Độ phức tạp.** Nếu cần một đường đi từ cùng nguồn tới 100 đích, nên chạy BFS 100 lần không?

*Đáp án:* **Không cần** khi graph và nguồn giữ nguyên. Chạy BFS một lần O(V+E) để có parent, depth; mỗi đích truy vết trong O(độ dài đường xuất ra).

**Tổng kết:** **Cây duyệt** gồm những cạnh phát hiện một đỉnh **lần đầu**, mỗi đỉnh tới được khác nguồn có một **parent** và mọi chuỗi parent đều quay về gốc. **Khôi phục đường đi** bằng cách đi ngược parent từ đích rồi đảo danh sách; phải kiểm tra **reachability** và phân biệt nguồn với đỉnh chưa tới được. **BFS** cho đường ít cạnh nhất trên đồ thị không trọng số, còn **DFS** cho một đường hợp lệ không nhất thiết ngắn nhất. Duyệt từ nhiều gốc tạo **rừng duyệt**; ở đồ thị vô hướng nó mô tả các thành phần liên thông, còn ở đồ thị có hướng không tự thay thế thuật toán SCC.
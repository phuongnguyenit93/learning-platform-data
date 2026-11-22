# Thuật toán Hopcroft–Karp

**Hopcroft–Karp** là thuật toán tìm **ghép cặp cực đại** (*maximum matching*) trong **đồ thị hai phía** (*bipartite graph*). Thuật toán tăng dần số cạnh ghép thông qua các **đường tăng** (*augmenting paths*), nhưng không tìm một đường tùy ý sau mỗi bước: nó dùng **BFS** để dựng các lớp của **những đường tăng ngắn nhất hiện tại**, rồi dùng **DFS** để tăng ghép theo một tập lớn đường tăng ở cùng độ dài ấy. Chiến lược chia thành các **pha BFS–DFS** giúp đạt độ phức tạp kinh điển **`O(E√V)`** (thêm chi phí khởi tạo/đỉnh cô lập tùy mô hình triển khai), nhanh hơn cách tìm từng đường tăng O(VE) trong nhiều trường hợp.

Bài thuộc chủ đề **Ghép cặp và phân công**. Các mô hình ứng dụng gồm ghép học sinh với công việc có thể làm, phân công người–ca trực, ghép đơn hàng–tài nguyên, ghép máy–nhiệm vụ, hoặc các bài “chọn được nhiều cặp nhất sao cho mỗi đối tượng dùng tối đa một lần”. **Điểm quan trọng:** Hopcroft–Karp **tối đa hóa số cặp**, không tối ưu chi phí/trọng số của từng cặp. Nếu mỗi phương án ghép có tiền lương, khoảng cách, mức ưu tiên hoặc điểm lợi ích khác nhau, đó là bài **ghép cặp có trọng số/assignment** cần thuật toán khác.

Bài sẽ đi từ định nghĩa matching, phân biệt **maximal** với **maximum**, đường luân phiên và đường tăng, định lý Berge, cơ chế BFS layering + DFS, chứng minh chính xác và độ phức tạp, cài đặt **Java 17+ độc lập**, truy xuất **phủ đỉnh nhỏ nhất** theo định lý König, xử lý hai phía rỗng/cạnh trùng/đỉnh cô lập, so với Kuhn và luồng cực đại, và kiểm thử đối chiếu với vét cạn.

**Kết quả học tập:** sau bài này có thể tự cài Hopcroft–Karp cho đồ thị hai phía có chỉ số 0-based, đọc được mảng ghép `pairLeft/pairRight`, lý giải vì sao DFS chỉ đi theo lớp BFS, phân biệt ghép cực đại với ghép tối đại, tính phủ đỉnh nhỏ nhất từ matching cuối cùng và biết các giới hạn cần lưu ý trước khi dùng trong thực tế.

## 1. Đồ thị hai phía và định nghĩa ghép cặp

Một đồ thị hai phía có thể viết:

**`G=(L∪R,E)`**, với **`L∩R=∅`**, và mọi cạnh nối một đỉnh **bên trái L** với một đỉnh **bên phải R**. Không có cạnh nối hai đỉnh cùng phía.

Ta đánh số riêng:

- `L={0,1,...,n_L−1}`, ứng với ứng viên/người/máy.
- `R={0,1,...,n_R−1}`, ứng với công việc/ca trực/tài nguyên.
- Một cạnh `(u,v)` nghĩa là đối tượng trái u **được phép** ghép với đối tượng phải v.

Trong phiên bản code, cạnh được lưu **theo chiều dữ liệu từ trái sang phải** để tiện duyệt adjacency list. Đồ thị hai phía về mặt khái niệm là **vô hướng**, không phải một mạng luồng có hướng tùy ý: khi tìm đường tăng, ta có thể đi từ trái sang phải trên cạnh chưa ghép và đi ngược trên cạnh đã ghép.

Một **matching** `M⊆E` là tập cạnh sao cho **không có hai cạnh nào cùng chung đầu mút**. Mỗi đỉnh trái hoặc phải xuất hiện trong **tối đa một** cặp ghép.

**Kích thước matching** là số cạnh được chọn: **`|M|`**.

Matching gọi là **maximum** nếu `|M|` lớn nhất trong tất cả các matching. Chú ý: mục tiêu là số cặp, không phải tổng số đỉnh đã ghép (dù giá trị ấy bằng `2|M|`).

### Maximal khác maximum

- **Maximal matching (ghép cặp tối đại):** không thể **thêm một cạnh mới vào ngay** mà vẫn giữ các cạnh đang ghép.
- **Maximum matching (ghép cặp cực đại):** không tồn tại matching khác có **nhiều cạnh hơn**.

Mọi maximum matching đều maximal, nhưng **maximal chưa chắc maximum**.

Ví dụ:

~~~text
Trái                Phải

L0 ---- R0
  \     
   \--- R1

L1 ---- R0
~~~

Các cạnh: `(0,0),(0,1),(1,0)`.

Matching `M={(0,0)}` là **maximal**: không còn một cạnh có cả hai đầu chưa ghép. Nhưng nó **không maximum**, vì có thể thay thành `M'={(0,1),(1,0)}` gồm **2 cặp**.

Một chương trình tham lam duyệt mỗi đỉnh trái một lần và chọn đỉnh phải tự do đầu tiên chỉ bảo đảm một matching hợp lệ; để đạt maximum, nó cần khả năng **đổi lại các cặp ghép cũ** qua đường tăng.

### Ghép hoàn hảo và ghép bao phủ phía trái

- **Ghép bao phủ L** (*left-perfect matching*) khi mọi đỉnh trái được ghép; khi đó `|M|=n_L`, bắt buộc `n_R≥n_L`.
- **Perfect matching** đúng nghĩa bao phủ **mọi đỉnh của cả hai phía**; đòi `n_L=n_R` và `|M|=n_L=n_R`.
- Nếu hai phía không cùng số đỉnh, matching cực đại vẫn có thể rất lớn mà không phải perfect.

Một đỉnh **cô lập** (không có cạnh) không thể tham gia matching. Bất kể thuật toán nào cũng không thể “tự ghép” nó với đỉnh khác.

## 2. Đường luân phiên và đường tăng

Với matching hiện tại M:

- **Cạnh ghép** là cạnh thuộc M.
- **Cạnh chưa ghép** là cạnh thuộc `E\M`.
- **Đường luân phiên** (*alternating path*) là đường có các cạnh **xen kẽ** ghép/chưa ghép.
- **Đường tăng** (*augmenting path*) là một đường luân phiên bắt đầu ở **đỉnh chưa ghép**, kết thúc ở **đỉnh chưa ghép phía đối diện**, với cạnh đầu/cuối đều **chưa ghép**.

Trong đồ thị hai phía, đường tăng bắt đầu ở một đỉnh tự do phía L và kết thúc ở một đỉnh tự do phía R, nên số cạnh trên đường tăng là **số lẻ**: 1,3,5,...

### Lật các cạnh trên đường tăng

Giả sử đường tăng P có k cạnh chưa ghép và k−1 cạnh đã ghép. Ta **lật** trạng thái các cạnh trên P:

**`M' = M △ E(P)`**,

với `△` là **hiệu đối xứng** (*symmetric difference*): cạnh trong đúng một tập sẽ nằm trong kết quả.

Hệ quả:

- Hai đầu P vốn tự do nay mỗi đầu được ghép một lần.
- Mỗi đỉnh bên trong P trước/sau đều có đúng một cạnh ghép trong đường.
- Những cạnh ngoài P không thay đổi.
- Kích thước tăng **đúng 1**: `|M'|=|M|+1`.

Vậy nếu còn một đường tăng, M **không thể** là ghép cực đại.

### Ví dụ buộc phải thay các cặp cũ

Có ba đỉnh trái L0,L1,L2 và ba đỉnh phải R0,R1,R2, với cạnh:

- L0–R0, L0–R1.
- L1–R0.
- L2–R1, L2–R2.

Giả sử matching tạm:

**`M={(L0,R0),(L2,R1)}`**, còn L1 và R2 chưa ghép.

Từ L1, ta tìm được đường tăng:

~~~text
L1 -- R0 == L0 -- R1 == L2 -- R2

-- : cạnh chưa ghép
== : cạnh đang ghép
~~~

Đường có 5 cạnh: chưa ghép, ghép, chưa ghép, ghép, chưa ghép.

Lật cạnh cho:

**`M'={(L1,R0),(L0,R1),(L2,R2)}`**,

tức **3 cặp**. Không có bước nào “đòi hai đỉnh phải cho cùng một đỉnh trái”: các cạnh cũ trên đường được bỏ đúng lúc khi cạnh mới được thêm.

**Bài học:** một matching không tăng được bằng cách **thêm cạnh trực tiếp** vẫn có thể tăng thông qua chuỗi **đổi cặp**.

## 3. Định lý Berge: điều kiện dừng chính xác

**Định lý Berge:** matching M là **maximum** khi và chỉ khi **không tồn tại đường tăng đối với M**.

**Chiều dễ:** nếu tồn tại đường tăng, lật cạnh làm `|M|` tăng 1 ⇒ M không maximum.

**Chiều ngược:** giả sử M chưa maximum. Tồn tại matching `M*` có `|M*|>|M|`. Xét đồ thị chỉ gồm những cạnh xuất hiện trong **đúng một** trong hai matching: `M△M*`. Vì mỗi matching dùng tối đa một cạnh tại một đỉnh, mỗi đỉnh trong đồ thị hiệu đối xứng có bậc không quá 2. Các thành phần của nó là những đường hoặc chu trình **luân phiên** giữa cạnh của M và M*.

Tổng số cạnh của M* lớn hơn M, nên phải có ít nhất một thành phần chứa **nhiều cạnh M*** hơn cạnh M. Thành phần ấy là **đường luân phiên bắt đầu/kết thúc bằng cạnh M***, có hai đầu tự do đối với M; chính là **đường tăng của M**.

Do đó nếu không còn đường tăng thì M đã là maximum.

Đây là cơ sở tính đúng của nhiều thuật toán matching như **Kuhn** và **Hopcroft–Karp**. Điểm khác biệt chủ yếu là **tìm và xử lý các đường tăng như thế nào**, không phải định lý tối ưu cuối cùng.

## 4. Vì sao Hopcroft–Karp xử lý đường tăng theo pha?

Cách đơn giản: tìm một đường tăng bất kỳ bằng DFS, lật nó, rồi tìm tiếp. Cách này vẫn đúng nhưng trong trường hợp xấu có thể phải tìm/duyệt lại nhiều cạnh sau mỗi lần tăng, dẫn đến cận **O(VE)** cho một cách cài DFS tăng ghép cơ bản.

Hopcroft–Karp cải tiến bằng hai thao tác kết hợp:

1. **BFS:** xác định **độ dài ngắn nhất** của một đường tăng còn tồn tại, đồng thời gán các **lớp** cho đỉnh trái sao cho DFS biết chuyển tiếp nào là hợp lệ.
2. **DFS:** trong lớp vừa tạo, tìm nhiều đường tăng **ngắn nhất** có thể dùng trong cùng pha, lật matching khi tìm thấy và cắt nhánh thất bại.

Sau khi thực hiện một tập tối đại các đường tăng ngắn nhất trong pha, **độ dài đường tăng ngắn nhất còn lại sẽ tăng**. Vì không cần tăng matching lần lượt qua một phép duyệt đồ thị đầy đủ cho từng đường, số pha có thể bị chặn bằng O(√V).

Mỗi pha là **một lần BFS và nhiều DFS**, không phải “một BFS trước mỗi lần tìm một đường tăng”.

### Lưu ý về đường ngắn nhất

Đường tăng ngắn nhất ở đây là **ít cạnh nhất**, không phải nhỏ nhất theo trọng số, chi phí hay khoảng cách hình học. Đồ thị trong bài là **không trọng số**. Nếu bài yêu cầu matching tối đa về tổng lợi ích, không thể tùy ý gắn trọng số rồi vẫn dùng Hopcroft–Karp nguyên bản để tối ưu tổng ấy.

## 5. Biểu diễn matching bằng hai mảng

Với hai phía riêng:

- `pairLeft[u]` là đỉnh phải hiện ghép với đỉnh trái u; nếu chưa ghép là **−1**.
- `pairRight[v]` là đỉnh trái hiện ghép với đỉnh phải v; nếu chưa ghép là **−1**.

Bất biến:

**`pairLeft[u]=v ⇔ pairRight[v]=u`.**

Bắt đầu mọi phần tử là −1, matching rỗng.

Nếu DFS tìm được đường tăng và chọn cạnh u–v ở đoạn cuối khi v chưa ghép hoặc đã **giải phóng** bằng tăng ghép đệ quy, cập nhật:

~~~text
pairLeft[u] = v
pairRight[v] = u
~~~

Các lời gọi DFS đệ quy trả về theo đường tăng và lần lượt cập nhật lại những cặp cũ. Mỗi đỉnh vẫn được ghép tối đa một lần.

### Vì sao chỉ lưu adjacency từ phía trái?

Trong phiên bản chuyên biệt cho đồ thị hai phía, mỗi đường tăng luôn đi:

**L → R qua một cạnh**; nếu R đã ghép thì quay về **L đang là bạn ghép của R**.

Do đó chỉ cần:

- `adj[u]`: danh sách tất cả v phía phải được nối với u.
- `pairRight[v]`: biết R v ghép với đỉnh trái nào để tiếp tục.

Không cần xây một mạng residual tường minh để thực hiện các bước này. Việc rẽ qua `pairRight[v]` chính là bước đi ngược trên **cạnh đã ghép** trong đồ thị luân phiên.

## 6. BFS dựng lớp ngắn nhất của các đường tăng

BFS bắt đầu **đồng thời từ mọi đỉnh trái đang tự do**:

- Nếu `pairLeft[u]=−1`, đặt `dist[u]=0` và đưa u vào queue.
- Nếu u đã ghép, đặt `dist[u]=INF` (chưa được gán lớp trong pha).
- Đặt `shortest=INF`, biểu diễn lớp của **đích ảo NIL** — một đỉnh phải tự do bất kỳ.

Khi lấy đỉnh trái u khỏi queue, chỉ mở rộng nếu `dist[u]<shortest`. Với mỗi đỉnh phải v thuộc `adj[u]`:

- Nếu `pairRight[v]=−1`, ta đã tìm được một đường tăng kết thúc ở R tự do, có chỉ số lớp **`dist[u]+1`**. Cập nhật `shortest=min(shortest,dist[u]+1)`.
- Nếu v đã ghép với một đỉnh trái x và `dist[x]=INF`, gán `dist[x]=dist[u]+1` và thêm x vào queue.

BFS thành công khi `shortest≠INF`. Nếu không có đỉnh phải tự do nào đạt tới theo những bước luân phiên hợp lệ, không còn đường tăng ⇒ matching hiện tại là maximum.

### Vì sao dist chỉ lưu cho phía trái?

Mỗi lần ta đi từ đỉnh trái u qua v phía phải **đã ghép** rồi quay sang bạn ghép x phía trái, ta coi đó là một bước tăng lớp:

**`dist[x]=dist[u]+1`.**

Vì thế `dist[u]` đếm số “chuyển tiếp qua đỉnh phải đã ghép” từ một trái tự do đến u, chứ **không phải** số cạnh thực tế trên đường luân phiên.

Nếu từ u đang ở lớp d nối được trực tiếp tới một đỉnh phải tự do, `shortest=d+1`. Đường tăng thực tế tương ứng gồm **`2·shortest−1` cạnh**: mỗi lớp trước đó đi qua một cạnh chưa ghép và một cạnh ghép, rồi kết thúc bằng cạnh chưa ghép cuối cùng.

Ví dụ đường tăng L1–R0–L0–R1–L2–R2 có 5 cạnh thực, nhưng:

- `dist[L1]=0`.
- `dist[L0]=1`.
- `dist[L2]=2`.
- `shortest=3`.

Công thức `2·3−1=5` khớp.

### Pseudocode BFS

~~~text
bfs():
    queue = empty
    shortest = INF

    for each left vertex u:
        if pairLeft[u] == -1:
            dist[u] = 0
            queue.push(u)
        else:
            dist[u] = INF

    while queue not empty:
        u = queue.pop()
        if dist[u] >= shortest:
            continue

        for v in adj[u]:
            x = pairRight[v]
            if x == -1:
                shortest = min(shortest, dist[u] + 1)
            else if dist[x] == INF:
                dist[x] = dist[u] + 1
                queue.push(x)

    return shortest != INF
~~~

**Không được BFS mọi cạnh như đường đi thông thường trên đồ thị hai phía rồi bỏ qua trạng thái ghép.** Cấu trúc lớp phải phản ánh **cạnh luân phiên**: từ L qua R chưa ghép với L, rồi từ R đã ghép quay lại **đúng bạn ghép**.

### Vì sao dừng mở rộng ở lớp sâu hơn shortest?

Mục tiêu của pha là tìm các đường tăng **ngắn nhất hiện tại**. Khi đã phát hiện một đích phải tự do ở lớp shortest, việc tiếp tục mở rộng những đỉnh trái có dist≥shortest không thể tạo đường tăng ngắn hơn hoặc bằng shortest. Ta có thể cắt để tiết kiệm duyệt.

BFS vẫn cần xem hết các lựa chọn ở lớp **nhỏ hơn shortest** để ghi đủ các đường ngắn nhất cho DFS, không được dừng toàn bộ BFS ngay khi tìm **một** đích tự do.

## 7. DFS tăng ghép theo các lớp đã xây

Trong cùng một pha, với từng đỉnh trái u đang tự do, gọi `dfs(u)`. DFS chỉ được đi theo các quy tắc:

- Nếu cạnh u–v tới một đỉnh phải **chưa ghép**, chỉ chấp nhận kết thúc đường khi **`dist[u]+1=shortest`**.
- Nếu v **đã ghép** với x, chỉ đi tiếp bằng `dfs(x)` khi **`dist[x]=dist[u]+1`**, tức từ lớp d sang d+1.
- Nếu mọi cạnh đều thất bại, đặt **`dist[u]=INF`** để đánh dấu u là “ngõ cụt trong phần graph của pha này” và không tốn công thử lại cùng trạng thái.

Pseudocode:

~~~text
dfs(u):
    for v in adj[u]:
        x = pairRight[v]

        if x == -1:
            if dist[u] + 1 == shortest:
                pairLeft[u] = v
                pairRight[v] = u
                return true

        else if dist[x] == dist[u] + 1 and dfs(x):
            pairLeft[u] = v
            pairRight[v] = u
            return true

    dist[u] = INF
    return false
~~~

Khi DFS trả true, các bước ngược dòng cập nhật matching. Nó **không** chỉ đơn giản “chọn thêm cạnh” mà có thể hoán đổi nhiều cặp trên đường tăng.

### Một pha hoàn chỉnh

~~~text
matchingSize = 0

while bfs():
    for each left vertex u:
        if pairLeft[u] == -1:
            if dfs(u):
                matchingSize++

return matchingSize
~~~

Mỗi lần `dfs(u)` thành công là một lần lật đường tăng, tăng cardinality **đúng 1**. Trong một pha có thể thành công nhiều lần. Khi BFS tiếp theo trả false, không còn đường tăng và kết quả là cực đại theo định lý Berge.

### Tại sao DFS không tạo vòng lặp vô hạn?

Nếu đi qua đỉnh phải đã ghép để gọi DFS ở một đỉnh trái khác, điều kiện bắt buộc là:

**`dist[nextLeft]=dist[currentLeft]+1`**.

Lớp tăng nghiêm ngặt qua mỗi lời gọi. Trong một pha, số lớp hữu hạn nên không thể quay lại một đỉnh trái đã gặp trên đường DFS hiện tại. Đây là lý do không cần một mảng visited toàn cục riêng chỉ để ngăn DFS quay vòng.

### Vì sao có thể đặt dist[u]=INF khi thất bại?

Nếu không thể hoàn tất một đường tăng ngắn nhất từ u qua các cạnh hợp lệ của lớp, mọi DFS khác trong **cùng pha** không cần thử lại ngõ cụt u. Gán INF là thao tác cắt nhánh; **không** thay đổi matching. Sang pha tiếp theo, BFS sẽ tính lại toàn bộ dist, nên việc cắt nhánh của pha trước không làm mất một đường tăng hợp lệ mới xuất hiện sau này.

### Một chi tiết quan trọng về rủi ro stack

DFS đệ quy có độ sâu bằng số đỉnh trái trên đường tăng đang xét, có thể lên tới **O(V)** trong một đồ thị đặc biệt. Mã Java 17 dưới đây là phiên bản đệ quy dễ đọc theo thuật toán chuẩn; nếu đầu vào rất lớn và độ sâu DFS có thể vượt giới hạn stack, cần chuyển DFS sang **stack tường minh** hoặc có chiến lược cấu hình stack phù hợp sau khi đo đạc. Không thể kết luận “vì Hopcroft–Karp có O(√V) pha nên độ sâu một DFS chỉ O(√V)” — hai đại lượng khác nhau.

## 8. Ví dụ đầy đủ hai pha: đường tăng dài sau lượt đầu

Cho cạnh theo thứ tự:

~~~text
L0: R0, R1
L1: R0
L2: R1, R2
~~~

Ban đầu matching rỗng. BFS đầu tiên đặt dist=0 cho L0,L1,L2. Vì có cạnh trực tiếp từ nhiều đỉnh trái tự do tới R tự do, `shortest=1`.

Trong DFS pha 1 theo thứ tự trái:

- L0 ghép R0.
- L1 thử R0 nhưng R0 đã ghép L0; L0 ở dist=0, không phải lớp dist[L1]+1=1, nên không đi sâu; L1 chưa ghép.
- L2 ghép R1.

Matching sau pha 1:

**`M={(L0,R0),(L2,R1)}`**, kích thước 2.

BFS pha 2:

1. L1 là đỉnh trái duy nhất tự do, dist[L1]=0.
2. L1→R0, R0 ghép L0 ⇒ dist[L0]=1.
3. L0→R1, R1 ghép L2 ⇒ dist[L2]=2.
4. L2→R2, R2 tự do ⇒ `shortest=3`, đường tăng gồm 5 cạnh thực.

DFS pha 2 lật:

~~~text
L1 -- R0 == L0 -- R1 == L2 -- R2
~~~

Matching mới:

**`M={(L0,R1),(L1,R0),(L2,R2)}`**, kích thước 3.

BFS pha 3 không còn đỉnh trái tự do, trả false ngay. Kết quả:

- `matchingSize=3`.
- `pairLeft=[1,0,2]`.
- `phases=2` (chỉ đếm các pha có BFS trả true).

Ví dụ này minh họa **không đủ chỉ tìm những cạnh trực tiếp từ trái tự do tới phải tự do**. Cần những đường luân phiên dài hơn để hoàn thiện matching.

## 9. Vì sao nhiều đường tăng trong một pha nhanh hơn?

Trong một pha, các đường tăng đã tìm được đều có **độ dài ngắn nhất**. DFS có thể thay matching để lấy một tập nhiều đường tăng không tranh chấp đỉnh trong phần xử lý lớp. Khi không còn đường ngắn nhất nào có thể tăng thêm trong cấu trúc lớp hiện hành, pha kết thúc. Pha sau BFS mới thấy đường tăng ngắn nhất còn lại có độ dài lớn hơn.

Cốt lõi của phân tích lý thuyết:

1. **Mỗi pha tốn O(V+E)** cho BFS cùng công việc DFS trên các cạnh/lớp (với cắt nhánh ngõ cụt đúng cách).
2. **Độ dài đường tăng ngắn nhất tăng nghiêm ngặt sau mỗi pha**; gọi độ dài này là ℓ.
3. Với ngưỡng khoảng `√V`, số pha khi ℓ còn nhỏ là **O(√V)** vì ℓ tăng theo số nguyên.
4. Khi mọi đường tăng còn lại dài hơn `√V`, số lần tăng tiếp để đạt matching tối ưu cũng chỉ còn **O(√V)**.

Lý do của bước 4: xét hiệu đối xứng giữa matching hiện tại M và matching tối ưu M*. Các thành phần làm tăng cardinality là những đường tăng **rời nhau về đỉnh**. Mỗi đường tăng còn lại dài hơn √V chiếm **Ω(√V)** đỉnh riêng, nên với tổng V đỉnh chỉ có thể có **O(√V)** đường như vậy. Số lượng cần tăng bằng `|M*|−|M|` nên cũng bị chặn tương ứng.

Ghép hai giai đoạn ta có **O(√V) pha**, mỗi pha O(E) trên phần đồ thị có cạnh với chi phí khởi tạo đỉnh, cho cận quen thuộc:

**`O(E√V)`** với `V=|L|+|R|` trong mô hình thường dùng, hoặc **`O((V+E)√V)`** là cận bảo thủ rõ cả chi phí quét đỉnh cô lập trong từng pha.

**Bộ nhớ O(V+E):** các adjacency lists, mảng pairLeft/pairRight, dist và hàng đợi BFS. Các mảng output/cover vẫn là O(V).

### Vì sao không phải O(VE) trong mọi trường hợp?

Thuật toán tìm từng đường tăng có thể cần tìm O(V) lần, mỗi lần O(E); Hopcroft–Karp tận dụng các đường ngắn nhất theo **lô**. Nhưng điều này không có nghĩa mọi bộ dữ liệu sẽ thấy nhanh hơn: đồ thị rất nhỏ hoặc số cạnh ít có thể khiến code Kuhn đơn giản có chi phí thực tế cạnh tranh hơn.

### Bản Java không có con trỏ cạnh DFS riêng

Mã minh họa dùng DFS chuẩn với `dist[u]=INF` khi thất bại. Việc cắt những nhánh ngõ cụt theo lớp giúp đạt tổng công việc DFS O(E) mỗi pha theo phân tích Hopcroft–Karp chuẩn. Một biến thể khác dùng “current arc”/iterator ở mỗi đỉnh trái để tránh duyệt lại cạnh trong pha; khi áp dụng cần xử lý đúng việc matching bị lật và reset con trỏ ở đầu pha. Không cần đưa thêm cấu trúc ấy vào code để giải thích ý tưởng chính.

## 10. Java 17+ hoàn chỉnh: matching, cặp ghép và phủ đỉnh

Chương trình sau nhận `nLeft,nRight≥0`, và danh sách cạnh `(left,right)`. Cả hai phía **đánh số riêng từ 0**. Để tránh nhầm, nếu L0 và R0 có cùng chỉ số 0, chúng vẫn là **hai đỉnh khác nhau**.

**Hợp đồng dữ liệu:**

- Cho phép **cạnh trùng** (nhiều lần liệt kê cùng cặp left,right). Chúng không giúp một đỉnh được ghép hai lần; kết quả maximum matching theo cặp đỉnh không đổi.
- Cho phép **đỉnh cô lập**, một phía rỗng, hoặc toàn bộ E rỗng.
- Không cho phép chỉ số âm hoặc vượt `nLeft/nRight`; `nLeft,nRight` không âm; edge null bị từ chối.
- Bài chỉ hỗ trợ đồ thị **hai phía đã biết phân hoạch**. Nếu input là đồ thị vô hướng tổng quát, phải kiểm tra tô hai màu và lấy phân hoạch trước khi áp dụng.
- Nếu graph **không hai phía**, thuật toán này không thay thế thuật toán Blossom cho maximum matching tổng quát.
- Không có trọng số trên cạnh, không xử lý bài minimum-cost matching.

Kết quả từ `solve`:

- `size`: số cặp trong maximum matching.
- `pairs`: các chuỗi “L-index–R-index” theo thứ tự trái tăng dần, giúp thấy rõ một matching cụ thể.
- `coverL` và `coverR`: phủ đỉnh nhỏ nhất của đồ thị hai phía, sẽ giải thích ở mục tiếp.
- `phases`: số pha BFS thành công và có chạy DFS (không tính BFS cuối cùng trả false).

Lưu thành **`HopcroftKarpDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class HopcroftKarpDemo {
    private static final int INF = Integer.MAX_VALUE;

    private record Edge(int left, int right) {}

    private record Result(
            int size,
            List<String> pairs,
            List<Integer> coverL,
            List<Integer> coverR,
            int phases) {}

    private static final class Solver {
        private final int nLeft;
        private final int nRight;
        private final List<Integer>[] adj;
        private final int[] pairLeft;
        private final int[] pairRight;
        private final int[] dist;
        private int shortest;
        private int phases;

        @SuppressWarnings("unchecked")
        Solver(int nLeft, int nRight) {
            if (nLeft < 0 || nRight < 0) {
                throw new IllegalArgumentException(
                        "Partition sizes must be nonnegative");
            }
            this.nLeft = nLeft;
            this.nRight = nRight;
            adj = (List<Integer>[]) new List[nLeft];
            for (int u = 0; u < nLeft; u++) {
                adj[u] = new ArrayList<>();
            }
            pairLeft = new int[nLeft];
            pairRight = new int[nRight];
            dist = new int[nLeft];
            Arrays.fill(pairLeft, -1);
            Arrays.fill(pairRight, -1);
        }

        void addEdge(int u, int v) {
            if (u < 0 || u >= nLeft
                    || v < 0 || v >= nRight) {
                throw new IllegalArgumentException(
                        "Bipartite edge out of range");
            }
            // Duplicate pairs are harmless for cardinality.
            adj[u].add(v);
        }

        private boolean bfs() {
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            shortest = INF;

            for (int u = 0; u < nLeft; u++) {
                if (pairLeft[u] == -1) {
                    dist[u] = 0;
                    queue.addLast(u);
                } else {
                    dist[u] = INF;
                }
            }

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                if (dist[u] >= shortest) {
                    continue;
                }

                for (int v : adj[u]) {
                    int matchedLeft = pairRight[v];
                    if (matchedLeft == -1) {
                        // The virtual NIL endpoint is reached.
                        shortest = Math.min(
                                shortest, dist[u] + 1);
                    } else if (dist[matchedLeft] == INF) {
                        dist[matchedLeft] = dist[u] + 1;
                        queue.addLast(matchedLeft);
                    }
                }
            }
            return shortest != INF;
        }

        private boolean dfs(int u) {
            for (int v : adj[u]) {
                int matchedLeft = pairRight[v];

                if (matchedLeft == -1) {
                    if (dist[u] + 1 == shortest) {
                        pairLeft[u] = v;
                        pairRight[v] = u;
                        return true;
                    }
                } else if (dist[matchedLeft] == dist[u] + 1
                        && dfs(matchedLeft)) {
                    pairLeft[u] = v;
                    pairRight[v] = u;
                    return true;
                }
            }

            dist[u] = INF; // Prune failed layer states.
            return false;
        }

        // By Konig's theorem, a min vertex cover can be built
        // from alternating reachability after max matching.
        private Result buildResult(int size) {
            boolean[] seenLeft = new boolean[nLeft];
            boolean[] seenRight = new boolean[nRight];
            ArrayDeque<Integer> queue = new ArrayDeque<>();

            for (int u = 0; u < nLeft; u++) {
                if (pairLeft[u] == -1) {
                    seenLeft[u] = true;
                    queue.addLast(u);
                }
            }

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();

                for (int v : adj[u]) {
                    // L -> R only along an UNMATCHED edge.
                    if (pairLeft[u] == v) {
                        continue;
                    }
                    if (!seenRight[v]) {
                        seenRight[v] = true;
                        int matchedLeft = pairRight[v];
                        // R -> L only along the MATCHED edge.
                        if (matchedLeft != -1
                                && !seenLeft[matchedLeft]) {
                            seenLeft[matchedLeft] = true;
                            queue.addLast(matchedLeft);
                        }
                    }
                }
            }

            List<String> pairs = new ArrayList<>();
            List<Integer> coverL = new ArrayList<>();
            List<Integer> coverR = new ArrayList<>();

            for (int u = 0; u < nLeft; u++) {
                if (pairLeft[u] != -1) {
                    pairs.add(u + "-" + pairLeft[u]);
                }
                if (!seenLeft[u]) {
                    coverL.add(u);
                }
            }
            for (int v = 0; v < nRight; v++) {
                if (seenRight[v]) {
                    coverR.add(v);
                }
            }

            if (coverL.size() + coverR.size() != size) {
                throw new IllegalStateException(
                        "Konig certificate mismatch");
            }

            return new Result(
                    size, List.copyOf(pairs),
                    List.copyOf(coverL),
                    List.copyOf(coverR), phases);
        }

        Result run() {
            int size = 0;
            phases = 0;

            while (bfs()) {
                phases++;
                for (int u = 0; u < nLeft; u++) {
                    if (pairLeft[u] == -1 && dfs(u)) {
                        size++;
                    }
                }
            }
            return buildResult(size);
        }
    }

    static Result solve(
            int nLeft, int nRight, Edge... edges) {
        if (edges == null) {
            throw new IllegalArgumentException(
                    "Edge list must not be null");
        }
        Solver solver = new Solver(nLeft, nRight);
        for (Edge e : edges) {
            if (e == null) {
                throw new IllegalArgumentException(
                        "Null bipartite edge");
            }
            solver.addEdge(e.left(), e.right());
        }
        return solver.run();
    }

    private static void show(
            String name, int nLeft, int nRight, Edge... edges) {
        Result result = solve(nLeft, nRight, edges);
        System.out.println(
                name + ": size=" + result.size()
                + ", pairs=" + result.pairs()
                + ", coverL=" + result.coverL()
                + ", coverR=" + result.coverR()
                + ", phases=" + result.phases());
    }

    public static void main(String[] args) {
        show("Reroute", 3, 3,
                new Edge(0, 0), new Edge(0, 1),
                new Edge(1, 0), new Edge(2, 1),
                new Edge(2, 2));

        show("Partial", 4, 3,
                new Edge(0, 0), new Edge(1, 0),
                new Edge(2, 1), new Edge(3, 1));

        show("Mixed cover", 4, 4,
                new Edge(0, 0), new Edge(1, 1),
                new Edge(2, 1), new Edge(3, 2),
                new Edge(3, 3));

        show("No edges", 3, 2);

        show("Duplicates", 2, 2,
                new Edge(0, 0), new Edge(0, 0),
                new Edge(1, 0), new Edge(1, 1));

        show("Empty left", 0, 3);
        show("Empty right", 3, 0);

        show("Alternating", 3, 3,
                new Edge(0, 0), new Edge(1, 0),
                new Edge(1, 1), new Edge(2, 1));

        show("Complete", 3, 3,
                new Edge(0, 0), new Edge(0, 1),
                new Edge(0, 2), new Edge(1, 0),
                new Edge(1, 1), new Edge(1, 2),
                new Edge(2, 0), new Edge(2, 1),
                new Edge(2, 2));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac HopcroftKarpDemo.java
java HopcroftKarpDemo
~~~

**Stdout chính xác** với thứ tự cạnh trong mã:

~~~text
Reroute: size=3, pairs=[0-1, 1-0, 2-2], coverL=[0, 1, 2], coverR=[], phases=2
Partial: size=2, pairs=[0-0, 2-1], coverL=[], coverR=[0, 1], phases=1
Mixed cover: size=3, pairs=[0-0, 1-1, 3-2], coverL=[0, 3], coverR=[1], phases=1
No edges: size=0, pairs=[], coverL=[], coverR=[], phases=0
Duplicates: size=2, pairs=[0-0, 1-1], coverL=[0, 1], coverR=[], phases=1
Empty left: size=0, pairs=[], coverL=[], coverR=[], phases=0
Empty right: size=0, pairs=[], coverL=[], coverR=[], phases=0
Alternating: size=2, pairs=[0-0, 1-1], coverL=[], coverR=[0, 1], phases=1
Complete: size=3, pairs=[0-0, 1-1, 2-2], coverL=[0, 1, 2], coverR=[], phases=1
~~~

### Tại sao stdout là một matching cụ thể, không phải mọi matching?

Matching cực đại có thể **không duy nhất**. Mã đi theo thứ tự u tăng dần, còn mỗi adjacency list giữ thứ tự cạnh nhập. Vì thế nó đưa ra **một** matching cực đại tái lập được cho ví dụ cụ thể. Nếu đảo thứ tự cạnh, các cặp được chọn và số pha có thể thay đổi, nhưng **kích thước cực đại** và **kích thước phủ đỉnh nhỏ nhất** không đổi.

**Ví dụ Partial:** có 4 trái nhưng hai phải hữu ích R0,R1; matching tối đa chỉ có 2 cặp, và có nhiều cách phân công L0 hoặc L1 vào R0, L2 hoặc L3 vào R1. Code chọn `{L0–R0,L2–R1}`.

**Ví dụ Mixed cover:** ba cặp ghép được và một phủ đỉnh nhỏ nhất là `{L0,L3,R1}`, gồm đỉnh ở **cả hai phía**, chứ không chỉ toàn trái hoặc toàn phải.

**Ví dụ No edges/Empty partitions:** không có cặp nào khả thi, kết quả matching rỗng, phủ đỉnh rỗng, phases=0.

**Ví dụ Duplicates:** cùng cặp (0,0) được liệt kê hai lần; nó **không cho phép ghép L0 với R0 hai lần**. Mã vẫn chỉ ghép mỗi đỉnh tối đa một lần.

## 11. Phủ đỉnh nhỏ nhất (minimum vertex cover) từ matching

**Vertex cover** là một tập đỉnh C sao cho **mọi cạnh của đồ thị** có ít nhất một đầu mút thuộc C. Ta muốn phủ **ít đỉnh nhất**.

Định lý **König** trên đồ thị hai phía:

**`maximumMatchingSize = minimumVertexCoverSize`.**

Đây là một định lý đặc trưng của đồ thị hai phía; không áp dụng nguyên xi cho đồ thị bất kỳ. Chúng ta có thể dùng kết quả Hopcroft–Karp để **lấy một phủ đỉnh nhỏ nhất**, vừa hữu ích cho bài toán phụ, vừa là **chứng chỉ tối ưu độc lập** cho số cặp.

### Dựng phủ đỉnh theo đường luân phiên

Sau khi tìm xong matching maximum:

1. Đưa **mọi đỉnh trái chưa ghép** vào queue, đánh dấu `Z_L`.
2. Từ một đỉnh trái u đã thăm, đi qua **các cạnh chưa ghép** u–v để đánh dấu các đỉnh phải v vào `Z_R`.
3. Từ một đỉnh phải v đã thăm, nếu v đang ghép với đỉnh trái x, đi qua **chính cạnh đang ghép** v–x và đánh dấu x vào `Z_L`.
4. Lặp tới khi không còn đỉnh mới.

Khi đó một phủ đỉnh nhỏ nhất là:

**`C=(L\Z_L) ∪ Z_R`.**

Trong Java, `seenLeft=Z_L`, `seenRight=Z_R`. Vì vậy:

- `coverL` gồm các trái **không được thăm**.
- `coverR` gồm các phải **được thăm**.

### Vì sao công thức phủ mọi cạnh?

Xét cạnh (u,v):

- Nếu u không thuộc Z_L thì u thuộc `L\Z_L`, cạnh được phủ từ phía trái.
- Nếu u thuộc Z_L, mọi cạnh **chưa ghép** từ u sẽ dẫn đến v thuộc Z_R. Còn nếu cạnh (u,v) **đang ghép**, u hoặc là một đỉnh trái ghép được thăm qua chính v, nên v cũng thuộc Z_R (không có đỉnh trái tự do nào có cạnh ghép). Vì vậy cạnh được phủ từ phía phải.

Mọi cạnh được phủ.

### Vì sao cover nhỏ nhất?

Mỗi cạnh ghép cần một đầu mút trong bất kỳ vertex cover, và các cạnh ghép không chia sẻ đỉnh; do đó **mọi cover có ít nhất |M| đỉnh**.

Phép dựng bằng alternating reachability chọn **đúng một đầu mút của mỗi cạnh ghép** và **không chọn đỉnh thừa**: phía phải được thăm đều đang ghép (nếu có phải tự do đạt được thì đã tồn tại đường tăng, mâu thuẫn matching maximum). Vì thế số đỉnh cover bằng **|M|**.

Công thức đạt cận dưới ⇒ cover là **minimum**. Phép kiểm tra:

**`coverL.size()+coverR.size()==matchingSize`**

là kiểm tra nội bộ hữu ích nhưng **chưa đủ nếu không kiểm tra mọi cạnh đều được cover**. Bộ kiểm thử độc lập bên dưới kiểm cả hai.

### Ví dụ Mixed cover

Các cạnh:

`(0,0),(1,1),(2,1),(3,2),(3,3)`.

Matching từ code: `{(0,0),(1,1),(3,2)}`, còn L2 tự do.

Duyệt alternating từ L2:

- L2→R1 bằng cạnh chưa ghép.
- R1→L1 bằng cạnh đang ghép.
- Từ L1 không có cạnh chưa ghép khác.

Vậy:

`Z_L={L2,L1}`, `Z_R={R1}`.

Kết quả cover:

**`(L\Z_L)∪Z_R={L0,L3,R1}`**.

Ba đỉnh này phủ mọi cạnh và bằng matching size 3. Đây cũng là ví dụ lý giải tại sao cover nhỏ nhất không nhất thiết nằm toàn bộ bên trái hoặc toàn bộ bên phải.

## 12. Liên hệ định lý Hall và phân công đủ mọi người

**Định lý Hall:** trong đồ thị hai phía `(L,R,E)`, tồn tại một matching **bao phủ mọi đỉnh L** khi và chỉ khi với **mọi tập con S⊆L**:

**`|N(S)|≥|S|`**,

trong đó `N(S)` là tập các đỉnh phải kề ít nhất một đỉnh trong S.

Trực giác: bất kỳ nhóm S người nào cũng phải có đủ ít nhất |S| công việc khả dụng **khác nhau** để không phải cho hai người cùng một công việc.

Một mô hình thiếu Hall:

~~~text
L0 -- R0
L1 -- R0
L2 -- R1
L3 -- R1
~~~

Chọn S={L0,L1}, `N(S)={R0}` nên `|N(S)|=1<2=|S|`. Không thể ghép đủ hai người L0,L1, và càng không thể ghép đủ cả bốn trái. Hopcroft–Karp trả size=2.

### Liên hệ với alternating reachability

Nếu sau maximum matching vẫn còn đỉnh trái tự do, tập Z_L các đỉnh trái đạt được bằng alternating paths từ những trái tự do thường cung cấp **chứng cứ thiếu Hall**:

- Do matching đã maximum, không có đỉnh phải **tự do** nào đạt từ những trái tự do.
- Mọi đỉnh phải trong Z_R đều được ghép với một trái trong Z_L.
- Có ít nhất một đỉnh trái tự do ở Z_L.
- Do vậy **`|Z_L|>|Z_R|=|N(Z_L)|`**.

Tập Z_L vi phạm điều kiện Hall. Đây là cách hiểu tại sao **không thể** tăng số cặp thêm: một nhóm trái đang “tranh nhau” quá ít đỉnh phải.

**Lưu ý:** nếu mục tiêu là ghép đủ tất cả đỉnh L, chỉ cần kiểm `matchingSize==nLeft` sau Hopcroft–Karp, không cần liệt kê mọi tập S để tự kiểm định lý Hall (có tới `2^{nLeft}` tập con).

## 13. Giới hạn và biến thể cần phân biệt

### 13.1. Ghép cặp tối đa số lượng và ghép tối thiểu chi phí

Hopcroft–Karp tối ưu **số lượng cặp**. Nếu cần:

- Ghép được nhiều cặp nhất, sau đó tối thiểu tổng chi phí.
- Ghép 1–1 với n×n ma trận chi phí.
- Tối đa hóa tổng điểm phù hợp của những cặp được chọn.

thì cần mô hình có **trọng số/chi phí**. Các cách tiếp cận phù hợp có thể là **Hungarian algorithm** cho assignment, hoặc **min-cost max-flow** trong mạng phù hợp, với giả thiết/độ phức tạp riêng.

Không thể chạy Hopcroft–Karp rồi tin matching đầu tiên là minimum cost trong tất cả maximum matchings. Thứ tự duyệt cạnh quyết định **một** matching, không bảo đảm giá trị trọng số.

### 13.2. Ghép nhiều–một

Nếu mỗi người chỉ làm một nhiệm vụ, nhưng mỗi nhiệm vụ có **quota** nhiều người, đó là **b-matching/capacitated assignment**. Có thể chuyển sang luồng cực đại bằng các cạnh dung lượng quota hoặc dùng thuật toán riêng. Mã pairRight[v] chỉ chứa **một** trái nên không thể dùng nguyên bản cho quota>1.

### 13.3. Đồ thị không hai phía

Nếu input là đồ thị vô hướng tùy ý và chứa **chu trình lẻ**, không thể phân hoạch tất cả đỉnh thành hai phía để mọi cạnh đi ngang. Thuật toán maximum matching tổng quát cần xử lý **odd blossoms** và các chu trình luân phiên khó hơn, ví dụ **Edmonds' blossom algorithm**. Hopcroft–Karp chỉ áp dụng khi **đã có hoặc đã xác nhận** phân hoạch hai phía.

Nếu input là danh sách cạnh không cho phân hoạch L/R, có thể dùng BFS tô hai màu để phát hiện bipartite và xây nLeft/nRight tương ứng trước khi dùng mã ở đây. Không được đưa một cạnh cùng phía vào API trái–phải bằng cách tùy tiện đổi nhãn.

### 13.4. Giảm bài toán matching về max flow

Tạo mạng có hướng:

- Siêu nguồn s nối tới mỗi đỉnh trái L bằng cạnh dung lượng 1.
- Mỗi cạnh hợp lệ L–R thành cung L→R dung lượng 1.
- Mỗi đỉnh phải R nối tới siêu đích t bằng cạnh dung lượng 1.

Một luồng nguyên đơn vị đi theo đường s→L→R→t tương ứng một cặp ghép. Định lý luồng nguyên với dung lượng nguyên cho biết có thể tìm luồng tối ưu nguyên, nên:

**`maximumFlowValue=maximumBipartiteMatchingSize`**.

Đây là cách chứng minh/mô hình hóa tổng quát, nhưng đối với bipartite unweighted matching, Hopcroft–Karp khai thác cấu trúc hai phía để có cận hiệu quả đặc thù O(E√V).

### 13.5. Kuhn/DFS augmenting paths

Thuật toán Kuhn duyệt các đỉnh trái, mỗi lần dùng DFS tìm một đường tăng (có thể thử hoán đổi bạn ghép của một đỉnh phải). Nó đơn giản và thường phù hợp với đồ thị nhỏ hoặc một phía nhỏ. Cận kinh điển của cài đặt cơ bản là **O(VE)**.

Hopcroft–Karp vẫn dùng đường tăng, nhưng gom theo **độ dài ngắn nhất**, không gọi một DFS độc lập cho mỗi trái với BFS mới sau mỗi lần. Vì vậy cần mảng dist và vòng lặp pha.

### 13.6. Không yêu cầu in một cặp ghép duy nhất

Với đồ thị đầy đủ K_{3,3}, có **3! = 6** matching hoàn hảo khác nhau theo cặp đỉnh. Mã in một matching `{0–0,1–1,2–2}` vì thứ tự cạnh, nhưng các phép hoán vị khác cũng là maximum.

Nếu đề hỏi **đếm số maximum matchings** hoặc **xác định matching duy nhất**, Hopcroft–Karp nguyên bản chưa giải quyết hai câu hỏi ấy. Đặc biệt, đếm số perfect matchings trên đồ thị hai phía tổng quát khó hơn đáng kể so với chỉ tìm kích thước cực đại.

## 14. Cận thời gian thực tế và chi tiết triển khai Java

### Phân tích bộ nhớ

Mảng:

- `adj[u]` cho trái u: tổng độ dài các list bằng E (tính cả cạnh trùng).
- `pairLeft`: nLeft phần tử.
- `pairRight`: nRight phần tử.
- `dist`: nLeft phần tử.
- `queue` BFS: tối đa O(nLeft) đỉnh.
- `seenLeft/seenRight` và queue alternating cho min cover: O(V).
- Stack gọi DFS: tối đa O(V) trong trường hợp xấu.

Tổng **O(V+E)**.

### Không cần lưu đường tăng thành một danh sách

DFS quay lui cập nhật `pairLeft/pairRight` ngay khi đã chứng minh đường tăng có thể hoàn tất. Vì thế code không cần tạo List<Edge> cho mỗi path. Khi DFS tìm thành công từ một matchedLeft ở lớp sâu hơn, lời gọi phía trước chỉ cần gán cặp u–v đã chọn của nó để hoàn tất quá trình lật.

### Tránh dùng visited một cách tùy tiện

Trong nhiều cài đặt Kuhn đơn giản, có mảng `visited[]` đánh dấu các đỉnh trái đã thử **trong một DFS**, rồi reset cho lần DFS tiếp. Trong Hopcroft–Karp, `dist[]` mang ý nghĩa lớp, và cắt nhánh thất bại bằng `dist[u]=INF` đã đủ cho phiên bản chuẩn. Nếu thêm visited với vòng đời không đúng (ví dụ giữ xuyên pha) có thể bỏ sót đường tăng hợp lệ.

### Độ sâu BFS khác số cạnh đường tăng

Mã lưu `dist` cho **đỉnh trái** và `shortest` dưới dạng lớp kết thúc. Không nên in `shortest` ra rồi gọi đó là “số cạnh của đường tăng” khi chưa đổi theo công thức `2·shortest−1`.

### Cạnh trùng

Giả sử input chứa hai lần `(0,0)`. Graph adjacency của L0 có hai phần tử đều là R0. Khi L0 được ghép với R0, cả hai lần đều biểu diễn cùng **cặp đỉnh đang ghép**. Mã không tạo hai đơn vị capacity hay cho phép một đỉnh right được ghép hai lần; matching vẫn là tập cặp khác endpoint.

Cạnh trùng chỉ làm tăng số mục adjacency và có thể làm thuật toán chậm hơn. Nếu input rất nhiều cạnh trùng, có thể khử trùng **cặp (left,right)** trước khi chạy để tiết kiệm bộ nhớ và thời gian, miễn đề xem cạnh trùng như một khả năng ghép duy nhất.

### Trường hợp E=0 hoặc một phía rỗng

Nếu không có cạnh, BFS chỉ duyệt những trái tự do, nhưng không tìm ra right tự do nào qua cạnh, nên trả false. Matching size=0, cover rỗng. Nếu nLeft=0, không có đỉnh trái và BFS trả false ngay; nếu nRight=0, không có cạnh hợp lệ, cũng trả 0.

Đây là lý do nên nêu độ phức tạp đầy đủ **O(V+E)** cho khởi tạo và các lần quét, thay vì lấy `O(E√V)=0` theo nghĩa đen với E=0.

## 15. Kiểm thử độc lập bằng vét cạn matching và vertex cover

Để chắc chắn code đúng, không nên chỉ chạy lại cùng Hopcroft–Karp với một thứ tự cạnh khác rồi so kết quả. Có thể dùng **oracle khác bản chất** trên đồ thị nhỏ.

### 15.1. Vét cạn mọi cách ghép

Với nLeft,nRight≤6 hoặc 7, dùng quay lui trên từng đỉnh trái:

- Lấy u trái chưa xét.
- Nhánh thứ nhất: **không ghép u**.
- Với mỗi v phải kề u và **chưa được dùng**, thử ghép u→v rồi xét u tiếp theo.
- Trả lại v khi quay lui.
- Kích thước matching lớn nhất qua các nhánh là kết quả oracle.

Cách này không dùng BFS layering, không dùng ý tưởng “đường tăng”. Nó là tìm kiếm tổ hợp với chi phí mũ/giai thừa nên phù hợp cho bộ thử nhỏ nhưng đủ độc lập để bắt lỗi.

Nếu input có các cạnh trùng (u,v), oracle nên coi chúng là **một lựa chọn cặp endpoint**, không nhân số cách chỉ vì trùng dòng nhập; cardinality tối đa không thay đổi.

### 15.2. Vét cạn vertex cover

Với tổng V nhỏ, liệt kê tập đỉnh trái và phải được chọn, kiểm tra **mọi cạnh** có ít nhất một đầu mút đã chọn. Tìm số đỉnh nhỏ nhất.

Theo định lý König, ta phải có:

**`bruteMaximumMatchingSize = bruteMinimumCoverSize = HopcroftKarpSize`**.

Đây là cách kiểm thử chéo ba chứng cứ:

1. Matching hợp lệ có `size` cặp.
2. Cover thực sự bao phủ **mọi cạnh**, có `size` đỉnh.
3. Vét cạn xác nhận không tồn tại matching lớn hơn và cover nhỏ hơn.

### 15.3. Ca biên nên có

| Tình huống | Kết quả cần bảo đảm |
|---|---|
| Một phía rỗng | Matching 0, cover rỗng |
| Không có cạnh | Matching 0, cover rỗng |
| Một cạnh duy nhất | Matching 1 |
| Nhiều trái nối cùng một phải | Chỉ ghép được tối đa 1 cặp qua đỉnh phải ấy |
| Nhiều phải nối cùng một trái | Chỉ ghép được tối đa 1 cặp qua đỉnh trái ấy |
| Cạnh trùng `(u,v)` | Không làm tăng số cặp |
| Có đỉnh cô lập | Đỉnh ấy không thể ghép |
| Đồ thị đầy đủ `K_{a,b}` | Maximum matching có `min(a,b)` cặp |
| Matching tham lam ban đầu mắc kẹt | Đường tăng luân phiên có thể sửa |
| Đường tăng dài 5,7,... cạnh | DFS theo lớp phải tìm được khi cần |
| Có nhiều maximum matchings | Size không đổi, cặp cụ thể có thể khác |
| Không có left-perfect matching | `size<nLeft`; có Hall obstruction |
| Có left-perfect matching | `size=nLeft` |
| Matching cuối | Mọi cạnh phải được phủ bởi một min cover có size bằng matching |
| Chỉ số cạnh vượt phạm vi | Ném IllegalArgumentException |
| Graph input không hai phía | Không được dùng API như thể đã phân hoạch hợp lệ |

### 15.4. Sinh ngẫu nhiên có kiểm soát

Với mỗi lần thử:

1. Chọn `nLeft,nRight` từ 0..6.
2. Sinh ngẫu nhiên tới 20 cặp (u,v) hợp lệ; cho phép lặp.
3. Chạy Hopcroft–Karp.
4. Tính brute matching bằng quay lui xét trái theo thứ tự và tập phải đang dùng.
5. Tính brute minimum vertex cover bằng liệt kê tập đỉnh.
6. Kiểm `matchingSize==bruteMatching==bruteCover==|coverL|+|coverR|`.
7. Kiểm các cặp được in có endpoint hợp lệ, thực sự xuất hiện trong input, không lặp đỉnh trái/phải.
8. Kiểm mọi cạnh input có u trong coverL **hoặc** v trong coverR.
9. Hoán vị thứ tự input: size và min-cover size phải không đổi; matching cụ thể có thể thay.

Đặc biệt nên thử các đồ thị mà **pha đầu tạo matching không cực đại**: ví dụ Reroute ở mục 8 cần **hai pha BFS–DFS**, không phải chỉ tìm được các cạnh trực tiếp đầu tiên.

## 16. Các lỗi phổ biến khi cài Hopcroft–Karp

1. **Nhầm maximal với maximum:** không thêm được một cạnh trực tiếp chưa có nghĩa đã đạt cardinality tối ưu.
2. **Gộp chỉ số trái/phải vào một miền không có ánh xạ:** L0 và R0 là hai đỉnh khác nhau.
3. **Nhầm matching với phủ đỉnh:** một matching chọn cạnh không chung đầu, cover chọn đỉnh chạm mọi cạnh.
4. **Gán cùng một R cho hai L:** phải cập nhật pairLeft và pairRight nhất quán.
5. **Chỉ dùng DFS greedy mà không cho đổi ghép cũ:** bỏ sót đường tăng và trả size nhỏ.
6. **Dùng BFS trên cạnh thường, không đi qua matched-right → matched-left:** lớp không phản ánh đường luân phiên.
7. **Bắt đầu BFS từ mọi trái, kể cả đã ghép:** làm lớp sai, có thể cho phép những đường không bắt đầu tự do.
8. **Dừng toàn bộ BFS khi thấy right tự do đầu tiên:** không thu đủ các lựa chọn đường ngắn nhất trong pha.
9. **Cho DFS kết thúc ở R tự do có độ dài không bằng shortest:** mất cơ chế blocking shortest paths.
10. **Cho DFS đệ quy sang matchedLeft mà không kiểm `dist[next]=dist[u]+1`:** có thể đi vòng, mất chứng minh độ phức tạp.
11. **Không đặt dist[u]=INF khi DFS thất bại:** có thể lặp lại nhiều trạng thái ngõ cụt trong cùng pha.
12. **Giữ dist[u]=INF từ pha cũ không reset:** BFS tiếp theo phải tái dựng lớp từ matching mới.
13. **Quên tăng matchingSize đúng một lần khi DFS từ trái tự do thành công:** số cặp báo ra sai.
14. **Lật một cạnh trên đường tăng nhưng quên các cạnh phía sau:** phá invariant pairLeft/pairRight.
15. **Đếm phases gồm cả BFS cuối không tìm đường:** nếu cần báo số pha thành công, chỉ tăng sau bfs() true.
16. **Tưởng dist là số cạnh thực trên đường tăng:** dist đếm bước qua cặp matched L–R, có công thức riêng.
17. **Dùng visited[] giữ xuyên pha không reset:** bỏ qua các đường tăng mới có thể xuất hiện.
18. **Cho rằng matching được in là duy nhất:** nhiều matching cùng maximum là bình thường.
19. **Lấy phủ đỉnh bằng ZL∪ZR:** công thức đúng là `(L\ZL)∪ZR`.
20. **Duyệt phủ đỉnh từ trái đã ghép thay vì trái tự do:** không cho chứng chỉ König đúng.
21. **Đi L→R theo cả cạnh đã ghép khi dựng cover mà không chứng minh:** công thức alternating chính thức cần cạnh chưa ghép ở chiều L→R và cạnh ghép ở chiều R→L.
22. **Quên rằng right tự do đạt từ unmatched left nghĩa là còn augmenting path:** matching chưa maximum.
23. **Giải bài có trọng số như thể chỉ cần cardinality:** thuật toán không tối ưu tổng chi phí.
24. **Áp cho đồ thị không hai phía:** matching tổng quát cần xử lý odd cycles/blossoms.
25. **Nhầm quota nhiều–một với matching một–một:** pairRight chỉ lưu một đối tác.
26. **Tuyên bố O(E√V) theo nghĩa 0 bước khi E=0:** vẫn có khởi tạo mảng/duyệt đỉnh.
27. **Giả định DFS depth O(√V):** số pha O(√V) không hạn chế độ dài một đường tăng.
28. **Cạnh trùng làm tăng matching size hai lần:** trùng endpoint không tạo thêm một đỉnh khả dụng.
29. **Chỉ kiểm tra matching size, không kiểm tra cặp và cover:** code có thể đếm đúng nhưng cập nhật cặp ghép sai.
30. **Không thử các đường tăng dài hơn 1:** dễ bỏ sót phần cốt lõi của Hopcroft–Karp.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Trong `K_{5,3}`, maximum matching có thể có bao nhiêu cạnh?  
**Đáp:** 3, do mỗi đỉnh phải tham gia tối đa một cặp và bên phải chỉ có 3 đỉnh. Có thể chọn ba đỉnh trái khác nhau để ghép với ba đỉnh phải.

**Câu 2.** Một matching không thể thêm ngay cạnh nào nữa; nó đã maximum chưa?  
**Đáp:** Chưa chắc. Nó chỉ được bảo đảm là **maximal**. Cần kiểm đường tăng.

**Câu 3.** Trong một đường tăng dài 7 cạnh, có bao nhiêu cạnh đang ghép trước khi lật và sau lật matching tăng bao nhiêu?  
**Đáp:** Có 3 cạnh đã ghép và 4 cạnh chưa ghép; lật làm matching tăng **1**.

**Câu 4.** Tại sao BFS dùng `dist[left]` tăng một đơn vị khi đi qua một right đã ghép?  
**Đáp:** Vì đây là một chuyển tiếp luân phiên `L→R→L` (hai cạnh thực). Lớp phải tự do kết thúc đường tăng và được mã hóa bằng `shortest=dist[u]+1`.

**Câu 5.** Vì sao `cover=(L\Z_L)∪Z_R` có kích thước bằng maximum matching?  
**Đáp:** Mọi cạnh matching có đúng một đầu được chọn, các đỉnh phải trong Z_R đều đã ghép khi matching maximum, nên cover chọn đúng một đầu mỗi cạnh ghép. Bất kỳ cover nào cũng phải chứa ít nhất một đầu mỗi cạnh ghép; do matching edges rời nhau, cận dưới là |M| và cover dựng đạt đúng cận ấy.

**Câu 6.** Nếu thay đổi thứ tự nhập cạnh có thể thay đổi kết quả không?  
**Đáp:** Có thể thay đổi **những cặp cụ thể** và số pha, nhưng không thể đổi **cardinality maximum**. Kích thước minimum vertex cover cũng bằng cardinality ấy.

## 18. Checklist trước khi nộp

- Đã xác nhận input **hai phía** và ánh xạ chỉ số L/R đúng?
- Mục tiêu là **nhiều cặp nhất**, không phải tối ưu trọng số hay quota?
- Mảng pairLeft/pairRight luôn đối xứng và khởi tạo −1?
- BFS xuất phát từ **tất cả trái tự do**, dist=0; trái đã ghép dist=INF?
- Khi gặp right đã ghép, có chuyển về **đúng matchedLeft** để tạo lớp mới?
- Khi gặp right tự do, có cập nhật **shortest** thay vì dừng BFS quá sớm?
- DFS có chỉ đi theo `dist[nextLeft]=dist[u]+1`?
- DFS chỉ kết thúc ở right tự do khi `dist[u]+1=shortest`?
- DFS thất bại có cắt nhánh `dist[u]=INF`, và BFS pha mới reset lớp?
- Matching size chỉ tăng khi DFS từ trái tự do thành công, mỗi lần đúng 1?
- Khi BFS cuối trả false, đã biết không còn đường tăng theo Berge?
- Đã tính complexity theo số **pha** chứ không nhân một BFS cho từng đường tăng?
- Nếu xuất cover, đã tìm ZL,ZR bằng alternating BFS từ **trái chưa ghép**?
- Có lấy `coverL=L\ZL` và `coverR=ZR`, kiểm cover thật sự bao mọi cạnh?
- Có kiểm `|cover|=|matching|` theo König?
- Đã thử một phía rỗng, không cạnh, cạnh trùng, đỉnh cô lập, `K_{a,b}` và đường tăng dài?
- Có kiểm tra size với brute-force matching và cover trên đồ thị nhỏ?
- Nếu đồ thị lớn, độ sâu DFS đệ quy có an toàn với stack hay cần đổi sang iterative?
- Nếu cần perfect/left-perfect matching, có so size với nLeft/nRight theo định nghĩa?
- Nếu cần cost/quota/ghép tổng quát, đã lựa chọn mô hình khác phù hợp?

**Kết luận:** Hopcroft–Karp giải bài toán **maximum cardinality matching trong đồ thị hai phía** bằng cách lặp các pha: **BFS xây lớp của những đường tăng ngắn nhất**, rồi **DFS lật nhiều đường tăng trên các lớp hợp lệ**. Khi không còn đường tăng, matching là cực đại theo định lý Berge; tính chất độ dài đường tăng ngắn nhất tăng sau mỗi pha dẫn tới cận **O(E√V)** theo mô hình chuẩn. Từ kết quả maximum matching có thể xây **minimum vertex cover** bằng tìm các đỉnh đạt được qua đường luân phiên từ trái tự do và dùng công thức **`(L\Z_L)∪Z_R`**, qua đó vừa giải thêm một bài toán quan trọng vừa có chứng chỉ tối ưu theo định lý König.
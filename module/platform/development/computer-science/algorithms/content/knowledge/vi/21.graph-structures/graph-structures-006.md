# Thuật toán Tarjan cho thành phần liên thông mạnh

**Tarjan's algorithm** là thuật toán tìm tất cả **thành phần liên thông mạnh** (*strongly connected components – SCC*) của một **đồ thị có hướng** trong thời gian **O(V+E)** khi dùng danh sách kề. Tarjan chỉ cần **một lượt DFS toàn đồ thị**, kết hợp thời điểm khám phá `index`, giá trị `lowlink`, và một stack lưu các đỉnh **chưa được gán vĩnh viễn vào SCC**.

Ý tưởng then chốt: những đỉnh thuộc cùng một SCC có thể **đi tới nhau theo cả hai chiều**. Trong quá trình DFS, các cạnh quay về những đỉnh còn trên stack cho biết nhiều nhánh duyệt thật ra thuộc một vòng liên thông mạnh. Khi gặp một đỉnh u thỏa **`low[u] == index[u]`**, u là **gốc của một SCC đang mở**; pop từ đỉnh trên cùng của stack xuống tới u sẽ lấy trọn SCC ấy.

Bài học giải thích kỹ cơ chế này, phân biệt `lowlink` với `index` và `onStack` với `visited`, chứng minh vì sao pop đúng nhóm, xử lý đồ thị không liên thông, cạnh tự nối/cạnh song song, xây đồ thị co thành phần (*condensation DAG*), phân tích độ phức tạp và một chương trình **Java 17+** đầy đủ có stdout kiểm chứng.

## 1. SCC là gì? Phân biệt với liên thông thông thường

Cho đồ thị có hướng \(G=(V,E)\). Ta nói đỉnh u **tới được** v nếu có một đường đi theo đúng chiều các cạnh từ u đến v.

Hai đỉnh u,v thuộc cùng **thành phần liên thông mạnh** khi và chỉ khi:

\[
u\leadsto v\quad\text{và}\quad v\leadsto u.
\]

Một SCC là **tập đỉnh cực đại** thỏa mọi cặp đỉnh trong tập đều tới được nhau. "Cực đại" nghĩa là không thể thêm đỉnh ngoài vào tập mà vẫn giữ tính chất này.

Các SCC tạo thành một **phân hoạch duy nhất của tập đỉnh V**: mỗi đỉnh thuộc đúng một SCC, các SCC không giao nhau, và hợp của chúng là toàn bộ V.

### Ba ví dụ nhỏ

**Ví dụ 1 — Cạnh một chiều:**

~~~text
0 -> 1
~~~

Từ 0 tới được 1, nhưng từ 1 không thể tới 0. Vì thế các SCC là **`{0}`** và **`{1}`**, không phải `{0,1}`.

**Ví dụ 2 — Chu trình:**

~~~text
0 -> 1 -> 2
^         |
|_________|
~~~

Có đường theo chiều cạnh giữa mọi cặp đỉnh, nên `{0,1,2}` là **một SCC**.

**Ví dụ 3 — Hai vòng có cạnh một chiều giữa chúng:**

~~~text
  0 -> 1 -> 2         3 -> 4 -> 5
  ^         |         ^         |
  |_________|         |_________|

          2 --------> 3
~~~

Có đường từ vòng trái sang vòng phải, nhưng không có đường quay ngược. Kết quả gồm **hai SCC**: `{0,1,2}` và `{3,4,5}`.

### Đồ thị vô hướng không phải đầu vào ý nghĩa của SCC theo cách này

Với một cạnh vô hướng, đi được cả hai chiều; mỗi **thành phần liên thông vô hướng** đồng thời thỏa tính mạnh nếu biểu diễn thành hai cung đối nhau. Nhưng Tarjan SCC được thiết kế cho **đồ thị có hướng**. Nếu đề chỉ hỏi thành phần liên thông của đồ thị vô hướng, BFS/DFS thường đơn giản hơn.

Cũng không được nhầm SCC với **thành phần liên thông yếu** của đồ thị có hướng: liên thông yếu bỏ qua chiều cạnh; SCC giữ nguyên chiều cạnh khi xét cả hai hướng tới được.

## 2. Vì sao một lượt DFS với visited chưa đủ?

DFS thường chỉ đánh dấu `visited[u]` để khám phá các đỉnh từ một nguồn. Điều đó cho biết **reachability một chiều**, không đủ kết luận các đỉnh đã thăm thuộc cùng SCC.

Xét đường:

~~~text
0 -> 1 -> 2 -> 3
~~~

Một DFS từ 0 thăm cả bốn đỉnh, nhưng không có đường quay về từ 3 tới 0. Do đó có **bốn SCC riêng lẻ**.

Ngay cả với đồ thị có chu trình, không được gộp tất cả đỉnh mà DFS thấy thành một SCC. Ví dụ:

~~~text
0 <-> 1 -> 2 <-> 3
~~~

Đỉnh 0 tới được 2,3 nhưng từ 2,3 không trở lại được 0,1. Kết quả là `{0,1}` và `{2,3}`.

Tarjan bổ sung những thông tin mà visited không có:

- **`index[u]`**: thứ tự khám phá u lần đầu.
- **`low[u]`**: một mốc khám phá sớm nhất mà các nhánh đi từ u có thể liên hệ tới **trong phần SCC còn mở**, theo quy tắc cập nhật Tarjan.
- **Stack Tarjan**: lưu các đỉnh đã khám phá nhưng **chưa được chốt vào SCC**.
- **`onStack[u]`**: xác định một đỉnh đã khám phá **còn nằm trên stack Tarjan hay đã được pop**.

Các biến này giúp xác định khi nào một tập đỉnh thực sự có đường đi qua lại và có thể **đóng** thành một SCC.

## 3. Cấu trúc dữ liệu của Tarjan

Với V đỉnh `0..V-1`, ta dùng:

| Biến | Giá trị lúc khởi tạo | Vai trò |
|---|---|---|
| `index[u]` | -1 | Thứ tự DFS phát hiện u; -1 là chưa thăm |
| `low[u]` | Chưa có nghĩa cho đỉnh chưa thăm | Giá trị lowlink theo chuyển trạng thái Tarjan |
| `onStack[u]` | false | u có còn trong stack SCC chưa chốt không? |
| `stack` | Rỗng | Các đỉnh đã khám phá nhưng chưa thuộc SCC đã hoàn tất |
| `nextIndex` | 0 | Bộ đếm cấp `index` tăng dần |
| `componentOf[u]` | -1 | ID của SCC chứa u; gán khi pop SCC |
| `components` | Danh sách rỗng | Danh sách các nhóm SCC đã chốt |

Khi DFS lần đầu vào u:

~~~text
index[u] = low[u] = nextIndex
nextIndex = nextIndex + 1
stack.push(u)
onStack[u] = true
~~~

Một đỉnh được **đưa vào stack SCC đúng một lần** và được **lấy ra đúng một lần** sau khi SCC chứa nó đã xác định. Không đẩy lặp đỉnh đã có `index`.

### Hai loại stack rất dễ bị nhầm

**Call stack của DFS đệ quy:** các hàm `dfs(u)` hiện đang hoạt động, tự co giãn khi đệ quy vào và trả về.

**Stack Tarjan:** các đỉnh đã được khám phá nhưng **chưa gán SCC**. Một lời gọi DFS có thể đã trả về nhưng đỉnh vẫn ở stack Tarjan nếu nó đang chờ một SCC lớn hơn khép lại.

Do đó:

> **`onStack[u]` không đồng nghĩa u đang ở call stack DFS.**

Đây là lý do không thể dùng mảng ba màu `GRAY/BLACK` của bài phát hiện chu trình có hướng như một thay thế máy móc cho `onStack` của Tarjan. Một đỉnh có thể đã hoàn tất việc duyệt neighbor nhưng vẫn cần ở lại stack SCC để ghép với đỉnh/tổ tiên thích hợp.

## 4. Công thức cốt lõi của lowlink

Sau khi khám phá u, xét từng cạnh **có hướng** \(u\to v\).

### Trường hợp A — v chưa được khám phá

Nếu `index[v] == -1`, DFS vào v:

~~~text
dfs(v)
low[u] = min(low[u], low[v])
~~~

Lý do: nếu từ nhánh con v có thể quay tới một mốc mở có index nhỏ hơn, thì u cũng đi theo cạnh u→v để tới được mốc ấy. Ta **lan truyền lowlink từ con lên cha DFS**.

### Trường hợp B — v đã khám phá và vẫn ở stack Tarjan

Nếu `index[v] != -1` và `onStack[v] == true`:

~~~text
low[u] = min(low[u], index[v])
~~~

Cạnh u→v dẫn tới một đỉnh **chưa chốt SCC**, nên nó có thể kết nối u với một nhóm đang mở được khám phá trước đó.

**Chú ý dùng `index[v]`, không phải `low[v]` trong nhánh này.** Đây là quy tắc chuyển chuẩn của Tarjan khi gặp một đỉnh đã khám phá còn trên stack. Nó ghi nhận cạnh cụ thể u→v, còn `low[v]` có thể đã chứa thông tin tổng hợp từ những nhánh khác; thay bằng low[v] không còn là phép cập nhật chuẩn đang được chứng minh.

### Trường hợp C — v đã được pop khỏi stack

Nếu `index[v] != -1` nhưng `onStack[v] == false`:

~~~text
Không thay đổi low[u]
~~~

SCC chứa v **đã chốt**. Một cạnh đi từ SCC đang mở sang SCC đã chốt **không phải bằng chứng có đường quay lại** để gộp hai SCC. Dùng `index[v]` ở đây có thể kéo `low[u]` xuống sai, làm gộp nhầm các thành phần vốn chỉ có đường một chiều.

### Công thức đầy đủ

\[
low[u]=\min\left(
index[u],
\ \{low[v]: u\to v,\ v\text{ chưa thăm khi xét cạnh}\},
\ \{index[v]: u\to v,\ v\text{ đã thăm và còn trên stack}\}
\right)
\]

với chú ý đây là công thức **theo tiến trình DFS**: sau nhánh A ta dùng `low[v]` đã được tính xong; với nhánh B ta chỉ dùng `index[v]` của đỉnh còn trên stack tại thời điểm xét cạnh. Không được hiểu rằng có thể lấy min của tất cả đỉnh từng thăm **sau khi DFS kết thúc**; các SCC đã pop phải bị loại khỏi ảnh hưởng lowlink.

## 5. Khi nào tìm được một SCC?

Sau khi xét hết các cạnh ra của u, kiểm tra:

\[
\boxed{low[u]=index[u].}
\]

Nếu bằng nhau, u là **gốc của một SCC đang mở** theo cấu trúc DFS. Lấy các đỉnh khỏi **đỉnh trên cùng của stack Tarjan** cho tới và bao gồm u:

~~~text
if low[u] == index[u]:
    component = []
    do:
        w = stack.pop()
        onStack[w] = false
        component.add(w)
        componentOf[w] = số_thứ_tự_component
    while w != u
    ghi nhận component
~~~

Vì stack lưu theo thứ tự khám phá và một SCC đã khép sẽ bị pop **nguyên khối**, đoạn đỉnh từ đỉnh stack xuống tới u chính là các đỉnh của SCC ấy. Đỉnh nằm dưới u thuộc những thành phần đang mở trước đó; không được pop vượt qua u.

**Không pop một đỉnh chỉ vì nó đã duyệt xong mọi neighbor.** Trong Tarjan, một đỉnh có thể hoàn tất lời gọi DFS nhưng phải chờ một tổ tiên có `low==index` rồi mới được lấy ra cùng SCC. Đây là sự khác biệt chính giữa stack Tarjan và call stack đệ quy.

### Vì sao có dấu bằng?

Ban đầu `low[u]=index[u]`, và mọi phép cập nhật đều lấy `min`, nên `low[u]\le index[u]`.

- Nếu `low[u]<index[u]`, từ miền DFS của u có liên hệ tới một đỉnh **được khám phá trước u** trong phần đang mở; u chưa thể làm gốc tách SCC ở thời điểm này.
- Nếu `low[u]==index[u]`, không có thông tin lowlink buộc nhóm chưa chốt gốc u phải nối ngược tới một đỉnh được khám phá sớm hơn u. u là mốc để chốt nhóm có thể tới được qua lại.

Đây là một tiêu chuẩn của **thuật toán Tarjan chuẩn**, không phải quy tắc chung cho mọi thuật toán DFS.

## 6. Mã giả Tarjan chuẩn

~~~text
tarjan(G):
    for each vertex u:
        index[u] = -1
        onStack[u] = false
        componentOf[u] = -1

    nextIndex = 0
    stack = empty
    components = empty

    for each vertex u in V:
        if index[u] == -1:
            strongConnect(u)

    return components, componentOf


strongConnect(u):
    index[u] = nextIndex
    low[u] = nextIndex
    nextIndex++

    stack.push(u)
    onStack[u] = true

    for v in adj[u]:
        if index[v] == -1:
            strongConnect(v)
            low[u] = min(low[u], low[v])
        else if onStack[v]:
            low[u] = min(low[u], index[v])
        else:
            // v belongs to an already completed SCC
            // do not update low[u]

    if low[u] == index[u]:
        group = empty
        repeat:
            w = stack.pop()
            onStack[w] = false
            componentOf[w] = components.size
            group.add(w)
        until w == u

        components.add(group)
~~~

**Vòng lặp ngoài bắt buộc** nếu cần tìm SCC của **toàn đồ thị**, kể cả đỉnh không đi tới được từ đỉnh 0. Nếu chỉ gọi `strongConnect(0)`, những đỉnh nằm ngoài vùng tới được từ 0 sẽ bị bỏ sót.

**Một SCC một đỉnh là hợp lệ**: đỉnh cô lập hoặc đỉnh không thuộc chu trình vẫn là SCC kích thước 1 vì một đỉnh luôn tới được chính nó bằng đường đi độ dài 0. Cạnh tự nối u→u cũng **không bắt buộc tạo SCC nhiều đỉnh**.

## 7. Ví dụ xuyên suốt: 11 đỉnh, nhiều SCC và cạnh một chiều

Xét đồ thị có hướng gồm 11 đỉnh `0..10`. Các cạnh:

~~~text
0 -> 1
1 -> 2, 3, 6
2 -> 0
3 -> 4
4 -> 5
5 -> 3, 6
6 -> 7
7 -> 6, 8
8 -> 9
9 -> (không có cạnh ra)
10 -> (đỉnh cô lập)
~~~

Minh họa các nhóm kết nối:

~~~text
      +-------------+
      |   0 -> 1    |
      |   ^    |    |
      |   +-- 2     |
      +-------------+
             | từ 1
             v
      +-------------+       +-----------+
      |  3 -> 4     | ----> | 6 <-> 7   | ---> 8 ---> 9
      |  ^    |     |       +-----------+
      |  +-- 5      |
      +-------------+

Ngoài ra có cạnh trực tiếp 1 -> 6.
Đỉnh 10 cô lập.
~~~

Bảng đỉnh cho ví dụ được xây bằng danh sách kề **theo đúng thứ tự đã nêu**, để có thể tái hiện trình tự DFS trong chương trình Java.

Các SCC theo quan hệ tới được hai chiều là:

\[
\{0,1,2\},\quad
\{3,4,5\},\quad
\{6,7\},\quad
\{8\},\quad
\{9\},\quad
\{10\}.
\]

**Cạnh 1→3, 1→6, 5→6, 7→8, 8→9 chỉ đi một chiều giữa các nhóm.** Không có đường quay ngược để gộp những nhóm khác nhau thành một SCC lớn.

### Dòng thời gian DFS

Duyệt đỉnh theo thứ tự tăng và neighbor theo thứ tự trong danh sách kề:

1. DFS khám phá 0 (index 0), 1 (index 1), 2 (index 2).
2. Cạnh 2→0 dẫn tới đỉnh 0 **vẫn trên stack**, nên `low[2]=0`.
3. Quay về 1; sau khi lan truyền, `low[1]=0`.
4. Từ 1 đi tới 3 (index 3), 4 (index 4), 5 (index 5). Cạnh 5→3 giữ `low[5]=3`.
5. Từ 5 đi tới 6 (index 6), 7 (index 7). Cạnh 7→6 đưa `low[7]` về 6.
6. Từ 7 đi tới 8 (index 8), 9 (index 9). Đỉnh 9 không có cạnh ra nên `low[9]==index[9]`; pop SCC `{9}`. Sau đó 8 cũng thỏa tiêu chuẩn và được pop thành `{8}`.
7. Quay về 6: `low[6]=6`, pop từ 7 tới 6 ⇒ SCC **`{6,7}`**.
8. Quay về 5 rồi 4 và 3: `low[3]=3`; pop từ 5 xuống 3 ⇒ SCC **`{3,4,5}`**.
9. Lúc này 1 xét thêm cạnh 1→6. Đỉnh 6 đã thuộc SCC **đã pop**, `onStack[6]=false`, nên **không hạ low[1]**. Sau đó kết thúc 1, quay về 0.
10. `low[0]=index[0]=0`; pop từ 2 xuống 0 ⇒ SCC **`{0,1,2}`**.
11. Vòng lặp ngoài phát hiện 10 chưa thăm, DFS(10), pop SCC riêng **`{10}`**.

**Chi tiết quan trọng nhất:** cạnh **1→6** chỉ cho phép đi tới nhóm `{6,7}`; nó không chứng minh 6 có thể quay về 1. Vì 6 đã được chốt, nó phải được **bỏ qua** khi cập nhật lowlink của 1.

### Giá trị index và lowlink cuối

| u | index[u] | low[u] | SCC |
|---:|---:|---:|---|
| 0 | 0 | 0 | {0,1,2} |
| 1 | 1 | 0 | {0,1,2} |
| 2 | 2 | 0 | {0,1,2} |
| 3 | 3 | 3 | {3,4,5} |
| 4 | 4 | 3 | {3,4,5} |
| 5 | 5 | 3 | {3,4,5} |
| 6 | 6 | 6 | {6,7} |
| 7 | 7 | 6 | {6,7} |
| 8 | 8 | 8 | {8} |
| 9 | 9 | 9 | {9} |
| 10 | 10 | 10 | {10} |

Lưu ý: giá trị `index` và `low` **phụ thuộc thứ tự DFS**, và lowlink được xác định bởi thuật toán tại thời điểm xử lý. **Các tập SCC thì không phụ thuộc vào thứ tự duyệt**. Chạy Tarjan với neighbor theo thứ tự khác có thể tạo ID và thứ tự xuất SCC khác mà vẫn hoàn toàn đúng.

### Vì sao danh sách SCC được pop theo thứ tự “ngược”?

Trong ví dụ, các SCC được xuất hiện khi hoàn tất DFS từ nhánh sâu nhất trước:

~~~text
[9]
[8]
[6,7]
[3,4,5]
[0,1,2]
[10]
~~~

Nếu gán ID thành phần bằng thứ tự pop, ta được:

~~~text
Vertex:         0  1  2  3  4  5  6  7  8  9  10
Component ID:   4  4  4  3  3  3  2  2  1  0   5
~~~

ID chỉ là nhãn **do thuật toán gán**, không phải thứ tự “quan trọng” hay một số đo của SCC. Muốn xuất danh sách theo ID nhỏ nhất của đỉnh, có thể chuẩn hóa **sau khi tính**; không được nhầm việc đổi thứ tự in với thay đổi tập kết quả.

## 8. Bất biến và chứng minh tính đúng

Một chứng minh đúng của Tarjan thường dựa trên ba nhóm bất biến.

### 8.1. Index phản ánh đúng thứ tự khám phá

Mỗi đỉnh được gán `index[u]` **đúng một lần** khi bắt đầu DFS(u). Các index được tăng đơn điệu, nên chỉ số nhỏ hơn biểu thị được khám phá sớm hơn.

Trong lúc xử lý một đỉnh u, nếu gặp neighbor v chưa thăm, v trở thành **con DFS của u**. Nếu v đã thăm, không được gọi DFS(v) lần nữa.

### 8.2. Stack chứa chính các đỉnh chưa gán SCC

Một đỉnh được push khi khám phá. Nó vẫn ở stack cho tới khi một gốc SCC phù hợp pop nó; sau khi pop, `onStack[u]` chuyển false và `componentOf[u]` nhận ID cố định.

Vì một đỉnh chỉ push một lần, chỉ pop một lần, nên không thể thuộc hai SCC khác nhau. Những cạnh tới SCC đã pop bị bỏ qua khi hạ lowlink, vì SCC đã chốt không được trộn lại vào nhóm đang mở.

Bất biến này giải thích tại sao `onStack` quan trọng hơn một boolean `visited`: **visited chỉ nói đã thăm; onStack nói còn được phép gộp trong SCC đang mở**.

### 8.3. Lowlink giữ quan hệ với phần DFS đang mở

Bằng khởi tạo `low[u]=index[u]`, mỗi đỉnh tự tham chiếu mốc khám phá của mình.

- Khi gặp **con DFS mới** v, thông tin lowlink của v có thể lan về u vì có cạnh u→v.
- Khi gặp cạnh tới v **đã thăm và còn onStack**, index của v phản ánh một mốc của phần chưa chốt có cạnh tới từ u.
- Khi gặp v **đã pop**, không thể dùng nó làm bằng chứng ghép SCC đang xét, vì SCC của v đã hoàn tất và không cần quay lại.

Lowlink không đơn thuần là **index nhỏ nhất có thể đi tới được bằng mọi đường của đồ thị gốc**. Nó là đại lượng gắn với **ngữ cảnh DFS và stack chưa chốt**. Một đường đi một chiều tới một SCC đã pop không được dùng để làm lowlink nhỏ đi.

### 8.4. Vì sao pop đúng một SCC?

Xét u với `low[u]==index[u]` sau khi đã xử lý tất cả các cạnh ra:

1. Các đỉnh đang ở trên u trong stack được phát hiện trong miền tìm kiếm sau khi u mở SCC của mình. Những đường đi và thông tin lowlink giữ chúng trong cùng vùng **chưa chốt** với u.
2. Nếu một nhóm ấy có đường quay tới một thành phần mở với index nhỏ hơn u thì lowlink sẽ bị lan tới mốc nhỏ hơn, trái `low[u]==index[u]`.
3. Vì u là mốc sớm nhất cần giữ trong nhóm này, việc pop đúng đoạn stack từ đỉnh trên cùng xuống u thu được một **SCC cực đại**.
4. Các đỉnh dưới u không được pop vì chúng nằm trong phần khám phá trước u và chưa được chứng minh là cùng nhóm với u.
5. Sau khi pop, SCC này không bao giờ được ghép với SCC khác, và việc bỏ cạnh trỏ tới nó khi tính lowlink là an toàn.

Lập luận đầy đủ có thể được formal hóa bằng các tính chất của cây DFS và quan hệ tới được hai chiều. Điều quan trọng để cài đặt đúng là **không phá ba bất biến** và dùng đúng công thức cập nhật lowlink. Nếu thay `onStack` bằng `visited`, hoặc pop khi `dfs(u)` trở về thay vì khi `low==index`, chứng minh không còn áp dụng.

### 8.5. Đầy đủ và không trùng

Vòng lặp ngoài duyệt mọi u chưa có index, nên mỗi đỉnh của toàn graph được khám phá. Mỗi đỉnh được giữ trên stack cho đến lúc SCC chứa nó được chốt; cuối cùng không có đỉnh nào còn thiếu. Vì mỗi đỉnh chỉ pop một lần, SCC tạo thành **phân hoạch không trùng** của V.

**Đúng về quan hệ:** nếu hai đỉnh được pop trong cùng một nhóm, chúng thuộc một SCC theo tiêu chuẩn Tarjan; nếu hai đỉnh thuộc SCC thật của graph, quy tắc lowlink và stack sẽ không tách chúng thành hai nhóm khác nhau.

## 9. Đồ thị co thành phần (condensation DAG)

Sau khi có `componentOf[u]`, ta có thể **co mỗi SCC thành một đỉnh**. Với mỗi cạnh gốc \(u\to v\):

- Nếu `componentOf[u]==componentOf[v]`: cạnh nằm **trong cùng SCC**, không cần đưa vào đồ thị co.
- Nếu khác: thêm cạnh \(\operatorname{comp}(u)\to\operatorname{comp}(v)\) vào đồ thị co.

Nên **khử trùng** các cạnh giữa cùng cặp SCC nếu nhiều cạnh gốc cho cùng kết nối, để danh sách kề DAG rõ ràng hơn.

### Vì sao đồ thị co chắc chắn là DAG?

Giả sử đồ thị co có chu trình:

\[
C_0\to C_1\to \cdots\to C_k\to C_0.
\]

Trong mỗi SCC, mọi đỉnh tới được nhau. Chu trình giữa các SCC cho phép đi từ bất kỳ đỉnh của \(C_i\) tới bất kỳ đỉnh của \(C_j\) và ngược lại theo các cạnh nối cùng đường nội bộ. Vậy tất cả các SCC trên chu trình đáng lẽ phải là **một SCC lớn**, mâu thuẫn với việc chúng là những thành phần mạnh cực đại khác nhau.

Do đó đồ thị co **không có chu trình có hướng**.

### Đồ thị co của ví dụ

Nếu ID SCC được gán theo thứ tự pop ở phần 7, quan hệ cạnh là:

~~~text
SCC 4 ({0,1,2}) -> SCC 3 ({3,4,5})
SCC 4 ({0,1,2}) -> SCC 2 ({6,7})
SCC 3 ({3,4,5}) -> SCC 2 ({6,7})
SCC 2 ({6,7})   -> SCC 1 ({8})
SCC 1 ({8})     -> SCC 0 ({9})
SCC 5 ({10})    -> (không có cạnh)
~~~

Danh sách kề DAG theo ID (đã sắp/khử trùng) là:

~~~text
[[], [0], [1], [2], [2, 3], []]
~~~

Đồ thị co hữu ích cho **DP trên DAG**, đếm/tổng hợp số SCC nguồn hoặc đích, nghiên cứu thứ tự phụ thuộc, và bài toán muốn phân tích tính chu trình ở mức nhóm thay vì từng đỉnh.

**Chú ý:** số SCC **nguồn** (bậc vào bằng 0) hoặc SCC **đích** (bậc ra bằng 0) là tính chất của DAG co. Nó không đồng nghĩa số gốc trong cây DFS ban đầu. ID SCC cũng không nhất thiết là chỉ số tô-pô tăng dần nếu ta tùy ý đổi cách đánh số; nên tính bậc vào hoặc topo thực sự khi cần.

## 10. Java 17+: Tarjan chạy được và tạo DAG co

Chương trình sau cài **Tarjan SCC chuẩn** bằng DFS đệ quy. Nó sử dụng `ArrayDeque<Integer>` cho stack SCC và `TreeSet<Integer>` để loại các cạnh trùng giữa các SCC trong đồ thị co.

**Quy ước:**

- Đỉnh là `0..vertices-1`; đồ thị có **hướng**.
- `index=-1` biểu thị chưa khám phá.
- Các nhóm SCC **được chốt theo thứ tự pop**, nhưng mỗi nhóm được **sắp tăng dần khi in** để dễ kiểm chứng.
- `componentOf[v]` là vị trí nhóm trong danh sách trả về.
- `onStack` khác `visited`: chỉ các đỉnh chưa chốt SCC còn onStack.
- Mã từ chối đầu mút cạnh không hợp lệ; đồ thị rỗng V=0 trả danh sách SCC rỗng.
- Chi phí dùng stack đệ quy của Java có thể quá sâu trên graph cực lớn; phần 14 thảo luận bản lặp.

Lưu tệp **TarjanSccDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.TreeSet;

public class TarjanSccDemo {
    record SccResult(
        List<List<Integer>> components,
        int[] componentOf,
        int[] index,
        int[] lowlink
    ) {}

    static List<List<Integer>> buildGraph(int vertices, int[][] edges) {
        Objects.requireNonNull(edges, "edges");
        if (vertices < 0) {
            throw new IllegalArgumentException("negative vertex count");
        }
        List<List<Integer>> graph = new ArrayList<>();
        for (int u = 0; u < vertices; u++) {
            graph.add(new ArrayList<>());
        }
        for (int[] edge : edges) {
            if (edge == null || edge.length != 2
                    || edge[0] < 0 || edge[0] >= vertices
                    || edge[1] < 0 || edge[1] >= vertices) {
                throw new IllegalArgumentException("invalid edge");
            }
            graph.get(edge[0]).add(edge[1]);
        }
        return graph;
    }

    static SccResult tarjan(List<List<Integer>> graph) {
        Objects.requireNonNull(graph, "graph");
        int n = graph.size();
        for (List<Integer> next : graph) {
            if (next == null) {
                throw new IllegalArgumentException("null adjacency list");
            }
            for (Integer v : next) {
                if (v == null || v < 0 || v >= n) {
                    throw new IllegalArgumentException("invalid neighbor");
                }
            }
        }
        return new TarjanSearch(graph).solve();
    }

    static final class TarjanSearch {
        private final List<List<Integer>> graph;
        private final int[] index;
        private final int[] lowlink;
        private final int[] componentOf;
        private final boolean[] onStack;
        private final ArrayDeque<Integer> stack = new ArrayDeque<>();
        private final List<List<Integer>> components = new ArrayList<>();
        private int nextIndex = 0;

        TarjanSearch(List<List<Integer>> graph) {
            this.graph = graph;
            int n = graph.size();
            index = new int[n];
            lowlink = new int[n];
            componentOf = new int[n];
            onStack = new boolean[n];
            Arrays.fill(index, -1);
            Arrays.fill(componentOf, -1);
        }

        SccResult solve() {
            for (int u = 0; u < graph.size(); u++) {
                if (index[u] == -1) {
                    dfs(u);
                }
            }
            return new SccResult(
                List.copyOf(components),
                componentOf.clone(),
                index.clone(),
                lowlink.clone()
            );
        }

        private void dfs(int u) {
            index[u] = lowlink[u] = nextIndex++;
            stack.push(u);
            onStack[u] = true;

            for (int v : graph.get(u)) {
                if (index[v] == -1) {
                    // Tree edge to an undiscovered descendant.
                    dfs(v);
                    lowlink[u] = Math.min(lowlink[u], lowlink[v]);
                } else if (onStack[v]) {
                    // Edge to an unfinished SCC. Use index[v],
                    // NOT lowlink[v], for an already visited v.
                    lowlink[u] = Math.min(lowlink[u], index[v]);
                }
                // Already assigned SCC: no lowlink update.
            }

            if (lowlink[u] == index[u]) {
                int componentId = components.size();
                List<Integer> group = new ArrayList<>();

                while (true) {
                    int v = stack.pop();
                    onStack[v] = false;
                    componentOf[v] = componentId;
                    group.add(v);
                    if (v == u) {
                        break;
                    }
                }
                Collections.sort(group); // Display normalization only.
                components.add(List.copyOf(group));
            }
        }
    }

    static List<List<Integer>> condensation(
        List<List<Integer>> graph, SccResult result
    ) {
        int count = result.components().size();
        List<TreeSet<Integer>> outgoing = new ArrayList<>();
        for (int i = 0; i < count; i++) {
            outgoing.add(new TreeSet<>());
        }

        for (int u = 0; u < graph.size(); u++) {
            int cu = result.componentOf()[u];
            for (int v : graph.get(u)) {
                int cv = result.componentOf()[v];
                if (cu != cv) {
                    outgoing.get(cu).add(cv);
                }
            }
        }

        List<List<Integer>> dag = new ArrayList<>();
        for (TreeSet<Integer> set : outgoing) {
            dag.add(List.copyOf(set));
        }
        return List.copyOf(dag);
    }

    public static void main(String[] args) {
        int[][] edges = {
            {0, 1}, {1, 2}, {2, 0},
            {1, 3}, {3, 4}, {4, 5}, {5, 3},
            {5, 6}, {6, 7}, {7, 6},
            {7, 8}, {8, 9}, {1, 6}
        };
        List<List<Integer>> graph = buildGraph(11, edges);
        SccResult result = tarjan(graph);

        System.out.println("Tarjan SCCs: "
            + result.components());
        System.out.println("Component ID by vertex: "
            + Arrays.toString(result.componentOf()));
        System.out.println("Index: "
            + Arrays.toString(result.index()));
        System.out.println("Lowlink: "
            + Arrays.toString(result.lowlink()));
        System.out.println("Same SCC 0,2: "
            + (result.componentOf()[0] == result.componentOf()[2]));
        System.out.println("Same SCC 0,4: "
            + (result.componentOf()[0] == result.componentOf()[4]));
        System.out.println("Condensation DAG: "
            + condensation(graph, result));

        List<List<Integer>> special = buildGraph(
            3, new int[][] {
                {0, 0}, {0, 1}, {0, 1}, {1, 2}, {2, 1}
            }
        );
        System.out.println("Self-loop/parallel SCCs: "
            + tarjan(special).components());

        List<List<Integer>> chain = buildGraph(
            4, new int[][] {{0, 1}, {1, 2}, {2, 3}}
        );
        System.out.println("DAG SCCs: "
            + tarjan(chain).components());
        System.out.println("Empty graph SCCs: "
            + tarjan(buildGraph(0, new int[][] {})).components());

        try {
            buildGraph(3, new int[][] {{0, 3}});
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid edge rejected: "
                + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac TarjanSccDemo.java
java TarjanSccDemo
~~~

**Stdout chính xác với dữ liệu đã cho:**

~~~text
Tarjan SCCs: [[9], [8], [6, 7], [3, 4, 5], [0, 1, 2], [10]]
Component ID by vertex: [4, 4, 4, 3, 3, 3, 2, 2, 1, 0, 5]
Index: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
Lowlink: [0, 0, 0, 3, 3, 3, 6, 6, 8, 9, 10]
Same SCC 0,2: true
Same SCC 0,4: false
Condensation DAG: [[], [0], [1], [2], [2, 3], []]
Self-loop/parallel SCCs: [[1, 2], [0]]
DAG SCCs: [[3], [2], [1], [0]]
Empty graph SCCs: []
Invalid edge rejected: invalid edge
~~~

### 10.1. Gắn mã với công thức Tarjan

- `index[u] = lowlink[u] = nextIndex++`: gán thứ tự khám phá và khởi tạo lowlink cùng giá trị.
- `stack.push(u)` và `onStack[u]=true`: giữ u trong tập SCC chưa chốt.
- Nhánh `index[v]==-1`: duyệt DFS con rồi lấy min với **lowlink[v]**.
- Nhánh `onStack[v]`: v đã thăm, vẫn chưa chốt SCC; lấy min với **index[v]**.
- Nhánh còn lại: v thuộc SCC đã chốt, **không cập nhật**.
- `lowlink[u]==index[u]`: pop chính xác cho tới u, gán cùng `componentId` cho mọi đỉnh vừa pop.
- `Collections.sort(group)` chỉ thay đổi **cách hiển thị** trong mỗi SCC, không thay đổi cách Tarjan tìm thành phần.
- Vòng `for (u=0;u<n;u++)` bảo đảm cả **đỉnh 10 cô lập** vẫn được xử lý.

### 10.2. Vì sao condensation dùng TreeSet?

Có thể có nhiều cạnh gốc nối hai SCC giống nhau. Một DAG co thường chỉ cần biết có **ít nhất một cạnh** giữa cặp SCC đó. `TreeSet<Integer>` vừa loại trùng vừa sắp ID đích tăng dần, nên stdout dễ đối chiếu.

Việc khử trùng cạnh không thay đổi reachability của DAG. Nếu ứng dụng đòi **đếm số cạnh song song** giữa hai SCC, không được dùng `TreeSet` để xóa chúng; hãy lưu số đếm riêng theo đặc tả.

### 10.3. Mảng trong Java record vẫn mutable

`SccResult` là `record`, nhưng `int[] componentOf`, `index`, `lowlink` vẫn là mảng có thể sửa qua accessor. Mã tạo bản sao khi trả từ bộ giải để cô lập trạng thái nội bộ, nhưng **không tạo bản sao mỗi lần gọi accessor**.

Demo chỉ đọc dữ liệu sau khi giải. Với API sản phẩm nhiều người gọi, nên thiết kế phương thức truy vấn chỉ đọc, sao chép phòng vệ ở accessor, hoặc dùng cấu trúc bất biến để không bị người dùng sửa mảng làm mất tính nhất quán của kết quả.

## 11. Ví dụ phản chứng: tại sao phải kiểm tra onStack?

Xét đồ thị:

~~~text
0 -> 1 -> 2
     |
     +----> 3
~~~

Không có cạnh quay ngược, nên mỗi đỉnh là một SCC singleton. Duyệt từ 0:

1. DFS(0) đi tới 1 rồi 2; đỉnh 2 được pop thành SCC `{2}`.
2. Quay về 1, tiếp tục đi tới 3; đỉnh 3 được pop thành `{3}`.
3. 1 được pop thành `{1}`, rồi 0 thành `{0}`.

Nếu sau đó thuật toán gặp một cạnh tới một đỉnh **đã pop**, cạnh đó không làm hai SCC liên thông mạnh.

Ví dụ cụ thể hơn, với thêm cạnh `0→2`:

~~~text
0 -> 1 -> 2
|         ^
+---------+
~~~

Khi quay lại 0 sau nhánh qua 1, 2 đã pop. Cạnh 0→2 chỉ xác nhận 0 **tới được** 2, không có đường 2→0. Nếu cập nhật `low[0]=min(low[0],index[2])`, trong trường hợp này index[2] lớn hơn index[0] nên chưa làm sai; nhưng với những cạnh chéo tới SCC hoàn tất được khám phá **sớm hơn u**, lấy index đó có thể hạ low[u] quá mức và gộp nhầm.

Một ví dụ bộc lộ lỗi rõ hơn:

~~~text
      0
     / \
    v   v
    1   2
        |
        v
        1
~~~

Danh sách kề `adj[0]=[1,2]`, `adj[1]=[]`, `adj[2]=[1]`:

- DFS(0) đi vào 1 trước. SCC `{1}` được pop ngay.
- Sau đó từ 0 đi vào 2; 2 có cạnh 2→1, nhưng `onStack[1]=false`.
- Nếu **sai** khi dùng index[1] để hạ low[2], ta được `low[2]=index[1]=1 < index[2]=2`. Lúc đó 2 sẽ không được pop như một SCC độc lập tại lời gọi DFS(2), và có thể bị gộp nhầm khi 0 được pop.
- Cách **đúng** bỏ qua cạnh tới 1 đã pop, giữ `low[2]=index[2]=2`; pop `{2}` riêng. SCC thật vẫn là `{0}`, `{1}`, `{2}`.

Đây là lý do **chỉ biết “đỉnh đã thăm” là không đủ**. Tư cách còn ở trong **stack Tarjan** mới quyết định một cạnh tới đỉnh đã khám phá có được dùng để cập nhật lowlink hay không.

## 12. Trường hợp biên: self-loop, cạnh song song, không liên thông

### 12.1. Một đỉnh không có cạnh

Một đỉnh cô lập u có `low[u]==index[u]` ngay sau khi khởi tạo. Không có neighbor để đổi lowlink; thuật toán pop `{u}` thành SCC singleton.

### 12.2. Self-loop u→u

Khi DFS(u) gặp cạnh tới chính u, `onStack[u]=true`, nên:

\[
low[u]=\min(low[u],index[u])=index[u].
\]

Self-loop là chu trình độ dài 1, nhưng **không cần có thêm đỉnh nào** trong SCC. `{u}` vẫn là một SCC hợp lệ.

### 12.3. Cạnh song song

Hai cạnh giống nhau u→v có thể được duyệt hai lần. Sau lần đầu, v đã được khám phá; lần tiếp theo gặp v ở trạng thái onStack hoặc đã pop. Quy tắc Tarjan vẫn đúng; mỗi đỉnh vẫn chỉ được push/pop một lần. Độ phức tạp tính theo E có bao gồm **số cạnh song song**.

### 12.4. Đồ thị không có cạnh

V đỉnh và E=0 có đúng **V SCC singleton**. Không phải một SCC rỗng chứa tất cả các đỉnh.

### 12.5. Đồ thị rỗng

V=0 không có đỉnh, nên kết quả danh sách SCC **rỗng `[]`**. Nếu API của ứng dụng yêu cầu đồ thị phải có ít nhất một đỉnh, có thể từ chối đầu vào; demo cho phép V=0 và trả kết quả rỗng.

### 12.6. Đồ thị có nhiều thành phần không kết nối

Vòng ngoài `for u in 0..V-1` sẽ gọi DFS mới tại một đỉnh có index=-1. Nhờ đó Tarjan xử lý **mọi SCC**, không chỉ những SCC tới được từ đỉnh 0. Các SCC được pop theo thứ tự tùy DFS, nhưng quan hệ thành phần là duy nhất.

### 12.7. Tất cả đỉnh thuộc cùng một SCC

Trong chu trình `0→1→...→(V-1)→0`, mỗi đỉnh sau có lowlink lan ngược về index[0]. Đến khi DFS(0) hoàn tất, `low[0]==index[0]` và pop **toàn bộ V đỉnh** thành một SCC.

### 12.8. DAG

Trong DAG, không hai đỉnh phân biệt nào đi được tới nhau theo cả hai chiều, nếu không sẽ có chu trình. Do đó **mọi SCC đều là singleton**. Mã thử chuỗi `0→1→2→3` cho kết quả `[[3],[2],[1],[0]]` theo thứ tự pop.

## 13. Độ phức tạp: vì sao O(V+E)?

Cho đồ thị dùng **danh sách kề**.

- Mỗi đỉnh được gọi DFS đúng **một lần**, vì `index[u]` khác -1 ngay lúc khám phá.
- Mỗi cạnh \(u\to v\) được xem xét **một lần** khi duyệt `adj[u]`.
- Mỗi đỉnh được **push đúng một lần**, **pop đúng một lần** khỏi stack Tarjan.
- Mỗi phép cập nhật `Math.min`, đánh dấu onStack, gán ID và kiểm tra điều kiện pop đều O(1).

Vì thế:

\[
\boxed{T_{\text{Tarjan}}=O(V+E).}
\]

Các mảng `index`, `lowlink`, `onStack`, `componentOf` và stack Tarjan đều có kích thước tối đa O(V). Stack đệ quy có thể sâu tối đa O(V):

\[
\boxed{S_{\text{phụ}}=O(V)}
\]

ngoài cấu trúc lưu graph và danh sách kết quả.

**Chi phí hiển thị kết quả trong demo:** mã sắp tăng đỉnh **trong mỗi SCC**, nên có thêm thời gian \(\sum_i O(|C_i|\log|C_i|)\le O(V\log V)\). Đây là **chi phí chuẩn hóa đầu ra**, không phải bước bắt buộc của Tarjan. Nếu bỏ `Collections.sort(group)`, thuật toán tính SCC thuần giữ **O(V+E)**.

**Chi phí xây DAG co:** xét mỗi cạnh một lần, nhưng demo dùng `TreeSet` để khử trùng/sắp ID, mỗi lần thêm cạnh có thể cần O(log C) với C là số SCC. Vì vậy bản dựng DAG co minh họa có cận \(O(V+E\log V)\), không tự động bằng O(V+E) do dùng cấu trúc cây cân bằng. Có thể dùng `HashSet` với kỳ vọng O(1) mỗi lần thêm (và giữ kết quả chưa sắp) để đạt kỳ vọng O(V+E); hoặc dùng kỹ thuật đánh dấu/ký nhận theo ID SCC để loại trùng trong thời gian tuyến tính theo dữ liệu thích hợp.

### Tràn call stack Java

Tarjan chuẩn trong demo dùng **đệ quy**. Với đường có rất nhiều đỉnh (chẳng hạn hàng trăm nghìn đỉnh nối tiếp), Java có thể ném `StackOverflowError`, dù bộ nhớ phụ theo lý thuyết là O(V).

Bản Tarjan **lặp** có thể dùng stack frame riêng lưu `vertex`, `nextNeighborIndex`, cùng trạng thái “vừa trở về từ con” để cập nhật lowlink của cha ở đúng thời điểm. Nhưng phải giữ **hai stack/ý nghĩa khác nhau**: stack frame DFS điều khiển quá trình duyệt và stack Tarjan lưu các đỉnh chưa được chốt SCC. Không được thay cả hai bằng một stack chung mà không thiết kế lại bất biến.

Nếu V cực lớn và muốn tránh đệ quy, cân nhắc bản Tarjan iterative đã được kiểm thử hoặc thuật toán SCC khác có cài đặt lặp phù hợp. Không đổi sang visited-only DFS vì nó sẽ mất tiêu chuẩn SCC.

### Ma trận kề

Nếu lưu đồ thị bằng **ma trận kề V×V**, để tìm tất cả neighbor của từng u có thể phải quét V vị trí, làm thời gian duyệt lên **O(V²)**. Cận O(V+E) gắn với danh sách kề hoặc cách liệt kê các cạnh thực có chi phí tỷ lệ số cạnh.

## 14. So sánh Tarjan và Kosaraju

Cả hai đều tìm SCC trong **O(V+E)** trên danh sách kề.

| Đặc điểm | Tarjan | Kosaraju |
|---|---|---|
| Số lượt DFS toàn đồ thị | Thường **một lượt** | **Hai lượt** |
| Thông tin chính | `index`, `lowlink`, stack SCC, `onStack` | Thứ tự hoàn tất, đồ thị đảo cạnh, visited |
| Có cần đồ thị chuyển vị? | **Không** | **Có**, hoặc một cách duyệt cạnh ngược tương đương |
| Cách chốt SCC | Khi `low[u]==index[u]`, pop tới u | DFS trên đồ thị chuyển vị theo thứ tự finish phù hợp |
| Độ phức tạp | O(V+E) | O(V+E) |
| Điểm dễ sai | onStack, hai nhánh cập nhật lowlink | Thứ tự finish và hướng cạnh ở lượt hai |

**Tarjan** thường tiện nếu muốn tìm SCC bằng một lượt DFS và không tạo đồ thị chuyển vị. **Kosaraju** có cấu trúc hai lượt dễ trực giác khi đã hiểu thứ tự hoàn tất DFS. Không phải cứ ít lượt DFS là luôn nhanh hơn trong mọi code/đầu vào; hằng số cài đặt, bộ nhớ, độ sâu DFS và cấu trúc graph vẫn quan trọng.

## 15. Các lỗi thường gặp

1. **Chỉ dùng visited** rồi gom tất cả đỉnh thăm từ một nguồn vào cùng SCC.
2. **Quên vòng lặp ngoài** nên bỏ sót SCC ở vùng không tới được từ đỉnh đầu.
3. **Dùng lowlink cho cả hai loại cạnh**, thay vì `low[v]` với con DFS mới và `index[v]` với cạnh tới v đã thăm còn trên stack.
4. **Không kiểm tra onStack** khi gặp đỉnh đã thăm, làm một cạnh tới SCC đã chốt kéo lowlink xuống sai.
5. **Pop khi dfs(u) trả về**, thay vì chỉ pop khi `low[u]==index[u]`.
6. **Pop chỉ riêng u** khi `low[u]==index[u]`, bỏ các đỉnh thuộc cùng SCC đang ở phía trên stack.
7. **Pop quá u**, lấy cả những đỉnh thuộc SCC khác chưa chốt.
8. **Quên đặt `onStack[v]=false`** lúc pop, làm cạnh sau tưởng v vẫn có thể gộp.
9. **Quên gán `componentOf[v]` cho toàn bộ các đỉnh vừa pop**.
10. **Khởi tạo index bằng 0 rồi kiểm tra index==0 là chưa thăm**, trong khi đỉnh khám phá đầu tiên cũng nhận 0.
11. **Không tăng nextIndex** khi khám phá đỉnh mới, khiến nhiều đỉnh có index giống nhau.
12. **Nhầm index/lowlink với khoảng cách hoặc độ sâu DFS**; đó là mốc khám phá và giá trị tổng hợp, không phải đường đi ngắn nhất.
13. **Nhầm stack Tarjan với call stack DFS**, pop đỉnh quá sớm hoặc dùng GRAY như onStack.
14. **Gộp các SCC có cạnh một chiều** vì cho rằng có đường từ A sang B thì A,B thuộc cùng SCC.
15. **Nhầm thứ tự pop/ID SCC là kết quả duy nhất**, rồi viết test yêu cầu một thứ tự dù neighbor được phép đổi.
16. **Đánh đồng SCC singleton với đỉnh cô lập**, quên rằng một đỉnh trong DAG có cạnh ra vẫn có thể là SCC riêng.
17. **Không xử lý self-loop**, dù nó không thay đổi số đỉnh SCC.
18. **Loại nhầm cạnh song song bằng cách thay đổi graph** khi bài còn cần đếm số cạnh, hoặc quên độ phức tạp theo E thực.
19. **Dùng thuật toán SCC trên đồ thị đã đảo chiều một cách vô thức**; tập SCC không đổi dưới đảo toàn bộ cạnh, nhưng thứ tự duyệt và DAG co đổi hướng.
20. **Không bỏ cạnh nội bộ khi co SCC**, tạo self-loop trong DAG co và kết luận sai là vẫn có chu trình.
21. **Không khử trùng cạnh DAG co** khi kết quả mong đợi chỉ là quan hệ kết nối, khiến danh sách cạnh trùng.
22. **Quên giới hạn stack đệ quy Java**, làm thuật toán đúng lý thuyết nhưng thất bại trên đường sâu.
23. **Dùng `int` quá nhỏ cho trọng số/tổng trong bài ứng dụng**, dù bản thân Tarjan chỉ cần chỉ số đỉnh.
24. **Không phân biệt độ phức tạp Tarjan thuần O(V+E) với bước sắp SCC/DAG co**, có thể có log.
25. **Ghi kết quả SCC trực tiếp vào dữ liệu mutable dùng chung**, khiến người gọi vô ý sửa ID nhóm sau khi thuật toán kết thúc.

## 16. Quy trình áp dụng Tarjan cho bài đồ thị mới

1. **Xác nhận hướng cạnh.** SCC là quan hệ tới được hai chiều trên đồ thị có hướng. Nếu đầu vào vô hướng và chỉ hỏi thành phần liên thông, BFS/DFS đơn giản là đủ.
2. **Đọc miền đỉnh.** Đảm bảo mọi ID hợp lệ, không bỏ đỉnh cô lập; quyết định cách xử lý self-loop và cạnh song song.
3. **Tạo danh sách kề.** Duyệt theo chiều cạnh gốc; không tự thêm cạnh ngược.
4. **Khởi tạo toàn bộ index=-1**, onStack=false, stack rỗng, nextIndex=0.
5. **Duyệt toàn đồ thị.** Với mỗi u chưa thăm, gọi strongConnect(u).
6. **Khám phá u.** Gán index và lowlink bằng nextIndex rồi tăng biến đếm; push u và đánh dấu onStack.
7. **Xét từng cạnh u→v.** Nếu v chưa thăm, DFS(v) và lấy min với low[v]. Nếu v đã thăm nhưng còn onStack, lấy min với index[v]. Nếu v đã pop, bỏ qua cạnh cho mục đích lowlink.
8. **Chỉ khi low[u]==index[u] mới pop.** Pop tới u, đánh dấu offStack, gán cùng componentId.
9. **Kiểm tra kết quả phân hoạch.** Mọi đỉnh phải có đúng một componentId trong miền `[0,C-1]`; tổng kích thước các SCC bằng V.
10. **Nếu bài cần DAG co**, tạo một đỉnh mỗi SCC, thêm cạnh giữa hai SCC khác ID và xử lý cạnh trùng theo yêu cầu.
11. **Tính toán trên DAG co** nếu cần DP, topo, số SCC nguồn/đích, hoặc điều kiện sau khi gom chu trình.
12. **Kiểm thử bằng graph nhỏ** có một chiều, chu trình, cạnh chéo tới SCC đã pop, đỉnh cô lập, self-loop và cạnh song song.
13. **Đánh giá giới hạn V/E và stack đệ quy**, chọn phiên bản cài đặt phù hợp bộ nhớ và độ sâu tối đa.

### Kiểm thử bằng oracle độc lập trên đồ thị rất nhỏ

Với V nhỏ, có thể chạy BFS/DFS từ **từng đỉnh u** để tính ma trận reachability `reach[u][v]` (hoặc dùng Floyd–Warshall). Khi ấy:

\[
u\sim v \iff reach[u][v]\ \land\ reach[v][u].
\]

Những lớp tương đương của quan hệ này phải trùng đúng các SCC của Tarjan, **không phụ thuộc thứ tự ID/pop**. Đây là một cách kiểm chứng mạnh để phát hiện lỗi lowlink/onStack.

Ngoài ra cần kiểm tra DAG co thật sự không có chu trình; nếu có chu trình giữa các ID khác nhau, kết quả tách SCC đã sai hoặc bước dựng DAG co sai.

## 17. Bài tập tự kiểm tra

**Bài 1 — SCC một chiều.** Với duy nhất cạnh `0→1`, có bao nhiêu SCC?

*Đáp án:* **Hai**: `{0}` và `{1}`. 0 tới 1 nhưng 1 không tới 0.

**Bài 2 — Cạnh ngược.** Với `0→1→2→0`, kết quả Tarjan gồm những SCC nào?

*Đáp án:* **Một SCC** `{0,1,2}`, vì mỗi đỉnh có đường tới mọi đỉnh khác dọc chu trình.

**Bài 3 — Con DFS mới.** Khi u đi tới neighbor v có index[v]=-1, sau khi DFS(v) kết thúc, dùng `index[v]` hay `low[v]` để cập nhật low[u]?

*Đáp án:* **`low[v]`**, vì v là **con DFS mới** và thông tin lowlink của cả miền con v cần được lan về u.

**Bài 4 — Đỉnh đã thăm còn onStack.** Nếu v đã có index và `onStack[v]=true`, công thức cập nhật là gì?

*Đáp án:* `low[u]=min(low[u],index[v])`. Không dùng tùy tiện `low[v]` ở nhánh này.

**Bài 5 — Đỉnh đã pop.** Nếu u có cạnh tới v nhưng v đã thuộc SCC hoàn tất, `onStack[v]=false`, làm gì?

*Đáp án:* **Không cập nhật low[u]** từ cạnh này. Một cạnh một chiều tới SCC khác không có nghĩa hai SCC liên thông mạnh.

**Bài 6 — Tiêu chuẩn pop.** Khi nào được lấy một nhóm SCC ra khỏi stack Tarjan?

*Đáp án:* Sau khi xử lý mọi neighbor của u, nếu **`low[u]==index[u]`**, pop liên tục tới và bao gồm u. Không pop từng đỉnh chỉ vì lời gọi DFS của nó kết thúc.

**Bài 7 — Stack khác call stack.** Một đỉnh có thể đã trả về khỏi hàm DFS nhưng vẫn `onStack=true` không?

*Đáp án:* **Có.** Nó có thể đang chờ ghép vào SCC có gốc ở một tổ tiên hoặc một nhóm còn mở. Stack Tarjan khác stack lời gọi đệ quy.

**Bài 8 — SCC singleton.** Đỉnh u có self-loop u→u thì SCC của u có bắt buộc chứa đỉnh khác không?

*Đáp án:* **Không.** `{u}` vẫn là SCC nếu không có đỉnh khác vừa tới được từ u vừa quay lại được u.

**Bài 9 — DAG co.** Vì sao không thể có chu trình giữa các SCC trong đồ thị co?

*Đáp án:* Chu trình giữa các SCC sẽ cho phép tất cả các nhóm trên chu trình tới nhau theo cả hai chiều, nên chúng phải là **một SCC lớn hơn**, trái tính cực đại ban đầu.

**Bài 10 — Độ phức tạp.** Vì sao Tarjan dùng danh sách kề chạy O(V+E)?

*Đáp án:* Mỗi đỉnh được khám phá một lần, mỗi cạnh xét một lần, và mỗi đỉnh push/pop stack SCC đúng một lần. Mọi phép cập nhật lowlink và onStack tốn O(1).

**Bài 11 — Cạnh chéo sai.** Đồ thị có cạnh `0→1`, `0→2`, `2→1`; khi DFS đi 0→1 và pop `{1}`, rồi tới 2→1, có nên hạ low[2] theo index[1] không?

*Đáp án:* **Không**. 1 đã được pop; nếu hạ low[2] thì có thể bỏ mất SCC singleton `{2}` và gộp sai với `{0}`.

**Bài 12 — Đồ thị không liên thông.** Nếu DFS từ 0 không tới đỉnh 10, Tarjan có bỏ qua 10 không?

*Đáp án:* **Không** nếu cài đặt đúng. Vòng lặp ngoài sẽ gặp index[10]=-1, gọi DFS(10) và ghi SCC `{10}`.

**Bài 13 — So sánh.** Tarjan và Kosaraju khác nhau chủ yếu ở cách tổ chức nào?

*Đáp án:* Tarjan dùng **một lượt DFS với index/lowlink/stack SCC**; Kosaraju dùng **thứ tự hoàn tất, đồ thị đảo cạnh và hai lượt DFS**. Cả hai có thời gian O(V+E).

**Bài 14 — Thứ tự xuất.** Nếu thay đổi thứ tự neighbor nhưng giữ nguyên các cạnh, danh sách SCC và ID có được phép thay đổi không?

*Đáp án:* **Thứ tự pop và ID có thể đổi**, nhưng **các tập đỉnh thuộc từng SCC không được đổi**. Khi kiểm thử, chuẩn hóa mỗi tập và thứ tự tập nếu bài không quy định thứ tự.

**Tổng kết:** Tarjan tìm **SCC của đồ thị có hướng** trong **O(V+E)** bằng **một lượt DFS**, `index`, `lowlink` và stack những đỉnh chưa chốt. Quy tắc phải nhớ: **con DFS mới ⇒ min với `low[v]`**; **đỉnh đã thăm và còn onStack ⇒ min với `index[v]`**; **đỉnh đã pop ⇒ bỏ qua**. Khi `low[u]==index[u]`, pop từ stack tới u để có một SCC. Sau khi gom SCC, đồ thị co luôn là **DAG**, tạo nền cho nhiều thuật toán tiếp theo.
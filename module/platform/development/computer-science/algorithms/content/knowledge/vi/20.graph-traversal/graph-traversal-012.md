# Thời điểm vào, ra và phân loại cạnh DFS

## 1. Mục tiêu: đọc được cấu trúc ẩn trong một lần duyệt sâu

**DFS (Depth-First Search, duyệt theo chiều sâu)** đi từ một đỉnh, ưu tiên thăm tiếp các đỉnh kề chưa được thăm, chỉ quay lui khi không còn lựa chọn. Ngoài việc đánh dấu đỉnh đã đi qua, DFS còn tạo ra hai thông tin quan trọng:

- **Thời điểm vào (discovery time, `tin[u]`):** thời điểm đỉnh `u` được phát hiện lần đầu, ngay khi bắt đầu xử lý nó.
- **Thời điểm ra (finish/exit time, `tout[u]`):** thời điểm xử lý xong toàn bộ các cạnh kề xuất phát từ `u` và rời đỉnh ấy.

Nhờ cặp thời điểm này, ta có thể biết một đỉnh là **tổ tiên/hậu duệ trong rừng DFS** hay thuộc một nhánh khác. Khi duyệt **đồ thị có hướng**, ta còn phân loại từng cạnh thành **cạnh cây (tree)**, **cạnh ngược (back)**, **cạnh xuôi không thuộc cây (forward)** và **cạnh ngang (cross)**.

Những thông tin này hữu ích trong:

- Phát hiện **chu trình có hướng**.
- Sắp xếp topo của **DAG** (Directed Acyclic Graph).
- Hiểu quan hệ tổ tiên trong cây/rừng DFS.
- Xây dựng các thuật toán liên quan đến **thành phần liên thông mạnh**, **cầu**, **đỉnh khớp**, **low-link** và nhiều cấu trúc đồ thị khác — mỗi thuật toán có các điều kiện bổ sung riêng.
- Kiểm tra lời giải DFS qua bất biến về khoảng thời gian và phân loại cạnh.

**Lưu ý cốt lõi:** phân loại bốn loại cạnh là cách diễn đạt chuẩn cho **đồ thị có hướng**. Với đồ thị vô hướng, nếu mỗi cạnh vật lý được xử lý đúng một lần thì DFS chỉ có **tree** và **back**; không được máy móc gán thêm forward/cross cho các bản sao chiều ngược của cùng một cạnh vô hướng.

## 2. Quy ước đồ thị, đồng hồ DFS và màu của đỉnh

Ta làm việc trước tiên với đồ thị có hướng `G=(V,E)`, với `V={0,1,\ldots,n-1}`. Danh sách kề `adj[u]` chứa các đích `v` của mọi cạnh có hướng `u\to v` theo **thứ tự được liệt kê**.

Đồ thị có thể:

- **Không liên thông yếu hoặc không liên thông mạnh**; phải duyệt từ nhiều gốc để bao phủ mọi đỉnh.
- Có **cạnh song song** giữa cùng hai đỉnh.
- Có **khuyên (self-loop)** như `u\to u`.
- Có đỉnh **cô lập** hoặc đồ thị rỗng `n=0`.

Thứ tự liệt kê cạnh kề và thứ tự chọn gốc ảnh hưởng tới **rừng DFS, thời điểm và loại cạnh**. Các đại lượng này không nhất thiết duy nhất với cùng một đồ thị. Chúng phải nhất quán với **một cuộc duyệt cụ thể**.

### Ba màu để diễn tả trạng thái đệ quy

| Màu | Ý nghĩa | Trạng thái của `tin/tout` |
|---|---|---|
| **WHITE — trắng (0)** | Chưa được phát hiện | Chưa có thời điểm vào, ra |
| **GRAY — xám (1)** | Đã vào, nhưng chưa ra; đang nằm trên **ngăn xếp DFS hoạt động** | `tin` đã gán, `tout` chưa gán |
| **BLACK — đen (2)** | Đã xử lý xong toàn bộ cạnh kề, đã rời DFS | Cả `tin` và `tout` đã gán |

Màu **GRAY** khác với “đã thăm” thông thường: nó phân biệt **tổ tiên đang hoạt động** với **đỉnh đã xử lý xong**, là thông tin quan trọng để phát hiện cạnh ngược.

### Đồng hồ vào–ra

Dùng một biến `timer` **toàn cục cho cả rừng DFS**, ban đầu `0`. Mỗi đỉnh làm đúng hai thao tác:

1. Khi vừa vào `u`: `tin[u]=++timer` và đổi màu thành GRAY.
2. Khi đã duyệt xong mọi cạnh kề của `u`: `tout[u]=++timer` và đổi màu thành BLACK.

Như vậy, nếu đồ thị có `n` đỉnh, các thời điểm là **`1,2,\ldots,2n`**, mỗi thời điểm được dùng đúng một lần. Với mỗi đỉnh:

\[
tin[u]<tout[u].
\]

Không nên đặt lại `timer=0` mỗi khi gặp thành phần mới: làm vậy sẽ mất tính nhất quán của các khoảng thời gian trên toàn rừng DFS.

**Không được nhầm thời điểm vào/ra với thời gian thực**: đây là các số thứ tự của sự kiện trong một lần chạy DFS, không phải mili-giây và không phải khoảng cách ngắn nhất trong đồ thị.

## 3. Cách tính thời điểm vào và ra

Pseudocode đầy đủ cho đồ thị có hướng:

```text
timer = 0
color[u] = WHITE với mọi u
parent[u] = -1 với mọi u

dfs(u):
    color[u] = GRAY
    tin[u] = ++timer

    for v in adj[u] theo thứ tự đã cho:
        if color[v] == WHITE:
            parent[v] = u
            dfs(v)
        // Các loại cạnh khác sẽ phân loại ở phần 5.

    color[u] = BLACK
    tout[u] = ++timer

for u = 0 .. n-1:
    if color[u] == WHITE:
        dfs(u)               // u là gốc của một cây DFS mới
```

Từ một gốc, DFS đi sâu qua những đỉnh WHITE trước khi quay lui. Khi gọi `dfs(v)` từ `dfs(u)`, toàn bộ công việc trong `dfs(v)` hoàn thành **trước** khi `dfs(u)` tiếp tục với cạnh kề kế tiếp.

Trong đồ thị không liên thông, vòng ngoài tạo một **rừng DFS** gồm nhiều cây. Mỗi cây có một gốc `parent[root]=-1`; các đỉnh con có `parent[v]` là đỉnh mà từ đó chúng được phát hiện bằng cạnh cây.

### Ví dụ nhỏ

Cho đồ thị có hướng:

```text
0 -> 1
1 -> 2
2 -> (không có cạnh)
```

DFS bắt đầu ở `0`:

```text
Sự kiện                  timer
Vào 0                      1
Vào 1                      2
Vào 2                      3
Ra 2                       4
Ra 1                       5
Ra 0                       6

tin  = [1, 2, 3]
tout = [6, 5, 4]
```

Khoảng thời gian của `2` nằm hoàn toàn trong khoảng của `1`, và khoảng của `1` nằm trong khoảng của `0`. Đây không phải sự trùng hợp: nó là tính chất nền tảng của DFS.

## 4. Định lý khoảng lồng nhau: nhận diện tổ tiên/hậu duệ

Đặt khoảng của một đỉnh `u`:

\[
I(u)=[tin[u],tout[u]].
\]

Với một cuộc duyệt DFS và đồng hồ như trên, **hai khoảng của hai đỉnh phân biệt hoặc lồng hoàn toàn, hoặc rời nhau**.

Nếu `u` là tổ tiên thật sự của `v` trong **rừng DFS**, thì:

\[
tin[u]<tin[v]<tout[v]<tout[u].
\]

Nếu hai đỉnh nằm trong các nhánh không có quan hệ tổ tiên/hậu duệ thì các khoảng **không giao nhau**:

\[
tout[u]<tin[v]\quad\text{hoặc}\quad tout[v]<tin[u].
\]

Vì vậy, một kiểm tra tổ tiên **bao gồm chính đỉnh đó** là:

\[
u\text{ là tổ tiên của }v
\iff tin[u]\le tin[v]\ \land\ tout[v]\le tout[u].
\]

Nếu chỉ muốn **tổ tiên thật sự** (`u\ne v`), dùng bất đẳng thức nghiêm ngặt ở hai đầu tương ứng.

### Vì sao khoảng không thể cắt nhau một phần?

Khi DFS bắt đầu xử lý `u`, nó chưa gán `tout[u]` cho tới khi **mọi lời gọi đệ quy con** trở về. Một đỉnh `v` được phát hiện bên trong lời gọi `dfs(u)` sẽ vào **sau** `u` và ra **trước** `u`. Nếu `v` không thuộc cây con của `u`, nó được xử lý hoàn chỉnh **trước khi** `u` bắt đầu hoặc **sau khi** `u` kết thúc; không thể chen một phần khoảng này vào giữa khoảng kia.

Đây gọi là **parenthesis theorem** (định lý dấu ngoặc): sự kiện mở khi vào và đóng khi ra của DFS tạo một chuỗi ngoặc lồng nhau hợp lệ.

### Hai lưu ý dễ sai

1. **Tổ tiên DFS không đồng nghĩa với khả năng đi tới theo một đường có hướng.** Có thể có đường đi `u\rightsquigarrow v` nhưng `v` được DFS phát hiện từ một gốc khác trước đó; `u` sẽ không là tổ tiên DFS của `v`. Khoảng `tin/tout` mô tả **cây duyệt cụ thể**, không phải toàn bộ quan hệ reachability.
2. **Hai đỉnh ở hai cây DFS khác nhau** có khoảng rời nhau. Dùng chung đồng hồ `timer` bảo đảm kiểm tra tổ tiên không lẫn các cây.

## 5. Bốn loại cạnh trong đồ thị có hướng

Xét một cạnh có hướng `u\to v` **ngay lúc DFS đang quét cạnh ấy**. Tại thời điểm này `u` đang GRAY.

| Loại cạnh | Trạng thái `v` khi xét cạnh `u\to v` | Ý nghĩa trong rừng DFS |
|---|---|---|
| **TREE** | `v` WHITE | Cạnh trực tiếp phát hiện `v`, nên `parent[v]=u` |
| **BACK** | `v` GRAY | Đi từ `u` về **tổ tiên đang hoạt động** `v`; gồm cả self-loop |
| **FORWARD** | `v` BLACK và `tin[u]<tin[v]` | Đi tới **hậu duệ thật sự** của `u`, nhưng không phải cạnh cây đã phát hiện nó |
| **CROSS** | `v` BLACK và `tin[u]>tin[v]` | Nối tới đỉnh đã hoàn tất không phải hậu duệ/tổ tiên DFS đang hoạt động |

### 5.1. TREE — cạnh cây

Cạnh `u\to v` là **TREE** nếu lúc xét nó, `v` còn WHITE. DFS ghi `parent[v]=u` rồi gọi `dfs(v)`. Đây là cạnh xuất hiện trong rừng DFS.

Trong một rừng có `c` gốc, luôn có **`n-c` cạnh cây**, bởi mỗi đỉnh không phải gốc được phát hiện đúng một lần qua một cạnh cây.

Ví dụ `0\to1\to2`: cả `0\to1` và `1\to2` là TREE nếu bắt đầu ở `0` và danh sách kề theo thứ tự đó.

### 5.2. BACK — cạnh ngược về tổ tiên đang hoạt động

Cạnh `u\to v` là **BACK** nếu `v` đang GRAY khi xét cạnh. GRAY có nghĩa `v` vẫn nằm trên ngăn xếp các lời gọi DFS dẫn tới `u`, nên `v` là tổ tiên của `u` hoặc `v=u` (self-loop).

Ví dụ đang duyệt `0\to1\to2`, gặp cạnh `2\to0`: `0` vẫn GRAY, nên `2\to0` là BACK.

Cạnh BACK lập tức chứng minh có **chu trình có hướng**: đi theo các cạnh TREE từ `v` xuống `u`, rồi đi cạnh `u\to v` để quay lại `v`. Với self-loop, chu trình có độ dài một.

### 5.3. FORWARD — cạnh xuôi không thuộc cây

Cạnh `u\to v` là **FORWARD** nếu `v` đã BLACK và là hậu duệ thật sự của `u` trong rừng DFS. Ví dụ:

```text
0 -> 1 -> 2
 \------> 2
```

Nếu DFS xét `0\to1` trước, qua `1` phát hiện `2` rồi quay về `0`, thì cạnh `0\to2` được xét sau cùng, lúc `2` đã BLACK và là hậu duệ của `0`. Nó được phân loại **FORWARD**, không phải TREE.

Khi đang thực hiện `dfs(u)` mà `v` đã BLACK, nếu `tin[v]>tin[u]` thì `v` phải nằm trong một nhánh con đã duyệt xong của `u` (vì `u` chưa kết thúc), nên là FORWARD. Sau khi duyệt xong, điều kiện tương đương là:

\[
tin[u]<tin[v]<tout[v]<tout[u].
\]

**Cạnh song song:** nếu có hai cạnh riêng `u\to v` và cạnh đầu tiên phát hiện `v`, cạnh thứ hai có thể là **FORWARD** khi quay lại quét; không được mặc nhiên gắn mọi cạnh `u\to v` là TREE chỉ vì `parent[v]=u`. Phân loại là theo **từng lần xuất hiện cạnh**, dựa trên thời điểm thực sự quét.

### 5.4. CROSS — cạnh ngang

Cạnh `u\to v` là **CROSS** nếu `v` đã BLACK và **không phải hậu duệ của `u`**. Đó có thể là đỉnh trong một nhánh đã xong, một cây DFS trước đó, hoặc một nhánh khác do thứ tự duyệt tạo ra.

Ví dụ:

```text
0 -> 1 -> 3
|         
+ -> 2 -> 3
```

Nếu DFS từ `0` duyệt `1` và `3` trước, lúc đến `2` thì `3` đã BLACK, không thuộc cây con DFS của `2`. Cạnh `2\to3` là CROSS.

Với điều kiện `u` còn GRAY khi quét `u\to v` và `v` BLACK, nếu `tin[v]<tin[u]` thì `v` đã được phát hiện trước `u` và không còn hoạt động: đó là CROSS. Trong rừng DFS cuối cùng, khoảng của `v` nằm **trước** khoảng của `u`.

### Không được phân loại chỉ bằng việc “đã thăm”

Nếu chỉ dùng boolean `visited[v]`, ta chỉ phân biệt WHITE với “không WHITE”, không biết `v` **GRAY** hay **BLACK**. Khi đó không thể xác định chính xác BACK đối lập với FORWARD/CROSS, và phép phát hiện chu trình cho **đồ thị có hướng** sẽ sai.

Cần ít nhất trạng thái **ba màu** hoặc tương đương `visited + inStack` để phát hiện cạnh BACK.

## 6. Ví dụ đầy đủ: một lần DFS chứa cả bốn loại cạnh

Xét đồ thị có hướng gồm tám đỉnh. Danh sách kề dưới đây cũng chính là **thứ tự quét cạnh**:

```text
0: [1, 2, 4]
1: [2, 3]
2: [0, 3]
3: [1]
4: [2, 5]
5: [6]
6: [4]
7: [6]

Vòng ngoài duyệt các gốc theo thứ tự 0,1,...,7.
```

### Diễn biến

DFS bắt đầu tại `0`:

1. `0\to1`: TREE; từ `1` đi `1\to2`: TREE.
2. Ở `2`, cạnh `2\to0` gặp `0` đang GRAY nên là BACK. Sau đó `2\to3` là TREE.
3. Ở `3`, `3\to1` gặp `1` GRAY nên là BACK. Kết thúc `3` rồi `2`.
4. Quay lại `1`, `1\to3` gặp `3` BLACK và thuộc cây con của `1` nên là FORWARD. Kết thúc `1`.
5. Quay lại `0`, `0\to2` là FORWARD (vì `2` đã hoàn tất và là hậu duệ của `0`).
6. `0\to4` là TREE. Ở `4`, `4\to2` là CROSS: `2` đã hoàn tất ở nhánh khác. `4\to5` rồi `5\to6` đều TREE.
7. Ở `6`, `6\to4` gặp `4` GRAY nên là BACK. Kết thúc `6,5,4,0`.
8. Đỉnh `7` vẫn WHITE, trở thành **gốc DFS thứ hai**. Cạnh `7\to6` là CROSS vì `6` đã BLACK trong cây trước đó.

### Thời điểm và cây cha

| Đỉnh `u` | `tin[u]` | `tout[u]` | `parent[u]` |
|---:|---:|---:|---:|
| 0 | 1 | 14 | -1 |
| 1 | 2 | 7 | 0 |
| 2 | 3 | 6 | 1 |
| 3 | 4 | 5 | 2 |
| 4 | 8 | 13 | 0 |
| 5 | 9 | 12 | 4 |
| 6 | 10 | 11 | 5 |
| 7 | 15 | 16 | -1 |

Hai gốc `0` và `7` có `parent=-1`. Số cạnh TREE bằng `8-2=6`.

Sự kiện quét cạnh, theo đúng thứ tự:

```text
0->1 TREE
1->2 TREE
2->0 BACK
2->3 TREE
3->1 BACK
1->3 FORWARD
0->2 FORWARD
0->4 TREE
4->2 CROSS
4->5 TREE
5->6 TREE
6->4 BACK
7->6 CROSS
```

Có tổng `13` cạnh, phân thành:

- **6 TREE**.
- **3 BACK**.
- **2 FORWARD**.
- **2 CROSS**.

Kiểm tra khoảng:

- `I(0)=[1,14]` bao trùm `I(1)=[2,7]` và `I(4)=[8,13]`.
- `I(1)` bao trùm `I(2)=[3,6]`, `I(2)` bao trùm `I(3)=[4,5]`.
- `I(4)` bao trùm `I(5)=[9,12]` và `I(6)=[10,11]`.
- `I(7)=[15,16]` rời toàn bộ cây gốc `0`.

Chính vì `2` và `4` nằm ở hai nhánh DFS rời nhau, cạnh `4\to2` là CROSS. Nó **không** phải BACK, vì lúc quét cạnh ấy `2` đã **BLACK**, không còn trên ngăn xếp DFS đang hoạt động.

## 7. Phân loại cạnh và phát hiện chu trình có hướng

Đối với **đồ thị có hướng**, một định lý căn bản là:

\[
\boxed{G\text{ có chu trình có hướng}
\iff\text{DFS gặp ít nhất một cạnh BACK}.}
\]

### Chiều 1: gặp BACK thì chắc chắn có chu trình

Nếu đang ở `u` và gặp cạnh `u\to v` tới `v` GRAY, thì `v` là tổ tiên của `u` trong cây DFS (hoặc `v=u`). Đường đi TREE từ `v` xuống `u`, ghép với cạnh `u\to v`, tạo chu trình có hướng.

Vậy có BACK `\Rightarrow` có chu trình.

### Chiều 2: có chu trình thì sẽ gặp BACK

Giả sử có chu trình `v_0\to v_1\to\cdots\to v_t\to v_0`. Chọn đỉnh `v` trên chu trình có **thời điểm được phát hiện sớm nhất** trong cuộc duyệt DFS. Từ `v` có đường đi theo các cạnh của chu trình đến mọi đỉnh còn lại trên chu trình.

Trong khi lời gọi `dfs(v)` còn hoạt động, DFS sẽ khám phá các đỉnh trên những đường đi đó nếu chúng chưa được phát hiện trước. Do `v` là đỉnh được phát hiện sớm nhất trên chu trình, các đỉnh còn lại không thể đã BLACK trước khi `v` bắt đầu. Cuối cùng, cạnh quay về `v` từ đỉnh đứng ngay trước nó trên chu trình sẽ gặp `v` còn GRAY, nên được phân loại BACK.

Vậy có chu trình `\Rightarrow` có BACK.

### Hai hậu quả

1. Với đồ thị có hướng, chỉ cần gặp cạnh **tới GRAY** là có thể báo có chu trình ngay. Không cần chờ `tin/tout` hoàn chỉnh để kết luận.
2. Nếu **không có BACK**, đồ thị là DAG và có thể sắp xếp topo bằng **đảo thứ tự kết thúc DFS**.

**Không dùng dấu hiệu “cạnh đến đỉnh đã thăm” để phát hiện chu trình có hướng.** Cạnh FORWARD hoặc CROSS có thể tồn tại trong DAG và không phải chu trình.

## 8. Thời điểm ra và sắp xếp topo của DAG

Một **thứ tự topo** là thứ tự các đỉnh sao cho với mọi cạnh `u\to v`:

\[
position[u]<position[v].
\]

Nó chỉ tồn tại nếu đồ thị có hướng **không có chu trình**.

Trong một DAG, mọi cạnh `u\to v` đều thỏa:

\[
tout[u]>tout[v].
\]

Vì:

- Nếu `v` là hậu duệ DFS của `u` (TREE hoặc FORWARD), `v` kết thúc trước `u`.
- Nếu là CROSS, `v` đã kết thúc trước khi `u` tiếp tục/được phát hiện, nên vẫn `tout[v]<tout[u]`.
- Không thể có BACK trong DAG.

Vì thế, sắp các đỉnh theo **`tout` giảm dần** cho một thứ tự topo hợp lệ.

Trong DFS, ta có thể ghi `finishOrder.add(u)` ngay khi ra `u`. Danh sách này có `tout` **tăng dần**, nên chỉ cần đảo ngược sau khi duyệt xong.

### Một DAG có cả FORWARD và CROSS

```text
0: [1, 2, 3]
1: [3]
2: [3]
3: []
4: [2]
```

Thứ tự quét từ đỉnh `0` rồi đến các đỉnh WHITE còn lại cho:

```text
tin  = [1, 2, 6, 3, 9]
tout = [8, 5, 7, 4, 10]

Các cạnh theo thứ tự quét:
0->1 TREE
1->3 TREE
0->2 TREE
2->3 CROSS
0->3 FORWARD
4->2 CROSS

Danh sách ra (finish order): [3, 1, 2, 0, 4]
Thứ tự topo đảo lại:      [4, 0, 2, 1, 3]
```

Kiểm tra mọi cạnh đều hướng **từ trái sang phải** trong thứ tự topo `[4,0,2,1,3]`:

- `4\to2`: `4` đứng trước `2`.
- `0\to1,0\to2,0\to3`: `0` đứng trước cả ba đích.
- `1\to3` và `2\to3`: `3` ở sau `1` và `2`.

Như vậy, **FORWARD và CROSS không ngăn cản sắp xếp topo**. Chỉ chu trình — tương đương có BACK trong DFS có hướng — mới làm topo bất khả thi.

**Lưu ý:** không được xuất “topo” nếu DFS phát hiện BACK. Đảo finish order của một đồ thị có chu trình vẫn cho một danh sách đỉnh, nhưng danh sách đó **không thể** thỏa mọi cạnh.

## 9. Đồ thị vô hướng: xử lý hai bản ghi của một cạnh

Với đồ thị **vô hướng**, mỗi cạnh vật lý `{u,v}` thường xuất hiện thành **hai mục** trong danh sách kề:

```text
u: ... v ...
v: ... u ...
```

Nếu xử lý hai mục này như hai cạnh có hướng độc lập, sau khi thăm `v` từ `u`, bản ghi `v\to u` sẽ gặp `u` GRAY và bị đánh BACK. Nhưng **đó chỉ là chiều ngược của chính cạnh cây vừa đi qua**, không phải chu trình độc lập.

Do vậy, trong đồ thị vô hướng đơn, DFS thường **bỏ qua cạnh cha** khi duyệt từ con trở về cha. Khi ấy các cạnh vật lý được phân thành:

- **TREE:** phát hiện đỉnh chưa thăm.
- **BACK:** nối một đỉnh tới tổ tiên đã được thăm qua **một cạnh vật lý khác**.

Không có các cạnh FORWARD/CROSS riêng biệt nếu phân loại **mỗi cạnh vô hướng đúng một lần** theo một cuộc duyệt DFS tiêu chuẩn.

### 9.1. Mã giả cho đồ thị vô hướng có thể có cạnh song song

Nếu đồ thị có thể có **nhiều cạnh song song** giữa cùng cặp đỉnh, chỉ kiểm tra `if(v==parent[u]) continue` là **không đủ**. Hai cạnh vật lý khác nhau cùng nối `u` với cha là hai cạnh khác nhau: bỏ tất cả sẽ che mất một chu trình độ dài hai trong **đa đồ thị**.

Cách chắc chắn là gắn **ID duy nhất cho từng cạnh vô hướng**; hai mục kề của cùng một cạnh mang cùng ID. Sau đó đánh dấu cạnh đã xử lý:

```text
for each undirected edge e = {u,v}:
    adj[u].add((v, e.id))
    adj[v].add((u, e.id))
    // Với khuyên, vẫn phải thống nhất cùng một edge ID.

dfs(u):
    color[u] = GRAY
    tin[u] = ++timer

    for (v, edgeId) in adj[u]:
        if seenEdge[edgeId]:
            continue
        seenEdge[edgeId] = true   // chỉ phân loại mỗi cạnh vật lý một lần

        if color[v] == WHITE:
            classify edgeId as TREE
            parent[v] = u
            dfs(v)
        else if color[v] == GRAY:
            classify edgeId as BACK
        else:
            // Với đồ thị vô hướng được duyệt DFS chuẩn,
            // cạnh vật lý chưa xử lý tới BLACK không xảy ra.

    color[u] = BLACK
    tout[u] = ++timer
```

Đối với **đồ thị vô hướng đơn** (không khuyên, không cạnh song song), có thể bỏ riêng cạnh nối với cha; còn với đa đồ thị, ID cạnh giúp phân biệt chính xác từng bản sao.

### 9.2. Ví dụ

Cho các cạnh vật lý:

```text
0--1, 1--2, 2--0, 2--3
```

DFS từ `0`, nếu đi theo `0-1-2-3` trước, ba cạnh `0-1`, `1-2`, `2-3` là TREE. Cạnh `2-0` còn lại là BACK vì nó nối `2` tới tổ tiên `0` mà không phải cạnh cha đã dùng. Do đó có chu trình vô hướng `0-1-2-0`.

Ngược lại, nếu đồ thị chỉ có đúng một cạnh `0--1`, bản ghi chiều ngược `1\to0` **không phải** một chu trình mới.

### 9.3. Phân biệt quy tắc phát hiện chu trình

- **Có hướng:** cạnh `u\to v` tới GRAY tạo chu trình có hướng. Không bỏ cạnh về “cha” vì cạnh có hướng `u\to parent[u]` nếu thực sự tồn tại là một cạnh hợp lệ và có thể tạo chu trình.
- **Vô hướng:** cạnh vật lý đã dùng để đi từ cha xuống con phải được bỏ khi xét chiều ngược, tốt nhất qua **edge ID** nếu có cạnh song song/khuyên.

Không được dùng chung một điều kiện “bỏ cạnh về cha” cho cả hai loại đồ thị.

## 10. Java 17+ hoàn chỉnh: thời điểm, loại cạnh, chu trình và topo

Chương trình dưới đây chạy trên **đồ thị có hướng**, nhận `int[][] graph` là danh sách kề theo thứ tự đã cho. Nó:

1. Kiểm tra tất cả đỉnh kề nằm trong `[0,n-1]`, không nhận hàng kề `null`.
2. Chạy DFS từ tất cả gốc WHITE theo thứ tự tăng.
3. Ghi `tin[]`, `tout[]` và `parent[]`, dùng chung một đồng hồ.
4. Ghi sự kiện cho **từng cạnh có hướng** ngay lúc xét, gồm cả cạnh song song và self-loop nếu có.
5. Phát hiện chu trình khi gặp BACK.
6. Chỉ trả thứ tự topo khi đồ thị **không có chu trình**, bằng cách đảo `finishOrder`.

**Chính sách thời điểm:** vào là `++timer`, ra cũng `++timer`. Giá trị đầu tiên là `1`. Vì vậy kết quả mẫu phía dưới không phụ thuộc đồng hồ hệ thống.

Lưu thành **`DfsEdgeClassificationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public final class DfsEdgeClassificationDemo {
    private DfsEdgeClassificationDemo() {
    }

    private static final int WHITE = 0;
    private static final int GRAY = 1;
    private static final int BLACK = 2;

    public static final class Result {
        private final int[] tin;
        private final int[] tout;
        private final int[] parent;
        private final int[] color;
        private final List<String> edgeEvents = new ArrayList<>();
        private final List<Integer> finishOrder = new ArrayList<>();

        private int timer;
        private boolean hasCycle;

        private Result(int n) {
            tin = new int[n];
            tout = new int[n];
            parent = new int[n];
            color = new int[n];
            Arrays.fill(parent, -1);
        }

        public int[] discovery() {
            return tin.clone();
        }

        public int[] finish() {
            return tout.clone();
        }

        public int[] parents() {
            return parent.clone();
        }

        public List<String> edges() {
            return List.copyOf(edgeEvents);
        }

        public List<Integer> finishingOrder() {
            return List.copyOf(finishOrder);
        }

        public boolean hasCycle() {
            return hasCycle;
        }

        public List<Integer> topologicalOrder() {
            if (hasCycle) {
                throw new IllegalStateException(
                    "A directed cycle prevents topological sorting"
                );
            }
            List<Integer> result = new ArrayList<>(finishOrder);
            Collections.reverse(result);
            return List.copyOf(result);
        }
    }

    public static Result analyze(int[][] graph) {
        Objects.requireNonNull(graph, "graph");
        int n = graph.length;

        // Kiểm tra toàn bộ đầu vào trước khi bắt đầu DFS.
        for (int u = 0; u < n; u++) {
            if (graph[u] == null) {
                throw new IllegalArgumentException(
                    "Adjacency row must not be null"
                );
            }
            for (int v : graph[u]) {
                if (v < 0 || v >= n) {
                    throw new IllegalArgumentException(
                        "Neighbor outside 0..n-1"
                    );
                }
            }
        }

        Result result = new Result(n);
        for (int u = 0; u < n; u++) {
            if (result.color[u] == WHITE) {
                dfs(u, graph, result);
            }
        }
        return result;
    }

    private static void dfs(int u, int[][] graph, Result r) {
        r.color[u] = GRAY;
        r.tin[u] = ++r.timer;

        for (int v : graph[u]) {
            if (r.color[v] == WHITE) {
                r.edgeEvents.add(u + "->" + v + " TREE");
                r.parent[v] = u;
                dfs(v, graph, r);
            } else if (r.color[v] == GRAY) {
                r.edgeEvents.add(u + "->" + v + " BACK");
                r.hasCycle = true;
            } else {
                // v BLACK; u vẫn GRAY.
                // tin[v] > tin[u] => v đã hoàn tất ở cây con u.
                String type = r.tin[u] < r.tin[v]
                    ? "FORWARD"
                    : "CROSS";
                r.edgeEvents.add(u + "->" + v + " " + type);
            }
        }

        r.color[u] = BLACK;
        r.tout[u] = ++r.timer;
        r.finishOrder.add(u);
    }

    public static void main(String[] args) {
        int[][] directed = {
            {1, 2, 4},
            {2, 3},
            {0, 3},
            {1},
            {2, 5},
            {6},
            {4},
            {6}
        };

        Result a = analyze(directed);
        System.out.println("Directed tin: "
            + Arrays.toString(a.discovery()));
        System.out.println("Directed tout: "
            + Arrays.toString(a.finish()));
        System.out.println("Directed parent: "
            + Arrays.toString(a.parents()));
        System.out.println("Directed edges:");
        for (String edge : a.edges()) {
            System.out.println(edge);
        }
        System.out.println("Directed has cycle: "
            + a.hasCycle());

        int[][] dag = {
            {1, 2, 3},
            {3},
            {3},
            {},
            {2}
        };

        Result b = analyze(dag);
        System.out.println("DAG tin: "
            + Arrays.toString(b.discovery()));
        System.out.println("DAG tout: "
            + Arrays.toString(b.finish()));
        System.out.println("DAG edges:");
        for (String edge : b.edges()) {
            System.out.println(edge);
        }
        System.out.println("DAG has cycle: "
            + b.hasCycle());
        System.out.println("DAG topological: "
            + b.topologicalOrder());

        Result empty = analyze(new int[0][]);
        System.out.println("Empty vertices: "
            + empty.discovery().length);

        Result selfLoop = analyze(new int[][] {{0}});
        System.out.println("Self-loop edges: "
            + selfLoop.edges());
        System.out.println("Self-loop cycle: "
            + selfLoop.hasCycle());

        boolean rejected = false;
        try {
            analyze(new int[][] {{1}});
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("Invalid neighbor rejected: " + rejected);
    }
}
```

Biên dịch và chạy bằng **JDK 17 hoặc mới hơn**:

```bash
javac -encoding UTF-8 DfsEdgeClassificationDemo.java
java DfsEdgeClassificationDemo
```

**Đầu ra chuẩn:**

```text
Directed tin: [1, 2, 3, 4, 8, 9, 10, 15]
Directed tout: [14, 7, 6, 5, 13, 12, 11, 16]
Directed parent: [-1, 0, 1, 2, 0, 4, 5, -1]
Directed edges:
0->1 TREE
1->2 TREE
2->0 BACK
2->3 TREE
3->1 BACK
1->3 FORWARD
0->2 FORWARD
0->4 TREE
4->2 CROSS
4->5 TREE
5->6 TREE
6->4 BACK
7->6 CROSS
Directed has cycle: true
DAG tin: [1, 2, 6, 3, 9]
DAG tout: [8, 5, 7, 4, 10]
DAG edges:
0->1 TREE
1->3 TREE
0->2 TREE
2->3 CROSS
0->3 FORWARD
4->2 CROSS
DAG has cycle: false
DAG topological: [4, 0, 2, 1, 3]
Empty vertices: 0
Self-loop edges: [0->0 BACK]
Self-loop cycle: true
Invalid neighbor rejected: true
```

### Giải thích mã quan trọng

- `analyze` xử lý mọi đỉnh trong vòng ngoài. Nếu một đỉnh đã BLACK do cây DFS trước đó, nó không trở thành gốc nữa. Đỉnh `7` trong ví dụ `directed` là một gốc mới vì không có đường từ gốc `0` phát hiện nó.
- Với cạnh tới WHITE, mã ghi sự kiện TREE, gán `parent` và gọi DFS con. Sự kiện được ghi **trước** khi đi sâu để thứ tự in thể hiện đúng thời điểm quét cạnh.
- Với cạnh tới GRAY, mã ghi BACK và bật `hasCycle`. Self-loop `0\to0` gặp chính đỉnh `0` GRAY nên được xử lý đúng.
- Với cạnh tới BLACK, mã so `tin` để phân biệt FORWARD/CROSS. Điều này đúng vì **`u` vẫn GRAY khi quét cạnh**, nên một `v` BLACK được phát hiện **sau `u`** buộc phải thuộc cây con DFS của `u`.
- `finishOrder.add(u)` xuất hiện **sau** khi hoàn thành mọi cạnh kề của `u`. `topologicalOrder` đảo danh sách này nhưng **ném ngoại lệ khi có chu trình**, không đưa một thứ tự không hợp lệ ra ngoài.
- Các mảng trả qua `discovery()`, `finish()` và `parents()` được sao chép bằng `clone()` để người gọi không vô tình làm thay đổi dữ liệu phân tích bên trong.

### Khác biệt giữa `tin`, `tout` và `parent`

`parent[v]` chỉ phản ánh **cạnh TREE trực tiếp đưa DFS tới `v`**. Một cạnh FORWARD từ tổ tiên tới hậu duệ không làm thay đổi `parent[v]`. Một cạnh CROSS nối hai nhánh cũng không làm đổi cha.

`tout[u]` chỉ được gán khi `u` chuyển BLACK. Khi `v` còn GRAY, chưa được dùng `tout[v]` để phân loại BACK; hãy dựa vào **màu**. Có thể dùng `tin/tout` để xác minh quan hệ tổ tiên **sau khi DFS kết thúc**.

## 11. Chứng minh tính đúng của dấu thời điểm và loại cạnh

### 11.1. Bất biến về màu

Khi `dfs(u)` đang hoạt động:

- `u` đã được phát hiện nên không WHITE.
- `u` chưa kết thúc, nên GRAY.
- Mọi lời gọi đệ quy đang chờ trở về nằm trên **cùng một đường tổ tiên** của `u`.
- Một đỉnh BLACK đã hoàn tất toàn bộ việc duyệt các cạnh của chính nó và không bị gọi DFS lại.

Nhờ chỉ chuyển `WHITE→GRAY→BLACK` đúng một lần cho mỗi đỉnh, thuật toán không phát hiện lại đỉnh và kết thúc sau hữu hạn thao tác.

### 11.2. Chứng minh phân loại các cạnh phủ hết và không trùng

Mỗi cạnh `u\to v` được quét đúng một lần trong vòng kề của `u`. Lúc ấy `v` có đúng một trong ba màu:

- WHITE: phát hiện `v` bằng cạnh này ⇒ **TREE**.
- GRAY: `v` thuộc ngăn xếp DFS và là tổ tiên của `u` ⇒ **BACK**.
- BLACK: `v` đã hoàn tất. Nếu `tin[v]>tin[u]`, `v` được phát hiện khi `u` đã hoạt động; do `u` chưa kết thúc nên `v` nằm trong cây con của `u` ⇒ **FORWARD**. Nếu `tin[v]<tin[u]`, `v` hoàn tất từ trước/ở nhánh khác ⇒ **CROSS**.

Do thời điểm phát hiện của hai đỉnh phân biệt không thể bằng nhau, hai trường hợp cuối loại trừ nhau. Vì vậy mỗi cạnh được gán **đúng một** trong bốn loại.

**Chú ý cạnh song song:** hai lần xuất hiện của `u\to v` có thể mang hai loại khác nhau, vì màu của `v` thay đổi sau khi quét cạnh đầu tiên. Đó không phải lỗi phân loại; mỗi cạnh vật lý có thời điểm quét riêng.

### 11.3. Chứng minh khoảng tổ tiên

DFS không ra `u` trước khi mọi DFS con của nó hoàn thành. Bởi vậy với mọi hậu duệ `v`, thời điểm vào `u` đi trước `v`, và thời điểm ra `u` đi sau `v`. Với hai đỉnh không có quan hệ tổ tiên, các khoảng không thể cắt nhau một phần do ngăn xếp DFS có tính lồng nhau.

Từ đó suy ra quy tắc kiểm tra tổ tiên bằng bất đẳng thức `tin/tout`. Đây cũng là cơ sở để hậu kiểm loại FORWARD và CROSS.

### 11.4. Độ đúng của topo khi không có chu trình

Trong DAG không có cạnh BACK. Với mỗi cạnh TREE hoặc FORWARD, `v` là hậu duệ nên `tout[v]<tout[u]`. Với cạnh CROSS tới BLACK, `v` đã hoàn tất trước khi `u` hoàn tất, nên cũng `tout[v]<tout[u]`. Khi sắp `tout` giảm dần, mọi cạnh đi từ đỉnh đứng trước sang đỉnh đứng sau. Đó chính là điều kiện topo.

## 12. Độ phức tạp và giới hạn của đệ quy Java

Ký hiệu `V` là số đỉnh và `E` là **số cạnh có hướng**, tính cả các lần xuất hiện trùng trong danh sách kề:

- Mỗi đỉnh được chuyển WHITE→GRAY→BLACK **một lần**.
- Mỗi danh sách kề được duyệt **một lần**, nên mỗi cạnh được xét **một lần**.
- Tổng thời gian DFS và phân loại cạnh: **`O(V+E)`**.
- Mảng màu, `tin`, `tout`, `parent`, danh sách finish và ngăn xếp DFS cần **`O(V)`** chỗ.
- Ví dụ còn lưu một chuỗi mô tả cho **mỗi cạnh**, nên **`O(E)` bản ghi sự kiện**. Tổng bộ nhớ phụ của **chính chương trình minh họa** là **`O(V+E)`**, chưa kể danh sách kề đầu vào.
- Nếu chỉ cần phát hiện chu trình hoặc thời điểm, có thể bỏ `edgeEvents` và giữ **`O(V)` bộ nhớ phụ** (không tính biểu diễn đồ thị).

### Đệ quy sâu

Trong đường đi dài `0→1→2→...→(n-1)`, độ sâu đệ quy có thể là `O(V)`. Java có thể ném `StackOverflowError` nếu `V` lớn và giới hạn ngăn xếp JVM không đủ.

Có thể chuyển sang **DFS lặp với ngăn xếp các khung (stack frames)**. Nhưng phải lưu **vị trí cạnh kề tiếp theo** cho mỗi khung, không chỉ đẩy các đỉnh:

```text
Frame(u, nextNeighborIndex)

Khi đẩy khung mới u:
    chuyển u thành GRAY
    gán tin[u] = ++timer

Trong vòng lặp:
    lấy khung trên cùng (u, nextNeighborIndex)
    nếu còn cạnh kề:
        xét đúng cạnh tiếp theo; tăng nextNeighborIndex
        nếu v WHITE:
            gán parent[v]=u và đẩy khung v
        nếu v GRAY/BLACK:
            phân loại cạnh như DFS đệ quy
    nếu hết cạnh kề:
        gán tout[u] = ++timer
        chuyển u thành BLACK
        thêm u vào finishOrder
        pop khung
```

Nếu đặt `tout[u]` ngay khi **đưa `u` vào stack** thay vì khi **pop sau khi xử lý xong cạnh kề**, các khoảng sẽ sai, không giữ định lý lồng nhau. Việc dùng stack lặp không tự động bảo đảm thời điểm ra đúng: phải mô phỏng **cả sự kiện vào lẫn ra**.

## 13. Ứng dụng mở rộng và những điều không nên suy diễn

### 13.1. Topo và phát hiện chu trình

Đối với đồ thị có hướng, chỉ cần ba màu là có thể phát hiện chu trình và lấy thứ tự topo bằng đảo danh sách kết thúc. Khi có BACK, dừng hoặc báo không có topo.

Nếu đồ thị có rất nhiều thành phần, vẫn phải duyệt mọi gốc WHITE. Một DFS bắt đầu từ `0` có thể không chạm tới đỉnh `7`; trả kết quả chỉ cho thành phần của `0` là thiếu.

### 13.2. Kosaraju: thứ tự ra của DFS

Trong thuật toán **Kosaraju** tìm các thành phần liên thông mạnh, một lượt DFS ghi **thứ tự kết thúc**; một lượt DFS khác trên **đồ thị đảo chiều** hoặc theo phiên bản tương đương sử dụng thứ tự thích hợp để gom SCC.

Cần hiểu chính xác **đồ thị nào được duyệt trước**, **đồ thị nào bị đảo cạnh**, và **thứ tự gốc** khi học thuật toán đó. Biết `tout` là nền tảng, nhưng chỉ có `tin/tout` của một DFS thông thường chưa tự nó xác định tất cả SCC.

### 13.3. Cầu, đỉnh khớp và `low[]` của đồ thị vô hướng

Trong đồ thị **vô hướng**, thời điểm vào `tin[u]` kết hợp với `low[u]` giúp tìm:

- **Cầu (bridge):** một cạnh TREE `(u,v)`, với `u` là cha của `v`, là cầu nếu `low[v]>tin[u]`.
- **Đỉnh khớp (articulation point):** có điều kiện riêng cho gốc DFS và cho đỉnh không phải gốc, dựa vào các giá trị `low` của con.

Khái niệm `low[u]` ở đây tóm tắt thời điểm vào nhỏ nhất mà cây con có thể tiếp cận qua đường đi TREE xuống dưới và nhiều nhất một cạnh BACK phù hợp. Nó **không** phải `tout[u]` và không phải giá trị nhỏ nhất của tất cả `tin` của mọi đỉnh reachable trong toàn đồ thị.

Nếu có cạnh song song, phải bỏ **đúng cạnh TREE đã dùng để vào đỉnh con**, theo **ID cạnh**, chứ không bỏ mọi cạnh tới đỉnh cha; nếu không, thuật toán tìm cầu có thể báo sai.

### 13.4. Cạnh FORWARD/CROSS trong đồ thị có hướng không có nghĩa giống cạnh vô hướng

Một cạnh CROSS trong đồ thị có hướng **không nhất thiết chỉ nối hai thành phần liên thông khác nhau**; nó có thể nối hai nhánh thuộc cùng một cây DFS. Một cạnh FORWARD vẫn là cạnh thật của đồ thị, dù không nằm trong cây DFS.

Phân loại cạnh mô tả **quan hệ với rừng DFS đã tạo**. Nó không đơn độc kết luận cạnh đó có thuộc chu trình nào, có phải cầu, hay có thể bỏ khỏi đồ thị mà không đổi reachability. Muốn kết luận cần chứng minh bổ sung cho đúng bài toán.

### 13.5. Không nhầm DFS với Euler tour có một mốc vào

Một số thuật toán cây dùng kỹ thuật **Euler tour** với biến `timer` tăng **chỉ khi vào đỉnh**, đặt `tin[u]` khi vào và `tout[u]` sau khi duyệt xong nhưng không nhất thiết tăng đồng hồ lúc ra. Khi ấy khoảng `[tin[u],tout[u]]` thường biểu diễn một đoạn liên tiếp của thứ tự vào và cần dùng điều kiện theo quy ước riêng.

Trong bài này, `timer` tăng **hai lần trên mỗi đỉnh**, cả lúc vào và ra. Không được lấy mã/định lý dùng quy ước một đồng hồ chỉ tăng khi vào rồi áp thẳng vào một định dạng thời gian khác mà không kiểm tra dấu so sánh.

## 14. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ dùng `visited[]` boolean | Không phân biệt GRAY với BLACK; dễ nhận nhầm chu trình | Dùng ba màu hoặc `inRecursionStack[]` |
| Gán `tout[u]` ngay khi vào `u` | Không phản ánh lúc con đã xong, hỏng định lý khoảng lồng nhau | Chỉ gán `tout` **sau** toàn bộ cạnh kề |
| Reset `timer` mỗi cây DFS | Các khoảng của nhiều cây bị trùng | Dùng một đồng hồ cho cả rừng |
| Chỉ DFS từ đỉnh `0` | Bỏ sót thành phần không tới được từ `0` | Vòng ngoài qua mọi đỉnh WHITE |
| Nhầm BLACK thành GRAY | Gọi CROSS/FORWARD là BACK; báo chu trình giả | GRAY là trên stack hiện tại; BLACK đã hoàn tất |
| Mọi cạnh tới “đã thăm” đều báo chu trình có hướng | DAG cũng có FORWARD/CROSS | Chỉ báo chu trình khi cạnh tới GRAY |
| Dùng `tin[v]>tin[u]` để quyết định BACK | Sai vì BACK đi tới tổ tiên có `tin` nhỏ hơn | Dùng **màu GRAY** tại lúc quét |
| Thấy `tin[u]<tin[v]` là gán FORWARD ngay | Có thể là TREE | Kiểm tra WHITE trước, chỉ FORWARD khi `v` BLACK |
| Thấy `parent[v]=u` là mọi cạnh `u\to v` đều TREE | Cạnh song song còn lại có thể FORWARD | Phân loại **từng cạnh tại lúc quét** |
| Quên self-loop `u\to u` | Bỏ chu trình độ dài 1 | GRAY ở chính `u` ⇒ BACK |
| Dùng quy tắc “bỏ cạnh về cha” của vô hướng cho đồ thị có hướng | Bỏ mất một cạnh ngược thật và chu trình | Đồ thị có hướng **không** bỏ cạnh về cha |
| Trong đa đồ thị vô hướng bỏ mọi cạnh tới đỉnh cha | Mất cạnh song song và có thể báo sai cầu/chu trình | Dùng **ID cạnh vật lý** |
| Dùng hai mục kề của một cạnh vô hướng như hai cạnh hướng độc lập | Đếm bản sao chiều ngược thành cạnh BACK giả | Phân loại **mỗi cạnh vật lý một lần** |
| Đảo finish order để xuất topo dù có BACK | Tạo thứ tự không phải topo | Chỉ xuất topo nếu **không có chu trình** |
| Gọi CROSS là “cạnh giữa hai thành phần” | Có thể là giữa hai nhánh trong cùng một cây | Dựa trên khoảng DFS thay vì tên gọi trực giác |
| Cho rằng `tin/tout` xác định reachability | Tổ tiên DFS không tương đương đường đi có hướng | Phân biệt DFS tree và toàn đồ thị |
| Không kiểm tra ID đỉnh trong danh sách kề | Truy cập mảng ngoài phạm vi | Validate `0<=v<n` |
| Chuyển DFS sang stack lặp nhưng không lưu trạng thái cạnh kế tiếp | Gán `tout` sai, mất thứ tự sự kiện | Dùng stack frame `(u,nextNeighborIndex)` |
| Dùng `int timer` cho đồ thị có `V` vượt giới hạn kiểu số | Có thể tràn, đảo thứ tự thời gian | Giới hạn `V` khả thi hoặc dùng `long` cho mốc thời gian |
| In mảng `tin/tout` rồi coi là kết quả độc lập thứ tự kề | Các thời điểm thay đổi khi thứ tự kề thay đổi | Chốt thứ tự kề/gốc trong ví dụ và kiểm thử |

## 15. Cách kiểm thử đúng thời điểm và phân loại cạnh

### 15.1. Kiểm tra cấu trúc thời điểm

Sau khi DFS hoàn tất với `n` đỉnh:

1. Mỗi đỉnh có đúng một `tin[u]` và một `tout[u]`.
2. Nếu dùng đồng hồ tăng khi vào/ra từ `0`, tất cả các số **`1..2n` xuất hiện đúng một lần**.
3. `tin[u]<tout[u]` cho mọi `u`.
4. Nếu `parent[v]=u`, phải có `tin[u]<tin[v]<tout[v]<tout[u]`.
5. Với mọi cặp đỉnh phân biệt, các khoảng **lồng hoàn toàn hoặc rời nhau**; không cắt nhau một phần.
6. Số cạnh TREE bằng `n` trừ số gốc DFS.

### 15.2. Kiểm tra cạnh và chu trình

- Tổng số sự kiện cạnh đúng bằng tổng độ dài các danh sách kề, **kể cả cạnh song song**.
- TREE luôn đi tới một đỉnh được phát hiện mới.
- BACK nối một đỉnh tới tổ tiên GRAY tại thời điểm xét; khi DFS hoàn tất, khoảng của tổ tiên bao trùm khoảng của đỉnh nguồn (self-loop được cho phép).
- FORWARD nối tổ tiên thật sự tới hậu duệ, nhưng cạnh này không trực tiếp tạo lần phát hiện đỉnh đích.
- CROSS có các khoảng rời nhau.
- So kết quả **có chu trình** với một thuật toán độc lập: **Kahn topological sort** dựa trên indegree. Nếu Kahn không lấy được đủ `n` đỉnh, đồ thị có chu trình; kết quả phải khớp với việc DFS có BACK.
- Nếu không có chu trình, kiểm tra mọi cạnh `u\to v` có `pos[u]<pos[v]` trong thứ tự topo trả về.

### 15.3. Các ca biên nên thử

```text
Đồ thị rỗng: n=0
Một đỉnh không có cạnh: n=1, adj[0]=[]
Một self-loop: n=1, adj[0]=[0]
Hai đỉnh có cạnh qua lại: 0->1, 1->0
Hai cạnh song song: 0->1, 0->1
Đồ thị dây dài: 0->1->2->...->(n-1)
DAG hình thoi: 0->1, 0->2, 1->3, 2->3
Nhiều thành phần: các đỉnh/nhóm không nối từ gốc 0
Đồ thị dày: nhiều cạnh để kiểm tra đủ TREE/BACK/FORWARD/CROSS
Đồ thị vô hướng có hai cạnh song song: phải dùng edge ID
```

Khi kiểm thử ngẫu nhiên, giữ **seed** và **thứ tự danh sách kề** cố định để có thể tái lập chính xác thời điểm và loại cạnh. Khi thấy sai khác, in cả `tin`, `tout`, `parent`, màu tại lúc xét cạnh và danh sách sự kiện cạnh.

**Lưu ý:** không bắt buộc hai cách cài DFS dùng thứ tự kề khác nhau trả **cùng thời điểm hoặc loại cạnh**. Hãy so các bất biến và kết quả không phụ thuộc thứ tự như **có chu trình hay không**, hoặc cùng một thứ tự vào/cạnh nếu đang đối chiếu chi tiết.

## 16. Bài tập tự luyện

**Bài 1 — Thời gian của dây DFS.** Với `0\to1\to2`, bắt đầu từ `0`, đồng hồ tăng khi vào và ra, hãy tính `tin/tout`.

*Đáp án:* `tin=[1,2,3]`, `tout=[6,5,4]`.

**Bài 2 — Tổ tiên.** Nếu `I(1)=[2,7]` và `I(3)=[4,5]`, đỉnh `1` có là tổ tiên DFS của `3` không?

*Đáp án:* có, vì `2<4<5<7`.

**Bài 3 — Cạnh cây và xuôi.** Đồ thị có `0\to1`, `1\to2`, `0\to2` và xét cạnh `0\to1` trước. Loại của ba cạnh?

*Đáp án:* `0\to1` TREE, `1\to2` TREE, `0\to2` FORWARD.

**Bài 4 — Cạnh ngang.** Trong DAG `0\to1\to3` và `0\to2\to3`, sau khi nhánh `1\to3` hoàn tất, loại cạnh `2\to3` là gì?

*Đáp án:* CROSS, vì `3` BLACK và không nằm trong cây con DFS của `2`.

**Bài 5 — Chu trình.** Khi đang ở `6`, cạnh `6\to4` gặp `4` GRAY. Ta biết chắc điều gì?

*Đáp án:* đây là BACK và có chu trình có hướng: đường TREE từ `4` xuống `6` cộng cạnh `6\to4`.

**Bài 6 — Một đỉnh tự trỏ.** Đồ thị `adj[0]=[0]` có chu trình không? Loại cạnh?

*Đáp án:* có chu trình độ dài `1`; `0\to0` là BACK.

**Bài 7 — Rừng DFS.** Với bảng thời điểm ở phần 6, đỉnh `7` có thuộc cây con DFS của `0` không?

*Đáp án:* không. `I(0)=[1,14]` và `I(7)=[15,16]` rời nhau; `7` là gốc khác.

**Bài 8 — Đảo thứ tự ra.** Với DAG ở phần 8, `finishOrder=[3,1,2,0,4]`. Thứ tự topo là gì?

*Đáp án:* `[4,0,2,1,3]`, vì đảo thứ tự kết thúc và đồ thị không có BACK.

**Bài 9 — Song song trong đồ thị có hướng.** Có hai cạnh `0\to1`, quét liên tiếp theo DFS từ `0`. Cạnh thứ nhất TREE; cạnh thứ hai nhất thiết TREE không?

*Đáp án:* không. Sau cạnh đầu và lời gọi `dfs(1)` trở về, `1` đã BLACK và là hậu duệ `0`, nên cạnh còn lại là FORWARD.

**Bài 10 — Vô hướng và cạnh về cha.** Đồ thị vô hướng chỉ có `0--1`. Khi DFS từ `0` sang `1`, vì sao bản ghi kề từ `1` về `0` không chứng minh chu trình?

*Đáp án:* đó là **cùng cạnh vật lý** đã dùng để phát hiện `1`. Phải bỏ qua nó khi phân loại chu trình vô hướng; với cạnh song song phải phân biệt theo ID.

**Bài 11 — Kiểm tra chu trình độc lập.** Viết một hàm Kahn lấy indegree, liên tục bỏ đỉnh indegree `0` và giảm indegree các đỉnh kề. Khi nào đồ thị có chu trình?

*Đáp án:* nếu số đỉnh lấy ra **nhỏ hơn `n`**, còn một phần đồ thị có chu trình, tương ứng DFS phải có ít nhất một BACK.

**Bài 12 — Vào–ra khi không dùng đệ quy.** Thiết kế một stack frame giữ đỉnh và chỉ số cạnh kề tiếp theo. Khi nào gán `tout[u]`?

*Đáp án:* chỉ khi frame của `u` không còn cạnh kề cần xét, ngay trước khi pop khỏi stack.

**Bài 13 — Phân biệt reachability và tổ tiên.** Nếu có cạnh CROSS `u\to v`, `u` có đường đi tới `v` không? Có bắt buộc `u` là tổ tiên DFS của `v` không?

*Đáp án:* có đường đi trực tiếp `u\to v`, nhưng `u` **không** là tổ tiên DFS của `v` vì khoảng hai đỉnh rời nhau. Điều này cho thấy reachability không đồng nhất với tổ tiên của rừng DFS.

## Ghi nhớ

**DFS với ba màu** và đồng hồ tăng ở **lúc vào lẫn lúc ra** cho cặp `tin[u],tout[u]`. Một đỉnh `u` là tổ tiên DFS của `v` (kể cả chính nó) khi `tin[u]\le tin[v]` và `tout[v]\le tout[u]`. Các khoảng thời gian của hai đỉnh phân biệt **lồng nhau hoàn toàn hoặc rời nhau**.

Khi quét **cạnh có hướng `u\to v`**:

- `v` **WHITE** ⇒ **TREE** (phát hiện đỉnh).
- `v` **GRAY** ⇒ **BACK** (về tổ tiên, có chu trình).
- `v` **BLACK** và `tin[u]<tin[v]` ⇒ **FORWARD**.
- `v` **BLACK** và `tin[u]>tin[v]` ⇒ **CROSS**.

Có **BACK khi và chỉ khi đồ thị có chu trình có hướng**. Nếu không có BACK, đảo danh sách thời điểm ra cho một **thứ tự topo**. Đối với **đồ thị vô hướng**, hai bản ghi kề của cùng cạnh phải được xử lý như **một cạnh vật lý**; với đa đồ thị hãy dùng **ID cạnh** để không bỏ nhầm cạnh song song.

Toàn bộ DFS chạy trong **`O(V+E)`** thời gian. Quan trọng hơn việc nhớ tên bốn loại cạnh là hiểu **màu tại đúng lúc quét**, **cách thời điểm lồng nhau**, và **sự khác nhau giữa cạnh có hướng và vô hướng**.

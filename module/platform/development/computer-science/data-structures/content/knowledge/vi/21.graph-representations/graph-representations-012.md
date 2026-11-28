# Thông tin đánh dấu, cha và khoảng cách khi duyệt đồ thị

## 1. Thuật toán duyệt cần ghi nhớ điều gì?

Giả sử một hệ thống học phần có quan hệ `A → B` khi học phần A dẫn trực tiếp tới B. Bắt đầu ở A, ta muốn biết:

- Những học phần nào **có thể đi tới** bằng cách lần theo các cung?
- Học phần D được phát hiện **từ đỉnh nào**?
- Từ A tới D cần **ít nhất bao nhiêu cung**?
- Có thể **dựng lại một đường đi cụ thể** từ A tới D không?

Chỉ lưu danh sách kề chưa đủ để trả lời các câu hỏi này một cách hiệu quả. Khi chạy **BFS (Breadth-First Search – duyệt theo chiều rộng)** hoặc **DFS (Depth-First Search – duyệt theo chiều sâu)**, ta thường tạo thêm dữ liệu **theo từng đỉnh**:

| Thông tin | Câu hỏi được trả lời |
| --- | --- |
| `visited[v]` hoặc `color[v]` | Đỉnh v đã được phát hiện/xử lý đến đâu? |
| `parent[v]` (cha của v) | Đỉnh nào đã phát hiện v lần đầu? |
| `distance[v]` | BFS đã tìm được đường ít nhất bao nhiêu cạnh từ nguồn tới v? |
| `depth[v]` | v nằm ở độ sâu nào trong **cây duyệt**? |
| `tin[v]`, `tout[v]` | DFS bắt đầu và kết thúc xử lý v lúc nào? |
| `root[v]` hoặc ID thành phần | v thuộc cây duyệt gốc nào, nếu duyệt nhiều lần? |

Các thông tin này là **trạng thái của một lần chạy thuật toán**, không phải thuộc tính bất biến của bản thân đỉnh. Nếu đổi nguồn, thay thứ tự láng giềng hoặc cập nhật cạnh, kết quả có thể thay đổi và thường phải tính lại.

**Trọng tâm bài học:** thiết kế đúng các mảng/từ điển đánh dấu, cha và khoảng cách; hiểu bất biến của BFS/DFS; biết dựng đường đi và xử lý đồ thị có hướng, đỉnh cô lập, khuyên, cạnh song song; phân tích thời gian, bộ nhớ theo `n=|V|` và `m=|E|`.

## 2. Đánh dấu: chưa phát hiện, đã phát hiện và đã hoàn tất

Mục đích cơ bản của `visited` là tránh đưa một đỉnh vào hàng đợi/ngăn xếp lặp đi lặp lại, đặc biệt khi đồ thị có **chu trình**:

```text
A ---> B ---> C
^             |
|_____________|
```

Nếu cứ đi theo các cung mà không nhớ đỉnh đã gặp, thuật toán có thể quay lại A vô hạn.

### Đánh dấu hai trạng thái

Với nhiều bài toán BFS và DFS chỉ cần kiểm tra khả năng tới được:

```text
visited[v] = False  # Chưa phát hiện
visited[v] = True   # Đã phát hiện
```

Đánh dấu `True` **ngay khi phát hiện** đỉnh v lần đầu, không đợi xử lý xong v. Sau đó, nếu một cung khác cũng dẫn tới v, ta không thêm v lần nữa.

### Đánh dấu ba màu trong DFS

Khi cần phân biệt một đỉnh đã xử lý hết các cung chưa, đặc biệt để xét chu trình hay thứ tự hoàn tất, ba màu rất hữu ích:

| Màu | Ý nghĩa |
| --- | --- |
| **WHITE** | Chưa phát hiện |
| **GRAY** | Đã phát hiện, đang nằm trên ngăn xếp lời gọi/khung DFS, chưa xử lý xong |
| **BLACK** | Đã xử lý xong toàn bộ láng giềng trong lần DFS này |

Một lần thăm DFS của một đỉnh đi qua trình tự:

```text
WHITE --phát hiện--> GRAY --kết thúc--> BLACK
```

Trong **đồ thị có hướng**, gặp cung từ một đỉnh đang xử lý tới **đỉnh GRAY** là dấu hiệu của cung ngược (*back edge*) tới một tổ tiên trên ngăn xếp DFS, cho biết có chu trình. Không thể thay quy tắc này bằng “gặp bất kỳ đỉnh đã thăm nào là có chu trình”: cung tới đỉnh BLACK có thể không tạo ra chu trình tương ứng.

**Lưu ý:** `visited` và `color` thường chỉ lưu **một bản ghi cho mỗi đỉnh**, dù đỉnh đó có nhiều cung đi vào.

## 3. Ví dụ xuyên suốt với cung song song, khuyên và đỉnh cô lập

Xét đồ thị có hướng:

```text
V = {A, B, C, D, E, F, G}

out[A] = [B, C, B]     # Hai cung riêng A -> B
out[B] = [D, B]        # Có khuyên B -> B
out[C] = [D, E]
out[D] = [F]
out[E] = [F]
out[F] = []
out[G] = []            # G cô lập
```

Có `n=7` đỉnh, `m=9` cung **khi đếm cả cung song song và khuyên**. Một sơ đồ lược bỏ phần cạnh song song để dễ đọc:

```text
                 B ------> D ------> F
               /            ^        ^
              /             |        |
             A -----> C ----+        |
                      \              |
                       +----> E -----+

G (cô lập); B còn có khuyên B -> B và cung A -> B thứ hai.
```

Bắt đầu BFS từ A, theo thứ tự các mục trong mỗi `out[u]` như đã ghi:

| Thứ tự lấy khỏi queue | Đỉnh xử lý | Những đỉnh mới được phát hiện | Trạng thái đáng chú ý |
| ---: | --- | --- | --- |
| 1 | A | B, C | `parent[B]=A`, `parent[C]=A`, cả hai có `distance=1` |
| 2 | B | D | `parent[D]=B`, `distance[D]=2`; khuyên B→B bị bỏ qua vì B đã được đánh dấu |
| 3 | C | E | D đã được phát hiện; `parent[E]=C`, `distance[E]=2` |
| 4 | D | F | `parent[F]=D`, `distance[F]=3` |
| 5 | E | Không | F đã được phát hiện |
| 6 | F | Không | Không có cung đi ra |

**G không được phát hiện**, vì không có đường có hướng từ A đến G. Cung A→B thứ hai không tạo ra một lần thăm B thứ hai.

Kết quả BFS từ A:

| Đỉnh | Đã tới được? | `parent` | `distance` (số cung) |
| --- | --- | --- | ---: |
| A | Có | `None` (nguồn) | 0 |
| B | Có | A | 1 |
| C | Có | A | 1 |
| D | Có | B | 2 |
| E | Có | C | 2 |
| F | Có | D | 3 |
| G | Không | `None` | Không xác định / `∞` |

Đường đi được chọn tới F là **A→B→D→F**, gồm 3 cung. Một đường đi khác có cùng số bước là **A→C→D→F**. `parent` chỉ lưu **một** phương án được tìm thấy trước theo thứ tự duyệt, không phải tất cả các đường đi.

## 4. Khi nào đánh dấu trong BFS?

BFS dùng **queue (hàng đợi FIFO)**. Mỗi lần lấy `u` ra, thuật toán xét từng cung `u→v`. Nếu `v` chưa được phát hiện, ta đặt trạng thái, ghi cha/khoảng cách và đưa `v` vào queue.

Mã giả:

```text
for v in V:
    visited[v] = false
    parent[v] = NONE
    distance[v] = INFINITY

visited[source] = true
distance[source] = 0
queue.push_back(source)

while queue không rỗng:
    u = queue.pop_front()
    for mỗi cung u -> v:
        if not visited[v]:
            visited[v] = true       # Đánh dấu NGAY khi enqueue
            parent[v] = u
            distance[v] = distance[u] + 1
            queue.push_back(v)
```

**Tại sao phải đánh dấu trước khi đưa vào queue?** Giả sử A→B, A→C, B→D và C→D. Nếu chỉ đánh dấu D sau khi lấy D khỏi queue, cả B và C có thể cùng thêm D vào queue trước khi D được xử lý. Khi đánh dấu ngay lúc **enqueue**, D chỉ được đưa vào queue **một lần**, và `parent[D]` giữ nguyên B trong ví dụ đã chọn.

**Bất biến quan trọng của BFS:** khi một đỉnh `v` được phát hiện lần đầu:

\[
distance[v]=distance[parent[v]]+1.
\]

Các đỉnh được xử lý theo **khoảng cách không giảm** so với nguồn. Vì vậy, với đồ thị không trọng số hoặc khi mỗi cung được coi là **một bước**, giá trị `distance[v]` sau BFS bằng **số cung ít nhất** từ nguồn tới v.

Không cần thêm lại v để “thử đường mới” khi dùng BFS đúng với chi phí mỗi cung bằng 1: lần phát hiện đầu tiên đã có số bước tối ưu. Điều này **không đúng** nếu đang cố tối thiểu hóa **tổng trọng số khác nhau** của các cung.

## 5. Đường đi và cây cha: không phải mọi cung là cung của cây

Trong BFS hoặc DFS, mỗi đỉnh khác gốc được phát hiện từ **đúng một đỉnh cha**. Tập các cung `parent[v]→v` tạo nên **cây duyệt (traversal tree)** từ một nguồn, nếu chỉ xét các đỉnh được phát hiện.

Với đồ thị ở mục 3, cây cha BFS từ A:

```text
        A
       / \
      B   C
      |   |
      D   E
      |
      F
```

Lưu ý: hình cây không vẽ hết cung của đồ thị gốc. Đồ thị vẫn có cung C→D, E→F, khuyên B→B và một cung A→B song song. Những cung đó **không tạo thêm cha** cho các đỉnh đã được phát hiện.

### Bất biến của `parent`

1. `parent[source]=None` vì nguồn không được phát hiện từ đỉnh nào khác.
2. Mọi đỉnh đã tới được và **khác nguồn** có đúng một cha là đỉnh đã tới được trước nó.
3. Với mỗi `v` khác nguồn, tồn tại **một cung thực** `parent[v]→v` trong đồ thị có hướng; với vô hướng là một cạnh nối hai đầu mút.
4. Theo chuỗi cha phải **tiến về nguồn** sau hữu hạn bước, không được tạo chu trình trong cây cha.
5. Mỗi đỉnh được gán cha **một lần ở thời điểm phát hiện đầu tiên** trong BFS thông thường.

`parent` thường lưu **ID đỉnh cha**, không phải một bản sao toàn bộ bản ghi đỉnh. Với **đa đồ thị**, nếu cần biết chính xác **cung nào** đã được chọn khi nhiều cung song song cùng nối u→v, phải lưu thêm `parent_edge[v]=edge_id`. Chỉ ghi `parent[v]=u` không đủ để tái hiện ID cung, vé tàu hoặc trọng số cụ thể của hành trình.

## 6. Truy vết đường đi từ bảng cha

Sau BFS, để dựng đường từ nguồn `s` tới đích `t`:

1. Kiểm tra `t` **có thể tới được** từ s không.
2. Bắt đầu tại `t`, đọc `parent[t]` rồi tiếp tục đọc cha cho tới khi gặp `s`.
3. Đảo ngược dãy đỉnh thu được.

Ví dụ:

```text
parent[F] = D
parent[D] = B
parent[B] = A
parent[A] = None

Truy vết ngược: F, D, B, A
Đảo lại:       A, B, D, F
```

**Phân biệt hai trường hợp có `parent=None`:** một đỉnh có thể là **nguồn của cây duyệt**, hoặc **chưa tới được**. Chỉ nhìn `parent=None` không đủ phân biệt. Cần thêm `visited` hoặc `distance`:

- `distance[source]=0`.
- `distance[t]=∞` (hoặc `None` theo quy ước phần mềm) nếu t không tới được.

Nếu t không tới được, API nên trả **`None` / “không có đường”**, không tạo nhầm một đường chỉ gồm t. Nếu `s=t`, đường đi `[s]` dài 0 cung là hợp lệ theo quy ước thông thường.

Chi phí truy vết là **`O(L+1)`**, với `L` là số cung trong đường được dựng, vì cần đọc các ID trong chuỗi cha rồi đảo kết quả. Bộ nhớ kết quả cũng là **`O(L+1)`**.

## 7. BFS: khoảng cách là số cạnh, không phải tổng trọng số

`distance[v]` trong BFS chuẩn thường có nghĩa:

\[
distance[v]=\min\{\text{số cung trên một đường từ s đến v}\}.
\]

Nó **không tự là** khoảng cách hình học (km), thời gian (phút) hoặc tổng trọng số.

Ví dụ có hướng:

```text
S ---> T          chi phí 100
 \
  \---> X ---> T   mỗi cung chi phí 1
```

BFS coi mỗi cung là một bước:

- Đường `S→T` dài **1 bước**, nên `distance[T]=1`.
- Đường `S→X→T` dài **2 bước**, nhưng có **tổng trọng số 2**, nhỏ hơn 100.

Vì vậy, BFS đúng cho **đường đi ít cạnh nhất**, không đúng cho mục tiêu “tổng chi phí nhỏ nhất” khi trọng số khác nhau.

| Bài toán | Hướng thuật toán thích hợp |
| --- | --- |
| Mỗi cung được tính là một bước / cùng chi phí | BFS |
| Trọng số chỉ là 0 hoặc 1 | **0–1 BFS** với deque |
| Trọng số không âm tổng quát | **Dijkstra** với cấu trúc ưu tiên phù hợp |
| Có trọng số âm, cần phát hiện chu trình âm tới được | **Bellman–Ford** |

DFS cũng không tự tìm số bước ngắn nhất. Khi cần khoảng cách ngắn nhất theo cung, dùng BFS thay vì đặt `distance` theo độ sâu DFS rồi coi là đáp án tối ưu.

## 8. DFS: cha, độ sâu và thời điểm phát hiện/kết thúc

**DFS** đi sâu theo một nhánh trước khi quay lại xử lý những nhánh khác. Cấu trúc điều khiển có thể là **ngăn xếp lời gọi** (đệ quy) hoặc **stack các khung duyệt**.

Các trường thường dùng:

- `color[v]` để theo dõi WHITE/GRAY/BLACK;
- `parent[v]` để ghi đỉnh đã phát hiện v đầu tiên;
- `depth[v]` để ghi **độ sâu của v trong cây DFS**;
- `tin[v]` và `tout[v]` để đánh dấu **thời điểm phát hiện và kết thúc**.

Nếu đặt một bộ đếm thời gian tăng 1 khi vào và tăng 1 khi rời mỗi đỉnh, ta có:

\[
tin[v]<tout[v]\quad\text{với mọi đỉnh đã duyệt}.
\]

Nếu v là hậu duệ thực sự của u trong **cùng cây DFS**:

\[
tin[u]<tin[v]<tout[v]<tout[u].
\]

Tính chất khoảng thời gian lồng nhau giúp nhận biết quan hệ tổ tiên trong **cây DFS**. Nhưng `depth[v]` chỉ là **số cạnh của đường cha DFS từ gốc đến v**, không phải khoảng cách ít cung nhất trong đồ thị gốc.

### Phản ví dụ: DFS phát hiện đường dài hơn BFS

```text
S -> A -> C -> T
 \
  +----> B ----> T
```

Giả sử DFS từ S xét A trước B:

- DFS có thể phát hiện T theo `S→A→C→T`, **độ sâu 3**.
- BFS tìm `S→B→T`, chỉ **2 cung**.

Nếu bài toán chỉ hỏi **khả năng tới được** hoặc cần cây duyệt DFS, kết quả DFS vẫn hợp lệ. Nếu hỏi **độ dài đường ngắn nhất theo số cung**, độ sâu DFS là đáp án sai.

### Cung về đỉnh đã thăm có phải chu trình?

Trong đồ thị **có hướng**, DFS gặp cung tới một đỉnh **GRAY** trên ngăn xếp hiện hành cho biết có chu trình có hướng. Cung tới đỉnh **BLACK** không thể được coi tự động là dấu hiệu chu trình.

Trong **đồ thị vô hướng**, cạnh trở lại cha thường được bỏ qua khi phát hiện chu trình. Tuy nhiên, với **đa đồ thị**, hai cạnh song song u—v có thể tạo chu trình gồm hai cạnh khác ID. Cần ghi và so sánh **`parent_edge_id`** để chỉ bỏ qua đúng cạnh đã đi xuống, không bỏ qua tất cả cạnh nối về đỉnh cha. Khuyên là chu trình độ dài 1 theo quy ước đồ thị cho phép khuyên.

## 9. Python: BFS với bảng đánh dấu, cha và khoảng cách

Ví dụ sau dùng một `dict` từ **ID đỉnh** sang danh sách các **đích đi ra**. Danh sách có thể chứa **cung song song** và **khuyên**. Mã vẫn giữ những đỉnh chưa có cung như G.

Quy ước:

- `distance[v]=None` khi v **chưa tới được**, còn số nguyên không âm khi đã tới được.
- `parent[v]=None` cho nguồn và đỉnh chưa tới được; dùng `distance` để phân biệt.
- `visited` là một `set`, đánh dấu ngay khi **đưa vào queue**.
- `order` lưu thứ tự **lấy khỏi queue**, không phải tất cả các cung đã quét.

```python
from collections import deque


def kiem_tra_danh_sach_ke(g):
    # Mọi đỉnh đích cần tồn tại thành một khóa, kể cả khi không có cung ra.
    for u, ds in g.items():
        for v in ds:
            if v not in g:
                raise ValueError(f"Cung {u}->{v} có đỉnh đích không tồn tại")


def bfs(g, source):
    if source not in g:
        raise KeyError(f"Đỉnh nguồn không tồn tại: {source}")
    kiem_tra_danh_sach_ke(g)

    parent = {v: None for v in g}
    distance = {v: None for v in g}
    visited = {source}
    queue = deque([source])
    order = []
    distance[source] = 0

    while queue:
        u = queue.popleft()
        order.append(u)
        for v in g[u]:
            if v not in visited:
                visited.add(v)            # Đánh dấu ngay lúc phát hiện
                parent[v] = u
                distance[v] = distance[u] + 1
                queue.append(v)

    return {
        "visited": visited,
        "parent": parent,
        "distance": distance,
        "order": order,
    }


def truy_vet_duong(parent, distance, source, target):
    if source not in parent or target not in parent:
        raise KeyError("Nguồn hoặc đích không tồn tại")
    if distance[target] is None:
        return None   # Không có đường từ source đến target

    path = []
    v = target
    while v is not None:
        path.append(v)
        if v == source:
            path.reverse()
            return path
        v = parent[v]

    # Đường cha phải về đúng source nếu parent/distance thuộc cùng BFS.
    raise ValueError("Bảng cha hoặc nguồn truy vết không nhất quán")


g = {
    "A": ["B", "C", "B"],  # Hai cung song song A -> B
    "B": ["D", "B"],       # Khuyên B -> B
    "C": ["D", "E"],
    "D": ["F"],
    "E": ["F"],
    "F": [],
    "G": [],               # Đỉnh cô lập
}

result = bfs(g, "A")

print(result["order"])  # ['A', 'B', 'C', 'D', 'E', 'F']
print(result["distance"])
# {'A': 0, 'B': 1, 'C': 1, 'D': 2, 'E': 2, 'F': 3, 'G': None}
print(result["parent"])
# {'A': None, 'B': 'A', 'C': 'A', 'D': 'B',
#  'E': 'C', 'F': 'D', 'G': None}

print(truy_vet_duong(result["parent"], result["distance"],
                    "A", "F"))  # ['A', 'B', 'D', 'F']
print(truy_vet_duong(result["parent"], result["distance"],
                    "A", "G"))  # None: không tới được
print(truy_vet_duong(result["parent"], result["distance"],
                    "A", "A"))  # ['A']: đường dài 0

print(len(result["visited"]))  # 6, không phải 7
```

**Giải thích kết quả:** BFS chỉ thêm mỗi đỉnh một lần vào queue. Cung song song A→B không làm B có hai cha; khuyên B→B không làm lặp vô hạn; G vẫn xuất hiện trong `parent` và `distance` với giá trị chưa tới được.

**Giới hạn API:** `truy_vet_duong` yêu cầu bảng `parent` và `distance` được tạo từ **cùng lần BFS, cùng nguồn**. Nếu lấy `parent` của lần chạy khác hoặc đã thay đổi cạnh sau khi BFS, không được xem đường truy vết là bằng chứng cho trạng thái mới. Hàm này cũng không phân biệt **ID của hai cung song song**, vì ví dụ chỉ lưu ID đỉnh kề; nếu cần đường theo ID cung, hãy mở rộng bảng trạng thái thành `parent_edge`.

## 10. Python: DFS lặp với ba màu, cha và thời điểm

DFS đệ quy rất dễ viết, nhưng với đường đi rất sâu có thể vượt giới hạn ngăn xếp lời gọi. Ví dụ sau dùng **stack các khung `(đỉnh, iterator)`** để duy trì đúng trạng thái đang xử lý, phù hợp với việc ghi `tin`, `tout` và chuyển màu GRAY → BLACK.

Hàm duyệt **mọi đỉnh**, kể cả những đỉnh chưa tới được từ đỉnh đầu tiên, nên tạo **rừng DFS (DFS forest)**. Trên đồ thị có hướng, các cây của rừng phụ thuộc vào thứ tự bắt đầu và **không nhất thiết là các thành phần liên thông mạnh hoặc yếu**.

```python
def dfs_toan_bo(g):
    kiem_tra_danh_sach_ke(g)

    color = {v: "WHITE" for v in g}
    parent = {v: None for v in g}
    depth = {v: None for v in g}
    tin, tout = {}, {}
    preorder, postorder, roots = [], [], []
    clock = 0

    for start in g:
        if color[start] != "WHITE":
            continue

        roots.append(start)
        color[start] = "GRAY"
        depth[start] = 0
        clock += 1
        tin[start] = clock
        preorder.append(start)
        stack = [(start, iter(g[start]))]

        while stack:
            u, neighbors = stack[-1]
            try:
                v = next(neighbors)
            except StopIteration:
                stack.pop()
                color[u] = "BLACK"
                clock += 1
                tout[u] = clock
                postorder.append(u)
                continue

            if color[v] == "WHITE":
                parent[v] = u
                depth[v] = depth[u] + 1
                color[v] = "GRAY"
                clock += 1
                tin[v] = clock
                preorder.append(v)
                stack.append((v, iter(g[v])))
            # Với GRAY/BLACK: không tạo thêm một cha cho v.

    return {
        "color": color,
        "parent": parent,
        "depth": depth,
        "tin": tin,
        "tout": tout,
        "preorder": preorder,
        "postorder": postorder,
        "roots": roots,
    }


dfs = dfs_toan_bo(g)  # Dùng đúng g từ ví dụ BFS phía trên
print(dfs["preorder"])  # ['A', 'B', 'D', 'F', 'C', 'E', 'G']
print(dfs["roots"])     # ['A', 'G']
print(dfs["parent"]["G"])  # None: G là gốc cây DFS thứ hai
print(dfs["depth"]["F"])   # 3: độ sâu trong cây DFS
print(dfs["tin"]["A"] < dfs["tin"]["B"]
      < dfs["tout"]["B"] < dfs["tout"]["A"])  # True
print(all(c == "BLACK" for c in dfs["color"].values()))  # True
```

**Vì sao giữ iterator trong stack?** Khi quay lại u sau khi duyệt sâu từ v, DFS phải tiếp tục từ **mục kề còn lại** của u, không quét đi quét lại từ đầu. Nhờ đó, mỗi mục kề được xét một lần trong lần duyệt, cho cận `O(n+m)` với danh sách kề.

`tin/tout` ở đây là **thời điểm logic** do thuật toán tự tăng, không phải đồng hồ thực hoặc timestamp hệ điều hành. Giá trị cụ thể tùy thứ tự đỉnh và thứ tự láng giềng; bất biến quan hệ tổ tiên trong cây DFS mới là điều có ý nghĩa tổng quát.

## 11. Duyệt nhiều nguồn và đồ thị không liên thông

### BFS từ một nguồn

BFS từ `s` chỉ đánh dấu **các đỉnh có thể tới được từ s** theo chiều cung. Những đỉnh không tới được giữ `distance=None` hoặc `∞`, tùy quy ước.

### BFS nhiều nguồn (*multi-source BFS*)

Nếu cần khoảng cách ít cung nhất từ **bất kỳ nguồn nào** trong một tập `S`, khởi tạo:

```text
for s in S:
    visited[s] = true
    distance[s] = 0
    parent[s] = NONE
    queue.push_back(s)
```

Sau đó chạy vòng BFS bình thường. Kết quả `distance[v]` là **số cung ít nhất từ một nguồn thuộc S** đến v, không phải khoảng cách riêng từ từng nguồn. Nếu cần biết v thuộc nguồn nào, lưu thêm `origin[v]` và gán `origin[v]=origin[parent[v]]` khi phát hiện v.

Khi có nhiều nguồn cùng đạt khoảng cách tối thiểu, nguồn được chọn có thể phụ thuộc **thứ tự đưa vào queue** và thứ tự duyệt láng giềng.

### Duyệt để bao phủ toàn bộ tập V

Một vòng lặp bắt đầu BFS/DFS tại **mỗi đỉnh chưa được đánh dấu** sẽ tạo một **rừng duyệt**. Với đồ thị vô hướng, mỗi cây tương ứng một **thành phần liên thông**, nếu mọi cạnh vô hướng được lưu kề đúng hai phía.

Với đồ thị **có hướng**, một lần duyệt từ u chỉ đi theo chiều cung, nên các cây BFS/DFS lập bằng cách quét toàn bộ V **không phải phép phân chia thành phần liên thông mạnh**. Muốn SCC cần thuật toán chuyên biệt như Kosaraju hoặc Tarjan; muốn thành phần liên thông yếu phải xét liên kết không phân biệt chiều.

**Chú ý nghĩa của `distance`:** nếu đặt `distance[root]=0` cho mỗi gốc mới trong rừng BFS, thì `distance[v]` là số cung ít nhất từ **gốc của cây mà v được gán**, không phải khoảng cách từ một nguồn ban đầu duy nhất. Nếu bài toán cần khoảng cách từ s, không được khởi động lại BFS cho đỉnh khác rồi dùng lẫn chung một cột khoảng cách mà không ghi `root`.

## 12. Độ phức tạp và cách chọn cấu trúc lưu trạng thái

Giả sử đồ thị được biểu diễn bằng **danh sách kề**, mỗi phép đánh dấu/tra bảng ID đủ rẻ, queue dùng `deque` hoặc cấu trúc FIFO với thao tác hằng số:

| Công việc | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| Khởi tạo `visited,parent,distance` cho n đỉnh | `O(n)` | `O(n)` |
| BFS từ một nguồn, sau khi khởi tạo | `O(n+m)` cận trên | `O(n)` cho trạng thái và queue |
| DFS toàn bộ đồ thị | `O(n+m)` | `O(n)` cho màu, cha, thời điểm, stack |
| Truy vết đường dài L cung từ bảng cha | `O(L+1)` | `O(L+1)` cho đường trả về |
| Dựng cây cha từ `parent` của n đỉnh | `O(n)` | `O(n)` nếu tạo danh sách cạnh cây |

Ở đồ thị có hướng, mỗi cung nằm trong một danh sách nguồn; với đồ thị vô hướng, mỗi cạnh thường xuất hiện ở hai đầu, nên số mục quét vẫn là `O(m)`. Khuyên và cung/cạnh song song có thể làm tăng `m` và số mục kề được xét, **nhưng không làm tăng số đỉnh được đánh dấu quá n lần**.

**Nếu chỉ BFS từ s:** về phần duyệt, có thể mô tả chính xác hơn là `O(n_R+m_R)`, với `n_R` là số đỉnh tới được và `m_R` là số mục kề thực sự được quét từ chúng, chưa kể chi phí khởi tạo toàn bộ n đỉnh nếu có. Nếu dùng một bộ `dict` chỉ tạo entry cho các đỉnh được phát hiện, bộ nhớ trạng thái có thể phụ thuộc số đỉnh tới được thay vì tất cả n.

**Nếu dùng ma trận kề đặc:** mỗi đỉnh được xử lý có thể phải quét **n ô** để tìm láng giềng. BFS/DFS bao phủ toàn bộ đồ thị theo cách thông thường có chi phí **`O(n²)`**, dù thông tin `visited,parent,distance` vẫn chỉ tốn **`O(n)`**.

### Mảng, dictionary hay set?

- Khi đỉnh đánh số `0..n-1`: mảng `visited[n]`, `parent[n]`, `distance[n]` thuận tiện, tra theo chỉ số `O(1)`.
- Khi đỉnh có ID chuỗi: `dict` và `set` như ví dụ Python dễ dùng; tra cứu có chi phí **`O(1)` kỳ vọng** với các giả định băm thông thường, chưa kể chi phí băm khóa rất dài.
- Nếu cần trả kết quả ổn định qua các lần chạy, nên dùng một **thứ tự duyệt đỉnh/láng giềng được quy định**, không dựa vào thứ tự ngẫu nhiên hoặc không được bảo đảm của `set`.

Các mảng trạng thái nên được cấp cho **mỗi lần duyệt**, không gắn vĩnh viễn với các bản ghi đỉnh trừ khi ứng dụng quản lý **phiên bản kết quả** và quy trình đặt lại dữ liệu rõ ràng.

## 13. Thay đổi đồ thị sau khi duyệt: kết quả nào còn đúng?

Giả sử BFS từ A đã lưu `parent[D]=B`, `distance[D]=2`. Nếu sau đó **xóa cung B→D**, bảng cha có thể không còn biểu diễn một đường hợp lệ. Nếu thêm một **cung trực tiếp A→D**, `distance[D]=2` tuy vẫn là độ dài một đường cũ nhưng **không còn là khoảng cách ngắn nhất**; giá trị mới có thể là 1.

Do đó, cần phân biệt:

- **Trạng thái duyệt:** `visited`, `color`, queue/stack hiện hành.
- **Kết quả của snapshot đồ thị:** `parent`, `distance`, `tin`, `tout`, thứ tự duyệt.
- **Dữ liệu đồ thị hiện tại:** tập đỉnh/cung sau các thao tác thêm/xóa.

Khi đồ thị thay đổi, những kết quả đã lưu nên được xem là gắn với **phiên bản dữ liệu trước đó**. Cách đơn giản và an toàn là chạy lại BFS/DFS nếu cần kết quả chính xác trên phiên bản mới. Có những thuật toán động cập nhật kết quả từng phần, nhưng phức tạp hơn việc dùng lại bảng cũ mà không kiểm tra.

Nếu hệ thống có nhiều luồng hoặc giao dịch cập nhật, một lần BFS/DFS cần được thực hiện trên **một snapshot nhất quán** hoặc dưới cơ chế đồng bộ phù hợp. Nếu vừa duyệt vừa đọc những danh sách kề đang bị thay đổi dở, ngay cả bất biến “cha tương ứng cung có thật” cũng có thể không được bảo đảm.

## 14. Những nhầm lẫn thường gặp

1. **Đánh dấu khi lấy khỏi queue.** Có thể enqueue một đỉnh nhiều lần nếu nhiều cung dẫn tới nó; đánh dấu ngay khi phát hiện.
2. **Coi `parent[source]=None` và `parent[unreachable]=None` là cùng trạng thái.** Phải dùng thêm `visited` hoặc `distance` để phân biệt.
3. **Coi `distance` BFS là tổng trọng số.** BFS chuẩn đếm số cung khi mọi cung được tính một bước.
4. **Coi `depth` DFS là khoảng cách ngắn nhất.** DFS có thể khám phá một đường dài hơn đường ngắn nhất.
5. **Ghi đè cha của đỉnh đã phát hiện.** Có thể phá bất biến cây cha hoặc làm sai khoảng cách.
6. **Bỏ mất đỉnh cô lập vì không xuất hiện trong cạnh.** Đỉnh đó vẫn có trạng thái chưa tới được và phải thuộc tập V.
7. **Coi cung song song là nhiều đỉnh mới.** Một đỉnh vẫn được đánh dấu một lần; nếu cần đường theo cung, lưu thêm `parent_edge_id`.
8. **Không xử lý khuyên.** Không có đánh dấu, khuyên có thể gây lặp; có đánh dấu đúng thì không tạo thêm đỉnh mới.
9. **Gặp đỉnh đã thăm trong DFS là kết luận có chu trình có hướng.** Cần phân biệt GRAY và BLACK.
10. **Bỏ qua mọi cạnh về đỉnh cha trong đa đồ thị vô hướng.** Có thể bỏ sót chu trình từ hai cạnh song song; cần so sánh ID cạnh cha.
11. **Dùng rừng BFS của đồ thị có hướng để nhận diện SCC.** Tập đỉnh tới được từ một gốc không đồng nghĩa với thành phần liên thông mạnh.
12. **Dựng đường truy vết từ bảng cha của phiên bản đồ thị khác.** Đường có thể không còn hợp lệ hoặc không tối ưu.
13. **Không cố định thứ tự láng giềng nhưng yêu cầu đúng một cây cha duy nhất.** Có thể có nhiều cây BFS/DFS hợp lệ và nhiều đường ngắn nhất.
14. **Cho rằng thông tin trạng thái luôn lưu trong chính đồ thị.** Nhiều bài toán tốt hơn khi giữ riêng trạng thái theo lần chạy, tránh nhiễm kết quả từ nguồn khác.

## 15. Tự kiểm tra

**Câu 1.** Tại sao BFS đánh dấu đỉnh `v` ngay lúc thêm v vào queue, thay vì đợi lúc lấy v ra?

**Đáp án:** Để khi một cung khác cũng dẫn tới v, thuật toán không enqueue v lần hai. Điều đó giữ chi phí duyệt, `parent[v]` và `distance[v]` nhất quán với lần phát hiện đầu tiên.

**Câu 2.** Một BFS từ A có `parent[A]=None` và `parent[G]=None`. Hai giá trị này có nghĩa hoàn toàn giống nhau không?

**Đáp án:** Không. A là **nguồn** có khoảng cách 0; G có thể là **đỉnh không tới được**, có `distance[G]=None` hoặc `∞`. Phải xét thêm trạng thái tới được.

**Câu 3.** Với `parent[F]=D`, `parent[D]=B`, `parent[B]=A`, `parent[A]=None`, đường từ A tới F là gì?

**Đáp án:** Đi ngược F–D–B–A rồi đảo lại, nhận **A→B→D→F**, gồm ba cung.

**Câu 4.** Trong đồ thị ở mục 3, BFS từ A trả `distance[D]=2`. Vì sao cung C→D không tự đổi cha của D thành C?

**Đáp án:** D đã được phát hiện trước qua B→D ở khoảng cách 2; khi xét C→D, D đã được đánh dấu. Cả hai đường đều có hai bước, nhưng BFS chỉ giữ cha đầu tiên theo thứ tự duyệt.

**Câu 5.** Trong đồ thị có hai cung song song A→B và một khuyên B→B, BFS từ A có thể thêm B vào queue mấy lần nếu đánh dấu đúng?

**Đáp án:** **Một lần**. B được đánh dấu từ cung A→B đầu tiên; cung song song và khuyên không thêm B lần nữa.

**Câu 6.** Một đường S→T có một cung trọng số 100; đường S→X→T có hai cung trọng số 1. BFS chuẩn chọn khoảng cách nào, và vì sao không trả tổng chi phí tối thiểu?

**Đáp án:** BFS trả **1 bước** cho T qua cung trực tiếp S→T. Tổng trọng số tối thiểu là 2 qua S→X→T; BFS không được thiết kế để tối ưu trọng số khác nhau.

**Câu 7.** Nếu DFS đi theo S→A→C→T trước khi thử S→B→T, độ sâu DFS của T có thể là mấy, còn khoảng cách ít cung nhất từ S tới T là mấy?

**Đáp án:** Độ sâu DFS có thể là **3**, trong khi khoảng cách ít cung nhất là **2**.

**Câu 8.** Ba màu WHITE, GRAY, BLACK lần lượt thể hiện điều gì trong DFS?

**Đáp án:** Chưa phát hiện; đã phát hiện nhưng chưa xử lý hết, còn trên stack; đã xử lý xong toàn bộ láng giềng.

**Câu 9.** Một cạnh u—v trong đa đồ thị vô hướng có hai bản sao song song với ID e0 và e1. Vì sao phát hiện chu trình bằng DFS nên lưu `parent_edge_id`?

**Đáp án:** Để bỏ qua đúng cạnh e0 đã đi từ u tới v nhưng vẫn nhận ra e1 là một cạnh khác nối v về u; nếu bỏ qua **mọi** cạnh tới cha u, có thể bỏ sót chu trình hai cạnh.

**Câu 10.** BFS toàn bộ đồ thị bằng danh sách kề có chi phí thời gian và bộ nhớ phụ nào?

**Đáp án:** **`O(n+m)` thời gian** và **`O(n)` bộ nhớ phụ** cho đánh dấu, cha, khoảng cách và queue, với giả định thao tác ID hiệu quả.

**Câu 11.** Trong BFS nhiều nguồn, khi khởi tạo cả `s1` và `s2` có `distance=0`, giá trị `distance[v]` cuối cùng thể hiện điều gì?

**Đáp án:** Số cung ít nhất từ **một nguồn bất kỳ** trong `{s1,s2}` tới v, không phải khoảng cách riêng từ từng nguồn. Có thể lưu `origin[v]` để biết nguồn được chọn.

**Câu 12.** Duyệt mọi đỉnh chưa thăm bằng DFS trong đồ thị có hướng có tự tạo ra các thành phần liên thông mạnh không?

**Đáp án:** **Không**. Các cây của rừng DFS phụ thuộc thứ tự bắt đầu và chiều cung; cần thuật toán SCC như Kosaraju/Tarjan để xác định thành phần liên thông mạnh.

**Câu 13.** Khi thêm cung mới A→D sau một lần BFS cũ đã có `distance[D]=2`, có thể dùng nguyên khoảng cách cũ như kết quả hiện hành không?

**Đáp án:** **Không nên**. Cung trực tiếp có thể làm khoảng cách mới còn 1. Cần tính lại hoặc có cơ chế cập nhật kết quả phù hợp với phiên bản đồ thị mới.

**Ghi nhớ:** **Đánh dấu** giúp một đỉnh chỉ được phát hiện một lần trong BFS/DFS; **cha** lưu quan hệ phát hiện để tạo cây duyệt và truy vết đường; **khoảng cách BFS** là **số cung ít nhất** khi mỗi cung được tính một bước. **Độ sâu DFS** không phải khoảng cách ngắn nhất, còn `tin/tout` và màu WHITE/GRAY/BLACK mô tả trình tự xử lý sâu. Hãy phân biệt **nguồn với đỉnh không tới được**, lưu **edge ID của cung cha** khi cần phân biệt cạnh song song, duyệt mọi đỉnh nếu muốn bao phủ cả đỉnh cô lập, và gắn kết quả trạng thái với **đúng lần chạy, đúng nguồn và đúng phiên bản đồ thị**.

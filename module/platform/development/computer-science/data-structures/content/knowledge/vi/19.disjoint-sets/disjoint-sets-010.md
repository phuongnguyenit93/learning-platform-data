# Ứng dụng thành phần liên thông tăng dần và phát hiện chu trình

Một hệ thống mạng bắt đầu với nhiều máy tính chưa kết nối. Các liên kết lần lượt được thêm vào: hôm nay nối máy 0 với máy 1, sau đó nối máy 1 với máy 2, rồi một liên kết mới lại nối máy 2 về máy 0. Hệ thống cần trả lời **hai câu hỏi ngay sau mỗi lần thêm cạnh**: *hai máy bất kỳ đã liên thông chưa?* và *cạnh vừa thêm có tạo ra chu trình không?*

Nếu dùng **Disjoint Set Union (DSU, Union–Find)**, ta quản lý mỗi **thành phần liên thông** bằng một tập hợp rời nhau. Mỗi cạnh mới có thể **hợp hai thành phần** hoặc **đi vào bên trong một thành phần đã tồn tại**. Trường hợp thứ hai chính là tín hiệu phát hiện chu trình trong đồ thị vô hướng, theo mô hình cạnh được chọn.

Bài này thuộc chương **Tập hợp rời nhau** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mục tiêu là hiểu ứng dụng DSU vào **liên thông tăng dần (incremental connectivity)** và **phát hiện chu trình (cycle detection)**, tự cài đặt bộ xử lý cạnh trực tuyến, kiểm chứng các bất biến, phân tích thời gian/bộ nhớ, và nhận diện trường hợp DSU **không** giải quyết được.

## 1. Đặt bài toán chính xác: chỉ thêm cạnh

Cho đồ thị vô hướng:

\[
G_t=(V,E_t),
\]

trong đó tập đỉnh V đã biết trước và `E_t` là tập hoặc đa tập các cạnh đã được thêm tính đến thời điểm t. Trong mô hình **incremental**, ta chỉ có:

\[
E_0\subseteq E_1\subseteq E_2\subseteq\cdots.
\]

Không có thao tác xóa cạnh. Mỗi sự kiện là:

```text
add_edge(u, v)
```

và có thể kèm các truy vấn:

```text
connected(u, v)      // Có đường đi vô hướng từ u tới v?
component_size(u)    // Thành phần chứa u có bao nhiêu đỉnh?
component_count()    // Hiện có bao nhiêu thành phần?
creates_cycle(u, v)  // Cạnh mới (u,v) có đóng một chu trình?
```

**Thành phần liên thông** là tập đỉnh mà mỗi cặp trong tập đều có đường đi nối nhau. Các thành phần tạo thành một **phân hoạch** của V: không giao nhau và bao phủ toàn bộ đỉnh.

Ví dụ với sáu đỉnh:

```text
V = {0,1,2,3,4,5}

Thêm (0,1) và (1,2):
  {0,1,2}  {3}  {4}  {5}

Thêm (3,4):
  {0,1,2}  {3,4}  {5}

Thêm (2,3):
  {0,1,2,3,4}  {5}
```

Cạnh `(2,3)` hợp **hai thành phần**, không chỉ thay đổi quan hệ của riêng hai đỉnh 2 và 3.

### Tính chất đơn điệu

Vì chỉ thêm cạnh:

- Hai đỉnh **đã liên thông** sẽ không trở thành không liên thông.
- Số thành phần **không thể tăng**.
- Khi đồ thị đã có chu trình, việc thêm cạnh không thể làm chu trình cũ biến mất.
- Một cạnh mới chỉ có thể giảm số thành phần **0 hoặc 1**.

Đây là lý do liên thông tăng dần rất phù hợp với DSU. Nếu có xóa cạnh, những tính chất đơn điệu không còn đúng và ta cần thuật toán khác.

## 2. Phân biệt đồ thị đầu vào và rừng cha của DSU

DSU có mảng:

```text
parent[x] = cha của phần tử x
parent[root] = root
```

Mỗi cây cha tương ứng một thành phần liên thông của đồ thị đã xử lý. Hàm `find(x)` đi tới gốc của cây; hai đỉnh liên thông nếu có chung gốc:

\[
u\leftrightarrow v
\quad\Longleftrightarrow\quad
\operatorname{find}(u)=\operatorname{find}(v).
\]

**Đừng nhầm hai cấu trúc khác nhau:**

1. **Cạnh đồ thị `(u,v)`:** liên kết thực sự được thêm, dùng để định nghĩa đường đi và chu trình.
2. **Liên kết cha `parent[x]`:** cạnh **nội bộ** của biểu diễn DSU, có thể xuất hiện hoặc biến mất khi `union` hoặc nén đường đi.

Ví dụ, ta thêm cạnh thực:

```text
(0,1), (1,2), (2,3)
```

DSU có thể lưu:

```text
parent = [0,0,0,0]

      0
    / | \
   1  2  3
```

Nhưng đồ thị thật là đường:

```text
0 — 1 — 2 — 3
```

**Không hề có cạnh thật `(0,3)`** trong ví dụ. Vì thế, DSU trả lời **có đường đi hay không**, nhưng không tự trả về các cạnh trên đường đi đó.

## 3. Từ nhóm đơn tới thành phần liên thông

Giả sử có n đỉnh với chỉ số `0..n-1`. Khởi tạo:

```text
parent[x] = x
size[x] = 1
components = n
```

Ban đầu chưa có cạnh nên mọi đỉnh là một thành phần riêng.

Khi thêm cạnh `(u,v)`:

1. Tìm `ru=find(u)` và `rv=find(v)`.
2. Nếu `ru!=rv`, hai đầu thuộc **hai thành phần khác nhau**.
3. Hợp hai gốc để chúng trở thành **một thành phần**.
4. Nếu `ru==rv`, hai đầu **đã liên thông**, nên không cần hợp nhóm.

Hàm `find` và `union` có thể được triển khai bằng mảng cha với **union by size/rank** và **path compression** để tránh đường cha quá dài.

### Bất biến liên thông

Sau khi xử lý một tiền tố bất kỳ của luồng cạnh, DSU phải thỏa:

\[
\forall u,v\in V:\quad
\mathrm{find}(u)=\mathrm{find}(v)
\iff
u,v\text{ liên thông trong đồ thị hiện tại}.
\]

Đây là **bất biến ứng dụng**, bổ sung cho các bất biến rừng cha:

- Mỗi cha nằm trong miền chỉ số.
- Mỗi cây có đúng một gốc tự trỏ.
- Không có chu trình cha dài từ hai nút trở lên.
- Các cây không giao nhau và bao phủ toàn bộ đỉnh.
- `size[root]` đúng bằng số đỉnh trong thành phần của gốc ấy.

## 4. Vì sao kiểm tra cùng gốc phát hiện chu trình?

Trong đồ thị **vô hướng**, trước khi thêm cạnh `(u,v)`, xét hai trường hợp.

**Trường hợp A — Chưa có đường đi từ u đến v:**

```text
Thành phần A        Thành phần B

  u —— ...            ... —— v
```

Thêm cạnh `(u,v)` nối hai thành phần thành một. Cạnh mới không thể tạo chu trình vì **trước đó không có đường đi** giữa hai đầu của nó.

**Trường hợp B — Đã có đường đi từ u đến v:**

```text
u —— a —— b —— v
 \             /
  \—— cạnh mới/
```

Đường đi cũ từ u tới v kết hợp với cạnh mới `(u,v)` tạo một **đường khép kín**. Nếu `u!=v` và đường cũ chọn không lặp đỉnh, đó là một chu trình theo mô hình vô hướng tương ứng.

Do đó:

\[
\boxed{
\text{Cạnh mới }(u,v)\text{ tạo chu trình}
\iff
\mathrm{find}(u)=\mathrm{find}(v)
}
\]

**Điều kiện của kết luận:** đây là bài toán **thêm cạnh vô hướng** với quy ước cạnh mới thực sự được chấp nhận vào đồ thị, kể cả trường hợp đồ thị đa cạnh; cách xử lý khuyên và cạnh song song cần được nói rõ.

### Tại sao phải kiểm tra trước khi `union`?

Nếu gọi `union(u,v)` trước, cả hai đầu sẽ cùng nhóm **sau** thao tác kể cả khi ban đầu chúng thuộc hai thành phần khác nhau. Lúc đó kiểm tra lại `find(u)==find(v)` luôn đúng, và ta sẽ **báo chu trình sai cho cả cạnh nối hai thành phần**.

Thứ tự đúng:

```text
ru = find(u)
rv = find(v)

if ru == rv:
    // Cạnh mới đóng chu trình trong đồ thị vô hướng.
else:
    // Cạnh mới nối hai thành phần.
    union_roots(ru, rv)
```

## 5. Giả mã xử lý cạnh trực tuyến

Với đồ thị vô hướng có n đỉnh:

```text
initialize(n):
    for v from 0 to n-1:
        parent[v] = v
        size[v] = 1

    components = n
    cycle_edges = 0

find(x):
    root = x

    while parent[root] != root:
        root = parent[root]

    while parent[x] != x:
        old_parent = parent[x]
        parent[x] = root
        x = old_parent

    return root

add_edge(u, v):
    ru = find(u)
    rv = find(v)

    if ru == rv:
        cycle_edges += 1
        return "CREATES_CYCLE"

    if size[ru] < size[rv]:
        swap(ru, rv)

    parent[rv] = ru
    size[ru] += size[rv]
    components -= 1

    return "MERGED"
```

Hàm `add_edge` trên kết hợp **kiểm tra chu trình** với **hợp nhóm** trong một bước. Nó không cần lưu tất cả cạnh nếu chỉ cần kết quả liên thông và biết **cạnh vừa thêm** có tạo chu trình hay không.

### Kết quả của hàm cần được hiểu đúng

- `"MERGED"`: cạnh vừa thêm nối **hai thành phần khác nhau**; số thành phần giảm 1.
- `"CREATES_CYCLE"`: hai đầu **đã liên thông** trước cạnh mới; số thành phần không đổi.
- `cycle_edges` đếm **những sự kiện thêm cạnh bị từ chối khi xây rừng không chu trình**, không phải tổng số chu trình đơn khác nhau trong đồ thị.

Nếu hệ thống từ chối cạnh gây chu trình và không thực sự lưu nó trong đồ thị, thì bộ đếm cạnh của **đồ thị được chấp nhận** sẽ khác bộ đếm **cạnh đã được yêu cầu thêm**. Phải chọn một ý nghĩa nhất quán trước khi đặt tên biến.

## 6. Rừng cạnh được chấp nhận và rừng cha DSU là hai rừng khác nhau

Khi duyệt luồng cạnh, ta có thể phân loại:

- **Cạnh được chấp nhận:** hai đầu ở hai thành phần khác nhau; ta có thể đưa cạnh này vào một **rừng khung**.
- **Cạnh bị từ chối khi xây rừng:** hai đầu đã liên thông; nếu thêm vào đồ thị gốc, cạnh này tạo chu trình.

Tập cạnh được chấp nhận **không có chu trình** và kết nối đúng mỗi thành phần. Nó tạo một **spanning forest** của đồ thị đã xử lý.

Ví dụ:

```text
Cạnh vào: (0,1), (1,2), (0,2)

Chấp nhận:
  (0,1), (1,2)

Từ chối khi xây rừng:
  (0,2)
```

Rừng cạnh được chấp nhận:

```text
0 — 1 — 2
```

Rừng cha DSU có thể là:

```text
      0
     / \
    1   2
```

Dù cùng xác định các thành phần, **hai loại cạnh không nhất thiết trùng nhau**. Muốn khôi phục một chu trình cụ thể, hãy giữ **rừng cạnh được chấp nhận** hoặc đồ thị thật, không dựa trực tiếp vào `parent`.

## 7. Truy vết 10 cạnh trên 7 đỉnh

Xét đồ thị **vô hướng đa cạnh**, cho phép **khuyên** `(u,u)` và những cạnh trùng cặp đầu mút. Mỗi lần `add_edge` được coi là thêm một **cạnh mới vào đa tập cạnh**.

Bắt đầu với bảy đỉnh:

```text
V = {0,1,2,3,4,5,6}

parent     = [0,1,2,3,4,5,6]
size       = [1,1,1,1,1,1,1]
components = 7
```

Luồng cạnh theo thứ tự:

```text
1.  (0,1)
2.  (1,2)
3.  (3,4)
4.  (2,0)
5.  (4,5)
6.  (2,3)
7.  (5,1)
8.  (6,6)
9.  (6,2)
10. (0,6)
```

Dùng union by size và full path compression; khi hai nhóm bằng kích thước, giữ gốc của đối số đầu sau khi tìm hai gốc.

| Bước | Cạnh mới | Hai đầu đã cùng nhóm trước cạnh? | Kết quả | Số thành phần | Cạnh tạo chu trình tích lũy |
|---:|---|---|---|---:|---:|
| 0 | Chưa có cạnh | — | 7 nhóm đơn | 7 | 0 |
| 1 | `(0,1)` | Không | Hợp `{0}` và `{1}` | 6 | 0 |
| 2 | `(1,2)` | Không | Hợp thành `{0,1,2}` | 5 | 0 |
| 3 | `(3,4)` | Không | Hợp thành `{3,4}` | 4 | 0 |
| 4 | `(2,0)` | Có | **Tạo chu trình** `0-1-2-0` | 4 | 1 |
| 5 | `(4,5)` | Không | Hợp thành `{3,4,5}` | 3 | 1 |
| 6 | `(2,3)` | Không | Hợp thành `{0,1,2,3,4,5}` | 2 | 1 |
| 7 | `(5,1)` | Có | **Tạo chu trình** trong nhóm lớn | 2 | 2 |
| 8 | `(6,6)` | Có | **Khuyên**, tạo chu trình độ dài 1 | 2 | 3 |
| 9 | `(6,2)` | Không | Hợp `{6}` với nhóm lớn | 1 | 3 |
| 10 | `(0,6)` | Có | **Tạo chu trình** | 1 | 4 |

### Những bước quan trọng

**Bước 4:** trước khi thêm `(2,0)`, đồ thị đã có đường `2-1-0`. Cạnh mới khép đường `2-1-0-2`. Không có phép hợp nhóm mới, nên vẫn còn bốn thành phần.

**Bước 6:** nhóm `{0,1,2}` và nhóm `{3,4,5}` đều có kích thước 3. Cạnh `(2,3)` nối hai nhóm này; nếu tie-break giữ gốc nhóm đầu, gốc 3 thành con của gốc 0. Không tạo chu trình.

**Bước 7:** hai đầu 5 và 1 giờ đã cùng một thành phần; cạnh `(5,1)` tạo một chu trình vì đã có đường cũ nối chúng.

**Bước 8:** `(6,6)` là **khuyên tự nối (self-loop)**. Với đồ thị đa cạnh cho phép khuyên, đây là chu trình độ dài 1; nó không làm giảm số thành phần.

**Bước 9:** `(6,2)` nối thành phần `{6}` vào nhóm sáu đỉnh, làm cả đồ thị liên thông.

**Bước 10:** `(0,6)` có hai đầu đã liên thông, vì thế tạo thêm một chu trình theo nghĩa phát hiện cạnh dư.

## 8. Quan sát mảng `parent` trong cùng ví dụ

Cùng quy tắc union by size và full path compression, ta có các trạng thái:

```text
Bước 0:  [0,1,2,3,4,5,6]

(0,1):   [0,0,2,3,4,5,6]
(1,2):   [0,0,0,3,4,5,6]
(3,4):   [0,0,0,3,3,5,6]
(2,0):   [0,0,0,3,3,5,6]   // Cùng gốc, không hợp
(4,5):   [0,0,0,3,3,3,6]
(2,3):   [0,0,0,0,3,3,6]
(5,1):   [0,0,0,0,3,0,6]   // find(5) nén 5 → 0
(6,6):   [0,0,0,0,3,0,6]   // Khuyên, không hợp
(6,2):   [0,0,0,0,3,0,0]
(0,6):   [0,0,0,0,3,0,0]   // Cùng gốc
```

Ở cuối, `parent[4]=3` nhưng `parent[3]=0`, nên:

```text
find(4) = 0
find(6) = 0
same(4,6) = true
component_size(4) = 7
components = 1
```

**Không nên suy một cạnh `(4,3)` hay `(5,0)` của `parent` là cạnh đồ thị thực mới được thêm ở cùng bước.** Các cập nhật cha có thể do nén đường hoặc nối gốc, chỉ phục vụ quản lý đại diện.

Khi so sánh hai cài đặt DSU khác nhau, bảng mảng cha có thể khác do tie-break, path halving, path splitting hoặc union by rank. **Phân hoạch và kết quả phát hiện cạnh tạo chu trình** mới là những gì cần nhất quán.

## 9. Đếm thành phần, cạnh rừng và cạnh dư

Gọi:

- `n=|V|` là số đỉnh, gồm cả đỉnh cô lập.
- `m=|E|` là số **cạnh thực sự đã thêm**, với số lần xuất hiện được tính riêng nếu là đa đồ thị.
- `c` là số thành phần liên thông hiện tại.
- `a` là số cạnh được nhận vào rừng khung.
- `r` là số cạnh bị nhận diện là tạo chu trình khi xử lý theo thứ tự.

### Rừng khung luôn có `n-c` cạnh

Ban đầu có n thành phần và chưa có cạnh rừng. Mỗi cạnh được nhận vào rừng **giảm số thành phần đúng một**. Do đó:

\[
a=n-c.
\]

Các cạnh khác là những sự kiện có hai đầu đã liên thông:

\[
r=m-a.
\]

Thay `a=n-c`:

\[
\boxed{r=m-n+c}.
\]

Đối với ví dụ ở trên:

\[
m=10,\quad n=7,\quad c=1.
\]

Suy ra:

\[
r=10-7+1=4.
\]

Đúng bằng các sự kiện `(2,0)`, `(5,1)`, `(6,6)` và `(0,6)`.

### Đây là số gì?

Đại lượng `m-n+c` được gọi là **cycle rank**, **cyclomatic number** hoặc **số chu trình độc lập** của đồ thị vô hướng (xét cấu trúc cạnh trên `GF(2)`), với quy ước đồ thị đa cạnh phù hợp. Nó bằng số cạnh cần bỏ từ đồ thị hiện tại để còn một rừng khung.

**Không đồng nghĩa với số lượng tất cả chu trình đơn.** Một đồ thị có nhiều chu trình đơn khác nhau, nhưng không gian chu trình có số chiều chỉ bằng `m-n+c`.

### Vì sao số cạnh dư bằng cycle rank?

Các cạnh được nhận vào rừng tạo một rừng khung gồm `n-c` cạnh. Mỗi cạnh còn lại đóng một chu trình cơ bản khi thêm vào rừng. Những chu trình cơ bản này độc lập theo nghĩa đại số; nhưng các cách ghép của chúng có thể tạo thêm những chu trình khác.

**Lưu ý:** nếu hệ thống **từ chối** và không thực sự thêm cạnh tạo chu trình, m của **đồ thị được chấp nhận** không bao gồm chúng. Công thức vẫn đúng cho đồ thị được chấp nhận, khi ấy r sẽ bằng 0 vì chính đồ thị được giữ là một rừng.

## 10. Đồ thị đơn, đa đồ thị, khuyên và cạnh lặp

Một thuật toán chỉ có thể đúng khi đã quy định loại dữ liệu đầu vào.

### Đồ thị đơn vô hướng

Đồ thị đơn thường:

- Không cho phép khuyên `(u,u)`.
- Không có hai cạnh cùng cặp đỉnh.
- Cạnh `(u,v)` tương đương `(v,u)`.

Nếu luồng đầu vào có cạnh lặp, chương trình phải **lọc hoặc từ chối** theo hợp đồng. Chỉ gọi DSU và phát hiện cùng gốc sẽ không phân biệt “cạnh bị lặp, không có thêm cạnh mới” với “cạnh mới được thêm gây chu trình”.

### Đa đồ thị vô hướng

Đa đồ thị cho phép nhiều cạnh giữa cùng hai đầu và có thể cho phép khuyên.

- Khuyên `(u,u)` tạo **chu trình độ dài 1**.
- Hai cạnh song song khác nhau giữa u và v tạo **chu trình độ dài 2** trong nghĩa đồ thị đa cạnh.
- Mỗi lần thêm một cạnh song song mới được coi là một sự kiện cạnh độc lập, kể cả nếu cặp đầu mút đã xuất hiện trước đó.

Ví dụ:

```text
add_edge(0,1)   // Hai thành phần khác nhau: không có chu trình.
add_edge(0,1)   // Cạnh song song mới: có chu trình độ dài 2.
```

Nếu bài toán chỉ xét **chu trình đơn có ít nhất 3 đỉnh trong đồ thị đơn**, khuyên và cạnh song song phải được xử lý riêng hoặc loại bỏ trước.

### Khi cần khử cạnh lặp

Dùng một tập khóa chuẩn hóa:

```text
key(u, v) = (min(u,v), max(u,v))
```

Với đồ thị đơn, chỉ xử lý cạnh có `key` chưa xuất hiện; nếu key đã có, tùy giao diện có thể báo `"DUPLICATE_IGNORED"` và **không tăng m**. Chi phí và bộ nhớ của tập khử trùng lặp cần tính riêng, thường là `O(m)` bộ nhớ cho m cạnh phân biệt; hash set có truy cập kỳ vọng nhanh nhưng không mặc định worst-case hằng số.

## 11. Cài đặt Python: bộ xử lý liên thông tăng dần có đếm cạnh

Mã bên dưới sử dụng:

- Mảng `parent` biểu diễn rừng cha.
- **Union by size** giữ gốc nhóm lớn hơn.
- **Full path compression** trong `find`.
- `edges_in_component[root]` là **số cạnh thực tế đã thêm** nằm trong thành phần có gốc root.
- `redundant_edges` đếm các sự kiện cạnh có hai đầu **đã liên thông trước khi thêm**, gồm khuyên/cạnh song song theo mô hình đa đồ thị.

Mã **chấp nhận đồ thị vô hướng đa cạnh**, nên **mỗi lần `add_edge` tạo một cạnh mới**, kể cả khi cùng cặp đầu mút.

```python
class IncrementalUndirectedGraph:
    def __init__(self, n: int):
        if not isinstance(n, int) or isinstance(n, bool):
            raise TypeError("n phải là số nguyên")
        if n < 0:
            raise ValueError("n phải không âm")

        self.parent = list(range(n))
        self.size = [1] * n
        self.edges_in_component = [0] * n

        self.components = n
        self.edges_seen = 0
        self.redundant_edges = 0

    def _check(self, x: int) -> None:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError("ID đỉnh phải là số nguyên")
        if not 0 <= x < len(self.parent):
            raise IndexError("Đỉnh nằm ngoài miền")

    def find(self, x: int) -> int:
        self._check(x)

        # Lượt 1: tìm gốc.
        root = x
        while self.parent[root] != root:
            root = self.parent[root]

        # Lượt 2: nén toàn bộ đường tới gốc.
        while self.parent[x] != x:
            old_parent = self.parent[x]
            self.parent[x] = root
            x = old_parent

        return root

    def same(self, u: int, v: int) -> bool:
        return self.find(u) == self.find(v)

    def add_edge(self, u: int, v: int) -> dict[str, int | bool]:
        ru = self.find(u)
        rv = self.find(v)

        # Đỉnh đã hợp lệ: ghi nhận một cạnh mới.
        self.edges_seen += 1

        if ru == rv:
            # Cạnh nội bộ vẫn tăng số cạnh thật.
            self.edges_in_component[ru] += 1
            self.redundant_edges += 1

            return {
                "merged": False,
                "creates_cycle": True,
                "components": self.components,
            }

        # Cạnh nối hai thành phần; chọn gốc cây lớn.
        if self.size[ru] < self.size[rv]:
            ru, rv = rv, ru

        self.parent[rv] = ru
        self.size[ru] += self.size[rv]

        # Cộng cạnh của hai nhóm cũ và cạnh vừa thêm.
        self.edges_in_component[ru] += (
            self.edges_in_component[rv] + 1
        )
        self.components -= 1

        return {
            "merged": True,
            "creates_cycle": False,
            "components": self.components,
        }

    def component_stats(self, x: int) -> dict[str, int | bool]:
        root = self.find(x)
        vertex_count = self.size[root]
        edge_count = self.edges_in_component[root]

        # Thành phần là đồ thị vô hướng liên thông.
        cycle_rank = edge_count - vertex_count + 1

        return {
            "root": root,
            "vertices": vertex_count,
            "edges": edge_count,
            "cycle_rank": cycle_rank,
            "has_cycle": cycle_rank > 0,
        }

    def cycle_rank(self) -> int:
        return self.edges_seen - len(self.parent) + self.components


stream = [
    (0, 1), (1, 2), (3, 4), (2, 0), (4, 5),
    (2, 3), (5, 1), (6, 6), (6, 2), (0, 6),
]

graph = IncrementalUndirectedGraph(7)
cycle_events = []

for step, (u, v) in enumerate(stream, start=1):
    event = graph.add_edge(u, v)
    if event["creates_cycle"]:
        cycle_events.append(step)

assert cycle_events == [4, 7, 8, 10]
assert graph.components == 1
assert graph.edges_seen == 10
assert graph.redundant_edges == 4
assert graph.cycle_rank() == 4
assert graph.same(4, 6)
assert graph.component_stats(4) == {
    "root": 0,
    "vertices": 7,
    "edges": 10,
    "cycle_rank": 4,
    "has_cycle": True,
}

# Một lần thêm cạnh nữa giữa hai đỉnh đang liên thông
# tiếp tục tăng số cạnh và số sự kiện tạo chu trình.
extra = graph.add_edge(0, 1)
assert extra["creates_cycle"] is True
assert graph.cycle_rank() == 5

print(cycle_events)  # [4, 7, 8, 10]
```

### Đọc mã đúng theo hợp đồng

- `find` trả **gốc hiện tại**; nén đường đi không đổi thành viên nhóm hoặc số cạnh thực.
- `add_edge` tìm **cả hai gốc trước khi sửa `parent`**.
- Nếu hai gốc giống nhau, không cập nhật `size` hoặc số thành phần, nhưng vẫn tăng **số cạnh thực** và **số cạnh dư**.
- Nếu khác gốc, hợp theo size, cộng số đỉnh, cộng số cạnh cũ của cả hai thành phần **và cộng 1 cho cạnh mới**.
- `component_stats(x)` luôn tìm gốc trước khi đọc metadata, không đọc `size[x]` hoặc `edges_in_component[x]` tại một nút tùy ý.
- `cycle_rank()` dùng công thức toàn đồ thị `m-n+c`. Nó không quét danh sách cạnh.

Mã ví dụ xử lý **một luồng tuần tự**. Trong môi trường nhiều luồng, `find` có nén và `add_edge` đều có thể sửa chung `parent`, `size` và các bộ đếm; cần đồng bộ hoặc cấu trúc concurrent chuyên dụng.

## 12. Tại sao metadata số cạnh ở gốc cập nhật như vậy?

Tại mỗi gốc hiện tại r, ta duy trì:

\[
\mathrm{size}[r]=|V_r|,
\qquad
\mathrm{edgeCount}[r]=|E_r|,
\]

trong đó `V_r` là tập đỉnh của thành phần, còn `E_r` gồm **toàn bộ cạnh đã thêm có hai đầu trong `V_r`**.

### Cạnh nối hai thành phần khác nhau

Giả sử hai thành phần trước đó có:

```text
Nhóm A: 4 đỉnh, 4 cạnh
Nhóm B: 3 đỉnh, 2 cạnh
```

Thêm một cạnh nối A với B:

```text
Nhóm mới:
  vertices = 4 + 3 = 7
  edges    = 4 + 2 + 1 = 7
```

Cộng **1** vì cạnh nối hai nhóm là một cạnh thật mới.

### Cạnh nằm trong cùng thành phần

Nếu một thành phần đang có 7 đỉnh và 7 cạnh, thêm cạnh giữa hai đỉnh đã liên thông:

```text
vertices = 7 (không đổi)
edges    = 8 (tăng 1)
```

Từ `e-v+1=1` trước đó thành `e-v+1=2` sau đó. Một sự kiện cạnh nội bộ tăng **số chu trình độc lập thêm một**, nhưng không làm tăng số thành phần.

### Điều kiện để công thức hoạt động

Mọi cạnh đã được thêm phải được tính **đúng một lần**, với đúng quy ước cạnh trùng và khuyên. Khi dùng đồ thị đơn và lọc cạnh trùng, `edgeCount` phải **không tăng** đối với cạnh bị bỏ qua. Khi dùng đa đồ thị, mỗi bản sao cạnh được tính riêng.

## 13. Cách xác định một thành phần hiện tại có chu trình

Vì mỗi thành phần liên thông có `v` đỉnh và tối thiểu `v-1` cạnh để liên thông:

\[
e\ge v-1.
\]

Hơn nữa, thành phần **không có chu trình** khi và chỉ khi:

\[
e=v-1.
\]

Một thành phần **có ít nhất một chu trình** khi:

\[
\boxed{e\ge v.}
\]

Với cách đếm khuyên và cạnh song song của đa đồ thị, điều này vẫn đúng theo khái niệm chu trình của đa đồ thị.

Do đó trong mã Python:

```text
has_cycle = (
    edges_in_component[root] >= size[root]
)
```

Cách viết dùng `cycle_rank=edge_count-vertex_count+1` cũng tương đương:

```text
has_cycle = cycle_rank > 0
```

### Trường hợp gốc đơn có khuyên

```text
V_r = {6}
E_r = {(6,6)}
```

Khi đó `v=1`, `e=1`, `cycle_rank=1−1+1=1`. Thành phần có chu trình độ dài 1 dù vẫn có đúng một đỉnh.

### Đừng dùng số gốc của DSU thay cho số cạnh

`components` chỉ đếm thành phần. Nó không cho biết một thành phần có bao nhiêu **cạnh dư** nếu không lưu thêm số cạnh thực hoặc số sự kiện đã xử lý. Hai đồ thị có cùng phân hoạch nhưng có thể khác số chu trình:

```text
G1: các cạnh (0,1), (1,2)
G2: các cạnh (0,1), (1,2), (2,0)

Cùng một thành phần {0,1,2};
G1 không chu trình; G2 có chu trình.
```

## 14. Thuật toán có chứng minh đúng: quy nạp theo luồng cạnh

Ta chứng minh hai kết quả:

1. DSU luôn biểu diễn đúng **thành phần liên thông** của đồ thị đã xử lý.
2. Cờ `creates_cycle` cho cạnh mới là đúng trong mô hình đồ thị vô hướng đa cạnh đã chọn.

### Bước cơ sở

Khi chưa có cạnh, mỗi đỉnh là một thành phần đơn. Mảng `parent[v]=v` tạo đúng n nhóm đơn. Không có chu trình; số cạnh bằng 0.

### Giả thuyết quy nạp

Giả sử sau k cạnh đầu, hai đỉnh có cùng gốc DSU **khi và chỉ khi** chúng liên thông trong đồ thị `G_k`.

### Thêm cạnh thứ k+1 là `(u,v)`

**Nếu `find(u)!=find(v)`:** theo giả thuyết, u và v ở hai thành phần khác nhau nên **không có đường đi** giữa chúng trước cạnh mới. Cạnh nối hai thành phần ấy thành một, và không tạo chu trình. DSU nối hai gốc cũng hợp đúng hai thành phần, giữ bất biến.

**Nếu `find(u)==find(v)`:** đã có đường đi giữa u và v trước cạnh mới. Cạnh mới kết hợp với đường cũ tạo chu trình (hoặc là khuyên khi u=v). Không thành phần nào bị hợp thêm. DSU giữ nguyên phân hoạch.

Vậy cả phát hiện chu trình và duy trì liên thông đều đúng sau k+1 cạnh. Theo quy nạp, chúng đúng sau mọi tiền tố của luồng.

### Chứng minh bộ đếm thành phần

Chỉ khi hai gốc khác nhau mới giảm `components` một. Lúc ấy số thành phần thật cũng giảm đúng một. Trường hợp cùng gốc không giảm. Bắt đầu từ n, nên số đếm luôn đúng.

### Chứng minh số cạnh dư

Mỗi sự kiện cạnh có hai đầu khác thành phần được chấp nhận vào rừng, làm c giảm một. Những cạnh còn lại tăng bộ đếm `redundant_edges` một. Vì số cạnh rừng là `n-c`, sau m cạnh:

\[
\mathrm{redundantEdges}=m-n+c.
\]

Bộ đếm này phản ánh số chu trình **độc lập**, không đếm toàn bộ chu trình đơn khác nhau.

## 15. Khôi phục một chu trình cụ thể khi cần

DSU **chỉ phát hiện có chu trình**, không tự cung cấp đường đi hoặc danh sách cạnh trong chu trình.

Nếu cần trả một **chứng cứ chu trình**, có thể giữ thêm **danh sách kề của những cạnh đã được nhận vào rừng khung**.

Khi `add_edge(u,v)` báo đã liên thông:

1. Tìm đường đi **duy nhất** từ u tới v trong rừng cạnh đã được nhận.
2. Thêm cạnh mới `(u,v)` để khép đường thành chu trình.
3. Báo các đỉnh hoặc các cạnh trên chu trình.

### Ví dụ

Ta đã nhận:

```text
(0,1), (1,2)
```

Rừng khung là:

```text
0 — 1 — 2
```

Khi cạnh `(2,0)` tới, tìm được đường đi cũ `2→1→0`. Thêm cạnh `(2,0)`, ta có chu trình:

```text
2 → 1 → 0 → 2
```

### Python: lấy đường đi trong rừng cạnh được nhận

```python
from collections import deque


def forest_path(
    forest: list[list[int]], start: int, target: int
) -> list[int]:
    queue = deque([start])
    previous: dict[int, int | None] = {start: None}

    while queue:
        u = queue.popleft()
        if u == target:
            break

        for v in forest[u]:
            if v not in previous:
                previous[v] = u
                queue.append(v)

    if target not in previous:
        raise ValueError("Hai đỉnh chưa liên thông trong rừng")

    path = []
    current: int | None = target

    while current is not None:
        path.append(current)
        current = previous[current]

    path.reverse()
    return path


graph = IncrementalUndirectedGraph(3)
forest = [[] for _ in range(3)]

for u, v in [(0, 1), (1, 2)]:
    event = graph.add_edge(u, v)
    assert event["merged"]

    # Chỉ lưu cạnh thực đã được nhận, không lưu parent.
    forest[u].append(v)
    forest[v].append(u)

event = graph.add_edge(2, 0)
assert event["creates_cycle"]

old_path = forest_path(forest, 2, 0)
cycle_vertices = old_path + [2]

assert cycle_vertices == [2, 1, 0, 2]
print(cycle_vertices)
```

### Chi phí của chứng cứ chu trình

Tìm đường đi bằng BFS/DFS trong một rừng có n đỉnh mất **`O(n)` worst-case** nếu tìm từ đầu và không có chỉ mục đường đi phụ trợ. Việc trả về k đỉnh của chu trình cũng mất ít nhất **`Ω(k)` thời gian để xuất đầu ra**.

Vì vậy nếu yêu cầu **liệt kê chu trình cụ thể**, không được nói toàn bộ yêu cầu chỉ mất `O(α(n))`; chặn đó chỉ dành cho thành phần DSU phát hiện cùng gốc.

**Với khuyên:** `u=v`, chu trình có thể biểu diễn bằng `[u,u]`. **Với hai cạnh song song:** một chu trình đa đồ thị có thể dài hai cạnh, cần phân biệt **ID của hai cạnh thực** nếu xuất danh sách cạnh, tránh coi chúng là một cạnh duy nhất.

## 16. Cài đặt C++17: phân loại cạnh và duy trì thống kê

Phiên bản sau cài DSU trực tuyến với union by size, **path halving**, số nhóm, tổng số cạnh và số cạnh dư. Nó thích hợp khi đỉnh được đánh số `0..n-1`.

```cpp
#include <algorithm>
#include <cstddef>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <utility>
#include <vector>

class IncrementalGraph {
public:
    struct AddResult {
        bool merged;
        bool creates_cycle;
        std::size_t components;
    };

    explicit IncrementalGraph(std::size_t n)
        : parent_(n), size_(n, 1),
          edges_in_component_(n, 0),
          components_(n), edges_seen_(0),
          redundant_edges_(0) {
        std::iota(parent_.begin(), parent_.end(),
                  std::size_t{0});
    }

    std::size_t find(std::size_t x) {
        if (x >= parent_.size()) {
            throw std::out_of_range("Vertex outside graph");
        }

        // Path halving.
        while (parent_[x] != x) {
            parent_[x] = parent_[parent_[x]];
            x = parent_[x];
        }
        return x;
    }

    AddResult add_edge(std::size_t u, std::size_t v) {
        std::size_t ru = find(u);
        std::size_t rv = find(v);

        ++edges_seen_;

        if (ru == rv) {
            ++edges_in_component_[ru];
            ++redundant_edges_;
            return {false, true, components_};
        }

        if (size_[ru] < size_[rv]) {
            std::swap(ru, rv);
        }

        parent_[rv] = ru;
        size_[ru] += size_[rv];
        edges_in_component_[ru] +=
            edges_in_component_[rv] + 1;
        --components_;

        return {true, false, components_};
    }

    bool connected(std::size_t u, std::size_t v) {
        return find(u) == find(v);
    }

    std::size_t component_size(std::size_t x) {
        return size_[find(x)];
    }

    std::size_t component_edges(std::size_t x) {
        return edges_in_component_[find(x)];
    }

    bool component_has_cycle(std::size_t x) {
        std::size_t r = find(x);
        return edges_in_component_[r] >= size_[r];
    }

    std::size_t component_count() const {
        return components_;
    }

    std::size_t redundant_edges() const {
        return redundant_edges_;
    }

    std::size_t cycle_rank() const {
        // Cạnh đã thêm >= số cạnh rừng (n - components).
        // Tránh phép trừ unsigned âm ở kết quả trung gian.
        return edges_seen_ - (parent_.size() - components_);
    }

private:
    std::vector<std::size_t> parent_;
    std::vector<std::size_t> size_;
    std::vector<std::size_t> edges_in_component_;
    std::size_t components_;
    std::size_t edges_seen_;
    std::size_t redundant_edges_;
};

int main() {
    IncrementalGraph graph(7);

    const std::vector<std::pair<std::size_t, std::size_t>>
        stream = {
            {0,1}, {1,2}, {3,4}, {2,0}, {4,5},
            {2,3}, {5,1}, {6,6}, {6,2}, {0,6}
        };

    std::size_t cycle_events = 0;
    for (const auto& edge : stream) {
        auto result = graph.add_edge(edge.first, edge.second);
        if (result.creates_cycle) ++cycle_events;
    }

    std::cout << graph.connected(4, 6) << '\n'; // 1
    std::cout << graph.component_size(4) << '\n'; // 7
    std::cout << graph.component_edges(4) << '\n'; // 10
    std::cout << graph.component_count() << '\n'; // 1
    std::cout << graph.redundant_edges() << '\n';  // 4
    std::cout << graph.cycle_rank() << '\n';       // 4
    std::cout << cycle_events << '\n';             // 4
}
```

### Điểm cần chú ý trong C++

- `find` là thao tác **có thể ghi** vì path halving sửa `parent_`; không phải `const`.
- `add_edge` kiểm tra cả hai chỉ số qua `find` **trước khi** tăng `edges_seen_`. Nếu chỉ số ngoài phạm vi, ngoại lệ xảy ra và bộ đếm cạnh không đổi.
- `std::size_t` là kiểu không dấu. Nếu ID âm bị chuyển kiểu, phải bảo đảm kiểm tra `x>=n` từ chối giá trị không hợp lệ.
- Phép tính `edges_seen_ - parent_.size() + components_` được hiểu với các bộ đếm hợp lệ của đồ thị đang quản lý. Trong mã sản xuất, cần thiết kế chống tràn `std::size_t` nếu xử lý một số lượng cạnh cực lớn.
- Ví dụ không hỗ trợ xóa cạnh, không có cập nhật đồng thời và không lưu danh sách các cạnh thật.

## 17. Các truy vấn trực tuyến có thể trả ngay sau mỗi cạnh

Với DSU còn giữ `size[root]` và `components`, ứng dụng có thể hỏi:

| Truy vấn | Cách trả lời | Thông tin cần duy trì |
|---|---|---|
| Hai đỉnh đã liên thông? | `find(u)==find(v)` | `parent` |
| Thành phần của u có bao nhiêu đỉnh? | `size[find(u)]` | `size` |
| Cả đồ thị có bao nhiêu thành phần? | `components` | Biến đếm nhóm |
| Cạnh vừa thêm có tạo chu trình? | Hai gốc **trước khi hợp** có bằng nhau? | `find` trước `union` |
| Đã có ít nhất một chu trình? | `redundant_edges>0` | Đếm sự kiện cạnh dư |
| Thành phần của u có chu trình? | `edgeCount[root]>=size[root]` | Bộ đếm cạnh mỗi nhóm |
| Bao nhiêu chu trình độc lập toàn đồ thị? | `m-n+c` | Tổng cạnh, số đỉnh, số thành phần |
| Cần liệt kê một chu trình cụ thể? | Tìm đường trong rừng cạnh được nhận | Lưu cạnh thật và BFS/DFS |

Hầu hết những truy vấn đầu có thể xử lý với chi phí rất nhỏ trên DSU tối ưu. Nhưng truy vấn **liệt kê đường đi hoặc chu trình** đòi thêm dữ liệu và có chi phí tương xứng với đường đi được trả.

### Đọc `find(u)` nhiều lần có vấn đề gì?

Path compression có thể cập nhật `parent` ngay trong quá trình truy vấn, dù không thay đổi nhóm logic. Vì thế:

- Trong chương trình **đơn luồng**, điều này bình thường và có lợi cho truy vấn sau.
- Trong chương trình **đa luồng**, phải đồng bộ hoặc dùng một triển khai concurrent phù hợp.
- Trong hệ thống lưu lịch sử, mảng `parent` ở thời điểm mới **không đủ** để tự trả lời trạng thái liên thông ở mọi thời điểm cũ.

## 18. Độ phức tạp thời gian và bộ nhớ

Đặt:

- `n=|V|`: số đỉnh đã khởi tạo.
- `m`: số sự kiện thêm cạnh.
- `q`: số truy vấn liên thông hoặc metadata.
- `α(n)`: một hàm nghịch đảo Ackermann theo quy ước phân tích Union–Find.

### Khi dùng union by size/rank và path compression

Khởi tạo mảng `parent`, `size`, `edges_in_component` tốn **`Θ(n)` thời gian và `Θ(n)` bộ nhớ**.

Mỗi lần `add_edge` cần tối đa hai lần `find` và số hằng phép cập nhật khi đã biết hai gốc. Mỗi truy vấn `connected` hoặc `component_size` cũng cần một hoặc hai lần tìm gốc.

Tổng chi phí DSU cho một chuỗi m lần thêm cạnh và q truy vấn là một dạng chặn quen dùng:

\[
\boxed{
O\bigl(n+(m+q)\alpha(n)\bigr).
}
\]

Đây là **chặn khấu hao** theo chuỗi thao tác, không phải `O(1)` worst-case chắc chắn cho từng lần `find`. Một lời gọi tìm gốc riêng lẻ vẫn có thể đi qua `O(log n)` cạnh trước khi nén.

### Nếu chỉ union by size, không nén

Chiều cao cây được chặn `O(log n)`, nên `find` và `union` có chi phí **`O(log n)` worst-case** cho một lời gọi.

### Nếu nối gốc tùy ý, không nén

Cây có thể thành chuỗi `Θ(n)`, khiến một `find` hoặc `union` có thể tốn **`O(n)` worst-case**.

### Bộ nhớ của từng phương án

| Nhu cầu | Bộ nhớ |
|---|---|
| Chỉ liên thông, size, đếm nhóm và phát hiện sự kiện chu trình | `O(n)` |
| Thêm `edgeCount` ở mỗi gốc | Vẫn `O(n)` |
| Lưu rừng cạnh được nhận để có đường chứng cứ | `O(n)` cạnh (tối đa n−c), cộng DSU |
| Lưu **mọi** cạnh đã thêm | `O(n+m)` tổng |
| Khử cạnh lặp của đồ thị đơn bằng set | Thêm `O(m)` cho m cạnh phân biệt |

**Không nên đánh đồng bộ nhớ lưu rừng cha với lưu toàn bộ đồ thị**. Nếu chỉ cần phát hiện chu trình trực tuyến, có thể xử lý luồng cạnh mà không lưu mọi cạnh. Nếu cần in ra chu trình, phải duy trì thêm các cạnh phù hợp.

## 19. Trường hợp cực biên và quy tắc dữ liệu đầu vào

### Không có đỉnh

Với `n=0`:

```text
components = 0
edges_seen = 0
```

Không có `u`, `v` hợp lệ. Mọi yêu cầu `add_edge` phải bị từ chối; không được truy cập `parent[0]`.

### Chỉ một đỉnh

Với `n=1`, chưa có cạnh thì đồ thị có một thành phần và không có chu trình. Nếu chấp nhận khuyên `(0,0)`, sự kiện đó tạo chu trình độ dài 1; số thành phần vẫn là 1.

### Hai cạnh song song

Với đa đồ thị trên hai đỉnh:

```text
add_edge(0,1)  → không có chu trình, một thành phần
add_edge(0,1)  → có chu trình độ dài 2, vẫn một thành phần
```

Với đồ thị đơn, sự kiện thứ hai là **cạnh trùng không được thêm**, chứ không phải một cạnh mới.

### Đỉnh cô lập vẫn tính trong n

Nếu có n=8 nhưng chỉ có các cạnh giữa 0, 1, 2, ta vẫn phải đếm các đỉnh 3..7 là các thành phần riêng. Công thức `m-n+c` dùng **tất cả đỉnh đã đăng ký**, không chỉ đỉnh xuất hiện ở đầu mút cạnh.

### Chỉ số âm và chỉ số ngoài miền

Trong Python, `parent[-1]` trỏ tới phần tử cuối; đó không phải chỉ số DSU hợp lệ khi định nghĩa miền `0..n-1`. Cần kiểm tra kiểu và khoảng chỉ số trước khi thao tác.

### Cạnh lặp trong dữ liệu nhiễu

Nếu luồng sự kiện có thể truyền lại cùng một bản ghi vì lỗi mạng, phải phân biệt:

- **Một cạnh vật lý được gửi lại:** cần khử trùng lặp dựa trên ID sự kiện/cạnh, không tăng số cạnh.
- **Một cạnh vật lý song song mới:** trong đa đồ thị phải tính thêm một cạnh.

Chỉ từ cặp đỉnh `(u,v)` không thể luôn suy ra hai sự kiện có phải cùng một **cạnh vật lý** hay không. Khi cần phân biệt, dữ liệu đầu vào phải có ID cạnh.

## 20. Vì sao DSU cơ bản không xử lý xóa cạnh?

Xét đồ thị:

```text
0 — 1 — 2
```

Sau khi thêm các cạnh `(0,1)` và `(1,2)`, DSU xác định cả ba đỉnh thuộc một nhóm.

Nếu **xóa cạnh `(1,2)`**, đồ thị thật tách thành:

```text
{0,1}    {2}
```

Nhưng DSU chỉ biết một gốc chung và các liên kết cha nội bộ; nó không lưu đủ thông tin để xác định nên tách nhóm như thế nào.

### Xóa cạnh cũng có thể không tách nhóm

Nếu đồ thị có tam giác:

```text
0 — 1
 \ /
  2
```

Xóa một cạnh vẫn có thể giữ cả ba đỉnh liên thông qua hai cạnh còn lại. Vì thế không thể đơn giản “đảo union” theo cặp đầu mút; phải xét **cấu trúc các đường thay thế**.

Các hướng giải quyết khác gồm:

- Dựng lại DSU từ tập cạnh còn lại khi số lần xóa rất ít.
- Thuật toán **dynamic connectivity** chuyên dụng khi thêm/xóa cạnh trực tuyến.
- Các kỹ thuật **offline**, ví dụ chia khoảng thời gian tồn tại của cạnh, cây phân đoạn theo thời gian và **rollback DSU**.

Rollback DSU thường cần tránh path compression không kiểm soát vì `find` có thể sửa nhiều ô `parent`, làm hoàn tác phức tạp. Không được áp nguyên chặn `O(α(n))` của DSU chuẩn cho mọi phiên bản có rollback.

## 21. Vì sao DSU không phát hiện chu trình có hướng?

Trong đồ thị **có hướng**, các cạnh `u→v` mang chiều, và câu hỏi “có đường đi từ u tới v?” **không đối xứng**.

DSU biểu diễn quan hệ **cùng thành phần liên thông vô hướng**, là một quan hệ tương đương. Vì vậy DSU không giữ thông tin về chiều của đường đi.

### Phản ví dụ đồ thị có hướng không chu trình

Xét ba cạnh:

```text
0 → 1
0 → 2
1 → 2
```

Đồ thị này là **DAG** (không có chu trình có hướng). Tuy nhiên, nếu quên hướng và gọi DSU theo các cạnh:

1. Sau `0→1`, DSU hợp 0 và 1.
2. Sau `0→2`, DSU hợp 0 và 2.
3. Khi xử lý `1→2`, DSU thấy hai đầu **đã cùng gốc** và sẽ báo “tạo chu trình vô hướng”.

Kết luận đó **không có nghĩa tạo chu trình có hướng**.

### Cách phát hiện chu trình có hướng

Có thể dùng:

- **DFS với trạng thái trắng/xám/đen** để tìm cạnh ngược tới nút đang trên ngăn xếp DFS.
- **Sắp xếp topo/Kahn** để xác định đồ thị có hướng còn chu trình hay không.
- Thuật toán **incremental topological ordering** chuyên dụng nếu cạnh có hướng được thêm liên tục và cần cập nhật nhanh.

Nếu chỉ quan tâm **liên thông yếu** của đồ thị có hướng (bỏ hướng của các cạnh), DSU vẫn có thể quản lý các nhóm theo **đồ thị vô hướng nền**. Nhưng đó là **một bài toán khác** với phát hiện chu trình có hướng hoặc thành phần liên thông mạnh.

## 22. Phân biệt phát hiện chu trình và tìm cây khung nhỏ nhất

DSU cũng xuất hiện trong **thuật toán Kruskal** tìm cây khung nhỏ nhất (MST) của đồ thị vô hướng có trọng số.

Kruskal:

1. **Sắp xếp cạnh theo trọng số tăng dần.**
2. Duyệt theo thứ tự đã sắp xếp.
3. Chỉ nhận cạnh `(u,v)` khi hai đầu thuộc hai thành phần khác nhau.
4. Hợp hai thành phần sau khi nhận cạnh.

Điểm giống với bài toán trực tuyến: **kiểm tra hai gốc trước khi nhận cạnh** để tránh chu trình.

Điểm khác:

- Luồng cạnh tăng dần được xử lý theo **thứ tự thời gian đến**, không nhất thiết theo trọng số.
- Rừng cạnh được nhận từ luồng thời gian là một **rừng khung**, nhưng **không nhất thiết là rừng khung nhỏ nhất**.
- Kruskal cần **sắp xếp cạnh**, thường tốn `O(m\log m)` thời gian trước phần thao tác DSU.

### Ví dụ vì sao thứ tự đến không bảo đảm MST

Với ba đỉnh:

```text
(0,1) trọng số 100
(1,2) trọng số 100
(0,2) trọng số 1
```

Nếu nhận cạnh theo thứ tự đến, rừng sẽ nhận hai cạnh trọng số 100 và từ chối cạnh trọng số 1 do tạo chu trình. Tổng trọng số rừng là 200.

Kruskal sắp xếp trước, nhận cạnh trọng số 1 rồi một cạnh trọng số 100, tổng trọng số là **101**.

**Chỉ dùng DSU không làm một chiến lược chọn cạnh trở nên tối ưu.** DSU đảm bảo đúng **liên thông và tránh chu trình trong rừng đã nhận**; tiêu chí chọn cạnh là quyết định của thuật toán bên ngoài.

## 23. Đăng ký đỉnh mới trong mô hình tăng dần

Một số hệ thống không biết trước toàn bộ đỉnh. Khi một máy mới xuất hiện, ta có thể thêm một **nhóm đơn** vào DSU.

Giả mã:

```text
add_vertex():
    x = parent.length

    parent.append(x)
    size.append(1)
    edges_in_component.append(0)

    components += 1
    return x
```

Cần cập nhật **đồng bộ tất cả mảng**. Nếu chỉ tăng chiều dài `parent` mà quên `size` hoặc `edges_in_component`, các chỉ số sẽ lệch.

Nếu m và n thay đổi theo thời gian, công thức:

\[
r=m-n+c
\]

vẫn đúng ở **mỗi thời điểm** khi n là số đỉnh đã đăng ký, m là số cạnh đã thêm và c là số thành phần hiện tại. Thêm một đỉnh cô lập làm n tăng một và c tăng một, vì vậy r **không đổi**, đúng vì chưa có thêm chu trình.

### ID bên ngoài không liên tục

Khi đỉnh là chuỗi như `"device-A"` hoặc ID rất lớn, có thể dùng bảng ánh xạ:

```text
external_id → internal_index
```

rồi dùng mảng DSU trên chỉ số nội bộ. Phải xác định rõ `add_edge` sẽ **tự tạo đỉnh mới** hay **từ chối ID chưa đăng ký**. Trong lớp Python ở phần 11, các ID chưa đăng ký **bị từ chối**.

Chi phí bảng ánh xạ, cấp phát và lưu chuỗi phải được cộng ngoài chi phí DSU thuần.

## 24. Kiểm tra tính đúng đắn bằng mô hình tham chiếu

Với n nhỏ, có thể lưu **toàn bộ cạnh thật** và dùng BFS/DFS để tìm thành phần liên thông sau mỗi sự kiện; sau đó so sánh với DSU.

Một mô hình kiểm tra độc lập rất hữu ích:

1. Khởi tạo danh sách kề cho n đỉnh.
2. Trước khi thêm cạnh `(u,v)`, chạy BFS từ u để kiểm tra xem v đã tới được chưa.
3. So sánh kết quả BFS với cờ `creates_cycle` của DSU.
4. Thêm cạnh thật vào danh sách kề (với khuyên/đa cạnh xử lý theo đúng mô hình).
5. Đếm thành phần bằng BFS/DFS, so với `graph.components`.
6. Quét `parent` để kiểm tra các con trỏ nằm trong miền và số gốc bằng số thành phần.

### Python: kiểm tra cờ chu trình bằng BFS

```python
from collections import deque


def reachable(
    adj: list[list[int]], source: int, target: int
) -> bool:
    if source == target:
        return True

    seen = {source}
    queue = deque([source])

    while queue:
        u = queue.popleft()
        for v in adj[u]:
            if v == target:
                return True
            if v not in seen:
                seen.add(v)
                queue.append(v)

    return False


stream = [
    (0, 1), (1, 2), (3, 4), (2, 0), (4, 5),
    (2, 3), (5, 1), (6, 6), (6, 2), (0, 6)
]

n = 7
graph = IncrementalUndirectedGraph(n)
adj = [[] for _ in range(n)]

for u, v in stream:
    expected_cycle = reachable(adj, u, v)
    event = graph.add_edge(u, v)
    assert event["creates_cycle"] == expected_cycle

    # Mỗi lần thêm cạnh thật, thêm hai chiều trong
    # danh sách kề; khuyên được ghi hai lần cũng không
    # làm thay đổi tính liên thông khi BFS.
    adj[u].append(v)
    adj[v].append(u)

assert graph.redundant_edges == graph.cycle_rank() == 4
assert graph.components == 1
```

**BFS trong ví dụ kiểm thử không nhanh hơn DSU**: nó có thể đi qua `O(n+m)` cấu trúc đồ thị cho một lần hỏi. Mục đích là dùng một cách tính độc lập, dễ kiểm chứng trên trường hợp nhỏ, để phát hiện lỗi trong triển khai DSU.

### Các bất biến nên tự động kiểm tra

- `0 ≤ parent[x] < n` với mọi x.
- Mỗi đường cha kết thúc tại một gốc, không có chu trình cha sai.
- `components` bằng số gốc trong rừng DSU.
- Tổng `size[root]` trên các gốc bằng n.
- Với từng thành phần, `edges_in_component[root]≥size[root]-1`.
- Tổng `edges_in_component[root]` trên các gốc bằng `edges_seen`.
- `redundant_edges == edges_seen-n+components`.
- Mọi cặp đỉnh liên thông theo BFS có cùng `find` trong DSU.

Các kiểm tra toàn miền có thể tốn thời gian lớn, vì thế phù hợp cho unit test/debug, không nhất thiết chạy sau mỗi cạnh trong hệ thống sản xuất.

## 25. Những sai lầm hay gặp

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Gọi `union` trước rồi mới kiểm tra chu trình | Hai đầu luôn cùng nhóm sau phép hợp | Kiểm tra hai gốc **trước khi hợp** |
| Nối `parent[v]=u` thay vì nối hai gốc | Có thể làm sai phân hoạch, tạo chu trình cha | Tìm hai gốc rồi hợp đúng |
| Coi `parent` là cạnh đồ thị thật | Suy đường đi/chu trình không tồn tại | Lưu riêng cạnh thật khi cần chứng cứ |
| Tăng số nhóm sau một cạnh nối hai nhóm | Đếm sai; số nhóm phải giảm | Chỉ giảm khi hợp thành công |
| Giảm số nhóm khi cạnh đã nội bộ | Đếm sai liên thông | Nếu hai gốc bằng nhau, số nhóm giữ nguyên |
| Đếm cạnh tạo chu trình là tổng số mọi chu trình đơn | Có thể thiếu rất nhiều chu trình | Phân biệt cycle rank với liệt kê chu trình |
| Bỏ qua khuyên nhưng vẫn xem là một cạnh đã thêm | Không nhất quán mô hình | Quy định rõ đơn đồ thị/đa đồ thị |
| Xem sự kiện cạnh trùng là cạnh mới mà không xét ngữ nghĩa | Có thể báo chu trình giả do bản ghi gửi lại | Khử trùng lặp theo ID cạnh nếu cần |
| Chỉ tăng `edgeCount` khi union thành công | Bỏ sót cạnh nội bộ tạo chu trình | Đếm **mọi cạnh thực sự được thêm** |
| Dùng cùng-gốc để phát hiện chu trình có hướng | Có thể báo sai với DAG | Dùng DFS/topo hoặc thuật toán chuyên dụng |
| Xóa cạnh nhưng không cập nhật DSU | Có thể báo hai đỉnh vẫn liên thông khi đã tách | Dựng lại hoặc dynamic connectivity |
| Tưởng rừng được nhận theo thời gian là MST | Bỏ qua trọng số và bước sắp xếp | Phân biệt với Kruskal |
| Không kiểm tra ID âm/ngoài miền | Sai phần tử hoặc truy cập lỗi | Kiểm tra miền `0..n-1` |
| Bỏ qua chi phí xuất một chu trình cụ thể | Báo thời gian thấp hơn thực tế | Cộng BFS/DFS và chi phí đầu ra |
| Dùng `find` có nén trong môi trường đa luồng không đồng bộ | Có thể có data race và sai bộ đếm | Dùng khóa hoặc concurrent DSU |

## 26. Bài tập tự kiểm tra có lời giải

**Câu 1.** Ban đầu có 7 đỉnh cô lập. Sau ba cạnh nối ba cặp thành phần khác nhau, còn bao nhiêu thành phần?

**Đáp án:** `7-3=4` thành phần. Mỗi cạnh nối hai thành phần khác nhau giảm số thành phần đúng một.

**Câu 2.** Với các cạnh theo thứ tự `(0,1), (1,2), (2,0)` trong đồ thị vô hướng đơn, cạnh nào tạo chu trình?

**Đáp án:** Cạnh thứ ba `(2,0)`. Trước khi thêm nó đã có đường `2-1-0`.

**Câu 3.** Tại sao phải so sánh `find(u)` và `find(v)` **trước** phép hợp hai nhóm?

**Đáp án:** Sau khi hợp, hai đầu sẽ có cùng gốc dù ban đầu ở hai thành phần khác nhau. Kiểm tra sau union sẽ báo sai rằng mọi cạnh đều tạo chu trình.

**Câu 4.** Một cạnh nối hai thành phần riêng có thể tạo chu trình vô hướng ngay tại lúc nó được thêm không?

**Đáp án:** Không. Trước đó không có đường đi giữa hai đầu; cạnh mới chỉ tạo đường nối đầu tiên giữa hai thành phần, không khép vòng.

**Câu 5.** Trong ví dụ 10 cạnh trên 7 đỉnh, những sự kiện nào tạo chu trình?

**Đáp án:** Các bước **4, 7, 8, 10**: `(2,0)`, `(5,1)`, `(6,6)` và `(0,6)`.

**Câu 6.** Với `n=7`, `m=10` và `c=1`, cycle rank bằng bao nhiêu?

**Đáp án:** `m-n+c=10-7+1=4`.

**Câu 7.** Cycle rank bằng 4 có nghĩa đồ thị có đúng bốn chu trình đơn khác nhau không?

**Đáp án:** Không. Nó là số chu trình **độc lập**/số cạnh dư so với một rừng khung; số lượng chu trình đơn có thể lớn hơn.

**Câu 8.** Một đồ thị vô hướng liên thông có 9 đỉnh và không có chu trình. Nó có bao nhiêu cạnh?

**Đáp án:** **8 cạnh**, vì một cây trên v đỉnh có đúng `v-1` cạnh.

**Câu 9.** Một thành phần liên thông có 9 đỉnh và 9 cạnh. Có chu trình không?

**Đáp án:** **Có**. Vì `e=v`, cycle rank của thành phần là `9-9+1=1`.

**Câu 10.** Một khuyên `(u,u)` được thêm vào đa đồ thị vô hướng có tạo chu trình không?

**Đáp án:** **Có**, nếu mô hình cho phép khuyên; đó là chu trình độ dài 1. Nó không làm giảm số thành phần.

**Câu 11.** Hai cạnh song song khác nhau cùng nối u với v có thể tạo chu trình không?

**Đáp án:** **Có** trong đa đồ thị, chúng tạo chu trình độ dài 2. Trong đồ thị đơn, cạnh thứ hai phải được xem là cạnh trùng và không thêm.

**Câu 12.** Tại sao DSU không đủ để in ra các đỉnh trên một chu trình cụ thể?

**Đáp án:** DSU chỉ lưu đại diện/thành phần; liên kết cha không nhất thiết là cạnh thật. Cần lưu rừng cạnh được nhận hoặc đồ thị rồi tìm đường đi cũ giữa hai đầu.

**Câu 13.** Khi `add_edge(u,v)` thấy hai đầu đã liên thông, có phải tăng `size[root]` không?

**Đáp án:** **Không.** Không có đỉnh mới và không hợp nhóm mới; chỉ số cạnh thực và bộ đếm chu trình tăng nếu cạnh mới thực sự được thêm.

**Câu 14.** Một thành phần có 4 đỉnh, 4 cạnh và một thành phần khác có 3 đỉnh, 2 cạnh. Thêm một cạnh nối chúng. Thành phần mới có bao nhiêu đỉnh/cạnh?

**Đáp án:** **7 đỉnh, 7 cạnh**, vì `4+3=7` và `4+2+1=7`.

**Câu 15.** Vì sao đếm `edges_in_component[root]` chỉ khi `union` thành công là sai?

**Đáp án:** Nó bỏ sót cạnh nối hai đỉnh đã cùng nhóm, trong khi những cạnh đó tồn tại trong đồ thị và tạo chu trình.

**Câu 16.** Trong đồ thị có hướng `0→1, 0→2, 1→2`, dùng DSU bỏ hướng có thể báo chu trình ở cạnh thứ ba không? Đồ thị có chu trình có hướng không?

**Đáp án:** DSU **có thể báo chu trình vô hướng** ở cạnh `1→2` vì hai đầu đã cùng nhóm. Nhưng đồ thị có hướng là **DAG**, không có chu trình có hướng.

**Câu 17.** Thêm cạnh theo thứ tự trọng số bất kỳ, dùng DSU để tránh chu trình, có chắc nhận được MST không?

**Đáp án:** **Không.** Cần thuật toán như Kruskal với cạnh được xét theo trọng số tăng dần hoặc một phương pháp MST hợp lệ khác.

**Câu 18.** Nếu hệ thống chỉ cần hỏi liên thông và phát hiện cạnh tạo chu trình, có bắt buộc lưu toàn bộ m cạnh không?

**Đáp án:** **Không.** DSU có thể xử lý luồng theo thời gian với `O(n)` bộ nhớ; chỉ cần giữ thêm cạnh thật khi ứng dụng yêu cầu chứng cứ chu trình, lịch sử hoặc thao tác khác.

**Câu 19.** Với union by size và path compression, tổng thời gian DSU cho m cạnh và q truy vấn trên n đỉnh thường được mô tả thế nào?

**Đáp án:** `O(n+(m+q)α(n))` theo chặn **khấu hao** quen dùng; không có nghĩa mỗi `find` là `O(1)` worst-case.

**Câu 20.** Một đỉnh mới được đăng ký nhưng chưa có cạnh. Trong công thức `r=m-n+c`, các đại lượng thay đổi thế nào?

**Đáp án:** n tăng 1, c tăng 1, m không đổi, nên r không đổi. Đỉnh mới chưa tạo chu trình.

**Câu 21.** Nếu xóa cạnh `(1,2)` khỏi đường `0-1-2`, có thể giữ DSU cũ và vẫn trả đúng liên thông không?

**Đáp án:** **Không.** Đỉnh 2 sẽ tách khỏi nhóm `{0,1}`, nhưng DSU chuẩn không có thao tác split để tự cập nhật.

**Câu 22.** Nếu muốn truy vấn trạng thái liên thông của đồ thị ở thời điểm quá khứ, mảng DSU hiện tại có đủ không?

**Đáp án:** **Không.** Mảng hiện tại chỉ biểu diễn phân hoạch hiện hành; cần lưu lịch sử, các bản snapshot, persistent DSU hoặc thuật toán offline phù hợp.

**Câu 23.** Thêm cạnh `(u,v)` khi hai đầu đã liên thông làm số thành phần thay đổi bao nhiêu?

**Đáp án:** **Không thay đổi**. Nếu cạnh được thêm thực sự, số cạnh dư/cycle rank tăng một.

**Câu 24.** Trong một ứng dụng có thể gửi trùng cùng ID sự kiện cạnh, tại sao không nên đếm mỗi lần nhận bản tin là một cạnh mới?

**Đáp án:** Bản tin gửi lại không nhất thiết là một cạnh vật lý mới. Nếu đếm trùng, `m` và cycle rank sai; cần khử trùng lặp theo định danh cạnh/sự kiện theo hợp đồng.

## Ghi nhớ

- **Liên thông tăng dần** chỉ thêm cạnh. DSU duy trì mỗi thành phần vô hướng dưới dạng một nhóm, và `find(u)==find(v)` khi và chỉ khi hai đỉnh liên thông ở thời điểm hiện tại.
- **Để phát hiện chu trình**, kiểm tra **hai gốc trước khi hợp**. Nếu đã cùng gốc, cạnh vô hướng mới đóng một đường đi cũ thành chu trình; nếu khác gốc, cạnh nối hai thành phần và không tạo chu trình.
- Cạnh được nhận khi hai thành phần khác nhau tạo thành **rừng khung** với `n-c` cạnh. Số cạnh dư hay số chu trình **độc lập** là **`m-n+c`**, không phải số lượng mọi chu trình đơn.
- **Khuyên và cạnh song song** phải theo quy ước của đồ thị đơn hoặc đa đồ thị. Cạnh chỉ được tính khi thực sự thêm; bản ghi lặp bị lọc không được tăng số cạnh.
- **Đếm cạnh trong thành phần** phải tăng cả khi cạnh nội bộ không dẫn đến union. Một thành phần liên thông có chu trình khi `edgeCount[root]≥size[root]`.
- **Union by size/rank + path compression** cho chi phí DSU gần `O(α(n))` **khấu hao** trên mỗi thao tác; để trả **chu trình cụ thể**, cần giữ cạnh thật và tìm đường, có chi phí bổ sung.
- DSU chuẩn không trực tiếp xử lý **xóa cạnh, tách thành phần, truy vấn lịch sử hoặc phát hiện chu trình có hướng**. Hãy chọn thuật toán theo đúng yêu cầu và bất biến của bài toán.

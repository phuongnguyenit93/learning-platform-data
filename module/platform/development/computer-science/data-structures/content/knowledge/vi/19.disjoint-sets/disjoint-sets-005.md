# Hợp theo kích thước hoặc theo hạng

Một cấu trúc **Disjoint Set Union (DSU)**, còn gọi là **Union–Find**, quản lý những nhóm phần tử không giao nhau. Mỗi nhóm là một cây trong rừng cha `parent`, và phần tử có cùng gốc thì thuộc cùng nhóm. Khi hợp hai nhóm, cách đơn giản nhất là nối gốc này dưới gốc kia. Tuy nhiên, **chọn gốc không hợp lý có thể tạo một cây rất cao**, làm `find` phải đi qua nhiều con trỏ cha.

Hai chiến lược cơ bản để khống chế chiều cao là **hợp theo kích thước (union by size)** và **hợp theo hạng (union by rank)**. Cả hai đều chọn gốc dựa vào thông tin của cây thay vì nối tùy ý. Nếu kết hợp thêm **nén đường đi (path compression)**, DSU có thời gian xử lý chuỗi thao tác gần như hằng số theo nghĩa **khấu hao**.

Bài này thuộc chương **Tập hợp rời nhau** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**, nơi ta học cách chọn cấu trúc dữ liệu dựa trên **bất biến, thao tác, độ phức tạp thời gian và bộ nhớ**. Trọng tâm là phân biệt chính xác hai heuristic, chứng minh vì sao chúng hiệu quả, triển khai đúng và tránh nhầm metadata của gốc với dữ liệu của các nút con.

## 1. Bài toán: hợp nhóm đúng nhưng cây quá sâu

Cho `n` phần tử:

\[
U=\{0,1,\ldots,n-1\}.
\]

Mỗi phần tử x lưu một con trỏ cha:

```text
parent[x] = nút cha của x
parent[root] = root
```

Các nút có cùng gốc tạo thành **một nhóm**. Hàm `find(x)` lần theo các con trỏ cha đến gốc. Hàm `union(x,y)` phải lấy hai gốc `rx=find(x)`, `ry=find(y)` rồi **chỉ nối hai gốc khi chúng khác nhau**.

Một phép hợp cơ bản:

```text
union(x, y):
    rx = find(x)
    ry = find(y)

    if rx == ry:
        return false

    parent[ry] = rx
    return true
```

Cách này đúng về **phân hoạch** nhưng không giới hạn tốt chiều cao cây.

### Ví dụ tạo chuỗi dài

Khởi tạo `parent[i]=i` với sáu phần tử, rồi gọi:

```text
union(1,0)
union(2,1)
union(3,2)
union(4,3)
union(5,4)
```

Vì mỗi lần nối gốc nhóm của đối số thứ hai dưới gốc nhóm của đối số thứ nhất, ta nhận:

```text
0 → 1 → 2 → 3 → 4 → 5
                        ^ gốc

parent = [1,2,3,4,5,5]
```

Để tính `find(0)`, chương trình phải đi qua **năm cạnh cha**. Với `n` nút, cách hợp tùy ý có thể tạo chiều cao `n-1`, khiến `find` mất **`Θ(n)`** ở trường hợp xấu.

Vấn đề **không phải tính đúng đắn**: mọi nút vẫn thuộc một cây hợp lệ. Vấn đề là **hiệu năng của những lần truy vấn sau**.

## 2. Nguyên tắc chung: nối gốc để giữ cây thấp

Khi hợp hai cây, chúng ta có quyền chọn gốc nào trở thành gốc mới. Để giữ độ cao thấp, một hướng hợp lý là:

- Không để một cây đang lớn hoặc cao bị treo dưới một cây nhỏ hoặc thấp nếu có thể tránh.
- Gắn **gốc của cây nhỏ/yếu hơn** dưới **gốc của cây lớn/mạnh hơn**.
- Chỉ cập nhật metadata của **gốc mới**.
- Không thay đổi gì nếu hai phần tử đã cùng gốc.

Hai cách xác định “mạnh hơn” là:

1. **Union by size:** dùng **số thành viên** trong nhóm.
2. **Union by rank:** dùng **hạng** phản ánh thông tin về độ cao của cây.

Cả hai chiến lược đều **không thay đổi ngữ nghĩa**: hai nhóm được hợp vẫn gồm đúng những phần tử ban đầu của hai nhóm, bất kể gốc nào được giữ.

### Bất biến nền tảng của DSU

Mọi triển khai bên dưới phải luôn thỏa:

1. Với `0 ≤ x < n`, `parent[x]` cũng thuộc `[0,n)`.
2. Mỗi cây có đúng một gốc `r` với `parent[r]=r`.
3. Không có chu trình cha dài từ hai nút trở lên; lần theo cha luôn tới gốc.
4. `find(x)==find(y)` **khi và chỉ khi** x và y cùng nhóm.
5. Các cây rời nhau và bao phủ toàn bộ miền.
6. Một `union` thành công giảm số nhóm đúng **một**; hợp trùng không giảm.

Hai heuristic chỉ điều chỉnh **cách chọn gốc** và metadata, không thay thế các bất biến này.

## 3. Union by size: kích thước nhóm quyết định gốc

Ta thêm mảng:

```text
size[root] = số phần tử của cây có gốc root
```

Ban đầu mỗi nhóm có một phần tử:

```text
parent = [0,1,2,3,4,5]
size   = [1,1,1,1,1,1]
```

Khi hợp hai cây có gốc `rx` và `ry`, luôn giữ gốc của **cây lớn hơn hoặc bằng**. Nếu nhóm của `rx` nhỏ hơn, hoán đổi hai gốc.

```text
union_by_size(x, y):
    rx = find(x)
    ry = find(y)

    if rx == ry:
        return false

    if size[rx] < size[ry]:
        swap(rx, ry)

    parent[ry] = rx
    size[rx] += size[ry]
    componentCount -= 1
    return true
```

Hàm `find` ở đây có thể là bản đi theo cha đơn giản hoặc bản có nén đường đi. Chính sách union by size **không phụ thuộc** vào việc `find` có nén hay không để đảm bảo gộp đúng hai nhóm.

### Ví dụ với hai nhóm không cân bằng

Giả sử:

```text
Nhóm A = {0,1,2,3}, rootA = 0, size[0] = 4
Nhóm B = {4,5},     rootB = 4, size[4] = 2
```

Gọi `union_by_size(5,3)`:

```text
rx = find(5) = 4   // size 2
ry = find(3) = 0   // size 4

size[rx] < size[ry] → đổi rx, ry

rx = 0, ry = 4

parent[4] = 0
size[0] = 4 + 2 = 6
```

Mặc dù đối số đầu của phép hợp thuộc nhóm nhỏ, **gốc 0** được giữ lại vì nhóm đó lớn hơn.

Sau hợp:

```text
Cây chung có root 0
Các phần tử: {0,1,2,3,4,5}
size[0] = 6
```

**Chú ý:** `size[4]` có thể còn giá trị **2**, nhưng nó không còn mô tả kích thước nhóm hiện tại vì 4 đã là nút con. Phải hỏi:

```text
component_size(x) = size[find(x)]
```

### Khi hai nhóm bằng kích thước

Nếu `size[rx]==size[ry]`, chọn gốc nào cũng đúng. Ví dụ trên, ta giữ `rx` — tức gốc nhóm chứa đối số đầu sau khi tính `find`.

**Quy tắc chọn trong trường hợp bằng nhau phải nhất quán trong ví dụ hoặc kiểm thử mảng cha**, nhưng nó không ảnh hưởng phân hoạch logic. Hai cài đặt có thể cho mảng `parent` khác nhau mà vẫn trả cùng kết quả `same` và `component_size`.

## 4. Vì sao union by size khống chế chiều cao?

Giả sử một cây `T_a` có `a` nút được gắn dưới cây `T_b` có `b` nút. Union by size chỉ cho phép tình huống này khi:

\[
a\le b.
\]

Khi gốc `T_a` trở thành con của gốc `T_b`:

- Độ sâu của mỗi nút trong `T_a` **tăng đúng một**.
- Nhóm mới chứa những nút đó có kích thước:

\[
a+b\ge 2a.
\]

Nói cách khác, **mỗi lần độ sâu một nút tăng vì cây của nó bị treo dưới cây khác, kích thước nhóm chứa nút đó ít nhất gấp đôi**.

Nếu một nút bị tăng độ sâu `t` lần, nhóm chứa nó có ít nhất `2^t` phần tử. Vì tổng số phần tử không vượt `n`:

\[
2^t\le n
\quad\Longrightarrow\quad
t\le \lfloor\log_2 n\rfloor.
\]

Do đó, **không dùng path compression**, chiều cao của mọi cây được chặn bởi:

\[
h\le\lfloor\log_2 n\rfloor.
\]

Vì `find` chỉ đi qua các cạnh cha trên đường đến gốc, mỗi `find` và `union` có chặn thời gian **`O(log n)`** trong trường hợp xấu khi chỉ dùng union by size.

### Đối chiếu với phép hợp tùy ý

| Nhiều phép hợp | Nối gốc tùy ý | Union by size |
|---|---|---|
| Tính đúng của phân hoạch | Đúng nếu luôn nối hai gốc khác nhau | Đúng |
| Chiều cao xấu nhất | Có thể `Θ(n)` | `O(log n)` |
| Thời gian `find` xấu nhất, chưa nén | `O(n)` | `O(log n)` |
| Metadata riêng | Không bắt buộc | `size[root]` |
| Truy vấn kích thước nhóm | Cần quét hoặc metadata khác | `size[find(x)]` |

Điều quan trọng là chặn `O(log n)` này **đúng trước cả khi thêm path compression**. Path compression chỉ có thể rút ngắn đường cha, không làm tăng chiều cao.

## 5. Union by rank: dùng hạng thay vì số thành viên

**Union by rank** lưu một giá trị `rank[root]` tại mỗi gốc. Bắt đầu với nhóm đơn:

```text
parent[x] = x
rank[x] = 0
```

Ta định nghĩa rank theo quy tắc:

- Khi hai gốc có **rank khác nhau**, gắn gốc rank thấp dưới gốc rank cao. **Rank gốc mới giữ nguyên**.
- Khi hai gốc có **rank bằng nhau**, chọn một gốc làm gốc mới và **tăng rank của gốc đó đúng 1**.
- Khi hai phần tử vốn đã cùng gốc, **không nối, không tăng rank**.

Giả mã:

```text
union_by_rank(x, y):
    rx = find(x)
    ry = find(y)

    if rx == ry:
        return false

    if rank[rx] < rank[ry]:
        swap(rx, ry)

    parent[ry] = rx

    if rank[rx] == rank[ry]:
        rank[rx] += 1

    componentCount -= 1
    return true
```

**Thứ tự quan trọng:** ta kiểm tra hạng của **hai gốc trước khi nối**. Trong cách viết này, `rank[ry]` không bị thay đổi khi gắn `ry` dưới `rx`, nên điều kiện bằng nhau vẫn phản ánh hai rank cũ.

### Vì sao chỉ tăng rank khi bằng nhau?

Giả sử cây cao nhất (rank cao) có rank `r`, còn cây được gắn dưới nó có rank **nhỏ hơn** `r`. Khi thêm một cạnh từ gốc cây thấp tới gốc cây cao, chiều cao tổng thể **không cần tăng**.

Nhưng khi hai cây **cùng rank `r`**, treo một gốc dưới gốc còn lại có thể làm xuất hiện một đường dài hơn một cạnh, nên rank gốc mới tăng lên `r+1`.

```text
Ban đầu: hai nút đơn        Sau union(0,1):

    0       1                   0   rank=1
                               |
rank=0    rank=0                1

Hai cây rank=1:             Sau khi gộp:

    0       2                   0   rank=2
    |       |                  / \
    1       3                 1   2
                                 |
                                 3
```

Nếu sau đó nối thêm một cây chỉ có rank 0 dưới gốc rank 2, rank **vẫn là 2**.

## 6. Rank không đồng nghĩa với kích thước hoặc chiều cao hiện tại

Đây là điểm phân biệt quan trọng nhất giữa hai heuristic.

### `size[root]` có nghĩa gì?

`size[root]` là **số phần tử thực sự** trong nhóm của gốc đó ở thời điểm hiện tại. Nếu có `k` thành viên, `size[root]=k`. Khi hợp hai nhóm khác nhau, kích thước **luôn được cộng**.

### `rank[root]` có nghĩa gì?

`rank[root]` là **hạng được duy trì theo thuật toán**, dùng làm chỉ báo về độ cao:

- Không dùng path compression, với cách khởi tạo rank 0 và quy tắc union by rank chuẩn, rank của gốc có thể đúng bằng chiều cao cây.
- Có path compression, các đường cha có thể được rút ngắn nhưng rank **không giảm**; vì vậy rank chỉ còn là **chặn trên** cho chiều cao hiện tại, không nhất thiết bằng chiều cao thật.
- Rank không bằng số thành viên và **không dùng trực tiếp để trả lời `component_size`**.

Nếu `rank[root]=3`, ta không thể suy ra nhóm có đúng 3 phần tử. Thực tế, gốc rank 3 có **ít nhất 8 phần tử** theo lập luận tăng rank ở phần tiếp theo.

### Metadata của nút không phải gốc

Sau khi hợp, chỉ `size[root]` hoặc `rank[root]` ở **gốc hiện tại** mới được xem là metadata của cả nhóm.

```text
Trước union:
  root A = 0, rank[0] = 2
  root B = 4, rank[4] = 1

Sau union:
  parent[4] = 0
  rank[0] = 2
  rank[4] vẫn có thể là 1 (giá trị cũ)
```

Không được so sánh `rank[x]` với `rank[y]` khi `x` và `y` là các nút tùy ý. **Luôn gọi `find` trước, rồi so sánh rank của hai gốc.**

## 7. Chứng minh rank không vượt `log₂ n`

Lập luận theo cách rank được tăng.

**Bước cơ sở:** một nhóm đơn có rank 0 và kích thước 1, thỏa:

\[
\operatorname{size}(G)\ge 2^{\operatorname{rank}(G)}
\quad\text{vì }1\ge2^0.
\]

**Bước hợp với rank khác nhau:** gốc có rank cao hơn được giữ lại, rank không đổi, còn kích thước nhóm tăng. Bất đẳng thức vẫn đúng.

**Bước hợp với rank bằng nhau:** hai gốc có rank `r`. Theo giả thuyết quy nạp, mỗi nhóm chứa ít nhất `2^r` nút. Sau hợp:

\[
\operatorname{size}_{\mathrm{new}}
\ge 2^r + 2^r
= 2^{r+1}.
\]

Thuật toán tăng rank gốc mới lên `r+1`, nên bất đẳng thức tiếp tục đúng.

Vì không nhóm nào có hơn `n` phần tử:

\[
2^{\operatorname{rank(root)}}\le n
\quad\Longrightarrow\quad
\operatorname{rank(root)}\le\lfloor\log_2 n\rfloor.
\]

Đồng thời, khi **không nén đường đi**, chiều cao thực tế của cây không vượt rank gốc theo cách hợp chuẩn. Khi **có nén đường đi**, chiều cao chỉ giảm hoặc giữ nguyên trong thao tác `find`, nên rank vẫn là chặn trên.

**Kết quả:** union by rank cũng bảo đảm `find`/`union` có chặn xấu nhất **`O(log n)`** nếu chưa sử dụng path compression; đây là chặn dựa trên số nút, không dựa vào cảm nhận “cây trông cân bằng”.

## 8. Mô phỏng tám phần tử: size và rank đều tránh cây chuỗi

Bắt đầu với `n=8`:

```text
parent = [0,1,2,3,4,5,6,7]
size   = [1,1,1,1,1,1,1,1]
rank   = [0,0,0,0,0,0,0,0]
components = 8
```

Ta lần lượt gọi:

```text
union(0,1)
union(2,3)
union(4,5)
union(6,7)
union(0,2)
union(4,6)
union(0,4)
```

**Trong ví dụ này**, cả union by size và union by rank đều giữ gốc của đối số đầu khi metadata bằng nhau. Hai cách tạo cùng hình dạng rừng:

| Bước | Lần hợp | `parent` sau hợp | Số nhóm |
|---:|---|---|---:|
| 0 | Khởi tạo | `[0,1,2,3,4,5,6,7]` | 8 |
| 1 | `union(0,1)` | `[0,0,2,3,4,5,6,7]` | 7 |
| 2 | `union(2,3)` | `[0,0,2,2,4,5,6,7]` | 6 |
| 3 | `union(4,5)` | `[0,0,2,2,4,4,6,7]` | 5 |
| 4 | `union(6,7)` | `[0,0,2,2,4,4,6,6]` | 4 |
| 5 | `union(0,2)` | `[0,0,0,2,4,4,6,6]` | 3 |
| 6 | `union(4,6)` | `[0,0,0,2,4,4,4,6]` | 2 |
| 7 | `union(0,4)` | `[0,0,0,2,0,4,4,6]` | 1 |

Các giá trị tại **gốc 0** sau bước 7:

```text
size[0] = 8
rank[0] = 3

Đường tới gốc sâu nhất:
  7 → 6 → 4 → 0   (3 cạnh)
  3 → 2 → 0       (2 cạnh)
```

Nhưng `size` và `rank` cập nhật theo quy tắc khác nhau:

| Lần hợp | Gốc được giữ | `size` ở gốc sau hợp | `rank` ở gốc sau hợp |
|---|---:|---:|---:|
| `union(0,1)` | 0 | 2 | 1 |
| `union(2,3)` | 2 | 2 | 1 |
| `union(4,5)` | 4 | 2 | 1 |
| `union(6,7)` | 6 | 2 | 1 |
| `union(0,2)` | 0 | 4 | 2 |
| `union(4,6)` | 4 | 4 | 2 |
| `union(0,4)` | 0 | 8 | 3 |

### Sau khi nén đường đi

Gọi `find(7)` với **full path compression**:

```text
Trước:
7 → 6 → 4 → 0

Sau:
parent[7] = 0
parent[6] = 0
parent[4] = 0

parent = [0,0,0,2,0,4,0,0]
```

Trong cây này vẫn còn đường `5→4→0` và `3→2→0` dài 2 cạnh. Vì vậy **chiều cao hiện tại giảm từ 3 xuống 2**, trong khi:

```text
size[0] = 8   // không đổi
rank[0] = 3   // không đổi
components = 1
```

Đây là minh họa trực tiếp rằng **rank có thể lớn hơn chiều cao thực tế sau path compression**. Không được giảm rank theo chiều cao mới trong thuật toán union by rank chuẩn.

## 9. Khi nào union by size và union by rank chọn gốc khác nhau?

Không phải lúc nào hai heuristic cũng chọn cùng gốc.

Xây hai nhóm:

```text
Nhóm A = {0,1,2,3}
  union(0,1), union(0,2), union(0,3)
  rootA = 0, size[0] = 4, rank[0] = 1

Nhóm B = {4,5}
  union(4,5)
  rootB = 4, size[4] = 2, rank[4] = 1
```

Bây giờ gọi `union(4,0)`:

**Union by size:**

```text
size[4] = 2 < size[0] = 4
→ Gắn gốc 4 dưới gốc 0
→ root mới = 0, size[0] = 6
```

**Union by rank**, với quy tắc giữ gốc đối số đầu khi rank bằng:

```text
rank[4] = 1 == rank[0] = 1
→ Gắn gốc 0 dưới gốc 4
→ root mới = 4, rank[4] = 2
```

Hai kết quả có **gốc khác nhau**, nhưng cùng phân hoạch:

\[
\{\{0,1,2,3,4,5\}\}.
\]

Không được đánh giá tính đúng chỉ bằng so sánh `parent` hay root có đúng “giá trị mong đợi” nếu bài toán không bắt buộc chọn gốc cụ thể.

### Nên chọn size hay rank?

- **Size** trực tiếp phục vụ truy vấn số thành viên của nhóm.
- **Rank** tóm tắt thông tin về chiều cao theo quy tắc union và có thể cần lưu riêng `size` nếu muốn trả kích thước.
- Cả hai có bộ nhớ **`O(n)`** và cùng chặn độ phức tạp lý thuyết điển hình.
- Với các kích thước thông thường, chênh lệch tốc độ thực tế phụ thuộc dữ liệu, cache, kiểu số, compiler và cách tối ưu khác; không có quy tắc “rank luôn nhanh hơn size”.

## 10. Cài đặt Python: DSU hợp theo kích thước

Mã bên dưới dùng miền chỉ số liên tục `0..n-1`. Hàm `find` thực hiện full path compression **dạng lặp** để tránh phụ thuộc vào giới hạn đệ quy.

```python
class DSUBySize:
    def __init__(self, n: int):
        if n < 0:
            raise ValueError("n phải không âm")

        self.parent = list(range(n))
        self.size = [1] * n
        self.components = n

    def _check(self, x: int) -> None:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError("Chỉ số phải là số nguyên")
        if not 0 <= x < len(self.parent):
            raise IndexError("Chỉ số ngoài miền DSU")

    def find(self, x: int) -> int:
        self._check(x)

        root = x
        while self.parent[root] != root:
            root = self.parent[root]

        while self.parent[x] != x:
            next_x = self.parent[x]
            self.parent[x] = root
            x = next_x

        return root

    def union(self, x: int, y: int) -> bool:
        rx = self.find(x)
        ry = self.find(y)

        if rx == ry:
            return False

        if self.size[rx] < self.size[ry]:
            rx, ry = ry, rx

        self.parent[ry] = rx
        self.size[rx] += self.size[ry]
        self.components -= 1
        return True

    def same(self, x: int, y: int) -> bool:
        return self.find(x) == self.find(y)

    def component_size(self, x: int) -> int:
        return self.size[self.find(x)]


dsu = DSUBySize(8)

for x, y in [
    (0, 1), (2, 3), (4, 5), (6, 7),
    (0, 2), (4, 6), (0, 4)
]:
    assert dsu.union(x, y) is True

assert dsu.components == 1
assert dsu.component_size(7) == 8
assert dsu.same(3, 6) is True

# Gộp trùng không được cộng kích thước hoặc trừ số nhóm.
assert dsu.union(3, 7) is False
assert dsu.components == 1
assert dsu.component_size(0) == 8

print(dsu.parent)
```

### Điểm cần nắm từ mã

- Chỉ `size[root]` của **gốc hiện tại** có ý nghĩa “kích thước nhóm”.
- Khi hai gốc giống nhau, hàm trả về `False` **trước khi** cộng size.
- Khi nhóm nhỏ là đối số đầu, phép hoán đổi đảm bảo gốc của nhóm lớn mới được giữ.
- `components` chỉ giảm một lần trên mỗi phép hợp thành công.
- Gọi `find` có thể thay đổi `parent` để nén đường; mã này **không tự an toàn đa luồng**.

**Lưu ý xử lý chỉ số:** Python xem `True`/`False` là giá trị thuộc kiểu `int`, nên `_check` cố ý từ chối `bool` nếu API chỉ nhận chỉ số nguyên thông thường. Trong một API đơn giản hơn có thể chỉ kiểm tra khoảng chỉ số, nhưng phải có hợp đồng rõ ràng.

## 11. Cài đặt Python: DSU hợp theo hạng

Phiên bản union by rank có logic `find` giống hệt, nhưng `union` quyết định dựa trên `rank` thay cho `size`.

```python
class DSUByRank:
    def __init__(self, n: int):
        if n < 0:
            raise ValueError("n phải không âm")

        self.parent = list(range(n))
        self.rank = [0] * n
        self.components = n

    def _check(self, x: int) -> None:
        if not 0 <= x < len(self.parent):
            raise IndexError("Chỉ số ngoài miền DSU")

    def find(self, x: int) -> int:
        self._check(x)

        root = x
        while self.parent[root] != root:
            root = self.parent[root]

        while self.parent[x] != x:
            next_x = self.parent[x]
            self.parent[x] = root
            x = next_x

        return root

    def union(self, x: int, y: int) -> bool:
        rx = self.find(x)
        ry = self.find(y)

        if rx == ry:
            return False

        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx

        self.parent[ry] = rx

        # Chỉ tăng rank nếu rank của hai gốc bằng nhau.
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1

        self.components -= 1
        return True

    def same(self, x: int, y: int) -> bool:
        return self.find(x) == self.find(y)


dsu = DSUByRank(8)

for x, y in [
    (0, 1), (2, 3), (4, 5), (6, 7),
    (0, 2), (4, 6), (0, 4)
]:
    assert dsu.union(x, y)

assert dsu.components == 1
assert dsu.rank[dsu.find(0)] == 3
assert dsu.same(3, 7) is True
assert dsu.union(1, 6) is False

print(dsu.parent)
print(dsu.rank[dsu.find(0)])  # 3
```

**Tại sao lớp `DSUByRank` không có `component_size`?** Vì rank **không phải** số thành viên. Nếu muốn hỏi kích thước nhóm với thời gian tương tự `find`, cần bổ sung mảng `size` và cộng hai kích thước sau mỗi phép hợp. Một API khác có thể đếm thành viên bằng cách quét cả miền, nhưng thường mất nhiều thời gian hơn.

### Một lỗi nhỏ dễ làm sai rank

Đoạn mã **sai**:

```python
# Sai: tăng rank của gốc mới sau mọi phép hợp!
self.parent[ry] = rx
self.rank[rx] += 1
```

Rank chỉ được tăng khi **hai rank cũ bằng nhau**. Nếu tăng sau mọi phép hợp, nó không còn tuân theo bất biến thuật toán rank chuẩn; các lập luận về hạng, chiều cao và số nút tối thiểu theo rank không còn áp dụng như đã chứng minh.

## 12. Ví dụ C++17: union by rank, đóng gói mảng cha

Với ID liên tục, `std::vector` giúp giữ hai mảng cha và hạng liên tiếp trong bộ nhớ. Ví dụ C++17 dưới đây dùng **path halving** cho `find`, một biến thể của nén đường đi:

```cpp
#include <algorithm>
#include <cstddef>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <vector>

class DSUByRank {
public:
    explicit DSUByRank(std::size_t n)
        : parent_(n), rank_(n, 0), components_(n) {
        std::iota(parent_.begin(), parent_.end(), std::size_t{0});
    }

    std::size_t find(std::size_t x) {
        if (x >= parent_.size()) {
            throw std::out_of_range("DSU index out of range");
        }

        // Path halving: cho mỗi nút trỏ tới ông/bà.
        while (parent_[x] != x) {
            parent_[x] = parent_[parent_[x]];
            x = parent_[x];
        }
        return x;
    }

    bool unite(std::size_t x, std::size_t y) {
        x = find(x);
        y = find(y);

        if (x == y) return false;

        if (rank_[x] < rank_[y]) std::swap(x, y);

        parent_[y] = x;

        if (rank_[x] == rank_[y]) {
            ++rank_[x];
        }

        --components_;
        return true;
    }

    bool same(std::size_t x, std::size_t y) {
        return find(x) == find(y);
    }

    std::size_t component_count() const {
        return components_;
    }

private:
    std::vector<std::size_t> parent_;
    std::vector<unsigned> rank_;
    std::size_t components_;
};

int main() {
    DSUByRank dsu(6);

    dsu.unite(0, 1);
    dsu.unite(2, 3);
    dsu.unite(0, 2);

    std::cout << dsu.same(1, 3) << '\n';  // 1
    std::cout << dsu.same(0, 5) << '\n';  // 0
    std::cout << dsu.component_count() << '\n'; // 3

    std::cout << dsu.unite(1, 3) << '\n'; // 0, hợp trùng
}
```

Khác với full path compression dạng hai lượt ở Python, **path halving** rút ngắn đường trong lúc đi và có thể tạo mảng `parent` khác sau cùng một truy vấn. Dù vậy, `find` vẫn trả về **đúng gốc**, còn `unite` vẫn có hợp đồng và tính đúng đắn như nhau.

### Hợp đồng cần giữ khi dùng C++

- `std::size_t` là kiểu không dấu; chỉ số `x>=n` bị từ chối bằng ngoại lệ.
- Constructor tương đương tạo `n` nhóm đơn.
- `rank_` chỉ có ý nghĩa đối với **gốc hiện tại** và không được suy ra kích thước nhóm.
- `find` có thể sửa mảng `parent_`, nên không phải phương thức `const`.
- Cài đặt ví dụ là đơn luồng; cập nhật đồng thời cần thiết kế riêng.

## 13. Độ phức tạp và đánh đổi bộ nhớ

Đặt:

- `n`: số phần tử đã đăng ký.
- `m`: số thao tác tìm/hợp trong một chuỗi truy vấn.
- `h`: chiều cao của cây cha tại thời điểm xét.
- `α(n)`: hàm **Ackermann ngược**, tăng cực kỳ chậm.

| Cách cài đặt | Chiều cao cây | `find` xấu nhất | `union` xấu nhất | Bộ nhớ |
|---|---|---|---|---|
| Nối gốc tùy ý, không nén | Có thể `Θ(n)` | `O(n)` | `O(n)` | `O(n)` |
| Union by size, không nén | `O(log n)` | `O(log n)` | `O(log n)` | `O(n)` |
| Union by rank, không nén | `O(log n)` | `O(log n)` | `O(log n)` | `O(n)` |
| Union by size + path compression | Không vượt chặn logarithmic từ union | `O(α(n))` **khấu hao** | `O(α(n))` **khấu hao** | `O(n)` |
| Union by rank + path compression | Không vượt chặn logarithmic từ union | `O(α(n))` **khấu hao** | `O(α(n))` **khấu hao** | `O(n)` |

### Chi phí khởi tạo

Khởi tạo `parent` cùng `size` hoặc `rank` cho `n` phần tử mất **`Θ(n)` thời gian** và **`Θ(n)` bộ nhớ**.

Một lần `union` bao gồm hai lần `find`, một phép nối gốc và vài phép đọc/ghi metadata; phần công việc ngoài `find` là **`O(1)`**.

### Khấu hao có nghĩa gì?

Kết quả lý thuyết kinh điển khi kết hợp union by size/rank với path compression thường được diễn đạt là chi phí **gần `O(α(n))` khấu hao cho một thao tác** trong một chuỗi dài. Một cách viết tổng quát, đơn giản khi khởi tạo n phần tử rồi thực hiện m thao tác là:

\[
O\bigl(n+m\alpha(n+m)\bigr),
\]

với giả định mô hình và phát biểu chuẩn phù hợp; các công thức chặt hơn có thể biểu diễn theo cả `n` và `m`.

Điều này **không** bảo đảm một lần `find` riêng lẻ luôn mất `O(1)` trong trường hợp xấu. Nó có thể cần đi qua một đường cha dài trước khi nén. Hiệu quả được phân tích trên **toàn bộ chuỗi thao tác**.

Nếu không muốn dựa vào phân tích khấu hao, chỉ dùng union by size/rank đã có chặn rõ ràng **`O(log n)` worst-case** cho mỗi `find` hoặc `union`.

### Size và rank khác chi phí bộ nhớ bao nhiêu?

Cả hai lưu một mảng `parent` và một mảng metadata, do đó đều là **`O(n)` bộ nhớ**. Tuy nhiên:

- `size[root]` có thể cần biểu diễn giá trị từ 1 đến `n`.
- `rank[root]` không vượt `⌊log₂ n⌋`, nên có thể biểu diễn bằng kiểu số nhỏ hơn trong một số triển khai.
- Nếu dùng union by rank **và vẫn cần kích thước nhóm**, phải lưu thêm `size`, tăng hằng số bộ nhớ.
- Nếu chỉ cần truy vấn cùng nhóm, hai cách đều đủ; hãy ưu tiên tính rõ ràng và đo hiệu năng thực tế khi cần.

## 14. Chứng minh các heuristic giữ nguyên phân hoạch

Ta xét hai bất biến:

1. Mỗi nhóm tương ứng một cây cha có đúng một gốc.
2. Hai phần tử cùng nhóm khi và chỉ khi tìm tới cùng gốc.

**Ban đầu:** `parent[x]=x` cho mọi x, nên có n cây đơn không giao nhau; bất biến đúng.

**Một phép `find` không nén:** chỉ đọc đường cha nên không đổi bất biến.

**Một phép `find` có nén:** đổi một số liên kết cha bên trong một cây thành liên kết trực tiếp tới **gốc của chính cây ấy**; không thay thành viên, không chuyển nút giữa các cây và không làm gốc mất vai trò gốc.

**Phép `union` khi hai gốc bằng nhau:** không nối gì, không đổi phân hoạch. Nếu có `size`, `rank` và số nhóm, đều không thay đổi.

**Phép `union` khi hai gốc khác nhau:** hai cây đang rời nhau; nối gốc `ry` dưới gốc `rx` (hoặc ngược lại) làm chúng trở thành một cây, không tạo chu trình vì chưa có đường cha nối hai cây trước đó.

Chọn `rx` bằng **size** hoặc **rank** chỉ quyết định **hình dạng cây**. Cả hai cùng bảo toàn các nhóm logic và làm số nhóm giảm một. Phần metadata được cập nhật theo đúng quy tắc để giữ thêm bất biến của heuristic tương ứng.

### Hai lỗi metadata dẫn tới kết quả sai

**Lỗi 1 — Hợp trùng vẫn cộng kích thước:**

```text
rx = find(x)
ry = find(y)

// Sai nếu rx == ry:
size[rx] += size[ry]
```

Nếu `rx==ry`, đây là cùng nhóm, cộng kích thước sẽ **đếm hai lần những phần tử đã có**, phá dữ liệu `size`. Phải trả về ngay khi hai gốc bằng nhau.

**Lỗi 2 — Tăng rank sau phép hợp khác hạng:**

```text
rank[rx] = 3
rank[ry] = 1

parent[ry] = rx

// Sai:
rank[rx] += 1
```

Khi cây rank 1 treo dưới cây rank 3, rank gốc mới **giữ nguyên 3**, vì không xuất hiện lý do tăng hạng theo thuật toán chuẩn.

## 15. Kiểm tra thử bằng bảng và bất biến

Có thể kiểm tra hai thuật toán bằng cách đối chiếu **phân hoạch và kết quả truy vấn**, thay vì buộc mảng cha phải giống nhau.

### Kiểm tra nhóm được giữ đúng

```python
operations = [
    (0, 1), (2, 3), (4, 5), (6, 7),
    (0, 2), (4, 6), (0, 4)
]

a = DSUBySize(8)
b = DSUByRank(8)

for x, y in operations:
    assert a.union(x, y) == b.union(x, y)

assert a.components == b.components == 1

for x in range(8):
    for y in range(8):
        assert a.same(x, y) == b.same(x, y)
```

Hai DSU có thể cho **gốc khác nhau** khi kích thước và rank ưu tiên khác nhau. Kiểm tra trên là hợp lý vì nó đối chiếu **câu trả lời cùng nhóm**.

### Kiểm tra size ở các gốc

```python
def validate_sizes(dsu: DSUBySize) -> None:
    n = len(dsu.parent)

    groups: dict[int, list[int]] = {}
    for x in range(n):
        r = dsu.find(x)
        groups.setdefault(r, []).append(x)

    assert len(groups) == dsu.components

    for root, members in groups.items():
        assert dsu.parent[root] == root
        assert dsu.size[root] == len(members)

    assert sum(dsu.size[root] for root in groups) == n


validate_sizes(a)
```

### Kiểm tra chặn rank

Dù lớp chỉ lưu rank mà không lưu kích thước, trong phép kiểm tra nhỏ có thể đếm thành viên của từng gốc và xác minh:

\[
2^{\operatorname{rank(root)}}\le \#\{\text{phần tử của nhóm root}\}.
\]

```python
def validate_ranks(dsu: DSUByRank) -> None:
    groups: dict[int, int] = {}

    for x in range(len(dsu.parent)):
        root = dsu.find(x)
        groups[root] = groups.get(root, 0) + 1

    assert len(groups) == dsu.components

    for root, count in groups.items():
        assert dsu.parent[root] == root
        assert (1 << dsu.rank[root]) <= count


validate_ranks(b)
```

**Lưu ý:** các hàm kiểm thử trên gọi `find`, nên giả định mảng cha đã tạo một rừng hợp lệ và `find` có thể kết thúc. Nếu nghi ngờ dữ liệu `parent` đã bị hỏng và có chu trình, phải dùng trình kiểm tra chu trình riêng trước khi gọi `find` để tránh vòng lặp vô hạn.

## 16. Áp dụng trong thuật toán đồ thị

Đối với **đồ thị vô hướng** có `V` đỉnh, DSU giúp quản lý các thành phần liên thông khi **thêm cạnh**:

```text
for each vertex v:
    make_set(v)

for each edge (u, v) added:
    union(u, v)

connected(u, v):
    return find(u) == find(v)
```

Nếu số cạnh lớn và các phép kiểm tra liên thông lặp lại nhiều, union by size hoặc union by rank tránh việc cây cha trở nên quá dài. Path compression giảm thêm chi phí các truy vấn về sau.

### Phát hiện cạnh tạo chu trình

Trong quá trình xây một rừng cạnh được chấp nhận:

- Nếu `find(u) != find(v)`, thêm cạnh `(u,v)` nối hai cây khác nhau, sau đó `union(u,v)`.
- Nếu `find(u) == find(v)`, hai đỉnh đã có đường đi trong rừng; thêm cạnh sẽ tạo chu trình.

Đây là vai trò của DSU trong **thuật toán Kruskal** để tìm cây khung nhỏ nhất. Với `E` cạnh, sau khi sắp xếp các cạnh theo trọng số, phần DSU xử lý những phép thử/hợp với chi phí gần hằng số khấu hao. **Thời gian sắp xếp `O(E log E)` thường vẫn là thành phần quan trọng của Kruskal.**

### DSU không giải quyết việc gì?

- **Xóa cạnh/tách thành phần:** DSU chuẩn chỉ hợp, không tự đảo phép hợp.
- **Trả về đường đi giữa hai đỉnh:** rừng cha của DSU không phải cây cạnh thật của đồ thị gốc.
- **Quan hệ có hướng không mang tính tương đương:** không thể dùng `find` để suy ra mọi truy vấn đường đi có hướng.
- **Nhóm giao nhau:** một phần tử đồng thời nằm trong nhiều nhóm độc lập không phù hợp với một phân hoạch DSU.

Union by size và union by rank chỉ cải thiện **hiệu năng của cùng mô hình DSU**, không mở rộng loại thao tác hay quan hệ mà cấu trúc có thể biểu diễn.

## 17. Lỗi thường gặp khi triển khai union by size/rank

| Sai lầm | Tác hại | Cách tránh |
|---|---|---|
| So sánh `size[x]` và `size[y]` khi x/y không phải gốc | Metadata có thể cũ | Gọi `find`, chỉ xét `size[rx]`/`size[ry]` |
| So sánh `rank[x]` và `rank[y]` khi x/y chưa phải gốc | Chọn sai gốc theo heuristic | Chỉ so sánh rank của hai gốc |
| Tăng rank sau mọi lần hợp | Phá quy tắc rank và lập luận chặn chiều cao | Chỉ tăng khi hai rank trước hợp **bằng nhau** |
| Gọi `union` trên cùng gốc nhưng vẫn cộng size | Đếm trùng thành viên | Nếu `rx==ry`, trả no-op |
| Không kiểm tra cùng gốc rồi nối một nút tùy ý | Có thể tạo chu trình cha | Luôn nối **hai gốc khác nhau** |
| Dùng `rank[root]` như số thành viên | Trả kết quả kích thước sai | Dùng `size[root]` hoặc đếm thực tế |
| Sau path compression, gán rank bằng chiều cao vừa thấy | Rank có thể là chặn trên, không phải chiều cao thật | Giữ rank theo quy tắc chuẩn |
| Lưu gốc như ID nhóm nghiệp vụ vĩnh viễn | Root có thể đổi sau một lần hợp | Dùng mã nhóm nghiệp vụ riêng |
| Nghĩ dùng size/rank thì `find` worst-case `O(1)` | Sai; chặn chưa nén là `O(log n)` | Phân biệt worst-case và khấu hao |
| Dùng đệ quy tìm gốc khi giới hạn stack không đủ | Có thể tràn stack | Dùng `find` dạng lặp |
| Đổi metadata nhưng quên cập nhật `components` | Sai số nhóm | Chỉ giảm sau hợp thành công |
| Nhiều luồng cùng ghi DSU không đồng bộ | Có thể mất cập nhật hoặc phá bất biến rừng | Dùng khóa hoặc concurrent DSU |

### Rank và size không bảo đảm đại diện ổn định

Nếu nhóm chứa x trước phép hợp có gốc `r`, sau khi hợp vào nhóm lớn/cao hơn, gốc mới có thể khác `r`. Vì vậy, **`find(x)` là đại diện hiện tại**, không phải ID cố định mà ứng dụng nên lưu trong khóa ngoại.

Nếu cần một ID nhóm bền vững, hãy duy trì metadata theo quy tắc nghiệp vụ thay vì buộc heuristic của DSU phải phục vụ hai mục đích mâu thuẫn.

## 18. Quy trình lựa chọn heuristic

Khi thiết kế DSU cho một bài toán mới, có thể tự hỏi:

1. **Có cần kích thước nhóm không?** Nếu có, union by size tiện vì đã duy trì `size[root]`.
2. **Chỉ quan tâm liên thông/cùng nhóm?** Union by size hoặc union by rank đều là lựa chọn chuẩn.
3. **Dữ liệu lớn và nhiều truy vấn lặp lại?** Kết hợp với path compression.
4. **Cần kiểm soát worst-case mà chưa dùng compression?** Cả hai cho chiều cao `O(log n)`.
5. **ID có liên tục không?** Nếu `0..n-1` thì mảng `parent`/`size`/`rank` thuận lợi; nếu ID rời rạc, dùng bảng ánh xạ hoặc DSU dựa trên dictionary.
6. **Có cần tách nhóm, hoàn tác, xóa cạnh không?** DSU chuẩn với compression có thể không phù hợp; xem xét thuật toán rollback hoặc liên thông động.
7. **Có truy cập đồng thời không?** Path compression và union đều có thể ghi vào cấu trúc chung; phải cân nhắc đồng bộ.

Nếu không có yêu cầu đặc biệt, **union by size + path compression** thường là điểm xuất phát rõ ràng vì vừa tốt về hiệu năng, vừa thuận tiện cho truy vấn kích thước. **Union by rank + path compression** cũng có chặn lý thuyết tương đương.

## 19. Bài tập tự kiểm tra có lời giải

**Câu 1.** Trong DSU mảng cha, vì sao phải tìm hai gốc trước khi hợp?

**Đáp án:** Phép hợp phải gộp **toàn bộ hai cây**, không chỉ nối hai nút x/y. Gắn gốc khác nhau bảo đảm các nhóm được hợp đúng và không tạo chu trình cha.

**Câu 2.** Hai nhóm có kích thước 3 và 8. Union by size sẽ giữ gốc nhóm nào?

**Đáp án:** Giữ gốc của nhóm 8 phần tử; gốc của nhóm 3 phần tử nối bên dưới. Kích thước nhóm mới bằng 11.

**Câu 3.** Hai gốc có rank 2 và rank 5. Sau union by rank, rank của gốc mới bằng bao nhiêu?

**Đáp án:** Bằng **5**. Cây rank 2 nối dưới gốc rank 5; rank **không tăng** vì hai hạng khác nhau.

**Câu 4.** Hai gốc khác nhau cùng có rank 2. Sau union by rank, rank gốc mới là bao nhiêu?

**Đáp án:** Rank tăng từ 2 lên **3** tại gốc được giữ; gốc kia trở thành nút con.

**Câu 5.** Tại sao không tăng rank khi `union(x,y)` với `find(x)==find(y)`?

**Đáp án:** Đó là phép hợp trùng, **không tạo nhóm mới cũng không thay cấu trúc giữa hai cây**, nên không có lý do tăng rank. Số nhóm cũng không đổi.

**Câu 6.** Nếu nhóm A có 12 phần tử nhưng rank 1, còn nhóm B có 8 phần tử rank 3, union by size và union by rank có thể chọn gốc khác nhau không?

**Đáp án:** Có. Union by size ưu tiên nhóm A vì `12>8`. Union by rank ưu tiên nhóm B vì `3>1`. Cả hai đều đúng về phân hoạch.

**Câu 7.** Vì sao union by size không dùng path compression vẫn cho chiều cao `O(log n)`?

**Đáp án:** Mỗi lần một cây bị treo dưới cây khác, nó là cây nhỏ hơn hoặc bằng; kích thước nhóm chứa những nút bị tăng độ sâu **ít nhất gấp đôi**. Một nút không thể tăng độ sâu quá `log₂ n` lần.

**Câu 8.** Một gốc có rank 4. Nhóm của nó phải có ít nhất bao nhiêu phần tử theo bất biến union by rank?

**Đáp án:** Ít nhất `2^4=16` phần tử. Rank 4 không có nghĩa nhóm chỉ có bốn phần tử.

**Câu 9.** Sau path compression, một nhóm có rank 3 nhưng chiều cao thực tế là 1. Điều này có sai không?

**Đáp án:** Không. Rank được duy trì như một **chặn trên**, không tự giảm theo chiều cao thực tế sau compression.

**Câu 10.** Hai DSU áp dụng cùng chuỗi hợp nhóm nhưng chọn root khác nhau có thể đều đúng không?

**Đáp án:** Có. Tính đúng dựa trên **phân hoạch**, tức cặp phần tử nào cùng nhóm, số nhóm và kích thước nhóm, không phụ thuộc giá trị root cụ thể.

**Câu 11.** Sau khi union by size hợp hai gốc có kích thước 4 và 7, ta có thể đọc `size` ở gốc đã trở thành con để biết kích thước nhóm mới không?

**Đáp án:** Không. `size` ở nút con có thể là giá trị cũ. Cần lấy `size[find(x)]` của **gốc hiện tại**, lúc đó bằng 11.

**Câu 12.** DSU có `n=1024` phần tử, dùng union by rank nhưng chưa path compression. Chiều cao cây có thể vượt 10 không?

**Đáp án:** Không nếu áp dụng đúng heuristic từ trạng thái nhóm đơn, vì `rank≤⌊log₂ 1024⌋=10` và chiều cao không vượt rank.

**Câu 13.** Vì sao nói `O(α(n))` khấu hao không đồng nghĩa mỗi lần `find` worst-case `O(1)`?

**Đáp án:** Chặn khấu hao đánh giá **tổng chi phí của một chuỗi thao tác**, còn một lần `find` riêng lẻ vẫn có thể phải đi qua nhiều cạnh cha trước khi nén.

**Câu 14.** Nếu chỉ cần số nhóm hiện tại, có nhất thiết đếm gốc bằng cách quét toàn bộ `parent` không?

**Đáp án:** Không. Có thể lưu `components=n` ban đầu và giảm đúng một sau mỗi lần hợp hai gốc khác nhau; đọc biến này là `O(1)`.

**Câu 15.** Trong Kruskal, khi nào một cạnh được chấp nhận để nối hai thành phần?

**Đáp án:** Khi hai đầu cạnh có `find(u) != find(v)`. Khi đó việc thêm cạnh không tạo chu trình trong rừng cạnh đã chấp nhận, và DSU hợp hai nhóm.

**Câu 16.** DSU có path compression và union by rank có thể xóa một cạnh và tự tách đúng hai nhóm hay không?

**Đáp án:** Không. Hai tối ưu chỉ cải thiện thao tác hợp và tìm đại diện; DSU kinh điển vẫn không có thao tác tách nhóm sau khi xóa liên kết.

## Ghi nhớ

- **Union by size** gắn **gốc nhóm nhỏ dưới gốc nhóm lớn** và cộng kích thước tại gốc mới. `size[root]` là **số thành viên thực** của nhóm, thuận tiện cho `component_size(x)`.
- **Union by rank** gắn gốc rank thấp dưới gốc rank cao; **chỉ tăng rank một đơn vị khi hai rank bằng nhau**. Rank là thông tin về độ cao, **không phải kích thước nhóm**.
- Cả hai heuristic giữ chiều cao **`O(log n)`** ngay cả khi chưa nén đường đi. Kết hợp **path compression** đem lại chi phí gần hằng số **khấu hao**, thường diễn đạt bằng `α(n)`.
- **Rank có thể lớn hơn chiều cao thực sau nén**. Chỉ so sánh `size`/`rank` ở **các gốc hiện tại**, không ở nút con, và không coi root là ID nghiệp vụ bền vững.
- **Union chỉ cập nhật metadata và giảm số nhóm khi hai gốc khác nhau**; hợp trùng phải là no-op. Mọi phép tìm/hợp cần giữ bất biến rừng cha và phân hoạch.
- Chọn **size hoặc rank** theo nhu cầu truy vấn và tính rõ ràng của cài đặt. Cả hai dùng `O(n)` bộ nhớ; **không** tự hỗ trợ tách nhóm, xóa cạnh hoặc truy cập đồng thời thiếu đồng bộ.

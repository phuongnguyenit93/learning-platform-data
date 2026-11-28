# Danh sách kề và chi phí theo số đỉnh, số cạnh

## 1. Từ câu hỏi “đỉnh này nối với ai?” đến danh sách kề

Trong mạng xã hội, mỗi người dùng thường chỉ kết nối với một phần nhỏ người dùng khác. Trong hệ thống học tập, mỗi học phần cũng chỉ có một số học phần tiên quyết hoặc phụ thuộc trực tiếp. Nếu cần duyệt các đối tượng **liên kết với một đỉnh đã biết**, ta không nhất thiết phải tạo bảng cho mọi cặp đỉnh có thể có.

**Danh sách kề (adjacency list)** lưu, với mỗi đỉnh `u`, một tập hoặc danh sách các đỉnh có liên kết trực tiếp với `u`. Đối với đồ thị có hướng, thông thường đây là **các đỉnh đích của cung đi ra từ `u`**.

Ví dụ, đồ thị vô hướng gồm ba đỉnh nối thành đường thẳng:

```text
A ----- B ----- C       D

Danh sách kề:
A: [B]
B: [A, C]
C: [B]
D: []          D là đỉnh cô lập, vẫn được lưu
```

Khác với **ma trận kề** dành một ô cho mỗi cặp đỉnh, danh sách kề chủ yếu dành chỗ cho **những liên kết thực sự tồn tại**. Nhờ đó, với `n` đỉnh và `m` cạnh/cung, cách biểu diễn chuẩn thường chỉ tốn **`O(n+m)` bộ nhớ**. Đây là lựa chọn quan trọng trong nền tảng cấu trúc dữ liệu khi phải đánh đổi giữa bộ nhớ, kiểm tra một cặp đỉnh và duyệt các láng giềng.

## 2. Khái niệm, ký hiệu và quy ước

Cho đồ thị `G=(V,E)`, trong đó:

- `V` là tập đỉnh, `n=|V|` là **số đỉnh**.
- `E` là tập cạnh vô hướng hoặc cung có hướng, `m=|E|` là **số liên kết thực**.
- `adj[u]` là các mục kề được lưu cho đỉnh `u`.
- `deg(u)` là bậc của đỉnh trong đồ thị vô hướng; `outdeg(u)` và `indeg(u)` lần lượt là bậc ra và bậc vào trong đồ thị có hướng.

Trong một đồ thị vô hướng đơn, cạnh `{u,v}` không phân biệt thứ tự: có cạnh A—B cũng có nghĩa B—A. Trong một đồ thị có hướng, cung `(u,v)` mang chiều `u → v`; không tự sinh cung `v → u`.

Chữ **“danh sách”** trong “danh sách kề” chỉ ý tưởng lưu những láng giềng có thật. Mỗi `adj[u]` có thể được cài bằng:

- Một **list/vector** lưu các mục theo thứ tự chèn.
- Một **set** lưu các đỉnh kề phân biệt.
- Một **hash map** từ đỉnh kề đến trọng số hoặc thông tin liên kết.
- Danh sách các **edge ID** nếu cho phép nhiều cạnh/cung song song.

Những lựa chọn này có cùng ý tưởng biểu diễn nhưng **không có cùng chi phí mọi thao tác**. Khi nói một phép kiểm tra kề là `O(1)` hay `O(deg(u))`, phải cho biết loại cấu trúc được dùng ở bên trong.

## 3. Ví dụ đầy đủ với đồ thị vô hướng

Xét tập đỉnh `V={A,B,C,D,E}` và các cạnh:

\[
E=\{\{A,B\},\{A,C\},\{B,C\},\{C,D\}\}.
\]

```text
      A -------- B          E (cô lập)
       \        /
        \      /
            C -------- D
```

Danh sách kề biểu diễn bằng list:

| Đỉnh | `adj[u]` | Bậc `deg(u)` |
| --- | --- | ---: |
| A | `[B, C]` | 2 |
| B | `[A, C]` | 2 |
| C | `[A, B, D]` | 3 |
| D | `[C]` | 1 |
| E | `[]` | 0 |

Ta có `n=5`, `m=4`. Có **8 mục kề** vì **mỗi cạnh vô hướng được ghi ở hai đầu mút**:

\[
\sum_{u\in V}\deg(u)=2+2+3+1+0=8=2m.
\]

Đây là **định lý bắt tay (handshaking lemma)** và cũng là bất biến kiểm tra dữ liệu: nếu quên thêm C vào danh sách của A nhưng vẫn thêm A vào danh sách của C, phép đếm có thể sai và biểu diễn không còn đối xứng.

Khi lưu bằng từ điển, phải **tạo khóa cho cả E** dù `adj[E]` rỗng. Chỉ suy ra tập đỉnh từ những cạnh hiện có sẽ làm mất thông tin về đỉnh cô lập.

### Có cần sắp xếp láng giềng?

Không nhất thiết. `[B,C]` và `[C,B]` biểu diễn **cùng tập láng giềng** đối với một đồ thị đơn không yêu cầu thứ tự. Nhưng thứ tự lưu có thể ảnh hưởng đến **thứ tự thăm** khi chạy BFS/DFS. Nếu bài toán cần đầu ra duyệt ổn định theo ID, phải quy định sắp xếp hoặc một thứ tự duyệt cố định; sắp xếp cũng có chi phí.

## 4. Đồ thị có hướng: chỉ ghi cung đi ra

Giữ tập đỉnh `V={A,B,C,D,E}`, nhưng thay các cạnh bằng cung:

\[
E=\{(A,B),(A,C),(C,B),(C,D)\}.
\]

```text
A -----> B         E (cô lập)
 \       ^
  \     /
   v   /
     C -----> D
```

Danh sách kề **theo cung đi ra**:

| Đỉnh nguồn | `adj[u]`: các đỉnh đích | `outdeg(u)` | `indeg(u)` |
| --- | --- | ---: | ---: |
| A | `[B, C]` | 2 | 0 |
| B | `[]` | 0 | 2 |
| C | `[B, D]` | 2 | 1 |
| D | `[]` | 0 | 1 |
| E | `[]` | 0 | 0 |

Có `m=4` cung nên **chỉ có 4 mục kề**, khác với 8 mục của đồ thị vô hướng ở mục trước. Hai tổng bậc thỏa:

\[
\sum_{u\in V}\operatorname{outdeg}(u)
=\sum_{u\in V}\operatorname{indeg}(u)=m=4.
\]

**Không được** tự thêm A vào `adj[B]` chỉ vì có cung A→B. Nếu cần nhanh chóng truy vấn “những đỉnh nào có cung tới B?”, ta có thể duy trì thêm **danh sách kề ngược** `incoming[B]`; khi đó mỗi lần thêm/xóa cung phải cập nhật cả hai phía.

Một đỉnh có danh sách cung đi ra rỗng **chưa chắc là đỉnh cô lập**. B trong ví dụ có `outdeg(B)=0` nhưng `indeg(B)=2`, nên B không cô lập. E mới thực sự có cả bậc vào và bậc ra bằng 0.

## 5. Khi có trọng số, khuyên hoặc cạnh song song

### Trọng số

Thay vì chỉ lưu đỉnh kề, mỗi mục có thể lưu `(neighbor, weight)`:

```text
Đồ thị có hướng có trọng số:
A: [(B, 5), (C, 2)]
B: []
C: [(B, 7), (D, 4)]
D: []
E: []
```

Với đồ thị vô hướng có trọng số, cùng một cạnh A—B trọng số 5 thường tạo hai mục `(B,5)` ở A và `(A,5)` ở B. Hai trọng số phải **nhất quán**; không được âm thầm coi cạnh vô hướng là hai cung có trọng số khác nhau.

**Trọng số bằng 0 vẫn có thể hợp lệ.** Để kiểm tra một liên kết có tồn tại hay không, phải dựa trên **sự hiện diện của mục kề**, không dựa vào biểu thức `if weight` vì `0` là giá trị falsy trong Python.

### Khuyên (self-loop)

Khuyên `{u,u}` hoặc cung `(u,u)` nối một đỉnh với chính nó.

- Trong đồ thị **có hướng**, khuyên thường xuất hiện **một mục** `u` trong danh sách cung đi ra của `u`, tăng bậc ra và bậc vào mỗi loại 1.
- Trong đồ thị **vô hướng**, bậc theo quy ước chuẩn đếm khuyên **hai lần**. Có hai lựa chọn biểu diễn: ghi khuyên **hai mục** trong `adj[u]`, hoặc chỉ ghi **một mục** nhưng tính bậc bằng độ dài danh sách cộng thêm số khuyên tại `u`.

Hai cách đều hợp lệ nếu thực hiện nhất quán. **Không được lấy `len(adj[u])` làm bậc vô hướng** trong cách chỉ ghi mỗi khuyên một mục mà không cộng thêm phần bù.

### Cạnh/cung song song

Trong **đa đồ thị**, hai liên kết có cùng đầu mút vẫn có thể là hai sự kiện độc lập:

```text
edge_id 0: A -- B, trọng số 5
edge_id 1: A -- B, trọng số 9
```

Để giữ được cả hai, có thể dùng `adj[A] = [(B,0),(B,1)]` và bảng `edges[id] -> (u,v,w)`. Một `set` láng giềng hoặc `dict` `B -> weight` thông thường sẽ **gộp hoặc ghi đè** các liên kết song song. Đồ thị đơn có thể dùng set/map, còn đa đồ thị cần **định danh liên kết hoặc dữ liệu lưu tính bội**.

## 6. Đếm bộ nhớ theo n và m

Giả sử mỗi ID đỉnh và mỗi mục kề có kích thước cố định trong mô hình phân tích cơ bản.

**Đồ thị có hướng:** mỗi cung `u→v` tạo **một mục** trong `adj[u]`. Cần `n` cấu trúc chứa danh sách và `m` mục kề:

\[
S_{\text{có hướng}}(n,m)=\Theta(n+m).
\]

**Đồ thị vô hướng:** mỗi cạnh không khuyên được ghi **hai mục**. Nếu khuyên cũng được ghi hai mục, tổng đúng `2m` mục; nếu khuyên ghi một mục, tổng không vượt quá `2m`. Vì thế:

\[
S_{\text{vô hướng}}(n,m)=\Theta(n+2m)=\Theta(n+m).
\]

Điểm `\Theta(n)` rất quan trọng: ngay cả khi **`m=0`**, ta vẫn phải lưu đủ `n` đỉnh, kể cả các danh sách rỗng.

| Ví dụ | Số đỉnh `n` | Số liên kết `m` | Số mục kề (không có khuyên) | Số ô của ma trận kề |
| --- | ---: | ---: | ---: | ---: |
| Có hướng, thưa | 5 | 4 | 4 | 25 |
| Vô hướng, thưa | 5 | 4 | 8 | 25 |
| Có hướng, 10.000 đỉnh | 10.000 | 20.000 | 20.000 | 100.000.000 |
| Vô hướng, 10.000 đỉnh | 10.000 | 20.000 | 40.000 | 100.000.000 |

Đây là **số mục logic**, không phải số byte RAM thực tế. Danh sách của Python có overhead cho các đối tượng list/tuple/string; ma trận bitset có thể nén mỗi ô thành một bit. Tuy nhiên, trong mô hình thông thường, **bậc tăng trưởng** vẫn là `n+m` với danh sách kề so với `n^2` với ma trận đặc.

Nếu đồ thị **thưa** (`m\ll n^2`), danh sách kề thường tiết kiệm bộ nhớ đáng kể. Nếu đồ thị **dày** (`m=\Theta(n^2)`), hai biểu diễn có cùng bậc bộ nhớ `\Theta(n^2)`, nhưng số đối tượng, cách truy cập và chi phí thao tác vẫn khác.

## 7. Chi phí từng thao tác với danh sách kề dạng list

Giả sử `adj[u]` là một **list**. Ký hiệu `d(u)` là số mục kề của `u`: thường bằng `deg(u)` ở đồ thị vô hướng không khuyên, hoặc `outdeg(u)` ở đồ thị có hướng.

| Thao tác | Chi phí với list | Nguyên nhân |
| --- | --- | --- |
| Tạo tất cả danh sách rỗng cho `n` đỉnh | `O(n)` | Tạo một cấu trúc ứng với mỗi đỉnh |
| Thêm một mục vào cuối `adj[u]` | `O(1)` **phân bổ** | `append` thỉnh thoảng phải mở rộng list |
| Thêm cạnh vô hướng đã biết chắc chưa tồn tại | `O(1)` phân bổ | Hai lần `append`, không phải duyệt cả đồ thị |
| Kiểm tra có cung `u→v` không | `O(d(u))` trường hợp xấu | Phải quét danh sách của `u` |
| Chèn cạnh vào **đồ thị đơn** và kiểm tra trùng | `O(d(u))` hoặc cao hơn tùy kiểm tra đối xứng | Trước khi thêm cần biết có cặp đầu mút đó chưa |
| Xóa cung `u→v` khỏi list | `O(d(u))` | Tìm mục và dời phần tử còn lại |
| Xóa cạnh vô hướng `{u,v}` | `O(d(u)+d(v))` | Xóa các mục ở cả hai đầu; khuyên cần quy ước riêng |
| Duyệt toàn bộ láng giềng của `u` | `\Theta(d(u))` | Mỗi mục kề được đọc một lần |
| Lấy `outdeg(u)` hoặc số mục kề | `O(1)` | `len(adj[u])` nếu list được duy trì đầy đủ |
| Đếm `indeg(v)` nếu chỉ lưu cung đi ra | `O(n+m)` | Quét các danh sách để tìm cung đi tới `v` |

Cận `O(1)` cho **thêm cạnh** chỉ đúng khi ta không phải quét để **kiểm tra trùng đầu mút**, không phải sắp xếp lại, và không có kiểm tra đặc biệt phức tạp. Một API `add_edge` cho **đồ thị đơn** phải bảo đảm không có cạnh trùng, vì vậy với list thông thường chi phí thực tế có thể là `O(d(u))`.

**Xóa đỉnh:** cần xử lý các liên kết liên quan. Với đồ thị có hướng chỉ lưu cung đi ra, phải tìm cả **cung đi vào** từ những danh sách khác; một cách làm trực tiếp là quét toàn bộ `n+m` mục, tốn `O(n+m)`. Với đồ thị vô hướng, có thể duyệt các láng giềng của đỉnh để tìm và xóa mục đối ứng, chi phí tùy độ dài của những danh sách đó; nếu không có chỉ mục phụ, cận đơn giản an toàn là `O(n+m)` cho một cách cài đặt quét toàn bộ.

Nếu ID đỉnh là chuỗi và `adj` là `dict`, cần cộng chi phí tra cứu `adj[u]`. Chi phí ấy thường `O(1)` **kỳ vọng** khi hash/equality của ID có chi phí hằng số và phân bố phù hợp, không phải bảo đảm cho đầu vào đối kháng hoặc chuỗi rất dài.

## 8. Nếu dùng set hoặc hash map láng giềng thì sao?

Thay vì:

```python
adj_list = {"A": ["B", "C"], "B": ["A"], "C": ["A"]}
```

Ta có thể lưu:

```python
adj_set = {"A": {"B", "C"}, "B": {"A"}, "C": {"A"}}
```

Hoặc cho đồ thị có trọng số:

```python
adj_map = {
    "A": {"B": 5, "C": 2},
    "B": {"A": 5},
    "C": {"A": 2},
}
```

Khi dùng set/map, với các giả định băm tốt và các khóa ổn định:

- Kiểm tra `v in adj[u]` thường `O(1)` **kỳ vọng**.
- Thêm hoặc xóa láng giềng đã biết cũng thường `O(1)` **kỳ vọng/phân bổ**.
- Duyệt hết các láng giềng vẫn cần `O(d(u))` lần thăm mục.
- Bộ nhớ vẫn `O(n+m)` về số bản ghi, nhưng có thể nhiều overhead hơn list.

**Đánh đổi:** set/map thông thường không giữ **nhiều cạnh song song** cùng một cặp đỉnh. Nếu cần đa đồ thị, có thể dùng `adj[u][v]` là một danh sách ID cạnh, hoặc kết hợp `edge_id -> edge_record` với chỉ mục kề; phải cập nhật mọi chỉ mục khi thêm/xóa liên kết.

Một lưu ý nữa: **danh sách kề không bắt buộc giữ khóa theo thứ tự tăng**. List có thể phản ánh thứ tự chèn, set/map có quy tắc duyệt riêng theo ngôn ngữ và thư viện. Nếu thuật toán yêu cầu láng giềng được thăm theo thứ tự, cần sắp xếp hoặc dùng cấu trúc duy trì thứ tự, phát sinh chi phí bổ sung.

## 9. Python: lớp đồ thị dùng danh sách kề thực sự

Ví dụ dưới đây dùng `dict` ánh xạ **ID đỉnh** sang một **list các cặp `(neighbor,weight)`**. Đồ thị có thể có hướng hoặc vô hướng, cho phép trọng số bất kỳ theo dữ liệu đầu vào và khuyên, nhưng là **đồ thị đơn**: mỗi cặp đầu mút chỉ có tối đa một liên kết theo chiều tương ứng.

Để dễ hiểu bất biến, **khuyên vô hướng chỉ xuất hiện một mục** trong danh sách của đỉnh và phương thức `bac` cộng thêm 1 để tính đủ hai đầu mút. Số cạnh/cung `m` được lưu bằng bộ đếm riêng; xóa một cạnh giảm bộ đếm đúng 1.

```python
from collections import deque


class DanhSachKe:
    def __init__(self, co_huong=False):
        self.co_huong = co_huong
        self.ke = {}         # vertex_id -> [(neighbor, weight), ...]
        self.so_canh = 0      # Số cạnh vô hướng hoặc số cung có hướng

    def them_dinh(self, ma: str):
        if ma in self.ke:
            raise ValueError("Đỉnh đã tồn tại")
        self.ke[ma] = []     # Đỉnh cô lập vẫn có danh sách rỗng

    def _vi_tri(self, u: str, v: str):
        # Trả vị trí mục u -> v, hoặc None nếu không tìm thấy.
        for i, (dich, _) in enumerate(self.ke[u]):
            if dich == v:
                return i
        return None

    def co_canh(self, u: str, v: str):
        if u not in self.ke or v not in self.ke:
            raise KeyError("Đỉnh không tồn tại")
        return self._vi_tri(u, v) is not None

    def them_canh(self, u: str, v: str, trong_so=1):
        if u not in self.ke or v not in self.ke:
            raise KeyError("Hai đầu mút phải tồn tại")
        if self._vi_tri(u, v) is not None:
            raise ValueError("Liên kết đã tồn tại")

        self.ke[u].append((v, trong_so))
        if not self.co_huong and u != v:
            self.ke[v].append((u, trong_so))
        self.so_canh += 1

    def xoa_canh(self, u: str, v: str):
        if u not in self.ke or v not in self.ke:
            raise KeyError("Đỉnh không tồn tại")
        i = self._vi_tri(u, v)
        if i is None:
            raise KeyError("Không có liên kết")

        self.ke[u].pop(i)
        if not self.co_huong and u != v:
            j = self._vi_tri(v, u)
            if j is None:
                raise RuntimeError("Mất bất biến đối xứng")
            self.ke[v].pop(j)
        self.so_canh -= 1

    def bac(self, u: str):
        if self.co_huong:
            raise ValueError("Dùng bac_ra/bac_vao cho đồ thị có hướng")
        # Một khuyên u--u chỉ được lưu một mục nhưng đóng góp bậc 2.
        return len(self.ke[u]) + (self._vi_tri(u, u) is not None)

    def bac_ra(self, u: str):
        if not self.co_huong:
            raise ValueError("Đồ thị vô hướng")
        return len(self.ke[u])

    def bac_vao(self, v: str):
        if not self.co_huong:
            raise ValueError("Đồ thị vô hướng")
        if v not in self.ke:
            raise KeyError(v)
        return sum(1 for ds in self.ke.values()
                   for dich, _ in ds if dich == v)

    def bfs(self, bat_dau: str):
        if bat_dau not in self.ke:
            raise KeyError(bat_dau)
        da_tham = {bat_dau}
        hang_doi = deque([bat_dau])
        thu_tu = []
        while hang_doi:
            u = hang_doi.popleft()
            thu_tu.append(u)
            for v, _ in self.ke[u]:
                if v not in da_tham:
                    da_tham.add(v)    # Đánh dấu khi thêm vào queue
                    hang_doi.append(v)
        return thu_tu


# Ví dụ vô hướng, không cần dùng trọng số để tìm khả năng tới được.
g = DanhSachKe()
for dinh in "ABCDE":
    g.them_dinh(dinh)

for u, v in [("A", "B"), ("A", "C"), ("B", "C"), ("C", "D")]:
    g.them_canh(u, v)

print(g.ke["C"])         # [('A', 1), ('B', 1), ('D', 1)]
print(g.ke["E"])         # []: đỉnh cô lập
print(g.so_canh)          # 4
print([g.bac(v) for v in "ABCDE"])  # [2, 2, 3, 1, 0]
print(sum(g.bac(v) for v in "ABCDE"))  # 8 = 2 * 4

g.them_canh("B", "B", 0) # Khuyên vô hướng trọng số 0
print(g.bac("B"))       # 4: A, C, khuyên đóng góp 2
print(sum(g.bac(v) for v in "ABCDE"))  # 10 = 2 * 5

g.xoa_canh("A", "C")
print(g.so_canh)        # 4: đã bỏ một cạnh
print(g.co_canh("C", "A"))  # False: hai phía đã được cập nhật
print(g.bfs("A"))       # ['A', 'B', 'C', 'D']
print(g.bfs("E"))       # ['E']


# Ví dụ có hướng: lưu cung đi ra, không tự thêm cung ngược.
h = DanhSachKe(co_huong=True)
for dinh in "ABCD":
    h.them_dinh(dinh)
for u, v, w in [
    ("A", "B", 0), ("A", "C", 3),
    ("C", "B", 2), ("C", "D", 4),
]:
    h.them_canh(u, v, w)

print(h.ke["A"])        # [('B', 0), ('C', 3)]
print(h.ke["B"])        # []
print(h.bac_ra("C"))    # 2
print(h.bac_vao("B"))   # 2
print(h.bfs("B"))       # ['B']: B không có cung đi ra
print(h.bfs("A"))       # ['A', 'B', 'C', 'D']
```

**Phân tích ví dụ:** `_vi_tri(u,v)` quét list `ke[u]` nên tốn `O(d(u))` trong trường hợp xấu. Vì `them_canh` phải kiểm tra trùng, một lần thêm không được bảo đảm `O(1)`, dù các lệnh `append` riêng lẻ có chi phí phân bổ hằng số. `bac` vô hướng quét tìm khuyên trong cách cài đặt này, nên cũng có thể là `O(d(u))`; nếu duy trì bộ đếm khuyên hoặc dùng hai mục kề cho khuyên, có thể truy vấn bậc trong `O(1)`.

Đối với đồ thị có hướng, `bac_ra(u)` lấy `len` của list nên `O(1)`; `bac_vao(v)` phải duyệt **mọi danh sách** nên `O(n+m)`. Nếu thường xuyên hỏi bậc vào, lưu thêm mảng/từ điển đếm bậc vào và cập nhật khi thêm/xóa cung là lựa chọn hiệu quả hơn.

Lớp minh họa **chưa** có phương thức xóa đỉnh, cập nhật trọng số, đa đồ thị hay cơ chế đồng bộ nhiều luồng. Những chức năng ấy cần có bất biến và chính sách riêng; không thể tùy tiện xóa khóa `ke[u]` mà bỏ lại liên kết đến `u` ở những danh sách khác.

## 10. Vì sao BFS/DFS dùng danh sách kề có O(n+m)?

**BFS (Breadth-First Search)** duyệt theo chiều rộng bằng queue; **DFS (Depth-First Search)** duyệt theo chiều sâu bằng stack hoặc đệ quy. Khi áp dụng với danh sách kề, ta không cần quét những cặp đỉnh không liên kết.

Trong một lần duyệt toàn bộ đồ thị:

1. Khởi tạo tập/đánh dấu đã thăm và xét từng đỉnh tốn `O(n)`.
2. Mỗi đỉnh được đưa vào queue/stack và xử lý một số lần hằng định nếu đánh dấu đúng lúc.
3. Mỗi mục kề được đọc một số lần hằng định. Có `m` mục kề ở đồ thị có hướng, hoặc tối đa `2m` mục ở đồ thị vô hướng.

Vì vậy:

\[
T_{\text{BFS/DFS với danh sách kề}}=O(n+m).
\]

**Điều kiện:** mô hình coi việc xem một mục kề và đánh dấu/tra cứu ID là `O(1)` (thường dùng chỉ số nguyên, mảng đánh dấu hoặc hash set có thời gian kỳ vọng phù hợp).

Với `bfs(start)` chỉ thăm các đỉnh **có thể tới được** từ `start`, chi phí có thể nhỏ hơn `O(n+m)` theo kích thước toàn đồ thị. Nếu gọi BFS cho **tất cả thành phần** trong đồ thị vô hướng, phải duyệt các đỉnh chưa thăm, gồm cả đỉnh cô lập, để bao phủ toàn bộ `V`.

**Thứ tự đánh dấu trong BFS:** đánh dấu ngay khi **đưa đỉnh vào queue**, không đợi đến lúc lấy ra. Nếu nhiều đỉnh cùng dẫn đến một láng giềng, cách đánh dấu muộn có thể đưa cùng một đỉnh vào queue nhiều lần, làm mất tính đơn giản của cận hiệu năng và gây xử lý thừa.

### So sánh với ma trận kề

Trên ma trận kề `n×n`, để biết láng giềng của một đỉnh phải quét **cả hàng `n` ô**. Nếu duyệt toàn bộ `n` đỉnh, chi phí là `O(n^2)`, kể cả khi đồ thị chỉ có `m=O(n)` cạnh.

Ví dụ `n=10.000, m=20.000`: danh sách kề đọc số mục tỷ lệ với vài chục nghìn liên kết, còn một vòng duyệt tất cả hàng của ma trận đặc có thể phải xét **100 triệu ô**. Đây là lợi thế quan trọng của danh sách kề với đồ thị **thưa**.

## 11. Đỉnh cô lập, xóa đỉnh và chỉ số ID

Các đỉnh thường có ID ngoài ứng dụng, ví dụ `"student-314"` hoặc `"course-CS101"`. Ta có hai cách phổ biến:

**Dùng ID trực tiếp làm khóa dictionary**:

```python
ke = {
    "course-CS101": ["course-CS102"],
    "course-CS102": [],
    "course-MATH": [],  # Đỉnh cô lập vẫn được lưu
}
```

**Nén ID thành số nguyên** để dùng vector/list `adj[0],...,adj[n-1]`:

```text
"course-CS101" -> 0
"course-CS102" -> 1
"course-MATH"  -> 2

adj[0] = [1]
adj[1] = []
adj[2] = []
```

Cách dùng chỉ số nguyên thường thuận tiện khi cần mảng `visited`, `distance`, `parent` cho BFS/DFS. Đổi lại, phải quản lý **ánh xạ ID ↔ chỉ số** và tránh thay đổi chỉ số mà chưa cập nhật các liên kết tương ứng.

**Xóa một đỉnh `u`:** phải có chính sách nhất quán:

- Với đồ thị vô hướng, xóa mọi cạnh nối tới `u` trong danh sách kề của các láng giềng.
- Với đồ thị có hướng, xóa mọi cung **đi ra từ u** và mọi cung **đi vào u**, kể cả những cung nằm trong danh sách kề của đỉnh khác.
- Nếu xóa đỉnh ở vị trí `i` rồi nén mảng chỉ số, mọi chỉ số lớn hơn `i` có thể thay đổi; phải cập nhật toàn bộ tham chiếu hoặc thiết kế dùng chỉ số ổn định.

Không được chỉ xóa `adj[u]` rồi để những danh sách khác chứa ID `u` đã không còn hợp lệ. Trong một cấu trúc có nhiều chỉ mục kề, quá trình cập nhật cũng phải giữ chúng đồng bộ.

## 12. Khi nào danh sách kề là lựa chọn phù hợp?

| Yêu cầu | Danh sách kề | Ma trận kề đặc |
| --- | --- | --- |
| Bộ nhớ khi đồ thị thưa | **`O(n+m)`**, ít mục không cần thiết | `O(n^2)`, có nhiều ô trống |
| Lấy tất cả láng giềng của u | **`O(d(u))`** | `O(n)` để quét hàng |
| Kiểm tra u có nối v không | `O(d(u))` với list; `O(1)` kỳ vọng với set/map | **`O(1)`** theo chỉ số |
| BFS/DFS toàn bộ đồ thị | **`O(n+m)`** | `O(n^2)` |
| Dữ liệu cập nhật thường xuyên | Thường linh hoạt, tùy loại list/map và chính sách trùng | Thêm/xóa đỉnh có thể tốn nhiều thao tác hàng/cột |
| Đồ thị rất dày | `m=\Theta(n^2)`, bộ nhớ cũng có thể lên `\Theta(n^2)` | Có thể tận dụng truy cập ô trực tiếp |
| Cho phép cạnh song song | Có thể giữ từng mục kèm edge ID | Phải đổi ô Boolean thành số lượng/danh sách ID |

**Gợi ý chọn cấu trúc:** với đồ thị phụ thuộc học phần, mạng quan hệ người dùng, hệ thống giao thông thưa hoặc bài toán thường duyệt BFS/DFS, danh sách kề là lựa chọn phổ biến. Với đồ thị dày, tập đỉnh tương đối cố định và bài toán liên tục hỏi **“có cạnh u–v không?”**, ma trận kề có thể phù hợp hơn.

Đừng chỉ so sánh một cận đơn lẻ. Cần xét **tỷ lệ số cạnh trên số đỉnh**, thao tác được gọi thường xuyên, cách biểu diễn trọng số/đa cạnh, chi phí cấp phát và yêu cầu giữ ID ổn định.

## 13. Những lỗi thường gặp khi cài đặt

1. **Bỏ quên đỉnh cô lập:** chỉ tạo `adj[u]` cho đỉnh xuất hiện trong cạnh khiến `n` bị đếm thiếu.
2. **Chỉ ghi một chiều trong đồ thị vô hướng:** thiếu mục đối ứng làm sai kết quả tìm đường hoặc đếm bậc.
3. **Tự thêm chiều ngược trong đồ thị có hướng:** làm xuất hiện cung không tồn tại trong dữ liệu.
4. **Nhầm số mục kề với số cạnh:** vô hướng thường có hai mục kề trên mỗi cạnh.
5. **Đếm khuyên vô hướng sai:** nếu khuyên chỉ lưu một mục, `len(adj[u])` chưa phải bậc theo quy ước chuẩn.
6. **Tin rằng `add_edge` luôn `O(1)`:** kiểm tra trùng khóa trong một list có thể cần `O(d(u))`.
7. **Tin rằng kiểm tra hai đỉnh kề nhau là `O(1)` với mọi danh sách kề:** điều này phụ thuộc list hay set/map bên trong.
8. **Dùng `if weight` để kiểm tra cạnh:** trọng số 0 hợp lệ nên có thể gây kết quả sai.
9. **Dùng set/map láng giềng cho đa đồ thị mà không mở rộng:** các cạnh song song bị gộp, mất edge ID/trọng số.
10. **Xóa đỉnh nhưng không xóa mọi cung/cạnh liên quan:** để lại liên kết mồ côi.
11. **Không kiểm soát thứ tự duyệt:** BFS/DFS vẫn đúng về khả năng tới được, nhưng thứ tự trả về có thể khác kỳ vọng.
12. **Đánh dấu visited quá muộn:** có thể đưa cùng đỉnh vào queue nhiều lần khi nhiều đường dẫn đến nó.

## 14. Tự kiểm tra

**Câu 1.** Đồ thị vô hướng có `V={A,B,C,D,E}` và bốn cạnh `{A,B},{A,C},{B,C},{C,D}`. Danh sách kề của C là gì? Đỉnh nào cô lập?

**Đáp án:** `adj[C]=[A,B,D]` (thứ tự có thể khác). E cô lập nên `adj[E]=[]` nhưng E vẫn thuộc tập đỉnh.

**Câu 2.** Đồ thị vô hướng không có khuyên có `m=25` cạnh. Tổng cộng có bao nhiêu mục kề trong cách lưu hai đầu mút? Tổng bậc là bao nhiêu?

**Đáp án:** Có `2m=50` mục kề và tổng bậc là 50.

**Câu 3.** Đồ thị có hướng có `A→B`, `A→C`, `C→B`. Nếu chỉ lưu cung đi ra, `adj[A]`, `adj[B]` là gì? B có phải đỉnh cô lập không?

**Đáp án:** `adj[A]=[B,C]`, `adj[B]=[]`. B **không cô lập** vì có hai cung đi vào, dù bậc ra bằng 0.

**Câu 4.** Nếu một đỉnh `u` có `d(u)=1000` mục kề trong list, kiểm tra `u` có nối `v` không có chi phí xấu nhất nào? Nếu dùng set thì sao?

**Đáp án:** List có thể phải kiểm tra 1000 mục, tổng quát `O(d(u))`. Set hashable có chi phí **`O(1)` kỳ vọng** khi hàm băm phân bố phù hợp, không phải bảo đảm cho mọi trường hợp.

**Câu 5.** Vì sao nói đồ thị vô hướng có `n=10.000`, `m=20.000` phù hợp với danh sách kề về bộ nhớ hơn ma trận đặc?

**Đáp án:** Danh sách kề có số mục tỷ lệ `n+2m`, còn ma trận dành `n^2=100.000.000` ô cho mọi cặp đỉnh kể cả khi không có cạnh.

**Câu 6.** Khi lưu khuyên vô hướng `B—B` bằng **một mục** trong `adj[B]`, khuyên đó phải đóng góp bao nhiêu vào `deg(B)`?

**Đáp án:** Đóng góp **2** vào bậc, dù chỉ có một mục lưu; có thể tính `deg(B)=len(adj[B])+so_khuyen(B)` theo quy ước một mục/khuyên.

**Câu 7.** Vì sao BFS duyệt toàn bộ đồ thị bằng danh sách kề có cận `O(n+m)`, còn ma trận kề đặc thường là `O(n^2)`?

**Đáp án:** Danh sách kề chỉ duyệt các mục tương ứng liên kết đang có và xét mỗi đỉnh một lần; ma trận phải kiểm tra cả `n` ô trong từng hàng, gồm cả những ô vắng cạnh.

**Câu 8.** Một đồ thị có hướng chỉ lưu `out[u]`. Muốn tính `indeg(v)` mà không có chỉ mục bổ sung phải làm gì, tốn bao nhiêu?

**Đáp án:** Duyệt các danh sách cung đi ra của mọi đỉnh và đếm cung có đích `v`, tốn `O(n+m)`. Có thể lưu bộ đếm/chỉ mục đi vào nếu cần truy vấn thường xuyên.

**Câu 9.** Hai tuyến đường A–B có hai trọng số khác nhau, nhưng `adj[A]` được lưu thành `{"B": 5}`. Tại sao thêm tuyến thứ hai bằng `adj[A]["B"]=9` gây mất dữ liệu?

**Đáp án:** Một khóa láng giềng chỉ giữ một giá trị; giá 9 sẽ ghi đè giá 5. Với đa đồ thị cần lưu nhiều liên kết kèm ID riêng.

**Câu 10.** Khi xóa đỉnh C trong đồ thị có hướng, vì sao chỉ xóa `adj[C]` là chưa đủ?

**Đáp án:** Nó chỉ xóa các cung đi ra từ C. Các cung đi vào C còn nằm trong danh sách của những nguồn khác; phải xóa chúng để không còn liên kết đến một đỉnh không tồn tại.

**Ghi nhớ:** **Danh sách kề lưu các liên kết thực thay vì mọi cặp đỉnh**, nên bộ nhớ chuẩn là **`\Theta(n+m)`**: đồ thị có hướng có `m` mục kề, đồ thị vô hướng thường có `2m` mục. Duyệt láng giềng phụ thuộc **bậc của đỉnh**, còn BFS/DFS toàn bộ đồ thị thường tốn **`O(n+m)`**. Kiểm tra hoặc xóa cạnh có thể là `O(d(u))` với list nhưng `O(1)` kỳ vọng với set/map; phải nêu rõ cách cài đặt, xử lý khuyên/cạnh song song, đỉnh cô lập và bất biến cập nhật trước khi chọn cấu trúc.

# Danh sách cạnh và cấu trúc bản ghi của cạnh

## 1. Vì sao đôi khi cần lưu từng cạnh thành một bản ghi riêng?

Giả sử hệ thống giao thông phải lưu thông tin các tuyến nối ga A và ga B. Có hai tuyến khác nhau: tuyến số 7 dài 4 km, tuyến số 12 dài 7 km. Một bảng chỉ cho biết `A` có kề `B` không sẽ không đủ để quản lý từng tuyến. Ta cần biết **mỗi liên kết là đối tượng nào**, nó nối những đỉnh nào và mang những thuộc tính gì.

**Danh sách cạnh (edge list)** là biểu diễn đồ thị bằng một tập hợp có thể duyệt tuần tự các **bản ghi cạnh**. Mỗi bản ghi chứa tối thiểu **hai đầu mút**; đối với đồ thị có hướng, chúng được hiểu là **nguồn** và **đích**. Bản ghi có thể mang thêm **trọng số**, **định danh cạnh** và những thuộc tính nghiệp vụ.

Ví dụ:

```text
Đỉnh: A, B, C, D

Danh sách cạnh vô hướng:
edge_id   đầu mút u   đầu mút v   độ dài
0         A           B           4 km
1         A           B           7 km
2         B           C           2 km
3         C           C           0 km

D vẫn là một đỉnh dù không xuất hiện trong cạnh nào.
```

Danh sách này giữ **hai cạnh A–B riêng biệt** và một **khuyên C–C** mà không phải gộp dữ liệu. Nó cũng rất gần với cách các tập dữ liệu, tệp CSV hoặc bảng cơ sở dữ liệu lưu từng liên kết thành một dòng.

Bài học tập trung vào **cấu trúc của bản ghi cạnh**, **những bất biến phải giữ**, **chi phí thao tác theo số đỉnh `n` và số cạnh `m`**, và cách chuyển danh sách cạnh sang biểu diễn kề để chạy các thuật toán duyệt.

## 2. Tập đỉnh và tập cạnh: cần tách hai nguồn dữ liệu

Gọi `G=(V,E)`, trong đó `n=|V|` là số đỉnh và `m=|E|` là số **liên kết thực tế**.

- Trong **đồ thị vô hướng**, cạnh `{u,v}` không phân biệt thứ tự đầu mút; `{A,B}` và `{B,A}` là cùng **cặp đầu mút**.
- Trong **đồ thị có hướng**, cung `(u,v)` có **nguồn `u` và đích `v`**. Cung `A→B` khác với cung `B→A`.
- **Khuyên** nối một đỉnh với chính nó: `u=v`.
- Trong **đa đồ thị**, nhiều cạnh hoặc cung có thể trùng cặp đầu mút nhưng là **những liên kết độc lập**.

Nếu chỉ lưu danh sách cạnh, một đỉnh không có liên kết sẽ không xuất hiện ở đâu cả. Vì vậy, biểu diễn đầy đủ nên có **cả danh sách/tập đỉnh lẫn danh sách cạnh**:

```text
V = {A, B, C, D}
E = [(A,B), (B,C)]

D là đỉnh cô lập: D thuộc V nhưng không có trong E.
```

Khi đọc tệp chỉ chứa cạnh, **không được mặc định** toàn bộ đỉnh đều đã xuất hiện trong các dòng. Nếu bài toán có đỉnh cô lập, người tạo dữ liệu phải cung cấp tập `V` hoặc một cách khác để xác định đầy đủ các đỉnh.

Trong phân tích thuật toán, danh sách cạnh thường được biểu diễn bằng `list` hoặc mảng có `m` bản ghi. Giữ thêm tập đỉnh chiếm `O(n)` mục; vì thế tổng bộ nhớ biểu diễn tiêu chuẩn là **`O(n+m)`**.

## 3. Bản ghi cạnh nên chứa những trường nào?

Một cấu trúc bản ghi rõ ràng có thể là:

| Trường | Ý nghĩa | Ví dụ | Có bắt buộc? |
| --- | --- | --- | --- |
| `edge_id` | ID duy nhất của **liên kết** | `"route-07"` | Cần nếu quản lý đa cạnh hoặc sửa/xóa đúng một liên kết |
| `u` | Đỉnh đầu; với cung là **nguồn** | `"A"` | Có |
| `v` | Đỉnh cuối; với cung là **đích** | `"B"` | Có |
| `weight` | Trọng số: khoảng cách, thời gian, chi phí... | `4` | Chỉ cần nếu bài toán có trọng số |
| `label` | Tên/loại liên kết hiển thị | `"Tuyến 7"` | Không |
| `attributes` | Những thông tin bổ sung theo nghiệp vụ | `{"operator": "X"}` | Không |

Không phải bài toán nào cũng cần mọi trường. Ví dụ thuật toán chỉ kiểm tra hai đỉnh có nối nhau không có thể dùng bản ghi `(u,v)`. Nhưng nếu hai đường tàu A–B có trọng số khác nhau, **cặp đầu mút không còn đủ để xác định một bản ghi duy nhất**.

### Định danh cạnh khác định danh đỉnh

`vertex_id` định danh **đối tượng là đỉnh**; `edge_id` định danh **một liên kết cụ thể**. Hai cạnh `e0=(A,B,4)` và `e1=(A,B,7)` có đầu mút giống nhau nhưng ID khác nhau.

Định danh cạnh hữu ích khi cần trả lời:

- “Xóa **tuyến e0** nhưng giữ **tuyến e1**.”
- “Cập nhật giá vé của chuyến có `edge_id=123`.”
- “Hiển thị chi tiết tuyến đã được thuật toán chọn.”

Nếu edge ID được cấp phát tăng dần, một chính sách thường dùng là **không tái sử dụng ID đã xóa** trong vòng đời dữ liệu, để tham chiếu cũ không vô tình trỏ sang một cạnh mới.

### Trọng số không phải ID

Hai cạnh khác nhau có thể cùng trọng số; một cạnh có thể đổi trọng số mà **không đổi danh tính**. Vì vậy, không nên ghép trọng số vào khóa duy nhất của cạnh nếu yêu cầu nghiệp vụ cho phép cập nhật trọng số độc lập.

Với đồ thị không trọng số, có thể bỏ trường `weight`, hoặc quy ước mỗi cạnh có chi phí `1` khi **đếm số bước**. Trọng số `0` của một liên kết có trọng số là giá trị hợp lệ, **không đồng nghĩa với không có cạnh**.

## 4. Vô hướng và có hướng: cách hiểu `u, v` quyết định tính đúng

Xét hai bản ghi:

```text
e0: u=A, v=B, weight=5
e1: u=B, v=A, weight=9
```

**Trong đồ thị có hướng**, `e0` là cung A→B và `e1` là cung B→A. Chúng khác chiều, có thể có trọng số khác nhau; không được tự đổi chỗ `u,v` khi ghi dữ liệu.

**Trong đồ thị vô hướng**, `e0` và `e1` cùng nối cặp đầu mút A–B. Có hai trường hợp:

1. Nếu hệ thống là **đồ thị đơn**, cặp đầu mút đã tồn tại, nên bản ghi thứ hai là liên kết trùng và phải được từ chối hoặc xử lý bằng chính sách cập nhật.
2. Nếu hệ thống là **đa đồ thị**, cả `e0` và `e1` có thể được giữ như **hai cạnh song song**.

Vì vậy, **một danh sách cạnh không tự cho biết quy tắc vô hướng hay có hướng**; nó phải đi kèm thông tin mô hình. Khi viết API, nên cấu hình `directed` ở mức đồ thị hoặc ghi rõ loại liên kết cho từng bản ghi nếu thực sự xây dựng đồ thị hỗn hợp.

### Cách chuẩn hóa cặp đầu mút trong đồ thị vô hướng đơn

Nếu ID đỉnh có thứ tự so sánh ổn định, có thể chuẩn hóa cặp `(u,v)` thành `(min(u,v),max(u,v))` để kiểm tra trùng:

```python
def khoa_canh_don_vo_huong(u: str, v: str):
    return (u, v) if u <= v else (v, u)


assert khoa_canh_don_vo_huong("A", "B") == (
    khoa_canh_don_vo_huong("B", "A")
)
```

Cách này **chỉ định danh cặp đầu mút**, không định danh hai cạnh song song trong đa đồ thị. Nếu ID không so sánh được bằng `<=`, phải dùng một quy tắc chuẩn hóa khác, không tự gọi `min/max` trên kiểu không có thứ tự.

## 5. Khuyên và cạnh song song trong danh sách cạnh

Với danh sách cạnh, **khuyên chỉ là một bản ghi có `u==v`**. Nó không bị mất như khi một biểu diễn khác dùng tập hai đầu mút rồi gộp phần tử trùng.

```text
e0 = (A, B, 4)
e1 = (A, B, 7)   Hai cạnh song song khác ID
e2 = (B, B, 2)   Một khuyên tại B
```

Số cạnh là `m=3`, dù chỉ có hai cặp đầu mút phân biệt. Khi duyệt danh sách cạnh, ta gặp **mỗi edge ID một lần**, nên dễ đếm đúng số liên kết, dễ xóa một cạnh có ID cụ thể và dễ lưu nhiều thuộc tính khác nhau.

Tuy nhiên, phải phân biệt **số bản ghi cạnh** và **bậc đỉnh**:

- Trong đồ thị **vô hướng**, một cạnh thường đóng góp 1 vào bậc ở mỗi đầu mút; khuyên đóng góp **2 vào bậc của chính đỉnh đó**.
- Trong đồ thị **có hướng**, cung `u→v` đóng góp 1 cho bậc ra của `u` và 1 cho bậc vào của `v`; cung khuyên `u→u` đóng góp 1 cho mỗi loại bậc của `u`.

Hai đẳng thức quan trọng:

\[
\sum_{v\in V}\deg(v)=2m
\quad\text{(vô hướng),}
\]

\[
\sum_{v\in V}\operatorname{indeg}(v)
=\sum_{v\in V}\operatorname{outdeg}(v)=m
\quad\text{(có hướng).}
\]

Trong trường hợp vô hướng, danh sách cạnh giữ **một bản ghi cho mỗi cạnh**, dù khi chuyển sang danh sách kề người ta có thể tạo **hai mục kề cho mỗi cạnh**, kể cả khuyên theo quy ước đếm bậc.

## 6. Vì sao danh sách cạnh phù hợp với dữ liệu đầu vào và lưu trữ?

Một danh sách cạnh rất gần với bảng dữ liệu:

```csv
edge_id,source,target,weight
100,A,B,4
101,A,B,7
102,B,C,2
103,C,C,0
```

Mỗi dòng là một liên kết, nên phù hợp cho:

- **Nhập/xuất:** đọc dữ liệu theo dòng, lưu lại ID và thuộc tính gốc.
- **Lưu trữ theo bảng:** một hàng cho mỗi cạnh/cung; có thể tạo chỉ mục theo `edge_id`, `source` hoặc `target`.
- **Quét toàn bộ liên kết:** tính tổng trọng số, lọc cạnh theo nhãn, hoặc xét từng cạnh của thuật toán.
- **Đa đồ thị:** giữ các cạnh song song mà không phải gộp theo cặp đầu mút.

Trong cơ sở dữ liệu, **khóa chính** thường là `edge_id`, còn `source` và `target` là tham chiếu đến bảng đỉnh. Để dữ liệu có nghĩa:

1. Mỗi `edge_id` phải duy nhất.
2. Mỗi `source` và `target` phải chỉ tới đỉnh tồn tại.
3. Các ràng buộc “cho phép khuyên” và “cho phép cạnh song song” phải được thực thi rõ ràng.
4. Nếu lưu trọng số, phải có đơn vị và miền giá trị phù hợp với bài toán.

Ví dụ một trường `weight=5` không cho biết đó là **5 km**, **5 phút** hay **5 đơn vị tiền**. Thông tin đơn vị không nên chỉ tồn tại trong suy đoán của lập trình viên.

## 7. Chi phí theo n và m: ưu điểm và hạn chế

Giả sử bản ghi cạnh có kích thước hằng số, danh sách cạnh được cài bằng **mảng/list** và tập đỉnh được lưu riêng. Khi đó:

| Thao tác | Chi phí điển hình | Vì sao? |
| --- | --- | --- |
| Lưu `n` đỉnh và `m` cạnh | **`O(n+m)` bộ nhớ** | `n` bản ghi đỉnh, `m` bản ghi cạnh |
| Tạo danh sách cạnh từ `m` bản ghi | `O(m)` thời gian | Phải đọc/ghi mỗi cạnh một lần |
| Duyệt toàn bộ cạnh | **`O(m)`** | Mỗi bản ghi được đọc một lần |
| Thêm cạnh đã xác thực đầu mút, không dò trùng | `O(1)` phân bổ | Thêm ở cuối mảng động |
| Thêm cạnh vào **đồ thị đơn**, kiểm tra cặp đầu mút chưa có | `O(m)` nếu chỉ có danh sách cạnh | Phải quét để tìm bản ghi trùng |
| Kiểm tra có cạnh/cung `u→v` không | **`O(m)`** nếu không có chỉ mục | Quét từng bản ghi |
| Lấy tất cả cạnh nối `u,v` | `O(m+r)`, thường viết `O(m)` | Quét `m` cạnh để trả `r\le m` kết quả |
| Liệt kê láng giềng của `u` | **`O(m)`** nếu quét toàn danh sách | Phải xem cạnh có chạm tới `u` không |
| Xóa cạnh theo ID trong một list tuần tự | **`O(m)`** | Tìm ID và dời các phần tử sau vị trí xóa |
| Sắp xếp cạnh theo trọng số | **`O(m\log m)`** | Sắp xếp so sánh |
| Chuyển sang danh sách kề | **`O(n+m)`** | Tạo `n` danh sách, duyệt `m` cạnh |
| Chuyển sang ma trận kề đặc | **`O(n^2+m)`** | Khởi tạo `n^2` ô rồi ghi các liên kết |

Các cận này **không phải đặc tính của mọi thiết kế có tên “danh sách cạnh”**. Nếu lưu thêm `edge_id -> index` bằng hash map, tra cạnh theo ID có thể nhanh hơn về kỳ vọng. Nếu dùng danh sách liên kết và giữ trực tiếp con trỏ đến nút, thao tác xóa nút có chi phí khác. Nếu thêm chỉ mục theo đầu mút, kiểm tra kề có thể nhanh nhưng phải trả thêm **bộ nhớ và chi phí cập nhật chỉ mục**.

### Vì sao BFS/DFS không tự động là O(n+m) trên edge list thuần?

Giả sử BFS đến đỉnh `u` và cần tìm mọi cung đi ra từ `u`. Nếu chỉ có danh sách cạnh tuần tự, chương trình có thể phải **quét cả `m` bản ghi** để lọc những cung có nguồn `u`. Nếu làm thế cho mỗi đỉnh được thăm, tổng có thể tới **`O(nm)`**, cộng chi phí quản lý đỉnh.

Trong khi đó, danh sách kề đã nhóm các liên kết theo đỉnh nguồn nên BFS/DFS thông thường chạy trong **`O(n+m)`** thời gian trên toàn đồ thị. Vì vậy, nếu thường xuyên duyệt từ một đỉnh, hãy **chuyển edge list sang adjacency list một lần** hoặc duy trì một chỉ mục kề.

Đây là đánh đổi cốt lõi: **danh sách cạnh thuận tiện để lưu và quét toàn bộ liên kết; danh sách kề thuận tiện để tìm liên kết xuất phát từ một đỉnh đã biết**.

## 8. Bản ghi bất biến và quy trình cập nhật an toàn

Một cách giảm lỗi là coi một bản ghi cạnh đã được cấp ID là **đối tượng có định danh ổn định**. Khi cần đổi trọng số, thay bản ghi bằng một bản ghi mới **cùng ID**, thay vì tự ý đổi đầu mút của bản ghi mà không cập nhật các chỉ mục liên quan.

Trong Python, `@dataclass(frozen=True)` có thể dùng để minh họa cấu trúc bản ghi:

```python
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Canh:
    edge_id: int
    u: str
    v: str
    weight: float


e = Canh(10, "A", "B", 4)
e_moi = replace(e, weight=5)
print(e)      # Canh(edge_id=10, u='A', v='B', weight=4)
print(e_moi)  # Canh(edge_id=10, u='A', v='B', weight=5)
```

Mã này **chỉ tạo bản ghi mới**, chưa thay bản ghi bên trong một đồ thị thực tế. Muốn cập nhật có hiệu lực, API quản lý đồ thị phải thay `e` bằng `e_moi` tại vị trí đúng và cập nhật những chỉ mục/cache tương ứng nếu có.

`frozen=True` không tự đảm bảo tính bất biến sâu nếu bản ghi chứa các cấu trúc lồng có thể thay đổi. Với `edge_id` nguyên, `u,v` là chuỗi và `weight` là số như ví dụ, các trường định danh và giá trị đơn giản dễ kiểm soát.

## 9. Python: một đồ thị lưu danh sách bản ghi cạnh

Lớp minh họa dưới đây lưu:

- `dinh`: từ điển `vertex_id -> label`, bảo toàn đỉnh cô lập;
- `canh`: **list** các bản ghi `Canh`;
- `next_id`: bộ đếm cấp edge ID không tái sử dụng;
- Cấu hình `co_huong` và `cho_song_song`.

Lớp cho phép khuyên, lưu trọng số hữu hạn (kể cả **0** và số âm), có phương thức tìm theo cặp đầu mút, cập nhật trọng số, xóa đúng một edge ID và chuyển sang danh sách kề. Mã này chỉ nhằm quan sát biểu diễn và chi phí; không cài thuật toán đường đi.

```python
from dataclasses import dataclass, replace
from math import isfinite


@dataclass(frozen=True)
class Canh:
    edge_id: int
    u: str
    v: str
    weight: float


class DoThiDanhSachCanh:
    def __init__(self, co_huong=False, cho_song_song=True):
        self.co_huong = co_huong
        self.cho_song_song = cho_song_song
        self.dinh = {}       # vertex_id -> nhãn hiển thị
        self.canh = []       # Mỗi liên kết là một bản ghi Canh
        self.next_id = 0

    def them_dinh(self, ma: str, nhan: str):
        if ma in self.dinh:
            raise ValueError("Định danh đỉnh đã tồn tại")
        self.dinh[ma] = nhan

    def _kiem_tra_trong_so(self, weight):
        if (isinstance(weight, bool)
                or not isinstance(weight, (int, float))
                or not isfinite(weight)):
            raise ValueError("Trọng số phải là số hữu hạn")

    def _cung_dau_mut(self, e: Canh, u: str, v: str):
        if e.u == u and e.v == v:
            return True
        return not self.co_huong and e.u == v and e.v == u

    def canh_giua(self, u: str, v: str):
        if u not in self.dinh or v not in self.dinh:
            raise KeyError("Đỉnh không tồn tại")
        return [e for e in self.canh if self._cung_dau_mut(e, u, v)]

    def them_canh(self, u: str, v: str, weight=1):
        if u not in self.dinh or v not in self.dinh:
            raise KeyError("Hai đầu mút phải tồn tại")
        self._kiem_tra_trong_so(weight)
        if not self.cho_song_song and self.canh_giua(u, v):
            raise ValueError("Liên kết này đã tồn tại")
        eid = self.next_id
        self.next_id += 1
        self.canh.append(Canh(eid, u, v, weight))
        return eid

    def doi_trong_so(self, eid: int, weight):
        self._kiem_tra_trong_so(weight)
        for i, e in enumerate(self.canh):
            if e.edge_id == eid:
                self.canh[i] = replace(e, weight=weight)
                return
        raise KeyError(eid)

    def xoa_canh(self, eid: int):
        for i, e in enumerate(self.canh):
            if e.edge_id == eid:
                return self.canh.pop(i)
        raise KeyError(eid)

    def tao_danh_sach_ke(self):
        ke = {u: [] for u in self.dinh}  # Giữ cả đỉnh cô lập
        for e in self.canh:
            ke[e.u].append((e.v, e.edge_id, e.weight))
            if not self.co_huong:
                # Khuyên u == v tạo 2 mục cùng tại u.
                ke[e.v].append((e.u, e.edge_id, e.weight))
        return ke


# Đa đồ thị vô hướng: 2 cạnh song song A--B, 1 B--C,
# 1 khuyên C--C; D cô lập.
g = DoThiDanhSachCanh()
for ma in "ABCD":
    g.them_dinh(ma, f"Đỉnh {ma}")

e0 = g.them_canh("A", "B", 4)
e1 = g.them_canh("A", "B", 7)
e2 = g.them_canh("B", "C", 2)
e3 = g.them_canh("C", "C", 0)

print([e.edge_id for e in g.canh_giua("B", "A")])  # [0, 1]
print([e.edge_id for e in g.canh_giua("C", "C")])  # [3]
ke = g.tao_danh_sach_ke()
print(ke["C"])  # [('B', 2, 2), ('C', 3, 0), ('C', 3, 0)]
print([len(ke[u]) for u in "ABCD"])  # [2, 3, 3, 0]
print(sum(len(ds) for ds in ke.values()))  # 8 = 2 * 4 cạnh

g.doi_trong_so(e0, 5)
print([(e.edge_id, e.weight) for e in g.canh_giua("A", "B")])
# [(0, 5), (1, 7)]: đổi trọng số nhưng không đổi ID

g.xoa_canh(e1)
print([e.edge_id for e in g.canh_giua("A", "B")])  # [0]
print([len(g.tao_danh_sach_ke()[u]) for u in "ABCD"])
# [1, 2, 3, 0]: đã xóa đúng một cạnh, còn 3 cạnh

# Đa đồ thị có hướng: chiều ngược là cung khác.
h = DoThiDanhSachCanh(co_huong=True)
for ma in "AB":
    h.them_dinh(ma, ma)
h.them_canh("A", "B", 3)
h.them_canh("B", "A", 8)
h.them_canh("A", "B", 5)
print([e.edge_id for e in h.canh_giua("A", "B")])  # [0, 2]
print([e.edge_id for e in h.canh_giua("B", "A")])  # [1]
print(h.tao_danh_sach_ke()["A"])  # [('B', 0, 3), ('B', 2, 5)]
```

Điểm quan trọng: `e0` và `e1` nối cùng cặp đầu mút nhưng được nhận diện bằng **hai edge ID**. Khi `xoa_canh(e1)`, cạnh `e0` vẫn tồn tại. Với đồ thị có hướng, việc hỏi A→B không tự lấy cả cung B→A.

Phương thức `tao_danh_sach_ke()` tạo **bản sao cấu trúc kề tại thời điểm được gọi**, không phải chỉ mục sống tự đồng bộ. Sau khi sửa/xóa một cạnh ở danh sách cạnh, nếu đã giữ `ke` cũ thì phải **tạo lại** hoặc thiết kế một API cập nhật cả hai cấu trúc.

**Chi phí chính của mã:** `canh_giua`, `doi_trong_so`, `xoa_canh` phải quét danh sách, nên là `O(m)`. Với `cho_song_song=True`, `them_canh` chủ yếu xác thực hai đầu mút và `append`, thường `O(1)` kỳ vọng/phân bổ khi tra cứu ID đỉnh trong dict có hiệu năng phù hợp. Với `cho_song_song=False`, việc kiểm tra trùng phải quét, có thể tốn `O(m)`.

## 10. Chuyển đổi giữa danh sách cạnh, danh sách kề và ma trận kề

### Danh sách cạnh → danh sách kề

Ý tưởng đã được cài bằng `tao_danh_sach_ke()`:

1. Khởi tạo `adj[u]=[]` cho **mọi `u\in V`**, gồm đỉnh cô lập.
2. Với mỗi cạnh/cung `e=(u,v,w)`, thêm một mục `(v,e.id,w)` vào `adj[u]`.
3. Nếu **vô hướng**, thêm một mục đối ứng `(u,e.id,w)` vào `adj[v]`. Với khuyên, hai mục đều nằm tại `u`, nếu dùng quy ước khuyên đóng góp hai mục.

Số thao tác khởi tạo là `O(n)`; mỗi liên kết tạo một hoặc hai mục, tổng **`O(n+m)` thời gian và bộ nhớ**.

### Danh sách kề → danh sách cạnh

Với đồ thị **có hướng** lưu cung đi ra, có thể duyệt tất cả các danh sách và tạo một bản ghi cạnh cho mỗi mục.

Với đồ thị **vô hướng**, mỗi cạnh có thể xuất hiện **hai lần** ở hai đầu. Cần tránh tạo **hai bản ghi cạnh** từ một cạnh. Nếu mỗi mục có `edge_id`, chỉ thêm bản ghi khi gặp một ID chưa xử lý. Nếu chỉ có cặp đỉnh trong đồ thị đơn, có thể chọn một quy tắc như `u < v` để xử lý mỗi cạnh không khuyên một lần và xử lý khuyên riêng.

Với **đa đồ thị**, chỉ khử trùng theo cặp đầu mút là sai: nó sẽ gộp các cạnh song song. Muốn phục hồi chính xác edge list, biểu diễn kề phải giữ **ID hoặc thông tin phân biệt từng liên kết**.

### Danh sách cạnh → ma trận kề

Trước hết tạo ma trận `n×n`, với ô vắng liên kết được ký hiệu đúng cách (chẳng hạn `None`):

```text
for mỗi cạnh e = (u, v, weight):
    matrix[u][v] = weight
    if graph vô hướng:
        matrix[v][u] = weight
```

Nếu có hai cạnh A–B trọng số 4 và 7, lệnh gán vào **một ô** sẽ ghi đè. Cần quyết định có lưu **danh sách edge ID trong ô**, **số lượng cạnh**, hay một **giá trị tổng hợp** phục vụ mục tiêu cụ thể. Một ma trận Boolean chỉ cho biết **có ít nhất một liên kết**, không bảo toàn tính bội.

Chi phí tạo ma trận đặc là **`O(n^2+m)`** thời gian và `O(n^2)` ô, chưa kể các danh sách cạnh nếu lưu kèm. Với đồ thị thưa, đây có thể là đánh đổi lớn.

## 11. Thuật toán nào phù hợp với danh sách cạnh?

### Kruskal: xét các cạnh theo trọng số

Thuật toán **Kruskal** tìm **cây khung nhỏ nhất (minimum spanning tree, MST)** cho đồ thị vô hướng có trọng số và liên thông. Nó cần xét các cạnh theo thứ tự **trọng số tăng dần**:

1. Sắp xếp danh sách cạnh theo trọng số.
2. Dùng cấu trúc **Disjoint Set Union (DSU, union–find)** để theo dõi các thành phần đã nối.
3. Chỉ nhận một cạnh nếu hai đầu mút hiện thuộc **hai thành phần khác nhau**; khi đó hợp nhất hai thành phần.
4. Với đồ thị liên thông, dừng khi chọn đủ `n-1` cạnh; nếu không liên thông, thu được **rừng khung nhỏ nhất (minimum spanning forest)** trên các thành phần.

Ví dụ:

| Cạnh | Trọng số | Khi xét tăng dần |
| --- | ---: | --- |
| `B—C` | 1 | Chọn: nối B và C |
| `A—C` | 2 | Chọn: nối A vào thành phần B–C |
| `A—B` | 4 | Bỏ: sẽ tạo chu trình |
| `B—D` | 5 | Chọn: nối D vào thành phần |
| `C—D` | 8 | Bỏ: sẽ tạo chu trình |

Cây khung chọn ba cạnh cho bốn đỉnh A, B, C, D, tổng trọng số `1+2+5=8`. Nếu còn đỉnh E cô lập, không thể có cây khung nối cả năm đỉnh; thuật toán tạo **rừng khung** và E là một thành phần riêng.

Với cách cài đặt DSU phù hợp, phần sắp xếp thường chi phối: **`O(m\log m)`** thời gian, cộng chi phí khởi tạo DSU cho `n` đỉnh và các thao tác gần hằng số khấu hao trên từng cạnh. Cần lưu tập đỉnh độc lập để khởi tạo DSU cả cho đỉnh cô lập.

### Bellman–Ford: duyệt toàn bộ các cung nhiều lượt

Thuật toán **Bellman–Ford** tính khoảng cách ngắn nhất từ một nguồn trong đồ thị có hướng có trọng số, cho phép **trọng số âm** và có thể phát hiện chu trình âm **tới được từ nguồn**.

Mỗi lượt, thuật toán xét lần lượt các cung `(u,v,w)` và thử **nới lỏng (relax)**:

\[
\text{nếu }dist[u]+w<dist[v]\text{ thì }dist[v]\leftarrow dist[u]+w.
\]

Phải bỏ qua phép nới lỏng nếu `dist[u]` còn là vô cực. Thuật toán chuẩn thực hiện tối đa `n-1` lượt nới lỏng toàn bộ `m` cung, sau đó có thể kiểm tra thêm một lượt để phát hiện cải thiện bất thường do chu trình âm có thể tới được.

Chi phí là **`O(nm)` thời gian**, cộng bộ nhớ khoảng cách `O(n)` ngoài dữ liệu đồ thị. Đây là ví dụ một thuật toán **chủ động quét toàn bộ danh sách cạnh** nên edge list là cách cung cấp dữ liệu tự nhiên.

Đối với đồ thị **vô hướng có cạnh âm**, nếu đường đi được phép đi qua cạnh đó rồi đi ngược lại nhiều lần, nó tạo một vòng lặp có tổng trọng số âm. Cần làm rõ định nghĩa đường đi hợp lệ trước khi áp dụng phát biểu về đường ngắn nhất.

### Khi cần duyệt từ một đỉnh

BFS, DFS và một số thuật toán đường đi cần liên tục tìm tất cả cung/cạnh **kề một đỉnh cụ thể**. Với edge list thuần, mỗi lần tìm phải quét `m` cạnh; chuyển sang danh sách kề giúp truy cập theo nhóm nhanh hơn. Không phải biểu diễn nào cũng tối ưu mọi thuật toán.

## 12. Giữ bất biến khi lưu, cập nhật và xóa cạnh

Một thiết kế đáng tin cậy nên bảo đảm:

**Đỉnh và tham chiếu**

- Mỗi `vertex_id` xác định đúng một đỉnh trong phạm vi đồ thị.
- Mọi `edge.u`, `edge.v` phải trỏ tới **đỉnh đang tồn tại**.
- Đỉnh cô lập vẫn được lưu trong `V`; không suy đoán `V` chỉ từ hai đầu mút cạnh.

**Định danh và hướng**

- Mỗi `edge_id` là duy nhất đối với các liên kết đang tồn tại.
- Với **đồ thị đơn có hướng**, cặp có thứ tự `(u,v)` không được lặp; `(v,u)` là cung khác.
- Với **đồ thị đơn vô hướng**, `(u,v)` và `(v,u)` là cùng cặp đầu mút và phải được kiểm tra trùng như nhau.
- Với **đa đồ thị**, cho phép trùng đầu mút nhưng **không** trùng `edge_id`.
- Khuyên `u=v` có hợp lệ không phải do chính sách mô hình quyết định; nếu cấm thì phải kiểm tra khi chèn.

**Thuộc tính và cập nhật**

- Trọng số, đơn vị và nhãn phải phù hợp nghiệp vụ; `0` là một trọng số hợp lệ nếu mô hình cho phép.
- Thay đổi trọng số không làm đổi `edge_id`; thay đổi đầu mút là **một cập nhật có ảnh hưởng tới cấu trúc kề**, không chỉ là sửa hai trường.
- Xóa cạnh theo `edge_id` chỉ xóa **một** liên kết, không xóa mọi cạnh song song cùng đầu mút.
- Nếu duy trì cả edge list và adjacency list/ma trận, các chỉ mục phải được cập nhật **nhất quán** sau mỗi thao tác.

**Xóa đỉnh:** phải xóa hoặc xử lý toàn bộ cạnh/cung có đầu mút tại đỉnh bị xóa; không để lại bản ghi tham chiếu ID không tồn tại.

Trong hệ thống đồng thời hoặc có lưu trữ lâu dài, những thao tác ghi liên quan nhiều bảng/chỉ mục cần cơ chế đồng bộ hoặc giao dịch để tránh trạng thái cập nhật dở.

## 13. Những lỗi thường gặp

1. **Chỉ lấy hai đầu mút làm ID trong đa đồ thị:** gộp mất những cạnh/cung song song có thông tin khác nhau.
2. **Đổi thứ tự nguồn–đích trong đồ thị có hướng:** biến cung `u→v` thành cung `v→u`.
3. **Xem `(A,B)` và `(B,A)` là hai cạnh vô hướng khác nhau trong đồ thị đơn:** tạo bản ghi trùng logic.
4. **Dùng trọng số làm định danh:** đổi trọng số hoặc có hai cạnh cùng trọng số làm hỏng cách nhận diện liên kết.
5. **Đếm `m` bằng số cặp đỉnh khác nhau:** sai khi có cạnh song song.
6. **Bỏ mất đỉnh cô lập khi nhập dữ liệu:** edge list không tự chứa ID của đỉnh không có cạnh.
7. **Khẳng định tìm cạnh theo đầu mút là `O(1)` trên list thuần:** phải quét `O(m)` nếu không có chỉ mục.
8. **Khẳng định BFS luôn `O(n+m)` dù mỗi lần tìm láng giềng đều quét mọi cạnh:** có thể thành `O(nm)`; nên tạo danh sách kề trước.
9. **Quên xử lý khuyên khi tính bậc:** khuyên vô hướng đóng góp hai đầu mút, không phải một.
10. **Dùng một ô ma trận trọng số cho nhiều cạnh:** ghi đè liên kết khi chuyển từ edge list đa đồ thị.
11. **Xóa bản ghi cạnh nhưng không cập nhật chỉ mục kề:** thuật toán vẫn thấy cạnh không còn tồn tại.
12. **Tái sử dụng edge ID khi còn tham chiếu cũ:** gây nhận nhầm cạnh sau khi xóa/thêm.

## 14. Tự kiểm tra

**Câu 1.** Edge list có hai bản ghi `e0=(A,B,4)` và `e1=(A,B,7)`. Số cạnh là bao nhiêu trong một đa đồ thị vô hướng? Vì sao không thể nhận diện duy nhất một cạnh bằng `(A,B)`?

**Đáp án:** Có **2 cạnh riêng** vì e0 và e1 có ID khác nhau. Cặp `(A,B)` chỉ xác định đầu mút chung, không phân biệt hai liên kết.

**Câu 2.** Đồ thị có `V={A,B,C,D}`, edge list chỉ chứa `(A,B)` và `(B,C)`. Có bao nhiêu đỉnh? Đỉnh nào bị mất nếu chỉ suy ra V từ edge list?

**Đáp án:** Có **4 đỉnh**. D là đỉnh cô lập sẽ bị bỏ sót nếu không lưu tập V riêng.

**Câu 3.** Trong đồ thị có hướng, `(A,B,5)` và `(B,A,5)` là cùng cung không? Trong đồ thị vô hướng đơn thì sao?

**Đáp án:** Có hướng: là **hai cung ngược chiều**. Vô hướng đơn: là **cùng cặp đầu mút**, nên bản ghi thứ hai là trùng logic nếu không cho cạnh song song.

**Câu 4.** Đa đồ thị vô hướng gồm hai cạnh A–B và một khuyên B–B. Tính `deg(A)`, `deg(B)` và tổng bậc.

**Đáp án:** `deg(A)=2`; `deg(B)=4` vì hai cạnh A–B đóng góp 2 và khuyên đóng góp 2. Tổng bậc là `6=2m`, với `m=3`.

**Câu 5.** Danh sách cung của đồ thị có hướng gồm `m=1000` bản ghi, không có chỉ mục theo nguồn. Tìm tất cả láng giềng đi ra từ một đỉnh `u` có chi phí bao nhiêu?

**Đáp án:** Phải quét đến `m` bản ghi để xem `edge.u==u`, nên tốn `O(m)` thời gian.

**Câu 6.** Vì sao không thể kết luận BFS trên edge list thuần luôn là `O(n+m)` nếu phải tìm láng giềng bằng cách quét lại cả danh sách?

**Đáp án:** Nếu có tới `n` đỉnh được thăm, mỗi đỉnh có thể quét `m` cạnh để tìm các láng giềng. Tổng có thể `O(nm)`; chuyển thành adjacency list mất `O(n+m)` và hỗ trợ BFS `O(n+m)`.

**Câu 7.** Muốn chuyển edge list đa đồ thị vô hướng sang danh sách kề mà vẫn giữ được hai tuyến A–B, mỗi mục kề cần giữ gì?

**Đáp án:** Cần giữ **edge ID** (và có thể trọng số hoặc tham chiếu bản ghi) bên cạnh ID láng giềng. Không chỉ dùng một set láng giềng B vì sẽ gộp hai tuyến.

**Câu 8.** Nếu xóa cạnh `e1` mà `e0` cùng nối A–B vẫn tồn tại, thao tác đúng là gì?

**Đáp án:** Xóa **đúng bản ghi `edge_id=e1`** và mọi mục chỉ mục tương ứng; không xóa tất cả cạnh nối A–B.

**Câu 9.** Thuật toán nào dùng trực tiếp việc sắp xếp danh sách cạnh theo trọng số để chọn liên kết tạo cây khung nhỏ nhất?

**Đáp án:** **Kruskal**, kết hợp sắp xếp cạnh với DSU để chỉ nhận cạnh nối hai thành phần khác nhau.

**Câu 10.** Nếu một hệ thống thường xuyên hỏi “u có nối v không?” nhưng đang dùng edge list thuần, lựa chọn thiết kế nào có thể cải thiện thời gian truy vấn?

**Đáp án:** Có thể duy trì **chỉ mục theo cặp đầu mút** hoặc chuyển sang danh sách kề dùng set/map, hay ma trận kề nếu mật độ và bộ nhớ phù hợp. Đổi lại, mọi cập nhật phải giữ chỉ mục nhất quán.

**Ghi nhớ:** **Danh sách cạnh** lưu mỗi cạnh/cung thành **một bản ghi độc lập** với đầu mút, ID và thuộc tính tùy nhu cầu. Nó phù hợp để nhập/xuất, lưu đa đồ thị, duyệt toàn bộ cạnh và những thuật toán như Kruskal hoặc Bellman–Ford; khi giữ cả tập đỉnh, bộ nhớ là **`O(n+m)`**. Nhưng không có chỉ mục kề thì tìm liên kết theo cặp đỉnh hoặc tìm láng giềng thường phải quét **`O(m)`** bản ghi. Chọn đúng cấu trúc bản ghi, giữ **edge ID ổn định**, xác định hướng và xử lý khuyên/cạnh song song nhất quán sẽ giúp chuyển đổi biểu diễn mà không làm mất thông tin.

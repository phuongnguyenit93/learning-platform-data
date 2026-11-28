# Đỉnh, cạnh, cung và lựa chọn định danh cho đối tượng

## 1. Vì sao cần xác định rõ “đỉnh” và “liên kết” trước khi lập trình?

Một mạng xã hội có người dùng và quan hệ kết bạn; hệ thống giao thông có ga và tuyến kết nối; nền tảng học tập có học phần và quan hệ “học phần A là điều kiện tiên quyết của B”. Cả ba có thể được mô hình hóa bằng **đồ thị (graph)**, nhưng **đối tượng nào là đỉnh** và **quan hệ nào là cạnh hoặc cung** phải được xác định trước khi chọn cấu trúc dữ liệu.

Trong mô hình cơ bản, đồ thị gồm:

- **Đỉnh (vertex, số nhiều: vertices; còn gọi là node):** đối tượng hoặc trạng thái mà ta muốn biểu diễn.
- **Cạnh (edge):** liên kết **không có hướng** giữa hai đỉnh, khi quan hệ được xem là hai chiều.
- **Cung (arc, directed edge):** liên kết **có hướng** từ một đỉnh nguồn đến một đỉnh đích.

Các tên gọi “đỉnh”, “cạnh” và “cung” không phải dữ liệu nằm trong máy một cách tự nhiên; chúng là **quyết định mô hình hóa**. Ví dụ, quan hệ “A theo dõi B” nên là cung `A → B`; không thể tự suy ra “B theo dõi A”. Quan hệ “A và B đã kết bạn hai chiều” có thể được biểu diễn bằng một cạnh vô hướng.

Sau bài này, người học cần phân biệt **đối tượng thực tế**, **định danh đỉnh**, **nhãn hiển thị**, **định danh cạnh/cung** và các **bất biến** cần giữ khi lưu đồ thị bằng cấu trúc dữ liệu.

## 2. Định nghĩa toán học: tập đỉnh và tập liên kết

Ký hiệu tập đỉnh là `V`, tập liên kết là `E`. Số đỉnh thường ký hiệu `n=|V|`, số cạnh/cung `m=|E|`.

### Đồ thị vô hướng (undirected graph)

Trong **đồ thị vô hướng đơn** không có khuyên và không có cạnh song song:

\[
G=(V,E),\qquad E\subseteq\big\{\{u,v\}:u,v\in V,\ u\ne v\big\}.
\]

Một cạnh `{u,v}` **không phân biệt thứ tự đầu mút**: `{A,B}={B,A}`. Nếu A kết nối với B thì B cũng kết nối với A theo cùng một cạnh. Với đồ thị đơn, giữa hai đỉnh khác nhau có **tối đa một cạnh**.

Ví dụ:

```text
V = {A, B, C, D}
E = {{A,B}, {A,C}, {B,C}}

       A -------- B
        \        /
         \      /
             C             D

D là đỉnh cô lập: vẫn thuộc V nhưng không có cạnh.
```

### Đồ thị có hướng (directed graph, digraph)

Với đồ thị có hướng đơn, cung là **cặp có thứ tự**:

\[
G=(V,E),\qquad E\subseteq V\times V.
\]

Cung `(A,B)` có nghĩa là `A → B`; nói chung **khác** cung `(B,A)`. Có thể có cả hai cung nếu quan hệ tồn tại ở hai chiều. Ví dụ:

```text
V = {A, B, C, D}
E = {(A,B), (B,A), (B,C)}

A ---> B ---> C       D
  <---
```

`D` vẫn là một đỉnh dù không có cung đi vào hoặc đi ra. Trong một số mô hình đồ thị có hướng, cung `(A,A)` cũng có thể hợp lệ; phải nói rõ chính sách về **khuyên (self-loop)**.

**Chú ý thuật ngữ:** Nhiều tài liệu dùng từ “cạnh có hướng” thay cho “cung”. Ở đây ta dùng **cạnh** cho quan hệ vô hướng, **cung** cho quan hệ có hướng để tránh nhầm khi tính bậc và biểu diễn kề.

## 3. Cạnh vô hướng và cung có hướng khác nhau thế nào?

Hãy xét hai người `An` và `Bình`:

| Ý nghĩa nghiệp vụ | Mô hình | Điều được suy ra |
| --- | --- | --- |
| An và Bình là bạn của nhau | Cạnh `{An,Bình}` | Quan hệ hai chiều |
| An theo dõi Bình | Cung `(An,Bình)` | Không suy ra Bình theo dõi An |
| Bình cũng theo dõi An | Thêm cung `(Bình,An)` | Có hai cung ngược chiều, không phải một cung duy nhất |
| An gửi ba tin nhắn cho Bình | Có thể là ba cung **song song** kèm thời gian | Cần mô hình cho phép nhiều cung cùng đầu mút nếu muốn giữ từng sự kiện |

Nếu hệ thống chỉ cần biết **có quan hệ hay không**, một cạnh/cung duy nhất giữa cùng đầu mút có thể đã đủ. Nếu cần lưu **từng sự kiện độc lập**, chẳng hạn ba chuyến tàu A–B vào ba giờ khác nhau, ta phải cân nhắc **đa đồ thị (multigraph)**.

Như vậy, ngay cả khi tập đỉnh giống nhau, chọn **vô hướng/có hướng**, **đơn/đa đồ thị** và có cho phép **khuyên** hay không sẽ làm thay đổi dữ liệu, thao tác và công thức đếm.

## 4. Khuyên và liên kết song song: những trường hợp cần thống nhất

### Khuyên (self-loop)

Một khuyên nối một đỉnh với chính nó, chẳng hạn cạnh vô hướng `{A,A}` theo cách ghi thông thường hoặc cung `(A,A)`.

- Trong đồ thị vô hướng, khuyên được tính **hai lần vào bậc của đỉnh** theo quy ước bậc chuẩn, vì nó có hai đầu mút cùng nằm ở đỉnh ấy.
- Trong đồ thị có hướng, cung `(A,A)` đóng góp **1 vào bậc ra** và **1 vào bậc vào** của A.
- Một số bài toán không cho phép khuyên; khi đó thao tác thêm liên kết phải từ chối `u=v`.

### Liên kết song song (parallel edges/arcs)

Trong đa đồ thị, có thể có nhiều cạnh `A—B` khác nhau. Ví dụ hai tuyến xe buýt đều nối A và B nhưng có mã tuyến và thời gian hoạt động riêng. Nếu chỉ lưu tập `{A,B}` thì hai tuyến sẽ bị **gộp**.

```text
Đồ thị đơn:         A ----- B        (một cạnh)
Đa đồ thị:          A ===== B        (hai cạnh phân biệt e1, e2)

Hai cung song song: A ==>> B         (e3: 08:00; e4: 09:00)
```

Đồ thị đơn có thể định danh liên kết bằng **cặp đầu mút**; đa đồ thị cần thêm **ID của từng cạnh/cung**, chẳng hạn `edge_id=e1`, `edge_id=e2`. Tùy mục tiêu, trọng số, nhãn tuyến hay thời điểm khởi hành thuộc **thuộc tính của liên kết**, không nhất thiết là một phần ID.

## 5. “Đỉnh” không đồng nghĩa “tên hiển thị của đối tượng”

Một người dùng có thể đổi tên; một nhà ga có thể đổi tên; hai sinh viên có thể cùng tên. Nếu dùng `"Lan"` làm **định danh đỉnh**, ta gặp ít nhất hai nguy cơ:

1. **Trùng tên:** hai đối tượng khác nhau bị coi thành cùng một đỉnh.
2. **Đổi tên:** các cạnh tham chiếu theo tên cũ không còn nối đến đỉnh mong muốn.

Nên tách các khái niệm:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Đối tượng miền nghiệp vụ** | Thực thể ta muốn mô hình hóa | Một người dùng thực tế |
| **Định danh đỉnh (vertex ID)** | Khóa ổn định, duy nhất trong đồ thị | `user-0042` |
| **Nhãn (label)** | Thông tin hiển thị, có thể đổi hoặc trùng | `"Lan"` |
| **Thuộc tính (attributes)** | Dữ liệu phụ như mô tả, tọa độ, trạng thái | `{"city": "Huế"}` |
| **Định danh cạnh/cung (edge ID)** | Phân biệt các liên kết, đặc biệt khi song song | `e-103` |

Một đỉnh thường được mô hình hóa là `vertex_id -> vertex_data`. Các cạnh lưu **ID của hai đỉnh** chứ không sao chép tên hiển thị vào vị trí định danh.

```text
V:
  user-0042 -> {display_name: "Lan"}
  user-0197 -> {display_name: "Lan"}

E vô hướng:
  e-103 -> {u: "user-0042", v: "user-0197", since: 2026}
```

Hai người cùng tên vẫn là hai đỉnh khác nhau. Đổi `display_name` không làm đứt cạnh `e-103`, vì hai đầu mút vẫn trỏ đến **ID ổn định**.

## 6. Tiêu chí chọn định danh đỉnh

Một **định danh tốt** thường có các đặc điểm:

1. **Duy nhất trong phạm vi được xác định:** không gán cùng ID cho hai đỉnh khác nhau.
2. **Ổn định khi đối tượng còn được tham chiếu:** đổi nhãn, địa chỉ hoặc thuộc tính khác không vô tình đổi ID.
3. **Có kiểu và quy tắc so sánh nhất quán:** hai ID giống nhau theo logic cần được so sánh bằng nhau và cho cùng hash nếu dùng làm khóa bảng băm.
4. **Có chính sách về vòng đời:** định danh đã xóa có được tái sử dụng không? Tái sử dụng có thể khiến cạnh hoặc dữ liệu cũ trỏ nhầm sang đối tượng mới.
5. **Thống nhất ranh giới hệ thống:** nếu một đồ thị có nhiều tổ chức, ID chỉ duy nhất *trong mỗi tổ chức* có thể phải kết hợp thêm `tenant_id`.

### Các lựa chọn thường gặp

**Số nguyên tăng dần** (`0,1,2,...`): tiết kiệm bộ nhớ và dễ dùng làm chỉ số mảng. Nhưng nếu xóa một đỉnh, không nên tùy tiện đánh lại số của mọi đỉnh mà không cập nhật toàn bộ các cạnh.

**Chuỗi ID ổn định** (`"user-0042"`, `"station-A5"`): dễ trao đổi giữa các thành phần phần mềm và dễ đọc khi gỡ lỗi. Đổi lại, băm/so sánh chuỗi có chi phí phụ thuộc độ dài khóa và thường dùng thêm bảng ánh xạ ID sang chỉ số nguyên để lưu đồ thị trong mảng.

**ID được sinh độc lập với tên hiển thị** (ví dụ UUID): thuận tiện khi cần cấp phát ID ở nhiều nơi mà không phối hợp số thứ tự trung tâm. ID vẫn phải được kiểm tra/thiết kế phù hợp với yêu cầu duy nhất trong phạm vi ứng dụng; bản thân một định dạng không thay thế ràng buộc dữ liệu.

**Khóa tổ hợp** (`(tenant_id, local_user_id)`): hữu ích khi `local_user_id` chỉ duy nhất trong một tổ chức. Phải dùng kiểu có so sánh và hash nhất quán; không nối các thành phần thành chuỗi một cách mơ hồ.

### Ví dụ khóa tổ hợp

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class DinhID:
    tenant: str
    local_id: int


a = DinhID("truong-A", 17)
b = DinhID("truong-B", 17)
print(a == b)  # False: hai đỉnh thuộc hai phạm vi khác nhau

ten_hien_thi = {a: "Linh", b: "Linh"}
print(len(ten_hien_thi))  # 2: nhãn trùng, ID khác
```

`frozen=True` ngăn sửa trực tiếp các trường của dataclass trong tình huống thông thường, giúp tránh rủi ro đổi khóa đang dùng trong `dict`/`set`. Với thành phần `str` và `int` bất biến như trên, hash của ID được giữ ổn định.

## 7. Định danh cạnh/cung: khi nào cần một ID riêng?

Xét đồ thị có hướng đơn với cung `(A,B)`. Nếu mô hình **không cho phép hai cung cùng hướng giữa cùng đầu mút**, thì cặp `(A,B)` có thể đóng vai trò định danh logic. Cung `(B,A)` là **một cung khác**.

Trong đồ thị vô hướng đơn, `(A,B)` và `(B,A)` biểu diễn **cùng một cạnh**. Nếu dùng cặp hai ID để làm khóa, phải chuẩn hóa hoặc dùng biểu diễn không phụ thuộc thứ tự. Với các ID so sánh được, có thể đặt đầu mút nhỏ hơn trước:

```python
def khoa_canh_vo_huong(u: str, v: str):
    return (u, v) if u <= v else (v, u)


print(khoa_canh_vo_huong("A", "B"))  # ('A', 'B')
print(khoa_canh_vo_huong("B", "A"))  # ('A', 'B')
assert khoa_canh_vo_huong("A", "B") == khoa_canh_vo_huong("B", "A")
```

Cách chuẩn hóa bằng `<=` đòi hỏi các ID có **thứ tự so sánh tổng quát và ổn định**. Nếu ID là những đối tượng không thể so sánh bằng `<=`, cần một hàm chuẩn hóa khác hoặc dùng `frozenset((u,v))` trong trường hợp cạnh vô hướng giữa **hai đỉnh phân biệt**.

Không nên dùng một khóa cặp đầu mút để đại diện cho **hai cạnh song song**: chúng sẽ bị gộp. Trong đa đồ thị, mỗi liên kết nên có `edge_id` duy nhất và giữ cặp `(u,v)` làm **thuộc tính định vị**, không nhất thiết là khóa duy nhất.

Khi dùng `frozenset`, lưu ý `frozenset((A,A))` chỉ chứa một phần tử; nếu muốn biểu diễn khuyên và kiểm tra số đầu mút, phải giữ thêm quy tắc cho `u=v`, không suy luận bậc từ kích thước tập.

## 8. Biểu diễn kề phản ánh định nghĩa cạnh và cung

Sau khi đã có ID đỉnh và liên kết, một cấu trúc phổ biến là **danh sách kề (adjacency list)**.

Với đồ thị **vô hướng** `E=\{\{A,B\},\{A,C\},\{B,C\}\}`:

| Đỉnh | Danh sách các đỉnh kề |
| --- | --- |
| A | B, C |
| B | A, C |
| C | A, B |
| D | *(rỗng)* |

Mỗi cạnh vô hướng `{u,v}` nối **hai đầu mút**, vì vậy khi lưu kề cần ghi **cả hướng `u→v` và `v→u`**, dù về mặt toán học đây chỉ là **một cạnh**.

Với đồ thị **có hướng** `E=\{(A,B),(B,A),(B,C)\}`:

| Đỉnh | Danh sách cung đi ra |
| --- | --- |
| A | B |
| B | A, C |
| C | *(rỗng)* |
| D | *(rỗng)* |

Chỉ ghi cung đi **từ nguồn đến đích**: `A→B` không tự tạo `B→A`. Nếu thường xuyên cần biết **cung đi vào**, có thể lưu thêm danh sách kề ngược; khi đó thêm/xóa cung phải cập nhật cả hai phía.

### Bậc đỉnh

- **Đồ thị vô hướng:** `deg(v)` là số đầu mút cạnh gắn với đỉnh `v`; khuyên đóng góp 2. Với đồ thị không có khuyên, đó cũng là số cạnh kề đỉnh.
- **Đồ thị có hướng:** `outdeg(v)` là số cung đi ra, `indeg(v)` là số cung đi vào. Cung khuyên góp 1 vào mỗi loại bậc.
- **Đỉnh cô lập:** đỉnh không có liên kết liên quan. Nó vẫn phải tồn tại trong tập `V` và trong cấu trúc chứa các đỉnh.

Hai đẳng thức đếm quan trọng, đúng cả khi cho phép khuyên và liên kết song song nếu tính bậc theo quy ước ở trên:

\[
\sum_{v\in V}\deg(v)=2m
\qquad\text{(đồ thị vô hướng)}
\]

\[
\sum_{v\in V}\operatorname{outdeg}(v)
=\sum_{v\in V}\operatorname{indeg}(v)
=m
\qquad\text{(đồ thị có hướng).}
\]

Đây là những **bất biến hữu ích** khi kiểm tra chương trình thêm và xóa liên kết.

## 9. Python: mô hình có ID đỉnh và ID liên kết độc lập

Ví dụ dưới đây cài đặt một đồ thị nhỏ hỗ trợ **có hướng hoặc vô hướng**, có thể có **cạnh/cung song song** và **khuyên**. Các đỉnh dùng **chuỗi ID ổn định**, còn tên hiển thị được lưu riêng. Mỗi liên kết được cấp một ID nguyên để phân biệt cả khi hai liên kết có cùng đầu mút.

```python
class DoThi:
    def __init__(self, co_huong=False):
        self.co_huong = co_huong
        self.dinh = {}       # vertex_id -> label
        self.ke = {}         # vertex_id -> [(neighbor_id, edge_id), ...]
        self.canh = {}       # edge_id -> (u, v, weight)
        self._id_canh_ke_tiep = 0

    def them_dinh(self, ma: str, nhan: str):
        if ma in self.dinh:
            raise ValueError(f"Đỉnh {ma!r} đã tồn tại")
        self.dinh[ma] = nhan
        self.ke[ma] = []  # Kể cả đỉnh cô lập

    def doi_nhan(self, ma: str, nhan_moi: str):
        if ma not in self.dinh:
            raise KeyError(ma)
        self.dinh[ma] = nhan_moi  # Không đổi định danh

    def them_lien_ket(self, u: str, v: str, trong_so=None):
        if u not in self.dinh or v not in self.dinh:
            raise KeyError("Cả hai đầu mút phải tồn tại")

        eid = self._id_canh_ke_tiep
        self._id_canh_ke_tiep += 1
        self.canh[eid] = (u, v, trong_so)

        self.ke[u].append((v, eid))
        if not self.co_huong:
            # Nếu u == v, ghi 2 mục kề cho cùng một khuyên:
            # bậc vô hướng của u sẽ tăng 2.
            self.ke[v].append((u, eid))
        return eid

    def bac(self, ma: str):
        if self.co_huong:
            raise ValueError("Dùng bac_ra/bac_vao cho đồ thị có hướng")
        return len(self.ke[ma])

    def bac_ra(self, ma: str):
        if not self.co_huong:
            raise ValueError("Đồ thị này vô hướng")
        return len(self.ke[ma])

    def bac_vao(self, ma: str):
        if not self.co_huong:
            raise ValueError("Đồ thị này vô hướng")
        if ma not in self.dinh:
            raise KeyError(ma)
        # Không có chỉ mục cung đi vào nên phải duyệt các cung.
        return sum(1 for _, v, _ in self.canh.values() if v == ma)


g = DoThi(co_huong=False)
for ma, nhan in [
    ("A", "Ga trung tâm"),
    ("B", "Ga phía đông"),
    ("C", "Ga phía nam"),
    ("D", "Ga chưa nối tuyến"),
]:
    g.them_dinh(ma, nhan)

e0 = g.them_lien_ket("A", "B", 5)
e1 = g.them_lien_ket("B", "C", 9)
e2 = g.them_lien_ket("A", "B", 7)  # Cạnh song song với e0
e3 = g.them_lien_ket("C", "C", 2)  # Khuyên tại C

print((e0, e1, e2, e3))       # (0, 1, 2, 3)
print(g.ke["A"])              # [('B', 0), ('B', 2)]
print(g.ke["C"])              # [('B', 1), ('C', 3), ('C', 3)]
print([g.bac(x) for x in "ABCD"])  # [2, 3, 3, 0]
print(sum(g.bac(x) for x in "ABCD"))  # 8 = 2 * 4 cạnh

g.doi_nhan("A", "Ga trung tâm mới")
print(g.canh[e0])             # ('A', 'B', 5): đầu mút không đổi

h = DoThi(co_huong=True)
for ma in "ABCD":
    h.them_dinh(ma, ma)
h.them_lien_ket("A", "B")
h.them_lien_ket("B", "A")
h.them_lien_ket("B", "C")
h.them_lien_ket("C", "C")     # Cung khuyên
print(h.ke["B"])              # [('A', 1), ('C', 2)]
print([h.bac_ra(x) for x in "ABCD"])  # [1, 2, 1, 0]
print([h.bac_vao(x) for x in "ABCD"]) # [1, 1, 2, 0]
```

Với `g`, cạnh `A—B` có hai phiên bản độc lập mang ID 0 và 2, nên thông tin trọng số 5 và 7 không bị ghi đè. Với `h`, hai cung `A→B` và `B→A` là hai bản ghi khác nhau; khuyên `C→C` tăng cả `indeg(C)` lẫn `outdeg(C)` một đơn vị.

Mã được thiết kế để minh họa **ý nghĩa biểu diễn**. Chưa triển khai xóa liên kết/đỉnh, tra cứu theo đầu mút, chống thêm cạnh trùng trong đồ thị đơn hoặc thuật toán duyệt BFS/DFS. Với đồ thị đơn, thao tác `them_lien_ket` còn phải **kiểm tra chính sách duy nhất** trước khi thêm; với đa đồ thị, cho phép trùng đầu mút là chủ ý.

## 10. Bất biến dữ liệu cần giữ khi thêm, sửa và xóa

Khi xây dựng một lớp đồ thị, hãy xác định rõ các điều kiện luôn phải đúng:

**Bất biến về đỉnh:**

- Mỗi `vertex_id` có tối đa một bản ghi trong tập `V`; hai nhãn giống nhau không đồng nghĩa cùng ID.
- ID của đỉnh đã lưu phải ổn định. Đổi tên hiển thị không thay đổi các đầu mút liên kết.
- Một đỉnh có thể **cô lập**. Không suy ra tập đỉnh chỉ từ các cạnh đang tồn tại.

**Bất biến về liên kết:**

- Mọi cạnh/cung `(u,v)` đều tham chiếu đến **hai đỉnh đang tồn tại**.
- Với đồ thị vô hướng và danh sách kề như ví dụ, một cạnh không phải khuyên có **hai mục kề đối ứng**, cùng `edge_id`; một khuyên cũng có hai mục kề tại cùng đỉnh.
- Với đồ thị có hướng, một cung được ghi tại nguồn trong danh sách cung đi ra, **không tự thêm cung ngược**.
- Nếu hỗ trợ đa đồ thị, phải phân biệt **ID liên kết** với cặp đầu mút. Nếu không hỗ trợ, phải từ chối liên kết trùng theo đúng quy tắc có hướng/vô hướng.

**Khi xóa đỉnh:** phải quyết định từ chối xóa nếu còn liên kết, hay **xóa kéo theo** tất cả cạnh/cung liên quan. Không được để lại **đầu mút mồ côi (dangling endpoint)** tham chiếu đến ID đã bị xóa.

**Khi đổi ID:** không được chỉ thay khóa của bản ghi đỉnh và bỏ nguyên các cạnh cũ. Nếu thật sự cần chuyển định danh, phải cập nhật nhất quán tất cả tham chiếu, chỉ mục và cơ chế so sánh/hash; đơn giản hơn là chọn ID bất biến từ đầu.

**Khi tái sử dụng ID đã xóa:** nếu còn dữ liệu khác tham chiếu ID cũ, việc cấp lại nó cho đối tượng mới có thể làm sai ý nghĩa liên kết. Cần chính sách không tái sử dụng, hoặc dùng ID kèm **thế hệ (generation)**/cơ chế kiểm tra tham chiếu.

## 11. ID, biểu diễn dữ liệu và độ phức tạp

Sau khi xác định đúng đối tượng, cách lưu đồ thị ảnh hưởng đến thời gian và bộ nhớ:

| Biểu diễn | Bộ nhớ điển hình | Kiểm tra kề `u,v` | Duyệt láng giềng của `u` | Phù hợp |
| --- | --- | --- | --- | --- |
| **Danh sách kề** dùng danh sách | `O(n+m)` | `O(deg(u))` nếu quét danh sách vô hướng; `O(outdeg(u))` với cung đi ra | `O(deg(u))` hoặc `O(outdeg(u))` | Đồ thị thưa, duyệt BFS/DFS |
| **Danh sách kề** dùng tập/map láng giềng | `O(n+m)` kỳ vọng về số mục | Kỳ vọng `O(1)` nếu khóa hashable, phân bố tốt | Tỷ lệ số láng giềng | Đồ thị đơn cần hỏi “có kề không?” thường xuyên |
| **Ma trận kề** `n×n` | `O(n^2)` | `O(1)` truy cập ô | `O(n)` để quét một hàng | Đồ thị dày hoặc miền đỉnh nhỏ, chỉ số cố định |
| **Danh sách cạnh/cung** | `O(n+m)` nếu giữ cả tập đỉnh | `O(m)` nếu chỉ quét danh sách liên kết | `O(m)` nếu không có chỉ mục kề | Dữ liệu đầu vào, duyệt toàn bộ liên kết |

Trong bảng trên, `m` là **số liên kết thực**, không phải số bản ghi mục kề. Với đồ thị vô hướng, danh sách kề thường lưu **hai mục** cho mỗi cạnh; tổng vẫn là `O(n+m)`. Ma trận kề kiểu `0/1` không thể tự phân biệt nhiều cạnh song song; để biểu diễn đa đồ thị phải đổi ô ma trận thành số lượng hoặc danh sách liên kết.

Nếu ID ngoài ứng dụng là chuỗi, ma trận hoặc mảng kề đánh số `0,...,n-1` thường cần một **bảng ánh xạ `external_id → index`**. Bảng băm cho phép tìm chỉ số kỳ vọng `O(1)` dưới giả định hash phù hợp; chính mảng kề mới là phần dùng các chỉ số đó.

Khi xóa đỉnh, **đánh số lại toàn bộ** những chỉ số mảng có thể khiến các cạnh chỉ đến sai đỉnh. Một lựa chọn là giữ các ô ID ổn định và đánh dấu chỗ trống; lựa chọn khác là **nén lại** bảng và cập nhật mọi đầu mút theo ánh xạ chỉ số mới. Cả hai đều có đánh đổi về bộ nhớ, tốc độ và độ phức tạp cập nhật.

**Chi phí của ví dụ Python:** với `dict` ánh xạ ID và danh sách kề, thêm một đỉnh hoặc một cạnh thường là `O(1)` kỳ vọng và phân bổ nếu tính hash/so sánh ID là hằng số, và không kiểm tra liên kết trùng. Tính `bac` vô hướng hay `bac_ra` theo `len(list)` là `O(1)`; tính `bac_vao` trong mã minh họa phải **duyệt tất cả `m` cung**, nên là `O(m)`. Duy trì thêm bộ đếm hoặc chỉ mục cung đi vào có thể làm truy vấn nhanh hơn nhưng tăng chi phí cập nhật.

## 12. Những ngộ nhận dễ mắc

1. **“Hai người cùng tên thì là một đỉnh.”** Sai: nhãn hiển thị có thể trùng; ID phải phân biệt đối tượng.
2. **“Cung `A→B` cũng là cung `B→A`.”** Sai: đó là hai cung khác nhau trong đồ thị có hướng.
3. **“Một cạnh vô hướng lưu trong hai danh sách kề là hai cạnh.”** Sai: đó là hai **mục biểu diễn** của cùng một cạnh.
4. **“Một khuyên vô hướng tăng bậc lên 1.”** Sai theo quy ước bậc chuẩn: khuyên tăng bậc lên **2**.
5. **“Muốn lưu nhiều tuyến A–B thì chỉ cần một tập cặp `(A,B)`.”** Không đủ nếu mỗi tuyến là một liên kết riêng; cần ID cạnh hoặc cấu trúc lưu nhiều cạnh.
6. **“Đỉnh không có cạnh thì không thuộc đồ thị.”** Sai: đỉnh cô lập vẫn thuộc `V`.
7. **“Đổi tên đỉnh đồng nghĩa đổi ID đỉnh.”** Không nên: tên hiển thị là thuộc tính; ID ổn định giúp bảo toàn mọi tham chiếu.
8. **“ID chỉ cần duy nhất tại thời điểm tạo.”** Chưa đủ nếu các tham chiếu cũ còn tồn tại hoặc có nguy cơ tái sử dụng ID sai đối tượng.

## 13. Tự kiểm tra

**Câu 1.** Trong mạng “A theo dõi B”, nên dùng cạnh vô hướng hay cung có hướng? Có được tự suy ra “B theo dõi A” không?

**Đáp án:** Dùng cung `(A,B)` vì quan hệ theo dõi có chiều. Không được suy ra cung `(B,A)` nếu chưa có dữ liệu thể hiện chiều ngược lại.

**Câu 2.** Đồ thị vô hướng có `V={A,B,C,D}` và `E={{A,B},{B,C}}`. Đỉnh nào cô lập? Danh sách kề của B gồm những ai?

**Đáp án:** D cô lập; danh sách kề của B là A và C. Đồ thị có 4 đỉnh và 2 cạnh.

**Câu 3.** Đồ thị vô hướng có một cạnh `A—B`, một cạnh song song `A—B` khác và một khuyên tại B. Bậc của A và B lần lượt bằng bao nhiêu?

**Đáp án:** `deg(A)=2` do hai cạnh A–B. `deg(B)=4`: hai cạnh A–B đóng góp 2, khuyên đóng góp 2. Tổng bậc `2+4=6=2m` với `m=3`.

**Câu 4.** Đồ thị có hướng có hai cung `A→B`, `B→A` và một cung khuyên `B→B`. Tính bậc vào và ra của B.

**Đáp án:** `indeg(B)=2` từ `A→B` và `B→B`; `outdeg(B)=2` từ `B→A` và `B→B`.

**Câu 5.** Hai sinh viên cùng tên “Lan” được lưu làm đỉnh. Nếu dùng tên làm ID, vấn đề gì xảy ra? Cách thiết kế nào tốt hơn?

**Đáp án:** Có thể gộp nhầm hai sinh viên thành một đỉnh. Nên dùng `student_id` ổn định (hoặc khóa tổ hợp như `(school_id, student_id)` nếu cần), còn “Lan” là nhãn hiển thị.

**Câu 6.** Một đồ thị vô hướng lưu cạnh `A—B` trong danh sách kề `A:[B]` và `B:[A]`. Số cạnh là 1 hay 2? Khi xóa cạnh phải sửa những gì?

**Đáp án:** Có **một cạnh**; hai mục kề chỉ là hai bản ghi biểu diễn. Khi xóa cần cập nhật cả danh sách kề A và B (và bản ghi cạnh nếu có) để giữ bất biến.

**Câu 7.** Tại sao hai tuyến đường khác nhau cùng nối A và B nên có `edge_id` riêng nếu cần giữ giờ chạy và trọng số của từng tuyến?

**Đáp án:** Cặp đầu mút `(A,B)` không đủ phân biệt hai tuyến; dùng một khóa như vậy có thể làm ghi đè hoặc gộp thông tin của chúng. ID riêng giúp lưu hai bản ghi độc lập.

**Câu 8.** Với lớp `DoThi` minh họa, vì sao `bac_ra(B)` tính `O(1)` còn `bac_vao(B)` tính `O(m)`?

**Đáp án:** `bac_ra` lấy `len` của danh sách cung đi ra đã lưu; `bac_vao` phải quét tất cả bản ghi cung vì cấu trúc chưa duy trì danh sách hoặc bộ đếm cung đi vào.

**Ghi nhớ:** Đồ thị là **tập đỉnh và tập liên kết có ý nghĩa được xác định rõ**. Cạnh vô hướng không phân biệt đầu mút, cung có hướng phân biệt nguồn và đích; khuyên, cạnh song song và đỉnh cô lập phải được xử lý theo quy ước mô hình. Dùng **ID đỉnh ổn định** tách khỏi nhãn hiển thị và **ID cạnh/cung riêng khi cần phân biệt liên kết** giúp danh sách kề, ma trận kề và các thuật toán về sau giữ đúng bất biến, tránh mất đối tượng hoặc nối nhầm đầu mút.

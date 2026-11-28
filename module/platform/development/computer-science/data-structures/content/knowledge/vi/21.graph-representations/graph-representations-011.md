# Thêm, xóa đỉnh hoặc cạnh và giữ nhất quán các chỉ mục

## 1. Thay đổi đồ thị không chỉ là sửa một danh sách

Một hệ thống học phần lưu quan hệ `A → B` với ý nghĩa “A là điều kiện tiên quyết trực tiếp của B”. Để trả lời hai kiểu câu hỏi, hệ thống giữ:

- `out[A]`: các học phần trực tiếp phụ thuộc vào A;
- `in[B]`: các học phần là điều kiện tiên quyết trực tiếp của B.

Nếu xóa quan hệ A→B nhưng chỉ sửa `out[A]`, một màn hình sẽ báo **không còn** quan hệ, trong khi màn hình khác vẫn báo **có**. Đồ thị đã bị **mất nhất quán chỉ mục**. Tương tự, nếu xóa học phần B mà không xóa các cung có đích B, những liên kết còn lại sẽ trỏ đến một đỉnh không tồn tại.

Vì vậy, nhiệm vụ của cấu trúc dữ liệu đồ thị không chỉ là hỗ trợ thêm/xóa, mà còn phải giữ **các bất biến (invariants)** sau mỗi thao tác thành công.

Trong bài này, ta xét việc cập nhật đồ thị có hướng và vô hướng, đồ thị đơn và đa đồ thị, các cách lưu bằng **danh sách cạnh, danh sách kề, ma trận kề và CSR/CSC**, cùng chi phí thời gian/bộ nhớ của mỗi lựa chọn. Trọng tâm là **phân biệt dữ liệu gốc và chỉ mục phục vụ truy vấn**, để cập nhật đúng, không tạo cạnh giả hoặc làm mất cạnh hợp lệ.

## 2. Mô hình dữ liệu: đỉnh, liên kết và chỉ mục

Cho `G=(V,E)` với `n=|V|` đỉnh, `m=|E|` cạnh hoặc cung. Một thiết kế hỗ trợ cập nhật rõ ràng có thể dùng ba lớp thông tin:

1. **Bảng đỉnh:** `vertices[vertex_id] = vertex_record`, kể cả đỉnh chưa có cạnh.
2. **Bảng liên kết:** `edges[edge_id] = (u,v,weight,...)`; mỗi ID là **một cạnh hoặc một cung thực tế**.
3. **Chỉ mục kề:** cấu trúc giúp tìm nhanh những liên kết có đầu mút tại một đỉnh.

Đối với **đồ thị có hướng**, chọn:

```text
out_ids[u] = tập edge_id của cung đi ra từ u
in_ids[v]  = tập edge_id của cung đi vào v
```

Một cung `e=(u→v)` xuất hiện trong **hai chỉ mục** `out_ids[u]` và `in_ids[v]`, nhưng là **một** bản ghi trong `edges`. Hai chỉ mục có vai trò khác nhau, không phải hai cung ngược chiều.

Đối với **đồ thị vô hướng**, có thể chọn:

```text
incident_ids[u] = tập edge_id có ít nhất một đầu mút ở u
```

Cạnh `{u,v}` với `u != v` xuất hiện trong tập của cả hai đỉnh. Khuyên `{u,u}` xuất hiện một lần trong tập ID của u, nhưng **đóng góp 2 vào bậc vô hướng**. Nếu thay set bằng list chứa từng đầu mút, có thể ghi khuyên hai lần; phải ghi rõ quy ước.

### Định danh đỉnh khác vị trí lưu trữ

ID ổn định như `"course-CS101"` không nhất thiết bằng chỉ số `7` của một hàng ma trận. Nếu xóa một đỉnh và nén các hàng/cột, **chỉ số có thể thay đổi** trong khi ID nghiệp vụ không được phép tự đổi. Một ánh xạ `vertex_id → index` cần được quản lý riêng nếu dùng cấu trúc dựa vào vị trí.

### Định danh cạnh khác cặp đầu mút

Trong **đa đồ thị**, hai cung `A→B` có thể có hai ID, trọng số và thông tin khác nhau. Khi yêu cầu **xóa cung ID e0**, không được xóa luôn cung ID e1 chỉ vì chúng có chung nguồn và đích. Với đồ thị đơn, có thể dùng cặp đầu mút làm khóa tra cứu, nhưng cũng cần xác định quy tắc **có hướng** hay **vô hướng**.

## 3. Ví dụ xuyên suốt: sáu cung và ba bảng dữ liệu

Xét đồ thị có hướng `V={A,B,C,D}`, cho phép cung song song và khuyên:

| ID | Nguồn | Đích | Trọng số | Ghi chú |
| --- | --- | --- | ---: | --- |
| `e0` | A | B | 4 | Chuyến A→B thứ nhất |
| `e1` | A | B | 7 | Chuyến A→B thứ hai |
| `e2` | C | B | 5 | Cung vào B |
| `e3` | B | B | 0 | Khuyên tại B |
| `e4` | B | D | 2 | Cung đi ra từ B |
| `e5` | A | D | 12 | Cung không liên quan đến B |

```text
e0,e1             e4
A ======> B ------------> D
 \        ^               ^
  \       | e2            |
   \      C               |
    +---------------------+
             e5

e3: B -> B (khuyên)
```

Các chỉ mục lưu **edge ID**, không lưu bản sao trọng số:

```text
out_ids[A] = {e0, e1, e5}     in_ids[A] = {}
out_ids[B] = {e3, e4}         in_ids[B] = {e0, e1, e2, e3}
out_ids[C] = {e2}             in_ids[C] = {}
out_ids[D] = {}               in_ids[D] = {e4, e5}
```

Hãy kiểm tra:

- Có **6 cung** nên `m=6`, không phải 5 cặp nguồn–đích phân biệt.
- Bậc ra của `[A,B,C,D]` là `[3,2,1,0]`; bậc vào là `[0,4,0,2]`.
- Tổng bậc ra bằng tổng bậc vào, cùng bằng **6**.
- Khuyên `e3=B→B` nằm trong **cả hai chỉ mục của B**, nhưng chỉ là **một cung** trong bảng `edges`.

Ví dụ này sẽ giúp đối chiếu chính xác kết quả **xóa một cung**, **cập nhật trọng số** và **xóa một đỉnh**.

## 4. Các bất biến phải đúng sau mọi cập nhật thành công

Một thiết kế có bảng `vertices`, `edges`, `out_ids`, `in_ids` nên đảm bảo:

**Bất biến đỉnh và đầu mút**

- Mỗi ID đỉnh chỉ có **một** bản ghi trong `vertices`.
- Mọi cung `e=(u,v,...)` đều thỏa **`u∈V` và `v∈V`**.
- Mọi đỉnh, kể cả đỉnh cô lập, đều có một tập chỉ mục đi ra và một tập đi vào (có thể rỗng).

**Bất biến liên kết và chỉ mục**

- Mỗi **edge ID** đang hoạt động là duy nhất và ánh xạ tới đúng một cung.
- Với mỗi cung `e=(u→v)`: `e∈out_ids[u]` **và** `e∈in_ids[v]`.
- Ngược lại, nếu ID `e` xuất hiện trong `out_ids[u]` thì `edges[e].source==u`; nếu xuất hiện trong `in_ids[v]` thì `edges[e].target==v`.
- Một cung không được xuất hiện ở **chỉ mục của đỉnh sai**.
- Hai cung song song có **hai ID**, không được vô tình gộp khi thêm/xóa.

**Bất biến đếm**

\[
\sum_{u\in V}|out\_ids[u]|
=\sum_{v\in V}|in\_ids[v]|
=|E|=m.
\]

Đẳng thức này vẫn đúng khi có cung song song và khuyên. Với đồ thị vô hướng, tổng **bậc theo đầu mút** thỏa:

\[
\sum_{u\in V}\deg(u)=2m.
\]

**Chú ý:** tổng kích thước `out_ids` bằng `m` là **điều kiện cần**, không đủ để chứng minh đúng. Hai chỉ mục cùng sai một cách “bù trừ” vẫn có thể giữ tổng. Vì vậy, cần kiểm tra **từng edge ID và đúng đầu mút**, không chỉ đếm số phần tử.

## 5. Thêm đỉnh: tạo đầy đủ trạng thái ngay cả khi chưa có cạnh

Để thêm đỉnh `X` vào đồ thị dùng hai chỉ mục:

1. Kiểm tra ID `X` chưa tồn tại.
2. Tạo `vertices[X]` với dữ liệu đỉnh.
3. Tạo `out_ids[X]=set()`.
4. Tạo `in_ids[X]=set()`.

Sau thao tác, `n` tăng 1 nhưng `m` **không đổi**. Đỉnh mới là **đỉnh cô lập** cho tới khi có cung gắn với nó.

Với `dict` và `set` của Python, thao tác trên các khóa có chi phí **`O(1)` kỳ vọng** (và một số thao tác cấp phát có tính phân bổ) theo các giả định thường dùng về hàm băm. Đây không phải bảo đảm thời gian xấu nhất với mọi khóa.

**Các trường hợp cần xử lý:** ID bị trùng, ID có kiểu không hashable, nhãn hiển thị trùng nhưng ID khác, hoặc thao tác thất bại giữa chừng khiến chỉ một trong các bảng được tạo.

### Thêm đỉnh trong ma trận kề khác gì?

Một ma trận đặc `n×n` phải có thêm **một hàng và một cột** mới. Nếu cài bằng `n` list có thể mở rộng, cần thêm khoảng `2n+1` ô mới nên chi phí phân bổ thường **`O(n)`**; nếu lưu bằng một khối nhớ liên tiếp phải cấp phát lại, một lần resize có thể cần sao chép **`O(n²)`** ô.

Với **CSR/CSC** dạng mảng nén, thêm một đỉnh cô lập ở cuối có thể chỉ thêm một offset cuối bằng offset cũ, nhưng nếu phải đổi lại thứ tự ID/chỉ số hoặc chuyển các mảng sang vùng nhớ mới thì chi phí phụ thuộc cách cài đặt. Không có một cận cập nhật đỉnh áp dụng cho mọi biến thể.

## 6. Thêm cạnh hoặc cung: quyết định chính sách trùng trước khi ghi

Với **đồ thị có hướng**, thêm cung `u→v` gồm:

1. Kiểm tra cả `u` và `v` **đã tồn tại**; quyết định có cho **khuyên `u=v`** hay không.
2. Nếu mô hình là **đồ thị đơn**, kiểm tra **chưa có cung `u→v`**. Cung ngược `v→u` nếu có là một liên kết **khác**.
3. Cấp `edge_id` mới và lưu bản ghi `edges[e]`.
4. Thêm `e` vào **`out_ids[u]`** và **`in_ids[v]`**.
5. Cập nhật bộ đếm, cache hoặc các chỉ mục bổ sung nếu ứng dụng duy trì.

Nếu **đa đồ thị**, có thể thêm nhiều cung cùng cặp `(u,v)`, nhưng mỗi cung phải có ID riêng. Nếu **đồ thị vô hướng**, thêm một cạnh `{u,v}` tạo một bản ghi cạnh và cập nhật tập incidence của **cả hai đầu mút**, không tạo hai cạnh độc lập.

Với bảng `edges` và hai bảng kề là `dict` chứa `set` các ID, **thêm một cung theo ID** có chi phí **`O(1)` kỳ vọng/phân bổ** sau khi đã kiểm tra đầu mút. Nếu phải kiểm tra **cặp đầu mút chưa tồn tại** bằng cách quét các ID trong `out_ids[u]`, chi phí có thể là `O(outdeg(u))`. Muốn kiểm tra trùng nhanh hơn, cần chỉ mục phụ theo `(u,v)`.

### Một bẫy khi dùng bảng kề trọng số

```python
out = {"A": {"B": 4}}
out["A"]["B"] = 7
# Kết quả chỉ còn trọng số 7, không còn cung A->B trọng số 4.
```

Đây có thể là thao tác **cập nhật trọng số** hợp lệ của đồ thị đơn; nhưng với **đa đồ thị**, nó làm mất một cung song song. Trong đa đồ thị, hãy lưu **edge ID riêng** hoặc dùng một danh sách các ID tại mỗi cặp đầu mút.

## 7. Xóa một cạnh/cung: phải xác định chính xác liên kết nào

Nếu được yêu cầu xóa **cung ID e0** trong ví dụ ở mục 3:

1. Tìm bản ghi `edges[e0]=(A,B,4)`.
2. Loại **e0** khỏi `out_ids[A]`.
3. Loại **e0** khỏi `in_ids[B]`.
4. Loại **e0** khỏi bảng `edges`.

Sau khi xóa:

```text
out_ids[A] = {e1, e5}
in_ids[B]  = {e1, e2, e3}
edges[e1]  = (A,B,7)     # e1 vẫn còn
m = 5
```

Không được xóa mọi cung `A→B`, vì cung **e1** vẫn hợp lệ. Với khuyên `B→B`, thao tác xóa một ID phải xóa ID ấy ở **`out_ids[B]` và `in_ids[B]`**; một cung bị xóa đúng một lần khỏi `edges`.

Với `dict` và `set` kèm tra ID trực tiếp, thao tác xóa ID khỏi hai chỉ mục thường **`O(1)` kỳ vọng**, không cần quét toàn bộ đồ thị. Nhưng khi chỉ mục là **list** mục kề, việc tìm và xóa có thể tốn **`O(outdeg(u)+indeg(v))`**, do phải tìm mục và dời phần tử.

**Nếu API chỉ nhận `xoa_canh(u,v)`:** trong đa đồ thị, yêu cầu ấy nhập nhằng. Phải xác định rõ xóa **một liên kết bất kỳ**, **tất cả liên kết**, hoặc yêu cầu cung cấp **edge ID**. Không được chọn cách xóa ngầm khiến mất dữ liệu ngoài ý định.

**Nếu cung không tồn tại:** nên báo lỗi hoặc trả một kết quả không thay đổi theo hợp đồng API; không được lặng lẽ giảm `m` khiến bộ đếm âm hoặc lệch.

## 8. Xóa đỉnh: xóa toàn bộ liên kết liên quan, kể cả khuyên

Xóa đỉnh B nguy hiểm hơn xóa một cung vì B có thể có:

- Nhiều cung **đi ra** từ B.
- Nhiều cung **đi vào** B.
- Nhiều cung **song song**.
- Cung **khuyên B→B**, xuất hiện trong cả hai chỉ mục.

Một thuật toán đúng khi có `out_ids` và `in_ids`:

```text
incident_ids = out_ids[B] ∪ in_ids[B]

for each edge_id in incident_ids:
    delete_edge(edge_id)

delete out_ids[B]
delete in_ids[B]
delete vertices[B]
```

**Vì sao dùng hợp (union)?** Khuyên e3 có mặt trong **cả `out_ids[B]` và `in_ids[B]`**. Nếu nối hai danh sách mà không khử trùng ID, ta có thể xóa e3 **hai lần** và gặp lỗi ở lần thứ hai. Tập hợp các ID liên quan chỉ chứa e3 một lần.

Với dữ liệu ban đầu ở mục 3, tập cung liên quan đến B là **`{e0,e1,e2,e3,e4}`**. Xóa B sẽ xóa **5 cung** ấy, nhưng giữ **e5=A→D**. Sau khi xóa:

```text
V = {A,C,D}
E = {e5 : A -> D, weight=12}
out_ids[A] = {e5}
in_ids[D]  = {e5}
m = 1
```

Nếu dùng hai bảng `set(edge_id)`, chi phí tìm các ID liên quan và xóa chúng là **`O(indeg(B)+outdeg(B))` kỳ vọng**, tính một cung khuyên tối đa hai lần khi xây tập hợp và một lần khi xóa. Không cần quét toàn bộ `m` cung không liên quan.

Nếu **chỉ có danh sách cung đi ra**, không có `in_ids`, để tìm mọi cung đi vào B thường phải quét **toàn bộ các danh sách**: `O(n+m)`. Nếu chỉ có **danh sách cạnh thuần**, phải lọc toàn bộ bảng `m` liên kết, thường `O(m)`.

### Chính sách thay thế: từ chối xóa đỉnh chưa cô lập

Không phải hệ thống nào cũng muốn tự động xóa hàng loạt quan hệ. Một API có thể quy định:

> Chỉ cho xóa `u` khi `indeg(u)=outdeg(u)=0`; nếu còn liên kết, trả lỗi và yêu cầu xử lý liên kết trước.

Chính sách **xóa liên đới (cascade)** hoặc **từ chối (restrict)** phải được chọn có chủ đích theo nghiệp vụ. Không được xóa đỉnh rồi để những edge ID khác trỏ tới đỉnh đã biến mất.

## 9. Đồ thị vô hướng: một cạnh, hai đầu mút, một trường hợp khuyên

Trong đồ thị vô hướng, một cạnh `e={u,v}` với `u≠v` là **một liên kết**, dù danh sách kề có thể lưu ở hai phía. Khi thêm cạnh:

```text
edges[e] = (u, v, weight)
incident_ids[u].add(e)
incident_ids[v].add(e)
```

Xóa cạnh cần xóa **cả hai tham chiếu** và bản ghi. Cập nhật trọng số tập trung theo ID giúp tránh hai bản sao trọng số ở hai phía bị lệch.

Đối với khuyên `e={u,u}`, nếu `incident_ids[u]` là **set ID**, ta chỉ thêm `e` **một lần**. Bậc vô hướng vẫn phải đếm **hai đầu mút**:

\[
\deg(u)
=|incident\_ids[u]|
+\#\{e\in incident\_ids[u]:e\text{ là khuyên tại }u\}.
\]

Ví dụ có hai cạnh song song A—B và một khuyên B—B:

```text
edges[e0] = (A,B)
edges[e1] = (A,B)
edges[e2] = (B,B)

incident_ids[A] = {e0,e1}
incident_ids[B] = {e0,e1,e2}

deg(A) = 2
deg(B) = 3 + 1 = 4
sum(deg) = 6 = 2 * 3 cạnh
```

Nếu sử dụng **list các đầu mút kề** thay vì set ID, có thể ghi khuyên **hai lần** để `len(adj[u])` bằng bậc. Hai cách lưu không mâu thuẫn khi dùng đúng quy ước, nhưng trộn hai quy ước sẽ làm sai số cạnh, bậc hoặc kết quả xóa.

## 10. Python: cập nhật đồ thị có hướng với bảng cung và hai chỉ mục

Lớp dưới đây minh họa một **đa đồ thị có hướng**, cho phép khuyên, cung song song, trọng số bằng 0 và đỉnh cô lập. Bảng `cung` là nơi lưu thông tin cung chuẩn; hai chỉ mục `ra` và `vao` chỉ giữ **edge ID**.

Chúng ta sử dụng `dataclass(frozen=True)` để hạn chế việc sửa đầu mút hoặc trọng số mà không thông qua API đồ thị. Khi đổi trọng số, lớp thay bản ghi cung bằng một bản ghi mới **giữ nguyên ID**.

```python
from dataclasses import dataclass, replace
from math import isfinite


@dataclass(frozen=True)
class Cung:
    eid: int
    nguon: str
    dich: str
    trong_so: float


class DoThiCoHuong:
    def __init__(self):
        self.dinh = {}    # vertex_id -> nhãn hiển thị
        self.cung = {}    # edge_id -> Cung
        self.ra = {}      # vertex_id -> set(edge_id)
        self.vao = {}     # vertex_id -> set(edge_id)
        self.next_eid = 0

    def them_dinh(self, ma: str, nhan: str):
        if ma in self.dinh:
            raise ValueError("Đỉnh đã tồn tại")
        self.dinh[ma] = nhan
        self.ra[ma] = set()
        self.vao[ma] = set()

    @staticmethod
    def _kiem_tra_trong_so(w):
        if (isinstance(w, bool)
                or not isinstance(w, (int, float))
                or not isfinite(w)):
            raise ValueError("Trọng số phải là số hữu hạn")

    def them_cung(self, u: str, v: str, trong_so=1) -> int:
        if u not in self.dinh or v not in self.dinh:
            raise KeyError("Đầu mút không tồn tại")
        self._kiem_tra_trong_so(trong_so)

        eid = self.next_eid
        self.next_eid += 1  # Không tái sử dụng ID cung đã xóa
        self.cung[eid] = Cung(eid, u, v, trong_so)
        self.ra[u].add(eid)
        self.vao[v].add(eid)
        return eid

    def xoa_cung(self, eid: int) -> Cung:
        e = self.cung[eid]  # KeyError nếu ID không tồn tại
        self.ra[e.nguon].remove(eid)
        self.vao[e.dich].remove(eid)
        del self.cung[eid]
        return e

    def doi_trong_so(self, eid: int, trong_so):
        self._kiem_tra_trong_so(trong_so)
        e = self.cung[eid]
        # Hai chỉ mục chỉ lưu ID, không cần sửa nguồn/đích.
        self.cung[eid] = replace(e, trong_so=trong_so)

    def xoa_dinh(self, u: str):
        if u not in self.dinh:
            raise KeyError(u)
        # Tạo tập MỚI vì xoa_cung thay đổi self.ra/self.vao.
        cac_cung_lien_quan = self.ra[u] | self.vao[u]
        for eid in cac_cung_lien_quan:
            self.xoa_cung(eid)
        del self.ra[u]
        del self.vao[u]
        del self.dinh[u]
        return cac_cung_lien_quan

    def cung_di_vao(self, v: str):
        if v not in self.dinh:
            raise KeyError(v)
        return [(eid, self.cung[eid].nguon)
                for eid in sorted(self.vao[v])]

    def kiem_tra_bat_bien(self) -> bool:
        # assert dùng để minh họa kiểm chứng trong lúc phát triển.
        assert set(self.dinh) == set(self.ra) == set(self.vao)
        assert sum(map(len, self.ra.values())) == len(self.cung)
        assert sum(map(len, self.vao.values())) == len(self.cung)

        for eid, e in self.cung.items():
            assert eid == e.eid
            assert e.nguon in self.dinh and e.dich in self.dinh
            assert eid in self.ra[e.nguon]
            assert eid in self.vao[e.dich]
        for u, ids in self.ra.items():
            for eid in ids:
                assert eid in self.cung
                assert self.cung[eid].nguon == u
        for v, ids in self.vao.items():
            for eid in ids:
                assert eid in self.cung
                assert self.cung[eid].dich == v
        return True


g = DoThiCoHuong()
for u in "ABCD":
    g.them_dinh(u, f"Đỉnh {u}")

e0 = g.them_cung("A", "B", 4)
e1 = g.them_cung("A", "B", 7)  # Cung song song
e2 = g.them_cung("C", "B", 5)
e3 = g.them_cung("B", "B", 0)  # Khuyên
e4 = g.them_cung("B", "D", 2)
e5 = g.them_cung("A", "D", 12)

print([len(g.ra[u]) for u in "ABCD"])   # [3, 2, 1, 0]
print([len(g.vao[u]) for u in "ABCD"])  # [0, 4, 0, 2]
print(g.cung_di_vao("B"))
# [(0, 'A'), (1, 'A'), (2, 'C'), (3, 'B')]
print(g.kiem_tra_bat_bien())           # True

g.xoa_cung(e0)
print(g.cung_di_vao("B"))
# [(1, 'A'), (2, 'C'), (3, 'B')]: e1 vẫn tồn tại

g.doi_trong_so(e1, 9)
print(g.cung[e1].trong_so)            # 9: ID e1 không đổi

da_xoa = g.xoa_dinh("B")
print(sorted(da_xoa))                 # [1, 2, 3, 4]
print(sorted(g.dinh))                 # ['A', 'C', 'D']
print(sorted(g.cung))                 # [5]: chỉ còn A -> D
print(g.kiem_tra_bat_bien())           # True

g.them_dinh("E", "Đỉnh E")
e6 = g.them_cung("D", "E", 3)
print(e6)                            # 6: không tái sử dụng ID đã xóa
print(sorted(g.cung))                 # [5, 6]
print(g.kiem_tra_bat_bien())           # True
```

**Giải thích:** Khi `xoa_dinh("B")`, khuyên e3 nằm cả trong `ra[B]` và `vao[B]` nhưng toán tử hợp `|` chỉ giữ ID e3 **một lần**. Sau đó e1, e2, e3 và e4 đều bị xóa; cung e5=A→D không liên quan tới B nên vẫn giữ nguyên.

**Giới hạn quan trọng:** đây là mô hình **đơn luồng trong bộ nhớ**, giả định các thao tác cấp phát/set/dict thực hiện bình thường. Nó **chưa bảo đảm rollback hoặc tính nguyên tử nếu xảy ra lỗi cấp phát giữa chừng**, chưa chặn sửa trực tiếp thuộc tính công khai `dinh/cung/ra/vao`, và chưa xử lý xóa đỉnh theo chính sách `restrict`. Trong môi trường sản xuất, cần đóng gói dữ liệu, kiểm tra đầu vào, cơ chế đồng bộ/giao dịch thích hợp và kiểm thử lỗi.

Trong Python, `assert` có thể bị vô hiệu hóa khi chạy ở chế độ tối ưu hóa; vì vậy hàm kiểm chứng dùng `assert` ở đây phục vụ **minh họa và phát triển**, không thay thế kiểm tra dữ liệu bắt buộc ở hệ thống thực.

## 11. So sánh chi phí cập nhật giữa các biểu diễn

Giả sử `n` đỉnh, `m` liên kết; với đồ thị có hướng, ký hiệu `d^+(u)=outdeg(u)`, `d^-(u)=indeg(u)`. Các cận trong bảng giả sử ID đã tồn tại và không tính bước kiểm tra nghiệp vụ phức tạp hơn.

| Biểu diễn | Thêm/xóa một liên kết | Xóa đỉnh cùng liên kết liên quan | Ghi chú |
| --- | --- | --- | --- |
| Bảng cạnh + `out/in` dạng **hash set edge ID** | `O(1)` **kỳ vọng/phân bổ** theo ID | `O(d^+(u)+d^-(u))` **kỳ vọng** | Cần đồng bộ các chỉ mục; giữ được cung song song và khuyên |
| Danh sách kề **list** | Thêm cuối `O(1)` phân bổ nếu không dò trùng; xóa theo láng giềng `O(d(u))` | Tùy chỉ mục; có thể phải quét `O(n+m)` | Với đồ thị vô hướng cần cập nhật cả hai phía |
| Danh sách cạnh **thuần** | Thêm cuối `O(1)` phân bổ; xóa theo ID thường `O(m)` | Lọc toàn bộ `m` bản ghi: `O(m)` | Kiểm tra đầu mút và giữ V riêng |
| Ma trận kề **đặc** | Ghi/xóa một ô `O(1)` theo chỉ số | Nén lại hàng/cột thường `O(n²)` | Không trực tiếp giữ được đa cạnh nếu mỗi ô chỉ là Boolean/trọng số |
| CSR/CSC **mảng nén đặc** | Chèn/xóa giữa mảng có thể `O(n+m)` xấu nhất | Thường cần nén lại, tái dựng hoặc cơ chế delta | Hợp với dữ liệu tĩnh/nhiều đọc |

Với `out/in` dạng **hash set**, thao tác **`xoa_dinh`** của mã Python có chi phí kỳ vọng theo **số cung liên quan**, không cần quét mọi `m` cung. Nhưng để đạt được điều này, mỗi lần thêm/xóa một cung phải duy trì **đầy đủ cả hai chỉ mục**.

**Không nhầm `O(1)` cập nhật ô ma trận với `O(1)` thêm/xóa đỉnh.** Ma trận có thể ghi nhanh liên kết giữa hai chỉ số đã có, nhưng thay đổi tập đỉnh ảnh hưởng tới kích thước ma trận và ánh xạ ID.

## 12. Ánh xạ ID–chỉ số, tombstone và cấu trúc nén

### 12.1. Xóa đỉnh khỏi ma trận kề

Giả sử các đỉnh là `[A,B,C,D]` và được gán chỉ số `[0,1,2,3]`. Nếu xóa B bằng cách bỏ hàng/cột 1, thứ tự còn lại là `[A,C,D]` với chỉ số `[0,1,2]`.

Điều đó có nghĩa **C đổi chỉ số từ 2 sang 1 và D từ 3 sang 2**. Bất kỳ bộ đệm, chỉ mục hoặc mảng parent/distance còn giữ chỉ số cũ có thể trả lời sai.

Hai chiến lược:

- **Nén lại:** bỏ hàng/cột và xây lại `id_to_index` (hoặc cập nhật những entry bị ảnh hưởng). Thường tốn `O(n²)` đối với ma trận đặc do phải dịch dữ liệu.
- **Giữ chỉ số trống:** đánh dấu một index không còn hoạt động, không di chuyển những đỉnh khác. Cần cập nhật trạng thái đỉnh còn hiệu lực, xóa/ẩn hàng và cột tương ứng, quản lý quyền tái sử dụng chỉ số và chấp nhận chỗ trống trong ma trận.

Đừng tái sử dụng chỉ số hoặc edge ID khi các tham chiếu cũ bên ngoài chưa được vô hiệu hóa; một tham chiếu “đúng chỉ số” nhưng trỏ sang đối tượng khác là một lỗi khó phát hiện.

### 12.2. Chèn/xóa với CSR/CSC

CSR có `row_ptr` và một mảng liên tiếp `col_idx`; CSC có `col_ptr` và `row_idx`. Chèn một cung vào giữa đoạn có thể phải:

1. Dịch chuyển nhiều mục láng giềng, trọng số và ID trong mảng.
2. Tăng những offset sau vị trí chèn.
3. Nếu lưu cả CSR và CSC, cập nhật **cả hai biểu diễn** và mọi bảng ánh xạ edge ID → vị trí.

Một lần cập nhật có thể tốn **`O(n+m)` trường hợp xấu**, dù việc **đọc** một đoạn kề là rất hiệu quả. Các giải pháp thường dùng là **cập nhật theo lô rồi dựng lại**, hoặc giữ **CSR nền + delta thêm/xóa (tombstone)**.

Khi có delta, một phép truy vấn phải trả về **trạng thái logic hiện tại**, tức cung trong CSR nền **trừ** ID bị xóa **cộng** cung thêm mới. Bậc đỉnh cũng phải tính theo trạng thái đã hợp nhất, không chỉ lấy hiệu offset cũ.

## 13. Đồng bộ, rollback và nguồn dữ liệu chuẩn

Với một đồ thị lưu nhiều chỉ mục, lỗi có thể xuất hiện không chỉ trong thuật toán mà còn trong cách **thực hiện nhiều thay đổi như một giao dịch**:

```text
Thêm cung u -> v:
  1. edges[e] = ...
  2. out_ids[u].add(e)
  3. in_ids[v].add(e)
```

Nếu có lần đọc khác chen vào **sau bước 2 nhưng trước bước 3**, nó sẽ thấy trạng thái không nhất quán. Nếu bước 3 thất bại do lỗi tài nguyên, thao tác ghi cũng không hoàn thành hợp lệ.

Một số biện pháp thiết kế:

- **Chọn dữ liệu chuẩn:** ví dụ bảng `edges` là nguồn dữ liệu gốc; `out/in`, ma trận hoặc CSR/CSC là các **chỉ mục suy ra** có thể dựng lại.
- **Kiểm tra trước khi ghi:** xác thực đầu mút, chính sách khuyên/cung song song, khả năng hợp lệ của trọng số, ID và quyền sửa.
- **Cập nhật nguyên tử theo mô hình hệ thống:** dùng khóa phù hợp, transaction của cơ sở dữ liệu, hoặc xây một snapshot mới rồi công bố nhất quán.
- **Có quy tắc phục hồi:** rollback khi một phần cập nhật thất bại, hoặc ghi nhật ký để sửa/dựng lại chỉ mục.
- **Quản lý phiên bản:** một truy vấn không nên vô tình đọc bảng cạnh ở phiên bản mới nhưng chỉ mục `in` ở phiên bản cũ.

Trong thiết kế kiểu **copy-on-write**, có thể xây cấu trúc mới từ trạng thái hiện hành và chỉ thay tham chiếu đang công bố khi bản mới đã đầy đủ. Đổi lại, chi phí cấp phát/sao chép có thể tăng; không nên tuyên bố mọi chiến lược nguyên tử đều miễn phí.

Đối với dữ liệu lâu dài, việc kiểm tra **khóa ngoại giữa bảng cung và bảng đỉnh** có thể giúp ngăn cung mồ côi. Nhưng nếu xóa cascade, ứng dụng vẫn phải xác định rõ các chỉ mục, cache và tác vụ phụ thuộc sẽ được cập nhật thế nào.

## 14. Kiểm tra bất biến và trường hợp ranh giới

Ngoài kiểm tra trong mã, một bộ kiểm thử cho API đồ thị nên có những trường hợp sau:

| Tình huống | Điều kiện cần xác minh |
| --- | --- |
| Thêm đỉnh không có cạnh | Đỉnh xuất hiện trong bảng V, `out` và `in` rỗng |
| Thêm lại ID đỉnh | Bị từ chối hoặc xử lý theo hợp đồng; không tạo hai bản ghi trùng |
| Thêm cung A→B | Có đúng một edge ID mới; hiện ở `out[A]` và `in[B]` |
| Thêm cung B→A | Chỉ tạo cung ngược khi được yêu cầu; không sửa cung A→B |
| Thêm hai cung A→B | Đa đồ thị giữ đủ hai ID; đồ thị đơn phải kiểm tra trùng |
| Thêm khuyên B→B | Một bản ghi cung, một ID ở mỗi `out[B]` và `in[B]` |
| Xóa một cung song song | Chỉ ID được chỉ định biến mất, ID kia còn |
| Xóa cùng một ID hai lần | Lần hai báo không tồn tại; không làm giảm số cung lần nữa |
| Xóa một đỉnh có khuyên | Khuyên chỉ bị xóa một lần; các cung vào/ra khác cũng bị xóa |
| Xóa đỉnh cô lập | Không làm thay đổi `m` hoặc chỉ mục của các đỉnh khác |
| Đổi trọng số của cung | ID và đầu mút giữ nguyên; chỉ giá trị trọng số thay đổi |
| Cung có trọng số 0 | Vẫn xuất hiện trong chỉ mục và được tính là một cung |
| Xóa đỉnh không tồn tại | Báo lỗi, không làm biến đổi dữ liệu khác |
| Xây lại chỉ mục từ bảng cung | Hai chỉ mục mới tương đương trạng thái logic cũ |

### Cách kiểm tra sau một chuỗi cập nhật ngẫu nhiên

Trong quá trình phát triển, có thể tạo một **mô hình tham chiếu đơn giản** chỉ lưu `V` và danh sách bản ghi `E`. Sau một chuỗi thao tác thêm/xóa:

1. Dựng lại `expected_out` và `expected_in` trực tiếp từ bảng cung chuẩn.
2. So sánh **tập edge ID theo từng đỉnh** với các chỉ mục đang duy trì.
3. Kiểm tra tổng bậc và mọi đầu mút còn tồn tại.
4. Kiểm tra các phép truy vấn theo chiều đi ra/đi vào và xóa cung song song.

Kiểm chứng theo từng ID và hai đầu mút mạnh hơn chỉ so sánh tổng số cung. Trong hệ thống thực, có thể dùng kiểm tra định kỳ hoặc kiểm tra theo mẫu, vì quét toàn bộ `n+m` mục sau **mỗi** cập nhật sẽ làm mất lợi thế `O(1)` kỳ vọng của thao tác thêm/xóa.

## 15. Những lỗi thường gặp

1. **Xóa đỉnh nhưng chỉ xóa danh sách cung đi ra.** Các cung đi vào từ đỉnh khác vẫn trỏ tới đỉnh đã biến mất.
2. **Xóa cung ở `out` nhưng quên `in`.** Hai truy vấn cho kết quả mâu thuẫn.
3. **Thêm cạnh vô hướng chỉ tại một đầu mút.** Bất biến đối ứng bị phá vỡ.
4. **Nhầm hai mục chỉ mục với hai cung thực.** Một cung có một edge ID, dù được tra qua `out` và `in`.
5. **Xóa tất cả cung A→B khi chỉ yêu cầu xóa e0.** Làm mất những cung song song không liên quan.
6. **Xóa khuyên hai lần khi xóa đỉnh.** Phải khử trùng ID khi hợp các tập cung vào và đi ra.
7. **Bỏ qua đỉnh cô lập vì không xuất hiện trong bảng cạnh.** Khi đó số đỉnh và kết quả thuật toán sai.
8. **Dùng trọng số 0 làm dấu không có cạnh.** Một cung trọng số 0 vẫn tồn tại.
9. **Tái sử dụng edge ID hoặc chỉ số khi còn tham chiếu cũ.** Dẫn đến đọc nhầm liên kết hoặc đỉnh mới.
10. **Cho rằng xóa theo ID là `O(1)` trong mọi biểu diễn.** List, edge list thuần và CSR có chi phí khác nhau.
11. **Giữ chỉ mục cũ sau khi nén ma trận hoặc dựng lại CSR.** ID → vị trí hoặc edge ID → offset có thể đã thay đổi.
12. **Dùng snapshot cũ và delta mới mà không có quy tắc phiên bản.** Các truy vấn thấy những trạng thái không nhất quán.
13. **Chỉ kiểm tra tổng bậc bằng m.** Các ID sai đầu mút có thể không làm thay đổi tổng.
14. **Coi `dict`/`set` luôn bảo đảm `O(1)` xấu nhất.** Đó thường là chi phí kỳ vọng, tùy dữ liệu và phép băm.

## 16. Tự kiểm tra

**Câu 1.** Đồ thị có hướng lưu `out` và `in`. Khi thêm `e=(A→B)`, những chỉ mục nào phải nhận ID e?

**Đáp án:** `out[A]` và `in[B]`, cùng bảng `edges[e]`. Không tự thêm cung ngược `B→A`.

**Câu 2.** Một đỉnh C có bậc vào 3, bậc ra 2. Nếu xóa C và không có khuyên, có bao nhiêu cung khác nhau bị xóa?

**Đáp án:** **5 cung**: ba cung đi vào và hai cung đi ra. Nếu có khuyên, phải trừ số khuyên khi cộng hai bậc để tránh đếm một cung hai lần.

**Câu 3.** Đỉnh B có cung khuyên e3. Tại sao xóa B bằng cách nối `out[B]` và `in[B]` rồi xóa từng ID có thể lỗi?

**Đáp án:** e3 xuất hiện trong cả hai danh sách, nên có thể bị xóa hai lần. Phải lấy **hợp ID**, chẳng hạn `out[B] | in[B]`, để mỗi cung chỉ được xóa một lần.

**Câu 4.** Có hai cung e0 và e1 cùng A→B. Sau khi xóa e0, `in[B]` có còn nguồn A không?

**Đáp án:** Có, vì e1 vẫn là một cung A→B. Một tập nguồn phân biệt chỉ nên loại A khi **không còn cung nào** từ A tới B.

**Câu 5.** Trong ví dụ ở mục 3, sau khi xóa đỉnh B trực tiếp từ đồ thị ban đầu, còn lại những cung nào?

**Đáp án:** Chỉ còn **e5=A→D**. Các cung e0, e1, e2, e3 và e4 đều liên quan tới B nên phải xóa.

**Câu 6.** Với đồ thị vô hướng, một khuyên `e={B,B}` được lưu một lần trong `incident_ids[B]`. Nó đóng góp bao nhiêu vào bậc B?

**Đáp án:** **2**, vì khuyên có hai đầu mút cùng tại B. Nếu chỉ đếm số edge ID trong set, phải cộng thêm số khuyên.

**Câu 7.** Với `out/in` dạng hash set edge ID, xóa một đỉnh có `p` cung ra, `q` cung vào có chi phí kỳ vọng nào nếu không cần quét những cung khác?

**Đáp án:** **`O(p+q)` kỳ vọng** để lấy hợp ID và cập nhật các chỉ mục, trong các giả định thông thường về hash/set. Cung khuyên được khử trùng bằng hợp ID.

**Câu 8.** Vì sao thao tác xóa một cạnh theo đầu mút trong danh sách kề dạng list không mặc nhiên là `O(1)`?

**Đáp án:** Phải tìm mục phù hợp trong list và có thể dịch chuyển phần tử khi xóa; thường tốn thời gian tỷ lệ với bậc của đầu mút.

**Câu 9.** Khi xóa B khỏi ma trận kề với thứ tự `[A,B,C,D]` rồi nén hàng/cột, những đỉnh nào thay đổi chỉ số?

**Đáp án:** C đổi từ 2 sang 1, D từ 3 sang 2. Mọi ánh xạ ID–chỉ số và dữ liệu phụ theo chỉ số phải được cập nhật.

**Câu 10.** Tại sao cập nhật một cung trong CSR packed có thể tốn `O(n+m)` dù biết chính xác vị trí muốn chèn?

**Đáp án:** Các phần tử ở những đoạn sau phải dịch chuyển và các offset tương ứng phải tăng/giảm; nếu có CSC và chỉ mục ID phụ còn phải cập nhật đồng bộ.

**Câu 11.** Sau khi cập nhật trọng số của cung e1 từ 7 lên 9, ID và hai đầu mút của cung có thay đổi không?

**Đáp án:** Không. Đó là cập nhật thuộc tính của cùng cung; lưu bản ghi theo ID giúp giữ định danh ổn định.

**Câu 12.** Một hệ thống phải phục vụ truy vấn liên tục trong khi cập nhật cả `edges`, `out` và `in`. Rủi ro nào xuất hiện nếu không đồng bộ?

**Đáp án:** Truy vấn có thể đọc một trạng thái cập nhật dở, chẳng hạn cung đã có trong `out` nhưng chưa có trong `in`. Cần cơ chế giao dịch, khóa hoặc snapshot nhất quán theo yêu cầu hệ thống.

**Ghi nhớ:** **Thêm/xóa đỉnh hoặc cạnh không chỉ sửa một ô hay một list.** Mỗi liên kết có ID và hai đầu mút hợp lệ; các chỉ mục `out`, `in` hoặc `incident` phải phản ánh **đúng cùng tập liên kết**, đặc biệt khi có **khuyên và cạnh/cung song song**. Khi xóa đỉnh, xử lý **toàn bộ liên kết liên quan** và khử trùng ID của khuyên; khi xóa cạnh, chỉ xóa **đúng liên kết được chỉ định**. Chi phí cập nhật phụ thuộc vào biểu diễn: hash set thường **`O(1)` kỳ vọng** cho một liên kết, danh sách kề list phụ thuộc bậc, ma trận phải quản lý hàng/cột, còn CSR/CSC packed có thể cần **`O(n+m)`** khi chèn/xóa. Tính đúng đắn đòi hỏi **bất biến, định danh ổn định và đồng bộ các chỉ mục**.

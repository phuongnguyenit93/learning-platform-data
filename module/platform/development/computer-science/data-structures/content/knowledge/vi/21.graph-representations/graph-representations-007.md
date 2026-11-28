# Danh sách kề có thứ tự, tập kề và kiểm tra cạnh tồn tại

## 1. Cùng là danh sách kề, vì sao hiệu năng có thể khác nhau?

Trong mạng học phần, ứng dụng thường hỏi “học phần A có liên kết trực tiếp đến B không?”. Trong mạng xã hội, ứng dụng cần cả hai thao tác “A đã kết nối với B chưa?” và “liệt kê bạn bè của A theo mã tăng dần”. Hai kiểu truy vấn tưởng gần giống nhau nhưng có thể dẫn đến những lựa chọn **cấu trúc kề** khác nhau.

**Danh sách kề (adjacency list)** là ý tưởng lưu, với mỗi đỉnh `u`, những liên kết đi từ `u` tới các **đỉnh kề**. Cách cài đặt cụ thể có thể là:

- **Danh sách không sắp xếp:** thường thêm mục nhanh nhưng phải dò từng láng giềng khi kiểm tra cạnh.
- **Danh sách/mảng kề có thứ tự:** duy trì ID láng giềng tăng dần để tìm kiếm nhị phân và duyệt có thứ tự.
- **Tập kề (adjacency set):** dùng tập băm để kiểm tra sự hiện diện của láng giềng nhanh theo kỳ vọng.
- **Tập có thứ tự (ordered set):** dùng cấu trúc duy trì thứ tự, chẳng hạn cây tìm kiếm cân bằng.

Điểm quan trọng: **`O(n+m)` bộ nhớ của biểu diễn danh sách kề không đồng nghĩa mọi truy vấn kề đều `O(1)`**. Thời gian kiểm tra cạnh, thêm, xóa và duyệt phụ thuộc vào kiểu dữ liệu bên trong từng `adj[u]`.

Bài này sẽ phân tích những đánh đổi đó, minh họa việc lưu đồng thời **mảng kề có thứ tự và tập kề**, và nêu bất biến phải giữ để hai cấu trúc luôn biểu diễn **cùng một đồ thị**.

## 2. Quy ước đồ thị và bài toán kiểm tra cạnh

Cho đồ thị `G=(V,E)`, với `n=|V|` đỉnh và `m=|E|` cạnh hoặc cung. Gọi:

- `adj[u]`: các láng giềng được lưu tại đỉnh `u`.
- `deg(u)`: bậc trong đồ thị vô hướng.
- `outdeg(u)`: số cung đi ra từ `u` trong đồ thị có hướng.
- `d(u)`: **số mục kề** trong `adj[u]`; với đồ thị đơn không khuyên, nó bằng `deg(u)` hoặc `outdeg(u)` theo loại đồ thị.

Với **đồ thị có hướng**, cung `u → v` được biểu diễn bởi **`v` xuất hiện trong `adj[u]`**. Không được tự đưa `u` vào `adj[v]` nếu không có cung `v → u`.

Với **đồ thị vô hướng**, cạnh `{u,v}` giữa hai đỉnh khác nhau phải được phản ánh **ở cả hai phía**:

\[
v\in adj[u]\quad\Longleftrightarrow\quad u\in adj[v].
\]

Xét đồ thị vô hướng đơn `V={A,B,C,D,E}`, có các cạnh `{A,B}`, `{A,C}`, `{B,C}`, `{B,D}`, `{C,D}`. Nếu các láng giềng được sắp theo ID:

```text
      A ------ B
       \      /|
        \    / |
          C --- D          E (cô lập)

adj[A] = [B, C]
adj[B] = [A, C, D]
adj[C] = [A, B, D]
adj[D] = [B, C]
adj[E] = []
```

Để trả lời **“có cạnh B–D không?”**, ta chỉ cần kiểm tra **D có thuộc `adj[B]` hay không**. Nhưng chi phí phép “thuộc” này thay đổi đáng kể theo cách cài `adj[B]`.

Đỉnh E không có cạnh vẫn phải có mục `adj[E]=[]`. Không được suy ra tập đỉnh chỉ từ những đầu mút xuất hiện trong cạnh.

## 3. Danh sách kề không sắp xếp: đơn giản, nhưng phải quét khi tìm

Cách đầu tiên là dùng **list/vector** ở mỗi đỉnh và chèn láng giềng vào cuối:

```python
ke = {
    "A": ["C", "B"],
    "B": ["D", "C", "A"],
    "C": ["A", "D", "B"],
    "D": ["B", "C"],
    "E": [],
}

print("D" in ke["B"])  # True
```

Với `d(u)` mục trong list không sắp xếp:

- **Thêm một mục ở cuối:** `O(1)` **phân bổ** với mảng động, nếu đã biết mục đó chưa tồn tại và không cần duy trì thứ tự.
- **Kiểm tra có `v` trong `adj[u]` không:** `O(d(u))` **trường hợp xấu**, vì có thể phải kiểm tra tất cả mục.
- **Xóa một mục theo giá trị:** `O(d(u))` do phải tìm mục và có thể dời phần tử còn lại.
- **Duyệt toàn bộ láng giềng:** `\Theta(d(u))`.

Đây là lựa chọn tốt khi thao tác chủ yếu là **duyệt toàn bộ láng giềng**, thứ tự không quan trọng, hoặc dữ liệu được xây dựng một lần rồi xử lý bằng BFS/DFS. Tuy nhiên, để cài một **đồ thị đơn**, API `add_edge` thường phải kiểm tra **cạnh đã có chưa**. Bước kiểm tra đó cần `O(d(u))`, nên không thể tuyên bố cả thao tác chèn cạnh luôn `O(1)` chỉ từ chi phí `append`.

Thứ tự láng giềng trong list này chủ yếu phản ánh **thứ tự thêm**, không phải thứ tự theo giá trị ID. Nếu những cạnh đầu vào được đọc theo thứ tự khác, BFS/DFS có thể trả thứ tự thăm khác dù tập đỉnh tới được vẫn như nhau.

## 4. Danh sách kề có thứ tự: tìm nhị phân trên mảng

Giả sử ID đỉnh là chuỗi và mỗi `adj[u]` được lưu thành một **mảng tăng dần, không trùng**:

```text
adj[B] = [A, C, D]
          0  1  2
```

Ta có thể dùng **tìm kiếm nhị phân** để xác định D có xuất hiện hay không. Với mảng độ dài `d(u)`, chi phí tìm là:

\[
T_{\text{kiểm tra cạnh}}=O(\log(d(u)+1)).
\]

Viết `\log(d+1)` giúp biểu thức có ý nghĩa cả khi `d=0`; với `d\ge2`, đó vẫn là `O(\log d)`.

Trong Python, `bisect_left` tìm vị trí mà một giá trị nên xuất hiện trong mảng đã sắp xếp:

```python
from bisect import bisect_left


def co_lan_can_sap_xep(ds: list[str], v: str) -> bool:
    i = bisect_left(ds, v)
    return i < len(ds) and ds[i] == v


ds = ["A", "C", "D"]
print(co_lan_can_sap_xep(ds, "D"))  # True
print(co_lan_can_sap_xep(ds, "B"))  # False
```

**Điều kiện để tìm nhị phân đúng:** list phải được sắp theo **cùng một quan hệ thứ tự** mà phép `bisect` sử dụng. Nếu một chỗ so sánh ID bằng chữ thường, chỗ khác dùng chuẩn hóa không phân biệt hoa/thường, cần quy tắc nhất quán; không được sắp theo một khóa mà tìm theo một khóa khác.

### Thêm và xóa vẫn phải dời phần tử

Giữ `adj[B]=[A,C,D]`, muốn thêm láng giềng `B2` (với `"A" < "B2" < "C"` theo thứ tự từ điển), ta tìm vị trí bằng `bisect_left` rồi **chèn vào giữa mảng**:

```python
from bisect import insort

ds = ["A", "C", "D"]
insort(ds, "B2")
print(ds)  # ['A', 'B2', 'C', 'D']
```

Tìm vị trí chỉ mất `O(\log(d+1))` phép so sánh, nhưng `list.insert` có thể phải **dời `O(d)` phần tử**. Vì thế:

- Kiểm tra cạnh bằng tìm nhị phân: `O(\log(d+1))`.
- Thêm/xóa láng giềng trong mảng có thứ tự: `O(d)` trường hợp xấu.
- Duyệt láng giềng theo thứ tự tăng: `\Theta(d)`, **không phải sắp xếp lại mỗi lần duyệt**.

Đặc điểm này phù hợp khi đồ thị **được đọc rất nhiều nhưng ít cập nhật**, và những láng giềng cần xuất hiện theo thứ tự ổn định.

Một **danh sách liên kết đã sắp xếp** không có truy cập chỉ số trực tiếp, nên không tự có lợi thế tìm nhị phân `O(\log d)` của **mảng đã sắp xếp**. Trong trường hợp đó tìm phần tử theo thứ tự vẫn thường cần đi qua các nút và tốn `O(d)`.

## 5. Tập kề bằng hash set: kiểm tra cạnh nhanh theo kỳ vọng

Nếu lưu mỗi `adj[u]` là một **tập băm (hash set)**, ta có thể hỏi trực tiếp `v in adj[u]`:

```python
ke_tap = {
    "A": {"B", "C"},
    "B": {"A", "C", "D"},
    "C": {"A", "B", "D"},
    "D": {"B", "C"},
    "E": set(),
}

print("D" in ke_tap["B"])  # True
print("E" in ke_tap["B"])  # False
```

Với giả định hàm băm phân bố phù hợp, hệ số tải được kiểm soát và phép băm/so sánh ID đủ rẻ:

- **Kiểm tra láng giềng:** `O(1)` **kỳ vọng**.
- **Thêm/xóa láng giềng:** `O(1)` **kỳ vọng và phân bổ**.
- **Duyệt toàn bộ láng giềng:** `O(d(u))` để xuất ra các phần tử, nếu đang dùng iterator của set.
- **Bộ nhớ:** `O(n+m)` về số phần tử của đồ thị, thường có **overhead lớn hơn list**.

Một ưu điểm tự nhiên là **tính duy nhất**: thêm cùng `v` vào `adj[u]` lần nữa không tạo bản sao. Nhưng chỉ gọi `set.add(v)` không đủ để tự báo lỗi “cạnh đã tồn tại”; nếu API đồ thị đơn muốn **từ chối trùng**, cần kiểm tra và quyết định hành vi rõ ràng.

**Không được nhầm thời gian kỳ vọng với bảo đảm xấu nhất.** Va chạm hash, khóa bất lợi hoặc chi phí băm chuỗi dài có thể khiến một thao tác đắt hơn. Tập băm không bảo đảm thứ tự duyệt **tăng dần theo ID**, dù một lần chạy cụ thể có vẻ xuất ra theo thứ tự nào đó.

### Khi liên kết có trọng số

Nếu mỗi cặp đỉnh theo chiều phù hợp có **tối đa một cạnh/cung**, một **hash map** có thể vừa kiểm tra cạnh vừa lưu trọng số:

```python
ke_trong_so = {
    "A": {"B": 0, "C": 7},
    "B": {},
    "C": {},
}

print("B" in ke_trong_so["A"])      # True
print(ke_trong_so["A"]["B"])       # 0: cạnh có trọng số bằng 0
```

Phải kiểm tra **sự hiện diện của khóa** (`"B" in ke_trong_so["A"]`), không dùng `if ke_trong_so["A"].get("B")`, vì giá trị trọng số `0` là hợp lệ nhưng là falsy.

Nếu cần **nhiều cạnh song song** giữa cùng hai đỉnh, một map `neighbor -> weight` sẽ ghi đè. Khi đó có thể lưu `neighbor -> [edge_id,...]` và bảng cạnh riêng theo ID, hoặc dùng danh sách mục kề kèm ID.

## 6. Tập kề có thứ tự bằng cây cân bằng

Một lựa chọn khác là dùng **tập có thứ tự (ordered set)** dựa trên cây tìm kiếm nhị phân cân bằng, chẳng hạn AVL hay Red–Black Tree. Với `d` láng giềng của một đỉnh:

| Thao tác | Cây tìm kiếm cân bằng |
| --- | --- |
| Tìm/kiểm tra láng giềng | `O(\log(d+1))` trường hợp xấu |
| Thêm một láng giềng | `O(\log(d+1))` trường hợp xấu |
| Xóa một láng giềng | `O(\log(d+1))` trường hợp xấu |
| Duyệt tất cả theo thứ tự | `O(d)` |
| Tìm láng giềng đầu tiên `>= x` | `O(\log(d+1))` với phép lower-bound |

Cây cân bằng tránh **dịch chuyển tuyến tính** khi chèn giữa mảng đã sắp xếp, nhưng phải trả thêm chi phí cấp phát nút, con trỏ và duy trì cân bằng. ID cũng cần có **thứ tự so sánh nhất quán**, không chỉ khả năng băm.

**Phân biệt với Python `set`:** `set` của Python là một bảng băm, **không phải ordered set dựa trên cây cân bằng**. Nếu cần cây cân bằng trong Python, phải dùng một cấu trúc/thư viện khác hoặc tự cài; `sorted(my_set)` chỉ tạo **danh sách đã sắp xếp tại thời điểm gọi**, không biến tập thành cây cân bằng.

## 7. Bảng so sánh chi phí theo số láng giềng

Đặt `d=d(u)`. Các cận dưới đây xét **đồ thị đơn**, ID có chi phí so sánh/băm `O(1)` và cấu trúc láng giềng đã được tạo sẵn. Với đồ thị vô hướng, cập nhật cạnh `{u,v}` phải cập nhật **cả hai phía**, nên chi phí là tổng chi phí trên `d(u)` và `d(v)`.

| Cấu trúc cho `adj[u]` | Kiểm tra `u→v` | Thêm láng giềng (có kiểm tra trùng) | Xóa láng giềng | Duyệt theo ID tăng dần |
| --- | --- | --- | --- | --- |
| List/vector **không sắp xếp** | `O(d)` | `O(d)` để kiểm tra + `O(1)` append phân bổ | `O(d)` | Phải sắp xếp thêm: `O(d\log d)` |
| **Mảng đã sắp xếp** | `O(\log(d+1))` | `O(d)` do dời phần tử | `O(d)` do dời phần tử | `O(d)` |
| **Hash set / hash map** | `O(1)` kỳ vọng | `O(1)` kỳ vọng/phân bổ | `O(1)` kỳ vọng | Phải sắp xếp thêm: `O(d\log d)` |
| **Ordered set trên cây cân bằng** | `O(\log(d+1))` xấu nhất | `O(\log(d+1))` xấu nhất | `O(\log(d+1))` xấu nhất | `O(d)` |

Giả định “đã biết ID đỉnh” còn giúp tách phần chi phí lấy `adj[u]` từ cấu trúc ngoài. Nếu `adj` là một `dict` với khóa chuỗi, việc định vị `adj[u]` cũng dùng hash và có thể chịu chi phí băm/so sánh chuỗi. Với ID là chỉ số nguyên nhỏ và mảng `adj[0...n-1]`, bước định vị đó là `O(1)` theo chỉ số.

Không nên viết “`O(1)` cho truy vấn cạnh” nếu **thực tế đang dùng list**: chỉ sự khác biệt một lớp chứa bên trong cũng có thể làm thời gian kiểm tra chuyển từ tuyến tính theo bậc sang logarit hoặc hằng số kỳ vọng.

## 8. Thứ tự kề mang lại chức năng gì ngoài việc in đẹp?

Giữ láng giềng đã sắp xếp theo ID có ích khi:

1. **Xuất kết quả ổn định:** cùng dữ liệu cho ra cùng thứ tự nếu quy tắc so sánh ID cố định.
2. **Duyệt theo một quy tắc xác định:** BFS/DFS chọn những láng giềng theo thứ tự đã quy định; điều này thuận tiện cho kiểm thử và giải thích bước duyệt.
3. **Tìm láng giềng trong khoảng ID:** với mảng tăng dần, `bisect_left` và `bisect_right` xác định biên trong `O(\log(d+1))`, rồi trả `r` mục trong `O(r)`.
4. **Tìm hai đỉnh có láng giềng chung:** nếu cả hai danh sách đã sắp xếp, có thể dùng **hai con trỏ** và bỏ qua nhiều phép kiểm tra thành viên lặp lại.

Ví dụ hai danh sách có thứ tự:

```text
adj[A] = [B, C, E, H]
adj[D] = [A, C, F, H]
          ^  ^  ^  ^

Láng giềng chung = [C, H]
```

**Hai con trỏ** có thể tìm giao hai mảng tăng dần trong `O(d(A)+d(D))` thời gian:

```python
def lang_gieng_chung(ds1: list[str], ds2: list[str]) -> list[str]:
    i = j = 0
    ket_qua = []
    while i < len(ds1) and j < len(ds2):
        if ds1[i] == ds2[j]:
            ket_qua.append(ds1[i])
            i += 1
            j += 1
        elif ds1[i] < ds2[j]:
            i += 1
        else:
            j += 1
    return ket_qua


print(lang_gieng_chung(
    ["B", "C", "E", "H"], ["A", "C", "F", "H"]
))  # ['C', 'H']
```

Nếu mỗi `adj[u]` là **hash set**, ta có thể duyệt tập nhỏ hơn và kiểm tra từng phần tử trong tập lớn hơn. Khi đó chi phí kỳ vọng thường là `O(\min(d(u),d(v)))` để tìm các phần tử chung, cộng chi phí ghi kết quả, với giả định hashing tốt. Phương pháp này không tự trả kết quả theo thứ tự; nếu cần đầu ra tăng dần, phải sắp xếp.

**Thứ tự cục bộ không phải thứ tự toàn đồ thị:** `adj[u]` tăng dần chỉ nói về thứ tự **láng giềng của một đỉnh**. Nó không biến đồ thị thành cây tìm kiếm, không tự sắp xếp tất cả cạnh theo trọng số và không tự giải quyết bài toán đường đi ngắn nhất.

## 9. Cách kết hợp hai chỉ mục: mảng kề có thứ tự và tập kề

Đôi khi ứng dụng cần **cả hai**:

- Kiểm tra nhanh `u` có nối `v` không, bằng `v in ke_tap[u]`.
- Duyệt láng giềng của `u` theo ID tăng dần, bằng `ke_sap_xep[u]`.

Có thể lưu **hai cấu trúc cho cùng tập láng giềng**:

```text
Đỉnh B:

ke_tap[B]    = {D, A, C}  (hash set, không có thứ tự tăng)
ke_sap_xep[B] = [A, C, D] (mảng có thứ tự)

Bất biến: set(ke_sap_xep[B]) == ke_tap[B]
```

Thêm/xóa một cạnh phải sửa **cả hai chỉ mục**. Nhờ đó:

- Kiểm tra cạnh: `O(1)` **kỳ vọng** qua set.
- Duyệt láng giềng có thứ tự: `O(d)` qua mảng.
- Thêm/xóa cạnh: **vẫn có thể `O(d)`** do phải duy trì mảng đã sắp xếp; không được cộng hai lợi ích đọc rồi quên chi phí ghi.
- Bộ nhớ: tăng hệ số hằng vì mỗi quan hệ kề được lưu hai lần, nhưng vẫn `O(n+m)` về số mục.

**Đây là một lựa chọn có đánh đổi**, phù hợp khi truy vấn đọc rất nhiều và số lần thay đổi cạnh thấp. Nếu cập nhật thường xuyên, một ordered set dựa trên cây cân bằng hoặc một cách chỉ mục khác có thể hợp lý hơn.

## 10. Python: đồ thị với hai chỉ mục kề đồng bộ

Ví dụ sau hiện thực **đồ thị đơn** có hướng hoặc vô hướng, với ID đỉnh là chuỗi và **thứ tự từ điển Python**. Để quan sát rõ vấn đề khuyên, ví dụ cho phép `u==v`, nhưng với đồ thị vô hướng chỉ lưu khuyên **một lần** trong tập/mảng kề và cộng thêm 1 khi tính bậc.

Lớp không hỗ trợ cạnh song song vì `set` cố ý chỉ giữ một láng giềng `v` cho mỗi đỉnh `u`. Nó cũng không lưu trọng số; có thể mở rộng bằng `neighbor -> weight` nếu đồ thị có trọng số nhưng đơn.

```python
from bisect import bisect_left
from collections import deque


class DoThiKeHaiChiMuc:
    def __init__(self, co_huong: bool = False):
        self.co_huong = co_huong
        self.ke_tap = {}       # vertex_id -> set(neighbor_id)
        self.ke_sap_xep = {}   # vertex_id -> sorted list(neighbor_id)
        self.so_canh = 0       # Số cạnh vô hướng/cung có hướng

    def _kiem_tra_dinh(self, u: str):
        if u not in self.ke_tap:
            raise KeyError(f"Đỉnh không tồn tại: {u}")

    def them_dinh(self, u: str):
        if u in self.ke_tap:
            raise ValueError("Đỉnh đã tồn tại")
        self.ke_tap[u] = set()
        self.ke_sap_xep[u] = []  # Giữ cả đỉnh cô lập

    def _chen_mot_chieu(self, u: str, v: str):
        # Tiền điều kiện: v chưa có trong ke_tap[u].
        ds = self.ke_sap_xep[u]
        i = bisect_left(ds, v)
        ds.insert(i, v)
        self.ke_tap[u].add(v)

    def _xoa_mot_chieu(self, u: str, v: str):
        # Tiền điều kiện: v có trong cả hai chỉ mục.
        ds = self.ke_sap_xep[u]
        i = bisect_left(ds, v)
        if i == len(ds) or ds[i] != v:
            raise RuntimeError("Hai chỉ mục kề không đồng bộ")
        ds.pop(i)
        self.ke_tap[u].remove(v)

    def co_canh(self, u: str, v: str) -> bool:
        self._kiem_tra_dinh(u)
        self._kiem_tra_dinh(v)
        return v in self.ke_tap[u]  # O(1) kỳ vọng

    def them_canh(self, u: str, v: str):
        self._kiem_tra_dinh(u)
        self._kiem_tra_dinh(v)
        if v in self.ke_tap[u]:
            raise ValueError("Cạnh/cung đã tồn tại")
        self._chen_mot_chieu(u, v)
        if not self.co_huong and u != v:
            self._chen_mot_chieu(v, u)
        self.so_canh += 1

    def xoa_canh(self, u: str, v: str):
        self._kiem_tra_dinh(u)
        self._kiem_tra_dinh(v)
        if v not in self.ke_tap[u]:
            raise KeyError("Cạnh/cung không tồn tại")
        self._xoa_mot_chieu(u, v)
        if not self.co_huong and u != v:
            self._xoa_mot_chieu(v, u)
        self.so_canh -= 1

    def lang_gieng_sap_xep(self, u: str):
        self._kiem_tra_dinh(u)
        return list(self.ke_sap_xep[u])  # Bản sao tránh sửa từ bên ngoài

    def bac(self, u: str) -> int:
        if self.co_huong:
            raise ValueError("Dùng bậc ra/bậc vào cho đồ thị có hướng")
        self._kiem_tra_dinh(u)
        # Khuyên vô hướng lưu một mục nhưng đóng góp bậc 2.
        return len(self.ke_tap[u]) + (u in self.ke_tap[u])

    def bac_ra(self, u: str) -> int:
        if not self.co_huong:
            raise ValueError("Đồ thị vô hướng")
        self._kiem_tra_dinh(u)
        return len(self.ke_tap[u])

    def bac_vao(self, v: str) -> int:
        if not self.co_huong:
            raise ValueError("Đồ thị vô hướng")
        self._kiem_tra_dinh(v)
        # Duyệt n tập kề; mỗi phép thuộc là O(1) kỳ vọng.
        return sum(v in ds for ds in self.ke_tap.values())

    def bfs(self, bat_dau: str):
        self._kiem_tra_dinh(bat_dau)
        da_tham = {bat_dau}
        hang_doi = deque([bat_dau])
        thu_tu = []
        while hang_doi:
            u = hang_doi.popleft()
            thu_tu.append(u)
            # Duyệt láng giềng theo ID tăng dần:
            for v in self.ke_sap_xep[u]:
                if v not in da_tham:
                    da_tham.add(v)
                    hang_doi.append(v)
        return thu_tu


# Đồ thị vô hướng, chèn cạnh KHÔNG theo thứ tự tăng dần.
g = DoThiKeHaiChiMuc()
for dinh in "ABCDE":
    g.them_dinh(dinh)
for u, v in [
    ("A", "C"), ("B", "D"), ("A", "B"),
    ("C", "D"), ("B", "C"),
]:
    g.them_canh(u, v)

print(g.lang_gieng_sap_xep("B"))  # ['A', 'C', 'D']
print(g.co_canh("B", "D"))        # True
print(g.co_canh("A", "D"))        # False
print(g.bfs("A"))                 # ['A', 'B', 'C', 'D']
print(g.bfs("E"))                 # ['E'] (đỉnh cô lập)
print([g.bac(u) for u in "ABCDE"])  # [2, 3, 3, 2, 0]
print(g.so_canh)                 # 5

g.them_canh("B", "B")            # Khuyên vô hướng
print(g.lang_gieng_sap_xep("B"))  # ['A', 'B', 'C', 'D']
print(g.bac("B"))               # 5: khuyên đóng góp 2
print(sum(g.bac(u) for u in "ABCDE"))  # 12 = 2 * 6

g.xoa_canh("B", "D")
print(g.co_canh("D", "B"))       # False: đã xóa hai mục đối ứng
print(g.lang_gieng_sap_xep("B"))  # ['A', 'B', 'C']
print(g.so_canh)                # 5
print(all(
    g.ke_sap_xep[u] == sorted(g.ke_tap[u])
    for u in g.ke_tap
))  # True: hai chỉ mục nhất quán

# Đồ thị có hướng: B không tự có cung ngược về A.
h = DoThiKeHaiChiMuc(co_huong=True)
for dinh in "ABC":
    h.them_dinh(dinh)
h.them_canh("A", "B")
h.them_canh("A", "C")
h.them_canh("C", "B")
h.them_canh("B", "B")            # Cung khuyên
print(h.lang_gieng_sap_xep("A")) # ['B', 'C']
print(h.co_canh("B", "A"))       # False
print(h.bac_ra("B"), h.bac_vao("B"))  # 1 3
```

**Độ phức tạp của ví dụ:** `co_canh` dùng hash set nên `O(1)` kỳ vọng; `lang_gieng_sap_xep(u)` sao chép `d(u)` mục nên `O(d(u))`; `them_canh` và `xoa_canh` có thể tốn `O(d(u)+d(v))` cho cạnh vô hướng vì mảng đã sắp xếp phải dời phần tử. `bac(u)` và `bac_ra(u)` là `O(1)` kỳ vọng; `bac_vao(v)` quét `n` tập nên là `O(n)` **kỳ vọng** khi thao tác kiểm tra thuộc set đủ rẻ.

Việc dùng hai chỉ mục làm ví dụ dễ kiểm soát những phép tra cứu đọc. Trong hệ thống có **truy cập đồng thời**, thêm/xóa cạnh phải được bảo vệ khỏi những lần đọc thấy trạng thái mới ở một chỉ mục nhưng trạng thái cũ ở chỉ mục còn lại; cần cơ chế đồng bộ hoặc giao dịch thích hợp. Ví dụ không triển khai xóa đỉnh hoặc phục hồi khi lỗi cấp phát giữa các bước cập nhật.

## 11. Đếm bậc, khuyên, đồ thị có hướng và đa đồ thị

Chọn list hay set không thay đổi các **định nghĩa đồ thị**:

### Vô hướng

Với cạnh `{u,v}`, `u\ne v`, phải cập nhật cả `adj[u]` và `adj[v]`. Khi không có khuyên, `deg(u)=|adj[u]|` với đồ thị đơn dùng tập láng giềng.

Khuyên `{u,u}` chỉ tạo **một phần tử `u` trong set `adj[u]`**, nhưng theo quy ước bậc chuẩn:

\[
\deg(u)=|adj[u]|+\mathbf{1}_{\{u\in adj[u]\}},
\]

vì khuyên đóng góp **2 vào bậc** dù set chỉ lưu một phần tử. Bất biến đếm tổng bậc vẫn là:

\[
\sum_{u\in V}\deg(u)=2m.
\]

### Có hướng

Với cung `u→v`, chỉ cập nhật `out[u]`. Bậc ra của `u` là số phần tử trong tập cung đi ra, còn bậc vào của `v` cần **danh sách cung đi vào**, bộ đếm phụ hoặc quét những cung của các nguồn.

Một cung khuyên `u→u` đóng góp 1 vào **cả bậc ra và bậc vào**. Luôn có:

\[
\sum_{u\in V}\operatorname{outdeg}(u)
=\sum_{u\in V}\operatorname{indeg}(u)=m.
\]

### Đa đồ thị

Nếu hai cạnh `e0`, `e1` cùng nối A–B, set `adj[A]={B}` chỉ ghi nhận **một láng giềng phân biệt**, không biểu diễn **hai cạnh riêng**. Muốn giữ đa cạnh/cung, có thể dùng:

```text
edges[0] = (A, B, weight=5)
edges[1] = (A, B, weight=7)

adj[A][B] = [0, 1]  # danh sách edge ID thay vì một Boolean
```

Nếu chỉ cần kiểm tra “có ít nhất một cạnh không?”, set láng giềng vẫn hữu ích như **chỉ mục phụ**. Nhưng khi xóa e0 mà e1 còn tồn tại, **không được xóa B khỏi set kề của A**. Chỉ khi số cạnh A–B trở về 0 mới loại láng giềng khỏi tập.

## 12. Xây dựng một lần hay cập nhật liên tục?

Không có cấu trúc “tốt nhất cho mọi thao tác”. Tỷ lệ **đọc/ghi** là yếu tố quyết định:

**Đồ thị tĩnh, nhiều lần kiểm tra cạnh và duyệt có thứ tự.** Có thể:

1. Đọc toàn bộ `m` cạnh; tạo danh sách láng giềng cho `n` đỉnh.
2. Sắp xếp và loại trùng theo chính sách đồ thị đơn.
3. Giữ mảng kề đã sắp xếp để tìm nhị phân hoặc duyệt tăng dần.

Chi phí xây dựng điển hình là:

\[
O\!\left(n+m+\sum_{u\in V}d(u)\log(d(u)+1)\right),
\]

và có thể chặn bởi `O(n+m\log(\Delta+1))` nếu `\Delta=\max_{u\in V}d(u)` và mỗi mục có chi phí so sánh hằng số. Cách này tránh **chèn vào giữa mảng nhiều lần** trong quá trình đọc dữ liệu.

**Đồ thị thay đổi thường xuyên, ưu tiên kiểm tra cạnh.** Hash set/map láng giềng có thể phù hợp vì thêm/xóa thường `O(1)` kỳ vọng, miễn là ứng dụng không cần duyệt theo thứ tự tăng ở mọi lần.

**Đồ thị thay đổi thường xuyên và vẫn cần duyệt có thứ tự.** Cân nhắc ordered set trên cây cân bằng để giảm chi phí dịch chuyển mảng, hoặc dùng chiến lược **cập nhật theo lô** rồi sắp xếp lại khi cần.

**Nhiều truy vấn cực trị/khoảng theo ID láng giềng.** Mảng kề có thứ tự hoặc cây có thứ tự có thể hỗ trợ lower-bound, duyệt khoảng hoặc giao hai danh sách hiệu quả hơn tập băm không sắp xếp.

Nếu mỗi đỉnh có rất ít láng giềng (`d(u)` nhỏ), một list đơn giản có thể có chi phí thực tế thấp dù cận lý thuyết tìm là `O(d(u))`. Không nên bỏ qua độ phức tạp **bộ nhớ, hằng số và đặc điểm dữ liệu thực** khi lựa chọn.

## 13. Những lỗi thường gặp

1. **Gọi mọi biểu diễn kề là “danh sách” rồi coi kiểm tra cạnh luôn `O(1)`.** List không sắp xếp cần `O(d(u))); mảng có thứ tự `O(\log(d+1))); hash set `O(1)` kỳ vọng.
2. **Dùng `bisect` trên list chưa được sắp xếp.** Kết quả tìm có thể sai dù mọi cạnh đều đã được thêm.
3. **Tưởng tìm vị trí `O(\log d)` nghĩa chèn vào mảng cũng `O(\log d)`.** Dời phần tử có thể tốn `O(d)`.
4. **Tin rằng hash set tự trả láng giềng tăng dần.** Thứ tự duyệt không được bảo đảm theo ID.
5. **Xem `sorted(set)` là cấu trúc tự duy trì thứ tự.** Nó chỉ tạo một danh sách được sắp tại thời điểm gọi.
6. **Chèn vào hai chỉ mục nhưng chỉ xóa ở một chỉ mục.** Khi đó `co_canh` và danh sách láng giềng có thể trả kết quả mâu thuẫn.
7. **Quên cập nhật chiều đối ứng trong đồ thị vô hướng.** Quan hệ kề không còn đối xứng.
8. **Tạo chiều ngược không có thật trong đồ thị có hướng.** Kết quả duyệt và khả năng tới được bị sai.
9. **Đếm khuyên vô hướng bằng một lần xuất hiện trong set.** Theo quy ước bậc chuẩn khuyên đóng góp 2.
10. **Dùng một set láng giềng làm dữ liệu duy nhất của đa đồ thị.** Các cạnh song song, ID và trọng số riêng bị gộp mất.
11. **Không giữ đỉnh cô lập.** Dù `adj[u]` rỗng, `u` vẫn thuộc tập đỉnh.
12. **Chọn cấu trúc chỉ theo một benchmark đọc.** Phải tính cả cập nhật, tạo chỉ mục, bộ nhớ và tính nhất quán.

## 14. Tự kiểm tra

**Câu 1.** Danh sách `adj[A]=[B,C,D,E]` đã được sắp theo ID. Chi phí kiểm tra `A→D` bằng tìm nhị phân là bao nhiêu theo bậc `d(A)`? Nếu list không được sắp thì sao?

**Đáp án:** Với mảng tăng dần, `O(\log(d(A)+1))`; với list không sắp xếp, kiểm tra tuyến tính cần `O(d(A))` trường hợp xấu.

**Câu 2.** Vì sao chèn `B2` vào giữa `[A,C,D]` vẫn có thể tốn `O(d)` dù `bisect_left` tìm vị trí trong `O(\log d)`?

**Đáp án:** Mảng động phải dời những phần tử đứng sau vị trí chèn; bước dịch chuyển có thể tuyến tính theo số láng giềng.

**Câu 3.** Đồ thị đơn dùng `adj[u]` là hash set. Thời gian kiểm tra `v in adj[u]` là `O(1)` trong mọi trường hợp hay không?

**Đáp án:** Không. Thông thường đó là **`O(1)` kỳ vọng**, phụ thuộc hàm băm, tải và chi phí xử lý khóa; trường hợp xấu vẫn có thể lớn hơn.

**Câu 4.** Vì sao `sorted(adj_set[A])` không thể thay hoàn toàn ordered set nếu đồ thị thêm/xóa liên tục và phải luôn giữ thứ tự?

**Đáp án:** `sorted` tạo danh sách mới tại một thời điểm với chi phí sắp xếp, không tự cập nhật khi tập gốc thay đổi. Cần sắp lại hoặc duy trì một chỉ mục có thứ tự.

**Câu 5.** Với `adj[A]=[B,C,E,H]` và `adj[D]=[A,C,F,H]`, giao hai danh sách tăng dần là gì và có thể tìm trong thời gian nào?

**Đáp án:** Giao là `[C,H]`. Thuật toán hai con trỏ tốn `O(d(A)+d(D))` thời gian.

**Câu 6.** Trong lớp Python có hai chỉ mục, thêm một cạnh vô hướng `{B,D}` phải thay đổi những cấu trúc nào?

**Đáp án:** Phải cập nhật cả `ke_tap[B]`, `ke_sap_xep[B]`, `ke_tap[D]` và `ke_sap_xep[D]`; đồng thời cập nhật bộ đếm cạnh. Nếu là khuyên `{B,B}`, chỉ thêm một mục láng giềng B ở mỗi chỉ mục của B theo quy ước bài này.

**Câu 7.** Một đỉnh B trong đồ thị vô hướng có tập láng giềng `{A,B,C}`, trong đó B là khuyên. Bậc của B bằng bao nhiêu?

**Đáp án:** `deg(B)=|{A,B,C}|+1=4`: hai cạnh tới A, C đóng góp 2 và khuyên đóng góp thêm 2.

**Câu 8.** Có cung `A→B` trong đồ thị có hướng. Vì sao `A in adj[B]` có thể là `False` dù `B in adj[A]` là `True`?

**Đáp án:** Vì danh sách kề lưu **cung đi ra**, cung ngược `B→A` không tự tồn tại.

**Câu 9.** Hai cạnh song song A–B được lưu dưới ID e0 và e1. Nếu xóa e0, có được xóa B khỏi set láng giềng của A ngay không?

**Đáp án:** Không nếu e1 còn tồn tại. Tập kề kiểu Boolean phải tiếp tục phản ánh **còn ít nhất một** cạnh A–B; chỉ loại B sau khi không còn cạnh nào giữa hai đỉnh.

**Câu 10.** Ứng dụng phải thêm/xóa cạnh rất thường xuyên, truy vấn cạnh tồn tại nhiều, nhưng ít khi cần sắp thứ tự láng giềng. Nên cân nhắc biểu diễn nào trước?

**Đáp án:** Hash set/map ở mỗi đỉnh là lựa chọn đáng cân nhắc: kiểm tra/thêm/xóa thường `O(1)` kỳ vọng, không phải duy trì mảng sắp xếp sau mỗi cập nhật. Cần kiểm tra các ràng buộc khác như trọng số, đa cạnh, bộ nhớ và đầu vào bất lợi.

**Ghi nhớ:** **Danh sách kề có thứ tự** giúp tìm nhị phân `O(\log(d+1))` trên mảng tăng dần và duyệt láng giềng theo thứ tự `O(d)`, nhưng chèn/xóa mảng vẫn có thể tốn `O(d)`. **Tập kề bằng hash set** thường kiểm tra/thêm/xóa trong **`O(1)` kỳ vọng**, song không tự duy trì thứ tự tăng dần. **Ordered set** trên cây cân bằng có thể dung hòa cập nhật và truy vấn có thứ tự với `O(\log(d+1))` cho tìm/thêm/xóa. Nếu lưu nhiều chỉ mục, tính đúng đắn phụ thuộc vào việc **cập nhật nhất quán**, giữ hướng cạnh, xử lý khuyên/đa cạnh và bảo toàn đỉnh cô lập.

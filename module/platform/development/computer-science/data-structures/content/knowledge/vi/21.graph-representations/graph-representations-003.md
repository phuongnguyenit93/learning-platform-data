# Khuyên, cạnh song song và yêu cầu biểu diễn đa đồ thị

## 1. Một cặp đỉnh có thể mang nhiều liên kết khác nhau

Giả sử mạng giao thông có hai tuyến xe độc lập cùng nối ga A và ga B: tuyến số 7 dài 5 km, tuyến số 12 dài 8 km. Nếu chỉ lưu `A: {B: 5}`, sau khi thêm tuyến thứ hai bằng `A[B] = 8`, dữ liệu của tuyến đầu tiên bị **ghi đè**. Trong một tình huống khác, đỉnh B có một tuyến vòng khởi hành và quay về chính B; nếu cấm mọi liên kết có cùng đầu mút, ta sẽ không lưu được tuyến đó.

Hai hiện tượng cần mô hình hóa là:

- **Khuyên (self-loop):** một cạnh hoặc cung nối một đỉnh với chính nó.
- **Cạnh/cung song song (parallel edges/arcs):** nhiều liên kết riêng biệt có **cùng cặp đầu mút** (với cung còn phải cùng hướng).

Một **đa đồ thị (multigraph)** cho phép nhiều liên kết phân biệt giữa cùng các đỉnh. Tùy tài liệu, đa đồ thị có thể cho phép hoặc không cho phép khuyên; mô hình cho phép cả khuyên lẫn cạnh song song đôi khi được gọi là **giả đồ thị (pseudograph)**. Trong bài này, ta quy ước rõ ràng rằng **đa đồ thị có thể chứa cả hai** để tập trung vào cách biểu diễn dữ liệu.

Điểm quan trọng không phải cách gọi mà là **hợp đồng cấu trúc**: liên kết nào được phép tồn tại, hai liên kết được coi là một hay hai, và thao tác xóa/tìm/đếm phải làm gì với chúng.

## 2. Phân biệt đồ thị đơn, đa đồ thị và khuyên

Với `V` là tập đỉnh và `E` là tập **các liên kết có định danh riêng**, ta có thể xét:

| Mô hình | Nhiều liên kết cùng đầu mút? | Khuyên? | Ví dụ |
| --- | --- | --- | --- |
| Đồ thị vô hướng đơn không khuyên | Không | Không | Một quan hệ “có kết nối” giữa A và B |
| Đồ thị có hướng đơn không khuyên | Không cho cùng cặp có thứ tự | Không | Một cung A→B và một cung B→A vẫn là hai cung khác nhau |
| Đa đồ thị vô hướng | Có | Theo quy ước của mô hình | Nhiều đường tàu nối A và B |
| Đa đồ thị có hướng | Có nhiều cung cùng chiều | Theo quy ước của mô hình | Nhiều chuyến bay A→B có mã chuyến riêng |

Trong một đồ thị vô hướng đơn, **cạnh `{A,B}` chính là `{B,A}`**. Trong một đồ thị có hướng, **cung `(A,B)` khác cung `(B,A)`**. Với đa đồ thị, ngay cả khi hai cạnh cùng nối `A` và `B`, ta vẫn có thể giữ chúng là hai đối tượng khác nhau.

```text
Đồ thị vô hướng đơn:        A ------ B
Đa đồ thị vô hướng:         A ====== B    e0 và e1 cùng đầu mút
Khuyên tại B:               B --+
                             |  |
                             +--+

Đa đồ thị có hướng:         A ==>> B     a0 và a1: A -> B
                            A <--- B     a2: B -> A (khác hướng)
```

Một ví dụ mô hình hóa cho ba chuyến bay có thể là:

```text
a0: (nguồn=HAN, đích=SGN, giờ=08:00)
a1: (nguồn=HAN, đích=SGN, giờ=14:00)
a2: (nguồn=SGN, đích=HAN, giờ=16:00)
```

`a0` và `a1` là **hai cung song song cùng hướng**, còn `a2` có hướng ngược lại. Nếu dữ liệu chỉ có tập cặp `(HAN, SGN)`, ta không thể lưu đủ ba chuyến.

## 3. Mô hình toán học: liên kết là đối tượng, không chỉ là cặp đỉnh

Đối với đồ thị đơn, ta thường viết `G=(V,E)` với `E` là một tập cặp đầu mút. Tập không chứa hai bản sao của cùng phần tử, vì vậy cách viết đó **không trực tiếp biểu diễn được hai cạnh song song**.

Đối với đa đồ thị, nên tách:

- `V`: tập định danh đỉnh;
- `E`: tập định danh cạnh hoặc cung;
- `endpoints`: ánh xạ từ **định danh liên kết** đến các đầu mút của liên kết;
- `w` (tùy chọn): ánh xạ từ ID liên kết đến trọng số, nhãn hoặc thuộc tính khác.

Với đa đồ thị có hướng, ánh xạ đầu mút có dạng:

\[
\operatorname{endpoints}:E\to V\times V.
\]

Chẳng hạn:

\[
\operatorname{endpoints}(a_0)=(A,B),\qquad
\operatorname{endpoints}(a_1)=(A,B).
\]

Hai cung vẫn phân biệt vì `a_0 \ne a_1`, mặc dù nguồn và đích giống nhau.

Với đa đồ thị vô hướng, hai đầu mút **không có thứ tự**. Ta có thể xem `endpoints(e)` là một **cặp không thứ tự có thể lặp phần tử**, để biểu diễn cả `{B,B}` là khuyên. Trong chương trình, có thể lưu một tuple `(u,v)` và quy định rằng đảo `(v,u)` không làm thay đổi ý nghĩa của cạnh.

**Không nên dùng** `set` thông thường của hai đầu mút để đại diện đầy đủ cho khuyên: `set([B,B])` chỉ còn một phần tử. Nếu phải bảo toàn số đầu mút và ID liên kết, bản ghi có cấu trúc như `edge_id -> (u,v,weight)` rõ ràng hơn.

## 4. Khuyên được đếm như thế nào?

Khuyên là liên kết mà **hai đầu mút cùng một đỉnh**. Nó có thể mang ý nghĩa thực tế: một trạng thái tự chuyển về chính nó, một tuyến đường vòng hoặc một công việc được phép lặp.

### Đồ thị vô hướng

Bậc của đỉnh `v`, ký hiệu `deg(v)`, đếm số **đầu mút liên kết** chạm vào `v`. Vì một khuyên có **hai đầu mút cùng tại `v`**, theo quy ước bậc chuẩn, nó tăng bậc lên **2**:

\[
\deg(v)
= \#\{\text{đầu mút của các cạnh gắn với }v\}.
\]

Ví dụ đồ thị vô hướng có `e_0={A,B}`, `e_1={A,B}` và `e_2={B,B}`:

- `deg(A)=2`, do hai cạnh A–B riêng biệt.
- `deg(B)=4`, do hai cạnh A–B và một khuyên tại B góp 2.
- Tổng bậc bằng `6=2\cdot3` với `m=3` cạnh.

**Định lý bắt tay (handshaking lemma):**

\[
\sum_{v\in V}\deg(v)=2|E|.
\]

Đẳng thức **vẫn đúng với khuyên và cạnh song song**, miễn là đếm theo quy ước trên.

### Đồ thị có hướng

Với một cung khuyên `a=(B,B)`:

- `outdeg(B)` tăng **1** vì B là nguồn.
- `indeg(B)` tăng **1** vì B là đích.

Với mọi đa đồ thị có hướng:

\[
\sum_{v\in V}\operatorname{outdeg}(v)
=\sum_{v\in V}\operatorname{indeg}(v)
=|E|.
\]

Hai cung song song `A\to B` đóng góp **2** vào bậc ra của A và **2** vào bậc vào của B; một cung ngược `B\to A` là cung khác, đóng góp theo chiều ngược lại.

## 5. Ví dụ số: nhiều cạnh cùng đầu mút nhưng trọng số khác

Xét đa đồ thị vô hướng có bốn đỉnh:

```text
V = {A, B, C, D}

e0: A -- B, trọng số 5
e1: A -- B, trọng số 7
e2: B -- C, trọng số 4
e3: B -- B, trọng số 2 (khuyên)

D cô lập.
```

| Edge ID | Đầu mút 1 | Đầu mút 2 | Trọng số | Vai trò |
| --- | --- | --- | ---: | --- |
| `e0` | A | B | 5 | Tuyến A–B thứ nhất |
| `e1` | A | B | 7 | Tuyến A–B thứ hai |
| `e2` | B | C | 4 | Tuyến B–C |
| `e3` | B | B | 2 | Tuyến vòng tại B |

Trong ví dụ này có **4 cạnh**, không phải 3 cặp đỉnh phân biệt. Nếu kiểm tra “A có kề B không?”, câu trả lời chỉ là **có**; nếu hỏi “có bao nhiêu tuyến A–B?”, câu trả lời là **2**; nếu hỏi “các trọng số tuyến A–B là gì?”, câu trả lời là **5 và 7**.

Bảng bậc:

| Đỉnh | Đóng góp vào bậc | Bậc |
| --- | --- | ---: |
| A | `e0:1`, `e1:1` | 2 |
| B | `e0:1`, `e1:1`, `e2:1`, `e3:2` | 5 |
| C | `e2:1` | 1 |
| D | Không có cạnh | 0 |
| **Tổng** | | **8 = 2 × 4** |

Các con số này sẽ được dùng để kiểm tra cấu trúc dữ liệu và ví dụ Python bên dưới.

## 6. Vì sao `set` láng giềng hoặc `neighbor -> weight` làm mất dữ liệu?

Với một **đồ thị đơn**, ta có thể lưu:

```python
# Đủ để trả lời "A có kề B không?" trong đồ thị đơn
ke_tap = {"A": {"B"}, "B": {"A"}}

# Mỗi cặp đầu mút chỉ giữ một trọng số
ke_trong_so = {"A": {"B": 5}, "B": {"A": 5}}
ke_trong_so["A"]["B"] = 7
print(ke_trong_so["A"]["B"])  # 7: trọng số 5 đã bị ghi đè
```

Đối với đa đồ thị, các cấu trúc này không phân biệt được `e0` với `e1`. Thậm chí danh sách `["B","B"]` dù ghi nhận được **hai lần xuất hiện** vẫn không đủ nếu người dùng cần xóa *chính xác tuyến có ID e0* hoặc lưu trọng số riêng.

Cần chọn cấu trúc bảo toàn **tính bội (multiplicity)** của liên kết. Một số lựa chọn:

- `adj[u] = [(neighbor, edge_id), ...]`, lưu danh sách các mục kề có ID.
- `edges[edge_id] = (u, v, weight, attributes)`, lưu bản ghi liên kết tập trung.
- Kết hợp **bảng cạnh theo ID** với **danh sách kề theo ID** để hỗ trợ cả truy vấn liên kết lẫn duyệt láng giềng.
- Trong ma trận kề, mỗi ô lưu **số lượng** cạnh/cung hoặc một **danh sách edge ID**, thay vì một giá trị Boolean.

Đối với đồ thị vô hướng, cặp `(A,B)` và `(B,A)` đại diện **cùng cặp đầu mút**; với đồ thị có hướng, hai cặp có thứ tự đó khác nhau. Nhưng trong cả hai trường hợp, **cặp đầu mút không đủ làm ID liên kết trong đa đồ thị**.

## 7. Cấu trúc phù hợp: bảng cạnh và danh sách kề có ID

Ta dùng một **bảng cạnh** để lưu mỗi liên kết **đúng một lần**:

```text
edges:
  0 -> (A, B, 5)
  1 -> (A, B, 7)
  2 -> (B, C, 4)
  3 -> (B, B, 2)
```

Với đồ thị vô hướng và chính sách **mỗi đầu mút tạo một mục kề**, danh sách kề trở thành:

```text
adj[A]: [(B,0), (B,1)]
adj[B]: [(A,0), (A,1), (C,2), (B,3), (B,3)]
adj[C]: [(B,2)]
adj[D]: []
```

Có ba điểm dễ sai:

1. **Cạnh e0/e1:** cùng láng giềng B nhưng **hai ID khác nhau**, nên đều được giữ.
2. **Cạnh e3 khuyên:** có **hai mục kề tại B cùng mang ID 3**, tương ứng với hai đầu mút tại B; nhờ vậy `len(adj[B])=5=deg(B)`.
3. **Bảng cạnh:** e3 vẫn chỉ là **một cạnh**, dù xuất hiện hai mục trong danh sách kề. Số cạnh phải đếm từ bảng `edges`, không lấy tổng kích thước các danh sách kề.

Với đồ thị có hướng, ta có thể chỉ lưu **cung đi ra từ nguồn**:

```text
edges:
  0 -> (A, B, 5)
  1 -> (A, B, 7)
  2 -> (B, A, 9)
  3 -> (B, B, 0)

out[A]: [(B,0), (B,1)]
out[B]: [(A,2), (B,3)]
out[C]: []
```

Lúc này mỗi cung xuất hiện **đúng một mục** trong danh sách cung đi ra, kể cả cung khuyên. Từ `out[A]` có thể đọc trực tiếp `outdeg(A)=2`. Muốn biết `indeg(B)=3`, ta phải đếm hai cung A→B và một cung B→B hoặc duy trì thêm một **chỉ mục cung đi vào**.

## 8. Ma trận kề và ma trận liên thuộc có thể biểu diễn đa đồ thị không?

### Ma trận kề

Ma trận kề Boolean `M[u][v]\in\{0,1\}` chỉ cho biết **có ít nhất một** liên kết; nó **mất thông tin về số lượng**. Nếu muốn lưu đa đồ thị:

- `M[u][v]` có thể là **số lượng cung** từ u tới v.
- Hoặc `M[u][v]` là **danh sách edge ID** (và truy cập trọng số qua bảng cạnh).
- Với đồ thị vô hướng, `M[u][v]=M[v][u]` khi lưu số lượng cạnh và `u\ne v`. Với khuyên `M[v][v]` có thể lưu **số khuyên**, còn bậc phải tính phần đường chéo **hai lần**.

Ví dụ ma trận **số lượng cạnh** cho A, B, C ở mục 5 (D bị lược bỏ trong ví dụ ma trận nhỏ):

\[
M=
\begin{bmatrix}
0&2&0\\
2&1&1\\
0&1&0
\end{bmatrix}.
\]

`M[A][B]=2` vì có e0 và e1; `M[B][B]=1` vì có **một khuyên** e3. Bậc của B không phải tổng các ô hàng B `2+1+1=4`, mà là `2+2\cdot1+1=5`.

**Chú ý:** một ma trận trọng số đơn `M[A][B]=5` không lưu được đồng thời cả trọng số 5 lẫn 7. Chọn `min(5,7)` có thể phù hợp cho một truy vấn tối ưu cụ thể, nhưng đó là **thông tin tổng hợp**, không còn biểu diễn nguyên vẹn hai cạnh.

### Ma trận liên thuộc (incidence matrix)

Trong một **ma trận liên thuộc**, mỗi **cột** tương ứng với một **edge ID**, còn mỗi hàng là một đỉnh. Vì e0 và e1 có hai cột riêng, cạnh song song vẫn được phân biệt.

Theo một quy ước vô hướng thông dụng, ô hàng `v`/cột `e` ghi số đầu mút của cạnh `e` ở `v`: 0 nếu không chạm, 1 nếu là một đầu mút, **2 đối với khuyên tại `v`**. Ví dụ e0=A–B, e1=A–B, e2=B–B:

\[
I=
\begin{array}{c|ccc}
& e_0&e_1&e_2\\\hline
A&1&1&0\\
B&1&1&2
\end{array}.
\]

Ma trận liên thuộc có hướng đôi khi dùng `-1` ở nguồn, `+1` ở đích. Với **cung khuyên**, hai dấu sẽ triệt tiêu nếu chỉ lưu một ô, nên một ma trận dấu đơn thuần không còn đủ để suy ra sự tồn tại cung khuyên; cần ghi nhận riêng hoặc có quy ước phù hợp.

Ma trận liên thuộc thường chiếm `O(nm)` ô khi lưu dạng đặc; trên đồ thị lớn và thưa, bảng cạnh kết hợp danh sách kề thường tiết kiệm hơn.

## 9. Python: cài đặt đa đồ thị có ID liên kết độc lập

Ví dụ Python sau hỗ trợ **đa đồ thị vô hướng hoặc có hướng**, **cạnh/cung song song**, **khuyên**, **trọng số**, **đỉnh cô lập** và xóa **đúng một liên kết theo ID**. Để giữ quy tắc đếm bậc rõ ràng, đồ thị vô hướng ghi **hai mục kề cho mỗi cạnh**, kể cả khuyên; đồ thị có hướng chỉ ghi một mục ở nguồn.

```python
class DaDoThi:
    def __init__(self, co_huong=False):
        self.co_huong = co_huong
        self.dinh = {}    # vertex_id -> nhãn hiển thị
        self.canh = {}    # edge_id -> (u, v, trọng số)
        self.ke = {}      # vertex_id -> [(neighbor_id, edge_id), ...]
        self._id_ke_tiep = 0

    def them_dinh(self, ma: str, nhan: str):
        if ma in self.dinh:
            raise ValueError("Định danh đỉnh đã tồn tại")
        self.dinh[ma] = nhan
        self.ke[ma] = []

    def them_canh(self, u: str, v: str, trong_so=1):
        if u not in self.dinh or v not in self.dinh:
            raise KeyError("Đầu mút phải là đỉnh đã tồn tại")

        eid = self._id_ke_tiep
        self._id_ke_tiep += 1  # Không tái dùng ID đã xóa
        self.canh[eid] = (u, v, trong_so)

        # Cung: chỉ một mục ở nguồn.
        # Cạnh vô hướng: hai mục, kể cả khi u == v.
        self.ke[u].append((v, eid))
        if not self.co_huong:
            self.ke[v].append((u, eid))
        return eid

    def canh_giua(self, u: str, v: str):
        if u not in self.dinh or v not in self.dinh:
            raise KeyError("Đỉnh không tồn tại")

        # Một khuyên vô hướng xuất hiện hai lần trong ke[u].
        # Dùng dict.fromkeys để khử trùng ID và giữ thứ tự gặp.
        return list(dict.fromkeys(
            eid for lang_gieng, eid in self.ke[u]
            if lang_gieng == v
        ))

    def xoa_canh(self, eid: int):
        u, v, trong_so = self.canh.pop(eid)
        # Xóa chỉ những mục mang ID cần xóa; không xóa
        # tất cả liên kết cùng đầu mút.
        self.ke[u] = [
            (x, j) for x, j in self.ke[u] if j != eid
        ]
        if not self.co_huong and v != u:
            self.ke[v] = [
                (x, j) for x, j in self.ke[v] if j != eid
            ]
        # Với khuyên vô hướng u == v, bộ lọc đầu tiên
        # loại cả hai mục kề mang cùng ID.
        return (u, v, trong_so)

    def bac(self, v: str):
        if self.co_huong:
            raise ValueError("Hãy dùng bac_ra hoặc bac_vao")
        return len(self.ke[v])

    def bac_ra(self, v: str):
        if not self.co_huong:
            raise ValueError("Đồ thị vô hướng")
        return len(self.ke[v])

    def bac_vao(self, v: str):
        if not self.co_huong:
            raise ValueError("Đồ thị vô hướng")
        if v not in self.dinh:
            raise KeyError(v)
        # Không lưu chỉ mục đi vào: cần duyệt mọi cung.
        return sum(1 for _, dich, _ in self.canh.values()
                   if dich == v)


# Vô hướng: hai cạnh A--B, một B--C, một khuyên B--B.
g = DaDoThi()
for ma in "ABCD":
    g.them_dinh(ma, f"Đỉnh {ma}")

e0 = g.them_canh("A", "B", 5)
e1 = g.them_canh("A", "B", 7)
e2 = g.them_canh("B", "C", 4)
e3 = g.them_canh("B", "B", 2)

print((e0, e1, e2, e3))  # (0, 1, 2, 3)
print(g.canh_giua("A", "B"))  # [0, 1]
print(g.canh_giua("B", "B"))  # [3], không phải [3, 3]
print(g.ke["B"])
# [('A', 0), ('A', 1), ('C', 2), ('B', 3), ('B', 3)]
print([g.bac(v) for v in "ABCD"])  # [2, 5, 1, 0]
print(sum(g.bac(v) for v in "ABCD"))  # 8 = 2 * 4 cạnh

g.xoa_canh(e0)
print(g.canh_giua("A", "B"))  # [1]: chỉ e0 bị xóa
print(g.canh[e1])             # ('A', 'B', 7)
print([g.bac(v) for v in "ABCD"])  # [1, 4, 1, 0]
print(len(g.canh))             # 3 cạnh

# Có hướng: hai cung A->B, một B->A và một khuyên B->B.
h = DaDoThi(co_huong=True)
for ma in "ABC":
    h.them_dinh(ma, ma)
h.them_canh("A", "B", 5)
h.them_canh("A", "B", 7)
h.them_canh("B", "A", 9)
h.them_canh("B", "B", 0)

print(h.canh_giua("A", "B"))  # [0, 1]
print(h.canh_giua("B", "A"))  # [2]
print([h.bac_ra(v) for v in "ABC"])   # [2, 2, 0]
print([h.bac_vao(v) for v in "ABC"])  # [1, 3, 0]
```

**Vì sao `xoa_canh(e0)` là thao tác quan trọng?** Nếu chỉ gọi “xóa cạnh A–B” mà không chỉ rõ ID, lớp đồ thị phải định nghĩa rõ: xóa **một** cạnh bất kỳ, xóa **tất cả** cạnh A–B, hay từ chối vì nhập nhằng. API `xoa_canh(edge_id)` tránh nhầm lẫn, giữ nguyên các cạnh song song không liên quan.

Mã trên dùng chuỗi cho ID đỉnh nhưng không phụ thuộc vào nhãn để định vị. ID cạnh là số nguyên tăng dần, không được tái sử dụng trong đời sống của đối tượng đồ thị này; đó là một chính sách minh họa giúp tránh tham chiếu cũ vô tình trỏ vào cạnh mới.

## 10. Chi phí thời gian và bộ nhớ của biểu diễn

Gọi `n=|V|`, `m=|E|` và `deg(v)` là bậc vô hướng (đếm khuyên hai lần), `outdeg(v)` là bậc ra.

| Thao tác | Biểu diễn bảng cạnh + danh sách kề như ví dụ |
| --- | --- |
| Bộ nhớ | `O(n+m)`: mỗi ID cạnh có một bản ghi; vô hướng có hai mục kề cho mỗi cạnh |
| Thêm đỉnh | `O(1)` kỳ vọng và phân bổ với `dict`, giả định hash ID phù hợp |
| Thêm liên kết | `O(1)` kỳ vọng và phân bổ, không kiểm tra liên kết trùng |
| Tìm các ID nối `u` với `v` | `O(deg(u)+r)` vô hướng hoặc `O(outdeg(u)+r)` có hướng nếu trả `r` ID và quét kề |
| Xóa một cạnh bằng ID | `O(deg(u)+deg(v))` vô hướng (hoặc `O(deg(u))` với khuyên); `O(outdeg(u))` có hướng, do lọc list |
| Lấy bậc vô hướng hoặc bậc ra | `O(1)` qua `len(ke[v])` |
| Lấy bậc vào có hướng | `O(m)` trong ví dụ vì phải quét toàn bộ bảng cung |
| Duyệt toàn bộ liên kết | `O(m)` qua bảng `canh` |

Chi phí `r` ở hàng “tìm các ID” biểu diễn số ID được tạo thành đầu ra; vì chương trình đã quét toàn bộ `ke[u]`, có thể viết gọn cận `O(deg(u))` hoặc `O(outdeg(u))` trong mô hình thao tác hằng số.

Nếu cần xóa liên kết theo ID rất thường xuyên, có thể thiết kế **chỉ mục từ edge ID đến vị trí/nút kề** hoặc dùng cấu trúc liên kết phù hợp; khi đó việc cập nhật có thể nhanh hơn, nhưng phải giữ chỉ mục nhất quán sau mọi lần thêm/xóa. Nếu cần truy vấn **mọi cạnh giữa u và v** thường xuyên, có thể duy trì `pair -> list/set(edge_id)` bổ sung; đổi lại, thêm/xóa phải cập nhật chỉ mục này.

**Không nhầm `m` với số cặp đỉnh khác nhau**: ví dụ bốn cạnh ở mục 5 có chỉ **ba** cặp đầu mút khác nhau. Khi quy mô đo theo số liên kết thực, bộ nhớ và thời gian của những thuật toán duyệt từng cạnh phải phụ thuộc `m`, kể cả khi có nhiều cạnh song song.

## 11. Tác động của khuyên và cạnh song song đến thuật toán đồ thị

### BFS/DFS và khả năng tới được

Khi chỉ kiểm tra **khả năng tới được**, nhiều liên kết cùng từ u sang v không tạo ra một đỉnh mới. BFS/DFS có thể gặp v nhiều lần nhưng **đánh dấu đỉnh đã thăm** để không xử lý lại không cần thiết. Cận `O(n+m)` vẫn đúng khi duyệt mọi mục kề và mỗi đỉnh được đánh dấu đúng quy tắc.

Khuyên `u\to u` không làm xuất hiện đỉnh mới có thể đi tới, nhưng vẫn là một liên kết hợp lệ trong dữ liệu.

### Đường đi ngắn nhất và lựa chọn tuyến

Hai cung A→B có trọng số 5 và 7 là hai phương án di chuyển khác nhau. Nếu chỉ cần **tổng chi phí tối thiểu** và trọng số không âm, thuật toán như Dijkstra nên xét **cả hai cung** hoặc áp dụng một phép gộp có chứng minh bảo toàn kết quả (ví dụ giữ trọng số nhỏ nhất cho cặp đầu mút trong bài toán tối ưu đó).

Việc gộp này **không bảo toàn số chuyến, lịch trình, ID, năng lực hay khả năng đếm đường đi khác nhau theo cạnh**. Một khuyên trọng số không âm không cải thiện đường đi ngắn nhất giữa hai đỉnh; khuyên **trọng số âm** trong bài toán đường đi cho phép lặp có thể tạo **chu trình âm**, khiến không tồn tại giá trị tối ưu hữu hạn cho những đích liên quan.

### Chu trình và DFS trên đồ thị vô hướng

Với đồ thị vô hướng đơn, khi DFS phát hiện láng giềng chính là **đỉnh cha**, ta thường bỏ qua cạnh quay về cha. Nhưng trong **đa đồ thị**, hai cạnh song song A–B tạo thành một **chu trình độ dài 2 khi phân biệt cạnh**: đi A→B theo e0 rồi B→A theo e1.

Nếu bỏ qua **mọi** liên kết dẫn về đỉnh cha, ta có thể **bỏ sót chu trình** này. Khi cần phát hiện chu trình bằng DFS, phải phân biệt **edge ID của cạnh đã đi vào đỉnh**; chỉ bỏ qua đúng cạnh cha ấy, không bỏ qua một cạnh song song khác cũng nối về đỉnh cha.

Khuyên `A—A` là một **chu trình độ dài 1** theo quy ước chu trình trong đa đồ thị cho phép khuyên. Những quy ước về “chu trình đơn” có thể khác giữa tài liệu; thuật toán cần dùng định nghĩa phù hợp.

### Cây khung và đường đi Euler

- **Cây khung nhỏ nhất (MST)** của đồ thị vô hướng bỏ qua khuyên vì chúng không thể nối hai thành phần đỉnh khác nhau. Hai cạnh song song có thể là những ứng viên khác nhau; thuật toán phải chọn theo trọng số và cấu trúc chu trình.
- **Đường đi Euler** xét **mỗi cạnh một lần**, không phải mỗi cặp đỉnh một lần. Cạnh song song và khuyên phải được đếm riêng; khi dùng đồ thị vô hướng, khuyên đóng góp **2 vào bậc**, nên không làm thay đổi tính chẵn lẻ bậc của đỉnh.

Những ví dụ này cho thấy sai lầm “gộp mọi cặp đầu mút thành một cạnh” có thể làm hỏng **kết quả thuật toán**, không chỉ mất một trường dữ liệu phụ.

## 12. Bất biến cập nhật và các trường hợp ranh giới

Một cài đặt đa đồ thị nên kiểm tra những điều kiện sau:

1. **Tập đỉnh đầy đủ:** đỉnh cô lập vẫn được giữ; không suy ra `V` chỉ từ đầu mút của `E`.
2. **Đầu mút hợp lệ:** mọi edge ID tham chiếu hai ID đỉnh đang tồn tại.
3. **ID liên kết duy nhất:** hai cạnh song song có ID khác nhau, dù trùng đầu mút và trọng số.
4. **Vô hướng:** mỗi cạnh xuất hiện hai mục kề có cùng ID và đầu mút đối ứng; khuyên có hai mục cùng tại một đỉnh theo quy ước bài này.
5. **Có hướng:** mỗi cung xuất hiện một mục tại đỉnh nguồn trong danh sách cung đi ra; không tự tạo cung ngược.
6. **Xóa theo ID:** phải xóa đúng bản ghi cạnh và tất cả mục kề mang ID đó; không xóa nhầm các cạnh song song khác.
7. **Đếm bậc:** `sum(deg)=2m` với vô hướng; `sum(indeg)=sum(outdeg)=m` với có hướng.
8. **Xóa đỉnh:** phải xử lý mọi liên kết đi vào/đi ra hoặc vô hướng có đầu mút tại đỉnh ấy, tránh liên kết mồ côi; có thể từ chối xóa nếu đỉnh chưa cô lập.

Khi hỗ trợ **cập nhật trọng số**, nên sửa tại bản ghi `edges[edge_id]` rồi để các mục kề tham chiếu ID, thay vì lưu nhiều bản sao trọng số có thể lệch nhau. Nếu muốn hiệu năng cao, có thể lưu cache trọng số trong kề, nhưng bắt buộc cập nhật mọi bản sao nhất quán.

## 13. Những ngộ nhận thường gặp

1. **“Cùng hai đầu mút nghĩa là cùng một cạnh.”** Sai trong đa đồ thị; edge ID quyết định liên kết riêng.
2. **“Cung A→B và B→A là hai cung song song cùng hướng.”** Sai: chúng ngược chiều; cung song song cùng hướng phải có cùng cặp nguồn–đích.
3. **“Khuyên vô hướng tăng bậc 1.”** Sai theo quy ước chuẩn: tăng bậc **2**.
4. **“Khuyên xuất hiện hai lần trong danh sách kề tức là hai cạnh.”** Sai: hai mục cùng ID có thể là hai đầu mút của **một khuyên**.
5. **“`set(neighbor)` đủ biểu diễn mọi đồ thị.”** Sai nếu cần lưu số lượng, ID hoặc thuộc tính của các liên kết song song.
6. **“Một ma trận Boolean cho biết có bao nhiêu tuyến.”** Sai: nó chỉ phân biệt không có/có ít nhất một tuyến.
7. **“Xóa theo cặp A–B luôn là thao tác rõ nghĩa.”** Sai khi A–B có nhiều edge ID; cần xác định chính sách xóa.
8. **“BFS/DFS cần thăm v nhiều lần nếu có nhiều cung tới v.”** Sai: duyệt liên kết nhưng quản lý visited theo đỉnh khi tìm khả năng tới được.
9. **“DFS vô hướng chỉ cần bỏ qua mọi cạnh nối về cha.”** Sai trong đa đồ thị vì có thể bỏ sót chu trình hình thành từ cạnh song song.
10. **“Đồ thị có cùng tập đỉnh, cùng tập cặp đầu mút là như nhau.”** Sai nếu một mô hình có nhiều liên kết, trọng số, nhãn hoặc khuyên riêng biệt.

## 14. Tự kiểm tra

**Câu 1.** Một ứng dụng có hai chuyến xe A→B lúc 08:00 và 10:00. Vì sao biểu diễn `adj[A] = {B}` không đủ?

**Đáp án:** Nó chỉ lưu việc **có** tuyến A→B, không giữ được hai chuyến riêng. Cần cung song song với ID riêng và thuộc tính thời gian của từng chuyến.

**Câu 2.** Đồ thị vô hướng có hai cạnh A–B và một khuyên B–B. `deg(A)`, `deg(B)` và tổng bậc bằng bao nhiêu?

**Đáp án:** `deg(A)=2`; `deg(B)=4` vì khuyên đóng góp 2. Tổng bậc là `6=2\cdot3` với 3 cạnh.

**Câu 3.** Đồ thị có hướng chứa hai cung A→B, một cung B→A và một cung B→B. Tính bậc vào/ra của B.

**Đáp án:** `indeg(B)=3` (hai A→B và một B→B), `outdeg(B)=2` (một B→A và một B→B).

**Câu 4.** Trong biểu diễn `edges[eid]=(u,v,w)` và `adj[u]=[(neighbor,eid),...]`, vì sao một khuyên vô hướng có thể xuất hiện hai lần trong `adj[B]` nhưng vẫn chỉ tính một cạnh?

**Đáp án:** Vì hai mục kề tương ứng với **hai đầu mút** của cùng khuyên ở B, cùng dùng **một edge ID**. Số cạnh được đếm từ số bản ghi trong `edges`.

**Câu 5.** Đồ thị có hai cạnh A–B trọng số 5 và 7. Nếu ma trận kề lưu `M[A][B]=2` thì biết được điều gì, và chưa biết được điều gì?

**Đáp án:** Biết có **hai cạnh** giữa A và B. Chưa biết các trọng số 5, 7 hoặc ID từng cạnh; cần bảng cạnh hoặc danh sách ID riêng.

**Câu 6.** Vì sao thao tác `xoa_canh(e0)` phải giữ e1 nếu e0 và e1 cùng nối A–B?

**Đáp án:** Hai liên kết là hai đối tượng riêng; yêu cầu xóa e0 không có nghĩa xóa mọi cạnh cùng đầu mút. Chỉ các mục kề mang ID e0 bị loại bỏ.

**Câu 7.** Hai cạnh song song A–B có thể tạo chu trình mà thuật toán DFS vô hướng bỏ qua mọi liên kết tới đỉnh cha sẽ không phát hiện không?

**Đáp án:** Có. Đi từ A sang B theo e0, rồi trở lại A theo e1 tạo chu trình hai cạnh. DFS phải phân biệt **edge ID** để chỉ bỏ qua đúng cạnh cha e0, không bỏ qua e1.

**Câu 8.** Trong đồ thị vô hướng, một khuyên có trọng số 2 và hai cạnh A–B có trọng số 5, 7, nên dùng khuyên để nối hai thành phần khác nhau trong cây khung nhỏ nhất không?

**Đáp án:** Không. Khuyên chỉ nối một đỉnh với chính nó, không giúp hợp nhất hai thành phần. MST không chọn khuyên để kết nối các đỉnh.

**Câu 9.** Bảng cạnh chứa `m` liên kết, danh sách kề vô hướng lưu hai mục cho mỗi cạnh. Bộ nhớ theo `n,m` ở bậc lớn là bao nhiêu?

**Đáp án:** `O(n+m)`. Hai mục kề trên mỗi cạnh chỉ làm tăng hệ số hằng, kể cả khi đó là khuyên.

**Ghi nhớ:** **Khuyên** có hai đầu mút tại cùng một đỉnh, còn **cạnh/cung song song** là các liên kết khác nhau có chung đầu mút (và chung chiều nếu có hướng). Trong đa đồ thị, **cặp đầu mút không phải định danh duy nhất cho liên kết**. Cần lưu từng **edge ID**, bảo toàn tính bội trong danh sách kề hoặc cấu trúc tương đương, và nhất quán cách đếm bậc, thêm/xóa, xử lý trọng số và thuật toán. Một phép gộp đơn giản theo láng giềng có thể làm mất tuyến, mất khuyên hoặc cho kết quả thuật toán sai.

# Đồ thị có hướng, vô hướng, trọng số và không trọng số

## 1. Hai câu hỏi độc lập khi mô hình hóa đồ thị

Một đồ thị có thể mô tả tình bạn giữa người dùng, những học phần tiên quyết, mạng đường bộ hoặc đường truyền trong máy tính. Để xây dựng cấu trúc dữ liệu đúng, trước tiên phải trả lời **hai câu hỏi khác nhau**:

1. **Liên kết có chiều hay không?** Quan hệ từ A đến B có tự động đồng nghĩa với quan hệ từ B đến A không?
2. **Liên kết có giá trị định lượng riêng hay không?** Ta chỉ quan tâm một liên kết có tồn tại, hay còn phải biết độ dài, chi phí, thời gian, dung lượng... của nó?

Từ đó hình thành bốn loại cơ bản:

| Kiểu đồ thị | Có hướng? | Có trọng số? | Ví dụ cách mô hình hóa |
| --- | --- | --- | --- |
| Vô hướng, không trọng số | Không | Không | Quan hệ kết bạn được xác nhận hai chiều |
| Có hướng, không trọng số | Có | Không | Học phần A là tiên quyết của học phần B |
| Vô hướng, có trọng số | Không | Có | Đường truyền hai chiều với một độ dài cố định chung |
| Có hướng, có trọng số | Có | Có | Thời gian hoặc chi phí di chuyển từ địa điểm này sang địa điểm khác |

**Hướng** và **trọng số** là hai thuộc tính **độc lập**. Đồ thị có hướng không nhất thiết có trọng số; đồ thị có trọng số không nhất thiết có hướng. Lựa chọn này ảnh hưởng đến cách ghi dữ liệu, bất biến cần giữ và thuật toán nên sử dụng.

## 2. Ký hiệu toán học: đỉnh, cạnh và cung

Ký hiệu `V` là tập đỉnh, `E` là tập liên kết, `n=|V|` là số đỉnh và `m=|E|` là số cạnh hoặc cung (không phải số mục lưu trong danh sách kề).

### Đồ thị vô hướng

Trong đồ thị vô hướng đơn không có khuyên:

\[
G=(V,E),\qquad
E\subseteq\{\{u,v\}\mid u,v\in V,\ u\ne v\}.
\]

Cạnh `{A,B}` đồng nghĩa cạnh `{B,A}`: nó không có điểm đầu hay điểm cuối cố định. Ví dụ:

```text
A -------- B -------- C          D

V = {A, B, C, D}
E = {{A,B}, {B,C}}
```

Từ A đi tới C có thể đi qua B; từ C cũng có thể đi ngược qua B về A. D là **đỉnh cô lập**: thuộc tập V dù không nối với đỉnh nào.

### Đồ thị có hướng

Trong đồ thị có hướng đơn, mỗi cung là một **cặp có thứ tự**:

\[
G=(V,E),\qquad E\subseteq V\times V.
\]

```text
A -----> B -----> C          D

E = {(A,B), (B,C)}
```

Cung `(A,B)` có nghĩa `A → B`, **không tự sinh** cung `(B,A)`. Vì thế A có thể tới C qua B, nhưng từ C không có đường đi ngược về A trong ví dụ này.

Một đồ thị có hướng có thể chứa cả `A → B` và `B → A`, nhưng đó là **hai cung phân biệt**. Khi bản chất quan hệ là hai chiều không phân biệt nguồn–đích, biểu diễn bằng một cạnh vô hướng thường tự nhiên hơn.

## 3. Trọng số là gì và biểu diễn điều gì?

Với đồ thị có trọng số, mỗi liên kết `e\in E` được gán một giá trị:

\[
w:E\longrightarrow W.
\]

Tập `W` có thể là các số thực hoặc một kiểu dữ liệu khác, tùy bài toán. Trong các ví dụ tìm đường ngắn nhất, ta thường xét `W\subseteq\mathbb{R}`.

Một trọng số có thể biểu diễn:

- **Độ dài:** quãng đường giữa hai ga, đơn vị km.
- **Thời gian:** số phút đi qua một đoạn đường.
- **Chi phí:** phí giao hàng hoặc tiền vận chuyển.
- **Dung lượng:** khả năng truyền tải tối đa qua một đường nối.
- **Độ tin cậy hoặc xác suất:** cần quy tắc tổng hợp thích hợp, không mặc nhiên cộng như khoảng cách.

Ví dụ đồ thị **vô hướng có trọng số**:

```text
         4 km          7 km
    A ------------ B ------------ C
     \                            /
      \--------- 15 km ----------/
```

Một cạnh `{A,B}` có trọng số `4`. Nếu ứng dụng định nghĩa trọng số là độ dài tuyến đường và đường đi hai chiều có cùng độ dài, dùng một trọng số chung cho hai chiều là hợp lý.

Với đồ thị **có hướng có trọng số**:

```text
    A ---4 phút---> B
    A <--9 phút--- B
    B ---3 phút---> C
```

Cung `A → B` có trọng số `4`, còn cung `B → A` (nếu tồn tại) có thể có trọng số **khác**, là `9`. Hai chiều có thể tốn thời gian khác nhau vì đường một chiều, độ dốc, mật độ giao thông hoặc quy ước nghiệp vụ.

**Không trọng số** không đồng nghĩa mọi liên kết có trọng số bằng `0`. Khi tìm đường đi qua ít cạnh nhất, ta thường **diễn giải mỗi cạnh/cung là một bước với chi phí đơn vị 1**. Một cạnh có trọng số `0` trong đồ thị có trọng số là **cạnh có thật** với chi phí bằng 0, không phải cạnh vắng mặt.

## 4. Bốn mô hình cho cùng một tập đỉnh

Cho `V=\{A,B,C\}`. Ta có thể dùng các liên kết `A-B`, `B-C` để minh họa độc lập hai trục:

**Mô hình 1 — vô hướng, không trọng số:**

```text
A --- B --- C

E = {{A,B}, {B,C}}
```

Từ A tới C mất **hai bước qua hai cạnh**, và đi từ C về A cũng có hai bước.

**Mô hình 2 — có hướng, không trọng số:**

```text
A ---> B ---> C

E = {(A,B), (B,C)}
```

Có đường A tới C dài hai cung; **không có** đường C tới A. Đường đi không trọng số được đánh giá theo **số cung**.

**Mô hình 3 — vô hướng, có trọng số:**

```text
A --(5)-- B --(2)-- C
```

Tổng trọng số của đường A–B–C là `5+2=7`, như nhau khi đi ngược nếu trọng số cạnh là một giá trị chung.

**Mô hình 4 — có hướng, có trọng số:**

```text
A --(5)--> B --(2)--> C
A <--(9)-- B
```

Đường A→B→C có tổng trọng số `7`, còn B→A (nếu xét) có trọng số `9`. Không có đủ cung để suy ra đường C→A.

Như vậy, đổi **hướng** có thể thay đổi những đường đi hợp lệ; đổi **trọng số** có thể thay đổi tiêu chí chọn “đường đi tốt nhất”, ngay cả khi tập đỉnh và cặp đầu mút không đổi.

## 5. Đường đi ít cạnh nhất có thể không rẻ nhất

Xét đồ thị có hướng có trọng số:

```text
        7
   A ---------> C
    \          ^
   2 \        / 2
      v      /
         B
```

Có hai đường từ A đến C:

| Đường đi | Số cung | Tổng trọng số |
| --- | ---: | ---: |
| `A → C` | 1 | 7 |
| `A → B → C` | 2 | 4 |

Nếu bài toán hỏi **ít bước nhất**, đường `A → C` tốt hơn vì chỉ có một cung. Nếu hỏi **chi phí nhỏ nhất**, đường `A → B → C` tốt hơn vì `2+2=4<7`.

Cho một đường đi gồm dãy đỉnh `v_0,v_1,\ldots,v_t`, trong đó mọi `(v_i,v_{i+1})` là cung hợp lệ (hoặc cặp đầu mút của cạnh vô hướng), thì:

\[
\operatorname{cost}(v_0,\ldots,v_t)
=\sum_{i=0}^{t-1}w(v_i,v_{i+1}).
\]

Với đồ thị không trọng số khi ta chủ động quy ước **mỗi cung/cạnh có giá 1**, công thức này trở thành `\operatorname{cost}=t`, tức **số bước**. Với đồ thị có trọng số, cộng trọng số chỉ phù hợp khi trọng số là đại lượng **có thể cộng dọc đường** như khoảng cách, thời gian cố định hoặc chi phí. Không áp dụng bừa phép cộng cho mọi ý nghĩa của trọng số.

## 6. Cách lưu đồ thị bằng danh sách kề

Một cách biểu diễn thường gặp là **danh sách kề (adjacency list)**. Với mỗi đỉnh `u`, lưu những đỉnh `v` có liên kết từ `u` sang `v`.

### Không trọng số

Với đồ thị vô hướng `A—B—C`:

```text
A: [B]
B: [A, C]
C: [B]
```

Mỗi cạnh vô hướng `{u,v}` được lưu bằng **hai mục kề**, một ở `u` và một ở `v`. Đây là **hai mục biểu diễn của một cạnh**, không phải hai cạnh độc lập.

Với đồ thị có hướng `A→B→C`:

```text
A: [B]
B: [C]
C: []
```

Chỉ ghi **cung đi ra từ nguồn**. Không được tự thêm B vào danh sách kề của A và A vào danh sách kề của B như khi lưu cạnh vô hướng.

### Có trọng số

Với đồ thị có hướng có trọng số `A→B` giá 2, `A→C` giá 7 và `B→C` giá 2:

```text
A: [(B, 2), (C, 7)]
B: [(C, 2)]
C: []
```

Đối với đồ thị vô hướng có trọng số, **cùng trọng số** của một cạnh phải được phản ánh ở cả hai mục kề đối ứng, nếu mô hình dùng một trọng số cho cả hai chiều.

Nếu ID đỉnh có dạng chuỗi, một biểu diễn Python tự nhiên là `dict[str, dict[str, float]]`, trong đó:

- Khóa ngoài là ID đỉnh nguồn.
- Khóa trong là ID đỉnh đích.
- Giá trị trong là trọng số.

Đối với đồ thị không trọng số, có thể dùng `dict[str, set[str]]` để chỉ lưu quan hệ kề, hoặc vẫn dùng giá trị `1` theo quy ước để thống nhất giao diện.

## 7. Ma trận kề: hướng và trọng số xuất hiện như thế nào?

Nếu các đỉnh được đánh số `0,\ldots,n-1`, ta có thể dùng **ma trận kề** `A` kích thước `n×n`.

### Không trọng số

Với đồ thị có hướng `0→1`, `1→2`:

\[
A=
\begin{bmatrix}
0&1&0\\
0&0&1\\
0&0&0
\end{bmatrix}.
\]

Trong ma trận này, `A[i][j]=1` biểu diễn có cung `i→j`. Ta thấy `A[0][1]=1` nhưng `A[1][0]=0`: **ma trận không cần đối xứng**.

Với đồ thị vô hướng đơn, `A[i][j]=A[j][i]` vì cạnh `{i,j}` không có hướng. Nếu không có khuyên, đường chéo `A[i][i]=0`.

### Có trọng số

Muốn lưu trọng số, ô `A[i][j]` cần phân biệt **không có liên kết** với **liên kết có trọng số 0**. Một quy ước an toàn:

```text
A[i][j] = None      nếu không có cung i -> j
A[i][j] = 0         nếu có cung i -> j, trọng số bằng 0
A[i][j] = 2.5       nếu có cung i -> j, trọng số bằng 2.5
```

Ví dụ đồ thị có hướng với `0→1` trọng số 0 và `1→2` trọng số 4:

```text
       0     1     2
0:   None    0    None
1:   None   None   4
2:   None   None  None
```

Nếu đặt `0` nghĩa là “không có cạnh”, cung `0→1` trọng số 0 sẽ bị **mất khỏi biểu diễn**. Một số thuật toán dùng `+∞` làm ký hiệu “chưa có đường trực tiếp” nhưng phải phân biệt với ô đường chéo có khoảng cách từ đỉnh đến chính nó bằng 0 khi khởi tạo ma trận khoảng cách.

**Chi phí bộ nhớ:** danh sách kề thường chiếm `O(n+m)`, còn ma trận kề chiếm `O(n^2)` dù chỉ có ít liên kết. Đổi lại, tra xem `i→j` có tồn tại trong ma trận là `O(1)` khi đã biết chỉ số hai đỉnh.

## 8. Bậc đỉnh, số cung và các bất biến

Hướng của đồ thị ảnh hưởng đến cách đếm **bậc (degree)**.

### Đồ thị vô hướng

`deg(v)` là số đầu mút cạnh chạm vào đỉnh `v`. Cạnh khuyên `{v,v}` có hai đầu mút cùng ở `v`, vì vậy theo quy ước chuẩn nó **đóng góp 2 vào bậc**.

\[
\sum_{v\in V}\deg(v)=2m.
\]

Ví dụ có cạnh A—B và B—C thì `deg(A)=1`, `deg(B)=2`, `deg(C)=1`; tổng `4=2·2`.

### Đồ thị có hướng

`outdeg(v)` là số cung đi ra, `indeg(v)` là số cung đi vào. Một cung khuyên `v→v` đóng góp 1 vào mỗi số.

\[
\sum_{v\in V}\operatorname{outdeg}(v)
=\sum_{v\in V}\operatorname{indeg}(v)=m.
\]

Ví dụ `A→B`, `B→C`: bậc ra lần lượt `1,1,0`, bậc vào `0,1,1`. Hai tổng đều bằng `m=2`.

**Trọng số không tự động thay đổi số cạnh hoặc bậc.** Một cung trọng số `100` vẫn là **một cung**. Nếu bài toán hỏi “tổng trọng số các cung đi ra”, đó là một thống kê khác:

\[
s_{\text{out}}(v)=\sum_{(v,u)\in E} w(v,u).
\]

Với đồ thị vô hướng, tổng trọng số theo hai mục kề của mỗi cạnh (kể cả khuyên được tính hai lần theo quy ước bậc) sẽ là **hai lần tổng trọng số các cạnh**, nếu mỗi cạnh vô hướng chỉ có một trọng số chung.

## 9. Khuyên, nhiều cạnh và những quyết định không được bỏ qua

Trước khi lập trình, cần xác định đồ thị của mình có phải **đồ thị đơn** hay cho phép **đa cạnh/cung**.

- **Khuyên (self-loop):** liên kết một đỉnh với chính nó, ví dụ `A→A` hoặc cạnh vô hướng tại A. Hợp lệ hay không tùy mô hình.
- **Cạnh/cung song song:** hai liên kết khác nhau có cùng đầu mút, có thể mang hai trọng số hoặc ID riêng.
- **Hai cung ngược chiều:** `A→B` và `B→A` không phải “cung song song cùng hướng”; mỗi cung có hướng riêng.

Một `dict` ánh xạ `u -> {v: weight}` chỉ giữ **một giá trị cho mỗi cặp có thứ tự** `(u,v)`. Nếu chèn lại cùng cặp, giá trị cũ có thể bị ghi đè. Đó là lựa chọn hợp lý cho **đồ thị đơn**, nhưng không đủ để biểu diễn hai chuyến xe A→B khác nhau.

Muốn hỗ trợ đa đồ thị, có thể lưu:

```text
u -> [(v, edge_id, weight), ...]
```

hoặc lưu tập `edge_id -> (u,v,weight)` song song với chỉ mục kề. Khi đó thuật toán và phép đếm phải xác định rõ xử lý **từng liên kết riêng** hay chỉ **quan hệ kề giữa hai đỉnh**.

## 10. Python: một lớp biểu diễn cả bốn loại đồ thị

Đoạn mã sau minh họa cách biểu diễn **đồ thị đơn** với ID đỉnh là chuỗi; mỗi cặp đầu mút chỉ có tối đa một liên kết cùng chiều. Nó hỗ trợ đỉnh cô lập và khuyên, nhưng chủ động **từ chối liên kết trùng**. Với đồ thị vô hướng, mỗi cạnh được phản ánh ở cả hai danh sách kề; nếu là khuyên thì chỉ lưu một khóa `u` trong `ke[u]` và tính bậc theo quy ước riêng.

Trong chế độ không trọng số, mỗi liên kết được lưu nội bộ với chi phí quy ước bằng `1`. Trong chế độ có trọng số, người gọi phải cung cấp một số hữu hạn, có thể bằng 0 hoặc âm; kiểm tra thuật toán tìm đường phù hợp được thảo luận ở mục sau.

```python
from math import isfinite


class DoThi:
    def __init__(self, co_huong=False, co_trong_so=False):
        self.co_huong = co_huong
        self.co_trong_so = co_trong_so
        self.ke = {}  # vertex_id -> {neighbor_id: weight}

    def them_dinh(self, ma: str):
        if ma in self.ke:
            raise ValueError(f"Đỉnh {ma!r} đã tồn tại")
        self.ke[ma] = {}  # Giữ cả đỉnh cô lập

    def them_lien_ket(self, u: str, v: str, trong_so=None):
        if u not in self.ke or v not in self.ke:
            raise KeyError("Hai đầu mút phải tồn tại")

        if self.co_trong_so:
            if (isinstance(trong_so, bool)
                    or not isinstance(trong_so, (int, float))
                    or not isfinite(trong_so)):
                raise ValueError("Cần trọng số hữu hạn dạng số")
            w = trong_so
        else:
            if trong_so is not None:
                raise ValueError("Đồ thị không trọng số không nhận trọng số")
            w = 1

        if v in self.ke[u]:
            raise ValueError("Liên kết này đã tồn tại")
        self.ke[u][v] = w
        if not self.co_huong:
            self.ke[v][u] = w

    def chi_phi_duong(self, duong: list[str]):
        if not duong:
            raise ValueError("Đường đi không được rỗng")
        if any(ma not in self.ke for ma in duong):
            raise KeyError("Đường đi chứa đỉnh không tồn tại")
        tong = 0
        for u, v in zip(duong, duong[1:]):
            if v not in self.ke[u]:
                raise ValueError(f"Không có liên kết {u!r} -> {v!r}")
            tong += self.ke[u][v]
        return tong

    def so_lien_ket(self):
        if self.co_huong:
            return sum(len(hang) for hang in self.ke.values())
        # Một cạnh vô hướng xuất hiện ở hai hàng; khuyên xuất hiện
        # ở một hàng nên phải tính riêng.
        tong_muc_ke = sum(len(hang) for hang in self.ke.values())
        so_khuyen = sum(u in hang for u, hang in self.ke.items())
        return (tong_muc_ke + so_khuyen) // 2


# Vô hướng, không trọng số:
vo_huong = DoThi()
for ma in "ABCD":
    vo_huong.them_dinh(ma)
vo_huong.them_lien_ket("A", "B")
vo_huong.them_lien_ket("B", "C")
print(vo_huong.ke["B"])       # {'A': 1, 'C': 1}
print(vo_huong.so_lien_ket())  # 2
print(vo_huong.chi_phi_duong(["C", "B", "A"]))  # 2 bước
print(vo_huong.ke["D"])       # {}: đỉnh cô lập

# Có hướng, có trọng số:
co_huong = DoThi(co_huong=True, co_trong_so=True)
for ma in "ABC":
    co_huong.them_dinh(ma)
co_huong.them_lien_ket("A", "B", 2)
co_huong.them_lien_ket("B", "C", 2)
co_huong.them_lien_ket("A", "C", 7)
co_huong.them_lien_ket("B", "A", 9)
print(co_huong.ke["A"])       # {'B': 2, 'C': 7}
print(co_huong.chi_phi_duong(["A", "C"]))       # 7
print(co_huong.chi_phi_duong(["A", "B", "C"]))  # 4
print(co_huong.chi_phi_duong(["B", "A"]))       # 9
print(co_huong.so_lien_ket())  # 4 cung

# Trọng số 0 vẫn là một liên kết có thật:
co_huong.them_lien_ket("C", "C", 0)
print(co_huong.chi_phi_duong(["C", "C"]))  # 0
print(co_huong.so_lien_ket())  # 5 cung, tính cả khuyên
```

**Bất biến của mã:** trong đồ thị vô hướng, với mọi cạnh `u—v`, cả `ke[u][v]` và `ke[v][u]` phải tồn tại và bằng cùng trọng số. Trong đồ thị có hướng, điều này **không bắt buộc**; cung ngược chỉ tồn tại khi đã được thêm riêng.

**Giới hạn:** lớp trên chưa triển khai xóa đỉnh/cạnh, tìm đường tối ưu, cập nhật trọng số hoặc đa đồ thị; `chi_phi_duong` chỉ **tính chi phí của một dãy đỉnh được đưa vào**, không tự tìm đường ngắn nhất. Khi bổ sung xóa, phải bảo đảm không có liên kết trỏ tới đỉnh đã biến mất.

## 11. Chọn thuật toán theo hướng và ý nghĩa trọng số

Không phải thuật toán nào cũng phù hợp mọi loại đồ thị. Cần phân biệt **tìm đường hợp lệ**, **đường ít bước** và **đường có tổng trọng số nhỏ nhất**.

| Mục tiêu | Điều kiện phù hợp | Gợi ý thuật toán | Điều cần lưu ý |
| --- | --- | --- | --- |
| Đến được đỉnh đích không? | Có hướng hoặc vô hướng; có/không trọng số | DFS/BFS | Duyệt đúng chiều các cung nếu đồ thị có hướng |
| Đường ít cạnh/cung nhất | Không trọng số hoặc mọi cạnh có cùng chi phí dương | BFS | Tối ưu **số bước**, không tối ưu trọng số khác nhau |
| Đường có tổng trọng số nhỏ nhất | Trọng số cạnh/cung **không âm** | Dijkstra | Trọng số 0 hợp lệ; không dùng bảo đảm này nếu có trọng số âm |
| Đường ngắn nhất với trọng số âm | Có thể có cạnh/cung âm, cần phát hiện chu trình âm liên quan | Bellman–Ford trong đồ thị có hướng | Chu trình âm có thể làm bài toán không có giá trị tối ưu hữu hạn |
| Đường ngắn nhất trên DAG | Đồ thị **có hướng không chu trình**, có thể có trọng số âm | Quy hoạch động theo thứ tự topo | Chỉ dùng khi thực sự là DAG |
| Cây khung nhỏ nhất | Đồ thị vô hướng, có trọng số (thường xét thành phần liên thông) | Kruskal/Prim | Không thay bằng khái niệm MST trực tiếp cho đồ thị có hướng |
| Sắp thứ tự phụ thuộc | Đồ thị có hướng không chu trình | Sắp xếp topo | Trọng số không phải yếu tố quyết định điều kiện trước–sau |

**Dijkstra** không yêu cầu trọng số phải lớn hơn 0; **trọng số bằng 0 vẫn dùng được**. Trọng số âm phá vỡ lập luận tham lam thông thường. Trong đồ thị **vô hướng** có cạnh âm và cho phép đi đi lại lại qua cạnh, ta có thể đi qua cạnh âm hai chiều lặp lại để giảm chi phí không giới hạn; vì vậy phải làm rõ khái niệm đường đi và điều kiện của bài toán trước khi áp dụng thuật toán ngắn nhất.

Với đồ thị mà trọng số chỉ là `0` hoặc `1`, thuật toán **0–1 BFS** dùng deque là một lựa chọn chuyên biệt; không nên gán mọi bài toán có trọng số cho BFS thông thường.

### Khi trọng số không phải chi phí cộng dồn

Nếu trọng số là **dung lượng tối đa của mỗi đường truyền**, tổng dung lượng của một đường không nhất thiết bằng tổng trọng số các cạnh: **nút thắt cổ chai** có thể là cạnh nhỏ nhất trên đường. Nếu trọng số là **xác suất độc lập**, xác suất thành công qua nhiều bước thường được kết hợp bằng **phép nhân**, không phải phép cộng đơn thuần.

Vì vậy, trước khi chọn thuật toán, phải định nghĩa **đại lượng cần tối ưu** và **phép tổng hợp trọng số trên đường**. Hai đồ thị có cùng cặp đầu mút và cùng các con số vẫn có thể đòi hỏi thuật toán khác nhau khi các con số mang ý nghĩa khác nhau.

## 12. Đổi từ loại đồ thị này sang loại khác có làm mất thông tin không?

Một số phép biến đổi thường gặp:

**Vô hướng → có hướng:** có thể thay mỗi cạnh `{u,v}` bằng hai cung `(u,v)` và `(v,u)`. Nếu cạnh có trọng số `w`, có thể gán cả hai cung cùng `w`. Tuy nhiên, đó là **quy ước mô phỏng quan hệ hai chiều**, không phải hai sự kiện độc lập trong dữ liệu gốc.

**Có hướng → vô hướng:** nếu chỉ bỏ chiều, phải quyết định điều gì xảy ra với `A→B` và `B→A`; một chiều hay hai chiều đủ để tạo cạnh `{A,B}`? Nếu hai cung có trọng số khác nhau, chọn trọng số vô hướng thế nào: `min`, `max`, trung bình hay từ chối gộp? Không có câu trả lời chung mà không dựa vào nghiệp vụ.

**Có trọng số → không trọng số:** xóa trọng số sẽ **mất thông tin**. Sau đó thuật toán chỉ biết liên kết tồn tại và có thể tối ưu số bước, không còn tối ưu chi phí ban đầu.

**Không trọng số → có trọng số:** gán `1` cho mỗi cạnh/cung có thể bảo toàn cách đếm bước; nhưng không tạo được quãng đường, phí hoặc thời gian thực tế từ dữ liệu chưa có.

**Bảng ví dụ chuyển đổi:**

| Trước | Sau | Thông tin cần quyết định |
| --- | --- | --- |
| `A—B` vô hướng, trọng số 5 | `A→B` và `B→A`, cùng trọng số 5 | Có giả định chi phí hai chiều bằng nhau không? |
| `A→B` giá 2, `B→A` giá 7 | `A—B` vô hướng | Chọn một trọng số chung bằng quy tắc nào? |
| `A→B` giá 0 | `A→B` không trọng số | Mất sự khác biệt giữa chi phí 0 và chi phí 1 |
| `A—B` không trọng số | `A—B` trọng số 1 | Trọng số 1 chỉ đại diện cho số bước |

## 13. Thiết kế dữ liệu: định danh, đơn vị và tính nhất quán

Khi biến đồ thị thành các bảng, dictionary hoặc mảng, phải xác định:

1. **Định danh đỉnh:** dùng ID ổn định, phân biệt với tên hiển thị. Đỉnh cô lập vẫn phải được lưu ngay cả khi danh sách kề rỗng.
2. **Tập liên kết hợp lệ:** hai đầu mút phải tồn tại; cho phép hay cấm khuyên, đa cạnh, hai cung ngược chiều.
3. **Đơn vị trọng số:** cùng một trường `weight` có đang trộn km với phút không? Nếu có nhiều loại đại lượng, cần cấu trúc dữ liệu rõ ràng, không cộng tùy tiện.
4. **Miền giá trị trọng số:** có cho phép 0, số âm, số thực, vô cực, giá trị thiếu hay không? Với thuật toán nhất định có thể cần ràng buộc trọng số không âm.
5. **Bất biến cập nhật:** thêm/xóa cạnh vô hướng phải thay đổi cả hai mục kề và trọng số của chúng phải khớp; thêm/xóa cung có hướng chỉ thay đổi đúng chiều nguồn–đích.
6. **Thời gian và tính động:** nếu thời gian di chuyển phụ thuộc giờ xuất phát, một số trọng số phải là **hàm theo thời gian**, không chỉ một số cố định.

Không nên dùng **`0` thay cho “không có liên kết”** trong hệ thống cho phép cạnh trọng số 0. Không nên dùng **`-1` thay cho “không có liên kết”** trong hệ thống cho phép trọng số âm. Một giá trị đánh dấu riêng hoặc một cấu trúc lưu sự tồn tại độc lập với trọng số sẽ ít nhập nhằng hơn.

## 14. Độ phức tạp và các lựa chọn biểu diễn

Với `n` đỉnh và `m` cạnh/cung, giả sử ID có chi phí băm và so sánh hằng số:

| Biểu diễn | Bộ nhớ | Kiểm tra có liên kết `u→v` | Duyệt láng giềng đi ra của `u` |
| --- | --- | --- | --- |
| Danh sách kề dạng list | `O(n+m)` | `O(\deg(u))` vô hướng; `O(\operatorname{outdeg}(u))` có hướng | `O(\deg(u))` hoặc `O(\operatorname{outdeg}(u))` |
| Danh sách kề dạng set/map | `O(n+m)` kỳ vọng về các mục | `O(1)` kỳ vọng | Tỷ lệ số láng giềng/mục kề |
| Ma trận kề | `O(n^2)` | `O(1)` sau khi biết chỉ số | `O(n)` để quét hàng |
| Danh sách cạnh/cung, không chỉ mục kề | `O(n+m)` nếu giữ cả V | `O(m)` nếu quét | `O(m)` nếu quét toàn bộ liên kết |

Ở đồ thị vô hướng dùng danh sách kề, một cạnh thường chiếm **hai mục kề**, nhưng vẫn là `O(n+m)` vì chỉ khác một hệ số hằng. Trong đồ thị có trọng số, mỗi mục kề phải lưu thêm trọng số hoặc tham chiếu đến bản ghi liên kết, không thay đổi bậc độ phức tạp bộ nhớ nếu mỗi trọng số có kích thước hằng số.

Đối với **đồ thị thưa** (`m\ll n^2`), danh sách kề thường tiết kiệm hơn ma trận. Đối với đồ thị dày, ma trận có thể phù hợp nếu thường xuyên cần kiểm tra một cặp đỉnh có kề hay không. Nếu dùng đa đồ thị, set/map láng giềng đơn giản không giữ được nhiều cạnh giữa cùng cặp đầu mút nếu không mở rộng biểu diễn.

## 15. Những ngộ nhận cần tránh

1. **“Có hướng thì phải có trọng số.”** Sai; hướng và trọng số là hai trục độc lập.
2. **“Vô hướng nghĩa là thêm hai cạnh.”** Sai trong mô hình toán học: chỉ một cạnh, có thể được lưu hai lần trong danh sách kề.
3. **“`A→B` đồng nghĩa `B→A`.”** Sai; đó là hai cung riêng nếu cùng tồn tại.
4. **“Cạnh không trọng số có giá 0.”** Sai nếu đang đếm bước: mỗi cạnh thường được coi là có chi phí 1.
5. **“Ô ma trận bằng 0 nghĩa là không có cạnh.”** Không an toàn khi trọng số 0 là hợp lệ.
6. **“BFS tìm đường rẻ nhất trong mọi đồ thị.”** Sai; BFS tối ưu số bước, không tối ưu tổng trọng số khác nhau.
7. **“Dijkstra chấp nhận mọi số thực.”** Sai với trọng số âm trong bảo đảm thuật toán thông thường.
8. **“Hai cung ngược chiều phải có cùng trọng số.”** Sai; với đồ thị có hướng chúng có thể khác nhau.
9. **“Tổng trọng số là bậc đỉnh.”** Sai; bậc đếm liên kết, tổng trọng số là phép tổng hợp số liệu khác.
10. **“Đồ thị chỉ gồm các đỉnh đã có cạnh.”** Sai; đỉnh cô lập vẫn phải nằm trong tập đỉnh.

## 16. Tự kiểm tra

**Câu 1.** Quan hệ “A phải học trước B” nên là cạnh vô hướng hay cung có hướng? Nếu không cần lưu mức độ khó, có cần trọng số không?

**Đáp án:** Nên dùng cung `A→B`. Quan hệ tiên quyết có chiều và không mặc nhiên có trọng số; chỉ thêm trọng số nếu nghiệp vụ cần một đại lượng định lượng cụ thể.

**Câu 2.** Trong đồ thị vô hướng có trọng số, cạnh `{A,B}` có trọng số 6. Danh sách kề dạng `(neighbor,weight)` cần chứa những mục nào?

**Đáp án:** Ở A lưu `(B,6)` và ở B lưu `(A,6)`. Đây là hai mục biểu diễn **một** cạnh vô hướng, không phải hai cạnh.

**Câu 3.** Với các cung `A→B` giá 2, `B→C` giá 2 và `A→C` giá 7, đường nào ít cung nhất, đường nào có tổng trọng số nhỏ nhất?

**Đáp án:** Ít cung nhất là `A→C` (1 cung). Tổng trọng số nhỏ nhất là `A→B→C` với giá `2+2=4`, nhỏ hơn 7.

**Câu 4.** Ma trận trọng số có `A[0][1]=0`. Có thể kết luận không có cung `0→1` không?

**Đáp án:** Không, nếu trọng số 0 hợp lệ. Phải xem quy ước biểu diễn: ví dụ `None` là vắng mặt và `0` là cung có thật với giá 0.

**Câu 5.** Đồ thị có hướng có hai cung `A→B` và `B→A`, cùng một khuyên `B→B`. Bậc vào và bậc ra của B là bao nhiêu?

**Đáp án:** `indeg(B)=2` từ `A→B`, `B→B`; `outdeg(B)=2` từ `B→A`, `B→B`. Trọng số nếu có không ảnh hưởng bậc.

**Câu 6.** Một mạng đường có `A→B` mất 5 phút và `B→A` mất 12 phút. Vì sao không nên ép thành một cạnh vô hướng có trọng số 5 hoặc 12 mà không có quy tắc nghiệp vụ?

**Đáp án:** Vì làm mất thông tin về hướng và chi phí khác nhau ở hai chiều. Muốn gộp, phải xác định rõ đại lượng và cách tổng hợp thích hợp.

**Câu 7.** Một đồ thị cho phép cung trọng số âm. Có thể dùng Dijkstra mà không điều kiện không? Điều gì cần kiểm tra?

**Đáp án:** Không. Dijkstra theo bảo đảm chuẩn cần trọng số không âm. Với cung âm có thể dùng thuật toán thích hợp như Bellman–Ford, đồng thời kiểm tra chu trình âm có ảnh hưởng đến đường đi đang xét.

**Câu 8.** Vì sao danh sách kề thường hợp với đồ thị thưa có trọng số, còn ma trận kề có thể lãng phí bộ nhớ?

**Đáp án:** Danh sách kề chỉ lưu các liên kết tồn tại và trọng số của chúng nên chiếm `O(n+m)`; ma trận cấp phát `n^2` ô dù phần lớn cặp đỉnh không nối với nhau.

**Câu 9.** Trong một lớp đồ thị đơn lưu `ke[u][v]=weight`, tại sao không thể dùng cùng một ô để biểu diễn hai chuyến xe A→B có ID và giá vé khác nhau?

**Đáp án:** Một khóa láng giềng `v` chỉ lưu được một trọng số cho `u`. Muốn giữ hai chuyến độc lập phải dùng nhiều bản ghi cạnh/cung, chẳng hạn `(neighbor,edge_id,weight)`.

**Ghi nhớ:** **Hướng** quyết định chiều nào có thể đi, còn **trọng số** quyết định thông tin định lượng gắn với mỗi liên kết; chúng là hai lựa chọn độc lập. Danh sách kề và ma trận kề phải biểu diễn nhất quán cả hướng, trọng số, liên kết trọng số 0 và các quy ước về khuyên/đa cạnh. Chỉ sau khi hiểu đồ thị thuộc loại nào, trọng số mang ý nghĩa gì và mục tiêu tối ưu là gì, ta mới chọn đúng thuật toán và đánh giá được thời gian, bộ nhớ của cấu trúc lưu trữ.

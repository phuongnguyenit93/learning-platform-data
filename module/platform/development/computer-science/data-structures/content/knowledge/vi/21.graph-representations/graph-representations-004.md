# Ma trận kề và chi phí theo số đỉnh

## 1. Vì sao ma trận kề có thể nhanh khi tra cứu cạnh nhưng tốn bộ nhớ?

Xét hệ thống học tập có nhiều học phần. Một quan hệ `A → B` nghĩa là phải hoàn thành học phần A trước khi học B. Nếu cần kiểm tra **“A có là điều kiện tiên quyết trực tiếp của B không?”** rất thường xuyên, ta muốn một phép tra cứu theo cặp đỉnh nhanh. Nhưng nếu có hàng chục nghìn học phần và chỉ vài quan hệ cho mỗi học phần, việc dành chỗ cho **mọi cặp đỉnh có thể có** lại lãng phí.

**Ma trận kề (adjacency matrix)** là cách biểu diễn đồ thị theo ý tưởng:

> Đánh số mỗi đỉnh từ `0` đến `n-1`; tạo bảng hai chiều `n × n`, trong đó ô ở hàng `i`, cột `j` mô tả liên kết từ đỉnh `i` tới đỉnh `j`.

Vì có `n^2` ô, chi phí lưu trữ của ma trận phụ thuộc chủ yếu vào **số đỉnh `n`**, không phải số cạnh thực tế `m`. Bù lại, khi biết chỉ số đỉnh, kiểm tra một cạnh/cung cụ thể chỉ cần đọc **một ô `O(1)`**.

Bài này sẽ giải thích cấu trúc, các bất biến cho đồ thị có hướng/vô hướng, cách lưu trọng số, và vì sao có thao tác `O(1)` nhưng có thao tác `O(n)` hoặc `O(n^2)`.

## 2. Định nghĩa toán học và quy ước ô ma trận

Cho đồ thị `G=(V,E)` có:

- `n=|V|` đỉnh;
- `m=|E|` cạnh nếu vô hướng, hoặc cung nếu có hướng;
- ánh xạ từ mỗi ID đỉnh sang một chỉ số trong `0,1,...,n-1`.

Với đồ thị **không trọng số**, có thể định nghĩa:

\[
A[i][j]=
\begin{cases}
1 & \text{nếu có cung }i\to j\text{ (hoặc cạnh }\{i,j\}\text{)},\\
0 & \text{nếu không có liên kết tương ứng.}
\end{cases}
\]

Tất cả các ô phải được khởi tạo với giá trị biểu thị **không có cạnh/cung**. Đỉnh không nối với ai vẫn có một hàng và một cột trong ma trận.

### Ví dụ vô hướng với bốn đỉnh

Chọn thứ tự đỉnh `[A,B,C,D]` và tập cạnh:

```text
E = {{A,B}, {A,C}, {B,C}}

       A ----- B       D
        \     /
         \   /
           C
```

Ma trận kề là:

| Hàng \ Cột | A | B | C | D |
| --- | ---: | ---: | ---: | ---: |
| **A** | 0 | 1 | 1 | 0 |
| **B** | 1 | 0 | 1 | 0 |
| **C** | 1 | 1 | 0 | 0 |
| **D** | 0 | 0 | 0 | 0 |

Ta đọc `A[A][B]=1` là có cạnh A—B; `A[D][C]=0` là không có cạnh D—C. Hàng D toàn số 0 nhưng D **không biến mất khỏi tập đỉnh**.

Với đồ thị vô hướng, ma trận **đối xứng qua đường chéo chính**: `A[i][j]=A[j][i]`. Một cạnh vô hướng `{A,B}` xuất hiện tại **hai ô đối xứng**, nhưng về mặt toán học vẫn chỉ là **một cạnh**.

## 3. Đồ thị có hướng: hàng là nguồn, cột là đích

Với đồ thị có hướng, cung `(u,v)` có nghĩa `u → v`. Theo quy ước hàng nguồn – cột đích:

\[
A[i][j]=1\iff (i,j)\in E.
\]

Xét `V=[A,B,C,D]` và các cung `A→B`, `B→C`, `C→A`:

```text
A ---> B ---> C
^             |
|_____________|

D cô lập
```

| Hàng \ Cột | A | B | C | D |
| --- | ---: | ---: | ---: | ---: |
| **A** | 0 | 1 | 0 | 0 |
| **B** | 0 | 0 | 1 | 0 |
| **C** | 1 | 0 | 0 | 0 |
| **D** | 0 | 0 | 0 | 0 |

Ma trận **không cần đối xứng**: `A[A][B]=1` trong khi `A[B][A]=0`. Nếu thêm cung `B→A`, ta chỉ cập nhật `A[B][A]`; cung `A→B` vốn có không thay đổi.

**Bất biến khi thêm cung:** chỉ cập nhật ô của **đúng chiều**. Tự động ghi cả `A[j][i]` sẽ làm xuất hiện cung ngược không có trong dữ liệu.

## 4. Khuyên, đường chéo chính và cạnh song song

Một **khuyên (self-loop)** là liên kết có nguồn và đích cùng một đỉnh. Trong ma trận kề, nó nằm ở **ô đường chéo** `A[i][i]`.

- Nếu đồ thị không cho phép khuyên, mọi ô `A[i][i]` phải biểu thị **không có liên kết**.
- Nếu cho phép khuyên, `A[i][i]` có thể là 1, hoặc trọng số/đối tượng đại diện cho khuyên.
- Trong đồ thị **vô hướng**, khuyên tăng **bậc** của đỉnh lên **2** theo quy ước thông thường, mặc dù chỉ chiếm **một ô đường chéo**.
- Trong đồ thị **có hướng**, cung khuyên tăng **bậc ra** và **bậc vào** mỗi loại **1**.

Ví dụ với đồ thị vô hướng ở mục 2, thêm một khuyên tại C làm `A[C][C]=1`. Khi đó:

\[
\deg(C)=\sum_{j=0}^{n-1}A[C][j]+A[C][C]=3+1=4.
\]

Vì sao cộng thêm `A[C][C]`? Tổng hàng đếm ô đường chéo đúng một lần, còn khuyên phải đóng góp hai đầu mút cho bậc vô hướng.

### Trường hợp đa đồ thị

Ma trận Boolean/0–1 chỉ lưu **có ít nhất một liên kết**. Nếu có hai tuyến A–B khác nhau, `A[A][B]=1` không cho biết có một hay hai tuyến.

Để biểu diễn **đa đồ thị**, có thể đổi ý nghĩa mỗi ô:

- **Số lượng:** `A[i][j]` bằng số cạnh/cung giữa hai đỉnh theo chiều tương ứng.
- **Danh sách edge ID:** `A[i][j]=[e_1,e_2,...]`; tra thông tin từng cạnh qua bảng cạnh riêng.
- **Danh sách bản ghi trọng số:** nếu cần giữ từng liên kết và thuộc tính của nó.

Với ma trận **đếm số cạnh** của đa đồ thị vô hướng, `A[i][i]` thường lưu **số khuyên**, không phải số đầu mút; vì vậy công thức bậc phải tính đường chéo **hai lần**. Nếu mỗi ô chỉ lưu một trọng số, các cạnh song song có trọng số khác nhau sẽ bị gộp hoặc ghi đè.

Phần còn lại chủ yếu xét **đồ thị đơn**, tức mỗi cặp đỉnh theo chiều thích hợp có tối đa một liên kết.

## 5. Có trọng số: phải phân biệt không có cạnh với cạnh giá 0

Với đồ thị có trọng số, ô ma trận có thể lưu trực tiếp `w(u,v)`, ví dụ số phút di chuyển. Nhưng một lỗi thiết kế phổ biến là dùng `0` vừa để biểu diễn **không có cạnh** vừa để biểu diễn **cạnh trọng số bằng 0**.

Chọn `None` là dấu vắng liên kết:

```text
                    B          C
Hàng của A:        0.0        None

A -> B tồn tại, trọng số bằng 0.0.
A -> C không tồn tại.
```

Trong Python, phải kiểm tra `cell is not None`, **không** dùng `if cell`: trọng số `0` là falsy nhưng vẫn đại diện cho cạnh hợp lệ.

Một số thuật toán đường đi dùng `+∞` để chỉ “chưa có đường trực tiếp”; cách đó phù hợp với những quy ước và phép tính nhất định. Khi dùng ma trận trọng số tổng quát, dấu vắng như `None` tránh nhập nhằng với một trọng số số học. Đồ thị vô hướng có trọng số phải giữ `A[i][j]=A[j][i]` về cả **sự tồn tại** và **trọng số**.

Trong đồ thị có hướng, trọng số của `A→B` và `B→A` (nếu cả hai có mặt) **không nhất thiết bằng nhau**.

## 6. Vì sao chi phí bộ nhớ là O(n²), không phải O(m)?

Ma trận kề cấp phát **`n` hàng, mỗi hàng `n` ô**:

\[
\text{số ô}=n\cdot n=n^2.
\]

Với đơn vị ô có kích thước cố định, chi phí bộ nhớ là:

\[
S(n)=\Theta(n^2).
\]

Các ô tương ứng **cạnh không tồn tại** vẫn chiếm chỗ. Do đó, ngay cả đồ thị không có cạnh nào (`m=0`) vẫn cần `n^2` ô nếu biểu diễn bằng ma trận đặc (*dense matrix*).

| Số đỉnh `n` | Số ô `n²` | Nếu giả sử đúng 1 byte/ô | Nếu giả sử 4 byte/ô |
| ---: | ---: | ---: | ---: |
| 100 | 10.000 | 10 KB | 40 KB |
| 1.000 | 1.000.000 | 1 MB | 4 MB |
| 10.000 | 100.000.000 | 100 MB | 400 MB |

Con số ở đây sử dụng **MB thập phân**, chỉ là **dung lượng dữ liệu thô** dưới giả định 1 hoặc 4 byte cho mỗi ô. Một ma trận Python dạng danh sách của danh sách còn có đối tượng danh sách, con trỏ tham chiếu và overhead khác, nên **không thể coi** các số trong bảng là lượng RAM thực tế mà ví dụ Python sử dụng. Một **bitset** chuyên dụng có thể giảm chi phí lưu Boolean xuống xấp xỉ một bit cho mỗi ô, nhưng bậc `\Theta(n^2)` vẫn không đổi.

### Khi đồ thị thưa hoặc dày

Trong đồ thị vô hướng đơn **không khuyên**, số cạnh tối đa là:

\[
m_{\max}=\frac{n(n-1)}2.
\]

Trong đồ thị có hướng đơn **không khuyên**, số cung tối đa là:

\[
m_{\max}=n(n-1).
\]

Nếu `m\ll n^2` (đồ thị **thưa**), phần lớn ô ma trận rỗng, nên **danh sách kề** với bộ nhớ `O(n+m)` thường kinh tế hơn. Nếu `m=\Theta(n^2)` (đồ thị **dày**), ma trận và danh sách kề cùng bậc bộ nhớ tiệm cận, và ma trận có lợi thế kiểm tra cạnh cụ thể bằng một truy cập ô.

**Lưu ý:** “đồ thị dày” không mặc nhiên có nghĩa ma trận luôn nhanh hơn trong mọi chương trình; còn phải xét lưu trữ, kiểu dữ liệu, mẫu truy cập, chi phí cập nhật và thuật toán sử dụng.

## 7. Chi phí thao tác: O(1), O(n) và O(n²) đến từ đâu?

Giả sử đã có **chỉ số nguyên** của các đỉnh và mỗi ô được truy cập trong thời gian hằng số:

| Thao tác với ma trận kề đặc | Chi phí điển hình | Giải thích |
| --- | --- | --- |
| Tạo ma trận ban đầu | `O(n²)` thời gian và bộ nhớ | Khởi tạo `n²` ô |
| Kiểm tra cạnh/cung `u→v` | `O(1)` | Đọc `A[u][v]` |
| Thêm cạnh/cung vào đồ thị đơn | `O(1)` | Ghi một ô; vô hướng ghi thêm ô đối xứng |
| Xóa một cạnh/cung theo đầu mút | `O(1)` | Đặt ô tương ứng về trạng thái vắng liên kết |
| Cập nhật trọng số một cạnh/cung | `O(1)` | Sửa một hoặc hai ô |
| Duyệt láng giềng đi ra của `u` | `O(n)` | Phải kiểm tra toàn bộ `n` cột của hàng `u` |
| Tính bậc ra `u` từ ma trận | `O(n)` | Đếm những ô có cung trong hàng `u` |
| Tính bậc vào `u` từ ma trận | `O(n)` | Đếm những ô có cung trong cột `u` |
| Duyệt tất cả các cạnh/cung | `O(n²)` | Quét ma trận; vô hướng có thể chỉ quét nửa trên và đường chéo |
| Thêm một đỉnh trong ma trận danh sách động | `O(n)` | Thêm một cột vào `n` hàng và một hàng mới dài `n+1` |
| Xóa đỉnh và nén lại chỉ số | `O(n²)` trường hợp xấu | Bỏ một cột khỏi nhiều hàng, dời phần tử, cập nhật ánh xạ chỉ số |

**Chỉ số/ID:** nếu đầu vào của API là chuỗi ID như `"SV101"` thay vì chỉ số nguyên, còn có bước `id_to_index[id]`. Với bảng băm ánh xạ ID sang chỉ số, bước đó thường **`O(1)` kỳ vọng** khi hash/so sánh ID có chi phí hằng số; không nên coi là bảo đảm thời gian xấu nhất. Nếu ID rất dài, việc băm chuỗi còn có chi phí xử lý ký tự.

**Đếm bậc có thể tối ưu bằng bộ đếm:** nếu luôn duy trì `indegree` và `outdegree` khi thêm/xóa cạnh, truy vấn bậc có thể giảm về `O(1)`. Nhưng đó là **thông tin phụ**, cần cập nhật đúng cả với khuyên và khi xóa đỉnh.

### Một điểm cần phân biệt khi thêm đỉnh

Với **ma trận bằng các list Python có thể mở rộng**, thêm đỉnh mới `x` thường làm:

1. Thêm một ô rỗng vào cuối **mỗi hàng cũ**: `n` ô mới.
2. Tạo một **hàng mới** gồm `n+1` ô rỗng.
3. Thêm `x` vào bảng ánh xạ ID → chỉ số.

Số ô mới là `2n+1`, nên chi phí **phân bổ điển hình** là `O(n)` khi các thao tác `append` được khấu hao; một vài lần cấp phát lại bên trong list có thể đắt hơn. Nếu ma trận được cấp phát thành **một khối nhớ liên tiếp kích thước chính xác**, việc tăng chiều từ `n×n` lên `(n+1)×(n+1)` có thể phải sao chép **`\Theta(n²)` ô**. Vì vậy, phải nêu rõ **cách tổ chức bộ nhớ** trước khi gán một cận resize cụ thể.

## 8. Ví dụ Python: cài đặt ma trận kề với ID đỉnh

Lớp sau minh họa **đồ thị đơn** có thể có hướng hoặc vô hướng, có trọng số hoặc không trọng số. Nó sử dụng `None` để biểu diễn **không tồn tại liên kết**, cho phép **trọng số 0** và **khuyên**, nhưng không cho nhiều cạnh/cung cùng một cặp đầu mút theo đúng chiều. ID đỉnh được ánh xạ sang vị trí trong danh sách.

```python
from math import isfinite


class MaTranKe:
    def __init__(self, co_huong=False, co_trong_so=False):
        self.co_huong = co_huong
        self.co_trong_so = co_trong_so
        self.id_dinh = []   # index -> vertex_id
        self.vi_tri = {}    # vertex_id -> index
        self.a = []         # ma trận, None nghĩa là không có liên kết

    def them_dinh(self, ma: str):
        if ma in self.vi_tri:
            raise ValueError("Đỉnh đã tồn tại")
        n = len(self.id_dinh)
        for hang in self.a:
            hang.append(None)         # Cột mới ở cuối mỗi hàng cũ
        self.a.append([None] * (n + 1))  # Hàng mới
        self.vi_tri[ma] = n
        self.id_dinh.append(ma)

    def _chi_so(self, ma: str):
        return self.vi_tri[ma]  # KeyError nếu đỉnh không tồn tại

    def them_canh(self, u: str, v: str, trong_so=None):
        i, j = self._chi_so(u), self._chi_so(v)
        if self.co_trong_so:
            if (isinstance(trong_so, bool)
                    or not isinstance(trong_so, (int, float))
                    or not isfinite(trong_so)):
                raise ValueError("Trọng số phải là số hữu hạn")
            w = trong_so
        else:
            if trong_so is not None:
                raise ValueError("Đồ thị không trọng số")
            w = 1           # Mỗi liên kết được tính là 1 bước

        if self.a[i][j] is not None:
            raise ValueError("Cạnh/cung này đã tồn tại")
        self.a[i][j] = w
        if not self.co_huong:
            self.a[j][i] = w  # Đảm bảo đối xứng

    def co_canh(self, u: str, v: str):
        i, j = self._chi_so(u), self._chi_so(v)
        return self.a[i][j] is not None

    def trong_so(self, u: str, v: str):
        i, j = self._chi_so(u), self._chi_so(v)
        return self.a[i][j]  # None nếu không có liên kết

    def xoa_canh(self, u: str, v: str):
        i, j = self._chi_so(u), self._chi_so(v)
        if self.a[i][j] is None:
            raise KeyError("Không có cạnh/cung")
        self.a[i][j] = None
        if not self.co_huong:
            self.a[j][i] = None

    def lang_gieng(self, u: str):
        i = self._chi_so(u)
        for j, w in enumerate(self.a[i]):
            if w is not None:
                yield self.id_dinh[j], w

    def bac(self, u: str):
        if self.co_huong:
            raise ValueError("Hãy dùng bac_ra/bac_vao")
        i = self._chi_so(u)
        so_o_co_canh = sum(w is not None for w in self.a[i])
        return so_o_co_canh + (self.a[i][i] is not None)

    def bac_ra(self, u: str):
        if not self.co_huong:
            raise ValueError("Đồ thị vô hướng")
        i = self._chi_so(u)
        return sum(w is not None for w in self.a[i])

    def bac_vao(self, u: str):
        if not self.co_huong:
            raise ValueError("Đồ thị vô hướng")
        j = self._chi_so(u)
        return sum(self.a[i][j] is not None
                   for i in range(len(self.id_dinh)))

    def so_canh(self):
        n = len(self.id_dinh)
        if self.co_huong:
            return sum(w is not None
                       for hang in self.a for w in hang)
        return sum(self.a[i][j] is not None
                   for i in range(n) for j in range(i, n))

    def xoa_dinh(self, u: str):
        i = self._chi_so(u)
        self.id_dinh.pop(i)
        self.a.pop(i)        # Bỏ cả hàng liên quan
        for hang in self.a:
            hang.pop(i)     # Bỏ cột tương ứng
        self.vi_tri = {ma: j for j, ma in enumerate(self.id_dinh)}


# Vô hướng, không trọng số
g = MaTranKe()
for ma in "ABCD":
    g.them_dinh(ma)
for u, v in [("A", "B"), ("A", "C"), ("B", "C")]:
    g.them_canh(u, v)

print([[int(w is not None) for w in hang] for hang in g.a])
# [[0, 1, 1, 0],
#  [1, 0, 1, 0],
#  [1, 1, 0, 0],
#  [0, 0, 0, 0]]
print(g.co_canh("A", "C"))       # True
print(list(g.lang_gieng("A")))  # [('B', 1), ('C', 1)]
print(g.so_canh())              # 3

g.them_canh("C", "C")          # Một khuyên ở C
print(g.bac("C"))              # 4: A-C, B-C, khuyên tính 2
print(g.so_canh())             # 4
g.xoa_dinh("B")
print(g.id_dinh)               # ['A', 'C', 'D']
print(g.co_canh("A", "C"))      # True: chỉ số đã được cập nhật
print(g.so_canh())             # 2: A-C và khuyên C-C

# Có hướng, có trọng số
h = MaTranKe(co_huong=True, co_trong_so=True)
for ma in "ABC":
    h.them_dinh(ma)
h.them_canh("A", "B", 0)
h.them_canh("B", "C", 2.5)
h.them_canh("C", "A", 5)
h.them_canh("C", "C", 1)
print(h.co_canh("A", "B"), h.trong_so("A", "B"))  # True 0
print(h.co_canh("B", "A"))                     # False
print(h.bac_ra("C"), h.bac_vao("C"))          # 2 2
print(h.so_canh())                            # 4 cung
```

Trong lớp này, **đọc hoặc cập nhật cạnh cụ thể** chỉ cần truy cập ô sau khi có chỉ số. Ngược lại, `lang_gieng`, `bac_ra`, `bac_vao` quét hàng/cột `n` ô; `so_canh` quét nhiều ô và mất `O(n²)`.

Phương thức `xoa_dinh` **xóa luôn tất cả liên kết liên quan** bằng cách bỏ một hàng và cột. Nó thay đổi chỉ số của những đỉnh đứng sau đỉnh bị xóa, nên bắt buộc cập nhật `vi_tri`. Các đoạn mã khác không được giữ một chỉ số cũ rồi tiếp tục dùng sau thao tác này.

Ví dụ chỉ mô phỏng dữ liệu trong bộ nhớ, không giải quyết truy cập đồng thời, cấp phát thất bại, định danh tái sử dụng hoặc các bảo đảm giao dịch. Nó cũng chưa hiện thực đa đồ thị có cạnh song song; `them_canh` từ chối việc chèn cùng cặp đầu mút lần thứ hai.

## 9. BFS/DFS trên ma trận kề: vì sao có thể thành O(n²)?

**BFS (duyệt theo chiều rộng)** và **DFS (duyệt theo chiều sâu)** thường được giới thiệu với thời gian `O(n+m)` khi dùng danh sách kề: mỗi đỉnh được thăm, mỗi cạnh/cung được xét một số lần hằng định.

Với **ma trận kề đặc**, để tìm những láng giềng của **một đỉnh**, thuật toán phải quét cả hàng `n` ô, kể cả khi đỉnh chỉ có một láng giềng. Nếu duyệt toàn bộ đồ thị, có tới `n` hàng được quét:

\[
T_{\text{BFS/DFS trên ma trận}}=O(n\cdot n)=O(n^2).
\]

Đây là **cận cho việc duyệt toàn bộ đỉnh** và dùng cách quét hàng thông thường. Nếu chỉ duyệt từ một đỉnh và tới được `r\le n` đỉnh, phần quét hàng là `O(rn)`, cộng thêm khởi tạo dữ liệu phụ (thường `O(n)`). Khi `r=n`, cận trở thành `O(n^2)`.

Ví dụ có `n=1000` đỉnh nhưng chỉ `m=999` cạnh tạo thành một đường dây, danh sách kề duyệt toàn bộ trong `O(n+m)=O(n)`; ma trận vẫn có thể phải xem gần `1.000.000` ô. Đó là lý do **đồ thị thưa** thường ưu tiên danh sách kề cho các thuật toán duyệt.

Ngược lại, trên đồ thị dày với `m=\Theta(n^2)`, cả hai biểu diễn đều có cận duyệt toàn bộ `O(n^2)`, dù chi phí hằng số và tính thân thiện bộ nhớ có thể khác.

## 10. Thêm/xóa đỉnh và bài toán chỉ số ổn định

Các cạnh trong ma trận được nhận diện bằng **tọa độ hàng–cột**, nên ID ngoài ứng dụng phải có ánh xạ ổn định tới chỉ số hoặc phải được cập nhật mỗi khi đổi chỉ số.

Ví dụ trước khi xóa B:

```text
ID:       A   B   C   D
index:    0   1   2   3
```

Nếu xóa **hàng và cột 1** để giữ ma trận liên tục, thứ tự mới là:

```text
ID:       A   C   D
index:    0   1   2
```

Đỉnh C đổi từ chỉ số 2 sang 1. Nếu một cấu trúc ngoài ma trận vẫn giữ `C -> 2`, lần tìm cạnh sau đó có thể truy cập nhầm đỉnh D hoặc truy cập sai vị trí.

Có hai hướng thiết kế:

- **Nén lại:** xóa hàng/cột, cập nhật ánh xạ ID–chỉ số; giữ ma trận gọn `n×n` nhưng chi phí xóa một đỉnh có thể là `O(n²)`.
- **Giữ ô trống (tombstone cho chỉ số đỉnh):** không dời chỉ số cũ, đánh dấu đỉnh đã xóa và quản lý một tập chỉ số còn hiệu lực. Cách này tránh đổi chỉ số của các đỉnh khác, nhưng ma trận vẫn chiếm chỗ cho cả chỉ số không còn dùng và cần quy tắc tái sử dụng an toàn.

Nếu lưu ma trận trong một khối nhớ cố định, việc mở rộng số đỉnh có thể đòi hỏi cấp phát lại toàn bộ. Với đồ thị thường xuyên thêm/xóa đỉnh, cần cân nhắc **danh sách kề** hoặc một cấu trúc có khả năng thay đổi quy mô linh hoạt hơn.

## 11. Khi nào chọn ma trận kề, khi nào chọn danh sách kề?

| Tiêu chí | Ma trận kề đặc | Danh sách kề |
| --- | --- | --- |
| Bộ nhớ | `\Theta(n^2)` | `\Theta(n+m)` với biểu diễn chuẩn |
| Kiểm tra cặp đỉnh có kề không | `O(1)` theo chỉ số | `O(deg(u))` nếu dùng list, hoặc `O(1)` kỳ vọng nếu dùng set/map |
| Duyệt láng giềng một đỉnh | `O(n)` | `O(deg(u))` vô hướng hoặc `O(outdeg(u))` có hướng |
| Duyệt toàn bộ đồ thị bằng BFS/DFS | `O(n^2)` | `O(n+m)` |
| Thêm/xóa cạnh theo hai ID đã ánh xạ | `O(1)` | Tùy biểu diễn láng giềng, có thể phải tìm và xóa |
| Thêm/xóa đỉnh | Thường phải thêm hoặc bỏ hàng/cột | Thường thuận tiện hơn, nhưng vẫn phải xử lý các cạnh liên quan |
| Trọng số hoặc khuyên | Ô ma trận chứa giá trị; đường chéo biểu diễn khuyên | Mục kề chứa trọng số/ID; cần quy ước riêng với khuyên |
| Cạnh song song | Cần mở rộng ô để giữ số lượng hoặc danh sách ID | Danh sách mục kề kèm ID thường tự nhiên |

Với đồ thị **dày, số đỉnh tương đối ổn định, nhiều truy vấn kiểm tra cặp `(u,v)`**, ma trận là lựa chọn đáng cân nhắc. Với đồ thị **thưa, số đỉnh lớn, thường xuyên duyệt láng giềng hoặc thêm/xóa đỉnh**, danh sách kề thường tiết kiệm và linh hoạt hơn.

Một ứng dụng cũng có thể duy trì **cả danh sách kề và một cấu trúc chỉ mục kiểm tra kề**. Đổi lại, mọi thao tác cập nhật phải giữ hai cấu trúc đồng bộ; không thể chỉ tính lợi ích đọc mà bỏ qua thời gian, bộ nhớ và tính nhất quán khi ghi.

## 12. Những lỗi thường gặp

1. **Đếm số ô có giá trị 1 thành số cạnh vô hướng:** một cạnh `u—v`, `u\ne v`, chiếm hai ô đối xứng nhưng chỉ là **một cạnh**.
2. **Quên đối xứng khi thêm cạnh vô hướng:** `A[i][j]` và `A[j][i]` khác nhau làm mất bất biến.
3. **Tự tạo cung ngược khi đồ thị có hướng:** ghi hai ô trong khi chỉ có một cung là sai dữ liệu.
4. **Dùng `if A[i][j]` khi trọng số 0 hợp lệ:** cạnh giá 0 bị coi nhầm là vắng mặt.
5. **Quên lưu đỉnh cô lập:** dù hàng/cột toàn dấu vắng mặt, đỉnh vẫn tồn tại trong `V`.
6. **Đếm khuyên vô hướng một lần vào bậc:** theo quy ước bậc chuẩn phải đóng góp **2**.
7. **Khẳng định mọi thao tác trên ma trận đều `O(1)`:** chỉ tra cứu ô cụ thể là `O(1)`; duyệt hàng cần `O(n)`, duyệt toàn bộ cần `O(n^2)`.
8. **Nói thêm đỉnh luôn `O(1)`:** kích thước ma trận tăng theo cả hàng và cột; trong một số cách cấp phát còn phải sao chép nhiều ô.
9. **Giữ chỉ số cũ sau khi xóa đỉnh:** các đầu mút có thể bị ánh xạ nhầm nếu ma trận được nén.
10. **Dùng ma trận 0–1 cho nhiều cạnh song song:** làm mất tính bội và thuộc tính từng liên kết.

## 13. Tự kiểm tra

**Câu 1.** Ma trận kề của đồ thị `n=1000` đỉnh có bao nhiêu ô dù đồ thị chỉ có 10 cạnh?

**Đáp án:** `1000^2=1.000.000` ô. Ma trận đặc dành chỗ cho mọi cặp đỉnh, nên bộ nhớ `\Theta(n^2)` không phụ thuộc trực tiếp vào `m=10`.

**Câu 2.** Vì sao ma trận của đồ thị vô hướng phải đối xứng? Nếu `A[1][3]=1` thì `A[3][1]` bằng bao nhiêu?

**Đáp án:** Cạnh vô hướng `{1,3}` không phân biệt hai đầu mút; phải có `A[3][1]=1`.

**Câu 3.** Trong đồ thị có hướng, nếu `A[1][3]=1` và `A[3][1]=0`, điều gì được xác nhận?

**Đáp án:** Có cung từ 1 đến 3, không có cung từ 3 đến 1. Đây là cấu hình hợp lệ cho đồ thị có hướng.

**Câu 4.** Đồ thị vô hướng có ba cạnh giữa những đỉnh khác nhau và một khuyên. Nếu ma trận Boolean chứa các liên kết đó, tổng số ô bằng 1 là bao nhiêu? Tổng bậc các đỉnh bằng bao nhiêu?

**Đáp án:** Có `3\cdot2+1=7` ô bằng 1. Tổng bậc là `2\cdot4=8`; khuyên đóng góp 2 vào tổng bậc dù chỉ chiếm một ô đường chéo.

**Câu 5.** Tại sao phép `co_canh("A","B")` trong ví dụ Python phải kiểm tra `is not None` thay vì chuyển giá trị ô thành Boolean?

**Đáp án:** Vì một cung trọng số `0` vẫn tồn tại. `bool(0)` là `False`, nên chuyển trực tiếp sang Boolean sẽ trả lời sai.

**Câu 6.** Với ma trận kề, truy vấn `A[u][v]` là `O(1)`; vì sao `lang_gieng(u)` lại `O(n)`?

**Đáp án:** Muốn liệt kê láng giềng của `u` phải kiểm tra **tất cả `n` cột** trong hàng `u`, kể cả những ô không có cạnh.

**Câu 7.** Duyệt toàn bộ đồ thị bằng BFS có danh sách kề và ma trận kề khác nhau ra sao nếu `m=O(n)`?

**Đáp án:** Danh sách kề cho cận `O(n+m)=O(n)`; ma trận kề đặc với thao tác quét mỗi hàng cho cận `O(n^2)`.

**Câu 8.** Khi xóa đỉnh B ở vị trí 1 của `[A,B,C,D]` bằng cách bỏ hàng/cột, vì sao phải sửa ánh xạ chỉ số của C và D?

**Đáp án:** Hai đỉnh đổi chỉ số: C từ 2 thành 1, D từ 3 thành 2. Giữ ánh xạ cũ khiến việc tra cứu cạnh/cung dùng sai hàng hoặc cột.

**Câu 9.** Ma trận kề 0–1 chứa `A[A][B]=1`. Từ đó có biết chính xác có mấy tuyến A–B trong đa đồ thị không?

**Đáp án:** Không. Nó chỉ cho biết có **ít nhất một** liên kết; để giữ nhiều tuyến phải lưu số lượng hoặc danh sách ID tại ô tương ứng, hay dùng cấu trúc đa đồ thị khác.

**Ghi nhớ:** Ma trận kề dành **một ô cho mỗi cặp đỉnh** nên lưu trữ đặc có chi phí **`\Theta(n^2)`**, kể cả khi đồ thị rất thưa. Đổi lại, kiểm tra hoặc cập nhật **một cạnh/cung đã biết hai đầu mút** cần `O(1)` sau khi ánh xạ ID sang chỉ số. Duyệt láng giềng phải xem `n` ô, duyệt toàn bộ thường `O(n^2)`; thêm/xóa đỉnh còn liên quan đến hàng, cột và chỉ số. Chọn ma trận khi mật độ cạnh, mẫu truy vấn và sự ổn định của tập đỉnh phù hợp; nếu đồ thị thưa và cần duyệt nhiều, hãy cân nhắc danh sách kề.

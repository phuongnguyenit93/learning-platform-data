# Biểu diễn nén CSR, CSC và đánh đổi khi cập nhật

## 1. Tại sao đồ thị thưa thường cần một cách lưu gọn hơn?

Giả sử nền tảng học tập quản lý hàng trăm nghìn học phần và tài nguyên liên quan. Mỗi học phần chỉ liên kết trực tiếp tới một số học phần khác. Một **ma trận kề** phải cấp phát `n × n` ô cho mọi cặp đỉnh, kể cả khi phần lớn cặp không có cung. **Danh sách kề** chỉ lưu liên kết có thật, nhưng nếu được cài bằng `n` đối tượng list riêng lẻ, nó vẫn có thể tốn bộ nhớ quản lý và tạo nhiều vùng cấp phát nhỏ.

**CSR (Compressed Sparse Row)** và **CSC (Compressed Sparse Column)** giải quyết một phần vấn đề đó: gom các liên kết thành **những mảng liên tiếp**, dùng một mảng offset để chỉ ra đoạn dữ liệu thuộc về từng đỉnh. Mục tiêu là **bố trí bộ nhớ gọn và duyệt nhanh**, đặc biệt khi đồ thị lớn và tương đối ít thay đổi.

Đổi lại, với mảng nén truyền thống, **chèn hoặc xóa một cung** có thể phải dịch chuyển nhiều phần tử và thay đổi hàng loạt offset. Vì vậy, cấu trúc tốt cho **đọc và duyệt** chưa chắc tốt cho **cập nhật trực tiếp**.

Sau bài này, người học cần:

- Đọc và dựng đúng các mảng của CSR/CSC.
- Phân biệt **hàng nguồn** với **cột đích** trong đồ thị có hướng.
- Hiểu các bất biến của offset, chỉ số láng giềng, trọng số và ID cung.
- Giải thích chi phí bộ nhớ, duyệt, kiểm tra cạnh, tạo chỉ mục và cập nhật theo `n,m`.
- Biết khi nào nên dùng CSR, CSC, cả hai, hay danh sách kề động.

## 2. Định nghĩa đồ thị và hai hướng tra cứu

Cho đồ thị có hướng `G=(V,E)`, với `n=|V|` đỉnh và `m=|E|` cung. Đầu tiên giả sử các đỉnh đã được ánh xạ sang chỉ số `0,1,...,n-1`. Một cung `(u,v)` có:

- **Nguồn** `u`: đỉnh mà cung **đi ra**.
- **Đích** `v`: đỉnh mà cung **đi vào**.

Chọn ma trận kề logic `A` theo quy ước:

\[
A[u,v]\ne0\quad\Longleftrightarrow\quad
\text{có cung }u\rightarrow v
\]

trong trường hợp giá trị khác 0 biểu diễn liên kết không trọng số. Nếu **trọng số 0 là hợp lệ**, phải lưu **sự hiện diện của cung** độc lập với giá trị số của nó, không dùng điều kiện `A[u,v] != 0` để kiểm tra.

Hai kiểu truy vấn quan trọng:

- **Cung đi ra (outgoing):** `out[u]` liệt kê các cung `u→v`. Đây là điều CSR của ma trận `A` thuận tiện thực hiện.
- **Cung đi vào (incoming):** `in[v]` liệt kê các cung `u→v`. Đây là điều CSC của cùng ma trận `A` thuận tiện thực hiện.

CSR và CSC **không định nghĩa hai tập cung khác nhau**. Chúng là **hai cách lập chỉ mục cùng tập cung**. Nếu dữ liệu gốc là vô hướng, mỗi cạnh `{u,v}` thường được biểu diễn bởi **hai mục kề** `u→v` và `v→u` trong cấu trúc nén, nhưng đó vẫn là **một cạnh toán học**.

## 3. CSR lưu những mảng nào?

**CSR — Compressed Sparse Row** nhóm các mục liên kết theo **hàng nguồn**.

Với đồ thị có hướng và `m` cung, cấu trúc cơ bản gồm:

| Mảng | Số phần tử | Vai trò |
| --- | ---: | --- |
| `row_ptr` hoặc `offset` | `n+1` | Ranh giới đoạn các cung đi ra của từng đỉnh |
| `col_idx` hoặc `neighbor` | `m` | Đỉnh đích của mỗi cung, xếp liền nhau theo nguồn |
| `weight` (*tùy chọn*) | `m` | Trọng số của cung ở cùng vị trí |
| `edge_id` (*tùy chọn*) | `m` | Định danh riêng của cung, nhất là khi có cung song song |

**Cách đọc đoạn cung đi ra của đỉnh `u`:**

\[
\operatorname{out}(u)=
\texttt{col\_idx[row\_ptr[u]:row\_ptr[u+1]]}.
\]

Các mảng `weight` và `edge_id`, nếu có, được cắt theo **cùng khoảng chỉ số** đó. Mỗi vị trí `k` tương ứng một **cung duy nhất** và những thuộc tính của nó:

```text
k             0      1      2      ...
col_idx[k]    đích   đích   đích
edge_id[k]    id     id     id
weight[k]     w      w      w
```

Đọc `row_ptr[u]` là `O(1)` khi `u` là chỉ số nguyên hợp lệ; duyệt hết cung ra từ `u` tốn **`\Theta(outdeg(u))`**. Đỉnh có bậc ra 0 có hai offset liên tiếp **bằng nhau**, không phải một hàng được loại bỏ khỏi tập đỉnh.

## 4. Ví dụ CSR có cung song song, khuyên và đỉnh không có cung ra

Xét **5 đỉnh** `V={0,1,2,3,4}` và **7 cung**. Trọng số chỉ là dữ liệu minh họa:

| ID cung | Nguồn `u` | Đích `v` | Trọng số |
| --- | ---: | ---: | ---: |
| `e0` | 0 | 1 | 5 |
| `e1` | 0 | 3 | 2 |
| `e2` | 0 | 1 | 9 |
| `e3` | 2 | 1 | 7 |
| `e4` | 3 | 1 | 4 |
| `e5` | 3 | 4 | 6 |
| `e6` | 4 | 4 | 0 |

Trong đó:

- `e0` và `e2` là **hai cung song song** `0→1`, cần phân biệt bằng ID.
- `e6` là **cung khuyên** `4→4`, trọng số bằng 0 vẫn là cung có thật.
- Đỉnh `1` **không có cung ra**, dù có nhiều cung đi vào.

Nhóm bản ghi theo nguồn, giữ thứ tự ID trong mỗi nhóm:

```text
out[0] = [(1,e0,5), (3,e1,2), (1,e2,9)]
out[1] = []
out[2] = [(1,e3,7)]
out[3] = [(1,e4,4), (4,e5,6)]
out[4] = [(4,e6,0)]
```

CSR:

```text
u                  0     1     2     3     4
row_ptr         [  0,    3,    3,    4,    6,    7 ]
                 | 0 |    | 2 |   3    | 4 |

vị trí k           0   1   2   3   4   5   6
col_idx         [  1,  3,  1,  1,  1,  4,  4 ]
edge_id         [  0,  1,  2,  3,  4,  5,  6 ]
weight          [  5,  2,  9,  7,  4,  6,  0 ]
```

Ví dụ:

- `out[0]` nằm trong đoạn **`[row_ptr[0],row_ptr[1])=[0,3)`**, nên lấy `col_idx[0:3]=[1,3,1]`.
- `out[1]` nằm trong đoạn **`[3,3)`**, tức rỗng; nhưng đỉnh 1 vẫn tồn tại.
- `out[3]` là đoạn **`[4,6)`**, có hai cung tới đỉnh 1 và 4.
- `outdeg(u)=row_ptr[u+1]-row_ptr[u]` nên bậc ra lần lượt là **`[3,0,1,2,1]`**.

Tổng bậc ra là `3+0+1+2+1=7=m`. Nếu chỉ giữ một tập láng giềng `out[0]={1,3}`, ta sẽ **mất tính bội** của hai cung đến 1.

## 5. CSC: cùng cung nhưng nhóm theo cột đích

**CSC — Compressed Sparse Column** nhóm các mục theo **cột đích**. Mỗi đoạn giúp lấy nhanh **các nguồn của cung đi vào một đỉnh**.

| Mảng | Số phần tử | Vai trò |
| --- | ---: | --- |
| `col_ptr` | `n+1` | Ranh giới đoạn cung **đi vào** từng đỉnh |
| `row_idx` | `m` | **Nguồn** của các cung tương ứng |
| `weight` (*tùy chọn*) | `m` | Trọng số gắn với đúng cung tại vị trí đó |
| `edge_id` (*tùy chọn*) | `m` | Định danh cung để nhận diện và sửa/xóa |

Đoạn các cung vào đỉnh `v`:

\[
\operatorname{in}(v)=
\texttt{row\_idx[col\_ptr[v]:col\_ptr[v+1]]}.
\]

Nhóm bảng cung ở mục 4 theo **đích**:

```text
in[0] = []
in[1] = [(0,e0,5), (0,e2,9), (2,e3,7), (3,e4,4)]
in[2] = []
in[3] = [(0,e1,2)]
in[4] = [(3,e5,6), (4,e6,0)]
```

CSC tương ứng:

```text
v                  0     1     2     3     4
col_ptr         [  0,    0,    4,    4,    5,    7 ]

vị trí k           0   1   2   3   4   5   6
row_idx         [  0,  0,  2,  3,  0,  3,  4 ]
edge_id         [  0,  2,  3,  4,  1,  5,  6 ]
weight          [  5,  9,  7,  4,  2,  6,  0 ]
```

Với `v=1`, `col_ptr[1]=0` và `col_ptr[2]=4`: có **4 cung vào** từ các nguồn `[0,0,2,3]`. Hai số 0 được giữ vì `e0` và `e2` là hai cung khác nhau.

Với `v=4`, hai nguồn là `[3,4]`, trong đó `4→4` là khuyên. Dãy bậc vào là **`[0,4,0,1,2]`**, tổng bằng `7=m`.

**Lưu ý về thứ tự:** các mảng CSR và CSC không nhất thiết có `col_idx` hay `row_idx` được sắp tăng **trong từng đoạn**. Thứ tự phụ thuộc cách dựng; ví dụ CSR của đỉnh 0 là `[1,3,1]`, không tăng dần. Muốn tìm nhị phân, trước hết phải sắp xếp từng đoạn theo một quy tắc nhất quán và di chuyển đồng thời ID/trọng số tương ứng.

## 6. CSR, CSC và đồ thị đảo chiều không phải một khái niệm

Đặt `A[u,v]` là ô biểu diễn cung `u→v`. Khi đó:

- **CSR(A)** cho phép duyệt theo **hàng `u`**: cung **đi ra từ u**.
- **CSC(A)** cho phép duyệt theo **cột `v`**: cung **đi vào v**.
- Đồ thị đảo chiều `G^T` có ma trận logic **`A^T`**, trong đó cung `u→v` của G trở thành cung `v→u` của `G^T`.

Về mặt các mảng chỉ mục:

\[
\operatorname{CSC}(A)
\quad\text{có cùng cách nhóm chỉ số với}\quad
\operatorname{CSR}(A^T).
\]

Vì các cột của A là các hàng của `A^T`, khi dùng CSC(A) để duyệt cung vào `v`, ta đang duyệt **các cung đi ra từ v trong đồ thị đảo chiều**.

**Nhưng CSC(A) không làm phát sinh cung ngược trong G.** Nó chỉ là cách sắp xếp bản ghi của **các cung gốc** để truy vấn chiều đi vào nhanh. Một chiều `B→A` không được tự suy ra là quan hệ có thật trong hệ thống chỉ vì ta có CSC của cung `A→B`.

Nếu lưu đồng thời CSR(A) và CSC(A), ta có thể trả lời:

```text
outgoing(0)  -> CSR.row(0)      # 0 -> 1, 0 -> 3, 0 -> 1
incoming(1)  -> CSC.column(1)   # 0 -> 1 (2 lần), 2 -> 1, 3 -> 1
```

Hai danh sách có thể có **thứ tự ID khác nhau**; cần dựa trên `edge_id`, không dựa vào vị trí trong mảng để kết luận hai mục thuộc cùng một cung.

## 7. Bất biến của mảng nén

Một cài đặt đúng phải giữ các điều kiện sau:

### Bất biến offset

Đối với CSR:

\[
\texttt{len(row\_ptr)}=n+1,
\quad \texttt{row\_ptr[0]}=0,
\quad \texttt{row\_ptr[n]}=m,
\]

\[
0\le\texttt{row\_ptr[u]}\le
\texttt{row\_ptr[u+1]}\le m.
\]

CSC có bất biến tương tự với `col_ptr`. Các offset **không giảm**, nhưng có thể **bằng nhau** khi đỉnh không có cung đi ra/đi vào.

Nếu đồ thị **vô hướng** được lưu với hai mục có hướng cho mỗi cạnh không khuyên, số mục lưu trữ có thể là `q=2m`; khi đó offset cuối phải bằng **`q`**, không phải `m` cạnh toán học. Đối với đa đồ thị có hướng, `q=m` vì mỗi cung có một mục CSR.

### Bất biến dữ liệu song song

Với mỗi vị trí `k` hợp lệ:

- `col_idx[k]` (hoặc `row_idx[k]`) phải là chỉ số đỉnh hợp lệ.
- `edge_id[k]`, nếu có, phải chỉ đến đúng cung chứa tại vị trí đó.
- `weight[k]`, nếu có, phải là trọng số của **chính cung tại `k`**, không thể sắp xếp riêng trọng số mà bỏ nguyên chỉ số láng giềng.
- Một cung khuyên được lưu như một mục có nguồn bằng đích; trọng số 0 vẫn **chiếm vị trí trong mảng**.

Khi giữ **cả CSR lẫn CSC**, mỗi `edge_id` đang hoạt động phải được tìm thấy **đúng một lần trong mỗi chỉ mục** đối với đồ thị có hướng. Tổng bậc ra và tổng bậc vào đều bằng `m`.

Một cách tự kiểm tra cấu trúc là:

```text
row_ptr[0] == 0
row_ptr[n] == len(col_idx) == len(edge_id) == len(weight)
all(row_ptr[i] <= row_ptr[i+1] for i in range(n))
```

Trong thực tế, nếu không lưu `edge_id` hoặc `weight`, bỏ các kiểm tra tương ứng; không bắt buộc mọi đồ thị đều có đủ bốn mảng.

## 8. Xây dựng CSR và CSC từ danh sách cung trong O(n+m)

Có hai hướng dựng phổ biến.

**Cách đơn giản:** tạo `n` nhóm tạm theo nguồn (cho CSR) hoặc theo đích (cho CSC), duyệt mọi cung và thêm bản ghi vào nhóm, rồi nối các nhóm thành mảng nén. Thời gian và bộ nhớ phụ là `O(n+m)`; chi phí hằng số có thể tăng do nhiều danh sách nhỏ.

**Cách đếm và rải vào vị trí (count + prefix sum + scatter)** tránh phải giữ `n` list chứa từng nhóm trong quá trình dựng:

1. Khởi tạo `count[0..n-1]=0`.
2. Duyệt `m` cung, tăng `count[u]` theo nguồn để dựng CSR (hoặc `count[v]` theo đích để dựng CSC).
3. Tính **tổng tiền tố** để có `ptr[0]=0`, `ptr[i+1]=ptr[i]+count[i]`.
4. Dùng con trỏ ghi tạm `next[i]=ptr[i]`. Duyệt lại các cung, đặt `neighbor`, `edge_id`, `weight` tại `next[i]`, rồi tăng `next[i]`.

Thời gian:

\[
T_{\mathrm{build}}=\Theta(n+m)
\]

khi mỗi bản ghi được xử lý bằng các thao tác hằng số và các chỉ số đỉnh đã được ánh xạ sang số nguyên. Các mảng kết quả dùng `\Theta(n+m)` phần tử; nếu cần sắp xếp đích **trong từng hàng**, ta phải cộng thêm chi phí sắp xếp.

Với đa đồ thị, thuật toán này **không khử trùng đầu mút**: các cung song song vẫn tạo những vị trí khác nhau. Muốn giữ ID cung và trọng số, cần rải **tất cả mảng song song theo cùng một vị trí**.

### Python: dựng cả hai cấu trúc

Đoạn mã sau dùng đúng dữ liệu 5 đỉnh, 7 cung ở mục 4. Cả khuyên lẫn cung song song đều được giữ; `edge_id` là số nguyên không thay đổi. Hàm dùng **hai lượt duyệt dữ liệu** và không sắp xếp thêm bên trong các nhóm.

```python
def nen_cung(n, edges, theo_nguon=True):
    # Mỗi bản ghi: (edge_id, source, target, weight).
    # CSR khi theo_nguon=True; CSC khi theo_nguon=False.
    if n < 0:
        raise ValueError("Số đỉnh không thể âm")

    counts = [0] * n
    for eid, u, v, w in edges:
        if (not isinstance(u, int) or not isinstance(v, int)
                or not (0 <= u < n and 0 <= v < n)):
            raise ValueError("Chỉ số đầu mút không hợp lệ")
        key = u if theo_nguon else v
        counts[key] += 1

    ptr = [0]
    for count in counts:
        ptr.append(ptr[-1] + count)

    next_pos = ptr[:-1].copy()
    other = [None] * len(edges)
    ids = [None] * len(edges)
    weights = [None] * len(edges)

    for eid, u, v, w in edges:
        key = u if theo_nguon else v
        k = next_pos[key]
        next_pos[key] += 1
        other[k] = v if theo_nguon else u
        ids[k] = eid
        weights[k] = w

    return ptr, other, ids, weights


def cac_muc_cua_dinh(dinh, compressed):
    ptr, other, ids, weights = compressed
    if not 0 <= dinh < len(ptr) - 1:
        raise IndexError(dinh)
    for k in range(ptr[dinh], ptr[dinh + 1]):
        yield other[k], ids[k], weights[k]


edges = [
    (0, 0, 1, 5),  # e0: 0 -> 1
    (1, 0, 3, 2),  # e1: 0 -> 3
    (2, 0, 1, 9),  # e2: 0 -> 1, song song e0
    (3, 2, 1, 7),  # e3: 2 -> 1
    (4, 3, 1, 4),  # e4: 3 -> 1
    (5, 3, 4, 6),  # e5: 3 -> 4
    (6, 4, 4, 0),  # e6: 4 -> 4, khuyên có trọng số 0
]

csr = nen_cung(5, edges, theo_nguon=True)
csc = nen_cung(5, edges, theo_nguon=False)

print(csr[0])  # [0, 3, 3, 4, 6, 7]
print(csr[1])  # [1, 3, 1, 1, 1, 4, 4]
print(csr[2])  # [0, 1, 2, 3, 4, 5, 6]
print(csr[3])  # [5, 2, 9, 7, 4, 6, 0]

print(csc[0])  # [0, 0, 4, 4, 5, 7]
print(csc[1])  # [0, 0, 2, 3, 0, 3, 4]
print(csc[2])  # [0, 2, 3, 4, 1, 5, 6]
print(csc[3])  # [5, 9, 7, 4, 2, 6, 0]

print(list(cac_muc_cua_dinh(0, csr)))
# [(1, 0, 5), (3, 1, 2), (1, 2, 9)] : cung đi ra

print(list(cac_muc_cua_dinh(1, csc)))
# [(0, 0, 5), (0, 2, 9), (2, 3, 7), (3, 4, 4)] : cung đi vào

print(list(cac_muc_cua_dinh(4, csc)))
# [(3, 5, 6), (4, 6, 0)] : gồm cung khuyên

print([csr[0][u+1] - csr[0][u] for u in range(5)])
# [3, 0, 1, 2, 1] : bậc ra
print([csc[0][v+1] - csc[0][v] for v in range(5)])
# [0, 4, 0, 1, 2] : bậc vào
```

**Ghi chú về ví dụ:** `edges` ở đây là **list có thể duyệt lại** và `len(edges)` cho biết số cung. Nếu nguồn dữ liệu là iterator chỉ dùng một lần, phải lưu lại các bản ghi hoặc dùng cách dựng phù hợp trước khi thực hiện hai lượt. Trong chương trình sản xuất, các mảng thường dùng kiểu số nguyên/số thực có kích thước cố định, thay vì Python list chứa tham chiếu đối tượng.

## 9. Chi phí tra cứu và duyệt sau khi đã nén

Giả sử `ptr`, `neighbor` và các mảng đi kèm đã tồn tại, đỉnh được biểu diễn bằng chỉ số nguyên:

| Thao tác | CSR | CSC |
| --- | --- | --- |
| Lấy **bậc ra** `u` | `O(1)` từ hiệu hai `row_ptr` | Cần chỉ mục/bộ đếm phụ hoặc quét các cột |
| Lấy **bậc vào** `v` | Cần chỉ mục/bộ đếm phụ hoặc quét các hàng | `O(1)` từ hiệu hai `col_ptr` |
| Liệt kê các cung **đi ra** từ `u` | `\Theta(outdeg(u))` | Nếu chỉ có CSC, quét tới `O(n+m)` |
| Liệt kê các cung **đi vào** `v` | Nếu chỉ có CSR, quét tới `O(n+m)` | `\Theta(indeg(v))` |
| Kiểm tra **có ít nhất một cung** `u→v` | `O(outdeg(u))` nếu đoạn chưa sắp | `O(indeg(v))` nếu đoạn chưa sắp |
| Kiểm tra khi đoạn đã **sắp theo ID láng giềng** | `O(\log(outdeg(u)+1))` | `O(\log(indeg(v)+1))` |
| Quét toàn bộ cung | `O(n+m)` nếu đi qua từng đoạn | `O(n+m)` nếu đi qua từng đoạn |
| BFS/DFS toàn đồ thị theo chiều cung gốc | `O(n+m)` | Nếu chỉ có CSC, thích hợp với **duyệt ngược** hơn |

**Tìm cung cụ thể theo ID:** nếu có `edge_id` song song nhưng **không** có bảng ánh xạ `ID → vị trí`, ta vẫn có thể phải quét để tìm vị trí của một cung. Có bảng chỉ mục ID có thể giúp tìm nhanh theo kỳ vọng, nhưng duy trì chỉ mục đó khi **dịch chuyển mảng** cũng phát sinh chi phí.

**Số phần tử được xuất:** truy vấn liệt kê `k` cung không thể có thời gian tốt hơn `\Omega(k)` nếu phải thực sự trả đủ `k` bản ghi. Lợi ích của CSR/CSC là tránh quét những cung **không liên quan** tới đỉnh đang hỏi.

## 10. Bộ nhớ: O(n+m) nhưng kích thước ô vẫn quan trọng

Với đồ thị có hướng có `m` cung, một CSR cơ bản có `n+1` offset và `m` chỉ số đích:

\[
S_{\mathrm{CSR}}=\Theta(n+m).
\]

CSC có bậc tương tự. Nếu lưu đồng thời hai chỉ mục, số phần tử tăng xấp xỉ gấp đôi ở phần offset và chỉ số láng giềng, nhưng vẫn là **`\Theta(n+m)`** về bậc tăng trưởng.

Để ước tính **byte thực**, xét một ví dụ:

- `n=1.000.000` đỉnh và `m=5.000.000` cung.
- Mỗi offset dùng **8 byte**, mỗi chỉ số láng giềng **4 byte**, mỗi trọng số **8 byte**.
- Một CSR chỉ gồm `ptr + neighbor + weight` cần xấp xỉ:

\[
(n+1)\cdot8+m\cdot(4+8)
\approx 8\text{ MB}+60\text{ MB}=68\text{ MB}.
\]

Đây là **MB thập phân** và chỉ đếm các mảng dữ liệu thô: chưa tính ID cung, bảng ánh xạ đỉnh, dung lượng dự phòng, metadata hay chi phí của đối tượng Python. Thêm mảng `edge_id` 8 byte cho mỗi cung sẽ thêm khoảng **40 MB** nữa theo giả định này.

Nếu cả CSR và CSC đều lưu **bản sao trọng số và ID**, bộ nhớ tăng đáng kể. Một cách khác là lưu **bảng cung theo ID làm nguồn dữ liệu chuẩn** và để CSR/CSC chỉ giữ **ID liên kết hoặc chỉ số tham chiếu**, đổi lại truy cập trọng số cần thêm một lần gián tiếp.

So với **ma trận kề đặc `n²` ô**, CSR/CSC đặc biệt hữu ích khi `m\ll n²`. Tuy nhiên, với đồ thị rất dày, một **bitset ma trận** hoặc cách lưu đặc khác có thể có lợi thế hằng số hoặc truy vấn theo cặp; nên đo bộ nhớ và thời gian theo workload thực tế.

## 11. Vì sao cập nhật một cung có thể tốn O(n+m)?

Giả sử CSR đang lưu tất cả cung theo từng hàng, **không có chỗ trống** giữa các đoạn.

```text
row_ptr = [0, 3, 3, 4, 6, 7]
col_idx = [1, 3, 1, 1, 1, 4, 4]
```

Giờ thêm cung mới `1→4`. Hàng `1` vốn là đoạn rỗng `[3,3)`; muốn đặt đích 4 vào đoạn đúng hàng trong mảng liên tiếp:

1. **Chèn `4` tại vị trí `3`** của `col_idx`, khiến nhiều phần tử sau vị trí này phải dịch sang phải.
2. Cùng chèn các giá trị tương ứng vào `edge_id`, `weight` nếu có.
3. Tăng tất cả offset **`row_ptr[2]`, `row_ptr[3]`, ... , `row_ptr[n]`** thêm 1, vì các đoạn từ hàng 2 trở đi đã dịch chuyển.

Sau cập nhật, riêng hai mảng cơ bản trở thành:

```text
row_ptr = [0, 3, 4, 5, 7, 8]
col_idx = [1, 3, 1, 4, 1, 1, 4, 4]
```

Một phần tử mới có thể làm **`O(m)` mục dữ liệu** phải dịch chuyển và **`O(n)` offset** phải sửa:

\[
T_{\mathrm{insert\ packed}}=O(n+m)
\]

trong trường hợp xấu của **biểu diễn mảng nén đặc, cập nhật trực tiếp**. Xóa một cung ở giữa cũng có vấn đề tương tự: dịch mảng sang trái và giảm các offset liên quan.

**Không nên phát biểu rằng mọi lần thêm cung đều bắt buộc tốn đúng `\Theta(n+m)`.** Nếu thêm vào đúng cuối mảng, có chỗ dự phòng hay dùng cách quản lý offset khác, một lần cập nhật có thể rẻ hơn. Cận trên ở đây nêu **trường hợp xấu điển hình** của thiết kế packed CSR/CSC truyền thống.

Với **CSC**, việc chèn `u→v` cũng phải đặt một mục vào đoạn **cột v** và có thể cập nhật nhiều `col_ptr`. Nếu lưu **cả CSR và CSC**, phải bảo đảm cả hai chỉ mục đồng bộ; thêm một cung mới có thể tác động hai vùng mảng hoàn toàn khác nhau.

## 12. Những chiến lược khi đồ thị thay đổi thường xuyên

### 12.1. Xây dựng một lần rồi chỉ đọc

Nếu dữ liệu được nạp một lần và sau đó truy vấn rất nhiều, CSR/CSC đặc biệt phù hợp: trả chi phí dựng `O(n+m)` một lần (hoặc thêm sắp xếp nếu cần), rồi tận dụng các mảng nén để duyệt liên tục.

Ví dụ: đồ thị phụ thuộc học phần được tính cho một phiên bản chương trình đào tạo; mỗi phiên bản mới tạo một snapshot nén riêng.

### 12.2. Gom cập nhật thành lô rồi dựng lại

Thay vì chèn vào mảng nén ngay sau mỗi thay đổi, có thể giữ các thao tác thêm/xóa trong một **bộ đệm cập nhật**. Sau một lô, hợp nhất chúng với dữ liệu gốc và dựng lại CSR/CSC.

Nếu trạng thái sau hợp nhất có `m'` cung, chi phí một lần dựng lại thường là `O(n+m')` khi dữ liệu đầu vào đã được chuẩn bị phù hợp. Khi tính **toàn bộ quy trình**, phải kể cả chi phí đọc dữ liệu cũ, xử lý các bản ghi thay đổi và kiểm tra trùng/ID nếu cần; không được khẳng định vô điều kiện “mỗi lần cập nhật có chi phí khấu hao O(1)”.

Ưu điểm là tránh liên tục dịch chuyển các mảng lớn; nhược điểm là có độ trễ trước khi snapshot mới được công bố.

### 12.3. Base CSR + delta và dấu xóa

Một thiết kế thường gặp:

```text
base_CSR : dữ liệu nén ổn định
delta    : tập cung thêm mới hoặc trọng số cập nhật
deleted  : tập edge_id đã bị xóa (tombstone)
```

Khi truy vấn cung đi ra từ `u`, ứng dụng phải **gộp đúng** cung trong `base_CSR` với thay đổi trong `delta`, đồng thời **bỏ qua** ID trong `deleted`. Với **cung song song**, không được chỉ gộp theo cặp `(u,v)`; phải giữ ID từng cung. Với **cập nhật trọng số**, phải có quy tắc phiên bản mới ghi đè bản cũ theo cùng `edge_id`.

Cách này có thể làm một lần thêm/xóa **nhanh hơn việc dịch toàn bộ mảng** nếu bộ đệm dùng cấu trúc phù hợp, nhưng:

- Truy vấn có thể tốn thêm công kiểm tra delta/tombstone.
- Số bậc và số cung phải phản ánh **các thay đổi chưa nén**, không chỉ lấy hiệu offset của bản cũ.
- Bộ đệm và dấu xóa có thể lớn dần, nên cần **compact/rebuild** định kỳ.
- Nếu có truy cập đồng thời, một lần đọc phải thấy **cùng một phiên bản logic** của snapshot và delta; không thể đọc CSR cũ rồi delta mới một cách tùy tiện.

### 12.4. Dùng cấu trúc động làm bản chuẩn

Khi mỗi giây có nhiều thêm/xóa cạnh hoặc đỉnh, một **danh sách kề dạng list/set/map**, cộng chỉ mục cung đi vào nếu cần, có thể đơn giản và hiệu quả hơn. Sau đó mới **xuất CSR/CSC** cho các tác vụ phân tích hoặc chạy trên phần cứng/tư liệu cần mảng liên tục.

**Cập nhật trọng số khác cập nhật cấu trúc:** nếu biết vị trí phần tử trong mảng `weight`, việc sửa **một trọng số tại chỗ** có thể là `O(1)` khi không thay số cung hoặc thứ tự. Nhưng tìm vị trí từ `edge_id` có thể tốn `O(m)` nếu chưa có chỉ mục, và nếu lưu cả CSR/CSC với hai bản sao trọng số phải sửa cả hai.

## 13. Lựa chọn CSR, CSC, cả hai hay biểu diễn khác

| Nhu cầu chính | Lựa chọn đáng cân nhắc | Lý do |
| --- | --- | --- |
| Thường duyệt cung **đi ra** và BFS/DFS theo chiều gốc | **CSR** | Lấy đoạn theo nguồn bằng hai offset |
| Thường hỏi **ai có cung tới đỉnh v** hoặc duyệt ngược | **CSC** | Lấy đoạn theo đích bằng hai offset |
| Cần truy vấn cả cung **đi ra và đi vào** | **CSR + CSC** | Hai chỉ mục nhanh hơn quét toàn bộ mỗi lần |
| Đồ thị lớn, **ít thay đổi**, chạy phân tích lặp lại | **CSR/CSC** | Mảng gọn, duyệt tuần tự có locality tốt |
| Đồ thị cập nhật cạnh/đỉnh liên tục | **Danh sách kề động** hoặc **base + delta** | Tránh chèn/xóa giữa mảng nén sau mỗi thao tác |
| Chủ yếu nhập/xuất, sắp xếp hoặc lọc mọi cung | **Danh sách cạnh (edge list)** | Mỗi cung một bản ghi dễ quản lý |
| Đồ thị rất dày, cần hỏi một cặp đỉnh có nối không | **Ma trận kề/bitset** | Truy cập ô trực tiếp `O(1)` theo chỉ số |

**Khi là đồ thị vô hướng:** CSR lưu hai mục đối ứng cho mỗi cạnh `{u,v}` với `u\ne v`; về mặt ma trận, `A=A^T`, nên CSC có thể không bổ sung thông tin kề mới. Nhưng số ID/trọng số, cách lưu khuyên và tính bội vẫn phải được quy định rõ; không suy ra hai bản sao chỉ mục là **hai cạnh khác nhau**.

**Khi là đồ thị có trọng số:** lưu mảng `weight` song song với chỉ số, hoặc lưu `edge_id` trỏ tới bảng trọng số chuẩn. Trọng số 0 không làm cung “biến mất” khỏi CSR/CSC.

**Khi có đỉnh cô lập:** CSR và CSC vẫn cần đủ `n+1` offset. Một đỉnh không có cung ra có đoạn CSR rỗng; một đỉnh không có cung vào có đoạn CSC rỗng. Hai tính chất đó không đồng nghĩa với nhau.

## 14. Những sai lầm thường gặp

1. **Nhầm `row_ptr` với danh sách đỉnh đích.** Offset chỉ là ranh giới đoạn; đích nằm trong `col_idx`.
2. **Quên phần tử offset cuối.** Phải có `n+1` giá trị, phần tử cuối bằng số mục thực được nén.
3. **Loại đỉnh không có cung khỏi offset.** Đoạn rỗng cần hai offset liên tiếp bằng nhau để giữ đúng định danh đỉnh.
4. **Cho rằng CSR tự tìm cung đi vào nhanh.** Nếu chỉ có CSR, truy vấn đi vào có thể phải quét toàn bộ; CSC mới nhóm theo đích.
5. **Nhầm CSC với việc thêm cung ngược vào đồ thị gốc.** CSC là chỉ mục của những cung đã có.
6. **Giả định phần láng giềng của mỗi đỉnh luôn được sắp xếp.** Nén không tự đồng nghĩa với sắp thứ tự trong đoạn.
7. **Sắp xếp `col_idx` mà không hoán vị `edge_id` và `weight`.** Làm lệch thuộc tính khỏi cung.
8. **Dùng một khóa cặp đầu mút để gộp cung song song.** Làm mất ID và trọng số của từng cung.
9. **Xem trọng số 0 như không có cung.** Sự hiện diện được xác định bởi vị trí/ID của mục nén, không phải giá trị trọng số.
10. **Nói chèn một cung vào CSR luôn O(1) vì mảng hỗ trợ truy cập theo chỉ số.** Chèn giữa mảng nén có thể phải dời nhiều mục và sửa nhiều offset.
11. **Xóa cung trong CSR nhưng quên cập nhật CSC.** Hai chỉ mục trả lời khác nhau cho cùng một đồ thị.
12. **Giữ snapshot cũ nhưng lấy bậc từ offset khi đã có delta cập nhật.** Bậc cần tính từ **trạng thái logic hiện hành**, không chỉ dữ liệu nền.
13. **Tưởng `O(n+m)` bộ nhớ là số byte cố định.** Kích thước chỉ số, trọng số, ID và overhead quyết định dung lượng thực.
14. **Đổi ID đỉnh mà không cập nhật mapping.** Mảng nén dựa trên chỉ số nguyên; đổi ánh xạ ID không nhất quán sẽ làm các cung nối sai đỉnh.

## 15. Tự kiểm tra

**Câu 1.** Với CSR có `row_ptr=[0,2,2,5]`, đồ thị có bao nhiêu đỉnh? Mỗi đỉnh có bao nhiêu mục cung đi ra?

**Đáp án:** Có `n=3` đỉnh vì `len(row_ptr)=4=n+1`. Bậc ra lần lượt là `[2,0,3]` và tổng có 5 mục.

**Câu 2.** Trong ví dụ bảy cung của bài, `row_ptr=[0,3,3,4,6,7]`. Vì sao hai phần tử `row_ptr[1]` và `row_ptr[2]` bằng nhau?

**Đáp án:** Vì đỉnh 1 không có cung đi ra; đoạn của nó là `[3,3)` rỗng. Đỉnh 1 vẫn thuộc `V`.

**Câu 3.** CSC ở mục 5 có `col_ptr=[0,0,4,4,5,7]`. Có bao nhiêu cung đi vào đỉnh 1 và chúng xuất phát từ đâu?

**Đáp án:** Có `col_ptr[2]-col_ptr[1]=4` cung đi vào, từ các nguồn `[0,0,2,3]`. Nguồn 0 xuất hiện hai lần vì có hai cung song song khác ID.

**Câu 4.** Nếu `edge_id=[0,1,2]` và `weight=[5,7,9]` là hai mảng song song, việc chỉ đổi vị trí `edge_id[0]` và `edge_id[2]` có an toàn không?

**Đáp án:** Không, trừ khi hoán vị đồng thời các mảng chỉ số và trọng số của chính những cung đó. Nếu không, ID, đầu mút và trọng số sẽ bị gán nhầm.

**Câu 5.** Đồ thị có hướng có `n` đỉnh, `m` cung. Bộ nhớ của CSR và chi phí dựng CSR theo thuật toán đếm–tiền tố–rải là bao nhiêu?

**Đáp án:** Cả hai có bậc **`\Theta(n+m)`**, giả sử mỗi mục được xử lý và lưu bằng số lượng thông tin hằng số.

**Câu 6.** Tại sao kiểm tra `u→v` trong CSR chưa sắp xếp không nhất thiết là `O(1)`?

**Đáp án:** Hai offset chỉ xác định đoạn cung đi ra của `u`; phải tìm `v` trong đoạn đó, có thể quét `O(outdeg(u))` mục. Nếu đoạn đã sắp theo đích, có thể dùng tìm nhị phân.

**Câu 7.** Thêm `1→4` vào CSR ở mục 4 làm `row_ptr` mới bằng gì?

**Đáp án:** `[0,3,4,5,7,8]`. Các offset từ `row_ptr[2]` trở đi tăng 1 vì hàng 1 nhận thêm một mục tại vị trí 3.

**Câu 8.** Vì sao xóa một cung theo ID trong CSR/CSC packed có thể tốn `O(n+m)` trường hợp xấu dù ta đã biết ID?

**Đáp án:** Tìm vị trí theo ID chỉ là một phần; còn phải dịch các mục phía sau trong mảng và sửa các offset của những hàng/cột bị ảnh hưởng, cũng như các chỉ mục song song.

**Câu 9.** CSR(A) và CSC(A) khác đồ thị đảo chiều `G^T` như thế nào?

**Đáp án:** CSR(A) nhóm cung theo nguồn; CSC(A) nhóm **cùng cung** theo đích. `G^T` là đồ thị toán học mới với mọi cung đảo hướng; CSC(A) có cách nhóm chỉ số tương đương CSR(`A^T`) nhưng không thêm cung ngược vào G.

**Câu 10.** Đồ thị được cập nhật hàng nghìn lần mỗi phút, nhưng công việc phân tích chỉ chạy định kỳ. Có nên sửa mảng CSR packed ngay sau từng cập nhật không?

**Đáp án:** Không nhất thiết. Có thể giữ bản chuẩn dạng cấu trúc động hoặc bộ đệm delta, sau đó dựng lại snapshot CSR/CSC theo lô. Phải xử lý đúng cung xóa, ID cung song song, trọng số và tính nhất quán giữa các phiên bản.

**Câu 11.** Một cung `4→4` có trọng số `0` sẽ làm tăng bậc như thế nào và có bị bỏ khỏi mảng nén không?

**Đáp án:** Nó là một cung khuyên có thật, đóng góp **1 vào bậc ra** và **1 vào bậc vào** của đỉnh 4; nó vẫn chiếm một vị trí trong CSR và một vị trí trong CSC nếu lưu cả hai.

**Ghi nhớ:** **CSR** nhóm cung theo **nguồn** bằng `row_ptr` và `col_idx`; **CSC** nhóm cung theo **đích** bằng `col_ptr` và `row_idx`. Mỗi đoạn nằm giữa hai offset liên tiếp, đỉnh không có liên kết tương ứng có đoạn rỗng; mảng `edge_id` và `weight` phải luôn được căn chỉnh với các mục liên kết. Hai biểu diễn đều dùng **`\Theta(n+m)` bộ nhớ**, hỗ trợ truy vấn cung ra/vào và duyệt theo số mục cần thiết, nhưng **chèn/xóa trực tiếp trên mảng nén** có thể tốn **`O(n+m)` trường hợp xấu**. Chọn CSR, CSC, hai chỉ mục hoặc cấu trúc động theo **hướng truy vấn, mật độ, tần suất cập nhật và yêu cầu nhất quán dữ liệu**.

# Mảng răng cưa và biểu diễn nhiều chiều không đều

## 1. Khi các hàng không có cùng số phần tử

Mảng hai chiều thông thường thường được mô tả bằng hình chữ nhật `R × C`: có `R` hàng, mỗi hàng đúng `C` phần tử. Tuy nhiên, nhiều bài toán thực tế chứa các nhóm có số lượng phần tử khác nhau:

- Mỗi lớp có số học sinh khác nhau.
- Mỗi ngày có số giao dịch khác nhau, kể cả ngày không có giao dịch nào.
- Mỗi đỉnh trong đồ thị có số đỉnh kề khác nhau.
- Mỗi câu trong một văn bản có số từ khác nhau.

Ví dụ, số đơn hàng của bốn cửa hàng trong một ngày được lưu dưới dạng các mã đơn hàng:

```text
Hàng / Cửa hàng 0:  [12, 18, 21]     3 phần tử
Hàng / Cửa hàng 1:  []               0 phần tử
Hàng / Cửa hàng 2:  [7, 9]           2 phần tử
Hàng / Cửa hàng 3:  [25]             1 phần tử
```

Dữ liệu này tạo thành **mảng răng cưa** (*jagged array* hoặc *ragged array*): mỗi hàng có thể có độ dài khác nhau. Ta vẫn dùng cách viết `A[i][j]` để chọn phần tử thứ `j` của hàng `i`, nhưng **miền chỉ số cột phụ thuộc vào hàng đang chọn**.

Sau bài học, bạn có thể mô hình hóa mảng răng cưa, kiểm tra chỉ số an toàn, phân biệt cách lưu bằng các mảng con với cách lưu phẳng có offset, phân tích chi phí truy cập và cập nhật, đồng thời lựa chọn biểu diễn phù hợp với bài toán. Đây là một chủ đề của chương **Mảng** trong học phần **Cấu trúc dữ liệu**, nơi ta dựa vào bất biến và độ phức tạp thời gian, bộ nhớ để so sánh các cấu trúc như mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị.

## 2. Mô hình chỉ số: mỗi hàng có độ dài riêng

Giả sử có `m` hàng, hàng `i` chứa `L_i` phần tử. Với ví dụ trên:

```text
A = [
    [12, 18, 21],  # L[0] = 3
    [],            # L[1] = 0
    [7, 9],        # L[2] = 2
    [25],          # L[3] = 1
]

Số hàng m = 4
Độ dài từng hàng L = [3, 0, 2, 1]
Tổng số phần tử N = 3 + 0 + 2 + 1 = 6
```

Chỉ số hợp lệ phải thỏa **đồng thời hai điều kiện**:

\[
0\le i<m,\qquad 0\le j<L_i
\]

Ta có thể biểu diễn miền chỉ số của mảng răng cưa như sau:

\[
D=\{(i,j)\mid 0\le i<m,\ 0\le j<L_i\}
\]

Mảng là một ánh xạ `A:D\rightarrow T` từ mỗi cặp chỉ số hợp lệ đến giá trị tương ứng. Tổng số phần tử là:

\[
\boxed{N=\sum_{i=0}^{m-1}L_i}
\]

Với ví dụ đã cho:

| Truy cập | Hợp lệ? | Giải thích |
|---|---|---|
| `A[0][2]` | Có, nhận `21` | Hàng `0` có chỉ số cột `0, 1, 2` |
| `A[1][0]` | Không | Hàng `1` rỗng |
| `A[2][1]` | Có, nhận `9` | Hàng `2` có hai phần tử |
| `A[2][2]` | Không | `2 == L_2` nên vượt giới hạn |
| `A[3][0]` | Có, nhận `25` | Hàng `3` có một phần tử |
| `A[4][0]` | Không | Không tồn tại hàng `4` |

**Bất biến quan trọng:** mọi hàng có độ dài không âm; với một truy cập `A[i][j]`, phải kiểm tra `i` trước khi lấy `L_i`, rồi mới kiểm tra `j`. Kiểm tra `0 <= j < max(L)` là sai vì hàng hiện tại có thể ngắn hơn hàng dài nhất.

### Phân biệt số hàng, số cột và tổng số phần tử

Một mảng chữ nhật có hình dạng `(R, C)`, nên tổng số ô là `R×C`. Mảng răng cưa có `m` hàng nhưng **không có một giá trị số cột chung**; cách mô tả thích hợp là `m` kèm vector độ dài `(L_0,\ldots,L_{m-1})`.

Nếu mọi `L_i` tình cờ bằng nhau, cấu trúc có hình dạng chữ nhật về mặt dữ liệu, dù vẫn có thể được triển khai bằng các hàng cấp phát riêng. Ngược lại, việc dùng cú pháp hai chỉ số không chứng minh rằng bộ nhớ là một khối ma trận liên tiếp.

## 3. Biểu diễn bằng danh sách các hàng riêng biệt

Cách trực quan nhất là lưu một mảng bên ngoài chứa tham chiếu tới các mảng con. Mỗi hàng quản lý độ dài riêng:

```text
Mảng ngoài A (m = 4):
       +-----+-----+-----+-----+
       | ref | ref | ref | ref |
       +--|--+--|--+--|--+--|--+
          |     |     |     |
          v     v     v     v
       [12,18,21]  []   [7,9]   [25]
```

Các mảng con có thể được cấp phát ở những vùng nhớ khác nhau. Việc truy cập `A[i][j]` thường diễn ra qua hai bước: chọn tham chiếu đến hàng `i`, rồi truy cập ô `j` trong hàng đó. Nếu cả hai cấp hỗ trợ truy cập theo chỉ số, đây vẫn thường là **`O(1)` thời gian** khi biết chỉ số hợp lệ.

### Ví dụ Python

```python
orders = [
    [12, 18, 21],
    [],
    [7, 9],
    [25],
]

print(len(orders))        # 4 hàng
print([len(row) for row in orders])  # [3, 0, 2, 1]
print(sum(map(len, orders)))         # 6 phần tử
print(orders[2][1])      # 9

# Duyệt mọi phần tử, kể cả khi có hàng rỗng.
for i, row in enumerate(orders):
    for j, value in enumerate(row):
        print(i, j, value)
```

Vòng lặp trong chỉ chạy đúng `L_i` lần cho hàng `i`. Vì vậy tổng số lần đọc giá trị là `N`; nếu tính cả việc duyệt qua `m` hàng (gồm những hàng rỗng), thời gian duyệt toàn bộ là **`O(m+N)`**.

Trong Python, `list` bên ngoài và mỗi `list` hàng là các đối tượng riêng. Các `list` lưu tham chiếu đến đối tượng Python; bản thân các giá trị số nguyên không nhất thiết nằm liên tiếp trong một khối nhớ hai chiều. Tương tự, `int[][]` trong Java thường là mảng ngoài chứa tham chiếu đến các mảng `int[]`, và các hàng có thể dài khác nhau.

### Hàm đọc an toàn với quy ước chỉ số không âm

Python chấp nhận chỉ số âm như `row[-1]` để đọc phần tử cuối. Trong các thuật toán dùng miền `0..L_i-1`, ta nên kiểm tra giới hạn rõ ràng:

```python
def read_ragged(rows: list[list[int]], i: int, j: int) -> int:
    if not 0 <= i < len(rows):
        raise IndexError("Chỉ số hàng không hợp lệ")
    if not 0 <= j < len(rows[i]):
        raise IndexError("Chỉ số cột không hợp lệ ở hàng đã chọn")
    return rows[i][j]


print(read_ragged(orders, 0, 2))  # 21
print(read_ragged(orders, 3, 0))  # 25
# read_ragged(orders, 1, 0) -> IndexError: hàng rỗng
```

Nếu `rows=[]` thì `m=0` và không có hàng hợp lệ. Nếu `rows=[[]]` thì có **một hàng rỗng** nhưng vẫn không có phần tử; hai trường hợp khác nhau về cấu trúc dù cùng có `N=0`.

## 4. Vì sao không thể dùng trực tiếp công thức hàng nhân số cột?

Với ma trận chữ nhật có `C` cột và lưu liên tiếp theo hàng, vị trí phẳng của `(i,j)` là:

\[
\operatorname{index}(i,j)=iC+j
\]

Công thức này dựa vào giả định **mọi hàng đứng trước đều chứa đúng `C` phần tử**. Trong mảng răng cưa, độ dài từng hàng khác nhau, nên không thể thay `C` bằng một hằng số duy nhất.

Ở ví dụ:

```text
Hàng 0: [12, 18, 21] -> 3 phần tử
Hàng 1: []           -> 0 phần tử
Hàng 2: [7, 9]       -> 2 phần tử
Hàng 3: [25]         -> 1 phần tử

Dữ liệu trải phẳng: [12, 18, 21, 7, 9, 25]
Chỉ số phẳng:         0   1   2  3  4   5
```

Phần tử `A[2][1] = 9` nằm ở chỉ số phẳng `4`. Nếu sai lầm dùng số cột dài nhất `C=3`, ta sẽ tính `2×3+1=7`, vượt cả kích thước bộ đệm sáu phần tử.

Cách sửa là lưu hoặc tính **tổng số phần tử của các hàng trước**. Đây chính là ý tưởng của *mảng offset* và *tổng tiền tố*.

## 5. Trải phẳng với mảng offset của từng hàng

Ta muốn lưu mọi giá trị vào **một bộ đệm phẳng liên tiếp** `data` nhưng vẫn biết mỗi hàng bắt đầu và kết thúc ở đâu. Đặt `offsets` có `m+1` phần tử:

\[
offsets[0]=0,\qquad
offsets[i+1]=offsets[i]+L_i
\]

Vì vậy:

\[
\boxed{offsets[i]=\sum_{k=0}^{i-1}L_k}
\]

Mảng offset của ví dụ là:

```text
L        = [3, 0, 2, 1]
offsets  = [0, 3, 3, 5, 6]
data     = [12, 18, 21, 7, 9, 25]
            0   1   2  3  4   5

Hàng 0 -> data[0:3] = [12, 18, 21]
Hàng 1 -> data[3:3] = []
Hàng 2 -> data[3:5] = [7, 9]
Hàng 3 -> data[5:6] = [25]
```

Các bất biến phải luôn đúng:

\[
0=offsets[0]\le offsets[1]\le\cdots\le offsets[m]=N
\]

\[
\boxed{L_i=offsets[i+1]-offsets[i]}
\]

Hàng rỗng tương ứng với **hai offset liên tiếp bằng nhau**. Trong ví dụ `offsets[1]=offsets[2]=3`, nên hàng `1` không chiếm ô nào trong `data`. Mảng vẫn biểu diễn được hàng rỗng mà không cần thêm giá trị giả.

Một phần tử ở tọa độ `(i,j)`, với `0<=j<L_i`, có chỉ số phẳng:

\[
\boxed{k=offsets[i]+j}
\]

Do đó `A[2][1]` tương ứng `k=offsets[2]+1=3+1=4` và `data[4]=9`.

Nếu mọi phần tử có kích thước cố định `s` byte, `data` thực sự là một bộ đệm các ô liên tiếp và địa chỉ ô đầu là `base`, thì:

\[
\operatorname{addr}(A[i][j])=base+(offsets[i]+j)\times s
\]

Công thức địa chỉ byte này áp dụng cho **bộ đệm lưu giá trị trực tiếp** hoặc các ô tham chiếu liên tiếp có kích thước cố định; với Python `list`, phép tính tương ứng chỉ xác định vị trí ô tham chiếu, không nhất thiết là địa chỉ của đối tượng số nguyên được tham chiếu.

### Cài đặt bằng Python

```python
def flatten_ragged(rows: list[list[int]]) -> tuple[list[int], list[int]]:
    data: list[int] = []
    offsets: list[int] = [0]

    for row in rows:
        data.extend(row)
        offsets.append(len(data))
    return data, offsets


def get_flat_value(data: list[int], offsets: list[int],
                   i: int, j: int) -> int:
    m = len(offsets) - 1
    if not 0 <= i < m:
        raise IndexError("Hàng không hợp lệ")
    row_length = offsets[i + 1] - offsets[i]
    if not 0 <= j < row_length:
        raise IndexError("Cột không hợp lệ")
    return data[offsets[i] + j]


rows = [[12, 18, 21], [], [7, 9], [25]]
data, offsets = flatten_ragged(rows)
print(data)                   # [12, 18, 21, 7, 9, 25]
print(offsets)                # [0, 3, 3, 5, 6]
print(get_flat_value(data, offsets, 2, 1))  # 9
print(data[offsets[1]:offsets[2]])         # []
```

Việc tạo biểu diễn phẳng mất **`O(m+N)` thời gian** và cần `O(m+N)` vị trí lưu (gồm `N` ô dữ liệu, `m+1` offset). Sau khi đã có `offsets`, truy cập theo cặp chỉ số hợp lệ vẫn thường **`O(1)`**.

### Tìm hàng từ một chỉ số phẳng

Chiều ngược lại khó hơn: cho `k` trong `[0,N)`, cần xác định hàng nào đang chứa `data[k]`. Ta tìm hàng `i` sao cho:

\[
offsets[i]\le k<offsets[i+1]
\]

Vì `offsets` không giảm (có thể có giá trị trùng ở các hàng rỗng), có thể dùng **tìm kiếm nhị phân** để tìm điểm cuối của các offset `<= k`:

```python
from bisect import bisect_right

def coordinates_from_flat(offsets: list[int], k: int) -> tuple[int, int]:
    n = offsets[-1]
    if not 0 <= k < n:
        raise IndexError("Chỉ số phẳng không hợp lệ")
    i = bisect_right(offsets, k) - 1
    j = k - offsets[i]
    return i, j


offsets = [0, 3, 3, 5, 6]
print(coordinates_from_flat(offsets, 0))  # (0, 0)
print(coordinates_from_flat(offsets, 3))  # (2, 0), bỏ qua hàng rỗng
print(coordinates_from_flat(offsets, 5))  # (3, 0)
```

Hàm này giả định `offsets` hợp lệ, bắt đầu từ `0` và kết thúc tại `N`. Tìm kiếm nhị phân trên `m+1` offset mất **`O(log(m+1))` thời gian**; nếu đã biết hàng `i` và cột `j` thì truy cập trực tiếp không cần bước tìm ngược ấy.

## 6. So sánh bộ đệm phẳng và các hàng cấp phát riêng

| Tiêu chí | Mảng ngoài chứa các hàng | Bộ đệm phẳng + offsets |
|---|---|---|
| Số phần tử mỗi hàng | Do từng mảng con quản lý | `offsets[i+1]-offsets[i]` |
| Truy cập `A[i][j]` | Thường `O(1)` qua hai cấp chỉ số | Thường `O(1)` qua `offsets[i]+j` |
| Các ô dữ liệu có liền nhau? | Không bảo đảm giữa các hàng | Có nếu bộ đệm được thiết kế liên tiếp |
| Hàng rỗng | Mảng con rỗng | Hai offset kề nhau bằng nhau |
| Thêm vào cuối một hàng | Thường `O(1)` khấu hao nếu hàng là mảng động | Có thể phải chèn giữa bộ đệm và cập nhật offset phía sau |
| Duyệt theo hàng | Trực tiếp trên từng hàng | Duyệt các đoạn `data[offsets[i]:offsets[i+1]]` |
| Chi phí bộ nhớ | Đối tượng/tham chiếu cho từng hàng, có thể có dung lượng dự phòng | `N` ô dữ liệu và `m+1` offset, cộng quản lý bộ đệm |
| Trao đổi dữ liệu một khối | Cần gom hoặc mã hóa các hàng | Thuận lợi khi giao diện chấp nhận data + offsets |

Hai cách biểu diễn có thể chứa **cùng dữ liệu logic** nhưng đánh đổi khác nhau. Không thể kết luận cách nào luôn nhanh hơn nếu chưa biết loại phần tử, quy mô, cách cấp phát và tần suất cập nhật.

Đặc biệt, biểu diễn phẳng với offset có nét giống cách lưu **CSR (Compressed Sparse Row)** của ma trận thưa: CSR cũng dùng vùng dữ liệu theo hàng và con trỏ bắt đầu từng hàng, nhưng còn lưu **chỉ số cột** của các phần tử khác không nhằm tiết kiệm những vị trí bằng 0. Mảng răng cưa thông thường không có khái niệm “lỗ trống” trong mỗi hàng: các phần tử của một hàng được đánh chỉ số liên tiếp `0,1,\ldots,L_i-1`.

## 7. Chi phí thêm, xóa và thay đổi hình dạng

Một cấu trúc phù hợp không chỉ giúp **đọc nhanh** mà còn phải có chi phí cập nhật đáp ứng nhu cầu thực tế. Giả sử mỗi hàng là một Python `list` độc lập.

```python
rows = [[12, 18, 21], [], [7, 9], [25]]

rows[1].append(8)    # Thêm vào hàng vốn rỗng
rows[0].insert(1, 99)  # Chèn giữa hàng 0, dịch các phần tử ở hàng này
rows[2].pop(0)       # Xóa phần tử đầu của hàng 2
rows.append([])      # Thêm một hàng rỗng mới ở cuối

print(rows)  # [[12, 99, 18, 21], [8], [9], [25], []]
```

| Thao tác | Mảng ngoài + các hàng động (thường gặp) | Vì sao? |
|---|---|---|
| Đọc/ghi `A[i][j]` đã biết và hợp lệ | `O(1)` | Truy cập chỉ số qua hai cấp |
| Thêm cuối hàng `i` | `O(1)` khấu hao | Phát triển riêng hàng `i`; đôi khi cấp phát lại |
| Chèn/xóa ở giữa hàng `i` | `O(L_i)` trường hợp xấu nhất | Dịch phần đuôi của riêng hàng `i` |
| Thêm một hàng ở cuối | `O(1)` khấu hao | Mảng ngoài có thể phát triển |
| Chèn/xóa hàng ở giữa | `O(m)` trường hợp xấu nhất | Dịch các tham chiếu hàng phía sau |
| Duyệt toàn bộ cấu trúc | `O(m+N)` | Thăm mỗi hàng và mỗi phần tử |

Trong biểu diễn **phẳng + offsets**, thao tác thêm một phần tử vào **hàng nằm giữa** có thể cần:

1. Dịch đuôi `data` để tạo chỗ, chi phí tối đa `O(N)`.
2. Tăng các offset của mọi hàng đứng sau hàng được thêm phần tử, tối đa `O(m)`.

Vì vậy, một thao tác chèn vào giữa có thể tốn **`O(N+m)`**. Nếu chỉ thêm phần tử vào **hàng cuối cùng**, và `data` là mảng động, thường chỉ cần `append` và tăng `offsets[m]`, nên có thể đạt `O(1)` khấu hao. Dữ liệu ít thay đổi nhưng được duyệt, tìm và truyền dưới dạng bộ đệm liên tiếp thường phù hợp với biểu diễn phẳng hơn dữ liệu có các hàng cần mở rộng thường xuyên ở giữa.

**Lưu ý khi giữ các chỉ số:** chèn phần tử vào trước cột `j` có thể khiến các phần tử cũ dịch sang chỉ số lớn hơn; chèn hoặc xóa cả hàng làm thay đổi chỉ số hàng. Nếu dữ liệu có mã định danh nghiệp vụ cần tồn tại lâu dài, đừng dùng chỉ số vị trí như một mã định danh không đổi.

## 8. Có nên đệm thành ma trận chữ nhật?

Một cách khác là chọn `C_{\max}=\max_i L_i`, rồi tạo ma trận chữ nhật `m×C_{\max}`. Mỗi hàng được bổ sung các **ô đệm** để đủ `C_{\max}` phần tử:

```text
Mảng răng cưa:         Dạng chữ nhật có padding:

[12, 18, 21]           [12, 18, 21]
[]                     [ _,  _,  _]
[7, 9]                 [ 7,  9,  _]
[25]                   [25,  _,  _]

6 phần tử thật          12 ô được dành trong bảng 4 × 3
```

Số ô dữ liệu vật lý ở dạng chữ nhật là `m×C_{\max}`, so với `N=\sum_i L_i` phần tử thật ở dạng răng cưa. Tỷ lệ sử dụng là `N/(mC_{\max})` khi `mC_{\max}>0`; trong ví dụ là `6/12=50%`.

Dạng chữ nhật có thể thuận lợi nếu thuật toán hoặc thiết bị xử lý song song yêu cầu **cùng kích thước mỗi hàng**, hoặc thư viện số học tối ưu tốt với bộ đệm chữ nhật. Tuy nhiên, khoảng trống đệm có thể tốn nhiều bộ nhớ khi độ dài các hàng khác nhau rất lớn.

**Không dùng một giá trị như `0`, `-1` hoặc `None` để biểu diễn “không có phần tử” nếu giá trị ấy cũng có thể là dữ liệu hợp lệ**, trừ khi đặc tả đã dành riêng giá trị đó. Nên lưu thêm `L_i` hoặc *mask* đánh dấu ô thật, hoặc chọn một biểu diễn răng cưa để phân biệt dữ liệu với ô đệm.

Trong bài toán học máy, dữ liệu chuỗi có độ dài khác nhau thường được gom thành một lô (*batch*) bằng padding và mask. Khi xử lý từng chuỗi độc lập hoặc cần tiết kiệm bộ nhớ cho chuỗi rất ngắn, biểu diễn răng cưa có thể hợp lý hơn.

## 9. Ứng dụng quan trọng: danh sách kề của đồ thị

Trong đồ thị, mỗi đỉnh có số đỉnh láng giềng khác nhau. **Danh sách kề** (*adjacency list*) có thể xem như một mảng răng cưa, mỗi hàng tương ứng với một đỉnh.

Ví dụ, một đồ thị có hướng với bốn đỉnh `0,1,2,3`:

```text
Đỉnh 0 -> [1, 2]
Đỉnh 1 -> [2]
Đỉnh 2 -> []
Đỉnh 3 -> [0, 1, 2]
```

```python
adjacency = [
    [1, 2],
    [2],
    [],
    [0, 1, 2],
]

degrees = [len(neighbors) for neighbors in adjacency]
print(degrees)           # [2, 1, 0, 3]
print(sum(degrees))      # 6 cạnh có hướng (không trùng)

for vertex, neighbors in enumerate(adjacency):
    print(vertex, "->", neighbors)
```

Với đồ thị có hướng gồm `V` đỉnh, `E` cạnh (mỗi cạnh được ghi một lần theo đỉnh xuất phát), tổng số phần tử trong các danh sách kề là `E`. Vì vậy, lưu danh sách kề tốn **`O(V+E)` vị trí lưu**, tính cả `V` đầu hàng. Trong khi đó, **ma trận kề** chữ nhật `V×V` cần `O(V^2)` ô, kể cả khi rất ít cặp đỉnh nối với nhau.

Đánh đổi:

- Duyệt tất cả láng giềng của đỉnh `u` bằng danh sách kề mất `O(\deg^+(u))` thời gian, tương ứng số phần tử thực sự có trong hàng.
- Kiểm tra xem cạnh `u→v` có tồn tại bằng cách quét một danh sách kề **chưa được lập chỉ mục** thường mất `O(\deg^+(u))` trong trường hợp xấu nhất; dùng tập băm cho mỗi hàng có thể cải thiện tra cứu trung bình, nhưng tốn thêm bộ nhớ.
- Với ma trận kề, sau khi biết chỉ số `u,v`, kiểm tra một ô `matrix[u][v]` thường là `O(1)`, đổi lại chi phí lưu `O(V^2)`.

Khi đồ thị thưa, danh sách kề thường tiết kiệm bộ nhớ. Khi đồ thị dày đặc hoặc cần tra sự tồn tại của cạnh theo cặp đỉnh rất thường xuyên, ma trận kề có thể phù hợp. Đây là ví dụ cho thấy chọn cấu trúc dữ liệu phụ thuộc **kiểu thao tác cần hỗ trợ**, không chỉ số chiều của dữ liệu.

## 10. Mở rộng: nhiều cấp có độ dài không đều

Mảng răng cưa không chỉ giới hạn ở hai chiều. Xét dữ liệu ba cấp:

```python
tensor = [
    [[1, 2], [3]],           # Nhóm 0 có 2 hàng
    [[4], [], [5, 6, 7]],    # Nhóm 1 có 3 hàng
]

print(tensor[0][1][0])  # 3
print(tensor[1][2][1])  # 6
```

Để truy cập `tensor[a][b][c]`, phải lần lượt kiểm tra:

\[
0\le a<\operatorname{len}(tensor)
\]

\[
0\le b<\operatorname{len}(tensor[a])
\]

\[
0\le c<\operatorname{len}(tensor[a][b])
\]

Không có công thức `aD_1D_2+bD_2+c` với các `D_1,D_2` cố định nếu số hàng ở từng nhóm và số ô ở mỗi hàng khác nhau.

Nếu cần lưu phẳng cả ba cấp, có thể dùng **hai tầng offset**:

```text
Số hàng ở từng nhóm:      [2, 3]
group_offsets:             [0, 2, 5]

Độ dài của 5 hàng:         [2, 1, 1, 0, 3]
row_offsets:               [0, 2, 3, 4, 4, 7]

data:                      [1, 2, 3, 4, 5, 6, 7]
```

Với tọa độ `(a,b,c)=(1,2,1)`:

1. Hàng toàn cục là `group_offsets[1]+2=2+2=4`.
2. Chỉ số phẳng là `row_offsets[4]+1=4+1=5`.
3. Giá trị `data[5]=6`.

Ý tưởng **offset theo từng cấp** cho phép biểu diễn cây danh sách có độ dài biến đổi, nhưng cấu trúc dữ liệu phức tạp hơn mảng chữ nhật: mỗi tầng phải bảo toàn bất biến tổng tiền tố và phạm vi của các phần tử con.

## 11. Một số lỗi triển khai đặc biệt nguy hiểm

### Vô tình để nhiều hàng dùng chung một danh sách

Python có cú pháp nhân danh sách, nhưng nếu dùng với một **danh sách con có thể thay đổi**, các hàng có thể là **cùng một đối tượng**:

```python
# Sai nếu muốn các hàng độc lập:
bad = [[0] * 3] * 2
bad[0][1] = 9
print(bad)  # [[0, 9, 0], [0, 9, 0]]

# Đúng: tạo riêng từng hàng.
good = [[0] * 3 for _ in range(2)]
good[0][1] = 9
print(good)  # [[0, 9, 0], [0, 0, 0]]
```

Lỗi này cũng xuất hiện khi tạo mảng răng cưa bằng cách lặp lại một hàng mẫu hoặc thêm nhiều lần **cùng một tham chiếu** vào mảng ngoài. Hãy bảo đảm mỗi hàng cần cập nhật độc lập được tạo thành một đối tượng riêng.

### Các bẫy khác

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Truy cập `rows[0]` để suy số cột khi `rows=[]` | Lỗi chỉ số | Kiểm tra số hàng trước |
| Lấy `len(rows[0])` làm số cột của mọi hàng | Sai với hàng ngắn hơn hoặc dài hơn | Dùng `len(rows[i])` theo từng hàng |
| Duyệt `for j in range(max_length)` rồi đọc mọi `rows[i][j]` | Đọc ngoài hàng ngắn | Duyệt đúng `range(len(rows[i]))` |
| Trộn chỉ số âm của Python với mô hình `0..L_i-1` | Đọc nhầm phần tử cuối | Kiểm tra `0 <= i < m` và `0 <= j < L_i` |
| Dùng `i*C+j` cho mảng răng cưa | Sai vị trí phẳng | Dùng `offsets[i]+j` |
| Giả định offsets tăng nghiêm ngặt | Không biểu diễn được hàng rỗng | Cho phép offsets bằng nhau |
| Không cập nhật offset khi sửa độ dài một hàng | Các vị trí của những hàng sau bị sai | Duy trì tổng tiền tố hoặc xây lại offsets |
| Coi tất cả ô trong ma trận padding đều là dữ liệu | Tính sai tổng, số lượng hoặc trung bình | Dùng độ dài thật hoặc mask |
| Dùng `zip(*rows)` để chuyển vị mà không xét hàng ngắn | Có thể bỏ các ô ngoài độ dài ngắn nhất | Quy định rõ cách xử lý ô thiếu |
| Sao chép mảng ngoài bằng `rows.copy()` rồi sửa hàng con | Hai cấu trúc vẫn chia sẻ hàng con | Sao chép từng hàng khi cần độc lập |

**Chuyển vị** một mảng răng cưa không luôn tạo ra ma trận chữ nhật hoặc một cấu trúc răng cưa tương ứng duy nhất: phải quy định các ô thiếu được bỏ qua, đệm bằng giá trị đặc biệt hay xem là lỗi. Nếu bài toán đòi phép nhân ma trận hoặc phép toán trên những ô tương ứng, cần xác định rõ yêu cầu hình dạng trước khi tính.

## 12. Chọn biểu diễn theo thao tác và ràng buộc

Trước khi chọn cách lưu, hãy xác định các đại lượng `m` (số hàng), `N` (tổng phần tử) và độ dài từng hàng `L_i`, rồi trả lời:

1. **Mỗi hàng có thường xuyên được thêm, xóa phần tử không?** Nếu có, các hàng động độc lập dễ cập nhật hơn một vùng phẳng duy nhất.
2. **Dữ liệu có chủ yếu được đọc tuần tự hoặc truyền qua giao diện bộ đệm không?** Nếu có, `data + offsets` cho cách duyệt liền mạch và biểu diễn gọn.
3. **Thư viện xử lý có yêu cầu hình dạng chữ nhật không?** Nếu có, cân nhắc padding và mask; kiểm tra chi phí `m×C_{\max}` so với `N`.
4. **Có nhiều hàng rỗng hoặc hàng cực ngắn không?** Phải tính chi phí phần mô tả các hàng, tham chiếu và offset, bên cạnh các phần tử thật.
5. **Cần tra các phần tử bên trong từng hàng theo vị trí, theo giá trị hay theo khóa?** Mảng cho truy cập chỉ số, nhưng tìm giá trị trong hàng chưa sắp xếp vẫn có thể là `O(L_i)`; bảng băm phụ có thể hữu ích nếu truy vấn theo khóa nhiều.

Ví dụ, một hệ thống theo dõi đơn hàng của hàng nghìn cửa hàng, mỗi cửa hàng có số đơn khác nhau: nếu cập nhật đơn liên tục theo cửa hàng, mảng các hàng động thuận tiện. Nếu tạo một **bản chụp dữ liệu ít thay đổi** để xử lý hàng loạt, bộ đệm phẳng có offsets có thể giảm chi phí quản lý từng hàng và phù hợp với thuật toán duyệt tuần tự. Nếu chạy phép tính số học yêu cầu nhiều hàng cùng độ dài, có thể phải đệm thành hình chữ nhật và đi kèm mặt nạ hợp lệ.

## 13. Bài tập tự kiểm tra

Cho mảng răng cưa:

```text
B = [
    [4, 8],
    [],
    [3, 5, 7, 9],
    [6],
]
```

1. Mảng có bao nhiêu hàng? Viết vector độ dài `L` và tổng số phần tử `N`. `B[2][3]` và `B[1][0]` có hợp lệ không?
2. Hãy trải phẳng `B` theo thứ tự từng hàng, xây mảng `offsets` có `m+1` phần tử.
3. Trong biểu diễn phẳng, giá trị `B[2][1]` nằm ở chỉ số `k` nào? Tính địa chỉ byte nếu `base=3000` và mỗi phần tử rộng `4` byte.
4. Với chỉ số phẳng `k=2`, phần tử thuộc hàng nào, cột nào? Tại sao cần xét các offset trùng nhau?
5. Chèn số `10` vào cuối **hàng `0`** của biểu diễn các hàng động. Viết lại hàng `0`. Trong biểu diễn phẳng, những offset nào thay đổi nếu vẫn giữ thứ tự dữ liệu?
6. Nếu đệm mảng thành hình chữ nhật với độ rộng bằng hàng dài nhất, cần bao nhiêu ô? Bao nhiêu ô là padding?
7. Một đồ thị có `V=1000` đỉnh và `E=2000` cạnh có hướng. Ước lượng số vị trí lưu của danh sách kề và ma trận kề bằng Big-O; biểu diễn nào thường tiết kiệm ô nhớ hơn?
8. Chỉ ra lỗi trong đoạn mã `rows = [[0] * 2] * 3; rows[0][0] = 5`. Cách viết đúng nếu muốn ba hàng độc lập là gì?
9. Một mảng nhiều chiều `C = [[[1], []], [[2, 3]]]` có bao nhiêu nhóm ngoài, số hàng từng nhóm và số phần tử tổng cộng?

### Đáp án và giải thích

1. `m=4`, `L=[2,0,4,1]`, `N=7`. `B[2][3]=9` hợp lệ; `B[1][0]` không hợp lệ vì hàng `1` rỗng.
2. `data=[4,8,3,5,7,9,6]`; `offsets=[0,2,2,6,7]`. Hàng `1` rỗng nên hai offset liên tiếp đều bằng `2`.
3. `k=offsets[2]+1=2+1=3`; địa chỉ `3000+3×4=3012`.
4. `k=2` nằm tại hàng `2`, cột `0`. Vì `offsets[1]=offsets[2]=2`, hàng `1` rỗng; phải chọn hàng thỏa `offsets[i] <= k < offsets[i+1]`.
5. Hàng `0` thành `[4,8,10]`. Độ dài hàng đầu tăng một, nên `offsets=[0,3,3,7,8]`; các offset từ vị trí `1` trở đi tăng `1`, và dữ liệu ở những hàng sau có thể cần dịch trong bộ đệm phẳng.
6. Hàng dài nhất có `4` phần tử: bảng `4×4` cần `16` ô, trong đó `16-7=9` ô padding.
7. Danh sách kề tốn `O(V+E)` vị trí lưu, ma trận kề tốn `O(V²)` ô; với `V=1000` và `E=2000` thì danh sách kề thường ít ô hơn đáng kể.
8. Ba hàng cùng tham chiếu đến một danh sách, nên sửa một hàng làm thay đổi cả ba. Viết `rows = [[0] * 2 for _ in range(3)]` để tạo ba hàng độc lập.
9. `C` có `2` nhóm ngoài; nhóm `0` có `2` hàng, nhóm `1` có `1` hàng. Tổng số phần tử là `1+0+2=3`.

## 14. Ghi nhớ

**Mảng răng cưa** lưu các hàng có độ dài `L_i` khác nhau, nên truy cập `A[i][j]` phải thỏa `0<=i<m` và `0<=j<L_i`. Tổng dữ liệu là `N=\sum_i L_i`, không nhất thiết bằng tích số hàng với một số cột cố định. Có thể biểu diễn bằng **mảng ngoài chứa các mảng con** để cập nhật từng hàng linh hoạt, hoặc bằng **`data + offsets`** để lưu phẳng và định vị `A[i][j]` tại `data[offsets[i]+j]`. Các offset liên tiếp có thể bằng nhau khi hàng rỗng. Truy cập phần tử theo hai chỉ số thường là `O(1)` với cả hai cách lưu; chi phí duyệt, chèn và xóa phụ thuộc tổng số phần tử, độ dài từng hàng cùng cách tổ chức vùng nhớ. Hiểu các bất biến này giúp xử lý dữ liệu không đều chính xác và lựa chọn cấu trúc thích hợp cho danh sách kề, chuỗi có độ dài khác nhau và những bài toán nhiều chiều khác.

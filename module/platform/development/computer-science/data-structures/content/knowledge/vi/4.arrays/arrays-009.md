# Lát cắt, khung nhìn và quan hệ với mảng gốc

## 1. Một đoạn mảng có nhất thiết là một mảng mới?

Cho mảng số liệu đo theo thứ tự thời gian:

```text
Chỉ số:   0    1    2    3    4    5
Dữ liệu: [10,  20,  30,  40,  50,  60]
               └──── [1, 4) ────┘
```

Khi nói “lấy các phần tử từ chỉ số `1` đến trước chỉ số `4`”, kết quả logic là `[20, 30, 40]`. Nhưng có **hai cách tạo kết quả với ý nghĩa rất khác nhau**:

- **Bản sao** (*copy*): tạo vùng chứa mới và chép các phần tử hoặc tham chiếu tương ứng. Thay đổi vị trí trong bản sao không tự động thay đổi vị trí trong mảng gốc.
- **Khung nhìn** (*view*): tạo một đối tượng mô tả cách truy cập một phần của **vùng dữ liệu đang có**; thông thường không chép phần tử. Nếu hai bên có quyền ghi vào cùng ô, cập nhật một bên có thể quan sát được từ bên kia.

Người học cần phân biệt thêm **bí danh** (*alias*): hai biến chỉ cùng một đối tượng mảng, chứ không phải hai đối tượng có dữ liệu giống nhau. Một lát cắt không mặc định là bản sao hay view trong mọi ngôn ngữ; **ngữ nghĩa phụ thuộc kiểu dữ liệu và thư viện**.

Sau bài học, bạn có thể:

1. Đọc quy ước khoảng nửa kín `[start, stop)` và bước nhảy `step` khi cắt mảng.
2. Phân biệt alias, bản sao nông (*shallow copy*), bản sao sâu (*deep copy*) và view.
3. Dự đoán đúng việc cập nhật bản sao, view hay mảng gốc có lan truyền hay không.
4. Tính độ lệch và stride của một view trên bộ đệm liên tiếp.
5. Phân tích chi phí thời gian và bộ nhớ của lấy lát cắt, duyệt view và sao chép dữ liệu.
6. Nhận diện rủi ro vòng đời bộ nhớ, thay đổi kích thước, truy cập ngoài giới hạn và view không liên tiếp.

Đây là một chủ đề của chương **Mảng** trong học phần **Cấu trúc dữ liệu**. Việc xác định dữ liệu được **sở hữu**, **tham chiếu** hay **sao chép** giúp hiểu bất biến và đánh đổi thời gian, bộ nhớ khi xây dựng mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị.

## 2. Lát cắt là một yêu cầu chọn các vị trí

Với mảng `A` có độ dài `n` và chỉ số bắt đầu từ `0`, khoảng nửa kín `[l, r)` chứa các chỉ số nguyên:

\[
l,\ l+1,\ldots,r-1 \quad \text{với }0\le l\le r\le n
\]

Số phần tử được chọn là `r-l`. Cận phải `r=n` là hợp lệ để mô tả đoạn đến cuối mảng, nhưng `A[n]` không phải một phần tử có thể truy cập.

Trong nhiều ngôn ngữ và thư viện, lát cắt còn có **bước nhảy** (*step*), ví dụ cú pháp Python:

```python
values = [10, 20, 30, 40, 50, 60, 70, 80]

print(values[1:5])     # [20, 30, 40, 50]
print(values[1:7:2])   # [20, 40, 60]
print(values[:3])      # [10, 20, 30]
print(values[5:])      # [60, 70, 80]
print(values[3:3])     # []: đoạn rỗng
print(values[::-1])    # [80, 70, 60, 50, 40, 30, 20, 10]
```

Ký hiệu `A[start:stop:step]` với bước dương chọn các chỉ số `start, start+step, ...` **trước** `stop`. Với `0 <= start <= stop <= n` và `step=t>0`, số phần tử được chọn là:

\[
\boxed{k=\left\lceil\frac{stop-start}{t}\right\rceil
=\left\lfloor\frac{stop-start+t-1}{t}\right\rfloor}
\]

Ví dụ `values[1:7:2]` chọn chỉ số `1,3,5` nên có `3` phần tử; `(7-1+2-1)//2=3`.

Với bước âm, các chỉ số giảm dần và cận `stop` vẫn **không được lấy**. `values[6:1:-2]` chọn chỉ số `6,4,2`. Python còn hỗ trợ chỉ số âm để đếm từ cuối, cận bị thiếu và cận nằm ngoài phạm vi được tự điều chỉnh theo quy tắc của `slice`; bước `0` gây `ValueError`. Những tiện ích này là **quy tắc ngôn ngữ**, không thay thế điều kiện kiểm tra chỉ số hợp lệ khi xây dựng thuật toán tổng quát.

**Cốt lõi:** một mô tả lát cắt cho biết *chọn ô nào*, chưa tự cho biết *các ô đó được sao chép hay dùng chung bộ nhớ*.

## 3. Alias, copy và view: ba quan hệ khác nhau

Giả sử mảng gốc là `A=[10,20,30,40,50]`.

### 3.1. Bí danh: cùng một đối tượng

`B=A` không tạo mảng khác. `A` và `B` là hai tên chỉ cùng một đối tượng:

```python
original = [10, 20, 30, 40, 50]
alias = original

alias[1] = 99
print(original)             # [10, 99, 30, 40, 50]
print(alias is original)    # True
```

Mọi thao tác thay đổi trực tiếp đối tượng, như `append`, `pop` hay gán phần tử, đều được nhìn thấy qua cả hai biến.

### 3.2. Bản sao: một vùng chứa khác

`B=A[l:r]` trên Python `list` tạo **danh sách mới**. Hai danh sách có thể ban đầu chứa các giá trị bằng nhau nhưng không phải cùng một đối tượng:

```python
original = [10, 20, 30, 40, 50]
copied = original[1:4]

print(copied)               # [20, 30, 40]
print(copied is original)   # False

copied[0] = 77
print(copied)               # [77, 30, 40]
print(original)             # [10, 20, 30, 40, 50]
```

Việc thay ô `copied[0]` không làm đổi `original[1]`. Tuy nhiên, bản sao lát cắt `list` là **bản sao nông**: các phần tử của danh sách mới vẫn có thể là tham chiếu đến **cùng đối tượng con**; phần này sẽ được phân tích riêng.

### 3.3. View: đối tượng khác, dùng chung ô dữ liệu

View thường có **thông tin mô tả riêng** như vùng gốc, độ lệch bắt đầu, độ dài và stride, nhưng không có bộ dữ liệu phần tử độc lập.

```text
Mảng gốc (các ô nhớ):
       0       1       2       3       4
      [10]    [20]    [30]    [40]    [50]
               ↑       ↑       ↑
View [1:4]  ───┘───────┘───────┘

Chỉ số trong view:  0       1       2
Chỉ số trong gốc:   1       2       3
```

Nếu một view có quyền ghi, phép gán `view[0] = 77` tương ứng với việc ghi vào ô `original[1]`. View có thể là **chỉ đọc** (*read-only*) hoặc **có thể ghi** (*writable*), nên không nên kết luận view nào cũng sửa được mảng gốc.

| Quan hệ | Có đối tượng chứa riêng? | Có sao chép các ô dữ liệu lúc tạo? | Gán lại phần tử qua biến mới ảnh hưởng gốc? |
|---|---|---|---|
| Alias | Không | Không | Có, vì chính là cùng đối tượng |
| Copy nông của `list` | Có | Sao chép các tham chiếu trong đoạn | Không đối với ô của danh sách ngoài; đối tượng con vẫn có thể dùng chung |
| View có thể ghi | Có đối tượng mô tả riêng | Thường không sao chép dữ liệu | Có, nếu cùng ánh xạ tới ô nhớ |
| View chỉ đọc | Có đối tượng mô tả riêng | Thường không sao chép dữ liệu | Không cho phép gán qua view |

## 4. Python list: lát cắt thường tạo bản sao nông

Trong Python, `list` là mảng động chứa tham chiếu đến các đối tượng. Lấy `numbers[l:r]` hoặc `numbers[l:r:step]` tạo **một danh sách mới** chứa các tham chiếu được chọn.

```python
numbers = [10, 20, 30, 40, 50]
part = numbers[1:4]       # Danh sách mới [20, 30, 40]

numbers[2] = 300
print(part)               # [20, 30, 40], không cập nhật theo gốc

part[0] = 200
print(numbers)            # [10, 20, 300, 40, 50]
print(part)               # [200, 30, 40]
```

Với một lát cắt lấy `k` phần tử, việc tạo danh sách mới thường tốn **`O(k)` thời gian và `O(k)` bộ nhớ phụ** để lưu các tham chiếu. Các đối tượng phần tử không nhất thiết được sao chép.

### 4.1. Gán vào lát cắt của gốc không giống sửa bản sao

So sánh hai tình huống:

```python
data = [10, 20, 30, 40, 50]
slice_copy = data[1:4]
slice_copy[:] = [7, 8, 9]   # Chỉ đổi danh sách slice_copy
print(data)                 # [10, 20, 30, 40, 50]

data[1:4] = [7, 8]         # Gán trực tiếp vào đoạn của data
print(data)                 # [10, 7, 8, 50]
print(slice_copy)           # [7, 8, 9]
```

Biểu thức `data[1:4] = ...` không phải là “lấy bản sao rồi thay bản sao”; nó là **phép gán lát cắt** do đối tượng `list` thực hiện ngay trên dữ liệu gốc. Khi dùng bước mặc định `1`, số phần tử thay thế **có thể khác** số phần tử bị xóa, khiến độ dài mảng thay đổi và các phần tử phía sau dịch vị trí.

Ngược lại, với gán lát cắt có bước khác `1`, Python yêu cầu số phần tử mới bằng số vị trí được chọn:

```python
data = [0, 1, 2, 3, 4, 5]
data[::2] = [10, 20, 30]
print(data)  # [10, 1, 20, 3, 30, 5]

# data[::2] = [10] -> ValueError: số phần tử thay thế không khớp
```

Các phép gán lát cắt có thể dịch chuyển nhiều phần tử, nên thời gian không đơn thuần là `O(1)` cho mọi phép gán.

### 4.2. Bản sao nông vẫn chia sẻ đối tượng con

Điểm dễ gây lỗi nhất là mảng **lồng nhau** hoặc các phần tử chứa đối tượng có thể thay đổi:

```python
original = [[1], [2], [3], [4]]
piece = original[1:3]

piece[0].append(99)
print(original)            # [[1], [2, 99], [3], [4]]
print(piece)               # [[2, 99], [3]]

piece[0] = [777]
print(original[1])         # [2, 99], không bị thay bằng [777]
print(piece)               # [[777], [3]]
```

Lý do: `piece[0]` lúc đầu và `original[1]` đều trỏ tới **cùng danh sách con**. Phương thức `append` thay đổi danh sách con đó, còn phép `piece[0] = [777]` chỉ thay tham chiếu ở vị trí `0` của danh sách ngoài `piece`.

Khi cần cấu trúc độc lập ở **mọi cấp**, phải sao chép các đối tượng con tương ứng hoặc dùng `copy.deepcopy` nếu ngữ nghĩa sao chép sâu phù hợp với dữ liệu. Sao chép sâu có thể tốn nhiều thời gian và bộ nhớ, và không phải mọi đối tượng đều nên hoặc có thể được sao chép như nhau.

## 5. Python memoryview: ví dụ view thực sự không chép dữ liệu

Python có kiểu `memoryview` để cung cấp khung nhìn lên các đối tượng hỗ trợ **giao thức bộ đệm** (*buffer protocol*) như `bytearray`, `bytes` và một số mảng số. Khác với cắt `list`, cắt `memoryview` thường tạo view mới chia sẻ vùng dữ liệu.

```python
buffer = bytearray(b"abcdef")
view = memoryview(buffer)[1:5:2]  # Chọn vị trí 1 và 3: b"bd"
print(bytes(view))                # b'bd'

view[0] = ord("X")                # Ghi vào buffer[1]
print(buffer)                     # bytearray(b'aXcdef')

buffer[3] = ord("Y")              # Ghi vào ô thứ hai của view
print(bytes(view))                # b'XY'
print(buffer)                     # bytearray(b'aXcYef')

snapshot = bytes(view)           # Tạo bản sao bytes độc lập
buffer[1] = ord("Z")
print(bytes(view))                # b'ZY', view thấy thay đổi
print(snapshot)                   # b'XY', bản sao không đổi

view.release()                   # Giải phóng quyền truy cập bộ đệm của view
```

Ở đây, `view` có **chỉ số riêng từ `0`**, nhưng `view[0]` ánh xạ tới `buffer[1]` và `view[1]` ánh xạ tới `buffer[3]`. Lát cắt với bước `2` là một khung nhìn **không liên tiếp theo các phần tử được chọn**; việc `bytes(view)` tạo một vùng `bytes` mới không làm view trở thành bản sao.

Nếu nền tảng bộ đệm là bất biến như `bytes`, `memoryview` thường là **chỉ đọc**:

```python
view = memoryview(b"abc")
print(view.readonly)  # True
# view[0] = 88 -> TypeError: cannot modify read-only memory
view.release()
```

### View đang hoạt động và thay đổi kích thước bộ đệm

Khi một `memoryview` còn xuất dữ liệu từ `bytearray`, Python thường **không cho phép thay đổi kích thước** của `bytearray`. Việc này bảo vệ vùng nhớ mà view đang tham chiếu:

```python
data = bytearray(b"abc")
view = memoryview(data)

try:
    data.append(100)  # Thao tác làm tăng độ dài
except BufferError:
    print("Không thể thay đổi kích thước khi view đang hoạt động")

view.release()
data.append(100)      # Lúc này có thể thêm
print(data)           # bytearray(b'abcd')
```

Lưu ý: `release()` có nghĩa là view không còn được phép truy cập vùng đệm; nó không đồng nghĩa tự động xóa hoặc giải phóng mọi dữ liệu của mảng gốc. Không được dùng view sau khi đã release.

## 6. NumPy: basic slicing thường tạo view, advanced indexing tạo bản sao

Trong xử lý số liệu, ma trận và tensor, thư viện **NumPy** dùng kiểu `ndarray` gồm dữ liệu cùng thông tin hình dạng và stride. Với một `ndarray` thông thường, **lát cắt cơ bản** (*basic slicing*) như `a[1:4]`, `a[::2]` hoặc `a[:, 1:3]` thường tạo **view**. Trái lại, **lấy dữ liệu bằng danh sách chỉ số hoặc mặt nạ Boolean** (*advanced indexing*) tạo bản sao khi đọc.

> Đoạn mã dưới đây cần cài NumPy; đây là ví dụ về ngữ nghĩa thư viện, không phải ngữ nghĩa lát cắt của `list` Python.

```python
import numpy as np

a = np.array([10, 20, 30, 40, 50])
v = a[1:4]              # Basic slice: view
v[0] = 99
print(a.tolist())       # [10, 99, 30, 40, 50]
print(np.shares_memory(v, a))  # True

c = a[1:4].copy()       # Bản sao dữ liệu riêng
c[0] = -1
print(a.tolist())       # [10, 99, 30, 40, 50]

selected = a[[1, 3]]    # Advanced indexing khi đọc: bản sao
selected[0] = 777
print(a.tolist())       # [10, 99, 30, 40, 50]
```

**Điểm tinh tế:** `a[[1, 3]]` khi **đọc** tạo bản sao, nhưng `a[[1, 3]] = [7, 8]` là phép **gán có chỉ số** do mảng gốc thực hiện, nên sẽ thay các ô `a[1]` và `a[3]`. Đừng nhầm kết quả của phép đọc với tác động của phép gán.

```python
a = np.array([10, 20, 30, 40, 50])
picked = a[[1, 3]]        # Bản sao
picked[:] = [7, 8]
print(a.tolist())         # [10, 20, 30, 40, 50]

a[[1, 3]] = [7, 8]        # Gán trực tiếp vào a
print(a.tolist())         # [10, 7, 30, 8, 50]
```

Không nên đoán mọi phép biến đổi `reshape`, `ravel`, `transpose` hay mọi thao tác trên đối tượng thư viện khác đều chia sẻ dữ liệu. Một số thao tác có thể tạo view **hoặc** bản sao tùy bố trí hiện tại. Với NumPy, có thể dùng `np.shares_memory(result, source)` để kiểm tra hai mảng có vùng dữ liệu dùng chung hay không, hoặc dùng `.copy()` khi cần chắc chắn có bản sao độc lập.

## 7. Địa chỉ, độ lệch và stride của view một chiều

Đối với một mảng liên tiếp `A` có ô rộng `s` byte, giả sử view chọn các phần tử ở chỉ số gốc:

\[
l,\ l+t,\ l+2t,\ldots,l+(k-1)t
\]

Trong đó `t` là bước theo **số phần tử**, có thể dương hoặc âm nếu thư viện cho phép. Phần tử thứ `j` của view ánh xạ đến:

\[
\boxed{V[j]=A[l+jt]},\quad 0\le j<k
\]

Vì vậy, địa chỉ phần tử thứ `j` trong view là:

\[
\boxed{\operatorname{addr}(V[j])=base_A+(l+jt)s}
\]

Đặt `base_V=base_A+ls` là địa chỉ ô đầu tiên của view, và `stride_V=t\,s` là khoảng cách địa chỉ giữa hai phần tử kề nhau của view, ta có:

\[
\boxed{\operatorname{addr}(V[j])=base_V+j\cdot stride_V}
\]

**Ví dụ:** mảng có tám phần tử, `base_A=1000`, mỗi ô rộng `s=4` byte. View lấy `A[1:7:2]`.

```text
Chỉ số gốc:   0    1    2    3    4    5    6    7
Địa chỉ:     1000 1004 1008 1012 1016 1020 1024 1028
                    ↑         ↑         ↑
View V:           [A[1],    A[3],    A[5]]
Chỉ số view:         0         1         2
```

Lúc này:

- `base_V=1000+1×4=1004`.
- `stride_V=2×4=8` byte; ba ô được xem ở địa chỉ `1004,1012,1020`.
- Mỗi ô rộng `4` byte nhưng khoảng cách trong view là `8` byte; **view không liên tiếp** theo các phần tử được chọn.

Nếu bước âm, `stride_V` cũng có thể âm: một view đảo ngược nhìn các ô theo thứ tự ngược mà không nhất thiết phải đảo dữ liệu vật lý. Để lấy địa chỉ đúng, điểm bắt đầu `base_V` phải ứng với **phần tử đầu tiên theo thứ tự view**, không nhất thiết là ô đầu của mảng gốc.

Stride mô tả ánh xạ dữ liệu, nhưng không tự đảm bảo view có quyền ghi hay việc thay đổi vùng gốc được phép. Những điều này thuộc hợp đồng quản lý bộ nhớ của kiểu dữ liệu.

## 8. Khung nhìn nhiều chiều: cắt vùng ảnh và chuyển vị

Đối với ma trận có `R` hàng, `C` cột, kích thước ô `s` byte, cách lưu **theo hàng** (*row-major*) liên tiếp có:

\[
stride_{row}=C\,s,\qquad stride_{col}=s
\]

Địa chỉ tọa độ `(i,j)`:

\[
\operatorname{addr}(M[i,j])
=base+i\cdot stride_{row}+j\cdot stride_{col}
\]

Một **view của vùng con** có thể chỉ đổi địa chỉ bắt đầu và giữ hoặc nhân các stride với bước lát cắt. Ví dụ:

```text
Mảng gốc M (3 hàng × 4 cột):

           c0   c1   c2   c3
    r0      0    1    2    3
    r1      4    5    6    7
    r2      8    9   10   11

View M[1:3, 1:4:2]:
            5    7
            9   11
```

Đây là hai hàng cuối, các cột `1` và `3`. Với NumPy:

```python
import numpy as np

matrix = np.arange(12).reshape(3, 4)
crop = matrix[1:3, 1:4:2]
print(crop.tolist())        # [[5, 7], [9, 11]]

crop[0, 0] = 500
print(matrix[1, 1])        # 500: cùng ô dữ liệu

transposed = matrix.T      # Hoán đổi trục, thường là view
print(transposed.shape)    # (4, 3)
print(np.shares_memory(transposed, matrix))  # True
```

Với ma trận ban đầu row-major, các phần tử kề nhau theo cột logic của view chuyển vị có thể **không kề nhau trong bộ nhớ**. Phép chuyển vị dạng view thường hoán đổi thông tin shape và stride, thay vì dời mọi phần tử sang vùng mới.

Đối với bộ đệm có khoảng đệm cuối hàng, stride hàng có thể lớn hơn `C×s`. Do đó, khi xử lý ảnh, tensor hoặc dữ liệu lấy từ thư viện ngoài, không được tự đoán một view là liên tiếp chỉ từ hình dạng của nó. Một số giao diện yêu cầu dữ liệu liên tiếp và có thể cần tạo bản sao trước khi truyền vào.

## 9. Chi phí thời gian và bộ nhớ: đừng chỉ nhìn độ dài đoạn

Giả sử lấy `k` phần tử từ mảng gốc có `n` phần tử. Dưới các giả định thao tác trên từng ô có chi phí hằng số:

| Thao tác | Thời gian tạo/làm | Bộ nhớ phụ điển hình | Ghi chú |
|---|---|---|---|
| Gán alias `b = a` | `O(1)` | `O(1)` | Không tạo đối tượng chứa mới |
| Lấy `list` slice `a[l:r]` | `O(k)` | `O(k)` | Tạo danh sách mới chứa `k` tham chiếu |
| Tạo một view đơn giản lên bộ đệm | Thường `O(1)` | Thường `O(1)` | Chỉ tạo mô tả vùng, offset và stride |
| Truy cập `view[j]` với thông tin ánh xạ đã biết | Thường `O(1)` | `O(1)` | Tính vị trí qua offset và stride |
| Duyệt đủ `k` phần tử trong slice/view | `O(k)` | `O(1)` ngoài đối tượng đã có | Mỗi phần tử vẫn phải được đọc |
| Chép một view thành vùng độc lập | `O(k)` | `O(k)` | Phải đọc và lưu `k` phần tử |
| Gán lát cắt làm thay đổi độ dài `list` | Có thể `O(n+k)` | Tùy triển khai | Có thể dịch đuôi và cấp phát lại |

**View không làm phép duyệt `k` phần tử trở thành `O(1)`.** Nó chỉ có thể tránh chi phí **sao chép ban đầu**, và đôi khi tránh bộ nhớ phụ. Ngược lại, khi view có stride lớn, truy cập dữ liệu không liên tiếp có thể gây nhiều lần trượt cache hơn một bản sao đã sắp lại liên tiếp; trong vài bài toán lặp lại rất nhiều lần, trả chi phí tạo bản sao một lần có thể tăng hiệu năng tổng thể.

### View nhỏ có thể giữ cả vùng dữ liệu gốc tồn tại

Một view chỉ tham chiếu tới vài phần tử nhưng thường phải giữ một quan hệ tham chiếu tới bộ đệm gốc (trực tiếp hoặc gián tiếp). Vì vậy, giữ view lâu dài có thể làm **toàn bộ vùng dữ liệu gốc lớn chưa được giải phóng**. Bộ nhớ “phụ” của bản thân view có thể nhỏ nhưng **lượng bộ nhớ bị giữ sống** vẫn lớn.

Ví dụ, nếu đọc một tệp lớn vào bộ đệm rồi chỉ cần lưu lại mười byte trong nhiều giờ, việc tạo một bản sao mười byte có thể tốt hơn giữ view khiến cả bộ đệm lớn tiếp tục tồn tại.

## 10. Vòng đời, thay đổi kích thước và bất biến khi dùng chung dữ liệu

View tạo ra sự **phụ thuộc** giữa đối tượng sử dụng và vùng dữ liệu được dùng chung. Cần xác định rõ:

1. **Ai sở hữu bộ đệm?** View thường không tự sở hữu bản sao đầy đủ của dữ liệu.
2. **Dữ liệu có được thay đổi hay không?** Nếu view có quyền ghi, thay đổi có thể xuất hiện ngay ở mảng gốc hoặc view khác.
3. **Có được thay đổi hình dạng hoặc cấp phát lại không?** Một số kiểu chặn thao tác đổi kích thước khi view còn hoạt động; một số giao diện con trỏ/view không sở hữu khác có thể trở nên không hợp lệ sau khi vùng gốc cấp phát lại.
4. **View còn hợp lệ bao lâu?** Phải tuân theo thời hạn sống và quy tắc của vùng nhớ gốc.
5. **Có nhiều luồng cùng ghi không?** Chia sẻ bộ nhớ không tự tạo an toàn luồng, tính nguyên tử hay đồng bộ.

Ví dụ trong C++, `std::span<T>` là một kiểu view không sở hữu bộ nhớ. Nếu `std::vector<T>` gốc tăng dung lượng và cấp phát lại, một `span` đang trỏ vào vùng nhớ cũ có thể không còn hợp lệ; việc tiếp tục truy cập là nguy hiểm. Ngược lại, đối tượng `memoryview` của Python giữ quan hệ với exporter qua buffer protocol và có những cơ chế bảo vệ riêng. **Không thể lấy quy tắc an toàn của một API áp dụng cho mọi view khác.**

Một bất biến hữu ích cho thuật toán xử lý đoạn là ghi rõ **khoảng gốc nào** đang được xem, ví dụ `[l,r)`, và bảo đảm mọi chỉ số trong view ánh xạ tới một chỉ số gốc hợp lệ. Khi có bước `t`, điều kiện là `0 <= l+j*t < n` với mọi `j` thuộc miền của view. Nếu vùng dữ liệu gốc bị thay đổi trong lúc chạy, thuật toán phải quy định liệu sự thay đổi đó được phép và có giữ bất biến hay không.

## 11. Ví dụ thuật toán: tránh sao chép lát cắt không cần thiết

Giả sử cần tìm tổng lớn nhất của mọi đoạn liên tiếp dài đúng `k` trong một mảng số nguyên `values`. Một cách dễ viết là lấy lát cắt cho từng vị trí bắt đầu:

```python
def max_window_sum_by_slicing(values: list[int], k: int) -> int:
    if not 1 <= k <= len(values):
        raise ValueError("Độ dài cửa sổ không hợp lệ")

    best = None
    for left in range(len(values) - k + 1):
        current = sum(values[left:left + k])  # Tạo list mới k phần tử
        best = current if best is None else max(best, current)
    return best


print(max_window_sum_by_slicing([4, 1, 7, 2, 5], 3))  # 14
```

Có `n-k+1` cửa sổ; mỗi lát cắt và phép tính tổng mất `O(k)` thời gian. Tổng thời gian là **`O((n-k+1)k)`** và mỗi lần cắt cần **`O(k)` bộ nhớ phụ**. Trong trường hợp `k` tỷ lệ với `n`, thời gian có thể lên `O(n²)`.

Nếu khai thác quan hệ giữa hai cửa sổ kề nhau, ta chỉ cần **bỏ giá trị rời cửa sổ và thêm giá trị mới**:

```python
def max_window_sum(values: list[int], k: int) -> int:
    if not 1 <= k <= len(values):
        raise ValueError("Độ dài cửa sổ không hợp lệ")

    current = sum(values[i] for i in range(k))
    best = current

    for right in range(k, len(values)):
        current += values[right] - values[right - k]
        best = max(best, current)

    return best


print(max_window_sum([4, 1, 7, 2, 5], 3))  # 14
```

Thuật toán thứ hai có thời gian **`O(n)`** và bộ nhớ phụ **`O(1)`** (không tạo các danh sách lát cắt). Đây là một ví dụ cho thấy hiểu sự khác nhau giữa **mô tả đoạn**, **tạo bản sao đoạn** và **xử lý trực tiếp trên mảng gốc** có thể thay đổi đáng kể hiệu năng. Nếu thực sự cần chuyển một đoạn cho hàm khác, một view thích hợp có thể tránh sao chép, nhưng cần giữ rõ ràng hợp đồng về khả năng ghi và thời hạn sống.

## 12. Chọn copy hay view trong tình huống thực tế?

| Nhu cầu | Lựa chọn nên cân nhắc | Lý do |
|---|---|---|
| Chỉ cần đọc nhanh một vùng dữ liệu lớn, không sửa | View chỉ đọc nếu API hỗ trợ | Tránh tạo bản sao `O(k)` |
| Cần chỉnh sửa một phần và **muốn** tác động đến mảng gốc | View có thể ghi hoặc gán lát cắt lên gốc | Cùng dữ liệu, ít sao chép |
| Muốn thử nghiệm/chỉnh sửa nhưng không được thay mảng gốc | Bản sao độc lập | Tránh tác dụng phụ ngoài ý muốn |
| Muốn giữ vài phần tử lâu sau khi bỏ mảng rất lớn | Bản sao nhỏ | Không giữ sống bộ đệm gốc lớn |
| Cần truyền dữ liệu cho API yêu cầu liên tiếp | Có thể cần bản sao liên tiếp | View có stride có thể không đáp ứng yêu cầu |
| Dữ liệu gốc thường xuyên thay đổi kích thước/cấp phát lại | Cẩn trọng với view; cân nhắc copy | Tránh view hết hiệu lực hoặc thao tác resize bị chặn |
| Cần chỉnh sửa đối tượng lồng nhau một cách độc lập | Sao chép cả các đối tượng con phù hợp | Lát cắt `list` chỉ tạo bản sao nông |
| Cần chia sẻ thay đổi giữa nhiều thành phần | View/alias với hợp đồng ghi rõ ràng | Phải quản lý đồng bộ và quyền sở hữu |

Không có quy tắc “view luôn tốt hơn copy”. View tiết kiệm công việc tạo dữ liệu nhưng làm tăng sự phụ thuộc giữa các thành phần. Copy tốn thời gian và bộ nhớ ban đầu nhưng giúp cô lập trạng thái và thường dễ lập luận về tính đúng đắn hơn.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| “Mọi cú pháp `a[l:r]` đều là view.” | Python `list` tạo bản sao nông; NumPy `ndarray` basic slicing thường tạo view |
| “Mọi bản sao lát cắt đều độc lập hoàn toàn.” | `list` slice sao chép các tham chiếu; đối tượng con có thể vẫn dùng chung |
| “`part = a[1:3]` rồi `part[0] = x` là sửa `a[1]`.” | Với `list` thì không; với view có thể ghi thì có |
| “`a[1:3] = [...]` trước hết tạo bản sao.” | Đây là gán lát cắt trực tiếp vào `a`; có thể đổi độ dài |
| “View nhất thiết liên tiếp.” | Bước nhảy, chuyển vị và padding có thể tạo view với stride khác kích thước ô |
| “Bản sao tốn `O(1)` vì chỉ truyền biến.” | Tạo bản sao `k` ô thường tốn `O(k)`; gán alias mới là `O(1)` |
| “View có kích thước rất nhỏ thì không giữ bộ nhớ đáng kể.” | View có thể giữ sống toàn bộ bộ đệm lớn |
| “Sửa mảng gốc không ảnh hưởng view.” | Một view chia sẻ ô nhớ có thể quan sát cập nhật; ngược lại copy thì không |
| “Lấy view rồi luôn có thể `append` vào vùng gốc.” | Một số API chặn resize hoặc khiến view không hợp lệ |
| “`a[[i,j]]` và `a[i:j]` có cùng ngữ nghĩa bộ nhớ.” | Trong NumPy, advanced indexing khi đọc thường sao chép, basic slicing thường tạo view |
| “View chỉ đọc cũng có thể gán dữ liệu như view thường.” | Cần kiểm tra quyền ghi; view chỉ đọc từ chối phép gán |
| “Sử dụng view bảo đảm an toàn khi nhiều luồng thay đổi dữ liệu.” | Không; còn cần đồng bộ và hợp đồng truy cập |

Khi xem một đoạn mảng từ thư viện chưa quen thuộc, hãy xác định bốn thông tin: **(1)** tạo copy hay view, **(2)** có thể ghi không, **(3)** có liên tiếp không, **(4)** có còn hợp lệ sau khi mảng gốc thay đổi kích thước hoặc hết vòng đời không.

## 14. Bài tập tự kiểm tra

**Bài 1.** Cho `a = [2,4,6,8,10,12]`. Hãy tính `a[1:5]`, `a[0:6:2]` và `a[5:0:-2]`. Các đoạn lần lượt có bao nhiêu phần tử?

**Bài 2.** Trong Python, sau đoạn mã `a=[1,2,3,4]; b=a[1:3]; b[0]=99`, giá trị của `a` và `b` là gì? Vì sao?

**Bài 3.** Cho `a=[[1],[2],[3]]; b=a[1:]`. Sau lệnh `b[0].append(7)`, `a` thay đổi ra sao? Nếu tiếp theo `b[0]=[9]`, `a[1]` có bị thay bằng `[9]` không?

**Bài 4.** Một mảng liên tiếp có `base=2000`, phần tử rộng `s=8` byte. Một view chọn các vị trí gốc `2,5,8`. Tính địa chỉ đầu view, stride và địa chỉ phần tử thứ ba của view.

**Bài 5.** Cho `buffer = bytearray(b"wxyz")`, `view = memoryview(buffer)[1:3]`. Sau `view[0]=ord("A")`, `buffer` là gì? Nếu chạy `view.release()`, buffer gốc có tự biến mất không?

**Bài 6.** Trong NumPy, phân biệt `a[1:4]`, `a[[1,3]]` và `a[1:4].copy()` về việc dùng chung vùng dữ liệu. Nếu muốn chắc chắn có vùng độc lập cho lát cắt, nên dùng thao tác nào?

**Bài 7.** Vì sao tạo một view dài `10` phần tử từ bộ đệm `1` triệu phần tử có thể vẫn khiến bộ đệm lớn tồn tại trong bộ nhớ? Nêu một trường hợp nên sao chép dữ liệu nhỏ.

**Bài 8.** Trong thuật toán tìm tổng lớn nhất của các cửa sổ dài `k` trên mảng dài `n`, cách liên tục gọi `sum(a[i:i+k])` có chi phí thời gian nào? Làm thế nào đạt `O(n)` mà không tạo lát cắt mới?

**Bài 9.** Một chương trình giữ view không sở hữu bộ nhớ từ mảng động của ngôn ngữ cấp thấp. Mảng gốc được mở rộng và cấp phát lại. Có nên tiếp tục sử dụng view cũ không? Vì sao?

### Đáp án gợi ý

1. `[4,6,8,10]` (4 phần tử), `[2,6,10]` (3 phần tử), `[12,8,4]` (3 phần tử: chỉ số `5,3,1`).
2. `a=[1,2,3,4]`, `b=[99,3]`. `list` slice tạo một danh sách mới, nên gán vào ô của `b` không thay ô của `a`.
3. Sau `append`, `a=[[1],[2,7],[3]]` do hai danh sách ngoài chia sẻ đối tượng con. Gán `b[0]=[9]` chỉ thay tham chiếu trong `b`, nên `a[1]` vẫn là `[2,7]`.
4. Vị trí gốc đầu là `2` nên `base_V=2000+2×8=2016`; bước là `3×8=24` byte; phần tử thứ ba có chỉ số view `2` và địa chỉ `2016+2×24=2064`.
5. `buffer=bytearray(b"wAyz")`. `release()` kết thúc việc dùng bộ đệm qua view; không tự xóa buffer gốc.
6. `a[1:4]` là basic slicing nên thường là view; `a[[1,3]]` là advanced indexing khi đọc nên tạo bản sao; `a[1:4].copy()` là bản sao tường minh.
7. View có thể giữ tham chiếu đến toàn bộ vùng gốc. Nếu chỉ muốn giữ vài giá trị rất lâu sau khi bỏ dữ liệu lớn, sao chép đoạn nhỏ có thể giảm bộ nhớ bị giữ sống.
8. Mỗi cửa sổ tốn `O(k)` nên tổng `O((n-k+1)k)`; dùng tổng trượt, trừ phần tử đi ra và cộng phần tử đi vào, để đạt `O(n)` thời gian và `O(1)` bộ nhớ phụ.
9. Không. Nếu vùng gốc đã cấp phát lại, view không sở hữu bộ nhớ có thể trỏ tới vị trí cũ không hợp lệ; phải lấy lại view phù hợp với vùng dữ liệu mới.

## 15. Ghi nhớ

**Lát cắt** mô tả những vị trí được chọn, còn **bản sao** và **khung nhìn** mô tả cách lưu và chia sẻ dữ liệu. Với `list` Python, lát cắt tạo bản sao nông `O(k)` thời gian và bộ nhớ; với `memoryview` hoặc lát cắt cơ bản của NumPy, thường có thể tạo view chia sẻ bộ nhớ với chi phí mô tả gần `O(1)`. View có thể nhìn thấy cập nhật từ mảng gốc, có thể không liên tiếp do stride và có thể giữ vùng gốc tồn tại hoặc bị ràng buộc bởi vòng đời của vùng nhớ. Để chọn đúng, hãy xác định rõ **ai sở hữu dữ liệu, có được sửa chung hay không, vùng nhớ có liên tiếp không và khi nào view hết hợp lệ**. Hiểu những hợp đồng này giúp tránh lỗi dữ liệu và đánh giá chính xác độ phức tạp thời gian, bộ nhớ của thuật toán trên mảng.

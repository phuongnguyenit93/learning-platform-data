# Lỗi vượt biên, lệch một đơn vị và nhầm độ dài với chỉ số cuối

## 1. Một phép truy cập sai chỉ vì nhầm số đếm với vị trí

Cho mảng lưu nhiệt độ của năm ngày:

```text
Chỉ số:     0     1     2     3     4
Giá trị:  [28,   30,   29,   27,   31]

Độ dài n = 5
Chỉ số đầu = 0
Chỉ số cuối = 4 = n - 1
                  ↑            ↑
               phần tử       ranh giới
                 cuối       sau cuối: 5
```

Mảng chứa **năm phần tử**, nhưng không có phần tử ở chỉ số `5`. Đây là nguồn gốc của rất nhiều lỗi trong chương trình:

- **Vượt biên** (*out-of-bounds*): truy cập vị trí không thuộc miền chỉ số hợp lệ.
- **Lệch một đơn vị** (*off-by-one*): lặp, đếm, sao chép hoặc cắt nhiều hơn hay ít hơn đúng một phần tử.
- **Nhầm độ dài với chỉ số cuối**: dùng `n` như chỉ số phần tử cuối thay vì `n-1`.

Ba khái niệm có liên quan, nhưng không hoàn toàn đồng nghĩa. Một vòng lặp sai có thể bỏ sót phần tử cuối mà **không** truy cập vượt biên; ngược lại, dùng điều kiện kết thúc sai có thể truy cập phần tử `A[n]` và gây lỗi bộ nhớ.

Sau bài này, bạn có thể:

1. Phân biệt **độ dài**, **sức chứa**, **chỉ số hợp lệ** và **cận ngay sau cuối**.
2. Sử dụng khoảng nửa kín `[l, r)` để giảm lỗi ở vòng lặp, lát cắt, sao chép và tìm kiếm.
3. Nhận diện lỗi lệch một đơn vị trong thao tác chèn, xóa, duyệt ngược và mảng nhiều chiều.
4. Giải thích sự khác nhau giữa Python có kiểm tra chỉ số và C/C++ nơi truy cập sai có thể dẫn đến hành vi không xác định.
5. Viết điều kiện kiểm tra biên an toàn, bao gồm tình huống mảng rỗng, chỉ số âm và số nguyên không dấu.
6. Thiết kế ca kiểm thử và bất biến vòng lặp nhằm phát hiện lỗi trước khi triển khai.

Đây là kiến thức nền tảng của chương **Mảng** trong học phần **Cấu trúc dữ liệu**: hiểu bất biến và giới hạn của phép truy cập giúp chọn, cài đặt và đánh giá an toàn các thao tác trên mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị.

## 2. Bốn đại lượng dễ bị đánh đồng

Giả sử một vùng đệm có thể chứa tối đa tám số nguyên nhưng hiện mới sử dụng năm số:

```text
Vị trí vật lý:  0   1   2   3   4   5   6   7
Vùng đệm:     [8,  6,  4,  2,  0,  _,  _,  _]
               └─ năm phần tử hợp lệ ─┘

length = 5
capacity = 8
last_index = 4
end = 5
```

| Khái niệm | Ký hiệu | Ý nghĩa |
|---|---|---|
| Độ dài (*length/size*) | `n` | **Số phần tử đang thuộc mảng logic** |
| Sức chứa (*capacity*) | `c` | Số ô mà vùng lưu trữ hiện có thể chứa trước khi cần mở rộng |
| Chỉ số cuối (*last index*) | `n-1` nếu `n>0` | Vị trí phần tử cuối đang tồn tại |
| Cận ngay sau cuối (*past-the-end*) | `n` | Ranh giới kết thúc, **không phải phần tử** |

Bất biến thường gặp của mảng động là:

\[
0\le n\le c.
\]

Nếu dùng quy ước chỉ số bắt đầu từ `0`, miền chỉ số đọc/ghi một phần tử đang tồn tại là:

\[
\boxed{0\le i<n.}
\]

Nếu `n=5` thì các chỉ số hợp lệ là `0,1,2,3,4`. Ô vật lý `5` có thể còn chỗ trống, nhưng chưa phải phần tử thứ sáu về mặt **độ dài logic**. Với các giao diện mảng động thông thường, không được dùng `A[5]` chỉ vì `capacity >= 6`.

### Mảng rỗng: trường hợp làm lộ lỗi ngay lập tức

Nếu `n=0`, tập chỉ số hợp lệ là **rỗng**. Khi đó:

- Không có “phần tử đầu” hay “phần tử cuối”.
- `n-1=-1` là kết quả số học, **không phải chỉ số cuối hợp lệ**.
- Cận ngay sau cuối vẫn là `0`.
- Đoạn `[0,0)` hợp lệ và rỗng.

Do vậy, mã đọc `A[n-1]` chỉ hợp lệ sau khi đã kiểm tra `n>0`.

## 3. Vì sao khoảng nửa kín [l, r) dễ suy luận hơn?

Một khoảng nửa kín `[l,r)` bao gồm `l`, nhưng **không bao gồm** `r`. Với `0<=l<=r<=n`, các chỉ số được chọn là:

\[
l,l+1,\ldots,r-1.
\]

Số phần tử trong đoạn là:

\[
\boxed{\operatorname{length}([l,r))=r-l.}
\]

Ví dụ, từ mảng `A=[10,20,30,40,50]`:

```text
A[1:4] tương ứng [1, 4):
Chỉ số:    0   1   2   3   4
Giá trị: [10, 20, 30, 40, 50]
               └───┘
Kết quả: [20, 30, 40]
Số phần tử: 4 - 1 = 3
```

Khoảng nửa kín mang lại ba đặc tính thuận tiện:

1. **Đoạn rỗng:** `[l,l)` có đúng `0` phần tử mà không cần chỉ số đặc biệt.
2. **Ghép hai đoạn:** `[l,m)` và `[m,r)` nằm kề nhau, không lặp lại hay bỏ mất chỉ số `m`; tổng số phần tử là `(m-l)+(r-m)=r-l`.
3. **Duyệt cả mảng:** `[0,n)` chứa đúng `n` phần tử, ngay cả khi `n=0`.

Ngược lại, khoảng **đóng** `[l,r]` bao gồm cả hai đầu, nên số phần tử bằng `r-l+1` khi `l<=r`. Nếu một API dùng cận đóng mà ta lại áp dụng công thức cho cận nửa kín, có thể chép thừa hoặc thiếu một phần tử.

| Mô tả | Chỉ số được chọn | Số phần tử |
|---|---|---:|
| `[1,4)` | `1,2,3` | `3` |
| `[1,4]` | `1,2,3,4` | `4` |
| `[3,3)` | Không có | `0` |
| `[0,n)` | `0,...,n-1` | `n` |

Trong bài học này, mặc định mọi **đoạn thuật toán** dùng cận nửa kín trừ khi có ghi rõ khác.

## 4. Lỗi lệch một đơn vị trong vòng lặp

### 4.1. Dùng <= n thay vì < n

```python
numbers = [10, 20, 30]
n = len(numbers)

# Sai: i có lúc bằng n = 3.
for i in range(n + 1):
    print(numbers[i])   # IndexError khi i = 3
```

Cách đúng:

```python
for i in range(n):
    print(numbers[i])

# Hoặc khi chỉ cần giá trị:
for value in numbers:
    print(value)
```

Trong Python, `range(n)` sinh `0` đến `n-1`. Nếu muốn dùng vòng lặp kiểu C, điều kiện tương đương là `i < n`, không phải `i <= n`:

```c
for (size_t i = 0; i < n; ++i) {
    use(a[i]);
}
```

Vòng lặp trên thực hiện đúng `n` lần, kể cả khi `n=0`: lúc ấy không có lần lặp nào.

### 4.2. Sai nhưng không phát sinh ngoại lệ: bỏ sót phần tử cuối

```python
values = [4, 6, 8, 10]

# Sai nếu mục tiêu là tính tổng tất cả phần tử.
total = 0
for i in range(len(values) - 1):
    total += values[i]
print(total)             # 18: thiếu 10

print(sum(values))       # 28: đúng
```

Không có truy cập vượt biên ở đoạn sai: vòng lặp chỉ duyệt `0,1,2`, bỏ mất chỉ số `3`. Đây vẫn là lỗi *off-by-one*. Chỉ kiểm tra chương trình “không bị crash” là chưa đủ để chứng minh tính đúng.

### 4.3. Đếm số vòng lặp theo khoảng

Với vòng `for i in range(l,r)`, số lần chạy là `r-l` nếu `0<=l<=r`; nếu muốn thực hiện **cả** `r`, phải dùng cận kết thúc `r+1` và bảo đảm chỉ số `r` hợp lệ.

**Mẹo kiểm tra:** viết ra tập chỉ số của một ví dụ có `n=3` và một ví dụ có `n=0`. Nếu vòng lặp đúng cho cả hai, khả năng gặp lỗi biên giảm đáng kể.

## 5. Duyệt ngược: cẩn thận với số nguyên không dấu

Để duyệt từ phần tử cuối về đầu, ta muốn các chỉ số `n-1,n-2,\ldots,0`.

Trong Python:

```python
values = [2, 4, 6, 8]
for i in range(len(values) - 1, -1, -1):
    print(i, values[i])
# 3 8
# 2 6
# 1 4
# 0 2
```

Ở đây, cận dừng `-1` **không được lấy**, nên chỉ số `0` vẫn được duyệt. Nếu viết `range(n-1,0,-1)` thì sẽ **bỏ sót phần tử đầu**.

Trong C/C++, `size_t` thường là kiểu **số nguyên không dấu**. Vòng sau nguy hiểm:

```c
/* SAI: i >= 0 luôn đúng với size_t. */
for (size_t i = n - 1; i >= 0; --i) {
    use(a[i]);
}
```

Khi `n=0`, biểu thức `n-1` có thể tràn vòng về một giá trị rất lớn. Khi `i=0` rồi giảm tiếp, `i` quay vòng về giá trị lớn nhất; điều kiện `i>=0` vẫn đúng và có nguy cơ truy cập sai.

Một cách an toàn, kể cả khi `n=0`:

```c
for (size_t i = n; i > 0; ) {
    --i;
    use(a[i]);
}
```

Hoặc trong C++:

```cpp
for (std::size_t i = values.size(); i-- > 0; ) {
    use(values[i]);
}
```

Biến `i` bắt đầu tại **cận sau cuối** `n`, giảm trước khi đọc, nên không bao giờ cần một chỉ số âm. Ví dụ C++ thứ hai dựa vào quy tắc toán tử giảm hậu tố; trong mã dành cho người mới học, phiên bản giảm trước khi truy cập thường dễ đọc hơn.

## 6. Chèn và xóa: điều kiện hợp lệ khác nhau đúng một đơn vị

Cho mảng dài `n`, thao tác chèn vào vị trí `i` và thao tác xóa phần tử tại `i` **không có cùng miền chỉ số**.

### Chèn trước vị trí i

Chèn vào `i` hợp lệ khi:

\[
\boxed{0\le i\le n.}
\]

Cho phép `i=n` vì đó là thêm vào cuối, **không phải đọc phần tử `A[n]`**. Nếu dùng bộ đệm cố định, còn cần `n<capacity`.

Nếu chèn tại `i<n` và phải giữ thứ tự, ta dịch `n-i` phần tử sang phải. Phải dịch **từ phải sang trái** để không ghi đè nguồn:

```text
Trước:  [10, 20, 30, 40, __]  n=4
Chèn 7 tại i=2:
        [10, 20, 30, 40, 40]  dịch 40
        [10, 20, 30, 30, 40]  dịch 30
        [10, 20,  7, 30, 40]  ghi giá trị mới, n=5
```

Giả mã an toàn cho bộ đệm có đủ chỗ:

```text
INSERT(A, n, capacity, i, value)
    require 0 <= i <= n
    require n < capacity
    for j = n down to i+1:
        A[j] = A[j-1]
    A[i] = value
    n = n+1
    return n
```

Nếu viết điều kiện vòng lặp `j >= i` rồi luôn đọc `A[j-1]`, khi `i=0` có thể đọc `A[-1]` hoặc xảy ra tràn số nguyên không dấu. Cận đúng của vòng sao chép là **`j > i`**.

### Xóa tại vị trí i

Xóa phần tử hiện có chỉ hợp lệ khi:

\[
\boxed{0\le i<n.}
\]

Để giữ thứ tự, cần dịch `n-i-1` phần tử sang trái, **từ trái sang phải**:

```text
DELETE(A, n, i)
    require 0 <= i < n
    removed = A[i]
    for j = i to n-2:
        A[j] = A[j+1]
    n = n-1
    return n, removed
```

Đừng nhầm số phần tử dịch khi xóa với `n-i`: ô `i` là vị trí đang bị xóa, chỉ các ô phía sau `i+1,...,n-1` mới phải chuyển, tổng cộng `n-i-1` ô.

| Thao tác trên mảng dài `n=5` | Chỉ số nhỏ nhất hợp lệ | Chỉ số lớn nhất hợp lệ | Số phần tử dịch nếu ở cuối |
|---|---:|---:|---:|
| Chèn | `0` | `5` | `0` với `i=5` |
| Xóa | `0` | `4` | `0` với `i=4` |
| Đọc/ghi phần tử có sẵn | `0` | `4` | Không cần dịch |

Lỗi biên trong chèn/xóa thường đi kèm lỗi **quên cập nhật độ dài logic**. Nếu đã chèn thành công nhưng `n` vẫn là độ dài cũ, phần tử mới có thể không xuất hiện trong lần duyệt sau; nếu xóa nhưng không giảm `n`, vùng dữ liệu cũ có thể bị xử lý thêm lần nữa.

## 7. Tìm kiếm nhị phân: phân biệt chỉ số phần tử và ranh giới

Tìm kiếm nhị phân là nơi lỗi lệch một đơn vị rất dễ xảy ra: có thể sai khi chọn `mid`, cập nhật cận, hoặc đọc kết quả `n` như phần tử.

Hãy dùng thuật toán tìm **cận trái** (*lower bound*) trên mảng **đã sắp không giảm**. Kết quả là chỉ số đầu tiên có giá trị `>= target`, hoặc `n` nếu không có phần tử nào thỏa:

```python
def lower_bound(values: list[int], target: int) -> int:
    left, right = 0, len(values)   # Đoạn cần xét [left, right)

    while left < right:
        mid = left + (right - left) // 2
        if values[mid] < target:
            left = mid + 1
        else:
            right = mid
    return left


values = [2, 4, 4, 7, 9]
print(lower_bound(values, 4))   # 1
print(lower_bound(values, 5))   # 3: vị trí chèn 5
print(lower_bound(values, 12))  # 5: ranh giới sau cuối
print(lower_bound([], 12))      # 0: ranh giới sau cuối mảng rỗng
```

Giữ bất biến `0<=left<=right<=n`. Khi `left<right`, `mid<right<=n` nên `mid<n` và phép đọc `values[mid]` là hợp lệ. Mỗi lần lặp đoạn còn lại thu hẹp và cuối cùng `left==right`.

Nếu muốn **kiểm tra tồn tại**, không được đọc `values[pos]` trước khi xét `pos<n`:

```python
def contains_sorted(values: list[int], target: int) -> bool:
    pos = lower_bound(values, target)
    return pos < len(values) and values[pos] == target


print(contains_sorted([2, 4, 4, 7, 9], 12))  # False
```

Trả về `n` từ hàm tìm cận **không phải lỗi**: nó là đáp án hợp lệ của bài toán tìm **ranh giới**. Lỗi chỉ xuất hiện nếu người gọi nhầm nó thành chỉ số **phần tử**.

### Vì sao các biến thể nhị phân cần nhất quán?

Hai cách biểu diễn đoạn tìm kiếm thường gặp:

- **Nửa kín** `[left,right)`: bắt đầu với `right=n`; lặp khi `left<right`.
- **Đóng** `[left,right]`: thường bắt đầu với `right=n-1`; lặp khi `left<=right` và phải xử lý `n=0` cẩn thận.

Không thể lấy `right=n` của phiên bản nửa kín rồi dùng phép truy cập biên của phiên bản đóng mà không sửa công thức. Khi triển khai, hãy chọn **một quy ước** và kiểm tra bất biến sau mỗi lần cập nhật cận.

## 8. Lát cắt và sao chép đoạn: số phần tử phải khớp

Cho mảng `A` có `n` phần tử. Muốn sao chép đoạn `[l,r)`, phải kiểm tra:

\[
0\le l\le r\le n.
\]

Vùng đích cần đủ chỗ cho **`r-l` phần tử**. Vòng lặp theo chỉ số đoạn:

```python
def copy_interval(values: list[int], left: int, right: int) -> list[int]:
    n = len(values)
    if not (0 <= left <= right <= n):
        raise IndexError("Khoảng không hợp lệ")

    result = []
    for i in range(left, right):
        result.append(values[i])
    return result


source = [10, 20, 30, 40, 50]
print(copy_interval(source, 1, 4))  # [20, 30, 40]
print(copy_interval(source, 5, 5))  # []
```

Ví dụ đáng chú ý là `[n,n)`: đây là **đoạn rỗng hợp lệ**, mặc dù `A[n]` không hợp lệ nếu đọc như một phần tử. Hàm sao chép không bao giờ đọc `A[n]` vì `range(n,n)` không có phần tử nào.

### Python slice có quy tắc mềm hơn phép truy cập chỉ số

Trong Python:

```python
values = [10, 20, 30]
print(values[1:100])  # [20, 30] — stop được giới hạn về cuối
print(values[100:])   # [] — lát cắt rỗng

# print(values[100])  # IndexError — truy cập phần tử khác với lấy slice
```

Python cho phép cận slice vượt phạm vi và tự điều chỉnh. Đây là hành vi tiện lợi **đặc thù của API**, không có nghĩa chỉ số vượt biên là hợp lệ trong thuật toán tổng quát, trong C/C++ hoặc trong mọi thư viện.

Một số API dùng **cận đóng** hoặc **độ dài đoạn** thay vì `stop`. Ví dụ `slice(start,count)` và `slice(start,stop)` có ý nghĩa khác nhau nếu `count!=stop`. Luôn kiểm tra hợp đồng của hàm: tham số thứ hai là **vị trí kết thúc** hay **số phần tử cần lấy**?

## 9. Mảng nhiều chiều: mỗi chiều có giới hạn riêng

Với ma trận chữ nhật `R` hàng, `C` cột và quy ước bắt đầu từ `0`, tọa độ hợp lệ là:

\[
\boxed{0\le i<R\quad\text{và}\quad 0\le j<C.}
\]

Ví dụ:

```text
M (2 hàng × 3 cột):

          c0   c1   c2
     r0  11   12   13
     r1  21   22   23
```

`M[1][2]=23` hợp lệ. `M[2][0]` không hợp lệ vì hàng `2` vượt biên; `M[1][3]` không hợp lệ vì cột `3` vượt biên. **Độ dài của mỗi chiều không phải chỉ số cuối của chiều ấy.**

Khi trải phẳng theo hàng:

\[
k=iC+j,\qquad 0\le k<RC.
\]

Nếu đặt `i=R`, công thức vẫn cho một số `k`, nhưng không có nghĩa tọa độ hợp lệ. Chẳng hạn `R=2, C=3`, `i=0, j=3` cho `k=3`, trùng vị trí phẳng của `M[1][0]`. Nếu chỉ kiểm tra `0<=k<RC` mà bỏ qua điều kiện `j<C`, chương trình có thể âm thầm đọc **sai ô** thay vì báo lỗi.

Do đó phải kiểm tra **từng chiều** trước khi chuyển tọa độ sang chỉ số phẳng. Với mảng răng cưa có hàng dài khác nhau, điều kiện cột phải là `0<=j<len(rows[i])`, không phải so với một số cột chung.

### Chú ý tràn số khi tính tổng ô và offset

Trong ngôn ngữ dùng kiểu số nguyên giới hạn, các tích `R*C`, `i*C` hoặc `(i*C+j)*sizeof(T)` có thể tràn. Kiểm tra chỉ số hợp lệ không tự bảo đảm biểu thức tính byte offset không tràn. Cần dùng kiểu số phù hợp và xác minh phép nhân/cộng trước khi cấp phát hay truy cập.

## 10. C và C++: vượt biên có thể không báo lỗi ngay

Khác với Python `list` thường ném `IndexError` khi truy cập sai, biểu thức truy cập trực tiếp trên mảng C hoặc toán tử `operator[]` của nhiều cấu trúc C++ **không thực hiện kiểm tra biên tự động**.

```c
int a[3] = {10, 20, 30};

/* SAI: a chỉ có chỉ số 0, 1, 2. */
int wrong = a[3];   /* Hành vi không xác định (undefined behavior). */
```

Với C/C++, truy cập ngoài đối tượng có thể dẫn đến **hành vi không xác định** (*undefined behavior*, UB): chương trình có thể chạy mà không báo lỗi, trả dữ liệu vô nghĩa, bị crash, làm hỏng dữ liệu khác, hoặc bị trình biên dịch tối ưu hóa theo giả định truy cập đúng. Không được dựa vào việc “chạy thử thấy được giá trị” để kết luận truy cập an toàn.

Trong C++:

```cpp
#include <vector>
#include <stdexcept>

std::vector<int> data{10, 20, 30};
// data[3]       // Sai phạm vi, không được truy cập.
// data.at(3)    // Ném std::out_of_range.

if (index < data.size()) {
    int value = data.at(index);
    use(value);
}
```

Ví dụ giả định `index` là kiểu **không dấu** (`std::size_t`). Nếu `index` là kiểu có dấu và có thể âm, phải kiểm tra `index>=0` trước khi so sánh hay chuyển kiểu. Dùng `at()` khi cần phát hiện truy cập sai qua ngoại lệ, nhưng kiểm tra hợp đồng đầu vào vẫn quan trọng.

### Con trỏ trỏ ngay sau cuối không phải con trỏ tới phần tử

Với mảng C dài `n`, việc hình thành **con trỏ ngay sau phần tử cuối** có vai trò trong các vòng lặp:

```c
int a[3] = {10, 20, 30};
int *begin = a;
int *end = a + 3; /* Hợp lệ để làm ranh giới. */

for (int *p = begin; p != end; ++p) {
    use(*p);      /* p luôn trỏ tới phần tử khi giải tham chiếu. */
}

/* *end: KHÔNG hợp lệ — con trỏ end không trỏ tới phần tử. */
```

Một con trỏ *one-past-the-end* có thể dùng để so sánh hoặc làm điểm dừng trong phạm vi cho phép; **không được giải tham chiếu** nó.

### Nhầm `sizeof` với số phần tử

`sizeof(a)` đối với mảng C thực sự trả về **kích thước tính theo byte**, không phải số phần tử:

```c
int a[5] = {0, 1, 2, 3, 4};
size_t count = sizeof a / sizeof a[0]; /* 5 phần tử */
```

Công thức này dùng khi `a` thực sự có kiểu **mảng** tại vị trí biểu thức `sizeof`. Nếu truyền `a` vào hàm nhận `int *`, thông tin độ dài có thể đã mất; `sizeof(pointer)/sizeof(pointer[0])` **không** trả về độ dài mảng gốc. Hãy truyền độ dài riêng hoặc dùng một cấu trúc mang theo thông tin kích thước.

## 11. Kiểm tra biên an toàn trước khi cộng offset và độ dài

Giả sử một API nhận:

- `offset`: vị trí bắt đầu;
- `count`: số phần tử muốn đọc;
- `n`: độ dài mảng.

Yêu cầu logic là đoạn `[offset, offset+count)` nằm trọn trong `[0,n)`, và `offset+count` có thể bằng `n`.

Điều kiện dễ nghĩ đến:

```text
offset + count <= n
```

Tuy nhiên, trong kiểu số nguyên giới hạn, **phép cộng có thể tràn trước khi so sánh**, đặc biệt khi dùng số nguyên không dấu. Để tránh điều đó, nếu các biến là số nguyên không âm:

\[
\boxed{offset\le n\quad\land\quad count\le n-offset.}
\]

Kiểm tra `offset<=n` **trước** để phép trừ `n-offset` không bị âm hoặc tràn kiểu không dấu.

```cpp
#include <cstddef>

bool valid_interval(std::size_t offset,
                    std::size_t count,
                    std::size_t length) {
    return offset <= length && count <= length - offset;
}

// (0, 0, 0) -> true : đoạn rỗng trong mảng rỗng.
// (5, 0, 5) -> true : đoạn rỗng ở cuối.
// (5, 1, 5) -> false: yêu cầu một phần tử sau cuối.
```

Trong Python, số nguyên thông thường không tràn kiểu cố định, nhưng vẫn cần kiểm tra biên để tránh truy cập logic sai:

```python
def valid_interval(offset: int, count: int, length: int) -> bool:
    return (
        length >= 0
        and 0 <= offset <= length
        and 0 <= count <= length - offset
    )


print(valid_interval(2, 3, 5))  # True: [2, 5)
print(valid_interval(5, 0, 5))  # True: đoạn rỗng
print(valid_interval(5, 1, 5))  # False
print(valid_interval(-1, 2, 5)) # False
```

Khi kiểm tra số byte để cấp phát, cần xét thêm **tràn phép nhân** `count*sizeof(T)`. Một chương trình phải bảo đảm các phép tính kích thước nằm trong giới hạn của kiểu số và vùng nhớ cho phép trước khi thực hiện cấp phát.

## 12. Chỉ số âm và sentinel: “-1” có thể gây nhầm nghĩa

Nhiều thuật toán tự quy ước trả về `-1` khi tìm không thấy phần tử. Quy ước này thông dụng nhưng có rủi ro nếu đem kết quả đi truy cập mảng mà không kiểm tra.

Trong Python:

```python
names = ["An", "Bình", "Chi"]
found = -1  # Quy ước của thuật toán tìm kiếm: không tìm thấy

print(names[found])  # "Chi" — không có ngoại lệ!
```

Python cho phép chỉ số âm để đếm ngược, nên `names[-1]` thực sự là phần tử cuối. Nếu hàm tìm kiếm dùng `-1` làm sentinel, người gọi phải kiểm tra `found != -1` **trước** khi lấy phần tử.

Một API an toàn hơn trong Python là trả về `None` khi không tìm thấy:

```python
def find_first(values: list[int], target: int) -> int | None:
    for i, value in enumerate(values):
        if value == target:
            return i
    return None


position = find_first([3, 6, 9], 7)
if position is not None:
    print("Giá trị:", [3, 6, 9][position])
else:
    print("Không tìm thấy")
```

Một số thư viện dùng ranh giới `n` hoặc một iterator `end` để diễn đạt “không tìm thấy”. Dù chọn sentinel nào, hợp đồng hàm phải nói rõ **khi nào kết quả là chỉ số phần tử và khi nào chỉ là trạng thái**.

## 13. Thay đổi mảng trong lúc duyệt

Ngay cả khi vòng lặp ban đầu dùng giới hạn đúng, thao tác chèn/xóa trong quá trình duyệt có thể làm độ dài và ý nghĩa các chỉ số thay đổi.

Ví dụ, xóa những số chẵn:

```python
values = [2, 4, 6, 7]

# Sai nếu mục tiêu là xóa hết số chẵn.
for value in values:
    if value % 2 == 0:
        values.remove(value)

print(values)  # [4, 7] — bỏ sót số 4
```

Khi xóa `2`, phần tử `4` dịch sang vị trí `0` trong khi bộ duyệt đã tiến tới vị trí tiếp theo; phần tử `4` bị bỏ qua.

Một giải pháp an toàn là **tạo danh sách mới** từ những phần tử muốn giữ:

```python
values = [2, 4, 6, 7]
values = [value for value in values if value % 2 != 0]
print(values)  # [7]
```

Hoặc dùng một vòng lặp chỉ số với bất biến rõ ràng:

```python
values = [2, 4, 6, 7]
i = 0

while i < len(values):
    if values[i] % 2 == 0:
        values.pop(i)   # Phần tử sau dịch về chỉ số i, chưa tăng i.
    else:
        i += 1          # Chỉ tăng khi giữ phần tử hiện tại.

print(values)  # [7]
```

Cách `pop(i)` có thể dịch `O(n)` phần tử, nên vòng lặp xóa nhiều phần tử có thể tốn `O(n²)` thời gian. Lọc sang danh sách mới thường `O(n)` thời gian và thêm `O(n)` bộ nhớ. Bài học chính không phải “luôn dùng một cách”, mà là phải tính **thay đổi độ dài và chỉ số sau mỗi thao tác**.

## 14. Bất biến vòng lặp: cách kiểm chứng chứ không chỉ sửa lỗi

Một phương pháp đáng tin cậy là viết **bất biến** (*loop invariant*) mô tả điều luôn đúng trước/sau mỗi lần lặp.

Ví dụ, tính tổng mảng:

```python
def sum_array(values: list[int]) -> int:
    total = 0
    i = 0

    while i < len(values):
        total += values[i]
        i += 1
    return total
```

Bất biến ở đầu mỗi vòng:

\[
0\le i\le n,\qquad total=\sum_{j=0}^{i-1}A[j].
\]

Ta có ba bước lập luận:

1. **Khởi tạo:** `i=0`, tổng đoạn rỗng bằng `0`; bất biến đúng.
2. **Duy trì:** nếu `i<n` thì `A[i]` hợp lệ. Cộng nó vào `total` và tăng `i` khiến tổng trở thành tổng của `[0,i+1)`.
3. **Kết thúc:** điều kiện `i<n` sai trong khi bất biến còn đúng, nên `i=n` và `total` là tổng toàn bộ `[0,n)`.

Nếu vô tình đổi điều kiện thành `i<=n`, tại `i=n` vòng lặp vẫn chạy nhưng phép đọc `A[i]` vi phạm bất biến truy cập `i<n`. Nếu kết thúc ở `i<n-1`, thuật toán không cộng đủ phần tử cuối.

Nhờ bất biến, ta không chỉ phát hiện một đầu vào sai, mà còn có thể giải thích **vì sao** điều kiện vòng lặp cần đúng như vậy đối với mọi `n` hợp lệ.

## 15. Kiểm thử biên theo kích thước và vị trí

Các lỗi lệch một đơn vị thường không xuất hiện khi chỉ chạy thử với mảng dài và thao tác ở giữa. Nên thiết kế ca kiểm thử theo **phân hoạch biên**:

| Kích thước hoặc vị trí | Cần kiểm thử | Lý do |
|---|---|---|
| `n=0` | Duyệt, tìm, chèn đầu, xóa/đọc bị từ chối | Không có chỉ số phần tử hợp lệ |
| `n=1` | Đọc `0`, tìm thấy/không thấy, xóa cuối | Chỉ số đầu cũng là chỉ số cuối |
| `n=2` | Đọc cả hai vị trí, duyệt tiến/lùi | Dễ nhận ra bỏ sót đầu hoặc cuối |
| `i=0` | Đọc/chèn/xóa đầu | Tránh đọc `i-1` khi `i=0` |
| `i=n-1` khi `n>0` | Đọc/xóa cuối | Không có phần tử `i+1` |
| `i=n` | Chèn cuối hợp lệ; đọc/xóa không hợp lệ | Phân biệt cận với phần tử |
| `i=-1` | API có chỉ số âm hay không? | Ngữ nghĩa khác nhau giữa ngôn ngữ |
| `[l,l)` | Lát cắt rỗng | Số phần tử phải bằng `0` |
| `[0,n)` | Lát cắt cả mảng | Số phần tử phải bằng `n` |
| `[n,n)` | Lát cắt rỗng ở cuối | Không được đọc `A[n]` |
| `offset=n, count=1` | Phải bị từ chối | Bắt đầu sau phần tử cuối |
| `capacity=n` | Chèn cần mở rộng hoặc từ chối | Không còn chỗ vật lý cho phần tử mới |

### Ví dụ kiểm thử với Python

```python
def first_index(values: list[int], target: int) -> int | None:
    for i in range(len(values)):
        if values[i] == target:
            return i
    return None


assert first_index([], 9) is None
assert first_index([9], 9) == 0
assert first_index([9], 1) is None
assert first_index([1, 9], 9) == 1
assert first_index([9, 1], 9) == 0
assert first_index([9, 9], 9) == 0

assert copy_interval([1, 2, 3], 0, 3) == [1, 2, 3]
assert copy_interval([1, 2, 3], 3, 3) == []

assert lower_bound([], 5) == 0
assert lower_bound([1, 3, 5], 6) == 3
assert lower_bound([1, 3, 3, 5], 3) == 1
```

Đoạn kiểm thử giả định các hàm `copy_interval` và `lower_bound` đã được định nghĩa như trong các phần trước. Trường hợp giá trị trùng `[9,9]` đặc biệt hữu ích để kiểm tra hợp đồng “trả **vị trí đầu tiên**”, chứ không chỉ “tìm một vị trí bất kỳ”.

### Một vài thuộc tính có thể kiểm tra tự động

Ngoài các ví dụ cố định, có thể kiểm tra các quan hệ đúng với mọi dữ liệu hợp lệ:

- Với mọi `A`, `copy_interval(A,0,len(A))` phải bằng `A` về giá trị.
- Với mọi `0<=l<=r<=len(A)`, độ dài lát cắt phải bằng `r-l`.
- Nếu `lower_bound` trả `p` trên mảng không giảm, mọi phần tử trước `p` phải `<target`, còn mọi phần tử từ `p` trở đi phải `>=target`.
- Sau khi chèn vào vị trí `i`, độ dài mới là `n+1`; sau khi xóa, độ dài mới là `n-1`.

Kiểm thử dựa trên thuộc tính (*property-based testing*) rất hữu ích để sinh ra nhiều độ dài, vị trí và giá trị sát ranh giới.

## 16. Hậu quả an toàn và cách phòng tránh

Trong môi trường có kiểm tra biên, lỗi thường biểu hiện dưới dạng ngoại lệ, giúp dừng thao tác sai. Trong môi trường thao tác bộ nhớ trực tiếp, một truy cập vượt biên có thể đọc/ghi vào vùng nhớ không thuộc đối tượng. Đây là một lỗi **an toàn bộ nhớ** (*memory safety*) có thể gây hỏng dữ liệu, crash hoặc tạo lỗ hổng bảo mật.

Những thói quen giúp giảm rủi ro:

1. Xác định rõ độ dài `n` và miền `[0,n)` trước khi viết mã.
2. Đặt tên `start`, `end_exclusive`, `count`, `last_index` để phân biệt ý nghĩa.
3. Kiểm tra điều kiện trước khi đọc `A[i]`; đừng suy đoán từ sức chứa.
4. Ưu tiên vòng lặp theo tập phần tử hoặc iterator an toàn nếu không cần tự tính chỉ số.
5. Giữ một quy ước khoảng nhất quán, đặc biệt trong tìm kiếm nhị phân.
6. Với kích thước không dấu, tránh `n-1` nếu chưa biết `n>0` và tránh điều kiện `i>=0` khi duyệt ngược.
7. Kiểm tra tràn số khi tính `offset+count`, `n*sizeof(T)` hoặc các tích nhiều chiều.
8. Kiểm thử mảng rỗng, một phần tử, đầu/cuối, độ dài cực lớn và dữ liệu thay đổi trong lúc duyệt.
9. Với C/C++, tận dụng cảnh báo trình biên dịch, công cụ kiểm tra biên, AddressSanitizer hoặc UndefinedBehaviorSanitizer trong môi trường phát triển khi có thể.

**Công cụ kiểm tra không thay thế lập luận biên.** Một chương trình vượt qua nhiều bài thử vẫn có thể chứa lỗi ở nhánh hiếm hoặc với kích thước không được kiểm thử.

## 17. Tình huống thực tế: phân trang một danh sách

Một dịch vụ có `n=23` bản ghi và muốn trả về trang thứ `p` (bắt đầu từ `0`), mỗi trang chứa tối đa `page_size=10` bản ghi. Ta có:

\[
start=p\times page\_size,\qquad
end=\min(start+page\_size,n).
\]

Nếu `start>=n`, trang không chứa bản ghi nào. Với `p=2`:

```text
Các trang:
Trang 0 -> chỉ số [0, 10)  -> 10 bản ghi
Trang 1 -> chỉ số [10, 20) -> 10 bản ghi
Trang 2 -> chỉ số [20, 23) ->  3 bản ghi
Trang 3 -> chỉ số [30, 30) ->  0 bản ghi
```

Hàm Python sau thể hiện cách dùng slice của `list`:

```python
def get_page(records: list[str], page: int, page_size: int) -> list[str]:
    if page < 0 or page_size <= 0:
        raise ValueError("Trang phải không âm, kích thước trang phải dương")

    start = page * page_size
    if start >= len(records):
        return []
    end = min(start + page_size, len(records))
    return records[start:end]


items = [f"item-{i}" for i in range(23)]
print(len(get_page(items, 2, 10)))  # 3
print(len(get_page(items, 3, 10)))  # 0
```

Nếu nhầm `end` là chỉ số cuối **được lấy**, lập trình viên có thể dùng `end+1` và trả dư một phần tử cho trang chưa đầy. Nếu tính `end=n-1` rồi dùng `records[start:end]`, lại bỏ mất bản ghi cuối. Quy ước `[start,end)` giúp số phần tử trả về luôn bằng `end-start`.

Trong C/C++ hoặc hệ thống có kiểu số nguyên giới hạn, phép nhân `page*page_size` cũng cần được kiểm soát để tránh tràn trước khi tính `start`. Ví dụ trên dùng số nguyên Python có độ chính xác tùy ý nên không gặp loại tràn cố định này.

## 18. Bài tập tự kiểm tra

**Bài 1.** Cho `A=[5,10,15,20,25,30]`. Độ dài là bao nhiêu? Chỉ số đầu, chỉ số cuối và cận ngay sau cuối lần lượt là gì? `A[6]` có hợp lệ không?

**Bài 2.** Với `A=[1,2,3,4]`, hãy cho biết vòng `for i in range(len(A)-1)` duyệt những chỉ số nào. Nếu muốn xử lý mọi phần tử, phải sửa ra sao?

**Bài 3.** Đoạn `[2,5)` có bao nhiêu phần tử? Còn đoạn đóng `[2,5]` có bao nhiêu phần tử? Hai đoạn khác nhau ở chỉ số nào?

**Bài 4.** Với mảng rỗng `B=[]`, những thao tác nào là hợp lệ: đọc `B[0]`, lấy lát cắt `B[0:0]`, chèn một phần tử ở vị trí `0`, xóa phần tử vị trí `0`?

**Bài 5.** Mảng dài `n=7` có đủ sức chứa. Chèn phần tử mới tại `i=2` cần dịch bao nhiêu phần tử? Xóa phần tử tại `i=2` cần dịch bao nhiêu phần tử?

**Bài 6.** Viết điều kiện lặp ngược an toàn với `size_t i` trong C/C++ cho mảng `n` phần tử. Vì sao `i>=0` không phải điều kiện dừng phù hợp?

**Bài 7.** Mảng đã sắp `C=[1,3,6,8]`. `lower_bound(C,9)` trả về gì? Phải kiểm tra điều gì trước khi dùng kết quả làm chỉ số phần tử?

**Bài 8.** Ma trận `2×3` có các chỉ số hợp lệ nào cho hàng và cột? Vì sao tọa độ `(0,3)` sai, dù công thức row-major cho chỉ số phẳng `3` nằm trong `[0,6)`?

**Bài 9.** Với một vùng đệm `length=10` và bộ đôi `offset=9, count=2`, yêu cầu đọc có hợp lệ không? Hãy dùng điều kiện an toàn tránh tràn `offset<=length && count<=length-offset`.

**Bài 10.** Xét đoạn Python `values=[2,4,6]; for x in values: if x%2==0: values.remove(x)`. Sau khi chạy, liệu tất cả phần tử chẵn đã bị xóa chưa? Nêu một cách sửa.

**Bài 11.** Một hàm trả `-1` nếu không tìm thấy. Vì sao phép đọc `data[result]` có thể im lặng trả sai phần tử trong Python? Nêu cách tránh.

**Bài 12.** Một API có tham số `start=3` và `count=4`. Nếu quy ước bắt đầu từ `0` và dữ liệu có ít nhất `7` phần tử, các chỉ số được chọn là gì? Vì sao không nên hiểu `count` là chỉ số kết thúc?

### Đáp án và giải thích

1. `n=6`, chỉ số đầu `0`, cuối `5`, cận sau cuối `6`. `A[6]` không hợp lệ để đọc.
2. Duyệt `0,1,2` và bỏ sót chỉ số `3`. Sửa thành `range(len(A))` hoặc duyệt trực tiếp qua các phần tử.
3. `[2,5)` gồm `2,3,4` nên có `3` phần tử. `[2,5]` gồm `2,3,4,5` nên có `4` phần tử; khác nhau ở chỉ số `5`.
4. `B[0]` và xóa ở vị trí `0` không hợp lệ; `B[0:0]` hợp lệ và rỗng; chèn ở vị trí `0` hợp lệ nếu có thể mở rộng vùng chứa.
5. Chèn: `7-2=5` phần tử. Xóa: `7-2-1=4` phần tử.
6. Ví dụ `for (size_t i=n; i>0; ) { --i; use(a[i]); }`. Kiểu `size_t` không dấu nên `i>=0` luôn đúng và giảm `0` có thể quay vòng.
7. Trả `4=n`, là vị trí chèn cuối. Phải kiểm tra `pos<n` trước khi truy cập `C[pos]`; ở đây `9` không tồn tại.
8. Chỉ số hàng `0,1`, cột `0,1,2`. `j=3` vượt cột mặc dù phép tính `0×3+3=3` tình cờ trỏ đến ô `(1,0)` trong biểu diễn phẳng; kiểm tra chỉ số phẳng đơn lẻ không đủ.
9. Không hợp lệ vì `9<=10` đúng nhưng `2<=10-9=1` sai.
10. Không. Xóa trong lúc duyệt có thể bỏ qua phần tử vừa dịch sang vị trí đã duyệt. Sửa bằng lọc sang danh sách mới hoặc dùng `while` và chỉ tăng chỉ số khi giữ phần tử.
11. Trong Python, `data[-1]` là phần tử cuối, nên có thể trả sai thay vì báo không tìm thấy. Kiểm tra `result!=-1` hoặc dùng `None` làm trạng thái không tìm thấy.
12. Chọn `3,4,5,6`, tương ứng khoảng `[3,7)`. `count` là **số lượng** chứ không phải cận `stop`.

## 19. Ghi nhớ

Với mảng dài `n`, **độ dài** là số phần tử, **chỉ số cuối** là `n-1` chỉ khi `n>0`, còn **`n` là cận ngay sau cuối**, không phải một phần tử có thể đọc. Quy tắc truy cập cơ bản là **`0<=i<n`**; chèn ở ranh giới cuối có thể cho phép **`i=n`**, nhưng xóa không cho phép. Khoảng nửa kín **`[l,r)`** giúp số phần tử bằng `r-l` và xử lý đoạn rỗng dễ dàng. Để tránh lỗi vượt biên và lệch một đơn vị, cần nhất quán quy ước khoảng, kiểm tra trường hợp rỗng, cẩn trọng khi duyệt ngược bằng số không dấu, phân biệt độ dài với sức chứa và dùng bất biến vòng lặp cùng kiểm thử biên. Đây là nền tảng của cả **tính đúng đắn**, **an toàn bộ nhớ** và phân tích thao tác trên mảng.

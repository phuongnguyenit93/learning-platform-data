# Truy vấn đoạn, tìm theo tổng tích lũy và điều kiện cần

Một kho hàng lưu số sản phẩm còn lại ở mỗi ngăn. Nhân viên thường hỏi **“Tổng số sản phẩm trong các ngăn từ l đến r là bao nhiêu?”**, đồng thời hệ thống cần biết **“Sản phẩm thứ k trong thứ tự quét các ngăn đang nằm ở ngăn nào?”**. Sau mỗi lần nhập hoặc xuất hàng, số lượng ở một ngăn thay đổi, và những câu hỏi tiếp theo phải dùng ngay dữ liệu mới.

**Cây Fenwick** (*Fenwick tree*, *Binary Indexed Tree* — BIT) giúp xử lý cả **cập nhật một điểm** và **truy vấn tổng đoạn** trong O(log n). Đặc biệt, khi **mọi số lượng hiện tại đều không âm**, ta có thể tìm **biên tiền tố đầu tiên đạt một ngưỡng tổng tích lũy** bằng kỹ thuật *binary lifting* trực tiếp trên BIT, cũng trong O(log n).

Nhưng hai thao tác này có **những điều kiện khác nhau**:

- **Tính tổng đoạn** bằng hiệu hai tổng tiền tố vẫn đúng khi có **số âm**, bởi phép cộng có nghịch đảo là phép trừ.
- **Tìm biên theo tổng tích lũy** bằng phương pháp Fenwick chuẩn cần tổng tiền tố **không giảm**. Trong số học chính xác, điều đó tương đương với **mọi phần tử của mảng đều không âm**.
- Nếu muốn tìm **vị trí của phần tử thứ k theo tần suất**, cần tần suất là **số nguyên không âm** và `k` là thứ tự hợp lệ.
- Một phép tổng hợp bất kỳ như min hoặc ghép chuỗi không thể tự thay thế vào công thức hiệu hai tiền tố.

Bài thuộc chương **Truy vấn đoạn** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, xây nền tảng cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị. Tinh thần xuyên suốt là xác định **bất biến, thao tác và độ phức tạp thời gian/bộ nhớ** trước khi chọn cấu trúc. Trọng tâm của bài này là phân biệt rõ **điều kiện cần cho truy vấn tổng** với **điều kiện bảo đảm tính đúng khi tìm theo ngưỡng**.

## 1. Bài toán với hai loại câu hỏi

Cho mảng:

```text
a = [a[0], a[1], ..., a[n-1]]
```

Ta xét ba thao tác trực tuyến:

```text
point_add(pos, delta)
    a[pos] <- a[pos] + delta

range_sum(l, r)
    trả tổng trên [l,r)

first_prefix_at_least(target)
    tìm end nhỏ nhất sao cho
    a[0] + ... + a[end-1] >= target
```

Trong toàn bài, giao diện công khai dùng **0-based**, đoạn **nửa mở `[l,r)`**:

```text
0 <= l <= r <= n
0 <= pos < n
0 <= end <= n
```

Đặt:

```text
P[end] = a[0] + a[1] + ... + a[end-1]
P[0] = 0
```

Theo quy ước này:

```text
range_sum(l,r) = P[r] - P[l]
```

và câu hỏi tìm theo ngưỡng là:

```text
Tìm min {end thuộc [0,n] : P[end] >= target}.
```

Nếu tập chỉ số thỏa điều kiện rỗng, bài dùng giá trị trả về **None**.

**Chú ý phân biệt:** `end` là **số phần tử đầu tiên được lấy**, không phải chỉ số của phần tử cuối. Nếu câu hỏi yêu cầu **vị trí của đơn vị dữ liệu thứ k**, kết quả thường là `end-1`, không phải `end`.

## 2. Ví dụ xuyên suốt: dãy tần suất không âm

Lấy số sản phẩm ở tám ngăn:

```text
Chỉ số ngăn:  0  1  2  3  4  5  6  7
Số lượng:    2  0  3  1  0  4  2  0
```

Khi cộng dồn từ trái sang phải:

```text
end:          0  1  2  3  4  5   6   7   8
P[end]:       0  2  2  5  6  6  10  12  12
```

Bảng tiền tố:

| `end` | `P[end]` | Ý nghĩa |
|---:|---:|---|
| 0 | 0 | Chưa lấy ngăn nào |
| 1 | 2 | Ngăn 0 |
| 2 | 2 | Ngăn 0..1 |
| 3 | 5 | Ngăn 0..2 |
| 4 | 6 | Ngăn 0..3 |
| 5 | 6 | Ngăn 0..4 |
| 6 | 10 | Ngăn 0..5 |
| 7 | 12 | Ngăn 0..6 |
| 8 | 12 | Toàn bộ tám ngăn |

Một số kết quả:

- `range_sum(2,7)=3+1+0+4+2=10`.
- `range_sum(1,6)=0+3+1+0+4=8`.
- `first_prefix_at_least(7)=6` vì `P[5]=6<7` và `P[6]=10>=7`.
- Sản phẩm thứ 7 nằm ở **ngăn 5**, tức `end-1=5`.
- `first_prefix_at_least(13)=None` vì toàn bộ mảng chỉ có 12 sản phẩm.

Lưu ý tiền tố **không giảm nhưng không nhất thiết tăng nghiêm ngặt**. Các ngăn có số lượng 0 khiến `P[1]=P[2]` và `P[4]=P[5]`. Tìm ngưỡng phải xử lý chính xác các giá trị bằng nhau ấy.

## 3. Fenwick lưu những tổng con nào?

Cây Fenwick cho phép tính nhanh `P[end]` và sửa nhanh một phần tử mà không lưu mọi `P[end]`.

Bên trong BIT dùng **chỉ số từ 1**, dù mảng ngoài dùng 0-based:

```text
a[0]  <->  bit[1]
a[1]  <->  bit[2]
...
a[n-1] <-> bit[n]

bit[0] không sử dụng.
```

Định nghĩa với `i>0`:

```text
lowbit(i) = i & -i
```

`lowbit(i)` lấy **giá trị của bit 1 thấp nhất** trong biểu diễn nhị phân của i.

Bất biến tổng Fenwick:

```text
bit[i] = sum(a[i-lowbit(i) : i])
```

Nói cách khác, `bit[i]` chịu trách nhiệm một đoạn **0-based nửa mở** kết thúc tại biên phải `i`, dài đúng `lowbit(i)`.

### Bảng vùng phụ trách cho n=8

| `i` | `lowbit(i)` | Đoạn mảng ngoài | `bit[i]` với ví dụ |
|---:|---:|---|---:|
| 1 | 1 | `[0,1)` | 2 |
| 2 | 2 | `[0,2)` | 2 |
| 3 | 1 | `[2,3)` | 3 |
| 4 | 4 | `[0,4)` | 6 |
| 5 | 1 | `[4,5)` | 0 |
| 6 | 2 | `[4,6)` | 4 |
| 7 | 1 | `[6,7)` | 2 |
| 8 | 8 | `[0,8)` | 12 |

Biểu diễn:

```text
bit index:  0  1  2  3  4  5  6  7   8
bit value:  0  2  2  3  6  0  4  2  12
```

**Không phải `bit[6]` bằng `P[6]`**: `bit[6]=a[4]+a[5]=4`, trong khi `P[6]=10`.

Vì vậy, truy vấn tiền tố phải chọn và gộp **một số vùng không chồng lấn**, chứ không đọc một ô `bit[end]` cho mọi end.

## 4. Hai đường đi trái ngược của BIT

Từ bất biến, Fenwick có hai vòng lặp đối xứng.

### Truy vấn tiền tố: đi xuống

```text
prefix_sum(end):
    result = 0
    i = end
    while i > 0:
        result += bit[i]
        i -= lowbit(i)
    return result
```

Ở mỗi lần lặp, `bit[i]` chứa **đoạn cuối của phần tiền tố còn lại**. Sau khi cộng, `i-lowbit(i)` là biên phải mới của phần chưa xử lý.

### Cập nhật một điểm: đi lên

```text
point_add(pos, delta):
    i = pos + 1
    while i <= n:
        bit[i] += delta
        i += lowbit(i)
```

Vòng này sửa **mọi vùng BIT chứa phần tử ở vị trí pos**.

### Truy vết

Với ví dụ `n=8`, `prefix_sum(7)` đi qua:

```text
7 -> 6 -> 4 -> 0

bit[7] + bit[6] + bit[4]
= 2 + 4 + 6
= 12
```

Đúng với tổng `[0,7)`.

Nếu cộng thêm `3` vào ngăn ngoài `pos=5`, vòng update bắt đầu ở `i=6`:

```text
6 -> 8 -> 16 (dừng vì n=8)
```

Nó sửa `bit[6]` và `bit[8]`; những tổng tiền tố chứa vị trí 5 sẽ tự có kết quả mới.

| Thao tác | Chỉ số đầu | Bước nhảy | Dừng |
|---|---:|---|---|
| Cộng điểm tại `pos` | `pos+1` | `i += lowbit(i)` | `i>n` |
| Tổng tiền tố `P[end]` | `end` | `i -= lowbit(i)` | `i=0` |

**Không dùng `i=pos` cho cập nhật 0-based**: nếu `pos=0`, `lowbit(0)=0` và vòng lặp có thể không tiến.

## 5. Truy vấn đoạn: hiệu hai tổng tiền tố

Trước hết, Fenwick có thể hỏi `P[end]` trong O(log n), kể cả khi mảng có số âm.

Với `0<=l<=r<=n`:

```text
P[r] = a[0] + ... + a[l-1] + a[l] + ... + a[r-1]
P[l] = a[0] + ... + a[l-1]

P[r] - P[l] = a[l] + ... + a[r-1]
```

Vậy:

```text
range_sum(l,r) = prefix_sum(r) - prefix_sum(l)
```

### Truy vết `[2,7)`

Với `a=[2,0,3,1,0,4,2,0]`:

```text
P[7] = 12
P[2] = 2

sum([2,7)) = 12 - 2 = 10
```

Lấy tiền tố bằng BIT:

```text
P[7]:
    i=7, bit[7]=2
    i=6, bit[6]=4
    i=4, bit[4]=6
    Tổng = 12

P[2]:
    i=2, bit[2]=2
    Tổng = 2

Hiệu = 12-2 = 10
```

Tổng của đoạn rỗng:

```text
range_sum(l,l) = P[l]-P[l] = 0
```

Toàn mảng:

```text
range_sum(0,n) = P[n]-P[0] = P[n]
```

Nếu có hai tiền tố, ta không nhất thiết phải trừ từng phần tử gốc. Bản chất của kỹ thuật là **khử đúng phần đã cộng chung**.

## 6. Điều kiện đúng của phép lấy hiệu tiền tố

Công thức `P[r]-P[l]` hoạt động trên số nguyên, số hữu tỉ và những miền số học hỗ trợ phép cộng/trừ phù hợp.

Ở mức đại số:

- Phép **cộng** có tính kết hợp: `(x+y)+z=x+(y+z)`.
- Có phần tử đơn vị là `0`.
- Có phép **nghịch đảo**: `-x`, nên có thể bỏ tổng tiền tố trái.

**Không cần mọi `a[i]` không âm để hỏi tổng đoạn.** Các phần tử âm vẫn cộng và trừ bình thường.

Ví dụ:

```text
a = [5, -10, 10]

P = [0,5,-5,5]

sum([1,3)) = -10 + 10 = 0
P[3]-P[1] = 5-5 = 0
```

Công thức vẫn đúng dù `P` tăng rồi giảm.

### Không lấy hiệu hai prefix min

Giả sử:

```text
a = [1, 9, 5]
b = [1, 7, 8]
```

Hai dãy có cùng các min tiền tố không rỗng `[1,1,1]`, nhưng:

```text
min(a[1:3]) = 5
min(b[1:3]) = 7
```

Không thể suy ra min đoạn giữa chỉ từ hai min tiền tố. Phép min không có phép nghịch đảo tổng quát để “trừ” vùng trái.

**BIT tổng chuẩn không phải BIT min chỉ bằng cách thay dấu cộng bởi `min`.**

## 7. Tìm theo ngưỡng: định nghĩa đúng “đạt tổng tích lũy”

Bây giờ xét thao tác khác với tính tổng:

```text
first_prefix_at_least(target)
```

Ta muốn tìm:

```text
end_min = min {end : 0<=end<=n và P[end] >= target}
```

Nếu không tồn tại `end` như vậy, trả `None`.

Với dãy tần suất:

```text
a = [2,0,3,1,0,4,2,0]
P = [0,2,2,5,6,6,10,12,12]
```

Các câu hỏi:

| `target` | `end` đầu tiên đạt ngưỡng | Lý do |
|---:|---:|---|
| -2 | 0 | `P[0]=0>=-2` |
| 0 | 0 | Tiền tố rỗng đủ ngưỡng |
| 1 | 1 | `P[1]=2` |
| 2 | 1 | `P[1]=2`, không đợi đến end=2 |
| 3 | 3 | `P[2]=2<3`; `P[3]=5` |
| 5 | 3 | `P[3]=5` |
| 6 | 4 | `P[4]=6` |
| 7 | 6 | `P[5]=6<7`; `P[6]=10` |
| 10 | 6 | `P[6]=10` |
| 11 | 7 | `P[7]=12` |
| 12 | 7 | `P[7]=12` |
| 13 | `None` | Tổng toàn mảng chỉ 12 |

Từ `end=6` cho target=7, vị trí ngăn chứa **sản phẩm thứ 7** là:

```text
pos = end - 1 = 5
```

**Đừng nhầm:** phép tìm trả **biên tiền tố `end`**; bài toán “đơn vị thứ k” mới lấy `end-1` để nhận **chỉ số phần tử**.

## 8. Điều kiện then chốt: tổng tiền tố không giảm

Ta cần sử dụng tính chất:

```text
P[0] <= P[1] <= ... <= P[n]
```

Khi đó, với một `target` cố định, mệnh đề:

```text
P[end] >= target
```

là **sai ở một số biên ban đầu**, rồi **đúng từ một biên trở về sau**, không quay lại sai.

Đây là tính đơn điệu (*monotonicity*) cho phép dùng **binary search** hoặc **binary lifting**.

Mà:

```text
P[i+1] - P[i] = a[i]
```

nên trong số học chính xác:

```text
P không giảm
  <=> với mọi i: a[i] >= 0
```

Vì vậy, **không âm ở mọi vị trí** là điều kiện cần và đủ để **toàn bộ dãy tiền tố không giảm**.

### Không yêu cầu tăng nghiêm ngặt

Các số 0 không làm hỏng thuật toán:

```text
a = [2,0,3,1,0,4,2,0]
P = [0,2,2,5,6,6,10,12,12]
```

Dù nhiều giá trị P bằng nhau, ta vẫn có thể tìm **biên đầu tiên** thỏa `P[end]>=target`. Chỉ cần dùng so sánh **`< target` để bỏ qua những tiền tố chưa đạt**, thay vì `<= target`.

### Không âm là điều kiện cho bảo đảm chung, không phải một mẹo tùy chọn

Với một mảng có số âm, một truy vấn ngưỡng cụ thể đôi khi vẫn tình cờ được trả đúng. Nhưng ta **không thể bảo đảm** binary search/lifting chuẩn đúng cho mọi target.

Nếu bài toán cho phép giảm các số lượng thành âm, việc kiểm tra điều kiện phải áp dụng **sau mỗi cập nhật**, không chỉ khi xây BIT ban đầu.

## 9. Phản ví dụ rõ ràng khi có số âm

Xét:

```text
a = [5, -10, 10]
P = [0, 5, -5, 5]
```

Với `target=4`:

```text
P[0]=0 <4
P[1]=5 >=4     <- đáp án đầu tiên là end=1
P[2]=-5 <4
P[3]=5 >=4
```

Mệnh đề “đạt ngưỡng” có dạng:

```text
Sai, Đúng, Sai, Đúng
```

Nó **không đơn điệu**. Thuật toán tìm biên dựa trên một miền sai rồi một miền đúng không có căn cứ.

### Binary lifting sẽ sai như thế nào?

Với `n=3`, Fenwick của mảng này có:

```text
bit[1] = 5
bit[2] = 5 + (-10) = -5
bit[3] = 10
```

Thuật toán chuẩn thử bước lớn `step=2`:

```text
idx=0, acc=0
candidate=2, acc+bit[2]=-5 < 4
=> chấp nhận idx=2, acc=-5

step=1
candidate=3, acc+bit[3]=5 >= 4
=> không chấp nhận

Trả end=idx+1=3
```

Đáp án thật là **end=1**, nên kết quả 3 **sai**.

Không thể sửa lỗi chỉ bằng đổi `<` thành `<=`. Vấn đề nằm ở **điều kiện đơn điệu bị phá**, chứ không ở một dấu so sánh đơn lẻ.

## 10. Cách đơn giản: tìm bằng quét trực tiếp

Trước khi tối ưu, hãy có một bản thuật toán đúng trên cả mảng có số âm:

```python
def first_prefix_scan(values, target):
    """Tìm end đầu tiên có tổng tiền tố >= target, cho cả số âm."""
    if target <= 0:
        return 0

    running = 0

    for end, value in enumerate(values, start=1):
        running += value
        if running >= target:
            return end

    return None


assert first_prefix_scan([2, 0, 3, 1, 0, 4, 2, 0], 7) == 6
assert first_prefix_scan([5, -10, 10], 4) == 1
assert first_prefix_scan([5, -10, 10], 6) is None
assert first_prefix_scan([], 1) is None
assert first_prefix_scan([], 0) == 0
```

Độ phức tạp là **O(n)** thời gian trong trường hợp xấu nhất, O(1) bộ nhớ điều khiển.

Bản quét này vừa là lời giải đúng khi mảng có số âm, vừa là **oracle** để kiểm thử thuật toán Fenwick trên các dữ liệu thỏa điều kiện không âm.

## 11. Binary search ngoài Fenwick: đúng nhưng O(log² n)

Khi `P[end]` không giảm, ta có thể tìm biên bằng binary search:

1. Chọn `mid` của khoảng biên còn xét.
2. Tính `P[mid]` bằng `Fenwick.prefix_sum(mid)`.
3. Nếu `P[mid]>=target`, thu hẹp về nửa trái.
4. Nếu chưa đạt, chuyển sang nửa phải.

Số vòng tìm kiếm nhị phân là O(log n), nhưng **mỗi lần tính `P[mid]` mất O(log n)**. Do đó:

```text
O(log n) lần thử * O(log n) mỗi prefix
    = O(log² n)
```

### Mã tham khảo

```python
def first_prefix_by_binary_search(fw, target):
    """Tiền điều kiện: mọi fw.values[i] >= 0."""
    if fw.negative_count:
        raise ValueError("Tìm theo ngưỡng yêu cầu giá trị không âm")

    if target <= 0:
        return 0

    if target > fw.prefix_sum(fw.n):
        return None

    lo, hi = 0, fw.n

    while lo < hi:
        mid = (lo + hi) // 2

        if fw.prefix_sum(mid) >= target:
            hi = mid
        else:
            lo = mid + 1

    return lo
```

Hàm này dùng lớp `FenwickInt` sẽ được cài ở mục sau, trong đó `negative_count` được duy trì O(1) khi cập nhật một điểm.

**Binary search O(log² n) vẫn có thể đủ tốt**, nhưng Fenwick còn cho phép làm tốt hơn bằng cách tận dụng trực tiếp các tổng khối trong `bit`.

## 12. Tư tưởng binary lifting trực tiếp trên BIT

Trong Fenwick, mỗi ô `bit[i]` đại diện một đoạn có độ dài là lũy thừa 2. Thay vì hỏi tổng tiền tố ở từng `mid` từ đầu, ta **đi qua các khối** từ lớn đến nhỏ.

Giả sử đã xác định một biên:

```text
idx
```

và tổng các phần tử trước biên đó là:

```text
acc = P[idx]
```

Bây giờ xét một bước nhảy `step` là lũy thừa 2. Thử biên:

```text
candidate = idx + step
```

Khi thuật toán giữ đúng quy tắc chọn các bit từ cao xuống thấp, **đoạn mới `[idx,candidate)` chính là vùng do `bit[candidate]` quản lý**. Vì thế:

```text
P[candidate] = acc + bit[candidate]
```

Ta không cần gọi `prefix_sum(candidate)` để tính lại từ đầu.

### Quy tắc chấp nhận bước

Nếu:

```text
candidate <= n
và
acc + bit[candidate] < target
```

thì tiền tố ở candidate **vẫn chưa đủ ngưỡng**. Ta chấp nhận bước:

```text
idx = candidate
acc += bit[candidate]
```

Ngược lại, không chấp nhận bước ấy, vì có thể đã đi quá biên đầu tiên đạt ngưỡng.

Sau đó giảm `step` đi một nửa rồi thử tiếp.

### Điều kiện để so sánh có ý nghĩa

Nếu `P` không giảm, khi ta đã biết `P[candidate]<target` thì mọi biên không vượt candidate cũng chưa đạt, nên có thể bỏ qua chúng an toàn.

Nếu `P` có thể giảm, `P[candidate]<target` **không loại trừ** khả năng một biên trước candidate đã đạt ngưỡng — đó chính là phản ví dụ `[5,-10,10]`.

## 13. Giả mã tìm biên đầu tiên đạt target

Giả định đầu vào đã xác nhận **mọi giá trị hiện tại không âm**.

```text
FIRST_PREFIX_AT_LEAST(target):
    if target <= 0:
        return 0

    total = prefix_sum(n)
    if target > total:
        return None

    idx = 0
    acc = 0

    step = lũy thừa 2 lớn nhất <= n

    while step > 0:
        candidate = idx + step

        if candidate <= n and acc + bit[candidate] < target:
            idx = candidate
            acc += bit[candidate]

        step //= 2

    return idx + 1
```

Cả `idx` và `candidate` là **biên tiền tố** thuộc `[0,n]`, không phải các chỉ số phần tử ngoài mảng. Kết quả cuối là `idx+1` vì idx được duy trì là **biên cuối cùng chưa đạt ngưỡng**.

Nếu không có giá trị đạt ngưỡng, ta trả `None` **trước** khi vào vòng tìm kiếm.

### Chọn step đầu tiên

Với `n>0`:

```python
step = 1 << (n.bit_length() - 1)
```

Đó là lũy thừa 2 lớn nhất không vượt n.

- `n=8`: step=8.
- `n=10`: step=8.
- `n=13`: step=8.
- `n=1`: step=1.

Với `n=0`, không tính biểu thức trên vì `n.bit_length()-1=-1`. Hàm hoàn chỉnh xử lý trường hợp không có ngưỡng dương đạt được trước khi tính step.

## 14. Truy vết binary lifting: target=7

Dữ liệu:

```text
a = [2,0,3,1,0,4,2,0]
n = 8

bit[1..8] = [2,2,3,6,0,4,2,12]
P = [0,2,2,5,6,6,10,12,12]
```

Mục tiêu `target=7`:

```text
idx=0, acc=0
step=8
```

Các lần thử:

| Bước | `step` | `candidate` | `acc+bit[candidate]` | So với 7 | Quyết định |
|---:|---:|---:|---:|---|---|
| 1 | 8 | 8 | 12 | Đã đạt | Không nhảy |
| 2 | 4 | 4 | 6 | Chưa đạt | `idx=4,acc=6` |
| 3 | 2 | 6 | `6+4=10` | Đã đạt | Không nhảy |
| 4 | 1 | 5 | `6+0=6` | Chưa đạt | `idx=5,acc=6` |

Sau khi hết các bước:

```text
idx = 5
P[idx] = 6 < 7

end = idx+1 = 6
P[6] = 10 >= 7
```

Đúng như tìm trực tiếp.

### Vì sao khối ở candidate=5 chỉ có một phần tử?

`lowbit(5)=1`, nên `bit[5]` quản lý `[4,5)` — ngăn có giá trị 0. Vì cập nhật `acc+0=6<7` vẫn chưa đạt, ta có thể **bỏ qua cả vị trí 4** mà không bỏ mất đáp án.

### Vì sao không dùng so sánh <=?

Nếu `target=6`, tiền tố `P[4]=6` **đã đạt ngưỡng**. Quy tắc chấp nhận bước dùng:

```text
acc + bit[candidate] < target
```

nên **không bỏ qua end=4**. Nếu dùng `<=target`, thuật toán có thể đi qua biên đạt đúng mục tiêu và trả một biên muộn hơn, đặc biệt khi có phần tử 0.

## 15. Bất biến quan trọng của binary lifting

Khi duyệt `step` từ lũy thừa lớn xuống nhỏ, duy trì:

1. `idx` là biên đã chấp nhận, với **`P[idx]<target`**.
2. `acc=P[idx]`.
3. Các bước nhảy lớn hơn `step` đã được quyết định; `idx` là tổng các bước đã chấp nhận.
4. Tại mỗi bước xét, `idx` chia hết cho `2*step`. Do đó `candidate=idx+step` có `lowbit(candidate)=step`, miễn candidate hợp lệ.

Điều kiện (4) giải thích **vì sao có thể dùng trực tiếp `bit[candidate]`**:

```text
Vùng của bit[candidate]
 = [candidate-lowbit(candidate),candidate)
 = [candidate-step,candidate)
 = [idx,candidate)
```

Vậy:

```text
acc + bit[candidate] = P[candidate]
```

Sau khi xét từng bit từ cao xuống thấp, việc chỉ chấp nhận những bước có tổng chưa đạt tạo ra biên `idx` **lớn nhất** còn thỏa `P[idx]<target` (nhờ P không giảm).

Nếu đã kiểm tra `target<=P[n]`, biên kế tiếp tồn tại, và:

```text
P[idx] < target <= P[idx+1]
```

nên `idx+1` là biên đầu tiên đạt ngưỡng.

**Đây là chứng minh cho O(log n) tìm kiếm, không cần quét tất cả tiền tố.**

## 16. Độ phức tạp của phép tìm

Với `n>0`, số bước `step` được thử lần lượt là:

```text
2^floor(log2(n)), ..., 4, 2, 1
```

Số lượng là:

```text
floor(log2(n)) + 1 = O(log n)
```

Mỗi lần thử dùng:

- Một phép cộng chỉ số.
- Một lần kiểm tra biên.
- Tối đa một lần đọc `bit[candidate]`.
- Một phép cộng và một so sánh.
- Có thể cập nhật `idx` và `acc`.
- Chia `step` cho 2.

Vì vậy, **binary lifting trên Fenwick tốn O(log n) thời gian và O(1) bộ nhớ điều khiển**, với phép toán trên giá trị được coi O(1).

Hàm hoàn chỉnh còn gọi `prefix_sum(n)` một lần để kiểm tra `target` vượt tổng, mất O(log n); tổng chi phí vẫn O(log n).

So với binary search ngoài Fenwick:

| Phương pháp | Số lần xem tiền tố | Chi phí mỗi lần | Tổng |
|---|---:|---:|---:|
| Quét trực tiếp | Đến n | O(1) cộng mỗi bước | O(n) |
| Binary search + query BIT | O(log n) | O(log n) | O(log² n) |
| **Binary lifting trực tiếp trên BIT** | O(log n) khối | O(1) mỗi khối | **O(log n)** |

**Cả hai cách tìm nhị phân đều yêu cầu tính đơn điệu**. Nhanh hơn không đồng nghĩa điều kiện đầu vào được nới lỏng.

## 17. Cài đặt Python hoàn chỉnh cho số nguyên có dấu

Để có một API chính xác, ta lưu:

- `values`: giá trị hiện tại của từng phần tử.
- `bit`: các tổng vùng của Fenwick 1-based.
- `negative_count`: **số phần tử hiện đang âm**.

Nhờ `negative_count`, hàm tìm ngưỡng kiểm tra điều kiện không âm trong O(1) **mà không quét lại cả mảng** mỗi lần. Truy vấn tổng đoạn vẫn dùng được dù `negative_count>0`.

Ví dụ triển khai tập trung vào **số nguyên Python**, để các vấn đề số học/so sánh có ý nghĩa rõ ràng. Nếu cần số thực, phải quyết định thêm cách xử lý NaN, vô cực, dung sai và làm tròn.

```python
class FenwickInt:
    """BIT tổng số nguyên: API ngoài 0-based, nội bộ 1-based."""

    def __init__(self, values):
        self.values = list(values)

        if any(type(v) is not int for v in self.values):
            raise TypeError("Ví dụ này chỉ nhận số nguyên")

        self.n = len(self.values)
        self.bit = [0] * (self.n + 1)
        self.negative_count = sum(v < 0 for v in self.values)

        # Xây BIT tuyến tính O(n).
        for i, value in enumerate(self.values, start=1):
            self.bit[i] += value
            parent = i + (i & -i)

            if parent <= self.n:
                self.bit[parent] += self.bit[i]

    def _check_pos(self, pos):
        if type(pos) is not int:
            raise TypeError("pos phải là số nguyên")
        if not 0 <= pos < self.n:
            raise IndexError("pos ngoài mảng")

    def _check_end(self, end):
        if type(end) is not int:
            raise TypeError("end phải là số nguyên")
        if not 0 <= end <= self.n:
            raise IndexError("end ngoài khoảng [0,n]")

    def _check_range(self, l, r):
        if type(l) is not int or type(r) is not int:
            raise TypeError("l và r phải là số nguyên")
        if not 0 <= l <= r <= self.n:
            raise IndexError("Đoạn [l,r) không hợp lệ")

    def point_add(self, pos, delta):
        self._check_pos(pos)
        if type(delta) is not int:
            raise TypeError("delta phải là số nguyên")

        old = self.values[pos]
        new = old + delta

        # Duy trì điều kiện tìm kiếm khi dữ liệu đổi dấu.
        self.negative_count += int(new < 0) - int(old < 0)
        self.values[pos] = new

        i = pos + 1
        while i <= self.n:
            self.bit[i] += delta
            i += i & -i

    def point_assign(self, pos, new_value):
        self._check_pos(pos)
        if type(new_value) is not int:
            raise TypeError("Giá trị gán phải là số nguyên")

        delta = new_value - self.values[pos]
        self.point_add(pos, delta)

    def prefix_sum(self, end):
        self._check_end(end)

        result = 0
        i = end

        while i > 0:
            result += self.bit[i]
            i -= i & -i

        return result

    def range_sum(self, l, r):
        self._check_range(l, r)
        return self.prefix_sum(r) - self.prefix_sum(l)

    def first_prefix_at_least(self, target):
        if type(target) is not int:
            raise TypeError("target phải là số nguyên")

        if self.negative_count:
            raise ValueError(
                "Cần mọi phần tử không âm để bảo đảm tiền tố không giảm"
            )

        if target <= 0:
            return 0

        if target > self.prefix_sum(self.n):
            return None

        idx = 0
        acc = 0
        step = 1 << (self.n.bit_length() - 1)

        while step:
            candidate = idx + step

            if (candidate <= self.n
                    and acc + self.bit[candidate] < target):
                idx = candidate
                acc += self.bit[candidate]

            step >>= 1

        return idx + 1

    def kth_unit_index(self, k):
        """Tìm chỉ số phần tử chứa đơn vị thứ k, đánh số k từ 1."""
        if type(k) is not int or k <= 0:
            raise ValueError("k phải là số nguyên dương")

        end = self.first_prefix_at_least(k)
        return None if end is None else end - 1
```

### Xây và truy vấn trên dãy mẫu

```python
a = [2, 0, 3, 1, 0, 4, 2, 0]
fw = FenwickInt(a)

assert fw.n == 8
assert fw.negative_count == 0
assert fw.bit == [0, 2, 2, 3, 6, 0, 4, 2, 12]

assert fw.prefix_sum(0) == 0
assert fw.prefix_sum(6) == 10
assert fw.prefix_sum(8) == 12
assert fw.range_sum(2, 7) == 10
assert fw.range_sum(1, 6) == 8
assert fw.range_sum(8, 8) == 0
```

### Tìm các biên chính xác

```python
expected = {
    -2: 0,
    0: 0,
    1: 1,
    2: 1,
    3: 3,
    5: 3,
    6: 4,
    7: 6,
    10: 6,
    11: 7,
    12: 7,
    13: None,
}

for target, end in expected.items():
    assert fw.first_prefix_at_least(target) == end

assert fw.kth_unit_index(7) == 5
assert fw.kth_unit_index(12) == 6
assert fw.kth_unit_index(13) is None
```

### Cập nhật trực tuyến rồi tìm lại

```python
fw.point_add(6, 3)  # Ngăn 6 tăng từ 2 lên 5.

assert fw.values == [2, 0, 3, 1, 0, 4, 5, 0]
assert fw.prefix_sum(8) == 15
assert fw.first_prefix_at_least(13) == 7
assert fw.kth_unit_index(13) == 6

fw.point_assign(6, 2)  # Đưa ngăn 6 về 2.
assert fw.prefix_sum(8) == 12
assert fw.first_prefix_at_least(13) is None
```

### Số âm được phép cho truy vấn tổng nhưng chặn phép tìm

```python
signed = FenwickInt([5, -10, 10])

assert signed.range_sum(0, 3) == 5
assert signed.range_sum(1, 3) == 0
assert signed.prefix_sum(2) == -5
assert signed.negative_count == 1

try:
    signed.first_prefix_at_least(4)
except ValueError:
    pass
else:
    raise AssertionError("Không được binary lift khi tiền tố không đơn điệu")

signed.point_assign(1, 0)
assert signed.negative_count == 0
assert signed.values == [5, 0, 10]
assert signed.first_prefix_at_least(4) == 1
```

Kiểm tra `negative_count` là **chính sách bảo đảm điều kiện đầu vào** của lớp, không phải đặc tính bắt buộc của mọi BIT. Một Fenwick chỉ cần hỏi tổng không cần lưu trường này.

## 18. Tại sao cách xây BIT O(n) là đúng?

Trong `FenwickInt.__init__`, duyệt `i` tăng từ 1 đến n:

```text
bit[i] += values[i-1]
parent = i + lowbit(i)

nếu parent <= n:
    bit[parent] += bit[i]
```

Khi đến một ô `i`, nó đã nhận mọi đóng góp từ các ô nhỏ hơn có vùng con đẩy về `i`. Sau khi cộng giá trị trực tiếp ở `a[i-1]`, `bit[i]` trở thành tổng đúng của vùng:

```text
[i-lowbit(i), i)
```

Ta đẩy tổng đã hoàn thiện ấy một lần lên cha. Mỗi ô được duyệt đúng một lần và làm O(1) phép số học, nên:

```text
Xây dựng: O(n) thời gian
Lưu bit và values: O(n) bộ nhớ
```

Nếu thay bằng cách gọi cập nhật điểm n lần, mỗi lần O(log n), chi phí xây là **O(n log n)**. Hai phương pháp cho cùng bất biến nhưng khác chi phí.

### Kiểm tra hai cách xây

```python
def build_fenwick_by_adds(values):
    n = len(values)
    bit = [0] * (n + 1)

    for pos, value in enumerate(values):
        i = pos + 1
        while i <= n:
            bit[i] += value
            i += i & -i

    return bit


values = [2, 0, 3, 1, 0, 4, 2, 0]

assert FenwickInt(values).bit == build_fenwick_by_adds(values)
```

Mã chỉ so sánh kết quả xây; nó không thay thế vòng kiểm thử tính đúng sau cập nhật.

## 19. Xử lý các trường hợp biên của tìm theo ngưỡng

### 19.1. Target bằng 0 hoặc âm

Với mảng không âm:

```text
P[0] = 0
```

nên nếu `target<=0`, biên đầu tiên đạt ngưỡng **luôn là end=0**, ngay cả khi mảng rỗng.

```python
empty = FenwickInt([])

assert empty.first_prefix_at_least(0) == 0
assert empty.first_prefix_at_least(-3) == 0
assert empty.first_prefix_at_least(1) is None
```

### 19.2. Không có đơn vị nào

Nếu mọi phần tử bằng 0:

```text
a = [0,0,0]
P = [0,0,0,0]
```

không có `end` đạt ngưỡng dương:

```python
zero = FenwickInt([0, 0, 0])

assert zero.first_prefix_at_least(0) == 0
assert zero.first_prefix_at_least(1) is None
assert zero.kth_unit_index(1) is None
```

### 19.3. Phần tử đầu đã đạt ngưỡng

```python
fw = FenwickInt([10, 0, 2])

assert fw.first_prefix_at_least(1) == 1
assert fw.first_prefix_at_least(10) == 1
assert fw.first_prefix_at_least(11) == 3
```

Vì ngăn 1 có số lượng 0, ngưỡng từ 1 đến 10 đều đạt ngay sau phần tử đầu.

### 19.4. Biên cuối và target bằng tổng

```python
fw = FenwickInt([2, 0, 3, 1, 0, 4, 2, 0])

assert fw.first_prefix_at_least(12) == 7
assert fw.first_prefix_at_least(13) is None
```

Dù có n=8 phần tử, tiền tố đầu tiên đạt tổng toàn mảng nằm ở **end=7**, vì ngăn cuối bằng 0. Không được luôn trả `n` khi target bằng tổng.

### 19.5. Target phải là số nguyên trong ví dụ

```python
try:
    fw.first_prefix_at_least(2.5)
except TypeError:
    pass
else:
    raise AssertionError("Lớp ví dụ chỉ dùng target nguyên")
```

Một phiên bản tổng quát có thể hỗ trợ số thực, nhưng cần xác định hợp đồng về so sánh, sai số và các giá trị không hữu hạn.

## 20. Từ tìm biên tiền tố đến phần tử thứ k

Giả sử `a[i]` biểu thị **số lần xuất hiện của khóa hoặc số phần tử** tại vị trí i. Mọi `a[i]` phải là **số nguyên không âm**.

Nếu có:

```text
a = [2,0,3,1,0,4,2,0]
```

thì chuỗi các vị trí khi trải phẳng theo tần suất là:

```text
0,0, 2,2,2, 3, 5,5,5,5, 6,6
```

Đơn vị thứ k (đánh số **từ 1**) nằm ở vị trí:

```text
pos = first_prefix_at_least(k) - 1
```

với điều kiện tồn tại kết quả.

Ví dụ:

| `k` | Vị trí ngoài `pos` | Giải thích |
|---:|---:|---|
| 1 | 0 | Đơn vị đầu tiên trong hai đơn vị ở ngăn 0 |
| 2 | 0 | Đơn vị thứ hai ở ngăn 0 |
| 3 | 2 | Ngăn 1 rỗng, chuyển đến ngăn 2 |
| 5 | 2 | Đơn vị cuối trong ba đơn vị ở ngăn 2 |
| 6 | 3 | Một đơn vị ở ngăn 3 |
| 7 | 5 | Bắt đầu nhóm bốn đơn vị ở ngăn 5 |
| 10 | 5 | Đơn vị cuối ở ngăn 5 |
| 11 | 6 | Nhóm hai đơn vị ở ngăn 6 |
| 12 | 6 | Đơn vị cuối toàn mảng |

**Không chấp nhận `k=0` khi nói “đơn vị thứ k”.** Nó không phải một đơn vị dữ liệu có thứ tự từ 1. Với `k>total`, không có phần tử tương ứng nên trả `None`.

## 21. Lớp đếm tần suất: không cho phép giảm xuống âm

Một ứng dụng thứ tự thống kê (*order statistics*) nên có giao diện ngăn các cập nhật làm tần suất âm. Khi đó điều kiện tìm kiếm được duy trì **theo thiết kế**, không chỉ nhờ người gọi nhớ kiểm tra.

```python
class FrequencyFenwick:
    """Đếm số đơn vị tại mỗi vị trí và tìm phần tử thứ k."""

    def __init__(self, counts):
        if any(type(c) is not int or c < 0 for c in counts):
            raise ValueError("Mọi tần suất phải là số nguyên không âm")

        self.fw = FenwickInt(counts)

    def add_count(self, pos, delta):
        self.fw._check_pos(pos)

        if type(delta) is not int:
            raise TypeError("delta phải là số nguyên")

        new_count = self.fw.values[pos] + delta
        if new_count < 0:
            raise ValueError("Tần suất không được âm")

        self.fw.point_add(pos, delta)

    def total(self):
        return self.fw.prefix_sum(self.fw.n)

    def count_in_range(self, l, r):
        return self.fw.range_sum(l, r)

    def kth(self, k):
        if type(k) is not int or k <= 0:
            raise ValueError("k phải là số nguyên dương")

        return self.fw.kth_unit_index(k)


freq = FrequencyFenwick([2, 0, 3, 1, 0, 4, 2, 0])

assert freq.total() == 12
assert freq.kth(1) == 0
assert freq.kth(3) == 2
assert freq.kth(7) == 5
assert freq.kth(12) == 6
assert freq.kth(13) is None
assert freq.count_in_range(2, 7) == 10

freq.add_count(6, -2)  # Ngăn 6 từ 2 về 0.
assert freq.total() == 10
assert freq.kth(11) is None

freq.add_count(6, 5)   # Ngăn 6 từ 0 lên 5.
assert freq.total() == 15
assert freq.kth(13) == 6

try:
    freq.add_count(1, -1)
except ValueError:
    pass
else:
    raise AssertionError("Không được tạo tần suất âm")
```

### Chỉ số của khóa và tọa độ thực

Ở đây `pos` chỉ là **vị trí trong mảng tần suất**. Nếu ngăn là các khóa lớn, thưa hoặc không liên tiếp (ví dụ mã hàng 100, 700, 9000), cần **nén tọa độ** hoặc ánh xạ từ vị trí mảng sang khóa thực.

Khi đó BIT giúp tìm **vị trí trong danh sách khóa đã sắp**, rồi ứng dụng trả lại **khóa tương ứng**. Không được đồng nhất chỉ số Fenwick với mã hàng thực khi hai miền khác nhau.

## 22. Tìm phần tử thứ k trong một đoạn con

Biết tìm thứ k toàn mảng, ta có thể tìm **thứ k theo tần suất trong một đoạn `[l,r)`** mà vẫn dùng cùng cây Fenwick.

Giả sử các tần suất đều không âm. Tổng số đơn vị trong đoạn:

```text
count = P[r] - P[l]
```

Nếu `k` nằm trong `[1,count]`, thì đơn vị thứ k của đoạn nằm ở nơi tiền tố toàn mảng lần đầu đạt:

```text
target_global = P[l] + k
```

Vì mọi giá trị không âm, phần tử trước l chỉ chứa tổng `P[l]` và không thể đã đạt ngưỡng lớn hơn nó. Vì `k<=P[r]-P[l]`, vị trí tìm thấy luôn nằm trong `[l,r)`.

### Hàm

```python
def kth_in_range(fw, l, r, k):
    """Trả vị trí ngoài của đơn vị thứ k trong [l,r)."""
    fw._check_range(l, r)

    if fw.negative_count:
        raise ValueError("Tần suất cần không âm")

    if type(k) is not int or k <= 0:
        raise ValueError("k phải là số nguyên dương")

    available = fw.range_sum(l, r)
    if k > available:
        return None

    global_target = fw.prefix_sum(l) + k
    end = fw.first_prefix_at_least(global_target)
    return end - 1


fw = FenwickInt([2, 0, 3, 1, 0, 4, 2, 0])

assert kth_in_range(fw, 2, 7, 1) == 2
assert kth_in_range(fw, 2, 7, 3) == 2
assert kth_in_range(fw, 2, 7, 4) == 3
assert kth_in_range(fw, 2, 7, 5) == 5
assert kth_in_range(fw, 2, 7, 10) == 6
assert kth_in_range(fw, 2, 7, 11) is None
assert kth_in_range(fw, 3, 3, 1) is None
```

Độ phức tạp vẫn **O(log n)**: tính tổng đoạn và `P[l]` bằng một số cố định lần truy vấn O(log n), rồi tìm theo ngưỡng O(log n).

**Lưu ý:** hàm này đếm đơn vị theo tần suất, không tìm “phần tử có giá trị lớn thứ k” của một mảng số tùy ý. Nếu `a[i]` là điểm số (có cả âm) chứ không phải số lượng, cách diễn giải thứ tự thống kê sẽ không còn đúng.

## 23. Tìm biên trong đoạn khi chỉ hỏi tổng đạt ngưỡng

Một biến thể bài toán là:

> Với một `l` cố định, tìm `r` nhỏ nhất có `r>=l` sao cho `sum([l,r))>=x`.

Với mọi `a[i]>=0`, ta có:

```text
sum([l,r)) = P[r]-P[l]
```

Do đó:

```text
P[r] >= P[l]+x
```

Nếu `x<=0`, chính đoạn rỗng `[l,l)` đã đủ ngưỡng nên trả `r=l`.

Nếu `x>0`, tìm ngưỡng toàn cục `P[l]+x`:

```text
r = first_prefix_at_least(P[l]+x)
```

và chỉ chấp nhận kết quả trong `[l,n]`; khi không có, trả `None`.

### Python

```python
def first_right_with_sum_at_least(fw, l, target):
    """Tìm r nhỏ nhất >=l sao cho sum([l,r))>=target."""
    if type(l) is not int or not 0 <= l <= fw.n:
        raise IndexError("l nằm ngoài [0,n]")

    if fw.negative_count:
        raise ValueError("Cần mọi phần tử không âm")

    if target <= 0:
        return l

    required = fw.prefix_sum(l) + target
    return fw.first_prefix_at_least(required)


fw = FenwickInt([2, 0, 3, 1, 0, 4, 2, 0])

assert first_right_with_sum_at_least(fw, 2, 4) == 4
assert first_right_with_sum_at_least(fw, 2, 5) == 6
assert first_right_with_sum_at_least(fw, 6, 2) == 7
assert first_right_with_sum_at_least(fw, 7, 1) is None
assert first_right_with_sum_at_least(fw, 7, 0) == 7
```

Kiểm tra ví dụ `l=2,target=4`: `a[2]+a[3]=3+1=4`, nên r=4. Với target=5, cần thêm bốn đơn vị ở vị trí 5 nên r=6.

**Đừng nhầm phương thức này với `range_sum(l,r)`:** một phương thức **trả tổng khi đã biết r**; phương thức còn lại **tìm r khi biết ngưỡng tổng**.

## 24. Phân biệt ngưỡng ≥ và >

Với các giá trị tiền tố bằng nhau, việc dùng dấu so sánh đúng rất quan trọng.

### Tìm biên đầu tiên có tổng ít nhất target

Ta cần:

```text
P[end] >= target
```

Do đó thuật toán chỉ bỏ qua candidate nếu:

```text
P[candidate] < target
```

### Tìm biên đầu tiên có tổng lớn hơn target

Nếu yêu cầu là:

```text
P[end] > target
```

thì ta bỏ qua candidate khi:

```text
P[candidate] <= target
```

Hai quy tắc khác nhau khi các tiền tố bằng đúng target.

Với **tổng nguyên**, một cách viết lại là:

```text
P[end] > target
  <=> P[end] >= target+1
```

nên có thể gọi:

```python
def first_prefix_strictly_greater(fw, target):
    if type(target) is not int:
        raise TypeError("target phải là số nguyên")
    return fw.first_prefix_at_least(target + 1)


fw = FenwickInt([2, 0, 3, 1, 0, 4, 2, 0])

assert fw.first_prefix_at_least(2) == 1
assert first_prefix_strictly_greater(fw, 2) == 3
assert fw.first_prefix_at_least(6) == 4
assert first_prefix_strictly_greater(fw, 6) == 6
```

Đổi `target+1` chỉ đúng theo cách này khi tổng/target thuộc **miền nguyên rời rạc**. Với số thực, `>target` không thể luôn quy về `>=target+1`.

## 25. Nếu dữ liệu có số âm thì dùng gì để tìm ngưỡng?

Khi có số âm, `P` có thể không đơn điệu. Để tìm **biên đầu tiên** đạt một target bất kỳ, ta cần một cấu trúc ghi nhận nhiều thông tin hơn **chỉ tổng khối**.

Một lựa chọn là **segment tree lưu tổng và tổng tiền tố lớn nhất** của mỗi đoạn.

Với mỗi nút quản lý một đoạn liên tiếp, lưu:

```text
sum = tổng mọi phần tử trong đoạn
best = tổng lớn nhất của một tiền tố trong đoạn,
       cho phép tiền tố rỗng có tổng 0
```

Khi ghép nút trái L và nút phải R:

```text
sum(parent) = sum(L) + sum(R)

best(parent) = max(
    best(L),
    sum(L) + best(R)
)
```

Vì một tiền tố của đoạn cha hoặc:

- Nằm hoàn toàn trong đoạn trái; hoặc
- Ăn hết đoạn trái rồi lấy thêm một tiền tố đoạn phải.

**Không cần các giá trị không âm.** Trường `best` cho biết liệu **có một tiền tố trong đoạn đang xét** đạt target không, ngay cả khi tổng toàn đoạn thấp hơn target.

### Tìm nhánh đầu tiên đạt ngưỡng

Duy trì `acc` là tổng của tất cả phần tử trước nút đang xét.

Nếu:

```text
acc + best(left) >= target
```

thì lời giải sớm nhất nằm bên trái. Ngược lại, không có tiền tố nào ở nhánh trái đạt target, nên cộng `sum(left)` vào acc rồi đi sang phải.

Tìm tới một lá, trả `end=leaf_index+1`. Với `target<=0`, đoạn rỗng `end=0` là đáp án.

### Python minh họa

```python
class MaxPrefixSegmentTree:
    """Tìm tiền tố đầu tiên đạt ngưỡng, kể cả dữ liệu âm."""

    def __init__(self, values):
        self.n = len(values)
        self.size = 1

        while self.size < self.n:
            self.size *= 2

        self.total = [0] * (2 * self.size)
        self.best = [0] * (2 * self.size)

        for i, value in enumerate(values):
            node = self.size + i
            self.total[node] = value
            self.best[node] = max(0, value)

        for node in range(self.size - 1, 0, -1):
            self._pull(node)

    def _pull(self, node):
        left = 2 * node
        right = left + 1

        self.total[node] = self.total[left] + self.total[right]
        self.best[node] = max(
            self.best[left],
            self.total[left] + self.best[right],
        )

    def point_assign(self, pos, value):
        if type(pos) is not int or not 0 <= pos < self.n:
            raise IndexError("pos ngoài mảng")

        node = self.size + pos
        self.total[node] = value
        self.best[node] = max(0, value)

        node //= 2
        while node:
            self._pull(node)
            node //= 2

    def first_prefix_at_least(self, target):
        if target <= 0:
            return 0

        if self.best[1] < target:
            return None

        node = 1
        acc = 0

        while node < self.size:
            left = 2 * node

            if acc + self.best[left] >= target:
                node = left
            else:
                acc += self.total[left]
                node = left + 1

        return node - self.size + 1


tree = MaxPrefixSegmentTree([5, -10, 10])

assert tree.first_prefix_at_least(4) == 1
assert tree.first_prefix_at_least(5) == 1
assert tree.first_prefix_at_least(6) is None
assert tree.first_prefix_at_least(0) == 0

tree.point_assign(1, 0)
assert tree.first_prefix_at_least(10) == 3

assert MaxPrefixSegmentTree([]).first_prefix_at_least(1) is None
```

Độ phức tạp:

- Xây: O(n) thời gian/bộ nhớ.
- Gán một điểm: O(log n).
- Tìm tiền tố đầu tiên đạt ngưỡng: O(log n), kể cả có số âm.

Cấu trúc này có **bất biến khác** Fenwick tổng đơn giản. Nó không phải “Fenwick với phép so sánh thay dấu cộng”, mà là lựa chọn khi **điều kiện đơn điệu không được đáp ứng**.

## 26. Những điều kiện cần kiểm tra trước khi chọn thuật toán

| Yêu cầu | Điều kiện/bất biến | Giải pháp tiêu biểu |
|---|---|---|
| Hỏi tổng `[l,r)` trên dữ liệu tĩnh | Có phép cộng/trừ; không cần không âm | Prefix sum |
| Cộng một điểm + hỏi tổng đoạn online | Phép cộng có thể khử tiền tố | Fenwick sum |
| Tìm biên đầu tiên `P[end]>=target` bằng BIT lifting | **P không giảm**; đủ và tương đương với mọi `a[i]>=0` | Fenwick binary lifting |
| Tìm vị trí đơn vị thứ k | Tần suất **nguyên không âm**, `k>=1` | Frequency Fenwick |
| Tìm đơn vị thứ k trong `[l,r)` | Tần suất nguyên không âm; k không vượt số đơn vị trong đoạn | Fenwick + mục tiêu `P[l]+k` |
| Tìm biên đầu tiên với mảng có số âm | Không dựa vào đơn điệu của P | Segment tree tổng + max tiền tố |
| Tìm min/max đoạn tùy ý | Cần phép tổng hợp min/max thích hợp | Segment tree, sparse table tĩnh |
| Cộng đoạn và hỏi giá trị một điểm | Mốc hiệu + tổng tiền tố | Fenwick trên mảng hiệu |
| Cộng đoạn và hỏi tổng đoạn online | Cần thêm thông tin cập nhật đoạn | Hai BIT hoặc segment tree lazy |

**Cần phân biệt hai cách dùng từ “cần”:** nonnegative là điều kiện **cần và đủ để toàn bộ dãy P không giảm** trong số học chính xác; còn với một bộ dữ liệu và một target cụ thể, một thuật toán tìm kiếm có thể tình cờ trả đúng dù có số âm. Vì thế, đây là **tiền điều kiện để bảo đảm tính đúng cho toàn bộ đầu vào của thuật toán chuẩn**, không phải kết luận rằng chẳng bài toán tìm kiếm có số âm nào giải được.

## 27. Độ phức tạp tổng thể và bộ nhớ

Gọi `n` là số phần tử, `u` là số lần cập nhật, `q` là số lần truy vấn tổng và `t` là số lần tìm biên ngưỡng.

Với `FenwickInt` xây tuyến tính và các phép toán số nguyên kích thước cố định xem là O(1):

```text
Xây ban đầu:             O(n)
Một point_add:           O(log n)
Một point_assign:        O(log n)
Một prefix_sum:          O(log n)
Một range_sum:           O(log n)
Một first_prefix:        O(log n)
Một kth_unit_index:      O(log n)

Tổng: O(n + (u+q+t)*log n)
```

Bộ nhớ:

```text
values: n phần tử
bit:    n+1 ô
negative_count: 1 số

=> O(n) tổng bộ nhớ
```

Nếu giữ mọi câu trả lời trong một danh sách, riêng kết quả tốn thêm O(q+t).

### So sánh với lựa chọn khác

| Cách làm | Tiền xử lý | Query tổng đoạn | Cập nhật điểm | Tìm biên ngưỡng |
|---|---:|---:|---:|---:|
| Quét mảng | O(1) | O(r-l) | O(1) | O(n) bằng quét |
| Prefix sum tĩnh | O(n) | **O(1)** | O(n) để duy trì bảng | O(log n) binary search nếu không âm |
| Fenwick sum | O(n) | **O(log n)** | **O(log n)** | **O(log n)** lifting nếu không âm |
| Binary search ngoài Fenwick | O(n) xây BIT | O(log n) | O(log n) | O(log² n) nếu không âm |
| Segment tree tổng + max tiền tố | O(n) | O(log n) nếu triển khai tổng đoạn | O(log n) | O(log n), kể cả có số âm |

Đối với số nguyên Python rất lớn, phép cộng/trừ và so sánh có thể phụ thuộc độ dài bit. Bậc thời gian ở trên theo mô hình RAM với chi phí phép toán số học hằng số.

## 28. Truy vấn sau cập nhật và điều kiện không âm

Hệ thống đếm hàng hóa có thể nhận:

```text
add(pos=2, delta=+5)
add(pos=5, delta=-1)
query_sum(1,7)
kth(10)
```

Khi giảm số lượng, điều kiện phải kiểm tra là:

```text
a[pos] + delta >= 0
```

Nếu cho phép số lượng âm, BIT vẫn có tổng đúng, nhưng thao tác `kth` không còn tương ứng một chuỗi các đơn vị dữ liệu.

### Kiểm tra điều kiện tại điểm cập nhật

Lớp `FrequencyFenwick` thực hiện:

```python
new_count = self.fw.values[pos] + delta
if new_count < 0:
    raise ValueError("Tần suất không được âm")
```

Nhờ vậy, mỗi lần gọi `kth` không cần quét toàn mảng để xác minh điều kiện.

Ngược lại, `FenwickInt` được thiết kế cho cả số có dấu: nó **cho phép giá trị âm**, nhưng duy trì `negative_count` và từ chối việc tìm biên khi tồn tại số âm.

Hai giao diện này minh họa một nguyên tắc:

> **Định nghĩa hợp đồng dữ liệu ở nơi tạo và cập nhật, thay vì đợi đến lúc tìm kiếm mới phát hiện một giả định đã sai.**

## 29. Vì sao không cần tính lại toàn bộ P sau mỗi update?

Trong dãy tổng tiền tố vật lý:

```text
P[i+1], P[i+2], ..., P[n]
```

đều bị ảnh hưởng khi cập nhật `a[i]`. Nếu sửa từng ô, một lần cập nhật có thể O(n).

Fenwick không vật chất hóa mọi `P[k]`. Thay vào đó:

- Khi cộng một điểm, sửa đúng các **tổng khối BIT** chứa điểm ấy.
- Khi hỏi `P[end]`, ghép các **khối rời nhau** phủ `[0,end)`.
- Khi tìm end theo target, thử các khối **theo thứ tự các bit từ cao xuống thấp**.

Cách tổ chức này làm cho mỗi thao tác chỉ đụng O(log n) ô.

Đây là sự đánh đổi: **truy vấn P không còn O(1)** như prefix tĩnh, nhưng cập nhật không còn O(n). Khi `u` và `q` đều lớn và xen kẽ, đánh đổi thường có lợi.

## 30. Kiểm thử bất biến BIT và kết quả tổng đoạn

Một lớp cấu trúc dữ liệu tối ưu nên được so sánh với cách làm đơn giản trên mảng nhỏ.

### Kiểm tra trực tiếp vùng của từng ô BIT

```python
def check_bit_regions(fw):
    for i in range(1, fw.n + 1):
        low = i & -i
        expected = sum(fw.values[i-low:i])
        assert fw.bit[i] == expected


fw = FenwickInt([2, 0, 3, 1, 0, 4, 2, 0])
check_bit_regions(fw)

fw.point_add(2, 5)
check_bit_regions(fw)

fw.point_assign(2, 0)
check_bit_regions(fw)
```

### Kiểm tra mọi đoạn

```python
def check_all_ranges(fw):
    for l in range(fw.n + 1):
        for r in range(l, fw.n + 1):
            assert fw.range_sum(l, r) == sum(fw.values[l:r])


for values in [
    [],
    [0],
    [9],
    [2, 0, 3, 1, 0, 4, 2, 0],
    [5, -10, 10],
    [-3, 0, -4, 5, 8],
]:
    fw = FenwickInt(values)
    check_bit_regions(fw)
    check_all_ranges(fw)
```

Trường hợp có số âm vẫn phải **PASS toàn bộ kiểm tra tổng đoạn**, dù bị cấm tìm theo ngưỡng bằng binary lifting.

## 31. Kiểm thử tìm ngưỡng bằng oracle tuyến tính

Dùng bản quét ở mục 10 để kiểm thử Fenwick trên mảng **không âm**. Vì mỗi query oracle O(n), cách này phù hợp cho dữ liệu nhỏ, không nên dùng làm thuật toán vận hành khi n lớn.

```python
def check_all_thresholds(fw):
    assert fw.negative_count == 0

    total = sum(fw.values)

    for target in range(-2, total + 3):
        expected = first_prefix_scan(fw.values, target)
        actual = fw.first_prefix_at_least(target)
        assert actual == expected


for values in [
    [],
    [0],
    [0, 0, 0],
    [2, 0, 3, 1, 0, 4, 2, 0],
    [1, 1, 1, 1],
    [0, 5, 0, 0, 2],
    [10, 0, 2],
]:
    fw = FenwickInt(values)
    check_all_thresholds(fw)
```

### Kiểm tra sau chuỗi cập nhật

```python
fw = FenwickInt([2, 0, 3, 1, 0, 4, 2, 0])

for pos, value in [
    (0, 0),
    (6, 5),
    (5, 1),
    (2, 0),
    (7, 9),
]:
    fw.point_assign(pos, value)
    check_bit_regions(fw)
    check_all_ranges(fw)
    check_all_thresholds(fw)
```

Bộ kiểm thử này phát hiện lỗi:

- Dùng `<=` thay vì `<` khi có tiền tố bằng đúng target.
- Trả `end` thay vì `end-1` trong bài toán vị trí đơn vị thứ k.
- Bỏ sót một ô cha lúc cập nhật BIT.
- Không giữ đúng số lượng âm sau khi cập nhật.
- Đọc sai biên `end=n` hoặc xử lý không đúng mảng rỗng.

### Kiểm tra lỗi đầu vào

```python
fw = FenwickInt([2, 0, 3])

for l, r in [(-1, 1), (2, 1), (0, 4)]:
    try:
        fw.range_sum(l, r)
    except IndexError:
        pass
    else:
        raise AssertionError("Phải từ chối biên sai")

try:
    fw.kth_unit_index(0)
except ValueError:
    pass
else:
    raise AssertionError("k=0 không phải đơn vị thứ k")

try:
    fw.first_prefix_at_least(True)
except TypeError:
    pass
else:
    raise AssertionError("Boolean không phải target nguyên")
```

## 32. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Lấy `P[r]+P[l]` thay vì hiệu | Cộng thừa tiền tố trái | `P[r]-P[l]` |
| Hiểu `[l,r)` có cả `r` | Sai một phần tử | `r` exclusive |
| Truy vấn BIT từ `end+1` | Lấy thừa một phần tử | `prefix_sum(end)` bắt đầu ở end |
| Cập nhật BIT từ `pos` 0-based | Có thể dùng lowbit(0) | Bắt đầu ở `pos+1` |
| Cho rằng `bit[i]` là tổng `[0,i)` | Nhầm bất biến | `bit[i]` lưu `[i-lowbit(i),i)` |
| Tìm ngưỡng trên mảng có số âm | Có thể trả biên sai | Kiểm tra không âm hoặc đổi cấu trúc |
| Nghĩ không âm nghĩa là dương | Từ chối dữ liệu có số 0 | Cần `a[i]>=0`, không phải `>0` |
| Dùng `<=target` để bỏ qua tiền tố trong lower_bound | Đi qua biên đã đạt target | Bỏ qua chỉ khi `<target` |
| Luôn trả n khi target bằng tổng | Sai nếu có số 0 cuối | Trả biên **đầu tiên** đạt |
| Dùng `target=0` như “đơn vị thứ 0” | Nhầm quy ước | kth chỉ nhận `k>=1` |
| Trả end làm chỉ số phần tử | Lệch một vị trí | `pos=end-1` |
| Không kiểm tra k vượt tổng | Có thể trả chỉ số ngoài mảng | Trả `None` khi không có |
| Chỉ kiểm tra không âm lúc xây | Update có thể tạo số âm | Duy trì điều kiện sau mỗi cập nhật |
| Quét toàn mảng để kiểm tra không âm trước mọi tìm kiếm | Tốn O(n), mất lợi ích O(log n) | Duy trì bộ đếm âm hoặc API tần suất |
| Quên cập nhật `negative_count` khi point_assign | Cho phép tìm sai hoặc chặn nhầm | Gán qua `delta=new-old` và cập nhật dấu |
| Dùng binary search ngoài BIT rồi báo O(log n) | Mỗi lần thử gọi prefix O(log n) | Tổng là O(log² n) |
| Dùng `bit[candidate]` không theo bước lũy thừa giảm | Không còn đúng vùng `[idx,candidate)` | Giữ invariant `idx` và `step` |
| Tính `1<<(n.bit_length()-1)` khi n=0 | Dịch bit với số âm | Xử lý n=0 trước |
| Lấy min đoạn bằng hiệu hai min tiền tố | Không có nghịch đảo | Chọn cấu trúc min phù hợp |
| Dùng kth cho tần suất số thực/âm | Không còn ý nghĩa số đơn vị rời | Dùng số nguyên không âm |
| Dùng Python `float` chứa NaN | Không có thứ tự so sánh thông thường | Xác định chính sách dữ liệu |
| Bỏ qua chi phí phép cộng số rất lớn | Cận O(log n) không phản ánh chi phí bit | Nêu rõ mô hình số học |

## 33. Bài tập tự luyện có lời giải

**Bài 1 — Truy vấn tổng.** Với `a=[2,0,3,1,0,4,2,0]`, tổng `[2,7)` là bao nhiêu?

*Lời giải:* `3+1+0+4+2=10`, cũng bằng `P[7]-P[2]=12-2=10`.

**Bài 2 — Tổng không âm có bắt buộc?** Phép tính tổng `[l,r)` bằng Fenwick có hoạt động khi `a` chứa số âm không?

*Lời giải:* **Có**. Phép cộng/trừ vẫn đúng; điều kiện không âm chỉ dành cho một số thao tác **tìm theo ngưỡng**.

**Bài 3 — Ngưỡng 7.** Với dãy mẫu, `end` đầu tiên thỏa `P[end]>=7` là gì?

*Lời giải:* **6**, vì `P[5]=6<7` và `P[6]=10>=7`.

**Bài 4 — Vị trí đơn vị thứ 7.** Nếu các giá trị mẫu là tần suất, đơn vị thứ 7 nằm ở chỉ số nào?

*Lời giải:* **5**, bằng `end-1=6-1`.

**Bài 5 — Tiền tố trùng nhau.** Vì sao `P[1]=P[2]` không làm binary lifting sai?

*Lời giải:* Số 0 khiến tiền tố **bằng nhau**, nhưng vẫn không giảm; thuật toán chỉ bỏ qua những biên có tổng **nhỏ hơn** target.

**Bài 6 — Ngưỡng đúng bằng tổng.** Dãy mẫu tổng 12, `first_prefix_at_least(12)` trả 7 hay 8?

*Lời giải:* **7**, vì `P[7]=12` và vị trí cuối `a[7]=0` không làm tổng tăng.

**Bài 7 — Target vượt tổng.** Với cùng dãy, `first_prefix_at_least(13)` là gì?

*Lời giải:* **None**, vì `P[n]=12<13`.

**Bài 8 — Target=0.** Dãy không âm có `P[0]=0`. Biên đầu tiên đạt `target=0` là gì?

*Lời giải:* **0**, do tiền tố rỗng đã đủ.

**Bài 9 — Mảng rỗng.** Với `a=[]`, kết quả của ngưỡng 0 và ngưỡng 1 lần lượt là gì?

*Lời giải:* **0** và **None**.

**Bài 10 — Điều kiện không giảm.** Vì sao mọi `a[i]>=0` tương đương `P` không giảm trong số học chính xác?

*Lời giải:* `P[i+1]-P[i]=a[i]`, nên mọi bước tiền tố không giảm đúng khi mọi phần tử không âm.

**Bài 11 — Phản ví dụ âm.** Với `a=[5,-10,10]`, ngưỡng 4 được đạt đầu tiên ở end nào?

*Lời giải:* **end=1**; `P=[0,5,-5,5]`, không đơn điệu.

**Bài 12 — Lỗi binary lifting.** Trên dãy ở bài 11, binary lifting kiểu chuẩn có thể trả end nào sai?

*Lời giải:* **3**. Bước đầu thử `P[2]=-5<4` và bỏ qua nhầm end=1.

**Bài 13 — Vùng bit[6].** Trong BIT 1-based, `bit[6]` có vùng ngoài nào?

*Lời giải:* `lowbit(6)=2`, vùng `[4,6)`.

**Bài 14 — Đường prefix(7).** Những ô BIT nào được đọc để tính `P[7]`?

*Lời giải:* `bit[7],bit[6],bit[4]`; đường chỉ số **7→6→4→0**.

**Bài 15 — Tổng đoạn rỗng.** `range_sum(5,5)` có hợp lệ không và trả gì?

*Lời giải:* **Hợp lệ**, tổng 0.

**Bài 16 — Đường cập nhật.** Với n=8, cộng điểm ở `pos=5` đi qua những ô BIT nào?

*Lời giải:* Bắt đầu `i=6` rồi `i=8`; sửa **bit[6], bit[8]**.

**Bài 17 — Chọn step.** Với n=13, lũy thừa 2 lớn nhất không vượt n là bao nhiêu?

*Lời giải:* **8**, tức `1<<(13.bit_length()-1)`, và các bước thử sau là 4,2,1.

**Bài 18 — Vì sao dùng bit[candidate]?** Trong một bước lifting, nếu `idx` chia hết cho `2*step` thì vùng `bit[idx+step]` nằm ở đâu?

*Lời giải:* Vì `lowbit(idx+step)=step`, vùng là **`[idx,idx+step)`**, nên cộng được vào `acc=P[idx]`.

**Bài 19 — So sánh chuẩn.** Để tìm biên đầu tiên có `P[end]>=target`, khi nào chấp nhận nhảy?

*Lời giải:* Chỉ khi `candidate<=n` và `acc+bit[candidate]<target`; không bỏ qua biên đã đạt ngưỡng.

**Bài 20 — O(log² n).** Vì sao binary search ngoài Fenwick có thể tốn O(log² n)?

*Lời giải:* Có O(log n) bước chọn mid và mỗi `prefix_sum(mid)` tốn O(log n).

**Bài 21 — O(log n).** Vì sao lifting trực tiếp trên BIT chỉ cần O(log n)?

*Lời giải:* Mỗi bit lũy thừa 2 được thử một lần; tổng mới của candidate lấy trực tiếp từ `acc+bit[candidate]` trong O(1) mỗi bước.

**Bài 22 — Cập nhật âm hợp lệ.** Với tần suất `a[6]=2`, có được gọi `add_count(6,-2)` không?

*Lời giải:* **Có**, vì kết quả là 0, vẫn không âm. Gọi `-3` sẽ làm tần suất âm và phải bị từ chối.

**Bài 23 — Kth theo đoạn.** Với dãy mẫu, đơn vị thứ 4 trong `[2,7)` nằm ở chỉ số nào?

*Lời giải:* `a[2]=3` đơn vị đầu, `a[3]=1` đơn vị thứ 4, nên chỉ số **3**.

**Bài 24 — Ngưỡng từ l.** Với dãy mẫu, từ `l=2` cần tổng ít nhất 5, biên r đầu tiên là gì?

*Lời giải:* `P[2]=2`, cần `P[r]>=7`. Biên đầu tiên là **r=6**.

**Bài 25 — Ngưỡng không dương từ l.** Nếu yêu cầu `sum([l,r))>=0` với mảng không âm và cho phép r=l, biên đầu tiên là gì?

*Lời giải:* **r=l**, vì đoạn rỗng có tổng 0.

**Bài 26 — Dấu ≥ so với >.** Với dãy mẫu, `P[end]>=6` và `P[end]>6` có biên đầu tiên lần lượt là gì?

*Lời giải:* **4** và **6**. Các tiền tố end=4,5 đều bằng 6.

**Bài 27 — Duy trì điều kiện.** Tại sao lớp `FenwickInt` lưu `negative_count`?

*Lời giải:* Để kiểm tra mọi phần tử không âm trong **O(1)** trước tìm ngưỡng, đồng thời duy trì số âm sau từng cập nhật điểm.

**Bài 28 — Cấu trúc cho số âm.** Nếu dữ liệu có số âm nhưng cần tìm biên đầu tiên đạt target sau cập nhật điểm, có lựa chọn nào?

*Lời giải:* **Segment tree lưu tổng và tổng tiền tố lớn nhất**, tìm theo nhánh O(log n) dù tiền tố không đơn điệu.

**Bài 29 — Công thức ghép max tiền tố.** Với nút trái L và phải R, `best(parent)` được tính thế nào?

*Lời giải:* `max(best(L),sum(L)+best(R))`, vì tiền tố lớn nhất hoặc ở toàn trái, hoặc qua trái rồi thêm tiền tố phải.

**Bài 30 — Miền khóa thưa.** Nếu các khóa có giá trị 100,700,9000, chỉ số Fenwick có phải chính các khóa ấy không?

*Lời giải:* **Không nhất thiết.** Nén tọa độ theo thứ tự khóa, lưu tần suất ở các chỉ số 0..m−1, rồi ánh xạ kết quả về khóa.

**Bài 31 — Chọn cấu trúc.** Nếu chỉ có dữ liệu tĩnh, hỏi nhiều tổng đoạn, không cập nhật và không tìm theo ngưỡng động, Fenwick có phải luôn tối ưu?

*Lời giải:* **Không**. Prefix sum có thể đơn giản hơn: xây O(n), truy vấn O(1) trên mảng không đổi.

**Bài 32 — Tổng chi phí.** Với n phần tử, u cập nhật điểm, q truy vấn tổng và t lần tìm ngưỡng hợp lệ, Fenwick có tổng thời gian bao nhiêu nếu xây tuyến tính?

*Lời giải:* **O(n+(u+q+t)log n)** trong mô hình phép toán số học O(1).

## 34. Tổng kết

**Cây Fenwick** hỗ trợ cập nhật một điểm và truy vấn tổng tiền tố trong O(log n) nhờ bất biến:

```text
lowbit(i) = i & -i
bit[i] = sum(a[i-lowbit(i):i])
```

Từ đó, tổng đoạn **0-based nửa mở `[l,r)`** được tính bằng:

```text
range_sum(l,r) = prefix_sum(r) - prefix_sum(l)
```

Công thức này **không cần các phần tử không âm**, mà dựa trên phép cộng/trừ để khử phần tiền tố trái.

Nếu cần tìm **biên tiền tố đầu tiên đạt ngưỡng**:

```text
first_prefix_at_least(target)
    = min {end : P[end]>=target}
```

thì binary lifting trực tiếp trên BIT cho O(log n), **với tiền điều kiện tổng tiền tố không giảm** — tương đương mọi giá trị hiện tại `a[i]>=0` trong số học chính xác. Mỗi lần thử khối `step`, chỉ chấp nhận biên mới nếu `acc+bit[candidate]<target`; cuối cùng trả `idx+1`, hoặc `None` nếu ngưỡng vượt tổng.

Với bài toán **tần suất nguyên không âm**, biên `end` chuyển thành vị trí **đơn vị thứ k** bằng `end-1`, và có thể mở rộng tìm thứ k trong một đoạn `[l,r)` bằng ngưỡng toàn cục `P[l]+k`. Ngược lại, **mảng có số âm** có thể làm kết quả binary lifting sai; khi ấy cần quét trực tiếp hoặc dùng một cấu trúc giàu thông tin hơn như **segment tree lưu max tiền tố**.

Điều quan trọng nhất không phải thuộc lòng phép nhảy bit, mà là hiểu **đại lượng truy vấn, ý nghĩa chỉ số, bất biến mỗi ô, điều kiện đơn điệu và quy tắc xử lý ngưỡng bằng nhau**. Đó là cơ sở để chọn đúng thuật toán và chứng minh kết quả, thay vì chỉ có một đoạn mã chạy nhanh trên vài ví dụ.

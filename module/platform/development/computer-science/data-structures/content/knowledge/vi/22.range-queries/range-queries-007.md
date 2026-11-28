# Cây Fenwick: vùng phụ trách của mỗi chỉ số

Giả sử có một mảng ghi số đơn hàng theo ngày. Hệ thống thường xuyên nhận hai yêu cầu:

- **Cập nhật một ngày:** ngày thứ `i` có thêm `delta` đơn hàng.
- **Tính tổng một khoảng ngày:** tổng đơn hàng từ vị trí `l` đến trước vị trí `r` là bao nhiêu?

Nếu quét mảng để hỏi tổng, mỗi truy vấn có thể tốn O(n). Nếu dùng mảng tổng tiền tố, truy vấn O(1) nhưng khi một phần tử thay đổi, nhiều tổng tiền tố phải cập nhật, có thể tốn O(n).

**Cây Fenwick** (*Fenwick tree*, còn gọi là *Binary Indexed Tree*, viết tắt **BIT**) là cách lưu **một số tổng đoạn được chọn khéo léo**. Mỗi chỉ số `i` trong BIT chịu trách nhiệm cho một đoạn liên tiếp kết thúc tại `i`. Nhờ quy tắc tính đoạn từ bit 1 thấp nhất của chỉ số, ta có thể:

- **Cộng một điểm:** O(log n).
- **Tính tổng tiền tố:** O(log n).
- **Tính tổng đoạn:** O(log n) bằng hiệu hai tổng tiền tố.
- **Xây từ mảng:** O(n) với thuật toán lan truyền tổng từ chỉ số nhỏ đến chỉ số lớn.
- **Lưu trữ:** O(n) bộ nhớ.

Điều cốt lõi cần hiểu không phải chỉ là hai dòng `i += i & -i` và `i -= i & -i`, mà là **vì sao `bit[i]` lưu đúng một đoạn**, những đoạn nào ghép thành một tiền tố, và những ô nào phải thay đổi khi cập nhật một phần tử.

Bài thuộc chương **Truy vấn đoạn** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, xây nền tảng về mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị. Trọng tâm là bất biến, thao tác và độ phức tạp thời gian/bộ nhớ để chọn cấu trúc dữ liệu phù hợp. Ta sẽ diễn giải Fenwick từ vùng phụ trách của mỗi chỉ số, chứng minh các bước truy vấn/cập nhật, rồi cài đặt và kiểm tra bằng Python.

## 1. Bài toán và hai hệ chỉ số phải phân biệt

Cho mảng dữ liệu có `n` phần tử:

```text
a[0], a[1], ..., a[n-1]
```

Giao diện người dùng của bài sử dụng **chỉ số từ 0, đoạn nửa mở `[l,r)`**:

```text
0 <= l <= r <= n

range_sum(l,r) = a[l] + ... + a[r-1]
```

Các trường hợp:

- `range_sum(0,n)`: tổng toàn mảng.
- `range_sum(l,l)`: đoạn rỗng, tổng bằng 0.
- `range_sum(2,5)`: ba phần tử ở vị trí 2,3,4.
- `point_add(i,delta)`: thay `a[i]` bằng `a[i]+delta`, với `0<=i<n`.

**Nhưng ở bên trong BIT, ta dùng chỉ số từ 1.**

```text
Mảng ngoài:     a[0] a[1] a[2] ... a[n-1]
BIT nội bộ:     bit[1] bit[2] bit[3] ... bit[n]
                bit[0] không sử dụng
```

Quy tắc ánh xạ:

```text
Phần tử ngoài a[j] tương ứng vị trí nội bộ x = j + 1.
```

Chọn **1-based nội bộ** làm cho biểu thức `i & -i` luôn dương khi `i>=1`, còn truy vấn tiền tố dừng gọn ở chỉ số 0. Nếu áp dụng trực tiếp vòng lặp cập nhật của hệ 1-based cho `i=0`, `i & -i=0` và vòng lặp có thể không tiến lên.

### Tiền tố cần hỏi có biên exclusive

Định nghĩa:

```text
prefix_sum(end) = a[0] + a[1] + ... + a[end-1]
```

trong đó `0<=end<=n`. Dù phương thức nhận `end` theo hệ chỉ số ngoài, giá trị `end` chính là **số phần tử đầu tiên**, cũng là chỉ số BIT nội bộ dùng để bắt đầu truy vấn.

```text
range_sum(l,r) = prefix_sum(r) - prefix_sum(l)
```

Đây là công thức mà BIT sẽ hỗ trợ, với chi phí O(log n) cho mỗi tiền tố.

## 2. Lowbit: bit 1 thấp nhất của một số nguyên dương

Với số nguyên dương `i`, đặt:

```text
lowbit(i) = i & (-i)
```

Ký hiệu `&` là phép **AND theo bit**.

`lowbit(i)` là **giá trị lũy thừa 2 ứng với bit 1 ở vị trí thấp nhất** trong biểu diễn nhị phân của `i`.

Ví dụ:

```text
i = 12
Nhị phân: 1100₂

Bit 1 thấp nhất nằm ở hàng 2².
lowbit(12) = 4
```

Một số ví dụ:

| `i` | Dạng nhị phân | `lowbit(i)` |
|---:|---|---:|
| 1 | 0001 | 1 |
| 2 | 0010 | 2 |
| 3 | 0011 | 1 |
| 4 | 0100 | 4 |
| 5 | 0101 | 1 |
| 6 | 0110 | 2 |
| 7 | 0111 | 1 |
| 8 | 1000 | 8 |
| 9 | 1001 | 1 |
| 10 | 1010 | 2 |
| 12 | 1100 | 4 |
| 16 | 10000 | 16 |

### Tại sao `i & -i` lấy được đúng bit ấy?

Trong biểu diễn **bù hai** (*two's complement*) quen thuộc, `-i` giữ lại bit 1 thấp nhất của `i` và biến những bit 1 cao hơn theo cách mà phép AND lọc ra đúng bit đó.

Ví dụ `i=12`, xét trên 8 bit:

```text
 i = 00001100
-i = 11110100
   -----------
 & = 00000100 = 4
```

Trong Python, số nguyên âm dùng biểu diễn logic tương thích với phép toán bit bù hai có mở rộng dấu; biểu thức `i & -i` vẫn trả đúng kết quả cho số nguyên dương.

**Chỉ dùng `lowbit(i)` cho `i>0` trong các vòng lặp Fenwick 1-based.** Với `i=0`, lowbit bằng 0, không giúp con trỏ tiến lên.

### Hàm Python

```python
def lowbit(i):
    if type(i) is not int or i <= 0:
        raise ValueError("lowbit yêu cầu số nguyên dương")
    return i & -i


assert lowbit(1) == 1
assert lowbit(6) == 2
assert lowbit(12) == 4
assert lowbit(16) == 16
```

Trong các hàm nội bộ đã kiểm tra chỉ số, ta có thể viết ngắn `i & -i` mà không phải gọi hàm kiểm tra ở từng bước.

## 3. Bất biến trung tâm: mỗi bit[i] chịu trách nhiệm một đoạn

Với mỗi chỉ số nội bộ `i` từ 1 đến `n`, đặt:

```text
w = lowbit(i)
```

**Bất biến của Fenwick tổng**:

```text
bit[i] = tổng các phần tử nội bộ từ i-w+1 đến i, lấy cả hai đầu
```

Viết theo đoạn nửa mở 1-based:

```text
bit[i] = sum(internal_a[i-w+1 : i+1])
```

Hoặc quy đổi về mảng ngoài 0-based:

```text
bit[i] = sum(a[i-w : i])
```

Công thức cuối là cách dễ kiểm chứng nhất với Python: **`bit[i]` là tổng đoạn ngoài `[i-lowbit(i),i)`**.

Chiều dài đoạn đúng bằng `lowbit(i)`.

### Ví dụ quan trọng

```text
bit[1]  chịu trách nhiệm [0,1)  -> 1 phần tử
bit[2]  chịu trách nhiệm [0,2)  -> 2 phần tử
bit[3]  chịu trách nhiệm [2,3)  -> 1 phần tử
bit[4]  chịu trách nhiệm [0,4)  -> 4 phần tử
bit[5]  chịu trách nhiệm [4,5)  -> 1 phần tử
bit[6]  chịu trách nhiệm [4,6)  -> 2 phần tử
bit[7]  chịu trách nhiệm [6,7)  -> 1 phần tử
bit[8]  chịu trách nhiệm [0,8)  -> 8 phần tử
```

Đây là điểm phân biệt BIT với “một mảng tổng tiền tố đầy đủ”: **không phải mọi `bit[i]` đều là tổng của `[0,i)`**. Chỉ một số chỉ số như 1,2,4,8,16,... tình cờ có đoạn bắt đầu từ 0.

### Bảng vùng phụ trách đến chỉ số 16

| `i` nội bộ | `lowbit(i)` | Đoạn nội bộ đóng | Đoạn ngoài `[l,r)` |
|---:|---:|---|---|
| 1 | 1 | `[1,1]` | `[0,1)` |
| 2 | 2 | `[1,2]` | `[0,2)` |
| 3 | 1 | `[3,3]` | `[2,3)` |
| 4 | 4 | `[1,4]` | `[0,4)` |
| 5 | 1 | `[5,5]` | `[4,5)` |
| 6 | 2 | `[5,6]` | `[4,6)` |
| 7 | 1 | `[7,7]` | `[6,7)` |
| 8 | 8 | `[1,8]` | `[0,8)` |
| 9 | 1 | `[9,9]` | `[8,9)` |
| 10 | 2 | `[9,10]` | `[8,10)` |
| 11 | 1 | `[11,11]` | `[10,11)` |
| 12 | 4 | `[9,12]` | `[8,12)` |
| 13 | 1 | `[13,13]` | `[12,13)` |
| 14 | 2 | `[13,14]` | `[12,14)` |
| 15 | 1 | `[15,15]` | `[14,15)` |
| 16 | 16 | `[1,16]` | `[0,16)` |

**Lưu ý:** các vùng của **những ô khác nhau có thể chồng lên nhau**. Ví dụ vùng `bit[4]` chứa vùng `bit[2]`. Điều này không làm câu trả lời bị đếm trùng, vì một phép truy vấn tiền tố chỉ chọn **một tập ô có vùng rời nhau**.

## 4. Minh họa bằng một dãy số cụ thể

Chọn dãy tám phần tử:

```text
Chỉ số ngoài:  0   1   2   3   4   5   6   7
a:             3   2  -1   6   5   4  -3   3
```

Từ bất biến vùng phụ trách:

| Ô BIT | Đoạn ngoài | Phép cộng | Giá trị |
|---|---|---|---:|
| `bit[1]` | `[0,1)` | 3 | 3 |
| `bit[2]` | `[0,2)` | 3+2 | 5 |
| `bit[3]` | `[2,3)` | -1 | -1 |
| `bit[4]` | `[0,4)` | 3+2-1+6 | 10 |
| `bit[5]` | `[4,5)` | 5 | 5 |
| `bit[6]` | `[4,6)` | 5+4 | 9 |
| `bit[7]` | `[6,7)` | -3 | -3 |
| `bit[8]` | `[0,8)` | 3+2-1+6+5+4-3+3 | 19 |

Bảng BIT thật (có ô 0 không sử dụng):

```text
Chỉ số BIT: 0   1   2   3    4   5   6   7    8
bit:        0   3   5  -1   10   5   9  -3   19
```

Mỗi giá trị được xem như **một tổng con đã chuẩn bị sẵn**. Truy vấn sẽ chọn những tổng con có đoạn phù hợp, tránh cộng lại từng phần tử.

## 5. Truy vấn tiền tố: đi xuống bằng i -= lowbit(i)

Muốn tìm tổng của `end` phần tử đầu tiên:

```text
prefix_sum(end) = sum(a[0:end])
```

Bắt đầu từ chỉ số BIT nội bộ `i=end`.

Ở mỗi bước:

1. Cộng `bit[i]` vào đáp án.
2. Bỏ qua đúng vùng mà `bit[i]` đã bao phủ bằng lệnh `i -= lowbit(i)`.
3. Lặp đến khi `i=0`.

Giả mã:

```text
PREFIX_SUM(end):
    answer = 0
    i = end

    while i > 0:
        answer += bit[i]
        i -= lowbit(i)

    return answer
```

### Vì sao đi xuống lại đúng?

Giả sử hiện tại ta còn cần tổng của đoạn `[0,i)`. Theo bất biến:

```text
bit[i] = sum(a[i-lowbit(i) : i])
```

Đây chính là **đoạn ở cuối** của tiền tố chưa xử lý.

Sau khi cộng `bit[i]`, phần chưa xử lý là:

```text
[0, i-lowbit(i))
```

Vậy đặt:

```text
i = i - lowbit(i)
```

là đúng. Mỗi vòng lặp xử lý một đoạn mới, không chồng lấn đoạn cũ.

### Ví dụ prefix_sum(7)

Tổng cần tính:

```text
a[0] + ... + a[6]
= 3+2-1+6+5+4-3
= 16
```

Đường đi trong BIT:

```text
i=7, lowbit(7)=1
    bit[7] = sum([6,7)) = -3
    i <- 6

i=6, lowbit(6)=2
    bit[6] = sum([4,6)) = 5+4 = 9
    i <- 4

i=4, lowbit(4)=4
    bit[4] = sum([0,4)) = 3+2-1+6 = 10
    i <- 0

Đáp án = -3 + 9 + 10 = 16
```

Các đoạn được ghép:

```text
[0,4) + [4,6) + [6,7) = [0,7)
```

Chúng **phủ hết tiền tố và không có phần tử nào được cộng hai lần**.

### Ví dụ prefix_sum(13)

Nếu mảng dài ít nhất 13 phần tử, đường đi chỉ số là:

```text
13 -> 12 -> 8 -> 0
```

Các vùng lần lượt:

```text
bit[13] quản lý [12,13)
bit[12] quản lý [8,12)
bit[8]  quản lý [0,8)
```

Hợp các vùng là `[0,13)`. Đây là ví dụ cho thấy các chỉ số truy vấn **không phải** 13,12,11,... mà nhảy theo từng khối có độ dài là `lowbit`.

## 6. Vì sao tiền tố chỉ đi O(log n) bước?

Mỗi lần trừ:

```text
i -= i & -i
```

ta **xóa bit 1 thấp nhất** trong biểu diễn nhị phân của `i`.

Ví dụ:

```text
i=13:  1101₂
       1100₂  (12)
       1000₂  (8)
       0000₂  (0)
```

Số bước bằng **số bit 1** trong biểu diễn nhị phân của `end` (*popcount*). Con số này không vượt `floor(log2 n)+1` khi `n>0`.

Vì thế:

```text
T_prefix(end) = O(log n)
```

với `end>0`, và `prefix_sum(0)` trả 0 ngay trong O(1).

**Không phải mọi truy vấn đều thực hiện đúng log2(n) bước.** Ví dụ `prefix_sum(8)` chỉ đọc `bit[8]` một lần; `prefix_sum(7)` đọc ba ô `bit[7],bit[6],bit[4]`.

## 7. Cập nhật một điểm: đi lên bằng i += lowbit(i)

Giả sử ta muốn cộng `delta` vào phần tử ngoài `a[pos]`.

Đổi sang chỉ số nội bộ:

```text
i = pos + 1
```

Một ô `bit[j]` cần tăng `delta` **khi và chỉ khi đoạn mà nó quản lý chứa phần tử có chỉ số nội bộ i**.

Quy tắc đi lên trong Fenwick:

```text
POINT_ADD(pos, delta):
    i = pos + 1

    while i <= n:
        bit[i] += delta
        i += lowbit(i)
```

Từ một vị trí, việc tăng `i` bằng `lowbit(i)` đưa ta đến ô lớn hơn kế tiếp có **vùng phụ trách bao trùm vùng hiện tại**.

### Ví dụ cập nhật ở vị trí nội bộ 5

Giả sử `n>=16`. Đi từ `i=5`:

```text
i=5:  lowbit=1, vùng [5,5]   (nội bộ)
      i <- 6

i=6:  lowbit=2, vùng [5,6]
      i <- 8

i=8:  lowbit=8, vùng [1,8]
      i <- 16

i=16: lowbit=16, vùng [1,16]
      i <- 32 (dừng nếu n=16)
```

Tất cả các vùng đều chứa **phần tử nội bộ 5**. Vì vậy, khi phần tử ấy tăng `delta`, mỗi tổng tương ứng phải tăng đúng `delta`.

### Ví dụ trên mảng tám phần tử

Mảng ban đầu:

```text
a = [3,2,-1,6,5,4,-3,3]
bit = [0,3,5,-1,10,5,9,-3,19]
```

Cập nhật:

```text
point_add(pos=3, delta=+4)
```

Vị trí ngoài 3 tương ứng chỉ số BIT `i=4`:

```text
i=4: bit[4] từ 10 thành 14
i=8: bit[8] từ 19 thành 23
i=16: vượt n=8, dừng
```

Mảng logic sau cập nhật:

```text
a = [3,2,-1,10,5,4,-3,3]
```

Không cần sửa `bit[5]` hoặc `bit[6]` vì các đoạn `[4,5)` và `[4,6)` không chứa phần tử ngoài 3.

## 8. Vì sao cập nhật đi O(log n) bước?

Với `i>0`, viết:

```text
i = 2^k * odd
```

trong đó `odd` là số lẻ. Khi đó:

```text
lowbit(i) = 2^k
i + lowbit(i) = 2^k * (odd+1)
```

Vì `odd+1` là số chẵn, chỉ số mới chia hết cho **ít nhất** `2^(k+1)`. Nói cách khác, vị trí bit 1 thấp nhất của chỉ số tăng lên ít nhất một bậc sau mỗi bước.

Số bậc có thể tăng trước khi vượt `n` không quá O(log n). Vì thế:

```text
T_point_add = O(log n)
```

Bằng cách đi đúng theo chuỗi các vùng bao chứa vị trí đã sửa, cập nhật không cần quét tất cả ô BIT hay phần tử gốc.

## 9. Truy vấn đoạn qua hiệu hai tiền tố

Trước khi viết lớp Python, cần nhớ rằng BIT cơ bản tính **tổng tiền tố** chứ không trực tiếp có sẵn một ô cho mọi đoạn tùy ý.

Với đoạn `[l,r)`:

```text
range_sum(l,r) = prefix_sum(r) - prefix_sum(l)
```

Ví dụ trên mảng gốc:

```text
a = [3,2,-1,6,5,4,-3,3]
```

Tổng `[2,7)` gồm `-1,6,5,4,-3`:

```text
prefix_sum(7) = 16
prefix_sum(2) = 5

range_sum(2,7) = 16 - 5 = 11
```

Sau khi cộng 4 vào `a[3]`:

```text
prefix_sum(7) = 20
prefix_sum(2) = 5

range_sum(2,7) = 20 - 5 = 15
```

Mỗi tiền tố tốn O(log n), nên một truy vấn đoạn thực hiện hai lần trong:

```text
O(log n) + O(log n) = O(log n)
```

**Điều kiện:** công thức lấy hiệu hai tổng tiền tố dựa trên phép cộng có **phép trừ/nghịch đảo** phù hợp. Không nên bê nguyên BIT tổng sang truy vấn min bằng cách “trừ hai min tiền tố”.

## 10. Cài đặt Python hoàn chỉnh: FenwickSum

Lớp dưới đây dùng **0-based ở giao diện** và **1-based bên trong**. Nó hỗ trợ:

- `prefix_sum(end)`: tổng `a[0:end]`.
- `range_sum(l,r)`: tổng `a[l:r]`.
- `point_add(pos,delta)`.
- `point_assign(pos,value)`.
- `get(pos)`: đọc giá trị hiện tại.
- Xây dựng `bit` trong O(n) từ dữ liệu ban đầu.

```python
class FenwickSum:
    """BIT nội bộ 1-based, API ngoài 0-based và [l,r)."""

    def __init__(self, values):
        self._values = list(values)
        self.n = len(self._values)
        self.bit = [0] * (self.n + 1)

        # Xây BIT O(n), theo thứ tự chỉ số tăng dần.
        for i, value in enumerate(self._values, start=1):
            self.bit[i] += value
            parent = i + (i & -i)

            if parent <= self.n:
                self.bit[parent] += self.bit[i]

    def _validate_index(self, pos):
        if type(pos) is not int:
            raise TypeError("Chỉ số điểm phải là số nguyên")
        if not 0 <= pos < self.n:
            raise IndexError("Chỉ số điểm ngoài mảng")

    def _validate_range(self, l, r):
        if type(l) is not int or type(r) is not int:
            raise TypeError("Biên đoạn phải là số nguyên")
        if not 0 <= l <= r <= self.n:
            raise IndexError("Đoạn [l,r) không hợp lệ")

    def prefix_sum(self, end):
        if type(end) is not int:
            raise TypeError("Biên tiền tố phải là số nguyên")
        if not 0 <= end <= self.n:
            raise IndexError("Biên tiền tố ngoài mảng")

        answer = 0
        i = end

        while i > 0:
            answer += self.bit[i]
            i -= i & -i

        return answer

    def range_sum(self, l, r):
        self._validate_range(l, r)
        return self.prefix_sum(r) - self.prefix_sum(l)

    def point_add(self, pos, delta):
        self._validate_index(pos)
        self._values[pos] += delta

        i = pos + 1
        while i <= self.n:
            self.bit[i] += delta
            i += i & -i

    def point_assign(self, pos, value):
        self._validate_index(pos)
        delta = value - self._values[pos]
        self.point_add(pos, delta)

    def get(self, pos):
        self._validate_index(pos)
        return self._values[pos]


a = [3, 2, -1, 6, 5, 4, -3, 3]
fw = FenwickSum(a)

assert fw.bit == [0, 3, 5, -1, 10, 5, 9, -3, 19]
assert fw.prefix_sum(0) == 0
assert fw.prefix_sum(7) == 16
assert fw.prefix_sum(8) == 19
assert fw.range_sum(2, 7) == 11
assert fw.range_sum(8, 8) == 0

fw.point_add(3, 4)   # a[3]: 6 -> 10.
assert fw.get(3) == 10
assert fw.bit[4] == 14
assert fw.bit[8] == 23
assert fw.range_sum(2, 7) == 15

fw.point_assign(6, 1)  # a[6]: -3 -> 1; delta=+4.
assert fw.get(6) == 1
assert fw.range_sum(2, 7) == 19
assert fw.prefix_sum(8) == 27

# Danh sách bên ngoài không bị sửa bởi các phương thức trên.
assert a == [3, 2, -1, 6, 5, 4, -3, 3]
```

Vì lớp giữ bản sao `_values`, cập nhật thông qua phương thức không sửa danh sách đầu vào. Tuy nhiên, dấu gạch dưới `_` chỉ là **quy ước thuộc tính nội bộ của Python**, không bảo vệ trước một người gọi cố ý sửa trực tiếp `fw.bit` hoặc `fw._values`. Muốn giữ bất biến, phải sử dụng các phương thức cung cấp.

## 11. Xây BIT bằng cách thêm từng phần tử: O(n log n)

Một cách dễ hiểu để xây Fenwick là:

1. Tạo BIT gồm `n` giá trị 0.
2. Với mỗi phần tử `a[pos]`, gọi `point_add(pos,a[pos])`.

```python
def build_fenwick_slow(values):
    n = len(values)
    bit = [0] * (n + 1)

    for pos, value in enumerate(values):
        i = pos + 1

        while i <= n:
            bit[i] += value
            i += i & -i

    return bit


assert build_fenwick_slow([3, 2, -1, 6, 5, 4, -3, 3]) == [
    0, 3, 5, -1, 10, 5, 9, -3, 19
]
```

Mỗi lần cập nhật đi O(log n) ô, tổng `n` phần tử tốn **O(n log n)**.

Cách này đúng vì mỗi phần tử đóng góp `value` vào đúng những vùng phụ trách chứa nó. Tuy nhiên, khi đã có sẵn toàn bộ dữ liệu, ta có thể xây **O(n)** bằng cách lan truyền các tổng khối.

## 12. Xây BIT tuyến tính O(n) bằng cách đẩy tổng lên cha

Chỉ số cha trong cấu trúc cập nhật là:

```text
parent(i) = i + lowbit(i)
```

Với thứ tự duyệt `i=1,2,...,n`, ta làm:

```text
bit[i] += a[i-1]

parent = i + lowbit(i)
if parent <= n:
    bit[parent] += bit[i]
```

Chính là vòng xây trong `FenwickSum.__init__`. Ta cộng **toàn bộ tổng của vùng i** vào ô cha, thay vì gọi cập nhật đi dọc chuỗi nhiều lần.

### Tại sao lan truyền một lần là đủ?

Khi tới chỉ số `i`:

- `bit[i]` đã nhận giá trị `a[i-1]`.
- Các chỉ số nhỏ hơn `i` có cha là `i` đã được xử lý và **đẩy tổng hoàn chỉnh của chúng lên**.
- Vì vậy, `bit[i]` chứa tổng đúng của vùng `[i-lowbit(i),i)`.

Sau đó ta đẩy tổng này đến `parent(i)` (nếu tồn tại), nơi có một vùng lớn hơn chứa toàn bộ vùng của `i`.

Một cách hình dung:

```text
bit[1] -> bit[2] -> bit[4] -> bit[8]
bit[3] ----------> bit[4]
bit[5] -> bit[6] -> bit[8]
bit[7] ----------> bit[8]
```

Các nhánh này mô tả **đường lan truyền tổng**, không phải cây nhị phân đầy đủ kiểu segment tree.

### Truy vết vài bước đầu với n=8

```text
i=1:
    bit[1] += 3        => bit[1]=3
    đẩy bit[1] sang bit[2]  => bit[2]=3

i=2:
    bit[2] += 2        => bit[2]=5
    đẩy bit[2] sang bit[4]  => bit[4]=5

i=3:
    bit[3] += -1       => bit[3]=-1
    đẩy bit[3] sang bit[4]  => bit[4]=4

i=4:
    bit[4] += 6        => bit[4]=10
    đẩy bit[4] sang bit[8]  => bit[8]=10
```

Tiếp tục đến `i=8` ta thu `bit=[0,3,5,-1,10,5,9,-3,19]`.

### Mã xây tách riêng

```python
def build_fenwick_linear(values):
    n = len(values)
    bit = [0] * (n + 1)

    for i, value in enumerate(values, start=1):
        bit[i] += value
        parent = i + (i & -i)

        if parent <= n:
            bit[parent] += bit[i]

    return bit


data = [3, 2, -1, 6, 5, 4, -3, 3]

assert build_fenwick_linear(data) == build_fenwick_slow(data)
```

Vì mỗi chỉ số chỉ được xét một lần, và trong mỗi lần làm O(1) phép số học, xây tuyến tính tốn **O(n) thời gian** và **O(n) bộ nhớ**.

**Không nhầm thời gian xây và thời gian cập nhật sau này:** xây một lần từ toàn bộ mảng có thể O(n); nhưng **một cập nhật điểm bất kỳ sau khi xây** vẫn cần O(log n) để bảo toàn những vùng phụ trách liên quan.

## 13. Chứng minh tính đúng của truy vấn tiền tố

Bất biến BIT đã định nghĩa:

```text
bit[i] = sum(a[i-lowbit(i):i])
```

Xét thuật toán `prefix_sum(end)`.

### Bất biến vòng lặp

Gọi `p` là biên ban đầu (`p=end`). Tại đầu mỗi vòng:

> `answer` là tổng của các phần tử trong `[i,p)` đã xử lý; `[0,i)` là phần chưa xử lý.

Ban đầu `i=p`, đoạn đã xử lý `[p,p)` rỗng, `answer=0`.

Khi `i>0`:

```text
bit[i] = sum(a[i-lowbit(i):i])
```

Lấy vùng này và chuyển `i' = i-lowbit(i)`. Khi đó:

```text
answer' = answer + bit[i]
```

là tổng đoạn `[i',p)`; phần chưa xử lý còn `[0,i')`. Bất biến được duy trì.

Khi `i=0`, phần chưa xử lý rỗng, nên:

```text
answer = sum(a[0:p])
```

đúng bằng tổng tiền tố yêu cầu.

### Chứng minh không đếm trùng

Mỗi bước chọn đoạn kết thúc tại `i`; bước tiếp theo bắt đầu từ biên trái của đoạn cũ. Do đó các đoạn chọn được **liền kề nhưng không chồng lấn**, dù các vùng BIT nói chung có thể chồng lấn khi nhìn toàn bộ bảng.

Đây là khác biệt quan trọng giữa **những vùng BIT tồn tại** và **những vùng được chọn trong một truy vấn cụ thể**.

## 14. Chứng minh tính đúng của cập nhật điểm

Giả sử phần tử nội bộ `x=pos+1` tăng `delta`.

Theo bất biến vùng phụ trách, `bit[j]` phải tăng `delta` nếu:

```text
j-lowbit(j)+1 <= x <= j
```

hay dưới dạng mảng ngoài:

```text
x-1 thuộc [j-lowbit(j),j)
```

Các vùng chứa `x` tạo thành chuỗi bao chứa tăng dần dọc theo:

```text
x
-> x+lowbit(x)
-> ...
-> chỉ số > n
```

Ở mỗi bước, chỉ số cha quản lý một đoạn rộng hơn chứa toàn bộ đoạn của con. Những ô ngoài chuỗi ấy không có đoạn chứa `x`, nên không được cập nhật.

Vòng `point_add`:

```text
while i <= n:
    bit[i] += delta
    i += lowbit(i)
```

chạm đúng các ô cần sửa. Sau khi cập nhật, mọi tổng của các vùng vẫn bằng tổng dữ liệu mới.

### Nếu bỏ sót một ô cha?

Giả sử cập nhật phần tử ngoài 3 nhưng chỉ sửa `bit[4]`, quên `bit[8]`. Khi hỏi `prefix_sum(8)`, thuật toán chỉ đọc `bit[8]` nên sẽ trả **tổng cũ**, dù `bit[4]` đã đúng. Vì vậy không thể chỉ sửa ô BIT tại vị trí tương ứng mà phải **đi lên hết các cha hợp lệ**.

## 15. Trường hợp biên: n=0, n=1 và các chỉ số đặc biệt

### Mảng rỗng

Với `n=0`:

```python
empty = FenwickSum([])

assert empty.bit == [0]
assert empty.prefix_sum(0) == 0
assert empty.range_sum(0, 0) == 0

try:
    empty.point_add(0, 5)
except IndexError:
    pass
else:
    raise AssertionError("Mảng rỗng không có phần tử để cập nhật")
```

Không có chỉ số BIT dương nào, nên không có bước cập nhật/truy vấn nào đi vào vòng lặp.

### Mảng một phần tử

```python
one = FenwickSum([9])

assert one.bit == [0, 9]
assert one.prefix_sum(1) == 9
assert one.range_sum(0, 1) == 9
assert one.range_sum(1, 1) == 0

one.point_add(0, -4)
assert one.range_sum(0, 1) == 5
```

### Biên end=n và vị trí pos=n

Hai khái niệm rất khác nhau:

- `prefix_sum(n)` hợp lệ: tổng **n** phần tử đầu.
- `point_add(n,delta)` **không** hợp lệ với mảng có chỉ số ngoài `0..n-1`.

`range_sum(n,n)` cũng hợp lệ vì đó là đoạn rỗng ở cuối.

### Không chấp nhận biên âm hoặc đảo

```python
fw = FenwickSum([3, 2, -1, 6])

for l, r in [(-1, 2), (3, 2), (0, 5)]:
    try:
        fw.range_sum(l, r)
    except IndexError:
        pass
    else:
        raise AssertionError("Biên đoạn sai phải bị từ chối")

try:
    fw.prefix_sum(True)
except TypeError:
    pass
else:
    raise AssertionError("Không chấp nhận Boolean làm biên")
```

Dùng `type(x) is int` là **lựa chọn chính sách API** để từ chối `True`/`False`, vốn là lớp con của `int` trong Python.

## 16. Mô hình chi phí và so sánh với prefix sum

Cho `n` phần tử, `q` truy vấn tổng đoạn và `u` cập nhật cộng điểm:

| Cấu trúc | Xây từ mảng | Tổng đoạn | Cộng một điểm | Bộ nhớ phụ |
|---|---:|---:|---:|---:|
| Mảng thường + quét | O(1) ngoài dữ liệu | O(k), k=r-l | O(1) | O(1) |
| Prefix sum tĩnh | O(n) | **O(1)** | O(n) nếu duy trì bảng | O(n) |
| **Fenwick cho tổng** | **O(n)** xây tuyến tính | **O(log n)** | **O(log n)** | **O(n)** |
| Segment tree tổng | O(n) | O(log n) | O(log n) | O(n) |
| Sqrt decomposition tổng | O(n) | O(√n) | O(1) | O(n/B) ngoài mảng |

Nếu dùng cách xây BIT bằng `n` lần `point_add`, riêng bước xây là **O(n log n)**; bản cài ở trên dùng cách xây **O(n)**.

### Tổng thời gian cho chuỗi thao tác

- Quét trực tiếp: có thể O(qn+u) trong trường hợp xấu nhất.
- Prefix nếu xây lại sau cập nhật: có thể O(n+q+un) trong mô hình đơn giản.
- Fenwick với xây tuyến tính: **O(n+(q+u)log n)**.

Đây là lý do Fenwick phù hợp khi **truy vấn tổng và cập nhật điểm xen kẽ trực tuyến**.

### Fenwick khác segment tree ở đâu?

Cả hai có thể xử lý tổng và cập nhật một điểm trong O(log n), nhưng:

- Fenwick lưu **một tổng theo đoạn lowbit ở mỗi chỉ số** và dùng một mảng có `n+1` ô.
- Segment tree lưu tổng của nhiều đoạn theo một cấu trúc phân nhánh rõ ràng; thường linh hoạt hơn với nhiều phép tổng hợp và cập nhật đoạn có lazy.
- Fenwick thường **ngắn gọn, ít bộ nhớ hơn về hằng số và dễ cài** cho tổng/XOR.
- Không nên suy từ tổng rằng Fenwick có thể xử lý mọi phép kết hợp trong cùng cách cài đặt.

## 17. Vì sao Fenwick không tự giải min đoạn tùy ý?

Truy vấn tổng đoạn lấy hiệu:

```text
sum([l,r)) = prefix_sum(r) - prefix_sum(l)
```

Phép cộng trên số nguyên có phần tử đơn vị 0 và phép nghịch đảo là `-x`. Nhờ phép nghịch đảo, ta **khử được phần tiền tố bên trái**.

Min không có phép trừ tương ứng:

```text
min([0,r)) và min([0,l))
```

không đủ để suy ra `min([l,r))`.

Ví dụ:

```text
a = [1, 9, 5]
b = [1, 7, 8]
```

Hai mảng có cùng các min tiền tố sau mỗi phần tử là `[1,1,1]`, nhưng min trên `[1,3)` lần lượt là 5 và 7.

Ngoài ra, nếu chỉ lưu min của vùng BIT, việc tăng một phần tử từng là min có thể làm cần tính lại toàn vùng, không thể chỉ cộng `delta`.

**Kết luận:** BIT chuẩn trong bài này là BIT cho **phép cộng số**. Có các biến thể Fenwick đặc thù cho min dưới những điều kiện thao tác nhất định, nhưng chúng không có cùng hợp đồng cập nhật/query tổng quát với `FenwickSum`.

## 18. Prefix XOR và những giới hạn của phép gộp

Với XOR bit:

```text
x XOR x = 0
```

và XOR có tính kết hợp, giao hoán. Vì vậy có thể xây Fenwick để cập nhật điểm bằng XOR và lấy XOR đoạn qua:

```text
XOR([l,r)) = XOR_prefix(r) XOR XOR_prefix(l)
```

Tuy nhiên, các biểu thức trong `FenwickSum` như:

```python
delta = value - old_value
answer = prefix_sum(r) - prefix_sum(l)
```

phải được **đổi theo phép toán**. Không chỉ đổi tên `sum` thành `xor` mà vẫn giữ dấu cộng/trừ.

### Phép nối chuỗi thì sao?

Nối chuỗi kết hợp nhưng **không giao hoán** và không có phép nghịch đảo tổng quát. Nếu sửa một phần tử, không có cách chỉ “cộng phần chênh” vào mọi vùng bằng thao tác nối đơn giản. BIT cộng điểm như ở đây **không phù hợp** với phép nối chuỗi tùy ý.

Nếu cần gộp các đoạn theo thứ tự và cập nhật điểm, một **segment tree monoid** là lựa chọn tự nhiên hơn.

## 19. Đổi truy vấn 1-based đóng từ đề bài

Một số đề thuật toán cho vị trí `L,R` bắt đầu từ 1 và hỏi **cả hai đầu**:

```text
1 <= L <= R <= n
```

Quy đổi vào API Fenwick:

```text
[l,r) = [L-1,R)
```

Sau đó:

```text
sum_1based(L,R) = prefix_sum(R) - prefix_sum(L-1)
```

Ví dụ trên dãy:

```text
a = [3,2,-1,6,5,4,-3,3]
```

Truy vấn đóng 1-based `[3,7]` có đúng các phần tử ngoài 0-based `[2,7)`:

```text
-1 + 6 + 5 + 4 - 3 = 11
```

### Hàm adapter

```python
def range_sum_1based_inclusive(fenwick, L, R):
    if type(L) is not int or type(R) is not int:
        raise TypeError("Biên 1-based phải là số nguyên")
    if not 1 <= L <= R <= fenwick.n:
        raise IndexError("Đoạn đóng 1-based không hợp lệ")

    return fenwick.range_sum(L - 1, R)


fw = FenwickSum([3, 2, -1, 6, 5, 4, -3, 3])

assert range_sum_1based_inclusive(fw, 3, 7) == 11
assert range_sum_1based_inclusive(fw, 1, 8) == 19
assert range_sum_1based_inclusive(fw, 8, 8) == 3
```

**Đừng đổi biên hai lần.** Mặc dù BIT bên trong cũng đánh số từ 1, adapter đã chuyển đầu vào đề bài về dạng nửa mở 0-based, rồi phương thức `range_sum` tự làm việc với `prefix_sum`. Hai lớp quy ước phục vụ hai mục đích khác nhau.

## 20. Mở rộng: cộng cả đoạn và hỏi giá trị tại một điểm

Cây Fenwick còn giúp hiểu một ứng dụng của **mảng hiệu** (*difference array*).

Nếu muốn cộng `delta` vào mọi phần tử ngoài `[l,r)`, hãy lưu các mốc thay đổi:

```text
diff[l] += delta
diff[r] -= delta        (nếu r < n)
```

Giá trị lượng tăng tại vị trí `pos` là:

```text
effect(pos) = diff[0] + ... + diff[pos]
```

Vậy ta có thể dùng **FenwickSum trên mảng hiệu**, để:

- Cập nhật hai mốc bằng **hai lần point_add**, mỗi lần O(log n).
- Hỏi lượng tăng tại `pos` bằng **prefix_sum(pos+1)**, O(log n).

### Cài đặt tối giản

```python
class RangeAddPointQuery:
    def __init__(self, values):
        self.base = tuple(values)
        self.n = len(self.base)
        self.diff_bit = FenwickSum([0] * self.n)

    def range_add(self, l, r, delta):
        if type(l) is not int or type(r) is not int:
            raise TypeError("Biên phải là số nguyên")
        if not 0 <= l <= r <= self.n:
            raise IndexError("Đoạn không hợp lệ")

        if l == r:
            return

        self.diff_bit.point_add(l, delta)
        if r < self.n:
            self.diff_bit.point_add(r, -delta)

    def get(self, pos):
        if type(pos) is not int:
            raise TypeError("pos phải là số nguyên")
        if not 0 <= pos < self.n:
            raise IndexError("pos ngoài mảng")

        return self.base[pos] + self.diff_bit.prefix_sum(pos + 1)


rq = RangeAddPointQuery([2, 5, 1, 4, 3])

rq.range_add(1, 4, 3)
rq.range_add(2, 5, -2)

assert [rq.get(i) for i in range(5)] == [2, 8, 2, 5, 1]
```

**Phân biệt:** cấu trúc `RangeAddPointQuery` hỗ trợ **range add + point query**; nó không có ngay phương thức **range sum O(log n)** sau nhiều range add.

Nếu cần vừa **cộng cả đoạn** vừa **hỏi tổng cả đoạn** trực tuyến, một lựa chọn là **hai Fenwick tree** với công thức trọng số chỉ số, hoặc **segment tree với lazy propagation**. Không thể giả định một BIT chỉ lưu các mốc hiệu sẽ tự cho tổng đoạn bằng hiệu hai tiền tố của chính các mốc ấy.

## 21. Nhìn theo “rừng cây” và quan hệ cha

Fenwick thường được gọi là “cây” dù được lưu trong **một mảng** và không tạo đối tượng nút có con trỏ.

Với mỗi chỉ số nội bộ `i`, có thể định nghĩa:

```text
parent(i) = i + lowbit(i)
```

nếu `parent(i)<=n`.

Một vài đường đi:

```text
1 -> 2 -> 4 -> 8
3 ------> 4 -> 8
5 -> 6 ------> 8
7 ------------> 8
```

Sơ đồ thể hiện quan hệ **ô nào phải nhận tổng đóng góp của ô nào khi xây/cập nhật**.

### Có phải mỗi nút có đúng hai con?

Không. Fenwick **không phải cây nhị phân đầy đủ**. Các mối liên kết cha có thể tạo ra các nút với số con khác nhau, và đường query khác đường update.

Tên *Binary Indexed Tree* nhấn mạnh **cấu trúc chỉ số nhị phân và phép lowbit**, không phải mọi nút đều có đúng hai nhánh con giống một binary tree thông thường.

### “Vùng phụ trách” và “nút cha” là hai cách nhìn cùng bất biến

- **Vùng phụ trách:** `bit[i]` lưu tổng của `[i-lowbit(i),i)`.
- **Đường cha:** khi một phần tử tăng, mọi ô có vùng chứa phần tử đó đều nhận cùng `delta`.

Vùng được mở rộng theo phép `parent(i)`, còn tiền tố được tách thành các vùng rời bằng phép `i-=lowbit(i)`. Hai chiều di chuyển là lý do BIT có thể vừa **cập nhật** vừa **truy vấn tiền tố** nhanh.

## 22. Trực quan so sánh các đường đi

Xét `n=16` và cập nhật phần tử ngoài `pos=8`, tương ứng nội bộ `i=9`.

```text
UPDATE(pos=8):

i=9,  lowbit=1,  bit[9]  quản lý [8,9)
i=10, lowbit=2,  bit[10] quản lý [8,10)
i=12, lowbit=4,  bit[12] quản lý [8,12)
i=16, lowbit=16, bit[16] quản lý [0,16)
i=32 -> dừng
```

Tất cả bốn vùng đều chứa vị trí ngoài 8.

Ngược lại, truy vấn `prefix_sum(13)`:

```text
QUERY(end=13):

i=13, lowbit=1,  đọc bit[13] cho [12,13)
i=12, lowbit=4,  đọc bit[12] cho [8,12)
i=8,  lowbit=8,  đọc bit[8]  cho [0,8)
i=0  -> dừng
```

Ba vùng truy vấn **rời nhau** và phủ toàn bộ `[0,13)`.

| Đặc điểm | Cập nhật một điểm | Truy vấn tiền tố |
|---|---|---|
| Điểm bắt đầu nội bộ | `pos+1` | `end` |
| Hướng đi | Chỉ số **tăng** | Chỉ số **giảm** |
| Công thức bước tiếp | `i += lowbit(i)` | `i -= lowbit(i)` |
| Dừng | `i>n` | `i=0` |
| Ý nghĩa vùng | Mọi vùng chứa phần tử sửa | Các vùng rời phủ tiền tố |
| Thời gian | O(log n) | O(log n) |

Hai vòng lặp trông gần giống nhau nhưng **không được hoán đổi phép cộng và phép trừ chỉ số**.

## 23. Fenwick 0-based thuần túy: có thể nhưng khác công thức

Ngoài cách 1-based, có một dạng Fenwick sử dụng **chỉ số nội bộ từ 0** với các phép toán:

```text
g(i) = i & (i+1)

bit[i] quản lý đoạn đóng 0-based [g(i), i]
```

Nếu muốn tính tổng tiền tố **đóng** đến i:

```text
while i >= 0:
    answer += bit[i]
    i = (i & (i+1)) - 1
```

Để cộng một điểm:

```text
while i < n:
    bit[i] += delta
    i = i | (i+1)
```

Đó là một cách viết **tương đương về ý tưởng**, nhưng **khác công thức nhảy** so với 1-based. Không được lấy `i & -i` theo cách 1-based rồi bắt đầu cập nhật tại `i=0`.

### Vì sao bài chọn 1-based bên trong?

Trong việc giảng dạy, công thức:

```text
lowbit(i) = i & -i
range(bit[i]) = [i-lowbit(i),i)  trong mảng ngoài
```

giúp trực tiếp nhìn thấy một ô chịu trách nhiệm cho bao nhiêu phần tử. 0-based thuần túy cũng đúng, nhưng nên học **một hệ chỉ số cho thật chắc** trước khi đổi cách cài.

## 24. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Dùng `bit[0]` làm ô dữ liệu của Fenwick 1-based | `lowbit(0)=0`, có thể lặp vô hạn | Giữ bit[0] không sử dụng |
| Quên `pos+1` khi cập nhật điểm ngoài 0-based | Cập nhật sai vùng, có thể không tiến | Đổi sang chỉ số BIT nội bộ |
| Dùng `i-=lowbit(i)` cho update | Bỏ sót các vùng cha chứa vị trí sửa | Update dùng **cộng lowbit** |
| Dùng `i+=lowbit(i)` cho query | Đi sai hướng hoặc vượt n | Query dùng **trừ lowbit** |
| Nghĩ `bit[i]` luôn là tổng `a[0:i]` | Hiểu và kiểm thử sai | Dùng vùng `[i-lowbit(i),i)` |
| Cập nhật chỉ `bit[pos+1]` | Các tổng vùng cha lỗi thời | Đi lên đến khi `i>n` |
| Đọc mọi ô BIT từ 1 đến end để tính tiền tố | Đếm trùng vì vùng các ô chồng lấn | Chỉ đi theo đường `i-=lowbit(i)` |
| Dùng `prefix_sum(r)-prefix_sum(l-1)` cho `[l,r)` | Sai lệch đầu trái | Dùng `P(r)-P(l)` |
| Coi biên `r` thuộc `[l,r)` | Cộng thừa phần tử | Biên phải là exclusive |
| Không cho `end=n` | Không lấy được tổng toàn mảng | `end=n` hợp lệ |
| Cho phép `point_add(n,delta)` | Cập nhật ngoài dữ liệu | Yêu cầu `0<=pos<n` |
| Đọc chỉ số âm theo Python | Có thể trả giá trị không đúng hợp đồng | Từ chối biên âm |
| Nhầm `point_assign` với `point_add` | Tổng sai vì gán không phải cộng | Dùng `delta=new-old` |
| Xây BIT bằng các lần add rồi báo O(n) | Đánh giá sai độ phức tạp | Add n lần O(nlog n); xây lan truyền O(n) |
| Trộn công thức BIT 0-based và 1-based | Sai đường đi, lặp vô hạn | Chọn và giữ nhất quán một biến thể |
| Dùng BIT tổng để hỏi min bằng trừ hai tiền tố | Không có phép nghịch đảo cho min | Dùng cấu trúc/min biến thể thích hợp |
| Dùng một BIT hiệu để vừa range-add vừa range-sum | Lấy nhầm tổng hiệu thay vì tổng giá trị | Cần hai BIT/cấu trúc khác |
| Sửa trực tiếp `_values` mà không sửa bit | Bất biến giữa dữ liệu và BIT bị phá | Cập nhật qua phương thức |
| Quên phân tích kích thước số | Cận thực tế có thể khác O(log n) bit-op | Nêu mô hình chi phí số học |
| Bỏ qua đoạn rỗng `[l,l)` | Có thể báo sai hoặc vượt biên | Sum rỗng trả 0 theo hợp đồng |

## 25. Kiểm thử bất biến và kiểm tra bằng bản chậm

Một cách chắc chắn để xác minh triển khai là dùng mảng thường làm **oracle**: trên dữ liệu nhỏ, so sánh mọi tổng đoạn và các giá trị BIT với công thức vùng phụ trách.

### Kiểm tra từng vùng bit[i]

```python
def assert_fenwick_invariant(fw):
    for i in range(1, fw.n + 1):
        w = i & -i
        expected = sum(fw._values[i - w:i])
        assert fw.bit[i] == expected


fw = FenwickSum([3, 2, -1, 6, 5, 4, -3, 3])
assert_fenwick_invariant(fw)

fw.point_add(3, 4)
assert_fenwick_invariant(fw)

fw.point_assign(6, 1)
assert_fenwick_invariant(fw)
```

Mỗi ô được đối chiếu với đúng đoạn `[i-lowbit(i),i)` mà nó phụ trách. Đây là cách kiểm tra trực tiếp **bất biến chính**, thay vì chỉ xem vài đáp án truy vấn.

### Kiểm tra mọi đoạn trên mảng nhỏ

```python
def assert_all_range_sums(fw):
    for l in range(fw.n + 1):
        for r in range(l, fw.n + 1):
            expected = sum(fw._values[l:r])
            assert fw.range_sum(l, r) == expected


for sample in [
    [],
    [9],
    [0, 0, 0],
    [2, -5, 7, 3, -1],
    [3, 2, -1, 6, 5, 4, -3, 3],
]:
    fw = FenwickSum(sample)
    assert_fenwick_invariant(fw)
    assert_all_range_sums(fw)
```

Đây là phép kiểm thử O(n²) truy vấn trên mảng nhỏ, không phải một phương án xử lý toàn bộ truy vấn lớn trong ứng dụng.

### Kiểm tra chuỗi cập nhật

```python
values = [3, 2, -1, 6, 5, 4, -3, 3]
fw = FenwickSum(values)
reference = values.copy()

operations = [
    ("add", 3, 4),
    ("assign", 6, 1),
    ("add", 0, -7),
    ("assign", 7, 0),
    ("add", 5, 10),
]

for kind, pos, x in operations:
    if kind == "add":
        fw.point_add(pos, x)
        reference[pos] += x
    else:
        fw.point_assign(pos, x)
        reference[pos] = x

    assert_fenwick_invariant(fw)

    for l in range(len(reference) + 1):
        for r in range(l, len(reference) + 1):
            assert fw.range_sum(l, r) == sum(reference[l:r])
```

Kiểm thử xen kẽ query/update phát hiện được lỗi **chỉ thay đổi mảng gốc mà quên cập nhật BIT**, hoặc ngược lại.

### Tình huống nhất thiết nên thử

- Mảng rỗng, một phần tử; n là lũy thừa 2 và không phải lũy thừa 2.
- Dữ liệu dương, âm, bằng 0 và các tổng tiền tố không đơn điệu.
- `prefix_sum(0)`, `prefix_sum(n)` và `range_sum(n,n)`.
- Update tại vị trí đầu, giữa và cuối; update bằng 0.
- Gán điểm thành chính giá trị cũ.
- Nhiều cập nhật liên tiếp rồi truy vấn.
- Biên âm, vượt n, đảo biên, Boolean.
- So sánh xây O(n) với xây bằng n lần cập nhật.

## 26. Lựa chọn Fenwick trong thực tế

Với một bài toán mới, hãy kiểm tra những câu hỏi sau:

1. **Có cần cập nhật sau khi xây không?** Nếu không, prefix sum thường đơn giản hơn cho tổng.
2. **Cập nhật gì?** Cộng/gán điểm, cộng đoạn hay gán đoạn?
3. **Truy vấn gì?** Tổng tiền tố, tổng đoạn, min/max, XOR, hay bản tóm tắt không giao hoán?
4. **Có dùng được nghịch đảo tiền tố không?** Tổng số nguyên và XOR có; min tổng quát không có.
5. **Dữ liệu có bao nhiêu phần tử và thao tác?** `n, q, u` quyết định áp lực hiệu năng.
6. **Chỉ số đầu vào là 0-based hay 1-based, đoạn đóng hay nửa mở?**
7. **Phải giữ dữ liệu gốc không?** Nếu cần point-assign nhanh, lưu giá trị cũ để tính delta.
8. **Giá trị có nguy cơ tràn hoặc mất chính xác không?**

Fenwick phù hợp khi đề cần **tổng và thay đổi điểm trực tuyến** với ít mã, bộ nhớ O(n), mỗi thao tác O(log n). Nó cũng là nền tảng của những biến thể xử lý cập nhật đoạn, nhưng mỗi biến thể phải được **chứng minh đúng theo vùng phụ trách và phép toán** của nó.

## 27. Bài tập tự luyện có lời giải

**Bài 1 — Lowbit.** Tính `lowbit(6)`, `lowbit(12)` và `lowbit(16)`.

*Lời giải:* Lần lượt **2, 4, 16**.

**Bài 2 — Biểu diễn nhị phân.** Số 13 có dạng `1101₂`. Khi liên tục trừ lowbit đến 0, các giá trị nhận được là gì?

*Lời giải:* **13 → 12 → 8 → 0**.

**Bài 3 — Vùng của bit[6].** Trong BIT 1-based, `bit[6]` phụ trách đoạn nào? Viết cả nội bộ và ngoài 0-based.

*Lời giải:* `lowbit(6)=2`, nội bộ **`[5,6]` đóng**, tương ứng ngoài **`[4,6)`**.

**Bài 4 — Vùng của bit[12].** `bit[12]` có độ dài bao nhiêu và phụ trách phần tử ngoài nào?

*Lời giải:* `lowbit(12)=4`; vùng ngoài **`[8,12)`**, gồm chỉ số 8,9,10,11.

**Bài 5 — Vùng của bit[8].** Với mảng n≥8, `bit[8]` là tổng của đoạn nào?

*Lời giải:* `lowbit(8)=8`; đó là **`[0,8)`**, tổng 8 phần tử đầu.

**Bài 6 — Bảng BIT.** Với `a=[3,2,-1,6,5,4,-3,3]`, hãy viết `bit[1..8]`.

*Lời giải:* **`[3,5,-1,10,5,9,-3,19]`**.

**Bài 7 — Prefix(7).** Những ô BIT nào được đọc khi hỏi tiền tố 7 phần tử?

*Lời giải:* Đường **7 → 6 → 4 → 0**; đọc `bit[7],bit[6],bit[4]`.

**Bài 8 — Tổng tiền tố.** Với bảng ở bài 6, `prefix_sum(7)` bằng bao nhiêu?

*Lời giải:* `-3+9+10=16`.

**Bài 9 — Ghép vùng.** Ba ô ở bài 7 phụ trách những đoạn nào của mảng ngoài?

*Lời giải:* **`[6,7)`, `[4,6)`, `[0,4)`**; chúng rời nhau và hợp thành `[0,7)`.

**Bài 10 — Tổng đoạn.** Với mảng trên, `range_sum(2,7)` bằng bao nhiêu?

*Lời giải:* `prefix_sum(7)-prefix_sum(2)=16-5=11`.

**Bài 11 — Đường cập nhật.** Nếu n=16, cập nhật phần tử ngoài pos=4 thì các ô BIT nào thay đổi?

*Lời giải:* Chỉ số nội bộ `i=5`; đường đi **5 → 6 → 8 → 16**.

**Bài 12 — Cập nhật cụ thể.** Với n=8, tăng `a[3]` thêm 4 thì các ô BIT nào thay đổi?

*Lời giải:* Nội bộ `i=4`; tăng **`bit[4]` và `bit[8]`** thêm 4.

**Bài 13 — Tổng sau cập nhật.** Sau bài 12, `range_sum(2,7)` mới bằng bao nhiêu?

*Lời giải:* Tổng cũ 11, đoạn chứa vị trí 3, nên tổng mới **15**.

**Bài 14 — Gán điểm.** Nếu `a[6]=-3` và muốn gán thành 1, phải truyền delta nào cho point_add?

*Lời giải:* `delta=1-(-3)=4`.

**Bài 15 — Dừng truy vấn.** Vì sao khi truy vấn prefix cần dừng khi `i=0`?

*Lời giải:* `bit[0]` không có vùng phụ trách trong BIT 1-based và `lowbit(0)=0`; tiếp tục sẽ không làm con trỏ giảm.

**Bài 16 — Dừng cập nhật.** Vì sao vòng point_add dùng `i<=n`?

*Lời giải:* Chỉ có các ô dữ liệu BIT từ 1 đến n. Khi `i>n` không còn vùng phụ trách hợp lệ nào cần cập nhật.

**Bài 17 — O(log n).** Vì sao truy vấn tiền tố chỉ mất O(log n) bước?

*Lời giải:* Mỗi lần trừ lowbit **xóa một bit 1** của chỉ số, có nhiều nhất O(log n) bit cần xóa.

**Bài 18 — O(log n) cập nhật.** Vì sao đường cập nhật không đi qua n ô?

*Lời giải:* `i+=lowbit(i)` làm tăng ít nhất một bậc vị trí bit 1 thấp nhất, nên chỉ có **O(log n)** bước trước khi vượt n.

**Bài 19 — Xây dựng.** Xây BIT bằng n lần point_add khác xây tuyến tính như thế nào?

*Lời giải:* N lần point_add mất **O(n log n)**; duyệt tăng chỉ số và đẩy tổng đến cha chỉ mất **O(n)**.

**Bài 20 — Đoạn rỗng.** `range_sum(n,n)` có hợp lệ không? `point_add(n,3)` thì sao?

*Lời giải:* `range_sum(n,n)` hợp lệ và trả **0**. `point_add(n,3)` không hợp lệ vì chỉ số điểm ngoài là 0..n−1.

**Bài 21 — 1-based đóng.** Truy vấn `[3,7]` 1-based đóng đổi sang đoạn ngoài nửa mở nào?

*Lời giải:* **`[2,7)`** 0-based; tính bằng `prefix_sum(7)-prefix_sum(2)`.

**Bài 22 — Bất biến.** Phát biểu chính xác nội dung `bit[i]` theo mảng ngoài.

*Lời giải:* **`bit[i]=sum(a[i-lowbit(i):i])`**, với `1<=i<=n`.

**Bài 23 — Quên cập nhật cha.** Nếu sửa `bit[4]` nhưng không sửa `bit[8]` khi thay `a[3]`, truy vấn nào dễ phát hiện lỗi?

*Lời giải:* `prefix_sum(8)`, vì nó đọc **bit[8]** và sẽ không thấy delta.

**Bài 24 — Min đoạn.** Vì sao không thể dùng hiệu hai min tiền tố như hiệu hai tổng tiền tố?

*Lời giải:* Min **không có nghịch đảo để khử tiền tố**; các min tiền tố không giữ đủ thông tin cho min trên đoạn giữa.

**Bài 25 — Range add.** Để cộng delta vào `[l,r)` bằng Fenwick trên mảng hiệu, cần ghi những mốc nào?

*Lời giải:* Cộng **delta ở l** và **−delta ở r nếu r<n**; giá trị điểm i lấy tổng tiền tố các mốc đến i.

**Bài 26 — Kích thước.** Với mảng n phần tử, BIT 1-based cần bao nhiêu ô nếu lưu cả vị trí 0 không sử dụng?

*Lời giải:* **n+1** ô, từ `bit[0]` đến `bit[n]`.

**Bài 27 — Chọn cấu trúc.** Mảng tĩnh, có một triệu truy vấn tổng nhưng không cập nhật: prefix sum hay Fenwick nên được cân nhắc trước?

*Lời giải:* **Prefix sum** thường đơn giản và nhanh hơn cho tổng tĩnh: xây O(n), truy vấn O(1), trong khi Fenwick query O(log n).

**Bài 28 — Truy vấn/cập nhật xen kẽ.** Với n giá trị, q truy vấn tổng và u lần cộng điểm, nếu xây Fenwick tuyến tính thì tổng thời gian là gì?

*Lời giải:* **O(n+(q+u)log n)** với phép số học O(1); bộ nhớ O(n).

## 28. Tổng kết

Fenwick không lưu mọi tổng tiền tố. Nó lưu **những tổng khối có ranh giới xác định bởi bit 1 thấp nhất**:

```text
lowbit(i) = i & -i

bit[i] = sum(a[i-lowbit(i):i])
```

Đây là bất biến giải thích toàn bộ thuật toán:

- **Truy vấn tiền tố:** lấy vùng cuối `bit[i]`, rồi đi sang phần chưa xử lý bằng `i-=lowbit(i)`.
- **Cập nhật một điểm:** sửa mọi vùng chứa điểm bằng đường đi `i+=lowbit(i)`.
- **Tổng đoạn `[l,r)`:** lấy `prefix_sum(r)-prefix_sum(l)`.

Các vùng được chọn khi truy vấn **rời nhau và phủ đúng tiền tố**, còn những vùng phải sửa khi cập nhật **đều chứa vị trí đã thay đổi**. Cả hai đường đi có nhiều nhất O(log n) bước. Với phép cộng số học được coi O(1), Fenwick hỗ trợ **O(log n) mỗi lần truy vấn/cập nhật**, có thể xây trong **O(n)** và dùng **O(n)** bộ nhớ.

Hãy giữ tách biệt **API ngoài 0-based `[l,r)`** với **BIT nội bộ 1-based**. Tránh nhầm `bit[i]` với tổng của mọi phần tử từ đầu đến i, tránh dùng lowbit(0), và không áp dụng hiệu tiền tố cho phép min khi không có nghịch đảo. Nắm chắc **vùng phụ trách của mỗi chỉ số** sẽ giúp bạn suy luận đúng cả Fenwick cơ bản lẫn các biến thể cập nhật đoạn và truy vấn động sau này.

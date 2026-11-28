# Cập nhật điểm và truy vấn tiền tố bằng Fenwick

Hãy tưởng tượng một bảng thống kê doanh thu có một ô cho mỗi ngày. Nhân viên liên tục nhập giao dịch mới, khiến doanh thu một ngày tăng hoặc giảm; đồng thời người quản lý hỏi **tổng doanh thu từ đầu tháng đến ngày k** hay **tổng trong một khoảng ngày**. Dữ liệu thay đổi ngay trong khi các câu hỏi được gửi tới, nên không thể xây một bảng tổng tiền tố duy nhất rồi sử dụng mãi.

**Cây Fenwick** (*Fenwick tree* hay *Binary Indexed Tree — BIT*) giải quyết tình huống **cập nhật một điểm và truy vấn tổng tiền tố trực tuyến** trong **O(log n)** thời gian mỗi thao tác. Nó dùng một mảng phụ, trong đó mỗi ô lưu tổng của một đoạn có kích thước được xác định bằng **bit 1 thấp nhất của chỉ số**.

Bài học này tập trung vào hai thao tác vận hành:

1. **Cập nhật điểm:** tăng `a[pos]` thêm `delta` hoặc gán một giá trị mới.
2. **Truy vấn tiền tố:** lấy tổng `a[0]+...+a[end-1]`; từ đó lấy tổng đoạn bất kỳ bằng hiệu hai tiền tố.

Ta sẽ truy vết từng ô được đọc/sửa, hiểu bất biến được duy trì sau mỗi bước, lập trình bằng Python và thử các trường hợp biên. Đây là một bài trong chương **Truy vấn đoạn** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, thuộc lộ trình học cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, chú trọng **bất biến, thao tác và độ phức tạp thời gian/bộ nhớ** để chọn cấu trúc phù hợp.

## 1. Bài toán: nhiều cập nhật điểm xen kẽ truy vấn

Cho một mảng số ban đầu:

```text
a = [3, 1, 4, 1, 5, 9, 2, 6]
n = 8
```

Một chuỗi thao tác có thể là:

```text
Hỏi tổng của 7 phần tử đầu.
Tăng phần tử tại chỉ số 4 thêm 3.
Hỏi tổng của 7 phần tử đầu lần nữa.
Gán phần tử tại chỉ số 2 thành -1.
Hỏi tổng của đoạn [2,7).
```

Ta muốn mỗi thao tác phản ánh **đúng trạng thái mới nhất**, không cần quét toàn bộ mảng sau mỗi cập nhật.

### Hợp đồng chỉ số của bài

Mọi phương thức công khai dùng **chỉ số ngoài 0-based**:

- `point_add(pos, delta)` cập nhật phần tử tại `pos`, với `0 <= pos < n`.
- `point_assign(pos, value)` gán phần tử tại `pos` bằng `value`.
- `prefix_sum(end)` lấy **`end` phần tử đầu tiên**, với `0 <= end <= n`.
- `range_sum(l,r)` lấy tổng đoạn **nửa mở `[l,r)`**, với `0 <= l <= r <= n`.

Định nghĩa:

```text
prefix_sum(0) = 0
prefix_sum(end) = a[0] + ... + a[end-1]

range_sum(l,r) = prefix_sum(r) - prefix_sum(l)
```

**Quan trọng:** `prefix_sum(5)` nghĩa là **năm phần tử ở chỉ số 0..4**, không phải các phần tử đến và gồm `a[5]`.

### Vì sao bài toán này cần cấu trúc dữ liệu động?

Nếu chỉ có truy vấn trên mảng tĩnh, tổng tiền tố `P` đủ để trả lời O(1):

```text
P[0]=0
P[k+1]=P[k]+a[k]
```

Nhưng khi `a[i]` tăng `delta`, mọi `P[k]` với `k>i` cũng phải thay đổi `delta`. Cách duy trì trực tiếp có thể tốn O(n) cho một lần cập nhật.

Fenwick không lưu tất cả các tiền tố riêng rẽ; nó lưu **một tập các tổng khối có cấu trúc**, giúp cả cập nhật và truy vấn chỉ cần đụng tới O(log n) ô.

## 2. Fenwick dùng chỉ số nội bộ từ 1

Mảng ngoài vẫn dùng chỉ số 0 để thuận tiện trong Python. Nhưng mảng `bit` của Fenwick dùng **chỉ số nội bộ từ 1**:

```text
a:       a[0] a[1] a[2] ... a[n-1]
BIT:     bit[1] bit[2] bit[3] ... bit[n]

bit[0] là ô đệm, không lưu tổng đoạn.
```

Ánh xạ một phần tử:

```text
Vị trí ngoài pos -> vị trí BIT i = pos + 1
```

Nhưng với truy vấn **tiền tố có biên exclusive**:

```text
prefix_sum(end) bắt đầu từ i = end
```

Không cộng thêm 1 vào `end`: vì `end` vốn đã biểu thị **số phần tử đầu tiên**, tức là vị trí nội bộ của phần tử cuối của tiền tố cần hỏi.

| Thao tác ngoài | Chỉ số đầu tiên trong BIT | Lý do |
|---|---:|---|
| `point_add(0,delta)` | 1 | `a[0]` ↔ vị trí 1 |
| `point_add(4,delta)` | 5 | `a[4]` ↔ vị trí 5 |
| `prefix_sum(0)` | 0 | Tiền tố rỗng |
| `prefix_sum(5)` | 5 | Tổng `a[0:5]` |
| `prefix_sum(n)` | n | Tổng toàn mảng |

Đây là nguồn gây lỗi lệch chỉ số phổ biến nhất khi cài BIT lần đầu.

## 3. Lowbit và độ dài vùng mà một ô quản lý

Với `i` là **số nguyên dương**, định nghĩa:

```text
lowbit(i) = i & (-i)
```

Trong đó `&` là phép AND bit. Kết quả là lũy thừa 2 biểu thị **bit 1 thấp nhất** trong dạng nhị phân của `i`.

Ví dụ:

```text
i = 12 = 1100₂
lowbit(12) = 4 = 0100₂

i = 10 = 1010₂
lowbit(10) = 2 = 0010₂

i = 8 = 1000₂
lowbit(8) = 8 = 1000₂
```

Bảng nhanh:

| `i` | Nhị phân | `lowbit(i)` |
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

### Vì sao dùng `i & -i`?

Trong biểu diễn bù hai cho số nguyên âm (two's complement), `-i` làm cho phép AND với `i` chỉ giữ lại bit 1 thấp nhất. Ví dụ với 8 bit:

```text
  12 = 00001100
 -12 = 11110100
       --------
   & = 00000100 = 4
```

Python hỗ trợ thao tác bit trên số nguyên âm với hành vi tương thích biểu diễn bù hai có mở rộng dấu vô hạn, nên `i & -i` cho kết quả mong muốn với `i>0`.

### Không dùng lowbit(0) làm bước nhảy

```text
0 & -0 = 0
```

Nếu cập nhật bắt đầu tại `i=0` và viết `i += i & -i`, chỉ số không tăng và vòng lặp có thể không kết thúc.

Vì vậy **cập nhật điểm 0-based phải đổi sang `i=pos+1`** trước khi chạy vòng lặp 1-based.

## 4. Bất biến của BIT: bit[i] lưu tổng đoạn nào?

Đặt:

```text
w = lowbit(i)
```

Với mọi `1 <= i <= n`:

```text
bit[i] = a[i-w] + a[i-w+1] + ... + a[i-1]
```

Hay viết đúng quy ước nửa mở:

```text
bit[i] = sum(a[i-lowbit(i):i])
```

**`bit[i]` luôn chứa tổng của một đoạn kết thúc ngay trước chỉ số ngoài `i` và dài đúng `lowbit(i)`.**

Đây là bất biến phải đúng sau khi xây, sau mọi cập nhật và trước mỗi truy vấn.

### Bảng các vùng với n=8

| Ô BIT | `lowbit(i)` | Đoạn ngoài `[l,r)` | Số phần tử |
|---|---:|---|---:|
| `bit[1]` | 1 | `[0,1)` | 1 |
| `bit[2]` | 2 | `[0,2)` | 2 |
| `bit[3]` | 1 | `[2,3)` | 1 |
| `bit[4]` | 4 | `[0,4)` | 4 |
| `bit[5]` | 1 | `[4,5)` | 1 |
| `bit[6]` | 2 | `[4,6)` | 2 |
| `bit[7]` | 1 | `[6,7)` | 1 |
| `bit[8]` | 8 | `[0,8)` | 8 |

Sơ đồ trực quan:

```text
Chỉ số ngoài:  0   1   2   3   4   5   6   7
a:            3   1   4   1   5   9   2   6

bit[1]:       [3]
bit[2]:       [3, 1]
bit[3]:               [4]
bit[4]:       [3, 1, 4, 1]
bit[5]:                       [5]
bit[6]:                       [5, 9]
bit[7]:                               [2]
bit[8]:       [3, 1, 4, 1, 5, 9, 2, 6]
```

Các vùng trong **toàn bảng** có thể chồng nhau: `bit[4]` chứa hai vị trí do `bit[2]` quản lý. Tuy nhiên, **những vùng được chọn trong một lần truy vấn tiền tố** sẽ **rời nhau**, nên không đếm trùng.

## 5. Xây một bảng BIT bằng tay

Với mảng:

```text
a = [3, 1, 4, 1, 5, 9, 2, 6]
```

Tính từng giá trị theo vùng phụ trách:

| Ô | Đoạn được gộp | Giá trị |
|---|---|---:|
| `bit[1]` | 3 | 3 |
| `bit[2]` | 3+1 | 4 |
| `bit[3]` | 4 | 4 |
| `bit[4]` | 3+1+4+1 | 9 |
| `bit[5]` | 5 | 5 |
| `bit[6]` | 5+9 | 14 |
| `bit[7]` | 2 | 2 |
| `bit[8]` | 3+1+4+1+5+9+2+6 | 31 |

Kết quả:

```text
Chỉ số bit: 0  1  2  3  4  5   6  7   8
bit:        0  3  4  4  9  5  14  2  31

bit[0] = 0 chỉ là ô đệm.
```

Kiểm tra vài tổng:

```text
bit[6] = sum(a[4:6]) = 5+9 = 14
bit[7] = sum(a[6:7]) = 2
bit[8] = sum(a[0:8]) = 31
```

Không phải mọi `bit[i]` đều bằng tổng tiền tố `a[0:i]`. Ví dụ `bit[6]=14`, trong khi `sum(a[0:6])=23`.

## 6. Truy vấn tiền tố: lấy các đoạn từ phải sang trái

Với `prefix_sum(end)`, ta bắt đầu từ `i=end`. Ô `bit[i]` chứa **đoạn cuối** của tiền tố đang chưa tính:

```text
[i-lowbit(i), i)
```

Cộng ô ấy vào đáp án, rồi chuyển sang phần còn lại ở bên trái:

```text
i -= lowbit(i)
```

Lặp lại đến `i=0`.

### Giả mã

```text
PREFIX_SUM(end):
    answer = 0
    i = end

    while i > 0:
        answer += bit[i]
        i -= lowbit(i)

    return answer
```

Khi `end=0`, vòng lặp không chạy, trả `0`: đúng tổng của đoạn rỗng.

### Truy vết prefix_sum(7)

Mảng gốc:

```text
a = [3, 1, 4, 1, 5, 9, 2, 6]
```

Tổng bảy phần tử đầu là:

```text
3+1+4+1+5+9+2 = 25
```

Fenwick thực hiện:

| Bước | `i` | `lowbit(i)` | Vùng được lấy | `bit[i]` | `answer` sau cộng |
|---:|---:|---:|---|---:|---:|
| 1 | 7 | 1 | `[6,7)` | 2 | 2 |
| 2 | 6 | 2 | `[4,6)` | 14 | 16 |
| 3 | 4 | 4 | `[0,4)` | 9 | 25 |
| 4 | 0 | — | Dừng | — | **25** |

Đường đi chỉ số:

```text
7 -> 6 -> 4 -> 0
```

Ba vùng:

```text
[6,7) + [4,6) + [0,4) = [0,7)
```

không chồng lấn và phủ đúng 7 phần tử đầu.

### Truy vết prefix_sum(8)

Vì `lowbit(8)=8`, `bit[8]` đã chứa toàn bộ `[0,8)`:

```text
i=8: answer += bit[8] = 31
i=0: dừng

prefix_sum(8) = 31
```

Một tiền tố có thể được trả lời bằng **một ô duy nhất**, trong khi tiền tố khác đọc nhiều ô. O(log n) là **cận trên**, không phải số bước cố định.

## 7. Chứng minh bất biến của vòng truy vấn

Gọi `end` ban đầu là `p`.

**Bất biến:** trước mỗi vòng, `answer` là tổng của đoạn ngoài `[i,p)` đã xử lý, còn `[0,i)` chưa xử lý.

- **Khởi tạo:** `i=p`, đoạn `[p,p)` rỗng nên `answer=0` đúng.
- **Duy trì:** `bit[i]` chứa tổng đoạn `[i-lowbit(i),i)`. Cộng nó vào `answer` nghĩa là thêm đúng phần chưa xử lý sát bên trái; đặt `i'=i-lowbit(i)`. Lúc này `answer` bằng tổng `[i',p)`.
- **Kết thúc:** khi `i=0`, không còn phần chưa xử lý. Kết quả là tổng `[0,p)`.

Chứng minh này giải thích vì sao phép trừ lowbit không chỉ là một mẹo bit, mà là thao tác **bỏ đi đúng vùng vừa cộng**.

### Vì sao truy vấn kết thúc?

Với `i>0`:

```text
lowbit(i) >= 1
```

nên mỗi vòng có `0 <= i-lowbit(i) < i`. Chỉ số giảm nguyên dương và không thể chạy mãi.

Mỗi bước xóa một bit 1 của `i`, nên có tối đa O(log n) bước.

## 8. Cập nhật điểm: từ phần tử bị sửa đi tới mọi vùng bao chứa nó

Giả sử cần thực hiện:

```text
point_add(pos, delta)
```

Nghĩa là:

```text
a[pos] <- a[pos] + delta
```

Mỗi ô `bit[i]` lưu tổng của một vùng. Nếu vùng đó chứa `pos`, tổng khối tăng đúng `delta`; nếu không chứa, nó phải giữ nguyên.

Thay vì kiểm tra tất cả `n` vùng, Fenwick dùng **đường đi cha**:

```text
i = pos + 1

while i <= n:
    bit[i] += delta
    i += lowbit(i)
```

Cộng `lowbit(i)` đưa tới ô cha tiếp theo có vùng phụ trách **bao chứa vị trí đang cập nhật**.

### Truy vết point_add(4,+3)

Ban đầu:

```text
a = [3,1,4,1,5,9,2,6]
bit = [0,3,4,4,9,5,14,2,31]
```

Cập nhật phần tử ngoài `pos=4`, giá trị `5` thành `8`.

Đổi sang BIT:

```text
i = pos + 1 = 5
```

Đường đi:

```text
i=5, lowbit=1  -> bit[5]  : 5  -> 8
i=6, lowbit=2  -> bit[6]  : 14 -> 17
i=8, lowbit=8  -> bit[8]  : 31 -> 34
i=16 > n=8    -> dừng
```

| Ô sửa | Vùng ngoài | Có chứa vị trí 4? | Giá trị mới |
|---|---|---|---:|
| `bit[5]` | `[4,5)` | Có | 8 |
| `bit[6]` | `[4,6)` | Có | 17 |
| `bit[8]` | `[0,8)` | Có | 34 |

Các ô khác không đổi:

```text
Mảng mới:
a = [3,1,4,1,8,9,2,6]

BIT mới:
bit = [0,3,4,4,9,8,17,2,34]
```

Giờ `prefix_sum(7)` đọc:

```text
bit[7] + bit[6] + bit[4]
= 2 + 17 + 9
= 28
```

Tổng tăng từ 25 lên 28, đúng vì tiền tố 7 phần tử có chứa vị trí 4.

### Không cập nhật một ô duy nhất

Nếu chỉ sửa `bit[5]` mà bỏ qua `bit[6]` và `bit[8]`, những truy vấn sử dụng tổng khối lớn hơn vẫn nhìn thấy giá trị cũ.

Ví dụ `prefix_sum(8)` chỉ đọc `bit[8]`. Nếu quên sửa ô này, truy vấn sẽ tiếp tục trả 31 thay vì 34.

## 9. Vì sao đường cập nhật có O(log n) bước?

Với `i>0`, đặt:

```text
lowbit(i) = 2^k
```

Ta có thể viết `i=2^k*t` với `t` lẻ. Khi cộng:

```text
i + lowbit(i)
= 2^k*(t+1)
```

Vì `t+1` chẵn, chỉ số mới chia hết cho `2^(k+1)`. Vậy bit 1 thấp nhất của chỉ số mới nằm ở một bậc **cao hơn**.

Trong phạm vi `1..n`, chỉ có O(log n) bậc nhị phân cần đi qua; khi chỉ số vượt n, vòng kết thúc.

### Tại sao không dùng i -= lowbit(i) cho cập nhật?

`i -= lowbit(i)` đi về những vùng ở **bên trái của một tiền tố**, dùng cho truy vấn. Khi cập nhật, ta cần các **vùng ngày càng lớn bao chứa điểm đã sửa**, nên phải đi theo `i += lowbit(i)`.

Đảo hai phép nhảy này sẽ khiến BIT sai bất biến hoặc thậm chí có thể lặp không tiến nếu trộn hệ chỉ số.

## 10. Gán một điểm: quy về cập nhật theo chênh lệch

Có hai thao tác thường bị nhầm:

- **Cộng điểm:** `a[pos] += delta`.
- **Gán điểm:** `a[pos] = new_value`.

Vòng Fenwick được xây cho **cộng một lượng chênh lệch**. Để gán, ta phải biết giá trị cũ:

```text
delta = new_value - old_value
```

Sau đó chạy cùng đường `point_add(pos,delta)`.

### Truy vết point_assign(2,-1)

Sau cập nhật trước, mảng là:

```text
a = [3,1,4,1,8,9,2,6]
bit = [0,3,4,4,9,8,17,2,34]
```

Ta muốn thay giá trị `a[2]=4` thành `-1`:

```text
old_value = 4
new_value = -1
delta = -1 - 4 = -5
```

Vị trí BIT `i=2+1=3`:

```text
i=3: bit[3] 4  -> -1
i=4: bit[4] 9  -> 4
i=8: bit[8] 34 -> 29
i=16: dừng
```

Kết quả:

```text
a = [3,1,-1,1,8,9,2,6]
bit = [0,3,4,-1,4,8,17,2,29]
```

Kiểm tra tổng bảy phần tử đầu:

```text
3+1-1+1+8+9+2 = 23
```

Qua BIT:

```text
bit[7]+bit[6]+bit[4]
= 2+17+4 = 23
```

### Khi chưa lưu mảng gốc

Nếu chỉ có BIT, có thể lấy giá trị tại `pos` bằng:

```text
old_value = prefix_sum(pos+1) - prefix_sum(pos)
```

rồi tính delta. Phương án này vẫn là O(log n), nhưng cần hai lần truy vấn tiền tố trước cập nhật, làm tăng hệ số thời gian.

Lưu một bản sao các giá trị `a` tốn thêm O(n) bộ nhớ nhưng giúp lấy `old_value` trong O(1), hợp lý khi cần gán điểm thường xuyên.

## 11. Cài đặt Python: Fenwick hỗ trợ cập nhật và truy vấn trực tuyến

Dưới đây là triển khai đầy đủ. Giao diện công khai là **0-based**, còn `bit` dùng **1-based**. Mã có kiểm tra biên, lưu snapshot dữ liệu hiện tại và hỗ trợ cả cộng điểm lẫn gán điểm.

```python
class FenwickSum:
    """Cộng/gán một điểm và tính tổng tiền tố/đoạn."""

    def __init__(self, values):
        self.values = list(values)
        self.n = len(self.values)
        self.bit = [0] * (self.n + 1)

        # Xây tuyến tính O(n).
        for i, value in enumerate(self.values, start=1):
            self.bit[i] += value
            parent = i + (i & -i)
            if parent <= self.n:
                self.bit[parent] += self.bit[i]

    def _check_pos(self, pos):
        if type(pos) is not int:
            raise TypeError("pos phải là số nguyên")
        if not 0 <= pos < self.n:
            raise IndexError("pos nằm ngoài mảng")

    def _check_end(self, end):
        if type(end) is not int:
            raise TypeError("end phải là số nguyên")
        if not 0 <= end <= self.n:
            raise IndexError("end phải thuộc [0,n]")

    def _check_range(self, l, r):
        if type(l) is not int or type(r) is not int:
            raise TypeError("l và r phải là số nguyên")
        if not 0 <= l <= r <= self.n:
            raise IndexError("Đoạn [l,r) không hợp lệ")

    def point_add(self, pos, delta):
        self._check_pos(pos)

        self.values[pos] += delta

        i = pos + 1
        while i <= self.n:
            self.bit[i] += delta
            i += i & -i

    def point_assign(self, pos, value):
        self._check_pos(pos)
        delta = value - self.values[pos]
        self.point_add(pos, delta)

    def prefix_sum(self, end):
        self._check_end(end)

        answer = 0
        i = end
        while i > 0:
            answer += self.bit[i]
            i -= i & -i

        return answer

    def range_sum(self, l, r):
        self._check_range(l, r)
        return self.prefix_sum(r) - self.prefix_sum(l)

    def get(self, pos):
        self._check_pos(pos)
        return self.values[pos]


a = [3, 1, 4, 1, 5, 9, 2, 6]
fw = FenwickSum(a)

assert fw.bit == [0, 3, 4, 4, 9, 5, 14, 2, 31]
assert fw.prefix_sum(7) == 25
assert fw.prefix_sum(8) == 31
assert fw.range_sum(2, 7) == 21

fw.point_add(4, 3)
assert fw.values == [3, 1, 4, 1, 8, 9, 2, 6]
assert fw.bit == [0, 3, 4, 4, 9, 8, 17, 2, 34]
assert fw.prefix_sum(7) == 28

fw.point_assign(2, -1)
assert fw.values == [3, 1, -1, 1, 8, 9, 2, 6]
assert fw.bit == [0, 3, 4, -1, 4, 8, 17, 2, 29]
assert fw.prefix_sum(7) == 23
assert fw.range_sum(2, 7) == 19

# Mã không sửa danh sách ban đầu do đã tạo một bản sao.
assert a == [3, 1, 4, 1, 5, 9, 2, 6]
```

### Thứ tự cập nhật mảng gốc và BIT

Trong `point_add`, ta sửa `values[pos]` và các ô `bit`. Về mặt đơn luồng và không có ngoại lệ, sau khi phương thức trả về, hai biểu diễn **đồng bộ**.

Nếu một hệ thống cần xử lý đa luồng, giao dịch thất bại giữa chừng, hay nhiều đối tượng truy cập đồng thời, phải bổ sung cơ chế đồng bộ/giao dịch phù hợp. Mã này minh họa thuật toán **tuần tự**, không tuyên bố có tính nguyên tử trong môi trường đồng thời.

## 12. Các kết quả kiểm tra biên

Trường hợp biên quan trọng hơn vẻ ngoài ngắn gọn của các vòng lặp.

### Mảng rỗng

```python
empty = FenwickSum([])

assert empty.bit == [0]
assert empty.prefix_sum(0) == 0
assert empty.range_sum(0, 0) == 0

try:
    empty.point_add(0, 1)
except IndexError:
    pass
else:
    raise AssertionError("Mảng rỗng không có vị trí để cập nhật")
```

Không có ô BIT dương nào và cập nhật điểm phải bị từ chối.

### Mảng một phần tử

```python
single = FenwickSum([7])

assert single.bit == [0, 7]
assert single.prefix_sum(1) == 7
assert single.range_sum(0, 1) == 7

single.point_add(0, -3)
assert single.get(0) == 4
assert single.prefix_sum(1) == 4

single.point_assign(0, 10)
assert single.prefix_sum(1) == 10
assert single.range_sum(1, 1) == 0
```

### Cập nhật delta bằng 0 và gán về giá trị cũ

```python
fw = FenwickSum([2, -3, 5])
before = fw.bit.copy()

fw.point_add(1, 0)
fw.point_assign(2, 5)

assert fw.bit == before
assert fw.values == [2, -3, 5]
```

Cả hai thao tác là no-op về mặt giá trị, nhưng mã vẫn xử lý hợp lệ.

### Biên âm, vượt n hoặc đảo

```python
fw = FenwickSum([2, -3, 5])

for l, r in [(-1, 2), (2, 1), (0, 4)]:
    try:
        fw.range_sum(l, r)
    except IndexError:
        pass
    else:
        raise AssertionError("Phải từ chối biên không hợp lệ")

try:
    fw.point_add(3, 1)
except IndexError:
    pass
else:
    raise AssertionError("pos=n không phải chỉ số phần tử")

try:
    fw.prefix_sum(True)
except TypeError:
    pass
else:
    raise AssertionError("Không dùng Boolean làm chỉ số")
```

Việc từ chối Boolean bằng `type(x) is int` là quyết định giao diện trong ví dụ; Python xem `bool` là lớp con của `int`, nên nếu không kiểm tra riêng, `True` có thể bị hiểu thành 1.

## 13. Truy vấn tổng đoạn sau mỗi cập nhật

Với hợp đồng `[l,r)`:

```text
range_sum(l,r) = prefix_sum(r) - prefix_sum(l)
```

Ta tính hai tiền tố từ **cùng trạng thái đã cập nhật**. Do các phép cập nhật đã sửa đúng những tổng con trong BIT, hiệu trả đúng tổng của đoạn.

### Truy vết trên ví dụ chính

Ban đầu:

```text
a = [3,1,4,1,5,9,2,6]
P(7) = 25
P(2) = 4
```

Truy vấn `[2,7)`:

```text
P(7) - P(2) = 25 - 4 = 21
```

Sau `point_add(4,+3)`:

```text
P(7) = 28
P(2) = 4

sum([2,7)) = 28 - 4 = 24
```

Sau `point_assign(2,-1)`, tức giảm vị trí 2 đi 5:

```text
P(7) = 23
P(2) = 4

sum([2,7)) = 23 - 4 = 19
```

Vì `pos=2` nằm trong đoạn `[2,7)`, lần gán này tác động trực tiếp đến đáp án. Còn nếu sửa một vị trí `pos<2`, cả hai tiền tố `P(7)` và `P(2)` đều thay đổi cùng delta, nên **hiệu không đổi**.

### Hai trường hợp đáng chú ý

- `range_sum(l,l)=0` vì hai tiền tố trùng nhau.
- `range_sum(0,n)=prefix_sum(n)` vì `prefix_sum(0)=0`.

Không cần mã riêng cho hai trường hợp này nếu đã kiểm tra biên đúng.

## 14. Ví dụ thao tác kiểu nhật ký sự kiện

Một hệ thống có thể nhận các sự kiện theo thứ tự:

```text
Q 0 8       # hỏi tổng toàn mảng
A 4 3       # cộng 3 vào a[4]
Q 0 8       # hỏi lại
S 2 -1      # gán a[2] = -1
Q 2 7       # hỏi đoạn [2,7)
Q 3 3       # hỏi đoạn rỗng
```

Một vòng xử lý lệnh có thể sử dụng các phương thức của `FenwickSum`:

```python
operations = [
    ("sum", 0, 8),
    ("add", 4, 3),
    ("sum", 0, 8),
    ("assign", 2, -1),
    ("sum", 2, 7),
    ("sum", 3, 3),
]

fw = FenwickSum([3, 1, 4, 1, 5, 9, 2, 6])
answers = []

for kind, x, y in operations:
    if kind == "sum":
        answers.append(fw.range_sum(x, y))
    elif kind == "add":
        fw.point_add(x, y)
    elif kind == "assign":
        fw.point_assign(x, y)
    else:
        raise ValueError("Loại thao tác không hỗ trợ")

assert answers == [31, 34, 19, 0]
```

Trong chuỗi này, mọi câu trả lời phản ánh **chính xác những cập nhật đã xảy ra trước nó**. Đây là đặc điểm của cấu trúc xử lý **online** — không phải chờ đến lúc kết thúc toàn bộ cập nhật mới dựng lại mảng.

### Đừng nhập nhằng giữa gán và cộng

Nếu dòng `S 2 -1` bị hiểu thành `point_add(2,-1)` thay vì `point_assign(2,-1)`, giá trị `a[2]` sẽ từ 4 thành 3 thay vì -1, gây sai toàn bộ truy vấn sau đó.

Khi thiết kế định dạng dữ liệu, hãy đặt tên lệnh và kiểm thử đầu vào rõ ràng.

## 15. Xây BIT bằng n lần cập nhật

Một cách xây dễ hiểu là tạo BIT toàn số 0 rồi lần lượt thêm từng phần tử.

```python
def build_bit_by_updates(values):
    n = len(values)
    bit = [0] * (n + 1)

    for pos, value in enumerate(values):
        i = pos + 1

        while i <= n:
            bit[i] += value
            i += i & -i

    return bit


a = [3, 1, 4, 1, 5, 9, 2, 6]
assert build_bit_by_updates(a) == [0, 3, 4, 4, 9, 5, 14, 2, 31]
```

Mỗi phần tử đi qua O(log n) ô, nên toàn bộ bước xây là **O(n log n)**.

Cách này đúng và tiện để hiểu bất biến: mỗi phần tử đóng góp vào mọi vùng BIT chứa nó. Nhưng khi đã biết toàn bộ mảng đầu vào, có thể xây nhanh hơn.

## 16. Xây BIT tuyến tính O(n) bằng lan truyền tổng

Ta tận dụng công thức cha:

```text
parent(i) = i + lowbit(i)
```

Duyệt chỉ số nội bộ `i=1,2,...,n`. Khi đến i:

1. Cộng `a[i-1]` vào `bit[i]`.
2. Các ô nhỏ hơn đã đẩy những tổng thích hợp vào `bit[i]`, nên `bit[i]` chính là tổng của vùng nó quản lý.
3. Nếu `parent(i)<=n`, đẩy **toàn bộ `bit[i]`** vào `bit[parent(i)]`.

### Giả mã

```text
BUILD_LINEAR(a):
    n = length(a)
    bit = [0] * (n+1)

    for i from 1 to n:
        bit[i] += a[i-1]

        parent = i + lowbit(i)
        if parent <= n:
            bit[parent] += bit[i]

    return bit
```

### Code Python

```python
def build_bit_linear(values):
    n = len(values)
    bit = [0] * (n + 1)

    for i, value in enumerate(values, start=1):
        bit[i] += value
        parent = i + (i & -i)
        if parent <= n:
            bit[parent] += bit[i]

    return bit


a = [3, 1, 4, 1, 5, 9, 2, 6]

assert build_bit_linear(a) == [0, 3, 4, 4, 9, 5, 14, 2, 31]
assert build_bit_linear(a) == build_bit_by_updates(a)
assert build_bit_linear([]) == [0]
```

Cách xây tuyến tính chạm mỗi i đúng một lần và thực hiện O(1) phép tính tại mỗi i, nên **O(n)** thời gian và **O(n)** bộ nhớ.

### Truy vết bốn bước đầu

```text
i=1: bit[1]+=3 => 3; đẩy sang bit[2].
i=2: bit[2]+=1 => 4; đẩy sang bit[4].
i=3: bit[3]+=4 => 4; đẩy sang bit[4].
i=4: bit[4]+=1 => 9; đẩy sang bit[8].
```

Sau khi đi hết i=8, bảng chứa đúng tổng vùng của từng chỉ số.

**Phân biệt rõ:** thời gian **xây toàn bộ** O(n) không có nghĩa một lần **cập nhật điểm mới** cũng O(1). Sau khi xây, một `point_add` cần đi tới O(log n) ô liên quan.

## 17. Chứng minh vì sao cập nhật duy trì bất biến

Giả sử trước cập nhật:

```text
bit[i] = sum(a[i-lowbit(i):i])
```

Ta tăng `a[pos]` thêm `delta`.

Với mỗi ô `bit[i]`, chỉ có hai khả năng:

1. Nếu `pos` nằm **trong vùng phụ trách**, tổng đoạn tăng đúng `delta`.
2. Nếu `pos` nằm **ngoài vùng phụ trách**, tổng đoạn không đổi.

Đường đi `i=pos+1; i+=lowbit(i)` liệt kê đúng các ô BIT có vùng chứa vị trí ấy. Vòng cập nhật cộng `delta` vào mỗi ô trên đường và không sửa các ô khác.

Bởi vậy, sau cập nhật:

```text
bit[i] mới = tổng vùng tương ứng của a mới
```

với mọi chỉ số i. Bất biến được bảo toàn.

### Vì sao đường đi không bỏ sót vùng?

Ở hệ 1-based, mỗi vị trí x thuộc một chuỗi các đoạn Fenwick lồng nhau:

```text
[x-lowbit(x)+1, x]  (đóng nội bộ)
    nằm trong vùng của
x + lowbit(x)
    nằm trong vùng của
điểm cha tiếp theo ...
```

Mỗi lần nhảy tới cha, vùng được mở rộng sang trái và có biên phải lớn hơn. Nếu một vùng Fenwick khác chứa x, biên phải của nó nằm trên chuỗi cha ấy theo cấu trúc lowbit, nên không bị bỏ qua.

Đây là tính chất nền tảng của việc tổ chức các đoạn theo **bit thấp nhất**, không phải hệ quả của việc chỉ đơn giản tăng một chỉ số bất kỳ.

## 18. Tổng tiền tố có thể âm hoặc không tăng

Với dữ liệu âm:

```text
a = [5, -8, 4, 2, -1]
```

Các tiền tố:

```text
P[0] = 0
P[1] = 5
P[2] = -3
P[3] = 1
P[4] = 3
P[5] = 2
```

Fenwick vẫn tính đúng tất cả `P[end]`:

```python
fw = FenwickSum([5, -8, 4, 2, -1])

assert [fw.prefix_sum(i) for i in range(6)] == [
    0, 5, -3, 1, 3, 2
]
assert fw.range_sum(1, 4) == -2
```

Không có yêu cầu các giá trị phải dương hay tiền tố phải không giảm. Phép cộng và trừ vẫn hoạt động trên số âm.

**Nhưng:** những thuật toán *tìm vị trí đầu tiên đạt tổng mục tiêu bằng tìm kiếm nhị phân* cần thêm điều kiện đơn điệu. Dữ liệu âm làm tiền tố có thể giảm, nên không được áp dụng nhầm.

## 19. Một ứng dụng nâng cao: tìm biên tiền tố theo mục tiêu

Khi **tất cả giá trị hiện tại đều không âm**, các tổng tiền tố:

```text
P[0], P[1], ..., P[n]
```

**không giảm**. Nếu muốn tìm `end` nhỏ nhất sao cho:

```text
prefix_sum(end) >= target
```

ta có thể tìm bằng **binary lifting trên BIT** trong O(log n), thay vì tìm kiếm nhị phân ngoài và gọi O(log n) truy vấn mỗi lần (O(log² n)).

### Mục tiêu

Ví dụ `a=[3,1,4,1,5,9,2,6]`:

```text
P = [0,3,4,8,9,14,23,25,31]
```

Với `target=10`, `end` nhỏ nhất có tổng tiền tố ít nhất 10 là `5`, vì:

```text
P[4]=9 < 10
P[5]=14 >= 10
```

### Điều kiện quan trọng

Tính đơn điệu chỉ được bảo đảm khi các giá trị hiện tại **không âm**. Nếu có số âm, phép tìm dưới đây **không có hợp đồng đúng**.

Với `target <= 0`, `end=0` đã thỏa vì `P[0]=0`. Nếu `target` vượt tổng toàn mảng không âm, không có lời giải và ta trả `None`.

### Thuật toán binary lifting

Trong BIT, các ô tổng cho phép di chuyển qua những đoạn liên tiếp theo các bước lũy thừa 2. Thuật toán duy trì:

```text
idx = biên tiền tố lớn nhất đã biết có tổng < target
acc = prefix_sum(idx)
```

Từ bước nhảy lớn nhất `2^k <= n`, thử chuyển tới `idx+2^k`. Nếu nằm trong miền và tổng sau chuyển vẫn nhỏ hơn mục tiêu, ta chấp nhận bước; sau đó giảm bước một nửa.

```python
def first_prefix_at_least_nonnegative(fw, target):
    """
    Tiền điều kiện: mọi fw.values[i] >= 0.
    Tìm end nhỏ nhất thuộc [0,n] với prefix_sum(end) >= target.
    Trả None nếu không tồn tại.
    """
    if target <= 0:
        return 0

    total = fw.prefix_sum(fw.n)
    if target > total:
        return None

    idx = 0
    acc = 0
    step = 1 << (fw.n.bit_length() - 1)

    while step:
        candidate = idx + step

        if candidate <= fw.n and acc + fw.bit[candidate] < target:
            idx = candidate
            acc += fw.bit[candidate]

        step //= 2

    return idx + 1


fw = FenwickSum([3, 1, 4, 1, 5, 9, 2, 6])

assert first_prefix_at_least_nonnegative(fw, 10) == 5
assert first_prefix_at_least_nonnegative(fw, 1) == 1
assert first_prefix_at_least_nonnegative(fw, 31) == 8
assert first_prefix_at_least_nonnegative(fw, 32) is None
assert first_prefix_at_least_nonnegative(fw, 0) == 0
```

**Hợp đồng của hàm yêu cầu người gọi duy trì mảng không âm cả sau các lần cập nhật.** Không có kiểm tra `all(value>=0)` trong hàm để giữ phần tìm kiếm O(log n); nếu ứng dụng không bảo đảm điều kiện ấy, nên lưu bộ đếm số phần tử âm được cập nhật cùng mảng hoặc kiểm tra điều kiện ở nơi khác.

Với `fw.n=0` và `target>0`, `total=0` khiến hàm trả `None` trước khi tính bước nhảy. Vì vậy biểu thức dịch bit chỉ được thực hiện khi cần một tìm kiếm trên mảng có tổng dương.

### Phân biệt với range_sum

Đây là bài toán **tìm chỉ số dựa trên tổng tiền tố**, không phải thao tác cơ bản được yêu cầu ở mọi BIT. Nó cần thêm **tính không giảm** của tiền tố; trong khi `prefix_sum` và `range_sum` bình thường vẫn đúng với số âm.

## 20. Tính độ phức tạp chính xác của chuỗi thao tác

Ký hiệu:

- `n`: số phần tử.
- `u`: số lệnh cập nhật điểm.
- `q`: số lệnh truy vấn tổng đoạn hoặc tiền tố.

Với phép cộng/trừ trên giá trị kích thước cố định được coi là O(1):

| Thao tác | Thời gian | Bộ nhớ phụ mỗi lần |
|---|---:|---:|
| Xây BIT bằng thêm n phần tử | O(n log n) | O(n) cho bảng |
| Xây BIT tuyến tính | **O(n)** | **O(n)** cho bảng |
| `point_add` | **O(log n)** | O(1) |
| `point_assign` khi lưu giá trị cũ | **O(log n)** | O(1) |
| `prefix_sum` | **O(log n)** | O(1) |
| `range_sum` | **O(log n)** | O(1) |
| `get` khi lưu mảng hiện tại | **O(1)** | O(1) |
| Tìm biên tiền tố dưới điều kiện không âm | **O(log n)** | O(1) |

Tổng thời gian cho một lần xây tuyến tính và `q+u` thao tác:

```text
O(n + (q+u)log n)
```

Bộ nhớ của ví dụ lưu:

```text
values: n phần tử
bit: n+1 phần tử
```

nên tổng O(n). Dù con số ô khoảng `2n+1` trong ví dụ, bậc bộ nhớ vẫn O(n).

Nếu giữ mọi câu trả lời truy vấn trong một danh sách, còn tốn **O(q) bộ nhớ đầu ra**, không phải bộ nhớ làm việc của bản thân thao tác.

### Chi phí số nguyên lớn và số thực

Phân tích O(log n) đếm các lần truy cập ô và phép cộng/trừ. Với Python `int` rất lớn, chi phí một phép cộng có thể tăng theo số bit; với `float`, phép cộng có sai số làm tròn. Khi ứng dụng nhạy về hiệu năng hoặc độ chính xác, phải xét cả **chi phí phép toán trên giá trị**, không chỉ số bước BIT.

## 21. Fenwick và vấn đề làm tròn số thực

Trong toán học, phép cộng có tính kết hợp:

```text
(x+y)+z = x+(y+z)
```

Ở số thực dấu phẩy động, làm tròn có thể khiến hai cách cộng cho kết quả khác nhau ở các bit thấp.

Fenwick gộp giá trị theo **những đoạn khác** so với quét trực tiếp hoặc mảng tổng tiền tố; vì vậy, với `float` rất lớn, nhỏ, hoặc triệt tiêu nhau, kết quả có thể hơi khác.

Ví dụ về sự phụ thuộc thứ tự ở nhiều hệ số thực máy:

```text
(1e16 + (-1e16)) + 1.0  -> 1.0
1e16 + ((-1e16) + 1.0)  -> 0.0
```

Điều đó không làm sai chứng minh trong **mô hình số học chính xác** nhưng cho thấy hợp đồng thực tế cần **mức sai số chấp nhận**.

Nếu xử lý tiền tệ, có thể dùng số nguyên biểu diễn đơn vị nhỏ nhất phù hợp; nếu cần thập phân có kiểm soát, có thể cân nhắc `Decimal` và quy tắc làm tròn rõ ràng.

## 22. Fenwick khác tổng tiền tố và segment tree như thế nào?

| Cấu trúc | Xây | Tổng tiền tố | Cập nhật điểm | Bộ nhớ |
|---|---:|---:|---:|---:|
| Mảng thường, quét | O(1) ngoài mảng | O(k) | O(1) | O(1) phụ |
| Prefix sum tĩnh | O(n) | **O(1)** | O(n) nếu duy trì bảng | O(n) |
| **Fenwick sum** | **O(n)** tuyến tính | **O(log n)** | **O(log n)** | **O(n)** |
| Segment tree sum | O(n) | O(log n) | O(log n) | O(n) |
| Sqrt decomposition tổng | O(n) | O(√n) | O(1) | O(n/B) ngoài mảng |

**Ưu điểm của Fenwick:**

- Cài đặt ngắn gọn.
- Một mảng tổng hợp, thường ít hằng số bộ nhớ hơn segment tree.
- Hỗ trợ các thao tác cộng điểm/tổng tiền tố theo thời gian O(log n).
- Có thể mở rộng cho các bài toán liên quan mảng hiệu và thống kê tần suất.

**Giới hạn:**

- Không hỗ trợ phép gộp bất kỳ với cùng các công thức cộng/trừ.
- Khi cập nhật cả đoạn hoặc hỏi min/max tùy ý, cần biến thể có điều kiện riêng hay chọn cấu trúc khác.
- Nếu hoàn toàn không có cập nhật và chỉ hỏi tổng, prefix sum thường đơn giản và nhanh hơn.

### Vì sao không thể lấy “hiệu hai min tiền tố”?

Min không có phép nghịch đảo giúp bỏ phần tiền tố bên trái.

```text
a = [1,9,5]
b = [1,7,8]
```

Hai mảng đều có min các tiền tố không rỗng là `[1,1,1]`, nhưng:

```text
min(a[1:3]) = 5
min(b[1:3]) = 7
```

Không thể suy kết quả min đoạn từ hai min tiền tố giống nhau. Fenwick chuẩn cho **tổng cộng** không tự chuyển thành BIT min bằng cách đổi dấu `+` thành `min` trong mọi phương thức.

## 23. Mở rộng tới cộng đoạn bằng mảng hiệu

Kỹ thuật mảng hiệu biểu diễn một lệnh cộng `delta` trên `[l,r)` bằng hai mốc:

```text
diff[l] += delta
diff[r] -= delta      (nếu r < n)
```

Giá trị tăng thêm tại một vị trí `pos` là:

```text
effect(pos) = diff[0] + ... + diff[pos]
```

Nếu lưu mảng `diff` trong một Fenwick hỗ trợ **cập nhật điểm và tổng tiền tố**, ta có thể:

- Cộng đoạn: hai lần cập nhật điểm của BIT, O(log n).
- Hỏi giá trị tại một điểm: một truy vấn tiền tố, O(log n).

### Mẫu Python

```python
class RangeAddPointValue:
    def __init__(self, initial):
        self.base = tuple(initial)
        self.n = len(self.base)
        self.diff_bit = FenwickSum([0] * self.n)

    def range_add(self, l, r, delta):
        self.diff_bit._check_range(l, r)

        if l == r:
            return

        self.diff_bit.point_add(l, delta)
        if r < self.n:
            self.diff_bit.point_add(r, -delta)

    def get(self, pos):
        self.diff_bit._check_pos(pos)
        return self.base[pos] + self.diff_bit.prefix_sum(pos + 1)


ds = RangeAddPointValue([2, 5, 1, 4, 3])

ds.range_add(1, 4, 3)
ds.range_add(2, 5, -2)

assert [ds.get(i) for i in range(5)] == [2, 8, 2, 5, 1]
```

Cấu trúc này giải **range-add + point-value**, không tự hỗ trợ **range-add + range-sum** với một lần lấy hiệu tiền tố trực tiếp trên `diff_bit`.

Muốn vừa cộng đoạn vừa hỏi tổng đoạn online, có thể dùng **hai BIT với công thức có trọng số chỉ số** hoặc **segment tree lazy**. Đó là một hợp đồng thao tác mở rộng, cần chứng minh và triển khai riêng, không thể chỉ sao chép phương thức `range_sum` của BIT trên mảng hiệu.

## 24. Đổi chỉ số của đề bài 1-based đóng

Một đề có thể nói: “Tăng giá trị ở vị trí **K**” hoặc “Hỏi tổng từ vị trí **L đến R**, gồm cả hai đầu”, trong đó vị trí đầu tiên là 1.

### Cập nhật một điểm

Với chỉ số đề bài 1-based `K`:

```text
pos_0based = K - 1
```

Nên:

```python
fw.point_add(K - 1, delta)
```

### Tổng đoạn đóng 1-based

Với `1 <= L <= R <= n`:

```text
[L,R] 1-based đóng
    ->
[L-1,R) 0-based nửa mở
```

Vì thế:

```text
sum_1based(L,R)
  = prefix_sum(R) - prefix_sum(L-1)
```

### Adapter rõ hợp đồng

```python
def sum_1based_inclusive(fw, L, R):
    if type(L) is not int or type(R) is not int:
        raise TypeError("L và R phải là số nguyên")
    if not 1 <= L <= R <= fw.n:
        raise IndexError("Đoạn đóng 1-based không hợp lệ")

    return fw.range_sum(L - 1, R)


fw = FenwickSum([3, 1, 4, 1, 5, 9, 2, 6])

assert sum_1based_inclusive(fw, 3, 7) == 21
assert sum_1based_inclusive(fw, 1, 8) == 31
assert sum_1based_inclusive(fw, 8, 8) == 6
```

**Không được quy đổi hai lần:** bản thân BIT đã có chỉ số nội bộ 1-based, nhưng phương thức `range_sum` cung cấp hợp đồng 0-based nửa mở. Adapter chỉ quy đổi **đầu vào đề bài sang API ngoài**; việc nội bộ bắt đầu ở chỉ số nào là trách nhiệm của lớp Fenwick.

## 25. Lỗi thường gặp trong point update và prefix query

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Cập nhật từ `i=pos` thay vì `pos+1` | Sai hệ chỉ số, `pos=0` có thể lặp vô hạn | Cập nhật từ **`pos+1`** |
| Truy vấn `prefix_sum(end)` từ `end+1` | Lấy thừa phần tử cuối | Bắt đầu từ **`end`** |
| Nghĩ `bit[i]` là `sum(a[0:i])` | Diễn giải sai các ô BIT | Dùng `[i-lowbit(i),i)` |
| Dùng `i -= lowbit(i)` cho update | Chưa sửa các vùng cha | Update phải đi lên bằng `+lowbit` |
| Dùng `i += lowbit(i)` cho query | Không thu gọn tiền tố | Query đi xuống bằng `-lowbit` |
| Quên sửa mảng `values` khi có point_add | Gán điểm sau đó tính delta sai | Đồng bộ dữ liệu gốc và BIT |
| Quên sửa BIT khi cập nhật mảng gốc | Truy vấn dùng tổng cũ | Chỉ cập nhật qua phương thức |
| Gán trực tiếp `bit[pos+1]=value` | Phá tổng vùng và các vùng cha | Đổi gán thành `delta=new-old` |
| Dùng hiệu hai tiền tố sai thứ tự | Tổng đoạn đổi dấu | `P(r)-P(l)` |
| Coi `r` thuộc `[l,r)` | Thừa một phần tử | Biên phải **exclusive** |
| Từ chối `prefix_sum(n)` | Không lấy được tổng toàn mảng | `end=n` hợp lệ |
| Chấp nhận `point_add(n,delta)` | Cập nhật ngoài mảng | Điểm phải `pos<n` |
| Không chặn `end<0` | Trả kết quả sai hợp đồng | Validate `0<=end<=n` |
| Dùng lowbit(0) trong vòng cập nhật | Không tiến chỉ số | BIT nội bộ 1-based |
| Xây bằng n lần add rồi báo O(n) | Sai phân tích chi phí | O(n log n) hoặc dùng xây tuyến tính |
| Tin rằng tiền tố luôn tăng | Sai với số âm | Chỉ tìm biên theo tổng khi không âm |
| Dùng BIT sum để tính min bằng hiệu tiền tố | Min không có nghịch đảo | Cấu trúc phù hợp với min |
| Dùng một BIT hiệu để trả range sum sau range add | Lấy nhầm tổng mức mốc | Dùng biến thể hai BIT/lazy |
| Lưu `float` nhưng so sánh luôn tuyệt đối | Có thể sai vì làm tròn | Dùng dung sai/chính sách số phù hợp |
| Không kiểm thử cập nhật nhiều lần | Lỗi phát hiện muộn | So khớp với mảng quét trên dữ liệu nhỏ |

## 26. Kiểm thử đối chiếu với mảng thường

Để đảm bảo một cấu trúc tối ưu đúng, hãy so sánh nó với một cách tính trực tiếp **dễ hiểu và ít nhánh** trên mảng nhỏ.

### Kiểm tra mọi vùng phụ trách

```python
def assert_bit_ranges(fw):
    for i in range(1, fw.n + 1):
        w = i & -i
        expected = sum(fw.values[i - w:i])
        assert fw.bit[i] == expected


fw = FenwickSum([3, 1, 4, 1, 5, 9, 2, 6])
assert_bit_ranges(fw)

fw.point_add(4, 3)
assert_bit_ranges(fw)

fw.point_assign(2, -1)
assert_bit_ranges(fw)
```

Vòng lặp này kiểm tra **đúng bất biến Fenwick** sau mỗi thay đổi, chứ không chỉ kiểm tra một câu trả lời ngẫu nhiên.

### Kiểm tra mọi tiền tố và đoạn

```python
def assert_queries_against_scan(fw):
    for end in range(fw.n + 1):
        assert fw.prefix_sum(end) == sum(fw.values[:end])

    for l in range(fw.n + 1):
        for r in range(l, fw.n + 1):
            assert fw.range_sum(l, r) == sum(fw.values[l:r])


for sample in [
    [],
    [9],
    [0, 0, 0],
    [5, -8, 4, 2, -1],
    [3, 1, 4, 1, 5, 9, 2, 6],
]:
    fw = FenwickSum(sample)
    assert_bit_ranges(fw)
    assert_queries_against_scan(fw)
```

Duyệt mọi cặp biên tốn O(n²) truy vấn, nên chỉ dùng phương pháp này để **kiểm thử trên mảng nhỏ**, không phải thuật toán thay thế Fenwick khi dữ liệu lớn.

### Kiểm tra cập nhật xen kẽ

```python
reference = [3, 1, 4, 1, 5, 9, 2, 6]
fw = FenwickSum(reference)

ops = [
    ("add", 4, 3),
    ("assign", 2, -1),
    ("add", 0, -5),
    ("assign", 7, 10),
    ("add", 5, 0),
]

for kind, pos, value in ops:
    if kind == "add":
        reference[pos] += value
        fw.point_add(pos, value)
    else:
        reference[pos] = value
        fw.point_assign(pos, value)

    assert fw.values == reference
    assert_bit_ranges(fw)
    assert_queries_against_scan(fw)
```

Các trường hợp cần thử gồm **mảng rỗng, một phần tử, n là lũy thừa 2 hoặc không, chỉ số đầu/cuối, số âm, delta bằng 0, gán lặp lại cùng giá trị, tổng đoạn rỗng và các biên không hợp lệ**.

## 27. Câu hỏi thường gặp

### Q1. BIT có phải một cây nhị phân tạo bằng nút và con trỏ?

Không. Cây Fenwick thường chỉ dùng **một mảng**, với quan hệ vùng phụ trách và phép nhảy chỉ số nhị phân. Tên “tree” mô tả cấu trúc liên hệ giữa những đoạn tổng, không yêu cầu các đối tượng node hay con trỏ.

### Q2. Vì sao không duy trì tổng tiền tố trong một mảng P?

Vì sau một cập nhật tại `pos`, nhiều `P[k]` với `k>pos` đều thay đổi. Fenwick chỉ phải sửa O(log n) vùng được chọn.

### Q3. Có thể hỏi tổng một điểm mà không lưu values không?

Có. Với `pos` hợp lệ:

```text
a[pos] = prefix_sum(pos+1) - prefix_sum(pos)
```

nên đọc một điểm O(log n). Lưu `values` thêm O(n) cho phép lấy trong O(1).

### Q4. BIT có hỗ trợ giảm điểm không?

Có. Chỉ cần gọi `point_add(pos,delta)` với `delta<0`. Cả vòng cập nhật và tổng tiền tố vẫn đúng vì phép cộng hỗ trợ số âm.

### Q5. Nếu cả hai biên của range_sum đều nằm trong một khối BIT thì có còn O(log n) không?

Có cận O(log n), dù số bước cụ thể có thể nhỏ. Công thức vẫn gọi hai tiền tố, không phụ thuộc hai biên có cùng một vùng của một ô BIT hay không.

### Q6. Cập nhật điểm có thể ảnh hưởng tới những tiền tố nào?

Một thay đổi tại `pos` ảnh hưởng tới mọi tiền tố `prefix_sum(end)` với `end>pos`. Nhưng ta **không sửa từng tiền tố**; ta sửa những ô BIT trên đường cha, để mọi tiền tố sau này ghép đúng kết quả.

### Q7. Fenwick dùng được với phép XOR không?

Có thể thiết kế BIT XOR vì XOR kết hợp, giao hoán và mỗi giá trị tự là nghịch đảo của mình. Phải dùng phép XOR cho cả cập nhật và truy vấn, không dùng nguyên công thức `new-old` của tổng số.

### Q8. Tại sao có khi BIT query 1-based và có khi 0-based?

Đó là hai cách biểu diễn chỉ số. Bài này **cố định 0-based ngoài, 1-based trong**. Một biến thể nội bộ 0-based sử dụng phép nhảy khác; không được trộn các công thức từ hai biến thể.

## 28. Bài tập tự luyện có lời giải

**Bài 1 — Phạm vi chỉ số.** Với n=8, chỉ số ngoài hợp lệ cho cập nhật điểm và biên cuối hợp lệ cho prefix_sum là gì?

*Lời giải:* Cập nhật điểm chọn `pos` trong **0..7**; `end` cho tiền tố trong **0..8**.

**Bài 2 — Đổi chỉ số.** Cập nhật `pos=4` ngoài 0-based bắt đầu từ chỉ số BIT nào?

*Lời giải:* **`i=pos+1=5`**.

**Bài 3 — Lowbit.** Tính `lowbit(5)`, `lowbit(6)`, `lowbit(8)`.

*Lời giải:* Lần lượt **1, 2, 8**.

**Bài 4 — Vùng BIT.** `bit[6]` quản lý đoạn nào trên mảng ngoài?

*Lời giải:* `lowbit(6)=2`, nên vùng là **`[4,6)`**.

**Bài 5 — Bất biến.** Công thức tổng quát mô tả `bit[i]` là gì?

*Lời giải:* **`bit[i]=sum(a[i-lowbit(i):i])`** với `1<=i<=n`.

**Bài 6 — Xây bảng.** Với `a=[3,1,4,1,5,9,2,6]`, hãy liệt kê `bit[1..8]`.

*Lời giải:* **`[3,4,4,9,5,14,2,31]`**.

**Bài 7 — Truy vấn tiền tố.** Đường đi của `prefix_sum(7)` qua các chỉ số BIT nào?

*Lời giải:* **7 → 6 → 4 → 0**.

**Bài 8 — Kết quả truy vấn.** Trên dãy ở bài 6, `prefix_sum(7)` bằng bao nhiêu?

*Lời giải:* `bit[7]+bit[6]+bit[4]=2+14+9=25`.

**Bài 9 — Toàn mảng.** `prefix_sum(8)` là bao nhiêu và đọc những ô nào?

*Lời giải:* Đọc một ô **`bit[8]=31`**, rồi dừng ở 0.

**Bài 10 — Cập nhật đường cha.** Với n=8, cập nhật vị trí ngoài 4 phải sửa các ô BIT nào?

*Lời giải:* Bắt đầu 5, rồi 6, rồi 8; các ô **bit[5], bit[6], bit[8]**.

**Bài 11 — Tăng điểm.** Nếu `point_add(4,3)`, `bit[6]` thay đổi từ bao nhiêu thành bao nhiêu?

*Lời giải:* Từ **14 thành 17**.

**Bài 12 — Tiền tố sau tăng.** Sau bài 11, `prefix_sum(7)` mới bằng bao nhiêu?

*Lời giải:* **28**, tăng 3 so với 25.

**Bài 13 — Gán điểm.** Nếu `a[2]=4` và muốn gán thành `-1`, delta cần dùng bằng bao nhiêu?

*Lời giải:* `-1-4=**-5**`.

**Bài 14 — Đường gán.** Với n=8, cập nhật vị trí ngoài 2 đi qua các ô BIT nào?

*Lời giải:* Nội bộ 3, tiếp theo 4, rồi 8; tức **bit[3], bit[4], bit[8]**.

**Bài 15 — Tổng đoạn sau hai cập nhật.** Sau `point_add(4,3)` và `point_assign(2,-1)`, tổng `[2,7)` bằng bao nhiêu?

*Lời giải:* **19**, vì dãy mới là `[3,1,-1,1,8,9,2,6]` và tổng `-1+1+8+9+2=19`.

**Bài 16 — Đoạn rỗng.** `range_sum(8,8)` có hợp lệ không, kết quả là gì?

*Lời giải:* **Hợp lệ**, trả **0**, vì hai tiền tố giống nhau.

**Bài 17 — Mảng rỗng.** `FenwickSum([]).prefix_sum(0)` và `range_sum(0,0)` bằng bao nhiêu?

*Lời giải:* Cả hai bằng **0**.

**Bài 18 — Không dùng lowbit(0).** Vì sao vòng update từ i=0 có thể không kết thúc?

*Lời giải:* `lowbit(0)=0`, nên `i+=0` không tăng. Đổi từ pos ngoài sang `i=pos+1`.

**Bài 19 — Cận query.** Vì sao truy vấn tiền tố chỉ mất O(log n)?

*Lời giải:* Mỗi bước `i-=lowbit(i)` xóa một bit 1 thấp nhất; số bit 1 không vượt O(log n).

**Bài 20 — Cận update.** Vì sao cập nhật điểm chỉ mất O(log n)?

*Lời giải:* `i+=lowbit(i)` khiến bit 1 thấp nhất chuyển lên bậc cao hơn, nên chỉ có O(log n) bước trước khi vượt n.

**Bài 21 — Xây tuyến tính.** Tại sao duyệt i tăng dần và đẩy `bit[i]` vào cha xây được BIT trong O(n)?

*Lời giải:* Mỗi i nhận dữ liệu gốc và tổng từ các ô con đã xử lý, sau đó đẩy một lần lên cha. Có n bước, mỗi bước O(1), nên O(n).

**Bài 22 — Cập nhật không ảnh hưởng truy vấn.** Nếu sửa vị trí `pos=1`, tổng đoạn `[3,7)` có đổi không?

*Lời giải:* **Không**, vì vị trí 1 nằm ngoài đoạn. Trong hiệu hai tiền tố `P(7)-P(3)`, cả hai cùng thay đổi một delta và triệt tiêu nhau.

**Bài 23 — Tìm biên.** Với `a=[3,1,4,1,5,9,2,6]` không âm, `end` nhỏ nhất có `prefix_sum(end)>=10` là bao nhiêu?

*Lời giải:* **5**, vì `P(4)=9<10` và `P(5)=14>=10`.

**Bài 24 — Số âm.** Khi mảng có giá trị âm, BIT còn trả tổng tiền tố đúng không? Có được tìm biên bằng tính đơn điệu không?

*Lời giải:* **Tổng tiền tố vẫn đúng**. Nhưng không bảo đảm tiền tố không giảm, nên **không được dùng tìm kiếm dựa trên đơn điệu** nếu không có điều kiện bổ sung.

**Bài 25 — Query sau cập nhật.** Có q truy vấn và u cập nhật trên n phần tử. Với Fenwick xây tuyến tính, tổng thời gian bao nhiêu?

*Lời giải:* **O(n+(q+u)log n)** trong mô hình phép cộng/trừ O(1).

**Bài 26 — So với prefix tĩnh.** Vì sao prefix sum không phải lựa chọn tốt nhất khi cập nhật điểm và truy vấn tổng thường xuyên xen kẽ?

*Lời giải:* Một cập nhật có thể làm thay đổi O(n) tiền tố; Fenwick chỉ cần sửa O(log n) ô.

**Bài 27 — Đổi biên 1-based.** Đề hỏi `[L=3,R=7]` 1-based đóng. Đoạn ngoài nửa mở là gì?

*Lời giải:* **`[2,7)`** 0-based, có thể trả bằng `P(7)-P(2)`.

**Bài 28 — Cập nhật theo mảng hiệu.** Muốn cộng delta vào đoạn `[l,r)` rồi hỏi giá trị một điểm bằng BIT trên hiệu, cần thao tác gì?

*Lời giải:* Ghi **+delta ở l** và **−delta ở r nếu r<n**, rồi lấy tổng tiền tố của mốc tới vị trí cần hỏi.

**Bài 29 — Giữ giá trị gốc.** Nếu không lưu `values`, có thể tìm `a[pos]` bằng BIT không? Chi phí?

*Lời giải:* Có, bằng `prefix_sum(pos+1)-prefix_sum(pos)` trong **O(log n)**.

**Bài 30 — Bảo toàn bất biến.** Nêu một phép kiểm thử mạnh hơn việc chỉ hỏi `prefix_sum(n)`.

*Lời giải:* Với mọi `i`, so sánh **`bit[i]` với `sum(values[i-lowbit(i):i])`**; sau đó có thể duyệt mọi đoạn nhỏ để đối chiếu `range_sum` với `sum(values[l:r])`.

## 29. Tổng kết

Fenwick là cấu trúc gọn cho chuỗi thao tác **cập nhật điểm và truy vấn tổng tiền tố trực tuyến**. Bất biến trọng tâm là:

```text
lowbit(i) = i & -i

bit[i] = sum(a[i-lowbit(i):i])
```

Với API ngoài **0-based** và BIT nội bộ **1-based**:

```text
POINT_ADD(pos, delta):
    i = pos+1
    while i <= n:
        bit[i] += delta
        i += lowbit(i)

PREFIX_SUM(end):
    i = end
    answer = 0
    while i > 0:
        answer += bit[i]
        i -= lowbit(i)
    return answer

RANGE_SUM(l,r) = PREFIX_SUM(r) - PREFIX_SUM(l)
```

**Truy vấn** chọn các vùng rời nhau phủ đúng tiền tố. **Cập nhật** sửa đúng những vùng chứa phần tử thay đổi. Khi dùng phép cộng/trừ có chi phí hằng số, cả hai thao tác có cận **O(log n)**, xây tuyến tính **O(n)**, bộ nhớ **O(n)**.

Hãy luôn phân biệt **cộng** với **gán điểm**, kiểm tra `0<=pos<n` và `0<=l<=r<=n`, tránh `lowbit(0)`, và giữ BIT đồng bộ với dữ liệu hiện tại. Khi đã hiểu chính xác đường cập nhật đi lên và truy vấn đi xuống, bạn có thể chọn Fenwick đúng chỗ, phân tích độ phức tạp và phát triển các biến thể truy vấn đoạn có cập nhật một cách có cơ sở.

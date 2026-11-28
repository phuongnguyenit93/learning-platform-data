# Biến đổi Fenwick để cập nhật đoạn và truy vấn tổng

Giả sử một hệ thống vận hành lưu lượng khách của từng ngày. Người quản lý thường thực hiện các lệnh **“Tăng chỉ tiêu của mọi ngày từ ngày l đến trước ngày r thêm 5”**, rồi ngay lập tức hỏi **“Tổng chỉ tiêu của các ngày 2 đến 9 là bao nhiêu?”**. Các lệnh cập nhật đoạn và truy vấn tổng xuất hiện **xen kẽ**, nên không thể đơn giản chờ cập nhật xong hết mới dựng mảng kết quả.

Cây Fenwick (*Fenwick tree* hay *Binary Indexed Tree — BIT*) cơ bản nổi tiếng với **cộng một điểm** và **tổng tiền tố**, mỗi thao tác O(log n). Nếu chuyển mảng sang **mảng hiệu** (*difference array*), một lệnh cộng đoạn trở thành **hai lần cộng điểm**. Tuy nhiên, chỉ một Fenwick trên mảng hiệu mới cho phép truy vấn **giá trị tại một điểm**, chứ chưa đủ để trả lời trực tiếp **tổng của một đoạn bất kỳ** trong O(log n).

Giải pháp là dùng **hai cây Fenwick**: một cây giữ các mốc sai phân, cây còn lại giữ **mốc sai phân nhân trọng số chỉ số**. Khi đó, ta có thể tính tổng tiền tố của mảng thực bằng công thức:

```text
prefix_sum(x) = x * sum(D[0:x]) - sum(i*D[i] với 0 <= i < x)
```

Sau khi tiền xử lý, cấu trúc này hỗ trợ:

| Thao tác | Chi phí |
|---|---:|
| Xây hai Fenwick từ mảng ban đầu | O(n) |
| Cộng `delta` cho đoạn `[l,r)` | **O(log n)** |
| Truy vấn tổng tiền tố `[0,x)` | **O(log n)** |
| Truy vấn tổng đoạn `[l,r)` | **O(log n)** |
| Cộng/gán một điểm thông qua API đoạn | **O(log n)** |
| Bộ nhớ tổng | **O(n)** |

Bài nằm trong chương **Truy vấn đoạn** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mô-đun xây nền tảng về mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; nhấn mạnh **bất biến, thao tác và độ phức tạp thời gian/bộ nhớ** để chọn đúng cấu trúc cho từng bài toán. Ở đây, ta sẽ đi từ một Fenwick đơn giản qua mảng hiệu đến hai Fenwick, chứng minh công thức, truy vết chính xác các biên, viết mã Python và kiểm thử các trường hợp khó.

## 1. Hợp đồng thao tác và quy ước chỉ số

Cho mảng `a` dài `n`, phần tử tại vị trí `0,1,...,n-1`.

Ta cần hỗ trợ hai thao tác chính:

```text
range_add(l, r, delta):
    với mọi i thuộc [l,r), thực hiện a[i] += delta

range_sum(l, r):
    trả về a[l] + a[l+1] + ... + a[r-1]
```

Trong toàn bộ mã và công thức 0-based của bài, đoạn có dạng **nửa mở `[l,r)`**:

```text
0 <= l <= r <= n
```

Điều đó có nghĩa:

- `l` là chỉ số phần tử đầu tiên **được lấy**.
- `r` là biên ngay sau phần tử cuối, **không được lấy**.
- `[0,n)` là toàn mảng.
- `[l,l)` là đoạn rỗng, **cập nhật không làm gì** và **tổng bằng 0**.
- `r=n` hợp lệ, dù không tồn tại phần tử `a[n]`.

Ví dụ với:

```text
Chỉ số:  0  1  2  3  4
a:       2  5  1  4  3
```

Lệnh `range_add(1,4,3)` tác động vào các chỉ số 1,2,3:

```text
Trước: [2, 5, 1, 4, 3]
Sau:   [2, 8, 4, 7, 3]
```

Sau lệnh ấy, `range_sum(1,4)=8+4+7=19`.

**Mục tiêu của bài:** cập nhật một đoạn dài không cần sửa từng phần tử và vẫn hỏi được tổng của đoạn bất kỳ **ngay sau cập nhật**.

## 2. Ba tổ hợp thao tác dễ bị nhầm

Fenwick có thể được tổ chức cho những tổ hợp khác nhau:

| Cấu trúc | Cập nhật | Truy vấn | Ý tưởng |
|---|---|---|---|
| **Một BIT trên mảng gốc** | Cộng **điểm** | Tổng **đoạn** | Tổng của các khối thuộc `a` |
| **Một BIT trên mảng hiệu** | Cộng **đoạn** | Giá trị **điểm** | Mốc đầu/cuối, tổng tiền tố của hiệu |
| **Hai BIT trên mảng hiệu và hiệu có trọng số** | Cộng **đoạn** | Tổng **đoạn** | Hai loại tiền tố cho công thức tổng tích lũy |

Đây là ba hợp đồng **khác nhau**.

Nếu một bài chỉ có `point_add` và `range_sum`, **một BIT thông thường** là đủ. Nếu chỉ có `range_add` và `point_get`, **một BIT trên hiệu** là đủ. Nhưng nếu vừa `range_add` vừa `range_sum` trực tuyến, mô hình hai BIT là một lời giải tiêu biểu.

**Không nên trả lời “Fenwick cập nhật đoạn O(log n)” mà không nói rõ Fenwick đang lưu cái gì và truy vấn nào phải hỗ trợ.**

## 3. Bước đầu: biểu diễn dữ liệu bằng mảng hiệu

Với mảng `a`, định nghĩa mảng hiệu `D`:

```text
D[0] = a[0]

D[i] = a[i] - a[i-1]    với 1 <= i < n
```

Ở đây ta hình dung giá trị trước `a[0]` bằng 0 trong định nghĩa toán học; **không dùng `a[-1]` của Python** vì đó là phần tử cuối.

Ví dụ:

```text
a = [2, 5, 1, 4, 3]

D[0] =  2
D[1] =  5 - 2 =  3
D[2] =  1 - 5 = -4
D[3] =  4 - 1 =  3
D[4] =  3 - 4 = -1

D = [2, 3, -4, 3, -1]
```

Tổng cộng dồn của hiệu khôi phục mảng:

```text
a[i] = D[0] + D[1] + ... + D[i]
```

Chẳng hạn:

```text
a[3] = 2+3-4+3 = 4
```

Đây là tổng khử liên tiếp:

```text
D[0] + D[1] + ... + D[i]
= a[0] + (a[1]-a[0]) + ... + (a[i]-a[i-1])
= a[i]
```

**Bất biến:** `D` mô tả chính xác toàn bộ mảng `a` thông qua các hiệu giữa vị trí kề nhau.

## 4. Cập nhật đoạn trở thành hai dấu mốc

Khi cộng `delta` vào mọi phần tử của `[l,r)`, những phần tử nằm sâu bên trong đoạn cùng tăng một lượng nên **hiệu giữa chúng không đổi**.

Chỉ hai biên có thể tạo hiệu mới:

```text
D[l] += delta

D[r] -= delta              nếu r < n
```

Tại biên trái, tác động cộng bắt đầu; tại biên phải, nó kết thúc.

Nếu `r=n`, không có phần tử thật mang chỉ số n, nên **không ghi `D[n]`** trong biểu diễn hiệu dài n. Nếu thích công thức không có nhánh điều kiện, có thể cấp phát **n+1 mốc**, nhưng hai BIT của bài này chỉ lưu các mốc `0..n-1` vì ta chỉ hỏi các phần tử thật.

Nếu `l=r`, đoạn rỗng; **bỏ qua** toàn bộ cập nhật.

### Ví dụ cộng một đoạn

```text
a = [2, 5, 1, 4, 3]
D = [2, 3, -4, 3, -1]

Cập nhật [1,4) +3:

D[1] += 3      -> 6
D[4] -= 3      -> -4

D mới = [2, 6, -4, 3, -4]
```

Cộng dồn:

```text
2; 2+6=8; 8-4=4; 4+3=7; 7-4=3

a mới = [2, 8, 4, 7, 3]
```

Vậy một cập nhật cho đoạn dài ba phần tử có thể ghi bằng **hai phép sửa mốc**, không phải sửa trực tiếp cả ba giá trị.

### Tại sao mốc ở r chứ không phải r-1?

Đoạn `[l,r)` **chứa** `r-1` nhưng **không chứa** `r`. Vì vậy tại vị trí `r`, tác động phải **ngừng**, nên mốc trừ ở đúng `D[r]`.

Nếu ghi trừ ở `r-1`, phần tử cuối cần cập nhật sẽ bị thiếu `delta`.

## 5. Một Fenwick trên D: range add, point query

Fenwick cơ bản lưu một mảng số `v` bằng những tổng khối:

```text
bit[i] = sum(v[i-lowbit(i):i])      với 1 <= i <= n
lowbit(i) = i & -i
```

BIT dùng **chỉ số nội bộ 1-based**, còn `v` có chỉ số 0-based.

Để hỗ trợ mảng hiệu:

```text
v = D
```

Khi cập nhật `[l,r)`:

```text
BIT.add(l,delta)
if r < n:
    BIT.add(r,-delta)
```

Giá trị mảng tại vị trí `pos` là:

```text
a[pos] = D[0] + ... + D[pos]
       = BIT.prefix_sum(pos+1)
```

Mỗi lần cập nhật mốc hoặc hỏi tổng tiền tố trong Fenwick tốn O(log n).

### Nhưng tổng của cả đoạn thì sao?

Nếu ta gọi:

```text
BIT.prefix_sum(r) - BIT.prefix_sum(l)
```

trên **BIT lưu D**, kết quả là:

```text
D[l] + D[l+1] + ... + D[r-1]
```

**Đây là tổng của sai phân, không phải tổng của các phần tử a.**

Ví dụ với `a=[2,5,1,4,3]`:

```text
D = [2,3,-4,3,-1]

BIT_D.prefix_sum(5) = 2+3-4+3-1 = 3

Nhưng tổng a[0:5] = 2+5+1+4+3 = 15.
```

Không thể trả tổng mảng thực bằng một tổng tiền tố của `D`. Đây chính là lý do cần một phép biến đổi bổ sung.

## 6. Vì sao tổng tiền tố của mảng thực có trọng số?

Đặt:

```text
P(x) = a[0] + a[1] + ... + a[x-1]

0 <= x <= n
```

Vì `a[i]=D[0]+...+D[i]`, ta thay vào:

```text
P(x)
= (D[0])
  + (D[0]+D[1])
  + (D[0]+D[1]+D[2])
  + ...
  + (D[0]+...+D[x-1])
```

Đếm số lần xuất hiện của từng mốc:

- `D[0]` xuất hiện `x` lần.
- `D[1]` xuất hiện `x-1` lần.
- `D[2]` xuất hiện `x-2` lần.
- ...
- `D[x-1]` xuất hiện đúng 1 lần.

Do đó:

```text
P(x) = x*D[0] + (x-1)*D[1] + ... + 1*D[x-1]
```

Hay viết thành tổng:

```text
P(x) = sum((x-i)*D[i] với 0 <= i < x)
```

Tách `x-i` thành hai phần:

```text
P(x)
= x * sum(D[i] với i < x)
  - sum(i*D[i] với i < x)
```

**Công thức nền tảng:**

```text
P(x) = x * S1(x) - S2(x)

S1(x) = sum(D[0:x])
S2(x) = sum(i*D[i] với 0 <= i < x)
```

Đây là công thức của **hai Fenwick**. Ta chỉ cần cấu trúc hỗ trợ tổng tiền tố của `D` và tổng tiền tố của `i*D[i]`.

## 7. Tạo mảng hiệu có trọng số

Đặt mảng thứ hai:

```text
W[i] = i * D[i]
```

Trong toàn bài, `i` tại đây là **chỉ số ngoài 0-based** của mảng hiệu.

Với ví dụ:

```text
a = [2, 5, 1, 4, 3]
D = [2, 3, -4, 3, -1]

i:  0   1   2   3   4
D:  2   3  -4   3  -1
W:  0   3  -8   9  -4
```

Công thức tính tổng:

```text
P(x) = x * sum(D[0:x]) - sum(W[0:x])
```

### Kiểm tra bằng tay: x=3

```text
D[0:3] = [2,3,-4]
sum D  = 1

W[0:3] = [0,3,-8]
sum W  = -5

P(3) = 3*1 - (-5) = 8
```

Đúng với:

```text
a[0]+a[1]+a[2] = 2+5+1 = 8
```

### Kiểm tra x=5

```text
sum(D[0:5]) = 2+3-4+3-1 = 3
sum(W[0:5]) = 0+3-8+9-4 = 0

P(5) = 5*3 - 0 = 15
```

Đúng với tổng toàn mảng.

### Kiểm tra x=0

Hai tổng tiền tố rỗng đều bằng 0:

```text
P(0) = 0*0 - 0 = 0
```

Vì vậy công thức tự xử lý tổng của đoạn rỗng ở đầu mảng.

## 8. Hai Fenwick lưu chính xác những gì?

Ta khởi tạo:

```text
B1 = Fenwick(D)
B2 = Fenwick(W)
```

Tên có thể là `BIT1` và `BIT2` hoặc `F` và `G` trong những tài liệu khác. **Ý nghĩa, không phải tên gọi, mới quan trọng:**

- `B1.prefix(x)` trả `S1(x)=sum(D[0:x])`.
- `B2.prefix(x)` trả `S2(x)=sum(i*D[i] với i<x)`.

Vì thế:

```text
prefix_sum(x):
    return x * B1.prefix(x) - B2.prefix(x)
```

Và:

```text
range_sum(l,r):
    return prefix_sum(r) - prefix_sum(l)
```

**Bất biến kép:** sau mọi cập nhật hợp lệ, cả `B1` lẫn `B2` phải tiếp tục là cây Fenwick đúng của `D` và `W` tương ứng.

Nếu chỉ cập nhật `B1` mà quên `B2`, truy vấn tổng mảng thực sẽ sai, ngay cả khi truy vấn giá trị điểm từ `B1` vẫn đúng.

## 9. Cập nhật hai cây Fenwick tại các mốc

Khi có lệnh:

```text
range_add(l, r, delta)
```

và `l<r`, mảng hiệu biến đổi:

```text
D[l] += delta
D[r] -= delta             nếu r < n
```

Mà `W[i]=i*D[i]`, nên:

```text
W[l] += l*delta
W[r] -= r*delta           nếu r < n
```

Do đó, hai BIT cần nhận:

```text
B1.add(l, +delta)
B2.add(l, +l*delta)

if r < n:
    B1.add(r, -delta)
    B2.add(r, -r*delta)
```

Mỗi lệnh `add` là **cập nhật một điểm trong một Fenwick**, mất O(log n). Tổng cộng tối đa **bốn** lần cập nhật điểm, vẫn là O(log n).

### Ghi nhớ dấu của mốc phải

Mốc ở `r` hủy `+delta`:

```text
B1 tại r: -delta
B2 tại r: -(r*delta)
```

Đây là dấu **âm của cả tích**, không phải `(-r)*(-delta)`.

### Biên phải r=n

Với cây Fenwick lưu `n` mốc `D[0..n-1]`, `r=n` nằm **ngoài miền mốc thật**. Ta **không cập nhật `B1.add(n,...)` hay `B2.add(n,...)`**, vì hai BIT này chỉ nhận chỉ số `0..n-1`.

Mốc “tắt tác động” ở n không ảnh hưởng tới bất cứ tiền tố nào của mảng thật `P(x)` với `x<=n`, nên bỏ qua là hoàn toàn đúng.

### Đoạn rỗng

Với `l=r`, không có giá trị nào thay đổi, nên ta bỏ qua cả hai cây. Nếu l=n và r=n, cách này cũng tránh cố cập nhật chỉ số n.

## 10. Truy vết cập nhật [1,4) cộng 3

Mảng ban đầu:

```text
a = [2, 5, 1, 4, 3]
D = [2, 3, -4, 3, -1]
W = [0, 3, -8, 9, -4]
```

Cập nhật `[1,4)` với `delta=3`.

### Hai dấu mốc trong D

```text
D[1] += 3
D[4] -= 3

D mới = [2, 6, -4, 3, -4]
```

### Hai dấu mốc trong W

```text
W[1] += 1*3  = +3
W[4] -= 4*3  = -12

W mới = [0, 6, -8, 9, -16]
```

### Kiểm tra tổng tiền tố sau cập nhật

Tổng toàn mảng:

```text
sum(D[0:5]) = 2+6-4+3-4 = 3
sum(W[0:5]) = 0+6-8+9-16 = -9

P(5) = 5*3 - (-9) = 24
```

Đúng với:

```text
a mới = [2, 8, 4, 7, 3]

2+8+4+7+3 = 24
```

Truy vấn `[1,4)`:

```text
P(4):
sum(D[0:4]) = 2+6-4+3 = 7
sum(W[0:4]) = 0+6-8+9 = 7
P(4) = 4*7-7 = 21

P(1):
sum(D[0:1]) = 2
sum(W[0:1]) = 0
P(1) = 1*2-0 = 2

range_sum(1,4) = 21-2 = 19
```

Đúng vì `8+4+7=19`.

## 11. Truy vết nhiều cập nhật chồng lấn

Tiếp tục từ mảng `[2,8,4,7,3]`.

Áp dụng tiếp:

```text
U2: range_add(2,5,-2)
U3: range_add(0,2,+1)
```

Sau U2:

```text
a  = [2, 8, 2, 5, 1]
D  = [2, 6, -6, 3, -4]
W  = [0, 6, -12, 9, -16]
```

Với U2, `r=5=n` nên chỉ có mốc trái `D[2]-=2` và `W[2]-=4`. Không tạo mốc ở `D[5]`.

Kiểm tra:

```text
sum D = 2+6-6+3-4 = 1
sum W = 0+6-12+9-16 = -13

P(5)=5*1-(-13)=18
```

Đúng vì `2+8+2+5+1=18`.

Sau U3, cộng 1 vào `[0,2)`:

```text
D[0] += 1
D[2] -= 1

W[0] += 0*1 = 0
W[2] -= 2*1 = 2

a = [3, 9, 2, 5, 1]
D = [3, 6, -7, 3, -4]
W = [0, 6, -14, 9, -16]
```

Kiểm tra:

```text
sum D = 3+6-7+3-4 = 1
sum W = 0+6-14+9-16 = -15

P(5)=5*1-(-15)=20
```

Mọi cập nhật được tính cộng dồn đúng, kể cả **đoạn chồng lấn, đoạn chứa nhau, delta âm, delta dương và biên phải n**.

## 12. Fenwick đơn lẻ: hàm hỗ trợ điểm và tổng tiền tố

Trước khi viết cấu trúc hai BIT, ta cần một Fenwick đơn giản.

Lớp dưới đây:

- Nhận một mảng `values` các **số nguyên**.
- Dùng chỉ số **0-based ở phương thức công khai**.
- Lưu cây BIT **1-based** trong `tree[1..n]`.
- Xây dựng từ toàn bộ dữ liệu bằng thuật toán **O(n)**.
- Hỗ trợ `add(index,delta)` và `prefix(end)` trong **O(log n)**.

```python
class FenwickPointPrefix:
    """Cập nhật một điểm, tính tổng tiền tố [0,end)."""

    def __init__(self, values):
        self.n = len(values)
        self.tree = [0] * (self.n + 1)

        # Xây Fenwick tuyến tính O(n).
        for i, value in enumerate(values, start=1):
            self.tree[i] += value

            parent = i + (i & -i)
            if parent <= self.n:
                self.tree[parent] += self.tree[i]

    def add(self, index, delta):
        if type(index) is not int:
            raise TypeError("index phải là số nguyên")
        if not 0 <= index < self.n:
            raise IndexError("index nằm ngoài mảng")

        i = index + 1
        while i <= self.n:
            self.tree[i] += delta
            i += i & -i

    def prefix(self, end):
        if type(end) is not int:
            raise TypeError("end phải là số nguyên")
        if not 0 <= end <= self.n:
            raise IndexError("end nằm ngoài [0,n]")

        answer = 0
        i = end

        while i > 0:
            answer += self.tree[i]
            i -= i & -i

        return answer

    def recover_points(self):
        """Khôi phục các giá trị được lưu trong BIT, O(n)."""
        cells = self.tree.copy()

        # Đảo phép lan truyền khi xây BIT, đi từ chỉ số lớn về nhỏ.
        for i in range(self.n, 0, -1):
            parent = i + (i & -i)
            if parent <= self.n:
                cells[parent] -= cells[i]

        return cells[1:]
```

Phương thức `recover_points` được giải thích ở phần sau; hai thao tác chính của Fenwick vẫn là `add` và `prefix`.

### Kiểm tra một Fenwick đơn

```python
f = FenwickPointPrefix([2, 3, -4, 3, -1])

assert f.tree == [0, 2, 5, -4, 4, -1]
assert f.prefix(0) == 0
assert f.prefix(2) == 5
assert f.prefix(5) == 3
assert f.recover_points() == [2, 3, -4, 3, -1]

f.add(1, 3)
assert f.prefix(2) == 8
assert f.recover_points() == [2, 6, -4, 3, -1]
```

Các giá trị trong `tree` là **tổng vùng Fenwick**, không phải các giá trị đầu vào tại đúng vị trí. Chỉ phương thức `recover_points()` mới trả về các giá trị đang được biểu diễn.

## 13. Cài đặt Python: hai BIT cho cộng đoạn và tổng đoạn

Ta dùng hai Fenwick đơn:

- `b1` lưu `D`.
- `b2` lưu `W[i]=i*D[i]`.

API ngoài xử lý **số nguyên chính xác**. Điều này giúp phép cộng/trừ và phép nhân trọng số có ý nghĩa rõ ràng, không phát sinh sai số làm tròn của số thực.

```python
class RangeAddRangeSum:
    """Cộng đoạn [l,r), tổng đoạn [l,r), 0-based."""

    def __init__(self, values):
        a = list(values)

        if any(type(value) is not int for value in a):
            raise TypeError("Ví dụ này chỉ nhận giá trị nguyên")

        self.n = len(a)
        diff = []
        previous = 0

        # D[i] = a[i] - a[i-1]; riêng D[0] = a[0].
        for value in a:
            diff.append(value - previous)
            previous = value

        weighted_diff = [
            i * value for i, value in enumerate(diff)
        ]

        self.b1 = FenwickPointPrefix(diff)
        self.b2 = FenwickPointPrefix(weighted_diff)

    def _check_range(self, l, r):
        if type(l) is not int or type(r) is not int:
            raise TypeError("l và r phải là số nguyên")
        if not 0 <= l <= r <= self.n:
            raise IndexError("Đoạn [l,r) nằm ngoài mảng")

    def _check_pos(self, pos):
        if type(pos) is not int:
            raise TypeError("pos phải là số nguyên")
        if not 0 <= pos < self.n:
            raise IndexError("pos nằm ngoài mảng")

    def _mark(self, index, change):
        """Thay D[index] và W[index] đúng một lượng."""
        if index == self.n:
            return     # Mốc sentinel không thuộc [0,n).

        self.b1.add(index, change)
        self.b2.add(index, index * change)

    def range_add(self, l, r, delta):
        self._check_range(l, r)
        if type(delta) is not int:
            raise TypeError("delta phải là số nguyên")

        if l == r:
            return

        self._mark(l, delta)
        self._mark(r, -delta)

    def prefix_sum(self, end):
        if type(end) is not int:
            raise TypeError("end phải là số nguyên")
        if not 0 <= end <= self.n:
            raise IndexError("end nằm ngoài [0,n]")

        s1 = self.b1.prefix(end)
        s2 = self.b2.prefix(end)

        return end * s1 - s2

    def range_sum(self, l, r):
        self._check_range(l, r)
        return self.prefix_sum(r) - self.prefix_sum(l)

    def point_get(self, pos):
        self._check_pos(pos)
        return self.range_sum(pos, pos + 1)

    def point_add(self, pos, delta):
        self._check_pos(pos)
        self.range_add(pos, pos + 1, delta)

    def point_assign(self, pos, value):
        self._check_pos(pos)
        if type(value) is not int:
            raise TypeError("value phải là số nguyên")

        old = self.point_get(pos)
        self.range_add(pos, pos + 1, value - old)

    def materialize(self):
        """Khôi phục tất cả giá trị logic, O(n) từ BIT hiệu."""
        diff = self.b1.recover_points()
        result = []
        running = 0

        for value in diff:
            running += value
            result.append(running)

        return result
```

Đây là cấu trúc **hai Fenwick** được áp dụng cho bài toán cộng đoạn/hỏi tổng đoạn. `point_add` và `point_assign` là các tiện ích bổ sung; chúng không làm thay đổi bản chất hai cây.

### Kiểm tra trên mảng có giá trị ban đầu

```python
a = [2, 5, 1, 4, 3]
ds = RangeAddRangeSum(a)

assert ds.n == 5
assert ds.b1.recover_points() == [2, 3, -4, 3, -1]
assert ds.b2.recover_points() == [0, 3, -8, 9, -4]

assert ds.prefix_sum(0) == 0
assert ds.prefix_sum(3) == 8
assert ds.prefix_sum(5) == 15
assert ds.range_sum(2, 5) == 8
assert ds.range_sum(0, 5) == 15
assert ds.range_sum(5, 5) == 0

assert ds.materialize() == a
```

### Cập nhật, truy vấn và chồng lấn

```python
ds.range_add(1, 4, 3)

assert ds.materialize() == [2, 8, 4, 7, 3]
assert ds.range_sum(1, 4) == 19
assert ds.range_sum(0, 5) == 24
assert ds.b1.recover_points() == [2, 6, -4, 3, -4]
assert ds.b2.recover_points() == [0, 6, -8, 9, -16]

ds.range_add(2, 5, -2)

assert ds.materialize() == [2, 8, 2, 5, 1]
assert ds.range_sum(0, 5) == 18

ds.range_add(0, 2, 1)

assert ds.materialize() == [3, 9, 2, 5, 1]
assert ds.range_sum(0, 5) == 20
assert ds.range_sum(2, 5) == 8
assert ds.point_get(2) == 2

# Mảng đầu vào không bị chỉnh sửa.
assert a == [2, 5, 1, 4, 3]
```

### Gán một điểm thông qua cập nhật đoạn

```python
ds.point_assign(2, 10)

assert ds.materialize() == [3, 9, 10, 5, 1]
assert ds.point_get(2) == 10
assert ds.range_sum(0, 5) == 28

ds.point_add(4, -1)

assert ds.materialize() == [3, 9, 10, 5, 0]
assert ds.range_sum(3, 5) == 5
```

Gán điểm phải tính **chênh lệch giữa giá trị mới và giá trị cũ**. Nếu gọi `range_add(pos,pos+1,value)` mà không trừ giá trị cũ, đó là **cộng thêm value**, không phải gán bằng value.

## 14. Vì sao xây hai BIT trong O(n)?

Trong `RangeAddRangeSum.__init__`, ta tính hiệu `D` trong một lượt:

```text
D[0] = a[0]
D[i] = a[i] - a[i-1]
```

Sau đó tạo `W[i]=i*D[i]` trong O(n).

Cả `b1` và `b2` sử dụng cách xây Fenwick **lan truyền tuyến tính**:

```text
for i = 1..n:
    bit[i] += value[i-1]

    parent = i + lowbit(i)
    if parent <= n:
        bit[parent] += bit[i]
```

Mỗi chỉ số được xử lý đúng một lần. Vì thế:

```text
Tạo D:     O(n)
Tạo W:     O(n)
Xây BIT1:  O(n)
Xây BIT2:  O(n)

Tổng:      O(n)
```

Nếu thay bằng n lần gọi `add` cho mỗi cây, thời gian xây sẽ là O(n log n) — vẫn đúng nhưng không tối ưu bằng xây tuyến tính.

### Tại sao mỗi bước đẩy tổng lên cha là hợp lệ?

Khi duyệt tăng dần, những ô nhỏ hơn đã chuyển đóng góp của chúng lên những ô cha thích hợp. Vì vậy tại thời điểm xử lý chỉ số i, `bit[i]` đã chứa tổng của vùng mà nó phụ trách, và có thể chuyển tổng hoàn chỉnh ấy đến:

```text
parent(i) = i + lowbit(i)
```

Cách này duy trì bất biến của Fenwick mà không cần chạy một vòng cập nhật logarit cho mỗi phần tử ban đầu.

## 15. Chứng minh công thức tổng tiền tố bằng đổi thứ tự tổng

Ta chứng minh cẩn thận:

```text
P(x) = x*S1(x) - S2(x)
```

với `S1(x)=ΣD[j]` và `S2(x)=ΣjD[j]` trên `j=0..x-1`.

Theo định nghĩa hiệu:

```text
a[i] = sum(D[j], j=0..i)
```

Nên:

```text
P(x)
 = sum(a[i], i=0..x-1)
 = sum(sum(D[j], j=0..i), i=0..x-1)
```

Đổi thứ tự lấy tổng hữu hạn:

```text
P(x)
 = sum(sum(D[j], i=j..x-1), j=0..x-1)
 = sum((x-j)*D[j], j=0..x-1)
```

Tách hệ số:

```text
P(x)
 = x*sum(D[j], j<x)
   - sum(j*D[j], j<x)
 = x*S1(x)-S2(x)
```

Đây là đẳng thức chính xác trên số nguyên và những miền số học cho phép cộng/trừ/nhân trọng số. Nó đúng cho **mọi giá trị âm hoặc dương**; không cần tính đơn điệu của tổng tiền tố.

**Đặc biệt:** `S1(x)` vốn bằng `a[x-1]` khi `x>0`. Công thức này cho thấy tổng của x phần tử đầu không chỉ phụ thuộc giá trị phần tử cuối, mà còn cần trừ tổng sai phân có trọng số.

## 16. Chứng minh một lệnh cộng đoạn làm đúng mọi tổng tiền tố

Xét một cập nhật:

```text
range_add(l, r, delta)
```

với `0<=l<r<=n`.

Sau cập nhật, tổng tiền tố `P(x)` phải tăng:

```text
DeltaP(x) = delta * số phần tử thuộc giao [0,x) ∩ [l,r)
```

Tức là:

```text
DeltaP(x) =
    0                 nếu x <= l
    delta*(x-l)       nếu l < x <= r
    delta*(r-l)       nếu x > r
```

Với `r=n`, nhánh `x>r` không xảy ra vì x chỉ nằm trong `[0,n]`.

Ta kiểm tra tác động của hai mốc D/W.

### Trường hợp 1: x <= l

Cả mốc ở l và r đều nằm ngoài tiền tố `[0,x)`:

```text
DeltaS1(x) = 0
DeltaS2(x) = 0

DeltaP(x) = x*0 - 0 = 0
```

Đúng vì tiền tố chưa chạm đoạn cập nhật.

### Trường hợp 2: l < x <= r

Tiền tố đã đi qua mốc trái ở l, chưa đi qua mốc phải ở r:

```text
DeltaS1(x) = +delta
DeltaS2(x) = +l*delta
```

Vậy:

```text
DeltaP(x)
 = x*delta - l*delta
 = delta*(x-l)
```

Đúng bằng số phần tử được cập nhật trong `[l,x)`.

### Trường hợp 3: x > r

Tiền tố đã đi qua cả mốc ở l và mốc ở r:

```text
DeltaS1(x) = +delta-delta = 0

DeltaS2(x) = l*delta-r*delta
           = (l-r)*delta
```

Do đó:

```text
DeltaP(x)
 = x*0 - (l-r)*delta
 = (r-l)*delta
```

Đúng bằng tác động của **toàn bộ đoạn cập nhật**.

Ba trường hợp bao phủ mọi `x` hợp lệ. Vậy cập nhật hai BIT đúng với mọi tổng tiền tố, suy ra cũng đúng với mọi tổng đoạn:

```text
range_sum(l,r) = P(r)-P(l)
```

## 17. Chồng lấn nhiều lần: tính tuyến tính của cập nhật

Các cập nhật cộng đoạn có thể:

- Rời nhau.
- Giao nhau một phần.
- Lồng nhau.
- Trùng nhau hoàn toàn.
- Có `delta` dương hoặc âm.
- Có tổng tác động triệt tiêu nhau.

Với số học chính xác, mỗi lệnh góp một cặp mốc. Mảng hiệu cuối cùng là **tổng của những đóng góp mốc**, và công thức tiền tố là **tuyến tính theo D**:

```text
P(x) = x*sum(D[0:x]) - sum(i*D[i], i<x)
```

Nếu `D=D_base+D_update1+...+D_updateq`, tổng tiền tố sau q lần cộng bằng tổng tiền tố ban đầu cộng các tác động tương ứng, không phụ thuộc thứ tự cộng các số chính xác.

### Ví dụ trên mảng toàn số 0

Cho `n=8` và ba lệnh:

```text
U1: [1,6) +3
U2: [3,8) -2
U3: [0,4) +1
```

Trạng thái sau từng lệnh:

```text
Ban đầu: [0,0,0,0,0,0,0,0]
Sau U1:  [0,3,3,3,3,3,0,0]
Sau U2:  [0,3,3,1,1,1,-2,-2]
Sau U3:  [1,4,4,2,1,1,-2,-2]
```

Các mốc tổng hợp:

```text
D = [1, 3, 0, -2, -1, 0, -3, 0]
W = [0, 3, 0, -6, -4, 0, -18, 0]
```

Tổng toàn mảng cuối:

```text
sum(D) = -2
sum(W) = -25

P(8) = 8*(-2) - (-25) = 9
```

Đúng vì:

```text
1+4+4+2+1+1-2-2 = 9
```

Truy vấn `[2,7)` cho kết quả:

```text
4+2+1+1-2 = 6
```

Đây là minh chứng cụ thể rằng **dữ liệu âm và cập nhật âm hoàn toàn hợp lệ** cho bài toán cộng đoạn/hỏi tổng đoạn.

## 18. Vì sao không cần phần tử không âm?

Ở một số bài toán Fenwick, chẳng hạn **tìm biên đầu tiên có tổng tiền tố đạt ngưỡng**, người học gặp điều kiện mọi phần tử không âm để tổng tiền tố không giảm.

**Bài cộng đoạn và tổng đoạn không có điều kiện đó.**

Ta chỉ dùng:

1. Phép cộng và trừ trên dữ liệu.
2. Bất biến Fenwick cho tổng.
3. Đẳng thức đại số của hiệu và tổng.
4. Phép nhân với chỉ số nguyên.

Không có bước tìm kiếm trên thứ tự của các tổng tiền tố. Do đó số âm, tổng âm và các tiền tố không đơn điệu **không làm sai thuật toán**.

### Thử dữ liệu có số âm ngay từ đầu

```python
ds = RangeAddRangeSum([5, -10, 10])

assert ds.materialize() == [5, -10, 10]
assert ds.prefix_sum(2) == -5
assert ds.range_sum(1, 3) == 0

ds.range_add(0, 2, -3)

assert ds.materialize() == [2, -13, 10]
assert ds.prefix_sum(3) == -1
assert ds.range_sum(0, 2) == -11
```

Nếu một lời giải cho **range add + range sum** yêu cầu “mọi phần tử phải không âm” mà không có thao tác tìm theo ngưỡng, hãy kiểm tra xem nó có đang nhầm với **Fenwick order statistics** không.

## 19. Vì sao một BIT trên hiệu không đủ cho tổng đoạn O(log n)?

Giả sử chỉ lưu tổng tiền tố của D bằng `B1`.

Ta có thể biết:

```text
S1(x) = sum(D[0:x]) = a[x-1]    với x>0
```

Nhưng muốn lấy:

```text
P(x) = sum(a[0:x])
```

ta cần **lượng đóng góp nhiều lần của từng mốc**, tùy mốc cách biên x bao xa.

### Phản ví dụ với cùng tổng D, khác tổng a

Xét hai dãy D dài 2:

```text
D_A = [1,0]
D_B = [0,1]
```

Hai dãy đều có:

```text
sum(D[0:2]) = 1
```

Nhưng mảng thực tương ứng:

```text
a_A = [1,1]     => P_A(2)=2
a_B = [0,1]     => P_B(2)=1
```

Nếu chỉ biết `S1(2)=1`, ta không phân biệt được hai tổng thực.

Trọng số khắc phục:

```text
W_A = [0,0] => S2_A(2)=0 => P_A(2)=2*1-0=2
W_B = [0,1] => S2_B(2)=1 => P_B(2)=2*1-1=1
```

Vì vậy, **hai loại tổng tiền tố** là phần thông tin cần cho công thức O(log n) đang triển khai.

Không có nghĩa ta **không thể** tính tổng từ một BIT lưu D bằng bất cứ cách nào: ta vẫn có thể quét/tái dựng mảng, nhưng không có công thức lấy ngay tổng thực từ **một tổng tiền tố D** như trong BIT tổng thông thường.

## 20. Quy đổi sang chỉ số 1-based đóng

Nhiều đề thuật toán viết:

```text
Tăng delta cho tất cả vị trí L, L+1, ..., R

1 <= L <= R <= n
```

Đây là đoạn **đóng 1-based `[L,R]`**, không phải đoạn nửa mở ngoài 0-based.

Quy đổi:

```text
l = L - 1
r = R

[L,R] 1-based đóng
    <=> [L-1,R) 0-based nửa mở
```

### Công thức 1-based thường gặp

Nếu viết toàn bộ thuật toán trực tiếp theo chỉ số 1-based:

```text
d[1] = a[1]
d[i] = a[i]-a[i-1]

B1 lưu d[i]
B2 lưu (i-1)*d[i]
```

Với cập nhật đóng `[L,R]`:

```text
B1.add(L, +delta)
B2.add(L, +(L-1)*delta)

if R+1 <= n:
    B1.add(R+1, -delta)
    B2.add(R+1, -R*delta)
```

Và:

```text
prefix_sum(x)
  = x * B1.prefix(x) - B2.prefix(x)
```

Ở đây `B1.add`/`B2.add` được hiểu là **API cập nhật vị trí 1-based**, không phải phương thức `add` 0-based của lớp Python ở mục 12.

### Cách công thức 1-based khớp với bản Python

Vị trí 1-based `i` tương ứng chỉ số 0-based `j=i-1`. Vì vậy:

```text
(i-1)*d[i] = j*D[j]
```

Và mốc phải `R+1` 1-based tương ứng `r=R` 0-based, đúng với vị trí tắt tác động trong cách viết `[l,r)`.

**Lỗi phổ biến:** lấy công thức `(i-1)*d[i]` của 1-based rồi lại nhân `(index-1)` trong API 0-based. Trong mã bài này, hệ 0-based dùng chính xác **`index*change`**.

### Adapter Python

```python
def range_add_inclusive_1based(ds, L, R, delta):
    if type(L) is not int or type(R) is not int:
        raise TypeError("L và R phải là số nguyên")

    if not 1 <= L <= R <= ds.n:
        raise IndexError("Đoạn [L,R] 1-based không hợp lệ")

    ds.range_add(L - 1, R, delta)


def range_sum_inclusive_1based(ds, L, R):
    if type(L) is not int or type(R) is not int:
        raise TypeError("L và R phải là số nguyên")

    if not 1 <= L <= R <= ds.n:
        raise IndexError("Đoạn [L,R] 1-based không hợp lệ")

    return ds.range_sum(L - 1, R)


ds = RangeAddRangeSum([2, 5, 1, 4, 3])

range_add_inclusive_1based(ds, 2, 4, 3)

assert ds.materialize() == [2, 8, 4, 7, 3]
assert range_sum_inclusive_1based(ds, 2, 4) == 19
```

Với `n=0`, không tồn tại đoạn đóng 1-based không rỗng nào. Truy vấn đoạn rỗng chỉ được hỗ trợ bởi API nửa mở `[0,0)` của cấu trúc chính.

## 21. Biên rỗng, biên toàn mảng và mảng rỗng

### Mảng không có phần tử

```python
empty = RangeAddRangeSum([])

assert empty.n == 0
assert empty.prefix_sum(0) == 0
assert empty.range_sum(0, 0) == 0
assert empty.materialize() == []

empty.range_add(0, 0, 100)
assert empty.materialize() == []
```

Trong trường hợp này, `b1.tree` và `b2.tree` chỉ chứa ô đệm 0; không có mốc nào trong miền thật.

### Mảng một phần tử

```python
one = RangeAddRangeSum([7])

assert one.range_sum(0, 1) == 7

one.range_add(0, 1, -3)
assert one.materialize() == [4]

one.range_add(1, 1, 999)
assert one.materialize() == [4]

one.point_assign(0, 10)
assert one.range_sum(0, 1) == 10
```

Đối với `n=1`, cập nhật `[0,1)` chạm mốc `D[0]` và bỏ mốc tại `r=n=1`.

### Cập nhật toàn mảng

```python
ds = RangeAddRangeSum([1, 2, 3])

ds.range_add(0, 3, 5)

assert ds.materialize() == [6, 7, 8]
assert ds.range_sum(0, 3) == 21
```

Cập nhật toàn mảng chỉ cần mốc `D[0]+=5`, vì không có biên tắt nào bên trong mảng.

### Cập nhật rỗng ở đầu, giữa, cuối

```python
ds = RangeAddRangeSum([1, 2, 3])

for l in [0, 1, 3]:
    ds.range_add(l, l, 12345)

assert ds.materialize() == [1, 2, 3]
assert ds.range_sum(2, 2) == 0
assert ds.range_sum(3, 3) == 0
```

### Từ chối chỉ số âm, đảo biên và vượt n

```python
ds = RangeAddRangeSum([1, 2, 3])

for l, r in [(-1, 2), (2, 1), (0, 4), (4, 4)]:
    try:
        ds.range_add(l, r, 10)
    except IndexError:
        pass
    else:
        raise AssertionError("Đoạn ngoài phạm vi phải bị từ chối")

try:
    ds.range_sum(True, 2)
except TypeError:
    pass
else:
    raise AssertionError("Không chấp nhận Boolean làm chỉ số")
```

Hợp đồng kiểm tra `type(x) is int` cố ý từ chối `bool`, dù `bool` là lớp con của `int` trong Python.

## 22. Khôi phục toàn bộ mảng từ BIT hiệu trong O(n)

Nếu một ứng dụng muốn xuất tất cả n giá trị sau một chuỗi cập nhật, cách hiển nhiên là:

```text
for i = 0..n-1:
    result[i] = range_sum(i,i+1)
```

Mỗi truy vấn điểm có chi phí O(log n), nên tổng thành **O(n log n)**.

Tuy nhiên, phương thức `materialize()` trong ví dụ dùng một cách **O(n)**:

1. Khôi phục các giá trị `D[0],...,D[n-1]` từ `b1`.
2. Cộng dồn `D` để lấy `a`.

### Đảo quy trình xây Fenwick tuyến tính

Khi xây Fenwick tuyến tính theo thứ tự tăng, mỗi ô i chuyển tổng hoàn chỉnh của vùng nó đến:

```text
parent(i) = i + lowbit(i)
```

Để lấy lại các giá trị gốc, sao chép bảng `tree` rồi **đảo các phép chuyển theo thứ tự giảm dần**:

```text
for i = n..1:
    parent = i + lowbit(i)
    if parent <= n:
        cells[parent] -= cells[i]
```

Sau khi đảo hết, `cells[1:n+1]` chính là các giá trị đầu vào đã tạo BIT hiện tại. Phương thức `recover_points` đã triển khai đúng cách này.

### Truy vết với D gốc

```text
D = [2, 3, -4, 3, -1]

BIT1:
index:  0  1  2   3  4   5
tree:   0  2  5  -4  4  -1
```

Đảo từ i=5 về i=1 sẽ khôi phục:

```text
[2, 3, -4, 3, -1]
```

Rồi cộng dồn:

```text
[2, 5, 1, 4, 3]
```

**Quan trọng:** `recover_points` sao chép `tree` trước, nên không phá hỏng Fenwick đang dùng để truy vấn/cập nhật. Nếu sửa trực tiếp các ô gốc khi đảo, cây sẽ không còn ở dạng tổng vùng đúng để xử lý những thao tác sau.

### Vì sao cách đảo vẫn đúng sau các cập nhật?

Mỗi lần `FenwickPointPrefix.add` duy trì chính xác BIT của mảng điểm hiện tại. Bất kỳ BIT đúng nào như vậy đều là kết quả của phép biến đổi tuyến tính khi xây từ các điểm tương ứng. Đảo các phép lan truyền theo thứ tự ngược do đó khôi phục được những điểm hiện tại, **không chỉ điểm lúc khởi tạo**.

Chi phí là O(n) phép số học và O(n) bộ nhớ cho bản sao cùng đầu ra.

## 23. Cập nhật điểm, gán đoạn và những giới hạn

Hai BIT của bài hỗ trợ **cộng một lượng giống nhau vào mọi phần tử trong đoạn**.

### Cộng một điểm

Là trường hợp riêng của cộng đoạn:

```text
point_add(pos,delta)
    = range_add(pos,pos+1,delta)
```

Mất O(log n).

### Gán một điểm

Để thực hiện `a[pos]=new_value`:

```text
old = range_sum(pos,pos+1)
delta = new_value-old
range_add(pos,pos+1,delta)
```

Mất O(log n) vì số lần gọi Fenwick là hằng số.

### Gán cả đoạn khác với cộng đoạn

Lệnh:

```text
assign([l,r),x)
```

yêu cầu mọi phần tử trong đoạn trở thành **đúng x**, không phải tăng thêm x.

Ví dụ:

```text
a = [2,5,1,4,3]

Gán [1,4) thành 7
=> [2,7,7,7,3]
```

Nếu gọi `range_add(1,4,7)`, kết quả là:

```text
[2,12,8,11,3]
```

hoàn toàn khác.

**Hai BIT cộng đoạn không tự hỗ trợ gán đoạn O(log n)** với đúng những công thức mốc cộng/trừ trên. Nếu cần cộng đoạn, gán đoạn và tổng đoạn xen kẽ, một **segment tree với lazy propagation và quy tắc hợp thành tag** là lựa chọn phổ biến.

### Cập nhật nhân đoạn

Phép nhân mọi phần tử trong đoạn với một hệ số cũng không thể được mô phỏng đơn giản bằng hai mốc cộng không phụ thuộc giá trị cũ. Mỗi phần tử có mức thay đổi phụ thuộc chính nó.

Đừng đánh đồng khả năng “cộng đoạn” với “mọi kiểu cập nhật đoạn”.

## 24. Khi nào nên chọn hai BIT?

Có bốn tình huống dễ gặp:

### 24.1. Dữ liệu tĩnh, chỉ hỏi tổng đoạn

Nếu không cập nhật:

```text
P[0] = 0
P[i+1] = P[i]+a[i]

sum([l,r)) = P[r]-P[l]
```

Prefix sum tĩnh thường tốt hơn: xây O(n), hỏi O(1), bộ nhớ O(n).

### 24.2. Cộng điểm và hỏi tổng đoạn

Một Fenwick lưu trực tiếp `a` là đủ:

```text
point_add: O(log n)
range_sum: O(log n)
```

Không cần hai cây.

### 24.3. Cộng đoạn nhưng chỉ hỏi giá trị tại một điểm

Một Fenwick lưu `D` là đủ:

```text
range_add: O(log n)
point_get: O(log n)
```

Vẫn không cần cây có trọng số.

### 24.4. Cộng đoạn và hỏi tổng đoạn trực tuyến

Hai Fenwick trên `D` và `iD[i]`:

```text
range_add: O(log n)
range_sum: O(log n)
```

Đây là **trường hợp mục tiêu** của bài học.

### Nếu chỉ có một lô cập nhật và sau cùng xuất kết quả

Mảng hiệu thông thường còn đơn giản hơn:

```text
Ghi mỗi cập nhật: O(1)
Kết xuất toàn bộ sau q cập nhật: O(n)

Tổng: O(n+q)
```

Không nên dùng hai BIT chỉ vì nó “mạnh hơn” khi bài không cần truy vấn xen kẽ.

## 25. So sánh chi phí các cấu trúc

Gọi:

- `n`: số phần tử.
- `q`: số truy vấn tổng đoạn.
- `u`: số lần cộng đoạn.
- `k=r-l`: số phần tử của đoạn đang thao tác.

| Cấu trúc | Xây | Cộng đoạn | Tổng đoạn | Bộ nhớ phụ tiêu biểu |
|---|---:|---:|---:|---:|
| Mảng, sửa/quét trực tiếp | O(1) ngoài dữ liệu | O(k) | O(k) | O(1) |
| Prefix sum tĩnh | O(n) | O(n) để duy trì bảng | O(1) | O(n) |
| Mảng hiệu theo lô | O(n) khởi tạo/khôi phục | O(1) ghi mốc | Không online O(log n) trực tiếp | O(n) |
| BIT trên mảng gốc | O(n) | O(k log n) nếu gọi point add từng phần tử | O(log n) | O(n) |
| BIT trên mảng hiệu | O(n) | O(log n) | Không trực tiếp O(log n) bằng một hiệu tiền tố | O(n) |
| **Hai Fenwick có trọng số** | **O(n)** | **O(log n)** | **O(log n)** | **O(n)** |
| Sqrt decomposition lazy cộng | O(n) | O(√n) | O(√n) | O(n) gồm mảng |
| Segment tree lazy cộng/tổng | O(n) | O(log n) | O(log n) | O(n) |

Các cận dùng mô hình RAM với phép số học trên mỗi giá trị là O(1). Một `range_add` bao gồm **tối đa bốn lần cập nhật một điểm Fenwick**, không phải O(1) bất kể n.

Với một lần xây, `u` cập nhật đoạn và `q` truy vấn tổng, tổng chi phí của hai Fenwick là:

```text
O(n + (u+q)log n)
```

Nếu có thêm `p` lần gán điểm, thời gian tổng trở thành:

```text
O(n + (u+q+p)log n)
```

Bộ nhớ của lớp gồm hai Fenwick với tổng `2(n+1)` ô lưu, cộng các mảng tạm khởi tạo O(n); do đó tổng vẫn là **O(n)**.

## 26. Vì sao phương pháp hai BIT vẫn đúng khi r=n?

Xét cập nhật `[l,n)` với `delta`.

Trong mảng hiệu hữu hạn độ dài n, chỉ mốc:

```text
D[l] += delta
```

được lưu. Nó làm mọi giá trị `a[i]` từ l đến n-1 tăng `delta`, vì không có biên tắt nào trước khi hết mảng.

Trong công thức tiền tố, mọi `x<=n` chỉ xét mốc có chỉ số `i<x`.

Nếu `x<=l`, mốc trái chưa được xét nên không thay đổi tổng.

Nếu `l<x<=n`, công thức tăng:

```text
DeltaP(x)
 = x*delta - l*delta
 = (x-l)*delta
```

Đúng bằng số phần tử trong `[l,x)`.

Một dấu trừ giả định ở chỉ số n sẽ **không được đưa vào bất kỳ tổng tiền tố `[0,x)` nào với x<=n**, kể cả khi x=n, nên không cần lưu.

**Không được cố chạy `Fenwick.add(n,-delta)` nếu phương thức nhận chỉ số 0-based `0..n-1`.** Mã `_mark` đã kiểm tra sentinel ở n và bỏ qua.

## 27. Giá trị âm, số lớn và tính chính xác

Hai Fenwick dùng phép:

```text
end * S1(end) - S2(end)
```

Nếu `delta` âm, dấu của cả hai mốc và trọng số có thể âm. Điều đó hoàn toàn hợp lệ đối với tổng số nguyên.

### Giá trị lớn có thể gây tràn trong ngôn ngữ số cố định

Giả sử `n` và `delta` rất lớn. Một mốc trọng số có độ lớn:

```text
index * delta
```

và phép tổng tiền tố có tích:

```text
end * S1(end)
```

Ngay cả khi **kết quả tổng đoạn cuối** không quá lớn nhờ triệt tiêu, **những biểu thức trung gian** có thể vượt giới hạn của số nguyên 32-bit.

Trong C++ hoặc Java, cần chọn kiểu đủ rộng và đánh giá **cả tích trung gian**, chẳng hạn `long long` / `long` nếu bảo đảm không vượt miền tương ứng. Trong Python, `int` hỗ trợ độ lớn tùy ý theo bộ nhớ nên không tràn kiểu cố định, nhưng phép toán trên số rất lớn có chi phí tăng theo độ dài bit.

### Số thực

Với `float`, công thức đúng trong số học thực nhưng phép cộng, nhân và trừ trong máy có thể làm tròn. Hai BIT gộp số theo thứ tự khác quét mảng, nên kết quả có thể chênh lệch nhỏ. Ngoài ra, phép trừ hai số gần bằng nhau có thể làm mất độ chính xác.

Khi ứng dụng cần tiền tệ, có thể dùng **số nguyên theo đơn vị nhỏ nhất**. Khi cần phép tính thập phân, có thể sử dụng kiểu số thập phân với chính sách sai số phù hợp.

### Không dùng điều kiện mọi phần tử phải không âm

Điều kiện không âm thuộc về **tìm biên theo tổng tích lũy** dựa trên tính đơn điệu, không thuộc yêu cầu của **range add + range sum**. Kết quả tổng âm là bình thường và không phải lỗi thuật toán.

## 28. Sơ đồ luồng dữ liệu

```text
Mảng gốc a[0..n-1]
       |
       | tạo sai phân
       v
D[i] = a[i] - a[i-1]
       |
       +-------------------------------+
       |                               |
       v                               v
BIT1 lưu D[i]                    W[i] = i*D[i]
                                       |
                                       v
                                BIT2 lưu W[i]

Khi cộng delta vào [l,r):
    D[l] += delta          => BIT1.add(l,+delta)
    W[l] += l*delta        => BIT2.add(l,+l*delta)

    Nếu r<n:
        D[r] -= delta      => BIT1.add(r,-delta)
        W[r] -= r*delta    => BIT2.add(r,-r*delta)

Khi hỏi P(x):
    S1 = BIT1.prefix(x)
    S2 = BIT2.prefix(x)
    P(x) = x*S1 - S2

Khi hỏi tổng [l,r):
    P(r) - P(l)
```

Sơ đồ cho thấy hai cây nhận **cùng các mốc chỉ số nhưng trọng số khác nhau**. Không có bước nào đòi hỏi phải giữ mảng gốc luôn được cập nhật từng phần tử.

## 29. Kiểm thử đối chiếu với mảng cập nhật trực tiếp

Trong triển khai thật, có thể đặt một **bản chậm dễ hiểu** làm chuẩn (*oracle*) trên dữ liệu nhỏ.

```python
def apply_range_add_direct(values, l, r, delta):
    if not 0 <= l <= r <= len(values):
        raise IndexError("Đoạn sai")

    for i in range(l, r):
        values[i] += delta


reference = [2, 5, 1, 4, 3]
ds = RangeAddRangeSum(reference)

updates = [
    (1, 4, 3),
    (2, 5, -2),
    (0, 2, 1),
    (1, 1, 999),
    (0, 5, -4),
    (4, 5, 7),
]

for l, r, delta in updates:
    apply_range_add_direct(reference, l, r, delta)
    ds.range_add(l, r, delta)

    assert ds.materialize() == reference

    # Mỗi cặp biên được kiểm tra.
    for left in range(len(reference) + 1):
        for right in range(left, len(reference) + 1):
            assert ds.range_sum(left, right) == sum(
                reference[left:right]
            )
```

Vì `reference` được cập nhật trực tiếp, vòng lặp xác minh rằng hai Fenwick luôn mô tả cùng trạng thái với mảng thật sau **mỗi** thao tác.

Đây là kiểm thử đúng đắn trên mảng nhỏ, không phải thuật toán truy vấn sản xuất: nó duyệt O(n²) đoạn sau mỗi cập nhật.

### Kiểm tra trực tiếp hai bất biến

```python
def assert_two_bit_invariants(ds, reference):
    assert len(reference) == ds.n

    diff = []
    previous = 0

    for value in reference:
        diff.append(value - previous)
        previous = value

    weighted = [i * value for i, value in enumerate(diff)]

    assert ds.b1.recover_points() == diff
    assert ds.b2.recover_points() == weighted

    for end in range(ds.n + 1):
        assert ds.prefix_sum(end) == sum(reference[:end])


reference = [5, -10, 10, 0]
ds = RangeAddRangeSum(reference)

assert_two_bit_invariants(ds, reference)

for l, r, delta in [
    (0, 4, 3),
    (1, 3, -4),
    (2, 2, 99),
    (3, 4, 7),
]:
    apply_range_add_direct(reference, l, r, delta)
    ds.range_add(l, r, delta)
    assert_two_bit_invariants(ds, reference)
```

Kiểm tra riêng `B1` và `B2` có thể phát hiện trường hợp một cây được cập nhật đúng nhưng cây còn lại **thiếu mốc hoặc sai trọng số**, ngay cả khi một vài truy vấn tình cờ cho kết quả đúng.

## 30. Bộ trường hợp khó cần có trong kiểm thử

### 30.1. n=0 và n=1

```python
empty = RangeAddRangeSum([])
assert empty.range_sum(0, 0) == 0
empty.range_add(0, 0, 100)
assert empty.materialize() == []

single = RangeAddRangeSum([3])
single.range_add(0, 1, -10)

assert single.materialize() == [-7]
assert single.range_sum(0, 1) == -7
```

### 30.2. Đoạn dài đúng một phần tử

```python
ds = RangeAddRangeSum([1, 2, 3])

ds.range_add(1, 2, 10)

assert ds.materialize() == [1, 12, 3]
assert ds.range_sum(1, 2) == 12
```

### 30.3. Đoạn rỗng tại n

```python
ds = RangeAddRangeSum([1, 2, 3])
ds.range_add(3, 3, 10000)

assert ds.materialize() == [1, 2, 3]
assert ds.range_sum(3, 3) == 0
```

### 30.4. Tăng rồi giảm triệt tiêu

```python
ds = RangeAddRangeSum([3, 1, 4, 1])

ds.range_add(1, 4, +7)
ds.range_add(1, 4, -7)

assert ds.materialize() == [3, 1, 4, 1]
assert ds.range_sum(0, 4) == 9
```

### 30.5. Dữ liệu có âm và tổng bằng 0

```python
ds = RangeAddRangeSum([-2, 2, -5, 5])

assert ds.range_sum(0, 4) == 0

ds.range_add(1, 3, -2)

assert ds.materialize() == [-2, 0, -7, 5]
assert ds.range_sum(0, 4) == -4
```

### 30.6. Đầu vào sai kiểu

```python
ds = RangeAddRangeSum([1, 2, 3])

try:
    ds.range_add(0, 2, 1.5)
except TypeError:
    pass
else:
    raise AssertionError("Ví dụ chỉ cho delta nguyên")

try:
    ds.range_sum(False, 2)
except TypeError:
    pass
else:
    raise AssertionError("Không nhận Boolean làm biên")
```

Những kiểm thử này nhằm xác định cả **giá trị đúng** và **hành vi khi đầu vào sai**, không chỉ xác minh công thức ở trường hợp trung bình.

## 31. Những lỗi thường gặp khi triển khai hai Fenwick

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Chỉ dùng một BIT lưu D rồi lấy hiệu hai prefix để hỏi tổng a | Hiệu tiền tố D là tổng **hiệu**, không phải tổng **giá trị** | Dùng hai BIT và công thức trọng số |
| Quên xây BIT2 từ `i*D[i]` | Không có thông tin về vị trí của các mốc | Xây `W[i]=i*D[i]` |
| Dùng `i+1` làm trọng số với API 0-based mà không đổi công thức | Công thức `P(x)=x*S1-S2` bị lệch | Trong bài dùng **i**, bắt đầu từ 0 |
| Trộn công thức 1-based `(i-1)*D[i]` với chỉ số 0-based | Sai trọng số mọi mốc trừ biên đầu | Ánh xạ rõ `i_1based=j_0based+1` |
| Ghi `B2.add(r,+r*delta)` | Mốc phải có dấu sai, tác động không tắt | Dùng **`-r*delta`** |
| Quên mốc `B1.add(r,-delta)` khi `r<n` | Tác động kéo dài quá r | Ghi cả hai mốc hiệu |
| Cập nhật B1 nhưng không cập nhật B2 | Tổng điểm có thể đúng, tổng đoạn sai | Mọi mốc phải cập nhật **hai** BIT |
| Cho `r=n` rồi gọi `Fenwick.add(n,...)` 0-based | Truy cập ngoài miền mốc | Bỏ mốc ở n |
| Dùng đoạn đóng như `[l,r)` | Sai ở phần tử biên phải | Chuẩn hóa chỉ số |
| Ghi trừ tại `r-1` | Phần tử cuối đoạn không nhận delta | Ghi trừ tại `r` |
| Cập nhật `l=r` không kiểm tra | Mốc trái và phải có thể không cần thiết | Bỏ qua đoạn rỗng |
| Tính `prefix_sum(x)=S1-S2` mà quên hệ số x | Không còn đúng tổng mảng thật | `x*S1-S2` |
| Tính `S2-x*S1` | Tổng bị đổi dấu | `x*S1-S2` |
| Dùng `prefix_sum(r)+prefix_sum(l)` cho tổng đoạn | Đếm thừa tiền tố bên trái | Dùng `P(r)-P(l)` |
| Nhầm `point_assign(pos,x)` với `range_add(pos,pos+1,x)` | Cộng x thay vì gán x | Cập nhật chênh lệch `x-old` |
| Chỉ khởi tạo B1/B2 bằng 0 khi mảng gốc không rỗng | Quên dữ liệu ban đầu | Xây từ hiệu của a gốc |
| Đọc chỉ số BIT từ 0 và dùng lowbit(0) | Vòng cập nhật có thể không tiến | BIT nội bộ 1-based |
| Bỏ qua lỗi chỉ số âm | Python có thể dùng chỉ số âm khác ý định | Validate `0<=l<=r<=n` |
| Sửa trực tiếp BIT khi khôi phục D | Phá hỏng bất biến cây | Khôi phục trên bản sao |
| Gọi n lần query để xuất mảng rồi báo O(n) | Mỗi query O(log n) | O(nlog n), hoặc đảo BIT O(n) |
| Khẳng định mọi cập nhật đoạn đều dùng hai BIT | Gán/nhân đoạn không là cộng tuyến tính | Chọn cấu trúc khác hoặc biến thể riêng |
| Bắt buộc dữ liệu không âm khi chỉ hỏi tổng | Điều kiện không liên quan | Cho phép số âm nếu kiểu số hỗ trợ |
| Quên xét tràn số trung gian `r*delta` | Có thể tràn dù đáp án cuối nhỏ | Chọn kiểu số đủ rộng |
| Báo cập nhật đoạn O(1) | Mỗi mốc dùng point update O(log n) | Tổng O(log n), không phải O(1) |

## 32. Câu hỏi thường gặp

### Q1. Tại sao phải dùng đúng hai BIT?

Trong biểu thức tiền tố:

```text
P(x) = x*sum(D[0:x]) - sum(i*D[i], i<x)
```

có **hai loại tổng**. Mỗi BIT hỗ trợ một loại tổng tiền tố khi các mốc được cập nhật trực tuyến. Có thể thiết kế những cấu trúc khác, nhưng trong phương pháp này, hai BIT phản ánh chính xác hai thành phần cần tính.

### Q2. Tại sao BIT2 không lưu `a[i]*i`?

Vì công thức xuất phát từ **mảng hiệu D**, nên tổng có trọng số là `i*D[i]`. Lưu `i*a[i]` không tạo công thức `P(x)=x*S1-S2` đang dùng.

### Q3. Hai cây có thể có giá trị âm không?

Có. Sai phân vốn có thể âm ngay cả khi mảng a không âm; sau nhiều cập nhật, trọng số có thể dương/âm. Không ảnh hưởng tính đúng của truy vấn tổng.

### Q4. Có thể cập nhật một điểm với hai BIT không?

Có, dùng `range_add(pos,pos+1,delta)`. Tuy nhiên, nếu bài **chỉ** yêu cầu cộng điểm và tổng đoạn, **một BIT trên mảng gốc** đơn giản và tiết kiệm hằng số hơn.

### Q5. Nếu r=n thì có phải cấp phát BIT dài n+1 mốc thật?

Không. Hai Fenwick trong bài dùng n vị trí mốc thật, cùng một ô đệm 1-based ở đầu. Mốc ở r=n không ảnh hưởng tiền tố nào trong miền thật, nên được bỏ qua.

### Q6. Hàm materialize có làm mất các cập nhật đã ghi không?

Không. Nó sao chép cấu trúc BIT1 rồi đảo biến đổi trên bản sao, sau đó cộng dồn sai phân. Hai BIT gốc không đổi và tiếp tục xử lý cập nhật/truy vấn.

### Q7. Nếu có rất nhiều cập nhật nhưng chỉ hỏi một lần cuối thì sao?

Mảng hiệu theo lô là lựa chọn đơn giản hơn: cập nhật O(1) mỗi lần và dựng O(n) một lần. Hai BIT có lợi rõ ràng khi **cập nhật và truy vấn tổng xen kẽ**.

### Q8. Có thể kết hợp với phép min thay phép sum được không?

Không thể lấy hiệu hai prefix min như phép cộng, vì min không có phép nghịch đảo tổng quát. Với cập nhật đoạn và truy vấn min, cần cấu trúc thích hợp như segment tree lazy hoặc phương án chuyên biệt.

### Q9. Truy vấn tổng có cần tổng tiền tố đơn điệu?

Không. Cộng và trừ vẫn đúng khi tổng tăng giảm, có giá trị âm hoặc bằng 0. Đơn điệu chỉ là tiền điều kiện của một số bài **tìm biên theo ngưỡng**, không phải tổng đoạn.

### Q10. Vì sao hai BIT vẫn chỉ tốn O(n) bộ nhớ?

Mỗi cây giữ n+1 ô. Hai lần một lượng tuyến tính vẫn tuyến tính:

```text
2*(n+1) = O(n)
```

Các mảng `D` và `W` tạm thời trong bước xây cũng có tổng số phần tử O(n).

## 33. Bài tập tự luyện có lời giải

**Bài 1 — Mảng hiệu.** Cho `a=[2,5,1,4,3]`. Tìm `D`.

*Lời giải:* **`[2,3,-4,3,-1]`**.

**Bài 2 — Trọng số.** Với `D` ở bài 1, tính `W[i]=i*D[i]` theo 0-based.

*Lời giải:* **`[0,3,-8,9,-4]`**.

**Bài 3 — Tổng tiền tố.** Dùng `S1(3)=1` và `S2(3)=-5`, tính `P(3)`.

*Lời giải:* `3*1-(-5)=8`.

**Bài 4 — Vì sao hai BIT?** Hai tổng tiền tố nào được lưu?

*Lời giải:* **`S1(x)=sum(D[0:x])`** và **`S2(x)=sum(i*D[i],i<x)`**.

**Bài 5 — Công thức cốt lõi.** Viết `P(x)` theo hai tổng Fenwick.

*Lời giải:* **`P(x)=x*S1(x)-S2(x)`**.

**Bài 6 — Cập nhật đoạn.** Với `[l,r)=[1,4)` và `delta=3`, hai mốc D nào thay đổi?

*Lời giải:* **`D[1]+=3`**, **`D[4]-=3`**.

**Bài 7 — Mốc trọng số.** Với l=1, r=4, delta=3, hai mốc W nào thay đổi?

*Lời giải:* **`W[1]+=3`**, **`W[4]-=12`**.

**Bài 8 — Kết quả sau cập nhật.** Với mảng bài 1, sau cộng `+3` vào `[1,4)` mảng là gì?

*Lời giải:* **`[2,8,4,7,3]`**.

**Bài 9 — Tổng đoạn.** Với mảng ở bài 8, tổng `[1,4)` bằng bao nhiêu?

*Lời giải:* **19**, bằng `8+4+7`.

**Bài 10 — Kiểm tra công thức.** Sau bài 8, `sum(D[0:5])=3` và `sum(W[0:5])=-9`. Tổng toàn mảng?

*Lời giải:* `P(5)=5*3-(-9)=24`.

**Bài 11 — Cập nhật chạm n.** Với n=5, l=2, r=5, delta=-2, có cập nhật mốc D[5] trong hai BIT không?

*Lời giải:* **Không**. Chỉ cập nhật `D[2]-=2` và `W[2]-=4`; mốc ở n ngoài miền thật.

**Bài 12 — Nhiều cập nhật.** Từ `[2,8,4,7,3]`, cộng `-2` vào `[2,5)` được mảng nào?

*Lời giải:* **`[2,8,2,5,1]`**.

**Bài 13 — Mốc ở đầu mảng.** Nếu cộng `+1` vào `[0,2)`, thay đổi của W[0] bằng bao nhiêu?

*Lời giải:* `0*1=0`. **B1 vẫn phải cập nhật mốc D[0]**, dù B2 không đổi tại 0.

**Bài 14 — Phân biệt hiệu và tổng.** Với D=[2,3,-4,3,-1], `sum(D)` bằng mấy? Có phải tổng a không?

*Lời giải:* `sum(D)=3`, **không** phải tổng a là 15.

**Bài 15 — Tổng đoạn qua tiền tố.** `range_sum(2,5)` được viết bằng hai tiền tố nào?

*Lời giải:* **`P(5)-P(2)`**.

**Bài 16 — Đoạn rỗng.** `range_add(3,3,100)` có thay dữ liệu không? `range_sum(3,3)` bằng gì?

*Lời giải:* **Không thay gì**; tổng là **0**.

**Bài 17 — Mảng rỗng.** Với n=0, có hợp lệ khi cập nhật `[0,0)` và hỏi tổng `[0,0)` không?

*Lời giải:* **Có**, cập nhật là no-op, tổng **0**.

**Bài 18 — Đoạn đóng 1-based.** Đề bài cộng vào `[L=2,R=4]` đánh số từ 1. Đổi thành đoạn ngoài 0-based nào?

*Lời giải:* **`[1,4)`**.

**Bài 19 — Trọng số 1-based.** Nếu dùng sai phân `d[i]` 1-based, BIT thứ hai lưu trọng số gì để `P(x)=x*S1(x)-S2(x)`?

*Lời giải:* **`(i-1)*d[i]`**.

**Bài 20 — Vì sao trọng số i?** Trong `P(x)`, mốc D[i] xuất hiện bao nhiêu lần?

*Lời giải:* **`x-i` lần** với `i<x`. Vì vậy `P(x)=Σ(x-i)D[i]`.

**Bài 21 — Chi phí cập nhật.** Mỗi `range_add` thay đổi nhiều nhất bao nhiêu điểm Fenwick ở hai cây, và mất thời gian nào?

*Lời giải:* Tối đa **4 cập nhật điểm**, mỗi lần O(log n), nên cả lệnh **O(log n)**.

**Bài 22 — Chi phí truy vấn.** Mỗi `range_sum` cần tính những tiền tố nào và có tổng thời gian nào?

*Lời giải:* Tính **`P(r)` và `P(l)`**. Mỗi P dùng hai truy vấn BIT, tổng vẫn **O(log n)**.

**Bài 23 — Bộ nhớ.** Hai Fenwick và dữ liệu tạm từ n phần tử dùng bao nhiêu bộ nhớ?

*Lời giải:* **O(n)**; nhân đôi số cây không biến bậc tuyến tính thành O(n²).

**Bài 24 — Gán điểm.** Với `a[pos]=5`, muốn gán thành 12 cần gọi update với delta nào?

*Lời giải:* `12-5=7` trên đoạn **`[pos,pos+1)`**.

**Bài 25 — Gán cả đoạn.** Vì sao `range_add(l,r,7)` không tương đương gán mọi phần tử trong đoạn bằng 7?

*Lời giải:* Vì nó **tăng 7 so với giá trị cũ**, không ghi đè giá trị cũ.

**Bài 26 — Tính đúng khi số âm.** Nếu mảng có tổng tiền tố không đơn điệu, hai BIT còn trả tổng đoạn đúng không?

*Lời giải:* **Có**, vì công thức dựa trên đại số cộng/trừ, không dựa vào điều kiện tiền tố không giảm.

**Bài 27 — Xây dựng.** Xây hai BIT từ mảng đã biết toàn bộ trong thời gian nào nếu dùng lan truyền tuyến tính?

*Lời giải:* **O(n)** thời gian và O(n) bộ nhớ.

**Bài 28 — Khôi phục mảng.** Nếu hỏi n lần `point_get` thì chi phí là gì? Có cách nào tốt hơn?

*Lời giải:* **O(n log n)**. Có thể **đảo phép lan truyền Fenwick trong O(n)** để lấy D, rồi cộng dồn O(n).

**Bài 29 — Oracle.** Nêu một bất biến có thể dùng kiểm thử sau mỗi cập nhật.

*Lời giải:* Với mọi i, hai cây phải biểu diễn đúng **`D[i]=a[i]-a[i-1]`** và **`W[i]=i*D[i]`**; có thể khôi phục điểm của từng cây rồi so với mảng trực tiếp.

**Bài 30 — Đổi thuật toán.** Nếu có q lần cộng đoạn nhưng chỉ cần toàn bộ mảng sau cùng một lần, cấu trúc nào thường đơn giản hơn?

*Lời giải:* **Mảng hiệu theo lô**, ghi O(1) mỗi lần, dựng O(n), tổng O(n+q).

**Bài 31 — Tràn trung gian.** Vì sao tích `index*delta` cần được xét giới hạn kiểu số trong ngôn ngữ số cố định?

*Lời giải:* Tích có thể **lớn hơn các giá trị phần tử và kết quả cuối**, nên có nguy cơ tràn trước khi các số hạng triệt tiêu.

**Bài 32 — Cận tổng thể.** Với n phần tử, u cập nhật đoạn và q truy vấn tổng đoạn, thời gian của hai Fenwick là gì?

*Lời giải:* **O(n+(u+q)log n)** nếu xây tuyến tính và phép số học O(1).

## 34. Tổng kết

Để hỗ trợ **cộng cả đoạn và hỏi tổng cả đoạn trực tuyến** bằng Fenwick, ta không lưu trực tiếp mảng gốc trong một BIT duy nhất. Thay vào đó:

1. Tạo **mảng hiệu** `D[0]=a[0]`, `D[i]=a[i]-a[i-1]`.
2. Tạo **mảng hiệu có trọng số** `W[i]=i*D[i]` với chỉ số **0-based**.
3. Dùng `BIT1` lưu D và `BIT2` lưu W.
4. Cập nhật đoạn `[l,r)` bằng hai mốc đối nhau trong cả hai BIT.
5. Tính tổng tiền tố và tổng đoạn bằng:

```text
S1(x) = BIT1.prefix(x)
S2(x) = BIT2.prefix(x)

P(x) = x*S1(x) - S2(x)

range_sum(l,r) = P(r) - P(l)
```

Với một cập nhật không rỗng `[l,r)`:

```text
BIT1.add(l, +delta)
BIT2.add(l, +l*delta)

if r < n:
    BIT1.add(r, -delta)
    BIT2.add(r, -r*delta)
```

Mỗi cập nhật có tối đa bốn lần sửa điểm Fenwick, mỗi truy vấn tổng đoạn có một số cố định lần lấy tiền tố Fenwick, nên cả **cộng đoạn** và **tổng đoạn** đều mất **O(log n)** sau khi xây tuyến tính **O(n)**, với bộ nhớ **O(n)**.

Điều kiện quan trọng là **giữ nhất quán quy ước biên và trọng số**: đoạn ngoài là `[l,r)`, BIT nội bộ 1-based, nhưng trọng số `i*D[i]` dùng **chỉ số mốc ngoài 0-based**; mốc ở r=n được bỏ qua. Cấu trúc hoạt động với cả số âm. Nó không tự hỗ trợ gán cả đoạn hoặc mọi phép cập nhật khác; trong các trường hợp ấy, cần phân tích lại bất biến và chọn cấu trúc phù hợp.

Hiểu được vì sao `P(x)=x*S1(x)-S2(x)` sẽ giúp bạn **suy ra**, kiểm chứng và mở rộng Fenwick theo loại thao tác, thay vì ghi nhớ máy móc bốn lệnh cập nhật mốc.

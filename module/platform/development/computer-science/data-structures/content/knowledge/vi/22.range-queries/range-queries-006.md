# Bảng thưa (sparse table) cho dữ liệu tĩnh

Giả sử ta có một dãy nhiệt độ đã ghi nhận, không thay đổi sau khi thu thập. Hệ thống phải trả lời hàng trăm nghìn câu hỏi như: **“Nhiệt độ thấp nhất trong các mẫu từ vị trí 120 đến 800 là bao nhiêu?”** Nếu mỗi truy vấn lại duyệt toàn bộ đoạn, ta sẽ lặp lại rất nhiều phép so sánh trên cùng dữ liệu.

**Bảng thưa** (*sparse table*) tận dụng giả định **dữ liệu tĩnh** để tính trước kết quả cho tất cả các đoạn có độ dài là **lũy thừa của 2**: 1, 2, 4, 8, 16, ... Từ những đoạn đã chuẩn bị, ta có thể trả lời truy vấn **min, max và một số phép gộp lũy đẳng khác chỉ bằng hai ô bảng**, không phải đi qua từng phần tử.

Với `n` phần tử, sparse table thông thường cho **range minimum query** (RMQ) có:

- **Xây dựng:** O(n log n) thời gian.
- **Bộ nhớ:** O(n log n).
- **Mỗi truy vấn trên đoạn không rỗng:** O(1) thời gian với phép so sánh O(1).
- **Cập nhật:** không được hỗ trợ hiệu quả trong phiên bản tĩnh; cách đơn giản là xây lại bảng.

Lợi ích O(1) đến từ một tính chất không phải phép gộp nào cũng có: **tính lũy đẳng** (`x ⊕ x = x`). Vì vậy, ta cần hiểu điều kiện đại số trước khi dùng công thức hai khối chồng lấn.

Bài thuộc chương **Truy vấn đoạn** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, trong lộ trình học cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị. Trọng tâm xuyên suốt là **bất biến, thao tác, độ phức tạp thời gian/bộ nhớ** để lựa chọn cấu trúc phù hợp với từng bài toán.

## 1. Phát biểu bài toán RMQ và quy ước biên

Cho dãy:

```text
a = [a[0], a[1], ..., a[n-1]]
```

Truy vấn RMQ yêu cầu:

```text
range_min(l,r) = min(a[l], a[l+1], ..., a[r-1])
```

Trong bài này ta thống nhất **0-based và đoạn nửa mở `[l,r)`**:

```text
0 <= l <= r <= n
```

- Lấy đầu trái `l` nhưng **không** lấy đầu phải `r`.
- Đoạn có độ dài `r-l`.
- `[0,n)` là cả mảng; `r=n` hoàn toàn hợp lệ.
- `[l,l)` là đoạn rỗng. Với giao diện RMQ ở đây, ta **báo lỗi** khi hỏi min/max trên đoạn rỗng vì không có phần tử nào để trả về.

Một ví dụ xuyên suốt:

```text
Chỉ số:   0   1   2   3   4   5   6   7
Giá trị:  5   2   6   3   1   7   4   8

a = [5, 2, 6, 3, 1, 7, 4, 8]
```

Các truy vấn:

| Đoạn | Phần tử được xét | Min | Max |
|---|---|---:|---:|
| `[0,4)` | 5,2,6,3 | 2 | 6 |
| `[1,7)` | 2,6,3,1,7,4 | 1 | 7 |
| `[2,4)` | 6,3 | 3 | 6 |
| `[4,5)` | 1 | 1 | 1 |
| `[0,8)` | Cả mảng | 1 | 8 |

Nếu đề bài dùng **1-based đóng `[L,R]`** thì quy đổi thành:

```text
[L,R] 1-based  ->  [L-1,R) 0-based

Điều kiện: 1 <= L <= R <= n
```

Ví dụ `[2,7]` 1-based chính là `[1,7)` 0-based; không được tự cộng thêm một lần nữa vào biên phải.

## 2. Vì sao đọc từng phần tử có thể tốn kém?

Cách trực tiếp trả min:

```python
def range_min_scan(a, l, r):
    if not 0 <= l < r <= len(a):
        raise IndexError("Cần một đoạn không rỗng, hợp lệ")
    answer = a[l]
    for i in range(l + 1, r):
        answer = min(answer, a[i])
    return answer


a = [5, 2, 6, 3, 1, 7, 4, 8]
assert range_min_scan(a, 1, 7) == 1
```

Một truy vấn dài `k=r-l` mất **O(k)** thời gian và chỉ O(1) bộ nhớ điều khiển. Với `q` truy vấn đều dài gần `n`, chi phí có thể là **O(qn)**.

Nếu dữ liệu không đổi, ta có thể xử lý một lần để tránh lặp lại những phép so sánh. Sparse table chọn cách **lưu kết quả những đoạn có độ dài 2^k**. Những đoạn ấy vừa đủ để dựng nhanh kết quả cho các độ dài bất kỳ.

### Dữ liệu phải tĩnh nghĩa là gì?

Dữ liệu `a` được giữ nguyên từ sau lúc xây bảng cho đến lúc hoàn thành các truy vấn dùng bảng đó.

Ví dụ, nếu sau khi xây ta đổi `a[4]` từ 1 thành 100, các kết quả đã lưu cho nhiều đoạn chứa vị trí 4 sẽ **không còn đúng**. Sparse table cơ bản không tự sửa các ô bảng khi mảng thay đổi.

## 3. Hai tính chất làm nền tảng: kết hợp và lũy đẳng

Gọi `⊕` là một phép gộp hai giá trị.

**Tính kết hợp** (*associativity*) là:

```text
(x ⊕ y) ⊕ z = x ⊕ (y ⊕ z)
```

Tính này cho phép đổi cách **đặt ngoặc** khi tính kết quả trên một đoạn, chẳng hạn gộp hai nửa để tạo thành một đoạn dài hơn.

**Tính lũy đẳng** (*idempotence*) là:

```text
x ⊕ x = x
```

Tính này cho phép gộp một **kết quả đã có** với chính nó mà không làm thay đổi kết quả.

Các ví dụ:

| Phép gộp | Kết hợp? | Lũy đẳng? | Có dùng truy vấn hai khối chồng lấn? |
|---|---|---|---|
| `min` trên số so sánh được | Có | **Có** | **Có** |
| `max` | Có | **Có** | **Có** |
| `gcd` trên số nguyên không âm | Có | **Có** | **Có** |
| AND bit trên số nguyên/bit-vector | Có | **Có** | **Có** |
| OR bit | Có | **Có** | **Có** |
| Cộng số nguyên | Có | **Không** | **Không** |
| XOR bit | Có | **Không** | **Không** |
| Nối chuỗi | Có | **Không** | **Không** |
| Trừ số | **Không** | Không tổng quát | **Không** |

Tính **giao hoán** là `x⊕y=y⊕x`, khác với cả hai tính chất trên. Ví dụ ghép chuỗi kết hợp nhưng không giao hoán. Đối với thuật toán gộp những đoạn liên tiếp, cần giữ đúng thứ tự **trái trước phải**.

### Cẩn thận với GCD của số âm

Theo quy ước thông thường, `gcd(-6,-6)=6` chứ không phải `-6`. Do đó, khi nói GCD lũy đẳng theo dạng `gcd(x,x)=x`, ta chọn **miền số nguyên không âm**, hoặc chuẩn hóa mỗi đầu vào thành trị tuyệt đối trước khi xây bảng.

### Có cần phần tử đơn vị?

Đối với phép min, `+∞` có thể đóng vai trò đơn vị trong miền số mở rộng, vì `min(+∞,x)=x`. Tuy nhiên, **truy vấn sparse table hai khối ở bài này chỉ nhận đoạn không rỗng**, nên không cần dùng đơn vị trong phương thức query.

Điều này không mâu thuẫn với segment tree thường có phần tử đơn vị cho nhánh rỗng. Hai cấu trúc có **giao diện và cách ghép** khác nhau.

## 4. Định nghĩa bảng st[k][i]

Ta lưu:

```text
st[k][i] = kết quả gộp đoạn [i, i+2^k)
```

Nói cách khác, ô `st[k][i]` mô tả **2^k phần tử liên tiếp bắt đầu tại vị trí i**.

Với min:

```text
st[k][i] = min(a[i], ..., a[i+2^k-1])
```

Các độ dài theo từng hàng:

| Hàng k | Độ dài đoạn | Diễn giải |
|---:|---:|---|
| 0 | 1 | Một phần tử |
| 1 | 2 | Hai phần tử liên tiếp |
| 2 | 4 | Bốn phần tử liên tiếp |
| 3 | 8 | Tám phần tử liên tiếp |
| 4 | 16 | Mười sáu phần tử liên tiếp |

**Không phải mọi hàng đều tồn tại.** Nếu `2^k > n` thì không có đoạn độ dài ấy trong mảng, nên không cần xây hàng k.

### Những vị trí bắt đầu hợp lệ của hàng k

Đoạn `[i,i+2^k)` phải nằm trong mảng:

```text
0 <= i
i + 2^k <= n

=> 0 <= i <= n - 2^k
```

Vì vậy, số ô hợp lệ của hàng k là:

```text
n - 2^k + 1
```

Ví dụ `n=8`:

- Hàng 0 dài 1 có 8 ô.
- Hàng 1 dài 2 có 7 ô.
- Hàng 2 dài 4 có 5 ô.
- Hàng 3 dài 8 có 1 ô.

Không nên tự đọc `st[2][5]` với `n=8`, vì nó sẽ biểu thị `[5,9)`, vượt cuối mảng.

## 5. Công thức xây bảng từ hai nửa

Hàng 0 là chính các phần tử gốc:

```text
st[0][i] = a[i]
```

Một đoạn độ dài `2^k` gồm **hai nửa liền nhau**, mỗi nửa dài `2^(k-1)`:

```text
[i, i+2^k)
        =
[i, i+2^(k-1))
        ghép với
[i+2^(k-1), i+2^k)
```

Do đó:

```text
st[k][i] = st[k-1][i] ⊕ st[k-1][i+2^(k-1)]
```

Với RMQ:

```text
st[k][i] = min(
    st[k-1][i],
    st[k-1][i + 2^(k-1)]
)
```

**Hai nửa trong bước xây không chồng lấn.** Chỉ cần phép toán **kết hợp** để gộp chúng. Tính **lũy đẳng** trở nên quan trọng ở cách **truy vấn hai khối có thể chồng lấn** sau này.

### Minh họa từ đoạn độ dài 4

```text
st[2][1] quản lý [1,5), gồm a[1],a[2],a[3],a[4].

            [1,5)        (độ dài 4)
           /     \
       [1,3)    [3,5)    (mỗi đoạn dài 2)
       /   \      /  \
    [1,2)[2,3) [3,4)[4,5)
```

Ta đã tính hai đoạn `[1,3)` và `[3,5)` ở hàng 1, nên hàng 2 chỉ cần một lần gộp.

## 6. Xây bảng min bằng tay

Dùng mảng:

```text
a = [5, 2, 6, 3, 1, 7, 4, 8]
n = 8
```

### Hàng k=0: đoạn dài 1

```text
st[0] = [5, 2, 6, 3, 1, 7, 4, 8]
```

### Hàng k=1: đoạn dài 2

```text
st[1][0] = min(5,2) = 2
st[1][1] = min(2,6) = 2
st[1][2] = min(6,3) = 3
st[1][3] = min(3,1) = 1
st[1][4] = min(1,7) = 1
st[1][5] = min(7,4) = 4
st[1][6] = min(4,8) = 4

st[1] = [2, 2, 3, 1, 1, 4, 4]
```

### Hàng k=2: đoạn dài 4

```text
st[2][0] = min(st[1][0], st[1][2]) = min(2,3) = 2
st[2][1] = min(st[1][1], st[1][3]) = min(2,1) = 1
st[2][2] = min(st[1][2], st[1][4]) = min(3,1) = 1
st[2][3] = min(st[1][3], st[1][5]) = min(1,4) = 1
st[2][4] = min(st[1][4], st[1][6]) = min(1,4) = 1

st[2] = [2, 1, 1, 1, 1]
```

### Hàng k=3: đoạn dài 8

```text
st[3][0] = min(st[2][0], st[2][4]) = min(2,1) = 1

st[3] = [1]
```

Toàn bộ bảng:

| Hàng | Độ dài | Các ô `st[k][i]` hợp lệ |
|---:|---:|---|
| 0 | 1 | `[5,2,6,3,1,7,4,8]` |
| 1 | 2 | `[2,2,3,1,1,4,4]` |
| 2 | 4 | `[2,1,1,1,1]` |
| 3 | 8 | `[1]` |

Ta đã trả chi phí tính trước những kết quả ấy, để mỗi truy vấn tiếp theo không cần duyệt đoạn gốc.

## 7. Trả lời RMQ bằng hai khối phủ đoạn

Cho truy vấn không rỗng `[l,r)`. Đặt:

```text
length = r-l
k = floor(log2(length))
s = 2^k
```

Chọn hai khối có **cùng độ dài s**:

```text
Khối trái:  [l, l+s)
Khối phải:  [r-s, r)
```

Do `s <= length < 2s`, hai khối này **phủ toàn bộ đoạn `[l,r)`**, và chúng có thể chồng lấn.

Kết quả:

```text
range_min(l,r)
    = min(st[k][l], st[k][r-s])
```

Tại sao có thể đếm một số phần tử hai lần? Vì với min:

```text
min(x,x) = x
```

Sự xuất hiện lặp lại **không làm kết quả đổi**. Đây là tính lũy đẳng.

### Ví dụ đoạn dài 6: [1,7)

```text
a = [5, 2, 6, 3, 1, 7, 4, 8]

[l,r) = [1,7)
length = 6
k = floor(log2(6)) = 2
s = 2^2 = 4

Khối trái: [1,5) -> [2,6,3,1] -> st[2][1] = 1
Khối phải: [3,7) -> [3,1,7,4] -> st[2][3] = 1

Vùng chồng lấn: [3,5) -> [3,1]

Đáp án: min(1,1) = 1
```

Sơ đồ phủ:

```text
Vị trí:         1   2   3   4   5   6
Giá trị:        2   6   3   1   7   4
Khối trái:      └───────────┘
Khối phải:              └───────────┘
Giao:                   3   4
```

Hai khối có thể trùng nhau một phần hoặc **trùng hoàn toàn** (nếu độ dài truy vấn đúng bằng `2^k`). Cả hai trường hợp đều đúng với phép lũy đẳng.

## 8. Cách tính k nhanh mà không dùng log số thực

Trong Python, với `length` là số nguyên dương:

```python
k = length.bit_length() - 1
```

Giá trị này bằng `floor(log2(length))`.

Ví dụ:

| `length` | `bit_length()` | `k` | `s=2^k` |
|---:|---:|---:|---:|
| 1 | 1 | 0 | 1 |
| 2 | 2 | 1 | 2 |
| 3 | 2 | 1 | 2 |
| 4 | 3 | 2 | 4 |
| 6 | 3 | 2 | 4 |
| 7 | 3 | 2 | 4 |
| 8 | 4 | 3 | 8 |
| 9 | 4 | 3 | 8 |

**Không được tính log của 0**. Vì vậy mã truy vấn phải kiểm tra `l<r` trước khi tính `k`.

Với `n` và độ dài chỉ số cỡ máy thông thường, thao tác này được coi O(1). Nếu làm việc với các số nguyên có hàng triệu bit, chi phí thao tác bit cũng phụ thuộc độ dài biểu diễn; phân tích O(1) của truy vấn hiểu theo mô hình RAM quen thuộc.

### Một cách khác: xây bảng floor-log

Có thể tiền xử lý:

```text
lg[1] = 0
lg[i] = lg[i//2] + 1      với i >= 2
```

Khi đó `k=lg[r-l]` trong O(1). Bảng log dài `n+1` có thể xây O(n), nhưng với Python, `bit_length` thường đơn giản hơn và không cần bộ nhớ phụ.

```python
def build_floor_log2(n):
    if type(n) is not int or n < 0:
        raise ValueError("n phải là số nguyên không âm")

    log2 = [0] * (n + 1)
    for length in range(2, n + 1):
        log2[length] = log2[length // 2] + 1

    return log2


assert build_floor_log2(8) == [0, 0, 1, 1, 2, 2, 2, 2, 3]
```

Giá trị `lg[0]=0` ở đây **chỉ là ô đệm**, không phải log2(0).

## 9. Python: sparse table cho min/max/GCD

Ta triển khai một lớp tổng quát cho **phép gộp vừa kết hợp vừa lũy đẳng**. Tính chất ấy là **hợp đồng của người gọi**; Python không thể tự chứng minh một callback tùy ý luôn thỏa.

```python
from math import gcd


def validate_half_open(n, l, r):
    """Đoạn [l,r), kể cả rỗng, nhưng không chấp nhận biên sai."""
    if type(l) is not int or type(r) is not int:
        raise TypeError("l và r phải là số nguyên")

    if not 0 <= l <= r <= n:
        raise IndexError("Đoạn [l,r) nằm ngoài miền hợp lệ")


class IdempotentSparseTable:
    def __init__(self, values, combine):
        self.n = len(values)
        self.combine = combine
        self.table = []

        if self.n == 0:
            return

        # Hàng 0: mỗi đoạn có đúng một phần tử.
        self.table.append(tuple(values))
        k = 1

        while (1 << k) <= self.n:
            half = 1 << (k - 1)
            width = 1 << k
            previous = self.table[k - 1]

            row = tuple(
                combine(previous[i], previous[i + half])
                for i in range(self.n - width + 1)
            )
            self.table.append(row)
            k += 1

    def query(self, l, r):
        validate_half_open(self.n, l, r)
        if l == r:
            raise ValueError("Truy vấn yêu cầu đoạn không rỗng")

        k = (r - l).bit_length() - 1
        width = 1 << k

        return self.combine(
            self.table[k][l],
            self.table[k][r - width],
        )


values = [5, 2, 6, 3, 1, 7, 4, 8]
rmq_min = IdempotentSparseTable(values, min)
rmq_max = IdempotentSparseTable(values, max)

assert rmq_min.table[0] == (5, 2, 6, 3, 1, 7, 4, 8)
assert rmq_min.table[1] == (2, 2, 3, 1, 1, 4, 4)
assert rmq_min.table[2] == (2, 1, 1, 1, 1)
assert rmq_min.table[3] == (1,)

assert rmq_min.query(1, 7) == 1
assert rmq_min.query(2, 4) == 3
assert rmq_min.query(4, 5) == 1
assert rmq_min.query(0, 8) == 1

assert rmq_max.query(1, 7) == 7
assert rmq_max.query(0, 8) == 8

gcd_data = [12, 18, 6, 9, 15]
rmq_gcd = IdempotentSparseTable(gcd_data, gcd)

assert rmq_gcd.query(1, 4) == 3
assert rmq_gcd.query(0, 5) == 3
```

**Lưu ý:** ví dụ GCD dùng số nguyên không âm để bảo đảm phép gộp lũy đẳng trên miền đầu vào. Nếu nhận số nguyên âm, có thể chuẩn hóa `abs(x)` trước khi xây.

### Xử lý mảng rỗng, một phần tử và đoạn rỗng

```python
empty = IdempotentSparseTable([], min)

assert empty.table == []

try:
    empty.query(0, 0)
except ValueError:
    pass
else:
    raise AssertionError("Min đoạn rỗng phải báo lỗi")

single = IdempotentSparseTable([42], min)

assert single.query(0, 1) == 42
assert len(single.table) == 1

try:
    single.query(1, 0)
except IndexError:
    pass
else:
    raise AssertionError("Biên đảo phải báo lỗi")
```

Mảng rỗng là đầu vào hợp lệ để **xây** một bảng trống; chỉ là không có truy vấn **không rỗng** nào hợp lệ.

### Kiểm tra biên nghiêm ngặt

```python
for l, r in [(-1, 3), (2, 9), (5, 2)]:
    try:
        rmq_min.query(l, r)
    except IndexError:
        pass
    else:
        raise AssertionError("Phải từ chối biên không hợp lệ")

try:
    rmq_min.query(True, 4)
except TypeError:
    pass
else:
    raise AssertionError("Không chấp nhận Boolean làm chỉ số")
```

Python cho phép chỉ số âm ở nhiều thao tác với list, nhưng một API truy vấn đoạn dựa trên `0<=l<=r<=n` không nên âm thầm chấp nhận chúng.

## 10. Chứng minh đúng bước tiền xử lý

Ta chứng minh bất biến:

> `st[k][i]` là giá trị gộp đúng của đoạn `[i,i+2^k)`, với mọi ô bảng hợp lệ.

### Cơ sở k=0

```text
st[0][i] = a[i]
```

Đoạn `[i,i+1)` chỉ chứa `a[i]`, nên bất biến đúng.

### Bước quy nạp

Giả sử ở hàng `k-1`, mọi ô đều là kết quả đúng của đoạn dài `2^(k-1)`.

Đoạn `[i,i+2^k)` tách thành:

```text
Trái: [i, i+2^(k-1))
Phải: [i+2^(k-1), i+2^k)
```

Hai đoạn **kề nhau, không chồng lấn**, và hợp lại chính là đoạn cần lưu. Vì phép `⊕` kết hợp, ta có:

```text
Q(i,i+2^k)
  = Q(i,i+2^(k-1))
      ⊕ Q(i+2^(k-1),i+2^k)
  = st[k-1][i]
      ⊕ st[k-1][i+2^(k-1)]
  = st[k][i]
```

Do đó bất biến đúng ở hàng k.

### Biên của bảng luôn hợp lệ

Với ô `st[k][i]`, ta chỉ xây khi `0<=i<=n-2^k`. Khi đó cả hai ô ở hàng trước đều tồn tại:

```text
i <= n - 2^k < n - 2^(k-1) + 1
i + 2^(k-1) <= n - 2^(k-1)
```

Nên công thức không đọc vượt các hàng đã xây.

## 11. Chứng minh đúng công thức truy vấn hai khối

Cho đoạn không rỗng `[l,r)` với:

```text
length = r-l
s = 2^floor(log2(length))
```

Khi đó:

```text
s <= length < 2s
```

Hai đoạn được chọn:

```text
A = [l, l+s)
B = [r-s, r)
```

đều dài s và nằm trong `[l,r)`. Vì `length<2s`, chúng **chồng lấn hoặc trùng nhau**, và hợp lại phủ toàn bộ truy vấn.

### Phân tích phần chồng lấn

Viết đoạn truy vấn theo thứ tự:

```text
X | Y | Z

X = phần chỉ thuộc A
Y = phần giao giữa A và B
Z = phần chỉ thuộc B
```

Nếu X hoặc Z rỗng, cứ hiểu các phần tương ứng được bỏ khỏi phép gộp. Khi chúng tồn tại:

```text
Q(A) = Q(X) ⊕ Q(Y)
Q(B) = Q(Y) ⊕ Q(Z)
```

Gộp hai kết quả:

```text
Q(A) ⊕ Q(B)
= Q(X) ⊕ Q(Y) ⊕ Q(Y) ⊕ Q(Z)
= Q(X) ⊕ Q(Y) ⊕ Q(Z)
= Q(l,r)
```

Bước giữa dùng tính **lũy đẳng**:

```text
Q(Y) ⊕ Q(Y) = Q(Y)
```

Các bước đổi ngoặc dùng tính **kết hợp**.

Nếu hai khối trùng hoàn toàn, `Q(A)=Q(B)` và kết quả vẫn đúng nhờ lũy đẳng. Không cần giả định hai khối tách rời.

**Kết luận:** công thức hai khối đúng cho phép gộp **kết hợp và lũy đẳng** trong cách lưu/ghép có thứ tự như trên. Không được áp dụng nó một cách máy móc cho tổng, tích, XOR hoặc ghép chuỗi.

## 12. Phản ví dụ: phép cộng không lũy đẳng

Vẫn dùng:

```text
a = [5, 2, 6, 3, 1, 7, 4, 8]
Truy vấn [1,7) gồm 2,6,3,1,7,4
```

Tổng thật:

```text
2 + 6 + 3 + 1 + 7 + 4 = 23
```

Hai khối theo công thức sparse table:

```text
Khối trái  [1,5): 2+6+3+1 = 12
Khối phải  [3,7): 3+1+7+4 = 15

12 + 15 = 27             (SAI)
```

Vùng giao `[3,5)` có các phần tử `3,1`, bị cộng **hai lần**, khiến tổng dư `4`.

Nguyên nhân:

```text
x+x != x                với tổng thông thường
```

Tương tự, XOR vùng giao hai lần sẽ **triệt tiêu** vùng ấy thay vì chỉ giữ một lần. Ghép chuỗi hai khối chồng lấn làm lặp lại các ký tự trong vùng chung.

### Không phải vì bảng thưa không thể lưu tổng

Công thức **xây** `st[k][i]=st[k-1][i]⊕st[k-1][i+half]` vẫn đúng với phép cộng, vì hai nửa **không chồng lấn**.

Chỉ **công thức truy vấn bằng hai khối có thể chồng lấn** là không hợp lệ với tổng.

Để hỏi tổng từ bảng ấy, ta phải gộp các **khối không chồng lấn**, hoặc chọn cấu trúc khác như **prefix sum**.

## 13. Truy vấn phép kết hợp bằng các khối không chồng lấn

Với một phép chỉ có **tính kết hợp**, ta có thể phân rã đoạn cần hỏi thành các đoạn dài lũy thừa của 2, **không chồng lấn** và theo đúng thứ tự trái–phải.

Ví dụ `[1,7)` dài 6:

```text
6 = 4 + 2

[1,7) = [1,5) ghép [5,7)
```

Ta tính:

```text
Q(1,7) = st[2][1] ⊕ st[1][5]
```

Với tổng:

```text
st[2][1] = 2+6+3+1 = 12
st[1][5] = 7+4 = 11

12+11 = 23               (ĐÚNG)
```

Một độ dài có thể được biểu diễn bằng tổng những lũy thừa của 2 từ các bit 1 trong biểu diễn nhị phân. Vì thế có nhiều nhất `O(log n)` khối không chồng lấn.

### Giả mã

```text
QUERY_DISJOINT(l,r):
    kiểm tra 0 <= l < r <= n
    result = chưa có giá trị
    position = l
    remaining = r-l

    while remaining > 0:
        k = floor(log2(remaining))
        width = 2^k

        block = st[k][position]
        gộp block vào result theo thứ tự trái -> phải

        position += width
        remaining -= width

    return result
```

Nếu phép gộp không có đơn vị thuận tiện hoặc API cấm đoạn rỗng, ta có thể khởi tạo `result` từ **khối đầu tiên**. Cách này không cần phát minh đơn vị giả.

**Độ phức tạp:** O(log n) lần gộp cho một truy vấn, với phép gộp O(1). Tính chất lũy đẳng **không cần thiết** vì các đoạn không chồng lấn.

## 14. Python: sparse table cho phép kết hợp tổng quát

Để không nhầm lẫn về hợp đồng, ta tạo một lớp riêng có **truy vấn các khối rời**, chấp nhận phép gộp **kết hợp** dù không lũy đẳng.

```python
class AssociativeSparseTable:
    def __init__(self, values, combine):
        self.n = len(values)
        self.combine = combine
        self.table = []

        if self.n == 0:
            return

        self.table.append(tuple(values))
        k = 1

        while (1 << k) <= self.n:
            half = 1 << (k - 1)
            width = 1 << k
            previous = self.table[k - 1]

            row = tuple(
                combine(previous[i], previous[i + half])
                for i in range(self.n - width + 1)
            )
            self.table.append(row)
            k += 1

    def query(self, l, r):
        validate_half_open(self.n, l, r)
        if l == r:
            raise ValueError("Truy vấn cần đoạn không rỗng")

        answer = None
        has_answer = False
        position = l
        remaining = r - l

        while remaining > 0:
            k = remaining.bit_length() - 1
            width = 1 << k
            block_value = self.table[k][position]

            if has_answer:
                answer = self.combine(answer, block_value)
            else:
                answer = block_value
                has_answer = True

            position += width
            remaining -= width

        return answer


a = [5, 2, 6, 3, 1, 7, 4, 8]
sum_sparse = AssociativeSparseTable(a, lambda x, y: x + y)

assert sum_sparse.query(1, 7) == 23
assert sum_sparse.query(0, 8) == 36
assert sum_sparse.query(4, 5) == 1

words = ["ab", "cd", "ef", "gh", "ij"]
join_sparse = AssociativeSparseTable(
    words, lambda x, y: x + y
)

assert join_sparse.query(1, 4) == "cdefgh"
assert join_sparse.query(0, 5) == "abcdefghij"
```

Trong ví dụ nối chuỗi, giữ thứ tự các khối là **bắt buộc**. Nối chuỗi kết hợp nhưng không giao hoán: `"cd"+"ef"` không giống `"ef"+"cd"`.

### Phân biệt chi phí gộp và chi phí byte

Khi nói O(log n) cho truy vấn, ta đang đếm **số phép gộp**. Với `int` có độ dài bit giới hạn, cộng số thường được coi O(1). Với chuỗi Python, `x+y` có thể sao chép toàn bộ ký tự, nên chi phí thực tế phụ thuộc **tổng độ dài chuỗi**, không chỉ số khối.

### Với tổng đoạn tĩnh, prefix sum thường đơn giản hơn

Nếu phép gộp là cộng trên số có phép trừ thích hợp, **prefix sum** cho:

```text
P[0]=0
P[i+1]=P[i]+a[i]

sum([l,r)) = P[r]-P[l]
```

Tiền xử lý O(n), bộ nhớ O(n), mỗi truy vấn O(1). Vì vậy không nên dùng sparse table O(n log n) chỉ để tính tổng tĩnh khi **prefix sum đã đáp ứng đầy đủ**.

## 15. Một biến thể khác: disjoint sparse table

Có một biến thể gọi là **disjoint sparse table** (*bảng thưa với các phân hoạch rời*). Với phép gộp **kết hợp**, nó tiền xử lý những bản tổng hợp tiền tố/hậu tố ở hai nửa của các khối theo nhiều mức.

Cho hai vị trí thuộc hai phía khác nhau của một lần chia khối, kết quả trên đoạn nối giữa chúng có thể lấy từ:

1. Một **hậu tố** đã lưu ở nửa trái.
2. Một **tiền tố** đã lưu ở nửa phải.

Hai phần này **không chồng lấn** nên chỉ cần tính kết hợp, không cần lũy đẳng.

Trong những biến thể disjoint sparse table thích hợp, sau **O(n log n)** tiền xử lý và bộ nhớ, truy vấn không rỗng có thể được trả lời trong **O(1)** phép gộp (với phép toán O(1)).

**Đừng nhầm hai cấu trúc:**

- Sparse table thông thường, hai khối **có thể chồng lấn**, O(1) query: cần **lũy đẳng**.
- Disjoint sparse table, dùng **hai phần rời**, O(1) query: chỉ cần **kết hợp**, nhưng bảng và cách tìm mức khác.

Bài này triển khai đầy đủ **sparse table thông thường**; disjoint sparse table được giới thiệu để người học không kết luận sai rằng “mọi phép không lũy đẳng đều không thể truy vấn O(1) với bất kỳ biến thể sparse table nào”.

## 16. Độ phức tạp xây dựng và bộ nhớ

Với `n>0`, số hàng là:

```text
K = floor(log2(n)) + 1
```

Mỗi hàng k có:

```text
n - 2^k + 1
```

ô hợp lệ.

Tổng số ô:

```text
S(n) = sum(n - 2^k + 1, k=0..floor(log2(n)))
```

Vì có O(log n) hàng, mỗi hàng có tối đa n ô:

```text
S(n) <= n * (floor(log2(n)) + 1)
     = O(n log n)
```

Bên cạnh hàng 0, mỗi ô được tính bằng **một phép gộp hai ô ở hàng trước**. Do vậy:

- **Thời gian xây:** O(n log n).
- **Bộ nhớ:** O(n log n) giá trị tóm tắt.
- **Truy vấn lũy đẳng hai khối:** O(1) phép gộp và O(1) bộ nhớ phụ.
- **Truy vấn tổng quát bằng khối rời:** O(log n) phép gộp và O(1) biến điều khiển.

Các cận này giả định `combine` tốn O(1). Với GCD trên số nguyên rất lớn, độ phức tạp tính GCD còn phụ thuộc độ dài bit; với chuỗi, phép nối thường không phải O(1).

### Bảng thưa có thật sự “thưa” không?

Tên *sparse table* là tên truyền thống của cấu trúc. Bảng này lưu nhiều đoạn, có thể đến O(n log n) giá trị; **không có nghĩa nó luôn tiết kiệm RAM hơn mảng n phần tử**.

Trong Python, mỗi ô còn có chi phí đối tượng/tham chiếu tùy kiểu giá trị và cách tổ chức tuple/list. Khi n rất lớn, bộ nhớ có thể trở thành yếu tố quyết định.

### Khi n không là lũy thừa của 2

Ví dụ `n=10`:

```text
K = floor(log2(10)) + 1 = 4

Hàng k=0, độ dài 1: 10 ô
Hàng k=1, độ dài 2:  9 ô
Hàng k=2, độ dài 4:  7 ô
Hàng k=3, độ dài 8:  3 ô
```

Không cần hàng độ dài 16. Việc chỉ lưu **các đoạn nằm trọn trong mảng** giúp tránh ô vô nghĩa và truy cập vượt biên.

## 17. Thời gian truy vấn O(1) đến từ đâu?

Một truy vấn RMQ thông thường chỉ cần:

```text
length = r-l
k = floor(log2(length))
width = 2^k

answer = min(st[k][l], st[k][r-width])
```

Các bước:

- Tính độ dài.
- Tìm k bằng `bit_length` hoặc bảng log.
- Tính `width`.
- Đọc hai ô bảng.
- Gộp một lần.

Số bước **không tăng theo độ dài đoạn**, miễn là một phép gộp và các phép tính chỉ số được coi O(1).

Tuy vậy, **O(1) mỗi query không có nghĩa toàn bộ hệ thống O(1)**: xây bảng vẫn O(n log n), và nếu giữ q đáp án thì riêng danh sách đầu ra đã O(q) bộ nhớ.

## 18. Tại sao cập nhật một điểm không còn đơn giản?

Giả sử bảng được xây từ:

```text
a = [5,2,6,3,1,7,4,8]
```

Ta đổi `a[4]` từ 1 thành 100. Khi đó:

```text
a' = [5,2,6,3,100,7,4,8]
```

Trước cập nhật:

```text
min([3,5)) = min(3,1) = 1
```

Sau cập nhật:

```text
min([3,5)) = min(3,100) = 3
```

Nhưng `st[1][3]` vẫn lưu 1 nếu không được sửa. Tương tự, những ô ở các hàng cao hơn chứa vị trí 4 cũng có thể sai.

### Hướng xử lý

- **Dữ liệu tĩnh thực sự:** xây một lần, truy vấn nhiều lần; đây là trường hợp mục tiêu.
- **Rất ít lần thay đổi:** xây một bảng mới sau mỗi đợt thay đổi, chi phí O(n log n) mỗi lần xây lại.
- **Cập nhật điểm thường xuyên:** cân nhắc segment tree với O(log n) cho min query và point update.
- **Có các cập nhật đoạn:** cân nhắc cấu trúc hỗ trợ lazy propagation hoặc thiết kế cập nhật chuyên biệt.
- **Mảng rất nhỏ:** quét trực tiếp đôi khi đơn giản và nhanh hơn chi phí tiền xử lý.

Không nên thêm một phương thức `point_assign` chỉ sửa hàng 0 rồi tiếp tục dùng các hàng còn lại: nó phá bất biến `st[k][i]` của toàn bảng.

### Có thể sửa chọn lọc ô thay vì xây lại?

Có thể xác định những đoạn đã lưu **chứa vị trí i** rồi tính lại chúng. Nhưng số ô bị ảnh hưởng có thể rất lớn; cách này không mang lại chi phí O(log n) như cập nhật trên segment tree.

Trong khóa học cơ bản, nên xem sparse table là cấu trúc **bất biến sau khi xây** và chọn cấu trúc khác khi workload động.

## 19. Snapshot dữ liệu và thao tác bên ngoài

Lớp `IdempotentSparseTable` lưu các hàng dưới dạng `tuple`. Đối với **các giá trị số hoặc chuỗi bất biến**, việc người gọi đổi vị trí của danh sách đầu vào không làm thay đổi các giá trị đã tính trong bảng.

```python
input_values = [5, 2, 6, 3, 1, 7, 4, 8]
table = IdempotentSparseTable(input_values, min)

assert table.query(1, 7) == 1

input_values[4] = 100

# Bảng vẫn mô tả snapshot trước đó, không phải mảng nguồn mới.
assert table.query(1, 7) == 1
```

Nhưng `tuple` chỉ giữ **tham chiếu phần tử**. Nếu phần tử là một đối tượng nội bộ **có thể thay đổi** và `combine` phụ thuộc trạng thái của nó, snapshot này không bảo đảm bất biến sâu. Muốn hỗ trợ dữ liệu như vậy cần đóng băng/chép sâu hợp lý hoặc quy định rõ ràng rằng các phần tử không được sửa.

Cũng không nên để callback `combine` tự sửa dữ liệu đầu vào hoặc sinh tác dụng phụ. Các chứng minh toán học giả định phép gộp xác định và nhất quán.

## 20. Trả vị trí nhỏ nhất thay vì chỉ giá trị

Một số bài toán yêu cầu không chỉ **giá trị min**, mà còn **vị trí của lần xuất hiện đầu tiên** của giá trị nhỏ nhất.

Ví dụ:

```text
a = [4,2,9,2,2,7]
          ^   ^ ^
        nhiều vị trí có giá trị 2
```

Nếu chỉ lưu min của mỗi khối, ta không thể biết **chỉ số nào** đã tạo min mà không giữ thêm thông tin.

Một cách làm là lưu cặp:

```text
(value, index)
```

và dùng thứ tự từ điển:

1. So sánh `value` trước.
2. Nếu bằng nhau, chọn `index` nhỏ hơn.

Phép `min` trên các cặp này có tính kết hợp và lũy đẳng, vì mỗi cặp giống hệt nó khi gộp lại.

### Python: argmin có quy tắc xử lý hòa

```python
def build_argmin_table(values):
    pairs = [(value, index) for index, value in enumerate(values)]
    return IdempotentSparseTable(pairs, min)


values = [4, 2, 9, 2, 2, 7]
argmin_table = build_argmin_table(values)

assert argmin_table.query(0, 6) == (2, 1)
assert argmin_table.query(2, 6) == (2, 3)
assert argmin_table.query(4, 6) == (2, 4)

value, index = argmin_table.query(1, 5)
assert value == 2
assert index == 1
```

Nếu cần chọn **lần xuất hiện cuối cùng**, có thể đổi quy tắc xử lý hòa, ví dụ lưu `(value,-index)` rồi chuyển lại chỉ số. Quan trọng là quy tắc phải **ổn định và nhất quán** trong cả lúc xây lẫn truy vấn.

### Tại sao không so sánh chỉ giá trị?

Với dữ liệu trùng nhau, trả về min đúng nhưng index sai có thể gây lỗi ở bài toán tìm vị trí hoặc áp dụng thao tác theo điểm. **Kiểu bản tóm tắt** phải chứa đủ thông tin để trả lời chính xác yêu cầu.

## 21. GCD, AND, OR và các phép gộp khác

Sparse table thông thường cho truy vấn hai khối áp dụng với bất kỳ phép `⊕` thỏa:

```text
(1) Kết hợp:     (x⊕y)⊕z = x⊕(y⊕z)
(2) Lũy đẳng:    x⊕x = x
```

Ví dụ:

### GCD trên số nguyên không âm

```text
gcd(x,x)=x
gcd(gcd(x,y),z)=gcd(x,gcd(y,z))
```

Nên có thể dựng `st` dùng `math.gcd`. Với số nguyên âm, hãy dùng trị tuyệt đối nếu muốn giữ đúng miền và thuộc tính lũy đẳng.

### AND bit

```text
x & x = x
```

Kết hợp từng bit vẫn đúng, nên hai khối chồng lấn không làm thay đổi phép AND.

### OR bit

```text
x | x = x
```

Cũng phù hợp. Chẳng hạn truy vấn xem những cờ nào đã từng được bật trong một khoảng thời gian tĩnh.

### Không phù hợp với XOR hai khối overlap

```text
x ^ x = 0
```

Hai lần xuất hiện làm một vùng bị **khử**, không phải giữ nguyên. Muốn XOR đoạn tĩnh, có thể dùng **prefix XOR**:

```text
PX[0]=0
PX[i+1]=PX[i] XOR a[i]

xor([l,r)) = PX[l] XOR PX[r]
```

Với XOR, prefix vừa có bộ nhớ O(n), vừa cho O(1) mỗi truy vấn, đơn giản hơn sparse table.

## 22. Trường hợp biên và những nhầm lẫn hay gặp

| Tình huống hoặc sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Mảng rỗng `n=0` | Không có đoạn min không rỗng | Cho phép bảng trống; query rỗng báo lỗi |
| Mảng một phần tử | Dễ tính log sai nếu dùng log2(0) | Độ dài 1 cho `k=0` |
| `l=r` | Min không được định nghĩa theo API | Kiểm tra và báo lỗi |
| `r=n` | Có thể bị từ chối sai | Hợp lệ vì `r` exclusive |
| Chỉ số âm theo Python | Có thể truy cập sai phần tử | Validate `0<=l<=r<=n` |
| Nhầm `[l,r]` với `[l,r)` | Lấy thừa hoặc thiếu phần tử | Chuẩn hóa biên |
| Dùng `log2(r-l)` với đoạn rỗng | Log không xác định | Kiểm tra rỗng trước |
| Dùng `round(log2(length))` | Chọn khối quá dài | Dùng floor, tốt nhất là `bit_length()-1` |
| Xây mọi hàng dài n ô không kiểm tra | Đọc vượt mảng | Hàng k chỉ dài `n-2^k+1` |
| Đọc `st[k][r]` thay vì `st[k][r-2^k]` | Sai biên khối phải | Điểm bắt đầu khối phải là `r-s` |
| Cho rằng hai khối không chồng lấn | Hiểu sai tính đúng | Chấp nhận overlap nhờ lũy đẳng |
| Dùng hai khối overlap để cộng tổng | Đếm trùng vùng giao | Dùng prefix hoặc khối không chồng lấn |
| Dùng hai khối overlap để XOR | Triệt tiêu vùng giao | Dùng prefix XOR |
| Cho rằng kết hợp đồng nghĩa lũy đẳng | Áp dụng nhầm công thức O(1) | Kiểm tra `op(x,x)=x` |
| Đảo thứ tự khối với phép không giao hoán | Kết quả sai | Giữ thứ tự trái–phải |
| Cập nhật dữ liệu nguồn rồi kỳ vọng bảng đổi | Bảng mô tả snapshot cũ | Rebuild hoặc cấu trúc động |
| Gán lại hàng 0 mà không cập nhật hàng khác | Bất biến của bảng bị phá | Không cập nhật theo cách ấy |
| Dùng GCD số âm như phép lũy đẳng trên ℤ | `gcd(-x,-x)=abs(x)` | Chuẩn hóa miền không âm |
| Dùng min với NaN không chính sách | Kết quả có thể phụ thuộc thứ tự | Định nghĩa rõ chính sách dữ liệu |
| Cho rằng query O(1) nghĩa tổng bộ nhớ O(1) | Bỏ qua bảng O(n log n) | Tách preprocessing và query |
| Bỏ qua chi phí `combine` | Cận O(1) không đúng cho dữ liệu lớn | Nêu rõ mô hình chi phí |
| Dùng sparse table cho cập nhật liên tục | Phải làm mới nhiều ô | Chọn segment tree hoặc cấu trúc động |

## 23. Kiểm thử đối chiếu với cách quét

Trên mảng nhỏ, ta có thể so sánh tất cả các truy vấn không rỗng với kết quả từ `min(a[l:r])`.

```python
def check_every_range(values, table, combine):
    n = len(values)

    for l in range(n):
        for r in range(l + 1, n + 1):
            expected = values[l]
            for i in range(l + 1, r):
                expected = combine(expected, values[i])
            assert table.query(l, r) == expected


samples = [
    [],
    [42],
    [5, 5, 5],
    [9, -2, 7, 0, 4],
    [5, 2, 6, 3, 1, 7, 4, 8],
]

for values in samples:
    min_table = IdempotentSparseTable(values, min)
    max_table = IdempotentSparseTable(values, max)

    check_every_range(values, min_table, min)
    check_every_range(values, max_table, max)
```

Khi `values=[]`, vòng kiểm tra không có truy vấn không rỗng nào, điều đó là hợp lệ.

### Kiểm thử phép không lũy đẳng với lớp phù hợp

```python
data = [3, -1, 5, 2, -4, 7]
sum_table = AssociativeSparseTable(
    data, lambda x, y: x + y
)

for l in range(len(data)):
    for r in range(l + 1, len(data) + 1):
        assert sum_table.query(l, r) == sum(data[l:r])
```

Dùng hai lớp khác nhau giúp bộ test **không vô tình lấy công thức overlap để kiểm thử sum**.

### Các bộ dữ liệu nên kiểm tra thêm

- `n=0`, `n=1` và n không phải lũy thừa 2.
- Mọi phần tử bằng nhau, giá trị âm, số 0, giá trị min nằm ở đầu hoặc cuối.
- Độ dài truy vấn `1,2,3,4,5,7,8,9` — đặc biệt ngay hai phía một lũy thừa 2.
- Truy vấn toàn mảng, một phần tử, đoạn có `r=n`.
- Biên âm, đảo biên, vượt n và đầu vào không phải số nguyên.
- Dữ liệu trùng giá trị khi truy vấn argmin có tie-break.

Bộ test mạnh phải kiểm tra cả **đáp án** và **hợp đồng lỗi** ở biên.

## 24. Sparse table 2D cho hình chữ nhật tĩnh

Ý tưởng còn có thể mở rộng sang ma trận `R×C` và truy vấn min trên hình chữ nhật nửa mở:

```text
[r1,r2) × [c1,c2)
```

Ta có thể lưu:

```text
st[k1][k2][i][j]
= min của hình chữ nhật bắt đầu tại (i,j)
  với chiều cao 2^k1, chiều rộng 2^k2.
```

Với một truy vấn không rỗng theo cả hai chiều, chọn lũy thừa 2 lớn nhất không vượt chiều cao và chiều rộng. Bốn hình chữ nhật tại **bốn góc** phủ toàn vùng truy vấn, có thể chồng nhau.

Vì phép min lũy đẳng, gộp bốn kết quả vẫn đúng. Trên mô hình phép gộp O(1):

- **Tiền xử lý/bộ nhớ:** O(R C log R log C).
- **Truy vấn:** O(1) bằng một số hằng định các ô bảng.

Đây là phần mở rộng của cùng nguyên lý, nhưng chi phí bộ nhớ lớn hơn nhiều so với bảng thưa 1D. Khi xử lý ma trận lớn, nên cân nhắc giới hạn bộ nhớ và liệu có thể dùng cấu trúc chuyên biệt khác hay không.

### Khi có một chiều rỗng

Một hình chữ nhật có `r1=r2` hoặc `c1=c2` không chứa ô nào. Nếu API trả min của tập rỗng là lỗi, phải kiểm tra trước khi tính log chiều dài, tương tự bài toán 1D.

## 25. So sánh sparse table với những lựa chọn khác

| Cấu trúc | Xây dựng | Truy vấn điển hình | Cập nhật một điểm | Phù hợp nhất |
|---|---:|---:|---:|---|
| Quét trực tiếp | O(1) ngoài dữ liệu | O(r-l) | O(1) trên mảng | Ít truy vấn, dữ liệu nhỏ |
| Prefix sum | O(n) | **O(1)** tổng | O(n) nếu phải duy trì bảng | Tổng trên mảng tĩnh |
| Prefix XOR | O(n) | **O(1)** XOR | O(n) nếu phải duy trì bảng | XOR trên mảng tĩnh |
| Sparse table min/max/GCD | **O(n log n)** | **O(1)** | Không hiệu quả theo thiết kế tĩnh | Rất nhiều truy vấn, không cập nhật |
| Sparse table phân khối rời | O(n log n) | O(log n) gộp bất kỳ phép kết hợp | Không hiệu quả theo thiết kế tĩnh | Phép kết hợp tổng quát |
| Disjoint sparse table | O(n log n) | O(1) với phép kết hợp phù hợp | Không hiệu quả theo thiết kế tĩnh | Query tĩnh kết hợp tổng quát |
| Sqrt decomposition | O(n) | O(√n) | O(1) cho tổng; O(√n) cho min đơn giản | Cần thiết kế khối dễ hiểu |
| Segment tree | O(n) | O(log n) | **O(log n)** | Truy vấn và cập nhật xen kẽ |
| Fenwick tree cho tổng | O(n) nếu xây tuyến tính | O(log n) tổng | O(log n) cộng điểm | Tổng động, thao tác thích hợp |

Các cận trên giả định phép toán xử lý một giá trị tốn O(1). Cập nhật sparse table không được ghi là O(1) vì việc sửa một giá trị nguồn **không tự sửa những kết quả đã lưu**.

### Khi nào sparse table là lựa chọn tốt?

- Mảng **hoàn toàn tĩnh** trong vòng đời truy vấn.
- Có rất nhiều truy vấn min/max/GCD.
- Có đủ bộ nhớ O(n log n).
- Cần độ trễ truy vấn rất thấp, O(1) số phép gộp.
- Không cần cập nhật điểm/đoạn hoặc chấp nhận xây lại sau các đợt thay đổi rất hiếm.

### Khi nào không nên ưu tiên?

- Chỉ hỏi vài đoạn ngắn: quét trực tiếp có thể rẻ hơn xây bảng.
- Hỏi tổng/XOR tĩnh: prefix có thể đơn giản và tiết kiệm bộ nhớ hơn.
- Cập nhật thường xuyên: segment tree hoặc cấu trúc động khác.
- Dữ liệu lớn vượt ngân sách RAM: O(n log n) có thể không phù hợp.
- Phép gộp không lũy đẳng nhưng muốn dùng công thức overlap: **không đúng**.

## 26. Bài tập tự luyện có lời giải

**Bài 1 — Ý nghĩa ô bảng.** `st[3][5]` mô tả đoạn nào?

*Lời giải:* Độ dài `2^3=8`, bắt đầu tại 5, nên mô tả **`[5,13)`** nếu mảng có ít nhất 13 phần tử.

**Bài 2 — Số ô hợp lệ.** Với `n=10`, hàng có đoạn dài 4 chứa bao nhiêu ô?

*Lời giải:* `10-4+1=7` ô, ứng với các vị trí bắt đầu 0 đến 6.

**Bài 3 — Số hàng.** Với `n=8`, sparse table có bao nhiêu hàng không rỗng?

*Lời giải:* `floor(log2(8))+1=4` hàng, cho độ dài **1,2,4,8**.

**Bài 4 — Bảng đầu tiên.** Với `a=[5,2,6,3,1,7,4,8]`, `st[1]` của min là gì?

*Lời giải:* **`[2,2,3,1,1,4,4]`**, lấy min từng cặp kề nhau.

**Bài 5 — Đoạn dài 4.** `st[2][1]` bằng bao nhiêu trên mảng ở bài 4?

*Lời giải:* `min(2,6,3,1)=1`, vì `st[2][1]` quản lý `[1,5)`.

**Bài 6 — Truy vấn dài 6.** Với đoạn `[1,7)`, chọn `k`, `s` và hai khối nào?

*Lời giải:* `k=floor(log2(6))=2`, `s=4`. Hai khối **`[1,5)`** và **`[3,7)`**.

**Bài 7 — Kết quả RMQ.** Min của `[1,7)` trên mảng mẫu bằng bao nhiêu?

*Lời giải:* `min(st[2][1],st[2][3])=min(1,1)=1`.

**Bài 8 — Giao nhau.** Hai khối ở bài 6 chồng lấn ở đâu? Tại sao không sai với min?

*Lời giải:* Vùng **`[3,5)`**, chứa các giá trị `3,1`. Do **min(x,x)=x**, gộp lại phần chung không đổi min.

**Bài 9 — Tổng bị đếm trùng.** Nếu dùng hai khối ở bài 6 để cộng, kết quả sai là bao nhiêu so với tổng thật?

*Lời giải:* Hai khối có tổng 12 và 15, gộp ra **27**. Tổng thật là **23**; dư 4 do đếm trùng `3+1`.

**Bài 10 — Thuộc tính.** Phép cộng số nguyên kết hợp và lũy đẳng không?

*Lời giải:* **Kết hợp**, nhưng **không lũy đẳng** vì `5+5=10≠5`.

**Bài 11 — Phép phù hợp.** Kể tên ba phép gộp có thể dùng sparse table hai khối overlap.

*Lời giải:* **Min, max, GCD trên số nguyên không âm**; AND/OR bit cũng là các ví dụ phù hợp.

**Bài 12 — Độ dài 1.** Với `[4,5)`, `k` là bao nhiêu và kết quả lấy ở đâu?

*Lời giải:* Độ dài 1, nên `k=0`, `s=1`. Hai khối đều trỏ `st[0][4]`; min với chính nó không đổi.

**Bài 13 — Đoạn rỗng.** Có được gọi `query(2,2)` trong giao diện RMQ bài này không?

*Lời giải:* **Không.** Đoạn có biên hợp lệ nhưng không có phần tử, nên phương thức báo **ValueError**.

**Bài 14 — Đổi biên.** Đề dùng `[L=2,R=7]` 1-based đóng; đổi thành dạng nào?

*Lời giải:* **`[1,7)` 0-based**.

**Bài 15 — Chọn k không dùng log thực.** Với độ dài 9, `k=(9).bit_length()-1` là bao nhiêu?

*Lời giải:* `(9).bit_length()=4`, nên `k=3` và `s=8`.

**Bài 16 — Bất biến.** Nêu bất biến đủ để chứng minh bước xây sparse table.

*Lời giải:* **`st[k][i]` luôn là kết quả gộp đúng đoạn `[i,i+2^k)`**. Hàng 0 đúng hiển nhiên; hàng k được gộp từ hai nửa ở hàng k−1.

**Bài 17 — Độ phức tạp.** Nêu thời gian và bộ nhớ xây sparse table thông thường.

*Lời giải:* Có O(log n) hàng, mỗi hàng tối đa n ô; xây **O(n log n)** thời gian và dùng **O(n log n)** bộ nhớ.

**Bài 18 — Truy vấn.** Với min và phép so sánh O(1), tại sao mỗi query O(1)?

*Lời giải:* Chỉ cần tính một k, đọc **hai ô bảng** và thực hiện **một phép min**, không quét theo độ dài đoạn.

**Bài 19 — Cập nhật.** Sau khi xây bảng, đổi `a[4]` từ 1 thành 100. Có thể giữ nguyên các hàng cao rồi tiếp tục hỏi min không?

*Lời giải:* **Không.** Những ô lưu đoạn chứa vị trí 4 có thể không còn đúng; cần tái tính thích hợp hoặc dùng cấu trúc động.

**Bài 20 — Phân khối không chồng lấn.** Với đoạn `[1,7)` dài 6, chia thành những khối lũy thừa 2 rời nào để tính tổng?

*Lời giải:* **`[1,5)`** dài 4 và **`[5,7)`** dài 2, tổng 12+11=23.

**Bài 21 — Khác biệt hai biến thể.** Sparse table thông thường và disjoint sparse table khác nhau ở điều kiện O(1) query như thế nào?

*Lời giải:* Bảng thông thường dùng **hai khối có thể chồng lấn** nên cần phép gộp lũy đẳng. Disjoint sparse table dùng **hai phần rời**, nên với cấu trúc thích hợp chỉ cần tính kết hợp.

**Bài 22 — Argmin.** Với `a=[4,2,9,2,2,7]`, trả cặp `(min,index)` cho `[0,6)`, ưu tiên vị trí nhỏ hơn khi hòa.

*Lời giải:* **`(2,1)`**. Giá trị 2 còn xuất hiện ở các vị trí 3 và 4 nhưng ưu tiên chỉ số 1.

**Bài 23 — GCD âm.** Vì sao nên chuẩn hóa số âm trước khi dùng `gcd(x,x)=x`?

*Lời giải:* Theo quy ước gcd không âm, `gcd(-6,-6)=6`, không phải −6. Dùng `abs(x)` đưa dữ liệu về miền phù hợp tính lũy đẳng.

**Bài 24 — Chọn cấu trúc.** Có `n=100000` giá trị tĩnh, hàng triệu truy vấn min, không cập nhật. Có đủ RAM cho O(n log n). Lựa chọn nào phù hợp?

*Lời giải:* **Sparse table min** là lựa chọn đáng cân nhắc: xây O(n log n), sau đó mỗi RMQ O(1). Cần kiểm tra chi phí RAM cụ thể của kiểu dữ liệu và ngôn ngữ.

**Bài 25 — Truy vấn tổng tĩnh.** Vì sao prefix sum có thể tốt hơn sparse table cho tổng?

*Lời giải:* Prefix sum xây O(n), lưu O(n), truy vấn `P[r]-P[l]` O(1). Sparse table tổng quát cần O(n log n) bảng và thường O(log n) nếu gộp các khối rời.

**Bài 26 — Sparse table 2D.** Truy vấn min hình chữ nhật tĩnh có thể dùng bao nhiêu khối ở bốn góc?

*Lời giải:* **Bốn hình chữ nhật** có chiều cao/rộng là các lũy thừa 2 phù hợp. Chúng có thể chồng lấn; phép min lũy đẳng cho phép gộp kết quả O(1).

## 27. Tổng kết

**Bảng thưa (sparse table)** chuẩn bị kết quả cho mọi đoạn độ dài **1,2,4,8,...** trong mảng không đổi. Bất biến:

```text
st[k][i] = Q(i, i+2^k)
```

được duy trì nhờ công thức chia đôi:

```text
st[k][i]
  = st[k-1][i] ⊕ st[k-1][i+2^(k-1)]
```

Với phép gộp **kết hợp và lũy đẳng**, truy vấn không rỗng `[l,r)` chỉ cần chọn `s` là lũy thừa 2 lớn nhất không vượt `r-l`, sau đó gộp:

```text
Q(l,r) = st[k][l] ⊕ st[k][r-s]

k = floor(log2(r-l))
s = 2^k
```

Hai khối được phép **chồng lấn** vì `x⊕x=x`. Đây là cơ chế cho **O(1) truy vấn min/max/GCD** sau **O(n log n) tiền xử lý và bộ nhớ**. Không được sao chép công thức overlap cho **tổng, XOR hoặc ghép chuỗi**, vì những phép ấy không lũy đẳng; nếu chỉ có tính kết hợp thì có thể phân rã thành khối rời O(log n), dùng prefix khi có nghịch đảo, hoặc chọn biến thể disjoint sparse table.

**Điều kiện quan trọng nhất là dữ liệu tĩnh.** Khi cần cập nhật thường xuyên, các bản tóm tắt đã tính trước sẽ lỗi thời và segment tree hay cấu trúc động khác thường phù hợp hơn. Trước khi áp dụng sparse table, hãy xác định **quy ước biên [l,r), phép gộp, tính lũy đẳng, chính sách đoạn rỗng, chi phí bộ nhớ và yêu cầu cập nhật**.

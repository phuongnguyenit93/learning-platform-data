# Tổng tiền tố và truy vấn tổng khi dữ liệu không đổi

Giả sử một cửa hàng lưu doanh thu mỗi ngày trong một mảng. Người quản lý liên tục hỏi: “Tổng doanh thu từ ngày thứ 3 đến ngày thứ 7 là bao nhiêu?”, “Tổng 30 ngày gần nhất?”, “Tổng toàn bộ kỳ báo cáo?”. Nếu mỗi câu hỏi đều chạy qua các ngày được chọn để cộng lại, một khối lượng lớn công việc sẽ bị **lặp đi lặp lại**.

**Mảng tổng tiền tố** (*prefix sum array*) giải quyết tình huống ấy bằng cách **tính sẵn tổng của mọi đoạn bắt đầu ở đầu mảng**. Khi dữ liệu không thay đổi, tổng của bất kỳ đoạn liên tiếp nào sau đó được trả lời chỉ bằng **hai lần tra bảng và một phép trừ**.

Tư tưởng chính là:

```text
Tổng [l,r) = Tổng [0,r) - Tổng [0,l)
```

Bài học nằm trong chương **Truy vấn đoạn**, thuộc mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mô-đun xây dựng nền tảng cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, nhấn mạnh **bất biến, thao tác và độ phức tạp thời gian/bộ nhớ** để lựa chọn cấu trúc phù hợp. Ở đây, ta học cách xây tổng tiền tố, chứng minh công thức, xử lý biên, triển khai Python, đo đánh đổi giữa tiền xử lý và nhiều truy vấn, đồng thời xác định đúng giới hạn **dữ liệu tĩnh**.

## 1. Bài toán truy vấn tổng trên đoạn

Cho mảng số gồm `n` phần tử:

```text
a = [a[0], a[1], ..., a[n-1]]
```

Một truy vấn tổng chỉ định hai chỉ số `l,r` để yêu cầu tổng các phần tử **liên tiếp**.

Trong bài này, quy ước thống nhất là **0-based, đoạn nửa mở `[l,r)`**:

```text
0 <= l <= r <= n

sum(l,r) = a[l] + a[l+1] + ... + a[r-1]
```

Nghĩa là **lấy vị trí l nhưng không lấy vị trí r**.

Dùng ví dụ xuyên suốt:

```text
Chỉ số:       0    1    2    3    4    5
Giá trị:      4   -1    7    2    9    3
```

Một số yêu cầu:

| Truy vấn | Phần tử được lấy | Kết quả |
|---|---|---:|
| `[0,3)` | `4,-1,7` | `10` |
| `[2,5)` | `7,2,9` | `18` |
| `[1,6)` | `-1,7,2,9,3` | `20` |
| `[0,6)` | Toàn bộ mảng | `24` |
| `[3,3)` | Không có phần tử | `0` |

**Tổng đoạn rỗng bằng 0**, vì 0 là phần tử đơn vị của phép cộng.

### Một truy vấn có độ dài bao nhiêu?

Với đoạn nửa mở:

```text
length([l,r)) = r - l
```

Do đó `[2,5)` có ba phần tử ở vị trí 2,3,4; `[3,3)` có 0 phần tử; `[0,n)` có đúng n phần tử.

### Vì sao không dùng ngay `sum(a[l:r])`?

Python có thể tính:

```python
a = [4, -1, 7, 2, 9, 3]

assert sum(a[2:5]) == 18
assert sum(a[0:6]) == 24
```

Nhưng `a[l:r]` **tạo danh sách con** dài `r-l` và `sum` duyệt qua từng phần tử. Một truy vấn tốn **O(r-l)** thời gian, có thể O(n) trong trường hợp xấu nhất. Chi phí tạo lát cắt còn dùng O(r-l) bộ nhớ tạm.

Nếu chỉ có vài câu hỏi, cách trực tiếp là lựa chọn tốt. Nếu có hàng trăm nghìn câu hỏi trên **cùng dữ liệu không đổi**, ta nên tận dụng tiền xử lý.

## 2. Ý tưởng tiền xử lý: ghi nhớ tổng từ đầu mảng

Gọi `P` là mảng tổng tiền tố, dài **n+1** phần tử.

Ta định nghĩa chính xác:

```text
P[0] = 0

P[k] = a[0] + a[1] + ... + a[k-1]
       với 1 <= k <= n
```

Nói bằng lời: **`P[k]` là tổng của đúng k phần tử đầu tiên**.

Cách định nghĩa này khác với “`P[k]` là tổng đến và bao gồm `a[k]`”. Sự khác nhau một chỉ số quyết định công thức truy vấn có đúng hay không.

### Công thức xây bảng

```text
P[0] = 0
P[i+1] = P[i] + a[i]       với i = 0,1,...,n-1
```

Từ ví dụ:

```text
a = [4, -1, 7, 2, 9, 3]
```

Ta xây lần lượt:

| `k` | `P[k]` | Diễn giải |
|---:|---:|---|
| 0 | 0 | Tổng 0 phần tử |
| 1 | 4 | `0+4` |
| 2 | 3 | `4+(-1)` |
| 3 | 10 | `3+7` |
| 4 | 12 | `10+2` |
| 5 | 21 | `12+9` |
| 6 | 24 | `21+3` |

Kết quả:

```text
Chỉ số a:  0    1    2    3    4    5
a:         4   -1    7    2    9    3

Chỉ số P:  0    1    2    3    4    5    6
P:         0    4    3   10   12   21   24
```

Mảng `P` có **7** phần tử dù mảng gốc có **6** phần tử. Phần tử thêm ở đầu `P[0]=0` giúp công thức truy vấn nhất quán cả khi `l=0`.

## 3. Công thức truy vấn tổng O(1)

Với `0 <= l <= r <= n`, ta có:

```text
P[r] = a[0] + ... + a[l-1] + a[l] + ... + a[r-1]
P[l] = a[0] + ... + a[l-1]
```

Lấy hiệu:

```text
P[r] - P[l] = a[l] + a[l+1] + ... + a[r-1]
```

Vậy:

```text
range_sum(l,r) = P[r] - P[l]
```

**Không có vòng lặp trong lúc trả lời truy vấn.** Ta chỉ đọc hai giá trị đã lưu và thực hiện một phép trừ.

### Truy vết truy vấn `[2,5)`

```text
a = [4, -1, 7, 2, 9, 3]
P = [0,  4, 3,10,12,21,24]

P[5] = 4+(-1)+7+2+9 = 21
P[2] = 4+(-1) = 3

P[5] - P[2] = 21 - 3 = 18
```

Phần `4+(-1)` phía trước vị trí 2 xuất hiện ở cả hai tiền tố và **triệt tiêu**. Chỉ còn các phần tử ở đoạn `[2,5)`.

### Truy vấn toàn mảng

```text
sum([0,n)) = P[n] - P[0] = P[n]
```

Với `n=6`, kết quả `P[6]=24`.

### Truy vấn đoạn rỗng

```text
sum([l,l)) = P[l] - P[l] = 0
```

Không cần một nhánh đặc biệt để cộng đoạn rỗng, miễn là hai biên **hợp lệ**.

## 4. Vì sao dùng đoạn nửa mở `[l,r)`?

Trong nhiều đề thuật toán, đầu vào sử dụng đoạn **đóng** `[L,R]` và chỉ số từ 1. Tuy vậy, với một API xử lý mảng trong Python, `[l,r)` thường dễ nhất vì:

1. **Độ dài:** `r-l`.
2. **Rỗng:** `[l,l)`.
3. **Toàn mảng:** `[0,n)`.
4. **Ghép đoạn:** `[l,m)` và `[m,r)` không đếm trùng vị trí `m`.
5. **Prefix:** hai biên sử dụng trực tiếp: `P[r]-P[l]`.
6. **Slicing:** `a[l:r]` cũng chọn đúng các phần tử ấy.

Đoạn `[l,r)` được coi hợp lệ khi:

```text
0 <= l <= r <= n
```

Đặc biệt, **`r=n` là hợp lệ**: đó là biên nằm **sau phần tử cuối**, không phải chỉ số được dùng để đọc `a[n]`.

### Bảng các trường hợp biên

Với `n=6`:

| Đoạn | Hợp lệ? | Tổng | Giải thích |
|---|---|---:|---|
| `[0,0)` | Có | 0 | Đoạn rỗng ở đầu |
| `[6,6)` | Có | 0 | Đoạn rỗng ở cuối |
| `[0,6)` | Có | 24 | Toàn mảng |
| `[5,6)` | Có | 3 | Chỉ phần tử cuối |
| `[3,5)` | Có | 11 | `2+9` |
| `[4,2)` | Không | — | Biên đảo |
| `[-1,2)` | Không | — | Biên âm |
| `[1,7)` | Không | — | Vượt n |

Điểm quan trọng là **một đoạn có hợp lệ hay không phải được kiểm tra trước**, dù trong Python việc truy cập phần tử `P[-1]` vẫn trả giá trị nào đó.

## 5. Triển khai cơ bản bằng Python

Ta bắt đầu từ một hàm xây tiền tố và một hàm trả lời truy vấn. Các hàm này hoạt động trên **giá trị số** có phép cộng và phép trừ đúng với mô hình tổng đoạn.

```python
def build_prefix_sums(values):
    """P[k] là tổng của k phần tử đầu tiên."""
    prefix = [0]

    for value in values:
        prefix.append(prefix[-1] + value)

    return prefix


def validate_range(n, l, r):
    """Kiểm tra đoạn 0-based [l,r), cho phép rỗng."""
    if type(l) is not int or type(r) is not int:
        raise TypeError("Biên l và r phải là số nguyên")

    if not 0 <= l <= r <= n:
        raise IndexError("Đoạn [l,r) không hợp lệ")


def range_sum(prefix, l, r):
    """Giả định prefix có n+1 phần tử."""
    n = len(prefix) - 1
    validate_range(n, l, r)
    return prefix[r] - prefix[l]


a = [4, -1, 7, 2, 9, 3]
P = build_prefix_sums(a)

assert P == [0, 4, 3, 10, 12, 21, 24]
assert range_sum(P, 2, 5) == 18
assert range_sum(P, 0, 6) == 24
assert range_sum(P, 3, 3) == 0
assert range_sum(P, 5, 6) == 3
```

### Tại sao có kiểm tra kiểu số nguyên?

Python xem `True` và `False` là các giá trị tương thích số nguyên trong một số thao tác (`bool` kế thừa `int`). Trong API học tập, chúng ta chủ động dùng `type(l) is int` để từ chối Boolean làm chỉ số biên; đó là một **chính sách giao diện** có thể điều chỉnh theo hệ thống.

### Cây rỗng có bảng tổng tiền tố không?

Mảng rỗng `[]` vẫn có **một** giá trị tiền tố:

```python
empty_P = build_prefix_sums([])

assert empty_P == [0]
assert range_sum(empty_P, 0, 0) == 0
```

Cách biểu diễn này làm cho cả công thức xây và công thức truy vấn đúng ở trường hợp `n=0`.

### Kiểm tra biên sai

```python
for bad_l, bad_r in [
    (-1, 2),
    (3, 2),
    (0, 7),
    (7, 7),
]:
    try:
        range_sum(P, bad_l, bad_r)
    except IndexError:
        pass
    else:
        raise AssertionError("Phải báo lỗi biên không hợp lệ")

try:
    range_sum(P, True, 3)
except TypeError:
    pass
else:
    raise AssertionError("Không chấp nhận Boolean làm biên")
```

Không nên mặc nhiên để Python xử lý chỉ số âm cho một API truy vấn đoạn 0-based nghiêm ngặt: `P[-1]` mang ý nghĩa “phần tử cuối” trong Python, không phải chỉ số âm hợp lệ của mô hình toán học trên.

## 6. Xây một lần và trả lời nhiều truy vấn

Điều khiến tổng tiền tố hữu ích là **tách công việc thành hai giai đoạn**:

1. **Preprocessing:** duyệt toàn bộ mảng **một lần**, xây `P`.
2. **Query:** cho mỗi cặp `(l,r)`, lấy `P[r]-P[l]`.

Giả sử có `q` truy vấn. Ta không phải xây lại `P` cho mỗi câu hỏi.

```python
a = [4, -1, 7, 2, 9, 3]
queries = [(0, 3), (2, 5), (1, 6), (0, 6), (3, 3)]

P = build_prefix_sums(a)
answers = [range_sum(P, l, r) for l, r in queries]

assert answers == [10, 18, 20, 24, 0]
```

Mỗi truy vấn được giải quyết bằng **O(1)** thao tác số học trên bảng đã tồn tại. Chi phí tạo danh sách câu trả lời cho `q` truy vấn là **O(q)** bộ nhớ đầu ra.

### Bảng truy vết cho nhiều truy vấn

| Truy vấn `[l,r)` | `P[l]` | `P[r]` | Hiệu | Tổng |
|---|---:|---:|---:|---:|
| `[0,3)` | 0 | 10 | `10-0` | 10 |
| `[2,5)` | 3 | 21 | `21-3` | 18 |
| `[1,6)` | 4 | 24 | `24-4` | 20 |
| `[0,6)` | 0 | 24 | `24-0` | 24 |
| `[3,3)` | 10 | 10 | `10-10` | 0 |

Lưu ý: hai truy vấn có thể chứa các phần tử trùng nhau rất nhiều, nhưng bảng `P` đã ghi lại tất cả phần tổng chung, nên **không có lần quét phần tử mới** cho mỗi câu hỏi.

## 7. Chứng minh bất biến khi xây tổng tiền tố

Ta muốn chứng minh rằng sau khi hoàn tất vòng xây:

> Với mọi `k` trong `[0,n]`, `P[k]` đúng bằng tổng các phần tử `a[0:k]`.

### Cơ sở quy nạp

Với `k=0`:

```text
P[0] = 0
```

Đó là tổng của **0 phần tử đầu**. Bất biến đúng.

### Bước quy nạp

Giả sử với một `k` từ 0 đến `n-1`:

```text
P[k] = a[0] + ... + a[k-1]
```

Theo lệnh xây bảng:

```text
P[k+1] = P[k] + a[k]
       = a[0] + ... + a[k-1] + a[k]
```

Vậy `P[k+1]` là tổng đúng `k+1` phần tử đầu. Bất biến được duy trì.

### Kết luận

Theo quy nạp, bất biến đúng cho mọi `k` đến `n`. Công thức truy vấn:

```text
P[r] - P[l]
```

lấy tổng đầu `r` phần tử và bỏ tổng đầu `l` phần tử, nên còn đúng đoạn `[l,r)`.

**Chứng minh này dựa trên phép cộng/trừ chính xác trong mô hình toán học**. Với số thực dấu phẩy động, sai số làm tròn có thể khiến hai cách tính sai khác một ít; xem phần lưu ý về kiểu dữ liệu.

## 8. Độ phức tạp: O(n) tiền xử lý, O(1) truy vấn

Gọi `n` là số phần tử và `q` là số truy vấn. Với phép cộng/trừ trên giá trị kích thước cố định có chi phí O(1):

### Xây bảng `P`

Vòng lặp xét từng giá trị `a[i]` đúng một lần. Mỗi bước thực hiện một phép cộng và `append` vào danh sách.

- **Thời gian:** O(n).
- **Bộ nhớ bảng:** `n+1` phần tử, O(n).
- **Bộ nhớ biến điều khiển:** O(1), không tính bảng kết quả.

### Trả lời một truy vấn

```text
return P[r] - P[l]
```

- **Thời gian:** O(1).
- **Bộ nhớ phụ:** O(1), nếu chỉ trả một số.

### Trả lời q truy vấn

- Xây một lần: O(n).
- q truy vấn: O(q).
- **Tổng thời gian:** O(n+q).
- **Bộ nhớ:** O(n) cho bảng; thêm O(q) nếu giữ toàn bộ câu trả lời.

So sánh với quét trực tiếp:

| Phương án | Tiền xử lý | Một truy vấn dài k | q truy vấn dài tối đa n | Bộ nhớ phụ |
|---|---:|---:|---:|---:|
| Cộng trực tiếp bằng vòng lặp | O(1) | O(k) | O(qn) trong trường hợp xấu nhất | O(1) |
| `sum(a[l:r])` và slicing | O(1) | O(k) | O(qn) | O(k) tạm thời |
| **Prefix sum** | **O(n)** | **O(1)** | **O(n+q)** | **O(n)** |

**Không phải lúc nào prefix cũng tối ưu hơn về thực tế.** Nếu chỉ có một truy vấn ngắn, xây cả bảng O(n) có thể nhiều việc hơn quét O(k). Nếu có nhiều truy vấn trên cùng mảng tĩnh, chi phí xây bảng được **phân bổ** qua nhiều câu hỏi.

### Tại sao không thể xây nhanh hơn O(n)?

Nếu cần một bảng tổng đúng với **mọi phần tử đầu vào**, ta phải đọc dữ liệu của các phần tử đó. Do vậy, tiền xử lý có cận dưới Ω(n) trong mô hình truy cập dữ liệu thông thường. Xây tiền tố bằng một lượt duyệt là tối ưu về bậc thời gian cho chính nhiệm vụ ấy.

## 9. Đổi quy ước 1-based đóng sang [l,r)

Nhiều đề bài mô tả câu hỏi:

> Tính tổng các phần tử từ **L đến R**, tính cả hai đầu, đánh số phần tử bắt đầu từ 1.

Đây là đoạn **1-based đóng `[L,R]`** với:

```text
1 <= L <= R <= n
```

Chuyển sang đoạn **0-based nửa mở**:

```text
l = L - 1
r = R

[L,R] 1-based  ->  [L-1,R) 0-based
```

Suy ra công thức:

```text
sum_1based_inclusive(L,R) = P[R] - P[L-1]
```

Ví dụ:

```text
a 0-based:    [4, -1, 7, 2, 9, 3]
Vị trí 1-based: 1   2  3  4  5  6

Yêu cầu [3,5] 1-based lấy 7,2,9.

Chuyển: [L-1,R) = [2,5)
Đáp án: P[5]-P[2] = 21-3 = 18
```

### Hàm chuyển đổi có kiểm tra biên

```python
def to_half_open_from_1based(n, L, R):
    if type(L) is not int or type(R) is not int:
        raise TypeError("L và R phải là số nguyên")
    if not 1 <= L <= R <= n:
        raise IndexError("Đoạn 1-based đóng không hợp lệ")
    return (L - 1, R)


def range_sum_1based(prefix, L, R):
    n = len(prefix) - 1
    l, r = to_half_open_from_1based(n, L, R)
    return range_sum(prefix, l, r)


assert range_sum_1based(P, 3, 5) == 18
assert range_sum_1based(P, 1, 6) == 24
assert range_sum_1based(P, 6, 6) == 3
```

Nếu đề bài dùng **0-based đóng `[l,R]`**, ta chuyển thành `[l,R+1)`, nên tổng là `P[R+1]-P[l]`. Các công thức không mâu thuẫn: chúng biểu diễn **những quy ước chỉ số khác nhau**.

### Truy vấn đóng trên mảng rỗng

Nếu `n=0`, không có cặp `1<=L<=R<=n` nào hợp lệ. Đây là khác biệt với `[0,0)` 0-based nửa mở, vốn biểu diễn **đoạn rỗng hợp lệ**.

## 10. Đối tượng tổng tiền tố bất biến theo giao diện

Hàm xây và hàm query ở trên đủ cho nhiều bài tập. Đối với mã ứng dụng, ta có thể gói chúng thành một kiểu đối tượng thể hiện hợp đồng: **dữ liệu tĩnh, không hỗ trợ cập nhật**.

```python
class StaticRangeSum:
    """Snapshot mảng số; query trên [l,r) trong O(1)."""

    def __init__(self, values):
        self._values = tuple(values)
        temp = [0]

        for value in self._values:
            temp.append(temp[-1] + value)

        self._prefix = tuple(temp)

    def __len__(self):
        return len(self._values)

    def query(self, l, r):
        validate_range(len(self), l, r)
        return self._prefix[r] - self._prefix[l]

    def query_1based_inclusive(self, L, R):
        l, r = to_half_open_from_1based(len(self), L, R)
        return self.query(l, r)

    def prefix_total(self, k):
        if type(k) is not int or not 0 <= k <= len(self):
            raise IndexError("Số lượng phần tử tiền tố không hợp lệ")
        return self._prefix[k]


original = [4, -1, 7, 2, 9, 3]
rs = StaticRangeSum(original)

assert len(rs) == 6
assert rs.prefix_total(0) == 0
assert rs.prefix_total(5) == 21
assert rs.query(2, 5) == 18
assert rs.query_1based_inclusive(3, 5) == 18
assert rs.query(6, 6) == 0

# Thay đổi mảng bên ngoài không đổi nội dung snapshot.
original[2] = 100
assert rs.query(2, 5) == 18

empty = StaticRangeSum([])
assert len(empty) == 0
assert empty.query(0, 0) == 0
```

**Bất biến đối tượng:** dữ liệu `_values` là một `tuple` và bảng `_prefix` cũng là `tuple`, nên người dùng thông thường không thể thay đổi từng phần tử bằng cú pháp gán chỉ số. Tuy vậy, các tên bắt đầu bằng `_` chỉ là **quy ước nội bộ Python**, không phải bảo mật hay bất biến được cưỡng chế tuyệt đối.

### Snapshot có nghĩa gì?

Khi tạo `StaticRangeSum(original)`, đối tượng sao chép các **tham chiếu giá trị** vào tuple. Với số nguyên, số thực và giá trị bất biến, snapshot này phù hợp. Nếu phần tử là đối tượng **có thể thay đổi** và phép cộng phụ thuộc trạng thái bên trong, tuple không tự tạo bản sao sâu. Bài này giả định dữ liệu số đơn giản, có giá trị không bị sửa bên trong.

### Vì sao nên gói thành đối tượng?

- Tránh làm sai sự tương ứng giữa bảng `P` và dữ liệu đã dùng để xây.
- Đặt hợp đồng truy vấn và kiểm tra biên ở một chỗ.
- Phản ánh rõ ràng: sau khi xây, chỉ **đọc**, không có phương thức `point_update`.
- Thuận tiện khi chạy nhiều truy vấn trên cùng snapshot.

Nếu ứng dụng thật sự cần cập nhật, phải chuyển sang một thiết kế khác hoặc xây snapshot mới.

## 11. Dữ liệu không đổi là giả định cốt lõi

Tổng tiền tố tĩnh **không tự theo dõi** việc thay đổi của mảng nguồn.

Giả sử:

```text
a = [4, -1, 7, 2, 9, 3]
P = [0, 4, 3, 10, 12, 21, 24]
```

Sau khi đổi `a[2]` từ 7 thành 10, tổng tiền tố đúng phải là:

```text
a' = [4, -1, 10, 2, 9, 3]
P' = [0, 4, 3, 13, 15, 24, 27]
```

Bảng cũ `P` cho tổng `[2,5)` là:

```text
P[5] - P[2] = 21 - 3 = 18
```

Nhưng trên mảng mới:

```text
10 + 2 + 9 = 21
```

Nếu sử dụng `P` cũ để trả lời câu hỏi về `a'`, kết quả sẽ sai.

### Một thay đổi tại i ảnh hưởng những tiền tố nào?

Vì `P[k]` chứa các phần tử ở vị trí từ 0 đến `k-1`, thay đổi `a[i]` sẽ ảnh hưởng đến:

```text
P[i+1], P[i+2], ..., P[n]
```

Tức là **toàn bộ hậu tố bảng tiền tố** từ `i+1` trở đi.

Với một cập nhật điểm, sửa lại các phần tử bảng có thể tốn O(n) trong trường hợp xấu nhất. Nếu có rất nhiều cập nhật xen kẽ truy vấn, lợi thế O(1) của truy vấn không bảo đảm hệ thống tổng thể hiệu quả.

### Các phương án khi dữ liệu thay đổi

- **Ít lần thay đổi:** sau mỗi lần sửa, xây lại bảng prefix O(n).
- **Nhiều lần cộng/gán điểm và hỏi tổng đoạn:** cân nhắc **Fenwick tree** hoặc **segment tree** (thường O(log n) cho những thao tác phù hợp).
- **Cộng/gán cả đoạn và hỏi tổng:** cân nhắc cấu trúc có hỗ trợ cập nhật đoạn, chẳng hạn segment tree với lazy propagation hoặc biến thể Fenwick thích hợp.
- **Biết trước mọi cập nhật, cuối cùng mới lấy kết quả:** có thể dùng **mảng hiệu** theo lô.

**Không có một lựa chọn tối ưu cho mọi tập thao tác.** Bài này tập trung vào trường hợp **mảng không đổi trong suốt các truy vấn**.

## 12. Tổng tiền tố không cần phần tử dương

Một hiểu lầm phổ biến là prefix sum chỉ hoạt động với các số **không âm**. Thực tế, công thức:

```text
sum(l,r) = P[r] - P[l]
```

đúng cho cả số âm, bằng 0, và các số có dấu khác nhau (với phép cộng/trừ phù hợp).

Ví dụ:

```text
a = [5, -8, 4, 2, -1]
P = [0, 5, -3, 1, 3, 2]
```

Ta có:

```text
sum([1,4)) = -8+4+2 = -2
P[4] - P[1] = 3 - 5 = -2
```

Trong ví dụ này `P` **không tăng đơn điệu** vì dữ liệu có số âm. Điều đó **không làm sai truy vấn tổng**, nhưng lại rất quan trọng nếu muốn dùng **tìm kiếm nhị phân trên tiền tố**.

### Khi nào tiền tố không giảm?

Nếu mọi phần tử `a[i] >= 0`, thì:

```text
P[i+1] = P[i] + a[i] >= P[i]
```

nên `P` **không giảm**.

Ngược lại, nếu có phần tử âm, `P` có thể giảm. Do đó, không được áp dụng các thuật toán dựa trên tính đơn điệu của tổng tiền tố khi dữ liệu có số âm mà chưa kiểm tra lại điều kiện.

### Phản ví dụ cách dùng sai tìm kiếm nhị phân

```text
a = [5, -8, 4, 2, -1]
P = [0, 5, -3, 1, 3, 2]
```

Dãy `P` không được sắp tăng/không giảm. Không thể dùng `bisect_left(P, target)` như trên một dãy đã sắp để tìm chính xác điểm cắt theo tổng, dù **mỗi truy vấn tổng đoạn vẫn O(1)**.

## 13. Mảng hai phần tử, một phần tử và nhiều số 0

Kiểm thử tình huống biên giúp phát hiện lỗi off-by-one mà ví dụ dài đôi khi bỏ sót.

### Mảng một phần tử

```text
a = [9]
P = [0, 9]

sum([0,1)) = 9
sum([0,0)) = 0
sum([1,1)) = 0
```

### Hai phần tử, có số âm

```text
a = [-4, 7]
P = [0, -4, 3]

sum([0,2)) = 3
sum([0,1)) = -4
sum([1,2)) = 7
```

### Các phần tử 0

```text
a = [0, 0, 0]
P = [0, 0, 0, 0]
```

Dù nhiều tiền tố bằng nhau, **không có lỗi**: hiệu của hai tổng tiền tố vẫn là tổng đúng đoạn cần hỏi. Nhưng bằng nhau nhiều lần sẽ hữu ích trong bài toán đếm các đoạn con có tổng 0 về sau.

### Python kiểm tra tổng quát

```python
for data in [
    [],
    [9],
    [-4, 7],
    [0, 0, 0],
    [5, -8, 4, 2, -1],
]:
    prefix = build_prefix_sums(data)
    n = len(data)

    for l in range(n + 1):
        for r in range(l, n + 1):
            expected = sum(data[l:r])
            actual = range_sum(prefix, l, r)
            assert actual == expected
```

Đây là cách **đối chiếu với giải pháp chậm** trên mảng nhỏ. Ta dùng `sum(data[l:r])` làm *oracle* để kiểm tra các cặp biên. Việc kiểm thử này tốn nhiều thời gian hơn một truy vấn thật, nhưng có giá trị phát hiện sai sót trong quá trình phát triển.

## 14. Prefix sum và tổng trung bình đoạn

Một khi biết tổng đoạn, ta có thể tính trung bình cộng trên đoạn **không rỗng**:

```text
average([l,r)) = sum([l,r)) / (r-l),  với l < r
```

Ví dụ trên `a=[4,-1,7,2,9,3]`:

```text
[2,5) có 3 phần tử: 7,2,9
Tổng: 18
Trung bình: 18 / 3 = 6
```

### Python

```python
def range_average(prefix, l, r):
    n = len(prefix) - 1
    validate_range(n, l, r)

    if l == r:
        raise ValueError("Không có trung bình cho đoạn rỗng")

    return (prefix[r] - prefix[l]) / (r - l)


assert range_average(P, 2, 5) == 6.0
assert range_average(P, 0, 6) == 4.0

try:
    range_average(P, 2, 2)
except ValueError:
    pass
else:
    raise AssertionError("Không thể chia cho độ dài 0")
```

Hàm trả số thực theo phép chia `/` của Python, ngay cả khi các đầu vào là số nguyên. Nếu ứng dụng cần phân số chính xác, có thể dùng `fractions.Fraction` hoặc giữ cặp `(total,count)`.

**Quan trọng:** phần tử đơn vị của **tổng** là 0, nhưng **trung bình trên đoạn rỗng** thường **không được định nghĩa**, vì mẫu số bằng 0. Không được tự trả 0 trừ khi giao diện có quy ước riêng được công bố.

## 15. Truy vấn số phần tử thỏa một điều kiện cố định

Không nhất thiết bảng prefix phải lưu trực tiếp giá trị gốc. Ta có thể **biến đổi mỗi phần tử** thành một giá trị khác rồi xây tổng tiền tố trên dãy biến đổi.

Ví dụ, muốn hỏi “Có bao nhiêu số chẵn trong đoạn `[l,r)`?”. Định nghĩa:

```text
b[i] = 1 nếu a[i] là số chẵn
b[i] = 0 nếu không
```

Khi đó:

```text
count_even(l,r) = prefix_b[r] - prefix_b[l]
```

Với dãy:

```text
a = [4, -1, 7, 2, 9, 3]
b = [1,  0, 0, 1, 0, 0]
```

Truy vấn `[0,5)` có 2 số chẵn, gồm 4 và 2.

```python
a = [4, -1, 7, 2, 9, 3]
even_flags = [1 if value % 2 == 0 else 0 for value in a]
even_prefix = build_prefix_sums(even_flags)

assert even_flags == [1, 0, 0, 1, 0, 0]
assert range_sum(even_prefix, 0, 5) == 2
assert range_sum(even_prefix, 2, 5) == 1
assert range_sum(even_prefix, 5, 6) == 0
```

### Điều kiện phải cố định khi xây bảng

Nếu sau đó người dùng đổi câu hỏi thành “Đếm số lớn hơn `x`”, trong đó `x` thay đổi tùy mỗi truy vấn, một bảng cờ duy nhất không còn đủ để xử lý mọi `x`. Ta cần thêm bảng theo từng điều kiện hoặc lựa chọn cấu trúc khác.

Tư duy tổng tiền tố áp dụng khi giá trị cần cộng ở mỗi vị trí có thể được **xác định trước** và **không thay đổi** qua các truy vấn.

## 16. Cửa sổ trượt bằng tổng tiền tố

Một **cửa sổ liên tiếp** dài `k`, bắt đầu tại vị trí `i`, là đoạn:

```text
[i, i+k)
```

Nếu `1 <= k <= n`, vị trí bắt đầu hợp lệ là:

```text
i = 0,1,...,n-k
```

Có đúng **`n-k+1` cửa sổ**.

Ví dụ với mảng sáu phần tử và `k=3`:

| Cửa sổ | Phần tử | Tổng qua tiền tố |
|---|---|---:|
| `[0,3)` | `4,-1,7` | 10 |
| `[1,4)` | `-1,7,2` | 8 |
| `[2,5)` | `7,2,9` | 18 |
| `[3,6)` | `2,9,3` | 14 |

### Python cho mọi tổng cửa sổ

```python
def all_window_sums(values, k):
    n = len(values)
    if type(k) is not int or not 1 <= k <= n:
        raise ValueError("Yêu cầu độ dài cửa sổ 1 <= k <= n")

    prefix = build_prefix_sums(values)
    return [
        range_sum(prefix, i, i + k)
        for i in range(n - k + 1)
    ]


assert all_window_sums([4, -1, 7, 2, 9, 3], 3) == [
    10, 8, 18, 14
]
assert all_window_sums([4, -1, 7, 2, 9, 3], 6) == [24]
```

Xây `P` tốn O(n), rồi tính tổng các cửa sổ trong O(n). Kết quả đầy đủ chứa `n-k+1` số nên chiếm O(n) bộ nhớ trong trường hợp xấu nhất.

**So với kỹ thuật rolling sum:** ta cũng có thể lấy tổng cửa sổ đầu rồi trừ phần tử rời cửa sổ, cộng phần tử mới vào, vẫn O(n) thời gian nhưng chỉ cần O(1) bộ nhớ điều khiển nếu xuất kết quả ngay. Prefix hữu ích hơn khi ngoài các cửa sổ cùng kích thước, ứng dụng còn hỏi **nhiều đoạn độ dài bất kỳ**.

## 17. Tính tổng trên khoảng thời gian đã được đánh chỉ số

Một ứng dụng thực tế thường có dữ liệu theo ngày hoặc thời điểm. Giả sử ta đã sắp xếp các sự kiện theo timestamp, và mỗi sự kiện có một giá trị số.

Truy vấn thời gian dạng nửa mở:

```text
[start,end)
```

bao gồm các sự kiện có thời điểm `start <= t < end`. Nếu timestamp được sắp không giảm, ta tìm hai chỉ số bằng **tìm kiếm nhị phân**, rồi dùng bảng tổng tiền tố để trả kết quả.

```python
from bisect import bisect_left


times = [10, 12, 12, 15, 18, 20]
amounts = [4, 5, 7, -2, 3, 8]
prefix_amounts = build_prefix_sums(amounts)


def amount_between(start, end):
    if start > end:
        raise ValueError("Khoảng thời gian bị đảo")

    l = bisect_left(times, start)
    r = bisect_left(times, end)
    return range_sum(prefix_amounts, l, r)


assert amount_between(12, 18) == 5 + 7 - 2
assert amount_between(18, 21) == 3 + 8
assert amount_between(13, 13) == 0
```

Ở đây, thời điểm 12 xuất hiện hai lần; `bisect_left` tìm vị trí đầu tiên có thời gian **không nhỏ hơn** biên. Vì vậy các sự kiện đúng biên trái được lấy và đúng biên phải bị loại.

**Độ phức tạp:** mỗi truy vấn trên mốc thời gian tốn O(log n) để đổi biên thành chỉ số, sau đó O(1) để lấy tổng. Không được nói toàn bộ truy vấn thời gian O(1) nếu còn bước tìm chỉ số.

Điều kiện là `times` và `amounts` tương ứng một-một, cùng độ dài, và **đều không thay đổi** trong lúc sử dụng tiền tố.

## 18. Đếm đoạn con có tổng cho trước bằng tiền tố

Tổng tiền tố còn giúp giải những bài toán về **đoạn con liên tiếp**, không chỉ trả lời các cặp biên đã biết.

Ta muốn đếm số cặp `(l,r)` với `0 <= l < r <= n` sao cho:

```text
sum([l,r)) = target
```

Theo công thức tiền tố:

```text
P[r] - P[l] = target
```

Suy ra:

```text
P[l] = P[r] - target
```

Nếu duyệt `r` từ trái sang phải, ta chỉ cần biết **bao nhiêu tiền tố trước đó** có giá trị bằng `P[r]-target`.

### Thuật toán dùng bảng tần suất

Dùng dictionary `frequency` để lưu số lần xuất hiện của các tổng tiền tố **đã đi qua**, bắt đầu `P[0]=0`.

```python
def count_subarrays_with_sum(values, target):
    frequency = {0: 1}
    running = 0
    answer = 0

    for value in values:
        running += value

        # Có bao nhiêu biên l trước r thỏa P[l] = P[r]-target?
        answer += frequency.get(running - target, 0)

        # Sau khi đếm xong, đưa P[r] vào các tiền tố đã thấy.
        frequency[running] = frequency.get(running, 0) + 1

    return answer


assert count_subarrays_with_sum([1, 2, 1, 2], 3) == 3
assert count_subarrays_with_sum([2, -2, 3, 0, -3, 3], 0) == 6
assert count_subarrays_with_sum([], 0) == 0
```

### Vì sao phải đếm trước khi ghi tiền tố hiện tại?

Ta chỉ xét **đoạn không rỗng** `l<r`. Nếu ghi `P[r]` vào dictionary **trước khi đếm**, với `target=0` thuật toán có thể tính cả cặp `l=r` — một đoạn rỗng — làm kết quả sai.

Bất biến của dictionary:

> Khi đang xét biên phải `r`, `frequency` chỉ chứa các tiền tố `P[0],...,P[r-1]`, nên mọi `l` được đếm đều thỏa `l<r`.

### Đánh đổi chi phí

Thuật toán này tốn O(n) thời gian **trung bình** và O(n) bộ nhớ dictionary trong trường hợp xấu nhất, với giả định thao tác hash trên số có chi phí trung bình hằng số. Nó khác với truy vấn tổng **O(1) khi cặp biên đã cho**: ta đang **tìm/đếm tất cả các cặp biên thỏa một mục tiêu**.

## 19. Có thể khôi phục các giá trị gốc từ tiền tố không?

Với tổng số học chính xác, ta có:

```text
P[i+1] = P[i] + a[i]
```

nên:

```text
a[i] = P[i+1] - P[i]
```

Do đó bảng tiền tố chứa đủ thông tin để **khôi phục mảng số ban đầu**, miễn là phép cộng/trừ không mất thông tin.

```python
def recover_values(prefix):
    if not prefix:
        raise ValueError("Prefix phải có ít nhất P[0]")

    if prefix[0] != 0:
        raise ValueError("Prefix hợp lệ theo quy ước này cần P[0]=0")

    return [
        prefix[i + 1] - prefix[i]
        for i in range(len(prefix) - 1)
    ]


P = [0, 4, 3, 10, 12, 21, 24]
assert recover_values(P) == [4, -1, 7, 2, 9, 3]
assert recover_values([0]) == []
```

Đây là một cách kiểm tra bất biến rất hữu ích: **hiệu hai tổng tiền tố kề nhau chính là phần tử mới được thêm**.

### Đừng nhầm tiền tố với nén dữ liệu

Bảng `P` có n+1 phần tử, nhiều hơn mảng đầu một phần tử, nên nó **không tự là phương pháp nén**. Ta chấp nhận dùng thêm bộ nhớ để **đổi lấy tốc độ trả truy vấn**.

Trong số học dấu phẩy động, việc lấy hiệu hai số rất lớn và gần nhau có thể mất độ chính xác, nên khôi phục `a[i]` từ `P` không luôn cho đúng từng bit của dữ liệu gốc.

## 20. Số thực, số nguyên lớn và giả định phép toán O(1)

Các chứng minh tiền tố thường xét phép cộng trên số học chính xác. Trong chương trình thực tế, ta phải chú ý miền giá trị.

### Số nguyên có giới hạn bit

Ở ngôn ngữ dùng kiểu số nguyên kích thước cố định, tổng có thể **tràn** nếu các phần tử hoặc `n` lớn. Cần chọn kiểu đủ rộng hoặc có cơ chế kiểm tra tràn.

Python hỗ trợ `int` với độ chính xác tùy ý, tránh tràn theo bit cố định trong phép cộng thông thường, nhưng phép tính với số nguyên rất lớn có chi phí theo số chữ số. Mô hình O(1) cho mỗi phép cộng là **giả định về kích thước giá trị**, không phải chân lý bất kể độ dài số.

### Số thực dấu phẩy động

Phép cộng số thực ở máy có **sai số làm tròn**. Ví dụ cộng rất nhiều số lớn rồi trừ hai tiền tố gần nhau có thể gây **triệt tiêu số học (catastrophic cancellation)**.

```text
P[r] và P[l] rất lớn, nhưng tổng thật của [l,r) rất nhỏ.
Lấy hiệu hai số gần nhau có thể làm mất một phần chữ số có nghĩa.
```

Khi ứng dụng đòi độ chính xác tài chính hoặc tính toán khoa học, có thể cân nhắc:

- Lưu tiền theo **đơn vị nguyên nhỏ nhất** (ví dụ số xu) khi phù hợp.
- Dùng `Decimal` hoặc phân số với chính sách độ chính xác rõ ràng.
- Dùng phương pháp cộng ổn định số học hơn nếu cần.
- Nêu dung sai khi kiểm tra kết quả số thực, thay vì luôn so sánh `==` từng bit.

**Ví dụ mã trong bài chủ yếu dùng số nguyên** để tách rõ tính đúng đắn cấu trúc dữ liệu khỏi vấn đề làm tròn số thực.

### Tiền tố có thể giảm hoặc âm

Không phải mọi `P[i]` đều dương hoặc tăng. Với dữ liệu âm, ta có thể có `P[i+1]<P[i]`. Đây là hành vi **đúng**, không phải bảng prefix bị hỏng.

## 21. Điều gì làm công thức hiệu hai tiền tố đúng?

Có thể nhìn tổng tiền tố như một dạng **tổng hợp có phép nghịch đảo**.

Phép cộng số nguyên có:

- **Tính kết hợp:** có thể đổi cách đặt ngoặc khi cộng.
- **Phần tử đơn vị:** 0.
- **Nghịch đảo:** `-x`, nên có thể khử tổng tiền tố bên trái.

Vì vậy `P[r]-P[l]` hoạt động.

### Vì sao prefix min không tương đương?

Định nghĩa một bảng:

```text
M[k] = min(a[0:k])
```

Bảng min tiền tố không cho phép lấy **hiệu hai min** để suy ra min trên đoạn giữa. Phép min không có nghịch đảo tổng quát.

Ví dụ:

```text
a = [1, 9, 5]
b = [1, 7, 8]
```

Hai mảng có cùng dãy min tiền tố `1,1,1` (sau lần lượt 1,2,3 phần tử), nhưng:

```text
min(a[1:3]) = 5
min(b[1:3]) = 7
```

Không thể xác định hai kết quả khác nhau chỉ từ bảng min tiền tố giống nhau ấy.

### XOR là một trường hợp tương tự

Với XOR bit, mỗi giá trị là nghịch đảo của chính nó:

```text
x xor x = 0
```

Do đó:

```text
range_xor(l,r) = prefix_xor[r] xor prefix_xor[l]
```

Nhưng **bài toán tổng tiền tố** ở đây dựa trên cộng/trừ. Đừng tự suy rằng bất kỳ phép tổng hợp nào cũng có thể truy vấn đoạn bằng “lấy hiệu” nếu không chứng minh được phép nghịch đảo thích hợp.

## 22. Prefix sum 2D: mở rộng cho bảng số tĩnh

Nếu dữ liệu là ma trận `rows × cols`, câu hỏi có thể yêu cầu tổng trong một **hình chữ nhật**. Ta mở rộng ý tưởng từ 1D sang **prefix sum hai chiều**.

Đặt:

```text
S[r][c] = tổng các ô thuộc hàng [0,r), cột [0,c)
```

Tạo bảng kích thước `(rows+1) × (cols+1)`, trong đó hàng 0 và cột 0 bằng 0.

Công thức xây:

```text
S[r+1][c+1]
    = a[r][c]
    + S[r][c+1]
    + S[r+1][c]
    - S[r][c]
```

Với hình chữ nhật `[r1,r2) × [c1,c2)`:

```text
rect_sum
    = S[r2][c2]
    - S[r1][c2]
    - S[r2][c1]
    + S[r1][c1]
```

Dấu cộng cuối giúp **cộng lại vùng giao** đã bị trừ hai lần.

### Ví dụ

```text
Ma trận:

1   2   3   4
5   6   7   8
9  10  11  12

Hình chữ nhật [1,3) × [1,3) gồm:
6, 7, 10, 11

Tổng = 34
```

```python
def build_prefix_2d(matrix):
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0

    if any(len(row) != cols for row in matrix):
        raise ValueError("Ma trận phải có số cột đồng nhất")

    S = [[0] * (cols + 1) for _ in range(rows + 1)]

    for r in range(rows):
        for c in range(cols):
            S[r + 1][c + 1] = (
                matrix[r][c]
                + S[r][c + 1]
                + S[r + 1][c]
                - S[r][c]
            )

    return S


def rect_sum(S, r1, r2, c1, c2):
    rows = len(S) - 1
    cols = len(S[0]) - 1

    validate_range(rows, r1, r2)
    validate_range(cols, c1, c2)

    return S[r2][c2] - S[r1][c2] - S[r2][c1] + S[r1][c1]


matrix = [
    [1, 2, 3, 4],
    [5, 6, 7, 8],
    [9, 10, 11, 12],
]

S = build_prefix_2d(matrix)

assert rect_sum(S, 1, 3, 1, 3) == 34
assert rect_sum(S, 0, 3, 0, 4) == 78
assert rect_sum(S, 2, 2, 1, 3) == 0
```

Với dữ liệu không đổi, xây bảng tốn O(rows·cols) thời gian/bộ nhớ, và mỗi truy vấn hình chữ nhật tốn O(1).

Đây chỉ là **mở rộng ý tưởng tiền tố**: bản chất vẫn là lưu tổng trước để lấy hiệu/bao hàm–loại trừ khi truy vấn.

## 23. Quy trình quyết định có nên dùng prefix hay không

Khi gặp một bài toán tính tổng đoạn, hãy kiểm tra tuần tự:

1. **Dữ liệu có thực sự không đổi trong các truy vấn?** Nếu có cập nhật thường xuyên, prefix tĩnh có thể không phù hợp.
2. **Bài toán hỏi tổng trên đoạn liên tiếp hay một đại lượng khác?** Công thức hiệu hai tiền tố dành cho cộng/trừ, không tự thay thế cho min/max.
3. **Đầu vào đánh số từ 0 hay 1?** Chuyển về `[l,r)` 0-based một lần.
4. **Có cho phép đoạn rỗng không?** Tổng đoạn rỗng có thể trả 0; API phải công bố chính sách.
5. **Có bao nhiêu câu hỏi?** Nếu nhiều truy vấn, O(n) tiền xử lý có lợi.
6. **Kích thước và kiểu số thế nào?** Cần tránh tràn số nguyên hoặc sai số không chấp nhận được.
7. **Có cần lưu toàn bộ mảng nguồn không?** Nếu chỉ hỏi tổng, bảng `P` đủ để trả lời; nếu còn thao tác khác, cân nhắc giữ bản gốc.
8. **Làm thế nào kiểm tra tính đúng?** So sánh với cách quét trực tiếp trên những mảng nhỏ, đặc biệt ở các biên.

### Ma trận lựa chọn nhanh

| Kịch bản | Hướng tiếp cận |
|---|---|
| Một mảng nhỏ, vài truy vấn tổng | Cộng trực tiếp có thể đủ |
| Mảng lớn, nhiều truy vấn tổng, không cập nhật | **Prefix sum** |
| Mảng tĩnh, truy vấn tổng cửa sổ đủ loại độ dài | Prefix sum phù hợp |
| Mảng động, cập nhật một điểm và hỏi tổng đoạn | Cân nhắc Fenwick tree/segment tree |
| Mảng động, cập nhật cả đoạn và hỏi tổng | Cần thiết kế cập nhật đoạn thích hợp |
| Mảng tĩnh, nhiều truy vấn min/max | Prefix sum **không** giải quyết trực tiếp |
| Bảng số tĩnh, nhiều truy vấn tổng hình chữ nhật | Prefix sum **2D** |

**Lựa chọn cấu trúc là hệ quả của tập thao tác**, không phải của việc dữ liệu “là mảng” đơn thuần.

## 24. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Xây `P` chỉ có n phần tử rồi dùng `P[n]` | Vượt chỉ số ở truy vấn toàn mảng | Dùng **n+1** phần tử và `P[0]=0` |
| Hiểu `P[k]` là tổng đến `a[k]` | Lệch chỉ số ở công thức truy vấn | Ghi bất biến **tổng k phần tử đầu** |
| Dùng `P[r]-P[l-1]` cho `[l,r)` | Lấy thừa phần trước, có thể biên âm | Dùng **`P[r]-P[l]`** |
| Quên đổi chỉ số 1-based | Truy vấn lấy sai phần tử | `[L,R]` 1-based → `[L-1,R)` |
| Chuyển đổi 1-based hai lần | Lệch biên cả trái và phải | Chuẩn hóa biên đúng một lần |
| Coi biên `r` thuộc `[l,r)` | Cộng thừa phần tử cuối | Chỉ dùng chỉ số `l,...,r-1` |
| Coi `r=n` là không hợp lệ | Không hỏi được đoạn đến cuối | Cho phép `r=n` vì exclusive |
| Cho chỉ số âm theo Python | `P[-1]` âm thầm chọn phần tử cuối | Kiểm tra `0<=l<=r<=n` |
| Tự đảo biên nếu `l>r` | Thay đổi ý nghĩa yêu cầu sai | Báo lỗi nếu hợp đồng không cho phép |
| Trả `None` cho tổng đoạn rỗng | Không nhất quán với đơn vị cộng | Trả 0 theo quy ước của bài |
| Quên kiểm tra `l=r` trước khi tính average | Chia cho 0 | Trung bình rỗng báo lỗi |
| Cho rằng các prefix luôn không giảm | Sai khi có số âm | Không dùng tìm kiếm nhị phân nếu không đơn điệu |
| Dùng prefix cũ sau khi sửa mảng | Truy vấn trả số liệu lỗi thời | Rebuild hoặc chuyển sang cấu trúc động |
| Xây prefix lại cho mỗi truy vấn | Mất lợi ích tiền xử lý | Xây một lần, dùng lại cho mọi truy vấn |
| Dùng `sum(a[l:r])` rồi cho là O(1) | Thực tế O(r-l) và có bản sao slice | Phân biệt quét với đọc bảng |
| Dùng prefix min rồi “trừ” để lấy min đoạn | Min không có nghịch đảo | Dùng cấu trúc cho min |
| Bỏ qua kiểu số và tràn số | Tổng có thể sai | Chọn kiểu số/chính sách số phù hợp |
| Xem O(1) query là O(1) toàn bộ công việc | Bỏ qua O(n) xây bảng | Báo rõ **O(n+q)** cho q truy vấn |
| Không tính danh sách q đáp án | Thiếu O(q) bộ nhớ đầu ra | Phân tích riêng bảng và kết quả |

## 25. Câu hỏi tự luyện có lời giải

**Bài 1 — Định nghĩa tiền tố.** `P[k]` biểu thị điều gì nếu `P[0]=0`?

*Lời giải:* **Tổng của k phần tử đầu tiên** trong mảng, tức các chỉ số `0,...,k-1`.

**Bài 2 — Xây bảng.** Cho `a=[3,5,-2,4]`. Hãy viết `P`.

*Lời giải:* `P=[0,3,8,6,10]`. Mỗi lần thêm một phần tử, cộng giá trị ấy vào tổng trước đó.

**Bài 3 — Truy vấn.** Với `P` ở bài 2, tổng `[1,4)` là bao nhiêu?

*Lời giải:* `P[4]-P[1]=10-3=7`, đúng bằng `5+(-2)+4=7`.

**Bài 4 — Đoạn rỗng.** Với `P=[0,3,8,6,10]`, tổng `[3,3)` là bao nhiêu?

*Lời giải:* `P[3]-P[3]=6-6=0`.

**Bài 5 — Toàn mảng.** Với mảng `n` phần tử, truy vấn toàn bộ theo `[l,r)` là gì?

*Lời giải:* **`[0,n)`**, tổng bằng `P[n]-P[0]=P[n]`.

**Bài 6 — Chỉ số 1-based.** Đề hỏi tổng `[2,4]` 1-based trên `[3,5,-2,4]`. Quy đổi và tính đáp án.

*Lời giải:* Đổi thành **`[1,4)` 0-based**, tổng `5+(-2)+4=7`.

**Bài 7 — Số phần tử.** Đoạn `[2,7)` có bao nhiêu vị trí?

*Lời giải:* `7-2=5` phần tử, có chỉ số 2,3,4,5,6.

**Bài 8 — Độ dài bảng.** Mảng gốc 10 phần tử cần bao nhiêu giá trị tổng tiền tố?

*Lời giải:* **11** giá trị, tương ứng `P[0]` đến `P[10]`.

**Bài 9 — Kiểm tra biên.** Với `n=6`, `[6,6)` có hợp lệ không? `[6,7)` thì sao?

*Lời giải:* `[6,6)` là **đoạn rỗng hợp lệ** ở cuối. `[6,7)` **không hợp lệ** vì `r=7>n`.

**Bài 10 — Số âm.** Với `a=[5,-8,4,2,-1]`, `P` có bắt buộc tăng dần không? Tổng `[1,4)` là bao nhiêu?

*Lời giải:* **Không**; `P=[0,5,-3,1,3,2]`. Tổng `P[4]-P[1]=3-5=-2`.

**Bài 11 — Đánh đổi.** Có `n=100000` giá trị tĩnh và `q=100000` truy vấn tổng dài gần n. Chi phí O lớn của quét so với prefix là gì?

*Lời giải:* Quét có thể tốn **O(qn)**; prefix có chi phí **O(n+q)**, thêm O(n) bộ nhớ bảng.

**Bài 12 — Cập nhật.** Nếu `a[i]` tăng thêm `delta`, các giá trị tiền tố nào phải thay đổi?

*Lời giải:* Mọi `P[k]` có `k>i`, tức **`P[i+1],...,P[n]`**, đều tăng thêm `delta`.

**Bài 13 — Snapshot.** Tạo prefix từ mảng rồi sửa danh sách gốc. Có được dùng prefix cũ để hỏi mảng mới không?

*Lời giải:* **Không**. Prefix cũ mô tả **dữ liệu tại thời điểm xây**; cần rebuild hoặc sử dụng thiết kế cập nhật động.

**Bài 14 — Trung bình.** Với `a=[4,-1,7,2,9,3]`, trung bình đoạn `[2,5)` là bao nhiêu?

*Lời giải:* Tổng 18, độ dài 3, nên trung bình **6**.

**Bài 15 — Đếm số chẵn.** Với mảng trên, nếu tạo dãy cờ chẵn `[1,0,0,1,0,0]`, số chẵn trong `[0,5)` bằng bao nhiêu?

*Lời giải:* **2**, bằng hiệu hai tiền tố của dãy cờ.

**Bài 16 — Cửa sổ.** Với `n=6` và cửa sổ dài `k=3`, có bao nhiêu cửa sổ và tổng các cửa sổ của `[4,-1,7,2,9,3]` là gì?

*Lời giải:* Có `n-k+1=4` cửa sổ; tổng lần lượt **`10,8,18,14`**.

**Bài 17 — Khôi phục.** Nếu `P=[0,4,3,10,12,21,24]`, hãy suy ra `a[2]`.

*Lời giải:* `a[2]=P[3]-P[2]=10-3=7`.

**Bài 18 — Tổng mục tiêu.** Với `a=[1,2,1,2]`, có bao nhiêu đoạn con liên tiếp không rỗng có tổng 3?

*Lời giải:* **3** đoạn: vị trí `[0,2)`, `[1,3)` và `[2,4)`.

**Bài 19 — Bảng 2D.** Với ma trận ba hàng `[1,2,3,4]`, `[5,6,7,8]`, `[9,10,11,12]`, tổng hình chữ nhật `[1,3)×[1,3)` là bao nhiêu?

*Lời giải:* Các ô `6,7,10,11`; tổng **34**.

**Bài 20 — So sánh cấu trúc.** Vì sao tổng tiền tố rất phù hợp với dữ liệu tĩnh nhưng có thể kém hiệu quả khi cập nhật điểm thường xuyên?

*Lời giải:* Truy vấn chỉ cần O(1), nhưng cập nhật `a[i]` ảnh hưởng tới **mọi tiền tố từ `P[i+1]` trở đi**, có thể phải sửa O(n) giá trị.

**Bài 21 — Tính đúng đắn.** Hãy nêu một bất biến đủ để chứng minh công thức `P[r]-P[l]`.

*Lời giải:* `P[k]` luôn là tổng **k phần tử đầu**. Khi đó `P[r]` gồm tiền tố `P[l]` và phần cần hỏi `[l,r)`, nên lấy hiệu loại đúng phần đầu.

**Bài 22 — Chọn phương án.** Dãy tĩnh chỉ có một truy vấn `[l,r)` dài 3 trên mảng một triệu phần tử. Có bắt buộc xây prefix không?

*Lời giải:* **Không.** Quét ba phần tử tốn O(3), đơn giản và có thể rẻ hơn nhiều so với xây bảng O(n). Prefix chỉ có lợi khi khối lượng truy vấn đủ lớn hoặc có lý do tiền xử lý khác.

## 26. Tổng kết

**Mảng tổng tiền tố** thay một số lượng lớn phép cộng lặp lại bằng một lần tiền xử lý. Với dữ liệu `a` gồm `n` phần tử không đổi, xây:

```text
P[0] = 0
P[i+1] = P[i] + a[i]
```

rồi trả truy vấn **0-based nửa mở `[l,r)`** bằng:

```text
sum([l,r)) = P[r] - P[l]
```

Với giả định phép toán số có chi phí hằng số, **xây O(n) thời gian, O(n) bộ nhớ** và **mỗi truy vấn O(1) thời gian**; q truy vấn tốn tổng cộng O(n+q). Công thức đúng với cả **số âm, số 0 và đoạn rỗng**, miễn là các biên thỏa `0<=l<=r<=n`.

**Điều kiện quyết định là dữ liệu phải không đổi** trong suốt các truy vấn. Nếu mảng thay đổi, bảng `P` cũ mô tả dữ liệu cũ và cần xây lại hoặc thay bằng cấu trúc hỗ trợ cập nhật. Hãy luôn ghi rõ bất biến **“`P[k]` là tổng của k phần tử đầu”**, quy đổi chỉ số 1-based/0-based đúng một lần và kiểm tra các trường hợp `l=0`, `l=r`, `r=n` trước khi tối ưu.

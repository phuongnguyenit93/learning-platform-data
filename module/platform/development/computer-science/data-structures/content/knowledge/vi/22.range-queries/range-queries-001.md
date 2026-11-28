# Mô hình truy vấn trên đoạn và quy ước biên

Trong nhiều bài toán, dữ liệu không chỉ được hỏi **từng phần tử** mà còn được hỏi theo **một đoạn liên tiếp**: tổng doanh thu từ ngày thứ ba đến ngày thứ bảy, giá trị cảm biến nhỏ nhất trong 10 mẫu gần nhất, số lần xuất hiện sự kiện trong một khoảng thời gian, hay tổng điểm trên một phần của mảng.

Các yêu cầu ấy thuộc nhóm **truy vấn đoạn** (*range queries*). Trước khi chọn mảng cộng dồn, Fenwick tree hay segment tree, ta phải thống nhất ba điều:

1. **Đoạn gồm những vị trí nào?** Đầu trái/đầu phải có được tính không? Chỉ số bắt đầu từ 0 hay 1?
2. **Ta hỏi đại lượng gì?** Tổng, min, max, số lượng, XOR, ghép chuỗi hay một hàm tổng hợp khác?
3. **Dữ liệu có thay đổi không?** Không cập nhật, cập nhật một điểm, hay cập nhật nhiều phần tử trong một đoạn?

Nếu hiểu sai quy ước biên, cả thuật toán nhanh và mã đã tối ưu đều có thể trả **kết quả sai một phần tử**. Bài học này đặt nền tảng cho chương **Truy vấn đoạn** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, trong lộ trình học cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; trọng tâm là **bất biến**, **thao tác** và **độ phức tạp thời gian/bộ nhớ** để chọn cấu trúc phù hợp.

## 1. Truy vấn đoạn là gì?

Cho một dãy có `n` phần tử:

```text
a = [a[0], a[1], ..., a[n-1]]
```

Một **truy vấn đoạn** chỉ định hai biên `l` và `r`, sau đó tính một đại lượng từ các phần tử có chỉ số thuộc đoạn ấy. Với quy ước chuẩn của bài này là **chỉ số từ 0, đoạn nửa mở `[l, r)`**, những phần tử được xét là:

```text
a[l], a[l+1], ..., a[r-1]
```

Tức là **lấy đầu trái, không lấy đầu phải**. Điều kiện hợp lệ:

```text
0 <= l <= r <= n
```

Ví dụ dãy:

```text
Chỉ số:   0    1    2    3    4    5
Giá trị:  4   -1    7    2    9    3
```

Truy vấn `[2, 5)` chọn ba phần tử ở vị trí **2, 3, 4**, tương ứng **`[7, 2, 9]`**:

- Tổng đoạn: `7 + 2 + 9 = 18`.
- Giá trị nhỏ nhất: `2`.
- Giá trị lớn nhất: `9`.
- Số phần tử: `5 - 2 = 3`.

Một cặp biên giống nhau có thể dẫn đến những kết quả khác nhau nếu dùng quy ước khác. Vì thế, **quy ước biên là một phần của hợp đồng API**, không phải chi tiết trình bày phụ.

### Truy vấn trên đoạn khác truy vấn theo giá trị

Truy vấn đoạn chỉ số `[2, 5)` nói về **vị trí liên tiếp** trong dãy, không phải các phần tử có **giá trị** từ 2 đến 5. Nếu muốn hỏi mọi giá trị nằm trong khoảng `[2,5)` bất kể vị trí, đó là bài toán lọc theo giá trị hoặc truy vấn trên miền khóa, cần định nghĩa khác.

Ví dụ, trong dãy `[4,-1,7,2,9,3]`, đoạn chỉ số `[2,5)` chứa `7,2,9`; còn các giá trị thỏa `2 <= x < 5` là `4,2,3` ở những vị trí khác nhau.

## 2. Bốn cách viết biên và cách diễn giải

Có hai lựa chọn độc lập:

- **Cơ sở chỉ số:** phần tử đầu mang chỉ số **0** hay **1**?
- **Đầu phải:** được tính (**đoạn đóng**) hay không được tính (**đoạn nửa mở**)?

Các dạng thường gặp:

| Ký hiệu | Có lấy trái? | Có lấy phải? | Các vị trí khi chỉ số từ 0 |
|---|---|---|---|
| `[l, r)` | Có | Không | `l, ..., r-1` |
| `[l, r]` | Có | Có | `l, ..., r` |
| `(l, r]` | Không | Có | `l+1, ..., r` |
| `(l, r)` | Không | Không | `l+1, ..., r-1` |

Trong lập trình cấu trúc dữ liệu, hai quy ước rất phổ biến là **0-based `[l,r)`** và **1-based `[L,R]`**.

### 2.1. Đoạn nửa mở `[l, r)`, chỉ số bắt đầu từ 0

```text
a = [4, -1, 7, 2, 9, 3]
             ^  ^  ^
             2  3  4

[2,5) = [a[2], a[3], a[4]] = [7,2,9]
```

Điều kiện `0 <= l <= r <= n` cho phép `r = n`. Vì `r` **không được lấy**, không có lần đọc `a[n]`.

### 2.2. Đoạn đóng `[l, r]`, chỉ số bắt đầu từ 0

```text
[2,4] = [a[2], a[3], a[4]] = [7,2,9]
```

Nếu yêu cầu đoạn **không rỗng**, phải có `0 <= l <= r < n`. Độ dài là `r - l + 1`. Nếu muốn cho phép truy vấn rỗng, API đoạn đóng phải bổ sung quy ước riêng thay vì coi mọi cặp `l,r` đều hợp lệ.

### 2.3. Đoạn đóng `[L, R]`, chỉ số bắt đầu từ 1

Một số đề bài đánh số phần tử đầu tiên là **1**, nên:

```text
Vị trí 1-based: 1    2    3    4    5    6
Giá trị:       4   -1    7    2    9    3

[3,5] 1-based = [7,2,9] = [2,5) 0-based
```

Đây thường là quy ước của đề thi thuật toán. Không được lấy `a[L]` trong Python nếu `L` đã là chỉ số 1-based mà chưa đổi về 0-based.

## 3. Vì sao `[l,r)` thường thuận tiện hơn?

Chọn quy ước nội bộ **0-based nửa mở** đem lại nhiều tính chất đơn giản.

### 3.1. Độ dài đoạn bằng phép trừ biên

```text
length([l,r)) = r - l
```

Không cần cộng thêm 1. Với `[2,5)`, độ dài là `3`.

### 3.2. Đoạn rỗng được biểu diễn tự nhiên

```text
[l,l) = đoạn rỗng
```

Ví dụ `[0,0)`, `[3,3)` và `[n,n)` đều hợp lệ. Chúng không chứa phần tử nào.

### 3.3. Toàn bộ mảng có cùng dạng

```text
[0,n) = toàn bộ n phần tử
```

Kể cả với mảng rỗng `n=0`, đoạn toàn bộ là `[0,0)`.

### 3.4. Ghép hai đoạn kề nhau không chồng lấn

Với `l <= m <= r`:

```text
[l,r) = [l,m) nối tiếp [m,r)
```

Ví dụ:

```text
[1,5) gồm các chỉ số 1,2,3,4

[1,3) gồm 1,2
[3,5) gồm 3,4

Không bỏ sót, không đếm trùng chỉ số 3.
```

Đây là bất biến đặc biệt hữu ích khi chia đôi đoạn trong **segment tree** hoặc thuật toán chia để trị.

### 3.5. Tương thích trực tiếp với phép cắt Python

```python
a = [4, -1, 7, 2, 9, 3]

assert a[2:5] == [7, 2, 9]
assert a[0:len(a)] == a
assert a[3:3] == []
```

**Cảnh báo:** Python slicing mặc định còn hỗ trợ chỉ số âm và biên vượt mảng bằng cách tự điều chỉnh. Một API truy vấn đoạn nghiêm ngặt **không nên vô tình thừa hưởng** những hành vi ấy; ta sẽ kiểm tra biên trước.

## 4. Bảng chuyển đổi quy ước biên

Để tránh nhầm, hãy chuyển mọi truy vấn vào một dạng **`[l,r)` 0-based** trước khi gọi thuật toán nội bộ.

| Đầu vào | Điều kiện không rỗng | Chuyển sang `[l,r)` 0-based |
|---|---|---|
| 0-based `[l,r)` | `0 <= l < r <= n` | `[l,r)` |
| 0-based `[l,R]` | `0 <= l <= R < n` | `[l,R+1)` |
| 1-based `[L,R]` | `1 <= L <= R <= n` | `[L-1,R)` |
| 1-based `[L,R)` | `1 <= L < R <= n+1` | `[L-1,R-1)` |

Trong bảng, `R` được viết hoa khi nó là biên cuối **được lấy** hoặc là chỉ số 1-based, nhằm giảm nhầm lẫn. Quy tắc tương ứng:

```text
0-based inclusive [l,R]   -> half-open [l,R+1)
1-based inclusive [L,R]   -> half-open [L-1,R)
1-based half-open [L,R)   -> half-open [L-1,R-1)
```

Ví dụ:

```text
1-based [3,5] -> 0-based [2,5) -> giá trị [7,2,9]
0-based [2,4] -> 0-based [2,5) -> giá trị [7,2,9]
```

### Truy vấn rỗng khi chuyển đổi

Một truy vấn 0-based `[l,l)` là rỗng, nhưng **không có** cách biểu diễn bằng đoạn đóng không rỗng `[L,R]` với `L <= R`.

Nếu API đầu vào cho phép một đoạn đóng rỗng dưới quy ước riêng như `L=R+1`, phải diễn giải tường minh. Ví dụ `[L=4,R=3]` ở hệ 1-based được ánh xạ thành `[3,3)`; nhưng chỉ làm vậy nếu đề **chính thức cho phép**. Đừng tự ý hợp thức hóa mọi trường hợp `L > R`.

Đối với API học tập ở bài này, ta áp dụng:

- **Half-open:** cho phép rỗng khi `l=r`.
- **Closed:** chỉ chấp nhận **đoạn không rỗng** khi `L <= R`.
- Truy vấn ngoài miền hoặc đảo biên được **báo lỗi**, không tự sửa.

## 5. Hợp đồng hợp lệ và kiểm tra biên

Cho mảng có `n` phần tử, các truy vấn half-open được phép thỏa:

```text
0 <= l <= r <= n
```

Một số ví dụ:

| Truy vấn với `n=6` | Hợp lệ? | Số phần tử | Giải thích |
|---|---|---:|---|
| `[0,6)` | Có | 6 | Toàn mảng |
| `[2,5)` | Có | 3 | Các vị trí 2,3,4 |
| `[0,0)` | Có | 0 | Rỗng đầu mảng |
| `[6,6)` | Có | 0 | Rỗng cuối mảng |
| `[4,2)` | **Không** | — | Đảo biên trái/phải |
| `[-1,3)` | **Không** | — | Biên âm |
| `[2,7)` | **Không** | — | Vượt ngoài mảng |
| `[6,7)` | **Không** | — | Vị trí 6 không tồn tại |

Cần phân biệt **độ hợp lệ của đoạn** và **độ xác định của phép tổng hợp**. `[2,2)` là một đoạn hợp lệ, nhưng `min` trên đoạn rỗng có thể không được định nghĩa theo API, dù `sum` trên đoạn ấy hoàn toàn có nghĩa bằng 0.

### Python: kiểm tra biên chặt chẽ

```python
def validate_range(n, l, r):
    """Kiểm tra đoạn 0-based [l,r), cho phép đoạn rỗng."""
    if type(l) is not int or type(r) is not int:
        raise TypeError("l và r phải là số nguyên")

    if not 0 <= l <= r <= n:
        raise IndexError("Đoạn [l,r) nằm ngoài miền hợp lệ")

    return r - l


assert validate_range(6, 2, 5) == 3
assert validate_range(6, 6, 6) == 0

for l, r in [(-1, 3), (4, 2), (2, 7)]:
    try:
        validate_range(6, l, r)
    except IndexError:
        pass
    else:
        raise AssertionError("Phải từ chối biên sai")

try:
    validate_range(6, True, 2)
except TypeError:
    pass
else:
    raise AssertionError("Boolean không phải biên nguyên hợp lệ")
```

Dùng `type(x) is int` trong ví dụ nhằm từ chối `True`/`False` dù Python xem `bool` là lớp con của `int`. Đây là lựa chọn thiết kế API nghiêm ngặt; một hệ thống khác có thể đặt chính sách kiểu số nguyên khác.

## 6. Mô hình dữ liệu tĩnh và dữ liệu thay đổi

Hãy phân biệt **query** (đọc/tổng hợp) với **update** (thay đổi).

| Loại thao tác | Diễn giải | Ví dụ |
|---|---|---|
| `range_query(l,r)` | Trả thông tin của `a[l:r]` | Tổng, min, max của đoạn |
| `point_assign(i,x)` | Gán `a[i] = x` | Sửa điểm thứ i thành 10 |
| `point_add(i,delta)` | Cộng thêm `delta` vào `a[i]` | Tăng điểm thứ i lên 5 |
| `range_add(l,r,delta)` | Cộng `delta` vào mọi phần tử trong `[l,r)` | Tăng cả đoạn thêm 5 |
| `range_assign(l,r,x)` | Gán mọi phần tử trong đoạn bằng `x` | Đặt tất cả phần tử đoạn thành 0 |

Đừng nhầm **point_assign** và **point_add**. Ví dụ nếu `a[3]=2`, gán 5 đưa giá trị thành 5; cộng 5 đưa giá trị thành 7.

Một bộ truy vấn có thể là:

- **Tĩnh (static):** mảng không thay đổi; thực hiện nhiều truy vấn.
- **Động (dynamic):** xen kẽ truy vấn với cập nhật.
- **Offline:** biết trước toàn bộ truy vấn/cập nhật, có thể sắp xếp hoặc tiền xử lý theo lô.
- **Online:** phải trả lời từng truy vấn trước khi thấy các thao tác tiếp theo.

Một cấu trúc rất nhanh cho dữ liệu tĩnh có thể không phù hợp khi có **cập nhật thường xuyên**. Đây là lý do phải xác định **tập thao tác** trước khi chọn thuật toán.

## 7. Tổng hợp trên đoạn: từ cộng đến phép toán kết hợp

Truy vấn đoạn thường có dạng:

```text
Q(l,r) = a[l] ⊕ a[l+1] ⊕ ... ⊕ a[r-1]
```

Trong đó `⊕` là một phép kết hợp thông tin. Một số lựa chọn:

| Phép tổng hợp | `⊕` | Ví dụ trên `[7,2,9]` | Phần tử đơn vị nếu có |
|---|---|---:|---|
| Tổng | `+` | `18` | `0` |
| Tích | `*` | `126` | `1` |
| Min | `min` | `2` | `+∞` (mô hình số có vô cực) |
| Max | `max` | `9` | `-∞` |
| XOR bit | `xor` | `7 xor 2 xor 9 = 12` | `0` |
| GCD số nguyên | `gcd` | `gcd(7,2,9)=1` | `0` theo quy ước |
| Đếm phần tử | Cộng các giá trị chỉ báo `1` | `3` | `0` |
| Ghép chuỗi | Nối theo thứ tự | `"729"` | Chuỗi rỗng `""` |

Với `min` và `max`, phần tử đơn vị ±∞ tiện cho thuật toán, nhưng một **API công khai** vẫn có thể quy định rằng **min/max trên đoạn rỗng báo lỗi**, vì không có phần tử nào để trả về.

### Tính kết hợp

Phép `⊕` có tính **kết hợp** (*associative*) nếu:

```text
(x ⊕ y) ⊕ z = x ⊕ (y ⊕ z)
```

Ví dụ phép cộng, min, max, gcd, XOR và phép ghép chuỗi đều kết hợp (với cách hiểu toán học phù hợp).

Tính kết hợp cho phép chia `[l,r)` thành `[l,m)` và `[m,r)`, tính hai kết quả rồi ghép:

```text
Q(l,r) = Q(l,m) ⊕ Q(m,r)
```

Đây là nền tảng của cây phân đoạn và nhiều cấu trúc tổng hợp đoạn.

### Phần tử đơn vị và đoạn rỗng

Một giá trị `e` là **phần tử đơn vị** (*identity*) nếu:

```text
e ⊕ x = x
x ⊕ e = x
```

Khi có đơn vị, ta có thể định nghĩa:

```text
Q(l,l) = e
```

Cặp `(⊕, e)` có tính kết hợp và đơn vị là cấu trúc đại số gọi là **monoid**. Tên gọi không bắt buộc phải nhớ ngay, nhưng hai tính chất **kết hợp + phần tử đơn vị** giải thích vì sao những thuật toán gộp đoạn hoạt động.

**Tính giao hoán không bắt buộc.** Phép ghép chuỗi không giao hoán: `"AB" + "CD"` khác `"CD" + "AB"`. Một cấu trúc truy vấn đoạn tổng quát phải **giữ thứ tự trái rồi phải** nếu phép gộp không giao hoán.

### Phép toán không kết hợp: cẩn thận

Phép trừ thông thường không kết hợp:

```text
(10 - 4) - 2 = 4
10 - (4 - 2) = 8
```

Vì vậy không được tùy tiện đưa phép trừ lặp vào một segment tree tổng hợp như thể nó có thể gộp hai đoạn theo mọi cách. Nếu muốn một truy vấn có phép toán phụ thuộc vào thứ tự ngoặc, phải mô tả **chính xác thứ tự tính** hoặc thiết kế bản tóm tắt khác có phép gộp kết hợp.

## 8. Cách trực tiếp: quét từng phần tử trong đoạn

Cách đơn giản nhất để trả lời `range_sum(l,r)` là cộng lần lượt `a[l]` đến `a[r-1]`.

```python
def range_sum_scan(a, l, r):
    validate_range(len(a), l, r)

    total = 0
    for i in range(l, r):
        total += a[i]
    return total


def range_min_scan(a, l, r):
    validate_range(len(a), l, r)

    if l == r:
        raise ValueError("min của đoạn rỗng không được định nghĩa")

    answer = a[l]
    for i in range(l + 1, r):
        if a[i] < answer:
            answer = a[i]
    return answer


a = [4, -1, 7, 2, 9, 3]

assert range_sum_scan(a, 2, 5) == 18
assert range_sum_scan(a, 0, 6) == 24
assert range_sum_scan(a, 3, 3) == 0
assert range_min_scan(a, 2, 5) == 2

try:
    range_min_scan(a, 4, 4)
except ValueError:
    pass
else:
    raise AssertionError("min trên đoạn rỗng phải báo lỗi")
```

**Độ phức tạp:**

- Mỗi truy vấn tổng/min quét `k=r-l` phần tử, nên **O(k)**; trường hợp xấu nhất O(n).
- Bộ nhớ phụ cho biến đếm/kết quả là **O(1)**, không tính mảng đầu vào.
- `point_assign` trực tiếp lên mảng là O(1).
- `range_add` trực tiếp lên k phần tử tốn O(k).

Ưu điểm là mã **rõ ràng, dễ kiểm chứng** và cập nhật dữ liệu không làm hỏng cấu trúc phụ trợ. Với mảng nhỏ hoặc số lượng truy vấn ít, cách này có thể đủ tốt.

## 9. Mảng cộng dồn: tối ưu nhiều truy vấn tổng tĩnh

Nếu mảng **không đổi** và có nhiều truy vấn tổng, ta có thể tiền xử lý **prefix sum** (*mảng tổng tiền tố*).

Định nghĩa:

```text
P[0] = 0
P[i+1] = P[i] + a[i]       với 0 <= i < n
```

Nói cách khác:

```text
P[k] = a[0] + a[1] + ... + a[k-1]
```

**Bất biến quan trọng:** `P[k]` là tổng **k phần tử đầu tiên**, không phải nhất thiết là tổng kết thúc ở chỉ số k.

Với:

```text
a:         4   -1    7    2    9    3
Chỉ số a:  0    1    2    3    4    5

P:         0    4    3   10   12   21   24
Chỉ số P:  0    1    2    3    4    5    6
```

Mảng `P` có **n+1 phần tử**.

### Công thức truy vấn

Với đoạn `[l,r)`:

```text
P[r] = a[0] + ... + a[l-1] + a[l] + ... + a[r-1]
P[l] = a[0] + ... + a[l-1]

range_sum(l,r) = P[r] - P[l]
```

Ví dụ:

```text
sum([2,5)) = P[5] - P[2]
            = 21 - 3
            = 18
```

Và:

```text
sum([0,6)) = P[6] - P[0] = 24 - 0 = 24
sum([3,3)) = P[3] - P[3] = 10 - 10 = 0
```

Đây là một lý do lớn để chọn đoạn nửa mở: **hai biên được dùng trực tiếp làm chỉ số trong P**, không cần điều chỉnh `+1` ở mỗi truy vấn.

## 10. Python: prefix sum và kiểm tra đồng nhất

Ta xây một đối tượng **snapshot tĩnh**: dữ liệu đầu vào được sao chép thành `tuple` để các thay đổi bên ngoài không làm tiền tố trở nên lỗi thời.

```python
class StaticRangeSum:
    def __init__(self, values):
        self._data = tuple(values)
        self._prefix = [0]

        for value in self._data:
            self._prefix.append(self._prefix[-1] + value)

    def __len__(self):
        return len(self._data)

    def query(self, l, r):
        validate_range(len(self._data), l, r)
        return self._prefix[r] - self._prefix[l]


raw = [4, -1, 7, 2, 9, 3]
rs = StaticRangeSum(raw)

assert rs.query(2, 5) == 18
assert rs.query(0, 6) == 24
assert rs.query(3, 3) == 0
assert rs.query(6, 6) == 0

raw[2] = 100                 # Thay đổi danh sách bên ngoài.
assert rs.query(2, 5) == 18 # Snapshot vẫn giữ giá trị cũ.

empty = StaticRangeSum([])
assert empty.query(0, 0) == 0
```

**Độ phức tạp** khi các phép cộng/trừ trên giá trị có chi phí hằng số:

- Xây `P`: **O(n) thời gian**.
- Bộ nhớ `P`: **O(n)**; snapshot `tuple` thêm O(n).
- Mỗi `query(l,r)`: **O(1) thời gian**.
- Nếu dữ liệu bên trong thật sự thay đổi, một bảng tiền tố đã xây **không tự cập nhật**.

### Phải làm gì khi có cập nhật?

Nếu ta gán `a[i]=x`, giá trị `P[k]` sẽ thay đổi với **mọi `k > i`**. Do đó, duy trì tiền tố bằng cách sửa trực tiếp có thể tốn O(n) mỗi lần cập nhật.

Có thể **xây lại** prefix sau khi cập nhật O(n), hoặc chuyển sang một cấu trúc hỗ trợ cập nhật hiệu quả hơn. Không được tiếp tục dùng prefix cũ để truy vấn mảng mới mà không có quy tắc cập nhật.

## 11. Chuyển các công thức tổng giữa 0-based và 1-based

Cách dễ nhất là **chuẩn hóa trước về `[l,r)` 0-based**:

```text
Đầu vào 1-based [L,R] inclusive
      -> l = L - 1
      -> r = R

Đáp án = P[R] - P[L-1]
```

Ví dụ trên mảng sáu phần tử:

```text
1-based [3,5]
= các giá trị 7,2,9

P[5] - P[2]
= 21 - 3
= 18
```

Với 0-based **đóng** `[l,R]`:

```text
sum_closed(l,R) = P[R+1] - P[l]
```

### Hàm chuyển quy ước 1-based đóng

```python
def inclusive_1based_to_halfopen(n, L, R):
    if type(L) is not int or type(R) is not int:
        raise TypeError("Biên phải là số nguyên")
    if not 1 <= L <= R <= n:
        raise IndexError("Đoạn 1-based [L,R] không hợp lệ")
    return (L - 1, R)


def sum_1based_inclusive(rs, L, R):
    l, r = inclusive_1based_to_halfopen(len(rs), L, R)
    return rs.query(l, r)


assert sum_1based_inclusive(rs, 3, 5) == 18
assert sum_1based_inclusive(rs, 1, 6) == 24
assert sum_1based_inclusive(rs, 6, 6) == 3
```

**Không đổi biên hai lần.** Nếu `L,R` đã được chuyển về `l=L-1, r=R`, các hàm phía dưới phải nhận đúng `[l,r)`, không tiếp tục thêm 1 vào `r`.

## 12. Cập nhật một điểm và cập nhật cả đoạn

Khi có cập nhật, phải định nghĩa rõ những phần tử nào thay đổi.

Ví dụ ban đầu:

```text
a = [4, -1, 7, 2, 9, 3]
```

### Cập nhật điểm

Gán `a[3]=10`:

```text
Trước: [4, -1, 7,  2, 9, 3]
Sau:   [4, -1, 7, 10, 9, 3]

sum([2,5)) trước =  7 + 2 + 9 = 18
sum([2,5)) sau   =  7 +10 + 9 = 26
```

Cộng `delta` tại một điểm thì khác gán:

```text
point_add(3, 5):
  a[3] từ 2 thành 7

point_assign(3, 5):
  a[3] từ 2 thành 5
```

### Cập nhật đoạn

Cộng `5` vào đoạn `[1,4)`, tức các vị trí `1,2,3`:

```text
Trước: [4, -1,  7, 2, 9, 3]
Sau:   [4,  4, 12, 7, 9, 3]
               ^  ^  ^
            vị trí 1,2,3 đã cộng 5
```

Tổng đoạn `[1,4)` trước là `-1+7+2=8`; sau là `4+12+7=23`. Vì đoạn có ba phần tử, tổng tăng đúng `3*5=15`.

### Python: mô hình trực tiếp có cập nhật

```python
class MutableRangeArray:
    def __init__(self, values):
        self.data = list(values)

    def _validate_index(self, i):
        if type(i) is not int or not 0 <= i < len(self.data):
            raise IndexError("Chỉ số cập nhật không hợp lệ")

    def point_assign(self, i, value):
        self._validate_index(i)
        self.data[i] = value

    def point_add(self, i, delta):
        self._validate_index(i)
        self.data[i] += delta

    def range_add(self, l, r, delta):
        validate_range(len(self.data), l, r)
        for i in range(l, r):
            self.data[i] += delta

    def range_sum(self, l, r):
        return range_sum_scan(self.data, l, r)


m = MutableRangeArray([4, -1, 7, 2, 9, 3])

m.point_assign(3, 10)
assert m.range_sum(2, 5) == 26

m.point_add(3, -8)
assert m.data[3] == 2

m.range_add(1, 4, 5)
assert m.data == [4, 4, 12, 7, 9, 3]
assert m.range_sum(1, 4) == 23

m.range_add(2, 2, 999)
assert m.data == [4, 4, 12, 7, 9, 3]
```

API này dễ kiểm tra nhưng `range_add` tốn **O(r-l)** thời gian và `range_sum` tốn **O(r-l)**. Khi có rất nhiều thao tác, ta cần tìm cấu trúc dữ liệu hỗ trợ loại update/query mong muốn hiệu quả hơn.

## 13. Phân biệt hai mục tiêu tối ưu: nhiều query hay nhiều update?

Ta có thể đo khối lượng công việc bằng:

- `n`: số phần tử mảng.
- `q`: số truy vấn.
- `u`: số cập nhật.
- `k`: độ dài một đoạn truy vấn/cập nhật cụ thể.

Một mảng thường với quét trực tiếp:

```text
Chi phí xấp xỉ:
    tổng độ dài q đoạn truy vấn
  + tổng độ dài các đoạn cập nhật
  + số cập nhật điểm
```

Nếu tất cả truy vấn đều có độ dài gần `n`, thời gian là O(qn).

Với **mảng tĩnh + prefix sum**:

```text
Xây prefix: O(n)
q lần query sum: O(q)
Tổng: O(n+q)
```

Nhưng với cập nhật thường xuyên, prefix cần được cập nhật hoặc xây lại. Cấu trúc tối ưu cho truy vấn tổng tĩnh không tự tối ưu cho truy vấn sau cập nhật.

### Tối ưu cập nhật đoạn bằng mảng hiệu (difference array)

Nếu có nhiều thao tác **cộng vào đoạn**, nhưng **chỉ cần giá trị cuối cùng** sau khi cập nhật hết, có thể dùng **mảng hiệu**.

Với `range_add(l,r,delta)` trên `[l,r)`, ghi:

```text
diff[l] += delta
diff[r] -= delta
```

Sau đó cộng dồn `diff` để biết lượng tăng tại từng vị trí. Độ dài `diff` thường là `n+1` để vị trí `r=n` vẫn hợp lệ.

Ví dụ:

```python
def apply_range_adds(a, updates):
    n = len(a)
    diff = [0] * (n + 1)

    for l, r, delta in updates:
        validate_range(n, l, r)

        if l == r:
            continue  # Đoạn rỗng không thay đổi gì.

        diff[l] += delta
        diff[r] -= delta

    result = list(a)
    running = 0

    for i in range(n):
        running += diff[i]
        result[i] += running

    return result


a = [4, -1, 7, 2, 9, 3]

assert apply_range_adds(a, [(1, 4, 5)]) == [4, 4, 12, 7, 9, 3]
assert apply_range_adds(a, [(1, 4, 5), (2, 5, -2)]) == [
    4, 4, 10, 5, 7, 3
]
```

Mỗi cập nhật đoạn có thể ghi O(1) vào `diff`; dựng dãy cuối tốn O(n). **Mảng hiệu không tự trả lời mọi truy vấn tổng online trong O(1)** khi còn cập nhật chưa được materialize; nó phù hợp nhất với xử lý theo lô, có thể thay đổi thiết kế nếu cần thao tác online.

### So sánh theo thao tác thường gặp

| Cấu trúc/ý tưởng | Xây dựng | Tổng đoạn | Cập nhật một điểm | Cộng cả đoạn | Phù hợp |
|---|---:|---:|---:|---:|---|
| Mảng + quét | O(1) thêm ngoài dữ liệu | O(k) | O(1) | O(k) | Ít thao tác, đơn giản |
| Prefix sum tĩnh | O(n) | **O(1)** | O(n) để duy trì/rebuild prefix | O(n) trong cách trực tiếp | Nhiều truy vấn, không đổi |
| Mảng hiệu theo lô | O(n) bộ nhớ/khởi tạo | Không hỗ trợ trực tiếp hiệu quả khi chưa dựng kết quả | Có thể ghi hiệu theo quy ước | **O(1)** mỗi update | Nhiều cập nhật, xuất cuối |
| Fenwick tree cho tổng | O(n) có cách xây tuyến tính | O(log n) | **O(log n)** dạng cộng điểm | Cần biến thể riêng | Tổng + cộng điểm |
| Segment tree cơ bản | O(n) | O(log n) | **O(log n)** | Cần lazy propagation hoặc biến thể | Truy vấn/cập nhật hỗn hợp |
| Sparse table cho min tĩnh | O(n log n) | **O(1)** min (idempotent) | Không thiết kế để cập nhật | Không | Nhiều min tĩnh |

Bảng chỉ nêu **các cách sử dụng điển hình**, không phải mọi biến thể nâng cao. Ví dụ Fenwick có thể hỗ trợ một số loại cập nhật đoạn bằng cấu trúc bổ sung; segment tree có thể hỗ trợ nhiều phép tổng hợp nếu thiết kế phép gộp và cập nhật phù hợp.

**Quan trọng:** trước khi chọn cấu trúc, hãy xác định **query loại gì** và **update loại gì**. Không thể suy từ tên “range query” rằng cấu trúc nào cũng hỗ trợ mọi phép toán và cập nhật với cùng chi phí.

## 14. Bất biến với đoạn liền nhau và chia để trị

Giả sử một phép gộp `⊕` có tính kết hợp và phần tử đơn vị `e`. Định nghĩa:

```text
Q(l,l) = e
Q(l,r) = a[l] ⊕ ... ⊕ a[r-1]   khi l < r
```

Với mọi `l <= m <= r`:

```text
Q(l,r) = Q(l,m) ⊕ Q(m,r)
```

### Chứng minh trực quan

Các chỉ số trong `[l,r)` được chia thành hai tập rời nhau:

```text
{l, ..., m-1}  và  {m, ..., r-1}
```

Hai phần này không trùng nhau và hợp lại là toàn đoạn. Vì `⊕` có tính kết hợp, ta có thể gộp lần lượt kết quả hai đoạn **đúng thứ tự trái trước phải**.

### Khi mảng có số lượng phần tử lẻ

Giả sử cần chia `[0,5)`. Chọn:

```text
mid = (0 + 5) // 2 = 2

Trái: [0,2)  -> 2 phần tử
Phải: [2,5)  -> 3 phần tử
```

Không có phần tử nào ở `mid` được đếm hai lần. Đây là lý do nhiều thuật toán cây phân đoạn dùng khoảng nửa mở.

### Các trường hợp m= l hoặc m= r

Nếu `m=l` thì đoạn trái `[l,l)` rỗng; nếu `m=r` thì đoạn phải `[r,r)` rỗng. Nhờ đơn vị `e`, công thức vẫn đúng:

```text
Q(l,l) ⊕ Q(l,r) = e ⊕ Q(l,r) = Q(l,r)
```

Khả năng có đoạn rỗng giúp viết đệ quy và xử lý biên **nhất quán**, không cần “nhánh ngoại lệ” cho mọi trường hợp chia.

## 15. Một giao diện tổng hợp chung bằng phép gộp

Ta có thể viết một hàm quét đoạn nhận:

- `op`: phép gộp kết hợp.
- `identity`: phần tử đơn vị.
- `[l,r)`: đoạn cần tổng hợp.

```python
def range_fold(a, l, r, op, identity):
    validate_range(len(a), l, r)

    result = identity
    for i in range(l, r):
        result = op(result, a[i])

    return result


a = [4, -1, 7, 2, 9, 3]

assert range_fold(a, 2, 5, lambda x, y: x + y, 0) == 18
assert range_fold(a, 2, 5, min, float("inf")) == 2
assert range_fold(a, 2, 2, lambda x, y: x + y, 0) == 0

words = ["ab", "cd", "ef", "gh"]
assert range_fold(words, 1, 4, lambda x, y: x + y, "") == "cdefgh"
assert range_fold(words, 3, 3, lambda x, y: x + y, "") == ""
```

Hàm này **không tự kiểm tra** `op` có tính kết hợp hoặc `identity` thực sự là đơn vị. Đó là **hợp đồng người gọi phải bảo đảm** khi dùng nó làm nền tảng để chia/gộp đoạn bằng cấu trúc cao cấp.

Ngay cả khi `op` không kết hợp, vòng quét trái sang phải vẫn tạo ra **một kết quả theo quy tắc ngoặc trái** cụ thể. Nhưng một segment tree thay đổi cách đặt ngoặc có thể cho kết quả khác, nên không thể áp dụng lập luận gộp đoạn tổng quát nếu thiếu tính kết hợp.

## 16. Vì sao prefix sum không áp dụng y nguyên cho mọi phép gộp?

Prefix sum hoạt động vì có thể **loại bỏ phần trước biên trái**:

```text
sum([l,r)) = P[r] - P[l]
```

Đây là phép nghịch đảo của phép cộng. Với XOR, tính chất tương tự là:

```text
prefix_xor[k] = a[0] xor ... xor a[k-1]

xor([l,r)) = prefix_xor[r] xor prefix_xor[l]
```

Bởi `x xor x = 0`.

Nhưng với **min**:

```text
prefix_min[k] = min(a[0],...,a[k-1])
```

không có phép “trừ min của tiền tố” để suy ra min của một đoạn bất kỳ.

Ví dụ:

```text
a = [1, 9, 5]
b = [1, 7, 8]

prefix_min của cả hai đều là [1,1,1] sau ba bước.
Nhưng min([1,3)) trên a là min(9,5)=5;
min([1,3)) trên b là min(7,8)=7.
```

Cùng bảng prefix min nhưng kết quả đoạn khác nhau, nên **chỉ prefix min không chứa đủ thông tin** để trả lời mọi truy vấn min tùy ý.

### Tổng quát hơn

- **Phép có nghịch đảo thích hợp** như cộng trên số nguyên hoặc XOR có thể hỗ trợ cách lấy “tiền tố phải trừ/khử tiền tố trái”.
- **Phép kết hợp không có nghịch đảo** như min/max/gcd thường cần ý tưởng khác, chẳng hạn segment tree hoặc sparse table trong những điều kiện phù hợp.
- Với phép **không giao hoán**, phải còn xem xét **chiều áp dụng nghịch đảo**; không được tự động dùng `P[r] - P[l]` theo đúng nghĩa số học.

Đây là một kết nối quan trọng giữa **định nghĩa phép truy vấn** và **lựa chọn cấu trúc dữ liệu**.

## 17. Bài toán cửa sổ trượt và quy ước biên

Cửa sổ liên tiếp độ dài `k` bắt đầu ở vị trí `i` được viết gọn:

```text
[i, i+k)
```

Nếu `1 <= k <= n`, các vị trí bắt đầu hợp lệ là:

```text
i = 0, 1, ..., n-k
```

Có tổng cộng **`n-k+1` cửa sổ**.

Ví dụ `n=6, k=3`:

| Cửa sổ | Vị trí | Giá trị | Tổng |
|---|---|---|---:|
| `[0,3)` | 0,1,2 | `4,-1,7` | 10 |
| `[1,4)` | 1,2,3 | `-1,7,2` | 8 |
| `[2,5)` | 2,3,4 | `7,2,9` | 18 |
| `[3,6)` | 3,4,5 | `2,9,3` | 14 |

Nếu bài toán cho `k=0`, về mặt đoạn nửa mở có **n+1** cửa sổ rỗng `[i,i)` với `0<=i<=n`. Tuy nhiên nhiều đề bài về cửa sổ trượt chỉ cho phép **k>=1**; đừng tự chấp nhận `k=0` nếu hợp đồng không nói vậy.

### Python: mọi tổng cửa sổ bằng prefix

```python
def sliding_sums(values, k):
    n = len(values)
    if type(k) is not int or not 1 <= k <= n:
        raise ValueError("Yêu cầu 1 <= k <= n")

    rs = StaticRangeSum(values)
    return [rs.query(i, i + k) for i in range(n - k + 1)]


assert sliding_sums([4, -1, 7, 2, 9, 3], 3) == [
    10, 8, 18, 14
]
```

Một cách khác là duy trì tổng cửa sổ bằng việc **trừ phần tử rời cửa sổ, cộng phần tử vào**, cũng O(n) thời gian cho tất cả cửa sổ. Nếu cần max/min cửa sổ và muốn hiệu quả O(n), có thể dùng **deque đơn điệu**, nhưng đó là một cấu trúc truy vấn khác với prefix sum.

## 18. Từ chỉ số mảng đến khoảng thời gian

Trong ứng dụng thực tế, “đoạn” đôi khi là khoảng **thời gian** thay vì cặp chỉ số. Quy ước nửa mở cũng rất hữu ích:

```text
[start, end) = các sự kiện có thời điểm t thỏa
               start <= t < end
```

Nếu phân ngày thành hai kỳ liên tiếp:

```text
[08:00, 09:00)
[09:00, 10:00)
```

sự kiện đúng **09:00** thuộc kỳ thứ **hai**, không được đếm trùng.

Với các timestamp đã được sắp không giảm, ta có thể đổi khoảng thời gian thành khoảng chỉ số bằng **tìm kiếm nhị phân**:

```python
from bisect import bisect_left


def time_range_indices(sorted_times, start, end):
    if start > end:
        raise ValueError("Khoảng thời gian đảo biên")

    l = bisect_left(sorted_times, start)
    r = bisect_left(sorted_times, end)
    return (l, r)


times = [10, 12, 12, 15, 18, 20]

assert time_range_indices(times, 12, 18) == (1, 4)
# Các sự kiện được chọn có thời điểm 12, 12, 15.
assert time_range_indices(times, 13, 13) == (3, 3)
```

`bisect_left` tìm vị trí đầu tiên có giá trị **không nhỏ hơn** biên, nên xử lý đúng cả khi nhiều sự kiện cùng timestamp. Sau khi nhận `[l,r)`, ta có thể hỏi số sự kiện `r-l` hoặc tổng một trường số theo index tương ứng.

**Lưu ý:** hàm chỉ đúng khi `sorted_times` đã được sắp xếp và `start/end` cùng kiểu so sánh. Với thời gian thực tế, phải thống nhất cách biểu diễn múi giờ; không nên so trực tiếp các mốc thời gian trộn lẫn quy ước.

## 19. Truy vấn hình chữ nhật hai chiều: mở rộng tự nhiên

Quy ước nửa mở còn dùng được với ma trận `rows × cols`.

Một hình chữ nhật chỉ số:

```text
[row_lo,row_hi) × [col_lo,col_hi)
```

chứa các ô có:

```text
row_lo <= row < row_hi
col_lo <= col < col_hi
```

Số ô là:

```text
(row_hi - row_lo) * (col_hi - col_lo)
```

Ví dụ ma trận:

```text
      c0  c1  c2  c3
r0     1   2   3   4
r1     5   6   7   8
r2     9  10  11  12
```

Hình chữ nhật `[1,3) × [1,3)` chứa `6,7,10,11`; tổng là `34`. Ở biên hai chiều, nguyên tắc “lấy trái/trên, bỏ phải/dưới” giúp chia các ô không chồng lấn.

Để tính nhanh tổng nhiều hình chữ nhật tĩnh, có thể dùng **prefix sum 2D** với bảng kích thước `(rows+1) × (cols+1)` và nguyên lý cộng–trừ giao nhau. Đây là mở rộng từ mô hình 1D, chưa cần đi sâu để hiểu bản chất quy ước biên.

## 20. Chứng minh tính đúng của prefix sum theo quy ước đã chọn

Định nghĩa:

```text
P[0] = 0
P[k+1] = P[k] + a[k]
```

Ta chứng minh bằng quy nạp:

> Với mọi `k` từ 0 đến `n`, `P[k]` bằng tổng các phần tử thuộc `[0,k)`.

**Cơ sở:** `k=0`, đoạn `[0,0)` rỗng, tổng bằng `0` theo phần tử đơn vị.

**Bước quy nạp:** giả sử `P[k] = sum(a[0:k])`. Khi thêm phần tử `a[k]`:

```text
P[k+1] = P[k] + a[k]
       = sum(a[0:k]) + a[k]
       = sum(a[0:k+1])
```

Vậy bất biến đúng với mọi `k`.

Từ đó, tổng `[l,r)` là hiệu hai tổng tiền tố:

```text
sum(a[l:r])
  = sum(a[0:r]) - sum(a[0:l])
  = P[r] - P[l]
```

Chứng minh bao phủ cả:

- `l=0`: trừ `P[0]=0`.
- `r=n`: dùng `P[n]`, có tồn tại vì `P` dài `n+1`.
- `l=r`: hai tổng tiền tố bằng nhau, đáp án bằng 0.

Nếu ai đó lỡ tính `P[i]` là “tổng đến và gồm `a[i]`”, công thức trên **không còn đúng như viết**. Vì vậy, hãy **ghi rõ bất biến P[k] là tổng k phần tử đầu** ngay từ lúc xây dựng.

## 21. Lỗi thường gặp khi thiết kế truy vấn đoạn

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Coi `[l,r)` là có lấy `r` | Đếm thừa một phần tử, có thể vượt mảng | Chỉ lấy đến `r-1` |
| Coi `[l,r]` là bỏ `r` | Bỏ sót phần tử cuối | Đóng phải thì lấy cả `r` |
| Quên chuyển 1-based sang 0-based | Lệch toàn bộ chỉ số | `[L,R]` 1-based → `[L-1,R)` |
| Chuyển 1-based xong lại cộng 1 vào biên phải | Đếm thừa phần tử | Chuẩn hóa một lần |
| Tính độ dài `[l,r)` bằng `r-l+1` | Sai số phần tử | Dùng `r-l` |
| Cho phép `r=n` rồi đọc `a[r]` | Truy cập ngoài mảng | Biên phải là **exclusive** |
| Không xử lý `l=r` | Sai trên đoạn rỗng | Trả đơn vị hoặc báo lỗi theo phép |
| Mặc định `min([])=0` | Sai với dữ liệu có giá trị dương | Dùng quy ước rõ hoặc báo lỗi |
| Dùng Python `a[-1]` cho truy vấn chỉ số âm | Vô tình đọc cuối mảng | Kiểm tra biên chặt chẽ |
| Tự đảo `l,r` nếu `l>r` | Thay đổi ý nghĩa yêu cầu lỗi | Báo lỗi nếu hợp đồng không cho phép |
| Cắt đoạn vượt biên mà không báo | Che lỗi của người gọi | Chọn rõ policy strict hoặc clamping |
| Xây `P` dài n thay vì n+1 rồi dùng `P[r]` | Lỗi khi `r=n` | Dùng `P[0]=0` và n+1 phần tử |
| Nhầm `P[k]` chứa cả `a[k]` | Công thức trừ sai | Ghi bất biến “k phần tử đầu” |
| Dùng prefix cũ sau cập nhật | Truy vấn trả số liệu lỗi thời | Cập nhật/rebuild hoặc chọn cấu trúc động |
| Dùng prefix min rồi cố “trừ tiền tố” | Không thể khử bằng min | Dùng cấu trúc phù hợp với min |
| Cho rằng phép gộp bất kỳ đều kết hợp | Chia/gộp cho kết quả khác quét | Kiểm tra tính kết hợp |
| Đảo thứ tự hai đoạn với phép nối chuỗi | Kết quả khác vì không giao hoán | Gộp theo thứ tự trái–phải |
| Nhầm range_add và range_assign | Thay đổi giá trị sai yêu cầu | Đặc tả thao tác rõ ràng |
| Dùng mảng hiệu nhưng truy vấn ngay như đã cập nhật mảng | Kết quả chưa được materialize | Tổng hợp lại hoặc dùng cấu trúc online |
| Xem `[start,end)` thời gian là đóng cả hai | Đếm trùng sự kiện ở ranh giới | Đặt biên phải exclusive |

## 22. Quy trình chọn mô hình và cấu trúc

Khi nhận một bài truy vấn đoạn mới, hãy xác định theo trình tự:

1. **Miền dữ liệu:** một mảng 1D, ma trận 2D hay sự kiện theo timestamp?
2. **Quy ước:** chỉ số 0/1; đóng/nửa mở; có cho phép đoạn rỗng không?
3. **Phép hỏi:** sum, min, max, gcd, XOR, count, hoặc phép tổng hợp có thứ tự?
4. **Phép cập nhật:** không có, gán điểm, cộng điểm, cộng đoạn, hay gán đoạn?
5. **Thứ tự thao tác:** tĩnh, online hay offline?
6. **Giới hạn `n, q, u`:** một đoạn quét O(k) có đủ nhanh không?
7. **Giá trị cơ sở:** phép gộp có phần tử đơn vị cho đoạn rỗng không?
8. **Bất biến:** với mỗi cấu trúc tiền xử lý, nội dung lưu trữ có còn đúng sau cập nhật?

Ví dụ:

- “Có 100.000 giá trị không đổi, hỏi một triệu tổng đoạn” → **prefix sum** là ứng viên tốt.
- “Liên tục cộng vào một điểm rồi hỏi tổng đoạn” → cân nhắc **Fenwick tree**.
- “Sửa từng điểm và hỏi min trên đoạn” → cân nhắc **segment tree**.
- “Nhiều truy vấn min, hoàn toàn không cập nhật” → cân nhắc **sparse table**.
- “Hàng triệu lệnh cộng đoạn, cuối cùng mới lấy dãy” → cân nhắc **difference array**.

Đây là định hướng, không thay thế phân tích độ phức tạp chi tiết cho kích thước và ràng buộc thực tế.

## 23. Câu hỏi tự luyện có lời giải

**Bài 1 — Nhận diện phần tử.** Cho `a=[4,-1,7,2,9,3]`. Những phần tử nào thuộc đoạn 0-based `[2,5)`?

*Lời giải:* Các vị trí `2,3,4`, giá trị **`7,2,9`**. Phần tử `a[5]=3` không nằm trong đoạn.

**Bài 2 — Đổi quy ước.** Truy vấn 1-based đóng `[3,5]` tương đương đoạn 0-based nửa mở nào?

*Lời giải:* **`[2,5)`**, theo công thức `l=L-1`, `r=R`.

**Bài 3 — Biên đóng 0-based.** Đoạn `[2,4]` tính cả hai đầu trên mảng 0-based tương đương đoạn nửa mở nào?

*Lời giải:* **`[2,5)`**, vì biên phải được lấy nên phải tăng lên một khi đổi thành exclusive.

**Bài 4 — Độ dài.** Với `n=10`, đoạn `[4,9)` có bao nhiêu phần tử? Đoạn `[9,9)` có hợp lệ không?

*Lời giải:* `9-4=5` phần tử. `[9,9)` là **đoạn rỗng hợp lệ**, có độ dài 0.

**Bài 5 — Toàn mảng.** Trong quy ước 0-based nửa mở, biểu diễn toàn bộ mảng có n phần tử thế nào?

*Lời giải:* **`[0,n)`**. Biên phải `n` được phép vì nó **không bị truy cập** như chỉ số phần tử.

**Bài 6 — Prefix sum.** Với `a=[4,-1,7,2,9,3]`, viết mảng tổng tiền tố `P`.

*Lời giải:* **`P=[0,4,3,10,12,21,24]`**. Mảng dài `n+1=7`.

**Bài 7 — Công thức.** Dùng `P` ở bài 6 tính tổng `[1,4)` và `[3,3)`.

*Lời giải:* `P[4]-P[1]=12-4=8`. Đoạn rỗng: `P[3]-P[3]=0`.

**Bài 8 — Truy vấn rỗng.** `min` trên `[2,2)` có tự nhiên bằng 0 không?

*Lời giải:* **Không.** Đoạn hợp lệ nhưng không chứa giá trị. API có thể **báo lỗi** hoặc dùng đơn vị `+∞` ở tầng đại số; không tùy tiện lấy 0.

**Bài 9 — Cập nhật điểm.** Với `a[3]=2`, phân biệt `point_assign(3,5)` và `point_add(3,5)`.

*Lời giải:* Gán điểm đưa `a[3]` thành **5**. Cộng điểm đưa `a[3]` thành **7**.

**Bài 10 — Cập nhật đoạn.** Cộng 5 vào `[1,4)` của `[4,-1,7,2,9,3]` cho mảng nào?

*Lời giải:* **`[4,4,12,7,9,3]`**; chỉ thay các vị trí 1,2,3.

**Bài 11 — Dữ liệu động.** Vì sao không nên tiếp tục dùng một `prefix` đã xây để trả lời truy vấn sau khi `a[3]` thay đổi?

*Lời giải:* Các tổng tiền tố từ `P[4]` trở đi đã **không còn khớp với mảng mới**. Cần cập nhật bảng, xây lại hoặc dùng cấu trúc truy vấn động.

**Bài 12 — Tính kết hợp.** Ghép chuỗi có thể dùng để tổng hợp đoạn bằng cách chia đôi và gộp không? Có thể tùy ý đổi thứ tự hai nửa không?

*Lời giải:* **Có** vì ghép chuỗi kết hợp; **không** được đổi thứ tự vì ghép chuỗi thường không giao hoán.

**Bài 13 — Prefix min.** Vì sao không thể dùng công thức tương tự `P[r]-P[l]` để trả min của đoạn từ chỉ một bảng prefix min?

*Lời giải:* Phép min **không có phép nghịch đảo** cho phép khử phần tiền tố. Hai mảng có cùng prefix min vẫn có thể có min trên một đoạn giữa khác nhau.

**Bài 14 — Cửa sổ trượt.** Với `n=6,k=3` có bao nhiêu cửa sổ độ dài 3 theo `[i,i+k)`?

*Lời giải:* **`n-k+1=4`** cửa sổ, bắt đầu tại `i=0,1,2,3`.

**Bài 15 — Khoảng thời gian.** Hai khoảng `[08:00,09:00)` và `[09:00,10:00)` có đếm trùng sự kiện xảy ra đúng 09:00 không?

*Lời giải:* **Không.** Sự kiện tại biên phải của khoảng đầu bị loại và được lấy tại biên trái của khoảng sau.

**Bài 16 — Đoạn 2D.** Trên ma trận ở mục 19, tổng hình chữ nhật `[1,3) × [1,3)` bằng bao nhiêu?

*Lời giải:* Các ô `6,7,10,11`; tổng là **34**.

**Bài 17 — Chọn cấu trúc.** Một mảng tĩnh dài `n` phải trả lời `q` truy vấn tổng. So sánh tổng thời gian của cách quét và cách xây prefix.

*Lời giải:* Quét có thể tốn **O(qn)** trong trường hợp xấu nhất. Prefix cần **O(n)** tiền xử lý và **O(q)** cho q truy vấn, tổng **O(n+q)**.

**Bài 18 — Mảng hiệu.** Muốn cộng `delta` vào `[l,r)`, hai vị trí của diff phải cập nhật thế nào?

*Lời giải:* **`diff[l] += delta`**, **`diff[r] -= delta`**; sau đó cộng dồn diff theo chỉ số để nhận lượng tăng cho từng vị trí.

**Bài 19 — Kiểm tra biên.** Với `n=6`, `[6,6)` và `[6,7)` khác nhau như thế nào?

*Lời giải:* `[6,6)` là **đoạn rỗng hợp lệ** ở cuối mảng. `[6,7)` **không hợp lệ** vì `r=7 > n`.

**Bài 20 — Phép chia đoạn.** Nếu chia `[1,7)` tại `m=4` thì hai đoạn con là gì, và vì sao không đếm trùng `a[4]`?

*Lời giải:* **`[1,4)`** và **`[4,7)`**. Đoạn trái kết thúc **trước** vị trí 4, đoạn phải bắt đầu tại 4, nên mỗi chỉ số thuộc đúng một đoạn.

## 24. Tổng kết

**Truy vấn đoạn** đặt câu hỏi trên các vị trí **liên tiếp** của dãy. Quy ước nội bộ **0-based `[l,r)`** đặc biệt thuận tiện: độ dài là `r-l`, đoạn rỗng là `[l,l)`, toàn mảng là `[0,n)`, và hai đoạn kề nhau `[l,m)`, `[m,r)` ghép lại không trùng/thiếu phần tử.

Mọi đầu vào theo quy ước khác phải được **chuyển đúng một lần** về dạng chuẩn. Đặc biệt, **1-based đóng `[L,R]` → 0-based `[L-1,R)`**. Khi xác định phép hỏi, cần biết **phép gộp có tính kết hợp, có đơn vị và có nghịch đảo hay không**, đồng thời xác định kiểu cập nhật: không đổi, gán/cộng điểm hay gán/cộng đoạn.

Với **tổng đoạn tĩnh**, `P[0]=0`, `P[i+1]=P[i]+a[i]` và `sum([l,r))=P[r]-P[l]` cho phép xây O(n), trả lời O(1). Với dữ liệu động hoặc phép gộp khác, có thể cần Fenwick tree, segment tree, sparse table, deque hoặc mảng hiệu tùy bài toán. **Quy ước biên chính xác là bất biến đầu tiên phải giữ**, trước cả việc tối ưu thời gian và bộ nhớ.

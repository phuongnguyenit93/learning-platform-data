# Phân rã căn bậc hai và cân bằng kích thước khối

Một mảng có thể chứa hàng chục nghìn hoặc hàng triệu phần tử. Nếu cần trả lời nhiều truy vấn **tổng, min hoặc max trên một đoạn liên tiếp**, duyệt lại từng phần tử ở mỗi truy vấn sẽ lãng phí. Nhưng không phải lúc nào ta cũng muốn triển khai ngay một segment tree với nhiều nút, phép gộp và quy tắc cập nhật.

**Phân rã căn bậc hai** (*square-root decomposition*, hay *sqrt decomposition*) là một giải pháp trung gian: chia mảng thành những **khối liên tiếp** gần bằng nhau, lưu trước thông tin tổng hợp của từng khối, và kết hợp:

- **Quét trực tiếp** những phần tử nằm ở phần đầu/cuối đoạn nhưng không tạo thành khối trọn vẹn.
- **Đọc một giá trị tổng hợp** cho mỗi khối nằm hoàn toàn trong đoạn truy vấn.

Nếu mảng dài `n` và mỗi khối có tối đa `B` phần tử, một truy vấn thường tốn:

```text
O(B + n/B)
```

Chọn `B` xấp xỉ `√n` cân bằng số phần tử phải quét ở biên với số khối phải gộp, tạo độ phức tạp **O(√n)** cho mỗi truy vấn trong trường hợp xấu nhất.

Bài thuộc chương **Truy vấn đoạn** trong mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mô-đun xây nền tảng cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, nhấn mạnh **bất biến, thao tác và độ phức tạp thời gian/bộ nhớ** để lựa chọn cấu trúc phù hợp. Nội dung dưới đây giải thích cách phân khối, chọn kích thước, chứng minh và truy vết, mã Python cho truy vấn/cập nhật, biến thể lazy, lỗi biên và bài tập.

## 1. Bài toán và hợp đồng chỉ số

Cho mảng `a` gồm `n` phần tử:

```text
a = [a[0], a[1], ..., a[n-1]]
```

Ta cần hỗ trợ ít nhất hai thao tác:

1. `range_sum(l, r)`: tổng các phần tử thuộc đoạn.
2. `point_assign(i, x)`: gán `a[i] = x`, rồi những truy vấn sau phải nhìn thấy giá trị mới.

Ta cũng có thể thêm `point_add(i, delta)` và về sau mở rộng thành `range_add(l, r, delta)`.

**Quy ước xuyên suốt** là chỉ số bắt đầu từ 0, đoạn nửa mở `[l,r)`:

```text
0 <= l <= r <= n

[l,r) gồm các vị trí l, l+1, ..., r-1.
```

Do đó:

- `[0,n)` là toàn mảng.
- `[l,l)` là đoạn rỗng, tổng bằng 0.
- `r=n` là biên phải hợp lệ vì `a[n]` **không được đọc**.
- Nếu đề dùng đoạn đóng 1-based `[L,R]`, đổi thành `[L-1,R)` trước khi gọi API.

Ví dụ mảng:

```text
Chỉ số:   0   1   2   3   4   5   6   7   8   9
Giá trị:  4  -1   7   2   9   3   5  -2   6   1
```

Truy vấn `[2,9)` lấy các chỉ số `2,3,4,5,6,7,8` và có tổng:

```text
7 + 2 + 9 + 3 + 5 - 2 + 6 = 30
```

Mục tiêu là tái sử dụng những kết quả đã tính khi có nhiều truy vấn.

## 2. Ý tưởng: lưu bản tóm tắt cho từng khối

Chọn một số nguyên `B >= 1` gọi là **kích thước khối mục tiêu**. Chia mảng thành các đoạn:

```text
Khối 0: [0, B)
Khối 1: [B, 2B)
Khối 2: [2B, 3B)
...
```

Tất cả các biên thực tế được giới hạn trong `[0,n)`. Khối cuối **có thể ngắn hơn B**, không phải bổ sung giá trị giả vào mảng ban đầu.

Gọi số khối là `m`:

```text
m = ceil(n / B)
  = (n + B - 1) // B       khi n > 0, B >= 1
```

Với `n=10` và `B=4`:

```text
Khối 0: [0,4)  -> 4, -1, 7, 2
Khối 1: [4,8)  -> 9, 3, 5, -2
Khối 2: [8,10) -> 6, 1
```

Sơ đồ:

```text
Chỉ số    0    1    2    3 | 4    5    6    7 | 8    9
Giá trị   4   -1    7    2 | 9    3    5   -2 | 6    1
         └──── Khối 0 ───┘ └──── Khối 1 ───┘ └ Khối 2 ┘

B = 4
m = 3
```

Nếu truy vấn **tổng**, ta lưu một `block_sum[b]` cho mỗi khối:

```text
block_sum[0] = 4 - 1 + 7 + 2 = 12
block_sum[1] = 9 + 3 + 5 - 2 = 15
block_sum[2] = 6 + 1 = 7

block_sum = [12, 15, 7]
```

**Bất biến cốt lõi:**

```text
block_sum[b]
    = sum(a[i] với i thuộc khối b)
```

Khi bất biến đúng, lấy tổng của **một khối trọn vẹn** chỉ cần đọc một ô `block_sum[b]`, thay vì quét tối đa `B` phần tử.

## 3. Biên của khối và vị trí phần tử

Với kích thước khối `B`, phần tử tại chỉ số `i` nằm trong khối:

```text
block_id(i) = i // B
```

Khối có số hiệu `b` chiếm đoạn:

```text
start(b) = b * B
end(b)   = min(n, (b + 1) * B)

block(b) = [start(b), end(b))
```

Độ dài thật của khối cuối:

```text
length(b) = end(b) - start(b)
```

Ví dụ `n=10, B=4`:

| Khối `b` | Biên trái | Biên phải exclusive | Độ dài | Tổng |
|---:|---:|---:|---:|---:|
| 0 | 0 | 4 | 4 | 12 |
| 1 | 4 | 8 | 4 | 15 |
| 2 | 8 | 10 | 2 | 7 |

Chỉ số 9 thuộc khối `9//4=2`. Chỉ số 10 **không phải vị trí phần tử**, dù xuất hiện như biên phải của khối cuối.

### Khi n là số chính phương

Nếu `n=16` và `B=4`, ta có đúng bốn khối đủ bốn phần tử:

```text
[0,4), [4,8), [8,12), [12,16)
```

### Khi n không chia hết cho B

Nếu `n=10` và `B=4`, khối cuối dài hai phần tử. Không được giả định mọi khối đều dài bốn phần tử khi tính trung bình, nhân lazy tag với số phần tử hoặc truy cập ô cuối.

### Khi mảng rỗng

Với `n=0`, không có khối thật nào; ta vẫn có thể chọn `B=1` để tránh phép chia cho 0. Truy vấn hợp lệ duy nhất là `[0,0)`, có tổng 0.

## 4. Trả lời truy vấn bằng khối nguyên vẹn và phần biên

Xét truy vấn `[l,r)`. Ta chia các phần tử cần hỏi thành tối đa ba vùng:

1. **Biên trái:** vài phần tử từ `l` đến hết khối đang chứa `l`.
2. **Các khối nguyên vẹn:** mỗi khối nằm hoàn toàn trong `[l,r)` được lấy bằng một `block_sum`.
3. **Biên phải:** vài phần tử cuối chưa tạo thành khối đầy đủ.

Một truy vấn có thể chỉ chứa một vùng; không bắt buộc phải có đủ cả ba.

### Truy vết `[2,9)`

Với `B=4`:

```text
Chỉ số:    0   1   2   3 | 4   5   6   7 | 8   9
Giá trị:   4  -1   7   2 | 9   3   5  -2 | 6   1
                    ▲ ▲  └── một khối ──┘  ▲
                     trái                  phải

[2,9):
- Biên trái [2,4): 7 + 2 = 9
- Khối 1     [4,8): block_sum[1] = 15
- Biên phải [8,9): 6

Đáp án = 9 + 15 + 6 = 30
```

Ta chỉ đọc trực tiếp ba phần tử ở phần biên (7,2,6) và một giá trị tổng khối (15), thay vì quét cả bảy phần tử.

### Trường hợp đoạn nằm hoàn toàn trong một khối

Ví dụ `[5,7)` thuộc khối 1, chứa hai phần tử `3,5`; thuật toán quét trực tiếp và trả 8. **Không được** cộng cả `block_sum[1]` vì khối chứa cả các phần tử nằm ngoài đoạn.

### Trường hợp đoạn khớp biên khối

`[4,8)` khớp khối 1 nên trả trực tiếp `block_sum[1]=15`.

Với `[0,8)`, chỉ cần `block_sum[0]+block_sum[1]=27`. Không có biên lẻ.

## 5. Giả mã truy vấn tổng

Một cách cài đặt đơn giản tránh phải phân biệt nhiều nhánh:

```text
QUERY_SUM(l, r):
    kiểm tra 0 <= l <= r <= n
    result = 0

    while l < r và l chưa nằm trên biên bắt đầu khối:
        result += a[l]
        l += 1

    while còn ít nhất B phần tử từ l đến r:
        result += block_sum[l // B]
        l += B

    while l < r:
        result += a[l]
        l += 1

    return result
```

Tại đầu vòng thứ hai, `l` đã **thẳng hàng** với một biên khối (`l%B==0`). Điều kiện `l+B<=r` bảo đảm **toàn bộ B phần tử** thuộc đoạn truy vấn, nên khối này có thể lấy trực tiếp từ bảng tổng.

Nếu khối cuối có ít hơn B phần tử, đoạn đó sẽ được xử lý bởi vòng quét cuối. Cách này vẫn đúng và giữ giới hạn O(B) cho phần biên.

### Bất biến của biến result

Trong suốt thuật toán:

> `result` là tổng các phần tử ban đầu của truy vấn mà con trỏ đã đi qua; `l` luôn chỉ vào vị trí **đầu tiên chưa được tính**.

Mỗi bước chỉ xử lý:

- Một phần tử `a[l]`, rồi tăng `l` thêm 1; hoặc
- Một khối đầy đủ có tổng đã lưu, rồi tăng `l` thêm `B`.

Các phần được xử lý **không chồng lấn** và bao phủ toàn bộ `[l,r)` khi kết thúc. Bởi vậy thuật toán không đếm thừa hay bỏ sót phần tử.

## 6. Python: phân rã căn bậc hai cho tổng đoạn

Ta triển khai lớp `SqrtRangeSum` với mảng gốc và tổng của từng khối. Kích thước khối có thể chọn thủ công hoặc để hàm tự chọn gần `√n`.

```python
from math import isqrt


def validate_range(n, l, r):
    if type(l) is not int or type(r) is not int:
        raise TypeError("Biên truy vấn phải là số nguyên")
    if not 0 <= l <= r <= n:
        raise IndexError("Đoạn [l,r) không hợp lệ")


def choose_block_size(n):
    """ceil(sqrt(n)); với n=0 dùng 1 để tránh chia cho 0."""
    if n == 0:
        return 1
    return isqrt(n - 1) + 1


class SqrtRangeSum:
    def __init__(self, values, block_size=None):
        self.a = list(values)
        self.n = len(self.a)

        if block_size is None:
            self.B = choose_block_size(self.n)
        else:
            if type(block_size) is not int or block_size <= 0:
                raise ValueError("block_size phải là số nguyên dương")
            self.B = block_size

        self.m = (self.n + self.B - 1) // self.B
        self.block_sum = [0] * self.m

        for i, value in enumerate(self.a):
            self.block_sum[i // self.B] += value

    def range_sum(self, l, r):
        validate_range(self.n, l, r)
        answer = 0

        # Biên trái: quét cho tới đầu một khối.
        while l < r and l % self.B != 0:
            answer += self.a[l]
            l += 1

        # Các khối đủ B phần tử nằm trọn trong [l,r).
        while l + self.B <= r:
            answer += self.block_sum[l // self.B]
            l += self.B

        # Biên phải còn lại (có thể là khối cuối ngắn).
        while l < r:
            answer += self.a[l]
            l += 1

        return answer

    def point_assign(self, i, value):
        if type(i) is not int or not 0 <= i < self.n:
            raise IndexError("Chỉ số cập nhật không hợp lệ")

        delta = value - self.a[i]
        self.a[i] = value
        self.block_sum[i // self.B] += delta

    def point_add(self, i, delta):
        if type(i) is not int or not 0 <= i < self.n:
            raise IndexError("Chỉ số cập nhật không hợp lệ")

        self.a[i] += delta
        self.block_sum[i // self.B] += delta


a = [4, -1, 7, 2, 9, 3, 5, -2, 6, 1]
ds = SqrtRangeSum(a)

assert ds.B == 4
assert ds.m == 3
assert ds.block_sum == [12, 15, 7]

assert ds.range_sum(2, 9) == 30
assert ds.range_sum(4, 8) == 15
assert ds.range_sum(0, 10) == 34
assert ds.range_sum(5, 7) == 8
assert ds.range_sum(10, 10) == 0

ds.point_assign(5, 10)  # Vị trí 5: 3 -> 10.
assert ds.block_sum == [12, 22, 7]
assert ds.range_sum(2, 9) == 37

ds.point_add(9, -3)      # Vị trí 9: 1 -> -2.
assert ds.block_sum == [12, 22, 4]
assert ds.range_sum(8, 10) == 4
```

Lớp sao chép `values` sang `self.a`; thay đổi danh sách bên ngoài sau khi xây không trực tiếp thay đổi `self.a`. Mọi thay đổi thông qua các phương thức cập nhật phải giữ đúng **bất biến tổng khối**.

### Kiểm tra đầu vào rỗng và một phần tử

```python
empty = SqrtRangeSum([])
assert empty.B == 1
assert empty.m == 0
assert empty.range_sum(0, 0) == 0

one = SqrtRangeSum([9])
assert one.B == 1
assert one.block_sum == [9]
assert one.range_sum(0, 1) == 9

one.point_add(0, -4)
assert one.range_sum(0, 1) == 5

try:
    empty.point_assign(0, 7)
except IndexError:
    pass
else:
    raise AssertionError("Không thể sửa phần tử ở mảng rỗng")
```

### Tùy chọn kích thước khối thủ công

```python
manual = SqrtRangeSum([1, 2, 3, 4, 5], block_size=2)

assert manual.B == 2
assert manual.m == 3
assert manual.block_sum == [3, 7, 5]
assert manual.range_sum(1, 5) == 14

# Dùng B lớn hơn n vẫn đúng, nhưng có ít lợi ích tiền xử lý.
huge = SqrtRangeSum([1, 2, 3], block_size=100)
assert huge.block_sum == [6]
assert huge.range_sum(1, 3) == 5
```

Không bắt buộc `B` đúng bằng căn bậc hai để thuật toán **đúng**. Chọn `B` chủ yếu quyết định **chi phí vận hành**, không quyết định tính hợp lệ của cấu trúc.

## 7. Cập nhật một điểm: vì sao tổng khối sửa trong O(1)?

Giả sử khối `b` chứa vị trí `i`. Bất biến là:

```text
block_sum[b] = tổng a[j] trên khối b
```

Nếu thay `a[i]` từ `old` thành `new` thì tổng của khối đó đổi đúng:

```text
delta = new - old
block_sum[b] += delta
```

Các khối khác không đổi vì chỉ một phần tử được sửa.

### Truy vết

Ban đầu:

```text
a         = [4,-1,7,2 | 9,3,5,-2 | 6,1]
block_sum = [12,        15,        7]
```

Gán `a[5]=10`:

```text
old = 3
new = 10
delta = +7
b = 5 // 4 = 1

block_sum[1] = 15 + 7 = 22
```

Mảng sau cập nhật:

```text
a         = [4,-1,7,2 | 9,10,5,-2 | 6,1]
block_sum = [12,        22,        7]
```

Truy vấn tiếp theo dùng bảng khối mới, không cần xây lại toàn bộ.

### Phân biệt gán và cộng điểm

- `point_assign(i, x)`: đặt giá trị mới bằng `x`; phải tính `x - old`.
- `point_add(i, delta)`: giá trị mới bằng `old + delta`; cập nhật tổng khối thêm `delta`.

Với **tổng**, cả hai đều có thể thực hiện O(1). Nhưng điều này **không tự đúng với min/max**, bởi khi tăng giá trị của phần tử hiện đang nhỏ nhất, ta không biết phần tử nhỏ nhất mới nếu chỉ giữ một số min.

## 8. Chứng minh thời gian truy vấn O(B + n/B)

Gọi `k=r-l` là độ dài đoạn cần hỏi.

### Số phần tử biên

Vòng thứ nhất đi từ `l` tới biên bắt đầu khối kế tiếp, hoặc dừng ở `r`. Nó quét **ít hơn B** phần tử.

Vòng cuối cùng quét những phần tử còn lại khi không còn một khối **đủ B phần tử** nằm trong đoạn. Nó quét **ít hơn B** phần tử.

Vì vậy tổng phần tử xử lý trực tiếp nằm trong:

```text
O(B)
```

Nếu đoạn rất ngắn, hai vòng có thể gộp lại và chỉ tốn O(k), không nhất thiết phải quét đủ B.

### Số khối đầy đủ

Mỗi lần vòng giữa chạy, nó tiêu thụ đúng `B` phần tử. Trên mảng dài `n`, tổng số khối đầy đủ có thể dùng nhiều nhất khoảng:

```text
n / B
```

Do đó chi phí đọc các tổng khối là:

```text
O(n/B)
```

### Tổng hợp

```text
T_query(B) = O(B + n/B)
```

Đây là **cận trên trường hợp xấu nhất** theo n và B, với một phép cộng/tra bảng có chi phí hằng số. Nó không có nghĩa rằng mọi truy vấn đều mất đúng số bước ấy.

### Đầu ra và bộ nhớ

Nếu một truy vấn chỉ trả một số tổng, bản thân phép truy vấn dùng O(1) biến điều khiển. Nếu giữ `q` câu trả lời trong một danh sách, danh sách đầu ra ấy tốn O(q) bộ nhớ, tách riêng khỏi bộ nhớ của cấu trúc.

## 9. Cân bằng kích thước khối bằng căn bậc hai

Có hai phần chi phí đối nghịch:

```text
B càng lớn:
    Ít khối hơn -> phần n/B giảm
    Nhưng biên phải quét dài hơn -> phần B tăng

B càng nhỏ:
    Phần biên được quét ngắn hơn -> B giảm
    Nhưng có nhiều khối -> phần n/B tăng
```

Ta muốn cân bằng hai thành phần:

```text
B ≈ n/B
=> B² ≈ n
=> B ≈ √n
```

Khi đó:

```text
B + n/B ≈ 2√n
```

Suy ra **O(√n)** thời gian cho mỗi truy vấn.

### Ví dụ n = 10.000

| `B` | Số khối xấp xỉ `n/B` | Chỉ báo `B+n/B` |
|---:|---:|---:|
| 1 | 10.000 | 10.001 |
| 10 | 1.000 | 1.010 |
| 50 | 200 | 250 |
| **100** | **100** | **200** |
| 200 | 50 | 250 |
| 1.000 | 10 | 1.010 |
| 10.000 | 1 | 10.001 |

Bảng là **chỉ báo bậc chi phí**, không phải số lần cộng chính xác của mọi truy vấn. Số phần tử thực sự nằm trong biên và số khối được chọn phụ thuộc `l,r`.

### Chọn floor hay ceil căn bậc hai?

Các lựa chọn như:

```text
B = max(1, floor(√n))
B = max(1, ceil(√n))
```

đều cho độ phức tạp O(√n). Với Python số nguyên, ví dụ sử dụng:

```python
from math import isqrt

def ceil_sqrt(n):
    if n == 0:
        return 1
    return isqrt(n - 1) + 1
```

Không phải dùng số thực `sqrt` rồi ép kiểu để tính đúng kích thước cho mọi số nguyên lớn. Dùng `isqrt` giúp tính chính xác theo số nguyên.

## 10. Không phải mọi B đều có cùng chi phí thực tế

Mặc dù lựa chọn `B≈√n` cho cận tốt, kích thước tối ưu **thực tế** còn tùy:

- Phân bố độ dài và vị trí của truy vấn.
- Tỷ lệ truy vấn so với cập nhật.
- Phép gộp dùng cộng số nguyên, min hay nối dữ liệu phức tạp.
- Chi phí truy cập ngẫu nhiên, vòng lặp, bộ đệm CPU và ngôn ngữ triển khai.
- Số lượng phần tử n và giới hạn bộ nhớ.
- Yêu cầu truy vấn sau từng cập nhật hay xử lý offline.

Ví dụ, với nhiều truy vấn rất ngắn, phần quét trực tiếp có thể chiếm phần lớn công việc. Một B nhỏ hơn `√n` có thể có lợi trong một số bộ dữ liệu dù cận trường hợp xấu nhất vẫn có cùng dạng.

**Không nên khẳng định B=√n luôn tối ưu số nanosecond.** Nó là lựa chọn có căn cứ toán học về cân bằng bậc thời gian; tinh chỉnh thực tế cần đo trên khối lượng công việc đại diện.

## 11. Đánh đổi khi phép gộp là min hoặc max

Với **tổng**, thay một phần tử từ `old` sang `new` chỉ cần sửa tổng khối bằng `new-old`. Nhưng với **min**, giả sử khối chứa:

```text
[8, 2, 6, 4]
block_min = 2
```

Nếu tăng phần tử 2 thành 9:

```text
[8, 9, 6, 4]
block_min mới = 4
```

Không thể suy ra 4 chỉ từ hai số **min cũ = 2** và **giá trị mới = 9**. Ta cần tìm min lại trong khối, có thể quét tối đa B phần tử.

### Chi phí thường gặp

| Thao tác | Tổng khối | Min/Max khối |
|---|---:|---:|
| Xây bản tóm tắt tất cả khối | O(n) | O(n) |
| Truy vấn đoạn | O(B+n/B) | O(B+n/B) |
| Gán một điểm | **O(1)** | **O(B)** nếu quét lại khối |
| Cộng một điểm | **O(1)** | **O(B)** nếu không có thông tin bổ sung |
| Bộ nhớ bản tóm tắt | O(n/B) | O(n/B) |

Chú ý: cập nhật min/max có thể có tối ưu cho một số trường hợp cụ thể (chẳng hạn giảm giá trị và biết nó nhỏ hơn min hiện tại), nhưng **O(B)** là cận đơn giản, chắc chắn đúng cho thao tác gán điểm tùy ý.

## 12. Python: phân rã căn bậc hai cho min đoạn

Cách sau trả min của đoạn **không rỗng**. Với một đoạn rỗng, API báo lỗi thay vì tùy tiện trả 0.

```python
class SqrtRangeMin:
    def __init__(self, values, block_size=None):
        self.a = list(values)
        self.n = len(self.a)

        if block_size is None:
            self.B = choose_block_size(self.n)
        else:
            if type(block_size) is not int or block_size <= 0:
                raise ValueError("block_size phải dương")
            self.B = block_size

        self.m = (self.n + self.B - 1) // self.B
        self.block_min = [float("inf")] * self.m

        for i, value in enumerate(self.a):
            b = i // self.B
            self.block_min[b] = min(self.block_min[b], value)

    def query(self, l, r):
        validate_range(self.n, l, r)
        if l == r:
            raise ValueError("Không có min cho đoạn rỗng")

        answer = float("inf")

        while l < r and l % self.B != 0:
            answer = min(answer, self.a[l])
            l += 1

        while l + self.B <= r:
            answer = min(answer, self.block_min[l // self.B])
            l += self.B

        while l < r:
            answer = min(answer, self.a[l])
            l += 1

        return answer

    def point_assign(self, i, value):
        if type(i) is not int or not 0 <= i < self.n:
            raise IndexError("Chỉ số cập nhật không hợp lệ")

        self.a[i] = value
        b = i // self.B
        left = b * self.B
        right = min(self.n, (b + 1) * self.B)

        # Giá trị min có thể tăng hoặc giảm: tính lại cả khối.
        self.block_min[b] = min(self.a[left:right])


mins = SqrtRangeMin([8, 2, 6, 4, 9, 3], block_size=4)

assert mins.block_min == [2, 3]
assert mins.query(0, 6) == 2
assert mins.query(2, 6) == 3

mins.point_assign(1, 10)
assert mins.block_min == [4, 3]
assert mins.query(0, 4) == 4
assert mins.query(0, 6) == 3

try:
    mins.query(2, 2)
except ValueError:
    pass
else:
    raise AssertionError("Min của đoạn rỗng phải báo lỗi")
```

Trong mã, `float("inf")` đóng vai trò phần tử đơn vị cho phép min trên những giá trị số hữu hạn. Nếu miền có `NaN` hoặc kiểu không tương thích với `float`, cần quy định cách xử lý thích hợp.

**Điểm chính:** một phép gộp kết hợp giúp truy vấn đoạn bằng bản tóm tắt khối; nhưng **chi phí duy trì bản tóm tắt khi cập nhật** phụ thuộc bản chất phép gộp.

## 13. Cân bằng B khi truy vấn và cập nhật có trọng số khác nhau

Giả sử có:

- `q` truy vấn min, mỗi truy vấn tốn khoảng `O(B+n/B)`.
- `u` lần gán điểm, mỗi lần tính lại min khối tốn `O(B)`.
- O(n) tiền xử lý.

Một mô hình chi phí bậc lớn đơn giản:

```text
T(B) ≈ n + q*(B+n/B) + u*B
     = n + q*n/B + (q+u)*B
```

Bỏ qua các hằng số và xét `B` là số thực dương tạm thời, hai thành phần biến thiên là:

```text
q*n/B       và       (q+u)*B
```

Cân bằng hai phần:

```text
q*n/B ≈ (q+u)*B

B² ≈ q*n/(q+u)

B ≈ sqrt(q*n/(q+u))
```

Sau đó làm tròn và giới hạn B trong khoảng `[1,n]` với n dương.

### Ví dụ cân bằng theo tập thao tác

Cho `n=10.000`, `q=1.000` truy vấn min và `u=9.000` cập nhật điểm:

```text
B ≈ sqrt(1000*10000 / 10000)
  = sqrt(1000)
  ≈ 32
```

Nếu chỉ xét truy vấn, `√n≈100`. Nhưng do cập nhật min phải quét lại khối, khối **nhỏ hơn** giúp giảm tổng chi phí trong mô hình này.

### Điều kiện cần nhớ

Đây là **mô hình gần đúng**, không phải lời cam kết tối ưu cho mọi dữ liệu. Nếu truy vấn thường rất ngắn, chi phí quét biên khác giả định trung bình; nếu việc cập nhật có thể xử lý nhanh nhờ bản tóm tắt bổ sung, công thức phải thay đổi.

Với **tổng và gán điểm O(1)**, mô hình chi phí truy vấn/cập nhật là:

```text
T(B) ≈ n + q*(B+n/B) + u
```

khi `q>0`, lựa chọn cân bằng theo query vẫn là **B≈√n**, vì chi phí cập nhật không phụ thuộc B trong cấu trúc tổng đơn giản.

## 14. Cập nhật cả đoạn: cần thiết kế thêm bất biến

Nếu muốn hỗ trợ:

```text
range_add(l, r, delta)
```

thì cập nhật trực tiếp từng phần tử trong đoạn dài k lại tốn O(k). Khi đã chia khối, ta có thể cải tiến:

- Với **khối nằm trọn** trong đoạn cập nhật, ghi **một lazy tag** biểu thị lượng cộng thêm chung cho mọi phần tử trong khối.
- Với **khối chỉ bị phủ một phần**, sửa trực tiếp những phần tử thực sự nằm trong đoạn và cập nhật bản tóm tắt của khối.

Đây là biến thể **sqrt decomposition với lazy propagation theo khối**. Nó không phải segment tree; mỗi khối chỉ có một tag, không có hệ nút nhiều tầng.

### Hai lớp dữ liệu

Trong biến thể cho tổng, mỗi khối `b` lưu:

1. `raw[i]`: giá trị nền của từng phần tử.
2. `lazy[b]`: lượng tăng chung đang chờ áp dụng cho **toàn bộ khối**.
3. `raw_sum[b]`: tổng các giá trị **raw** thuộc khối (chưa cộng lazy).

**Bất biến:**

```text
Giá trị logic tại i:
    actual[i] = raw[i] + lazy[i//B]

Tổng logic của khối b:
    actual_block_sum[b]
      = raw_sum[b] + lazy[b] * block_length[b]
```

Nhờ vậy, cộng `delta` vào một khối trọn vẹn chỉ cần:

```text
lazy[b] += delta
```

Không phải chạm vào từng `raw[i]`.

### Tại sao phải nhân với độ dài thật của khối?

Nếu khối cuối chỉ có hai phần tử và `lazy[b]=+5`, tổng logic của khối tăng **2*5=10**, không phải `B*5` nếu `B=4`.

Cần dùng `end(b)-start(b)` khi làm việc với **khối cuối ngắn hơn B**. Trong mã ví dụ dưới đây, vòng xử lý khối trọn chỉ lấy những khối **đủ B** phần tử; khối cuối ngắn được xử lý bằng phần tử biên, nên phép nhân `B` vẫn đúng trong nhánh đó. Nếu đổi mã để nhận khối cuối là khối trọn, phải chuyển sang **độ dài thật**.

## 15. Truy vết lazy trên khối hoàn chỉnh

Trở lại ví dụ `n=10, B=4`:

```text
raw: [4,-1,7,2 | 9,3,5,-2 | 6,1]
sum: [12,        15,        7]
lazy:[ 0,         0,        0]
```

Áp dụng:

```text
range_add(1, 7, +3)
```

Các vị trí 1..6 nhận +3. Không có khối `[0,4)` hoặc `[4,8)` nào được phủ trọn, vì đoạn chỉ chạm phần lớn hai khối. Ta có thể sửa trực tiếp sáu phần tử, vẫn hợp lệ theo cận O(B+n/B).

Với:

```text
range_add(4, 8, +5)
```

khối 1 được phủ trọn, nên:

```text
lazy[1] = 5
raw vẫn không đổi
raw_sum vẫn không đổi
```

Giá trị logic trong khối 1 là:

```text
raw:     [9, 3, 5, -2]
lazy:     +5 cho từng phần tử
actual:  [14, 8, 10, 3]

Tổng logic:
raw_sum[1] + 5*4 = 15 + 20 = 35
```

Nếu sau đó chỉ cộng 2 vào `a[5]`, có thể sửa:

```text
raw[5] += 2
raw_sum[1] += 2
lazy[1] vẫn = 5
```

Giá trị thực ở `a[5]` là `raw[5]+lazy[1] = 5+5=10`. **Không cần đẩy lazy về tất cả phần tử để sửa một điểm** đối với phép cộng này, vì bất biến tách thành “raw + lazy”.

## 16. Python: cộng đoạn và hỏi tổng bằng lazy theo khối

Triển khai dưới đây có:

- `range_add(l,r,delta)`.
- `range_sum(l,r)`.
- `point_assign(i,value)`.
- `materialize()` để xuất toàn bộ mảng logic.

Mỗi truy vấn/cập nhật đoạn có cận `O(B+n/B)`; gán điểm có O(1) thời gian.

```python
class LazySqrtRangeSum:
    def __init__(self, values, block_size=None):
        self.raw = list(values)
        self.n = len(self.raw)

        if block_size is None:
            self.B = choose_block_size(self.n)
        else:
            if type(block_size) is not int or block_size <= 0:
                raise ValueError("block_size phải dương")
            self.B = block_size

        self.m = (self.n + self.B - 1) // self.B
        self.lazy = [0] * self.m
        self.raw_sum = [0] * self.m

        for i, value in enumerate(self.raw):
            self.raw_sum[i // self.B] += value

    def range_add(self, l, r, delta):
        validate_range(self.n, l, r)

        # Biên trái chưa thẳng khối: cập nhật các phần tử raw.
        while l < r and l % self.B != 0:
            b = l // self.B
            self.raw[l] += delta
            self.raw_sum[b] += delta
            l += 1

        # Những khối đủ B phần tử: chỉ cập nhật lazy.
        while l + self.B <= r:
            b = l // self.B
            self.lazy[b] += delta
            l += self.B

        # Phần biên phải.
        while l < r:
            b = l // self.B
            self.raw[l] += delta
            self.raw_sum[b] += delta
            l += 1

    def range_sum(self, l, r):
        validate_range(self.n, l, r)
        answer = 0

        while l < r and l % self.B != 0:
            b = l // self.B
            answer += self.raw[l] + self.lazy[b]
            l += 1

        while l + self.B <= r:
            b = l // self.B
            answer += self.raw_sum[b] + self.lazy[b] * self.B
            l += self.B

        while l < r:
            b = l // self.B
            answer += self.raw[l] + self.lazy[b]
            l += 1

        return answer

    def point_assign(self, i, value):
        if type(i) is not int or not 0 <= i < self.n:
            raise IndexError("Chỉ số cập nhật không hợp lệ")

        b = i // self.B
        old_actual = self.raw[i] + self.lazy[b]

        # Giữ lazy, đổi raw để logical value bằng value.
        self.raw[i] = value - self.lazy[b]
        self.raw_sum[b] += value - old_actual

    def materialize(self):
        return [
            self.raw[i] + self.lazy[i // self.B]
            for i in range(self.n)
        ]


a = [4, -1, 7, 2, 9, 3, 5, -2, 6, 1]
lazy_ds = LazySqrtRangeSum(a)

assert lazy_ds.B == 4
assert lazy_ds.range_sum(2, 9) == 30

lazy_ds.range_add(1, 7, 3)
assert lazy_ds.materialize() == [4, 2, 10, 5, 12, 6, 8, -2, 6, 1]
assert lazy_ds.range_sum(2, 9) == 45

lazy_ds.range_add(4, 10, -2)
assert lazy_ds.materialize() == [4, 2, 10, 5, 10, 4, 6, -4, 4, -1]
assert lazy_ds.range_sum(2, 9) == 35
assert lazy_ds.range_sum(0, 10) == 40

lazy_ds.point_assign(5, 11)
assert lazy_ds.materialize()[5] == 11
assert lazy_ds.range_sum(2, 9) == 42
assert lazy_ds.range_sum(0, 10) == 47
```

### Trường hợp cập nhật trọn khối có lazy thật sự

```python
example = LazySqrtRangeSum(
    [4, -1, 7, 2, 9, 3, 5, -2, 6, 1],
    block_size=4,
)

example.range_add(4, 8, 5)

assert example.lazy == [0, 5, 0]
assert example.raw_sum == [12, 15, 7]
assert example.range_sum(4, 8) == 35
assert example.materialize()[4:8] == [14, 8, 10, 3]

example.point_assign(5, 20)
assert example.materialize()[5] == 20
assert example.range_sum(4, 8) == 47
```

Lý do đáp án cuối là 47: tổng trước gán bằng 35, `a[5]` đang là 8 và được gán thành 20, nên tổng tăng thêm 12.

### Cây rỗng và đoạn rỗng

```python
empty = LazySqrtRangeSum([])
empty.range_add(0, 0, 999)

assert empty.range_sum(0, 0) == 0
assert empty.materialize() == []

single = LazySqrtRangeSum([7])
single.range_add(0, 1, -3)
assert single.materialize() == [4]

single.point_assign(0, 100)
assert single.range_sum(0, 1) == 100
```

**Giới hạn:** mã này thiết kế cho phép cộng `delta` vào mỗi giá trị. Nó không tự hỗ trợ gán **cả đoạn** bằng `value` với cùng quy tắc tag, vì lệnh gán cần xử lý ghi đè và hợp thành cập nhật theo thứ tự.

## 17. Chứng minh bất biến của lazy theo khối

Với khối `b`, định nghĩa:

```text
A[i] = raw[i] + lazy[b]            (i thuộc b)
S[b] = sum(raw[i] với i thuộc b)
```

Giả sử trước một cập nhật, hai công thức đều đúng.

### Trường hợp khối được phủ trọn

Cộng `delta` vào mọi phần tử logic trong khối:

```text
lazy[b] <- lazy[b] + delta
raw không đổi
raw_sum không đổi
```

Khi đó:

```text
A_new[i] = raw[i] + (lazy[b] + delta)
         = A_old[i] + delta
```

Đúng cho mọi phần tử khối.

### Trường hợp chỉ phủ một phần khối

Cập nhật trực tiếp mỗi `raw[i]` trong phần giao với truy vấn:

```text
raw[i] <- raw[i] + delta
raw_sum[b] <- raw_sum[b] + delta   cho mỗi vị trí được sửa
lazy[b] không đổi
```

Với vị trí được cập nhật:

```text
A_new[i] = (raw_old[i] + delta) + lazy[b]
         = A_old[i] + delta
```

Các vị trí khác không đổi. `raw_sum[b]` vẫn bằng tổng raw vì ta cộng đúng delta cho từng phần tử raw đã sửa.

### Trường hợp gán điểm

Muốn `A[i]=value`, đặt:

```text
raw_new[i] = value - lazy[b]
```

Vì thế:

```text
raw_new[i] + lazy[b] = value
```

Tổng raw đổi:

```text
raw_new[i] - raw_old[i]
  = value - (raw_old[i] + lazy[b])
  = value - old_actual
```

đúng với dòng:

```python
self.raw_sum[b] += value - old_actual
```

Như vậy mọi cập nhật đều duy trì **giá trị logic** và **tổng raw**. Truy vấn từng phần tử lấy `raw+lazy`; truy vấn cả khối lấy `raw_sum + lazy*độ dài`, nên đều trả đúng kết quả.

## 18. Tại sao range add cũng mất O(B+n/B)?

Với mỗi lần cộng đoạn:

- Tối đa một phần đầu khối và một phần cuối khối cần cập nhật từng phần tử: O(B).
- Mỗi khối đầy đủ trong đoạn chỉ sửa một số `lazy[b]`: tối đa O(n/B).

Vậy:

```text
T_range_add = O(B+n/B)
T_range_sum = O(B+n/B)
```

Chọn B gần `√n` đem lại O(√n) cho cả hai.

**Điểm khác mảng hiệu theo lô:** mảng hiệu thông thường có thể **ghi mỗi cập nhật O(1)** nhưng cần **O(n) để xuất trạng thái cuối**; lazy sqrt decomposition cần O(√n) mỗi cập nhật và truy vấn, đổi lại có thể **trả lời online** mà không cần xây lại toàn mảng sau mỗi bước.

### Bộ nhớ biến thể lazy

- Mảng `raw`: O(n) nếu sao chép dữ liệu.
- Mảng `raw_sum`: O(n/B).
- Mảng `lazy`: O(n/B).
- Các biến vòng lặp: O(1).
- `materialize()`: thêm O(n) bộ nhớ đầu ra.

Cấu trúc giữ bản tóm tắt và tag theo **số khối**, không phải mỗi nút của một cây phân đoạn.

## 19. Cập nhật min/max cả đoạn có thể đơn giản hơn trong một số mô hình

Với phép **cộng một lượng cố định** vào cả khối, nếu khối lưu `block_min` thì:

```text
min(a[i]+delta trên khối)
= min(a[i] trên khối) + delta
```

Tương tự cho max:

```text
max(a[i]+delta trên khối)
= max(a[i] trên khối) + delta
```

Vì thế có thể giữ lazy cộng theo khối và cập nhật min/max đầy khối trong O(1). Nhưng nếu chỉ cập nhật **một phần khối**, thường phải sửa những phần tử ấy và tính lại min/max khối (hoặc duy trì cấu trúc phụ trong từng khối).

Đừng suy từ biến thể lazy cho **tổng** rằng mọi phép gộp đều có công thức tương tự. Ví dụ:

- Với tổng: thêm `delta` cho `k` phần tử làm tổng tăng `k*delta`.
- Với min/max: thêm `delta` cho **mọi** phần tử làm min/max tăng `delta`.
- Với gcd: thêm `delta` cho mọi phần tử **không có công thức đơn giản** chỉ dựa vào gcd cũ.
- Với ghép chuỗi: “cộng delta” không có ý nghĩa chung nếu chưa đặc tả kiểu dữ liệu và update.

Muốn hỗ trợ lazy đúng, phải xác định **phép cập nhật tác động lên bản tóm tắt** ra sao và **nhiều cập nhật hợp thành** theo thứ tự như thế nào.

## 20. So sánh với các cấu trúc truy vấn đoạn khác

Phân rã căn bậc hai không thay thế mọi cấu trúc, nhưng nó là điểm trung gian dễ triển khai và dễ kiểm chứng.

| Cấu trúc | Xây dựng | Tổng đoạn | Gán/cộng một điểm | Cộng đoạn | Bộ nhớ phụ tiêu biểu |
|---|---:|---:|---:|---:|---:|
| Quét mảng | O(1) ngoài mảng | O(k) | O(1) | O(k) | O(1) |
| Tổng tiền tố tĩnh | O(n) | **O(1)** | O(n) để duy trì bảng | O(n) theo cách trực tiếp | O(n) |
| Mảng hiệu theo lô | O(n) khởi tạo/đầu ra | Không online trực tiếp | Tùy thiết kế | **O(1)** ghi mốc | O(n) |
| Sqrt decomposition tổng | O(n) | **O(√n)** | **O(1)** | O(k) nếu sửa trực tiếp | O(n/B) tóm tắt |
| Sqrt decomposition lazy cộng | O(n) | **O(√n)** | **O(1)** | **O(√n)** | O(n/B) tóm tắt + tag |
| Fenwick tree cho tổng | O(n) nếu xây tối ưu | O(log n) | O(log n) | Cần biến thể riêng | O(n) |
| Segment tree tổng | O(n) | O(log n) | O(log n) | Cần lazy hoặc biến thể | O(n) |
| Sparse table min tĩnh | O(n log n) | O(1) cho min | Không thiết kế cập nhật | Không | O(n log n) |

Ở bảng, `k=r-l`. Cột bộ nhớ phụ cho sqrt decomposition **không tính bản sao mảng gốc O(n)** nếu triển khai sao chép dữ liệu như mã Python ở trên; nếu tính cả bản sao, tổng bộ nhớ của cấu trúc là O(n).

### Khi nào sqrt decomposition đáng dùng?

- Muốn có lời giải **dễ kiểm thử**, cấu trúc ít phức tạp.
- `n` vừa phải; O(√n) đủ đáp ứng giới hạn thời gian.
- Cần nhiều dạng bản tóm tắt hoặc thao tác theo khối.
- Các phép cập nhật/truy vấn cho phép thiết kế **lazy đơn giản**.
- Không cần tối ưu tới O(log n) mỗi thao tác như Fenwick hoặc segment tree.

### Khi nào cân nhắc phương án khác?

- Mảng **không đổi**, chỉ hỏi tổng: tổng tiền tố O(1) mỗi truy vấn thường tốt hơn.
- Số cập nhật và truy vấn cực lớn, cần O(log n) thay vì O(√n): Fenwick/segment tree đáng cân nhắc.
- Chỉ ghi cộng đoạn theo lô và cuối cùng mới xuất kết quả: mảng hiệu O(1) cập nhật hợp lý hơn.
- Nhiều truy vấn min tĩnh: sparse table có thể cho O(1) sau tiền xử lý.

Lựa chọn cuối phụ thuộc vào **giới hạn n, số thao tác, phép gộp, kiểu cập nhật và tính online/offline**.

## 21. Tính kết hợp và thứ tự khối

Trong các ví dụ tổng/min, phép gộp có tính **kết hợp**, nghĩa là:

```text
(x ⊕ y) ⊕ z = x ⊕ (y ⊕ z)
```

Vì thế việc chia một đoạn thành những khối rời và phần biên rồi gộp lại là đúng.

Tuy nhiên, tính kết hợp **không có nghĩa giao hoán**. Nếu phép gộp là **nối chuỗi**, phải giữ đúng thứ tự:

```text
Phần biên trái
    ⊕ khối nguyên vẹn theo thứ tự tăng vị trí
    ⊕ phần biên phải
```

Không được đảo các khối vì `"ab"+"cd"` khác `"cd"+"ab"`.

Đối với phép gộp bất kỳ, cần:

1. Một phép gộp kết hợp trên các bản tóm tắt.
2. Phần tử đơn vị cho đoạn rỗng nếu API hỗ trợ.
3. Bất biến bản tóm tắt khối.
4. Cách duy trì bản tóm tắt khi cập nhật.
5. Nếu lazy, cách tác động của update lên từng bản tóm tắt.

**Đặc biệt:** một phép không kết hợp như phép trừ lặp thông thường không thể gộp tùy ý theo khối rồi mong giữ kết quả của phép trừ trái sang phải. Muốn tối ưu phải thiết kế dạng tóm tắt khác có phép gộp kết hợp.

## 22. Lỗi biên thường gặp khi triển khai

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng `B=0` khi n=0 | Chia cho 0 | Chọn B tối thiểu 1 |
| Tính `m=n//B` mà bỏ phần dư | Mất khối cuối ngắn | `m=(n+B-1)//B` |
| Truy vấn khối cuối như đủ B phần tử | Đọc vượt mảng hoặc cộng sai | Dùng min(n,(b+1)B) khi cần |
| Đưa tổng của khối chỉ bị phủ một phần vào đáp án | Cộng thừa phần tử ngoài đoạn | Quét phần không trọn khối |
| Trong `[l,r)` lại lấy `a[r]` | Off-by-one, có thể vượt mảng | Biên phải exclusive |
| Không kiểm tra `l>r` | Trả kết quả im lặng cho đoạn sai | Kiểm tra `0<=l<=r<=n` |
| Cho chỉ số âm chạy như Python slicing | Kết quả không theo hợp đồng toán học | Từ chối biên âm |
| Nhầm `point_assign` với `point_add` | Giá trị và tổng khối sai | Với assign, dùng `new-old` |
| Cập nhật a mà quên `block_sum` | Truy vấn sau đó lỗi thời | Duy trì bất biến mọi khối |
| Cộng `delta` cho toàn khối rồi còn sửa từng phần tử raw cùng khối | Cộng hai lần | Phân biệt nhánh full/lẻ |
| Truy vấn full lazy chỉ dùng `raw_sum` | Bỏ sót lazy | Cộng `lazy*độ dài khối` |
| Truy vấn phần tử lazy chỉ dùng `raw[i]` | Trả giá trị cũ | Dùng `raw[i]+lazy[b]` |
| Gán điểm trong khối có lazy mà đặt thẳng raw=value | Giá trị logic thành `value+lazy` | Đặt `raw=value-lazy` |
| Với khối cuối ngắn dùng `B*lazy` trong tổng toàn khối | Đếm thừa tác động | Nhân độ dài thật |
| Dùng `min` cũ sau khi tăng phần tử nhỏ nhất | Min khối sai | Quét lại khối hoặc giữ cấu trúc phụ |
| Cho rằng mọi cập nhật min là O(1) | Báo sai độ phức tạp | Cận đơn giản O(B) |
| Dùng `B≈√n` như tối ưu tuyệt đối | Chậm với workload đặc thù | Đo benchmark/tính tỉ lệ thao tác |
| Cho rằng mỗi truy vấn luôn phải quét cả biên | Báo số bước không chính xác | O(B+n/B) là cận trên |
| Bỏ qua đầu ra O(q) khi lưu q câu trả lời | Báo thiếu bộ nhớ | Tách cấu trúc/đầu ra |
| Dùng sqrt decomposition để xử lý đồ thị tùy ý như các đoạn liên tiếp | Sai mô hình dữ liệu | Xác nhận có thứ tự chỉ số liên tiếp |

## 23. Kiểm thử bằng cách đối chiếu với quét trực tiếp

Một cấu trúc tối ưu rất nên có **bản thực thi đơn giản làm chuẩn** (*oracle*) để phát hiện lỗi, đặc biệt là khối cuối và các đoạn có biên trùng ranh giới khối.

### Kiểm tra mọi đoạn của một mảng nhỏ

```python
values = [4, -1, 7, 2, 9, 3, 5, -2, 6, 1]
ds = SqrtRangeSum(values, block_size=4)

for l in range(len(values) + 1):
    for r in range(l, len(values) + 1):
        assert ds.range_sum(l, r) == sum(values[l:r])
```

### Đối chiếu sau các cập nhật điểm

```python
reference = list(values)
ds = SqrtRangeSum(values, block_size=3)

for i, new_value in [(0, 100), (4, -20), (9, 7), (5, 0)]:
    reference[i] = new_value
    ds.point_assign(i, new_value)

    for l in range(len(reference) + 1):
        for r in range(l, len(reference) + 1):
            assert ds.range_sum(l, r) == sum(reference[l:r])
```

### Đối chiếu lazy range add

```python
reference = [4, -1, 7, 2, 9, 3, 5, -2, 6, 1]
lazy_ds = LazySqrtRangeSum(reference, block_size=4)

updates = [
    (0, 10, 5),
    (2, 7, -3),
    (3, 3, 99),    # Đoạn rỗng.
    (7, 10, 2),    # Chạm khối cuối ngắn.
    (4, 8, -1),    # Khối đầy đủ.
]

for l, r, delta in updates:
    for i in range(l, r):
        reference[i] += delta
    lazy_ds.range_add(l, r, delta)

    assert lazy_ds.materialize() == reference

    for ql in range(len(reference) + 1):
        for qr in range(ql, len(reference) + 1):
            assert lazy_ds.range_sum(ql, qr) == sum(reference[ql:qr])
```

Các vòng kiểm tra trên chỉ nên chạy cho **mảng nhỏ trong giai đoạn kiểm thử**, vì duyệt mọi cặp biên có O(n²) truy vấn. Đây không phải chiến lược trả lời truy vấn hiệu quả khi sản xuất.

### Những trường hợp quan trọng

- `n=0`, `n=1`, n là số chính phương, n không chia hết cho B.
- `B=1` và B lớn hơn n.
- Truy vấn rỗng, toàn mảng, nằm trong một khối, bắt đầu/kết thúc đúng ranh giới.
- Gán/cộng một điểm ở phần tử đầu, cuối và phần tử chứa min hiện tại.
- Cập nhật đoạn phủ đúng một khối, chỉ một phần khối, toàn mảng, đoạn rỗng.
- Lượng cộng âm, bằng 0 và các cập nhật chồng nhau.
- Truy vấn sau khi cập nhật để phát hiện bản tóm tắt/lazy lỗi thời.

## 24. Phân tích ví dụ nhiều truy vấn và cập nhật

Giả sử `n=100.000`, chọn `B≈317`; có `q=20.000` truy vấn tổng và `u=5.000` cập nhật điểm.

### Quét trực tiếp

Nếu một truy vấn thường dài gần n, tổng công việc có thể gần:

```text
q*n = 20.000 * 100.000 = 2.000.000.000
```

lượt xét phần tử, chưa tính chi phí thao tác khác.

### Sqrt decomposition

Một cận sơ bộ cho truy vấn:

```text
B + n/B ≈ 317 + 315,5 ≈ 632,5
```

đơn vị công việc đại diện, còn cập nhật điểm cho tổng chỉ O(1). Tổng công việc truy vấn được giảm đáng kể so với quét n phần tử cho mỗi câu hỏi.

Đây **không phải** ước lượng thời gian chạy chính xác: hệ số vòng lặp, nhánh điều kiện, kiểu dữ liệu và chi phí truy cập bộ nhớ ảnh hưởng lớn đến hiệu năng thực tế.

### Nếu cần nhanh hơn nữa

Fenwick tree hoặc segment tree có O(log n) thao tác cho các bài toán tổng và cập nhật điểm phù hợp, thường tốt hơn về bậc so với O(√n) khi `n` và số truy vấn rất lớn. Nhưng sqrt decomposition vẫn có ưu thế **mã dễ tiếp cận, dễ thay đổi ý nghĩa bản tóm tắt khối và dễ kiểm chứng với oracle**.

## 25. Bài tập tự luyện có lời giải

**Bài 1 — Chọn khối.** Với `n=10, B=4`, có bao nhiêu khối? Viết các đoạn chỉ số của chúng.

*Lời giải:* `ceil(10/4)=3` khối: **`[0,4)`, `[4,8)`, `[8,10)`**.

**Bài 2 — Khối của một chỉ số.** Với `B=4`, vị trí `i=9` thuộc khối nào?

*Lời giải:* `9//4=2`, là **khối 2**, đoạn `[8,10)`.

**Bài 3 — Tổng khối.** Cho `a=[4,-1,7,2,9,3,5,-2,6,1]` và `B=4`. Tính `block_sum`.

*Lời giải:* **`[12,15,7]`**.

**Bài 4 — Truy vấn bằng phần biên.** Tính tổng `[2,9)` bằng cách dùng các khối ở bài 3.

*Lời giải:* Biên trái `7+2=9`, khối `[4,8)` có tổng 15, biên phải `6`. Tổng **`9+15+6=30`**.

**Bài 5 — Đoạn khớp một khối.** Với dữ liệu trên, tổng `[4,8)` là bao nhiêu?

*Lời giải:* Đây là khối 1 nguyên vẹn, lấy **`block_sum[1]=15`**.

**Bài 6 — Đoạn rỗng.** Truy vấn `[10,10)` trên mảng 10 phần tử có hợp lệ không và trả gì với sum?

*Lời giải:* **Hợp lệ**, không chứa phần tử; tổng bằng **0**.

**Bài 7 — Gán một điểm.** Trong ví dụ chính, `a[5]` đổi từ 3 thành 10. Tổng khối 1 thay đổi ra sao?

*Lời giải:* Hiệu `delta=10-3=7`, nên `block_sum[1]=15+7=22`.

**Bài 8 — Cộng một điểm.** Nếu sau đó cộng `-3` vào `a[9]`, tổng khối 2 thành bao nhiêu?

*Lời giải:* `7-3=4`, và `a[9]` từ 1 thành -2.

**Bài 9 — Tính B.** Với `n=10.000`, chọn `B=100` thì chỉ báo `B+n/B` là bao nhiêu?

*Lời giải:* `100+10000/100=200`.

**Bài 10 — B quá nhỏ.** Với `n=10.000, B=1`, vì sao truy vấn dài có thể chậm?

*Lời giải:* Có tới `10.000` khối, nên quét qua các khối nguyên vẹn mất **O(n)** thay vì O(√n).

**Bài 11 — B quá lớn.** Với `B=n`, vì sao truy vấn lệch biên vẫn có thể O(n)?

*Lời giải:* Một phần biên có thể phải quét gần n phần tử; việc chỉ có một khối không giúp ích cho những truy vấn không phủ trọn khối.

**Bài 12 — Cân bằng.** Từ biểu thức `B+n/B`, suy ra lựa chọn B có bậc nào?

*Lời giải:* Cho hai thành phần cùng bậc: `B≈n/B`, nên **`B≈√n`**, tổng chi phí O(√n).

**Bài 13 — Min update.** Vì sao gán phần tử nhỏ nhất của một khối thành số lớn hơn có thể cần O(B) để cập nhật `block_min`?

*Lời giải:* Min cũ có thể biến mất; chỉ từ min cũ và giá trị mới không xác định được phần tử nhỏ nhất kế tiếp. Có thể phải **quét lại cả khối**.

**Bài 14 — Tỷ lệ thao tác.** Với `q` truy vấn min và `u` cập nhật điểm, nếu mô hình chi phí `q*n/B+(q+u)*B` thì B nên xấp xỉ bao nhiêu?

*Lời giải:* **`sqrt(q*n/(q+u))`**, nếu `q+u>0`; làm tròn và giới hạn vào miền hợp lệ.

**Bài 15 — Lazy full block.** Một khối bốn phần tử có tổng raw 15 và `lazy=+5`. Tổng logic của khối?

*Lời giải:* `15+5*4=35`.

**Bài 16 — Lazy khối cuối.** Khối cuối chỉ có hai phần tử, `raw_sum=7` và `lazy=+5`. Tổng logic là bao nhiêu?

*Lời giải:* `7+5*2=17`, **không** phải `7+5*B` nếu B=4.

**Bài 17 — Lazy partial update.** Khi chỉ cộng vào hai phần tử của một khối đang có lazy tag, có bắt buộc đẩy lazy về toàn khối không trong mô hình `actual=raw+lazy`?

*Lời giải:* **Không.** Cộng trực tiếp delta vào hai giá trị raw và cập nhật raw_sum tương ứng; giữ nguyên lazy vẫn bảo toàn bất biến.

**Bài 18 — Point assign với lazy.** Nếu `lazy[b]=5` và muốn một phần tử có giá trị logic bằng 20, phải gán `raw[i]` bằng bao nhiêu?

*Lời giải:* **15**, vì `raw[i]+5=20`.

**Bài 19 — Online range add và sum.** Biến thể lazy theo khối có cận thời gian nào cho cả hai thao tác nếu `B≈√n`?

*Lời giải:* **O(√n)** cho mỗi range add và range sum; khởi tạo O(n).

**Bài 20 — So sánh mảng hiệu.** Nếu có q phép cộng đoạn, chỉ muốn xuất mảng cuối một lần, vì sao mảng hiệu có thể tốt hơn lazy sqrt?

*Lời giải:* Mảng hiệu ghi mỗi cập nhật **O(1)**, cuối cùng dựng O(n), tổng O(n+q). Lazy sqrt tốn O(√n) mỗi cập nhật nhưng hỗ trợ truy vấn **online**.

**Bài 21 — Thứ tự với nối chuỗi.** Nếu lưu chuỗi nối của từng khối, có được gộp khối phải trước khối trái không?

*Lời giải:* **Không.** Phép nối kết hợp nhưng không giao hoán, phải giữ đúng thứ tự vị trí tăng.

**Bài 22 — n=0.** Vì sao khi n=0 vẫn nên đặt B=1 thay vì B=0?

*Lời giải:* Tránh phép chia cho 0 trong `i//B` và khi tính số khối; mảng không có khối và chỉ có truy vấn rỗng `[0,0)`.

**Bài 23 — Bất biến.** Hãy nêu bất biến đủ để chứng minh truy vấn tổng đọc khối nguyên vẹn là đúng.

*Lời giải:* **`block_sum[b]` bằng tổng tất cả phần tử thật thuộc khối b**. Khi truy vấn lấy trọn khối ấy, một lần đọc `block_sum[b]` tương đương việc cộng từng phần tử trong khối.

**Bài 24 — Kiểm tra.** Nêu ba tình huống dễ phát hiện lỗi triển khai phân khối.

*Lời giải:* Ví dụ: **khối cuối ngắn hơn B**, **đoạn rỗng `[l,l)`**, và **truy vấn bắt đầu/kết thúc đúng ranh giới khối**. Có thể thêm cập nhật điểm sau khi đã xây bản tóm tắt và lazy tag chưa được đẩy.

## 26. Tổng kết

**Phân rã căn bậc hai** chia mảng dài `n` thành các khối liên tiếp có kích thước mục tiêu `B`, lưu thông tin gộp của từng khối và trả lời truy vấn bằng **phần tử ở biên + các khối trọn vẹn**. Với bất biến tổng khối, phép **gán/cộng một điểm** có thể O(1), còn truy vấn tổng tốn **O(B+n/B)**. Chọn **`B≈√n`** cân bằng hai nguồn chi phí và đạt **O(√n)** cho truy vấn trong trường hợp xấu nhất.

Lựa chọn kích thước khối không chỉ dựa vào n. Với min/max cần quét lại khối sau cập nhật tùy ý, chi phí cập nhật O(B) có thể làm ta chọn khối nhỏ hơn khi số lần cập nhật lớn. Với **lazy cộng theo khối**, ta có thể hỗ trợ **cộng đoạn và tổng đoạn online** cùng O(√n), bằng bất biến `actual[i]=raw[i]+lazy[block(i)]` và `raw_sum[b]=sum(raw trong khối b)`.

Quan trọng nhất là **không đánh mất phần tử ở ranh giới**: đoạn `[l,r)` không chứa `r`; khối cuối có thể ngắn; những khối chỉ bị phủ một phần phải được xử lý khác khối trọn vẹn. Trước khi tối ưu, hãy xác định **phép gộp, loại cập nhật, chính sách đoạn rỗng, chi phí duy trì bản tóm tắt và tỷ lệ query/update**. Đó là cơ sở để chọn đúng B, hoặc quyết định chuyển sang prefix sum, Fenwick tree hay segment tree.

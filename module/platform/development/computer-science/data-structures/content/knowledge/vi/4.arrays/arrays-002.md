# Độ dài, chỉ số hợp lệ và quy ước khoảng nửa kín

## 1. Vì sao cần một quy ước thống nhất?

Khi xử lý mảng, nhiều lỗi xuất hiện chỉ vì nhầm lẫn giữa **số lượng phần tử**, **chỉ số của một phần tử** và **ranh giới của một đoạn**. Ví dụ, mảng có `5` phần tử nhưng không có phần tử ở chỉ số `5` nếu đếm từ `0`. Tuy vậy, số `5` lại là cận phải hoàn toàn hợp lệ của đoạn chứa cả mảng: `[0, 5)`.

Quy ước **khoảng nửa kín** (*half-open interval*) giải quyết sự nhập nhằng đó. Một khoảng `[l, r)` bao gồm `l` nhưng không bao gồm `r`. Nhờ vậy, độ dài của đoạn luôn là `r - l`, hai đoạn kề nhau có thể ghép trực tiếp và các trường hợp rỗng trở nên dễ biểu diễn.

Sau bài này, bạn có thể:

- Phân biệt độ dài `n`, chỉ số phần tử `i` và cận đoạn `l`, `r`.
- Nêu đúng điều kiện truy cập `0 <= i < n` và điều kiện một đoạn hợp lệ `0 <= l <= r <= n`.
- Dùng khoảng `[l, r)` để duyệt, cắt, chia và ghép các đoạn mảng.
- Xác định các trường hợp biên: mảng rỗng, đoạn rỗng, phần tử đầu, phần tử cuối, cận phải bằng `n`.
- Áp dụng bất biến khoảng nửa kín trong tính tổng đoạn và tìm kiếm nhị phân.

Đây là một nền tảng của học phần **cấu trúc dữ liệu**: từ mảng, danh sách liên kết, stack, queue đến bảng băm, cây, heap và đồ thị, việc xác định ranh giới và bất biến giúp chúng ta chứng minh thao tác đúng và đánh giá độ phức tạp thời gian, bộ nhớ.

## 2. Độ dài khác với chỉ số lớn nhất

Giả sử mảng `A` có `n` phần tử và dùng cách đánh chỉ số từ `0`:

\[
A = [a_0, a_1, \ldots, a_{n-1}]
\]

**Độ dài** (*length*) `n` là số phần tử hiện có. **Chỉ số hợp lệ** là số nguyên `i` thỏa:

\[
0 \le i < n
\]

Ví dụ:

```text
Giá trị:   [ 7, 12,  5, 12,  9 ]
Chỉ số:      0   1   2   3   4
            └───────────────┘
                 n = 5
```

| Đại lượng | Giá trị | Giải thích |
|---|---|---|
| `n` | `5` | Tổng số phần tử |
| Chỉ số đầu tiên | `0` | Truy cập `A[0]` cho giá trị `7` |
| Chỉ số cuối cùng | `n - 1 = 4` | Truy cập `A[4]` cho giá trị `9` |
| `A[5]` | Không hợp lệ | `5` bằng độ dài, nằm ngoài miền chỉ số |
| `A[-1]` | Ngoài mô hình chỉ số `0..n-1` | Một số ngôn ngữ có quy tắc riêng cho chỉ số âm |

Nếu `n = 0`, mảng không có phần tử và **không tồn tại chỉ số hợp lệ**. Công thức `n - 1` khi ấy cho `-1`, nhưng `-1` không phải “chỉ số cuối” của một phần tử có thật.

### Độ dài và sức chứa

Với **mảng động**, cần tách độ dài (*length* hoặc *size*) khỏi sức chứa (*capacity*):

- `length = 5`: có năm phần tử được phép truy cập, theo chỉ số `0..4`.
- `capacity = 8`: vùng lưu trữ đã dự phòng đủ chỗ cho tám phần tử, nhưng ba ô dự phòng chưa làm phát sinh các chỉ số `5`, `6`, `7` hợp lệ.

Việc thay đổi sức chứa hoặc thêm, xóa phần tử có thể ảnh hưởng cách lưu trữ hoặc độ dài. Khi kiểm tra chỉ số, ta dựa trên **độ dài hiện tại** chứ không dựa trên dung lượng đã cấp phát.

## 3. Ký hiệu `[l, r)` có nghĩa chính xác là gì?

Trong ký hiệu `[l, r)`, dấu `[` tại `l` nghĩa là **lấy cận trái**, còn dấu `)` tại `r` nghĩa là **không lấy cận phải**. Đối với các chỉ số nguyên:

\[
[l,r)=\{l, l+1, \ldots, r-1\} \quad \text{khi } l<r
\]

Đoạn này tương ứng với các phần tử `A[l]`, `A[l+1]`, ..., `A[r-1]`. Điều kiện để nó là một đoạn hợp lệ trong mảng độ dài `n` là:

\[
0 \le l \le r \le n
\]

**Số phần tử trong đoạn** được tính trực tiếp:

\[
\operatorname{length}([l,r))=r-l
\]

Ví dụ với `A = [7, 12, 5, 12, 9]` (`n = 5`):

```text
Chỉ số       0    1    2    3    4   | 5 là ranh giới cuối
Giá trị      7   12    5   12    9   |

[1, 4)           [12,   5,  12]       → 3 phần tử
[0, 5)      [ 7, 12,   5,  12,  9]   → 5 phần tử
[3, 3)                       ∅        → 0 phần tử
```

| Khoảng | Các chỉ số được chọn | Độ dài | Hợp lệ với `n = 5`? |
|---|---|---:|---|
| `[0, 5)` | `0, 1, 2, 3, 4` | `5` | Có, toàn bộ mảng |
| `[1, 4)` | `1, 2, 3` | `3` | Có |
| `[4, 5)` | `4` | `1` | Có, phần tử cuối |
| `[2, 2)` | Không có | `0` | Có, đoạn rỗng |
| `[5, 5)` | Không có | `0` | Có, đoạn rỗng ở cuối |
| `[2, 6)` | — | — | Không, `r > n` |
| `[4, 2)` | — | — | Không, `l > r` |

Điểm dễ nhầm nhất: **`r = n` là cận phải hợp lệ, nhưng `A[n]` không phải truy cập hợp lệ**. Trong `[0, n)`, ta dừng *trước* `n`.

### So sánh với khoảng đóng `[l, r]`

Một số đề bài diễn đạt “lấy từ phần tử `l` đến phần tử `r`, tính cả hai đầu” và sử dụng khoảng đóng `[l, r]`. Với `l <= r`, khoảng đóng có `r - l + 1` chỉ số; khoảng nửa kín `[l, r)` có `r - l` chỉ số.

| Tình huống | Khoảng đóng | Khoảng nửa kín |
|---|---|---|
| Lấy phần tử từ chỉ số `2` tới `4`, kể cả `4` | `[2, 4]` | `[2, 5)` |
| Lấy toàn mảng độ dài `n > 0` | `[0, n-1]` | `[0, n)` |
| Lấy đúng một phần tử ở chỉ số `k` | `[k, k]` | `[k, k+1)` |
| Biểu diễn đoạn rỗng | Cần quy ước riêng, chẳng hạn `l > r` | `[k, k)` với `0 <= k <= n` |

Chuyển đổi từ đoạn đóng `[l, r]` sang đoạn nửa kín `[l, r+1)` chỉ đúng khi `l, r` là các chỉ số hợp lệ và **cả hai đầu đều được tính**. Nếu đề bài đã dùng cận phải loại trừ thì không cộng thêm `1` lần nữa.

## 4. Ba lợi ích lớn của khoảng nửa kín

### Lợi ích 1: Độ dài là phép trừ

Một đoạn `[3, 8)` luôn có `8 - 3 = 5` vị trí: `3`, `4`, `5`, `6`, `7`. Quy tắc này vẫn đúng với đoạn rỗng `[3, 3)`, vì `3 - 3 = 0`. Ta không cần công thức riêng cho trường hợp đoạn rỗng.

### Lợi ích 2: Chia đoạn không trùng, không sót

Với `l <= m <= r`, ta có thể chia đoạn `[l, r)` thành hai đoạn liền nhau:

\[
[l,r) = [l,m) \cup [m,r)
\]

Hai đoạn không chia sẻ phần tử nào; `m` chỉ xuất hiện ở đoạn bên phải. Tổng độ dài cũng được bảo toàn:

\[
(m-l)+(r-m)=r-l
\]

```text
         [l,                 r)
          l   l+1  ...  m-1  m   ...  r-1
         └──── [l, m) ────┘└─ [m, r) ─┘
```

Đây là lý do nhiều thuật toán **chia để trị** và **tìm kiếm nhị phân** thích sử dụng khoảng nửa kín: điểm chia `m` luôn có vai trò rõ ràng.

### Lợi ích 3: Nối các đoạn liền kề rất tự nhiên

Hai đoạn `[0, 3)` và `[3, 7)` nối thành `[0, 7)`, không cần sửa lại cận. Khi xử lý dữ liệu theo lô, ta có thể dùng `[0, k)`, `[k, 2k)`, ... và điều chỉnh cận phải của lô cuối bằng `min(..., n)`.

Ví dụ, phân chia mảng `10` phần tử thành từng nhóm tối đa `4` phần tử:

```text
[0, 4)  →  0, 1, 2, 3
[4, 8)  →  4, 5, 6, 7
[8,10)  →  8, 9
```

Các nhóm không chồng lấn và bao phủ chính xác `[0, 10)`.

## 5. Viết vòng lặp đúng theo chỉ số

Trong Python, `range(start, stop)` cũng tuân theo quy ước lấy `start` nhưng không lấy `stop`. Vì vậy, `range(n)` tạo các số `0, 1, ..., n-1` nếu `n > 0`.

```python
values = [7, 12, 5, 12, 9]
n = len(values)

# Duyệt cả mảng: các chỉ số thuộc [0, n).
for i in range(n):
    print(i, values[i])

# Duyệt các chỉ số thuộc [1, 4): 1, 2, 3.
for i in range(1, 4):
    print(values[i])

# Đoạn rỗng: vòng lặp không chạy lần nào.
for i in range(3, 3):
    print("Dòng này không xuất hiện")
```

Khi có thể, duyệt giá trị trực tiếp bằng `for value in values` hoặc lấy cả chỉ số và giá trị bằng `enumerate(values)`. Tuy nhiên, khi thuật toán cần tính theo vị trí, bất biến `0 <= i < n` vẫn là cơ sở để bảo đảm truy cập hợp lệ.

### Cắt mảng bằng lát cắt

Python sử dụng cùng quy ước cho lát cắt `values[l:r]`:

```python
values = [7, 12, 5, 12, 9]
print(values[1:4])  # [12, 5, 12]
print(values[0:5])  # [7, 12, 5, 12, 9]
print(values[5:5])  # []
```

Lưu ý về **chi phí**: truy cập một phần tử `values[i]` thường là `O(1)`, còn lấy lát cắt của Python `list` thông thường **tạo danh sách mới**, nên cần thời gian và bộ nhớ `O(r-l)` cho đoạn hợp lệ dài `r-l`. Nếu chỉ cần duyệt, dùng `range(l, r)` hoặc một giao diện xem đoạn (*view*) phù hợp để tránh bản sao không cần thiết.

Đối với Python, chỉ số âm có ý nghĩa đặc biệt và lát cắt có thể tự điều chỉnh cận nằm ngoài phạm vi. Đó là quy tắc của cú pháp ngôn ngữ; khi thiết kế thuật toán theo mảng trừu tượng, hãy tự giữ điều kiện `0 <= l <= r <= n` để hành vi nhất quán giữa các ngôn ngữ.

## 6. Kiểm tra giới hạn trước khi truy cập

Hai phép kiểm tra trông giống nhau nhưng dùng cho hai loại đầu vào khác nhau:

```python
def read_at(values: list[int], index: int) -> int:
    """Đọc đúng một phần tử."""
    if not 0 <= index < len(values):
        raise IndexError("Chỉ số nằm ngoài mảng")
    return values[index]


def sum_interval(values: list[int], left: int, right: int) -> int:
    """Tính tổng đoạn [left, right)."""
    if not 0 <= left <= right <= len(values):
        raise ValueError("Khoảng không hợp lệ")
    total = 0
    for i in range(left, right):
        total += values[i]
    return total


data = [7, 12, 5, 12, 9]
print(read_at(data, 4))          # 9
print(sum_interval(data, 2, 5))  # 26 = 5 + 12 + 9
print(sum_interval(data, 5, 5))  # 0 (đoạn rỗng)
```

Hàm `read_at` kiểm tra **một chỉ số**: `index < n`. Hàm `sum_interval` kiểm tra **hai ranh giới**: `right <= n`. Nếu đổi `right <= n` thành `right < n`, chương trình sẽ từ chối sai đoạn `[0, n)` vốn hợp lệ.

Nếu đầu vào từ người dùng là **số thứ tự phần tử tính từ 1**, cần kiểm tra `1 <= k <= n` rồi truy cập `A[k-1]`. Đừng dùng `k` trực tiếp làm chỉ số. Ví dụ phần tử thứ `3` là `A[2]`.

Khi thêm hoặc xóa phần tử trong lúc duyệt, độ dài và vị trí các phần tử có thể thay đổi. Hãy xác định rõ vòng lặp dùng độ dài ở thời điểm nào và các phần tử có dịch chuyển không; nếu không, chương trình dễ bỏ sót hoặc truy cập sai sau khi cập nhật mảng.

## 7. Ứng dụng: tổng đoạn với mảng cộng dồn

Giả sử thường xuyên phải trả lời câu hỏi “tổng các giá trị trong đoạn `[l, r)` là bao nhiêu?”. Duyệt trực tiếp mất `O(r-l)` thời gian mỗi truy vấn. **Mảng cộng dồn** (*prefix sum*) biến mỗi truy vấn thành `O(1)` sau một bước chuẩn bị `O(n)`.

Tạo mảng `P` có `n + 1` phần tử:

\[
P[0]=0, \qquad P[k]=\sum_{i=0}^{k-1}A[i] \quad (1\le k\le n)
\]

`P[k]` chứa tổng trên đoạn `[0, k)`, vì vậy:

\[
\operatorname{sum}(l,r)=P[r]-P[l]
\]

```python
def make_prefix_sums(values: list[int]) -> list[int]:
    prefix = [0]
    for value in values:
        prefix.append(prefix[-1] + value)
    return prefix


def range_sum(prefix: list[int], left: int, right: int) -> int:
    n = len(prefix) - 1
    if not 0 <= left <= right <= n:
        raise ValueError("Khoảng không hợp lệ")
    return prefix[right] - prefix[left]


data = [3, 1, 4, 1, 5]
prefix = make_prefix_sums(data)    # [0, 3, 4, 8, 9, 14]
print(range_sum(prefix, 1, 4))    # 6 = 1 + 4 + 1
print(range_sum(prefix, 0, 5))    # 14 (toàn bộ mảng)
print(range_sum(prefix, 3, 3))    # 0 (đoạn rỗng)
```

Ở đây `P[n]` **truy cập được** vì `P` có độ dài `n+1`; ngược lại, `A[n]` vẫn nằm ngoài mảng gốc. Mảng phụ cần thêm `O(n)` bộ nhớ. Nếu giá trị trong `A` thay đổi, các tổng cộng dồn liên quan cũng cần được cập nhật hoặc tính lại; khi có nhiều phép cập nhật lẫn truy vấn, nên cân nhắc cấu trúc như Fenwick tree hoặc segment tree ở các bài học nâng cao.

## 8. Ứng dụng: tìm kiếm nhị phân với đoạn `[left, right)`

Cho mảng đã **sắp xếp tăng dần**, hãy tìm vị trí đầu tiên mà giá trị không nhỏ hơn `target` (còn gọi là *lower bound*). Nếu mọi phần tử đều nhỏ hơn `target`, kết quả là `n`, tức vị trí có thể chèn thêm ở cuối.

Ta duy trì đoạn chỉ số ứng viên `[left, right)`:

```python
def lower_bound(values: list[int], target: int) -> int:
    left, right = 0, len(values)

    while left < right:
        mid = left + (right - left) // 2
        if values[mid] < target:
            left = mid + 1
        else:
            right = mid

    return left


sorted_data = [2, 4, 4, 7, 9]
print(lower_bound(sorted_data, 4))   # 1
print(lower_bound(sorted_data, 8))   # 4
print(lower_bound(sorted_data, 10))  # 5
```

Tại mỗi lần lặp, bất biến bao gồm `0 <= left <= right <= n`, và vị trí đầu tiên có giá trị `>= target` (nếu có) vẫn nằm trong đoạn ứng viên. Khi `left < right`, ta có `left <= mid < right <= n`, nên `values[mid]` chắc chắn là truy cập hợp lệ. Sau mỗi lần so sánh, đoạn ứng viên ngắn đi và thuật toán kết thúc sau `O(log n)` bước.

Giá trị trả về `5` trong ví dụ cuối là **cận chèn hợp lệ**, không phải chỉ số phần tử có sẵn. Nếu muốn truy cập `values[pos]`, phải kiểm tra `pos < len(values)` trước. Trường hợp mảng rỗng (`n = 0`) cũng xử lý được ngay: `left == right == 0`, vòng lặp không chạy và hàm trả về `0`.

## 9. Lỗi lệch một đơn vị (*off-by-one*) thường gặp

| Sai lầm | Tác động | Quy tắc sửa |
|---|---|---|
| Duyệt `i = 0..n` rồi đọc `A[i]` | Đọc `A[n]` ngoài mảng | Duyệt `0 <= i < n` |
| Xem cận phải `r` của `[l, r)` là một phần tử | Đọc thừa một phần tử | Phần tử cuối đoạn là `A[r-1]` nếu `l < r` |
| Tính độ dài đoạn `[l, r)` bằng `r-l+1` | Đếm dư một phần tử | Độ dài là `r-l` |
| Không cho phép `right == n` | Bỏ mất đoạn đến cuối mảng | Điều kiện đoạn là `r <= n` |
| Mặc định đoạn `[k, k)` có một phần tử | Xử lý sai đoạn rỗng | `[k, k)` có `0` phần tử |
| Dùng `n-1` làm cận phải loại trừ cho toàn mảng | Bỏ qua phần tử cuối | Toàn mảng là `[0, n)` |
| Trộn chỉ số từ `0` và số thứ tự từ `1` | Đọc sai vị trí | Số thứ tự `k` đổi thành chỉ số `k-1` |

Một kỹ thuật kiểm tra nhanh là thử thuật toán với bốn trường hợp: mảng rỗng `[]`, mảng một phần tử `[x]`, đoạn rỗng `[k, k)` và đoạn toàn mảng `[0, n)`. Nếu thuật toán sai ở một trong bốn trường hợp này, hãy kiểm tra lại điều kiện vòng lặp và cách sử dụng `n`, `r`.

## 10. Tự luyện tập

Với mảng `B = [6, 2, 8, 3, 5, 9]` (`n = 6`):

1. Liệt kê các chỉ số hợp lệ. `B[6]` có hợp lệ không? Khoảng `[0, 6)` có hợp lệ không?
2. Đoạn `[2, 5)` chọn các giá trị nào và có độ dài bao nhiêu?
3. Hãy viết đoạn nửa kín tương đương với yêu cầu “lấy từ chỉ số `1` đến chỉ số `4`, kể cả hai đầu”.
4. Chia `[0, 6)` tại `m = 2` thành hai đoạn nửa kín. Tổng độ dài hai đoạn có bằng `6` không?
5. Đoạn `[6, 6)` chứa bao nhiêu phần tử? Có thể đọc `B[6]` dựa trên việc đoạn này hợp lệ không?
6. Nếu lập mảng cộng dồn `P` từ `B`, tính `P[5]-P[2]` và giải thích nó tương ứng với đoạn nào của `B`.

**Đáp án:** (1) `0, 1, 2, 3, 4, 5`; `B[6]` không hợp lệ, `[0, 6)` hợp lệ. (2) `[8, 3, 5]`, độ dài `3`. (3) `[1, 5)`. (4) `[0, 2)` và `[2, 6)`, độ dài `2 + 4 = 6`. (5) `0` phần tử; không thể đọc `B[6]`. (6) `P[5]-P[2] = 8 + 3 + 5 = 16`, là tổng trên `[2, 5)`.

## 11. Ghi nhớ

Với mảng đánh chỉ số từ `0` có độ dài `n`, **chỉ số hợp lệ** phải thỏa `0 <= i < n`, còn **đoạn nửa kín hợp lệ** phải thỏa `0 <= l <= r <= n`. Trong `[l, r)`, cận trái được lấy, cận phải bị loại trừ và số phần tử luôn là `r-l`. Sự khác biệt giữa **chỉ số phần tử** và **ranh giới đoạn** giải thích vì sao `[0, n)` chứa cả mảng nhưng `A[n]` không hợp lệ. Giữ đúng bất biến này giúp viết vòng lặp, chia đoạn, tính tổng và tìm kiếm nhị phân dễ kiểm chứng, hạn chế lỗi lệch một đơn vị khi triển khai thuật toán.

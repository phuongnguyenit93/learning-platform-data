# Mảng hiệu và cập nhật cả đoạn

Một hệ thống lưu doanh thu của từng ngày, lượng điện tiêu thụ theo giờ hay điểm số tại các vị trí trong một dãy. Người dùng liên tục yêu cầu: **“Cộng thêm 5 vào các ngày 3 đến 8”**, **“Giảm 2 đơn vị cho mọi vị trí trong đoạn [l,r)”**. Nếu mỗi yêu cầu đều chạy qua từng phần tử rồi sửa, một đoạn dài có thể làm tốn O(n) thời gian. Với rất nhiều lần cập nhật, tổng thời gian dễ tăng lên O(nq).

**Mảng hiệu** (*difference array*) cho phép biến thao tác **cộng cùng một lượng vào mọi phần tử của một đoạn** thành hai dấu mốc tại **đầu đoạn** và **ngay sau cuối đoạn**:

```text
diff[l] += delta
diff[r] -= delta            # Với đoạn nửa mở [l,r).
```

Các dấu mốc được cộng dồn **một lần ở cuối** để khôi phục lượng thay đổi tại từng vị trí. Nếu có `q` lệnh cập nhật trên mảng `n` phần tử, ta có thể thực hiện các thao tác này trong tổng thời gian **O(n+q)** thay vì O(nq) ở trường hợp xấu nhất.

Đây là kỹ thuật đặc biệt phù hợp với **cập nhật theo lô (*offline batch updates*)**: biết và xử lý nhiều lệnh cộng đoạn, rồi mới cần dãy kết quả cuối. **Mảng hiệu thuần túy không tự hỗ trợ truy vấn tổng đoạn trực tuyến O(1) sau mỗi cập nhật**. Phân biệt này quyết định khi nào nên dùng mảng hiệu và khi nào cần Fenwick tree hoặc segment tree.

Bài thuộc chương **Truy vấn đoạn** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mô-đun xây nền tảng qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, nhấn mạnh **bất biến, thao tác, độ phức tạp thời gian và bộ nhớ** để lựa chọn cấu trúc phù hợp. Trong bài, ta làm rõ định nghĩa, công thức, bằng chứng tính đúng, mã Python, quy ước biên, xử lý cập nhật chồng lấn, kiểm thử và những giới hạn của kỹ thuật.

## 1. Bài toán: cộng vào một đoạn liên tiếp

Cho mảng ban đầu gồm `n` số:

```text
a = [a[0], a[1], ..., a[n-1]]
```

Ta nhận những lệnh:

```text
range_add(l, r, delta)
```

Nghĩa là **tăng mỗi phần tử `a[i]` có `l <= i < r` lên đúng `delta`**, giữ nguyên những vị trí khác.

### Quy ước chỉ số

Trong toàn bài, ta dùng **0-based, đoạn nửa mở `[l,r)`**:

```text
0 <= l <= r <= n
```

- **Lấy đầu trái `l`**.
- **Không lấy đầu phải `r`**.
- `r=n` là hợp lệ.
- `l=r` là đoạn rỗng; cập nhật không thay đổi phần tử nào.

Ví dụ:

```text
Chỉ số:  0  1  2  3  4
Giá trị: 2  5  1  4  3

range_add(1,4,+3)

Trước:   2  5  1  4  3
Sau:     2  8  4  7  3
            ^  ^  ^
            1  2  3
```

Nếu áp dụng bằng vòng lặp:

```python
def range_add_slow(a, l, r, delta):
    for i in range(l, r):
        a[i] += delta
```

một lệnh có độ dài `k=r-l` sẽ tốn O(k) thời gian. Nếu có `q` lệnh, mỗi lệnh dài gần `n`, tổng thời gian là **O(nq)**.

Câu hỏi: có thể ghi nhận **tác động của cả đoạn** mà không sửa từng phần tử ngay lập tức không?

## 2. Trực giác: ghi lại nơi bắt đầu và nơi kết thúc tác động

Một lệnh cộng `delta` vào `[l,r)` tạo ra một **mức tăng thêm**:

```text
Vị trí i < l:        tăng 0
Vị trí l <= i < r:   tăng delta
Vị trí i >= r:       tăng 0
```

Nghĩa là tác động **bắt đầu** tại `l` và **kết thúc** tại `r`.

Thay vì lưu mức tăng ở mọi phần tử, ta chỉ ghi các **thay đổi của mức tăng**:

```text
Tại l:  +delta  (bật tác động)
Tại r:  -delta  (tắt tác động)
```

Sau đó, khi duyệt các vị trí từ trái sang phải, một biến `running` cộng dồn những mốc đã gặp. Mọi vị trí nằm giữa `l` và `r` tự động thấy mức tăng `delta`.

### Minh họa một lệnh

Cho `n=5`, cập nhật `[1,4)` thêm 3:

```text
Chỉ số:       0    1    2    3    4   | 5 (mốc cuối)
Mốc hiệu:     0   +3    0    0   -3   | 0

Cộng dồn:     0    3    3    3    0
```

Vì thế các vị trí 1,2,3 tăng 3, các vị trí 0,4 không đổi. Không cần đi qua từng vị trí của đoạn tại **thời điểm ghi cập nhật**.

### Tại sao không dùng một mốc `+delta`?

Nếu chỉ ghi `diff[l] += delta` mà không có dấu `-delta` ở `r`, mức tăng `delta` sẽ **kéo dài mãi đến cuối mảng**, kể cả những vị trí nằm ngoài đoạn mong muốn.

Dấu âm ở `r` không có nghĩa rằng giá trị `a[r]` phải giảm `delta`. Nó chỉ **hủy tác động đang chạy** để những phần tử từ `r` trở đi không bị cộng thêm.

## 3. Mảng hiệu theo định nghĩa toán học

Với mảng `a` có `n` phần tử, một dạng **mảng hiệu liên tiếp** `D` là:

```text
D[0] = a[0]
D[i] = a[i] - a[i-1]       khi 1 <= i < n
```

Ở đây `a[-1]` theo định nghĩa toán học được coi là 0, **không phải** phép truy cập phần tử cuối theo quy tắc chỉ số âm của Python.

Với mảng:

```text
a = [2, 5, 1, 4, 3]
```

ta có:

```text
D[0] =  2
D[1] =  5 - 2 =  3
D[2] =  1 - 5 = -4
D[3] =  4 - 1 =  3
D[4] =  3 - 4 = -1

D = [2, 3, -4, 3, -1]
```

**Ý nghĩa của `D[i]`:** mức thay đổi từ vị trí ngay trước sang vị trí `i`, riêng `D[0]` đo từ giá trị gốc giả định bằng 0.

Nếu giá trị liền kề không đổi, hiệu bằng 0. Nếu giá trị tăng, hiệu dương; nếu giảm, hiệu âm.

### Tổng tiền tố của hiệu khôi phục mảng

Vì:

```text
D[0] + D[1] + ... + D[i]
= a[0] + (a[1]-a[0]) + ... + (a[i]-a[i-1])
= a[i]
```

các số hạng trung gian triệt tiêu theo kiểu **telescoping sum** (tổng khử liên tiếp).

Vậy:

```text
a[i] = D[0] + D[1] + ... + D[i]
```

Đây là bất biến quan trọng: **mảng gốc là tổng cộng dồn của mảng hiệu**.

### Mảng hiệu và tổng tiền tố khác nhau như thế nào?

- **Tổng tiền tố `P[k]`** lưu *tổng các giá trị đã đi qua* để trả lời **truy vấn tổng đoạn** bằng hiệu hai tiền tố.
- **Mảng hiệu `D[i]`** lưu *mức thay đổi tại ranh giới* để thực hiện **cộng đoạn** bằng hai dấu mốc rồi dựng lại giá trị.

Hai kỹ thuật có mối liên hệ **hiệu và tổng cộng dồn là hai thao tác ngược nhau**, nhưng phục vụ các bộ thao tác khác nhau.

## 4. Tại sao một lần cộng đoạn chỉ sửa hai phần tử hiệu?

Giả sử ta cộng `delta` vào mọi `a[i]` trong `[l,r)`.

Với `0 < l < r < n`, hãy xem hiệu mới `D'`:

- Các cặp chỉ số **hoàn toàn ngoài đoạn**: cả hai giá trị đều không đổi, nên hiệu không đổi.
- Các cặp **hoàn toàn nằm trong đoạn**: cả hai giá trị đều tăng `delta`, nên hiệu `(a[i]+delta)-(a[i-1]+delta)` vẫn bằng hiệu cũ.
- **Tại biên trái `l`:** `a[l]` tăng nhưng `a[l-1]` không tăng, nên `D[l]` tăng `delta`.
- **Tại biên phải `r`:** `a[r]` không tăng nhưng `a[r-1]` tăng, nên `D[r]` giảm `delta`.

Tức là:

```text
D[l] += delta
D[r] -= delta
```

Đối với `l=0`, `D[0]` cũng phải tăng `delta`. Đối với `r=n`, không còn phần tử thật `a[n]`; ta có thể dùng **ô sentinel** `D[n]` để ghi mốc tắt tác động, hoặc bỏ mốc này nếu chỉ cần dựng các vị trí từ 0 đến n−1.

Với **đoạn rỗng `l=r`**, không có phần tử cần cập nhật. Ta nên **bỏ qua thao tác**, tránh tạo hai dấu mốc triệt tiêu tại cùng một vị trí khi không cần thiết.

## 5. Hai cách tổ chức mảng hiệu: dài n hoặc n+1

Có hai cách triển khai phổ biến và đều đúng nếu dùng nhất quán.

### Cách A — Mảng hiệu dài n

Dùng `D[0],...,D[n-1]`. Khi xử lý `[l,r)`:

```text
D[l] += delta       (nếu l < r)
if r < n:
    D[r] -= delta
```

Nếu `r=n`, không có phần tử ở vị trí `n`, nên không phải ghi dấu trừ. Cách này ít tốn một ô nhưng cần **nhánh điều kiện**.

### Cách B — Mảng hiệu dài n+1

Dùng `D[0],...,D[n]`. Khi xử lý một đoạn **không rỗng**:

```text
D[l] += delta
D[r] -= delta
```

Cách này cho phép `r=n` mà không cần xét riêng biên phải, vì `D[n]` tồn tại.

Chỉ tính tổng cộng dồn tới `D[n-1]` để xuất **n phần tử thật**; `D[n]` là mốc cuối, không phải phần tử thứ n+1 của mảng gốc.

Trong phần lớn mã của bài, ta chọn **cách B: hiệu dài n+1**, vì hai phép cập nhật biên luôn giống nhau.

### Chọn giá trị nào cho `D[n]`?

Nếu khởi tạo mảng hiệu từ một mảng gốc `a`, ta có thể đặt `D[n] = 0` làm **ô sentinel không sử dụng khi khôi phục n phần tử**. Các lệnh chạm biên `r=n` vẫn cập nhật ô ấy. Theo quy ước này, tổng của tất cả `D[0:n+1]` **không nhất thiết bằng 0** khi mảng gốc có giá trị cuối khác 0.

Một quy ước khác là hình dung phần tử giả `a[n]=0` và đặt `D[n]=-a[n-1]`. Khi đó tổng toàn bộ mảng hiệu bằng 0 trước và sau mọi cập nhật. Hai quy ước không mâu thuẫn: chúng chỉ khác **giá trị của ô mốc ngoài miền dữ liệu thật**.

**Phải xác định quy ước trước khi diễn giải `D[n]`.** Trong thuật toán khởi tạo mốc cộng đoạn bằng các số 0, ta chỉ lưu **hiệu của lượng tăng thêm**, nên sentinel bằng 0 trước cập nhật là hoàn toàn tự nhiên.

## 6. Cách 1: giữ mảng gốc và ghi hiệu của lượng cập nhật

Đây là cách đơn giản nhất khi `a` đã tồn tại và ta chỉ muốn **ghi nhận các lượng cộng thêm**.

Khởi tạo:

```text
delta_diff = [0] * (n+1)
```

Với mỗi cập nhật `[l,r)` tăng `delta`:

```text
delta_diff[l] += delta
delta_diff[r] -= delta
```

Sau khi nhận xong tất cả cập nhật, ta cộng dồn `delta_diff` vào `running` và xuất:

```text
answer[i] = a[i] + running
```

**Bất biến:** tại thời điểm dựng vị trí `i`, `running` chính là **tổng lượng thay đổi của tất cả cập nhật bao phủ chỉ số i**.

### Ví dụ ba cập nhật chồng lấn

Cho:

```text
a = [2, 5, 1, 4, 3]
```

Các lệnh:

```text
U1: add [1,4) +3
U2: add [2,5) -2
U3: add [0,2) +1
```

Nếu cập nhật trực tiếp, ta có:

```text
Ban đầu: [2, 5, 1, 4, 3]
Sau U1:  [2, 8, 4, 7, 3]
Sau U2:  [2, 8, 2, 5, 1]
Sau U3:  [3, 9, 2, 5, 1]
```

Với mảng hiệu lượng thay đổi, `n=5` nên có 6 ô:

| Lệnh | Mốc bắt đầu | Mốc kết thúc |
|---|---|---|
| U1 `[1,4), +3` | `diff[1] += 3` | `diff[4] -= 3` |
| U2 `[2,5), -2` | `diff[2] -= 2` | `diff[5] += 2` |
| U3 `[0,2), +1` | `diff[0] += 1` | `diff[2] -= 1` |

Tổng hợp các mốc:

```text
Chỉ số diff:    0   1   2   3   4   5
Mốc hiệu:       1   3  -3   0  -3   2

Vị trí thật i:  0   1   2   3   4
Tăng cộng dồn:  1   4   1   1  -2

Mảng gốc:       2   5   1   4   3
Mảng kết quả:   3   9   2   5   1
```

Hai cập nhật chồng lên nhau ở vị trí 2,3. Tổng tác động tại mỗi chỉ số được cộng đúng một lần khi cộng dồn mốc hiệu; **không có yêu cầu các đoạn cập nhật phải rời nhau**.

## 7. Python: cập nhật hàng loạt và xuất mảng kết quả

Ta dùng các hàm thuần, không sửa mảng gốc, có kiểm tra biên chặt chẽ.

```python
def validate_range(n, l, r):
    """Đoạn [l,r) 0-based, cho phép rỗng."""
    if type(l) is not int or type(r) is not int:
        raise TypeError("l và r phải là số nguyên")

    if not 0 <= l <= r <= n:
        raise IndexError("Đoạn [l,r) ngoài miền hợp lệ")


def apply_range_adds(values, updates):
    """
    values: mảng gốc không thay đổi.
    updates: các bộ (l, r, delta), áp dụng trên [l,r).
    Trả mảng mới sau tất cả các lần cộng đoạn.
    """
    n = len(values)
    diff = [0] * (n + 1)

    for l, r, delta in updates:
        validate_range(n, l, r)

        if l == r:
            continue

        diff[l] += delta
        diff[r] -= delta

    answer = list(values)
    running = 0

    for i in range(n):
        running += diff[i]
        answer[i] += running

    return answer


original = [2, 5, 1, 4, 3]
updates = [
    (1, 4, +3),
    (2, 5, -2),
    (0, 2, +1),
]

assert apply_range_adds(original, updates) == [3, 9, 2, 5, 1]
assert original == [2, 5, 1, 4, 3]

# Một cập nhật phủ toàn mảng.
assert apply_range_adds([3, 6, 9], [(0, 3, 4)]) == [7, 10, 13]

# Cập nhật đoạn rỗng không làm gì.
assert apply_range_adds([1, 2], [(1, 1, 999)]) == [1, 2]

# Không có lệnh nào.
assert apply_range_adds([1, 2, 3], []) == [1, 2, 3]

# Mảng rỗng chỉ có đoạn [0,0).
assert apply_range_adds([], [(0, 0, 10)]) == []
```

Mã lưu phần tăng trong `diff`, không duyệt trực tiếp từng phần tử khi xử lý cập nhật. Cuối cùng, một vòng lặp duy nhất cộng các mức thay đổi vào mảng kết quả.

### Điều kiện kiểu dữ liệu

Công thức giả định các phần tử `values` và `delta` là các đại lượng hỗ trợ **cộng và trừ nhất quán**, chẳng hạn số nguyên hoặc số thực. Nếu `delta` là một chuỗi hoặc đối tượng không có phép trừ, câu lệnh `diff[r] -= delta` có thể không hợp lệ.

Với những loại thao tác khác như thay toàn bộ đoạn bằng một giá trị, không thể tự động áp dụng cùng cặp mốc `+/-delta`. Ta sẽ phân tích giới hạn đó ở phần sau.

## 8. Cách 2: chuyển chính mảng gốc sang dạng hiệu

Có thể bắt đầu trực tiếp từ hiệu liên tiếp của `a` rồi cập nhật các dấu mốc ngay trong biểu diễn ấy.

Xây:

```text
D[0] = a[0]
D[i] = a[i] - a[i-1]    với 1 <= i < n
D[n] = 0                # sentinel quy ước của bài
```

Sau khi thực hiện toàn bộ cập nhật, cộng dồn `D[0:n]` để dựng lại mảng.

### Code Python

```python
def to_difference(values):
    """Mảng hiệu dài n+1 với sentinel D[n]=0."""
    n = len(values)
    diff = [0] * (n + 1)

    if n == 0:
        return diff

    diff[0] = values[0]

    for i in range(1, n):
        diff[i] = values[i] - values[i - 1]

    return diff


def add_on_difference(diff, l, r, delta):
    """Thêm delta trên [l,r) vào mảng hiệu đã có sentinel."""
    n = len(diff) - 1
    validate_range(n, l, r)

    if l == r:
        return

    diff[l] += delta
    diff[r] -= delta


def from_difference(diff):
    """Dựng n giá trị thật; không xuất ô sentinel cuối."""
    n = len(diff) - 1
    answer = []
    running = 0

    for i in range(n):
        running += diff[i]
        answer.append(running)

    return answer


a = [2, 5, 1, 4, 3]
D = to_difference(a)

assert D == [2, 3, -4, 3, -1, 0]
assert from_difference(D) == a

add_on_difference(D, 1, 4, +3)
add_on_difference(D, 2, 5, -2)
add_on_difference(D, 0, 2, +1)

assert D == [3, 6, -7, 3, -4, 2]
assert from_difference(D) == [3, 9, 2, 5, 1]
```

Đối chiếu:

- Cách **giữ gốc + delta_diff** phù hợp khi muốn giữ snapshot ban đầu và chỉ lưu chênh lệch do các cập nhật.
- Cách **hiệu hóa mảng gốc** phù hợp khi muốn bản biểu diễn chính là dãy hiệu được sửa trực tiếp.

Cả hai đều có cùng tính đúng đắn và chi phí bậc lớn. **Đừng cộng dồn hai lần**: khi đã xây hiệu của mảng gốc, bước khôi phục chỉ lấy tổng tiền tố của `D`; không cộng thêm `a[i]` lần nữa.

## 9. Bất biến của hai dấu mốc biên

Xét một cập nhật `(l,r,delta)` với `l<r`. Nó ghi:

```text
diff[l] += delta
diff[r] -= delta
```

Với một vị trí thật `i`, đặt:

```text
effect(i) = diff[0] + diff[1] + ... + diff[i]
```

Ảnh hưởng của riêng cập nhật đó là:

```text
effect_update(i)
  = 0       nếu i < l
  = delta   nếu l <= i < r
  = 0       nếu i >= r
```

Vì:

1. Khi `i<l`, cả hai mốc chưa được cộng vào.
2. Khi `l<=i<r`, chỉ có mốc `+delta` nằm trong tổng.
3. Khi `i>=r`, đã bao gồm cả `+delta` và `-delta` nên chúng triệt tiêu.

Công thức này chứng minh **hai mốc là đủ** để mô tả chính xác phép cộng trên đoạn.

### Chồng lấn nhiều đoạn

Với các cập nhật `U_1,...,U_q`, tổng mốc hiệu:

```text
diff = diff_U1 + diff_U2 + ... + diff_Uq
```

Phép cộng dồn có tính tuyến tính, nên:

```text
effect(i)
= sum(effect_Uj(i) for j=1..q)
= sum(delta_j for mọi Uj có l_j <= i < r_j)
```

Do vậy **mọi cập nhật bao phủ vị trí i đều góp đúng delta của nó**, không phụ thuộc thứ tự ghi mốc khi sử dụng số học chính xác.

Đây cũng là chứng minh rằng mảng hiệu xử lý đúng **đoạn chồng lấn, đoạn lồng nhau, đoạn bằng nhau và đoạn ngược dấu**, miễn là mỗi cập nhật được ghi theo cùng quy ước.

## 10. Đoạn đóng 1-based: đổi biên cho đúng

Không ít đề bài đưa lệnh:

```text
Tăng delta vào mọi phần tử ở vị trí L, L+1, ..., R
```

trong đó các vị trí được **đánh số từ 1** và **cả hai đầu đều được lấy**.

Đó là đoạn đóng `[L,R]`, với:

```text
1 <= L <= R <= n
```

Đổi sang chuẩn của bài:

```text
[l,r) = [L-1,R)
```

Sau đó đánh dấu:

```text
diff[L-1] += delta
diff[R]   -= delta
```

Ví dụ mảng năm phần tử:

```text
1-based [2,4]   ->   0-based [1,4)

Cập nhật +3 vào vị trí 1,2,3 theo 0-based.
```

### Hàm chuyển biên

```python
def inclusive_1based_to_halfopen(n, L, R):
    if type(L) is not int or type(R) is not int:
        raise TypeError("L và R phải là số nguyên")

    if not 1 <= L <= R <= n:
        raise IndexError("Đoạn [L,R] 1-based không hợp lệ")

    return (L - 1, R)


def apply_range_adds_1based(values, updates):
    converted = []

    for L, R, delta in updates:
        l, r = inclusive_1based_to_halfopen(len(values), L, R)
        converted.append((l, r, delta))

    return apply_range_adds(values, converted)


assert apply_range_adds_1based(
    [2, 5, 1, 4, 3],
    [(2, 4, 3)]
) == [2, 8, 4, 7, 3]
```

**Lỗi off-by-one điển hình:** nếu đã đổi `[L,R]` 1-based thành `[L-1,R)`, không được cộng thêm 1 vào `r` lần nữa. Khi dùng mảng hiệu với sentinel dài n+1, **diff[R]** là ô tắt tác động, không phải phần tử cuối được cộng.

### Đoạn đóng 0-based

Nếu dữ liệu dùng `[l,R]` 0-based và lấy cả R, quy đổi:

```text
[l,R] -> [l,R+1)
```

Các quy tắc này khác nhau. Hãy viết rõ **0-based hay 1-based, đóng hay nửa mở**, trước khi triển khai.

## 11. Cập nhật toàn mảng, đoạn một phần tử và đoạn rỗng

Những trường hợp biên dễ tạo lỗi nếu mảng hiệu không có sentinel hoặc không kiểm tra chỉ số.

### Toàn mảng

Trên `n` phần tử:

```text
range_add(0,n,delta)

diff[0] += delta
diff[n] -= delta
```

Vòng dựng chỉ cộng dồn `diff[0],...,diff[n-1]`; toàn bộ n phần tử nhận `delta`. Dấu ở `diff[n]` chỉ biểu thị hết tác động sau vị trí cuối.

### Đoạn một phần tử

Để cộng `delta` vào duy nhất `a[i]`:

```text
range_add(i,i+1,delta)

diff[i]   += delta
diff[i+1] -= delta
```

Nếu `i=n-1`, mốc thứ hai ở `diff[n]` vẫn hợp lệ.

### Đoạn rỗng

```text
range_add(l,l,delta)
```

không thay đổi bất kỳ vị trí nào. Việc bỏ qua sớm giúp tránh dấu mốc đối kháng không cần thiết và giảm nguy cơ lỗi ở API phức tạp hơn.

### Mảng rỗng

Với `n=0`:

```text
values = []
diff = [0]
```

Chỉ có đoạn `[0,0)` hợp lệ, và mọi cập nhật trên đó là no-op. Không được truy cập `diff[1]` hay tạo `answer[0]`.

### Kiểm thử các biên

```python
assert apply_range_adds([1], [(0, 1, 5)]) == [6]
assert apply_range_adds([1], [(0, 0, 5)]) == [1]
assert apply_range_adds([1], [(1, 1, 5)]) == [1]
assert apply_range_adds([], [(0, 0, 5)]) == []

for bad_l, bad_r in [
    (-1, 2),
    (2, 1),
    (0, 6),
    (5, 6),
]:
    try:
        apply_range_adds([2, 5, 1, 4, 3], [(bad_l, bad_r, 1)])
    except IndexError:
        pass
    else:
        raise AssertionError("Phải từ chối biên sai")
```

**Đáng chú ý:** Python chấp nhận chỉ số âm ở nhiều thao tác trên list. Một API truy vấn đoạn nghiêm ngặt không nên để `diff[-1]` bị hiểu nhầm là “biên -1 hợp lệ”.

## 12. Một đối tượng gom cập nhật theo lô

Để thể hiện rõ mô hình sử dụng, ta có thể viết lớp `RangeAddBatch`:

- Nhận dữ liệu ban đầu và tạo một **snapshot**.
- Ghi nhận nhiều lệnh `add(l,r,delta)`.
- Khi cần, **materialize** để xuất một mảng mới.
- Không hỗ trợ query nhanh trực tuyến sau mỗi lệnh.

```python
class RangeAddBatch:
    def __init__(self, values):
        self.base = tuple(values)
        self.n = len(self.base)
        self.diff = [0] * (self.n + 1)

    def add(self, l, r, delta):
        validate_range(self.n, l, r)

        if l == r:
            return

        self.diff[l] += delta
        self.diff[r] -= delta

    def materialize(self):
        result = list(self.base)
        running = 0

        for i in range(self.n):
            running += self.diff[i]
            result[i] += running

        return result


batch = RangeAddBatch([2, 5, 1, 4, 3])

batch.add(1, 4, 3)
batch.add(2, 5, -2)
batch.add(0, 2, 1)

assert batch.materialize() == [3, 9, 2, 5, 1]

# Việc materialize không tiêu thụ các cập nhật.
assert batch.materialize() == [3, 9, 2, 5, 1]

batch.add(4, 5, 10)
assert batch.materialize() == [3, 9, 2, 5, 11]
```

Mỗi lần `add` chỉ dùng O(1) thao tác. Mỗi lần `materialize` dùng O(n) thời gian và tạo mảng kết quả O(n).

**Lưu ý về tên:** `materialize` là “vật chất hóa” dữ liệu đang được biểu diễn gián tiếp bằng mảng hiệu. Nó **không** phải truy vấn tổng đoạn O(1), cũng không phải một lần cập nhật mới.

### Nhiều lần gọi materialize

Giả sử có `t` lần gọi `materialize()`, mỗi lần đi qua toàn mảng, thì riêng phần xuất kết quả tốn O(tn), **không thể vẫn báo tổng chi phí O(n+q)**. Cận O(n+q) chỉ áp dụng cho kịch bản **q lần ghi cập nhật, sau đó dựng kết quả một lần**.

## 13. Độ phức tạp và giả định về chi phí số học

Gọi:

- `n`: số phần tử.
- `q`: số lần cộng đoạn.
- `k`: độ dài một đoạn cụ thể.
- `t`: số lần cần dựng toàn bộ kết quả.

### Cách trực tiếp

Một lần `range_add(l,r,delta)` sửa `k=r-l` phần tử:

```text
Thời gian cập nhật: O(k)
Bộ nhớ điều khiển: O(1)
```

Với q cập nhật phủ gần như toàn mảng:

```text
O(nq)
```

### Cách mảng hiệu

Khởi tạo `diff` dài `n+1`:

```text
O(n) thời gian/bộ nhớ
```

Mỗi lần cập nhật chỉ sửa hai mốc:

```text
O(1) thời gian
```

Cộng dồn và xuất n phần tử:

```text
O(n) thời gian
```

Tổng cho **q cập nhật rồi một lần xuất**:

```text
O(n + q)
```

Bộ nhớ phụ `diff` và mảng kết quả là O(n); các biến `running`, `i` sử dụng O(1).

| Kịch bản | Cập nhật một đoạn dài k | Sau q cập nhật, lấy toàn mảng | Phù hợp |
|---|---:|---:|---|
| Sửa trực tiếp từng phần tử | O(k) | Không cần thêm bước nếu đã sửa | Ít cập nhật; cần mảng mới ngay |
| Mảng hiệu theo lô | **O(1)** | **O(n+q)** kể cả ghi q lệnh và xuất | Nhiều cập nhật, lấy kết quả cuối |
| Mảng hiệu, dựng sau mỗi lệnh | O(1) ghi mốc + O(n) dựng | Có thể O(nq) | Không tận dụng được xử lý theo lô |

### Chi phí thao tác số học

Các cận trên giả định phép cộng/trừ trên một giá trị có chi phí hằng số theo mô hình RAM. Số nguyên rất lớn trong Python, số thực có quy tắc làm tròn, hoặc các giá trị kiểu vector dài có thể khiến chi phí mỗi phép toán phụ thuộc kích thước giá trị. Khi đánh giá thực tế, cần nêu thêm giới hạn độ lớn dữ liệu và số lần cấp phát.

## 14. Vì sao mảng hiệu thuần không trả lời truy vấn online O(1)?

Đây là điểm dễ hiểu sai nhất của kỹ thuật.

Sau khi ghi các mốc, mảng `diff` **chưa chứa giá trị cuối tại từng vị trí**. Muốn tìm giá trị `a[i]` sau cập nhật, ta phải biết:

```text
effect(i) = diff[0] + ... + diff[i]
value(i)  = base[i] + effect(i)
```

Nếu không có cấu trúc phụ, tính `effect(i)` cần quét O(i+1) phần tử; trong trường hợp xấu nhất O(n).

Muốn hỏi **tổng đoạn sau cập nhật**, việc có `diff` cũng không tự cho phép lấy ngay hiệu hai ô. Ta phải **dựng mảng cuối và có thể xây thêm prefix sum**:

```text
q cập nhật -> diff
       |
       v
Cộng dồn O(n) để có mảng cuối
       |
       v
Xây prefix mới O(n)
       |
       v
Query sum [l,r) O(1) trên snapshot đã xuất
```

**Nếu lại thêm cập nhật**, prefix mới trở nên lỗi thời. Xây lại sau mỗi cập nhật có thể tốn O(n) mỗi lần.

### Cấu trúc khác khi cần online

Với thao tác **cộng đoạn và hỏi giá trị một điểm** liên tục, có thể lưu các mốc hiệu trong **Fenwick tree** để cập nhật hai biên và tính tổng tiền tố của hiệu trong O(log n).

Với thao tác **cộng đoạn và hỏi tổng đoạn** liên tục, có thể dùng **hai Fenwick tree** với công thức thích hợp hoặc **segment tree hỗ trợ lazy propagation**.

Mảng hiệu là nền tảng để hiểu các cấu trúc đó, nhưng **không thay thế hoàn toàn** các cấu trúc truy vấn động khi cần trả lời sau mỗi bước.

## 15. Vì sao mảng hiệu phù hợp với cộng nhưng không tự xử lý gán đoạn?

Một lệnh cộng đoạn:

```text
a[i] <- a[i] + delta
```

tác động như nhau trên mọi phần tử của đoạn. Những thay đổi ở nội bộ đoạn **triệt tiêu nhau** khi lấy hiệu liên tiếp, chỉ còn hai mốc biên.

Ngược lại, lệnh gán đoạn:

```text
a[i] <- x             với l <= i < r
```

làm giá trị mới **phụ thuộc vào giá trị cũ** tại từng phần tử.

Ví dụ:

```text
a = [2, 5, 1, 4, 3]
assign([1,4), 7)
=> [2, 7, 7, 7, 3]
```

Nếu chỉ ghi:

```text
diff[1] += 7
diff[4] -= 7
```

ta đã thực hiện **cộng thêm 7**, không phải gán bằng 7.

**Không thể dùng cùng biểu diễn hai mốc cộng/trừ để biến mọi lệnh gán đoạn thành O(1) mà vẫn giữ nguyên quy tắc dựng như phép cộng đoạn.** Có những phương pháp xử lý gán đoạn offline hoặc lazy segment tree, nhưng yêu cầu mô hình tác động và thứ tự cập nhật khác.

### Cập nhật cộng và gán khác nhau về tính giao hoán

Với cộng số chính xác:

```text
add(+3) rồi add(-2) = add(+1)
add(-2) rồi add(+3) = add(+1)
```

Nhưng:

```text
assign(7) rồi add(3)  => 10
add(3) rồi assign(7)  => 7
```

Thứ tự có thể làm đổi kết quả. Mảng hiệu cộng đoạn đơn giản tận dụng tính **cộng dồn** của các lượng thay đổi, không xử lý trực tiếp mọi kiểu phép cập nhật.

## 16. Cập nhật đoạn chồng lấn và lồng nhau

Mảng hiệu có thể ghi nhiều đoạn, không bắt buộc phải xử lý theo thứ tự vị trí hay không chồng nhau.

Ví dụ với `n=8`, ban đầu mọi giá trị bằng 0:

```text
U1: [1,7) +3
U2: [3,5) +4
U3: [0,8) -2
```

Sau từng cập nhật theo cách trực tiếp:

```text
Ban đầu:  [0, 0, 0, 0, 0, 0, 0, 0]
Sau U1:   [0, 3, 3, 3, 3, 3, 3, 0]
Sau U2:   [0, 3, 3, 7, 7, 3, 3, 0]
Sau U3:   [-2,1, 1, 5, 5, 1, 1,-2]
```

Mảng hiệu lượng tăng:

```text
U1: diff[1]+=3, diff[7]-=3
U2: diff[3]+=4, diff[5]-=4
U3: diff[0]-=2, diff[8]+=2

Chỉ số:  0   1   2   3   4   5   6   7   8
diff:   -2   3   0   4   0  -4   0  -3   2

Cộng dồn tại 0..7:
        -2   1   1   5   5   1   1  -2
```

Đoạn `[3,5)` nằm **bên trong** `[1,7)` và đồng thời thuộc `[0,8)`. Ở các vị trí 3,4, tác động là `+3 +4 -2 = +5`.

### Công thức tổng quát

Mỗi cập nhật `(l_j,r_j,delta_j)` đóng góp tại chỉ số `i`:

```text
contribution_j(i) =
    delta_j    nếu l_j <= i < r_j
    0          ngược lại
```

Mảng kết quả:

```text
answer[i] = a[i] + sum(contribution_j(i), j=1..q)
```

Mảng hiệu chỉ là một cách tính tổng đó với việc ghi các mốc **O(1)** mỗi cập nhật và một vòng cộng dồn **O(n)** cuối cùng.

## 17. Đếm số đoạn bao phủ từng vị trí

Một ứng dụng rất tự nhiên của mảng hiệu là **đếm mức độ phủ** (*coverage count*).

Giả sử có những khoảng thời gian đã quy đổi thành các vị trí nguyên hoặc những đoạn ghế được đặt. Muốn biết tại mỗi vị trí có **bao nhiêu đoạn phủ qua**, ta gán:

```text
delta = +1
```

cho mỗi khoảng `[l,r)`.

### Ví dụ

Có `n=7` vị trí đánh số 0..6 và các khoảng:

```text
[1,4)
[2,6)
[2,5)
```

Ta có:

```text
diff[1] += 1; diff[4] -= 1
diff[2] += 1; diff[6] -= 1
diff[2] += 1; diff[5] -= 1
```

Cộng dồn thu được:

```text
i:           0  1  2  3  4  5  6
coverage:    0  1  3  3  2  1  0
```

Có ba khoảng phủ các vị trí 2 và 3; hai khoảng phủ vị trí 4; một khoảng phủ vị trí 5.

### Python

```python
def coverage_counts(n, intervals):
    if type(n) is not int or n < 0:
        raise ValueError("n phải là số nguyên không âm")

    return apply_range_adds(
        [0] * n,
        [(l, r, 1) for l, r in intervals],
    )


assert coverage_counts(
    7, [(1, 4), (2, 6), (2, 5)]
) == [0, 1, 3, 3, 2, 1, 0]
```

**Số lượng đoạn phủ là một tổng tác động**, không đòi hỏi giá trị ban đầu khác 0. Nhờ vậy mảng hiệu áp dụng được cho lịch đặt chỗ, số lượng sự kiện hoạt động, tải hệ thống theo bước thời gian và nhiều bài toán đếm giao nhau.

## 18. Tìm vị trí có mức tác động lớn nhất sau cập nhật

Sau khi có `diff` từ nhiều cập nhật, ta có thể tìm **mức tăng lớn nhất**, **giá trị cuối lớn nhất** hoặc **số khoảng bao phủ tối đa** trong một lần cộng dồn.

Ví dụ các khoảng ở mục 17 có mức phủ lớn nhất bằng 3, đạt tại vị trí 2 và 3.

```python
def max_coverage(n, intervals):
    counts = coverage_counts(n, intervals)

    if n == 0:
        return (0, [])

    highest = max(counts)
    positions = [i for i, count in enumerate(counts) if count == highest]
    return (highest, positions)


assert max_coverage(
    7, [(1, 4), (2, 6), (2, 5)]
) == (3, [2, 3])

assert max_coverage(0, []) == (0, [])
```

Với ứng dụng cần chỉ mức lớn nhất mà không cần giữ mọi giá trị, ta có thể quét `diff` cộng dồn và duy trì `maximum` trong O(n) thời gian, O(1) biến điều khiển, **nhưng vẫn cần không gian O(n) để lưu diff nếu dùng mảng dài n+1**.

### Mức tăng khác giá trị cuối

Nếu mảng gốc không đều, vị trí có **mức tăng lớn nhất** chưa chắc là vị trí có **giá trị cuối lớn nhất**.

Ví dụ:

```text
Mảng gốc:    [100, 1]
Mức tăng:    [0, 50]
Mảng cuối:   [100, 51]
```

Mức tăng lớn nhất ở vị trí 1, còn giá trị cuối lớn nhất ở vị trí 0. Hãy xác định đang tối ưu đại lượng nào.

## 19. Mảng hiệu và quét sự kiện (sweep line)

Các dấu mốc `+delta` và `-delta` có thể được hiểu là **sự kiện tại ranh giới**. Với một trục chỉ số nguyên đã biết `0..n`, ta dùng mảng để lưu sự kiện.

Nếu miền tọa độ rất lớn hoặc thưa, ví dụ timestamp nguyên đến hàng tỷ nhưng chỉ có vài nghìn khoảng, cấp phát mảng dài theo giá trị tọa độ là không hợp lý.

Ta có thể lưu các mốc trong một **bản đồ có khóa là tọa độ**, cộng các mốc trùng, rồi duyệt các tọa độ sau khi **sắp xếp**.

### Ý tưởng trên tọa độ thưa

Mỗi khoảng thời gian `[start,end)` với trọng số `delta`:

```text
events[start] += delta
events[end]   -= delta
```

Sau khi sắp các mốc `x_0 < x_1 < ...`, mức tác động là hằng số trên từng đoạn giữa hai mốc liên tiếp.

```text
Ví dụ:
[10,20) +3
[15,25) +2

Sự kiện:
10: +3
15: +2
20: -3
25: -2

Mức trên các khoảng:
[10,15): 3
[15,20): 5
[20,25): 2
[25,...) : 0
```

### Python: các khoảng giá trị không đổi

```python
def weighted_interval_segments(intervals):
    """Trả (start,end,weight) cho mỗi đoạn giữa các mốc."""
    events = {}

    for start, end, delta in intervals:
        if start > end:
            raise ValueError("Khoảng đảo biên")
        if start == end:
            continue

        events[start] = events.get(start, 0) + delta
        events[end] = events.get(end, 0) - delta

    points = sorted(events)
    segments = []
    running = 0

    for i in range(len(points) - 1):
        x = points[i]
        next_x = points[i + 1]
        running += events[x]

        segments.append((x, next_x, running))

    return segments


segments = weighted_interval_segments([
    (10, 20, 3),
    (15, 25, 2),
])

assert segments == [
    (10, 15, 3),
    (15, 20, 5),
    (20, 25, 2),
]
```

**Độ phức tạp:** với `q` khoảng, có tối đa `2q` mốc. Ghi sự kiện tốn O(q) thời gian trung bình (dictionary), sắp các mốc O(q log q), quét O(q). Đây là một **biến thể ý tưởng mảng hiệu** cho miền tọa độ thưa, không phải thuật toán O(n+q) với n là chiều dài trục tọa độ ban đầu.

### Biên nửa mở vẫn quan trọng

Hai khoảng `[10,20)` và `[20,30)` không chồng nhau: tại đúng tọa độ 20, khoảng thứ nhất đã kết thúc và khoảng thứ hai bắt đầu. Khi gom các sự kiện cùng tọa độ, ta **cộng tổng các mốc tại đó** để có mức tác động cho khoảng bắt đầu từ tọa độ ấy.

## 20. Mảng hiệu trong hai chiều

Ý tưởng “ghi mốc ở biên rồi cộng dồn” còn mở rộng cho **cộng một giá trị vào mọi ô của hình chữ nhật** trong ma trận.

Với ma trận có `rows` hàng, `cols` cột và hình chữ nhật nửa mở:

```text
[r1,r2) x [c1,c2)
```

ta muốn cộng `delta` vào mọi ô có:

```text
r1 <= row < r2
c1 <= col < c2
```

Thay vì ghi vào mọi ô, dùng **mảng hiệu 2D** kích thước `(rows+1) × (cols+1)`, đánh dấu **bốn góc**:

```text
diff[r1][c1] += delta
diff[r1][c2] -= delta
diff[r2][c1] -= delta
diff[r2][c2] += delta
```

Hai dấu dương và hai dấu âm bù trừ chính xác vùng ngoài hình chữ nhật. Khi cộng dồn hai chiều (trái sang phải và trên xuống dưới), ta thu được mức tác động tại từng ô.

### Minh họa dấu góc

```text
        c1                   c2
r1      +delta               -delta

r2      -delta               +delta
```

Khi cộng dồn qua hàng và cột, mức tác động chỉ tồn tại trong hình chữ nhật `[r1,r2) × [c1,c2)`.

### Python: cập nhật hình chữ nhật theo lô

```python
def apply_rectangle_adds(matrix, updates):
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0

    if any(len(row) != cols for row in matrix):
        raise ValueError("Ma trận phải có số cột đồng nhất")

    diff = [[0] * (cols + 1) for _ in range(rows + 1)]

    for r1, r2, c1, c2, delta in updates:
        validate_range(rows, r1, r2)
        validate_range(cols, c1, c2)

        if r1 == r2 or c1 == c2:
            continue

        diff[r1][c1] += delta
        diff[r1][c2] -= delta
        diff[r2][c1] -= delta
        diff[r2][c2] += delta

    answer = [list(row) for row in matrix]

    for r in range(rows):
        for c in range(cols):
            top = diff[r - 1][c] if r else 0
            left = diff[r][c - 1] if c else 0
            corner = diff[r - 1][c - 1] if r and c else 0

            diff[r][c] += top + left - corner
            answer[r][c] += diff[r][c]

    return answer


matrix = [
    [1, 2, 3],
    [4, 5, 6],
]

updated = apply_rectangle_adds(
    matrix,
    [(0, 2, 1, 3, 10)],
)

assert updated == [
    [1, 12, 13],
    [4, 15, 16],
]
assert matrix == [[1, 2, 3], [4, 5, 6]]
```

Với `R` hàng, `C` cột, `q` cập nhật, tổng chi phí là **O(RC+q)** thời gian và O(RC) bộ nhớ phụ/đầu ra, nếu các phép toán số là O(1). Kỹ thuật 2D dùng cùng ý tưởng, nhưng cần hiểu rõ **bao hàm–loại trừ qua bốn góc** để tránh sai dấu.

## 21. Khi nào nên giữ mảng gốc, khi nào nên chỉ lưu hiệu?

Có ba tình huống thiết kế thường gặp.

### 21.1. Chỉ cần dãy kết quả cuối

Lưu `diff` (dài n+1) và mảng gốc hoặc dãy hiệu của mảng gốc, ghi mọi cập nhật, rồi xuất một lần.

- Ưu điểm: O(1) mỗi lần cộng đoạn.
- Nhược điểm: chưa sẵn sàng để đọc giá trị ở vị trí tùy ý trong O(1) trước khi dựng.

Đây là **trường hợp mục tiêu** của kỹ thuật.

### 21.2. Cần đọc dữ liệu thường xuyên giữa các cập nhật

Nếu cứ sau một lệnh lại hỏi giá trị hiện tại ở điểm `i` hoặc tổng `[l,r)`, việc cộng dồn lại `diff` nhiều lần có thể mất O(n) mỗi lần.

Cân nhắc Fenwick tree hoặc segment tree để hỗ trợ thao tác **online**. Chi phí xử lý sẽ cao hơn O(1) ở mỗi update, nhưng truy vấn cũng nhanh và không cần dựng lại toàn bộ mảng sau mỗi bước.

### 21.3. Cần lưu lịch sử của nhiều phiên bản

Mảng hiệu theo lô thường mô tả **tổng hợp tất cả cập nhật hiện có**, không lưu riêng trạng thái từng thời điểm. Nếu cần hỏi “Giá trị sau lệnh thứ k là gì?” với nhiều k, ta phải thiết kế lưu lịch sử (snapshot, cấu trúc persistent hoặc phương pháp offline khác).

Một `diff` đã chứa tổng các cập nhật **không tự trả lại được lịch sử thứ tự cập nhật** khi chỉ biết các mốc tổng hợp.

## 22. Cách kiểm thử bằng triển khai chậm

Để xác minh mã mảng hiệu, một phương pháp có ích là viết bản **quét trực tiếp** làm chuẩn tham chiếu. Trên mảng nhỏ, so sánh mọi phần tử kết quả của hai cách với cùng chuỗi lệnh.

```python
def apply_range_adds_naive(values, updates):
    result = list(values)

    for l, r, delta in updates:
        validate_range(len(result), l, r)

        for i in range(l, r):
            result[i] += delta

    return result


cases = [
    ([], [(0, 0, 5)]),
    ([1], [(0, 1, 7), (1, 1, 9)]),
    ([2, 5, 1, 4, 3], [(1, 4, 3), (2, 5, -2), (0, 2, 1)]),
    ([0, 0, 0, 0], [(0, 4, -1), (1, 3, 4), (1, 3, -4)]),
    ([3, -2, 7], [(0, 3, 0), (2, 3, -10)]),
]

for values, updates in cases:
    expected = apply_range_adds_naive(values, updates)
    actual = apply_range_adds(values, updates)
    assert actual == expected
```

Bộ kiểm tra nên có:

- Mảng rỗng, một phần tử, nhiều phần tử.
- Cập nhật toàn mảng và cập nhật chỉ một phần tử.
- Đoạn rỗng, cập nhật `delta=0`.
- Các đoạn chồng lấn, lồng nhau và bằng nhau.
- `delta` dương, âm, các cập nhật triệt tiêu nhau.
- Truy vấn biên sai bị báo lỗi thay vì ghi nhầm vào chỉ số âm.

### Kiểm tra dạng hiệu được cập nhật

Một bất biến khác:

```text
from_difference(to_difference(a)) == a
```

và sau mọi cập nhật hợp lệ:

```text
from_difference(update_diff(to_difference(a)))
  == apply_range_adds_naive(a, updates)
```

Khi cả hai mô hình cho cùng kết quả, ta có thêm niềm tin rằng việc đặt mốc đầu/cuối và cộng dồn chính xác.

## 23. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Coi `[l,r)` lấy cả `r` | Cập nhật thừa một phần tử | Chỉ cập nhật đến `r-1` |
| Với `[L,R]` 1-based ghi `diff[L]` | Lệch mất vị trí đầu | Dùng `diff[L-1]`, `diff[R]` |
| Quên dấu `-delta` ở `r` | Tác động kéo dài tới cuối mảng | Luôn ghi đủ hai mốc |
| Ghi `-delta` tại `r-1` | Làm mất cập nhật ở phần tử cuối đoạn | Dấu tắt đặt tại **r**, không phải r−1 |
| Dùng diff dài n nhưng luôn ghi `diff[n]` | Truy cập ngoài mảng khi `r=n` | Dùng n+1 ô hoặc kiểm tra `r<n` |
| Cộng dồn cả `diff[n]` và xuất thành phần tử thật | Kết quả có n+1 giá trị | Chỉ xuất chỉ số 0..n−1 |
| Xử lý `l=r` như một đoạn có phần tử | Làm thay đổi dữ liệu không đáng có | Bỏ qua cập nhật đoạn rỗng |
| Cho phép `l>r` rồi ghi mốc | “Bật/tắt” theo thứ tự sai | Kiểm tra `l<=r` |
| Để Python xử lý chỉ số âm | Mốc có thể ghi vào cuối list | Kiểm tra `0<=l<=r<=n` |
| Ghi dấu hiệu nhưng quên cộng dồn | Đọc mốc như giá trị cuối | Dựng bằng tổng tiền tố của diff |
| Khởi tạo diff từ hiệu gốc rồi cộng thêm a một lần nữa | Đếm trùng mảng ban đầu | Chọn rõ biểu diễn **delta-only** hay **base-difference** |
| Dùng `diff[n]=0` rồi kỳ vọng tổng mọi hiệu luôn 0 | Hiểu sai vai trò sentinel | Chọn/ghi rõ quy ước ô ngoài miền |
| Materialize sau mỗi cập nhật nhưng báo O(n+q) | Thực tế có thể O(nq) | Chỉ áp dụng O(n+q) khi dựng một lần |
| Nhầm cộng đoạn với gán đoạn | Không thu được giá trị x mong muốn | Gán đoạn cần mô hình khác |
| Hỏi tổng đoạn ngay từ hai ô diff | Sai vì diff chứa mốc thay đổi | Dựng giá trị, xây prefix hoặc dùng cấu trúc online |
| Quên dấu của delta âm | Kết quả cộng trừ sai ở biên | Dùng cùng công thức với delta có dấu |
| Dùng mảng dài theo timestamp rất lớn | Lãng phí bộ nhớ | Dùng sự kiện thưa/sắp tọa độ |
| Sai dấu một góc ở hiệu 2D | Cập nhật lan sang vùng ngoài | Dùng mẫu `+ - - +` ở bốn góc |
| Kết luận mọi kiểu số có cộng/trừ O(1) | Đánh giá thiếu chi phí số lớn/vector | Nêu mô hình và giới hạn kiểu giá trị |
| Không kiểm tra kết quả với mã chậm | Lỗi biên khó phát hiện | Dùng kiểm thử đối chiếu trên mảng nhỏ |

## 24. Bài tập tự luyện và lời giải

**Bài 1 — Cộng vào đoạn.** Cho `a=[2,5,1,4,3]`. Sau `range_add(1,4,3)`, mảng trở thành gì?

*Lời giải:* Các vị trí 1,2,3 tăng 3; kết quả **`[2,8,4,7,3]`**.

**Bài 2 — Mốc đầu/cuối.** Với `n=5`, một lệnh cộng 3 trên `[1,4)` đánh dấu những ô diff nào?

*Lời giải:* **`diff[1]+=3`** và **`diff[4]-=3`**.

**Bài 3 — Vai trò mốc âm.** Điều gì xảy ra nếu quên `diff[r]-=delta`?

*Lời giải:* Mức tăng không được tắt, nên những phần tử từ `r` đến `n-1` cũng có thể bị cộng nhầm.

**Bài 4 — Khôi phục hiệu.** Cho `D=[2,3,-4,3,-1]`. Hãy cộng dồn để dựng `a`.

*Lời giải:* Tổng chạy lần lượt `2,5,1,4,3`, nên **`a=[2,5,1,4,3]`**.

**Bài 5 — Hiệu gốc.** Với `a=[3,3,6,2]`, tìm `D[0:n]` theo hiệu kề nhau.

*Lời giải:* **`[3,0,3,-4]`**. Nếu dùng sentinel dài n+1 của bài, thêm `D[n]=0`.

**Bài 6 — Đoạn toàn mảng.** Trên `n=6`, cần ghi hai dấu mốc nào để cộng `-2` vào toàn bộ mảng?

*Lời giải:* `diff[0]-=2` và `diff[6]+=2`, với diff dài 7 ô.

**Bài 7 — Đoạn một phần tử.** Cộng 8 vào vị trí `i=3` có thể biểu diễn bằng đoạn nào?

*Lời giải:* Dùng `[3,4)`, ghi **`diff[3]+=8`, `diff[4]-=8`**.

**Bài 8 — Đoạn rỗng.** Cập nhật `[n,n)` bằng lượng bất kỳ có được phép không? Kết quả có đổi không?

*Lời giải:* Hợp lệ theo `0<=l<=r<=n`, nhưng đoạn rỗng nên **không đổi phần tử nào**.

**Bài 9 — Quy đổi 1-based.** Đề cho cộng 4 vào vị trí từ 2 đến 5 tính cả hai đầu, đánh số từ 1. Hai mốc 0-based là gì?

*Lời giải:* Đổi `[2,5]` thành `[1,5)`; đánh dấu **`diff[1]+=4`, `diff[5]-=4`**.

**Bài 10 — Chồng lấn.** Với `a=[2,5,1,4,3]` và ba lệnh `[1,4)+3`, `[2,5)-2`, `[0,2)+1`, hãy tính kết quả.

*Lời giải:* **`[3,9,2,5,1]`**.

**Bài 11 — Đếm bao phủ.** Có ba đoạn `[1,4)`, `[2,6)`, `[2,5)` trên `n=7`. Mức phủ từng vị trí?

*Lời giải:* **`[0,1,3,3,2,1,0]`**.

**Bài 12 — Chi phí.** `q` lần cập nhật, mỗi lần dài gần `n`. So sánh sửa trực tiếp và hiệu theo lô xuất một lần.

*Lời giải:* Sửa trực tiếp có thể O(nq). Mảng hiệu ghi O(q) thao tác mốc, khởi tạo và xuất O(n), tổng **O(n+q)**.

**Bài 13 — Materialize nhiều lần.** Sau mỗi một trong `q` cập nhật, ta lại dựng toàn mảng. Tổng thời gian có còn O(n+q) không?

*Lời giải:* **Không.** Có `q` lần dựng, mỗi lần O(n), nên có thể **O(nq)**.

**Bài 14 — Cập nhật gán.** Tại sao `diff[l]+=x; diff[r]-=x` không mô phỏng lệnh “gán mọi phần tử đoạn bằng x”?

*Lời giải:* Hai mốc chỉ cộng thêm `x` vào giá trị cũ, **không thay bằng `x`**. Gán đoạn cần biết và xử lý cách ghi đè.

**Bài 15 — Truy vấn online.** Sau một cập nhật vào diff, muốn đọc giá trị `a[i]` mới thì cần thông tin nào?

*Lời giải:* Cần **tổng tiền tố `diff[0]+...+diff[i]`** để biết tác động tại i. Nếu không có cấu trúc phụ, có thể tốn O(n) ở trường hợp xấu nhất.

**Bài 16 — Online có truy vấn điểm.** Nếu liên tục cộng đoạn và hỏi giá trị tại một điểm, cấu trúc nào thường phù hợp?

*Lời giải:* **Fenwick tree trên các mốc hiệu**, hỗ trợ cập nhật hai biên và tính tổng tiền tố trong O(log n), với điều kiện thích hợp.

**Bài 17 — Sentinel.** Với diff dài n+1, tại sao không xuất `diff[n]` như một phần tử sau khi cộng dồn?

*Lời giải:* `diff[n]` là **mốc kết thúc sau chỉ số n-1**, không ứng với phần tử thật. Dãy kết quả phải có đúng n phần tử.

**Bài 18 — Âm và triệt tiêu.** Nếu cùng đoạn nhận hai lệnh `+5` và `-5`, kết quả cuối thay đổi ra sao?

*Lời giải:* Hai tác động cộng lại bằng 0; mọi vị trí **giữ nguyên** so với trước hai lệnh.

**Bài 19 — Mốc tọa độ thưa.** Tại sao không nên dùng mảng dài một tỷ phần tử nếu chỉ có vài trăm khoảng trên trục timestamp?

*Lời giải:* Tốn bộ nhớ theo **giá trị tọa độ** chứ không theo số khoảng. Có thể dùng dictionary lưu mốc và sắp xếp sự kiện.

**Bài 20 — Hiệu 2D.** Cộng `delta` vào hình chữ nhật `[r1,r2)×[c1,c2)` cần thay đổi bốn ô góc như thế nào?

*Lời giải:* **`+delta` tại `(r1,c1)` và `(r2,c2)`**, **`-delta` tại `(r1,c2)` và `(r2,c1)`**.

**Bài 21 — Kiểm thử.** Nêu hai bất biến hữu ích để kiểm tra bản cài mảng hiệu.

*Lời giải:* `from_difference(to_difference(a)) == a`; và kết quả sau nhiều cập nhật theo diff phải bằng kết quả của vòng lặp sửa trực tiếp cho cùng các lệnh.

**Bài 22 — Mốc biên phải.** Với cập nhật `[1,4)`, tại sao ghi `diff[3]-=delta` là sai?

*Lời giải:* Chỉ số 3 **vẫn thuộc đoạn**, cần nhận `delta`. Mốc tắt phải ở **`r=4`**, ngay sau phần tử cuối được cập nhật.

## 25. Tổng kết

**Mảng hiệu** lưu sự thay đổi giữa những vị trí kề nhau. Với cộng cùng một `delta` trên đoạn **0-based nửa mở `[l,r)`**, chỉ cần ghi:

```text
diff[l] += delta
diff[r] -= delta
```

trong mảng hiệu dài `n+1`, rồi lấy **tổng cộng dồn** để biết lượng tác động tại từng vị trí. Nếu hiệu được xây từ mảng gốc, tổng cộng dồn cho ngay giá trị cuối; nếu hiệu chỉ lưu các lượng cập nhật, phải **cộng lượng tác động vào mảng gốc**. Hai cách biểu diễn cần được sử dụng nhất quán.

Với `q` lệnh cộng đoạn và **một lần** xuất kết quả, thuật toán tốn **O(n+q) thời gian và O(n) bộ nhớ**, thay vì có thể O(nq) khi cập nhật từng phần tử trực tiếp. Nó hỗ trợ tự nhiên các đoạn chồng lấn, đoạn lồng nhau, lượng tăng âm, đoạn rỗng, đếm mức bao phủ và cả biến thể đánh dấu sự kiện theo tọa độ hoặc hình chữ nhật 2D.

**Giới hạn quan trọng:** mảng hiệu đơn giản tối ưu cho **ghi cập nhật theo lô**, không tự cho phép hỏi tổng đoạn trực tuyến O(1) sau mỗi lần cập nhật, và không biến lệnh **gán đoạn** thành lệnh cộng đoạn. Khi phải vừa cập nhật vừa truy vấn thường xuyên, hãy lựa chọn cấu trúc động có bất biến phù hợp. Điều cần giữ vững là **quy ước biên, hai dấu mốc đối nhau và bước khôi phục bằng tổng cộng dồn**.

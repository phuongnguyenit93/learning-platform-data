# Duy trì giá trị nhỏ nhất hoặc lớn nhất cùng ngăn xếp

## 1. Bài toán: vừa thao tác LIFO, vừa biết min/max hiện tại

**Ngăn xếp (stack)** là kiểu dữ liệu trừu tượng tuân theo nguyên tắc **LIFO (Last In, First Out)**: phần tử được thêm vào sau cùng sẽ được lấy ra đầu tiên. Giao diện cơ bản gồm `push(x)` (thêm vào đỉnh), `pop()` (lấy và xóa đỉnh), `peek()` (xem đỉnh) và `is_empty()` (kiểm tra rỗng).

Giả sử một chương trình lần lượt đưa các số `7, 3, 5, 3, 9` vào stack. Ngoài `pop()` và `peek()`, chương trình còn muốn:

- `get_min()`: trả **giá trị nhỏ nhất** trong các phần tử **hiện còn** ở stack.
- `get_max()`: trả **giá trị lớn nhất** trong các phần tử **hiện còn** ở stack.

Khi `pop()` loại bỏ một phần tử, min/max phải được cập nhật theo **stack hiện tại**, chứ không theo toàn bộ lịch sử các phần tử từng được thêm. Ví dụ, stack `[7, 3, 5]` có min bằng `3`, max bằng `7`; sau hai lần `pop()`, stack chỉ còn `[7]` nên cả min và max đều bằng `7`.

Một cách trực tiếp là quét toàn bộ stack mỗi khi cần min/max. Nhưng nếu ứng dụng truy vấn rất nhiều lần, mỗi lần quét mất `O(n)` thời gian với `n` phần tử. Bài toán **Min Stack / Max Stack** yêu cầu duy trì thêm thông tin để lấy cực trị trong **`O(1)` thời gian**.

Đây là ví dụ về việc bổ sung **bất biến dữ liệu và thông tin tổng hợp** lên một cấu trúc cơ bản. Trong học phần **Cấu trúc dữ liệu**, ta cần hiểu thao tác nào cập nhật thông tin tổng hợp, vì sao thuật toán đúng, và chi phí thời gian/bộ nhớ phải trả để lựa chọn cách cài đặt phù hợp.

### Một ví dụ trực quan

Quy ước bên **phải** là đỉnh của stack:

```text
Giá trị:       [7, 3, 5, 3, 9]
                                 ↑ top
Cực tiểu:       3
Cực đại:        9

pop() → 9
Stack:          [7, 3, 5, 3]
Cực tiểu:        3
Cực đại:         7

pop() → 3
Stack:          [7, 3, 5]
Cực tiểu:        3  (vẫn còn một số 3 khác)
Cực đại:         7
```

Đặc biệt, **giá trị trùng lặp** buộc ta thiết kế việc cập nhật min/max cẩn thận. Nếu lấy ra một số `3`, không có nghĩa min phải đổi ngay: có thể vẫn còn số `3` khác nằm bên dưới.

## 2. Hợp đồng API và những điều phải đúng

Một Min–Max Stack hỗ trợ giao diện sau:

| Phép toán | Kết quả | Tác động lên stack |
|---|---|---|
| `push(x)` | Thêm giá trị `x` | Tăng kích thước một đơn vị |
| `pop()` | Trả và xóa giá trị đỉnh | Giảm kích thước một đơn vị |
| `peek()` | Trả giá trị đỉnh | Không đổi |
| `get_min()` | Trả cực tiểu của toàn bộ phần tử hiện có | Không đổi |
| `get_max()` | Trả cực đại của toàn bộ phần tử hiện có | Không đổi |
| `is_empty()` | Stack có rỗng hay không | Không đổi |
| `size()` | Số phần tử | Không đổi |

**Điều kiện biên:** khi stack rỗng, không tồn tại đỉnh, min hay max. Trong các ví dụ dưới đây, `pop()`, `peek()`, `get_min()` và `get_max()` sẽ ném `IndexError` nếu được gọi khi rỗng. Một API khác có thể trả kiểu kết quả tùy chọn; điều cần thiết là phải có hợp đồng rõ ràng.

Giả sử stack hiện có dãy `S = [v₀, v₁, ..., vₙ₋₁]` từ đáy lên đỉnh. Với `n > 0`, kết quả phải thỏa mãn:

\[
\operatorname{get\_min}(S)=\min\{v_0,v_1,\ldots,v_{n-1}\}
\]

\[
\operatorname{get\_max}(S)=\max\{v_0,v_1,\ldots,v_{n-1}\}
\]

Đồng thời, `pop()` vẫn phải trả `vₙ₋₁`, đúng nguyên tắc LIFO. Việc bổ sung truy vấn cực trị **không được thay đổi thứ tự** mà stack lưu và lấy phần tử.

Để đơn giản, bài này giả định các giá trị **so sánh được với nhau theo một thứ tự nhất quán** (chẳng hạn số nguyên hữu hạn). Với Python, không nên trộn những kiểu không so sánh được (như `int` và `str`), và cần xử lý riêng giá trị `NaN` vì các phép so sánh thông thường không xác lập thứ tự đầy đủ cho nó.

## 3. Cách cơ bản: quét stack khi cần min/max

Với `list` của Python làm stack, ta có thể tính min và max bằng cách duyệt các phần tử đang có:

```python
class ScanningMinMaxStack:
    def __init__(self):
        self._values = []

    def push(self, value):
        self._values.append(value)

    def pop(self):
        if not self._values:
            raise IndexError("pop trên stack rỗng")
        return self._values.pop()

    def peek(self):
        if not self._values:
            raise IndexError("peek trên stack rỗng")
        return self._values[-1]

    def get_min(self):
        if not self._values:
            raise IndexError("get_min trên stack rỗng")
        return min(self._values)

    def get_max(self):
        if not self._values:
            raise IndexError("get_max trên stack rỗng")
        return max(self._values)
```

Với `n` phần tử, `push` và `pop` ở cuối mảng động có chi phí trung bình phân bổ `O(1)`, `peek` là `O(1)`, nhưng `get_min` và `get_max` mất **`O(n)`** thời gian vì phải duyệt các giá trị. Bộ nhớ dùng để lưu dữ liệu là `O(n)`.

Giải pháp này vẫn **đúng** và thường đủ tốt nếu stack nhỏ hoặc các truy vấn min/max hiếm xảy ra. Tuy nhiên, nếu thuật toán cần min/max sau mỗi thao tác trên stack lớn, quét liên tục có thể trở thành nút thắt. Ta có thể đổi một lượng bộ nhớ bổ sung lấy truy vấn `O(1)`.

## 4. Ý tưởng chính: lưu cực trị của từng tiền tố

Hãy tưởng tượng mỗi lần `push(x)`, ta lưu thêm hai thông tin:

- **Cực tiểu hiện tại** sau khi thêm `x`.
- **Cực đại hiện tại** sau khi thêm `x`.

Mỗi phần tử không còn chỉ là `value`, mà là một bản ghi:

```text
(value, min_so_far, max_so_far)
```

Ở đây, `min_so_far` và `max_so_far` là min/max của **tất cả phần tử từ đáy đến chính vị trí bản ghi đó**. Ví dụ:

| Thứ tự push | Giá trị thêm | Bản ghi lưu vào stack |
|---:|---:|---|
| 1 | `7` | `(7, 7, 7)` |
| 2 | `3` | `(3, 3, 7)` |
| 3 | `5` | `(5, 3, 7)` |
| 4 | `3` | `(3, 3, 7)` |
| 5 | `9` | `(9, 3, 9)` |

Bản ghi trên đỉnh luôn biết **min/max của toàn bộ stack hiện tại**:

```text
Đáy                                              Đỉnh
  ↓                                                 ↓
(7,7,7) → (3,3,7) → (5,3,7) → (3,3,7) → (9,3,9)
                                             └─ get_min() = 3
                                                get_max() = 9
```

Nếu gọi `pop()`, ta bỏ **toàn bộ bản ghi đỉnh**. Bản ghi mới lộ ra đã lưu sẵn min/max của tiền tố còn lại, nên không cần quét, đếm hay tính lại các phần tử cũ.

### Công thức cập nhật

Nếu stack trước khi thêm `x` đang rỗng:

\[
m_{\text{new}} = x,\qquad M_{\text{new}} = x
\]

Nếu không rỗng và đỉnh cũ chứa `m_old`, `M_old`:

\[
m_{\text{new}} = \min(x,m_{\text{old}})
\]

\[
M_{\text{new}} = \max(x,M_{\text{old}})
\]

Như vậy, muốn cập nhật min/max khi thêm phần tử, ta chỉ cần **hai phép so sánh với cực trị của tiền tố cũ**. Muốn lấy min/max thì chỉ cần xem hai trường của bản ghi trên đỉnh.

## 5. Cài đặt Python: một stack chứa bộ ba giá trị

Phiên bản sau cài đầy đủ `push`, `pop`, `peek`, `get_min`, `get_max`, `size` và `is_empty`. Toàn bộ dữ liệu được giữ trong một danh sách `_frames`; mỗi phần tử của danh sách là bộ ba `(value, current_min, current_max)`.

```python
class MinMaxStack:
    def __init__(self):
        self._frames = []

    def is_empty(self):
        return len(self._frames) == 0

    def size(self):
        return len(self._frames)

    def push(self, value):
        if self.is_empty():
            current_min = value
            current_max = value
        else:
            _, previous_min, previous_max = self._frames[-1]
            current_min = (
                value if value < previous_min else previous_min
            )
            current_max = (
                value if value > previous_max else previous_max
            )

        self._frames.append((value, current_min, current_max))

    def pop(self):
        if self.is_empty():
            raise IndexError("pop trên stack rỗng")
        value, _, _ = self._frames.pop()
        return value

    def peek(self):
        if self.is_empty():
            raise IndexError("peek trên stack rỗng")
        return self._frames[-1][0]

    def get_min(self):
        if self.is_empty():
            raise IndexError("get_min trên stack rỗng")
        return self._frames[-1][1]

    def get_max(self):
        if self.is_empty():
            raise IndexError("get_max trên stack rỗng")
        return self._frames[-1][2]


stack = MinMaxStack()
for x in [7, 3, 5, 3, 9]:
    stack.push(x)

print(stack.peek())     # 9
print(stack.get_min())  # 3
print(stack.get_max())  # 9

print(stack.pop())      # 9
print(stack.get_min())  # 3
print(stack.get_max())  # 7

print(stack.pop())      # 3
print(stack.get_min())  # 3 (vẫn còn số 3 bên dưới)
print(stack.pop())      # 5
print(stack.pop())      # 3
print(stack.get_min())  # 7
print(stack.get_max())  # 7
```

Một đặc điểm hữu ích là **chỉ số logic của phần tử đỉnh luôn trùng với bản ghi chứa cực trị hiện thời**. Vì vậy `get_min()` và `get_max()` đọc trực tiếp trường thích hợp ở `_frames[-1]`. Không có vòng lặp tìm kiếm trong hai phương thức này.

### Theo dõi trạng thái sau từng thao tác

Trong bảng, nội dung stack được ghi từ đáy đến đỉnh:

| Bước | Thao tác | Stack giá trị sau thao tác | `get_min()` | `get_max()` |
|---:|---|---|---:|---:|
| 0 | Khởi tạo | `[]` | Chưa xác định | Chưa xác định |
| 1 | `push(7)` | `[7]` | 7 | 7 |
| 2 | `push(3)` | `[7, 3]` | 3 | 7 |
| 3 | `push(5)` | `[7, 3, 5]` | 3 | 7 |
| 4 | `push(3)` | `[7, 3, 5, 3]` | 3 | 7 |
| 5 | `push(9)` | `[7, 3, 5, 3, 9]` | 3 | 9 |
| 6 | `pop() → 9` | `[7, 3, 5, 3]` | 3 | 7 |
| 7 | `pop() → 3` | `[7, 3, 5]` | 3 | 7 |
| 8 | `pop() → 5` | `[7, 3]` | 3 | 7 |
| 9 | `pop() → 3` | `[7]` | 7 | 7 |
| 10 | `pop() → 7` | `[]` | Chưa xác định | Chưa xác định |

Tại bước 7, min **vẫn là 3** dù một số `3` đã bị lấy ra. Tại bước 9, khi số `3` cuối cùng bị lấy ra, cực tiểu của stack còn lại tự động trở về `7`, vì bản ghi của `7` đã lưu sẵn cặp cực trị `(7, 7)`.

## 6. Chứng minh tính đúng đắn bằng bất biến

Giả sử với stack có `n` phần tử từ đáy lên đỉnh, bản ghi ở vị trí `i` (đếm từ `0`) thỏa mãn:

\[
\text{frame}[i].\text{min}
  = \min(v_0, v_1, \ldots, v_i)
\]

\[
\text{frame}[i].\text{max}
  = \max(v_0, v_1, \ldots, v_i)
\]

Đây là **bất biến tiền tố cực trị**.

**Trường hợp ban đầu.** Stack rỗng chưa có bản ghi nào. Khi `push(x)` lần đầu, bản ghi `(x, x, x)` đúng vì tiền tố chỉ chứa `x`.

**Bước `push(x)`.** Giả sử các bản ghi cũ đều đúng. Mọi giá trị của tiền tố mới nằm trong tiền tố cũ hoặc chính là `x`. Do đó min mới bằng `min(x, min_cũ)` và max mới bằng `max(x, max_cũ)`. Thêm bộ ba tương ứng vào cuối giữ nguyên thứ tự các giá trị, nên bất biến tiếp tục đúng.

**Bước `pop()`.** Xóa bản ghi cuối cũng xóa đúng giá trị cuối (LIFO). Các bản ghi bên dưới không bị sửa. Bản ghi lộ ra ở đỉnh vốn đã giữ cực trị của chính tiền tố tương ứng, nên không cần cập nhật các bản ghi còn lại.

**Bước `peek()`, `get_min()`, `get_max()`.** Các phương thức chỉ đọc đỉnh và không thay đổi dữ liệu. Do bất biến, cực trị tại đỉnh chính là cực trị của toàn bộ stack hiện tại.

Vì các thao tác giữ được bất biến, sau bất kỳ chuỗi `push`/`pop` hợp lệ nào, truy vấn min/max đều trả giá trị đúng.

## 7. Độ phức tạp: thời gian O(1) đổi lấy bộ nhớ bổ sung

Giả sử `n` là số phần tử trong stack, việc so sánh hai giá trị tốn `O(1)` trong mô hình thuật toán thông thường và mảng động được mở rộng theo chiến lược chuẩn.

| Phép toán | Stack chỉ lưu giá trị, quét để tìm min/max | MinMaxStack lưu min/max tiền tố |
|---|---|---|
| `push(x)` | `O(1)` amortized | `O(1)` amortized |
| `pop()` | `O(1)` amortized | `O(1)` amortized |
| `peek()` | `O(1)` | `O(1)` |
| `get_min()` | `O(n)` | **`O(1)`** |
| `get_max()` | `O(n)` | **`O(1)`** |
| `is_empty()`, `size()` | `O(1)` | `O(1)` |
| Tổng bộ nhớ lưu stack | `O(n)` | `O(n)`, nhưng mỗi bản ghi giữ thêm hai cực trị |

**Phân biệt độ phức tạp tổng và bộ nhớ phụ:** cả hai cách vẫn dùng `O(n)` bộ nhớ tổng. Tuy nhiên, `MinMaxStack` lưu thêm hai giá trị/tham chiếu cho mỗi phần tử, nên bộ nhớ **bổ sung so với stack thường** cũng là `O(n)`. Không nên nói nó chỉ dùng `O(1)` bộ nhớ vì riêng truy vấn cực trị dùng `O(1)` thời gian.

Vì Python `list` là mảng động, `append` và `pop` ở cuối thường tốn `O(1)` **trung bình phân bổ (amortized)**. Một lần cấp phát lại bộ nhớ trong `append` (hoặc một lần thu nhỏ của một cách cài đặt mảng động) có thể tốn nhiều hơn. Nếu cài bằng danh sách liên kết đơn, đặt đỉnh ở đầu danh sách và lưu cực trị trong từng nút thì có thể thực hiện các thao tác đỉnh trong `O(1)` theo mô hình cấp phát nút chuẩn.

Trường hợp so sánh có chi phí lớn (ví dụ chuỗi rất dài hoặc đối tượng tùy biến) thì `push` còn mang chi phí so sánh. Phân tích `O(1)` ở đây giả định phép so sánh là một thao tác cơ bản.

## 8. Phương án hai hoặc ba stack song song

Không bắt buộc phải lưu bộ ba trong mỗi bản ghi. Một thiết kế tương đương sử dụng:

- `values`: stack chứa giá trị thực tế.
- `mins`: stack chứa min của mỗi tiền tố.
- `maxs`: stack chứa max của mỗi tiền tố.

Khi `push(x)`, thêm `x` vào `values`, min mới vào `mins` và max mới vào `maxs`. Khi `pop()`, **pop cả ba stack**; khi truy vấn, chỉ nhìn đỉnh `mins` hoặc `maxs`.

```text
values: [7, 3, 5, 3, 9]
mins:   [7, 3, 3, 3, 3]
maxs:   [7, 7, 7, 7, 9]
                    ↑
                  top

pop() đồng thời ở cả ba:
values: [7, 3, 5, 3]
mins:   [7, 3, 3, 3]
maxs:   [7, 7, 7, 7]
```

**Bất biến đồng bộ:** mọi lúc `len(values) == len(mins) == len(maxs)`. Tại chỉ số `i`, `mins[i]` là min và `maxs[i]` là max của `values[0..i]`. Nếu quên pop từ một stack phụ, các cực trị có thể lệch với nội dung thực.

Hai phương án **bộ ba trong một stack** và **ba stack song song** đều có thời gian truy vấn `O(1)` và bộ nhớ `O(n)`. Bộ ba giúp các trường của cùng một tiền tố gắn chặt trong một bản ghi; ba stack có thể thuận tiện trong một số thư viện hoặc bài toán chỉ cần thêm một loại cực trị.

## 9. Tối ưu bộ nhớ phụ: chỉ lưu các mốc cực trị mới

Khi push một giá trị **không làm thay đổi** min hiện tại, không nhất thiết phải thêm một mục min mới vào stack phụ. Chẳng hạn với các giá trị `[7, 3, 5, 8]`, cực tiểu chỉ thay đổi ở `7` rồi `3`; các giá trị `5` và `8` không tạo min mới.

Ta có thể duy trì riêng:

- `values`: toàn bộ giá trị của stack chính.
- `mins`: các **mốc cực tiểu mới**, từ cũ đến mới.
- `maxs`: các **mốc cực đại mới**, từ cũ đến mới.

Mỗi mốc phụ lưu `(giá_trị_cực_trị, số_lần_xuất_hiện)` để xử lý **giá trị trùng nhau**.

### Vì sao cần đếm số lần trùng?

Giả sử lần lượt `push(5)`, `push(2)`, `push(2)`. Nếu stack min phụ chỉ lưu `[5, 2]`, rồi khi `pop()` một số `2` ta vội xóa mốc `2`, min phụ sẽ trở thành `5` — **sai**, vì vẫn còn số `2` trong stack chính.

Cách đúng: lưu mốc cực tiểu `(2, 2)`, nghĩa là cực tiểu `2` đã được thêm hai lần tại cấp hiện tại. Sau khi pop một số `2`, giảm bộ đếm từ `2` xuống `1`; chỉ xóa mốc khi số lần còn lại bằng `0`.

```text
push(5): values = [5]       mins = [(5, 1)]
push(2): values = [5, 2]    mins = [(5, 1), (2, 1)]
push(2): values = [5, 2, 2] mins = [(5, 1), (2, 2)]

pop() → 2
         values = [5, 2]    mins = [(5, 1), (2, 1)]
get_min() → 2

pop() → 2
         values = [5]       mins = [(5, 1)]
get_min() → 5
```

### Cài đặt Python dùng mốc và bộ đếm

Lớp dưới đây quản lý cả min và max. Các phần tử trong `_mins` và `_maxs` là danh sách hai phần tử `[value, count]` để có thể giảm `count` trực tiếp.

```python
class CompactMinMaxStack:
    def __init__(self):
        self._values = []
        self._mins = []   # [record_minimum, count]
        self._maxs = []   # [record_maximum, count]

    def is_empty(self):
        return not self._values

    def size(self):
        return len(self._values)

    def push(self, value):
        # Xác định quan hệ so sánh trước khi sửa các stack.
        if self._values:
            min_value = self._mins[-1][0]
            max_value = self._maxs[-1][0]
            new_min = value < min_value
            same_min = value == min_value
            new_max = value > max_value
            same_max = value == max_value
        else:
            new_min = new_max = True
            same_min = same_max = False

        self._values.append(value)

        if new_min:
            self._mins.append([value, 1])
        elif same_min:
            self._mins[-1][1] += 1

        if new_max:
            self._maxs.append([value, 1])
        elif same_max:
            self._maxs[-1][1] += 1

    def pop(self):
        if self.is_empty():
            raise IndexError("pop trên stack rỗng")

        value = self._values.pop()

        if value == self._mins[-1][0]:
            self._mins[-1][1] -= 1
            if self._mins[-1][1] == 0:
                self._mins.pop()

        if value == self._maxs[-1][0]:
            self._maxs[-1][1] -= 1
            if self._maxs[-1][1] == 0:
                self._maxs.pop()

        return value

    def peek(self):
        if self.is_empty():
            raise IndexError("peek trên stack rỗng")
        return self._values[-1]

    def get_min(self):
        if self.is_empty():
            raise IndexError("get_min trên stack rỗng")
        return self._mins[-1][0]

    def get_max(self):
        if self.is_empty():
            raise IndexError("get_max trên stack rỗng")
        return self._maxs[-1][0]


s = CompactMinMaxStack()
for value in [5, 2, 2, 7, 7]:
    s.push(value)

print(s.get_min(), s.get_max())  # 2 7
print(s.pop())                  # 7
print(s.get_max())              # 7 (vẫn còn số 7)
print(s.pop())                  # 7
print(s.get_max())              # 5
print(s.pop())                  # 2
print(s.get_min())              # 2 (vẫn còn số 2)
print(s.pop())                  # 2
print(s.get_min())              # 5
```

### Bất biến của các mốc

`_mins[-1]` chứa **min của stack chính hiện tại**, cùng bộ đếm các lần giá trị đó đang tồn tại trên đoạn stack phía trên mốc cực tiểu trước đó. Các mốc cũ vẫn được lưu bên dưới để khi cực tiểu hiện tại biến mất do pop, cực tiểu trước đó lập tức lộ ra. `_maxs` hoạt động tương tự cho cực đại.

Tại sao cách đếm hoạt động? Nếu một cực tiểu mới **nhỏ hơn hẳn** được push, các phần tử cũ vẫn nằm phía dưới nó. Do tính chất LIFO, trước khi pop tới các phần tử cũ, phải pop hết các phần tử được thêm sau cực tiểu mới. Vì thế không thể “quay về” một mốc cũ quá sớm. Các lần push giá trị **bằng** cực tiểu hiện tại tăng bộ đếm thay vì tạo thêm một mốc giống hệt.

Với các giá trị được so sánh nhất quán, mọi `push`/`pop` chỉ sửa một lượng hằng số thông tin trên mỗi stack phụ, nên vẫn **`O(1)` trung bình phân bổ** với cài đặt bằng mảng động, còn `get_min`/`get_max` là **`O(1)`**.

### Chi phí bộ nhớ của cách lưu mốc

Gọi `k_min` là số mốc trong `_mins`, `k_max` là số mốc trong `_maxs`, mỗi số không vượt quá `n`:

- Stack chính `_values` lưu `n` giá trị, cần `O(n)` bộ nhớ.
- Hai stack phụ cần `O(k_min + k_max)` bộ nhớ, có thể **ít hơn `O(n)` trong một số dãy dữ liệu**.
- **Trường hợp xấu nhất vẫn là `O(n)` bộ nhớ phụ**, chẳng hạn dãy giảm dần liên tục tạo thêm mốc cực tiểu ở mỗi lần push (hoặc dãy tăng dần tạo mốc cực đại).

Đừng hiểu “chỉ lưu mốc” là bảo đảm bộ nhớ phụ `O(1)`. Đó là một **tối ưu dựa trên phân bố và thứ tự dữ liệu**, không phải cải thiện chặn trên trong trường hợp xấu nhất.

Trong mã minh họa, giả định phép so sánh có nghĩa và việc cấp phát thành công. Một triển khai thư viện chịu lỗi cần cân nhắc thêm chính sách khi các lần cấp phát cho stack phụ thất bại, để các stack vẫn đồng bộ; điều này nằm ngoài mô hình độ phức tạp cơ bản của bài.

## 10. Những tình huống biên và lỗi triển khai thường gặp

### 10.1. Stack rỗng

Khi rỗng, **không tồn tại min hoặc max**. Không nên mặc định trả `0` vì `0` có thể là một giá trị dữ liệu hợp lệ và thường không phải cực trị “trung tính” với mọi tập giá trị.

```python
s = MinMaxStack()
assert s.is_empty()

try:
    s.get_min()
except IndexError:
    print("Stack rỗng: không tồn tại min")
```

Nếu muốn tránh ngoại lệ cho truy vấn rỗng, có thể thiết kế `try_get_min()` trả `(success, value)` hoặc kiểu `Optional` có trạng thái riêng. Giao diện phải phân biệt chính xác “không có kết quả” và “giá trị kết quả là `None`” nếu cho phép lưu `None`.

### 10.2. Giá trị cực trị trùng lặp

Đừng chỉ lưu “cực tiểu trước đó” rồi thay đổi khi một bản ghi cực tiểu bị pop mà không xét còn bản sao khác hay không. Cách **lưu cực trị theo từng tiền tố** ở phần 4 xử lý trùng lặp tự nhiên. Cách **lưu mốc** ở phần 9 cần bộ đếm hoặc lưu riêng từng lần trùng.

### 10.3. Cực trị bị lấy ra

Nếu min hiện tại chính là đỉnh và bị `pop`, **min mới không nhất thiết là giá trị vừa đứng thứ hai từ đỉnh**. Ví dụ `[8, 4, 6, 2]`: sau khi pop `2`, min mới là `4` dù đỉnh mới là `6`. Vì vậy không thể cập nhật min chỉ bằng cách so sánh phần tử vừa pop với đỉnh mới.

### 10.4. Số âm, số bằng nhau và giá trị đơn lẻ

Stack `[-3, -8, 0]` có min `-8`, max `0`. Stack chứa duy nhất `[4]` có min và max đều là `4`. Dữ liệu có cả âm, dương, số `0` và trùng lặp **không làm thay đổi thuật toán**, miễn là phép so sánh xác định một thứ tự hợp lệ.

### 10.5. Dữ liệu không so sánh được hoặc thay đổi sau khi push

Một số vấn đề thực tế có thể phá bất biến đã lưu:

- **Trộn kiểu không có thứ tự chung**, chẳng hạn `push(3)` rồi `push("A")` trong Python, khiến phép so sánh có thể ném `TypeError`.
- **Giá trị `NaN`**, vì `NaN < x`, `NaN > x` và `NaN == x` đều không theo kỳ vọng của thứ tự số thông thường.
- **Đối tượng có thuộc tính ưu tiên thay đổi được.** Nếu đã push một đối tượng rồi sửa trường dùng để so sánh, cực trị lưu sẵn có thể không phản ánh giá trị mới.
- **Tiêu chí so sánh không nhất quán.** Nếu `<`, `>` và `==` không biểu diễn cùng một thứ tự, nhất là ở phương án đếm mốc, kết quả có thể sai.

Khi cần lưu đối tượng phức tạp, nên quy định một **khóa so sánh ổn định** (ví dụ `priority` số nguyên) và lưu khóa cùng phần tử lúc push, hoặc chủ động cập nhật cấu trúc nếu khóa thay đổi. Tính đúng đắn của Min–Max Stack dựa trên dữ liệu so sánh ổn định trong thời gian nó còn ở stack.

### 10.6. Truy vấn và sửa trong hệ thống đồng thời

Mã Python ví dụ không cung cấp bảo đảm thao tác nguyên tử cho nhiều luồng. Nếu một luồng gọi `is_empty()` rồi luồng khác pop phần tử cuối trước khi luồng đầu gọi `get_min()`, thao tác sau vẫn có thể gặp rỗng. Cần khóa hoặc cấu trúc đồng thời phù hợp, đặc biệt với cách dùng nhiều stack phụ phải được cập nhật cùng nhau.

## 11. Ứng dụng và cách chọn cấu trúc phù hợp

**Min–Max Stack** hữu ích khi dữ liệu được thêm/xóa theo LIFO và ứng dụng thường xuyên cần hỏi cực trị của **phần tử còn hoạt động**:

- **Mô phỏng và quay lui:** mỗi bước push một trạng thái có chi phí/độ ưu tiên; khi quay lui pop trạng thái mới nhất, min/max của các trạng thái còn lại được khôi phục ngay.
- **Lịch sử giới hạn theo chiều sâu:** trong quá trình đi sâu từng cấp xử lý, duy trì mức tài nguyên nhỏ nhất/lớn nhất đã xuất hiện trên **đường đi đang hoạt động**.
- **Thuật toán đơn điệu, bài toán truy vấn cực trị động:** min/max stack có thể là thành phần của cấu trúc lớn hơn, ví dụ một **queue hỗ trợ truy vấn min** được tạo từ hai stack có cực tiểu.

Cần phân biệt Min–Max Stack với cấu trúc chọn phần tử nhỏ nhất để lấy ra: `pop()` của stack **luôn lấy đỉnh**, không lấy phần tử nhỏ nhất hay lớn nhất. Nếu bài toán yêu cầu **xóa cực tiểu nhanh nhất** bất kể vị trí, **priority queue/heap** thường phù hợp hơn, vì Min–Max Stack chỉ hỗ trợ **xem** cực trị `O(1)`.

### Bảng chọn giải pháp

| Tình huống | Cách tiếp cận phù hợp | Lý do |
|---|---|---|
| Stack nhỏ, ít hỏi cực trị | Quét khi gọi `get_min`/`get_max` | Cài đơn giản, ít bộ nhớ bổ sung |
| Hỏi min và max sau nhiều `push`/`pop` | Bộ ba `(value, min, max)` | Mọi truy vấn cực trị `O(1)`, dễ chứng minh |
| Chỉ cần min | Bộ đôi `(value, min)` hoặc stack min phụ | Không phải lưu max không sử dụng |
| Muốn tiết kiệm thông tin phụ khi cực trị ít thay đổi | Stack mốc min/max có bộ đếm | Có thể giảm số bản ghi cực trị |
| Cần lấy và xóa **phần tử nhỏ nhất** | Heap hoặc cấu trúc ưu tiên | Thứ tự lấy không còn là LIFO |
| Cần cực trị của hàng đợi FIFO | Queue hỗ trợ min/max (ví dụ dùng hai stack) | Bảo toàn thứ tự FIFO thay vì LIFO |

**Lựa chọn quan trọng nhất** là hợp đồng thao tác. Nếu hệ thống thực sự cần lấy phần tử theo thời gian thêm gần nhất thì stack là cấu trúc chính xác. Truy vấn min/max có thể bổ sung hiệu quả nhờ thông tin tiền tố, nhưng không biến stack thành hàng đợi ưu tiên.

## 12. Bài tập tự kiểm tra và đáp án

### Bài 1. Theo dõi min và max qua các lần pop

Khởi tạo stack rỗng, thực hiện:

```text
push(6), push(2), push(8), push(2),
pop(), get_min(), get_max(), pop(), get_min(), pop(), get_min()
```

Hãy xác định từng giá trị trả về và trạng thái stack cuối cùng.

**Đáp án:** Sau bốn lần push, stack là `[6, 2, 8, 2]`. `pop()` trả `2`, còn `[6, 2, 8]`. `get_min() = 2`, `get_max() = 8`. `pop()` tiếp theo trả `8`, còn `[6, 2]`; `get_min() = 2`. `pop()` tiếp theo trả `2`, còn `[6]`; `get_min() = 6`.

### Bài 2. Lưu các bộ ba

Với lần lượt các lệnh `push(4)`, `push(1)`, `push(7)`, hãy viết nội dung các bản ghi `(value, min_so_far, max_so_far)`.

**Đáp án:** Từ đáy lên đỉnh: `(4, 4, 4)`, `(1, 1, 4)`, `(7, 1, 7)`. Khi pop `7`, bản ghi `(1, 1, 4)` lộ ra nên cực trị trở thành `1` và `4`.

### Bài 3. Chặn trên bộ nhớ

Nếu MinMaxStack lưu hai cực trị kèm mỗi giá trị, với `n` phần tử ta cần bao nhiêu bộ nhớ phụ để truy vấn `O(1)`? Nếu chỉ lưu mốc cực trị, chặn trên trường hợp xấu nhất có đổi không?

**Đáp án:** Bộ nhớ phụ `O(n)` vì có hai thông tin cực trị cho mỗi phần tử. Lưu mốc có thể giảm bộ nhớ trong một số dãy nhưng trường hợp xấu nhất vẫn `O(n)` khi các phần tử liên tục tạo cực trị mới.

### Bài 4. Phần tử trùng lặp

Nếu stack chính là `[5, 2, 2]` và mốc min có `[(5, 1), (2, 2)]`, sau một lần pop thì mốc min và giá trị `get_min()` là gì?

**Đáp án:** Pop trả `2`. Mốc min trở thành `[(5, 1), (2, 1)]`, và `get_min() = 2`. Phải pop thêm số `2` còn lại thì mốc `(2, 1)` mới bị xóa.

### Bài 5. Vì sao không chỉ nhìn đỉnh mới?

Stack đang chứa `[9, 4, 7, 2]`. Sau khi pop `2`, đỉnh là `7` nhưng min là bao nhiêu? Giải thích.

**Đáp án:** Min là `4`. Đỉnh mới không nhất thiết là min; phải nhớ cực trị của toàn bộ tiền tố `[9, 4, 7]`, thông qua bản ghi cực trị hoặc stack phụ.

### Bài 6. Bài toán nào cần cấu trúc khác?

Bạn muốn “mỗi lần lấy ra phần tử **nhỏ nhất** trong tập hiện có”, bất kể phần tử đó được thêm lúc nào. Dùng `MinMaxStack.pop()` có đúng yêu cầu không?

**Đáp án:** Không. `MinMaxStack.pop()` vẫn lấy phần tử thêm cuối cùng. `get_min()` chỉ cho biết giá trị cực tiểu, không xóa phần tử đó. Hãy xem xét cấu trúc ưu tiên/heap khi thứ tự lấy phải dựa trên độ ưu tiên.

### Bài 7. Kiểm thử các thao tác biên

Dùng lớp `MinMaxStack` ở phần 5 và dự đoán đầu ra:

```python
s = MinMaxStack()
s.push(-2)
s.push(-2)
s.push(10)
assert s.get_min() == -2
assert s.get_max() == 10
assert s.pop() == 10
assert s.get_max() == -2
assert s.pop() == -2
assert s.get_min() == -2
assert s.pop() == -2
assert s.is_empty()
```

**Đáp án:** Tất cả câu lệnh `assert` đều đúng. Việc xóa một trong hai số `-2` không làm min đổi; chỉ sau lần pop cuối cùng stack mới rỗng và không còn min/max.

## 13. Những điều cần ghi nhớ

Min–Max Stack mở rộng stack LIFO bằng khả năng trả cực tiểu hoặc cực đại hiện tại trong **`O(1)` thời gian**. Ý tưởng căn bản là lưu **cực trị của từng tiền tố** cùng phần tử: khi `push`, cập nhật từ cực trị cũ và giá trị mới; khi `pop`, chỉ cần bỏ bản ghi đỉnh, để lộ cực trị đã lưu cho tiền tố còn lại.

Cách lưu bộ ba `(value, min, max)` dễ hiểu, xử lý tốt giá trị trùng và giữ các thao tác `O(1)` trung bình phân bổ trong cài đặt mảng động, với **`O(n)` bộ nhớ bổ sung**. Có thể thay bằng stack phụ hoặc chỉ lưu các mốc cực trị có bộ đếm nếu muốn giảm chi phí phụ trong một số dữ liệu.

Khi áp dụng thực tế, cần quy định hành vi stack rỗng, bảo đảm các giá trị so sánh được và không tự thay đổi sau khi lưu, đồng thời phân biệt **truy vấn cực trị** với **lấy phần tử theo độ ưu tiên**. Những điều đó quyết định tính đúng đắn của bất biến và sự phù hợp của cấu trúc với bài toán.

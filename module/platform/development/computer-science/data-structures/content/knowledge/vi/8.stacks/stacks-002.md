# Ngăn xếp bằng mảng cố định hoặc mảng động

## 1. Từ quy tắc LIFO đến cách lưu trữ trong mảng

**Ngăn xếp (stack)** là kiểu dữ liệu trừu tượng tuân theo **LIFO (Last In, First Out)**: phần tử được đưa vào sau cùng được lấy ra đầu tiên. Các thao tác quan trọng nhất là `push(x)` (thêm phần tử vào đỉnh), `pop()` (lấy và xóa đỉnh) và `peek()` (xem đỉnh mà không xóa). Quy tắc này không phụ thuộc vào việc ta lưu stack bằng mảng, danh sách liên kết hay một cấu trúc khác.

Trong chương **Ngăn xếp** của học phần **Cấu trúc dữ liệu**, hai cách cài đặt bằng mảng thường gặp là:

- **Mảng cố định (fixed-capacity array):** cấp sẵn `capacity` ô chứa; số phần tử không thể vượt quá giới hạn này.
- **Mảng động (dynamic/resizable array):** bắt đầu với một dung lượng và cấp phát mảng mới lớn hơn khi hết chỗ, nhờ đó có thể tăng số phần tử khi cần, trong giới hạn bộ nhớ khả dụng.

Mục tiêu là hiểu **bất biến dữ liệu**, viết đúng các thao tác, tính được chi phí thời gian và bộ nhớ, rồi quyết định cách cài đặt phù hợp với bài toán.

### Vì sao chọn cuối mảng làm đỉnh?

Với mảng `data`, ta đặt **đáy** ở chỉ số `0` và **đỉnh** ở chỉ số `size - 1`, trong đó `size` là số phần tử đang có. Khi đó `push` ghi vào ô tiếp theo và `pop` lấy ô cuối đang sử dụng, nên không phải dịch chuyển các phần tử còn lại.

```text
Mảng có capacity = 6, size = 4

Chỉ số:     0      1      2      3      4       5
          ┌─────┬─────┬─────┬─────┬───────┬───────┐
data:     │  A  │  B  │  C  │  D  │ trống │ trống │
          └─────┴─────┴─────┴─────┴───────┴───────┘
                               ↑
                         top = size - 1 = 3

Đáy: A                                             Đỉnh: D
Thứ tự pop nếu không push thêm: D → C → B → A
```

Nếu đặt đỉnh ở **đầu mảng tuần tự** thì thao tác thêm hoặc xóa đầu thường phải dịch các phần tử khác, tốn `O(n)` thời gian. Đặt đỉnh ở cuối giúp thao tác thông thường đạt `O(1)`.

## 2. Bất biến và hợp đồng thao tác chung

Một cài đặt dùng mảng nên duy trì những bất biến sau:

1. `0 ≤ size ≤ capacity`.
2. Các ô `data[0]` đến `data[size - 1]` là phần tử hợp lệ theo thứ tự **đáy → đỉnh**.
3. Khi `size > 0`, đỉnh là `data[size - 1]`; khi `size = 0`, stack rỗng và không có đỉnh.
4. `push` chỉ bổ sung đỉnh mới; `pop` chỉ xóa đỉnh hiện tại; `peek` không thay đổi stack.
5. Nếu dùng mảng động, sau mọi lần thay đổi dung lượng, thứ tự `data[0..size-1]` phải được bảo toàn.

**`size` khác `capacity`:** stack có thể chứa 3 phần tử nhưng đã cấp 8 ô nhớ. Năm ô chưa sử dụng **không** thuộc nội dung stack. Nếu dữ liệu hợp lệ có thể là `None`, `null` hay số `0`, cũng không được nhận biết ô trống bằng cách so sánh với các giá trị đó; phải dựa vào `size`.

Hợp đồng thao tác thống nhất trong bài:

| Phép toán | Điều kiện | Kết quả |
|---|---|---|
| `push(x)` | Còn dung lượng, hoặc có thể mở rộng mảng | Ghi `x` vào `data[size]` và tăng `size` |
| `pop()` | `size > 0` | Giảm `size` và trả lại phần tử đỉnh cũ |
| `peek()` | `size > 0` | Trả phần tử `data[size - 1]`, không đổi `size` |
| `is_empty()` | Không cần | Trả `size == 0` |
| `size()` | Không cần | Trả số phần tử |
| `capacity()` | Không cần | Trả số ô được cấp phát, là thuộc tính cài đặt |

Trong các ví dụ bên dưới, `pop` hoặc `peek` trên stack rỗng sẽ ném `IndexError` (**underflow**). `push` vào mảng cố định đã đầy sẽ ném `OverflowError` (**overflow**). Đây là lựa chọn API minh họa; một ngôn ngữ hoặc thư viện khác có thể dùng giá trị kết quả hoặc ngoại lệ khác.

## 3. Cài đặt ngăn xếp bằng mảng cố định

Với dung lượng `C` được chọn khi khởi tạo, tạo một mảng gồm `C` ô và một biến `size = 0`. Dung lượng **không đổi trong suốt vòng đời stack**. Cách này phù hợp khi biết trước số phần tử tối đa hoặc cần kiểm soát bộ nhớ đã cấp.

### Mã giả

```text
INIT(C):
    data = ARRAY(C)
    size = 0

PUSH(x):
    if size == C: báo lỗi overflow
    data[size] = x
    size = size + 1

POP():
    if size == 0: báo lỗi underflow
    size = size - 1
    x = data[size]
    xóa tham chiếu cũ ở data[size] nếu cần
    return x

PEEK():
    if size == 0: báo lỗi underflow
    return data[size - 1]
```

**Thứ tự cập nhật là quan trọng:** `push` ghi vào `data[size]` **trước khi** tăng `size`; `pop` giảm `size` **trước khi** lấy `data[size]`. Với mảng đánh chỉ số từ 0, đỉnh đầu tiên sau khi thêm một phần tử là ô `0`. Cách viết này tránh truy cập `data[-1]` hoặc `data[C]` ngoài phạm vi logic.

### Ví dụ Python đầy đủ

```python
class FixedArrayStack:
    def __init__(self, capacity):
        if capacity < 0:
            raise ValueError("capacity phải không âm")
        self._data = [None] * capacity
        self._size = 0

    def push(self, value):
        if self._size == len(self._data):
            raise OverflowError("stack đã đầy")
        self._data[self._size] = value
        self._size += 1

    def pop(self):
        if self._size == 0:
            raise IndexError("pop trên stack rỗng")
        self._size -= 1
        value = self._data[self._size]
        self._data[self._size] = None  # Giải phóng tham chiếu
        return value

    def peek(self):
        if self._size == 0:
            raise IndexError("peek trên stack rỗng")
        return self._data[self._size - 1]

    def is_empty(self):
        return self._size == 0

    def size(self):
        return self._size

    def capacity(self):
        return len(self._data)


stack = FixedArrayStack(3)
stack.push("A")
stack.push("B")
stack.push("C")
print(stack.peek())      # C
print(stack.pop())       # C
print(stack.size())      # 2
print(stack.capacity())  # 3
```

Trong Python, `[None] * capacity` tạo một `list` có sẵn đúng số ô cần dùng. Ví dụ **mô phỏng giao diện mảng cố định** bằng cách không bao giờ gọi `append`, `extend` hoặc thay đổi độ dài `_data`; `list` của Python về bản chất vẫn là một cấu trúc có khả năng thay đổi kích thước.

Đặt `_data[self._size] = None` sau khi `pop` giúp đối tượng cũ có thể được giải phóng nếu không còn tham chiếu nào khác trỏ tới. `None` vẫn có thể là một **giá trị được push hợp lệ**, vì thao tác kiểm tra rỗng dựa trên `_size` chứ không dựa trên giá trị ô mảng.

### Theo dõi chỉ số và trạng thái

Cho `capacity = 3`, `size = 0` ban đầu:

| Thao tác | Giá trị trả về | Nội dung stack (đáy → đỉnh) | `size` | `capacity` |
|---|---|---|---:|---:|
| Khởi tạo | — | `[]` | 0 | 3 |
| `push(4)` | — | `[4]` | 1 | 3 |
| `push(7)` | — | `[4, 7]` | 2 | 3 |
| `peek()` | `7` | `[4, 7]` | 2 | 3 |
| `push(9)` | — | `[4, 7, 9]` | 3 | 3 |
| `push(11)` | Lỗi overflow | `[4, 7, 9]` | 3 | 3 |
| `pop()` | `9` | `[4, 7]` | 2 | 3 |
| `push(11)` | — | `[4, 7, 11]` | 3 | 3 |

Khi `push(11)` thất bại do đầy, **trạng thái stack giữ nguyên**. Khi `pop()` giải phóng một ô, lần `push(11)` tiếp theo sẽ thành công.

### Độ phức tạp của mảng cố định

Giả sử `capacity = C` và `size = n ≤ C`:

- **`push`, `pop`, `peek`, `is_empty`, `size`:** đều `O(1)` thời gian trong mô hình thao tác mảng, vì chỉ kiểm tra điều kiện, gán/đọc một ô và chỉnh biến đếm.
- **Bộ nhớ đã cấp:** `O(C)` cho các ô phần tử và `O(1)` cho biến quản lý, ngay cả khi stack đang rỗng.
- **Bộ nhớ phụ cho một thao tác:** `O(1)`; thao tác không cần sao chép toàn bộ mảng.

Nếu cần tạo một mảng và khởi tạo `C` ô, bước **khởi tạo** như trong Python tốn `O(C)` thời gian và `O(C)` bộ nhớ. Không nên nhầm chi phí khởi tạo với chi phí của mỗi lần `push`.

## 4. Cài đặt ngăn xếp bằng mảng động

Mảng động cũng giữ đỉnh ở `data[size - 1]`, nhưng có thêm cơ chế **thay đổi `capacity`**. Khi mảng đầy, ta thường cấp phát một mảng có dung lượng **gấp đôi**, sao chép các phần tử đang có sang cùng chỉ số, rồi thay thế mảng cũ.

Ví dụ với dung lượng ban đầu bằng `2`:

| Lệnh | Nội dung stack | `size` | `capacity` | Điều xảy ra |
|---|---|---:|---:|---|
| Khởi tạo | `[]` | 0 | 2 | Cấp 2 ô |
| `push(A)` | `[A]` | 1 | 2 | Ghi trực tiếp |
| `push(B)` | `[A, B]` | 2 | 2 | Mảng vừa đầy |
| `push(C)` | `[A, B, C]` | 3 | 4 | Cấp 4 ô, sao chép A và B |
| `push(D)` | `[A, B, C, D]` | 4 | 4 | Ghi trực tiếp |
| `push(E)` | `[A, B, C, D, E]` | 5 | 8 | Cấp 8 ô, sao chép 4 phần tử |

**Bất biến sau khi mở rộng:** các phần tử cũ vẫn ở vị trí `0..size-1`, `size` không đổi trong lúc sao chép, còn `capacity` tăng. Sau đó thao tác `push` mới ghi thêm phần tử ở `data[size]`.

### Thuật toán mở rộng

```text
PUSH(x):
    if size == capacity:
        newCapacity = max(1, capacity * 2)
        newData = ARRAY(newCapacity)
        for i = 0..size-1:
            newData[i] = data[i]
        data = newData
        capacity = newCapacity
    data[size] = x
    size = size + 1
```

Nếu tăng dung lượng **chỉ một ô** mỗi lần đầy, khi đưa `n` phần tử từ stack rỗng, có thể phải sao chép `1 + 2 + ... + (n - 1) = O(n²)` phần tử. Với chiến lược **gấp đôi**, tổng số phần tử được sao chép trong `n` lần push chỉ là một chuỗi hình học `1 + 2 + 4 + ... < 2n`. Nhờ đó tổng thời gian của `n` lần `push` là `O(n)`, tương ứng `O(1)` **trung bình phân bổ (amortized)** cho mỗi lần push.

**Amortized không đồng nghĩa mọi lần gọi đều O(1):** riêng lần `push` gây mở rộng mảng vẫn phải sao chép `n` phần tử và mất `O(n)` thời gian. Đây là điểm cần cân nhắc nếu ứng dụng có giới hạn độ trễ nghiêm ngặt cho từng thao tác.

### Cài đặt Python tự quản lý dung lượng

Đoạn mã này thể hiện rõ cách cấp mảng mới và sao chép phần tử. Chúng ta sử dụng `list` để mô phỏng **bộ đệm mảng có dung lượng được quản lý thủ công**; cách quản lý tương tự ý tưởng mảng động trong nhiều thư viện hệ thống.

```python
class DynamicArrayStack:
    def __init__(self, initial_capacity=2):
        if initial_capacity < 1:
            raise ValueError("initial_capacity phải dương")
        self._minimum = initial_capacity
        self._data = [None] * initial_capacity
        self._size = 0

    def _resize(self, new_capacity):
        new_data = [None] * new_capacity
        for i in range(self._size):
            new_data[i] = self._data[i]
        self._data = new_data

    def push(self, value):
        if self._size == len(self._data):
            self._resize(len(self._data) * 2)
        self._data[self._size] = value
        self._size += 1

    def pop(self):
        if self._size == 0:
            raise IndexError("pop trên stack rỗng")
        self._size -= 1
        value = self._data[self._size]
        self._data[self._size] = None

        # Chỉ thu nhỏ khi còn không quá 1/4 số ô đã cấp.
        current = len(self._data)
        if current > self._minimum and self._size <= current // 4:
            self._resize(max(self._minimum, current // 2))
        return value

    def peek(self):
        if self._size == 0:
            raise IndexError("peek trên stack rỗng")
        return self._data[self._size - 1]

    def is_empty(self):
        return self._size == 0

    def size(self):
        return self._size

    def capacity(self):
        return len(self._data)


stack = DynamicArrayStack(initial_capacity=2)
stack.push(5)
stack.push(8)
stack.push(13)           # Mở rộng từ 2 lên 4 ô
print(stack.capacity())  # 4
print(stack.pop())       # 13
print(stack.pop())       # 8, thu nhỏ từ 4 xuống 2 ô
print(stack.peek())      # 5
print(stack.capacity())  # 2
```

Các điểm cần quan sát:

- `_resize` chỉ sao chép **`_size` phần tử đang dùng**, vì các ô còn lại không thuộc stack.
- `pop` xóa tham chiếu của ô cũ để tránh giữ đối tượng không cần thiết.
- Không thu nhỏ dưới `_minimum` để bảo toàn dung lượng tối thiểu đã chọn.
- Stack giữ nguyên thứ tự **đáy → đỉnh** sau cả khi mở rộng lẫn thu nhỏ.

### Vì sao không thu nhỏ ngay khi thiếu một ô?

Nếu cứ `size < capacity` là thu nhỏ ngay, chuỗi `push`/`pop` gần ngưỡng có thể làm mảng liên tục mở rộng rồi co lại, khiến mỗi thao tác phát sinh sao chép dữ liệu. Một chiến lược ổn định là:

- **Mở rộng:** khi `size == capacity`, tăng `capacity` lên `2 × capacity`.
- **Thu nhỏ:** khi `size ≤ capacity / 4`, giảm dung lượng còn khoảng một nửa (nhưng không thấp hơn dung lượng tối thiểu).

Hai ngưỡng khác nhau tạo khoảng đệm giữa các lần đổi dung lượng. Sau khi giảm còn một nửa, stack thường chỉ dùng tối đa khoảng một nửa số ô mới; nhiều thao tác thêm sẽ được thực hiện trước khi cần mở rộng trở lại.

Một số thư viện thực tế dùng hệ số tăng trưởng, tiêu chí thu nhỏ hoặc chính sách quản lý bộ nhớ khác. Nếu không tự thu nhỏ, `pop` sẽ có `O(1)` thời gian trong trường hợp xấu nhất, nhưng bộ nhớ đã cấp có thể lớn hơn nhiều so với lượng phần tử đang giữ.

## 5. Phân tích thời gian và bộ nhớ

Gọi `n` là số phần tử hiện tại và `C` là số ô đã cấp. Với mảng động, giả sử mở rộng bằng cách nhân đôi và có thể thu nhỏ theo ngưỡng 1/4 như trong ví dụ:

| Thao tác | Mảng cố định | Mảng động |
|---|---|---|
| `push(x)` | `O(1)`; lỗi nếu đầy | `O(1)` amortized; **`O(n)`** khi phải mở rộng |
| `pop()` | `O(1)` | `O(1)` amortized; **`O(n)`** nếu lần đó phải thu nhỏ |
| `peek()` | `O(1)` | `O(1)` |
| `is_empty()`, `size()` | `O(1)` | `O(1)` |
| Bộ nhớ lưu trữ | `O(C)`, `C` cố định | `O(C)`, `C` thay đổi |
| Bộ nhớ phụ khi đổi dung lượng | Không có | Có thể cần `O(n)` tạm thời cho mảng mới |

Ở mảng động gấp đôi dung lượng, số ô được cấp thường tỷ lệ với `n` khi `n` đủ lớn; cách quản lý thu nhỏ ảnh hưởng đến mức bộ nhớ dư được giữ lại. Khi `n = 0`, chương trình vẫn có thể giữ dung lượng tối thiểu thay vì giải phóng toàn bộ.

Việc cấp phát mảng mới có thể **thất bại do hết bộ nhớ**, dù không có giới hạn dung lượng logic như mảng cố định. Trong thời gian mở rộng, bộ nhớ cao điểm có thể gồm cả mảng cũ và mảng mới. Với dữ liệu rất lớn, chi phí sao chép và áp lực bộ nhớ này có thể quan trọng hơn độ phức tạp trung bình phân bổ.

## 6. Chọn mảng cố định hay mảng động?

| Tiêu chí | Mảng cố định | Mảng động |
|---|---|---|
| Số phần tử tối đa | Biết rõ và giới hạn bằng `C` | Có thể tăng theo nhu cầu, tùy bộ nhớ |
| Thời gian từng `push` | `O(1)`, không sao chép khi thêm | Có những lần `O(n)` do mở rộng |
| Sử dụng bộ nhớ | Dự trù `C` ô từ đầu | Dung lượng thay đổi, có bộ nhớ dự phòng |
| Khi dữ liệu tăng ngoài dự kiến | Báo overflow, cần thiết kế cách xử lý | Có thể tiếp tục sau khi cấp phát thêm |
| Tính đơn giản | Dễ cài và chứng minh bất biến | Cần chiến lược tăng/giảm dung lượng |
| Tình huống phù hợp | Hệ thống giới hạn tài nguyên, giới hạn số phần tử rõ ràng | Ứng dụng thông thường, kích thước dữ liệu biến động |

**Ví dụ chọn cấu trúc:**

- Một thiết bị có tối đa 32 lệnh đang chờ xử lý theo LIFO, cần chặn khi vượt ngưỡng: stack mảng cố định với `capacity = 32` giúp xác định trước mức bộ nhớ dùng cho các ô.
- Một chức năng hoàn tác thao tác có số bước thay đổi trong lúc sử dụng: stack mảng động tiện hơn vì không cần dự đoán chính xác số bước ngay từ đầu. Nếu ứng dụng cần giới hạn lịch sử, có thể chủ động đặt giới hạn dù dùng mảng động.
- Một hệ thống có yêu cầu thời gian phản hồi chặt chẽ cho **mọi lần** thêm phần tử cần cân nhắc chi phí cấp phát và sao chép trong mảng động; mảng cố định có giới hạn đã được tính trước có thể phù hợp hơn.

Không thể chỉ dựa vào chữ “động” để kết luận mảng động luôn tốt hơn. Quyết định phụ thuộc vào giới hạn dung lượng, yêu cầu độ trễ, nhu cầu giải phóng bộ nhớ và tính chất tải thực tế.

## 7. Dùng stack mảng động có sẵn trong Python

Trong ứng dụng Python thông thường, có thể dùng `list` trực tiếp làm stack; `append` thêm cuối, `pop` lấy cuối và `[-1]` xem đỉnh:

```python
stack = []
stack.append("đọc tệp")
stack.append("xử lý")
stack.append("lưu kết quả")

print(stack[-1])   # lưu kết quả (peek)
print(stack.pop()) # lưu kết quả (pop)
print(stack)       # ['đọc tệp', 'xử lý']
```

`list` trong Python quản lý việc tăng dung lượng nội bộ nên không cần viết hàm `_resize` cho phần lớn bài toán. Tuy nhiên, phải kiểm tra stack rỗng trước khi dùng `stack[-1]` hoặc `stack.pop()` nếu không muốn phát sinh `IndexError`. Tránh `stack.insert(0, x)` và `stack.pop(0)` vì các cách này thường phải dịch phần tử, làm mất lợi thế thao tác cuối mảng.

## 8. Sai lầm thường gặp và cách tự kiểm tra

1. **Nhầm số phần tử với dung lượng.** `size = 3` và `capacity = 8` không có nghĩa đỉnh nằm ở ô 7. Đỉnh nằm ở ô `size - 1 = 2`.
2. **Sai thứ tự tăng/giảm chỉ số.** Nếu `push` tăng `size` rồi mới ghi vào `data[size]`, vị trí đầu tiên dễ bị bỏ trống. Nếu `pop` đọc `data[size]` trước khi giảm khi stack đang đầy, có thể truy cập ngoài phần tử hợp lệ.
3. **Không kiểm tra đầy/rỗng.** Mảng cố định cần chặn `push` khi `size == capacity`; mọi stack cần xác định hành vi `pop` và `peek` khi `size == 0`.
4. **Quên xóa tham chiếu sau `pop`.** Việc giảm `size` mà vẫn giữ tham chiếu ở ô cũ có thể khiến đối tượng tiếp tục được giữ trong bộ nhớ dù không còn thuộc stack.
5. **Sao chép sai khi mở rộng.** Phải sao chép theo thứ tự cũ, đủ `size` phần tử; đảo ngược thứ tự sẽ làm hỏng hành vi LIFO.
6. **Nhầm `O(1)` amortized với `O(1)` ở mọi lần.** Các lần đổi dung lượng có thể cần `O(n)` thời gian.

### Bài tập tự kiểm tra có đáp án

**Câu 1.** Stack mảng cố định có `capacity = 4`. Ban đầu rỗng; thực hiện `push(2)`, `push(5)`, `pop()`, `push(7)`, `push(9)`, `peek()`. Hãy cho biết `size`, đỉnh và thứ tự từ đáy lên đỉnh.

**Đáp án:** `pop()` trả `5`. Sau các thao tác, stack là `[2, 7, 9]`; `size = 3`, `peek() = 9`. Dung lượng vẫn là `4`.

**Câu 2.** Mảng động bắt đầu với `capacity = 2` và chỉ mở rộng gấp đôi, chưa thu nhỏ. Sau khi thực hiện bảy lần `push` liên tiếp, `size` và `capacity` bằng bao nhiêu?

**Đáp án:** `size = 7`, `capacity = 8`. Các lần mở rộng xảy ra trước lần push thứ 3 (từ 2 lên 4) và trước lần push thứ 5 (từ 4 lên 8).

**Câu 3.** Vì sao `push` vào cuối mảng động có thể đạt `O(1)` amortized dù có những lần tốn `O(n)`?

**Đáp án:** Khi dung lượng tăng theo cấp số nhân, số phần tử phải sao chép qua toàn bộ `n` lần push chỉ là `O(n)`. Phân bổ chi phí sao chép đó cho `n` thao tác thì mỗi thao tác có chi phí trung bình phân bổ `O(1)`.

**Điểm cần ghi nhớ:** Hai cách cài đặt đều giữ bất biến **phần tử ở `data[size - 1]` là đỉnh**, với `push` và `pop` thao tác ở cuối mảng. Mảng cố định ưu tiên giới hạn dung lượng và thời gian thao tác dự đoán được; mảng động linh hoạt hơn nhờ thay đổi dung lượng nhưng phải tính cả chi phí tái cấp phát, sao chép và bộ nhớ dự phòng.

# Tràn, rỗng và lựa chọn chính sách xử lý lỗi

## 1. Hai tình huống biên của ngăn xếp

**Ngăn xếp (stack)** là kiểu dữ liệu trừu tượng hoạt động theo nguyên tắc **LIFO (Last In, First Out)**: phần tử thêm sau cùng sẽ được lấy ra đầu tiên. Các phép toán quen thuộc gồm `push(x)` để đưa `x` lên đỉnh, `pop()` để lấy và xóa phần tử đỉnh, và `peek()` để xem đỉnh mà không xóa.

Khi lập trình cấu trúc dữ liệu, viết đúng các thao tác ở trạng thái bình thường mới là một phần của bài toán. Ta còn phải xác định **điều gì xảy ra khi không thể thực hiện thao tác**:

- **Underflow (lấy từ stack rỗng):** gọi `pop()` hoặc `peek()` khi không có phần tử nào.
- **Overflow (tràn dung lượng):** gọi `push(x)` khi stack bị giới hạn và đã đạt số phần tử tối đa, hoặc không còn tài nguyên để tiếp tục lưu phần tử.

Trong chương **Ngăn xếp** của học phần **Cấu trúc dữ liệu**, việc xử lý hai tình huống này giúp hiểu rõ *bất biến*, *hợp đồng API* và *độ phức tạp thời gian, bộ nhớ*. Cùng một stack có thể chọn cách báo lỗi khác nhau tùy yêu cầu ứng dụng, nhưng hành vi phải **nhất quán và được mô tả rõ**.

### Trạng thái có thể gặp

Với stack dùng mảng, gọi `size` là số phần tử hiện có và `capacity` là dung lượng được cấp:

```text
Stack có capacity = 3, đỉnh ở bên phải

RỖNG                   CHƯA ĐẦY                 ĐẦY
size = 0               size = 2                size = 3

┌───┬───┬───┐           ┌───┬───┬───┐           ┌───┬───┬───┐
│   │   │   │           │ A │ B │   │           │ A │ B │ C │
└───┴───┴───┘           └───┴───┴───┘           └───┴───┴───┘
                            ↑                        ↑
                           top                      top

pop() hoặc peek()      pop()/peek() hợp lệ      push(D) gây overflow
gây underflow           push(C) hợp lệ           nếu không thể mở rộng
```

Một stack rỗng và một stack đầy là **trạng thái hợp lệ** của cấu trúc dữ liệu. Lỗi chỉ xảy ra khi người gọi yêu cầu một thao tác không đáp ứng được *điều kiện tiên quyết* của nó.

| Trạng thái | `push(x)` | `pop()` | `peek()` | `is_empty()` |
|---|---|---|---|---|
| Rỗng (`size = 0`) | Thường hợp lệ nếu còn chỗ | Underflow | Underflow | `true` |
| Có phần tử và chưa đầy | Hợp lệ | Hợp lệ | Hợp lệ | `false` |
| Đầy theo giới hạn (`size = capacity`) | Overflow hoặc áp dụng chính sách đã định | Hợp lệ nếu `size > 0` | Hợp lệ nếu `size > 0` | `false` |

Lưu ý trường hợp đặc biệt `capacity = 0` của stack có giới hạn: stack **vừa rỗng vừa đầy**; không thể `push`, `pop` hoặc `peek` thành công. Vì thế, hai khái niệm rỗng và đầy không nhất thiết loại trừ nhau.

## 2. Underflow: lấy phần tử không tồn tại

Đặc điểm của stack LIFO là **chỉ phần tử đỉnh mới có thể được lấy ra**. Khi `size = 0`, không tồn tại đỉnh để trả về. Nếu một cài đặt mảng đặt `top = size - 1` thì với stack rỗng, giá trị `top = -1` chỉ là dấu hiệu chưa có phần tử, không phải chỉ số của một đỉnh hợp lệ.

Giả sử gọi các lệnh:

```text
Ban đầu:  []
push(5):  [5]
pop():    trả 5, còn []
pop():    underflow, stack vẫn []
peek():   underflow, stack vẫn []
```

Một cài đặt tốt phải định nghĩa chính xác **kết quả của lần gọi thất bại** và giữ bất biến dữ liệu. Nếu `pop()` gặp underflow, nó không được tự ý giảm `size` thành `-1` hoặc thay đổi `top` thành tham chiếu không hợp lệ.

### Dấu hiệu nhận biết underflow

- **Mảng:** `size == 0` hoặc `top == -1`, tùy cách lưu trữ.
- **Danh sách liên kết:** `top is None` nếu dùng nút đầu làm đỉnh.
- **Giao diện trừu tượng:** `is_empty() == true`.

Không thể dùng `value == 0` hay `value is None` để suy ra stack rỗng nếu `0` và `None` cũng có thể được đưa vào như phần tử dữ liệu.

Trong Python, biểu thức `items[-1]` truy cập **phần tử cuối** của danh sách có phần tử; với danh sách rỗng nó ném `IndexError`. Nếu tự xây stack bằng mảng mà bỏ qua kiểm tra rỗng, không nên coi chỉ số `-1` là một cách xác định đỉnh hợp lệ khi `size = 0`.

## 3. Overflow: không thể thêm phần tử

Với stack giới hạn dung lượng `C`, điều kiện trực tiếp để nhận biết đầy là **`size == C`**. Khi ấy `push(x)` chỉ thành công nếu chính sách cho phép nới dung lượng hoặc giải phóng đủ chỗ trước khi thêm.

### Mảng cố định

Một stack mảng cố định cấp trước `C` ô, có bất biến `0 ≤ size ≤ C`. Nếu `size == C`, việc ghi tiếp vào `data[size]` sẽ vượt vùng chứa được cấp phát. Vì vậy phải phát hiện trạng thái đầy **trước khi ghi**.

```text
Stack capacity = 2

push("A")  → ["A"]           size = 1
push("B")  → ["A", "B"]      size = 2
push("C")  → overflow         size = 2, stack vẫn ["A", "B"]
pop()      → trả "B"          size = 1, stack còn ["A"]
push("C")  → ["A", "C"]      size = 2
```

Đối với stack cố định thuần túy, tăng dung lượng vượt `C` sẽ làm mất ý nghĩa của giới hạn được thiết kế trước. Nếu ứng dụng thực sự cần tự mở rộng, nên chọn **stack dùng mảng động** hoặc đổi hợp đồng dung lượng.

### Mảng động và giới hạn tài nguyên

Mảng động có thể tăng dung lượng bằng cách cấp bộ đệm lớn hơn và sao chép phần tử hiện có. Vì thế, việc **mảng hiện tại đầy** chưa nhất thiết là lỗi: đó có thể chỉ là tín hiệu cần mở rộng.

Tuy nhiên, mảng động vẫn có những giới hạn:

1. **Giới hạn nghiệp vụ** do người lập trình đặt, chẳng hạn stack chỉ được lưu tối đa 100 tác vụ.
2. **Giới hạn của thư viện/runtime** về kích thước mảng hoặc số đối tượng.
3. **Bộ nhớ khả dụng**: lần cấp phát để mở rộng có thể thất bại, chẳng hạn sinh `MemoryError` trong Python.

Phải phân biệt **vượt giới hạn logic** với **hết bộ nhớ vật lý**. Ở trường hợp đầu, API có thể báo `OverflowError` hoặc từ chối theo chính sách. Ở trường hợp sau, ứng dụng có thể nhận lỗi cấp phát; không thể mặc định rằng việc thử lại `push` sẽ thành công.

### Stack ADT và call stack là hai khái niệm khác nhau

Lỗi tràn do đệ quy quá sâu thường được gọi là **stack overflow của ngăn xếp lời gọi hàm (call stack)**, nhưng đây **không phải** lần `push` thông thường vào một đối tượng stack do lập trình viên tạo.

- **ADT stack:** ta kiểm soát các thao tác `push`/`pop` và, nếu có, giới hạn dung lượng của cấu trúc.
- **Call stack:** runtime quản lý khung ngăn xếp cho những lời gọi hàm. Trong Python, đệ quy vượt giới hạn thường sinh `RecursionError`; trong một số ngôn ngữ hoặc môi trường khác có thể gặp lỗi stack overflow.

Đừng sửa lỗi đệ quy sâu bằng cách chỉ tăng `capacity` của một stack dữ liệu không liên quan. Một giải pháp thuật toán có thể là chuyển từ đệ quy sang duyệt dùng stack tường minh, nếu điều đó phù hợp.

## 4. Bất biến cần giữ khi thao tác thất bại

**Bất biến (invariant)** là điều kiện phải đúng sau mỗi thao tác công khai:

- `size ≥ 0`.
- Với stack giới hạn `C`: `size ≤ C`.
- Nếu `size > 0`, đỉnh trỏ tới phần tử được thêm gần nhất nhưng chưa được lấy ra.
- Thứ tự của các phần tử còn trong stack phản ánh đúng LIFO.

Với chính sách **từ chối thao tác khi không đủ điều kiện**, ta có thể yêu cầu:

> `push(x)` bị từ chối do đầy và `pop()`/`peek()` bị từ chối do rỗng phải giữ nguyên toàn bộ nội dung và thứ tự phần tử của stack.

Đây là nguyên tắc hữu ích để thiết kế và kiểm thử. Chẳng hạn:

| Thao tác | Điều kiện | Trạng thái trước | Kết quả | Trạng thái sau |
|---|---|---|---|---|
| `push(3)` | Còn chỗ | `[1, 2]` | Thành công | `[1, 2, 3]` |
| `push(4)` | Đã đầy với `C = 3` | `[1, 2, 3]` | Từ chối | `[1, 2, 3]` |
| `pop()` | Không rỗng | `[1, 2, 3]` | Trả `3` | `[1, 2]` |
| `pop()` | Rỗng | `[]` | Từ chối | `[]` |
| `peek()` | Rỗng | `[]` | Từ chối | `[]` |

Nếu chọn **ghi đè** hoặc **loại bỏ phần tử** khi đầy, trạng thái sau thao tác sẽ khác. Những chính sách đó phải được thiết kế như một hợp đồng riêng và đánh giá xem có còn phù hợp với ngữ nghĩa stack mong muốn hay không.

## 5. Những chính sách xử lý lỗi thường dùng

Không có một cách báo lỗi phù hợp với mọi ứng dụng. Việc lựa chọn phụ thuộc vào câu hỏi: *Tình huống này là lỗi lập trình, kết quả bình thường của nghiệp vụ, hay một trạng thái tài nguyên mà chương trình phải chủ động xử lý?*

| Chính sách | Hành vi | Ưu điểm | Điều cần cân nhắc |
|---|---|---|---|
| **Ném ngoại lệ** | `pop`/`peek` rỗng hoặc `push` đầy ném lỗi | Không thể lặng lẽ bỏ qua; phù hợp trường hợp đáng lẽ không xảy ra | Người gọi cần bắt đúng ngoại lệ khi phục hồi |
| **Trả trạng thái + dữ liệu** | Ví dụ `try_pop() → (success, value)` | Tình huống rỗng/đầy có thể xử lý như một nhánh bình thường | API và mã gọi cần kiểm tra `success` |
| **Trả kiểu tùy chọn (Option/Optional)** | Thành công trả phần tử, rỗng trả trạng thái `None`/`Empty` được biểu diễn tường minh | Thể hiện việc có/không có kết quả ở cấp kiểu dữ liệu | Phải tránh nhập nhằng nếu bản thân giá trị được lưu cũng có thể là `null` |
| **Chặn và chờ** | Với cấu trúc đồng thời có giới hạn, `push` chờ đến khi có chỗ hoặc hết thời hạn chờ | Điều tiết tốc độ giữa bên tạo và bên tiêu thụ | Có thể treo mãi hoặc deadlock nếu không ai tạo chỗ; cần timeout/hủy |
| **Từ chối phần tử mới** | Không thêm `x` khi đầy, trả trạng thái thất bại | Giữ nguyên dữ liệu cũ và bất biến LIFO | Bên gọi phải quyết định lưu lại, báo lỗi hay bỏ yêu cầu |
| **Loại bỏ/ghi đè dữ liệu cũ** | Loại phần tử đang có để nhường chỗ | Giữ dung lượng không vượt ngưỡng | Mất dữ liệu; thay đổi ngữ nghĩa và cần xác định rõ phần tử nào bị loại |

Chính sách “bỏ phần tử cũ nhất khi đầy” không phải là thao tác `push` chuẩn của một stack thuần LIFO. Nó có thể cần tìm đến đáy hoặc sử dụng cấu trúc khác. Nếu ứng dụng thật sự cần cơ chế loại bỏ phần tử cũ nhất (ví dụ bộ đệm sự kiện có giới hạn), hãy mô tả đó là **cấu trúc có chính sách loại bỏ riêng**, tránh gọi nhầm là ngăn xếp LIFO chuẩn.

### Nên chọn chính sách nào?

**Ngoại lệ** thích hợp khi rỗng/đầy là dấu hiệu người gọi đã vi phạm hợp đồng. Ví dụ, thuật toán đánh giá biểu thức đã kiểm tra đủ toán hạng; nếu `pop()` vẫn gặp rỗng thì đây là lỗi logic cần được phát hiện sớm.

**Phương thức `try_*`** phù hợp khi việc không có dữ liệu là bình thường. Ví dụ, một vòng lặp xử lý từng tác vụ có thể gọi `try_pop()`: nếu `success = false` thì kết thúc lượt xử lý mà không cần ném ngoại lệ.

**Giới hạn và từ chối thao tác** phù hợp khi ứng dụng phải kiểm soát tài nguyên. Có thể báo cho người dùng “đã đạt số bước hoàn tác tối đa” hoặc buộc họ xử lý công việc cũ trước khi thêm việc mới.

**Chờ có giới hạn thời gian** chỉ phù hợp với stack hoặc bộ đệm có cơ chế đồng bộ giữa nhiều luồng. Một stack thông thường không tự có thao tác chờ an toàn; nếu không có luồng khác lấy phần tử ra, chờ sẽ không giải quyết được trạng thái đầy.

## 6. Ví dụ Python: một stack, hai giao diện báo lỗi

Ta cài một **stack mảng cố định** với dung lượng `capacity`. Ngoài `push`/`pop`/`peek` ném ngoại lệ, lớp còn có các phương thức `try_push`, `try_pop` và `try_peek` để trả trạng thái thành công.

```python
class BoundedStack:
    def __init__(self, capacity):
        if not isinstance(capacity, int) or capacity < 0:
            raise ValueError("capacity phải là số nguyên không âm")
        self._items = [None] * capacity
        self._size = 0

    def is_empty(self):
        return self._size == 0

    def is_full(self):
        return self._size == len(self._items)

    def size(self):
        return self._size

    def capacity(self):
        return len(self._items)

    def try_push(self, value):
        if self.is_full():
            return False
        self._items[self._size] = value
        self._size += 1
        return True

    def push(self, value):
        if not self.try_push(value):
            raise OverflowError("stack đã đầy")

    def try_pop(self):
        if self.is_empty():
            return (False, None)

        self._size -= 1
        value = self._items[self._size]
        self._items[self._size] = None  # Bỏ tham chiếu đã lấy
        return (True, value)

    def pop(self):
        success, value = self.try_pop()
        if not success:
            raise IndexError("pop trên stack rỗng")
        return value

    def try_peek(self):
        if self.is_empty():
            return (False, None)
        return (True, self._items[self._size - 1])

    def peek(self):
        success, value = self.try_peek()
        if not success:
            raise IndexError("peek trên stack rỗng")
        return value


s = BoundedStack(2)
print(s.try_pop())     # (False, None)
print(s.try_push(10))  # True
print(s.try_push(None))  # True: None là dữ liệu hợp lệ
print(s.try_push(30))  # False: đầy, không đổi stack
print(s.try_peek())    # (True, None)
print(s.pop())         # None
print(s.pop())         # 10
print(s.is_empty())    # True
```

Ví dụ sử dụng cả hai phong cách báo lỗi:

```python
s = BoundedStack(1)
s.push("A")

try:
    s.push("B")
except OverflowError:
    print("Không còn chỗ để thêm")  # Stack vẫn chứa "A"

print(s.pop())  # A

try:
    print(s.pop())
except IndexError:
    print("Không có phần tử để lấy")  # Stack vẫn rỗng
```

**Vì sao `try_pop()` trả cặp `(success, value)`?** Nếu chỉ trả `None` khi rỗng, ta không thể phân biệt hai trường hợp: stack rỗng và stack chứa một phần tử có giá trị `None`. Cặp trạng thái làm rõ hai tình huống `(False, None)` và `(True, None)`.

Trong lớp này, việc kiểm tra đầy xảy ra **trước khi ghi**; kiểm tra rỗng xảy ra **trước khi giảm biến đếm**. Do đó, các thao tác thất bại vì đầy/rỗng không làm đổi `_size` hoặc những phần tử hiện có. Khi `pop` thành công, ta cũng xóa tham chiếu tại ô vừa giải phóng để đối tượng không bị giữ lại ngoài ý muốn.

Lớp minh họa không có cơ chế khóa và **không được coi là an toàn cho nhiều luồng truy cập đồng thời**.

## 7. Với stack mảng động: giới hạn logic và lỗi cấp phát

Một stack mảng động thường dùng cuối danh sách làm đỉnh. Dung lượng lưu trữ bên trong có thể thay đổi, nhưng ứng dụng vẫn có thể đặt **giới hạn số phần tử**:

```python
class DynamicStackWithLimit:
    def __init__(self, max_size=None):
        if max_size is not None and max_size < 0:
            raise ValueError("max_size phải không âm")
        self._items = []
        self._max_size = max_size

    def push(self, value):
        if self._max_size is not None:
            if len(self._items) >= self._max_size:
                raise OverflowError("đã đạt giới hạn phần tử")
        self._items.append(value)  # Có thể thất bại khi hết bộ nhớ

    def pop(self):
        if not self._items:
            raise IndexError("stack rỗng")
        return self._items.pop()

    def peek(self):
        if not self._items:
            raise IndexError("stack rỗng")
        return self._items[-1]


s = DynamicStackWithLimit(max_size=2)
s.push("A")
s.push("B")
# s.push("C") sẽ gây OverflowError do max_size
print(s.pop())  # B
```

Giới hạn `max_size` kiểm soát **số phần tử logic**, không phải số ô mà `list` đã cấp nội bộ. Nếu `max_size=None`, không có giới hạn nghiệp vụ nhưng vẫn có giới hạn tài nguyên của máy. `append` có thể cần tái cấp phát bộ nhớ; lỗi `MemoryError` nên được phân biệt với lỗi vượt `max_size`. Không nên bắt mọi ngoại lệ rồi trả về như thể `push` đã thành công.

Trong ứng dụng thực tế, còn cần cân nhắc cách ứng xử với lỗi cấp phát: ghi log, giải phóng tài nguyên khác, giảm tải hoặc thông báo tác vụ thất bại. Việc thử lại không kiểm soát sau lỗi hết bộ nhớ có thể làm tình hình tệ hơn.

## 8. Tránh lỗi điều kiện biên và xử lý đồng thời

### Kiểm tra trước khi thao tác

Trong mã đơn luồng, kiểm tra `is_empty()` hoặc `is_full()` có thể làm nhánh điều khiển dễ đọc:

```python
if not s.is_empty():
    value = s.pop()
else:
    print("Stack rỗng")
```

Tuy nhiên, **kiểm tra trước không thay thế kiểm tra bên trong thao tác** nếu API hứa sẽ báo lỗi khi vi phạm điều kiện. Lớp `BoundedStack` vẫn kiểm tra ngay trong `pop` và `push` để bảo vệ bất biến kể cả khi người gọi không kiểm tra.

### Bẫy check-then-act trong chương trình nhiều luồng

Trong môi trường có nhiều luồng, có thể xảy ra trình tự:

```text
Ban đầu stack chứa đúng một phần tử X.

Luồng A: kiểm tra is_empty() → False
Luồng B: pop() lấy X, stack trở thành rỗng
Luồng A: pop() → underflow
```

Như vậy, câu lệnh `if not s.is_empty(): s.pop()` **không bảo đảm an toàn nguyên tử** nếu luồng khác có thể thay đổi stack giữa hai lệnh. Cần dùng thao tác nguyên tử hoặc đồng bộ phù hợp, chẳng hạn một `try_pop` được thực thi **trong vùng khóa bảo vệ chung**.

Ngay cả khi API có tên `try_pop`, điều đó **không tự động khiến nó an toàn đa luồng**. Nếu nhiều luồng cùng dùng chung cấu trúc, phải xác định rõ cơ chế khóa, thứ tự thao tác, quy tắc chờ và khả năng hủy/timeout.

### Đừng che giấu lỗi lập trình

Một số mẫu xử lý cần tránh:

```python
# Không nên: bỏ qua mọi lỗi rồi giả vờ thao tác thành công.
try:
    s.pop()
except Exception:
    pass
```

Cách này có thể che cả lỗi lập trình khác, khiến dữ liệu và luồng xử lý trở nên khó kiểm soát. Nếu underflow là tình huống mong đợi, hãy dùng API `try_pop` hoặc chỉ xử lý đúng ngoại lệ được hợp đồng xác định.

### Giới hạn dung lượng và chính sách mất dữ liệu

Nếu stack đã đầy, ứng dụng cần làm rõ điều kiện thành công:

- **Giữ nguyên:** từ chối phần tử mới, trả lỗi; dữ liệu cũ không bị thay đổi.
- **Lưu ở nơi khác:** chuyển yêu cầu sang bộ nhớ ngoài hoặc cơ chế khác, nếu ứng dụng có thiết kế rõ.
- **Loại bỏ dữ liệu:** chỉ cho phép khi người sử dụng chấp nhận mất dữ liệu và quy tắc loại bỏ được mô tả chính xác.
- **Chờ:** trong kiến trúc có nhiều bên tạo và tiêu thụ, phải quy định timeout/cancel và bảo đảm có bên có thể giải phóng chỗ.

Với lịch sử thao tác để hoàn tác, việc âm thầm xóa một trạng thái cũ có thể khiến người dùng không còn hoàn tác được xa hơn. Với stack biểu diễn lời gọi cần xử lý, bỏ mất phần tử có thể gây mất công việc. Chính sách đầy không chỉ là chuyện kỹ thuật mà còn ảnh hưởng đến kết quả nghiệp vụ.

## 9. Chi phí thời gian, bộ nhớ và cách chọn phương án

Gọi `n` là số phần tử đang lưu, `C` là dung lượng của mảng cố định.

| Cách cài đặt và thao tác | Chi phí thông thường | Giới hạn cần nhớ |
|---|---|---|
| Stack mảng cố định: kiểm tra rỗng/đầy | `O(1)` thời gian | Cần lưu `size` và `capacity` |
| Stack mảng cố định: `push`/`pop`/`peek` | `O(1)` thời gian, `O(1)` bộ nhớ phụ | `push` đầy bị từ chối; cấp `O(C)` bộ nhớ từ đầu |
| Stack mảng động: `push` | `O(1)` thời gian trung bình phân bổ (*amortized*) | Lần mở rộng có thể tốn `O(n)` thời gian và thêm `O(n)` bộ nhớ tạm |
| Stack mảng động: `pop` | `O(1)` thông thường; có thể `O(n)` nếu thu nhỏ mảng bằng sao chép | Phụ thuộc chiến lược cấp phát |
| Stack danh sách liên kết: `push`/`pop`/`peek` tại đầu | `O(1)` trong mô hình chuẩn | Mỗi nút cần thêm liên kết và chi phí cấp phát |
| Trả trạng thái hoặc ném ngoại lệ khi đầy/rỗng | Việc **kiểm tra** điều kiện thường `O(1)` | Chi phí tạo/xử lý ngoại lệ trong runtime không được mô tả đầy đủ chỉ bằng mô hình truy cập cấu trúc |

Khi quyết định chính sách, có thể sử dụng ba câu hỏi:

1. **Rỗng/đầy có phải tình huống bình thường không?** Nếu có, `try_pop`/`try_push` với kết quả có trạng thái thường dễ xử lý. Nếu là vi phạm hợp đồng, ngoại lệ giúp phát hiện lỗi.
2. **Giới hạn số phần tử có xác định được không?** Nếu có, mảng cố định hoặc stack động có `max_size` giúp kiểm soát tài nguyên. Nếu kích thước tăng giảm khó đoán, xem xét mảng động hoặc danh sách liên kết.
3. **Ứng dụng có chấp nhận chờ, từ chối hoặc mất dữ liệu không?** Trả lời câu hỏi này trước khi thiết kế hành vi overflow; mỗi lựa chọn tạo ra kết quả nghiệp vụ khác nhau.

## 10. Kiểm thử các điều kiện biên

Những ca kiểm thử sau nhằm bảo vệ bất biến của stack và xác minh hợp đồng lỗi:

| Ca kiểm thử | Thao tác | Kỳ vọng |
|---|---|---|
| Stack vừa khởi tạo | `pop()` hoặc `peek()` | Báo underflow, không đổi trạng thái |
| Stack rỗng | `try_pop()` | Trả `(False, None)` |
| Stack có một phần tử | `pop()` | Trả phần tử, sau đó rỗng |
| Stack đã đạt giới hạn | `push(x)` | Báo overflow, giữ nguyên nội dung |
| Stack đã đạt giới hạn | `try_push(x)` | Trả `False`, giữ nguyên nội dung |
| Stack đầy rồi `pop` | `push(x)` lần nữa | Thành công nếu giải phóng được một ô |
| Stack chứa `None` | `try_peek()` hoặc `try_pop()` | Trả `(True, None)`, phân biệt với rỗng |
| Stack giới hạn bằng 0 | `try_push(x)` và `try_pop()` | Đều thất bại, `size = 0` |
| Một dãy `push`/`pop` hợp lệ | So thứ tự kết quả | Phần tử vào sau ra trước |
| Stack dùng chung nhiều luồng | Đua giữa kiểm tra và lấy | Không dựa vào hai lệnh rời rạc để bảo đảm nguyên tử |

Khi kiểm tra `BoundedStack` ở phần 6, có thể chạy thêm ví dụ:

```python
s = BoundedStack(1)
assert s.try_pop() == (False, None)
assert s.try_push(None) is True
assert s.try_peek() == (True, None)
assert s.try_push("X") is False
assert s.size() == 1
assert s.try_pop() == (True, None)
assert s.size() == 0

zero = BoundedStack(0)
assert zero.is_empty() and zero.is_full()
assert zero.try_push(5) is False
assert zero.try_pop() == (False, None)
```

Các kiểm tra này chỉ xác nhận một số trường hợp biên tiêu biểu. Với ứng dụng thực tế, cần bổ sung kiểm thử theo hợp đồng được chọn, nhất là nếu có nhiều luồng hoặc chính sách bỏ phần tử khi tràn.

## 11. Câu hỏi tự luyện tập

**Câu 1.** Stack có `capacity = 2`, đang chứa `[4, 7]` (bên phải là đỉnh). Gọi `push(9)` theo chính sách từ chối khi đầy. Nội dung stack là gì? Sau đó `pop()` trả về giá trị nào?

**Đáp án:** `push(9)` bị từ chối, nội dung vẫn là `[4, 7]`. `pop()` tiếp theo trả `7`, để lại `[4]`.

**Câu 2.** Nếu `try_pop()` chỉ trả `None` khi stack rỗng, có vấn đề gì khi cho phép `push(None)`?

**Đáp án:** Không thể phân biệt “stack rỗng” với “lấy thành công giá trị `None`”. Dùng cặp `(success, value)` hoặc một kiểu kết quả có trạng thái riêng.

**Câu 3.** Trong một ứng dụng xử lý tác vụ có giới hạn, vì sao không nên tự động “bỏ phần tử ở đáy” khi `push` gặp đầy mà không thông báo cho người gọi?

**Đáp án:** Điều đó làm mất dữ liệu và thay đổi hành vi mong đợi của stack. Nếu ứng dụng yêu cầu bảo toàn tác vụ, việc bỏ phần tử có thể khiến tác vụ không bao giờ được xử lý. Chính sách mất dữ liệu cần được cho phép và công khai.

**Câu 4.** Tại sao `if not stack.is_empty(): stack.pop()` có thể vẫn gặp underflow trong hệ thống nhiều luồng?

**Đáp án:** Một luồng khác có thể lấy phần tử cuối giữa lần kiểm tra và lần `pop`. Cần khóa hoặc thao tác thử lấy được bảo đảm nguyên tử.

**Câu 5.** Một stack mảng động đã cấp đủ `8` ô và chứa `8` phần tử. Gọi `push(9)` có bắt buộc là overflow không?

**Đáp án:** Không. Nếu được phép mở rộng và còn bộ nhớ, stack có thể cấp mảng lớn hơn rồi thêm `9`. Nếu có giới hạn logic `max_size = 8` hoặc không cấp phát được thêm bộ nhớ, thao tác sẽ thất bại theo chính sách tương ứng.

**Ghi nhớ:** **Underflow** xuất hiện khi `pop` hoặc `peek` trên stack rỗng; **overflow** là tình huống không thêm được phần tử vì giới hạn dung lượng hoặc tài nguyên. Hãy kiểm tra điều kiện trước khi thay đổi cấu trúc, định nghĩa kết quả khi thao tác thất bại, và duy trì bất biến **LIFO**. Chọn ngoại lệ, API trả trạng thái, cơ chế chờ hoặc chính sách giới hạn dựa vào yêu cầu của ứng dụng và khả năng chấp nhận mất dữ liệu, độ trễ và chi phí bộ nhớ.

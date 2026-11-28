# Ngăn xếp bằng danh sách liên kết

## 1. Vì sao có thể cài stack bằng danh sách liên kết?

**Ngăn xếp (stack)** là kiểu dữ liệu trừu tượng tuân theo nguyên tắc **LIFO — Last In, First Out**: phần tử thêm sau cùng được lấy ra đầu tiên. Giao diện điển hình của stack có ba thao tác: `push(x)` đưa `x` vào **đỉnh**, `pop()` lấy và loại bỏ phần tử đỉnh, còn `peek()` xem đỉnh mà không làm thay đổi stack.

Trong học phần **Cấu trúc dữ liệu**, stack là ví dụ rõ ràng cho sự khác biệt giữa **quy tắc hoạt động của kiểu dữ liệu trừu tượng** và **cách bố trí phần tử trong bộ nhớ**. Một stack có thể được lưu bằng mảng cố định, mảng động, hoặc **danh sách liên kết (linked list)** mà vẫn giữ quy tắc LIFO. Khi lựa chọn cách cài đặt, cần hiểu bất biến, thao tác, thời gian và bộ nhớ của từng phương án.

Danh sách liên kết gồm nhiều **nút (node)**. Mỗi nút chứa một giá trị và một **liên kết** đến nút kế tiếp. Với **danh sách liên kết đơn (singly linked list)**, nút điển hình có hai trường:

- `value`: dữ liệu do người dùng đưa vào stack.
- `next`: tham chiếu/con trỏ tới nút tiếp theo, hoặc `None`/`null` khi không có nút tiếp theo.

Không cần cấp sẵn một mảng chứa toàn bộ phần tử. Mỗi lần `push` có thể tạo một nút mới; mỗi lần `pop` loại bỏ một nút khỏi cấu trúc. Vì vậy số lượng nút thường tăng giảm theo số phần tử thực tế.

### Đặt đỉnh ở đầu danh sách

Để `push` và `pop` đều nhanh, ta chọn **nút đầu (head)** làm **đỉnh (top)** của stack. Trường `top` lưu tham chiếu đến nút đầu tiên.

```text
Stack có 3 phần tử theo thứ tự được push: A, B, C

   top
    │
    ▼
  ┌──────┬──────┐      ┌──────┬──────┐      ┌──────┬──────┐
  │  C   │ next ├─────►│  B   │ next ├─────►│  A   │ None │
  └──────┴──────┘      └──────┴──────┘      └──────┴──────┘
     đỉnh                                              đáy

pop() sẽ trả về C; sau đó top trỏ đến nút B.
```

Khi dùng danh sách liên kết đơn, thao tác **chèn vào đầu** và **xóa ở đầu** chỉ cần đổi vài tham chiếu, không phải duyệt danh sách. Đây là lý do vị trí `top = head` phù hợp hơn `top = tail`: nếu chỉ giữ con trỏ tới nút cuối, muốn xóa nút cuối thường phải duyệt từ đầu để tìm nút liền trước, tốn `O(n)` thời gian.

## 2. Trạng thái và bất biến của stack liên kết

Một cài đặt có thể lưu hai trường:

- `top`: nút đỉnh hiện tại, hoặc `None` khi stack rỗng.
- `size`: số nút thuộc stack, khởi đầu bằng `0`.

Nếu muốn cài `size()` bằng `O(1)`, cần duy trì biến đếm `size`. Nếu chỉ lưu `top`, vẫn có thể tính kích thước bằng cách đi theo từng liên kết `next` đến cuối danh sách, nhưng thao tác ấy tốn `O(n)`.

**Những bất biến cần được bảo toàn sau mọi thao tác:**

1. `size ≥ 0`; `size == 0` khi và chỉ khi `top is None`.
2. Nếu stack không rỗng, `top` trỏ đến nút chứa phần tử được `push` gần đây nhất mà chưa bị `pop`.
3. Đi theo `next` từ `top` sẽ gặp chính xác `size` nút; nút cuối có `next = None`, danh sách không có chu trình.
4. Thứ tự nút từ `top` đến cuối danh sách là thứ tự mà các phần tử sẽ lần lượt được `pop`, nếu không có lần `push` mới.
5. `peek` giữ nguyên `top`, `size` và toàn bộ liên kết.

Nếu thêm lần lượt `A`, `B`, `C`, chuỗi nút từ đỉnh đến đáy là `C → B → A`. Thứ tự giá trị này đối lập với thời điểm thêm, nhưng hoàn toàn đúng theo LIFO.

## 3. Ba thao tác cốt lõi

### 3.1. `push(x)`: chèn một nút vào đầu

Giả sử `top` đang trỏ tới nút `B`:

```text
Trước push(C):       top → [B] → [A] → None

Tạo nút mới:         new = [C] → None
Gán new.next = top:  new = [C] → [B] → [A] → None
Gán top = new:       top → [C] → [B] → [A] → None
```

Mã giả:

```text
PUSH(x):
    newNode = Node(value = x)
    newNode.next = top
    top = newNode
    size = size + 1
```

**Thứ tự gán quan trọng:** phải cho `newNode.next` trỏ đến đỉnh cũ **trước khi** cập nhật `top`. Nếu cập nhật `top` trước mà không lưu đỉnh cũ, có thể làm mất đường dẫn đến các nút đang có.

Với stack rỗng, `top = None`. Nút mới có `next = None` và trở thành cả đỉnh lẫn đáy; không cần nhánh xử lý đặc biệt.

### 3.2. `pop()`: xóa nút đầu và trả giá trị

Giả sử `top → C → B → A → None`. Để lấy `C`, ta lưu nút cũ, dời `top` sang nút thứ hai, giảm `size` rồi trả giá trị:

```text
Trước:     top → [C] → [B] → [A] → None
Sau:       top ───────► [B] → [A] → None
Kết quả:   C
```

Mã giả:

```text
POP():
    if top == None:
        báo lỗi underflow
    oldTop = top
    top = oldTop.next
    size = size - 1
    result = oldTop.value
    giải phóng hoặc bỏ tham chiếu oldTop theo mô hình bộ nhớ
    return result
```

Để tránh làm mất chuỗi liên kết còn lại, cần dời `top` đến `oldTop.next` **trước khi** hủy liên kết hoặc giải phóng nút cũ. Trong ngôn ngữ quản lý bộ nhớ thủ công như C/C++, phải giải phóng nút đã loại bỏ đúng cách. Trong Python/Java, nút không còn tham chiếu có thể được bộ gom rác thu hồi; việc thu hồi cụ thể phụ thuộc runtime.

Nếu chỉ có một nút, `oldTop.next = None`; sau `pop`, `top = None` và `size = 0`, đúng bất biến stack rỗng.

### 3.3. `peek()`: xem đỉnh mà không xóa

```text
PEEK():
    if top == None:
        báo lỗi underflow
    return top.value
```

`peek()` chỉ đọc giá trị ở nút mà `top` đang trỏ tới. Hai lần `peek()` liên tiếp trên cùng một stack không bị thay đổi sẽ trả về cùng một giá trị.

### Khi stack rỗng

Gọi `pop` hoặc `peek` trên stack rỗng là **underflow**. Cần chọn hợp đồng rõ ràng: ném ngoại lệ, trả kiểu kết quả có cờ thành công, hoặc yêu cầu người gọi kiểm tra `is_empty()` trước. Không nên tự ý dùng giá trị `0` hay `None` làm dấu hiệu lỗi nếu đây cũng có thể là dữ liệu hợp lệ.

Khác với mảng cố định, danh sách liên kết không có giới hạn `capacity` được quy định sẵn. Dù vậy, `push` vẫn có thể thất bại khi không cấp phát được nút mới hoặc hệ thống đặt giới hạn bộ nhớ. **Không có dung lượng cố định không có nghĩa bộ nhớ là vô hạn.**

## 4. Cài đặt Python đầy đủ

Ví dụ sau dùng một lớp nút nội bộ `_Node` và một lớp quản lý stack `LinkedStack`. Các thao tác công khai tuân theo LIFO; `size` được cập nhật cùng với các thay đổi liên kết.

```python
class _Node:
    __slots__ = ("value", "next")

    def __init__(self, value, next_node=None):
        self.value = value
        self.next = next_node


class LinkedStack:
    def __init__(self):
        self._top = None
        self._size = 0

    def push(self, value):
        self._top = _Node(value, self._top)
        self._size += 1

    def pop(self):
        if self._top is None:
            raise IndexError("pop trên ngăn xếp rỗng")

        old_top = self._top
        self._top = old_top.next
        self._size -= 1

        value = old_top.value
        old_top.next = None  # Tách nút đã lấy khỏi danh sách
        return value

    def peek(self):
        if self._top is None:
            raise IndexError("peek trên ngăn xếp rỗng")
        return self._top.value

    def is_empty(self):
        return self._top is None

    def size(self):
        return self._size


stack = LinkedStack()
stack.push("A")
stack.push("B")
stack.push("C")

print(stack.peek())      # C
print(stack.size())      # 3
print(stack.pop())       # C
print(stack.pop())       # B
print(stack.peek())      # A
print(stack.is_empty())  # False
print(stack.pop())       # A
print(stack.is_empty())  # True
```

Ở đây, `_top` và `_size` là chi tiết cài đặt; mã sử dụng stack nên gọi các phương thức công khai thay vì tự đổi liên kết. `__slots__` là một tối ưu nhỏ trong Python để giới hạn thuộc tính của mỗi nút; **không cần** tính năng này mới cài được stack liên kết.

Câu lệnh `old_top.next = None` giúp tách hẳn nút bị lấy ra khỏi chuỗi nút còn lại. Trong ví dụ này không có mã nào trả ra nút nội bộ, nên việc tách liên kết không bắt buộc để bảo đảm kết quả LIFO; nó làm trạng thái rõ ràng và tránh giữ liên kết dư trong các biến thể cài đặt có thể lưu tham chiếu tới nút cũ.

Một chi tiết dễ nhầm: `push(None)` vẫn hợp lệ trong ví dụ trên, vì tính rỗng được kiểm tra bằng **`_top is None`**, không dựa vào giá trị `_top.value`. Nút `_Node(None)` là một nút có thật và được tính vào `_size`.

### Tự kiểm tra với một vết thực thi

Giả sử ban đầu stack rỗng; nội dung cột thứ ba được viết theo thứ tự **đỉnh → đáy**, cũng là thứ tự có thể lấy ra tiếp theo:

| Bước | Thao tác | Chuỗi nút sau thao tác | Giá trị trả về | `size` |
|---:|---|---|---|---:|
| 0 | Khởi tạo | `None` | — | 0 |
| 1 | `push(10)` | `10 → None` | — | 1 |
| 2 | `push(20)` | `20 → 10 → None` | — | 2 |
| 3 | `push(30)` | `30 → 20 → 10 → None` | — | 3 |
| 4 | `peek()` | `30 → 20 → 10 → None` | `30` | 3 |
| 5 | `pop()` | `20 → 10 → None` | `30` | 2 |
| 6 | `push(40)` | `40 → 20 → 10 → None` | — | 3 |
| 7 | `pop()` | `20 → 10 → None` | `40` | 2 |
| 8 | `pop()` | `10 → None` | `20` | 1 |
| 9 | `pop()` | `None` | `10` | 0 |
| 10 | `pop()` | `None` | Lỗi underflow | 0 |

Sau bước 4, `peek` không làm thay đổi số nút. Ở bước 6, nút mới `40` được nối ngay trước nút `20`; không cần dịch hoặc sao chép hai nút cũ.

## 5. Giải thích tính đúng đắn qua bất biến

Ta có thể chứng minh ngắn gọn bằng cách xem từng thao tác bảo toàn bất biến:

**Trường hợp ban đầu.** `top = None`, `size = 0` nên stack rỗng và danh sách có đúng 0 nút.

**Sau `push(x)`.** Nút mới chứa `x` trỏ tới đỉnh cũ; đỉnh mới là nút đó. Chuỗi nút cũ còn nguyên thứ tự; số nút tăng đúng một. Vì thế `x` trở thành phần tử được lấy ra đầu tiên, phù hợp LIFO.

**Sau `pop()`.** Ta loại nút đỉnh cũ ra khỏi chuỗi và trả giá trị của nó. Đỉnh mới chính là nút đứng ngay sau đỉnh cũ; số nút giảm đúng một. Phần còn lại vẫn giữ nguyên thứ tự. Nếu trước đó chỉ có một nút, chuỗi chuyển thành rỗng.

**Sau `peek()`.** Không thay đổi nút, liên kết hay `size`; chỉ trả giá trị đỉnh nên bất biến được giữ nguyên.

Từ trạng thái rỗng ban đầu và ba bước trên, sau mọi dãy thao tác hợp lệ, stack vẫn có hành vi LIFO.

## 6. Độ phức tạp thời gian và bộ nhớ

Gọi `n` là số phần tử đang có. Giả sử tạo và giải phóng một nút mất `O(1)` trong mô hình phân tích cấu trúc dữ liệu:

| Thao tác | Thời gian | Bộ nhớ phụ của thao tác | Lý do |
|---|---|---|---|
| `push(x)` | `O(1)` | `O(1)` | Tạo một nút và đổi liên kết ở đầu |
| `pop()` | `O(1)` | `O(1)` | Dời `top` một bước, trả giá trị |
| `peek()` | `O(1)` | `O(1)` | Đọc nút đỉnh |
| `is_empty()` | `O(1)` | `O(1)` | Kiểm tra `top` |
| `size()` nếu có biến đếm | `O(1)` | `O(1)` | Trả về `_size` |
| Đếm số phần tử bằng cách duyệt nếu không lưu `size` | `O(n)` | `O(1)` | Đi qua `n` nút |

**Bộ nhớ toàn stack là `O(n)`**, vì mỗi phần tử cần một nút và một liên kết `next`. Bên cạnh dữ liệu của phần tử, nút còn mang chi phí của con trỏ/tham chiếu, cấp phát và thông tin quản lý đối tượng (tùy ngôn ngữ/runtime). Việc không cần mảng dự phòng có thể tiết kiệm các ô chưa dùng, nhưng mỗi nút có chi phí riêng.

Ưu điểm là **không cần sao chép toàn bộ `n` phần tử khi `push`** như một lần mở rộng mảng động. Trong phân tích thuật toán chuẩn, `push` và `pop` ở đầu danh sách có `O(1)` **trong từng lần gọi**. Trong thực tế, thời gian cấp phát, thu gom rác hoặc giải phóng bộ nhớ có thể thay đổi; vì vậy `O(1)` về số thao tác trên cấu trúc không phải cam kết độ trễ thực tuyệt đối.

### So sánh với stack bằng mảng

| Tiêu chí | Danh sách liên kết đơn (đỉnh ở đầu) | Mảng cố định (đỉnh ở cuối) | Mảng động (đỉnh ở cuối) |
|---|---|---|---|
| `push` | `O(1)`, cấp một nút | `O(1)` nếu chưa đầy | `O(1)` amortized, đôi lúc `O(n)` khi mở rộng |
| `pop` | `O(1)` | `O(1)` | Thường `O(1)`; có thể `O(n)` nếu thư viện thu nhỏ mảng |
| `peek` | `O(1)` | `O(1)` | `O(1)` |
| Giới hạn cố định | Không bắt buộc | Có, bằng dung lượng đã cấp | Không cố định, tùy bộ nhớ |
| Phần bộ nhớ dự phòng | Không có các ô mảng chưa dùng | Có nếu chưa đầy | Có thể có do cấp dư dung lượng |
| Chi phí mỗi phần tử | Dữ liệu và tham chiếu `next` cùng overhead nút | Thường chỉ một ô chứa dữ liệu/tham chiếu | Một ô mảng, cộng phần dung lượng dự phòng |
| Tính liên tục bộ nhớ | Các nút có thể ở nhiều vị trí | Ô mảng liên tiếp | Ô mảng liên tiếp trong mỗi bộ đệm |
| Đặc điểm thực tế | Cấp phát nhiều nút, truy cập bộ nhớ phân tán | Dự trù dung lượng từ đầu | Thường có locality tốt, nhưng đôi lúc phải cấp lại |

**Không nên suy ra stack liên kết luôn nhanh hoặc tiết kiệm bộ nhớ hơn.** Mảng thường thuận lợi cho bộ nhớ đệm CPU vì các ô liên tiếp, và mỗi phần tử không cần một con trỏ `next` riêng. Danh sách liên kết hữu ích khi kích thước khó dự đoán và cần tránh việc sao chép hàng loạt lúc mảng động mở rộng; cái giá là cấp phát riêng lẻ và overhead trên từng nút.

## 7. Ứng dụng: duyệt đồ thị theo chiều sâu với stack liên kết

Một ứng dụng điển hình của stack là **duyệt theo chiều sâu (Depth-First Search, DFS)**. Thay vì gọi hàm đệ quy, ta dùng stack để lưu những đỉnh cần xử lý. Đỉnh vừa được đưa vào stack sẽ được xét trước, thể hiện trực tiếp nguyên tắc LIFO.

Ví dụ với đồ thị mô tả bởi danh sách kề:

```text
       A
      / \
     B   C
     |   |
     D   E
```

Dùng lại lớp `LinkedStack` vừa cài:

```python
def dfs(graph, start):
    pending = LinkedStack()
    pending.push(start)
    discovered = {start}
    result = []

    while not pending.is_empty():
        vertex = pending.pop()
        result.append(vertex)

        # Đảo thứ tự để xét láng giềng xuất hiện sớm hơn trước.
        for neighbor in reversed(graph.get(vertex, [])):
            if neighbor not in discovered:
                discovered.add(neighbor)
                pending.push(neighbor)

    return result


graph = {
    "A": ["B", "C"],
    "B": ["D"],
    "C": ["E"],
    "D": [],
    "E": [],
}

print(dfs(graph, "A"))  # ['A', 'B', 'D', 'C', 'E']
```

Tập `discovered` ngăn mỗi đỉnh bị thêm nhiều lần (và tránh lặp vô hạn khi đồ thị có chu trình). Việc duyệt các láng giềng theo thứ tự đảo ngược trước khi `push` khiến `B` nằm trên `C` và được `pop` trước trong ví dụ này. Thứ tự duyệt cụ thể phụ thuộc vào thứ tự các láng giềng trong danh sách kề và thời điểm đánh dấu đỉnh đã gặp.

Với `V` đỉnh và `E` cạnh được biểu diễn bằng danh sách kề, DFS trên đồ thị hữu hạn dùng `O(V + E)` thời gian; tập đánh dấu và stack dùng `O(V)` bộ nhớ phụ khi mỗi đỉnh chỉ được `push` một lần. Dữ liệu `graph` đã được cung cấp không tính vào bộ nhớ phụ của thuật toán.

Ngoài DFS, stack liên kết còn phù hợp cho mô phỏng lịch sử hoàn tác, quay lui và xử lý cấu trúc lồng nhau như dấu ngoặc. Những ứng dụng này cần lấy lại **trạng thái mới nhất** trước các trạng thái cũ hơn.

## 8. Sai lầm thường gặp

1. **Đặt `top` ở cuối danh sách liên kết đơn mà không có con trỏ về nút trước.** Chèn cuối có thể tối ưu bằng con trỏ `tail`, nhưng xóa cuối vẫn phải tìm nút trước, làm `pop` thành `O(n)`. Cách đơn giản là chọn **đầu danh sách** làm đỉnh.
2. **Cập nhật `top` quá sớm khi `push`.** Nếu không nối nút mới với đỉnh cũ trước, các nút cũ có thể bị mất liên kết.
3. **Giải phóng nút đỉnh trước khi lấy `next`.** Trong ngôn ngữ quản lý bộ nhớ thủ công, truy cập `oldTop.next` sau khi giải phóng nút là lỗi sử dụng bộ nhớ đã giải phóng (*use-after-free*). Phải lưu hoặc cập nhật đỉnh mới trước.
4. **Không cập nhật `size` hoặc cập nhật sai lúc thao tác thất bại.** Khi `pop` trên stack rỗng, trạng thái phải giữ nguyên. Sau `push` thành công thì tăng, sau `pop` thành công thì giảm đúng một.
5. **Dùng giá trị nút để nhận biết stack rỗng.** Một nút có `value = None` vẫn là phần tử hợp lệ. Kiểm tra `top is None`.
6. **Tạo liên kết vòng ngoài ý muốn.** Nếu một nút `next` trỏ lại nút trước đó, phép đếm hoặc duyệt sẽ không kết thúc; bất biến danh sách không chu trình bị phá vỡ.
7. **Đồng nhất độ phức tạp lý thuyết với hiệu năng thực tế.** Stack mảng có thể chạy nhanh hơn trong thực tế nhờ locality dù một số thao tác mảng động có chi phí sao chép hiếm gặp.

## 9. Tự luyện tập có lời giải

**Câu 1.** Một stack liên kết đơn ban đầu rỗng. Thực hiện lần lượt `push(3)`, `push(8)`, `push(5)`, `pop()`, `push(1)`. Hãy vẽ các nút theo thứ tự từ `top` đến đáy và cho biết lần `pop` tiếp theo trả gì.

**Đáp án:** Sau `push(5)`, chuỗi là `5 → 8 → 3 → None`. `pop()` lấy `5`; `push(1)` tạo chuỗi `1 → 8 → 3 → None`. Lần `pop` tiếp theo trả `1`.

**Câu 2.** Khi stack chỉ có một nút `X`, `top` và `size` thay đổi thế nào sau `pop()`?

**Đáp án:** `pop()` trả `X`; `top = None` và `size = 0`. Không cần phân biệt trường hợp này bằng một thuật toán khác nếu mã `pop` đã viết đúng.

**Câu 3.** Vì sao tính `size()` của danh sách liên kết có thể là `O(1)` hoặc `O(n)`?

**Đáp án:** Nếu duy trì biến đếm và cập nhật ở mỗi lần thêm/xóa, chỉ cần trả giá trị biến đếm nên `O(1)`. Nếu không lưu biến đếm, phải đi qua tất cả `n` nút để đếm nên `O(n)`.

**Câu 4.** Khi nào bạn sẽ cân nhắc dùng stack liên kết thay cho stack mảng động?

**Đáp án:** Khi muốn thêm/xóa ở đỉnh mà không có các đợt sao chép phần tử khi mảng đầy, kích thước thay đổi khó dự đoán và chi phí cấp phát nút chấp nhận được. Nếu ưu tiên tận dụng cache và giảm overhead mỗi phần tử, stack dùng mảng động thường là lựa chọn tốt.

**Ghi nhớ:** Với danh sách liên kết đơn, đặt `top` ở **đầu danh sách** để mọi lần `push`, `pop` và `peek` chỉ thao tác trên một số hữu hạn nút, đạt `O(1)` thời gian trong mô hình chuẩn. Một biến `size` giúp truy vấn kích thước `O(1)`, còn chi phí bộ nhớ của `n` nút vẫn là `O(n)`. Cách cài đặt phù hợp phụ thuộc vào tải sử dụng, bộ nhớ và yêu cầu độ trễ của ứng dụng.

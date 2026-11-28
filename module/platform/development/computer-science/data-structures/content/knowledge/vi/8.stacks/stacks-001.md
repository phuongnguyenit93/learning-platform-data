# Kiểu dữ liệu trừu tượng LIFO và các phép `push`, `pop`, `peek`

## 1. Ngăn xếp là gì?

**Ngăn xếp (stack)** là một **kiểu dữ liệu trừu tượng (Abstract Data Type – ADT)** quản lý một dãy phần tử có thứ tự theo nguyên tắc **LIFO (Last In, First Out)**: phần tử được đưa vào **sau cùng** sẽ được lấy ra **đầu tiên**. Vị trí duy nhất dùng để thêm, xem và lấy phần tử trong giao diện stack cơ bản gọi là **đỉnh (top)**.

Hãy hình dung một chồng đĩa: đặt đĩa mới lên trên cùng và muốn lấy đĩa thì lấy từ trên xuống. Một stack cũng hoạt động như vậy. Nếu lần lượt đưa `A`, `B`, `C` vào một stack rỗng, thứ tự lấy ra là `C`, `B`, `A`.

```text
                 ĐỈNH (top)
                      ↓
                   ┌─────┐
                   │  C  │  ← vào sau cùng, ra đầu tiên
                   ├─────┤
                   │  B  │
                   ├─────┤
                   │  A  │  ← vào đầu tiên
                   └─────┘
                     ĐÁY
```

Trong học phần **Cấu trúc dữ liệu**, stack giúp rèn luyện cách mô tả **bất biến**, định nghĩa rõ các **thao tác**, phân tích **độ phức tạp thời gian và bộ nhớ**, rồi lựa chọn cách cài đặt phù hợp. Điểm cốt lõi là *hành vi LIFO* chứ không phải stack nhất thiết phải nằm trong một vùng bộ nhớ liên tục.

## 2. Stack là ADT: quy tắc hoạt động độc lập với cách lưu trữ

ADT mô tả **những thao tác được phép gọi và kết quả mong đợi**, không bắt buộc cấu trúc bộ nhớ bên dưới. Một stack có thể được cài bằng mảng, mảng động hoặc danh sách liên kết mà vẫn tuân theo cùng giao diện.

Với stack `S = [A, B, C]`, ta quy ước **bên phải là đỉnh**. Như vậy `C` là phần tử được phép lấy ra tiếp theo. Quy ước hiển thị này không yêu cầu stack phải cho phép truy cập tùy ý vào `A` hay `B`.

**Các bất biến quan trọng:**

1. Các phần tử có thứ tự từ đáy đến đỉnh; khi thêm phần tử mới, nó trở thành đỉnh.
2. `pop` chỉ loại bỏ phần tử đang ở đỉnh; các phần tử còn lại giữ nguyên thứ tự tương đối.
3. `peek` chỉ đọc đỉnh, không thay đổi nội dung hay số phần tử.
4. Stack rỗng có kích thước bằng `0` và không có phần tử đỉnh.

Do mỗi thao tác thêm và lấy đều thực hiện ở đỉnh, phần tử chưa bị lấy ra được đưa vào gần đây nhất luôn là phần tử sẽ được lấy ra trước. Đó chính là tính chất LIFO.

## 3. Những phép toán cơ bản

| Phép toán | Ý nghĩa | Ảnh hưởng đến stack | Khi stack rỗng |
|---|---|---|---|
| `push(x)` | Đưa `x` lên đỉnh | Kích thước tăng `1` | Hợp lệ nếu còn khả năng lưu trữ |
| `pop()` | Lấy **và xóa** phần tử đỉnh, trả về phần tử đó | Kích thước giảm `1` | Lỗi *underflow* |
| `peek()` (hoặc `top()`) | Trả về phần tử đỉnh **mà không xóa** | Không thay đổi | Lỗi *underflow* hoặc kết quả báo rỗng theo hợp đồng API |
| `isEmpty()` | Kiểm tra stack có rỗng không | Không thay đổi | Trả về `true` |
| `size()` | Cho biết số phần tử hiện có | Không thay đổi | Trả về `0` |

**`push(x)` — thêm vào đỉnh.** Nếu `S = [A, B]` thì sau `push(C)`, `S = [A, B, C]`. Phần tử `C` trở thành đỉnh; không có phần tử nào cũ bị mất.

**`pop()` — lấy và loại bỏ đỉnh.** Nếu `S = [A, B, C]` thì `pop()` trả về `C` và sau đó `S = [A, B]`. Hai lần gọi `pop()` liên tiếp khi chưa có lần `push()` mới sẽ lần lượt lấy `B` rồi `A`.

**`peek()` — xem đỉnh.** Nếu `S = [A, B]`, `peek()` trả về `B` nhưng sau thao tác `S` vẫn là `[A, B]`. Vì thế hai lần gọi `peek()` liên tiếp cho cùng kết quả, trừ khi có thao tác khác xen vào.

### Theo dõi trạng thái từng bước

Giả sử ban đầu stack rỗng và bên phải là đỉnh:

| Bước | Lệnh | Giá trị trả về | Trạng thái sau lệnh (đáy → đỉnh) |
|---:|---|---|---|
| 0 | Khởi tạo | — | `[]` |
| 1 | `push(10)` | — | `[10]` |
| 2 | `push(20)` | — | `[10, 20]` |
| 3 | `peek()` | `20` | `[10, 20]` |
| 4 | `push(30)` | — | `[10, 20, 30]` |
| 5 | `pop()` | `30` | `[10, 20]` |
| 6 | `pop()` | `20` | `[10]` |
| 7 | `peek()` | `10` | `[10]` |
| 8 | `pop()` | `10` | `[]` |
| 9 | `isEmpty()` | `true` | `[]` |

Ở bước 3, `peek()` **không làm mất** `20`; ở bước 5, `pop()` lấy `30`, dù `10` là phần tử được đưa vào sớm nhất.

## 4. Điều gì xảy ra khi stack rỗng hoặc đầy?

**Underflow** xảy ra khi gọi `pop()` hoặc `peek()` mà stack không có phần tử. Thư viện có thể ném ngoại lệ, trả một kiểu kết quả đặc biệt hoặc yêu cầu người gọi tự kiểm tra `isEmpty()`. Hợp đồng API phải xác định rõ cách xử lý. Không nên mặc định trả `0` hay `null` để báo lỗi nếu `0` hoặc `null` cũng có thể là dữ liệu hợp lệ.

**Overflow** có thể xảy ra khi stack được cấp **dung lượng cố định** và gọi `push()` lúc đã đầy. Với mảng động có khả năng mở rộng, thường không đặt giới hạn phần tử cố định; tuy vậy việc cấp phát vẫn có thể thất bại khi hết bộ nhớ.

Ví dụ với stack dung lượng tối đa `2`:

```text
push(A) → [A]
push(B) → [A, B]
push(C) → overflow (nếu không cho mở rộng)
pop()   → trả B; stack còn [A]
pop()   → trả A; stack còn []
pop()   → underflow
```

Kiểm tra rỗng trước khi lấy phần tử là cần thiết nếu ứng dụng không muốn ngoại lệ phát sinh. Tuy nhiên, với mã chạy đồng thời, kiểm tra `isEmpty()` rồi mới `pop()` chưa đủ để đảm bảo an toàn nếu một luồng khác có thể sửa stack ở giữa; khi đó cần cơ chế đồng bộ hoặc API thao tác nguyên tử.

## 5. Cài đặt stack bằng mảng động

Một cách phổ biến là dùng **cuối mảng động làm đỉnh**: thêm cuối mảng cho `push`, xóa cuối mảng cho `pop`, đọc phần tử cuối cho `peek`. Nhờ vậy không phải dời các phần tử còn lại mỗi khi lấy phần tử ở đỉnh.

Ví dụ Python dưới đây đóng gói danh sách bên trong và quy định `pop()`/`peek()` trên stack rỗng sẽ ném `IndexError`:

```python
class Stack:
    def __init__(self):
        self._items = []

    def push(self, value):
        self._items.append(value)

    def pop(self):
        if self.is_empty():
            raise IndexError("pop từ ngăn xếp rỗng")
        return self._items.pop()

    def peek(self):
        if self.is_empty():
            raise IndexError("peek từ ngăn xếp rỗng")
        return self._items[-1]

    def is_empty(self):
        return len(self._items) == 0

    def size(self):
        return len(self._items)


s = Stack()
s.push("A")
s.push("B")
print(s.peek())      # B
print(s.size())      # 2
print(s.pop())       # B
print(s.peek())      # A
print(s.is_empty())  # False
```

Danh sách `_items` là **chi tiết cài đặt**. Mã bên ngoài nên thao tác qua các phương thức công khai thay vì sửa `_items` trực tiếp; điều đó giúp giữ đúng giao diện stack và có thể thay thế cách lưu trữ sau này.

### Độ phức tạp

Gọi `n` là số phần tử hiện tại. Khi dùng mảng động thông thường:

| Phép toán | Thời gian | Giải thích |
|---|---|---|
| `push(x)` | `O(1)` trung bình phân bổ (*amortized*); `O(n)` trong lần phải mở rộng mảng | Thường chỉ gắn phần tử vào cuối; đôi khi phải sao chép phần tử sang vùng nhớ lớn hơn |
| `pop()` | `O(1)` trung bình phân bổ | Xóa phần tử cuối; một số cài đặt có thể thu nhỏ mảng, gây chi phí `O(n)` ở lần riêng lẻ |
| `peek()` | `O(1)` | Truy cập phần tử cuối |
| `isEmpty()`, `size()` | `O(1)` | Đọc số phần tử đang được lưu |

**Bộ nhớ lưu trữ** là `O(n)` cho `n` phần tử, ngoài phần dung lượng dự phòng của mảng động. `peek()` và một lần `pop()` thông thường chỉ dùng `O(1)` bộ nhớ phụ; một lần `push()` buộc tái cấp phát có thể tạm thời cần thêm `O(n)` bộ nhớ khi sao chép dữ liệu.

Có thể cài stack bằng **danh sách liên kết đơn**, dùng nút đầu danh sách làm đỉnh. Khi đó `push`, `pop`, `peek` đều có thể đạt `O(1)` thời gian ở mỗi lần gọi nếu giữ con trỏ đến nút đầu; đổi lại mỗi phần tử phải mang thêm liên kết và cần cấp phát một nút riêng. Vì thế lựa chọn mảng hay danh sách liên kết phụ thuộc vào mẫu thao tác, chi phí bộ nhớ và yêu cầu cấp phát.

> Lưu ý: Xóa phần tử **đầu** của mảng tuần tự rồi dịch các phần tử còn lại thường mất `O(n)` thời gian. Bởi vậy, khi dùng mảng để cài stack, nên đặt đỉnh tại **cuối mảng**.

## 6. Ví dụ ứng dụng: kiểm tra dấu ngoặc hợp lệ

Stack hữu ích khi gặp cấu trúc **lồng nhau**, vì dấu mở gần đây nhất phải được ghép với dấu đóng tiếp theo. Ví dụ, trong chuỗi `"({[]})"`, dấu `[` được mở gần nhất nên phải được đóng bởi `]` trước khi đóng `}` và `)`.

Thuật toán kiểm tra ba loại ngoặc `()`, `[]`, `{}` như sau:

1. Duyệt ký tự từ trái sang phải. Gặp dấu mở, `push` vào stack.
2. Gặp dấu đóng, nếu stack rỗng thì kết luận sai; nếu không, `pop` dấu mở gần nhất và kiểm tra có đúng loại không.
3. Sau khi duyệt hết, chuỗi hợp lệ khi không gặp lỗi và stack đã rỗng.

```python
def balanced_brackets(text):
    stack = Stack()  # Dùng lớp Stack đã định nghĩa ở trên
    pairs = {')': '(', ']': '[', '}': '{'}

    for ch in text:
        if ch in '([{':
            stack.push(ch)
        elif ch in pairs:
            if stack.is_empty() or stack.pop() != pairs[ch]:
                return False

    return stack.is_empty()


print(balanced_brackets("({[]})"))  # True
print(balanced_brackets("([)]"))    # False
print(balanced_brackets("(()"))     # False
```

Với chuỗi dài `m` ký tự, mỗi ký tự được xét một lần và mỗi dấu ngoặc được thêm/lấy tối đa một lần. Do đó **thời gian `O(m)`** và **bộ nhớ phụ `O(m)`** trong trường hợp xấu nhất (toàn dấu mở). Những ký tự không phải dấu ngoặc được bỏ qua trong phiên bản minh họa này.

## 7. Khi nào nên dùng stack?

- **Undo/Redo:** mỗi thao tác có thể được ghi lại để hoàn tác theo thứ tự gần nhất trước; một hệ thống undo/redo thường phối hợp hai stack hoặc cơ chế lịch sử tương đương.
- **Phân tích biểu thức và cú pháp:** dùng stack để kiểm tra ngoặc, chuyển biểu thức trung tố sang hậu tố hoặc đánh giá biểu thức hậu tố.
- **Duyệt đồ thị/cây theo chiều sâu (DFS):** lưu những đỉnh cần thăm tiếp; có thể dùng stack tường minh thay cho ngăn xếp lời gọi đệ quy.
- **Quay lui (backtracking):** lưu các trạng thái cần quay về khi một lựa chọn không còn khả thi.

Stack khác **hàng đợi (queue)** ở chính quy tắc lấy phần tử: stack tuân theo **LIFO** còn queue thường tuân theo **FIFO (First In, First Out)**. Nếu yêu cầu là xử lý yêu cầu theo thứ tự đến trước được phục vụ trước, queue phù hợp hơn; nếu yêu cầu là quay về phần tử hoặc trạng thái gần nhất, stack thường là lựa chọn tự nhiên.

Stack như một **ADT** cũng cần phân biệt với **call stack** của chương trình. Call stack là một ứng dụng cụ thể của nguyên tắc LIFO để quản lý các lời gọi hàm; nó không có nghĩa mọi stack do lập trình viên tạo đều được lưu trực tiếp trong vùng nhớ call stack.

## 8. Ghi nhớ và tự kiểm tra tư duy

Khi đánh giá một lời giải dùng stack, hãy tự đối chiếu ba câu hỏi: **(1)** phần tử nào được lấy ra tiếp theo, **(2)** thao tác có thay đổi đỉnh hoặc kích thước hay không, **(3)** điều gì xảy ra nếu stack rỗng? Với stack `S = [4, 7, 9]` (đỉnh ở bên phải), `peek()` trả `9` và giữ nguyên `S`; `pop()` tiếp theo trả `9` và để lại `[4, 7]`; cuối cùng `push(2)` cho `[4, 7, 2]`.

Điểm cần nắm chắc là `push` thêm ở đỉnh, `pop` lấy **và xóa** đỉnh, còn `peek` chỉ **xem** đỉnh. Các thao tác đều xoay quanh bất biến **LIFO**; mảng động và danh sách liên kết là hai cách hiện thực cùng một hợp đồng dữ liệu.

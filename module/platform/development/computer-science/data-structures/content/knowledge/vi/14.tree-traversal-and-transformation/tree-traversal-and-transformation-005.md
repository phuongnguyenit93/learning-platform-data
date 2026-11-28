# Bộ duyệt lười và trạng thái cần giữ giữa các lần lấy phần tử

Một chương trình cần liệt kê các khóa trong cây tìm kiếm nhị phân có hàng triệu nút, nhưng người dùng chỉ yêu cầu xem **10 khóa đầu tiên**. Nếu trước tiên duyệt hết cây, đưa mọi khóa vào mảng rồi mới lấy 10 khóa, chương trình sẽ làm nhiều công việc và dùng nhiều bộ nhớ không cần thiết. Thay vào đó, một **bộ duyệt lười** (*lazy iterator*) có thể cung cấp từng nút qua những lần gọi `next()`, đồng thời **giữ trạng thái chưa duyệt** để tiếp tục đúng vị trí ở lần gọi sau.

Đây là nội dung của bài **“Bộ duyệt lười và trạng thái cần giữ giữa các lần lấy phần tử”**, thuộc chương **Duyệt và biến đổi cây** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trong module này, việc chọn mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap hay đồ thị cần dựa trên **bất biến, chi phí thời gian và bộ nhớ**. Bài này làm rõ cách dùng **ngăn xếp**, **hàng đợi**, **khung gọi hàm** và **con trỏ nút** để tạo bộ duyệt cây có thể tạm dừng rồi tiếp tục.

Sau bài học, bạn có thể:

- Phân biệt **duyệt háo hức** (*eager traversal*) với **duyệt lười** (*lazy traversal*) và diễn giải ý nghĩa của `yield`, `next`, `hasNext`, `end`.
- Xác định **trạng thái tối thiểu cần nhớ** để tiếp tục duyệt preorder, inorder, postorder và level-order.
- Cài đặt bộ duyệt inorder bằng stack tường minh và generator Python; hiểu nguyên tắc tương đương khi viết lớp iterator trong C++.
- Phân tích **O(n) tổng thời gian**, **O(h) stack DFS** hoặc **O(w) queue BFS**, đồng thời phân biệt chi phí *mỗi lần lấy* với chi phí *cả lượt duyệt*.
- Nhận biết rủi ro khi cây bị chèn/xóa hoặc giải phóng trong lúc còn một bộ duyệt tạm dừng; lựa chọn snapshot, phiên bản bất biến hoặc hợp đồng iterator phù hợp.
- Áp dụng duyệt lười để tìm sớm, lọc phần tử, phân trang và xử lý luồng kết quả có giới hạn bộ nhớ.

## 1. Duyệt lười là gì?

**Duyệt háo hức** tạo toàn bộ kết quả trước khi bên gọi nhận được phần tử đầu tiên. **Duyệt lười** chỉ tạo phần tử tiếp theo khi bên gọi yêu cầu.

Giả sử cây có `n` nút và cần lấy `k` nút đầu tiên (`k` nhỏ hơn `n` rất nhiều):

```text
Eager:
Cây --> duyệt tất cả n nút --> [kết quả n phần tử] --> lấy k phần tử đầu

Lazy:
Cây --> [trạng thái bộ duyệt]
           | next() -> phần tử 1
           | next() -> phần tử 2
           | ...
           | next() -> phần tử k
           + dừng tại đây nếu không cần thêm
```

Nếu bài toán không cần giữ toàn bộ giá trị đã thăm, lazy iterator **không phải tạo danh sách kết quả O(n)**. Tuy nhiên, nó vẫn cần bộ nhớ để ghi nhớ *nơi sẽ tiếp tục*; lượng bộ nhớ đó phụ thuộc loại cây và thứ tự duyệt, không phải tự động O(1).

### 1.1. Lazy không có nghĩa “không tính toán gì trước”

Một bộ duyệt inorder có thể phải đi xuống một **đường con trái dài** để tìm phần tử đầu tiên. Vì vậy lần gọi `next()` đầu có thể duyệt qua `h` liên kết, dù chỉ trả về một giá trị. Một bộ duyệt khác có thể làm phần việc này ngay trong constructor thay vì trong `next()`.

Hợp đồng “lười” thường có ý nghĩa: **không tạo trước toàn bộ dãy kết quả**, và mỗi lần yêu cầu chỉ thực hiện lượng công việc cần thiết để lấy phần tử kế tiếp theo chiến lược đã chọn.

### 1.2. Không nhầm lazy, streaming và asynchronous

- **Lazy**: dữ liệu được sinh theo nhu cầu, ví dụ gọi `next()` mới tiến thêm.
- **Streaming**: có thể xử lý lần lượt mà không lưu toàn bộ kết quả. Một nguồn có thể streaming nhưng chủ động đẩy dữ liệu thay vì chờ gọi `next()`.
- **Asynchronous**: thao tác có thể chờ I/O hoặc sự kiện mà không chặn luồng điều khiển theo mô hình runtime. Generator đồng bộ Python có thể lazy nhưng **không tự là async**.
- **Snapshot**: dữ liệu/phiên bản được cố định để không thay đổi theo nguồn. Lazy iterator thông thường **không tự tạo snapshot**.

Những thuộc tính này có thể kết hợp với nhau, nhưng không tương đương.

### 1.3. Khi nào eager hợp lý hơn?

Eager có thể thích hợp nếu:

- Bên gọi cần truy cập ngẫu nhiên tới tất cả giá trị kết quả.
- Cần sắp xếp/nhóm/tổng hợp toàn bộ dữ liệu trước khi trả lời.
- Cần trả một **snapshot tách khỏi vòng đời cây nguồn**, với ngữ nghĩa sao chép được xác định rõ.
- Kích thước cây nhỏ, việc xây kết quả đơn giản hơn và chi phí chấp nhận được.

Lazy có ích nhất khi **không chắc sẽ tiêu thụ hết**, khi cây lớn, hoặc khi muốn tách trách nhiệm duyệt khỏi trách nhiệm xử lý từng phần tử.

## 2. Hợp đồng `next()`, `hasNext()` và điểm kết thúc

Một bộ duyệt dạng pull có thể được mô hình hóa bằng ba thao tác:

1. **Tạo iterator** tại trạng thái bắt đầu.
2. **Kiểm tra còn phần tử không** bằng `hasNext()` hoặc bằng việc `next()` báo hết.
3. **Lấy phần tử tiếp** bằng `next()`, đồng thời cập nhật trạng thái nội bộ để lần gọi sau không trả lặp.

Ví dụ giao diện tưởng tượng:

```text
it = inorder_iterator(root)

while it.hasNext():
    value = it.next()
    process(value)
```

Hoặc dạng Python:

```python
iterator = iter([10, 20])   # Ví dụ đơn giản minh họa protocol.

print(next(iterator))       # 10
print(next(iterator))       # 20

try:
    print(next(iterator))
except StopIteration:
    print("Đã duyệt hết")
```

Python `for` tự gọi `iter(...)`, lặp `next(...)` và kết thúc khi iterator báo `StopIteration`.

### 2.1. `hasNext()` có được làm thay đổi trạng thái không?

Một hợp đồng phổ biến yêu cầu nhiều lần `hasNext()` liên tiếp **không làm mất phần tử**. Có hai cách thiết kế:

- **Trạng thái đã sẵn sàng**: stack/queue hiện có cho biết còn nút hay không. `hasNext` chỉ kiểm tra metadata.
- **Lookahead/prefetch**: `hasNext` có thể tìm trước và lưu **một phần tử kế tiếp trong buffer nội bộ**, nhưng lần gọi tiếp vẫn phải trả đúng phần tử ấy. Khi đó `hasNext` có thể tốn thời gian, song không được vô tình bỏ qua dữ liệu.

Nếu chọn prefetch, cần giữ thêm ít nhất cờ `has_buffered` và vùng `buffered_value` (hoặc handle đến nút) để hai lần gọi `hasNext` không kéo tiến trình thêm hai bước.

### 2.2. Trạng thái “hết” khác với giá trị dữ liệu rỗng

Nếu nút thật có thể mang `None` hoặc `NULL` làm **payload**, không được lấy chính giá trị đó làm tín hiệu đã hết dữ liệu.

```python
values = iter([None, 7])

print(next(values))   # None: phần tử thật, không phải EOF.
print(next(values))   # 7
```

Giao diện nên tách **có/không có phần tử** khỏi **giá trị phần tử** bằng ngoại lệ, `Optional`/`Result`, hoặc hàm trả trạng thái kèm tham số đầu ra.

### 2.3. Một iterator có thể được duyệt hai lần không?

Một **iterator** thường mang trạng thái tiến trình và **tiêu thụ một chiều**. Một **iterable** là đối tượng có thể tạo iterator mới (trong những API hỗ trợ). Python list là iterable có thể tạo nhiều iterator độc lập; Python generator là iterator riêng đã tiến tới đâu thì tiếp tục từ đó.

```python
values = [1, 2, 3]
first = iter(values)
second = iter(values)

print(next(first))   # 1
print(next(first))   # 2
print(next(second))  # 1: trạng thái độc lập

generator = (x for x in values)
print(list(generator))  # [1, 2, 3]
print(list(generator))  # []: generator đã cạn
```

Đối với cây, API có thể cung cấp `tree.iter_inorder()` để tạo **iterator mới** mỗi lần gọi, thay vì giữ một iterator đã dùng dở làm thuộc tính dùng chung của cây.

## 3. Mẫu cây và các thứ tự duyệt

Xét cây nhị phân:

```text
                  8
                /   \
               3     10
              / \      \
             1   6      14
                / \     /
               4   7   13
```

Đặt `n` là số nút thật, `h` là chiều cao theo số cạnh từ gốc tới lá và `w` là số nút lớn nhất trên một tầng.

| Thứ tự | Quy tắc | Dãy giá trị trên cây mẫu |
| --- | --- | --- |
| **Preorder** | Gốc → Trái → Phải | `8, 3, 1, 6, 4, 7, 10, 14, 13` |
| **Inorder** | Trái → Gốc → Phải | `1, 3, 4, 6, 7, 8, 10, 13, 14` |
| **Postorder** | Trái → Phải → Gốc | `1, 4, 7, 6, 3, 13, 14, 10, 8` |
| **Level-order** | Tầng nông trước, trái → phải | `8, 3, 10, 1, 6, 14, 4, 7, 13` |

Một iterator “cây” chưa đủ thông tin nếu không nói rõ **thứ tự**. Preorder và postorder đều dùng DFS nhưng lưu trạng thái có khác biệt; BFS lại cần queue FIFO.

### 3.1. Định nghĩa lớp nút dùng trong các ví dụ Python

Các ví dụ Python bên dưới dùng chung khai báo và hàm tạo cây sau. Có thể chép hai hàm vào đầu một tệp rồi chạy các ví dụ tiếp theo:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(eq=False)
class Node:
    value: int
    left: Node | None = None
    right: Node | None = None


def sample_tree() -> Node:
    return Node(
        8,
        left=Node(
            3,
            left=Node(1),
            right=Node(6, left=Node(4), right=Node(7)),
        ),
        right=Node(10, right=Node(14, left=Node(13))),
    )
```

`eq=False` giữ định danh đối tượng làm cách so sánh mặc định của lớp, tránh ngầm coi hai nút khác nhau nhưng cùng giá trị/cây con như một. Mỗi nút thuộc **một cây không có chu trình và không dùng chung nút con** trong các ví dụ chính.

## 4. Vì sao duyệt inorder cần ghi nhớ tổ tiên?

Inorder tuân theo **Trái → Gốc → Phải**. Khi đi sâu xuống nhánh trái, bộ duyệt chưa thể “quên” các nút cha: sau khi thăm cây con trái, nó phải quay về chính cha ấy, thăm cha, rồi đi sang cây con phải.

```text
             8
           /   \
          3     10
         / \
        1   6

Đang chuẩn bị trả 1:
  stack (đáy -> đỉnh): [8, 3, 1]

Trả 1:
  stack: [8, 3]
  Lần sau trả 3, rồi mới đi qua nhánh phải 6.
```

**Trạng thái tối thiểu điển hình** cho inorder lặp:

- `current`: nút đang đi xuống một đường chưa được đẩy vào stack.
- `stack`: các nút tổ tiên **đã gặp nhưng chưa xuất**.
- Không cần lưu tất cả nút đã xuất, vì mỗi nút sau khi pop sẽ không được đưa trở lại với cây bất biến.

### 4.1. Pseudocode resumable inorder

```text
STATE:
    current = root
    stack = empty

NEXT_INORDER():
    while current != null:
        stack.push(current)
        current = current.left

    if stack.empty():
        return END

    node = stack.pop()
    current = node.right
    return ITEM(node.value)
```

Ngay trước khi pop, top của stack là nút kế tiếp theo thứ tự inorder: mọi nút nằm bên trái nó đã được xử lý hoặc không tồn tại. Sau khi xuất nút này, ta chuyển sang **cây con phải** của nó và sẽ đi hết đường trái của cây con đó trước lần xuất tiếp.

### 4.2. Vì sao chỉ giữ `current` là không đủ?

Giả sử ta đi đến nút `1` (không có con). Nếu không giữ stack hoặc con trỏ `parent` và thông tin đã đi vào nhánh nào, không biết phải quay lại nút `3` hay `8` sau khi thăm 1.

Một cây có trường `parent` có thể hỗ trợ traversal khác mà không cần stack đầy đủ, nhưng phải giữ **vị trí và hướng di chuyển** để không lặp; loại bỏ stack không có nghĩa trạng thái tự biến mất. Nếu dùng Morris traversal để đạt O(1) bộ nhớ phụ, thuật toán phải **tạm sửa liên kết cây rồi khôi phục**, phát sinh thêm các ràng buộc về quyền ghi, huỷ sớm và đồng thời.

## 5. Python generator inorder: `yield` giữ trạng thái giữa hai lần lấy

Python `yield` biến hàm thành **generator function**. Khi gọi hàm, ta nhận một generator object; thân hàm chưa chạy đến khi có yêu cầu lấy phần tử. Mỗi lần `yield`, generator **tạm dừng** và giữ những biến cục bộ/điểm tiếp tục cần thiết cho lần `next` sau.

### 5.1. Inorder không đệ quy, chỉ giữ stack O(h)

```python
from collections.abc import Iterator


def inorder_nodes(root: Node | None) -> Iterator[Node]:
    """Sinh từng Node theo inorder; không tạo list n phần tử."""
    stack: list[Node] = []
    current = root

    while current is not None or stack:
        while current is not None:
            stack.append(current)
            current = current.left

        current = stack.pop()
        yield current

        # Dòng này chỉ chạy khi bên gọi yêu cầu next() lần sau.
        current = current.right


root = sample_tree()
it = inorder_nodes(root)

print(next(it).value)  # 1
print(next(it).value)  # 3
print(next(it).value)  # 4

# Không duyệt hết những nút còn lại nếu không cần.
```

Tại `yield current`, generator giữ:

- `stack` (các tổ tiên còn cần quay lại),
- `current` (nút vừa được trả ra ở điểm tạm dừng),
- vị trí lệnh đang dừng để biết phải tiếp tục ở `current = current.right`.

Trạng thái đang giữ không phải một mảng kết quả. Với cây sâu `h`, stack có thể chứa O(h) nút. Nút được trả ra là **đối tượng thật trong cây**, không phải bản sao.

### 5.2. Quan sát tiến trình từng lần `next`

Trên cây mẫu:

| Lần `next()` | Nút trả | Trạng thái đáng chú ý |
| --- | --- | --- |
| 1 | 1 | Đã đi xuống đường trái `8 → 3 → 1` |
| 2 | 3 | Quay lại nút cha đang chờ |
| 3 | 4 | Đi từ `3.right = 6` xuống `6.left = 4` |
| 4 | 6 | Quay về 6 sau khi xử lý cây con trái |
| 5 | 7 | Đi tới con phải của 6 |
| 6 | 8 | Quay về gốc sau khi hoàn tất toàn bộ nhánh trái |
| 7 | 10 | Bắt đầu xử lý nhánh phải của gốc |
| 8 | 13 | Đi xuống từ 14 tới con trái 13 |
| 9 | 14 | Kết thúc mọi nút, lần gọi kế tiếp báo `StopIteration` |

Lưu ý: khi `yield` trả một nút, generator thường chưa chạy dòng `current = current.right` ngay sau đó; nó chạy dòng ấy **khi tiếp tục**. Điều này quan trọng khi bạn đặt lệnh log hoặc thao tác có tác dụng phụ ở phía sau `yield`.

### 5.3. Cần giá trị thì sinh giá trị, cần sửa thì sinh nút

```python
def inorder_values(root: Node | None):
    for node in inorder_nodes(root):
        yield node.value


print(list(inorder_values(sample_tree())))
# [1, 3, 4, 6, 7, 8, 10, 13, 14]
```

Cả `inorder_nodes` và `inorder_values` đều **lười**. Nhưng `list(...)` là **bên tiêu thụ háo hức**: nó kéo toàn bộ generator để tạo list đầy đủ, cần O(n) bộ nhớ kết quả.

Nếu trả nút thật, bên gọi có thể sửa `node.value`. Chỉ làm vậy khi hợp đồng cây cho phép; với cây tìm kiếm nhị phân (BST), sửa **khóa** theo cách phá thứ tự có thể làm kết quả duyệt và phép tìm kiếm không còn đúng dù stack còn trỏ đến nút hợp lệ.

### 5.4. Dừng sớm với `itertools.islice`

```python
from itertools import islice

root = sample_tree()
first_three = list(islice(inorder_values(root), 3))
print(first_three)  # [1, 3, 4]
```

Bên gọi chỉ yêu cầu ba giá trị. Bộ duyệt có thể thực hiện công việc chuẩn bị theo các nhánh liên quan, nhưng **không phải duyệt và lưu toàn bộ chín giá trị**. `islice` rất hữu ích cho giới hạn số kết quả; nhưng nếu muốn phân trang sâu theo kiểu “bỏ qua một triệu phần tử”, việc tiến qua iterator tới vị trí trang vẫn có thể tốn thời gian tuyến tính theo số phần tử bị bỏ qua. Lazy không thay thế chỉ mục tìm kiếm.

## 6. Cài đặt một lớp cursor inorder có `has_next` / `next` trong Python

Generator tiện dụng, nhưng đôi khi bạn cần kiểm soát API và kiểm tra trạng thái của iterator một cách tường minh. Lớp dưới đây giữ **stack các nút chưa xuất**. Constructor chuẩn bị đường trái đầu tiên.

```python
class InorderCursor:
    def __init__(self, root: Node | None):
        self._stack: list[Node] = []
        self._push_left(root)

    def _push_left(self, node: Node | None) -> None:
        while node is not None:
            self._stack.append(node)
            node = node.left

    def has_next(self) -> bool:
        return bool(self._stack)

    def next_node(self) -> Node:
        if not self._stack:
            raise StopIteration

        node = self._stack.pop()
        self._push_left(node.right)
        return node


root = sample_tree()
cursor = InorderCursor(root)

print(cursor.has_next())        # True
print(cursor.has_next())        # True: không bỏ mất nút.
print(cursor.next_node().value) # 1
print(cursor.next_node().value) # 3

while cursor.has_next():
    print(cursor.next_node().value, end=" ")
# 4 6 7 8 10 13 14
```

**Khác với generator trước:** sau khi `next_node` trả về, trạng thái `stack` đã được cập nhật cho lần gọi sau. Vì vậy `has_next` chỉ cần kiểm tra `bool(stack)`, không cần chạy thêm thuật toán duyệt.

### 6.1. Bất biến của `InorderCursor`

Tại ranh giới giữa hai lần gọi `next_node`:

1. Stack chứa các nút **chưa xuất**, theo một đường tổ tiên và các cây con phải đã được lên kế hoạch xử lý.
2. **Đỉnh stack là nút inorder kế tiếp**.
3. Những nút đã pop không được đẩy lại.
4. Mọi đường con trái cần đi qua để tìm phần tử tiếp theo đã được đẩy vào stack qua `_push_left`.
5. `has_next() == False` khi và chỉ khi không còn nút nào để xuất trong phạm vi cây bất biến của lượt duyệt.

Bất biến trên dựa vào giả thiết không ai **chèn/xóa/đổi liên kết cây** giữa các lần gọi. Nếu cây bị sửa, các nút trong stack có thể không còn tạo thành lộ trình duyệt đúng, hoặc thậm chí đã hết vòng đời.

### 6.2. Chi phí constructor và từng lần lấy

Nếu chiều cao tính theo số cạnh là `h`:

- Constructor gọi `_push_left(root)`, có thể mất **O(h)** thời gian/bộ nhớ.
- `has_next` kiểm tra stack có rỗng không, **O(1)**.
- Một lần `next_node` có thể đẩy toàn bộ đường trái trong cây con phải, nên **O(h)** trong trường hợp xấu nhất.
- Trên **cả lượt duyệt n nút**, mỗi nút được push đúng một lần và pop đúng một lần, nên tổng công việc **O(n)**; chi phí `next_node` là **O(1) trung bình khấu hao (amortized)** trên cả lượt, không phải O(1) tuyệt đối cho mọi lần.
- Bộ nhớ phụ trợ của cursor **O(h)**, không tính bộ nhớ các nút cây và kết quả do bên gọi tự lưu.

Hai phiên bản generator/cursor khác nhau ở thời điểm thực hiện `_push_left`, nhưng cùng kiểu trạng thái và bậc chi phí cơ bản.

## 7. Preorder lười: stack các nút chờ xử lý

Với preorder (**Gốc → Trái → Phải**), ta có thể dùng stack LIFO giữ các nút **đã phát hiện nhưng chưa xuất**:

1. Ban đầu đẩy gốc nếu tồn tại.
2. Pop nút trên đỉnh, `yield` nút.
3. Đẩy **con phải trước, con trái sau**, để lần pop sau ưu tiên con trái.
4. Tiếp tục đến khi stack rỗng.

```python
from collections.abc import Iterator


def preorder_nodes(root: Node | None) -> Iterator[Node]:
    if root is None:
        return

    stack = [root]

    while stack:
        node = stack.pop()
        yield node

        if node.right is not None:
            stack.append(node.right)
        if node.left is not None:
            stack.append(node.left)


print([node.value for node in preorder_nodes(sample_tree())])
# [8, 3, 1, 6, 4, 7, 10, 14, 13]
```

### 7.1. Trạng thái giữa các lần `yield`

Sau khi `yield node`, biến `node` còn giữ nút vừa xuất, còn `stack` là tập công việc chưa làm. **Các lệnh đẩy con nằm sau `yield`** và chỉ chạy khi bên gọi yêu cầu giá trị tiếp theo.

Điều này có một hệ quả: nếu bên gọi **đổi liên kết `node.left` hoặc `node.right` ngay sau khi nhận nút**, rồi tiếp tục generator, các con được đẩy có thể phản ánh liên kết **mới**, chứ không phải trạng thái cây tại thời điểm node được xuất. Nếu cần cố định các con ở thời điểm thăm, phải đọc/ghi nhận các con **trước `yield`**, hoặc dùng một snapshot của cây. Đây là lựa chọn ngữ nghĩa phải được thiết kế có chủ đích.

Một phiên bản ghi nhận các con trước khi nhường điều khiển:

```python
def preorder_nodes_captured(root: Node | None):
    if root is None:
        return

    stack = [root]
    while stack:
        node = stack.pop()
        right = node.right
        left = node.left

        if right is not None:
            stack.append(right)
        if left is not None:
            stack.append(left)

        yield node
```

Phiên bản `captured` đảm bảo các **liên kết con trực tiếp** đã được lấy cho nút vừa xuất, nhưng **không phải snapshot toàn bộ cây**; các nút đã được enqueue/stack vẫn có thể bị sửa/xóa ở nơi khác.

### 7.2. Bộ nhớ preorder

Một stack preorder theo nhánh sâu giữ các nhánh phải chưa xử lý cùng đường đi đang duyệt; với cây nhị phân, số mục tối đa **O(h)**. Mỗi nút được push và pop một lần, nên tổng thời gian **O(n)** và công việc giữa các lần `yield` có thể O(1) trong phiên bản tường minh này, ngoài chi phí xử lý một nút.

Việc dùng `yield` sau pop ở đây rất khác `inorder`: preorder có thể xuất gốc ngay mà không cần đi tìm nút trái nhất trước.

## 8. Postorder lười: phải nhớ đã xử lý con nào

Postorder theo thứ tự **Trái → Phải → Gốc**. Không thể chỉ lấy nút cha ra rồi lập tức `yield` như preorder: phải **đợi cả hai cây con hoàn tất** trước khi xuất cha.

Có hai cách giữ trạng thái thường gặp:

- Stack các khung `(node, phase)`, ghi rõ đang mở rộng hay sẵn sàng xuất nút.
- Một stack nút kết hợp con trỏ `last_visited` để biết cây con phải đã hoàn tất chưa.

Cách dùng trạng thái/phase dễ lý giải và ít mắc lỗi hơn cho người học.

### 8.1. Stack các khung `(node, ready)`

```python
from collections.abc import Iterator


def postorder_nodes(root: Node | None) -> Iterator[Node]:
    if root is None:
        return

    # ready=False: cần xử lý hai cây con trước.
    # ready=True: hai cây con đã được lên lịch xử lý xong.
    stack: list[tuple[Node, bool]] = [(root, False)]

    while stack:
        node, ready = stack.pop()

        if ready:
            yield node
            continue

        stack.append((node, True))

        if node.right is not None:
            stack.append((node.right, False))
        if node.left is not None:
            stack.append((node.left, False))


print([node.value for node in postorder_nodes(sample_tree())])
# [1, 4, 7, 6, 3, 13, 14, 10, 8]
```

Thứ tự push là:

1. Khung `(node, True)` để nhớ **sau này** phải xuất cha.
2. Khung con phải.
3. Khung con trái.

Do stack là LIFO, **con trái được xử lý trước**, sau đó con phải, cuối cùng mới tới khung `ready=True` của cha.

### 8.2. Bất biến của postorder với phase

Một khung `(node, False)` biểu diễn **công việc chưa mở rộng**. Khung `(node, True)` biểu diễn **công việc xuất nút sau khi đã xử lý các công việc con được đẩy lên phía trên nó**.

Với cây thực sự không thay đổi:

- Không xuất cha trước khi con của cha được xuất.
- Mỗi nút đi qua một khung `False` và một khung `True` đúng một lần.
- Các khung đang chờ tập trung dọc theo các đường đang duyệt, nên dùng **O(h)** stack cho cây nhị phân.
- Mỗi nút tạo số thao tác hằng số: tổng thời gian O(n).

Nếu dùng **hai stack** để tạo postorder bằng cách đảo một thứ tự duyệt, ta cũng có thể đạt O(n) thời gian nhưng stack thứ hai có thể chứa **O(n)** nút. Vì vậy, khi mục tiêu là **lazy với bộ nhớ O(h)**, thiết kế phase trên một stack thường phù hợp hơn.

### 8.3. Tránh nhầm “đã được lên lịch” với “đã xử lý”

`ready=True` không có nghĩa **nó lập tức được xuất khi vừa push**; nó nằm **dưới** các công việc con trong stack. Chỉ khi những công việc con đã bị pop và xử lý xong thì khung cha mới lên đỉnh.

Trong một cây có chu trình hoặc dùng chung cùng một nút qua nhiều nhánh, giả thiết “mỗi nút có đúng một cha” không còn đúng. Mã trên có thể xuất một đối tượng nhiều lần hoặc lặp vô hạn. Cần thuật toán đồ thị với trạng thái thăm/định danh phù hợp nếu đầu vào không thật sự là cây.


## 9. Level-order lười: hàng đợi ghi nhớ những nút đã phát hiện

Duyệt theo tầng (**level-order/BFS**) yêu cầu xử lý các nút độ sâu nhỏ trước, trong mỗi tầng từ trái sang phải. Vì vậy nó cần **queue FIFO** thay vì stack LIFO.

Bộ duyệt lười BFS giữ:

- `queue`: các nút đã được phát hiện nhưng **chưa trả ra**.
- Thứ tự FIFO: nút được enqueue trước sẽ được dequeue trước.
- Nếu cần phân nhóm tầng: thêm `depth` vào mỗi mục, hoặc biến đếm số nút còn lại ở tầng hiện tại.

### 9.1. Generator BFS không lưu trước kết quả

```python
from collections import deque
from collections.abc import Iterator


def levelorder_nodes(root: Node | None) -> Iterator[Node]:
    if root is None:
        return

    queue = deque([root])

    while queue:
        node = queue.popleft()

        # Enqueue trước khi yield để ghi nhận con tại thời điểm này.
        if node.left is not None:
            queue.append(node.left)
        if node.right is not None:
            queue.append(node.right)

        yield node


root = sample_tree()
it = levelorder_nodes(root)

print(next(it).value)  # 8
print(next(it).value)  # 3
print(next(it).value)  # 10
print([node.value for node in it])
# [1, 6, 14, 4, 7, 13]
```

Queue giữ các nút sẽ được xử lý ở lần `next` sau. Ví dụ khi chuẩn bị trả nút 8, generator đưa 3 và 10 vào queue, rồi tạm dừng; khi bên gọi yêu cầu tiếp, nó mới pop 3.

Đặt các thao tác enqueue **trước** `yield` làm rõ rằng các con của **nút vừa trả** đã được đọc trước khi bên gọi có thể thay đổi nó. Cách này không đóng băng những nhánh sâu hơn và không làm iterator an toàn khi các nút đã enqueue bị xóa.

### 9.2. Bất biến của queue BFS

Trước mỗi bước pop:

1. Queue chứa các nút **đã phát hiện nhưng chưa xuất**.
2. Độ sâu của các nút trong queue theo thứ tự **không giảm**.
3. Queue chỉ có thể giữ phần còn lại của một tầng và phần đã phát hiện của **tầng kế tiếp**.
4. Với **cây thật** mỗi nút khác gốc chỉ có một cha, nên được enqueue đúng một lần.
5. Tại ranh giới `yield`, queue đã có đủ con của nút vừa lấy ra theo chính sách ví dụ.

Vì mỗi nút được enqueue và dequeue đúng một lần, thời gian tổng O(n). Nếu `w` là số nút lớn nhất trong một tầng, queue dùng O(w) bộ nhớ phụ trợ theo bậc tiệm cận: có thể giữ phần nút chưa xuất ở tầng d cùng một số nút tầng d+1.

### 9.3. Generator gắn độ sâu để xuất từng cặp

```python
from collections import deque


def levelorder_with_depth(root: Node | None):
    if root is None:
        return

    queue = deque([(root, 0)])

    while queue:
        node, depth = queue.popleft()

        if node.left is not None:
            queue.append((node.left, depth + 1))
        if node.right is not None:
            queue.append((node.right, depth + 1))

        yield node, depth


print([(n.value, d) for n, d in levelorder_with_depth(sample_tree())])
# [(8, 0), (3, 1), (10, 1), (1, 2), (6, 2),
#  (14, 2), (4, 3), (7, 3), (13, 3)]
```

Giữ `depth` trong từng mục queue giúp bên gọi tìm nút ở một độ sâu cụ thể mà không cần tạo danh sách mọi tầng. Mỗi phần tử queue có thêm một số nguyên, nhưng vẫn O(w) bộ nhớ.

### 9.4. Trả từng nhóm tầng có còn là lazy?

Có. Mỗi lần `next` có thể trả **cả một tầng** thay vì một nút:

```python
from collections import deque


def lazy_levels(root: Node | None):
    if root is None:
        return

    queue = deque([root])

    while queue:
        count = len(queue)
        current_level = []

        for _ in range(count):
            node = queue.popleft()
            current_level.append(node.value)

            if node.left is not None:
                queue.append(node.left)
            if node.right is not None:
                queue.append(node.right)

        yield current_level


it = lazy_levels(sample_tree())
print(next(it))  # [8]
print(next(it))  # [3, 10]
print(next(it))  # [1, 6, 14]
print(next(it))  # [4, 7, 13]
```

Mỗi lần lấy **một tầng** có thể tốn thời gian O(số nút tầng hiện tại) và O(số phần tử tầng) để chứa kết quả. Không nên nói “mỗi `next` O(1)” cho generator này. Queue lẫn `current_level` cùng sống trong một bước có tổng dung lượng O(w) cho cây nhị phân chuẩn (ngoài kết quả các tầng cũ mà bên gọi tự giữ).

## 10. Sinh inorder bằng đệ quy và `yield from`

Generator đệ quy là cách diễn đạt rất gần định nghĩa inorder:

```python
from collections.abc import Iterator


def inorder_recursive(root: Node | None) -> Iterator[Node]:
    if root is None:
        return

    yield from inorder_recursive(root.left)
    yield root
    yield from inorder_recursive(root.right)


root = sample_tree()
it = inorder_recursive(root)

print([node.value for node in it])
# [1, 3, 4, 6, 7, 8, 10, 13, 14]
```

`yield from` chuyển tiếp các phần tử do generator của cây con sinh ra. Khi cây con gọi `yield`, không chỉ generator con mà **cả chuỗi generator cha** vẫn cần giữ khung trạng thái để có thể quay lại tiếp tục.

### 10.1. Stack ẩn vẫn là trạng thái cần giữ

Duyệt đệ quy có thể trông ngắn hơn phiên bản stack tường minh, nhưng **không có nghĩa bộ nhớ O(1)**.

- Mỗi lời gọi/generator đang hoạt động trên một đường từ gốc xuống nút hiện tại giữ một khung.
- Độ sâu của chuỗi khung có thể là `h+1` nếu `h` được tính bằng số cạnh.
- Bộ nhớ phụ trợ **O(h+1)**, thường viết O(h) cho chiều cao lớn; tổng thời gian O(n) trên cây không thay đổi.
- Python có giới hạn độ sâu đệ quy và có thể ném `RecursionError` khi cây quá lệch.

Phiên bản **stack tường minh** chịu chi phí lưu stack trong heap Python thay vì dùng chuỗi lời gọi sâu; thường phù hợp hơn khi cây có thể lệch với số tầng rất lớn. Cả hai vẫn là bộ duyệt lười nếu dùng `yield` đúng cách.

### 10.2. Lưu ý về tài nguyên khi generator tạm dừng

Một generator đang dừng ở `yield` có thể giữ **tham chiếu mạnh** tới những nút trong biến cục bộ và stack. Nếu chương trình đã bỏ `root` bên ngoài nhưng vẫn giữ generator, những nút còn reachable qua generator có thể tiếp tục sống trong runtime có GC như Python.

```python
root = sample_tree()
iterator = inorder_nodes(root)

first = next(iterator)
root = None

# iterator và first vẫn có thể giữ tham chiếu tới các nút.
# Đặt root = None không có nghĩa mọi đối tượng cây đã được thu hồi.

iterator.close()  # Kết thúc generator; không dùng iterator để lấy thêm.
```

`close()` cho phép kết thúc generator và thực hiện phần cleanup được thiết kế trong `finally` nếu có. Nó không bảo đảm mọi object lập tức được bộ gom rác thu hồi, vì có thể còn tham chiếu từ biến khác. Với iterator C++ giữ con trỏ mượn, ngược lại, giữ iterator **không** kéo dài vòng đời cây: nếu chủ sở hữu hủy nút, con trỏ trong iterator có thể treo.

## 11. C++: lớp inorder iterator giữ stack giữa các lần gọi

Trong C++, một lớp cursor tường minh có thể bảo đảm `has_next()` **không tiêu thụ** phần tử và `next(int& out)` trả `false` khi hết. Ví dụ này không dùng coroutine và không tạo trước vector kết quả.

### 11.1. Chương trình C++ độc lập

```cpp
#include <iostream>
#include <vector>

struct Node {
    int value;
    const Node *left = nullptr;
    const Node *right = nullptr;
};

class InorderCursor {
private:
    std::vector<const Node *> pending_;

    void push_left(const Node *node) {
        while (node != nullptr) {
            pending_.push_back(node);
            node = node->left;
        }
    }

public:
    explicit InorderCursor(const Node *root) {
        push_left(root);
    }

    bool has_next() const {
        return !pending_.empty();
    }

    bool next(int &out) {
        if (pending_.empty()) {
            return false;
        }

        const Node *node = pending_.back();
        pending_.pop_back();

        out = node->value;
        push_left(node->right);
        return true;
    }
};

int main() {
    Node n1{1};
    Node n4{4};
    Node n7{7};
    Node n6{6, &n4, &n7};
    Node n3{3, &n1, &n6};
    Node n13{13};
    Node n14{14, &n13};
    Node n10{10, nullptr, &n14};
    Node n8{8, &n3, &n10};

    InorderCursor cursor(&n8);

    std::cout << std::boolalpha << cursor.has_next() << "\n";

    int value = 0;
    while (cursor.next(value)) {
        std::cout << value << " ";
    }
    std::cout << "\n";
    // 1 3 4 6 7 8 10 13 14

    InorderCursor empty(nullptr);
    std::cout << empty.has_next() << "\n"; // false
}
```

### 11.2. Giải thích state và an toàn

`pending_` lưu đường đi và các nút còn phải xuất. Khi cursor tạo từ `&n8`, `push_left` sẽ đưa `8, 3, 1` vào stack; lần đầu `next` pop `1` và chuẩn bị phần tiếp theo.

**Hợp đồng vòng đời:** `const Node*` chỉ là con trỏ **không sở hữu**. Các `Node` tại `main` vẫn còn sống trong suốt quá trình cursor được dùng. Nếu cây bị hủy hoặc thay đổi liên kết trong lúc cursor còn tồn tại, việc giữ stack con trỏ không tạo ra bảo đảm an toàn mới.

**Ngoại lệ cấp phát:** `std::vector::push_back` trong `push_left` có thể cấp phát và ném ngoại lệ như `std::bad_alloc`. `next` ở đây có thể đã pop nút và gán `out` trước khi cấp phát mới thất bại. Một API sản xuất cần xác định **exception safety** nếu muốn thao tác `next` thất bại mà không làm thay đổi vị trí iterator; ví dụ chuẩn bị trước trạng thái trong vùng tạm rồi commit khi thành công hoặc quy định trạng thái sau lỗi. Ví dụ trên ưu tiên giải thích đúng thuật toán duyệt.

### 11.3. Chi phí

Với cây có `n` nút và chiều cao `h`:

- Tạo cursor: O(h+1) thời gian và bộ nhớ trong trường hợp xấu nhất để đẩy đường trái.
- `has_next`: O(1) thời gian.
- `next`: có thể O(h+1) một lần khi mở đường trái mới.
- Một lần duyệt trọn vẹn: O(n) tổng push/pop và O(h+1) bộ nhớ stack.

Có thể đặt API trả `const Node*` thay vì `int` nếu cần xem đối tượng, nhưng phải ghi rõ pointer còn hợp lệ đến khi nào và liệu người gọi có được sửa thông tin trong nút không.

## 12. Chi phí của việc “lấy từng phần tử” — phân tích đúng các đơn vị

Một số mô tả đơn giản nói “lazy iterator có `next()` O(1)”. Phát biểu ấy **không đúng cho mọi thuật toán và mọi trường hợp**, nhất là khi một lần `next` cần chuẩn bị nhiều nút trước khi sinh phần tử.

### 12.1. Cần phân biệt bốn phép đo

1. **Thời gian khởi tạo iterator**: có thể O(1) nếu generator chưa chạy, hoặc O(h+1) nếu constructor chuẩn bị đường trái.
2. **Thời gian một lần `next` xấu nhất**: có thể O(h+1) trên inorder/postorder do phải đi sâu qua nhiều nút không phát ra giá trị.
3. **Thời gian trọn lượt**: O(n) với DFS/BFS chuẩn nếu mỗi nút được push/pop/xử lý số lần hằng số.
4. **Bộ nhớ đang sống lúc tạm dừng**: stack O(h+1), queue O(w), chưa tính kết quả đã được bên gọi lưu.

| Bộ duyệt lười | Trạng thái đang giữ | Khởi tạo điển hình | Một lần lấy xấu nhất | Tổng khi duyệt n nút |
| --- | --- | --- | --- | --- |
| Preorder stack | Stack nút chờ | O(1) | O(1) cho nút và tối đa hai con | O(n), bộ nhớ O(h+1) |
| Inorder stack, generator | `current` + stack tổ tiên | O(1) tạo generator, việc đẩy đường trái ở `next` | O(h+1) | O(n), bộ nhớ O(h+1) |
| Inorder cursor chuẩn bị trước | Stack tổ tiên | O(h+1) | O(h+1) | O(n), bộ nhớ O(h+1) |
| Postorder stack/phase | Stack khung chưa xử lý | O(1) | O(h+1) có thể mở rộng nhiều khung | O(n), bộ nhớ O(h+1) |
| BFS queue | Queue FIFO | O(1) | O(1) cho một nút và tối đa hai con | O(n), bộ nhớ O(w) |
| BFS theo tầng | Queue + list tầng hiện tại | O(1) | O(số nút ở tầng) | O(n), bộ nhớ phụ O(w) |
| Đệ quy `yield from` | Chuỗi khung generator | O(1) tạo generator | O(h+1) trong tình huống phải đi sâu | O(n), bộ nhớ O(h+1) |

Các bậc O(1) giả định thao tác stack/deque và truy cập trường nút có chi phí hằng số và không tính xử lý payload tùy ý của người dùng. Phát biểu về O(h+1) nhất quán khi `h=0` cho cây một nút.

### 12.2. Tại sao amortized O(1) cho inorder vẫn đúng?

Mỗi nút:

- Được **đẩy lên stack một lần**.
- Được **lấy ra một lần** khi trở thành phần tử tiếp theo.
- Chỉ cần kiểm tra một số liên kết con với công việc hằng số.

Một lần `next` có thể đẩy O(h) nút, nhưng đó là những nút sẽ không cần đẩy lại ở lần khác. Cộng qua toàn bộ `n` phần tử, số lần push/pop là O(n). Chia đều chi phí cho `n` lần lấy, chi phí khấu hao O(1), **không đảm bảo độ trễ cứng O(1) cho từng lần**.

Nếu ứng dụng yêu cầu giới hạn độ trễ mỗi lần lấy để phục vụ giao diện thời gian thực, bậc amortized chưa đủ; cần đo và/hoặc chọn cấu trúc có bảo đảm worst-case phù hợp.

### 12.3. Tiêu thụ không hết có tiết kiệm công việc không?

Có thể, nhưng phải đọc thuật toán:

- Với preorder, lấy gốc sớm không cần khám phá toàn cây.
- Với inorder, muốn lấy khóa nhỏ nhất của BST phải đi tới nút trái nhất, có thể tốn O(h).
- Với postorder, muốn lấy phần tử đầu có thể phải tìm tới lá trước, tốn O(h).
- Với BFS, lấy `k` phần tử đầu sẽ phát hiện con của những nút đã trả theo quy tắc enqueue; có thể giữ thêm các nút chờ trong queue.

Lazy giúp tránh sinh **toàn bộ kết quả nếu dừng sớm**, nhưng không bảo đảm “yêu cầu k kết quả chỉ tốn O(k)” cho mọi kiểu duyệt và hình dạng cây.

## 13. Tìm sớm, lọc và phân trang trên kết quả duyệt lười

### 13.1. Tìm phần tử thỏa điều kiện rồi ngừng

```python
from itertools import islice


def first_matching(iterator, predicate):
    for node in iterator:
        if predicate(node):
            return node
    return None


root = sample_tree()
found = first_matching(
    inorder_nodes(root),
    lambda node: node.value >= 7,
)

print(found.value if found is not None else None)  # 7
```

Thuật toán dừng khi gặp nút đầu tiên thỏa điều kiện trong thứ tự inorder. Tổng thời gian đến nút tìm được tỷ lệ với **số nút phải đi qua**, có thể O(n) xấu nhất nếu không có nút thỏa hoặc nút phù hợp ở cuối.

Đối với **BST** có khóa sắp xếp hợp lệ, nếu cần “khóa đầu tiên lớn hơn hoặc bằng `x`” thì một thuật toán `lower_bound` có thể đi theo nhánh dựa vào so sánh, với thời gian O(h+1) mà không cần duyệt tuần tự mọi khóa nhỏ hơn x. Sau khi định vị được vị trí đầu, có thể tiếp tục bằng iterator successor nếu API hỗ trợ. **Lazy traversal không thay thế phép tìm kiếm dùng cấu trúc BST**.

### 13.2. Pipeline lọc lười

```python
root = sample_tree()

even_values = (
    node.value
    for node in inorder_nodes(root)
    if node.value % 2 == 0
)

print(list(islice(even_values, 3)))  # [4, 6, 8]
```

Generator expression chỉ tạo các giá trị chẵn theo nhu cầu. Tuy nhiên, để tìm được ba giá trị chẵn, nó phải **kiểm tra** những nút lẻ nằm trước hoặc xen giữa. Nếu rất ít nút phù hợp, một lần lấy kết quả tiếp theo có thể mất rất nhiều thời gian.

### 13.3. Phân trang kiểu offset và kiểu seek

Khi giao diện yêu cầu “trang 1000, mỗi trang 20 phần tử”:

- Cách **offset**: lấy iterator từ đầu, bỏ qua 19.980 phần tử rồi lấy 20 phần tử; thời gian vẫn tỷ lệ với số phần tử bị bỏ qua.
- Cách **seek/cursor theo khóa**: nếu cây là BST và API hỗ trợ tìm phần tử lớn hơn một khóa đã biết, có thể bắt đầu từ vị trí sau khóa cuối của trang trước, giảm nhu cầu quét lại phần đầu.
- Nếu cây có thể thay đổi giữa hai trang, cần xác định chính sách về khóa trùng, phần tử mới và snapshot/phiên bản. Chỉ lưu “đã lấy đến phần tử thứ 20” không đủ bảo đảm không bỏ/lặp dữ liệu nếu thứ tự thay đổi.

**Độ phức tạp không chỉ phụ thuộc iterator**, mà còn phụ thuộc liệu cấu trúc cung cấp phép định vị ngẫu nhiên/`lower_bound` và liệu cây có cân bằng hay không.

### 13.4. Giữ iterator để duyệt tiếp hay tạo iterator mới?

Một iterator còn sống có thể tiếp tục đúng từ vị trí tạm dừng, nhưng cũng giữ các tham chiếu và stack/queue trong bộ nhớ. Với thao tác người dùng gián đoạn lâu, cân nhắc:

- Giữ iterator và cây bất biến cho đến khi hoàn tất.
- Lưu **khóa tiếp tục** và tạo iterator mới từ vị trí tìm được.
- Lưu **phiên bản** dữ liệu rồi từ chối tiếp tục khi phiên bản đổi.
- Lưu snapshot nếu cần một dãy kết quả nhất quán qua nhiều trang.

Cách nào đúng phải xét vòng đời, tần suất cập nhật và mức nhất quán mong muốn.


## 14. Khi cây bị sửa giữa hai lần `next()`

Đây là một trong những điểm khó nhất khi thiết kế **bộ duyệt lười**. Giữa hai lần gọi, bên ngoài có thể thêm nút, xóa nút, quay cây cân bằng hoặc thay khóa. Bộ duyệt đang giữ thông tin về trạng thái trước; ta cần xác định **nó còn được phép tiếp tục không**.

### 14.1. Ba mức nguy cơ cần phân biệt

1. **Vòng đời:** nút đã được lưu trong stack/queue bị hủy. Con trỏ C/C++ tới nút ấy thành dangling; lần truy cập sau có thể gây use-after-free.
2. **Cấu trúc:** các liên kết `left`/`right` bị thay hoặc các nút di chuyển theo cấu trúc cây. Iterator có thể bỏ sót, thăm lặp, thay thứ tự dù nút còn sống.
3. **Bất biến nghiệp vụ:** một nút BST bị sửa khóa làm mất quan hệ trái nhỏ hơn – phải lớn hơn; ngay cả nếu iterator vẫn truy cập nút hợp lệ, thứ tự không còn phản ánh thứ tự BST.

Đừng đánh đồng “không crash” với “duyệt đúng”.

### 14.2. Thí dụ trạng thái có thể trở nên cũ

```text
Ban đầu:
            8
           / \
          3   10
         / \
        1   6

Cursor inorder đã xuất 1.
pending stack có thể còn [8, 3].

Một bên khác xóa nút 3 và hủy vùng nhớ của nút ấy.

Lần next sau:
Cursor cố lấy node 3 từ pending.
=> con trỏ tới vùng đã hủy có thể treo (C/C++).
```

Trong Python có GC, stack giữ tham chiếu mạnh tới `Node(3)` nên đối tượng có thể còn sống **ngay cả khi bị gỡ khỏi cây**. Khi ấy rủi ro không nhất thiết là truy cập vùng đã hủy mà là kết quả không còn phản ánh cây hiện hành.

**Cùng một thay đổi có thể gây lỗi khác nhau tùy ngôn ngữ và chính sách sở hữu.**

### 14.3. Chính sách iterator thường gặp

| Chính sách | Hành vi khi cây bị sửa | Chi phí/đánh đổi |
| --- | --- | --- |
| **Không được sửa khi đang duyệt** | Mọi thay đổi cấu trúc ngoài iterator là vi phạm hợp đồng | Đơn giản, nhưng cần đảm bảo bằng kỷ luật/khóa |
| **Fail-fast** | Phát hiện phiên bản khác, từ chối `next` | Thêm bộ đếm phiên bản; không tự bảo đảm đồng bộ/vòng đời |
| **Snapshot** | Duyệt ảnh chụp ổn định trước thay đổi | Sao chép và giữ thêm dữ liệu, có thể O(n) |
| **Persistent tree** | Iterator gắn với một phiên bản bất biến | Cần structural sharing/ownership thích hợp |
| **Live iterator** | Duyệt cấu trúc đang thay đổi theo hợp đồng riêng | Khó quy định phần tử thêm/xóa sẽ thấy hay bỏ |
| **Iterator với ID ổn định** | Tra lại nút theo ID mỗi lần; xử lý ID bị xóa | Chi phí tra cứu, metadata/generation |

Không nên mặc định bộ duyệt stack tự cài có bảo đảm như iterator của `std::map` trong C++. `std::map` có hợp đồng riêng về độ ổn định iterator khi chèn/xóa; bộ duyệt cây đơn giản giữ stack tổ tiên **không tự có** những bảo đảm ấy.

### 14.4. Fail-fast với phiên bản cấu trúc

Một container có thể lưu `version`, tăng sau mọi thay đổi cấu trúc thành công. Khi tạo cursor, lưu `expected_version`. Trước `next`, kiểm tra:

```text
NEXT():
    if tree is no longer alive:
        error INVALID_OWNER

    if tree.version != expected_version:
        error MODIFIED_DURING_TRAVERSAL

    ...
    trả nút tiếp theo
```

Hai trạng thái **hết dữ liệu** và **bị vô hiệu do sửa cây** phải được phân biệt. Nhưng cần nhớ:

- Chỉ có kiểm tra version chưa bảo đảm việc **lấy con trỏ owner** là an toàn nếu tree đã bị hủy.
- Trong nhiều luồng, đọc `version` rồi đọc nút sau đó vẫn cần đồng bộ phù hợp: luồng khác có thể sửa **sau lúc kiểm tra**.
- Version tăng theo chính sách phải thống nhất trên mọi thao tác sửa; một nhánh quên tăng sẽ tạo lỗ hổng.
- Tràn/quay vòng của bộ đếm phiên bản cần được xét nếu yêu cầu bảo đảm mạnh trong thời gian rất dài.
- Một hệ thống có thể chọn chỉ tăng version khi thay **liên kết**, không tăng khi thay payload; nếu duyệt cần snapshot payload, chính sách ấy là chưa đủ.

### 14.5. Snapshot và bất biến sâu

Nếu cần kết quả là cây tại **một thời điểm**, có thể sao chép cấu trúc cây trước khi tạo iterator, hoặc giữ một phiên bản bất biến. Nhưng **sao chép nông danh sách các con trỏ nút** có thể vẫn dùng chung đối tượng đích, nên không tự trở thành snapshot sâu.

Ở persistent tree, phiên bản mới có thể chia sẻ các **nhánh bất biến** với phiên bản cũ. Iterator tới phiên bản cũ vẫn có thể hợp lệ nếu cơ chế quyền sở hữu giữ mọi nút mà nó cần sống đủ lâu; nhưng nếu nhánh “bất biến” lại bị sửa qua một alias có quyền ghi, ý nghĩa snapshot bị phá.

### 14.6. Có thể sửa payload khi đang duyệt?

Tùy yêu cầu. Ví dụ, preorder generator sinh từng `Node` rồi bên gọi đổi trường `color` để đánh dấu (không đổi `left/right`), thứ tự duyệt có thể vẫn đúng. Tuy nhiên:

- Nếu `value` là **khóa BST**, thay giá trị có thể phá thứ tự.
- Nếu một luồng khác đồng thời đọc cùng trường, phải xét đồng bộ.
- Nếu generator giữ tham chiếu tới payload mutable và ứng dụng muốn ảnh chụp bất biến, vẫn cần copy/phiên bản hóa.

Một hướng thiết kế đơn giản là **tách hai pha**: duyệt và thu thập các ID cần đổi, rồi thực hiện thay đổi sau khi bộ duyệt kết thúc. Điều này dùng thêm bộ nhớ cho danh sách thay đổi, nhưng giảm nguy cơ làm sai lộ trình duyệt.

## 15. Quyền sở hữu, đóng sớm và bộ nhớ bị giữ bởi iterator

Bộ duyệt lười ít tạo dữ liệu đầu ra hơn, nhưng thường phải giữ **một phần cây còn tới được** qua stack, queue và các khung generator.

### 15.1. Iterator Python có thể giữ cây sống lâu hơn mong đợi

```python
root = sample_tree()
it = levelorder_nodes(root)

node = next(it)  # Lấy gốc.
root = None

# 'it' vẫn giữ queue chứa các nút con,
# 'node' vẫn giữ gốc và các liên kết từ gốc.
# Vì vậy các Node chưa chắc đủ điều kiện thu hồi.

it.close()
node = None
```

Một generator Python giữ các biến cục bộ sau khi `yield`. Đối tượng cây có thể tiếp tục sống khi có đường tham chiếu từ `it` hoặc `node`. Khi hết cần, hoàn tất generator hoặc đóng, và bỏ những tham chiếu không còn dùng theo hợp đồng ứng dụng.

**Điểm cần chú ý:** `for ... break` không phải một lời hứa chung rằng một generator còn được giữ trong biến sẽ tự động `close()` ngay lập tức. Nếu generator quản lý file, lock, transaction hoặc tài nguyên khác, có thể cần dùng `try/finally` hay context manager và đảm bảo đóng khi dừng sớm.

### 15.2. Ví dụ cleanup khi dừng sớm

```python
def traced_inorder(root: Node | None):
    print("Bat dau duyet")
    try:
        yield from inorder_nodes(root)
    finally:
        print("Ket thuc hoac dong generator")


it = traced_inorder(sample_tree())

print(next(it).value)  # In thông báo bắt đầu rồi giá trị 1.
it.close()             # Kích hoạt nhánh finally khi đã bắt đầu chạy.
```

Đây là ví dụ về vòng đời generator, không phải yêu cầu mọi thuật toán inorder phải mở tài nguyên. Nếu `finally` có thao tác giải phóng tài nguyên bên ngoài, hợp đồng phải làm rõ ai sở hữu tài nguyên và liệu dừng sớm có được phép hay không.

### 15.3. Iterator C++ mượn nút phải ngắn hơn vòng đời cây

Trong ví dụ C++ ở Mục 11, `pending_` là vector các `const Node*`, **không sở hữu các nút**. Container stack giải phóng vùng lưu các **con trỏ**, không hủy `Node` mà chúng trỏ tới.

Nếu cây nguồn cấp phát động rồi bị giải phóng trước khi cursor tiêu thụ hết, những con trỏ trong `pending_` không còn hợp lệ. Các phương án cần cân nhắc:

- Giữ tree owner sống lâu hơn mọi cursor mượn.
- Dùng owner chia sẻ hoặc snapshot khi có hợp đồng phù hợp.
- Truy cập qua ID/handle có kiểm tra hiệu lực.
- Không trả cursor ra khỏi phạm vi có đảm bảo vòng đời cây.

Không dùng `shared_ptr` tràn lan chỉ để “đỡ phải nghĩ về vòng đời”: chia sẻ quyền sở hữu thêm chi phí metadata và có thể tạo chu trình nếu liên kết cha–con được tổ chức không đúng.

## 16. Bảng chọn kiểu bộ duyệt theo yêu cầu

| Nhu cầu | Thứ tự/phương án phù hợp | Vì sao |
| --- | --- | --- |
| In dãy khóa BST tăng dần | Inorder iterator | Nếu BST đúng bất biến khóa, inorder cho thứ tự không giảm |
| Xử lý gốc trước rồi tới cây con | Preorder iterator | Có thể trả gốc ngay; stack O(h+1) |
| Cần xử lý con trước cha | Postorder iterator | Dùng stack/phase để trì hoãn cha |
| Duyệt những nút gần gốc trước | Level-order iterator | Queue FIFO; O(w) bộ nhớ |
| Lấy 10 giá trị đầu rồi dừng | Lazy iterator + giới hạn | Không cần materialize toàn bộ |
| Đếm/tổng theo tầng | BFS theo tầng | Chụp kích thước queue; có thể yield từng tầng |
| Tìm lá gần gốc nhất | BFS + dừng khi gặp lá | Thứ tự tầng đảm bảo tối thiểu số cạnh |
| Duyệt một phiên bản không đổi | Persistent/snapshot iterator | Cần bảo đảm lifetime, bất biến dữ liệu |
| Duyệt trong khi cây liên tục thay | Iterator có hợp đồng concurrent/live riêng | Không thể dùng stack cursor thường và giả định an toàn |
| Phân trang sâu trên BST | Tìm theo khóa + tiếp tục bằng successor | Tránh duyệt bỏ qua quá nhiều phần tử từ đầu |
| Cây rất lệch trong Python | DFS stack tường minh | Tránh chuỗi đệ quy quá sâu |
| Dữ liệu thực là đồ thị có chu trình | BFS/DFS với visited theo ID | Tránh thăm trùng hoặc lặp vô hạn |

### 16.1. Không đánh đồng chiều cao và độ rộng

- Cây lệch như danh sách một đường: `h = Θ(n)`, `w = 1`. Inorder/preorder stack có thể sâu O(n), còn BFS queue O(1).
- Cây nhị phân cân đối: `h = Θ(log n)`, nhưng tầng đáy có thể chứa Θ(n) nút. DFS stack O(log n), BFS queue có thể O(n).
- Nếu bắt buộc giữ toàn bộ kết quả, bộ nhớ kết quả O(n) có thể lấn át bộ nhớ iterator; đó là quyết định của **bên tiêu thụ**, không phải bản chất của bộ duyệt lười.

## 17. Thiết kế kiểm thử cho iterator có thể tạm dừng

Một thuật toán duyệt eager có thể được kiểm tra bằng một dãy kết quả. Với lazy iterator, cần kiểm tra **thứ tự** lẫn **trạng thái qua nhiều lần lấy**.

### 17.1. Các trường hợp bắt buộc

1. **Cây rỗng:** generator không yield gì; cursor báo `has_next == False` hoặc `next == END`.
2. **Cây một nút:** `next` đầu trả gốc; lần tiếp báo hết.
3. **Cây lệch trái/phải:** đúng thứ tự và không phát sinh lỗi đệ quy trong phiên bản stack.
4. **Cây cân đối và không cân đối:** so sánh dãy với kết quả tham chiếu độc lập.
5. **Nút có giá trị trùng:** không bỏ nút vì trùng payload.
6. **`has_next` gọi nhiều lần:** không vô tình tiêu thụ nhiều nút.
7. **Dừng sau 1, 2, 3 giá trị rồi tiếp tục:** không lặp hoặc bỏ phần tử.
8. **Duyệt hết rồi gọi tiếp:** nhận tín hiệu kết thúc theo hợp đồng, không dereference null.
9. **Tạo hai iterator độc lập:** tiến trình của một iterator không làm iterator kia tự tiến.
10. **Lấy phần tử qua `islice`:** số kết quả đúng, không materialize cây ngoài ý muốn.
11. **BFS từng tầng:** tổng số giá trị trong các tầng bằng số nút thật.
12. **Generator đóng sớm:** cleanup được gọi theo thiết kế và không tiếp tục sinh giá trị.
13. **Cây bị sửa giữa hai lần lấy:** kiểm tra hành vi hợp đồng (từ chối, snapshot, hoặc live), không chỉ xem chương trình có crash không.
14. **Nút bị hủy trong C++:** không dùng cursor cũ nữa; kiểm tra đường quản lý lifetime.
15. **Cây cực rộng/cực sâu:** theo dõi số phần tử stack/queue đạt giới hạn theo kỳ vọng.
16. **Cây lắp nhầm thành DAG/chu trình:** xác định giới hạn đầu vào; dùng visited nếu chuyển bài toán thành duyệt đồ thị.

### 17.2. Kiểm thử các kết quả khớp giữa lazy và eager

Giả sử `root` là cây bất biến. Có thể tạo kết quả tham chiếu rồi so sánh:

```python
root = sample_tree()

expected_inorder = [1, 3, 4, 6, 7, 8, 10, 13, 14]
expected_preorder = [8, 3, 1, 6, 4, 7, 10, 14, 13]
expected_postorder = [1, 4, 7, 6, 3, 13, 14, 10, 8]
expected_levelorder = [8, 3, 10, 1, 6, 14, 4, 7, 13]

assert [x.value for x in inorder_nodes(root)] == expected_inorder
assert [x.value for x in preorder_nodes(root)] == expected_preorder
assert [x.value for x in postorder_nodes(root)] == expected_postorder
assert [x.value for x in levelorder_nodes(root)] == expected_levelorder
```

Bốn câu `assert` trên tạo list trong **mã kiểm thử** để dễ so sánh. Điều này không làm mất tính lazy của chính hàm generator; ứng dụng chỉ nên materialize toàn bộ kết quả khi có lý do.

### 17.3. Kiểm thử luồng lấy dở và tiếp tục

```python
from itertools import islice

cursor = inorder_nodes(sample_tree())

assert [n.value for n in islice(cursor, 2)] == [1, 3]
assert [n.value for n in islice(cursor, 3)] == [4, 6, 7]
assert [n.value for n in cursor] == [8, 10, 13, 14]
assert [n.value for n in cursor] == []
```

Cùng một iterator được tiếp tục đúng từ vị trí đã dừng. Nếu vô tình gọi `inorder_nodes(root)` mới ở mỗi lần lấy “trang”, ta sẽ **bắt đầu lại từ đầu**, gây lặp giá trị.

### 17.4. Theo dõi bất biến stack/queue trong bản debug

Trong mã kiểm thử:

- Inorder cursor: đỉnh stack phải là **nút kế tiếp** theo inorder; không pop cùng nút hai lần.
- Preorder: thứ tự xử lý dự kiến là cha trước con, trái trước phải.
- Postorder: không xuất nút khi còn con chưa xuất.
- BFS: độ sâu nút trả ra không giảm; queue không chứa nút đã trả trên một cây thật.
- Mọi iterator: số lần yield trên cây không đổi bằng đúng `n`.

Các phép kiểm tra tổng quát có thể tốn O(n) hoặc thêm metadata; không nên nhét chúng vào mọi lần `next` trên đường chạy sản phẩm nếu mục tiêu là giữ độ trễ/bộ nhớ thấp.

## 18. Bài tập có lời giải

### Bài 1. Lazy và eager khác gì?

Một cây có một triệu nút nhưng người dùng chỉ lấy 5 nút đầu theo preorder. Vì sao iterator lazy có thể phù hợp hơn hàm trả `list` toàn cây?

**Lời giải:** Bộ duyệt preorder có thể trả gốc và lần lượt các nút theo nhu cầu mà không tạo danh sách một triệu phần tử. Nó giữ stack O(h+1) và dừng sau vài lần `next`. Tuy nhiên, phải tính công việc để định vị các nút đầu và thời gian duy trì cây/cursor, không khẳng định mọi kiểu lazy luôn O(5).

### Bài 2. Trạng thái inorder sau khi đã xuống trái

Cây có gốc 8, con trái 3, con trái của 3 là 1. Cursor inorder đã đi xuống trái nhất nhưng chưa trả phần tử. Stack từ đáy đến đỉnh là gì và phần tử đầu là gì?

**Lời giải:** Stack là `[8, 3, 1]`. Pop đỉnh trả nút 1. Hai nút 8 và 3 cần được giữ vì sau khi xong cây con trái phải quay về xuất chúng.

### Bài 3. Vì sao phải đi sang `node.right` sau khi xuất inorder?

Sau khi đã thăm toàn bộ cây con trái và xuất nút `node`, nút inorder tiếp theo nằm ở đâu?

**Lời giải:** Nếu `node.right` có cây con phải, nút tiếp theo là nút **trái nhất** trong cây con ấy. Nếu không có, phải quay lên tổ tiên chưa xuất trên stack. Do đó cursor gọi `push_left(node.right)` sau khi pop nút.

### Bài 4. `has_next` có được làm mất phần tử?

Một cursor có đúng một nút còn lại. Người dùng gọi `has_next()` ba lần rồi `next_node()` một lần. Kết quả đúng là gì?

**Lời giải:** Theo hợp đồng cursor trong bài, cả ba lần `has_next` đều trả `True` và không tiêu thụ nút. `next_node` trả nút cuối; sau đó `has_next` mới trả `False`.

### Bài 5. Postorder cần thêm trạng thái gì?

Tại sao một stack chỉ chứa các nút chưa xuất theo kiểu preorder chưa đủ để trả ngay nút khi pop cho postorder?

**Lời giải:** Postorder phải xuất **cha sau cả hai cây con**. Ta cần trạng thái như `(node, ready)` để quay lại cha, hoặc stack + `last_visited` để biết con phải đã xong. Nếu cứ pop rồi xuất ngay như preorder sẽ cho thứ tự sai.

### Bài 6. Thứ tự push trong preorder

Với stack LIFO và quy tắc preorder trái trước phải, tại sao nên push **con phải trước con trái**?

**Lời giải:** Vì LIFO pop phần tử được push **sau** trước. Push phải rồi trái làm con trái nằm trên đỉnh và được xử lý trước con phải.

### Bài 7. Tính dãy postorder

Cho cây:

```text
       A
      / \
     B   C
        / \
       D   E
```

**Lời giải:** Postorder trái–phải–gốc là `B, D, E, C, A`. Một postorder iterator có stack/phase phải trì hoãn A và C tới sau các con.

### Bài 8. BFS lazy cần gì giữa hai lần lấy?

Một BFS iterator đã trả gốc A của cây `A -> {B,C}`. Nếu generator enqueue con trước `yield`, trạng thái queue có gì?

**Lời giải:** Queue là `[B, C]`, đầu B cuối C. Khi bên gọi yêu cầu tiếp, dequeue B; không phải đi lại từ gốc.

### Bài 9. Nhận biết độ phức tạp khác nhau

Với cây một đường `n` nút, so sánh bộ nhớ stack inorder và queue BFS.

**Lời giải:** Inorder dựa trên stack có thể cần O(n) trong trường hợp cây lệch trái (đường trái dài), còn BFS queue O(1) vì mỗi tầng chỉ có một nút. Với cây lệch phải, cách triển khai inorder có thể giữ rất ít nút mỗi lúc; O(n) vẫn là **giới hạn xấu nhất theo chiều cao**, không phải lượng sử dụng thực tế trên mọi cây.

### Bài 10. Cây cân đối, rất rộng

Một cây nhị phân gần đầy có `n` nút, chiều cao Θ(log n). DFS stack và BFS queue dùng bộ nhớ phụ trợ cỡ nào?

**Lời giải:** DFS stack O(log n), còn BFS queue có thể Θ(n) vì tầng cuối rất rộng. Nếu materialize toàn bộ kết quả, cả hai đều thêm O(n) bộ nhớ đầu ra.

### Bài 11. `next` inorder có luôn O(1) worst-case?

**Lời giải:** Không. Một lần `next` có thể phải đẩy một đường trái dài O(h+1). Nhưng trên toàn lượt `n` nút, mỗi nút push/pop một lần nên tổng O(n), khấu hao O(1) cho mỗi giá trị được trả.

### Bài 12. Generator đệ quy có bộ nhớ O(1)?

```python
def recursive(root):
    if root is None:
        return
    yield from recursive(root.left)
    yield root.value
    yield from recursive(root.right)
```

**Lời giải:** Không. Các generator/lời gọi đang dừng giữ chuỗi khung theo đường cây, có thể O(h+1) bộ nhớ. Trên cây quá sâu, Python có thể gặp giới hạn đệ quy.

### Bài 13. Dừng sớm có giải phóng cây ngay không?

Python generator inorder đang tạm dừng, giữ stack các nút. Người dùng đặt `root = None` nhưng vẫn giữ biến `it`. Có chắc toàn bộ nút được GC thu hồi không?

**Lời giải:** Không. Iterator có thể giữ tham chiếu mạnh tới nhiều nút hoặc cây con. Chỉ khi các tham chiếu cần thiết biến mất thì các object mới đủ điều kiện thu hồi theo runtime. `close` và bỏ tham chiếu có thể cần thiết khi không còn nhu cầu duyệt.

### Bài 14. Cursor C++ sau khi cây bị hủy

Một lớp iterator lưu `const Node*` trong vector. Chủ sở hữu gọi `delete` cho các nút nhưng iterator còn giữ địa chỉ. Có được `next` để đọc tiếp không?

**Lời giải:** Không. Các con trỏ có thể treo; `const` không kéo dài vòng đời. Cần giữ cây sống trong thời gian cursor tồn tại hoặc dùng chiến lược sở hữu/snapshot khác theo hợp đồng.

### Bài 15. Tạo hai iterator khác nhau

Tạo `a = inorder_nodes(root)`, `b = inorder_nodes(root)` rồi gọi `next(a)` hai lần. Lần `next(b)` đầu trả gì?

**Lời giải:** Trả phần tử inorder đầu tiên vì hai generator giữ **trạng thái riêng**. `a` đã tiến hai bước không làm `b` tự tiến.

### Bài 16. Lọc lười có tạo kết quả nhanh tương ứng số phần tử lấy?

Một generator lọc nút có `value > 1000` trên cây mà 999.999 nút đầu không thỏa. Muốn lấy giá trị đầu tiên, thời gian có chắc O(1) không?

**Lời giải:** Không. Bộ duyệt phải kiểm tra nhiều nút không thỏa trước khi sinh phần tử đầu, có thể O(n) thời gian. Lazy không tự làm tìm kiếm nhanh hơn; nếu có BST hợp lệ và điều kiện theo khóa, có thể tìm vị trí bằng thuật toán tìm kiếm thích hợp.

### Bài 17. Snapshot nông có đủ khi payload mutable?

Sao chép toàn bộ danh sách các tham chiếu tới nút cây rồi dùng nó làm kết quả duyệt ổn định. Nếu nút có trường `payload` là đối tượng mutable và nơi khác sửa nó, snapshot có cố định giá trị payload không?

**Lời giải:** Không. Danh sách tham chiếu có thể giữ thứ tự nút đã chụp nhưng các nút/payload vẫn được chia sẻ. Muốn snapshot nội dung độc lập, cần sao chép phần dữ liệu cần cố định hoặc dùng đối tượng bất biến/phiên bản hóa.

### Bài 18. DAG dùng chung nút

Hai nhánh cây cùng trỏ tới một nút D. Generator preorder không có visited sẽ xuất D bao nhiêu lần?

**Lời giải:** Có thể hai lần, theo hai đường đến D. Đầu vào khi đó là **DAG**, không phải cây có mỗi nút một cha. Nếu yêu cầu mỗi đỉnh một lần, dùng BFS/DFS đồ thị với visited dựa trên định danh đỉnh.

### Bài 19. Cây bị sửa giữa hai lần `yield`

Preorder generator đọc con của node **sau** `yield`. Bên gọi nhận node rồi đổi `node.left` từ B sang X trước khi gọi `next`. Generator có thể duyệt B hay X?

**Lời giải:** Với mã Mục 7, generator có thể đọc liên kết **mới** và duyệt X. Phiên bản đọc con **trước khi yield** đã ghi lại B cho bước kế tiếp, nhưng vẫn không tự trở thành snapshot toàn bộ cây.

### Bài 20. Kiểu phân trang nào tránh quét lại đầu BST?

Với BST cân bằng và API tìm `lower_bound`/`successor`, cần đọc các trang khóa tăng dần rất sâu. Dùng offset từ gốc ở mỗi trang hay giữ khóa tiếp tục và seek?

**Lời giải:** Theo ngữ nghĩa phù hợp, giữ khóa cuối và tìm phần tử kế tiếp bằng `lower_bound`/successor có thể tránh quét lại nhiều phần tử đầu. Phải xác định xử lý khóa trùng và cây thay đổi giữa các trang. Không mặc định “giữ iterator mãi” là an toàn nếu owner hoặc cấu trúc có thể biến đổi.

## 19. Ghi nhớ để triển khai

- **Bộ duyệt lười** không tạo trước toàn bộ danh sách kết quả: nó trả từng phần tử qua `next`/`yield` và giữ lại **trạng thái để tiếp tục**.
- **Inorder:** phải nhớ các **tổ tiên chưa xuất** bằng stack và đi theo đường trái; tổng O(n), một `next` có thể O(h+1), khấu hao O(1).
- **Preorder:** stack nút chờ, push phải trước trái để ưu tiên trái; với phiên bản stack đơn giản có thể trả gốc ngay.
- **Postorder:** cần khung/phase hoặc trạng thái tương đương để **chỉ xuất cha sau khi hai cây con xong**.
- **Level-order:** dùng FIFO queue chứa nút đã phát hiện nhưng chưa xuất; bộ nhớ O(w), phù hợp duyệt từ nông tới sâu.
- **Đệ quy `yield from` cũng giữ khung trạng thái** O(h+1); không miễn phí bộ nhớ và có giới hạn đệ quy trong Python.
- **Không đồng nhất lazy với snapshot hoặc an toàn đa luồng.** Chèn/xóa/quay cây giữa hai lần lấy có thể làm con trỏ treo, lặp/bỏ nút hoặc phá thứ tự dù iterator vẫn tồn tại.
- **Định nghĩa hợp đồng rõ ràng:** thứ tự, kiểu kết quả (node/value), trạng thái END/STALE, quyền sở hữu, chi phí `next`, cách đóng sớm và quy tắc khi cây thay đổi.
- **Chọn bộ duyệt theo yêu cầu xử lý và hình dạng cây**, đo cả số phần tử cần lấy, chiều cao `h`, độ rộng `w`, dung lượng kết quả và chi phí giữ cây sống trong thời gian người dùng chưa duyệt tiếp.

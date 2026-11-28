# Xóa đầu, xóa sau nút và giới hạn khi chỉ biết nút cần xóa

Trong **danh sách liên kết đơn** (*singly linked list*), mỗi nút chứa dữ liệu và một tham chiếu **next** đến nút tiếp theo. Xóa một phần tử về bản chất là **thay đổi đường liên kết đi từ head** để bỏ qua nút đó, đồng thời duy trì các tham chiếu đầu/cuối và số phần tử.

Phần **Danh sách liên kết** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES** giúp hiểu bất biến, các thao tác và chi phí thời gian/bộ nhớ khi chọn cấu trúc dữ liệu. Bài này đi sâu vào ba câu hỏi thường gặp: vì sao **xóa đầu** là O(1), vì sao **xóa nút ngay sau một nút đã biết** cũng là O(1), và tại sao **chỉ có tham chiếu đến chính nút cần xóa** lại có giới hạn đáng kể trong danh sách đơn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Vẽ các liên kết trước và sau thao tác xóa đầu hoặc xóa nút sau một nút đã biết.
- Cập nhật **head**, **tail**, **size** đúng trong danh sách rỗng, một nút và nhiều nút.
- Giải thích vai trò của **nút đứng trước** khi xóa một nút ở giữa hoặc cuối.
- Phân biệt **xóa nút theo danh tính** với **thay dữ liệu của một nút**.
- Chỉ ra giới hạn của mẹo “sao chép dữ liệu từ nút kế tiếp”, đặc biệt với nút cuối và các tham chiếu khác tới nút.
- Phân tích chi phí xóa khi biết **head**, biết **prev**, chỉ biết **target**, hoặc phải tìm target theo giá trị.
- Cài đặt và tự kiểm chứng các thao tác xóa trong Python.

## 2. Mô hình và bất biến sau thao tác xóa

Xét danh sách liên kết đơn:

~~~text
head
 │
 ▼
[ 10 | next ] ──► [ 20 | next ] ──► [ 30 | None ]
                                          ▲
                                          │
                                         tail
size = 3
~~~

**Head** trỏ tới nút đầu tiên. **Tail** trỏ tới nút cuối cùng, có **next = None**. Nếu chỉ có head, ta vẫn có thể duyệt đến nút cuối, nhưng không thể đi trực tiếp từ một nút về nút đứng trước: danh sách đơn không lưu trường **prev**.

Trong bài này, danh sách không dùng nút canh gác (*sentinel/dummy node*) và duy trì ba thuộc tính **head**, **tail**, **size**. Sau mỗi thao tác hoàn tất, những bất biến dưới đây phải đúng:

1. **Danh sách rỗng:** **head is None**, **tail is None**, **size == 0**.
2. **Danh sách không rỗng:** cả head lẫn tail khác None, nút cuối từ head chính là tail và **tail.next is None**.
3. Đi theo các liên kết **next** từ head phải gặp đúng **size** nút rồi đến None, không có chu trình.
4. Khi chỉ còn một nút, **head is tail**; khi có từ hai nút trở lên, head và tail là hai nút khác nhau.
5. Mỗi lần xóa thành công làm **size giảm đúng 1**; nếu thao tác thất bại, trạng thái danh sách không đổi.

**Xóa khỏi danh sách** nghĩa là không còn đường đi từ head đến nút đã bị gỡ. Trong Python, đối tượng nút vẫn có thể còn tồn tại nếu biến ở chỗ khác đang giữ tham chiếu tới nó. Trong ngôn ngữ quản lý bộ nhớ thủ công như C, việc cập nhật liên kết và giải phóng vùng nhớ là hai trách nhiệm riêng.

## 3. Xóa đầu: pop_front

Để xóa đầu, ta không cần tìm nút đứng trước: **head chính là tham chiếu tới nút cần bỏ**.

### 3.1. Danh sách có từ hai nút trở lên

Trước:

~~~text
head ──► [ A | • ] ──► [ B | • ] ──► [ C | None ] ◄── tail
            ▲
           old
~~~

Sau khi xóa A:

~~~text
head ──────────────► [ B | • ] ──► [ C | None ] ◄── tail

old ──► [ A | None ]      (nút đã tách, nếu ta giữ tham chiếu old)
~~~

Thực hiện:

1. Lưu **old = head** để còn truy cập nút cũ.
2. Gán **head = old.next** để head chuyển sang nút B.
3. Nếu head trở thành None, cập nhật **tail = None**.
4. Giảm size; có thể đặt **old.next = None** để tách nút cũ khỏi chuỗi còn lại.

Ví dụ phương thức:

~~~python
def pop_front(self):
    if self.head is None:
        raise IndexError("Danh sách rỗng")

    old = self.head
    self.head = old.next

    if self.head is None:
        self.tail = None

    old.next = None
    self.size -= 1
    return old.value
~~~

Với ít nhất hai nút, tail giữ nguyên vì nút cuối chưa bị xóa. Tách **old.next = None** chỉ tác động đến đối tượng cũ, sau khi head đã nắm giữ phần còn lại của danh sách.

### 3.2. Danh sách có đúng một nút

Trước:

~~~text
head ─┐
      ▼
    [ A | None ]
      ▲
tail ─┘
size = 1
~~~

Sau khi xóa nút duy nhất:

~~~text
head = None
tail = None
size = 0
~~~

Nếu chỉ đặt head = None mà **quên tail**, cấu trúc báo rỗng khi xem head nhưng tail vẫn trỏ tới nút không thuộc danh sách. Một thao tác thêm cuối về sau có thể nối vào chuỗi sai.

### 3.3. Danh sách rỗng

Khi **head is None**, không có nút để xóa. API cần chọn quy ước nhất quán. Phương thức ở trên ném **IndexError** và giữ nguyên trạng thái. Không thể đọc **head.next** trước khi kiểm tra head.

**Chi phí:** pop_front sử dụng số thao tác con trỏ cố định nên mất **Θ(1)** thời gian, **O(1)** bộ nhớ phụ. Điều này không phụ thuộc vào độ dài n của danh sách.

## 4. Xóa nút ngay sau một nút đã biết: remove_after

Giả sử danh sách có ba nút A → B → C, và đã có tham chiếu **prev** tới nút A. Muốn xóa B, ta cần sửa **prev.next** để nó trỏ tới C.

~~~text
Trước:
head ──► [ A | • ] ──► [ B | • ] ──► [ C | None ] ◄── tail
            ▲                ▲
           prev             removed

Sau:
head ──► [ A | • ] ─────────────────► [ C | None ] ◄── tail

[ B | None ]   (removed đã tách khỏi danh sách)
~~~

Thứ tự hợp lý:

~~~python
removed = prev.next
prev.next = removed.next
removed.next = None
~~~

Dòng **prev.next = removed.next** nối trực tiếp A với C, loại bỏ B khỏi chuỗi đi từ head. Nút B có thể được tách bằng **removed.next = None** sau khi liên kết từ A sang C đã được khôi phục.

Phải kiểm tra trước rằng **prev thuộc danh sách hiện tại** và **prev.next khác None**. Nếu prev là tail, không có nút phía sau để xóa; API có thể ném **IndexError**. Nếu prev không thuộc danh sách, thay next của nó có thể không ảnh hưởng chuỗi từ head nhưng vẫn làm sai size nếu cứ giảm biến đếm.

### 4.1. Xóa nút ở giữa

Với A → B → C → D và prev là A, thao tác bỏ B biến liên kết **A.next** từ B sang C. **Head** vẫn là A, **tail** vẫn là D, chỉ size giảm 1.

### 4.2. Xóa chính nút cuối

Với A → B → C → None và prev là B, nút cần xóa C đang là tail:

~~~text
Trước:
head ──► [ A | • ] ──► [ B | • ] ──► [ C | None ] ◄── tail
                         ▲                ▲
                        prev            removed

Sau:
head ──► [ A | • ] ──► [ B | None ] ◄── tail
~~~

Vì B trở thành nút cuối, **tail = prev**. Đây là thay đổi rất dễ bỏ quên: nếu tail vẫn chỉ C, phép thêm cuối sau đó có thể nối vào một nút đã bị loại khỏi chuỗi.

Cài đặt hoàn chỉnh:

~~~python
def remove_after(self, prev):
    # Tiền điều kiện: prev đang thuộc danh sách này.
    if prev is None:
        raise ValueError("prev không được là None")

    removed = prev.next
    if removed is None:
        raise IndexError("Không có nút sau prev")

    prev.next = removed.next
    if self.tail is removed:
        self.tail = prev

    removed.next = None
    self.size -= 1
    return removed.value
~~~

Không có trường hợp hợp lệ để gọi remove_after trên **danh sách rỗng**: không tồn tại prev thuộc danh sách. Nếu danh sách có **một nút**, nút ấy vừa là head vừa là tail, cũng không có nút phía sau; muốn xóa nó, hãy dùng pop_front.

**Chi phí:** Khi **đã có tham chiếu hợp lệ tới prev**, remove_after dùng Θ(1) thời gian và O(1) bộ nhớ phụ. Nếu cần **tìm prev** theo chỉ số hoặc giá trị trước, chi phí tổng có thể là Θ(n).

## 5. Vì sao xóa một nút ở giữa cần biết nút đứng trước?

Giả sử bạn có tham chiếu **target** trực tiếp đến nút B trong chuỗi:

~~~text
head ──► A ──► B ──► C ──► None
                ▲
              target
~~~

Bạn biết **target.next = C** nhưng B **không lưu địa chỉ của A**. Để thật sự bỏ nút B khỏi đường đi, phép cập nhật cần thực hiện là:

~~~text
A.next = C
~~~

Nếu chưa có tham chiếu tới A, bạn không biết đối tượng nào có trường next đang trỏ đến B. Đây là giới hạn cấu trúc của danh sách **đơn**.

Nếu **có thể truy cập head của danh sách**, bạn có thể duyệt để tìm nút ngay trước target theo **danh tính đối tượng**, rồi dùng remove_after:

~~~text
prev ← head

while prev khác None và prev.next không phải target:
    prev ← prev.next

nếu prev tồn tại:
    remove_after(prev)
~~~

Trường hợp target chính là head được xử lý riêng bằng pop_front. Vòng tìm có chi phí **O(n)** trong trường hợp xấu nhất; một khi tìm thấy prev, nối lại liên kết là O(1).

Nếu chỉ biết giá trị của target, vấn đề còn khác: nhiều nút có thể chứa **cùng giá trị**, nên cần quyết định xóa lần xuất hiện nào. Chỉ so sánh **value** chưa đủ để xác định đúng **đối tượng nút** khi có giá trị trùng.

### 5.1. Khi target là tail

~~~text
head ──► A ──► B ──► C ──► None
                       ▲
                    target = tail
~~~

Target.next bằng None, và target không có tham chiếu tới B. Không có cách “bỏ qua target bằng cách lấy dữ liệu từ nút tiếp theo”, vì **không tồn tại nút tiếp theo**. Nếu có head, ta duyệt để tìm B và đổi **B.next = None**, sau đó cập nhật tail = B. Nếu chỉ cầm tham chiếu tới C và không có cách truy cập cấu trúc khác, không thể thực hiện phép xóa đúng theo cách liên kết đơn thông thường.

Giữ tail trong cấu trúc giúp **truy cập nút cuối** nhanh, nhưng **không** cung cấp tham chiếu đến nút đứng trước tail. Vì thế, xóa cuối danh sách đơn thường mất Θ(n) để tìm prev khi n ≥ 2.

## 6. Mẹo chép nút kế tiếp: làm được gì và không làm được gì?

Có một câu hỏi phỏng vấn phổ biến: “Chỉ có tham chiếu tới nút cần xóa trong danh sách liên kết đơn, có thể xóa trong O(1) không?”

Nếu **target.next tồn tại**, ta có thể sao chép giá trị của nút kế tiếp vào target, rồi bỏ qua nút kế tiếp:

~~~text
Trước:
head ──► A ──► B ──► C ──► D ──► None
                ▲     ▲
              target  next_node

Bước 1: target.value = next_node.value
        target (vẫn cùng đối tượng B cũ) giờ chứa giá trị C

Bước 2: target.next = next_node.next

Sau:
head ──► A ──► [ B cũ, value = C ] ──► D ──► None

Đối tượng C cũ bị loại khỏi chuỗi.
~~~

Mã minh họa riêng cho **chuỗi nút không quản lý tail/size**:

~~~python
def overwrite_from_successor(target):
    if target is None or target.next is None:
        raise ValueError("Cần target có nút kế tiếp")

    successor = target.next
    target.value = successor.value
    target.next = successor.next
    successor.next = None
~~~

Nếu phép gán/copy giá trị là O(1), việc cập nhật liên kết và payload trong ví dụ là **O(1)**. Tuy nhiên, **hành vi này không tương đương với việc xóa đối tượng target**:

- **Danh tính nút thay đổi theo ý nghĩa:** đối tượng target cũ vẫn ở trong danh sách, nhưng mang giá trị của successor. Đối tượng successor mới là nút bị gỡ.
- **Tham chiếu từ bên ngoài bị ảnh hưởng:** một biến khác đang giữ target sẽ quan sát giá trị mới; biến giữ successor vẫn tham chiếu tới đối tượng vừa bị gỡ.
- **Không xử lý được tail:** nếu target là nút cuối, **target.next is None**, nên không có successor để chép.
- **Có thể làm sai tail/size:** nếu danh sách giữ tail và successor chính là tail, sau khi bỏ successor, tail phải chuyển về target. Nếu còn size, phải giảm 1. Khi chỉ biết target mà không biết đối tượng quản lý danh sách, không thể tự cập nhật các thuộc tính đó.
- **Có thể vi phạm quy tắc dữ liệu:** khi nút mang danh tính riêng, dữ liệu bất biến, ràng buộc khóa, con trỏ trỏ vào payload hoặc có tài nguyên cần giải phóng, “chuyển payload” có thể không tương đương xóa đối tượng.

**Ví dụ về danh tính đối tượng trong Python:**

~~~python
a = Node("A")
b = Node("B")
c = Node("C")
a.next = b
b.next = c

external_b = b
external_c = c

overwrite_from_successor(b)

assert a.next is b          # Đối tượng b VẪN ở trong danh sách.
assert b.value == "C"       # Nội dung của b bị đổi từ B sang C.
assert b.next is None
assert external_b is b
assert external_c is c      # Đối tượng c cũ vẫn tồn tại qua alias.
assert external_c is not b  # Đối tượng c mới là nút bị gỡ.
~~~

Trong ví dụ, nhìn theo **giá trị** thì danh sách trở thành A → C, nhưng nút gốc mang danh tính B vẫn ở đó. Vì vậy, mẹo này chỉ phù hợp với bài toán cho phép **ghi đè dữ liệu**, không quan tâm danh tính nút và xử lý đầy đủ các metadata liên quan.

Nếu yêu cầu là “xóa đúng đối tượng B” và các đối tượng khác có thể giữ tham chiếu tới các nút, cách đáng tin cậy là tìm nút trước B (hoặc có sẵn prev) rồi đổi liên kết từ nút trước. **Không thể khẳng định xóa theo danh tính bất kỳ chỉ với target luôn đạt O(1)** trong danh sách liên kết đơn cơ bản.

## 7. Cài đặt Python: xóa đúng nút và duy trì head/tail/size

Ví dụ sau sử dụng Python 3.10 trở lên. Các phương thức **pop_front**, **remove_after** và **remove_node** trả về kết quả phù hợp với từng API. **remove_node** nhận tham chiếu tới chính đối tượng cần xóa, tìm prev từ head và trả **True/False** để phân biệt có xóa thành công hay không.

~~~python
from __future__ import annotations


class Node:
    def __init__(self, value: int, next_node: Node | None = None) -> None:
        self.value = value
        self.next = next_node


class SinglyLinkedList:
    def __init__(self) -> None:
        self.head: Node | None = None
        self.tail: Node | None = None
        self.size = 0

    def append(self, value: int) -> Node:
        node = Node(value)
        if self.tail is None:
            self.head = node
        else:
            self.tail.next = node
        self.tail = node
        self.size += 1
        return node

    def pop_front(self) -> int:
        if self.head is None:
            raise IndexError("Không thể xóa đầu danh sách rỗng")

        old = self.head
        self.head = old.next
        if self.head is None:
            self.tail = None

        old.next = None
        self.size -= 1
        return old.value

    def remove_after(self, prev: Node) -> int:
        # Tiền điều kiện: prev thực sự thuộc danh sách này.
        if prev is None:
            raise ValueError("prev không được là None")

        removed = prev.next
        if removed is None:
            raise IndexError("Không có nút ngay sau prev")

        prev.next = removed.next
        if removed is self.tail:
            self.tail = prev

        removed.next = None
        self.size -= 1
        return removed.value

    def remove_node(self, target: Node | None) -> bool:
        """Xóa đúng đối tượng target, nếu thuộc danh sách."""
        if target is None:
            return False

        if self.head is target:
            self.pop_front()
            return True

        prev = self.head
        while prev is not None and prev.next is not target:
            prev = prev.next

        if prev is None:  # target không nằm trong chuỗi từ head
            return False

        self.remove_after(prev)
        return True

    def to_list(self) -> list[int]:
        values = []
        current = self.head
        while current is not None:
            values.append(current.value)
            current = current.next
        return values

    def check_invariants(self) -> None:
        """Phục vụ học và gỡ lỗi, kiểm tra cả chu trình."""
        if self.head is None:
            assert self.tail is None and self.size == 0
            return

        assert self.tail is not None and self.tail.next is None
        visited: set[int] = set()
        count = 0
        last = None
        current = self.head

        while current is not None:
            assert id(current) not in visited, "Có chu trình"
            visited.add(id(current))
            last = current
            count += 1
            current = current.next

        assert last is self.tail, "Tail sai"
        assert count == self.size, "Size sai"


items = SinglyLinkedList()
items.check_invariants()

# Xóa đầu khi rỗng: báo lỗi và trạng thái không đổi.
try:
    items.pop_front()
except IndexError:
    pass
else:
    raise AssertionError("Thiếu IndexError")
items.check_invariants()

n10 = items.append(10)
n20 = items.append(20)
n30 = items.append(30)
assert items.to_list() == [10, 20, 30]

# Xóa nút giữa theo prev.
assert items.remove_after(n10) == 20
items.check_invariants()
assert items.to_list() == [10, 30]
assert n20.next is None  # Nút đã gỡ có thể vẫn tồn tại qua biến n20.

# Xóa tail: cập nhật tail về n10.
assert items.remove_after(n10) == 30
items.check_invariants()
assert items.to_list() == [10]
assert items.head is items.tail is n10

# Xóa đầu của danh sách một nút -> rỗng.
assert items.pop_front() == 10
items.check_invariants()
assert items.head is None and items.tail is None
assert items.size == 0

# Xóa theo danh tính khi chỉ được truyền target.
first = items.append(7)
middle = items.append(7)  # Hai nút cùng giá trị 7.
last = items.append(9)
assert items.remove_node(middle) is True
items.check_invariants()
assert items.head is first and items.tail is last
assert items.to_list() == [7, 9]

assert items.remove_node(Node(7)) is False  # Nút ngoài danh sách.
assert items.remove_node(last) is True      # Xóa tail.
assert items.remove_node(first) is True     # Xóa head/nút duy nhất.
items.check_invariants()
assert items.to_list() == []
~~~

Trong **remove_node**, việc so sánh **is** dùng **danh tính đối tượng**, vì các nút có thể có giá trị bằng nhau. Nếu không có target trong danh sách, hàm trả False và không thay đổi head, tail, size.

Hàm **check_invariants** duyệt qua toàn bộ chuỗi, theo dõi danh tính nút và phát hiện sai số lượng, tail hoặc chu trình; nó có chi phí O(n) thời gian và O(n) bộ nhớ phụ do tập **visited**. Chi phí kiểm tra này không nằm trong độ phức tạp của phép xóa cơ bản nếu không gọi kiểm tra sau mỗi lần xóa.

## 8. Bảng xử lý trường hợp biên

| Thao tác | Trước thao tác | Kết quả / thay đổi bắt buộc |
| --- | --- | --- |
| pop_front | Rỗng | Báo lỗi (theo API bài này), không đổi head/tail/size. |
| pop_front | Một nút | Head và tail đều thành None; size thành 0. |
| pop_front | Từ hai nút | Head chuyển đến nút sau; tail giữ nguyên; size giảm 1. |
| remove_after(prev) | prev là tail | Không có nút sau prev, báo lỗi; không đổi trạng thái. |
| remove_after(prev) | Nút sau prev nằm giữa | Nối prev tới nút sau removed; head/tail không đổi. |
| remove_after(prev) | Nút sau prev là tail | Nối prev.next = None; tail chuyển về prev. |
| remove_node(target) | target chính là head | Xử lý bằng pop_front, O(1). |
| remove_node(target) | target nằm giữa/cuối | Tìm prev theo danh tính; sửa prev.next và có thể tail. |
| remove_node(target) | target không thuộc danh sách | Trả False; không thay đổi cấu trúc. |
| Chép successor | target là tail | Không thực hiện được, vì target.next là None. |

Nếu API trả **giá trị** nút bị xóa, giá trị đó hoàn toàn có thể bằng None nếu kiểu dữ liệu cho phép; do đó, nên dùng **exception**, **boolean** hoặc một kết quả có trạng thái rõ ràng để biểu đạt lỗi, thay vì luôn dùng None làm dấu hiệu thất bại.

## 9. Độ phức tạp thời gian và bộ nhớ

Giả sử danh sách có n nút trước thao tác; các bất biến hợp lệ; chi phí so sánh dữ liệu, cấp phát và giải phóng bộ nhớ được xem là hằng số khi thích hợp.

| Thao tác | Thời gian | Bộ nhớ phụ | Điều kiện |
| --- | --- | --- | --- |
| Xóa đầu bằng head | **Θ(1)** | O(1) | Có thể kiểm tra rỗng bằng head. |
| Xóa ngay sau prev đã biết | **Θ(1)** | O(1) | prev thuộc danh sách và có nút kế tiếp. |
| Tìm prev từ head để xóa đúng target | **O(n)**, xấu nhất Θ(n) | O(1) | Chỉ biết target và vẫn truy cập được danh sách qua head. |
| Xóa nút có giá trị x đầu tiên | **O(n)**, xấu nhất Θ(n) | O(1) | Phải duyệt để tìm target/prev. |
| Xóa tail khi n ≥ 2 | **Θ(n)** | O(1) | Phải tìm nút đứng trước tail trong danh sách đơn. |
| Chép dữ liệu từ successor và bỏ successor | **O(1)** nếu chép là O(1) | O(1) | Target không phải nút cuối; semantics của đối tượng có thể thay đổi. |
| Kiểm tra toàn bộ bất biến với visited set | **Θ(n)** | O(n) | Duyệt mọi nút và theo dõi đối tượng đã thăm. |

**Bộ nhớ gốc của danh sách:** O(n) cho n nút và liên kết next. Xóa một nút thành công làm số nút trong chuỗi giảm một, nhưng thời điểm thu hồi bộ nhớ phụ thuộc ngôn ngữ và việc có còn tham chiếu đến đối tượng bị gỡ hay không.

**Phân biệt công việc định vị với công việc đổi liên kết:** Đổi một vài con trỏ sau khi biết prev là Θ(1). Nhưng việc tìm prev hoặc target bằng duyệt có thể là Θ(n), làm tổng phép xóa trở thành Θ(n) trong trường hợp xấu nhất.

### Danh sách đơn so với danh sách đôi

Danh sách liên kết **đôi** (*doubly linked list*) thường lưu cả **prev** và **next** cho mỗi nút. Khi đã có tham chiếu hợp lệ tới target trong danh sách đôi, có thể truy cập trực tiếp target.prev và target.next để nối hai phía, cập nhật head/tail khi cần; thao tác xóa có thể O(1).

Đổi lại, mỗi nút cần thêm một tham chiếu prev và các thao tác chèn/xóa phải duy trì thêm các bất biến về liên kết hai chiều. Danh sách đơn tiết kiệm một liên kết trên mỗi nút và phù hợp khi chủ yếu chèn/xóa ở đầu hoặc khi đã có **prev**.

## 10. Những lỗi thường gặp

| Sai sót | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Xóa đầu khi chưa kiểm tra head là None | Truy cập thuộc tính của None và gây lỗi ngoài dự kiến. | Kiểm tra rỗng trước khi đọc head.next. |
| Xóa nút duy nhất nhưng giữ tail cũ | Tail trỏ tới nút không còn trong danh sách. | Khi head thành None, cập nhật tail = None. |
| Xóa sau prev mà chỉ gán prev.next = None | Cắt bỏ toàn bộ phần đuôi sau removed. | Gán prev.next = removed.next. |
| Xóa tail nhưng không đổi tail về prev | Tail sai, lần append sau có thể nối hỏng danh sách. | Khi removed is tail, đặt tail = prev. |
| Quên giảm size | Số phần tử báo cáo sai. | Giảm size một lần duy nhất khi xóa thành công. |
| Không bảo đảm prev thuộc danh sách | Có thể thay đổi nút không liên quan nhưng vẫn giảm size. | Chỉ nhận prev từ API của danh sách hoặc kiểm tra tư cách thành viên. |
| So sánh nút theo value khi cần xóa theo danh tính | Có thể xóa nhầm một nút khác có cùng giá trị. | So sánh tham chiếu bằng is. |
| Dùng mẹo chép successor để “xóa target” | Target cũ vẫn tồn tại, dữ liệu và alias bị đổi; tail có thể sai. | Phân biệt rõ thao tác ghi đè dữ liệu với xóa đúng đối tượng. |
| Cho rằng có tail thì xóa tail luôn O(1) | Không biết nút trước tail trong danh sách đơn. | Duyệt tìm prev hoặc đổi cấu trúc dữ liệu nếu nhu cầu thường xuyên. |
| Giải phóng nút trước khi nối lại trong C/C++ | Có thể đọc vùng nhớ đã giải phóng hoặc mất phần đuôi. | Lưu next, sửa liên kết, rồi giải phóng đúng nút theo quy tắc quản lý bộ nhớ. |

Khi gỡ lỗi, hãy vẽ mũi tên từ head đến None, xác nhận nút cuối đúng là tail, đếm số nút và kiểm tra không có chu trình. Thử riêng các trạng thái **0 nút**, **1 nút** và **2 nút** vì lỗi ở ranh giới thường khó phát hiện khi chỉ thử danh sách dài.

## 11. Ví dụ ứng dụng và bài tập

**Ứng dụng 1 — Stack dựa trên danh sách đơn.** Trong ngăn xếp, thao tác lấy phần tử trên cùng có thể gắn với **pop_front** trên head, đạt Θ(1). Không cần tìm phần tử trước nút cần xóa.

**Ứng dụng 2 — Queue dựa trên head/tail.** Trong hàng đợi, **dequeue** xóa đầu trong Θ(1); khi lấy phần tử cuối cùng ra khỏi hàng đợi, phải đưa cả head và tail về None. Điều này giúp **enqueue** tiếp theo nối đúng khi hàng đợi trở về trạng thái rỗng.

**Ứng dụng 3 — Loại bỏ một tác vụ sau tác vụ hiện tại.** Nếu hệ thống giữ sẵn tham chiếu đến nút đang xử lý, có thể xóa tác vụ ngay sau nó bằng **remove_after** trong Θ(1). Nếu chỉ biết ID tác vụ cần xóa mà không biết nút đứng trước, cần duyệt hoặc một cơ chế chỉ mục khác.

### Bài tập 1 — Xóa đầu

Cho **head → 4 → 8 → 12 → None**, tail chỉ nút 12 và size = 3. Sau pop_front, head, tail và size là gì?

*Đáp án:* Head chỉ nút 8; tail vẫn chỉ nút 12; size = 2. Nút 4 không còn đi tới được từ head.

### Bài tập 2 — Xóa sau prev

Cho **A → B → C → D → None**, prev chỉ B. Xóa ngay sau prev khiến liên kết nào thay đổi?

*Đáp án:* Nút cần xóa là C. Gán **B.next = D**, có thể tách **C.next = None**, size giảm 1. Head vẫn là A, tail vẫn là D.

### Bài tập 3 — Xóa tail

Cho danh sách **10 → 20 → None**, head chỉ 10, tail chỉ 20. Biết prev là nút 10, cần cập nhật những gì khi xóa sau prev?

*Đáp án:* **prev.next = None**, **tail = prev**, size từ 2 giảm còn 1; head và tail cùng chỉ nút 10.

### Bài tập 4 — Chỉ biết target

Cho chuỗi **A → B → C**, chỉ biết tham chiếu target trỏ B, không có tham chiếu head hoặc prev. Có thể bảo đảm xóa đúng **đối tượng B** trong O(1) không?

*Đáp án:* Không. Có thể chép dữ liệu C vào B rồi bỏ đối tượng C khỏi chuỗi nếu cho phép ghi đè payload và điều kiện phù hợp, nhưng **đối tượng B vẫn ở trong danh sách**. Muốn gỡ đúng B phải sửa **A.next**, đòi hỏi biết A hoặc tìm được A.

### Bài tập 5 — Giới hạn tail

Với chuỗi **A → B → C → None**, chỉ biết target là C. Vì sao không dùng mẹo chép successor để xóa C?

*Đáp án:* C là tail nên **C.next = None**. Không có successor để chép và bỏ qua. Muốn xóa C phải có hoặc tìm được nút B đứng trước nó.

### Bài tập 6 — Phân tích tổng chi phí

Có n nút và bạn chỉ biết một giá trị x cần xóa khỏi danh sách đơn. Giả sử phải tìm lần xuất hiện đầu tiên của x từ head rồi đổi liên kết. Tổng thời gian trong trường hợp xấu nhất là bao nhiêu?

*Đáp án:* **Θ(n)**: bước duyệt tìm target/prev chiếm thời gian tuyến tính; bước gỡ liên kết sau khi tìm thấy prev chỉ tốn Θ(1).

### Bài tập 7 — Nút giống giá trị

Danh sách có hai nút khác nhau đều chứa 7. Bạn giữ tham chiếu tới nút 7 thứ hai nhưng gọi hàm xóa theo **value = 7**. Có chắc nút thứ hai bị xóa không?

*Đáp án:* Không. Hàm xóa lần xuất hiện đầu tiên theo giá trị thường xóa nút 7 thứ nhất. Cần API xóa theo **danh tính target** để xóa đúng đối tượng được chỉ định.

**Ghi nhớ:** Xóa đầu và xóa sau một nút **đã biết** cần số phép cập nhật liên kết cố định nên có thể đạt Θ(1). Muốn xóa đúng một nút ở giữa hoặc cuối mà **chỉ biết chính nút đó**, ta thường phải tìm **nút đứng trước** từ head, tốn Θ(n) trong trường hợp xấu nhất. Mẹo chép dữ liệu từ successor chỉ áp dụng trong điều kiện hẹp và không bảo toàn danh tính nút.

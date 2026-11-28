# Đảo danh sách và cập nhật liên kết an toàn

**Đảo danh sách liên kết** (*linked-list reversal*) là biến thứ tự nút **A → B → C** thành **C → B → A**. Thông thường, ta **không đổi giá trị chứa trong mỗi nút**, mà thay đổi các tham chiếu **next** (và **prev** nếu là danh sách đôi). Sau đảo, A, B, C vẫn là các đối tượng ban đầu; chỉ vị trí tương đối và các liên kết giữa chúng thay đổi.

Thao tác này dễ mắc lỗi bởi một phép gán sai có thể làm mất đường đi đến toàn bộ phần đuôi. Quy tắc cốt lõi là **lưu liên kết cũ trước khi ghi đè**, đảo từng cạnh, rồi cập nhật head/tail đúng lúc.

Trong mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, bài thuộc chương **Danh sách liên kết** và là ví dụ tiêu biểu để học bất biến, thao tác, độ phức tạp thời gian/bộ nhớ và lựa chọn cấu trúc dữ liệu phù hợp.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt đảo **liên kết nút** với đảo **giá trị dữ liệu**.
- Mô phỏng và cài đặt thuật toán đảo danh sách đơn tại chỗ bằng **previous**, **current**, **next_node**.
- Giải thích thứ tự gán liên kết nào bảo đảm không thất lạc nút.
- Chứng minh tính đúng đắn qua bất biến vòng lặp.
- Cập nhật head, tail, size trong các danh sách có 0, 1, 2 hoặc nhiều nút.
- Phân tích các biến thể: đảo bằng đệ quy, đảo một đoạn và đảo danh sách đôi.
- Nhận biết sự khác biệt khi đảo danh sách vòng.
- Đánh giá rủi ro đối với iterator, tham chiếu bên ngoài và cập nhật đồng thời.
- Phân tích độ phức tạp thời gian và bộ nhớ; luyện tập phát hiện lỗi.

## 2. Đảo liên kết thực sự thay đổi điều gì?

Xét danh sách đơn có ba nút A, B, C:

~~~text
Trước:
head                                 tail
 │                                    │
 ▼                                    ▼
[A | next] ───► [B | next] ───► [C | None]

Sau:
head                                 tail
 │                                    │
 ▼                                    ▼
[C | next] ───► [B | next] ───► [A | None]
~~~

Bảng thay đổi cụ thể:

| Nút | next trước khi đảo | next sau khi đảo |
| --- | --- | --- |
| A | B | None |
| B | C | A |
| C | None | B |

Từ đó:

- **head mới** là **tail cũ** (nút C).
- **tail mới** là **head cũ** (nút A).
- **size** không thay đổi vì không tạo hay xóa nút.
- Đối tượng nút và giá trị bên trong mỗi nút vẫn giữ nguyên.

Một biến ngoài đang trỏ tới A vẫn trỏ tới **chính A**, dù sau đảo A là tail và A.next là None. Nếu chỉ hoán đổi giá trị giữa các nút, những tham chiếu ngoài sẽ thấy một hành vi khác: các nút giữ nguyên vị trí liên kết nhưng dữ liệu đã đổi. Hai thao tác **không tương đương** khi nút có danh tính, metadata hoặc được tham chiếu từ nơi khác.

## 3. Ba biến then chốt và thứ tự gán an toàn

Thuật toán đảo danh sách đơn tại chỗ dùng ba tham chiếu:

- **previous**: đầu của đoạn nút **đã đảo**.
- **current**: nút sẽ được chuyển khỏi đoạn chưa xử lý.
- **next_node**: nút tiếp theo **theo chiều cũ**, phải lưu trước khi thay current.next.

Khởi tạo:

~~~python
previous = None
current = head
~~~

Ở mỗi vòng:

~~~python
next_node = current.next    # 1. Giữ đường đi tới phần còn lại.
current.next = previous     # 2. Đảo chiều cạnh của current.
previous = current          # 3. Mở rộng đoạn đã đảo.
current = next_node         # 4. Đi tới nút chưa xử lý.
~~~

Lặp cho tới khi current là None. Sau vòng lặp, previous chỉ nút đầu của danh sách đảo.

### Vì sao phải lưu next_node trước?

Giả sử đang ở B trong chuỗi A → B → C, còn A đã được đảo:

~~~text
Đã đảo:        A → None        previous = A
Chưa xử lý:    B → C → None    current = B
~~~

Nếu thực hiện **B.next = A** trước, B sẽ không còn giữ liên kết đến C. Khi đó, đi tiếp bằng **current.next** khiến chương trình quay về A, không đến C. Nút C có thể trở thành phần dữ liệu không còn truy cập được qua các tham chiếu thuật toán đang giữ.

Đoạn sau **sai**:

~~~python
current.next = previous
current = current.next      # Đây là previous cũ, không phải next cũ.
previous = current
~~~

Đoạn đúng phải lưu **next_node = current.next** trước, rồi mới thay current.next, và tiến tới next_node đã lưu.

## 4. Mô phỏng đảo A → B → C từng bước

Trạng thái đầu:

~~~text
previous ──► None

current ──► A ──► B ──► C ──► None
~~~

**Lượt 1:**

~~~text
next_node = B
A.next = None
previous = A
current = B

Đoạn đã đảo:       A ──► None
                   ▲
                 previous

Đoạn còn lại:      B ──► C ──► None
                   ▲
                 current
~~~

**Lượt 2:**

~~~text
next_node = C
B.next = A
previous = B
current = C

Đoạn đã đảo:       B ──► A ──► None
                   ▲
                 previous

Đoạn còn lại:      C ──► None
                   ▲
                 current
~~~

**Lượt 3:**

~~~text
next_node = None
C.next = B
previous = C
current = None

Đoạn đã đảo:       C ──► B ──► A ──► None
                   ▲
                 previous
~~~

Sau lượt 3, current là None và previous trỏ tới C. Ta có bảng:

| Lượt | current trước xử lý | next_node đã lưu | Liên kết được đổi | previous sau lượt |
| ---: | --- | --- | --- | --- |
| 1 | A | B | A.next = None | A |
| 2 | B | C | B.next = A | B |
| 3 | C | None | C.next = B | C |

Kết thúc bằng **head = previous = C** và **tail = head cũ = A**.

## 5. Bất biến vòng lặp và chứng minh đúng đắn

**Bất biến** hữu ích là:

> Ở đầu mỗi lượt, previous đứng đầu chuỗi đã đảo, current đứng đầu chuỗi chưa xử lý. Hai chuỗi không chứa nút chung; mọi nút ban đầu vẫn thuộc đúng một trong hai chuỗi. Đoạn trước previous đã được nối theo thứ tự đảo, còn đoạn từ current vẫn giữ thứ tự cũ.

### Khởi tạo

Trước vòng đầu, previous là None nên chuỗi đã đảo rỗng. Current là head nên toàn bộ danh sách ban đầu còn trong chuỗi chưa xử lý. Không có nút bị thất lạc.

### Duy trì

Giả sử bất biến đúng ở đầu lượt và current trỏ X.

1. Lưu **next_node** để giữ lối vào đoạn sau X.
2. Đổi **X.next** sang previous, đưa X vào đầu đoạn đã đảo.
3. Đổi previous thành X, current thành next_node.
4. Đoạn đã đảo dài thêm một nút, đoạn còn lại ngắn đi một nút. Không có nút chung hoặc bị bỏ rơi.

Vì vậy bất biến tiếp tục đúng ở đầu lượt kế tiếp.

### Kết thúc

Trong danh sách đơn **hữu hạn và không có chu trình**, mỗi lượt giảm số nút chưa xử lý đi một. Sau n lượt, current bằng None. Bất biến cho biết chuỗi bắt đầu từ previous chứa tất cả n nút theo thứ tự đảo.

Nút head cũ là nút được xử lý đầu tiên: next của nó đã thành None, nên nó chính là tail mới. Số nút không đổi, do đó **size giữ nguyên**.

**Điều kiện tiên quyết:** Danh sách đầu vào phải hợp lệ và có điểm kết thúc None. Với danh sách vòng, thuật toán dừng tại None không phù hợp; xem mục 11.

## 6. Head, tail và các trường hợp biên

Trong cấu trúc có cả head, tail, size, cần ghi nhớ **head cũ** trước khi sửa liên kết:

~~~python
def reverse(self):
    old_head = self.head
    previous = None
    current = self.head

    while current is not None:
        next_node = current.next
        current.next = previous
        previous = current
        current = next_node

    self.head = previous
    self.tail = old_head
    # Không thay đổi self.size.
~~~

Bảng các trạng thái:

| Số nút trước đảo | Head sau đảo | Tail sau đảo | Size |
| ---: | --- | --- | ---: |
| 0 | None | None | 0 |
| 1, nút X | X | X | 1 |
| 2, A → B | B | A | 2 |
| n, A → ... → Z | Z | A | n |

**Rỗng:** current ban đầu là None, vòng lặp không chạy; head/tail vẫn None.

**Một nút:** current chỉ nút X, next_node là None, X.next được gán None; head/tail vẫn X.

**Nhiều nút:** head trở thành nút cuối cũ; tail trở thành nút đầu cũ. Vì liên kết của nút đầu cũ đã được sửa thành None ngay từ lượt đầu, ta cũng có **tail.next is None**.

Một lỗi hay gặp là chỉ thay head mà không thay tail. Khi đó một lời gọi append sau đảo có thể nối vào sai nút và làm thất lạc một phần danh sách.

## 7. Mã Python tự chứa: đảo danh sách đơn tại chỗ

Ví dụ Python 3.10 trở lên có cả append, reverse, duyệt và kiểm tra bất biến.

~~~python
from __future__ import annotations


class Node:
    def __init__(self, value: int, next_node: Node | None = None):
        self.value = value
        self.next = next_node


class SinglyLinkedList:
    def __init__(self):
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

    def reverse(self) -> None:
        old_head = self.head
        previous = None
        current = self.head

        while current is not None:
            next_node = current.next
            current.next = previous
            previous = current
            current = next_node

        self.head = previous
        self.tail = old_head

    def values(self) -> list[int]:
        values = []
        current = self.head
        while current is not None:
            values.append(current.value)
            current = current.next
        return values

    def check_invariants(self) -> None:
        # Chỉ phục vụ kiểm tra, không thuộc chi phí của reverse.
        if self.size == 0:
            assert self.head is None and self.tail is None
            return

        assert self.head is not None and self.tail is not None
        assert self.tail.next is None

        current = self.head
        visited = set()
        count = 0
        last = None
        while current is not None:
            assert id(current) not in visited, "Có chu trình"
            visited.add(id(current))
            last = current
            count += 1
            current = current.next

        assert last is self.tail, "Tail sai"
        assert count == self.size, "Size sai"


items = SinglyLinkedList()
items.reverse()                  # Rỗng
items.check_invariants()
assert items.values() == []

a = items.append(10)
items.reverse()                  # Một nút
items.check_invariants()
assert items.head is items.tail is a
assert a.next is None

b = items.append(20)
c = items.append(30)
d = items.append(40)
assert items.values() == [10, 20, 30, 40]

items.reverse()
items.check_invariants()
assert items.values() == [40, 30, 20, 10]
assert items.head is d and items.tail is a
assert d.next is c and c.next is b
assert b.next is a and a.next is None
assert items.size == 4

items.reverse()                  # Hai lần đảo khôi phục thứ tự.
items.check_invariants()
assert items.values() == [10, 20, 30, 40]

items.reverse()
items.append(50)                # Append sau đảo vẫn phải đúng.
items.check_invariants()
assert items.values() == [40, 30, 20, 10, 50]
assert items.tail.value == 50
~~~

**Giải thích:** Reverse chỉ cập nhật tham chiếu; không cấp phát thêm nút. Những biến a, b, c, d vẫn tham chiếu đúng đối tượng ban đầu. Hàm check_invariants kiểm tra tail, size, chu trình và các nút có thể đi tới được từ head. Nó tốn Θ(n) thời gian, O(n) bộ nhớ phụ do tập visited; không phải một bước mặc định cần chạy trong thuật toán đảo.

## 8. Đảo bằng đệ quy: đúng nhưng tốn ngăn xếp

Có thể đảo bằng cách đảo đệ quy chuỗi bắt đầu tại nút kế tiếp trước, rồi nối nút hiện tại vào cuối kết quả:

~~~python
def reverse_recursive(head):
    if head is None or head.next is None:
        return head

    new_head = reverse_recursive(head.next)
    head.next.next = head
    head.next = None
    return new_head
~~~

Ví dụ với A → B → C:

~~~text
reverse(A) gọi reverse(B)
reverse(B) gọi reverse(C)
reverse(C) trả C

Quay lui:
C.next = B; B.next = None
B.next = A; A.next = None

Kết quả:
C → B → A → None
~~~

**Vì sao hai gán bên trong đúng?** Sau khi đoạn từ head.next được đảo, nút kế tiếp cũ đứng cuối đoạn ấy. Gán **head.next.next = head** nối nó tới head cũ; gán **head.next = None** biến head cũ thành nút cuối của đoạn kết quả.

Nếu danh sách giữ head/tail:

~~~python
old_head = linked_list.head
linked_list.head = reverse_recursive(linked_list.head)
linked_list.tail = old_head
# Không thay đổi size.
~~~

**Độ phức tạp:** thời gian Θ(n), bộ nhớ phụ **Θ(n)** do ngăn xếp lời gọi đệ quy. Đây là điểm khác với bản vòng lặp dùng O(1) bộ nhớ phụ, dù cả hai đều sửa liên kết ngay trên nút cũ. Python còn có giới hạn độ sâu đệ quy; danh sách rất dài có thể gây **RecursionError**.

Nếu cần xử lý danh sách lớn với chiều dài khó dự đoán, thường nên chọn vòng lặp.

## 9. Đảo một đoạn [left, right] trong danh sách đơn

Đôi khi chỉ muốn đảo các nút từ chỉ số **left** đến **right** (gồm cả hai đầu), giữ nguyên các nút ngoài đoạn.

~~~text
Trước:
10 → 20 → 30 → 40 → 50 → None
     ^           ^
   left=1      right=3

Sau:
10 → 40 → 30 → 20 → 50 → None
~~~

Cần bảo toàn ba mốc:

- **before**: nút ngay trước đoạn, hoặc dummy head nếu left = 0.
- **segment_tail**: nút đầu đoạn **trước khi đảo**, sẽ trở thành cuối đoạn sau đảo.
- **after**: nút ngay sau đoạn, dùng để nối lại chuỗi khi đã đảo xong.

### Các bước

1. Kiểm tra **0 ≤ left ≤ right < size** trước khi sửa cấu trúc.
2. Dùng dummy head để có một đối tượng before kể cả khi left = 0.
3. Đi từ dummy đến nút ngay trước đoạn.
4. Đảo đúng **right − left + 1** nút bằng previous/current/next_node.
5. Gán **before.next = đầu đoạn đã đảo**.
6. Gán **segment_tail.next = after** để nối lại phần chưa đảo.
7. Đặt head = dummy.next; nếu đoạn chạm cuối, tail = segment_tail. Size giữ nguyên.

Mã dưới đây là **phương thức bổ sung vào lớp SinglyLinkedList** ở mục 7:

~~~python
def reverse_range(self, left: int, right: int) -> None:
    if not (0 <= left <= right < self.size):
        raise IndexError("Đoạn đảo ngoài phạm vi")

    dummy = Node(0, self.head)
    before = dummy
    for _ in range(left):
        before = before.next

    segment_tail = before.next
    current = segment_tail
    previous = None

    for _ in range(right - left + 1):
        next_node = current.next
        current.next = previous
        previous = current
        current = next_node

    # current là nút ngay sau đoạn đảo (after).
    before.next = previous
    segment_tail.next = current

    self.head = dummy.next
    if right == self.size - 1:
        self.tail = segment_tail
~~~

**Điểm dễ sai:** Khi đảo xong, previous là đầu đoạn đảo, nhưng **segment_tail** vẫn giữ danh tính nút đầu cũ. Nếu quên **segment_tail.next = current**, toàn bộ các nút sau đoạn có thể không còn đi tới được từ head.

Ví dụ sau giả định đã gắn phương thức trên vào lớp:

~~~python
sample = SinglyLinkedList()
for value in [10, 20, 30, 40, 50]:
    sample.append(value)

sample.reverse_range(1, 3)
sample.check_invariants()
assert sample.values() == [10, 40, 30, 20, 50]

sample.reverse_range(0, 2)  # Đoạn có head.
sample.check_invariants()
assert sample.values() == [30, 40, 10, 20, 50]

sample.reverse_range(2, 4)  # Đoạn có tail.
sample.check_invariants()
assert sample.values() == [30, 40, 50, 20, 10]
assert sample.tail.value == 10

sample.reverse_range(0, 0)  # Một nút: thứ tự không đổi.
sample.check_invariants()
assert sample.values() == [30, 40, 50, 20, 10]

try:
    sample.reverse_range(3, 5)
except IndexError:
    pass
else:
    raise AssertionError("Thiếu lỗi chỉ số ngoài phạm vi")
~~~

**Chi phí:** Phải đi từ đầu đến trước vị trí left (O(left)) và đảo right − left + 1 nút. Tổng thời gian **Θ(right + 1)** cho đoạn hợp lệ trong cách cài đặt này, trường hợp xấu nhất Θ(n), bộ nhớ phụ O(1).

## 10. Danh sách đôi: hoán đổi prev và next

Ở danh sách liên kết đôi tuyến tính, mỗi nút lưu hai tham chiếu **prev** và **next**. Để đảo thứ tự, có thể **hoán đổi prev và next của từng nút**, sau đó hoán đổi head và tail.

~~~text
Trước:
head                            tail
 │                               │
 ▼                               ▼
A ⇄ B ⇄ C

A.prev = None, A.next = B
B.prev = A,    B.next = C
C.prev = B,    C.next = None

Sau:
head                            tail
 │                               │
 ▼                               ▼
C ⇄ B ⇄ A

C.prev = None, C.next = B
B.prev = C,    B.next = A
A.prev = B,    A.next = None
~~~

### Cần lưu next cũ trước khi hoán đổi

Đoạn sai:

~~~python
current.prev, current.next = current.next, current.prev
current = current.next   # Đã là prev cũ, không phải next cũ.
~~~

Đoạn đúng:

~~~python
old_next = current.next
current.prev, current.next = current.next, current.prev
current = old_next
~~~

Để cài đặt đầy đủ với Python 3.10 trở lên:

~~~python
from __future__ import annotations


class DNode:
    def __init__(self, value: int):
        self.value = value
        self.prev: DNode | None = None
        self.next: DNode | None = None


class DoublyLinkedList:
    def __init__(self):
        self.head: DNode | None = None
        self.tail: DNode | None = None
        self.size = 0

    def append(self, value: int) -> DNode:
        node = DNode(value)
        node.prev = self.tail
        if self.tail is None:
            self.head = node
        else:
            self.tail.next = node
        self.tail = node
        self.size += 1
        return node

    def reverse(self) -> None:
        current = self.head
        while current is not None:
            old_next = current.next
            current.prev, current.next = current.next, current.prev
            current = old_next

        self.head, self.tail = self.tail, self.head

    def values_forward(self) -> list[int]:
        values = []
        current = self.head
        while current is not None:
            values.append(current.value)
            current = current.next
        return values

    def values_backward(self) -> list[int]:
        values = []
        current = self.tail
        while current is not None:
            values.append(current.value)
            current = current.prev
        return values

    def check_invariants(self) -> None:
        if self.size == 0:
            assert self.head is None and self.tail is None
            return

        assert self.head is not None and self.tail is not None
        assert self.head.prev is None and self.tail.next is None

        current = self.head
        previous = None
        seen = set()
        count = 0
        while current is not None:
            assert id(current) not in seen, "Có chu trình"
            seen.add(id(current))
            assert current.prev is previous
            if previous is not None:
                assert previous.next is current
            previous = current
            current = current.next
            count += 1

        assert previous is self.tail and count == self.size

        current = self.tail
        following = None
        backward_count = 0
        while current is not None:
            assert current.next is following
            following = current
            current = current.prev
            backward_count += 1
            assert backward_count <= self.size
        assert following is self.head
        assert backward_count == self.size


double = DoublyLinkedList()
double.reverse()
double.check_invariants()

a = double.append(1)
b = double.append(2)
c = double.append(3)

double.reverse()
double.check_invariants()
assert double.values_forward() == [3, 2, 1]
assert double.values_backward() == [1, 2, 3]
assert double.head is c and double.tail is a
assert c.prev is None and a.next is None
assert a.prev is b and b.next is a

double.reverse()
double.check_invariants()
assert double.values_forward() == [1, 2, 3]
~~~

Danh sách đôi đảo tại chỗ mất **Θ(n)** thời gian, O(1) bộ nhớ phụ, vì mỗi nút chỉ cần một phép lưu next cũ và một lần hoán đổi prev/next.

## 11. Đảo danh sách vòng: điều kiện dừng khác

Một **danh sách vòng** hợp lệ không có điểm kết thúc None trong chuỗi liên kết khi không rỗng. Do vậy, dùng nguyên vòng lặp của danh sách đơn tuyến tính có thể khiến chương trình không kết thúc.

### 11.1. Vòng đơn có head, tail và size

Giả sử A → B → C → A, với head = A, tail = C, size = 3. Sau đảo cần C → B → A → C, với head = C và tail = A.

Có thể đảo đúng **size liên kết**, khởi tạo previous bằng **tail cũ** để duy trì đường khép vòng:

~~~python
def reverse_circular_singly(self) -> None:
    if self.size <= 1:
        return

    old_head = self.head
    old_tail = self.tail
    previous = old_tail
    current = old_head

    for _ in range(self.size):
        next_node = current.next
        current.next = previous
        previous = current
        current = next_node

    self.head = old_tail
    self.tail = old_head
    # Bất biến sau đảo: self.tail.next is self.head.
~~~

Sau đúng n bước, các liên kết được đảo và tail mới.next phải trỏ về head mới. Phương thức trên giả định head, tail, size của vòng đơn **ban đầu đều hợp lệ**. Với n = 1, nút duy nhất vẫn có next trỏ về chính nó nên không cần thay đổi.

Nếu không lưu size, có thể giữ **start = head cũ**, đi theo các liên kết cũ đã lưu và dừng sau khi quay về start, nhưng phải cẩn thận với trường hợp một nút và thứ tự kiểm tra điểm dừng.

### 11.2. Vòng đôi

Với danh sách vòng đôi hợp lệ, thay prev/next của mỗi nút rồi hoán đổi head/tail, nhưng phải đi **đúng size nút** thay vì chờ None:

~~~python
def reverse_circular_doubly(self) -> None:
    current = self.head

    for _ in range(self.size):
        old_next = current.next
        current.next, current.prev = current.prev, current.next
        current = old_next

    self.head, self.tail = self.tail, self.head
~~~

Khi không rỗng, các bất biến vẫn là:

~~~text
tail.next is head
head.prev is tail
x.next.prev is x, x.prev.next is x
~~~

Nếu danh sách có **sentinel vòng**, sentinel là nút cấu trúc đặc biệt, không phải dữ liệu. Thuật toán phải tính đúng cách duyệt hoặc cập nhật liên kết liên quan tới sentinel; không nên áp dụng máy móc phiên bản head/tail không sentinel vào cấu trúc đó.

**Điểm mấu chốt:** với danh sách vòng, điều kiện kết thúc phụ thuộc **độ dài chính xác hoặc việc quay về nút xuất phát**, không phải việc gặp None.

## 12. Độ phức tạp và đánh đổi

Giả sử đầu vào hợp lệ, không có chỉnh sửa đồng thời, và thao tác đọc/ghi tham chiếu là O(1).

| Phương án | Thời gian | Bộ nhớ phụ | Ghi chú |
| --- | --- | --- | --- |
| Đảo đơn bằng vòng lặp | **Θ(n)** | **O(1)** | Duyệt mỗi nút một lần. |
| Đảo đơn bằng đệ quy | **Θ(n)** | **Θ(n)** | Ngăn xếp đệ quy. |
| Đảo đoạn [left, right] | **Θ(right + 1)** | **O(1)** | Tìm đầu đoạn rồi đảo. |
| Đảo đôi bằng hoán đổi prev/next | **Θ(n)** | **O(1)** | Mỗi nút đổi hai tham chiếu. |
| Đảo vòng đơn, biết size | **Θ(n)** | **O(1)** | Phải giữ chu trình khép kín. |
| Đảo vòng đôi, biết size | **Θ(n)** | **O(1)** | Hoán đổi hướng trong một vòng. |
| Tạo chuỗi mới theo thứ tự đảo | **Θ(n)** | **O(n)** | Cần nút/kết quả mới. |
| Kiểm tra bất biến bằng tập visited | **Θ(n)** | **O(n)** | Chỉ dùng khi kiểm thử. |

Một lượt đảo tại chỗ phải đọc và cập nhật các liên kết của n nút, nên Θ(n) là chi phí tự nhiên. **O(1) bộ nhớ phụ** không nghĩa là không dùng biến; nó nghĩa là số biến tạm không tăng theo n.

Nếu người gọi cần **giữ nguyên chuỗi gốc**, thay vì sửa tại chỗ có thể tạo một danh sách mới theo thứ tự đảo. Phương án ấy tốn O(n) bộ nhớ nhưng không làm các tham chiếu next/prev trong danh sách gốc thay đổi.

**Không nhầm chi phí thao tác và chi phí kiểm chứng:** Nếu gọi check_invariants sau mỗi phép đảo, thời gian tổng vẫn Θ(n) nhưng bộ nhớ phụ khi kiểm tra sẽ là O(n). Nếu một API yêu cầu bảo đảm mạnh hơn như xác minh toàn bộ nút trước khi cập nhật, phải cộng chi phí của các kiểm tra đó.

## 13. An toàn liên kết không đồng nghĩa an toàn đa luồng

Trong bài này, “cập nhật an toàn” nghĩa là **không mất nút, không tạo chu trình ngoài ý muốn, giữ đúng head/tail/size và bất biến khi thao tác kết thúc**. Điều đó **không bảo đảm tính nguyên tử** (*atomicity*) hoặc an toàn khi nhiều tác vụ cùng truy cập cấu trúc.

### 13.1. Trạng thái trung gian

Trong khi reverse chạy:

- Một số nút đã có next đảo chiều, các nút còn lại vẫn theo hướng cũ.
- Head và tail thường chỉ được cập nhật sau vòng lặp.
- Một iterator đang duyệt từ một nút cũ có thể bỏ sót nút hoặc đọc sai thứ tự.
- Nếu có luồng khác sửa liên kết đồng thời, những tham chiếu được lưu có thể không còn phản ánh cấu trúc như dự kiến.

Vì vậy, với dữ liệu chia sẻ giữa nhiều luồng, cần cơ chế đồng bộ phù hợp. Không nên gọi reverse đồng thời với thao tác append, remove hoặc duyệt nếu API không có quy tắc rõ ràng.

### 13.2. Ngoại lệ và khả năng khôi phục

Ở các lớp nút Python đơn giản, phép gán trường next/prev là thao tác trực tiếp. Tuy nhiên, với lớp tùy biến có thuộc tính đặc biệt, hooks, ràng buộc hoặc thao tác kèm theo, một lỗi trong lúc đảo có thể để lại cấu trúc nối dở.

Nếu hệ thống cần **bảo đảm giao dịch**, có thể cần khóa, kiểm tra tiền điều kiện, cơ chế rollback hoặc dựng cấu trúc mới rồi mới thay tham chiếu công khai. Các giải pháp này có chi phí bổ sung và không tự có trong thuật toán đảo vòng lặp cơ bản.

### 13.3. Tham chiếu từ bên ngoài

Một biến **saved_node** trỏ tới nút A vẫn trỏ tới A sau khi đảo. Nhưng thuộc tính **A.next** đã thay đổi. Nếu một thành phần lưu vị trí k, iterator đang chạy hoặc cache ánh xạ vị trí tới nút, metadata đó có thể không còn phù hợp sau đảo.

Do vậy, hãy xác định rõ API hứa hẹn điều gì về **danh tính nút, thứ tự, iterator và quyền chỉnh sửa đồng thời** trước khi cho phép đảo tại chỗ.

## 14. Các lỗi thường gặp

| Sai sót | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Ghi đè current.next trước khi lưu next cũ | Mất đường tới phần chưa xử lý. | Lưu **next_node = current.next** đầu tiên. |
| Sau khi đổi next, dùng current = current.next để đi tiếp | Đi về đoạn đã đảo, không tới nút chưa xử lý. | Dùng next_node đã lưu. |
| Sau đảo chỉ đổi head, không đổi tail | Tail sai; append sau đó có thể hỏng danh sách. | Lưu old_head và đặt tail = old_head. |
| Tăng/giảm size trong reverse | Size không bằng số nút thực tế. | Giữ nguyên size. |
| Trong danh sách đôi chỉ sửa next | Prev không đối ứng, duyệt ngược sai. | Hoán đổi cả prev và next. |
| Trong danh sách đôi đi theo next mới | Quay về nút đã xử lý hoặc bỏ nút. | Lưu old_next trước khi đổi prev/next. |
| Đảo đoạn mà quên nối segment_tail.next = after | Mất phần đuôi ở ngoài đoạn. | Nối cả hai biên của đoạn đảo. |
| Đảo đoạn có tail mà không cập nhật tail | Biến tail sai. | Nếu right = size − 1, tail = segment_tail. |
| Dùng thuật toán dừng ở None trên danh sách vòng | Có thể lặp vô hạn. | Duyệt đúng size bước hoặc dừng khi quay về start. |
| Đảo vòng đơn với previous = None | Không giữ liên kết khép vòng. | Với thuật toán n bước, khởi tạo previous = tail cũ. |
| Đảo cấu trúc có chu trình lỗi bằng mã tuyến tính | Không có điểm dừng chính xác. | Xác định biến thể và kiểm tra bất biến. |
| Duyệt đồng thời khi một luồng khác đang đảo | Có thể bỏ sót hoặc xử lý lại nút. | Đồng bộ hoặc tránh chỉnh sửa xen kẽ. |
| Tưởng đệ quy là O(1) bộ nhớ vì không tạo nút mới | Bỏ qua bộ nhớ khung lời gọi. | Đệ quy dùng Θ(n) ngăn xếp. |
| Chỉ so sánh giá trị sau đảo | Không phát hiện nút bị sao chép/thay thế ngoài ý muốn. | Kiểm tra danh tính nút khi cần. |

Một quy trình gỡ lỗi hữu ích: thử danh sách có **0, 1, 2, 3 nút**, ghi từng giá trị previous/current/next_node, duyệt từ head đến None sau khi đảo, kiểm tra số nút và xác nhận **tail.next is None**. Với danh sách đôi, kiểm tra cả liên kết prev theo hướng ngược.

## 15. Bài tập tự luyện có đáp án

**Bài 1 — Điền mã.** Hoàn thành:

~~~python
previous = None
current = head
while current is not None:
    # (1)
    current.next = previous
    previous = current
    # (2)
~~~

*Đáp án:* (1) **next_node = current.next**; (2) **current = next_node**.

**Bài 2 — Mô phỏng hai lượt.** Cho A → B → C → D. Sau hai lượt đảo vòng lặp, đoạn đã đảo và chưa xử lý là gì?

*Đáp án:* **B → A → None** là đoạn đã đảo (previous chỉ B); **C → D → None** là đoạn chưa xử lý (current chỉ C).

**Bài 3 — Head và tail.** Với 1 → 2 → 3, head cũ chỉ nút 1 và tail cũ chỉ nút 3. Sau đảo, head/tail/size là gì?

*Đáp án:* Head chỉ nút 3, tail chỉ nút 1, size vẫn bằng 3.

**Bài 4 — Rỗng.** Gọi reverse trên danh sách rỗng có head = tail = None. Kết quả?

*Đáp án:* Không có lượt xử lý; head/tail tiếp tục None, size = 0.

**Bài 5 — Một nút.** Với nút X có next = None, reverse có làm thay đổi danh tính X hay size không?

*Đáp án:* Không. Head/tail vẫn cùng chỉ X, next vẫn None, size giữ nguyên 1.

**Bài 6 — Hai lần đảo.** Vì sao đảo liên kết hai lần cho lại thứ tự cũ?

*Đáp án:* Mỗi phép đảo đổi hướng mọi liên kết của chuỗi. Đảo thêm lần nữa đưa mỗi quan hệ kề trở lại hướng ban đầu; các nút vẫn là những đối tượng cũ.

**Bài 7 — Đệ quy.** Đảo đệ quy một danh sách n nút dùng bộ nhớ phụ bao nhiêu?

*Đáp án:* Θ(n) do ngăn xếp đệ quy, dù không tạo n nút dữ liệu mới.

**Bài 8 — Đảo đoạn.** Cho 10 → 20 → 30 → 40 → 50. Đảo [1, 3] với chỉ số từ 0 thu được gì?

*Đáp án:* **10 → 40 → 30 → 20 → 50**. Head và tail không đổi.

**Bài 9 — Đoạn chạm tail.** Cho A → B → C → D. Đảo đoạn [1, 3], tail mới là nút nào?

*Đáp án:* Chuỗi thành A → D → C → B; tail mới là **B**, nút đầu đoạn cũ.

**Bài 10 — Danh sách đôi.** Trong quá trình đảo A ⇄ B ⇄ C, vì sao phải lưu old_next?

*Đáp án:* Sau khi hoán đổi prev/next, next mới là prev cũ. old_next giữ lối tới nút tiếp theo theo hướng duyệt ban đầu.

**Bài 11 — Vòng đơn.** Cho A → B → C → A (head A, tail C, size 3). Nếu đảo đúng ba bước bằng thuật toán vòng, previous ban đầu là gì và hai đầu sau đảo là gì?

*Đáp án:* previous ban đầu là **tail cũ C**. Sau đảo, head = C, tail = A, chuỗi C → B → A → C.

**Bài 12 — Chi phí.** Một danh sách đơn có một triệu nút. Đảo vòng lặp có cần một triệu nút mới không, và chi phí là bao nhiêu?

*Đáp án:* Không; chỉ sửa các tham chiếu cũ. Thời gian Θ(n), bộ nhớ phụ O(1).

**Bài 13 — Tham chiếu ngoài.** Biến saved trỏ nút A của A → B → C. Sau reverse, saved có trỏ nút C không?

*Đáp án:* Không; saved vẫn chỉ **chính A**. A trở thành tail nên A.next bằng None.

**Bài 14 — Iterator.** Tại sao không nên duyệt bằng iterator cũ trong khi reverse đang chạy?

*Đáp án:* Các liên kết được cập nhật từng bước, nên iterator có thể thấy trạng thái trung gian và bỏ sót hoặc lặp nút. Cần quy tắc đồng bộ hoặc tránh chỉnh sửa trong khi duyệt.

**Ghi nhớ:** Đảo danh sách đơn an toàn có thứ tự **lưu next cũ → đảo current.next → cập nhật previous → đi tiếp bằng next đã lưu**. Khi kết thúc, **head mới = tail cũ**, **tail mới = head cũ**, **size không đổi**. Danh sách đôi cần hoán đổi prev/next của từng nút; danh sách vòng cần điều kiện dừng theo chu trình. Phiên bản vòng lặp tại chỗ đạt **Θ(n) thời gian và O(1) bộ nhớ phụ** khi các bất biến đầu vào đúng.

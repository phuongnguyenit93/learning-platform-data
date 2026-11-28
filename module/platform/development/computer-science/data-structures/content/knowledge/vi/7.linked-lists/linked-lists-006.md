# Danh sách đôi và liên kết hai chiều

**Danh sách liên kết đôi** (*doubly linked list*) là cấu trúc tuyến tính gồm các nút có thể đi theo cả hai hướng. Mỗi nút lưu dữ liệu cùng hai tham chiếu: **next** trỏ tới nút kế tiếp và **prev** trỏ tới nút đứng trước. Khác với danh sách liên kết đơn, danh sách đôi cho phép đi từ một nút đã biết đến hai nút lân cận mà không cần bắt đầu lại từ đầu.

Trong mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, chương **Danh sách liên kết** trang bị cách suy luận về bất biến, thao tác và độ phức tạp thời gian/bộ nhớ. Liên kết hai chiều đặc biệt hữu ích khi thường xuyên xóa một nút đã có tham chiếu, duyệt ngược, hoặc chèn ở hai phía của một nút. Đổi lại, cần lưu và duy trì **hai liên kết trên mỗi nút**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích ý nghĩa của **prev**, **next**, **head** và **tail** trong danh sách đôi.
- Vẽ đường liên kết xuôi và ngược; nhận diện trạng thái danh sách rỗng, một nút và nhiều nút.
- Phát biểu bất biến đối xứng giữa các nút kề nhau.
- Chèn đầu, thêm cuối, chèn trước hoặc sau một nút đã biết mà vẫn giữ liên kết hai chiều hợp lệ.
- Xóa đúng **đối tượng nút** đã biết trong O(1), kể cả nút đầu hoặc cuối, với tiền điều kiện nút thuộc danh sách.
- Cài đặt duyệt hai chiều, kiểm tra cấu trúc và phân tích chi phí thời gian/bộ nhớ.
- So sánh danh sách đôi với danh sách đơn và mảng động để lựa chọn cấu trúc phù hợp.

## 2. Một nút có hai liên kết

Trong danh sách đơn, một nút thường có dạng **[value | next]**. Danh sách đôi mở rộng thành **[prev | value | next]**.

Ví dụ ba nút lưu 10, 20, 30:

~~~text
head                                                   tail
 │                                                       │
 ▼                                                       ▼
None ← [None | 10 | •] ⇄ [• | 20 | •] ⇄ [• | 30 | None] → None
           A                 B                 C
~~~

Các mũi tên hai chiều trong sơ đồ là **hai liên kết riêng**, không phải một mũi tên “tự quay lại”:

- **A.next is B**, đồng thời **B.prev is A**.
- **B.next is C**, đồng thời **C.prev is B**.
- **A.prev is None** vì A là nút đầu.
- **C.next is None** vì C là nút cuối.
- **head is A** và **tail is C**.

Ví dụ tạo ba nút trong Python:

~~~python
class Node:
    def __init__(self, value, prev=None, next_node=None):
        self.value = value
        self.prev = prev
        self.next = next_node

a = Node(10)
b = Node(20)
c = Node(30)

a.next = b
b.prev = a
b.next = c
c.prev = b

head = a
tail = c

assert head.next is b
assert b.prev is head
assert tail.prev is b
assert tail.next is None
~~~

**Điểm quan trọng:** prev và next lưu tham chiếu đến **đối tượng nút**, không phải vị trí số học hay bản sao giá trị. Hai nút có thể cùng chứa số 10 nhưng là hai đối tượng khác nhau.

Trong Python, tham chiếu được quản lý bởi ngôn ngữ; trong C/C++, prev và next thường là con trỏ. Những quy tắc nối liên kết vẫn tương tự nhưng C/C++ còn phải quản lý vòng đời bộ nhớ.

### Hai chiều không có nghĩa là vòng tròn

Trong **danh sách đôi tuyến tính** được sử dụng ở bài này, head.prev và tail.next đều là None. Nó khác **danh sách đôi vòng** (*circular doubly linked list*), trong đó đầu và cuối có thể nối trở lại nhau, và khác biến thể sử dụng **nút canh gác** (*sentinel/dummy node*).

Những cài đặt khác nhau có bất biến khác nhau. Không nên áp dụng quy tắc dừng ở None của danh sách tuyến tính cho một danh sách vòng nếu chưa điều chỉnh thuật toán.

## 3. Head, tail và ba trạng thái quan trọng

Một danh sách đôi thường quản lý:

- **head**: tham chiếu tới nút đầu tiên.
- **tail**: tham chiếu tới nút cuối cùng.
- **size**: số nút hiện có, nếu muốn đọc kích thước trong O(1).

| Trạng thái | head | tail | Liên kết biên | size |
| --- | --- | --- | --- | ---: |
| Rỗng | None | None | Không có nút | 0 |
| Một nút X | X | Cũng chính X | X.prev = None; X.next = None | 1 |
| Từ hai nút | Nút đầu | Nút cuối | head.prev = None; tail.next = None | ≥ 2 |

~~~text
Rỗng:
head = None
tail = None
size = 0

Một nút:
        head ─┐
              ▼
        [None | 7 | None]
              ▲
        tail ─┘
size = 1

Nhiều nút:
head ─► [None | A | •] ⇄ [• | B | •] ⇄ [• | C | None] ◄─ tail
size = 3
~~~

Nếu một nút lưu giá trị **None**, danh sách vẫn **không rỗng**. Kiểm tra rỗng dựa vào việc **head is None**, không dựa vào giá trị trong head.

## 4. Bất biến hai chiều

**Bất biến** là những điều phải đúng trước và sau mỗi thao tác hoàn tất. Danh sách đôi có thêm ràng buộc so với danh sách đơn: các liên kết giữa nút kề nhau phải **nhất quán theo cả hai hướng**.

Với một danh sách đôi tuyến tính không có nút canh gác:

1. **Trạng thái rỗng:** size bằng 0 khi và chỉ khi cả head và tail đều là None.
2. **Liên kết tại biên:** nếu không rỗng, **head.prev is None** và **tail.next is None**.
3. **Đối xứng theo chiều xuôi:** với mọi nút x có **x.next = y**, phải có **y.prev is x**.
4. **Đối xứng theo chiều ngược:** với mọi nút x có **x.prev = p**, phải có **p.next is x**.
5. **Khả năng đi tới:** duyệt từ head bằng next phải đến tail rồi None; duyệt từ tail bằng prev phải đến head rồi None.
6. **Không có chu trình ngoài ý muốn:** một nút không được xuất hiện lặp lại trong một lượt duyệt tuyến tính.
7. **Số lượng:** số nút khi duyệt xuôi và ngược đều bằng size.

Ví dụ liên kết bị hỏng:

~~~text
A.next ──► B
B.prev ──► C      (SAI nếu C không phải A)
~~~

Một lượt duyệt xuôi có thể vẫn đi qua A → B, nhưng đi ngược từ B lại sang C. Danh sách vì vậy không còn biểu diễn cùng một thứ tự ở hai hướng.

Một lỗi khác:

~~~text
A.next = B
B.prev = A
B.next = C
C.prev = A       (SAI; phải là B)
~~~

Muốn kiểm tra, hãy đối chiếu **cả x.next.prev is x và x.prev.next is x** cho các liên kết tồn tại. Chỉ xác nhận tail.next là None chưa đủ để kết luận danh sách hợp lệ.

Các bất biến phải đúng **khi thao tác kết thúc**. Trong lúc thực hiện một nhóm phép gán, cấu trúc có thể tạm thời chưa nhất quán. Nếu nhiều luồng cùng truy cập, cần đồng bộ thích hợp để không quan sát trạng thái đang cập nhật dở.

## 5. Duyệt theo chiều xuôi và chiều ngược

### 5.1. Duyệt xuôi từ head

~~~text
current ← head
while current khác None:
    xử lý current.value
    current ← current.next
~~~

Python:

~~~python
current = head
while current is not None:
    print(current.value)
    current = current.next
~~~

### 5.2. Duyệt ngược từ tail

~~~text
current ← tail
while current khác None:
    xử lý current.value
    current ← current.prev
~~~

Python:

~~~python
current = tail
while current is not None:
    print(current.value)
    current = current.prev
~~~

Với A ⇄ B ⇄ C, duyệt từ head theo next thu được **A, B, C**, còn duyệt từ tail theo prev thu được **C, B, A**.

Khi có n nút, một lượt duyệt đủ n nút mất **Θ(n)** thời gian và **O(1)** bộ nhớ phụ nếu chỉ dùng biến current. Khả năng duyệt ngược **không** đồng nghĩa với truy cập chỉ số bất kỳ trong O(1): muốn đến vị trí k vẫn phải đi từng bước từ một đầu.

### 5.3. Truy cập theo chỉ số từ đầu gần hơn

Giả sử đã biết size = n, chỉ số k hợp lệ từ 0 đến n − 1:

- Đi từ head cần **k** lần theo next.
- Đi từ tail cần **n − 1 − k** lần theo prev.

Chọn đầu gần vị trí k hơn giúp giảm số bước. Ví dụ n = 10, k = 8: đi từ tail chỉ cần **1 bước**, còn từ head cần 8 bước.

Với lựa chọn tối ưu đầu xuất phát, chi phí truy cập là **Θ(1 + min(k, n − 1 − k))**. Trong trường hợp xấu nhất (chỉ số gần giữa), chi phí vẫn là **Θ(n)**. Head và tail chỉ giúp các vị trí gần hai đầu được truy cập nhanh hơn.

## 6. Thêm nút ở hai đầu

### 6.1. Chèn đầu (prepend)

Trước:

~~~text
head ─► [None | B | •] ⇄ [• | C | None] ◄─ tail
~~~

Sau prepend(A):

~~~text
head ─► [None | A | •] ⇄ [• | B | •] ⇄ [• | C | None] ◄─ tail
~~~

Cần cập nhật **hai phía của liên kết mới**:

1. Tạo new chứa A, với **new.prev = None** và **new.next = head cũ**.
2. Nếu head cũ tồn tại, gán **head cũ.prev = new**.
3. Gán **head = new**.
4. Nếu danh sách trước đó rỗng, gán thêm **tail = new**.
5. Tăng size.

~~~python
def prepend(self, value):
    new = Node(value, next_node=self.head)

    if self.head is None:
        self.tail = new
    else:
        self.head.prev = new

    self.head = new
    self.size += 1
    return new
~~~

Một lỗi phổ biến là sửa **new.next** và **head** nhưng quên sửa **head cũ.prev**. Khi đó duyệt xuôi vẫn có thể đúng, nhưng từ head cũ không thể đi ngược tới new.

### 6.2. Thêm cuối (append)

Trước:

~~~text
head ─► [None | A | •] ⇄ [• | B | None] ◄─ tail
~~~

Sau append(C):

~~~text
head ─► [None | A | •] ⇄ [• | B | •] ⇄ [• | C | None] ◄─ tail
~~~

Các bước:

1. Tạo new với **new.prev = tail cũ**, **new.next = None**.
2. Nếu tail cũ tồn tại, gán **tail cũ.next = new**.
3. Gán **tail = new**.
4. Nếu danh sách trước đó rỗng, **head = new**.
5. Tăng size.

~~~python
def append(self, value):
    new = Node(value, prev=self.tail)

    if self.tail is None:
        self.head = new
    else:
        self.tail.next = new

    self.tail = new
    self.size += 1
    return new
~~~

Cả **prepend** và **append** đều mất **Θ(1)** khi có head và tail hợp lệ. Danh sách đôi lưu cả hai đầu nên nối ở hai phía không cần duyệt.

## 7. Chèn giữa hai nút: phải sửa bốn hướng tham chiếu

Giả sử A và B kề nhau: A.next là B, B.prev là A. Muốn đưa X vào giữa:

~~~text
Trước:
A ⇄ B

Sau:
A ⇄ X ⇄ B
~~~

Bốn quan hệ cần đúng sau chèn:

~~~text
X.prev = A
X.next = B
A.next = X
B.prev = X
~~~

Cần giữ tham chiếu tới **B cũ** trước khi thay A.next. Ví dụ:

~~~python
next_node = a.next             # B cũ
new = Node("X", prev=a, next_node=next_node)
a.next = new
next_node.prev = new
~~~

Kết quả là **A.next is X**, **X.prev is A**, **X.next is B**, **B.prev is X**.

Nếu gán **a.next = new** trước rồi mới lấy **next_node = a.next**, next_node sẽ là chính new, gây liên kết sai hoặc mất đường đi tới B.

### Chèn sau nút đã biết

Với **insert_after(anchor, value)**:

- Nếu anchor là tail, thao tác tương đương **append(value)**.
- Nếu anchor không phải tail, lưu nút **successor = anchor.next**, tạo new ở giữa anchor và successor, rồi nối lại cả hai hướng.

### Chèn trước nút đã biết

Với **insert_before(anchor, value)**:

- Nếu anchor là head, thao tác tương đương **prepend(value)**.
- Nếu anchor không phải head, lưu nút **predecessor = anchor.prev**, tạo new ở giữa predecessor và anchor, rồi nối lại cả hai hướng.

**Tiền điều kiện:** anchor phải là nút đang thuộc danh sách, không phải một nút bất kỳ có cùng giá trị. Nếu đã có tham chiếu hợp lệ tới anchor, mỗi phép chèn cần Θ(1) thời gian và O(1) bộ nhớ phụ ngoài một nút mới.

Nếu API phải **tìm anchor theo giá trị hoặc chỉ số** trước khi chèn, bước tìm có thể tốn Θ(n) trong trường hợp xấu nhất. Việc chèn liên kết nhanh không làm bước định vị trở nên nhanh hơn.

## 8. Xóa đúng nút đã biết: lợi thế của prev

Xét danh sách A ⇄ B ⇄ C, và đã có tham chiếu **target** tới nút B:

~~~text
Trước:
head ─► A ⇄ B ⇄ C ◄─ tail
               ▲
             target

Sau:
head ─► A ⇄ C ◄─ tail

B đã bị tách khỏi đường đi từ head.
~~~

Vì target có cả **prev** lẫn **next**, ta lấy được hai nút lân cận trực tiếp:

~~~python
left = target.prev      # A
right = target.next     # C

left.next = right
right.prev = left
target.prev = None
target.next = None
~~~

Không cần duyệt từ head để tìm nút đứng trước như trong danh sách đơn. Phép nối lại chỉ cập nhật số liên kết cố định nên mất **Θ(1)** nếu target thuộc danh sách và ta đã giữ tham chiếu của nó.

### Xử lý các vị trí biên

Khi target là **head**, target.prev là None: cần chuyển **head = target.next**; nếu có nút kế tiếp thì nút ấy có prev = None.

Khi target là **tail**, target.next là None: cần chuyển **tail = target.prev**; nếu có nút đứng trước thì nút ấy có next = None.

Khi danh sách chỉ có **một nút**, target vừa là head vừa là tail, nên sau khi xóa phải có **head = tail = None, size = 0**.

Cách viết thống nhất cho mọi trường hợp:

~~~python
def remove_node(self, target):
    # Tiền điều kiện: target là nút đang thuộc danh sách.
    left = target.prev
    right = target.next

    if left is None:
        self.head = right
    else:
        left.next = right

    if right is None:
        self.tail = left
    else:
        right.prev = left

    target.prev = None
    target.next = None
    self.size -= 1
    return target.value
~~~

Ở nhánh xóa head, **right.prev = None** vì biến left bằng None; ở nhánh xóa tail, **left.next = None** vì right bằng None. Cả hai nhánh kết hợp xử lý cả danh sách một nút.

**Đây là xóa theo danh tính nút:** target thực sự không còn nằm trên đường liên kết của danh sách. Trong Python, đối tượng target vẫn có thể tồn tại nếu biến ngoài còn tham chiếu đến nó. Việc gỡ nút khỏi danh sách và việc thu hồi bộ nhớ là hai khái niệm khác nhau.

### Giới hạn của tiền điều kiện

Hàm trên chỉ đúng nếu **target đang thuộc danh sách này** và cấu trúc ban đầu hợp lệ. Nếu truyền nút ngoài danh sách hoặc đã bị gỡ, hàm có thể làm sai head/tail/size. Việc xác minh tư cách thành viên bằng cách duyệt toàn bộ thường tốn **O(n)**; một thiết kế khác có thể lưu thông tin sở hữu nút để kiểm tra nhanh hơn nhưng làm tăng metadata và các nghĩa vụ cập nhật.

Do đó, phát biểu **“xóa nút đã biết trong O(1)”** áp dụng cho **tham chiếu nút hợp lệ và không tính bước tìm/kiểm chứng**. Nếu chỉ biết giá trị cần xóa, tìm kiếm tuyến tính vẫn có chi phí O(n).

## 9. Cài đặt Python đầy đủ

Đoạn mã dưới đây chạy với **Python 3.10 trở lên**, quản lý head/tail/size, cho phép chèn và xóa hai chiều. Các phương thức nhận nút (**insert_after**, **insert_before**, **remove_node**) yêu cầu nút đang thuộc chính danh sách này; ví dụ chỉ truyền các tham chiếu trả về từ phương thức của danh sách.

~~~python
from __future__ import annotations


class Node:
    def __init__(
        self,
        value: int,
        prev: Node | None = None,
        next_node: Node | None = None,
    ) -> None:
        self.value = value
        self.prev = prev
        self.next = next_node


class DoublyLinkedList:
    def __init__(self) -> None:
        self.head: Node | None = None
        self.tail: Node | None = None
        self.size = 0

    def prepend(self, value: int) -> Node:
        new = Node(value, next_node=self.head)
        if self.head is None:
            self.tail = new
        else:
            self.head.prev = new
        self.head = new
        self.size += 1
        return new

    def append(self, value: int) -> Node:
        new = Node(value, prev=self.tail)
        if self.tail is None:
            self.head = new
        else:
            self.tail.next = new
        self.tail = new
        self.size += 1
        return new

    def insert_after(self, anchor: Node, value: int) -> Node:
        # Tiền điều kiện: anchor thuộc danh sách hiện tại.
        if anchor is self.tail:
            return self.append(value)

        successor = anchor.next
        assert successor is not None  # Anchor hợp lệ và chưa phải tail.
        new = Node(value, prev=anchor, next_node=successor)
        anchor.next = new
        successor.prev = new
        self.size += 1
        return new

    def insert_before(self, anchor: Node, value: int) -> Node:
        # Tiền điều kiện: anchor thuộc danh sách hiện tại.
        if anchor is self.head:
            return self.prepend(value)

        predecessor = anchor.prev
        assert predecessor is not None  # Anchor hợp lệ và chưa phải head.
        new = Node(value, prev=predecessor, next_node=anchor)
        predecessor.next = new
        anchor.prev = new
        self.size += 1
        return new

    def remove_node(self, target: Node) -> int:
        # Tiền điều kiện: target thuộc danh sách hiện tại.
        left = target.prev
        right = target.next

        if left is None:
            self.head = right
        else:
            left.next = right

        if right is None:
            self.tail = left
        else:
            right.prev = left

        target.prev = None
        target.next = None
        self.size -= 1
        return target.value

    def pop_front(self) -> int:
        if self.head is None:
            raise IndexError("Danh sách rỗng")
        return self.remove_node(self.head)

    def pop_back(self) -> int:
        if self.tail is None:
            raise IndexError("Danh sách rỗng")
        return self.remove_node(self.tail)

    def get_node(self, index: int) -> Node:
        if index < 0 or index >= self.size:
            raise IndexError("Chỉ số ngoài phạm vi")

        if index <= (self.size - 1 - index):
            current = self.head
            for _ in range(index):
                current = current.next
        else:
            current = self.tail
            for _ in range(self.size - 1 - index):
                current = current.prev

        assert current is not None
        return current

    def values_forward(self) -> list[int]:
        result = []
        current = self.head
        while current is not None:
            result.append(current.value)
            current = current.next
        return result

    def values_backward(self) -> list[int]:
        result = []
        current = self.tail
        while current is not None:
            result.append(current.value)
            current = current.prev
        return result

    def check_invariants(self) -> None:
        # Dùng khi học và gỡ lỗi; không tính vào chi phí thao tác cơ bản.
        if self.size == 0:
            assert self.head is None and self.tail is None
            return

        assert self.head is not None and self.tail is not None
        assert self.head.prev is None
        assert self.tail.next is None

        seen = set()
        current = self.head
        previous = None
        count = 0

        while current is not None:
            assert id(current) not in seen, "Chu trình theo next"
            seen.add(id(current))
            assert current.prev is previous, "Liên kết prev sai"
            if previous is not None:
                assert previous.next is current, "Liên kết next sai"
            previous = current
            current = current.next
            count += 1

        assert previous is self.tail
        assert count == self.size

        current = self.tail
        following = None
        reverse_count = 0
        while current is not None:
            assert current.next is following, "Liên kết ngược sai"
            following = current
            current = current.prev
            reverse_count += 1
            assert reverse_count <= self.size, "Chu trình theo prev"

        assert following is self.head
        assert reverse_count == self.size


items = DoublyLinkedList()
items.check_invariants()  # 0 nút

n20 = items.append(20)
items.check_invariants()
assert items.head is n20 and items.tail is n20

n10 = items.prepend(10)
n40 = items.append(40)
n30 = items.insert_after(n20, 30)
n35 = items.insert_before(n40, 35)

items.check_invariants()
assert items.values_forward() == [10, 20, 30, 35, 40]
assert items.values_backward() == [40, 35, 30, 20, 10]
assert items.get_node(0) is n10
assert items.get_node(4) is n40
assert items.get_node(2) is n30
assert items.size == 5

# Xóa đúng nút ở giữa, giữ các nút lân cận nối nhau.
assert items.remove_node(n30) == 30
items.check_invariants()
assert items.values_forward() == [10, 20, 35, 40]
assert n30.prev is None and n30.next is None

# Xóa đầu và cuối đều O(1) khi có head/tail.
assert items.pop_front() == 10
assert items.pop_back() == 40
items.check_invariants()
assert items.values_forward() == [20, 35]
assert items.values_backward() == [35, 20]

# Xóa tới khi rỗng.
assert items.remove_node(n35) == 35
assert items.remove_node(n20) == 20
items.check_invariants()
assert items.head is None and items.tail is None
assert items.size == 0

try:
    items.pop_back()
except IndexError:
    pass
else:
    raise AssertionError("Cần báo IndexError khi rỗng")
~~~

Trong **check_invariants**, chương trình duyệt cả hai chiều để đối chiếu cấu trúc và dùng tập **seen** nhằm phát hiện chu trình. Hàm này mất **O(n)** thời gian và **O(n)** bộ nhớ phụ. Nó phục vụ kiểm chứng; không nên tính nó vào thời gian O(1) của các phép chèn/xóa cơ bản.

**Lưu ý về alias:** sau khi gọi remove_node(n30), biến n30 vẫn tham chiếu tới đối tượng nút đã bị gỡ, dù nó không còn trên đường đi từ head. Trong ví dụ, việc đặt n30.prev và n30.next về None giúp tách các liên kết của đối tượng cũ. Không gọi remove_node lần nữa trên nút đã bị gỡ.

## 10. Độ phức tạp và đánh đổi

Giả sử danh sách đôi có n nút, head/tail/size hợp lệ và các thao tác cơ bản trên tham chiếu/cấp phát nút được xem có chi phí hằng số.

| Thao tác | Thời gian | Bộ nhớ phụ | Điều kiện |
| --- | --- | --- | --- |
| Đọc head hoặc tail | **Θ(1)** | O(1) | Có tham chiếu hai đầu. |
| Đi một bước next hoặc prev | **Θ(1)** | O(1) | Đang ở nút hợp lệ. |
| Duyệt hết theo một chiều | **Θ(n)** | O(1) | Không tạo mảng kết quả. |
| Đọc chỉ số k từ đầu gần hơn | **Θ(1 + min(k, n − 1 − k))** | O(1) | 0 ≤ k < n; biết size. |
| Chèn đầu / thêm cuối | **Θ(1)** | O(1) | Chỉ cập nhật vài tham chiếu. |
| Chèn trước/sau nút đã biết | **Θ(1)** | O(1) | Nút anchor thuộc danh sách. |
| Xóa nút đã biết | **Θ(1)** | O(1) | Nút target thuộc danh sách. |
| Xóa đầu / xóa cuối | **Θ(1)** | O(1) | Có head/tail, xử lý rỗng. |
| Tìm nút theo giá trị rồi xóa | **O(n)** | O(1) | Bước tìm có thể duyệt hết. |
| Tạo list kết quả từ mọi nút | **Θ(n)** | O(n) | Phải chứa n giá trị kết quả. |
| Kiểm tra bất biến kèm tập phát hiện chu trình | **Θ(n)** | O(n) | Phục vụ kiểm thử/gỡ lỗi. |

**Bộ nhớ:** một danh sách đôi n nút sử dụng **O(n)** không gian nhưng mỗi nút lưu **hai tham chiếu** thay vì một như danh sách đơn. Cấu trúc thêm head/tail/size chỉ chiếm O(1) bộ nhớ. Tổng bộ nhớ có thể lớn hơn danh sách đơn do một liên kết bổ sung và chi phí cấp phát đối tượng.

### So sánh với các cấu trúc khác

| Tiêu chí | Danh sách đơn | Danh sách đôi | Mảng động |
| --- | --- | --- | --- |
| Liên kết mỗi nút | next | prev + next | Không cần liên kết theo nút |
| Duyệt ngược trực tiếp | Không, thường phải có cách xử lý bổ sung | Có, từ tail bằng prev | Có, bằng chỉ số |
| Chèn/xóa ở đầu | O(1) | O(1) | Chèn/xóa đầu thường O(n) |
| Thêm cuối với tail | O(1) | O(1) | Thêm cuối thường O(1) trung bình khấu hao |
| Xóa cuối với tail | O(n) nếu cần tìm nút trước | O(1) | O(1) khi bỏ phần tử cuối |
| Xóa đúng nút đã có tham chiếu | Thường cần biết nút đứng trước | O(1) với target hợp lệ | Thường phải xác định vị trí và dịch phần tử |
| Đọc vị trí ngẫu nhiên | O(n) xấu nhất | O(n) xấu nhất | O(1) |

**Lưu ý:** Chi phí “xóa đúng nút đã có tham chiếu” của danh sách đôi O(1) không bao gồm tìm nút hoặc kiểm tra tư cách thành viên. Với danh sách đơn, nếu đã có **nút đứng trước**, xóa nút sau đó cũng là O(1).

Không nên chọn danh sách đôi chỉ vì khả năng xóa O(1) nếu ứng dụng thường xuyên phải tìm nút qua một lượt duyệt O(n) hoặc yêu cầu truy cập chỉ số ngẫu nhiên. Khi đó mảng động hoặc cấu trúc khác có thể phù hợp hơn.

## 11. Ứng dụng thực tế

**Lịch sử điều hướng:** một con trỏ current đang chỉ trang hiện tại có thể đi về trang trước qua **prev**, sang trang sau qua **next**. Nếu người dùng truy cập trang mới sau khi quay lại, hệ thống có thể cần bỏ nhánh lịch sử phía sau; cấu trúc hai chiều giúp xác định các nút lân cận, dù quy tắc ứng dụng cần được triển khai riêng.

**Bộ đệm LRU (Least Recently Used):** khi kết hợp **bảng băm** ánh xạ khóa tới nút với **danh sách đôi**, có thể tìm nút theo khóa trong O(1) *trung bình* đối với bảng băm, rồi gỡ và đưa nút ấy lên đầu danh sách trong O(1). Nút ít được dùng gần đây nhất thường nằm ở cuối và có thể bị gỡ nhanh. Nếu chỉ dùng danh sách đôi mà không có bảng băm, tìm theo khóa vẫn có thể mất O(n).

**Danh sách tác vụ có thay đổi vị trí:** nếu hệ thống giữ tham chiếu tới nút tác vụ đang được chọn, có thể di chuyển hoặc xóa tác vụ đó bằng việc cập nhật các liên kết ở hai phía. Điều này hữu ích khi vị trí quan trọng hơn chỉ số số học.

## 12. Lỗi thường gặp khi cập nhật liên kết

| Sai sót | Hệ quả | Cách tránh |
| --- | --- | --- |
| Chèn giữa nhưng chỉ sửa A.next | B.prev vẫn chỉ A, đi ngược bỏ qua X. | Sửa đủ X.prev, X.next, A.next, B.prev. |
| Chèn đầu nhưng quên head cũ.prev | Duyệt xuôi đúng, duyệt ngược sai. | Cập nhật head cũ.prev trước khi đổi head. |
| Thêm cuối nhưng quên tail cũ.next | Nút mới không đi tới được từ head. | Nối tail cũ.next trước khi chuyển tail. |
| Xóa giữa nhưng chỉ sửa left.next | right.prev vẫn trỏ vào target bị gỡ. | Sửa cả left.next và right.prev. |
| Xóa đầu/cuối nhưng quên cập nhật head/tail | Biến đầu/cuối chỉ nút sai. | Kiểm tra left/right có None trong remove_node. |
| Xóa nút duy nhất nhưng giữ một trong hai đầu | Danh sách rỗng có tham chiếu lỗi thời. | Đưa cả head và tail về None. |
| Không giảm/tăng size khi thay đổi | size không khớp số nút thực tế. | Mỗi lần chèn tăng 1, mỗi lần xóa thành công giảm 1. |
| Truyền nút ngoài danh sách vào remove_node | Có thể làm hỏng cấu trúc và size. | Bảo đảm tiền điều kiện; thêm cơ chế kiểm chứng nếu API công khai yêu cầu. |
| Nhầm giá trị giống nhau với cùng một nút | Xóa hoặc chèn sai đối tượng. | So sánh tham chiếu đối tượng bằng **is** khi xác định nút. |
| Áp dụng thuật toán dừng ở None cho danh sách vòng | Có thể lặp vô hạn. | Xác định biến thể danh sách và điểm dừng tương ứng. |

Để gỡ lỗi, hãy duyệt **từ head theo next** và **từ tail theo prev**. Hai lượt phải thấy cùng số nút theo thứ tự ngược nhau; ở mỗi cặp nút kề, kiểm tra liên kết đối xứng.

## 13. Bài tập vận dụng

**Bài 1 — Khôi phục liên kết.** Danh sách A ⇄ B cần chèn X ở giữa. Hãy liệt kê bốn phép gán tham chiếu để sau chèn được A ⇄ X ⇄ B.

*Đáp án:* **X.prev = A**, **X.next = B**, **A.next = X**, **B.prev = X**. Lưu B cũ trước khi thay A.next.

**Bài 2 — Chèn đầu vào danh sách rỗng.** Ban đầu head = tail = None, size = 0. Sau prepend(7), các bất biến nào phải đúng?

*Đáp án:* **head is tail**, cả hai trỏ vào một nút chứa 7; nút ấy có prev và next đều bằng None; size bằng 1.

**Bài 3 — Xóa nút giữa.** Danh sách A ⇄ B ⇄ C, target trỏ B. Sau xóa B, các liên kết nào thay đổi?

*Đáp án:* **A.next = C** và **C.prev = A**; size giảm 1. Head vẫn A, tail vẫn C; có thể tách B.prev và B.next về None.

**Bài 4 — Xóa tail.** Danh sách A ⇄ B ⇄ C với tail là C. Có thể xóa C mà không duyệt từ head không?

*Đáp án:* Có. **C.prev** trực tiếp là B; đặt **B.next = None**, **tail = B**, giảm size. Thao tác O(1) nếu đã có nút tail hợp lệ.

**Bài 5 — Kiểm tra bất biến.** Trong danh sách A → B → C theo chiều next, B.prev đúng là A nhưng C.prev lại chỉ A. Danh sách còn hợp lệ không?

*Đáp án:* Không. Vì **B.next is C** nên phải có **C.prev is B**. Liên kết ngược đang sai dù duyệt xuôi có thể vẫn đi tới C.

**Bài 6 — Chi phí theo vị trí.** Với danh sách đôi n = 10 nút, muốn đọc chỉ số k = 8, nên đi từ head hay tail? Phải thực hiện bao nhiêu bước qua liên kết?

*Đáp án:* Đi từ tail (chỉ số 9) lùi **1 bước** theo prev. Đi từ head sẽ cần 8 bước theo next.

**Bài 7 — Giá trị trùng nhau.** Danh sách có hai nút khác nhau cùng lưu giá trị 5. Nếu yêu cầu xóa nút 5 thứ hai, chỉ đưa **value = 5** cho hàm tìm kiếm có đủ xác định đối tượng cần xóa không?

*Đáp án:* Không. Hàm tìm có thể trả nút 5 đầu tiên. Cần xác định rõ lần xuất hiện hoặc giữ đúng tham chiếu tới nút thứ hai.

**Bài 8 — Lựa chọn cấu trúc.** Một bộ đệm thường xuyên loại bỏ phần tử cũ nhất và chuyển một phần tử vừa được truy cập lên đầu. Vì sao kết hợp bảng băm và danh sách đôi có ích?

*Đáp án:* Bảng băm giúp tra ra nút từ khóa với O(1) trung bình, trong khi danh sách đôi cho phép gỡ nút đã biết và đưa lên đầu bằng số phép gán cố định, O(1). Danh sách riêng lẻ vẫn phải duyệt tìm khóa.

**Ghi nhớ:** Hai liên kết **prev** và **next** phải nhất quán với nhau. Danh sách đôi hỗ trợ duyệt xuôi/ngược, chèn cạnh nút đã biết và xóa đúng nút đã biết trong **O(1)**, kể cả ở cuối. Lợi thế đó đi cùng chi phí lưu thêm tham chiếu và trách nhiệm cập nhật đủ hai chiều; truy cập theo chỉ số hoặc tìm theo giá trị vẫn có thể mất **O(n)**.

# Chèn, xóa một nút trong danh sách đôi khi đã có tham chiếu

Trong **danh sách liên kết đôi** (*doubly linked list*), mỗi nút chứa một giá trị cùng hai liên kết: **prev** trỏ đến nút trước và **next** trỏ đến nút sau. Khi chương trình **đã có tham chiếu hợp lệ tới một nút đang thuộc danh sách**, nó có thể chèn ngay trước/sau nút ấy hoặc xóa chính nút ấy bằng một số phép gán cố định.

Đây là lợi thế quan trọng của danh sách đôi so với danh sách liên kết đơn: để xóa một nút ở giữa, ta lấy được nút đứng trước trực tiếp từ **target.prev**, không phải đi từ **head** để tìm. Tuy vậy, phát biểu “chèn/xóa O(1)” có điều kiện: **phải có sẵn tham chiếu đúng**, và thao tác phải duy trì cả hai chiều liên kết.

Bài học thuộc chương **Danh sách liên kết** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Chủ đề này rèn cách xác định bất biến, sửa liên kết và phân tích độ phức tạp thời gian/bộ nhớ để lựa chọn cấu trúc phù hợp với từng bài toán.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **tham chiếu tới nút**, **giá trị chứa trong nút** và **chỉ số vị trí**.
- Trình bày điều kiện để chèn trước hoặc sau một nút đã biết trong **Θ(1)**.
- Xóa đúng đối tượng nút đã biết trong **Θ(1)** mà không làm mất những nút còn lại.
- Xử lý nhất quán trường hợp nút đầu, nút cuối, nút duy nhất và danh sách rỗng.
- Giải thích, vẽ và kiểm tra bất biến **x.next.prev is x** và **x.prev.next is x** khi các liên kết tương ứng tồn tại.
- Nhận biết giới hạn của tiền điều kiện “nút đang thuộc danh sách” và chi phí tìm hoặc kiểm chứng nút.
- Cài đặt các phép chèn/xóa bằng Python, kể cả di chuyển một nút đã biết đến đầu danh sách mà giữ nguyên danh tính đối tượng.

## 2. Điều kiện đầu vào và bất biến

Ta xét **danh sách đôi tuyến tính, không dùng nút canh gác**. Mỗi nút có ba thành phần:

~~~text
[ prev | value | next ]
~~~

Một chuỗi ba nút A, B, C được biểu diễn như sau:

~~~text
head                                                   tail
 │                                                       │
 ▼                                                       ▼
None ← [None | A | •] ⇄ [• | B | •] ⇄ [• | C | None] → None
~~~

Mỗi cặp nút kề nhau duy trì **hai liên kết đối ứng**:

~~~text
A.next is B     và     B.prev is A
B.next is C     và     C.prev is B
~~~

Danh sách quản lý **head** (nút đầu), **tail** (nút cuối) và **size** (số nút). Những bất biến cần đúng **trước và sau khi mỗi thao tác hoàn tất** gồm:

1. **Rỗng:** size = 0 khi và chỉ khi head và tail đều là None.
2. **Biên:** nếu không rỗng, **head.prev is None** và **tail.next is None**.
3. **Chiều xuôi:** với mọi nút x có nút kế tiếp y, **x.next is y** kéo theo **y.prev is x**.
4. **Chiều ngược:** với mọi nút x có nút trước p, **x.prev is p** kéo theo **p.next is x**.
5. **Tính liên thông:** duyệt theo next từ head gặp đủ size nút rồi kết thúc ở tail/None; duyệt theo prev từ tail cũng gặp chính các nút ấy theo thứ tự ngược.
6. **Không có chu trình ngoài ý muốn:** nút không được lặp lại trên đường duyệt tuyến tính.

Trong mô hình này, danh sách **một nút** phải có **head is tail**, và nút duy nhất có cả prev và next bằng None.

### Đã có tham chiếu nghĩa là gì?

Giả sử biến **anchor** đang chỉ đúng nút B trong sơ đồ. Ta có thể đọc **anchor.prev** để biết A và **anchor.next** để biết C. Không cần tìm B từ head; đây là tiền đề để thao tác chèn/xóa chỉ cần Θ(1).

**Cần phân biệt ba tình huống:**

| Dữ kiện đang có | Ý nghĩa | Chi phí thường gặp |
| --- | --- | --- |
| Có **tham chiếu tới đúng nút** B đang thuộc danh sách | Có thể đọc ngay B.prev, B.next | Chèn trước/sau B hoặc xóa B: Θ(1) |
| Chỉ biết **giá trị** của B | Phải tìm nút phù hợp; giá trị có thể trùng | Tìm từ head/tail có thể Θ(n) |
| Chỉ biết **chỉ số k** | Phải duyệt từ một đầu để định vị nút | Xấu nhất Θ(n) |

Việc nút có cùng giá trị không có nghĩa chúng là cùng đối tượng. Trong Python, toán tử **is** biểu thị cùng danh tính đối tượng; **==** có thể chỉ so sánh giá trị.

**Tiền điều kiện quan trọng:** Mọi thao tác nhận trực tiếp nút **anchor/target** ở bài này giả định nút đó đang thuộc **chính danh sách được thao tác**. Tham chiếu tới nút ngoài danh sách hoặc đã bị xóa không đáp ứng điều kiện, dù vẫn là một đối tượng Node hợp lệ.

## 3. Chèn ngay sau nút đã biết

Cho danh sách **A ⇄ B ⇄ C**, trong đó **anchor** trỏ tới B. Mục tiêu là chèn X ngay sau B:

~~~text
Trước:
head ──► A ⇄ B ⇄ C ◄── tail
               ▲
             anchor

Sau:
head ──► A ⇄ B ⇄ X ⇄ C ◄── tail
               ▲    ▲
             anchor  new
~~~

Gọi **right = anchor.next** để giữ tham chiếu tới C trước khi sửa liên kết. Cần tạo bốn quan hệ:

~~~text
new.prev    = anchor
new.next    = right
anchor.next = new
right.prev  = new
~~~

Với B ở giữa, bốn phép gán trên phục hồi chính xác hai cặp liên kết B ⇄ X và X ⇄ C. Ví dụ Python:

~~~python
right = anchor.next
new = Node(99)

new.prev = anchor
new.next = right
anchor.next = new
right.prev = new
~~~

**Thứ tự gán có ý nghĩa:** nếu thực hiện **anchor.next = new** rồi mới lấy **right = anchor.next**, right sẽ là chính new, không còn tham chiếu tới C cũ. Có thể tạo vòng tự trỏ hoặc làm mất phần đuôi.

### Khi anchor là tail

Lúc này **right is None**. Ta không thể truy cập **right.prev**; thay vào đó cần đặt **tail = new**:

~~~text
Trước:
head ──► A ⇄ B ◄── tail
               ▲
             anchor

Sau:
head ──► A ⇄ B ⇄ X ◄── tail
~~~

Các liên kết bắt buộc: **new.prev = B**, **new.next = None**, **B.next = new**, **tail = new**. Head giữ nguyên.

Cài đặt khái quát:

~~~python
def insert_after(self, anchor, value):
    # Tiền điều kiện: anchor thuộc danh sách này.
    right = anchor.next
    new = Node(value)

    new.prev = anchor
    new.next = right
    anchor.next = new

    if right is None:
        self.tail = new
    else:
        right.prev = new

    self.size += 1
    return new
~~~

Nếu danh sách chỉ có **một nút** và anchor là nút đó, thao tác tạo danh sách hai nút: head giữ nguyên, tail trở thành new. Không có anchor hợp lệ khi danh sách rỗng; trường hợp rỗng nên dùng thao tác **prepend** hoặc **append**.

**Thời gian:** Θ(1) khi anchor hợp lệ đã được cung cấp; tạo và nối đúng một nút cần O(1) bộ nhớ bổ sung.

## 4. Chèn ngay trước nút đã biết

Cho **A ⇄ B ⇄ C**, anchor chỉ B; cần chèn X **trước B**:

~~~text
Trước:
head ──► A ⇄ B ⇄ C ◄── tail
               ▲
             anchor

Sau:
head ──► A ⇄ X ⇄ B ⇄ C ◄── tail
            ▲    ▲
            new  anchor
~~~

Lưu **left = anchor.prev** (nút A), rồi cập nhật:

~~~text
new.prev    = left
new.next    = anchor
left.next   = new
anchor.prev = new
~~~

Khác với danh sách liên kết đơn, **anchor.prev** cho phép tìm nút đứng trước trong Θ(1). Không cần duyệt từ head.

### Khi anchor là head

Nếu anchor chính là head, **left is None**. Sau chèn phải đặt **head = new**, đồng thời:

~~~text
new.prev = None
new.next = anchor
anchor.prev = new
~~~

**Tail giữ nguyên** trừ khi danh sách được thiết kế với biến thể khác; trong trường hợp một nút, chèn trước nút duy nhất tạo hai nút và tail vẫn là nút cũ.

Phương thức chèn trước:

~~~python
def insert_before(self, anchor, value):
    # Tiền điều kiện: anchor thuộc danh sách này.
    left = anchor.prev
    new = Node(value)

    new.prev = left
    new.next = anchor
    anchor.prev = new

    if left is None:
        self.head = new
    else:
        left.next = new

    self.size += 1
    return new
~~~

Kết quả giữ đúng **head.prev is None** và mọi liên kết đối ứng. Đây là thao tác Θ(1) vì prev của anchor cung cấp trực tiếp nút trước.

## 5. Xóa đúng nút đã biết: remove_node

Trong danh sách đơn, muốn xóa **chính đối tượng B** ta thường cần nút A đứng trước để sửa A.next. Nếu chỉ có B, danh sách đơn không giúp tìm A trực tiếp. Trong danh sách đôi, B lưu **prev = A** và **next = C** nên có đủ thông tin để nối hai phía.

~~~text
Trước:
head ──► A ⇄ B ⇄ C ◄── tail
               ▲
             target

Sau:
head ──► A ⇄ C ◄── tail

B: prev = None, next = None (nếu tách hai liên kết cũ)
~~~

Lưu hai nút lân cận:

~~~python
left = target.prev
right = target.next
~~~

Sau đó nối **qua target**:

~~~text
left.next  = right
right.prev = left
~~~

Cuối cùng đặt target.prev và target.next về None để nút đã gỡ không còn giữ liên kết tới danh sách. **Size giảm đúng 1**.

Các phép gán này không sao chép giá trị của nút khác. **Đúng đối tượng target** được loại khỏi chuỗi từ head, nên nếu các nút lưu cùng một giá trị, ta vẫn loại bỏ đúng đối tượng được tham chiếu.

### Xóa ở biên: hai phía có thể là None

Khi target là **head**, left bằng None nên không thể gán left.next; thay bằng **head = right**. Nếu right tồn tại, phải sửa **right.prev = None**.

Khi target là **tail**, right bằng None nên không thể gán right.prev; thay bằng **tail = left**. Nếu left tồn tại, phải sửa **left.next = None**.

Khi danh sách chỉ có **một nút**, cả left và right đều là None; phải đưa **head = tail = None** và size về 0.

Mẫu thống nhất xử lý mọi vị trí:

~~~python
def remove_node(self, target):
    # Tiền điều kiện: target đang thuộc danh sách này.
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

Khi xóa đúng nút giữa, cả head và tail giữ nguyên. Khi xóa một đầu, chỉ cần sửa tham chiếu biên tương ứng. Khi xóa nút duy nhất, **cả hai đầu về None**.

**Chi phí:** remove_node là Θ(1) thời gian, O(1) bộ nhớ phụ khi target đã được biết và hợp lệ. Xóa cuối danh sách đôi với tail cũng là Θ(1): **tail.prev** cung cấp trực tiếp nút cuối mới.

## 6. Chứng minh vì sao phép nối đúng

Có thể kiểm tra sự đúng đắn bằng bất biến thay vì chỉ nhìn vào giá trị trả về.

### 6.1. Chèn X giữa A và B

**Trước:** A.next is B và B.prev is A.

**Sau:** đặt X.prev = A, X.next = B, A.next = X, B.prev = X. Khi đó:

- Liên kết A → X có chiều ngược X → A.
- Liên kết X → B có chiều ngược B → X.
- Các nút bên ngoài đoạn A, B không cần thay liên kết, vì vẫn đứng ở cùng vị trí tương đối.
- Nếu A hoặc B không tồn tại do chèn ở biên, thay liên kết còn thiếu bằng cập nhật head/tail tương ứng.
- Tăng size một lần vì có đúng một nút mới trên chuỗi.

Vì vậy danh sách vẫn liên tục từ head tới tail theo cả hai chiều, miễn là bất biến ban đầu và tiền điều kiện hợp lệ.

### 6.2. Gỡ B giữa A và C

**Trước:** A.next is B, B.prev is A, B.next is C, C.prev is B.

**Sau:** A.next = C và C.prev = A. Khi đó:

- Cặp nút A, C trở thành hai nút kề nhau có liên kết đối xứng.
- B không còn đường đi đến từ head qua A.
- Những nút khác giữ nguyên thứ tự.
- Nếu B là một đầu, gán head hoặc tail sang nút lân cận còn lại; nếu B là nút duy nhất, cả hai đầu thành None.
- Giảm size một lần vì chuỗi từ head chứa ít hơn đúng một nút.

**Bất biến không yêu cầu các giá trị khác nhau.** Chỉ cần các liên kết đối ứng trỏ đúng **đối tượng nút**.

## 7. Bảng trường hợp biên

| Thao tác | Vị trí hoặc trạng thái | Cập nhật cần chú ý |
| --- | --- | --- |
| Chèn sau anchor | Anchor ở giữa | Cập nhật anchor.next, new.prev/new.next và successor.prev. |
| Chèn sau anchor | Anchor là tail | Cập nhật **tail = new**; new.next = None. |
| Chèn trước anchor | Anchor ở giữa | Cập nhật predecessor.next, new.prev/new.next và anchor.prev. |
| Chèn trước anchor | Anchor là head | Cập nhật **head = new**; new.prev = None. |
| Chèn trước/sau | Danh sách chỉ có một nút | Head và tail sau chèn phải trỏ tới hai nút ở hai đầu. |
| Chèn trước/sau | Danh sách rỗng | Không có anchor hợp lệ; dùng prepend/append để tạo nút đầu tiên. |
| Xóa target | Nút giữa | Nối hai hàng xóm; head/tail giữ nguyên. |
| Xóa target | Head của danh sách nhiều nút | Head chuyển sang next; head mới.prev = None. |
| Xóa target | Tail của danh sách nhiều nút | Tail chuyển về prev; tail mới.next = None. |
| Xóa target | Nút duy nhất | Head = tail = None; size = 0. |
| Xóa target | Danh sách rỗng | Không có target hợp lệ; pop_front/pop_back có thể báo IndexError. |
| Xóa target | Target không thuộc danh sách | Không thỏa tiền điều kiện; tuyệt đối không cập nhật size một cách mù quáng. |

Một phép chèn **thành công** tăng size 1; một phép xóa **thành công** giảm size 1. Nếu thao tác thất bại trước khi sửa liên kết, trạng thái phải giữ nguyên.

## 8. Mã Python tự chứa: chèn, xóa và kiểm chứng

Ví dụ sau dùng **Python 3.10 trở lên**. Để tránh lặp logic, một hàm nội bộ **_link_between(left, right, new)** nối nút mới giữa hai nút kề nhau. Nó xử lý cả ranh giới đầu/cuối, bao gồm trường hợp danh sách rỗng.

**Tiền điều kiện của _link_between:** left và right là hai nút kề nhau trong danh sách, hoặc một trong hai là None tại biên tương ứng; new là nút mới chưa thuộc danh sách. Các phương thức nhận trực tiếp **anchor/target** cũng yêu cầu nút thuộc danh sách hiện tại.

~~~python
from __future__ import annotations


class Node:
    def __init__(self, value: int):
        self.value = value
        self.prev: Node | None = None
        self.next: Node | None = None


class DoublyLinkedList:
    def __init__(self):
        self.head: Node | None = None
        self.tail: Node | None = None
        self.size = 0

    def _link_between(
        self,
        left: Node | None,
        right: Node | None,
        new: Node,
    ) -> Node:
        """Nối nút mới vào một khoảng liên kết hợp lệ."""
        new.prev = left
        new.next = right

        if left is None:
            self.head = new
        else:
            left.next = new

        if right is None:
            self.tail = new
        else:
            right.prev = new

        self.size += 1
        return new

    def prepend(self, value: int) -> Node:
        return self._link_between(None, self.head, Node(value))

    def append(self, value: int) -> Node:
        return self._link_between(self.tail, None, Node(value))

    def insert_before(self, anchor: Node, value: int) -> Node:
        # Tiền điều kiện: anchor thuộc danh sách này.
        return self._link_between(anchor.prev, anchor, Node(value))

    def insert_after(self, anchor: Node, value: int) -> Node:
        # Tiền điều kiện: anchor thuộc danh sách này.
        return self._link_between(anchor, anchor.next, Node(value))

    def remove_node(self, target: Node) -> int:
        # Tiền điều kiện: target thuộc danh sách này.
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

    def move_to_front(self, node: Node) -> None:
        """Di chuyển nút đang thuộc danh sách lên đầu; size không đổi."""
        if node is self.head:
            return

        # Vì node thuộc danh sách nhưng không phải head,
        # nút đứng trước chắc chắn tồn tại.
        left = node.prev
        right = node.next
        assert left is not None

        # Gỡ node khỏi vị trí cũ, giữ phần còn lại nối liền.
        left.next = right
        if right is None:
            self.tail = left
        else:
            right.prev = left

        # Nối cùng đối tượng node lên trước head.
        first = self.head
        assert first is not None
        node.prev = None
        node.next = first
        first.prev = node
        self.head = node

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
        """Kiểm tra cấu trúc; dành cho học tập và gỡ lỗi."""
        if self.size == 0:
            assert self.head is None
            assert self.tail is None
            return

        assert self.head is not None and self.tail is not None
        assert self.head.prev is None
        assert self.tail.next is None

        current = self.head
        previous = None
        seen = set()
        count = 0

        while current is not None:
            assert id(current) not in seen, "Chu trình theo next"
            seen.add(id(current))
            assert current.prev is previous, "prev không đối ứng"
            if previous is not None:
                assert previous.next is current, "next không đối ứng"
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
items.check_invariants()

# Danh sách rỗng -> một nút.
n20 = items.append(20)
items.check_invariants()
assert items.head is n20 and items.tail is n20

# Chèn trước head, chèn sau tail và chèn giữa.
n10 = items.insert_before(n20, 10)
n30 = items.insert_after(n20, 30)
n15 = items.insert_after(n10, 15)
n25 = items.insert_before(n30, 25)
items.check_invariants()
assert items.values_forward() == [10, 15, 20, 25, 30]
assert items.values_backward() == [30, 25, 20, 15, 10]
assert items.head is n10 and items.tail is n30
assert items.size == 5

# Xóa đúng nút giữa theo danh tính, giữ các nút lân cận.
assert items.remove_node(n20) == 20
items.check_invariants()
assert items.values_forward() == [10, 15, 25, 30]
assert n20.prev is None and n20.next is None

# Xóa head và tail.
assert items.remove_node(n10) == 10
assert items.remove_node(n30) == 30
items.check_invariants()
assert items.values_forward() == [15, 25]
assert items.head is n15 and items.tail is n25

# Di chuyển đúng đối tượng nút đến đầu; không thêm/xóa nút.
items.move_to_front(n25)
items.check_invariants()
assert items.values_forward() == [25, 15]
assert items.head is n25 and items.tail is n15
assert items.size == 2

# Xóa tới danh sách rỗng.
assert items.pop_back() == 15
assert items.pop_front() == 25
items.check_invariants()
assert items.head is None and items.tail is None
assert items.size == 0

try:
    items.pop_front()
except IndexError:
    pass
else:
    raise AssertionError("Phải báo lỗi khi danh sách rỗng")

# Hai nút có cùng value vẫn là hai đối tượng khác nhau.
a = items.append(7)
b = items.append(7)
assert a is not b
assert items.remove_node(b) == 7
items.check_invariants()
assert items.head is a and items.tail is a
assert items.values_forward() == [7]
~~~

Ví dụ xác minh các đường đi quan trọng: từ rỗng sang một nút, chèn ở đầu/cuối/giữa, xóa từng vị trí, thay đổi thứ tự mà giữ danh tính nút, rồi quay về rỗng. Các lời gọi **check_invariants** là bước kiểm tra hỗ trợ học tập.

**Phân tích hàm kiểm tra:** check_invariants duyệt hai chiều và dùng một tập **seen** để theo dõi nút đã thăm, nên tốn **Θ(n)** thời gian và **O(n)** bộ nhớ phụ. Chi phí đó **không thuộc** các phép chèn/xóa Θ(1) nếu không chạy hàm kiểm tra sau mỗi thao tác.

## 9. Di chuyển nút đã biết mà không tạo nút mới

Đôi khi yêu cầu không phải chèn giá trị mới hay xóa hẳn nút, mà là **đưa một nút đang ở giữa/cuối lên đầu**. Ví dụ, bộ đệm LRU di chuyển nút của phần tử vừa sử dụng lên đầu danh sách để biểu thị mức độ gần đây.

Cho:

~~~text
head ──► A ⇄ B ⇄ C ⇄ D ◄── tail
                 ▲
                node
~~~

Muốn chuyển chính đối tượng C lên đầu:

~~~text
head ──► C ⇄ A ⇄ B ⇄ D ◄── tail
~~~

Thực hiện hai pha:

1. **Gỡ C khỏi vị trí cũ:** B.next = D, D.prev = B.
2. **Nối C lên trước head cũ:** C.prev = None, C.next = A, A.prev = C, head = C.

Độ dài danh sách **không đổi**, do đó size **không được tăng hay giảm**. Nếu C đang là tail, bước gỡ cũng phải cập nhật tail về B. Nếu C đã là head, không cần làm gì.

Phương thức **move_to_front** trong ví dụ thực hiện đúng hai pha đó. Nó duy trì **danh tính đối tượng** C, khác với cách tạo một nút mới chứa cùng dữ liệu rồi gỡ nút C cũ. Việc giữ danh tính đặc biệt quan trọng khi bảng băm hoặc các thành phần khác đang lưu tham chiếu tới nút.

**Chi phí:** Nếu đã có tham chiếu hợp lệ tới node, việc di chuyển lên đầu là Θ(1), vì số phép gán không phụ thuộc n. Nếu phải tìm node từ giá trị trước, tổng chi phí có thể trở thành Θ(n).

## 10. Độ phức tạp và giới hạn của O(1)

Gọi n là số nút trong danh sách. Bảng sau phân biệt rõ **thao tác liên kết khi có nút** và **toàn bộ yêu cầu tìm rồi thao tác**.

| Công việc | Thời gian | Bộ nhớ phụ | Điều kiện |
| --- | --- | --- | --- |
| Chèn trước/sau anchor đã biết | **Θ(1)** | O(1) cộng một nút mới | Anchor hợp lệ, thuộc danh sách. |
| Xóa đúng target đã biết | **Θ(1)** | O(1) | Target hợp lệ, thuộc danh sách. |
| Xóa head hoặc tail | **Θ(1)** | O(1) | Có head/tail, xử lý rỗng. |
| Chuyển nút đã biết lên đầu | **Θ(1)** | O(1) | Nút thuộc danh sách; không đổi size. |
| Chèn/xóa theo giá trị khi chưa biết nút | **O(n)**, xấu nhất Θ(n) | O(1) | Phải tìm nút phù hợp qua các liên kết. |
| Chèn/xóa tại chỉ số tùy ý | **O(n)**, xấu nhất Θ(n) | O(1) | Phải định vị nút trước. |
| Duyệt để kiểm chứng nút thuộc danh sách | **O(n)** | O(1) | Nếu dùng cách tìm từ head. |
| Kiểm tra mọi bất biến bằng tập đã thăm | **Θ(n)** | O(n) | Chỉ dùng khi kiểm tra/gỡ lỗi. |

Một phép chèn cấp phát **một nút**, có chi phí O(1) theo mô hình phân tích thông thường. Ngoài nút mới, số biến tham chiếu tạm thời cũng không tăng theo n. Danh sách đôi lưu **prev** và **next** cho mỗi nút, nên bộ nhớ tổng cộng là **O(n)**, với chi phí mỗi nút lớn hơn danh sách đơn dùng một liên kết.

### Tại sao không tự kiểm tra thuộc danh sách trong O(1)?

Chỉ có trường prev và next **không đủ** để xác nhận một đối tượng nút thuộc **đúng danh sách cụ thể**. Một nút thuộc danh sách khác có thể có liên kết đối ứng hợp lệ, hoặc một nút đã gỡ có prev và next đều là None giống nút duy nhất của danh sách.

Một API công khai có thể:

- Giữ tiền điều kiện rõ ràng, chỉ chuyển tham chiếu nút từ chính cấu trúc quản lý.
- Duyệt từ head để xác nhận nút nằm trong danh sách, làm chi phí bước kiểm tra thành O(n).
- Bổ sung metadata về chủ sở hữu nút để kiểm tra nhanh hơn; khi đó phải duy trì metadata khi chèn/xóa hoặc chuyển nút giữa danh sách.

Không nên ghi chung chung “xóa nút bất kỳ trong O(1)” nếu đầu vào thực tế chỉ là một **giá trị** hoặc một **chỉ số**, vì việc định vị nút có thể chiếm phần lớn thời gian.

## 11. Danh tính nút, tham chiếu bên ngoài và vòng đời dữ liệu

Xét danh sách chứa hai nút khác nhau nhưng cùng giá trị 7:

~~~text
head ──► [7, nút P] ⇄ [7, nút Q] ◄── tail
~~~

Nếu đã giữ tham chiếu **target = Q**, remove_node(target) phải **xóa Q**, không phải tùy ý xóa P vì cùng giá trị 7. So sánh bằng **is** phù hợp khi cần xác định đối tượng.

Sau khi xóa Q, một biến bên ngoài vẫn có thể giữ Q. Việc đặt **Q.prev = None** và **Q.next = None** chỉ gỡ các liên kết cũ; nó không buộc đối tượng Q biến mất ngay. Trong Python, bộ thu gom bộ nhớ quản lý vòng đời dựa trên khả năng truy cập đối tượng. Trong C/C++, nếu nút được cấp phát động, quản lý vùng nhớ cần thực hiện riêng và tránh dùng con trỏ trỏ tới vùng đã giải phóng.

### Vì sao không xóa nút bằng cách chép dữ liệu?

Mẹo của danh sách đơn đôi khi ghi đè giá trị target bằng giá trị successor rồi gỡ successor. Cách đó không xóa **đúng đối tượng target**; nó thay đổi dữ liệu của target, trong khi đối tượng successor mới bị gỡ. Nếu hệ thống có tham chiếu bên ngoài hoặc mỗi nút có danh tính riêng, hành vi này có thể sai.

Danh sách đôi không cần mẹo đó: với prev và next, remove_node có thể sửa trực tiếp hai nút lân cận và gỡ **chính target** trong Θ(1).

### Tham chiếu tới nút đã xóa

Sau khi remove_node(target), **không được tiếp tục dùng target làm anchor/target của thao tác chèn/xóa đối với danh sách cũ** khi chưa thêm nó trở lại theo API hợp lệ. Ví dụ cài đặt ở trên tạo nút mới mỗi khi insert; nó không có API nối lại một nút cũ đã tách.

Gọi remove_node lần thứ hai trên cùng nút đã bị gỡ có thể làm sai head/tail/size vì tiền điều kiện không còn thỏa. Cần quản lý vòng đời tham chiếu tại nơi gọi hoặc bổ sung cơ chế kiểm chứng nếu đây là yêu cầu của API.

## 12. Lỗi thường gặp khi cập nhật liên kết

| Lỗi | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| Chèn giữa nhưng chỉ gán anchor.next = new | Thiếu liên kết new.prev/new.next và successor.prev. | Lưu hàng xóm cũ, cập nhật đủ hai chiều. |
| Lấy successor sau khi đã đổi anchor.next | Mất tham chiếu tới phần đuôi cũ; có thể tạo tự tham chiếu. | Giữ **right = anchor.next** trước khi sửa. |
| Chèn trước head nhưng không đổi head | Nút mới không phải đầu theo metadata. | Nếu left là None, đặt head = new. |
| Chèn sau tail nhưng không đổi tail | Tail cũ có next khác None. | Nếu right là None, đặt tail = new. |
| Xóa giữa mà chỉ gán left.next = right | Right.prev vẫn trỏ tới target đã gỡ. | Gán đồng thời right.prev = left. |
| Xóa head mà không đưa head sang right | Head giữ nút đã bị gỡ. | Nếu left là None, cập nhật head = right. |
| Xóa tail mà không chuyển tail về left | Tail giữ nút cũ. | Nếu right là None, cập nhật tail = left. |
| Xóa nút duy nhất nhưng chỉ sửa một đầu | Danh sách rỗng có metadata không nhất quán. | Cả head và tail phải thành None, size = 0. |
| Quên cập nhật size khi chèn/xóa | Size khác số nút thực tế. | Chèn tăng 1; xóa thành công giảm 1. |
| Tăng size khi chỉ di chuyển một nút | Đếm nhầm nút trong danh sách. | Di chuyển giữ nguyên size và danh tính nút. |
| Truyền nút thuộc danh sách khác | Có thể làm hỏng cả hai danh sách. | Bảo đảm tiền điều kiện hoặc xác minh chủ sở hữu. |
| Gỡ một nút hai lần | Có thể hủy head/tail và giảm size sai. | Không sử dụng tham chiếu đã gỡ làm target lần nữa. |
| Chỉ kiểm tra thứ tự giá trị theo chiều xuôi | Có thể bỏ qua lỗi prev. | Kiểm tra cả hướng head → tail và tail → head. |

Khi thấy danh sách có hành vi lạ, hãy vẽ **trước và sau** các mũi tên cho hai nút lân cận của vị trí sửa. Sau đó duyệt từ head theo next và từ tail theo prev; hai lượt phải thấy **cùng số nút với thứ tự đảo ngược**.

## 13. Ứng dụng: bộ đệm LRU và trình quản lý tác vụ

Một **bộ đệm LRU** (*Least Recently Used*) thường cần hai thao tác: khi một khóa được truy cập, đưa nút tương ứng lên đầu; khi bộ đệm đầy, loại nút cuối ít được dùng gần đây nhất.

Nếu chỉ có danh sách đôi, việc **tìm khóa** có thể mất O(n). Nhưng nếu kết hợp **bảng băm** ánh xạ khóa → tham chiếu nút:

1. Tra bảng băm để lấy nút của khóa, **O(1) trung bình**.
2. Gọi thao tác di chuyển nút đã biết lên đầu, **Θ(1)**.
3. Khi cần loại bỏ mục cũ nhất, gỡ tail của danh sách đôi, **Θ(1)**, và cập nhật bảng băm cho khóa bị loại.

Danh sách đôi hữu ích ở đây bởi **không phải tìm nút trước** và có thể giữ **cùng danh tính nút** khi di chuyển.

Trong một ứng dụng quản lý tác vụ, nếu giao diện đang giữ tham chiếu tới tác vụ hiện tại, có thể chèn tác vụ mới ngay trước/sau tác vụ ấy hoặc xóa chính tác vụ ấy trong Θ(1). Nếu giao diện chỉ biết tên tác vụ, chi phí tìm tham chiếu phụ thuộc cấu trúc tra cứu.

## 14. Bài tập vận dụng có đáp án

**Bài 1 — Chèn sau nút giữa.** Danh sách A ⇄ B ⇄ C, đã có tham chiếu tới B. Muốn chèn X sau B, cần cập nhật những liên kết nào?

*Đáp án:* Lưu right = B.next (C), đặt **X.prev = B**, **X.next = C**, **B.next = X**, **C.prev = X**. Head/tail không đổi; size tăng 1.

**Bài 2 — Chèn trước head.** Danh sách chỉ có một nút A; head is tail is A. Chèn X trước A khiến head và tail thay đổi ra sao?

*Đáp án:* **head = X**, **tail = A**. X.prev = None, X.next = A, A.prev = X, A.next = None; size từ 1 thành 2.

**Bài 3 — Xóa nút giữa.** Với A ⇄ B ⇄ C, target trỏ B. Hãy mô tả hai liên kết giữa hàng xóm sau xóa.

*Đáp án:* **A.next = C** và **C.prev = A**. Gỡ B.prev/B.next về None, giảm size 1.

**Bài 4 — Xóa nút cuối.** Danh sách A ⇄ B ⇄ C, target = C = tail. Có cần duyệt từ head để tìm B không?

*Đáp án:* Không. **C.prev is B**, nên đặt B.next = None và tail = B, giảm size. Chi phí Θ(1) khi target hợp lệ.

**Bài 5 — Xóa nút duy nhất.** head is tail trỏ tới X, size = 1. Sau remove_node(X), các thuộc tính phải bằng gì?

*Đáp án:* **head is None**, **tail is None**, **size == 0**. X.prev = X.next = None.

**Bài 6 — Tiền điều kiện.** Có hai danh sách L1 và L2. Một nút B thuộc L2 được truyền vào L1.remove_node(B). Tại sao đây là lỗi dù B có prev/next đầy đủ?

*Đáp án:* B không thuộc L1. L1 có thể thay head/tail/size dựa trên các liên kết của L2, phá vỡ cấu trúc. Phải xác minh quyền sở hữu hoặc chỉ truyền tham chiếu nút thuộc L1.

**Bài 7 — Hai nút trùng giá trị.** Danh sách có hai nút khác nhau cùng value = 5, và bạn chỉ muốn xóa nút thứ hai. Có thể gọi xóa theo value mà luôn đúng không?

*Đáp án:* Không. Tìm theo value có thể chọn nút đầu tiên. Cần giữ **tham chiếu tới đúng đối tượng nút thứ hai** rồi remove_node trên đối tượng ấy.

**Bài 8 — Di chuyển nút.** Danh sách A ⇄ B ⇄ C ⇄ D, node trỏ C. Sau move_to_front(C), chuỗi và size là gì?

*Đáp án:* **C ⇄ A ⇄ B ⇄ D**, size vẫn là 4. Chính đối tượng C được di chuyển, không tạo nút C mới.

**Bài 9 — Phân tích thời gian.** Bạn chỉ biết khóa x, không có tham chiếu nút. Hệ thống duyệt danh sách đôi để tìm x rồi xóa. Độ phức tạp xấu nhất có phải Θ(1) không?

*Đáp án:* Không. Bước tìm khóa có thể tốn Θ(n); nối lại liên kết sau khi tìm thấy target mới là Θ(1). Tổng thời gian xấu nhất là Θ(n).

**Bài 10 — Sửa lỗi.** Trong khi chèn X giữa A và B, mã chỉ gán A.next = X và X.next = B; duyệt từ head theo next vẫn in A, X, B. Vì sao danh sách chưa đúng?

*Đáp án:* Thiếu **X.prev = A** và **B.prev = X**. Duyệt ngược sẽ sai; bất biến liên kết hai chiều bị vi phạm.

**Ghi nhớ:** Khi đã có **tham chiếu hợp lệ tới nút thuộc danh sách đôi**, chèn trước/sau nút đó và xóa đúng nút đó chỉ cần **Θ(1)** thời gian. Thành công phụ thuộc việc giữ đồng thời liên kết **prev/next**, cập nhật head/tail ở ranh giới và điều chỉnh size chính xác. Bước **tìm hoặc kiểm chứng** nút vẫn có thể tốn Θ(n), cần tính riêng khi phân tích toàn bộ thao tác.

# Chèn đầu, chèn sau nút và thêm cuối

Trong **danh sách liên kết đơn** (*singly linked list*), mỗi nút chứa một giá trị và tham chiếu **next** đến nút kế tiếp. Để thêm một phần tử, ta tạo nút mới rồi cập nhật một vài liên kết. Không cần dịch chuyển hàng loạt giá trị như khi chèn vào đầu hoặc giữa mảng động, nhưng cần **xác định đúng nút sẽ nối** và **giữ nguyên đường đi tới các nút còn lại**.

Trong mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, bài học thuộc chương **Danh sách liên kết**, góp phần xây dựng nền tảng về bất biến, thao tác và độ phức tạp thời gian/bộ nhớ để lựa chọn cấu trúc phù hợp. Ba phép chèn cơ bản được khảo sát ở đây là **chèn đầu** (*prepend*), **chèn sau nút đã biết** (*insert after*) và **thêm cuối** (*append*).

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Vẽ sơ đồ liên kết trước và sau mỗi phép chèn trên danh sách đơn.
- Thực hiện đúng thứ tự gán tham chiếu để không làm mất chuỗi nút hoặc tạo chu trình.
- Cập nhật **head**, **tail** và **size** trong các trường hợp danh sách rỗng, một nút và nhiều nút.
- Giải thích điều kiện “**đã có tham chiếu tới nút trước vị trí chèn**” khi phát biểu độ phức tạp O(1).
- So sánh thêm cuối khi có tail với khi chỉ có head; nêu chi phí tìm vị trí trước khi chèn.
- Cài đặt và kiểm tra các phép chèn bằng Python.

## 2. Mô hình nút và những bất biến cần giữ

Xét danh sách chứa ba giá trị:

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

Mỗi nút gồm **value** (dữ liệu) và **next** (tham chiếu đến nút sau). **Head** chỉ nút đầu tiên; **tail** chỉ nút cuối cùng; **size** đếm số nút. Trong mô hình bài này, không dùng nút canh gác (*dummy/sentinel node*).

Trước và sau mỗi phép chèn hoàn chỉnh, các **bất biến** phải đúng:

1. Danh sách rỗng khi và chỉ khi **head** và **tail** đều là **None**, đồng thời **size = 0**.
2. Khi danh sách không rỗng, từ **head** đi theo **next** phải gặp đúng nút cuối **tail**; **tail.next is None**.
3. Chuỗi không có chu trình và mọi nút thuộc danh sách đều đi tới được từ head.
4. **size** bằng số nút đi qua khi duyệt từ head tới None.
5. Với đúng một nút, **head is tail**; với từ hai nút trở lên, chúng tham chiếu tới hai nút khác nhau.

Tất cả các thao tác được giả định thực hiện trên danh sách hợp lệ ban đầu. **Một giá trị có thể trùng nhau ở nhiều nút**; việc chỉ tới nút dựa vào tham chiếu đối tượng, không dựa vào so sánh giá trị.

Trong Python, một nút đơn giản được viết như sau:

~~~python
class Node:
    def __init__(self, value, next_node=None):
        self.value = value
        self.next = next_node
~~~

Một liên kết mới được tạo bằng phép gán **next**, chẳng hạn **a.next = b**. Phép gán chỉ thay đổi tham chiếu của a; nó không sao chép giá trị hoặc toàn bộ cấu trúc của b.

## 3. Chèn vào đầu: prepend

Phép **prepend(x)** thêm một nút mang giá trị x ở đầu. Sau chèn, nút mới phải là head và trỏ đến head cũ.

### 3.1. Trường hợp danh sách có sẵn nút

Trước khi chèn 5:

~~~text
head ──► [ 10 | • ] ──► [ 20 | • ] ──► [ 30 | None ] ◄── tail
~~~

Sau khi chèn:

~~~text
head ──► [ 5 | • ] ──► [ 10 | • ] ──► [ 20 | • ] ──► [ 30 | None ] ◄── tail
~~~

Các bước theo đúng thứ tự:

1. Tạo nút **new** chứa 5.
2. Gán **new.next = head** để new giữ liên kết đến toàn bộ chuỗi cũ.
3. Gán **head = new** để đánh dấu nút đầu mới.
4. Giữ nguyên tail vì nút cuối không đổi; tăng size thêm 1.

Ví dụ Python:

~~~python
new = Node(5)
new.next = head
head = new
size += 1
~~~

Trình tự **nối tới head cũ rồi mới đổi head** giúp không mất tham chiếu đến chuỗi cũ. Với đoạn mã trên, giả định danh sách trước đó không rỗng nên tail giữ nguyên.

### 3.2. Trường hợp danh sách rỗng

Ban đầu **head = None, tail = None, size = 0**. Nút mới vừa là đầu vừa là cuối:

~~~text
Trước:
head ──► None
tail ──► None

Sau prepend(5):
head ──┐
       ▼
     [ 5 | None ]
       ▲
tail ──┘
size = 1
~~~

Vì head cũ là None, phép gán **new.next = head** tự tạo liên kết kết thúc hợp lệ. Nhưng cần **đặt tail = new**, nếu không cấu trúc sẽ có head mà không có tail.

Cài đặt đúng cho cả hai trạng thái:

~~~python
def prepend(self, value):
    new = Node(value, self.head)
    self.head = new

    if self.tail is None:  # Trước khi chèn, danh sách rỗng
        self.tail = new

    self.size += 1
~~~

**Thời gian:** Θ(1) vì số phép gán không phụ thuộc độ dài danh sách. **Bộ nhớ thêm:** Θ(1) cho đúng một nút và một số biến tham chiếu; dung lượng toàn danh sách sau n lần chèn là O(n).

## 4. Chèn ngay sau một nút đã biết: insert_after

Giả sử có tham chiếu **p** đến nút chứa 10 và muốn chèn 20 ngay sau p:

~~~text
Trước:
head ──► [ 10 | • ] ─────────────────► [ 30 | None ] ◄── tail
            ▲
            p

Sau insert_after(p, 20):
head ──► [ 10 | • ] ──► [ 20 | • ] ──► [ 30 | None ] ◄── tail
            ▲                ▲
            p                new
~~~

Nhiệm vụ là **giữ liên kết cũ p.next**, rồi cho p trỏ tới nút mới.

### 4.1. Thứ tự hai phép gán quyết định tính đúng đắn

Giả sử p.next đang trỏ đến nút 30:

~~~python
new = Node(20)
new.next = p.next
p.next = new
~~~

Sau dòng thứ hai, new.next vẫn trỏ tới nút 30. Sau dòng thứ ba, p.next trỏ tới new. Vì vậy, chuỗi trở thành **10 → 20 → 30**.

**Không được đảo hai phép gán** trong cách viết này:

~~~python
# SAI: tạo tự tham chiếu.
p.next = new
new.next = p.next
~~~

Sau phép gán đầu, p.next đã là new. Phép gán sau tương đương **new.next = new**, khiến nút mới trỏ vào chính nó:

~~~text
p ──► new
      ▲  │
      └──┘

Nút 30 cũ không còn đi tới được qua p.
~~~

Một biến thể tương đương và dễ đọc là lưu nút sau cũ:

~~~python
old_next = p.next
new = Node(20, old_next)
p.next = new
~~~

Điểm cốt lõi vẫn là **bảo toàn đường đi đến phần đuôi trước khi thay p.next**.

### 4.2. Chèn sau nút cuối

Khi **p is tail**, p.next ban đầu là None. Sau khi nối, **new** trở thành nút cuối, vì vậy phải cập nhật tail:

~~~text
Trước:
head ──► [ 10 | • ] ──► [ 30 | None ] ◄── tail
                          ▲
                          p

Sau insert_after(p, 40):
head ──► [ 10 | • ] ──► [ 30 | • ] ──► [ 40 | None ] ◄── tail
                          ▲              ▲
                          p              new
~~~

Nếu quên **tail = new**, tail sẽ chỉ vào nút 30 có **next khác None**, phá vỡ bất biến của nút cuối.

Cài đặt:

~~~python
def insert_after(self, p, value):
    # Tiền điều kiện: p đang thuộc danh sách này.
    if p is None:
        raise ValueError("Nút đứng trước không được là None")

    new = Node(value, p.next)
    p.next = new

    if self.tail is p:
        self.tail = new

    self.size += 1
    return new
~~~

**Điều kiện tiên quyết quan trọng:** p phải là tham chiếu tới một nút **thực sự thuộc danh sách hiện tại**. Một nút riêng biệt nằm ngoài danh sách cũng có trường next, nhưng thay next của nó không thêm nút vào chuỗi từ head. Nếu vẫn tăng size, các bất biến sẽ bị phá vỡ.

Có hai cách thiết kế API:

- **API thao tác nút nội bộ:** yêu cầu người gọi bảo đảm p thuộc danh sách; việc nối sau p là Θ(1).
- **API công khai an toàn hơn:** nhận một giá trị hoặc chỉ số, tự duyệt để tìm p rồi chèn; bước tìm có thể mất Θ(n). Nếu cần kiểm chứng một tham chiếu p có thuộc danh sách hay không bằng cách duyệt từ head, bước kiểm chứng cũng tốn O(n).

### 4.3. Chèn vào giữa cần giữ tail không đổi

Nếu p không phải tail thì nút cuối trước và sau chèn là cùng một đối tượng. Chỉ cần gán **new.next = p.next**, **p.next = new** và tăng size. Không cần cập nhật head, vì nút đầu không đổi; không cần cập nhật tail, vì nút cuối không đổi.

Trường hợp danh sách có đúng một nút đặc biệt hữu ích để kiểm tra: **head is tail is p**. Chèn sau p sẽ tạo hai nút; head vẫn là p và tail chuyển thành new.

## 5. Thêm vào cuối: append

Phép **append(x)** luôn đặt nút mới ở cuối, sau tail hiện tại. Đây có thể xem là một trường hợp riêng của chèn sau nút đã biết, với nút trước chính là **tail**; tuy nhiên danh sách rỗng không có tail, nên cần nhánh riêng.

### 5.1. Danh sách không rỗng, có lưu tail

~~~text
Trước append(40):
head ──► [ 10 | • ] ──► [ 20 | None ] ◄── tail

Sau append(40):
head ──► [ 10 | • ] ──► [ 20 | • ] ──► [ 40 | None ] ◄── tail
~~~

Thứ tự thao tác:

1. Tạo **new** với **new.next = None**.
2. Gán **tail.next = new** để nối sau nút cuối cũ.
3. Gán **tail = new** để cập nhật con trỏ cuối.
4. Tăng size thêm 1.

~~~python
new = Node(40)
tail.next = new
tail = new
size += 1
~~~

Không nên gán tail thành new **trước** khi nối tail cũ; sau khi thay tail, biến đó không còn chỉ đến nút cuối cũ và sẽ mất điểm nối.

### 5.2. Thêm cuối vào danh sách rỗng

Khi rỗng, không thể đọc **tail.next** vì tail là None. Nút mới phải là cả head và tail:

~~~python
def append(self, value):
    new = Node(value)

    if self.tail is None:
        self.head = new
    else:
        self.tail.next = new

    self.tail = new
    self.size += 1
~~~

Tại nhánh danh sách rỗng, phép gán tail = new ở cuối hàm bảo đảm **head is tail**. Với danh sách không rỗng, head giữ nguyên, chỉ nút cuối cũ được nối với new và tail chuyển đến new.

### 5.3. Nếu chỉ lưu head thì sao?

Không có tail, muốn thêm cuối khi danh sách có nút, phải duyệt để tìm nút có next là None:

~~~python
def append_without_tail(head, value):
    new = Node(value)

    if head is None:
        return new

    current = head
    while current.next is not None:
        current = current.next

    current.next = new
    return head
~~~

Với n nút, phép duyệt có thể đi qua n nút, nên **append không có tail mất Θ(n)** trong trường hợp xấu nhất. Khi lưu tail hợp lệ, append là **Θ(1)**, đổi lại phải duy trì chính xác tail trong mọi thao tác thay đổi cấu trúc.

## 6. Bảng chuyển trạng thái và con trỏ cần cập nhật

Bảng sau giả định danh sách đơn có head, tail, size, không có nút canh gác:

| Phép chèn | Trạng thái trước | Head sau thao tác | Tail sau thao tác | Liên kết được sửa |
| --- | --- | --- | --- | --- |
| prepend(x) | Rỗng | new | new | new.next = None |
| prepend(x) | Không rỗng | new | Giữ tail cũ | new.next = head cũ |
| insert_after(p, x) | p ở giữa hoặc đầu nhưng chưa phải tail | Giữ head cũ | Giữ tail cũ | new.next = p.next cũ; p.next = new |
| insert_after(p, x) | p là tail | Giữ head cũ | new | p.next = new; new.next = None |
| append(x) | Rỗng | new | new | new.next = None |
| append(x) | Không rỗng | Giữ head cũ | new | tail cũ.next = new; new.next = None |

**Mọi phép chèn thành công** đều làm **size mới = size cũ + 1**. Với đúng một nút, head và tail cùng trỏ vào một đối tượng; với hai nút, chúng trở thành hai đối tượng khác nhau.

Không có trường hợp **insert_after(p, x)** hợp lệ khi danh sách rỗng, bởi không tồn tại p thuộc danh sách. Muốn chèn nút đầu tiên, hãy dùng **prepend** hoặc **append**.

## 7. Cài đặt Python đầy đủ và các ví dụ kiểm chứng

Cài đặt sau dùng Python 3.10 trở lên và cố ý giữ điều kiện tiên quyết của **insert_after** rõ ràng: p là một nút thuộc danh sách. Hàm **find_node** hỗ trợ lấy tham chiếu p bằng cách tìm giá trị, với chi phí duyệt riêng.

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

    def prepend(self, value: int) -> Node:
        new = Node(value, self.head)
        self.head = new
        if self.tail is None:
            self.tail = new
        self.size += 1
        return new

    def insert_after(self, p: Node, value: int) -> Node:
        # Tiền điều kiện: p thuộc danh sách hiện tại.
        if p is None:
            raise ValueError("Không thể chèn sau None")

        new = Node(value, p.next)
        p.next = new
        if self.tail is p:
            self.tail = new
        self.size += 1
        return new

    def append(self, value: int) -> Node:
        new = Node(value)
        if self.tail is None:
            self.head = new
        else:
            self.tail.next = new
        self.tail = new
        self.size += 1
        return new

    def find_node(self, value: int) -> Node | None:
        current = self.head
        while current is not None:
            if current.value == value:
                return current
            current = current.next
        return None

    def to_list(self) -> list[int]:
        result = []
        current = self.head
        while current is not None:
            result.append(current.value)
            current = current.next
        return result

    def check_invariants(self):
        # Hàm dùng khi học/gỡ lỗi, không nằm trong chi phí phép chèn.
        if self.head is None:
            assert self.tail is None and self.size == 0
            return

        assert self.tail is not None and self.tail.next is None
        count = 0
        current = self.head
        visited = set()
        last = None
        while current is not None:
            assert id(current) not in visited, "Có chu trình"
            visited.add(id(current))
            last = current
            current = current.next
            count += 1

        assert last is self.tail, "Tail không phải nút cuối"
        assert count == self.size, "Size không khớp"


items = SinglyLinkedList()
items.check_invariants()
assert items.to_list() == []

# Rỗng -> một nút: thêm đầu.
n10 = items.prepend(10)
items.check_invariants()
assert items.head is n10 and items.tail is n10
assert items.to_list() == [10]

# Một nút -> hai nút: chèn sau chính tail.
n30 = items.insert_after(n10, 30)
items.check_invariants()
assert items.head is n10 and items.tail is n30
assert items.to_list() == [10, 30]

# Chèn vào giữa; tail phải giữ nguyên.
n20 = items.insert_after(n10, 20)
items.check_invariants()
assert items.tail is n30
assert items.to_list() == [10, 20, 30]

# Chèn đầu khi danh sách đã có nút.
n5 = items.prepend(5)
items.check_invariants()
assert items.head is n5 and items.tail is n30
assert items.to_list() == [5, 10, 20, 30]

# Thêm cuối với tail.
n40 = items.append(40)
items.check_invariants()
assert items.tail is n40 and n40.next is None
assert items.to_list() == [5, 10, 20, 30, 40]
assert items.size == 5

# Một danh sách độc lập: append khi ban đầu rỗng.
other = SinglyLinkedList()
first = other.append(7)
other.check_invariants()
assert other.head is first and other.tail is first
assert other.size == 1

# Kiểm tra tiền điều kiện None.
try:
    items.insert_after(None, 99)
except ValueError:
    pass
else:
    raise AssertionError("Cần báo lỗi khi p là None")
~~~

Đoạn mã dùng **assert** để xác nhận kết quả cùng các bất biến sau mỗi bước; các ví dụ không yêu cầu thư viện bên ngoài. **check_invariants** duyệt toàn bộ và dùng một tập theo dõi danh tính nút nên tốn O(n) thời gian và O(n) bộ nhớ phụ, chỉ phục vụ kiểm chứng.

### Phân biệt tham chiếu nút với giá trị nút

Cho danh sách **10 → 20 → 10**: có hai nút cùng lưu 10. Nếu gọi **find_node(10)**, hàm ở trên trả về **nút 10 đầu tiên**, vì nó duyệt từ head và dừng tại lần khớp đầu. Nếu muốn chèn sau nút 10 thứ hai, cần giữ đúng tham chiếu đến nút thứ hai hoặc duyệt để xác định nó; một giá trị đơn lẻ không xác định duy nhất một nút.

Tương tự, không nên sửa tham chiếu **next** của nút vừa được trả ra từ hàm find ở bên ngoài API nếu việc đó có thể phá vỡ các bất biến mà danh sách đang duy trì.

## 8. Phân tích độ phức tạp

Gọi **n** là số nút trước khi chèn. Bảng giả định cấp phát một nút có chi phí hằng số trên mô hình phân tích thông thường, danh sách hợp lệ và dữ liệu không phát sinh xử lý đặc biệt:

| Thao tác | Thời gian | Bộ nhớ bổ sung | Điều kiện |
| --- | --- | --- | --- |
| Chèn đầu (prepend) | **Θ(1)** | **O(1)** | Có head; xử lý riêng tail khi rỗng. |
| Chèn sau nút p đã có | **Θ(1)** | **O(1)** | p thuộc danh sách; không tính chi phí tìm/kiểm chứng p. |
| Tìm p theo giá trị rồi chèn sau | **O(n)** | **O(1)** | Có thể phải duyệt hết hoặc không tìm thấy. |
| Tìm p theo chỉ số k rồi chèn | **O(k + 1)**, xấu nhất **O(n)** | **O(1)** | Chỉ số hợp lệ, bắt đầu tìm từ head. |
| Thêm cuối có tail | **Θ(1)** | **O(1)** | Tail luôn chính xác. |
| Thêm cuối chỉ có head | **O(n)**, xấu nhất **Θ(n)** | **O(1)** | Phải đi tới nút cuối nếu không rỗng. |
| Kiểm tra tất cả bất biến bằng cách duyệt | **O(n)** | **O(n)** nếu lưu tập phát hiện chu trình | Bước kiểm tra độc lập với phép chèn. |

Các phép chèn tạo ra **một nút mới**, nên ngoài phần dữ liệu chứa trong nút, bộ nhớ cần thêm trên mỗi lần chèn chỉ là O(1). Một danh sách có n nút chiếm **O(n)** bộ nhớ tổng thể, vì mỗi nút cần lưu giá trị và tham chiếu next.

### Tại sao chèn sau nút là O(1) còn chèn vào giữa theo chỉ số có thể là O(n)?

Có hai công việc khác nhau:

1. **Định vị**: tìm nút đứng ngay trước vị trí cần chèn.
2. **Nối liên kết**: tạo new, gán new.next và sửa p.next.

Công việc thứ hai luôn có số phép gán cố định nếu đã biết p. Nhưng công việc thứ nhất có thể tốn Θ(n) khi p nằm gần cuối. Vì thế, không nên suy luận rằng “danh sách liên kết chèn ở giữa luôn O(1)”.

Ví dụ, để thêm một nút trước vị trí k > 0 của danh sách đơn, thường cần tìm nút ở vị trí k − 1 từ head; việc tìm mất O(k). Nếu chèn trước vị trí 0, ta dùng prepend trong O(1).

### So sánh với mảng động

Mảng động như **list** trong Python hỗ trợ truy cập chỉ số O(1), nhưng chèn ở đầu hoặc giữa thường phải dời nhiều phần tử, có chi phí O(n). Danh sách liên kết đơn chèn đầu O(1) và chèn sau nút **đã có tham chiếu** O(1), đổi lại truy cập theo chỉ số có chi phí xấu nhất O(n), có chi phí tham chiếu cho từng nút và có thể kém thuận lợi hơn về bộ nhớ đệm.

Lựa chọn cấu trúc cần xét **toàn bộ chuỗi thao tác** của ứng dụng: có hay không có tham chiếu tới vị trí chèn, mức độ thường xuyên truy cập ngẫu nhiên, cách sử dụng bộ nhớ và tần suất thêm/xóa.

## 9. Lỗi thường gặp và cách phát hiện

| Lỗi | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| Chèn đầu bằng cách đổi head trước khi nối new.next | Có thể mất chuỗi cũ nếu không giữ tham chiếu. | Nối **new.next = head cũ** trước, rồi đổi head. |
| Chèn sau p bằng cách gán p.next = new trước, rồi new.next = p.next | **new.next = new**, tạo chu trình và bỏ rơi phần sau. | Lưu **p.next cũ** vào new.next trước khi gán p.next. |
| Chèn sau tail nhưng không cập nhật tail | Tail không còn là nút cuối, **tail.next** khác None. | Nếu **p is tail**, đặt **tail = new**. |
| Append vào danh sách rỗng bằng tail.next | Đọc thuộc tính của None gây lỗi. | Nếu tail là None, cập nhật **head = new**, sau đó **tail = new**. |
| Append đổi tail trước rồi mới dùng tail.next | Mất điểm nối vào nút cuối cũ. | Nối từ **tail cũ** trước khi đổi tail. |
| Chèn sau một nút p không thuộc danh sách | Size tăng nhưng nút mới không đi tới được từ head. | Giữ tiền điều kiện thuộc danh sách; kiểm chứng p khi cần API an toàn. |
| Quên tăng size | Số nút được báo cáo thấp hơn thực tế. | Mỗi lần chèn thành công tăng size đúng một lần. |
| Nhầm hai nút bằng giá trị với cùng một nút | Chèn sai vị trí, nhất là khi giá trị trùng. | So sánh **danh tính nút**, không chỉ so sánh value. |
| Cho new.next trỏ đến head khi append | Có thể tạo chu trình từ cuối về đầu. | Nút append mới phải có **next = None**. |

Khi nghi có lỗi, hãy vẽ lại chuỗi từ head, đi theo next cho tới None, đếm nút, xác định nút cuối thực tế rồi đối chiếu với tail và size. Một số lỗi chỉ bộc lộ ở thao tác sau: ví dụ quên cập nhật tail khi chèn sau nút cuối có thể làm lần append tiếp theo nối vào sai chỗ.

## 10. Ứng dụng thực tế

**Ngăn xếp (stack) dùng danh sách liên kết:** Khi cần thao tác **push**, có thể gọi prepend để đưa nút mới lên head trong Θ(1). Thao tác lấy khỏi đầu cũng có chi phí Θ(1), phù hợp với nguyên tắc vào sau ra trước (LIFO).

**Hàng đợi (queue) dùng danh sách liên kết:** Khi cần **enqueue**, có thể dùng append với tail trong Θ(1); khi cần **dequeue**, xóa head trong Θ(1). Phải đặc biệt chú ý khi hàng đợi từ rỗng thành một nút hoặc từ một nút trở về rỗng để cả head và tail đều chính xác. Đây là nền tảng để xây dựng FIFO bằng danh sách đơn.

**Chuỗi tác vụ có vị trí đã biết:** Nếu hệ thống đang giữ tham chiếu đến tác vụ hiện tại và cần chèn một tác vụ ngay sau nó, insert_after có thể nối nút mới trong Θ(1). Nếu tác vụ chỉ được biết qua tên hoặc thứ tự, hệ thống vẫn phải tìm tác vụ trước, làm chi phí tổng cộng tăng lên.

## 11. Bài tập tự luyện có đáp án

**Bài 1 — Chèn đầu vào danh sách rỗng.** Ban đầu head = tail = None, size = 0. Sau prepend(7), các thuộc tính phải là gì?

*Đáp án:* Head và tail đều chỉ tới **cùng một nút** chứa 7; next của nút ấy là None; size = 1.

**Bài 2 — Chèn vào giữa.** Có chuỗi **4 → 12 → 20 → None**, p chỉ nút 12. Muốn chèn 16 ngay sau p, hãy viết đúng hai phép gán liên kết.

*Đáp án:* Tạo new chứa 16, gán **new.next = p.next** rồi **p.next = new**. Kết quả **4 → 12 → 16 → 20 → None**. Tail vẫn chỉ nút 20.

**Bài 3 — Chèn sau tail.** Danh sách có hai nút **A → B → None**, tail chỉ B. Sau insert_after(B, C), head/tail/size và liên kết phải như thế nào?

*Đáp án:* **A → B → C → None**; head vẫn chỉ A, tail chuyển sang C, size tăng thêm 1. B.next chỉ C và C.next là None.

**Bài 4 — Phát hiện vòng lặp.** Xét mã:

~~~python
new = Node(9)
p.next = new
new.next = p.next
~~~

Tại sao mã có thể làm hỏng danh sách, ngay cả khi p đang thuộc danh sách?

*Đáp án:* Sau khi p.next đã là new, phép gán tiếp theo khiến **new.next cũng là new**. Nút new tự trỏ vào nó và chuỗi cũ sau p không còn nối qua được. Cần gán new.next từ **p.next cũ** trước khi thay p.next.

**Bài 5 — Phân tích chi phí.** Muốn chèn giá trị 99 sau nút ở vị trí thứ k trong danh sách đơn dài n, nhưng chỉ có head. Tổng độ phức tạp thời gian là bao nhiêu? Nếu đã giữ tham chiếu trực tiếp đến nút thứ k thì sao?

*Đáp án:* Khi chỉ có head, đi đến nút thứ k mất Θ(k + 1), rồi nối liên kết mất Θ(1); tổng Θ(k + 1), xấu nhất Θ(n). Khi đã có tham chiếu hợp lệ tới nút ấy, chèn mất Θ(1).

**Bài 6 — So sánh append.** Hãy giải thích vì sao append có tail là Θ(1) còn append chỉ lưu head là Θ(n) trong trường hợp xấu nhất.

*Đáp án:* Có tail, ta nối trực tiếp sau nút cuối rồi cập nhật tail. Không có tail, phải duyệt từ head đến nút có next là None trước khi nối.

**Bài 7 — Vẽ chuỗi thao tác.** Từ danh sách rỗng, thực hiện prepend(20), prepend(10), append(40), rồi insert_after(nút chứa 20, 30). Ghi chuỗi cuối cùng và giá trị tại head, tail, size.

*Đáp án:* **10 → 20 → 30 → 40 → None**. Head chỉ nút chứa 10; tail chỉ nút chứa 40; size = 4.

**Ghi nhớ:** Chèn đầu, chèn sau nút đã biết và thêm cuối (khi có tail) đều có thể **Θ(1)** vì chỉ cập nhật vài tham chiếu. Độ chính xác phụ thuộc **thứ tự gán liên kết** và việc giữ bất biến của head, tail, size. Nếu cần **tìm vị trí trước khi chèn**, hãy tính thêm chi phí duyệt; với danh sách liên kết đơn, chi phí đó có thể là Θ(n).

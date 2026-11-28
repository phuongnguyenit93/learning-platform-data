# Nút và liên kết trong danh sách đơn

Danh sách liên kết đơn (*singly linked list*) là cấu trúc dữ liệu tuyến tính gồm các **nút** (*node*). Mỗi nút chứa một giá trị và một **liên kết tới nút kế tiếp**. Khác với mảng, các nút không cần nằm cạnh nhau trong bộ nhớ; thứ tự phần tử được xác định bởi các liên kết.

Trong mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, việc hiểu nút và liên kết là nền tảng để học các thao tác trên danh sách liên kết, phân tích chi phí thời gian/bộ nhớ và lựa chọn cấu trúc dữ liệu phù hợp. Bài này đi từ mô hình một nút đến cách duy trì một chuỗi nút hợp lệ khi thêm, tìm và xóa phần tử.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của **giá trị**, trường **next**, nút **head** và nút **tail**.
- Phân biệt liên kết tới một đối tượng với việc sao chép giá trị của đối tượng đó.
- Vẽ và lần theo chuỗi nút từ đầu đến cuối danh sách.
- Cập nhật liên kết đúng thứ tự để thêm hoặc xóa nút mà không làm mất phần còn lại của danh sách.
- Nêu bất biến cơ bản và phân tích độ phức tạp của các thao tác trong danh sách liên kết đơn.

## 2. Một nút gồm những gì?

Mỗi nút có hai thành phần cơ bản:

| Thành phần | Ý nghĩa |
| --- | --- |
| **value** (hay data) | Dữ liệu được lưu tại nút, chẳng hạn số nguyên, chuỗi hoặc đối tượng. |
| **next** | Tham chiếu (hoặc con trỏ, tùy ngôn ngữ) đến nút kế tiếp; bằng **None/null** nếu không có nút kế tiếp. |

Ví dụ chuỗi chứa ba giá trị 10, 20, 30:

~~~text
head
 │
 ▼
[ 10 | next ] ──► [ 20 | next ] ──► [ 30 | None ]
                                         ▲
                                        tail
~~~

Đọc sơ đồ từ trái sang phải: **head** chỉ nút mang giá trị 10; trường **next** của nút 10 chỉ nút 20; **next** của nút 20 chỉ nút 30; **next** của nút 30 bằng **None**, đánh dấu kết thúc.

Điểm then chốt: ô **next** lưu *tham chiếu đến nút*, không phải giá trị ở nút ấy. Hai nút có thể lưu cùng một giá trị mà vẫn là hai đối tượng khác nhau.

Ví dụ trong Python:

~~~python
class Node:
    def __init__(self, value, next_node=None):
        self.value = value
        self.next = next_node

third = Node(30)
second = Node(20, third)
first = Node(10, second)

head = first
print(head.value)             # 10
print(head.next.value)        # 20
print(head.next.next.value)   # 30
print(head.next.next.next)    # None
~~~

Các biến **first**, **second**, **third** chỉ các đối tượng nút. Khi gán **second.next = third**, ta tạo một liên kết tới nút **third**; không tạo thêm bản sao của nút 30.

### Vì sao nút không cần nằm liền nhau trong bộ nhớ?

Ở mảng, phần tử được tổ chức để hỗ trợ truy cập theo chỉ số hiệu quả. Với danh sách liên kết, chương trình đi từ nút này sang nút khác qua **next**, dù các nút được cấp phát ở các vị trí bộ nhớ khác nhau. Điều này cho phép thay đổi chuỗi liên kết mà không phải dời hàng loạt phần tử, nhưng làm mất khả năng truy cập trực tiếp vào phần tử thứ *i*.

Trong Python, **next** là tham chiếu tới đối tượng. Trong C, cấu trúc tương tự có thể dùng con trỏ; dù biểu diễn cụ thể khác nhau, tư tưởng “nút hiện tại biết nút tiếp theo” vẫn giống nhau.

## 3. Head, tail và các trạng thái đặc biệt

Một danh sách đơn thường giữ **head**, là tham chiếu đến nút đầu tiên. Có thể giữ thêm **tail** để nối nút ở cuối nhanh hơn; **size** là số nút hiện có.

| Trạng thái | head | tail (nếu lưu) | Chuỗi liên kết |
| --- | --- | --- | --- |
| Rỗng, 0 nút | None | None | Không có nút |
| Một nút | Chỉ nút đó | Cũng chính nút đó | Nút duy nhất → None |
| Nhiều nút | Nút đầu tiên | Nút cuối cùng | head → … → tail → None |

~~~text
Danh sách rỗng:
head = None, tail = None

Danh sách một nút:
head ──► [ 7 | None ] ◄── tail

Danh sách nhiều nút:
head ──► [ 7 | • ] ──► [ 9 | • ] ──► [ 12 | None ] ◄── tail
~~~

**Head không phải một “nút giả” mặc định.** Trong cách cài đặt ở bài này, head chỉ là biến tham chiếu; nút đầu tiên lưu dữ liệu thực. Một số cài đặt khác dùng *sentinel/dummy node*, nhưng đó là lựa chọn thiết kế riêng.

### Những bất biến cần giữ

**Bất biến** là điều phải đúng trước và sau mỗi thao tác hoàn tất:

1. Danh sách rỗng khi và chỉ khi **head is None**. Nếu có quản lý **tail** thì khi rỗng, **tail** cũng là **None**.
2. Với danh sách không rỗng, đi theo **next** từ **head** phải đến đúng nút cuối; **next** của nút cuối bằng **None**.
3. Nếu có **tail**, nó phải là nút cuối cùng, tức **tail.next is None**.
4. Trong danh sách đơn thông thường không có chu trình: không thể đi theo **next** rồi quay lại một nút đã thăm.
5. Nếu lưu **size**, số nút có thể đi tới từ **head** phải bằng **size**.

Các bất biến này quan trọng hơn việc chỉ kiểm tra các giá trị in ra. Ví dụ, danh sách vẫn có thể bắt đầu bằng 10 → 20 nhưng do nối sai, nút 30 trở thành không thể truy cập từ head.

## 4. Duyệt danh sách: đi theo từng liên kết

Danh sách đơn **không có cách nhảy trực tiếp** từ head sang phần tử ở vị trí bất kỳ. Muốn gặp nút thứ *k*, ta phải đi qua các nút đứng trước nó.

~~~text
current = head
trong khi current khác None:
    xử lý current.value
    current = current.next
~~~

Với head → 10 → 20 → 30 → None, biến **current** lần lượt tham chiếu nút 10, 20, 30, rồi **None**. Phải kiểm tra **current** khác **None** trước khi đọc **current.value** hoặc **current.next**.

~~~python
current = head
while current is not None:
    print(current.value)
    current = current.next
~~~

Nếu có *n* nút, duyệt toàn bộ tốn **O(n)** thời gian và **O(1)** bộ nhớ phụ nếu chỉ dùng một biến **current**. Tìm một giá trị cũng mất **O(n)** trong trường hợp xấu nhất. Nếu danh sách vô tình có chu trình, vòng lặp này có thể không kết thúc.

## 5. Thêm nút: nối liên kết theo đúng thứ tự

Các ví dụ sau giả sử danh sách đơn có **head** và **tail** như mục 3.

### 5.1. Thêm vào đầu — O(1)

Từ:

~~~text
head ──► [ 20 ] ──► [ 30 ] ──► None
~~~

Thêm nút mang giá trị 10:

~~~text
new ──► [ 10 ] ──► [ 20 ] ──► [ 30 ] ──► None
          ▲
         head
~~~

Thực hiện đúng thứ tự:

1. Tạo **new** chứa 10.
2. Gán **new.next = head** để new trỏ tới nút đầu cũ.
3. Gán **head = new**.
4. Nếu danh sách trước đó rỗng, cũng gán **tail = new**.

Nếu cập nhật head trước khi nối **new.next**, ta có nguy cơ đánh mất tham chiếu duy nhất tới chuỗi cũ. Thêm vào đầu không cần duyệt, nên tốn **O(1)** thời gian.

### 5.2. Thêm ngay sau nút đã biết — O(1)

Cho chuỗi:

~~~text
head ──► [ 10 ] ──► [ 30 ] ──► None
            p
~~~

Để chèn 20 sau nút **p** (nút có giá trị 10):

~~~python
new = Node(20)
new.next = p.next
p.next = new
~~~

Kết quả:

~~~text
head ──► [ 10 ] ──► [ 20 ] ──► [ 30 ] ──► None
            p          new
~~~

**Thứ tự hai phép gán là điều cốt lõi.** Phải để **new.next** giữ liên kết cũ của **p** rồi mới chuyển **p.next** sang **new**. Nếu làm **p.next = new** trước, sau đó **new.next = p.next**, nút new sẽ trỏ vào chính nó, tạo chu trình.

Nếu **p** vốn là tail, nút mới trở thành **tail**. Chi phí chèn là **O(1)** *khi đã có tham chiếu tới p*; nếu phải tìm p theo giá trị hoặc vị trí trước, tổng chi phí có thể là **O(n)**.

### 5.3. Thêm vào cuối

Nếu **tail** được duy trì chính xác:

- Danh sách rỗng: **head = tail = new**.
- Danh sách không rỗng: **tail.next = new**, sau đó **tail = new**.

Nút mới có **new.next = None**. Việc nối cuối với tail mất **O(1)**. Nếu chỉ lưu head, phải duyệt đến nút cuối nên mất **O(n)**.

## 6. Xóa nút: nối qua nút cần loại bỏ

Xóa một nút thường có nghĩa là thay đổi liên kết để nút đó **không còn thuộc chuỗi đi từ head**. Trong Python, đối tượng có thể tiếp tục tồn tại nếu nơi khác còn tham chiếu đến nó; cơ chế thu hồi bộ nhớ không phải thao tác “xóa khỏi danh sách”.

### 6.1. Xóa nút đầu — O(1)

~~~text
Trước: head ──► [ 10 ] ──► [ 20 ] ──► [ 30 ] ──► None
Sau:   head ─────────────► [ 20 ] ──► [ 30 ] ──► None
~~~

Ta giữ nút đầu cũ trong **removed**, rồi gán **head = removed.next**. Nếu nút vừa bỏ là nút duy nhất, **head** trở thành None và **tail** cũng phải thành None. Có thể gán **removed.next = None** để tách liên kết của nút đã bỏ.

### 6.2. Xóa nút sau một nút đã biết — O(1)

Giả sử đã có tham chiếu tới nút **p = 10**, muốn bỏ nút 20:

~~~text
Trước: [ 10 ] ──► [ 20 ] ──► [ 30 ] ──► None
          p        removed

Sau:   [ 10 ] ─────────────► [ 30 ] ──► None
          p
~~~

Thao tác:

~~~python
removed = p.next
if removed is not None:
    p.next = removed.next
    # Nếu removed là tail, cập nhật tail = p.
    removed.next = None
~~~

Cần có **nút đứng trước** nút cần xóa để sửa liên kết **next** của nút ấy. Vì danh sách đơn không lưu liên kết ngược, khi chỉ biết giá trị cần xóa, ta thường phải duyệt từ head để tìm nút trước nó: chi phí tổng thể **O(n)**.

### Trường hợp biên phải xét

- **Danh sách rỗng:** không có nút để xóa; API có thể báo lỗi hoặc trả kết quả thất bại.
- **Chỉ một nút:** xóa nút đầu phải đưa cả head và tail về None.
- **Xóa nút cuối:** nút đứng trước trở thành tail và có **next = None**.
- **Không tìm thấy giá trị:** không được thay đổi liên kết.
- **Tham chiếu nút không thuộc danh sách:** không được sử dụng làm **p** khi chèn/xóa sau p; ví dụ bên dưới coi việc p thuộc danh sách là *tiền điều kiện*.

## 7. Ví dụ Python hoàn chỉnh

Cài đặt sau dùng Python 3.10 trở lên, lưu head, tail và size. Các hàm **insert_after** và **remove_after** nhận tham chiếu tới một nút **đang thuộc danh sách**; người gọi chịu trách nhiệm bảo đảm tiền điều kiện này. Việc kiểm tra nút có thực sự thuộc danh sách thường phải duyệt O(n).

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

    def prepend(self, value: int) -> None:
        node = Node(value, self.head)
        self.head = node
        if self.tail is None:
            self.tail = node
        self.size += 1

    def append(self, value: int) -> None:
        node = Node(value)
        if self.tail is None:
            self.head = self.tail = node
        else:
            self.tail.next = node
            self.tail = node
        self.size += 1

    def find(self, value: int) -> Node | None:
        current = self.head
        while current is not None:
            if current.value == value:
                return current
            current = current.next
        return None

    def insert_after(self, prev: Node, value: int) -> None:
        # Tiền điều kiện: prev thuộc danh sách hiện tại.
        node = Node(value, prev.next)
        prev.next = node
        if self.tail is prev:
            self.tail = node
        self.size += 1

    def remove_first(self) -> int:
        if self.head is None:
            raise IndexError("Danh sách rỗng")
        removed = self.head
        self.head = removed.next
        if self.head is None:
            self.tail = None
        removed.next = None
        self.size -= 1
        return removed.value

    def remove_after(self, prev: Node) -> int:
        # Tiền điều kiện: prev thuộc danh sách hiện tại.
        removed = prev.next
        if removed is None:
            raise IndexError("Không có nút sau prev")
        prev.next = removed.next
        if self.tail is removed:
            self.tail = prev
        removed.next = None
        self.size -= 1
        return removed.value

    def to_list(self) -> list[int]:
        values: list[int] = []
        current = self.head
        while current is not None:
            values.append(current.value)
            current = current.next
        return values


items = SinglyLinkedList()
items.append(10)                     # 10
items.append(30)                     # 10 -> 30
node_10 = items.find(10)
assert node_10 is not None
items.insert_after(node_10, 20)      # 10 -> 20 -> 30
assert items.to_list() == [10, 20, 30]

assert items.remove_after(node_10) == 20
items.prepend(5)                     # 5 -> 10 -> 30
assert items.remove_first() == 5
assert items.to_list() == [10, 30]
assert items.size == 2
assert items.tail is not None and items.tail.next is None

assert items.remove_after(node_10) == 30
assert items.to_list() == [10]
assert items.head is items.tail

assert items.remove_first() == 10
assert items.head is None and items.tail is None
assert items.size == 0
~~~

Các phép kiểm tra cuối ví dụ lần lượt xác nhận việc nối giữa danh sách, xóa tail, chuyển về danh sách một nút và chuyển về danh sách rỗng. Các thao tác thay đổi head/tail đều cập nhật size.

## 8. Chi phí thời gian và bộ nhớ

Gọi **n** là số nút. Bảng sau xét danh sách đơn không có chu trình, có head/tail/size và không bao gồm chi phí tùy ý của việc xử lý giá trị.

| Thao tác | Thời gian | Vì sao? |
| --- | --- | --- |
| Đọc giá trị ở head | **O(1)** | Đã có tham chiếu đến nút đầu. |
| Truy cập nút ở vị trí *i* | **O(n)** trong trường hợp xấu nhất | Cần đi lần lượt qua các liên kết. |
| Duyệt toàn bộ / tìm theo giá trị | **O(n)** | Có thể phải thăm mọi nút. |
| Chèn đầu / xóa đầu | **O(1)** | Chỉ cập nhật vài tham chiếu. |
| Chèn sau nút **p** đã biết | **O(1)** | Không phải tìm vị trí. |
| Xóa nút ngay sau **p** đã biết | **O(1)** | Không phải tìm nút trước. |
| Chèn cuối có tail / không có tail | **O(1)** / **O(n)** | Có / không có tham chiếu sẵn tới cuối. |
| Xóa theo giá trị (khi chưa biết nút trước) | **O(n)** | Phải tìm vị trí cần nối lại. |
| Đọc size nếu đã duy trì biến size | **O(1)** | Không cần đếm lại các nút. |

**Bộ nhớ:** n nút dùng **O(n)** không gian. Ngoài dữ liệu, mỗi nút còn cần chỗ lưu tham chiếu **next** và thường có chi phí đối tượng/cấp phát. Duyệt bằng một con trỏ **current** sử dụng **O(1)** bộ nhớ phụ; hàm **to_list** ở ví dụ dùng **O(n)** bộ nhớ phụ vì tạo một mảng mới.

Với mảng động (ví dụ **list** của Python), truy cập phần tử theo chỉ số là O(1) và dữ liệu thường có tính cục bộ bộ nhớ tốt hơn. Danh sách liên kết đơn nổi bật khi cần **chèn/xóa tại đầu** hoặc **sau một nút đã biết** thường xuyên. Nó không tự động nhanh hơn mảng cho việc “chèn ở giữa” nếu trước tiên phải tìm vị trí.

## 9. Lỗi liên kết thường gặp

| Lỗi | Hệ quả | Cách tránh |
| --- | --- | --- |
| Gán **p.next = new** rồi **new.next = p.next** | **new.next** trỏ vào chính new, tạo chu trình. | Lưu liên kết cũ vào **new.next** trước khi sửa **p.next**. |
| Đổi head mà không nối nút mới tới head cũ | Có thể mất toàn bộ chuỗi trước đó. | Gán **new.next = head** trước, sau đó mới gán **head = new**. |
| Xóa nút cuối mà quên đổi tail | tail trỏ tới nút đã bị loại khỏi danh sách. | Khi xóa tail, đặt tail thành nút trước hoặc None nếu rỗng. |
| Không xử lý danh sách rỗng / một nút | Truy cập **None.next** hoặc để head, tail không nhất quán. | Xét riêng hai trạng thái biên trước khi cập nhật. |
| Duyệt bằng điều kiện **current.next is not None** | Bỏ sót nút cuối; có thể lỗi khi current là None. | Khi duyệt mọi nút, dùng **current is not None**. |
| Quên cập nhật **size** | Số phần tử báo cáo sai. | Tăng/giảm size đúng một lần cho mỗi nút được thêm/xóa. |
| Truyền nút không thuộc danh sách vào insert_after/remove_after | Làm sai cấu trúc hoặc size. | Giữ rõ tiền điều kiện; nếu cần API an toàn hơn, xác minh tư cách thành viên bằng duyệt. |

Một cách kiểm tra bằng tay là luôn vẽ các mũi tên **trước** và **sau** thao tác, rồi lần từ head đến None. Nếu thiếu nút, lặp vô hạn, hoặc tail không phải nút cuối, cấu trúc đã vi phạm bất biến.

## 10. Ví dụ ứng dụng và câu hỏi tự luyện

Hãy hình dung một chuỗi công việc cần xử lý theo thứ tự **A → B → C**. Mỗi nút lưu một công việc, trường **next** chỉ công việc tiếp theo. Nếu đã có tham chiếu đến nút A và muốn đưa công việc X ngay sau A, ta chỉ cần đổi hai liên kết để được **A → X → B → C**. Nhưng nếu muốn lấy công việc thứ 100, phải đi từ head qua những công việc trước đó.

**Câu hỏi 1.** Có danh sách head → 4 → 8 → 12 → None, biết tham chiếu **p** tới nút 8. Sau khi chèn nút 10 ngay sau p, các liên kết cần cập nhật là gì?

*Đáp án:* Tạo new mang 10; gán **new.next = p.next** (nút 12), rồi **p.next = new**. Kết quả 4 → 8 → 10 → 12 → None.

**Câu hỏi 2.** Với danh sách chỉ có một nút 7, xóa đầu xong head, tail và size là gì?

*Đáp án:* **head = None**, **tail = None**, **size = 0**.

**Câu hỏi 3.** Vì sao “chèn sau nút đã biết là O(1)” không có nghĩa “chèn tại vị trí thứ 500 luôn là O(1)”?

*Đáp án:* Cần tìm được nút ở vị trí 499 trước; việc đi theo liên kết từ head tới đó mất thời gian tuyến tính theo vị trí, tức **O(n)** trong trường hợp xấu nhất.

**Ghi nhớ:** **next** quyết định thứ tự logic của danh sách đơn. Mọi thao tác thêm và xóa thực chất là điều chỉnh một vài liên kết, đồng thời giữ đúng head, tail, size và bảo đảm đường đi từ head kết thúc ở None.

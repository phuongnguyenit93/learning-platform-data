# Danh sách vòng đơn, vòng đôi và điều kiện kết thúc duyệt

**Danh sách liên kết vòng** (*circular linked list*) là danh sách mà nút cuối liên kết trở lại nút đầu, thay vì kết thúc bằng **None** như danh sách tuyến tính. Nó có thể là **danh sách vòng đơn** (*circular singly linked list*) với một trường **next** trên mỗi nút, hoặc **danh sách vòng đôi** (*circular doubly linked list*) với hai trường **next** và **prev**.

Sự thay đổi tưởng như nhỏ ở nút cuối dẫn đến một thay đổi lớn trong thuật toán: **duyệt đến khi gặp None không còn là điều kiện kết thúc đúng**. Để xử lý mỗi nút đúng một lần, vòng lặp phải nhận ra thời điểm quay lại điểm xuất phát hoặc giới hạn số bước theo độ dài đã biết.

Bài học nằm trong chương **Danh sách liên kết** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Việc hiểu bất biến, thao tác và độ phức tạp thời gian/bộ nhớ của các biến thể danh sách giúp lựa chọn cấu trúc phù hợp khi xây dựng vòng xử lý luân phiên, hàng đợi hoặc những cấu trúc cần di chuyển liên tục giữa hai đầu.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt danh sách liên kết **tuyến tính**, **vòng đơn** và **vòng đôi** qua các liên kết ở nút biên.
- Mô tả trạng thái **rỗng**, **một nút** và **nhiều nút** của từng biến thể vòng.
- Phát biểu các bất biến **tail.next is head**, **head.prev is tail** và tính đối ứng giữa các liên kết của danh sách vòng đôi.
- Viết vòng lặp duyệt từ bất kỳ nút bắt đầu hợp lệ nào, xử lý **mỗi nút đúng một lần** và kết thúc đúng lúc.
- Chèn/xóa ở đầu và cuối, đồng thời bảo toàn liên kết tạo vòng.
- Giải thích vì sao xóa cuối danh sách vòng đơn thường cần O(n), còn danh sách vòng đôi có thể thực hiện trong O(1) khi giữ tail.
- Phân biệt một **vòng hợp lệ bao trùm toàn bộ danh sách** với một **chu trình vô tình xuất hiện do lỗi**.
- Cài đặt ví dụ Python và kiểm chứng các bất biến quan trọng.

## 2. Từ danh sách tuyến tính đến danh sách vòng

### 2.1. Danh sách đơn tuyến tính

Với danh sách đơn tuyến tính có ba nút A, B, C:

~~~text
head ──► [ A | • ] ──► [ B | • ] ──► [ C | None ] ◄── tail
~~~

Nút cuối C có **C.next is None**. Duyệt tuần tự thường dừng ở None:

~~~python
current = head
while current is not None:
    process(current.value)
    current = current.next
~~~

Đây là điều kiện phù hợp cho **danh sách tuyến tính**, nhưng không phù hợp cho danh sách vòng.

### 2.2. Danh sách vòng đơn

Ở danh sách vòng đơn, liên kết **next** của nút cuối quay trở lại nút đầu:

~~~text
                head
                 │
                 ▼
                [ A ] ──next──► [ B ] ──next──► [ C ]
                  ▲                              │
                  └────────────next──────────────┘
                                                 ▲
                                                tail
~~~

Các quan hệ quan trọng:

~~~text
A.next is B
B.next is C
C.next is A
tail.next is head
~~~

Không có nút nào có **next = None** trong một danh sách vòng đơn **không rỗng và hợp lệ**. Sau C, thuật toán lại gặp A, rồi B, C và tiếp tục vô hạn nếu không có điều kiện dừng phù hợp.

### 2.3. Danh sách vòng đôi

Danh sách vòng đôi cho phép đi hai chiều; nút cuối nối về đầu qua **next** và nút đầu nối về cuối qua **prev**:

~~~text
                   head
                    │
                    ▼
                   [ A ] ⇄ [ B ] ⇄ [ C ]
                     ▲                 ▲
                     │                 │
                     └──── next ───────┘  (C.next → A)
                     └──── prev ◄──────┘  (A.prev → C)
                                       tail = C
~~~

Mũi tên bên trong giữa các nút biểu diễn các cặp liên kết **next/prev**. Hai liên kết khép vòng là:

~~~text
tail.next is head
head.prev is tail
~~~

Ngoài ra, với mọi nút **x**:

~~~text
x.next.prev is x
x.prev.next is x
~~~

Khi danh sách hợp lệ và không rỗng, mọi nút đều có cả **next** và **prev** khác None. Có thể đi xuôi bằng next hoặc đi ngược bằng prev liên tục mà không gặp None.

> **Phạm vi bài học:** Các ví dụ dưới đây dùng **head**, **tail**, **size** và **không có nút canh gác** (*sentinel/dummy node*). Danh sách vòng có nút canh gác là một biến thể khác: thuật toán có thể dừng khi gặp sentinel thay vì head, và bất biến trạng thái rỗng cũng khác.

## 3. Trạng thái rỗng, một nút, nhiều nút

### 3.1. Danh sách vòng đơn

| Số nút | head | tail | Điều kiện liên kết |
| ---: | --- | --- | --- |
| 0 | None | None | Không tồn tại nút dữ liệu. |
| 1 | Nút X | Cũng là nút X | **X.next is X**. |
| ≥ 2 | Nút đầu | Nút cuối | **tail.next is head**; đi theo next đúng n bước quay về head. |

~~~text
Rỗng:
head = None
tail = None
size = 0

Một nút:
     head, tail
          │
          ▼
         [ X ] ──┐
          ▲      │
          └──────┘
      X.next is X

Ba nút:
head → A → B → C (= tail)
       ▲       │
       └───────┘
~~~

**Trường hợp một nút là trường hợp đặc biệt quan trọng:** trong danh sách vòng đơn, liên kết next của nút duy nhất phải trỏ về **chính nó**. Nếu đặt X.next = None, ta đã vô tình biến nó thành danh sách đơn tuyến tính một nút.

### 3.2. Danh sách vòng đôi

| Số nút | head và tail | Quan hệ liên kết |
| ---: | --- | --- |
| 0 | Đều là None | Không có nút dữ liệu. |
| 1 | Cùng chỉ X | **X.next is X** và **X.prev is X**. |
| ≥ 2 | Hai nút biên khác nhau | **tail.next is head**, **head.prev is tail**; các cặp liên kết phải đối ứng. |

~~~text
Một nút X trong danh sách vòng đôi:

               ┌──── next ────┐
               ▼              │
            [ X ] ◄───────────┘
               ▲
               └──── prev về chính X

head is tail is X
X.next is X
X.prev is X
~~~

Ở danh sách vòng đôi, **head.prev** không bằng None khi có nút. Việc dùng bất biến **head.prev is None** của danh sách đôi tuyến tính là sai cho phiên bản vòng.

### 3.3. Rỗng không đồng nghĩa giá trị rỗng

Danh sách có một nút **Node(None)** vẫn không rỗng. Nút ấy là head, tail và liên kết về chính nó. Muốn kiểm tra danh sách rỗng, dùng **head is None** hoặc **size == 0** khi size được duy trì đúng.

Tuyệt đối không dùng **head.value is None** để xác định trạng thái rỗng: head có thể là None (gây lỗi khi truy cập thuộc tính), hoặc một nút dữ liệu hợp lệ chứa giá trị None.

## 4. Bất biến của cấu trúc vòng

Bất biến là điều kiện phải đúng **trước và sau mỗi thao tác hoàn tất**. Với danh sách có head, tail, size và không có sentinel:

### 4.1. Bất biến của danh sách vòng đơn

1. **size == 0** khi và chỉ khi **head is None** và **tail is None**.
2. Nếu size > 0 thì **head** và **tail** đều khác None.
3. Nếu size > 0 thì **tail.next is head**.
4. Bắt đầu từ head, đi theo next đúng **size lần** phải trở về head.
5. Trong **size bước** ấy, trước khi quay về head không được gặp lại bất kỳ nút nào; tất cả size nút đều khác nhau về **danh tính đối tượng**.
6. Nút được thăm ở bước cuối trước khi trở lại head phải chính là tail.

Điều kiện **tail.next is head** là **cần nhưng chưa đủ**. Ví dụ tail có thể là một nút tách rời trỏ về head, trong khi đường đi từ head lại quay về sớm và không đi qua tail. Khi đó danh sách vẫn sai.

### 4.2. Bất biến bổ sung của danh sách vòng đôi

Ngoài những điều kiện phù hợp ở trên, cần:

1. **head.prev is tail** và **tail.next is head**.
2. Với mọi nút x, **x.next.prev is x**.
3. Với mọi nút x, **x.prev.next is x**.
4. Duyệt từ head theo next và từ tail theo prev đều đi qua **chính size nút**, không lặp sớm, rồi quay về điểm bắt đầu.

Chỉ kiểm tra hướng xuôi chưa đủ; một liên kết prev bị ghi nhầm có thể làm chương trình duyệt xuôi vẫn in đúng nhưng duyệt ngược sai.

### 4.3. “Có chu trình” chưa chắc là “danh sách vòng hợp lệ”

Xét cấu trúc bị lỗi:

~~~text
head → A → B → C
           ▲   │
           └───┘
~~~

Từ head, ta đi A → B → C → B → C → ...; **không bao giờ quay về head**. Thuật toán duyệt kiểu “đi đến khi gặp head lần nữa” sẽ lặp vô hạn.

Danh sách vòng hợp lệ yêu cầu **một chu trình bao trùm tất cả các nút thuộc danh sách và quay về đúng head**. Thuật toán phát hiện chu trình như *Floyd's tortoise and hare* chỉ xác nhận có chu trình; nó **không tự chứng minh** chu trình ấy bắt đầu tại head, đi qua đủ size nút và thỏa bất biến tail hay prev.

## 5. Điều kiện kết thúc khi duyệt danh sách vòng

Đây là khác biệt quan trọng nhất so với danh sách tuyến tính.

### 5.1. Vì sao while current is not None không dừng?

Đoạn sau **không phù hợp** với một danh sách vòng không rỗng, hợp lệ:

~~~python
current = head
while current is not None:
    print(current.value)
    current = current.next
~~~

Vì nút cuối lại nối về head, biến current sẽ luôn chỉ tới một nút và điều kiện **current is not None** luôn đúng. Chương trình có thể in mãi và không kết thúc.

### 5.2. Duyệt một vòng bắt đầu tại head

Thuật toán phải xử lý **head trước**, rồi kiểm tra xem đã quay về head hay chưa:

~~~text
nếu head là None:
    kết thúc

current ← head
lặp:
    xử lý current.value
    current ← current.next
    nếu current chính là head:
        kết thúc
~~~

Mã Python:

~~~python
if head is not None:
    current = head
    while True:
        print(current.value)
        current = current.next
        if current is head:
            break
~~~

Điểm dừng nằm **sau** lệnh xử lý và di chuyển. Nếu đặt điều kiện kiểm tra **current is not head** ngay trước lần xử lý đầu tiên, vòng lặp có thể dừng tức thì vì current ban đầu đã là head.

Mẫu này giống vòng **do ... while** trong một số ngôn ngữ: thực hiện thân vòng ít nhất một lần **chỉ khi danh sách không rỗng**. Trong Python, ta dùng **while True** và **break**.

### 5.3. Có thể dùng chỉ số bước khi đã biết size

Nếu **size** là số nút chính xác, có thể duyệt đúng size lượt:

~~~python
current = head
for _ in range(size):
    print(current.value)
    current = current.next
~~~

Đối với danh sách hợp lệ, sau đúng **size bước**, current sẽ trở lại head.

Ưu điểm của cách này là số lượt xử lý đã được giới hạn ngay trong vòng lặp. Nhưng **không thể dùng riêng size làm bằng chứng cấu trúc đúng**: nếu size sai, chương trình có thể bỏ sót nút, xử lý lặp một nút hoặc gặp None do liên kết hỏng.

Khi kiểm thử, nên bổ sung kiểm tra **current is head** sau vòng lặp; muốn khẳng định tất cả nút đều khác nhau, cần kiểm tra thêm danh tính nút đã thăm.

### 5.4. Bắt đầu từ một nút không phải head

Giả sử cần xử lý lần lượt các nút từ B trong vòng **A → B → C → A**:

~~~text
start = B
B → C → A → B   (dừng khi trở lại B)
~~~

Điều kiện dừng phải so sánh với **start**, không nhất thiết là head:

~~~python
start = some_node_in_list
current = start

while True:
    process(current.value)
    current = current.next
    if current is start:
        break
~~~

Mẫu này chỉ đúng khi **start thuộc chu trình hợp lệ**; nếu start là None, không thuộc danh sách hoặc liên kết đã hỏng, cần xử lý tiền điều kiện trước.

Để kiểm tra **cùng một nút**, dùng **is** trong Python thay vì so sánh **value** hoặc **==** nếu lớp Node định nghĩa so sánh theo nội dung. Hai nút có thể chứa giá trị bằng nhau, nên “dừng khi gặp cùng giá trị với head” sẽ dừng sớm.

### 5.5. Duyệt ngược danh sách vòng đôi

Danh sách vòng đôi hỗ trợ duyệt từ tail bằng **prev**:

~~~python
if tail is not None:
    start = tail
    current = start
    while True:
        print(current.value)
        current = current.prev
        if current is start:
            break
~~~

Với A ⇄ B ⇄ C, duyệt xuôi từ head thu được **A, B, C**; duyệt ngược từ tail thu được **C, B, A**. Khi đi ngược hết một vòng, current quay về tail, không gặp None.

### 5.6. Trường hợp rỗng và một nút

| Trạng thái | Cách dùng điều kiện dừng | Số lượt xử lý đúng |
| --- | --- | ---: |
| Rỗng | Kiểm tra head là None trước khi truy cập nút | 0 |
| Một nút | Xử lý nút một lần, đi theo next về chính nó, rồi dừng | 1 |
| n nút | Xử lý từ start, dừng sau lần đi tiếp quay về start | n |

**Không nên** dùng điều kiện **current.next is not head** để duyệt mọi nút: điều kiện có thể bỏ qua tail, và với danh sách một nút nó bỏ qua toàn bộ nút duy nhất.

## 6. Thêm nút trong danh sách vòng đơn

Với mô hình duy trì head và tail, **tail.next luôn phải trỏ về head**.

### 6.1. Thêm vào danh sách rỗng

Nút mới X đồng thời là head và tail, với **X.next = X**:

~~~text
head = tail = X
X.next = X
size = 1
~~~

Đây là bước thiết lập vòng đầu tiên. Không được tạo X.next = None nếu muốn duy trì danh sách vòng ngay sau thao tác.

### 6.2. Thêm cuối trong O(1)

Giả sử **A → B → A**, tail là B. Thêm C:

~~~text
Trước: A → B ┐
         ▲   │
         └───┘

Sau:   A → B → C ┐
         ▲       │
         └───────┘
~~~

Cần gán:

~~~python
new.next = head
tail.next = new
tail = new
size += 1
~~~

**Head giữ nguyên**. Vòng mới khép bằng **tail mới.next is head**.

### 6.3. Thêm đầu trong O(1)

Tạo X thành head mới của A → B → A:

~~~python
new.next = head
tail.next = new
head = new
size += 1
~~~

Tail giữ nguyên nhưng phải **đổi tail.next sang head mới**. Quên thao tác này sẽ khiến đường đi từ tail quay về head cũ, còn biến head mới không nằm trên chu trình.

Cả prepend và append đều O(1) khi danh sách vòng đơn đã giữ **tail** hợp lệ. Nếu chỉ lưu head, muốn tìm nút có next quay về head để cập nhật liên kết cuối khi chèn đầu hoặc thêm cuối thường phải duyệt, mất O(n) trong trường hợp xấu nhất.

## 7. Thêm nút trong danh sách vòng đôi

Với danh sách vòng đôi, các bất biến ở hai đầu là:

~~~text
tail.next is head
head.prev is tail
~~~

### 7.1. Thêm vào danh sách rỗng

Nút duy nhất X phải tự trỏ theo **cả hai chiều**:

~~~text
head = tail = X
X.next = X
X.prev = X
size = 1
~~~

### 7.2. Thêm cuối

Cho A ⇄ B, thêm C ở cuối. Liên kết cần đúng:

~~~text
C.prev = B
C.next = A
B.next = C
A.prev = C
tail = C
~~~

Trong trường hợp không rỗng, mã tương ứng:

~~~python
new.prev = tail
new.next = head
tail.next = new
head.prev = new
tail = new
size += 1
~~~

### 7.3. Thêm đầu

Cho A ⇄ B, thêm X ở đầu:

~~~text
X.prev = B
X.next = A
B.next = X
A.prev = X
head = X
~~~

Mã cho danh sách không rỗng:

~~~python
new.prev = tail
new.next = head
tail.next = new
head.prev = new
head = new
size += 1
~~~

Với cả hai thao tác, số liên kết được sửa là hằng số, nên độ phức tạp là **Θ(1)** nếu head và tail đã hợp lệ. Quan trọng là cập nhật **cả hai chiều**, không chỉ next.

## 8. Xóa đầu và xóa cuối: vòng đơn so với vòng đôi

### 8.1. Xóa đầu vòng đơn

Với danh sách A → B → C → A:

~~~text
Trước: head = A, tail = C
Sau:   head = B, tail = C, C.next = B
~~~

Khi còn từ hai nút:

~~~python
old = head
head = head.next
tail.next = head
old.next = None
size -= 1
~~~

Nếu có đúng **một nút**, phải đặt head = tail = None và size = 0. Không được để biến tail trỏ tới nút cũ có next quay vào chính nó khi danh sách đã rỗng.

Xóa đầu vòng đơn có head/tail hợp lệ là **Θ(1)**.

### 8.2. Xóa cuối vòng đơn

Dù có tail, mỗi nút chỉ biết nút tiếp theo. Muốn gỡ tail, phải tìm **nút đứng trước tail** bằng cách đi từ head:

~~~text
A → B → C → A
    ▲   ▲
   prev tail

Sau: A → B → A, tail = B
~~~

Trong trường hợp có từ hai nút, phép cập nhật:

~~~text
prev.next = head
tail = prev
size giảm 1
~~~

Công việc nối lại liên kết chỉ là O(1), nhưng **tìm prev** tốn Θ(n) trong trường hợp xấu nhất. Đây vẫn là giới hạn của danh sách **đơn**, dù cấu trúc có tính vòng.

### 8.3. Xóa đầu và cuối vòng đôi

Trong vòng đôi, từ tail có thể đến nút trước qua **tail.prev**. Vì thế:

- Xóa đầu: chuyển head sang head.next; đặt **tail.next = head** và **head.prev = tail**.
- Xóa cuối: chuyển tail sang tail.prev; đặt **tail.next = head** và **head.prev = tail**.
- Nếu chỉ có một nút: sau xóa đưa head và tail về None.

Mỗi thao tác cần số phép gán cố định nên là **Θ(1)** khi giữ head và tail hợp lệ.

### 8.4. Không tự ý dùng quy tắc xóa tuyến tính

Trong danh sách đôi tuyến tính, sau khi xóa đầu người ta thường đặt head.prev = None. **Không thực hiện như vậy trên danh sách vòng đôi không rỗng**: head.prev phải trỏ tới tail. Tương tự, sau khi xóa cuối của danh sách vòng đơn/dôi không được để tail.next = None nếu vẫn còn nút.

## 9. Cài đặt Python cho danh sách vòng đơn

Ví dụ sau dùng Python 3.10 trở lên. Mỗi thao tác chèn/xóa duy trì **head**, **tail**, **size**; phương thức **values** giới hạn đúng size lượt để tránh vòng lặp vô hạn khi duyệt danh sách hợp lệ.

~~~python
from __future__ import annotations


class SinglyNode:
    def __init__(self, value: int):
        self.value = value
        self.next: SinglyNode | None = None


class CircularSinglyList:
    def __init__(self) -> None:
        self.head: SinglyNode | None = None
        self.tail: SinglyNode | None = None
        self.size = 0

    def append(self, value: int) -> SinglyNode:
        node = SinglyNode(value)
        if self.head is None:
            self.head = self.tail = node
            node.next = node
        else:
            assert self.tail is not None
            node.next = self.head
            self.tail.next = node
            self.tail = node

        self.size += 1
        return node

    def prepend(self, value: int) -> SinglyNode:
        node = SinglyNode(value)
        if self.head is None:
            self.head = self.tail = node
            node.next = node
        else:
            assert self.tail is not None
            node.next = self.head
            self.tail.next = node
            self.head = node

        self.size += 1
        return node

    def pop_front(self) -> int:
        if self.head is None:
            raise IndexError("Danh sách vòng rỗng")

        removed = self.head
        if self.head is self.tail:
            self.head = self.tail = None
        else:
            assert self.tail is not None
            self.head = removed.next
            self.tail.next = self.head

        removed.next = None
        self.size -= 1
        return removed.value

    def pop_back(self) -> int:
        if self.tail is None:
            raise IndexError("Danh sách vòng rỗng")

        if self.head is self.tail:
            return self.pop_front()

        assert self.head is not None
        previous = self.head
        while previous.next is not self.tail:
            assert previous.next is not None
            previous = previous.next

        removed = self.tail
        previous.next = self.head
        self.tail = previous
        removed.next = None
        self.size -= 1
        return removed.value

    def values(self) -> list[int]:
        """Đọc mỗi nút đúng một lần, dựa trên size được duy trì."""
        result: list[int] = []
        current = self.head
        for _ in range(self.size):
            assert current is not None
            result.append(current.value)
            current = current.next
        return result

    def check_invariants(self) -> None:
        """Xác nhận toàn bộ chu trình đúng size và quay về head."""
        if self.size == 0:
            assert self.head is None and self.tail is None
            return

        assert self.head is not None and self.tail is not None
        assert self.tail.next is self.head

        visited: set[int] = set()
        current = self.head
        last = None

        for _ in range(self.size):
            assert current is not None
            assert id(current) not in visited, "Lặp nút quá sớm"
            visited.add(id(current))
            last = current
            current = current.next

        assert current is self.head, "Không quay về head đúng lúc"
        assert last is self.tail, "Tail không phải nút cuối chu trình"


single = CircularSinglyList()
single.check_invariants()  # 0 nút
assert single.values() == []

single.append(20)
single.check_invariants()
assert single.head is single.tail
assert single.head.next is single.head  # Một nút tự liên kết.

single.prepend(10)
single.append(30)
single.check_invariants()
assert single.values() == [10, 20, 30]
assert single.tail.next is single.head

assert single.pop_front() == 10
single.check_invariants()
assert single.values() == [20, 30]

assert single.pop_back() == 30  # Cần tìm nút trước tail.
single.check_invariants()
assert single.head is single.tail
assert single.head.next is single.head

assert single.pop_back() == 20
single.check_invariants()
assert single.head is None and single.tail is None
assert single.size == 0
~~~

Hàm **check_invariants** dùng tập danh tính nút đã thăm nên mất **Θ(n)** thời gian và **O(n)** bộ nhớ phụ. Việc đọc bằng **values** tạo danh sách kết quả nên cũng dùng O(n) bộ nhớ cho kết quả, dù bản thân duyệt chỉ cần một tham chiếu current.

**Không nên suy luận** các phép chèn/xóa O(1) vẫn là O(1) nếu tự động gọi **check_invariants** sau mỗi lần: lúc đó tổng chi phí của mỗi lời gọi có thêm bước kiểm tra Θ(n).

## 10. Cài đặt Python cho danh sách vòng đôi

Mỗi nút có cả **prev** và **next**. Khi một nút là duy nhất, cả hai liên kết đều trỏ về chính nó. Ví dụ sau minh họa thêm hai đầu, xóa hai đầu, duyệt xuôi/ngược và đối chiếu các bất biến.

~~~python
from __future__ import annotations


class DoublyNode:
    def __init__(self, value: int):
        self.value = value
        self.prev: DoublyNode | None = None
        self.next: DoublyNode | None = None


class CircularDoublyList:
    def __init__(self) -> None:
        self.head: DoublyNode | None = None
        self.tail: DoublyNode | None = None
        self.size = 0

    def append(self, value: int) -> DoublyNode:
        node = DoublyNode(value)
        if self.head is None:
            node.prev = node.next = node
            self.head = self.tail = node
        else:
            assert self.tail is not None
            node.prev = self.tail
            node.next = self.head
            self.tail.next = node
            self.head.prev = node
            self.tail = node

        self.size += 1
        return node

    def prepend(self, value: int) -> DoublyNode:
        node = DoublyNode(value)
        if self.head is None:
            node.prev = node.next = node
            self.head = self.tail = node
        else:
            assert self.tail is not None
            node.prev = self.tail
            node.next = self.head
            self.tail.next = node
            self.head.prev = node
            self.head = node

        self.size += 1
        return node

    def pop_front(self) -> int:
        if self.head is None:
            raise IndexError("Danh sách vòng rỗng")

        removed = self.head
        if self.head is self.tail:
            self.head = self.tail = None
        else:
            assert self.tail is not None
            self.head = removed.next
            assert self.head is not None
            self.head.prev = self.tail
            self.tail.next = self.head

        removed.prev = removed.next = None
        self.size -= 1
        return removed.value

    def pop_back(self) -> int:
        if self.tail is None:
            raise IndexError("Danh sách vòng rỗng")

        if self.head is self.tail:
            return self.pop_front()

        assert self.head is not None
        removed = self.tail
        self.tail = removed.prev
        assert self.tail is not None
        self.tail.next = self.head
        self.head.prev = self.tail

        removed.prev = removed.next = None
        self.size -= 1
        return removed.value

    def values_forward(self) -> list[int]:
        result: list[int] = []
        current = self.head
        for _ in range(self.size):
            assert current is not None
            result.append(current.value)
            current = current.next
        return result

    def values_backward(self) -> list[int]:
        result: list[int] = []
        current = self.tail
        for _ in range(self.size):
            assert current is not None
            result.append(current.value)
            current = current.prev
        return result

    def check_invariants(self) -> None:
        if self.size == 0:
            assert self.head is None and self.tail is None
            return

        assert self.head is not None and self.tail is not None
        assert self.tail.next is self.head
        assert self.head.prev is self.tail

        visited: set[int] = set()
        current = self.head
        last = None

        for _ in range(self.size):
            assert current is not None
            assert current.next is not None
            assert current.prev is not None
            assert current.next.prev is current
            assert current.prev.next is current
            assert id(current) not in visited, "Lặp nút quá sớm"
            visited.add(id(current))
            last = current
            current = current.next

        assert current is self.head
        assert last is self.tail

        reverse_seen: set[int] = set()
        current = self.tail
        first = None
        for _ in range(self.size):
            assert current is not None
            assert id(current) in visited
            assert id(current) not in reverse_seen
            reverse_seen.add(id(current))
            first = current
            current = current.prev

        assert current is self.tail
        assert first is self.head
        assert reverse_seen == visited


double = CircularDoublyList()
double.check_invariants()
assert double.values_forward() == []

double.append(20)
double.check_invariants()
assert double.head is double.tail
assert double.head.next is double.head
assert double.head.prev is double.head

double.prepend(10)
double.append(30)
double.check_invariants()
assert double.values_forward() == [10, 20, 30]
assert double.values_backward() == [30, 20, 10]
assert double.tail.next is double.head
assert double.head.prev is double.tail

assert double.pop_back() == 30
double.check_invariants()
assert double.values_forward() == [10, 20]

assert double.pop_front() == 10
double.check_invariants()
assert double.head is double.tail
assert double.head.next is double.head
assert double.head.prev is double.head

assert double.pop_front() == 20
double.check_invariants()
assert double.head is None and double.tail is None
assert double.size == 0
~~~

Ở cả hai ví dụ, có thể dùng **while True** và điều kiện quay về start khi muốn duyệt theo liên kết mà không dựa vào size. Trong mã trên, **size** được duy trì đúng để giới hạn số lượt; hàm check_invariants kiểm tra riêng việc chuỗi khép vòng và đi qua đủ các nút.

## 11. Độ phức tạp và đánh đổi

Giả sử danh sách hợp lệ, có n nút, giữ cả head và tail, việc cấp phát nút và đọc/ghi một tham chiếu có chi phí hằng số.

| Thao tác | Vòng đơn | Vòng đôi | Giải thích |
| --- | --- | --- | --- |
| Kiểm tra rỗng | Θ(1) | Θ(1) | Kiểm tra head là None. |
| Đọc head/tail | Θ(1) | Θ(1) | Có sẵn hai tham chiếu. |
| Duyệt n nút đúng một vòng | Θ(n) | Θ(n) | Xử lý mỗi nút một lần. |
| Duyệt ngược trực tiếp | Không có prev | Θ(n) cho toàn bộ vòng | Vòng đôi có prev. |
| Thêm đầu | Θ(1) | Θ(1) | Cập nhật các liên kết ở biên. |
| Thêm cuối | Θ(1) | Θ(1) | Có tail để nối trực tiếp. |
| Xóa đầu | Θ(1) | Θ(1) | Có head/tail. |
| Xóa cuối | Θ(n) khi n ≥ 2, xấu nhất | Θ(1) | Vòng đơn phải tìm nút trước tail; vòng đôi có tail.prev. |
| Chèn sau nút đã biết | Θ(1) | Θ(1) | Nút anchor thuộc danh sách. |
| Xóa nút đã biết | Thường cần nút trước | Θ(1) | Vòng đôi có target.prev; không tính tìm/kiểm chứng target. |
| Tìm theo giá trị | O(n) | O(n) | Có thể phải kiểm tra cả vòng. |
| Truy cập vị trí tùy ý | O(n) xấu nhất | O(n) xấu nhất | Không có truy cập ngẫu nhiên kiểu mảng. |

**Bộ nhớ:** cả hai loại đều cần **O(n)** tổng không gian. Mỗi nút vòng đơn lưu một liên kết next; vòng đôi lưu thêm prev, dẫn đến chi phí trên mỗi nút cao hơn. Các biến head/tail/size chỉ chiếm O(1) bộ nhớ bổ sung.

**Bộ nhớ phụ khi duyệt:** chỉ giữ current/start cần O(1) bộ nhớ; tạo mảng chứa n giá trị như các hàm **values** dùng thêm O(n) bộ nhớ cho kết quả. Kiểm tra không lặp nút bằng **visited set** cũng cần O(n) bộ nhớ phụ.

### So với danh sách tuyến tính

| Thuộc tính | Danh sách tuyến tính | Danh sách vòng |
| --- | --- | --- |
| Liên kết cuối (đơn) | tail.next = None | tail.next = head |
| Liên kết đầu (đôi) | head.prev = None | head.prev = tail |
| Điểm dừng khi duyệt | Gặp None | Quay về start hoặc đếm đủ size |
| Khả năng chuyển từ tail sang head | Cần thao tác riêng | Đi theo next một bước |
| Rủi ro khi điều kiện dừng sai | Có thể bỏ sót nút hoặc lỗi None | Có thể lặp vô hạn |
| Trạng thái một nút | Liên kết biên là None | Nút tự trỏ về mình |

Danh sách vòng **không tự động nhanh hơn** danh sách tuyến tính cho mọi phép toán. Giá trị lớn nhất là khả năng chuyển tiếp liên tục qua ranh giới cuối/đầu và biểu diễn tự nhiên quá trình xử lý theo chu kỳ.

## 12. Ứng dụng: xử lý luân phiên và vòng người chơi

### 12.1. Xếp lịch Round Robin

Giả sử có ba tác vụ A, B, C cần được cấp lượt xử lý lần lượt:

~~~text
A → B → C → A → B → C → ...
~~~

Danh sách vòng đơn mô hình hóa quá trình đó trực tiếp. Một biến **current** trỏ tác vụ đang xử lý; sau mỗi lượt, chỉ cần **current = current.next** để chuyển sang tác vụ tiếp theo.

Nếu muốn xử lý **đúng một vòng**, ta lưu **start = current** rồi dừng khi current quay trở lại start. Nếu hệ thống muốn lặp liên tục cho đến khi một điều kiện bên ngoài xảy ra, không cần dừng sau một vòng, nhưng phải có quy tắc dừng theo yêu cầu nghiệp vụ và xử lý trường hợp không còn tác vụ.

Nếu số tác vụ thay đổi trong lúc chạy, cần xác định cách cập nhật current khi xóa nút hiện tại và không được giữ tham chiếu tới nút đã bị loại khỏi vòng.

### 12.2. Vòng người chơi có thể đổi chiều

Một trò chơi cho người chơi đi lượt xuôi hoặc ngược có thể dùng danh sách vòng đôi:

- Đi xuôi: **current = current.next**.
- Đổi chiều: **current = current.prev**.
- Sau người chơi cuối, đi tiếp tự động quay về người đầu; đi ngược từ người đầu trở về người cuối.

Mỗi lần chuyển lượt là Θ(1) với tham chiếu current hợp lệ, nhưng thêm/xóa người chơi phải giữ các liên kết đối ứng.

### 12.3. Khi nào nên cân nhắc cấu trúc khác?

Nếu chủ yếu cần truy cập theo chỉ số, mảng động thường phù hợp hơn vì hỗ trợ truy cập ngẫu nhiên O(1). Nếu thường xuyên cần tra tác vụ theo khóa, có thể kết hợp bảng băm với danh sách vòng hoặc chọn cấu trúc khác. Danh sách vòng tự thân không giải quyết bài toán tra cứu theo khóa.

## 13. Lỗi thường gặp và cách kiểm tra

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Duyệt vòng bằng **while current is not None** | Duyệt vô hạn khi cấu trúc hợp lệ không rỗng. | Dừng khi quay về start hoặc sau size bước. |
| Kiểm tra current is head trước khi xử lý lần đầu | Bỏ qua toàn bộ danh sách vì current ban đầu đã là head. | Xử lý trước, di chuyển rồi mới so sánh. |
| Dùng current.next is not head để duyệt mọi nút | Bỏ qua tail; với một nút không xử lý gì. | Xử lý current rồi kiểm tra sau bước di chuyển. |
| So sánh **current.value == head.value** để dừng | Dừng sớm nếu nhiều nút có cùng giá trị. | So sánh **current is head** theo danh tính. |
| Quên **tail.next = head mới** khi thêm/xóa đầu vòng đơn | Không đi được từ tail về head mới. | Cập nhật liên kết khép vòng cùng head. |
| Tạo nút duy nhất với next = None | Phá vỡ bất biến vòng. | Nút duy nhất phải trỏ về chính nó. |
| Xóa nút duy nhất nhưng giữ tail cũ | Trạng thái rỗng không nhất quán. | Đặt cả head và tail thành None, size = 0. |
| Trong vòng đôi chỉ sửa next mà quên prev | Đi xuôi có thể đúng, đi ngược sai. | Kiểm tra **x.next.prev is x** và **x.prev.next is x**. |
| Sau xóa cuối đặt tail.next = None | Biến danh sách vòng thành chuỗi không khép. | Nếu còn nút, đặt **tail.next = head**. |
| Dừng khi gặp lại giá trị thay vì nút xuất phát | Dừng sớm với dữ liệu trùng. | Giữ biến start là tham chiếu đối tượng. |
| Có chu trình B ↔ C nhưng head là A | Duyệt đến khi gặp head lần nữa sẽ không dừng. | Kiểm tra vòng phải bao trùm đủ size nút và quay về head. |
| Dùng size sai để giới hạn vòng lặp | Có thể xử lý thiếu/lặp nút. | Duy trì size và đối chiếu cấu trúc khi kiểm thử. |
| Sửa liên kết tùy ý trong khi duyệt | Bỏ sót, lặp nút hoặc đi vào vòng khác. | Xác định rõ thứ tự thao tác và lưu nút kế tiếp trước khi xóa nếu cần. |

**Kiểm chứng bằng tay:** với các vòng có **0, 1, 2 và 3 nút**, hãy viết chuỗi đi theo next từ head. Với vòng đơn/dôi không rỗng, sau đúng size bước phải quay về head; nếu là vòng đôi, làm tương tự theo prev từ tail và kiểm tra các liên kết đối ứng.

## 14. Bài tập tự luyện có đáp án

**Bài 1 — Một nút trong vòng đơn.** Danh sách vòng đơn có duy nhất nút X. Head, tail và X.next phải như thế nào?

*Đáp án:* **head is tail is X** và **X.next is X**; size bằng 1.

**Bài 2 — Một nút trong vòng đôi.** Danh sách vòng đôi chỉ có nút Y. Giá trị của Y.prev và Y.next là gì?

*Đáp án:* Cả hai đều tham chiếu **chính Y**. Head và tail cũng cùng trỏ Y.

**Bài 3 — Chọn điều kiện dừng.** Danh sách vòng đơn A → B → C → A. Đoạn mã dùng while current is not None có dừng không?

*Đáp án:* Không. current liên tục luân chuyển trong A, B, C. Phải dừng sau khi đã xử lý C và current trở lại A (hoặc sau đúng 3 lượt khi size = 3).

**Bài 4 — Vấn đề so sánh giá trị.** Danh sách vòng đơn có ba nút riêng biệt chứa 5 → 7 → 5 → 5 (quay về nút đầu), và thuật toán dừng khi gặp cùng **value** với head. Điều gì xảy ra?

*Đáp án:* Thuật toán có thể dừng sớm tại nút 5 thứ hai mà chưa đi hết vòng. Cần so sánh **danh tính đối tượng** với nút start, không so sánh dữ liệu.

**Bài 5 — Thêm đầu vòng đơn.** Với A → B → A và tail là B, muốn thêm X vào đầu, cần sửa những liên kết nào?

*Đáp án:* **X.next = A**, **B.next = X**, **head = X**; tail vẫn là B và size tăng 1.

**Bài 6 — Xóa đầu vòng đơn.** Với A → B → C → A, xóa A thì liên kết khép vòng phải trở thành gì?

*Đáp án:* Head mới là B, tail vẫn C, **C.next = B**. Nút A được tách và size giảm 1.

**Bài 7 — Xóa cuối.** Vì sao xóa cuối danh sách vòng đơn có tail thường tốn O(n), còn vòng đôi có thể là O(1)?

*Đáp án:* Vòng đơn không có prev; cần duyệt để tìm nút đứng trước tail. Vòng đôi dùng **tail.prev** để lấy trực tiếp nút cuối mới và cập nhật các liên kết.

**Bài 8 — Phân biệt chu trình với vòng hợp lệ.** Có liên kết A → B → C → B, head là A. Tại sao phát hiện chu trình không đủ để kết luận cấu trúc là danh sách vòng hợp lệ?

*Đáp án:* Chu trình chỉ gồm B và C, không quay về head A. Một danh sách vòng hợp lệ phải trở về head sau khi đi qua đúng tất cả nút thuộc danh sách một lần.

**Bài 9 — Duyệt ngược vòng đôi.** Cho A ⇄ B ⇄ C khép vòng, head A và tail C. Nếu bắt đầu tại tail và đi theo prev, thứ tự xử lý đúng một vòng là gì?

*Đáp án:* **C, B, A**, sau đó prev từ A trở về C; lúc ấy dừng.

**Bài 10 — Chi phí một lượt.** Danh sách vòng đơn có n nút. Nếu mỗi lần xử lý một nút mất O(1), duyệt đúng một vòng tốn thời gian và bộ nhớ phụ bao nhiêu?

*Đáp án:* **Θ(n)** thời gian và **O(1)** bộ nhớ phụ khi chỉ giữ current/start. Nếu lưu toàn bộ kết quả hoặc danh sách nút đã thăm, cần thêm O(n) bộ nhớ.

**Bài 11 — Khép vòng sai khi thêm cuối đôi.** Trong vòng đôi A ⇄ B, thêm C bằng cách chỉ gán B.next = C và C.prev = B. Những liên kết nào còn thiếu?

*Đáp án:* C.next phải trỏ tới A, A.prev phải trỏ tới C và **tail = C**. Nếu thiếu các gán đó, vòng hai chiều không còn hợp lệ.

**Bài 12 — Tình huống luân phiên.** Một ứng dụng xử lý lần lượt P, Q, R và tiếp tục quay về P. Nếu có khả năng đi theo thứ tự ngược R, Q, P, nên dùng vòng đơn hay vòng đôi?

*Đáp án:* **Vòng đôi** giúp di chuyển theo cả next và prev trong Θ(1) mỗi lần, miễn là giữ tham chiếu current hợp lệ. Vòng đơn chỉ cho phép đi thuận trực tiếp.

**Ghi nhớ:** Danh sách vòng **khép liên kết** thay vì kết thúc tại None. Với vòng đơn không rỗng, **tail.next is head**; với vòng đôi, còn có **head.prev is tail** và các liên kết đối ứng. Khi duyệt, hãy **xử lý nút rồi dừng khi quay về nút xuất phát**, hoặc duyệt đúng size lần nếu size chính xác. Mọi phép chèn/xóa phải bảo toàn các liên kết khép vòng, đặc biệt khi danh sách chuyển giữa **0, 1 và nhiều nút**.

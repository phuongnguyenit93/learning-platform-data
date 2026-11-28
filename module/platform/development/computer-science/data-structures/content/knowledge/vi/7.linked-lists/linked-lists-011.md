# Ghép, tách và chuyển đoạn nút giữa các danh sách

Trong danh sách liên kết, **ghép** (*concatenate*), **tách** (*split*) và **chuyển đoạn** (*splice/transfer*) có thể được thực hiện bằng cách **đổi liên kết giữa các nút đang tồn tại**, thay vì sao chép từng giá trị. Đây là một lợi thế quan trọng khi ứng dụng cần tái tổ chức chuỗi phần tử, di chuyển một nhóm tác vụ hoặc nối các hàng đợi.

Tuy nhiên, không phải thao tác nào cũng tự động là O(1). Khi đã có tham chiếu tới **các nút biên**, phần sửa liên kết thường chỉ tốn O(1). Nếu chỉ biết **chỉ số**, phải duyệt để tìm các biên; nếu cần xác định **số nút được chuyển** để cập nhật size, cũng có thể phải đếm. Ngoài ra, thao tác đúng phải giữ các bất biến về **head**, **tail**, **size**, liên kết và quyền sở hữu nút.

Bài thuộc chương **Danh sách liên kết** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, nơi chúng ta học cấu trúc dữ liệu qua thao tác, bất biến và độ phức tạp thời gian/bộ nhớ để lựa chọn giải pháp phù hợp. Nội dung sử dụng **danh sách đơn tuyến tính** và **danh sách đôi tuyến tính** làm mô hình chính; danh sách vòng và sentinel được nhắc đến ở những điểm cần điều chỉnh bất biến.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **nối hai danh sách**, **tách một danh sách**, **chuyển một đoạn nút** và **sao chép các giá trị**.
- Vẽ và cập nhật liên kết đúng khi ghép A với B, tách tại chỉ số k và chuyển đoạn [first, last].
- Giữ nguyên **danh tính đối tượng nút** trong các phép chuyển không cấp phát nút mới.
- Duy trì chính xác head/tail/size của **cả nguồn và đích**, kể cả khi một bên rỗng hoặc khi chuyển toàn bộ.
- Nhận biết nguy cơ **tự ghép**, **dùng chung nút giữa hai danh sách**, tạo chu trình hoặc để lại tail sai.
- Cài đặt thao tác chuyển nút với danh sách đơn bằng Python.
- Hiểu cách **splicing đoạn liên tiếp O(1)** trên danh sách đôi khi đã biết các nút biên và số phần tử được chuyển.
- Phân biệt **thời gian sửa liên kết** và **thời gian tìm vị trí/kiểm chứng tính hợp lệ**.
- Phân tích và lựa chọn thuật toán cho những tình huống như hàng đợi, danh sách tác vụ và bộ đệm.

## 2. Chuyển nút không giống sao chép dữ liệu

Xét hai danh sách đơn độc lập:

~~~text
Danh sách A: headA → [10] → [20] → None
                                  ▲
                                 tailA

Danh sách B: headB → [30] → [40] → None
                                  ▲
                                 tailB
~~~

Nếu **ghép bằng cách chuyển quyền sở hữu nút** từ B vào cuối A, ta muốn có:

~~~text
Sau ghép:

A: headA → [10] → [20] → [30] → [40] → None
                                    ▲
                                   tailA

B: headB = None, tailB = None, sizeB = 0
~~~

Các nút 30 và 40 **không được tạo lại**; chúng chỉ được nối vào sau nút 20. Sau thao tác, B không còn sở hữu chuỗi đó.

Đây là hai hợp đồng API khác nhau:

| Cách thực hiện | Hành vi | Tác động tới danh tính nút |
| --- | --- | --- |
| **Ghép bằng chuyển nút** | Thay liên kết, đưa nút của B vào A; làm B rỗng | Giữ nguyên các đối tượng nút |
| **Ghép bằng sao chép** | Tạo những nút mới trong A từ giá trị của B | Nút mới khác nút của B; B vẫn nguyên |
| **Ghép bằng dùng chung đoạn** | A và B cùng trỏ tới một số nút | Rủi ro khi hai danh sách được phép chỉnh sửa độc lập |

Bài này chọn hợp đồng **chuyển quyền sở hữu nút**. Sau thao tác, **mỗi nút thuộc đúng một danh sách**. Không dùng chung những nút có thể sửa liên kết giữa hai cấu trúc độc lập.

### Điều gì xảy ra với tham chiếu từ bên ngoài?

Trong Python, một biến **saved_node** vẫn có thể trỏ tới đối tượng nút trước và sau khi chuyển. Thao tác không thay danh tính nút, nhưng **chuỗi sở hữu của nó đã đổi**. Vì vậy, các thao tác sau đó phải sử dụng API của **danh sách đích**, không tiếp tục giả định nút thuộc danh sách nguồn.

Việc đưa nút ra khỏi một danh sách **không đồng nghĩa giải phóng nó khỏi bộ nhớ**. Khi chuyển nút, chương trình phải giữ nút để tái sử dụng; giải phóng nút ngay sau khi tách sẽ làm hỏng đích trong ngôn ngữ quản lý bộ nhớ thủ công.

## 3. Những bất biến cần giữ ở cả hai danh sách

Với danh sách **đơn tuyến tính** có head, tail, size:

1. **size = 0** khi và chỉ khi head = tail = None.
2. Nếu không rỗng, đi từ head theo next gặp đúng **size nút khác nhau**, kết thúc ở tail, rồi tới None.
3. **tail.next is None**.
4. Không có chu trình.
5. Hai danh sách độc lập **không cùng sở hữu** một đối tượng nút.

Với danh sách **đôi tuyến tính**, cần thêm:

- **head.prev is None** và **tail.next is None** khi không rỗng.
- Với mọi nút x có **x.next = y**, phải có **y.prev is x**.
- Với mọi nút x có **x.prev = p**, phải có **p.next is x**.
- Duyệt ngược từ tail phải gặp đúng những nút ở hướng xuôi theo thứ tự đảo.

Đặc biệt, sau khi chuyển **m nút từ S sang D**:

\[
\text{sizeS}_{mới} = \text{sizeS}_{cũ} - m
\]

\[
\text{sizeD}_{mới} = \text{sizeD}_{cũ} + m
\]

Tổng số nút **không đổi**:

\[
\text{sizeS}_{mới}+\text{sizeD}_{mới}
=\text{sizeS}_{cũ}+\text{sizeD}_{cũ}.
\]

Nếu hai cấu trúc ban đầu sở hữu các tập nút không giao nhau, thì các tập nút sau khi chuyển vẫn không giao nhau. Đây là một bất biến hữu ích để kiểm tra tình trạng **nhân đôi quyền sở hữu**.

## 4. Ghép hai danh sách đơn: nối đuôi trong O(1)

Giả sử A và B có n và m nút. Nếu **cả hai đều lưu head, tail, size**, việc đưa toàn bộ B nối vào cuối A có thể không cần duyệt.

### 4.1. Hai danh sách đều không rỗng

~~~text
Trước:
A: 10 → 20 → None     tailA = 20
B: 30 → 40 → None     headB = 30, tailB = 40

Sửa đúng một liên kết:
tailA.next = headB

Sau:
A: 10 → 20 → 30 → 40 → None
B: rỗng
~~~

Thứ tự cập nhật hợp lý:

1. Giữ tham chiếu tới headB và tailB khi vẫn còn sở hữu B.
2. Gán **tailA.next = headB**.
3. Gán **tailA = tailB**.
4. Tăng **sizeA** thêm **sizeB**.
5. Đưa **headB = tailB = None**, **sizeB = 0**.

Không nên chỉ nối **tailA.next** mà quên thay **tailA**. Nếu tailA vẫn là nút 20, nó có next khác None và lần append tiếp theo của A có thể nối sai vị trí.

### 4.2. Nếu A đang rỗng

Không có tailA để sửa next. Thay vào đó, A **nhận trực tiếp** headB, tailB, sizeB:

~~~text
A: rỗng
B: 30 → 40 → None

Sau:
A: 30 → 40 → None
B: rỗng
~~~

Các đối tượng nút được chuyển nguyên vẹn; không cần chép giá trị hoặc tạo nút mới.

### 4.3. Nếu B rỗng

Nối B rỗng vào A là thao tác **không đổi**: không có nút nào để chuyển. Độ phức tạp là O(1).

### 4.4. Tự ghép là trường hợp nguy hiểm

Không thực hiện **A.concat_move(A)**. Nếu A đang không rỗng, phép gán **tailA.next = headA** sẽ tạo một vòng từ nút cuối về nút đầu, rồi bước “làm rỗng nguồn” có thể xóa luôn metadata của A vì nguồn và đích là cùng một đối tượng.

Với API chuyển toàn bộ nút, cách đơn giản là **từ chối self-concatenation bằng kiểm tra danh tính danh sách**.

### 4.5. Phép ghép bằng chuyển nút có độ phức tạp gì?

Khi head/tail/size hợp lệ, A và B khác đối tượng và **không chia sẻ nút**, ghép B vào A chỉ cần số phép gán cố định:

- **Thời gian:** Θ(1), kể cả khi B chứa hàng triệu nút.
- **Bộ nhớ phụ:** O(1), không cấp phát thêm nút dữ liệu.
- **Đếm size:** O(1) vì cả hai biến size đều sẵn có.

Nếu **không lưu tail**, phải đi đến cuối A trước khi nối, khiến chi phí trường hợp xấu nhất là Θ(n). Nếu **không lưu size**, muốn cập nhật chính xác độ dài có thể phải đếm các nút của B, mất Θ(m).

## 5. Tách một danh sách tại chỉ số k

**Tách tại k** có nghĩa giữ các nút vị trí **0 đến k − 1** trong danh sách gốc, còn các nút vị trí **k đến n − 1** chuyển sang **danh sách mới**. Chỉ số k là **số nút được giữ lại ở bên trái**.

Ví dụ:

~~~text
Ban đầu:
head → [A] → [B] → [C] → [D] → [E] → None
index    0     1     2     3     4

split_off(2):

Bên trái (gốc): A → B → None
Bên phải (mới): C → D → E → None

size trái = 2; size phải = 3
~~~

### 5.1. Tìm nút biên

Với **0 < k < n**, cần tìm nút ở chỉ số **k − 1**, gọi là **before**. Khi đó:

~~~text
before.next = C  (head của đoạn phải)

left_tail = before
right_head = before.next
right_tail = tail cũ
~~~

Sau khi **lưu right_head**, cắt liên kết:

~~~python
right_head = before.next
before.next = None
~~~

Sau đó cập nhật metadata:

~~~text
head trái: giữ nguyên
tail trái: before
size trái: k

head phải: right_head
tail phải: tail cũ
size phải: n - k
~~~

**Thứ tự cần nhớ:** lấy **right_head** trước khi đặt **before.next = None**. Nếu cắt trước mà không lưu, không còn đường đi từ bên trái sang phần cần tách.

### 5.2. Các trường hợp biên

| k | Kết quả | Có cần tìm nút biên không? |
| ---: | --- | --- |
| 0 | Bên trái rỗng; bên phải nhận toàn bộ n nút | Không |
| 1 (n > 1) | Bên trái chỉ giữ head cũ | Không cần đi xa head |
| n − 1 (n > 1) | Bên phải chứa tail cũ | Cần tìm nút ngay trước tail |
| n | Bên phải rỗng; bên trái không đổi | Không |
| k < 0 hoặc k > n | Chỉ số không hợp lệ; không thay đổi cấu trúc | Không |

Với **danh sách đơn**, tìm nút ở k − 1 từ head tốn **Θ(k)** cho 1 ≤ k < n. Bản thân phép cắt liên kết là Θ(1). Với k = 0 hoặc k = n có thể trả kết quả trong Θ(1) mà không duyệt.

### 5.3. Sau khi tách, hai bên phải độc lập

Nếu sau split_off(2) mà vẫn giữ **B.next = C**, danh sách gốc và mới sẽ cùng nhìn thấy C, D, E. Đó là **chia sẻ nút**, không phải tách thành hai cấu trúc có thể chỉnh sửa độc lập.

Trong mô hình chuyển quyền sở hữu, phải có **B.next = None** và cập nhật tail gốc thành B.

## 6. Chuyển đoạn giữa hai danh sách đơn

Xét nguồn S:

~~~text
S: A → B → C → D → E → F → None
   0   1   2   3   4   5
~~~

Muốn **chuyển đoạn [B, C, D]** (start = 1, count = 3) sang **cuối danh sách T**:

~~~text
T trước: X → Y → None

S sau: A → E → F → None
T sau: X → Y → B → C → D → None
~~~

Đây là **một đoạn liên tiếp**, không phải ba lần tìm/xóa/chèn riêng lẻ.

### 6.1. Xác định bốn mốc

Để cắt một đoạn khỏi S, cần:

- **before**: nút đứng trước B, hoặc None nếu B là head.
- **first**: nút đầu đoạn cần chuyển (B).
- **last**: nút cuối đoạn cần chuyển (D).
- **after**: nút ngay sau D theo thứ tự cũ (E), có thể None.

Sơ đồ:

~~~text
... → before → first → ... → last → after → ...
                B             D      E
~~~

### 6.2. Cắt đoạn khỏi nguồn

Đầu tiên lưu **after = last.next**. Sau đó sửa:

~~~text
Nếu before tồn tại: before.next = after
Nếu before là None: S.head = after

Nếu last là S.tail: S.tail = before
~~~

Nếu chuyển toàn bộ nút, **S.head = S.tail = None**. Giảm sizeS đi count.

Để biến đoạn [first, last] thành một chuỗi tách biệt trước khi nối, đặt:

~~~python
last.next = None
~~~

Việc gán này chỉ được thực hiện **sau khi đã lưu after**, nếu không sẽ đánh mất phần sau đoạn.

### 6.3. Nối vào cuối đích

Nếu T không rỗng:

~~~text
T.tail.next = first
T.tail = last
~~~

Nếu T rỗng:

~~~text
T.head = first
T.tail = last
~~~

Cuối cùng tăng sizeT thêm count. **Mọi nút chuyển giữ nguyên value và danh tính đối tượng**.

### 6.4. Phần nào mất O(1), phần nào mất O(n)?

Nếu đã có **before, first, last**, và count đã biết, mọi phép đổi liên kết ở hai danh sách chỉ tốn Θ(1). Nhưng nếu API chỉ nhận **start** và **count**:

- Cần đi từ head để tìm before/first: O(start + 1).
- Cần đi từ first tới last: O(count).
- Tổng **O(start + count)**, xấu nhất O(n), với count > 0.
- Dùng O(1) bộ nhớ phụ và không cấp phát lại những nút được chuyển.

**Cảnh báo:** Một thao tác **chuyển đoạn giữa hai danh sách khác nhau** dễ bảo đảm hơn việc chuyển trong **cùng một danh sách**. Khi chuyển nội bộ, vị trí đích có thể nằm trong chính đoạn được cắt, hoặc chỉ số đích có thể thay đổi sau khi gỡ đoạn. Ví dụ ở bài này từ chối chuyển nội bộ bằng chính API dành cho hai danh sách khác nhau.

## 7. Mã Python đầy đủ: ghép, tách, chuyển đoạn trong danh sách đơn

Ví dụ Python 3.10 trở lên sau đây sử dụng **head**, **tail**, **size**. Các phương thức chuyển **không sao chép dữ liệu** và không tạo nút mới để thay thế nút đang có.

~~~python
from __future__ import annotations


class SNode:
    def __init__(self, value: int):
        self.value = value
        self.next: SNode | None = None


class SinglyList:
    def __init__(self):
        self.head: SNode | None = None
        self.tail: SNode | None = None
        self.size = 0

    def append(self, value: int) -> SNode:
        node = SNode(value)
        if self.tail is None:
            self.head = node
        else:
            self.tail.next = node
        self.tail = node
        self.size += 1
        return node

    def concat_move(self, other: SinglyList) -> None:
        """Chuyển toàn bộ nút của other vào cuối self."""
        if self is other:
            raise ValueError("Không được tự ghép danh sách")
        if other.head is None:
            return

        if self.head is None:
            self.head = other.head
        else:
            self.tail.next = other.head

        self.tail = other.tail
        self.size += other.size

        # other nhường toàn bộ nút cho self.
        other.head = None
        other.tail = None
        other.size = 0

    def split_off(self, index: int) -> SinglyList:
        """Giữ [0, index) ở self; trả về chuỗi [index, size)."""
        if index < 0 or index > self.size:
            raise IndexError("Vị trí tách ngoài phạm vi")

        right = SinglyList()

        if index == self.size:
            return right

        if index == 0:
            right.head = self.head
            right.tail = self.tail
            right.size = self.size
            self.head = None
            self.tail = None
            self.size = 0
            return right

        before = self.head
        for _ in range(index - 1):
            before = before.next

        right.head = before.next
        right.tail = self.tail
        right.size = self.size - index

        before.next = None
        self.tail = before
        self.size = index
        return right

    def move_range_to_end(
        self,
        start: int,
        count: int,
        destination: SinglyList,
    ) -> None:
        """Chuyển count nút từ start ở self sang cuối destination."""
        if self is destination:
            raise ValueError("API này chỉ chuyển giữa hai danh sách khác nhau")
        if not (0 <= start <= self.size and
                0 <= count <= self.size - start):
            raise IndexError("Đoạn chuyển ngoài phạm vi")
        if count == 0:
            return

        before = None
        first = self.head
        for _ in range(start):
            before = first
            first = first.next

        last = first
        for _ in range(count - 1):
            last = last.next
        after = last.next

        # Tách đoạn ra khỏi nguồn.
        if before is None:
            self.head = after
        else:
            before.next = after

        if last is self.tail:
            self.tail = before

        self.size -= count
        if self.size == 0:
            self.head = None
            self.tail = None

        last.next = None

        # Nối đoạn vào cuối đích.
        if destination.head is None:
            destination.head = first
        else:
            destination.tail.next = first

        destination.tail = last
        destination.size += count

    def values(self) -> list[int]:
        result = []
        current = self.head
        while current is not None:
            result.append(current.value)
            current = current.next
        return result

    def check_invariants(self) -> set[int]:
        """Trả tập id các nút; dùng khi học và kiểm thử."""
        if self.size == 0:
            assert self.head is None and self.tail is None
            return set()

        assert self.head is not None and self.tail is not None
        assert self.tail.next is None

        visited = set()
        current = self.head
        last = None
        while current is not None:
            assert id(current) not in visited, "Có chu trình"
            visited.add(id(current))
            last = current
            current = current.next

        assert last is self.tail
        assert len(visited) == self.size
        return visited


# Ghép và tách: giữ nguyên các đối tượng nút.
left = SinglyList()
nodes = [left.append(v) for v in [10, 20, 30, 40, 50]]
right = left.split_off(2)

assert left.values() == [10, 20]
assert right.values() == [30, 40, 50]
assert right.head is nodes[2]
assert left.tail is nodes[1]

# Chuyển hai nút ở vị trí 1, 2 của right vào cuối một đích khác.
receiver = SinglyList()
receiver.append(99)
right.move_range_to_end(1, 2, receiver)

assert right.values() == [30]
assert receiver.values() == [99, 40, 50]
assert receiver.tail is nodes[4]

# Ghép nút 30 trở lại vào left.
left.concat_move(right)
assert left.values() == [10, 20, 30]
assert right.values() == []

# Chuyển nút 40, 50 trở về cuối left.
receiver.move_range_to_end(1, 2, left)
assert receiver.values() == [99]
assert left.values() == [10, 20, 30, 40, 50]
assert left.tail is nodes[4]

# Chuyển toàn bộ danh sách vào một danh sách đang rỗng.
empty = SinglyList()
empty.concat_move(left)
assert empty.values() == [10, 20, 30, 40, 50]
assert left.values() == []
assert empty.head is nodes[0]
assert empty.tail is nodes[4]

# Trường hợp k = size: không có nút nào được tách.
nothing = empty.split_off(empty.size)
assert nothing.values() == []
assert empty.size == 5

# Trường hợp chuyển toàn bộ nút từ nguồn sang cuối đích.
empty.move_range_to_end(0, empty.size, receiver)
assert empty.values() == []
assert receiver.values() == [99, 10, 20, 30, 40, 50]

ids_empty = empty.check_invariants()
ids_left = left.check_invariants()
ids_right = right.check_invariants()
ids_receiver = receiver.check_invariants()
assert not (ids_empty & ids_receiver)
assert not (ids_left & ids_receiver)
assert not (ids_right & ids_receiver)
assert len(ids_receiver) == 6

# Không cho tự ghép; không làm thay đổi cấu trúc khi báo lỗi.
try:
    receiver.concat_move(receiver)
except ValueError:
    pass
else:
    raise AssertionError("Phải từ chối tự ghép")

receiver.check_invariants()
~~~

### Vì sao không cấp phát n nút trong concat_move?

Phương thức **concat_move** chỉ sửa một liên kết giữa hai chuỗi, đổi tail và các con số size. Việc nguồn trở thành rỗng **không xóa đối tượng nút**; các nút vẫn đi tới được từ head của đích.

**split_off** tạo **một đối tượng danh sách quản lý mới**, không tạo lại các nút dữ liệu đã có. Nếu tách ở giữa, phải tìm nút trước điểm tách; nếu tách ở hai đầu, chỉ cần cập nhật metadata.

**move_range_to_end** có thể duyệt để tìm các nút biên. Sau khi xác định, phần nối/cắt là số phép gán cố định. Trong ví dụ, các biến **nodes** giữ tham chiếu tới các đối tượng cũ, cho phép kiểm tra không có nút nào bị thay thế.

Hàm **check_invariants** dùng tập danh tính nút để phát hiện chu trình và đếm nút, nên có **Θ(n)** thời gian và **O(n)** bộ nhớ phụ. Nó phục vụ kiểm thử, không thuộc chi phí của mỗi lần ghép/chuyển cơ bản.

## 8. Danh sách đôi: chuyển đoạn khi đã biết hai đầu mút

Với danh sách đôi, mỗi nút giữ **prev** và **next**. Giả sử có một đoạn liên tiếp **first → ... → last** của danh sách nguồn S, muốn chuyển nó sang danh sách đích D **ngay trước nút before**.

~~~text
Nguồn trước:
S: A ⇄ B ⇄ C ⇄ D ⇄ E
       ▲       ▲
      first    last

Đích trước:
T: X ⇄ Y ⇄ Z
       ▲
     before

Nguồn sau:
S: A ⇄ E

Đích sau:
T: X ⇄ B ⇄ C ⇄ D ⇄ Y ⇄ Z
~~~

Trong sơ đồ, **before là nút Y** của danh sách đích. Nếu before chỉ tới nút khác, vị trí chèn cũng khác. Quan trọng hơn tên nút là tính kề nhau của các tham chiếu được sửa.

### 8.1. Cắt đoạn khỏi nguồn

Giữ hai hàng xóm ngoài đoạn:

~~~text
left  = first.prev
right = last.next
~~~

Nối phần nguồn còn lại:

~~~text
Nếu left tồn tại:  left.next = right
Nếu left là None:  S.head = right

Nếu right tồn tại: right.prev = left
Nếu right là None: S.tail = left
~~~

Khi chuyển **toàn bộ nguồn**, left và right đều None, khiến S.head = S.tail = None.

### 8.2. Nối đoạn vào đích

Nếu muốn chèn trước một nút before thuộc D:

~~~text
dst_right = before
dst_left  = before.prev
~~~

Nếu muốn nối cuối D, dùng **dst_right = None** và **dst_left = D.tail**.

Sau đó:

~~~text
first.prev = dst_left
last.next = dst_right

Nếu dst_left tồn tại: dst_left.next = first
Nếu không:            D.head = first

Nếu dst_right tồn tại: dst_right.prev = last
Nếu không:             D.tail = last
~~~

Các nút **bên trong đoạn** không cần sửa liên kết. Ví dụ, khi chuyển B ⇄ C ⇄ D, quan hệ B.next = C, C.prev = B, C.next = D, D.prev = C giữ nguyên.

### 8.3. Tại sao có thể O(1)?

Nếu đầu vào đã bao gồm:

- Tham chiếu hợp lệ tới **first** và **last** của cùng một đoạn liên tiếp thuộc S.
- Số lượng nút trong đoạn **count** đã được xác định chính xác.
- Tham chiếu hợp lệ tới **before** thuộc D hoặc một quy ước rõ ràng rằng before = None là chèn cuối.
- S và D là **hai danh sách khác nhau, không dùng chung nút**.

thì thao tác cắt và nối chỉ đụng tới các nút biên, nên mất **Θ(1)** thời gian, **O(1)** bộ nhớ phụ, bất kể count lớn đến đâu.

Tuy nhiên, nếu API chỉ có first/last mà **không biết count**, muốn cập nhật size chính xác thường phải đếm các nút từ first tới last, mất **Θ(count)**. Nếu cần kiểm chứng first/last thực sự liên tiếp, kiểm tra quyền sở hữu hoặc tìm before theo chỉ số, cũng có thêm chi phí. Những điều kiện đó không được bỏ qua trong phân tích thuật toán đầy đủ.

## 9. Cài đặt Python: splice đoạn trong danh sách đôi

Ví dụ tiếp theo sử dụng head/tail/size, **không dùng sentinel**. Phương thức **splice_known_before** yêu cầu những tham chiếu nút đáng tin cậy; phương thức **move_by_index_before** là giao diện an toàn hơn cho người dùng nhập chỉ số, vì nó tự định vị hai đầu đoạn và đích trước khi sửa liên kết.

~~~python
from __future__ import annotations


class DNode:
    def __init__(self, value: int):
        self.value = value
        self.prev: DNode | None = None
        self.next: DNode | None = None


class DoublyList:
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

    def node_at(self, index: int) -> DNode:
        if index < 0 or index >= self.size:
            raise IndexError("Chỉ số ngoài phạm vi")

        if index <= self.size - 1 - index:
            current = self.head
            for _ in range(index):
                current = current.next
        else:
            current = self.tail
            for _ in range(self.size - 1 - index):
                current = current.prev

        assert current is not None
        return current

    def splice_known_before(
        self,
        first: DNode,
        last: DNode,
        count: int,
        destination: DoublyList,
        before: DNode | None = None,
    ) -> None:
        """Chuyển đoạn [first, last] sang trước before ở destination.

        Tiền điều kiện:
        - Hai danh sách khác nhau và không dùng chung nút.
        - first..last là đoạn liên tiếp thuộc self.
        - count đúng bằng số nút trong đoạn và > 0.
        - before thuộc destination hoặc bằng None để nối cuối.
        """
        if self is destination:
            raise ValueError("Không chuyển nội bộ bằng API này")
        if count <= 0 or count > self.size:
            raise ValueError("Độ dài đoạn không hợp lệ")

        left = first.prev
        right = last.next

        # 1. Gỡ cả đoạn khỏi nguồn.
        if left is None:
            self.head = right
        else:
            left.next = right

        if right is None:
            self.tail = left
        else:
            right.prev = left

        self.size -= count

        # 2. Xác định biên đích; None nghĩa là nối cuối.
        dst_right = before
        dst_left = destination.tail if before is None else before.prev

        # 3. Nối đoạn vào đích; các liên kết bên trong đoạn giữ nguyên.
        first.prev = dst_left
        last.next = dst_right

        if dst_left is None:
            destination.head = first
        else:
            dst_left.next = first

        if dst_right is None:
            destination.tail = last
        else:
            dst_right.prev = last

        destination.size += count

    def move_by_index_before(
        self,
        start: int,
        count: int,
        destination: DoublyList,
        destination_index: int,
    ) -> None:
        """Chuyển đoạn từ vị trí start sang trước vị trí đích."""
        if self is destination:
            raise ValueError("Không chuyển nội bộ bằng API này")
        if not (0 <= start <= self.size and
                0 <= count <= self.size - start):
            raise IndexError("Đoạn nguồn ngoài phạm vi")
        if not (0 <= destination_index <= destination.size):
            raise IndexError("Vị trí đích ngoài phạm vi")
        if count == 0:
            return

        # Định vị mọi tham chiếu trước khi sửa liên kết.
        first = self.node_at(start)
        last = first
        for _ in range(count - 1):
            last = last.next

        before = (
            destination.node_at(destination_index)
            if destination_index < destination.size else None
        )
        self.splice_known_before(first, last, count, destination, before)

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

    def check_invariants(self) -> set[int]:
        if self.size == 0:
            assert self.head is None and self.tail is None
            return set()

        assert self.head is not None and self.tail is not None
        assert self.head.prev is None
        assert self.tail.next is None

        visited = set()
        current = self.head
        previous = None
        count = 0
        while current is not None:
            assert id(current) not in visited, "Chu trình theo next"
            visited.add(id(current))
            assert current.prev is previous
            if previous is not None:
                assert previous.next is current
            previous = current
            current = current.next
            count += 1

        assert previous is self.tail
        assert count == self.size

        current = self.tail
        following = None
        reverse_count = 0
        while current is not None:
            assert id(current) in visited
            assert current.next is following
            following = current
            current = current.prev
            reverse_count += 1
            assert reverse_count <= self.size

        assert following is self.head
        assert reverse_count == self.size
        return visited


source = DoublyList()
nodes = [source.append(v) for v in [1, 2, 3, 4, 5]]

target = DoublyList()
target_nodes = [target.append(v) for v in [10, 20, 30]]

# Chuyển đoạn [2, 3, 4] vào trước vị trí 1 (nút 20).
source.move_by_index_before(1, 3, target, 1)
source.check_invariants()
target.check_invariants()
assert source.values_forward() == [1, 5]
assert target.values_forward() == [10, 2, 3, 4, 20, 30]
assert target.values_backward() == [30, 20, 4, 3, 2, 10]
assert target.node_at(1) is nodes[1]
assert target.node_at(3) is nodes[3]

# Chuyển tail của nguồn vào đầu đích.
source.move_by_index_before(1, 1, target, 0)
source.check_invariants()
target.check_invariants()
assert source.values_forward() == [1]
assert target.values_forward() == [5, 10, 2, 3, 4, 20, 30]

# Chuyển nốt nút duy nhất của nguồn sang cuối đích.
source.move_by_index_before(0, 1, target, target.size)
source.check_invariants()
target.check_invariants()
assert source.values_forward() == []
assert target.values_forward() == [5, 10, 2, 3, 4, 20, 30, 1]
assert target.tail is nodes[0]

# Các tập nút của hai danh sách sau chuyển không giao nhau.
assert not (source.check_invariants() & target.check_invariants())

try:
    target.splice_known_before(
        target.head, target.head, 1, target, None
    )
except ValueError:
    pass
else:
    raise AssertionError("Cần từ chối chuyển nội bộ sai hợp đồng")

assert target.size == 8
~~~

### Đọc đúng hợp đồng của splice_known_before

**splice_known_before** không tìm, không đếm và không duyệt để xác minh rằng first..last thực sự là một đoạn gồm count nút của self. Vì thế, khi đầu vào thỏa **tiền điều kiện**, phần cắt-nối mất Θ(1). Nếu người gọi truyền sai count hoặc truyền nút thuộc danh sách khác, cấu trúc có thể hỏng.

**move_by_index_before** an toàn hơn trước chỉ số không hợp lệ vì kiểm tra biên và tự định vị tất cả các nút từ chính danh sách trước khi sửa, nên không cho người gọi cung cấp một đoạn có endpoints không nhất quán. Nó vẫn giả định hai đối tượng danh sách không bị dùng chung nút từ trước.

Cả hai phương thức giữ các đối tượng nút nguyên vẹn. Biến **nodes[1]** vẫn chỉ đúng nút chứa 2 dù nút ấy đã chuyển từ source sang target.

## 10. Chi phí tìm biên so với chi phí sửa liên kết

Cách viết “**splice O(1)**” chỉ phản ánh một pha của thuật toán. Để phân tích đúng, phải biết API nhận **tham chiếu nút** hay **chỉ số/giá trị**.

Giả sử nguồn có n nút, chuyển đoạn m nút bắt đầu ở chỉ số k sang đích có t nút.

### Với danh sách đơn

Khi nhận **k, m** để chuyển đoạn vào cuối đích:

- Tìm nút đầu đoạn và nút trước nó mất O(k + 1).
- Tìm nút cuối đoạn mất O(m).
- Cắt và nối mất Θ(1).
- **Tổng thời gian O(k + m)** với m > 0; xấu nhất O(n).
- Bộ nhớ phụ O(1).

Đặc biệt, **ghép toàn bộ hai danh sách bằng tail** có thể làm Θ(1) mà không phải tìm cả đoạn. Do đó, dùng một phương thức chuyển đoạn tổng quát để ghép toàn bộ có thể kém hiệu quả hơn phương thức **concat_move** chuyên biệt.

### Với danh sách đôi

Nếu biết **first, last, count, before**:

- Đọc first.prev và last.next: Θ(1).
- Cắt các liên kết nguồn: Θ(1).
- Nối vào đích: Θ(1).
- Cập nhật hai biến size: Θ(1).

Nếu chỉ biết **chỉ số**, cần tìm first và before, và thường vẫn phải tìm last hoặc đếm đoạn. Nếu danh sách đôi lưu tail, có thể tìm nút theo chỉ số từ **đầu gần hơn**, với chi phí:

\[
\Theta(1+\min(i,n-1-i))
\]

cho một chỉ số i hợp lệ. Tổng thời gian thao tác theo chỉ số vẫn có thể là O(n + t), không tự động O(1).

### Nếu count không sẵn có thì sao?

Việc sửa liên kết có thể nối một đoạn dài m trong O(1) nếu đã biết first và last. Nhưng để cập nhật size chính xác cần biết số nút m. Nếu không có metadata kích thước đoạn, phải duyệt để đếm hoặc chấp nhận không duy trì size trong O(1). Đây là một đánh đổi **API và metadata**, không phải giới hạn của riêng phép gán con trỏ.

## 11. Bảng trường hợp biên và những bất biến cần kiểm tra

| Trường hợp | Kết quả đúng | Rủi ro thường gặp |
| --- | --- | --- |
| Ghép B rỗng vào A | A giữ nguyên, B vẫn rỗng | Sửa tail không cần thiết |
| Ghép B có nút vào A rỗng | A nhận head/tail/size của B, B rỗng | Đọc tailA.next khi tailA là None |
| Tự ghép A vào A | API từ chối trước khi sửa | Tạo chu trình và làm mất metadata |
| Tách tại k = 0 | Gốc rỗng, danh sách mới nhận toàn bộ | Hai danh sách cùng trỏ một chuỗi |
| Tách tại k = n | Danh sách mới rỗng, gốc giữ nguyên | Đi quá tail để tìm vị trí n |
| Tách ở giữa | Tail trái kết thúc ở None, head phải là nút k | Cắt trước khi lưu head phải |
| Chuyển đoạn ở đầu nguồn | Head nguồn đổi sang after | Head vẫn chỉ nút đã chuyển |
| Chuyển đoạn chứa tail nguồn | Tail nguồn trở thành before | Tail cũ không còn thuộc nguồn |
| Chuyển toàn bộ nguồn | Head/tail nguồn đều None, size = 0 | Chỉ đặt một trong hai về None |
| Chuyển vào đích rỗng | Head = first, tail = last | Chỉ sửa tail, bỏ quên head |
| Chèn đoạn trước head đích đôi | Head mới là first | first.prev phải là None |
| Nối đoạn cuối đích đôi | Tail mới là last | last.next phải là None |
| Chuyển count = 0 | Không thay đổi cấu trúc | Gỡ/nối nhầm một nút |
| Hai danh sách có nút chung từ trước | Vi phạm tiền điều kiện | Chu trình, nhân đôi sở hữu, metadata không đúng |
| Nút bên ngoài giữ tham chiếu vào đoạn | Tham chiếu vẫn tới nút ấy, nhưng chủ sở hữu thay đổi | Gọi API của danh sách cũ |

Để kiểm thử, hãy kiểm tra cả **tập danh tính nút**. Số phần tử đúng và thứ tự giá trị đúng **chưa đủ** để bảo đảm không có một nút bị lặp ở cả hai danh sách.

## 12. Độ an toàn, sở hữu nút và thay đổi đồng thời

### 12.1. Quyền sở hữu phải rõ ràng

Trong các ví dụ, mỗi nút thuộc về **một** danh sách tại một thời điểm. Nguồn **nhường** nút cho đích sau khi chuyển; source không còn được sửa các liên kết của đoạn ấy như thể nó vẫn sở hữu đoạn.

Nếu bạn cố ý sử dụng cấu trúc **persistent/immutable** có chia sẻ đuôi, đó là thiết kế khác: không được sửa liên kết của đoạn dùng chung theo cách ở bài này nếu còn các danh sách khác đang phụ thuộc vào nó.

### 12.2. Không giải phóng nút đang được chuyển

Với Python, khi một đối tượng nút còn được tham chiếu từ đích hoặc biến bên ngoài, nó vẫn có thể tồn tại sau khi gỡ khỏi nguồn. Với C/C++, nếu nút được cấp phát động, **không free/delete nút rồi nối nó sang đích**, vì đó là dùng bộ nhớ đã giải phóng. Cần xác định chủ sở hữu chịu trách nhiệm giải phóng nút khi nó thực sự không còn được sử dụng.

**Chuyển** và **xóa vĩnh viễn** là hai nghiệp vụ khác nhau. Một API move nên giữ nguyên nút; một API delete có thể thu hồi tài nguyên theo hợp đồng riêng.

### 12.3. Bảo đảm tiền điều kiện trước khi thay liên kết

Với API nhận chỉ số, hãy kiểm tra **độ dài đoạn, vị trí đích và việc source khác destination** trước khi cắt. Với API nhận tham chiếu, cần có hợp đồng rõ rằng first/last/anchor thuộc đúng danh sách và đoạn liên tiếp.

Nếu muốn xác minh tất cả tiền điều kiện bằng một lượt duyệt, hãy cộng chi phí đó vào độ phức tạp. Thao tác cắt-nối O(1) không làm cho **kiểm tra sở hữu nút** tự nhiên trở thành O(1).

### 12.4. Trạng thái trung gian và đa luồng

Trong một lần splice, sẽ có khoảnh khắc đoạn đã bị gỡ khỏi nguồn nhưng chưa nối hoàn chỉnh vào đích. Nếu một luồng khác có thể duyệt/chèn/xóa cùng lúc, nó có thể nhìn thấy trạng thái chưa nhất quán.

**An toàn liên kết** trong bài nghĩa là khi thao tác hoàn tất, các bất biến của cả hai danh sách đúng. Nó **không tự bảo đảm tính nguyên tử hay an toàn đa luồng**. Hệ thống có truy cập đồng thời cần cơ chế đồng bộ, khóa cả nguồn và đích theo thứ tự nhất quán để tránh deadlock, hoặc một chiến lược giao dịch khác.

### 12.5. Iterator và tham chiếu vị trí

Iterator của source đang duyệt có thể bỏ qua hoặc đi theo đoạn đã được chuyển sang destination nếu các liên kết thay đổi. Nếu API hứa hẹn iterator vẫn hợp lệ, cần định nghĩa rõ hành vi hoặc phát hiện sửa đổi trong khi duyệt.

Tương tự, một biến lưu chỉ số vị trí của nút trước chuyển có thể không còn đúng vì thứ tự trong cả hai danh sách đã thay đổi. **Danh tính nút giữ nguyên**, nhưng **vị trí và chủ sở hữu** đã đổi.

## 13. So sánh độ phức tạp

Giả sử danh sách hợp lệ, nguồn và đích khác nhau, không chia sẻ nút, đọc/ghi tham chiếu O(1). Bảng tách riêng việc xác định biên với việc sửa liên kết.

| Thao tác | Thời gian | Bộ nhớ phụ | Điều kiện |
| --- | --- | --- | --- |
| Ghép toàn bộ B vào cuối A, cả hai có head/tail/size | **Θ(1)** | O(1) | Chuyển quyền sở hữu, B rỗng sau ghép |
| Ghép nếu A không lưu tail | O(n) xấu nhất | O(1) | Phải duyệt tìm nút cuối A |
| Tách đơn tại 0 hoặc n | **Θ(1)** | O(1) | Không cần tìm nút ở giữa |
| Tách đơn tại 0 < k < n | **Θ(k)** | O(1) | Tìm nút ngay trước vị trí k |
| Chuyển đoạn đơn theo start/count sang cuối | **O(start + count)** | O(1) | count > 0, tìm hai biên từ head |
| Chuyển đoạn đôi với first, last, count, before đã biết | **Θ(1)** | O(1) | Bốn tham chiếu/metadata hợp lệ |
| Chuyển đoạn đôi theo chỉ số nguồn và đích | **O(n + t)** xấu nhất | O(1) | Cần tìm nút trong hai danh sách |
| Kiểm tra một đoạn có m nút | **Θ(m)** | O(1) hoặc O(m) | O(m) bộ nhớ nếu lưu tập nút đã thăm |
| Sao chép n giá trị sang những nút mới | **Θ(n)** | O(n) | Tạo nút và giữ nguồn cũ |
| Kiểm tra toàn bộ bất biến với tập danh tính | **Θ(n)** | O(n) | Phục vụ kiểm thử/gỡ lỗi |

**Bộ nhớ tổng thể:** Nối/tách/chuyển bằng liên kết không làm tăng số nút dữ liệu; tổng bộ nhớ của tất cả nút vẫn O(n + t). Tách có thể cấp phát **một đối tượng danh sách quản lý mới** (O(1)), còn bản thân các nút được tái sử dụng.

**Giới hạn của kết luận O(1):** Nếu phải đi tìm một nút biên hoặc xác minh quyền sở hữu bằng duyệt, chi phí toàn bộ thao tác phải tính thêm bước đó. Không nên viết “di chuyển một đoạn bất kỳ luôn O(1)” khi đầu vào thực tế là các chỉ số.

## 14. Ứng dụng thực tế

### 14.1. Hàng đợi tác vụ

Giả sử một hệ thống có hai hàng đợi liên kết: **đang chờ** và **sẵn sàng**. Khi một nhóm tác vụ liên tiếp đã được chuẩn bị, có thể chuyển toàn bộ đoạn nút từ hàng chờ sang cuối hàng sẵn sàng mà không tạo lại các nút.

Nếu chuyển **toàn bộ danh sách**, có thể dùng concat_move trong O(1) khi có tail. Nếu chỉ chuyển một đoạn chọn theo vị trí, phải cộng chi phí tìm đoạn đó.

### 14.2. Trình quản lý thứ tự công việc

Một trình chỉnh sửa danh sách công việc có thể cần chuyển một nhóm dòng liên tiếp lên trước một mục khác. Nếu dùng **danh sách đôi** và giao diện đang giữ tham chiếu tới **first**, **last**, **before**, việc sửa liên kết có thể chỉ O(1). Nhưng nếu người dùng chỉ cung cấp số thứ tự dòng, hệ thống cần tìm vị trí trong cấu trúc trước.

Đặc biệt, trường hợp **chuyển trong cùng một danh sách** cần kiểm tra vị trí đích không nằm trong đoạn được chuyển và định nghĩa chỉ số trước/sau khi gỡ đoạn. Mã ví dụ dành cho **hai danh sách độc lập** không tự xử lý trường hợp này.

### 14.3. Di chuyển dữ liệu mà giữ danh tính đối tượng

Nếu một thành phần khác đang giữ tham chiếu tới nút (ví dụ map từ khóa sang nút), chuyển nút thật cho phép tham chiếu ấy vẫn hợp lệ về **danh tính**. Tuy nhiên, hệ thống phải cập nhật metadata về danh sách sở hữu hoặc vị trí của nút nếu chúng được lưu riêng.

### 14.4. Khi nào nên dùng mảng thay vì danh sách?

Nếu ứng dụng thường xuyên yêu cầu truy cập phần tử ở một chỉ số bất kỳ, **mảng động** thường phù hợp hơn vì truy cập O(1). Danh sách liên kết chỉ phát huy lợi thế ghép/chuyển O(1) khi chương trình có sẵn những tham chiếu biên cần thiết; nếu mỗi thao tác đều phải tìm vị trí O(n), lợi thế này có thể bị giảm đáng kể.

## 15. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Ghép A với chính A | Tạo chu trình hoặc làm rỗng sai metadata | Từ chối nếu source is destination |
| Chỉ gán tailA.next = headB | TailA vẫn là tail cũ, có next khác None | Chuyển tailA sang tailB |
| Ghép mà không làm rỗng B | Hai danh sách cùng sở hữu nút | Đặt headB/tailB None, sizeB = 0 |
| Tách giữa nhưng quên before.next = None | Hai danh sách chia sẻ đuôi | Cắt liên kết sau khi lưu head phải |
| Cắt before.next trước khi lưu first/right_head | Mất điểm vào chuỗi cần chuyển | Lưu các mốc trước khi thay liên kết |
| Chuyển đoạn chứa head nhưng không sửa head nguồn | Head nguồn chỉ nút đã chuyển | Nếu before là None, head = after |
| Chuyển đoạn chứa tail nhưng không sửa tail nguồn | Tail nguồn trỏ vào đích | Nếu last là tail, tail = before |
| Chuyển toàn bộ nhưng chỉ đưa head về None | Tail nguồn và size vẫn sai | Đồng bộ cả head/tail/size |
| Chuyển sang đích rỗng mà không cập nhật head | Đích có tail nhưng không đi tới nút từ head | Nếu đích rỗng, head = first |
| Trong danh sách đôi chỉ sửa next | Các liên kết prev không đối ứng | Sửa cả predecessor.next và successor.prev |
| Không lưu after trước khi thay last.next | Mất phần nguồn sau đoạn chuyển | Lưu after = last.next |
| Đếm sai số nút chuyển | Size nguồn/đích lệch thực tế | Cần count chính xác hoặc phải đếm |
| Chuyển nút giữa hai danh sách có phần tử chung | Tạo chu trình hoặc nhân đôi quyền sở hữu | Bảo đảm nguồn/đích độc lập trước thao tác |
| Gọi splice với nút ngoài danh sách | Có thể làm hỏng nhiều chuỗi liên kết | Kiểm chứng quyền sở hữu hoặc chỉ truyền nút từ API đáng tin |
| Giải phóng nút trước khi nối vào đích | Tham chiếu tới bộ nhớ không còn hợp lệ | Chuyển quyền sở hữu, không delete/free nút |
| Duyệt đồng thời khi đang chuyển | Iterator có thể bỏ sót hoặc lặp nút | Đồng bộ hoặc định nghĩa quy tắc sửa đổi |
| Áp dụng thuật toán tuyến tính cho danh sách vòng/sentinel | Điều kiện kết thúc và liên kết biên sai | Dựa trên bất biến của đúng biến thể |

Một phương pháp gỡ lỗi hữu ích: **vẽ bốn nút biên** ở nguồn (**before, first, last, after**) và hai nút biên ở đích, cập nhật mũi tên từng bước, rồi kiểm tra cả hai danh sách sau thao tác. Đối với danh sách đôi, duyệt thêm hướng ngược.

## 16. Bài tập tự luyện có đáp án

**Bài 1 — Ghép hai danh sách.** A = 1 → 2 → None, B = 3 → 4 → None. Ghép B vào cuối A bằng chuyển nút thì head/tail/size của A và B là gì?

*Đáp án:* A = 1 → 2 → 3 → 4 → None; headA là nút 1, tailA là nút 4, sizeA = 4. B trở thành rỗng với headB = tailB = None, sizeB = 0.

**Bài 2 — Tự ghép.** Vì sao concat_move(A, A) là lỗi trong một API chuyển quyền sở hữu toàn bộ nút?

*Đáp án:* Nút cuối có thể nối về head của chính A, tạo chu trình; bước làm rỗng nguồn cũng làm rỗng metadata của đích vì là cùng một đối tượng. API phải từ chối trước khi thay liên kết.

**Bài 3 — Tách tại k.** Cho A → B → C → D → E, gọi split_off(3) nhận hai chuỗi nào?

*Đáp án:* Chuỗi gốc giữ **A → B → C → None**; chuỗi mới nhận **D → E → None**. Hai bên không dùng chung nút; size tương ứng 3 và 2.

**Bài 4 — Tách hai biên.** Tách tại k = 0 và k = n có phải duyệt tìm nút giữa không?

*Đáp án:* Không. Khi k = 0, chuyển toàn bộ head/tail/size sang danh sách mới; khi k = n, trả danh sách mới rỗng. Cả hai có thể Θ(1).

**Bài 5 — Thứ tự cắt.** Cho P → Q → R → S, cần tách phần bắt đầu ở R. Vì sao phải lưu right_head = Q.next trước khi gán Q.next = None?

*Đáp án:* Nếu cắt trước mà không lưu, không còn tham chiếu qua Q để tìm R và phần đuôi. Lưu right_head giúp giữ quyền truy cập đoạn cần tách.

**Bài 6 — Chuyển đoạn.** Nguồn A → B → C → D → E, đích X → Y. Chuyển đoạn bắt đầu ở vị trí 1 dài 3 vào cuối đích. Kết quả?

*Đáp án:* Nguồn **A → E → None**; đích **X → Y → B → C → D → None**. Mọi nút giữ nguyên đối tượng.

**Bài 7 — Cập nhật tail.** Trong nguồn A → B → C, chuyển đoạn [B, C] sang đích. Tail nguồn mới là ai?

*Đáp án:* Tail nguồn chuyển thành **A**, và **A.next = None**. Nếu để tail là C thì tail trỏ vào đoạn không còn thuộc nguồn.

**Bài 8 — Danh sách đôi.** Có nguồn A ⇄ B ⇄ C ⇄ D, chuyển đoạn [B, C] sang trước Y của đích X ⇄ Y. Những liên kết biên nào cần cập nhật?

*Đáp án:* Nguồn cần **A.next = D**, **D.prev = A**. Đích cần **X.next = B**, **B.prev = X**, **C.next = Y**, **Y.prev = C**; các liên kết nội bộ B ⇄ C giữ nguyên.

**Bài 9 — Vì sao count quan trọng?** Khi biết first/last của một đoạn dài m, sửa liên kết đôi có thể O(1). Nếu không biết m mà cần duy trì size chính xác thì sao?

*Đáp án:* Thường phải duyệt và đếm m nút, tốn Θ(m) thời gian, trừ khi có metadata về số nút của đoạn.

**Bài 10 — Chuyển sang đích rỗng.** Đích chưa có nút, bạn chuyển đoạn [B, C] sang đích. Head/tail của đích là gì?

*Đáp án:* Head = B, tail = C, size = 2; B.prev = None và C.next = None nếu là danh sách đôi tuyến tính.

**Bài 11 — So sánh chi phí.** Vì sao ghép toàn bộ hai danh sách đơn có tail/size có thể Θ(1), nhưng chuyển đoạn theo start/count của một danh sách đơn có thể Θ(n)?

*Đáp án:* Ghép toàn bộ đã có sẵn headB và tailA/tailB; không cần tìm nút. Chuyển đoạn theo chỉ số phải duyệt tới nút đầu và cuối đoạn trước khi sửa liên kết.

**Bài 12 — Cùng danh tính.** Một biến saved trỏ nút C trước khi chuyển C từ nguồn sang đích. Sau chuyển, saved có trỏ sang đối tượng khác không?

*Đáp án:* Không. Saved vẫn trỏ đúng đối tượng C, nhưng C nay thuộc danh sách đích. Không được tiếp tục dùng C làm nút thuộc nguồn.

**Bài 13 — Chuyển trong cùng danh sách.** Vì sao không được sử dụng trực tiếp API move_range_to_end dành cho hai danh sách khác nhau để chuyển đoạn trong cùng một danh sách?

*Đáp án:* Vị trí đích có thể nằm trong đoạn, các chỉ số có thể thay đổi sau khi cắt, và thuật toán có thể tạo chu trình. Phải định nghĩa thuật toán riêng hoặc từ chối như ví dụ.

**Bài 14 — Bất biến tổng kích thước.** Nguồn có 8 nút, đích có 5 nút. Chuyển 3 nút nguồn sang đích. Hai size mới và tổng của chúng bằng bao nhiêu?

*Đáp án:* size nguồn = 5, size đích = 8, tổng vẫn bằng **13**.

**Bài 15 — Tự đánh giá.** Một người nói “chuyển đoạn bất kỳ của danh sách đôi luôn O(1), vì chỉ sửa vài con trỏ”. Phát biểu đúng trong điều kiện nào?

*Đáp án:* Đúng cho **pha cắt-nối**, khi đã biết first, last, count, vị trí đích qua tham chiếu hợp lệ và hai danh sách độc lập. Nếu còn phải tìm/đếm/kiểm chứng các biên thì tổng thời gian có thể cao hơn.

**Ghi nhớ:** Ghép, tách và chuyển đoạn nút có thể thực hiện **không sao chép dữ liệu**, giữ nguyên danh tính đối tượng. Với head/tail/size, nối toàn bộ danh sách vào cuối danh sách khác thường là **Θ(1)**. Tách ở chỉ số và chuyển đoạn theo chỉ số cần tính thêm chi phí duyệt. Trong danh sách đôi, **cắt-nối cả một đoạn có biên và số nút đã biết** có thể là **Θ(1)**. Luôn cập nhật **cả nguồn và đích**, bảo đảm các nút không bị hai danh sách cùng sở hữu, và xác minh đúng head/tail/size sau thao tác.

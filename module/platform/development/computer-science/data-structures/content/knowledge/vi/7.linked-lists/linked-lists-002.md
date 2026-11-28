# Con trỏ đầu, con trỏ cuối và bất biến của danh sách rỗng

Một danh sách liên kết đơn (*singly linked list*) gồm các nút nối tiếp nhau qua trường **next**. Để biết danh sách bắt đầu ở đâu, cấu trúc lưu một tham chiếu **head** (con trỏ đầu). Nếu muốn thêm phần tử ở cuối mà không phải duyệt từ đầu, danh sách có thể lưu thêm tham chiếu **tail** (con trỏ cuối). Hai tham chiếu này tạo nên “cửa vào” và điểm kết thúc của chuỗi nút.

Trong mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, phần học về **Danh sách liên kết** giúp xây dựng nền tảng về bất biến, các thao tác và độ phức tạp thời gian/bộ nhớ. Bài này tập trung vào cách quản lý **head**, **tail** và đặc biệt là **trạng thái rỗng**: một lỗi cập nhật con trỏ có thể khiến danh sách mất nút, trỏ nhầm vào nút đã xóa hoặc báo sai số phần tử.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Chỉ ra **head** và **tail** trên sơ đồ danh sách liên kết đơn; giải thích điểm khác nhau giữa chúng.
- Xác định chính xác head, tail và size ở danh sách **rỗng**, **một nút** và **nhiều nút**.
- Phát biểu và kiểm tra những **bất biến** cần giữ trước và sau thao tác.
- Cập nhật đúng head/tail khi thêm đầu, thêm cuối, xóa đầu và xóa cuối.
- Giải thích vì sao có tail giúp nối cuối **O(1)** nhưng không tự động làm xóa cuối thành **O(1)** trong danh sách liên kết đơn.
- Nhận diện lỗi liên kết “treo”, tail lỗi thời, chu trình và nhầm lẫn giữa nút rỗng với danh sách rỗng.

## 2. Head và tail thực sự chỉ vào đâu?

Xét danh sách chứa 4, 8, 12:

~~~text
head
  │
  ▼
[ 4 | next ] ──► [ 8 | next ] ──► [ 12 | None ]
                                          ▲
                                          │
                                         tail
~~~

- **head** tham chiếu tới **nút đầu tiên** (ở đây chứa 4). Đi theo **next** từ head sẽ gặp những nút còn lại.
- **tail** tham chiếu tới **nút cuối cùng** (ở đây chứa 12). Vì không có nút tiếp theo, **tail.next is None**.
- **head** và **tail** là các tham chiếu đến *nút*, không phải chính giá trị 4 và 12. Hai đầu có thể chứa giá trị bằng nhau nhưng là hai nút khác nhau.
- **tail** không thay thế **head**: danh sách đơn chỉ có liên kết **next**, nên từ tail không có cách trực tiếp lần ngược về nút đứng trước.

Trong Python, hai biến là *tham chiếu đối tượng*; trong C hoặc C++, cách cài đặt tương ứng thường dùng *con trỏ*. Dù ngôn ngữ khác nhau, quy tắc cấu trúc vẫn giống nhau.

Có thể triển khai danh sách đơn **chỉ lưu head**. Bài này chọn mô hình lưu **cả head và tail**, kèm **size** là số nút, để khảo sát cụ thể những bất biến liên quan tới con trỏ cuối.

## 3. Ba trạng thái cần phân biệt

| Trạng thái | head | tail | size | Quan hệ cần đúng |
| --- | --- | --- | ---: | --- |
| **Rỗng** | None | None | 0 | Không có nút nào truy cập được từ head. |
| **Một nút** | Tham chiếu nút duy nhất | **Cùng nút với head** | 1 | **head is tail** và **tail.next is None**. |
| **Từ hai nút** | Nút đầu | Nút cuối | ≥ 2 | **head is not tail**; đi theo next từ head sẽ đến tail rồi None. |

Sơ đồ:

~~~text
(0) Rỗng
    head ──► None
    tail ──► None
    size = 0

(1) Một nút
    head ─┐
          ▼
        [ 7 | None ]
          ▲
    tail ─┘
    size = 1

(2) Nhiều nút
    head ──► [ 7 | • ] ──► [ 9 | • ] ──► [ 11 | None ] ◄── tail
    size = 3
~~~

Ở trạng thái **một nút**, việc head và tail trỏ tới *cùng một đối tượng* là hoàn toàn đúng. Lỗi thường gặp là tạo hai nút riêng biệt có cùng giá trị rồi nghĩ rằng đó là “một nút”.

Ở trạng thái **rỗng**, không có “nút đầu rỗng” hoặc “nút cuối rỗng” trong mô hình này. Cả head lẫn tail đều bằng **None**. Nếu nút thật chứa giá trị **None**, danh sách **vẫn không rỗng**: trạng thái rỗng phụ thuộc vào sự tồn tại của nút, không phụ thuộc nội dung dữ liệu.

> **Phân biệt:** “Danh sách rỗng” nghĩa là không có nút dữ liệu. “Nút có giá trị None” vẫn là một nút. Một số thư viện dùng nút canh gác (*sentinel/dummy node*); khi đó quy tắc biểu diễn rỗng có thể khác. Các bất biến trong bài áp dụng cho cài đặt **không có nút canh gác**.

## 4. Bất biến là hợp đồng của cấu trúc

**Bất biến** (*invariant*) là điều phải đúng với một danh sách ở trạng thái hợp lệ, trước và sau mỗi thao tác hoàn tất. Với mô hình có head, tail, size và không có nút canh gác, ta cần:

1. **Tính nhất quán của trạng thái rỗng:**

   \`size == 0 ⇔ head is None ⇔ tail is None\`.

   Viết cách khác: khi size bằng 0 thì head và tail đều là None; khi có ít nhất một nút thì cả hai đều khác None.

2. **Tính nhất quán của nút cuối:** nếu không rỗng, **tail.next is None**. Tail không được trỏ tới một nút ở giữa chuỗi hay một nút đã bị gỡ ra.

3. **Tính đến được từ đầu:** nếu không rỗng, bắt đầu từ head và đi theo next phải gặp tail, sau đó gặp None. Mọi nút thuộc danh sách đều phải nằm trên đường đi này.

4. **Không có chu trình:** đi theo next không được quay về nút đã đi qua. Nếu có chu trình, thao tác duyệt dựa vào None có thể lặp vô hạn.

5. **Đúng số nút:** nếu lưu biến size, số nút thực tế đi được từ head tới None phải bằng size.

Hệ quả hữu ích:

~~~text
size = 0  → head is None và tail is None
size = 1  → head is tail và tail.next is None
size ≥ 2  → head is not tail và tail.next is None
~~~

Dấu **is** trong Python kiểm tra hai tham chiếu có chỉ **cùng một đối tượng**; toán tử **==** có thể được định nghĩa để so sánh giá trị, không phù hợp cho kiểm tra quan hệ nút đầu/cuối.

Bất biến được yêu cầu tại **ranh giới thao tác**. Trong lúc thực hiện nhiều phép gán, trạng thái trung gian có thể tạm thời chưa thỏa mãn tất cả điều kiện; hàm phải khôi phục các bất biến trước khi hoàn thành. Nếu danh sách được chia sẻ giữa nhiều luồng, cần cơ chế đồng bộ phù hợp để không cho luồng khác quan sát trạng thái trung gian.

### Khi bất biến bị phá vỡ

Ví dụ A: **head is None, tail vẫn trỏ tới nút 5**. Danh sách báo rỗng qua head nhưng tail còn giữ nút; lệnh nối cuối dựa vào tail có thể thêm vào một chuỗi không thể đi tới từ head.

Ví dụ B: **head → 2 → 4 → None, tail trỏ tới nút 2**. Lệnh thêm cuối theo tail sẽ gắn nút mới sau 2, cắt mất khả năng đi tới nút 4 nếu ghi đè liên kết 2.next.

Ví dụ C: **head → 2 → 4 → 2 → ...**. Chuỗi không kết thúc tại None; duyệt thông thường có nguy cơ lặp vô hạn.

Vì vậy, việc cập nhật **tail** cần được xem là một phần của thao tác thay đổi cấu trúc, không phải thông tin phụ có thể sửa sau.

## 5. Thêm phần tử: chuyển trạng thái rỗng thành có nút

### 5.1. Thêm vào danh sách rỗng

Khởi đầu:

~~~text
head = None, tail = None, size = 0
~~~

Tạo nút **new = [10 | None]**. Sau thao tác, **cả head và tail đều chỉ vào new**, size thành 1:

~~~text
head ─┐
      ▼
    [ 10 | None ]
      ▲
tail ─┘
size = 1
~~~

Nếu chỉ cập nhật head mà quên tail, lần append tiếp theo không thể dựa vào tail để nối đúng.

### 5.2. Thêm vào đầu (prepend)

Nếu danh sách đã có nút, ta thực hiện:

~~~python
new = Node(value)
new.next = head
head = new
# Nếu trước khi thêm danh sách rỗng thì tail = new.
~~~

Ví dụ:

~~~text
Trước:
head ──► [ 20 | • ] ──► [ 30 | None ] ◄── tail

Sau prepend(10):
head ──► [ 10 | • ] ──► [ 20 | • ] ──► [ 30 | None ] ◄── tail
~~~

**Tail giữ nguyên** vì nút cuối không đổi. Nhưng nếu danh sách ban đầu rỗng, nút mới đồng thời là đầu và cuối, nên tail phải cập nhật.

Thời gian prepend là **O(1)** vì chỉ cần số phép gán cố định.

### 5.3. Thêm vào cuối (append)

Nếu danh sách **không rỗng**, tail chỉ nút cuối hiện tại. Ta nối tail.next tới nút mới rồi chuyển tail:

~~~python
new = Node(value)          # new.next mặc định là None
tail.next = new
tail = new
~~~

~~~text
Trước:
head ──► [ 10 | • ] ──► [ 20 | None ] ◄── tail

Sau append(30):
head ──► [ 10 | • ] ──► [ 20 | • ] ──► [ 30 | None ] ◄── tail
~~~

Trường hợp **rỗng** phải xử lý riêng: gán **head = new**, **tail = new**. Không thể truy cập **tail.next** khi tail là None.

Với tail hợp lệ, append là **O(1)**. Nếu cấu trúc chỉ lưu head, phải tìm nút cuối bằng cách duyệt, nên append thường là **O(n)**.

## 6. Xóa phần tử: khi nào phải cập nhật cả hai con trỏ?

### 6.1. Xóa đầu (pop front)

Nếu danh sách rỗng, thao tác không có nút để xóa. API có thể ném lỗi hoặc báo thất bại; phải chọn quy ước nhất quán.

Nếu có ít nhất một nút:

1. Lưu nút cũ trong **old = head**.
2. Chuyển **head = old.next**.
3. Nếu **head is None** (vừa xóa nút duy nhất), đặt **tail = None**.
4. Giảm size; có thể tách **old.next = None** để nút bỏ ra không tiếp tục giữ tham chiếu đến chuỗi còn lại.

Ví dụ danh sách hai nút:

~~~text
Trước: head ──► [ A | • ] ──► [ B | None ] ◄── tail
Sau:   head ──────────────► [ B | None ] ◄── tail
~~~

Ở đây tail vẫn là B. Nếu danh sách chỉ có A, sau khi xóa phải là:

~~~text
head = None, tail = None, size = 0
~~~

**Xóa đầu là O(1)** vì không cần tìm nút đứng trước.

### 6.2. Xóa cuối (pop back)

Trường hợp **một nút** có thể xử lý ngay: gán **head = None**, **tail = None**, giảm size từ 1 xuống 0.

Trường hợp **từ hai nút**, muốn bỏ tail, ta cần tìm **nút ngay trước tail**:

~~~text
head ──► [ A | • ] ──► [ B | • ] ──► [ C | None ] ◄── tail
                         prev                 old_tail
~~~

Thao tác:

~~~text
prev.next = None
tail = prev
size = size - 1
~~~

Kết quả:

~~~text
head ──► [ A | • ] ──► [ B | None ] ◄── tail
~~~

Tại sao không thể đi ngược từ tail để lấy prev? Bởi mỗi nút chỉ lưu **next** và không biết ai trỏ đến nó. Để tìm prev, phải duyệt từ head: **O(n)** thời gian trong trường hợp xấu nhất, dù đã có tail.

> **Giới hạn quan trọng:** Có tail giúp **thêm cuối O(1)**, nhưng **xóa cuối vẫn O(n)** trong danh sách liên kết đơn thông thường. Danh sách liên kết đôi có liên kết **prev** và các điều kiện cập nhật khác.

## 7. Cài đặt Python tự chứa

Mã sau minh họa trực tiếp trạng thái rỗng và các biến đổi head/tail. Cài đặt này **không có nút canh gác**; **size** luôn là số nút hiện tại. Hàm **check_invariants** phục vụ kiểm tra, nên có thể tốn thêm thời gian và bộ nhớ; không cần chạy sau mỗi thao tác trong môi trường sản xuất.

~~~python
from __future__ import annotations


class Node:
    def __init__(self, value, next_node: Node | None = None):
        self.value = value
        self.next = next_node


class SinglyLinkedList:
    def __init__(self):
        self.head: Node | None = None
        self.tail: Node | None = None
        self.size = 0

    def is_empty(self) -> bool:
        return self.head is None

    def prepend(self, value) -> None:
        node = Node(value, self.head)
        self.head = node

        if self.tail is None:  # Trước khi thêm: danh sách rỗng
            self.tail = node

        self.size += 1

    def append(self, value) -> None:
        node = Node(value)  # node.next = None

        if self.tail is None:
            self.head = node
        else:
            self.tail.next = node

        self.tail = node
        self.size += 1

    def pop_front(self):
        if self.head is None:
            raise IndexError("Không thể xóa đầu danh sách rỗng")

        old = self.head
        self.head = old.next

        if self.head is None:  # Vừa xóa nút duy nhất
            self.tail = None

        old.next = None
        self.size -= 1
        return old.value

    def pop_back(self):
        if self.tail is None:
            raise IndexError("Không thể xóa cuối danh sách rỗng")

        if self.head is self.tail:  # Chỉ một nút
            value = self.head.value
            self.head = None
            self.tail = None
            self.size = 0
            return value

        # Có ít nhất hai nút: tìm nút ngay trước tail.
        prev = self.head
        while prev.next is not self.tail:
            prev = prev.next

        old = self.tail
        prev.next = None
        self.tail = prev
        self.size -= 1
        return old.value

    def to_list(self) -> list:
        result = []
        current = self.head
        while current is not None:
            result.append(current.value)
            current = current.next
        return result

    def check_invariants(self) -> None:
        """Kiểm tra cấu trúc, dùng khi học và gỡ lỗi."""
        if self.head is None:
            assert self.tail is None
            assert self.size == 0
            return

        assert self.tail is not None
        assert self.size > 0
        assert self.tail.next is None

        # Theo dõi danh tính nút để phát hiện chu trình.
        visited = set()
        current = self.head
        last = None
        count = 0

        while current is not None:
            assert id(current) not in visited, "Có chu trình"
            visited.add(id(current))
            last = current
            count += 1
            current = current.next

        assert last is self.tail, "Tail không phải nút cuối"
        assert count == self.size, "Size không khớp"


items = SinglyLinkedList()
items.check_invariants()                # Rỗng
assert items.is_empty()

items.append(10)
items.check_invariants()                # Một nút: head is tail
assert items.head is items.tail
assert items.to_list() == [10]

items.append(20)
items.prepend(5)
items.check_invariants()                # Nhiều nút: 5 -> 10 -> 20
assert items.to_list() == [5, 10, 20]

assert items.pop_front() == 5
assert items.pop_back() == 20
items.check_invariants()                # Còn một nút: 10
assert items.head is items.tail

assert items.pop_back() == 10
items.check_invariants()                # Trở lại rỗng
assert items.head is None and items.tail is None
assert items.size == 0

# Giá trị None vẫn là một nút dữ liệu hợp lệ.
items.append(None)
items.check_invariants()
assert not items.is_empty()
assert items.size == 1
assert items.pop_front() is None
items.check_invariants()
~~~

Trong vòng lặp tìm **prev** ở **pop_back**, điều kiện đã biết là danh sách hợp lệ và có ít nhất hai nút; do đó tồn tại một nút có **next is tail**. Nếu bất biến bị phá vỡ từ trước, không thể tiếp tục tin vào điều kiện này.

**Lưu ý chi phí kiểm tra:** **check_invariants** duyệt toàn bộ *n* nút và dùng tập **visited** để phát hiện chu trình, nên tốn **O(n)** thời gian và **O(n)** bộ nhớ phụ. Chi phí đó là của thao tác kiểm tra, không thuộc chi phí cơ bản của append/prepend/pop_front.

## 8. Bảng chuyển trạng thái và độ phức tạp

### Bảng chuyển trạng thái

| Thao tác | Trước | Sau | Cập nhật đặc biệt |
| --- | --- | --- | --- |
| append(x), prepend(x) | Rỗng | Một nút | **head = tail = new**, size = 1. |
| prepend(x) | Một hoặc nhiều nút | Nhiều hơn một nút | **head = new**, tail giữ nguyên. |
| append(x) | Một hoặc nhiều nút | Nhiều hơn một nút | **old_tail.next = new**, **tail = new**. |
| pop_front(), pop_back() | Một nút | Rỗng | **head = tail = None**, size = 0. |
| pop_front() | Ít nhất hai nút | Ít đi một nút | head chuyển sang head.next; tail giữ nguyên. |
| pop_back() | Ít nhất hai nút | Ít đi một nút | Tìm prev, đặt **prev.next = None**, **tail = prev**. |
| pop_front(), pop_back() | Rỗng | Rỗng | Báo lỗi; không sửa trạng thái. |

### Chi phí thao tác

| Thao tác | Có head + tail | Chỉ có head | Ghi chú |
| --- | --- | --- | --- |
| Kiểm tra rỗng | **O(1)** | **O(1)** | Kiểm tra head có là None. |
| Đọc nút đầu | **O(1)** | **O(1)** | Đã có head. |
| Đọc nút cuối | **O(1)** | **O(n)** | Không có tail thì phải duyệt. |
| Thêm đầu | **O(1)** | **O(1)** | Chỉ thay vài tham chiếu. |
| Thêm cuối | **O(1)** | **O(n)** | Tail cho phép nối trực tiếp. |
| Xóa đầu | **O(1)** | **O(1)** | Cần xử lý về trạng thái rỗng. |
| Xóa cuối | **O(n)** | **O(n)** | Phải tìm nút đứng trước nút cuối. |
| Kiểm tra đầy đủ bất biến | **O(n)** | Tùy bất biến | Phải duyệt chuỗi; phát hiện chu trình có thể cần thêm bộ nhớ. |

Khi có *n* nút, dữ liệu và liên kết **next** chiếm **O(n)** bộ nhớ. Hai tham chiếu head/tail và biến size chỉ chiếm **O(1)** bộ nhớ bổ sung. Lợi ích thêm cuối O(1) đạt được bằng cách duy trì chính xác tail mỗi khi cấu trúc thay đổi.

Không nên tính việc kiểm tra đầy đủ bất biến vào mọi lời gọi append rồi vẫn tuyên bố append O(1): nếu chạy **check_invariants** sau mỗi append, tổng lời gọi đó có chi phí O(n) do bước kiểm tra.

## 9. Những lỗi dễ gặp khi danh sách rỗng

| Sai sót | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ đặt head = None khi xóa nút duy nhất | tail giữ tham chiếu lỗi thời. | Đặt **cả head và tail = None**. |
| Append vào danh sách rỗng bằng **tail.next = new** | Lỗi truy cập thuộc tính của None. | Phân nhánh riêng cho **tail is None**. |
| Prepend vào danh sách rỗng nhưng không cập nhật tail | Danh sách có head nhưng không có tail hợp lệ. | Khi tail là None, đặt **tail = new**. |
| Sau khi xóa tail, quên gán **prev.next = None** | Nút cũ vẫn nằm trên đường đi từ head. | Cắt liên kết và chuyển tail sang prev. |
| Kiểm tra rỗng bằng **head.value is None** | Nhầm nút chứa None với danh sách rỗng; có thể lỗi khi head là None. | Kiểm tra **head is None**. |
| So sánh **head.value == tail.value** để suy ra một nút | Nhiều nút có thể chứa cùng giá trị. | So sánh danh tính **head is tail**. |
| Size không thay đổi khi thêm/xóa | size mâu thuẫn với số nút thực tế. | Cập nhật size đúng một lần trong thao tác thành công. |
| Chỉ kiểm tra **tail.next is None** để kết luận danh sách đúng | Tail có thể là nút tách rời hoặc trỏ nhầm. | Kiểm tra thêm khả năng đi từ head tới tail và số nút. |

**Cách gỡ lỗi thực tế:** Sau một thao tác, thử lần theo **head → next → ... → None**, đếm số nút, xác định nút cuối thực tế và so sánh với tail. Với danh sách rỗng, kiểm tra cùng lúc **head**, **tail**, **size**; với danh sách một nút, kiểm tra **head is tail**.

## 10. Bài tập vận dụng

**Bài 1 — Chuyển từ rỗng sang một nút.** Ban đầu head = tail = None, size = 0. Sau **prepend(42)**, ba thuộc tính đó phải có giá trị gì?

*Đáp án:* head và tail cùng tham chiếu một nút chứa 42; size = 1; tail.next = None.

**Bài 2 — Xóa nút duy nhất.** Danh sách đang có head is tail cùng trỏ nút X. Nếu chỉ thực hiện **head = head.next**, điều gì bị thiếu?

*Đáp án:* Vì X.next = None nên head thành None, nhưng tail vẫn chỉ X. Cần đặt tail = None và size = 0.

**Bài 3 — Tìm bất biến sai.** Cho head → A → B → None, tail → A, size = 2. Những điều kiện nào bị vi phạm?

*Đáp án:* Tail không phải nút cuối có thể đi tới từ head; tail.next khác None (vẫn trỏ B). Size đang bằng 2 nhưng điều đó không làm trạng thái trở nên hợp lệ.

**Bài 4 — Vì sao xóa cuối O(n)?** Tail đã cho biết nút cuối T. Tại sao vẫn cần duyệt từ head khi danh sách có nhiều nút?

*Đáp án:* Cần tìm nút đứng trước T để sửa **prev.next = None** và đặt **tail = prev**. Nút T trong danh sách đơn không có liên kết ngược đến prev.

**Bài 5 — Dự đoán trạng thái.** Thực hiện trên danh sách rỗng: **append(2)** → **append(4)** → **pop_front()** → **pop_back()**. Sau mỗi bước, trạng thái là gì?

*Đáp án:* Sau append(2): [2], head is tail, size 1; sau append(4): [2, 4], head khác tail, size 2; sau pop_front(): [4], head is tail, size 1; sau pop_back(): rỗng, head = tail = None, size 0.

**Tự kiểm tra:** Nếu bạn có thể vẽ đúng head/tail khi danh sách thay đổi giữa **0, 1 và 2 nút**, giải thích vì sao **tail.next** phải bằng None và chỉ ra khi nào cần tìm **prev** để xóa cuối, bạn đã nắm được phần cốt lõi của bất biến danh sách liên kết đơn.

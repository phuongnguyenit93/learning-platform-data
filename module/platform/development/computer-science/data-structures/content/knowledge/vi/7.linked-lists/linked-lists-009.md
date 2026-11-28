# Nút đầu giả, nút cuối giả và nút canh gác

Một lỗi phổ biến khi lập trình **danh sách liên kết** là thao tác chèn/xóa phải xử lý riêng quá nhiều trường hợp: danh sách rỗng, nút đầu, nút cuối, hoặc chỉ có một nút. Kỹ thuật **nút giả** (*dummy node*) và **nút canh gác** (*sentinel node*) giúp tổ chức các liên kết sao cho phần lớn thao tác dùng chung một quy tắc cập nhật.

Thay vì để mọi trường hợp đều thao tác trực tiếp với **None**, cấu trúc đặt một hoặc hai nút đặc biệt ở ranh giới. Chúng **không đại diện cho phần tử dữ liệu của người dùng**, nhưng cung cấp những liên kết ổn định để thao tác chèn/xóa. Đổi lại, chương trình phải phân biệt rõ **nút thật** với **nút canh gác**, và quy ước về danh sách rỗng thay đổi tùy kiểu triển khai.

Bài học thuộc chương **Danh sách liên kết** trong mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Chủ đề này tập trung vào bất biến, thao tác và độ phức tạp thời gian/bộ nhớ nhằm giúp chọn cấu trúc dữ liệu phù hợp, đồng thời viết mã ít lỗi ở các trường hợp biên.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của **dummy head** (nút đầu giả), **dummy tail** (nút cuối giả) và **sentinel** (nút canh gác).
- Phân biệt ba cách biểu diễn: danh sách đơn với **một nút đầu giả**, danh sách đôi với **hai nút biên giả**, và danh sách đôi vòng với **một sentinel tự nối**.
- Xác định đúng trạng thái **rỗng**, **một nút** và **nhiều nút** trong từng thiết kế.
- Phát biểu các bất biến của đầu, cuối và liên kết hai chiều.
- Chèn/xóa nút bằng cùng một mẫu liên kết, kể cả ở ranh giới.
- Duyệt đúng nút dữ liệu mà **không đưa sentinel vào kết quả**.
- Giải thích khi nào sentinel giảm số nhánh xử lý nhưng **không cải thiện bậc độ phức tạp**.
- Nhận diện các lỗi như xóa nhầm sentinel, dựa vào giá trị None để phát hiện sentinel hoặc giữ sai con trỏ cuối.

## 2. Tên gọi và ý nghĩa: dummy khác sentinel như thế nào?

Trong tài liệu cấu trúc dữ liệu, các thuật ngữ **dummy node** và **sentinel node** đôi khi được dùng gần như đồng nghĩa. Cả hai đều chỉ **nút tồn tại vì mục đích điều khiển cấu trúc**, không tính là phần tử dữ liệu. Tuy nhiên, ta có thể phân biệt theo vai trò cụ thể:

| Khái niệm | Vai trò thông thường | Ví dụ |
| --- | --- | --- |
| **Nút đầu giả** (*dummy head*) | Đứng trước phần tử đầu tiên; cung cấp nút đứng trước head thật | Chèn/xóa đầu danh sách đơn bằng phép sửa dummy.next |
| **Nút cuối giả** (*dummy tail*) | Đứng sau phần tử cuối cùng; đánh dấu điểm kết thúc | Dừng duyệt khi gặp dummy tail của danh sách đôi |
| **Nút canh gác** (*sentinel*) | Nút đặc biệt làm ranh giới, điểm dừng hoặc thay cho trường hợp None | Một sentinel của danh sách đôi vòng tự trỏ đến chính nó khi rỗng |

**Không có một bố trí sentinel bắt buộc cho mọi danh sách.** Có triển khai chỉ dùng dummy head, có triển khai dùng cả head/tail sentinel, có triển khai dùng một sentinel trong một vòng hai chiều. Thuật toán đúng phải xuất phát từ **bất biến của đúng biến thể đang dùng**.

Vài nguyên tắc chung:

- Sentinel có thể chứa một trường **value**, nhưng giá trị đó **không phải dữ liệu hợp lệ của danh sách**.
- Nút dữ liệu thật có thể chứa **None**. Vì vậy, không xác định sentinel bằng điều kiện **node.value is None**.
- Phân biệt sentinel bằng **danh tính đối tượng**: trong Python dùng **node is self.before**, **node is self.after** hoặc **node is self.sentinel**.
- Biến **size** chỉ đếm **nút dữ liệu**, không tính các nút giả.

## 3. Danh sách đơn với một nút đầu giả

Một danh sách liên kết đơn thông thường có thể biểu diễn:

~~~text
head ──► [ 10 | • ] ──► [ 20 | • ] ──► [ 30 | None ]
~~~

Nếu chèn hoặc xóa ở đầu, chương trình phải sửa chính biến head. Khi thêm **dummy head**, ta đặt một nút đặc biệt ở trước nút 10:

~~~text
dummy
  │
  ▼
[ giả | • ] ──► [ 10 | • ] ──► [ 20 | • ] ──► [ 30 | None ]
                    ▲
             nút dữ liệu đầu
~~~

Khi đó:

- **dummy.next** là nút dữ liệu đầu tiên hoặc None nếu rỗng.
- **dummy** không nằm trong tập phần tử cần trả về cho người dùng.
- Không nhất thiết lưu một biến head dữ liệu riêng: có thể lấy nút đầu bằng **dummy.next**.
- Nếu lưu thêm con trỏ **tail** trỏ tới nút dữ liệu cuối, thao tác append có thể O(1).

### 3.1. Trạng thái rỗng và một nút

~~~text
Danh sách rỗng:
dummy ──► [ giả | None ]
size = 0

Danh sách một nút:
dummy ──► [ giả | • ] ──► [ 7 | None ]
size = 1
~~~

Nếu mô hình **lưu tail và quy ước tail chỉ nút cuối, hoặc dummy khi rỗng**, thì:

~~~text
Rỗng:       dummy.next is None, tail is dummy, size == 0
Không rỗng: dummy.next is not None, tail.next is None
Một nút:    dummy.next is tail, size == 1
~~~

**Chú ý:** Nút đầu giả vẫn tồn tại khi không có phần tử nào. Không thể dùng **dummy is None** để kiểm tra rỗng vì dummy không bao giờ là None sau khi khởi tạo.

### 3.2. Vì sao chèn đầu và xóa đầu đơn giản hơn?

Khi chèn ở đầu, có thể coi đó là **chèn ngay sau dummy**. Khi xóa đầu, có thể coi đó là **xóa ngay sau dummy**.

~~~text
Trước: dummy → A → B → None
Chèn X sau dummy:
       dummy → X → A → B → None

Xóa đầu (X) bằng xóa sau dummy:
       dummy → A → B → None
~~~

Mẫu chèn sau một nút **prev** đã biết:

~~~python
new = Node(value, prev.next)
prev.next = new
~~~

Mẫu xóa nút ngay sau **prev**:

~~~python
removed = prev.next
prev.next = removed.next
~~~

Với **prev = dummy**, cả hai mẫu tác động đến phần tử đầu mà không cần một nhánh riêng để đổi biến head. Tuy nhiên, nếu cấu trúc lưu **tail**, vẫn phải cập nhật tail khi nút đầu tiên hoặc nút cuối cùng thay đổi.

**Giới hạn:** Dummy head không giúp xóa trực tiếp nút cuối của danh sách đơn trong O(1) nếu chưa có **nút đứng trước tail**. Phải đi từ dummy hoặc nút đầu để tìm predecessor.

## 4. Các thao tác với dummy head và tail thật

Giả sử danh sách đơn lưu:

- **dummy**: nút đầu giả, tồn tại suốt vòng đời danh sách.
- **tail**: nút dữ liệu cuối; khi rỗng, tail chính là dummy.
- **size**: số nút dữ liệu.

### 4.1. Chèn đầu

Với **prev = dummy**, ta gán:

~~~python
new = Node(value, dummy.next)
dummy.next = new
if tail is dummy:
    tail = new
size += 1
~~~

Nếu danh sách đã có phần tử, tail giữ nguyên; nếu rỗng, new đồng thời là nút đầu và cuối.

### 4.2. Thêm cuối

Vì tail luôn là một đối tượng nút, kể cả khi danh sách rỗng (lúc đó tail is dummy), có thể viết:

~~~python
new = Node(value)
tail.next = new
tail = new
size += 1
~~~

Không cần nhánh **if tail is None**. Khi rỗng, câu lệnh **tail.next = new** thực chất là **dummy.next = new**.

Đây là một lợi ích của dummy head: **tail luôn có liên kết next có thể sửa**, ngay cả lúc rỗng.

### 4.3. Xóa đầu

Xóa ngay sau dummy:

~~~python
removed = dummy.next
if removed is None:
    raise IndexError("Danh sách rỗng")

dummy.next = removed.next
if tail is removed:
    tail = dummy

removed.next = None
size -= 1
~~~

Nếu removed là nút duy nhất, tail phải quay về dummy; không được giữ tail trỏ tới nút đã gỡ.

### 4.4. Xóa sau nút đã biết

Nếu prev thuộc danh sách (hoặc chính là dummy) và có nút phía sau:

~~~python
removed = prev.next
if removed is None:
    raise IndexError("Không có nút sau prev")

prev.next = removed.next
if tail is removed:
    tail = prev

removed.next = None
size -= 1
~~~

Khi removed là tail, nút prev trở thành cuối; nếu prev là dummy, danh sách trở về rỗng. Điều kiện tiền quyết là **prev phải thuộc cấu trúc hiện tại hoặc là dummy của chính danh sách này**.

**Độ phức tạp:** chèn/xóa ngay sau prev hợp lệ là Θ(1); thêm cuối có tail là Θ(1). Nếu phải tìm prev theo giá trị/chỉ số, cần cộng chi phí duyệt, có thể Θ(n).

## 5. Danh sách đôi với nút đầu giả và nút cuối giả

Trong danh sách **liên kết đôi**, mỗi nút có **prev** và **next**. Ta có thể đặt hai sentinel cố định ở hai biên:

- **before**: nút đầu giả, luôn đứng trước nút dữ liệu đầu.
- **after**: nút cuối giả, luôn đứng sau nút dữ liệu cuối.

Trạng thái có ba nút:

~~~text
                  nút dữ liệu thật
             ┌───────────────────────────┐
             ▼                           ▼
[ before ] ⇄ [ 10 ] ⇄ [ 20 ] ⇄ [ 30 ] ⇄ [ after ]
  giả đầu                                       giả cuối
~~~

Ta có các liên kết:

~~~text
before.next is node_10
node_10.prev is before

node_30.next is after
after.prev is node_30
~~~

### 5.1. Danh sách rỗng

Hai nút giả **không bị xóa** khi size bằng 0. Chúng nối trực tiếp với nhau:

~~~text
[ before ] ⇄ [ after ]
size = 0
~~~

Bất biến rỗng:

~~~text
before.next is after
after.prev is before
size == 0
~~~

Với cài đặt tuyến tính đơn giản, có thể đặt thêm **before.prev is None** và **after.next is None**. Đây là hai liên kết ở *phía ngoài* ranh giới, không dùng để duyệt dữ liệu.

### 5.2. Danh sách một nút

~~~text
[ before ] ⇄ [ X ] ⇄ [ after ]
size = 1
~~~

**before.next is X**, **X.prev is before**, **X.next is after**, **after.prev is X**.

Nút X vẫn là một nút dữ liệu thông thường; sentinel không cần chứa giá trị người dùng. Khi xóa X, thao tác nối lại before và after:

~~~text
before.next = after
after.prev = before
~~~

Danh sách trở về rỗng mà không phải đặt head/tail thành None.

### 5.3. Điều kiện dừng duyệt

Khi duyệt xuôi, bắt đầu từ **before.next** và dừng khi gặp **after**:

~~~python
current = before.next
while current is not after:
    process(current.value)
    current = current.next
~~~

Duyệt ngược tương tự, bắt đầu từ **after.prev** và dừng khi gặp **before**:

~~~python
current = after.prev
while current is not before:
    process(current.value)
    current = current.prev
~~~

Nếu rỗng, before.next chính là after nên vòng lặp xuôi chạy **0 lần**. Nếu chỉ có một phần tử, vòng lặp xử lý đúng một nút rồi gặp after.

**Không dùng** điều kiện **current is not None** để biểu thị còn dữ liệu: khi đi từ trước tới after, current vẫn là một đối tượng nút thật (sentinel), và mã có thể xử lý nhầm giá trị của after trước khi dừng.

## 6. Chèn giữa hai nút trong danh sách đôi có sentinel

Với hai nút kề nhau **left** và **right**, dù một trong hai là sentinel, thao tác chèn X vào giữa có cùng bốn phép nối:

~~~text
Trước: left ⇄ right

Sau:   left ⇄ X ⇄ right
~~~

~~~python
new.prev = left
new.next = right
left.next = new
right.prev = new
~~~

Với hai sentinel biên, ta luôn có hai đối tượng hợp lệ **left** và **right**:

- Chèn đầu: **left = before**, **right = before.next**.
- Thêm cuối: **left = after.prev**, **right = after**.
- Chèn trước nút data: **left = target.prev**, **right = target**.
- Chèn sau nút data: **left = target**, **right = target.next**.

Vì **left** và **right** không phải None trong các thao tác hợp lệ, không cần phân nhánh cập nhật head/tail riêng. Điều kiện cần giữ là left và right **thực sự đang kề nhau** và cùng thuộc danh sách.

Ví dụ, danh sách đang rỗng:

~~~text
before ⇄ after
~~~

Gọi chèn giữa before và after tạo:

~~~text
before ⇄ X ⇄ after
~~~

Cùng một đoạn mã cũng hoạt động khi danh sách có hàng nghìn nút và chèn vào giữa hai nút đã biết.

### Lỗi thứ tự gán

Nếu ghi **left.next = new** trước, rồi đọc **right = left.next**, biến right sẽ chỉ chính new, khiến cấu trúc bị sai. Hãy giữ tham chiếu **right cũ** trước khi thay liên kết.

Không chèn một nút mới vào danh sách bằng cách chỉ sửa **left.next** và **new.next** mà bỏ qua **right.prev**: khi đó duyệt xuôi có thể đúng nhưng duyệt ngược sẽ sai.

## 7. Xóa một nút dữ liệu giữa hai sentinel

Cho:

~~~text
before ⇄ A ⇄ B ⇄ C ⇄ after
               ▲
             target
~~~

Khi đã có tham chiếu **target = B**, lấy hai nút kề:

~~~python
left = target.prev    # A
right = target.next   # C
~~~

Nối trực tiếp:

~~~python
left.next = right
right.prev = left
target.prev = None
target.next = None
size -= 1
~~~

Kết quả:

~~~text
before ⇄ A ⇄ C ⇄ after
~~~

Điểm hay của thiết kế **hai sentinel** là:

- Xóa nút đầu dữ liệu: left chính là **before**, không phải None.
- Xóa nút cuối dữ liệu: right chính là **after**, không phải None.
- Xóa nút dữ liệu duy nhất: left = before và right = after, vẫn có hai liên kết hợp lệ để sửa.

**Không được xóa sentinel.** Ví dụ, before và after là nút quản lý cấu trúc, không phải mục dữ liệu. Một API xóa nút nên từ chối khi target là before hoặc after. Cũng cần bảo đảm target thực sự thuộc danh sách; nếu target là nút ngoài hoặc đã bị gỡ, các liên kết của nó không nhất thiết hợp lệ.

Thao tác xóa đúng nút đã biết trên danh sách đôi với sentinel mất **Θ(1)** thời gian và **O(1)** bộ nhớ phụ nếu target hợp lệ. Nếu chỉ biết giá trị cần xóa, bước duyệt tìm target vẫn có thể mất Θ(n).

## 8. Một sentinel cho danh sách đôi vòng

Một biến thể khác sử dụng **một nút sentinel duy nhất** trong **danh sách đôi vòng**. Ta đặt tên **s**, và liên kết vòng đi qua cả s lẫn các nút dữ liệu.

### 8.1. Danh sách rỗng

Khi chưa có phần tử nào:

~~~text
s.next is s
s.prev is s
size == 0
~~~

Sơ đồ:

~~~text
               ┌──── next ────┐
               ▼              │
             [ s ] ───────────┘
               ▲              │
               └──── prev ────┘
~~~

Sentinel không “biến mất” trong danh sách rỗng; nó tự trỏ theo hai chiều.

### 8.2. Danh sách có dữ liệu

Khi có A, B, C:

~~~text
        ┌─────────────────────────┐
        ▼                         │
[ s ] ⇄ [ A ] ⇄ [ B ] ⇄ [ C ] ─────┘
  ▲                          │
  └────────── prev ──────────┘
~~~

Cụ thể:

~~~text
s.next is A
A.prev is s
C.next is s
s.prev is C
~~~

**Nút dữ liệu đầu** là s.next; **nút dữ liệu cuối** là s.prev. Không cần biến head/tail dữ liệu riêng nếu luôn có s.

### 8.3. Duyệt đúng một vòng

Bắt đầu ở **s.next**, dừng khi quay lại **s**:

~~~python
current = s.next
while current is not s:
    process(current.value)
    current = current.next
~~~

Duyệt ngược:

~~~python
current = s.prev
while current is not s:
    process(current.value)
    current = current.prev
~~~

Chú ý điểm dừng là **sentinel**, không phải None và cũng không phải nút dữ liệu đầu. Đối với danh sách rỗng, s.next is s nên vòng duyệt xuôi chạy 0 lần; trường hợp một nút cũng không cần nhánh dừng đặc biệt.

### 8.4. Chèn và xóa

Một sentinel vòng vẫn dùng cùng mẫu **chèn giữa left và right**:

~~~python
new.prev = left
new.next = right
left.next = new
right.prev = new
~~~

Để **thêm đầu**, đặt left = s, right = s.next. Để **thêm cuối**, đặt left = s.prev, right = s. Khi rỗng, cả left và right có thể là **chính s**, và các gán vẫn đúng.

Xóa một nút dữ liệu có prev/next hợp lệ cũng dùng mẫu nối hai nút bên cạnh, miễn là **không xóa chính sentinel**.

## 9. Mã Python: danh sách đơn với dummy head và tail thật

Cài đặt tự chứa dưới đây cho phép **prepend**, **append**, **insert_after**, **remove_after** và **pop_front**. Nó duy trì tail theo quy ước **tail is dummy khi danh sách rỗng**, nên không cần nhánh tail is None trong thao tác append.

~~~python
from __future__ import annotations


class Node:
    def __init__(self, value, next_node: Node | None = None):
        self.value = value
        self.next = next_node


class SinglyWithDummy:
    def __init__(self):
        self.dummy = Node(None)  # Giá trị không được dùng để nhận diện dummy.
        self.tail = self.dummy
        self.size = 0

    def prepend(self, value) -> Node:
        return self.insert_after(self.dummy, value)

    def append(self, value) -> Node:
        new = Node(value)
        self.tail.next = new    # Tail luôn là một nút, kể cả lúc rỗng.
        self.tail = new
        self.size += 1
        return new

    def insert_after(self, prev: Node, value) -> Node:
        # Tiền điều kiện: prev là dummy hoặc một nút dữ liệu thuộc list.
        if prev is None:
            raise ValueError("prev không được là None")

        new = Node(value, prev.next)
        prev.next = new
        if prev is self.tail:
            self.tail = new
        self.size += 1
        return new

    def remove_after(self, prev: Node):
        # Tiền điều kiện: prev là dummy hoặc một nút dữ liệu thuộc list.
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

    def pop_front(self):
        if self.size == 0:
            raise IndexError("Danh sách rỗng")
        return self.remove_after(self.dummy)

    def values(self) -> list:
        result = []
        current = self.dummy.next
        while current is not None:
            result.append(current.value)
            current = current.next
        return result

    def check_invariants(self) -> None:
        """Kiểm tra cấu trúc, dùng để học/gỡ lỗi."""
        if self.size == 0:
            assert self.dummy.next is None
            assert self.tail is self.dummy
            return

        assert self.dummy.next is not None
        assert self.tail is not self.dummy
        assert self.tail.next is None

        current = self.dummy.next
        visited = set()
        count = 0
        last = None

        while current is not None:
            assert current is not self.dummy
            assert id(current) not in visited, "Có chu trình"
            visited.add(id(current))
            last = current
            count += 1
            current = current.next

        assert count == self.size, "Sai size"
        assert last is self.tail, "Sai tail"


items = SinglyWithDummy()
items.check_invariants()
assert items.dummy.next is None
assert items.tail is items.dummy

n20 = items.append(20)
items.check_invariants()
assert items.dummy.next is n20 and items.tail is n20

n10 = items.prepend(10)
n15 = items.insert_after(n10, 15)
n30 = items.append(30)
items.check_invariants()
assert items.values() == [10, 15, 20, 30]
assert items.tail is n30

assert items.remove_after(items.dummy) == 10
items.check_invariants()
assert items.values() == [15, 20, 30]

assert items.remove_after(n20) == 30
items.check_invariants()
assert items.tail is n20
assert items.values() == [15, 20]

assert items.pop_front() == 15
assert items.pop_front() == 20
items.check_invariants()
assert items.dummy.next is None
assert items.tail is items.dummy
assert items.size == 0

# Dữ liệu có giá trị None vẫn là một nút thật.
items.append(None)
items.check_invariants()
assert items.values() == [None]
assert items.pop_front() is None
items.check_invariants()
~~~

**Nhận xét:** Dummy head giúp thao tác xóa đầu dùng chính remove_after(dummy) và append không cần phân nhánh khi rỗng nếu giữ **tail is dummy**. Tuy nhiên, việc tìm **nút đứng trước** để xóa một vị trí bất kỳ của danh sách đơn vẫn có thể mất Θ(n).

Hàm **check_invariants** duyệt toàn bộ n nút và dùng tập **visited**, nên tốn Θ(n) thời gian và O(n) bộ nhớ phụ. Đây là công cụ kiểm tra, không phải chi phí bắt buộc trong mỗi thao tác thường xuyên.

## 10. Mã Python: danh sách đôi với hai sentinel biên

Mô hình sau tạo hai nút giả **before** và **after** ngay khi khởi tạo. Cả khi rỗng, before.next vẫn là after, và after.prev vẫn là before. Nhờ đó, các hàm chèn/xóa nút thật không phải phân nhánh theo head hay tail.

~~~python
from __future__ import annotations


class DNode:
    def __init__(self, value=None):
        self.value = value
        self.prev: DNode | None = None
        self.next: DNode | None = None


class DoublyWithSentinels:
    def __init__(self):
        self.before = DNode()
        self.after = DNode()
        self.before.next = self.after
        self.after.prev = self.before
        self.size = 0

    def _insert_between(self, left: DNode, right: DNode, value) -> DNode:
        # Tiền điều kiện: left.next is right, right.prev is left;
        # cả hai nút thuộc cùng danh sách.
        new = DNode(value)
        new.prev = left
        new.next = right
        left.next = new
        right.prev = new
        self.size += 1
        return new

    def prepend(self, value) -> DNode:
        return self._insert_between(self.before, self.before.next, value)

    def append(self, value) -> DNode:
        return self._insert_between(self.after.prev, self.after, value)

    def insert_before(self, anchor: DNode, value) -> DNode:
        # Anchor phải là một nút dữ liệu thuộc danh sách.
        if anchor is self.before or anchor is self.after:
            raise ValueError("Không chèn trước nút canh gác bằng API này")
        return self._insert_between(anchor.prev, anchor, value)

    def insert_after(self, anchor: DNode, value) -> DNode:
        # Anchor phải là một nút dữ liệu thuộc danh sách.
        if anchor is self.before or anchor is self.after:
            raise ValueError("Không chèn sau nút canh gác bằng API này")
        return self._insert_between(anchor, anchor.next, value)

    def remove_node(self, target: DNode):
        # Target phải là nút dữ liệu đang thuộc danh sách.
        if target is self.before or target is self.after:
            raise ValueError("Không được xóa nút canh gác")

        left = target.prev
        right = target.next
        if left is None or right is None:
            raise ValueError("Nút không được nối hợp lệ")

        left.next = right
        right.prev = left
        target.prev = None
        target.next = None
        self.size -= 1
        return target.value

    def pop_front(self):
        if self.size == 0:
            raise IndexError("Danh sách rỗng")
        return self.remove_node(self.before.next)

    def pop_back(self):
        if self.size == 0:
            raise IndexError("Danh sách rỗng")
        return self.remove_node(self.after.prev)

    def values_forward(self) -> list:
        result = []
        current = self.before.next
        while current is not self.after:
            result.append(current.value)
            current = current.next
        return result

    def values_backward(self) -> list:
        result = []
        current = self.after.prev
        while current is not self.before:
            result.append(current.value)
            current = current.prev
        return result

    def check_invariants(self) -> None:
        assert self.before.prev is None
        assert self.after.next is None
        assert self.before.next is not None
        assert self.after.prev is not None

        count = 0
        current = self.before
        seen = {id(self.before)}
        previous = None

        while current is not self.after:
            following = current.next
            assert following is not None
            assert following.prev is current

            if following is not self.after:
                assert id(following) not in seen, "Chu trình bất thường"
                seen.add(id(following))
                count += 1

            previous = current
            current = following

        assert self.after.prev is previous
        assert count == self.size

        reverse_count = 0
        current = self.after.prev
        while current is not self.before:
            assert current is not None
            assert id(current) in seen
            assert current.next is not None
            assert current.next.prev is current
            reverse_count += 1
            assert reverse_count <= self.size
            current = current.prev

        assert reverse_count == self.size


items = DoublyWithSentinels()
items.check_invariants()
assert items.before.next is items.after
assert items.after.prev is items.before

n20 = items.append(20)
items.check_invariants()
assert items.before.next is n20 and items.after.prev is n20

n10 = items.prepend(10)
n30 = items.append(30)
n15 = items.insert_after(n10, 15)
items.check_invariants()
assert items.values_forward() == [10, 15, 20, 30]
assert items.values_backward() == [30, 20, 15, 10]

assert items.remove_node(n15) == 15
assert items.pop_front() == 10
assert items.pop_back() == 30
items.check_invariants()
assert items.values_forward() == [20]

assert items.remove_node(n20) == 20
items.check_invariants()
assert items.before.next is items.after
assert items.after.prev is items.before
assert items.size == 0

# Không được xóa nút đầu giả hay nút cuối giả.
try:
    items.remove_node(items.before)
except ValueError:
    pass
else:
    raise AssertionError("Phải từ chối xóa sentinel")

# Một nút dữ liệu chứa None vẫn phải được duyệt.
n_none = items.append(None)
items.check_invariants()
assert items.values_forward() == [None]
assert items.remove_node(n_none) is None
items.check_invariants()
~~~

**Quan trọng:** Các phương thức insert_before, insert_after và remove_node giả định **anchor/target là nút thuộc chính danh sách**. Kiểm tra target không phải sentinel **không đồng nghĩa đã kiểm chứng tư cách thành viên**. Một nút ở danh sách khác cũng có thể có prev/next hợp lệ. Nếu muốn API an toàn với tham chiếu bất kỳ, cần cơ chế kiểm chứng thành viên, chẳng hạn duyệt từ before (O(n)) hoặc metadata chủ sở hữu được duy trì đúng.

## 11. Mã ngắn: sentinel vòng cho danh sách đôi

Để thấy rõ cách một sentinel duy nhất phục vụ cả hai biên, ta xét phiên bản vòng tối giản. Khi rỗng, sentinel tự trỏ; khi không rỗng, các nút dữ liệu và sentinel tạo thành một vòng.

~~~python
class RingNode:
    def __init__(self, value=None):
        self.value = value
        self.prev = self
        self.next = self


class CircularWithSentinel:
    def __init__(self):
        self.sentinel = RingNode()
        self.size = 0

    def append(self, value):
        s = self.sentinel
        last = s.prev
        node = RingNode(value)

        node.prev = last
        node.next = s
        last.next = node
        s.prev = node

        self.size += 1
        return node

    def pop_front(self):
        s = self.sentinel
        first = s.next
        if first is s:
            raise IndexError("Danh sách rỗng")

        second = first.next
        s.next = second
        second.prev = s
        first.prev = None
        first.next = None

        self.size -= 1
        return first.value

    def values(self):
        s = self.sentinel
        result = []
        current = s.next
        while current is not s:
            result.append(current.value)
            current = current.next
        return result


ring = CircularWithSentinel()
assert ring.sentinel.next is ring.sentinel
assert ring.sentinel.prev is ring.sentinel
assert ring.values() == []

ring.append("A")
ring.append("B")
assert ring.values() == ["A", "B"]
assert ring.sentinel.next.value == "A"
assert ring.sentinel.prev.value == "B"

assert ring.pop_front() == "A"
assert ring.pop_front() == "B"
assert ring.values() == []
assert ring.sentinel.next is ring.sentinel
assert ring.sentinel.prev is ring.sentinel
assert ring.size == 0
~~~

Khi append vào danh sách rỗng, **last chính là sentinel**; sau bốn phép gán, sentinel.next và sentinel.prev đều chỉ tới nút mới. Khi xóa nút dữ liệu duy nhất, **second cũng là sentinel**, nên hai phép gán s.next = s và s.prev = s được thiết lập tự nhiên.

Với danh sách vòng, **không dùng None để đánh dấu kết thúc duyệt**. Thuật toán dừng khi gặp lại chính đối tượng sentinel.

## 12. Bảng đối chiếu ba cách bố trí sentinel

| Tiêu chí | Một dummy head ở danh sách đơn | Hai sentinel ở danh sách đôi tuyến tính | Một sentinel ở danh sách đôi vòng |
| --- | --- | --- | --- |
| Nút giả | 1 | 2 | 1 |
| Liên kết mỗi nút dữ liệu | next | prev, next | prev, next |
| Biểu diễn rỗng | dummy.next is None | before.next is after và after.prev is before | s.next is s và s.prev is s |
| Nút dữ liệu đầu | dummy.next (nếu có) | before.next (nếu có) | s.next (nếu có) |
| Nút dữ liệu cuối | tail thật nếu có lưu | after.prev (nếu có) | s.prev (nếu có) |
| Điểm dừng duyệt xuôi | None | after | s |
| Chèn đầu | Θ(1) | Θ(1) | Θ(1) |
| Thêm cuối | Θ(1) nếu có tail | Θ(1) | Θ(1) |
| Xóa đầu | Θ(1) | Θ(1) | Θ(1) |
| Xóa cuối | Θ(n) nếu phải tìm prev | Θ(1) | Θ(1) |
| Xóa nút đã có tham chiếu | Thường cần nút trước | Θ(1) | Θ(1) |
| Truy cập chỉ số tùy ý | Θ(n) xấu nhất | Θ(n) xấu nhất | Θ(n) xấu nhất |

**Giả định:** các con trỏ, sentinel và bất biến đang đúng; khi phát biểu Θ(1) cho chèn/xóa theo nút, đã có tham chiếu hợp lệ và không tính thời gian tìm/kiểm chứng thành viên.

### Chi phí bộ nhớ

Với n nút dữ liệu, cả ba cấu trúc cần **O(n)** tổng bộ nhớ. Một hoặc hai sentinel chỉ thêm **O(1)** nút, không làm thay đổi bậc độ phức tạp không gian.

Tuy nhiên, cấu trúc đôi có hai tham chiếu **prev/next** cho từng nút, thường tốn nhiều bộ nhớ hơn danh sách đơn có một liên kết. Các nút giả cũng tiêu tốn đối tượng và đòi hỏi cấp phát, khởi tạo, duy trì liên kết.

**Sentinel chủ yếu đơn giản hóa logic trường hợp biên, không tự biến truy cập theo chỉ số từ O(n) thành O(1).** Nếu thao tác thường xuyên là đọc vị trí tùy ý, mảng động có thể phù hợp hơn.

## 13. Điều kiện kết thúc duyệt và các lỗi dễ nhầm

Ba biến thể sử dụng ba điểm dừng khác nhau:

~~~text
Dummy head, danh sách đơn tuyến tính:
dummy → A → B → None
Dừng khi current is None.

Hai sentinel, danh sách đôi tuyến tính:
before ⇄ A ⇄ B ⇄ after
Dừng khi current is after (duyệt xuôi).
Dừng khi current is before (duyệt ngược).

Một sentinel, danh sách đôi vòng:
s ⇄ A ⇄ B ⇄ s
Dừng khi current is s.
~~~

Các lỗi thường gặp:

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Tính dummy/sentinel là một phần tử dữ liệu | Size và kết quả duyệt thừa một nút. | Khởi tạo size = 0, chỉ đếm nút dữ liệu. |
| Kiểm tra rỗng qua **dummy is None** | Luôn sai vì dummy tồn tại suốt vòng đời danh sách. | Kiểm tra dummy.next hoặc size theo bất biến. |
| Nhận diện sentinel bằng **value is None** | Nhầm với nút dữ liệu hợp lệ chứa None. | So sánh danh tính **is sentinel**. |
| Duyệt hai sentinel đến khi gặp None | Xử lý cả after hoặc đi quá biên. | Dừng trước **after** (hoặc trước before khi duyệt ngược). |
| Duyệt sentinel vòng bằng while current is not None | Có thể lặp vô hạn. | Dừng khi current quay về sentinel. |
| Chèn vào danh sách đôi mà chỉ sửa next | Liên kết prev không đối ứng. | Sửa đủ left.next và right.prev. |
| Xóa nút dữ liệu cuối nhưng giữ tail lỗi thời ở danh sách đơn | Lần append sau nối vào nút đã gỡ. | Khi removed is tail, đặt tail = prev. |
| Xóa chính before, after hoặc sentinel vòng | Phá hủy điểm biên cố định của cấu trúc. | API phải từ chối xóa nút giả. |
| Nhầm tail thật với dummy tail | Có thể trả về giá trị giả như dữ liệu hoặc cập nhật sai liên kết. | Đặt tên rõ **after** và **last_data** khi cần. |
| Chuyển một sentinel dùng chung cho hai danh sách | Sửa một danh sách làm hỏng danh sách kia. | Mỗi danh sách sở hữu sentinel riêng. |
| Chèn sau nút không thuộc danh sách | Nút mới không xuất hiện khi duyệt nhưng size có thể tăng. | Đảm bảo tiền điều kiện hoặc kiểm chứng chủ sở hữu. |
| Không xử lý vòng đời nút đã gỡ | Tham chiếu ngoài có thể giữ nút cũ; có thể tái sử dụng sai. | Tách liên kết, quản lý tham chiếu và tài nguyên theo ngôn ngữ. |

Các hàm kiểm chứng dùng tập visited trong ví dụ có thể phát hiện chu trình bất thường hoặc đếm sai; chúng không phải thành phần cần thiết trong mỗi phép chèn/xóa thường ngày. Nếu thêm kiểm tra O(n) sau mọi thao tác, tổng thời gian lời gọi cũng tăng theo n.

## 14. Khi nào nên dùng nút giả hoặc sentinel?

**Hàng đợi bằng danh sách đơn:** dummy head kết hợp tail thật cho phép **enqueue cuối O(1)** và **dequeue đầu O(1)**, kể cả khi hàng đợi chuyển giữa rỗng và có một phần tử. Giữ tail là dummy khi rỗng giúp tránh nhánh xử lý tail là None trong append.

**Deque bằng danh sách đôi:** hai sentinel hoặc một sentinel vòng cho phép chèn và xóa ở cả đầu/cuối bằng các thao tác liên kết cố định. Cần lưu prev và next cho từng nút, nhưng các nhánh xử lý biên gọn hơn.

**LRU cache:** danh sách đôi có sentinel thường được dùng cùng **bảng băm** ánh xạ khóa tới nút dữ liệu. Bảng băm tra nút O(1) *trung bình*, còn việc gỡ/đưa nút vào đầu danh sách là O(1) sau khi đã có tham chiếu. Sentinel giúp cùng một logic hoạt động dù nút được chuyển đang ở đầu, giữa hay cuối. Chỉ dùng danh sách mà không có bảng băm, tìm theo khóa vẫn có thể O(n).

**Quản lý con trỏ trong thuật toán phức tạp:** sentinel hữu ích khi viết nhiều phép chèn/xóa trên một cấu trúc biến đổi liên tục. Tuy nhiên, nếu chỉ cần một danh sách nhỏ, ít thao tác hoặc không muốn thêm đối tượng và các quy tắc sentinel, cài đặt không có nút giả cũng có thể đủ đơn giản.

Điều cần ưu tiên không phải “có sentinel thì luôn nhanh hơn”, mà là **bất biến rõ ràng, mã ít nhánh nhưng đúng và phù hợp với tập thao tác của ứng dụng**.

## 15. Bài tập vận dụng có đáp án

**Bài 1 — Dummy head khi rỗng.** Một danh sách đơn có một dummy head và tail quy ước là dummy nếu rỗng. Khi size = 0, dummy.next và tail bằng gì?

*Đáp án:* **dummy.next is None**, **tail is dummy**; nút giả vẫn tồn tại nhưng không phải phần tử dữ liệu.

**Bài 2 — Chèn đầu.** Danh sách đơn đang là dummy → A → B → None. Nếu chèn X sau dummy, chuỗi kết quả và tail có đổi không?

*Đáp án:* **dummy → X → A → B → None**. Tail vẫn là B vì nút cuối dữ liệu không thay đổi.

**Bài 3 — Xóa phần tử cuối cùng.** Danh sách đơn có dummy → A → None và tail là A. Gọi remove_after(dummy) cần đặt tail thành gì?

*Đáp án:* Sau khi xóa A, **tail = dummy** và **dummy.next = None**, size = 0.

**Bài 4 — Hai sentinel và danh sách rỗng.** Với before và after của danh sách đôi tuyến tính, khi không có dữ liệu thì hai liên kết giữa chúng là gì?

*Đáp án:* **before.next is after**, **after.prev is before**. Size bằng 0; before và after không tính là dữ liệu.

**Bài 5 — Chèn vào danh sách đôi rỗng.** Gọi chèn nút X vào giữa before và after. Hãy viết bốn phép gán liên kết.

*Đáp án:* **X.prev = before**, **X.next = after**, **before.next = X**, **after.prev = X**.

**Bài 6 — Xóa nút duy nhất.** Danh sách before ⇄ X ⇄ after có một nút dữ liệu. Khi remove_node(X), có cần phân nhánh head/tail không?

*Đáp án:* Không nếu dùng thiết kế hai sentinel. Chỉ cần **before.next = after**, **after.prev = before**, tách liên kết của X và giảm size.

**Bài 7 — Giá trị None.** Trong danh sách có hai sentinel, nút dữ liệu đầu chứa None. Có thể dùng **current.value is None** để dừng duyệt không?

*Đáp án:* Không. Phải dừng khi **current is after**; dữ liệu có giá trị None vẫn là một phần tử hợp lệ.

**Bài 8 — Sentinel vòng khi rỗng.** Trong danh sách đôi vòng dùng một sentinel s, s.prev và s.next là gì khi size = 0?

*Đáp án:* Cả hai đều trỏ **chính s**.

**Bài 9 — Điều kiện kết thúc.** Có chuỗi s ⇄ A ⇄ B ⇄ s trong danh sách đôi vòng. Muốn duyệt xuôi hai nút dữ liệu, khởi đầu và điều kiện dừng là gì?

*Đáp án:* Bắt đầu tại **s.next (A)**, lần lượt xử lý A và B, dừng khi **current is s**. Không dùng None.

**Bài 10 — Độ phức tạp.** Danh sách đôi có hai sentinel, đã có tham chiếu đúng tới nút cần xóa. Thời gian xóa là bao nhiêu? Nếu chỉ biết giá trị cần xóa thì sao?

*Đáp án:* Xóa theo tham chiếu hợp lệ là **Θ(1)**. Nếu chỉ có giá trị, bước tìm có thể mất **Θ(n)** trong trường hợp xấu nhất; tổng thao tác khi đó cũng có thể Θ(n).

**Bài 11 — Kiểm tra lỗi.** Sau thao tác chèn giữa left và right, ta có left.next is X và X.next is right, nhưng right.prev vẫn là left. Cấu trúc có hợp lệ không?

*Đáp án:* Không. **right.prev phải là X**, đồng thời **X.prev phải là left**. Nếu không, liên kết hai chiều mất tính đối ứng.

**Bài 12 — So sánh ba thiết kế.** Trường hợp nào phù hợp hơn khi cần xóa cuối thường xuyên: danh sách đơn với dummy head hay danh sách đôi có sentinel? Vì sao?

*Đáp án:* **Danh sách đôi có sentinel** phù hợp hơn vì từ nút cuối có thể truy cập nút đứng trước qua prev, cho phép xóa cuối Θ(1). Danh sách đơn với dummy head vẫn cần tìm nút đứng trước tail, thường tốn Θ(n).

**Ghi nhớ:** Dummy head, dummy tail và sentinel là **nút cấu trúc**, không phải dữ liệu. Dummy head giúp đơn giản hóa thao tác đầu danh sách đơn; hai sentinel giúp thống nhất chèn/xóa ở mọi biên của danh sách đôi; một sentinel vòng vừa làm mốc biên vừa là điều kiện dừng duyệt. Luôn xác định **bất biến rỗng, liên kết biên và điểm dừng**, không dựa vào giá trị dữ liệu để nhận biết nút canh gác. Lợi ích chính của sentinel là giảm lỗi ở các trường hợp đặc biệt, chứ không thay thế việc phân tích chi phí tìm nút.

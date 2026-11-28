# Duyệt tuần tự và chi phí truy cập theo vị trí

Danh sách liên kết đơn (*singly linked list*) gồm các nút; mỗi nút lưu giá trị và tham chiếu **next** đến nút kế tiếp. Các nút không nhất thiết nằm kề nhau trong bộ nhớ. Muốn đọc một nút ở giữa, chương trình thường phải bắt đầu từ **head** rồi lần lượt đi theo các liên kết. Đi từ một nút sang nút kế tiếp là việc đơn giản; **tìm đến vị trí bất kỳ** mới là phần tốn thời gian.

Trong mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, chủ đề thuộc chương **Danh sách liên kết**, giúp xây dựng nền tảng về bất biến, thao tác và độ phức tạp thời gian/bộ nhớ để lựa chọn cấu trúc phù hợp. Bài này tập trung vào kỹ thuật duyệt tuần tự, cách truy cập theo chỉ số, cách tính chi phí và những vòng lặp dễ vô tình trở thành O(n²).

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Vẽ đường đi theo **next** từ head tới nút cuối và xác định điểm dừng.
- Cài đặt duyệt bằng vòng lặp, lấy giá trị theo chỉ số và tìm kiếm tuyến tính.
- Giải thích vì sao đi một bước theo **next** là O(1) nhưng đến nút ở chỉ số k mất Θ(k + 1) khi đi từ head.
- Phân biệt thời gian tốt nhất, xấu nhất, trung bình và bộ nhớ phụ của thao tác truy cập.
- Tránh sử dụng truy cập theo vị trí lặp lại khiến toàn bộ một lượt duyệt mất Θ(n²).
- So sánh nhu cầu duyệt, đọc theo chỉ số giữa danh sách liên kết đơn và mảng động.

## 2. Tại sao phải duyệt từng nút?

Xét danh sách gồm năm nút, đánh chỉ số bắt đầu từ 0:

~~~text
       head
         │
         ▼
index:   0           1           2           3           4
       [ 5 | • ] ─► [ 8 | • ] ─► [13 | • ] ─► [21 | • ] ─► [34 | None]
                                                                ▲
                                                               tail
~~~

Nút ở chỉ số 0 chỉ biết nút ở chỉ số 1 qua trường **next**. Nó không lưu thông tin về nút ở chỉ số 3 hoặc 4. Vì vậy, để đọc giá trị 21 ở chỉ số 3 từ head, chương trình phải đi qua ba liên kết.

Một nút có thể được biểu diễn trong Python như sau:

~~~python
class Node:
    def __init__(self, value, next_node=None):
        self.value = value
        self.next = next_node
~~~

Trong Python, **next** là tham chiếu đến một đối tượng nút; trong C, ý tưởng tương đương thường được biểu diễn bằng con trỏ. Câu lệnh:

~~~python
current = current.next
~~~

chuyển biến **current** từ nút hiện tại sang nút ngay sau. Đây là thao tác **O(1)**, bởi chỉ cần đọc một tham chiếu, không cần quét toàn bộ danh sách.

**Phân biệt:** O(1) cho *một bước* không có nghĩa O(1) để đi tới *bất kỳ chỉ số nào*. Chẳng hạn cần 1.000 bước để đến nút ở chỉ số 1.000 nếu chỉ biết head.

Danh sách có thể lưu thêm **tail** để tham chiếu trực tiếp đến nút cuối. Tuy nhiên, danh sách liên kết **đơn** không có tham chiếu quay ngược về nút trước, nên tail không giúp nhảy tới các nút ở giữa.

## 3. Vòng lặp duyệt tuần tự

Thuật toán tổng quát:

~~~text
current ← head
while current khác None:
    xử lý current.value
    current ← current.next
~~~

Nếu head trỏ tới chuỗi **5 → 8 → 13 → 21 → 34 → None**, ta có bảng:

| Lượt duyệt | Nút current | Giá trị được xử lý | current sau khi di chuyển |
| ---: | --- | ---: | --- |
| 1 | Chỉ số 0 | 5 | Chỉ số 1 |
| 2 | Chỉ số 1 | 8 | Chỉ số 2 |
| 3 | Chỉ số 2 | 13 | Chỉ số 3 |
| 4 | Chỉ số 3 | 21 | Chỉ số 4 |
| 5 | Chỉ số 4 | 34 | None |
| Kết thúc | None | Không xử lý | Thoát vòng lặp |

Ví dụ Python:

~~~python
current = head

while current is not None:
    print(current.value)
    current = current.next
~~~

**Vì sao dùng điều kiện current is not None?** Bởi nút cuối cũng phải được xử lý: tại nút cuối, **current vẫn là một nút hợp lệ** và chỉ có **current.next** bằng None. Nếu viết điều kiện **current.next is not None**, chương trình bỏ qua nút cuối. Khi head là None, biểu thức **current.next** còn gây lỗi.

Với danh sách rỗng, **head is None**, vòng lặp dừng ngay mà không xử lý nút nào. Với danh sách chỉ có một nút, vòng lặp chạy đúng một lượt.

Nếu có n nút và phần xử lý mỗi nút là O(1), duyệt toàn bộ mất **Θ(n)** thời gian. Biến current chỉ sử dụng **O(1)** bộ nhớ phụ. Nếu xử lý từng nút là một công việc tốn nhiều thời gian hơn, chi phí xử lý đó phải được cộng vào tổng thời gian của thuật toán.

### Bất biến của vòng lặp

Ở đầu mỗi lượt, current hoặc là nút chưa xử lý tiếp theo trên đường đi từ head, hoặc là None khi đã đi hết. Sau khi xử lý current, lệnh **current = current.next** chuyển đến nút kế tiếp. Vòng lặp dừng khi gặp None, nên điều kiện để thuật toán kết thúc là chuỗi liên kết không có chu trình.

Nếu cập nhật sai để **next** trỏ ngược về nút đã thăm, vòng lặp có thể chạy vô hạn. Thuật toán duyệt thông thường giả định danh sách có cấu trúc hợp lệ và nút cuối có **next = None**.

## 4. Truy cập vị trí k: đếm số bước

Giả sử chỉ số hợp lệ **0 ≤ k < n**, với n là số nút. Thuật toán lấy nút ở vị trí k:

~~~text
current ← head
lặp k lần:
    current ← current.next
trả về current
~~~

Truy cập chỉ số 3 trong ví dụ:

~~~text
Bắt đầu:  current → 5  (index 0)
Bước 1:   current → 8  (index 1)
Bước 2:   current → 13 (index 2)
Bước 3:   current → 21 (index 3)
Đọc giá trị 21
~~~

Có **k lần chuyển qua next**, nhưng **k + 1 nút** nằm trên đường đi tính cả nút đầu. Do đó, khi thuật toán luôn bắt đầu từ head, thời gian là **Θ(k + 1)**.

| Chỉ số cần đọc | Số lần đi theo next | Số nút trên đường đi | Nhận xét |
| ---: | ---: | ---: | --- |
| 0 | 0 | 1 | Truy cập head trong Θ(1). |
| 1 | 1 | 2 | Chi phí cố định nếu k = 1. |
| 3 | 3 | 4 | Phải đi qua các nút trước. |
| n − 1 | n − 1 | n | Mất Θ(n) trong trường hợp xấu nhất. |

Việc viết Θ(k + 1) chính xác hơn Θ(k) khi k có thể bằng 0, vì đọc head vẫn có chi phí hằng số.

### Tốt nhất, trung bình và xấu nhất

Với n > 0, nếu thao tác đọc một chỉ số luôn đi từ head:

- **Tốt nhất:** k = 0, đọc ngay head, thời gian Θ(1).
- **Xấu nhất:** k = n − 1, gần như duyệt hết danh sách, thời gian Θ(n).
- **Trung bình:** nếu tất cả chỉ số hợp lệ được chọn đều nhau, số lần chuyển next trung bình là **(n − 1) / 2**, nên thời gian trung bình Θ(n).

Kết quả trung bình phụ thuộc phân bố truy cập. Nếu phần lớn yêu cầu chỉ lấy head, thời gian trung bình thực tế có thể gần hằng số. Khi nói “truy cập theo vị trí có độ phức tạp O(n)”, ta đang nói về **trường hợp xấu nhất đối với vị trí tùy ý**.

### Tail có làm mọi truy cập nhanh hơn không?

Nếu đã lưu tail chính xác, chương trình có thể lấy **nút cuối** trong O(1) bằng chính tham chiếu tail. Điều đó không giúp đọc **nút trước tail** trong O(1) trên danh sách đơn: tail không có trường **prev**. Một API tối ưu riêng cho phần tử cuối vẫn có thể mất Θ(n) đối với các vị trí khác.

## 5. Chỉ số ngoài phạm vi

Bài này dùng quy tắc **chỉ số nguyên không âm, bắt đầu từ 0**:

- Chỉ số hợp lệ khi **0 ≤ index < size**.
- Chỉ số âm hoặc index ≥ size gây **IndexError**.
- Danh sách rỗng có size = 0 nên không có vị trí hợp lệ.
- Giá trị của nút có thể là None; không thể lấy việc trả về None làm bằng chứng chỉ số không tồn tại.

Một cách truy cập cơ bản khi danh sách có thuộc tính head và size:

~~~python
def get_node(self, index):
    if not isinstance(index, int):
        raise TypeError("Chỉ số phải là số nguyên")
    if index < 0 or index >= self.size:
        raise IndexError("Chỉ số ngoài phạm vi")

    current = self.head
    for _ in range(index):
        current = current.next

    return current
~~~

Hàm giả định **size đúng bằng số nút có thể đi tới từ head**, và các liên kết hợp lệ. Nếu có sẵn size, việc từ chối chỉ số ngoài phạm vi chỉ mất **O(1)** thời gian cho các phép kiểm tra biên.

Nếu không lưu size, để biết một chỉ số quá lớn có hợp lệ không, chương trình thường phải đi tới None, mất **O(n)** trong trường hợp xấu nhất. Với danh sách hỗ trợ chỉ số âm kiểu Python, có thể quy đổi index âm thành **size + index** khi biết size, nhưng việc đến nút ở vị trí mới vẫn cần duyệt thông thường.

## 6. Ví dụ Python hoàn chỉnh: get, find và iterator

Dưới đây là cài đặt tự chứa sử dụng **head**, **tail** và **size**. Phương thức **get** đọc một vị trí; **find_index** tìm chỉ số của giá trị xuất hiện đầu tiên; **__iter__** cho phép duyệt bằng vòng lặp for và tránh phải tìm lại head mỗi lần.

~~~python
class Node:
    def __init__(self, value, next_node=None):
        self.value = value
        self.next = next_node


class SinglyLinkedList:
    def __init__(self):
        self.head = None
        self.tail = None
        self.size = 0

    def append(self, value):
        node = Node(value)
        if self.tail is None:
            self.head = node
        else:
            self.tail.next = node
        self.tail = node
        self.size += 1

    def __len__(self):
        return self.size

    def get_node(self, index):
        if not isinstance(index, int):
            raise TypeError("Chỉ số phải là số nguyên")
        if index < 0 or index >= self.size:
            raise IndexError("Chỉ số ngoài phạm vi")

        current = self.head
        for _ in range(index):
            current = current.next
        return current

    def get(self, index):
        return self.get_node(index).value

    def __iter__(self):
        current = self.head
        while current is not None:
            yield current.value
            current = current.next

    def find_index(self, target):
        current = self.head
        index = 0
        while current is not None:
            if current.value == target:
                return index
            current = current.next
            index += 1
        return -1


items = SinglyLinkedList()
for value in [5, 8, 13, 21, 34]:
    items.append(value)

assert len(items) == 5
assert items.get(0) == 5
assert items.get(3) == 21
assert items.get(4) == 34
assert items.find_index(13) == 2
assert items.find_index(99) == -1
assert list(items) == [5, 8, 13, 21, 34]
assert sum(items) == 81
assert items.get_node(0) is items.head
assert items.get_node(4) is items.tail

empty = SinglyLinkedList()
assert list(empty) == []
empty.append(None)
assert len(empty) == 1
assert empty.get(0) is None

try:
    items.get(-1)
except IndexError:
    pass
else:
    raise AssertionError("Thiếu IndexError cho chỉ số âm")

try:
    items.get(5)
except IndexError:
    pass
else:
    raise AssertionError("Thiếu IndexError cho chỉ số vượt cuối")
~~~

**Độ phức tạp:**

- **append:** O(1) khi có tail, không bao gồm chi phí tạo/cấp phát nút cụ thể.
- **get(index):** Θ(index + 1) với chỉ số hợp lệ; O(1) bộ nhớ phụ.
- **find_index(value):** Θ(n) trong trường hợp xấu nhất, chẳng hạn không có giá trị cần tìm.
- **__iter__:** toàn bộ một lượt duyệt mất Θ(n), dùng O(1) bộ nhớ phụ cho vị trí current.

### Vì sao iterator hữu ích?

Hàm **__iter__** là một *generator*: sau mỗi lần trả giá trị bằng **yield**, nó giữ trạng thái current để tiếp tục tại nút kế tiếp. Vì vậy:

~~~python
for value in items:
    print(value)
~~~

chỉ đi qua danh sách **một lần**. Nếu chuyển tất cả giá trị sang mảng bằng **list(items)**, bản thân quá trình duyệt vẫn Θ(n), nhưng mảng kết quả mới cần thêm **O(n)** bộ nhớ.

**Giới hạn:** Generator trên không tự phát hiện khi liên kết bị thay đổi trong lúc duyệt. Chèn, xóa hoặc nối lại nút giữa các lần lấy phần tử có thể làm đổi kết quả, bỏ sót nút hoặc tạo chu trình. Khi thuật toán cần chỉnh sửa cấu trúc lúc duyệt, phải xác định thứ tự cập nhật và hành vi iterator rõ ràng.

## 7. Bẫy hiệu năng: get(i) trong vòng lặp

Trên mảng Python, truy cập **array[i]** là O(1), nên duyệt bằng chỉ số hợp lý:

~~~python
for i in range(len(array)):
    process(array[i])
~~~

Với danh sách liên kết đơn, cách viết tương tự có thể gây vấn đề:

~~~python
# Mỗi lời gọi get(i) lại bắt đầu từ head.
for i in range(len(items)):
    process(items.get(i))
~~~

Giả sử có n nút. Lời gọi **get(0)** xét 1 nút; **get(1)** xét 2 nút; ...; **get(n − 1)** xét n nút. Tổng lượt xét nút là:

\[
1 + 2 + \cdots + n = \frac{n(n+1)}{2} = \Theta(n^2).
\]

Với n = 1.000, tổng là **500.500 lượt xét nút**, trong khi một lượt duyệt tuần tự chỉ xét 1.000 nút. Đây là khác biệt giữa việc **đi tiếp từ vị trí hiện tại** với việc **đi lại từ head nhiều lần**.

Cách thích hợp khi muốn xử lý mọi phần tử theo thứ tự:

~~~python
# Một lượt đi qua toàn bộ danh sách.
for value in items:
    process(value)

# Hoặc dùng current trực tiếp:
current = items.head
while current is not None:
    process(current.value)
    current = current.next
~~~

Nếu **process** tốn O(1) cho mỗi phần tử, hai cách trên đều có tổng thời gian Θ(n).

Ví dụ tính tổng có thể chạy độc lập cùng cài đặt ở mục 6:

~~~python
total_slow = sum(items.get(i) for i in range(len(items)))
total_fast = sum(items)

assert total_slow == total_fast == 81
~~~

Kết quả bằng nhau, nhưng thuật toán đầu mất Θ(n²) vì phải duyệt từ head nhiều lần; thuật toán sau mất Θ(n) vì giữ vị trí duyệt.

**Truy cập theo chỉ số không phải lúc nào cũng sai:** nếu chỉ cần đọc một vị trí, **get(index)** vẫn là API rõ nghĩa. Cần tránh gọi nó cho tất cả vị trí để thay thế cho một lượt duyệt tuần tự.

## 8. Tìm giá trị cũng là một lượt duyệt

Khác với truy cập theo chỉ số, bài toán tìm kiếm cho trước **giá trị** mà chưa biết nó nằm ở nút nào. Thuật toán lần lượt so sánh từ head:

~~~python
def find_index(head, target):
    current = head
    index = 0

    while current is not None:
        if current.value == target:
            return index
        current = current.next
        index += 1

    return -1
~~~

Trên chuỗi **5 → 8 → 13 → 21 → 34**:

- Tìm 5 chỉ cần kiểm tra nút đầu: **Θ(1)**.
- Tìm 21 cần kiểm tra lần lượt 5, 8, 13, 21.
- Tìm 99 phải kiểm tra hết năm nút rồi mới biết không tìm thấy.

Trong trường hợp xấu nhất, tìm tuyến tính mất **Θ(n)** thời gian, sử dụng **O(1)** bộ nhớ phụ. Nếu danh sách có giá trị trùng nhau, thuật toán trả về **vị trí xuất hiện đầu tiên**.

Bảng phân biệt hai yêu cầu:

| Yêu cầu | Thông tin đầu vào | Điều kiện dừng |
| --- | --- | --- |
| Lấy giá trị tại chỉ số k | Biết k | Đi đúng k bước từ head sau khi kiểm tra biên. |
| Tìm chỉ số của giá trị x | Biết x | Dừng khi gặp x hoặc đi tới None. |
| Xử lý tất cả giá trị | Không có vị trí đích | Dừng khi đi tới None. |

Dù dữ liệu được sắp xếp, tìm kiếm nhị phân kiểu mảng cũng không có lợi thế như trên mảng nếu mỗi lần tìm nút giữa đều cần duyệt từ head. Có thể dùng những thuật toán cấu trúc khác, nhưng danh sách đơn cơ bản vẫn dựa trên liên kết kế tiếp.

## 9. Tổng hợp thời gian và bộ nhớ

Bảng dưới đây giả định danh sách đơn có n nút, không có chu trình, các bất biến đúng và phần xử lý giá trị tại một nút là O(1).

| Thao tác | Thời gian | Bộ nhớ phụ | Lý do |
| --- | --- | --- | --- |
| Đọc head | Θ(1) | O(1) | Đã có tham chiếu đầu. |
| Đi sang nút tiếp theo | Θ(1) | O(1) | Chỉ đọc một next. |
| Đọc chỉ số k hợp lệ từ head | Θ(k + 1) | O(1) | Phải đi qua k liên kết. |
| Đọc chỉ số tùy ý, xấu nhất | Θ(n) | O(1) | Có thể phải đến nút cuối. |
| Duyệt toàn bộ bằng while hoặc iterator | Θ(n) | O(1) | Mỗi nút xét đúng một lần. |
| Tìm giá trị, xấu nhất | Θ(n) | O(1) | Có thể không tìm thấy. |
| Tạo mảng giá trị bằng list(items) | Θ(n) | O(n) | Sao chép n tham chiếu giá trị vào mảng. |
| Duyệt bằng n lần get(i) | Θ(n²) | O(1) | Lặp lại nhiều đoạn từ head. |
| Kiểm tra chỉ số ngoài biên khi có size | Θ(1) | O(1) | So sánh index với size. |
| Đếm số nút nếu không lưu size | Θ(n) | O(1) | Duyệt đến None. |

Tổng dung lượng lưu n nút là **O(n)**, vì mỗi nút có phần dữ liệu và một tham chiếu next. Bộ nhớ phụ **O(1)** của phép duyệt không bao gồm danh sách gốc; nếu thuật toán tạo kết quả gồm n giá trị, phần kết quả đó cần O(n).

Chi phí thực tế còn chịu ảnh hưởng bởi bộ nhớ đệm CPU: các nút có thể nằm rải rác trong bộ nhớ, khiến việc đi theo con trỏ kém thuận lợi hơn truy cập tuần tự phần tử trong mảng. Phân tích O lớn biểu diễn mức tăng theo n, không mô tả mọi hằng số thời gian.

### So sánh với mảng động

| Tiêu chí | Danh sách liên kết đơn | Mảng động (ví dụ list Python) |
| --- | --- | --- |
| Truy cập chỉ số k | Θ(k + 1) từ head, xấu nhất Θ(n) | Θ(1) |
| Duyệt n phần tử | Θ(n) | Θ(n) |
| Thêm đầu | O(1) | O(n) do dời phần tử |
| Chèn sau nút đã có tham chiếu | O(1) | Chèn tại vị trí thường cần dời phần tử |
| Khả năng truy cập phần tử liền kề | Đi theo next | Đi theo chỉ số/bộ nhớ liên tiếp |

**Lưu ý:** Lợi thế chèn sau một nút đã biết chỉ áp dụng **khi đã có tham chiếu tới nút đó**. Nếu phải tìm nút theo chỉ số trước khi chèn, tổng chi phí có thể là Θ(n).

## 10. Lỗi thường gặp khi duyệt

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng điều kiện current.next khác None để duyệt | Bỏ sót nút cuối và có thể lỗi với danh sách rỗng. | Dùng **current is not None**. |
| Không thực hiện current = current.next | Có thể xử lý mãi một nút. | Luôn cập nhật current khi chưa kết thúc. |
| Đọc current.value sau khi current thành None | Lỗi truy cập thuộc tính. | Kiểm tra current trước khi dùng. |
| Lẫn chỉ số 0 và 1 | Truy cập sai vị trí. | Xác định quy ước từ 0 và kiểm tra index = 0, n − 1. |
| Dùng get(i) để duyệt mọi phần tử | Tăng từ Θ(n) lên Θ(n²). | Giữ current hoặc dùng iterator. |
| Trả None để báo chỉ số không tồn tại | Nhầm nút có giá trị None với lỗi truy cập. | Báo IndexError hoặc trả kết quả có trạng thái riêng. |
| Liên kết next vô tình tạo chu trình | Duyệt có thể không kết thúc. | Duy trì bất biến không chu trình; kiểm tra nếu nghi sai. |
| Chỉnh sửa liên kết bất cẩn khi đang duyệt | Có thể bỏ sót nút hoặc lặp sai. | Xác định rõ thứ tự cập nhật và lưu tham chiếu cần thiết. |

Một cách kiểm tra đơn giản là lần theo sơ đồ **head → next → ... → None**, ghi lại current trước và sau mỗi vòng. Với danh sách có ba nút A → B → C, vòng lặp đúng phải xử lý A, B, C theo thứ tự rồi dừng.

## 11. Bài tập vận dụng

**Bài 1 — Đếm bước.** Cho danh sách **3 → 6 → 9 → 12 → 15 → None**. Để đọc giá trị ở chỉ số 4, có bao nhiêu lần cập nhật current = current.next khi bắt đầu từ head?

*Đáp án:* Có **4 lần cập nhật** và 5 nút trên đường đi tính cả nút đầu.

**Bài 2 — Lỗi điều kiện.** Vì sao đoạn mã dưới đây không in nút cuối?

~~~python
current = head
while current is not None and current.next is not None:
    print(current.value)
    current = current.next
~~~

*Đáp án:* Khi current ở nút cuối thì current.next bằng None, điều kiện sai trước khi in giá trị cuối. Sửa thành **while current is not None**.

**Bài 3 — Tổng chi phí.** Một chương trình gọi lần lượt get(0), get(1), ..., get(999) trên danh sách 1.000 nút, mỗi lần bắt đầu từ head. Bỏ qua chi phí khác, tổng số nút được xét là bao nhiêu?

*Đáp án:* **1 + 2 + ... + 1.000 = 500.500** lượt xét nút, tương ứng Θ(n²). Duyệt bằng current chỉ xét 1.000 nút.

**Bài 4 — Chọn cách lặp.** Ứng dụng cần xử lý mỗi sự kiện đúng một lần theo thứ tự nhận. Nên dùng n lần get(i) hay một lượt duyệt bằng current?

*Đáp án:* Dùng một lượt duyệt bằng current hoặc iterator, vì mỗi nút chỉ được thăm một lần, tổng thời gian Θ(n) nếu mỗi sự kiện xử lý O(1).

**Bài 5 — Truy cập cuối.** Danh sách có cả head và tail. Có thể đọc phần tử cuối trong O(1) không? Có thể đọc phần tử ngay trước tail trong O(1) không?

*Đáp án:* Có thể đọc tail trong O(1). Với danh sách liên kết đơn cơ bản, tail không lưu liên kết ngược nên muốn tìm nút trước tail vẫn thường phải duyệt từ head, mất Θ(n).

**Bài 6 — Danh sách rỗng.** Nếu head = None và size = 0, duyệt chạy mấy vòng? Hàm get(0) nên xử lý thế nào?

*Đáp án:* Duyệt chạy **0 vòng**. Theo API trong bài, get(0) ném **IndexError** vì vị trí 0 không tồn tại.

**Ghi nhớ:** Mỗi bước đi theo **next** có chi phí O(1), nhưng đi từ head đến vị trí k cần k bước, tức **Θ(k + 1)**. Một lần duyệt n nút chỉ tốn **Θ(n)**, còn duyệt bằng n lời gọi get(i) có thể tốn **Θ(n²)**. Đây là lý do cần phân biệt thao tác tại một nút đã biết với thao tác tìm nút theo vị trí khi lựa chọn cấu trúc dữ liệu.

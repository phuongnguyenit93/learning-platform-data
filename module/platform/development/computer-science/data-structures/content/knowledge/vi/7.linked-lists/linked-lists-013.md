# Phát hiện chu trình và phân biệt chu trình hợp lệ với lỗi liên kết

Trong **danh sách liên kết**, ta thường duyệt từ **head**, lần lượt đi theo **next** để xử lý các nút. Với **danh sách tuyến tính**, một chuỗi đúng phải kết thúc ở **None**. Nhưng nếu một liên kết vô tình trỏ về nút đã đi qua, việc duyệt có thể lặp vô hạn. Ngược lại, trong **danh sách vòng**, quay về đầu là **một phần của thiết kế**, không phải lỗi.

Vì vậy, cần trả lời **hai câu hỏi riêng biệt**:

1. Từ head, đi theo next **có gặp một nút đã thăm hay không**? Đây là bài toán **phát hiện chu trình** (*cycle detection*).
2. Nếu có chu trình, nó có **đúng hình dạng được quy định bởi kiểu danh sách** hay không? Đây là bài toán **kiểm tra bất biến cấu trúc** (*structural validation*).

Hai câu hỏi không tương đương: thuật toán Floyd có thể xác nhận tồn tại chu trình, nhưng **không tự kết luận đó là vòng hợp lệ**.

Bài thuộc chương **Danh sách liên kết** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, với mục tiêu xây dựng nền tảng về bất biến, thao tác, thời gian và bộ nhớ để chọn cấu trúc phù hợp cho từng bài toán.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích thế nào là **chu trình** trong đồ thị các liên kết next của danh sách đơn.
- Phân biệt danh sách đơn tuyến tính hợp lệ, danh sách vòng đơn hợp lệ và chu trình xuất hiện do lỗi.
- Dùng **tập nút đã thăm** để phát hiện nút bị lặp và xác định điểm vào chu trình.
- Cài đặt **Floyd's tortoise and hare** bằng hai tham chiếu chậm/nhanh với O(1) bộ nhớ phụ.
- Tìm **nút bắt đầu chu trình**, số nút trước chu trình (**μ**) và độ dài chu trình (**λ**).
- Kiểm tra tính hợp lệ dựa trên **head**, **tail**, **size**, nút cuối và khả năng quay về head.
- Đánh giá thêm liên kết **prev** của danh sách đôi và ranh giới **sentinel** khi có nút canh gác.
- Tránh các bẫy như so sánh giá trị thay vì danh tính, duyệt mãi đến None trên danh sách vòng hoặc sửa chuỗi khi chưa biết biến thể.
- Phân tích chi phí thời gian/bộ nhớ và sử dụng ví dụ Python để kiểm chứng các trường hợp biên.

## 2. Xem các liên kết như một đồ thị có hướng

Trong danh sách liên kết đơn, mỗi nút có **tối đa một** liên kết next đến một nút khác. Xét các nút đi tới được từ head; đường đi sẽ có một trong hai dạng chính nếu cấu trúc hữu hạn:

- **Kết thúc:** một nút có next là None, không có chu trình trên đường đi từ head.
- **Lặp lại:** một nút xuất hiện lần thứ hai, tạo chu trình có thể đi mãi theo next.

### 2.1. Danh sách tuyến tính hợp lệ

~~~text
head
 │
 ▼
 A ──► B ──► C ──► None
                ▲
               tail
~~~

Nếu **head = A**, **tail = C**, **size = 3**, các điều kiện cần có là:

- A, B, C là ba đối tượng nút khác nhau.
- Đi theo next từ head gặp đúng ba nút rồi đến None.
- **tail.next is None**.
- Nút cuối thực sự đi tới từ head là tail.

**Không phát hiện chu trình** là điều cần nhưng **chưa đủ** để chứng minh toàn bộ metadata đúng: tail có thể trỏ sai hoặc size có thể sai dù chuỗi A → B → C → None không có vòng.

### 2.2. Danh sách vòng đơn hợp lệ

~~~text
head
 │
 ▼
 A ──► B ──► C
 ▲            │
 └────────────┘
              ▲
             tail
~~~

Ở đây **C.next is A**, tức **tail.next is head**. Chu trình là **cố ý**. Để đúng theo mô hình head/tail/size không có sentinel:

- A, B, C là những nút thuộc cùng một vòng.
- Từ head đi đúng **size = 3 bước next** phải quay lại head.
- Không quay về head sớm và không lặp một nút khác trước đó.
- Nút ngay trước head trong vòng là **tail**.

Với một nút duy nhất X, dạng hợp lệ là **X.next is X**; thuật toán phát hiện chu trình sẽ trả về X dù dữ liệu hoàn toàn không lỗi.

### 2.3. Chu trình phát sinh từ lỗi nối liên kết

~~~text
head
 │
 ▼
 A ──► B ──► C
       ▲     │
       └─────┘
~~~

Từ A, các nút được gặp theo thứ tự:

~~~text
A, B, C, B, C, B, C, ...
~~~

Có chu trình **B → C → B**, nhưng nó **không quay về A**. Nếu cấu trúc được khai báo là danh sách tuyến tính, đây là lỗi vì không kết thúc ở None. Nếu khai báo là danh sách vòng đơn với head = A, đây **cũng là lỗi**, vì head không nằm trong chu trình.

Kết luận quan trọng:

> **Có chu trình** chưa đủ để nói **danh sách vòng hợp lệ**. Phải biết **hợp đồng của cấu trúc** và kiểm tra đúng bất biến của hợp đồng đó.

## 3. Phân biệt chu trình, điểm vào và độ dài vòng

Một đường đi có chu trình có thể chia thành:

~~~text
head ──► P0 ──► P1 ──► E ──► Q1 ──► Q2
                       ▲              │
                       └──────────────┘
                       điểm vào vòng
~~~

Đặt:

- **μ (mu)**: số cạnh next cần đi từ head để đến **điểm vào chu trình E** lần đầu; chính là số nút nằm **trước vòng**.
- **λ (lambda)**: số nút khác nhau nằm trong **chu trình**, cũng là số bước từ E đi theo next để quay về E.
- **Điểm vào** (*cycle entry*): nút đầu tiên thuộc chu trình khi đi từ head.

Trong sơ đồ, **head là biến tham chiếu tới P0**, không phải một nút thêm vào danh sách. Vì vậy, có **hai nút trước vòng** là P0 và P1, nên μ = 2. Một ví dụ khác:

~~~text
A ──► B ──► C ──► D
       ▲           │
       └───────────┘

head = A
Điểm vào = B
μ = 1            (A → B)
λ = 3            (B → C → D → B)
~~~

Ba dạng thường gặp:

| Hình dạng | Chu trình? | μ | λ | Ý nghĩa |
| --- | --- | ---: | ---: | --- |
| A → B → None | Không | Không áp dụng | Không áp dụng | Tuyến tính |
| A → B → C → A | Có | 0 | 3 | Ứng viên vòng đơn hợp lệ |
| A → B → C → B | Có | 1 | 2 | Vòng nằm sau một đoạn dẫn; không phải vòng đơn bắt đầu ở head |
| X → X | Có | 0 | 1 | Vòng một nút, hợp lệ nếu kiểu là danh sách vòng |
| A → B → A nhưng size khai báo 3 | Có | 0 | 2 | Không hợp lệ với size = 3 |

**μ = 0 và λ = size** là điều kiện quan trọng của một vòng đơn không sentinel khi head hợp lệ. Ngoài ra phải kiểm tra **tail**, các nút thực sự đi tới được và những metadata khác theo thiết kế.

## 4. Phương pháp 1: tập các nút đã thăm

Cách trực quan nhất là duyệt theo next, lưu **danh tính** của mỗi nút trong một tập.

~~~text
current = head
visited = tập rỗng

lặp khi current không là None:
    nếu current đã xuất hiện trong visited:
        phát hiện chu trình
    thêm current vào visited
    current = current.next

nếu gặp None:
    không có chu trình trên đường đi từ head
~~~

Python:

~~~python
def first_repeated_node(head):
    visited = set()
    current = head

    while current is not None:
        key = id(current)
        if key in visited:
            return current
        visited.add(key)
        current = current.next

    return None
~~~

**Vì sao lưu id(current)?** Mục tiêu là phát hiện **cùng đối tượng nút** xuất hiện lần thứ hai, không phải hai nút có giá trị bằng nhau. Trong Python, các lớp có thể tùy biến phép so sánh **==** hoặc trở thành không băm được; dùng **id** cho các đối tượng vẫn đang được tham chiếu trên đường duyệt giúp so sánh danh tính rõ ràng. Vì visited chỉ lưu số định danh, khi triển khai ở hệ thống có vòng đời đối tượng khác cần cân nhắc cách duy trì tham chiếu sống; đối với mã Python minh họa có thể dùng tập chứa **đối tượng nút** khi Node dùng hash theo danh tính.

Một biến thể dùng tập chứa chính đối tượng Node nếu lớp không định nghĩa so sánh theo giá trị:

~~~python
def first_repeated_node_by_object(head):
    visited = set()
    current = head
    while current is not None:
        if current in visited:
            return current
        visited.add(current)
        current = current.next
    return None
~~~

Với chuỗi dạng **đường dẫn vào vòng rồi chu trình**, nút lặp đầu tiên chính là **điểm vào chu trình**.

### Ưu và nhược điểm

- **Dễ hiểu và dễ gỡ lỗi:** có thể giữ tập để kiểm tra số nút khác nhau.
- **Thời gian:** O(u), trong đó u là số nút khác nhau có thể đi tới từ head; với một danh sách n nút thì O(n) theo giả định thao tác tập băm trung bình O(1).
- **Bộ nhớ phụ:** O(u), vì tập giữ thông tin cho mỗi nút đã thăm.
- **Giới hạn:** nếu liên kết prev sai nhưng next vẫn tuyến tính hợp lệ, kiểm tra chỉ dựa trên next chưa chắc phát hiện được lỗi prev.

Khi không muốn dùng bộ nhớ tăng theo n, có thể dùng thuật toán hai con trỏ Floyd.

## 5. Phương pháp 2: Floyd – rùa và thỏ

**Floyd's cycle detection algorithm** dùng hai tham chiếu:

- **slow** (*rùa*): tiến một liên kết next mỗi lượt.
- **fast** (*thỏ*): tiến hai liên kết next mỗi lượt.

Khởi tạo:

~~~python
slow = head
fast = head
~~~

Vòng lặp phát hiện:

~~~python
while fast is not None and fast.next is not None:
    slow = slow.next
    fast = fast.next.next

    if slow is fast:
        # Có chu trình đi tới được từ head.
        break
else:
    # Đã gặp đường kết thúc None: không có chu trình.
    pass
~~~

### 5.1. Tại sao không có vòng thì thuật toán dừng?

Trong danh sách tuyến tính hữu hạn, fast tiến nhanh hơn slow. Cuối cùng **fast is None** hoặc **fast.next is None**, nên không thể đi thêm hai bước và vòng dừng.

Phải kiểm tra cả hai điều kiện trước khi đọc **fast.next.next**; bỏ kiểm tra fast.next có thể gây lỗi khi fast đang đứng ở nút cuối.

### 5.2. Tại sao có vòng thì hai con trỏ sẽ gặp nhau?

Khi slow và fast đều đã đi vào chu trình dài λ, mỗi lượt fast tiến nhiều hơn slow **một bước theo modulo λ**. Khoảng cách tương đối trên chu trình lần lượt thay đổi, nên sau không quá λ lượt khi cả hai đã nằm trong vòng, khoảng cách sẽ bằng 0: **slow is fast**.

Điểm gặp nhau **không nhất thiết là head hoặc điểm vào vòng**. Nó chỉ đủ để kết luận tồn tại chu trình.

### 5.3. Mã phát hiện thuần túy

~~~python
def has_cycle(head):
    slow = head
    fast = head

    while fast is not None and fast.next is not None:
        slow = slow.next
        fast = fast.next.next
        if slow is fast:
            return True

    return False
~~~

**Chi phí:** O(μ + λ) thời gian với chuỗi có vòng, hoặc O(n) cho chuỗi tuyến tính n nút; **O(1) bộ nhớ phụ** vì chỉ giữ một số tham chiếu cố định.

Floyd không thay đổi bất kỳ liên kết nào: đây là phép kiểm tra **không phá hủy cấu trúc**.

## 6. Tìm chính xác điểm vào vòng, μ và λ

Sau khi slow gặp fast trong vòng, có thể tìm **điểm vào** bằng kỹ thuật cổ điển:

1. Giữ một con trỏ ở **head** và con trỏ còn lại ở **điểm gặp**.
2. Cho cả hai tiến **một bước/lượt**.
3. Nút hai con trỏ gặp lại chính là **điểm vào chu trình**.
4. Từ điểm vào, đi theo next cho tới khi quay lại chính nó để đếm **λ**.
5. Số bước con trỏ đi từ head tới điểm vào là **μ**.

### 6.1. Vì sao cách tìm điểm vào đúng?

Gọi t là số bước slow đã đi tại thời điểm gặp fast; fast đã đi 2t bước. Hiệu hai quãng đường **t** là bội số của λ vì hai con trỏ đang ở cùng nút trong vòng.

Từ head đến điểm vào có μ bước, nên vị trí gặp trên vòng cách điểm vào theo chiều next một số bước tương đương **t − μ** theo modulo λ, tức tương đương **−μ** theo modulo λ. Khi một con trỏ bắt đầu từ head và con trỏ kia từ điểm gặp cùng tiến μ bước, cả hai đều đến điểm vào.

Đây là lý do **không được mặc định điểm gặp đầu tiên là điểm vào**. Phải làm thêm pha dịch chuyển hai con trỏ.

### 6.2. Hàm Python tự chứa trả về thông tin vòng

Đoạn mã dưới đây chạy với Python 3.10 trở lên:

~~~python
from __future__ import annotations


class Node:
    def __init__(self, value):
        self.value = value
        self.next: Node | None = None
        self.prev: Node | None = None


def floyd_cycle_info(head: Node | None):
    """Trả (entry, mu, cycle_length).

    Không có vòng: (None, None, 0).
    Có vòng: entry là chính đối tượng nút đầu tiên thuộc chu trình.
    Không sửa liên kết.
    """
    slow = head
    fast = head

    while fast is not None and fast.next is not None:
        slow = slow.next
        fast = fast.next.next

        if slow is fast:
            break
    else:
        return None, None, 0

    # Tìm điểm vào: hai con trỏ đều đi một bước/lượt.
    from_head = head
    from_meeting = slow
    mu = 0

    while from_head is not from_meeting:
        from_head = from_head.next
        from_meeting = from_meeting.next
        mu += 1

    entry = from_head

    # Đếm số nút trong một vòng đầy đủ.
    cycle_length = 1
    cursor = entry.next
    while cursor is not entry:
        cycle_length += 1
        cursor = cursor.next

    return entry, mu, cycle_length


# Trường hợp không có vòng.
a, b, c = Node("A"), Node("B"), Node("C")
a.next = b
b.next = c

assert floyd_cycle_info(None) == (None, None, 0)
assert floyd_cycle_info(a) == (None, None, 0)

# Vòng đơn bắt đầu ngay tại head.
c.next = a
entry, mu, period = floyd_cycle_info(a)
assert entry is a
assert mu == 0
assert period == 3

# Vòng lỗi: head A dẫn tới chu trình B -> C -> B.
c.next = b
entry, mu, period = floyd_cycle_info(a)
assert entry is b
assert mu == 1
assert period == 2

# Một nút tự trỏ: chu trình độ dài một.
single = Node("X")
single.next = single
entry, mu, period = floyd_cycle_info(single)
assert entry is single and mu == 0 and period == 1
~~~

Các ví dụ trên dùng **is** để so sánh chính đối tượng nút. Hai nút khác nhau cùng có value = "A" không khiến Floyd báo có chu trình.

### 6.3. Chi phí của việc tính μ và λ

Sau khi gặp nhau, pha tìm điểm vào đi tối đa μ bước; pha đếm một vòng đi λ bước. Toàn bộ vẫn mất **O(μ + λ)** thời gian và **O(1)** bộ nhớ phụ.

Nếu không có vòng, hàm trả **(None, None, 0)**, trong đó μ không áp dụng. Không nên nhầm 0 ở trường độ dài vòng với “chu trình độ dài 0”.

## 7. Hợp đồng cấu trúc quyết định chu trình có hợp lệ không

**Tính hợp lệ không thể suy ra chỉ từ hình dạng next nếu chưa biết loại danh sách dự kiến.** Xét chuỗi A → B → C → A:

- Với **danh sách đơn tuyến tính**, đây là lỗi vì tail.next phải là None.
- Với **danh sách vòng đơn không sentinel**, đây **có thể hợp lệ**, nếu head = A, tail = C, size = 3 và không có nút ngoài chu trình được tính là phần tử.
- Với **danh sách đôi vòng**, chỉ next đúng vẫn chưa đủ: các liên kết **prev** cũng phải đối ứng và head.prev phải là tail.
- Với **danh sách đôi vòng có một sentinel s**, chu trình có cả s; quy tắc dừng duyệt phải loại s khỏi dữ liệu.

Bảng đối chiếu:

| Kiểu danh sách | Khi không rỗng | Điều kiện kết thúc duyệt đúng | Điều kiện nhận dạng hợp lệ |
| --- | --- | --- | --- |
| Đơn tuyến tính | tail.next is None | Gặp None | Không có chu trình next; tail và size khớp |
| Đôi tuyến tính | head.prev is None, tail.next is None | Gặp None | Không có vòng next, liên kết prev/next đối ứng |
| Vòng đơn, không sentinel | tail.next is head | Quay về head hoặc đủ size bước | Điểm vào vòng = head, λ = size, tail đúng |
| Vòng đôi, không sentinel | tail.next is head, head.prev is tail | Quay về head/tail | Vòng next đúng và tất cả prev/next đối ứng |
| Vòng đôi có sentinel s | s.next/s.prev tạo vòng qua nút dữ liệu | Gặp chính s | Duyệt từ s.next đủ size nút dữ liệu rồi trở về s, liên kết đối ứng |

**Quan trọng:** Floyd trả về sự tồn tại chu trình trong các cạnh next **đi tới được từ head**. Nó không kiểm tra được các nút không thể đi tới từ head, không đảm bảo tail đúng, không phát hiện được mọi lỗi ở prev và không biết liệu một nút nào đó là sentinel theo hợp đồng của ứng dụng.

## 8. Kiểm tra danh sách đơn tuyến tính và vòng đơn

Để kiểm tra cấu trúc một cách có hệ thống, cần kết hợp **Floyd** với các bất biến **head/tail/size**.

### 8.1. Danh sách đơn tuyến tính

Cần xác nhận:

1. Nếu size = 0: head và tail đều là None.
2. Nếu size > 0: head và tail khác None.
3. Floyd **không phát hiện chu trình** từ head.
4. Duyệt từ head tới None phải gặp đúng size nút.
5. Nút cuối thực tế phải là tail và **tail.next is None**.

Vì Floyd loại trừ chu trình trước, lượt đếm tới None không có nguy cơ lặp vô hạn do một vòng next hợp lệ với đồ thị đầu vào.

### 8.2. Danh sách vòng đơn không sentinel

Cần xác nhận:

1. Nếu size = 0: head = tail = None.
2. Nếu size > 0: head và tail khác None.
3. Floyd tìm được chu trình, **entry is head**, **μ = 0**, **λ = size**.
4. Đi từ head đúng size bước phải quay về head.
5. Nút ngay trước khi quay về head phải chính là tail; **tail.next is head**.

Đặc biệt, **tail.next is head không đủ** nếu tail không thực sự nằm trên đường duyệt từ head. Bước kiểm tra nút cuối loại bỏ trường hợp tail trỏ đến một nút riêng lẻ không thuộc vòng.

### 8.3. Mã kiểm tra cả hai kiểu

Mã dưới đây có thể dùng trực tiếp cùng lớp Node và hàm floyd_cycle_info ở mục 6:

~~~python
def validate_singly(head, tail, size: int, *, circular: bool) -> None:
    """Ném ValueError nếu cấu trúc sai hợp đồng."""
    if not isinstance(size, int) or size < 0:
        raise ValueError("size phải là số nguyên không âm")

    if size == 0:
        if head is not None or tail is not None:
            raise ValueError("Rỗng phải có head = tail = None")
        return

    if head is None or tail is None:
        raise ValueError("Danh sách không rỗng cần head và tail")

    entry, mu, length = floyd_cycle_info(head)

    if not circular:
        if entry is not None:
            raise ValueError("Danh sách tuyến tính có chu trình")

        count = 0
        current = head
        last = None

        while current is not None:
            last = current
            count += 1
            current = current.next

        if count != size:
            raise ValueError("size không khớp số nút")
        if last is not tail or tail.next is not None:
            raise ValueError("tail không phải nút cuối")
        return

    # Trường hợp khai báo danh sách vòng đơn.
    if entry is not head or mu != 0:
        raise ValueError("Vòng phải bắt đầu tại head")
    if length != size:
        raise ValueError("Độ dài vòng khác size")

    current = head
    last = None
    for _ in range(size):
        last = current
        current = current.next

    if current is not head:
        raise ValueError("Không quay lại head đúng sau size bước")
    if last is not tail or tail.next is not head:
        raise ValueError("tail hoặc liên kết khép vòng không đúng")


# Đúng kiểu tuyến tính.
a, b, c = Node("A"), Node("B"), Node("C")
a.next, b.next = b, c
validate_singly(a, c, 3, circular=False)

# Cũng chuỗi ấy nhưng metadata size sai.
try:
    validate_singly(a, c, 4, circular=False)
except ValueError:
    pass
else:
    raise AssertionError("Phải phát hiện size sai")

# Chuyển thành vòng đơn hợp lệ.
c.next = a
validate_singly(a, c, 3, circular=True)

try:
    validate_singly(a, c, 3, circular=False)
except ValueError:
    pass
else:
    raise AssertionError("Vòng không phải danh sách tuyến tính")

# Một vòng sai: A -> B -> C -> B, không quay về A.
c.next = b
try:
    validate_singly(a, c, 3, circular=True)
except ValueError:
    pass
else:
    raise AssertionError("Phải phát hiện chu trình không bắt đầu ở head")

# Vòng một nút là hợp lệ.
single = Node("X")
single.next = single
validate_singly(single, single, 1, circular=True)

# Danh sách rỗng hợp lệ cho cả hai quy ước.
validate_singly(None, None, 0, circular=False)
validate_singly(None, None, 0, circular=True)
~~~

**Độ phức tạp:** Floyd và lượt đếm/nối xác minh mỗi nút một số lần hữu hạn. Với u nút khác nhau đi tới được từ head, thời gian là O(u), bộ nhớ phụ **O(1)**. Nếu khai báo size rất lớn và liên kết không hợp lệ, hàm vẫn dựa vào Floyd để phân biệt vòng đúng với các dạng không đúng trước khi duyệt theo size.

**Giới hạn cần hiểu:** Hàm chỉ kiểm tra các nút đi tới được từ head và các metadata được truyền vào. Một nút bị tách rời, không được tham chiếu từ head, không thể tự nhiên được tìm ra chỉ bằng cách duyệt danh sách.

## 9. Danh sách đôi: kiểm tra cả prev, không chỉ next

Danh sách liên kết đôi lưu thêm **prev**. Một chuỗi có next hoàn toàn hợp lệ vẫn có thể sai ở chiều ngược.

~~~text
Chiều xuôi: A ──next──► B ──next──► C

Yêu cầu:     B.prev is A
             C.prev is B

Lỗi:         C.prev is A
~~~

Trong ví dụ lỗi, Floyd theo next sẽ không phát hiện chu trình và kết luận đường đi theo next không có vòng. Tuy nhiên, **C.prev không trỏ tới B**, vi phạm bất biến danh sách đôi.

### 9.1. Danh sách đôi tuyến tính

Sau khi xác nhận cấu trúc next tuyến tính và head/tail/size đúng, cần duyệt để kiểm tra:

- **head.prev is None**.
- Với từng nút current, **current.prev is previous**.
- Nếu previous tồn tại, **previous.next is current**.
- **tail.next is None**, và duyệt ngược qua prev phải trở lại head.

### 9.2. Danh sách đôi vòng không sentinel

Ngoài điều kiện vòng next hợp lệ còn phải có:

- **head.prev is tail** và **tail.next is head**.
- Với mọi nút current, **current.next.prev is current**.
- Với mọi nút current, **current.prev.next is current**.
- Đi ngược theo prev đúng size bước từ tail phải quay lại tail.

### 9.3. Cài đặt kiểm tra chiều ngược

Cùng lớp Node, floyd_cycle_info và validate_singly ở các mục trước:

~~~python
def validate_doubly_linear(head, tail, size: int) -> None:
    validate_singly(head, tail, size, circular=False)

    if size == 0:
        return

    if head.prev is not None:
        raise ValueError("head.prev phải là None")

    previous = None
    current = head

    while current is not None:
        if current.prev is not previous:
            raise ValueError("Liên kết prev không đối ứng")
        if previous is not None and previous.next is not current:
            raise ValueError("Liên kết next không đối ứng")

        previous = current
        current = current.next

    if previous is not tail:
        raise ValueError("tail sai")


def validate_doubly_circular(head, tail, size: int) -> None:
    validate_singly(head, tail, size, circular=True)

    if size == 0:
        return

    if head.prev is not tail:
        raise ValueError("head.prev phải trỏ tới tail")

    current = head
    previous = tail

    for _ in range(size):
        if current.prev is not previous:
            raise ValueError("prev không đối ứng")
        following = current.next
        if following.prev is not current:
            raise ValueError("next.prev không đối ứng")

        previous = current
        current = following

    if current is not head or previous is not tail:
        raise ValueError("Vòng hai chiều sai")


# Tuyến tính đôi đúng.
a, b, c = Node(1), Node(2), Node(3)
a.next, b.prev = b, a
b.next, c.prev = c, b
validate_doubly_linear(a, c, 3)

# Cố ý phá prev, dù next vẫn đúng.
c.prev = a
try:
    validate_doubly_linear(a, c, 3)
except ValueError:
    pass
else:
    raise AssertionError("Phải phát hiện prev sai")
c.prev = b

# Khép chu trình hai chiều.
c.next = a
a.prev = c
validate_doubly_circular(a, c, 3)

# Phá liên kết ở đầu vòng.
a.prev = b
try:
    validate_doubly_circular(a, c, 3)
except ValueError:
    pass
else:
    raise AssertionError("Phải phát hiện head.prev sai")
~~~

Trong mã này, kiểm tra chuỗi next và sau đó kiểm tra prev có thời gian **O(n)**, bộ nhớ phụ **O(1)**. Nếu ứng dụng muốn báo chi tiết vị trí sai, có thể trả thêm thông tin nút và loại bất biến bị vi phạm.

## 10. Trường hợp có nút canh gác: sentinel cũng thuộc chu trình vật lý

Một danh sách đôi vòng đôi khi dùng **một nút canh gác s** (*sentinel*) thay vì head/tail dữ liệu độc lập.

Rỗng:

~~~text
s.next is s
s.prev is s
size = 0
~~~

Có hai nút dữ liệu A, B:

~~~text
       ┌───────────────────┐
       ▼                   │
       s ⇄ A ⇄ B ──────────┘
       ▲               │
       └───────────────┘
~~~

Các liên kết phải đúng:

~~~text
s.next is A
A.prev is s
B.next is s
s.prev is B
size = 2  (không tính sentinel)
~~~

### 10.1. Vì sao Floyd chưa đủ?

Nếu chạy Floyd từ **s.next** trên danh sách không rỗng, Floyd có thể phát hiện một chu trình bao gồm cả **sentinel**. Độ dài vòng **vật lý** là **size + 1**, bởi s không phải nút dữ liệu. Do đó, không được áp dụng trực tiếp bất biến **λ = size** của danh sách vòng không sentinel.

Thay vào đó, quy ước duyệt là:

~~~python
current = s.next
while current is not s:
    process(current.value)
    current = current.next
~~~

Với cấu trúc hợp lệ, s là mốc dừng. Nhưng nếu một liên kết vô tình tạo vòng con trước khi quay tới s, vòng lặp trên vẫn có thể **không kết thúc**. Trong mã kiểm chứng, hãy giới hạn số bước bằng size và xác nhận cuối cùng quay về s.

### 10.2. Kiểm chứng sentinel vòng an toàn với size

~~~python
def validate_sentinel_ring(s, size: int) -> None:
    """s là sentinel của danh sách đôi vòng, size đếm nút dữ liệu."""
    if s is None or not isinstance(size, int) or size < 0:
        raise ValueError("Sentinel hoặc size không hợp lệ")
    if s.next is None or s.prev is None:
        raise ValueError("Sentinel mất liên kết")

    current = s.next
    previous = s

    for _ in range(size):
        if current is None or current is s:
            raise ValueError("Gặp ranh giới quá sớm")
        if current.prev is not previous:
            raise ValueError("prev không đối ứng")
        if current.next is None:
            raise ValueError("Có next bằng None trong vòng")
        if current.next.prev is not current:
            raise ValueError("next.prev không đối ứng")

        previous = current
        current = current.next

    if current is not s:
        raise ValueError("Không trở về sentinel đúng lúc")
    if s.prev is not previous:
        raise ValueError("s.prev không trỏ tới nút cuối")
    if s.prev.next is not s:
        raise ValueError("Nút cuối không trỏ về sentinel")
    if s.next.prev is not s:
        raise ValueError("Nút đầu không trỏ ngược về sentinel")


# Sentinel của danh sách rỗng.
s = Node(None)
s.next = s
s.prev = s
validate_sentinel_ring(s, 0)

# Hai nút dữ liệu, một nút chứa None cũng hoàn toàn hợp lệ.
a, b = Node(None), Node(7)
s.next, s.prev = a, b
a.prev, a.next = s, b
b.prev, b.next = a, s
validate_sentinel_ring(s, 2)

# Tạo lỗi: b trỏ ngược tới s thay vì a.
b.prev = s
try:
    validate_sentinel_ring(s, 2)
except ValueError:
    pass
else:
    raise AssertionError("Phải phát hiện liên kết ngược sai")
~~~

Hàm chỉ dùng một số biến tạm nên có O(1) bộ nhớ phụ, chạy **O(size)** bước đối với size đã khai báo. Bước kiểm tra sau vòng xác nhận đã tới đúng sentinel; nếu cấu trúc bị lỗi và size vẫn hữu hạn, vòng kiểm chứng không phải chạy vô hạn.

**Không xác định sentinel bằng value = None:** nút dữ liệu thật cũng có thể lưu None. Điểm dừng là **danh tính nút s**.

## 11. Vì sao một số lỗi không được phát hiện chỉ bằng head?

Giả sử danh sách báo size = 3 nhưng từ head chỉ đi tới hai nút A → B → None, còn một nút C đã bị tách rời:

~~~text
head → A → B → None

C → None      (không còn đường đi từ head tới C)
~~~

Duyệt từ head không thể tự khám phá C, vì không có liên kết nào dẫn tới nó. Nếu size vẫn là 3, kiểm chứng sẽ phát hiện **size sai**, nhưng không thể biết chính xác C ở đâu nếu không có một cơ chế theo dõi nút khác.

Một trường hợp khác, nếu size đã bị cập nhật sai xuống 2 cùng lúc với việc đánh mất C, cấu trúc hiện tại A → B → None có thể **hợp lệ theo metadata mới**; không thể dựa vào head mà khẳng định từng tồn tại một nút C trong quá khứ.

Đây là khác biệt giữa:

- **Kiểm chứng trạng thái hiện tại:** các nút đi tới được từ head có thỏa bất biến không?
- **Kiểm chứng lịch sử thao tác hoặc không mất dữ liệu:** những nút từng có đã đi đâu?

Vấn đề thứ hai cần **nhật ký thao tác, danh sách sở hữu, registry, kiểm thử đặc tả hoặc hợp đồng quản lý bộ nhớ**; Floyd không giải quyết được.

### 11.1. Sai tail mà không có vòng

~~~text
head → A → B → C → None
tail ───────► B
~~~

Floyd không thấy chu trình, nhưng **tail không phải nút cuối**. Vì vậy cần kiểm tra nút cuối thực tế là C và **tail is C**.

### 11.2. Vòng đúng nhưng size sai

~~~text
A → B → C → A
size khai báo = 4
~~~

Floyd thấy vòng, entry = head và λ = 3; nhưng **λ != size** nên trạng thái sai.

### 11.3. Next đúng nhưng prev sai

Với danh sách đôi tuyến tính, có thể A.next = B, B.next = C và C.next = None, nhưng C.prev lại trỏ về A. Floyd không phát hiện vòng next, trong khi chiều ngược không đối ứng. Cần kiểm tra prev.

## 12. Độ phức tạp của các chiến lược kiểm tra

Ký hiệu:

- **n**: số nút dữ liệu trong một danh sách hợp lệ.
- **μ**: độ dài đoạn trước vòng nếu có vòng.
- **λ**: độ dài vòng nếu có vòng.
- **u = μ + λ**: số nút khác nhau đi tới được từ head khi có vòng.

| Chiến lược | Thời gian | Bộ nhớ phụ | Trả lời được gì? |
| --- | --- | --- | --- |
| Duyệt tuyến tính tới None (chỉ khi biết không có chu trình) | Θ(n) | O(1) | Thứ tự, nút cuối, số nút |
| Tập visited, phát hiện nút lặp | O(u) trung bình | O(u) | Có vòng, điểm vào, các nút đã gặp |
| Floyd hai con trỏ | O(u) | **O(1)** | Có vòng hay không |
| Floyd + điểm vào + đếm λ | O(u) | **O(1)** | Điểm vào, μ, λ |
| Kiểm tra tuyến tính head/tail/size sau Floyd | O(n) | **O(1)** | Chuỗi next và metadata có hợp lệ? |
| Kiểm tra vòng đơn không sentinel | O(n) | **O(1)** | Vòng bắt đầu tại head, đúng size/tail? |
| Kiểm tra vòng đôi prev/next | O(n) | **O(1)** | Liên kết hai chiều có đối ứng? |
| Kiểm tra sentinel vòng bằng size bước | O(n) | **O(1)** | Đi hết dữ liệu rồi quay về sentinel? |
| Kiểm tra qua tập id các nút | O(n) trung bình | O(n) | Phát hiện nút lặp và hỗ trợ đối chiếu tập nút |

**Lưu ý về độ phức tạp Floyd:** Nếu không có vòng và có n nút, thời gian O(n). Nếu có vòng từ head với u = μ + λ nút khác nhau, thời gian O(μ + λ). Trong mọi trường hợp thuật toán không dùng bộ nhớ tăng theo số nút.

**Tập visited:** chi phí O(n) thời gian là **trung bình** theo mô hình bảng băm; việc chọn cấu trúc tập và hàm băm ảnh hưởng các tình huống cực đoan.

**Bộ nhớ giữ nút:** Nếu muốn giữ lại đối tượng từng thăm để phục vụ gỡ lỗi chi tiết, có thể lưu chúng trong tập/danh sách O(n). Nếu mục tiêu là kiểm tra tối thiểu với O(1) bộ nhớ, Floyd thích hợp hơn.

## 13. Không tự ý “sửa vòng” khi chưa biết hợp đồng

Một cách xử lý thường được đề xuất là: “Nếu phát hiện vòng, tìm nút cuối của chu trình rồi gán next = None.” Cách này **có thể phá hủy cấu trúc hợp lệ**.

### 13.1. Khi nào cắt vòng là sai?

Với danh sách vòng đơn hợp lệ A → B → C → A, cắt **C.next = None** sẽ biến nó thành danh sách tuyến tính. Nếu các thao tác khác vẫn coi cấu trúc là vòng, chúng sẽ lỗi hoặc đi tới None ngoài dự kiến.

Với danh sách vòng đôi, chỉ cắt next mà không sửa prev còn khiến các bất biến hai chiều mất đối ứng.

Vì vậy, trước khi sửa phải xác định:

1. Cấu trúc **được thiết kế là tuyến tính hay vòng**?
2. Có **sentinel** không?
3. **Head/tail/size** phải tuân theo quy tắc nào?
4. Thao tác có đang chạy đồng thời với duyệt/chèn/xóa khác không?
5. Có tham chiếu hoặc thành phần nào phụ thuộc vào danh tính của những nút hiện tại không?

### 13.2. Nếu một danh sách tuyến tính bị tạo vòng do lỗi

Có thể phát hiện entry bằng Floyd, tìm nút trước entry trong chu trình, rồi cắt liên kết trỏ ngược về entry. Tuy nhiên, đây chỉ là một chiến lược **cứu hộ cấu trúc**, không chứng minh các phần tử còn lại và metadata đã đúng.

Nếu chuỗi có dạng A → B → C → B, cắt C.next = None sẽ cho A → B → C → None. Nhưng **tail**, **size** và các cấu trúc tham chiếu tới nó vẫn cần đối chiếu.

Tùy tình huống, điều đúng hơn có thể là **báo lỗi**, **khôi phục từ bản sao an toàn** hoặc **tái tạo danh sách từ dữ liệu nguồn**, chứ không sửa một liên kết bất kỳ.

### 13.3. Không làm thay đổi cấu trúc khi chỉ kiểm tra

Các hàm phát hiện/kiểm chứng trong bài **không sửa liên kết**, tránh gây tác dụng phụ khi đang chẩn đoán. Đây cũng là lý do nên tách API **validate** và API **repair**, thay vì lén sửa cấu trúc trong thao tác duyệt.

## 14. Bẫy khi duyệt và khi kiểm thử

| Sai sót | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| Duyệt danh sách vòng bằng while current is not None | Không kết thúc khi vòng hợp lệ. | Dừng khi quay về start hoặc sau size bước. |
| Dừng khi current.value == head.value | Dừng sớm nếu nhiều nút cùng giá trị. | So sánh **current is head**. |
| Chỉ kiểm tra Floyd rồi tuyên bố danh sách vòng hợp lệ | Bỏ qua chu trình bắt đầu sau head, tail sai, size sai. | Kiểm tra entry, μ, λ, tail, size. |
| Chỉ kiểm tra tail.next is head | Không đảm bảo tail có thể đi tới được từ head. | Xác nhận nút cuối khi duyệt size bước là tail. |
| Chỉ kiểm tra không có vòng trong danh sách tuyến tính | Có thể bỏ qua tail hoặc size sai. | Đếm nút và đối chiếu tail thực tế. |
| Danh sách đôi chỉ xác minh next | Không phát hiện prev trỏ sai. | Kiểm tra liên kết đối ứng hai chiều. |
| Không kiểm tra fast.next trước khi đọc fast.next.next | Có thể truy cập thuộc tính của None. | Dùng điều kiện fast != None và fast.next != None. |
| Dùng == thay vì is để phát hiện hai con trỏ gặp nhau | Có thể coi hai nút cùng giá trị là cùng nút. | So sánh danh tính đối tượng. |
| Coi điểm gặp đầu tiên của Floyd là điểm vào | Trả sai entry nếu vòng có đoạn dẫn. | Đưa một con trỏ về head và cùng tiến một bước. |
| Đếm size của danh sách vòng bằng while current != None | Vòng lặp vô hạn. | Đếm một vòng tới start/sentinel với bảo vệ hợp lệ. |
| Đếm sentinel như nút dữ liệu | size bị lớn hơn thực tế một đơn vị. | Dừng trước sentinel; không tính nó vào size. |
| Áp dụng λ = size cho vòng có sentinel | Lệch một nút do chu trình vật lý có sentinel. | Kiểm tra vòng với điểm dừng là sentinel và size nút dữ liệu. |
| Cắt mọi chu trình được phát hiện | Có thể phá danh sách vòng hợp lệ. | Biết loại cấu trúc trước khi sửa. |
| Chỉ thử trường hợp ba nút bình thường | Bỏ sót lỗi 0/1 nút, vòng tự trỏ, tail sai. | Thử đủ rỗng, một nút, hai nút, lollipop, vòng đúng. |
| Tin rằng Floyd tìm được nút tách rời không thể đi tới từ head | Không thể tìm thông tin ngoài đường liên kết đang duyệt. | Dùng thêm registry hoặc kiểm thử thao tác nếu cần. |
| Chạy kiểm tra đồng thời với luồng khác đang sửa liên kết | Kết quả kiểm tra không ổn định, có thể quan sát trạng thái trung gian. | Đồng bộ hoặc kiểm tra trên snapshot. |

### Bộ tình huống tối thiểu nên thử

~~~text
(1) Rỗng: head = None, tail = None, size = 0

(2) Tuyến tính một nút: X → None

(3) Vòng một nút: X ──► X

(4) Tuyến tính nhiều nút: A → B → C → None

(5) Vòng đơn hợp lệ: A → B → C → A

(6) Vòng sai kiểu lollipop: A → B → C → B

(7) Vòng đúng nhưng tail trỏ nhầm B thay vì C

(8) Vòng đúng nhưng size sai

(9) Danh sách đôi next đúng, prev sai

(10) Danh sách đôi có sentinel tự trỏ khi rỗng
~~~

Khi kiểm thử một hàm duyệt thông thường, nên có **giới hạn số bước** hoặc thử trên dữ liệu đã qua kiểm tra để tránh tác vụ treo do một chu trình lỗi.

## 15. Ứng dụng thực tế

### 15.1. Hàng đợi và danh sách tác vụ

Một hàng đợi xây dựng trên danh sách đơn tuyến tính phải có tail.next = None. Nếu một lỗi gán tail.next về một nút ở giữa, thao tác duyệt để tính số tác vụ có thể không dừng. Bước kiểm tra trước khi xử lý dữ liệu không đáng tin cậy có thể dùng Floyd và đối chiếu head/tail/size.

### 15.2. Xếp lịch luân phiên

Danh sách vòng đơn có thể biểu diễn các tác vụ xử lý theo chu kỳ A → B → C → A. Ở đây, **phát hiện chu trình là kết quả mong đợi**. Phép kiểm tra đúng không phải “không có vòng”, mà là **vòng gồm đúng các tác vụ, bắt đầu tại head, có độ dài size và tail nối về head**.

### 15.3. Bộ đệm LRU và danh sách đôi

Một số cấu trúc LRU dùng danh sách đôi có sentinel. Nếu **next** đúng nhưng **prev** sai, thao tác gỡ nút hoặc chuyển nút lên đầu có thể hỏng dù lượt duyệt xuôi vẫn in đúng các khóa. Vì vậy, trong kiểm thử nên đối chiếu các bất biến **next.prev** và **prev.next**, không chỉ chạy Floyd.

### 15.4. Kiểm tra dữ liệu sau thao tác nhiều bước

Những phép chèn/xóa, đảo danh sách hoặc chuyển đoạn nút giữa các danh sách có thể khiến head, tail, size và liên kết biến đổi cùng lúc. Hàm validate độc lập rất hữu ích trong unit test để phát hiện sai lệch ngay sau thao tác. Trong môi trường hiệu năng cao, không nên mặc định chạy validate O(n) sau mỗi thao tác O(1) nếu không có yêu cầu chẩn đoán tương ứng.

## 16. Bài tập vận dụng có đáp án

**Bài 1 — Nhận diện chu trình.** Cho A → B → C → None. Floyd trả về điều gì?

*Đáp án:* Không có chu trình. fast cuối cùng gặp None hoặc nút có fast.next = None; hàm has_cycle trả False.

**Bài 2 — Vòng hợp lệ hay lỗi?** Cho A → B → C → A, head = A, tail = C, size = 3. Nếu cấu trúc được khai báo là danh sách vòng đơn, chuỗi có hợp lệ không? Nếu là tuyến tính?

*Đáp án:* Hợp lệ với **danh sách vòng đơn** theo các bất biến đã nêu. Không hợp lệ với **danh sách tuyến tính**, vì tail.next không phải None.

**Bài 3 — Vòng có đoạn dẫn.** Cho A → B → C → D → B, head = A. Điểm vào, μ và λ bằng bao nhiêu?

*Đáp án:* **Entry = B**, μ = 1, λ = 3 (B → C → D → B).

**Bài 4 — Vòng tự trỏ.** Danh sách có một nút X với X.next is X. Có phải lỗi không?

*Đáp án:* **Tùy hợp đồng.** Đây là vòng đơn một nút hợp lệ nếu cấu trúc là vòng không sentinel với head = tail = X, size = 1. Đây là lỗi nếu cấu trúc yêu cầu tuyến tính.

**Bài 5 — Vì sao dùng is?** Hai nút P và Q đều chứa giá trị 7 nhưng P.next = Q, Q.next = None. Có chu trình không?

*Đáp án:* Không. Hai nút có giá trị bằng nhau vẫn là hai đối tượng khác nhau. Phải phát hiện **cùng nút**, không phải cùng giá trị.

**Bài 6 — Điều kiện bảo vệ fast.** Tại sao vòng Floyd kiểm tra cả fast và fast.next trước khi gán fast = fast.next.next?

*Đáp án:* Để không đọc thuộc tính next của None trên chuỗi tuyến tính, đặc biệt khi fast đang là nút cuối.

**Bài 7 — Điểm gặp khác điểm vào.** Trong Floyd, slow và fast gặp ở một nút thuộc vòng. Có thể trả ngay nút ấy là entry không?

*Đáp án:* Không đảm bảo. Cần đưa một con trỏ về head và cho cả hai tiến một bước tới khi gặp lại; nút gặp lại mới là entry.

**Bài 8 — Tail sai.** Cho A → B → C → None, head = A, tail = B, size = 3. Floyd có báo chu trình không? Danh sách có hợp lệ không?

*Đáp án:* Floyd không báo chu trình, nhưng danh sách **không hợp lệ** vì nút cuối thực tế là C, không phải B; B.next cũng khác None.

**Bài 9 — Size sai.** Danh sách vòng A → B → C → A có entry = A và λ = 3 nhưng size lưu là 4. Có chấp nhận không?

*Đáp án:* Không. Vòng không có đủ 4 nút dữ liệu và vi phạm λ = size của mô hình không sentinel.

**Bài 10 — Chu trình không qua head.** A → B → C → B, head = A. Vì sao không thể coi đây là vòng đơn hợp lệ với head A?

*Đáp án:* Đi theo next từ A sẽ không bao giờ quay về A; entry = B, μ = 1, khác điều kiện entry is head.

**Bài 11 — Prev sai.** Danh sách đôi A ⇄ B ⇄ C có next đúng A → B → C → None, nhưng C.prev = A. Floyd có phát hiện lỗi không?

*Đáp án:* Không, vì Floyd chỉ theo next. Cần kiểm tra C.prev is B và liên kết đối ứng giữa B/C.

**Bài 12 — Sentinel.** Trong danh sách đôi vòng với sentinel s và hai nút dữ liệu A, B, chu trình vật lý có bao nhiêu nút? Khi duyệt dữ liệu thì dừng ở đâu?

*Đáp án:* Chu trình vật lý gồm **3 nút** (s, A, B). Size dữ liệu = 2; duyệt bắt đầu ở s.next và dừng khi gặp lại **chính s**.

**Bài 13 — Phân tích bộ nhớ.** Vì sao Floyd chỉ dùng O(1) bộ nhớ trong khi tập visited có thể dùng O(n)?

*Đáp án:* Floyd chỉ giữ một vài con trỏ chậm/nhanh và con trỏ đếm; tập visited giữ thông tin cho từng nút đã đi qua.

**Bài 14 — Chỉ tail.next là đủ?** Một nút tail tách rời trỏ về head, còn chuỗi từ head tạo vòng riêng không đi qua tail. Kiểm tra tail.next is head cho kết luận gì?

*Đáp án:* Điều kiện ấy đúng nhưng **không đủ**. Cần duyệt từ head đủ size bước, xác nhận nút cuối trước khi quay về head chính là tail.

**Bài 15 — Sửa vòng.** Hệ thống phát hiện chu trình A → B → C → A. Có nên tự động đổi C.next = None không?

*Đáp án:* Chỉ khi biết chắc hợp đồng cần danh sách tuyến tính và hiểu đầy đủ hậu quả. Nếu cấu trúc là danh sách vòng, thao tác đó phá bất biến hợp lệ. Nên tách kiểm tra khỏi sửa chữa.

**Bài 16 — Nút thất lạc.** Trong một danh sách tuyến tính, chuỗi từ head hợp lệ và size đã được sửa để khớp, nhưng một nút cũ đã bị tách rời. Floyd có thể phát hiện nút cũ đó không?

*Đáp án:* Không. Floyd chỉ duyệt nút đi tới được từ head; muốn biết nút cũ đã bị mất cần thông tin sở hữu hoặc lịch sử riêng.

**Ghi nhớ:** Thuật toán Floyd và tập visited trả lời câu hỏi **có chu trình theo next hay không**. Để kết luận cấu trúc **hợp lệ**, phải biết đó là danh sách tuyến tính, vòng đơn, vòng đôi hay có sentinel, rồi kiểm tra **head/tail/size**, điểm vào **μ**, độ dài vòng **λ**, các liên kết **prev/next** và điểm dừng duyệt. **Chu trình là lỗi của danh sách tuyến tính nhưng có thể là bất biến bắt buộc của danh sách vòng**; không bao giờ tự ý cắt vòng khi chưa xác định hợp đồng cấu trúc.

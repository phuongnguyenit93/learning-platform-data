# Danh sách bất biến và dùng chung phần đuôi

Một ứng dụng học tập ghi lại các bước học của người dùng. Sau khi lưu phiên bản danh sách công việc `[10, 20, 30]`, ứng dụng muốn thêm một công việc ưu tiên `5` lên đầu, đồng thời vẫn cho phép xem danh sách cũ để hoàn tác hoặc đối chiếu lịch sử. Nếu sử dụng một list mutable và chỉ giữ hai biến trỏ đến cùng list, thao tác thay đổi có thể làm “lịch sử” cũng đổi theo.

**Danh sách liên kết bất biến** (*immutable linked list*) giải quyết bài toán theo một hướng rất tự nhiên: thay vì sửa nút đang có, ta **tạo một nút đầu mới** và cho nó trỏ tới **toàn bộ phần đuôi cũ**. Phiên bản mới và phiên bản cũ dùng chung phần đuôi ấy; vì các nút cũ không bị sửa, cả hai phiên bản vẫn đúng.

```text
Bản gốc:     v0 ──► [10] ──► [20] ──► [30] ──► None

Thêm 5:     v1 ──► [ 5] ──┐
                          ▼
                         [10] ──► [20] ──► [30] ──► None
                          ▲
                         v0

Chỉ tạo 1 nút mới; phần đuôi [10,20,30] được dùng chung.
```

Bài thuộc chương **Bất biến và phiên bản**, trong module cấu trúc dữ liệu. Ta sẽ xây danh sách liên kết đơn bất biến, giải thích **structural sharing** ở phần đuôi, cài đặt `cons`/`head`/`tail`/`pop`, cập nhật giữa danh sách bằng **sao chép tiền tố**, phân tích thời gian–bộ nhớ, kiểm thử số nút vật lý được chia sẻ và xử lý các trường hợp như phần tử mutable, phiên bản phân nhánh, garbage collection và truy cập đồng thời.

## 1. “Danh sách bất biến” nghĩa là gì?

Một cấu trúc dữ liệu *immutable* không cung cấp thao tác sửa tại chỗ những thành phần thuộc trạng thái của chính đối tượng sau khi tạo, theo hợp đồng của nó.

Với danh sách liên kết đơn, trạng thái cấu trúc gồm:

- **Giá trị `value`** ở từng nút.
- **Tham chiếu `next`** đến nút kế tiếp.
- **Tham chiếu `head`** mà một phiên bản dùng để bắt đầu danh sách.

Mỗi nút có dạng:

```text
┌──────────────┐
│ value │ next │ ──► nút tiếp theo
└──────────────┘
```

Với nút bất biến, sau khi tạo:

- Không gán lại `node.value`.
- Không gán lại `node.next`.
- Muốn danh sách có đầu khác hoặc phần tử khác, tạo **những nút mới cần thiết** và trả về **head mới**.

**Không đồng nghĩa với cấm tạo phiên bản mới:** “bất biến” không cản các thao tác thêm/xóa/chỉnh sửa *về mặt logic*. Nó chỉ yêu cầu thao tác ấy **không làm biến đổi các nút thuộc phiên bản cũ**.

### Phân biệt với invariant

Trong môn cấu trúc dữ liệu, *invariant* là **điều kiện phải luôn đúng**, ví dụ danh sách liên kết hợp lệ không có chu trình ngoài ý muốn. *Immutability* là **quy tắc không sửa trạng thái tại chỗ**. Một cấu trúc mutable cũng có thể giữ invariant đúng qua mỗi thao tác; một nút frozen không tự làm toàn bộ đồ thị liên kết hợp lệ nếu khởi tạo sai.

## 2. Vì sao chỉ giữ alias của list mutable là chưa đủ?

Xét Python:

```python
current = [10, 20, 30]
history = current

current.insert(0, 5)

assert history is current
assert history == [5, 10, 20, 30]
```

`history` chỉ là **tham chiếu khác đến cùng list**. Sau khi `current` thay đổi, `history` không còn trả trạng thái ban đầu.

Có thể sửa bằng cách tạo bản sao list:

```python
v0 = [10, 20, 30]
v1 = v0.copy()
v1.insert(0, 5)

assert v0 == [10, 20, 30]
assert v1 == [5, 10, 20, 30]
```

Với các phần tử `int` bất biến, cách này giữ được hai trạng thái. Nhưng `copy()` phải sao chép **`n` tham chiếu** cho danh sách dài `n`, nên mất **`O(n)` thời gian** và **`O(n)` bộ nhớ cấp ngoài**, dù chỉ muốn thêm một phần tử.

Danh sách liên kết bất biến có cách tổ chức khác: **không chép các nút đuôi**, mà dùng lại chính các nút cũ.

## 3. Cấu trúc danh sách liên kết đơn và phần đuôi

Một danh sách liên kết đơn (*singly linked list*) gồm chuỗi nút:

```text
head ──► [10] ──► [20] ──► [30] ──► None
```

Tại mỗi nút, trường `next` trỏ đến phần còn lại của danh sách. Ta gọi phần còn lại đó là **đuôi** (*tail*), ví dụ:

```text
Danh sách: [10, 20, 30]
Head value: 10
Tail:       [20, 30]
```

**Cần phân biệt hai cách dùng từ “tail”:** ở một số cấu trúc mutable, `tail` là **con trỏ tới nút cuối**. Trong bài này, `tail` có nghĩa chức năng phổ biến của functional list: **danh sách còn lại sau khi bỏ phần tử đầu**.

Do liên kết chỉ đi từ đầu sang sau:

- Đọc giá trị đầu: `O(1)`.
- Lấy tham chiếu tới danh sách đuôi: `O(1)`.
- Đi tới vị trí thứ `i`: cần đi qua khoảng `i` liên kết, `O(i+1)`.
- Đọc nút cuối nếu không có chỉ mục phụ: `O(n)`.

Chính hướng liên kết này làm việc **thêm đầu rất rẻ** nhưng **thêm cuối có thể đắt**, đặc biệt khi không được sửa nút cũ.

## 4. Mô hình persistent: một head cho mỗi phiên bản

Ta ký hiệu:

```text
v0 = danh sách [10,20,30]
v1 = thêm 5 vào đầu v0
v2 = thêm 7 vào đầu v0
```

Sơ đồ:

```text
v1 ──► [5] ───┐
               │
               ▼
v0 ──────────► [10] ──► [20] ──► [30] ──► None
               ▲
               │
v2 ──► [7] ───┘
```

Đây là **chia sẻ phần đuôi** (*tail sharing*):

- `v0` trỏ tới nút `10`.
- `v1` trỏ tới nút mới `5`, với `next` trỏ tới **chính nút `10`**.
- `v2` trỏ tới nút mới `7`, cũng với `next` trỏ tới **chính nút `10`**.

Ba phiên bản độc lập về **nội dung logic**, nhưng không độc lập về **danh tính mọi nút**: chúng dùng chung ba nút `10`, `20`, `30`. Đây là **chủ ý thiết kế** chứ không phải lỗi aliasing, miễn là phần được chia sẻ thực sự bất biến.

## 5. Python: định nghĩa nút bất biến

Chúng ta dùng Python 3.10+ và `dataclass(frozen=True, slots=True)` để chặn gán lại các trường qua giao diện thông thường. Để tập trung vào cơ chế chia sẻ, mỗi nút chứa **số nguyên**.

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Link:
    value: int
    next: "Link | None" = None
```

Tạo một nút đầu:

```python
last = Link(30)
middle = Link(20, last)
first = Link(10, middle)

assert first.value == 10
assert first.next is middle
assert middle.next is last
assert last.next is None
```

Không thể sửa liên kết bằng thao tác gán thuộc tính thông thường:

```python
try:
    first.next = None
except AttributeError:
    pass
else:
    raise AssertionError("Link không được sửa tại chỗ")
```

**Lưu ý:** `frozen=True` là cơ chế tạo hợp đồng đối tượng qua API thông thường; nó không phải một ranh giới bảo mật chống mọi kỹ thuật can thiệp nội bộ. Bên cạnh đó, nó không tự đóng băng một `list` hoặc `dict` nếu trường `value` tham chiếu tới chúng.

## 6. Dựng và duyệt danh sách bất biến

Ta cần các hàm nhỏ, tự chứa:

```python
def from_values(values):
    """Tạo danh sách liên kết từ một sequence như list/tuple."""
    head = None

    # Duyệt ngược để mỗi bước nối một phần tử vào đầu.
    for value in reversed(values):
        head = Link(value, head)

    return head


def to_list(head):
    """Trả một list mới chứa các giá trị theo thứ tự."""
    result = []
    node = head

    while node is not None:
        result.append(node.value)
        node = node.next

    return result


base = from_values([10, 20, 30])

assert to_list(base) == [10, 20, 30]
assert to_list(None) == []
assert to_list(from_values([])) == []
assert to_list(from_values([42])) == [42]
```

### Chi phí của các hàm hỗ trợ

Với `n` phần tử:

- `from_values`: tạo `n` nút, `O(n)` thời gian; nếu `values` là list/tuple có `reversed`, chỉ cần `O(1)` bộ nhớ phụ cho vòng lặp, ngoài `O(n)` bộ nhớ các nút mới.
- `to_list`: duyệt `n` nút, `O(n)` thời gian, `O(n)` bộ nhớ cho list đầu ra.
- Nếu đầu vào là **generator chỉ duyệt xuôi**, không thể gọi `reversed(generator)` trực tiếp; có thể vật hóa thành list trung gian `O(n)` rồi duyệt ngược, hoặc chọn kỹ thuật xây khác.

Các hàm trên **không sửa nút cũ**. `to_list` chỉ sao chép giá trị vào một list mới để thuận tiện in ra và kiểm thử.

## 7. Thêm đầu bằng cons: O(1) và đúng một nút mới

Trong lập trình hàm, thao tác tạo một danh sách bằng **phần tử đầu + phần đuôi** thường gọi là `cons`.

```python
def cons(value, tail):
    return Link(value, tail)


v0 = from_values([10, 20, 30])
v1 = cons(5, v0)

assert to_list(v0) == [10, 20, 30]
assert to_list(v1) == [5, 10, 20, 30]

# Đuôi của v1 chính là toàn bộ v0.
assert v1.next is v0
```

Chỉ có **một lần cấp phát nút mới**:

```text
v0 ──► A:10 ──► B:20 ──► C:30 ──► None
       ▲
       │
v1 ──► X:5 ──┘
```

Dù `v0` có 3 hay 3 triệu nút, `cons(5,v0)` vẫn chỉ:

1. Tạo nút `Link(5,v0)`.
2. Trả tham chiếu tới nút ấy.

Với thao tác cấp phát nút và gắn tham chiếu được tính `O(1)`:

- **Thời gian:** `O(1)`.
- **Nút mới:** 1.
- **Bộ nhớ phụ:** `O(1)`.

Đây là ưu thế cốt lõi của **danh sách liên kết đơn bất biến với cập nhật ở đầu**.

## 8. Lấy head, tail và pop mà không xóa nút cũ

Ta có thể thiết kế các thao tác chỉ đọc hoặc trả phiên bản đuôi.

```python
def head_value(head):
    if head is None:
        raise IndexError("head của danh sách rỗng")
    return head.value


def tail_of(head):
    if head is None:
        raise IndexError("tail của danh sách rỗng")
    return head.next


def pop_front(head):
    """Trả (giá trị đầu, danh sách đuôi), không sửa head."""
    if head is None:
        raise IndexError("pop từ danh sách rỗng")
    return head.value, head.next


v0 = from_values([10, 20, 30])

assert head_value(v0) == 10
assert to_list(tail_of(v0)) == [20, 30]

value, v_tail = pop_front(v0)

assert value == 10
assert v_tail is v0.next
assert to_list(v_tail) == [20, 30]
assert to_list(v0) == [10, 20, 30]
```

**Không có nút nào bị xóa khỏi phiên bản `v0`**. Ta chỉ trả con trỏ tới phần còn lại. Nếu gốc `v0` vẫn còn được giữ, các nút `10,20,30` vẫn có thể được truy cập từ nó.

Chi phí:

| Thao tác | Thời gian | Số nút mới |
| --- | --- | --- |
| `head_value(v)` | `O(1)` | 0 |
| `tail_of(v)` | `O(1)` | 0 |
| `pop_front(v)` | `O(1)` | 0 |

Với danh sách rỗng, cần một hợp đồng rõ: ở đây `head_value`, `tail_of` và `pop_front` **ném `IndexError`**, còn `to_list(None)` trả `[]`.

## 9. Tạo nhiều nhánh mà không ghi đè lịch sử

Một cấu trúc persistent có thể hỗ trợ **cập nhật từ bất kỳ phiên bản cũ nào còn được giữ** (*full persistence*).

```python
base = from_values([10, 20, 30])
branch_a = cons(5, base)
branch_b = cons(7, base)
branch_c = cons(9, branch_a)

assert to_list(base) == [10, 20, 30]
assert to_list(branch_a) == [5, 10, 20, 30]
assert to_list(branch_b) == [7, 10, 20, 30]
assert to_list(branch_c) == [9, 5, 10, 20, 30]

assert branch_a.next is base
assert branch_b.next is base
assert branch_c.next is branch_a
```

Các nhánh:

```text
branch_c ──► [9] ──► [5] ──┐
                            ▼
base ────────────────────► [10] ──► [20] ──► [30] ──► None
                            ▲
branch_b ──► [7] ──────────┘
```

Khi tạo `branch_c` từ `branch_a`, ta không cần “chuyển phiên bản hiện hành về A” để sửa toàn bộ cây: chỉ dùng **tham chiếu đầu của phiên bản A** làm tham số `tail`.

**Cấu trúc liên kết giữa các nút dữ liệu** và **đồ thị quan hệ giữa các phiên bản** là hai khái niệm khác nhau. Mỗi danh sách logic là một chuỗi đơn, còn tập hợp các phiên bản có thể phân nhánh và dùng chung đuôi.

## 10. Đếm nút vật lý phân biệt qua nhiều phiên bản

Nếu chỉ cộng độ dài mọi phiên bản, ta sẽ **đếm lặp các nút được chia sẻ**.

Ví dụ:

```text
base     = [10,20,30]       (3 nút logic)
branch_a = [5,10,20,30]     (4 nút logic)
branch_b = [7,10,20,30]     (4 nút logic)

Tổng độ dài logic = 3 + 4 + 4 = 11

Nhưng số nút vật lý phân biệt:
[10],[20],[30],[5],[7] = 5 nút
```

Ta có thể kiểm tra bằng **danh tính đối tượng**:

```python
def count_unique_nodes(roots):
    """Đếm các đối tượng Link phân biệt qua các gốc."""
    seen = set()
    stack = list(roots)

    while stack:
        node = stack.pop()

        if node is None:
            continue

        marker = id(node)
        if marker in seen:
            continue

        seen.add(marker)
        stack.append(node.next)

    return len(seen)


base = from_values([10, 20, 30])
branch_a = cons(5, base)
branch_b = cons(7, base)

assert count_unique_nodes([base]) == 3
assert count_unique_nodes([base, branch_a]) == 4
assert count_unique_nodes([base, branch_a, branch_b]) == 5
```

Ở đây `id(node)` giúp phân biệt các **đối tượng nút**; hai nút có cùng `value` vẫn tính là hai nút nếu chúng được tạo độc lập.

Hàm đếm chỉ dành cho chẩn đoán/kiểm thử: nó cần `O(U)` thời gian và `O(U)` bộ nhớ với `U` là số nút phân biệt có thể đi tới từ các gốc. **Không cần chạy phép đếm này sau mỗi cập nhật của ứng dụng**.

## 11. Tại sao dùng chung phần đuôi là an toàn?

Trong mô hình ở trên:

1. Một nút `Link` được tạo với một `value` và một tham chiếu `next`.
2. Sau khi tạo, không có thao tác nào sửa hai trường ấy theo hợp đồng.
3. Một phiên bản mới có thể trỏ tới nút cũ, nhưng không có quyền sửa nó.
4. Mọi lần duyệt từ gốc cũ vẫn đi qua **cùng chuỗi liên kết và cùng giá trị**.

Do đó, **chỉ thêm một nút ở đầu** không thể làm nội dung của danh sách cũ đổi.

### Chứng minh ngắn cho cons

Giả sử danh sách `tail` là bất biến và có nội dung `[a₁,a₂,...,aₙ]`. Hàm:

```python
new_head = Link(x, tail)
```

không viết vào `tail`; nó chỉ tạo nút mới có `value=x` và `next=tail`.

- Duyệt từ `tail` vẫn cho `[a₁,a₂,...,aₙ]`.
- Duyệt từ `new_head` cho `[x,a₁,a₂,...,aₙ]`.
- Các nút của `tail` không bị cấp phát lại.

Vậy `cons` **giữ phiên bản cũ** và chỉ tạo **một nút mới**. Đây chính là nội dung của cả **immutability** và **tail sharing**.

## 12. Vì sao thêm cuối không thể O(1) bằng cách sửa nút cuối?

Giả sử:

```text
v0 ──► [10] ──► [20] ──► [30] ──► None
```

Muốn có `v1=[10,20,30,40]`, một cấu trúc mutable có thể đi tới nút `30` rồi sửa:

```text
node_30.next = Link(40)
```

Nhưng `node_30` cũng thuộc `v0`. Nếu sửa `next` tại đó, `v0` **bất ngờ thấy thêm `40`**, phá lời hứa lưu phiên bản.

### Cách đúng trong danh sách bất biến đơn

Phải tạo một đường mới từ đầu đến nút cuối:

```text
v0: [10] ──► [20] ──► [30] ──► None

v1: [10'] ─► [20'] ─► [30'] ─► [40] ─► None
```

Không thể dùng chung nút `30` vì `next` của nó cần khác. Tương tự `20` và `10` phải được tạo lại để nối tới phần sau phiên bản mới.

Với danh sách đơn **chỉ có liên kết `next` bất biến và cập nhật theo đầu**, thêm cuối cần:

- Duyệt `n` nút cũ.
- Tạo `n+1` nút mới nếu danh sách ban đầu dài `n`.
- Thời gian `O(n+1)`, hay `Θ(n)` với `n ≥ 1`.
- Không chia sẻ nút cấu trúc với phiên bản cũ trong phương án đơn giản này.

**Đây không phải giới hạn của mọi sequence persistent**. Các cấu trúc như cây phân nhánh hoặc queue functional chuyên dụng có thể hỗ trợ thao tác khác hiệu quả hơn. Kết luận ở đây dành cho **danh sách liên kết đơn bất biến thông thường**.

## 13. Thay phần tử ở giữa: cần sao chép tiền tố

Giả sử `v0=[10,20,30,40]`, ta muốn thay vị trí chỉ số `1` (giá trị `20`) thành `99`.

Không được gán:

```python
# Không được sửa trực tiếp một nút đã thuộc v0:
# v0.next.value = 99
```

Thay vào đó:

1. Đi từ đầu tới vị trí cần sửa.
2. Tạo **nút mới cho phần tử được sửa**.
3. Cho nút mới ấy trỏ tới **cùng phần đuôi sau vị trí sửa**.
4. Tạo lại các nút **tiền tố đứng trước vị trí sửa**, từ gần chỗ sửa ngược về đầu.
5. Trả gốc mới.

```text
v0: [10] ──► [20] ──► [30] ──► [40] ──► None
                          ▲
                          └── phần đuôi có thể chia sẻ

v1: [10'] ──► [99] ───────┘
```

Hai nút `10'` và `99` là mới; hai nút `30` và `40` vẫn là **các đối tượng cũ**.

Đây là **path copying trên danh sách liên kết**: ta sao chép **đường tiền tố** từ gốc tới vị trí thay đổi, chứ không sao chép toàn bộ các nút.

## 14. Python: cập nhật một vị trí bằng path copying

Ta dùng thuật toán **lặp**, tránh đệ quy sâu trên danh sách dài.

```python
def update_at(head, index, value):
    """Trả danh sách mới với phần tử tại index được thay.

    index tính từ 0. Không sửa nút cũ.
    """
    if index < 0:
        raise IndexError("index phải không âm")

    path = []
    current = head
    remaining = index

    # Lưu các nút nằm trước vị trí cần thay.
    while remaining > 0:
        if current is None:
            raise IndexError("index ngoài danh sách")

        path.append(current)
        current = current.next
        remaining -= 1

    if current is None:
        raise IndexError("index ngoài danh sách")

    # Với số nguyên, cùng giá trị nghĩa là không đổi logic.
    if current.value == value:
        return head

    # Phần đuôi sau vị trí thay được chia sẻ.
    new_head = Link(value, current.next)

    # Tạo lại tiền tố theo hướng từ phải sang trái.
    for old in reversed(path):
        new_head = Link(old.value, new_head)

    return new_head
```

### Kiểm chứng dữ liệu và chia sẻ

```python
base = from_values([10, 20, 30, 40])
changed = update_at(base, 1, 99)

assert to_list(base) == [10, 20, 30, 40]
assert to_list(changed) == [10, 99, 30, 40]

assert changed is not base
assert changed.next is not base.next

# Hai nút 30 và 40 là cùng đối tượng của phiên bản cũ.
assert changed.next.next is base.next.next

# Chỉ có 2 nút mới: 10' và 99.
assert count_unique_nodes([base, changed]) == 6
```

### Cập nhật ở đầu và ở cuối

```python
front_changed = update_at(base, 0, 7)
assert to_list(front_changed) == [7, 20, 30, 40]
assert front_changed.next is base.next

last_changed = update_at(base, 3, 77)
assert to_list(last_changed) == [10, 20, 30, 77]
assert count_unique_nodes([base, last_changed]) == 8
```

Ở chỉ số `0`, chỉ cần **một nút mới**, chia sẻ toàn bộ đuôi. Ở chỉ số cuối cùng `3` của dãy bốn nút, phải tạo lại **cả bốn nút**, không còn phần đuôi khác rỗng để chia sẻ.

### Trường hợp không thay đổi

```python
same = update_at(base, 1, 20)

assert same is base
assert to_list(base) == [10, 20, 30, 40]
```

Nhờ kiểm tra `current.value == value`, thuật toán có thể trả **chính gốc cũ** nếu không có cập nhật logic. Đây là tối ưu, không phải điều kiện bắt buộc của tính persistent.

## 15. Chi phí cập nhật tại chỉ số i

Với chỉ số **0-based** `i` hợp lệ:

- Phải duyệt `i+1` nút để đến vị trí cần cập nhật.
- Nếu giá trị thay đổi, tạo **`i+1` nút mới**: một nút tại vị trí sửa và `i` nút tiền tố.
- Phần đuôi sau chỉ số `i` được **dùng chung**.
- Bản lặp lưu `i` nút tiền tố trong mảng `path`.

Vì vậy:

```text
Thời gian:                   Θ(i + 1)
Số nút mới nếu đổi giá trị:  i + 1
Bộ nhớ phụ lưu đường đi:     O(i)
```

Trường hợp xấu khi `i = n-1`:

```text
Thời gian: Θ(n)
Nút mới:  n
```

Nếu giá trị **không đổi** và ta dùng tối ưu `same is base`, thời gian vẫn cần đi tới vị trí `i` nhưng **không tạo nút mới**.

**Phân biệt:** bộ nhớ phụ `path` tách biệt với **bộ nhớ nút mới** được cấp phát để giữ phiên bản; cả hai có thể tăng tuyến tính theo `i`.

## 16. Xóa phần tử: bỏ đầu O(1), bỏ giữa sao chép tiền tố

Khi xóa phần tử đầu, chỉ cần **trả `head.next`**. Không thay đổi nút nào:

```text
v0: [10] ──► [20] ──► [30]
             ▲
             │
v1 ──────────┘
```

Nhưng để xóa vị trí `1` của `[10,20,30,40]`, phải tạo nút đầu mới mang `10`, với `next` bỏ qua nút `20` và trỏ tới nút `30` cũ.

```text
v0: [10] ──► [20] ──► [30] ──► [40] ──► None

v1: [10'] ──────────► [30] ──► [40] ──► None
```

Một bản xóa không sửa nút cũ:

```python
def remove_at(head, index):
    """Trả (giá trị bị xóa, danh sách mới).

    Không sửa các nút trong danh sách cũ.
    """
    if index < 0:
        raise IndexError("index phải không âm")

    path = []
    current = head
    remaining = index

    while remaining > 0:
        if current is None:
            raise IndexError("index ngoài danh sách")

        path.append(current)
        current = current.next
        remaining -= 1

    if current is None:
        raise IndexError("index ngoài danh sách")

    # Bỏ qua nút cần xóa; dùng chung phần đuôi phía sau.
    new_head = current.next

    for old in reversed(path):
        new_head = Link(old.value, new_head)

    return current.value, new_head
```

### Kiểm thử xóa

```python
base = from_values([10, 20, 30, 40])

removed, without_second = remove_at(base, 1)

assert removed == 20
assert to_list(without_second) == [10, 30, 40]
assert to_list(base) == [10, 20, 30, 40]

assert without_second.next is base.next.next
assert count_unique_nodes([base, without_second]) == 5

removed_front, after_front = remove_at(base, 0)

assert removed_front == 10
assert after_front is base.next
assert count_unique_nodes([base, after_front]) == 4
```

Nếu xóa tại chỉ số `i`, số nút tiền tố phải tạo lại là **`i`**. Thời gian tìm vị trí và dựng lại là **`Θ(i+1)`**; xóa đầu `i=0` là `O(1)` và **0 nút mới**.

## 17. Chèn tại một vị trí: phần đuôi từ đó trở đi được chia sẻ

Để chèn giá trị `25` **trước** phần tử ở chỉ số `2` của `[10,20,30,40]`:

```text
v0: [10] ──► [20] ──► [30] ──► [40]

v1: [10'] ─► [20'] ─► [25] ──┐
                              ▼
                             [30] ──► [40]
```

Chỉ có `10'`, `20'`, `25` là nút mới. Các nút `30,40` vẫn được chia sẻ.

```python
def insert_at(head, index, value):
    """Chèn value trước vị trí index, cho phép index == length."""
    if index < 0:
        raise IndexError("index phải không âm")

    path = []
    current = head
    remaining = index

    while remaining > 0:
        if current is None:
            raise IndexError("index ngoài danh sách")

        path.append(current)
        current = current.next
        remaining -= 1

    # current là phần đuôi từ vị trí index.
    new_head = Link(value, current)

    for old in reversed(path):
        new_head = Link(old.value, new_head)

    return new_head
```

### Kiểm thử

```python
base = from_values([10, 20, 30, 40])

inserted = insert_at(base, 2, 25)
assert to_list(inserted) == [10, 20, 25, 30, 40]

assert inserted.next.next.next is base.next.next
assert count_unique_nodes([base, inserted]) == 7

first_insert = insert_at(base, 0, 5)
assert first_insert.next is base

end_insert = insert_at(base, 4, 50)
assert to_list(end_insert) == [10, 20, 30, 40, 50]
assert count_unique_nodes([base, end_insert]) == 9
```

Với chỉ số `i` hợp lệ trong đoạn `0..n`, số nút mới là **`i+1`**. Vì vậy:

- Chèn đầu `i=0`: **1 nút**, `O(1)`.
- Chèn giữa: sao chép `i` nút tiền tố, dùng chung đuôi.
- Chèn cuối `i=n`: **`n+1` nút**, `Θ(n+1)`.

Hàm này cho phép **chèn vào danh sách rỗng** ở `index=0`; các vị trí ngoài phạm vi ném `IndexError`.

## 18. Nối hai danh sách: sao chép bên trái, chia sẻ bên phải

Giả sử:

```text
left  = [10,20]
right = [30,40]
```

Ta muốn `concat(left,right)=[10,20,30,40]` mà vẫn giữ cả hai danh sách cũ.

Không thể dùng nguyên nút `20` vì `next` của nó ban đầu là `None`, còn trong kết quả cần trỏ tới nút `30`.

Nhưng ta **có thể chia sẻ nguyên danh sách `right`**:

```text
left:   [10] ──► [20] ──► None

right:  [30] ──► [40] ──► None
         ▲
         │
result: [10'] ──► [20'] ──┘
```

Cài đặt:

```python
def concat(left, right):
    """Nối hai danh sách bất biến; giữ nguyên cả hai đầu vào."""
    if left is None:
        return right
    if right is None:
        return left

    prefix = []
    node = left

    while node is not None:
        prefix.append(node.value)
        node = node.next

    result = right

    for value in reversed(prefix):
        result = Link(value, result)

    return result


left = from_values([10, 20])
right = from_values([30, 40])

joined = concat(left, right)

assert to_list(joined) == [10, 20, 30, 40]
assert to_list(left) == [10, 20]
assert to_list(right) == [30, 40]

assert joined.next.next is right
assert count_unique_nodes([left, right, joined]) == 6
```

### Độ phức tạp

Gọi `a` là số nút của `left`:

- Sao chép `a` giá trị vào `prefix` và tạo `a` nút mới: **`O(a)` thời gian**.
- Nút mới: **`a`** (nếu cả hai danh sách không rỗng).
- Danh sách `right` được chia sẻ **nguyên vẹn**, không phụ thuộc độ dài `b` của nó.
- Bộ nhớ phụ cho mảng `prefix` là **`O(a)`**.

Nếu `left` rỗng, trả **chính `right`**. Nếu `right` rỗng, trả **chính `left`**; không có thay đổi logic nên không cần cấp phát.

**Thứ tự hai toán hạng quan trọng:** `concat(left,right)` sao chép phần trái, dùng chung phần phải; đổi thứ tự có thể thay đổi rất lớn số nút phải tạo.

## 19. Đảo ngược danh sách: phải tạo những liên kết mới

Hàm đảo ngược một danh sách mutable có thể đổi con trỏ `next` của các nút cũ. Với danh sách immutable, **không được sửa liên kết cũ**.

Tuy nhiên, có thể dựng danh sách ngược bằng `cons` trong một vòng lặp:

```python
def reversed_list(head):
    result = None
    current = head

    while current is not None:
        result = Link(current.value, result)
        current = current.next

    return result


base = from_values([10, 20, 30])
backward = reversed_list(base)

assert to_list(base) == [10, 20, 30]
assert to_list(backward) == [30, 20, 10]
assert count_unique_nodes([base, backward]) == 6
```

Dù mỗi lần `cons` là `O(1)`, thuật toán phải đi qua **`n` nút**, nên tổng:

- **`Θ(n)` thời gian**.
- **`n` nút mới** cho bản đảo với `n > 0`.
- **`O(1)` bộ nhớ điều khiển phụ** khi dùng vòng lặp, chưa kể các nút đầu ra.

Thông thường **không thể chia sẻ trực tiếp các nút cũ** khi đảo ngược vì liên kết giữa các giá trị phải có hướng khác.

## 20. Bảng chi phí các thao tác chính

Gọi `n` là độ dài danh sách hiện có, `i` là chỉ số hợp lệ tính từ 0 và `a` là độ dài toán hạng bên trái của phép nối.

| Thao tác | Thời gian | Số nút mới | Phần được chia sẻ |
| --- | --- | --- | --- |
| `cons(x,head)` | **`O(1)`** | **1** | Toàn bộ `head` |
| `head_value(head)` | **`O(1)`** | 0 | Không thay đổi |
| `tail_of(head)` | **`O(1)`** | 0 | Nguyên đuôi |
| `pop_front(head)` | **`O(1)`** | 0 | Nguyên đuôi |
| Đọc phần tử thứ `i` | `O(i+1)` | 0 | Không thay đổi |
| `update_at(head,i,x)` đổi giá trị | `Θ(i+1)` | `i+1` | Đuôi sau chỉ số `i` |
| `remove_at(head,i)` | `Θ(i+1)` | `i` | Đuôi sau nút bị bỏ |
| `insert_at(head,i,x)` | `Θ(i+1)` | `i+1` | Đuôi từ chỉ số `i` |
| Chèn cuối `insert_at(head,n,x)` | `Θ(n+1)` | `n+1` | Không có nút cũ |
| `concat(left,right)`, cả hai không rỗng | `Θ(a)` | `a` | Toàn bộ `right` |
| `reversed_list(head)` | `Θ(n)` | `n` | Thường không chia sẻ nút cũ |
| `to_list(head)` | `Θ(n)` | 0 nút `Link` | Trả list đầu ra mới |

**Chú ý:**

- `update_at` có thể không cấp phát nếu value không đổi.
- Các thao tác `head/tail/pop` trên danh sách **rỗng** cần hợp đồng riêng; ví dụ ở đây ném `IndexError`.
- Bảng đếm **nút `Link` mới**, chưa tính ô của mảng `path`, kết quả `to_list` hay chi phí của payload.
- Khi `n=0`, công thức `O(n+1)` giúp mô tả việc vẫn phải tạo một nút; với `n≥1`, cách ghi `O(n)` thường đủ.

## 21. Chứng minh vì sao chỉ sao chép tiền tố là đủ

Xét cập nhật ở chỉ số `i`:

```text
Danh sách cũ:
[a0, a1, ..., a(i-1), ai, a(i+1), ..., a(n-1)]
```

Giả sử cần thay `ai` bằng `x`. Chia danh sách thành:

- Tiền tố `[a0,...,a(i-1)]`.
- Phần tử thay `ai`.
- Đuôi `[a(i+1),...,a(n-1)]`.

Thuật toán `update_at` tạo một nút `x` với `next` bằng tham chiếu tới **đuôi cũ**. Sau đó lần lượt tạo bản sao của tiền tố từ phải sang trái.

### Vì sao kết quả có đúng thứ tự?

Khi tạo nút `x` trước, danh sách mới tạm thời có nội dung:

```text
[x, a(i+1), ..., a(n-1)]
```

Khi thêm ngược `a(i-1), ..., a0` vào đầu, kết quả trở thành:

```text
[a0, ..., a(i-1), x, a(i+1), ..., a(n-1)]
```

Đúng yêu cầu thay phần tử tại `i`, không thay các giá trị khác.

### Vì sao phiên bản cũ không đổi?

Không có phép gán vào `value` hoặc `next` của nút cũ. Chỉ có các lời gọi tạo `Link(...)` mới và giữ lại tham chiếu của đuôi cũ. Do các nút đuôi bất biến, phiên bản cũ vẫn có thể duyệt theo cùng đường cũ.

### Vì sao không thể chia sẻ tiền tố cũ theo cách này?

Nút `a(i-1)` cũ đang trỏ tới `ai` cũ, nhưng ở phiên bản mới cần trỏ tới nút `x` mới. Nếu dùng lại `a(i-1)` mà không sửa `next`, đường từ gốc mới sẽ **không đi tới thay đổi**.

Tương tự, những nút đứng trước nó cần liên kết mới tới bản sao tiền tố, nên phải được tạo lại. Đây là lý do chi phí phụ thuộc **vị trí cập nhật**, không chỉ số lượng phần tử được sửa.

## 22. Bản lặp và bản đệ quy: tránh giới hạn call stack

Ta có thể viết phiên bản đệ quy ngắn hơn cho việc thay ở chỉ số `i`:

```python
def update_at_recursive(head, index, value):
    if index < 0 or head is None:
        raise IndexError("index ngoài danh sách")

    if index == 0:
        if head.value == value:
            return head
        return Link(value, head.next)

    changed_tail = update_at_recursive(
        head.next, index - 1, value
    )

    if changed_tail is head.next:
        return head

    return Link(head.value, changed_tail)
```

Hàm này dễ đọc vì phản ánh trực tiếp cấu trúc:

```text
update(head, i) =
    nếu i=0: thay head
    ngược lại: giữ head.value và cập nhật tail ở i-1
```

Tuy nhiên:

- Độ sâu đệ quy tới `i+1`.
- Bộ nhớ call stack `O(i+1)`.
- Trong Python, danh sách rất dài có thể gây **`RecursionError`** khi `i` lớn.

Bản lặp `update_at` ở phần 14 dùng `path` tường minh nên tránh lỗi giới hạn call stack của Python. **Nó không làm giảm bậc thời gian hoặc số nút cần tạo**: vẫn `Θ(i+1)` khi có thay đổi.

## 23. Khi giữ nhiều phiên bản, bộ nhớ tăng thế nào?

Giả sử có một danh sách ban đầu dài `n`, và ta giữ mọi gốc phiên bản.

### Trường hợp liên tục thêm đầu

Mỗi lần `cons` chỉ tạo một nút mới:

```text
v0: n nút
v1: n nút cũ + 1 nút
v2: n nút cũ + 2 nút
...
vm: n nút cũ + m nút
```

Số nút vật lý phân biệt:

```text
n + m
```

Vậy với `m` lần thêm đầu thành công:

- **Tổng số nút cấp phát**: `Θ(n+m)` tính cả n nút ban đầu.
- **Chi phí mỗi cập nhật**: `O(1)` thời gian và một nút.
- Có thể giữ `m+1` gốc phiên bản, dùng thêm `O(m)` tham chiếu gốc.

### Trường hợp mỗi phiên bản cập nhật cuối danh sách

Nếu mỗi phiên bản có độ dài cố định `n`, thay giá trị ở chỉ số cuối phải tạo **`n` nút mới**. Sau `m` lần cập nhật như vậy và giữ tất cả gốc, số nút cấp phát có thể:

```text
n + m · n = Θ((m+1)n)
```

Structural sharing ở phần đuôi **không giúp nhiều** trong trường hợp này, vì sau vị trí cuối chỉ có `None` để chia sẻ.

### Trường hợp cập nhật vị trí khác nhau

Nếu lượt thứ `j` thay giá trị tại chỉ số `i_j`, số nút mới là `i_j+1` (trừ cập nhật không đổi):

```text
Nút đã cấp phát ≤ n + Σ(i_j + 1)
```

Công thức này rõ hơn việc chỉ ghi `O(mn)`: nó cho biết **mức chia sẻ phụ thuộc phân bố các vị trí được sửa**.

## 24. “Dùng chung đuôi” và vòng đời bộ nhớ

Một ứng dụng có thể giữ:

```text
history = [v0, v1, v2, ...]
```

Các gốc trong `history` giữ tham chiếu tới những nút thuộc phiên bản của chúng.

Nếu bỏ `v0` khỏi `history`:

- Những nút vẫn được `v1`, `v2` hoặc một tham chiếu khác trỏ tới **không thể xem là đã chết**.
- Những nút chỉ reachable từ `v0` và không còn tham chiếu tới chúng **có thể được thu hồi** theo cơ chế quản lý bộ nhớ.
- Không thể suy từ việc xóa một gốc rằng “giải phóng ngay toàn bộ nút của phiên bản ấy”, bởi các phiên bản **chia sẻ đuôi**.

### Ví dụ

```text
v0 ──► [10] ──► [20] ──► [30]

v1 ──► [5] ──► [10] ──► [20] ──► [30]
                    ▲
                    │
                    v0
```

Bỏ biến `v0` không khiến các nút `10,20,30` mất đi khi `v1` còn trỏ tới chúng.

**Persistence không buộc giữ mọi phiên bản vô hạn.** Nó bảo đảm những phiên bản **còn được giữ và còn hợp lệ** không bị thao tác trên phiên bản khác phá hỏng.

## 25. So sánh danh sách liên kết bất biến với tuple và mảng

Một tuple Python cũng có thể biểu diễn một dãy **bất biến cấp ngoài**:

```python
v0 = (10, 20, 30)
v1 = (5,) + v0

assert v0 == (10, 20, 30)
assert v1 == (5, 10, 20, 30)
```

Nhưng `(5,) + v0` tạo một tuple mới có `n+1` vị trí và phải sao chép các tham chiếu tới giá trị, nên là **`O(n)` thời gian/bộ nhớ cấp ngoài** khi n lớn.

Bảng chọn biểu diễn:

| Tiêu chí | Linked list bất biến | Tuple/mảng bất biến cấp ngoài |
| --- | --- | --- |
| Thêm đầu và giữ bản cũ | **`O(1)`** với `cons` | Thường **`O(n)`** do phải tạo dãy mới |
| Lấy phần tử đầu | `O(1)` | `O(1)` |
| Lấy phần đuôi không sao chép | **`O(1)`** bằng `next` | Phụ thuộc API; slicing tuple Python tạo tuple mới |
| Truy cập chỉ số bất kỳ | `O(i+1)` | **`O(1)`** với tuple/list |
| Cập nhật chỉ số giữa thành bản mới | `O(i+1)` nút tiền tố | `O(n)` tham chiếu cho tuple mới |
| Duyệt tuần tự | `O(n)` | `O(n)`, thường có locality tốt hơn |
| Chi phí nút/con trỏ | Một đối tượng và tham chiếu mỗi nút | Bố trí liên tiếp tham chiếu, ít overhead hơn |
| Phù hợp đặc biệt | Stack, phiên bản tạo bằng thêm đầu | Đọc theo chỉ số, dữ liệu tĩnh |

**Không có lựa chọn nào thắng mọi thao tác.** Linked list persistent tận dụng tốt **cập nhật ở đầu**; tuple/mảng hiệu quả hơn cho **truy cập ngẫu nhiên** và thường dễ xử lý trong những bài toán thiên về đọc theo chỉ số.

### Một lựa chọn khác: persistent vector

Một *persistent vector* dựa trên cây phân nhánh có thể hỗ trợ cập nhật chỉ số bằng chia sẻ cấu trúc theo đường đi. Nó khác cả tuple và linked list, với độ phức tạp phụ thuộc bậc phân nhánh và hiện thực. Khi cần **vừa có phiên bản vừa truy cập chỉ số tốt**, đây là hướng đáng tìm hiểu.

## 26. Ứng dụng: stack persistent và undo

Một stack là cấu trúc **LIFO** (*Last In, First Out*): phần tử vào sau ra trước. Danh sách liên kết đơn bất biến đặc biệt tự nhiên để hiện thực stack:

```text
push(x)     ↔ cons(x, top)
peek()      ↔ head_value(top)
pop()       ↔ pop_front(top)
```

Mỗi thao tác stack cơ bản có **`O(1)` thời gian**, và `push` chỉ tạo một nút mới.

### Ví dụ undo nhiều bước

```python
states = [None]  # Stack rỗng ban đầu.

states.append(cons(10, states[-1]))
states.append(cons(20, states[-1]))
states.append(cons(30, states[-1]))

assert to_list(states[0]) == []
assert to_list(states[1]) == [10]
assert to_list(states[2]) == [20, 10]
assert to_list(states[3]) == [30, 20, 10]

# Quay lại trạng thái trước lần push 30.
previous_state = states[2]

assert to_list(previous_state) == [20, 10]

# Tạo một nhánh khác từ phiên bản cũ.
alternative = cons(99, previous_state)

assert to_list(alternative) == [99, 20, 10]
assert to_list(states[3]) == [30, 20, 10]
```

**Chi phí của lịch sử:** mỗi lần push tạo **một nút mới**; lưu thêm một head vào `states` có chi phí một tham chiếu. Không cần chụp bản sao toàn bộ stack sau mỗi thao tác.

### Giới hạn

Mô hình này giữ nội dung stack của từng trạng thái. Nó chưa tự cung cấp **thời điểm thay đổi, quyền truy cập, lưu bền trên đĩa, đồng bộ đa luồng hay cơ chế merge các nhánh**.

## 27. Không nên dùng danh sách đơn bất biến cho mọi loại queue

Một queue FIFO cần:

- `enqueue` thêm ở cuối.
- `dequeue` lấy ở đầu.

Với danh sách liên kết đơn bất biến đơn giản:

- `dequeue` ở đầu là `O(1)`.
- `enqueue` ở cuối có thể là `O(n)`, vì phải tạo lại mọi nút tiền tố.

Do đó, một queue cần hiệu năng tốt ở cả hai đầu thường dùng thiết kế khác, ví dụ **hai danh sách bất biến**:

```text
front: các phần tử sắp được lấy ra
rear:  các phần tử mới thêm, lưu ngược thứ tự

Khi front rỗng:
    đảo rear thành front theo quy tắc tái cân bằng
```

Nhiều hiện thực functional queue đạt **`O(1)` khấu hao** cho `enqueue/dequeue` dưới mô hình phân tích thích hợp, nhưng một số thiết kế cần quản lý sự lười đánh giá hoặc lịch tái cân bằng để có bảo đảm trường hợp xấu.

**Mục tiêu bài này không phải cài queue đầy đủ**, mà là nhận ra chi phí theo hướng liên kết: **thêm đầu rẻ**, **thêm cuối không tự rẻ**, nên cần chọn biểu diễn đúng theo bộ thao tác.

## 28. Payload mutable có thể phá tính ổn định của phiên bản

Cho dù nút `Link` được đánh dấu `frozen=True`, nếu trường `value` là một đối tượng mutable, vẫn có thể xảy ra alias.

```python
@dataclass(frozen=True, slots=True)
class LinkOfLists:
    value: list[int]
    next: "LinkOfLists | None" = None


external = [8, 9]
old = LinkOfLists(external)
new = LinkOfLists([10], old)

external.append(7)

assert old.value == [8, 9, 7]
assert new.next.value == [8, 9, 7]
```

Hai gốc chia sẻ đuôi `old` đúng về **cấu trúc nút**, nhưng nội dung điểm ở đuôi bị thay đổi từ bên ngoài. Nếu ứng dụng cần **lịch sử điểm bất biến**, kết quả này là **lỗi hợp đồng**, không phải ưu điểm.

### Đóng băng phần tử theo miền dữ liệu

Với dãy điểm `list[int]`, có thể chuyển thành tuple khi nhận:

```python
@dataclass(frozen=True, slots=True)
class LinkOfTuples:
    value: tuple[int, ...]
    next: "LinkOfTuples | None" = None


input_grades = [8, 9]
old_safe = LinkOfTuples(tuple(input_grades))
new_safe = LinkOfTuples((10,), old_safe)

input_grades.append(7)

assert old_safe.value == (8, 9)
assert new_safe.next is old_safe
```

Ở đây `int` và tuple được dùng như **giá trị bất biến**. Với đối tượng phức tạp hơn, cần kiểm tra mọi đối tượng lồng nhau hoặc chính sách quyền sở hữu; **đóng băng nút ngoài không tự đóng băng sâu payload**.

### Không nhầm với read-only view

Một API “chỉ đọc” của list mutable có thể vẫn thấy thay đổi từ chủ sở hữu nguồn. Danh sách immutable có **các nút liên kết không đổi** và phần tử ổn định thì mới bảo vệ đúng nội dung của phiên bản đã tạo.

## 29. Danh tính, tính bằng nhau và tính chia sẻ

Hai danh sách có thể **bằng nhau về giá trị** nhưng **không dùng chung nút**.

```python
a = from_values([10, 20, 30])
b = from_values([10, 20, 30])

assert to_list(a) == to_list(b)
assert a is not b
assert a.next is not b.next

assert count_unique_nodes([a, b]) == 6
```

Ngược lại:

```python
base = from_values([10, 20, 30])
a = cons(5, base)
b = cons(7, base)

assert a.next is base
assert b.next is base
assert count_unique_nodes([base, a, b]) == 5
```

**Kiểm thử hai điều riêng:**

1. **Nội dung phiên bản:** dùng `to_list(...) == [...]`.
2. **Nút được chia sẻ:** dùng `is` hoặc đếm `id(node)`.

Đừng dùng `a == b` của một dataclass lồng nhau như bằng chứng chia sẻ, bởi `==` kiểm tra **giá trị trường** và còn có thể tốn thời gian tỷ lệ với độ dài danh sách.

## 30. Bất biến về cấu trúc và vòng tham chiếu

Trong một danh sách liên kết đơn thông thường, ta muốn:

- Mỗi nút có tối đa một liên kết `next`.
- Một danh sách kết thúc ở `None`.
- Không có chu trình từ head về nút trước đó.
- Mỗi phiên bản có một thứ tự tuyến tính duy nhất.

Nếu ta chỉ tạo nút mới bằng `Link(value, tail)`, trong đó `tail` là danh sách hữu hạn đã hợp lệ, thì việc thêm đầu **không thể tạo chu trình**: nút mới chưa xuất hiện trong phần đuôi cũ.

Một hàm kiểm tra chu trình khi nhận dữ liệu không đáng tin cậy có thể dùng hai con trỏ:

```python
def has_cycle(head):
    slow = head
    fast = head

    while fast is not None and fast.next is not None:
        slow = slow.next
        fast = fast.next.next

        if slow is fast:
            return True

    return False


base = from_values([10, 20, 30])

assert has_cycle(base) is False
assert has_cycle(cons(5, base)) is False
```

Thuật toán *Floyd's tortoise and hare* kiểm tra chu trình trong **`O(n)` thời gian** và **`O(1)` bộ nhớ phụ**, với danh sách hữu hạn không có chu trình hoặc chu trình phát hiện được.

**Không cần chạy `has_cycle` sau mỗi `cons`** nếu cấu trúc chỉ được tạo qua những constructor đúng và các nút thực sự bất biến. Nhưng nó hữu ích khi đọc dữ liệu đã bị lỗi hoặc kiểm tra một hiện thực tùy biến.

## 31. Đọc đồng thời và công bố phiên bản

Nếu nhiều người đọc giữ **những head phiên bản khác nhau**, các nút `Link` bất biến và payload ổn định cho phép họ duyệt dữ liệu mà không có thao tác nào trên các phiên bản mới phải sửa những nút họ đang đọc.

```text
reader A ──► v0 ──► [10] ──► [20]
reader B ──► v1 ──► [5] ──┐
                           ▼
                          [10] ──► [20]

writer tạo v2 bằng cách tạo nút mới,
không thay liên kết đang được reader duyệt.
```

Tuy vậy, **immutability không tự giải quyết toàn bộ concurrency**:

- Cần công bố head mới theo quy tắc bộ nhớ/đồng bộ của ngôn ngữ.
- Hai writer có thể cùng lấy một head cũ và tạo hai nhánh; việc chọn bản hiện hành có thể gây *lost update* nếu không có cơ chế điều phối.
- Payload mutable vẫn có thể gây race nếu bị sửa đồng thời.
- Nhiều cập nhật phải thành một giao dịch nghiệp vụ cần hợp đồng nhất quán riêng.

**Kết luận:** chia sẻ đuôi bất biến giúp thao tác đọc theo phiên bản dễ suy luận hơn, nhưng không thay thế khóa, nguyên tử, transaction hay chính sách xung đột ở lớp quản lý trạng thái.

## 32. Khi nào chọn danh sách bất biến và dùng chung đuôi?

Cấu trúc này phù hợp khi:

- Chủ yếu có thao tác **thêm/bỏ đầu**.
- Muốn lưu nhiều **phiên bản stack** cho undo hoặc thử nghiệm phân nhánh.
- Muốn một API **không sửa dữ liệu truyền vào**.
- Thường xử lý theo **quy nạp đầu–đuôi** trong thuật toán hàm.
- Các phiên bản có chung **phần đuôi dài**, giúp chia sẻ tiết kiệm bộ nhớ.

Nó kém phù hợp khi:

- Cần **truy cập chỉ số ngẫu nhiên `O(1)`**.
- Thường xuyên **thêm cuối**, chèn giữa hoặc cập nhật phần tử sâu.
- Cần duyệt rất nhiều nút và hiệu năng **locality/cache** quan trọng.
- Phần tử là đối tượng mutable phức tạp mà API chưa có hợp đồng sở hữu rõ.
- Không cần giữ lịch sử và chỉ dùng một trạng thái mutable hiện hành.

### Câu hỏi quyết định

1. Thao tác thường xuyên nhất là ở **đầu hay cuối**?
2. Có cần **bao nhiêu phiên bản**, giữ trong bao lâu?
3. Phần đuôi được chia sẻ có thật sự **không thể sửa** không?
4. Giá trị tại nút có mutable hoặc alias bên ngoài không?
5. Có cần truy cập theo chỉ số hay quét toàn bộ?
6. Người dùng cần **snapshot ổn định** hay một **view sống**?
7. Độ dài danh sách có thể gây vấn đề **đệ quy sâu** không?
8. Có cần giao dịch đồng thời hoặc merge các nhánh không?

Chọn cấu trúc theo **bộ thao tác và hợp đồng dữ liệu**, thay vì chỉ theo danh xưng “bất biến”.

## 33. Các lỗi thường gặp

1. **Giữ alias của list mutable rồi gọi đó là phiên bản cũ.** Alias cùng thấy cập nhật.
2. **Cho rằng immutable nghĩa là không thể thêm phần tử theo nghĩa logic.** Có thể trả head mới.
3. **Tưởng `cons` phải copy cả danh sách.** Nó chỉ tạo một nút và dùng chung đuôi.
4. **Tưởng đuôi được sao chép nông ở mỗi `cons`.** Đuôi là **chính cùng đối tượng nút cũ**.
5. **Dùng `==` để kiểm tra hai phiên bản chia sẻ nút.** Phải dùng `is`/danh tính.
6. **Sửa `old.next` để chèn cuối.** Phá phiên bản cũ.
7. **Chỉ tạo nút mới ở giữa nhưng không sao chép tiền tố.** Head mới không dẫn tới thay đổi.
8. **Sao chép cả đuôi khi chỉ thay một phần tử ở đầu.** Lãng phí, mất lợi ích O(1).
9. **Cho rằng thêm cuối cũng O(1) trên danh sách đơn bất biến.** Phải copy tiền tố nếu không dùng cấu trúc khác.
10. **Cho rằng cập nhật chỉ số bất kỳ O(1).** Phải đi từ đầu tới vị trí đó.
11. **Nhầm `tail_of` với con trỏ tới nút cuối.** Trong functional list, tail là **phần còn lại sau head**.
12. **Quên xử lý danh sách rỗng** ở `head/pop/remove/update`.
13. **Dùng `reversed(generator)` trên generator không hỗ trợ truy cập ngược.** Cần materialize hoặc thuật toán khác.
14. **Dùng đệ quy cho một danh sách rất sâu** rồi không tính giới hạn call stack.
15. **Chỉ đọc số nút logic của từng gốc rồi cộng tất cả.** Đếm lặp đuôi dùng chung.
16. **Giữ toàn bộ lịch sử vô hạn mà không tính tổng nút mới.** Bộ nhớ vẫn tăng.
17. **Bỏ gốc cũ rồi tin các nút của nó chắc chắn được thu hồi ngay.** Chúng có thể được phiên bản khác chia sẻ.
18. **Cho rằng `frozen=True` làm list payload bất biến sâu.** Alias tới list vẫn có thể sửa.
19. **Cho rằng immutable tự mang lại thread safety toàn hệ thống.** Công bố head và phối hợp writer cần hợp đồng riêng.
20. **Dùng danh sách linked list immutable cho workload truy cập chỉ số rất thường xuyên** mà không so với tuple/vector.
21. **Tưởng structural sharing tự tạo một thuật toán merge các nhánh.** Merge có chính sách riêng.
22. **Không kiểm thử phiên bản cũ sau thao tác mới.** Không phát hiện lỗi viết vào nút cũ.
23. **Bỏ qua trường hợp update no-op.** Có thể tạo các nút dư nếu không kiểm tra giá trị bằng nhau.
24. **Nhầm shallow copy với chia sẻ đuôi an toàn.** Cần xác định rõ bất biến của nút và phần tử.

## 34. Bài tập tự luyện

**Bài 1.** Định nghĩa danh sách liên kết đơn bất biến. Khác biệt giữa không sửa nút cũ và không được tạo danh sách mới là gì?

**Bài 2.** Dùng sơ đồ mô tả `v0=[10,20,30]` và `v1=cons(5,v0)`. Có bao nhiêu nút mới?

**Bài 3.** Từ `v0=[10,20]`, tạo `v1=cons(5,v0)`, `v2=cons(7,v0)`. Hai phiên bản mới chia sẻ các nút nào?

**Bài 4.** Vì sao `v1.next is v0` quan trọng hơn việc chỉ kiểm tra `to_list(v1)==[5,10,20]`?

**Bài 5.** Với `v0` là một danh sách không rỗng, `head_value`, `tail_of` và `pop_front` có chi phí thời gian và số nút mới ra sao?

**Bài 6.** Trong stack persistent, tại sao `pop` không cần đặt `old_head.next=None`?

**Bài 7.** Một danh sách ban đầu dài `n=1000`. Nếu thêm đầu `m=100` lần và giữ mọi gốc, có bao nhiêu nút `Link` vật lý được cấp phát tổng cộng?

**Bài 8.** Nếu thay value ở chỉ số `i=3` (đếm từ 0), bản danh sách liên kết bất biến cần tạo bao nhiêu nút mới khi giá trị thực sự đổi?

**Bài 9.** Với `base=[10,20,30,40]`, hãy vẽ bản cập nhật `index=1` thành `99` và chỉ ra phần đuôi được dùng chung.

**Bài 10.** Vì sao không thể sửa `node.value` của nút thứ hai thuộc phiên bản cũ rồi cho rằng đã có phiên bản mới?

**Bài 11.** Giải thích thuật toán `update_at` dùng `path` và tạo lại tiền tố từ phải sang trái. Thời gian và bộ nhớ phụ theo `i`?

**Bài 12.** Khi xóa phần tử đầu, số nút mới là bao nhiêu? Khi xóa phần tử ở chỉ số `i`, cần copy bao nhiêu nút tiền tố?

**Bài 13.** Với `base=[10,20,30,40]`, xóa `index=1`. Kết quả có chia sẻ nút `30`, `40` không? Cần bao nhiêu nút mới?

**Bài 14.** Với `base=[10,20,30,40]`, chèn `25` trước chỉ số `2`. Nêu các nút mới và những nút được chia sẻ.

**Bài 15.** Vì sao chèn cuối bằng `insert_at(base,n,x)` phải tạo `n+1` nút mới, trong khi chèn đầu chỉ một nút?

**Bài 16.** Với `left=[1,2]` và `right=[3,4,5]`, `concat(left,right)` phải copy bao nhiêu nút bên trái? Có thể chia sẻ những nút nào?

**Bài 17.** Khi `concat(left,None)`, có thể trả chính `left` không? Vì sao đây là tối ưu đúng?

**Bài 18.** Đảo danh sách `[1,2,3]` mà không sửa nút cũ cần tạo bao nhiêu nút mới trong hiện thực `reversed_list`?

**Bài 19.** Nếu hai danh sách có `to_list(a)==to_list(b)` nhưng `a is not b`, điều đó có chứng minh chúng không dùng chung **bất kỳ** nút nào không?

**Bài 20.** Viết hàm đếm số nút vật lý phân biệt qua một tập gốc, không đếm lặp các đuôi dùng chung.

**Bài 21.** Tại sao một nút `@dataclass(frozen=True)` chứa `list[int]` vẫn có thể làm lịch sử điểm thay đổi sau khi tạo?

**Bài 22.** Đề xuất cách làm cho payload `list[int]` ổn định khi đưa vào nút persistent.

**Bài 23.** So sánh `(x,)+tuple_old` và `cons(x,head_old)` về thời gian/bộ nhớ khi thêm đầu.

**Bài 24.** Vì sao danh sách đơn persistent phù hợp làm stack hơn làm queue FIFO với enqueue ở cuối?

**Bài 25.** Phân biệt tổng số nút logic khi cộng độ dài các phiên bản với số nút vật lý phân biệt còn được tham chiếu.

**Bài 26.** Một hệ thống giữ nhiều phiên bản từ hai writer. Tail sharing có tự quyết định nhánh nào được công bố làm bản hiện hành không?

<details>
<summary>Đáp án và gợi ý</summary>

1. Nút đã tạo không được sửa `value/next` theo hợp đồng; có thể tạo nút mới rồi trả head mới đại diện cho danh sách logic khác.
2. Tạo một nút `5` với `next=v0`. Các nút `10,20,30` được chia sẻ; đúng **1 nút mới**.
3. Cả `v1` và `v2` cùng dùng lại hai nút `10` và `20` của `v0`, mỗi nhánh chỉ tạo một nút đầu.
4. `is` chứng minh dùng **chính đối tượng nút cũ**; `to_list` chỉ chứng minh bằng nhau về nội dung.
5. Cả ba `O(1)` thời gian, không tạo nút mới cho head/tail/pop; `pop` trả giá trị đầu cùng con trỏ đuôi.
6. Sửa `old_head.next` sẽ làm trạng thái của phiên bản cũ thay đổi. `pop` chỉ cần trả `old_head.next` làm head của trạng thái mới.
7. Ban đầu `1000` nút, thêm đầu `100` lần mỗi lần một nút ⇒ **1100 nút vật lý** nếu tính mọi nút đã tạo và các phiên bản vẫn giữ.
8. **4 nút mới**: các nút ở chỉ số `0,1,2,3` được tạo lại; đuôi từ chỉ số `4` được chia sẻ.
9. Bản mới `[10',99,30,40]`. Tạo `10'` và `99`; dùng chung nút `30` và `40`.
10. Vì cả phiên bản cũ và mới có thể cùng trỏ tới nút đó. Sửa nút tại chỗ làm thay đổi bản cũ, trái hợp đồng persistent.
11. Đi tới vị trí và lưu `i` nút tiền tố, tạo nút thay rồi xây lại tiền tố bằng `reversed(path)`. Thời gian `Θ(i+1)`, bộ nhớ phụ `O(i)` và `i+1` nút mới khi đổi giá trị.
12. Xóa đầu trả `head.next`, **0 nút mới**. Xóa ở chỉ số `i` tạo lại **`i` nút tiền tố**.
13. Kết quả `[10',30,40]`, dùng chung đúng nút `30` và `40`. Tạo **1 nút** `10'`.
14. Nút mới `10',20',25`; phần đuôi `30,40` được chia sẻ.
15. Mọi nút cũ đều cần liên kết tới nút/bản kế tiếp mới khi thêm cuối, nên phải tạo lại tiền tố dài `n` cộng nút cuối mới. Chèn đầu không thay đổi liên kết cũ.
16. Sao chép **2 nút** của `left`, nối bản cuối mới tới **chính nút đầu của `right`**, chia sẻ cả `3,4,5`.
17. Có. Ghép thêm danh sách rỗng không đổi nội dung hay liên kết; trả cùng tham chiếu tiết kiệm cấp phát.
18. Tạo **3 nút mới** và giữ nguyên ba nút cũ; thông thường không chia sẻ nút cũ vì hướng liên kết phải đổi.
19. Không. Hai gốc khác nhau **có thể có chung một đuôi**. Muốn kết luận không chia sẻ nút nào, phải kiểm tra danh tính những nút reachable hoặc bộ đếm phù hợp.
20. Duyệt các gốc và lưu `id(node)` vào `seen`; gặp lại object thì bỏ qua, chỉ đếm một lần.
21. `frozen=True` ngăn gán lại thuộc tính nút nhưng list bên trong vẫn có thể bị `append` qua alias khác.
22. Ví dụ chuyển `list[int]` thành `tuple[int,...]` khi tạo nút, với giả thiết các phần tử `int` bất biến và không lộ đường sửa tới container.
23. Nối tuple tạo dãy mới và sao chép `n` tham chiếu, `O(n)`; `cons` tạo một nút mới trỏ tới head cũ, `O(1)`.
24. Stack push/pop đều ở đầu nên `O(1)`; queue FIFO muốn enqueue cuối có thể cần `O(n)` nếu chỉ dùng một linked list đơn bất biến.
25. Tổng độ dài phiên bản **đếm lặp nút đuôi** được chia sẻ. Số nút vật lý chỉ đếm mỗi object một lần, thường thấp hơn nhiều.
26. Không. Dữ liệu của từng nhánh có thể đúng và bất biến, nhưng chọn head hiện hành và xử lý xung đột cần cơ chế đồng bộ/chính sách riêng.

</details>

## Ghi nhớ

**Danh sách liên kết đơn bất biến đặc biệt hiệu quả khi nhiều phiên bản có cùng phần đuôi.** Thao tác `cons(x,tail)` chỉ tạo **một nút mới** và trỏ tới **chính phần đuôi cũ**, đạt **`O(1)` thời gian/bộ nhớ mới**; `head`, `tail` và `pop_front` cũng `O(1)`. Khi sửa/chèn/xóa ở giữa, phải **sao chép các nút tiền tố cần thay liên kết** và có thể **dùng chung đuôi phía sau**, nên chi phí tăng theo **vị trí cập nhật**. Thêm cuối vào linked list đơn bất biến thường tốn **`Θ(n)`**, không phải `O(1)`. Nếu giữ nhiều phiên bản, hãy đếm **nút vật lý phân biệt** thay vì cộng độ dài logic, và bảo đảm **nút lẫn payload được chia sẻ có ngữ nghĩa ổn định**. Chọn linked list persistent cho stack, undo và thao tác thêm/bỏ đầu; khi cần truy cập chỉ số nhanh hoặc cập nhật cuối thường xuyên, hãy cân nhắc cấu trúc khác phù hợp hơn.

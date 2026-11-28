# Cấu trúc bền vững (persistent): giữ phiên bản cũ sau cập nhật

Một hệ thống quản lý bài tập lưu trạng thái danh sách công việc và cần hỗ trợ **hoàn tác**, xem **lịch sử thay đổi**, hoặc tạo **nhánh thử nghiệm** từ một thời điểm trước đó. Với một danh sách hay cây mutable thông thường, thao tác cập nhật thường sửa ngay cấu trúc đang dùng. Nếu chỉ giữ một tham chiếu tới đối tượng cũ, ta **không có một phiên bản lịch sử độc lập**: tham chiếu ấy có thể nhìn thấy trạng thái đã bị thay đổi.

**Cấu trúc dữ liệu bền vững** (*persistent data structure*) giải quyết vấn đề bằng một hợp đồng rõ ràng: **cập nhật tạo ra một phiên bản mới, còn những phiên bản cũ vẫn truy cập được và giữ nguyên ngữ nghĩa của chúng**. Để tránh sao chép toàn bộ dữ liệu, các phiên bản thường **chia sẻ những nút con không thay đổi** (*structural sharing*) và chỉ tạo mới phần cấu trúc thật sự bị ảnh hưởng.

Trong chương **Bất biến và phiên bản** của module **Cấu trúc dữ liệu**, bài này giải thích khái niệm persistent, phân biệt các dạng quản lý phiên bản, so sánh thao tác sửa tại chỗ với thao tác trả phiên bản mới, xây **stack/danh sách liên kết persistent** và **BST persistent** bằng Python, chứng minh bất biến, kiểm tra việc chia sẻ nút, và phân tích độ phức tạp thời gian – bộ nhớ để lựa chọn cấu trúc phù hợp.

## 1. Persistent nghĩa là giữ được phiên bản cũ

Với một cấu trúc mutable:

```python
tasks = ["Đọc bài", "Làm bài"]
old = tasks

tasks.append("Nộp bài")

assert old is tasks
assert old == ["Đọc bài", "Làm bài", "Nộp bài"]
```

`old` là **alias** cùng trỏ tới một list; nó **không** giữ trạng thái trước `append`.

Một cấu trúc persistent thường có cách dùng khác:

```text
v0 = empty_structure()
v1 = update(v0, thao_tác_A)
v2 = update(v1, thao_tác_B)

read(v0)  → trạng thái ban đầu
read(v1)  → chỉ có thay đổi A
read(v2)  → có A và B
```

Điểm mấu chốt:

- `update(v1, ...)` **không sửa `v1`**.
- Hàm trả về một **đại diện phiên bản mới**: có thể là gốc cây, đầu danh sách hoặc đối tượng chứa gốc.
- Các thao tác **đọc** vẫn có thể được gọi với phiên bản cũ.
- Những nút không bị ảnh hưởng **có thể chia sẻ** giữa các phiên bản, nếu việc chia sẻ an toàn.
- Nếu một cập nhật **không làm thay đổi trạng thái logic**, hiện thực có thể trả **chính đối tượng phiên bản cũ**.

Chữ *persistent* ở đây **không đồng nghĩa với lưu bền trên ổ đĩa** (*durable storage*). Một cây persistent chỉ tồn tại trong RAM vẫn có ngữ nghĩa giữ phiên bản; nếu tiến trình tắt mà không lưu dữ liệu, các phiên bản vẫn có thể mất.

## 2. Phân biệt tính bất biến của nút với tính bền vững của phiên bản

Hai khái niệm liên quan nhưng không trùng nhau:

| Khái niệm | Điều bảo đảm chính |
| --- | --- |
| **Immutable object** | Đối tượng không bị sửa tại chỗ sau khi tạo, trong phạm vi hợp đồng |
| **Persistent data structure** | Các phiên bản cũ vẫn có thể được dùng sau khi tạo phiên bản mới |
| **Structural sharing** | Nhiều phiên bản tái sử dụng các phần cấu trúc không đổi |
| **Snapshot** | Một ảnh chụp trạng thái tại thời điểm xác định, theo hợp đồng nhất quán |
| **Read-only view** | Không sửa được qua giao diện đọc, nhưng dữ liệu nguồn có thể vẫn đổi |

Một tuple Python là immutable ở cấp ngoài. Biểu thức `v1 = v0 + (item,)` tạo tuple mới và giữ được `v0`, nên có thể dùng tuple để mô phỏng phiên bản. Tuy nhiên, mỗi lần nối phải tạo tuple mới và sao chép các tham chiếu: **không có nghĩa cách này hiệu quả cho mọi kích thước**.

Một cấu trúc persistent thường thiết kế **cấu trúc nút bất biến** và **phương thức cập nhật trả gốc mới**, nhằm vừa duy trì phiên bản cũ vừa kiểm soát chi phí cấp phát.

### Điều kiện về phần tử bên trong

Nếu một nút bất biến chứa **list mutable** và nhiều phiên bản cùng chia sẻ list ấy, việc sửa list có thể làm **nội dung quan sát của phiên bản cũ đổi** dù mọi liên kết nút vẫn giữ nguyên. Bởi vậy, muốn lịch sử đáng tin cậy, phải xác định rõ **payload có bất biến sâu hoặc quyền sửa được kiểm soát hay không**.

## 3. Vì sao cần nhiều phiên bản?

Một số nhu cầu điển hình:

1. **Undo/redo:** giữ các trạng thái trước để quay về mà không xây lại toàn bộ từ đầu.
2. **Lịch sử cấu hình:** tra cứu một khóa ở phiên bản được chốt tuần trước.
3. **Thử nghiệm nhánh:** từ phiên bản đang chạy, tạo nhánh mô phỏng mà không đụng trạng thái chính.
4. **Đọc snapshot:** một lượt đọc dùng một gốc nhất quán trong khi hệ thống chuẩn bị phiên bản tiếp theo.
5. **Kiểm thử:** so trực tiếp trạng thái trước và sau thao tác, bảo đảm cập nhật không ảnh hưởng dữ liệu cũ.
6. **Thuật toán ngoại tuyến:** trả lời câu hỏi “cấu trúc ở thời điểm `t` có gì?” bằng nhiều gốc phiên bản.
7. **Ghi nhận thay đổi:** dùng phiên bản cũ và mới để tính diff, với điều kiện có thuật toán diff phù hợp.

Ví dụ, ứng dụng học tập có thể giữ danh sách khóa học tại thời điểm mở đăng ký (`v0`), sau khi một học phần mới được thêm (`v1`), và sau khi sửa tên học phần (`v2`). Nếu `v0` được giữ đúng, báo cáo lịch sử có thể đọc lại mà không bị ảnh hưởng bởi cập nhật sau này.

**Không nên đánh đồng** tính persistent với chức năng audit hoàn chỉnh: phiên bản trong RAM chưa tự cung cấp tính xác thực, người sửa, timestamp, phân quyền, sao lưu, giao dịch hay bảo quản lâu dài.

## 4. Ba mức persistence thường gặp

Các tài liệu thuật toán phân biệt những khả năng sửa và truy cập phiên bản:

| Kiểu | Đọc phiên bản cũ? | Tạo cập nhật từ phiên bản nào? |
| --- | --- | --- |
| **Ephemeral (không persistent)** | Thường không giữ được trạng thái cũ độc lập | Chỉ sửa trạng thái đang có |
| **Partially persistent** | **Có** | Chỉ được cập nhật từ **phiên bản mới nhất** |
| **Fully persistent** | **Có** | Có thể cập nhật từ **bất kỳ phiên bản đã giữ** |
| **Confluently persistent** | **Có** | Có thể tạo phiên bản mới bằng cách **kết hợp nhiều phiên bản** theo quy tắc riêng |

### Partially persistent

```text
v0 ──update──► v1 ──update──► v2 ──update──► v3

Được đọc: v0, v1, v2, v3
Được cập nhật tiếp: v3
```

Ví dụ lịch sử các lần chốt cấu hình nối tiếp nhau: phiên bản cũ chỉ để xem, không dùng làm điểm xuất phát cho một nhánh mới.

### Fully persistent

```text
                    ┌──update──► v3
v0 ──update──► v1 ─┤
                    └──update──► v4
                     \
                      (được phép tạo nhánh từ v1)

v0 cũng có thể tạo nhánh khác.
```

Ta có thể lấy `v1` làm đầu vào để tạo `v4` ngay cả sau khi đã có `v2`, `v3`. Kết quả là một **đồ thị phiên bản phân nhánh** thay vì chỉ một chuỗi tuyến tính.

### Confluently persistent

Một mức mạnh hơn cho phép **kết hợp** hai phiên bản thành một phiên bản mới. Đây không phải chỉ là nối con trỏ tùy ý: phải quy định **merge dữ liệu, xung đột khóa và bất biến cấu trúc**. Những ví dụ path copying ở bài này chủ yếu minh họa **full persistence**, **không tự cung cấp thuật toán merge**.

## 5. Mô hình phiên bản bằng gốc riêng

Trong nhiều cấu trúc dạng cây, một phiên bản có thể đại diện bằng **một tham chiếu tới nút gốc**:

```text
roots[0] ──► root_v0
roots[1] ──► root_v1
roots[2] ──► root_v2
```

Khi cập nhật:

```text
new_root = update(old_root, key, value)
roots.append(new_root)
```

Không cần có một “cây phiên bản” tách biệt chứa toàn bộ dữ liệu cho từng thời điểm. Các gốc có thể tham chiếu tới những cây con giống hệt nhau.

### Hai lớp đồ thị

Cần phân biệt:

- **Đồ thị phiên bản:** mỗi đỉnh là một phiên bản, cạnh biểu thị phiên bản nào được dùng để tạo phiên bản mới.
- **Đồ thị các nút dữ liệu:** mỗi gốc phiên bản dẫn tới một cấu trúc logic; hai gốc có thể dùng chung những nút bất biến.

Một BST đơn lẻ vẫn có cấu trúc cây bình thường. Nhưng **toàn bộ các nút được nhìn qua nhiều gốc phiên bản** có thể tạo thành một **DAG** (*directed acyclic graph*: đồ thị có hướng không chu trình), vì nhiều gốc/cây con cùng tham chiếu các nút chung.

**Chia sẻ nút không đồng nghĩa có chu trình trong một phiên bản.** Các liên kết dữ liệu phải được thiết kế để không làm sai dạng cây hoặc danh sách của mỗi phiên bản.

## 6. Ví dụ cơ bản nhất: stack persistent bằng danh sách liên kết

Một stack có thao tác:

- `push(top, value)`: đưa phần tử lên đỉnh.
- `pop(top)`: lấy giá trị ở đỉnh và chuyển tới phần còn lại.
- `peek(top)`: đọc giá trị ở đỉnh.

Với stack mutable, `push` và `pop` sửa biến/đối tượng đang giữ đỉnh. Với một **stack persistent**, ta coi **nút đầu bất biến** và cập nhật chỉ tạo ra **gốc mới**.

```text
v0 = empty

v1:
  top ──► [10] ──► None

v2 = push(v1, 20):
  top ──► [20] ──► [10] ──► None
                    ▲
                    └── v1 vẫn trỏ tới [10]
```

Không phải sao chép nút `10` khi thêm `20`. Vì các nút cũ không bị sửa, cả hai phiên bản an toàn chia sẻ đuôi.

## 7. Python: cài stack persistent tự chứa

Ta sử dụng `@dataclass(frozen=True)` để ngăn việc gán lại các trường nút theo API thông thường, và chỉ lưu `int` làm phần tử (bất biến).

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class StackNode:
    value: int
    next: "StackNode | None" = None


def push(top, value):
    """Trả phiên bản mới có value trên đỉnh."""
    return StackNode(value, top)


def pop(top):
    """Trả (giá_trị_đỉnh, gốc_còn_lại), không sửa top."""
    if top is None:
        raise IndexError("pop from empty persistent stack")
    return top.value, top.next


def peek(top):
    if top is None:
        raise IndexError("peek from empty persistent stack")
    return top.value


def stack_values(top):
    result = []
    node = top
    while node is not None:
        result.append(node.value)
        node = node.next
    return result


s0 = None
s1 = push(s0, 10)
s2 = push(s1, 20)
s3 = push(s2, 30)

assert stack_values(s0) == []
assert stack_values(s1) == [10]
assert stack_values(s2) == [20, 10]
assert stack_values(s3) == [30, 20, 10]

assert s3.next is s2
assert s2.next is s1

top_value, rest = pop(s3)
assert top_value == 30
assert rest is s2
assert stack_values(s3) == [30, 20, 10]
```

### Vì sao pop không xóa nút cũ?

`pop` trả `top.next` làm đầu stack của **một trạng thái khác**; nó không làm `top.next = None`. Vì vậy, cả `s3` và `s2` đều còn hợp lệ.

Nếu chẳng ai giữ `s3` nữa, nút `30` có thể trở thành đối tượng không còn được tham chiếu và được bộ quản lý bộ nhớ thu hồi. **Persistence không bắt buộc phải giữ vô hạn mọi phiên bản**; nó chỉ bảo đảm phiên bản **còn được giữ** không bị thao tác mới phá.

## 8. Tạo nhánh từ một phiên bản stack cũ

Full persistence cho phép tiếp tục cập nhật `s1` dù `s3` đã tồn tại:

```python
s_branch = push(s1, 99)

assert stack_values(s_branch) == [99, 10]
assert stack_values(s1) == [10]
assert stack_values(s2) == [20, 10]
assert stack_values(s3) == [30, 20, 10]

assert s_branch.next is s1
assert s2.next is s1
```

Sơ đồ:

```text
       s3 → [30] → [20] ─┐
                  s2    │
                        ▼
                        [10] → None
                         ▲
                  s1 ───┤
                        │
     s_branch → [99] ────┘
```

Hai nhánh `[20,10]` và `[99,10]` chia sẻ nút `10`. Không nhánh nào phải ghi đè nhánh kia.

### Chi phí của stack persistent này

| Thao tác | Thời gian | Nút mới |
| --- | --- | --- |
| `push` | **`O(1)`** | **1** |
| `pop` | **`O(1)`** | **0** |
| `peek` | **`O(1)`** | **0** |
| Duyệt `n` phần tử | `O(n)` | 0 (chưa tính list đầu ra) |
| Tìm theo chỉ số `i` từ đỉnh | `O(i+1)` | 0 |

Danh sách liên kết persistent phù hợp **thêm/bỏ đầu**, nhưng **không** cho phép truy cập ngẫu nhiên theo chỉ số nhanh như mảng.

## 9. Bẫy cơ bản: frozen node vẫn có thể chứa payload mutable

Đoạn mã trên dùng `int`. Nếu phần tử là `list`, chỉ đóng băng trường tham chiếu chưa đủ để giữ nội dung lịch sử.

```python
@dataclass(frozen=True)
class LooseNode:
    value: list[int]
    next: "LooseNode | None" = None


external = [8, 9]
old = LooseNode(external)
new = LooseNode([10], old)

external.append(5)

assert old.value == [8, 9, 5]
assert new.next.value == [8, 9, 5]
```

Không có thao tác sửa `old.next` hay `old.value` thành một tham chiếu mới. Nhưng **list được tham chiếu** bị sửa.

### Chọn một hợp đồng rõ ràng

Với lịch sử điểm số, có thể chuyển mỗi list điểm thành tuple ngay khi đưa vào nút:

```python
@dataclass(frozen=True)
class GradesNode:
    value: tuple[int, ...]
    next: "GradesNode | None" = None


input_grades = [8, 9]
stable_old = GradesNode(tuple(input_grades))
stable_new = GradesNode((10,), stable_old)

input_grades.append(5)

assert stable_old.value == (8, 9)
assert stable_new.next is stable_old
```

**Chia sẻ an toàn** đòi hỏi phần được chia sẻ có ngữ nghĩa không đổi, không chỉ có một nhãn kiểu là “immutable”.

## 10. Từ linked list tới cây: path copying

Với stack liên kết, thêm đầu chỉ tạo một nút mới. Nhưng với **cây**, cập nhật một lá ở sâu thường buộc ta sửa liên kết `left` hoặc `right` của một số tổ tiên để nối tới phần mới.

Nếu **không được sửa nút cũ**, ta làm như sau:

1. Tìm vị trí cần thay đổi theo quy tắc của cấu trúc.
2. Tạo nút mới tại vị trí thay đổi.
3. Trên đường đi **từ vị trí đó về gốc**, tạo **bản mới của từng tổ tiên** và nối nó tới cây con mới.
4. **Giữ nguyên tham chiếu** tới các cây con nằm ngoài đường cập nhật.
5. Trả **gốc mới**, không sửa gốc cũ.

Kỹ thuật này được gọi là **path copying** (*sao chép đường đi*).

### Ví dụ với BST

Phiên bản `v0`:

```text
                  40 (A)
                 /      \
             20 (B)    60 (C)
                      /      \
                  50 (D)   70 (E)
```

Chèn khóa `55` vào cây con phải của `50`. Đường tìm là:

```text
40 → 60 → 50 → chỗ con phải rỗng
```

Phiên bản `v1`:

```text
                  40' (A')
                 /       \
             20 (B)     60' (C')
                       /       \
                    50' (D')  70 (E)
                       \
                        55 (F)
```

Các nút `40'`, `60'`, `50'` và `55` là **đối tượng mới**. Nút `20` và `70` được **dùng chung bằng đúng tham chiếu cũ**.

Ở phiên bản `v0`, `40.right` vẫn trỏ tới nút `60` ban đầu; nó không bị gán sang `60'`. Vì vậy, `v0` không thấy khóa `55`.

## 11. Vì sao sao chép chỉ đường đi là đủ?

Trong BST khóa duy nhất, việc chèn một khóa `x` chọn **một đường duy nhất** bằng so sánh:

```text
x < node.key  → đi trái
x > node.key  → đi phải
x == node.key → cập nhật payload của khóa hiện có
```

Chỉ các nút trên đường này cần thay đổi tham chiếu tới cây con mới hoặc payload tại nút đích.

Với mỗi tổ tiên trên đường:

- **Một con** dẫn tới phần cấu trúc đã thay đổi → nhận tham chiếu mới.
- **Con kia** không đổi → có thể chia sẻ.
- Khóa và payload của tổ tiên không đổi → được chép lại nguyên giá trị vào đối tượng nút mới.

Bởi vậy, với chiều cao cây `h`, số nút mới được tạo cho một lần chèn/cập nhật bằng path copying là **`O(h)`** (thường là một nút mới cho mỗi mức trên đường, cộng nút được thêm).

### Điều không được làm

```python
# Sai trong persistent tree:
old_parent.right = new_subtree

# Gán trên sẽ làm phiên bản cũ cùng dùng old_parent bị thay đổi.
```

Quy tắc đúng là tạo một **parent mới** có `right=new_subtree` và `left` giữ lại tham chiếu cũ.

## 12. Python: biểu diễn nút BST bất biến

Ta xây BST-map có khóa nguyên **phân biệt**, giá trị là `str` hoặc `None`. Các giá trị này được dùng như dữ liệu bất biến trong ví dụ. Việc thêm khóa trùng nghĩa là **cập nhật giá trị tại cùng khóa**, không tạo nút thứ hai.

```python
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class PNode:
    key: int
    value: str | None
    left: "PNode | None" = None
    right: "PNode | None" = None


def find(root, key):
    """Trả (found, value), kể cả khi value=None."""
    current = root

    while current is not None:
        if key == current.key:
            return True, current.value

        if key < current.key:
            current = current.left
        else:
            current = current.right

    return False, None


def inorder_keys(root):
    """Sinh khóa theo thứ tự tăng, không sửa cây."""
    stack = []
    current = root

    while current is not None or stack:
        while current is not None:
            stack.append(current)
            current = current.left

        current = stack.pop()
        yield current.key
        current = current.right
```

**Điều kiện của cây:** mọi khóa trong toàn bộ cây con trái nhỏ hơn `node.key`, mọi khóa trong cây con phải lớn hơn `node.key`. Các phép so sánh dùng thứ tự số nguyên thông thường.

Hàm `find` trả **cờ tồn tại** và giá trị để tránh nhập nhằng giữa “khóa vắng mặt” với “khóa có giá trị hợp lệ bằng `None`”.

## 13. Python: chèn/cập nhật trả về gốc mới

Ở mỗi nhánh, lời gọi đệ quy trả về **gốc của cây con phiên bản mới**. Ta dùng `dataclasses.replace` để tạo nút mới có các trường cũ, ngoại trừ phần cần thay đổi.

```python
def persistent_put(root, key, value):
    """Trả (new_root, inserted), không sửa root đầu vào."""
    if root is None:
        return PNode(key, value), True

    if key < root.key:
        new_left, inserted = persistent_put(
            root.left, key, value
        )

        if new_left is root.left:
            return root, inserted

        return replace(root, left=new_left), inserted

    if key > root.key:
        new_right, inserted = persistent_put(
            root.right, key, value
        )

        if new_right is root.right:
            return root, inserted

        return replace(root, right=new_right), inserted

    # Khóa đã tồn tại. Nếu giá trị không đổi, giữ nguyên nút.
    if root.value == value:
        return root, False

    return replace(root, value=value), False


def build_by_put(items):
    root = None
    for key, value in items:
        root, _ = persistent_put(root, key, value)
    return root
```

### Ý nghĩa của cờ inserted

- `True` khi trước thao tác **chưa tồn tại khóa** và nay có thêm một nút logic.
- `False` khi khóa đã tồn tại, bất kể giá trị có được cập nhật hay không.

Một lần **cập nhật value** không tăng số khóa của BST. Nếu `key` có sẵn và `value` bằng giá trị cũ, mã trả **chính tham chiếu root cũ**, giúp không cấp phát nút khi không có thay đổi logic.

### Những điều cần tránh

- Không gán `root.left = ...` hoặc `root.value = ...`.
- Không sửa bất kỳ nút cũ nào được chia sẻ.
- Không thay đổi thứ tự so sánh giữa các phiên bản.
- Không dùng payload mutable mà không có chính sách snapshot phù hợp.

## 14. Thử tạo, lưu và so sánh các phiên bản BST

Tạo cây `v0` theo sơ đồ phần 10:

```python
v0 = build_by_put([
    (40, "v40"),
    (20, "v20"),
    (60, "v60"),
    (50, "v50"),
    (70, "v70"),
])

v1, inserted = persistent_put(v0, 55, "v55")

assert inserted is True

assert list(inorder_keys(v0)) == [20, 40, 50, 60, 70]
assert list(inorder_keys(v1)) == [20, 40, 50, 55, 60, 70]

assert find(v0, 55) == (False, None)
assert find(v1, 55) == (True, "v55")
```

### Xác nhận các nút thực sự được chia sẻ

```python
# Gốc phải mới vì đường chèn đi qua gốc:
assert v1 is not v0

# Cây con trái của gốc không đổi, được dùng chung:
assert v1.left is v0.left

# Nút 60 nằm trên đường thay đổi, phải là đối tượng mới:
assert v1.right is not v0.right

# Nút 70 ngoài đường chèn, được dùng chung:
assert v1.right.right is v0.right.right

# Nút 50 nằm trên đường chèn, nên là bản mới:
assert v1.right.left is not v0.right.left

# Cây cũ không bị chèn 55:
assert v0.right.left.right is None
assert v1.right.left.right.key == 55
```

**Dùng `is` thay cho `==` khi kiểm tra chia sẻ nút:** `is` kiểm tra cùng **đối tượng**; `==` của dataclass có thể chỉ phản ánh hai cây có giá trị bằng nhau, không cho biết chúng có chung nút hay không.

## 15. Tạo nhánh mới từ một phiên bản cũ

Không cần cập nhật từ `v1`. Ta có thể dùng **`v0` làm điểm xuất phát** cho một nhánh khác:

```python
v_branch, added = persistent_put(v0, 10, "v10")
assert added is True

assert list(inorder_keys(v0)) == [20, 40, 50, 60, 70]
assert list(inorder_keys(v1)) == [20, 40, 50, 55, 60, 70]
assert list(inorder_keys(v_branch)) == [10, 20, 40, 50, 60, 70]

# v_branch không phải hậu duệ của v1:
assert find(v_branch, 55) == (False, None)
assert find(v1, 10) == (False, None)

# Nhánh phải không đổi khi chèn khóa 10 vào nhánh trái:
assert v_branch.right is v0.right
```

Sơ đồ quan hệ phiên bản:

```text
                    v1: chèn 55
                   /
v0: trạng thái gốc
                   \
                    v_branch: chèn 10
```

Đây là **fully persistent** ở mức cập nhật một gốc bất kỳ: nhiều bản tiếp diễn có thể tồn tại song song và không ghi đè nhau.

### Cách lưu các gốc

```python
versions = {
    "base": v0,
    "add-55": v1,
    "experiment-add-10": v_branch,
}

assert find(versions["base"], 55) == (False, None)
assert find(versions["add-55"], 55) == (True, "v55")
```

Dictionary `versions` trong ví dụ **có thể thay đổi**: việc gán/xóa tên phiên bản không làm thay đổi nội dung của các cây bất biến được tham chiếu. Lớp quản lý phiên bản và lớp dữ liệu persistent có **hai hợp đồng riêng**.

## 16. Cập nhật cùng khóa không làm thay đổi phiên bản cũ

```python
v2, inserted = persistent_put(v1, 20, "updated-20")

assert inserted is False
assert find(v1, 20) == (True, "v20")
assert find(v2, 20) == (True, "updated-20")

assert v2 is not v1
assert v2.right is v1.right

# Không có thay đổi logic: có thể tái sử dụng hoàn toàn v2.
unchanged, inserted = persistent_put(v2, 20, "updated-20")
assert inserted is False
assert unchanged is v2

# Giá trị None là hợp lệ; phân biệt rõ với khóa vắng.
with_none, inserted = persistent_put(v2, 90, None)
assert inserted is True
assert find(with_none, 90) == (True, None)
assert find(v2, 90) == (False, None)
```

Nếu giá trị đầu vào là một đối tượng mutable, phép so sánh `==` chỉ cho biết kết quả bằng nhau ở thời điểm đó; nó **không** bảo đảm giá trị ấy sẽ không bị sửa về sau. Trong bài, ta chỉ dùng `str` hoặc `None` để giữ ví dụ tập trung vào ngữ nghĩa phiên bản.

## 17. Xóa persistent: không được tháo liên kết của nút cũ

Trong BST mutable, ta có thể xóa lá bằng cách đặt `parent.left = None`; xóa nút một con bằng cách cho cha trỏ thẳng tới con; xóa nút hai con bằng kế nhiệm/tiền nhiệm rồi tháo nút thay thế.

Trong **BST persistent**, các ý tưởng thứ tự đó vẫn đúng, nhưng thao tác **thay liên kết** phải tạo ra **nút mới**, không sửa nút của phiên bản cũ.

### Ba tình huống xóa

| Nút cần xóa | Cấu trúc phiên bản mới |
| --- | --- |
| **Lá** | Trả `None` ở vị trí nút ấy, dựng lại các tổ tiên trên đường |
| **Một con** | Trả **gốc cây con còn lại**, dựng lại các tổ tiên cần đổi |
| **Hai con** | Thay nút bằng payload kế nhiệm/tiền nhiệm và dựng lại những nhánh liên quan |

Với hai con, một cách dễ chứng minh là:

1. Chọn **kế nhiệm** `min(root.right)`.
2. Tạo **nút gốc mới** mang cặp `(key,value)` của kế nhiệm.
3. Cây trái của gốc mới có thể dùng chung với cây trái cũ.
4. Cây phải của gốc mới là **phiên bản mới của cây con phải sau khi bỏ nút kế nhiệm**.
5. Không sửa cây cũ.

Hàm hỗ trợ xóa nút nhỏ nhất của cây con cũng phải persistent.

## 18. Python: lấy minimum và xóa bằng path copying

Đặt các hàm sau cùng tệp với `PNode` và `persistent_put`:

```python
def pop_min_persistent(root):
    """root khác None.

    Trả (min_node_cũ, new_root_khi_đã_bỏ_min).
    Không sửa bất kỳ nút nào của cây đầu vào.
    """
    if root.left is None:
        return root, root.right

    minimum, new_left = pop_min_persistent(root.left)
    return minimum, replace(root, left=new_left)


def persistent_delete(root, key):
    """Trả (new_root, removed); giữ nguyên phiên bản cũ."""
    if root is None:
        return None, False

    if key < root.key:
        new_left, removed = persistent_delete(root.left, key)
        if not removed:
            return root, False
        return replace(root, left=new_left), True

    if key > root.key:
        new_right, removed = persistent_delete(root.right, key)
        if not removed:
            return root, False
        return replace(root, right=new_right), True

    # Đã tìm được khóa cần xóa.
    if root.left is None:
        return root.right, True

    if root.right is None:
        return root.left, True

    # Hai con: dùng kế nhiệm trong cây con phải.
    successor, new_right = pop_min_persistent(root.right)

    return PNode(
        key=successor.key,
        value=successor.value,
        left=root.left,
        right=new_right,
    ), True
```

### Vì sao vẫn giữ được BST?

Nút kế nhiệm có khóa nhỏ nhất trong cây con phải, nên nó lớn hơn mọi khóa của cây con trái và không lớn hơn các khóa còn lại của cây con phải. Sau khi bỏ đúng nút kế nhiệm ở chỗ cũ, gốc mới mang khóa kế nhiệm đứng đúng giữa hai cây con.

Các nút tạo mới nằm trên **đường tìm khóa** và, với trường hợp hai con, **đường tìm kế nhiệm trong cây con phải**. Cả hai đường đều có độ dài tối đa theo chiều cao `h`. Những nhánh khác chỉ giữ lại tham chiếu cũ.

### Không giữ parent pointer mutable kiểu truyền thống

Ví dụ này **không lưu trường `parent`** trong `PNode`. Khi nhiều phiên bản chia sẻ một cây con, **cùng một nút con có thể nằm dưới các nút cha khác nhau tùy phiên bản**. Một trường `parent` đơn nhất trong chính nút được chia sẻ không thể đồng thời trỏ tới hai cha ấy.

Nếu cần đi ngược tổ tiên trong cây persistent, thường dùng **stack đường đi trong iterator**, zipper/đường dẫn gắn với một phiên bản, hoặc thiết kế con trỏ cha theo phiên bản thay vì sửa `parent` của nút dùng chung.

## 19. Kiểm thử xóa: phiên bản cũ phải giữ nguyên

```python
# v1 chứa: 20, 40, 50, 55, 60, 70
deleted_root, removed = persistent_delete(v1, 40)

assert removed is True
assert list(inorder_keys(v1)) == [20, 40, 50, 55, 60, 70]
assert list(inorder_keys(deleted_root)) == [20, 50, 55, 60, 70]

assert find(v1, 40) == (True, "v40")
assert find(deleted_root, 40) == (False, None)
assert find(deleted_root, 55) == (True, "v55")

# Khóa 40 là gốc v1 và có hai con.
assert deleted_root.key == 50
assert deleted_root.left is v1.left

# Chỉ xóa khóa không tồn tại: không tạo phiên bản khác.
same, removed = persistent_delete(v1, 999)
assert removed is False
assert same is v1
```

### Xóa lá và nút có một con

```python
leaf_removed, ok = persistent_delete(v1, 70)
assert ok is True
assert list(inorder_keys(leaf_removed)) == [
    20, 40, 50, 55, 60
]

# Sau khi bỏ 70, cây mới vẫn còn 55 và 50.
assert find(leaf_removed, 55) == (True, "v55")

one_child = PNode(
    10, "ten",
    None,
    PNode(20, "twenty"),
)

promoted, ok = persistent_delete(one_child, 10)
assert ok is True
assert promoted is one_child.right
assert list(inorder_keys(promoted)) == [20]
assert list(inorder_keys(one_child)) == [10, 20]
```

Ở trường hợp nút một con, phiên bản mới có thể dùng **chính cây con cũ** làm gốc; không nhất thiết phải tạo bản sao nút con. Điều này đúng vì nút con không bị sửa và không chứa một con trỏ cha mutable buộc phải cập nhật.

## 20. Kiểm thử bất biến của mọi phiên bản

Một cách kiểm thử thứ tự BST là duyệt in-order và xác nhận khóa tăng nghiêm ngặt. Cách khác truyền cận tổ tiên `(low, high)` cho mỗi nhánh.

Hàm dưới đây kiểm tra đồng thời:

- Cấu trúc không có chu trình hoặc nút xuất hiện hai lần **trong cùng phiên bản**.
- Bất biến BST trên **toàn bộ cây con**.
- Không có khóa trùng ở nhiều nút trong một phiên bản.

```python
def validate_persistent_bst(root):
    seen = set()
    stack = [(root, None, None)]

    while stack:
        node, low, high = stack.pop()
        if node is None:
            continue

        if id(node) in seen:
            return False
        seen.add(id(node))

        if low is not None and not (low < node.key):
            return False
        if high is not None and not (node.key < high):
            return False

        stack.append((node.left, low, node.key))
        stack.append((node.right, node.key, high))

    return True


for version in (
    v0, v1, v2, v_branch,
    with_none, deleted_root, leaf_removed,
):
    assert validate_persistent_bst(version)
```

**Lưu ý về `seen`:** tập này được tạo **mới cho mỗi phiên bản**. Nếu dùng chung một tập `seen` cho nhiều gốc, những nút được structural sharing giữa phiên bản sẽ bị nhận nhầm là lỗi.

Đồ thị nút **giữa nhiều phiên bản** có thể chia sẻ rất nhiều đối tượng; điều bất hợp lệ là khi **một cây logic duy nhất** có chu trình hoặc cùng nút xuất hiện qua hai đường không phù hợp.

## 21. Chứng minh tính đúng của path copying

Ta nêu ba bất biến quan trọng khi cập nhật một BST persistent:

1. **Giữ thứ tự:** mỗi phiên bản mới vẫn thỏa bất biến BST.
2. **Giữ lịch sử:** không có nút thuộc một phiên bản cũ bị sửa tại chỗ.
3. **Đúng thay đổi:** phiên bản mới thêm, cập nhật hoặc xóa **đúng khóa được yêu cầu**, các khóa khác giữ nguyên cặp khóa–giá trị.

### Chèn và cập nhật

**Cơ sở:** nếu cây rỗng, tạo nút chứa khóa mới. BST một nút hợp lệ; không có phiên bản cũ nào bị sửa.

**Bước quy nạp:** với nút có khóa `k`, nếu khóa cần chèn nhỏ hơn `k`, theo bất biến BST, thay đổi chỉ cần xảy ra trong cây con trái. Giả sử lời gọi đệ quy trả cây trái mới đúng và không sửa cây trái cũ. Tạo **nút cha mới** mang khóa `k`, giữ nguyên cây phải cũ và gắn cây trái mới. Vì các khóa trong cây trái mới vẫn nhỏ hơn `k`, bất biến BST được giữ. Phía phải đối xứng.

Nếu khóa đã tồn tại, chỉ cần tạo nút mới mang cùng khóa và giá trị mới, còn hai cây con không đổi; thứ tự BST không bị ảnh hưởng.

Tất cả các nhánh chỉ **tạo đối tượng mới**, nên những gốc cũ vẫn trỏ tới các nút cũ, không bị thay đổi.

### Xóa

Với nút cần xóa:

- **Lá:** trả cây rỗng.
- **Một con:** trả cây con còn lại, vốn là BST hợp lệ.
- **Hai con:** lấy kế nhiệm từ cây con phải. Kế nhiệm lớn hơn mọi khóa bên trái; cây con phải đã bỏ kế nhiệm vẫn chứa các khóa lớn hơn kế nhiệm. Tạo nút mới với khóa và giá trị kế nhiệm bảo toàn thứ tự.

Khi đi ngược lên các tổ tiên, mỗi bước tạo nút cha mới có đúng một cây con thay đổi; cây con còn lại được chia sẻ. Không có phép gán vào nút cũ.

Đó là lý do các phép cập nhật này đáp ứng hợp đồng **persistent**. **Chúng chưa phải cây tự cân bằng**; chiều cao vẫn phụ thuộc thứ tự thao tác.

## 22. Phân tích độ phức tạp thời gian và bộ nhớ

Gọi:

- `n`: số nút trong một phiên bản.
- `h`: chiều cao của phiên bản, tính theo số nút trên đường dài nhất.
- `m`: số lần cập nhật thực sự thay đổi trạng thái.
- `k`: số mục được phát từ một phép duyệt phạm vi.

Giả sử so sánh khóa và tạo một đối tượng nút tốn `O(1)`.

| Thao tác | Thời gian | Bộ nhớ phụ/đối tượng mới |
| --- | --- | --- |
| `find(root,key)` trên BST | `O(h)` | `O(1)` nếu lặp |
| `persistent_put(root,key,value)` | `O(h)` | `O(h)` nút mới + `O(h)` call stack |
| `persistent_delete(root,key)` | `O(h)` | `O(h)` nút mới + `O(h)` call stack |
| `inorder_keys(root)` duyệt hết | `O(n)` | `O(h)` stack |
| `push` stack liên kết | **`O(1)`** | **1 nút mới** |
| `pop` stack liên kết | **`O(1)`** | **0 nút mới** |
| Bản sao tuple `v+(x,)` | `O(n)` | `O(n)` tham chiếu cho tuple mới |
| Dựng cây cân đối từ mảng đã sắp | `O(n)` | `O(n)` nút + `O(log n)` stack |

### BST cân đối và suy biến

- Nếu có một **BST persistent tự cân bằng** đúng cách: `h=O(log n)`, nên các thao tác cập nhật có thể được thiết kế với `O(log n)` thời gian và nút mới, tùy thuật toán cân bằng.
- Với mã BST persistent thường trong bài: trường hợp xấu `h=Θ(n)`; một lần cập nhật có thể mất `Θ(n)` thời gian/nút mới.
- **Immutability không tự làm cây cân bằng.** Path copying bảo toàn lịch sử, không tự giới hạn chiều cao.

### Chi phí của nhiều phiên bản

Nếu cây ban đầu có `n₀` nút và các lần cập nhật thứ `i` tạo `O(hᵢ+1)` nút mới (kể cả khi cây rỗng, `hᵢ=0` nhưng một lần chèn vẫn tạo nút), số nút đã được cấp phát có giới hạn:

```text
O(n₀ + tổng (hᵢ + 1) trên m lần cập nhật)
```

Với chiều cao logarit cho mọi phiên bản, một cách chặn đơn giản là:

```text
O(n₀ + m · log(n₀ + m + 1))
```

chưa tính bộ nhớ của các giá trị payload và bảng lưu gốc phiên bản (thường thêm `O(m)` tham chiếu).

Nếu mỗi phiên bản cũ đều được giữ, những nút mà nó tham chiếu tới không thể thu hồi chỉ vì phiên bản mới được tạo. Nếu một số phiên bản bị bỏ và không còn tham chiếu tới các nút chỉ dành cho chúng, bộ quản lý bộ nhớ có thể giải phóng phần không còn dùng.

## 23. Vì sao path copying hiệu quả hơn sao chép cả cây?

Giả sử một BST có **1.023 nút**, cân đối với chiều cao khoảng **10**. Ta muốn chèn một khóa mới.

**Sao chép toàn bộ cây:**

```text
Gần 1.023 nút được tạo lại cho một lần cập nhật
Thời gian và số nút mới: O(n)
```

**Path copying:**

```text
Chỉ tạo nút mới trên đường tìm kiếm và vị trí chèn
Số nút mới xấp xỉ theo h, khoảng 10–11 trong ví dụ
Thời gian và số nút mới: O(h)
```

Hai cách đều có thể giữ phiên bản cũ, nếu không sửa nút cũ và xử lý đúng phần tử. Nhưng **path copying tiết kiệm cấp phát đáng kể** trên cây thấp, nhất là khi nhiều phiên bản khác nhau rất ít.

### Không lạm dụng hình dung “mọi phiên bản chỉ thêm vài byte”

Mỗi nút mới có overhead đối tượng, con trỏ, metadata và chi phí quản lý bộ nhớ. Các giá trị payload có thể lớn. Một hệ thống giữ rất nhiều phiên bản vẫn có thể tiêu tốn đáng kể bộ nhớ.

Vì vậy, phân tích cần xét **số phiên bản được giữ**, mức chia sẻ, số nút mới và vòng đời đối tượng, không chỉ nêu “persistent tiết kiệm bộ nhớ”.

## 24. Những cấu trúc persistent khác và đặc điểm của chúng

Kỹ thuật chia sẻ khác nhau tùy loại cấu trúc:

| Cấu trúc | Cách chia sẻ điển hình | Thao tác phù hợp |
| --- | --- | --- |
| **Linked list / stack** | Thêm đầu tạo nút mới, chia sẻ đuôi | Push/pop đầu `O(1)` |
| **Persistent BST** | Sao chép đường từ gốc tới nút thay đổi | Tra cứu/cập nhật có thứ tự theo `h` |
| **Persistent segment tree** | Sao chép đường tới một lá, chia sẻ các nhánh còn lại | Cập nhật điểm/truy vấn đoạn trên nhiều phiên bản |
| **Trie persistent** | Sao chép các nút dọc đường ký tự/bit khóa | Cập nhật từ khóa hoặc bit prefix |
| **HAMT (hash array mapped trie)** | Chia sẻ các nhánh không thay đổi | Map/set persistent dùng cấu trúc phân nhánh theo băm |
| **Persistent vector dạng cây** | Chia sẻ phần lớn các nút, sao chép một đường/nhánh | Truy cập theo chỉ số và cập nhật phiên bản mới |

**Không được gán một độ phức tạp cố định cho mọi cấu trúc trong bảng.** Ví dụ, một persistent vector được tổ chức theo cây phân nhánh có các bảo đảm khác với tuple Python; một persistent segment tree chỉ nhanh theo những thao tác mà nó được thiết kế để hỗ trợ.

### Phản ví dụ: dùng tuple cho mọi cập nhật

```python
a0 = (1, 2, 3)
a1 = a0 + (4,)
a2 = a1 + (5,)

assert a0 == (1, 2, 3)
assert a1 == (1, 2, 3, 4)
assert a2 == (1, 2, 3, 4, 5)
```

Cách này rất dễ hiểu và có phiên bản cũ, nhưng phép nối tuple dài `n` cần **`O(n)` thời gian và tuple mới có `O(n)` ô tham chiếu**. Với dữ liệu nhỏ hoặc ít cập nhật, nó có thể hoàn toàn phù hợp; với nhiều phiên bản lớn, nên cân nhắc cấu trúc chia sẻ chuyên dụng.

## 25. Phiên bản cũ, bộ nhớ và thu gom rác

Persistence bảo đảm tính đúng của những phiên bản **còn được tham chiếu**, không có nghĩa runtime phải giữ mọi phiên bản được tạo ra mãi mãi.

Ví dụ:

```python
history = [v0, v1, v2]
current = history[-1]

# Ứng dụng quyết định không cần giữ phiên bản v0.
history.pop(0)

# Vẫn còn current, v1, v2; những nút được các gốc này
# hoặc các tham chiếu khác giữ lại thì vẫn có thể tồn tại.
```

Không thể kết luận rằng xóa một phần tử khỏi `history` sẽ lập tức giải phóng một số nút cụ thể:

- Một nút có thể vẫn được chia sẻ bởi các phiên bản khác.
- Người dùng/iterator khác có thể giữ tham chiếu riêng.
- Cơ chế giải phóng bộ nhớ tùy ngôn ngữ và runtime.

### Chính sách giữ phiên bản

Một ứng dụng thực tế có thể quy định:

- Giữ **10 phiên bản gần nhất** cho undo.
- Giữ những phiên bản được gắn nhãn **checkpoint**.
- Chỉ giữ bản hiện tại và một số bản snapshot đang được đọc.
- Lưu bản lịch sử lâu dài xuống kho bền vững theo cơ chế riêng.
- Loại phiên bản không còn sử dụng để cho phép thu hồi nút.

Cần tách **chính sách retention** khỏi logic cập nhật persistent.

## 26. Sửa nhầm dữ liệu mutable sẽ phá lịch sử ra sao?

Một cây persistent có nút `frozen=True` vẫn có thể chứa giá trị kiểu list. Nếu bên ngoài giữ alias tới list ấy, việc sửa nó có thể làm các phiên bản chung nút cùng quan sát một giá trị mới.

```python
@dataclass(frozen=True)
class UnsafePNode:
    key: int
    value: list[int]
    left: "UnsafePNode | None" = None
    right: "UnsafePNode | None" = None


raw_scores = [8, 9]
old_root = UnsafePNode(40, raw_scores)
new_root = UnsafePNode(
    50, [10],
    left=old_root,
)

raw_scores.append(5)

assert old_root.value == [8, 9, 5]
assert new_root.left.value == [8, 9, 5]
```

Ví dụ này không phải thao tác BST cập nhật theo path copying; nó chỉ cho thấy **hai gốc giữ chung payload mutable** sẽ mất tính ổn định lịch sử.

### Cách thiết kế an toàn hơn

- Chuyển `list[int]` thành `tuple[int,...]` khi nhận vào cấu trúc.
- Tạo đối tượng giá trị bất biến và không công bố đường sửa trạng thái bên trong.
- Nếu cần payload phức tạp, sao chép/chuẩn hóa **đúng cấp** thay vì chỉ đóng băng nút ngoài.
- Không để khóa mutable thay đổi giá trị so sánh/băm khi đang làm thành viên chỉ mục.
- Ghi rõ hợp đồng phiên bản: **giữ nguyên topology** hay **giữ nguyên toàn bộ giá trị quan sát**?

Đối với bài toán lịch sử điểm số, thông thường cần ngữ nghĩa thứ hai.

## 27. Persistence và undo/redo

Một cách triển khai undo rất đơn giản là giữ các gốc:

```python
undo_stack = [v0]
redo_stack = []

def apply_change(new_root):
    undo_stack.append(new_root)
    redo_stack.clear()

def undo():
    if len(undo_stack) <= 1:
        return undo_stack[-1]

    redo_stack.append(undo_stack.pop())
    return undo_stack[-1]

def redo():
    if redo_stack:
        undo_stack.append(redo_stack.pop())
    return undo_stack[-1]


apply_change(v1)
apply_change(v2)

assert undo() is v1
assert redo() is v2
```

Các nút được giữ trong những gốc lịch sử **không bị sửa**. Quay lại một phiên bản có thể chỉ cần đổi **tham chiếu gốc đang dùng**.

### Giới hạn của mô hình undo tuyến tính

- Nếu undo tới `v1` rồi tạo cập nhật mới, ta thường xóa `redo_stack` theo chính sách giao diện tuyến tính.
- Nếu muốn **giữ nhiều nhánh** thay vì xóa redo, phải lưu **đồ thị phiên bản** và nhãn nhánh tương ứng.
- Đoạn mã minh họa **không đồng bộ** và không tự xử lý những cập nhật từ nhiều luồng.
- Không có cơ chế ghi bền xuống ổ đĩa; mất tiến trình có thể mất lịch sử.

Những chức năng ấy thuộc **lớp quản lý phiên bản**, tách biệt với thuật toán sửa nút của cấu trúc persistent.

## 28. So sánh với log thao tác và copy-on-write

Persistent data structure không phải lựa chọn duy nhất để xây lịch sử.

### Lưu toàn bộ snapshot

```text
Mỗi thay đổi → sao chép cả trạng thái hiện tại
```

Ưu điểm: đọc lại một phiên bản trực tiếp và dễ giải thích. Nhược điểm: nếu trạng thái `O(n)` và có nhiều lượt cập nhật, sao chép đầy đủ tốn `O(n)` mỗi lượt, có thể lãng phí bộ nhớ.

### Lưu log thao tác (event sourcing / operation log)

```text
v0 + thao tác 1 + thao tác 2 + ... → trạng thái tại thời điểm t
```

Ưu điểm: có thể lưu lịch sử thao tác gọn nếu mỗi thao tác nhỏ. Nhược điểm: muốn đọc trạng thái cũ có thể phải **phát lại log** từ một checkpoint; còn cần giải quyết tính xác định, phiên bản schema và tác động bên ngoài.

### Copy-on-write (COW)

**Copy-on-write** mô tả một chiến lược: nhiều bên cùng chia sẻ dữ liệu cho tới khi có thao tác ghi, khi ấy sao chép phần cần sửa. Structural sharing/path copying là một cách cụ thể để tạo phiên bản trên cấu trúc nút; **không phải mọi cơ chế COW đều cung cấp full persistence** hoặc API truy cập tùy ý mọi phiên bản cũ.

| Phương án | Giữ lịch sử? | Chi phí khi thay đổi nhỏ |
| --- | --- | --- |
| Mutable, sửa tại chỗ | Không tự giữ | Thường ít cấp phát |
| Snapshot đầy đủ | Có nếu lưu các bản | Có thể sao chép `O(n)` mỗi lần |
| Operation log | Có thể tái dựng nếu log đủ | Ghi log thường nhỏ; đọc lại có thể tốn công |
| Persistent structural sharing | Có khi giữ gốc phiên bản | Chỉ sao chép phần ảnh hưởng, tùy cấu trúc |
| COW tổng quát | Tùy giao diện và vòng đời bản sao | Sao chép phần cần tách khi ghi |

Chọn giải pháp theo **nhu cầu truy vấn phiên bản cũ**, tần suất cập nhật, kích thước dữ liệu, đồng thời và chi phí bộ nhớ, không theo tên công nghệ.

## 29. Tính bất biến và xử lý đồng thời

Đọc một cây persistent từ **một gốc đã công bố** thường dễ suy luận hơn đọc một cây mutable bị sửa liên tục, vì những nút của gốc cũ không thay đổi.

Tuy nhiên:

- **Công bố `current_root`** cho luồng đọc phải theo quy tắc bộ nhớ/đồng bộ của nền tảng.
- Hai người ghi cùng tạo phiên bản mới từ một gốc cần chính sách **xử lý xung đột** nếu đều muốn cập nhật gốc hiện hành.
- Đọc đồng thời các payload mutable vẫn có rủi ro, dù liên kết nút không đổi.
- Phiên bản chỉ ổn định khi **toàn bộ trạng thái nằm trong phạm vi snapshot** cũng ổn định.
- Với nhiều thay đổi tạo thành một giao dịch, chỉ dùng cấu trúc persistent **chưa tự cung cấp ACID** hay tính nguyên tử nghiệp vụ.

### Ví dụ lost update

```text
current = v0

Writer A đọc v0 → tạo vA (thêm 10)
Writer B đọc v0 → tạo vB (thêm 20)

Nếu B ghi current = vB sau A ghi current = vA,
trạng thái hiện hành có thể không chứa thay đổi của A.
```

Cả `vA` và `vB` đều là phiên bản hợp lệ và bất biến, nhưng **quyết định chọn phiên bản hiện hành** vẫn có thể bị lost update. Cần khóa, compare-and-swap, giao dịch hoặc một chiến lược merge phù hợp với nghiệp vụ.

## 30. Lưu phiên bản không tự động giải quyết merge và xung đột

Fully persistent cho phép:

```text
          ┌── vA: sửa key=20 thành "A"
v0 ───────┤
          └── vB: sửa key=20 thành "B"
```

Nếu muốn tạo một phiên bản chung từ `vA` và `vB`, phải trả lời:

- Giá trị nào của khóa `20` được chọn?
- Có ghi nhận xung đột và yêu cầu người dùng quyết định không?
- Có quy tắc “last writer wins”, hợp nhất tập hợp, hoặc hàm merge miền dữ liệu không?
- Hai nhánh đã cùng xóa và thêm một khóa ra sao?
- Có phải giữ quan hệ thứ tự BST và mọi metadata sau khi merge không?

**Chỉ có gốc của hai cây chưa đủ định nghĩa kết quả merge.** Persistent giữ được dữ liệu để **so sánh và kết hợp**, nhưng **không tự đưa ra chính sách giải quyết xung đột**.

Nếu ứng dụng cần phiên bản phân nhánh có thể gộp lại, hãy thiết kế **hợp đồng merge** riêng.

## 31. Lỗi thường gặp

1. **Cho rằng persistent là lưu trên đĩa.** Trong cấu trúc dữ liệu, persistence trước hết nói về phiên bản cũ.
2. **Giữ alias tới list mutable rồi gọi nó là phiên bản cũ.** Alias vẫn thấy thay đổi.
3. **Sửa `left/right` của nút cũ khi path copying.** Làm hỏng phiên bản dùng chung.
4. **Chỉ sao chép nút lá nhưng không tạo lại đường tổ tiên.** Gốc mới có thể không dẫn tới thay đổi.
5. **Sao chép toàn bộ cây mỗi lần nhưng báo cập nhật `O(h)`.** Đó là `O(n)` theo kích thước cây.
6. **Cho rằng mọi cập nhật persistent đều `O(1)`.** Stack prepend khác BST path copying.
7. **Cho rằng BST persistent tự cân bằng.** Chiều cao của BST thường vẫn có thể `Θ(n)`.
8. **Dùng `frozen=True` nhưng chứa list mutable.** Lịch sử payload vẫn có thể đổi.
9. **Thay đổi khóa dùng trong comparator sau khi lưu trong BST.** Có thể phá thứ tự cây.
10. **Để con trỏ `parent` đơn nhất trong nút chia sẻ giữa hai phiên bản.** Cha phụ thuộc ngữ cảnh phiên bản.
11. **Nhầm `==` với `is` khi kiểm thử chia sẻ nút.** Bằng giá trị chưa chắc là cùng đối tượng.
12. **Xóa phiên bản cũ rồi mặc định tất cả nút cũ lập tức được giải phóng.** Có thể còn tham chiếu khác.
13. **Giữ mọi phiên bản vô hạn nhưng không dự toán bộ nhớ.** Số nút mới tích lũy vẫn tăng.
14. **Không phân biệt bản update không đổi và update thực sự thay đổi.** Có thể cấp phát thừa.
15. **Cho rằng xóa nút hai con chỉ cần sao chép khóa nhưng quên value.** Làm sai ánh xạ.
16. **Để một thuật toán xóa persistent sửa cây con cũ tại chỗ.** Phiên bản cũ bị ảnh hưởng.
17. **Dùng `seen` chung cho nhiều phiên bản rồi báo chúng có nút lặp.** Structural sharing giữa các phiên bản là chủ đích.
18. **Cho rằng fully persistent có nghĩa tự merge các nhánh.** Merge là khả năng khác.
19. **Cho rằng snapshot bất biến tự làm giao dịch đồng thời an toàn.** Cần giải quyết công bố và ghi xung đột.
20. **Không kiểm thử trạng thái trước cập nhật.** Mã có thể cho kết quả mới đúng nhưng đã phá lịch sử.
21. **Dùng các phần tử mutable từ API bên ngoài mà không copy/freeze.** Thay đổi ngoài luồng có thể làm lịch sử biến dạng.
22. **Không xác định chính sách khóa trùng.** Tạo nhiều nút có cùng khóa có thể phá bất biến BST đang dùng.

## 32. Bài tập tự luyện

**Bài 1.** Định nghĩa cấu trúc dữ liệu persistent. Nó khác gì với một biến Python trỏ đến list mutable trước và sau khi gọi `append`?

**Bài 2.** Phân biệt *partially persistent*, *fully persistent* và *confluently persistent*. Trong kiểu nào có thể cập nhật phiên bản cũ để tạo nhánh mới?

**Bài 3.** Vì sao một cấu trúc chỉ gồm các nút bất biến là điều kiện thuận lợi cho structural sharing nhưng chưa bảo đảm lịch sử ổn định nếu payload mutable?

**Bài 4.** Với `s0=None`, `s1=push(s0,10)`, `s2=push(s1,20)`, `s3=push(s1,99)`, hãy viết nội dung từng phiên bản từ đỉnh tới đáy.

**Bài 5.** Khi `pop(s2)`, có cần xóa hoặc sửa nút `20` không? Vì sao chi phí `O(1)`?

**Bài 6.** Một linked list persistent có `n` nút. Thêm đầu và sửa phần tử ở vị trí sâu `i` có chi phí ra sao đối với cách biểu diễn liên kết đơn giản?

**Bài 7.** Vẽ đường sao chép khi chèn `55` vào BST `40` có nhánh phải `60→trái 50` và nhánh trái `20`. Những nút nào được tạo mới và những nút nào dùng chung?

**Bài 8.** Trong `persistent_put`, tại sao nên trả chính `root` cũ khi khóa đã có và giá trị không thay đổi?

**Bài 9.** Với `v0` có khóa `20,40,50,60,70` và `v1` được tạo bằng cách chèn `55`, kết quả `find(v0,55)` và `find(v1,55)` là gì?

**Bài 10.** Từ `v0` tạo thêm `v_branch` bằng chèn `10`. Phiên bản `v1` có chứa `10` không? Hai nhánh có ghi đè nhau không?

**Bài 11.** Viết cài đặt persistent BST-map với `put` trả gốc mới và `inserted`; giải thích vì sao hai con không đổi được chia sẻ.

**Bài 12.** Vì sao persistent BST thường không nên lưu một trường `parent` mutable đơn nhất trong nút có thể dùng chung qua nhiều phiên bản?

**Bài 13.** Trình bày ba trường hợp xóa nút BST theo phương pháp persistent. Với nút hai con, dùng kế nhiệm thế nào?

**Bài 14.** Xóa khóa không tồn tại nên trả kết quả gì để tránh cấp phát không cần thiết? Có làm thay đổi phiên bản cũ không?

**Bài 15.** Với BST cao `h`, một lần chèn bằng path copying có chi phí thời gian, số nút mới và bộ nhớ đệ quy theo bậc nào?

**Bài 16.** Cùng một thao tác trên BST cân đối và BST lệch thành chuỗi: vì sao chi phí persistent khác nhau?

**Bài 17.** Phân biệt **giữ mọi phiên bản** với **giải phóng phiên bản không còn dùng**. Một nút chia sẻ có được thu hồi ngay khi bỏ một gốc không?

**Bài 18.** Nếu một lần cập nhật chỉ sửa một khóa trong cây cân đối có 1.023 nút, vì sao path copying thường ít cấp phát hơn sao chép toàn cây?

**Bài 19.** So sánh snapshot toàn bộ, log thao tác và persistent structural sharing khi cần tra cứu các trạng thái lịch sử.

**Bài 20.** Một hệ thống có hai writer cùng đọc `v0` và tạo `vA`/`vB`. Vì sao các phiên bản bất biến không tự ngăn được lost update?

**Bài 21.** Một cây persistent lưu `value: list[int]`. Hãy viết kiểm thử chứng minh một alias bên ngoài có thể làm nội dung của nhiều phiên bản thay đổi.

**Bài 22.** Vì sao một thao tác merge từ hai nhánh phải có chính sách xử lý xung đột riêng, dù cả hai nhánh đều là BST persistent hợp lệ?

<details>
<summary>Đáp án và gợi ý</summary>

1. Persistent giữ các phiên bản cũ dùng được sau cập nhật. Biến trỏ tới cùng một list mutable chỉ là alias và sẽ thấy thay đổi khi `append`.
2. Partial: đọc mọi phiên bản, chỉ cập nhật bản mới nhất. Full: đọc và cập nhật bất kỳ phiên bản đã giữ, tạo nhánh. Confluent: còn có khả năng kết hợp nhiều phiên bản theo quy tắc merge.
3. Nút bất biến chỉ giữ nguyên liên kết/trường tham chiếu. Nếu value là list còn sửa được, mọi gốc dùng chung list ấy có thể quan sát thay đổi.
4. `s0=[]`, `s1=[10]`, `s2=[20,10]`, `s3=[99,10]`.
5. Không sửa nút cũ; trả `(20,s1)`. Chỉ lấy giá trị ở đỉnh và tham chiếu `next`, nên `O(1)`.
6. Prepend `O(1)` và một nút mới. Thay phần tử sâu `i` có thể cần sao chép `O(i)` nút tiền tố, nếu không có cấu trúc chỉ mục phụ.
7. Chèn tạo nút `55`, tạo bản mới của `50`, `60` và `40`; nút `20` và `70` được dùng chung.
8. Không có thay đổi logic thì trả gốc cũ tránh cấp phát, đồng thời làm rõ các nhánh không đổi có thể được dùng lại.
9. `find(v0,55)=(False,None)`; `find(v1,55)=(True,"v55")`.
10. `v1` không chứa `10` vì được tạo từ `v0` trên nhánh khác. Không ghi đè nhau khi mọi nút dữ liệu được giữ bất biến.
11. Khi rẽ trái, cập nhật đệ quy cây trái rồi tạo bản nút cha mới với `left` mới và `right` cũ; khi rẽ phải thì đối xứng. Không sửa nút cũ.
12. Cùng một nút con có thể được chia sẻ dưới các bản cha khác nhau. Một trường parent đơn nhất không thể biểu diễn đồng thời hai ngữ cảnh phiên bản.
13. Lá trả `None`; một con trả con còn lại; hai con tìm kế nhiệm, xóa kế nhiệm bằng path copying ở nhánh phải, tạo nút gốc mới chứa cặp `(key,value)` kế nhiệm.
14. Trả `(root,False)` với **chính tham chiếu gốc cũ**; không cấp phát và không sửa dữ liệu lịch sử.
15. `O(h)` thời gian, `O(h)` nút mới, `O(h)` call stack đối với mã đệ quy.
16. Cây cân đối có `h=O(log n)`; cây lệch có `h=Θ(n)`. Path copying tạo các nút theo đường tìm nên chi phí phụ thuộc chiều cao.
17. Persistence không bắt buộc giữ vĩnh viễn mọi gốc. Nếu bỏ một gốc, các nút dùng chung với gốc khác vẫn phải tồn tại; chỉ các nút không còn tham chiếu mới có thể được thu hồi.
18. Một đường từ gốc đến vị trí cần đổi chỉ dài khoảng logarit số nút; path copying chỉ tạo một số nút theo đường đó, không tạo lại hàng nghìn nút không đổi.
19. Snapshot toàn bộ dễ đọc nhưng có thể tốn `O(n)` mỗi lần. Log có thể gọn nhưng phát lại tốn công. Structural sharing cho phép đọc phiên bản cũ trực tiếp, thường chỉ sao chép phần ảnh hưởng.
20. Hai writer có thể tạo phiên bản hợp lệ từ cùng `v0`, nhưng thao tác công bố gốc cuối cùng có thể ghi đè lựa chọn trước. Cần đồng bộ/transaction hoặc cơ chế xử lý xung đột.
21. Lưu list `raw` trong nút frozen, tạo hai gốc chia sẻ nút; gọi `raw.append(x)` rồi xác nhận cả hai gốc đều thấy list mới. Đây là **negative test**.
22. Hai nhánh có thể sửa cùng khóa theo hai giá trị khác nhau. Persistence giữ được cả hai, nhưng không quyết định giá trị cuối hay cách giải quyết xung đột.

</details>

## Ghi nhớ

**Cấu trúc dữ liệu persistent giữ được phiên bản cũ sau cập nhật**: thao tác mới tạo một gốc/trạng thái mới và **không sửa những nút thuộc phiên bản trước**. Kỹ thuật quan trọng là **structural sharing**, chỉ cấp phát phần thay đổi và chia sẻ những phần còn lại nếu chúng **bất biến cả về ngữ nghĩa dữ liệu**. Với stack liên kết, `push/pop` có thể `O(1)`; với BST persistent dùng **path copying**, chèn/xóa/cập nhật thường tốn **`O(h)` thời gian và nút mới**, tương ứng `O(log n)` nếu cây luôn được cân bằng. **Full persistence** cho phép tạo nhánh từ phiên bản cũ, nhưng **không tự cung cấp merge, đồng bộ, snapshot giao dịch hoặc lưu bền trên đĩa**. Muốn lịch sử đáng tin cậy, hãy quản lý **gốc phiên bản, vòng đời bộ nhớ, payload mutable và chính sách công bố/xung đột** một cách rõ ràng.

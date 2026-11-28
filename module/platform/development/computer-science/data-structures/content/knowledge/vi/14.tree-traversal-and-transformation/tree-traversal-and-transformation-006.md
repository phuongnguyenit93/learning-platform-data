# Tính kích thước, chiều cao và tổng hợp thông tin từ cây con

Một cây có thể chứa hàng nghìn hoặc hàng triệu nút. Khi hỏi **“Cây có bao nhiêu nút?”**, **“Cây cao bao nhiêu?”**, **“Tổng giá trị của một cây con là gì?”**, ta cần tính trên toàn bộ cấu trúc chứ không chỉ nhìn vào nút gốc. Điểm chung của những bài toán này là **đáp án của cây lớn có thể được ghép từ đáp án của các cây con**.

Trên cây nhị phân, các công thức điển hình là:

```text
size(node)   = 1 + size(node.left) + size(node.right)
height(node) = 1 + max(height(node.left), height(node.right))
sum(node)    = value(node) + sum(node.left) + sum(node.right)
```

Nếu quy ước hợp lý cho cây rỗng và **tính cây con trước khi tính cha**, mỗi nút chỉ cần xử lý một lần. Đó là tư duy **tổng hợp từ dưới lên** (*bottom-up aggregation*) bằng **duyệt sau (postorder)**.

Bài thuộc chương **Duyệt và biến đổi cây** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trong lộ trình học mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, mục tiêu không chỉ là viết đúng hàm đệ quy, mà còn hiểu **bất biến**, **thời điểm xử lý**, **độ phức tạp thời gian và bộ nhớ**, từ đó chọn cách biểu diễn phù hợp. Bài này hướng dẫn tính kích thước, chiều cao, tổng, số lá, trạng thái cân bằng và đường kính bằng một hoặc một số phép duyệt có kiểm soát.

## 1. Cấu trúc cây và các đại lượng cần phân biệt

Ta làm việc với **cây nhị phân có gốc**: mỗi nút `node` có thể có tối đa một con trái `left` và một con phải `right`. Giả định cây **hữu hạn**, không có chu trình, và mỗi nút (trừ gốc) thuộc đúng một vị trí con của một cha.

Ví dụ:

```text
                   8
                 /   \
                4     12
               / \      \
              2   6      15
```

Cây này gồm **6 nút**. Cây con gốc `4` gồm `4, 2, 6`; cây con gốc `12` gồm `12, 15`.

### 1.1. Kích thước cây con

**Kích thước** (*subtree size*) của một nút là **số nút thuộc cây con có gốc tại nút đó**, **tính cả chính nút gốc**.

```text
size(None) = 0
size(2)    = 1
size(4)    = 1 + size(2) + size(6) = 3
size(12)   = 1 + size(None) + size(15) = 2
size(8)    = 1 + 3 + 2 = 6
```

Đừng nhầm `size(node)` với **số nút con trực tiếp**. Nút `8` chỉ có hai con trực tiếp, nhưng cây con của nó chứa sáu nút.

### 1.2. Chiều cao và độ sâu

Có hai quy ước thường gặp về **chiều cao** (*height*):

- **Đếm theo số nút/mức:** cây rỗng cao **0**, nút lá cao **1**; `height(node) = 1 + max(height(left), height(right))`.
- **Đếm theo số cạnh:** một nút lá cao **0**, cây không rỗng có chiều cao bằng số cạnh trên đường dài nhất đến lá. Một số tài liệu đặt chiều cao cây rỗng là **−1** để giữ cùng công thức.

**Trong bài này, chiều cao `h` được đo bằng số nút trên đường dài nhất từ gốc đến lá.** Do đó:

```text
height(None) = 0
height(2)    = 1
height(4)    = 2
height(12)   = 2
height(8)    = 3
```

Với một cây không rỗng, chiều cao tính theo số cạnh bằng `height_nodes - 1`. Khi so sánh đáp án giữa các tài liệu, luôn kiểm tra quy ước đo.

**Độ sâu** (*depth*) là một khái niệm khác: số **cạnh từ gốc của toàn cây đến nút đang xét**. Độ sâu thường truyền **từ cha xuống con** (*top-down*); còn chiều cao của cây con tổng hợp **từ con lên cha** (*bottom-up*).

| Nút | Độ sâu từ gốc `8` (số cạnh) | Chiều cao cây con (số nút) |
|---|---:|---:|
| `8` | 0 | 3 |
| `4` | 1 | 2 |
| `12` | 1 | 2 |
| `2` | 2 | 1 |
| `6` | 2 | 1 |
| `15` | 2 | 1 |

Một nút có thể **nằm rất sâu** trong toàn cây nhưng cây con của nó **rất thấp**, ví dụ một lá ở độ sâu lớn có chiều cao bằng 1.

### 1.3. Tổng, số lá và các thông tin khác

Nếu `value` tại mỗi nút là một số, tổng giá trị cây con:

```text
sum(None) = 0
sum(node) = node.value + sum(node.left) + sum(node.right)
```

Đối với cây mẫu, tổng bằng:

```text
8 + 4 + 12 + 2 + 6 + 15 = 47
```

Một **lá** là nút không có con trái và không có con phải. Cây mẫu có **3 lá**: `2`, `6`, `15`. Tổng số lá cũng có thể tính từ hai cây con.

Những thống kê khác cùng ý tưởng gồm: giá trị nhỏ nhất/lớn nhất, tính cân bằng chiều cao, tổng theo điều kiện, số nút thỏa vị từ và **đường kính** (đường đi dài nhất giữa hai nút). Không phải đại lượng nào cũng cần cùng số trường, nhưng chúng có chung cách xử lý con trước cha.

## 2. Tư duy đệ quy: kết quả của cây lớn từ cây nhỏ

Giả sử mỗi lời gọi `solve(node)` trả về một đáp án cho **toàn bộ cây con** có gốc `node`. Ta thường có ba bước:

1. **Trường hợp cơ sở:** cây rỗng trả về một giá trị trung hòa.
2. **Giải cây con:** nhận kết quả từ `node.left` và `node.right`.
3. **Kết hợp tại cha:** dùng hai kết quả ấy cùng `node.value` để tạo đáp án cho `node`.

```text
SOLVE(node):
    if node == NULL:
        return EMPTY_RESULT

    left_result  = SOLVE(node.left)
    right_result = SOLVE(node.right)

    return COMBINE(node.value, left_result, right_result)
```

Mẫu này chính là **duyệt sau (postorder)**: Trái – Phải – Gốc. Ta có thể **đến nút cha** từ trước, nhưng **chỉ hoàn tất kết quả của cha sau khi hai cây con trả về**.

### Bất biến trung tâm

> Khi `SOLVE(node)` kết thúc, giá trị trả về phải mô tả chính xác **toàn bộ cây con gốc `node`**, không bỏ sót và không đếm trùng nút.

Để giữ bất biến, `COMBINE` chỉ dùng:

- Dữ liệu của nút hiện tại.
- Bản tóm tắt đã tính **đúng** của cây con trái.
- Bản tóm tắt đã tính **đúng** của cây con phải.

Không cần duyệt lại một cây con đã có kết quả. Đây là yếu tố quyết định để tổng thời gian là **O(n)** thay vì lặp công việc không cần thiết.

## 3. Công thức kích thước và chiều cao

### 3.1. Kích thước `size`

Với cây rỗng, không có nút nên `size(None) = 0`.

Với cây không rỗng có gốc `v`, các nút thuộc ba phần **không giao nhau**:

- Chính nút `v`: 1 nút.
- Cây con trái: `size(v.left)` nút.
- Cây con phải: `size(v.right)` nút.

Do đó:

```text
size(v) = 1 + size(v.left) + size(v.right)
```

Dấu **cộng** là cần thiết vì kích thước đếm **tất cả các nút ở cả hai phía**.

### 3.2. Chiều cao `height`

Với cây rỗng, `height(None) = 0` theo quy ước đếm số nút.

Một đường đi dài nhất từ `v` đến lá sẽ đi qua chính `v`, sau đó đi vào **một trong hai** cây con. Vì vậy:

```text
height(v) = 1 + max(height(v.left), height(v.right))
```

Dùng **`max`**, không phải cộng hai chiều cao: một đường gốc–lá chỉ có thể đi qua **một** nhánh tại nút `v`.

### 3.3. Python tự chứa cho hai đại lượng

```python
class Node:
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right


def subtree_size(node):
    if node is None:
        return 0
    return 1 + subtree_size(node.left) + subtree_size(node.right)


def tree_height(node):
    """Chiều cao tính theo số nút trên đường dài nhất."""
    if node is None:
        return 0
    return 1 + max(
        tree_height(node.left),
        tree_height(node.right),
    )


root = Node(
    8,
    left=Node(4, Node(2), Node(6)),
    right=Node(12, right=Node(15)),
)

assert subtree_size(root) == 6
assert subtree_size(root.left) == 3
assert subtree_size(root.right) == 2
assert tree_height(root) == 3
assert tree_height(root.left) == 2
assert tree_height(root.right) == 2

assert subtree_size(None) == 0
assert tree_height(None) == 0
assert subtree_size(Node(99)) == 1
assert tree_height(Node(99)) == 1
```

Hai hàm trên **không sửa cây**. Chúng tính một kết quả cho gốc được truyền vào. Nếu muốn lấy kích thước và chiều cao của *mọi* cây con, có thể lưu kết quả tại từng nút trong một lần duyệt (xem phần sau) thay vì gọi lại từ đầu tại từng nút.

## 4. Truy vết phép tổng hợp từ dưới lên

Dùng cây:

```text
                   8
                 /   \
                4     12
               / \      \
              2   6      15
```

Một thứ tự duyệt sau trái–phải–gốc là:

```text
2 → 6 → 4 → 15 → 12 → 8
```

Tại mỗi nút, ta nhận `(size, height, sum)` của hai con rồi kết hợp.

| Nút vừa hoàn tất | `size` | `height` (theo nút) | `sum` | Lý do |
|---:|---:|---:|---:|---|
| `2` | 1 | 1 | 2 | Hai con rỗng |
| `6` | 1 | 1 | 6 | Hai con rỗng |
| `4` | 3 | 2 | 12 | `(1+1+1,\ 1+max(1,1),\ 4+2+6)` |
| `15` | 1 | 1 | 15 | Hai con rỗng |
| `12` | 2 | 2 | 27 | `(1+0+1,\ 1+max(0,1),\ 12+0+15)` |
| `8` | 6 | 3 | 47 | `(1+3+2,\ 1+max(2,2),\ 8+12+27)` |

**Lá** có thể trả kết quả ngay sau hai lần gọi vào cây rỗng. **Cha** chỉ được tính khi đã có kết quả cả hai con.

### Minh họa thời điểm kết hợp

```text
Tính tại gốc 8:

                  8
               /     \
        (3,2,12)     (2,2,27)
             \         /
              \       /
                COMBINE
                   |
                   v
               (6,3,47)

Kết quả của 4 và 12 đã được tính trước kết quả của 8.
```

Nếu chỉ cần `size` hoặc chỉ cần `height`, ta có thể viết hàm riêng. Nhưng nếu cần **nhiều đại lượng trên cùng cây**, việc tính đồng thời trong một lần đi qua các nút sẽ tránh lặp công việc và thuận tiện cho việc mở rộng thuật toán.

## 5. Gộp kích thước, chiều cao và tổng trong một lượt

Một lời gọi có thể trả về một bộ kết quả thay vì một số duy nhất:

```text
AGGREGATE(node) trả (size, height, total)

AGGREGATE(NULL) = (0, 0, 0)

AGGREGATE(node):
    (ls, lh, lt) = AGGREGATE(node.left)
    (rs, rh, rt) = AGGREGATE(node.right)

    return (
        1 + ls + rs,
        1 + max(lh, rh),
        node.value + lt + rt
    )
```

Dùng `tuple` trong Python:

```python
def aggregate_basic(node):
    """Trả (size, height_nodes, total). Giá trị nút là số."""
    if node is None:
        return (0, 0, 0)

    left_size, left_height, left_total = aggregate_basic(node.left)
    right_size, right_height, right_total = aggregate_basic(node.right)

    return (
        1 + left_size + right_size,
        1 + max(left_height, right_height),
        node.value + left_total + right_total,
    )


assert aggregate_basic(root) == (6, 3, 47)
assert aggregate_basic(root.left) == (3, 2, 12)
assert aggregate_basic(None) == (0, 0, 0)
```

Mỗi nút thực hiện **O(1) phép kết hợp** sau khi hai cây con hoàn thành. Nếu chỉ dùng một lần gọi tại gốc, **tổng thời gian O(n)** và **stack lời gọi O(h)**, trong đó `h` là chiều cao tính theo số nút.

**Điều kiện dữ liệu:** công thức `total` giả định các giá trị nút là số và phép cộng có ý nghĩa. Nếu cây lưu chuỗi, đối tượng tùy biến hoặc giá trị thiếu, vẫn có thể tính `size`/`height`, nhưng cần xác định rõ phép tổng hợp thứ ba (hoặc bỏ nó). Không nên mặc nhiên cộng mọi kiểu dữ liệu như số.

## 6. Một bộ tóm tắt mở rộng cho mỗi cây con

Từ kích thước và chiều cao, ta có thể tính thêm thông tin trong **cùng một lần postorder**:

- `leaves`: số nút lá.
- `balanced`: cây con có **cân bằng chiều cao kiểu AVL** hay không.
- `diameter_edges`: số **cạnh** trên đường đi dài nhất giữa **hai nút bất kỳ** thuộc cây con.
- `total`: tổng giá trị số của cây con.

Để tránh nhầm giữa các trường, dùng một kiểu dữ liệu `Stats`.

### 6.1. Định nghĩa từng đại lượng và trường hợp cơ sở

Với cây rỗng:

```text
EMPTY_STATS:
    size            = 0
    height          = 0      # Đếm số nút
    total           = 0
    leaves          = 0
    balanced        = True
    diameter_edges  = 0
```

Ta xem cây rỗng **cân bằng**; không có lá; đường kính quy ước bằng 0.

Với nút `v` có bản tóm tắt hai cây con `L` và `R`:

```text
size(v)   = 1 + L.size + R.size
height(v) = 1 + max(L.height, R.height)
total(v)  = v.value + L.total + R.total

leaves(v) =
    1                          nếu v không có cả hai con
    L.leaves + R.leaves        ngược lại

balanced(v) =
    L.balanced AND R.balanced
    AND abs(L.height - R.height) <= 1

diameter_edges(v) =
    max(
        L.diameter_edges,
        R.diameter_edges,
        L.height + R.height
    )
```

Với `balanced`, điều kiện không chỉ kiểm tra tại gốc `v`; **cả hai cây con cũng phải cân bằng**. Một cây có hai nhánh cao bằng nhau ở gốc vẫn có thể không cân bằng nếu một cây con mất cân bằng ở tầng sâu.

Với `diameter_edges`, đường đi dài nhất hoặc:

1. Nằm **hoàn toàn trong** cây trái.
2. Nằm **hoàn toàn trong** cây phải.
3. **Đi qua nút hiện tại**, nối một đường dài nhất ở cây trái sang một đường dài nhất ở cây phải.

Vì `height` đo bằng **số nút**, đường đi qua gốc có `L.height + R.height` **cạnh**. Ví dụ nút lá có `0 + 0 = 0` cạnh, còn nút một con là lá có `1 + 0 = 1` cạnh.

### 6.2. Python: một lượt trả tất cả thống kê

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Stats:
    size: int
    height: int
    total: int
    leaves: int
    balanced: bool
    diameter_edges: int


EMPTY_STATS = Stats(
    size=0,
    height=0,
    total=0,
    leaves=0,
    balanced=True,
    diameter_edges=0,
)


def combine(value, left, right):
    """Tạo Stats cho nút có giá trị số, dựa trên Stats của hai con."""
    size = 1 + left.size + right.size
    height = 1 + max(left.height, right.height)
    total = value + left.total + right.total

    is_leaf = (left.size == 0 and right.size == 0)
    leaves = 1 if is_leaf else left.leaves + right.leaves

    balanced = (
        left.balanced
        and right.balanced
        and abs(left.height - right.height) <= 1
    )

    diameter_edges = max(
        left.diameter_edges,
        right.diameter_edges,
        left.height + right.height,
    )

    return Stats(
        size=size,
        height=height,
        total=total,
        leaves=leaves,
        balanced=balanced,
        diameter_edges=diameter_edges,
    )


def summarize(node):
    """Tổng hợp toàn bộ cây con bằng duyệt sau."""
    if node is None:
        return EMPTY_STATS

    left_stats = summarize(node.left)
    right_stats = summarize(node.right)
    return combine(node.value, left_stats, right_stats)


result = summarize(root)

assert result == Stats(
    size=6,
    height=3,
    total=47,
    leaves=3,
    balanced=True,
    diameter_edges=4,
)
assert summarize(None) == EMPTY_STATS
assert summarize(Node(9)) == Stats(1, 1, 9, 1, True, 0)
```

`@dataclass(frozen=True)` làm `Stats` **bất biến** sau khi tạo; việc dùng cùng một `EMPTY_STATS` cho nhiều lời gọi cơ sở là an toàn vì không thể sửa các trường của nó. `Node` trong ví dụ vẫn là đối tượng có thể thay đổi, nhưng hàm `summarize` **chỉ đọc** cây.

### 6.3. Kiểm tra đường kính trên ví dụ

Với cây:

```text
                   8
                 /   \
                4     12
               / \      \
              2   6      15
```

Đường đi dài nhất là một trong các đường nối lá phía trái qua gốc sang lá `15`, ví dụ:

```text
2 → 4 → 8 → 12 → 15

Có 5 nút và 4 cạnh.
diameter_edges = 4
```

Tại gốc `8`:

```text
L.height = 2
R.height = 2

Đường đi qua gốc = 2 + 2 = 4 cạnh.

Đường kính cây trái = 2 cạnh.
Đường kính cây phải = 1 cạnh.

diameter_edges(8) = max(2, 1, 4) = 4
```

**Đường kính không bắt buộc đi qua gốc của toàn cây**. Nếu đường đi dài nhất nằm hoàn toàn trong một cây con, phải lấy `max` với đường kính của con. Bỏ hai trường `L.diameter_edges`, `R.diameter_edges` có thể cho kết quả sai.

### 6.4. Thử cây lệch và giá trị âm

```python
chain = Node(1, right=Node(2, right=Node(3, right=Node(4))))
chain_stats = summarize(chain)

assert chain_stats.size == 4
assert chain_stats.height == 4
assert chain_stats.total == 10
assert chain_stats.leaves == 1
assert chain_stats.balanced is False
assert chain_stats.diameter_edges == 3

negative = Node(-5, Node(-2), Node(-7))
negative_stats = summarize(negative)

assert negative_stats.total == -14
assert negative_stats.size == 3
assert negative_stats.height == 2
assert negative_stats.leaves == 2
assert negative_stats.balanced is True
```

**Tổng có thể âm**; đó không phải lỗi. Công thức tổng phụ thuộc phép cộng và giá trị thực tế, còn kích thước và chiều cao chỉ phụ thuộc **cấu trúc cây**.

## 7. Tại sao kết hợp nhiều thông tin vẫn là O(n)?

Giả sử phép `combine` đọc và tính một **số lượng cố định trường** (size, height, total, leaves, balanced, diameter). Chi phí mỗi lần kết hợp là O(1) theo mô hình phép toán số học cơ bản.

Với cây có `n` nút, nếu hai cây con có `n_L` và `n_R` nút:

```text
n = 1 + n_L + n_R

T(n) = T(n_L) + T(n_R) + O(1)
T(0) = O(1)
```

Vì các cây con không chia sẻ nút, toàn bộ phép duyệt xử lý mỗi nút thực **một lần** và mỗi nhánh rỗng trong số O(n) nhánh cũng chỉ trả cơ sở một lần:

```text
T(n) = Θ(n)       với n >= 1
```

Một lần `summarize(root)` trả về nhiều trường nhưng không cần quét đi quét lại toàn bộ cây cho từng trường.

### 7.1. Bộ nhớ stack theo chiều cao

Gọi `h` là chiều cao của cây **theo số nút trên đường dài nhất**. Khi đệ quy xuống con trái, frame của cha phải chờ; khi con trái hoàn tất, cha tiếp tục sang con phải. Hai lời gọi **không thực thi đồng thời**.

Do vậy số frame đang hoạt động cùng lúc theo một đường gốc–lá dài nhất là O(h) (cộng một frame cơ sở đến `None`):

- **Cây cân bằng:** `h = Θ(log n)`, stack O(log n).
- **Cây lệch:** `h = Θ(n)`, stack O(n).
- **Cây rỗng:** một lời gọi cơ sở, O(1).

Với mỗi frame chỉ giữ hai `Stats` kích thước cố định và vài biến cục bộ, **bộ nhớ phụ điều khiển** của `summarize` là **O(h)**. Ở thời điểm gọi con phải, kết quả con trái vẫn nằm trong frame cha, nhưng có **tối đa một kết quả đã tổng hợp giữ lại cho mỗi mức**, nên cận trên vẫn O(h).

### 7.2. Khi nào tổng bộ nhớ thành O(n)?

Nếu chỉ **trả bộ tóm tắt tại gốc**, ta không lưu mảng n kết quả; bộ nhớ phụ là O(h) trong mô hình đã nêu.

Nếu muốn **gắn một bộ `Stats` vào mỗi nút** hoặc trả về **bảng kết quả của mọi nút**, sẽ phát sinh **O(n)** chỗ lưu cho các bản tóm tắt, bên cạnh O(h) stack. Cần tách:

```text
Chỉ lấy thống kê tại gốc:
    O(h) stack, O(1) kết quả cuối.

Lưu thống kê cho mọi nút:
    O(h) stack + O(n) dữ liệu thống kê.
```

Khi thuật toán ghi kết quả vào chính các nút, phần bộ nhớ này **là dữ liệu bổ sung gắn trong cây**, không phải “call stack”.

**Lưu ý về số nguyên rất lớn:** trong mô hình RAM thường coi phép cộng và so sánh trên số có kích thước máy là O(1). Trong Python, số nguyên tùy ý lớn có chi phí tính toán phụ thuộc số chữ số. Đối với bài tập phân tích cấu trúc dữ liệu, cận O(n) được hiểu dưới giả định chi phí phép toán số cơ bản là hằng số.

## 8. Tránh lỗi tính đi tính lại: từ O(n²) về O(n)

Một sai lầm phổ biến là tính kích thước hoặc chiều cao của **mọi** cây con bằng cách gọi lại hàm duyệt **từ đầu tại từng nút**.

Ví dụ ta muốn gán `subtree_size` cho mọi nút. Cách kém hiệu quả:

```python
def annotate_sizes_slow(node):
    if node is None:
        return

    node.subtree_size = subtree_size(node)  # Quét cây con của node.
    annotate_sizes_slow(node.left)
    annotate_sizes_slow(node.right)
```

Mã này đúng giá trị nếu đầu vào là cây, nhưng lặp nhiều công việc. Trên cây lệch có `n` nút:

```text
Nút gốc:      đếm n nút
Nút kế tiếp:  đếm n-1 nút
Nút kế tiếp:  đếm n-2 nút
...
Nút lá:       đếm 1 nút

Tổng = n + (n-1) + ... + 1
     = n(n+1)/2
     = Θ(n²)
```

Thay vì gọi `subtree_size(node)` từ đầu tại mỗi nút, ta để hàm đệ quy **trả kích thước vừa tính** lên cha, đồng thời gán thuộc tính ngay khi kết hợp:

```python
def annotate_sizes_once(node):
    if node is None:
        return 0

    left_size = annotate_sizes_once(node.left)
    right_size = annotate_sizes_once(node.right)

    node.subtree_size = 1 + left_size + right_size
    return node.subtree_size


assert annotate_sizes_once(root) == 6
assert root.subtree_size == 6
assert root.left.subtree_size == 3
assert root.right.subtree_size == 2
assert root.left.left.subtree_size == 1
```

Lúc này mỗi nút chỉ thực hiện **một lần** tổng hợp. Thời gian O(n), stack O(h) và lưu thêm một trường tại mỗi nút, tổng O(n) dữ liệu mới.

### Cảnh báo tương tự với bài toán cân bằng

Kiểm tra cân bằng bằng cách ở **mỗi nút** lại gọi `tree_height` trên hai cây con có thể lặp quét chiều cao và tốn Θ(n²) trên cây lệch trong trường hợp xấu nhất. Hàm `summarize` ở phần 6 **trả chiều cao và trạng thái cân bằng cùng lúc**, nên không cần tính lại chiều cao của từng cây con.

Nguyên tắc quan trọng:

> **Thông tin đã tính xong ở con nên được trả về hoặc lưu lại để cha sử dụng**, không tự động quét lại toàn bộ cây con.

## 9. Mô hình “fold cây”: một công thức kết hợp, nhiều bài toán

Nhiều phép tổng hợp có chung hình dạng:

```text
F(NULL) = base

F(node) = combine(
    node.value,
    F(node.left),
    F(node.right)
)
```

Đôi khi cách làm này được gọi là **fold**, **reduce** hay **catamorphism trên cây**: thay cấu trúc cây bằng một kết quả tổng hợp thông qua phép kết hợp tại từng nút.

Các ví dụ:

| Đại lượng | Giá trị ở cây rỗng | Kết hợp tại nút |
|---|---|---|
| Số nút | `0` | `1 + left + right` |
| Chiều cao (theo nút) | `0` | `1 + max(left, right)` |
| Tổng giá trị số | `0` | `value + left + right` |
| Tích giá trị số | `1` | `value * left * right` |
| Số nút có giá trị chẵn | `0` | `(1 nếu value chẵn, ngược lại 0) + left + right` |
| Có tồn tại giá trị thỏa điều kiện | `False` | `predicate(value) or left or right` |
| Mọi nút đều thỏa điều kiện | `True` | `predicate(value) and left and right` |

**Giá trị cơ sở phải tương thích với phép kết hợp**. Ví dụ phép nhân cần 1 chứ không phải 0; phép “mọi nút đều thỏa” có phần tử trung hòa là `True`. Nếu chọn sai cơ sở, kết quả có thể sai ngay trên cây một nút.

### Một hàm fold tổng quát bằng Python

```python
def fold_tree(node, empty, combine_fn):
    if node is None:
        return empty

    left_result = fold_tree(node.left, empty, combine_fn)
    right_result = fold_tree(node.right, empty, combine_fn)
    return combine_fn(node.value, left_result, right_result)


size = fold_tree(root, 0, lambda value, left, right: 1 + left + right)
height = fold_tree(root, 0, lambda value, left, right: 1 + max(left, right))
total = fold_tree(root, 0, lambda value, left, right: value + left + right)

assert (size, height, total) == (6, 3, 47)

even_count = fold_tree(
    root,
    0,
    lambda value, left, right: (1 if value % 2 == 0 else 0) + left + right,
)
assert even_count == 5
```

Trong cây mẫu, các số chẵn là `8, 4, 12, 2, 6`, nên `even_count == 5`.

Đây là **ba hoặc bốn lượt duyệt độc lập** khi gọi `fold_tree` nhiều lần. Mỗi lượt O(n), nên với **số lượng phép tổng hợp cố định**, tổng vẫn O(n) theo ký hiệu tiệm cận; nhưng nếu cần nhiều đại lượng cùng lúc, **gộp kết quả trong một `Stats`** tránh lặp duyệt và giảm hệ số chi phí.

### Khi nào phép kết hợp không còn O(1)?

Nếu `combine_fn` nối các danh sách lớn bằng phép tạo bản sao, sắp xếp toàn bộ phần tử cây con hay tìm kiếm lại trong cây, chi phí tại một nút có thể **phụ thuộc kích thước cây con**. Khi đó không thể khẳng định fold tự động O(n). Muốn phân tích đúng, phải cộng **chi phí kết hợp thực sự** tại tất cả nút.

## 10. Không đệ quy: tổng hợp bằng hai stack tường minh

Một cây lệch rất sâu có thể vượt **giới hạn độ sâu đệ quy của Python**. Ta có thể mô phỏng postorder bằng **stack tường minh**.

Một cách đơn giản là lưu `(node, expanded)`, trong đó:

- `expanded=False`: chưa duyệt các con, phải đẩy lại nút để xử lý sau.
- `expanded=True`: hai cây con đã hoàn tất; có thể kết hợp kết quả.

Nếu lưu bản tóm tắt **tại mỗi nút** hoặc trong một dictionary tra theo nút, cách ấy dễ viết nhưng cần **O(n)** bộ nhớ lưu kết quả của các nút. Có một biến thể chỉ dùng **hai stack**: một stack công việc, một stack kết quả của các cây con đã giải quyết.

### 10.1. Tránh tạo dictionary cho mọi nút

Ta có thể dùng hai stack:

- `frames`: chứa khung `(node, expanded)` chờ thực hiện.
- `values`: chứa kết quả tổng hợp của những cây con đã hoàn tất.

Khi đẩy công việc theo thứ tự **cha hẹn lại → cây phải → cây trái**, LIFO khiến cây trái hoàn tất rồi tới cây phải. Với mỗi nút, kết quả cây trái được đưa lên `values` trước kết quả cây phải; do đó khi xử lý cha, ta **lấy kết quả phải trước, rồi kết quả trái**.

```text
FOLD_ITERATIVE(root):
    frames = [(root, false)]
    values = []

    while frames không rỗng:
        (node, expanded) = frames.pop()

        if node == NULL:
            values.push(EMPTY_RESULT)

        else if NOT expanded:
            frames.push((node, true))
            frames.push((node.right, false))
            frames.push((node.left, false))

        else:
            right_result = values.pop()
            left_result = values.pop()
            values.push(COMBINE(node.value, left_result, right_result))

    return values.pop()
```

**Lưu ý:** phiên bản này vẫn xử lý **lời gọi cây rỗng** như một giá trị kết quả trung hòa. Nhờ vậy mỗi nút thật luôn lấy được chính xác hai kết quả con mà không cần rẽ nhánh nhiều ở bước kết hợp.

### 10.2. Cài đặt Python để tổng hợp `Stats`

```python
def summarize_iterative(root):
    frames = [(root, False)]
    values = []

    while frames:
        node, expanded = frames.pop()

        if node is None:
            values.append(EMPTY_STATS)
            continue

        if not expanded:
            frames.append((node, True))
            frames.append((node.right, False))
            frames.append((node.left, False))
            continue

        right_stats = values.pop()
        left_stats = values.pop()
        values.append(combine(node.value, left_stats, right_stats))

    # Kể cả cây rỗng, vẫn có đúng một kết quả.
    assert len(values) == 1
    return values[0]


assert summarize_iterative(root) == summarize(root)
assert summarize_iterative(None) == EMPTY_STATS
assert summarize_iterative(chain) == summarize(chain)
```

Đoạn mã dùng `Stats`, `EMPTY_STATS` và `combine` đã định nghĩa ở mục 6. Nó chỉ đọc cây; không sửa liên kết `left`/`right` và không gắn trường thống kê vào nút.

### 10.3. Vì sao bộ nhớ vẫn O(h)?

Trong cách thực thi này, tại mỗi thời điểm:

- `frames` ghi nhớ các nút đang chờ và các cây con chưa duyệt trên **đường DFS hiện tại**.
- `values` lưu các kết quả đã tính của những cây con đang chờ ghép vào tổ tiên. Trên cây nhị phân, mỗi mức đang mở có tối đa một kết quả con đã xong đang chờ nút cha kết hợp.

Do đó tổng số khung và kết quả đang lưu là **O(h)**, giả định một bản `Stats` có kích thước hằng số và không chứa danh sách các nút. Trên cây cân bằng, chi phí phụ thường O(log n), còn trên cây lệch có cận trên O(n). Tổng thời gian vẫn O(n), vì mỗi nút và mỗi tham chiếu con rỗng được xử lý số lần hằng số.

**Phân biệt** với cách postorder dùng một stack để xây thứ tự đảo vào một stack thứ hai chứa **tất cả n nút**: cách ấy có thể cần O(n) bộ nhớ. Số lượng stack không tự quyết định độ phức tạp; điều quyết định là **mỗi stack thực sự giữ những gì**.

## 11. Vấn đề thực tế: khi dữ liệu cây thay đổi

Các hàm tổng hợp từ dưới lên ở bài này giả định **cấu trúc và giá trị cây không đổi trong suốt phép duyệt**. Nếu chương trình vừa tính thống kê vừa sửa liên kết hoặc giá trị, cần xác lập quy tắc nhất quán.

### 11.1. Lưu cache thống kê tại mỗi nút

Nếu ứng dụng thường xuyên cần `size` hay `height` của nhiều cây con, có thể lưu các kết quả này trong nút để đọc nhanh về sau.

Nhưng khi **thêm, xóa hoặc chuyển một cây con**, thông tin ở các **nút tổ tiên** có thể không còn đúng. Ví dụ, thêm một lá mới dưới nút `12`:

- `size(12)` tăng.
- `size(8)` tăng.
- `height(12)` có thể đổi nếu nhánh mới dài hơn các nhánh cũ.
- `height(8)` có thể đổi nếu một đường mới trở thành đường sâu nhất.

Nếu có con trỏ `parent` hoặc một đường tìm kiếm đã biết, ta có thể cập nhật những tổ tiên bị ảnh hưởng theo quy tắc tương ứng. Còn nếu không quản lý cập nhật cache, phải **tính lại từ cây hiện tại** trước khi tin vào các thuộc tính đã lưu.

### 11.2. Tránh hiểu sai chiều cao và cân bằng

Một cây có thể có hai nhánh gốc **cùng chiều cao** nhưng vẫn **không cân bằng** do một cây con sâu bên trong bị lệch quá mức. Do đó công thức `balanced` phải kết hợp:

```text
balanced(left) AND balanced(right)
AND abs(height(left) - height(right)) <= 1
```

Chỉ kiểm tra `abs(height(left)-height(right)) <= 1` ở gốc là chưa đủ để kết luận **toàn bộ cây** cân bằng theo định nghĩa đã chọn.

### 11.3. Cây khác đồ thị có hướng

Nếu hai cha cùng tham chiếu **một đối tượng nút con**, dữ liệu thực tế là **DAG** có nút dùng chung, không còn là cây đúng theo giả định. Khi đó `size` đệ quy theo **số lần xuất hiện trong các đường đi** có thể **đếm trùng cùng một đối tượng**.

Nếu có chu trình, đệ quy có thể không kết thúc. Muốn đếm số **nút duy nhất trong một đồ thị**, phải thiết kế thuật toán duyệt với tập đã thăm `visited` và xác định rõ có được tính lặp một nút dùng chung hay không. Công thức chia hai cây con độc lập chỉ áp dụng trực tiếp khi cấu trúc là cây.

### 11.4. Kiểu số và dữ liệu không hợp lệ

- **Giá trị âm:** tổng có thể âm, các đại lượng cấu trúc không bị ảnh hưởng.
- **Giá trị không phải số:** không áp dụng trực tiếp `total = value + left.total + right.total`; thay bằng phép tổng hợp phù hợp.
- **Số dấu phẩy động `NaN`:** các so sánh min/max và phép tổng có thể cho kết quả khó mong muốn; cần chính sách xử lý giá trị thiếu.
- **Số nguyên rất lớn:** trong môi trường số nguyên giới hạn bit có thể xảy ra tràn; Python hỗ trợ số nguyên tùy ý nhưng phép tính với số rất lớn không còn chi phí hằng số theo số chữ số.
- **Dữ liệu từ nhiều luồng:** nếu một luồng sửa cây trong lúc luồng khác tổng hợp, kết quả có thể không mô tả một trạng thái nhất quán. Cần đồng bộ hoặc snapshot theo yêu cầu ứng dụng.

## 12. Các lỗi phổ biến và cách kiểm tra

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng `size(None) = 1` | Đếm thêm nút không tồn tại | Cơ sở kích thước rỗng là **0** |
| Dùng `height(None) = 1` với quy ước chiều cao lá bằng 1 | Chiều cao bị cộng dư | Dùng **0** cho cây rỗng khi đếm số nút |
| Nhầm chiều cao theo nút với theo cạnh | Kết quả lệch 1 ở cây không rỗng | Nêu quy ước và chuyển đổi khi cần |
| Cộng chiều cao hai con | Tạo độ dài của hai nhánh, không phải một đường gốc–lá | Dùng **max** hai chiều cao |
| Lấy max kích thước hai con | Bỏ quên nút của nhánh còn lại | Dùng **tổng** hai kích thước, cộng 1 |
| Xử lý cha khi chưa biết kết quả con | Tổng hợp thiếu dữ liệu | Dùng postorder/con trước cha |
| Gọi lại `subtree_size` tại mọi nút | Có thể tốn Θ(n²) | Trả kích thước lên cha trong một lượt |
| Kiểm tra cân bằng chỉ tại gốc | Bỏ qua mất cân bằng trong cây con | Kết hợp cả cờ `balanced` của hai con |
| Tính đường kính chỉ qua gốc | Bỏ lỡ đường dài nhất trong một cây con | Lấy max cả đường kính trái/phải |
| Nhầm chiều cao với độ sâu | Chọn hướng tổng hợp sai | Chiều cao bottom-up; độ sâu thường top-down |
| Không phân biệt bộ nhớ stack và cache mọi nút | Báo thiếu O(n) lưu kết quả | Phân tích riêng dữ liệu và điều khiển |
| Sửa cây nhưng không cập nhật thống kê đã lưu | Cache lỗi thời | Cập nhật tổ tiên hoặc tính lại |
| Bỏ qua cây quá sâu | `RecursionError` trong Python | Dùng stack tường minh khi phù hợp |
| Duyệt cấu trúc dùng chung nút như cây | Đếm trùng hoặc không kết thúc nếu có chu trình | Xác minh giả định hoặc dùng traversal đồ thị |

Để kiểm tra cách tính, nên thử theo thứ tự: **cây rỗng**, **một nút**, **cây lệch**, **cây có hai nhánh bằng nhau**, **cây có nhiều lá**, và **cây chứa số âm**. Mỗi tình huống làm lộ một lớp lỗi công thức khác nhau.

## 13. Bài tập tự luyện có lời giải

**Bài 1 — Kích thước và chiều cao.** Cho cây:

```text
        A
       / \
      B   C
         /
        D
```

Hãy tính `size(A)` và `height(A)` theo số nút.

*Lời giải:* Cây có bốn nút nên **`size(A) = 4`**. Đường dài nhất là `A → C → D` gồm ba nút, nên **`height(A) = 3`**.

**Bài 2 — Trường hợp cơ sở.** Theo quy ước chiều cao đếm số nút, cây rỗng và cây chỉ có một nút có `size` và `height` nào?

*Lời giải:* Cây rỗng `(size, height) = (0, 0)`. Cây một nút `(1, 1)`.

**Bài 3 — Tổng trên cây con.** Với cây số ở phần 1, tổng của cây con gốc `4` và gốc `12` lần lượt là bao nhiêu?

*Lời giải:* `4 + 2 + 6 = 12`; `12 + 15 = 27`. Tổng toàn cây là `8 + 12 + 27 = 47`.

**Bài 4 — Postorder.** Với cây `8`, `4`, `12`, `2`, `6`, `15`, hãy nêu thứ tự hoàn thành phép tổng hợp ở mỗi nút.

*Lời giải:* Một thứ tự postorder trái–phải–gốc là **`2, 6, 4, 15, 12, 8`**.

**Bài 5 — Kích thước không phải độ sâu.** Nút `15` ở độ sâu mấy và có chiều cao cây con mấy, nếu gốc là `8`?

*Lời giải:* `15` ở **độ sâu 2 cạnh** (từ `8` qua `12`), nhưng cây con của nó chỉ có một nút nên **chiều cao bằng 1**.

**Bài 6 — Số lá.** Cây số ở phần 1 có bao nhiêu lá? Nếu thêm con trái `10` cho nút `12`, số lá thay đổi ra sao?

*Lời giải:* Ban đầu có ba lá `2, 6, 15`. Khi thêm con trái `10` vào `12`, `12` vốn không phải lá nên thêm được **một lá mới**, tổng thành **4 lá**.

**Bài 7 — Cân bằng chiều cao.** Một nút có cây con trái cao 3, cây con phải cao 2. Có thể khẳng định cả cây con tại nút ấy cân bằng không?

*Lời giải:* **Chưa đủ.** Chênh lệch tại nút là 1, nhưng cần biết cả **hai cây con tự chúng cũng cân bằng**.

**Bài 8 — Đường kính.** Cây chỉ gồm một nút có đường kính theo **số cạnh** bằng bao nhiêu? Một chuỗi bốn nút liên tiếp có đường kính bằng bao nhiêu?

*Lời giải:* Một nút có đường kính **0 cạnh**; chuỗi bốn nút có đường kính **3 cạnh**.

**Bài 9 — Chọn phép kết hợp.** Để tính số nút có giá trị chẵn, cơ sở cho cây rỗng là gì? Khi hợp nhất một nút với hai cây con phải làm gì?

*Lời giải:* Cơ sở là **0**. Tại nút, cộng **1 nếu giá trị nút chẵn**, ngược lại 0, với hai kết quả đếm của cây con.

**Bài 10 — Chi phí.** Vì sao tính `subtree_size` bằng một lần postorder O(n), còn gọi lại hàm đếm toàn bộ cây con tại từng nút có thể Θ(n²)?

*Lời giải:* Một lần postorder **tái sử dụng kết quả từ con**, nên mỗi nút được tính O(1) công việc. Gọi đếm lại tại từng nút khiến nhiều cây con bị duyệt nhiều lần; cây lệch tạo tổng `n + (n-1) + … + 1 = Θ(n²)`.

**Bài 11 — Bộ nhớ.** Cây cân bằng có `n` nút, `h = Θ(log n)`. Tính và trả `Stats` chỉ tại gốc bằng đệ quy cần bao nhiêu bộ nhớ phụ? Nếu lưu `Stats` tại mọi nút thì sao?

*Lời giải:* Chỉ trả tại gốc: **O(h) = O(log n)** bộ nhớ stack, kết quả cuối kích thước hằng số. Nếu lưu tại mọi nút: **O(n)** kết quả bổ sung, ngoài stack.

**Bài 12 — Chiều cao và đường kính.** Vì sao đường kính đi qua nút hiện tại có thể bằng `left.height + right.height` khi hai chiều cao được đo bằng số nút?

*Lời giải:* Một đường từ nút hiện tại xuống lá sâu nhất bên trái có **`left.height` cạnh**; nhánh phải có **`right.height` cạnh**. Ghép hai nhánh qua nút hiện tại có tổng số cạnh đúng bằng tổng hai chiều cao ấy.

**Bài 13 — Cấu trúc dùng chung nút.** Nếu `root.left` và `root.right` cùng trỏ tới đúng một đối tượng lá, `1 + size(left) + size(right)` có đếm số đối tượng nút **duy nhất** không?

*Lời giải:* **Không.** Nó đếm hai lần tham chiếu cùng lá. Cấu trúc có nút được dùng chung là DAG, không còn thỏa giả định cây nhị phân không chia sẻ nút; cần định nghĩa lại bài toán và cách duyệt.

**Bài 14 — Cây thay đổi.** Đã lưu kích thước và chiều cao tại mọi nút, sau đó thêm một lá. Có thể tiếp tục đọc các thống kê đã lưu mà không cập nhật gì không?

*Lời giải:* **Không nói chung.** Kích thước của các tổ tiên tăng và chiều cao của một số tổ tiên có thể thay đổi. Phải cập nhật đúng vùng ảnh hưởng hoặc tính lại.

**Bài 15 — Biến thể không đệ quy.** Tại sao trong `summarize_iterative` phải lấy `right_stats = values.pop()` trước `left_stats = values.pop()`?

*Lời giải:* Thuật toán hoàn thành **cây trái trước**, đẩy kết quả trái vào `values`, sau đó hoàn thành cây phải và đẩy kết quả phải **lên trên**. Stack LIFO trả kết quả phải trước; đảo thứ tự sẽ ghép nhầm nếu phép kết hợp không giao hoán.

## 14. Tổng kết

Bài toán tính **kích thước, chiều cao và tổng hợp thông tin từ cây con** có chung một mô hình: cây rỗng có giá trị cơ sở rõ ràng, mỗi cây con trả kết quả của chính nó, và **nút cha kết hợp kết quả hai con sau khi chúng đã hoàn tất**. Công thức quan trọng là:

```text
size   = 1 + left.size + right.size
height = 1 + max(left.height, right.height)
total  = value + left.total + right.total
```

Tư duy **postorder / bottom-up** cho phép tính một hoặc nhiều thống kê **trong O(n) thời gian**, với **O(h) stack điều khiển** nếu mỗi khung chỉ giữ thông tin kích thước hằng số; `h` là chiều cao cây. Nếu lưu kết quả ở mọi nút, cần thêm O(n) bộ nhớ. Khi cây quá sâu, có thể dùng **stack tường minh** mà vẫn giữ bất biến con trước cha. Quan trọng nhất là **không quét lại cây con đã tính xong**, vì tái sử dụng kết quả là chìa khóa giúp tổng hợp vừa đúng vừa hiệu quả.

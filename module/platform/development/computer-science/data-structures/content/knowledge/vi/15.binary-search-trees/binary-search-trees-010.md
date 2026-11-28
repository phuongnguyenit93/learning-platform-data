# Truy vấn một khoảng khóa và giới hạn số phần tử đầu ra

Một hệ thống học tập lưu các bài kiểm tra theo **mã tăng dần**, hoặc các buổi học theo **thời điểm bắt đầu**, trong **cây tìm kiếm nhị phân** (*Binary Search Tree – BST*). Người dùng không phải lúc nào cũng muốn lấy tất cả hồ sơ. Chẳng hạn, họ có thể yêu cầu: **“Lấy tối đa 5 buổi có thời điểm bắt đầu từ 09:00 đến trước 12:00, theo thứ tự tăng dần.”**

Yêu cầu này kết hợp **hai vấn đề khác nhau**:

1. **Truy vấn một khoảng khóa** (*range query*): chỉ chọn các khóa thỏa điều kiện biên.
2. **Giới hạn số phần tử đầu ra** (*output limit*): chỉ trả về tối đa `L` kết quả đầu tiên trong khoảng, rồi **dừng duyệt** khi đã đủ.

Cây BST cho phép làm cả hai mà không phải duyệt toàn cây hoặc sắp xếp lại kết quả. Bài thuộc chương **Cây tìm kiếm nhị phân** trong module cấu trúc dữ liệu, nhằm kết nối bất biến BST với thao tác, độ phức tạp và lựa chọn cấu trúc phù hợp. Chúng ta sẽ chứng minh cách cắt tỉa nhánh, cài đặt bằng đệ quy và iterator Python, tạo các trang kết quả theo khóa cuối, đồng thời phân biệt **giới hạn hiển thị** với **đếm tổng số bản ghi khớp điều kiện**.

## 1. Hợp đồng truy vấn: khoảng, thứ tự và giới hạn

Giả sử BST chứa tập khóa phân biệt `S`, được so sánh bằng **một quy tắc thứ tự nhất quán**. Một truy vấn ví dụ là:

```text
RANGE(root, lo, hi, limit=L)

Chọn những khóa k sao cho:
    lo <= k < hi

Phát khóa theo thứ tự tăng dần.
Trả tối đa L phần tử đầu tiên thỏa điều kiện.
```

Trong bài, ta dùng khoảng **nửa mở** `[lo, hi)` làm mặc định: **bao gồm cận dưới**, **không bao gồm cận trên**.

Nếu dãy khóa trong khoảng theo thứ tự tăng là `q1, q2, ..., qm`, kết quả cần trả là **`min(L,m)` khóa đầu tiên**. Nếu có ít hơn `L` mục thì trả tất cả mục hiện có; nếu có nhiều hơn thì dừng ở mục thứ `L`.

Ví dụ:

```text
S = {10, 20, 25, 30, 35, 40, 50}

lo = 20
hi = 40
limit = 3

Khóa thỏa khoảng: 20, 25, 30, 35
Đầu ra giới hạn: 20, 25, 30
```

Khóa `35` **không sai điều kiện khoảng**; nó chỉ bị bỏ khỏi **trang kết quả này** vì giới hạn là ba. Khóa `40` không được trả vì khoảng có điều kiện `key < 40`.

### Những yêu cầu nên được quy định rõ trong API

- **Thứ tự:** theo khóa tăng dần, không theo thứ tự chèn và không theo giá trị đi kèm.
- **Biên:** dùng `[lo,hi)` hay một trong ba quy ước khác.
- **Giới hạn:** `L > 0`, `L = 0`, âm hoặc không truyền `L` được xử lý ra sao.
- **Kiểu trả về:** chỉ khóa, cặp `(key,value)`, iterator hay một trang kèm cursor.
- **Khóa trùng:** set/map khóa duy nhất hay multiset có nhiều bản sao.
- **Dữ liệu thay đổi:** có cần kết quả thuộc một ảnh chụp nhất quán (*snapshot*) hay chỉ đọc trạng thái hiện tại.

**Quy ước của mã Python bên dưới:** khóa là số nguyên phân biệt; `lo` và `hi` cũng là số so sánh được với khóa; `limit=None` nghĩa là không giới hạn, `limit=0` trả rỗng, và `limit < 0` báo lỗi.

## 2. Bất biến BST giúp loại cả một cây con

Một **BST hợp lệ** với khóa duy nhất thỏa:

- Mọi khóa trong **toàn bộ cây con trái** nhỏ hơn khóa của nút.
- Mọi khóa trong **toàn bộ cây con phải** lớn hơn khóa của nút.
- Hai cây con cũng thỏa quy tắc đó.

```text
                node.key = x
               /            \
   mọi khóa < x              mọi khóa > x
```

Điều này mạnh hơn việc chỉ kiểm tra hai nút con trực tiếp. Ví dụ, nếu một hậu duệ có khóa `60` bị đặt dưới cây con trái của nút `50`, bất biến đã sai dù quan hệ với cha trực tiếp của nó có thể trông đúng.

Khi tìm những khóa thuộc `[lo,hi)`, ta có thể suy luận:

| Quan hệ tại nút có khóa `x` | Cây con chắc chắn không cần duyệt | Nhánh còn có thể chứa kết quả |
| --- | --- | --- |
| `x < lo` | Toàn bộ cây con **trái** (`< x < lo`) | Đi phải |
| `x == lo` | Toàn bộ cây con **trái** (`< lo`) | Xét nút, rồi có thể đi phải |
| `lo < x < hi` | Không loại chỉ vì `x` nằm trong khoảng | Trái, nút, phải theo thứ tự |
| `x == hi` | Toàn bộ cây con **phải** (`> hi`) | Chỉ xét trái |
| `x > hi` | Toàn bộ cây con **phải** | Đi trái |

Nếu `x < lo`, **nút hiện tại** cũng không được phát. Nếu `x >= hi`, nút hiện tại cũng không được phát. Những cây con còn có khả năng chứa khóa trong khoảng phải được xử lý đúng thứ tự.

Cơ chế **cắt tỉa (*pruning*)** này là lý do một truy vấn khoảng có thể nhanh hơn quét toàn bộ `n` nút khi số kết quả ít.

## 3. Cây ví dụ xuyên suốt

Ta tạo BST bằng cách chèn lần lượt:

```text
50, 30, 75, 20, 40, 60, 90, 35, 45, 55, 70, 80
```

Cây có dạng:

```text
                         50
                       /    \
                     30      75
                    /  \    /  \
                  20   40  60   90
                      / \  / \  /
                     35 45 55 70 80
```

Nếu duyệt trung thứ tự (*in-order*: **trái → nút → phải**), dãy khóa là:

```text
20, 30, 35, 40, 45, 50, 55, 60, 70, 75, 80, 90
```

Để tìm khóa thuộc khoảng `[35,80)`, ta chọn:

```text
35, 40, 45, 50, 55, 60, 70, 75
```

Nếu đặt `limit=3`, chỉ trả:

```text
35, 40, 45
```

Nếu đổi thành `limit=6`, trả:

```text
35, 40, 45, 50, 55, 60
```

Chú ý: **giới hạn áp dụng sau điều kiện khoảng, nhưng cần được tích hợp vào quá trình duyệt** để dừng sớm. Không nên đi thăm toàn bộ cây rồi mới cắt list, nếu mục tiêu là giảm số nút cần xét.

### Bảng tình huống khác nhau

| Truy vấn | Kết quả đúng |
| --- | --- |
| `[35,80), limit=3` | `35,40,45` |
| `[42,78), limit=4` | `45,50,55,60` |
| `[30,40), limit=10` | `30,35` |
| `[80,90), limit=10` | `80` |
| `[90,91), limit=2` | `90` |
| `[91,100), limit=5` | Rỗng |
| `[35,35), limit=5` | Rỗng |
| `[35,80), limit=0` | Rỗng |

Thứ tự khóa trong kết quả vẫn **tăng nghiêm ngặt** vì ta dùng BST khóa duy nhất.

## 4. Cách đơn giản nhưng chưa tối ưu: duyệt hết rồi lọc và cắt

Một cách rất dễ viết là lấy toàn bộ khóa bằng in-order, lọc điều kiện khoảng, cuối cùng chỉ giữ `L` mục:

```python
def naive_range(all_items_sorted, lo, hi, limit):
    matching = [
        (key, value)
        for key, value in all_items_sorted
        if lo <= key < hi
    ]
    return matching[:limit]
```

Cách này **có thể đúng về mặt kết quả** nếu danh sách đã được sắp theo cùng quy tắc và `limit` không âm. Tuy nhiên, nó có những nhược điểm:

1. Phải duyệt hoặc có sẵn **toàn bộ `n` mục**, kể cả những mục ngoài khoảng.
2. Có thể tạo list lớn `O(n)` chỉ để trả vài kết quả.
3. Khi `L=3` mà cây có hàng triệu nút, cách làm trên không tận dụng được việc **đã đủ ba kết quả**.
4. Nếu phải gọi `sorted(...)` mỗi lần, còn phát sinh chi phí sắp xếp không cần thiết.

**Nguyên tắc cải thiện:** đừng chỉ giới hạn **số phần tử trả về**; hãy cố gắng giới hạn cả **công việc duyệt** bằng bất biến BST và cơ chế dừng sớm.

Trong những tập dữ liệu rất nhỏ, giải pháp đơn giản có thể vẫn đủ tốt. Nhưng đối với mục tiêu của bài học, ta ưu tiên truy vấn **`O(h+k)`** thay vì quét `O(n)`, với `h` là chiều cao BST và `k` là số kết quả thực trả.

## 5. Thuật toán đệ quy cắt tỉa cho khoảng [lo,hi)

Một phép duyệt khoảng có thể viết bằng ba quyết định tại nút `x`:

1. Nếu `x > lo`, cây con **trái** có thể chứa khóa thuộc khoảng → duyệt trái.
2. Nếu `lo <= x < hi`, phát nút.
3. Nếu `x < hi`, cây con **phải** có thể chứa khóa thuộc khoảng → duyệt phải.

Do thứ tự là **trái → nút → phải**, đầu ra vẫn tăng dần.

### Giả mã chưa có limit

```text
RANGE_INORDER(node, lo, hi):
    nếu node == null:
        return

    nếu node.key > lo:
        RANGE_INORDER(node.left, lo, hi)

    nếu lo <= node.key và node.key < hi:
        VISIT(node)

    nếu node.key < hi:
        RANGE_INORDER(node.right, lo, hi)
```

**Tại sao chỉ đi trái nếu `node.key > lo`?** Nếu `node.key <= lo` thì mọi khóa ở trái đều **nhỏ hơn `lo`**, không thể nằm trong `[lo,hi)`.

**Tại sao chỉ đi phải nếu `node.key < hi`?** Nếu `node.key >= hi` thì mọi khóa ở phải đều **lớn hơn `node.key`**, nên cũng ngoài khoảng.

### Thêm giới hạn số kết quả

Cần kiểm tra **đã đủ `L` chưa** trước khi đi sâu, sau khi duyệt trái và sau khi phát nút.

```text
RANGE_LIMITED(node, lo, hi, L):
    nếu node == null hoặc đã có L kết quả:
        return

    nếu node.key > lo:
        RANGE_LIMITED(node.left, lo, hi, L)

    nếu đã có L kết quả:
        return

    nếu lo <= node.key < hi:
        EMIT(node)

    nếu đã có L kết quả:
        return

    nếu node.key < hi:
        RANGE_LIMITED(node.right, lo, hi, L)
```

Nếu kết quả đã đủ sau khi duyệt trái, **không** được tiếp tục phát nút cha hoặc đi sang phải. Nếu đủ ngay sau khi phát nút hiện tại, **không** được thăm cây con phải của nó.

## 6. Vì sao phép cắt tỉa không bỏ sót khóa hợp lệ?

Giả sử cây đầu vào là BST hợp lệ theo thứ tự khóa.

**Trường hợp `x <= lo`:** tất cả khóa trong cây con trái đều `< x <= lo`, nên **không thể thuộc `[lo,hi)`**. Loại cả cây con trái là an toàn.

**Trường hợp `x >= hi`:** tất cả khóa trong cây con phải đều `> x >= hi`, nên **không thể thuộc `[lo,hi)`**. Loại cả cây con phải là an toàn.

**Trường hợp `lo <= x < hi`:** nút hiện tại hợp lệ. Duyệt trái trước, phát nút sau, rồi mới duyệt phải bảo đảm thứ tự tăng nhờ bất biến BST.

Lập luận áp dụng đệ quy ở mọi cây con. Khi đạt giới hạn `L`, nếu ta đã phát `L` khóa hợp lệ đầu tiên theo thứ tự tăng dần thì **mọi khóa hợp lệ chưa thăm đều lớn hơn các khóa đã phát**. Dừng lúc đó vẫn đúng hợp đồng **“trả tối đa `L` khóa đầu tiên”**.

### Hai tính chất cần phân biệt

- **Tính đúng của bộ lọc:** mọi phần tử được trả phải thỏa `lo <= key < hi`; không có mục không hợp lệ.
- **Tính đầy đủ có giới hạn:** nếu có ít nhất `L` khóa hợp lệ, phải trả **đúng `L` khóa nhỏ nhất** trong khoảng; nếu có ít hơn, phải trả **toàn bộ** số khóa hợp lệ đó.

Chỉ kiểm tra `len(output) <= L` là chưa đủ. Một thuật toán có thể trả ba khóa bất kỳ trong khoảng mà **bỏ qua ba khóa nhỏ hơn**; khi yêu cầu “các phần tử đầu tiên”, nó vẫn sai.

## 7. Python: tạo BST-map nhỏ để thử nghiệm

Đoạn mã trong phần này dùng **khóa nguyên phân biệt** và cho phép giá trị `None`. Việc tìm/chèn/duyệt luôn dựa vào **key**, không phụ thuộc `value`.

```python
class Node:
    def __init__(self, key, value=None):
        self.key = key
        self.value = value
        self.left = None
        self.right = None


def insert(root, key, value=None):
    """Trả (new_root, inserted). Key trùng thì cập nhật value."""
    if root is None:
        return Node(key, value), True

    current = root
    while True:
        if key == current.key:
            current.value = value
            return root, False

        if key < current.key:
            if current.left is None:
                current.left = Node(key, value)
                return root, True
            current = current.left
        else:
            if current.right is None:
                current.right = Node(key, value)
                return root, True
            current = current.right


root = None
keys = [50, 30, 75, 20, 40, 60, 90, 35, 45, 55, 70, 80]

for key in keys:
    root, inserted = insert(root, key, "v" + str(key))
    assert inserted

# Cập nhật giá trị không tạo khóa trùng.
root, inserted = insert(root, 40, None)
assert inserted is False

expected_keys = [20, 30, 35, 40, 45, 50, 55, 60, 70, 75, 80, 90]
```

Sau khi cập nhật `key=40` với `value=None`, hồ sơ `40` **vẫn tồn tại**. Một truy vấn khoảng phải trả cặp `(40,None)` nếu khóa `40` nằm trong biên. Không được coi `value=None` là dấu thiếu khóa.

## 8. Python: truy vấn khoảng đệ quy có giới hạn

Hàm dưới đây đúng với khoảng `[lo,hi)` và hỗ trợ giới hạn không âm. Nó **dừng đệ quy khi đã đủ kết quả**.

```python
def range_recursive_limited(root, lo, hi, limit=None):
    """Các (key,value) đầu tiên trong [lo,hi), tối đa limit."""
    if limit is not None and limit < 0:
        raise ValueError("limit không được âm")

    if lo >= hi or limit == 0:
        return []

    result = []

    def visit(node):
        if node is None:
            return
        if limit is not None and len(result) >= limit:
            return

        if node.key > lo:
            visit(node.left)

        if limit is not None and len(result) >= limit:
            return

        if lo <= node.key < hi:
            result.append((node.key, node.value))

        if limit is not None and len(result) >= limit:
            return

        if node.key < hi:
            visit(node.right)

    visit(root)
    return result


assert [k for k, _ in range_recursive_limited(root, 35, 80, 3)] == [
    35, 40, 45
]
assert [k for k, _ in range_recursive_limited(root, 42, 78, 4)] == [
    45, 50, 55, 60
]
assert range_recursive_limited(root, 35, 35, 3) == []
assert range_recursive_limited(root, 35, 80, 0) == []
assert range_recursive_limited(None, 35, 80, 3) == []

assert range_recursive_limited(root, 40, 41, 1) == [(40, None)]
```

### Cái gì xảy ra khi limit không đủ?

```python
all_small = range_recursive_limited(root, 30, 40, limit=10)
assert [k for k, _ in all_small] == [30, 35]

all_matching = range_recursive_limited(root, 35, 80, limit=None)
assert [k for k, _ in all_matching] == [
    35, 40, 45, 50, 55, 60, 70, 75
]
```

Nếu chỉ có hai khóa trong khoảng mà `limit=10`, kết quả chỉ có hai mục, không đệm bằng khóa ngoài khoảng và không lặp khóa.

**Đánh đổi:** mã đệ quy dễ liên hệ với LNR, nhưng dùng `O(h)` call stack và có thể vượt giới hạn đệ quy trên BST rất lệch. Để xây iterator phân trang, bản lặp dùng stack tường minh sẽ thuận tiện hơn.

## 9. Lower bound: bắt đầu ngay tại khóa đầu tiên >= lo

Một cách khác để truy vấn khoảng là:

1. Tìm **lower bound** của `lo`: khóa nhỏ nhất `>= lo`.
2. Duyệt in-order từ vị trí đó, theo thứ tự tăng.
3. Dừng nếu khóa đạt `hi` hoặc số mục đầu ra đạt `limit`.

Đối với BST khóa duy nhất:

- **Lower bound của `x`:** khóa nhỏ nhất `>= x`.
- **Upper bound của `x`:** khóa nhỏ nhất `> x`.

Với khoảng `[lo,hi)`, phần tử đầu tiên nên là **lower_bound(lo)**. Phần tử `hi`, nếu có, phải bị loại. Vì vậy điểm kết thúc không lấy tương đương **lower_bound(hi)**, không phải **upper_bound(hi)**.

### Tìm cận dưới theo đường ứng viên

```text
LOWER_BOUND(root, lo):
    candidate = null
    node = root

    while node != null:
        if node.key >= lo:
            candidate = node
            node = node.left
        else:
            node = node.right

    return candidate
```

Nếu `node.key >= lo`, đây là ứng viên hợp lệ; ta thử tìm một khóa hợp lệ **nhỏ hơn** ở cây con trái. Nếu `node.key < lo`, nút và cả cây con trái không hợp lệ; chỉ cần xét cây con phải.

Nhưng khi muốn **liệt kê tiếp nhiều khóa**, chỉ giữ một tham chiếu tới nút lower bound là chưa đủ nếu BST **không có liên kết `parent`**. Ta nên giữ một **stack đường đi** để biết nút nào cần phát tiếp theo.

## 10. Python: iterator in-order bắt đầu tại một cận

Hàm sau nhận mốc `bound` và một cờ:

- `inclusive=True`: phát từ khóa đầu tiên **`>= bound`**.
- `inclusive=False`: phát từ khóa đầu tiên **`> bound`**.

Đây là nền tảng để thực hiện **lower bound**, **upper bound**, truy vấn khoảng và phân trang theo cursor.

```python
def iter_from_bound(root, bound, inclusive=True):
    """Sinh các Node theo khóa tăng, từ >=bound hoặc >bound."""
    stack = []
    current = root

    # Định vị ứng viên đầu tiên và giữ tổ tiên cần thăm.
    while current is not None:
        eligible = (
            current.key > bound
            or (inclusive and current.key == bound)
        )

        if eligible:
            stack.append(current)
            current = current.left
        else:
            current = current.right

    # In-order tiếp tục từ ứng viên đầu tiên.
    while stack:
        node = stack.pop()
        yield node

        current = node.right
        while current is not None:
            stack.append(current)
            current = current.left


assert [n.key for n in iter_from_bound(root, 40, True)][:4] == [
    40, 45, 50, 55
]
assert [n.key for n in iter_from_bound(root, 40, False)][:4] == [
    45, 50, 55, 60
]
assert [n.key for n in iter_from_bound(root, 42)][:3] == [
    45, 50, 55
]
assert list(iter_from_bound(root, 100)) == []
```

### Vì sao stack này cho đúng thứ tự?

Trong giai đoạn định vị:

- Khi nút `>= bound` (hoặc `> bound` nếu strict), ta **đẩy nút đó** vì nó có thể cần phát sau cây con trái.
- Khi nút chưa thỏa cận, **cả cây con trái không thể thỏa**, nên ta bỏ qua nó và đi phải.

Nút trên đỉnh stack sau giai đoạn đầu là **ứng viên nhỏ nhất**. Sau khi phát, ta tiếp tục đi vào cây con phải và đẩy đường trái, đúng quy tắc in-order.

Mỗi nút được đẩy và lấy ra **tối đa một lần** trong toàn bộ lượt duyệt. Nhờ đó, việc đọc liên tiếp `k` mục sau khi tìm cận dưới có tổng chi phí khoảng `O(h+k)`.

## 11. Python: truy vấn khoảng dạng lặp, có limit thực sự

Dùng iterator vừa tạo, hàm sau chỉ giữ tối đa `limit` cặp kết quả. Nó không xây danh sách toàn cây.

```python
def range_limited(root, lo, hi, limit=None):
    """Danh sách có thứ tự, key thuộc [lo,hi), tối đa limit mục."""
    if limit is not None and limit < 0:
        raise ValueError("limit không được âm")

    if lo >= hi or limit == 0:
        return []

    result = []

    for node in iter_from_bound(root, lo, inclusive=True):
        if node.key >= hi:
            break

        result.append((node.key, node.value))

        if limit is not None and len(result) >= limit:
            break

    return result


assert [k for k, _ in range_limited(root, 35, 80, 3)] == [
    35, 40, 45
]
assert [k for k, _ in range_limited(root, 42, 78, 4)] == [
    45, 50, 55, 60
]
assert [k for k, _ in range_limited(root, 30, 40, 10)] == [
    30, 35
]
assert range_limited(root, 90, 90, 3) == []
assert range_limited(root, 91, 100, 5) == []
assert range_limited(root, 35, 80, 0) == []
assert range_limited(None, 35, 80, 4) == []
assert range_limited(root, 40, 41, 2) == [(40, None)]
```

### Khi limit âm

Theo hợp đồng bài này, giới hạn âm là **lỗi tham số**, không có nghĩa “lấy từ cuối” như cú pháp cắt list Python:

```python
try:
    range_limited(root, 30, 80, -1)
except ValueError:
    pass
else:
    raise AssertionError("Phải từ chối limit âm")
```

Đây là một lựa chọn API có chủ đích. Trong hệ thống thực tế, có thể quy định `limit` phải là số nguyên dương và đặt **trần kích thước trang** để tránh yêu cầu đầu ra quá lớn.

### Tại sao không chỉ cắt list sau khi duyệt?

Hàm trên **break ngay sau mục thứ `limit`**. Generator dừng và không tiếp tục duyệt những nút còn lại. Nếu chỉ viết `all_items[:limit]` sau khi đã gọi hàm dựng toàn bộ `all_items`, số phần tử đầu ra tuy nhỏ nhưng công việc duyệt vẫn lớn.

## 12. Bốn kiểu biên khoảng và dấu so sánh

Khi nhận yêu cầu từ người dùng, phải biết cận dưới/cận trên **có bao gồm giá trị bằng biên hay không**.

| Khoảng | Vị trí bắt đầu | Điều kiện dừng khi duyệt tăng |
| --- | --- | --- |
| `[lo,hi)` | **lower_bound(lo)**: `key >= lo` | `key >= hi` |
| `[lo,hi]` | **lower_bound(lo)**: `key >= lo` | `key > hi` |
| `(lo,hi)` | **upper_bound(lo)**: `key > lo` | `key >= hi` |
| `(lo,hi]` | **upper_bound(lo)**: `key > lo` | `key > hi` |

Ví dụ với `S={20,30,35,40,45,50}`, `lo=30` và `hi=45`:

```text
[30,45) -> 30, 35, 40
[30,45] -> 30, 35, 40, 45
(30,45) -> 35, 40
(30,45] -> 35, 40, 45
```

Nếu `lo == hi`, ba khoảng `[lo,hi)`, `(lo,hi)` và `(lo,hi]` rỗng. Riêng **`[lo,lo]`** có thể chứa **một khóa bằng `lo`**, nếu khóa ấy có trong BST.

### Hàm dùng chung cho cả bốn kiểu biên

```python
def range_with_edges(
    root, lo, hi, limit=None,
    include_lo=True, include_hi=False
):
    if limit is not None and limit < 0:
        raise ValueError("limit không được âm")

    if lo > hi or limit == 0:
        return []

    if lo == hi and not (include_lo and include_hi):
        return []

    result = []

    for node in iter_from_bound(
        root, lo, inclusive=include_lo
    ):
        if node.key > hi or (
            node.key == hi and not include_hi
        ):
            break

        result.append((node.key, node.value))
        if limit is not None and len(result) >= limit:
            break

    return result


assert [k for k, _ in range_with_edges(root, 30, 45)] == [
    30, 35, 40
]
assert [k for k, _ in range_with_edges(
    root, 30, 45, include_hi=True
)] == [30, 35, 40, 45]
assert [k for k, _ in range_with_edges(
    root, 30, 45, include_lo=False
)] == [35, 40]
assert [k for k, _ in range_with_edges(
    root, 40, 40, include_hi=True
)] == [40]
```

Hàm áp dụng cùng một thứ tự so sánh cho các phép chèn và truy vấn. Không nên tự chuyển chuỗi thời gian sang số ở một nơi và so chuỗi từ điển ở nơi khác mà không định nghĩa rõ quy tắc khóa.

## 13. Giới hạn đầu ra khác với đếm tổng số kết quả

Giả sử truy vấn `[35,80)` có **8 khóa** nhưng `limit=3`. Phần đầu ra là:

```text
items = [35,40,45]
```

Từ riêng danh sách này, không thể kết luận **tổng số khóa hợp lệ chỉ có ba**. Có thể còn nhiều kết quả hợp lệ chưa được duyệt.

Cần tách ba khái niệm:

| Tên thông tin | Ý nghĩa | Cần làm bao nhiêu việc? |
| --- | --- | --- |
| `returned_count` | Số mục thực sự đã trả, tối đa `L` | Có ngay từ list kết quả |
| `has_more` | Có ít nhất **một** mục hợp lệ khác sau trang hiện tại hay không | Có thể xem trước thêm **một** mục |
| `total_matches` | Tổng **mọi** mục trong khoảng, kể cả chưa trả | Thường phải đếm cả khoảng, trừ khi có chỉ mục/metadata hỗ trợ |

**`len(items) == limit` không chứng minh `has_more=True`.** Có thể đúng bằng `limit` mục hợp lệ rồi hết.

### Cách biết has_more mà không đọc cả khoảng

Một kỹ thuật phổ biến là lấy tối đa **`L+1` mục hợp lệ**:

- Nếu thấy thêm một mục thứ `L+1`, `has_more=True`.
- Nếu không có mục ấy, `has_more=False`.
- Chỉ trả **`L` mục đầu**, giữ mục thêm làm bằng chứng rằng còn dữ liệu.

Việc nhìn trước một mục tăng một lượng công việc hằng số so với giới hạn `L`, không bắt buộc duyệt toàn cây.

Nếu người dùng thực sự muốn `total_matches`, chỉ biết `has_more` không đủ; phải dùng một cách đếm riêng.

### Khi nào có thể đếm số khóa theo khoảng nhanh hơn?

Một **BST có metadata `subtree_size` chính xác** có thể hỗ trợ:

```text
rank_lt(x) = số khóa < x

count([lo,hi)) = rank_lt(hi) - rank_lt(lo)
```

Tính `rank_lt` chỉ cần một đường từ gốc nếu mỗi nút biết kích thước cây con trái, nên đếm khoảng có thể thực hiện trong `O(h)`. Tuy nhiên, phải **duy trì chính xác `subtree_size` khi chèn, xóa, quay cây**. BST đơn giản trong bài không lưu metadata này, vì vậy không thể tự nhận có truy vấn đếm `O(h)`.

## 14. Phân trang theo khóa: cursor thay vì offset lớn

Giả sử có hàng nghìn kết quả trong khoảng và giao diện chỉ hiển thị **`page_size=3`**. Người dùng muốn xem trang tiếp theo.

Một cách là lấy hết các khóa, rồi cắt theo **offset**:

```text
Trang 1: bỏ 0, lấy 3
Trang 2: bỏ 3, lấy 3
Trang 3: bỏ 6, lấy 3
...
```

Nếu mỗi lần duyệt từ đầu, trang có offset lớn phải **bỏ qua nhiều mục**, tốn thời gian vô ích.

Với BST có thứ tự, ta có thể dùng **keyset pagination**:

- Trang đầu: lấy các khóa `>= lo`.
- Ghi **khóa cuối cùng đã trả** vào `cursor`.
- Trang sau: lấy các khóa **`> cursor`** (không cho phép bằng), vẫn phải `< hi`.
- Lặp lại cho tới khi không còn mục hợp lệ.

Ví dụ:

```text
Khoảng [35,80), mỗi trang 3 mục

Trang 1: 35, 40, 45      cursor = 45
Trang 2: 50, 55, 60      cursor = 60
Trang 3: 70, 75          hết kết quả
```

**Vì sao trang tiếp theo phải dùng dấu `>`?** Nếu dùng `>= cursor`, khóa cuối của trang trước sẽ **bị lặp lại** ở trang sau.

### Cursor cho khóa không còn tồn tại

Nếu một khóa cursor bị xóa giữa hai lần yêu cầu, việc tìm **khóa đầu tiên `> cursor`** vẫn có ý nghĩa, vì ta đang so sánh theo giá trị khóa, không đòi nút mang cursor còn tồn tại. Tuy nhiên, không được nhầm điều này với bảo đảm ảnh chụp dữ liệu nhất quán khi có sửa đổi đồng thời.

## 15. Python: API phân trang có cursor và has_more chính xác

Ta dùng `iter_from_bound` đã xây, với `inclusive=False` cho trang sau.

Hàm trả về:

- `items`: tối đa `page_size` cặp `(key,value)`;
- `has_more`: còn ít nhất một khóa hợp lệ **sau các mục đã trả** tại thời điểm duyệt;
- `next_after`: khóa cuối đã trả nếu `has_more=True`; ngược lại là `None`.

```python
def range_page(root, lo, hi, page_size, after=None):
    if page_size <= 0:
        raise ValueError("page_size phải là số nguyên dương")

    if lo >= hi:
        return {
            "items": [], "has_more": False, "next_after": None
        }

    if after is None or after < lo:
        # Trang đầu, hoặc cursor nằm trước khoảng.
        bound, inclusive = lo, True
    else:
        # Trang tiếp theo: loại chính khóa cursor.
        bound, inclusive = after, False

    items = []

    for node in iter_from_bound(root, bound, inclusive):
        if node.key >= hi:
            break

        # Đã có đủ page_size mục: nút hiện tại là lookahead.
        if len(items) == page_size:
            return {
                "items": items,
                "has_more": True,
                "next_after": items[-1][0],
            }

        items.append((node.key, node.value))

    return {
        "items": items,
        "has_more": False,
        "next_after": None,
    }


p1 = range_page(root, 35, 80, 3)
assert [k for k, _ in p1["items"]] == [35, 40, 45]
assert p1["has_more"] is True
assert p1["next_after"] == 45

p2 = range_page(root, 35, 80, 3, after=p1["next_after"])
assert [k for k, _ in p2["items"]] == [50, 55, 60]
assert p2["has_more"] is True
assert p2["next_after"] == 60

p3 = range_page(root, 35, 80, 3, after=p2["next_after"])
assert [k for k, _ in p3["items"]] == [70, 75]
assert p3["has_more"] is False
assert p3["next_after"] is None
```

### Vì sao has_more của trang đầy không được đoán từ độ dài?

Kiểm thử khi số mục hợp lệ **đúng bằng kích thước trang**:

```python
exact = range_page(root, 35, 50, 3)

assert [k for k, _ in exact["items"]] == [35, 40, 45]
assert exact["has_more"] is False
assert exact["next_after"] is None
```

Không có khóa nào khác trong `[35,50)`, dù trang đã đầy ba mục. Hàm trả `has_more=False` vì nó không thấy mục thứ tư hợp lệ.

### Chi phí của việc xem trước

Để kết luận có trang sau, hàm có thể đọc **một khóa hợp lệ ngoài số `page_size` đã trả**. Phân tích độ phức tạp vẫn là **`O(h+L)`** với `L = page_size` (hoặc viết chi tiết `O(h+L+1)`), không cần quét cả khoảng.

Bộ nhớ phụ: `O(h)` cho stack và `O(L)` cho list đầu ra.

### Nếu muốn API chỉ trả kết quả, không cần phân trang

`range_limited` ở phần 11 có thể dừng đúng ngay sau `L` mục mà **không cần lookahead**. Như vậy, để biết `has_more` chính xác, ta chấp nhận một lượng công việc bổ sung nhỏ.

## 16. Định nghĩa cursor ổn định khi khóa không duy nhất

Một BST-map có **một nút cho mỗi khóa phân biệt** phù hợp với cursor là **khóa cuối cùng**.

Nhưng dữ liệu thực tế có thể có **nhiều bản ghi cùng giá trị khóa sắp xếp**, ví dụ nhiều buổi học bắt đầu cùng lúc:

```text
(start_minute=540, id="A")
(start_minute=540, id="B")
(start_minute=540, id="C")
(start_minute=600, id="D")
```

Nếu chỉ dùng `start_minute=540` làm cursor và trang đầu trả `A`, trang sau tìm `start_minute > 540` sẽ **bỏ mất B và C**.

Một cách giải quyết là dùng **khóa ghép duy nhất**:

```text
key = (start_minute, unique_id)
```

Ví dụ thứ tự tuple tăng:

```text
(540, "A"), (540, "B"), (540, "C"), (600, "D")
```

Cursor phải lưu **toàn bộ khóa ghép của mục cuối**, ví dụ `(540, "A")`. Trang tiếp theo tìm khóa **lớn hơn tuple đó**, nên vẫn có thể trả `(540, "B")`, `(540, "C")`.

### Quy tắc cho comparator

Nếu cây được sắp theo một comparator tùy biến, cursor phải biểu diễn một vị trí **được so sánh bằng chính comparator ấy**. Không thể xây cây theo `(time,id)` mà phân trang chỉ theo `time` rồi kỳ vọng không bỏ sót bản ghi có cùng thời gian.

Nếu dùng multiset với các bản sao **không phân biệt được bởi khóa**, cần một chính sách iterator/cursor xử lý bản sao, hoặc thêm thành phần định danh/thứ tự để tạo khóa duy nhất cho mục cần phân trang.

## 17. Phân trang và dữ liệu thay đổi giữa các lượt đọc

Một cursor theo khóa là cách phân trang hiệu quả, **không tự tạo ra snapshot nhất quán**.

Giả sử sau trang đầu với cursor `45`:

- Một khóa mới `42` được chèn: nó nằm **trước cursor** nên trang sau bắt đầu `>45` sẽ không phát khóa ấy.
- Một khóa mới `52` được chèn: nó nằm **sau cursor** nên có thể xuất hiện ở trang sau.
- Khóa `50` bị xóa: trang sau sẽ bỏ qua `50` và phát khóa tiếp theo.
- Giá trị của khóa `55` thay đổi: trang sau có thể thấy giá trị mới.

Do đó, cần phân biệt:

- **Đọc theo thứ tự trên trạng thái hiện tại:** cursor theo khóa thường hợp lý.
- **Đọc chính xác một ảnh chụp dữ liệu tại thời điểm bắt đầu:** cần snapshot, transaction/versioning hoặc một cơ chế nhất quán do hệ thống cung cấp.

Cả hai hướng đều có thể đúng tùy nghiệp vụ. Ví dụ xuất báo cáo học kỳ có thể yêu cầu dữ liệu ổn định, trong khi danh sách công việc cập nhật liên tục có thể chấp nhận dữ liệu thay đổi theo từng trang.

**Lưu ý khi dùng generator:** nếu cây bị sửa trong khi generator đang tạm dừng giữa các lần phát, các tham chiếu và stack cũ có thể không còn phù hợp. Mã trong bài giả định **không sửa cấu trúc cây trong một lượt duyệt đang diễn ra**.

## 18. Độ phức tạp thời gian và bộ nhớ

Gọi:

- `n`: số nút trong BST.
- `h`: chiều cao cây tính bằng số nút trên đường dài nhất (cây rỗng có `h=0`).
- `m`: tổng số khóa thực sự nằm trong khoảng truy vấn.
- `L`: giới hạn đầu ra; `k = min(L,m)` khi `L` hữu hạn, không âm.

Giả định so sánh khóa và xử lý một phần tử là `O(1)`.

| Cách truy vấn | Thời gian | Bộ nhớ phụ điều hướng | Bộ nhớ đầu ra |
| --- | --- | --- | --- |
| Duyệt toàn cây rồi lọc | `O(n)` | `O(h)` nếu duyệt bằng stack | Có thể `O(n)` nếu gom toàn bộ trước |
| Đệ quy cắt tỉa không giới hạn | `O(h+m)` | `O(h)` call stack | `O(m)` |
| Đệ quy cắt tỉa với limit | `O(h+k)` nếu `L>0` | `O(h)` | `O(k)` |
| Lower bound + iterator giới hạn | `O(h+k)` nếu `L>0` | `O(h)` stack | `O(k)` |
| Trang có has_more và xem trước | `O(h+L+1)` giới hạn trên | `O(h)` | `O(L)` |
| Duyệt khoảng rồi đếm toàn bộ | `O(h+m)` | `O(h)` | `O(1)` nếu chỉ đếm |
| Đếm bằng rank có metadata `subtree_size` | `O(h)` | `O(1)` nếu triển khai lặp | `O(1)` |

Các trường hợp `limit=0` hoặc khoảng rõ ràng rỗng có thể trả ngay trong **`O(1)`** trước khi duyệt.

### Vì sao là O(h+k), không phải O(n) trong mọi trường hợp?

Cắt tỉa giúp loại nguyên các cây con chắc chắn ngoài khoảng. Những nút được xét nhưng không phát chủ yếu thuộc **đường đi biên**; số bước biên được chặn bởi chiều cao `h`, trong khi mỗi khóa được phát góp phần vào `k`.

Với iterator, tìm lower bound mất tối đa `O(h)`; sau đó mỗi nút được đẩy/lấy khỏi stack tối đa một lần, nên phát `k` kết quả liên tiếp mất tổng `O(k)` theo phân tích khấu hao, cộng một bước xem trước nếu cần.

### Cây cân bằng và cây lệch

- **BST cân bằng:** `h = O(log n)`, nên truy vấn giới hạn `L` có thể đạt **`O(log n+k)`**.
- **BST không cân bằng:** trường hợp xấu `h = Θ(n)`; truy vấn rất ít kết quả vẫn có thể đi một đường dài `Θ(n)`.
- Việc chỉ trả `k=3` mục không đồng nghĩa toàn bộ truy vấn luôn **`O(3)`**, vì cần chi phí **định vị cận**.

Nếu khóa là chuỗi dài hoặc comparator phức tạp, một lần so sánh có thể tốn tới `O(C)` thay vì `O(1)`; khi đó cần tính thêm chi phí của comparator trong các bước điều hướng.

### Chi phí khi phân trang nhiều lần từ gốc

Nếu mỗi trang khởi động lại iterator và tìm cursor từ gốc, với `P` trang và tổng `M` mục được phát, tổng chi phí cỡ **`O(P·h + M)`**. Nếu có thể duy trì một iterator an toàn xuyên suốt lượt đọc, chi phí duyệt có thể gần `O(h+M)`, nhưng cần giải quyết vòng đời iterator và việc sửa cây trong lúc đọc.

Đây là một đánh đổi thực tế giữa **API phân trang độc lập theo cursor** và **một iterator có trạng thái**.

## 19. Ứng dụng: giới hạn danh sách bài kiểm tra theo thời gian

Giả sử ứng dụng lưu mỗi buổi kiểm tra bằng khóa `(start_minute, exam_id)`, vì nhiều bài kiểm tra có thể có cùng phút bắt đầu. Người dùng chọn khoảng **[09:00,12:00)** và chỉ muốn 5 mục đầu.

Chính sách có thể là:

- Chuẩn hóa thời gian theo cùng đơn vị và múi giờ.
- Dùng khóa ghép phân biệt các bài thi cùng thời điểm.
- Tìm cận dưới ứng với 09:00.
- Duyệt tăng dần, dừng khi thời gian đạt 12:00 hoặc khi đã đủ 5 mục.
- Trả `next_after` là **toàn bộ khóa ghép cuối** nếu còn mục trên trang sau.

Trong một hệ thống làm báo cáo định kỳ, còn cần xác định có yêu cầu **snapshot** không. Nếu danh sách chỉ phục vụ giao diện xem nhanh, keyset pagination thường đơn giản và hiệu quả. Nếu cần danh sách kiểm toán chính xác tại một thời điểm, nên dùng cơ chế truy vấn nhất quán của cơ sở dữ liệu thay vì chỉ dựa vào cursor của BST.

### Khi nào không cần BST?

- **Mảng đã sắp:** tìm cận bằng tìm nhị phân `O(log n)` và đọc `k` mục tiếp theo `O(k)`; tốt khi dữ liệu ít cập nhật.
- **Hash map:** truy vấn khóa chính xác thường nhanh trung bình, nhưng không có thứ tự khóa mặc định để thực hiện range query hiệu quả.
- **BST tự cân bằng:** thích hợp nếu cần nhiều thao tác chèn/xóa kết hợp truy vấn khoảng, với thời gian định vị logarit trong trường hợp xấu nhất.
- **B-tree/B+ tree và chỉ mục cơ sở dữ liệu:** thường phù hợp hơn cho tập dữ liệu lớn lưu trên đĩa và các truy vấn có phân trang; chọn theo hệ thống thực tế.

**Chọn cấu trúc dữ liệu theo hợp đồng thao tác**, không chỉ theo độ phức tạp của một lần `search(key)`.

## 20. Các trường hợp biên và lỗi thường gặp

1. **Cây rỗng:** truy vấn phải trả danh sách rỗng.
2. **`lo == hi` với khoảng `[lo,hi)`:** khoảng rỗng, không cần duyệt.
3. **`lo > hi`:** nên trả rỗng theo hợp đồng hoặc báo lỗi rõ ràng; mã trong bài trả rỗng.
4. **`limit=0`:** trả rỗng ngay, không cần tìm lower bound.
5. **`limit<0`:** không dùng ngữ nghĩa cắt list Python; mã báo `ValueError`.
6. **Có ít mục hơn limit:** trả các mục hiện có, không đệm hoặc lặp dữ liệu.
7. **Khóa bằng cận dưới:** phải được phát trong `[lo,hi)`.
8. **Khóa bằng cận trên:** phải bị loại trong `[lo,hi)`.
9. **Dừng sau limit nhưng không đúng thứ tự:** phải trả **`L` khóa nhỏ nhất**, không phải `L` khóa bất kỳ trong khoảng.
10. **Duyệt toàn cây rồi mới cắt list:** đầu ra nhỏ nhưng thời gian/bộ nhớ trung gian vẫn có thể lớn.
11. **Dùng upper_bound(hi) để kết thúc `[lo,hi)`:** có thể lấy thừa khóa bằng `hi`.
12. **Không cắt tỉa cây con ngoài khoảng:** tốn thời gian xét nhiều nút không cần thiết.
13. **Quên trường hợp `value=None`:** khóa vẫn tồn tại dù giá trị gắn với nó rỗng.
14. **Dùng comparator khác giữa chèn và truy vấn:** có thể rẽ sai nhánh hoặc sai thứ tự.
15. **Cho rằng BST luôn có chiều cao `O(log n)`:** BST thường có thể lệch thành chuỗi.
16. **Nhầm giới hạn với tổng số kết quả:** `len(items)==limit` không suy ra `has_more=True`.
17. **Không xem trước mục `L+1` nhưng vẫn báo chắc chắn còn trang sau:** thiếu căn cứ.
18. **Trang sau dùng `>= cursor`:** lặp khóa cuối trang trước.
19. **Cursor không phân biệt các bản ghi cùng khóa sắp xếp:** có thể bỏ sót bản ghi cùng thời gian/điểm.
20. **Thay đổi dữ liệu giữa các trang nhưng giả định là snapshot:** kết quả có thể phản ánh nhiều thời điểm khác nhau.
21. **Sửa cây trong khi generator đang mở:** các liên kết đã lưu có thể không còn phản ánh thứ tự.
22. **Duyệt và lưu mọi mục chỉ để biết số lượng:** nên phân biệt nhu cầu `has_more`, `total_matches` và metadata `subtree_size`.

## 21. Kiểm thử độc lập bằng danh sách đã sắp

Để xác minh kết quả trên cây nhỏ, ta có thể so sánh với mô hình tham chiếu lấy từ **dãy khóa đã sắp**, sử dụng thao tác list chậm hơn nhưng dễ tin cậy.

```python
reference = {key: "v" + str(key) for key in keys}
reference[40] = None

def expected_range(reference, lo, hi, limit=None):
    ordered = [
        (key, reference[key])
        for key in sorted(reference)
        if lo <= key < hi
    ]
    return ordered if limit is None else ordered[:limit]


queries = [
    (35, 80, 1),
    (35, 80, 3),
    (35, 80, 99),
    (42, 78, 4),
    (30, 40, 10),
    (90, 90, 5),
    (91, 100, 3),
    (35, 80, 0),
]

for lo, hi, limit in queries:
    expected = expected_range(reference, lo, hi, limit)
    assert range_recursive_limited(root, lo, hi, limit) == expected
    assert range_limited(root, lo, hi, limit) == expected

# Không giới hạn:
assert range_limited(root, 35, 80) == expected_range(
    reference, 35, 80
)
```

### Kiểm thử phân trang mà không lặp/bỏ sót

```python
def collect_pages(root, lo, hi, page_size):
    collected = []
    cursor = None

    while True:
        page = range_page(root, lo, hi, page_size, after=cursor)
        collected.extend(page["items"])

        if not page["has_more"]:
            break

        cursor = page["next_after"]

    return collected


assert collect_pages(root, 35, 80, 3) == expected_range(
    reference, 35, 80
)
assert collect_pages(root, 35, 80, 1) == expected_range(
    reference, 35, 80
)
assert collect_pages(root, 91, 100, 3) == []
```

Ở đây cây **không bị thay đổi giữa các trang**. Trường hợp có cập nhật concurrent cần một kiểm thử/hợp đồng riêng về snapshot hoặc độ tươi của dữ liệu.

Đây là **các bài kiểm thử minh họa để người học chạy**; chúng không thay thế quy trình Content QA chuyên môn của module.

## 22. Tự luyện tập

**Bài 1.** Với cây mẫu ở phần 3, liệt kê mọi khóa thuộc `[35,80)`. Nếu `limit=4`, kết quả là gì và khóa nào không được trả vì giới hạn?

**Bài 2.** Trên cùng cây, tính kết quả của `[30,50)` khi `limit=2`, `limit=10` và `limit=0`.

**Bài 3.** Vì sao ở nút có khóa `x <= lo` có thể bỏ toàn bộ cây con trái khi truy vấn `[lo,hi)`? Vì sao khi `x >= hi` có thể bỏ cây con phải?

**Bài 4.** Một chương trình duyệt in-order toàn bộ cây rồi cắt 3 mục đầu. Kết quả có thể đúng không? Vì sao nó không đạt được mục tiêu dừng công việc ngay khi đủ kết quả?

**Bài 5.** Viết giả mã đệ quy cắt tỉa và dừng sớm sau `L` mục, đảm bảo không duyệt cây con phải khi đã đủ kết quả từ phần trái.

**Bài 6.** Với `S={10,20,25,30,35,40}`, giải thích khác biệt kết quả của `[20,35)`, `[20,35]`, `(20,35)` và `(20,35]`.

**Bài 7.** Vì sao `lower_bound(lo)` phù hợp cho điểm bắt đầu `[lo,hi)`? Vì sao không nên dùng `upper_bound(lo)` khi cận dưới bao gồm bằng?

**Bài 8.** Một lời gọi `range_limited(root,35,80,3)` trả đủ 3 mục. Có thể khẳng định còn trang sau không? Làm sao kiểm tra chính xác chỉ bằng một lần xem trước?

**Bài 9.** Với khoảng `[35,80)` và `page_size=3`, hãy mô tả ba trang theo cursor và giá trị `has_more` của từng trang.

**Bài 10.** Một ứng dụng có các mục `(540,"A"), (540,"B"), (540,"C"), (600,"D")`. Nếu phân trang theo mỗi `start_minute`, điều gì xảy ra khi trang đầu chỉ trả `A`? Hãy đề xuất khóa/cursor đúng.

**Bài 11.** Khi cây cân bằng có `n` nút, chiều cao `h=O(log n)`, truy vấn chỉ lấy `k` khóa đầu tiên trong khoảng có thời gian nào? Điều gì thay đổi khi BST lệch?

**Bài 12.** So sánh `returned_count`, `has_more` và `total_matches`. Trường `subtree_size` có thể giúp tính `total_matches` như thế nào?

**Bài 13.** Vì sao không thể mặc định keyset pagination sẽ trả cùng một snapshot nếu có thao tác chèn/xóa giữa các trang?

**Bài 14.** Viết hàm `range_with_edges` cho cả bốn kiểu biên và thử với `lo==hi`; trường hợp nào có thể trả một khóa?

**Bài 15.** Một cây chứa khóa `35` nhưng value bằng `None`. Truy vấn khoảng có chứa `35` nên trả gì? Tại sao không được xem là khóa thiếu?

<details>
<summary>Đáp án và gợi ý</summary>

1. Toàn bộ `[35,80)`: `35,40,45,50,55,60,70,75`. Với limit 4: `35,40,45,50`; các khóa `55,60,70,75` vẫn thuộc khoảng nhưng không có trong trang đầu.
2. `[30,50)` chứa `30,35,40,45`. Limit 2: `30,35`; limit 10: cả bốn khóa; limit 0: rỗng.
3. Vì mọi khóa ở trái `< x <= lo` nên đều nhỏ hơn cận dưới; mọi khóa ở phải `> x >= hi` nên ngoài cận trên.
4. Có thể đúng về mặt đầu ra, nhưng vẫn phải duyệt `O(n)` nút và có thể dùng `O(n)` bộ nhớ trung gian trước khi cắt; cần dừng sớm trong chính quá trình duyệt.
5. Khi vào hàm, nếu rỗng hoặc đã đủ `L` thì return; nếu `node.key > lo` thì duyệt trái; kiểm tra limit; nếu nằm trong `[lo,hi)` thì phát; kiểm tra limit; nếu `node.key < hi` thì duyệt phải.
6. `[20,35)`: `20,25,30`; `[20,35]`: thêm `35`; `(20,35)`: `25,30`; `(20,35]`: `25,30,35`.
7. Lower bound lấy phần tử đầu tiên `>= lo`, gồm khóa bằng biên; upper bound lấy `> lo` nên sẽ bỏ mất khóa `lo` nếu tồn tại.
8. Không. Có thể khoảng chỉ chứa đúng ba mục. Cần thử đọc thêm phần tử hợp lệ thứ tư; nếu có thì `has_more=True`, nếu không thì `False`.
9. Trang 1: `35,40,45`, cursor 45, has_more True. Trang 2: `50,55,60`, cursor 60, has_more True. Trang 3: `70,75`, has_more False.
10. Cursor chỉ là `540` khiến trang sau `>540` bỏ `B,C`. Dùng khóa ghép duy nhất `(start_minute, unique_id)`, cursor đầy đủ `(540,"A")`; trang sau tiếp tục ở `(540,"B")`.
11. `O(log n+k)` khi cân bằng; BST lệch có thể `h=Θ(n)` nên truy vấn có thể tốn `O(n+k)` (trong đó `k <= n`).
12. `returned_count` là số mục đã trả; `has_more` chỉ cho biết còn ít nhất một mục; `total_matches` là số mục thuộc cả khoảng. Với metadata size, đếm bằng `rank_lt(hi)-rank_lt(lo)` trong `O(h)`.
13. Cursor bảo đảm vị trí theo khóa, không tự cố định phiên bản dữ liệu; khóa mới phía trước cursor có thể bị bỏ qua, khóa phía sau có thể xuất hiện ở trang tiếp theo.
14. Có thể dùng `iter_from_bound(root,lo,include_lo)` rồi dừng ở cận trên theo `include_hi`. Khi `lo==hi`, chỉ khoảng đóng `[lo,lo]` có thể chứa một mục bằng `lo`; ba khoảng còn lại rỗng.
15. Trả `(35,None)` nếu `35` nằm trong khoảng và chưa vượt giới hạn. `None` là giá trị hợp lệ của khóa hiện có; sự hiện diện phải xét theo khóa/nút, không suy từ value.

</details>

## Ghi nhớ

**Truy vấn khoảng trên BST** tận dụng bất biến thứ tự để **bỏ nguyên những cây con chắc chắn ngoài khoảng**, sau đó phát các khóa theo thứ tự **trái → nút → phải**. Với khoảng **`[lo,hi)`**, bắt đầu từ **lower_bound(lo)** và dừng khi **`key >= hi`**. Để **giới hạn đầu ra**, phải **dừng việc duyệt ngay khi đủ `L` mục**, không chỉ cắt danh sách sau khi đã duyệt hết. Với `k` kết quả thực trả và BST cao `h`, cách duyệt có cắt tỉa hoặc iterator từ cận đạt khoảng **`O(h+k)` thời gian**, thường **`O(log n+k)`** khi cây cân bằng. Muốn phân trang, lưu **khóa cuối** làm cursor và tiếp tục từ **khóa lớn hơn nghiêm ngặt**; muốn báo chính xác còn trang sau, hãy xem trước thêm một mục. **Giới hạn đầu ra không đồng nghĩa tổng số khóa thỏa khoảng**, và cursor không tự tạo snapshot khi cây thay đổi.

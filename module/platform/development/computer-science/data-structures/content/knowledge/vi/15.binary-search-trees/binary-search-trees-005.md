# Tìm khóa gần nhất theo cận dưới và cận trên

Trong một hệ thống xếp lịch, ta lưu các mốc bắt đầu buổi học theo thứ tự. Người dùng hỏi: “Buổi đầu tiên bắt đầu **không trước** 10:20 là buổi nào?” hoặc “Buổi đầu tiên bắt đầu **sau** 10:20 là buổi nào?”. Hai câu hỏi tưởng giống nhau, nhưng khác ở chỗ **có chấp nhận đúng mốc được hỏi hay không**.

Trên **cây tìm kiếm nhị phân** (*Binary Search Tree – BST*), những câu hỏi ấy được giải bằng hai phép tra cứu theo cận rất phổ biến: **lower bound** (cận dưới) và **upper bound** (cận trên). Cả hai đều tận dụng bất biến thứ tự để tìm **ứng viên gần nhất theo thứ tự khóa**, không cần duyệt rồi sắp xếp toàn bộ cây.

Bài thuộc chương **Cây tìm kiếm nhị phân** của module cấu trúc dữ liệu, tập trung vào bất biến, thao tác và độ phức tạp thời gian/bộ nhớ. Ta sẽ xác định hợp đồng của hai phép tìm theo cận, cài đặt BST bằng Python, chứng minh cách chọn nhánh, xử lý biên và sử dụng kết quả trong truy vấn khoảng.

## 1. Định nghĩa chính xác lower bound và upper bound

Giả sử `S` là tập khóa **phân biệt**, được so sánh theo một thứ tự nhất quán. Với khóa truy vấn `x`:

- **Lower bound của x:** khóa **nhỏ nhất lớn hơn hoặc bằng x**. Ký hiệu `LB(x) = min{k thuộc S | k >= x}`.
- **Upper bound của x:** khóa **nhỏ nhất lớn hơn x một cách nghiêm ngặt**. Ký hiệu `UB(x) = min{k thuộc S | k > x}`.

Nếu không có phần tử thỏa điều kiện, kết quả là **không tồn tại**; trong các thư viện dùng iterator, kết quả thường là vị trí `end()`.

Đây là định nghĩa về **thứ tự**, không nhất thiết là độ gần theo khoảng cách số học. “Gần nhất” ở đây nghĩa là khóa đầu tiên từ phía **không nhỏ hơn** hoặc **lớn hơn** mốc truy vấn.

### Bảng minh họa đầu tiên

Với các khóa tăng dần:

```text
S = {10, 20, 30, 40, 50}
```

| Mốc `x` | Lower bound: nhỏ nhất `>= x` | Upper bound: nhỏ nhất `> x` |
| ---: | ---: | ---: |
| `5` | `10` | `10` |
| `10` | `10` | `20` |
| `15` | `20` | `20` |
| `30` | `30` | `40` |
| `49` | `50` | `50` |
| `50` | `50` | Không có |
| `55` | Không có | Không có |

**Quy tắc nhớ:** lower bound **bao gồm dấu bằng**, còn upper bound **không bao gồm dấu bằng**.

Khi `x` không có trong cây, hai kết quả thường trùng nhau: đó là khóa nhỏ nhất lớn hơn `x`. Khi `x` có trong cây, lower bound trả `x`, trong khi upper bound bỏ qua `x` để tìm khóa lớn hơn tiếp theo.

## 2. Bất biến BST cho phép bỏ nguyên một cây con

Với BST **khóa duy nhất**, tại nút có khóa `k`:

- Mọi khóa trong **toàn bộ cây con trái** nhỏ hơn `k`.
- Mọi khóa trong **toàn bộ cây con phải** lớn hơn `k`.
- Hai cây con cũng tiếp tục thỏa bất biến này.

```text
         k
       /   \
   (< k)  (> k)
```

Từ “**toàn bộ**” là điều kiện thiết yếu. Nếu chỉ đúng với hai nút con trực tiếp mà có một hậu duệ nằm sai phía, thuật toán lower/upper bound có thể loại nhầm nhánh chứa đáp án.

Ta sử dụng quy tắc **một nút trên mỗi khóa phân biệt**. Nếu BST làm map, nút còn có thể lưu `value`; phép so sánh để đi trái/phải vẫn dựa vào **key**, không dựa vào giá trị.

## 3. Cây mẫu dùng xuyên suốt bài

Ta chèn các khóa:

```text
40, 20, 60, 10, 30, 50, 80, 35, 45, 55, 70, 90, 75
```

Cây được tạo ra:

```text
                         40
                       /    \
                     20      60
                    /  \    /  \
                  10   30  50   80
                         \ / \  / \
                         35 45 55 70 90
                                    \
                                     75
```

Dãy khóa khi duyệt trung thứ tự (*in-order*):

```text
10, 20, 30, 35, 40, 45, 50, 55, 60, 70, 75, 80, 90
```

Dãy này chỉ để đối chiếu kết quả. **Thuật toán tìm theo cận không cần tạo dãy in-order trước**.

| Truy vấn | `LB(x)` | `UB(x)` |
| ---: | ---: | ---: |
| `9` | `10` | `10` |
| `30` | `30` | `35` |
| `32` | `35` | `35` |
| `35` | `35` | `40` |
| `40` | `40` | `45` |
| `56` | `60` | `60` |
| `60` | `60` | `70` |
| `75` | `75` | `80` |
| `90` | `90` | Không có |
| `91` | Không có | Không có |

## 4. Thuật toán lower bound: tìm khóa đầu tiên không nhỏ hơn x

Muốn tìm **khóa nhỏ nhất `>= x`**, ta đi từ gốc và nhớ **ứng viên tốt nhất** (`candidate`).

Tại mỗi nút `current`:

1. Nếu `current.key >= x`, nút này là **ứng viên hợp lệ**. Ghi nhận nó, rồi đi **sang trái** để thử tìm một khóa **nhỏ hơn ứng viên** nhưng vẫn `>= x`.
2. Nếu `current.key < x`, nút này **không hợp lệ**. Mọi khóa trong cây con trái còn nhỏ hơn nó, nên cũng không hợp lệ. Đi **sang phải**.
3. Khi chạm liên kết rỗng, trả ứng viên đã lưu. Nếu chưa từng có ứng viên, kết quả không tồn tại.

```text
LOWER_BOUND(root, x):
    current = root
    candidate = null

    while current != null:
        if current.key >= x:
            candidate = current
            current = current.left
        else:
            current = current.right

    return candidate
```

**Không nên trả ngay khi gặp một khóa `> x`.** Đó chỉ là ứng viên; có thể còn khóa hợp lệ nhỏ hơn ở cây con trái. Nếu gặp khóa `== x` trong BST khóa duy nhất, ta biết kết quả lý tưởng đã có, nên có thể trả ngay để tối ưu. Giả mã thống nhất ở trên vẫn đi trái và cho kết quả đúng.

### Vết chạy: `LB(32)`

```text
x = 32

current = 40: 40 >= 32 → candidate = 40, đi trái
current = 20: 20 <  32 → không đổi candidate, đi phải
current = 30: 30 <  32 → không đổi candidate, đi phải
current = 35: 35 >= 32 → candidate = 35, đi trái
current = None: dừng

Kết quả LB(32) = 35
```

Dù `32` **không xuất hiện trong cây**, lower bound vẫn tìm được `35`. Không có yêu cầu phải tìm thấy `x` trước khi tìm theo cận.

### Vết chạy: `LB(40)`

```text
current = 40: 40 >= 40 → candidate = 40, đi trái
current = 20: 20 <  40 → đi phải
current = 30: 30 <  40 → đi phải
current = 35: 35 <  40 → đi phải tới None

Kết quả LB(40) = 40
```

Vì lower bound dùng điều kiện **`>=`**, khóa bằng mốc truy vấn là một đáp án hợp lệ.

## 5. Thuật toán upper bound: tìm khóa đầu tiên lớn hơn x

**Upper bound** khác lower bound ở đúng điều kiện nhận ứng viên:

1. Nếu `current.key > x`, nút này là ứng viên hợp lệ; lưu lại và **đi trái** để tìm khóa còn gần `x` hơn từ phía trên.
2. Nếu `current.key <= x`, cả nút hiện tại lẫn cây con trái đều không chứa khóa `> x`; **đi phải**.
3. Khi tới liên kết rỗng, trả ứng viên hoặc báo không có.

```text
UPPER_BOUND(root, x):
    current = root
    candidate = null

    while current != null:
        if current.key > x:
            candidate = current
            current = current.left
        else:
            current = current.right

    return candidate
```

### Vết chạy: `UB(40)`

```text
x = 40

current = 40: 40 <= 40 → đi phải
current = 60: 60 >  40 → candidate = 60, đi trái
current = 50: 50 >  40 → candidate = 50, đi trái
current = 45: 45 >  40 → candidate = 45, đi trái
current = None: dừng

Kết quả UB(40) = 45
```

Nếu viết nhầm `>=` trong hàm upper bound, hàm có thể trả lại chính `40`, sai vì yêu cầu **lớn hơn nghiêm ngặt**.

### Vết chạy: `UB(32)`

```text
40 > 32 → candidate = 40; đi trái
20 <= 32 → đi phải
30 <= 32 → đi phải
35 > 32 → candidate = 35; đi trái tới None

Kết quả UB(32) = 35
```

`32` không nằm trong cây nên `LB(32) = UB(32) = 35`.

## 6. Tại sao phải duy trì ứng viên và đi đúng một nhánh?

Ở mỗi bước, ta chỉ tìm được **một nút phù hợp tạm thời**, chưa chắc đó là khóa nhỏ nhất thỏa điều kiện.

Với lower bound:

- Khi `k >= x`, ta đã có một đáp án khả dĩ. Mọi khóa trong **cây con phải** của `k` đều lớn hơn `k` nên không thể tốt hơn. Vì vậy **loại cả cây con phải**, lưu `k` và đi trái.
- Khi `k < x`, `k` không phù hợp và **mọi khóa cây con trái** còn nhỏ hơn `k`, nên đều không phù hợp. Chỉ còn cây con phải cần xem.

Với upper bound, lập luận tương tự nhưng thay dấu `>=` bằng `>`.

### Bất biến vòng lặp

Trong quá trình tìm:

- `candidate` hoặc rỗng, hoặc mang khóa **thỏa điều kiện** của truy vấn.
- Mỗi ứng viên mới hợp lệ đều **nhỏ hơn ứng viên cũ** (vì nó nằm trong cây con trái của ứng viên trước đó).
- Những cây con đã loại **không thể chứa kết quả tốt hơn ứng viên**; việc loại dựa trên bất biến BST.
- Mọi khóa có thể là đáp án tốt hơn mà chưa bị loại đều thuộc cây con của `current`.

Khi vòng lặp kết thúc tại `current = None`, không còn nút nào có thể cải thiện ứng viên. Do đó ứng viên cuối là **khóa nhỏ nhất** trong những khóa thỏa điều kiện.

**Điều kiện tiên quyết:** cây đầu vào phải thực sự là BST theo **cùng một quy tắc so sánh** được dùng trong thuật toán. Một cây sai bất biến có thể khiến lower/upper bound cho kết quả sai dù bản thân vòng lặp được viết đúng.

## 7. Cài đặt Python: BST và hai phép tìm theo cận

Đây là một ví dụ **tự chứa**, sử dụng khóa số nguyên phân biệt. Lớp nút còn lưu `value` để minh họa BST làm **map**; vị trí nút chỉ phụ thuộc `key`.

### Tạo và cập nhật BST

```python
class Node:
    def __init__(self, key, value=None):
        self.key = key
        self.value = value
        self.left = None
        self.right = None


class BSTMap:
    def __init__(self):
        self.root = None
        self._size = 0

    def put(self, key, value):
        """Thêm khóa mới hoặc cập nhật value; trả True nếu thêm nút."""
        if self.root is None:
            self.root = Node(key, value)
            self._size = 1
            return True

        current = self.root
        while True:
            if key == current.key:
                current.value = value
                return False
            if key < current.key:
                if current.left is None:
                    current.left = Node(key, value)
                    self._size += 1
                    return True
                current = current.left
            else:
                if current.right is None:
                    current.right = Node(key, value)
                    self._size += 1
                    return True
                current = current.right

    def size(self):
        return self._size


tree = BSTMap()
keys = [40, 20, 60, 10, 30, 50, 80, 35, 45, 55, 70, 90, 75]
for key in keys:
    tree.put(key, "value-" + str(key))

assert tree.size() == 13
assert tree.put(40, "updated") is False
assert tree.size() == 13
```

Khi gọi `put` với khóa `40` cũ, giá trị được thay nhưng không tạo thêm nút. Việc này không ảnh hưởng thứ tự BST.

### Triển khai lower bound và upper bound

```python
def lower_bound_node(root, x):
    """Trả nút có khóa nhỏ nhất >= x, hoặc None."""
    candidate = None
    current = root

    while current is not None:
        if current.key >= x:
            candidate = current
            current = current.left
        else:
            current = current.right

    return candidate


def upper_bound_node(root, x):
    """Trả nút có khóa nhỏ nhất > x, hoặc None."""
    candidate = None
    current = root

    while current is not None:
        if current.key > x:
            candidate = current
            current = current.left
        else:
            current = current.right

    return candidate


def key_or_none(node):
    return None if node is None else node.key


assert key_or_none(lower_bound_node(tree.root, 32)) == 35
assert key_or_none(upper_bound_node(tree.root, 32)) == 35

assert key_or_none(lower_bound_node(tree.root, 40)) == 40
assert key_or_none(upper_bound_node(tree.root, 40)) == 45

assert key_or_none(lower_bound_node(tree.root, 75)) == 75
assert key_or_none(upper_bound_node(tree.root, 75)) == 80

assert key_or_none(lower_bound_node(tree.root, 90)) == 90
assert upper_bound_node(tree.root, 90) is None

assert lower_bound_node(tree.root, 91) is None
assert upper_bound_node(tree.root, 91) is None
assert lower_bound_node(None, 42) is None
assert upper_bound_node(None, 42) is None
```

**Điểm hay của phiên bản này:** không cần biết `x` có tồn tại hay không, không cần con trỏ `parent`, không cần cấp phát nút mới và chỉ sử dụng **một** đường tìm kiếm.

### Trả cặp (found, key) khi None có thể là khóa hợp lệ

Trong ví dụ khóa số nguyên, `None` là dấu “không tồn tại” hợp lệ ở phía API. Nhưng nếu dùng một cấu trúc có chính sách cho phép khóa `None` và comparator riêng, cần trả trạng thái riêng:

```python
def lower_bound_result(root, x):
    result = lower_bound_node(root, x)
    if result is None:
        return False, None
    return True, result.key
```

Kết quả `(True, None)` và `(False, None)` khi ấy sẽ phân biệt “khóa `None` có mặt” với “không có kết quả”. **Điều kiện bổ sung:** chính cấu trúc BST phải triển khai comparator phù hợp nếu cho phép khóa `None`; hai hàm mẫu dùng phép so sánh số học và không hỗ trợ khóa hỗn hợp tùy ý.

## 8. Lấy đồng thời hai cận bằng hai lần tra cứu

Khi ứng dụng cần biết đồng thời **lower bound** và **upper bound**, có thể viết một hàm thuận tiện. Với các khóa **duy nhất**, ở nút bằng `x`, lower bound chắc chắn là nút đó; upper bound nằm ở cây con phải hoặc một tổ tiên phù hợp.

Một giải pháp dễ kiểm tra và ít phức tạp là **gọi hai hàm riêng**:

```python
def bounds(root, x):
    return lower_bound_node(root, x), upper_bound_node(root, x)


lb, ub = bounds(tree.root, 40)
assert lb.key == 40
assert ub.key == 45
```

Hai lần đi theo đường tìm vẫn có tổng độ phức tạp `O(h) + O(h) = O(h)`, bộ nhớ phụ `O(1)`. Với nhiều tình huống, cách tách hai hàm làm ý nghĩa các dấu so sánh rõ ràng hơn một hàm tối ưu hóa phức tạp.

Nếu cần tối ưu hơn, các thư viện cây có thể cung cấp `equal_range`, trả đồng thời hai vị trí biên theo cùng quy tắc so sánh, nhưng phải dựa vào hợp đồng từng thư viện.

## 9. Phân biệt lower/upper bound với predecessor, successor, floor và ceiling

Các khái niệm thường bị nhầm vì đều là **truy vấn lân cận theo thứ tự**.

Với một tập khóa `S` và mốc `x`:

| Tên truy vấn | Điều kiện khóa | Chọn |
| --- | --- | --- |
| **Strict predecessor** | `k < x` | Khóa **lớn nhất** bên dưới `x` |
| **Floor** | `k <= x` | Khóa **lớn nhất** không vượt `x` |
| **Lower bound / Ceiling** | `k >= x` | Khóa **nhỏ nhất** không dưới `x` |
| **Upper bound / Strict successor** | `k > x` | Khóa **nhỏ nhất** phía trên `x` |

Trong quy ước bài này:

```text
lower_bound(x) == ceiling(x)
upper_bound(x) == strict_successor(x)
```

**Cẩn thận về cách gọi:** nhiều thư viện có tên `higher(x)` cho strict successor và `ceiling(x)` cho lower bound. Trong một số tài liệu, “successor của một nút” có nghĩa là nút tiếp theo khi duyệt in-order, thường giả định **nút đang xét thực sự tồn tại**. Định nghĩa `UB(x)` áp dụng cho **bất kỳ mốc truy vấn nào**, kể cả mốc không có trong cây.

### Ví dụ khi x có và không có

Với `S = {20, 30, 35, 40, 45}`:

| Mốc | Predecessor | Floor | Lower bound | Upper bound |
| ---: | ---: | ---: | ---: | ---: |
| `32` | `30` | `30` | `35` | `35` |
| `35` | `30` | `35` | `35` | `40` |
| `36` | `35` | `35` | `40` | `40` |
| `50` | `45` | `45` | Không có | Không có |

Nếu người dùng cần phần tử **gần nhất phía dưới**, lower bound **không phải** kết quả cần tìm; nên dùng floor hoặc predecessor. Hai phép “cận dưới/cận trên” thuộc nhóm tìm **từ phía trên mốc**, khác nhau ở chỗ chấp nhận dấu bằng.

## 10. Từ cận dưới/cận trên tới truy vấn khoảng

Đây là một ứng dụng quan trọng của các cấu trúc dữ liệu có thứ tự.

Giả sử cần xuất mọi khóa trong khoảng **nửa mở** `[lo, hi)`:

```text
lo <= key < hi
```

Ta có thể:

1. Tìm `lower_bound(lo)` để có khóa đầu tiên **không nhỏ hơn `lo`**.
2. Duyệt tăng dần các khóa kế tiếp theo thứ tự in-order.
3. Dừng ngay khi khóa hiện tại `>= hi`. Điểm kết thúc (không lấy) tương đương vị trí `lower_bound(hi)`, **không phải `upper_bound(hi)`**.

Sự khác nhau này rất dễ bị nhầm khi chuyển các dấu biên:

| Khoảng yêu cầu | Vị trí bắt đầu | Vị trí kết thúc (không lấy) |
| --- | --- | --- |
| `[lo, hi)` | `lower_bound(lo)` | `lower_bound(hi)` |
| `[lo, hi]` | `lower_bound(lo)` | `upper_bound(hi)` |
| `(lo, hi)` | `upper_bound(lo)` | `lower_bound(hi)` |
| `(lo, hi]` | `upper_bound(lo)` | `upper_bound(hi)` |

Các công thức giả định `lo <= hi` theo comparator đang dùng và có iterator theo thứ tự trên **cùng cấu trúc**. Nếu `lo > hi` thì khoảng rỗng theo quy ước thông thường.

### Ví dụ khoảng `[32, 75)`

Trên cây mẫu:

```text
lower_bound(32) = 35
Các khóa theo thứ tự từ 35:
35, 40, 45, 50, 55, 60, 70, 75, ...

Dừng khi gặp khóa >= 75.

Kết quả:
35, 40, 45, 50, 55, 60, 70
```

Nếu khoảng là `[32, 75]`, khóa `75` **được lấy** và điểm kết thúc thích hợp là `upper_bound(75) = 80`.

### Python: iterator bắt đầu ở lower bound

Một BST không lưu con trỏ cha vẫn có thể tạo iterator tăng dần từ `lower_bound(lo)` bằng **stack đường đi**:

```python
def iter_from_lower_bound(root, lo):
    """Sinh (key, value) có key >= lo theo thứ tự tăng dần."""
    stack = []
    current = root

    # Tìm các tổ tiên có thể xuất hiện sau khi lấy lower bound.
    while current is not None:
        if current.key >= lo:
            stack.append(current)
            current = current.left
        else:
            current = current.right

    # Tiếp tục duyệt in-order từ vị trí đầu tiên thỏa điều kiện.
    while stack:
        node = stack.pop()
        yield node.key, node.value

        current = node.right
        while current is not None:
            stack.append(current)
            current = current.left


def range_items(root, lo, hi):
    """Các cặp có lo <= key < hi, theo thứ tự khóa."""
    if lo >= hi:
        return []
    result = []
    for key, value in iter_from_lower_bound(root, lo):
        if key >= hi:
            break
        result.append((key, value))
    return result


selected = range_items(tree.root, 32, 75)
assert [key for key, _ in selected] == [
    35, 40, 45, 50, 55, 60, 70
]
assert range_items(tree.root, 75, 75) == []
assert range_items(tree.root, 90, 100) == [(90, "value-90")]
```

Hàm `iter_from_lower_bound` dùng một stack để giữ các nút còn phải duyệt. Nó không duyệt lại các khóa `< lo`, không sắp xếp toàn bộ cây và không tạo list trung gian chứa tất cả các nút. Chỉ `range_items` chủ động gom kết quả thành list để trả cho người gọi.

**Độ phức tạp:** định vị ban đầu `O(h)`, sau đó xuất `k` mục liên tiếp với tổng công việc `O(k)` theo phân tích khấu hao của duyệt in-order; tổng `O(h + k)`, bộ nhớ phụ `O(h)` cho stack và `O(k)` cho list kết quả. Nếu gọi `upper_bound_node(root, last_key)` từ gốc lặp lại cho từng mục, chi phí có thể tăng thành `O(kh)`; không nên nhầm hai cách duyệt.

## 11. Tìm “khóa gần nhất” theo khoảng cách số học là bài toán khác

Trong tiếng Việt, cụm **“khóa gần nhất”** đôi khi được hiểu là **giá trị có khoảng cách tuyệt đối nhỏ nhất** tới `x`. Đây **không phải** định nghĩa của lower/upper bound.

Ví dụ `S = {20, 30, 35, 40}` và `x = 32`:

- `LB(32) = 35`, vì `35` là khóa nhỏ nhất `>= 32`.
- `UB(32) = 35`, cùng kết quả vì `32` vắng mặt.
- Khóa **gần nhất theo khoảng cách** lại là `30`, vì `|30 - 32| = 2` nhỏ hơn `|35 - 32| = 3`.

Nếu bài toán yêu cầu **gần nhất theo số học**, cần xét cả hai phía: **floor(x)** (khóa lớn nhất `<= x`) và **lower_bound(x)** (khóa nhỏ nhất `>= x`), rồi so khoảng cách. Tại mốc `x` tồn tại, cả hai có thể chính là `x` và khoảng cách bằng 0.

### Cài floor và nearest cho khóa số

```python
def floor_node(root, x):
    candidate = None
    current = root

    while current is not None:
        if current.key <= x:
            candidate = current
            current = current.right
        else:
            current = current.left

    return candidate


def nearest_numeric_node(root, x):
    """Khóa có |key - x| nhỏ nhất; hòa thì chọn khóa nhỏ hơn."""
    below = floor_node(root, x)
    above = lower_bound_node(root, x)

    if below is None:
        return above
    if above is None:
        return below

    if x - below.key <= above.key - x:
        return below
    return above


assert nearest_numeric_node(tree.root, 32).key == 30
assert nearest_numeric_node(tree.root, 33).key == 35
assert nearest_numeric_node(tree.root, 32.5).key == 30  # Hòa → chọn nhỏ
assert nearest_numeric_node(tree.root, 40).key == 40
assert nearest_numeric_node(None, 40) is None
```

Hàm `nearest_numeric_node` **chỉ phù hợp với khóa số** có phép trừ và so sánh khoảng cách hợp lệ. Với mã chuỗi hoặc đối tượng có comparator, “gần nhất” không tự có ý nghĩa khoảng cách; cần định nghĩa thước đo riêng.

## 12. Quy tắc khóa trùng và comparator ảnh hưởng đến cận

Các hàm Python trên giả định **khóa số nguyên phân biệt**, so sánh bằng `<`, `>`, `==`. Trong cấu trúc thực tế, khóa có thể là chuỗi, ngày giờ, tuple hoặc đối tượng.

### Một comparator phải dùng xuyên suốt

Khi BST được tổ chức theo comparator `compare(a, b)`:

- Lower bound nhận nút nếu `compare(node.key, x) >= 0`.
- Upper bound nhận nút nếu `compare(node.key, x) > 0`.
- Các nhánh “chưa đủ điều kiện” và “tìm ứng viên nhỏ hơn” phải được hiểu theo **cùng comparator**.

Nếu xây cây theo thứ tự mã học viên **không phân biệt hoa thường**, nhưng tìm theo so sánh chuỗi có phân biệt hoa thường, có thể rẽ sai nhánh. **Mọi thao tác chèn, tìm, xóa và tìm theo cận phải thống nhất quy tắc thứ tự.**

### Khóa trùng trong multiset

Một **BST-set hoặc tree map** thường có khóa duy nhất. Nhưng **multiset** có thể chứa nhiều lần xuất hiện của cùng khóa.

Ví dụ dãy đã sắp:

```text
10, 20, 20, 20, 30, 40
    ↑           ↑
    LB(20)      UB(20) = vị trí của 30
```

Ở cấu trúc có iterator theo thứ tự:

- `lower_bound(20)` trỏ tới **phần tử đầu tiên không nhỏ hơn 20**, tức bản sao `20` đầu tiên.
- `upper_bound(20)` trỏ tới **phần tử đầu tiên lớn hơn 20**, tức `30`.
- Khoảng iterator `[lower_bound(20), upper_bound(20))` chứa **tất cả** các bản sao `20`.

Nếu multiset tự cài bằng **một nút có `count`**, kết quả lower/upper theo **giá trị khóa** vẫn có ý nghĩa; nhưng để lấy từng bản sao, iterator phải biết cách lặp lại nút theo `count`.

### Khóa ghép

Một cây lưu `(priority, task_id)` sẽ so sánh tuple theo thứ tự từ trái sang phải trong Python. Mốc truy vấn và quy tắc lấy lower/upper bound phải được định nghĩa cho **cả khóa ghép**, không chỉ thuộc tính `priority`.

Ví dụ hai công việc cùng ưu tiên `5` nhưng mã khác nhau vẫn được phân biệt nếu `task_id` tham gia so sánh. Nếu chỉ xét ưu tiên, hai khóa ấy có thể trở thành tương đương trong một tree set dùng comparator quá thô.

## 13. Liên hệ với thư viện C++, Java và mảng đã sắp

Tên lower/upper bound phổ biến nhất trong thư viện cấu trúc dữ liệu có thứ tự, nhưng các ngôn ngữ có API và kiểu trả về khác nhau.

### C++: `std::set::lower_bound` và `upper_bound`

```cpp
#include <cassert>
#include <set>

int main() {
    std::set<int> s = {10, 20, 30, 40, 50};

    auto lb = s.lower_bound(30);  // đầu tiên >= 30
    auto ub = s.upper_bound(30);  // đầu tiên > 30

    assert(lb != s.end() && *lb == 30);
    assert(ub != s.end() && *ub == 40);

    assert(s.lower_bound(51) == s.end());
    assert(s.upper_bound(50) == s.end());
}
```

`std::set` thường được triển khai bằng cây tìm kiếm cân bằng và các hàm thành viên `lower_bound` / `upper_bound` có chi phí logarit theo số phần tử. Với `std::map`, iterator trả về cặp khóa–giá trị.

**Lưu ý C++:** nên dùng **hàm thành viên** `s.lower_bound(x)` cho `std::set`, thay vì mặc định dùng thuật toán tổng quát `std::lower_bound(s.begin(), s.end(), x)` như thể đây là mảng truy cập ngẫu nhiên. Thuật toán tổng quát có thể thực hiện ít phép so sánh nhưng phải di chuyển iterator nhiều bước với iterator không truy cập ngẫu nhiên.

### C++: `std::multiset::equal_range`

```cpp
#include <cassert>
#include <iterator>
#include <set>

int main() {
    std::multiset<int> s = {10, 20, 20, 20, 30};

    auto range = s.equal_range(20);

    assert(*range.first == 20);
    assert(*range.second == 30);
    assert(std::distance(range.first, range.second) == 3);
}
```

Hai iterator của `equal_range(20)` tạo khoảng nửa mở chứa các bản sao của khóa `20`. Nếu không có khóa bằng `x`, hai vị trí biên có thể trùng nhau.

### Java: `NavigableSet` / `NavigableMap`

Java không nhất thiết dùng tên `lower_bound` / `upper_bound`, nhưng các cấu trúc có thứ tự hỗ trợ phép tương đương:

| Ý nghĩa | `NavigableSet` | `NavigableMap` |
| --- | --- | --- |
| Khóa nhỏ nhất `>= x` | `ceiling(x)` | `ceilingKey(x)` / `ceilingEntry(x)` |
| Khóa nhỏ nhất `> x` | `higher(x)` | `higherKey(x)` / `higherEntry(x)` |
| Khóa lớn nhất `<= x` | `floor(x)` | `floorKey(x)` / `floorEntry(x)` |
| Khóa lớn nhất `< x` | `lower(x)` | `lowerKey(x)` / `lowerEntry(x)` |

```java
import java.util.NavigableSet;
import java.util.TreeSet;

public class Main {
    public static void main(String[] args) {
        NavigableSet<Integer> keys = new TreeSet<>();
        keys.add(10);
        keys.add(20);
        keys.add(30);
        keys.add(40);

        System.out.println(keys.ceiling(30)); // 30
        System.out.println(keys.higher(30));  // 40
        System.out.println(keys.ceiling(35)); // 40
        System.out.println(keys.higher(40));  // null
    }
}
```

Trong `NavigableSet`, một số phương thức trả `null` khi không có kết quả; cần lưu ý quy tắc về phần tử null của triển khai cụ thể. Những phương thức của `TreeSet` có thời gian logarit theo số phần tử.

### Python: `bisect_left` và `bisect_right` trên list đã sắp

Thư viện chuẩn Python không có một lớp tree set/tree map tương đương `TreeSet` và `std::set` tích hợp sẵn. Nhưng với **list đã sắp**, các vị trí theo cận có thể tìm bằng `bisect`:

```python
from bisect import bisect_left, bisect_right

keys = [10, 20, 30, 35, 40, 45, 50]

i = bisect_left(keys, 35)   # vị trí đầu tiên >= 35
j = bisect_right(keys, 35)  # vị trí đầu tiên > 35

assert i == 3 and keys[i] == 35
assert j == 4 and keys[j] == 40

assert bisect_left(keys, 32) == bisect_right(keys, 32) == 3
assert bisect_left(keys, 99) == len(keys)
```

Với list có truy cập chỉ số `O(1)`, việc **tìm vị trí** bằng bisect là `O(log n)`, nhưng **chèn phần tử vào giữa list** vẫn có thể tốn `O(n)` do dịch các mục. Đây là khác biệt giữa **cấu trúc cây có thứ tự** và **mảng đã sắp** khi có nhiều cập nhật.

## 14. Độ phức tạp thời gian và bộ nhớ

Gọi `n` là số khóa phân biệt và `h` là chiều cao cây, đo bằng số nút trên đường dài nhất từ gốc đến lá.

| Tác vụ | BST thường | BST cân bằng | Bộ nhớ phụ |
| --- | --- | --- | --- |
| `lower_bound(x)` | `O(h)`, xấu nhất `O(n)` | `O(log n)` | `O(1)` với vòng lặp |
| `upper_bound(x)` | `O(h)`, xấu nhất `O(n)` | `O(log n)` | `O(1)` với vòng lặp |
| Tìm cả hai cận bằng hai lần tra | `O(h)` | `O(log n)` | `O(1)` |
| Floor và nearest numeric | `O(h)` | `O(log n)` | `O(1)` |
| Duyệt toàn bộ cây để tìm cận | `O(n)` | `O(n)` | Tùy cách duyệt |
| Truy vấn khoảng có `k` kết quả bằng iterator có cắt tỉa | `O(h+k)` | `O(log n+k)` | `O(h)` cho iterator, thêm `O(k)` nếu lưu kết quả |

Các mốc giả định phép so sánh khóa là `O(1)`. Nếu khóa chuỗi dài hoặc comparator phức tạp, một lần so sánh có thể tốn thêm thời gian, ví dụ `O(L)` theo độ dài khóa trong trường hợp xấu.

**BST hợp lệ không có nghĩa BST cân bằng.** Chèn dữ liệu tăng dần vào một BST không tự cân bằng có thể tạo cây lệch dạng danh sách, khiến lower/upper bound mất `O(n)`.

### So sánh với các lựa chọn khác

- **Hash set / hash map:** tra cứu **khóa chính xác** thường trung bình `O(1)`, nhưng không mặc nhiên hỗ trợ `lower_bound` theo thứ tự.
- **Mảng đã sắp:** dùng tìm nhị phân `O(log n)` để định vị cận, nhưng chèn/xóa trong mảng động có thể `O(n)`.
- **BST cân bằng:** tra cứu và cập nhật theo khóa `O(log n)`, hỗ trợ duyệt thứ tự và truy vấn khoảng mà không phải sắp lại toàn bộ.

Lựa chọn tùy **tần suất cập nhật**, **yêu cầu thứ tự** và **số lần truy vấn theo cận/khoảng**.

## 15. Các tình huống biên phải xử lý rõ

1. **Cây rỗng:** lower và upper bound đều không tồn tại.
2. **Mốc nhỏ hơn mọi khóa:** hai cận cùng trả **khóa nhỏ nhất**.
3. **Mốc bằng khóa nhỏ nhất:** lower bound trả chính nó; upper bound trả **khóa kế tiếp** nếu có.
4. **Mốc nằm giữa hai khóa:** hai cận trả **cùng khóa bên phải**.
5. **Mốc bằng khóa lớn nhất:** lower bound trả nó; upper bound không tồn tại.
6. **Mốc lớn hơn khóa lớn nhất:** cả hai cận không tồn tại.
7. **Cây một nút:** cần kiểm tra mốc nhỏ hơn, bằng hoặc lớn hơn nút duy nhất.
8. **Khóa có giá trị dữ liệu `None`:** vẫn có thể tìm thấy nút; không được dùng `node.value is None` để kết luận khóa vắng mặt.
9. **Khóa trùng:** cần xác định cấu trúc set/map hay multiset; `lower_bound` và `upper_bound` khác nhau về cách bỏ qua dãy bản sao.
10. **Comparator không nhất quán:** có thể làm đường tìm sai, kể cả khi tất cả mã nguồn đều dùng cùng một hàm gọi.
11. **Khóa bị sửa sau khi nằm trong BST:** vị trí nút có thể không còn phản ánh thứ tự, gây kết quả sai.
12. **Khóa truy vấn có kiểu không so sánh được với khóa cây:** Python có thể phát sinh `TypeError`; cần xác định miền khóa trước.
13. **Khóa số thực `NaN`:** các phép so sánh chuẩn với `NaN` không phù hợp với quy tắc thứ tự toàn phần thông thường; phải có chính sách riêng hoặc loại khỏi miền khóa.
14. **Truy vấn khoảng có `lo > hi`:** xử lý theo chính sách khoảng rỗng, không duyệt sai chiều.
15. **Thay đổi cấu trúc trong lúc iterator đang chạy:** cần hợp đồng iterator và đồng bộ phù hợp; không mặc nhiên an toàn.

## 16. Sai lầm dễ gặp khi viết code

- **Dùng `>` thay `>=` trong lower bound:** bỏ qua khóa bằng `x`.
- **Dùng `>=` thay `>` trong upper bound:** lấy nhầm chính `x`.
- **Gặp nút hợp lệ thì trả ngay:** bỏ lỡ khóa hợp lệ nhỏ hơn ở cây con trái.
- **Gặp nút không hợp lệ rồi đi trái:** có thể loại sạch vùng chứa các khóa lớn hơn `x` cần thiết; phải đi phải.
- **Không nhớ ứng viên:** gặp liên kết rỗng rồi kết luận không có, dù trước đó đã thăm nút hợp lệ.
- **Nhầm “upper bound” với khóa lớn nhất `<= x`:** cái sau là **floor**, nằm ở phía dưới, không phải phía trên.
- **Dùng thuật toán tìm predecessor để viết upper bound:** predecessor tìm khóa `< x`, ngược hướng với upper bound `> x`.
- **Tin rằng `O(log n)` đúng với mọi BST:** cần điều kiện chiều cao `O(log n)`.
- **Truy vấn khoảng `[a,b)` nhưng dùng `upper_bound(b)` làm điểm kết thúc:** vô tình lấy cả khóa bằng `b`.
- **Gọi lower/upper bound trên list chưa sắp:** kết quả tìm nhị phân không còn hợp lệ.
- **Trộn comparator khi chèn và truy vấn:** cây có thể còn hình dạng trông hợp lý nhưng trả kết quả sai về ngữ nghĩa.
- **Sắp xếp toàn bộ khóa cho mỗi yêu cầu cận:** đúng về mặt kết quả nếu sắp đúng, nhưng bỏ phí lợi thế tra cứu `O(h)` của BST.

## 17. Kiểm thử bằng đáp án độc lập từ dãy đã sắp

Một cách kiểm thử giúp phát hiện dấu `<`/`<=` bị nhầm là so sánh hàm BST với **bản tham chiếu trên list đã sắp**.

```python
from bisect import bisect_left, bisect_right

sorted_keys = sorted(set(keys))


def expected_lower_bound(sorted_values, x):
    i = bisect_left(sorted_values, x)
    return None if i == len(sorted_values) else sorted_values[i]


def expected_upper_bound(sorted_values, x):
    i = bisect_right(sorted_values, x)
    return None if i == len(sorted_values) else sorted_values[i]


queries = [-10, 10, 20, 29, 30, 32, 35, 40, 56, 60, 75, 90, 91, 200]

for x in queries:
    assert key_or_none(lower_bound_node(tree.root, x)) == (
        expected_lower_bound(sorted_keys, x)
    )
    assert key_or_none(upper_bound_node(tree.root, x)) == (
        expected_upper_bound(sorted_keys, x)
    )
```

Bản tham chiếu `bisect` phù hợp với kiểu khóa số nguyên và thứ tự tăng dần của ví dụ. Để kiểm thử chặt hơn, hãy tạo nhiều BST với **thứ tự chèn khác nhau** nhưng cùng tập khóa, rồi kiểm tra rằng lower/upper bound trả cùng khóa dù **đường đi và chiều cao cây khác nhau**.

**Lưu ý:** bài trình bày kiểm thử để người học tự chạy, chưa thực hiện quy trình kiểm thử/Content QA chuyên môn cho toàn bộ module.

## 18. Bài tập tự luyện

**Bài 1.** Cho tập khóa `{5, 10, 20, 30, 50}`. Tính lower bound và upper bound của `3, 10, 11, 30, 50, 60`.

**Bài 2.** Với cây mẫu ở phần 3, ghi lại đường đi cùng ứng viên khi tính `LB(32)` và `UB(40)`.

**Bài 3.** Giải thích vì sao khi `current.key >= x`, lower bound phải ghi nhận ứng viên rồi **rẽ trái**, không thể dừng ngay.

**Bài 4.** Một lập trình viên viết upper bound với điều kiện `current.key >= x`. Chỉ ra đầu vào phản ví dụ và kết quả sai.

**Bài 5.** Cho `S = {10, 20, 30, 40}`. So sánh `LB(30)`, `UB(30)`, `floor(30)` và `strict_predecessor(30)`.

**Bài 6.** Một BST có một nút `7`. Tính hai cận của `6`, `7` và `8`; xử lý cây rỗng.

**Bài 7.** Thiết kế hàm `bounds(root, x)` trả cả cận dưới và cận trên. Giải thích vì sao gọi hai phép tìm `O(h)` riêng vẫn là `O(h)` tổng.

**Bài 8.** Với cây mẫu, liệt kê các khóa thuộc `[32, 75)`, `[32, 75]`, `(30, 75)`, `(30, 75]`. Với mỗi khoảng, nêu lower/upper bound dùng để xác định iterator bắt đầu/kết thúc.

**Bài 9.** Vì sao `lower_bound(32)=35` không nhất thiết là khóa **gần 32 nhất theo trị tuyệt đối**? Hãy tìm khóa gần nhất trong cây mẫu theo khoảng cách số học, nếu hòa chọn khóa nhỏ hơn.

**Bài 10.** Một `std::multiset` có các khóa `[10,20,20,20,30,40]`. Hai iterator `lower_bound(20)` và `upper_bound(20)` bao quanh bao nhiêu phần tử, và mỗi iterator trỏ tới khóa nào?

**Bài 11.** Phân tích thời gian và bộ nhớ của lower/upper bound trong BST lệch và BST cân bằng. Khi nào thuật toán có thể `O(1)` cho một truy vấn cụ thể?

**Bài 12.** Một ứng dụng lưu thời gian bắt đầu lớp học theo phút: `{540,600,690,750}`. Người dùng hỏi buổi đầu tiên **không trước 600** và buổi đầu tiên **sau 600**. Chọn truy vấn và kết quả đúng.

<details>
<summary>Đáp án và gợi ý</summary>

1. Theo thứ tự `(LB, UB)`: `3 → (5,5)`; `10 → (10,20)`; `11 → (20,20)`; `30 → (30,50)`; `50 → (50,không có)`; `60 → (không có,không có)`.
2. `LB(32)`: `40` (ứng viên 40) → `20` → `30` → `35` (ứng viên 35) → rỗng, trả `35`. `UB(40)`: `40` → `60` (ứng viên 60) → `50` (ứng viên 50) → `45` (ứng viên 45) → rỗng, trả `45`.
3. Nút hiện tại thỏa `>= x` nhưng cây con trái có thể chứa một khóa `>= x` **nhỏ hơn nó**; phải kiểm tra để tìm ứng viên tốt hơn.
4. Với `S = {10, 20, 30}` và `x = 20`, thuật toán dùng `>=` có thể trả `20`, trong khi upper bound đúng là `30`.
5. `LB(30)=30`, `UB(30)=40`, `floor(30)=30`, `strict_predecessor(30)=20`.
6. Với cây `{7}`: `x=6 → (7,7)`; `x=7 → (7,không có)`; `x=8 → (không có,không có)`. Cây rỗng: cả hai không có.
7. Có thể gọi `lower_bound_node` và `upper_bound_node`, trả hai nút. Hai chi phí `O(h)` cộng lại vẫn là `O(h)`, bộ nhớ phụ lặp `O(1)`.
8. `[32,75)`: `35,40,45,50,55,60,70`; `[32,75]`: thêm `75`; `(30,75)`: `35,40,45,50,55,60,70`; `(30,75]`: thêm `75`. Các cặp điểm bắt đầu/kết thúc lần lượt là `(LB(32),LB(75))`, `(LB(32),UB(75))`, `(UB(30),LB(75))`, `(UB(30),UB(75))`.
9. `LB(32)=35` nhưng `|30-32|=2` nhỏ hơn `|35-32|=3`, nên khóa gần nhất theo số học là `30`; cần xét cả floor và LB.
10. `lower_bound(20)` trỏ bản sao `20` đầu tiên, `upper_bound(20)` trỏ `30`; khoảng nửa mở chứa ba bản sao `20`.
11. BST lệch `h=O(n)` nên truy vấn xấu nhất `O(n)`; BST cân bằng `h=O(log n)` nên `O(log n)`; bộ nhớ phụ lặp `O(1)`. Cây rỗng, hoặc kết quả phù hợp ở gốc mà thuật toán dừng sớm, có thể `O(1)`.
12. `lower_bound(600)=600` vì cho phép bằng; `upper_bound(600)=690` vì yêu cầu lớn hơn nghiêm ngặt.

</details>

## Ghi nhớ

**Lower bound** là khóa nhỏ nhất **`>= x`**; **upper bound** là khóa nhỏ nhất **`> x`**. Cả hai được tìm bằng cách đi theo **một đường BST**, lưu **ứng viên tốt nhất**, đi **trái** khi nút thỏa điều kiện và đi **phải** khi không thỏa. Khác biệt quan trọng nhất nằm ở dấu bằng: lower bound có thể trả lại `x`, upper bound thì không. Với BST cân bằng, mỗi truy vấn có thời gian `O(log n)`; với BST thường chi phí là `O(h)` và có thể `O(n)` khi cây lệch. Hai phép cận hỗ trợ tìm lân cận, xác định khoảng `[a,b)` và truy vấn thứ tự hiệu quả, nhưng **không đồng nghĩa tìm phần tử gần nhất theo khoảng cách số học**.

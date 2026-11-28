# Tìm khóa nhỏ nhất, lớn nhất, tiền nhiệm và kế nhiệm

Một ứng dụng lưu lịch thi theo thời điểm bắt đầu, một hệ thống quản lý học viên lưu hồ sơ theo mã, hoặc một bộ lập lịch cần tìm **công việc xảy ra ngay sau một mốc**. Những bài toán này không chỉ hỏi “khóa có tồn tại không?” mà còn cần biết **khóa nhỏ nhất, lớn nhất, gần trước và gần sau** một khóa cho trước.

Trên **cây tìm kiếm nhị phân** (*Binary Search Tree – BST*), các truy vấn ấy tận dụng trực tiếp bất biến thứ tự. Ta không cần lấy toàn bộ khóa ra rồi sắp xếp lại. Thay vào đó, có thể đi qua một đường từ gốc đến một nút hoặc một liên kết rỗng, đồng thời ghi nhớ **ứng viên phù hợp nhất**.

Bài thuộc chương **Cây tìm kiếm nhị phân** của module cấu trúc dữ liệu. Trọng tâm là định nghĩa chính xác **minimum**, **maximum**, **predecessor (tiền nhiệm)** và **successor (kế nhiệm)**, phân biệt với **floor/ceiling**, cài đặt Python, chứng minh tính đúng đắn và phân tích chi phí theo chiều cao cây.

## 1. Tiền đề: BST và chính sách khóa duy nhất

Trong bài này, BST chứa các **khóa phân biệt** có thể so sánh theo một quan hệ thứ tự nhất quán. Với mỗi nút có khóa `k`:

- Mọi khóa ở **toàn bộ cây con trái** nhỏ hơn `k`.
- Mọi khóa ở **toàn bộ cây con phải** lớn hơn `k`.
- Hai cây con cũng tuân thủ cùng bất biến.

```text
mọi x ∈ left(node):  x < node.key
mọi y ∈ right(node): y > node.key
```

Với **tree map**, một nút có thể chứa `(key, value)`; tất cả thuật toán trong bài quyết định vị trí theo **key**, không theo `value`. Với **tree set**, nút chỉ cần lưu khóa.

Ta dùng quy ước **khóa duy nhất**, nên có thể phân biệt “nhỏ hơn nghiêm ngặt” và “lớn hơn nghiêm ngặt” mà không phải xử lý nhiều nút trùng khóa. Nếu ứng dụng lưu số lần xuất hiện của một khóa, có thể dùng trường `count` ở cùng nút thay vì tự tạo nhiều nút có khóa bằng nhau.

### Phân biệt khóa với vị trí trong cây

**Tiền nhiệm theo thứ tự khóa** không nhất thiết là **nút cha** trong cây. Tương tự, **kế nhiệm** không nhất thiết là **nút con phải**. Các thuật toán sau tìm hai phần tử **liền kề trong thứ tự tăng dần của toàn bộ các khóa**, bất kể chúng nằm ở độ sâu nào.

## 2. Một cây ví dụ xuyên suốt

Xét BST được tạo bằng cách chèn lần lượt các khóa:

```text
40, 20, 60, 10, 30, 50, 80, 35, 45, 55, 70, 90, 75
```

Cây thu được:

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

Thứ tự các khóa khi **duyệt trung thứ tự** (*in-order*: trái → nút → phải) là:

```text
10, 20, 30, 35, 40, 45, 50, 55, 60, 70, 75, 80, 90
```

Đây là danh sách tham chiếu để tự kiểm tra kết quả, nhưng **không cần tạo danh sách này để trả từng truy vấn**.

| Truy vấn | Kết quả trên cây |
| --- | --- |
| Khóa nhỏ nhất | `10` |
| Khóa lớn nhất | `90` |
| Tiền nhiệm của `40` | `35` |
| Kế nhiệm của `40` | `45` |
| Tiền nhiệm của `60` | `55` |
| Kế nhiệm của `60` | `70` |
| Tiền nhiệm của `32` (không nằm trong cây) | `30` |
| Kế nhiệm của `32` | `35` |
| Tiền nhiệm của `10` | Không có |
| Kế nhiệm của `90` | Không có |

Điểm đáng chú ý: **`32` không tồn tại** nhưng ta vẫn có thể hỏi phần tử phân biệt **lớn nhất nhỏ hơn 32** và **nhỏ nhất lớn hơn 32**. Đây là kiểu truy vấn thường gặp khi tìm lân cận trên một tập khóa có thứ tự.

## 3. Tìm khóa nhỏ nhất: liên tục đi trái

**Khóa nhỏ nhất** của BST không rỗng nằm tại nút **không có con trái** trên đường đi bắt đầu từ gốc và liên tục rẽ trái.

Lý do: tại một nút có cây con trái, **mọi khóa trong cây con trái đều nhỏ hơn khóa nút**, do đó chưa thể dừng tại nút ấy để lấy khóa nhỏ nhất. Chỉ khi không còn con trái, nút hiện tại mới là nhỏ nhất của cây con đang xét.

```text
MINIMUM(node):
    nếu node == null:
        trả NOT_FOUND
    while node.left != null:
        node = node.left
    trả node
```

Trên cây mẫu:

```text
40 → trái 20 → trái 10 → không còn con trái
MIN = 10
```

Lưu ý: **nút nhỏ nhất vẫn có thể có cây con phải**. Ví dụ trong một BST khác, nút nhỏ nhất `10` có thể có con phải `15`, miễn là cấu trúc thỏa bất biến. Thuật toán chỉ cần biết **không có con trái**, chứ không đòi nút là lá.

### Điều kiện biên

- Cây rỗng: **không tồn tại khóa nhỏ nhất**.
- Cây một nút: chính nút đó vừa nhỏ nhất vừa lớn nhất.
- BST lệch phải: gốc có thể là khóa nhỏ nhất.
- BST lệch trái: cần đi qua gần như tất cả các nút để tới khóa nhỏ nhất.

**Độ phức tạp:** `O(h)` trong trường hợp xấu nhất, với `h` là chiều cao tính theo số nút trên đường dài nhất; chỉ dùng `O(1)` bộ nhớ phụ khi viết dạng lặp.

## 4. Tìm khóa lớn nhất: liên tục đi phải

Quy tắc đối xứng: **khóa lớn nhất** của BST không rỗng là nút nhận được khi **đi phải liên tục** từ gốc tới khi không còn con phải.

```text
MAXIMUM(node):
    nếu node == null:
        trả NOT_FOUND
    while node.right != null:
        node = node.right
    trả node
```

Trên cây mẫu:

```text
40 → phải 60 → phải 80 → phải 90
MAX = 90
```

**Nút lớn nhất vẫn có thể có cây con trái**, bởi các khóa ở đó nhỏ hơn nó. Thuật toán dừng khi không còn con phải, không nhất thiết khi gặp nút lá.

| Truy vấn | Hướng di chuyển | Điểm dừng |
| --- | --- | --- |
| `minimum(root)` | Đi trái liên tục | Nút không có con trái |
| `maximum(root)` | Đi phải liên tục | Nút không có con phải |

Hai thao tác đều có chi phí `O(h)` và `O(1)` bộ nhớ phụ với phiên bản lặp. Chúng không duyệt toàn bộ cây trong trường hợp tổng quát.

## 5. Tiền nhiệm: khóa lớn nhất nhỏ hơn một mốc

Với tập khóa `S` và mốc `x`, ta định nghĩa **tiền nhiệm nghiêm ngặt** (*strict predecessor*) là:

\[
\operatorname{pred}(x) = \max\{k \in S \mid k < x\}
\]

Nếu tập bên phải rỗng thì **không có tiền nhiệm**.

Trên cây mẫu:

```text
pred(40) = 35
pred(60) = 55
pred(75) = 70
pred(32) = 30
pred(10) = không có
```

“Tiền nhiệm” không có nghĩa lấy `x - 1`. Trên tập `{10, 20, 30, 35, ...}`, tiền nhiệm của `30` là `20`, không phải `29`.

### Hai tình huống khi x là khóa có sẵn trong BST

Giả sử ta đã tìm được **nút có khóa `x`**.

**Trường hợp A – nút có cây con trái:** tiền nhiệm là **khóa lớn nhất trong cây con trái**.

Ví dụ `x = 40`. Cây con trái của `40` bắt đầu tại `20`; đi phải tối đa:

```text
20 → phải 30 → phải 35
pred(40) = 35
```

Vì mọi khóa ở trái đều nhỏ hơn `40`, khóa lớn nhất tại đó là khóa gần `40` nhất từ phía dưới.

**Trường hợp B – nút không có cây con trái:** tiền nhiệm, nếu có, là **tổ tiên gần nhất mà đường đi từ tổ tiên ấy tới nút `x` rẽ sang phải**.

Ví dụ `x = 35`, nút `35` không có con trái:

```text
40 → trái 20 → phải 30 → phải 35
35 là con phải của 30; đi ngược từ 35 tới 30 gặp nhánh đi phải.
Tổ tiên gần nhất thỏa điều kiện là 30.
pred(35) = 30
```

Đi ngược từ `35` lên `30`, ta thấy `35` là **con phải của `30`**, nên `30` chính là tiền nhiệm. Trong cây khác, có thể phải đi lên nhiều tầng mới gặp tổ tiên mà đường tới nút cần tìm rẽ sang phải.

Với `x = 10`, tất cả bước đi từ gốc tới `10` là rẽ trái; không có tổ tiên nào có nhánh đi sang phải trên đường này. Vì vậy `10` không có tiền nhiệm.

### Quy tắc cô đọng

Nếu biết nút `x`:

1. Có con trái → `maximum(x.left)`.
2. Không có con trái → đi ngược về tổ tiên cho tới khi tìm được tổ tiên mà đường tới `x` đi sang **phải**.
3. Nếu không có tổ tiên như vậy → không có tiền nhiệm.

Không nên nhầm “tổ tiên gần nhất” với “nút cha trực tiếp”: có trường hợp phải đi ngược nhiều tầng.

## 6. Kế nhiệm: khóa nhỏ nhất lớn hơn một mốc

**Kế nhiệm nghiêm ngặt** (*strict successor*) của mốc `x` là:

\[
\operatorname{succ}(x) = \min\{k \in S \mid k > x\}
\]

Nếu không có khóa lớn hơn `x` thì **không có kế nhiệm**.

Trên cây mẫu:

```text
succ(40) = 45
succ(60) = 70
succ(75) = 80
succ(32) = 35
succ(90) = không có
```

### Hai tình huống khi x có trong cây

**Trường hợp A – nút có cây con phải:** kế nhiệm là **khóa nhỏ nhất trong cây con phải**.

Ví dụ `x = 40`:

```text
40 → phải 60 → trái 50 → trái 45
succ(40) = 45
```

**Trường hợp B – nút không có cây con phải:** kế nhiệm, nếu có, là **tổ tiên gần nhất mà đường từ tổ tiên ấy tới `x` rẽ sang trái**.

Ví dụ `x = 35`:

```text
40 → trái 20 → phải 30 → phải 35
↑
40 là tổ tiên gần nhất có bước đi sang trái trên đường từ gốc tới 35
succ(35) = 40
```

Từ `35` đi ngược lên `30` rồi `20`, cả hai lần đều đi từ **con phải** về cha, nên chưa gặp tổ tiên có đường rẽ trái. Đến `40`, ta đi ngược từ **con trái `20`**, vậy `40` là kế nhiệm.

Tương tự, `x = 90` không có con phải; đường đi từ gốc `40 → 60 → 80 → 90` chỉ rẽ phải, không có tổ tiên rẽ trái, nên không có kế nhiệm.

### Bảng đối xứng dễ nhớ

| Đặc điểm | Tiền nhiệm | Kế nhiệm |
| --- | --- | --- |
| Điều kiện | Lớn nhất trong các khóa `< x` | Nhỏ nhất trong các khóa `> x` |
| Có cây con thích hợp | **Max** của cây con **trái** | **Min** của cây con **phải** |
| Không có cây con thích hợp | Tổ tiên gần nhất có nhánh đi **phải** tới `x` | Tổ tiên gần nhất có nhánh đi **trái** tới `x` |
| Phần tử biên | Nhỏ nhất không có tiền nhiệm | Lớn nhất không có kế nhiệm |

Đây là cách lý giải khi **đã có nút `x`**. Để truy vấn cho một khóa bất kỳ, kể cả không có trong cây, ta có thể dùng thuật toán ứng viên từ gốc.

## 7. Tiền nhiệm cho mọi khóa truy vấn bằng ứng viên tốt nhất

Giả sử cần `pred(x)`, không biết `x` có nằm trong cây hay không. Ta đi từ gốc và duy trì biến `candidate`:

- Nếu `current.key < x`, nút hiện tại **đủ điều kiện** làm tiền nhiệm. Ghi nhận nó thành ứng viên mới và tiếp tục **sang phải**, nơi có thể có khóa lớn hơn ứng viên nhưng vẫn nhỏ hơn `x`.
- Nếu `current.key >= x`, nút hiện tại **không thể** là tiền nhiệm. Ta đi **sang trái** để tìm các khóa nhỏ hơn.
- Khi chạm liên kết rỗng, `candidate` là tiền nhiệm; nếu chưa từng có ứng viên, kết quả **không tồn tại**.

```text
PREDECESSOR(root, x):
    current = root
    candidate = null

    while current != null:
        if current.key < x:
            candidate = current
            current = current.right
        else:
            current = current.left

    return candidate
```

**Vì sao có thể thay ứng viên cũ?** Mỗi lần ta ghi nhận `current.key < x`, nút này nằm trong cây con phải của ứng viên trước đó (nếu có), nên **lớn hơn ứng viên trước** và vẫn nhỏ hơn `x`. Do đó nó là ứng viên **tốt hơn**.

### Vết chạy: `pred(32)`

```text
current = 40: 40 >= 32 → trái; candidate = None
current = 20: 20 < 32  → candidate = 20; phải
current = 30: 30 < 32  → candidate = 30; phải
current = 35: 35 >= 32 → trái
current = None: dừng

Kết quả: 30
```

Mốc `32` **không tồn tại**; thuật toán vẫn hoạt động vì chỉ cần tìm **khóa lớn nhất nhỏ hơn 32**.

### Vết chạy: `pred(40)`

```text
40 >= 40 → trái tới 20
20 < 40  → candidate = 20; phải tới 30
30 < 40  → candidate = 30; phải tới 35
35 < 40  → candidate = 35; phải tới None
Kết quả: 35
```

Dù `40` tồn tại, thuật toán **không trả lại `40`** vì tiền nhiệm được định nghĩa **nhỏ hơn nghiêm ngặt**.

## 8. Kế nhiệm cho mọi khóa truy vấn bằng ứng viên tốt nhất

Quy tắc hoàn toàn đối xứng:

- Nếu `current.key > x`, nút hiện tại **đủ điều kiện** làm kế nhiệm. Lưu nó vào `candidate` và đi **sang trái** để tìm một khóa nhỏ hơn ứng viên nhưng vẫn lớn hơn `x`.
- Nếu `current.key <= x`, nút hiện tại không thể là kế nhiệm. Đi **sang phải**.
- Nếu không tìm được ứng viên thì **không có kế nhiệm**.

```text
SUCCESSOR(root, x):
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

### Vết chạy: `succ(32)`

```text
current = 40: 40 > 32  → candidate = 40; trái
current = 20: 20 <= 32 → phải
current = 30: 30 <= 32 → phải
current = 35: 35 > 32  → candidate = 35; trái
current = None: dừng

Kết quả: 35
```

Ứng viên `35` **tốt hơn `40`** vì cả hai đều lớn hơn `32`, nhưng `35` nhỏ hơn.

### Vết chạy: `succ(60)`

```text
60 > 40 → đi phải tới 60, chưa có candidate
60 = 60 → đi phải tới 80
80 > 60 → candidate = 80; đi trái tới 70
70 > 60 → candidate = 70; đi trái tới None
Kết quả: 70
```

Không cần lưu cha của các nút hoặc tìm trước nút `60`. Thuật toán này phục vụ được cả **khóa hiện có** và **khóa chưa tồn tại**.

## 9. Cài đặt Python hoàn chỉnh

Dưới đây là chương trình tự chứa minh họa việc tạo BST khóa nguyên duy nhất và thực hiện bốn truy vấn. Các hàm cực trị trả **nút** hoặc `None`; người gọi lấy `node.key` khi nút tồn tại.

### Tạo cây ví dụ

```python
class Node:
    def __init__(self, key):
        self.key = key
        self.left = None
        self.right = None


def insert(root, key):
    """BST khóa duy nhất; trả lại gốc sau thao tác."""
    if root is None:
        return Node(key)

    current = root
    while True:
        if key == current.key:
            return root  # Bỏ qua khóa trùng

        if key < current.key:
            if current.left is None:
                current.left = Node(key)
                return root
            current = current.left
        else:
            if current.right is None:
                current.right = Node(key)
                return root
            current = current.right


values = [40, 20, 60, 10, 30, 50, 80, 35, 45, 55, 70, 90, 75]

root = None
for key in values:
    root = insert(root, key)
```

Trong ví dụ này, `values` là **thứ tự chèn**, không phải danh sách đã sắp. Thứ tự BST được hình thành bởi các đường đi trái/phải khi chèn.

### Minimum và maximum

```python
def min_node(node):
    if node is None:
        return None

    while node.left is not None:
        node = node.left

    return node


def max_node(node):
    if node is None:
        return None

    while node.right is not None:
        node = node.right

    return node


assert min_node(root).key == 10
assert max_node(root).key == 90
assert min_node(None) is None
assert max_node(None) is None
```

Khi cần tìm nhỏ nhất/lớn nhất của **một cây con**, ta chỉ việc truyền **gốc cây con ấy** vào cùng hàm. Ví dụ:

```python
assert min_node(root.right).key == 45
assert max_node(root.left).key == 35
```

Hai kiểm thử này cũng có thể giúp kiểm chứng quy tắc kế nhiệm/tiền nhiệm của nút gốc `40`.

### Tiền nhiệm và kế nhiệm nghiêm ngặt

```python
def predecessor_node(root, x):
    """Nút có khóa lớn nhất < x; None nếu không tồn tại."""
    candidate = None
    current = root

    while current is not None:
        if current.key < x:
            candidate = current
            current = current.right
        else:
            current = current.left

    return candidate


def successor_node(root, x):
    """Nút có khóa nhỏ nhất > x; None nếu không tồn tại."""
    candidate = None
    current = root

    while current is not None:
        if current.key > x:
            candidate = current
            current = current.left
        else:
            current = current.right

    return candidate


assert predecessor_node(root, 40).key == 35
assert successor_node(root, 40).key == 45

assert predecessor_node(root, 60).key == 55
assert successor_node(root, 60).key == 70

assert predecessor_node(root, 32).key == 30
assert successor_node(root, 32).key == 35

assert predecessor_node(root, 10) is None
assert successor_node(root, 90) is None

assert predecessor_node(None, 50) is None
assert successor_node(None, 50) is None
```

### Trả khóa thay vì trả nút

Một ứng dụng thường không muốn để lộ cấu trúc `Node`, nên có thể bao các hàm bằng một giao diện trả kết quả có nhãn:

```python
def neighboring_keys(root, x):
    pred = predecessor_node(root, x)
    succ = successor_node(root, x)
    return {
        "predecessor": None if pred is None else pred.key,
        "successor": None if succ is None else succ.key,
    }


assert neighboring_keys(root, 32) == {
    "predecessor": 30,
    "successor": 35,
}

assert neighboring_keys(root, 10) == {
    "predecessor": None,
    "successor": 20,
}
```

Giao diện trên an toàn vì ta đã giới hạn **khóa là số nguyên**, nên `None` có thể biểu thị thiếu kết quả. Nếu cho phép `None` là một khóa hợp lệ, nên trả `(found, key)` hoặc kiểu `Optional` có phân biệt rõ trạng thái, thay vì suy từ giá trị `None`.

## 10. Phân biệt predecessor/successor với floor/ceiling

Một số tài liệu và thư viện dùng thêm hai khái niệm:

- **Floor** của `x`: khóa **lớn nhất không vượt quá `x`**, tức `max{k ∈ S : k ≤ x}`.
- **Ceiling** của `x`: khóa **nhỏ nhất không nhỏ hơn `x`**, tức `min{k ∈ S : k ≥ x}`.

Khác biệt nằm ở dấu **nghiêm ngặt**:

| Truy vấn | Điều kiện | Nếu `x` có trong cây |
| --- | --- | --- |
| `predecessor(x)` | `k < x` | Không trả `x` |
| `floor(x)` | `k ≤ x` | **Trả `x`** |
| `successor(x)` | `k > x` | Không trả `x` |
| `ceiling(x)` | `k ≥ x` | **Trả `x`** |

Trên cây mẫu:

| Mốc `x` | Tiền nhiệm | Floor | Ceiling | Kế nhiệm |
| ---: | ---: | ---: | ---: | ---: |
| `40` | `35` | `40` | `40` | `45` |
| `32` | `30` | `30` | `35` | `35` |
| `10` | Không có | `10` | `10` | `20` |
| `90` | `80` | `90` | `90` | Không có |
| `5` | Không có | Không có | `10` | `10` |
| `100` | `90` | `90` | Không có | Không có |

Nếu `x` **không nằm trong cây**, predecessor trùng floor và successor trùng ceiling (nếu kết quả tồn tại). Nếu `x` **có mặt**, hai cặp sẽ khác nhau do cách xử lý dấu bằng.

### Cài floor và ceiling bằng cách sửa điều kiện

```python
def floor_node(root, x):
    candidate = None
    current = root

    while current is not None:
        if current.key == x:
            return current
        if current.key < x:
            candidate = current
            current = current.right
        else:
            current = current.left

    return candidate


def ceiling_node(root, x):
    candidate = None
    current = root

    while current is not None:
        if current.key == x:
            return current
        if current.key > x:
            candidate = current
            current = current.left
        else:
            current = current.right

    return candidate


assert floor_node(root, 40).key == 40
assert ceiling_node(root, 40).key == 40
assert floor_node(root, 32).key == 30
assert ceiling_node(root, 32).key == 35
assert floor_node(root, 5) is None
assert ceiling_node(root, 100) is None
```

Trong những thư viện có tên `lower_bound` hoặc `upper_bound`, cần kiểm tra hợp đồng cụ thể: chẳng hạn `lower_bound(x)` thường trả phần tử đầu tiên **không nhỏ hơn** `x`, gần với **ceiling**; `upper_bound(x)` thường trả phần tử đầu tiên **lớn hơn** `x`, gần với **successor nghiêm ngặt**.

## 11. Biết sẵn nút: dùng cây con và liên kết cha

Khi bài toán đã giữ tham chiếu tới **một nút có trong cây**, ta có thể dùng quy tắc cây con/tổ tiên đã nêu ở phần 5–6. Điều này thường xuất hiện khi thiết kế **iterator theo thứ tự** hoặc thực hiện thao tác xóa nút.

### Không có con phải/trái thì tìm qua tổ tiên ra sao?

Giả sử mỗi nút lưu thêm con trỏ `parent`. Ta có thể tìm **kế nhiệm của một nút** như sau:

```text
SUCCESSOR_OF_NODE(node):
    nếu node.right != null:
        return MINIMUM(node.right)

    current = node
    parent = current.parent

    while parent != null và current == parent.right:
        current = parent
        parent = parent.parent

    return parent
```

Nếu `node` nằm ở **cây con phải** của cha, phải tiếp tục đi lên; khi lần đầu đi lên từ một **cây con trái**, cha đó là kế nhiệm. Nếu lên tới trên gốc mà không gặp điều kiện này, nút đang xét chính là **khóa lớn nhất**, không có kế nhiệm.

Tương tự cho tiền nhiệm:

```text
PREDECESSOR_OF_NODE(node):
    nếu node.left != null:
        return MAXIMUM(node.left)

    current = node
    parent = current.parent

    while parent != null và current == parent.left:
        current = parent
        parent = parent.parent

    return parent
```

Chi phí tối đa `O(h)`; nếu chỉ giữ các tham chiếu `current` và `parent` thì bộ nhớ phụ `O(1)`.

**Lưu ý:** nút mẫu trong phần Python **không lưu `parent`**, nên không thể chạy trực tiếp giả mã này mà chưa bổ sung và đồng bộ trường liên kết cha lúc chèn, xóa và quay cây.

### Không có liên kết cha thì sao?

Có hai cách:

1. **Truy vấn từ gốc theo khóa**, dùng `predecessor_node(root, x)` và `successor_node(root, x)` như trên. Đây là cách đơn giản, không phải lưu đường đi.
2. **Lưu stack tổ tiên trong quá trình tìm nút**, rồi lần ngược khi cần. Tốn `O(h)` bộ nhớ phụ cho đường đi, nhưng hữu ích khi duyệt tiếp nhiều nút.

Nếu dùng **con trỏ cha** trong cây tự cân bằng, các phép quay phải cập nhật cả `parent`; nếu quên, truy vấn kế nhiệm theo tổ tiên có thể trả sai dù các khóa vẫn đúng thứ tự.

## 12. Vì sao thuật toán ứng viên là đúng?

Xét thuật toán tìm **tiền nhiệm nghiêm ngặt** của `x`.

**Bất biến vòng lặp:** sau mỗi bước, `candidate` hoặc chưa tồn tại, hoặc là một khóa đã thấy **nhỏ hơn `x`**; và trong những khóa đã loại khỏi hướng tiếp tục, không tồn tại lựa chọn nào tốt hơn ứng viên đã lưu.

Khi đang xét nút có khóa `k`:

- Nếu `k < x`, `k` là một ứng viên hợp lệ. **Toàn bộ cây con trái** của `k` còn nhỏ hơn `k`, nên không thể chứa tiền nhiệm tốt hơn `k`. Ta lưu `k` rồi đi **phải** để thử khóa lớn hơn `k` nhưng vẫn `< x`.
- Nếu `k >= x`, `k` cùng mọi khóa trong **cây con phải** đều không nhỏ hơn `x`, nên không thể là tiền nhiệm. Ta đi **trái** và vẫn không bỏ sót đáp án hợp lệ.

Mỗi lần đổi ứng viên, khóa ứng viên mới tốt hơn (lớn hơn nhưng vẫn dưới `x`). Khi đi tới liên kết rỗng, không còn nút nào trên đường cần xét, vì các cây con khác đã bị loại đúng nhờ bất biến BST. Kết quả cuối chính là **khóa lớn nhất nhỏ hơn `x`**, hoặc không có kết quả.

Lập luận cho **kế nhiệm** là đối xứng:

- `k > x`: lưu ứng viên, bỏ cây con phải, đi trái tìm một khóa còn gần `x` hơn.
- `k <= x`: bỏ nút hiện tại và cây con trái, đi phải.

### Tính đúng đắn của minimum và maximum

Với minimum, nếu nút hiện tại có cây con trái, mọi khóa ở đó đều nhỏ hơn khóa hiện tại, nên **nút hiện tại và toàn bộ cây con phải** không thể có khóa nhỏ nhất. Đi trái là an toàn. Khi không còn con trái, nút hiện tại là nhỏ nhất của cây con đang xét, đồng thời các bước trước đã loại đúng những vùng có khóa lớn hơn. Maximum lập luận đối xứng.

Những chứng minh này đều cần **tiền điều kiện cây thỏa BST**. Chúng không đúng nếu các nút bị đặt sai nhánh.

## 13. Độ phức tạp thời gian và bộ nhớ

Gọi `n` là số nút và `h` là số nút trên đường dài nhất từ gốc đến một lá, với cây rỗng có `h=0`.

| Thao tác | Di chuyển | Thời gian | Bộ nhớ phụ bản lặp |
| --- | --- | --- | --- |
| `minimum(root)` | Đi trái liên tục | `O(h)` | `O(1)` |
| `maximum(root)` | Đi phải liên tục | `O(h)` | `O(1)` |
| `predecessor(root, x)` | Một đường theo so sánh | `O(h)` | `O(1)` |
| `successor(root, x)` | Một đường theo so sánh | `O(h)` | `O(1)` |
| `floor(root, x)` | Một đường theo so sánh | `O(h)` | `O(1)` |
| `ceiling(root, x)` | Một đường theo so sánh | `O(h)` | `O(1)` |
| Tìm nút rồi dùng đường tổ tiên | Có thể đi xuống và đi lên | `O(h)` | `O(1)` với `parent`; `O(h)` nếu lưu stack tổ tiên |
| Duyệt toàn bộ in-order để lấy kết quả | Mọi nút | `O(n)` | `O(h)` nếu duyệt bằng stack, hoặc `O(n)` nếu lưu list |

Điều kiện của bảng: so sánh hai khóa có chi phí cơ bản hằng số; không tính việc định dạng/in kết quả.

### Khi cây cân bằng

Nếu `h = O(log n)`, tìm minimum, maximum, predecessor và successor đều có **độ phức tạp `O(log n)` trong trường hợp xấu nhất**.

Cây **AVL** hoặc cây **đỏ–đen** duy trì giới hạn chiều cao để tránh trường hợp quá lệch. Bản thân những thao tác tìm cực trị và lân cận không cần quay cây, vì chúng **chỉ đọc**, không sửa hình dạng cây.

### Khi cây lệch

Nếu chèn dãy tăng dần vào BST thông thường không tự cân bằng, cây có thể trở thành:

```text
10
  \
   20
     \
      30
        \
         40
           \
            50
```

Khi đó, maximum và successor của một khóa nhỏ có thể phải đi qua **`Θ(n)` nút**. Minimum trên cây này lại lấy ngay gốc trong `O(1)`. Vì vậy bảng dùng `O(h)` là **giới hạn chung**, không có nghĩa mọi lần gọi đều đi đúng `h` bước.

### Bộ nhớ của kết quả

Hàm trả một tham chiếu nút hoặc `None` nên không cần tạo danh sách tất cả khóa. Nếu thay vì trả một lân cận ta muốn liệt kê **`k` khóa liên tiếp**, chi phí bổ sung phụ thuộc việc lưu đầu ra hoặc chỉ phát từng khóa. Khi có iterator in-order thích hợp, có thể lần lượt lấy các phần tử theo thứ tự mà không sắp lại toàn cây mỗi lần.

## 14. Ứng dụng: tìm thời điểm ngay trước và ngay sau

Giả sử một ứng dụng đặt lịch lưu các **phút bắt đầu** của buổi học từ đầu ngày:

```text
S = {540, 600, 690, 750}
    09:00, 10:00, 11:30, 12:30
```

Ta cần tìm buổi **diễn ra gần nhất trước mốc 10:45** (phút `645`) và buổi **sớm nhất sau mốc đó**.

```python
schedule_root = None
for minute in (690, 540, 750, 600):
    schedule_root = insert(schedule_root, minute)

before = predecessor_node(schedule_root, 645)
after = successor_node(schedule_root, 645)

assert before.key == 600  # 10:00
assert after.key == 690   # 11:30
```

Nếu mốc chính xác trùng với một lịch đã có, ví dụ `600`:

- `predecessor(600) = 540`: buổi **trước 10:00**, không gồm 10:00.
- `floor(600) = 600`: buổi **muộn nhất không sau 10:00**, gồm 10:00.
- `ceiling(600) = 600`: buổi **sớm nhất không trước 10:00**.
- `successor(600) = 690`: buổi **sau 10:00**, không gồm 10:00.

Chọn sai dấu `<, <=, >, >=` sẽ dẫn tới kết quả khác biệt ngay tại biên. Trong ứng dụng thực tế, còn cần quy định lịch trùng thời gian, múi giờ và chính sách khóa, nhưng những yếu tố đó không thay đổi ý tưởng truy vấn lân cận BST.

## 15. Ứng dụng mở rộng: truy vấn khoảng và xóa BST

### Tìm lân cận trước khi thực hiện truy vấn khoảng

Khi cần lấy các khóa thuộc `[low, high]` theo thứ tự, ta có thể bắt đầu tại **ceiling(low)** rồi đi theo kế nhiệm, dừng khi vượt `high`.

```text
low = 32, high = 75
ceiling(32) = 35
Các khóa thuộc khoảng:
35, 40, 45, 50, 55, 60, 70, 75
```

Nếu đã có iterator in-order hoặc con trỏ cha, việc đi liên tiếp từ một nút sang kế nhiệm giúp tránh **tìm lại từ gốc cho từng khóa**. Một triển khai range query có thể đạt thời gian `O(h + k)` để xuất `k` khóa thuộc khoảng khi dùng cách duyệt có cắt tỉa phù hợp.

Nếu cứ gọi `successor_node(root, x)` từ gốc cho từng khóa, chi phí có thể lên tới `O(kh)` cộng chi phí tìm điểm đầu; vì vậy cần phân biệt **thuật toán đúng** với **thuật toán tối ưu cho nhiều kết quả liên tiếp**.

### Dùng kế nhiệm khi xóa nút có hai con

Khi xóa một nút BST có **hai con**, ta có thể tìm **khóa nhỏ nhất trong cây con phải** làm khóa thay thế (*in-order successor*). Ví dụ:

```text
Trước xóa khóa 40:

                 40
               /    \
             20      60
                    /
                   50
                  /
                 45

succ(40) = 45
```

Sau khi thay thế đúng cách, phải xóa vị trí cũ của `45` và nối lại liên kết thích hợp để không tạo hai nút cùng khóa. Đây là lý do thuật toán minimum trên cây con xuất hiện lại trong thao tác **xóa BST**.

**Không phải chỉ cần gán đè khóa rồi dừng:** nếu bỏ quên nút successor ở vị trí cũ, BST khóa duy nhất bị phá vì xuất hiện bản sao; nếu di chuyển nút sai liên kết, có thể làm mất cây con.

## 16. Những lỗi thường gặp và cách nhận biết

1. **Nhầm tiền nhiệm với cha.** Cha của `35` là `30` và cũng là tiền nhiệm trong ví dụ, nhưng ở vị trí khác tiền nhiệm có thể nằm sâu trong cây con trái hoặc là tổ tiên xa.
2. **Nhầm kế nhiệm với con phải.** Kế nhiệm của `40` là `45`, không phải con phải trực tiếp `60`.
3. **Dùng `x - 1` hoặc `x + 1`.** BST chứa tập khóa rời rạc; tiền nhiệm/kế nhiệm là lân cận **trong tập**, không nhất thiết là số nguyên liền kề.
4. **Quên “nghiêm ngặt”.** `predecessor(x) < x` và `successor(x) > x`; floor/ceiling mới cho phép bằng.
5. **Yêu cầu khóa truy vấn phải tồn tại.** Thuật toán ứng viên vẫn trả tiền nhiệm/kế nhiệm cho mốc không có trong cây.
6. **Dùng minimum của cây trái làm tiền nhiệm.** Khi nút có con trái, tiền nhiệm phải là **maximum của cây trái**, không phải minimum.
7. **Dùng maximum của cây phải làm kế nhiệm.** Kế nhiệm phải là **minimum của cây phải**.
8. **Đi về bất kỳ tổ tiên nào.** Khi không có cây con thích hợp, phải chọn tổ tiên gần nhất thỏa **hướng rẽ đúng**.
9. **Quên cập nhật ứng viên.** Khi tìm lân cận nghiêm ngặt, ứng viên mới phù hợp hơn phải thay ứng viên cũ.
10. **Cập nhật ứng viên khi khóa bằng `x`.** Điều này có thể khiến thuật toán strict trả chính `x`.
11. **Không xử lý cây rỗng hoặc phần tử biên.** Cây rỗng không có min/max; phần tử nhỏ nhất không có tiền nhiệm, lớn nhất không có kế nhiệm.
12. **Dùng `None` làm dấu thiếu khi `None` là khóa hợp lệ.** Cần một kiểu kết quả phân biệt sự hiện diện.
13. **Cho rằng mọi BST có `O(log n)`.** BST lệch có thể có chiều cao `O(n)`; chỉ cây được cân bằng mới bảo đảm logarit.
14. **Dùng bộ so sánh khác nhau giữa chèn và tìm lân cận.** Kết quả có thể sai hoặc khó dự đoán.
15. **Thay đổi trường định danh của khóa khi nút đã nằm trong cây.** Có thể làm sai thứ tự, khiến minimum/predecessor/successor dựa vào bất biến không còn đúng.
16. **Đánh đồng nút có khóa bằng nhau với bản sao hợp lệ.** Bài này giả định một nút cho mỗi khóa; cấu trúc đa tập hợp cần chính sách trùng riêng.
17. **Duyệt toàn cây cho mọi truy vấn dù chỉ cần một lân cận.** Duyệt in-order `O(n)` vẫn có thể đúng, nhưng không khai thác lợi thế `O(h)` của BST.

## 17. Kiểm thử đối chiếu với dãy khóa đã sắp

Một cách kiểm thử tốt là **không dùng lại chính thuật toán cây để tính đáp án mong đợi**. Khi dữ liệu nhỏ, có thể lấy dãy khóa đã sắp và so sánh kết quả với truy vấn BST.

```python
keys = sorted(set(values))
assert keys == [
    10, 20, 30, 35, 40, 45, 50, 55, 60, 70, 75, 80, 90
]


def expected_predecessor(keys, x):
    smaller = [key for key in keys if key < x]
    return max(smaller) if smaller else None


def expected_successor(keys, x):
    larger = [key for key in keys if key > x]
    return min(larger) if larger else None


def key_or_none(node):
    return None if node is None else node.key


for x in (-100, 10, 32, 40, 60, 75, 90, 100):
    assert key_or_none(predecessor_node(root, x)) == (
        expected_predecessor(keys, x)
    )
    assert key_or_none(successor_node(root, x)) == (
        expected_successor(keys, x)
    )
```

Kiểm thử tham chiếu trên dùng **lọc list rồi lấy min/max**, có thể tốn `O(n)` mỗi lượt, nhưng dễ kiểm tra tính đúng đắn cho tập dữ liệu nhỏ. Một triển khai tối ưu hơn cho mảng đã sắp có thể dùng tìm nhị phân. Mục đích của phép đối chiếu không phải đo tốc độ, mà là phát hiện lỗi ở **biên**, **dấu so sánh**, và **khóa không tồn tại**.

Các trường hợp nên kiểm thử thêm: cây rỗng, cây một nút, BST chỉ có nhánh trái, chỉ có nhánh phải, khóa âm, khoảng trống lớn giữa hai khóa, và khóa có bộ so sánh tùy biến.

## 18. Tự luyện tập

**Bài 1.** Với cây mẫu ở phần 2, viết đường đi từ gốc để tìm **khóa nhỏ nhất** và **khóa lớn nhất**. Mỗi đường thăm bao nhiêu nút?

**Bài 2.** Tính `pred(40)` và `succ(40)` bằng hai quy tắc: cây con trái/phải và thuật toán ứng viên từ gốc. Kết quả có trùng nhau không?

**Bài 3.** Tính `pred(35)` và `succ(35)`. Vì sao kế nhiệm `35` không phải cha trực tiếp của nó?

**Bài 4.** Trên cây mẫu, tìm tiền nhiệm và kế nhiệm của `32`, `56`, `9` và `100`. Những mốc nào không nằm trong cây?

**Bài 5.** Giải thích sự khác biệt giữa `pred(60)` và `floor(60)`, giữa `succ(60)` và `ceiling(60)`.

**Bài 6.** Cây rỗng có minimum/maximum hay không? Cây chỉ chứa khóa `7` có những kết quả nào cho minimum, maximum, predecessor(7), successor(7), floor(7), ceiling(7)?

**Bài 7.** Viết giả mã tìm tiền nhiệm nghiêm ngặt mà **không** cần lưu con trỏ cha. Giải thích vì sao khi gặp khóa `< x` phải tiếp tục tìm **sang phải**.

**Bài 8.** Một BST bị lệch hoàn toàn sang phải do chèn khóa tăng dần. Phân tích chi phí tìm minimum, maximum và successor của khóa nhỏ nhất.

**Bài 9.** Nếu có con trỏ `parent`, làm thế nào tìm successor của một nút **không có cây con phải**? Khi nào kết luận không có successor?

**Bài 10.** Viết hàm `neighbors(root, x)` trả cặp `(predecessor, successor)` theo quy tắc strict và xử lý cây rỗng.

**Bài 11.** Giả sử tập khóa là `{100, 200, 500}`. Tính predecessor/successor/floor/ceiling của `200` và `300`. Vì sao không thể dùng `x ± 1`?

**Bài 12.** Một ứng dụng phải liệt kê `k` khóa tiếp theo sau một mốc `x`. So sánh việc gọi `successor(root, current)` từ gốc `k` lần với sử dụng iterator in-order đã được định vị ở khóa đầu tiên.

<details>
<summary>Đáp án và gợi ý</summary>

1. Min: `40 → 20 → 10`, thăm 3 nút. Max: `40 → 60 → 80 → 90`, thăm 4 nút.
2. `pred(40) = max(left(40)) = 35` và `succ(40) = min(right(40)) = 45`. Hai thuật toán ứng viên cũng trả `35` và `45`.
3. `pred(35) = 30`; `succ(35) = 40`. Cha `30` nhỏ hơn `35` nên không thể là kế nhiệm; phải lên tới tổ tiên `40` có nhánh đi sang trái.
4. `x=32`: `(30,35)`; `x=56`: `(55,60)`; `x=9`: `(không có,10)`; `x=100`: `(90,không có)`. Cả bốn mốc đều không thuộc cây mẫu.
5. `pred(60)=55` còn `floor(60)=60`; `succ(60)=70` còn `ceiling(60)=60`. Floor/ceiling cho phép bằng mốc.
6. Cây rỗng không có cực trị. Cây `{7}` có `min=max=7`, `pred(7)=succ(7)=không có`, `floor(7)=ceiling(7)=7`.
7. Lưu ứng viên; nếu `node.key < x` thì nhận nút làm ứng viên và sang phải để thử khóa lớn hơn mà vẫn `< x`; ngược lại sang trái. Khi tới rỗng, trả ứng viên.
8. Minimum có thể là gốc, `O(1)`. Maximum phải đi hết chuỗi, `Θ(n)`. Successor của khóa nhỏ nhất (nếu có con phải trực tiếp) là khóa con phải của nó, có thể `O(1)`, dù một truy vấn successor cho mốc khác có thể mất `Θ(n)`. Vì vậy kết quả phụ thuộc vị trí và dạng truy vấn cụ thể.
9. Đi ngược bằng `parent` đến tổ tiên đầu tiên mà nút đang xét thuộc **cây con trái** của tổ tiên ấy; trả tổ tiên. Nếu lên qua gốc mà không gặp trường hợp đó, không có successor.
10. Có thể dùng:

```python
def neighbors(root, x):
    p = predecessor_node(root, x)
    s = successor_node(root, x)
    return (
        None if p is None else p.key,
        None if s is None else s.key,
    )


assert neighbors(root, 32) == (30, 35)
assert neighbors(None, 32) == (None, None)
```

11. Với `200`: `pred=100`, `succ=500`, `floor=200`, `ceiling=200`. Với `300`: `pred=floor=200`, `succ=ceiling=500`. Khóa được lưu có khoảng cách tùy ý.
12. Mỗi lần gọi từ gốc có thể tốn `O(h)` nên `k` lần tốn tới `O(kh)`. Nếu dùng duyệt in-order thích hợp, chi phí định vị ban đầu `O(h)` và xuất tiếp `k` khóa có thể đạt `O(h+k)` tổng (không tính chi phí lưu đầu ra).

</details>

## Ghi nhớ

Trong **BST hợp lệ**, **minimum** nằm trên đường đi **trái liên tục**, còn **maximum** nằm trên đường đi **phải liên tục**. **Tiền nhiệm nghiêm ngặt** của `x` là khóa lớn nhất **nhỏ hơn** `x`; **kế nhiệm nghiêm ngặt** là khóa nhỏ nhất **lớn hơn** `x`. Nếu truy vấn một khóa có sẵn, có thể dùng cực trị trong cây con hoặc tổ tiên phù hợp; với **mọi mốc truy vấn**, kể cả mốc không tồn tại, thuật toán **ứng viên tốt nhất** từ gốc giải quyết cả hai bài toán chỉ trong **`O(h)` thời gian, `O(1)` bộ nhớ phụ**. Hãy phân biệt rõ với **floor/ceiling** (cho phép bằng), xử lý kết quả không tồn tại ở hai đầu tập khóa và nhớ rằng **BST không tự cân bằng có thể có `h=O(n)`**.

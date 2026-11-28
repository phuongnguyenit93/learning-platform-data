# Duyệt giữa để lấy các khóa theo thứ tự

Một nền tảng học tập lưu các hồ sơ theo **mã học viên** trong **cây tìm kiếm nhị phân** (*Binary Search Tree – BST*). Tra cứu một mã cụ thể chỉ cần đi theo đường so sánh; nhưng nếu cần **xuất danh sách tất cả mã theo thứ tự tăng dần**, ta làm cách nào? Có cần thu toàn bộ mã rồi gọi hàm sắp xếp hay không?

Với một **BST hợp lệ**, câu trả lời là **duyệt giữa** (*in-order traversal*): thăm **cây con trái → nút hiện tại → cây con phải**. Nhờ bất biến thứ tự của BST, các khóa được phát ra **đã có thứ tự**, không cần sắp xếp lại.

Bài thuộc chương **Cây tìm kiếm nhị phân** trong module cấu trúc dữ liệu. Ta sẽ học cách mô phỏng thứ tự duyệt, chứng minh tính tăng của dãy khóa, cài đặt đệ quy, dùng stack tường minh và generator Python, so sánh chi phí thời gian/bộ nhớ, rồi ứng dụng vào xuất dữ liệu, truy vấn khoảng và kiểm thử bất biến.

## 1. Duyệt giữa là gì?

Một **cây nhị phân** có mỗi nút tối đa hai con. Có ba quy tắc duyệt theo chiều sâu thường gặp:

| Cách duyệt | Thứ tự | Tên tiếng Anh |
| --- | --- | --- |
| Duyệt trước | **Nút → Trái → Phải** | Pre-order (NLR) |
| **Duyệt giữa** | **Trái → Nút → Phải** | In-order (LNR) |
| Duyệt sau | **Trái → Phải → Nút** | Post-order (LRN) |

Trong bài, “thăm nút” nghĩa là **xử lý nút đó**, chẳng hạn đọc `key`, lấy cặp `(key, value)` hoặc đưa vào kết quả. Không nhất thiết phải in ra màn hình.

### Quy tắc LNR áp dụng đệ quy ở mọi mức

```text
INORDER(node):
    nếu node là rỗng:
        return

    INORDER(node.left)
    VISIT(node)
    INORDER(node.right)
```

Khi đứng ở một nút, **không** phát khóa của nó ngay lập tức nếu còn phải duyệt cây con trái. Ta phải xử lý **toàn bộ** cây con trái, rồi mới xử lý nút, sau đó mới sang cây con phải.

### Cây nhị phân khác BST

**Duyệt giữa là thuật toán áp dụng được cho mọi cây nhị phân**, nhưng **chỉ BST thỏa bất biến thứ tự tương ứng** mới bảo đảm kết quả đã được sắp xếp theo khóa.

Ví dụ cây nhị phân:

```text
        20
       /  \
     40    10
```

Duyệt giữa cho `40, 20, 10`, **không tăng dần**. Thuật toán duyệt không sai; cây này chỉ **không phải BST** theo quy tắc trái nhỏ hơn, phải lớn hơn.

## 2. Bất biến BST tạo ra thứ tự tăng

Trong bài này, ta chọn chính sách **khóa phân biệt**, với một quy tắc so sánh ổn định:

1. Mọi khóa thuộc **toàn bộ cây con trái** nhỏ hơn khóa tại nút.
2. Mọi khóa thuộc **toàn bộ cây con phải** lớn hơn khóa tại nút.
3. Hai cây con cũng là BST hợp lệ theo cùng quy tắc.

```text
BST(node):
    mọi k trong left(node):  k < node.key
    mọi k trong right(node): k > node.key
    BST(left(node)) và BST(right(node))
```

Quy tắc áp dụng cho **toàn bộ hậu duệ**, không chỉ hai con trực tiếp. Khi duyệt giữa:

- Các khóa thuộc cây con trái xuất hiện **trước** khóa của nút.
- Khóa nút xuất hiện ở **giữa**.
- Các khóa thuộc cây con phải xuất hiện **sau** khóa của nút.

Do đó, phép duyệt trung thứ tự của BST khóa duy nhất tạo thành một dãy **tăng nghiêm ngặt**.

**Quan trọng:** thứ tự được quyết định bởi **khóa `key`**, không phải bởi giá trị `value` gắn với khóa trong một tree map. Với một BST-map, điểm học viên có thể giảm hoặc tăng tùy ý mà dãy mã học viên vẫn tăng theo thứ tự mã.

## 3. Ví dụ truy vết trên một BST nhiều tầng

Xét cây:

```text
                          50
                        /    \
                      30      75
                     /  \    /  \
                   20   40  60   90
                       / \  / \  /
                      35 45 55 70 80
```

Các khóa được chèn để tạo cây này:

```text
50, 30, 75, 20, 40, 60, 90, 35, 45, 55, 70, 80
```

**Thứ tự chèn không phải thứ tự duyệt giữa**. Thứ tự chèn bắt đầu bằng `50`, nhưng duyệt giữa phải bắt đầu tại khóa nhỏ nhất, ở sâu bên trái.

### Diễn giải từng cây con

Tại gốc `50`:

1. Trước hết duyệt toàn bộ cây con gốc `30`.
2. Sau đó mới phát `50`.
3. Cuối cùng duyệt toàn bộ cây con gốc `75`.

Cây con gốc `30` có:

```text
          30
         /  \
       20    40
            /  \
           35   45

INORDER = 20, 30, 35, 40, 45
```

Cây con gốc `75` có:

```text
          75
         /  \
       60    90
      /  \   /
     55  70 80

INORDER = 55, 60, 70, 75, 80, 90
```

Ghép theo **Trái → Nút → Phải** tại gốc `50`:

```text
Trái của 50:   20, 30, 35, 40, 45
Nút gốc:       50
Phải của 50:   55, 60, 70, 75, 80, 90

Kết quả:
20, 30, 35, 40, 45, 50, 55, 60, 70, 75, 80, 90
```

### Vết thứ tự phát khóa

| Thứ tự phát | Khóa | Vì sao xuất hiện ở đây? |
| ---: | ---: | --- |
| 1 | `20` | Khóa nhỏ nhất, không có cây con trái |
| 2 | `30` | Đã xong cây trái của `30` |
| 3 | `35` | Nằm bên trái `40` |
| 4 | `40` | Đã xong cây trái của `40` |
| 5 | `45` | Nằm bên phải `40` |
| 6 | `50` | Đã duyệt hết cây con trái của gốc |
| 7 | `55` | Nhỏ nhất trong cây con phải của gốc |
| 8 | `60` | Sau khi xử lý cây trái của `60` |
| 9 | `70` | Bên phải `60` nhưng vẫn bên trái `75` |
| 10 | `75` | Đã xong cây con trái của `75` |
| 11 | `80` | Nằm ở trái `90` |
| 12 | `90` | Khóa lớn nhất |

Nhìn vào cây chỉ có thể mô tả đúng trình tự nếu **duyệt hết phần bên trái ở mỗi tầng** trước khi phát nút hiện tại.

## 4. Vì sao dãy khóa sau duyệt giữa tăng nghiêm ngặt?

Ta chứng minh bằng **quy nạp theo cấu trúc cây**.

**Cơ sở:** cây rỗng cho dãy rỗng; cây một nút cho dãy một phần tử. Hai dãy đều tăng nghiêm ngặt theo nghĩa không có cặp liền kề vi phạm.

**Bước quy nạp:** giả sử cây con trái và cây con phải của nút `x` đều là BST hợp lệ và kết quả in-order của chúng lần lượt đã tăng nghiêm ngặt. Gọi:

- `L`: dãy khóa thu được từ cây con trái;
- `k = x.key`: khóa nút hiện tại;
- `R`: dãy khóa thu được từ cây con phải.

Vì bất biến BST đúng **trên toàn bộ cây con**, mọi phần tử trong `L` đều `< k` và mọi phần tử trong `R` đều `> k`. Do đó, dãy ghép:

```text
INORDER(x) = L + [k] + R
```

vẫn tăng nghiêm ngặt. Lập luận đúng tại mọi nút, nên đúng ở gốc.

**Kết luận:** duyệt giữa thu các khóa đã sắp xếp **vì cây là BST**, chứ không phải vì thuật toán có thao tác so sánh và sắp xếp bên trong vòng duyệt.

### Đảo chiều lập luận để kiểm tra

Với một **cây nhị phân hữu hạn, đúng cấu trúc, khóa duy nhất** và phép so sánh nhất quán, việc các khóa in-order tăng nghiêm ngặt cũng là một cách xác minh bất biến thứ tự BST.

Nếu dãy giảm tại một vị trí hoặc có hai khóa bằng nhau trong chính sách khóa duy nhất, cây không hợp lệ. Tuy nhiên, chỉ kiểm tra thứ tự khóa không tự xác nhận **liên kết `parent`, metadata, không có chu trình hoặc nút bị dùng chung** nếu đầu vào vốn không còn là một cây đúng nghĩa.

## 5. Cài đặt Python: lớp Node và tạo BST minh họa

Ta dùng ví dụ **BST-map** với mỗi nút lưu `key` và `value`. Các hàm duyệt cũng áp dụng cho BST-set nếu chỉ lấy trường `key`.

```python
class Node:
    def __init__(self, key, value=None):
        self.key = key
        self.value = value
        self.left = None
        self.right = None


def insert(root, key, value=None):
    """Trả (root, inserted); key trùng thì cập nhật value."""
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


order_of_insertion = [
    50, 30, 75, 20, 40, 60, 90, 35, 45, 55, 70, 80
]
root = None

for key in order_of_insertion:
    root, inserted = insert(root, key, "info-" + str(key))
    assert inserted is True

expected_keys = [
    20, 30, 35, 40, 45, 50, 55, 60, 70, 75, 80, 90
]

# Chèn lại khóa 40 chỉ cập nhật value, không tạo nút trùng.
root, inserted = insert(root, 40, "updated-40")
assert inserted is False
```

Lớp này **không tự cân bằng**. Nó đủ để quan sát cách duyệt giữa, nhưng nếu chèn khóa đã tăng dần, cây có thể lệch và rất sâu. Chúng ta sẽ phân tích ảnh hưởng của chiều cao `h` ở phần sau.

## 6. Duyệt giữa bằng đệ quy: cách trực quan nhất

Hàm đệ quy mô tả nguyên tắc LNR gần như nguyên văn:

```python
def inorder_keys_recursive(root):
    result = []

    def visit(node):
        if node is None:
            return

        visit(node.left)       # L — cây con trái
        result.append(node.key)  # N — nút
        visit(node.right)      # R — cây con phải

    visit(root)
    return result


assert inorder_keys_recursive(root) == expected_keys
assert inorder_keys_recursive(None) == []
assert inorder_keys_recursive(Node(7)) == [7]
```

**Tại sao `result.append(node.key)` nằm giữa hai lời gọi?** Đặt nó trước `visit(node.left)` sẽ biến thao tác thành pre-order; đặt nó sau `visit(node.right)` sẽ thành post-order. Chỉ đặt **giữa** mới bảo đảm khóa bên trái được phát trước nút và khóa bên phải được phát sau nút.

### Duyệt cả cặp khóa–giá trị

Nếu cây dùng làm map, cần xuất `(key, value)` chứ không chỉ khóa:

```python
def inorder_items_recursive(root):
    result = []

    def visit(node):
        if node is None:
            return

        visit(node.left)
        result.append((node.key, node.value))
        visit(node.right)

    visit(root)
    return result


items = inorder_items_recursive(root)

assert [key for key, value in items] == expected_keys
assert dict(items)[40] == "updated-40"
assert len(items) == len(expected_keys)
```

Các cặp được **sắp theo khóa**; giá trị có thể là chuỗi, điểm số, đối tượng khác hay `None`. Duyệt giữa không tự sắp `value`.

### Trường hợp biên của đệ quy

- **Cây rỗng:** gặp `node is None` và trả dãy rỗng.
- **Một nút:** duyệt trái rỗng, phát nút, duyệt phải rỗng.
- **Cây chỉ có nhánh trái:** phát theo thứ tự từ nút sâu nhất lên gốc.
- **Cây chỉ có nhánh phải:** phát lần lượt từ gốc đi xuống.
- **Cây sâu:** dùng nhiều lời gọi lồng nhau, có thể vượt giới hạn đệ quy của Python.

Việc kiểm tra `node is None` phải thực hiện **trước khi truy cập `node.left` hoặc `node.key`**.

## 7. Duyệt giữa không đệ quy bằng stack tường minh

Đệ quy dùng **ngăn xếp lời gọi** của ngôn ngữ. Ta có thể thay nó bằng một **stack do chương trình quản lý**, tránh phụ thuộc giới hạn độ sâu đệ quy.

Ý tưởng:

1. Bắt đầu tại `current = root`.
2. **Đẩy mọi nút trên đường đi trái** vào stack.
3. Lấy một nút ra (nút này không còn cây con trái chưa xử lý), phát khóa của nó.
4. Chuyển sang **cây con phải** của nút vừa phát.
5. Lặp lại cho tới khi **stack rỗng và current là None**.

### Giả mã

```text
INORDER_ITERATIVE(root):
    stack = empty stack
    current = root

    while current != null OR stack không rỗng:
        while current != null:
            stack.push(current)
            current = current.left

        current = stack.pop()
        VISIT(current)
        current = current.right
```

### Mã Python trả danh sách cặp

```python
def inorder_items_iterative(root):
    result = []
    stack = []
    current = root

    while stack or current is not None:
        # Đi tới nút ngoài cùng bên trái của cây con hiện tại.
        while current is not None:
            stack.append(current)
            current = current.left

        # Nút trên đỉnh stack đã duyệt xong cây con trái.
        current = stack.pop()
        result.append((current.key, current.value))

        # Đến lượt cây con phải.
        current = current.right

    return result


iter_items = inorder_items_iterative(root)

assert [key for key, _ in iter_items] == expected_keys
assert iter_items[3] == (40, "updated-40")
assert inorder_items_iterative(None) == []
```

Không cần thêm một tập `visited` nếu đầu vào là **cây nhị phân bình thường, không có chu trình**. Các nút được đẩy rồi lấy ra theo quy tắc stack, mỗi nút được phát **đúng một lần**.

### Ví dụ trạng thái stack khi gặp gốc

Ban đầu, thuật toán đi trái:

```text
stack: [50, 30, 20]    (20 là phần tử trên đỉnh)
current: None
```

Lấy `20` ra, phát `20`. Không có nhánh phải, nên lấy `30`, phát `30`. Sau đó tới cây phải `40`; thuật toán lại đẩy đường trái `40 → 35`, phát `35` trước `40`, v.v.

Stack giữ lại **những tổ tiên còn chờ được xử lý**, vì vậy nút gốc `50` chỉ được lấy ra sau khi toàn bộ cây con trái đã hoàn thành.

## 8. Bất biến của vòng lặp và tính đúng của stack

Một cách diễn đạt **bất biến vòng lặp** của thuật toán lặp là:

> Tại mỗi thời điểm, mọi nút đã phát đều đứng **trước** mọi nút chưa phát theo thứ tự in-order; stack chứa các nút đã đi qua nhưng chưa phát, đang chờ hoàn tất cây con trái.

Khi `current` còn tồn tại, ta tiếp tục **đẩy đường trái** bởi cây con trái của một nút phải được xử lý trước nút ấy. Khi `current` là `None`, nút trên đỉnh stack đã hết nhánh trái chưa duyệt; vì vậy nó là nút **tiếp theo** trong thứ tự in-order.

Sau khi phát nút đó, chỉ cây con phải của nó có thể chứa các nút xuất hiện ngay tiếp theo trong thứ tự. Chuyển `current = node.right` và lặp lại giữ nguyên tính đúng đắn.

Vì mọi nút được đẩy một lần và lấy ra một lần, quá trình kết thúc sau khi đã phát tất cả nút của cây hữu hạn.

**Đừng nhầm:** stack **không phải** hàng đợi (*queue*). Thay stack bằng queue sẽ dẫn tới một thứ tự khác, thường giống duyệt theo tầng nếu dùng theo cách tương ứng.

## 9. Sinh dữ liệu từng phần bằng generator (lazy in-order)

Những hàm trên tạo một **list chứa tất cả kết quả**. Nếu cây có hàng triệu mục, ta có thể chỉ muốn đọc tuần tự, không cần giữ tất cả trong bộ nhớ.

Python có `yield` để tạo **generator**. Khi người gọi yêu cầu phần tử tiếp theo, thuật toán tiếp tục từ trạng thái stack đã lưu và phát một cặp.

```python
def iter_items_inorder(root):
    stack = []
    current = root

    while stack or current is not None:
        while current is not None:
            stack.append(current)
            current = current.left

        current = stack.pop()
        yield current.key, current.value

        current = current.right


assert [key for key, _ in iter_items_inorder(root)] == expected_keys

it = iter_items_inorder(root)
assert next(it) == (20, "info-20")
assert next(it) == (30, "info-30")

from itertools import islice

first_three = list(islice(iter_items_inorder(root), 3))
assert [key for key, _ in first_three] == [20, 30, 35]
```

### Lazy không có nghĩa duyệt không tốn công

Để phát phần tử đầu tiên, iterator có thể phải đi qua đường trái từ gốc, tốn tới `O(h)` thời gian và `O(h)` stack. Sau đó, các phần tử được phát theo thứ tự; **tổng** thời gian để phát cả `n` nút vẫn là `O(n)`.

Với một iterator in-order đúng cách:

- **Bộ nhớ nội bộ:** `O(h)`, không tự lưu toàn bộ `n` khóa.
- **Tổng thời gian duyệt hết:** `O(n)`.
- **Chi phí của một lần `next`:** có thể `O(h)` ở một bước cụ thể, nhưng tổng `n` lần lấy phần tử là `O(n)`; do đó trung bình khấu hao `O(1)` mỗi nút sau chi phí khởi tạo thích hợp.

Nếu người gọi làm `list(iter_items_inorder(root))`, **list do người gọi tạo** vẫn chiếm `O(n)` bộ nhớ. Đó là lựa chọn của bên tiêu thụ generator, không phải của bản thân iterator.

### Thay đổi cây trong khi duyệt

Generator giữ tham chiếu tới các nút chưa xử lý. Nếu một thao tác khác **chèn, xóa hoặc quay cây** trong lúc generator đang tạm dừng giữa các lần `next`, kết quả có thể không còn phù hợp, thậm chí bỏ qua hoặc lặp một số phần tử.

Trong bài này, **giả định cây không bị thay đổi cấu trúc trong suốt một lượt duyệt**. Các thư viện sản xuất có thể dùng iterator fail-fast, snapshot hoặc đồng bộ; không nên tự giả định generator trên đây an toàn khi có cập nhật đồng thời.

## 10. Duyệt giữa theo chiều giảm: Phải → Nút → Trái

Nếu muốn danh sách khóa **giảm dần**, ta đảo thứ tự xét hai cây con:

```text
REVERSE_INORDER(node):
    REVERSE_INORDER(node.right)
    VISIT(node)
    REVERSE_INORDER(node.left)
```

Cài đặt lặp:

```python
def iter_keys_descending(root):
    stack = []
    current = root

    while stack or current is not None:
        while current is not None:
            stack.append(current)
            current = current.right

        current = stack.pop()
        yield current.key

        current = current.left


descending = list(iter_keys_descending(root))

assert descending == list(reversed(expected_keys))
assert descending[0] == 90
assert descending[-1] == 20
```

BST không cần sửa liên kết để duyệt giảm dần; ta chỉ đổi hướng đi ưu tiên. Đây là cách lấy danh sách từ khóa lớn nhất về nhỏ nhất, chẳng hạn hiển thị mã hoặc điểm ưu tiên khi **chính khóa** đang biểu diễn tiêu chí cần xếp.

**Lưu ý:** duyệt giảm trên cây được so sánh theo một comparator tùy biến là giảm theo **comparator ấy**, không nhất thiết giảm theo bảng chữ cái hay giá trị số nguyên.

## 11. Khóa trùng và quy tắc so sánh

Ta đã dùng BST có **khóa phân biệt**, nên dãy in-order phải **tăng nghiêm ngặt**:

```text
20 < 30 < 35 < 40 < 45 < 50 < ...
```

Nhưng chính sách khóa trùng làm thay đổi cách diễn giải kết quả.

| Kiểu lưu trữ | Khi chèn lại khóa đã có | Kết quả duyệt giữa |
| --- | --- | --- |
| **BST-set** | Không thêm nút | Mỗi khóa xuất hiện một lần |
| **BST-map** | Cập nhật `value` | Mỗi khóa một cặp `(key, value)` |
| **BST-multiset có `count`** | Tăng bộ đếm tại nút | Mỗi khóa phân biệt một lần nếu duyệt nút; có thể phát lặp theo `count` |
| **BST-multimap** | Thêm vào collection ở cùng nút | Khóa được duyệt theo thứ tự; có thể có nhiều giá trị cho mỗi khóa |
| **BST cho phép nút trùng** | Lưu nhiều nút có cùng khóa theo chính sách riêng | Dãy khóa có thể chỉ **không giảm**, không tăng nghiêm ngặt |

### Ví dụ multiset gom bản sao tại nút

Giả sử mỗi nút có `key` và `count`, một lượt in-order chỉ thấy các **khóa phân biệt**:

```text
Nút: (10, count=2), (20, count=3), (30, count=1)

Duyệt nút theo thứ tự: 10, 20, 30

Nếu cần phát cả bản sao:
10, 10, 20, 20, 20, 30
```

Khi đó, người viết iterator phải lặp khóa theo `count` tại mỗi nút. Không nên nhầm số nút với tổng số bản sao.

### Comparator quyết định thế nào là “đã sắp”

Nếu BST được tổ chức bằng comparator không phân biệt hoa/thường, một dãy tăng theo comparator ấy có thể trông khác với kết quả `sorted(...)` mặc định trong Python.

Ví dụ, một comparator có thể xếp `"HV2"` trước `"HV10"` theo phần số, trong khi thứ tự chuỗi từ điển có thể xếp chúng theo một cách khác.

**Bất biến cần giữ:** thuật toán **chèn, tìm, xóa và xác minh thứ tự** phải dùng **cùng quy tắc so sánh**. Nếu thay comparator sau khi xây cây mà không tổ chức lại dữ liệu, kết quả in-order có thể không còn “đã sắp” theo comparator mới.

Cần quy định rõ cả việc hai khóa được coi là **tương đương** theo comparator. Với tree set/map, hai khóa được comparator xem là bằng nhau thường chỉ đại diện một khóa logic.

## 12. Truy vấn khoảng: chỉ phát khóa nằm trong [lo, hi)

Xuất **tất cả** khóa đã sắp bằng in-order mất `O(n)`. Nhưng nếu chỉ cần khóa trong một khoảng nhỏ, ví dụ `35 <= key < 75`, ta có thể **cắt tỉa các nhánh không phù hợp**.

Một cách đệ quy trực tiếp:

- Nếu `node.key > lo`, **cây con trái có thể** chứa khóa `>= lo`, nên xét trái.
- Nếu `lo <= node.key < hi`, phát nút.
- Nếu `node.key < hi`, **cây con phải có thể** chứa khóa `< hi`, nên xét phải.

Các điều kiện trên dùng BST có khóa phân biệt. Cây con không cần thăm nếu chắc chắn mọi khóa của nó ngoài khoảng.

### Mã duyệt khoảng bằng cắt tỉa đệ quy

```python
def range_keys_recursive(root, lo, hi):
    """Trả khóa lo <= key < hi theo thứ tự tăng."""
    if lo >= hi:
        return []

    result = []

    def visit(node):
        if node is None:
            return

        if node.key > lo:
            visit(node.left)

        if lo <= node.key < hi:
            result.append(node.key)

        if node.key < hi:
            visit(node.right)

    visit(root)
    return result


assert range_keys_recursive(root, 35, 75) == [
    35, 40, 45, 50, 55, 60, 70
]
assert range_keys_recursive(root, 75, 75) == []
assert range_keys_recursive(root, 100, 200) == []
assert range_keys_recursive(None, 0, 100) == []
```

Cách này có thể bỏ qua nhiều nhánh, nhưng dùng **đệ quy `O(h)`**. Với truy vấn khoảng và đầu ra `k` phần tử, một hiện thực duyệt có cắt tỉa phù hợp đạt giới hạn `O(h+k)`, không tính chi phí tính toán khóa bất thường; việc tạo `result` dùng thêm `O(k)` bộ nhớ.

### Vì sao có thể bỏ cả một nhánh?

Nếu `node.key <= lo`, mọi khóa trong cây con trái đều **nhỏ hơn `node.key`**, do đó cũng nhỏ hơn hoặc bằng `lo`. Với khoảng `[lo,hi)`, không có khóa hợp lệ ở đó.

Nếu `node.key >= hi`, mọi khóa trong cây con phải đều **lớn hơn `node.key`**, nên cũng `>= hi`. Không có khóa nào ở nhánh ấy thuộc khoảng.

Hai cách loại trừ này trực tiếp dựa vào **bất biến BST trên toàn bộ cây con**.

## 13. Iterator khởi đầu từ lower bound thay vì từ khóa nhỏ nhất

Nếu dùng generator in-order thông thường rồi bỏ qua các khóa `< lo`, ta có thể lãng phí thời gian duyệt nhiều nút không thuộc khoảng.

Với BST có thứ tự, ta có thể **định vị khóa đầu tiên không nhỏ hơn `lo`** (lower bound), đồng thời giữ các tổ tiên cần phát tiếp theo trên stack.

### Mã iterator bắt đầu từ cận dưới

```python
def iter_from_lower_bound(root, lo):
    """Sinh cặp có key >= lo theo thứ tự tăng."""
    stack = []
    current = root

    # Bước 1: định vị đường ứng viên >= lo.
    while current is not None:
        if current.key >= lo:
            stack.append(current)
            current = current.left
        else:
            current = current.right

    # Bước 2: tiếp tục in-order từ ứng viên đầu tiên.
    while stack:
        node = stack.pop()
        yield node.key, node.value

        current = node.right
        while current is not None:
            stack.append(current)
            current = current.left


assert [k for k, _ in iter_from_lower_bound(root, 35)][:3] == [
    35, 40, 45
]
assert [k for k, _ in iter_from_lower_bound(root, 78)] == [
    80, 90
]
assert list(iter_from_lower_bound(root, 100)) == []
```

Đối với cây mẫu, không cần duyệt `20` hoặc `30` trước khi phát `35`. Các nút nhỏ hơn cận dưới được loại bằng đường so sánh từ gốc.

### Xuất khoảng nửa mở từ iterator

```python
def range_items(root, lo, hi):
    if lo >= hi:
        return []

    result = []
    for key, value in iter_from_lower_bound(root, lo):
        if key >= hi:
            break
        result.append((key, value))

    return result


selected = range_items(root, 35, 75)

assert [key for key, _ in selected] == [
    35, 40, 45, 50, 55, 60, 70
]
assert dict(selected)[40] == "updated-40"
```

Chi phí:

- Tìm vị trí bắt đầu: **`O(h)`**.
- Phát `k` khóa tiếp theo và dừng ở biên: **`O(k)` theo phân tích khấu hao**.
- Tổng: **`O(h+k)` thời gian**.
- Bộ nhớ nội bộ của iterator: **`O(h)`**.
- Nếu lưu toàn bộ kết quả vào list như `range_items`: thêm **`O(k)`**.

Dùng phương pháp này hữu ích khi tập dữ liệu lớn nhưng khoảng cần xuất rất nhỏ.

### Chọn đúng điều kiện biên

| Khoảng mong muốn | Khóa đầu tiên | Điều kiện dừng |
| --- | --- | --- |
| `[lo, hi)` | `lower_bound(lo)` | Dừng khi `key >= hi` |
| `[lo, hi]` | `lower_bound(lo)` | Dừng khi `key > hi` |
| `(lo, hi)` | `upper_bound(lo)` | Dừng khi `key >= hi` |
| `(lo, hi]` | `upper_bound(lo)` | Dừng khi `key > hi` |

Nếu dùng sai dấu ở điểm đầu hoặc điểm cuối, ta có thể **bỏ sót khóa bằng biên** hoặc **lấy thừa khóa ngoài khoảng**.

## 14. Duyệt giữa và các thao tác dùng thứ tự

Duyệt giữa là nền tảng của nhiều thao tác trên **ordered set/map**:

| Nhu cầu | Vai trò của in-order |
| --- | --- |
| **Liệt kê toàn bộ khóa tăng dần** | Phát từng khóa theo thứ tự mà không sắp lại |
| **In cặp khóa–giá trị** | Phát `(key,value)` theo thứ tự `key` |
| **Lấy khóa nhỏ nhất/lớn nhất** | Phần tử đầu/cuối trong dãy, dù tìm trực tiếp bằng đi trái/phải có thể `O(h)` |
| **Tìm tiền nhiệm/kế nhiệm** | Hai khóa kề nhau trong dãy in-order |
| **Truy vấn khoảng** | Bắt đầu tại lower bound rồi phát tiếp |
| **Kiểm tra BST** | Phát hiện dãy khóa không tăng |
| **Tìm phần tử thứ `k`** | Có thể đếm khi duyệt, hoặc tăng tốc bằng metadata `subtree_size` |
| **Xuất báo cáo theo mã** | Không cần dùng thuật toán sắp xếp riêng sau khi duyệt |

### Không nhầm thứ tự khóa với thứ tự chèn

Một BST thường không ghi nhớ thứ tự các lần chèn để sử dụng làm thứ tự duyệt. Ví dụ chèn `50` trước rồi `20` sau, in-order vẫn phát `20` trước `50`.

Python `dict` hiện đại thường giữ **thứ tự chèn**, nhưng điều đó **không đồng nghĩa** thứ tự tăng theo khóa. Một hash map/hash set nhìn chung không bảo đảm iterator đi theo thứ tự khóa, trừ khi tài liệu của cấu trúc cụ thể cam kết điều ấy.

### Không nhầm BST với heap

Một heap cho phép lấy phần tử ưu tiên nhất nhanh, nhưng **không** bảo đảm “mọi khóa trái nhỏ hơn nút, mọi khóa phải lớn hơn nút”. Do đó, **duyệt giữa heap không đảm bảo sắp xếp**. Nếu muốn sắp bằng heap, cần thuật toán như heap sort hoặc nhiều lần loại phần tử ưu tiên; đó là câu chuyện khác.

## 15. Phân tích thời gian và bộ nhớ

Gọi:

- `n`: số nút trong BST.
- `h`: chiều cao tính bằng **số nút** trên đường dài nhất từ gốc đến một lá; với cây rỗng `h = 0`.
- `k`: số phần tử thực sự cần xuất trong một truy vấn khoảng.

| Cách thực hiện | Thời gian duyệt hết | Bộ nhớ phụ của thuật toán | Bộ nhớ kết quả nếu lưu list |
| --- | --- | --- | --- |
| Đệ quy in-order | `O(n)` | `O(h)` call stack | `O(n)` |
| Lặp với stack | `O(n)` | `O(h)` stack tường minh | `O(n)` |
| Generator in-order | `O(n)` nếu dùng hết | `O(h)` | `O(1)` nếu chỉ tiêu thụ từng mục |
| Iterator từ lower bound, lấy `k` mục | `O(h+k)` | `O(h)` | `O(k)` nếu gom |
| Duyệt rồi tạo list và gọi `sort` | Ít nhất phải duyệt `O(n)` | Tùy hiện thực sort | `O(n)` cho list |

`O(n)` là **chi phí tối ưu về bậc** khi phải phát **toàn bộ `n` khóa**: chỉ riêng việc xuất `n` phần tử cũng cần `Ω(n)` thời gian, ngay cả khi cây cân bằng.

### Tại sao duyệt hết vẫn là O(n) khi BST bị lệch?

Một cây lệch có `h=Θ(n)`, nên độ sâu/stack có thể `Θ(n)`. Nhưng mỗi nút vẫn được thăm một lần; **tổng thời gian duyệt hết** là **`Θ(n)`**, không phải `Θ(n²)`.

Sự lệch chủ yếu ảnh hưởng:

- Bộ nhớ phụ và độ sâu lời gọi `O(h)`;
- Chi phí tìm một khóa hoặc tìm điểm bắt đầu của một khoảng `O(h)`;
- Khả năng vượt giới hạn đệ quy.

**Không nên lấy chi phí `O(h)` của một lần tìm kiếm rồi nhân với `n` để kết luận duyệt giữa cần `O(nh)`.** Một lượt in-order đúng cách chia sẻ trạng thái ngăn xếp và không tìm lại từ gốc cho từng khóa.

### Cây cân bằng khác cây không cân bằng

- **BST cân bằng:** `h = O(log n)`, nên bộ nhớ stack của lượt duyệt `O(log n)`.
- **BST lệch:** `h = O(n)`, nên stack hoặc lời gọi đệ quy có thể `O(n)`.
- **Cả hai:** duyệt toàn bộ `n` nút vẫn `O(n)` thời gian.

## 16. Kiểm tra bất biến BST bằng dãy in-order

Một hàm kiểm thử đơn giản có thể kiểm tra dãy in-order **tăng nghiêm ngặt** mà không cần tạo list toàn bộ khóa.

```python
def is_strict_bst_inorder(root):
    has_previous = False
    previous = None

    for key, value in iter_items_inorder(root):
        if has_previous and not (previous < key):
            return False

        previous = key
        has_previous = True

    return True


assert is_strict_bst_inorder(root) is True
assert is_strict_bst_inorder(None) is True
```

Biến `has_previous` giúp tránh nhầm **khóa có giá trị bằng `None`** với tình huống chưa có khóa trước đó. Trong bài, khóa là số nguyên; bản thân hàm vẫn yêu cầu phép so sánh `<` hợp lệ và nhất quán.

### Phản ví dụ: cây nhị phân có hậu duệ đặt sai

```text
          50
         /  \
       30    70
         \
          60   ← Sai vì 60 nằm trong cây con trái của 50
```

Mọi cặp cha–con trực tiếp trông vẫn thỏa điều kiện địa phương:

```text
30 < 50
70 > 50
60 > 30
```

Nhưng dãy in-order là:

```text
30, 60, 50, 70
    ↑   ↑
    60 > 50: dãy không tăng
```

Kiểm thử Python:

```python
bad = Node(50)
bad.left = Node(30)
bad.left.right = Node(60)
bad.right = Node(70)

assert is_strict_bst_inorder(bad) is False
```

Đây là lý do kiểm tra mỗi quan hệ cha–con **không đủ** để xác minh BST. Một cách kiểm tra khác là truyền biên dưới/trên từ tổ tiên xuống mỗi nút.

**Giới hạn:** kiểm tra dãy tăng giả định đầu vào là một **cây nhị phân hữu hạn, không có chu trình hoặc nút được dùng chung**. Nó cũng không kiểm tra độ chính xác của metadata như `parent` hay `subtree_size`.

## 17. Duyệt giữa kiểu Morris: khi cần O(1) bộ nhớ phụ

Bản đệ quy và bản stack dùng `O(h)` bộ nhớ phụ. Có một kỹ thuật nâng cao gọi là **Morris traversal** có thể duyệt in-order với **`O(1)` bộ nhớ phụ** (không kể kết quả) bằng cách **tạm thay đổi một số liên kết phải**.

Ý tưởng tại nút `current`:

1. Nếu không có cây con trái, phát `current` rồi chuyển sang phải.
2. Nếu có cây con trái, tìm **nút phải nhất** của cây con trái (tiền nhiệm in-order).
3. Nếu `predecessor.right` rỗng, tạo một liên kết **tạm** từ `predecessor` quay tới `current` rồi đi trái.
4. Khi quay lại qua liên kết tạm, **khôi phục `predecessor.right = None`**, phát `current` rồi đi phải.

### Mã Python minh họa Morris in-order

```python
def inorder_keys_morris(root):
    result = []
    current = root

    while current is not None:
        if current.left is None:
            result.append(current.key)
            current = current.right
            continue

        predecessor = current.left
        while (
            predecessor.right is not None
            and predecessor.right is not current
        ):
            predecessor = predecessor.right

        if predecessor.right is None:
            # Tạo liên kết tạm để quay lại current.
            predecessor.right = current
            current = current.left
        else:
            # Đã duyệt xong nhánh trái: khôi phục liên kết.
            predecessor.right = None
            result.append(current.key)
            current = current.right

    return result


assert inorder_keys_morris(root) == expected_keys
assert inorder_keys_recursive(root) == expected_keys
```

Kỹ thuật này có tổng thời gian `O(n)` và **`O(1)` bộ nhớ phụ để điều hướng**, nhưng `result` ở ví dụ vẫn cần `O(n)` để lưu đầu ra.

### Tại sao Morris không phải mặc định tốt nhất?

Morris **tạm thay đổi cấu trúc cây**; trong quá trình duyệt, các liên kết phụ không còn biểu diễn một BST chuẩn. Vì vậy:

- Không nên có lượt tìm/chèn/xóa hoặc iterator khác dùng cùng cây trong khi các liên kết tạm còn tồn tại.
- Nếu dừng sớm hoặc phát sinh ngoại lệ bất ngờ, có nguy cơ **chưa khôi phục hết** liên kết. Không nên viết generator Morris tùy tiện rồi cho người gọi ngừng giữa chừng mà không có cơ chế dọn dẹp bảo đảm.
- Với cây có `parent` hoặc metadata phức tạp, các liên kết tạm không được hiểu là cạnh cha–con bình thường.
- Bản stack tường minh thường **dễ hiểu, dễ kiểm thử và ít rủi ro** hơn.

Morris hữu ích để hiểu đánh đổi **bộ nhớ phụ với việc sửa tạm cấu trúc**, nhưng không phải lựa chọn an toàn mặc định cho một cây đang được dùng chung.

## 18. Ứng dụng thực tế trong nền tảng học tập

Giả sử một chỉ mục tree map lưu:

```text
student_id → (full_name, score)
```

Ví dụ các mã `HV001`, `HV003`, `HV005`, ... được so sánh theo quy tắc mã học viên đã chọn.

Một số nhu cầu:

1. **Xuất báo cáo theo mã học viên tăng dần:** dùng in-order phát từng `(student_id, record)`, không cần sắp xếp lại ở đầu ra.
2. **Hiển thị phân trang theo mốc mã:** định vị lower bound của mã đầu trang, rồi lấy tiếp một số mục bằng iterator.
3. **Đếm các hồ sơ trong khoảng mã:** dùng cắt tỉa BST hoặc iterator bắt đầu ở cận dưới.
4. **Tìm mã kế tiếp:** từ vị trí đã duyệt, lấy phần tử kế tiếp trong thứ tự in-order.
5. **Kiểm thử sau chèn/xóa:** so dãy khóa in-order với `sorted(reference_keys)` của một mô hình tham chiếu.

Nếu ứng dụng chỉ có ít dữ liệu và hầu như không cập nhật, một **mảng đã sắp** cũng có thể hợp lý: duyệt mảng `O(n)` và tìm nhị phân `O(log n)`. Nếu dữ liệu thường xuyên thay đổi và cần truy vấn theo thứ tự, một **BST tự cân bằng** có thể thuận tiện hơn, vì tìm/chèn/xóa thường `O(log n)` theo số nút.

Không nên tự triển khai BST không cân bằng cho dữ liệu sản xuất lớn rồi mặc định mọi thao tác đều nhanh. Chiều cao của nó có thể lên tới `n`, dù in-order vẫn trả các khóa đúng thứ tự.

## 19. Sai lầm thường gặp

1. **Nhầm in-order với pre-order:** phát nút trước cây trái sẽ không bảo đảm khóa tăng.
2. **Nhầm in-order với post-order:** phát nút sau hai cây con cũng không tạo dãy khóa tăng nói chung.
3. **Cho rằng mọi cây nhị phân duyệt giữa đều ra khóa đã sắp:** chỉ đúng nếu cây thỏa bất biến BST theo quy tắc thứ tự phù hợp.
4. **Chỉ kiểm tra con trái/con phải trực tiếp:** có thể bỏ sót hậu duệ vi phạm giới hạn tổ tiên.
5. **Lưu kết quả `value` rồi kỳ vọng giá trị tăng:** BST được tổ chức theo `key`.
6. **Bỏ cơ sở `node is None` trong đệ quy:** dẫn đến lỗi truy cập thuộc tính.
7. **Đặt `append` sai vị trí:** thay đổi loại thứ tự duyệt.
8. **Lấy nút khỏi stack trước khi đã đẩy hết đường trái:** phát nút quá sớm.
9. **Quên chuyển sang `node.right` sau khi phát nút:** bỏ sót cây con phải.
10. **Quên điều kiện `stack or current is not None`:** có thể bỏ sót phần còn chờ hoặc lặp sai.
11. **Cho rằng duyệt cả cây là `O(log n)` vì cây cân bằng:** phải xuất `n` phần tử nên ít nhất `Ω(n)`.
12. **Cho rằng cây lệch làm một lượt in-order thành `O(n²)`:** mỗi nút chỉ được thăm một lần, thời gian vẫn `O(n)`.
13. **Bỏ qua bộ nhớ kết quả:** generator không cần giữ tất cả khóa, nhưng `list(generator)` vẫn dùng `O(n)` bộ nhớ.
14. **Dùng đệ quy trên cây lệch rất sâu mà không xét giới hạn ngăn xếp Python:** có thể gặp `RecursionError`.
15. **Vừa duyệt vừa thay đổi cấu trúc cây mà không có hợp đồng iterator:** có thể bỏ sót, lặp hoặc sai thứ tự.
16. **Dùng comparator khác khi xác minh:** một dãy tăng theo quy tắc xây cây chưa chắc tăng theo quy tắc khác.
17. **Nhầm số nút với số bản sao trong multiset:** nếu mỗi nút lưu `count`, muốn xuất mọi bản sao phải phát nhiều lần.
18. **Duyệt từ khóa nhỏ nhất mỗi khi chỉ cần một khoảng nhỏ:** có thể làm nhiều việc vô ích; nên định vị bằng lower bound.
19. **Không hoàn nguyên liên kết tạm khi dùng Morris:** có thể để cây ở trạng thái không hợp lệ.
20. **Dùng thứ tự duyệt giữa làm bằng chứng đầy đủ rằng parent pointer và metadata đã đúng:** cần kiểm thử riêng các bất biến cấu trúc và thông tin phụ.

## 20. Tự luyện tập

**Bài 1.** Cho BST:

```text
         40
        /  \
      20    60
     / \    / \
    10 30  50 70
```

Hãy viết kết quả duyệt trước, duyệt giữa và duyệt sau. Thứ tự nào tăng nghiêm ngặt?

**Bài 2.** Với cây ví dụ ở phần 3, hãy ghi rõ thứ tự các khóa được phát khi duyệt giữa. Khóa thứ `6` là gì nếu đếm từ 1?

**Bài 3.** Giải thích tại sao cần duyệt **toàn bộ** cây con trái trước khi phát nút gốc của một BST.

**Bài 4.** Viết hàm đệ quy nhận `root` và trả các khóa BST theo thứ tự tăng. Cây rỗng và cây một nút trả gì?

**Bài 5.** Viết thuật toán lặp in-order bằng stack và xác định stack chứa gì ở thời điểm vừa đi hết nhánh trái từ gốc trong cây phần 3.

**Bài 6.** So sánh thời gian và bộ nhớ phụ của duyệt đệ quy, duyệt lặp có stack và generator khi cây có `n` nút, chiều cao `h`.

**Bài 7.** Khi cây lệch thành chuỗi `1 → phải 2 → phải 3 → phải 4`, in-order cho dãy gì? Thời gian và độ sâu stack là bao nhiêu nếu duyệt lặp?

**Bài 8.** Một BST-map có khóa `10, 20, 30` và giá trị tương ứng `"Z", "A", "M"`. Duyệt in-order các **cặp** cho thứ tự nào? Có phải các giá trị theo thứ tự chữ cái không?

**Bài 9.** Cây nhị phân sau có phải BST không? Dùng in-order để chứng minh:

```text
         50
        /  \
       30  70
         \
          60
```

**Bài 10.** Một multiset có các khóa `10` xuất hiện 2 lần, `20` xuất hiện 3 lần, `30` xuất hiện 1 lần. Nếu lưu mỗi khóa một nút và thêm `count`, phải sửa thao tác phát nút thế nào để xuất đủ mọi bản sao?

**Bài 11.** Với cây phần 3, hãy lấy các khóa thuộc khoảng `[35, 75)`. Tại sao không nên phát `75`?

**Bài 12.** Nếu chỉ cần 3 khóa đầu tiên `>= 55`, hãy nêu cách dùng iterator từ lower bound và ước lượng thời gian theo `h`.

**Bài 13.** Vì sao không nên thay generator in-order bằng việc gọi hàm tìm successor từ **gốc** cho từng khóa nếu muốn xuất `n` mục liên tiếp?

**Bài 14.** Morris traversal đạt `O(1)` bộ nhớ phụ nhờ cơ chế nào? Rủi ro gì xảy ra khi ngừng duyệt giữa chừng?

<details>
<summary>Đáp án và gợi ý</summary>

1. Pre-order: `40,20,10,30,60,50,70`. In-order: `10,20,30,40,50,60,70`. Post-order: `10,30,20,50,70,60,40`. **In-order** cho dãy tăng nghiêm ngặt.
2. `20,30,35,40,45,50,55,60,70,75,80,90`. Khóa thứ 6 (đếm từ 1) là `50`.
3. Theo bất biến BST, **mọi** khóa của cây con trái đều nhỏ hơn khóa gốc. Nếu phát gốc trước khi xong cây trái, có thể phát một khóa lớn trước các khóa nhỏ hơn.
4. Dùng `visit(left)`, rồi `append(key)`, rồi `visit(right)`; cây rỗng trả `[]`, cây chỉ có `7` trả `[7]`.
5. Bắt đầu `current = 50`, đẩy `50, 30, 20`; stack là `[50,30,20]`, đỉnh là `20`. Lấy `20` trước.
6. Cả ba duyệt hết `O(n)` thời gian. Đệ quy dùng `O(h)` call stack, lặp dùng `O(h)` stack tường minh, generator dùng `O(h)` trạng thái nội bộ; nếu tạo list đầu ra thêm `O(n)`.
7. Dãy `1,2,3,4`; duyệt hết `Θ(n)` thời gian. Với cây lệch **phải**, stack trong vòng lặp không phải lúc nào cũng dài `n`; mức dùng thực tế có thể chỉ `O(1)`, nhưng giới hạn chung cho một cây chiều cao `h` là `O(h)`.
8. Các cặp `(10,"Z"), (20,"A"), (30,"M")`. Không, thứ tự là theo **khóa**, không theo giá trị chuỗi.
9. Không hợp lệ: nút `60` nằm ở cây con trái của `50` nhưng `60 > 50`. Duyệt giữa cho `30,60,50,70`, không tăng.
10. Tại mỗi nút, phát `key` đúng `count` lần. Dãy đầy đủ: `10,10,20,20,20,30`.
11. `35,40,45,50,55,60,70`. Khoảng **nửa mở** `[35,75)` có điều kiện `key < 75` nên loại `75`.
12. Định vị `lower_bound(55)` trong `O(h)` rồi phát `55,60,70` bằng iterator in-order. Tổng khoảng `O(h+3)`, không cần duyệt các khóa nhỏ hơn `55`.
13. Mỗi lần tìm successor từ gốc có thể `O(h)`, lặp `n` lần có thể `O(nh)`. Một iterator dùng lại stack chỉ mất `O(n)` cho cả lượt duyệt.
14. Morris tạo các **liên kết phải tạm** từ nút phải nhất của cây con trái về tổ tiên để quay lại mà không cần stack. Nếu dừng hoặc có ngoại lệ trước khi khôi phục hết, cấu trúc có thể còn các liên kết tạm và bị hỏng cho các thao tác khác.

</details>

## Ghi nhớ

**Duyệt giữa (in-order) là Trái → Nút → Phải.** Trên một **BST hợp lệ với khóa duy nhất**, phép duyệt này tạo dãy khóa **tăng nghiêm ngặt** vì mọi khóa ở cây con trái nhỏ hơn khóa nút và mọi khóa ở cây con phải lớn hơn. Có thể triển khai bằng **đệ quy**, **stack tường minh** hoặc **generator**; cả ba duyệt hết cây trong **`O(n)` thời gian**, dùng **`O(h)` bộ nhớ phụ** nếu không tính đầu ra. Khi chỉ cần một khoảng nhỏ, hãy kết hợp **lower bound + in-order iterator** để đạt khoảng **`O(h+k)`** cho `k` khóa; muốn duyệt giảm dần thì đảo thành **Phải → Nút → Trái**. Dãy in-order tăng là kiểm tra hữu ích cho **thứ tự BST**, nhưng không thay thế kiểm thử liên kết cha, chu trình hoặc metadata khác.

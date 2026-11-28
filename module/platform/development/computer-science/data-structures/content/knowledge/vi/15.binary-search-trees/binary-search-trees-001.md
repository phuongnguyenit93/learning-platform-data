# Bất biến BST trên toàn bộ cây con trái và phải

Một **cây tìm kiếm nhị phân** (*Binary Search Tree – BST*) có thể giúp tra cứu mã sản phẩm, lưu các khóa đã sắp theo thứ tự, hoặc tìm phần tử nhỏ nhất lớn hơn một ngưỡng. Điều làm BST khác một cây nhị phân bất kỳ không phải hình dáng cây, mà là **bất biến thứ tự** phải đúng tại **mọi nút và toàn bộ cây con của nút đó**.

Ví dụ, nút gốc có khóa `20`, nút con trái có khóa `10`, và một nút sâu hơn nằm trong cây con trái lại có khóa `24`. Mặc dù `24 > 10` có thể hợp lệ khi nhìn riêng quan hệ cha–con, cây **không phải BST hợp lệ**, vì `24` vẫn thuộc cây con trái của `20` nhưng lại lớn hơn `20`.

Bài học thuộc chương **Cây tìm kiếm nhị phân** trong module cấu trúc dữ liệu. Ta sẽ phát biểu chính xác bất biến, nhận diện cây sai, giải thích tại sao tìm kiếm/chèn dựa được vào bất biến ấy, xây thuật toán kiểm tra toàn cây và liên hệ chiều cao cây với chi phí thời gian, bộ nhớ.

## 1. BST là gì, và ta chọn quy ước nào?

**Cây nhị phân** là cấu trúc mỗi nút có tối đa hai con: `left` và `right`. Cây nhị phân **không mặc nhiên** là cây tìm kiếm nhị phân.

Một **BST** bổ sung quy tắc so sánh khóa. Trước hết, ta chọn quy ước thông dụng: **khóa là duy nhất**, có thứ tự toàn phần nhất quán, và:

1. Mọi khóa trong **toàn bộ cây con trái** của nút `x` đều **nhỏ hơn** `x.key`.
2. Mọi khóa trong **toàn bộ cây con phải** của nút `x` đều **lớn hơn** `x.key`.
3. Chính cây con trái và cây con phải cũng phải là các BST hợp lệ.

Có thể viết:

```text
BST(node):
    node == None
    hoặc
    (
        mọi k thuộc left(node):  k < node.key
        và mọi k thuộc right(node): k > node.key
        và BST(left(node))
        và BST(right(node))
    )
```

Với quy ước này, **hai nút có khóa bằng nhau không được tồn tại đồng thời**. Nếu BST biểu diễn một **map**, chèn lại cùng khóa thường **cập nhật giá trị** của nút cũ; nếu biểu diễn một **set**, chèn lại không làm tăng số phần tử.

### Ví dụ BST hợp lệ

```text
                  20
                /    \
              10      30
             /  \    /  \
            5   15  25   40
               /  \  /
              12  17 22
```

Kiểm tra tại gốc `20`:

- **Tất cả** `5, 10, 12, 15, 17` đều nhỏ hơn `20`.
- **Tất cả** `22, 25, 30, 40` đều lớn hơn `20`.

Kiểm tra tiếp tại `10`: mọi phần tử ở bên trái (`5`) nhỏ hơn `10`, còn các phần tử trong cây con phải (`12, 15, 17`) đều lớn hơn `10` **và vẫn nhỏ hơn tổ tiên `20`**.

Tại nút `25`, khóa `22` thuộc cây con trái của `25` nên `22 < 25`; đồng thời nó thuộc cây con phải của `20` nên `22 > 20`. Như vậy, một khóa có thể phải tuân theo **nhiều giới hạn cùng lúc**.

## 2. “Nhỏ hơn/lớn hơn” áp dụng cho toàn bộ cây con, không chỉ con trực tiếp

Đây là phân biệt quan trọng nhất trong bài.

Xét cây sau:

```text
          20
         /  \
       10    30
         \
          24    ← Sai: 24 nằm trong cây con trái của 20
```

Nếu chỉ kiểm tra các cạnh cha–con:

- `10 < 20`: đúng.
- `30 > 20`: đúng.
- `24 > 10`: đúng.

Nhưng kiểm tra BST **toàn cục** cho thấy `24` phải nhỏ hơn `20` vì nằm **bên trái gốc `20`**, trong khi thực tế `24 > 20`. Vì vậy cây **không hợp lệ**.

Một cây sai theo hướng ngược lại:

```text
          20
         /  \
       10    30
            /
           14    ← Sai: 14 nằm trong cây con phải của 20
```

Mọi cạnh cha–con vẫn có chiều so sánh “đúng”: `14 < 30`. Nhưng `14` nằm trong cây con phải của `20` nên phải **lớn hơn `20`**; điều đó không đúng.

**Kết luận:** điều kiện “con trái < cha < con phải” tại từng nút là **điều kiện cần, nhưng chưa đủ** cho BST. Phải kiểm tra **tất cả hậu duệ**, thường bằng cách truyền các giới hạn từ tổ tiên xuống.

### Tại sao lỗi này gây tìm kiếm sai?

Giả sử tìm khóa `24` trong cây sai đầu tiên:

1. So sánh `24` với gốc `20`; vì `24 > 20`, thuật toán đi **sang phải**.
2. Gặp nút `30`; vì `24 < 30`, thuật toán đi **sang trái**.
3. Không có nút nào; thuật toán kết luận `24` không tồn tại.

Trong thực tế `24` lại nằm ở **nhánh trái** của gốc. Thuật toán tìm kiếm chuẩn không duyệt nhánh ấy vì đang tin vào bất biến BST. **Một vi phạm ở hậu duệ có thể làm tìm kiếm trả kết quả sai** dù giá trị thực sự có mặt trong cây.

## 3. Phát biểu bằng khoảng giới hạn từ tổ tiên

Thay vì kiểm tra mọi phần tử của từng cây con bằng nhiều vòng duyệt lồng nhau, ta có thể duy trì **khoảng giá trị cho phép** ở mỗi nút.

Với khóa duy nhất và thứ tự số học, mỗi nút phải nằm trong khoảng mở:

```text
lower < node.key < upper
```

Hai biên `lower` và `upper` được xác định bởi những tổ tiên đã đi qua:

- Đi xuống **cây con trái** của nút có khóa `k`: cập nhật **biên trên** thành `k`.
- Đi xuống **cây con phải** của nút có khóa `k`: cập nhật **biên dưới** thành `k`.
- Biên còn lại kế thừa từ tổ tiên; **không được quên** nó.

Với cây mẫu hợp lệ:

```text
                 20          (-∞, +∞)
                /  \
       10 (-∞,20)  30 (20,+∞)
           /   \      /
        5       15   25
    (-∞,10)  (10,20) (20,30)
              /       /
            12       22
          (10,15)   (20,25)
```

Bảng giới hạn ở một số vị trí:

| Vị trí | Biên dưới | Biên trên | Khóa hợp lệ tại đó |
| --- | --- | --- | --- |
| Gốc | Không có | Không có | Bất kỳ khóa thuộc miền hợp lệ |
| Con trái của `20` | Không có | `20` | Nhỏ hơn `20` |
| Con phải của `20` | `20` | Không có | Lớn hơn `20` |
| Con phải của `10` khi `10` nằm bên trái `20` | `10` | `20` | `10 < k < 20` |
| Con trái của `25` khi `25` thuộc nhánh phải `20` | `20` | `25` | `20 < k < 25` |

Điều này giải thích ngay vì sao `24` ở con phải của `10` trong cây đầu tiên là sai: tại vị trí đó, khóa chỉ được phép nằm trong `(10,20)`.

### Bất biến được truyền xuống theo đường đi

Nếu đã đến nút `x` cùng khoảng `(low, high)`, điều kiện đúng là:

```text
low < x.key < high

đệ quy/duyệt trái:  (low, x.key)
đệ quy/duyệt phải: (x.key, high)
```

Khi các biên không tồn tại ở phía ngoài cùng của cây, ta có thể dùng **trạng thái không giới hạn**, thay vì tự đặt một số nguyên “rất nhỏ” hoặc “rất lớn”. Làm vậy giúp kiểm tra đúng cả với những khóa số âm, số cực đại hoặc kiểu khóa khác số.

## 4. Chứng minh ngắn gọn bằng quy nạp trên cây

Ta muốn lý giải vì sao điều kiện giới hạn đảm bảo bất biến trên **toàn bộ cây con**.

**Cơ sở:** cây rỗng không chứa nút vi phạm nên được coi là BST hợp lệ.

**Bước quy nạp:** giả sử tại nút `x`, ta kiểm tra `low < x.key < high`. Khi duyệt toàn bộ cây con trái với biên trên mới là `x.key`, mọi nút trái được kiểm tra phải nhỏ hơn `x.key`; đồng thời mỗi nút vẫn thỏa biên dưới kế thừa. Tương tự, khi duyệt cây con phải với biên dưới là `x.key`, mọi nút phải lớn hơn `x.key` và không vượt quá biên trên kế thừa.

Nếu hai cây con đều được xác nhận đúng theo các khoảng mới, cả cây gốc tại `x` thỏa bất biến BST. Lặp lập luận tới các nút lá sẽ kiểm tra được **toàn bộ cây**, không chỉ những cặp cha–con.

Một cách nhìn tương đương: **mỗi lần rẽ trái/phải đặt thêm một điều kiện**, và tất cả điều kiện đó tiếp tục có hiệu lực ở mọi nút phía dưới.

## 5. Chính xác hóa quy tắc khóa trùng và bộ so sánh

Trong bài này, ta dùng **BST không có khóa trùng**, vì vậy quan hệ tại cây con là **nghiêm ngặt**:

```text
mọi khóa trái < khóa nút < mọi khóa phải
```

Nhưng các ứng dụng khác có thể cần nhiều bản ghi có cùng giá trị. Có ba chính sách thường gặp:

| Chính sách | Cách xử lý khi bằng khóa hiện có | Ảnh hưởng tới bất biến |
| --- | --- | --- |
| **Set / map khóa duy nhất** | Không thêm nút; map có thể cập nhật giá trị | Dùng `left < key < right` |
| **Đếm số lần xuất hiện ở một nút** | Tăng bộ đếm `count` | Cây vẫn có một nút cho mỗi khóa phân biệt |
| **Cho phép nút trùng** | Chèn theo quy tắc nhất quán vào một phía | Phải đổi bất biến và cách kiểm tra biên cho phù hợp |

Nếu chọn “khóa bằng nút hiện tại thì đi sang phải”, quy tắc có thể là **trái < nút ≤ phải** cho BST chưa cân bằng. Tuy nhiên, phép **quay cây** ở các cấu trúc cân bằng có thể làm các nút có khóa bằng nhau nằm ở phía khác. Bởi vậy, trong nhiều ứng dụng cần trùng, **đếm số lần ở mỗi nút** hoặc dùng khóa ghép phân biệt thường dễ giữ bất biến hơn.

### Khóa và giá trị là hai thứ khác nhau

Một nút của **tree map** có thể lưu:

```text
(key="HV01", value=8.0)
```

Thứ tự BST xét theo **key** (ví dụ mã học viên), không theo điểm `value`. Khi cập nhật điểm từ `8.0` lên `9.5` mà khóa giữ nguyên, không cần di chuyển nút trong cây. Nhưng nếu đổi **khóa**, vị trí hiện tại có thể không còn thỏa BST; thông thường phải xóa mục cũ rồi chèn lại khóa mới.

### Bộ so sánh phải ổn định

Khóa không nhất thiết là số nguyên: nó có thể là chuỗi, tuple hoặc đối tượng với bộ so sánh nhất quán. Cần xác định quan hệ tương đương khóa bằng chính quy tắc so sánh dùng để tìm/chèn:

- Nếu `compare(a,b) < 0`, `a` đứng trước `b`.
- Nếu `compare(a,b) > 0`, `a` đứng sau `b`.
- Nếu `compare(a,b) == 0`, hai khóa thường được coi là **tương đương** trong tree map/set.

Bộ so sánh không nhất quán, trường khóa bị thay đổi sau chèn, hoặc phép so sánh không phù hợp (ví dụ giá trị `NaN` với các quy tắc so sánh số thực thông thường) có thể phá bất biến. Khi cài thủ công cần kiểm tra **quy tắc thứ tự** ngay từ đầu, không chỉ so sánh hình thức khi in dữ liệu.

## 6. Thuật toán kiểm tra sai: chỉ nhìn nút con trực tiếp

Đoạn mã sau minh họa **một cách làm không đủ**:

```python
def local_children_only(node):
    if node is None:
        return True

    if node.left is not None and node.left.key >= node.key:
        return False
    if node.right is not None and node.right.key <= node.key:
        return False

    return (
        local_children_only(node.left)
        and local_children_only(node.right)
    )
```

Nó kiểm tra mỗi quan hệ trực tiếp `left.key < node.key < right.key`, nhưng **không kiểm tra hậu duệ với tổ tiên xa hơn**.

Ví dụ mã sau tạo một cây có `24` sai vị trí, nhưng thuật toán kiểm tra nông có thể trả `True`:

```python
from dataclasses import dataclass

@dataclass
class Node:
    key: int
    left: "Node | None" = None
    right: "Node | None" = None

bad = Node(
    20,
    left=Node(10, right=Node(24)),
    right=Node(30),
)

assert local_children_only(bad) is True  # Kết luận SAI!
```

Vì sao xảy ra lỗi? Khi kiểm tra nút `10`, thuật toán chỉ biết `24 > 10`. Nó đã **quên giới hạn `24 < 20`** vốn được đặt ra bởi tổ tiên `20`.

Một thuật toán xác minh BST đúng cần:

- Xét mọi phần tử của cây con với khóa nút hiện tại, **hoặc**
- Truyền khoảng biên từ tổ tiên xuống, **hoặc**
- Kiểm tra tính tăng nghiêm ngặt của toàn bộ phép duyệt trung thứ tự.

Cách truyền biên thường rõ ràng và làm việc trong `O(n)` thời gian.

## 7. Kiểm tra toàn BST bằng biên dưới và biên trên

Giả sử cây chỉ có **khóa số nguyên Python**, không cho khóa `None` và không có bản sao bằng nhau. Hàm sau dùng `None` để biểu diễn **không có giới hạn**; nó không dùng `None` làm khóa thực.

### Phiên bản đệ quy

```python
def is_bst_recursive(node, low=None, high=None):
    if node is None:
        return True

    if low is not None and node.key <= low:
        return False
    if high is not None and node.key >= high:
        return False

    return (
        is_bst_recursive(node.left, low, node.key)
        and is_bst_recursive(node.right, node.key, high)
    )
```

Cách đọc:

- `node.key <= low` là sai vì khóa phải **lớn hơn nghiêm ngặt** biên dưới.
- `node.key >= high` là sai vì khóa phải **nhỏ hơn nghiêm ngặt** biên trên.
- Nhánh trái nhận `high = node.key`, nhánh phải nhận `low = node.key`.
- Nếu gặp một nút sai, hàm trả `False`; nếu tất cả đều hợp lệ, trả `True`.

Dùng với lớp `Node` đã định nghĩa:

```python
good = Node(
    20,
    left=Node(10, left=Node(5), right=Node(15)),
    right=Node(30, left=Node(25), right=Node(40)),
)

assert is_bst_recursive(good) is True
assert is_bst_recursive(bad) is False
assert is_bst_recursive(None) is True
assert is_bst_recursive(Node(7)) is True

duplicate = Node(20, left=Node(20))
assert is_bst_recursive(duplicate) is False
```

**Không nên dùng một giá trị số cố định** như `-10**9` làm biên dưới cho mọi cây nếu khóa có thể nhỏ hơn giá trị đó. `None` ở đây có ý nghĩa **không giới hạn**, không phải số. Với khóa kiểu khác hoặc chính `None` có thể là khóa, phải dùng sentinel riêng hoặc một biểu diễn giới hạn có nhãn.

### Phiên bản lặp với stack tường minh

Đệ quy dễ đọc, nhưng cây lệch rất sâu có thể vượt giới hạn đệ quy của Python. Cách dưới đây lưu `(node, low, high)` trên stack, tránh dựa vào call stack của ngôn ngữ:

```python
def is_bst_iterative(root):
    pending = [(root, None, None)]

    while pending:
        node, low, high = pending.pop()
        if node is None:
            continue

        if low is not None and node.key <= low:
            return False
        if high is not None and node.key >= high:
            return False

        pending.append((node.right, node.key, high))
        pending.append((node.left, low, node.key))

    return True


assert is_bst_iterative(good)
assert not is_bst_iterative(bad)
assert is_bst_iterative(None)
assert not is_bst_iterative(duplicate)
```

Hai phiên bản kiểm tra cùng một bất biến và cho cùng kết quả với **cây hữu hạn, không có chu trình** và phép so sánh khóa hợp lệ. Thuật toán này không tự nhận diện chu trình hoặc nút được dùng chung giữa nhiều đường đi; các hiện tượng đó vi phạm giả định đầu vào là cấu trúc cây thông thường. Nếu phải kiểm tra một đồ thị đối tượng không tin cậy, cần xử lý cả tính hợp lệ cấu trúc riêng.

### Phân tích chi phí kiểm tra

Với `n` nút và chiều cao `h`:

- **Thời gian:** `O(n)` trong trường hợp phải duyệt hết cây; mỗi nút được xử lý một lần, với số phép so sánh hằng số.
- **Bộ nhớ phụ:** `O(h)` cho đệ quy hoặc stack DFS tường minh trên một cây; ở cây lệch, `h = O(n)`.
- **Dừng sớm:** nếu phát hiện vi phạm, hàm có thể trả `False` trước khi đi hết `n` nút.

So sánh khóa dài hoặc bộ so sánh phức tạp có thể làm mỗi lần kiểm tra đắt hơn đơn vị hằng số. Chi phí `O(n)` ở đây giả định phép so sánh khóa mất `O(1)`.

## 8. Cách kiểm tra tương đương: duyệt trung thứ tự tăng nghiêm ngặt

BST có khóa duy nhất có một tính chất hữu ích:

> Khi **duyệt trung thứ tự** (*in-order*: trái → nút → phải), các khóa phải xuất hiện theo **thứ tự tăng nghiêm ngặt**.

Với cây hợp lệ ở đầu bài:

```text
5, 10, 12, 15, 17, 20, 22, 25, 30, 40
```

Đó là một dãy tăng nghiêm ngặt.

Ngược lại, cây sai có `24` trong cây con trái `20` sẽ cho một đoạn duyệt giống:

```text
10, 24, 20, 30
        ↑
      24 > 20: thứ tự giảm, cây không hợp lệ
```

### Cài đặt kiểm tra in-order không cần tạo toàn bộ list

```python
def is_bst_inorder(root):
    stack = []
    node = root
    has_previous = False
    previous = None

    while stack or node is not None:
        while node is not None:
            stack.append(node)
            node = node.left

        node = stack.pop()

        if has_previous and node.key <= previous:
            return False

        previous = node.key
        has_previous = True
        node = node.right

    return True


assert is_bst_inorder(good)
assert not is_bst_inorder(bad)
assert not is_bst_inorder(duplicate)
```

Biến `has_previous` giúp tránh dùng `None` làm giá trị so sánh lần đầu. Đoạn mã giả định các khóa so sánh được bằng `<=` và cây đúng cấu trúc.

**Thời gian:** `O(n)`; **bộ nhớ phụ:** `O(h)` cho stack duyệt. Nếu tạo toàn bộ list rồi dùng `all(keys[i-1] < keys[i] ...)`, thời gian vẫn `O(n)` nhưng cần **`O(n)` bộ nhớ** để lưu danh sách khóa.

### Dùng kiểm tra theo biên hay theo in-order?

| Cách | Diễn đạt | Ưu điểm |
| --- | --- | --- |
| **Biên dưới/trên** | Mỗi khóa phải nằm trong khoảng do tổ tiên quy định | Phơi bày trực tiếp bất biến toàn cây con |
| **In-order tăng nghiêm ngặt** | Dãy khóa khi duyệt trung thứ tự phải tăng | Hữu ích để kiểm thử, liên hệ BST với thứ tự sắp xếp |
| **Chỉ xét con trực tiếp** | Nút trái nhỏ hơn cha, nút phải lớn hơn cha | **Không đủ**, dễ bỏ sót lỗi ở hậu duệ |

Trong bài học về bất biến, **kiểm tra theo biên** thường dễ lý giải nguyên nhân sai hơn: có thể báo rõ khóa nào đã vượt biên trên hay dưới của tổ tiên.

## 9. Vì sao tìm kiếm BST đúng khi bất biến được giữ?

Một phép tìm kiếm khóa `target` bắt đầu tại gốc:

1. Nếu `target == node.key`, đã tìm thấy.
2. Nếu `target < node.key`, chỉ cần đi **sang trái**: mọi khóa bên phải đều lớn hơn `node.key` nên không thể bằng `target`.
3. Nếu `target > node.key`, chỉ cần đi **sang phải**: mọi khóa bên trái đều nhỏ hơn `node.key` nên không thể bằng `target`.
4. Nếu đi đến vị trí rỗng, kết luận khóa không có mặt.

Giả mã:

```text
SEARCH(root, target):
    current = root
    while current != null:
        if target == current.key:
            return FOUND(current)
        if target < current.key:
            current = current.left
        else:
            current = current.right
    return NOT_FOUND
```

Ví dụ tìm `17` trên cây hợp lệ:

```text
20  →  10  →  15  →  17  (tìm thấy)
<       >       >
```

Các dấu so sánh mô tả `target` so với khóa ở nút hiện tại. Thuật toán không cần kiểm tra tất cả các nút vì **bất biến toàn bộ cây con** cho phép loại hẳn một nhánh sau mỗi lần so sánh.

### Mã Python

```python
def contains(root, target):
    current = root

    while current is not None:
        if target == current.key:
            return True
        if target < current.key:
            current = current.left
        else:
            current = current.right

    return False


assert contains(good, 15) is True
assert contains(good, 99) is False
assert contains(bad, 24) is False  # Kết quả sai về dữ liệu do cây không còn là BST
```

Câu khẳng định cuối cố tình áp dụng thuật toán cho **cây lỗi**: `bad` thật sự chứa `24`, nhưng `contains` không tìm thấy. Điều đó chứng minh **bất biến là điều kiện tiên quyết của tính đúng đắn tìm kiếm BST**.

## 10. Chèn khóa mà vẫn bảo toàn bất biến

Với cây có khóa duy nhất, thao tác chèn mới phải đi theo **cùng quyết định trái/phải như tìm kiếm**. Khi gặp chỗ rỗng, tạo nút tại đó.

```text
INSERT(root, target):
    nếu root rỗng: tạo nút target
    bắt đầu từ root:
        nếu target bằng khóa nút hiện tại:
            không tạo thêm nút  (hoặc cập nhật value trong tree map)
        nếu target nhỏ hơn:
            tiếp tục bên trái
        nếu target lớn hơn:
            tiếp tục bên phải
    tạo nút tại liên kết rỗng vừa gặp
```

**Vì sao đúng?** Dọc đường đi, ta liên tục thu hẹp khoảng cho phép. Khi đến liên kết rỗng, `target` đã thỏa mọi giới hạn từ các tổ tiên vì mỗi lần rẽ nhánh đều được chọn theo đúng so sánh khóa. Nút mới không có con nên không tạo thêm vi phạm ở bên dưới. Những nút cũ giữ nguyên vị trí.

### Ví dụ cài chèn đơn giản, không tự cân bằng

```python
def insert(root, key):
    """Trả (gốc mới, inserted); bỏ qua khóa đã tồn tại."""
    if root is None:
        return Node(key), True

    current = root
    while True:
        if key == current.key:
            return root, False

        if key < current.key:
            if current.left is None:
                current.left = Node(key)
                return root, True
            current = current.left
        else:
            if current.right is None:
                current.right = Node(key)
                return root, True
            current = current.right


root = None
for key in (20, 10, 30, 5, 15, 25, 40, 12, 17, 22):
    root, inserted = insert(root, key)
    assert inserted
    assert is_bst_iterative(root)

root, inserted = insert(root, 15)
assert inserted is False
assert is_bst_iterative(root)
assert contains(root, 22)
```

**Bất biến cần nhớ:** các đường dẫn tìm/chèn chỉ an toàn nếu cây **đã là BST hợp lệ trước thao tác**. Thuật toán chèn chuẩn không thể tự sửa một nút đã đặt sai ở phần khác của cây.

### Không được chèn trực tiếp vào vị trí tùy ý

Giả sử muốn thêm `12`. Gắn nó ngay dưới nút `30` bên trái vì `12 < 30` là **không đủ**; nút `30` thuộc cây con phải của `20`, nên mọi hậu duệ của `30` đều phải `> 20`. Đúng hơn, `12` phải đi qua nhánh trái của `20` và được đặt vào khoảng `(10,15)`.

## 11. Khi xóa hoặc quay cây, bất biến phải tiếp tục đúng

Xóa nút BST là thao tác dễ làm hỏng thứ tự hơn chèn, đặc biệt với nút có hai con.

- **Nút lá:** bỏ nút không làm thay đổi thứ tự của các khóa còn lại.
- **Nút có một con:** nối cha với cây con duy nhất, vì mọi khóa trong cây con đó vốn đã thỏa các giới hạn của nút bị xóa và các tổ tiên.
- **Nút có hai con:** thường chọn **phần tử kế tiếp theo thứ tự** (*in-order successor*: nhỏ nhất trong cây con phải) hoặc **phần tử trước theo thứ tự** (*predecessor*: lớn nhất trong cây con trái) làm khóa thay thế; sau đó xóa nút thay thế ở vị trí cũ.

Ví dụ:

```text
       20
      /  \
    10    30
         /  \
       25    40

Xóa 20 bằng successor 25:

       25
      /  \
    10    30
            \
             40
```

Nút thay thế `25` lớn hơn mọi khóa trong cây con trái của `20` và không lớn hơn khóa đầu tiên của phần còn lại bên phải; với khóa duy nhất, ta có thể duy trì bất biến bằng cách xử lý đúng vị trí cũ của `25`.

**Cây tự cân bằng** (như AVL hoặc cây đỏ–đen) có thể thực hiện phép **quay trái/phải** sau chèn hoặc xóa. Một phép quay đúng giữ nguyên thứ tự in-order của các khóa, do đó vẫn giữ bất biến BST, trong khi thay đổi hình dáng/chiều cao cây. Nếu tự viết phép quay, cần nối lại đúng các cây con, không chỉ hoán đổi hai khóa.

## 12. Độ phức tạp: vai trò của chiều cao cây

Gọi:

- `n`: số nút trong cây.
- `h`: số nút trên đường dài nhất từ gốc đến một lá; cây rỗng có `h = 0`.

Tìm kiếm, chèn và xóa trong BST thường chỉ đi theo một đường từ gốc xuống, nên có chi phí `O(h)` với phép so sánh khóa hằng số.

| Trường hợp | Chiều cao `h` | Tìm / chèn / xóa điển hình |
| --- | --- | --- |
| **Cây cân đối** | `O(log n)` | `O(log n)` |
| **BST thông thường bị lệch** | `O(n)` | `O(n)` |
| **Cây tìm kiếm tự cân bằng** | Bảo đảm `O(log n)` | Bảo đảm `O(log n)` |
| **Kiểm tra toàn cây** | Không chỉ theo một đường | `O(n)` |

BST thông thường **không tự bảo đảm cân bằng**. Ví dụ chèn khóa tăng dần:

```text
Chèn: 1, 2, 3, 4, 5

1
 \
  2
   \
    3
     \
      4
       \
        5
```

Đường đến `5` có năm nút, tức `h = n`. Dù BST này **đúng về thứ tự**, tìm kiếm vẫn có thể `O(n)`.

Phân biệt rõ:

- **BST hợp lệ**: thỏa quy tắc toàn bộ cây con.
- **BST cân bằng**: bổ sung điều kiện để chiều cao không quá lớn.

Một cây có thể **hợp lệ nhưng lệch hoàn toàn**, hoặc **trông cân đối nhưng sai quy tắc BST**. Hình dáng không thay thế việc kiểm tra bất biến.

### Bộ nhớ của thuật toán

- Tìm kiếm/chèn **lặp** có thể dùng `O(1)` bộ nhớ phụ ngoài nút mới (nếu không lưu đường đi).
- Tìm kiếm/chèn **đệ quy** dùng `O(h)` ngăn xếp lời gọi.
- Kiểm tra toàn cây bằng DFS với biên dùng `O(h)` bộ nhớ phụ.
- Duyệt in-order và thu tất cả khóa vào list dùng thêm `O(n)` bộ nhớ cho kết quả; chỉ duyệt phát từng khóa có thể dùng `O(h)` cho ngăn xếp.
- Bản thân cây lưu `O(n)` nút, mỗi nút có các tham chiếu con và thông tin khóa/giá trị.

## 13. So sánh BST với những cấu trúc khác

BST là một phương án hiện thực **set/map có thứ tự**, không phải câu trả lời duy nhất cho mọi thao tác.

| Cấu trúc | Điều được bảo đảm | Tìm một khóa | Duyệt khóa tăng dần |
| --- | --- | --- | --- |
| Mảng chưa sắp | Chỉ lưu các phần tử/cặp | `O(n)` nếu tìm tuyến tính | Phải sắp xếp khi cần |
| Mảng đã sắp | Mọi khóa đã có thứ tự | `O(log n)` tìm nhị phân | `O(n)` |
| Hash map / hash set | Dựa trên băm và phép bằng nhau | Trung bình `O(1)` với giả định hash phù hợp | Không mặc định được sắp |
| BST chưa tự cân bằng | Thứ tự toàn cây con | `O(h)`, xấu nhất `O(n)` | `O(n)` bằng in-order |
| BST tự cân bằng | Thứ tự toàn cây con và giới hạn chiều cao | `O(log n)` | `O(n)` bằng in-order |

Một hash map có thể nhanh hơn để tra cứu **mã chính xác** nhưng không hỗ trợ trực tiếp việc tìm **khóa nhỏ nhất ≥ k** hoặc duyệt khoảng khóa theo thứ tự. Với BST cân bằng, những thao tác có thứ tự này là lợi thế lớn; việc tìm điểm bắt đầu có thể `O(log n)`, sau đó liệt kê `m` khóa tiếp theo trong `O(m)` theo cách duyệt phù hợp.

BST cũng **khác heap**: heap chỉ yêu cầu khóa ở mỗi nút có quan hệ ưu tiên với **con trực tiếp** theo bất biến heap; nó không yêu cầu tất cả phần tử ở cây con trái nhỏ hơn khóa gốc và tất cả phần tử bên phải lớn hơn. Vì vậy không được dùng quy tắc tìm kiếm BST trên một heap.

## 14. Các trường hợp biên và sai lầm thường gặp

1. **Chỉ so sánh cha với hai con:** bỏ sót nút vi phạm giới hạn của tổ tiên sâu hơn.
2. **Hiểu “cây con trái nhỏ hơn” là “chỉ nút con trái nhỏ hơn”:** bất biến phải đúng cho mọi nút hậu duệ.
3. **Quên biên khi đệ quy:** nhánh con phải của một nút trong cây con trái của gốc vẫn phải nhỏ hơn gốc.
4. **Dùng `<=` và `>=` không nhất quán:** nếu chọn BST khóa duy nhất, các biên phải nghiêm ngặt; chính sách khóa trùng phải được định nghĩa trước.
5. **Dùng một số làm biên vô hạn:** khóa thực tế có thể nằm ngoài khoảng số giả định.
6. **So sánh khóa bằng quy tắc khác nhau giữa tìm, chèn và kiểm tra:** có thể tạo cấu trúc không nhất quán.
7. **Thay đổi khóa của nút tại chỗ:** vị trí nút có thể không còn thỏa biên từ tổ tiên; muốn đổi khóa, thường xóa rồi chèn lại.
8. **Cho rằng cây cân đối thì chắc chắn là BST:** cân đối là điều kiện chiều cao, không phải điều kiện thứ tự.
9. **Cho rằng BST nào cũng tìm `O(log n)`:** BST lệch có chiều cao `O(n)`; cần cân bằng để bảo đảm chi phí logarit.
10. **Nhầm giá trị dữ liệu với khóa sắp xếp:** tree map sắp theo `key`; cập nhật `value` không tự thay thứ tự.
11. **Duyệt in-order rồi kiểm tra “không giảm” khi cấm khóa trùng:** phải kiểm tra **tăng nghiêm ngặt**.
12. **Dùng đệ quy trên cây cực sâu mà không xét giới hạn môi trường:** thuật toán đúng về logic vẫn có thể vượt độ sâu ngăn xếp lời gọi.
13. **Nhầm một cấu trúc có liên kết vòng với cây:** các thuật toán BST chuẩn giả định cây hữu hạn, không có chu trình và một đường từ gốc đến mỗi nút.
14. **Thử tìm kiếm trên cây đã hỏng rồi tin kết quả:** BST search chỉ đúng khi bất biến được giữ trước và sau mọi thay đổi.

## 15. Tự luyện tập

**Bài 1.** Cây sau có phải BST hợp lệ không? Giải thích bằng giới hạn tổ tiên:

```text
       18
      /  \
    10    25
      \
       21
```

**Bài 2.** Xét cây:

```text
       18
      /  \
    10    25
          /
         15
```

Bất biến bị vi phạm ở đâu, dù mọi cặp cha–con có chiều so sánh đúng?

**Bài 3.** Với đường đi gốc `50` → trái `20` → phải `35` → trái, khóa mới ở vị trí cuối phải nằm trong khoảng nào? Chọn `30`, `36` hoặc `70` để chèn tại vị trí ấy.

**Bài 4.** Viết hàm `is_bst(root)` dùng biên dưới và trên để kiểm tra BST khóa nguyên không trùng. Nêu chi phí thời gian và bộ nhớ phụ.

**Bài 5.** Vì sao dãy in-order `[3, 5, 7, 10, 12]` phù hợp với BST khóa duy nhất? Dãy `[3, 7, 5, 10]` cho thấy điều gì?

**Bài 6.** Với cây BST hợp lệ:

```text
       20
      /  \
    10    30
         /  \
       25    40
```

Hãy mô tả đường đi để tìm `25` và số lần so sánh tại các nút.

**Bài 7.** Nếu chèn lần lượt `1, 2, 3, 4, 5, 6` vào BST thường, chiều cao có thể là bao nhiêu? Tìm kiếm có còn được bảo đảm `O(log n)` không?

**Bài 8.** Một tree map lưu khóa `"HV01"` với giá trị `8.0`. Khi điểm đổi thành `9.0`, có cần đổi vị trí nút không? Nếu mã khóa đổi thành `"HV99"` thì sao?

**Bài 9.** Một hệ thống muốn lưu cả số lần một mã xuất hiện, nhưng vẫn duy trì BST khóa duy nhất. Hãy đề xuất cấu trúc nút và hành vi khi chèn lại mã cũ.

**Bài 10.** So sánh cây sau với bất biến của **min-heap**, giải thích tại sao nó không nhất thiết là BST:

```text
       1
      / \
     3   2
    / \
   5   4
```

<details>
<summary>Đáp án và gợi ý</summary>

1. **Không hợp lệ.** `21` nằm trong cây con trái của `18` nhưng `21 > 18`. Quan hệ `21 > 10` không đủ để hợp thức hóa vị trí đó.
2. **Không hợp lệ.** `15` thuộc cây con phải của `18` nên phải `> 18`; việc `15 < 25` chỉ là điều kiện cục bộ.
3. Khoảng phải là `(20,35)`: từ gốc rẽ trái được `< 50`, từ `20` rẽ phải được `> 20`, từ `35` rẽ trái được `< 35`. `30` phù hợp; `36` và `70` không phù hợp.
4. Duyệt với `(node, low, high)`; kiểm tra `low < key < high`; trái nhận `(low, key)`, phải nhận `(key, high)`. Thời gian `O(n)`, bộ nhớ DFS `O(h)` trong trường hợp xấu nhất.
5. Dãy đầu **tăng nghiêm ngặt**, phù hợp với điều kiện cần và đủ của phép duyệt trung thứ tự trên cây nhị phân có khóa duy nhất. Dãy thứ hai giảm từ `7` xuống `5` nên không thể là in-order của BST hợp lệ theo cùng quy tắc.
6. Đi `20` → phải `30` → trái `25`; tìm thấy sau ba phép so sánh với khóa nút.
7. Có thể hình thành chuỗi lệch phải gồm sáu nút, `h = 6` nếu đếm số nút trên đường sâu nhất; tìm kiếm có thể `O(n)`, không bảo đảm logarit.
8. Đổi `value` nhưng giữ `key` thì không cần di chuyển. Đổi `key` có thể phá thứ tự, nên thường xóa mục cũ rồi chèn mục mới theo khóa mới.
9. Mỗi nút lưu `(key, count, left, right)`. Khi chèn khóa đã có thì tăng `count`, không thêm nút mới; thứ tự nghiêm ngặt giữa các nút vẫn được giữ.
10. Cây thỏa tính chất min-heap cục bộ: khóa của cha không lớn hơn con. Nhưng cây con trái của gốc `1` chứa `3` và `5` lớn hơn `1`, trái với yêu cầu BST rằng mọi khóa ở trái gốc phải **nhỏ hơn** gốc.

</details>

## Ghi nhớ

**Bất biến BST là bất biến trên toàn bộ cây con:** với mỗi nút, **mọi khóa bên trái nhỏ hơn khóa nút, mọi khóa bên phải lớn hơn khóa nút, và hai cây con tiếp tục tuân thủ cùng quy tắc**. Chỉ so sánh cha với hai con trực tiếp là chưa đủ; phải kế thừa **biên dưới và biên trên từ tất cả tổ tiên**. Từ bất biến ấy mới suy ra tính đúng của tìm kiếm, chèn, xóa và duyệt in-order tăng nghiêm ngặt. **BST hợp lệ không đồng nghĩa BST cân bằng**: các thao tác theo một đường đi tốn `O(h)`, có thể là `O(log n)` khi cân bằng hoặc `O(n)` khi lệch.

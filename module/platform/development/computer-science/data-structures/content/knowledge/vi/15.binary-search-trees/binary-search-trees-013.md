# Kiểm tra BST bằng miền khóa hợp lệ thay vì chỉ so sánh con trực tiếp

Khi học **cây tìm kiếm nhị phân** (*Binary Search Tree – BST*), ta thường nhớ quy tắc: “Con trái nhỏ hơn cha, con phải lớn hơn cha.” Quy tắc này đúng nhưng **chưa đủ để xác minh cả cây**. Một nút có thể nhỏ hơn cha trực tiếp của nó, nhưng vẫn nằm sai phía so với **ông, bà hoặc một tổ tiên xa hơn**. Chương trình chỉ so khóa của cha với hai con trực tiếp sẽ không phát hiện được lỗi ấy.

Cách kiểm tra đáng tin cậy là theo dõi **miền khóa hợp lệ** cho từng nút. Khi đi vào cây con trái của nút có khóa `k`, ta biết mọi hậu duệ trong đó phải **nhỏ hơn `k`**. Khi đi vào cây con phải, mọi hậu duệ phải **lớn hơn `k`**. Các giới hạn từ những tổ tiên trước đó không mất đi: chúng được mang xuống và **thu hẹp dần** trên mỗi nhánh.

Bài thuộc chương **Cây tìm kiếm nhị phân** của module cấu trúc dữ liệu. Ta sẽ phân biệt bất biến **toàn cây con** với kiểm tra **con trực tiếp**, xây thuật toán kiểm tra bằng khoảng `(low, high)`, chứng minh tính đúng, cài đặt Python bằng đệ quy và stack, xử lý khóa trùng/comparator, phân tích `O(n)` thời gian – `O(h)` bộ nhớ phụ, rồi tự luyện qua các ca hợp lệ và phản ví dụ.

## 1. Phát biểu chính xác bất biến BST

Trong bài này, trước tiên xét BST có **khóa phân biệt** và dùng một **thứ tự nghiêm ngặt, nhất quán** trên các khóa.

Với mỗi nút `x` có khóa `k`, bất biến yêu cầu:

1. **Mọi** khóa trong **toàn bộ cây con trái** của `x` nhỏ hơn `k`.
2. **Mọi** khóa trong **toàn bộ cây con phải** của `x` lớn hơn `k`.
3. Các cây con trái và phải cũng phải thỏa chính bất biến này.

Có thể diễn đạt bằng tập khóa:

```text
Mọi a thuộc keys(x.left):  a < x.key
Mọi b thuộc keys(x.right): b > x.key
```

Điểm quan trọng là chữ **mọi**: không chỉ `x.left.key` hay `x.right.key`, mà là **tất cả hậu duệ** nằm dưới hai liên kết ấy.

### Cây hợp lệ

```text
                   50
                 /    \
               30      70
              /  \    /  \
            20   40  60   80
```

Tại gốc `50`:

- Cả `20, 30, 40` đều nhỏ hơn `50`.
- Cả `60, 70, 80` đều lớn hơn `50`.

Tại nút `30`, khóa `20 < 30 < 40`; tại `70`, khóa `60 < 70 < 80`. Không có hậu duệ nào vi phạm giới hạn của **bất kỳ tổ tiên** nào.

### Bất biến và hiệu năng là hai vấn đề khác nhau

Cây một nhánh như `10 → phải 20 → phải 30` vẫn hợp lệ theo BST, dù nó có thể có chiều cao `h=n` và tìm kiếm kém hiệu quả. Thuật toán trong bài **kiểm tra tính đúng của thứ tự**, không kiểm tra cây có cân bằng AVL/đỏ–đen hay không.

## 2. Phản ví dụ: tất cả quan hệ cha–con đều đúng, cả cây vẫn sai

Xét cây sau:

```text
                   50
                 /    \
               30      70
                 \
                  60    ← Sai vị trí trong BST
```

Nếu chỉ so các **cặp trực tiếp**, tất cả đều có vẻ đúng:

- `30 < 50`: con trái của `50` nhỏ hơn `50`.
- `70 > 50`: con phải của `50` lớn hơn `50`.
- `60 > 30`: con phải của `30` lớn hơn `30`.

Nhưng `60` thuộc **toàn bộ cây con trái của `50`**, vì vậy phải **nhỏ hơn `50`**. Thực tế `60 > 50`, nên cây **không phải BST**.

Chính trường hợp này dễ bị bỏ qua khi người mới học chỉ nhớ “trái nhỏ hơn nút cha, phải lớn hơn nút cha”.

### Hậu quả đối với tìm kiếm

Nếu tìm khóa `60` từ gốc theo thuật toán BST:

```text
60 > 50 → đi phải sang 70
60 < 70 → đi trái
bên trái 70 rỗng → báo không tìm thấy
```

Trong khi đối tượng nút mang khóa `60` thực sự tồn tại ở dưới `30`. Cây đã làm **mất tính đúng của thuật toán tìm kiếm**, không chỉ sai một quy tắc trang trí.

### Phản ví dụ đối xứng

```text
                   50
                 /    \
               30      70
                      /
                     40    ← Sai vị trí trong BST
```

`40 < 70` đúng quan hệ với cha trực tiếp, nhưng `40` đang nằm trong cây con phải của `50` nên bắt buộc phải `>50`. Không thể chấp nhận cây này.

## 3. Tại sao phép kiểm tra con trực tiếp không đủ?

Một cài đặt dễ nghĩ tới là:

```python
def incorrect_local_check(node):
    if node is None:
        return True

    if node.left is not None:
        if not (node.left.key < node.key):
            return False

    if node.right is not None:
        if not (node.key < node.right.key):
            return False

    return (
        incorrect_local_check(node.left)
        and incorrect_local_check(node.right)
    )
```

Hàm này **đi qua mọi nút**, nhưng mỗi lần chỉ kiểm tra:

```text
node.left.key < node.key < node.right.key
```

nếu hai con tồn tại. Nó không lưu thông tin rằng **một nút nằm dưới cây con trái của `50` phải nhỏ hơn `50`, dù cha trực tiếp của nó là ai**.

### Kiểm thử làm lộ lỗi

```python
class Node:
    def __init__(self, key, value=None):
        self.key = key
        self.value = value
        self.left = None
        self.right = None


bad_left = Node(50)
bad_left.left = Node(30)
bad_left.right = Node(70)
bad_left.left.right = Node(60)  # 60 > 50 nhưng nằm bên trái 50

assert incorrect_local_check(bad_left) is True  # Kết quả SAI!
```

Ở đây `True` không có nghĩa cây hợp lệ, mà là **chứng cứ hàm kiểm tra cục bộ đã bỏ sót lỗi**.

Vấn đề không nằm ở cách dùng đệ quy hay vòng lặp. Dù duyệt hết cây, nếu **điều kiện kiểm tra quá yếu** thì vẫn không thể xác minh bất biến toàn cục.

## 4. Tư duy đúng: mỗi nút có một miền khóa hợp lệ

Tại gốc, chưa có tổ tiên nào hạn chế khóa, nên ta bắt đầu với miền:

```text
(-∞, +∞)
```

Nếu nút đang xét có khóa `k` và phải nằm trong `(low, high)`, điều kiện là:

```text
low < k < high
```

Trong đó:

- `low` là **cận dưới nghiêm ngặt** do những tổ tiên ở phía mà ta từng rẽ phải áp đặt.
- `high` là **cận trên nghiêm ngặt** do những tổ tiên ở phía mà ta từng rẽ trái áp đặt.
- Nếu chưa có cận ở một phía, ta hiểu phía đó **không bị giới hạn**.

### Quy tắc truyền miền xuống cây con

Khi nút `k` hợp lệ trong `(low,high)`:

- **Cây con trái:** các khóa phải thuộc **`(low,k)`**.
- **Cây con phải:** các khóa phải thuộc **`(k,high)`**.

```text
                        k ∈ (low, high)
                       /                \
       left nhận (low, k)       right nhận (k, high)
```

Đây là phép **thu hẹp khoảng**, không tạo khoảng mới độc lập rồi quên tổ tiên.

Nếu một khóa nằm ở cây con trái của `50`, cận trên `50` sẽ tiếp tục tồn tại ở mọi tầng phía dưới, trừ khi còn một cận trên chặt hơn do một tổ tiên gần hơn quy định.

### Phân tích phản ví dụ trước

```text
              50: (-∞, +∞)
             /
       30: (-∞, 50)
           \
           60: (30, 50)  ← 60 không thuộc (30,50)
```

Kiểm tra tại `60`:

```text
low = 30, high = 50, key = 60

30 < 60      đúng
60 < 50      sai

⇒ BST không hợp lệ
```

Điều kiện sai xuất phát từ **cận trên của tổ tiên `50`**, vốn không xuất hiện trong phép so `60` với cha `30`.

## 5. Truy vết miền trên cây hợp lệ nhiều tầng

Dùng cây:

```text
                     50
                   /    \
                 30      70
                /  \    /  \
              20   40  60   80
                  /
                 35
```

Các miền nhận được khi đi xuống:

| Nút | Đường từ gốc | Miền hợp lệ |
| --- | --- | --- |
| `50` | Gốc | `(-∞,+∞)` |
| `30` | Trái của `50` | `(-∞,50)` |
| `20` | Trái của `30` | `(-∞,30)` |
| `40` | Phải của `30`, vẫn trái `50` | `(30,50)` |
| `35` | Trái của `40` | `(30,40)` |
| `70` | Phải của `50` | `(50,+∞)` |
| `60` | Trái của `70` | `(50,70)` |
| `80` | Phải của `70` | `(70,+∞)` |

Nút `35` phải thỏa cả `35 > 30`, `35 < 40` và `35 < 50`. Khoảng `(30,40)` đã **gói gọn** những giới hạn quan trọng nhất. Vì `40 < 50`, ràng buộc `<40` còn chặt hơn `<50`.

### Giới hạn không đơn thuần là “khóa cha”

Tại `35`, cha là `40`, nhưng **cận dưới là `30`**, không phải `40`. Nếu chỉ dựa vào khóa cha, ta sẽ không biết khóa `25` ở vị trí `35` là sai vì nó nhỏ hơn `30`.

Nếu thay `35` bằng `25`:

```text
              30
                \
                 40
                /
               25
```

thì `25 < 40` đúng với cha trực tiếp, nhưng `25` thuộc cây con phải của `30` nên phải `>30`. Miền `(30,40)` phát hiện ngay.

## 6. Giả mã kiểm tra toàn BST bằng khoảng mở

Thuật toán tổng quát:

```text
VALIDATE(node, low, high):
    if node is null:
        return true

    if low tồn tại and not (low < node.key):
        return false

    if high tồn tại and not (node.key < high):
        return false

    return (
        VALIDATE(node.left,  low,      node.key)
        and
        VALIDATE(node.right, node.key, high)
    )


IS_VALID_BST(root):
    return VALIDATE(root, không_có_cận, không_có_cận)
```

**Dạng khoảng mở** có ý nghĩa rõ:

- Nút bằng `low` → **không hợp lệ**.
- Nút bằng `high` → **không hợp lệ**.
- Tất cả nút đều phải **nằm nghiêm ngặt bên trong** các giới hạn còn hiệu lực.

Đây là lựa chọn đúng cho **BST không cho phép khóa trùng ở hai nút khác nhau**.

### Cơ sở dừng

`None` đại diện cây rỗng. Cây rỗng thỏa bất biến BST theo nghĩa không có khóa nào vi phạm. Vì vậy:

```text
VALIDATE(None, low, high) = True
```

**Không** được kiểm tra `node.key` trước khi biết `node` có phải `None` không.

### Dừng sớm

Ngay khi tìm thấy nút vượt miền, trả `False`. Không cần tiếp tục kiểm tra các nhánh khác nếu mục tiêu chỉ là câu hỏi **cả cây có hợp lệ không?**

Nếu cần **báo cáo tất cả các lỗi** để chẩn đoán, có thể tiếp tục duyệt và lưu những nút vi phạm, nhưng đó là hợp đồng khác, tốn thêm bộ nhớ cho danh sách lỗi.

## 7. Cài đặt Python đệ quy: dễ đọc và trực tiếp

Ta dùng lại lớp `Node` ở phần 3. Các khóa minh họa là **số nguyên**; `None` dùng làm dấu **“không có cận”**, nên trong phiên bản này **`None` không phải khóa hợp lệ**.

```python
def is_bst_recursive(root):
    """Kiểm tra BST có khóa duy nhất, so sánh được bằng <."""

    def visit(node, low, high):
        if node is None:
            return True

        if low is not None and not (low < node.key):
            return False

        if high is not None and not (node.key < high):
            return False

        return (
            visit(node.left, low, node.key)
            and visit(node.right, node.key, high)
        )

    return visit(root, None, None)
```

Việc dùng `not (low < key)` và `not (key < high)` còn nhấn mạnh rằng **giới hạn là nghiêm ngặt**, không chấp nhận khóa bằng biên.

### Kiểm thử một cây đúng

```python
good = Node(50)
good.left = Node(30)
good.right = Node(70)
good.left.left = Node(20)
good.left.right = Node(40)
good.right.left = Node(60)
good.right.right = Node(80)

assert is_bst_recursive(good) is True
```

### Kiểm thử vi phạm nằm sâu

```python
assert is_bst_recursive(bad_left) is False

bad_right = Node(50)
bad_right.left = Node(30)
bad_right.right = Node(70)
bad_right.right.left = Node(40)  # 40 < 50 nhưng ở cây con phải

assert incorrect_local_check(bad_right) is True
assert is_bst_recursive(bad_right) is False
```

### Cây rỗng và một nút

```python
assert is_bst_recursive(None) is True
assert is_bst_recursive(Node(42)) is True
```

Một cây có một nút luôn thỏa thứ tự BST nếu khóa của nó thuộc miền giá trị cho phép và comparator được định nghĩa hợp lệ. Trong bài, các khóa là số nguyên thông thường, không có `NaN` hay giá trị so sánh đặc biệt.

## 8. Cài đặt Python lặp bằng stack tường minh

Đệ quy dùng call stack của Python, nên có thể gây `RecursionError` nếu BST rất sâu. Ta có thể dùng **stack lưu ba thành phần `(node, low, high)`**.

```python
def is_bst_iterative(root):
    """Kiểm tra BST khóa duy nhất, không dùng đệ quy."""
    pending = [(root, None, None)]

    while pending:
        node, low, high = pending.pop()

        if node is None:
            continue

        if low is not None and not (low < node.key):
            return False

        if high is not None and not (node.key < high):
            return False

        pending.append((node.right, node.key, high))
        pending.append((node.left, low, node.key))

    return True
```

**Vì sao đẩy phải trước, trái sau?** Vì stack là *LIFO*: đẩy phải trước làm trái được xét trước. Tuy nhiên, với bài toán chỉ cần trả `True/False`, **thứ tự xét trái hay phải không quyết định tính đúng**. Nó chỉ ảnh hưởng nút lỗi nào được phát hiện trước nếu có nhiều vi phạm.

### Kiểm thử hai phiên bản cho cùng kết quả

```python
for sample, expected in (
    (None, True),
    (Node(42), True),
    (good, True),
    (bad_left, False),
    (bad_right, False),
):
    assert is_bst_recursive(sample) is expected
    assert is_bst_iterative(sample) is expected
```

Bản lặp thường là lựa chọn an toàn hơn khi **chiều cao BST không được kiểm soát**, ví dụ cây tạo ra từ dãy tăng dần.

### Những thông tin thực sự nằm trong stack

Tại mỗi mục `(node,low,high)`, ta lưu không chỉ nút đang xét mà còn **ngữ cảnh ràng buộc của mọi tổ tiên** cần thiết để xác minh nút ấy. Nếu chỉ đẩy `node` mà không có giới hạn, ta sẽ phải tìm lại tổ tiên hoặc bỏ sót thông tin toàn cục.

## 9. Chứng minh tính đúng của thuật toán truyền miền

Ta xét một cây nhị phân hữu hạn, không có chu trình, với khóa duy nhất và comparator nhất quán.

### Chiều thuận: cây là BST thì thuật toán trả True

Giả sử cây thỏa bất biến BST. Tại gốc, miền không bị giới hạn nên khóa gốc hợp lệ.

Với một nút có khóa `k` hợp lệ trong `(low,high)`:

- Mọi khóa thuộc cây con trái đều **`< k`**, đồng thời phải thỏa giới hạn `low` từ tổ tiên.
- Mọi khóa thuộc cây con phải đều **`> k`**, đồng thời phải thỏa giới hạn `high` từ tổ tiên.

Do đó, truyền `(low,k)` sang trái và `(k,high)` sang phải không từ chối bất kỳ nút nào của một BST thực sự hợp lệ. Lặp lại theo chiều sâu cho tới lá, thuật toán trả `True`.

### Chiều ngược: thuật toán trả True thì cây là BST

Giả sử mọi nút được xét đều thỏa **miền được truyền xuống**. Xét bất kỳ nút `x` mang khóa `k`.

- Mọi nút thuộc cây con trái của `x` đi qua lần rẽ trái từ `x`; do đó, miền của chúng có một **cận trên không lớn hơn `k`**. Vì chúng được chấp nhận, mọi khóa ấy **`< k`**.
- Tương tự, mọi nút thuộc cây con phải của `x` nhận một **cận dưới không nhỏ hơn `k`**, nên mọi khóa đều **`> k`**.

Lập luận đúng tại mọi nút và mọi hậu duệ, suy ra bất biến BST đúng trên toàn cây.

**Kết luận:** trong phạm vi giả định của bài, hàm trả `True` **khi và chỉ khi** cây thỏa bất biến BST với khóa phân biệt.

### Tính kết thúc

Mỗi lời gọi xử lý một nút rồi chuyển tới hai cây con nhỏ hơn. Với cây hữu hạn, không có chu trình hoặc nút được dùng chung sai cách, mỗi nút được xét một lần và các nhánh rỗng chấm dứt đệ quy.

**Lưu ý:** nếu đối tượng đầu vào chứa chu trình con trỏ, điều kiện “đầu vào là một cây” đã bị vi phạm; bản kiểm tra thông thường có thể lặp mãi. Phần sau sẽ bổ sung một cách phát hiện lỗi cấu trúc này.

## 10. Độ phức tạp: kiểm tra toàn cây tốn O(n), không phải O(h)

Gọi:

- `n` là số nút trong cây.
- `h` là chiều cao cây đo bằng **số nút trên đường dài nhất từ gốc tới lá**.

Một BST hợp lệ có thể chứa lỗi **tại bất kỳ nút nào**, kể cả lá rất sâu. Nếu cần chắc chắn cả cây đúng, thuật toán phải có khả năng kiểm tra toàn bộ `n` nút.

| Phương án | Thời gian trường hợp xấu nhất | Bộ nhớ phụ |
| --- | --- | --- |
| Đệ quy truyền miền | **`O(n)`** | **`O(h)`** call stack |
| DFS lặp với stack miền | **`O(n)`** | **`O(h)`** stack |
| Duyệt in-order kiểm tra khóa tăng | **`O(n)`** | **`O(h)`** nếu dùng stack |
| Kiểm tra từng con trực tiếp | `O(n)` | `O(h)`, nhưng **không đúng** |
| Duyệt lưu tất cả khóa rồi sắp xếp lại | Ít nhất `O(n)`, thường thêm chi phí sort | `O(n)` để chứa khóa |
| Kiểm tra cả tính cấu trúc với tập nút đã thấy | `O(n)` | Có thể **`O(n)`** |

### BST cân đối và BST lệch

- BST cân đối: `h = O(log n)`, nên DFS có bộ nhớ phụ `O(log n)`.
- BST lệch thành chuỗi: `h = Θ(n)`, nên bản đệ quy có thể dùng `Θ(n)` call stack.
- **Cả hai đều có thời gian kiểm tra toàn cây `O(n)`**, vì số nút phải được xem xét vẫn là `n`.

Điểm này khác với **tìm kiếm một khóa** vốn mất `O(h)`: kiểm tra **toàn bộ tính đúng của BST** phải xét các nhánh chứ không chỉ một đường tìm.

### Dừng sớm không thay đổi giới hạn xấu nhất

Nếu gặp vi phạm sớm, chương trình có thể trả `False` sau vài bước. Nhưng với một cây hợp lệ hoặc cây có vi phạm ở nút được thăm cuối cùng, nó vẫn phải xét `Θ(n)` nút.

Không được kết luận “kiểm tra BST là `O(log n)`” chỉ vì cây cân đối hoặc vì ta dùng ranh giới khoảng để kiểm tra.

## 11. Không dùng min/max của kiểu số làm cận “vô hạn”

Một cách cài đặt hay gặp là khởi tạo:

```python
low = -float("inf")
high = float("inf")
```

Với **khóa là số thực hữu hạn và có thứ tự phù hợp**, cách ấy có thể hoạt động. Nhưng nó **không phải lựa chọn tổng quát** cho mọi miền khóa:

- Khóa có thể là **chuỗi** hoặc tuple, không so sánh được với `float("-inf")`.
- Kiểu khóa có thể chứa số nguyên rất lớn hoặc đối tượng comparator tùy biến.
- **`-inf` hoặc `+inf` có thể là chính một khóa hợp lệ** trong một miền số mở rộng; biên nghiêm ngặt sẽ từ chối nó.
- Giá trị như `NaN` không tuân thủ các phép so sánh thứ tự thông thường.

Do đó, nên biểu diễn **“không có cận” bằng một dấu riêng**, thay vì giả định một giá trị số cực nhỏ/cực lớn luôn đủ.

Trong phiên bản số nguyên của bài, ta dùng `None` làm dấu không có cận. Tuy nhiên, nếu **`None` cũng được cho phép làm khóa**, phải dùng **một sentinel riêng** để không nhập nhằng giữa “cận bằng None” và “không có cận”.

## 12. Validator tổng quát hơn với comparator và sentinel

Có thể tham số hóa phép so sánh bằng một hàm `less(a,b)`, trả `True` khi khóa `a` phải đứng trước khóa `b`.

Ta cũng dùng một đối tượng duy nhất `UNBOUNDED` biểu thị “không có cận”:

```python
UNBOUNDED = object()


def is_bst_with_comparator(root, less):
    """Xác minh BST khóa duy nhất theo strict total order less."""
    pending = [(root, UNBOUNDED, UNBOUNDED)]

    while pending:
        node, low, high = pending.pop()

        if node is None:
            continue

        key = node.key

        if low is not UNBOUNDED and not less(low, key):
            return False

        if high is not UNBOUNDED and not less(key, high):
            return False

        pending.append((node.left, low, key))
        pending.append((node.right, key, high))

    return True
```

Ví dụ dùng thứ tự của số nguyên:

```python
def less_number(a, b):
    return a < b


assert is_bst_with_comparator(good, less_number)
assert not is_bst_with_comparator(bad_left, less_number)
assert not is_bst_with_comparator(bad_right, less_number)
```

### Thứ tự trên khóa chuỗi

```python
words = Node("m")
words.left = Node("c")
words.right = Node("t")
words.left.right = Node("f")

assert is_bst_with_comparator(words, lambda a, b: a < b)
```

Đối với comparator tùy biến, phải có một **thứ tự nghiêm ngặt đầy đủ, nhất quán** trên các khóa mà cây chấp nhận; nếu comparator tạo ra quan hệ không bắc cầu hoặc không xác định, thuật toán BST nói chung không có bảo đảm.

**Sentinel không chữa được comparator sai.** Nó chỉ giúp phân biệt rõ “không có cận” với một **giá trị khóa hợp lệ**.

## 13. Khóa trùng: cận đóng/mở phải theo chính sách của cây

Tất cả mã ở trên dành cho **BST có khóa phân biệt**: mọi miền đều mở ở hai đầu.

Nhưng một số cấu trúc cho phép khóa trùng theo chính sách cụ thể. Ta cần phân biệt:

| Chính sách lưu trữ | Quy tắc bất biến |
| --- | --- |
| **BST-set** | Mỗi khóa chỉ có một nút; trái `< key`, phải `> key` |
| **BST-map** | Mỗi khóa một nút; cập nhật giá trị nếu khóa đã có |
| **BST-multiset lưu count** | Một nút cho mỗi khóa phân biệt, thêm `count`; vẫn dùng miền **mở** |
| **BST cho phép nút trùng sang phải** | Trái **`< key`**, phải **`>= key`** |
| **BST cho phép nút trùng sang trái** | Trái **`<= key`**, phải **`> key`** |

**Không** thể lấy một validator với tất cả khoảng mở rồi kỳ vọng nó chấp nhận đúng một cây có nhiều nút khóa bằng nhau. Ngược lại, đổi sang cận bao gồm bằng khi cấu trúc thực tế không cho phép trùng sẽ làm validator chấp nhận cây sai.

### Ví dụ nếu các nút trùng luôn thuộc nhánh phải

```text
              50
                \
                 70
                /
               50
```

Tại `50` thứ hai, quan hệ với tổ tiên gốc yêu cầu **`key >= 50`**, trong khi quan hệ với nút `70` yêu cầu **`key < 70`**. Miền hợp lệ của nút là **`[50,70)`**.

Một cách kiểm tra có thể mang theo thông tin hai cận có **bao gồm bằng hay không**, thay vì chỉ hai giá trị `low/high`.

### Bản validator minh họa cho chính sách “trùng sang phải”

```python
def is_bst_duplicates_right(root):
    """Cho phép key trái < node.key, key phải >= node.key."""
    # (node, low, low_inclusive, high, high_inclusive)
    stack = [(root, None, False, None, False)]

    while stack:
        node, low, inc_low, high, inc_high = stack.pop()
        if node is None:
            continue

        key = node.key

        if low is not None:
            if key < low or (key == low and not inc_low):
                return False

        if high is not None:
            if key > high or (key == high and not inc_high):
                return False

        # Bên trái luôn nghiêm ngặt nhỏ hơn key.
        stack.append((node.left, low, inc_low, key, False))

        # Bên phải được bằng key hiện tại.
        stack.append((node.right, key, True, high, inc_high))

    return True
```

Kiểm thử:

```python
duplicate_on_right = Node(50)
duplicate_on_right.right = Node(70)
duplicate_on_right.right.left = Node(50)

assert is_bst_duplicates_right(duplicate_on_right)
assert not is_bst_recursive(duplicate_on_right)

wrong_duplicate_side = Node(50)
wrong_duplicate_side.left = Node(50)

assert not is_bst_duplicates_right(wrong_duplicate_side)
```

**Lưu ý về thiết kế:** với dữ liệu trùng nhiều và cần giữ chiều cao nhỏ, gom các bản sao trong `count` hoặc collection giá trị tại **một nút** thường dễ duy trì bất biến và thông tin phụ hơn. Khi đó phần khóa của BST vẫn dùng validator **nghiêm ngặt**.

## 14. So sánh kiểm tra miền với duyệt giữa in-order

Một BST hợp lệ với khóa duy nhất có dãy **in-order** tăng nghiêm ngặt. Vì vậy, ngoài cách truyền cận, ta còn có thể duyệt giữa và so với khóa trước đó.

### Validator theo thứ tự in-order

```python
def is_bst_inorder(root):
    """Kiểm tra khóa tăng nghiêm ngặt khi duyệt giữa."""
    stack = []
    current = root

    has_previous = False
    previous = None

    while stack or current is not None:
        while current is not None:
            stack.append(current)
            current = current.left

        current = stack.pop()

        if has_previous and not (previous < current.key):
            return False

        previous = current.key
        has_previous = True

        current = current.right

    return True
```

Kiểm thử:

```python
assert is_bst_inorder(good) is True
assert is_bst_inorder(bad_left) is False
assert is_bst_inorder(bad_right) is False
assert is_bst_inorder(None) is True
```

### Vì sao hai cách tương đương?

Với một cây nhị phân hữu hạn đúng cấu trúc và các khóa có thứ tự nghiêm ngặt đầy đủ:

- Nếu BST hợp lệ, thứ tự **trái → nút → phải** cho dãy tăng nghiêm ngặt.
- Nếu toàn bộ dãy in-order tăng nghiêm ngặt, mọi phần tử xuất hiện trước một nút đều nhỏ hơn khóa nút ấy, mọi phần tử xuất hiện sau đều lớn hơn; điều đó đủ để chứng minh bất biến trên mọi cây con.

Với khóa duy nhất, hai validator là hai cách diễn đạt của cùng điều kiện thứ tự, nhưng **cách miền khóa giúp làm rõ ràng buộc từ tổ tiên và vị trí vi phạm**.

### So sánh ưu và nhược

| Tiêu chí | Kiểm tra miền `(low,high)` | Kiểm tra in-order tăng |
| --- | --- | --- |
| Thể hiện trực tiếp điều kiện toàn cây con | **Có** | Gián tiếp qua dãy |
| Truyền giới hạn tổ tiên | **Có** | Không cần |
| Lưu khóa trước đó | Không cần | Cần |
| Phát hiện lỗi ở một nút | Khi khóa vượt miền của nút | Khi thứ tự hiện tại không lớn hơn khóa trước |
| Thời gian | `O(n)` | `O(n)` |
| Bộ nhớ phụ bản lặp | `O(h)` | `O(h)` |
| Mở rộng cho chính sách cận đóng/mở | Rõ ràng | Cần thêm quy tắc cho các khóa bằng nhau |

Với mục tiêu bài này, **truyền miền khóa** là phương án chính. In-order là cách **kiểm tra chéo độc lập** khi viết test.

## 15. Chỉ so min/max toàn cây con có đúng không?

Một phương án khác là kiểm tra:

- **Khóa lớn nhất của cây con trái** phải `< node.key`.
- **Khóa nhỏ nhất của cây con phải** phải `> node.key`.
- Hai cây con cũng hợp lệ.

Điều kiện này **đúng về mặt logic** nếu các cực trị được tính chính xác. Vấn đề là cách cài ngây thơ có thể tốn nhiều công.

Ví dụ:

```text
Tại mỗi nút:
    tìm maximum toàn bộ cây con trái
    tìm minimum toàn bộ cây con phải
    rồi kiểm tra đệ quy cả hai cây con
```

**Nếu cài hàm min/max bằng cách quét toàn bộ cây con mỗi lần gọi**, rồi lặp lại ở từng nút, các nút có thể bị xét nhiều lần; trên cây lệch, chi phí có thể thành **`Θ(n²)`** thay vì `Θ(n)`. Nếu tận dụng thứ tự BST để tìm cực trị chỉ bằng cách lần theo liên kết trái/phải, phải phân tích chính xác những đường đi đã duyệt; không thể mặc định mọi cách kiểm tra min/max đều tốn `Θ(n²)`.

Cách cải tiến là mỗi lần đệ quy **trả về đồng thời**:

```text
(is_valid, min_key, max_key)
```

và tính min/max từ kết quả của hai con đúng **một lần**. Cách này cũng có thể kiểm tra trong `O(n)`, nhưng cài đặt dài hơn và phải xử lý cây con rỗng/các sentinel cực trị.

**Truyền miền từ trên xuống** đơn giản hơn khi mục tiêu chỉ là xác minh bất biến BST. Hai tư duy đều dựa trên việc xét **toàn bộ cây con**, không phải chỉ so một cặp cha–con.

## 16. Vi phạm ở biên bằng nhau: lỗi rất dễ lọt

Với BST khóa phân biệt, những phép so sau phải dùng dấu **nghiêm ngặt**.

```text
low < key
key < high
```

Không được thay bằng:

```text
low <= key <= high
```

nếu chính sách không cho phép hai nút mang cùng một khóa.

### Trùng khóa sâu trong cây

```text
                50
               /
             30
               \
                50    ← Trùng khóa với gốc
```

Ở nút `50` dưới cùng, miền là `(30,50)`. Vì khóa **bằng cận trên**, nó phải bị từ chối.

```python
deep_duplicate = Node(50)
deep_duplicate.left = Node(30)
deep_duplicate.left.right = Node(50)

assert incorrect_local_check(deep_duplicate) is True
assert is_bst_recursive(deep_duplicate) is False
assert is_bst_iterative(deep_duplicate) is False
```

Quan hệ cha–con trực tiếp vẫn `50 > 30`, nhưng khóa trùng với **tổ tiên** làm cây không còn hợp lệ theo chính sách khóa duy nhất.

### Khóa âm, khóa bằng 0 và biên không có cận

```python
negative_keys = Node(0)
negative_keys.left = Node(-10)
negative_keys.right = Node(10)
negative_keys.left.right = Node(-3)

assert is_bst_recursive(negative_keys) is True
assert is_bst_iterative(negative_keys) is True
```

Cận bằng `0` là **cận thật**, không phải cận rỗng. Do đó, kiểm tra phải viết:

```python
if low is not None:
    ...
```

thay vì:

```python
if low:  # SAI khi low == 0
    ...
```

Cách viết `if low` có thể làm bỏ qua chính giới hạn do một tổ tiên mang khóa `0` áp đặt.

## 17. Một phản ví dụ mạnh với giới hạn từ nhiều tổ tiên

Xét cây:

```text
                   100
                  /
                50
                  \
                   80
                  /
                 60
                   \
                    75
                      \
                       90    ← Sai
```

Các quan hệ cha–con trực tiếp trên đường chứa `90` đều có vẻ đúng:

```text
50 < 100
80 > 50
60 < 80
75 > 60
90 > 75
```

Nhưng nút `90` nằm trong **cây con trái của `80`** (đi từ `80` xuống `60` rồi qua `75`). Vì thế nó bắt buộc **nhỏ hơn `80`**, trong khi `90 > 80`.

Theo thuật toán truyền miền:

| Nút | Miền |
| --- | --- |
| `100` | `(-∞,+∞)` |
| `50` | `(-∞,100)` |
| `80` | `(50,100)` |
| `60` | `(50,80)` |
| `75` | `(60,80)` |
| `90` | `(75,80)` → **vi phạm** |

Đường đi phức tạp không làm thay đổi công thức. Mỗi lần rẽ trái cập nhật **cận trên** bằng khóa hiện tại; mỗi lần rẽ phải cập nhật **cận dưới**. Miền tiếp tục giữ đủ những giới hạn quan trọng nhất từ tổ tiên.

### Kiểm thử ví dụ dài

```python
bad_deep = Node(100)
bad_deep.left = Node(50)
bad_deep.left.right = Node(80)
bad_deep.left.right.left = Node(60)
bad_deep.left.right.left.right = Node(75)
bad_deep.left.right.left.right.right = Node(90)

assert incorrect_local_check(bad_deep) is True
assert is_bst_recursive(bad_deep) is False
assert is_bst_iterative(bad_deep) is False
```

Đây là một kiểm thử tốt để tránh “sửa sai nửa vời”: nếu mã kiểm tra chỉ biết tới cha và ông trực tiếp, nó vẫn có thể bỏ sót vi phạm từ tổ tiên xa hơn.

## 18. Đầu vào không phải cây: chu trình và nút được dùng chung

Các validator trước đó giả định cấu trúc dữ liệu đã là **cây nhị phân đúng nghĩa**:

- Mỗi nút (trừ gốc) chỉ có **một cha** trong cấu trúc.
- Không tồn tại **chu trình**.
- Từ gốc có **một đường duy nhất** tới mỗi nút.

Nếu lỗi con trỏ tạo `node.left = node` hoặc cùng một đối tượng nút bị gắn vào hai nhánh, dữ liệu không còn là một cây. Các phép duyệt ngây thơ có thể lặp vô hạn khi gặp chu trình. Validator miền khóa có thể tình cờ từ chối sớm vì mâu thuẫn thứ tự, nhưng **không nên xem việc kiểm tra khóa là một hợp đồng đầy đủ để phát hiện lỗi liên kết và chu trình**.

### Cách kiểm tra thêm danh tính nút

Dùng `set` ghi nhận những **đối tượng nút đã gặp**. Nếu cùng đối tượng xuất hiện lần thứ hai qua liên kết con, ta từ chối:

```python
def is_valid_bst_structure(root):
    """Kiểm tra cả thứ tự BST và không có nút lặp/chu trình."""
    pending = [(root, None, None)]
    seen = set()

    while pending:
        node, low, high = pending.pop()
        if node is None:
            continue

        marker = id(node)
        if marker in seen:
            return False
        seen.add(marker)

        if low is not None and not (low < node.key):
            return False
        if high is not None and not (node.key < high):
            return False

        pending.append((node.left, low, node.key))
        pending.append((node.right, node.key, high))

    return True
```

Kiểm thử:

```python
cyclic = Node(50)
cyclic.left = cyclic

assert is_valid_bst_structure(cyclic) is False

shared = Node(50)
child = Node(30)
shared.left = child
shared.right = child

assert is_valid_bst_structure(shared) is False
assert is_valid_bst_structure(good) is True
```

### Đánh đổi bộ nhớ

Khi chỉ kiểm tra thứ tự trên một **cây đã được tin cậy là đúng cấu trúc**, stack DFS cần `O(h)` bộ nhớ phụ. Thêm `seen` làm chương trình dùng **`O(n)` bộ nhớ phụ** trong trường hợp xấu nhất.

Do đó, hãy **nói rõ hợp đồng của validator**:

- `is_bst_iterative`: kiểm tra **thứ tự BST**, giả định đầu vào là cây.
- `is_valid_bst_structure`: kiểm tra **thứ tự BST cộng với không có chu trình/nút dùng chung**.

Nếu nút có trường `parent`, ta còn có thể kiểm tra `root.parent is None` và mọi `child.parent is node` để xác minh bất biến liên kết hai chiều. Đó là một trách nhiệm bổ sung, không tự động được đảm bảo chỉ bằng miền khóa.

## 19. Khi dữ liệu thay đổi: kiểm tra định kỳ hay duy trì bất biến?

Một BST đúng không nhất thiết phải chạy validator toàn cây sau **mỗi** thao tác. Trong một cài đặt đúng, các hàm **insert/delete/rotation** được thiết kế để **duy trì bất biến** bằng những phép biến đổi cục bộ có chứng minh.

Vì vậy:

- **Trong học tập và kiểm thử:** có thể chạy validator sau mỗi lần chèn/xóa trên tập dữ liệu nhỏ để phát hiện lỗi.
- **Trong phần mềm sản xuất:** kiểm tra toàn cây `O(n)` sau mỗi cập nhật có thể làm tăng mạnh chi phí; thường cần thuật toán cập nhật đúng, kiểm thử tự động và kiểm tra định kỳ/giám sát nếu có yêu cầu.
- **Khi nhận cây từ dữ liệu không đáng tin cậy:** nên xem xét kiểm tra cả **thứ tự**, **liên kết/chu trình** và những metadata được dùng cho truy vấn.

### Liên hệ với thao tác chèn

Nếu BST ban đầu hợp lệ và thao tác chèn tìm vị trí theo đúng comparator rồi gắn khóa mới tại liên kết con rỗng, các quyết định rẽ trái/rẽ phải đã gián tiếp xác định **miền khóa phù hợp** cho nút mới.

Ngược lại, nếu lập trình viên tự gắn một nút bất kỳ vào một liên kết chỉ vì “nó lớn hơn cha trực tiếp”, họ có thể phá giới hạn từ tổ tiên và khiến tìm kiếm sau này sai.

### Liên hệ với thao tác xóa

Xóa nút lá, nút một con hoặc nút hai con bằng kế nhiệm/tiền nhiệm đều phải bảo toàn **bất biến trên toàn cây con**, không chỉ nối đúng con trỏ cha–con. Sau khi xóa, validator bằng miền khóa là một kiểm tra hữu ích cho các bài tập thực hành.

## 20. Tạo bộ kiểm thử đối chiếu hai thuật toán đúng

Có thể dùng một hàm chèn BST khóa duy nhất để tạo **cây hợp lệ**, rồi kiểm tra bằng cả hai phương án:

```python
def insert_unique(root, key):
    if root is None:
        return Node(key)

    current = root
    while True:
        if key == current.key:
            return root

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


numbers = [50, 30, 70, 20, 40, 60, 80, 35, 45]
built = None

for key in numbers:
    built = insert_unique(built, key)

assert is_bst_recursive(built) is True
assert is_bst_iterative(built) is True
assert is_bst_inorder(built) is True
assert is_valid_bst_structure(built) is True
```

Giờ chủ động sửa một khóa ở vị trí sâu:

```python
# Nút 45 là con phải của 40, nhưng vẫn ở cây con trái của 50.
built.left.right.right.key = 55

# Quan hệ 55 > 40 với cha vẫn đúng.
assert incorrect_local_check(built) is True

# Nhưng 55 không được nằm trong cây con trái của 50.
assert is_bst_recursive(built) is False
assert is_bst_iterative(built) is False
assert is_bst_inorder(built) is False
```

Những kiểm thử này không đo hiệu năng; chúng xác nhận **hợp đồng logic** của validator.

### Các nhóm ca cần có

| Nhóm | Ví dụ | Kỳ vọng |
| --- | --- | --- |
| Cây rỗng | `None` | `True` |
| Cây một nút | `Node(7)` | `True` |
| BST cân đối đúng | `50,30,70,20,40,60,80` | `True` |
| BST lệch đúng | `1 → phải 2 → phải 3` | `True` |
| Sai ở con trực tiếp | `left.key > parent.key` | `False` |
| Sai ở hậu duệ trái | `60` dưới cây con trái của `50` | `False` |
| Sai ở hậu duệ phải | `40` dưới cây con phải của `50` | `False` |
| Trùng với tổ tiên | `50` ở cây con trái của `50` | `False` nếu khóa duy nhất |
| Khóa âm/0 | `-10,0,10` đúng thứ tự | `True` |
| Cây có chu trình | `node.left is node` | `False` với bản kiểm tra cấu trúc |
| Dùng chung một nút | Cùng `Node` ở hai nhánh | `False` với bản kiểm tra cấu trúc |

### Thử BST lệch rất sâu

Có thể dựng một cây lệch có `n` nút và kiểm tra bằng bản lặp:

```python
deep = Node(0)
current = deep

for value in range(1, 2000):
    current.right = Node(value)
    current = current.right

assert is_bst_iterative(deep) is True
```

Bản đệ quy `is_bst_recursive` có thể gặp `RecursionError` trên một cây như vậy do giới hạn stack của Python. Đây không phải lỗi logic của miền khóa; nó là **giới hạn của cách triển khai đệ quy**.

## 21. Những lỗi thường gặp

1. **Chỉ so con trái/con phải với cha.** Không phát hiện hậu duệ vượt giới hạn tổ tiên.
2. **Duyệt toàn cây nhưng vẫn dùng điều kiện cục bộ yếu.** Đi qua mọi nút không đồng nghĩa đã kiểm tra đủ bất biến.
3. **Quên truyền cận trên khi rẽ trái.** Nút trong nhánh trái có thể lớn hơn tổ tiên.
4. **Quên truyền cận dưới khi rẽ phải.** Nút trong nhánh phải có thể nhỏ hơn tổ tiên.
5. **Mỗi lần xuống cây con lại đặt `low/high` thành vô hạn.** Làm mất ràng buộc từ tổ tiên.
6. **Dùng cận đóng cho BST khóa duy nhất.** Có thể cho phép trùng khóa sâu trong cây.
7. **Dùng `if low` thay vì `if low is not None`.** Bỏ qua cận bằng `0` hoặc giá trị falsy khác.
8. **Dùng `float("-inf")`/`float("inf")` cho mọi kiểu khóa.** Có thể không so sánh được hoặc loại sai khóa vô cực hợp lệ.
9. **Cho rằng `value=None` nghĩa nút không tồn tại.** BST-map có thể lưu giá trị `None` hợp lệ; kiểm tra theo `key`.
10. **Cho rằng phép so sánh khóa nào cũng tạo thứ tự đầy đủ.** `NaN` hoặc comparator không nhất quán phá giả thiết.
11. **Cho rằng cây cân đối thì chắc chắn hợp lệ.** Cân đối là tính hình dạng; thứ tự BST là tính khóa.
12. **Cho rằng cây lệch thì không hợp lệ.** Chuỗi tăng một phía vẫn có thể là BST đúng.
13. **Báo validator là `O(h)` thời gian.** Kiểm tra tất cả nút cần `O(n)` trường hợp xấu nhất.
14. **Không tính call stack.** Phiên bản đệ quy dùng `O(h)` bộ nhớ phụ và có thể tràn khi cây sâu.
15. **Dùng `set` ghi nhớ mọi nút rồi vẫn báo bộ nhớ `O(h)`.** Khi thêm `seen`, chi phí có thể là `O(n)`.
16. **Áp dụng validator khóa duy nhất cho multiset dùng nhiều nút bằng nhau** mà không sửa chính sách cận.
17. **Chấp nhận trùng ở cả hai phía không theo hợp đồng.** Phải thống nhất quy tắc khi chèn/tìm/xóa.
18. **Đồng nhất thứ tự của `key` và `value`.** Thứ tự BST chỉ dựa trên khóa.
19. **Đảo điều kiện rẽ trái/rẽ phải trong quá trình truyền miền.** Gán sai cận sẽ chấp nhận hoặc từ chối nhầm.
20. **Kiểm tra một cây có chu trình bằng DFS không có đánh dấu** rồi không có điểm dừng.
21. **Chạy kiểm tra toàn cây `O(n)` sau mọi thao tác sản xuất** mà không xét tổng chi phí.
22. **Chỉ kiểm tra in-order mà kết luận parent pointer, subtree_size hoặc AVL balance đúng.** Những bất biến phụ cần kiểm tra riêng.

## 22. Luyện tập: tự xác minh các cây

**Bài 1.** Phát biểu bất biến BST cho **toàn bộ cây con** và giải thích khác biệt với việc so hai nút con trực tiếp.

**Bài 2.** Với cây `50` có con trái `30` và `30` có con phải `60`, vì sao phép so cha–con cho kết quả sai? Miền hợp lệ tại `60` là gì?

**Bài 3.** Với cây `50` có con phải `70` và `70` có con trái `40`, hãy tính cận của nút `40` và kết luận.

**Bài 4.** Đi theo các bước `gốc 100 → trái 50 → phải 80 → trái 60 → phải 75`. Miền hợp lệ ở `75` là gì?

**Bài 5.** Hãy điền tham số còn thiếu:
```text
validate(node.left,  ?,         node.key)
validate(node.right, node.key,  ?)
```

**Bài 6.** Vì sao thuật toán dùng khoảng **mở** `(low, high)` khi BST có khóa phân biệt? Điều gì xảy ra nếu khóa bằng `high`?

**Bài 7.** Viết hàm Python đệ quy kiểm tra BST bằng `low/high`. Phải kiểm tra `node is None` ở bước nào?

**Bài 8.** Chuyển hàm đệ quy thành bản lặp dùng stack ba thành phần. Bộ nhớ phụ liên quan thế nào đến chiều cao `h`?

**Bài 9.** Với BST có `n` nút, kiểm tra toàn cây vì sao tốn `O(n)` thời gian dù BST cân đối có chiều cao `O(log n)`?

**Bài 10.** Tại sao `if low: ...` có thể khiến validator bỏ lọt lỗi khi cận dưới bằng `0`?

**Bài 11.** Một BST-map lưu `value=None` ở nút có khóa `10`. Validator thứ tự có được từ chối nút ấy không? Vì sao?

**Bài 12.** So sánh validator truyền miền với validator in-order: điểm giống nhau về tính đúng/độ phức tạp và điểm khác nhau về trạng thái cần lưu.

**Bài 13.** Nếu BST-multiset lưu `count` tại một nút cho mỗi khóa phân biệt, validator nên dùng cận mở hay cận đóng?

**Bài 14.** Nếu chính sách là “nút trùng khóa được đặt sang phải”, hãy nêu miền hợp lệ cho cây con phải của nút khóa `50`. Miền thay đổi thế nào khi nút nằm trong cây con trái của một tổ tiên `70`?

**Bài 15.** Vì sao dùng `float("-inf")`/`float("inf")` làm sentinel không phù hợp khi khóa là chuỗi hoặc một kiểu đặc biệt?

**Bài 16.** Cho một nút có `left` trỏ lại chính nó. Validator lặp đơn giản có thể xảy ra chuyện gì? Hãy bổ sung bước ngăn chặn.

**Bài 17.** Hãy nêu một cây có dãy in-order tăng nghiêm ngặt nhưng có `parent` sai. Validator bằng miền khóa có tự phát hiện lỗi `parent` không?

**Bài 18.** Vì sao không nên gọi validator toàn cây sau mọi lần tìm `search(key)` hoặc mỗi lần cập nhật trong một hệ thống lớn?

**Bài 19.** Giả sử khóa là chuỗi và comparator so theo độ dài chuỗi trước, sau đó theo bảng chữ cái. Điều kiện nào cần thỏa giữa comparator lúc xây cây và validator?

**Bài 20.** Viết kiểm thử cho các ca: cây rỗng, một nút, BST lệch hợp lệ, hậu duệ trái vượt upper bound, hậu duệ phải nhỏ hơn lower bound, trùng khóa với tổ tiên và cây có chu trình.

<details>
<summary>Đáp án và gợi ý</summary>

1. Mọi khóa trong **toàn bộ** cây con trái của một nút phải nhỏ hơn khóa nút ấy, mọi khóa trong **toàn bộ** cây con phải phải lớn hơn; cả hai cây con tiếp tục thỏa bất biến. So con trực tiếp không kiểm tra được ràng buộc với tổ tiên xa hơn.
2. `30 < 50` và `60 > 30` đều đúng cục bộ, nhưng `60` đang ở cây con trái `50`. Miền `(30,50)`, `60` nằm ngoài.
3. Nút `40` nhận miền `(50,70)`; vì `40 <= 50` nên sai.
4. `75` nhận miền `(60,80)`; khóa `75` hợp lệ. Nếu gắn `90` vào vị trí ấy thì sai.
5. Trái nhận `low` và phải nhận `high`: `validate(node.left,low,node.key)`; `validate(node.right,node.key,high)`.
6. Cận nghiêm ngặt ngăn trùng khóa. `key == high` không thuộc miền hợp lệ.
7. Cơ sở `node is None → True` phải đứng trước truy cập thuộc tính; kiểm tra `low < key < high` với các cận có mặt rồi đệ quy.
8. Stack chứa `(node,low,high)`; thời gian `O(n)`, bộ nhớ phụ `O(h)` trong DFS thông thường.
9. Một nút lỗi có thể nằm ở bất kỳ nhánh nào. Phải duyệt toàn bộ `n` nút nếu cây hợp lệ hoặc vi phạm ở cuối đường duyệt; chiều cao nhỏ chỉ giảm bộ nhớ/đường đơn.
10. `0` là falsy trong Python, nên `if low` bỏ qua cận thật bằng 0. Dùng `low is not None` hoặc sentinel riêng.
11. Không. Giá trị `None` là payload hợp lệ; bất biến BST phụ thuộc vào **khóa**, không vào giá trị.
12. Cả hai đúng với một cây hữu hạn đúng cấu trúc, khóa duy nhất và comparator phù hợp; đều `O(n)` thời gian, `O(h)` stack. Bản miền mang `low/high`; in-order lưu khóa vừa phát trước đó.
13. Dùng **cận mở** trên khóa, vì mỗi khóa phân biệt vẫn chỉ có một nút; `count` là metadata.
14. Với gốc `50`, cây con phải nhận **`[50,+∞)`**; dưới cây con trái của tổ tiên `70`, miền trở thành **`[50,70)`**.
15. Khóa chuỗi không so được với số thực vô cực; một số kiểu khóa có phần tử cực trị đặc biệt. Dấu không cận nên tách khỏi giá trị khóa.
16. DFS không ghi nhớ có thể lặp lại mãi trên chu trình. Thêm `seen` và từ chối khi gặp lại cùng danh tính nút, tốn thêm `O(n)` bộ nhớ.
17. Có thể lấy BST khóa `20,30,40` đúng liên kết `left/right` nhưng gán sai `root.left.parent`. Dãy in-order vẫn tăng; validator chỉ kiểm tra khóa sẽ **không phát hiện** parent sai nếu không bổ sung kiểm tra liên kết.
18. Validator `O(n)`; thêm vào mỗi thao tác biến nhiều đường thao tác vốn `O(h)` thành chi phí chứa một lần quét toàn cây. Chỉ dùng khi có mục tiêu kiểm thử/giám sát rõ.
19. Phải dùng **cùng quy tắc so sánh nhất quán** khi xây, tìm và xác minh; thứ tự sắp theo bảng chữ cái đơn thuần có thể khác thứ tự ưu tiên độ dài.
20. Có thể dựng `Node` theo các ví dụ trong bài, kiểm tra `is_bst_iterative` và `is_bst_recursive` đối với cây cấu trúc chuẩn; dùng `is_valid_bst_structure` cho cây có chu trình hoặc nút dùng chung. Kỳ vọng lần lượt `True,True,True,False,False,False,False` theo thứ tự các ca đã nêu.

</details>

## Ghi nhớ

**Kiểm tra BST không thể chỉ hỏi “con trái nhỏ hơn cha, con phải lớn hơn cha”.** Điều kiện đúng là **mọi khóa trong toàn bộ cây con trái nhỏ hơn nút, mọi khóa trong toàn bộ cây con phải lớn hơn nút**, ở mọi mức. Hãy truyền một **miền khóa hợp lệ `(low,high)` từ tổ tiên xuống**: khi rẽ trái, thu hẹp thành **`(low,key)`**; khi rẽ phải, thu hẹp thành **`(key,high)`**. Bất kỳ nút nào ngoài miền đều làm cây không hợp lệ. Với BST khóa duy nhất, các cận là **nghiêm ngặt**; chính sách khóa trùng khác phải có quy tắc biên khác. Validator đệ quy hoặc stack duyệt DFS đều có **`O(n)` thời gian** và **`O(h)` bộ nhớ phụ**, không phụ thuộc việc BST có cân đối hay không. Nếu cần xác minh thêm chu trình, parent pointer hoặc metadata, phải kiểm tra riêng những bất biến cấu trúc ấy.

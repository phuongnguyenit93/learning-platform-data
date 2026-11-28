# Tra cứu khóa và đường đi quyết định bởi phép so sánh

Trong một hệ thống học tập, ta có thể lưu cặp **mã học viên → điểm số**, **mã khóa học → thông tin khóa học** hoặc **mã bài tập → kết quả** trong một **cây tìm kiếm nhị phân** (*Binary Search Tree – BST*). Khi cần tìm khóa `65`, thuật toán không phải xem lần lượt mọi nút. Tại mỗi nút, **một phép so sánh** cho biết nên dừng lại, đi sang trái hay đi sang phải.

Đó là ý tưởng cốt lõi của tra cứu BST: **đường đi từ gốc đến kết quả được quyết định bởi chuỗi phép so sánh khóa**. Bài này thuộc chương **Cây tìm kiếm nhị phân** của module cấu trúc dữ liệu. Ta sẽ mô phỏng từng bước tra cứu, giải thích vì sao có thể bỏ qua toàn bộ một cây con, cài thuật toán lặp và đệ quy, phân tích độ phức tạp theo chiều cao và nhận diện những lỗi liên quan đến thứ tự khóa.

## 1. Điều kiện tiên quyết: cây thực sự thỏa bất biến BST

**Cây nhị phân** chỉ quy định mỗi nút có tối đa hai con. **BST** còn quy định thứ tự khóa. Trong bài này, ta dùng **khóa duy nhất**, với phép so sánh nhất quán:

- Mọi khóa thuộc **toàn bộ cây con trái** của một nút đều **nhỏ hơn** khóa nút ấy.
- Mọi khóa thuộc **toàn bộ cây con phải** đều **lớn hơn** khóa nút ấy.
- Hai cây con tiếp tục thỏa đúng quy tắc BST đó.

Ký hiệu tại nút có khóa `k`:

```text
mọi x trong cây con trái: x < k
mọi y trong cây con phải: y > k
```

Từ **“mọi”** rất quan trọng. Không chỉ nút con trực tiếp phải đúng: mọi hậu duệ ở phía trái hoặc phải đều phải tuân thủ giới hạn do tổ tiên đặt ra.

Xét cây ví dụ xuyên suốt:

```text
                      50
                    /    \
                  30      70
                 /  \    /  \
               20   40  60   90
                       / \   / \
                      55 65 80 95
```

Trong hình, `30` và mọi hậu duệ của nó đều nhỏ hơn `50`; `70` và mọi hậu duệ của nó đều lớn hơn `50`. Ở dưới nút `70`, toàn bộ cây con trái của nó gồm `55, 60, 65` và đều nhỏ hơn `70`, nhưng vẫn phải lớn hơn tổ tiên `50`.

**Bất biến BST chính là lý do thuật toán tìm kiếm chỉ đi theo một nhánh.** Nếu bất biến bị phá, tìm kiếm có thể thông báo không có khóa dù khóa đó thật sự đang nằm trong cây.

### Khóa và giá trị có vai trò khác nhau

Một **tree map** thường lưu nút dạng `(key, value)`. Thuật toán đi trái/phải bằng cách so sánh **key**, không phải `value`. Ví dụ khóa `"HV01"` có thể gắn điểm `8.0`; thay điểm thành `9.0` không làm thay đổi vị trí nút khi khóa không đổi.

Nếu BST được dùng làm **set**, mỗi nút có thể chỉ cần lưu khóa; thao tác tìm kiếm trả lời **có/không**. Nếu dùng làm **map**, thao tác tìm kiếm còn trả về **giá trị gắn với khóa tìm thấy**.

## 2. Ba kết quả của một lần so sánh tại nút

Giả sử đang đứng tại nút có khóa `current.key` và cần tìm `target`.

| Kết quả so sánh | Quyết định | Vì sao? |
| --- | --- | --- |
| `target == current.key` | **Tìm thấy**, dừng | Nút hiện tại có đúng khóa |
| `target < current.key` | Chỉ tìm trong **cây con trái** | Mọi khóa ở cây con phải đều lớn hơn khóa hiện tại, nên không thể là `target` |
| `target > current.key` | Chỉ tìm trong **cây con phải** | Mọi khóa ở cây con trái đều nhỏ hơn khóa hiện tại, nên không thể là `target` |

Với khóa có thứ tự toàn phần và **không tồn tại khóa trùng theo quy tắc so sánh**, ba trường hợp trên loại trừ nhau và bao phủ mọi kết quả so sánh hợp lệ. Nếu nút hoặc liên kết con cần đi tới là `None`, nghĩa là **cây con tương ứng rỗng**: không tìm thấy khóa.

Một thao tác tra cứu thường trả hai loại kết quả:

- **Found**: có nút mang khóa cần tìm (với map có thể lấy giá trị của nút).
- **Not found**: đường đi bắt buộc theo so sánh kết thúc ở liên kết rỗng.

Một số API chỉ trả `True/False`, một số trả nút hoặc giá trị; điều cốt lõi không thay đổi là **quyết định rẽ nhánh**.

## 3. Ví dụ tìm thấy: lần theo đường đi của khóa 65

Với cây trên, tìm `65`:

```text
                      50        65 > 50 → phải
                        \
                         70     65 < 70 → trái
                        /
                       60       65 > 60 → phải
                         \
                          65    65 = 65 → tìm thấy
```

Bảng vết chạy (*trace*):

| Lượt | Nút đang xét | So sánh | Quyết định |
| ---: | ---: | --- | --- |
| 1 | `50` | `65 > 50` | Đi phải tới `70` |
| 2 | `70` | `65 < 70` | Đi trái tới `60` |
| 3 | `60` | `65 > 60` | Đi phải tới `65` |
| 4 | `65` | `65 == 65` | **Found** |

Đường đi là:

```text
50 → 70 → 60 → 65
```

Thuật toán xem **bốn nút**. Nó không cần xét `30, 20, 40, 55, 90, 80, 95`, vì tại mỗi nhánh đã rẽ, bất biến BST cho phép loại hẳn những nút đó khỏi phạm vi tìm kiếm.

### Một lần tìm khác: khóa 55

```text
55 > 50 → phải
55 < 70 → trái
55 < 60 → trái
55 = 55 → tìm thấy
```

Đường đi `50 → 70 → 60 → 55` có cùng độ sâu với `65` nhưng khác quyết định ở nút `60`. **Đường đi không phải đường bất kỳ**: nó là hệ quả tất định của các so sánh với khóa ở từng nút.

## 4. Ví dụ không tìm thấy: đường đi kết thúc ở cây con rỗng

Hãy tìm khóa `22`:

| Lượt | Nút đang xét | So sánh | Quyết định |
| ---: | ---: | --- | --- |
| 1 | `50` | `22 < 50` | Sang trái đến `30` |
| 2 | `30` | `22 < 30` | Sang trái đến `20` |
| 3 | `20` | `22 > 20` | Sang **phải** |
| 4 | Liên kết `20.right` | `None` | **Not found** |

Đường đi tới các nút thực tế:

```text
50 → 30 → 20 → (cây con phải rỗng)
```

Điều này **không có nghĩa khóa gần nhất là 20** và cũng không có nghĩa thuật toán phải quay lại tìm ở nhánh khác. Vì BST hợp lệ, vị trí có thể chứa `22` nếu khóa đã được chèn sẽ nằm trên đường rẽ quyết định này. Khi liên kết cần đi tới rỗng, không có nút nào mang khóa `22` trong cây.

Ví dụ khác với `75`:

```text
75 > 50 → 70
75 > 70 → 90
75 < 90 → 80
75 < 80 → None → không tìm thấy
```

Một kết quả thất bại vẫn có **đường đi xác định**. Trong ứng dụng, đường đi này còn có ích khi phân tích nơi có thể chèn khóa mới, nhưng **tra cứu không tự tạo nút**.

## 5. Bất biến của chính vòng lặp tìm kiếm

Ngoài bất biến thứ tự của cây, thuật toán tìm kiếm có thể được giải thích bằng một **bất biến vòng lặp**:

> Nếu khóa `target` tồn tại trong cây đầu vào, thì sau mỗi bước chưa tìm thấy, `target` chỉ có thể nằm trong cây con mà biến `current` đang trỏ tới.

Ban đầu, `current` là gốc nên điều kiện đúng. Giả sử ở một nút có khóa `k`:

- Nếu `target < k`, khóa không thể nằm tại nút hiện tại (khác `k`) hoặc trong cây con phải (mọi khóa phải đều `> k`). Vì thế chỉ **cây con trái** cần xét.
- Nếu `target > k`, lập luận đối xứng: chỉ **cây con phải** còn khả năng chứa khóa.
- Nếu `target == k`, kết quả được tìm thấy tại nút hiện tại, không cần duyệt thêm.

Mỗi lần chuyển `current` xuống một con là thu hẹp tập nút có thể chứa đáp án. Nếu cuối cùng `current == None`, cây con còn lại rỗng, nên từ bất biến suy ra **khóa không tồn tại**.

Đây cũng là một chứng minh ngắn về **tính đúng đắn**: thuật toán không bỏ sót khóa hợp lệ, với điều kiện cây đầu vào thỏa bất biến BST và mọi phép so sánh dùng cùng một quy tắc.

### Đường đi có tính duy nhất

Trong BST khóa duy nhất với một bộ so sánh ổn định, tại mỗi nút chỉ có **một quyết định đúng**: dừng, trái hoặc phải. Vì vậy, với cùng cây và cùng khóa cần tìm, ta được cùng một đường đi logic.

Nếu cấu trúc cây bị thay đổi (ví dụ qua chèn, xóa hoặc quay để cân bằng), đường đi có thể **khác trước**, ngay cả khi tập khóa không đổi. Điều được bảo đảm là **kết quả có hay không**, không phải đường đi cố định qua mọi lần tổ chức lại cây.

## 6. Giả mã thuật toán tra cứu BST

Với mỗi nút gồm `key`, `left`, `right`:

```text
SEARCH(root, target):
    current ← root

    while current ≠ null:
        if target == current.key:
            return FOUND(current)

        if target < current.key:
            current ← current.left
        else:
            current ← current.right

    return NOT_FOUND
```

Các điểm cần chú ý:

1. Bắt đầu **ở gốc**, không chọn ngẫu nhiên một nút.
2. So sánh **khóa**, không so sánh địa chỉ đối tượng hoặc giá trị dữ liệu.
3. Khi rẽ trái hay phải, **không quay lại nhánh đã loại**.
4. Chỉ kết luận thiếu khóa khi đến **liên kết rỗng**, không phải khi thấy nút khác khóa.
5. Không thay đổi liên kết hoặc nội dung nút: **tra cứu là thao tác đọc** theo hợp đồng thông thường.

Nếu `root == null` ngay từ đầu, vòng lặp không chạy, hàm trả `NOT_FOUND`. Nếu khóa ở gốc, chỉ cần một lượt so sánh và kết thúc.

## 7. Cài đặt Python: tìm nút và ghi lại đường đi

Mô hình dữ liệu đơn giản dưới đây dùng **khóa số nguyên phân biệt** và giá trị bất kỳ. Để ví dụ dễ theo dõi, ta nối các nút tạo cây đúng như hình ở phần đầu.

```python
class Node:
    def __init__(self, key, value=None, left=None, right=None):
        self.key = key
        self.value = value
        self.left = left
        self.right = right


root = Node(50, "gốc")
root.left = Node(30, "L")
root.right = Node(70, "R")

root.left.left = Node(20, "LL")
root.left.right = Node(40, "LR")

root.right.left = Node(60, "RL")
root.right.right = Node(90, "RR")

root.right.left.left = Node(55, "RLL")
root.right.left.right = Node(65, "RLR")
root.right.right.left = Node(80, "RRL")
root.right.right.right = Node(95, "RRR")
```

### Hàm chỉ tìm nút

```python
def search_node(root, target):
    current = root

    while current is not None:
        if target == current.key:
            return current

        if target < current.key:
            current = current.left
        else:
            current = current.right

    return None


found = search_node(root, 65)
assert found is not None
assert found.key == 65
assert found.value == "RLR"

assert search_node(root, 22) is None
assert search_node(None, 65) is None
```

Hàm trả **đối tượng nút** khi tìm thấy và `None` khi thiếu khóa. Nó không cần biết giá trị của nút có thể bằng `None` hay không: **nút không tồn tại** và **nút tồn tại có giá trị rỗng** là hai trạng thái tách biệt.

### Hàm trả trạng thái, giá trị và vết đường đi

Khi học hoặc gỡ lỗi, ta có thể ghi lại khóa của những nút đã thăm:

```python
def lookup_with_path(root, target):
    current = root
    path = []

    while current is not None:
        path.append(current.key)

        if target == current.key:
            return True, current.value, path

        if target < current.key:
            current = current.left
        else:
            current = current.right

    return False, None, path


assert lookup_with_path(root, 65) == (
    True, "RLR", [50, 70, 60, 65]
)

assert lookup_with_path(root, 22) == (
    False, None, [50, 30, 20]
)

assert lookup_with_path(None, 99) == (
    False, None, []
)
```

Vết `path` chỉ ghi **nút thật đã thăm**, không thêm một khóa giả cho liên kết `None`. Hàm trả `found=False` tách rõ kết quả thất bại khỏi trường hợp một khóa hợp lệ được gắn giá trị `None`:

```python
root.left.value = None

found, value, path = lookup_with_path(root, 30)

assert found is True
assert value is None
assert path == [50, 30]

missing, value, path = lookup_with_path(root, 31)

assert missing is False
assert value is None
assert path == [50, 30, 40]
```

Trong ứng dụng, việc ghi vết có thể cần thiết để giải thích quyết định tìm kiếm, nhưng nó làm tăng bộ nhớ từ `O(1)` lên `O(h)` theo chiều dài đường đi. Nếu chỉ cần kết quả, hãy dùng phiên bản không lưu `path`.

## 8. Phiên bản đệ quy và tương đương với bản lặp

Cùng quy tắc so sánh có thể được viết bằng đệ quy:

```python
def search_recursive(node, target):
    if node is None:
        return None

    if target == node.key:
        return node

    if target < node.key:
        return search_recursive(node.left, target)

    return search_recursive(node.right, target)


assert search_recursive(root, 55).key == 55
assert search_recursive(root, 22) is None
assert search_recursive(None, 22) is None
```

Mỗi lần gọi chỉ thực hiện công việc hằng số ngoài lần gọi tiếp theo, rồi **đi đúng một nhánh**. Không viết:

```python
# Không nên làm thế này cho tìm kiếm BST:
# search_recursive(node.left, target)
# search_recursive(node.right, target)
```

Nếu duyệt cả hai nhánh, ta đang thực hiện **tìm kiếm trên cây nhị phân tổng quát**, không khai thác bất biến BST.

### Khác biệt về bộ nhớ

- **Bản lặp** chỉ cần tham chiếu `current` và các biến cục bộ: `O(1)` bộ nhớ phụ, nếu không lưu đường đi.
- **Bản đệ quy** cần ngăn xếp lời gọi với số frame tỷ lệ chiều dài đường đi: `O(h)`.
- **Bản lưu vết** dùng một list có tối đa `h` khóa: `O(h)`.

Với cây rất sâu, phiên bản đệ quy có thể vượt giới hạn đệ quy của môi trường, ví dụ lỗi `RecursionError` trong Python. Phiên bản lặp thường dễ kiểm soát hơn cho tìm kiếm đơn giản, đặc biệt khi BST không tự cân bằng.

## 9. Phân tích độ phức tạp theo chiều cao

Gọi:

- `n`: số nút trong BST.
- `h`: số nút trên đường dài nhất từ gốc đến một nút lá; cây rỗng có `h = 0`.
- `d`: số cạnh từ gốc đến nút được tìm thấy, nếu có.

Ở mỗi bước, thuật toán chỉ thăm **một nút** và chuyển xuống tối đa **một con**. Vì vậy:

- Nếu tìm thấy khóa ở độ sâu `d`, số nút đã thăm là `d + 1`.
- Nếu không tìm thấy, số nút đã thăm tối đa `h`; sau đó kiểm tra liên kết rỗng.
- Chi phí tra cứu trong trường hợp tổng quát là **`O(h)`**, giả sử mỗi lần so sánh khóa là `O(1)`.

| Cấu trúc cây | Chiều cao `h` | Tra cứu trường hợp xấu nhất |
| --- | --- | --- |
| Cây rỗng | `0` | `O(1)` để kết luận thiếu |
| Cây có một nút | `1` | `O(1)` |
| BST khá cân đối | `O(log n)` | `O(log n)` |
| BST tự cân bằng như AVL hoặc đỏ–đen | Bảo đảm `O(log n)` | Bảo đảm `O(log n)` |
| BST thường bị lệch thành chuỗi | `O(n)` | `O(n)` |

**Không được kết luận “BST tìm kiếm luôn `O(log n)`”.** Bất biến thứ tự giúp loại một cây con, nhưng nếu cây gần như một danh sách liên kết, mỗi bước chỉ loại rất ít nút.

### Vì sao cây cân đối giúp tìm nhanh?

Một cây nhị phân cân đối với `n` nút có chiều cao bậc `log n` vì số nút có thể tăng xấp xỉ gấp đôi khi thêm một tầng. Nếu cây có nhiều nút ở các nhánh tương đối đều nhau, chỉ cần đi qua số tầng nhỏ để tới vị trí một khóa.

Ngược lại, nếu chèn theo thứ tự tăng dần vào BST thường, không cân bằng:

```text
Chèn 10, 20, 30, 40, 50:

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

Tìm `50` phải đi qua `10 → 20 → 30 → 40 → 50`. Tìm `60` cũng phải đi hết chuỗi rồi mới tới `None`. Với `n` nút, trường hợp này có thể mất `Θ(n)` thời gian.

### Phân biệt chi phí đọc khóa và chi phí so sánh khóa

Các phân tích trên thường xem so sánh khóa là hằng số. Với khóa là chuỗi dài độ dài tối đa `L`, phép so sánh từ điển có thể cần đọc tới `O(L)` ký tự; một đường đi dài `h` có thể tốn tới `O(hL)`. Khi dùng comparator phức tạp, hãy tính cả chi phí của comparator trước khi đánh giá hiệu năng.

## 10. Đường đi tìm kiếm và giới hạn từ tổ tiên

Mỗi quyết định rẽ nhánh còn đặt **một giới hạn cho khóa cần tìm**. Khi từ gốc `50` đi phải, ta đã biết khóa mục tiêu `> 50`. Khi từ `70` đi trái, ta biết thêm mục tiêu `< 70`. Để tìm `65`, sau hai bước, khoảng khả dĩ là:

```text
50 < target < 70
```

Khi đứng ở `60` và đi phải, khoảng được thu hẹp thành:

```text
60 < target < 70
```

Ta có thể ghi nhận các khoảng cho đường đi `65`:

| Sau phép so sánh tại | Quyết định | Khoảng còn khả dĩ |
| --- | --- | --- |
| `50` | Đi phải | `(50, +∞)` |
| `70` | Đi trái | `(50, 70)` |
| `60` | Đi phải | `(60, 70)` |
| `65` | Bằng | Kết thúc |

Các khoảng này là cách khác để diễn đạt lý do thuật toán loại cây con: **mọi khóa ngoài khoảng đang xét không thể là mục tiêu trên đường đi này**.

### Ý nghĩa khi không tìm thấy

Tìm `22` cho các khoảng:

```text
Tại 50: 22 < 50  → (−∞, 50)
Tại 30: 22 < 30  → (−∞, 30)
Tại 20: 22 > 20  → (20, 30)
20.right = None
```

Nếu cần **chèn `22`**, một thuật toán chèn BST hợp lệ sẽ đặt nút mới tại liên kết `20.right`, miễn là cây ban đầu đúng bất biến. Tuy nhiên, **thuật toán tra cứu thuần túy** chỉ trả `NOT_FOUND`, không tự cấp phát hoặc nối nút.

Cách diễn đạt bằng khoảng rất hữu ích khi muốn giải thích tính đúng đắn của cả **tra cứu** và **định vị điểm chèn**, nhưng bài toán tra cứu chỉ cần sử dụng đường đi và kết luận hiện diện.

## 11. Quy tắc bằng nhau và bộ so sánh quyết định đường đi

Với khóa số nguyên, ta quen dùng `==`, `<` và `>`. Nhưng khi khóa là chuỗi, tuple, mã định danh hoặc đối tượng, cần thống nhất **một quy tắc so sánh** giữa lúc xây cây và lúc tra cứu.

Đối với một comparator ba chiều `compare(a, b)`, quy ước thường là:

| Giá trị trả về | Ý nghĩa | Hành vi tra cứu `a` tại nút `b` |
| --- | --- | --- |
| Âm | `a` đứng trước `b` | Đi trái |
| Bằng 0 | `a` tương đương `b` | Tìm thấy |
| Dương | `a` đứng sau `b` | Đi phải |

**Tương đương theo comparator** có thể không đồng nghĩa với **cùng đối tượng** hoặc **chuỗi giống hệt từng ký tự**. Ví dụ, nếu cây được xây với comparator **không phân biệt chữ hoa/thường**, `"HV01"` và `"hv01"` có thể được coi là **một khóa logic**.

### Python: chuẩn hóa khóa có chủ đích

Một cách đơn giản để thống nhất chính sách định danh là chuẩn hóa **trước khi chèn và tra cứu**:

```python
def canonical_id(text):
    return text.strip().casefold()


# Các khóa dưới đây là dạng chuẩn hóa, được sắp cùng một quy tắc.
root_codes = Node("hv10", "khóa gốc")
root_codes.left = Node("hv02", "học viên 02")
root_codes.right = Node("hv20", "học viên 20")

assert search_node(root_codes, canonical_id(" HV02 ")).value == "học viên 02"
assert search_node(root_codes, canonical_id("Hv20")).value == "học viên 20"
assert search_node(root_codes, canonical_id("HV99")) is None
```

Các mã trong ví dụ được so sánh theo **thứ tự chuỗi**, không phải số học ở hậu tố. Chẳng hạn, chuỗi `"hv10"` và `"hv2"` có thứ tự từ điển có thể khác thứ tự theo số. Nếu nghiệp vụ cần thứ tự mã theo phần số, phải dùng comparator hoặc khóa chuẩn hóa tương ứng **ngay từ lúc tổ chức cây**.

### Java: tra cứu qua TreeMap với comparator

```java
import java.util.Comparator;
import java.util.Map;
import java.util.TreeMap;

public class Main {
    public static void main(String[] args) {
        Map<String, Integer> scores =
            new TreeMap<>(String.CASE_INSENSITIVE_ORDER);

        scores.put("HV01", 8);
        scores.put("HV20", 9);

        System.out.println(scores.get("hv01")); // 8
        System.out.println(scores.containsKey("Hv20")); // true

        scores.put("hv01", 10); // Cập nhật khóa tương đương
        System.out.println(scores.size()); // 2
    }
}
```

`TreeMap` dựa vào comparator để tìm vị trí khóa. Nếu comparator coi `"HV01"` và `"hv01"` tương đương, tra cứu có thể tìm cùng một mục. Đây là **cam kết của kiểu cụ thể**; không nên suy ra mọi hash map đều dùng cùng bộ so sánh.

### Các điều kiện an toàn của comparator

Một bộ so sánh dùng cho BST cần bảo đảm thứ tự phù hợp, nhất quán và ổn định. Các lỗi dễ gặp:

- **So sánh khác nhau giữa chèn và tra cứu**: cây được tổ chức theo một tiêu chí, nhưng tìm theo tiêu chí khác.
- **Bộ so sánh không có tính nhất quán**: cùng một cặp khóa cho kết quả thay đổi hoặc vi phạm tính bắc cầu.
- **Thay đổi trường khóa sau khi chèn**: một nút có thể nằm sai nhánh theo giá trị mới.
- **Chỉ so sánh một thuộc tính không đủ phân biệt**: hai khóa khác nhau về định danh có thể được xem là tương đương và chỉ lưu một nút.
- **Dùng các giá trị không có thứ tự phù hợp**: ví dụ `NaN` trong so sánh số thực thông thường không thỏa quy tắc ba kết quả như số hữu hạn.

Trong một tree map/set, khi comparator trả về bằng 0, hai khóa có thể được xem là cùng khóa logic. Nếu nghiệp vụ cần phân biệt chúng, cần thêm tiêu chí phá hòa hoặc dùng định danh chính xác hơn.

## 12. Bất biến bị phá: tìm kiếm có thể bỏ sót khóa đang tồn tại

Xem cây sau:

```text
             50
            /  \
          30    70
            \
             60   ← sai: 60 thuộc cây con trái của 50
```

Khi cần tìm `60`, thuật toán quyết định:

```text
60 > 50 → đi phải tới 70
60 < 70 → đi trái tới None
→ NOT_FOUND
```

Nút `60` thật sự tồn tại nhưng lại ở nhánh không thể được truy cập qua quy tắc BST, vì đặt sai so với tổ tiên `50`.

**Bài học:** thuật toán tìm kiếm BST không phải thuật toán tìm kiếm tổng quát trên mọi cây nhị phân. Nó **dựa vào một tiền điều kiện**: cây đã thỏa bất biến thứ tự trên **toàn bộ cây con**.

Một phép kiểm tra chỉ xét quan hệ cha–con ở `30 → 60` sẽ kết luận cục bộ rằng `60 > 30` là đúng. Nhưng điều đó không cứu được cây, vì mọi phần tử ở cây con trái của `50` phải nhỏ hơn `50`.

Khi nhận cây từ nguồn không tin cậy hoặc tự cài thao tác xóa/quay cây, nên có kiểm thử bất biến toàn cây. Tuy nhiên, không cần quét xác minh toàn bộ cây trước **mỗi** lần `search` trong ứng dụng thông thường: làm thế sẽ biến tra cứu nhanh thành xử lý có thể tốn `O(n)`. Thay vào đó, bảo đảm mọi thao tác cập nhật luôn giữ bất biến và dùng kiểm thử để phát hiện lỗi.

## 13. So sánh tra cứu BST với các cách tra cứu khác

| Cấu trúc dữ liệu | Cơ chế chọn vị trí | Chi phí tìm khóa điển hình | Có duyệt khóa theo thứ tự? |
| --- | --- | --- | --- |
| Mảng chưa sắp | Duyệt lần lượt | `O(n)` | Phải sắp thêm nếu cần |
| Mảng đã sắp | So sánh tại vị trí giữa và thu hẹp khoảng chỉ số | `O(log n)` | Có, bằng cách duyệt mảng |
| Hash map/hash set | Tính hash và kiểm tra bằng nhau ở vị trí ứng viên | Trung bình `O(1)` với hash phù hợp | Không mặc định có thứ tự khóa |
| BST thường | So sánh tại nút rồi đi một cây con | `O(h)`, tệ nhất `O(n)` | Có, duyệt in-order |
| BST tự cân bằng | Cùng quy tắc rẽ nhánh và kiểm soát chiều cao | `O(log n)` | Có, duyệt in-order |

**So sánh với tìm nhị phân trên mảng đã sắp:** cả hai đều thu hẹp phạm vi tìm theo so sánh, nhưng tìm nhị phân mảng chọn **chỉ số giữa** của đoạn, còn BST đi theo **các liên kết nút hiện có**. BST thường không tự bảo đảm mỗi nút chia số phần tử gần như đều nhau; đây là lý do nó có thể bị lệch.

**So sánh với hash map:** nếu chủ yếu cần hỏi một khóa cụ thể có tồn tại không, hash map thường có hiệu suất trung bình rất tốt. Nếu còn cần tìm khóa lân cận, liệt kê theo thứ tự hoặc truy vấn khoảng, BST **cân bằng** có những lợi thế riêng.

### Không nhầm BST với heap

Trong **heap**, quy tắc ưu tiên liên hệ cha với con để nhanh chóng lấy phần tử ưu tiên nhất. Nó **không** bảo đảm toàn bộ cây con trái nhỏ hơn nút và cây con phải lớn hơn nút. Do đó, không được dùng thuật toán `target < key → left` trên heap để tìm một khóa tùy ý.

## 14. Những trường hợp biên và lỗi phổ biến

1. **Cây rỗng:** `root is None` phải trả không tìm thấy, không được truy cập `root.key`.
2. **Khóa ở gốc:** tra cứu dừng ngay tại gốc, không cần đi sâu.
3. **Khóa không có:** chỉ dừng khi liên kết phù hợp là rỗng, không tìm sang nhánh đối diện.
4. **So sánh sai chiều:** `target < key` phải đi trái theo quy ước BST đang dùng; đảo trái/phải làm tìm sai.
5. **So sánh giá trị `value` thay vì `key`:** tree map được tổ chức theo khóa; điểm số không quyết định nhánh.
6. **Dùng `is` thay `==`:** đồng nhất đối tượng không phải khái niệm khóa bằng nhau theo giá trị trong nhiều trường hợp.
7. **Trả `None` để biểu thị không có giá trị nhưng không có cờ found:** nhầm khóa thiếu với khóa tồn tại có giá trị `None`.
8. **Giả định toàn bộ cây con chỉ qua hai con trực tiếp:** một hậu duệ sai vị trí vẫn có thể phá điều kiện BST.
9. **Quên thống nhất comparator:** chèn theo mã đã chuẩn hóa nhưng tìm theo mã thô có thể cho kết quả sai.
10. **Đổi khóa của nút sau chèn mà không tổ chức lại cây:** đường rẽ nhánh không còn dẫn tới nút đó.
11. **Cho rằng mọi BST đều tìm `O(log n)`:** cây không cân bằng có thể cao `O(n)`.
12. **Duyệt cả hai cây con trong thao tác BST search:** kết quả có thể vẫn đúng trên cây nhị phân tổng quát, nhưng đánh mất lợi thế tìm theo một đường.
13. **Viết đệ quy khi cây có thể rất sâu:** chú ý giới hạn call stack của ngôn ngữ.
14. **Không xét chi phí so sánh khóa dài:** so sánh chuỗi hoặc đối tượng phức tạp có thể chiếm phần lớn thời gian.
15. **Tra cứu trong khi cây bị sửa đồng thời mà không có cơ chế phù hợp:** một đường đi có thể quan sát các trạng thái không nhất quán; cần đồng bộ hoặc cấu trúc dữ liệu đồng thời có hợp đồng rõ ràng.

## 15. Bài tập tự luyện

**Bài 1.** Dùng cây ví dụ gốc `50`. Viết dãy nút được thăm khi tìm `80`. Ở mỗi nút, xác định dấu so sánh và hướng rẽ.

**Bài 2.** Với cùng cây, hãy mô tả đường đi khi tìm `35`. Thuật toán gặp liên kết rỗng tại nút nào, phía nào?

**Bài 3.** Trên cây ví dụ, tìm `50` cần bao nhiêu lần thăm nút? Tìm `95` cần bao nhiêu lần thăm nút?

**Bài 4.** Giải thích vì sao `target < current.key` cho phép bỏ qua **toàn bộ cây con phải**, không chỉ nút con phải.

**Bài 5.** Cho cây:

```text
         40
        /  \
      20    60
        \
         50
```

Hãy mô tả đường đi khi tìm `50` và giải thích vì sao thuật toán trả không tìm thấy dù có nút `50` trong cây.

**Bài 6.** Một map có khóa `"A"` với giá trị `None`. Vì sao hàm tìm kiếm chỉ trả giá trị không thể phân biệt rõ khóa có mặt hay vắng mặt? Đề xuất kiểu kết quả đúng.

**Bài 7.** Phân biệt thời gian và bộ nhớ phụ giữa tìm kiếm lặp, tìm kiếm đệ quy và tìm kiếm có ghi vết đường đi với chiều cao cây `h`.

**Bài 8.** Nếu chèn `1,2,3,4,5,6` lần lượt vào BST thường không tự cân bằng, hãy tính số nút có thể phải thăm khi tìm `6`. Phân tích độ phức tạp tổng quát theo `n`.

**Bài 9.** Một cây lưu mã học viên không phân biệt hoa/thường bằng comparator phù hợp. Khi tìm `"hv01"`, có cần tìm nút đúng dạng chữ `"hv01"` không? Giải thích điều kiện đủ để coi là tìm thấy.

**Bài 10.** Viết hàm `search_trace(root, target)` trả cả danh sách khóa đã thăm và kết quả `True/False`. Kiểm tra trên cây rỗng, khóa ở gốc, khóa sâu và khóa không tồn tại.

<details>
<summary>Đáp án và gợi ý</summary>

1. `80 > 50` → phải `70`; `80 > 70` → phải `90`; `80 < 90` → trái `80`; bằng khóa. Đường đi: `50, 70, 90, 80`.
2. `35 < 50` → `30`; `35 > 30` → `40`; `35 < 40` → liên kết trái của `40` rỗng. Đường đi thực tế: `50, 30, 40`.
3. Tìm `50` thăm 1 nút. Tìm `95` theo `50 → 70 → 90 → 95`, thăm 4 nút.
4. Theo bất biến BST, **mọi** khóa trong cây con phải đều lớn hơn `current.key`, nên một khóa nhỏ hơn nút hiện tại không thể nằm ở đó.
5. `50 > 40` → phải `60`; `50 < 60` → trái `None`. Nút `50` đang ở cây con trái gốc `40` dù `50 > 40`, nên cây đã phá bất biến BST.
6. Có thể trả `(found, value)`, hoặc trả nút/`None`. Với `found=True, value=None`, khóa tồn tại và có giá trị hợp lệ là `None`.
7. Cả ba tốn `O(h)` thời gian trong trường hợp xấu nhất. Bản lặp không lưu vết dùng `O(1)` bộ nhớ phụ, đệ quy dùng `O(h)` call stack, bản ghi vết dùng `O(h)` cho list đường đi.
8. Cây có thể lệch phải thành chuỗi 6 nút; tìm `6` phải thăm 6 nút. Tổng quát, cây lệch có thời gian tìm xấu nhất `Θ(n)`.
9. Không cần cùng chữ hoa/thường nếu bộ so sánh coi hai khóa tương đương. Khi comparator trả `0` tại một nút, đó là khóa logic cần tìm theo chính sách của tree map.
10. Một cách cài đặt:

```python
def search_trace(root, target):
    visited = []
    current = root
    while current is not None:
        visited.append(current.key)
        if target == current.key:
            return True, visited
        current = current.left if target < current.key else current.right
    return False, visited

assert search_trace(None, 1) == (False, [])
assert search_trace(root, 50) == (True, [50])
assert search_trace(root, 65) == (True, [50, 70, 60, 65])
assert search_trace(root, 22) == (False, [50, 30, 20])
```

</details>

## Ghi nhớ

**Tra cứu BST đi theo đúng một đường từ gốc**, được quyết định bởi phép so sánh `target` với khóa của từng nút: **bằng thì tìm thấy, nhỏ hơn thì rẽ trái, lớn hơn thì rẽ phải**. Thuật toán loại được toàn bộ nhánh không phù hợp nhờ **bất biến thứ tự trên mọi hậu duệ**. Nếu đường đi chạm liên kết rỗng, khóa không tồn tại trong một BST hợp lệ. Chi phí tìm kiếm là **`O(h)`** theo chiều cao cây: thường `O(log n)` nếu cây cân đối, nhưng có thể `O(n)` nếu cây lệch. Hãy thống nhất quy tắc so sánh giữa xây cây và tra cứu, đồng thời phân biệt rõ **khóa thiếu** với **khóa có giá trị rỗng hợp lệ**.

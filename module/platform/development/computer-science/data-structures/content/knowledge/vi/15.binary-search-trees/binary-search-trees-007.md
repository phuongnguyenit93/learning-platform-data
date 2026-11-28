# Xóa nút hai con bằng tiền nhiệm hoặc kế nhiệm

Một hệ thống lưu mã học viên theo thứ tự trong **cây tìm kiếm nhị phân** (*Binary Search Tree – BST*). Khi xóa một nút lá, ta chỉ cần gỡ liên kết. Khi xóa nút có đúng một con, ta có thể nối cha trực tiếp với con còn lại. Nhưng nếu nút cần xóa có **cả con trái lẫn con phải**, việc chọn một con để thay thế sẽ làm **mất cả cây con bên kia**.

Giải pháp cổ điển là tìm một khóa đủ gần theo **thứ tự**, dùng khóa đó thay cho khóa cần xóa, rồi xóa nút chứa khóa thay thế ở vị trí cũ. Hai lựa chọn đối xứng là **tiền nhiệm** (*in-order predecessor*) và **kế nhiệm** (*in-order successor*).

Bài thuộc chương **Cây tìm kiếm nhị phân** trong module cấu trúc dữ liệu. Ta sẽ hiểu chính xác vì sao hai lựa chọn này giữ được bất biến BST, cách tìm và tháo nút thay thế, cách xử lý gốc, cặp khóa–giá trị của map, chi phí `O(h)` và các tình huống dễ gây lỗi.

## 1. Tiền đề: bất biến BST và giả định khóa duy nhất

Với BST lưu các khóa **phân biệt**, tại mỗi nút có khóa `k`:

- **Mọi** khóa trong cây con trái đều **nhỏ hơn** `k`.
- **Mọi** khóa trong cây con phải đều **lớn hơn** `k`.
- Cả hai cây con cũng phải thỏa cùng bất biến tại mọi nút.

```text
                  50
                /    \
              30      80
             /  \    /  \
           20   40  60   90
```

Trong cây trên, tất cả khóa ở trái gốc (`20, 30, 40`) đều nhỏ hơn `50`, tất cả khóa bên phải (`60, 80, 90`) đều lớn hơn `50`.

**Tiền điều kiện quan trọng:** cây đang đúng bất biến BST **trước khi xóa**, và mọi phép tìm, chèn, xóa đều dùng **cùng một quy tắc so sánh khóa**. Thuật toán xóa chuẩn không thể tự sửa một cây đã đặt sai khóa ở đâu đó.

Nếu BST được dùng làm **map**, nút còn chứa `value`; thứ tự được quyết định bởi **key**, không phải value. Khi di chuyển một ánh xạ sang vị trí khác, phải bảo toàn mối liên hệ **khóa ↔ giá trị**.

Trong bài này, một khóa phân biệt tương ứng một nút. Nếu cần các bản sao khóa, có thể lưu `count` hoặc collection giá trị tại nút; quy tắc xử lý trùng phải được xác định riêng.

## 2. Vì sao không thể xóa nút hai con như nút một con?

Xét cây:

```text
          50
         /  \
       30    80
      / \    / \
     20 40  60 90
```

Nếu muốn xóa `50` mà thực hiện:

```text
root = root.left
```

thì toàn bộ nhánh `80, 60, 90` **không còn truy cập được từ gốc**. Nếu chọn `root.right` thay thế, nhánh `30, 20, 40` lại mất.

Tương tự, khi nút cần xóa nằm sâu trong cây, việc nối cha với một con bất kỳ cũng có thể đánh mất con còn lại.

Một thuật toán đúng phải đạt đồng thời:

1. Khóa bị yêu cầu xóa không còn trong tập khóa logic.
2. Mọi khóa khác vẫn hiện diện đúng một lần (với BST khóa duy nhất).
3. Mọi cặp `(key, value)` khác vẫn giữ đúng quan hệ ánh xạ nếu đây là tree map.
4. Bất biến thứ tự của **toàn bộ cây con** tiếp tục đúng.
5. Biến đếm số nút giảm **đúng một** khi xóa thành công.

**Ý tưởng:** chọn một nút mà khóa có thể thế chỗ `50` **nằm giữa** mọi khóa ở trái và mọi khóa ở phải. Tiền nhiệm hoặc kế nhiệm gần nhất theo thứ tự thỏa đúng yêu cầu đó.

## 3. Tiền nhiệm và kế nhiệm theo thứ tự in-order

**Tiền nhiệm nghiêm ngặt của khóa `k`** là khóa **lớn nhất nhỏ hơn `k`** trong tập đang lưu.

**Kế nhiệm nghiêm ngặt của khóa `k`** là khóa **nhỏ nhất lớn hơn `k`** trong tập đang lưu.

Nếu duyệt BST bằng **in-order** (trái → nút → phải), ta nhận dãy tăng nghiêm ngặt; tiền nhiệm và kế nhiệm là **hai phần tử đứng ngay trước và ngay sau** khóa đang xét trong dãy ấy.

Ví dụ:

```text
BST keys: 20, 30, 40, 50, 60, 80, 90
                      ↑
                  muốn xóa 50

predecessor(50) = 40
successor(50)   = 60
```

Đối với **nút có hai con**, cả hai giá trị thay thế đều tồn tại:

- Vì cây con trái không rỗng, **tiền nhiệm** là `maximum(node.left)`: nút phải nhất trong cây con trái.
- Vì cây con phải không rỗng, **kế nhiệm** là `minimum(node.right)`: nút trái nhất trong cây con phải.

| Phương án | Cách tìm | Quan hệ với khóa cần xóa |
| --- | --- | --- |
| **Tiền nhiệm** | Đi vào cây con trái, rồi rẽ **phải liên tục** | Lớn nhất trong tất cả khóa `< k` |
| **Kế nhiệm** | Đi vào cây con phải, rồi rẽ **trái liên tục** | Nhỏ nhất trong tất cả khóa `> k` |

**Không nhầm với nút cha/con trực tiếp.** Nút thay thế có thể nằm nhiều tầng dưới nút cần xóa. Cũng không dùng `k - 1` hay `k + 1`, vì các khóa trong BST không nhất thiết liền nhau.

## 4. Xóa bằng kế nhiệm: phương án lấy nhỏ nhất của cây con phải

Xét cây ví dụ:

```text
                  50
                /    \
              30      80
             /  \    /  \
           20   40  60   90
```

Ta muốn xóa khóa `50`.

**Bước 1 — tìm nút cần xóa.** Đi từ gốc theo so sánh; gặp nút `50` có **hai con**.

**Bước 2 — tìm kế nhiệm.** Từ `50.right = 80`, đi trái tới `60`. Nút `60` không còn con trái, nên nó có khóa nhỏ nhất ở cây con phải của `50`.

**Bước 3 — thay thông tin logic.** Sao chép `(key, value)` từ nút `60` vào vị trí nút `50`; với BST-set chỉ cần sao chép khóa.

**Bước 4 — xóa nút thay thế ở vị trí cũ.** Nút `60` là nút lá trong ví dụ đơn giản này, nên nối `80.left = None`.

Kết quả:

```text
Trước:                     Sau:

         50                         60
        /  \                       /  \
      30    80                   30    80
     / \   / \                  / \     \
    20 40 60 90                20 40    90
```

Trước xóa, thứ tự khóa là:

```text
20, 30, 40, 50, 60, 80, 90
```

Sau xóa:

```text
20, 30, 40, 60, 80, 90
```

Chính xác một khóa `50` biến mất; `60` chỉ xuất hiện **một lần** vì nút `60` ở vị trí cũ đã bị loại.

### Vì sao nút kế nhiệm không có con trái?

Theo định nghĩa, ta tìm `minimum(node.right)` bằng cách đi trái liên tục. Nếu nút tìm được vẫn có con trái, ta còn có thể đi trái để tìm một khóa **nhỏ hơn nó** trong cùng cây con; điều này mâu thuẫn với việc nó là **nhỏ nhất**.

Vậy nút kế nhiệm có **tối đa một con**, và nếu có thì **chỉ có thể là con phải**.

Đó là điểm mấu chốt: **xóa nút có hai con được quy về xóa một nút có 0 hoặc 1 con** mà ta đã biết cách nối lại liên kết.

## 5. Tình huống khó hơn: nút kế nhiệm có con phải

Nút kế nhiệm có thể **không phải lá**. Nó không có con trái, nhưng **có thể có cả một cây con phải**.

```text
Trước khi xóa khóa 50:

                50
              /    \
            30      80
           /  \    /  \
          20  40  60   90
                   \
                    70
                   /
                  65
```

Kế nhiệm của `50` vẫn là `60`: từ `80` đi trái tới `60`; nút `60` không có con trái. Tuy nhiên, `60.right` đang là cây con gốc `70`, chứa cả `65`.

Ta không được chỉ gán `80.left = None` vì sẽ làm mất `70` và `65`.

Cần thực hiện:

1. Sao chép `(key, value)` của `60` vào nút đang mang khóa `50`.
2. **Nối cha của `60` tới con phải của `60`**, tức `80.left = 70`.
3. Giữ toàn bộ liên kết bên dưới `70`.

```text
Sau xóa khóa 50:

                60
              /    \
            30      80
           /  \    /  \
          20  40  70   90
                 /
                65
```

Tại sao đúng? Các khóa `65,70` đều **lớn hơn 60** và **nhỏ hơn 80** trong cây ban đầu. Chuyển liên kết `80.left` từ nút `60` sang `70` vẫn giữ thứ tự của những nút còn lại.

**Ghi nhớ:** khi tháo nút kế nhiệm, phần **còn lại cần nối lên** chính là `successor.right`, không phải một nút mới và cũng không nhất thiết là `None`.

## 6. Trường hợp kế nhiệm là con phải trực tiếp

Nút kế nhiệm đôi khi **chính là `node.right`**, tức không cần đi xuống sâu hơn.

```text
Trước:                     Sau xóa 50:

         50                          70
        /  \                        /  \
      30    70                    30    80
              \
               80
```

Ở đây `70` không có con trái, nên `70` là kế nhiệm của `50`.

Nếu dùng phương án **sao chép khóa và giá trị**:

- Sao chép cặp của `70` lên nút `50`.
- Nút kế nhiệm `70` đang là **con phải trực tiếp** của nút được thay.
- Nối `node.right = successor.right`, tức nút mới mang khóa `70` trỏ phải tới `80`.

Sự phân biệt này ảnh hưởng đến **liên kết phải sửa**:

| Vị trí kế nhiệm | Liên kết đang trỏ tới kế nhiệm | Liên kết thay thế |
| --- | --- | --- |
| Sâu bên trái trong cây con phải | `successor_parent.left` | `successor_parent.left = successor.right` |
| Là con phải trực tiếp của nút cần xóa | `node.right` | `node.right = successor.right` |

**Không thể luôn gán `successor_parent.left`.** Khi kế nhiệm là con phải trực tiếp, `successor_parent` chính là nút cần xóa, và phải sửa liên kết **right**.

## 7. Xóa bằng tiền nhiệm: phương án đối xứng

Thay vì chọn khóa nhỏ nhất từ cây con phải, ta có thể chọn **khóa lớn nhất từ cây con trái**.

```text
Trước khi xóa 50:

                50
              /    \
            30      80
           /  \    /  \
          20   40  60  90
              /
             35
```

Tiền nhiệm của `50` là `40`: đi vào cây con trái `30` rồi rẽ phải tới `40`; `40` không có con phải.

Các bước:

1. Sao chép `(key, value)` của `40` vào nút đang mang khóa `50`.
2. Nút `40` có con trái `35`, nên nối **`30.right = 35`**.
3. Gỡ nút `40` ở vị trí cũ; cây con `35` được giữ nguyên.

```text
Sau khi xóa 50 bằng tiền nhiệm:

                40
              /    \
            30      80
           /  \    /  \
          20   35  60  90
```

Nút tiền nhiệm tìm bằng cách **đi phải liên tục** nên **không có con phải**. Nếu có con, nó **chỉ có thể là con trái**.

### Trường hợp tiền nhiệm là con trái trực tiếp

```text
Trước:

        50
       /  \
     30    80
    /
   20

Sau xóa 50:

        30
       /  \
     20    80
```

Nút tiền nhiệm `30` là con trái trực tiếp và có con trái `20`. Sau khi sao chép thông tin `30` lên nút gốc, phải nối `node.left = predecessor.left`.

### Bảng đối chiếu hai chiến lược

| Chi tiết | Chọn **kế nhiệm** | Chọn **tiền nhiệm** |
| --- | --- | --- |
| Bắt đầu tìm thay thế | `node.right` | `node.left` |
| Hướng đi liên tục | **Trái** | **Phải** |
| Nút thay thế không có | Con trái | Con phải |
| Cây con có thể còn lại | `successor.right` | `predecessor.left` |
| Nếu thay thế sâu | Sửa `parent_of_successor.left` | Sửa `parent_of_predecessor.right` |
| Nếu thay thế trực tiếp | Sửa `node.right` | Sửa `node.left` |
| Bất biến cuối cùng | Trái nhỏ hơn < khóa mới < phải lớn hơn | Trái nhỏ hơn < khóa mới < phải lớn hơn |

Cả hai đều đúng với BST khóa duy nhất; cây tạo ra **có thể có hình dạng khác nhau**, nhưng tập khóa logic sau xóa phải giống nhau.

## 8. Hai chiến lược hiện thực: sao chép cặp hay ghép lại nút

Có hai cách phổ biến để đưa khóa thay thế về vị trí của nút cần xóa.

### Cách A — sao chép khóa và giá trị

Ta giữ **đối tượng nút ban đầu** ở nguyên chỗ, nhưng đổi `key` và `value` của nó bằng cặp lấy từ nút kế nhiệm/tiền nhiệm; sau đó xóa nút thay thế ở vị trí cũ.

Ưu điểm:

- Mã ngắn và dễ giảng giải.
- Chỉ cần tìm nút thay thế, ghi đè cặp và nối lại **một liên kết**.
- Không cần sắp xếp lại cây từ đầu.

Nhược điểm:

- **Định danh đối tượng nút** và **định danh khóa** không còn gắn cố định với nhau. Nếu bên ngoài giữ tham chiếu trực tiếp tới nút, việc gán lại khóa có thể gây bất ngờ.
- Với **tree map**, nếu chỉ sao chép khóa mà **quên sao chép giá trị**, ánh xạ sẽ sai.
- Khi cây có metadata gắn với nút (con trỏ cha, chiều cao, kích thước cây con, màu đỏ–đen...), thuật toán thực tế phải cập nhật những trường liên quan theo hợp đồng.

### Cách B — di chuyển/transplant cả đối tượng nút

Ta tháo nút kế nhiệm/tiền nhiệm khỏi vị trí cũ, rồi **đưa chính đối tượng nút ấy** vào vị trí nút cần xóa, nối lại cây con trái và phải đúng thứ tự.

Ưu điểm:

- Giữ nguyên cặp `(key, value)` trong đối tượng thay thế; phù hợp khi cần quản lý danh tính nút theo chính sách rõ.
- Có thể tránh thay đổi khóa của một nút còn đang tồn tại.

Nhược điểm:

- Phải xử lý **nhiều liên kết hơn**, đặc biệt khi nút thay thế là con trực tiếp và khi nút thay thế ở sâu.
- Với con trỏ `parent` hoặc các cấu trúc tự cân bằng, còn cần cập nhật metadata và liên kết phụ.

**Phạm vi mã của bài:** ta triển khai **Cách A**, để tập trung vào nguyên lý successor/predecessor và kết nối với bài xóa nút 0 hoặc 1 con. Không nên âm thầm giả định những tham chiếu bên ngoài tới các đối tượng nút sẽ giữ ngữ nghĩa trước và sau phép xóa.

## 9. Thuật toán tổng quát: tìm nút, thay cặp, tháo nút thay thế

Một hàm `remove(key)` cho BST-map có thể chia theo số con của nút được tìm thấy.

**Giai đoạn 1 — tìm nút cần xóa theo khóa:**

- Đi từ gốc.
- Ghi nhớ `parent` của nút đang xét.
- Nếu không tìm thấy, trả thất bại và không sửa cây.

**Giai đoạn 2 — chọn trường hợp:**

- **0 con:** thay liên kết từ cha/gốc bằng `None`.
- **1 con:** thay liên kết từ cha/gốc bằng gốc của con duy nhất.
- **2 con:** chọn kế nhiệm hoặc tiền nhiệm, sao chép **cả khóa và giá trị**, rồi xóa nút thay thế ở vị trí cũ bằng quy tắc 0 hoặc 1 con.

**Giai đoạn 3 — cập nhật số lượng:**

- Chỉ giảm `size` **một lần** sau khi xóa thành công.
- Không giảm hai lần vì về mặt logic chỉ có **một khóa** bị loại khỏi map.

### Giả mã dùng kế nhiệm

```text
DELETE(root, target):
    (parent, node) = SEARCH_WITH_PARENT(root, target)
    if node == null:
        return (root, false)

    if node.left != null and node.right != null:
        successor_parent = node
        successor = node.right

        while successor.left != null:
            successor_parent = successor
            successor = successor.left

        node.key   = successor.key
        node.value = successor.value

        remaining = successor.right
        if successor_parent == node:
            node.right = remaining
        else:
            successor_parent.left = remaining
    else:
        remaining = node.left if node.left != null else node.right
        if parent == null:
            root = remaining
        else if parent.left is node:
            parent.left = remaining
        else:
            parent.right = remaining

    return (root, true)
```

Đối với **tiền nhiệm**, đổi:

- `node.right` thành `node.left` ở bước bắt đầu.
- `successor.left` thành `predecessor.right` trong vòng tìm cực trị.
- `remaining = successor.right` thành `remaining = predecessor.left`.
- Các nhánh nối liên kết trái/phải đối xứng.

**Quan trọng:** hai con có thể được xử lý mà không **đệ quy xóa chính khóa vừa sao chép**. Nếu gọi lại `remove(target)` sau khi đã ghi đè, khóa `target` không còn ở nút ban đầu; điều đó có thể dẫn tới tìm sai nút. Ta đã biết **chính xác nút thay thế và nút cha của nó**, nên có thể tháo trực tiếp.

## 10. Cài đặt Python đầy đủ cho BST-map

Đoạn mã sau dùng **khóa số nguyên phân biệt** và cho phép `value` tùy ý, kể cả `None`. Phương thức `delete` hỗ trợ `strategy="successor"` hoặc `strategy="predecessor"`.

### Lớp Node và BSTMap

```python
class Node:
    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.left = None
        self.right = None


class BSTMap:
    def __init__(self):
        self.root = None
        self._size = 0

    def put(self, key, value):
        """Thêm mới hoặc cập nhật; trả True nếu vừa tạo nút."""
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

    def find(self, key):
        """Trả (found, value), tránh nhập nhằng value=None."""
        current = self.root
        while current is not None:
            if key == current.key:
                return True, current.value
            current = (
                current.left if key < current.key else current.right
            )
        return False, None

    def delete(self, key, strategy="successor"):
        """Xóa một khóa bằng successor hoặc predecessor; trả bool."""
        if strategy not in ("successor", "predecessor"):
            raise ValueError("strategy phải là successor hoặc predecessor")

        parent = None
        current = self.root

        # 1. Tìm đúng nút bằng phép so sánh khóa.
        while current is not None and key != current.key:
            parent = current
            current = (
                current.left if key < current.key else current.right
            )

        if current is None:
            return False

        # 2. Nếu có hai con: thay cặp (key,value), rồi tháo
        #    nút cực trị (nút cực trị có tối đa một con).
        if current.left is not None and current.right is not None:
            replacement_parent = current

            if strategy == "successor":
                replacement = current.right
                while replacement.left is not None:
                    replacement_parent = replacement
                    replacement = replacement.left

                current.key = replacement.key
                current.value = replacement.value
                child = replacement.right

                if replacement_parent is current:
                    current.right = child
                else:
                    replacement_parent.left = child

            else:  # strategy == "predecessor"
                replacement = current.left
                while replacement.right is not None:
                    replacement_parent = replacement
                    replacement = replacement.right

                current.key = replacement.key
                current.value = replacement.value
                child = replacement.left

                if replacement_parent is current:
                    current.left = child
                else:
                    replacement_parent.right = child

        else:
            # 3. Trường hợp 0 hoặc 1 con: nối cha/gốc tới child.
            child = (
                current.left if current.left is not None
                else current.right
            )

            if parent is None:
                self.root = child
            elif parent.left is current:
                parent.left = child
            else:
                parent.right = child

        # Chỉ loại một mục logic, kể cả khi phải sao chép khóa.
        self._size -= 1
        return True

    def size(self):
        return self._size

    def inorder_items(self):
        """Duyệt cặp (key,value) theo thứ tự khóa tăng dần."""
        result = []
        pending = []
        current = self.root

        while pending or current is not None:
            while current is not None:
                pending.append(current)
                current = current.left

            current = pending.pop()
            result.append((current.key, current.value))
            current = current.right

        return result
```

### Những điểm không được bỏ qua

- Phương thức `put` chỉ tạo nút mới nếu **khóa chưa tồn tại**; `find` phân biệt `(True, None)` với `(False, None)`.
- `delete` kiểm tra chiến lược trước khi sửa cây.
- Với nút **hai con**, `replacement_parent` bắt đầu từ `current` để xử lý đúng trường hợp nút thay thế là con trực tiếp.
- Với kế nhiệm, `child` là **con phải** của nút thay thế; với tiền nhiệm, `child` là **con trái**.
- Chỉ sao chép **`key` và `value`**, không tùy tiện sao chép hai liên kết `left/right` từ nút thay thế.
- Không dùng biến `parent` của nút cần xóa để tháo nút thay thế: `replacement_parent` mới là cha **tại vị trí cũ** của nút thay thế.
- `_size` giảm đúng một lần khi xóa thành công.
- Đoạn mã không lưu `parent pointer` hoặc thông tin cân bằng; nếu bổ sung những trường này phải đồng bộ chúng.

**Giới hạn:** đây là BST thường **không tự cân bằng**, không có bảo vệ truy cập đồng thời và không bảo đảm thời gian `O(log n)` trong trường hợp cây lệch.

## 11. Kiểm thử chiến lược kế nhiệm

### Kiểm thử kế nhiệm ở sâu và có con phải

Tạo một BST-map có cặp khóa–giá trị:

```python
def make_demo():
    tree = BSTMap()
    pairs = [
        (50, "xoa"), (30, "ba-muoi"), (80, "tam-muoi"),
        (20, "hai-muoi"), (40, "bon-muoi"),
        (60, "sau-muoi"), (90, "chin-muoi"),
        (70, "bay-muoi"), (65, "sau-muoi-lam"),
    ]
    for key, value in pairs:
        tree.put(key, value)
    return tree


tree = make_demo()
before = tree.inorder_items()

assert [key for key, _ in before] == [
    20, 30, 40, 50, 60, 65, 70, 80, 90
]
assert tree.size() == 9
assert tree.delete(50, strategy="successor") is True

assert [key for key, _ in tree.inorder_items()] == [
    20, 30, 40, 60, 65, 70, 80, 90
]
assert tree.find(50) == (False, None)
assert tree.find(60) == (True, "sau-muoi")
assert tree.find(65) == (True, "sau-muoi-lam")
assert tree.find(70) == (True, "bay-muoi")
assert tree.size() == 8
```

Trong thử nghiệm này:

- Nút cần xóa `50` có hai con `30` và `80`.
- Kế nhiệm `60` nằm **sâu ở nhánh trái của `80`**.
- Nút `60` có **con phải `70`**, trong đó còn có `65`.
- Sau xóa, các khóa `65` và `70` vẫn có mặt, còn cặp `60 → "sau-muoi"` được bảo toàn.

### Kiểm thử kế nhiệm là con phải trực tiếp

```python
direct = BSTMap()
for key in (50, 30, 70, 80):
    direct.put(key, "v" + str(key))

assert direct.delete(50, "successor") is True
assert direct.root.key == 70
assert direct.root.right.key == 80
assert [k for k, _ in direct.inorder_items()] == [30, 70, 80]
assert direct.size() == 3
```

Đây là ca đặc biệt dễ làm sai nếu chỉ biết sửa `replacement_parent.left`.

## 12. Kiểm thử chiến lược tiền nhiệm

### Tiền nhiệm ở sâu và có con trái

```python
pred_tree = BSTMap()
for key in (50, 30, 80, 20, 40, 60, 90, 35):
    pred_tree.put(key, "v" + str(key))

assert pred_tree.delete(50, "predecessor") is True

assert pred_tree.root.key == 40
assert [k for k, _ in pred_tree.inorder_items()] == [
    20, 30, 35, 40, 60, 80, 90
]
assert pred_tree.find(35) == (True, "v35")
assert pred_tree.find(40) == (True, "v40")
assert pred_tree.find(50) == (False, None)
assert pred_tree.size() == 7
```

Đường tìm tiền nhiệm là `50.left = 30`, rồi đi phải tới `40`. Nút `40` có con trái `35`, nên phải nối `30.right = 35` sau khi sao chép cặp `(40, "v40")` vào nút gốc.

### Tiền nhiệm là con trái trực tiếp

```python
direct_pred = BSTMap()
for key in (50, 30, 80, 20):
    direct_pred.put(key, "v" + str(key))

assert direct_pred.delete(50, "predecessor") is True
assert direct_pred.root.key == 30
assert direct_pred.root.left.key == 20
assert [k for k, _ in direct_pred.inorder_items()] == [
    20, 30, 80
]
```

Nếu chỉ sửa `replacement_parent.right` mà không xét tiền nhiệm là con trái trực tiếp, cây này sẽ bị sai liên kết.

### Hai cách có thể cho hai cây khác hình dạng

Giả sử cùng một tập khóa chứa `30, 40, 50, 60, 80`. Khi xóa `50`:

- Chọn **tiền nhiệm** làm nút giữ vị trí gốc có khóa `40`.
- Chọn **kế nhiệm** làm nút giữ vị trí gốc có khóa `60`.

Hai hình dạng khác nhau đều có thể hợp lệ, nhưng dãy in-order cuối phải cùng bằng:

```text
30, 40, 60, 80
```

**Đừng đánh giá tính đúng chỉ bằng hình dáng cây.** Điều cần kiểm tra là tập khóa, cặp dữ liệu, liên kết và bất biến thứ tự.

## 13. Xóa gốc, khóa thiếu và trường hợp rỗng

Một thuật toán xóa tổng quát phải xử lý thêm những tình huống không liên quan trực tiếp đến việc chọn tiền nhiệm/kế nhiệm.

### Xóa nút gốc có hai con

Mã `BSTMap.delete` xử lý bình thường vì nút gốc có thể được **ghi đè cặp bằng kế nhiệm/tiền nhiệm**, còn liên kết gốc tiếp tục trỏ tới đối tượng nút cũ (chỉ khóa/value bên trong nó thay đổi).

```python
root_case = BSTMap()
for k in (50, 30, 70):
    root_case.put(k, "v" + str(k))

assert root_case.delete(50, "successor")
assert root_case.root.key == 70
assert [k for k, _ in root_case.inorder_items()] == [30, 70]
```

### Xóa gốc chỉ có một con hoặc không có con

Với nút gốc có **tối đa một con**, đoạn mã chuyển sang nhánh thường:

```python
single = BSTMap()
single.put(42, None)
assert single.delete(42) is True
assert single.root is None
assert single.size() == 0

one_child = BSTMap()
one_child.put(42, "x")
one_child.put(30, "y")
assert one_child.delete(42, "predecessor") is True
assert one_child.root.key == 30
assert one_child.size() == 1
```

Tại đây, `parent is None` nên phải cập nhật `self.root = child`. Nếu nút có **hai con**, nhánh sao chép cặp không dùng `parent` để đổi gốc; nếu nút có **0 hoặc 1 con**, bắt buộc phải xét trường hợp không có cha.

### Khóa không tồn tại

```python
missing = make_demo()
old_items = missing.inorder_items()
old_size = missing.size()

assert missing.delete(12345) is False
assert missing.inorder_items() == old_items
assert missing.size() == old_size
```

**Xóa thất bại không được làm biến đổi cây hoặc giảm `size`.**

### Khóa có giá trị None

```python
nullable = BSTMap()
nullable.put(50, None)
nullable.put(30, "trai")
nullable.put(70, "phai")

assert nullable.find(50) == (True, None)
assert nullable.delete(50, "successor")
assert nullable.find(50) == (False, None)
assert nullable.find(70) == (True, "phai")
assert nullable.size() == 2
```

Phải xác định sự hiện diện bằng **khóa**, không suy từ `node.value is None` rằng nút không tồn tại.

## 14. Vì sao lựa chọn thay thế giữ bất biến BST?

Giả sử nút có khóa `k` và hai cây con đều không rỗng. Ta dùng **kế nhiệm** `s`:

```text
s = min(keys trong cây con phải)
```

Vì BST ban đầu hợp lệ:

1. **Mọi khóa ở cây con trái đều `< k`**, và do `s` nằm trong cây con phải nên `k < s`. Suy ra mọi khóa trái đều **`< s`**.
2. Theo định nghĩa `s` nhỏ nhất trong cây con phải, **mọi khóa còn lại** ở cây con phải đều **`> s`** (giả định khóa phân biệt).
3. Thay khóa `k` bằng `s` và **xóa đúng nút cũ mang `s`** khiến mọi khóa bên trái vẫn nhỏ hơn gốc mới, còn mọi khóa bên phải vẫn lớn hơn gốc mới.
4. Khi tháo nút chứa `s`, nó chỉ có thể có **con phải**. Các khóa trong cây con phải ấy trước đó đều nằm trong cùng những giới hạn từ tổ tiên nên nối chúng lên vị trí nút `s` không phá thứ tự.
5. Tất cả các cây con còn lại giữ nguyên thứ tự nội bộ.

Vậy BST sau xóa có tập khóa logic là **tập cũ trừ `{k}`** và vẫn thỏa bất biến.

### Lập luận đối xứng khi chọn tiền nhiệm

Với `p = max(keys trong cây con trái)`:

- Mọi khóa còn lại trong cây con trái đều **`< p`**.
- Mọi khóa bên phải đều **`> k > p`**.
- Nút chứa `p` không có con phải, chỉ có thể có con trái; nối con trái ấy lên chỗ nút `p` vẫn giữ các giới hạn.
- Sao chép `p` vào vị trí của `k` và gỡ nút chứa `p` ở chỗ cũ cho cây còn đúng thứ tự.

**Bất biến phải đúng ở mọi tổ tiên**, không chỉ tại nút bị xóa. Vì tất cả nút thay thế vốn đã nằm trong khoảng hợp lệ của vị trí gốc và các cây con được nối lại vẫn nằm trong các khoảng của tổ tiên, lập luận áp dụng cho toàn cây.

### Lưu ý với bản đồ khóa–giá trị

Chỉ chứng minh thứ tự khóa là **chưa đủ** cho BST-map. Cần thêm bất biến:

> Mỗi khóa còn lại phải tiếp tục gắn với **đúng giá trị của khóa ấy trước khi xóa**.

Vì thế trong chiến lược sao chép phải ghi đè **cả `node.key` và `node.value`** bằng thông tin của nút thay thế. Nếu chỉ đổi `key`, một mã học viên có thể nhận nhầm điểm của học viên bị xóa.

## 15. Độ phức tạp: tìm nút, tìm cực trị, nối liên kết

Đặt `n` là số nút phân biệt và `h` là chiều cao BST, tính theo số nút từ gốc tới lá xa nhất. Giả định mỗi lần so sánh khóa và cập nhật liên kết có chi phí hằng số.

| Giai đoạn | Chi phí thời gian | Bộ nhớ phụ bản lặp |
| --- | --- | --- |
| Tìm nút cần xóa theo khóa | `O(h)` | `O(1)` |
| Xác định có 0, 1 hay 2 con | `O(1)` | `O(1)` |
| Tìm kế nhiệm trong cây con phải | `O(h)` | `O(1)` |
| Tìm tiền nhiệm trong cây con trái | `O(h)` | `O(1)` |
| Sao chép cặp và nối liên kết | `O(1)` | `O(1)` |
| **Toàn bộ delete** | **`O(h)`** | **`O(1)`** |
| Kiểm tra toàn cây sau xóa để test | `O(n)` | `O(h)` nếu duyệt DFS |

Hai lần đi theo đường cao tối đa `h` vẫn là **`O(h) + O(h) = O(h)`**.

### Cây cân đối so với cây lệch

- Với BST có chiều cao `h = O(log n)`, thao tác xóa bằng tiền nhiệm/kế nhiệm mất `O(log n)`.
- Với BST không cân bằng, `h` có thể bằng `Θ(n)`, nên xóa mất tới `O(n)`.
- Chi phí thao tác **không phải `O(n)` chỉ vì cần xóa một nút có hai con**; thuật toán chỉ đi theo các đường tìm trong cây, không quét toàn bộ các nút.

Bản đệ quy có thể dùng `O(h)` ngăn xếp lời gọi, còn bản lặp minh họa dùng `O(1)` bộ nhớ phụ, không tính bộ nhớ các nút đã lưu sẵn.

### BST có tự cân bằng

Mã trong bài chỉ bảo toàn bất biến **thứ tự BST**, không thực hiện bước cân bằng.

Với **AVL** hoặc **cây đỏ–đen**, xóa có thể cần cập nhật chiều cao, màu và thực hiện phép quay để duy trì bất biến bổ sung. Đặc biệt, có thể phải theo dõi **đường đi từ nút bị tháo vật lý lên các tổ tiên** chứ không chỉ đường tới khóa ban đầu. Không nên lấy mã BST thường rồi giả định nó là mã xóa đầy đủ cho cây tự cân bằng.

## 16. Rủi ro liên kết, đối tượng và bộ nhớ

### Không làm mất cây con của nút thay thế

Nút kế nhiệm không có con trái nhưng có thể có **con phải**; nút tiền nhiệm không có con phải nhưng có thể có **con trái**.

Nếu gỡ nút cực trị bằng cách luôn nối tới `None`, dữ liệu trong cây con còn lại sẽ mất khỏi cây dù thuật toán không báo lỗi.

### Không tạo bản sao khóa

Sau khi sao chép `successor.key` vào nút cần xóa, phải **tháo nút successor ở chỗ cũ**. Nếu bỏ qua bước này, hai nút có cùng khóa sẽ tồn tại, phá quy tắc BST khóa duy nhất.

### Không chỉ sao chép khóa mà quên giá trị

```text
Trước:  (50, "học viên A")  và  (60, "học viên B")

Xóa 50 bằng successor 60:
  nút giữ vị trí cũ phải thành (60, "học viên B"),
  không được thành             (60, "học viên A").
```

### Không nhầm con trỏ cha của hai vị trí

`parent` là cha của **nút cần xóa**; `replacement_parent` là cha của **nút được chọn làm kế nhiệm/tiền nhiệm**. Trong trường hợp sâu, chúng thường là hai nút khác nhau. Khi tháo nút thay thế, phải sửa đúng liên kết từ `replacement_parent`.

### Nút cũ và tham chiếu từ bên ngoài

Với chiến lược sao chép cặp, một tham chiếu bên ngoài tới đối tượng nút ban đầu sẽ thấy **khóa và giá trị thay đổi**, dù nút đó vẫn nằm tại chỗ. Một tham chiếu bên ngoài tới nút thay thế cũ có thể trỏ tới đối tượng đã bị tháo khỏi cây. Vì thế thư viện thường nên **đóng gói nút nội bộ**, không để người dùng dựa vào danh tính đối tượng nút qua thao tác xóa.

### Con trỏ parent và bộ nhớ được quản lý thủ công

Nếu mỗi nút có `parent`, khi nối `child` vào `replacement_parent` cần cập nhật `child.parent` cho đúng. Khi thực hiện transplant, còn phải cập nhật nhiều liên kết cha–con khác.

Trong Python, bộ gom rác và bộ đếm tham chiếu quản lý vòng đời đối tượng theo runtime; xóa một nút khỏi BST **không bảo đảm** bộ nhớ được thu hồi ngay nếu còn tham chiếu khác. Trong C/C++, cần phân biệt rõ **quyền sở hữu** nút và việc giải phóng để không rò rỉ bộ nhớ hoặc giải phóng nhầm cây con còn sống.

## 17. Kiểm thử độc lập với dictionary tham chiếu

Để kiểm tra tính đúng, ta có thể dùng Python `dict` làm mô hình ánh xạ và đối chiếu tập khóa/cặp giá trị sau mỗi phép xóa.

Hàm kiểm tra BST theo **biên từ tổ tiên** tránh lỗi chỉ so cha và hai con trực tiếp:

```python
def validate_bst(root):
    """Kiểm tra khóa nguyên phân biệt và bất biến thứ tự."""
    pending = [(root, None, None)]

    while pending:
        node, low, high = pending.pop()
        if node is None:
            continue

        if low is not None and node.key <= low:
            return False
        if high is not None and node.key >= high:
            return False

        pending.append((node.left, low, node.key))
        pending.append((node.right, node.key, high))

    return True


reference = {
    50: "xoa", 30: "ba-muoi", 80: "tam-muoi",
    20: "hai-muoi", 40: "bon-muoi",
    60: "sau-muoi", 90: "chin-muoi",
    70: "bay-muoi", 65: "sau-muoi-lam",
}

for strategy in ("successor", "predecessor"):
    t = BSTMap()

    for key, value in reference.items():
        t.put(key, value)

    expected = dict(reference)

    for deleted_key in (50, 30, 80, 20, 9999):
        expected_removed = deleted_key in expected
        removed = t.delete(deleted_key, strategy)
        assert removed == expected_removed

        if expected_removed:
            del expected[deleted_key]

        assert validate_bst(t.root)
        assert t.inorder_items() == sorted(expected.items())
        assert t.size() == len(expected)

        for key, value in expected.items():
            assert t.find(key) == (True, value)
```

**Điểm quan trọng:** kiểm thử không chỉ so số nút hoặc dãy khóa. Nó còn kiểm tra **từng cặp khóa–giá trị**, giúp phát hiện lỗi sao chép khóa nhưng quên giá trị của kế nhiệm/tiền nhiệm.

### Một số kịch bản bổ sung

- Xóa nút hai con ở **gốc**, rồi xóa nút hai con ở vị trí **không phải gốc**.
- Kế nhiệm/tiền nhiệm là **con trực tiếp** so với ở **sâu trong cây con**.
- Nút thay thế là **lá** hoặc có **đúng một con được phép**.
- Xóa nút có **0 hoặc 1 con** và xóa một khóa **không tồn tại**.
- Chèn lại một khóa đã xóa rồi kiểm tra `find`.
- Giá trị hợp lệ là `None` hoặc `0`.
- BST **lệch hoàn toàn** và BST tương đối cân đối.
- Lặp lại phép xóa cho nhiều thứ tự khác nhau rồi so với dictionary tham chiếu.

Một bộ kiểm thử như trên đánh giá **tính đúng logic** của ví dụ; chưa phải benchmark hoặc quy trình Content QA học thuật của toàn module.

## 18. Ví dụ ứng dụng: xóa khóa học nhưng giữ đúng các hồ sơ khác

Giả sử cây chứa các ánh xạ:

```text
         "CS200"
         /      \
      "CS100"   "CS300"
               /      \
          "CS250"   "CS400"
```

Khi xóa khóa `"CS200"`, ta có thể lấy:

- **Kế nhiệm:** `"CS250"` là khóa nhỏ nhất của cây con phải.
- **Tiền nhiệm:** `"CS100"` là khóa lớn nhất của cây con trái.

Nếu dùng kế nhiệm, phải đưa **toàn bộ ánh xạ của `"CS250"`**, bao gồm thông tin khóa học, vào vị trí của `"CS200"`, rồi gỡ vị trí cũ của `"CS250"`. Mọi khóa `"CS100"`, `"CS300"`, `"CS400"` vẫn phải tra cứu được cùng thông tin trước đó.

Đây là lý do nên kiểm thử **nghiệp vụ của map** song song với bất biến BST: cây vẫn có thể in ra dãy khóa tăng dần nhưng dữ liệu bên trong bị gắn sai khóa nếu sao chép không đầy đủ.

Trong hệ thống sản xuất, nếu cần tree map có xóa đầy đủ và hiệu năng bảo đảm, nên dùng thư viện cây cân bằng đã kiểm thử hoặc triển khai riêng có kiểm thử sâu, không chỉ sao chép một đoạn mã minh họa.

## 19. Sai lầm thường gặp

1. **Chọn ngẫu nhiên một con để thay nút hai con.** Làm mất nhánh còn lại.
2. **Lấy minimum của cây con trái** làm tiền nhiệm. Tiền nhiệm phải là **maximum** của cây con trái.
3. **Lấy maximum của cây con phải** làm kế nhiệm. Kế nhiệm phải là **minimum** của cây con phải.
4. **Dùng `key ± 1`** thay vì tìm cực trị thực sự trong cây con; khóa không nhất thiết liền nhau.
5. **Sao chép khóa mà quên giá trị** trong tree map, làm sai liên kết dữ liệu.
6. **Sao chép cặp thay thế nhưng quên tháo nút thay thế cũ**, khiến khóa bị trùng.
7. **Xóa nút kế nhiệm bằng cách luôn gán `None`**, đánh mất cây con phải nếu tồn tại.
8. **Xóa nút tiền nhiệm bằng cách luôn gán `None`**, đánh mất cây con trái nếu tồn tại.
9. **Luôn sửa `replacement_parent.left` cho kế nhiệm**, bỏ sót trường hợp kế nhiệm chính là `node.right`.
10. **Luôn sửa `replacement_parent.right` cho tiền nhiệm**, bỏ sót trường hợp tiền nhiệm chính là `node.left`.
11. **Dùng `parent` của nút cần xóa thay cho `replacement_parent`**, sửa sai liên kết ở tầng trên.
12. **Giảm `size` hai lần** do vừa thay cặp vừa tháo nút, trong khi chỉ một khóa logic bị xóa.
13. **Giảm `size` khi khóa không tồn tại**, làm số nút báo cáo sai.
14. **Không cập nhật gốc** khi xóa một nút gốc có 0 hoặc 1 con.
15. **Chỉ kiểm tra hai con trực tiếp của từng nút** mà bỏ giới hạn tổ tiên khi xác minh BST.
16. **Nhầm cây BST đúng thứ tự với cây tự cân bằng**; cần xử lý điều kiện AVL/đỏ–đen riêng.
17. **Dựa vào định danh đối tượng nút** dù hiện thực sao chép khóa sang đối tượng khác.
18. **Sửa khóa bên trong nút tùy tiện** ở ngoài thuật toán có kiểm soát, khiến vị trí trong cây không còn hợp lệ.
19. **Dùng comparator khác lúc tìm nút và lúc tìm cực trị**, khiến đường đi không phản ánh thứ tự ban đầu.
20. **Sửa cây từ nhiều luồng mà không đồng bộ**, làm liên kết có thể bị quan sát ở trạng thái chưa nhất quán.

## 20. Tự luyện tập

**Bài 1.** Với cây:

```text
        50
       /  \
     30    80
    / \   /  \
   20 40 60  90
```

Hãy tìm tiền nhiệm và kế nhiệm của `50`. Vẽ cây sau khi xóa `50` bằng **kế nhiệm**.

**Bài 2.** Trên cây của bài 1, hãy xóa `50` bằng **tiền nhiệm**. Dãy khóa in-order cuối có khác phương án kế nhiệm không?

**Bài 3.** Vì sao nút **nhỏ nhất trong cây con phải** không thể có con trái? Nó có thể có con phải không?

**Bài 4.** Vì sao nút **lớn nhất trong cây con trái** không thể có con phải? Nếu nó có con trái, phải nối liên kết nào khi tháo nút đó?

**Bài 5.** Một nút cần xóa có con phải `70` và `70` không có con trái, nhưng `70.right` là `80`. Nếu chọn kế nhiệm, nút nào mang khóa thay thế và cần cập nhật liên kết gì?

**Bài 6.** Nút cần xóa `50` có cây con phải gốc `80`, con trái của `80` là `60`, con phải của `60` là `70`. Khi tháo kế nhiệm, liên kết `80.left` nên trỏ tới đâu?

**Bài 7.** Một tree map lưu `50 → "An"` và `60 → "Bình"`. Khi xóa khóa `50` bằng kế nhiệm `60`, vì sao phải sao chép **cả giá trị**?

**Bài 8.** Vì sao chi phí xóa nút có hai con vẫn là `O(h)` dù cần tìm nút mục tiêu rồi tìm nút thay thế?

**Bài 9.** Chỉ ra khác biệt giữa **sao chép cặp từ nút kế nhiệm** và **di chuyển chính đối tượng nút kế nhiệm**. Lựa chọn nào có thể làm tham chiếu đến đối tượng nút ban đầu đổi khóa?

**Bài 10.** Trong mã `BSTMap.delete`, điều gì xảy ra với `size` khi khóa không tồn tại, khi xóa nút lá và khi xóa nút hai con?

**Bài 11.** Nếu BST có con trỏ `parent`, khi nối con duy nhất của nút thay thế lên cha của nút đó, còn phải cập nhật thông tin gì?

**Bài 12.** Cùng một cây, xóa một khóa hai con bằng tiền nhiệm và kế nhiệm có luôn tạo ra **cùng hình dạng cây** không? Những thuộc tính nào bắt buộc giống nhau?

**Bài 13.** Hãy giải thích tại sao không nên dùng đoạn mã xóa BST thường này trực tiếp làm thuật toán xóa AVL mà không bổ sung bước cân bằng.

**Bài 14.** Hãy tự viết kiểm thử xóa `50` trên cây chứa `(50,30,80,20,40,60,90,70,65)`, xác minh các khóa còn lại, từng giá trị map, dãy in-order và bất biến BST.

<details>
<summary>Đáp án và gợi ý</summary>

1. `predecessor(50)=40`, `successor(50)=60`. Sau khi dùng kế nhiệm, gốc mang `60`; nút `60` ở bên trái `80` được tháo, cây còn các khóa `20,30,40,60,80,90`.
2. Gốc mang `40`; nút `40` cũ ở cây con trái được tháo. Dãy in-order cuối vẫn là `20,30,40,60,80,90`, giống hệt tập khóa của phương án kế nhiệm.
3. Nếu còn con trái, sẽ có khóa nhỏ hơn nó trong cùng cây con phải, mâu thuẫn với “nhỏ nhất”. Nó **có thể có con phải**; phải giữ con phải khi tháo.
4. Nếu còn con phải, sẽ có khóa lớn hơn nó trong cây con trái, mâu thuẫn với “lớn nhất”. Nó có thể có **con trái**; phải nối `predecessor_parent.right = predecessor.left` khi nằm sâu, hoặc `node.left = predecessor.left` khi trực tiếp.
5. Nút `70` là kế nhiệm trực tiếp; sao chép cặp `70` vào nút đang mang `50`, sau đó nối `node.right = 80`.
6. Nối `80.left = 70`; đây là cây con phải của nút kế nhiệm `60`, phải được giữ lại.
7. Nếu chỉ đổi khóa `50` thành `60` mà giữ giá trị `"An"`, ánh xạ `60` sẽ sai. Cần sao chép `"Bình"` cùng khóa `60`.
8. Tìm nút cần xóa `O(h)`, tìm cực trị ở một cây con cũng `O(h)`, nối liên kết `O(1)`. Tổng `O(h)+O(h)+O(1)=O(h)`.
9. Sao chép cặp giữ đối tượng nút cũ nhưng thay khóa/value bên trong; transplant thay đối tượng nút bằng nút thế chỗ và cần sửa nhiều liên kết. **Sao chép cặp** có thể khiến tham chiếu tới nút ban đầu thấy khóa khác.
10. Khóa thiếu: `size` không đổi; xóa lá: giảm một; xóa nút hai con: **cũng chỉ giảm một**, không giảm thêm cho bước tháo nút thế chỗ.
11. Nếu có `child`, đặt `child.parent` tới đúng `replacement_parent` (hoặc cha mới phù hợp); khi đưa một nút thành gốc phải đặt `parent = None`. Các liên kết hai chiều phải nhất quán.
12. **Không** bắt buộc cùng hình dạng; nhưng phải cùng tập khóa sau khi trừ khóa bị xóa, các cặp khóa–giá trị tương ứng còn nguyên, cùng số nút và bất biến BST đúng.
13. AVL còn bất biến cân bằng chiều cao; xóa có thể làm thay đổi chiều cao dọc đường tổ tiên và cần quay/cập nhật metadata. Giữ thứ tự BST **chưa đủ**.
14. Sau xóa `50`, dãy khóa mong đợi là `[20,30,40,60,65,70,80,90]`. Có thể dùng `inorder_items()` và `validate_bst` của bài, đối chiếu với một `dict` tham chiếu và kiểm tra `size() == 8`.

</details>

## Ghi nhớ

**Xóa nút BST có hai con** có thể quy về một thao tác xóa **nút 0 hoặc 1 con**: lấy **kế nhiệm** bằng `min(cây con phải)` hoặc **tiền nhiệm** bằng `max(cây con trái)`, sao chép đúng **cặp khóa–giá trị** vào vị trí cần xóa, rồi **tháo nút thay thế ở vị trí cũ**. Nút kế nhiệm không có con trái nhưng có thể có con phải; nút tiền nhiệm không có con phải nhưng có thể có con trái. Phải xử lý riêng trường hợp nút thay thế **là con trực tiếp**, giữ nguyên mọi cây con còn sống và giảm `size` đúng **một lần**. Tổng chi phí của BST thường là **`O(h)` thời gian, `O(1)` bộ nhớ phụ với mã lặp**; nếu cần bảo đảm `O(log n)` ở trường hợp xấu nhất, phải dùng BST tự cân bằng và bổ sung các bước duy trì cân bằng.

# Chèn nút mới và chính sách xử lý khóa trùng

Một hệ thống quản lý khóa học lưu các cặp **mã khóa học → thông tin khóa học** trong cây tìm kiếm nhị phân (*Binary Search Tree – BST*). Khi nhận thêm mã `CS105`, hệ thống cần tìm đúng vị trí để chèn. Nhưng nếu `CS105` đã tồn tại, hệ thống phải xử lý ra sao: bỏ qua, ghi đè thông tin cũ, báo lỗi hay tăng một bộ đếm?

Hai vấn đề ấy liên quan chặt chẽ: **chèn nút mới phải bảo toàn bất biến thứ tự**, còn **khóa trùng phải được xử lý theo hợp đồng dữ liệu đã chọn**, không được tự ý tạo thêm nút. Bài học thuộc chương **Cây tìm kiếm nhị phân**, trong module cấu trúc dữ liệu về bất biến, thao tác và độ phức tạp thời gian/bộ nhớ.

Sau bài này, người học có thể tự lần theo đường đi chèn, cài đặt chèn lặp hoặc đệ quy, phân biệt BST dùng làm **set**, **map** hay **multiset**, và đánh giá tác động của dữ liệu đầu vào lên chiều cao cây.

## 1. Nhắc lại bất biến BST và quy ước dùng trong bài

Mỗi nút BST có một **khóa** và tối đa hai liên kết `left`, `right`. Với chính sách **khóa duy nhất**, bất biến là:

1. Mọi khóa thuộc **toàn bộ cây con trái** đều **nhỏ hơn** khóa tại nút đang xét.
2. Mọi khóa thuộc **toàn bộ cây con phải** đều **lớn hơn** khóa tại nút đang xét.
3. Hai cây con cũng thỏa bất biến này tại mọi nút.

```text
                 40
               /    \
             20      60
            /  \    /  \
          10   30  50   70
```

Chẳng hạn `30` thuộc cây con trái của `40`, nên phải `30 < 40`, dù nó là con phải của `20`. Bất biến áp dụng cho **toàn bộ cây con**, không chỉ hai con trực tiếp.

Trong phần chính, ta giả định khóa là **số nguyên có thứ tự thông thường** và **mỗi khóa phân biệt có một nút**. Khi muốn lưu nhiều lần xuất hiện của cùng khóa, ta sẽ cân nhắc **lưu bộ đếm hoặc danh sách giá trị tại chính nút ấy**, thay vì phá quy tắc khóa duy nhất.

### Set và map cùng sử dụng phép chèn BST

- **BST-set:** nút chỉ cần lưu `key`. Chèn một khóa đã có không thay đổi tập.
- **BST-map:** nút lưu `(key, value)`. Chèn cặp có khóa cũ thường cập nhật `value` mà không tạo nút mới.
- **BST-multiset:** nút có thể lưu `(key, count)`. Chèn khóa cũ tăng số bản sao `count`, còn số nút phân biệt giữ nguyên.

Với cùng một đường đi, quyết định khi gặp **khóa bằng nhau** mới là điểm khác giữa các cách sử dụng.

## 2. Ba nhánh quyết định tại mỗi nút

Khi muốn chèn khóa `k` và đang xét nút `x`:

| So sánh | Hành động | Kết luận |
| --- | --- | --- |
| `k < x.key` | Đi tới `x.left` | Chỉ cây con trái có thể chứa vị trí phù hợp |
| `k > x.key` | Đi tới `x.right` | Chỉ cây con phải có thể chứa vị trí phù hợp |
| `k == x.key` | Áp dụng **chính sách khóa trùng** | Không tự động tạo nút mới theo quy ước khóa duy nhất |

Nếu cần đi sang một liên kết con đang rỗng (`None`), **đó là vị trí chèn**. Thuật toán tạo một nút lá mới và nối nó vào đúng liên kết ấy.

```text
INSERT(root, key):
    nếu root là rỗng:
        trả nút mới làm gốc

    current = root
    lặp:
        nếu key == current.key:
            xử lý khóa trùng và dừng
        nếu key < current.key:
            nếu current.left rỗng:
                current.left = nút mới(key)
                dừng
            current = current.left
        ngược lại:
            nếu current.right rỗng:
                current.right = nút mới(key)
                dừng
            current = current.right
```

Không thể chọn đại một ô trống trên cây. **Đường đi do phép so sánh quyết định** chính là điều đảm bảo vị trí mới phù hợp với mọi tổ tiên.

## 3. Ví dụ chèn từng bước

Bắt đầu từ cây:

```text
                 40
               /    \
             20      60
            /  \       \
          10   30       70
```

### Chèn khóa 25

Ta tìm `25` theo đúng quy tắc BST:

| Bước | Nút đang xét | So sánh | Quyết định |
| ---: | ---: | --- | --- |
| 1 | `40` | `25 < 40` | Đi trái tới `20` |
| 2 | `20` | `25 > 20` | Đi phải tới `30` |
| 3 | `30` | `25 < 30` | Đi trái |
| 4 | `30.left` | Liên kết rỗng | Tạo nút `25` |

Cây mới:

```text
                 40
               /    \
             20      60
            /  \       \
          10   30       70
              /
             25
```

Nút `25` phải đồng thời thỏa:

- `25 < 40` vì thuộc cây con trái của `40`.
- `25 > 20` vì thuộc cây con phải của `20`.
- `25 < 30` vì thuộc cây con trái của `30`.

Do đó, vị trí chèn hợp lệ có thể được nhìn như một khoảng `20 < 25 < 30`. Các điều kiện từ tổ tiên **không bị quên** khi đi xuống sâu.

### Chèn khóa 65

```text
65 > 40 → đi phải tới 60
65 > 60 → đi phải tới 70
65 < 70 → đi trái, gặp rỗng → tạo nút 65
```

Sau khi chèn:

```text
                 40
               /    \
             20      60
            /  \       \
          10   30       70
              /        /
             25       65
```

Nút `65` thuộc cây con phải của `60`, nhưng lại thuộc cây con trái của `70`. Thỏa `60 < 65 < 70` nên không làm hỏng bất biến.

### Khi chèn lại khóa 30

Đường đi `40 → 20 → 30` kết thúc ở nút đã có cùng khóa. Với BST-set, **không thêm nút thứ hai**. Với BST-map, ta có thể **thay giá trị** đang gắn với `30`. Với BST-multiset, ta có thể **tăng bộ đếm** của nút `30`.

## 4. Vì sao chèn tại liên kết rỗng vẫn giữ BST hợp lệ?

Giả sử cây ban đầu thỏa BST. Khi tìm vị trí cho khóa mới `k`:

1. Ở mỗi nút có khóa `x.key`, ta chỉ đi **trái** nếu `k < x.key`, hoặc đi **phải** nếu `k > x.key`.
2. Vì vậy `k` thỏa toàn bộ các điều kiện nhỏ hơn/lớn hơn do các tổ tiên đặt ra dọc đường đi.
3. Khi gặp liên kết rỗng, ta đặt `k` vào đó thành một **nút lá**; nó chưa có hậu duệ để gây vi phạm mới.
4. Không thay đổi vị trí hoặc khóa của các nút cũ, nên bất biến trong các cây con cũ vẫn đúng.
5. Vì nút mới thỏa mọi giới hạn từ tổ tiên, **toàn cây vẫn là BST hợp lệ**.

Đây là lập luận về tính đúng đắn với các điều kiện tiên quyết:

- Cây ban đầu đã là BST.
- So sánh khóa có thứ tự phù hợp, nhất quán giữa các lần thao tác.
- Chính sách khóa trùng không đưa thêm khóa bằng nhau vào một vị trí làm vi phạm bất biến nghiêm ngặt.
- Không có thao tác ngoài luồng thay đổi khóa hoặc liên kết cây trong quá trình chèn.

**Chèn BST chuẩn không tự sửa một cây đã sai bất biến từ trước.** Nếu một nút đã đặt sai chỗ, chọn đúng đường đi cho nút mới không thể bảo đảm chữa được lỗi cũ.

### Nhìn từ khoảng cho phép

Vị trí cần chèn là giao của những điều kiện đã gặp. Với đường đi `40 → 20 → 30 → left`, các giới hạn là:

```text
k < 40
k > 20
k < 30

Tổng hợp: 20 < k < 30
```

Nếu chương trình tự chọn chèn `50` tại `30.left` vì chỉ xét `50 > 20` hoặc chỉ vì ô rỗng, bất biến sẽ sai. Phải đi theo **mọi bước so sánh**, không chỉ một điều kiện cục bộ.

## 5. Cài chèn lặp cho BST-set

Một BST-set lưu **một nút cho mỗi khóa phân biệt**. Đoạn mã Python dưới đây dùng vòng lặp, không cần tạo ngăn xếp lời gọi đệ quy.

```python
class Node:
    def __init__(self, key, left=None, right=None):
        self.key = key
        self.left = left
        self.right = right


class BSTSet:
    def __init__(self):
        self.root = None
        self._size = 0

    def add(self, key):
        """Trả True nếu thêm nút mới; False nếu khóa đã tồn tại."""
        if self.root is None:
            self.root = Node(key)
            self._size = 1
            return True

        current = self.root

        while True:
            if key == current.key:
                return False

            if key < current.key:
                if current.left is None:
                    current.left = Node(key)
                    self._size += 1
                    return True
                current = current.left
            else:
                if current.right is None:
                    current.right = Node(key)
                    self._size += 1
                    return True
                current = current.right

    def contains(self, key):
        current = self.root
        while current is not None:
            if key == current.key:
                return True
            current = current.left if key < current.key else current.right
        return False

    def size(self):
        return self._size


numbers = BSTSet()
for key in [40, 20, 60, 10, 30, 25, 65]:
    assert numbers.add(key) is True

assert numbers.size() == 7
assert numbers.contains(25)
assert not numbers.contains(99)

assert numbers.add(30) is False
assert numbers.size() == 7    # Khóa trùng không tạo nút thứ hai
```

### Bất biến của lớp

- `_size` là **số nút**, cũng là số khóa phân biệt.
- `root is None` khi và chỉ khi `_size == 0`.
- Mỗi nút có khóa khác mọi khóa ở nút khác.
- Toàn bộ cây con trái/phải tuân thủ bất biến thứ tự.
- `add` trả `False` khi không chèn mới; không thay đổi cấu trúc đối với khóa đã có.

**Lưu ý:** đoạn mã giả định khóa có phép so sánh `==` và `<` nhất quán. Nó không tự xử lý `NaN` hoặc các đối tượng không có quan hệ thứ tự phù hợp. Với khóa tùy biến, cần định nghĩa rõ bộ so sánh trước khi thiết kế BST.

## 6. Cài chèn đệ quy và cập nhật lại liên kết con

Một cách khác là hàm đệ quy **trả về gốc mới của cây con đang xử lý**. Cách này đặc biệt quan trọng khi cây ban đầu rỗng hoặc khi thay đổi liên kết con.

```python
def insert_unique(root, key):
    """Trả (root_mới, inserted)."""
    if root is None:
        return Node(key), True

    if key == root.key:
        return root, False

    if key < root.key:
        root.left, inserted = insert_unique(root.left, key)
    else:
        root.right, inserted = insert_unique(root.right, key)

    return root, inserted


root = None
for key in [40, 20, 60, 30]:
    root, inserted = insert_unique(root, key)
    assert inserted

root, inserted = insert_unique(root, 30)
assert inserted is False

root, inserted = insert_unique(root, 25)
assert inserted is True
```

Ở mỗi lần gọi, hàm chỉ đi vào **một** cây con, vì phép so sánh đã loại được phía còn lại. Phép gán `root.left, inserted = ...` hoặc `root.right, inserted = ...` giúp nối lại cây con đã được xử lý.

### Không bỏ quên gốc mới

Sai lầm thường gặp:

```python
root = None
insert_unique(root, 40)  # Giá trị trả về bị bỏ qua
assert root is None      # Biến root vẫn không đổi
```

Đúng phải là:

```python
root, inserted = insert_unique(root, 40)
assert inserted
assert root.key == 40
```

Với phép chèn BST đơn giản, nếu `root` đã tồn tại thì liên kết gốc thường không đổi. Tuy nhiên, **gốc cây rỗng chắc chắn phải được cập nhật**. Và trong **cây tự cân bằng**, phép quay có thể đổi gốc của một cây con, nên thiết kế trả về gốc mới càng quan trọng.

### So sánh lặp và đệ quy

| Tiêu chí | Lặp | Đệ quy |
| --- | --- | --- |
| Đường đi theo so sánh | Một đường gốc → lá | Một nhánh đệ quy |
| Thời gian | `O(h)` | `O(h)` |
| Bộ nhớ phụ | `O(1)` nếu không lưu đường đi | `O(h)` ngăn xếp lời gọi |
| Cây rỗng | Phải gán `self.root` | Phải nhận gốc trả về |
| Cây lệch rất sâu | Không bị giới hạn đệ quy do thuật toán | Có thể vượt giới hạn call stack |

Trong bảng, `h` là chiều cao đo bằng số nút trên đường dài nhất từ gốc tới lá. Kết quả `O(h)` giả định phép so sánh một khóa có chi phí cơ bản hằng số.

## 7. Chính sách 1: khóa trùng được bỏ qua (set semantics)

Với **set**, hai lần thêm cùng khóa vẫn chỉ có một phần tử:

```text
add(20)  → thêm nút 20
add(10)  → thêm nút 10
add(20)  → không thay đổi
size     → 2
```

```python
students = BSTSet()

assert students.add(20) is True
assert students.add(10) is True
assert students.add(20) is False
assert students.size() == 2
```

Hợp đồng API có thể có các lựa chọn:

- Trả một giá trị boolean `inserted`, như lớp trên.
- Không trả kết quả, nhưng kích thước vẫn không đổi.
- Báo lỗi nếu khóa trùng, khi ứng dụng coi đây là dữ liệu nhập không hợp lệ.

**Điểm chung:** không được sinh thêm một nút `20` khác trong BST có quy tắc trái nhỏ hơn nghiêm ngặt và phải lớn hơn nghiêm ngặt.

Trong bài toán danh sách mã học viên **phân biệt**, bỏ qua khóa trùng thường hợp lý. Trong bài toán nhập hồ sơ cần phát hiện lỗi, phát sinh lỗi hoặc trả trạng thái trùng có thể tốt hơn việc im lặng bỏ qua.

## 8. Chính sách 2: cập nhật giá trị của khóa đã có (map semantics)

**Map** lưu duy nhất một nút cho mỗi khóa, nhưng giá trị có thể thay đổi. Khi chèn cặp `(key, value)`:

- Chưa có khóa: tạo nút mới, tăng `size`.
- Đã có khóa: **thay `value` của nút**, không đổi liên kết trái/phải, không tăng `size`.

```text
Trước:
   key=20 → value="Khóa học cũ"

put(20, "Khóa học cập nhật")

Sau:
   key=20 → value="Khóa học cập nhật"
   Số nút vẫn là 1
```

### Cài BSTMap với trạng thái chèn/cập nhật

```python
class MapNode:
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
        """Trả (inserted, old_value); old_value có thể là None."""
        if self.root is None:
            self.root = MapNode(key, value)
            self._size = 1
            return True, None

        current = self.root
        while True:
            if key == current.key:
                old_value = current.value
                current.value = value
                return False, old_value

            if key < current.key:
                if current.left is None:
                    current.left = MapNode(key, value)
                    self._size += 1
                    return True, None
                current = current.left
            else:
                if current.right is None:
                    current.right = MapNode(key, value)
                    self._size += 1
                    return True, None
                current = current.right

    def find(self, key):
        """Trả (found, value) để phân biệt thiếu khóa với value=None."""
        current = self.root
        while current is not None:
            if key == current.key:
                return True, current.value
            current = current.left if key < current.key else current.right
        return False, None

    def size(self):
        return self._size


courses = BSTMap()

assert courses.put(20, "Cấu trúc dữ liệu") == (True, None)
assert courses.put(10, "Python") == (True, None)
assert courses.put(20, "Cấu trúc dữ liệu nâng cao") == (
    False, "Cấu trúc dữ liệu"
)

assert courses.size() == 2
assert courses.find(20) == (True, "Cấu trúc dữ liệu nâng cao")
assert courses.find(99) == (False, None)
```

### Khóa thiếu và giá trị `None` hợp lệ

Đoạn mã `find` trả `(found, value)` thay vì chỉ trả giá trị. Ví dụ:

```python
assert courses.put(30, None) == (True, None)
assert courses.find(30) == (True, None)
assert courses.find(300) == (False, None)
```

Nếu chỉ `return None`, người gọi không thể phân biệt **không có khóa 300** với **có khóa 30 nhưng giá trị đang là None**.

Tương tự, `put` trả `(False, None)` khi **cập nhật khóa cũ từng có giá trị None**; cờ `inserted` mới là nguồn xác định đã tạo nút hay chưa. Không được xác định chèn thành công dựa vào `old_value is None`.

### Những biến thể API liên quan

| Kiểu thao tác | Khóa chưa tồn tại | Khóa đã tồn tại |
| --- | --- | --- |
| `put / upsert` | Thêm mới | Ghi đè/cập nhật |
| `insert_if_absent` | Thêm mới | Giữ nguyên, báo trùng |
| `insert_or_error` | Thêm mới | Báo lỗi |
| `update_if_present` | Không thêm | Cập nhật giá trị |

Không có chính sách nào tự động đúng cho tất cả bài toán. Nên quyết định rõ ngay trong **hợp đồng API**, đặc biệt khi mất dữ liệu do ghi đè là rủi ro quan trọng.

## 9. Chính sách 3: đếm số lần xuất hiện (multiset semantics)

Nếu bài toán là đếm có bao nhiêu lần một mã xuất hiện, ta có thể dùng một **BST đếm tần suất**. Mỗi khóa phân biệt chỉ có một nút, thêm trường `count` là số bản sao của khóa.

```text
Chèn lần lượt: 20, 10, 20, 30, 20

        20 (count=3)
       /             \
 10 (count=1)     30 (count=1)

distinct_size = 3
total_count   = 5
```

Đây là cách giữ bất biến BST nghiêm ngặt giữa các **nút**, đồng thời lưu đúng số lần xuất hiện.

### Cài ví dụ

```python
class CountNode:
    def __init__(self, key):
        self.key = key
        self.count = 1
        self.left = None
        self.right = None


class BSTMultiset:
    def __init__(self):
        self.root = None
        self._distinct = 0
        self._total = 0

    def add(self, key):
        if self.root is None:
            self.root = CountNode(key)
            self._distinct = 1
            self._total = 1
            return True

        current = self.root
        while True:
            if key == current.key:
                current.count += 1
                self._total += 1
                return False

            if key < current.key:
                if current.left is None:
                    current.left = CountNode(key)
                    break
                current = current.left
            else:
                if current.right is None:
                    current.right = CountNode(key)
                    break
                current = current.right

        self._distinct += 1
        self._total += 1
        return True

    def count(self, key):
        current = self.root
        while current is not None:
            if key == current.key:
                return current.count
            current = current.left if key < current.key else current.right
        return 0

    def distinct_size(self):
        return self._distinct

    def total_count(self):
        return self._total


bag = BSTMultiset()
for key in [20, 10, 20, 30, 20]:
    bag.add(key)

assert bag.count(20) == 3
assert bag.count(10) == 1
assert bag.count(99) == 0
assert bag.distinct_size() == 3
assert bag.total_count() == 5
```

### Hai bất biến về kích thước

- `_distinct` phải bằng **số nút** trong BST.
- `_total` phải bằng **tổng mọi `node.count`**, tính tất cả bản sao.

Chèn khóa cũ chỉ tăng `count` và `_total`; chèn khóa mới tăng cả `_distinct` và `_total`.

Nếu sau này bổ sung thao tác xóa **một bản sao**, có thể giảm `count`; chỉ khi `count` về 0 mới cần xóa nút theo thuật toán xóa BST. Đây là điểm nối giữa bài toán đa tập hợp và chính sách chèn/xóa của cây.

## 10. Chính sách 4: lưu nhiều giá trị dưới một khóa

Đôi khi cùng một khóa liên kết với nhiều bản ghi **khác nhau**, không chỉ nhiều bản sao cùng giá trị. Ví dụ `mã lớp học → các học viên đăng ký`.

Một cách giữ BST khóa duy nhất là mỗi nút chứa **collection giá trị**:

```text
key = "CS101" → ["HV01", "HV03", "HV09"]
key = "CS102" → ["HV02"]

Các khóa vẫn phân biệt theo BST;
nhiều giá trị nằm bên trong nút.
```

Đây là một dạng hiện thực **multimap trên BST**. Khi chèn `("CS101", "HV10")`, thuật toán tìm thấy nút `CS101` rồi thêm `HV10` vào collection, không tạo nút `CS101` thứ hai.

**Chọn collection theo yêu cầu nghiệp vụ:**

- `list` khi cần giữ các lượt đăng ký và có thể có giá trị lặp.
- `set` khi mỗi học viên chỉ cần được ghi nhận một lần trong mỗi lớp.
- `dict` hoặc map đếm khi cần tần suất/thuộc tính riêng của mỗi giá trị.

Cây chịu trách nhiệm **sắp xếp và tra cứu khóa**, còn collection gắn với nút quản lý các giá trị của khóa đó. Chi phí thao tác tổng còn phụ thuộc cấu trúc collection, không chỉ chiều cao BST.

## 11. Vì sao không nên tùy ý tạo nút riêng cho khóa trùng?

Một số tài liệu minh họa chính sách `key <= current.key` thì đi trái hoặc `key >= current.key` thì đi phải. Các quy ước ấy **có thể được cài đặt**, nhưng chúng thay đổi bất biến và kéo theo nhiều hệ quả.

### Cho khóa trùng đi phải

Nếu quy ước `left < key ≤ right`, chèn `20` hai lần có thể tạo:

```text
    20
      \
       20
```

Khi đó, **duyệt trung thứ tự không còn tăng nghiêm ngặt**; nó chỉ có thể **không giảm**. Các thao tác tìm/xóa/rank/range query phải được định nghĩa lại để xử lý bản sao.

Một vấn đề tinh tế xuất hiện khi chuyển sang **cây tự cân bằng**. Ví dụ quay trái:

```text
Trước quay trái:      Sau quay trái:

     20                  20
       \                /
        20             20
```

Nếu sau phép quay, khóa trùng nằm **bên trái** nút có cùng khóa, quy tắc “khóa trùng chỉ nằm bên phải” đã bị phá. Phép quay vẫn có thể giữ dãy in-order, nhưng **không tự giữ được chính sách khóa trùng ở một phía**.

Bởi vậy, khi cần BST hoặc tree map tự cân bằng, các phương án **bộ đếm tại nút**, **collection giá trị tại nút**, hoặc **khóa ghép có tiêu chí phân biệt** thường dễ thiết kế nhất quán hơn.

### Dùng khóa ghép để phân biệt bản ghi

Nếu hai bài kiểm tra cùng điểm `90` nhưng khác mã bài, ta có thể sắp theo `(điểm, mã bài)`:

```python
records = BSTSet()

assert records.add((90, "TEST-A")) is True
assert records.add((90, "TEST-B")) is True
assert records.add((90, "TEST-A")) is False
assert records.size() == 2
```

Hai tuple khác nhau vì mã bài khác nhau, dù điểm bằng nhau. Khi so sánh tuple Python, các thành phần được so theo thứ tự từ trái sang phải; tất cả thành phần dùng trong khóa phải có phép so sánh phù hợp và không thay đổi làm sai thứ tự cây.

**Lưu ý:** khóa ghép `(điểm, mã bài)` coi điểm là một phần định danh. Nếu điểm của `TEST-A` thay đổi, không nên sửa trực tiếp trường khóa bên trong nút; cần một chiến lược **xóa khóa cũ rồi chèn khóa mới** hoặc lưu map theo mã bài và chỉ dùng thứ tự điểm trong một chỉ mục phụ.

## 12. Bộ so sánh và quy tắc tương đương khóa

Trong ứng dụng thực tế, khóa có thể là chuỗi, tuple hoặc đối tượng. Một BST có thứ tự thường sử dụng một hàm so sánh ba chiều:

```text
compare(a, b) < 0  → a đứng trước b
compare(a, b) = 0  → a tương đương b
compare(a, b) > 0  → a đứng sau b
```

Trong cây dùng comparator, **tương đương khóa** là kết quả so sánh bằng 0, không nhất thiết đồng nghĩa hai đối tượng có cùng địa chỉ bộ nhớ.

### Ví dụ Java: TreeMap và TreeSet

```java
import java.util.Comparator;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class Main {
    public static void main(String[] args) {
        Comparator<String> byCode = String.CASE_INSENSITIVE_ORDER;

        Set<String> ids = new TreeSet<>(byCode);
        System.out.println(ids.add("HV01")); // true
        System.out.println(ids.add("hv01")); // false: cùng khóa logic
        System.out.println(ids.size());      // 1

        TreeMap<String, Integer> scores = new TreeMap<>(byCode);
        scores.put("HV01", 8);
        scores.put("hv01", 10);               // Ghi đè theo comparator
        System.out.println(scores.size());   // 1
        System.out.println(scores.get("Hv01")); // 10
    }
}
```

Trong ví dụ này, `"HV01"` và `"hv01"` được bộ so sánh xem là tương đương, nên `TreeSet` từ chối thêm khóa thứ hai còn `TreeMap` cập nhật giá trị. Nếu dùng cách lưu khóa có phân biệt hoa thường, kết quả có thể khác.

### Comparator thiếu tiêu chí phân biệt

Giả sử một comparator chỉ so độ dài chuỗi: `"AA"` và `"BB"` đều dài hai ký tự. Tree set/map có thể coi chúng là cùng khóa mặc dù nội dung khác nhau.

```java
import java.util.Comparator;
import java.util.TreeSet;

public class Main {
    public static void main(String[] args) {
        TreeSet<String> codes =
            new TreeSet<>(Comparator.comparingInt(String::length));

        codes.add("AA");
        codes.add("BB");

        System.out.println(codes.size()); // 1
    }
}
```

Nếu nghiệp vụ cần hai mã riêng, phải bổ sung tiêu chí so sánh khi bằng độ dài, chẳng hạn so toàn bộ chuỗi:

```java
import java.util.Comparator;

public class Main {
    public static void main(String[] args) {
        Comparator<String> byLengthThenText = Comparator
            .comparingInt(String::length)
            .thenComparing(Comparator.naturalOrder());

        System.out.println(byLengthThenText.compare("AA", "BB") < 0); // true
    }
}
```

Bộ so sánh phải tạo một quy tắc thứ tự **nhất quán và đủ phân biệt** theo khóa nghiệp vụ. Các cây có thứ tự không thể hoạt động đúng nếu comparator cho kết quả không ổn định hoặc vi phạm tính bắc cầu.

## 13. Tác động của thứ tự chèn lên hình dạng cây

Với **BST thông thường, không tự cân bằng**, cùng một tập khóa có thể cho cây rất khác nhau tùy **thứ tự chèn**.

### Chèn theo thứ tự gần cân đối

```text
Chèn: 40, 20, 60, 10, 30, 50, 70

         40
       /    \
     20      60
    /  \    /  \
  10   30  50   70
```

Chiều cao tính theo số nút trên đường gốc tới lá là `h = 3`.

### Chèn theo thứ tự tăng dần

```text
Chèn: 10, 20, 30, 40, 50, 60, 70

10
  \
   20
     \
      30
        \
         40
           \
            50
              \
               60
                 \
                  70
```

Chiều cao trở thành `h = 7`, bằng số nút. Cây vẫn thỏa BST nhưng **bị lệch hoàn toàn**, hành vi tìm/chèn có thể gần giống danh sách liên kết.

Điều này phân biệt hai khái niệm:

- **BST hợp lệ:** bảo toàn thứ tự toàn bộ cây con.
- **BST cân bằng:** có thêm quy tắc duy trì chiều cao nhỏ.

Chèn chuẩn vào BST không tự cân bằng **không bảo đảm `O(log n)`**. Nếu cần hiệu năng logarit trong trường hợp xấu nhất, phải dùng cấu trúc tự cân bằng như AVL hoặc cây đỏ–đen; các phép quay được thiết kế để giữ đúng thứ tự in-order.

### Chèn khóa trùng không làm cây dài hơn khi gom tại nút

Nếu dùng `BSTMultiset` với khóa phân biệt và bộ đếm, chèn `20` một triệu lần vẫn chỉ tạo **một nút** cho `20`. Chi phí tăng `count` là `O(1)` sau khi tìm được nút, còn chi phí đường đi để tới nút là `O(h)`.

Nếu tạo một nút mới cho mỗi bản sao, số nút tăng theo tổng bản sao và có thể làm cây lệch nghiêm trọng. Đây là một lý do thực tế để chọn chính sách **đếm hoặc gom giá trị tại nút**.

## 14. Độ phức tạp thời gian và bộ nhớ

Đặt `n` là **số nút phân biệt** và `h` là **chiều cao BST**, tính theo số nút trên đường dài nhất. Mỗi lần chèn vào BST chuẩn đi qua tối đa một đường từ gốc tới liên kết rỗng hoặc khóa cũ.

| Tình huống | Số bước so sánh/di chuyển | Thời gian | Bộ nhớ phụ |
| --- | --- | --- | --- |
| Chèn vào cây rỗng | Không cần đi qua nút cũ | `O(1)` | `O(1)` |
| Khóa trùng ngay tại gốc | Một nút | `O(1)` | `O(1)` |
| Chèn/tìm một khóa ở độ sâu `d` | Tỷ lệ `d + 1` | `O(d + 1)` | Lặp: `O(1)` |
| Chèn vào BST cân đối | Đường cao `O(log n)` | `O(log n)` | Lặp `O(1)`; đệ quy `O(log n)` |
| Chèn vào BST lệch | Đường cao `O(n)` | `O(n)` | Lặp `O(1)`; đệ quy `O(n)` |
| Chèn vào BST tự cân bằng | Đường cao `O(log n)` và cập nhật cân bằng | `O(log n)` | Phụ thuộc hiện thực |

Các mốc trên giả định so sánh khóa và tạo một nút tốn thời gian cơ bản hằng số. Với khóa là chuỗi dài độ dài `L`, mỗi lần so sánh có thể tốn đến `O(L)`, dẫn đến chi phí đường đi cỡ `O(hL)` trong trường hợp xấu của phép so sánh.

### Chèn nhiều khóa

Chèn `n` khóa phân biệt vào BST thường:

- Nếu cây luôn có chiều cao `O(log n)`, tổng thời gian có thể `O(n log n)`.
- Nếu khóa được đưa vào theo thứ tự bất lợi, các lần chèn có đường đi dài `1, 2, ..., n`, tổng là **`Θ(n²)`**.
- Cây tự cân bằng giúp duy trì `O(log n)` cho từng lần chèn, dù có thêm công việc duy trì cấu trúc.

Nếu một đầu vào có rất nhiều bản sao của cùng khóa, tổng số **sự kiện chèn** và số **nút phân biệt** cần được tách riêng. Với `m` lượt chèn và `d` khóa phân biệt, BST gom trùng có `d` nút; độ phức tạp phụ thuộc **đường đi tìm mỗi lượt** cùng chính sách cập nhật tại nút.

### Chi phí bộ nhớ cho bản sao

| Chính sách | Số nút cây | Dữ liệu phụ tại nút |
| --- | --- | --- |
| Set bỏ qua trùng | Số khóa phân biệt `d` | Không cần đếm bản sao |
| Map cập nhật value | `d` | Một giá trị hiện tại cho mỗi khóa |
| Multiset có count | `d` | Một bộ đếm trên mỗi khóa |
| Multimap có collection | `d` | Danh sách/set các giá trị tại mỗi khóa |
| Mỗi bản sao một nút | Có thể bằng tổng số bản sao `m` | Ít metadata nhưng cây phình to |

Với collection giá trị, bộ nhớ thực tế còn phụ thuộc tổng số giá trị lưu dưới các khóa, chứ không chỉ `d` nút cây.

## 15. Các bất biến và trường hợp biên cần kiểm thử

Một triển khai chèn tốt phải xử lý được:

1. **Cây rỗng:** tạo nút gốc mới; caller nhận được gốc.
2. **Chèn khóa nhỏ hơn/lớn hơn gốc:** rẽ đúng nhánh.
3. **Chèn sâu nhiều tầng:** khóa phải thỏa giới hạn của **mọi** tổ tiên.
4. **Khóa trùng tại gốc:** áp dụng chính sách trùng, không tạo nút mới ngoài ý muốn.
5. **Khóa trùng sâu trong cây:** kết quả phải giống chính sách ở gốc.
6. **Giá trị map bằng `None`, `0` hoặc chuỗi rỗng:** không nhầm dữ liệu hợp lệ với khóa vắng mặt.
7. **Kích thước:** chỉ tăng số nút khi tạo khóa mới.
8. **Đường đi trên cây lệch:** không giả định chèn luôn `O(log n)`.
9. **Quy tắc bằng nhau:** dùng cùng comparator khi chèn, tìm và cập nhật.
10. **Khóa mutable:** không sửa các trường ảnh hưởng thứ tự khi nút đang nằm trong cây.
11. **Đệ quy quá sâu:** có thể lỗi ngăn xếp lời gọi; bản lặp không gặp giới hạn đệ quy ấy.
12. **Đồng thời:** không được giả định hai luồng chèn vào cùng một liên kết rỗng là nguyên tử nếu không có đồng bộ.

Một sai lầm nghiêm trọng là viết `node.left = Node(key)` ngay khi `key < node.key` mà **không** kiểm tra cây con trái đã có nút hay chưa. Làm vậy có thể làm mất toàn bộ cây con cũ. Phải **đi tiếp** khi liên kết chưa rỗng và **chỉ tạo nút tại liên kết rỗng**.

### Kiểm tra bằng in-order

Với BST **khóa duy nhất**, duyệt trung thứ tự (*in-order*: trái → nút → phải) phải tạo dãy **tăng nghiêm ngặt**.

```python
def inorder_keys(root):
    result = []
    stack = []
    current = root

    while stack or current is not None:
        while current is not None:
            stack.append(current)
            current = current.left

        current = stack.pop()
        result.append(current.key)
        current = current.right

    return result


keys = inorder_keys(numbers.root)
assert keys == [10, 20, 25, 30, 40, 60, 65]
assert all(keys[i] < keys[i + 1] for i in range(len(keys) - 1))
```

Kiểm tra tăng nghiêm ngặt là một cách phát hiện lỗi thứ tự khi kiểm thử. Với cây có **nút trùng khóa**, dãy có thể chỉ **không giảm**; vì thế cần thống nhất chính sách trùng trước khi dùng điều kiện kiểm thử.

### Kiểm tra tính đồng nhất sau nhiều lần chèn

```python
sample = BSTSet()
inserted_flags = [sample.add(x) for x in [5, 2, 8, 2, 5, 10]]

assert inserted_flags == [True, True, True, False, False, True]
assert sample.size() == 4
assert inorder_keys(sample.root) == [2, 5, 8, 10]

bag = BSTMultiset()
for key in [5, 2, 8, 2, 5, 10]:
    bag.add(key)

assert bag.distinct_size() == 4
assert bag.total_count() == 6
assert bag.count(5) == 2
assert bag.count(2) == 2
```

**Chú ý:** bài viết trình bày ví dụ để người học chạy và tự kiểm tra; đây chưa phải vòng kiểm thử học thuật/toàn hệ thống hoặc benchmark hiệu năng.

## 16. Ví dụ ứng dụng: đăng ký học viên và chỉ mục điểm

Giả sử có các yêu cầu nghiệp vụ:

- Mỗi `student_id` chỉ được có **một hồ sơ điểm hiện tại**.
- Cập nhật điểm cho học viên cũ **không thêm hồ sơ thứ hai**.
- Muốn in hồ sơ **theo thứ tự mã học viên**.

Một tree map lưu `student_id → score` với chính sách `put` cập nhật phù hợp:

```python
scores = BSTMap()

scores.put("HV03", 7.0)
scores.put("HV01", 9.0)
scores.put("HV02", 8.0)

inserted, previous = scores.put("HV01", 9.5)
assert inserted is False
assert previous == 9.0
assert scores.size() == 3

assert scores.find("HV01") == (True, 9.5)
```

Nếu mục tiêu chuyển thành **đếm số lần điểm danh**, chỉ cập nhật điểm không phù hợp. Khi đó, dùng `BSTMultiset` theo mã học viên hoặc map `student_id → số lần điểm danh`.

Nếu muốn lưu **các điểm thi khác nhau theo từng lần thi**, dùng collection giá trị hoặc khóa ghép `(student_id, exam_id)`. Trước khi chọn chính sách chèn, phải trả lời: **“Hai bản ghi cùng student_id thực sự là một hồ sơ cập nhật, hai lượt sự kiện, hay hai thực thể khác nhau?”**

Một lựa chọn cấu trúc dữ liệu đúng không chỉ dựa trên `O(h)`, mà còn ở khả năng **giữ đúng ý nghĩa dữ liệu**.

## 17. Lỗi thường gặp

1. **Tạo nút ngay khi đi trái/phải**, dù liên kết còn chứa cây con: có thể làm mất các nút cũ.
2. **Chèn khóa bằng nhau như một khóa mới** trong BST-set/map dùng bất biến nghiêm ngặt.
3. **Quên tăng `size` khi tạo nút mới** hoặc tăng cả khi chỉ cập nhật giá trị.
4. **Quên cập nhật gốc khi cây ban đầu rỗng**, đặc biệt với hàm đệ quy trả gốc.
5. **Chỉ xét quan hệ cha–con**, không xét giới hạn từ toàn bộ tổ tiên.
6. **Đảo hướng so sánh**, làm khóa nhỏ hơn đi phải hoặc khóa lớn hơn đi trái.
7. **Dùng comparator khác nhau giữa chèn và tìm**, khiến một số khóa không thể tìm lại.
8. **Gộp khóa theo comparator quá thô**, ví dụ chỉ so điểm hoặc độ dài chuỗi khi định danh phải khác nhau.
9. **Sửa khóa tại chỗ sau khi chèn**, phá vị trí theo thứ tự.
10. **Coi cập nhật value như thêm nút**, làm sai số lượng khóa.
11. **Nhầm số nút và tổng số bản sao** trong BST-multiset.
12. **Giả định tạo mỗi bản sao thành một nút sẽ luôn dễ cân bằng**, trong khi quay cây có thể phá quy tắc trùng luôn ở một phía.
13. **Cho rằng mọi lần chèn đều `O(log n)`**, dù BST thường có thể lệch thành chuỗi.
14. **Nhầm thao tác chèn với tìm kiếm**: tìm kiếm chỉ xác định vị trí, chèn còn phải tạo nút hoặc cập nhật dữ liệu theo chính sách.
15. **Bỏ qua lỗi đồng thời** khi nhiều tác nhân cùng chèn/cập nhật; cần đồng bộ hoặc cấu trúc có hợp đồng concurrent thích hợp.

## 18. Tự luyện tập

**Bài 1.** Từ cây `40` gốc, `20` ở trái, `60` ở phải, `10` và `30` là con của `20`, hãy mô tả đường đi chèn khóa `25`. Khóa mới được đặt ở đâu?

**Bài 2.** Với cây `40 → trái 20 → phải 30`, vì sao không được chèn `50` làm con trái của `30`, dù liên kết ấy đang rỗng?

**Bài 3.** Chèn dãy `[8, 4, 12, 4, 10, 8]` vào BST-set. Có bao nhiêu nút, và những lần chèn nào trả `False` trong API `add` của bài?

**Bài 4.** Một BST-map nhận `put(20, "A")` rồi `put(20, "B")`. Số nút và giá trị ở khóa `20` là bao nhiêu? Nếu thao tác là `insert_if_absent` thay vì `put` thì sao?

**Bài 5.** Một BST-multiset nhận `[5, 2, 5, 5, 7, 2]`. Vẽ khóa của từng nút cùng `count`, tính số nút phân biệt và tổng số phần tử.

**Bài 6.** Viết hàm chèn đệ quy trả lại gốc và cờ `inserted`; giải thích vì sao caller phải nhận lại gốc trả về.

**Bài 7.** Vì sao việc lưu bản sao của khóa trùng **chỉ ở cây con phải** có thể gặp khó khăn khi BST được tự cân bằng bằng phép quay? Nêu một cách thay thế.

**Bài 8.** Nếu chèn `1,2,3,4,5,6` theo thứ tự vào BST thường không cân bằng, tìm/chèn khóa cuối có thể mất bao nhiêu bước? Tổng thời gian xây cây `n` khóa tăng dần thuộc bậc nào?

**Bài 9.** Một `TreeSet<String>` dùng comparator chỉ so độ dài nhận `"AB"` rồi `"CD"`. Vì sao có thể chỉ còn một phần tử? Làm sao giữ cả hai mà vẫn sắp theo độ dài trước?

**Bài 10.** Cho BST-map lưu khóa `"HV01"` với giá trị `None`. Hãy thiết kế kết quả của `find` để phân biệt khóa thiếu và khóa có giá trị `None`.

**Bài 11.** Khi muốn lưu nhiều học viên cho cùng mã lớp học, hãy so sánh ba cách: ghi đè giá trị, tăng bộ đếm, và lưu list/set dưới mỗi khóa. Khi nào mỗi cách có ý nghĩa?

**Bài 12.** Viết các `assert` để kiểm tra sau khi chèn nhiều lần rằng (a) kích thước set bằng số khóa phân biệt, (b) in-order tăng nghiêm ngặt, (c) chèn lại khóa cũ không đổi kích thước.

<details>
<summary>Đáp án và gợi ý</summary>

1. `25 < 40` → trái tới `20`; `25 > 20` → phải tới `30`; `25 < 30` → trái gặp rỗng, tạo nút `25` tại `30.left`.
2. `50` thuộc cây con trái của `40` nếu chèn tại đó, nhưng `50 > 40`, nên vi phạm bất biến toàn cây con. Phải đi theo đường so sánh từ gốc.
3. Bốn nút phân biệt: `{4, 8, 10, 12}`. Các lượt chèn `4` thứ hai và `8` thứ hai trả `False`.
4. Với `put`: một nút `20`, giá trị cuối là `"B"`. Với `insert_if_absent`: vẫn một nút, giá trị cũ `"A"` được giữ và thao tác sau báo trùng.
5. Cây có nút `5(count=3)`, `2(count=2)` ở trái và `7(count=1)` ở phải. Số khóa phân biệt `3`, tổng số lần xuất hiện `6`.
6. Dùng mẫu `root.left, inserted = insert(root.left, key)` hoặc `root.right, inserted = ...` và `return root, inserted`; với cây rỗng cần gán lại gốc mới từ kết quả.
7. Phép quay có thể đưa nút cùng khóa từ phải sang trái, phá chính sách “trùng chỉ ở bên phải”. Nên dùng `count` hoặc collection giá trị trên một nút, hay khóa ghép phân biệt.
8. Cây có thể lệch thành chuỗi, thao tác cuối mất `Θ(n)` bước; tổng các đường đi của `n` lần chèn tăng dần là `Θ(n²)`.
9. Bộ so sánh cho kết quả tương đương khi độ dài bằng nhau. Dùng so sánh `(length, text)`: trước tiên độ dài, sau đó nội dung chuỗi để phá hòa.
10. Trả `(True, None)` nếu có khóa, `(False, None)` nếu thiếu; không suy từ giá trị `None` rằng khóa không tồn tại.
11. Ghi đè hợp với một giá trị hiện tại cho mỗi lớp; đếm hợp khi chỉ cần số lượt; collection hợp khi cần danh sách/mối liên kết với từng học viên. List giữ được bản sao, set loại cặp trùng.
12. Một ví dụ:

```python
s = BSTSet()
events = [8, 4, 12, 4, 10, 8]
for x in events:
    s.add(x)

unique_keys = sorted(set(events))
assert s.size() == len(unique_keys)
assert inorder_keys(s.root) == unique_keys

before = s.size()
assert s.add(8) is False
assert s.size() == before
```

</details>

## Ghi nhớ

**Chèn BST đi theo đường so sánh từ gốc đến khóa bằng nhau hoặc một liên kết rỗng.** Chỉ tạo nút ở liên kết rỗng, vì đường đi đã thỏa các giới hạn từ mọi tổ tiên. Khi gặp khóa trùng, **set** thường bỏ qua, **map** có thể cập nhật giá trị, **multiset** tăng bộ đếm, và **multimap** thêm giá trị vào collection của một nút. Quy tắc trùng cần phù hợp với comparator, bất biến BST và thao tác xóa/cân bằng về sau. Chi phí chèn là **`O(h)`** theo chiều cao: `O(log n)` khi cây được cân bằng, nhưng có thể `O(n)` khi BST thường bị lệch; với đệ quy còn cần `O(h)` bộ nhớ ngăn xếp lời gọi.

# Chi phí theo chiều cao và nguy cơ suy biến khi dữ liệu đã có thứ tự

Cây tìm kiếm nhị phân (*Binary Search Tree – BST*) thường được giới thiệu như một cấu trúc hỗ trợ tìm kiếm, chèn và xóa hiệu quả. Nhưng có một điều kiện rất quan trọng: **BST thông thường không bảo đảm chiều cao nhỏ**. Cùng một tập khóa, chỉ cần thay đổi **thứ tự chèn**, cây có thể gần cân đối hoặc lệch thành một chuỗi dài giống danh sách liên kết.

Hãy tưởng tượng nền tảng học tập nhận mã học viên theo thứ tự `1, 2, 3, ..., n` từ một tệp CSV đã sắp xếp. Nếu đưa lần lượt từng mã vào **BST không tự cân bằng**, mỗi mã mới có thể trở thành con phải của mã trước. Khi ấy, tìm học viên cuối cùng phải đi qua gần như tất cả nút, thay vì đi một đường ngắn.

Bài học thuộc chương **Cây tìm kiếm nhị phân** trong module cấu trúc dữ liệu. Trọng tâm là ý nghĩa của độ phức tạp **`O(h)` theo chiều cao cây**, sự khác biệt giữa trường hợp cân đối và trường hợp suy biến, chi phí xây cây từ dữ liệu đã có thứ tự và những lựa chọn kỹ thuật giúp tránh giả định sai rằng **mọi BST đều có `O(log n)`**.

## 1. Bất biến BST không đồng nghĩa với cân bằng

Một BST có khóa phân biệt thỏa bất biến:

- Mọi khóa trong **toàn bộ cây con trái** nhỏ hơn khóa ở nút hiện tại.
- Mọi khóa trong **toàn bộ cây con phải** lớn hơn khóa ở nút hiện tại.
- Hai cây con cũng thỏa quy tắc ấy tại mọi nút.

Ví dụ:

```text
          40
         /  \
       20    60
      / \    / \
    10  30  50  70
```

Cây này hợp lệ và tương đối cân đối. Nhưng cây sau cũng **hoàn toàn hợp lệ** theo BST:

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
              \
               60
                 \
                  70
```

Mỗi khóa trong cây thứ hai đều lớn hơn tổ tiên phía trên nó, vì vậy bất biến vẫn đúng. Tuy nhiên, cây có hình dạng như **một danh sách liên kết một chiều**.

**Phân biệt ba khái niệm:**

| Khái niệm | Điều kiện | Có bảo đảm cây thấp không? |
| --- | --- | --- |
| **Cây nhị phân** | Mỗi nút có tối đa hai con | Không |
| **BST hợp lệ** | Khóa bên trái nhỏ hơn, bên phải lớn hơn trên toàn bộ cây con | Không |
| **BST tự cân bằng** | BST và thêm bất biến cân bằng, ví dụ AVL/đỏ–đen | Có giới hạn chiều cao `O(log n)` |

Một chương trình có thể **đúng về mặt chức năng** vì tìm kiếm trả đáp án chính xác, nhưng **không đạt yêu cầu hiệu năng** do chiều cao quá lớn.

## 2. Chiều cao h và số nút n: định nghĩa cần thống nhất

Gọi:

- `n`: số **nút chứa khóa phân biệt** đang nằm trong BST.
- `h`: chiều cao cây, trong bài này đo bằng **số nút trên đường dài nhất từ gốc đến một lá**.
- `d`: độ sâu của một nút, đo bằng **số cạnh từ gốc tới nút ấy**.

Ta quy ước:

```text
Cây rỗng:              n = 0, h = 0
Cây có một nút:        n = 1, h = 1
Cây gốc + một con:     n = 2, h = 2
Cây hoàn hảo 7 nút:    n = 7, h = 3
Chuỗi 7 nút:          n = 7, h = 7
```

Có tài liệu định nghĩa chiều cao theo **số cạnh** thay vì số nút; lúc đó cây một nút cao 0. Hai quy ước chỉ lệch một đơn vị trên cây không rỗng, nên **không làm thay đổi các kết quả Big-O**, nhưng phải thống nhất khi mô phỏng và kiểm thử.

### Tại sao mỗi thao tác thường đi theo một đường?

Để tìm khóa `x` từ gốc:

- Nếu `x == node.key`: tìm thấy.
- Nếu `x < node.key`: chỉ cần tìm ở cây con trái.
- Nếu `x > node.key`: chỉ cần tìm ở cây con phải.

Tương tự, khi chèn khóa mới, ta đi theo một đường cho đến một liên kết con rỗng. Khi xóa, ta tìm nút theo một đường; nếu có hai con, còn đi tìm cực trị trong một cây con rồi nối lại liên kết.

Vì số nút trên bất kỳ đường gốc–lá nào **không vượt `h`**, các thao tác này có giới hạn thời gian **`O(h)`** nếu mỗi lần so sánh/cập nhật tham chiếu có chi phí hằng số.

**`O(h)` mới là mô tả tổng quát của BST thường.** Chỉ thay `h` bằng `O(log n)` khi có lý do xác đáng để kết luận chiều cao nhỏ.

## 3. Chiều cao nhỏ nhất và lớn nhất với n nút

Một cây nhị phân có chiều cao `h` đo bằng số nút trên đường dài nhất có tối đa:

```text
Tầng 1: 1 nút
Tầng 2: 2 nút
Tầng 3: 4 nút
...
Tầng h: 2^(h-1) nút

Tổng lớn nhất = 1 + 2 + 4 + ... + 2^(h-1)
              = 2^h - 1
```

Do đó, nếu cây có `n` nút:

```text
n <= 2^h - 1
h >= ceil(log2(n + 1))
```

Cận dưới đạt được bởi những cây được phân bố gần hoàn hảo theo các tầng. Ngược lại, chiều cao lớn nhất của cây nhị phân có `n >= 1` nút là **`h = n`**, khi mỗi nút chỉ có một con trên đường dài nhất.

| Số nút `n` | Chiều cao tối thiểu | Chiều cao tối đa |
| ---: | ---: | ---: |
| `1` | `1` | `1` |
| `3` | `2` | `3` |
| `7` | `3` | `7` |
| `15` | `4` | `15` |
| `31` | `5` | `31` |
| `1.023` | `10` | `1.023` |

**Ý nghĩa:** cùng `1.023` khóa, một cây rất cân đối có thể chỉ cần đi tối đa khoảng 10 nút từ gốc tới lá; cây lệch hoàn toàn có thể cần đi qua 1.023 nút.

Đây không phải khác biệt nhỏ về hằng số, mà là khác biệt về **bậc tăng trưởng** khi số phần tử ngày càng lớn.

## 4. Truy vết chi phí tìm kiếm: cùng khóa, đường dài khác nhau

Xét hai BST cùng lưu tập:

```text
S = {10, 20, 30, 40, 50, 60, 70}
```

**Cây A – tương đối cân đối:**

```text
          40
         /  \
       20    60
      / \    / \
    10  30  50  70
```

**Cây B – lệch phải:**

```text
10 → 20 → 30 → 40 → 50 → 60 → 70
   (mỗi mũi tên là một liên kết con phải)
```

### Tìm khóa 70

| Cây | Đường đi | Số nút được xét |
| --- | --- | ---: |
| A | `40 → 60 → 70` | `3` |
| B | `10 → 20 → 30 → 40 → 50 → 60 → 70` | `7` |

### Tìm khóa 10

| Cây | Đường đi | Số nút được xét |
| --- | --- | ---: |
| A | `40 → 20 → 10` | `3` |
| B | `10` | `1` |

Vậy **không phải mọi lần tìm trên cây lệch đều chậm**. Một khóa ở gần gốc vẫn có thể tìm trong `O(1)`; rủi ro nằm ở **trường hợp xấu nhất** và nhiều khóa nằm sâu.

### Tìm khóa không tồn tại

Nếu hỏi khóa `75`, cả hai cây phải đi đến một liên kết rỗng:

```text
Cây A: 40 → 60 → 70 → None
Cây B: 10 → 20 → 30 → 40 → 50 → 60 → 70 → None
```

Đường tìm dài nhất bị chi phối bởi `h`, nên giới hạn trên là `O(h)`.

**Lưu ý về phép đếm:** trong bảng ta đếm **số nút được xét**, không đếm chính xác số lần thực thi toán tử `==` và `<`. Một nút có thể dùng hơn một phép so sánh nguyên thủy; điều này chỉ thay đổi hệ số hằng số với khóa số có so sánh `O(1)`.

## 5. Vì sao chèn dữ liệu tăng dần làm BST thông thường suy biến?

Bắt đầu với cây rỗng. Chèn lần lượt:

```text
10, 20, 30, 40, 50
```

Các bước:

**Chèn 10:** cây rỗng, tạo gốc `10`.

```text
10
```

**Chèn 20:** `20 > 10`, đi phải; liên kết rỗng, gắn `20`.

```text
10
  \
   20
```

**Chèn 30:** `30 > 10` → `30 > 20` → rỗng, gắn phía phải `20`.

```text
10
  \
   20
     \
      30
```

**Chèn 40 và 50:** mỗi khóa mới **lớn hơn toàn bộ khóa đã có**, nên phải đi qua **toàn bộ chuỗi con phải** để tới ô rỗng cuối.

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

Chiều cao sau các lần chèn là:

```text
Lượt chèn:  1  2  3  4  5
Chiều cao:  1  2  3  4  5
```

Khi có `n` khóa phân biệt tăng nghiêm ngặt, cây có `n` nút và `h=n`. Nó **vẫn là BST hợp lệ**, nhưng mất ưu thế của một cấu trúc tìm kiếm phân nhánh.

### Tổng quát hóa

Giả sử trước khi chèn `k_i`, các khóa đã có đều nhỏ hơn `k_i`. Thuật toán chèn không thể rẽ trái ở bất kỳ nút nào; nó đi từ gốc qua mọi nút của cây lệch phải rồi tạo con phải mới.

Không có phép quay, xây lại hoặc cân bằng nào xảy ra trong BST thông thường. **Chèn đúng bất biến không có nghĩa chèn tối ưu chiều cao.**

## 6. Dữ liệu giảm dần tạo cây lệch trái đối xứng

Chèn:

```text
50, 40, 30, 20, 10
```

Mỗi khóa mới nhỏ hơn mọi khóa đã có, nên luôn đi **trái** tới cuối đường:

```text
           50
          /
         40
        /
       30
      /
     20
    /
   10
```

Đây là ảnh gương của trường hợp tăng dần. Chiều cao vẫn bằng số nút.

Vì vậy, **cả dữ liệu đã sắp tăng lẫn dữ liệu đã sắp giảm đều nguy hiểm** nếu nạp tuần tự vào BST thường.

### Dữ liệu gần có thứ tự cũng cần thận trọng

Không chỉ dãy tăng/giảm **hoàn hảo** mới gây cây cao. Một tệp được sắp chủ yếu theo thời gian, với một vài mục đến trễ hoặc hoán đổi cục bộ, vẫn có thể tạo những nhánh dài.

Không có công thức chung rằng “chỉ lệch vài vị trí thì chiều cao chắc chắn nhỏ”. Chiều cao phụ thuộc vào **toàn bộ thứ tự chèn và cấu trúc cây hình thành**. Bản chất của rủi ro là **BST không tự đặt giới hạn cho độ chênh chiều cao giữa các nhánh**.

## 7. Tổng chi phí xây cây từ dữ liệu tăng dần là Θ(n²)

Khi chèn tuần tự `n` khóa tăng nghiêm ngặt vào BST rỗng **không tự cân bằng**:

- Khóa thứ nhất vào cây rỗng, không cần xét nút cũ.
- Khóa thứ hai xét 1 nút cũ.
- Khóa thứ ba xét 2 nút cũ.
- ...
- Khóa thứ `n` xét `n-1` nút cũ.

Tổng số lần **xét nút cũ** là:

```text
0 + 1 + 2 + ... + (n - 1)
= n(n - 1) / 2
```

Do đó, tổng thời gian xây BST bằng các phép chèn thông thường với đầu vào đã sắp là:

```text
T_build(n) = Θ(n²)
```

Với `n = 5`, các lượt xét nút cũ lần lượt là `0, 1, 2, 3, 4`, tổng `10`.

Với `n = 15`, tổng là:

```text
15 × 14 / 2 = 105 lượt xét nút cũ
```

Với `n = 1.000`, con số tăng lên `499.500` lượt xét nút cũ. Các số này đo thao tác **đi qua nút trong đường chèn**, không phải thời gian thực chạy trên phần cứng cụ thể.

### Phân biệt một lần chèn và cả quá trình xây

| Bài toán | BST cân đối | BST suy biến do thứ tự tăng/giảm |
| --- | --- | --- |
| Một lần chèn ở trường hợp xấu nhất | `O(log n)` | `O(n)` |
| Xây `n` khóa bằng chèn lần lượt | `O(n log n)` nếu chiều cao được giữ logarit | `Θ(n²)` |
| Bộ nhớ lưu các nút | `O(n)` | `O(n)` |
| Chiều cao cây thu được | `O(log n)` | `Θ(n)` |

**Chú ý:** `O(n log n)` cho việc chèn nhiều khóa đòi hỏi điều kiện các cây trung gian có chiều cao `O(log n)`, chẳng hạn dùng cây tự cân bằng. Đừng mặc định mọi thứ tự đầu vào của BST thường đều cho kết quả ấy.

## 8. Vì sao dữ liệu đã sắp là đầu vào rất thường gặp?

Không phải cứ người dùng nhập dữ liệu ngẫu nhiên. Trong thực tế, dữ liệu có thể đã được **sắp trước** vì nhu cầu khác:

- Tệp CSV xuất từ hệ thống quản lý đã có `ORDER BY student_id`.
- Thời gian đăng ký, timestamp hoặc số thứ tự tăng dần.
- ID tự tăng từ cơ sở dữ liệu.
- Danh sách từ một API đã trả theo khóa.
- Một chỉ mục cũ được duyệt in-order rồi dùng để dựng lại chỉ mục mới.
- Một chương trình **sắp xếp trước khi chèn**, vì tưởng rằng dữ liệu đã sắp sẽ giúp cây tìm kiếm nhanh hơn.

Điểm nguy hiểm trong trường hợp cuối là sự nhầm lẫn giữa hai cấu trúc:

- **Mảng đã sắp:** tìm nhị phân bằng chỉ số hoạt động tốt trên mảng đã sắp.
- **BST thường được xây bằng chèn lần lượt:** nạp dãy đã sắp theo đúng thứ tự ấy có thể làm cây lệch nhất.

**Sắp xếp trước khi chèn lần lượt vào BST thường không phải một bước cân bằng cây.** Trái lại, đó có thể là một trong những thứ tự chèn tệ nhất.

## 9. Chiều cao tác động tới từng thao tác như thế nào?

Gọi `h` là chiều cao theo số nút, `n` là số nút, và `k` là số mục thực sự được xuất khi duyệt một khoảng.

| Thao tác trên BST thường | Thời gian tổng quát | Nếu cây cao `O(log n)` | Nếu cây lệch `h=Θ(n)` |
| --- | --- | --- | --- |
| Tìm khóa chính xác | `O(h)` | `O(log n)` | `O(n)` |
| Chèn một khóa | `O(h)` | `O(log n)` | `O(n)` |
| Xóa nút lá/một con | `O(h)` để tìm, `O(1)` để nối | `O(log n)` | `O(n)` |
| Xóa nút hai con | `O(h)` gồm tìm nút và cực trị | `O(log n)` | `O(n)` |
| Tìm minimum/maximum | `O(h)` | `O(log n)` | `O(n)` trong tình huống xấu |
| Tìm tiền nhiệm/kế nhiệm | `O(h)` | `O(log n)` | `O(n)` |
| Tìm lower/upper bound | `O(h)` | `O(log n)` | `O(n)` |
| Truy vấn khoảng xuất `k` mục bằng iterator tốt | `O(h+k)` | `O(log n+k)` | `O(n+k)` |
| Duyệt giữa toàn cây | `Θ(n)` | `Θ(n)` | `Θ(n)` |

Một số điểm tinh tế:

1. **Không phải mọi thao tác đều bắt buộc mất `Θ(h)`.** Tìm khóa ở gốc tốn `O(1)`; minimum của cây lệch phải cũng có thể ở ngay gốc.
2. **Duyệt toàn cây vẫn `Θ(n)`** ngay cả khi cây suy biến, vì mỗi nút được thăm một lần; khác biệt lớn hơn nằm ở bộ nhớ stack và các thao tác định vị.
3. **`O(h+k)` cho truy vấn khoảng** giả định dùng thuật toán cắt tỉa hoặc iterator chia sẻ trạng thái. Nếu tìm lại successor từ gốc cho từng mục, tổng chi phí có thể xấu hơn.
4. Xóa một nút có thể làm chiều cao giảm, nhưng **BST thường không tự cân bằng lại** để duy trì `O(log n)` về lâu dài.

### Bộ nhớ phụ cũng phụ thuộc cách hiện thực

| Cách làm | Bộ nhớ phụ điển hình |
| --- | --- |
| Tìm/chèn/xóa bằng vòng lặp và vài con trỏ | `O(1)` |
| Tìm/chèn/xóa đệ quy | `O(h)` cho call stack |
| Duyệt giữa bằng stack hoặc đệ quy | `O(h)` |
| Duyệt giữa và lưu toàn bộ khóa vào list | `O(h)` stack và `O(n)` đầu ra |
| Cài Morris in-order (sửa liên kết tạm) | `O(1)` điều hướng nhưng có rủi ro thay đổi cấu trúc |

Ở BST lệch, mã đệ quy có thể phát sinh lỗi **vượt giới hạn ngăn xếp**, ví dụ `RecursionError` trong Python. Bản lặp tránh giới hạn đệ quy đó, **nhưng vẫn không làm thời gian tìm kiếm trở nên logarit**.

## 10. Python: BST không cân bằng và đếm độ dài đường đi

Chúng ta sẽ dùng một hiện thực Python tự chứa cho **BST-set khóa nguyên duy nhất**, không có phép quay.

Để nhìn rõ hiệu ứng của hình dạng cây, phương thức `insert` trả `(inserted, visited)`: `visited` là số **nút cũ được xét** trước khi tạo nút mới hoặc gặp khóa đã có. `search_with_steps` trả cờ tìm thấy và số nút đã thăm.

### Cài đặt Node và BST

```python
class Node:
    def __init__(self, key):
        self.key = key
        self.left = None
        self.right = None


class BST:
    def __init__(self):
        self.root = None
        self.size = 0

    def insert(self, key):
        """Trả (inserted, visited_old_nodes)."""
        if self.root is None:
            self.root = Node(key)
            self.size = 1
            return True, 0

        current = self.root
        visited = 0

        while True:
            visited += 1

            if key == current.key:
                return False, visited

            if key < current.key:
                if current.left is None:
                    current.left = Node(key)
                    self.size += 1
                    return True, visited
                current = current.left
            else:
                if current.right is None:
                    current.right = Node(key)
                    self.size += 1
                    return True, visited
                current = current.right

    def search_with_steps(self, key):
        """Trả (found, visited_nodes)."""
        current = self.root
        visited = 0

        while current is not None:
            visited += 1

            if key == current.key:
                return True, visited

            current = (
                current.left if key < current.key
                else current.right
            )

        return False, visited

    def height(self):
        """Đo chiều cao theo số nút, không dùng đệ quy."""
        if self.root is None:
            return 0

        stack = [(self.root, 1)]
        maximum = 0

        while stack:
            node, depth = stack.pop()
            maximum = max(maximum, depth)

            if node.left is not None:
                stack.append((node.left, depth + 1))
            if node.right is not None:
                stack.append((node.right, depth + 1))

        return maximum

    def inorder(self):
        result = []
        stack = []
        current = self.root

        while stack or current is not None:
            while current is not None:
                stack.append(current)
                current = current.left

            current = stack.pop()
            result.append(current.key)
            current = current.right

        return result
```

### Hai lưu ý về phép đo

- `height()` trong mã là **hàm chẩn đoán**, duyệt cả cây trong `O(n)` thời gian và dùng tới `O(h)` stack. Không nên tính lại chiều cao sau **mọi** lần tìm kiếm rồi đưa chi phí ấy vào thuật toán cơ bản.
- `visited` đo số nút đã gặp trong đường chèn/tìm, **không phải thời gian tính bằng giây**. Phép so sánh với chuỗi dài có thể tốn nhiều thời gian hơn phép so sánh hai số nguyên dù số nút thăm bằng nhau.

## 11. Kiểm chứng: chèn tăng dần làm h = n

Tạo cây bằng các khóa `1..15` theo đúng thứ tự:

```python
ascending = BST()
total_visited = 0

for key in range(1, 16):
    inserted, visited = ascending.insert(key)
    assert inserted
    total_visited += visited

assert ascending.size == 15
assert ascending.height() == 15
assert ascending.inorder() == list(range(1, 16))

assert ascending.search_with_steps(1) == (True, 1)
assert ascending.search_with_steps(15) == (True, 15)
assert ascending.search_with_steps(16) == (False, 15)

assert total_visited == 15 * 14 // 2 == 105
```

Phép kiểm tra `inorder()` vẫn trả **dãy tăng**: BST không sai bất biến. Vấn đề là đường tìm khóa cuối cùng dài tới `15` nút.

### Thử với thứ tự giảm dần

```python
descending = BST()

for key in range(15, 0, -1):
    inserted, _ = descending.insert(key)
    assert inserted

assert descending.height() == 15
assert descending.search_with_steps(1) == (True, 15)
assert descending.search_with_steps(15) == (True, 1)
assert descending.inorder() == list(range(1, 16))
```

Hai cây có hình dạng đối xứng. Tập khóa và kết quả in-order giống nhau, nhưng khóa nằm gần gốc thay đổi theo **thứ tự được chèn đầu tiên**.

### Kết quả với cây rỗng và khóa trùng

```python
empty = BST()
assert empty.height() == 0
assert empty.search_with_steps(10) == (False, 0)
assert empty.inorder() == []

inserted, visited = ascending.insert(15)

assert inserted is False
assert visited == 15
assert ascending.size == 15
assert ascending.height() == 15
```

Với BST-set khóa duy nhất, chèn lại khóa cũ không tạo nút, nhưng **vẫn phải đi tới nút chứa khóa ấy**. Khóa trùng ở sâu có thể tốn `O(h)` như tìm kiếm.

## 12. Cùng tập khóa: đổi thứ tự chèn để tạo cây thấp hơn

Một cây cân đối hơn có thể xuất hiện nếu ta chèn **trung vị trước**, rồi lần lượt trung vị của mỗi nửa.

Với dãy `1..15`, một thứ tự phù hợp là:

```text
8, 4, 2, 1, 3, 6, 5, 7,
12, 10, 9, 11, 14, 13, 15
```

Cây cuối:

```text
                     8
                 /       \
                4         12
              /   \      /   \
             2     6    10    14
            / \   / \  / \   /  \
           1   3 5   7 9  11 13  15
```

Chiều cao chỉ còn **`h=4`**, thay vì 15. Cả hai cây đều là BST hợp lệ với **chính xác cùng 15 khóa**.

### Sinh thứ tự chèn trung vị trước

```python
def median_first(sorted_keys):
    """Sinh khóa ở giữa trước, rồi nửa trái và nửa phải."""
    if not sorted_keys:
        return

    middle = len(sorted_keys) // 2
    yield sorted_keys[middle]
    yield from median_first(sorted_keys[:middle])
    yield from median_first(sorted_keys[middle + 1:])


balanced_by_order = BST()

for key in median_first(list(range(1, 16))):
    balanced_by_order.insert(key)

assert balanced_by_order.size == 15
assert balanced_by_order.height() == 4
assert balanced_by_order.inorder() == list(range(1, 16))

assert balanced_by_order.search_with_steps(8) == (True, 1)
assert balanced_by_order.search_with_steps(15) == (True, 4)
assert balanced_by_order.search_with_steps(16) == (False, 4)
```

Vì các nút được chèn theo thứ tự trung vị trước, mỗi nút được đặt vào một vị trí thuộc cây cân đối cuối cùng. Khi dữ liệu là dãy khóa phân biệt đã sắp và ta **được phép quyết định lại thứ tự chèn**, chiến lược này giúp xây được cây thấp.

**Nhưng:** đây là một **kỹ thuật nạp dữ liệu một lần**, không tự làm cho những lần chèn sau đó được cân bằng. Nếu tiếp tục chèn dãy `16,17,18,...` vào cây vừa dựng mà không có bước cân bằng, nhánh phải có thể dài dần.

## 13. Có dữ liệu đã sắp? Dựng BST cân đối trực tiếp trong O(n)

Nếu đã có **mảng khóa phân biệt được sắp tăng dần**, ta không bắt buộc phải gọi `insert` cho từng khóa.

Có thể **dựng cây trực tiếp**:

1. Lấy phần tử giữa của đoạn mảng làm nút gốc.
2. Dựng đệ quy nửa trái thành cây con trái.
3. Dựng đệ quy nửa phải thành cây con phải.

Vì mỗi phần tử chỉ được dùng để tạo **một nút**, quá trình dựng trực tiếp có thể mất `O(n)` thời gian và `O(log n)` bộ nhớ ngăn xếp đệ quy đối với cách chia gần đôi.

### Mã Python

```python
def build_balanced_from_sorted(sorted_keys):
    """Trả root của BST cân đối từ khóa tăng nghiêm ngặt."""
    if any(
        sorted_keys[i - 1] >= sorted_keys[i]
        for i in range(1, len(sorted_keys))
    ):
        raise ValueError("Cần khóa phân biệt đã sắp tăng")

    def build(lo, hi):
        if lo >= hi:
            return None

        middle = (lo + hi) // 2
        node = Node(sorted_keys[middle])

        node.left = build(lo, middle)
        node.right = build(middle + 1, hi)
        return node

    return build(0, len(sorted_keys))


from_sorted = BST()
from_sorted.root = build_balanced_from_sorted(
    list(range(1, 16))
)
from_sorted.size = 15

assert from_sorted.height() == 4
assert from_sorted.inorder() == list(range(1, 16))
assert from_sorted.search_with_steps(15) == (True, 4)
```

Ở đây, bước kiểm tra dãy đã sắp và dựng cây đều tốn `O(n)` thời gian. Bộ nhớ để **lưu 15 nút** vẫn là `O(n)`; `O(log n)` chỉ mô tả **bộ nhớ phụ của quá trình đệ quy dựng cây**.

### So sánh ba phương pháp nạp dữ liệu

| Cách nạp một mảng đã sắp | Hình dạng cuối | Thời gian dựng |
| --- | --- | --- |
| `insert` từng khóa từ nhỏ tới lớn vào BST thường | Lệch phải, `h=n` | `Θ(n²)` |
| Chèn theo thứ tự **trung vị trước** vào BST thường | Cân đối, `h=O(log n)` | `O(n log n)` |
| **Dựng trực tiếp** từ đoạn mảng và trung vị | Cân đối, `h=O(log n)` | **`O(n)`** |

**Phân biệt rõ:** “dữ liệu đã sắp” chỉ là **đầu vào**. Nó trở thành lợi thế khi dùng đúng thuật toán **dựng trực tiếp**, không phải khi cứ chèn lần lượt vào BST không cân bằng.

## 14. Trung vị giúp giảm chiều cao, nhưng không thay thế tự cân bằng

Giả sử một cây được dựng cân đối từ `1..15`. Nếu sau đó có các lượt chèn:

```text
16, 17, 18, 19, 20, ...
```

Vì những khóa này **lớn hơn tất cả khóa trước**, chúng có thể liên tục kéo dài nhánh ngoài cùng bên phải của cây. Không có thao tác nào trong lớp `BST` ở trên quay hay tổ chức lại các nút cũ.

**Dựng cân đối ban đầu ≠ duy trì cân đối suốt vòng đời.**

Để duy trì chiều cao khi có **nhiều cập nhật động**, cần một cấu trúc có **quy tắc cân bằng đi kèm thao tác chèn/xóa**, hoặc một chiến lược xây lại định kỳ với hợp đồng phù hợp.

### AVL và cây đỏ–đen

Cả **AVL** và **red–black tree** đều là BST theo thứ tự khóa, nhưng chúng thêm bất biến cấu trúc để giữ chiều cao `O(log n)`.

- **AVL:** duy trì chênh lệch chiều cao giữa hai cây con ở mỗi nút trong một giới hạn hẹp; khi chèn/xóa có thể cập nhật chiều cao và quay.
- **Cây đỏ–đen:** dùng quy tắc màu và chiều cao đen để kiểm soát độ dài các đường; khi chèn/xóa có thể đổi màu và quay.

Do đó, với các cài đặt đúng:

```text
search: O(log n) trường hợp xấu nhất
insert: O(log n) trường hợp xấu nhất
delete: O(log n) trường hợp xấu nhất
```

Phép quay giữ thứ tự in-order nhưng thay cấu trúc liên kết, vì vậy nếu cài cây có `parent`, `height`, `subtree_size`... phải cập nhật metadata liên quan. Không thể chỉ lấy lớp BST thường rồi gắn nhãn “AVL” mà không bổ sung logic cân bằng.

## 15. Ngẫu nhiên hóa thứ tự chèn: lợi ích và giới hạn

Nếu `n` khóa **phân biệt** được chèn vào BST rỗng theo một **hoán vị ngẫu nhiên đều**, hình dạng cây phân phối theo thứ tự chèn ngẫu nhiên. Trong mô hình này, **chiều cao kỳ vọng `O(log n)`** và chi phí tìm/chèn có thể đạt `O(log n)` theo kỳ vọng dưới các giả thiết tương ứng.

Nhưng cần đọc kỹ từ **“kỳ vọng”**:

- Nó **không** có nghĩa mọi hoán vị đều tạo cây thấp.
- Hoán vị tăng hoặc giảm vẫn có thể xuất hiện, cho chiều cao `n`.
- Một dữ liệu được gọi là “khá ngẫu nhiên” trong nghiệp vụ chưa chắc tương đương hoán vị đều.
- Không có bảo đảm trường hợp xấu nhất `O(log n)` cho **BST thường** chỉ nhờ đầu vào hiện tại có vẻ phân tán.

### Ví dụ xáo trộn khóa trước khi chèn

```python
import random

numbers = list(range(1, 101))
rng = random.Random(2026)
rng.shuffle(numbers)

random_order_tree = BST()
for key in numbers:
    random_order_tree.insert(key)

assert random_order_tree.size == 100
assert random_order_tree.inorder() == list(range(1, 101))

# Không assert một chiều cao cụ thể:
# hình dạng thay đổi theo hoán vị và seed.
print("height:", random_order_tree.height())
```

Đây là **thử nghiệm dành cho người học**, không phải benchmark và không phải bảo đảm độ phức tạp.

**Lưu ý an toàn hiệu năng:** với đầu vào có thể do người ngoài điều khiển, đừng dựa duy nhất vào sự “ngẫu nhiên tự nhiên” của dữ liệu để tránh trường hợp xấu nhất. Nếu cần giới hạn rõ ràng, hãy chọn cây tự cân bằng hoặc thuật toán với bảo đảm phù hợp.

## 16. Vì sao một số trường hợp không suy biến dù khóa đã tăng?

Cần phát biểu chính xác: **“BST không tự cân bằng suy biến khi chèn tuần tự các khóa phân biệt tăng/giảm”**, không phải “mọi BST gặp dữ liệu đã sắp đều suy biến”.

Những tình huống không áp dụng trực tiếp kết luận ấy:

1. **Cây tự cân bằng:** những lần chèn có phép quay hoặc cơ chế duy trì chiều cao.
2. **Dựng trực tiếp từ mảng đã sắp:** chọn trung vị để tạo cây cân đối.
3. **Chèn theo thứ tự đã sắp lại để cân bằng:** thứ tự chèn thực tế không còn tăng/giảm.
4. **Khóa trùng bị gom tại nút:** nhiều lượt thêm cùng một khóa không tạo chuỗi nút mới.
5. **Một BST ban đầu đã tồn tại với nhiều nhánh:** kết quả phụ thuộc trạng thái cây trước khi thêm dãy, dù một chuỗi khóa lớn dần vẫn có thể kéo dài một nhánh.

**Nhận biết chính sách khóa trùng:** nếu dữ liệu `10, 10, 10, 10` được thêm vào một **BST-set** chỉ lưu một nút cho mỗi khóa, cây vẫn có **một nút**. Nếu triển khai **multiset với `count`**, nút `10` chỉ tăng đếm. Hai tình huống ấy khác với `10, 20, 30, 40` là **bốn khóa phân biệt tăng dần**.

### Vấn đề comparator

Có thể thấy chuỗi khóa nhìn bằng mắt không tăng theo thứ tự chữ cái thông thường, nhưng lại **tăng nghiêm ngặt theo comparator của cây**.

Ví dụ:

- Một hệ thống sắp các mã `"HV2"` và `"HV10"` theo phần số.
- Một cây sắp thời gian theo timestamp thay vì chuỗi hiển thị.
- Một tree set sắp không phân biệt chữ hoa/chữ thường.

**Thứ tự “tăng dần” quan trọng là tăng theo cùng comparator dùng để chèn BST.** Nếu comparator coi nhiều mã là tương đương, số nút phân biệt và hình dạng cây cũng thay đổi.

## 17. Xóa nút có tự chữa cây lệch không?

Không có bảo đảm như vậy.

Trong BST thường, xóa một nút có thể:

- Bỏ một lá ở cuối chuỗi, khiến chiều cao giảm 1.
- Bỏ một nút một con và nối con của nó lên trên, vẫn để lại một chuỗi dài.
- Với nút hai con, thay bằng tiền nhiệm/kế nhiệm và tháo nút thay thế, giữ thứ tự BST nhưng không thiết lập bất biến cân bằng.

Ví dụ:

```text
Trước:
10 → 20 → 30 → 40 → 50

Xóa 30 (nút có một con phải):
10 → 20 → 40 → 50

Chiều cao giảm từ 5 xuống 4,
nhưng cây vẫn là một chuỗi.
```

Một BST bình thường có thể **tình cờ** trở nên cân đối hơn sau vài lần xóa/chèn, nhưng không có thuật toán bắt buộc nó phải giữ chiều cao `O(log n)`.

Nếu cấu trúc cần bảo đảm hiệu năng sau **mọi** cập nhật, phải có chiến lược cân bằng chuyên biệt chứ không chỉ mong đợi dữ liệu tự cải thiện hình dạng.

## 18. Tìm kiếm thành công, thất bại và thời gian kỳ vọng

Khi phân tích hiệu năng, cần biết đang nói về:

1. **Trường hợp tốt nhất** của một truy vấn: ví dụ gặp đúng khóa ở gốc, `Θ(1)`.
2. **Trường hợp xấu nhất**: đường tìm đi sâu nhất, `O(h)` và có thể `Θ(n)`.
3. **Trường hợp trung bình/kỳ vọng**: phải nói rõ **mô hình phân phối dữ liệu hoặc truy vấn**.

Chẳng hạn, trên BST suy biến lưu `1..n` theo chuỗi phải, nếu chọn **đều một trong n khóa** để tìm thành công, số nút được xét trung bình là:

```text
(1 + 2 + ... + n) / n
= (n + 1) / 2
= Θ(n)
```

Như vậy, vấn đề suy biến không chỉ xảy ra với **một khóa ở cuối chuỗi**. Với phân phối truy vấn đều trên tất cả khóa của cây lệch, **chi phí trung bình cũng tuyến tính**.

Ngược lại, đối với một BST cân đối, mọi nút có độ sâu tối đa `O(log n)`, nên mọi truy vấn tìm theo khóa đều có giới hạn `O(log n)`.

### Không suy từ một mẫu đo sang bảo đảm tổng quát

Một lần đo nhanh trên cây ít nút chưa chứng minh cấu trúc có `O(log n)`. Chạy thời gian trên môi trường máy tính còn chịu ảnh hưởng của bộ nhớ đệm, trình thông dịch, trình biên dịch và chi phí so sánh kiểu dữ liệu.

Để lý giải độ phức tạp, hãy kiểm tra **bất biến chiều cao, mô hình đầu vào và đường đi thuật toán** trước khi nhìn số liệu đo.

## 19. Chi phí so sánh khóa và kích thước dữ liệu thực tế

Các bảng `O(h)` trước đây thường coi phép so sánh hai khóa là `O(1)`. Giả thiết ấy tự nhiên với nhiều kiểu số nguyên máy, nhưng không đúng tuyệt đối với mọi kiểu khóa.

Ví dụ nếu khóa là chuỗi dài tối đa `L` ký tự, một phép so sánh thứ tự có thể tốn `O(L)` trong tình huống nhiều ký tự đầu trùng nhau.

Một đường tìm qua `h` nút khi đó có thể tốn:

```text
O(h · L)
```

Tương tự, comparator tự viết có thể phải chuẩn hóa Unicode, phân tích mã số hoặc so nhiều trường của tuple. **Chiều cao thấp giúp giảm số nút thăm**, nhưng không thay thế việc thiết kế **quy tắc khóa và comparator** hiệu quả.

### Không sửa khóa đã nằm trong cây

Nếu thay đổi trường tham gia so sánh của một đối tượng khóa **ngay tại vị trí nút cũ**, thứ tự BST có thể bị phá. Khi đó, các kết luận về tìm kiếm và chiều cao theo đường so sánh không còn bảo đảm đúng ngữ nghĩa.

Thông thường, muốn đổi khóa, ta cần **xóa khóa cũ rồi chèn khóa mới** hoặc duy trì chỉ mục riêng đúng theo chính sách của hệ thống.

## 20. Lựa chọn cấu trúc phù hợp với đặc điểm đầu vào

Không có lựa chọn nào luôn tốt nhất. Bảng sau so sánh một số phương án khi cần lưu khóa có thứ tự:

| Cấu trúc | Tìm khóa | Chèn/xóa | Truy vấn thứ tự/khoảng | Ghi chú |
| --- | --- | --- | --- | --- |
| **BST thường** | `O(h)`, xấu nhất `O(n)` | `O(h)` | `O(h+k)` nếu duyệt đúng | Dễ học nhưng có thể suy biến |
| **AVL / đỏ–đen** | `O(log n)` xấu nhất | `O(log n)` xấu nhất | `O(log n+k)` | Duy trì chiều cao bằng bất biến cân bằng |
| **Mảng đã sắp** | `O(log n)` bằng tìm nhị phân | Có thể `O(n)` do dịch phần tử | `O(log n+k)` | Tốt với dữ liệu tĩnh/ít cập nhật |
| **Hash map / hash set** | Trung bình `O(1)` cho tra cứu chính xác | Trung bình `O(1)` | Không mặc nhiên có thứ tự khóa | Phù hợp khi không cần range/order |
| **B-tree/B+ tree** | Phụ thuộc bậc cây và mô hình lưu trữ, thường logarit theo số khóa | Được tối ưu cho khối lưu trữ | Hỗ trợ range scan | Hay dùng cho chỉ mục lưu trên đĩa |

Trong bảng, `k` là số mục thực sự xuất trong một truy vấn khoảng, và `h` là chiều cao BST thường.

### Gợi ý chọn theo tình huống

- **Một lần nạp dữ liệu đã sắp, đọc rất nhiều, ít cập nhật:** cân nhắc **mảng đã sắp** hoặc **dựng trực tiếp BST cân đối từ trung vị**.
- **Thường xuyên chèn/xóa và cần thứ tự khóa:** chọn **cây tự cân bằng** hoặc thư viện ordered map/set phù hợp.
- **Chỉ tìm ID chính xác, không cần khoảng hay thứ tự:** cân nhắc **bảng băm**, đồng thời hiểu sự khác nhau giữa trung bình và trường hợp xấu.
- **Dữ liệu lớn trong hệ thống lưu trữ/SQL:** ưu tiên chỉ mục cơ sở dữ liệu được thiết kế cho truy vấn.
- **Mục đích học thuật hoặc tập dữ liệu nhỏ:** BST thường giúp nhìn thấy rõ bất biến, thao tác và vì sao việc cân bằng có giá trị.

## 21. Checklist đánh giá rủi ro suy biến

Khi chuẩn bị sử dụng BST, nên tự trả lời:

1. Dữ liệu có **đã sắp tăng hoặc giảm** theo comparator không?
2. Các khóa mới có xu hướng **tăng dần theo thời gian**, như timestamp hoặc ID tự tăng không?
3. Cấu trúc có **tự cân bằng** sau mỗi chèn/xóa hay chỉ bảo toàn thứ tự BST?
4. Có cần **bảo đảm trường hợp xấu nhất** hay chấp nhận bảo đảm kỳ vọng?
5. Chiều cao `h` có được theo dõi, hoặc có kiểm thử các thứ tự chèn bất lợi không?
6. Có thường xuyên thực hiện **range query** hoặc tìm predecessor/successor không?
7. Có thể **dựng trực tiếp** cây cân đối từ một mảng đã sắp thay vì chèn tuần tự không?
8. Có thể dùng **mảng đã sắp** nếu phần lớn dữ liệu tĩnh không?
9. Những khóa bị comparator coi là bằng nhau được **gom như thế nào**?
10. Có xử lý được cây rất sâu khi dùng **đệ quy** không?
11. Các phép so sánh khóa có chi phí hằng số hay phụ thuộc vào độ dài dữ liệu?
12. Hiệu năng được đánh giá bằng **độ phức tạp theo h**, không chỉ bằng một lần đo có vẻ nhanh, đúng không?

Nếu đầu vào đã sắp và BST không có cơ chế cân bằng, cần xem đó là **một nguy cơ cấu trúc có thể dự đoán**, không phải ngoại lệ hiếm gặp.

## 22. Lỗi thường gặp khi phân tích độ phức tạp BST

1. **Viết `search = O(log n)` cho mọi BST.** Tổng quát phải là `O(h)`; `O(log n)` cần chiều cao nhỏ.
2. **Nhầm BST hợp lệ với BST cân bằng.** Cây một nhánh vẫn thỏa bất biến thứ tự.
3. **Chỉ xét số nút `n` mà không xét `h`.** Hai cây cùng `n` có thể có đường tìm rất khác.
4. **Cho rằng dữ liệu đã sắp luôn có lợi.** Với chèn tuần tự vào BST thường, nó có thể gây cây lệch nhất.
5. **Chỉ xét một lần chèn, bỏ tổng chi phí dựng cây.** Dãy tăng dần có thể cho `Θ(n²)` thời gian xây.
6. **Coi xóa nút tự động cân bằng lại cây.** BST thường không có yêu cầu đó.
7. **Coi việc dùng vòng lặp là khắc phục độ phức tạp.** Vòng lặp giảm bộ nhớ phụ so với đệ quy, không giảm số nút phải đi qua.
8. **Bỏ qua cây rỗng và cây một nút khi định nghĩa h.** Dễ gây sai lệch khi tính chiều cao.
9. **Nhầm số cạnh và số nút khi mô tả chiều cao.** Big-O không đổi nhưng phép kiểm thử giá trị cụ thể có thể sai.
10. **Lấy `O(h)` rồi kết luận duyệt toàn cây là `O(nh)`.** In-order dùng lại stack và thăm mỗi nút một lần, `Θ(n)`.
11. **Giả định trộn thứ tự chèn một lần sẽ bảo đảm hiệu năng vĩnh viễn.** Các cập nhật tương lai có thể làm BST thường lệch.
12. **Trộn lẫn kỳ vọng và trường hợp xấu nhất.** Cây từ hoán vị ngẫu nhiên có thể có kỳ vọng tốt nhưng không bảo đảm mọi thứ tự.
13. **Bỏ qua chính sách khóa trùng.** Một triệu lượt cập nhật cùng khóa không tạo một triệu nút nếu map/set gom trùng.
14. **So sánh các khóa theo nhiều quy tắc khác nhau.** “Dữ liệu đã sắp” phải được hiểu theo chính comparator của BST.
15. **Đo h sau mỗi lần thao tác bằng cách duyệt toàn cây** rồi tính nhầm đó là chi phí vốn có của search/insert.
16. **Nhầm `O(n)` bộ nhớ lưu trữ các nút với `O(1)` bộ nhớ phụ của một lần tìm lặp.** Đây là hai đại lượng khác nhau.
17. **Dùng dữ liệu thử nghiệm quá nhỏ** rồi suy rộng rằng cây luôn cân đối.
18. **Tin chiều cao cân đối ban đầu có nghĩa cây sẽ tự cân bằng sau chèn/xóa.** Dựng cân đối và duy trì cân đối là hai bài toán khác nhau.

## 23. Bài tập tự luyện

**Bài 1.** Nêu bất biến BST và giải thích vì sao cây `10 → phải 20 → phải 30 → phải 40` vẫn là BST hợp lệ.

**Bài 2.** Dùng quy ước chiều cao bằng **số nút** trên đường gốc–lá, tính `h` của cây rỗng, cây một nút, cây hoàn hảo 7 nút và cây chuỗi 7 nút.

**Bài 3.** Với `n=15`, chiều cao nhỏ nhất và lớn nhất có thể là bao nhiêu? Vì sao?

**Bài 4.** Vẽ BST nhận dãy `[10,20,30,40,50]` theo thứ tự. Đếm số nút được xét khi tìm `50` và khi tìm khóa vắng mặt `60`.

**Bài 5.** Lặp lại bài 4 cho thứ tự chèn `[50,40,30,20,10]`. Cây lệch hướng nào và đường tìm khóa `10` dài bao nhiêu?

**Bài 6.** Chứng minh tổng số nút cũ được xét trong quá trình chèn `n` khóa phân biệt tăng dần vào BST rỗng là `n(n-1)/2`.

**Bài 7.** Với cây cân đối chứa các khóa `{10,20,30,40,50,60,70}` và gốc `40`, mô tả đường tìm `70`. So với cây lệch phải cùng tập, chi phí khác ra sao?

**Bài 8.** Vì sao một lượt in-order trên BST lệch vẫn chỉ mất `Θ(n)` thời gian, dù mỗi lần tìm ở cuối cây có thể `Θ(n)`?

**Bài 9.** Viết mã `height()` bằng stack để tránh đệ quy trên cây rất sâu. Giải thích thời gian và bộ nhớ phụ của phép đo chiều cao.

**Bài 10.** Với `1..15` đã sắp, hãy chọn thứ tự chèn giúp BST thường có chiều cao 4. Tại sao phải chọn trung vị trước?

**Bài 11.** So sánh chèn tuần tự dãy đã sắp, chèn trung vị trước và dựng trực tiếp từ mảng đã sắp về **thời gian dựng** và **chiều cao cuối**.

**Bài 12.** Một BST được dựng cân đối từ `1..15`, sau đó nhận liên tục `16..100`. Có bảo đảm `h=O(log n)` không? Tại sao?

**Bài 13.** Vì sao xáo trộn ngẫu nhiên thứ tự chèn có thể cải thiện **chi phí kỳ vọng** nhưng không bảo đảm trường hợp xấu nhất?

**Bài 14.** Một BST có `n` khóa thành chuỗi và truy vấn thành công chọn đều trên các khóa. Chi phí **trung bình** xét bao nhiêu nút? Nó thuộc bậc nào?

**Bài 15.** Dữ liệu `[10,10,10,10]` và `[10,20,30,40]` khác nhau như thế nào nếu BST-set từ chối khóa trùng? Chiều cao của cây thu được?

**Bài 16.** Vì sao phải xét cùng comparator khi nói một dãy khóa “đã được sắp”, nhất là với mã học viên `"HV2"` và `"HV10"`?

**Bài 17.** Chọn cấu trúc thích hợp cho ba kịch bản: (a) kho dữ liệu tĩnh đã sắp và tra cứu nhiều; (b) ordered map cập nhật thường xuyên; (c) chỉ tra cứu ID chính xác, không yêu cầu thứ tự.

**Bài 18.** Nếu một phép so sánh khóa chuỗi dài `L` ký tự có thể mất `O(L)`, hãy sửa lại ước lượng chi phí tìm khóa theo `h`.

<details>
<summary>Đáp án và gợi ý</summary>

1. Mọi khóa ở trái nhỏ hơn, mọi khóa ở phải lớn hơn nút xét và bất biến đúng tại mọi nút. Cây chuỗi phải thỏa thứ tự nhưng không cân đối.
2. Theo quy ước bài: `0, 1, 3, 7`.
3. Tối thiểu `ceil(log2(16))=4`; tối đa `15` nếu mọi nút nối thành một đường.
4. Cây lệch phải. Tìm `50` xét `5` nút; tìm `60` cũng xét `5` nút rồi gặp con phải rỗng.
5. Cây lệch trái. Tìm `10` xét `5` nút.
6. Trước lượt chèn thứ `i` có `i-1` nút và khóa mới lớn hơn mọi khóa cũ, nên đi qua `i-1` nút; cộng `0+1+...+(n-1)=n(n-1)/2=Θ(n²)`.
7. Cây cân đối: `40 → 60 → 70`, xét `3` nút. Cây lệch phải: `10 → 20 → 30 → 40 → 50 → 60 → 70`, xét `7` nút.
8. Một lượt in-order giữ trạng thái stack/đệ quy và thăm từng nút một lần; không khởi động lại tìm kiếm từ gốc cho mỗi nút.
9. Dùng stack các cặp `(node,depth)`, cập nhật chiều sâu lớn nhất; thăm toàn bộ `n` nút nên `O(n)` thời gian, stack DFS `O(h)` bộ nhớ phụ.
10. Chọn `8` làm gốc, `4` và `12` làm gốc hai nửa, tiếp tục chọn trung vị từng nửa. Cây có 4 tầng vì phân chia gần đều.
11. Chèn tăng tuần tự: cây `h=n` và `Θ(n²)` tổng chi phí. Chèn trung vị trước: `h=O(log n)` và `O(nlog n)` thời gian. Dựng trực tiếp: `h=O(log n)` và `O(n)` thời gian khi dãy đã sắp.
12. Không. BST không tự cân bằng có thể kéo dài nhánh phải khi các khóa mới tăng mãi.
13. Hoán vị ngẫu nhiên đều có chiều cao kỳ vọng logarit, nhưng một số hoán vị xấu vẫn có thể tạo cây chuỗi; kỳ vọng khác bảo đảm cho mọi đầu vào.
14. Trên chuỗi có độ sâu tìm `1,2,...,n`, trung bình `(n+1)/2 = Θ(n)` nút.
15. Dãy trùng `[10,10,10,10]` chỉ tạo **một nút**, `h=1`. Dãy khóa phân biệt tăng dần tạo **bốn nút lệch phải**, `h=4`.
16. Comparator có thể xếp theo phần số thay vì thứ tự chuỗi từ điển; sự đơn điệu phải hiểu theo đúng comparator dùng để xây BST.
17. (a) mảng đã sắp hoặc BST cân đối dựng trực tiếp; (b) AVL/đỏ–đen hoặc ordered map thư viện tương ứng; (c) hash map/hash set nếu nhu cầu là tra cứu khóa chính xác và chấp nhận hợp đồng hiệu năng của bảng băm.
18. `O(hL)` trong trường hợp xấu nếu mỗi lần so sánh có thể tốn `O(L)`; khi cây cân đối còn `O(Llog n)`, khi lệch có thể `O(nL)`.

</details>

## Ghi nhớ

**Độ phức tạp đúng cho thao tác tìm/chèn/xóa của BST thường là `O(h)` theo chiều cao `h`, không tự động là `O(log n)`.** Cây hợp lệ vẫn có thể **suy biến thành chuỗi `h=n`** khi chèn tuần tự các khóa **phân biệt đã sắp tăng hoặc giảm**, khiến một thao tác có thể tốn `O(n)` và tổng thời gian dựng `n` khóa thành **`Θ(n²)`**. Nếu đầu vào đã sắp và chủ yếu cần dựng một lần, hãy **chọn trung vị để dựng trực tiếp BST cân đối trong `O(n)`**, hoặc cân nhắc mảng đã sắp. Nếu cần cập nhật liên tục với bảo đảm trường hợp xấu nhất, hãy chọn **BST tự cân bằng** như AVL/cây đỏ–đen. Đừng nhầm **bảo toàn thứ tự khóa**, **bảo đảm chiều cao nhỏ** và **chi phí bộ nhớ phụ**: đó là ba thuộc tính cần phân tích riêng.

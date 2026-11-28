# Duyệt theo tầng bằng hàng đợi

Trong một cây phân cấp thư mục, có khi ta muốn liệt kê **những thư mục gần gốc trước**, rồi mới đi sâu vào các thư mục con. Trong cây giao diện người dùng, có thể cần xử lý mọi thành phần ở độ sâu 0, tiếp đến độ sâu 1, rồi độ sâu 2. Cách đi ấy gọi là **duyệt theo tầng (level-order traversal)**; thuật toán thường được thực hiện bằng **hàng đợi FIFO (First In, First Out)** và cũng là một dạng **tìm kiếm theo chiều rộng (Breadth-First Search, BFS)** trên cây.

Đây là bài **“Duyệt theo tầng bằng hàng đợi”** thuộc chương **Duyệt và biến đổi cây** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Module xây dựng nền tảng cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; bài này tập trung vào việc chọn **queue**, bảo toàn bất biến, phân tích **độ phức tạp thời gian/bộ nhớ** và vận dụng khi đọc hoặc biến đổi cây.

Mục tiêu sau bài học:

- Phát biểu đúng thứ tự duyệt theo tầng và phân biệt với preorder, inorder, postorder.
- Giải thích tại sao FIFO giúp các nút có độ sâu nhỏ được xử lý trước các nút sâu hơn.
- Viết BFS lặp không đệ quy, bao gồm kiểm tra cây rỗng và lưu kết quả theo từng tầng.
- Hiểu bất biến queue, lý do mỗi nút được xử lý đúng một lần và chi phí **O(n)** thời gian, **O(w)** bộ nhớ queue với `w` là độ rộng lớn nhất của một tầng.
- Nhận diện trường hợp cần ghi nhận độ sâu, tính chiều cao, tìm lá gần gốc, kiểm thử và tránh lỗi khi cây bị sửa trong lúc duyệt.

## 1. Duyệt theo tầng nghĩa là gì?

Xét cây nhị phân sau:

```text
                 8                   Tầng 0
              /     \
             3       10              Tầng 1
           /   \       \
          1     6       14           Tầng 2
               / \     /
              4   7   13             Tầng 3
```

**Tầng/độ sâu** (depth) của một nút là số cạnh trên đường đi từ **gốc** đến nút đó, nếu tính gốc ở độ sâu 0:

| Tầng | Các nút theo thứ tự trái → phải |
| --- | --- |
| 0 | `8` |
| 1 | `3, 10` |
| 2 | `1, 6, 14` |
| 3 | `4, 7, 13` |

Kết quả duyệt theo tầng, gộp thành một dãy:

```text
8, 3, 10, 1, 6, 14, 4, 7, 13
```

Định nghĩa: **thăm tất cả nút ở độ sâu d trước khi thăm bất kỳ nút nào ở độ sâu d+1**. Trong một tầng, với cây nhị phân và quy ước chèn con trái trước con phải, thứ tự là **từ trái sang phải**.

### 1.1. BFS khác DFS

**Duyệt theo chiều sâu (DFS)** sử dụng ngăn xếp (có thể là stack lời gọi đệ quy) để đi sâu trước khi quay lại. Với cây mẫu:

| Cách duyệt | Thứ tự |
| --- | --- |
| **Level-order (BFS)** | `8, 3, 10, 1, 6, 14, 4, 7, 13` |
| Preorder (gốc–trái–phải) | `8, 3, 1, 6, 4, 7, 10, 14, 13` |
| Inorder (trái–gốc–phải) | `1, 3, 4, 6, 7, 8, 10, 13, 14` |
| Postorder (trái–phải–gốc) | `1, 4, 7, 6, 3, 13, 14, 10, 8` |

BFS **không** đồng nghĩa “đi theo nhánh trái đến lá rồi chuyển sang phải”. Tại độ sâu 1, BFS phải thăm cả `3` và `10` trước khi đi tới `1` ở độ sâu 2.

BFS thuận tiện khi ta cần **thứ tự theo khoảng cách cạnh từ gốc**. DFS thuận tiện cho nhiều bài toán cần xử lý cây con trước/sau cha như tính biểu thức, duyệt hậu tự để giải phóng cây hoặc tổng hợp dữ liệu đệ quy. Không có cách nào tối ưu tuyệt đối cho mọi yêu cầu.

### 1.2. Cây rỗng và cây một nút

```text
Cây rỗng:       root = NULL         kết quả: []

Cây một nút:    root -> [5]         kết quả: [5]
```

BFS không được dereference gốc rỗng. Khi cây chỉ có một nút, thuật toán đưa gốc vào queue, xử lý gốc một lần và kết thúc vì không có con nào được thêm.

## 2. Vì sao phải dùng hàng đợi FIFO?

**Queue** giữ các phần tử theo thứ tự được thêm: `enqueue(x)` thêm vào **cuối**, `dequeue()` lấy từ **đầu**. BFS lần lượt:

1. Đưa nút gốc vào queue nếu cây không rỗng.
2. Lấy một nút từ đầu queue, xử lý giá trị của nó.
3. Đưa các con tồn tại của nút ấy vào cuối queue, từ trái sang phải.
4. Lặp đến khi queue rỗng.

```text
head/front                                   tail/back
   |                                            |
   v                                            v
  [3]     [10]     [1]     [6]        [14]
   ^ lấy ra                         ^ thêm con vào cuối

FIFO: nút nào được đưa vào sớm thì được lấy ra sớm.
```

Nếu thay queue bằng **stack LIFO** và liên tục đẩy con, thứ tự trở thành cách duyệt theo chiều sâu với quy tắc riêng. Chính tính FIFO làm cha được xử lý trước con và các nút trong cùng tầng được xử lý theo thứ tự thêm.

### 2.1. Pseudocode cho cây nhị phân

```text
LEVEL_ORDER(root):
    if root == null:
        return empty result

    q = empty FIFO queue
    enqueue(q, root)

    while not empty(q):
        node = dequeue(q)
        visit(node.value)

        if node.left != null:
            enqueue(q, node.left)

        if node.right != null:
            enqueue(q, node.right)
```

Ta **chỉ đưa các nút thực sự tồn tại** vào queue. Không enqueue `NULL` của nhánh vắng nếu mục tiêu chỉ là duyệt các giá trị. Nếu cần xuất cả cấu trúc thiếu con để tuần tự hóa cây, đó là bài toán khác, sẽ xét ở phần sau.

### 2.2. Mô phỏng queue từng bước

Ta ký hiệu queue theo thứ tự **[đầu, ..., cuối]**. Khởi tạo bằng `[8]`.

| Bước | Nút lấy ra | Nút được thêm | Queue sau bước | Kết quả đã thăm |
| --- | --- | --- | --- | --- |
| 1 | 8 | 3, 10 | `[3,10]` | `[8]` |
| 2 | 3 | 1, 6 | `[10,1,6]` | `[8,3]` |
| 3 | 10 | 14 | `[1,6,14]` | `[8,3,10]` |
| 4 | 1 | Không có | `[6,14]` | `[8,3,10,1]` |
| 5 | 6 | 4, 7 | `[14,4,7]` | `[8,3,10,1,6]` |
| 6 | 14 | 13 | `[4,7,13]` | `[8,3,10,1,6,14]` |
| 7 | 4 | Không có | `[7,13]` | `[8,3,10,1,6,14,4]` |
| 8 | 7 | Không có | `[13]` | `[8,3,10,1,6,14,4,7]` |
| 9 | 13 | Không có | `[]` | `[8,3,10,1,6,14,4,7,13]` |

Quan sát sau bước 2: queue đang chứa `10` (còn ở tầng 1) trước `1` và `6` (tầng 2). Thuật toán sẽ lấy `10` trước, đúng quy tắc “xử lý xong tầng cũ rồi đến tầng mới”.

## 3. Bất biến queue và chứng minh tính đúng đắn

Một thuật toán đúng không chỉ trả một ví dụ chính xác. Ta cần giải thích vì sao nó duyệt **đúng tất cả nút**, **không lặp nút** và **đúng thứ tự tầng**.

Giả sử đầu vào là **cây thực sự**: hữu hạn, không có chu trình và **mỗi nút trừ gốc có đúng một cha**. Mỗi cạnh con có hướng từ cha tới con.

### 3.1. Bất biến tại đầu mỗi lượt lặp

Trước khi lấy nút từ queue:

- Queue chứa **chính những nút đã được phát hiện (enqueue) nhưng chưa xử lý (dequeue)**.
- Các nút trong queue được sắp theo **độ sâu không giảm**. Với cây nhị phân, trong một tầng thứ tự tương ứng với thứ tự trái–phải do ta enqueue con trái trước con phải.
- Mỗi nút **được đưa vào queue tối đa một lần**, vì gốc được đưa một lần và mỗi nút khác có đúng một cha.
- Mọi nút đã xử lý sẽ không bao giờ được xử lý lại.

### 3.2. Chứng minh quy nạp ngắn

**Khởi tạo:** nếu gốc tồn tại, queue chỉ có gốc ở tầng 0. Các tính chất đúng.

**Duy trì:** lấy nút `u` ở đầu queue, tại độ sâu `d`. Các nút còn trong queue có độ sâu ít nhất `d`. Ta đưa con của `u`, nếu có, vào cuối queue; mọi con đều ở tầng `d+1`. Do các nút cũ cùng tầng `d` đã ở trước, việc đưa con vào cuối không khiến nút tầng sâu vượt qua nút tầng nông. Enqueue con trái rồi con phải giữ thứ tự trong tầng. Mỗi con chỉ có cha `u` nên không bị thêm từ một nút cha khác.

**Kết thúc:** cây hữu hạn nên sau khi xử lý hết các nút và không còn nút con mới, queue rỗng. Mỗi nút ngoài gốc được phát hiện khi cha nó được xử lý; do đó tất cả nút đều được thăm. Không có nút bị thăm hai lần.

**Kết luận:** thuật toán xử lý các nút theo độ sâu tăng dần, trái sang phải trong mỗi tầng với quy ước con trái trước con phải.

### 3.3. Một bất biến mạnh hơn: queue chỉ giữ tối đa hai tầng kề nhau

Tại một thời điểm trong BFS của cây:

```text
Queue = [những nút chưa xử lý ở tầng d]
        [các nút đã được phát hiện ở tầng d+1]
```

Trong khi xử lý tầng `d`, thuật toán **chưa xử lý nút nào của tầng d+1**, vì các nút tầng `d` còn lại vẫn ở trước chúng. Bởi vậy không thể có nút tầng `d+2` đang đợi trong queue cùng lúc ấy.

Tính chất này là cơ sở để tách kết quả theo tầng bằng cách **chụp số phần tử queue đầu mỗi vòng**.

## 4. Python: BFS bằng `collections.deque`

Trong Python, `collections.deque` hỗ trợ `append` ở cuối và `popleft` ở đầu với chi phí O(1) cho mỗi thao tác theo mô hình chuẩn. Dùng `list.pop(0)` liên tục thường tốn O(k) cho một lần lấy đầu list dài `k` vì các phần tử phía sau phải dịch vị trí.

### 4.1. Hiện thực hoàn chỉnh

```python
from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass
class Node:
    value: int
    left: Node | None = None
    right: Node | None = None


def level_order(root: Node | None) -> list[int]:
    """Trả giá trị theo thứ tự tầng, từ trái sang phải."""
    if root is None:
        return []

    result: list[int] = []
    queue = deque([root])

    while queue:
        node = queue.popleft()
        result.append(node.value)

        if node.left is not None:
            queue.append(node.left)
        if node.right is not None:
            queue.append(node.right)

    return result


def sample_tree() -> Node:
    return Node(
        8,
        left=Node(3, left=Node(1),
                  right=Node(6, left=Node(4), right=Node(7))),
        right=Node(10, right=Node(14, left=Node(13))),
    )


root = sample_tree()

print(level_order(root))
# [8, 3, 10, 1, 6, 14, 4, 7, 13]

print(level_order(None))
# []
```

Điểm mấu chốt:

- Kiểm tra `root is None` **trước** khi tạo queue từ gốc.
- Queue lưu **đối tượng nút**, không chỉ giá trị, để có thể truy cập trường `left` và `right`.
- Kiểm tra con khác `None` trước khi enqueue: tránh xem một nhánh vắng là nút dữ liệu.
- Không gọi `queue.pop()` (lấy cuối), vì đó là hành vi LIFO khi dùng deque không phù hợp với BFS.
- `result` nhận các **giá trị**; nếu cần biến đổi cây hoặc lưu vị trí, có thể trả **nút hoặc cặp (nút, độ sâu)** tùy API.

### 4.2. Cây có giá trị trùng nhau vẫn duyệt đủ nút

```python
root = Node(5, Node(5), Node(5))
print(level_order(root))  # [5, 5, 5]
```

Hai nút khác nhau có thể cùng giá trị `5`. BFS trên **cây** không được bỏ một nút chỉ vì giá trị đã xuất hiện: định danh nút và giá trị payload là hai thứ khác nhau.

Điều tương tự đúng với giá trị `0`, số âm hoặc chuỗi rỗng, nếu kiểu nút cho phép. Không dùng giá trị payload như tín hiệu “không có nút” khi giá trị đó có thể hợp lệ.

### 4.3. Vì sao queue chứa nút, không chỉ chứa số?

Nếu chỉ enqueue `node.value`, lúc dequeue ta không còn đường tới `node.left` và `node.right`. Với thuật toán chỉ có các liên kết từ nút cha xuống con, cần giữ ít nhất đường truy cập tới **nút** hoặc một **handle/ID** giúp tìm lại nút ấy.

Đối với cây lưu trong mảng theo chỉ số, queue có thể lưu **chỉ số** thay vì con trỏ nút. Khi đó phải tuân thủ quy tắc chỉ số còn hợp lệ, và kiểm tra con có tồn tại. Tính đúng đắn không phụ thuộc queue chứa con trỏ hay chỉ số; nó phụ thuộc **FIFO** và khả năng truy xuất con từ mỗi phần tử queue.

## 5. Lấy kết quả theo từng tầng bằng kích thước queue

Nếu muốn kết quả dạng `[[8], [3, 10], [1, 6, 14], [4, 7, 13]]`, không đủ chỉ nối mọi giá trị vào một dãy. Ta cần biết **ranh giới tầng**.

Kỹ thuật phổ biến:

1. Đầu mỗi lượt xử lý một tầng, lưu `count = len(queue)`.
2. Xử lý **chính xác `count` nút** này; đây là toàn bộ những nút ở tầng đang xét.
3. Trong quá trình xử lý, enqueue các con của chúng; các con thuộc **tầng tiếp theo**.
4. Sau khi xử lý xong `count` nút, ghi nhận một danh sách tầng.
5. Tiếp tục đến khi queue rỗng.

### 5.1. Mã Python trả về các tầng

```python
from collections import deque


def levels(root: Node | None) -> list[list[int]]:
    if root is None:
        return []

    result: list[list[int]] = []
    queue = deque([root])

    while queue:
        count = len(queue)     # Chụp độ dài TRƯỚC khi enqueue con.
        current_level: list[int] = []

        for _ in range(count):
            node = queue.popleft()
            current_level.append(node.value)

            if node.left is not None:
                queue.append(node.left)
            if node.right is not None:
                queue.append(node.right)

        result.append(current_level)

    return result


root = sample_tree()
print(levels(root))
# [[8], [3, 10], [1, 6, 14], [4, 7, 13]]
```

Mẫu này dùng lớp `Node` và hàm `sample_tree` ở ví dụ ngay trước.

### 5.2. Vì sao không dùng `for _ in range(len(queue))` sau mỗi lần enqueue?

Trong Python, biểu thức `range(len(queue))` được đánh giá lúc bắt đầu vòng `for`, vì thế nếu viết đúng ngay lúc bắt đầu tầng, nó cũng chụp số lượng; vấn đề là **phải xác định ranh giới tầng ở đúng thời điểm**. Nếu viết một vòng `while queue` để “xử lý hết queue của tầng này” mà trong vòng lại enqueue con, các con có thể bị xử lý **trong cùng tầng**, dẫn đến phân nhóm sai.

Ví dụ sai về ý tưởng:

```python
# SAI về phân tầng: vòng trong còn chạy khi đã enqueue con.
# while queue:
#     current_level = []
#     while queue:
#         node = queue.popleft()
#         current_level.append(node.value)
#         ... queue.append(children) ...
#     result.append(current_level)
```

Vòng trong sẽ duyệt đến khi toàn cây được xử lý (với cây hữu hạn), khiến kết quả chỉ có một danh sách lớn.

### 5.3. Gắn độ sâu vào queue

Một cách khác là enqueue cặp `(node, depth)`:

```python
from collections import deque


def values_with_depth(root: Node | None) -> list[tuple[int, int]]:
    if root is None:
        return []

    queue = deque([(root, 0)])
    output: list[tuple[int, int]] = []

    while queue:
        node, depth = queue.popleft()
        output.append((node.value, depth))

        if node.left is not None:
            queue.append((node.left, depth + 1))
        if node.right is not None:
            queue.append((node.right, depth + 1))

    return output


print(values_with_depth(sample_tree()))
# [(8, 0), (3, 1), (10, 1), (1, 2), (6, 2),
#  (14, 2), (4, 3), (7, 3), (13, 3)]
```

Lưu độ sâu rõ ràng có ích khi muốn lọc nút ở độ sâu `d`, ghi nhật ký theo tầng hoặc tính khoảng cách từ gốc. Đổi lại, mỗi mục queue mang thêm một số nguyên độ sâu; về bậc bộ nhớ vẫn O(w) cho queue.

## 6. Độ phức tạp thời gian và bộ nhớ

Gọi:

- `n` là số nút của cây.
- `h` là chiều cao tính theo **số cạnh trên đường dài nhất từ gốc tới lá** (`h = 0` nếu cây có một nút).
- `w` là **số nút lớn nhất trong một tầng** (maximum level width).

Với cây hữu hạn và hàng đợi có enqueue/dequeue O(1) theo mô hình thông dụng:

### 6.1. Thời gian O(n)

Mỗi nút được:

1. Enqueue đúng một lần.
2. Dequeue đúng một lần.
3. Kiểm tra tối đa hai liên kết `left`/`right` và thăm giá trị một lần.

Vì số thao tác trên mỗi nút là hằng số, tổng thời gian là:

```text
T(n) = O(n), n >= 1
T(0) = O(1) cho thao tác kiểm tra cây rỗng
```

Nếu xử lý giá trị nút tốn `f(node)`, tổng chi phí còn phải cộng `Σ f(node)`. Ví dụ in một chuỗi dài từ payload không nhất thiết có chi phí O(1) theo số ký tự.

### 6.2. Bộ nhớ queue O(w), không phải mặc định O(h)

Trong BFS tuần tự chuẩn, queue chứa những nút chưa xử lý của một tầng và những nút mới phát hiện ở tầng kế tiếp. Nếu tầng hiện tại có `a` nút, tầng tiếp theo có `b` nút, số phần tử chờ trong queue không vượt quá `a+b`, tức không vượt `2w`. Do đó:

```text
Bộ nhớ queue phụ trợ: O(w).
Nếu lưu toàn bộ kết quả n giá trị: thêm O(n) bộ nhớ kết quả.
Nếu chỉ in hoặc xử lý trực tuyến: không cần mảng kết quả O(n).
```

Không phải ở mọi thời điểm queue **chỉ chứa tối đa đúng `w` nút**. Trong một số cây, nó có thể đồng thời giữ phần chưa xử lý của tầng `d` cùng phần đã phát hiện của tầng `d+1`; phát biểu đúng cho phân tích là **O(w)**.

### 6.3. Ba hình dạng cây

| Hình dạng | `w` | `h` | Queue BFS | DFS đệ quy |
| --- | --- | --- | --- | --- |
| **Cây lệch thành chuỗi** `n` nút | 1 | `n-1` | O(1) | O(n) stack lời gọi |
| **Cây nhị phân gần đầy/cân đối** | Có thể Θ(n) ở tầng thấp | Θ(log n) | Có thể O(n) | O(log n) stack |
| **Cây rỗng** | 0 | Quy ước riêng | O(1) | O(1) |

Một cây nhị phân đầy `2^{h+1}-1` nút có tầng cuối `2^h` nút: queue có thể chứa Θ(n) mục. Với cây lệch, mỗi nút có tối đa một con, queue thường chỉ chứa một mục mỗi lúc, dù chiều cao lớn.

**Lựa chọn BFS hay DFS phụ thuộc cả bài toán lẫn hình dạng cây.** BFS không đệ quy và không gặp rủi ro stack lời gọi sâu như DFS đệ quy trên cây lệch, nhưng queue có thể chiếm nhiều RAM trên cây rất rộng.

### 6.4. Bảng so sánh biến thể

| Biến thể | Thời gian | Bộ nhớ phụ trợ ngoài kết quả | Dung lượng kết quả |
| --- | --- | --- | --- |
| BFS gọi `visit` trực tiếp | O(n) | O(w) | O(1) nếu không lưu |
| BFS trả list phẳng | O(n) | O(w) | O(n) |
| BFS trả các list theo tầng | O(n) | O(w) | O(n) và metadata các tầng |
| BFS gắn depth cho từng nút | O(n) | O(w) | O(n) nếu lưu đủ cặp |
| Tìm lá gần gốc bằng BFS | O(n) xấu nhất | O(w) | O(1) nếu chỉ trả lá/độ sâu |

Kết quả theo tầng chứa `n` giá trị và tối đa `h+1` danh sách con ở cây không rỗng; về bậc tổng là O(n) vì `h+1 <= n`. Trong một triển khai thực, mỗi list còn có metadata/allocator, nên sử dụng nhiều tầng rất hẹp có thể có thêm overhead hằng số đáng kể.

## 7. Phân biệt queue chứa nút và queue chứa trạng thái

Trong bài toán chỉ duyệt, mỗi mục queue thường là `Node *` hoặc một tham chiếu nút. Nhưng khi **biến đổi cây**, queue có thể giữ trạng thái phong phú hơn:

| Mục queue | Phù hợp với nhiệm vụ |
| --- | --- |
| `node` | Duyệt, đếm, tính tổng |
| `(node, depth)` | Gắn mức, tìm độ sâu, nhóm tầng |
| `(node, parent)` | Khôi phục đường từ nút về gốc nếu API cần |
| `(node, horizontal_index)` | Duyệt theo cột/đường chiếu với quy tắc cụ thể |
| `node_id` | Cây lưu nút trong bảng hoặc mảng, truy cập qua ID |
| `(node, state)` | Biến đổi có nhiều giai đoạn, đánh dấu công việc |

Dù giữ thêm metadata, FIFO vẫn quyết định thứ tự các **công việc đã enqueue**. Nếu một bài toán yêu cầu thứ tự ưu tiên khác, chẳng hạn nút có trọng số chi phí nhỏ hơn cần được xử lý trước bất chấp độ sâu, **priority queue/heap** có thể phù hợp hơn queue FIFO; khi ấy thuật toán không còn là BFS tầng đơn giản.

## 8. Các bài toán áp dụng ngay

### 8.1. Đếm số nút trong từng tầng

Kết quả `levels(root)` ở Mục 5 cho phép lấy số nút tại mỗi độ sâu:

```python
root = sample_tree()
counts = [len(level) for level in levels(root)]
print(counts)  # [1, 2, 3, 3]
```

Có thể tối ưu bộ nhớ nếu chỉ cần các con số: thay vì lưu `current_level`, đếm `count` mỗi tầng rồi ghi ra một danh sách số lượng. Điều này vẫn cần O(h) dung lượng nếu lưu toàn bộ thống kê tầng, nhưng không cần giữ `n` payload.

### 8.2. Tính chiều cao và độ sâu lớn nhất

Với quy ước chiều cao `h` là số **cạnh** từ gốc tới lá xa nhất:

```python
def height_edges(root: Node | None) -> int:
    """Trả -1 cho cây rỗng, 0 cho cây một nút."""
    if root is None:
        return -1

    queue = deque([root])
    depth = -1

    while queue:
        count = len(queue)
        depth += 1

        for _ in range(count):
            node = queue.popleft()
            if node.left is not None:
                queue.append(node.left)
            if node.right is not None:
                queue.append(node.right)

    return depth


print(height_edges(sample_tree()))  # 3
print(height_edges(Node(5)))       # 0
print(height_edges(None))          # -1
```

Dùng `-1` cho chiều cao cây rỗng là **một quy ước** tiện cho công thức cây nhị phân. Nếu định nghĩa chiều cao bằng **số tầng** thì cây rỗng có 0 tầng, cây một nút có 1 tầng và cây mẫu có 4 tầng. Khi trao đổi kết quả, phải nói rõ cách đếm.

### 8.3. Tìm lá gần gốc nhất

Trong BFS, mọi nút độ sâu nhỏ được dequeue trước các nút sâu hơn. Vì vậy **lá đầu tiên gặp được** có độ sâu nhỏ nhất theo số cạnh từ gốc:

```python
def nearest_leaf(root: Node | None) -> tuple[int, int] | None:
    """(giá trị lá, độ sâu); None nếu cây rỗng."""
    if root is None:
        return None

    queue = deque([(root, 0)])

    while queue:
        node, depth = queue.popleft()

        if node.left is None and node.right is None:
            return node.value, depth

        if node.left is not None:
            queue.append((node.left, depth + 1))
        if node.right is not None:
            queue.append((node.right, depth + 1))

    return None


print(nearest_leaf(sample_tree()))  # (1, 2)
```

Đây là một trong những tình huống BFS có thể **dừng sớm**. Thời gian xấu nhất vẫn O(n), nhưng nếu có lá gần gốc, thuật toán có thể trả kết quả trước khi thăm mọi nút.

**Phạm vi của kết luận:** khoảng cách tính bằng **số cạnh**, mỗi cạnh có chi phí như nhau. Nếu các cạnh mang trọng số khác nhau và muốn tìm tổng trọng số nhỏ nhất, BFS FIFO không đủ; cần thuật toán phù hợp với trọng số.


## 9. Cài đặt C hoàn chỉnh: queue liên kết lưu con trỏ nút cây

Trong C, ta không có sẵn `collections.deque`. Một cách minh họa rõ nguyên lý FIFO là tạo queue bằng danh sách liên kết đơn, có `front` và `back`:

```text
Queue rỗng:
    front = NULL
    back  = NULL
    size  = 0

Sau enqueue(A), enqueue(B):
    front --> [A | next] --> [B | NULL]
                                  ^
                                 back

Dequeue -> A; còn lại front/back đều dẫn tới B.
```

Queue chỉ giữ **con trỏ mượn tới nút cây**; **queue sở hữu những ô liên kết phục vụ chính nó**, chứ không sở hữu và không giải phóng nút cây khi dequeue. Đây là ranh giới ownership quan trọng.

### 9.1. Bất biến của hàng đợi C

Với `Queue` đã khởi tạo:

1. `size == 0` khi và chỉ khi `front == NULL` và `back == NULL`.
2. Nếu `size > 0`: từ `front` có đúng `size` ô queue, liên kết tới `back` và `back->next == NULL`.
3. Mỗi ô queue chứa `const TreeNode *` trỏ tới nút còn sống trong cây đang duyệt.
4. `dequeue` giải phóng **ô queue**, nhưng không `free` nút cây mà ô đó trỏ tới.
5. Nếu `enqueue` không cấp phát được, nó trả thất bại và giữ nguyên queue.

### 9.2. Mã C có thể biên dịch độc lập

```c
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct TreeNode {
    int value;
    const struct TreeNode *left;
    const struct TreeNode *right;
} TreeNode;

typedef struct QueueCell {
    const TreeNode *tree_node;   /* Mượn: không sở hữu TreeNode. */
    struct QueueCell *next;
} QueueCell;

typedef struct Queue {
    QueueCell *front;
    QueueCell *back;
    size_t size;
} Queue;

void queue_init(Queue *q) {
    q->front = NULL;
    q->back = NULL;
    q->size = 0;
}

bool queue_push(Queue *q, const TreeNode *node) {
    if (q == NULL || node == NULL || q->size == (size_t)-1) {
        return false;
    }

    QueueCell *cell = malloc(sizeof *cell);
    if (cell == NULL) {
        return false;
    }

    cell->tree_node = node;
    cell->next = NULL;

    if (q->back != NULL) {
        q->back->next = cell;
    } else {
        q->front = cell; /* Queue đang rỗng. */
    }

    q->back = cell;
    ++q->size;
    return true;
}

/* Chỉ gọi khi q->size > 0; giải phóng QueueCell, không hủy cây. */
const TreeNode *queue_pop(Queue *q) {
    QueueCell *first = q->front;
    const TreeNode *node = first->tree_node;

    q->front = first->next;
    if (q->front == NULL) {
        q->back = NULL;  /* Sau pop, queue đã rỗng. */
    }

    --q->size;
    free(first);
    return node;
}

void queue_clear(Queue *q) {
    if (q == NULL) return;

    while (q->front != NULL) {
        (void)queue_pop(q);
    }
}

/*
 * In một dòng cho mỗi tầng.
 * Thành công: true.
 * Hết bộ nhớ khi enqueue: clear queue, trả false.
 *
 * TreeNode thuộc phía gọi; hàm BFS không giải phóng TreeNode.
 * Nếu thất bại, một phần kết quả có thể đã được in ra stdout.
 */
bool bfs_print_levels(const TreeNode *root) {
    if (root == NULL) {
        puts("(cay rong)");
        return true;
    }

    Queue q;
    queue_init(&q);

    if (!queue_push(&q, root)) {
        return false;
    }

    while (q.size != 0) {
        size_t count = q.size;  /* Chụp số nút của tầng hiện tại. */

        for (size_t i = 0; i < count; ++i) {
            const TreeNode *node = queue_pop(&q);
            printf("%d ", node->value);

            if (node->left != NULL && !queue_push(&q, node->left)) {
                queue_clear(&q);
                return false;
            }

            if (node->right != NULL && !queue_push(&q, node->right)) {
                queue_clear(&q);
                return false;
            }
        }

        puts(""); /* Hết tầng hiện tại. */
    }

    return true;
}

int main(void) {
    /* Các nút cây có thời hạn lưu trữ tự động trong main. */
    TreeNode n1  = {1, NULL, NULL};
    TreeNode n4  = {4, NULL, NULL};
    TreeNode n7  = {7, NULL, NULL};
    TreeNode n13 = {13, NULL, NULL};

    TreeNode n6  = {6, &n4, &n7};
    TreeNode n14 = {14, &n13, NULL};
    TreeNode n3  = {3, &n1, &n6};
    TreeNode n10 = {10, NULL, &n14};
    TreeNode root = {8, &n3, &n10};

    if (!bfs_print_levels(&root)) {
        fputs("Khong du bo nho cho queue\n", stderr);
        return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}
```

Đầu ra thành công:

```text
8
3 10
1 6 14
4 7 13
```

**Tại sao phải có `queue_clear` khi lỗi?** Giả sử đã enqueue thành công con trái nhưng `malloc` cho con phải thất bại. Queue vẫn có một số `QueueCell` chờ xử lý. Hàm phải giải phóng các ô queue còn lại để không rò rỉ vùng quản lý. Nhưng nó **không được giải phóng nút cây**, vì các nút cây trong ví dụ do `main` sở hữu dưới dạng biến cục bộ.

**Ghi chú về lỗi xuất ra:** hàm thực hiện *streaming output*. Nếu `malloc` thất bại ở giữa lượt duyệt, một số giá trị hoặc dòng trước đó đã được in. Nếu API bắt buộc “thành công thì trả toàn bộ kết quả, thất bại thì không có gì được công bố”, cần thay thiết kế thành tạo vùng kết quả tạm, kiểm tra hoàn tất rồi mới công bố; việc này đòi hỏi thêm bộ nhớ và xử lý lỗi.

### 9.3. Độ phức tạp của queue liên kết

Mỗi nút cây được enqueue vào **một** ô `QueueCell` và dequeue một lần; mỗi ô được `malloc` một lần và `free` một lần. Với mô hình thao tác cấp phát O(1) thường dùng trong phân tích:

- Tổng **O(n)** thời gian cho BFS.
- Nhiều nhất **O(w)** ô queue còn sống cùng lúc, vì queue chỉ giữ nút ở hai tầng liền kề.
- Các biến điều khiển `Queue`/`count`/`i` dùng O(1) bộ nhớ.
- Không dùng đệ quy, nên không có stack lời gọi O(h).

Nếu muốn giảm overhead của **mỗi lần malloc/free**, có thể dùng **queue vòng bằng mảng con trỏ**, một buffer tăng dung lượng hoặc một vùng pool. Khi đó phải quy định rỗng/đầy, xử lý reallocation và giữ đúng FIFO. Lựa chọn cách hiện thực queue có thể thay đổi hiệu năng thực tế, nhưng không thay đổi ý tưởng BFS.

### 9.4. C++ dùng `std::queue`

Nếu làm việc bằng C++, thư viện đã cung cấp container adapter `std::queue` để enqueue/dequeue thuận tiện:

```cpp
#include <iostream>
#include <queue>

struct Node {
    int value;
    const Node *left = nullptr;
    const Node *right = nullptr;
};

void bfs(const Node *root) {
    if (root == nullptr) return;

    std::queue<const Node *> q;
    q.push(root);

    while (!q.empty()) {
        const Node *node = q.front();
        q.pop();

        std::cout << node->value << " ";

        if (node->left) q.push(node->left);
        if (node->right) q.push(node->right);
    }
}

int main() {
    Node left{2};
    Node right{3};
    Node root{1, &left, &right};

    bfs(&root); // 1 2 3
}
```

`q.front()` đọc phần tử đầu; `q.pop()` **loại bỏ** nó và không trả lại phần tử. Vì thế phải đọc `front` **trước** khi gọi `pop`. Với queue lưu con trỏ mượn, `pop` chỉ hủy mục queue chứ không hủy nút cây.

## 10. Biến đổi dựa trên tầng

Duyệt theo tầng không chỉ dùng để in giá trị. Nó cung cấp **thứ tự xử lý** để tạo báo cáo hoặc thay đổi những thuộc tính phụ thuộc vị trí/tầng.

### 10.1. Duyệt ziczac (zigzag level-order)

Một yêu cầu phổ biến là tầng 0 từ trái sang phải, tầng 1 từ phải sang trái, tầng 2 từ trái sang phải, v.v.

Với cây mẫu:

```text
Tầng 0: [8]
Tầng 1: [10, 3]
Tầng 2: [1, 6, 14]
Tầng 3: [13, 7, 4]
```

Cách đơn giản: duyệt các tầng bằng BFS, rồi **đảo thứ tự giá trị** ở các tầng lẻ:

```python
def zigzag_levels(root: Node | None) -> list[list[int]]:
    result = levels(root)

    for depth in range(len(result)):
        if depth % 2 == 1:
            result[depth].reverse()

    return result


print(zigzag_levels(sample_tree()))
# [[8], [10, 3], [1, 6, 14], [13, 7, 4]]
```

Đây là biến đổi **kết quả duyệt**, không đảo `left` và `right` của cây gốc. Nếu bài toán yêu cầu **biến đổi cấu trúc cây** thật sự, phải thiết kế thao tác đổi liên kết riêng và xác định tác động đến các bộ duyệt đang chạy.

Thời gian `O(n)` vì mỗi phần tử được duyệt và có thể bị đảo tối đa một lần; dung lượng kết quả O(n).

### 10.2. Tính tổng mỗi tầng

```python
def sums_by_level(root: Node | None) -> list[int]:
    if root is None:
        return []

    queue = deque([root])
    totals: list[int] = []

    while queue:
        count = len(queue)
        subtotal = 0

        for _ in range(count):
            node = queue.popleft()
            subtotal += node.value

            if node.left is not None:
                queue.append(node.left)
            if node.right is not None:
                queue.append(node.right)

        totals.append(subtotal)

    return totals


print(sums_by_level(sample_tree()))
# [8, 13, 21, 24]
```

Kiểm tra: tầng 2 có `1+6+14=21`; tầng 3 có `4+7+13=24`. Nếu kiểu số nguyên hữu hạn như `int` C, phải xét **tràn số** khi cộng nhiều giá trị lớn. Python `int` có độ chính xác tùy ý trong giới hạn bộ nhớ thực tế, không mặc định như số nguyên máy có dấu cố định.

### 10.3. Kết nối các nút ngang tầng

Một biến đổi cây khác là tạo liên kết `next_same_level` giữa các nút liền kề ở cùng độ sâu:

```text
Tầng 0: 8 -> NULL
Tầng 1: 3 -> 10 -> NULL
Tầng 2: 1 -> 6 -> 14 -> NULL
Tầng 3: 4 -> 7 -> 13 -> NULL
```

Khi đã chụp `count = len(queue)` ở đầu mỗi tầng, ta có thể duy trì biến `previous`. Mỗi lần dequeue nút mới, nếu `previous` tồn tại thì đặt `previous.next_same_level = node`; cuối tầng đặt `node_cuoi.next_same_level = NULL`.

Điều kiện triển khai:

- Lớp nút phải có trường `next_same_level` hoặc nơi khác để lưu quan hệ ngang.
- Chỉ sử dụng liên kết `left/right` hiện có để phát hiện con; không dùng liên kết ngang vừa tạo để đi xuống vì dễ lặp sai.
- Phải xử lý tầng có một nút và cây rỗng.
- Cần quyết định có cho phép sửa cây **trong lúc** một bộ duyệt khác đang đọc các trường liên kết hay không.

Đây là ứng dụng BFS để **biến đổi metadata của cây** mà vẫn dùng queue FIFO để xác định nhóm tầng.

## 11. Duyệt giá trị khác với tuần tự hóa đầy đủ hình dạng cây

Nếu chỉ lưu chuỗi giá trị BFS, ta có thể **không tái dựng được duy nhất hình dạng cây**.

Hai cây sau có cùng kết quả duyệt phẳng `[1, 2, 3]`:

```text
Cây A:              Cây B:
     1                    1
    / \                    \
   2   3                    2
                              \
                               3

BFS(A) = [1, 2, 3]
BFS(B) = [1, 2, 3]
```

Vì duyệt phẳng không ghi nhận liên kết con nào **vắng mặt**, mất thông tin hình dạng. Nếu nhiệm vụ là tuần tự hóa và khôi phục cấu trúc, cần thêm **dấu vị trí con rỗng**, một sơ đồ chỉ số hoặc định dạng cấu trúc khác.

### 11.1. Tuần tự hóa level-order có marker con vắng

Một cách đơn giản: khi lấy một nút thật, ghi giá trị của nút và enqueue **hai vị trí con**, kể cả vị trí không có nút (`None`). Khi lấy một vị trí `None`, ghi marker nhưng **không** enqueue con của nó. Cách này kết thúc sau hữu hạn bước, không nở cây rỗng vô hạn.

```python
from collections import deque


def serialize_levels(root: Node | None) -> list[int | None]:
    if root is None:
        return []

    queue = deque([root])
    output: list[int | None] = []

    while queue:
        node = queue.popleft()

        if node is None:
            output.append(None)
            continue

        output.append(node.value)
        queue.append(node.left)
        queue.append(node.right)

    # Bỏ marker rỗng ở CUỐI nếu định dạng quy định
    # những con rỗng cuối dãy được suy ra khi khôi phục.
    while output and output[-1] is None:
        output.pop()

    return output


a = Node(1, Node(2), Node(3))
b = Node(1, right=Node(2, right=Node(3)))

print(serialize_levels(a))  # [1, 2, 3]
print(serialize_levels(b))  # [1, None, 2, None, 3]
```

Ở ví dụ này, `Node.value` là `int` nên `None` chỉ được dùng làm marker “vắng nút”. Nếu **giá trị của nút thật cũng có thể là `None`**, định dạng cần phân biệt bằng thẻ riêng như `("NODE", value)` / `("ABSENT",)`; nếu không, dữ liệu bị mơ hồ.

**Phân biệt rõ:** đoạn mã trên là một *định dạng tuần tự hóa minh họa*, không phải thuật toán duyệt phẳng thường dùng. Nó lưu thêm vị trí con rỗng, nên kết quả không còn là dãy chỉ chứa các nút thật. Khi viết hàm khôi phục, phải dùng **chính quy ước marker và cắt marker cuối** đã chọn.

### 11.2. Số lượng marker và chi phí

Với một cây nhị phân `n >= 1` nút, có `2n` vị trí con. Trong một cây thực sự có `n-1` cạnh con, nên có `2n-(n-1)=n+1` vị trí con vắng. Vì thế nếu xuất toàn bộ marker vắng không cắt cuối, kết quả chứa `n` giá trị nút và `n+1` marker, tức **O(n)** mục.

Queue của quá trình tuần tự hóa có thể chứa các vị trí `None` cùng nút thật; vẫn có số mục O(n) ở mức toàn bộ, và trong một cây rộng, chi phí queue có thể lớn. Không nên áp dụng trực tiếp bảng chi phí **chỉ queue chứa nút thật** cho mọi định dạng có marker mà không phân tích lại.

## 12. Khi nào BFS của cây cần tập `visited`?

Với **cây đúng nghĩa**, không cần tập `visited` vì mỗi nút chỉ có **một** đường từ gốc đi đến nó. Việc thêm một bảng băm visited ở bài toán cây thuần túy thường làm tăng bộ nhớ mà không đem lại lợi ích.

Nhưng hãy xét cấu trúc sau:

```text
     A
    / \
   B   C
    \ /
     D

D có hai cha B và C.
```

Đó là một **đồ thị có hướng dạng DAG**, không phải cây theo định nghĩa mỗi nút khác gốc có đúng một cha. Nếu áp dụng BFS cây không visited:

```text
Output: A, B, C, D, D
```

Đỉnh D sẽ được enqueue hai lần. Nếu đồ thị có **chu trình**, BFS không visited có thể chạy vô hạn.

### 12.1. BFS có visited cho đồ thị

Mẫu tổng quát cho đồ thị:

```text
BFS_GRAPH(start):
    if start does not exist:
        return

    queue = [start]
    visited = {start}

    while queue not empty:
        u = queue.dequeue()
        visit(u)

        for each neighbor v of u:
            if v not in visited:
                visited.add(v)   # Đánh dấu KHI enqueue.
                queue.enqueue(v)
```

Đánh dấu khi **enqueue**, thay vì đợi đến khi dequeue, giúp tránh nhiều cạnh cùng đưa một đỉnh chưa xử lý vào queue nhiều lần. Với đồ thị có `V` đỉnh và `E` cạnh biểu diễn bằng danh sách kề, BFS thường có O(V+E) thời gian và O(V) bộ nhớ cho queue/visited (không tính dữ liệu đồ thị gốc).

Đối với cây thuần túy, phiên bản không visited đạt O(n) thời gian và O(w) bộ nhớ queue, thường tối ưu hơn về metadata. **Đừng tự thay giả định “cây” bằng “đồ thị có thể có chu trình”** khi phân tích một cài đặt.

### 12.2. Định danh nút khác với giá trị nút

Nếu mở rộng thành BFS đồ thị, `visited` nên dựa trên **định danh đỉnh/nút**, không mặc định dựa trên giá trị payload. Hai nút khác nhau có thể cùng `value = 5`; nếu đánh dấu “đã thấy giá trị 5” rồi bỏ nút thứ hai, thuật toán sẽ mất dữ liệu hợp lệ.

Đối với mã Python dùng dataclass mutable, có thể chọn một ID bất biến hoặc chính sách định danh đối tượng phù hợp; cần kiểm tra cách `__eq__` và `__hash__` được định nghĩa thay vì đưa thẳng mọi đối tượng mutable vào `set` rồi giả định hash hợp lệ.

## 13. Cây thay đổi trong lúc duyệt và tính hợp lệ của queue

BFS giữ **tham chiếu hoặc con trỏ tới các nút đang chờ**. Nếu nơi khác xóa những nút ấy hoặc thay đổi liên kết con trong lúc queue còn giữ chúng, kết quả có thể không nhất quán hoặc không an toàn.

### 13.1. Cây động trong C/C++

Giả sử queue đã chứa `TreeNode *p` rồi một hàm khác giải phóng nút `p`. Khi BFS dequeue và đọc `p->value` hoặc `p->left`, đây có thể là **use-after-free**.

Trong chương trình nhiều luồng, đọc liên kết và sửa liên kết không được đồng bộ có thể gây **data race** (trong C/C++). Việc queue FIFO được cài đặt đúng **không tự đồng bộ** vòng đời các nút cây.

Các lựa chọn thiết kế:

- **Không sửa cây trong lúc một lượt BFS đang chạy**, theo hợp đồng API.
- **Đồng bộ** các thao tác duyệt và thay đổi bằng khóa phù hợp.
- **Duyệt snapshot bất biến** hoặc một phiên bản cây bền vững (*persistent tree*) có structural sharing an toàn.
- **Lưu ID/handle có kiểm tra hiệu lực** thay vì giữ con trỏ có thể treo, khi dữ liệu thực sự cần thay đổi động.

### 13.2. Thay con làm lệch ngữ nghĩa ngay cả khi không có con trỏ treo

Trong Python, nếu đang duyệt một cây object và một phần khác sửa `node.left` trước khi BFS kiểm tra trường ấy, thuật toán có thể thấy cây **lai giữa các thời điểm**. Không nhất thiết có lỗi truy cập bộ nhớ, nhưng kết quả có thể không phải duyệt của **một trạng thái cây xác định**.

Do đó, phân biệt ba yêu cầu:

1. **An toàn bộ nhớ:** mọi nút được truy cập còn hợp lệ.
2. **Bất biến cây:** liên kết cha–con và cấu trúc hình thành cây đúng theo hợp đồng.
3. **Tính nhất quán của lượt duyệt:** kết quả có phản ánh cây tại một thời điểm/phiên bản cụ thể không?

Một BFS đúng về FIFO vẫn có thể không đạt hai yêu cầu sau nếu cây bị sửa không kiểm soát.

### 13.3. Khi nào được biến đổi ngay trong BFS?

Một số phép biến đổi có thể thực hiện ngay khi dequeue, như cập nhật **trường phụ chỉ dùng để ghi nhãn tầng** mà không sửa `left/right`. Nhưng ngay cả khi chỉ sửa payload, vẫn phải xem thuật toán/luồng khác có đang đọc cùng payload không.

Nếu muốn **xóa nút, xoay cây, chuyển cây con hoặc giải phóng nút** trong BFS, phải định nghĩa thứ tự và hiệu lực của những nút đã nằm trong queue. Một chiến lược an toàn là thu thập **danh sách ID cần sửa** khi duyệt xong, rồi thực hiện thay đổi trong giai đoạn thứ hai có kiểm soát.

## 14. Những lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng stack LIFO thay vì queue FIFO | Thứ tự đi sâu, không theo tầng | Dùng `popleft`/`dequeue` ở đầu queue |
| Enqueue `NULL` khi chỉ duyệt giá trị | Có thể dereference null hoặc in nút giả | Chỉ enqueue con tồn tại |
| Enqueue con phải trước con trái | Mất quy ước trái→phải trong mỗi tầng | Enqueue trái rồi phải |
| Vòng trong xử lý tới khi queue rỗng để tạo một tầng | Nút tầng sau bị gộp vào tầng hiện tại | Chụp `count = len(queue)` trước mỗi tầng |
| Dùng Python `list.pop(0)` trên queue lớn | Dịch mảng lặp lại, giảm hiệu năng | Dùng `collections.deque.popleft` |
| Dùng `list.pop()` | Lấy cuối, thành LIFO | Dùng `popleft()` |
| Quên kiểm tra `root == NULL` | Truy cập gốc rỗng không hợp lệ | Xử lý cây rỗng ngay đầu hàm |
| Tự dùng visited theo **giá trị payload** | Bỏ nhầm nút có giá trị trùng | Với đồ thị, visited theo định danh nút |
| Không có visited khi dữ liệu thực là đồ thị có chu trình | Có thể lặp vô hạn | Dùng BFS đồ thị có tập visited |
| Cho rằng BFS luôn O(h) bộ nhớ | Đánh giá thiếu queue của cây rất rộng | Phân tích O(w), cộng O(n) nếu lưu kết quả |
| Lưu `TreeNode *` trong queue rồi hủy nút từ nơi khác | Có thể use-after-free | Quản lý vòng đời/snapshot/đồng bộ |
| Dùng kết quả BFS phẳng để khôi phục hình dạng duy nhất | Mất thông tin con vắng | Lưu marker/null hoặc định dạng cấu trúc |

## 15. Kiểm thử có hệ thống

Một bộ kiểm thử cho BFS của cây nhị phân nên có cả **đúng thứ tự**, **đúng nhóm tầng**, **không lặp** và **đúng độ phức tạp kỳ vọng**.

### 15.1. Các trường hợp thiết yếu

1. **Cây rỗng:** trả `[]`, không enqueue gốc rỗng.
2. **Cây một nút:** trả đúng một giá trị, một tầng.
3. **Cây lệch trái:** kết quả theo thứ tự từ gốc xuống lá; queue không vượt quá một nút tại một thời điểm.
4. **Cây lệch phải:** tương tự cây lệch trái.
5. **Cây đầy và cân đối:** mỗi tầng có số nút phù hợp, con trái đứng trước con phải.
6. **Cây không cân đối:** thiếu nhiều nhánh nhưng vẫn phân tầng đúng.
7. **Giá trị trùng nhau:** hai nút khác nhau được thăm riêng, không bỏ theo payload.
8. **Giá trị 0/số âm:** không bị coi nhầm là “không có nút”.
9. **Kiểm tra tổng số phần tử của `levels`:** bằng số nút thật.
10. **Cấp phát queue thất bại trong C:** không rò rỉ `QueueCell` còn chờ; không giải phóng sai `TreeNode`.
11. **Chiều cao:** cây một nút bằng 0 nếu đếm cạnh, rỗng bằng -1 theo quy ước ví dụ.
12. **Tuần tự hóa:** hai cây có cùng BFS giá trị nhưng khác hình dạng được phân biệt bởi marker con vắng.
13. **Dữ liệu thực chất là DAG/graph:** áp dụng phiên bản BFS có visited nếu muốn mỗi đỉnh một lần.

### 15.2. Các tính chất dùng để kiểm thử

Với cây hữu hạn `n` nút:

- Mỗi nút được **dequeue đúng một lần**.
- `len(level_order(root)) == n`.
- `sum(len(level) for level in levels(root)) == n`.
- Nối các danh sách tầng của `levels(root)` thành một dãy phải bằng `level_order(root)`.
- Nếu có cặp `(value, depth)`, các depth xuất hiện **không giảm**.
- `height_edges(root) == len(levels(root)) - 1` đối với cây không rỗng.
- Nếu cây chỉ có con trái hoặc chỉ có con phải trên một đường, thứ tự BFS cũng là thứ tự đi từ gốc xuống đường đó.

Các tính chất này giúp phát hiện sai thứ tự, thăm lặp và lỗi nhóm tầng khi thử nghiệm nhiều hình dạng cây ngẫu nhiên.

## 16. Bài tập thực hành có lời giải

### Bài 1. Tính thứ tự BFS

Cho cây:

```text
       A
      / \
     B   C
    /   / \
   D   E   F
```

**Câu hỏi:** Duyệt theo tầng từ trái sang phải cho dãy nào?

**Lời giải:** `A, B, C, D, E, F`. Tầng 0 là A, tầng 1 là B/C, tầng 2 là D/E/F. Không duyệt hết nhánh B trước khi xử lý C.

### Bài 2. Mô phỏng queue

Với cây bài 1, sau khi dequeue A rồi enqueue hai con, queue chứa gì? Sau khi dequeue B và enqueue con của B, queue chứa gì?

**Lời giải:** Sau A: `[B, C]`. Sau B: `[C, D]`. C vẫn đứng trước D vì C được enqueue từ trước.

### Bài 3. Enqueue con phải trước

Nếu mỗi nút enqueue con phải rồi con trái trong cây bài 1, kết quả thế nào?

**Lời giải:** `A, C, B, F, E, D`. BFS vẫn đi theo độ sâu tăng dần, nhưng thứ tự ngang tầng bị đảo theo quy tắc enqueue con phải trước. Đây là lý do đặc tả “trái sang phải” phải được phản ánh trong mã.

### Bài 4. Cây rỗng

`root = None`. `level_order(root)` và `levels(root)` trả gì?

**Lời giải:** Cả hai trả `[]`. Không trả `[None]` vì không có nút thật nào trong cây.

### Bài 5. Cây một nút

`root = Node(0)`. Kết quả BFS và các tầng ra sao?

**Lời giải:** BFS phẳng là `[0]`; theo tầng là `[[0]]`. `0` là payload hợp lệ của một nút thật, không phải dấu hiệu cây rỗng.

### Bài 6. Ghi nhận ranh giới tầng

Vì sao `count = len(queue)` cần được chụp trước vòng xử lý các nút của một tầng?

**Lời giải:** Vì trong lúc xử lý các nút hiện tại, queue sẽ nhận thêm nút **tầng kế tiếp**. Số lượng `count` ban đầu cho biết chính xác bao nhiêu nút thuộc tầng đang xét và ngăn việc gộp con vào tầng cha.

### Bài 7. Tính độ phức tạp

Cây có `n` nút, mỗi nút được enqueue/dequeue một lần bằng queue O(1). Thời gian và bộ nhớ phụ trợ của BFS là bao nhiêu?

**Lời giải:** O(n) thời gian; O(w) bộ nhớ queue với `w` là độ rộng lớn nhất của tầng. Nếu trả một danh sách lưu `n` giá trị, cần thêm O(n) bộ nhớ kết quả.

### Bài 8. Cây lệch và cây rộng

Một cây lệch thành chuỗi có `n = 1000` nút và một cây gần đầy có khoảng 1000 nút. Queue BFS nào có thể lớn hơn?

**Lời giải:** Cây gần đầy thường có tầng rất rộng, nên queue có thể chứa Θ(n) nút. Cây lệch chỉ có một nút mỗi tầng, queue giữ O(1) nút. Điều này cho thấy độ cao lớn chưa chắc làm queue lớn.

### Bài 9. So sánh BFS và DFS

Cây có chiều cao rất lớn nhưng mỗi nút chỉ có một con. Giữa BFS lặp và DFS đệ quy, phương án nào có thể dùng ít bộ nhớ phụ trợ hơn?

**Lời giải:** BFS lặp thường dùng O(1) queue trên cây một đường; DFS đệ quy dùng O(h)=O(n) stack lời gọi. Tuy nhiên, nếu yêu cầu xử lý hậu tự hoặc kết hợp kết quả cây con, DFS vẫn có thể tự nhiên hơn về thuật toán.

### Bài 10. Lá gần gốc

Trong cây mẫu `8/3/10/...` ở đầu bài, lá nào được BFS gặp trước và nó ở độ sâu nào?

**Lời giải:** Nút `1` ở độ sâu `2`. Đây là lá đầu tiên được dequeue; các lá `4,7,13` ở độ sâu `3`.

### Bài 11. Tổng từng tầng

Với các tầng `[8]`, `[3,10]`, `[1,6,14]`, `[4,7,13]`, tính các tổng.

**Lời giải:** `[8, 13, 21, 24]`.

### Bài 12. Zigzag

Với cây bài 1, kết quả ziczac khi tầng chẵn từ trái sang phải, tầng lẻ từ phải sang trái là gì?

**Lời giải:** `[[A], [C, B], [D, E, F]]`. Ta đảo cách xuất giá trị tầng 1, không thay liên kết con thật của cây.

### Bài 13. Hai cây có cùng BFS

`1` có hai con `2` và `3`; cây khác là đường `1 -> right 2 -> right 3`. Vì sao BFS phẳng của chúng đều là `[1,2,3]`?

**Lời giải:** BFS phẳng chỉ lưu thứ tự giá trị và bỏ thông tin nhánh con vắng mặt. Muốn phân biệt hình dạng, cần marker con thiếu hoặc mã hóa cấu trúc khác.

### Bài 14. Cây hay DAG?

Hai nút B/C cùng có con trỏ đến một nút D. Nếu không có visited, BFS kiểu cây thăm D mấy lần?

**Lời giải:** Có thể **hai lần**, vì D được enqueue khi xử lý B và lại được enqueue khi xử lý C. Đây là DAG có một nút nhiều cha; nếu muốn mỗi đỉnh chỉ thăm một lần, dùng visited theo **định danh nút**.

### Bài 15. Queue lưu con trỏ mượn

BFS C đã enqueue con trỏ tới một nút cây. Một hàm khác `free` nút ấy trước khi BFS dequeue. Có thể dereference con trỏ đó không?

**Lời giải:** **Không.** Con trỏ trở thành dangling; queue không sở hữu và không kéo dài vòng đời nút. Phải giữ cây còn sống, dùng snapshot/đồng bộ hoặc hợp đồng handle phù hợp.

### Bài 16. BFS dùng `list.pop(0)`

Tại sao việc lặp `pop(0)` trên list Python có thể kém hơn `deque.popleft()` khi queue lớn?

**Lời giải:** `list.pop(0)` thường dịch các phần tử phía sau nên mỗi lần lấy đầu có thể O(k) khi list đang dài `k`; lặp lại nhiều lần có thể tạo tổng chi phí lớn, tới O(n²) trong các tình huống queue dài. `deque.popleft()` có chi phí O(1) ở đầu theo mô hình chuẩn.

### Bài 17. Kiểm tra tính chất

Giả sử `levels(root)` trả `[[8],[3,10],[1,6,14],[4,7,13]]`. Chiều cao tính bằng số cạnh và tổng số nút là bao nhiêu?

**Lời giải:** Có 4 tầng nên chiều cao là `4-1=3` cạnh; tổng số nút là `1+2+3+3=9`.

### Bài 18. Thêm visited theo giá trị

Cây có ba nút, cả ba cùng mang `value=5`. Nếu visited là tập `{5}`, hậu quả có thể xảy ra?

**Lời giải:** Hai nút có thể bị bỏ qua dù chúng là các đối tượng khác nhau. Nếu bài toán là cây thực sự, không cần visited; nếu là đồ thị, visited phải dựa trên **ID/danh tính đỉnh** thích hợp, không mặc định lấy payload làm định danh.

## 17. Tổng kết và checklist triển khai

- **BFS duyệt theo tầng**: nút gần gốc trước, trong mỗi tầng theo thứ tự chèn con (thường trái trước phải).
- **FIFO là yếu tố quyết định**: enqueue con vào cuối, dequeue nút ở đầu. Stack LIFO sẽ tạo thứ tự khác.
- **Bất biến chính**: queue giữ các nút đã phát hiện nhưng chưa xử lý, xếp theo độ sâu không giảm; với cây thật, mỗi nút được enqueue/dequeue đúng một lần.
- **Độ phức tạp**: O(n) thời gian, O(w) bộ nhớ queue; nếu trả toàn bộ `n` giá trị thì cộng O(n) dung lượng kết quả.
- **Theo tầng**: chụp `count = queue.size` trước khi xử lý một tầng, chỉ pop đúng `count` nút; mọi con enqueue trong vòng thuộc tầng kế tiếp.
- **Ứng dụng**: liệt kê theo độ sâu, tổng/đếm mỗi tầng, chiều cao, lá gần gốc, zigzag và liên kết ngang giữa các nút cùng tầng.
- **Đúng hình dạng cây**: kết quả BFS phẳng có thể không đủ để tái dựng liên kết; tuần tự hóa cần quy ước marker con vắng hoặc định dạng khác.
- **An toàn bộ nhớ và phạm vi**: queue thường mượn con trỏ nút, không sở hữu cây; không dùng nút đã hủy, không duyệt một cấu trúc đang thay đổi không kiểm soát.
- **Phân biệt cây với đồ thị**: cây không cần visited; DAG/đồ thị nhiều đường hoặc có chu trình cần quy tắc visited theo định danh và thay đổi phân tích bộ nhớ tương ứng.

**Trước khi hoàn tất một hiện thực**, hãy kiểm tra: cây rỗng, cây một nút, cây lệch, cây rộng, thứ tự trái–phải, dữ liệu trùng, độ sâu và đường lỗi queue. Sau đó mới quyết định có cần dùng BFS, DFS, hay một cấu trúc hàng đợi/ưu tiên khác theo đúng thao tác và bất biến của bài toán.

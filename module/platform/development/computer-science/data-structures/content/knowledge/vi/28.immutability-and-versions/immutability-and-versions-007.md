# Bền vững từng phần, toàn phần và hợp nhất các nhánh phiên bản

## 1. Vấn đề: một cấu trúc dữ liệu, nhiều trạng thái có thể truy vấn

Trong mô hình cấu trúc dữ liệu thông thường, ta có thể sửa mảng, danh sách liên kết hoặc cây tại chỗ. Ví dụ, một bản đồ có thứ tự lưu điểm số theo mã sinh viên:

```text
Phiên bản v0:
{10: "A", 20: "B", 30: "C"}
```

Sau khi sửa khóa `20` thành `"B+"`:

```text
Phiên bản v1:
{10: "A", 20: "B+", 30: "C"}
```

Nếu cập nhật tại chỗ, trạng thái `v0` có thể đã mất. Nhưng nhiều ứng dụng cần giữ dữ liệu theo thời điểm: lịch sử chỉnh sửa, snapshot để đọc ổn định, khôi phục phiên bản, thử nghiệm các phương án hoặc phát triển song song hai nhánh.

**Cấu trúc dữ liệu bền vững (*persistent data structure*)** là cấu trúc giữ các phiên bản đã tạo để những phiên bản đó còn có thể được truy vấn sau khi có bản mới. “Bền vững” trong bài này nói về **persistence của các phiên bản trong bộ nhớ**, không tự động có nghĩa là dữ liệu đã được lưu an toàn trên đĩa hay sống qua một lần tắt máy.

Từ nhu cầu giữ lịch sử, xuất hiện ba mức khả năng khác nhau:

1. **Bền vững từng phần (*partially persistent*):** đọc được mọi phiên bản đã giữ, nhưng chỉ được cập nhật **phiên bản mới nhất**.
2. **Bền vững toàn phần (*fully persistent*):** đọc được và có thể tạo phiên bản mới từ **bất kỳ phiên bản nào đã giữ**; lịch sử có thể rẽ nhánh.
3. **Bền vững hợp lưu (*confluently persistent*):** ngoài cập nhật từ một phiên bản, còn cho phép một phép toán **kết hợp nhiều phiên bản đầu vào** để tạo phiên bản mới.

Đề bài “**Bền vững từng phần, toàn phần và hợp nhất các nhánh phiên bản**” không chỉ hỏi ba định nghĩa. Người học cần hiểu **mô hình lịch sử**, **tính bất biến của nút chia sẻ**, **độ phức tạp**, **định nghĩa xung đột khi hợp nhất** và **giới hạn của từng cách biểu diễn**.

## 2. Phân biệt “phiên bản”, “gốc” và “nút dùng chung”

### 2.1. Phiên bản là một snapshot logic

Giả sử có một cây tìm kiếm nhị phân (BST) lưu ánh xạ khóa–giá trị. Một **phiên bản** được xác định bằng một tham chiếu tới **gốc cây** đại diện cho snapshot ấy:

```text
version 0 --> root0
version 1 --> root1
version 2 --> root2
```

Một truy vấn cần xác định rõ **đang đọc phiên bản nào**:

```text
get(version=0, key=20) --> "B"
get(version=1, key=20) --> "B+"
```

Đọc sai gốc có thể cho một kết quả đúng về mặt cấu trúc nhưng sai thời điểm.

### 2.2. Nút bất biến cho phép chia sẻ cấu trúc

Giả sử BST được tổ chức:

```text
v0:             [20:B]
                /    \
            [10:A]  [30:C]
```

Khi đổi giá trị ở gốc từ `B` sang `B+`, có thể tạo một nút gốc mới nhưng **dùng chung hai nút lá**:

```text
                    [20:B]   <-- root(v0)
                     /  \
                    /    \
                 [10:A] [30:C]
                    \    /
                     \  /
                    [20:B+]  <-- root(v1)
```

Sơ đồ trên chỉ minh họa **hai gốc tham chiếu chung các nút lá**; nó không biểu diễn một cây duy nhất có hai gốc. Mỗi phiên bản đọc qua gốc riêng đều thấy một BST đúng. Các nút `[10:A]` và `[30:C]` là **cùng đối tượng vật lý** giữa hai phiên bản.

Điều kiện quan trọng: những nút được chia sẻ **không được sửa tại chỗ**. Nếu cùng trỏ tới một `list` hoặc `dict` khả biến rồi cho mã ngoài sửa nội dung, phiên bản cũ vẫn có thể bị thay đổi dù liên kết cây không đổi.

### 2.3. Root là handle, không phải toàn bộ bản sao

Gán:

```python
snapshot_root = current_root
```

chỉ thêm một tham chiếu, **không phải deep copy**. Điều này đủ để lưu snapshot **nếu** mọi nút có thể truy cập đều bất biến. Nếu nút có thể thay đổi, giữ gốc cũ bằng một biến khác **không bảo vệ** snapshot.

### 2.4. Cấu trúc logic có thể là cây, toàn bộ nút qua nhiều phiên bản là DAG

Xét hai phiên bản cùng dùng một cây con `S`:

```text
root0 ----> parent0 ----> S
root1 ----> parent1 ----> S
```

- **Trong một phiên bản:** các liên kết tới con phải biểu diễn một cây hợp lệ.
- **Trong hợp của nhiều phiên bản:** nút `S` có thể có nhiều cạnh đi vào; toàn bộ đối tượng chia sẻ tạo thành một **đồ thị có hướng không chu trình (DAG)**, nếu các liên kết con được xây đúng.

Không được nhầm **chia sẻ một nút giữa các phiên bản** với lỗi **một nút xuất hiện hai lần trong cùng một cây** hoặc với chu trình con trỏ.

## 3. Phân loại chính xác: ephemeral, partial, full và confluent

| Mô hình | Đọc bản cũ | Sửa từ bản mới nhất | Sửa từ bản cũ bất kỳ | Kết hợp hai bản để sinh một bản |
|---|:---:|:---:|:---:|:---:|
| Ephemeral (khả biến thông thường) | Không được bảo đảm | Có | Không | Không có cơ chế phiên bản |
| **Partially persistent** | Có | Có | Không | Không phải khả năng tiêu chuẩn |
| **Fully persistent** | Có | Có | Có | Không tự động |
| **Confluently persistent** | Có | Có | Có | **Có**, theo phép kết hợp được định nghĩa |

Đây là **phân loại khả năng API và mô hình phiên bản**, không phải bảng xếp hạng hiệu suất. Một cấu trúc có nhiều tính năng hơn không nhất thiết nhanh hơn hay dùng ít bộ nhớ hơn.

### 3.1. Ephemeral: chỉ giữ trạng thái đang sử dụng

```text
v0 --edit--> v1 --edit--> v2

Gốc v0/v1 không được bảo đảm truy vấn sau khi sửa.
```

Một cây mutable có thể rất hiệu quả nếu ứng dụng không cần phiên bản cũ.

### 3.2. Partial persistence: tuyến cập nhật

```text
v0 --update--> v1 --update--> v2 --update--> v3
 |               |               |           |
 read            read            read        read

Cập nhật mới chỉ được phép từ v3.
```

Sau khi `v3` đã là bản mới nhất, ứng dụng có thể **đọc `v0`** nhưng không thể dùng thao tác cập nhật partial chuẩn để tạo nhánh mới trực tiếp từ `v0`.

### 3.3. Full persistence: lịch sử rẽ nhánh

```text
v0 --> v1 --> v2
        |
        +----> v3 --> v4
```

Có thể gọi `update(v1,...)` dù `v2` đã tồn tại, nhận `v3`. Hai nhánh không nhất thiết nhìn thấy các cập nhật của nhau.

Điểm then chốt là quyền **cập nhật từ phiên bản cũ bất kỳ**, không phải chỉ sự tồn tại của nhiều root.

### 3.4. Confluent persistence: nhiều đầu vào, một kết quả

```text
         v0
        /  \
       v1   v2
        \  /
         v3    <-- merge(v1, v2) theo một phép hợp nhất rõ ràng
```

Phiên bản `v3` có thể có **hai cha** trong đồ thị lịch sử. Điều này khác với `v3=update(v1,...)` thông thường vốn chỉ có một phiên bản cha.

**Cảnh báo khái niệm:** một đồ thị có hai cha **chưa đủ** để kết luận nội dung đã được hợp nhất đúng. Ta cần định nghĩa **phép kết hợp dữ liệu** và cách giải quyết xung đột.

### 3.5. Những khả năng này không tự suy ra lẫn nhau

Một persistent AVL dùng path copying có thể là **fully persistent** nếu API cho sửa từ mọi root, nhưng **không tự có hàm merge hai root**.

Ngược lại, một ứng dụng có thể lưu snapshot đầy đủ bằng cách deep copy và thực hiện hợp nhất logic. Nó có thể cung cấp đầy đủ ngữ nghĩa các phiên bản nhưng không hiệu quả về bộ nhớ. **Persistence là hợp đồng hành vi; path copying là một kỹ thuật triển khai.**

## 4. Lịch sử tuyến tính, lịch sử phân nhánh và lịch sử hợp lưu

### 4.1. Lịch sử phiên bản là một đồ thị riêng với cây dữ liệu

Phải phân biệt hai đối tượng:

**Đồ thị lịch sử**:

```text
V0 --> V1 --> V2
       |
       +----> V3
```

- Mỗi đỉnh là một **ID phiên bản**.
- Mỗi cạnh ghi một quan hệ “phiên bản mới được tạo từ phiên bản trước”.
- Có thể lưu thời điểm tạo, người thao tác, mô tả thay đổi, cha của commit.

**Cấu trúc dữ liệu của từng phiên bản**:

```text
V1.root --> TreeRoot_1
V2.root --> TreeRoot_2
V3.root --> TreeRoot_3
```

- Mỗi gốc dẫn tới các nút BST/AVL, vector, trie…
- Các nút dữ liệu có thể được chia sẻ giữa những gốc khác nhau.
- Đồ thị lịch sử không nhất thiết có hình dạng giống đồ thị các đối tượng dữ liệu.

Một cạnh `V1→V2` **không nói rằng** gốc dữ liệu của `V2` là con trỏ con của gốc `V1`. Đây là **hai đồ thị ở hai lớp trừu tượng khác nhau**.

### 4.2. Tại sao một lần merge có thể có hai cha?

Hệ thống cần lưu nguồn gốc của kết quả:

```text
M = merge(L, R, base=B)
M.parents = (L, R)
M.merge_base = B
```

Tham chiếu `base` giúp giải thích **các thay đổi của hai nhánh được so với trạng thái nào**. Với lịch sử phân nhánh phức tạp có nhiều tổ tiên chung, việc chọn base cũng là một quyết định thuật toán cần định nghĩa.

### 4.3. ID phiên bản không nhất thiết là thứ tự tổ tiên

Giả sử:

```text
V0 -- V1 -- V2
       \
        V3
```

Dù `id(V3)>id(V2)`, `V3` **không phải hậu duệ của `V2`**. Tăng ID theo thời điểm tạo không thể thay cho phép kiểm tra quan hệ tổ tiên trong đồ thị phiên bản.

### 4.4. Root có thể trùng nhau giữa hai ID phiên bản

Nếu thao tác không làm đổi dữ liệu, chẳng hạn xóa khóa chưa tồn tại:

```text
V4.root is V3.root
```

Hai ID phiên bản có thể khác nhau về metadata lịch sử nhưng **cùng trỏ tới một gốc dữ liệu**. Đây không phải lỗi.

Tương tự, khi hợp nhất hai nhánh có nội dung giống hệt nhau, kết quả có thể dùng lại một root mà vẫn có **hai cha phiên bản**.

## 5. Bền vững từng phần: sửa bản hiện hành, đọc mọi bản cũ

### 5.1. Hợp đồng partial persistence

Một API đơn giản có thể là:

```text
put(key, value)       -> version_mới
delete(key)           -> version_mới
get(version, key)     -> value_tại_phiên_bản
latest_version        -> ID hiện hành
```

Hàm `put/delete` **không nhận version để sửa tùy ý**, vì thao tác luôn dựa trên **phiên bản hiện hành mới nhất**.

Điều này khác API full persistence:

```text
put(base_version, key, value) -> new_version
```

Chỉ một tham số đầu vào cũng có thể thay đổi **mô hình lịch sử** và **khả năng triển khai**.

### 5.2. Kỹ thuật fat node

Một cách thể hiện partial persistence là **fat node**: thay vì ghi đè một trường, lưu **lịch sử các giá trị của trường** kèm phiên bản bắt đầu hiệu lực.

Ví dụ giá trị của khóa `20`:

```text
revision của key=20:
(version 1, "B")
(version 3, "B+")
(version 7, "A")
```

Truy vấn tại `version=5` lấy bản ghi gần nhất có phiên bản **≤5**, tức `"B+"`.

Vì phiên bản mới của partial persistence luôn tăng theo một chuỗi tuyến tính, lịch sử thay đổi của từng trường được lưu theo **thứ tự tăng phiên bản**, phù hợp với tìm kiếm nhị phân.

**Không cần chép cả giá trị ở mọi phiên bản nếu một khóa không đổi.** Chỉ ghi một bản ghi lịch sử khi giá trị của nó thực sự được cập nhật (hoặc khi API yêu cầu ghi lại một thao tác mới).

### 5.3. Vì sao “fat node” không tự biến mọi cây thành cấu trúc `O(\log n)`?

Nếu cấu trúc là một BST:

- Mỗi liên kết `left/right` cũng có thể phải có lịch sử theo phiên bản.
- Khi truy cập ở phiên bản `v`, phải lấy **giá trị của từng liên kết đúng ở `v`**.
- Thời gian đi đường cây còn phụ thuộc **chiều cao**.
- Nhiều thay đổi vào cùng một trường có thể làm lịch sử trường ấy dài.

Vì vậy, nếu một liên kết có `k` bản ghi, truy cập lịch sử của nó bằng binary search có thể tốn `O(\log k)`. Đi qua `h` liên kết như vậy có thể tốn tới `O(h\log U)` nếu chưa có tối ưu khác.

Phải phân biệt **lịch sử giá trị của một khóa** (ví dụ dễ hiểu sau đây) với **một persistent BST hoàn chỉnh** gồm các liên kết được phiên bản hóa. Kỹ thuật cho từng trường là viên gạch xây dựng, không tự giải quyết mọi bất biến cây.

### 5.4. Kỹ thuật node copying chuyên cho partial persistence

Ngoài fat node, còn có phương pháp **node-copying** với một số ô sửa đổi bổ sung trên mỗi nút.

Ý tưởng:

1. Khi một liên kết hoặc trường thay đổi, nếu nút vẫn còn ô lịch sử trống, ghi thay đổi kèm phiên bản.
2. Khi ô lịch sử đầy, tạo bản sao nút chứa trạng thái hiện hành.
3. Sửa những tham chiếu cha cần thiết để trỏ tới bản sao mới ở phiên bản hiện hành.
4. Các phiên bản cũ vẫn dùng nút hoặc mục sửa đổi cũ.

Trong một số mô hình con trỏ với **bậc vào bị chặn** và số trường trên nút hữu hạn, kỹ thuật node copying chuyên biệt có thể đạt **chi phí bộ nhớ thêm `O(1)` khấu hao cho một thay đổi cơ bản**. Nhưng kết luận ấy phụ thuộc các giả thiết cấu trúc và thuật toán quản lý ô lịch sử; **không được áp dụng máy móc** cho đồ thị có bậc vào không giới hạn hoặc cho hợp nhất nhiều nhánh.

Path copying vẫn có thể được dùng để triển khai partial persistence nếu API chỉ cho cập nhật bản mới nhất. Tuy vậy nó có thể cấp phát `O(h)` nút cho mỗi cập nhật một khóa, không nhất thiết đạt cùng chặn khấu hao như node-copying chuyên biệt.

## 6. Python minh họa partial persistence bằng lịch sử thay đổi

Đoạn mã sau lưu một **map từ khóa nguyên sang chuỗi**, không phải BST. Nó minh họa **ngữ nghĩa** partial persistence và cách tra một trường theo mốc phiên bản.

### 6.1. Quy ước

- Phiên bản `0` là map rỗng.
- Mỗi lần `put/delete` tạo **một ID mới**, được đánh số tăng liên tiếp.
- `get(v,key)` đọc giá trị gần nhất có phiên bản thay đổi không vượt `v`.
- Giá trị chỉ nhận chuỗi; `None` đại diện cho **khóa không tồn tại** khi trả về.
- Một giá trị bị xóa được lưu bằng sentinel riêng, tránh nhầm với chuỗi rỗng.
- Không có API “chỉnh sửa phiên bản `v` bất kỳ”.

### 6.2. Mã Python

```python
from bisect import bisect_right

_MISSING = object()


class PartialHistoryMap:
    def __init__(self):
        self._latest = 0
        # key -> danh sách số phiên bản đã đổi key
        self._when = {}
        # key -> danh sách giá trị tương ứng, có thể là _MISSING
        self._what = {}

    @property
    def latest_version(self):
        return self._latest

    @staticmethod
    def _check_key(key):
        if type(key) is not int:
            raise TypeError("key phải là int")

    def _record(self, key, value):
        self._latest += 1

        self._when.setdefault(key, []).append(self._latest)
        self._what.setdefault(key, []).append(value)

        return self._latest

    def put(self, key, value):
        self._check_key(key)
        if not isinstance(value, str):
            raise TypeError("value phải là str")
        return self._record(key, value)

    def delete(self, key):
        self._check_key(key)
        return self._record(key, _MISSING)

    def get(self, version, key):
        self._check_key(key)
        if (
            type(version) is not int
            or not 0 <= version <= self._latest
        ):
            raise IndexError("version ngoài phạm vi")

        revisions = self._when.get(key)
        if revisions is None:
            return None

        # Không tạo một list mới ở mỗi lần tra cứu.
        idx = bisect_right(revisions, version) - 1

        if idx < 0:
            return None

        value = self._what[key][idx]
        return None if value is _MISSING else value
```

### 6.3. Ví dụ: quá khứ luôn đọc được

```python
hist = PartialHistoryMap()

v1 = hist.put(20, "B")
v2 = hist.put(10, "A")
v3 = hist.put(20, "B+")
v4 = hist.delete(10)
v5 = hist.put(30, "")

assert (v1, v2, v3, v4, v5) == (1, 2, 3, 4, 5)

assert hist.get(0, 20) is None
assert hist.get(1, 20) == "B"
assert hist.get(2, 20) == "B"
assert hist.get(3, 20) == "B+"
assert hist.get(4, 20) == "B+"

assert hist.get(3, 10) == "A"
assert hist.get(4, 10) is None
assert hist.get(5, 30) == ""   # Chuỗi rỗng là dữ liệu hợp lệ.
```

### 6.4. Chi phí của minh họa này

Gọi `k_x` là số lần thay đổi của **khóa `x`**.

- `put/delete`: thêm một bản ghi vào cuối hai danh sách; **`O(1)` khấu hao** theo cơ chế nới mảng của Python.
- `get(version,x)`: tìm kiếm nhị phân trên `k_x` mốc; **`O(\log(k_x+1))`** thời gian nếu có lịch sử.
- Bộ nhớ: **`O(U+K)`** cho `U` bản ghi thay đổi và `K` khóa từng xuất hiện, chưa tính payload.
- Đọc một phiên bản **không** đòi hỏi quét mọi thay đổi toàn cục.

Cấu trúc này là **lịch sử theo trường**. Nó không hỗ trợ danh sách khóa trong một phiên bản với cùng độ phức tạp, không duy trì cân bằng BST, cũng không hỗ trợ cập nhật rẽ nhánh. Không nên dùng nó để kết luận **mọi partially persistent tree** có cùng chi phí.

## 7. Bền vững toàn phần: tạo nhánh từ bất kỳ phiên bản

### 7.1. Một API có phiên bản đầu vào

```text
put(base_version, key, value) -> new_version
delete(base_version, key)     -> new_version
get(version, key)             -> value
```

Khác partial persistence, bất kỳ `base_version` hợp lệ nào cũng được phép làm đầu vào cho cập nhật.

### 7.2. Ví dụ phân nhánh

```text
v0 = {}
v1 = put(v0, 10, "A")
v2 = put(v1, 20, "B")
v3 = put(v1, 30, "C")

Lịch sử:
v0 -> v1 -> v2
       |
       +----> v3

v2 = {10:"A",20:"B"}
v3 = {10:"A",30:"C"}
```

`v2` và `v3` không là “bản mới” của nhau; chúng là **hai nhánh anh em** cùng có tổ tiên `v1`.

### 7.3. Path copying trong cây bất biến

Một BST bất biến có thể triển khai:

```text
NEW_ROOT = UPDATE(OLD_ROOT, key, value)
```

Khi cập nhật:

- Đi xuống đường tìm khóa.
- Tạo nút mới ở điểm thay đổi.
- Dựng lại các tổ tiên từ dưới lên.
- Dùng lại các cây con không đổi.
- Trả gốc mới; không sửa gốc cũ.

Với chiều cao cây `h`:

\[
T_{\text{point-update}}=O(h+1),\qquad
S_{\text{new nodes}}=O(h+1).
\]

Nếu cây là **AVL cân bằng**, `h=O(\log(n+1))`. Nếu chỉ là BST không tự cân bằng, `h` có thể bằng `\Theta(n)`. Persistence **không tự làm cây thấp đi**.

### 7.4. Xoay cây cũng phải bất biến

Với xoay trái:

```text
Trước:                 Sau:
     x                      y'
    / \                    /  \
   A   y                  x'   C
      / \                / \
     B   C              A   B
```

Không được gán `x.right=B` hoặc `y.left=x` vào những nút cũ. Phải tạo `x'` và `y'`, rồi chia sẻ `A,B,C` khi chúng bất biến.

Nếu metadata lưu `height/size/sum`, các nút mới phải được tính lại từ đúng cây con.

### 7.5. Mỗi bản chỉ là một tham chiếu root

Bộ quản lý phiên bản có thể giữ:

```text
versions[0] = root0
versions[1] = root1
versions[2] = root2
versions[3] = root3
```

Việc lưu một ID/root thêm chi phí nhỏ, còn bộ nhớ chính do **những nút thực sự được tạo mới**. Các nhánh cây bất biến có thể được dùng lại xuyên nhiều phiên bản.

## 8. Từ full persistence tới hợp nhất hai nhánh

### 8.1. Full persistence không tự biết “kết hợp” là gì

Giả sử:

```text
base  = {10:"A", 20:"B"}
left  = {10:"A+",20:"B",30:"C"}
right = {10:"A", 20:"B+",40:"D"}
```

Ta muốn một phiên bản mới chứa **cả hai thay đổi độc lập**:

```text
merged = {
    10:"A+",
    20:"B+",
    30:"C",
    40:"D",
}
```

Cấu trúc fully persistent cho ta quyền đọc `left/right/base` và tạo bản mới từ một trong chúng. Nhưng nó **không tự biết** phải áp dụng cả hai tập thay đổi hay xử lý khi cùng một khóa được sửa khác nhau.

Để thêm khả năng **confluent**, cần định nghĩa một phép kết hợp rõ ràng, chẳng hạn:

```text
merge(base, left, right) -> merged
```

### 8.2. Merge phải có ngữ nghĩa theo kiểu dữ liệu

Cùng tên `merge` có thể có ý nghĩa rất khác:

- Với **tập hợp (set)**: hợp hai tập, giao hai tập hoặc thao tác khác.
- Với **map khóa–giá trị**: hợp nhất các cập nhật từng khóa, cần giải quyết trùng khóa.
- Với **chuỗi văn bản**: so sánh các đoạn chỉnh sửa theo tổ tiên chung.
- Với **giỏ hàng hoặc bộ đếm**: có thể cần định nghĩa cộng dồn, chọn trạng thái hoặc ngữ nghĩa nghiệp vụ.
- Với **cây dãy**: `merge(left,right)` có thể mang nghĩa **nối dãy**; đó không phải 3-way merge của hai nhánh lịch sử.

Vì vậy, “có một hàm `merge`” chưa đủ. Cần hỏi:

1. Kết quả phải **biểu diễn thông tin gì**?
2. Những thay đổi độc lập được nhận diện ra sao?
3. Khi hai nhánh cùng sửa một phần dữ liệu thì **ưu tiên, xung đột hay kết hợp**?
4. Phép merge có **giao hoán, kết hợp, lũy đẳng** không?
5. Có cần tìm tổ tiên chung, và tổ tiên nào được chọn?
6. Sau merge, phiên bản cũ có còn nguyên không?

### 8.3. Gộp dữ liệu khác nối hai cây con

Một cài đặt ngây thơ:

```text
merged_root.left = left_root
merged_root.right = right_root
```

**không phải cách hợp nhất hai BST theo khóa** nếu chưa chứng minh tất cả khóa ở nhánh trái nhỏ hơn khóa gốc và ở nhánh phải lớn hơn. Hai phiên bản thường chứa **cùng nhiều khóa**, khiến việc gắn trực tiếp có thể tạo khóa trùng và vi phạm bất biến BST.

Một thuật toán confluent đúng phải thực hiện phép kết hợp **theo ngữ nghĩa dữ liệu**, sau đó tạo một cây hợp lệ (có thể dùng chia sẻ cấu trúc nếu thuật toán tối ưu đủ tốt).

## 9. Hợp nhất ba chiều (three-way merge) dựa trên tổ tiên chung

### 9.1. Vì sao cần base?

Giả sử hai nhánh có:

```text
left [20]  = "B+"
right[20]  = "B"
```

Không biết base, ta không thể phân biệt:

- `left` thay `B→B+` còn `right` giữ nguyên; hay
- `right` thay `B+→B` còn `left` giữ nguyên.

Hai tình huống cần quyết định khác nhau. **Base** cho ta biết nhánh nào đã đổi so với trạng thái chung.

### 9.2. Xem từng khóa ở ba trạng thái

Gọi:

- `b`: giá trị khóa trong base.
- `l`: giá trị trong left.
- `r`: giá trị trong right.

Phải có thêm ký hiệu **ABSENT** cho “khóa không tồn tại”. Không được dùng một giá trị hợp lệ như chuỗi rỗng hoặc số `0` để thay thế trạng thái vắng mặt.

### 9.3. Quy tắc merge chuẩn cho map

Với phép so sánh giá trị theo ngữ nghĩa (trong bài, giá trị là chuỗi bất biến):

| Điều kiện | Kết quả |
|---|---|
| `l == r` | Lấy `l`: hai nhánh nhất trí, dù đã thay đổi |
| `l == b`, `r != b` | Lấy `r`: chỉ phải thay đổi |
| `r == b`, `l != b` | Lấy `l`: chỉ trái thay đổi |
| Còn lại | **Xung đột**: hai nhánh thay đổi khác nhau |

Mã giả:

```text
MERGE_VALUE(b, l, r):
    if l == r: return l
    if l == b: return r
    if r == b: return l
    raise CONFLICT
```

Quy tắc **không** quyết định tự động bên trái hoặc bên phải thắng ở trường hợp xung đột.

### 9.4. Ví dụ không xung đột

```text
base  = {10:"A",  20:"B"}
left  = {10:"A+", 20:"B",  30:"C"}
right = {10:"A",  20:"B+", 40:"D"}
```

So sánh:

- Khóa 10: chỉ trái thay → `"A+"`.
- Khóa 20: chỉ phải thay → `"B+"`.
- Khóa 30: chỉ trái thêm → `"C"`.
- Khóa 40: chỉ phải thêm → `"D"`.

Kết quả:

```text
{10:"A+",20:"B+",30:"C",40:"D"}
```

### 9.5. Ví dụ xung đột cùng một khóa

```text
base  = {20:"B"}
left  = {20:"B+"}
right = {20:"B-"}
```

Với khóa 20:

- `l!=r`.
- `l!=b`.
- `r!=b`.

Đây là **xung đột sửa–sửa** (*edit/edit conflict*). Một thuật toán nghiêm ngặt phải trả lỗi để người gọi chọn giá trị, hoặc dùng **chính sách hòa giải được công bố**.

### 9.6. Xóa và sửa cùng một khóa

```text
base  = {20:"B"}
left  = {}              # left xóa key 20.
right = {20:"B+"}       # right sửa key 20.
```

Trạng thái:

```text
b = "B"
l = ABSENT
r = "B+"
```

Đây là **xung đột xóa–sửa** (*delete/edit conflict*). Không được âm thầm chọn xóa hoặc sửa nếu API không quy định.

### 9.7. Hai nhánh cùng xóa hoặc cùng thêm

**Cùng xóa:**

```text
base  = {20:"B"}
left  = {}
right = {}
```

Vì `l==r==ABSENT`, kết quả là **không có khóa 20**, không xung đột.

**Cùng thêm cùng giá trị:**

```text
base  = {}
left  = {20:"B"}
right = {20:"B"}
```

Vì `l==r`, giữ `20:"B"`, không xung đột.

**Cùng thêm khác giá trị:**

```text
base  = {}
left  = {20:"B"}
right = {20:"C"}
```

Cả hai nhánh thay đổi khác nhau từ ABSENT → **xung đột thêm–thêm**.

### 9.8. “Giá trị trở về bằng base” được xem là không đổi trạng thái

Giả sử một nhánh sửa `B→C→B` rồi cuối cùng có giá trị `B` giống base. Three-way merge **chỉ dựa trên snapshot cuối** xem nhánh ấy **không đổi về giá trị**.

Nếu ứng dụng phải bảo toàn mọi sự kiện đã xảy ra, ngay cả khi trạng thái quay về như cũ, cần **nhật ký sự kiện** hoặc metadata thay đổi, không chỉ so sánh snapshot.

### 9.9. Tính chất của merge ba chiều

Quy tắc theo từng khóa ở trên là **đối xứng trái/phải** khi không có xung đột: đổi `left` và `right` vẫn cho cùng giá trị.

Nhưng một **chính sách ưu tiên trái** hoặc **ưu tiên phải** khi xung đột không còn đối xứng.

Không nên tùy tiện giả định phép merge tổng quát có **tính kết hợp**:

```text
merge(merge(A,B),C) == merge(A,merge(B,C))
```

vì mỗi lần merge có thể cần một base khác nhau, xung đột khác nhau và đồ thị lịch sử khác nhau. Tính chất đại số phải được định nghĩa và chứng minh cho **phép toán cụ thể**.

## 10. Chọn tổ tiên chung và ý nghĩa của đồ thị merge

### 10.1. Tổ tiên chung

Với hai phiên bản `L,R`, **tổ tiên chung** là phiên bản mà từ đó cả hai đều có thể đi xuống theo các cạnh tạo phiên bản.

Một lịch sử đơn giản:

```text
       B
      / \
     L   R
```

Có thể chọn `B` làm base để merge.

Nhưng trong một DAG có nhiều merge trước đó, có thể có **nhiều tổ tiên chung** và thậm chí nhiều “tổ tiên chung gần nhất” không so sánh được theo quan hệ tổ tiên. Việc chọn merge base **không luôn chỉ là lấy ID lớn nhất**.

### 10.2. Hợp đồng an toàn của ví dụ Python ở bài này

Trong phần cài đặt, người gọi sẽ cung cấp:

```text
merge(base_version, left_version, right_version)
```

Bộ quản lý kiểm tra:

- Ba ID đều hợp lệ.
- `base_version` là **tổ tiên của left**.
- `base_version` là **tổ tiên của right**.

Đó là điều kiện **cần** để dùng base làm tổ tiên chung. Nhưng nó chưa bảo đảm base được chọn là tổ tiên chung **gần nhất/duy nhất**. Người dùng chịu trách nhiệm chọn mốc phù hợp với ngữ nghĩa dự án; hệ thống sản xuất nên có thuật toán xác định merge base trên DAG.

### 10.3. Fast-forward không phải merge xung đột

Nếu `L` là tổ tiên của `R` và không có nhánh độc lập cần kết hợp, hệ thống quản lý lịch sử có thể “di chuyển con trỏ hiện hành” tới `R`, gọi là **fast-forward**.

Điều này không nhất thiết cần tạo một phiên bản hai cha hay dựng một cây dữ liệu mới.

### 10.4. Merge commit có hai cha

Khi thực sự tạo bản hợp nhất:

```text
      base
      /  \
    left right
      \  /
       M
```

Metadata lịch sử có thể lưu:

```text
M.parents = (left, right)
M.merge_base = base
```

Các phiên bản cũ và cây con bất biến phải tiếp tục được truy vấn. Phép merge **không được ghi đè** nội dung một nhánh để tiện ghép.

### 10.5. Cần phân biệt merge commit với thao tác `merge` của treap

Một implicit treap có hàm:

```text
merge(A,B) = nối dãy A rồi B
```

Nó thường đòi hỏi hoặc suy ra thứ tự vị trí phù hợp và trả về một **cây biểu diễn phép nối**. Đây không phải **merge ba chiều hai nhánh lịch sử**.

Tương tự, hợp hai tập hợp (*set union*) là một phép toán dữ liệu khác với hợp nhất trạng thái hai nhánh bằng base. Tên “merge” phải luôn đi kèm hợp đồng dữ liệu và lịch sử.

## 11. Python: cây AVL bất biến cho full persistence

Trong phần này, ta viết một ví dụ **tự chứa** để quản lý các phiên bản map có thứ tự. Mục tiêu:

- Bản ghi có **khóa `int` phân biệt**, **giá trị `str` bất biến**.
- Mọi nút cây là `@dataclass(frozen=True)`.
- Mọi phép chèn, sửa, xóa trả **gốc AVL mới**.
- Các phiên bản cũ giữ root và nội dung đúng.
- Một lần cập nhật đơn khóa tạo `O(\log n)` nút mới trên AVL cân bằng, thay vì sao chép tất cả `n` nút.
- Ta có thể thêm một phép merge ba chiều ở tầng **quản lý phiên bản**.

**Phân biệt hai chi phí:** chèn/sửa/xóa một khóa theo đường AVL có thể logarit. Một phép **merge toàn bộ trạng thái** theo thuật toán đơn giản ở mục 13 sẽ duyệt các map và dựng cây mới, vì vậy **không có cùng chi phí `O(\log n)`**.

### 11.1. Nút và các trường tóm tắt

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, eq=False)
class AVLNode:
    key: int
    value: str
    left: AVLNode | None
    right: AVLNode | None
    height: int
    size: int


def _height(node: AVLNode | None) -> int:
    return 0 if node is None else node.height


def _size(node: AVLNode | None) -> int:
    return 0 if node is None else node.size


def _make(
    key: int,
    value: str,
    left: AVLNode | None = None,
    right: AVLNode | None = None,
) -> AVLNode:
    """Tạo nút mới; tuyệt đối không sửa con truyền vào."""
    return AVLNode(
        key=key,
        value=value,
        left=left,
        right=right,
        height=1 + max(_height(left), _height(right)),
        size=1 + _size(left) + _size(right),
    )


def _balance(node: AVLNode) -> int:
    return _height(node.left) - _height(node.right)
```

Bất biến:

\[
height(\varnothing)=0,\quad height(u)=1+\max(height(L),height(R)).
\]

\[
size(\varnothing)=0,\quad size(u)=1+size(L)+size(R).
\]

Ở đây chiều cao **nút lá bằng `1`**, cây rỗng bằng `0`. `eq=False` giữ so sánh theo identity mặc định thay vì so sánh cấu trúc đệ quy; trong ví dụ ta dùng `is` để kiểm tra chia sẻ nút.

**Tại sao giá trị phải là `str`?** Vì `str` trong Python là bất biến. Nếu dùng `list` khả biến làm payload mà không sao chép/đóng băng, một thay đổi bên ngoài có thể làm snapshot cũ “thay đổi nội dung” dù nút frozen.

### 11.2. Hai phép xoay bất biến

```python
def _rotate_left(x: AVLNode) -> AVLNode:
    y = x.right
    if y is None:
        raise ValueError("Thiếu con phải để xoay trái")

    new_x = _make(x.key, x.value, x.left, y.left)
    return _make(y.key, y.value, new_x, y.right)


def _rotate_right(y: AVLNode) -> AVLNode:
    x = y.left
    if x is None:
        raise ValueError("Thiếu con trái để xoay phải")

    new_y = _make(y.key, y.value, x.right, y.right)
    return _make(x.key, x.value, x.left, new_y)


def _rebalance(node: AVLNode) -> AVLNode:
    bf = _balance(node)

    if bf > 1:
        left = node.left
        assert left is not None

        if _balance(left) < 0:
            new_left = _rotate_left(left)
            node = _make(
                node.key, node.value, new_left, node.right
            )

        return _rotate_right(node)

    if bf < -1:
        right = node.right
        assert right is not None

        if _balance(right) > 0:
            new_right = _rotate_right(right)
            node = _make(
                node.key, node.value, node.left, new_right
            )

        return _rotate_left(node)

    return node
```

Với mỗi xoay, có thể thấy **không có lệnh `x.left=...` hoặc `y.right=...`**. Nút cũ không đổi.

Phép xoay chỉ tạo một số **hằng nút mới**. Những cây con không bị thay đổi hình dạng được giữ bằng **tham chiếu gốc cũ**. Nếu cây con đang dùng trong phiên bản khác thì vẫn an toàn, vì nó bất biến.

### 11.3. Chèn hoặc thay thế một khóa

```python
def _put(
    root: AVLNode | None,
    key: int,
    value: str,
) -> AVLNode:
    if root is None:
        return _make(key, value)

    if key == root.key:
        # No-op: giữ nguyên nút (không cấp phát mới).
        if value == root.value:
            return root
        return _make(key, value, root.left, root.right)

    if key < root.key:
        new_left = _put(root.left, key, value)
        if new_left is root.left:
            return root

        rebuilt = _make(
            root.key, root.value, new_left, root.right
        )
        return _rebalance(rebuilt)

    new_right = _put(root.right, key, value)
    if new_right is root.right:
        return root

    rebuilt = _make(
        root.key, root.value, root.left, new_right
    )
    return _rebalance(rebuilt)
```

Nếu chỉ **thay giá trị** khóa cũ, thứ tự BST và hình dạng cây không đổi. Những nút trên đường đi được tái tạo vì liên kết về nhánh mới phải được biểu diễn trong các nút bất biến.

Nếu `value` không khác giá trị hiện có, `_put` trả lại **chính root cũ**. Một ID phiên bản mới vẫn có thể được thêm vào lịch sử, nhưng **không có nút cây mới**.

### 11.4. Xóa khóa bất biến, kể cả nút có hai con

```python
def _pop_min(
    root: AVLNode,
) -> tuple[int, str, AVLNode | None]:
    """Lấy bản ghi nhỏ nhất và cây còn lại, không sửa root."""
    if root.left is None:
        # Nút nhỏ nhất có thể có con phải.
        return root.key, root.value, root.right

    key, value, new_left = _pop_min(root.left)
    rebuilt = _make(
        root.key, root.value, new_left, root.right
    )
    return key, value, _rebalance(rebuilt)


def _delete(
    root: AVLNode | None,
    key: int,
) -> AVLNode | None:
    if root is None:
        return None

    if key < root.key:
        new_left = _delete(root.left, key)
        if new_left is root.left:
            return root

        rebuilt = _make(
            root.key, root.value, new_left, root.right
        )
        return _rebalance(rebuilt)

    if key > root.key:
        new_right = _delete(root.right, key)
        if new_right is root.right:
            return root

        rebuilt = _make(
            root.key, root.value, root.left, new_right
        )
        return _rebalance(rebuilt)

    # Đã tìm thấy khóa.
    if root.left is None:
        return root.right

    if root.right is None:
        return root.left

    # Hai con: lấy kế nhiệm inorder của cây phải.
    successor_key, successor_value, new_right = (
        _pop_min(root.right)
    )

    rebuilt = _make(
        successor_key,
        successor_value,
        root.left,
        new_right,
    )
    return _rebalance(rebuilt)
```

Khi nút có hai con, ta đưa **cả khóa và giá trị của kế nhiệm** vào nút mới. Không được chỉ chép khóa rồi để giá trị cũ, vì như vậy sẽ làm sai map khóa–giá trị.

Đặc biệt, `_pop_min` **trả lại con phải của nút nhỏ nhất** nếu có. Bỏ qua con ấy sẽ làm mất dữ liệu.

### 11.5. Đọc và duyệt mà không sửa nút

```python
def _get(root: AVLNode | None, key: int) -> str | None:
    node = root

    while node is not None:
        if key < node.key:
            node = node.left
        elif key > node.key:
            node = node.right
        else:
            return node.value

    return None


def _items(root: AVLNode | None) -> list[tuple[int, str]]:
    result = []
    stack = []
    node = root

    while node is not None or stack:
        while node is not None:
            stack.append(node)
            node = node.left

        node = stack.pop()
        result.append((node.key, node.value))
        node = node.right

    return result
```

Hàm `_get` tốn `O(\log(n+1))` trên AVL. Hàm `_items` duyệt toàn bộ `n` khóa và trả về danh sách mới, nên tốn **`O(n)` thời gian và bộ nhớ đầu ra**.

### 11.6. Dựng cây cân bằng từ các khóa đã sắp

Thuật toán merge ở tầng lịch sử sẽ có kết quả dưới dạng danh sách các cặp khóa–giá trị sắp tăng. Thay vì chèn từng cặp vào một cây rỗng, có thể dựng cây cân bằng bằng cách chọn phần tử giữa làm gốc:

```python
def _build_sorted(
    ordered: list[tuple[int, str]],
) -> AVLNode | None:
    """ordered có khóa int tăng nghiêm ngặt."""
    def build(lo, hi):
        if lo >= hi:
            return None

        mid = (lo + hi) // 2
        key, value = ordered[mid]

        left = build(lo, mid)
        right = build(mid + 1, hi)
        return _make(key, value, left, right)

    return build(0, len(ordered))
```

Với `m` bản ghi tăng theo khóa:

- Tạo đúng `m` nút cho cây kết quả.
- Thời gian **`O(m)`** sau khi dữ liệu đã sắp.
- Chiều cao **`O(\log(m+1))`** và thỏa AVL.

Đây là **chiến lược dễ chứng minh đúng** cho một phép merge toàn phần. Nó **không chia sẻ nút của hai cây đầu vào trong kết quả merge**, dù những phiên bản đầu vào vẫn tự giữ các cây của chúng. Cấu trúc có tính persistent theo hành vi nhưng **merge này không tối ưu về chia sẻ cấu trúc**.

## 12. Phiên bản đầy đủ và metadata của lịch sử DAG

### 12.1. Mỗi phiên bản có root và danh sách cha

Dùng một bản ghi metadata bất biến:

```python
@dataclass(frozen=True, slots=True)
class VersionRecord:
    root: AVLNode | None
    parents: tuple[int, ...]
    operation: str
    merge_base: int | None = None
```

Quy tắc:

- Phiên bản `0` có `parents=()` và root rỗng.
- Một thao tác cập nhật từ `v` có `parents=(v,)`.
- Một thao tác hợp nhất `L,R` có `parents=(L,R)` và lưu `merge_base`.
- `operation` phục vụ mô tả lịch sử, không thay thế dữ liệu bên trong root.

**Đồ thị phiên bản** chỉ gồm các quan hệ ID cha, còn **cây AVL** chỉ gồm liên kết nút trái/phải. Phải giữ hai lớp riêng.

### 12.2. Khung lớp quản lý phiên bản

```python
class VersionedMap:
    def __init__(self):
        self._versions = [
            VersionRecord(
                root=None,
                parents=(),
                operation="init",
            )
        ]

    @staticmethod
    def _check_key(key):
        if type(key) is not int:
            raise TypeError("key phải là int")

    def _check_version(self, version):
        if (
            type(version) is not int
            or not 0 <= version < len(self._versions)
        ):
            raise IndexError("version không hợp lệ")

    @property
    def version_count(self):
        return len(self._versions)

    def root(self, version):
        self._check_version(version)
        return self._versions[version].root

    def record(self, version):
        self._check_version(version)
        return self._versions[version]

    def put(self, base_version, key, value):
        self._check_version(base_version)
        self._check_key(key)
        if not isinstance(value, str):
            raise TypeError("value phải là str")

        old_root = self.root(base_version)
        new_root = _put(old_root, key, value)

        self._versions.append(
            VersionRecord(
                root=new_root,
                parents=(base_version,),
                operation="put",
            )
        )
        return len(self._versions) - 1

    def delete(self, base_version, key):
        self._check_version(base_version)
        self._check_key(key)

        old_root = self.root(base_version)
        new_root = _delete(old_root, key)

        self._versions.append(
            VersionRecord(
                root=new_root,
                parents=(base_version,),
                operation="delete",
            )
        )
        return len(self._versions) - 1

    def get(self, version, key):
        self._check_key(key)
        return _get(self.root(version), key)

    def items(self, version):
        return _items(self.root(version))

    def size(self, version):
        return _size(self.root(version))

    def _is_ancestor(self, ancestor, descendant):
        """Kiểm tra reachability trên đồ thị phiên bản."""
        stack = [descendant]
        seen = set()

        while stack:
            version = stack.pop()
            if version == ancestor:
                return True

            if version in seen:
                continue

            seen.add(version)
            stack.extend(self._versions[version].parents)

        return False
```

**Các phương thức của mục 13.1 sẽ được đặt tiếp bên trong cùng lớp `VersionedMap`**. Nếu ghép thành một tệp Python, hãy giữ chúng cùng mức thụt lề với `put`, `delete` và `_is_ancestor`.

### 12.3. Kiểm tra tổ tiên chung

Hàm `_is_ancestor(a,d)` đi từ phiên bản `d` ngược các cạnh `parents`. Nếu gặp `a` thì `a` là một tổ tiên (một đỉnh cũng được xem là tổ tiên của chính nó theo quy ước này).

Với `V` phiên bản đã lưu và mỗi phiên bản có tối đa hai cha, thao tác này có thể tốn **`O(V)` trong trường hợp xấu nhất**. Nó là công việc ở **đồ thị lịch sử**, không phải một truy vấn BST logarit.

Hệ thống lớn có thể xây chỉ mục tổ tiên, bảng nhảy, timestamp theo DAG hoặc các cấu trúc hỗ trợ reachability phù hợp, nhưng phải phân tích chi phí cập nhật chỉ mục và bộ nhớ riêng.

## 13. Hợp nhất ba chiều trên cây phiên bản

### 13.1. Phương thức `merge` có kiểm tra và chính sách xung đột

Các phương thức dưới đây là **phần tiếp theo của lớp `VersionedMap` ở mục 12.2**.

```python
    def merge(
        self,
        base_version,
        left_version,
        right_version,
        on_conflict="raise",
    ):
        """Tạo version có hai cha từ 3-way merge map.

        on_conflict:
            "raise": từ chối khi có khóa xung đột
            "prefer_left": lấy trạng thái trái ở khóa xung đột
            "prefer_right": lấy trạng thái phải ở khóa xung đột
        """
        for v in (
            base_version, left_version, right_version
        ):
            self._check_version(v)

        if on_conflict not in (
            "raise", "prefer_left", "prefer_right"
        ):
            raise ValueError("Chính sách xung đột không hợp lệ")

        if not self._is_ancestor(
            base_version, left_version
        ):
            raise ValueError(
                "base không phải tổ tiên của nhánh trái"
            )

        if not self._is_ancestor(
            base_version, right_version
        ):
            raise ValueError(
                "base không phải tổ tiên của nhánh phải"
            )

        base = dict(self.items(base_version))
        left = dict(self.items(left_version))
        right = dict(self.items(right_version))

        # Không được dùng None hoặc "" làm 'không tồn tại':
        # cả hai có thể là dữ liệu hợp lệ trong API khác.
        absent = object()

        all_keys = sorted(
            set(base) | set(left) | set(right)
        )

        result = []
        conflicts = []

        for key in all_keys:
            b = base.get(key, absent)
            l = left.get(key, absent)
            r = right.get(key, absent)

            if l == r:
                chosen = l
            elif l == b:
                chosen = r
            elif r == b:
                chosen = l
            else:
                # Cả hai nhánh đều đổi khác base và khác nhau.
                if on_conflict == "raise":
                    conflicts.append(key)
                    continue

                if on_conflict == "prefer_left":
                    chosen = l
                else:
                    chosen = r

            if chosen is not absent:
                result.append((key, chosen))

        if conflicts:
            # Không tạo version mới khi merge chưa giải quyết.
            raise ValueError(
                f"Xung đột tại các khóa: {conflicts}"
            )

        # result đã tăng theo khóa.
        merged_root = _build_sorted(result)

        self._versions.append(
            VersionRecord(
                root=merged_root,
                parents=(left_version, right_version),
                operation="merge",
                merge_base=base_version,
            )
        )
        return len(self._versions) - 1
```

### 13.2. Vì sao sentinel cho absent phải là đối tượng riêng?

Trong code:

```python
absent = object()
```

và dùng:

```python
value = some_map.get(key, absent)
```

Ta phân biệt được:

- Khóa không có trong map.
- Khóa có giá trị chuỗi rỗng `""`.
- Khóa có giá trị `"None"` dưới dạng chuỗi.

Vì API chỉ nhận `str` làm dữ liệu, sentinel là một đối tượng khác kiểu và không thể bị nhầm với bất kỳ chuỗi nào do người dùng thêm vào.

Việc so sánh `l==r` cũng hoạt động khi cả hai cùng thiếu khóa, vì chúng nhận **cùng một đối tượng `absent`**.

### 13.3. Vì sao dựng cây sau khi xác minh hết xung đột?

Quy trình:

1. Xác thực ID và quan hệ tổ tiên.
2. Đọc snapshot base/left/right.
3. Tính kết quả theo từng khóa và thu thập xung đột.
4. **Nếu có xung đột ở chế độ `raise`, trả lỗi trước khi công bố phiên bản.**
5. Nếu hợp lệ, dựng một AVL mới.
6. Thêm metadata phiên bản có hai cha.

Cách này tránh để một merge thất bại **để lại ID phiên bản nửa hoàn tất**.

Đó là **tính nguyên vẹn của thao tác ở mức API tuần tự trong ví dụ**, không có nghĩa là lớp đã cung cấp giao dịch an toàn cho nhiều luồng hoặc lưu bền sau mất điện.

### 13.4. Kỹ thuật hợp nhất có hai lớp hoàn toàn khác

Trong ví dụ:

- **Lớp lịch sử:** phiên bản kết quả có hai cha, lưu merge base.
- **Lớp dữ liệu:** tất cả khóa của kết quả được duyệt/tổng hợp rồi xây một AVL mới.

Nó chứng minh **ngữ nghĩa hợp nhất phiên bản**, nhưng **không tối ưu chia sẻ nút khi merge**. Các cập nhật `put/delete` riêng lẻ vẫn dùng path copying và chia sẻ cây con.

Một thuật toán merge persistent nâng cao có thể:

- So sánh identity của các cây con để bỏ qua nhánh **giống hệt đối tượng**.
- Dùng hash bất biến hoặc metadata khác để phát hiện cây con trùng nội dung (cần xử lý khả năng va chạm).
- Thực hiện union/diff theo khoảng khóa và tái sử dụng các cây con phù hợp.
- Gộp các thay đổi theo vùng với chi phí phụ thuộc **số nút khác nhau** hơn là tổng kích thước.

Nhưng tối ưu ấy cần chứng minh riêng về **độ đúng, chi phí split/join và cân bằng**. Không nên gán cho thuật toán dựng lại toàn cây ở đây độ phức tạp logarit.

## 14. Ví dụ đầy đủ: rẽ nhánh, hợp nhất và xung đột

### 14.1. Xây base chung

```python
store = VersionedMap()

v1 = store.put(0, 10, "A")
v2 = store.put(v1, 20, "B")
base = store.put(v2, 40, "D")

assert store.items(base) == [
    (10, "A"), (20, "B"), (40, "D")
]
assert store.size(base) == 3
```

Mỗi phiên bản tạo từ một phiên bản trước, nên ban đầu lịch sử là tuyến tính.

### 14.2. Hai nhánh sửa các khóa độc lập

```python
left1 = store.put(base, 10, "A+")
left = store.put(left1, 30, "C")

right1 = store.put(base, 20, "B+")
right = store.put(right1, 50, "E")

assert store.items(left) == [
    (10, "A+"), (20, "B"),
    (30, "C"), (40, "D"),
]

assert store.items(right) == [
    (10, "A"), (20, "B+"),
    (40, "D"), (50, "E"),
]

assert store.items(base) == [
    (10, "A"), (20, "B"), (40, "D")
]
```

### 14.3. Hợp nhất không xung đột

```python
merged = store.merge(base, left, right)

assert store.items(merged) == [
    (10, "A+"), (20, "B+"), (30, "C"),
    (40, "D"), (50, "E"),
]

rec = store.record(merged)
assert rec.parents == (left, right)
assert rec.merge_base == base
assert rec.operation == "merge"
```

Sơ đồ lịch sử:

```text
                     base
                    /    \
                  left1  right1
                   |       |
                  left    right
                    \      /
                     merged
```

Phiên bản `merged` chứa cả các thay đổi không xung đột. Phiên bản `base`, `left` và `right` vẫn nguyên vẹn.

### 14.4. Xung đột sửa–sửa

```python
left_conflict = store.put(base, 20, "B-left")
right_conflict = store.put(base, 20, "B-right")

before_count = store.version_count

try:
    store.merge(base, left_conflict, right_conflict)
except ValueError as exc:
    print(exc)  # Xung đột tại các khóa: [20]
else:
    raise AssertionError("Phải phát hiện xung đột")

assert store.version_count == before_count
```

**Không tạo thêm phiên bản** trong nhánh lỗi. Vì vậy không có “bản merge một nửa” được công bố.

### 14.5. Giải quyết xung đột có chính sách rõ

```python
prefer_left = store.merge(
    base,
    left_conflict,
    right_conflict,
    on_conflict="prefer_left",
)
assert store.get(prefer_left, 20) == "B-left"

prefer_right = store.merge(
    base,
    left_conflict,
    right_conflict,
    on_conflict="prefer_right",
)
assert store.get(prefer_right, 20) == "B-right"
```

**Ưu tiên trái/phải là chính sách ứng dụng**, không phải tính chất bắt buộc của confluent persistence. Với dữ liệu quan trọng, có thể yêu cầu người dùng quyết định thay vì tự chọn.

### 14.6. Xung đột xóa–sửa

```python
deleted = store.delete(base, 20)
edited = store.put(base, 20, "B-edited")

try:
    store.merge(base, deleted, edited)
except ValueError:
    pass
else:
    raise AssertionError("Xóa–sửa phải tạo xung đột")

# Chọn nhánh xóa bằng chính sách ưu tiên trái:
resolved = store.merge(
    base, deleted, edited,
    on_conflict="prefer_left",
)
assert store.get(resolved, 20) is None
```

### 14.7. Hai nhánh cùng xóa và cùng thêm

```python
l_delete = store.delete(base, 20)
r_delete = store.delete(base, 20)
both_deleted = store.merge(
    base, l_delete, r_delete
)
assert store.get(both_deleted, 20) is None

l_add = store.put(base, 99, "Z")
r_add = store.put(base, 99, "Z")
both_added = store.merge(base, l_add, r_add)
assert store.get(both_added, 99) == "Z"
```

Quy tắc `l==r` giúp tránh xung đột không cần thiết khi cả hai nhánh đã đạt **cùng trạng thái**.

### 14.8. Kiểm tra truy vấn bản cũ và chia sẻ cấu trúc

```python
old_root = store.root(base)
changed_root = store.root(left1)

assert old_root is not changed_root

# Việc put key=10 không đụng tới cây con bên phải
# của gốc 20 trong cấu hình AVL 3 khóa {10,20,40}.
assert old_root is not None
assert changed_root is not None
assert old_root.right is changed_root.right

assert store.get(base, 10) == "A"
assert store.get(left1, 10) == "A+"
```

Khi không phải xoay và chỉ thay giá trị một khóa, cây con không đổi được chia sẻ **theo định danh đối tượng**, không phải chỉ giống nhau về giá trị.

## 15. Kiểm tra tính đúng của AVL qua nhiều phiên bản

### 15.1. Những bất biến cần kiểm

- Một root phải biểu diễn một BST có **khóa phân biệt và thứ tự đúng theo mọi cận tổ tiên**.
- Mỗi nút lưu `height` và `size` khớp kết quả tính lại từ hai con.
- Mỗi nút có chênh lệch chiều cao AVL không quá `1`.
- Không có chu trình hoặc một đối tượng nút được dùng hai lần trong **cùng một root**.
- Có thể dùng một đối tượng nút trong **hai root khác nhau**; điều đó là structural sharing hợp lệ.
- Sau cập nhật/merge, các snapshot cũ vẫn cho đúng map cũ.

### 15.2. Validator hậu thứ tự độc lập

```python
def validate_avl(root: AVLNode | None) -> bool:
    if root is None:
        return True

    seen = set()
    actual = {}
    # (node, lower, upper, ready)
    frames = [(root, None, None, False)]

    while frames:
        node, lower, upper, ready = frames.pop()
        if node is None:
            continue
        if not isinstance(node, AVLNode):
            return False

        marker = id(node)

        if not ready:
            if marker in seen:
                return False
            seen.add(marker)

            if (
                type(node.key) is not int
                or not isinstance(node.value, str)
            ):
                return False

            if lower is not None and node.key <= lower:
                return False
            if upper is not None and node.key >= upper:
                return False

            frames.append((node, lower, upper, True))
            frames.append((node.right, node.key, upper, False))
            frames.append((node.left, lower, node.key, False))

        else:
            if node.left is None:
                left_size, left_height = 0, 0
            else:
                left_size, left_height = actual[id(node.left)]

            if node.right is None:
                right_size, right_height = 0, 0
            else:
                right_size, right_height = actual[id(node.right)]

            expected_size = 1 + left_size + right_size
            expected_height = (
                1 + max(left_height, right_height)
            )

            if node.size != expected_size:
                return False
            if node.height != expected_height:
                return False
            if abs(left_height - right_height) > 1:
                return False

            actual[marker] = (
                expected_size, expected_height
            )

    return True
```

Validator tính lại các trường từ liên kết thật, không dùng `size` và `height` hiện có để “xác nhận chính chúng”.

Thời gian và bộ nhớ phụ cho một root có `n` nút đều **`O(n)`**. Đây là công cụ kiểm thử, không phải việc cần làm sau mỗi cập nhật trong đường vận hành tối ưu.

### 15.3. Kiểm nhiều root sau các cập nhật

```python
store = VersionedMap()

v1 = store.put(0, 20, "B")
v2 = store.put(v1, 10, "A")
v3 = store.put(v2, 30, "C")
v4 = store.put(v2, 25, "Y")

m = store.merge(v2, v3, v4)

expected = {
    0: [],
    v1: [(20, "B")],
    v2: [(10, "A"), (20, "B")],
    v3: [(10, "A"), (20, "B"), (30, "C")],
    v4: [(10, "A"), (20, "B"), (25, "Y")],
    m: [
        (10, "A"), (20, "B"),
        (25, "Y"), (30, "C"),
    ],
}

for version, records in expected.items():
    assert store.items(version) == records
    assert store.size(version) == len(records)
    assert validate_avl(store.root(version))
```

Ngoài validator cấu trúc, cần so sánh với **mô hình tham chiếu** để bảo đảm nội dung đúng. Một cây có metadata hợp lệ vẫn có thể lưu **sai giá trị** do lỗi merge; chỉ đối chiếu dữ liệu mong đợi mới phát hiện được.

### 15.4. Kiểm thử lỗi xung đột không thay đổi lịch sử

```python
store = VersionedMap()
base = store.put(0, 10, "A")

l = store.put(base, 10, "L")
r = store.put(base, 10, "R")

old_versions = store.version_count
old_items = {
    i: store.items(i)
    for i in range(old_versions)
}

try:
    store.merge(base, l, r, on_conflict="raise")
except ValueError:
    pass
else:
    raise AssertionError("Phải báo xung đột")

assert store.version_count == old_versions

for i in range(old_versions):
    assert store.items(i) == old_items[i]
    assert validate_avl(store.root(i))
```

Đây là **mã minh họa để người học tự chạy**. Trong quy trình viết tài liệu, việc không chạy test chuyên môn là một ranh giới công việc riêng.

## 16. Phân tích độ phức tạp: cập nhật và hợp nhất không cùng chi phí

### 16.1. Ký hiệu

- `n`: số khóa trong một phiên bản AVL.
- `h`: chiều cao AVL, `O(\log(n+1))`.
- `n_b,n_l,n_r`: số khóa của ba snapshot base/left/right.
- `K`: số khóa phân biệt trong hợp khóa của ba snapshot.
- `V`: số phiên bản trong đồ thị lịch sử.
- `U`: số lần cập nhật khóa qua các phiên bản.

### 16.2. Bảng chi phí

| Thao tác | Thời gian | Bộ nhớ thêm | Ghi chú |
|---|---|---|---|
| Đọc khóa trong AVL | `O(\log(n+1))` | `O(1)` phụ | Đọc đường cây |
| Thêm/thay khóa, xóa khóa | `O(\log(n+1))` | `O(\log(n+1))` nút và stack | Path copying, AVL xoay thuần |
| Lưu root cho một ID mới | `O(1)` khấu hao | `O(1)` metadata | `list.append` |
| Truy vấn số lượng từ root | `O(1)` | `O(1)` | Đọc `size` |
| Liệt kê mọi cặp khóa–giá trị | `O(n)` | `O(n)` đầu ra | Inorder |
| Kiểm tổ tiên trên DAG phiên bản | `O(V)` xấu nhất | `O(V)` | Khi duyệt cha phiên bản |
| Tạo snapshot ba map | `O(n_b+n_l+n_r)` | `O(n_b+n_l+n_r)` | Thuật toán merge minh họa |
| Hợp khóa và sắp khóa | `O(K\log(K+1))` | `O(K)` | `sorted(set union)` |
| Dựng cây cân bằng kết quả | `O(K)` | `O(K)` nút mới | Một nút cho một khóa kết quả |

Với ví dụ `merge`:

\[
T_{\text{merge}}
=
O\left(V+n_b+n_l+n_r+K\log(K+1)\right).
\]

Bộ nhớ thêm trong một lần merge có thể là:

\[
O\left(V+n_b+n_l+n_r+K\right)
\]

tính cả `seen` cho kiểm tra tổ tiên, snapshot map và cây kết quả. Số nút của cây mới bằng số **khóa giữ lại trong kết quả**, không nhất thiết bằng `K` vì một số khóa đã bị xóa.

**Tổng quát:** chi phí một merge của cấu trúc có hai đầu vào **không mặc định bằng chi phí một point update**. Đây là lỗi phân tích rất thường gặp.

### 16.3. Chi phí lưu nhiều phiên bản full persistence

Với một cây AVL có `n_0` nút ban đầu và `U` lần cập nhật đơn khóa, mỗi lần trên phiên bản cỡ tối đa `N`:

\[
\boxed{
\text{nút cấp phát qua các cập nhật}
=
O(n_0+U\log(N+1)).
}
\]

Thêm `V` ID phiên bản cần `O(V)` metadata root/cha.

Tuy nhiên, nếu thực hiện `M` lần merge mà mỗi lần **dựng lại toàn bộ cây kết quả**, phải cộng thêm tổng số nút ở các cây merge:

\[
O\left(\sum_{j=1}^{M}n_{\text{result},j}\right).
\]

Vì vậy, không được tuyên bố tổng bộ nhớ của ví dụ confluent luôn chỉ `O(U\log N)` nếu có nhiều lần hợp nhất lớn.

### 16.4. Fat node partial persistence

Trong ví dụ `PartialHistoryMap`:

- Mỗi lần sửa một khóa thêm một bản ghi vào lịch sử khóa đó.
- Tra khóa ở phiên bản `v` dùng binary search trên các lần sửa của khóa.
- Tổng bộ nhớ tăng theo số lần sửa đã giữ.

Không thể lấy độ phức tạp đó thay cho path copying AVL nếu cấu trúc cần tìm khóa bằng đường cây. **Chọn thuật toán trước, rồi phân tích theo cấu trúc thực.**

### 16.5. Chi phí theo số bit và payload

Bảng trên giả định thao tác so sánh và sao chép tham chiếu tới khóa/giá trị có chi phí thích hợp. Nếu:

- Khóa là chuỗi rất dài, so sánh có thể tốn theo chiều dài tiền tố chung.
- Giá trị là một đối tượng lớn cần deep copy, chi phí sẽ tăng.
- Metadata gồm số nguyên cực lớn, phép toán số học không còn `O(1)` theo số bit.

Kết luận Big-O phải đi kèm **đơn vị chi phí** phù hợp, không che giấu đặc điểm dữ liệu thực tế.

## 17. Hợp nhất đúng dữ liệu khác với chia sẻ cấu trúc tối ưu

### 17.1. Hai việc cần chứng minh riêng

Một cấu trúc confluent có thể được đánh giá ở hai tầng:

1. **Tầng ngữ nghĩa:** kết quả hợp nhất có đúng nội dung dự kiến không? Có phát hiện xung đột không? Hai nhánh cũ còn đọc được không?
2. **Tầng biểu diễn:** cây kết quả chia sẻ được bao nhiêu nút? Có giữ BST/AVL, metadata và không tạo chu trình không? Chi phí cấp phát là bao nhiêu?

Bản `merge` của bài duyệt ba map, so sánh theo khóa rồi **dựng cây AVL mới từ danh sách đã sắp**. Nó đáp ứng tầng ngữ nghĩa nhưng **không tối ưu tái sử dụng các nút của hai đầu vào**.

### 17.2. Kiểm tra identity có ích như thế nào?

Giả sử cây con `T` ở bản trái và base là **cùng một đối tượng**:

```python
left_subtree is base_subtree
```

Nếu mọi nút/payload bất biến, ta có thể kết luận cây con ấy **giữ nguyên nội dung**. Thuật toán diff thông minh có thể bỏ qua cả nhánh.

Nhưng điều ngược lại không đúng:

```python
left_subtree is not base_subtree
```

**không chứng minh** nội dung khác. Hai phiên bản có thể xây những cây khác nhau nhưng biểu diễn cùng tập bản ghi. Vì vậy, identity là **dấu hiệu đủ để nhận ra một phần không đổi**, không phải tiêu chuẩn duy nhất để so sánh nội dung.

### 17.3. Vì sao không đơn giản gắn hai root làm hai con?

Hai map phiên bản thường chứa nhiều **khóa giống nhau**. Nếu lấy:

```text
new_root.left = left_root
new_root.right = right_root
```

ta có thể tạo:

- Hai bản ghi có cùng khóa trong một BST yêu cầu khóa phân biệt.
- Thứ tự khóa sai.
- Liên kết cây bị chia sẻ hai lần bên trong một root.
- Metadata `size/height` không còn đúng.
- Cây mất cân bằng.

Để tái sử dụng cây con một cách hiệu quả, thuật toán phải **phân hoạch theo vùng khóa**, xử lý trùng/xung đột, và gắn các cây con theo một phép **join/split** có chứng minh bảo toàn thứ tự và cân bằng.

### 17.4. Những hướng tối ưu nâng cao

Một thuật toán merge persistent nâng cao có thể:

- Đi đồng thời trên ba cây theo **khoảng khóa**.
- Bỏ qua cây con cùng identity và bất biến.
- Dùng hash của nội dung để phát hiện một số cây con giống nhau, nhưng phải xử lý nguy cơ va chạm nếu cần độ đúng tuyệt đối.
- Chỉ xây lại **những đường có thay đổi**.
- Dùng thuật toán union/difference của cây cân bằng để hợp nhất khóa và tái cân bằng.
- Dùng nhật ký thao tác/delta thay cho so sánh toàn bộ snapshot nếu các delta đáng tin và áp dụng được.

Tuy nhiên, không có chặn `O(\log n)` chung cho **mọi phép confluent merge**. Khi hai nhánh chứa rất nhiều thay đổi và kết quả cần xuất nhiều khóa, bản thân việc xử lý dữ liệu có thể tốn tuyến tính hoặc lớn hơn.

### 17.5. Lịch sử có thể chia sẻ và hội tụ phức tạp

Trong lịch sử hợp lưu, một bản có thể được merge nhiều lần vào các nhánh khác nhau. Nếu không quản lý rõ nguồn thay đổi, một thao tác có thể bị **áp dụng hai lần** khi gộp các delta theo cách cộng dồn không lũy đẳng.

Ví dụ, một lệnh “tăng bộ đếm thêm 5” xuất hiện trong cả hai nhánh vì cùng kế thừa từ một tổ tiên. Nếu merge bằng cách cộng **tất cả các lệnh trong hai log** mà không loại các lệnh chung, giá trị có thể bị tăng **hai lần**.

Đây là lý do các thuật toán dựa trên sự kiện hoặc CRDT thường phải có metadata định danh thao tác, quan hệ nhân quả hoặc cấu trúc đại số phù hợp. Three-way merge theo **snapshot base** là một hợp đồng khác với cộng trực tiếp hai nhật ký.

## 18. Chính sách xung đột phụ thuộc ngữ nghĩa nghiệp vụ

### 18.1. Phát hiện và yêu cầu giải quyết

Chính sách `on_conflict="raise"` là lựa chọn thận trọng khi:

- Hai bên sửa cùng một bản ghi theo hai giá trị khác nhau.
- Việc chọn sai có thể làm mất dữ liệu.
- Không có quy tắc nghiệp vụ để tự chọn một phía.

Thuật toán trả **danh sách khóa xung đột**, không tạo phiên bản kết quả. Ứng dụng có thể hiển thị:

```text
Key 20:
  base  = "B"
  left  = "B-left"
  right = "B-right"
```

cho người dùng quyết định.

### 18.2. Ưu tiên trái hoặc phải

Trong mã, `prefer_left` chỉ chọn dữ liệu bên trái **ở những khóa xung đột**.

Ví dụ:

```text
base  = {10:A,20:B}
left  = {10:A+,20:X}
right = {10:A, 20:Y,30:C}
```

Với `prefer_left`:

```text
merged = {10:A+,20:X,30:C}
```

Mặc dù khóa 20 lấy trái, khóa 30 vẫn được lấy từ nhánh phải vì đó là thay đổi **không xung đột**.

### 18.3. Last-write-wins không có từ ID phiên bản

Chính sách **last-write-wins** chọn bản ghi mới hơn theo một trật tự được quy định. Nhưng ID phiên bản tăng dần theo thời điểm tạo **không tự chứng minh** quan hệ “ghi sau về mặt nhân quả” giữa hai nhánh.

Muốn thực hiện LWW đúng theo đặc tả, phải lưu timestamp hoặc phiên bản logic thích hợp, xử lý trường hợp bằng nhau và cân nhắc đồng hồ không đồng bộ. Không nên dùng ID lớn hơn làm luật ẩn.

### 18.4. Bộ đếm cộng dồn cần ngữ nghĩa khác

Giả sử hai nhánh **tăng độc lập** cùng một bộ đếm:

```text
base = 10
left = 12   # tăng 2
right= 13   # tăng 3
```

Một luật kết hợp dựa trên delta có thể cho:

\[
merged=base+(left-base)+(right-base)=15.
\]

Đây là quy tắc hợp lý **nếu** hai nhánh thực sự chứa hai phép cộng độc lập. Nhưng nếu chúng là hai lần **gán lại** thành 12 và 13, cộng delta không còn là ngữ nghĩa bắt buộc.

### 18.5. CRDT không đồng nghĩa three-way merge

Trong một số **CRDT** (*Conflict-free Replicated Data Type*), phép gộp trạng thái được thiết kế có tính:

- **Giao hoán:** đổi thứ tự hai bản không đổi kết quả.
- **Kết hợp:** đổi cách nhóm các phép gộp không đổi kết quả.
- **Lũy đẳng:** gộp một trạng thái với chính nó không đổi trạng thái.

Các tính chất ấy hữu ích khi các bản sao đồng bộ không theo cùng thứ tự. Nhưng một map chứa chuỗi tùy ý với 3-way merge **không tự mang những tính chất đó**: nó có thể cần base, báo xung đột hoặc dùng chính sách thiên về một nhánh.

### 18.6. Văn bản và dãy không thể merge từng chỉ số một cách ngây thơ

Với văn bản:

```text
base:  "abcdef"
left:  "abXYcdef"   # chèn trước c
right: "abcdZZef"   # chèn trước e
```

Một phép chèn ở đầu làm các **chỉ số phía sau dịch chuyển**. Hợp nhất phải hiểu các thay đổi dựa trên **cùng vị trí base**, không chỉ so sánh ký tự cùng chỉ số ở hai snapshot cuối.

Đây là bài toán của thuật toán diff/merge văn bản hoặc những mô hình chỉnh sửa đồng thời như OT/CRDT, không phải chỉ của persistent BST.

## 19. Vòng đời phiên bản, bộ nhớ và đồng thời

### 19.1. Nút dùng chung không được giải phóng quá sớm

Giả sử:

```text
root_A ──┐
         ├──> shared_subtree
root_B ──┘
```

Nếu bỏ root A, cây con vẫn được root B tham chiếu nên không thể giải phóng ngay. Một nút chỉ có thể bị thu hồi khi **không còn tham chiếu còn sống** tới nó theo cơ chế quản lý bộ nhớ.

Nếu giữ mọi root mãi mãi, những nút chỉ còn một phiên bản rất cũ dùng vẫn có thể chiếm bộ nhớ.

### 19.2. Một số chính sách giữ lịch sử

- Giữ mọi phiên bản để hỗ trợ audit/truy vấn lịch sử đầy đủ.
- Giữ phiên bản gần đây và một số checkpoint.
- Chỉ giữ các phiên bản được đánh dấu hoặc đang có người đọc.
- Lưu log thay đổi và xây lại snapshot cần thiết khi truy vấn.
- Compact các cây phiên bản hoặc chuyển dữ liệu lịch sử sang storage khác.
- Thu hồi nút bằng reference counting, GC hoặc cơ chế quản lý vùng phù hợp.

Mỗi chính sách phải nói rõ **một ID cũ có còn truy vấn được không**, không chỉ giữ lại metadata tên phiên bản.

### 19.3. Nút bất biến không tự làm VersionedMap an toàn đa luồng

Mặc dù `AVLNode` là frozen, lớp `VersionedMap` vẫn thực hiện:

```python
self._versions.append(record)
```

Đó là cập nhật một danh sách mutable. Nếu nhiều luồng cùng ghi, hệ thống còn phải:

- Công bố ID và root mới một cách nhất quán.
- Đồng bộ danh sách phiên bản và metadata lịch sử.
- Đảm bảo snapshot không bị thu hồi khi có người còn đọc.
- Xác định thứ tự commit của các thao tác đồng thời.

**Bất biến nút** giúp truy vấn snapshot ổn định, nhưng **không tự cung cấp giao dịch hoặc linearizability**.

### 19.4. Commit nhiều khóa

Nếu muốn sửa nhiều khóa như một thao tác nguyên tử ở mức ứng dụng:

```text
r1 = put(r0, key1, value1)
r2 = delete(r1, key2)
r3 = put(r2, key3, value3)

publish(r3)  # Chỉ sau khi dựng xong mọi bước.
```

Nhờ các hàm thuần, không phải phơi bày cây cũ bị sửa dở. Nhưng việc **công bố root** và xử lý thất bại/nhiều luồng cần cơ chế giao dịch riêng.

### 19.5. Persistence không phải durability

Phiên bản còn đọc được trong bộ nhớ **không** bảo đảm còn tồn tại khi máy mất điện. Lưu bền cần các lớp:

- Mã hóa dữ liệu và ghi xuống đĩa/SSD.
- Commit và phục hồi sau lỗi.
- Xử lý nguyên tử khi lưu root, trang hoặc bản ghi lịch sử.
- Dọn dữ liệu không còn tham chiếu.
- Kiểm tra tính toàn vẹn của snapshot.

Đừng nhầm “bền vững phiên bản” trong lý thuyết với “ghi dữ liệu bền vững” trong cơ sở dữ liệu.

## 20. Liên hệ các cấu trúc dữ liệu khác

### 20.1. Persistent segment tree

Một cây đoạn persistent lưu tổng/min/max trên các đoạn chỉ số. Cập nhật điểm:

- Tạo lá mới.
- Tạo các nút mới trên đường về gốc.
- Dùng lại các cây con không thay đổi.
- Giữ root cũ để truy vấn.

Với cây đoạn cân bằng, cập nhật một chỉ số thường tốn **`O(\log n)` nút mới**. Đây là cùng ý tưởng path copying nhưng theo **miền chỉ số cố định**, không phải BST theo khóa.

### 20.2. Persistent trie và HAMT

Trong trie/HAMT, cập nhật một khóa đi theo ký tự hoặc các phần của giá trị hash:

- Các nút trên đường thay đổi được tạo mới.
- Các nhánh khác được dùng chung.
- Gốc cũ vẫn còn hiệu lực.

Chi phí phụ thuộc chiều dài đường theo biểu diễn khóa/độ phân nhánh, không nhất thiết theo chiều cao AVL.

### 20.3. Rope và cây lưu dãy

Rope chứa các khối chuỗi ở lá, còn các nút trong có thể lưu độ dài cây con. Một thao tác chèn vào văn bản có thể path-copy các nút đường tới lá và chia sẻ các khối khác.

Nhưng merge hai **nhánh chỉnh sửa văn bản** cần ngữ nghĩa vị trí/diff riêng; thao tác nối hai rope không tự trở thành 3-way merge lịch sử.

### 20.4. B-tree phân trang

Trong B-tree/B+ tree bền vững, đơn vị sao chép có thể là **trang chứa nhiều khóa** thay vì một nút nhị phân. Khi cập nhật, sao chép các trang trên đường tới gốc và chia sẻ trang không đổi.

Việc chọn B-tree thường liên quan kích thước page, I/O và lưu bền. Nó giữ tinh thần **sao chép đường đi**, nhưng có khác biệt đáng kể về chi phí trang và cơ chế split/merge.

## 21. Bảng chọn mô hình theo nhu cầu

| Yêu cầu | Cách tiếp cận đáng cân nhắc | Điểm phải kiểm tra |
|---|---|---|
| Chỉ cần trạng thái hiện hành | Ephemeral | Không cần lưu snapshot |
| Đọc mọi bản cũ, chỉ sửa bản cuối | Partial persistence | Lịch sử tuyến tính |
| Undo rồi sửa thành nhánh mới | Full persistence | Cập nhật từ root cũ |
| Hợp nhất hai nhánh độc lập | Confluent merge trên cấu trúc persistent | Base, xung đột, ngữ nghĩa dữ liệu |
| Sửa một khóa nhanh, có thứ tự | Persistent AVL/BST cân bằng | Path copying, phép xoay thuần |
| Truy vấn theo đoạn chỉ số | Persistent segment tree | Metadata và miền chỉ số |
| Map lớn với dữ liệu chia sẻ | Trie/HAMT hoặc cấu trúc phù hợp | Payload bất biến |
| Chỉnh sửa văn bản nhiều phiên bản | Rope hoặc dãy có cấu trúc phiên bản | Diff/merge văn bản |
| Đồng bộ phân tán không theo thứ tự | Cấu trúc/CRDT phù hợp | Tính giao hoán/kết hợp/lũy đẳng |
| Snapshot sống qua khởi động lại | Cơ chế storage và commit | Durability không miễn phí |

Chọn mô hình từ **truy vấn, cập nhật, hành vi rẽ nhánh/hợp nhất và tài nguyên thực tế**, không phải vì mô hình nhiều tính năng hơn luôn tốt hơn.

## 22. Ma trận tình huống biên cần thử

| Tình huống | Hành vi mong đợi |
|---|---|
| Map phiên bản 0 rỗng | `get` trả không có |
| Put ở bản cũ bất kỳ | Bản mới là nhánh mới, bản cũ không đổi |
| Put cùng giá trị | Có thể dùng lại root |
| Delete khóa không tồn tại | Không đổi nội dung |
| Delete nút có hai con | Cây mới hợp lệ; cây cũ không đổi |
| Chèn gây xoay AVL | Cân bằng, metadata đúng |
| Merge hai thay đổi trên khóa khác nhau | Giữ cả hai |
| Hai nhánh cùng sửa giống nhau | Không xung đột |
| Hai nhánh cùng xóa | Kết quả khóa vắng mặt |
| Hai nhánh cùng thêm khác giá trị | Xung đột |
| Xóa–sửa cùng khóa | Xung đột theo mặc định |
| Base không là tổ tiên của cả hai nhánh | Báo lỗi |
| Có xung đột và policy `raise` | Không tạo ID mới |
| Policy ưu tiên trái | Chỉ khóa xung đột chọn trái |
| Policy ưu tiên phải | Chỉ khóa xung đột chọn phải |
| Chọn version không tồn tại | Báo lỗi |
| Hai root chia sẻ một nút | Hợp lệ khi nút bất biến |
| Một root chứa chu trình | Validator phải từ chối |
| Chuỗi rỗng là value | Giữ như dữ liệu thật, không coi ABSENT |
| Version ID lớn hơn | Không chứng minh là hậu duệ |
| Bỏ một root | Không giải phóng cây con còn được tham chiếu |

## 23. Các lỗi thường gặp khi thiết kế phiên bản và hợp nhất

1. **Đồng nhất persistence với lưu bền sau mất điện.** Khả năng đọc lại trạng thái cũ trong bộ nhớ không tự bao gồm durability.
2. **Cho rằng copy root là snapshot khi nút vẫn mutable.** Các gốc khác nhau có thể trỏ tới cùng nút bị sửa.
3. **Nhầm partial với full persistence.** Partial chỉ cập nhật từ bản mới nhất; full có thể rẽ nhánh từ bản cũ.
4. **Cho rằng full persistence đã hỗ trợ merge.** Hợp nhất nhiều nhánh là khả năng bổ sung với hợp đồng riêng.
5. **Tạo phiên bản có hai cha nhưng không xác định dữ liệu kết quả.** Đồ thị lịch sử đúng hình chưa chứng minh merge đúng.
6. **Lấy ID tăng làm thứ tự tổ tiên.** ID không thay thế phép kiểm tra DAG.
7. **Bỏ qua merge base.** Hai giá trị cuối không cho biết bên nào đã sửa nếu không biết trạng thái gốc.
8. **Dùng chuỗi rỗng hoặc số 0 làm absent mặc dù là giá trị hợp lệ.** Có thể hiểu nhầm xóa với cập nhật.
9. **Hai bên cùng sửa giá trị giống nhau mà báo xung đột.** Quy tắc `l==r` nên xử lý trường hợp này.
10. **Hai bên cùng xóa mà báo xung đột.** Cả hai cùng đạt ABSENT.
11. **Xóa–sửa mà tự động chọn một bên không công bố chính sách.** Dễ làm mất dữ liệu.
12. **Hai bên cùng thêm một khóa với hai giá trị khác nhau mà gộp không báo gì.** Đây là xung đột thêm–thêm.
13. **Cho rằng prefer_left nghĩa là bỏ toàn bộ dữ liệu của right.** Chỉ những khóa xung đột mới cần ưu tiên.
14. **Chọn last-write-wins theo ID mà không có metadata thời gian/nhân quả.** Có thể quyết định sai.
15. **Nhầm merge văn bản với merge map từng chỉ số.** Chèn/xóa làm lệch vị trí ở hai nhánh.
16. **Cho rằng merge nào cũng giao hoán, kết hợp, lũy đẳng.** Tính chất phụ thuộc luật merge và base.
17. **Áp quy tắc cộng delta cho giá trị số bị gán tuyệt đối.** Có thể tạo kết quả không có ý nghĩa nghiệp vụ.
18. **Cộng lại toàn bộ event log ở hai nhánh mà không loại phần tổ tiên chung.** Có thể áp dụng một thao tác hai lần.
19. **Gắn hai root BST làm hai cây con của một nút mới để “hợp nhất”.** Có thể gây khóa trùng và phá thứ tự.
20. **Tái sử dụng các con trỏ mutable trong một phép xoay AVL persistent.** Sửa nút cũ sẽ làm hỏng nhiều phiên bản.
21. **Tính lại size/height trên nút cũ thay vì tạo nút mới.** Metadata cũng thuộc nội dung bất biến.
22. **Không cân bằng lại sau xóa có hai con.** Một BST đúng thứ tự vẫn có thể mất bất biến AVL.
23. **Lấy kế nhiệm nhưng quên con phải của kế nhiệm.** Có thể làm mất cả một cây con.
24. **Sao chép khóa kế nhiệm nhưng không chép giá trị đi kèm.** Cây giữ thứ tự nhưng map sai.
25. **Trả một nút mới dù no-op và cho rằng đó là bắt buộc.** Có thể dùng lại nguyên root.
26. **Thấy root khác identity rồi kết luận hai bản có dữ liệu khác.** Cấu trúc có thể khác nhưng nội dung bằng nhau.
27. **Thấy root cùng identity rồi vẫn cho mã ngoài sửa payload.** Identity chỉ bảo vệ dữ liệu khi đối tượng bất biến.
28. **Tin rằng frozen dataclass đóng băng sâu mọi đối tượng bên trong.** Một list được tham chiếu vẫn có thể thay đổi.
29. **Cho rằng danh sách thay đổi theo khóa đã là persistent AVL.** Nó chưa triển khai liên kết và truy vấn cây.
30. **Gán chi phí fat node cho mọi kiểu cập nhật.** Truy vấn liên kết cây còn phụ thuộc chiều cao và lịch sử từng trường.
31. **Áp kết quả node-copying partial với `O(1)` khấu hao cho mọi DAG.** Các giả thiết bậc vào và mô hình cần được kiểm tra.
32. **Suy ra merge toàn bộ là `O(\log n)` vì point update là `O(\log n)`.** Đó là hai thao tác khác nhau.
33. **Quảng bá merge chia sẻ tối đa trong khi code dựng lại AVL từ mọi khóa.** Cấp phát nút mới phụ thuộc độ lớn kết quả.
34. **Chỉ đọc bản merged sau khi hợp nhất.** Phải kiểm lại base, left và right để phát hiện mutation cũ.
35. **Chỉ kiểm AVL height/size mà không đối chiếu key/value.** Cấu trúc đúng chưa bảo đảm nội dung merge đúng.
36. **Coi một nút dùng chung giữa các root là lỗi.** Structural sharing là mục đích của persistence.
37. **Cho phép một node xuất hiện ở hai vị trí trong một root BST khóa phân biệt.** Lúc đó cấu trúc không còn là cây hợp lệ theo hợp đồng.
38. **Thêm trường parent mutable vào nút dùng chung.** Cha có thể khác theo phiên bản.
39. **Bỏ root cũ nhưng vẫn cho phép query ID ấy không có cơ chế tái dựng.** Snapshot đã không còn sẵn sàng truy vấn.
40. **Giữ mọi root nhưng kỳ vọng GC xóa những cây chỉ root cũ tham chiếu.** Chúng vẫn đang sống.
41. **Dùng cấu trúc immutable nhưng cho nhiều luồng cùng append metadata phiên bản không đồng bộ.** Nút an toàn không đồng nghĩa manager an toàn.
42. **Tin rằng path copying tự cung cấp commit nhiều khóa.** Cần quy tắc công bố root sau khi hoàn tất.
43. **Dùng ID lớn nhất làm merge base khi DAG có nhiều tổ tiên chung.** Phải chọn theo quan hệ tổ tiên và chính sách.
44. **Giữ phiên bản không giới hạn mà không hoạch định tài nguyên.** Tổng node, root và metadata lịch sử tiếp tục tăng.
45. **Chạy validator `O(n)` sau mọi cập nhật rồi tính cả quy trình là `O(\log n)`.** Phải tách kiểm thử khỏi chi phí đường vận hành.

## 24. Bài tập có lời giải

### Bài 1. Phân loại mô hình đọc cũ, chỉ sửa mới

Một hệ thống cho phép truy vấn mọi snapshot nhưng chỉ được cập nhật snapshot mới nhất. Đây là loại nào?

**Đáp án:** **Bền vững từng phần (partially persistent)**.

### Bài 2. Phân loại mô hình có thể sửa bản cũ

Một ứng dụng cho phép lấy `v3` làm nền để tạo `v8` dù `v7` đang là bản mới nhất. Đây là mô hình gì?

**Đáp án:** **Bền vững toàn phần (fully persistent)**.

### Bài 3. Phân loại mô hình hai đầu vào

Một thao tác `combine(v4,v6)` tạo một phiên bản mới bằng cách kết hợp cả hai đầu vào. Nếu được hỗ trợ như một phép cấu trúc hợp lệ, đây là khả năng gì?

**Đáp án:** **Bền vững hợp lưu (confluent persistence)**.

### Bài 4. Partial persistence và nhánh

Với chuỗi `v0→v1→v2` trong partial persistence chuẩn, có được gọi `update(v0)` để tạo một nhánh mới hay không?

**Đáp án:** **Không**. Chỉ được cập nhật phiên bản mới nhất; `v0` vẫn đọc được.

### Bài 5. Full persistence và nhánh

Cho `v1` có hai con là `v2,v3`. Có thể suy ra `v3` chứa thay đổi của `v2` không?

**Đáp án:** **Không**. Hai bản cùng lấy `v1` làm nền, không tự thừa hưởng cập nhật của nhau.

### Bài 6. Phân biệt đồ thị

Một root ở phiên bản A và một root ở phiên bản B cùng trỏ tới cây con S. Đây là cạnh giữa hai phiên bản hay liên kết trong cấu trúc dữ liệu?

**Đáp án:** Đây là **liên kết nút dữ liệu được chia sẻ** giữa hai cây. Quan hệ cha–con trong DAG lịch sử phiên bản là lớp khác.

### Bài 7. Sao chép nông

Vì sao sao chép gốc BST rồi sửa trực tiếp `new_root.left.value` có thể làm hỏng snapshot cũ?

**Đáp án:** Hai gốc có thể cùng tham chiếu tới **nút trái mutable**, nên thao tác ghi vào một đối tượng ảnh hưởng cả hai.

### Bài 8. Path copying

Đường từ gốc tới khóa cần sửa có bốn nút, không cần xoay. Thay giá trị khóa ấy cần tạo bao nhiêu nút mới với cách sao chép một nút mỗi tầng?

**Đáp án:** **Bốn nút mới**, gồm nút thay giá trị và ba tổ tiên.

### Bài 9. AVL và độ phức tạp

Một cây AVL có `n` khóa. Cập nhật một khóa bằng path copying tốn bao nhiêu thời gian và bao nhiêu nút mới theo bậc tăng trưởng?

**Đáp án:** **`O(\log(n+1))`** cho thời gian và số nút mới, với các giả thiết AVL và phép toán cơ bản.

### Bài 10. Fat node

Lịch sử của một trường là `(1,A),(4,B),(9,C)`. Truy vấn tại phiên bản `6` trả gì?

**Đáp án:** **`B`**, bản ghi mới nhất có mốc phiên bản không vượt `6`.

### Bài 11. Tìm trong lịch sử

Nếu một trường có `k` bản ghi lịch sử tăng theo version, binary search để tìm bản gần nhất có độ phức tạp gì?

**Đáp án:** **`O(\log(k+1))`** thời gian.

### Bài 12. No-op

Một bản cũ đã lưu `20:"B"`. Thực hiện `put(20,"B")` có bắt buộc cấp phát nút cây mới không?

**Đáp án:** **Không**. Có thể trả về cùng root nhưng vẫn ghi một ID phiên bản mới nếu API yêu cầu.

### Bài 13. Full persistence không tự confluent

Tại sao cho phép cập nhật từ mọi root chưa đủ để tự hợp nhất hai nhánh?

**Đáp án:** Vì cần **định nghĩa dữ liệu kết quả**, nhận diện thay đổi độc lập và xử lý xung đột. API một đầu vào không tự giải bài toán nhiều đầu vào.

### Bài 14. Base trong three-way merge

Vì sao cần snapshot chung base khi left và right có giá trị khác nhau?

**Đáp án:** Base cho biết nhánh nào đã thay đổi từ trạng thái gốc. Chỉ nhìn hai giá trị cuối thường không phân biệt được bên sửa hay bên giữ nguyên.

### Bài 15. Chỉ một bên sửa

Cho `b="A", l="A", r="B"`. Kết quả ba chiều là gì?

**Đáp án:** **`"B"`**, vì trái giữ nguyên base, chỉ phải thay đổi.

### Bài 16. Hai bên cùng sửa giống nhau

Cho `b="A", l="B", r="B"`. Có xung đột không?

**Đáp án:** **Không**. Hai nhánh có cùng trạng thái cuối, nên chọn `"B"`.

### Bài 17. Hai bên sửa khác nhau

Cho `b="A", l="B", r="C"`. Chế độ `raise` phải làm gì?

**Đáp án:** **Báo xung đột**, không công bố phiên bản hợp nhất.

### Bài 18. Cùng xóa

Cho `b="A", l=ABSENT, r=ABSENT`. Kết quả?

**Đáp án:** **ABSENT**, không giữ khóa, không xung đột.

### Bài 19. Xóa–sửa

Cho `b="A", l=ABSENT, r="B"`. Có xung đột không?

**Đáp án:** **Có**, vì trái xóa còn phải sửa khóa.

### Bài 20. Cùng thêm cùng giá trị

Base không có khóa `50`, hai nhánh đều thêm `50:"E"`. Kết quả?

**Đáp án:** Giữ **`50:"E"`**, không xung đột.

### Bài 21. Cùng thêm khác giá trị

Base không có khóa `50`, trái thêm `"E"`, phải thêm `"F"`. Cần xử lý sao?

**Đáp án:** **Xung đột thêm–thêm**, trừ khi ứng dụng có chính sách giải quyết.

### Bài 22. Sentinel cho ABSENT

Tại sao không dùng chuỗi rỗng `""` biểu thị khóa không có trong một map cho phép lưu chuỗi rỗng?

**Đáp án:** Vì `""` là **dữ liệu hợp lệ**. Cần sentinel không thể bị nhầm với giá trị của người dùng.

### Bài 23. Policy prefer_left

Trong một merge, khóa 20 xung đột nhưng khóa 30 chỉ nhánh phải mới thêm. Dùng `prefer_left` có bỏ khóa 30 không?

**Đáp án:** **Không**. Chính sách chỉ chọn trái ở các khóa xung đột; thay đổi độc lập ở khóa 30 vẫn được nhận.

### Bài 24. Merge không phát hành khi lỗi

Nếu phiên bản có `V` ID trước khi merge với `raise` và gặp xung đột, số phiên bản sau thao tác là bao nhiêu?

**Đáp án:** Vẫn là **`V`**. Ví dụ bài thu thập xung đột và báo lỗi trước khi thêm ID.

### Bài 25. Kiểm tra tổ tiên

Nếu `id(left)=5` và `id(right)=9`, có chắc left là tổ tiên của right không?

**Đáp án:** **Không.** Cần đi theo cạnh `parents` hoặc dùng chỉ mục reachability phù hợp.

### Bài 26. Merge base quá cũ

Một base là tổ tiên chung của hai nhánh nhưng không gần nhất. Có chắc đây là base được mong muốn trong quy trình hợp nhất không?

**Đáp án:** **Không**. Với DAG phức tạp cần chính sách chọn merge base, không chỉ kiểm tra “là tổ tiên”.

### Bài 27. Fast-forward

Nếu nhánh hiện hành là tổ tiên trực tiếp hoặc gián tiếp của nhánh đích và không có thay đổi độc lập cần gộp, có cần tạo merge commit hai cha không?

**Đáp án:** **Không nhất thiết.** Có thể chuyển tham chiếu hiện hành tới phiên bản đích (*fast-forward*).

### Bài 28. Chi phí merge

Một merge cần duyệt ba map có `n_b,n_l,n_r` bản ghi và sắp hợp `K` khóa. Chặn trên thời gian cơ bản là gì, chưa tính kiểm tra lịch sử?

**Đáp án:**

\[
O(n_b+n_l+n_r+K\log(K+1)).
\]

Nếu có kiểm tra tổ tiên bằng duyệt DAG `V` bản, cộng thêm `O(V)` trường hợp xấu nhất.

### Bài 29. Xây lại cây từ danh sách đã sắp

Danh sách kết quả chứa `K` khóa tăng. Dựng AVL bằng chọn phần tử giữa đệ quy có chi phí nào?

**Đáp án:** **`O(K)` thời gian**, tạo `K` nút mới và cây có chiều cao logarit.

### Bài 30. Merge chia sẻ tối đa?

Nếu mã merge chuyển mọi bản thành dict rồi dựng cây mới hoàn toàn, có thể tuyên bố nó tận dụng chia sẻ nút giữa cây kết quả và đầu vào không?

**Đáp án:** **Không.** Các đầu vào vẫn bất biến, nhưng cây merge được dựng mới; cần thuật toán tối ưu khác để tái sử dụng cây con.

### Bài 31. Identity

Nếu `left_subtree is base_subtree` và mọi nút bất biến, kết luận gì?

**Đáp án:** Cây con ấy **không đổi nội dung** và có thể được bỏ qua khi so sánh sâu.

### Bài 32. Identity khác

Nếu `left_subtree is not base_subtree`, có chắc nội dung khác không?

**Đáp án:** **Không**. Một cây mới sau tái cân bằng có thể biểu diễn cùng tập khóa/giá trị.

### Bài 33. Đồng thời

Vì sao frozen AVLNode không tự biến `VersionedMap` thành thread-safe?

**Đáp án:** Vì còn các cập nhật vào **danh sách phiên bản**, cơ chế công bố root, phân phối ID và thu hồi bộ nhớ. Chúng cần đồng bộ riêng.

### Bài 34. Payload khả biến

Một frozen node chứa list `[1,2]`. Mã ngoài gọi `append(3)` trên list đó. Snapshot cũ có giữ nguyên dữ liệu không?

**Đáp án:** **Không.** Bất biến trường nút không có nghĩa list bên trong đã bất biến sâu.

### Bài 35. CRDT

Có phải mọi 3-way merge theo base đều có tính kết hợp, giao hoán và lũy đẳng như state-based CRDT không?

**Đáp án:** **Không.** CRDT đòi hỏi một phép gộp và trạng thái được thiết kế theo các tính chất cụ thể; 3-way merge có thể báo xung đột hoặc dùng ưu tiên một bên.

### Bài 36. Cộng bộ đếm

Base là `10`, trái tăng `+2`, phải tăng `+3`. Nếu luật nghiệp vụ là hợp nhất các phép tăng độc lập, giá trị là gì?

**Đáp án:** **`15`**, theo `10+2+3`. Không áp dụng công thức này cho thao tác gán tuyệt đối.

### Bài 37. Giữ root cũ

Xóa một ID root khỏi danh sách quản lý có giải phóng ngay một cây con mà ID khác vẫn tham chiếu không?

**Đáp án:** **Không.** Cây con chỉ có thể thu hồi khi không còn tham chiếu giữ nó sống.

### Bài 38. Test nội dung và cấu trúc

Vì sao cần kiểm `items(version)` ngoài `validate_avl(root)`?

**Đáp án:** Validator kiểm **cấu trúc và metadata**, không biết kết quả merge **nên có giá trị nào**. Cần đối chiếu với map tham chiếu hoặc kết quả mong đợi.

### Bài 39. Kiểm thử bản cũ

Một merge chạy thành công và kết quả đúng. Tại sao vẫn phải đọc lại base/left/right?

**Đáp án:** Để phát hiện phép sửa vô ý lên **nút hoặc payload dùng chung**; tính đúng của bản mới chưa đủ chứng minh persistence.

### Bài 40. Lựa chọn mô hình cho ứng dụng

Một trình biên tập cần xem lịch sử, undo rồi chỉnh sửa thành nhánh mới và hợp nhất hai nhánh. Mô hình khả năng nào là phù hợp?

**Đáp án:** Cần ít nhất **full persistence** để cập nhật từ snapshot cũ, và cần **phép confluent merge** với quy tắc hợp nhất văn bản/xung đột phù hợp. Phải thiết kế thêm quản lý phiên bản, bộ nhớ và đồng thời nếu có.

## 25. Checklist thiết kế và triển khai

- [ ] Định nghĩa rõ cần ephemeral, partial, full hay confluent persistence.
- [ ] Mỗi snapshot được truy cập qua một root hoặc cách tái dựng đáng tin cậy.
- [ ] Tách đồ thị lịch sử phiên bản khỏi đồ thị các nút dữ liệu.
- [ ] Partial persistence giới hạn cập nhật trên bản mới nhất; lịch sử trường tra đúng mốc.
- [ ] Full persistence cho phép rẽ nhánh mà không sửa snapshot cũ.
- [ ] Các nút và payload dùng chung bất biến theo ngữ nghĩa.
- [ ] Các phép xoay hoặc tái cân bằng đều không sửa nút phiên bản trước.
- [ ] Chi phí cập nhật điểm được phân tích theo chiều cao cấu trúc.
- [ ] Merge nhận nhiều phiên bản và có **định nghĩa dữ liệu kết quả**.
- [ ] Three-way merge có base và sentinel riêng cho ABSENT.
- [ ] Đã xử lý xung đột sửa–sửa, thêm–thêm, xóa–sửa và cùng xóa.
- [ ] Chính sách xung đột được công bố và có thể kiểm thử.
- [ ] Đồ thị phiên bản kiểm tra quan hệ tổ tiên, không dựa vào thứ tự ID.
- [ ] Có nguyên tắc chọn merge base nếu lịch sử đã có nhiều nhánh/merge.
- [ ] Merge thất bại không công bố phiên bản nửa hoàn tất.
- [ ] Phân tích riêng chi phí update một khóa, diff, merge và duy trì root.
- [ ] Không gán bảo đảm chia sẻ cấu trúc cho thuật toán dựng cây mới hoàn toàn.
- [ ] Có validator và đối chiếu nội dung bằng mô hình tham chiếu.
- [ ] Test cả các snapshot cũ sau những cập nhật và hợp nhất.
- [ ] Có chính sách giữ, dọn hoặc lưu bền các phiên bản.
- [ ] Nếu có nhiều luồng, có cơ chế công bố phiên bản và quản lý bộ nhớ an toàn.

## 26. Tổng kết

Ba mức bền vững khác nhau bởi **phép thao tác được phép trên lịch sử**:

\[
\boxed{\text{Partial: đọc mọi phiên bản, chỉ cập nhật bản mới nhất}}
\]

\[
\boxed{\text{Full: đọc và cập nhật từ bất kỳ phiên bản đã giữ}}
\]

\[
\boxed{\text{Confluent: còn có thể kết hợp nhiều phiên bản}}
\]

**Partial persistence** phù hợp với lịch sử tuyến tính và có thể dùng lịch sử thay đổi theo trường (*fat node*) hoặc node-copying chuyên biệt. **Full persistence** cho phép rẽ nhánh; với các nút bất biến và path copying, một cập nhật đơn khóa trên AVL tạo **`O(\log(n+1))` nút mới** và chia sẻ những cây con không đổi. **Confluent persistence** cần thêm một phép toán kết hợp nhiều phiên bản với **ngữ nghĩa dữ liệu được xác định rõ**.

Đối với một map, three-way merge dùng **base chung** để phân biệt thay đổi độc lập, thay đổi giống nhau và thay đổi mâu thuẫn. Phải xử lý đúng **ABSENT**, xóa–sửa, thêm–thêm và chính sách giải quyết xung đột. Phiên bản kết quả có thể mang **hai cha** trong DAG lịch sử, nhưng quan hệ cha đó khác với liên kết trái/phải của cây dữ liệu.

Cần nhớ rằng:

- **Giữ đúng lịch sử** không đồng nghĩa với **chia sẻ nút tối ưu**.
- **Chia sẻ nút** chỉ an toàn khi nút và dữ liệu được chia sẻ **không bị sửa**.
- **Cập nhật một khóa** có thể logarit, nhưng **hợp nhất hai snapshot lớn** có thể tốn tuyến tính hoặc nhiều hơn.
- **Bất biến trong bộ nhớ** không tự giải quyết lưu bền, giao dịch và đồng thời.

Hiểu rõ mô hình partial/full/confluent, bất biến và phép merge dựa trên dữ liệu giúp lựa chọn và xây dựng cấu trúc phiên bản **đúng đắn, có thể kiểm chứng, kiểm soát được thời gian và bộ nhớ, đồng thời giữ được những trạng thái lịch sử mà ứng dụng thực sự cần**.

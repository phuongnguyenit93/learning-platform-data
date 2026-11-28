# Ngẫu nhiên hóa hình dạng cấu trúc thay vì chỉ ngẫu nhiên hóa dữ liệu vào

Giả sử một chương trình phải lưu các khóa `1, 2, 3, ..., 100000` trong **cây tìm kiếm nhị phân (BST)**. Nếu ta chèn lần lượt theo thứ tự tăng dần vào BST thông thường không tự cân bằng, cây có thể biến thành một **danh sách một đường**. Tìm kiếm, chèn và xóa có thể mất **O(n)** thay vì O(log n). Một cách ứng phó là xáo trộn thứ tự khóa trước khi chèn; nhưng điều đó chỉ giải quyết được **một đợt nạp dữ liệu** mà chương trình kiểm soát. Những khóa cập nhật về sau vẫn có thể đến theo thứ tự bất lợi.

Một hướng khác: giữ nguyên dữ liệu và thứ tự yêu cầu, nhưng **ngẫu nhiên hóa chính những quyết định làm nên hình dạng cấu trúc**. Ví dụ, mỗi khóa trong **treap** nhận một **độ ưu tiên ngẫu nhiên độc lập**; cấu trúc phải đồng thời thỏa thứ tự tìm kiếm theo khóa và thứ tự heap theo ưu tiên. Với giả định ngẫu nhiên phù hợp, hình dạng kỳ vọng đủ cân bằng dù khóa được đưa vào theo thứ tự tăng, giảm hoặc một thứ tự cố định do bên ngoài chọn.

Bài **“Ngẫu nhiên hóa hình dạng cấu trúc thay vì chỉ ngẫu nhiên hóa dữ liệu vào”** thuộc chương **Cấu trúc ngẫu nhiên** trong module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Module xây dựng nền tảng về mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, trọng tâm là **bất biến, thao tác, độ phức tạp thời gian và bộ nhớ** để lựa chọn cấu trúc phù hợp. Bài này dùng treap và skip list để phân biệt hai nguồn ngẫu nhiên, chỉ ra vì sao thuật toán có thể **đúng trên mọi đầu vào hợp lệ** nhưng **chi phí phụ thuộc vào lựa chọn ngẫu nhiên bên trong**.

**Mục tiêu sau bài học:**

- Phân biệt ngẫu nhiên hóa **dữ liệu hoặc thứ tự đầu vào** với ngẫu nhiên hóa **quy tắc xây hình dạng cấu trúc**.
- Hiểu mô hình phân tích **kỳ vọng trên lựa chọn ngẫu nhiên của thuật toán**, giữ đầu vào cố định; không nhầm *expected* với bảo đảm thời gian xấu nhất.
- Giải thích hai bất biến của **treap**: BST theo khóa và heap theo ưu tiên, cùng tác dụng của phép quay trái/phải.
- Cài đặt treap Python có tìm, thêm, xóa, duyệt, kiểm tra bất biến và seed tái lập; phân tích chi phí kỳ vọng O(log n).
- Hiểu ý tưởng **skip list** dùng số tầng được bốc ngẫu nhiên thay vì dựa vào dữ liệu đã xáo trộn.
- Biết ảnh hưởng của **phân phối ưu tiên, va chạm, seed, tính dự đoán được của PRNG**, yêu cầu bảo mật và kiểm thử thống kê.
- Chọn một cấu trúc có ngẫu nhiên hóa nội bộ khi dữ liệu đến trực tuyến, đồng thời biết lúc nào cấu trúc cân bằng tất định tốt hơn.

## 1. Tại sao thứ tự chèn có thể làm cây tìm kiếm mất cân bằng?

### 1.1. BST thường không tự cân bằng

BST với khóa không trùng tuân theo:

- Mọi khóa trong cây con trái của nút `u` đều **nhỏ hơn** `u.key`.
- Mọi khóa trong cây con phải đều **lớn hơn** `u.key`.
- Hai cây con cũng là BST.

Bất biến này đủ cho **tìm đúng**, nhưng **không bảo đảm chiều cao nhỏ**.

```text
Chèn 10, 20, 30, 40, 50 theo thứ tự này:

10
  \
   20
     \
      30
        \
         40
           \
            50

n = 5, h = 4 cạnh.
```

Một lần tìm kiếm phải đi qua nhiều nhất `h+1` nút. Nếu `n` khóa đều được chèn tăng dần vào BST không cân bằng, `h=n-1`, nên:

\[
T_{\text{find}}(n)=O(h+1)=O(n).
\]

Trong cây có chiều cao Θ(log n), tìm/chèn theo đường đi có thể cần O(log n) bước. **Vấn đề là hình dạng**, không phải bản thân phép so sánh khóa.

### 1.2. Xáo trộn đầu vào giúp được bao nhiêu?

Nếu có một **mảng khóa tĩnh** rồi được phép nạp một lần, ta có thể dùng xáo trộn Fisher–Yates để tạo một **hoán vị ngẫu nhiên đều**, sau đó chèn vào BST thường:

```python
import random

keys = [10, 20, 30, 40, 50]
rng = random.Random(2026)
rng.shuffle(keys)  # Chỉ thay đổi THỨ TỰ nạp khóa.

# Lần lượt insert(keys[i]) vào BST thường.
```

Đối với một tập `n` khóa phân biệt cố định và thứ tự chèn là hoán vị ngẫu nhiên đều, hình dạng BST nhận được có **cùng phân phối như random BST**, chiều sâu/chiều cao kỳ vọng đạt bậc logarit theo các kết quả chuẩn.

Nhưng cách này có ba giới hạn:

1. **Dữ liệu phải có thể gom và xáo trộn.** Với hệ thống nhận yêu cầu `insert` từng cái theo thời gian thực, thường không thể thay đổi thứ tự tác vụ mà bên gọi yêu cầu.
2. **Cập nhật về sau vẫn có thể bất lợi.** Sau đợt xây cây đầu, một dãy khóa lớn hơn tất cả khóa cũ có thể nối thành một nhánh dài nếu BST không tự cân bằng.
3. **Thứ tự đầu vào có thể mang ý nghĩa nghiệp vụ.** Không được tự ý hoán đổi thứ tự thực hiện giao dịch, ghi nhật ký hay thao tác có tác dụng phụ chỉ để cây có hình dạng đẹp.

Vì vậy, **xáo trộn dữ liệu trước khi nạp** không tương đương với **duy trì hình dạng ngẫu nhiên khi cấu trúc được cập nhật**.

### 1.3. Ngẫu nhiên hóa cấu trúc giải bài toán khác

```text
Phương án A: dữ liệu vào được xáo trộn

[10,20,30,40,50] --shuffle--> [30,10,50,20,40]
                                  |
                                  v
                            BST thường

Phương án B: dữ liệu/đơn hàng giữ nguyên

insert(10) -> insert(20) -> insert(30) -> insert(40) -> insert(50)
     |            |             |             |
     +---- cấu trúc tự bốc priority/level và tự tổ chức lại ----+
                                  |
                                  v
                           Treap / Skip list
```

Ở phương án B, **khóa không bị đổi** và yêu cầu vẫn được xử lý theo thứ tự đến. Phần ngẫu nhiên là **trạng thái nội bộ**: mức tháp của nút skip list, ưu tiên treap, lựa chọn pivot hay một phép tái cấu trúc được thiết kế có xác suất.

## 2. Mô hình xác suất: giữ đầu vào cố định, bốc ngẫu nhiên bên trong

Đây là nền tảng để đọc đúng các ký hiệu O(log n) **kỳ vọng**.

Gọi:

- `I` là một chuỗi yêu cầu **cố định** (ví dụ dãy khóa tăng dần).
- `R` là các lựa chọn ngẫu nhiên của cấu trúc (ví dụ priority của mỗi khóa).
- `T(I,R)` là chi phí chạy thuật toán với đầu vào `I` và kết quả random `R`.

Ta có thể xét:

\[
\mathbb{E}_{R}[T(I,R)].
\]

Kỳ vọng lấy trên **nguồn ngẫu nhiên nội bộ**, **không cần giả định dữ liệu người dùng có phân phối đẹp**. Khi phân tích một thao tác trên treap có `n` khóa phân biệt và các priority độc lập, ta thường nói chi phí trung bình **theo random priorities**, với tập khóa và dãy thao tác được xác định độc lập với các lần rút ngẫu nhiên.

### 2.1. Ba đại lượng không được trộn

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Worst-case** | Trường hợp tốn kém nhất trên mọi trạng thái hợp lệ là bao nhiêu? | Treap vẫn có thể có chiều cao O(n) |
| **Expected** | Trung bình theo các lựa chọn random đúng giả định là bao nhiêu? | Treap có chiều cao kỳ vọng O(log n) |
| **High probability** | Xác suất xảy ra thời gian lớn hơn một ngưỡng cụ thể là bao nhiêu? | Cần chứng minh tail bound, không suy ra chỉ từ kỳ vọng |

Nếu `\mathbb{E}[T]=O(\log n)` thì **không có nghĩa mỗi lần chạy đều O(log n)**. Muốn bảo đảm độ trễ cứng, cần cấu trúc có bảo đảm worst-case, hoặc cơ chế kiểm soát/tái cân bằng bổ sung.

### 2.2. Đầu vào cố định khác đối thủ thích nghi

Có hai mô hình khác nhau:

- **Oblivious input:** người tạo dãy thao tác không biết và không điều chỉnh dãy theo các kết quả ngẫu nhiên chưa được rút. Đây là mô hình quen thuộc khi chứng minh bound kỳ vọng của treap.
- **Adaptive adversary:** một tác nhân quan sát kết quả hoặc trạng thái rồi quyết định thao tác tiếp theo dựa trên những gì đã thấy.

Nếu nguồn random có thể đoán trước hoặc thứ tự/priorities bị lộ, đối thủ có thể cố tình chọn dãy thao tác gây trạng thái xấu. Không nên quảng bá rằng “dùng random nên chống được mọi tấn công” khi chưa mô tả **mô hình đối thủ** và cách bảo vệ nguồn ngẫu nhiên.

### 2.3. Ngẫu nhiên hóa ảnh hưởng chi phí, không được ảnh hưởng ngữ nghĩa tập khóa

Một cấu trúc set có random nội bộ vẫn phải bảo đảm:

- `insert(k)` thêm đúng khóa `k` hoặc báo đã tồn tại theo chính sách duplicate.
- `find(k)` trả đúng kết quả độc lập với random seed.
- `erase(k)` xóa đúng khóa `k`.
- Inorder của treap vẫn là thứ tự khóa tăng dần với khóa duy nhất.

Randomness được phép làm thay đổi **hình dạng và số bước**, chứ không được làm thay đổi **kết quả logic** của thao tác.

## 3. Treap: một cây đồng thời là BST và heap

**Treap** ghép **tree** và **heap**. Mỗi nút có hai thuộc tính khác nhau:

- `key`: khóa do bên gọi cung cấp, dùng làm BST.
- `priority`: độ ưu tiên do cấu trúc bốc ngẫu nhiên, dùng làm heap.

Ta chọn **min-heap theo priority**: mọi nút cha phải có priority **nhỏ hơn hoặc bằng** priority của các con. Dùng max-heap cũng được, miễn là định nghĩa nhất quán.

### 3.1. Hai bất biến trên cùng một cây

```text
                    key=40, p=10
                    /           \
              key=20,p=20      key=50,p=60
               /       \
         key=10,p=90  key=30,p=70

BST theo KEY:
  10 < 20 < 30 < 40 < 50

Min-heap theo PRIORITY:
  10 < 20, 60
  20 < 90, 70
```

Không yêu cầu priority của các nút **tăng theo key**. Key và priority là hai trục độc lập:

| Khóa | Priority minh họa |
| --- | --- |
| 10 | 90 |
| 20 | 20 |
| 30 | 70 |
| 40 | 10 |
| 50 | 60 |

Đây là hình dạng duy nhất của **treap Cartesian** nếu các priority là **phân biệt** và mọi key cũng phân biệt: nút priority nhỏ nhất là gốc; cây con trái/phải được xác định bởi các khóa nhỏ/lớn hơn nó, và đệ quy quy tắc đó.

### 3.2. Vì sao hình dạng không do thứ tự chèn quyết định?

Với một **tập cặp (key, priority) đã cố định** và các key/priority đều phân biệt, hai bất biến BST + heap quyết định **duy nhất** một treap. Chèn các cặp này theo thứ tự khác nhau, nếu thuật toán duy trì đúng hai bất biến, vẫn phải thu được cùng hình dạng cuối.

Tuy nhiên, trong ứng dụng bốc priority **khi một khóa được chèn**, nếu thay đổi **thứ tự chèn** thì có thể thay đổi **priority gắn với từng khóa**, ngay cả khi bắt đầu cùng một seed. Kết luận “thứ tự chèn không ảnh hưởng hình dạng” chỉ đúng khi **cặp (key, priority) đã được giữ cố định**, không phải khi seed được tái sử dụng với các chuỗi yêu cầu khác nhau.

### 3.3. Vì sao ưu tiên ngẫu nhiên dẫn tới cây có xu hướng cân bằng?

Giả sử `n` khóa phân biệt, và mỗi khóa nhận một priority **độc lập, cùng phân phối liên tục**, nên xác suất hai priority bằng nhau bằng 0. Khi ấy:

- Trong bất kỳ tập con các khóa nào, mỗi khóa có xác suất như nhau để có priority nhỏ nhất.
- Gốc của treap trên `n` khóa là **một khóa được chọn đều trong n khóa**, xét theo phân phối.
- Sau khi biết gốc, hai tập khóa trái/phải tiếp tục có thứ tự ưu tiên ngẫu nhiên tương đối.

Vì vậy treap có **cùng phân phối hình dạng với BST được xây từ hoán vị chèn đều ngẫu nhiên**. Kết quả quan trọng: độ sâu nút và chiều cao của treap có **kỳ vọng O(log n)**, dù **các khóa thực tế** là dãy tăng dần và không hề được xáo trộn.

Đây là bảo đảm **xác suất**, không phải một điều kiện cân bằng cứng như “chiều cao luôn ≤ c log n”.

## 4. Treap khác random BST qua xáo trộn đầu vào như thế nào?

| Tính chất | BST thường + shuffle một lần | Treap với priority random |
| --- | --- | --- |
| Có cần hoán vị chuỗi đầu vào trước khi nạp? | Có, nếu muốn tận dụng phân phối random insertion | **Không** |
| Bất biến chính | BST theo key | BST theo key + heap theo priority |
| Randomness nằm ở đâu? | Thứ tự các lần insert khi xây ban đầu | Thuộc tính nội bộ gắn với nút và phép tái cấu trúc |
| Thêm khóa trực tuyến | Dễ tạo nhánh bất lợi về sau | Vẫn duy trì hai bất biến bằng rotate/split/merge |
| Chiều cao trong mô hình random chuẩn | Expected O(log n) **sau đợt dựng bằng hoán vị ngẫu nhiên** | Expected O(log n) khi tập khóa có priority ngẫu nhiên thích hợp |
| Worst-case chiều cao | O(n) | O(n) |
| Hỗ trợ xóa | Cần thuật toán BST; không tự tái random hình dạng | Xóa được thiết kế bảo toàn heap/BST |
| Nhu cầu metadata trên mỗi nút | Thường chỉ key và liên kết | Thêm priority |

**Ví dụ dễ nhầm:** xáo trộn `[1..1000]` rồi xây BST thường, sau đó chèn tiếp `1001,1002,...,2000` theo thứ tự tăng dần. Nhánh bên phải có thể rất dài. Với treap, các khóa mới vẫn nhận priority random và có thể được quay lên đúng vị trí trong heap, thay vì chỉ nối thành đường phải không kiểm soát.

Không có cấu trúc nào miễn phí: treap phải lưu priority, duy trì invariant sau chèn/xóa, dùng RNG và chấp nhận độ trễ worst-case có thể tuyến tính.

## 5. Phép quay giữ thứ tự khóa nhưng thay hình dạng cây

Treap có thể dùng **rotation** để đưa nút có priority nhỏ lên trên mà không phá BST.

### 5.1. Quay phải

```text
Trước rotate_right(X):             Sau rotate_right(X):

            X                                Y
           / \                              / \
          Y   C                            A   X
         / \                                  / \
        A   B                                B   C

Các khóa phải thỏa: A < Y < B < X < C
(theo quan hệ toàn bộ cây con).
```

Nếu nút `Y` có priority nhỏ hơn `X` thì quay phải đưa `Y` lên trên `X`. Những liên kết của cây con `B` được chuyển thành `X.left`; không có nút nào bị copy.

```python
def rotate_right(root):
    child = root.left
    assert child is not None
    root.left = child.right
    child.right = root
    return child
```

### 5.2. Quay trái

```text
Trước rotate_left(X):              Sau rotate_left(X):

            X                                Y
           / \                              / \
          A   Y                            X   C
             / \                          / \
            B   C                        A   B

A < X < B < Y < C
```

```python
def rotate_left(root):
    child = root.right
    assert child is not None
    root.right = child.left
    child.left = root
    return child
```

**Phép quay không tạo/xóa node** và không đổi thứ tự inorder. Nó **có** thay các đường từ gốc tới nút, parent pointers nếu có và có thể làm iterator tự cài giữ đường tổ tiên cũ mất hợp lệ.

### 5.3. Chèn khóa mới và “nổi” theo priority

Một thuật toán treap đơn giản:

1. Tìm vị trí theo **key**, như BST thường; nếu trùng khóa thì áp dụng chính sách duplicate.
2. Tạo nút với **priority ngẫu nhiên** rồi gắn tại lá.
3. Trong khi priority của nó **nhỏ hơn** priority của cha, quay trái/phải để đưa nó lên.
4. Dừng khi ở gốc hoặc khi cha có priority ≤ priority của nút mới.

```text
Chèn key=30, p=10 vào:

       20,p=40
        \
        40,p=80

Sau khi gắn theo BST:
       20,p=40
        \
        40,p=80
        /
      30,p=10

Quay phải tại 40:
       20,p=40
        \
        30,p=10
          \
          40,p=80

Quay trái tại 20:
         30,p=10
        /       \
    20,p=40    40,p=80
```

Ở cuối thao tác, cả BST theo key và heap theo priority đều đúng. Các phép quay **chỉ sửa liên kết**, không tráo khóa vào vị trí sai.

## 6. Cài đặt treap Python hoàn chỉnh: tìm, chèn, xóa và xác minh

Ví dụ sử dụng **key nguyên duy nhất** và min-heap theo cặp `priority=(random_bits, insertion_serial)`. Số thứ tự thêm vào chỉ dùng để **phân xử va chạm priority** một cách tất định. Với các giá trị random 64-bit độc lập, va chạm hiếm cho kích thước thực tế vừa phải, nhưng không phải bất khả thi.

**Phân tích xác suất O(log n)** dùng mô hình priority độc lập **có thứ tự phân biệt ngẫu nhiên đều**; chương trình dùng PRNG 64-bit và tie-breaker là cách triển khai thực dụng gần mô hình ấy, không phải lời khẳng định độ ưu tiên hữu hạn tự động cho một chứng minh liên tục tuyệt đối.

### 6.1. Chương trình tự chạy

```python
from __future__ import annotations

import random
from dataclasses import dataclass
from collections.abc import Iterator


@dataclass(eq=False)
class TNode:
    key: int
    priority: tuple[int, int]
    left: TNode | None = None
    right: TNode | None = None


class Treap:
    """Set khóa int không trùng; min-heap theo priority."""

    def __init__(self, seed: int | None = None):
        self.root: TNode | None = None
        self.size = 0
        self._serial = 0
        self._rng = random.Random(seed)

    @staticmethod
    def _rotate_left(x: TNode) -> TNode:
        y = x.right
        assert y is not None
        x.right = y.left
        y.left = x
        return y

    @staticmethod
    def _rotate_right(x: TNode) -> TNode:
        y = x.left
        assert y is not None
        x.left = y.right
        y.right = x
        return y

    def contains(self, key: int) -> bool:
        node = self.root
        while node is not None:
            if key == node.key:
                return True
            node = node.left if key < node.key else node.right
        return False

    def insert(self, key: int) -> bool:
        """True nếu thêm khóa mới; False nếu khóa đã tồn tại."""
        path: list[TNode] = []
        node = self.root

        # Tìm trước để duplicate không tiêu thụ một lần bốc random.
        while node is not None:
            if key == node.key:
                return False
            path.append(node)
            node = node.left if key < node.key else node.right

        priority = (self._rng.getrandbits(64), self._serial)
        self._serial += 1
        fresh = TNode(key, priority)

        if not path:
            self.root = fresh
            self.size += 1
            return True

        parent = path[-1]
        if key < parent.key:
            parent.left = fresh
        else:
            parent.right = fresh

        # Đưa fresh lên bằng các phép quay đúng hướng.
        while path and fresh.priority < path[-1].priority:
            parent = path.pop()

            if parent.left is fresh:
                new_top = self._rotate_right(parent)
            else:
                new_top = self._rotate_left(parent)

            if path:
                grandparent = path[-1]
                if grandparent.left is parent:
                    grandparent.left = new_top
                else:
                    grandparent.right = new_top
            else:
                self.root = new_top

        self.size += 1
        return True

    def remove(self, key: int) -> bool:
        """True nếu xóa khóa đang tồn tại."""
        parent: TNode | None = None
        node = self.root

        while node is not None and node.key != key:
            parent = node
            node = node.left if key < node.key else node.right

        if node is None:
            return False

        # Hạ node xuống bằng quay cho đến khi nó có tối đa một con.
        # Trong thao tác đang thực hiện, heap có thể tạm bị đảo
        # tại node cần xóa; khi xóa xong, treap lại đúng bất biến.
        while node.left is not None and node.right is not None:
            if node.left.priority < node.right.priority:
                new_top = self._rotate_right(node)
            else:
                new_top = self._rotate_left(node)

            if parent is None:
                self.root = new_top
            elif parent.left is node:
                parent.left = new_top
            else:
                parent.right = new_top

            parent = new_top  # node mục tiêu giờ nằm ngay dưới new_top.

        replacement = node.left if node.left is not None else node.right

        if parent is None:
            self.root = replacement
        elif parent.left is node:
            parent.left = replacement
        else:
            parent.right = replacement

        node.left = node.right = None
        self.size -= 1
        return True

    def inorder_keys(self) -> Iterator[int]:
        stack: list[TNode] = []
        node = self.root

        while node is not None or stack:
            while node is not None:
                stack.append(node)
                node = node.left

            node = stack.pop()
            yield node.key
            node = node.right

    def height_edges(self) -> int:
        """-1 nếu rỗng, 0 nếu có một nút."""
        if self.root is None:
            return -1

        stack = [(self.root, 0)]
        height = 0

        while stack:
            node, depth = stack.pop()
            height = max(height, depth)

            if node.left is not None:
                stack.append((node.left, depth + 1))
            if node.right is not None:
                stack.append((node.right, depth + 1))

        return height

    def assert_valid(self) -> None:
        """Kiểm tra BST, min-heap, identity và số nút không đệ quy."""
        stack: list[tuple[TNode | None, int | None, int | None]] = [
            (self.root, None, None)
        ]
        seen: set[TNode] = set()

        while stack:
            node, low, high = stack.pop()
            if node is None:
                continue

            assert node not in seen, "Cycle hoặc shared node"
            seen.add(node)

            assert low is None or low < node.key
            assert high is None or node.key < high

            if node.left is not None:
                assert node.priority <= node.left.priority
                stack.append((node.left, low, node.key))

            if node.right is not None:
                assert node.priority <= node.right.priority
                stack.append((node.right, node.key, high))

        assert len(seen) == self.size


if __name__ == "__main__":
    tree = Treap(seed=2026)

    for key in range(1, 1001):  # Đầu vào tăng dần, KHÔNG shuffle.
        assert tree.insert(key)

    tree.assert_valid()
    assert list(tree.inorder_keys()) == list(range(1, 1001))

    assert tree.contains(777)
    assert not tree.insert(777)  # Duplicate: giữ kiểu set.

    assert tree.remove(777)
    assert not tree.contains(777)
    assert not tree.remove(777)

    tree.assert_valid()
    assert tree.size == 999
    assert list(tree.inorder_keys()) == [
        key for key in range(1, 1001) if key != 777
    ]

    print("size =", tree.size)
    print("height (edges) =", tree.height_edges())
```

Khi chạy, dãy inorder vẫn chứa các khóa tăng dần, **bất kể treap có hình dạng nào**. Giá trị chiều cao phụ thuộc vào các priority do nguồn ngẫu nhiên tạo; ví dụ chủ ý **không hardcode một chiều cao cụ thể**.

### 6.2. Vì sao phiên bản này không dùng đệ quy?

Các vòng tìm kiếm, chèn và xóa đi theo đường cây mà không dùng lời gọi lồng nhau. Chèn giữ `path` là stack các tổ tiên cần nối lại sau rotation; xóa dùng `parent` để nối lại gốc cây con sau mỗi rotation.

Điều đó tránh nguy cơ `RecursionError` chỉ do độ sâu của cây trong Python, nhưng **không** biến thời gian xấu nhất thành O(log n): nếu random tạo ra treap một đường, mỗi thao tác tìm/chèn/xóa vẫn có thể chạm **O(n)** nút.

### 6.3. Bất biến của thao tác chèn

Trước khi thêm, cây thỏa:

- **BST:** mọi key ở trái nhỏ hơn nút, mọi key bên phải lớn hơn.
- **Heap:** `priority(parent) <= priority(child)`.

Sau khi gắn khóa mới tại vị trí lá BST, **BST vẫn đúng**. Có thể chỉ vi phạm heap trên cạnh từ cha đến nút mới. Quay đúng hướng để đưa nút mới lên khi priority nhỏ hơn cha, đồng thời bảo toàn BST. Sau mỗi bước, đoạn đường tới nút mới được rút ngắn; khi dừng, heap toàn cây được khôi phục.

### 6.4. Bất biến của thao tác xóa

Xóa phải giữ **bộ khóa còn lại** và cuối cùng cả hai thứ tự. Khi nút mục tiêu có hai con, ta chọn con có **priority nhỏ hơn** để quay lên, hạ nút mục tiêu xuống một tầng. Lặp đến khi nút mục tiêu có tối đa một con, nối con còn lại vào vị trí ấy và loại nút mục tiêu.

Trong quá trình hạ, quan hệ heap **tại nút sắp bị xóa** có thể tạm không đúng; đó là trạng thái trung gian không được quan sát bởi luồng khác. Khi xóa xong, các nút còn lại tuân thủ heap/BST. Để hỗ trợ concurrent readers hoặc exception safety mạnh hơn, cần thiết kế đồng bộ/commit khác.

### 6.5. Chi phí bộ nhớ và thao tác

| Thao tác | Kỳ vọng theo priority thích hợp | Worst-case | Bộ nhớ phụ trợ |
| --- | --- | --- | --- |
| `contains(key)` | O(log n) | O(n) | O(1) |
| `insert(key)` | O(log n) | O(n) | O(h) stack đường tổ tiên |
| `remove(key)` | O(log n) | O(n) | O(1) ngoài các nút |
| `inorder_keys()` duyệt hết | O(n) | O(n) | O(h) stack |
| `height_edges()` | O(n) | O(n) | O(h) stack DFS |
| `assert_valid()` | O(n) kỳ vọng thao tác hash | Có thể phụ thuộc hash | O(n) bảng visited + O(h) stack |

Các chi phí chèn/xóa là theo độ dài đường và số rotation, trung bình kỳ vọng O(log n) khi priority phân phối đúng và chuỗi yêu cầu thuộc mô hình phân tích. Vùng lưu chính của treap là **O(n)** node, mỗi node có thêm priority và hai liên kết.

**Ghi chú triển khai:** `assert_valid` là công cụ kiểm thử/chẩn đoán và chủ động dùng O(n) metadata; không nên gọi sau **mọi** cập nhật trong đường chạy hiệu năng cao trừ khi cần xác minh hoặc dữ liệu đầu vào có rủi ro đặc biệt.


## 7. Phân tích treap bằng xác suất: vì sao độ sâu kỳ vọng là O(log n)?

Ta sẽ dùng một lập luận gọn cho **độ sâu kỳ vọng của một nút**, thay vì chỉ dựa vào biểu đồ kết quả thử nghiệm.

### 7.1. Mô hình chính xác

Giả sử các khóa đã được sắp `x_1 < x_2 < ... < x_n`. Tất cả khóa có priority độc lập, cùng phân phối **liên tục** và không phụ thuộc vào giá trị khóa. Chọn **min-heap** theo priority.

Với hai khóa `x_i` và `x_j` khác nhau, `x_j` là **tổ tiên** của `x_i` trong treap khi và chỉ khi `x_j` có priority **nhỏ nhất trên đoạn khóa** từ `x_{\min(i,j)}` đến `x_{\max(i,j)}`.

Ví dụ, nếu `i=3`, `j=7`, đoạn cần xét là `x_3, x_4, x_5, x_6, x_7`. Xác suất mỗi khóa có priority nhỏ nhất trên đoạn năm phần tử bằng `1/5`, bởi các priority được rút đối xứng và độc lập.

Do đó:

\[
\Pr[x_j \text{ là tổ tiên của } x_i]
  = \frac{1}{|i-j|+1},\quad j\ne i.
\]

Đây là sự kiện về **thứ tự priority**, không yêu cầu các khóa số học cách nhau đều.

### 7.2. Đếm số tổ tiên bằng biến chỉ báo

Đặt `D_i` là độ sâu (số cạnh từ gốc) của `x_i`. Độ sâu đúng bằng **số tổ tiên thực sự khác chính nó**.

Với mỗi `j\ne i`, đặt biến chỉ báo `I_{i,j}=1` nếu `x_j` là tổ tiên của `x_i`, và `0` nếu không. Khi ấy:

\[
D_i=\sum_{j\ne i}I_{i,j}.
\]

Dùng **tính tuyến tính của kỳ vọng**, dù các biến chỉ báo không nhất thiết độc lập:

\[
\begin{aligned}
\mathbb{E}[D_i]
&=\sum_{j<i}\frac{1}{i-j+1}
 +\sum_{j>i}\frac{1}{j-i+1}\\
&=(H_i-1)+(H_{n-i+1}-1)\\
&=H_i+H_{n-i+1}-2,
\end{aligned}
\]

trong đó `H_m=1+\frac12+\cdots+\frac1m` là **số điều hòa**.

Vì `H_m=O(\log m)`, suy ra:

\[
\mathbb{E}[D_i]=O(\log n).
\]

Điều này giải thích vì sao tìm một khóa có vị trí cố định trong tập sorted keys thường chỉ phải đi qua **số nút kỳ vọng logarit**.

### 7.3. Từ độ sâu nút đến chiều cao

**Cẩn thận:** chứng minh `\mathbb{E}[D_i]=O(\log n)` cho **từng nút** chưa đủ, nếu chỉ dùng bất đẳng thức thông thường, để tự kết luận `\mathbb{E}[\max_i D_i]=O(\log n)`. Chiều cao là **giá trị lớn nhất** trên nhiều biến ngẫu nhiên.

Với random BST/treap có priority độc lập, còn có **phân tích chặt hơn về độ dài các nhánh và xác suất đuôi**, cho kết quả chuẩn:

\[
\mathbb{E}[\text{height}]=O(\log n).
\]

Nói cách khác, câu “chiều cao kỳ vọng logarit” đúng trong mô hình này, nhưng **không phải** chỉ vì ta vừa tính xong độ sâu kỳ vọng của một nút. Khi trình bày chứng minh chính thức, cần lập luận bổ sung để khống chế nút sâu nhất.

### 7.4. Tại sao worst-case vẫn có thể O(n)?

Giả sử các priority của các khóa tăng dần theo key:

```text
key:        1    2    3    4    5
priority:   1    2    3    4    5

Min priority là key=1, đứng ở gốc.
Phần bên phải có min priority key=2, đứng dưới key=1.
Tiếp tục như thế:

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

Với `n` priority liên tục độc lập, xác suất **đúng một thứ tự tăng hoàn toàn** này bằng `1/n!`. Đây là một trường hợp rất hiếm khi `n` lớn, nhưng **không bị loại trừ**; còn những trường hợp xấu khác có thể xảy ra.

Kết luận: treap cho **phân phối hình dạng có lợi**, không áp đặt một giới hạn chiều cao tất định.

### 7.5. Xác suất không thay thế kiểm tra bất biến

Trong `Treap.assert_valid()`, ta kiểm tra hai invariant **trên trạng thái thực tế của một lượt chạy**. Hàm này có thể xác nhận:

- Cây có đúng các quan hệ khóa BST.
- Thứ tự priority cha–con đúng.
- Không có chu trình hoặc chia sẻ nút sai.
- `size` khớp số nút thực.

Nhưng một treap **rất cao** vẫn có thể **hoàn toàn hợp lệ** theo BST+heap. Validator không được báo sai chỉ vì chiều cao O(n); chiều cao là thuộc tính hiệu năng, không phải vi phạm bất biến của treap.

## 8. Skip list: ngẫu nhiên hóa chiều cao các “tháp” thay vì xáo trộn khóa

Treap ngẫu nhiên hóa **vị trí gốc và các cây con** thông qua priority. **Skip list** lại lưu một dãy khóa có thứ tự với nhiều **tầng liên kết chuyển tiếp**. Mỗi nút được chọn **độ cao ngẫu nhiên**, từ đó quyết định có mặt ở những tầng nào.

### 8.1. Hình dung skip list

```text
Level 4:  HEAD ---------------------------> 40
Level 3:  HEAD -------------> 20 ----------> 40
Level 2:  HEAD ---> 10 -----> 20 -----> 30 -> 40
Level 1:  HEAD ---> 10 -> 15 -> 20 -> 25 -> 30 -> 40

Các khóa ở mỗi tầng đều tăng dần.
Nút ở tầng cao cũng xuất hiện ở các tầng thấp hơn.
```

Trong skip list chuẩn, **tầng đáy** chứa mọi khóa. Các tầng cao chỉ chứa một số nút được “nâng cấp” ngẫu nhiên, giúp tìm kiếm bỏ qua nhiều phần tử.

Khi tìm `25`:

1. Bắt đầu tại `HEAD` trên tầng cao nhất.
2. Tiến sang phải khi khóa kế tiếp vẫn **nhỏ hơn 25**.
3. Khi không thể tiến nữa mà không vượt 25, xuống một tầng.
4. Lặp đến tầng đáy rồi kiểm tra khóa kế tiếp.

Không cần xáo trộn thứ tự các khóa: tầng đáy luôn duy trì sorted order.

### 8.2. Bốc mức theo các lần tung đồng xu

Chọn `p=1/2` là xác suất một nút được nâng thêm một tầng:

```text
random_level():
    level = 1
    while coin_flip_is_heads_with_probability_p():
        level += 1
    return level
```

Với biến độ cao `L≥1`:

\[
\Pr[L\ge k]=p^{k-1},
\quad
\Pr[L=k]=(1-p)p^{k-1}.
\]

Từ công thức kỳ vọng theo xác suất đuôi:

\[
\mathbb{E}[L]
 = \sum_{k=1}^{\infty}\Pr[L\ge k]
 = \sum_{k=1}^{\infty}p^{k-1}
 = \frac{1}{1-p}.
\]

Khi `p=1/2`, trung bình mỗi node có **2 liên kết forward** (không tính metadata riêng). Đó là lý do skip list có **O(n) dung lượng liên kết kỳ vọng** dù dùng nhiều tầng.

### 8.3. Tầng tối đa cũng là biến ngẫu nhiên

Với `n` nút, theo bất đẳng thức union bound:

\[
\Pr[\max_i L_i\ge k]\le n\,p^{k-1}.
\]

Đặt `k` cỡ `1+\log_{1/p}n`, xác suất xuất hiện những tầng cao hơn giảm nhanh. Độ cao lớn nhất của skip list là **O(log n) kỳ vọng** khi các lần bốc mức độc lập.

Kết quả chuẩn với `p` cố định, `0<p<1` và mô hình random đúng là **tìm/chèn/xóa O(log n) thời gian kỳ vọng**, **O(n) tổng bộ nhớ kỳ vọng**. Worst-case tìm kiếm vẫn có thể O(n), ví dụ mọi nút chỉ có tầng đáy.

**Cài đặt thực tế:** có thể giới hạn `MAX_LEVEL` để khống chế kích thước con trỏ mỗi nút, nhưng nếu giữ một giới hạn cố định rồi để `n` tăng mãi không giới hạn, tầng đáy dần quá dài và không thể tuyên bố O(log n) cho mọi `n` tiệm cận. Chọn giới hạn theo quy mô dự kiến hoặc điều chỉnh động.

## 9. Python: một skip list đơn giản có bốc tầng nội bộ

Phiên bản minh họa dưới đây chỉ nhận **khóa `int` duy nhất**, giữ các tầng forward là danh sách liên kết và có `insert`, `contains`, `discard`. Chúng ta **không bao giờ shuffle khóa đầu vào**.

### 9.1. Cài đặt hoàn chỉnh

```python
from __future__ import annotations

import random
from dataclasses import dataclass
from collections.abc import Iterator


@dataclass(eq=False)
class SNode:
    key: int | None
    forward: list[SNode | None]


class SkipList:
    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)
        self.head = SNode(None, [None])  # Sentinel.
        self.height = 1
        self.size = 0

    def _random_level(self) -> int:
        level = 1
        while self._rng.random() < 0.5:
            level += 1
        return level

    def _predecessors(self, key: int) -> list[SNode]:
        """update[level] là node đứng ngay trước key ở tầng đó."""
        update = [self.head] * self.height
        current = self.head

        for level in range(self.height - 1, -1, -1):
            while (
                current.forward[level] is not None
                and current.forward[level].key < key
            ):
                current = current.forward[level]

            update[level] = current

        return update

    def contains(self, key: int) -> bool:
        update = self._predecessors(key)
        candidate = update[0].forward[0]
        return candidate is not None and candidate.key == key

    def insert(self, key: int) -> bool:
        update = self._predecessors(key)
        candidate = update[0].forward[0]

        if candidate is not None and candidate.key == key:
            return False

        new_height = self._random_level()

        if new_height > self.height:
            extra = new_height - self.height
            self.head.forward.extend([None] * extra)
            update.extend([self.head] * extra)
            self.height = new_height

        fresh = SNode(key, [None] * new_height)

        for level in range(new_height):
            fresh.forward[level] = update[level].forward[level]
            update[level].forward[level] = fresh

        self.size += 1
        return True

    def discard(self, key: int) -> bool:
        update = self._predecessors(key)
        target = update[0].forward[0]

        if target is None or target.key != key:
            return False

        for level in range(len(target.forward)):
            assert update[level].forward[level] is target
            update[level].forward[level] = target.forward[level]

        while self.height > 1 and self.head.forward[-1] is None:
            self.head.forward.pop()
            self.height -= 1

        self.size -= 1
        return True

    def keys(self) -> Iterator[int]:
        node = self.head.forward[0]
        while node is not None:
            # Tất cả node dữ liệu có key int.
            yield node.key
            node = node.forward[0]

    def assert_valid(self) -> None:
        seen = set()
        node = self.head.forward[0]
        previous = None

        while node is not None:
            assert node not in seen, "Cycle tai level 0"
            seen.add(node)
            assert previous is None or previous < node.key
            previous = node.key
            node = node.forward[0]

        assert len(seen) == self.size

        assert len(self.head.forward) == self.height
        level_below = seen  # Tập nút tại tầng thấp hơn.

        for level in range(self.height):
            node = self.head.forward[level]
            last_key = None
            at_level: set[SNode] = set()

            while node is not None:
                assert node not in at_level, "Cycle tai level cao"
                assert node in level_below
                assert len(node.forward) > level
                assert last_key is None or last_key < node.key
                at_level.add(node)
                last_key = node.key
                node = node.forward[level]

            level_below = at_level


if __name__ == "__main__":
    sl = SkipList(seed=2026)

    for key in range(1, 1001):  # Vẫn chèn tăng dần.
        assert sl.insert(key)

    sl.assert_valid()
    assert list(sl.keys()) == list(range(1, 1001))

    assert sl.contains(400)
    assert not sl.insert(400)
    assert sl.discard(400)
    assert not sl.contains(400)
    assert not sl.discard(400)

    sl.assert_valid()
    assert sl.size == 999
    print("height =", sl.height)
```

### 9.2. Bất biến của skip list

- **Tầng 0** chứa mọi khóa đúng một lần, tăng dần.
- Với `level>0`, chuỗi ở tầng đó cũng tăng dần; chỉ chứa các nút có `len(forward)>level`.
- Một nút xuất hiện ở tầng trên phải **cũng** có mặt tại mọi tầng thấp hơn tới tầng 0.
- `head` là sentinel, **không** phải một khóa `int` được người dùng lưu.
- `size` đếm số khóa thật ở tầng đáy, không phải tổng số liên kết qua tất cả tầng.
- Chèn/xóa ở tầng cao phải cập nhật liên kết **cùng một node**, không tạo nhiều bản sao payload cho mỗi mức.

Dù `assert_valid` xác nhận sorted order từng tầng, bản cài đặt kiểm thử này không đi kiểm tra sâu mọi khía cạnh xác suất. Những liên kết tầng cao vẫn có thể dài bất thường mà không vi phạm invariant: đó là một trường hợp hiệu năng kém, không phải cấu trúc sai.

### 9.3. Tại sao code dùng predecessor array `update`?

Một lần tìm từ tầng cao xuống thấp giữ các vị trí **đứng trước khóa** trên từng tầng. Khi chèn node mới có độ cao `L`, chỉ cần nối vào **L chuỗi liên kết** tại những vị trí đã tìm.

```text
Ở tầng i:
    predecessor ---> successor

Sau chèn:
    predecessor ---> fresh ---> successor
```

Xóa làm ngược lại: ở mỗi tầng mà node có mặt, nối `predecessor.forward[i]` thẳng tới `target.forward[i]`. Không được xem `target` là `L` object khác nhau chỉ vì nó hiện diện ở L tầng.

### 9.4. Độ phức tạp và lưu ý tài nguyên

Với xác suất nâng tầng cố định `p=1/2` và các lần bốc độc lập:

- `contains/insert/discard`: **O(log n) kỳ vọng**. Nếu `H` là số tầng thực tế thì worst-case của quá trình tìm có thể tới **O(n+H)**; không thể chặn bởi riêng `n` khi cho phép bốc `H` không giới hạn. Với giới hạn tầng thực tế `H=O(n)`, worst-case trở thành O(n).
- Tất cả node ở tầng đáy dùng **O(n)**; tổng số con trỏ forward **O(n) kỳ vọng**.
- `update` dùng O(H) bộ nhớ, với `H` là độ cao skip list đang có; `H` có kỳ vọng O(log n). Hàm `_random_level` có số lần tung đồng xu kỳ vọng O(1), nhưng không có chặn worst-case hữu hạn nếu không đặt trần mức.
- `keys()` duyệt tầng đáy: O(n) thời gian, O(1) trạng thái riêng.
- `assert_valid()`: O(n+S) thời gian theo số node `n` và số liên kết tổng `S`, thêm O(n) bộ nhớ set; trong mô hình random kỳ vọng S=O(n).

Ví dụ không đặt mức trần để biểu diễn đúng cơ chế geometric trong lý thuyết. Một hệ thống cần hạn mức bộ nhớ cứng có thể đặt `MAX_LEVEL`, kiểm tra lỗi cấp phát và công bố phạm vi `n` được thiết kế.

## 10. Treap và skip list: hai hình dạng khác nhau, một ý tưởng xác suất

| Khía cạnh | Treap | Skip list |
| --- | --- | --- |
| Hình dạng ngẫu nhiên | Cây theo thứ tự priority | Tháp nhiều tầng theo số lần tung đồng xu |
| Thứ tự dữ liệu | BST theo key | Các linked list sorted theo key |
| Thông tin random mỗi khóa | `priority` | `level`/height |
| Trạng thái cơ bản | `left`/`right` | Mảng `forward[0..level-1]` |
| Tìm kiếm | Đi từ gốc theo so sánh key | Đi ngang rồi xuống tầng |
| Thêm | BST insert + rotation hoặc split/merge | Tìm predecessor ở mỗi tầng rồi nối |
| Xóa | Rotation xuống, merge hoặc biến thể khác | Bỏ liên kết node ở các tầng xuất hiện |
| Kỳ vọng tìm/chèn/xóa | O(log n) | O(log n) |
| Worst-case độ dài đường tìm | O(n) | O(n+H) nếu số tầng H không giới hạn; O(n) khi H bị chặn bởi O(n) |
| Bộ nhớ chính | O(n) node + priority | O(n) con trỏ kỳ vọng, thêm node |
| Phụ thuộc thứ tự đầu vào cố định? | Phân phối hình dạng do priority quyết định | Phân phối tầng do coin flip quyết định |
| Phù hợp thao tác theo cây con | Có thể hỗ trợ split/merge, order statistics | Cần metadata/thiết kế riêng |
| Phù hợp duyệt sorted keys | Inorder | Đi tầng đáy |

Cả hai không phải tự cân bằng bằng **ràng buộc chiều cao cứng** như AVL hay red-black tree. Chúng khuyến khích hình dạng có đường ngắn **bằng ngẫu nhiên hóa nội bộ**. Các khía cạnh như cache locality, số lần cấp phát, lượng metadata, quản lý vòng đời và độ phức tạp hiện thực có thể khiến một cấu trúc nhanh hơn cấu trúc kia trong workload thực tế.

## 11. Tại sao “dùng hash random” không tự giải quyết mọi bài toán?

Trong bảng băm, ta có thể chọn **hàm băm có seed** hoặc randomization để giảm việc tập khóa cố định đẩy nhiều phần tử vào cùng bucket. Đây cũng là một dạng ngẫu nhiên hóa **bố cục lưu trữ** dựa trên khóa.

Tuy nhiên, cần phân biệt:

- **Randomized hashing**: làm thay đổi vị trí bucket/collision pattern.
- **Treap**: làm thay đổi hình dạng BST dựa vào priority.
- **Skip list**: làm thay đổi độ cao node và các đường nhảy.
- **Shuffle input**: làm thay đổi thứ tự công việc **trước khi** nạp.

Một cấu trúc dùng RNG không đồng nghĩa nó đã có bound O(log n). Ví dụ một BST thường có trường `random_tag` nhưng **không dùng tag để quyết định rotation/hình dạng** thì vẫn bị thoái hóa với dãy khóa tăng. Randomness phải tham gia vào **quy tắc tổ chức và duy trì invariant**.

### 11.1. Randomized quicksort không phải random treap

Randomized quicksort chọn **pivot ngẫu nhiên** để phân chia mảng. Nó có expected O(n log n) thời gian cho một lượt sắp xếp và worst-case O(n²). Nó minh họa cùng triết lý **để lựa chọn ngẫu nhiên nội bộ quyết định cây phân chia**.

Tuy nhiên, quicksort thông thường là thuật toán sắp xếp, **không giữ một cấu trúc tìm kiếm động** sau khi hoàn tất. Treap là cấu trúc lưu trạng thái qua nhiều thao tác `insert/find/delete`, còn skip list là cấu trúc linked-level. Không nên đánh đồng chúng chỉ vì đều có phân phối xác suất.

### 11.2. “Random input” khác “randomized data structure”

Một phân tích **trung bình trên phân phối đầu vào** giả sử người dùng gửi khóa theo một phân phối được chọn. Nếu thực tế dữ liệu đến theo thứ tự tăng dần, giả định ấy có thể sai ngay lập tức.

Một phân tích **kỳ vọng theo nguồn random của cấu trúc**, với tập khóa cố định và giả định độc lập thích hợp, có thể giữ giá trị ngay cả khi dữ liệu không có vẻ ngẫu nhiên.

Đó chính là thay đổi tư duy quan trọng của chương: **đưa randomness vào chính cấu trúc thay vì đòi dữ liệu phải ngẫu nhiên**.


## 12. Seed, PRNG, va chạm và yêu cầu bảo mật

Ngẫu nhiên hóa cấu trúc chỉ có tác dụng khi nguồn priority/level đáp ứng **những giả định xác suất mà ta dùng khi phân tích**. Không nên coi mọi đoạn mã gọi `random()` là có cùng độ tin cậy.

### 12.1. PRNG tạo chuỗi có thể tái lập

**PRNG** (*Pseudo-Random Number Generator*) là bộ sinh số giả ngẫu nhiên từ một trạng thái nội bộ. Với cùng thuật toán, cùng seed và cùng thứ tự yêu cầu bốc số, nó tạo ra cùng chuỗi kết quả.

```python
import random

a = random.Random(1234)
b = random.Random(1234)

sample_a = [a.getrandbits(16) for _ in range(5)]
sample_b = [b.getrandbits(16) for _ in range(5)]

assert sample_a == sample_b
```

Tính tái lập có ích:

- Viết test có kết quả ổn định.
- Lưu một seed để tái tạo lỗi hiếm.
- So sánh hai phiên bản thuật toán trên cùng kịch bản.
- Tách logic thao tác khỏi nguồn random có thể thay thế.

Trong code treap và skip list, mỗi instance sở hữu `self._rng` riêng, thay vì sử dụng một biến trạng thái global khó kiểm soát. Điều này giúp giảm ảnh hưởng ngẫu nhiên ngoài ý muốn giữa các đối tượng/test.

### 12.2. Seed cố định không phải bảo đảm chống đầu vào đối kháng

`random.Random` của Python dùng một PRNG phổ thông để mô phỏng/nghiên cứu; **không thích hợp để tạo bí mật bảo mật**. Với dữ liệu có tác nhân cố ý tìm cách làm chậm hệ thống, seed cố định và quy tắc priority dự đoán được có thể khiến phân phối ngẫu nhiên **không còn độc lập với hành vi đối thủ**.

Trong môi trường có yêu cầu kháng tấn công gây cạn tài nguyên (*algorithmic complexity attack*), cần:

- Xác định chính xác **mô hình đối thủ**: có quan sát được hình dạng, độ trễ hay kết quả RNG không?
- Chọn nguồn random phù hợp và giữ bí mật cần thiết, chẳng hạn RNG an toàn mật mã khi chính sách bảo mật yêu cầu.
- Xem xét liệu một chuỗi thao tác **thích nghi với quan sát trước đó** còn thỏa các giả định chứng minh expected O(log n) không.
- Giới hạn tài nguyên, có cơ chế fallback hoặc chọn cấu trúc cân bằng **worst-case tất định** nếu độ trễ cứng quan trọng.

Không có một câu “dùng seed ngẫu nhiên” đủ để chứng minh an toàn trước mọi đối thủ.

### 12.3. Priority hữu hạn có thể va chạm

Trong mô hình lý thuyết, rút priority từ một phân phối liên tục làm xác suất va chạm bằng 0. Trong chương trình, priority là số **hữu hạn bit**. Với `n` lần rút 64 bit đều và độc lập, union bound cho xác suất có ít nhất một cặp trùng là:

\[
\Pr[\text{có va chạm}]
  \le \frac{n(n-1)}{2^{65}}.
\]

Đây là **chặn trên**, không phải xác suất đúng tuyệt đối. Khi `n` lớn hoặc chạy lâu và sử dụng không gian priority hữu hạn, phải có quy tắc xử lý tie.

Trong code `Treap` ở Mục 6, priority là cặp `(random_bits, insertion_serial)` nên có thứ tự toàn phần, không có hai cặp trùng nhau trong phạm vi serial không bị tái sử dụng. Tuy nhiên, khi các thành phần random trùng nhau, serial tạo ra một **thiên lệch theo thứ tự chèn** đối với cặp bị trùng; do đó phân phối hình dạng không còn **chính xác** là mô hình random continuous. Với không gian 64 bit và quy mô thường gặp, độ lệch này thường nhỏ, nhưng phải phân biệt mô hình toán với hiện thực hữu hạn.

Một lựa chọn khác là rút lại khi trùng priority và lưu một tập priority đã dùng. Cách này loại tie trong miền hữu hạn đang sử dụng nhưng cần thêm metadata và có giới hạn khi không gian ưu tiên cạn; phân tích xác suất cần xét mô hình rút không hoàn lại.

### 12.4. Không dùng giá trị khóa làm nguồn ưu tiên ngụy ngẫu nhiên

Một lựa chọn thiếu cân nhắc là đặt:

```python
priority = key
```

Nếu dùng `priority=key` và min-heap, treap trên tập khóa tăng trở thành đường phải. Không có randomness nào thực sự độc lập với key. Tương tự, `priority=key % 10` tạo nhiều va chạm có quy luật và không cho bảo đảm như rút độc lập.

Có thể tính priority bằng **hàm băm có seed/key bí mật** của khóa trong một số thiết kế, nhưng cần phân tích **phân phối**, collision, việc thay đổi seed và mô hình đối thủ; không tự cho rằng một hàm hash bất kỳ tương đương các priority độc lập đều ngẫu nhiên.

### 12.5. Nguồn random có thể ảnh hưởng API quan sát được

Nếu một cấu trúc hỗ trợ duyệt theo sorted key, **dãy khóa trả ra không phụ thuộc seed**. Nhưng những thuộc tính **nội bộ** như:

- Chiều cao treap.
- Số lần rotation.
- Số tầng skip list.
- Số node visited khi tìm một khóa.
- Đường từ gốc đến khóa.

có thể thay đổi theo seed hoặc theo thứ tự bốc random. Không nên đưa các chi tiết nội bộ ấy thành **hợp đồng nghiệp vụ ổn định** nếu chương trình còn quyền thay nguồn RNG/phiên bản thuật toán.

## 13. Chèn, xóa và trạng thái random sau nhiều lần cập nhật

Ngẫu nhiên hóa hình dạng có giá trị nhất khi **cấu trúc không chỉ được xây một lần** mà liên tục nhận thao tác.

### 13.1. Cập nhật treap không cần shuffle lại toàn bộ khóa

Với treap, một khóa mới nhận priority mới, được chèn theo BST và quay để khôi phục heap. Không cần gom lại toàn bộ keys rồi shuffle và xây lại từ đầu.

Nếu cùng một set khóa đã có một tập priority ngẫu nhiên đúng mô hình, treap duy trì phân phối của **Cartesian tree** tương ứng với tập cặp (key, priority). Sau khi xóa một khóa, priority của các khóa còn lại vẫn được giữ nguyên và các phép rotation/merge có thể duy trì hai bất biến.

**Điểm tinh tế:** nếu chính sách hệ thống xóa rồi chèn lại **cùng một khóa**, việc rút priority mới có thể tạo hình dạng khác. Quy tắc này phải rõ nếu các thao tác khác lưu con trỏ, cursor hay metadata gắn với nút.

### 13.2. Skip list chỉ bốc level cho node mới

Khi insert một khóa vào skip list:

- Bốc level một lần cho **node mới**.
- Nối node vào đúng các tầng từ 0 đến `level-1`.
- Không cần bốc lại level của mọi node cũ.

Khi xóa, bỏ node ở những tầng mà nó tham gia. Đó là lý do ngẫu nhiên hóa **hình dạng nội bộ ngay khi một node được tạo** giúp cập nhật trực tuyến mà không cần xáo trộn các thao tác bên ngoài.

### 13.3. Cập nhật có thể vô hiệu hóa iterator

Một iterator treap tự cài thường giữ stack các tổ tiên hoặc con trỏ nút. Phép quay có thể thay đường tổ tiên; xóa có thể hủy một nút mà iterator đang trỏ tới. Ngay cả khi inorder của tập khóa còn đúng, **iterator cũ không mặc nhiên hợp lệ**.

Skip list thay các con trỏ `forward` trong lúc chèn/xóa, cũng cần định nghĩa rõ liệu một cursor đang giữ node có thể tiếp tục hay không.

Các chiến lược:

1. Không cho sửa cấu trúc trong khi duyệt, hoặc dùng khóa đồng bộ.
2. Gắn số phiên bản và từ chối tiếp tục nếu có cập nhật không tương thích.
3. Tạo snapshot/persistent structure với vòng đời phù hợp.
4. Sử dụng một iterator được thư viện định nghĩa **cụ thể** là an toàn cho thao tác đang xét.

Ngẫu nhiên hóa cấu trúc **không** tự giải quyết ownership, data race, iterator invalidation hay memory reclamation.

### 13.4. Dữ liệu đi kèm phải tuân thủ hợp đồng key

Nếu dùng treap map lưu `(key,value)`:

- `key` quyết định nhánh trái/phải; không sửa key tùy tiện sau khi chèn.
- `priority` quyết định heap; không sửa priority mà bỏ qua khôi phục cấu trúc.
- `value` là payload; có thể sửa theo hợp đồng map nếu không làm đổi key/priority.
- Với khóa trùng, chọn chính sách: bỏ qua, cập nhật value, đếm multiplicity hoặc dùng khóa kết hợp ID duy nhất.

Code Mục 6 chọn **set không trùng key**. Các công thức expected search dựa vào `n` khóa phân biệt; nếu cần multiset phải thiết kế rõ cách một giá trị lặp được thể hiện và tính độ phức tạp.

## 14. Expected, amortized và worst-case: ba kiểu hứa hẹn khác nhau

Có ba cách lập luận thường xuất hiện trong tài liệu cấu trúc dữ liệu:

### 14.1. Worst-case cho mỗi thao tác

Một cây AVL hoặc red-black tree được duy trì đúng bất biến có thể bảo đảm chiều cao O(log n) ở **mọi trạng thái hợp lệ**, do đó tìm/chèn/xóa có giới hạn worst-case O(log n) theo thuật toán chuẩn.

Đây là bảo đảm **tất định**, không cần nguồn random của cấu trúc.

### 14.2. Expected đối với ngẫu nhiên nội bộ

Treap và skip list với mô hình random thích hợp thường có O(log n) **kỳ vọng**. Một trạng thái bất lợi có thể khiến một thao tác mất O(n), nhưng trạng thái ấy hiếm theo phân phối ngẫu nhiên được giả định.

Kỳ vọng này **khác** việc đo thời gian trên một tập dữ liệu trông ngẫu nhiên. Kỳ vọng là khái niệm toán học về **nhiều khả năng rút random** đối với đầu vào cố định.

### 14.3. Amortized trên một chuỗi thao tác

Một mảng động có thể có `push_back` worst-case O(n) khi reallocate, nhưng **chi phí khấu hao O(1)** cho một chuỗi dài chèn liên tục nếu capacity tăng theo hệ số thích hợp.

**Amortized** không bắt buộc có randomness; nó phân bổ chi phí các bước đắt qua nhiều thao tác trong một chuỗi.

| Loại bảo đảm | Nguồn trung bình | Một lần thao tác rất chậm có thể xảy ra? |
| --- | --- | --- |
| Worst-case O(log n) | Không trung bình, chặn mọi trường hợp | Không vượt bậc đã bảo đảm theo mô hình |
| Expected O(log n) | Trung bình trên lựa chọn random | Có |
| Amortized O(1) | Phân bổ chi phí trên chuỗi thao tác | Có |

**Không thay thế lẫn nhau**: expected O(log n) không có nghĩa amortized worst-case O(log n), và amortized O(1) không phải bảo đảm thời gian mọi thao tác O(1).

### 14.4. Thời gian thực và các tình huống nhạy cảm độ trễ

Nếu một yêu cầu phải hoàn tất trước deadline cứng, chỉ biết expected O(log n) có thể chưa đủ. Có thể:

- Chọn cây cân bằng tất định.
- Giới hạn kích thước tập dữ liệu.
- Thiết kế fallback khi chiều cao đo được vượt ngưỡng.
- Chia công việc thành các giai đoạn có thể tiếp tục.
- Đo cả phân vị cao của số bước, không chỉ thời gian trung bình.

Khi thêm fallback, phải phân tích cả **chi phí kích hoạt fallback**, điều kiện phát hiện và vòng đời các iterator/nút đang hoạt động. Không được tự nói fallback “giữ O(log n)” nếu không có chứng minh phù hợp.

## 15. Bộ nhớ và hiệu năng thực tế

Big-O giúp so sánh khi n tăng, nhưng ở quy mô thật, chi phí cũng đến từ metadata, cấp phát và cache.

### 15.1. Treap và locality

Một node treap thường chứa `key`, `priority`, `left` và `right`, có thể thêm `value`, `size`, `parent`... Các node cấp phát rời rạc có thể gây cache miss khi duyệt đường cây.

Cấu trúc cây được nén trong mảng, B-tree/B+ tree hoặc mảng sorted có thể tận dụng tính cục bộ tốt hơn khi workload chủ yếu là đọc, dù cập nhật có thể khác về chi phí.

### 15.2. Skip list và forward pointers

Tổng chiều cao node skip list có kỳ vọng O(n) đối với `p` cố định, nhưng:

- Một node có thể chứa một mảng forward với nhiều phần tử.
- Mỗi lần tìm có thể nhảy giữa các object phân tán trong bộ nhớ.
- Metadata head và cấp phát node cũng tốn bộ nhớ.
- Đặt `p` thấp hơn có thể giảm trung bình số liên kết nhưng làm đường tìm ngang dài hơn.

Chọn `p` là một **đánh đổi tốc độ–bộ nhớ**, không chỉ “0.5 là luôn tối ưu”.

### 15.3. Đối chiếu độ rộng tính năng

| Tình huống | Lựa chọn đáng xem xét | Điểm phải kiểm tra |
| --- | --- | --- |
| Lưu tập khóa online, cần find/insert/delete | Treap, skip list, AVL/red-black tree | Expected/worst latency, metadata |
| Dữ liệu chủ yếu xây một lần rồi tra cứu | Mảng sorted, BST cân bằng từ mảng, B-tree | Có cần update nhiều không? |
| Cần tách/ghép dải khóa | Treap split/merge, cây cân bằng có API tương ứng | Bất biến key-range và ownership |
| Cần duyệt sorted keys thường xuyên | Inorder treap, tầng đáy skip list | Cache locality và iterator validity |
| Cần latency cứng | Cây cân bằng tất định hoặc cấu trúc có bound được chứng minh | Không chỉ dựa vào expected |
| Rất nhiều khóa cạnh tranh trong hệ thống phân tán | Cấu trúc concurrent/persistent chuyên biệt | Đồng bộ, reclamation, partitioning |
| Đầu vào có đối thủ chủ động | Cấu trúc worst-case hoặc randomization phù hợp mô hình an toàn | PRNG, leak, adaptive attacker |

**Đừng chọn chỉ vì cấu trúc có tên “randomized”.** Mục tiêu là cân bằng giữa tính đúng đắn, độ phức tạp, bộ nhớ, latency, cập nhật và độ khó bảo trì.

## 16. Kiểm thử cấu trúc ngẫu nhiên đúng cách

Kiểm thử một cấu trúc randomized phải kiểm tra **hai lớp**:

1. **Lớp tất định:** với bất kỳ seed nào, nội dung set/map và mọi bất biến BST/heap/skip-list phải đúng.
2. **Lớp xác suất/hiệu năng:** qua nhiều seed và nhiều kích cỡ, phân phối chiều cao, số bước hoặc số pointer có phù hợp với kỳ vọng không?

Không được thay lớp thứ nhất bằng lớp thứ hai. Một chương trình có chiều cao trung bình đẹp nhưng đôi khi mất khóa vẫn là **sai thuật toán**.

### 16.1. Test treap với các thứ tự vào khác nhau

Đoạn sau giả định lớp `Treap` ở Mục 6 đã được định nghĩa.

```python
def test_treap(seed: int, keys: list[int]) -> None:
    tree = Treap(seed=seed)
    expected: set[int] = set()

    for key in keys:
        inserted = tree.insert(key)
        assert inserted == (key not in expected)
        expected.add(key)

        # Chỉ bật khi kiểm thử, vì mỗi lần kiểm tra có thể O(n).
        tree.assert_valid()
        assert list(tree.inorder_keys()) == sorted(expected)

    for key in keys[::3]:
        existed = key in expected
        assert tree.remove(key) == existed
        expected.discard(key)
        tree.assert_valid()

    assert list(tree.inorder_keys()) == sorted(expected)


for seed in range(8):
    ordered = list(range(40))
    test_treap(seed, ordered)
    test_treap(seed, list(reversed(ordered)))

    rng = random.Random(seed)
    shuffled = ordered.copy()
    rng.shuffle(shuffled)
    test_treap(seed, shuffled)
```

Test trên dùng nhiều seed **và** các kiểu thứ tự input. Việc shuffle trong test chỉ giúp tạo một trường hợp thử khác; bản thân treap **không yêu cầu shuffle** trước khi nhận dữ liệu.

### 16.2. Test skip list với mô hình tham chiếu

```python
def test_skip_list(seed: int) -> None:
    sl = SkipList(seed=seed)
    model: set[int] = set()

    for key in range(50):  # Đầu vào tăng dần.
        assert sl.insert(key)
        model.add(key)

    sl.assert_valid()
    assert list(sl.keys()) == sorted(model)

    for key in (4, 12, 25, 49, 12):
        result = sl.discard(key)
        assert result == (key in model)
        model.discard(key)

        sl.assert_valid()
        assert list(sl.keys()) == sorted(model)


for seed in range(8):
    test_skip_list(seed)
```

**Đối chiếu với `set` Python** là một cách kiểm thử ngữ nghĩa: số khóa, nội dung tập và phản hồi insert/remove phải khớp. Nhưng vì `set` không đảm bảo thứ tự sorted, ta so sánh `list(sl.keys())` với `sorted(model)`.

### 16.3. Bài thử thống kê không được hardcode chiều cao

Có thể tạo nhiều treap cùng kích thước `n` với những seed khác nhau rồi ghi lại:

```python
def sample_heights(n: int, seed_count: int = 100) -> list[int]:
    heights = []

    for seed in range(seed_count):
        tree = Treap(seed=seed)
        for key in range(n):
            tree.insert(key)

        tree.assert_valid()
        heights.append(tree.height_edges())

    return heights


heights = sample_heights(1000)
print("min =", min(heights),
      "max =", max(heights),
      "mean =", sum(heights) / len(heights))
```

Cần phân biệt:

- Thử nghiệm thực nghiệm không phải chứng minh toán.
- Kết quả sẽ phụ thuộc PRNG, seed set và số lần thử.
- **Không** viết `assert height <= 20` cho **mọi seed** rồi kết luận treap sai nếu gặp một cây hợp lệ nhưng cao hơn.
- Nếu muốn so sánh kỳ vọng tiệm cận, thử nhiều giá trị `n`, số lần thử đủ và ghi rõ đơn vị **số cạnh hoặc số nút trên đường**.

### 16.4. Failure injection và độ ổn định quyền sở hữu

Ngoài probability, cần kiểm tra:

- Trùng key không làm mất khóa hoặc tiêu thụ nguồn random ngoài chính sách.
- Xóa gốc, xóa lá, xóa nút có hai con rồi xác minh heap/BST.
- Tăng/giảm cấp chiều cao skip list khi chèn/xóa.
- Duyệt hết, duyệt rỗng, tìm key ngoài biên.
- Với ngôn ngữ có cấp phát thủ công, lỗi malloc/new giữa thao tác có làm mất/corrupt cấu trúc không?
- Copy/move/snapshot có định nghĩa ownership rõ ràng không?
- Iterator cũ sau chèn/xóa/rotation có được phép dùng không?
- Nguồn RNG có được cô lập giữa các test không?

### 16.5. Những số liệu hiệu năng nên đo

Nếu cần benchmark, có thể thu:

- Số phép so sánh key mỗi `find`.
- Chiều cao treap sau mỗi đợt thao tác.
- Số lần rotation của insert/delete.
- Số tầng và số forward pointer của skip list.
- Thời gian tìm/thêm/xóa ở kích cỡ `n` khác nhau.
- Phân phối độ trễ (trung vị, phân vị cao) qua nhiều seed.
- Bộ nhớ thực tế gồm overhead cấp phát, không chỉ `O(n)`.

Một benchmark phải chạy **cùng workload logic** cho các cấu trúc đem so, kiểm soát việc dựng dữ liệu, warm-up, thực thi GC và chi phí validation/logging. Không suy ra độ tốt từ một seed hay một máy duy nhất.

## 17. Những lỗi hiểu và cài đặt dễ mắc

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gắn một `random_tag` không tham gia quyết định hình dạng | BST vẫn lệch theo input | Định nghĩa invariants và thao tác dùng random thực sự |
| Chỉ shuffle khi nạp ban đầu | Update online vẫn có thể lệch | Dùng cấu trúc duy trì cân bằng/priority khi cập nhật |
| Chọn priority bằng key | Randomization giả; hình dạng lệ thuộc thứ tự khóa | Rút priority không phụ thuộc key theo mô hình |
| Dùng cùng một priority cố định cho mọi nút | Treap có thể suy biến thành BST không cân bằng | Bảo đảm thứ tự ưu tiên đủ ngẫu nhiên; xử lý tie |
| Giữ priority nhưng quên rotation sau chèn | Vi phạm heap | Kiểm tra và quay cho tới khi heap đúng |
| Rotation nối sai `left/right` | Có thể mất cây con/vi phạm BST | Kiểm tra invariant toàn cây sau test |
| Xóa nút có hai con bằng cách nối tùy ý | Vi phạm BST hoặc heap | Rotation/merge đúng quy tắc |
| Skip list chỉ xóa node ở tầng đáy | Còn pointer treo ở tầng cao | Sửa mọi tầng mà node xuất hiện |
| Skip list không lưu predecessor ở từng tầng | Chèn khó khớp liên kết | Dùng `update[level]` |
| Đếm một node ở mọi tầng thành nhiều khóa | `size` sai | Đếm key ở tầng đáy |
| Coi expected O(log n) là worst-case | Đánh giá sai latency | Nêu rõ xác suất và worst-case O(n) |
| Coi hash/PRNG bất kỳ là độc lập hoàn hảo | Chứng minh xác suất không khớp triển khai | Ghi rõ giả định, finite collision và seed |
| Dùng seed cố định công khai như cơ chế bảo vệ | Có thể đoán random trong môi trường đối kháng | Xác định mô hình an toàn và nguồn random phù hợp |
| Cây bị sửa giữa lúc iterator đang duyệt | Bỏ/lặp node, con trỏ treo hoặc data race | Quy định version, khóa hay snapshot |
| Chỉ test trên input ngẫu nhiên | Che lỗi khi input sorted/reversed | Test cả dữ liệu có cấu trúc và nhiều seed |
| Bác bỏ treap hợp lệ vì một chiều cao lớn | Nhầm hiệu năng xác suất với invariant | Tách validate logic khỏi kiểm thử thống kê |

**Điểm chốt:** randomization có thể đưa kỳ vọng hiệu năng về mức tốt hơn trong nhiều workload, nhưng không cho phép bỏ qua kiểm tra tính đúng đắn, vòng đời tài nguyên hoặc phân tích giả định.


## 18. Bài tập thực hành có lời giải

### Bài 1. Xác định thứ gì đang được ngẫu nhiên hóa

Một hệ thống nhận các khóa theo thứ tự `10,20,30,40,50`. Nó không đổi thứ tự nhận mà gắn một priority ngẫu nhiên vào mỗi khóa, rồi quay cây sao cho priority cha nhỏ hơn con. Thuật toán ngẫu nhiên hóa **dữ liệu vào** hay **hình dạng cấu trúc**?

**Lời giải:** Nó ngẫu nhiên hóa **hình dạng cấu trúc** qua priority của treap. Các khóa và thứ tự yêu cầu vẫn giữ nguyên. Phép quay chỉ thay liên kết cây để duy trì hai bất biến BST/heap.

### Bài 2. BST thường với dữ liệu tăng dần

Chèn `1,2,3,4,5` theo thứ tự đó vào BST không cân bằng. Chiều cao theo số cạnh và worst-case tìm là gì?

**Lời giải:** Cây lệch phải, chiều cao `h=4` cạnh. Tìm một khóa ở cuối đường hoặc khóa vắng có thể xét O(n) nút, không phải O(log n).

### Bài 3. Shuffle một lần có giải quyết mọi update về sau?

Ta shuffle 1.000 khóa đầu rồi xây BST thường. Sau đó nhận 1.000 khóa mới đều lớn hơn các khóa cũ theo thứ tự tăng dần. Cây có đảm bảo tiếp tục thấp không?

**Lời giải:** **Không.** Shuffle chỉ tác động đến đợt nạp ban đầu. Các khóa lớn hơn toàn bộ tập hiện tại có thể nối thành một nhánh bên phải ngày càng dài; BST thường không có cơ chế tái cân bằng.

### Bài 4. Bất biến treap

Một node treap min-heap có `key=20, priority=5`, con trái `key=10, priority=7`, con phải `key=30, priority=11`. Hai bất biến có đúng không?

**Lời giải:** Đúng: `10<20<30` theo BST; `5≤7` và `5≤11` theo heap. Bất biến phải đúng **đệ quy** trên tất cả cây con, không chỉ riêng gốc.

### Bài 5. Phát hiện lỗi heap

Một node treap có priority 80 và con trái có priority 10, nhưng thứ tự khóa BST đúng. Cấu trúc có phải treap min-heap hợp lệ không?

**Lời giải:** Không. Cha có priority lớn hơn con, vi phạm heap. Nếu node con được chèn mới, có thể quay phải tại cha để đưa node con lên, đồng thời giữ bất biến khóa BST.

### Bài 6. Quay phải có làm đổi inorder không?

```text
    X
   /
  Y
   \
    B
```

Sau rotate right tại X, thứ tự khóa inorder có thay không?

**Lời giải:** Không. Với bất biến `Y < B < X`, sau quay Y trở thành cha, B chuyển sang `X.left`; inorder vẫn là `Y, B, X` (cùng các cây con khác nếu có). Rotation đổi **hình dạng**, không đổi sorted order.

### Bài 7. Treap xác định bởi cặp key–priority

Có năm cặp: `(10,90), (20,20), (30,70), (40,10), (50,60)`. Nút gốc là khóa nào? Con trái và phải trực tiếp là gì?

**Lời giải:** Khóa 40 có priority nhỏ nhất (10) nên là gốc. Trong các khóa nhỏ hơn 40, priority nhỏ nhất là khóa 20 (20), nên con trái của gốc là 20. Trong các khóa lớn hơn 40 chỉ có khóa 50, nên con phải là 50. Các nhánh dưới 20 là 10 và 30.

### Bài 8. Đổi thứ tự chèn có nhất thiết đổi hình dạng?

Giữ đúng một tập **cặp (key,priority) cố định, phân biệt**, nhưng áp dụng thao tác chèn theo nhiều thứ tự. Treap cuối có hình dạng khác không?

**Lời giải:** Không, nếu thuật toán duy trì đúng BST+heap: cặp khóa–priority cố định xác định một Cartesian tree duy nhất. Tuy nhiên, nếu **priority được bốc khi insert**, đổi thứ tự insert có thể đổi priority **gắn với mỗi key**, nên hình dạng cụ thể có thể đổi dù seed giống nhau.

### Bài 9. Tính xác suất tổ tiên

Với `n` khóa phân biệt và priority IID liên tục, xác suất `x_8` là tổ tiên của `x_3` trong treap là bao nhiêu?

**Lời giải:** Đoạn khóa từ vị trí 3 tới 8 có `8-3+1=6` khóa. `x_8` phải có priority nhỏ nhất trong sáu khóa đó, xác suất là `1/6`.

### Bài 10. Công thức số điều hòa

Viết công thức kỳ vọng độ sâu của khóa `x_i` khi có `n` khóa theo mô hình treap chuẩn.

**Lời giải:**

\[
\mathbb{E}[D_i]=H_i+H_{n-i+1}-2
\]

với `H_m=\sum_{k=1}^m 1/k`. Suy ra O(log n) vì `H_m=O(\log m)`.

### Bài 11. Chứng minh độ sâu có tự chứng minh chiều cao không?

Nếu mọi nút có độ sâu kỳ vọng O(log n), có thể chỉ từ câu ấy kết luận chiều cao `max_i depth_i` có kỳ vọng O(log n) không?

**Lời giải:** **Không thể suy ra trực tiếp chỉ từ việc chặn kỳ vọng riêng lẻ.** Cần kiểm soát sự kiện có nút rất sâu, chẳng hạn bằng phân tích xác suất đuôi cho random BST/treap. Bản thân treap chuẩn thực sự có expected height O(log n), nhưng đòi lập luận mạnh hơn.

### Bài 12. Worst-case treap

Nếu priority tăng hoàn toàn theo thứ tự key tăng, treap min-heap có hình dạng gì? Thời gian tìm xấu nhất?

**Lời giải:** Cây một đường lệch phải; chiều cao `n-1`, tìm xấu nhất O(n). Sự kiện ấy hiếm theo phân phối priority đúng nhưng không bị loại trừ.

### Bài 13. Mục tiêu của random priority

Một chương trình tạo `priority = key`, rồi dùng đúng thuật toán quay treap. Với tập khóa `1..n`, có bảo đảm ngẫu nhiên hóa cân bằng không?

**Lời giải:** Không. Priority là hàm tất định đơn điệu của key, không độc lập với thứ tự khóa. Nó có thể tạo cây lệch, khiến lợi ích probabilistic bị mất.

### Bài 14. Duplicate trong treap set

Nếu `insert(7)` được gọi khi khóa 7 đã tồn tại, code bài học làm gì? Có bốc priority mới không?

**Lời giải:** Hàm tìm thấy khóa trùng, trả `False` và **không bốc** một priority mới. Đó là chính sách set khóa duy nhất, có lợi để test tái lập. Một multiset/map có thể có chính sách khác nhưng phải mô tả rõ.

### Bài 15. Xóa nút treap có hai con

Với treap min-heap, khi hạ nút đích có cả trái và phải trước khi xóa, nên chọn con nào để quay lên?

**Lời giải:** Chọn con có **priority nhỏ hơn** để đưa lên, sau đó tiếp tục hạ nút đích. Khi nút đích còn tối đa một con, nối con đó với cha và loại nút. Sau thao tác, các nút còn lại phải đúng BST+heap.

### Bài 16. Skip list cần shuffle dữ liệu không?

Một skip list nhận `1,2,3,...,n` theo thứ tự tăng dần và tự bốc level cho mỗi khóa. Có cần shuffle trước để đạt expected O(log n) không?

**Lời giải:** Không. Theo mô hình bốc level độc lập phù hợp, skip list có đường tìm kiếm kỳ vọng logarit **dù khóa nhận vào theo thứ tự tăng dần**. Đây là randomization của **cấu trúc liên kết tầng**.

### Bài 17. Xác suất đạt tầng 4

Với xác suất nâng mỗi tầng `p=1/2`, một node có xác suất đạt **ít nhất tầng thứ 4** là bao nhiêu (đánh số tầng từ 1)?

**Lời giải:** `\Pr[L\ge4]=(1/2)^3=1/8`. Muốn đạt tầng 4, cần được nâng thành công ba lần liên tiếp.

### Bài 18. Kỳ vọng số forward pointers

Với `p=1/2` và mô hình tầng không giới hạn, số liên kết forward kỳ vọng mỗi node là bao nhiêu? Với `n` node thì bao nhiêu?

**Lời giải:** `E[L]=1/(1-p)=2` forward slots mỗi node. Tổng số slot kỳ vọng `2n`, không tính header/allocator/sentinel. Đây là O(n) bộ nhớ kỳ vọng.

### Bài 19. Skip list quá thấp

Nếu tất cả node chỉ xuất hiện ở tầng đáy, tìm một khóa ở cuối danh sách tốn bao nhiêu?

**Lời giải:** Có thể phải đi qua Θ(n) node, nên worst-case thời gian tuyến tính. Random levels làm cấu trúc như vậy không điển hình, nhưng không biến worst-case thành O(log n).

### Bài 20. Thứ gì được đếm là một node skip list?

Node X xuất hiện ở bốn tầng liên kết. Bộ đếm `size` của set tăng bao nhiêu khi chèn X?

**Lời giải:** Tăng **1** vì X là một khóa và một node dữ liệu, chỉ được tham chiếu từ bốn tầng. Không đếm thành bốn object khác nhau.

### Bài 21. Xóa trong skip list

Nếu một node xuất hiện ở ba tầng nhưng chỉ gỡ liên kết tầng đáy, lỗi gì xảy ra?

**Lời giải:** Tầng cao còn con trỏ tới node đã bị loại, có thể phá sorted traversal, truy cập object không còn thuộc set hoặc tạo dangling pointer trong C/C++. Phải cập nhật **mọi tầng mà node có mặt**.

### Bài 22. Fixed `MAX_LEVEL` và khả năng mở rộng

Một skip list dùng `MAX_LEVEL=8` cố định và số khóa tăng vô hạn. Có thể khẳng định expected O(log n) cho mọi `n` mà không điều chỉnh gì không?

**Lời giải:** Không. Khi n rất lớn so với số tầng được phép, tầng cao nhất không còn đủ khả năng chia nhỏ toàn bộ đường đi; độ dài các đoạn ngang có thể tăng theo n. Cần giới hạn phạm vi sử dụng hoặc điều chỉnh mức cao tối đa theo quy mô.

### Bài 23. Seed giống nhau có làm dữ liệu khác nhau không?

Hai treap cùng chèn một tập khóa theo **cùng thứ tự** và dùng cùng thuật toán/seed PRNG. Chúng phải trả `contains`/inorder khác nhau vì random không?

**Lời giải:** Không. Trạng thái và hình dạng nội bộ có thể tái lập theo cùng seed, nhưng nội dung logic luôn là cùng tập khóa. Với thứ tự thao tác như nhau, chuỗi priority được rút như nhau nên hình dạng cũng có thể giống nhau; không coi hình dạng là hợp đồng ổn định qua mọi phiên bản phần mềm.

### Bài 24. Va chạm priority 64-bit

Vì sao dùng `getrandbits(64)` chưa thể nói “priority luôn phân biệt”?

**Lời giải:** Không gian 64 bit hữu hạn; hai lần rút độc lập có xác suất trùng khác 0. Cần tie-breaker hoặc rút lại nếu cần thứ tự toàn phần. Phân tích toán của mô hình liên tục không áp dụng **nguyên xi** khi va chạm có thiên lệch.

### Bài 25. Expected khác worst-case

Một treap có expected search O(log n) nhưng một seed cụ thể tạo cây cao n/2. Có thể kết luận treap triển khai sai không?

**Lời giải:** Không chỉ từ chiều cao. Cần kiểm tra BST và heap invariant, dữ liệu đầy đủ và phân phối random qua nhiều seed. Một lần ngẫu nhiên xấu có thể xảy ra trong mô hình expected; không đồng nghĩa implementation sai.

### Bài 26. Adaptive input

Một đối thủ có thể quan sát được chi tiết random nội bộ rồi chọn khóa thao tác tiếp theo. Có tự áp dụng mọi chứng minh expected O(log n) dành cho chuỗi thao tác cố định không?

**Lời giải:** Không. Mô hình phân tích có thể giả định thao tác không phụ thuộc random chưa rút hoặc không bị lộ. Đối thủ thích nghi làm thay đổi tính độc lập và yêu cầu phân tích riêng; nếu nhạy cảm bảo mật, cần nguồn random và cấu trúc phù hợp.

### Bài 27. Amortized có phải expected không?

Dynamic array tăng capacity theo hệ số có `push_back` khấu hao O(1) dù thỉnh thoảng reallocate O(n). Điều này có yêu cầu RNG không?

**Lời giải:** Không. Amortized phân bổ chi phí trên **chuỗi thao tác**, còn expected lấy trung bình trên **lựa chọn ngẫu nhiên**. Hai cách đánh giá có thể áp dụng độc lập.

### Bài 28. Chọn cấu trúc cho deadline cứng

Một dịch vụ phải có giới hạn worst-case chặt cho mỗi lần tìm, không cho phép các lần truy cập hiếm nhưng tuyến tính. Nên ưu tiên điều gì?

**Lời giải:** Một cấu trúc với bảo đảm worst-case được chứng minh, như AVL/red-black tree, hoặc hệ thống có giới hạn/fallback cụ thể. Treap/skip list thuần expected O(log n) không tự đáp ứng yêu cầu worst-case cứng.

### Bài 29. Bộ duyệt qua một phép quay

Một iterator inorder tự cài giữ stack tổ tiên. Treap vừa rotate để thêm khóa mới. Iterator có mặc nhiên còn hợp lệ không?

**Lời giải:** Không. Rotation đổi liên kết và đường tổ tiên; iterator có thể đi sai đường hoặc thăm trùng/bỏ nút. Phải tuân thủ hợp đồng invalidation, snapshot hoặc tạo lại cursor sau cập nhật.

### Bài 30. Chọn phép đo khi benchmark

Muốn so sánh treap với cây cân bằng tất định trên cùng dãy chèn đã sắp xếp, nên đo những gì ngoài một lần `find`?

**Lời giải:** Cần so sánh đúng nội dung và bất biến, chiều cao, số so sánh/rotation, thời gian find/insert/delete qua nhiều n và nhiều seed, phân vị độ trễ, metadata/peak memory và chi phí cấp phát. Một seed tốt không đại diện cho phân phối.

## 19. Tổng kết: ngẫu nhiên hóa quyết định bố cục, không đòi dữ liệu ngẫu nhiên

1. **BST không tự cân bằng** có thể thành một đường dài khi nhận khóa đã sắp xếp. Shuffle trước khi build chỉ tác động đợt nạp ban đầu, không bảo đảm các cập nhật trực tuyến sau đó.
2. **Ngẫu nhiên hóa cấu trúc** đặt randomness vào **quy tắc hình thành/duy trì liên kết**, ví dụ priority của treap hoặc số tầng của skip list. Khóa và ý nghĩa thao tác của người dùng không bị hoán đổi.
3. **Treap** đồng thời thỏa BST theo key và heap theo priority; phép quay giữ sorted order nhưng đổi hình dạng. Với priority IID phù hợp, expected độ sâu/chiều cao là O(log n); worst-case vẫn O(n).
4. **Skip list** bốc mức cho từng node bằng các lần tung đồng xu; ở `p=1/2`, kỳ vọng mỗi node có 2 slot forward, tìm/thêm/xóa O(log n) kỳ vọng theo mô hình chuẩn, bộ nhớ O(n) kỳ vọng.
5. **Expected không phải worst-case và không phải amortized.** Cần nói rõ nguồn random, mô hình input, giới hạn tail hoặc deadline nếu ứng dụng yêu cầu.
6. **RNG thực tế hữu hạn** có seed, chu kỳ, va chạm, quy tắc tie và những giả định khác mô hình toán lý tưởng. Trong bối cảnh đối kháng, chỉ dùng PRNG seed cố định không tự bảo đảm an toàn.
7. **Bất biến luôn phải đúng cho mọi seed:** BST order, heap order, thứ tự forward của skip list, số lượng khóa và không có liên kết hỏng. Bài test ngữ nghĩa khác bài đo phân phối hiệu năng.
8. **Đánh đổi bộ nhớ và bảo trì:** treap thêm priority/node, skip list thêm forward pointers, cả hai có chi phí cấp phát và cache locality. Không tự ưu việt hơn AVL/red-black, mảng sorted hoặc B-tree trong mọi workload.
9. **Cập nhật làm thay đổi hình dạng:** iterator, parent metadata, snapshot và ownership cần hợp đồng riêng; randomization không miễn trừ lỗi vòng đời hay data race.

Khi gặp một cấu trúc “trông cân bằng nhờ dữ liệu may mắn”, hãy hỏi: **Nếu khóa đầu vào bị sắp xếp hoặc cập nhật liên tục thì bảo đảm nào vẫn còn?** Treap và skip list cho một câu trả lời xác suất rõ ràng: **giữ đầu vào tùy ý nhưng làm cho quyết định tổ chức cấu trúc có ngẫu nhiên độc lập theo giả định đã công bố**. Chính sự chuyển nguồn ngẫu nhiên từ dữ liệu bên ngoài sang thuật toán bên trong là ý tưởng cốt lõi của bài.

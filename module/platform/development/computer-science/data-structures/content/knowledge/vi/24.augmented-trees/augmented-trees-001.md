# Nguyên tắc thêm thông tin phụ vào một cây nền

## 1. Từ một cây thông thường đến cây tăng cường

Trong học phần **Cấu trúc dữ liệu**, ta đã gặp những cấu trúc cây có nhiệm vụ lưu quan hệ phân cấp, quản lý khóa có thứ tự, hoặc hỗ trợ các phép truy vấn theo một quy tắc nhất định. Tuy nhiên, một cây nền đôi khi chưa đáp ứng đủ nhanh một yêu cầu cụ thể.

Ví dụ, với **cây tìm kiếm nhị phân** (Binary Search Tree — BST) lưu các khóa số phân biệt, ta có thể tìm một khóa bằng cách so sánh và đi theo một nhánh. Nhưng nếu muốn biết:

- **Khóa nhỏ thứ `k`** là khóa nào?
- Có **bao nhiêu khóa nhỏ hơn `x`**?
- **Tổng các khóa trong khoảng `[L,R]`** là bao nhiêu?
- Cây con có gốc tại một nút chứa bao nhiêu phần tử?

Một BST chỉ lưu `key`, `left` và `right` chưa có sẵn mọi câu trả lời trên. Có thể duyệt cả cây để tính, nhưng lặp lại phép duyệt sẽ tốn thời gian.

**Cây tăng cường (augmented tree)** giải quyết vấn đề bằng cách **giữ nguyên bất biến cốt lõi của cây nền**, đồng thời **lưu thêm thông tin phụ** tại các nút để trả lời một nhóm truy vấn nhanh hơn.

Ví dụ:

```text
BST thông thường:               BST tăng cường:

     key=8                           key=8
     /   \                           size=7
    4     12                         total=56
                                   /          \
                              key=4          key=12
                              size=3         size=3
                              total=12       total=36
```

Ở đây:

- `size`: số nút trong **cây con có gốc tại nút hiện tại**.
- `total`: tổng các khóa trong **cây con có gốc tại nút hiện tại**.

Hai trường này không làm thay đổi thứ tự các khóa của BST. Chúng là **thông tin được suy ra từ cây**, giúp những phép tính như xếp hạng và tổng đoạn không phải duyệt lại toàn bộ các phần tử mỗi lần.

Bài học tập trung vào câu hỏi thiết kế quan trọng nhất:

> **Thêm thông tin nào, tính lại bằng công thức nào, và bảo đảm thông tin ấy luôn đúng sau khi cấu trúc cây thay đổi như thế nào?**

Đây là nguyên tắc chung đứng sau **order-statistic tree**, **interval tree**, một số biến thể cây đoạn (*segment tree*), các cây lưu tổng/trị nhỏ nhất và nhiều cấu trúc dữ liệu có cache tổng hợp.

## 2. Cây nền vẫn là nguồn dữ liệu và nguồn bất biến chính

### 2.1. Cây nền (base tree) là gì?

**Cây nền** là cấu trúc ban đầu mà ta mở rộng, chẳng hạn:

- BST thông thường.
- AVL tree, Red–Black Tree hoặc cây tìm kiếm tự cân bằng.
- Treap.
- Cây đoạn (*segment tree*).
- Cây tổng quát theo quan hệ cha–con, khi mỗi nút có một số lượng con bất kỳ.

Cây nền xác định những **bất biến nền** cần giữ. Ví dụ, BST có khóa phân biệt yêu cầu:

\[
\forall u,\quad
\text{mọi khóa trong subtree trái của }u
< key(u)
<\text{mọi khóa trong subtree phải của }u.
\]

Với AVL, ngoài bất biến BST còn có ràng buộc cân bằng chiều cao. Với Red–Black Tree có bất biến màu và số nút đen trên các đường đi. Với cây đoạn, cấu trúc nút gắn với một phân hoạch khoảng cố định.

Việc thêm `size` hay `total` **không được phép phá những bất biến nền này**.

### 2.2. Thông tin phụ không phải một cấu trúc độc lập

Giả sử một nút `u` lưu:

```text
u.key
u.left
u.right
u.size
u.total
```

Hai trường cuối là **metadata/giá trị tổng hợp**, có thể **tính lại** từ cấu trúc và dữ liệu thật:

- `size(u)` phụ thuộc vào số nút của các cây con.
- `total(u)` phụ thuộc vào khóa `u` và tổng hai cây con.

Trong cách thiết kế này, **khóa và các liên kết cây là nguồn chân lý** (*source of truth*). Các giá trị phụ chỉ là những thông tin được lưu để truy vấn nhanh. Nếu metadata sai, cây vẫn có thể là một BST hợp lệ về thứ tự khóa, nhưng **những truy vấn dựa trên metadata sẽ trả kết quả sai**.

Đó là sự khác biệt giữa hai tầng bất biến:

| Tầng | Cần bảo đảm | Ví dụ vi phạm |
|---|---|---|
| Bất biến nền | Đường đi, cha–con, thứ tự khóa, cân bằng nếu có | Khóa `12` xuất hiện trong cây con trái của `8` |
| Bất biến tăng cường | Metadata bằng đúng hàm tổng hợp của cây con hiện tại | Nút thực tế có 5 hậu duệ tính cả chính nó nhưng `size=4` |

**Một cây tăng cường đúng phải giữ cả hai tầng.**

### 2.3. Metadata nào đáng lưu?

Một thông tin phụ đáng lưu khi đồng thời thỏa các điều kiện thực tế:

1. Nó giúp tăng tốc một truy vấn có ý nghĩa, được gọi đủ thường xuyên.
2. Có thể **tính lại** từ dữ liệu nút và metadata của số ít cây con (tốt nhất `O(1)`).
3. Có cách cập nhật sau chèn, xóa, đổi giá trị và tái cấu trúc như xoay cây.
4. Chi phí bộ nhớ thêm và duy trì metadata nhỏ hơn lợi ích truy vấn mang lại.

Không phải lưu càng nhiều trường càng tốt. Một cache rất đắt để cập nhật có thể khiến hệ thống chậm hơn so với tính theo yêu cầu.

## 3. Nguyên tắc tổng hợp cục bộ từ các cây con

### 3.1. Công thức cốt lõi

Với cây nhị phân, cách thiết kế phổ biến là định nghĩa một thông tin tổng hợp `A(u)` tại nút `u` bằng:

\[
A(u)=F\bigl(A(u.left),\ data(u),\ A(u.right)\bigr).
\]

Ở đây:

- `data(u)` là dữ liệu gốc tại nút.
- `A(u.left)` và `A(u.right)` là thông tin đã tính đúng cho hai cây con.
- `F` là phép kết hợp theo **quy tắc bài toán**.
- Nếu cây con rỗng, ta cung cấp **giá trị trung hòa** phù hợp.

Ý tưởng là **không duyệt lại toàn bộ hậu duệ** để tính `A(u)`. Nếu `F` mất `O(1)`, cập nhật nút `u` từ hai con chỉ cần thời gian hằng số.

### 3.2. Ba ví dụ dễ hình dung

| Thông tin phụ `A(u)` | Giá trị ở cây rỗng | Công thức cho nút `u` |
|---|---:|---|
| `size`: số nút cây con | `0` | `1 + size(left) + size(right)` |
| `total`: tổng khóa số | `0` | `key(u) + total(left) + total(right)` |
| `maximum`: khóa lớn nhất trong cây con | `-\infty` | `max(key(u), max(left), max(right))` |

Nếu áp dụng `total` cho các giá trị **không phải số** thì cần thay phép cộng bằng một phép tổng hợp thích hợp. Với số thực có sai số làm tròn, phép cộng theo các cấu trúc cây khác nhau có thể cho chênh lệch nhỏ do thứ tự cộng; điều này không làm thay đổi ý tưởng bất biến, nhưng phải xét khi hệ thống cần độ chính xác số học đặc biệt.

Một ví dụ liên quan đến **chiều cao**:

\[
height(\varnothing)=-1,\qquad
height(u)=1+\max(height(u.left),height(u.right)).
\]

Với quy ước đếm **số cạnh**, nút lá có chiều cao `0`. Chiều cao cũng là một giá trị tăng cường nếu cây nền không vốn lưu nó.

### 3.3. Điều kiện đủ để cập nhật nhanh

Nếu tổng hợp tại nút chỉ cần:

- Dữ liệu cục bộ của nút.
- Metadata đã đúng của các con trực tiếp.
- Một số **hằng** phép toán trên dữ liệu có kích thước giới hạn.

Thì việc tính lại **một nút** mất `O(1)`.

Khi một thay đổi xảy ra tại một lá, thường chỉ cần tính lại **các tổ tiên** của lá. Với chiều cao cây là `h` và mỗi mức cập nhật `O(1)`, thời gian duy trì metadata là **`O(h+1)`**. Nếu cây nền tự cân bằng có `h=O(\log n)`, phần duy trì này cũng là `O(\log n)`.

Ngược lại, nếu metadata của `u` đòi duyệt **mọi nút trong cây con** của `u`, việc tính lại một nút có thể tốn `O(s)` với `s` là kích thước cây con. Lặp lại tại các tổ tiên có thể khiến cập nhật rất đắt. Đây là dấu hiệu cần **tìm một công thức tổng hợp khác**, lưu thêm thông tin phù hợp, hoặc chấp nhận một đánh đổi khác.

### 3.4. Tính kết hợp và phép gộp tổng quát

Các tổng hợp theo cây con có thể xây từ một phép toán gộp `⊕` mang tính **kết hợp** (*associative*) với phần tử trung hòa `e`:

\[
(a\oplus b)\oplus c = a\oplus(b\oplus c),
\qquad
e\oplus a=a\oplus e=a.
\]

Ví dụ:

- Tổng số: `⊕=+`, `e=0`.
- Đếm số phần tử: `⊕=+`, `e=0` với mỗi nút đóng góp `1`.
- Giá trị nhỏ nhất: `⊕=\min`, `e=+\infty`.
- Ghép chuỗi theo thứ tự: `⊕` là nối chuỗi, `e=""`; phép nối **không giao hoán** nhưng vẫn kết hợp (nếu xét chuỗi lý tưởng, không tính chi phí sao chép).

**Không cần phép toán giao hoán**. Khi phép gộp phụ thuộc thứ tự, ta phải giữ thứ tự **cây con trái → nút hiện tại → cây con phải**. Tuy nhiên, nếu việc ghép chuỗi trực tiếp sao chép toàn bộ nội dung, thời gian gộp có thể tăng theo độ dài chuỗi; muốn giữ cập nhật nhanh cần một cách biểu diễn tóm tắt hoặc cấu trúc chuỗi phù hợp.

Trong cây tổng quát, công thức tương ứng có dạng:

\[
A(u)=F\bigl(data(u),A(c_1),A(c_2),\ldots,A(c_k)\bigr).
\]

Nếu `u` có `k` con và phải xem hết `k` kết quả, tính lại `u` có thể mất **`O(k)`**, không còn `O(1)` theo số nút con. Muốn tối ưu hơn cần chọn phép gộp hỗ trợ cập nhật gia tăng, chỉ mục/metadata bổ sung hoặc cấu trúc cân bằng trên danh sách con.

## 4. Quy trình thiết kế một cây tăng cường

Một quy trình thực tế gồm sáu bước.

### Bước 1 — Xác định truy vấn phải tăng tốc

Trước khi thêm trường, hãy phát biểu truy vấn rõ ràng:

- `select(k)`: phần tử nhỏ thứ `k`.
- `rank(x)`: số phần tử có khóa nhỏ hơn `x`.
- `range_sum(L,R)`: tổng khóa trong đoạn đóng `[L,R]`.
- `find_overlap([L,R])`: tìm một khoảng giao với khoảng truy vấn.

Nhiều người lưu một giá trị chỉ vì “có vẻ hữu ích” mà không biết thao tác nào sẽ đọc nó. Thiết kế tốt bắt đầu từ **yêu cầu truy vấn**, không bắt đầu từ tên trường.

### Bước 2 — Chọn cây nền phù hợp

Nếu cần so sánh khóa và xếp hạng, chọn BST hoặc BST tự cân bằng là tự nhiên.

Nếu cần truy vấn đoạn trên các vị trí tĩnh, cây đoạn có thể phù hợp hơn.

Nếu dữ liệu là một danh mục có nhiều con không theo thứ tự khóa, việc dùng BST làm cây phân cấp có thể làm sai ngữ nghĩa quan hệ cha–con. Có thể **lưu cây phân cấp riêng** và bổ sung một chỉ mục tìm kiếm.

**Tăng cường cây không thay đổi mục đích gốc của cấu trúc nền.** Nó chỉ thêm khả năng truy vấn hoặc duy trì thông tin.

### Bước 3 — Định nghĩa metadata và giá trị ở cây rỗng

Ví dụ:

\[
size(\varnothing)=0,\quad total(\varnothing)=0.
\]

Với khoảng, có thể cần `maxHigh(\varnothing)=-\infty`.

Nếu nhầm giá trị trung hòa, đặc biệt với dữ liệu âm hoặc tập rỗng, phép tính có thể sai dù phần còn lại của thuật toán đúng.

### Bước 4 — Viết một hàm `recompute` cho một nút

Thay vì cập nhật rải rác:

```text
node.size += 1
parent.total -= removed_key
...
```

hãy định nghĩa duy nhất một hàm tính lại từ trạng thái **đang đúng của hai con**:

```text
RECOMPUTE(u):
    u.size = 1 + size(u.left) + size(u.right)
    u.total = key(u) + total(u.left) + total(u.right)
```

Các thuật toán chèn, xóa, xoay cây chỉ cần gọi đúng hàm ở **đúng thời điểm**. Cách này giảm nguy cơ bỏ sót một nhánh cập nhật.

### Bước 5 — Liệt kê mọi thao tác có thể làm metadata cũ

Với BST:

- Chèn một nút.
- Xóa một nút.
- Thay đổi khóa hoặc dữ liệu đóng góp vào tổng.
- Xoay trái/phải, hoặc các phép tái cân bằng khác.
- Tách/gộp cây (*split/join*), dựng lại một cây con.
- Khôi phục dữ liệu từ tệp hay nhận một cấu trúc mới.

**Không phải thao tác đọc làm metadata cũ**, nhưng hầu hết thao tác thay đổi cấu trúc hoặc giá trị đều có khả năng đó. Mỗi thao tác cần quy tắc cập nhật và kiểm chứng bất biến.

### Bước 6 — Chứng minh đúng và phân tích chi phí

Xác minh:

1. **Cơ sở:** nút mới hoặc cây rỗng có metadata đúng.
2. **Giả thiết quy nạp:** metadata của các cây con đang đúng.
3. **Bước quy nạp:** gọi `recompute(u)` làm metadata của `u` đúng.
4. **Sau cập nhật:** các nút bị ảnh hưởng được tính lại **từ dưới lên**.
5. **Sau xoay:** tính lại các nút có con đã thay đổi theo **thứ tự phụ thuộc**.

Sau đó mới kết luận chi phí cập nhật là `O(h)` hay `O(\log n)`, tùy chiều cao được cây nền bảo đảm.

## 5. Ví dụ xuyên suốt: BST lưu `size` và `total`

Xét BST có bảy khóa phân biệt:

```text
                             8
                         size=7
                         total=56
                         /      \
                        /        \
                       4          12
                    size=3       size=3
                    total=12     total=36
                    /   \        /    \
                   2     6     10     14
                size=1 size=1 size=1 size=1
                sum=2  sum=6  sum=10 sum=14
```

Bảng metadata:

| Nút `u` | Khóa thuộc cây con của `u` | `size(u)` | `total(u)` |
|---|---|---:|---:|
| `2` | `{2}` | 1 | 2 |
| `6` | `{6}` | 1 | 6 |
| `10` | `{10}` | 1 | 10 |
| `14` | `{14}` | 1 | 14 |
| `4` | `{2,4,6}` | 3 | 12 |
| `12` | `{10,12,14}` | 3 | 36 |
| `8` | `{2,4,6,8,10,12,14}` | 7 | 56 |

Ví dụ tại nút `8`:

\[
size(8)=1+size(4)+size(12)=1+3+3=7,
\]

\[
total(8)=8+total(4)+total(12)=8+12+36=56.
\]

**Hai loại thông tin phục vụ hai truy vấn khác nhau:**

- `size` cho phép bỏ qua trọn một cây con khi đếm vị trí xếp hạng.
- `total` cho phép cộng trọn một cây con khi tính tổng tiền tố/đoạn.

Một nút có thể lưu **nhiều metadata cùng lúc**, miễn cập nhật chúng đúng và chi phí thêm phù hợp.

### Bất biến chính thức

Với mọi nút `u`, định nghĩa:

\[
S(u)=
\begin{cases}
0,&u=\varnothing,\\
1+S(u.left)+S(u.right),&u\ne\varnothing,
\end{cases}
\]

\[
T(u)=
\begin{cases}
0,&u=\varnothing,\\
key(u)+T(u.left)+T(u.right),&u\ne\varnothing.
\end{cases}
\]

Ta yêu cầu **trường lưu trữ**:

\[
u.size=S(u),\qquad u.total=T(u).
\]

Giá trị đúng được xác định từ **cây hiện tại**, không phải từ lịch sử đã từng chèn hoặc xóa những gì.

## 6. Cài đặt Python: nút BST và hàm cập nhật cục bộ

Trong ví dụ này:

- Khóa là **số nguyên**.
- Mỗi khóa xuất hiện **tối đa một lần**.
- `total` là tổng **chính các khóa**. Nếu bài toán có khóa và trọng số riêng, công thức tổng phải dùng trường trọng số.
- BST minh họa **chưa tự cân bằng**, nên chiều cao có thể là `O(n)`. Khi nói lợi ích `O(\log n)`, ta sẽ nêu rõ điều kiện cây cân bằng.

### 6.1. Định nghĩa nút và hàm `recompute`

```python
class Node:
    def __init__(self, key):
        self.key = key
        self.left = None
        self.right = None
        self.size = 1
        self.total = key


def size_of(node):
    return 0 if node is None else node.size


def total_of(node):
    return 0 if node is None else node.total


def recompute(node):
    """Hai con đã có metadata đúng trước khi gọi."""
    if node is None:
        return

    node.size = 1 + size_of(node.left) + size_of(node.right)
    node.total = (
        node.key
        + total_of(node.left)
        + total_of(node.right)
    )
```

**Điều kiện của `recompute`:** metadata của các con phải đúng. Nếu tính lại cha trước con sau một cập nhật sâu, giá trị cha sẽ được tổng hợp từ thông tin cũ.

### 6.2. Chèn không cân bằng và cập nhật theo đường đi

Ta đi từ gốc xuống vị trí chèn theo bất biến BST. Đồng thời lưu danh sách **các tổ tiên trên đường tìm**. Sau khi chèn nút mới, đi ngược danh sách để tính lại các trường từ dưới lên.

```python
def insert(root, key):
    """Trả (gốc mới, đã_chèn). Khóa trùng không được thêm."""
    if root is None:
        return Node(key), True

    path = []
    current = root

    while True:
        if key == current.key:
            return root, False

        path.append(current)

        if key < current.key:
            if current.left is None:
                current.left = Node(key)
                break
            current = current.left
        else:
            if current.right is None:
                current.right = Node(key)
                break
            current = current.right

    # Con/cháu trước, rồi tới cha và cuối cùng là gốc.
    for node in reversed(path):
        recompute(node)

    return root, True


def build_tree(keys):
    root = None
    for key in keys:
        root, _ = insert(root, key)
    return root


root = build_tree([8, 4, 12, 2, 6, 10, 14])

print(size_of(root))   # 7
print(total_of(root))  # 56

print(size_of(root.left))   # 3
print(total_of(root.left))  # 12

root, inserted = insert(root, 5)
print(inserted)        # True
print(size_of(root))   # 8
print(total_of(root))  # 61

root, inserted = insert(root, 5)
print(inserted)        # False: khóa trùng
print(size_of(root))   # 8: không được tăng thêm lần nữa
```

### 6.3. Truy vết thêm khóa `5`

Trong cây bảy nút ban đầu, đường đi tới vị trí chèn `5` là:

```text
8 → 4 → 6 → trái (rỗng)
```

Tạo nút `5` mới với:

```text
size(5)=1
total(5)=5
```

Sau đó cập nhật theo đúng thứ tự:

| Nút được tính lại | `size` mới | `total` mới | Vì sao? |
|---|---:|---:|---|
| `6` | 2 | 11 | Có thêm con trái `5` |
| `4` | 4 | 17 | Cây con phải `6` đã đổi |
| `8` | 8 | 61 | Cây con trái `4` đã đổi |

Nút `12` và các cây con nằm ngoài đường tìm **không thay đổi** nên không cần tính lại.

**Bất biến sau chèn:**

\[
root.size=8,\qquad root.total=56+5=61.
\]

### 6.4. Chi phí của ví dụ

Gọi `d` là số nút đã đi qua trên đường từ gốc tới vị trí chèn, tối đa `h+1`.

- Tìm vị trí: `O(d)` thời gian.
- Tính lại metadata trên đường đi: `O(d)` thời gian, vì mỗi `recompute` mất `O(1)`.
- Bộ nhớ phụ lưu `path`: `O(d)`.
- Lưu các trường `size` và `total` trên toàn cây: **`O(n)` bộ nhớ bổ sung**.

Đây là BST **không cân bằng**, nên trường hợp xấu nhất `d=O(n)`. Nếu chuyển cùng chiến lược cập nhật sang một BST tự cân bằng có `h=O(\log n)` và xử lý cả phép xoay, phần duy trì metadata có thể được giới hạn **`O(\log n)`**.

## 7. Truy vấn phần tử nhỏ thứ `k` bằng `subtree size`

### 7.1. Xếp hạng trong một BST

Ta dùng **thứ tự tăng dần** của các khóa, đánh số vị trí từ **`1`**:

```text
Các khóa:      2   4   6   8   10  12  14
Vị trí k:      1   2   3   4    5   6   7
```

Để tìm phần tử nhỏ thứ `k` tại nút `u`, gọi:

\[
L=size(u.left).
\]

Vì mọi khóa trong cây con trái nhỏ hơn khóa của `u`:

- Nếu `k=L+1`: **nút `u` là kết quả**.
- Nếu `k\le L`: phần tử cần tìm nằm trong **cây con trái**.
- Nếu `k>L+1`: nằm trong **cây con phải**, với thứ hạng mới `k'=k-L-1`.

Ta không duyệt toàn bộ cây con trái: **một lần đọc `size(u.left)` đủ để bỏ qua cả nhóm**.

### 7.2. Python: `select_kth`

```python
def select_kth(root, k):
    """Khóa nhỏ thứ k, đánh số từ 1; lỗi nếu k không hợp lệ."""
    if not 1 <= k <= size_of(root):
        raise IndexError("k nằm ngoài số phần tử của cây")

    current = root

    while current is not None:
        left_count = size_of(current.left)

        if k == left_count + 1:
            return current.key

        if k <= left_count:
            current = current.left
        else:
            k -= left_count + 1
            current = current.right

    # Nếu metadata hợp lệ thì không tới đây.
    raise RuntimeError("metadata size không nhất quán")
```

Ví dụ trên cây bảy nút ban đầu:

```text
select_kth(root, 4):

Tại 8: size(left)=3
k=4 = 3+1 → trả 8

select_kth(root, 6):

Tại 8: size(left)=3, k=6>4
Đi phải sang 12, k'=6-4=2
Tại 12: size(left)=1, k'=2=1+1 → trả 12
```

Nếu cây có chiều cao `h`, hàm đi tối đa một đường từ gốc xuống một nút: **`O(h+1)` thời gian** và **`O(1)` bộ nhớ phụ**. Với cây cân bằng: **`O(\log n)`**.

Không được áp dụng công thức này cho một cây lưu `size` sai hoặc không có bất biến BST: điều kiện “các khóa bên trái nhỏ hơn nút” là thiết yếu để diễn giải `k` theo thứ tự.

## 8. Truy vấn xếp hạng `rank(x)` bằng `subtree size`

### 8.1. Định nghĩa rank rõ ràng

Có hai quy ước thường gặp:

- `rank_lt(x)` = **số khóa nhỏ hơn `x`**.
- `rank_le(x)` = **số khóa nhỏ hơn hoặc bằng `x`**.

Bài này cài đặt `rank_lt`; giá trị `x` **không nhất thiết có mặt** trong cây.

Ví dụ trên cây bảy khóa:

```text
rank_lt(8)  = 3  (2, 4, 6)
rank_lt(10) = 4  (2, 4, 6, 8)
rank_lt(9)  = 4  (9 không có trong cây)
rank_lt(2)  = 0
```

### 8.2. Lập luận khi đi xuống

Nếu `x\le key(u)`, các khóa cần đếm (nhỏ hơn `x`) nếu có chỉ có thể ở **bên trái**.

Nếu `x>key(u)`, ta biết:

- Mọi `size(u.left)` khóa của cây con trái đều nhỏ hơn `x`.
- Chính `key(u)` cũng nhỏ hơn `x`.

Vì thế, cộng nhanh `size(u.left)+1` rồi đi sang phải để tìm các khóa còn lại.

### 8.3. Python: `rank_lt`

```python
def rank_lt(root, x):
    """Số khóa nhỏ hơn x, kể cả khi x không tồn tại."""
    count = 0
    current = root

    while current is not None:
        if x <= current.key:
            current = current.left
        else:
            count += size_of(current.left) + 1
            current = current.right

    return count
```

Với cây bảy nút ban đầu:

```python
base = build_tree([8, 4, 12, 2, 6, 10, 14])

print(select_kth(base, 1))  # 2
print(select_kth(base, 4))  # 8
print(select_kth(base, 7))  # 14

print(rank_lt(base, 8))     # 3
print(rank_lt(base, 10))    # 4
print(rank_lt(base, 9))     # 4
print(rank_lt(base, 20))    # 7
```

Thời gian **`O(h+1)`**, bộ nhớ phụ **`O(1)`**. Nếu cây có nhiều khóa trùng, phải định nghĩa riêng chính sách lưu khóa, `size` và rank; mã trên giả định **khóa phân biệt**.

## 9. Truy vấn tổng tiền tố và tổng đoạn bằng `subtree total`

### 9.1. Tổng các khóa nhỏ hơn hoặc bằng `x`

Định nghĩa:

\[
P_{\le}(x)=\sum_{\substack{key(u)\le x}} key(u).
\]

Nếu đang ở nút `u`:

- Với `x<key(u)`, những khóa cần cộng chỉ có thể nằm ở **cây con trái**.
- Với `x\ge key(u)`, **toàn bộ cây con trái** và **chính `u`** đều thỏa điều kiện. Cộng `total(u.left)+key(u)`, rồi đi sang phải.

### 9.2. Python: tổng tiền tố

```python
def prefix_sum_le(root, x):
    """Tổng các khóa <= x."""
    total = 0
    current = root

    while current is not None:
        if x < current.key:
            current = current.left
        else:
            total += total_of(current.left) + current.key
            current = current.right

    return total


def prefix_sum_lt(root, x):
    """Tổng các khóa < x."""
    total = 0
    current = root

    while current is not None:
        if x <= current.key:
            current = current.left
        else:
            total += total_of(current.left) + current.key
            current = current.right

    return total
```

### 9.3. Tổng trong đoạn đóng `[L,R]`

Với `L\le R`:

\[
rangeSum(L,R)=P_{\le}(R)-P_{<}(L).
\]

Phải dùng **tiền tố nhỏ hơn `L`** chứ không phải tiền tố nhỏ hơn hoặc bằng `L` nếu muốn **bao gồm cả khóa `L`**.

```python
def range_sum(root, low, high):
    """Tổng các khóa thuộc đoạn đóng [low, high]."""
    if low > high:
        return 0

    return (
        prefix_sum_le(root, high)
        - prefix_sum_lt(root, low)
    )


base = build_tree([8, 4, 12, 2, 6, 10, 14])

print(prefix_sum_le(base, 10))  # 30 = 2+4+6+8+10
print(prefix_sum_lt(base, 10))  # 20 = 2+4+6+8
print(range_sum(base, 5, 12))   # 36 = 6+8+10+12
print(range_sum(base, 20, 30))  # 0
print(range_sum(None, 1, 9))    # 0
```

Mỗi hàm tiền tố đi theo **một đường** trong BST, nên thời gian `O(h+1)`, bộ nhớ phụ `O(1)`. Tổng đoạn gọi hai hàm tiền tố, vẫn **`O(h+1)`** theo bậc tăng trưởng; với BST cân bằng, là **`O(\log n)`**.

**Lưu ý quan trọng:** tổng này cộng **khóa số**. Nếu nút có `key` dùng để sắp xếp và một `weight` khác (ví dụ doanh thu), ta phải định nghĩa `total` là tổng **weight**, sau đó thay `node.key` bằng `node.weight` ở các phép tổng hợp và truy vấn tiền tố. Bất biến BST vẫn dựa trên **key**.

### 9.4. Tổng không âm có bắt buộc không?

Không. Truy vấn tổng đoạn vẫn chính xác với khóa âm hoặc trọng số âm, vì thuật toán chọn nhánh dựa trên **thứ tự khóa**, không dựa trên việc tổng là hàm tăng.

Chỉ khi ta muốn dùng tổng để tìm “vị trí đầu tiên có tổng tiền tố ít nhất `T`”, việc có các trọng số âm mới ảnh hưởng mạnh đến tính đơn điệu và thuật toán lựa chọn. Đó là **bài toán khác** và cần bất biến bổ sung nếu muốn tìm nhanh.

## 10. Xoay cây: phép biến đổi cấu trúc và metadata

### 10.1. Vì sao phải quan tâm phép xoay?

Các BST tự cân bằng như AVL hoặc Red–Black Tree dùng **xoay trái (left rotation)** và **xoay phải (right rotation)** để điều chỉnh hình dạng mà vẫn giữ thứ tự khóa.

Ví dụ xoay trái tại `x`, với `y=x.right`:

```text
Trước xoay trái:                   Sau xoay trái:

          x                               y
         / \                             / \
        A   y                           x   C
           / \                         / \
          B   C                       A   B
```

Giả định các khóa thỏa:

\[
key(A)<key(x)<key(B)<key(y)<key(C)
\]

theo nghĩa mọi khóa thuộc từng cây con nằm trong khoảng tương ứng. Phép xoay giữ nguyên thứ tự inorder:

```text
A, x, B, y, C
```

Nhưng **cây con có gốc tại `x` và tại `y` đã đổi thành phần**, nên metadata ở hai nút này có thể bị cũ.

### 10.2. Thứ tự cập nhật đúng

Ngay sau xoay trái:

- `x` trở thành con trái của `y`.
- Cây con phải của `x` trở thành `B`.
- Cây con của `x` **được xác định xong trước**.
- Metadata của `y` phụ thuộc vào metadata **mới** của `x`.

Do đó phải:

1. Cập nhật liên kết con.
2. Gọi `recompute(x)`.
3. Gọi `recompute(y)`.
4. Trả `y` làm gốc mới của cây con.

Nếu tính lại `y` **trước `x`**, `y` sẽ đọc `size/total` cũ của `x` và lưu sai.

### 10.3. Python: hai phép xoay giữ metadata

```python
def rotate_left(x):
    """Trả về gốc mới sau xoay trái tại x."""
    y = x.right
    if y is None:
        raise ValueError("không thể xoay trái nếu không có con phải")

    x.right = y.left
    y.left = x

    # Con mới của x đã ổn định, sau đó mới tính y.
    recompute(x)
    recompute(y)

    return y


def rotate_right(y):
    """Trả về gốc mới sau xoay phải tại y."""
    x = y.left
    if x is None:
        raise ValueError("không thể xoay phải nếu không có con trái")

    y.left = x.right
    x.right = y

    recompute(y)
    recompute(x)

    return x
```

Hai hàm làm việc với **một cây con** và trả gốc mới. **Mã gọi phải nối gốc mới vào cha cũ hoặc thay gốc toàn cây**, nếu không sẽ mất liên kết đúng của BST. Ví dụ:

```python
example = build_tree([8, 4, 12, 2, 6, 10, 14])

# Xoay trái tại gốc toàn cây; phải gán lại biến gốc.
example = rotate_left(example)

print(example.key)         # 12
print(example.left.key)    # 8
print(example.left.size)   # 5 (2,4,6,8,10)
print(example.left.total)  # 30
print(example.size)        # 7
print(example.total)       # 56

# Xoay phải trở về hình dạng ban đầu.
example = rotate_right(example)
print(example.key)         # 8
print(example.size)        # 7
print(example.total)       # 56
```

Với `size` và `total` được tính từ hai con, **mỗi phép xoay chỉ cần `O(1)` cập nhật metadata** tại hai nút liên quan. Đây là lý do cách tăng cường này tương thích tốt với nhiều loại BST tự cân bằng.

### 10.4. Metadata của tổ tiên có cần sửa không?

Nếu một phép xoay chỉ thay đổi **hình dạng bên trong cùng một cây con** và không thêm/xóa khóa, thì:

- **Tập khóa** và **tổng số nút** của cây con đó không thay đổi.
- `size` và `total` ở **các tổ tiên nằm ngoài cây con xoay** có thể vẫn đúng vì chúng chỉ phụ thuộc vào tập nút/tổng hợp của cây con, không phụ thuộc hình dạng nội bộ.

Tuy nhiên, nếu ta cũng lưu **chiều cao**, độ dài đường đi, khoảng cách hoặc thông tin phụ thuộc hình dạng, các tổ tiên **có thể bị ảnh hưởng**. Sau chèn/xóa và các phép cân bằng, giải pháp an toàn là tái tính các metadata liên quan theo đúng đường cập nhật và quy tắc của cấu trúc nền.

Đừng mặc định rằng “xoay cây luôn chỉ phải sửa đúng hai trường ở hai nút” cho **mọi loại metadata**. Điều đó chỉ đúng với các tổng hợp cục bộ có công thức và phạm vi ảnh hưởng phù hợp.

## 11. Xóa nút và cập nhật cây tăng cường

Xóa phức tạp hơn chèn vì phải xét các trường hợp:

1. **Xóa lá:** tháo liên kết với cha.
2. **Xóa nút có một con:** nối cha của nút bị xóa tới nút con của nó.
3. **Xóa nút có hai con:** thường dùng **nút kế nhiệm inorder** (nhỏ nhất trong cây con phải) hoặc nút tiền nhiệm inorder, rồi di chuyển/chép khóa theo thuật toán BST.

Sau mỗi trường hợp, phải cập nhật metadata tại những nút có cây con thực sự thay đổi.

### 11.1. Xóa lá

Với cây bảy nút ban đầu, xóa khóa `6`:

```text
Trước:                       Sau:

       8                         8
      / \                       / \
     4  12                     4  12
    / \                        /
   2   6                      2
```

Sau xóa:

- Metadata của nút `4` và `8` bị ảnh hưởng.
- `size(4)` từ `3` xuống `2`; `total(4)` từ `12` xuống `6`.
- `size(8)` từ `7` xuống `6`; `total(8)` từ `56` xuống `50`.
- Cây con gốc `12` không đổi.

**Không được chỉ sửa `root.size -= 1`** rồi bỏ qua metadata của các nút trung gian. Nếu làm vậy, `select_kth` có thể định hướng sai ở nút `4`.

### 11.2. Xóa nút có hai con

Nếu xóa `8` trong cây bảy khóa, một cách là lấy kế nhiệm inorder `10` (khóa nhỏ nhất trong cây con phải) để thay vị trí khóa gốc, rồi xóa nút `10` khỏi chỗ cũ.

Lúc này:

- **Khóa tại nút thay thế** đã thay đổi, ảnh hưởng `total`.
- Cây con chứa kế nhiệm cũ đã mất một nút, ảnh hưởng `size` và `total`.
- Các tổ tiên trên đường sửa cấu trúc cũng có thể bị ảnh hưởng.
- Nếu cây tự cân bằng còn có thể diễn ra một số phép xoay.

Cách cài đặt chuẩn là giữ thông tin **đường cập nhật**, hoặc cấu trúc đệ quy trả về gốc cây con mới rồi gọi `recompute` sau khi xử lý con, hoặc các cơ chế sửa metadata tương ứng của AVL/Red–Black Tree.

### 11.3. Vì sao một công thức `recompute` chung tốt hơn các phép cộng/trừ thủ công?

Với chèn lá, `size += 1` thường dễ hiểu. Nhưng với xóa nút hai con, chuyển cây con, hoặc nhiều lần xoay, cập nhật bằng phép tăng/giảm riêng lẻ rất dễ:

- Cộng/trừ hai lần cùng một nút.
- Bỏ sót một tổ tiên.
- Dùng tổng cũ của cây con đã bị thay.
- Không xử lý đúng khóa được sao chép.

**Tính lại từ hai con đúng trạng thái** thường là cách dễ chứng minh và bảo trì hơn. Không bắt buộc mỗi lần tính lại phải duyệt toàn bộ cây; với `size` và `total`, mỗi lần gọi vẫn chỉ `O(1)`.

## 12. Một ví dụ tăng cường khác: cây khoảng

Một trường hợp kinh điển là **interval tree**, thường được xây trên BST hoặc BST cân bằng với khóa là **đầu mút thấp** của mỗi khoảng.

Một nút lưu khoảng đóng:

```text
interval = [low, high], với low <= high
```

Truy vấn: tìm **một khoảng bất kỳ giao với** khoảng `[L,R]`, không nhất thiết liệt kê tất cả.

### 12.1. Định nghĩa giao nhau

Hai khoảng đóng `[a,b]` và `[c,d]` giao nhau khi và chỉ khi:

\[
a\le d \quad\text{và}\quad c\le b.
\]

Ví dụ:

- `[5,9]` giao với `[8,11]`.
- `[5,9]` **không** giao với `[10,12]`.
- `[5,9]` giao với `[9,10]` tại đúng điểm `9` nếu xét khoảng đóng.

### 12.2. Tăng cường `maxHigh`

Tại mỗi nút `u`, lưu đầu mút cao lớn nhất trong toàn bộ cây con:

\[
\operatorname{maxHigh}(\varnothing)=-\infty,
\]

\[
\operatorname{maxHigh}(u)=
\max\bigl\{high(u),\operatorname{maxHigh}(u.left),\operatorname{maxHigh}(u.right)\bigr\}.
\]

Giả sử:

```text
                [10,15]  maxHigh=30
                /                 \
       [5,8] maxHigh=12       [20,30] maxHigh=30
            \
            [7,12] maxHigh=12
```

Đây là ví dụ minh họa một BST sắp theo `low`, với giả định chính sách xử lý các `low` trùng được xác định nhất quán.

Khi hỏi khoảng `[13,17]`, nếu ở một nút có cây con trái với `maxHigh(left)<13` thì **mọi khoảng bên trái đều kết thúc trước `13`**, nên **không thể giao** với khoảng truy vấn. Ta có thể bỏ qua toàn bộ cây con trái đó.

Điều này khác BST thường: BST sắp theo `low` chưa cung cấp đủ thông tin về `high` để loại trừ một cây con nhanh theo điều kiện giao khoảng. **`maxHigh` là metadata mới tạo ra khả năng cắt nhánh.**

### 12.3. Cập nhật và điều kiện đúng

- Thêm/xóa một khoảng: cập nhật `maxHigh` trên những đường cây con bị ảnh hưởng.
- Thay đổi `high` của khoảng: tính lại nút và các tổ tiên; nếu thay đổi `low`, bất biến BST về thứ tự khóa có thể bị phá và cần thao tác thay khóa hợp lệ.
- Xoay cây: tính lại `maxHigh` ở các nút có con thay đổi, tương tự `size` và `total`.

Nếu cây nền cân bằng và mỗi `maxHigh` tính lại trong `O(1)`, các phép cập nhật metadata vẫn có chi phí theo chiều cao. Một thuật toán tìm **một** khoảng giao có thể đạt `O(\log n)` trên interval tree cân bằng với bất biến và quy tắc cắt nhánh chuẩn; **liệt kê tất cả khoảng giao** còn phải tính chi phí xuất kết quả.

**Lưu ý học thuật:** không chỉ chọn trường `maxHigh` là đủ; phải chứng minh từng nhánh bị bỏ qua **chắc chắn không chứa kết quả**. Đó là vai trò của bất biến khi thiết kế thuật toán sử dụng metadata.

## 13. Những điểm khác cần lưu ý khi tăng cường cây tổng quát

### 13.1. Nút có nhiều con

Trong cây tổng quát, công thức kích thước cây con là:

\[
size(u)=1+\sum_{v\in children(u)}size(v).
\]

Nếu `u` có `k` con, phép tính lại từ đầu cần **`O(k)`** để đi qua danh sách con.

Với một nút có hàng nghìn con, nếu chỉ thay một cây con nhỏ, việc duyệt lại toàn bộ `k` con tại mỗi cập nhật có thể đắt. Ta có thể cân nhắc:

- Lưu tổng đã tính và **điều chỉnh theo chênh lệch**, nếu thao tác gộp hỗ trợ và có thể xử lý sửa/xóa an toàn.
- Sử dụng một **cấu trúc tăng cường riêng** để quản lý danh sách con.
- Chấp nhận `O(k)` nếu số con nhỏ hoặc thao tác cập nhật hiếm.

Không thể khẳng định mọi cây tăng cường đều có chi phí tính lại **`O(1)` mỗi nút**: điều đó phụ thuộc số con, kích thước metadata và công thức kết hợp.

### 13.2. Dữ liệu có thể không dùng phép cộng đảo ngược

Với tổng, việc tính lại sau xóa có thể dùng phép trừ nếu ta biết chính xác đóng góp cũ. Nhưng với **min/max**, không thể suy ra giá trị nhỏ nhất mới chỉ bằng cách “trừ” giá trị bị xóa.

Ví dụ, cây con có các khóa `{2,5,8}` và `min=2`. Xóa `2`, để biết min mới là `5`, ta cần xem lại thông tin các con hoặc có metadata bổ sung. Vì thế không nên thiết kế một phép cập nhật chênh lệch mà chưa xác định **có phép đảo và xử lý xóa hợp lệ** hay không.

### 13.3. Lazy propagation là một cơ chế liên quan nhưng khác

Trong một số **cây đoạn (segment tree)**, ta muốn **cập nhật hàng loạt** một khoảng. Thay vì chạm ngay tới mọi lá, cấu trúc có thể lưu một **thẻ lazy** tại nút để nói rằng các phần tử trong cây con còn một phép cập nhật chưa đẩy xuống.

Đây cũng là cách lưu thêm thông tin trong cây, nhưng nó mang ý nghĩa khác với một trường tổng hợp đơn thuần:

- `sum` mô tả **kết quả đã tổng hợp** của cây con.
- `lazy_tag` mô tả **một phép cập nhật đang chờ áp dụng xuống các con**.

Muốn đúng phải duy trì bất biến giữa tổng hợp và thẻ chờ, có các thao tác **apply/push/pull** rõ ràng. Không thể chỉ thêm một trường `lazy` rồi bỏ qua việc cập nhật con trước khi đọc. Bài hiện tại tập trung vào **nguyên tắc tăng cường và bảo trì metadata**, không thay thế hướng dẫn về toàn bộ thuật toán lazy propagation.

### 13.4. Metadata phụ thuộc hình dạng và metadata phụ thuộc tập dữ liệu

Phân biệt:

- **Phụ thuộc tập nút trong cây con:** `size`, `total`, giá trị min/max; khi xoay mà không thay tập nút toàn cây con, tổng hợp ở gốc cây con giữ cùng giá trị.
- **Phụ thuộc hình dạng:** chiều cao, đường kính, số độ sâu hoặc thông tin theo đường đi; xoay có thể làm thay đổi các giá trị này dù tập khóa không đổi.

Cùng là “lưu thông tin phụ” nhưng **phạm vi ảnh hưởng khi xoay** khác nhau. Phải xác định loại nào trước khi tối ưu thao tác cập nhật.

## 14. Chứng minh tính đúng bằng bất biến và quy nạp cấu trúc

Để thấy một cây tăng cường đáng tin cậy, không chỉ kiểm tra vài đầu vào mẫu. Ta cần lý giải vì sao **mọi trạng thái hợp lệ** đều giữ metadata chính xác.

### 14.1. Tính đúng sau khi xây từ cây rỗng

Với `Node(key)` mới:

\[
size=1,\qquad total=key.
\]

Điều này đúng vì cây con có đúng một nút.

Giả sử hai cây con `left`, `right` đã có metadata đúng. Khi gắn vào `u` rồi gọi `recompute(u)`:

\[
u.size=1+size(left)+size(right)
\]

đúng bằng số nút của cây con mới; và:

\[
u.total=key(u)+total(left)+total(right)
\]

đúng bằng tổng khóa của cây con mới.

Suy ra tính đúng bằng **quy nạp theo cấu trúc cây**.

### 14.2. Tính đúng sau chèn

Khi chèn một nút lá mới vào BST:

1. Nút mới có metadata đúng.
2. Những cây con **không nằm trên đường tới vị trí chèn** không đổi.
3. Tại cha của nút mới, hai cây con đã đúng, nên `recompute` làm cha đúng.
4. Lặp lập luận **từ dưới lên** tới gốc.

Vậy mọi nút tiếp tục có `size` và `total` đúng.

### 14.3. Tính đúng sau xoay

Sau xoay trái, hai nút `x`, `y` đổi liên kết:

1. Các cây con `A,B,C` nội bộ không đổi và metadata của chúng vẫn đúng.
2. `x` có hai con mới `A,B`, nên `recompute(x)` cho giá trị đúng.
3. `y` nay có con trái `x` đã đúng và con phải `C` đã đúng, nên `recompute(y)` cho giá trị đúng.
4. Những nút ngoài vùng xoay chỉ cần cập nhật nếu metadata/đường cấu trúc của chúng thực sự thay đổi.

**Thứ tự gọi là một phần của chứng minh**; đổi sang `recompute(y)` trước có thể làm lập luận sai.

### 14.4. Tính đúng của truy vấn tăng cường

Với `select_kth` và `rank_lt`, mỗi bước dựa trên hai bất biến:

- **BST:** mọi khóa bên trái nhỏ hơn khóa hiện tại, bên phải lớn hơn.
- **Size:** `size(left)` là số khóa chính xác của cây con trái.

Với `range_sum`, còn cần:

- **Total:** `total(left)` là tổng khóa chính xác của toàn bộ cây con trái.

Nếu một trong hai nhóm bất biến sai, phép bỏ qua nguyên cây con có thể trả kết quả sai. Vì vậy, **chứng minh thuật toán truy vấn và chứng minh bảo trì metadata phải đi cùng nhau**.

## 15. Phân tích chi phí và đánh đổi thiết kế

Gọi:

- `n`: số nút trong cây.
- `h`: chiều cao cây theo số cạnh.
- `q`: số truy vấn dự kiến.
- Giả định kích thước metadata mỗi nút là **`O(1)`**, phép gộp cục bộ **`O(1)`**.

### 15.1. Bảng chi phí với BST tăng cường

| Thao tác | BST nền không cân bằng | BST tự cân bằng, duy trì augmentation |
|---|---|---|
| Xây metadata cho một cây đã có bằng postorder | `O(n)` | `O(n)` |
| Chèn/xóa và cập nhật metadata | `O(h+1)`, xấu nhất `O(n)` | Thường `O(\log n)` nếu mọi thay đổi và xoay được xử lý đúng |
| Tính lại metadata tại một nút | `O(1)` | `O(1)` |
| Xoay trái/phải, cập nhật `size/total` cục bộ | `O(1)` | `O(1)` |
| `select_kth` | `O(h+1)` | `O(\log n)` |
| `rank_lt` | `O(h+1)` | `O(\log n)` |
| `range_sum` bằng hai tiền tố | `O(h+1)` | `O(\log n)` |
| Bộ nhớ metadata `size` và `total` | `O(n)` | `O(n)` |

Một cây tăng cường **không tự động trở thành cân bằng**. Nếu gắn hai trường `size`, `total` vào một BST suy biến, `select_kth` vẫn có thể đi qua `n` nút trong trường hợp xấu nhất. Việc metadata giúp **bỏ qua cây con** không thể cứu được đường đi dài khi hình dạng kém.

### 15.2. Vì sao đánh đổi thường đáng giá?

Giả sử cần `q` truy vấn chọn phần tử thứ `k` trên một BST đã cân bằng:

- Không lưu `size`: có thể phải thực hiện duyệt inorder hoặc công việc tính thứ hạng lại từ đầu, tới **`O(n)` mỗi truy vấn**.
- Có `size`: mỗi truy vấn đi theo một đường, **`O(\log n)`**.
- Đổi lại: **một trường metadata mỗi nút** và chi phí cập nhật đường đi sau mỗi thay đổi.

Nếu `q` lớn và cập nhật ít, lợi ích có thể rất đáng kể. Nếu cây rất nhỏ, truy vấn hiếm, hoặc metadata đắt cập nhật, lựa chọn **tính theo yêu cầu** có thể đơn giản hơn và tránh lỗi cache.

### 15.3. Không bỏ qua chi phí bổ sung khác

Ngoài Big-O, hệ thống thực tế cần xét:

- **Kích thước trường:** đếm nút có thể tràn kiểu số nguyên giới hạn; tổng khóa cũng có thể tràn hoặc chịu sai số số thực.
- **Thay đổi đồng thời:** một truy vấn nhìn thấy `size` của nút cha mới nhưng của con còn cũ có thể sai; cần khóa/phiên bản/snapshot nhất quán.
- **Bộ nhớ cache CPU:** thêm metadata làm đối tượng nút lớn hơn, ảnh hưởng locality.
- **Độ phức tạp triển khai:** càng nhiều trường cần đồng bộ, càng nhiều trường hợp chỉnh sửa phải xử lý.
- **Tần suất thao tác:** truy vấn nhanh có ích nếu số truy vấn đủ lớn để bù chi phí cập nhật và bộ nhớ.

## 16. Kiểm tra tính nhất quán của metadata

Một cách kiểm tra phục vụ học tập là **tính lại giá trị đúng từ dữ liệu thật** trên toàn bộ cây rồi so với các trường đã lưu. Lúc kiểm tra không tin vào metadata đang có.

### 16.1. Hàm kiểm tra tổng hợp

```python
def validate_metadata(root):
    """Kiểm tra size/total của mọi nút; giả định cây nền hợp lệ.

    Dùng hậu thứ tự lặp để không phụ thuộc độ sâu đệ quy.
    """
    if root is None:
        return True

    actual = {}
    frames = [(root, False)]

    while frames:
        node, ready = frames.pop()

        if ready:
            left_size, left_total = actual.get(node.left, (0, 0))
            right_size, right_total = actual.get(node.right, (0, 0))

            expected_size = 1 + left_size + right_size
            expected_total = (
                node.key + left_total + right_total
            )

            if node.size != expected_size:
                return False
            if node.total != expected_total:
                return False

            actual[node] = (expected_size, expected_total)
        else:
            frames.append((node, True))
            if node.right is not None:
                frames.append((node.right, False))
            if node.left is not None:
                frames.append((node.left, False))

    return True


tree = build_tree([8, 4, 12, 2, 6, 10, 14])

assert validate_metadata(tree)

tree.left.size = 99
assert not validate_metadata(tree)

# Khôi phục từ cấu trúc thật; hai con của tree.left vẫn đúng.
recompute(tree.left)
assert validate_metadata(tree)
```

Hàm sử dụng **`O(n)` thời gian** và **`O(n)` bộ nhớ phụ** để lưu giá trị độc lập của mọi cây con. Đây là **hàm kiểm tra**, không dùng trong đường cập nhật thường xuyên nếu muốn giữ `O(\log n)`.

**Phạm vi kiểm tra:** hàm này giả định cấu trúc đã là một cây nhị phân hợp lệ và không có chu trình/nút dùng chung. Muốn kiểm tra cả **bất biến BST** và **không chu trình**, phải có thêm bước xác thực khóa và định danh nút. Metadata đúng **không đủ** chứng minh cây là BST.

### 16.2. Những trường hợp biên cần tự kiểm tra

```python
# Cây rỗng
assert size_of(None) == 0
assert total_of(None) == 0
assert validate_metadata(None)

# Một nút
single = Node(7)
assert single.size == 1
assert single.total == 7
assert select_kth(single, 1) == 7
assert rank_lt(single, 7) == 0
assert range_sum(single, 7, 7) == 7

# Khóa âm vẫn được tính đúng
negative = build_tree([0, -5, 8])
assert size_of(negative) == 3
assert total_of(negative) == 3
assert rank_lt(negative, 0) == 1
assert range_sum(negative, -5, 0) == -5

# Chèn khóa trùng không tăng size/total
root_dup = build_tree([4, 2, 6])
root_dup, inserted = insert(root_dup, 4)
assert not inserted
assert root_dup.size == 3
assert root_dup.total == 12

# Chọn k ngoài phạm vi phải báo lỗi rõ ràng
try:
    select_kth(root_dup, 4)
except IndexError:
    pass
else:
    raise AssertionError("k vượt số phần tử phải bị từ chối")
```

Những `assert` là ví dụ cho người học thực hành, không thay thế các phép kiểm thử hệ thống sau này. Một hệ thống dữ liệu lớn còn cần xem xét giới hạn số học, trường hợp khóa/payload thay đổi và tương tác đồng thời.

## 17. Các lỗi thiết kế và cài đặt thường gặp

1. **Lưu metadata nhưng không định nghĩa bất biến.** Phải viết chính xác trường đó biểu diễn gì và tính trên cây con nào.
2. **Nhầm `size` với số con trực tiếp.** `size(u)` đếm **toàn bộ nút trong cây con**, kể cả `u`.
3. **Quên giá trị ở cây rỗng.** Với `size` và `total` là `0`; với `maxHigh` có thể cần `-\infty`.
4. **Cập nhật cha trước con.** Nếu metadata con còn cũ, công thức gộp tại cha sẽ sai.
5. **Chèn thành công nhưng chỉ cập nhật gốc.** Những nút trung gian vẫn cần metadata đúng để `select`/`rank` điều hướng.
6. **Chèn khóa trùng rồi vẫn tăng `size`.** Nếu chính sách BST không thêm khóa trùng, metadata phải giữ nguyên.
7. **Coi tăng cường cây là một cơ chế tự cân bằng.** Metadata không làm chiều cao thấp; phải chọn cây nền cân bằng nếu cần chặn trên logarit.
8. **Sửa khóa tại chỗ mà không xét bất biến BST.** Thay khóa có thể yêu cầu xóa/chèn hoặc tái cấu trúc, không chỉ tính lại tổng.
9. **Xóa nút hai con mà quên cập nhật đường kế nhiệm.** Phải xử lý mọi nút bị thay đổi cây con.
10. **Xoay cây rồi quên `recompute`.** Liên kết khóa có thể đúng nhưng `size`/`total` sai.
11. **Xoay trái và tính `y` trước `x`.** `y` phụ thuộc metadata mới của `x`; thứ tự đảo ngược dễ dùng giá trị cũ.
12. **Quên gắn gốc cây con mới sau phép xoay vào cha hoặc gốc toàn cây.** Trả nút mới nhưng không nối liên kết sẽ phá cấu trúc cây.
13. **Dùng `total(left)` như thể nó là tổng toàn cây.** Metadata tại mỗi nút chỉ tính trong **cây con của chính nút đó**.
14. **Dùng `prefix_sum_le(R)-prefix_sum_le(L)` cho đoạn đóng `[L,R]`.** Công thức này bỏ mất khóa đúng bằng `L`; cần trừ tiền tố có khóa **nhỏ hơn `L`**.
15. **Dựa vào tổng tiền tố là hàm tăng khi khóa/trọng số có thể âm.** Phải chứng minh tính đơn điệu trước khi dùng phép tìm theo ngưỡng tổng.
16. **Dùng các phép tổng hợp không `O(1)` rồi kết luận cập nhật `O(\log n)`.** Chi phí gộp có thể tăng theo kích thước metadata hoặc số con.
17. **Coi min/max có thể được trừ đi như tổng.** Xóa phần tử cực trị có thể phải tìm lại cực trị từ các con.
18. **Chỉ kiểm tra metadata mà bỏ qua bất biến BST.** Cache đúng trên một cây có khóa sai thứ tự vẫn không làm `rank` đúng.
19. **Áp dụng công thức cho khóa trùng mà không có chính sách trùng.** Dùng số đếm tại nút hoặc cách lưu cụ thể, rồi sửa `size` và `rank` cho nhất quán.
20. **Quên dữ liệu payload khác khóa.** Nếu tổng yêu cầu tính trọng số, phải gộp `weight`, không cộng `key` chỉ vì code ví dụ làm vậy.
21. **Truy vấn trong lúc cập nhật chưa xong.** Có thể quan sát metadata và liên kết không cùng một phiên bản; cần đồng bộ hoặc snapshot.
22. **Không phân biệt bộ nhớ cây nền và bộ nhớ bổ sung.** Mỗi trường metadata thêm một khoản `O(n)`, dù Big-O tổng vẫn là `O(n)`.
23. **Tin rằng chiều cao AVL/Red–Black Tree tự được duy trì khi chỉ copy đoạn code BST thường.** Phải tích hợp augmentation vào đúng thuật toán cân bằng hoàn chỉnh.
24. **Dùng hàm validate `O(n)` sau từng phép chèn trong mã chạy thực tế rồi vẫn tuyên bố tổng cập nhật `O(\log n)`.** Validation toàn cây là bước kiểm tra riêng, không tính là đường cập nhật tối ưu.

## 18. Bài tập thực hành có đáp án

### Bài 1. Nhận diện thông tin phụ

Một BST lưu `key, left, right, size`. Giá trị `size(u)` là gì? Nếu `u` là lá thì bằng bao nhiêu?

**Đáp án:** `size(u)` là số **nút trong toàn bộ cây con có gốc tại `u`**, kể cả nút `u`. Với lá, `size(u)=1`. Với cây con rỗng, `size(None)=0`.

### Bài 2. Tính kích thước nút trong

BST gốc `8` có hai cây con lần lượt chứa `3` và `5` nút. `size(8)` bằng bao nhiêu?

**Đáp án:** `size(8)=1+3+5=9`.

### Bài 3. Tổng cây con

Trong cây mẫu bảy khóa `2,4,6,8,10,12,14`, hãy tính `total` tại nút `4` và gốc `8`.

**Đáp án:** `total(4)=2+4+6=12`. `total(8)=2+4+6+8+10+12+14=56`.

### Bài 4. Truy vết chèn khóa `5`

Từ cây mẫu bảy nút, chèn khóa `5` theo quy tắc BST. Những nút nào cần tính lại metadata, theo thứ tự từ dưới lên?

**Đáp án:** Thêm `5` làm con trái của `6`. Tính lại **`6 → 4 → 8`**. Tổng mới tại gốc là `61`, kích thước mới là `8`.

### Bài 5. Chọn khóa thứ `k`

Với cây bảy khóa `[2,4,6,8,10,12,14]`, tính `select_kth(root,2)`, `select_kth(root,4)` và `select_kth(root,7)`.

**Đáp án:** Lần lượt là **`4,8,14`**, theo thứ hạng đánh từ `1`.

### Bài 6. Rank với khóa không tồn tại

Trên cây mẫu, `rank_lt(9)` bằng bao nhiêu? `9` có bắt buộc nằm trong cây không?

**Đáp án:** `rank_lt(9)=4` vì các khóa nhỏ hơn `9` là `2,4,6,8`. Khóa truy vấn **không cần tồn tại**.

### Bài 7. Tổng đoạn đóng

Tính `range_sum(root,5,12)` trên cây bảy khóa. Giải thích vì sao không trừ `prefix_sum_le(5)`.

**Đáp án:** Các khóa thuộc `[5,12]` là `6,8,10,12`, tổng **`36`**. Công thức là `prefix_sum_le(12)-prefix_sum_lt(5)`; nếu trừ tiền tố “`≤5`” trong trường hợp khóa `5` hiện diện thì vô tình loại nó khỏi tổng đoạn.

### Bài 8. Cây rỗng và cây một nút

Với cây rỗng, `size` và `total` bằng gì? Với cây một nút khóa `-3` thì sao?

**Đáp án:** Cây rỗng có `size=0`, `total=0`. Nút `-3` có `size=1`, `total=-3`.

### Bài 9. Metadata đúng nhưng BST sai

Một cây nhị phân có các trường `size` và `total` tính đúng, nhưng nút `20` nằm trong cây con trái của gốc `8`. Có thể dùng `rank_lt` theo thuật toán bài này không?

**Đáp án:** **Không.** Metadata đúng chưa đủ: `rank` còn phụ thuộc bất biến BST rằng **mọi khóa bên trái nhỏ hơn khóa gốc**. Cây đang vi phạm điều kiện đó.

### Bài 10. Xoay trái

Trước xoay trái tại `x` có con phải `y`, với `y.left=B`. Sau xoay, `x.right` và `y.left` phải trỏ tới đâu?

**Đáp án:** `x.right=B` và `y.left=x`. Sau sửa liên kết, gọi `recompute(x)` **trước**, rồi `recompute(y)`; trả `y` là gốc cây con mới.

### Bài 11. Bộ nhớ tăng cường

Một BST có `n` nút, mỗi nút bổ sung hai số cố định `size` và `total`. Bộ nhớ bổ sung theo Big-O là bao nhiêu?

**Đáp án:** Hai trường mỗi nút cần thêm **`O(n)` bộ nhớ**. Tổng bộ nhớ lưu cây vẫn thuộc **`O(n)`**, nhưng hằng số thực tế tăng.

### Bài 12. Cân bằng có bắt buộc không?

Một BST có lưu `size` nhưng được tạo bằng cách chèn tuần tự `1,2,3,\ldots,n` và không tái cân bằng. Có thể bảo đảm `select_kth` mất `O(\log n)` không?

**Đáp án:** **Không.** Cây có thể suy biến thành đường thẳng với `h=n-1`. Truy vấn đi theo đường có thể mất **`O(n)`**. Tăng cường không thay thế cân bằng cây.

### Bài 13. Cây khoảng

Trong interval tree, vì sao nên lưu `maxHigh` của mỗi cây con? Nếu `maxHigh(left)<L` đối với truy vấn `[L,R]`, có thể kết luận gì?

**Đáp án:** `maxHigh` giúp biết đầu mút cao nhất trong cây con để loại những nhánh **chắc chắn không giao** với khoảng truy vấn. Nếu `maxHigh(left)<L`, mọi khoảng bên trái kết thúc trước `L`, nên **cây con trái không có khoảng giao với `[L,R]`**.

### Bài 14. Nút nhiều con

Một cây tổng quát có nút `u` với `1000` con; `size(u)=1+\sum size(child)`. Nếu không có bộ đếm tổng phụ hoặc cơ chế cập nhật gia tăng, tính lại `size(u)` từ đầu mất bao lâu?

**Đáp án:** Phải xem `1000` con, tổng quát **`O(k)`** với `k` là số con của `u`. Không thể mặc định là `O(1)` chỉ vì metadata tên là `size`.

### Bài 15. Phép gộp không đảo được

Một cây lưu `min` của toàn bộ cây con. Nếu xóa đúng phần tử đang là giá trị min, có thể chỉ “trừ giá trị bị xóa” để lấy min mới không?

**Đáp án:** **Không.** Phép `min` không có cách trừ tương ứng như tổng. Cần tính lại từ metadata các con hoặc dùng cấu trúc bổ sung thích hợp.

### Bài 16. Tổng trọng số thay vì tổng khóa

Một cây tìm kiếm sắp theo `employee_id` nhưng cần truy vấn tổng `salary` trên các khoảng ID. Metadata `total` tại nút nên cộng gì?

**Đáp án:** Cộng **`salary(u)`** cùng tổng lương của hai cây con, trong khi bất biến BST và điều kiện đi nhánh vẫn xét theo **`employee_id`**. Phải phân biệt **khóa sắp xếp** với **giá trị cần tổng hợp**.

### Bài 17. Phân biệt `sum` và `lazy`

Trong cây đoạn, trường `sum` và một thẻ `lazy_add` mang hai ý nghĩa gì?

**Đáp án:** `sum` mô tả giá trị tổng hợp của đoạn tại nút; `lazy_add` mô tả phép cộng còn **chờ đẩy xuống cây con**. Phải phối hợp thao tác apply/push/pull đúng; không thể coi thẻ lazy chỉ là một bản sao của tổng.

### Bài 18. Chọn khi truy vấn nhiều và cập nhật ít

Một ứng dụng có BST cân bằng với hàng triệu truy vấn xếp hạng nhưng rất ít cập nhật. Có nên lưu `size` trên mỗi nút hay duyệt inorder lại mỗi lần?

**Đáp án:** Thường nên lưu `size`: mỗi truy vấn rank/select đi theo một đường dài **`O(\log n)`**, thay vì tính lại thứ hạng bằng duyệt tới **`O(n)`**. Đổi lại phải giữ metadata nhất quán sau mỗi cập nhật và chấp nhận bộ nhớ thêm.

### Bài 19. Kiểm tra mã xác thực

Nếu `validate_metadata(root)` trả `True`, có thể kết luận cây chắc chắn không có chu trình và là BST hợp lệ không?

**Đáp án:** **Không.** Hàm được viết dưới **giả định cây nền hợp lệ**. Nó chỉ kiểm tra `size` và `total`. Muốn kết luận toàn bộ cấu trúc hợp lệ, phải kiểm tra thêm liên kết/chu trình và bất biến khóa.

### Bài 20. Chi phí một phép xoay

Với metadata `size` và `total` có thể tính bằng `O(1)` từ hai con, chi phí cập nhật metadata của một phép xoay trái/phải đơn lẻ là bao nhiêu?

**Đáp án:** **`O(1)`**, vì chỉ cần tính lại hai nút ở vùng xoay theo thứ tự đúng. Chi phí của **toàn bộ một phép chèn/xóa có cân bằng** còn gồm tìm vị trí, cập nhật tổ tiên và các bước cân bằng, thường `O(\log n)` trên cây cân bằng.

### Bài 21. Tính đúng bằng quy nạp

Vì sao tính lại metadata theo thứ tự **con trước, cha sau** làm `size` đúng cho mọi nút?

**Đáp án:** Nút lá có `size=1`. Giả sử `size` hai cây con đã đúng, khi đó `1+size(left)+size(right)` đúng bằng số nút trong cây con gốc cha. Áp dụng lập luận **quy nạp từ lá lên gốc** cho toàn cây.

### Bài 22. Chọn không lưu cache

Nếu cây rất nhỏ, hiếm khi thực hiện truy vấn tổng cây con, nhưng thường xuyên đổi cấu trúc phức tạp, khi nào nên cân nhắc **không** lưu `total`?

**Đáp án:** Khi chi phí triển khai, cập nhật và kiểm soát tính nhất quán của cache lớn hơn chi phí đôi khi duyệt cây để tính tổng. Tăng cường là **đánh đổi**, không phải tối ưu bắt buộc trong mọi hệ thống.

## 19. Tổng kết

**Tăng cường cây** nghĩa là giữ một **cây nền** với các bất biến vốn có, đồng thời lưu thêm **metadata tại nút** để trả lời một số truy vấn nhanh hơn. Một thiết kế thành công phải có:

1. **Truy vấn cụ thể** cần tăng tốc.
2. **Định nghĩa toán học** rõ ràng cho metadata và trường hợp cây rỗng.
3. **Công thức gộp cục bộ** từ dữ liệu nút và thông tin của các cây con.
4. **Quy tắc bảo trì** khi chèn, xóa, thay khóa/dữ liệu, xoay hoặc tái cấu trúc.
5. **Chứng minh bất biến** và phân tích đầy đủ thời gian–bộ nhớ của chính cấu trúc nền.

Với BST lưu `subtree size` và `subtree total`, ta có thể thực hiện **select theo thứ hạng**, **rank**, **tổng tiền tố/tổng đoạn** bằng cách đi theo một đường trên cây: `O(h+1)` thời gian, trở thành `O(\log n)` nếu cây được cân bằng phù hợp. Các phép xoay có thể giữ metadata chính xác bằng cách tính lại các nút có liên kết con thay đổi **theo thứ tự từ dưới lên**.

Thông tin phụ không tự biến cây suy biến thành cân bằng, không tự sửa một bất biến khóa bị phá, và không miễn phí: nó tốn thêm bộ nhớ cùng công sức cập nhật. Điều cần nhớ nhất là **không chỉ thêm trường vào nút, mà phải biến công thức duy trì trường ấy thành một phần của mọi thao tác sửa cây**. Khi làm được điều đó, ta có thể mở rộng một cây nền thành cấu trúc phục vụ đúng những truy vấn chuyên biệt mà không phải tính lại toàn bộ dữ liệu mỗi lần.

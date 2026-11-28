# Biểu diễn cây tổng quát bằng danh sách con hoặc con đầu–anh em kế

## 1. Bài toán: lưu một cây có số con không cố định

Trong học phần **Cấu trúc dữ liệu**, cây (*tree*) được sử dụng để mô tả thư mục, mục lục, cấu trúc tổ chức, cây phân tích cú pháp, danh mục nội dung và nhiều quan hệ phân cấp. Mỗi nút có thể có **không con, một con hoặc rất nhiều con**. Đó là đặc điểm của **cây tổng quát có gốc** (*general rooted tree*), khác với cây nhị phân, nơi mỗi nút có tối đa hai vị trí con trái và phải.

Giả sử một hệ thống học trực tuyến có:

```text
                             A
                          /  |  \
                         B   C   D
                        / \  |  / \
                       E   F G H   I
                           |
                           J

A: khóa học
B, C, D: các chương
E, F, G, H, I, J: các mục nội dung ở những cấp khác nhau
```

Trong hình, `A` có ba con, nên không thể biểu diễn trực tiếp cây này bằng mô hình **con trái–con phải mang nghĩa con trực tiếp** của một cây nhị phân thông thường.

Hai cách lưu trữ phổ biến là:

1. **Danh sách con (children list):** mỗi nút chứa một danh sách tham chiếu tới tất cả con trực tiếp.
2. **Con đầu–anh em kế (first-child/next-sibling, hay left-child/right-sibling — LCRS):** mỗi nút chỉ cần hai liên kết cấu trúc, một tới **con đầu tiên** và một tới **anh em kế tiếp**.

Cả hai đều có thể biểu diễn cùng **một cây tổng quát có thứ tự**. Sự khác biệt nằm ở cách tìm con thứ `k`, thêm hoặc xóa con, quản lý bộ nhớ và duy trì các **bất biến liên kết**.

Mục tiêu của bài là hiểu cấu trúc của hai phương án, viết thuật toán chuyển đổi và duyệt cây, phân tích thời gian/bộ nhớ, rồi lựa chọn phương án phù hợp với yêu cầu ứng dụng.

## 2. Các khái niệm và bất biến phải giữ

### 2.1. Cây có gốc và thứ tự các con

Cây có gốc không rỗng gồm một **gốc** `r` và các quan hệ **cha–con**:

- Gốc **không có cha**.
- Mỗi nút khác gốc có **đúng một cha trực tiếp**.
- Mọi nút có đường đi từ gốc.
- Không có chu trình cha–con.
- Nếu có `n≥1` nút thì có **`n-1` cạnh** cha–con.

**Nút lá** là nút không có con; **nút trong** là nút có ít nhất một con. **Anh em** là các nút khác nhau có cùng cha.

Trong bài này, các con được xem là **có thứ tự** (*ordered tree*): danh sách `[B,C,D]` là một thứ tự khác `[D,C,B]`. Đây là yêu cầu tự nhiên đối với mục lục, menu và thứ tự xuất hiện của các phần trong cú pháp.

Một cây **không có thứ tự** (*unordered tree*) cũng có thể biểu diễn bằng hai phương án trên, nhưng khi đó thứ tự danh sách/chuỗi anh em chỉ là một lựa chọn cài đặt, không phải thông tin phải bảo toàn về mặt ngữ nghĩa.

### 2.2. Cây ví dụ dùng xuyên suốt

Để các phép duyệt và mã Python nhất quán, ta chọn đúng **10 nút**:

```text
Tập nút: A, B, C, D, E, F, G, H, I, J

Danh sách cạnh cha → con, theo thứ tự:
A→B, A→C, A→D
B→E, B→F
C→G
D→H, D→I
F→J

Có 9 cạnh = 10 - 1.
```

Bảng quan hệ:

| Nút | Cha trực tiếp | Các con theo thứ tự | Số con |
|---|---|---|---:|
| `A` | Không có | `B, C, D` | 3 |
| `B` | `A` | `E, F` | 2 |
| `C` | `A` | `G` | 1 |
| `D` | `A` | `H, I` | 2 |
| `E` | `B` | Rỗng | 0 |
| `F` | `B` | `J` | 1 |
| `G` | `C` | Rỗng | 0 |
| `H` | `D` | Rỗng | 0 |
| `I` | `D` | Rỗng | 0 |
| `J` | `F` | Rỗng | 0 |

Ta dùng quy ước **độ sâu gốc bằng `0`** và **độ sâu là số cạnh từ gốc tới nút**. Trong hình, `J` ở độ sâu `3`, còn `G,H,I` ở độ sâu `2`.

### 2.3. Bất biến quan trọng khi lưu cây

Bất kể cách biểu diễn nào, hệ thống cần bảo đảm:

1. Một nút **không được xuất hiện trong hai cây con khác nhau** của cùng cấu trúc cây; mỗi nút không phải gốc có một cha.
2. Một nút không được trở thành con/hậu duệ của chính nó theo chu trình.
3. Thứ tự con phải thống nhất nếu ứng dụng yêu cầu cây **có thứ tự**.
4. Mỗi cạnh cha–con xuất hiện đúng một lần trong biểu diễn hướng xuống.
5. Nếu có lưu thêm tham chiếu cha, nó phải phù hợp với liên kết hướng xuống.

**Không nên kiểm tra tính đúng chỉ bằng số cạnh.** Một tập liên kết có `n-1` cạnh vẫn có thể có chu trình trong một thành phần và một nút bị cô lập ở thành phần khác. Cần kiểm tra thêm tính liên thông từ gốc và việc không có nút lặp.

## 3. Phương án 1: mỗi nút chứa một danh sách con

### 3.1. Cấu trúc dữ liệu

Ta dùng một đối tượng nút với:

- `value`: dữ liệu.
- `children`: danh sách các nút con, theo thứ tự.
- `parent`: liên kết **tùy chọn** tới cha, giúp đi ngược về gốc nhanh hơn.

```text
┌────────────────────────────┐
│ Node(A)                    │
│ value = A                  │
│ parent = None              │
│ children = [B, C, D]       │
└────────────────────────────┘
           │  │  │
           ▼  ▼  ▼
           B  C  D

Node(B).children = [E, F]
Node(C).children = [G]
Node(D).children = [H, I]
Node(F).children = [J]
```

Cách lưu này rất trực quan: `children[u][i]` là **con ở vị trí thứ `i`** của nút `u` (đánh chỉ số từ `0`), nếu vị trí đó tồn tại.

Khi dùng danh sách động của Python:

- `len(u.children)`: thời gian **`O(1)`**.
- `u.children[i]` khi biết chỉ số hợp lệ: **`O(1)`**.
- Liệt kê `k` con: **`O(k)`**.
- Thêm con cuối bằng `append`: **`O(1)` trung bình phân bổ**, chưa tính kiểm tra hợp lệ.
- Chèn hoặc xóa ở giữa danh sách: có thể **`O(k)`**, vì phải dời phần tử.
- Bộ nhớ chứa tham chiếu con: tổng cộng **`n-1` mục**, nên **`O(n)`**.

Phần lớn trình bày sau sẽ dùng danh sách con để xây một cây mẫu, rồi chuyển đổi sang con đầu–anh em kế.

### 3.2. Lớp nút và thao tác gắn có kiểm tra

Các nút Python dưới đây sử dụng **định danh đối tượng** (so sánh `is`) để kiểm tra quan hệ. Hai nút có cùng `value` vẫn có thể là hai nút khác nhau.

```python
class ListNode:
    def __init__(self, value):
        self.value = value
        self.parent = None
        self.children = []


def attach_list_child(parent, child, index=None):
    """Gắn gốc một cây con rời vào parent.

    index=None: thêm cuối.
    index=i: chèn vào vị trí i trong danh sách con.
    """
    if not isinstance(parent, ListNode):
        raise TypeError("parent phải là ListNode")
    if not isinstance(child, ListNode):
        raise TypeError("child phải là ListNode")
    if child.parent is not None:
        raise ValueError("child đã có cha")

    # Nếu parent nằm trong cây con child, việc gắn sẽ tạo chu trình.
    cursor = parent
    while cursor is not None:
        if cursor is child:
            raise ValueError("không thể tạo chu trình")
        cursor = cursor.parent

    if index is None:
        parent.children.append(child)
    else:
        if not isinstance(index, int):
            raise TypeError("index phải là số nguyên")
        if not 0 <= index <= len(parent.children):
            raise IndexError("vị trí chèn không hợp lệ")
        parent.children.insert(index, child)

    child.parent = parent
```

Điều kiện `child.parent is None` nói rằng `child` hiện là **gốc của một cây riêng**. Hàm không tự chuyển một nút đã có cha, bởi việc đó phải xóa liên kết với cha cũ trước và có thể thay đổi độ sâu, kích thước các cây con.

Vòng đi qua `parent` từ `parent` dự kiến lên tới gốc ngăn việc gắn một **tổ tiên** xuống làm con của hậu duệ. Ví dụ, nếu `B` đang là tổ tiên của `F`, không được gắn `B` làm con của `F`.

### 3.3. Tạo cây ví dụ

```python
def build_list_tree():
    nodes = {name: ListNode(name) for name in "ABCDEFGHIJ"}

    for p, c in [
        ("A", "B"), ("A", "C"), ("A", "D"),
        ("B", "E"), ("B", "F"),
        ("C", "G"),
        ("D", "H"), ("D", "I"),
        ("F", "J"),
    ]:
        attach_list_child(nodes[p], nodes[c])

    return nodes["A"], nodes


list_root, list_nodes = build_list_tree()

print([x.value for x in list_root.children])
# ['B', 'C', 'D']

print([x.value for x in list_nodes["B"].children])
# ['E', 'F']

print(list_nodes["J"].parent.value)
# F
```

Mỗi liên kết cha–con được lưu ở cả `children` của cha và `parent` của con. Với cây mẫu có `10` nút, có đúng `9` tham chiếu `parent` khác `None` và `9` mục con tính trên tất cả danh sách.

## 4. Phương án 2: con đầu–anh em kế (LCRS)

### 4.1. Chỉ dùng hai liên kết cấu trúc cho mọi số con

Trong mô hình **first-child/next-sibling**:

- `first_child` của nút `u` trỏ tới **con đầu tiên** của `u`, hoặc `None` nếu `u` là lá.
- `next_sibling` của nút `v` trỏ tới **anh em liền sau** `v` trong danh sách các con của **cùng một cha**, hoặc `None` nếu `v` là anh em cuối.
- Có thể thêm `parent` để đi từ nút lên cha trong `O(1)`; trường này không bắt buộc cho việc duyệt xuống.

Thay vì `A.children=[B,C,D]`, ta lưu:

```text
A.first_child ──► B ──next_sibling──► C ──next_sibling──► D
                                                            │
                                                   next_sibling=None

B.first_child ──► E ──next_sibling──► F
C.first_child ──► G
D.first_child ──► H ──next_sibling──► I
F.first_child ──► J
```

**Cực kỳ quan trọng:** `C` là **anh em** của `B`, không phải con của `B`. Liên kết `B.next_sibling=C` không phải cạnh cha–con trong cây tổng quát.

Mô hình còn được gọi là **left-child/right-sibling (LCRS)** vì hai liên kết có thể mang tên `left` và `right` trong một biểu diễn dạng cây nhị phân. Nhưng khi dịch ngược về cây tổng quát:

- `left` tương đương `first_child`.
- `right` tương đương `next_sibling`, **không phải con phải trực tiếp** của nút đang xét.

Đây là **phép mã hóa cấu trúc** bằng hai liên kết, không phải lời khẳng định cây tổng quát bỗng trở thành một cây nhị phân cùng quan hệ cha–con.

### 4.2. Bảng liên kết của cây ví dụ

| Nút | `first_child` | `next_sibling` | `parent` nếu lưu |
|---|---|---|---|
| `A` | `B` | `None` | `None` |
| `B` | `E` | `C` | `A` |
| `C` | `G` | `D` | `A` |
| `D` | `H` | `None` | `A` |
| `E` | `None` | `F` | `B` |
| `F` | `J` | `None` | `B` |
| `G` | `None` | `None` | `C` |
| `H` | `None` | `I` | `D` |
| `I` | `None` | `None` | `D` |
| `J` | `None` | `None` | `F` |

Ví dụ, từ `A.first_child=B` có thể theo `B.next_sibling=C` rồi `C.next_sibling=D` để lấy đúng thứ tự `[B,C,D]`.

Đối với nút `F`, `first_child=J` nghĩa là nó có một con. `F.next_sibling=None` nghĩa là nó là **anh em cuối trong nhóm con của `B`**; đây là hai điều kiện độc lập.

### 4.3. Lớp nút và duyệt các con

```python
class LCRSNode:
    def __init__(self, value):
        self.value = value
        self.parent = None
        self.first_child = None
        self.next_sibling = None


def lcrs_children(node):
    """Lần lượt sinh ra các con trực tiếp của node."""
    child = node.first_child

    while child is not None:
        yield child
        child = child.next_sibling


def lcrs_child_count(node):
    return sum(1 for _ in lcrs_children(node))
```

Với danh sách con, `len(node.children)` là `O(1)`. Nhưng trong LCRS chỉ có liên kết tới **con đầu**; để đếm `k` con, phải theo đủ chuỗi `next_sibling` nên tốn **`O(k)` thời gian** nếu không lưu thêm bộ đếm.

Đọc **con thứ `i`** cũng mất `O(i+1)` trong trường hợp thông thường. Ngược lại, nếu đã có tham chiếu đến nút `v`, việc lấy **anh em kế tiếp** bằng `v.next_sibling` chỉ mất **`O(1)`**.

## 5. Bất biến riêng của con đầu–anh em kế

Ngoài bất biến một gốc, một cha, liên thông và không chu trình của cây, LCRS cần giữ thêm những điều kiện sau:

1. **Gốc có `next_sibling=None`.** Nó không nằm trong danh sách con của bất kỳ cha nào.
2. Với nút `u`, nếu `first_child=u₁`, theo `next_sibling` từ `u₁` phải lấy được **tất cả con của `u`, mỗi con đúng một lần**, theo thứ tự.
3. Nếu `u₁, u₂, \ldots, u_k` là các con của `u`, mọi `u_i` phải có cùng cha `u` (nếu lưu `parent`), `u_i.next_sibling=u_{i+1}` và `u_k.next_sibling=None`.
4. Các chuỗi anh em **không được tạo vòng**. Nếu `C.next_sibling=B` trong khi `B.next_sibling=C`, phép liệt kê con sẽ không bao giờ kết thúc.
5. Một nút không được xuất hiện trong hai chuỗi anh em của hai cha khác nhau.
6. Thay đổi thứ tự con phải cập nhật **liên kết của nút đứng trước nó** hoặc `first_child` của cha.

### Vì sao tháo một nút phải xóa `next_sibling` của nó?

Giả sử các con của `A` là `B,C,D`:

```text
A.first_child → B → C → D → None
```

Nếu muốn **tháo cây con gốc `C`** nhưng chỉ đặt `C.parent=None`, `B.next_sibling` vẫn trỏ vào `C`, nên `C` vẫn xuất hiện trong danh sách con của `A`.

Nếu đổi `B.next_sibling=D` mà **quên đặt `C.next_sibling=None`**, sau khi tách `C` ra thành gốc một cây mới, `C` vẫn trỏ tới `D`, vốn là **anh em cũ** chứ không phải hậu duệ của `C`. Đây là một tham chiếu dư nguy hiểm.

Cách tháo đúng:

```text
Trước: A.first_child → B → C → D

Sau:   A.first_child → B → D
       C.parent = None
       C.next_sibling = None

C.first_child (và mọi hậu duệ của C) giữ nguyên.
```

Vì thế, **liên kết ngang giữa anh em thuộc về ngữ cảnh cha cũ** và phải được tách ra cùng lúc với việc tháo nút khỏi chuỗi.

## 6. Chuyển từ danh sách con sang LCRS

Hai biểu diễn phải cho cùng:

- Gốc và tập nút.
- Quan hệ cha–con.
- **Thứ tự các con**.
- Kết quả duyệt tiền thứ tự, duyệt theo mức và các phép tính trên cây con.

### 6.1. Thuật toán chuyển đổi

Với từng nút `u` của mô hình danh sách:

1. Tạo nút bản sao `u'` trong LCRS.
2. Nếu `u.children` rỗng, đặt `u'.first_child=None`.
3. Nếu các con của `u` là `[v₁,v₂,\ldots,v_k]`, đặt:
   - `u'.first_child=v₁'`.
   - `v₁'.next_sibling=v₂'`, ..., `v_{k-1}'.next_sibling=v_k'`.
   - `v_k'.next_sibling=None`.
4. Đặt `parent` của các con bản sao thành `u'` nếu biểu diễn có lưu liên kết cha.
5. Tiếp tục chuyển đổi các cây con.

Để tránh giới hạn đệ quy trên cây rất sâu, ta dùng stack tường minh:

```python
def list_to_lcrs(root):
    if root is None:
        return None

    new_root = LCRSNode(root.value)
    pending = [(root, new_root)]

    while pending:
        source, target = pending.pop()
        previous = None

        for source_child in source.children:
            target_child = LCRSNode(source_child.value)
            target_child.parent = target

            if previous is None:
                target.first_child = target_child
            else:
                previous.next_sibling = target_child

            previous = target_child
            pending.append((source_child, target_child))

    return new_root


lcrs_root = list_to_lcrs(list_root)
print([x.value for x in lcrs_children(lcrs_root)])
# ['B', 'C', 'D']

print([x.value for x in lcrs_children(lcrs_root.first_child)])
# ['E', 'F']
```

Mỗi nút được sao chép đúng một lần. Với `n` nút và `n-1` cạnh cha–con, vòng lặp xử lý tổng cộng `n-1` mục trong các danh sách con.

**Độ phức tạp:** **`O(n)` thời gian**, dùng **`O(n)` bộ nhớ** cho `n` nút bản sao và tối đa `O(n)` công việc chờ. Hàm tạo **bản sao nút mới**, không sửa cây danh sách ban đầu.

**Giới hạn của phép sao chép:** `target_child = LCRSNode(source_child.value)` giữ **cùng tham chiếu tới đối tượng giá trị** nếu `value` là một đối tượng mutable. Hai cấu trúc có liên kết nút độc lập, nhưng **dữ liệu bên trong `value` chưa được sao chép sâu**. Nếu cần bản sao dữ liệu hoàn toàn độc lập, phải định nghĩa chính sách sao chép giá trị riêng.

### 6.2. Truy vết việc nối anh em

Với ba con của `A` là `[B,C,D]`:

| Lượt | Con mới | `A'.first_child` | Liên kết anh em vừa thiết lập |
|---|---|---|---|
| `1` | `B'` | `B'` | Chưa có |
| `2` | `C'` | `B'` | `B'.next_sibling=C'` |
| `3` | `D'` | `B'` | `C'.next_sibling=D'` |

Sau cùng, `D'.next_sibling=None` và `parent` của cả `B',C',D'` đều là `A'`.

Ta không gán `A'.next_sibling=B'`: `next_sibling` chỉ nối **những nút có cùng cha**, không nối cha tới con.

## 7. Chuyển ngược từ LCRS sang danh sách con

Trong phép chuyển ngược, ta làm việc với từng nút `u` của LCRS:

1. Tạo một nút danh sách `u'`.
2. Theo `u.first_child`, rồi lần lượt qua `next_sibling` để lấy các con của `u`.
3. Tạo các nút bản sao con theo **đúng thứ tự**, thêm vào `u'.children`.
4. Với mỗi con, đặt `parent` bằng `u'`.
5. Đưa các cây con vào stack để tiếp tục.

```python
def lcrs_to_list(root):
    if root is None:
        return None

    new_root = ListNode(root.value)
    pending = [(root, new_root)]

    while pending:
        source, target = pending.pop()

        child = source.first_child
        while child is not None:
            target_child = ListNode(child.value)
            target_child.parent = target
            target.children.append(target_child)

            pending.append((child, target_child))
            child = child.next_sibling

    return new_root


restored_root = lcrs_to_list(lcrs_root)

print([node.value for node in restored_root.children])
# ['B', 'C', 'D']

print([node.value for node in restored_root.children[0].children])
# ['E', 'F']
```

Mỗi nút và mỗi liên kết ngang được xử lý số lần hằng số, nên thời gian **`O(n)`**. Bộ nhớ cho cấu trúc bản sao cùng stack chờ cũng có chặn trên **`O(n)`**.

Với cây có thứ tự **hợp lệ**, ta có kết luận:

> Chuyển từ danh sách con sang LCRS rồi chuyển ngược sẽ bảo toàn **hình dạng cây tổng quát và thứ tự con**, dù các đối tượng nút ở kết quả là đối tượng mới.

Không nên kiểm tra bằng phép so sánh **định danh đối tượng** giữa hai bản cây đã sao chép; hãy so sánh **quan hệ, thứ tự, số nút hoặc kết quả duyệt**, và nếu cần thì kiểm tra `value` theo một định nghĩa bình đẳng phù hợp.

## 8. Duyệt DFS với hai cách biểu diễn

### 8.1. DFS tiền thứ tự trên danh sách con

Duyệt **preorder** (*tiền thứ tự*) xử lý:

1. Nút cha.
2. Cây con thứ nhất.
3. Cây con thứ hai.
4. Các cây con tiếp theo theo thứ tự.

Với stack LIFO, ta phải push các con **theo thứ tự ngược** để con đầu tiên được pop và xử lý trước:

```python
def preorder_list(root):
    if root is None:
        return []

    result = []
    pending = [root]

    while pending:
        node = pending.pop()
        result.append(node.value)

        for child in reversed(node.children):
            pending.append(child)

    return result


print(preorder_list(list_root))
# ['A', 'B', 'E', 'F', 'J', 'C', 'G', 'D', 'H', 'I']
```

### 8.2. DFS tiền thứ tự trên LCRS

Đối với LCRS, **không được** xem `node.next_sibling` là một cây con của `node`. Ta cần liệt kê toàn bộ **con trực tiếp** của `node` bằng cách đi từ `first_child` qua chuỗi `next_sibling`:

```python
def preorder_lcrs(root):
    if root is None:
        return []

    result = []
    pending = [root]

    while pending:
        node = pending.pop()
        result.append(node.value)

        children = list(lcrs_children(node))
        # Đảo để phần tử con đầu tiên nằm trên đỉnh stack.
        pending.extend(reversed(children))

    return result


print(preorder_lcrs(lcrs_root))
# ['A', 'B', 'E', 'F', 'J', 'C', 'G', 'D', 'H', 'I']

assert preorder_lcrs(lcrs_root) == preorder_list(list_root)
```

Cả hai thuật toán thăm mỗi nút một lần, mỗi cạnh con hoặc liên kết anh em được xét số lần hằng số. Tổng thời gian **`O(n)`**. Stack công việc có thể giữ **`O(n)`** nút trên cây tổng quát rất rộng; danh sách kết quả cũng cần `O(n)` bộ nhớ.

Ở hàm LCRS, tạo danh sách tạm `children` kích thước bằng số con của nút đang xử lý, tối đa `O(n)`. Có thể dùng các frame/iterator để duyệt không cần tạo danh sách tạm, nhưng mã sẽ dài hơn.

### 8.3. Vì sao duyệt nhầm `next_sibling` tạo kết quả sai?

Xét:

```text
A.first_child=B
B.next_sibling=C
B.first_child=E
```

Nếu gọi hàm đệ quy xử lý `B.first_child` rồi `B.next_sibling` như thể cả hai là **con của `B`**, ta sẽ hiểu sai quan hệ: `C` bị tính là hậu duệ của `B`, trong khi thực ra `B` và `C` là anh em.

Một số bài toán chỉ cần đi qua **tất cả các nút**, và sơ đồ đệ quy trên cả hai liên kết vẫn có thể ghé đủ các đối tượng. Nhưng **độ sâu cây tổng quát, kích thước cây con, tổ tiên và phân nhóm con** sẽ sai nếu ta không phân biệt ý nghĩa của liên kết dọc và liên kết ngang.

## 9. BFS theo mức với hai biểu diễn

**BFS (Breadth-First Search)** xử lý toàn bộ nút ở mức hiện tại trước khi chuyển sang mức tiếp theo. Nó dùng **queue FIFO**.

### 9.1. BFS với danh sách con

```python
from collections import deque


def level_order_list(root):
    if root is None:
        return []

    result = []
    queue = deque([root])

    while queue:
        node = queue.popleft()
        result.append(node.value)
        queue.extend(node.children)

    return result


print(level_order_list(list_root))
# ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
```

### 9.2. BFS với LCRS

```python
def level_order_lcrs(root):
    if root is None:
        return []

    result = []
    queue = deque([root])

    while queue:
        node = queue.popleft()
        result.append(node.value)

        # Mỗi mắt xích trong chuỗi là một CON của node.
        for child in lcrs_children(node):
            queue.append(child)

    return result


print(level_order_lcrs(lcrs_root))
# ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']

assert level_order_lcrs(lcrs_root) == level_order_list(list_root)
```

Với cây hợp lệ, **mỗi nút chỉ được đưa vào queue một lần**, nên cả hai hàm mất **`O(n)` thời gian**. Queue có thể chứa nhiều nút cùng lúc khi cây rộng, tối đa `O(n)` bộ nhớ phụ. Nếu cần trả danh sách `n` giá trị thì riêng danh sách trả về cũng chiếm `O(n)`.

**Không có phép duyệt inorder chuẩn cho cây tổng quát có nhiều hơn hai con** tương đương trực tiếp với thứ tự trái–gốc–phải của cây nhị phân. Nếu ứng dụng cần một thứ tự “giữa các con”, phải nêu quy tắc bổ sung; còn preorder, postorder và level-order đều tự nhiên với cây tổng quát.

## 10. Tính kích thước cây con đúng trong LCRS

Với nút `u` trong cây tổng quát, kích thước cây con của `u` là:

\[
\operatorname{size}(u)
=1+\sum_{v\in\operatorname{children}(u)}\operatorname{size}(v).
\]

Trong LCRS, `children(u)` phải được lấy bằng chuỗi bắt đầu tại `u.first_child`. **Không được cộng kích thước của `u.next_sibling` vào kích thước cây con của `u`**, bởi anh em kế tiếp nằm ngoài cây con gốc `u`.

Ví dụ ở cây mẫu:

- `size(J)=1`.
- `size(F)=2` vì gồm `F,J`.
- `size(B)=4` vì gồm `B,E,F,J`.
- `size(C)=2`, `size(D)=3`.
- `size(A)=10`.

### 10.1. Tính hậu thứ tự bằng stack

Khi tính kích thước từ dưới lên, phải hoàn tất tất cả con trước khi hoàn tất cha. Ta dùng các frame `(node, ready)`:

```python
def subtree_sizes_lcrs(root):
    if root is None:
        return {}

    sizes = {}
    frames = [(root, False)]

    while frames:
        node, ready = frames.pop()

        if ready:
            sizes[node] = 1 + sum(
                sizes[child] for child in lcrs_children(node)
            )
        else:
            frames.append((node, True))
            for child in lcrs_children(node):
                frames.append((child, False))

    return sizes


sizes = subtree_sizes_lcrs(lcrs_root)

node_b = lcrs_root.first_child
node_c = node_b.next_sibling
node_d = node_c.next_sibling

print(sizes[node_b])  # 4
print(sizes[node_c])  # 2
print(sizes[node_d])  # 3
print(sizes[lcrs_root])  # 10
```

**Bất biến:** khi lấy frame `(node, True)`, tất cả các nút con của `node` đã có kích thước trong bảng `sizes`. Vì vậy tổng ở giai đoạn `ready` là hợp lệ.

Thời gian là **`O(n)`**, vì các chuỗi con được xét một số lần hằng số và mỗi nút có đúng một frame bắt đầu cùng một frame hoàn tất. Bộ nhớ cho bảng kết quả và frames là **`O(n)`**.

### 10.2. Chiều cao cũng dựa trên các con trực tiếp

Theo quy ước chiều cao tính bằng **số cạnh**, nút lá có chiều cao `0`; nút có con có:

\[
\operatorname{height}(u)=1+\max_{v\in\operatorname{children}(u)}
\operatorname{height}(v).
\]

Đối với LCRS, chỉ cần thay phép liệt kê `children(u)` bằng `lcrs_children(u)`. Nút `u.next_sibling` không góp phần làm tăng chiều cao của cây con gốc `u`.

Có thể tính height bằng cùng cơ chế frame hậu thứ tự và thay `sum` thành `max`, với giá trị mặc định của `max` bằng `-1`. Đây cũng là một ví dụ về việc **thuật toán có thể độc lập với biểu diễn** nếu ta cung cấp một giao diện liệt kê con đúng nghĩa.

## 11. Thêm và xóa con trong LCRS

Khác với danh sách động có thể truy cập trực tiếp `children[i]`, LCRS lưu con theo một **chuỗi liên kết đơn**. Vì vậy chi phí phụ thuộc vị trí thao tác.

### 11.1. Thêm con vào đầu chuỗi

Để thêm một nút `child` làm **con đầu** của `parent`:

1. Kiểm tra `child` là gốc của một cây con đang tách riêng: `child.parent=None`, `child.next_sibling=None`.
2. Kiểm tra `parent` không nằm trong cây con của `child`; nếu không sẽ tạo chu trình.
3. Cho `child.next_sibling` trỏ tới con đầu cũ.
4. Đặt `parent.first_child=child`.
5. Đặt `child.parent=parent`.

```python
def prepend_lcrs_child(parent, child):
    if not isinstance(parent, LCRSNode):
        raise TypeError("parent phải là LCRSNode")
    if not isinstance(child, LCRSNode):
        raise TypeError("child phải là LCRSNode")
    if child.parent is not None or child.next_sibling is not None:
        raise ValueError("child chưa tách khỏi chuỗi anh em cũ")

    cursor = parent
    while cursor is not None:
        if cursor is child:
            raise ValueError("không thể tạo chu trình")
        cursor = cursor.parent

    child.next_sibling = parent.first_child
    parent.first_child = child
    child.parent = parent
```

**Chi phí về liên kết:** một số hằng thao tác con trỏ, **`O(1)`**. Tuy nhiên, trong triển khai an toàn ở trên còn có **kiểm tra tổ tiên**, mất `O(h+1)` thời gian với `h` là chiều cao cây hiện tại. Do đó tổng thời gian **không thể luôn quảng cáo là `O(1)`** nếu tính cả kiểm tra hợp lệ.

### 11.2. Thêm con ở cuối chuỗi

Muốn giữ thứ tự và thêm vào cuối, ta phải tìm **anh em cuối** trước:

```python
def append_lcrs_child(parent, child):
    if not isinstance(parent, LCRSNode):
        raise TypeError("parent phải là LCRSNode")
    if not isinstance(child, LCRSNode):
        raise TypeError("child phải là LCRSNode")
    if child.parent is not None or child.next_sibling is not None:
        raise ValueError("child chưa tách khỏi chuỗi anh em cũ")

    cursor = parent
    while cursor is not None:
        if cursor is child:
            raise ValueError("không thể tạo chu trình")
        cursor = cursor.parent

    if parent.first_child is None:
        parent.first_child = child
    else:
        tail = parent.first_child
        while tail.next_sibling is not None:
            tail = tail.next_sibling
        tail.next_sibling = child

    child.parent = parent
```

Nếu `parent` có `k` con, tìm cuối chuỗi mất **`O(k)`**, chưa kể kiểm tra tổ tiên `O(h+1)`. Tổng chi phí thông thường là **`O(h+k+1)`**.

Nếu ứng dụng thường xuyên thêm con cuối, có thể lưu thêm `last_child` ở mỗi nút để thêm vào cuối trong **`O(1)` thao tác liên kết**, nhưng khi xóa hoặc chuyển con cuối phải cập nhật tham chiếu này. Đây là **đánh đổi bộ nhớ và độ phức tạp cập nhật**.

### 11.3. Tháo một cây con khỏi chuỗi anh em

Hàm dưới đây tách nút khỏi cha hiện tại và giữ nguyên toàn bộ **hậu duệ** của nó:

```python
def detach_lcrs(node):
    if not isinstance(node, LCRSNode):
        raise TypeError("node phải là LCRSNode")

    parent = node.parent
    if parent is None:
        return False  # Đã là gốc một cây riêng.

    if parent.first_child is node:
        parent.first_child = node.next_sibling
    else:
        previous = parent.first_child
        while (
            previous is not None
            and previous.next_sibling is not node
        ):
            previous = previous.next_sibling

        if previous is None:
            raise ValueError("liên kết parent/sibling không nhất quán")

        previous.next_sibling = node.next_sibling

    node.parent = None
    node.next_sibling = None
    return True
```

- Nếu tháo **con đầu**, cập nhật `parent.first_child`: thao tác liên kết `O(1)`.
- Nếu tháo con ở giữa/cuối mà không lưu `previous_sibling`, phải quét chuỗi anh em trước: **`O(k)`**.
- Mọi hậu duệ vẫn ở trong cây con của `node`.
- Đặt `node.next_sibling=None` để nút được tháo không còn nối với các anh em cũ.

Một hàm **xóa toàn bộ cây con khỏi bộ nhớ** là công việc khác: còn phụ thuộc các tham chiếu ngoài và cơ chế quản lý bộ nhớ, có thể cần xử lý `s` nút của cây con, với chi phí `O(s)` hoặc khác tùy mục tiêu ứng dụng.

### 11.4. Kiểm tra kết quả bằng ví dụ mới

Mỗi ví dụ dưới đây tạo cây LCRS mới để tránh kết quả bị ảnh hưởng bởi các thao tác trước đó:

```python
example = list_to_lcrs(build_list_tree()[0])
b = example.first_child
c = b.next_sibling
d = c.next_sibling

print([x.value for x in lcrs_children(example)])
# ['B', 'C', 'D']

# Thêm X làm con đầu của A.
x = LCRSNode("X")
prepend_lcrs_child(example, x)
print([v.value for v in lcrs_children(example)])
# ['X', 'B', 'C', 'D']

# Tháo C khỏi chuỗi; con G của C vẫn giữ nguyên.
assert detach_lcrs(c)
print([v.value for v in lcrs_children(example)])
# ['X', 'B', 'D']

print(c.parent)                        # None
print(c.next_sibling)                  # None
print([v.value for v in lcrs_children(c)])  # ['G']
```

**Lưu ý:** trong một thao tác đổi cha (*reparent*) phức tạp, cần kiểm tra trước việc gắn vào cha mới không tạo chu trình; sau đó mới tháo và gắn lại. Nếu chương trình có thể lỗi giữa chừng hoặc chạy đa luồng, nhiều cập nhật liên kết nên được bảo vệ bằng cơ chế giao dịch/đồng bộ. Mã đơn giản trong bài không tự bảo đảm tính nguyên tử trước mọi loại lỗi.

## 12. Đếm chính xác số liên kết và bộ nhớ

Một ưu điểm dễ thấy của LCRS là **số trường liên kết cố định tại mỗi nút**, bất kể nút có bao nhiêu con.

Giả sử cây có `n≥1` nút và `I` nút trong.

### 12.1. Tổng số liên kết có ý nghĩa của LCRS

- Mỗi nút trong có **một `first_child` khác `None`**: tổng cộng `I` liên kết.
- Một nút cha có `k≥1` con thì chuỗi `next_sibling` của nhóm con đó có đúng `k-1` liên kết khác `None`.
- Cộng trên tất cả các nhóm con:

\[
\#\text{next\_sibling links}
=\sum_{u:\,childCount(u)>0} (childCount(u)-1).
\]

Vì:

\[
\sum_u childCount(u)=n-1,
\]

nên:

\[
\#\text{next\_sibling links}=(n-1)-I.
\]

Do đó tổng liên kết hướng xuống/đi ngang **khác `None`** là:

\[
I + (n-1-I)=\boxed{n-1}.
\]

Chúng mã hóa đúng `n-1` cạnh cha–con của cây gốc, dù một số liên kết được biểu diễn theo chiều **ngang giữa anh em**.

Nếu mỗi nút còn lưu `parent`, có thêm `n-1` liên kết khác `None`. Số trường có sẵn trên tất cả nút là:

- `2n` trường cấu trúc (`first_child` và `next_sibling`).
- Thêm `n` trường `parent` nếu cần.

Số trường có thể là `O(n)`, kể cả các trường mang giá trị `None`.

### 12.2. Đếm ở cây ví dụ

Cây mẫu có `n=10` nút. Các nút trong là `A,B,C,D,F`, nên `I=5`:

- Có `5` liên kết `first_child` khác `None`.
- Có `10-1-5=4` liên kết `next_sibling` khác `None`:
  `B→C, C→D, E→F, H→I`.
- Tổng liên kết cấu trúc khác rỗng là `5+4=9=n-1`.
- Nếu lưu thêm `parent`, có `9` liên kết ngược khác rỗng.

Nhờ phép đếm này, ta thấy cách lưu LCRS không cần nhiều trường con cho nút `A` dù nó có ba hoặc hàng trăm con.

### 12.3. Danh sách con cũng là `O(n)`

Với mô hình `children`, tổng số **tham chiếu tới con thực sự** trên mọi danh sách cũng là `n-1`. Tuy nhiên, mỗi nút có thể mang một đối tượng danh sách riêng; mảng động có thể cấp phát thêm dung lượng dự phòng và metadata.

Do vậy không được kết luận rằng LCRS **luôn dùng ít bộ nhớ thực tế hơn** chỉ vì có hai liên kết. Cả hai đều có độ phức tạp **`O(n)`**, còn hằng số phụ thuộc runtime, kiểu đối tượng, cách cấp phát và có/không có `parent` hay cache.

## 13. Bảng so sánh thao tác và lựa chọn cấu trúc

Gọi `n` là tổng số nút, `h` là chiều cao theo cạnh và `k` là số con trực tiếp của một nút.

| Thao tác | Danh sách con `children` (Python list) | LCRS chỉ có `first_child/next_sibling` |
|---|---|---|
| Xem có con không | `O(1)` | `O(1)` |
| Lấy con đầu | `O(1)` | `O(1)` |
| Đếm số con | `O(1)` | `O(k)` nếu không có cache |
| Lấy con thứ `i` (đã biết `i`) | `O(1)` | `O(i+1)` |
| Duyệt toàn bộ `k` con | `O(k)` | `O(k)` |
| Thêm con đầu | `O(k)` do dời phần tử | `O(1)` thao tác liên kết |
| Thêm con cuối | `O(1)` amortized | `O(k)` nếu không có `last_child` |
| Xóa con khi có con trỏ tới nút | `O(k)` với `list.remove` | `O(k)` để tìm nút đứng trước; `O(1)` nếu tháo con đầu |
| Lấy anh em kế tiếp khi có nút | Cần biết vị trí trong `children` hoặc tìm `O(k)` | `O(1)` |
| Đi ngược về cha | `O(1)` nếu lưu `parent` | `O(1)` nếu lưu `parent` |
| Duyệt toàn bộ cây | `O(n)` | `O(n)` |
| Bộ nhớ lưu cấu trúc | `O(n)` | `O(n)` |

**Các chi phí thêm/xóa trong bảng chỉ tính thao tác liên kết/danh sách**, chưa cộng **kiểm tra chu trình và tính hợp lệ**. Ví dụ, các hàm `attach_list_child` và `prepend_lcrs_child` ở trên đều duyệt theo cha để tránh chu trình, có thể cần thêm `O(h+1)` thời gian. Nếu không có sẵn tham chiếu nút và phải tìm nút theo dữ liệu, hãy cộng chi phí tìm kiếm.

### Khi nào ưu tiên danh sách con?

- Cần lấy nhanh **con ở vị trí bất kỳ** theo chỉ số.
- Cần hiển thị hay thao tác với toàn bộ một danh sách con.
- Muốn dùng trực tiếp API danh sách của ngôn ngữ lập trình.
- Số con thường nhỏ hoặc việc thêm cuối thường xuyên; các thao tác `append` hiệu quả.
- Cần code dễ hiểu, dễ kiểm thử, giảm rủi ro cập nhật sai chuỗi anh em.

### Khi nào ưu tiên LCRS?

- Số con thay đổi nhiều và muốn số **trường liên kết cố định** trên từng nút.
- Cần duyệt tuần tự các anh em hoặc chèn con đầu nhanh.
- Hệ thống dùng đối tượng có layout bộ nhớ chặt chẽ, hoặc cần mã hóa cây tổng quát dưới cấu trúc hai liên kết.
- Bài toán đã biểu diễn quan hệ anh em thành chuỗi; thao tác chủ yếu tuần tự hơn là truy cập ngẫu nhiên.
- Có thể bổ sung `parent`, `last_child` hoặc bộ đếm con nếu ứng dụng thực sự cần truy vấn đó nhanh hơn, chấp nhận thêm bộ nhớ và trách nhiệm cập nhật.

**Không có cách biểu diễn tốt nhất cho mọi ứng dụng.** Hãy dựa trên yêu cầu thao tác, thứ tự các con, khả năng cập nhật và ngân sách bộ nhớ.

## 14. Kiểm tra cấu trúc LCRS hợp lệ

Một chương trình có thể vô tình sửa `next_sibling` hoặc `first_child` sai, tạo chu trình hoặc dùng chung một nút. Một hàm kiểm tra nên dùng **định danh đối tượng**, không dựa vào `value`, vì nhiều nút khác nhau có thể cùng giá trị.

### 14.1. Kiểm tra từ gốc

Dưới đây là một hàm kiểm tra mô hình có lưu `parent`. Nó cũng chấp nhận một tập nút kỳ vọng nếu ứng dụng muốn phát hiện những nút đang **bị tách rời khỏi gốc**.

```python
def validate_lcrs(root, expected_nodes=None):
    if root is None:
        return expected_nodes is None or len(expected_nodes) == 0

    if not isinstance(root, LCRSNode):
        return False
    if root.parent is not None or root.next_sibling is not None:
        return False

    visited = set()
    pending = [root]

    while pending:
        node = pending.pop()
        marker = id(node)

        if marker in visited:
            return False  # Chu trình hoặc một nút có nhiều đường tới.
        visited.add(marker)

        child = node.first_child
        local_siblings = set()

        while child is not None:
            if not isinstance(child, LCRSNode):
                return False

            sibling_id = id(child)
            if sibling_id in local_siblings:
                return False  # Chu trình trong chuỗi anh em.
            local_siblings.add(sibling_id)

            if child.parent is not node:
                return False

            pending.append(child)
            child = child.next_sibling

    if expected_nodes is not None:
        expected_ids = [id(node) for node in expected_nodes]
        return (
            len(expected_ids) == len(set(expected_ids))
            and visited == set(expected_ids)
        )

    return True


assert validate_lcrs(lcrs_root)

# Liên kết anh em bị tạo vòng.
bad_root = LCRSNode("root")
bad_child = LCRSNode("child")
bad_root.first_child = bad_child
bad_child.parent = bad_root
bad_child.next_sibling = bad_child

assert not validate_lcrs(bad_root)
```

**Độ phức tạp:** với cấu trúc LCRS hợp lệ gồm `n` nút, hàm xử lý mỗi nút, con và liên kết anh em một số lần hằng số: **`O(n)` thời gian**. Tập đã thăm, tập anh em cục bộ và stack chờ chiếm **`O(n)` bộ nhớ trong trường hợp xấu nhất**.

Nếu danh sách `expected_nodes` có `q` nút, bước đối chiếu thêm `O(q)` thời gian và bộ nhớ.

### 14.2. Giới hạn của kiểm tra từ một gốc

Nếu chỉ đưa vào `root` mà không có tập nút kỳ vọng, không một thuật toán duyệt từ gốc nào có thể tự phát hiện một đối tượng nút nằm hoàn toàn **ngoài cây** và không được tham chiếu từ đâu trong cây đó. Hàm chỉ xác nhận cấu trúc **có thể tới được từ gốc**.

Để kiểm tra toàn bộ hệ thống, cần một danh sách hoặc tập định danh các nút mà ứng dụng xem là thuộc cùng cây, rồi so sánh với tập đã thăm.

Đồng thời, việc xác nhận một đối tượng thuộc kiểu `LCRSNode` chưa đủ chứng minh bất biến nếu mã khác có thể thay đổi liên kết trong lúc kiểm tra. Trong ứng dụng nhiều luồng, cần đọc từ **trạng thái nhất quán** hoặc sử dụng đồng bộ thích hợp.

## 15. Những sai lầm thường gặp

1. **Xem `next_sibling` là con phải của cây tổng quát.** Nó nối **hai anh em**, không nối một nút với con của nó.
2. **Quên thứ tự các con.** Cây có thứ tự `[B,C,D]` khác `[D,C,B]`; chuyển đổi phải giữ đúng thứ tự.
3. **Duyệt `first_child` mà không theo hết `next_sibling`.** Khi đó bỏ sót các con đứng sau con đầu.
4. **Tính kích thước cây con bằng cả `next_sibling` của chính nút.** Anh em nằm ngoài cây con của nút đang xét.
5. **Quên `root.next_sibling=None`.** Gốc không có anh em trong cùng một cây có gốc.
6. **Gắn một nút chưa được tháo khỏi chuỗi anh em cũ.** Nút có thể xuất hiện ở hai chuỗi con, tạo quan hệ nhiều cha.
7. **Chỉ xóa `parent` khi tháo LCRS.** Phải nối lại chuỗi anh em của cha và đặt `node.next_sibling=None`.
8. **Không kiểm tra chu trình trong chuỗi anh em.** Một vòng ngang có thể làm duyệt lặp vô hạn.
9. **Tưởng `child_count` là `O(1)` cho cả hai biểu diễn.** LCRS cần đi qua `k` con nếu không lưu cache.
10. **Tưởng thêm cuối luôn `O(1)`.** Với LCRS chỉ có `first_child`, tìm anh em cuối mất `O(k)`.
11. **Tưởng chèn đầu danh sách con Python là `O(1)`.** `list.insert(0, x)` có thể phải dời `k` phần tử.
12. **Bỏ qua chi phí kiểm tra tính hợp lệ.** Gắn con có thể cần duyệt tới gốc để phát hiện chu trình, mất `O(h+1)`.
13. **So sánh giá trị để nhận diện nút.** Hai nút mang cùng nhãn chưa chắc là cùng một đối tượng.
14. **Sao chép cây nhưng tưởng cả `value` mutable cũng được sao chép sâu.** Mã chuyển đổi chỉ tạo đối tượng nút mới; giá trị có thể vẫn được chia sẻ.
15. **Dùng phép duyệt đệ quy trên cây rất sâu mà không chú ý call stack.** Có thể chạm giới hạn của runtime; dùng stack tường minh khi cần.
16. **Cho rằng `n-1` liên kết là chứng cứ đủ của cây hợp lệ.** Vẫn cần kiểm tra một gốc, một cha, liên thông và không chu trình.
17. **Chỉ kiểm tra những nút từ gốc rồi kết luận không có nút cô lập.** Cần có tập nút kỳ vọng để phát hiện phần tử nằm ngoài.
18. **Cập nhật cấu trúc nhưng quên cập nhật cache `size`/`depth`/`height`.** Những giá trị phụ thuộc quan hệ cha–con có thể thay đổi khi chuyển cây con.
19. **Đánh giá bộ nhớ chỉ bằng số con của một nút.** Tổng các mục con của cả cây luôn `n-1`; số đối tượng danh sách và dung lượng dư mới là khác biệt ở mức cài đặt.
20. **Biến đổi thứ tự anh em khi chuyển đổi** vì push/pop không được đảo đúng cách. Kiểm tra preorder và level-order trên hai phiên bản sẽ giúp phát hiện lỗi này.

## 16. Bài tập thực hành có đáp án

### Bài 1. Danh sách con

Với cây mẫu `A,B,C,D,E,F,G,H,I,J`, hãy ghi `children(A)`, `children(B)`, `children(D)` và `children(F)`.

**Đáp án:** `children(A)=[B,C,D]`, `children(B)=[E,F]`, `children(D)=[H,I]` và `children(F)=[J]`.

### Bài 2. Chuyển sang LCRS

Với `children(A)=[B,C,D]`, xác định `A.first_child`, `B.next_sibling`, `C.next_sibling` và `D.next_sibling`.

**Đáp án:** `A.first_child=B`, `B.next_sibling=C`, `C.next_sibling=D`, `D.next_sibling=None`.

### Bài 3. Đọc đúng ý nghĩa liên kết

Nếu `B.next_sibling=C` thì `B` có phải cha của `C` không?

**Đáp án:** **Không.** `B` và `C` là **anh em**, cùng cha `A` trong cây mẫu. Liên kết `next_sibling` chỉ xác định **thứ tự giữa các con của cùng cha**.

### Bài 4. Đếm con

Trong LCRS, `A.first_child=B`, `B.next_sibling=C`, `C.next_sibling=D`, `D.next_sibling=None`. Nút `A` có mấy con và phép đếm cần bao nhiêu lượt đi qua chuỗi?

**Đáp án:** `A` có **3 con**. Phải đọc các nút `B,C,D` nên chi phí **`O(3)`**, tổng quát **`O(k)`** với `k` con.

### Bài 5. Duyệt preorder

Với cây mẫu ban đầu, hãy viết thứ tự DFS tiền thứ tự, xét các con từ trái sang phải.

**Đáp án:** `A, B, E, F, J, C, G, D, H, I`.

### Bài 6. Duyệt BFS

Với cùng cây, liệt kê các nút theo mức, từ trái qua phải.

**Đáp án:** `A, B, C, D, E, F, G, H, I, J`.

### Bài 7. Kích thước cây con

Trong cây mẫu, tính `size(F)`, `size(B)`, `size(C)` và `size(A)`.

**Đáp án:** `size(F)=2` (`F,J`), `size(B)=4` (`B,E,F,J`), `size(C)=2` (`C,G`) và `size(A)=10`.

### Bài 8. Tháo một anh em ở giữa

Các con của `A` theo LCRS là `B→C→D`. Nếu tháo cây con gốc `C`, những liên kết nào phải thay đổi?

**Đáp án:** Đặt `B.next_sibling=D`, `C.parent=None` và `C.next_sibling=None`. `C.first_child` và các hậu duệ của `C` **không thay đổi**.

### Bài 9. Thêm con đầu và cuối

Một nút có `k` con. So sánh độ phức tạp **thao tác liên kết** khi thêm con ở đầu và cuối giữa Python `list` và LCRS không có `last_child`.

**Đáp án:** Với `list`, thêm đầu có thể `O(k)` do dời phần tử; thêm cuối `O(1)` amortized. Với LCRS, thêm đầu `O(1)`; thêm cuối `O(k)` vì phải tìm anh em cuối. Các con số **chưa tính kiểm tra chu trình**.

### Bài 10. Định lý số liên kết

Một cây tổng quát có `n=12` nút và `I=5` nút trong. Trong biểu diễn LCRS, có bao nhiêu `first_child` và `next_sibling` khác rỗng?

**Đáp án:** Có `I=5` liên kết `first_child` và `n-1-I=12-1-5=6` liên kết `next_sibling` khác `None`. Tổng là `11=n-1`.

### Bài 11. Chuyển đổi bảo toàn điều gì?

Khi đổi một cây có thứ tự từ danh sách con sang LCRS, những tính chất nào bắt buộc phải giữ?

**Đáp án:** Giữ **quan hệ cha–con, gốc, số nút, số cạnh, thứ tự các con** và các kết quả duyệt phụ thuộc thứ tự. Các đối tượng nút mới có thể có định danh bộ nhớ khác; không bắt buộc giữ cùng tham chiếu đối tượng.

### Bài 12. Nhận diện chu trình anh em

Nếu `B.next_sibling=C` và `C.next_sibling=B`, điều gì xảy ra khi dùng vòng lặp duyệt hết các con từ `B`?

**Đáp án:** Vòng lặp có thể chạy mãi: `B→C→B→C→...`. Đây là chu trình trong **chuỗi anh em**, vi phạm bất biến LCRS; cần phát hiện bằng tập đã thăm hoặc logic xác thực cấu trúc.

### Bài 13. Mảng cha và danh sách con

Một ứng dụng chỉ có mảng `parent` của `n` nút. Muốn tìm tất cả con của một nút `u` phải làm gì? Nếu thường xuyên truy vấn con, nên bổ sung biểu diễn nào?

**Đáp án:** Quét `n` phần tử, giữ các chỉ số `v` có `parent[v]=u`, mất `O(n)` mỗi lần. Nếu truy vấn nhiều, xây/lưu **danh sách con** hoặc **LCRS**, để liệt kê đúng `k` con trong `O(k)` sau khi có điểm bắt đầu.

### Bài 14. Bộ nhớ

Một cây có `100` nút và `30` nút trong. Không lưu `parent`, LCRS có bao nhiêu liên kết khác `None` thuộc hai trường `first_child` và `next_sibling` cộng lại?

**Đáp án:** `99=n-1` liên kết khác `None`. Cụ thể, `30` liên kết `first_child` và `99-30=69` liên kết `next_sibling`. Mỗi nút vẫn có **hai trường** bất kể chúng rỗng hay không.

### Bài 15. Khôi phục cây con có giá trị trùng

Hai nút riêng biệt đều có `value="X"`. Khi chuyển đổi biểu diễn, có thể gộp chúng thành một nút vì cùng giá trị không?

**Đáp án:** **Không.** Giá trị bằng nhau không có nghĩa là cùng một nút. Gộp chúng có thể tạo nhiều cha hoặc làm mất nút/cạnh. Cần bảo toàn **định danh logic và quan hệ** của mỗi nút.

### Bài 16. Lựa chọn biểu diễn

Một ứng dụng mục lục thường xuyên truy cập “con thứ 50” của một mục và liên tục thêm phần tử ở **cuối** danh sách. Nên ưu tiên danh sách con hay LCRS chỉ có hai liên kết?

**Đáp án:** **Danh sách con dạng mảng động** thường phù hợp: truy cập phần tử theo chỉ số `O(1)` và thêm cuối `O(1)` amortized. LCRS phải đi qua chuỗi để lấy con thứ 50 hoặc tìm cuối, trừ khi bổ sung chỉ mục/`last_child`.

### Bài 17. Lựa chọn biểu diễn khi chèn đầu

Một trình phân tích dữ liệu thường xuyên thêm một thành phần mới vào **đầu danh sách con** của nút đã biết, và số con có thể rất lớn. Ưu điểm của LCRS là gì?

**Đáp án:** Khi nút mới hợp lệ và đã có tham chiếu cha, thay đổi `first_child`/`next_sibling` chỉ cần **`O(1)` thao tác liên kết**, không dời cả mảng như `list.insert(0, x)`. Tuy vậy, nếu API cần kiểm tra chu trình qua liên kết cha thì phải cộng chi phí kiểm tra.

### Bài 18. Phát hiện nút ngoài cây

Một phép duyệt từ gốc của LCRS thấy `10` nút hợp lệ, nhưng hệ thống quản lý `11` đối tượng nút. Có thể kết luận tất cả nút thuộc cùng một cây không?

**Đáp án:** **Không.** Một nút có thể bị cô lập, là gốc cây khác hoặc không còn được tham chiếu từ gốc đang xét. Cần đối chiếu với **tập nút kỳ vọng**; chỉ duyệt từ gốc không tự biết các đối tượng hoàn toàn nằm ngoài.

## 17. Tổng kết

Để biểu diễn **cây tổng quát**, nơi mỗi nút có thể có nhiều con, ta có hai phương án phổ biến:

- **Danh sách con:** mỗi nút lưu `children=[c₁,c₂,\ldots,c_k]`. Cách này trực quan, thuận tiện cho truy cập theo chỉ số và thêm cuối danh sách.
- **Con đầu–anh em kế (LCRS):** mỗi nút lưu `first_child` và `next_sibling`. Cách này dùng số trường liên kết cố định, hỗ trợ duyệt tuần tự anh em và thêm con đầu bằng vài thao tác liên kết.

Hai biểu diễn đều lưu một cây có `n` nút bằng **`O(n)` bộ nhớ**, và đều cho phép DFS/BFS hoặc tính các đại lượng cây con trong **`O(n)` thời gian** nếu duyệt đúng các quan hệ cha–con. Tổng các liên kết `first_child` và `next_sibling` khác rỗng của LCRS bằng **`n-1`**; nó chỉ là một **cách mã hóa các cạnh cha–con**, không biến `next_sibling` thành con phải thực sự.

Điều quan trọng nhất khi cài đặt là **giữ bất biến một cha, không chu trình, thứ tự các con và sự nhất quán giữa các liên kết**. Khi gắn hay tháo cây con trong LCRS, phải cập nhật đúng cả chuỗi anh em và các liên kết cha; khi chuyển đổi giữa hai biểu diễn, phải bảo toàn kết quả duyệt và hình dạng phân cấp.

Hãy chọn **danh sách con** khi cần truy cập ngẫu nhiên theo vị trí và thao tác mảng thuận tiện; chọn **LCRS** khi ưu tiên liên kết cố định trên mỗi nút, duyệt tuần tự hoặc chèn đầu. Quyết định cuối cùng nên dựa trên **bất biến, loại thao tác, độ phức tạp thời gian và chi phí bộ nhớ thực tế**, không chỉ trên số trường trong một đối tượng.

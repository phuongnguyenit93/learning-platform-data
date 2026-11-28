# Cây Cartesian và quan hệ với truy vấn cực trị trên đoạn

## 1. Bài toán: cực trị trong một đoạn liên tiếp

Cho một mảng tĩnh gồm `n` giá trị:

```text
Chỉ số:  0  1  2  3  4
Giá trị: 4  2  5  1  3
```

Một **truy vấn cực tiểu trên đoạn** (*range minimum query*, RMQ) hỏi giá trị nhỏ nhất của `A[l..r]`, với `0\le l\le r<n`. Ví dụ:

- `RMQ(0,2)=2` vì min của `[4,2,5]` là `2`.
- `RMQ(2,4)=1` vì min của `[5,1,3]` là `1`.
- `RMQ(4,4)=3` vì đoạn chỉ có một phần tử.

Một câu hỏi sâu hơn là: **có thể biến truy vấn tìm cực tiểu trong mảng thành một truy vấn trên cây hay không?**

Câu trả lời là có. **Cây Cartesian** (*Cartesian tree*) kết hợp hai nguyên tắc:

1. **Thứ tự duyệt giữa (in-order)** của cây chính là thứ tự chỉ số trong mảng.
2. **Bất biến heap** khiến nút cha không lớn hơn các nút con theo giá trị.

Nhờ hai nguyên tắc này, với **min-Cartesian tree**, phần tử nhỏ nhất trong đoạn `[l,r]` chính là nút **tổ tiên chung gần nhất** (*lowest common ancestor*, LCA) của hai nút có chỉ số `l` và `r`.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Định nghĩa min-Cartesian tree và max-Cartesian tree, phân biệt chúng với BST theo giá trị và cây heap hoàn chỉnh.
2. Hiểu bất biến **in-order theo chỉ số** và **heap-order theo giá trị**.
3. Xác định quy tắc phá hòa khi nhiều phần tử cùng đạt cực trị.
4. Xây cây Cartesian từ mảng bằng **ngăn xếp đơn điệu trong `O(n)`**.
5. Chứng minh định lý `RMQ(l,r)=A[LCA(l,r)]`.
6. Dùng **Euler tour + sparse table** để trả lời RMQ tĩnh với `O(1)` thời gian sau tiền xử lý `O(n\log n)`.
7. Phân biệt trường hợp dữ liệu tĩnh với bài toán cập nhật giá trị động.
8. So sánh cây Cartesian với sparse table trực tiếp, segment tree, monotonic stack và các cấu trúc liên quan.
9. Cài thuật toán Python và xây bộ kiểm tra bất biến, đối chiếu với lời giải duyệt thẳng.

Chủ đề thuộc chương **Cây tăng cường** trong học phần **Cấu trúc dữ liệu**: học cách tổ chức dữ liệu bằng mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, kết hợp bất biến và phân tích thời gian/bộ nhớ để lựa chọn đúng cấu trúc cho bài toán.

## 2. Định nghĩa cây Cartesian

Cho mảng `A[0..n-1]`. Một **min-Cartesian tree** là cây nhị phân có đúng `n` nút, mỗi nút ứng với một **vị trí** `i` của mảng, thỏa:

**Bất biến 1 — in-order theo chỉ số:**

Khi duyệt **trái → nút → phải**, ta thu được các chỉ số:

```text
0, 1, 2, ..., n-1
```

**Bất biến 2 — min-heap theo giá trị:**

Với mỗi cạnh từ cha `p` xuống con `c`:

\[
\boxed{A[p]\le A[c].}
\]

Nếu muốn kết quả cực tiểu được chọn **theo một quy tắc ổn định khi bằng nhau**, ta có thể tăng khóa ưu tiên thành cặp:

\[
\boxed{K(i)=(A[i],i),}
\]

so sánh theo thứ tự từ điển. Khi đó:

\[
\boxed{K(parent)<K(child)}
\]

với mọi cạnh, vì mỗi chỉ số `i` là duy nhất. Cây này trả về **vị trí xuất hiện đầu tiên (bên trái nhất)** khi nhiều giá trị cùng nhỏ nhất.

### Nút biểu diễn vị trí, không chỉ giá trị

Nếu mảng `[5,5,5]`, cây phải chứa **ba nút khác nhau** có chỉ số `0,1,2`, dù giá trị bằng nhau. Do đó, định danh của nút nên là **chỉ số gốc** hoặc một ID riêng, không phải chỉ là `A[i]`.

### Cây Cartesian không nhất thiết cân bằng

Một min-Cartesian tree của mảng tăng dần `[1,2,3,4,5]` có thể là một đường chỉ gồm các **con phải**. Độ cao lúc ấy `\Theta(n)`.

**Không** được suy luận rằng cứ là “cây” thì tìm LCA hoặc truy vấn luôn `O(\log n)`. Với cây Cartesian, cần chọn thuật toán tiền xử lý phù hợp để có hiệu năng truy vấn tốt ngay cả khi hình dạng cây lệch.

## 3. Ví dụ cụ thể với năm phần tử

Cho:

```text
index:   0  1  2  3  4
A:       4  2  5  1  3
```

Giá trị nhỏ nhất toàn mảng là `1` tại chỉ số `3`, nên **nút `3` làm gốc**. Bên trái chỉ số `3` là đoạn `[4,2,5]`, có min tại `1`, nên `1` là gốc cây trái. Bên phải chỉ số `3` chỉ có `3` tại chỉ số `4`, nên nút `4` là cây phải.

```text
                             (3: 1)
                            /      \
                        (1: 2)    (4: 3)
                        /    \
                     (0: 4) (2: 5)

Ký hiệu mỗi nút: (chỉ_số: giá_trị).
```

### Kiểm tra in-order

```text
Cây trái của (1:2) -> (0:4)  => chỉ số 0
Nút (1:2)                    => chỉ số 1
Cây phải của (1:2) -> (2:5) => chỉ số 2
Gốc (3:1)                   => chỉ số 3
Cây phải -> (4:3)           => chỉ số 4

Kết quả: 0,1,2,3,4
```

### Kiểm tra heap-order

```text
A[3]=1 <= A[1]=2
A[3]=1 <= A[4]=3
A[1]=2 <= A[0]=4
A[1]=2 <= A[2]=5
```

Cây này thỏa **đồng thời** hai bất biến, không phải một BST theo giá trị `A[i]`; giá trị `4` có thể nằm ở cây trái của giá trị `2` mà không vi phạm, vì BST-order ở đây áp dụng cho **chỉ số**.

## 4. Dựng cây theo định nghĩa đệ quy

Cách đơn giản nhất để hiểu cấu trúc là:

1. Nếu đoạn `[l,r]` rỗng thì trả nút rỗng.
2. Tìm vị trí `k` có giá trị nhỏ nhất trong đoạn `A[l..r]`.
3. Tạo nút `k`.
4. Dựng cây trái từ `A[l..k-1]`.
5. Dựng cây phải từ `A[k+1..r]`.

### Mã giả

```text
BUILD_SLOW(A, l, r):
    if l > r:
        return null

    k = vị trí cực tiểu của A[l..r]
        # Nếu bằng nhau, chọn chỉ số nhỏ nhất.

    node = Node(index=k)
    node.left  = BUILD_SLOW(A,l,k-1)
    node.right = BUILD_SLOW(A,k+1,r)
    return node
```

### Đúng đắn dễ nhận thấy

- Chọn min làm gốc bảo đảm heap-order giữa gốc và tất cả phần tử trong hai cây con.
- Phân đoạn theo **chỉ số** bảo đảm in-order đúng thứ tự ban đầu.
- Tiếp tục đệ quy giữ tính chất ở từng cây con.

### Nhưng chi phí chưa tốt

Mỗi lời gọi có thể quét toàn đoạn để tìm min. Với một mảng tăng dần, ta quét độ dài:

\[
n+(n-1)+(n-2)+\cdots+1=\Theta(n^2).
\]

Vì vậy, thuật toán đệ quy này có thể tốn **`\Theta(n^2)` thời gian**, mặc dù đầu ra chỉ có `n` nút. Nó hữu ích để hiểu định nghĩa, nhưng **không phải cách xây hiệu quả nhất**.

## 5. Tính duy nhất và quy tắc xử lý giá trị trùng

Nếu **mọi giá trị khác nhau**, min-Cartesian tree là **duy nhất**: phần tử nhỏ nhất phải là gốc; bên trái và bên phải gốc có những đoạn chỉ số cố định; áp dụng lập luận đệ quy.

Nếu có **giá trị bằng nhau**, điều kiện `A[parent]\le A[child]` **chưa đủ** để chọn duy nhất một cây.

Ví dụ với `A=[2,2]`:

```text
Phương án 1:                Phương án 2:

     (0:2)                      (1:2)
        \                       /
       (1:2)                 (0:2)

Hai cây đều cho in-order [0,1]
và đều thỏa heap-order không nghiêm ngặt.
```

### Chọn min bên trái nhất

Một chính sách phổ biến là ưu tiên **chỉ số nhỏ hơn** khi giá trị bằng nhau:

\[
\boxed{K(i)=(A[i],i).}
\]

Đây là một **thứ tự toàn phần** trên các vị trí nếu `A[i]` có phép so sánh nhất quán. Phần tử đạt min của đoạn sẽ được chọn ở **vị trí trái nhất**.

Với `[2,2]`, nút `0` làm gốc và nút `1` làm con phải.

### Chọn min bên phải nhất

Có thể dùng:

\[
K_{\mathrm{rightmost}}(i)=(A[i],-i),
\]

hoặc điều chỉnh quy tắc so sánh trong thuật toán stack. Khi hai giá trị bằng nhau, nút **có chỉ số lớn hơn** sẽ có ưu tiên cao hơn.

Hai quy tắc đều hợp lệ nếu được áp dụng **nhất quán** ở toàn bộ quá trình xây/truy vấn. Bài này chọn **trái nhất** để kết quả chỉ số RMQ có nghĩa xác định.

## 6. Xây cây tuyến tính bằng ngăn xếp đơn điệu

Ta có thể xây min-Cartesian tree trong **`O(n)` thời gian** bằng một **stack các chỉ số**.

Ý tưởng: duyệt mảng **từ trái sang phải**. Stack lưu một đường biên phải của cây đã xây, với các khóa `K(i)=(A[i],i)` tăng dần theo đường stack.

Khi đọc phần tử `A[i]`:

1. Pop khỏi stack các nút ở cuối có `A[stack.top]>A[i]`.
2. Ghi nhớ **nút cuối cùng bị pop**, gọi là `last`.
3. Nếu stack vẫn còn, nút mới `i` trở thành **con phải** của phần tử trên đỉnh stack.
4. Nếu `last` tồn tại, `last` trở thành **con trái** của nút mới `i`.
5. Đẩy `i` vào stack.

### Vì sao dùng dấu `>`, không phải `>=`?

Ta muốn **min bên trái nhất**. Vì đang duyệt theo chỉ số tăng, một nút cũ có giá trị **bằng** nút mới phải được giữ đứng trước và có ưu tiên cao hơn.

Do đó, chỉ pop khi:

\[
A[stack.top]>A[i].
\]

Nếu pop cả khi bằng nhau (`>=`), ta sẽ ưu tiên phần tử **xuất hiện bên phải** trong các nhóm bằng nhau, tương ứng một chính sách hòa khác.

### Mã giả

```text
BUILD_CARTESIAN(A):
    n = length(A)
    left  = array(n, -1)
    right = array(n, -1)
    parent= array(n, -1)
    stack = empty list

    for i from 0 to n-1:
        last = -1

        while stack not empty and A[stack.top] > A[i]:
            last = stack.pop()

        if stack not empty:
            p = stack.top
            right[p] = i
            parent[i] = p

        if last != -1:
            left[i] = last
            parent[last] = i

        stack.push(i)

    root = stack[0] if stack nonempty else -1
    return root, left, right, parent
```

**Điểm tinh tế:** một nút `last` vừa bị pop có thể từng là **con phải** của một nút khác. Khi nút mới `i` được gắn làm con phải, liên kết cũ được thay thế; `last` được chuyển thành **con trái của `i`**. Phải cập nhật `parent[last]=i`, nếu không bảng cha có thể sai dù bảng con nhìn có vẻ đúng.

## 7. Theo dõi ngăn xếp từng bước

Xây cây cho `A=[4,2,5,1,3]`.

| Bước `i` | `A[i]` | Các chỉ số bị pop | Stack sau bước | Liên kết mới/được thay |
|---:|---:|---|---|---|
| 0 | 4 | Không | `[0]` | Nút 0 tạm là gốc |
| 1 | 2 | `0` | `[1]` | `left[1]=0` |
| 2 | 5 | Không | `[1,2]` | `right[1]=2` |
| 3 | 1 | `2,1` | `[3]` | `left[3]=1`, con 2 vẫn là con phải của 1 |
| 4 | 3 | Không | `[3,4]` | `right[3]=4` |

Kết quả:

```text
root=3

left:
  left[3]=1
  left[1]=0

right:
  right[1]=2
  right[3]=4

parent:
  parent[3]=-1
  parent[1]=3
  parent[0]=1
  parent[2]=1
  parent[4]=3
```

Đúng với cây ở phần 3.

### Ví dụ có các giá trị bằng nhau

```text
A=[2,2,1,2]

i=0: stack=[0]
i=1: A[0] == A[1], KHÔNG pop -> right[0]=1
i=2: pop 1, pop 0 (vì 2 > 1) -> left[2]=0
i=3: không pop -> right[2]=3

Cây:
        (2:1)
        /   \
     (0:2) (3:2)
        \
        (1:2)
```

Truy vấn `RMQ(0,1)` phải trả **chỉ số 0** (cực tiểu bên trái nhất) dù cả `A[0]` và `A[1]` đều bằng `2`.

## 8. Vì sao xây bằng stack có O(n) thời gian?

Vòng `while` trong thuật toán có thể pop **nhiều** phần tử trong một bước. Ví dụ, khi đọc một giá trị nhỏ hơn toàn bộ các giá trị trước, nó có thể pop gần hết stack.

Nhưng mỗi chỉ số:

- Được **push đúng một lần**.
- Bị **pop nhiều nhất một lần**.
- Chỉ tham gia một số lượng hằng số phép gán/so sánh ngoài các thao tác stack.

Vì có tối đa `n` lần push và `n` lần pop:

\[
\boxed{T_{\mathrm{build}}=O(n).}
\]

Thuật toán cần:

- `O(n)` ô cho `left`, `right` và `parent`.
- `O(n)` ô trong stack trường hợp xấu nhất, chẳng hạn mảng tăng dần.

Vì thế:

\[
\boxed{S_{\mathrm{build}}=O(n).}
\]

Đây là **phân tích khấu hao** cho tổng số lần pop/push, **không** khẳng định mỗi bước của vòng `for` tốn `O(1)` trường hợp xấu nhất.

### Một ngộ nhận cần tránh

“Có một vòng `while` bên trong `for` thì chắc chắn `O(n^2)`.” Điều này sai trong các thuật toán stack đơn điệu, vì số lần phần tử có thể tham gia vòng `while` bị chặn. **Hãy đếm tổng số push/pop**, không nhân máy móc số vòng lặp lồng nhau.

## 9. Mã Python xây min-Cartesian tree

Đoạn mã dưới tạo các mảng `left`, `right`, `parent` và chỉ số `root`. Nó không dùng đệ quy, nên ngay cả khi cây hình thành một đường thẳng, **bước xây** vẫn không gặp giới hạn độ sâu recursion của Python.

```python
from dataclasses import dataclass


@dataclass
class CartesianTree:
    values: list[int]
    root: int
    left: list[int]
    right: list[int]
    parent: list[int]


def build_min_cartesian(values: list[int]) -> CartesianTree:
    a = list(values)  # Chụp dữ liệu tĩnh; không dùng list ngoài có thể sửa.
    n = len(a)
    left = [-1] * n
    right = [-1] * n
    parent = [-1] * n
    stack: list[int] = []

    for i, value in enumerate(a):
        last = -1
        while stack and a[stack[-1]] > value:
            last = stack.pop()

        if stack:
            p = stack[-1]
            right[p] = i
            parent[i] = p

        if last != -1:
            left[i] = last
            parent[last] = i

        stack.append(i)

    root = stack[0] if stack else -1
    return CartesianTree(a, root, left, right, parent)


tree = build_min_cartesian([4, 2, 5, 1, 3])
print(tree.root)    # 3
print(tree.left)    # [-1, 0, -1, 1, -1]
print(tree.right)   # [-1, 2, -1, 4, -1]
print(tree.parent)  # [1, 3, 1, -1, 3]
```

### Vì sao sao chép `values` vào `a`?

Vì cây Cartesian của phần này là **cấu trúc tĩnh**, các mảng liên kết được xây theo giá trị ban đầu. Nếu caller sửa trực tiếp danh sách `values` bên ngoài sau khi xây, cấu trúc không tự cập nhật.

Việc `a=list(values)` giúp nội dung trong object tách khỏi **danh sách bên ngoài**. Tuy nhiên, `CartesianTree.values` vẫn là một `list` có thể sửa từ phía người dùng; trong code production, nên che giấu dữ liệu hoặc dùng một kiểu immutable nếu muốn cưỡng chế bất biến.

## 10. Kiểm tra ba bất biến của cây vừa xây

Một cây min-Cartesian hợp lệ phải đồng thời thỏa:

1. **Có đúng một gốc** khi `n>0`, và `parent[root]=-1`.
2. **In-order** của cây trả các chỉ số `0,1,\ldots,n-1`.
3. **Heap-order** theo cặp `(A[i],i)`, để buộc tie-break bên trái nhất.

Ngoài ra cần kiểm tra:

- Hai con của một nút phải có `parent` trỏ về chính nút ấy.
- Không có chỉ số con bất hợp lệ hoặc chu trình.
- Mỗi nút xuất hiện **đúng một lần** trong cây.

### Hàm kiểm tra không dùng recursion

```python
def validate_cartesian(tree: CartesianTree) -> bool:
    a, root = tree.values, tree.root
    left, right, parent = tree.left, tree.right, tree.parent
    n = len(a)

    if len(left) != n or len(right) != n or len(parent) != n:
        return False
    if n == 0:
        return root == -1
    if not 0 <= root < n or parent[root] != -1:
        return False

    visited: set[int] = set()
    stack = [root]

    while stack:
        u = stack.pop()
        if u in visited or not 0 <= u < n:
            return False
        visited.add(u)

        for child in (left[u], right[u]):
            if child == -1:
                continue
            if not 0 <= child < n:
                return False
            if parent[child] != u:
                return False
            if (a[u], u) >= (a[child], child):
                return False
            stack.append(child)

    if len(visited) != n:
        return False

    # In-order lặp; tránh stack overflow trên cây lệch.
    order: list[int] = []
    walk_stack: list[int] = []
    current = root
    while current != -1 or walk_stack:
        while current != -1:
            walk_stack.append(current)
            current = left[current]
        current = walk_stack.pop()
        order.append(current)
        current = right[current]

    return order == list(range(n))


assert validate_cartesian(build_min_cartesian([4, 2, 5, 1, 3]))
assert validate_cartesian(build_min_cartesian([2, 2, 1, 2]))
assert validate_cartesian(build_min_cartesian([]))
```

Chạy `validate_cartesian` mất **`O(n)` thời gian và bộ nhớ phụ**, phù hợp cho kiểm thử/debug hơn là gọi liên tục sau mỗi truy vấn RMQ.

## 11. RMQ cần định nghĩa rõ trả về giá trị hay vị trí

Cùng một đề bài có thể yêu cầu hai dạng kết quả:

**RMQ-value:**

\[
\boxed{RMQ_{\mathrm{value}}(l,r)=\min_{l\le i\le r}A[i].}
\]

**RMQ-index theo quy tắc trái nhất:**

\[
\boxed{RMQ_{\mathrm{index}}(l,r)
=\min\{i\in[l,r]:A[i]=RMQ_{\mathrm{value}}(l,r)\}.}
\]

Ví dụ:

```text
A = [4, 1, 3, 1, 5]
RMQ_value(0,4) = 1
RMQ_index(0,4) = 1  # Không phải 3.
RMQ_index(2,4) = 3
```

### Quy ước về đoạn

Trong bài:

- `l` và `r` là **chỉ số 0-based**.
- Đoạn là **đóng** `[l,r]`.
- Điều kiện hợp lệ: `0\le l\le r<n`.
- **Đoạn rỗng không có cực tiểu**, nên `query` phải từ chối.

Nếu dùng API khác theo đoạn nửa kín `[l,r)`, phải chuyển thành `[l,r-1]` khi `l<r`, hoặc định nghĩa kết quả rỗng riêng; không thể mượn công thức và bỏ qua lỗi lệch một đơn vị.

## 12. Tổ tiên chung gần nhất (LCA) là gì?

Trong cây có gốc, nút `u` là **tổ tiên** của `v` nếu `u` nằm trên đường từ gốc tới `v` (thường tính cả chính `v`).

**Lowest common ancestor — LCA(u,v)** là tổ tiên chung của `u` và `v` nằm **sâu nhất** trong cây.

Ví dụ với cây phần 3:

```text
                            (3:1)
                           /     \
                        (1:2)   (4:3)
                       /   \
                    (0:4) (2:5)
```

Ta có:

- `LCA(0,2)=1`.
- `LCA(2,4)=3`.
- `LCA(1,2)=1` vì một nút là tổ tiên của nút kia.
- `LCA(4,4)=4`.

### LCA không mặc nhiên là O(1)

Nếu chỉ có `parent`, ta có thể đi lên để tìm LCA trong `O(h)` bước, với `h` là chiều cao cây. Đối với cây Cartesian lệch, `h` có thể là `\Theta(n)`.

Muốn nhiều truy vấn RMQ nhanh trên một mảng **không thay đổi**, ta có thể **tiền xử lý LCA** bằng một kỹ thuật khác, chẳng hạn Euler tour + sparse table.

## 13. Định lý trung tâm: RMQ(l,r) chính là LCA(l,r)

Xét **min-Cartesian tree** được xây với quy tắc phá hòa `K(i)=(A[i],i)`.

Với mọi `0\le l\le r<n`:

\[
\boxed{
RMQ_{\mathrm{index}}(l,r)
=LCA_{\mathrm{CartesianTree}}(l,r).
}
\]

Và:

\[
\boxed{
RMQ_{\mathrm{value}}(l,r)
=A[LCA_{\mathrm{CartesianTree}}(l,r)].
}
\]

### Chứng minh bằng hai bất biến

Đặt `w=LCA(l,r)`.

**Bước 1 — chỉ số của `w` nằm trong `[l,r]`.** Vì thứ tự in-order là `0,1,\ldots,n-1`, nếu `w` không trùng `l` hoặc `r` thì `l` và `r` phải nằm ở **hai nhánh khác nhau** của `w`. Khi ấy:

\[
l<w<r.
\]

Nếu `w=l` hoặc `w=r`, kết luận `w\in[l,r]` cũng đúng.

**Bước 2 — tất cả vị trí từ `l` đến `r` thuộc cây con của `w`.** Một cây con nhị phân chiếm **một khoảng liên tục trong in-order**. Cây con gốc `w` chứa cả `l` và `r`, nên chứa mọi chỉ số nằm giữa.

**Bước 3 — giá trị tại `w` không lớn hơn mọi phần tử trong đoạn.** Từ heap-order, khóa ưu tiên `K(w)` không lớn hơn `K(i)` của mọi hậu duệ `i`. Vì tất cả `i\in[l,r]` nằm trong cây con `w`:

\[
(A[w],w)\le (A[i],i),\quad \forall i\in[l,r].
\]

Suy ra `A[w]` là cực tiểu trên đoạn; nếu có nhiều phần tử bằng nhau, `w` có chỉ số nhỏ nhất theo tie-break.

**Kết luận:** nút `w` chính là vị trí RMQ bên trái nhất.

### Vì sao định lý đặc biệt hữu ích?

Nó biến bài toán trên **mảng** thành bài toán trên **cây**. Cấu trúc cây được xây **một lần**; sau đó nhiều truy vấn cực tiểu có thể được giải bằng một bộ máy LCA, không phải quét lại đoạn.

## 14. Mô phỏng RMQ bằng LCA

Với `A=[4,2,5,1,3]`, xét:

| Truy vấn | Hai nút | LCA | Vị trí min | Giá trị min |
|---|---|---|---|---|
| `RMQ(0,2)` | `0` và `2` | `1` | `1` | `2` |
| `RMQ(0,4)` | `0` và `4` | `3` | `3` | `1` |
| `RMQ(2,4)` | `2` và `4` | `3` | `3` | `1` |
| `RMQ(1,2)` | `1` và `2` | `1` | `1` | `2` |
| `RMQ(4,4)` | `4` và `4` | `4` | `4` | `3` |

Lưu ý `RMQ(0,2)` không lấy giá trị min của **toàn cây** `1` tại chỉ số `3`, bởi vị trí `3` **không nằm trong đoạn** `[0,2]`. LCA của **đúng hai đầu mút** bảo đảm chọn một nút chỉ số nằm trong đoạn.

### Một hiểu nhầm thường gặp

“Vì gốc cây là min toàn mảng, RMQ của đoạn nào cũng lấy gốc.” Sai. Cần tìm **LCA của hai nút đầu mút**, không nhất thiết là gốc toàn cây.

## 15. Euler tour biến LCA thành RMQ trên độ sâu

Một cách tiền xử lý LCA cho cây **tĩnh** là duyệt Euler.

Bắt đầu ở gốc, ghi lại nút mỗi lần:

- **Đi vào** nút.
- **Quay về** nút sau khi kết thúc một cây con.

Đồng thời ghi độ sâu `depth` tại mỗi lần xuất hiện. Với cây có `n` nút, Euler tour cổ điển đi qua `n-1` cạnh **mỗi cạnh hai chiều**, nên tạo:

\[
\boxed{|Euler|=2n-1}\quad (n\ge1).
\]

Đặt:

- `euler[t]`: chỉ số nút tại bước thứ `t` của tour.
- `depths[t]`: độ sâu của nút đó.
- `first[v]`: vị trí xuất hiện **đầu tiên** của nút `v` trong tour.

### Định lý Euler cho LCA

Cho `p=first[u]` và `q=first[v]`, đổi chỗ để `p\le q`. Khi đó:

\[
\boxed{
LCA(u,v)=euler[
\operatorname*{arg\,min}_{t\in[p,q]}depths[t]
].
}
\]

**Trực giác:** từ lần thăm đầu của `u` tới lần thăm đầu của `v`, tour phải đi lên đủ xa để tới **tổ tiên chung gần nhất** rồi mới đi xuống nhánh chứa `v`. Không cần đi lên cao hơn tổ tiên chung ấy trong khoảng tour được xét.

Điều này tạo một chuỗi biến đổi:

```text
RMQ trên mảng A
    |
    v
LCA trên cây Cartesian của A
    |
    v
RMQ trên mảng độ sâu của Euler tour
```

Đây là quan hệ hai chiều rất quan trọng giữa các bài toán **RMQ** và **LCA** trên cấu trúc tĩnh.

## 16. Euler tour chi tiết trên cây minh họa

Với cây:

```text
                3 (depth=0)
               / \
         1 (d=1)  4 (d=1)
         /   \
    0 (d=2) 2 (d=2)
```

Duyệt **nhánh trái trước nhánh phải**:

```text
euler:  [3, 1, 0, 1, 2, 1, 3, 4, 3]
depths: [0, 1, 2, 1, 2, 1, 0, 1, 0]
index:   0  1  2  3  4  5  6  7  8

first[3] = 0
first[1] = 1
first[0] = 2
first[2] = 4
first[4] = 7
```

Lấy `LCA(0,2)`:

```text
p = first[0] = 2
q = first[2] = 4

Đoạn depths[2:5] = [2,1,2]
Min depth = 1 tại Euler index 3
euler[3] = 1

LCA(0,2) = 1
```

Lấy `LCA(2,4)`:

```text
p = first[2] = 4
q = first[4] = 7

Đoạn depths[4:8] = [2,1,0,1]
Min depth = 0 tại Euler index 6
euler[6] = 3

LCA(2,4)=3
```

Như vậy, không cần đọc lại các giá trị `A[i]` trong lúc tìm LCA; bộ máy LCA chỉ thao tác với **mảng độ sâu** và các chỉ số tour.

## 17. Sparse table trên độ sâu: RMQ O(1) sau tiền xử lý

Đối với **mảng tĩnh** `D`, sparse table lưu chỉ số chứa min trên mọi đoạn có độ dài `2^k`:

\[
ST[k][i]=\operatorname*{arg\,min}_{j\in[i,i+2^k-1]}D[j].
\]

Khởi tạo:

\[
ST[0][i]=i.
\]

Quy hoạch động:

\[
ST[k][i]=\operatorname*{arg\,min}
\bigl(D[ST[k-1][i]],\ D[ST[k-1][i+2^{k-1}]]\bigr).
\]

### Truy vấn một đoạn bất kỳ

Với đoạn đóng `[l,r]` có chiều dài `q=r-l+1`, chọn:

\[
k=\lfloor\log_2 q\rfloor,\quad w=2^k.
\]

Hai đoạn:

```text
[l, l+w-1]
[r-w+1, r]
```

phủ toàn bộ `[l,r]` và có thể **giao nhau**. Vì `min` là phép **idempotent** (`min(x,x)=x`), việc một phần tử thuộc cả hai đoạn không làm sai giá trị cực tiểu.

Lấy chỉ số `p=ST[k][l]` và `q=ST[k][r-w+1]`, so sánh `D[p]` với `D[q]` để trả chỉ số có độ sâu nhỏ hơn.

### Độ phức tạp

Với một mảng độ dài `N`:

- Xây bảng: **`O(N\log N)`** thời gian và bộ nhớ.
- Truy vấn min một đoạn: **`O(1)`** phép đọc/so sánh.

Trong Euler tour của cây Cartesian, `N=2n-1`, nên sau tiền xử lý:

\[
\boxed{
\text{Build Cartesian }O(n)
+\text{ Euler }O(n)
+\text{ sparse }O(n\log n).
}
\]

Mỗi truy vấn RMQ trên mảng gốc chỉ cần tìm **LCA bằng một lần RMQ độ sâu**, đạt **`O(1)` thời gian**.

**Quan trọng:** bộ nhớ là `O(n\log n)`, **không phải `O(n)`** trong cách cài sparse table đơn giản này. Có những kỹ thuật RMQ/LCA tuyến tính tiên tiến hơn, nhưng chúng không phải sparse table chuẩn.

## 18. Cài Euler tour không đệ quy cho cây Cartesian

Một cây Cartesian có thể là **đường thẳng dài `n` nút**. Nếu dùng DFS đệ quy Python để xây Euler tour, dữ liệu như `[1,2,\ldots,n]` có thể làm vượt giới hạn recursion.

Vì vậy, ví dụ sử dụng **ngăn xếp tường minh** với ba trạng thái:

- `phase=0`: vừa tới nút, ghi lần xuất hiện, xử lý cây trái.
- `phase=1`: đã xử lý xong cây trái, ghi nút lần nữa nếu có đi qua nhánh trái, rồi xử lý cây phải.
- `phase=2`: đã xử lý xong cây phải, ghi nút lần nữa.

Mỗi nút sẽ được ghi khi bắt đầu, và được ghi lại mỗi lần trở về từ một con. Vì có đúng `n-1` cạnh trong cây, tổng số lần ghi là `2n-1` khi `n>0`.

### Mã Python (tiếp nối phần 9)

```python
def build_euler_tour(
    tree: CartesianTree,
) -> tuple[list[int], list[int], list[int]]:
    """Trả euler_nodes, depths và first_occurrence."""
    n = len(tree.values)
    first = [-1] * n
    euler: list[int] = []
    depths: list[int] = []

    if n == 0:
        return euler, depths, first

    # (node_index, depth, phase)
    work: list[tuple[int, int, int]] = [(tree.root, 0, 0)]

    while work:
        u, depth, phase = work.pop()

        if phase == 0:
            if first[u] == -1:
                first[u] = len(euler)
            euler.append(u)
            depths.append(depth)

            work.append((u, depth, 1))
            if tree.left[u] != -1:
                work.append((tree.left[u], depth + 1, 0))

        elif phase == 1:
            if tree.left[u] != -1:
                # Quay từ cây trái về nút u.
                euler.append(u)
                depths.append(depth)

            if tree.right[u] != -1:
                work.append((u, depth, 2))
                work.append((tree.right[u], depth + 1, 0))

        else:
            # Quay từ cây phải về nút u.
            euler.append(u)
            depths.append(depth)

    assert len(euler) == 2 * n - 1
    assert all(position != -1 for position in first)
    return euler, depths, first


tree = build_min_cartesian([4, 2, 5, 1, 3])
euler, depths, first = build_euler_tour(tree)
print(euler)   # [3, 1, 0, 1, 2, 1, 3, 4, 3]
print(depths)  # [0, 1, 2, 1, 2, 1, 0, 1, 0]
print(first)   # [2, 1, 4, 0, 7]
```

### Tại sao đây là Euler tour đúng?

Một nút được ghi ngay khi ta **đi vào** nó. Khi đi xong một cây con, ta phải quay về chính nút cha, nên ghi nút cha lần nữa. Thứ tự đẩy vào stack LIFO bảo đảm cây trái được duyệt trước cây phải. Kết quả trùng với Euler tour đệ quy nhưng dùng **`O(h)` stack tường minh** cho đường DFS, tránh giới hạn recursion của lời gọi hàm.

Chi phí:

\[
\boxed{T_{\mathrm{Euler}}=O(n),\quad S_{\mathrm{Euler}}=O(n).}
\]

Mảng Euler và độ sâu dài `2n-1`, còn mảng `first` dài `n`.

## 19. Sparse table lưu chỉ số nhỏ nhất trên đoạn độ sâu

Sparse table cần lưu **vị trí trong mảng Euler**, không chỉ lưu giá trị độ sâu. Nhờ vậy, từ chỉ số đạt độ sâu nhỏ nhất ta có thể truy ngược ra **nút LCA**.

Ở mỗi ô:

```text
table[k][i] = chỉ số t trong depths
              có độ sâu nhỏ nhất trên đoạn
              [i, i + 2**k - 1].
```

### Mã Python

```python
class DepthSparseTable:
    def __init__(self, depths: list[int]) -> None:
        self.depths = depths
        n = len(depths)
        self.logs = [0] * (n + 1)
        for length in range(2, n + 1):
            self.logs[length] = self.logs[length // 2] + 1

        self.table: list[list[int]] = []
        if n == 0:
            return

        self.table.append(list(range(n)))

        k = 1
        while (1 << k) <= n:
            previous = self.table[k - 1]
            half = 1 << (k - 1)
            width = 1 << k
            row: list[int] = []

            for start in range(n - width + 1):
                x = previous[start]
                y = previous[start + half]
                if depths[x] <= depths[y]:
                    row.append(x)
                else:
                    row.append(y)

            self.table.append(row)
            k += 1

    def argmin(self, left: int, right: int) -> int:
        """Vị trí min độ sâu trong đoạn ĐÓNG [left,right]."""
        n = len(self.depths)
        if not 0 <= left <= right < n:
            raise IndexError("Khoảng sparse table không hợp lệ")

        k = self.logs[right - left + 1]
        width = 1 << k
        x = self.table[k][left]
        y = self.table[k][right - width + 1]
        if self.depths[x] <= self.depths[y]:
            return x
        return y
```

### Vì sao cho phép hai đoạn chồng nhau?

`min` là phép **idempotent**: đưa một phần tử vào phép lấy min hai lần không thay kết quả. Do đó, chọn hai khối `2^k` phủ đoạn (và có thể trùng một phần) vẫn đúng.

Nếu ta thay `min` bằng **sum**, việc cộng hai khối chồng nhau sẽ **đếm đôi** phần giao, nên không thể dùng công thức hai khối chồng này. Đây là một khác biệt quan trọng giữa các phép tổng hợp trên đoạn.

### Truy vấn có độ sâu bằng nhau

Trong mã, nếu `depths[x]==depths[y]`, hàm chọn `x`. Đối với khoảng Euler dùng cho LCA, **mọi vị trí có độ sâu nhỏ nhất trên khoảng đều chỉ đến cùng nút LCA**, nên cách phá hòa độ sâu này không làm sai LCA.

## 20. Bộ giải RMQ từ cây Cartesian + Euler + sparse table

Ghép các hàm/lớp ở phần 9, 18 và 19 vào cùng một tệp Python, rồi bổ sung lớp:

```python
class CartesianRMQ:
    """Mảng tĩnh; RMQ trả vị trí min trái nhất."""

    def __init__(self, values: list[int]) -> None:
        self.tree = build_min_cartesian(values)
        self.euler, self.depths, self.first = build_euler_tour(
            self.tree
        )
        self.depth_rmq = DepthSparseTable(self.depths)

    def __len__(self) -> int:
        return len(self.tree.values)

    def lca(self, u: int, v: int) -> int:
        n = len(self)
        if not (0 <= u < n and 0 <= v < n):
            raise IndexError("Chỉ số nút ngoài miền")

        p = self.first[u]
        q = self.first[v]
        if p > q:
            p, q = q, p

        position = self.depth_rmq.argmin(p, q)
        return self.euler[position]

    def argmin(self, left: int, right: int) -> int:
        n = len(self)
        if not 0 <= left <= right < n:
            raise IndexError("Truy vấn RMQ phải là đoạn đóng không rỗng")
        return self.lca(left, right)

    def min_value(self, left: int, right: int) -> int:
        index = self.argmin(left, right)
        return self.tree.values[index]
```

### Cách sử dụng

```python
solver = CartesianRMQ([4, 2, 5, 1, 3])
print(solver.argmin(0, 2))     # 1
print(solver.min_value(0, 2)) # 2
print(solver.argmin(2, 4))     # 3
print(solver.min_value(2, 4)) # 1
print(solver.argmin(4, 4))     # 4
print(solver.lca(0, 2))        # 1

duplicates = CartesianRMQ([4, 1, 3, 1, 5])
print(duplicates.argmin(0, 4)) # 1: min bên trái nhất.
print(duplicates.argmin(2, 4)) # 3.

empty = CartesianRMQ([])
print(len(empty))             # 0
try:
    empty.min_value(0, 0)
except IndexError:
    print("Không có RMQ cho mảng rỗng")
```

### Hợp đồng dữ liệu tĩnh

Các mảng `left/right/parent` và sparse table được tạo **một lần**. Nếu thay đổi một phần tử trong dữ liệu gốc, kết quả có thể không còn đúng. Lớp `CartesianRMQ` **không hỗ trợ cập nhật**; tạo lại từ dữ liệu mới hoặc dùng cấu trúc động khác.

### Độ phức tạp tổng quát

| Bước | Thời gian | Bộ nhớ |
|---|---|---|
| Xây cây Cartesian với stack | `O(n)` | `O(n)` |
| Euler tour không đệ quy | `O(n)` | `O(n)` |
| Sparse table trên depths | `O(n\log n)` | `O(n\log n)` |
| `lca(u,v)` | `O(1)` | `O(1)` phụ khi truy vấn |
| `argmin(l,r)` | `O(1)` | `O(1)` phụ |
| `min_value(l,r)` | `O(1)` | `O(1)` phụ |

Với `n=0`, xây một cấu trúc rỗng hợp lệ, nhưng **không tồn tại đoạn truy vấn không rỗng**; mọi lời gọi RMQ phải báo lỗi theo API.

## 21. Một lời giải trực tiếp: sparse table trên mảng gốc

Với RMQ **tĩnh**, ta thậm chí **không cần cây Cartesian** nếu chỉ muốn lấy min của đoạn. Có thể xây sparse table trực tiếp trên `A`:

```text
ST[k][i] = chỉ số min của A[i .. i+2^k-1].
```

Vẫn có:

- Tiền xử lý `O(n\log n)`.
- Bộ nhớ `O(n\log n)`.
- Truy vấn `O(1)`.

### Mã Python tối giản, vẫn chọn min bên trái nhất

```python
class DirectSparseRMQ:
    def __init__(self, values: list[int]) -> None:
        self.values = tuple(values)
        n = len(self.values)
        self.logs = [0] * (n + 1)
        for i in range(2, n + 1):
            self.logs[i] = self.logs[i // 2] + 1

        self.table: list[list[int]] = []
        if n == 0:
            return

        self.table.append(list(range(n)))
        k = 1
        while (1 << k) <= n:
            prev = self.table[k - 1]
            half = 1 << (k - 1)
            width = 1 << k
            row = []
            for i in range(n - width + 1):
                x = prev[i]
                y = prev[i + half]
                row.append(
                    x if (self.values[x], x) <=
                         (self.values[y], y) else y
                )
            self.table.append(row)
            k += 1

    def argmin(self, left: int, right: int) -> int:
        n = len(self.values)
        if not 0 <= left <= right < n:
            raise IndexError("Đoạn RMQ không hợp lệ")
        k = self.logs[right - left + 1]
        width = 1 << k
        x = self.table[k][left]
        y = self.table[k][right - width + 1]
        return x if (self.values[x], x) <= (
            self.values[y], y
        ) else y


direct = DirectSparseRMQ([4, 1, 3, 1, 5])
print(direct.argmin(0, 4))  # 1.
print(direct.argmin(2, 4))  # 3.
```

### Vậy tại sao vẫn học cây Cartesian?

Vì cây Cartesian chỉ ra một **mối liên hệ cấu trúc sâu sắc** giữa:

- Thứ tự tuyến tính của mảng.
- Quan hệ bao hàm các đoạn có cực tiểu.
- Tổ tiên chung trên cây.
- RMQ trên Euler tour.

Nó còn là thành phần của nhiều thuật toán khác: **LCA**, phân tích đoạn, hình chữ nhật lớn nhất trong histogram, các cấu trúc dữ liệu succinct và các kỹ thuật truy vấn đoạn tĩnh nâng cao.

Nếu nhiệm vụ chỉ là “trả lời nhiều RMQ tĩnh nhanh, dễ cài”, sparse table trực tiếp thường là **baseline đơn giản hơn** so với dựng cây rồi duyệt Euler.

## 22. RMQ và LCA: hai bài toán gần tương đương

Ta vừa thấy:

\[
\boxed{\text{RMQ trên mảng}\longrightarrow
\text{LCA trên cây Cartesian}.}
\]

Chiều ngược lại:

\[
\boxed{\text{LCA trên cây}\longrightarrow
\text{RMQ trên độ sâu Euler tour}.}
\]

Vì vậy, trong bối cảnh **dữ liệu tĩnh** và mô hình truy vấn phù hợp, các lời giải hiệu quả cho một bài toán có thể được chuyển sang bài toán kia.

### Chi tiết quan trọng: độ sâu Euler chỉ thay đổi ±1

Trong Euler tour chuẩn:

- Đi xuống một cạnh: độ sâu tăng đúng `1`.
- Đi lên một cạnh: độ sâu giảm đúng `1`.

Do đó:

\[
\boxed{|depths[t+1]-depths[t]|=1}
\]

cho mọi cặp vị trí liên tiếp trong tour có ít nhất hai vị trí.

Đây là một **trường hợp đặc biệt của RMQ** gọi là *±1 RMQ*. Các thuật toán LCA tĩnh tiên tiến có thể khai thác tính chất này để đạt **`O(n)` thời gian và bộ nhớ tiền xử lý, `O(1)` mỗi truy vấn** trong mô hình RAM thích hợp, ví dụ các họ kỹ thuật phân khối và bảng mẫu.

**Không nhầm lẫn:** giải pháp **Euler + sparse table** ở phần 18–20 vẫn dùng **`O(n\log n)`** thời gian/bộ nhớ tiền xử lý. Việc mảng depths có tính ±1 **không tự làm sparse table chuẩn nhỏ xuống `O(n)`**.

## 23. Cartesian tree có giống treap không?

Hai cấu trúc có quan hệ nhưng không đồng nhất.

### Cây Cartesian cho mảng

- Thứ tự in-order được **cố định** bởi chỉ số `0..n-1`.
- Heap-order theo **giá trị `A[i]`** hoặc cặp `(A[i],i)`.
- Cây là một **hàm xác định từ mảng** nếu quy tắc hòa đã cố định.
- Có thể **rất lệch** nếu đầu vào tăng/giảm.
- Trọng tâm của bài là **RMQ tĩnh** và chứng minh quan hệ với LCA.

### Treap

- Có một thứ tự BST theo khóa hoặc chỉ số ẩn.
- Heap-order theo **priority ngẫu nhiên hoặc giá trị ưu tiên được cấp riêng**.
- Nhờ priority ngẫu nhiên độc lập, treap thường có chiều cao `O(\log n)` **kỳ vọng**.
- Có thể hỗ trợ các thao tác động như split/merge/insert/delete theo thiết kế.

### Một cách nhìn thống nhất

Cả hai là loại **Cartesian tree theo một thứ tự nền** và **một thứ tự ưu tiên khác**. Với treap, ưu tiên thường được chọn ngẫu nhiên để có cân bằng kỳ vọng; với RMQ Cartesian tree, ưu tiên chính là **giá trị dữ liệu cần hỏi cực tiểu**.

Không được tự dùng kết quả cân bằng kỳ vọng của **treap priority ngẫu nhiên** để kết luận cây Cartesian của một mảng bất kỳ có chiều cao `O(\log n)`.

## 24. Cây Cartesian min và max: hai hướng đối xứng

Đối với **range maximum query** (*RMQ max*, đôi khi viết RMaxQ), ta cần **max-Cartesian tree**:

- In-order vẫn trả đúng chỉ số `0..n-1`.
- Mỗi nút cha có giá trị **không nhỏ hơn** các con.
- Nếu hòa, dùng thứ tự ưu tiên bảo đảm **cực đại bên trái nhất**.

### Thay đổi ở ngăn xếp

Min-Cartesian tree với ưu tiên min bên trái:

```text
while stack and A[stack.top] > A[i]:
    pop
```

Max-Cartesian tree với ưu tiên max bên trái:

```text
while stack and A[stack.top] < A[i]:
    pop
```

Với phần tử bằng nhau, vẫn **không pop** nên nút có chỉ số nhỏ hơn là tổ tiên theo quy tắc hòa.

### Ví dụ max

```text
A = [4, 2, 5, 1, 3]

RMaxQ(0,2) = 5 tại chỉ số 2
RMaxQ(3,4) = 3 tại chỉ số 4
RMaxQ(0,4) = 5 tại chỉ số 2
```

Sau khi xây max-Cartesian tree, dùng định lý tương tự:

\[
\boxed{
\operatorname*{arg\,max}_{i\in[l,r]}A[i]
=LCA_{\mathrm{maxCartesian}}(l,r)
}
\]

với quy tắc hòa đã chọn. Bộ máy Euler + LCA không cần đổi: chỉ khác **cấu trúc cây ban đầu**.

## 25. Cập nhật giá trị: vì sao cây Cartesian tĩnh không phù hợp?

Giả sử:

```text
A = [4,2,5,1,3]
```

Cây min-Cartesian có gốc tại chỉ số `3` vì `A[3]=1`.

Bây giờ sửa:

```text
A[3] = 9
=> A = [4,2,5,9,3]
```

Cực tiểu toàn mảng lúc này là `2` tại chỉ số `1`, nên **gốc mới phải là nút 1**. Hình dạng cây có thể thay đổi đáng kể, ngay cả khi chỉ cập nhật **một** giá trị.

### Không đủ nếu chỉ đổi A[3] trong object

Cây và Euler tour trước đó được dựng từ thứ tự ưu tiên cũ. Sparse table trên độ sâu vẫn trả LCA **của cây cũ**, nên kết quả RMQ có thể sai.

Cách an toàn, đơn giản:

1. Cập nhật mảng gốc.
2. Xây lại cây Cartesian và cấu trúc LCA.

Chi phí theo bản cài ở bài: **`O(n\log n)` thời gian/bộ nhớ tiền xử lý** mỗi lần xây lại; quá đắt nếu có nhiều cập nhật.

### Nếu cần cập nhật động thì dùng gì?

**Segment tree** là lựa chọn phổ biến:

- Xây ban đầu: `O(n)` thời gian/bộ nhớ.
- Cập nhật `A[i]`: `O(\log n)`.
- Truy vấn min/max trên đoạn: `O(\log n)`.
- Có thể lưu cặp `(value,index)` để nhất quán với quy tắc cực trị bên trái nhất.

Một số cấu trúc Cartesian động chuyên dụng cũng tồn tại, nhưng không thể gán `O(\log n)` cho việc cập nhật một cây Cartesian bất kỳ **chỉ vì nó là cây**. Phải có thuật toán sửa/cân bằng và phân tích riêng.

## 26. So sánh các phương án cho RMQ

Gọi `n` là độ dài mảng, `Q` là số truy vấn, `U` là số lần cập nhật giá trị.

| Phương án | Xây ban đầu | Một RMQ | Một update | Bộ nhớ |
|---|---|---|---|---|
| Quét đoạn trực tiếp | `O(1)` | `O(r-l+1)`, xấu nhất `O(n)` | `O(1)` | `O(1)` phụ |
| Sparse table trực tiếp | `O(n\log n)` | `O(1)` | Phải xây lại khi đổi dữ liệu | `O(n\log n)` |
| Cartesian + Euler + sparse | `O(n\log n)` | `O(1)` | Phải xây lại trong bản cài này | `O(n\log n)` |
| Segment tree | `O(n)` | `O(\log n)` | `O(\log n)` | `O(n)` |
| Sqrt decomposition | `O(n)` | `O(\sqrt n)` | `O(\sqrt n)` hoặc cận khác tùy cách giữ block | `O(\sqrt n)` metadata ngoài mảng |
| LCA/RMQ tĩnh tối ưu tuyến tính | `O(n)` | `O(1)` | Không tự hỗ trợ | `O(n)` |

### Chọn theo workload

**Ít truy vấn, rất ít dữ liệu:** quét trực tiếp có thể đủ, không cần tiền xử lý.

**Rất nhiều truy vấn, không cập nhật:** sparse table trực tiếp đơn giản, thường là baseline tốt.

**Muốn khai thác quan hệ cấu trúc RMQ–LCA hoặc giải nhiều bài toán trên cây:** Cartesian tree là công cụ tư duy và thành phần thuật toán mạnh.

**Có cập nhật điểm thường xuyên:** segment tree thường thuận tiện và có cận rõ ràng.

**Muốn O(1) truy vấn và tiết kiệm bộ nhớ tuyến tính cho mảng tĩnh lớn:** tìm hiểu các kỹ thuật RMQ/LCA tĩnh tuyến tính chuyên biệt; chúng phức tạp hơn và cần đánh giá hằng số thực tế.

### Fenwick tree có thay được segment tree cho range min tùy ý?

Fenwick tree thông dụng được thiết kế cho **tổng tiền tố** và point updates. Với phép cộng, lấy hiệu hai tiền tố khôi phục tổng đoạn. Nhưng `min` **không có phép nghịch đảo** như phép cộng; không thể lấy `prefix_min(r) - prefix_min(l-1)` để ra min của đoạn `[l,r]`.

Có những biến thể Fenwick cho một số dạng cập nhật/truy vấn cực trị với giả định riêng, nhưng **không thể thay segment tree cho RMQ động tổng quát chỉ bằng cách đổi phép cộng thành min**.

## 27. Kiểm thử đối chiếu: mọi đoạn đều phải đúng

Một cây Cartesian có thể có **in-order đúng** nhưng vẫn sai **heap-order**, hoặc có heap-order đúng nhưng bảng `parent` lệch. Do đó, nên kiểm tra cả cấu trúc cây lẫn **kết quả RMQ**.

Một mô hình tham chiếu dễ tin cậy là duyệt thẳng từng đoạn:

```python
def slow_argmin(a: list[int], left: int, right: int) -> int:
    """Min bên trái nhất trên [left,right]."""
    return min(
        range(left, right + 1),
        key=lambda i: (a[i], i),
    )
```

### Kiểm thử tất cả đoạn của một mảng ngắn

```python
def test_one_array(a: list[int]) -> None:
    tree = build_min_cartesian(a)
    assert validate_cartesian(tree)

    solver = CartesianRMQ(a)
    direct = DirectSparseRMQ(a)
    assert len(solver) == len(a)

    if a:
        assert len(solver.euler) == 2 * len(a) - 1
        assert all(
            abs(solver.depths[i] - solver.depths[i - 1]) == 1
            for i in range(1, len(solver.depths))
        )
    else:
        assert solver.euler == []
        return

    for left in range(len(a)):
        for right in range(left, len(a)):
            expected = slow_argmin(a, left, right)
            assert solver.argmin(left, right) == expected
            assert solver.min_value(left, right) == a[expected]
            assert direct.argmin(left, right) == expected
            assert solver.lca(left, right) == expected


for data in [
    [],
    [7],
    [1, 2, 3, 4, 5],
    [5, 4, 3, 2, 1],
    [5, 5, 5, 5],
    [2, 2, 1, 2],
    [4, 2, 5, 1, 3],
    [4, 1, 3, 1, 5],
    [-3, 0, -3, 7, -4],
]:
    test_one_array(data)
```

### Vì sao cần cả mảng tăng và giảm?

- Mảng tăng dần tạo cây **lệch phải**.
- Mảng giảm dần tạo cây **lệch trái**.
- Mảng toàn phần tử bằng nhau kiểm tra quy tắc phá hòa.
- Mảng có âm/dương/giá trị lặp kiểm tra so sánh chính xác.
- Mảng rỗng, một phần tử kiểm tra các trường hợp cơ sở.

Bộ giải Euler của bài không dùng recursion khi dựng tour, nên phù hợp để **kiểm tra trên cây lệch dài** mà không gặp lỗi do đệ quy sâu ở bước Euler. Dù vậy, sparse table tiêu tốn `O(n\log n)` bộ nhớ; không nên tạo dữ liệu quá lớn chỉ để kiểm thử bằng tất cả `O(n^2)` đoạn.

### Kiểm thử ngẫu nhiên

Với một bộ sinh ngẫu nhiên có seed cố định, hãy tạo nhiều mảng ngắn từ một **miền giá trị nhỏ** như `[-3,3]` để tăng xác suất giá trị trùng. Sau đó gọi `test_one_array` cho từng mảng. Những lỗi tie-break thường bộc lộ dễ hơn khi giá trị có nhiều lần lặp.

## 28. Một ứng dụng: hình chữ nhật lớn nhất trong histogram

Cho các thanh histogram có chiều rộng `1`:

```text
heights = [2,1,5,6,2,3]
```

Một hình chữ nhật phủ đoạn `[l,r]` có chiều cao tối đa bằng **thanh thấp nhất trong đoạn**. Do đó, diện tích tốt nhất dùng đúng đoạn ấy là:

\[
\boxed{
Area(l,r)=(r-l+1)\cdot\min_{i\in[l,r]}heights[i].
}
\]

Phân chia dựa trên vị trí cực tiểu `k=RMQ\_index(l,r)`:

1. Hình chữ nhật tốt nhất **phủ toàn đoạn** có diện tích `(r-l+1)\cdot heights[k]`.
2. Hình chữ nhật tốt nhất **nằm hẳn bên trái** ở đoạn `[l,k-1]`.
3. Hình chữ nhật tốt nhất **nằm hẳn bên phải** ở đoạn `[k+1,r]`.

Ta có truy hồi:

\[
\boxed{
F(l,r)=\max\bigl(
(r-l+1)heights[k],
F(l,k-1),
F(k+1,r)
\bigr).
}
\]

### Quan hệ với cây Cartesian

Trong min-Cartesian tree, nút `k` là gốc của đoạn đang xét; các bài toán con nằm trên hai cây con trái/phải. Ta có thể tính `F` bằng **hậu tự** (*post-order*) trên cây mà không cần gọi RMQ để tìm lại min ở mỗi bước.

Nếu đã dựng cây trong `O(n)`, và mỗi nút chỉ được xử lý một lần:

\[
\boxed{T_{\mathrm{largestRectangle}}=O(n)}
\]

cho histogram với chiều rộng đều bằng một.

Một thuật toán monotonic stack trực tiếp cũng giải bài toán này trong `O(n)`. Cây Cartesian cung cấp **cách giải thích cấu trúc**: chia tại cực tiểu rồi kết hợp lời giải hai phía.

### Ví dụ

```text
heights = [2,1,5,6,2,3]

Hình chữ nhật tốt nhất nằm ở hai thanh 5 và 6:
chiều cao 5, chiều rộng 2 => diện tích 10.
```

**Chú ý:** một cách chia để trị cứ quét tuyến tính tìm min tại mỗi bước có thể `O(n^2)` nếu cây lệch. Dựng Cartesian tree bằng stack rồi duyệt hậu tự khắc phục việc quét lặp.

## 29. Mối liên hệ với phần tử nhỏ hơn gần nhất

Ngăn xếp đơn điệu dùng để xây Cartesian tree cũng xuất hiện trong các bài toán:

- **Previous smaller element:** phần tử nhỏ hơn gần nhất bên trái.
- **Next smaller element:** phần tử nhỏ hơn gần nhất bên phải.
- **Stock span**, các bài toán bao phủ đoạn và histogram.

### Ví dụ

```text
A = [4,2,5,1,3]

Với phần tử A[2]=5:
  nhỏ hơn gần nhất bên trái là A[1]=2.
  nhỏ hơn gần nhất bên phải là A[3]=1.
```

Trong thuật toán stack, các phần tử bị pop khi gặp một giá trị mới nhỏ hơn; quan hệ ấy giúp xác định các ranh giới mà một phần tử có thể là cực tiểu.

### Không đánh đồng hai bài toán

**Xây cây Cartesian** cần xác định **cha và con** của mỗi nút theo cả in-order và heap-order. **Tìm phần tử nhỏ hơn gần nhất** chỉ trả chỉ số láng giềng theo một phía. Hai kết quả liên quan chặt chẽ nhưng không phải cùng một API.

Đặc biệt, dấu `>`, `>=` quyết định cách xử lý phần tử bằng nhau; nếu hai phía dùng các quy tắc hòa không nhất quán, thuật toán đếm đoạn hoặc histogram có thể bị **đếm đôi** hoặc bỏ sót trường hợp trùng giá trị.

## 30. Khoảng liên tục tương ứng với cây con

Mỗi cây con của một nút Cartesian `v` chứa một **đoạn chỉ số liên tục**:

\[
\boxed{indices(subtree(v))=[L_v,R_v].}
\]

Vì cây được duyệt in-order theo chỉ số tăng, không thể có chỉ số của một nút **ngoài** cây con chen vào giữa hai chỉ số **trong** cây con.

### Tính hai biên bằng hậu tự

Có thể lưu:

```text
L_v = L_(left) nếu có left, ngược lại v
R_v = R_(right) nếu có right, ngược lại v
```

Tương tự, `size(v)` đếm số **nút** của cây con:

\[
size(v)=size(left)+1+size(right).
\]

Vì chỉ số của các nút trong cây con liên tục:

\[
\boxed{size(v)=R_v-L_v+1.}
\]

### Ứng dụng

Nếu một thuật toán muốn xử lý toàn bộ đoạn mà một nút `v` là phần tử cực tiểu, hai biên `L_v,R_v` cho biết chính xác đoạn mảng tương ứng. Việc lưu metadata này biến cây Cartesian thành một **cây tăng cường** để giải các bài toán thống kê trên khoảng và phân rã theo phần tử cực trị.

**Phải phân biệt:** mọi cây con ứng với một đoạn liên tục, nhưng **không phải mọi đoạn liên tục bất kỳ đều là một cây con**. Với đoạn bất kỳ `[l,r]`, LCA giúp tìm vị trí cực trị mà không cần đoạn ấy đúng bằng cây con của một nút.

## 31. Mã Python: tính các khoảng cây con và diện tích histogram

Hàm dưới duyệt **hậu tự không đệ quy**, do Cartesian tree có thể rất lệch.

```python
def subtree_intervals(
    tree: CartesianTree,
) -> tuple[list[int], list[int]]:
    """Trả hai mảng biên inclusive của cây con mỗi nút."""
    n = len(tree.values)
    lo = list(range(n))
    hi = list(range(n))

    if tree.root == -1:
        return lo, hi

    work: list[tuple[int, bool]] = [(tree.root, False)]
    while work:
        u, expanded = work.pop()

        if not expanded:
            work.append((u, True))
            if tree.right[u] != -1:
                work.append((tree.right[u], False))
            if tree.left[u] != -1:
                work.append((tree.left[u], False))
            continue

        if tree.left[u] != -1:
            lo[u] = lo[tree.left[u]]
        if tree.right[u] != -1:
            hi[u] = hi[tree.right[u]]

    return lo, hi


def largest_histogram_area(heights: list[int]) -> int:
    if any(h < 0 for h in heights):
        raise ValueError("Chiều cao histogram phải >= 0")

    tree = build_min_cartesian(heights)
    lo, hi = subtree_intervals(tree)
    best = 0

    for i, height in enumerate(heights):
        width = hi[i] - lo[i] + 1
        best = max(best, height * width)

    return best


print(largest_histogram_area([2, 1, 5, 6, 2, 3])) # 10
print(largest_histogram_area([]))                 # 0
print(largest_histogram_area([3, 3, 3]))          # 9
```

### Tại sao lấy max trên mọi nút là đủ?

Với mỗi hình chữ nhật hợp lệ trên đoạn `[l,r]`, lấy `k` là vị trí cực tiểu bên trái nhất trong đoạn. Nút `k` có `A[k]` không lớn hơn mọi thanh của `[l,r]`.

Khoảng cây con `[L_k,R_k]` có thể **chứa rộng hơn đoạn `[l,r]`** mà vẫn gồm các thanh có chiều cao không nhỏ hơn `A[k]`, nên hình chữ nhật có chiều cao `A[k]` và chiều rộng `R_k-L_k+1` không nhỏ hơn hình chữ nhật ban đầu. Do đó, ít nhất một nút tạo được diện tích tối ưu khi xét toàn bộ khoảng cây con của nó.

Vì có `n` nút, dựng cây `O(n)`, tính khoảng `O(n)` và xét diện tích `O(n)`:

\[
\boxed{T=O(n),\ S=O(n).}
\]

Mã không phải cách duy nhất giải histogram, nhưng cho thấy **cây Cartesian và metadata đoạn cây con** hữu ích vượt ra ngoài RMQ đơn thuần.

## 32. Khi nào không nên dùng cây Cartesian cho RMQ?

Cây Cartesian đặc biệt hữu ích để **liên kết RMQ với LCA** và tái sử dụng một phương pháp tiền xử lý LCA. Nhưng có những tình huống phương án khác thuận tiện hơn.

### 32.1. Chỉ có vài truy vấn

Nếu `Q` rất nhỏ, quét `A[l..r]` trực tiếp có thể tiết kiệm hơn bước xây bảng `O(n\log n)`.

### 32.2. Mảng thay đổi liên tục

Nếu `U` lớn, sparse table và Cartesian tree tĩnh phải xây lại. Segment tree hoặc một cấu trúc động phù hợp thường có tổng chi phí thấp hơn.

### 32.3. Giới hạn bộ nhớ chặt

Sparse table dùng `O(n\log n)` ô. Với `n` rất lớn, chi phí này có thể đáng kể, nhất là nếu mỗi ô là một object số nguyên trong ngôn ngữ cấp cao. Segment tree chuẩn dùng `O(n)` ô là một lựa chọn khác, đổi lại truy vấn `O(\log n)`.

### 32.4. Chỉ hỏi min toàn mảng

Nếu không có đoạn con tùy ý và mảng tĩnh, lưu một giá trị min `O(n)` khi xây và đọc `O(1)` là đủ. Không cần cây Cartesian hoặc sparse table.

### 32.5. Cần lọc theo điều kiện không tạo thành đoạn chỉ số

Ví dụ “min trong các phần tử có nhãn loại A” mà nhãn rải rác: RMQ theo đoạn chỉ số không trực tiếp giải điều kiện lọc. Có thể phải xây chỉ mục theo nhãn hoặc cấu trúc dữ liệu khác.

**Nguyên tắc:** chọn cấu trúc dựa trên **loại truy vấn, cập nhật, bộ nhớ và tần suất thao tác**, không chỉ vì một phép biến đổi lý thuyết đẹp.

## 33. Lỗi thường gặp và cách kiểm tra

| Lỗi hoặc ngộ nhận | Vì sao sai? | Cách xử lý |
|---|---|---|
| Gọi cây Cartesian là BST theo `A[i]` | In-order phải theo **chỉ số**, không theo giá trị | Mỗi nút giữ index và kiểm tra in-order `0..n-1` |
| Mọi cây Cartesian đều cân bằng | Dãy tăng/giảm tạo cây lệch | Phân tích chiều cao; dùng LCA tiền xử lý phù hợp |
| “Xây theo đệ quy chọn min luôn `O(n)`.” | Quét lại các đoạn có thể `O(n^2)` | Dùng monotonic stack `O(n)` |
| Vòng `while` trong stack nghĩa là `O(n^2)` | Mỗi phần tử chỉ push/pop tối đa một lần | Đếm tổng số pop |
| Pop cả khi bằng nhau nhưng yêu cầu min trái nhất | `>=` đổi chính sách tie | Dùng `>` cho min trái nhất |
| Không cập nhật `parent[last]` sau khi pop | Bảng cha sai, phá LCA dựa trên cha | Cập nhật đồng thời parent/left/right |
| Chỉ lưu giá trị, không lưu index | Không phân biệt giá trị trùng | Mỗi nút là một vị trí duy nhất |
| Lấy gốc cây làm mọi RMQ | Gốc có thể nằm ngoài đoạn | Tính `LCA(l,r)` |
| Dùng LCA trên cây gốc bất kỳ rồi gọi là RMQ | Định lý cần **Cartesian heap-order + in-order** | Kiểm tra hai bất biến |
| Đổi `A[i]` nhưng giữ cây/sparse table cũ | Cấu trúc dựa trên giá trị cũ | Xây lại hoặc dùng segment tree động |
| Tuyên bố sparse table Euler có bộ nhớ `O(n)` | Bảng có `O(n\log n)` ô | Nêu đúng cận hoặc dùng thuật toán tuyến tính chuyên biệt |
| Dùng DFS đệ quy trên cây Cartesian lệch rất dài | Có thể vượt recursion limit | Dùng Euler tour iterative |
| Quên ghi lại cha khi Euler quay về từ con | Sai độ sâu/độ dài tour | Ghi cả đường đi xuống và quay lên |
| Lấy min của `A` thay vì min của `depths` trong LCA | Biến đổi Euler dùng **độ sâu** | Xây sparse trên đúng mảng depths |
| Dùng `first` của nút theo lần xuất hiện cuối | Công thức minh họa dùng lần xuất hiện **đầu** | Lưu first khi gặp nút lần đầu |
| Quên đổi chỗ `first[u]` và `first[v]` | Đoạn Euler ngược | Đặt `p=min(first[u],first[v])` |
| Dùng cộng hai sparse blocks chồng nhau | Cộng không idempotent | Hai khối chồng chỉ hợp với min/max và phép phù hợp |
| Đếm đoạn `[l,r)` thành `[l,r]` | Lệch một phần tử | Công bố hợp đồng khoảng |
| Cho phép `RMQ(2,1)` như đoạn hợp lệ | Đoạn rỗng không có min theo API này | Từ chối hoặc dùng kết quả rỗng đã định nghĩa |
| Dùng `NaN` như giá trị có thứ tự bình thường | So sánh không tạo total order nhất quán | Chuẩn hóa hoặc từ chối NaN |
| Sửa trực tiếp `solver.tree.values` | Phá quan hệ cây/giá trị | Giữ dữ liệu bất biến, xây lại khi sửa |
| Tin `O(1)` query đồng nghĩa không tốn bộ nhớ | Phải lưu bảng tiền xử lý | Tính tổng chi phí bộ nhớ |
| Nói Fischer–Heun là chính sparse table đơn giản | Thuật toán tối ưu có phân khối phức tạp | Phân biệt hai mức kỹ thuật |
| Tính diện tích histogram với chiều cao âm | Không phù hợp mô hình histogram | Yêu cầu `height\ge0` |

### Giá trị đặc biệt: NaN và kiểu số khác

Min-Cartesian tree yêu cầu một **quan hệ thứ tự nhất quán**. Với số thực IEEE-754, `NaN` không tuân theo so sánh `<`/`>` như số thông thường, nên thuật toán `while A[top]>A[i]` có thể không biểu diễn một heap-order có nghĩa khi gặp NaN.

Trong sản phẩm thực tế, nên **từ chối NaN** hoặc định nghĩa một bộ so sánh total order xử lý NaN rõ ràng. Đồng thời, một cấu trúc đã xây từ số thực phải xem việc thay giá trị sau xây là **cập nhật dữ liệu** cần tái cấu trúc.

## 34. Bài tập tự kiểm tra

**Bài 1.** Phát biểu hai bất biến của min-Cartesian tree. Vì sao nó không phải BST sắp theo giá trị?

**Bài 2.** Với `A=[4,2,5,1,3]`, vị trí nào là gốc? Hãy vẽ hai cây con trái/phải.

**Bài 3.** Với cây ở bài 2, hãy liệt kê các chỉ số theo thứ tự in-order.

**Bài 4.** Tại sao nếu mọi phần tử trong mảng khác nhau thì Cartesian tree là duy nhất?

**Bài 5.** Với `A=[2,2]`, có bao nhiêu hình dạng min-Cartesian hợp lệ nếu không có quy tắc phá hòa? Nếu chọn min trái nhất thì gốc là nút nào?

**Bài 6.** Thuật toán stack xây min-Cartesian tree chọn min trái nhất dùng `A[top]>A[i]` hay `A[top]>=A[i]` trong vòng `while`? Giải thích.

**Bài 7.** Theo dõi stack khi xử lý `A=[3,1,2]`, rồi cho biết `root, left, right` của cây kết quả.

**Bài 8.** Chứng minh thời gian xây Cartesian tree bằng stack là `O(n)` dù vòng `while` có thể pop nhiều nút trong một bước.

**Bài 9.** Với `A=[1,2,3,4,5]`, hình dạng min-Cartesian tree như thế nào? Chiều cao có thể là `\Theta(n)` không?

**Bài 10.** Định nghĩa `RMQ_value` và `RMQ_index`. Với `A=[4,1,3,1,5]`, `RMQ_index(0,4)` phải trả bao nhiêu nếu chọn min trái nhất?

**Bài 11.** Trong cây ví dụ, tính `LCA(0,2)` và `LCA(2,4)`. Suy ra hai kết quả RMQ.

**Bài 12.** Giải thích vì sao `LCA(l,r)` của hai nút chỉ số `l,r` phải có chỉ số nằm trong `[l,r]`.

**Bài 13.** Vì sao mọi chỉ số từ `l` tới `r` đều nằm trong cây con của `LCA(l,r)`?

**Bài 14.** Một Euler tour trên cây có `n` nút, `n>0`, có bao nhiêu phần tử trong mảng tour? Vì sao?

**Bài 15.** Viết `euler` và `depths` cho cây `root=1` có hai lá `0` và `2`, duyệt trái trước phải.

**Bài 16.** Với Euler tour ở phần 16, tìm LCA của nút `0` và `2` bằng cách hỏi cực tiểu trên `depths[first[0]..first[2]]`.

**Bài 17.** Cho mảng độ sâu có độ dài `N`. Sparse table min cần bao nhiêu thời gian và bộ nhớ để xây? Một truy vấn lấy min mất bao lâu?

**Bài 18.** Tại sao có thể dùng hai khối sparse table `2^k` **chồng nhau** khi lấy min, nhưng không thể dùng cách ấy để tính tổng một đoạn?

**Bài 19.** Nêu toàn bộ các bước biến RMQ trên mảng gốc thành LCA rồi thành RMQ trên Euler tour.

**Bài 20.** Cây Cartesian tăng dần có thể lệch sâu. Tại sao Euler tour không đệ quy hữu ích trong mã Python?

**Bài 21.** Nếu `A[3]` thay từ `1` thành `9` trong `[4,2,5,1,3]`, tại sao không được dùng sparse table Euler cũ?

**Bài 22.** So sánh chi phí truy vấn và cập nhật điểm của sparse table tĩnh với segment tree.

**Bài 23.** Muốn trả chỉ số **max bên trái nhất**, phải đổi điều kiện pop của stack như thế nào?

**Bài 24.** Với `heights=[2,1,5,6,2,3]`, hình chữ nhật lớn nhất có diện tích bao nhiêu? Liên hệ nó với phép chia tại cực tiểu.

**Bài 25.** Cây con của một nút Cartesian biểu diễn một đoạn chỉ số liên tục. Có đúng rằng **mọi** đoạn liên tục là một cây con không?

**Bài 26.** Mảng Euler depth có đặc điểm gì giữa hai phần tử liên tiếp? Điều này có thể giúp các thuật toán RMQ/LCA tĩnh tiên tiến thế nào?

**Bài 27.** Nêu lý do việc dùng `(A[i],i)` thay vì chỉ `A[i]` là cần thiết khi định nghĩa chỉ số RMQ.

**Bài 28.** Thiết kế một bộ kiểm thử có thể phát hiện các lỗi: sai parent, sai tie-break, sai Euler tour, sai sparse query.

### Đáp án và giải thích

1. In-order của cây trả đúng thứ tự chỉ số `0,\ldots,n-1`; giá trị của cha không lớn hơn giá trị của con (min-heap). BST theo **giá trị** yêu cầu mọi giá trị cây trái nhỏ hơn khóa cha; điều đó không đúng với Cartesian tree.
2. Gốc chỉ số `3`, giá trị `1`. Cây trái gốc chỉ số `1`, có con trái `0` và con phải `2`; cây phải gốc chỉ số `4`.
3. `0,1,2,3,4`.
4. Gốc buộc là vị trí nhỏ nhất toàn đoạn; hai đoạn bên trái/bên phải cố định; áp dụng đệ quy nên không có lựa chọn hình dạng khác.
5. Có **hai** hình dạng min-heap hợp lệ: `0` làm cha của `1` hoặc `1` làm cha của `0`, vẫn in-order như cũ. Chọn min trái nhất thì gốc là `0`.
6. Dùng **`>`**. Nếu bằng nhau thì không pop, giữ nút cũ có chỉ số nhỏ hơn làm tổ tiên, cho chính sách min trái nhất.
7. `i=0` stack `[0]`. `i=1` pop `0`, đặt `left[1]=0`, stack `[1]`. `i=2` không pop, `right[1]=2`. Kết quả `root=1`, `left=[-1,0,-1]`, `right=[-1,2,-1]`.
8. Mỗi chỉ số được push đúng một lần và pop tối đa một lần; tổng số thao tác stack ≤ `2n` cộng số thao tác hằng số trong vòng `for`, nên `O(n)`.
9. Gốc `0`, mỗi nút `i` có con phải `i+1`, không có con trái. Chiều cao (số mức) là `n`, tức `\Theta(n)`.
10. `RMQ_value` trả giá trị min, `RMQ_index` trả vị trí của min theo tie-break. Với `A=[4,1,3,1,5]`, min `1` xuất hiện tại `1` và `3` nên chọn `RMQ_index(0,4)=1`.
11. `LCA(0,2)=1` nên `RMQ(0,2)=A[1]=2`. `LCA(2,4)=3` nên `RMQ(2,4)=A[3]=1`.
12. Theo in-order, LCA của hai nút `l\le r` hoặc trùng một đầu mút, hoặc nằm giữa hai nhánh chứa chúng; do đó chỉ số LCA thuộc `[l,r]`.
13. Các vị trí của một cây con tạo thành một khoảng in-order liên tục; cây con LCA chứa cả `l` và `r` nên chứa mọi chỉ số nằm giữa.
14. `2n-1`. Euler tour ghi gốc một lần và ghi thêm hai lượt di chuyển cho mỗi cạnh của `n-1` cạnh (đi xuống rồi quay lên).
15. Cây gốc `1`, hai con `0` và `2`: `euler=[1,0,1,2,1]`; `depths=[0,1,0,1,0]`.
16. `first[0]=2`, `first[2]=4`; đoạn depths `[2,1,2]`, min depth `1` tại Euler index `3`, trả nút `1`.
17. `O(N\log N)` thời gian và bộ nhớ tiền xử lý; `O(1)` mỗi truy vấn min.
18. `min(x,x)=x` nên phần giao bị xét hai lần không thay đáp án. Với tổng, phần giao bị cộng hai lần nên sai.
19. Xây min-Cartesian tree `O(n)` → lấy `LCA(l,r)` → tạo Euler tour và depths + first → sparse table min trên depths → min-depth trong khoảng first của hai đầu mút → nút LCA là chỉ số min của mảng gốc.
20. Cây có thể cao `n`, DFS đệ quy dễ vượt giới hạn recursion; dùng stack tường minh không phụ thuộc ngăn xếp lời gọi Python.
21. Giá trị cực tiểu toàn mảng và quan hệ heap-order đổi, hình dạng Cartesian tree có thể đổi; Euler/sparse cũ dựa trên cấu trúc sai và phải xây lại.
22. Sparse table: xây `O(n\log n)`, query `O(1)`, update thường xây lại; segment tree: xây `O(n)`, query và point update đều `O(\log n)`.
23. Dùng `while stack and A[stack[-1]] < A[i]: pop`; không pop khi bằng nhau để ưu tiên cực đại bên trái nhất.
24. Diện tích `10`, từ hai thanh chiều cao `5` và `6`. Có thể chia tại thanh min toàn đoạn, giải hai đoạn con và xét hình chữ nhật phủ toàn đoạn; trên Cartesian tree, duyệt hậu tự cho lời giải `O(n)`.
25. Không. Mỗi cây con chiếm một đoạn liên tục, nhưng đoạn bất kỳ `[l,r]` có thể cắt xuyên vài nhánh. Khi ấy tìm LCA của hai đầu mút để lấy cực tiểu, không cần đoạn là đúng một cây con.
26. Độ sâu thay đổi đúng `+1` hoặc `-1` vì tour đi qua một cạnh mỗi bước. Tính chất **±1 RMQ** cho phép các thuật toán tĩnh chuyên biệt đạt tiền xử lý/bộ nhớ `O(n)` và truy vấn `O(1)` trong mô hình thích hợp.
27. Khóa `(value,index)` phân biệt các vị trí có cùng giá trị và chọn index nhỏ hơn khi hòa, làm chỉ số RMQ có nghĩa xác định và cây Cartesian duy nhất.
28. Kiểm `parent[child]==node` và không chu trình; kiểm in-order `0..n-1` và heap-order theo `(A[i],i)`; kiểm `len(euler)==2n-1` và `|depths[t+1]-depths[t]|=1`; với mọi đoạn của mảng nhỏ, so `argmin(l,r)` với duyệt `min(range(l,r+1), key=lambda i:(A[i],i))`, đặc biệt ở mảng có giá trị trùng.

## 35. Ghi nhớ

**Cây Cartesian** kết hợp **thứ tự in-order theo chỉ số mảng** với **min-heap-order hoặc max-heap-order theo giá trị**. Đối với min-Cartesian tree, nếu dùng khóa ghép **`(A[i],i)`** thì mỗi đoạn có một **vị trí cực tiểu bên trái nhất** xác định. Cây có thể xây bằng **ngăn xếp đơn điệu trong `O(n)`**, vì mỗi phần tử được push một lần và pop nhiều nhất một lần; nó **không tự cân bằng** và có thể cao `\Theta(n)`. Định lý then chốt là **`RMQ_index(l,r)=LCA(l,r)`** trên min-Cartesian tree. Bằng **Euler tour** và **sparse table trên độ sâu**, ta có thể tiền xử lý `O(n\log n)` thời gian/bộ nhớ để trả **RMQ tĩnh `O(1)`**, nhưng dữ liệu thay đổi thường xuyên nên cân nhắc **segment tree**. Quan hệ Cartesian–LCA–RMQ còn giải thích các ứng dụng như **hình chữ nhật lớn nhất trong histogram**, các đoạn liên tục của cây con và các thuật toán RMQ/LCA tối ưu hơn. Khi lập trình, phải chốt **quy ước đoạn, cách phá hòa, dữ liệu tĩnh hay động, và kiểu bảo đảm thời gian/bộ nhớ** thay vì chỉ nhớ tên cấu trúc.

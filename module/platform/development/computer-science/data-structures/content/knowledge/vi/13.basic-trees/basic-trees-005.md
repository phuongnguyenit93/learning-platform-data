# Cây nhị phân và giới hạn tối đa hai nút con

## 1. Cây nhị phân là gì?

Trong học phần **Cấu trúc dữ liệu**, cây (*tree*) biểu diễn quan hệ phân cấp giữa các nút. Ta chọn một **gốc (root)**, rồi đi theo quan hệ **cha–con** tới các cây con. **Cây nhị phân (binary tree)** là một loại cây có gốc với hai đặc điểm quan trọng:

1. **Mỗi nút có tối đa hai con trực tiếp**.
2. Hai vị trí con được **phân biệt thành trái (left) và phải (right)**, ngay cả khi chỉ có một vị trí được sử dụng.

Ta có thể định nghĩa đệ quy:

> Một cây nhị phân hoặc là **rỗng**, hoặc gồm một nút gốc cùng **một cây nhị phân con trái** và **một cây nhị phân con phải**; mỗi cây con có thể rỗng.

Định nghĩa này khác với “mỗi nút có đúng hai con”. Một nút có **không con, một con hoặc hai con** đều hợp lệ. Nếu chỉ có một con, nó vẫn cần được xác định rõ là **con trái** hay **con phải**.

Ví dụ:

```text
                   A
                  / \
                 B   C
                / \   \
               D   E   F

A.left  = B          A.right = C
B.left  = D          B.right = E
C.left  = rỗng       C.right = F
D, E, F đều không có con
```

Đây là cây nhị phân hợp lệ gồm **6 nút** và **5 cạnh**. Nút `C` chỉ có **con phải** `F`, điều đó hoàn toàn được phép.

**Ý tưởng then chốt:** “tối đa hai con” là ràng buộc **cấu trúc**. Nó không tự động nói gì về thứ tự lớn–nhỏ giữa các giá trị, về độ cân bằng, hoặc về cách chèn/xóa nút. Những ràng buộc này chỉ xuất hiện trong các biến thể như **cây tìm kiếm nhị phân (BST)**, **heap nhị phân** và cây nhị phân cân bằng.

## 2. Quan hệ cha–con và hai vị trí trái/phải

### 2.1. Một nút có bốn trạng thái vị trí con

Trong cây nhị phân, hai vị trí con có thể có hoặc không có nút:

| Con trái | Con phải | Số con | Vai trò nút |
|---|---|---:|---|
| Rỗng | Rỗng | `0` | Lá |
| Có | Rỗng | `1` | Nút trong |
| Rỗng | Có | `1` | Nút trong |
| Có | Có | `2` | Nút trong |

**Lá (leaf)** là nút không có con. **Nút trong (internal node)** là nút có ít nhất một con. Bảng trên cũng cho thấy một nút chỉ có con trái và nút chỉ có con phải là **hai cấu trúc khác nhau**.

Ví dụ:

```text
Cây 1:          Cây 2:

   P               P
  /                 \
 Q                   Q
```

Cả hai có hai nút và một cạnh, nhưng **khác nhau về vị trí con**. Một phép duyệt có xét trái trước phải hay một phép tính sử dụng nhánh trái/phải sẽ quan sát được sự khác biệt.

### 2.2. Một gốc, một cha, không có chu trình

Cây nhị phân kế thừa các bất biến của cây có gốc:

- Nếu cây không rỗng thì có **đúng một gốc**.
- **Gốc không có cha**; mỗi nút còn lại có **đúng một cha**.
- Mọi nút có thể đi tới từ gốc theo các cạnh cha–con.
- Không có chu trình; một nút **không thể là hậu duệ của chính nó**.
- **Không thể dùng cùng một đối tượng nút làm con của hai cha**, kể cả cùng một cha ở cả hai vị trí trái và phải.
- Mỗi nút có tối đa **một con trái và một con phải**.

Nếu có `n ≥ 1` nút, cây vẫn có **`n - 1` cạnh**, vì mọi nút không phải gốc có đúng một cạnh nối từ cha của nó.

**Không nhầm lẫn:** nếu một đối tượng được tham chiếu từ nhiều vị trí như trong một DAG, ta có thể thấy hình vẽ phân nhánh nhưng không còn là **cây theo quan hệ một cha**. Thuật toán duyệt cây thuần túy có thể thăm nút lặp lại hoặc không kết thúc nếu cấu trúc bị tạo chu trình.

### 2.3. Phân biệt cây con trái và cây con phải

**Cây con trái (left subtree)** của nút `u` gồm `u.left` và toàn bộ hậu duệ của nút đó; nếu `u.left` rỗng thì cây con trái là cây rỗng. Cây con phải được xác định tương tự.

Ví dụ ở cây `A`:

- Cây con trái của `A` gồm `B, D, E`.
- Cây con phải của `A` gồm `C, F`.
- Cây con trái của `C` rỗng.
- Cây con phải của `C` gồm một nút `F`.

Đây là cách phân rã đệ quy tự nhiên: để tính một tính chất của cây gốc `u`, ta có thể tính trên **hai cây con** rồi kết hợp kết quả.

## 3. Giới hạn hai con không đồng nghĩa với cây cân bằng

Ràng buộc “tối đa hai con” **không bảo đảm cây có chiều cao nhỏ**. Cùng một số nút có thể tạo những hình dạng rất khác nhau.

Ví dụ, ba cây sau đều là cây nhị phân:

```text
(a) Gần cân đối       (b) Lệch trái       (c) Lệch phải

       A                  A                  A
      / \                /                    \
     B   C              B                      B
    / \                /                        \
   D   E              C                          C
                     /
                    D
                   /
                  E
```

Với cây (a), đường sâu nhất từ `A` đến lá có **2 cạnh**. Với cây (b) và (c), đường sâu nhất có **4 cạnh**. Cả ba đều có **5 nút**.

Khi một thuật toán phải đi qua các nút trên một đường từ gốc xuống dưới, chi phí thường liên quan tới **chiều cao** `h`:

- Cây có chiều cao `O(\log n)`: một lần đi theo đường gốc → lá có thể tốn `O(\log n)`.
- Cây lệch thành chuỗi: `h = n - 1`, nên đường đi có thể dài `O(n)`.

Tuy nhiên, **chiều cao nhỏ không tự động giúp tìm kiếm nhanh** trong một cây nhị phân không có quy tắc về giá trị. Muốn biết nút chứa một giá trị cụ thể ở đâu, có thể vẫn phải duyệt **`O(n)` nút**, vì không có bất biến so sánh như trong BST.

## 4. Độ sâu, chiều cao và số nút theo từng mức

Bài này dùng quy ước **độ sâu và chiều cao tính theo số cạnh**:

- Gốc có **độ sâu `0`**.
- Con trực tiếp của gốc có độ sâu `1`.
- **Lá có chiều cao `0`**.
- Chiều cao `h` của cây không rỗng là **độ sâu lớn nhất** của một nút.
- Cây rỗng được quy ước chiều cao `-1` để thuận tiện viết công thức đệ quy.

Một số tài liệu tính chiều cao theo **số nút** trên đường dài nhất: khi đó lá cao `1` và cây rỗng cao `0`. Với cây không rỗng, hai cách tính chênh nhau đúng **`1`**. Hãy thống nhất quy ước trước khi giải bài.

### 4.1. Mỗi mức có tối đa bao nhiêu nút?

Vì mỗi nút tối đa hai con:

- Mức `0` có tối đa `1 = 2⁰` nút.
- Mức `1` có tối đa `2 = 2¹` nút.
- Mức `2` có tối đa `4 = 2²` nút.
- ...
- Mức `d` có tối đa **`2^d` nút**.

Lập luận quy nạp: nếu mức `d` có không quá `2^d` nút và mỗi nút sinh không quá hai con, mức `d+1` có không quá `2 × 2^d = 2^(d+1)` nút.

### 4.2. Cây cao `h` có tối đa bao nhiêu nút?

Cộng chặn trên ở tất cả mức từ `0` đến `h`:

\[
n \le 1+2+4+\cdots+2^h = 2^{h+1}-1.
\]

Với cây nhị phân không rỗng có chiều cao `h` theo cạnh:

\[
h+1 \le n \le 2^{h+1}-1.
\]

**Vì sao có chặn dưới `h+1`?** Để chiều cao là `h`, phải có ít nhất một đường từ gốc tới lá gồm `h` cạnh, tức **`h+1` nút**. Một cây dạng chuỗi đạt chặn dưới.

**Vì sao có chặn trên?** Mỗi mức có thể có gấp đôi số nút của mức trước; chặn trên đạt được khi **mọi vị trí nút ở mọi mức từ `0` đến `h` đều được lấp đầy**.

| Chiều cao theo cạnh `h` | Ít nhất `h+1` nút | Nhiều nhất `2^(h+1)-1` nút |
|---:|---:|---:|
| `0` | `1` | `1` |
| `1` | `2` | `3` |
| `2` | `3` | `7` |
| `3` | `4` | `15` |
| `4` | `5` | `31` |

### 4.3. Nếu biết `n` nút, chiều cao có thể là bao nhiêu?

Từ chặn trên số nút, với `n≥1`:

\[
\left\lceil\log_2(n+1)\right\rceil-1 \le h \le n-1.
\]

Với `n` nguyên dương, giới hạn dưới cũng bằng `\lfloor \log_2 n\rfloor`.

Ví dụ cây có `n=10` nút:

- Chiều cao **nhỏ nhất** là `\lceil\log_2(11)\rceil-1=4-1=3` cạnh.
- Chiều cao **lớn nhất** là `9` cạnh khi tạo một chuỗi mười nút.

Điều này cho thấy có **giới hạn lý thuyết**, nhưng thuật toán xây cây phải **chủ động duy trì hình dạng** nếu muốn chiều cao nhỏ.

## 5. Phân biệt cây nhị phân đầy đủ, hoàn chỉnh và hoàn hảo

Các tài liệu đôi khi dịch thuật ngữ tiếng Anh theo nhiều cách. Để tránh mơ hồ, bài này luôn kèm tên tiếng Anh và định nghĩa.

### 5.1. Cây nhị phân đầy đủ theo nghĩa *full/proper/strict*

**Full binary tree:** **mỗi nút có hoặc `0` con hoặc đúng `2` con**. Không có nút nào chỉ có một con.

```text
       A
      / \
     B   C
        / \
       D   E

A có 2 con; C có 2 con;
B, D, E đều có 0 con → full.
```

Cây này **full**, nhưng **không complete** theo định nghĩa ở phần tiếp: mức cuối có nút dưới `C` trong khi các vị trí phía trái dưới `B` còn trống.

Nếu `I` là số nút trong, `L` là số lá, thì trong cây full không rỗng:

\[
n=I+L,\qquad n-1=2I
\quad\Longrightarrow\quad
L=I+1,\quad n=2I+1.
\]

Lý do: mỗi nút trong đóng góp đúng hai cạnh đi tới con, tổng số cạnh là `2I`; đồng thời cây có `n-1` cạnh.

**Kết luận:** một cây full không rỗng luôn có **số nút lẻ**, nhưng một cây có số nút lẻ **chưa chắc full**. Cây chỉ có một nút cũng là cây full: `I=0` và `L=1`.

### 5.2. Cây nhị phân hoàn chỉnh theo nghĩa *complete*

**Complete binary tree:** tất cả các mức **trừ có thể mức cuối** đều đầy; các nút ở mức cuối được đặt **liên tục từ trái sang phải**, không để lỗ trước một nút có mặt.

```text
        A
       / \
      B   C
     /
    D

Complete: mức 0 và 1 đầy,
mức cuối chỉ có D tại vị trí trái nhất.
```

Cây này **complete** nhưng **không full**, vì `B` chỉ có một con trái.

Đặc điểm của complete tree không rỗng:

- Số nút `n` quyết định hình dạng các vị trí chiếm chỗ theo thứ tự mức.
- Chiều cao theo cạnh là **`\lfloor\log_2 n\rfloor`**.
- Có thể lưu gọn trong một **mảng liên tiếp** mà không cần ô rỗng trung gian, theo thứ tự duyệt mức (*level-order*).

### 5.3. Cây nhị phân hoàn hảo theo nghĩa *perfect*

**Perfect binary tree:** **mọi nút trong có đúng hai con** và **tất cả lá đều ở cùng độ sâu**. Tương đương: mọi mức từ `0` tới `h` đều đầy.

```text
          A
         / \
        B   C
       / \ / \
      D  E F  G
```

Nếu chiều cao theo cạnh là `h`, cây perfect có:

\[
n=2^{h+1}-1,\qquad L=2^h.
\]

Perfect tree luôn **full** và **complete**. Nhưng full và complete **không tương đương** với nhau, và mỗi loại riêng lẻ không nhất thiết perfect.

### 5.4. Bảng nhận diện

| Hình dạng | Full: 0 hoặc 2 con | Complete: mức cuối sát trái | Perfect: mọi mức đầy |
|---|---|---|---|
| Một nút | Có | Có | Có |
| `A` chỉ có con trái `B` | Không | Có | Không |
| `A` chỉ có con phải `B` | Không | Không | Không |
| Gốc có 2 lá con | Có | Có | Có |
| `A` có 2 con; chỉ `B` có 2 con | Có | Có | Không |
| `A` có 2 con; chỉ `C` có 2 con | Có | Không | Không |

**Balanced (cân bằng)** lại là khái niệm khác. Chẳng hạn trong cây AVL, độ cao hai nhánh con của mỗi nút chênh nhau không quá một. Một cây có thể thỏa quy tắc cân bằng mà **không complete** và không perfect. Ngược lại, complete tree có chiều cao nhỏ theo số nút, nhưng các ứng dụng có thể dùng định nghĩa “cân bằng” cụ thể khác nhau.

## 6. Biểu diễn cây nhị phân bằng các nút liên kết

Cách biểu diễn trực quan nhất là mỗi nút lưu **giá trị**, **tham chiếu con trái** và **tham chiếu con phải**.

```text
              ┌─────────────┐
              │ value = A   │
              │ left  ──────┼──► B
              │ right ──────┼──► C
              └─────────────┘

Nếu một nhánh không có con, tham chiếu tương ứng là None.
```

### 6.1. Cài đặt Python

```python
class BinaryNode:
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right


# Cây mẫu:
#
#        A
#       / \
#      B   C
#     / \   \
#    D   E   F

root = BinaryNode(
    "A",
    left=BinaryNode(
        "B",
        left=BinaryNode("D"),
        right=BinaryNode("E")
    ),
    right=BinaryNode(
        "C",
        right=BinaryNode("F")
    )
)

print(root.value)              # A
print(root.left.value)         # B
print(root.right.value)        # C
print(root.right.left)         # None
print(root.right.right.value)  # F
```

Mã sử dụng `None` làm đại diện **cây con rỗng**. Con phải vẫn có thể tồn tại khi con trái rỗng; không được dịch con phải sang vị trí trái chỉ để “lấp chỗ” nếu bài toán cần giữ nguyên cấu trúc.

Với biểu diễn nút liên kết:

- Xem `left`, `right` hoặc `value` khi đã có tham chiếu nút: **`O(1)` thời gian**.
- Tạo một nút: **`O(1)`** thao tác cơ bản, không tính kích thước dữ liệu được lưu.
- Lưu `n` nút và tối đa hai tham chiếu con mỗi nút: **`O(n)` bộ nhớ**.
- Tìm một giá trị tùy ý nếu không có bất biến thứ tự hoặc chỉ mục: có thể cần **`O(n)` thời gian**.

Đây là cấu trúc *liên kết*; **không cần cấp phát chỗ cho mọi vị trí của một cây nhị phân đầy đủ theo mức**. Vì vậy nó thích hợp cả với cây thưa hoặc rất lệch.

### 6.2. Cần bảo vệ bất biến một cha và không chu trình

Lớp đơn giản trên **không tự ngăn** các thao tác sai như:

```python
shared = BinaryNode("X")
invalid = BinaryNode("A", left=shared, right=shared)

# invalid không phải cây hợp lệ:
# cùng một đối tượng X có hai liên kết từ cha A.
```

Tương tự, `root.left = root` sẽ tạo chu trình. Đây là **đồ thị tham chiếu**, không phải cây có gốc hợp lệ.

Nếu dữ liệu đến từ bên ngoài, một hàm kiểm tra có thể duyệt theo **định danh đối tượng** để phát hiện một nút bị gặp lại:

```python
def is_valid_binary_tree(root):
    if root is None:
        return True  # API này cho phép cây rỗng

    seen = set()
    pending = [root]

    while pending:
        node = pending.pop()

        if not isinstance(node, BinaryNode):
            return False

        node_id = id(node)
        if node_id in seen:
            # Gặp lại do chu trình hoặc một nút có nhiều đường tới.
            return False
        seen.add(node_id)

        if node.left is not None:
            pending.append(node.left)
        if node.right is not None:
            pending.append(node.right)

    return True


print(is_valid_binary_tree(root))     # True
print(is_valid_binary_tree(invalid))  # False
```

Hàm duyệt các nút **có thể tới được từ gốc**. Với `n` nút khác nhau được duyệt và cấu trúc hợp lệ, thời gian và bộ nhớ phụ đều **`O(n)`**. Khi một nút được gặp lần hai, ta biết cấu trúc không thể là một cây phân cấp đúng nghĩa, dù mỗi đối tượng có đúng hai trường con.

Không nên **vừa thay đổi cấu trúc vừa duyệt** khi không có chính sách đồng bộ thích hợp; dữ liệu có thể trở nên không nhất quán giữa hai lần đọc.

## 7. Biểu diễn bằng mảng: khi nào tiết kiệm?

Với **cây nhị phân complete**, ta có thể lưu các giá trị liên tục trong mảng theo thứ tự **duyệt mức**, từ trái sang phải.

Ví dụ:

```text
        A
       / \
      B   C
     / \ /
    D  E F

Mảng theo mức:
[A, B, C, D, E, F]

Chỉ số:
 0  1  2  3  4  5
```

Nếu sử dụng **chỉ số từ 0**:

- Nút ở vị trí `i` có con trái tại `2i+1` nếu vị trí đó tồn tại.
- Nút ở vị trí `i` có con phải tại `2i+2` nếu vị trí đó tồn tại.
- Với `i>0`, cha tại `\lfloor(i-1)/2\rfloor`.
- Gốc nằm ở chỉ số `0`.

```text
A: i=0   → left=1(B), right=2(C)
B: i=1   → left=3(D), right=4(E)
C: i=2   → left=5(F), right=6 (không có)
```

### 7.1. Vì sao complete tree hợp với mảng?

Một cây complete không có lỗ ở các vị trí trước những nút đang tồn tại trong thứ tự theo mức. Vì vậy mọi nút được đặt vào một ô của đoạn chỉ số `0..n-1`; các công thức cha/con vẫn đúng, mà **không cần lưu hai tham chiếu con cho từng nút**.

Đây là lý do **binary heap** thường dùng mảng. Heap còn áp đặt thêm **bất biến thứ tự ưu tiên giữa cha và con**, không chỉ hình dạng complete.

### 7.2. Cây nhị phân bất kỳ có thể có lỗ

Quay lại cây đầu bài: `C` chỉ có con **phải** `F`.

```text
       A
      / \
     B   C
    / \   \
   D   E   F

Vị trí mảng giữ đúng cấu trúc:
[A, B, C, D, E, None, F]
                ↑
        C.left là vị trí 5 bị khuyết
```

Nếu bỏ ô `None` và nén thành `[A,B,C,D,E,F]`, công thức `2i+1` sẽ hiểu sai `F` thành **con trái** của `C`.

Đối với cây rất lệch, chỉ số biểu diễn theo vị trí có thể tăng rất nhanh theo chiều cao. Một mảng được cấp phát tới chỉ số lớn nhất có thể có nhiều ô trống, nên cách lưu này **không bảo đảm tiết kiệm bộ nhớ cho mọi cây nhị phân**. Khi hình dạng thưa, lưu nút liên kết hoặc cấu trúc ánh xạ chỉ số tới nút thường phù hợp hơn.

**Bảng so sánh:**

| Tiêu chí | Nút liên kết | Mảng theo vị trí mức |
|---|---|---|
| Cây thưa/lệch | Thích hợp, chỉ lưu nút có thật | Có thể phải giữ nhiều ô rỗng |
| Cây complete | Hoạt động tốt | Rất phù hợp, lưu liên tục |
| Lấy con khi đã biết nút/chỉ số | `O(1)` | `O(1)` theo công thức chỉ số |
| Duyệt toàn bộ cây | `O(n)` | `O(n)` khi cây complete lưu đặc |
| Bộ nhớ với `n` nút | `O(n)` nút và tham chiếu | `O(n)` nếu complete; có thể lớn hơn nếu thưa và giữ lỗ |
| Sửa cấu trúc | Dễ đổi tham chiếu, cần bảo vệ bất biến | Phụ thuộc yêu cầu duy trì hình dạng, có thể phải dời dữ liệu |

## 8. Duyệt cây nhị phân: trái và phải có ý nghĩa

Sự phân biệt con trái/con phải tạo ra các thứ tự duyệt đặc trưng.

Cho cây mẫu:

```text
       A
      / \
     B   C
    / \   \
   D   E   F
```

| Kiểu duyệt | Quy tắc tại mỗi nút | Kết quả |
|---|---|---|
| **Preorder** (tiền thứ tự) | Gốc → Trái → Phải | `A, B, D, E, C, F` |
| **Inorder** (trung thứ tự) | Trái → Gốc → Phải | `D, B, E, A, C, F` |
| **Postorder** (hậu thứ tự) | Trái → Phải → Gốc | `D, E, B, F, C, A` |
| **Level-order** (theo mức) | Theo độ sâu tăng dần, trái trước phải | `A, B, C, D, E, F` |

**Inorder** là kiểu duyệt đặc trưng của cây nhị phân vì vị trí gốc nằm **giữa hai cây con trái/phải**. Trong cây tổng quát có nhiều hơn hai con, không có một vị trí duy nhất tương đương “giữa trái và phải” nếu chưa quy định thêm.

### 8.1. Code Python: preorder, inorder và postorder

Các hàm dưới đây dùng lớp `BinaryNode` đã định nghĩa ở phần 6. Mỗi hàm nhận `root`, trả một danh sách giá trị; với cây rỗng `None` thì trả `[]`.

```python
def preorder(root):
    if root is None:
        return []
    return (
        [root.value]
        + preorder(root.left)
        + preorder(root.right)
    )


def inorder(root):
    if root is None:
        return []
    return (
        inorder(root.left)
        + [root.value]
        + inorder(root.right)
    )


def postorder(root):
    if root is None:
        return []
    return (
        postorder(root.left)
        + postorder(root.right)
        + [root.value]
    )


print(preorder(root))   # ['A', 'B', 'D', 'E', 'C', 'F']
print(inorder(root))    # ['D', 'B', 'E', 'A', 'C', 'F']
print(postorder(root))  # ['D', 'E', 'B', 'F', 'C', 'A']
```

**Lưu ý hiệu năng:** các ví dụ trên ưu tiên biểu diễn quy tắc duyệt rõ ràng. Phép cộng `list` tạo danh sách mới nhiều lần, có thể khiến tổng thời gian **vượt `O(n)`**, nhất là trên cây lệch. Nếu cần `O(n)` thời gian, hãy **ghi trực tiếp vào một danh sách kết quả dùng chung**, hoặc xử lý nút tại chỗ.

### 8.2. Code Python: inorder `O(n)` thời gian

```python
def inorder_linear(root):
    result = []

    def visit(node):
        if node is None:
            return
        visit(node.left)
        result.append(node.value)
        visit(node.right)

    visit(root)
    return result


print(inorder_linear(root))  # ['D', 'B', 'E', 'A', 'C', 'F']
```

Mỗi nút được thăm một lần, nên tổng thời gian **`O(n)`** nếu thao tác xử lý/ghi một giá trị là `O(1)`. **Call stack** giữ tối đa `O(h+1)` khung ở một thời điểm với `h` là chiều cao theo cạnh. Danh sách kết quả dùng thêm **`O(n)` bộ nhớ**.

Độ sâu quá lớn có thể chạm giới hạn đệ quy Python. Khi cần duyệt cây lệch dài, một stack tường minh có thể thay thế call stack.

### 8.3. Code Python: preorder bằng stack tường minh

```python
def preorder_iterative(root):
    if root is None:
        return []

    result = []
    stack = [root]

    while stack:
        node = stack.pop()
        result.append(node.value)

        # LIFO: push phải trước, trái sau.
        if node.right is not None:
            stack.append(node.right)
        if node.left is not None:
            stack.append(node.left)

    return result


print(preorder_iterative(root))
# ['A', 'B', 'D', 'E', 'C', 'F']
```

Vì stack là **LIFO**, muốn xử lý cây con **trái trước**, ta phải **push phải trước** để cây con trái nằm trên đỉnh và được pop trước.

Với một cây nhị phân `n` nút, mỗi nút được push và pop đúng một lần nên thời gian duyệt **`O(n)`**. Stack nút chờ cần **`O(h+1)`** bộ nhớ phụ trong cách duyệt này; kết quả có `n` phần tử cần thêm `O(n)` bộ nhớ.

### 8.4. Code Python: duyệt mức bằng queue

```python
from collections import deque


def level_order(root):
    if root is None:
        return []

    result = []
    pending = deque([root])

    while pending:
        node = pending.popleft()
        result.append(node.value)

        if node.left is not None:
            pending.append(node.left)
        if node.right is not None:
            pending.append(node.right)

    return result


print(level_order(root))  # ['A', 'B', 'C', 'D', 'E', 'F']
```

BFS dùng **queue (FIFO)** thay vì stack, nên các nút ở mức trước được xử lý trước các nút ở mức sau. Độ phức tạp **`O(n)` thời gian**; queue có thể giữ số nút tỷ lệ với **độ rộng của các mức**, tối đa `O(n)`, và kết quả cần thêm `O(n)` bộ nhớ.

## 9. Đếm nút, đếm lá và tính chiều cao

Định nghĩa đệ quy của cây nhị phân cho phép xây các thuật toán rất ngắn.

### 9.1. Đếm số nút

```python
def count_nodes(root):
    if root is None:
        return 0
    return 1 + count_nodes(root.left) + count_nodes(root.right)
```

**Bất biến/ý tưởng:** tổng số nút của cây bằng **một nút gốc + số nút cây con trái + số nút cây con phải**. Hai cây con không được chia sẻ cùng một nút thật sự; nếu cấu trúc có nhiều cha, phép đếm có thể đếm trùng.

### 9.2. Đếm số lá

```python
def count_leaves(root):
    if root is None:
        return 0
    if root.left is None and root.right is None:
        return 1
    return count_leaves(root.left) + count_leaves(root.right)
```

Lá là nút có **không con trái và không con phải**. Cây chỉ có một nút có **một lá**; cây rỗng có **không lá** theo API này.

### 9.3. Chiều cao theo số cạnh

```python
def height_edges(root):
    if root is None:
        return -1

    return 1 + max(
        height_edges(root.left),
        height_edges(root.right)
    )


print(count_nodes(root))   # 6
print(count_leaves(root))  # 3
print(height_edges(root))  # 2
```

Với lá, cả hai cây con rỗng, nên `1 + max(-1, -1) = 0`. Với gốc của cây mẫu, nhánh dài nhất có hai cạnh.

Ba hàm trên duyệt mỗi nút hữu hạn số lần và có **`O(n)` thời gian** trên cây hợp lệ. Bộ nhớ khung đệ quy **`O(h+1)`** với cây không rỗng. Nếu một ứng dụng thường xuyên cần hỏi chiều cao của các cây con sau thao tác sửa cấu trúc, có thể lưu cache chiều cao, nhưng phải cập nhật cache khi đổi liên kết; nếu không, giá trị sẽ sai.

## 10. Thêm một nút vào cây nhị phân: không có một quy tắc duy nhất

Cấu trúc cây nhị phân chỉ đặt giới hạn **tối đa hai con**. Nó **không nói phải chèn vào đâu**. Có nhiều chính sách, tùy bài toán.

- **Chèn có chỉ định vị trí:** thêm vào con trái hoặc con phải của một nút đã biết, nếu vị trí còn rỗng. Thao tác gán tham chiếu là `O(1)`, **chưa tính** tìm nút cha và kiểm tra chu trình.
- **Chèn theo mức để giữ complete tree:** quét từ gốc theo BFS và lấp vị trí trống đầu tiên theo thứ tự trái → phải.
- **Chèn theo giá trị trong BST:** so sánh giá trị với từng nút và đi trái/phải theo bất biến của BST, **không phải** quy tắc chung của mọi cây nhị phân.
- **Chèn vào binary heap:** giữ cấu trúc complete rồi điều chỉnh thứ tự ưu tiên bằng thao tác nổi/sụt phù hợp.

### 10.1. Ví dụ: chèn theo mức

Giả sử đầu vào **đã là một cây nhị phân complete** và muốn sau khi chèn vẫn complete. Ta có thể chèn ở vị trí còn thiếu đầu tiên theo thứ tự duyệt mức:

```python
from collections import deque


def insert_level_order(root, value):
    new_node = BinaryNode(value)

    if root is None:
        return new_node

    pending = deque([root])

    while pending:
        node = pending.popleft()

        if node.left is None:
            node.left = new_node
            return root
        pending.append(node.left)

        if node.right is None:
            node.right = new_node
            return root
        pending.append(node.right)

    # Với một cây hữu hạn hợp lệ, sẽ có vị trí trống.
    raise RuntimeError("Không tìm được vị trí chèn")


complete_root = BinaryNode(
    "A",
    left=BinaryNode("B"),
    right=BinaryNode("C")
)

complete_root = insert_level_order(complete_root, "D")
print(level_order(complete_root))  # ['A', 'B', 'C', 'D']
```

Vì BFS duyệt nút cha từ mức thấp đến mức cao và xét trái trước phải, trên **cây complete ban đầu**, vị trí trống tìm được sẽ là vị trí kế tiếp trong trình tự mức. Phương án này có thể cần **`O(n)` thời gian** và queue **`O(n)` bộ nhớ** trong trường hợp xấu nhất.

**Không nên suy ra** rằng gọi hàm này trên **bất kỳ cây nhị phân không complete** sẽ tự biến nó thành complete. Nếu dữ liệu đã có lỗ ở mức trước nhưng có nút nằm sau lỗ, thêm một nút không thể nhất thiết sửa được toàn bộ các vi phạm hình dạng.

### 10.2. Xóa nút cần chính sách rõ ràng

Xóa một **lá** có thể chỉ cần gỡ tham chiếu tương ứng ở cha. Nhưng xóa một **nút trong** đặt ra nhiều lựa chọn: có xóa toàn bộ cây con, chuyển con lên, thay nút bằng một nút khác, hay từ chối thao tác? Với cây cần giữ complete hoặc heap, có thể phải di chuyển nút cuối cùng và sắp xếp lại.

**Không có thuật toán xóa duy nhất áp dụng cho mọi cây nhị phân.** Cần thiết kế theo bất biến cụ thể của kiểu cây và hợp đồng ứng dụng.

## 11. Cây nhị phân khác BST và binary heap như thế nào?

| Tiêu chí | Cây nhị phân nói chung | BST | Binary heap |
|---|---|---|---|
| Mỗi nút tối đa hai con | Có | Có | Có |
| Phân biệt trái/phải | Có | Có | Có |
| Có quy tắc sắp giá trị | **Không bắt buộc** | Có bất biến thứ tự trái–gốc–phải theo chính sách khóa trùng | Có thứ tự ưu tiên giữa cha và con |
| Hình dạng complete bắt buộc | Không | Không | **Có** trong binary heap thông thường |
| Tìm khóa tùy ý | Có thể cần `O(n)` | `O(h)` nếu theo so sánh khóa; cân bằng thường `O(\log n)` | Thường `O(n)` nếu không có chỉ mục phụ |
| Truy vấn cực trị ưu tiên | Không có bảo đảm đặc biệt | Theo đường cực trái/phải khi bất biến phù hợp | Xem gốc `O(1)` |

**Ví dụ:** cây `A` ở gốc, `B` bên trái và `C` bên phải là một cây nhị phân hợp lệ, nhưng nếu các giá trị là số và thứ tự không thỏa ràng buộc BST thì nó **không phải BST**. Ngược lại, một cây có hình dạng complete vẫn chưa chắc là heap nếu giá trị không thỏa bất biến heap.

Trong **BST**, với chính sách “khóa trái nhỏ hơn, khóa phải lớn hơn” và các khóa phân biệt, duyệt **inorder** cho khóa theo thứ tự tăng dần. Đó là hệ quả của **bất biến BST**, không phải tính chất của mọi cây nhị phân.

Trong **binary heap dạng max-heap**, mọi nút cha có khóa **lớn hơn hoặc bằng khóa các con**; min-heap có quan hệ ngược lại. Heap không đảm bảo toàn bộ cây con trái chứa giá trị nhỏ hơn toàn bộ cây con phải, nên duyệt inorder không có yêu cầu phải được sắp xếp.

## 12. Bất biến và độ phức tạp cần nhớ

Đối với một cây nhị phân **không rỗng** gồm `n` nút, chiều cao theo cạnh `h`, các bất biến cơ bản là:

1. **Mỗi nút có không quá hai con:** `left` và `right`.
2. **Con trái và con phải có vai trò khác nhau**, kể cả khi một bên rỗng.
3. **Gốc không có cha; nút còn lại đúng một cha**, không có chu trình hay nút dùng chung dưới nhiều cha.
4. **Số cạnh bằng `n-1`**.
5. **Chiều cao** thỏa `\lceil\log_2(n+1)\rceil - 1 \le h \le n-1`.
6. Nếu là **full**: `L=I+1`; nếu là **perfect**: `n=2^{h+1}-1` và `L=2^h`.
7. Nếu là **complete**: các vị trí mức được lấp từ trái sang phải, nên lưu mảng đặc theo level-order là thích hợp.

Bảng chi phí cho các thuật toán minh họa:

| Thao tác | Thời gian | Bộ nhớ phụ | Ghi chú |
|---|---|---|---|
| Xem `left`/`right` của nút đã biết | `O(1)` | `O(1)` | Chưa gồm tìm nút |
| Tìm giá trị trong cây nhị phân bất kỳ | `O(n)` trường hợp xấu nhất | Tùy chiến lược duyệt | Không có bất biến sắp giá trị |
| Đếm nút hoặc lá bằng đệ quy | `O(n)` | `O(h+1)` | Call stack theo chiều sâu |
| Tính chiều cao theo đệ quy | `O(n)` | `O(h+1)` | Cần kết quả hai cây con |
| Duyệt DFS bằng stack tường minh | `O(n)` | `O(h+1)` cho preorder nhị phân | Chưa tính kết quả |
| Duyệt BFS bằng queue | `O(n)` | Tối đa `O(n)` | Thường phụ thuộc độ rộng mức |
| Kiểm tra cấu trúc có phải cây hợp lệ | `O(n)` | `O(n)` | Duyệt kèm tập định danh nút |
| Chèn giữ complete bằng BFS | `O(n)` trường hợp xấu nhất | `O(n)` | Có thể tối ưu nếu có chỉ mục vị trí |

Các chặn trên dùng mô hình mỗi lần xử lý giá trị và thao tác tham chiếu tốn `O(1)`. Nếu giá trị là đối tượng lớn hoặc xử lý nút phức tạp, cần cộng thêm chi phí xử lý đó.

**Phân biệt bộ nhớ phụ với kết quả:** một phép duyệt có thể chỉ dùng stack `O(h)` nhưng trả danh sách gồm `n` giá trị; riêng danh sách trả về đã tốn **`O(n)`** bộ nhớ.

## 13. Sai lầm thường gặp

1. **Hiểu “nhị phân” là luôn có hai con.** Đúng là tối đa hai; nút lá có không con, nút trong có thể chỉ một con.
2. **Bỏ phân biệt trái/phải.** Nút có duy nhất con phải không giống nút có duy nhất con trái.
3. **Coi mọi cây nhị phân là BST.** Không có bảo đảm thứ tự khóa nếu bài toán không thêm bất biến BST.
4. **Coi mọi cây nhị phân đều complete hoặc cân bằng.** Cây lệch vẫn hợp lệ và có thể cao tới `n-1` cạnh.
5. **Nhầm full và complete.** Full yêu cầu mỗi nút 0 hoặc 2 con; complete yêu cầu lấp các vị trí từ trái sang phải theo mức.
6. **Nhầm perfect với complete.** Perfect phải đầy mọi mức; complete được phép có mức cuối chưa đầy.
7. **Dùng công thức con ở mảng trên cây thưa nhưng bỏ ô rỗng.** Sẽ gán sai các vị trí con trái/phải.
8. **Nhầm chiều cao theo số nút và số cạnh.** Cây một nút cao `0` cạnh hoặc `1` nút, theo quy ước đã chọn.
9. **Cho rằng nhị phân bảo đảm tìm kiếm `O(\log n)`.** Cần bất biến tìm kiếm và chiều cao nhỏ; nếu không, tìm kiếm có thể `O(n)`.
10. **Dùng cùng một đối tượng nút cho hai vị trí con.** Điều đó tạo cấu trúc chia sẻ, không phải cây một cha.
11. **Tạo liên kết ngược gây chu trình.** Một thuật toán đệ quy có thể lặp vô hạn nếu đầu vào không phải cây.
12. **Duyệt preorder nhưng push trái trước phải.** Với stack LIFO, như vậy sẽ xử lý phải trước trái.
13. **Chỉ viết mã đệ quy trên cây cực sâu.** Có thể gặp giới hạn call stack; cân nhắc duyệt lặp.
14. **Cho rằng mọi thuật toán duyệt đều `O(n)` chỉ vì thăm mỗi nút một lần.** Nếu liên tục nối/copy danh sách kết quả trung gian, chi phí thực tế có thể cao hơn.
15. **Xóa nút trong mà không định nghĩa chính sách xử lý cây con.** Thao tác có thể phá cấu trúc hoặc làm mất dữ liệu không mong muốn.

## 14. Tự kiểm tra các trường hợp biên

Có thể dùng các hàm đã định nghĩa để kiểm tra các trường hợp cơ bản sau:

```python
# Cây rỗng
assert is_valid_binary_tree(None)
assert count_nodes(None) == 0
assert count_leaves(None) == 0
assert height_edges(None) == -1
assert inorder_linear(None) == []
assert level_order(None) == []

# Cây một nút
single = BinaryNode(10)
assert count_nodes(single) == 1
assert count_leaves(single) == 1
assert height_edges(single) == 0

# Nút có duy nhất con phải: vẫn là cây nhị phân hợp lệ.
right_only = BinaryNode(10, right=BinaryNode(20))
assert is_valid_binary_tree(right_only)
assert right_only.left is None
assert right_only.right.value == 20
assert inorder_linear(right_only) == [10, 20]

# Hai vị trí không được cùng trỏ vào một nút.
shared = BinaryNode("same")
not_a_tree = BinaryNode("root", left=shared, right=shared)
assert not is_valid_binary_tree(not_a_tree)

# Mọi kiểu duyệt đều phải xuất ra cùng số nút.
assert len(preorder_iterative(root)) == count_nodes(root)
assert len(inorder_linear(root)) == count_nodes(root)
assert len(level_order(root)) == count_nodes(root)
```

Đây là những phép thử minh họa; theo yêu cầu bài học, cần tiếp tục thử cây lệch sâu, cây đủ hai con, cây thưa, cây complete, giá trị trùng và cấu trúc không hợp lệ khi đưa mã vào hệ thống thực tế.

## 15. Bài tập thực hành có đáp án

### Bài 1. Tối đa hai con có nghĩa gì?

Một nút `A` có ba con trực tiếp `B, C, D`. Đây có phải nút hợp lệ trong cây nhị phân không? Nếu `A` chỉ có con phải `D` thì sao?

**Đáp án:** Ba con trực tiếp **không hợp lệ** trong cây nhị phân. Chỉ có con phải **hợp lệ**, vì một nút có thể có 0, 1 hoặc 2 con; phải giữ rõ vị trí phải.

### Bài 2. Thứ tự trái/phải

Hai cây cùng có nút gốc `A` và một nút `B`. Cây thứ nhất đặt `B` ở bên trái; cây thứ hai đặt `B` bên phải. Chúng có cùng hình dạng cây nhị phân không?

**Đáp án:** Không. Cả hai có cùng số nút, cạnh và chiều cao, nhưng khác **vị trí con**. Ví dụ duyệt inorder cho kết quả `[B,A]` ở cây trái và `[A,B]` ở cây phải.

### Bài 3. Số nút tối đa

Một cây nhị phân có chiều cao `h=3` cạnh. Có thể có tối đa bao nhiêu nút? Nếu có đúng số nút tối đa, cây thuộc loại nào?

**Đáp án:** Tối đa `2^(3+1)-1=15` nút. Nếu đạt số nút đó, mọi vị trí mức đều đầy, nên là **perfect** (đồng thời full và complete).

### Bài 4. Chiều cao tối thiểu

Một cây nhị phân có `n=13` nút. Chiều cao nhỏ nhất và lớn nhất theo cạnh là bao nhiêu?

**Đáp án:** Nhỏ nhất `\lceil\log_2(14)\rceil-1=4-1=3`; lớn nhất `12` nếu tất cả nút tạo thành một chuỗi.

### Bài 5. Full nhưng không complete

Cho cây:

```text
     A
    / \
   B   C
      / \
     D   E
```

Cây thuộc loại full, complete hay perfect?

**Đáp án:** **Full** vì `A` và `C` có đúng hai con, còn `B,D,E` là lá. **Không complete** vì mức cuối có nút dưới `C` trong khi các vị trí bên trái dưới `B` còn trống; do đó cũng **không perfect**.

### Bài 6. Complete nhưng không full

Cho cây:

```text
     A
    / \
   B   C
  /
 D
```

Phân loại cây.

**Đáp án:** **Complete** vì các mức trước mức cuối đều đầy và `D` nằm ở vị trí trái nhất của mức cuối. **Không full** vì `B` chỉ có một con; do đó không perfect.

### Bài 7. Lá trong cây full

Một cây full không rỗng có `I=6` nút trong. Có bao nhiêu lá và tổng cộng bao nhiêu nút?

**Đáp án:** `L=I+1=7` lá; `n=I+L=13` nút; số cạnh `12` cũng bằng `2I`.

### Bài 8. Chỉ số mảng

Một cây complete được lưu trong mảng từ chỉ số `0`. Nút ở vị trí `i=4` có các vị trí con và cha theo công thức là gì?

**Đáp án:** Con trái ở `2×4+1=9`, con phải ở `2×4+2=10`, cha ở `\lfloor(4-1)/2\rfloor=1`. Các con chỉ tồn tại nếu chỉ số tương ứng nhỏ hơn độ dài mảng.

### Bài 9. Ô rỗng trong mảng

Trong cây có gốc `A`, con trái `B`, con phải `C` và `C` có duy nhất con phải `D`, vì sao không thể mã hóa đúng cấu trúc bằng mảng mức đặc `[A,B,C,D]`?

**Đáp án:** Theo công thức `2i+1`, ô `3` là con trái của `B`, không phải con phải của `C`. Phải giữ các ô rỗng trung gian, chẳng hạn `[A,B,C,None,None,None,D]`, hoặc dùng nút liên kết.

### Bài 10. Duyệt cây

Với cây mẫu đầu bài:

```text
       A
      / \
     B   C
    / \   \
   D   E   F
```

Hãy nêu kết quả preorder, inorder, postorder và level-order.

**Đáp án:** Preorder `A,B,D,E,C,F`; inorder `D,B,E,A,C,F`; postorder `D,E,B,F,C,A`; level-order `A,B,C,D,E,F`.

### Bài 11. Độ phức tạp tìm kiếm

Một cây nhị phân có `n` nút, nhưng không có quy tắc sắp xếp giá trị. Nếu muốn tìm một giá trị, có thể bảo đảm chỉ phải đi qua `O(\log n)` nút không?

**Đáp án:** Không. Trong trường hợp xấu nhất, giá trị cần tìm nằm ở nút cuối được duyệt hoặc không tồn tại, nên phải xem tới **`O(n)`** nút. Cây có hai con không tự động có bất biến tìm kiếm.

### Bài 12. Cây một nút

Một cây chỉ có nút `R`. Nút này là lá hay nút trong? Chiều cao cây theo cạnh là bao nhiêu? Cây thuộc loại full, complete và perfect không?

**Đáp án:** `R` là **gốc và lá**; chiều cao theo cạnh `0`. Cây một nút thỏa cả **full, complete và perfect**.

### Bài 13. Phát hiện nút bị chia sẻ

Giả sử `A.left = X` và `A.right = X`, với cùng một **đối tượng** `X`. Vì sao cấu trúc không phải cây nhị phân hợp lệ dù `A` có hai trường con?

**Đáp án:** Một nút thật sự `X` bị tham chiếu từ hai vị trí cha–con, vi phạm bất biến mỗi nút không phải gốc có **đúng một cha và đúng một đường đi từ gốc**. Đây là cấu trúc đồ thị có chia sẻ nút. Hàm kiểm tra dùng định danh đối tượng sẽ phát hiện `X` xuất hiện hai lần.

### Bài 14. Chọn cấu trúc

Ứng dụng cần giữ một cây nhị phân rất lệch và thưa. Nên ưu tiên mảng vị trí mức có nhiều ô `None` hay các nút liên kết? Vì sao?

**Đáp án:** **Nút liên kết** thường phù hợp hơn: chỉ cấp phát các nút có thật và hai tham chiếu con cho mỗi nút, dùng **`O(n)` bộ nhớ**. Mảng theo vị trí nếu giữ mọi ô trống đến chỉ số lớn nhất có thể phình rất nhanh theo chiều cao cây.

### Bài 15. Cài đặt kiểm tra nút lá

Hãy viết một hàm nhận `node` và trả `True` khi nút là lá. Trường hợp `node is None` có phải lá không?

**Đáp án:**

```python
def is_leaf(node):
    return (
        node is not None
        and node.left is None
        and node.right is None
    )
```

`None` biểu diễn **cây con rỗng**, không phải một nút lá thực sự. Hàm trả `False` cho `None`.

## 16. Tổng kết

**Cây nhị phân** là cây có gốc trong đó mỗi nút có **tối đa hai vị trí con phân biệt: trái và phải**. Nút có thể có `0`, `1` hoặc `2` con, và một nút chỉ có con phải không tương đương với nút chỉ có con trái. Cấu trúc còn phải giữ bất biến cây: **một gốc, một cha cho mỗi nút còn lại, không chu trình và không dùng chung một nút dưới nhiều vị trí**.

Với `n≥1` nút và chiều cao `h` theo số cạnh, ta có **`h+1≤n≤2^{h+1}-1`**. **Full** yêu cầu mọi nút có 0 hoặc 2 con; **complete** lấp mức cuối từ trái sang phải; **perfect** đầy tất cả các mức. Những điều kiện này khác với bất biến của BST hay heap, cũng khác với yêu cầu cân bằng.

Cài đặt **nút liên kết** phù hợp với cây thưa và cho phép truy cập con trực tiếp trong `O(1)`; cài đặt **mảng theo mức** đặc biệt hiệu quả cho complete tree. Các phép duyệt preorder, inorder, postorder và level-order thường xử lý mọi nút trong **`O(n)` thời gian** nếu tránh sao chép danh sách kết quả không cần thiết. Khi áp dụng thực tế, hãy xác định rõ **hình dạng, thứ tự trái/phải, chính sách chỉnh sửa, bất biến giá trị và chi phí bộ nhớ** trước khi chọn loại cây.

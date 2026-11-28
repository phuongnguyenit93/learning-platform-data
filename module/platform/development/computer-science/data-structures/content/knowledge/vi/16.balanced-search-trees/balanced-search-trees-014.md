# Duy trì bộ duyệt và tham chiếu khi quay hoặc tổ chức lại cây

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **tham chiếu tới một đối tượng nút**, **vị trí của nút trong cây**, **khóa logic của bản ghi** và **trạng thái nội bộ của bộ duyệt (iterator)**.
- Giải thích vì sao một phép quay AVL/Red–Black/splay **giữ nguyên tập nút và thứ tự inorder**, nhưng có thể đổi **`root`, `parent`, `left`, `right`** và làm hỏng bộ duyệt ghi nhớ đường đi cũ.
- Thực hiện quay trái/phải với **mọi liên kết hai chiều** và biết kiểm tra bất biến BST cùng `parent` sau khi quay.
- Phân biệt **bộ duyệt dựa trên ngăn xếp**, **con trỏ nút + successor**, **bộ duyệt fail-fast theo phiên bản** và **bản chụp (snapshot)**; hiểu điều kiện an toàn của từng kiểu.
- Phân tích ảnh hưởng của **chèn, xóa, thay nút bằng successor, splay, tách/nối cây, tái xây dựng toàn cây** lên tham chiếu và bộ duyệt.
- Trình bày giới hạn O(h + k) của duyệt `k` khóa liên tiếp từ một cận trên cây có chiều cao `h`, và O(log n + k) khi cây được cân bằng.
- Nêu rõ hợp đồng API về **khóa trùng, xóa rồi chèn lại cùng khóa, nút đã xóa, cập nhật giá trị, thay đổi thứ tự khóa, đồng thời và iterator**.
- Đọc ví dụ Python tự chứa có quay tại chỗ, xóa theo **chuyển nút vật lý (transplant)**, kiểm tra tham chiếu nút, con trỏ cha, epoch của iterator và đối chiếu inorder.
- Chọn chiến lược duyệt và tham chiếu phù hợp cho chỉ mục bài học có thứ tự trong module `COMPUTER_SCIENCE_DATA_STRUCTURES`.

## 1. Vấn đề: cây vẫn đúng nhưng bộ duyệt có thể sai

Trong **cây tìm kiếm nhị phân** (*binary search tree*, BST), mọi khóa ở cây con trái của một nút đều nhỏ hơn khóa tại nút, mọi khóa ở cây con phải đều lớn hơn. AVL, Red–Black Tree và splay tree đều giữ **bất biến thứ tự** này, nhưng chúng có thể quay hoặc sắp xếp lại các liên kết để thay đổi hình dạng cây.

Hãy xem tình huống đơn giản:

```text
TRƯỚC quay trái tại 20:       SAU quay:

       20                         30
         \                       /  \
          30                    20  40
            \
             40

Inorder: 20,30,40             Inorder: 20,30,40
```

**Ba đối tượng nút** không bị tạo lại hay xóa đi nếu ta thực hiện **phép quay tại chỗ**. Dãy khóa tăng dần cũng không đổi. Tuy vậy:

- Trước quay, `root` trỏ tới nút `20`; sau quay, `root` phải trỏ tới nút `30`.
- Trước quay, `20.right` là nút `30`; sau quay, `20.right` là `None`.
- Trước quay, `30.parent` là `20`; sau quay, `30.parent` là `None` và `20.parent` là `30`.
- Một bộ duyệt vừa trả `20` và dự tính dùng **`20.right` của hình dạng cũ** để tiếp tục có thể bỏ qua `30,40`.

**Bất biến dữ liệu đúng không đồng nghĩa mọi bộ duyệt đang chạy đều còn đúng.** Đây là trọng tâm của bài học.

### 1.1. Bốn loại “tham chiếu” rất khác nhau

| Loại | Ví dụ | Điều nó biểu diễn | Tác động của quay tại chỗ |
| --- | --- | --- | --- |
| **Tham chiếu đối tượng nút** | `handle = node20` | Chính đối tượng nút đang chứa `key=20` | **Vẫn là nút đó**, nếu không xóa/tạo lại nút |
| **Tham chiếu vai trò/vị trí** | `old_root = tree.root` | Nút nào *đang đóng vai trò gốc* lúc lấy | `old_root` vẫn là nút cũ nhưng **không còn là gốc** |
| **Liên kết cấu trúc** | `node.parent`, `node.left` | Quan hệ hiện tại của nút | **Phải cập nhật** sau quay |
| **Trạng thái bộ duyệt** | `stack=[ancestors...]` hoặc `cursor` | Cách tìm phần tử kế tiếp | Có thể **cũ**, phụ thuộc thuật toán bộ duyệt |
| **Khóa logic** | `lesson_id=20` | Định danh dùng tìm lại bản ghi | Không đổi khi chỉ quay các liên kết |

Ở đây “tham chiếu nút” là một **tham chiếu tới đối tượng tồn tại trong bộ nhớ**, không phải “khóa để truy xuất”. Có thể giữ nguyên đối tượng nút nhưng thay đổi vị trí của nó; cũng có thể **xóa đối tượng nút** rồi tạo nút khác mang **cùng khóa**. Hai thao tác đó có hợp đồng rất khác nhau.

### 1.2. Từ ngữ “iterator còn hợp lệ” cần một hợp đồng cụ thể

Một API có thể tuyên bố:

1. **Ổn định nút:** đối tượng nút còn tồn tại sau phép quay và có thể đọc `key/value`.
2. **Ổn định phần tử logic:** một khóa vẫn tìm được bằng `find(key)`.
3. **Ổn định bộ duyệt:** sau thay đổi, gọi `next()` vẫn trả đúng phần tử tiếp theo mà không lặp/thiếu.
4. **Ổn định snapshot:** việc duyệt giữ nguyên danh sách bản ghi tại một thời điểm đã định.

Không có suy luận tự động từ **(1)** sang **(3)** hoặc **(4)**. Một bộ duyệt có thể giữ con trỏ tới nút hợp lệ mà vẫn đi sai thứ tự nếu nó giữ **ngăn xếp tổ tiên cũ**.

> Mọi tuyên bố kiểu “iterator không bị vô hiệu sau quay” phải nói rõ **mô hình bộ duyệt**, **giao diện thư viện**, **quy tắc sửa đổi** và **điều kiện đồng bộ**.

## 2. Bất biến của cây và tính đúng đắn của tham chiếu

Với BST khóa phân biệt, bất biến thứ tự có thể viết:

\[
\forall v:\quad
\operatorname{keys}(v.left)<v.key<
\operatorname{keys}(v.right).
\]

Ký hiệu này nói về **mọi khóa** trong cây con. Ngoài ra, một triển khai dùng con trỏ `parent` còn cần:

\[
\begin{aligned}
v.left\ne\varnothing&\Rightarrow v.left.parent=v,\\
v.right\ne\varnothing&\Rightarrow v.right.parent=v,\\
root\ne\varnothing&\Rightarrow root.parent=\varnothing.
\end{aligned}
\]

Các điều kiện bổ sung cần kiểm tra:

- Mỗi đối tượng nút thật có **đúng một đường** từ gốc tới nó; không có chu trình hoặc một nút được gắn làm con ở hai vị trí.
- Không có khóa trùng nếu hợp đồng là ordered **Map/Set theo khóa duy nhất**.
- Trường `size` đếm đúng số nút thật **đang thuộc cây**.
- Metadata tăng cường (`height`, `color`, `subtree_size`, tổng giá trị cây con...) phải được cập nhật theo bất biến riêng của cấu trúc.
- Một handle tới nút đã xóa **không được coi là handle còn thuộc cây**, dù ngôn ngữ có thể vẫn giữ đối tượng trong bộ nhớ.

### 2.1. Hai chiều của cùng một cạnh

```text
                cha P
                 |
           P.left = C
                 |
                con C

            C.parent = P
```

Nếu chỉ cập nhật `P.left` mà quên `C.parent`, duyệt inorder **chỉ bằng trái/phải** có thể vẫn cho đáp án đúng, nhưng bộ duyệt dùng `parent` để tìm successor sẽ đi sai.

### 2.2. Tham chiếu nút và giá trị gắn với nút

Một ordered Map thường lưu cặp `(key,value)` trên cùng đối tượng nút. Phép quay **không nên hoán đổi `key` hoặc `value`**:

```text
handle = tham chiếu nút (20, "array")

Quay trái/phải:
  - handle vẫn trỏ cùng đối tượng.
  - handle.key vẫn 20.
  - handle.value vẫn "array".
  - handle.parent/left/right có thể thay đổi.
```

Nếu thuật toán “quay” bằng cách đổi giá trị khóa ở các đối tượng thay vì đổi liên kết, nó có thể phá hợp đồng **handle trỏ tới bản ghi nào**. Cách đó **không tương đương** với quay liên kết khi bên ngoài đang giữ tham chiếu tới nút.

## 3. Quay trái và quay phải: kiểm soát mọi liên kết

### 3.1. Quay trái tại nút `x`

Điều kiện: `y=x.right` tồn tại.

```text
      q (cha ngoài cụm)              q
             |                       |
             x                       y
            / \                     / \
           A   y                   x   C
              / \                 / \
             B   C               A   B
```

Giả sử `x.key<y.key` và các cây con có khóa:

\[
\operatorname{keys}(A)<x.key<
\operatorname{keys}(B)<y.key<
\operatorname{keys}(C).
\]

Sau quay:

1. `x.right` nhận cây con `B` (tức `y.left` cũ); nếu `B` không rỗng, đặt `B.parent=x`.
2. `y.parent` nhận `q` (cha cũ của `x`).
3. `q` phải trỏ tới `y` ở **đúng phía cũ** của `x`; nếu `q=None` thì cập nhật `tree.root=y`.
4. `y.left=x` và `x.parent=y`.

Dãy inorder vẫn là `A,x,B,y,C`. Mọi đối tượng nút trong cụm còn tồn tại và giữ nguyên `key/value`; chỉ **quan hệ cấu trúc** thay đổi.

### 3.2. Quay phải tại nút `y`

Trường hợp đối xứng, điều kiện `x=y.left` tồn tại:

```text
      q                              q
      |                              |
      y                              x
     / \                            / \
    x   C                          A   y
   / \                                / \
  A   B                              B   C
```

Trong quay phải, `B` chuyển thành **`y.left`**. Mọi liên kết cha phải được cập nhật đối xứng với quay trái.

### 3.3. Bảng kiểm tra nhanh sau quay

| Điểm kiểm tra | Quay trái `x→y` | Quay phải `y→x` |
| --- | --- | --- |
| Gốc cụm mới | `y` | `x` |
| Nút đi xuống | `x` | `y` |
| Cây con giữa `B` | `x.right=B` | `y.left=B` |
| Cha của `B` | `x` nếu `B` tồn tại | `y` nếu `B` tồn tại |
| Cha của gốc cụm mới | Cha cũ của `x` | Cha cũ của `y` |
| Liên kết cha bên ngoài | Trỏ đến `y` | Trỏ đến `x` |
| Inorder | **Không đổi** | **Không đổi** |
| `root` khi quay tại gốc | Cập nhật `root=y` | Cập nhật `root=x` |

Một phép quay đơn sửa số lượng liên kết **O(1)**. Nếu cần tăng cường `subtree_size`, có thể tính lại trường này ở **nút đi xuống trước, nút đi lên sau**, miễn các cây con đã có thông tin đúng.

## 4. Vì sao iterator dựa trên ngăn xếp dễ mất hiệu lực?

Một bộ duyệt inorder phổ biến dùng ngăn xếp:

```python
def inorder(root):
    stack = []
    node = root
    while stack or node is not None:
        while node is not None:
            stack.append(node)
            node = node.left
        node = stack.pop()
        yield node.key, node.value
        node = node.right
```

**Nếu cây không bị thay đổi** trong thời gian duyệt, thuật toán trả các khóa tăng dần, O(n) thời gian toàn bộ và O(h) bộ nhớ phụ với `h` là chiều cao cây.

### 4.1. Một thay đổi ở đúng điểm tạm dừng

```text
Iterator vừa yield(20) và tạm dừng:

      20
        \
         30
           \
            40
```

Nếu một luồng khác **quay trái tại 20** trong lúc iterator đang tạm dừng, cây thành:

```text
        30
       /  \
      20   40
```

Ở lần `next()` kế tiếp, dòng `node = node.right` trong iterator sẽ sử dụng **`node=20` đang giữ**. Nhưng **`20.right` bây giờ bằng `None`**, nên iterator có thể kết thúc sớm, **bỏ lỡ khóa 30 và 40**.

Mọi đối tượng nút vẫn tồn tại, inorder của **cây mới** vẫn đúng, nhưng **lộ trình nội bộ cũ của bộ duyệt** không còn đúng.

### 4.2. Không chỉ mất phần tử: còn nguy cơ lặp hoặc đi ngược

Một iterator giữ trước **ngăn xếp tổ tiên** có thể chứa những nút mà vị trí đã đổi. Sau quay, ngăn xếp đó có thể không còn là đường từ gốc tới nút hiện tại. Tùy cách viết, lần tiếp theo có thể:

- Lặp lại một phần tử đã trả.
- Bỏ qua những phần tử chưa trả.
- Đi ngược thứ tự khóa.
- Không dừng ở đúng điểm.

Không nên khẳng định một kiểu lỗi cố định cho mọi iterator. Điều chắc chắn là **ngăn xếp cũ không còn được bảo đảm mô tả cấu trúc hiện tại**.

### 4.3. Tại sao “bộ duyệt trên cây cân bằng” không tự giải quyết vấn đề?

AVL hoặc RB Tree vẫn có thể thực hiện phép quay sau chèn/xóa. Splay còn **quay trong lúc tìm kiếm**. Vì vậy:

- Với **AVL/RB**, thao tác chỉ đọc `find` thông thường không thay đổi cấu trúc, nhưng **cập nhật** có thể vô hiệu hóa một số iterator.
- Với **splay**, một thao tác có tên `get` hay `contains` cũng có thể đổi cấu trúc, nên người dùng API càng phải thận trọng khi iterator đang sống.

**Thư viện cụ thể có thể có hợp đồng iterator khác nhau.** Tính đúng đắn phụ thuộc chiến lược bộ duyệt, không chỉ tên của họ cây.

## 5. Bốn chiến lược duyệt khi cây có thể bị tổ chức lại

### 5.1. Iterator fail-fast bằng bộ đếm phiên bản

Giữ `tree.epoch` — số phiên bản tăng sau bất kỳ thao tác nào có thể làm thay đổi cấu trúc hoặc giá trị theo hợp đồng. Khi tạo bộ duyệt, lưu `expected_epoch`. Trước mỗi lần `next()`:

```text
if tree.epoch != expected_epoch:
    raise RuntimeError("Cây đã thay đổi trong lúc duyệt")
```

Ưu điểm: không âm thầm trả kết quả sai khi cây bị thay đổi trong một chuỗi thao tác **tuần tự**.

Giới hạn:

- Nó **không phải cơ chế khóa** bảo vệ truy cập đồng thời; nếu đọc epoch và sửa cây đan xen, vẫn có thể có race condition.
- Phải định nghĩa **thế nào là một thay đổi**. Ví dụ ở bài này tăng epoch cho cả quay, thêm/xóa nút và cập nhật giá trị cũ.
- Nếu chương trình quên tăng epoch ở một đường sửa dữ liệu, bộ duyệt có thể không phát hiện thay đổi.
- Một số API dùng fail-fast theo **thay đổi tập khóa** thay vì mọi thay đổi cấu trúc; hợp đồng ấy khác với ví dụ này.

**Chi tiết quan trọng:** bộ duyệt phải ghi `expected_epoch` **ngay khi được tạo**, không đợi đến lần gọi `next()` đầu tiên, nếu muốn phát hiện việc cây đổi **giữa lúc tạo và bắt đầu duyệt**.

### 5.2. Con trỏ nút hiện tại và thuật toán successor

Một cách khác là lưu **tham chiếu nút vừa trả**, rồi tính phần tử kế tiếp dựa trên **`parent/left/right` hiện tại**:

```text
successor(x):
    nếu x.right tồn tại: lấy nút trái nhất trong x.right
    nếu không:
        đi lên cha cho đến khi từ một con trái bước lên cha
        trả cha ấy (hoặc None nếu đã qua phần tử lớn nhất)
```

Nếu phép quay **được thực hiện tại chỗ, hoàn tất**, giữ mọi liên kết cha–con đúng và **nút hiện tại vẫn thuộc cây**, tính successor từ cấu trúc mới sẽ trả **khóa kế tiếp trong thứ tự hiện tại**, vì các phép quay không đổi inorder.

Nhưng giới hạn của một con trỏ sống là:

- **Xóa nút đang giữ** khiến handle không còn thuộc cây; phải từ chối đi tiếp.
- **Chèn/xóa nút khác** có thể làm tập phần tử trong những lần gọi kế tiếp thay đổi. Cursor này là **live**, không phải snapshot.
- **Xây dựng lại cây bằng những nút mới** làm các handle cũ không còn là nút của phiên bản cây mới.
- **Sửa đổi đồng thời** vẫn cần đồng bộ. Sự đúng đắn của `successor` giả định cây ở **một trạng thái hoàn chỉnh, nhất quán** khi duyệt các con trỏ.

### 5.3. Bộ duyệt theo khóa thay vì theo nút

Lưu `last_key` và gọi `upper_bound(last_key)` trên **cây hiện tại** ở mỗi bước:

```text
last_key = 20
next_key = upper_bound(20)  # khóa nhỏ nhất > 20 hiện có
```

Ưu điểm: không cần giữ tham chiếu tới nút có thể đã bị xóa; có thể phục hồi vị trí sau **tái xây dựng cây** nếu khóa so sánh ổn định.

Nhược điểm:

- Nếu mỗi lần phải đi từ gốc, một bước tốn O(h), nên trả `k` phần tử có thể tốn **O(kh)**, hay O(k log n) nếu cây cân bằng.
- Những khóa được chèn/xóa giữa các lần gọi có thể được thấy hoặc không thấy tùy vị trí; vẫn cần **hợp đồng duyệt live**.
- Nếu khóa bị sửa ngay trong nút, bất biến BST có thể hỏng; muốn đổi khóa phải **xóa khóa cũ và chèn khóa mới**.

### 5.4. Snapshot: chụp danh sách kết quả ở một thời điểm

Tạo một danh sách `[(key,value), ...]` bằng inorder **trước khi duyệt** rồi đọc trên danh sách ấy. Nếu cây thay đổi sau đó, trình tự phần tử đã chụp vẫn giữ nguyên.

Đánh đổi:

- Tạo snapshot cần **O(n) thời gian và O(n) bộ nhớ phụ** nếu chụp toàn cây.
- Với Python, danh sách tuple `(key,value)` thường chỉ là **snapshot nông**: các đối tượng `value` khả biến vẫn có thể bị thay đổi bên ngoài. Cần sao chép sâu/đóng băng giá trị nếu muốn snapshot thực sự cô lập trạng thái bản ghi.
- Khi có nhiều luồng, bước **tạo snapshot** cũng cần chiến lược đồng bộ hoặc cơ chế phiên bản thích hợp để tránh đọc một cây đang bị sửa dở.

### 5.5. Bảng so sánh nhanh

| Cách duyệt | Sau quay tại chỗ | Sau xóa nút đang giữ | Chi phí phụ | Trường hợp nên dùng |
| --- | --- | --- | --- | --- |
| Ngăn xếp inorder thô | **Không được bảo đảm** | Không được bảo đảm | O(h) | Duyệt khi cây không đổi |
| Fail-fast + ngăn xếp | **Phát hiện và báo lỗi** nếu epoch tăng | Báo lỗi nếu epoch tăng | O(h), kiểm tra O(1) mỗi bước | Tránh sai âm thầm khi bị sửa |
| Cursor nút + successor | Có thể tiếp tục đúng nếu nút sống và liên kết hoàn chỉnh | **Handle không hợp lệ** | O(1) handle, tìm successor theo đường đi | Live traversal tuần tự |
| Cursor khóa + upper bound | Không phụ thuộc handle | Có thể tìm lại từ khóa cũ | O(h) mỗi bước | Duyệt có thể phục hồi qua rebuild |
| Snapshot danh sách | Không đổi kết quả đã chụp | Không đổi danh sách đã chụp | O(n) thời gian/bộ nhớ khởi tạo | Báo cáo, xuất dữ liệu nhất quán |

Không cách nào tự động cho phép sửa đổi đồng thời không khóa. **Ổn định iterator** và **an toàn luồng** là hai yêu cầu riêng.

## 6. Duyệt một đoạn khóa: O(h + k) thay vì tìm lại từng phần tử

Cho cây chứa `n` khóa, chiều cao `h` tính theo **số nút thật** trên đường dài nhất. Muốn trả `k` khóa trong khoảng `[lo,hi]`:

1. Dùng `lower_bound(lo)` để tìm **khóa nhỏ nhất không nhỏ hơn `lo`** trong O(h).
2. Từ nút này, lần lượt tính `successor` cho đến khi khóa vượt `hi` hoặc cây hết phần tử.
3. Chỉ trả những nút thuộc khoảng.

```text
Khóa theo thứ tự:   10, 20, 30, 40, 50, 60, 70
Khoảng cần trả:         [25, 55]
lower_bound(25) --> 30
successor --> 40 --> 50 --> 60 (dừng vì 60 > 55)
Kết quả: 30, 40, 50
```

### 6.1. Một lần successor có thể O(h)

Nếu nút `x` có cây con phải, successor là nút trái nhất trong cây con ấy. Nếu không, ta có thể phải **leo nhiều tổ tiên** để tìm tổ tiên đầu tiên mà ta bước lên từ **con trái**. Một lần successor vì thế có thể tốn O(h) trong trường hợp xấu nhất.

Không nên diễn giải “bộ duyệt theo successor O(h+k)” thành “**mỗi** phép successor đều O(1) xấu nhất”.

### 6.2. Nhưng nhiều bước liên tiếp có tổng chi phí tuyến tính theo số phần tử đã đi qua

Trong một lần duyệt nhiều successor liên tiếp **trên cây không đổi**, mỗi cạnh trên phần đường duyệt được đi lên/xuống số lần bị chặn, và mỗi nút liên quan chỉ được xử lý hằng số lần trong toàn chuỗi. Vì vậy:

\[
\text{range}(lo,hi)=O(h+k),
\]

với `k` phần tử được trả và giả định duyệt theo successor có `parent` hoặc một ngăn xếp đang mô tả cây nhất quán.

Nếu cây AVL/Red–Black được duy trì đúng, `h=O(log n)`:

\[
\text{range}(lo,hi)=O(\log n+k).
\]

Với BST thường hoặc splay tree ở **một trạng thái có chiều cao `h=Θ(n)`**, cận chạy trên đường cụ thể là O(h+k). Chỉ gọi tên splay không cho phép đổi `h` tức thời thành O(log n).

### 6.3. Duyệt khoảng có splay bên trong cần được định nghĩa lại

Nếu mỗi lần lấy phần tử kế tiếp ta lại gọi `get` **và splay** phần tử đó, hình dạng cây thay đổi liên tục. Không thể tự động dùng chứng minh O(h+k) của một hành trình successor **trên cây cố định** cho thiết kế ấy.

Muốn duyệt khoảng trong splay tree, có thể:

- Splay tại **điểm cận** trước khi tạo iterator, sau đó đi successor trên cây **không bị tổ chức lại thêm** trong thời gian duyệt.
- Dùng **bản chụp** hoặc bộ duyệt theo khóa có hành vi rõ khi gặp cập nhật.
- Phân tích riêng một thuật toán duyệt có splay từng nút; không mượn cận cố định mà không chứng minh.

## 7. Chèn và cập nhật giá trị: điều gì ổn định?

### 7.1. Chèn khóa mới vào BST cân bằng

Giả sử có cây:

```text
        40
       /  \
      20   60
```

Chèn `30` sẽ tạo nút mới đúng vị trí BST, sau đó một thuật toán AVL/RB có thể quay hoặc đổi màu để duy trì cân bằng. Nếu **quay bằng nối lại các đối tượng nút hiện có**, handle ngoài cây đang giữ tới nút `20` hoặc `40` vẫn trỏ đúng những đối tượng đó, nhưng vị trí cha/con có thể thay đổi.

Một iterator đang duyệt trước khi chèn **không nhất thiết** tự động thấy khóa `30`, ngay cả nếu mọi node handle cũ vẫn sống.

### 7.2. Cập nhật `value` của khóa đã tồn tại

Với ordered Map:

```text
put(30, "queue")
put(30, "stack")
```

Một chính sách hợp lý là **giữ nút khóa `30`**, thay `value` từ `"queue"` thành `"stack"`. Thứ tự BST không đổi, nhưng:

- Bộ duyệt **live** có thể nhìn thấy giá trị mới.
- Snapshot nông chỉ giữ đối tượng giá trị cũ; nếu là chuỗi bất biến, tuple cũ giữ chuỗi cũ.
- Một iterator yêu cầu **không có bất kỳ cập nhật nào** có thể fail-fast cả khi chỉ đổi `value`, như mã ví dụ ở phần sau.
- Nếu API chỉ tăng `modCount` khi **thay đổi cấu trúc**, hành vi lại khác. Cần nói rõ hợp đồng.

### 7.3. Không thay `key` tại chỗ

Nếu đổi khóa `(30, "ds-queue")` thành `(45, "ds-queue")` mà không xóa/chèn lại, khóa mới có thể nằm **sai cây con**. Đây là lỗi BST chứ không chỉ lỗi iterator.

Quy trình đúng về logic:

1. Loại khóa cũ khỏi chỉ mục có thứ tự.
2. Thêm khóa mới đúng vị trí BST.
3. Nếu có nhiều chỉ mục, cập nhật nhất quán các bản ghi và quan hệ liên quan.

Việc **thay đổi khóa logic** khác hoàn toàn với **quay liên kết không đổi khóa**.

## 8. Xóa: hai cách hiện thực có tác động tham chiếu khác nhau

Xóa nút có hai con thường là nguồn lỗi lớn nhất nếu chương trình giữ handle tới đối tượng nút.

### 8.1. Cách A: sao chép nội dung của successor vào nút bị xóa

Cho:

```text
              40
             /  \
           20    60
                /  \
               50  70
```

Muốn xóa khóa `40`, một cài đặt đơn giản có thể:

1. Tìm successor `50`.
2. **Sao chép `key=50` và `value`** từ nút `50` vào **đối tượng nút vốn chứa 40**.
3. Loại đối tượng nút `50` cũ khỏi vị trí của nó.

```text
handle_old_40 ---> đối tượng gốc cũ, giờ key=50
handle_old_50 ---> đối tượng successor cũ, giờ bị tách khỏi cây
```

Dãy inorder và cấu trúc BST sau xóa **có thể hoàn toàn đúng**, nhưng **định danh logic của hai handle đã thay đổi**. Một chương trình bên ngoài tin rằng `handle_old_40` mãi đại diện bài `40` sẽ bị bất ngờ.

Nếu API công khai **tham chiếu nút ổn định theo bản ghi**, đây là một vấn đề cần giải quyết rõ ràng, không phải lỗi chỉ xuất hiện khi memory bị giải phóng.

### 8.2. Cách B: di chuyển đối tượng successor thật (physical transplant)

Một chiến lược khác:

1. Tìm nút `z` mang khóa cần xóa.
2. Nếu `z` có hai con, tìm nút successor `y=min(z.right)`.
3. **Tách chính đối tượng `y`** khỏi vị trí cũ và nối nó vào vị trí của `z`.
4. Loại `z` khỏi cây và đánh dấu handle của `z` đã hết hiệu lực.

```text
TRƯỚC:                         SAU transplant:

        40(z)                          50(y)
       /     \                        /     \
      20      60                     20      60
             /  \                              \
           50(y)  70                           70
```

Trong cách này:

- Handle tới `z` **không còn thuộc cây**; phép đọc qua API phải báo handle đã xóa.
- Handle tới đối tượng successor `y` vẫn trỏ **chính `y` với khóa 50**.
- Handle tới các nút khác vẫn giữ đối tượng và khóa/giá trị của chúng.
- `parent` của các nút được nối lại phải chính xác; cây có thể cần **tái cân bằng** nếu nó là AVL/RB, ngoài thao tác xóa BST cơ sở.

**Transplant không đồng nghĩa BST cân bằng tự động.** Các bước trên chỉ đảm bảo cấu trúc và thứ tự BST; nếu đang cài AVL/RB, cần bổ sung quy tắc sửa chiều cao/màu.

### 8.3. Nút đã xóa không tự “sống lại” khi chèn lại cùng khóa

Giả sử đã xóa `40`, rồi sau đó chèn lại khóa `40`:

```text
old_handle_40: đối tượng cũ, đã tách khỏi cây
find(40):      đối tượng mới được thêm sau đó
```

**Khóa logic trùng không làm hai đối tượng nút trở thành một.** API cung cấp node handle nên có trạng thái `alive/owner/generation`, hoặc quy định handle không được sử dụng sau xóa. Mã Python của bài dùng **owner token** để phát hiện handle đã bị loại, nhưng chính sách bộ nhớ thật còn tùy ngôn ngữ.

### 8.4. Không nhầm “Python còn tham chiếu” với “nút còn thuộc cây”

Trong Python, một biến ngoài cây vẫn có thể tham chiếu tới một đối tượng đã bị **tách khỏi cây**, nên đối tượng chưa chắc được giải phóng ngay. Nhưng việc nó vẫn còn trong RAM **không chứng minh** nó còn là phần tử của chỉ mục.

Trong C/C++ với cấp phát thủ công, con trỏ tới vùng nhớ đã giải phóng có thể trở thành **dangling pointer**, nguy hiểm hơn. Việc thiết kế handle an toàn cần áp dụng đúng quy tắc sở hữu bộ nhớ của ngôn ngữ và thư viện.

## 9. Tái tổ chức mạnh hơn quay: splay, split, join, rebuild, B-tree

Không phải mọi phép “cân bằng lại” đều chỉ thay vài liên kết nhị phân.

### 9.1. Splay trên một BST đã có

Splay đưa một nút vừa truy cập lên gốc bằng zig, zig-zig và zig-zag. Nếu chỉ dùng **quay tại chỗ**:

- Những đối tượng nút chưa bị xóa vẫn tồn tại.
- Inorder giữ nguyên.
- `root` và nhiều liên kết `parent/left/right` có thể đổi.
- Iterator dựa trên đường đi/stack có thể mất hiệu lực **ngay sau `get`**, không chỉ sau `put/delete`.

Một cursor lưu nút vừa trả và tính successor từ liên kết **hiện tại** có thể đi tiếp sau khi splay hoàn tất, với điều kiện cursor vẫn thuộc cây và không có sửa đổi đồng thời.

### 9.2. Split và join

Tách một cây theo khóa `k` thành hai cây `L,R`, hoặc nối hai cây có điều kiện mọi khóa `L` nhỏ hơn mọi khóa `R`, có thể **chuyển quyền sở hữu nút giữa các cây**.

Nếu handle chứa thông tin `owner`:

- Nó có thể vẫn chỉ đúng **đối tượng nút vật lý**.
- Nhưng các API `treeA.successor(handle)` có thể phải từ chối nếu handle đã chuyển sang `treeB`.
- Phải cập nhật **owner, parent gốc và phiên bản của cả hai cây**, hoặc thiết kế handle độc lập với owner và kiểm tra thành viên bằng cơ chế khác.

Ví dụ Python sau **không cung cấp split/join**, nên không tuyên bố hỗ trợ di chuyển handle giữa hai cây khác nhau. Nếu mở rộng, cần nêu rõ hợp đồng sở hữu sau tách/nối.

### 9.3. Rebuild (xây lại cân bằng) bằng các nút mới

Giả sử lấy dãy inorder rồi dựng lại một cây cân bằng:

```text
Cây cũ:    các đối tượng A, B, C, D, E

Lấy khóa/giá trị:
            [(10,a), (20,b), (30,c), (40,d), (50,e)]

Cây mới:   các đối tượng A', B', C', D', E'
```

Dãy khóa và kết quả tìm có thể **giống hệt**, nhưng toàn bộ handle `A..E` không còn trỏ vào **cây mới** nếu thuật toán cấp phát lại nút. Đây là khác biệt rất quan trọng với quay tại chỗ.

Một thuật toán rebuild khác có thể **tái sử dụng đối tượng nút cũ** và chỉ nối lại các liên kết, nên giữ được một số handle. **Không suy từ tên “rebuild” rằng mọi handle đều hợp lệ hoặc đều vô hiệu**: phải xem cách cài và hợp đồng API.

### 9.4. Cây đa khóa B-tree/B+ tree

Một trang/nút B-tree chứa **nhiều khóa trong mảng**. Split/merge có thể chuyển khóa từ một trang sang trang khác hoặc dịch chuyển **vị trí chỉ số** trong mảng. Do đó:

- Tham chiếu tới **ô `page.keys[i]`** không nhất thiết ổn định khi trang split.
- Tham chiếu tới **khóa logic** có thể được duy trì bằng ID/định danh bản ghi thay vì địa chỉ ô.
- B+ tree có thể hỗ trợ duyệt lá qua **liên kết lá** hoặc cursor chuyên dụng, nhưng việc sửa trang đồng thời vẫn đòi cơ chế tương ứng.

Không áp dụng máy móc kết luận “quay nhị phân giữ node handle” cho **nút đa khóa có slot di chuyển**.

### 9.5. Cấu trúc bất biến và phiên bản bền vững (persistent)

Một cây theo phong cách **immutable/persistent** có thể tạo **nút mới dọc đường sửa** và để phiên bản cũ còn được tham chiếu. Khi đó:

- Iterator của **phiên bản cũ** có thể tiếp tục duyệt snapshot cũ, nếu các nút được giữ sống.
- Iterator của phiên bản mới sử dụng gốc mới.
- Tham chiếu nút giữa hai phiên bản có thể được **chia sẻ một phần**, không nhất thiết trùng toàn bộ.

Đây là một chiến lược thiết kế **khác** với quay tại chỗ. Không nên tự hứa mọi iterator an toàn nếu chưa có hỗ trợ phiên bản hoặc đồng bộ tương ứng.

## 10. Ví dụ Python: giữ node handle và kiểm soát iterator

Ví dụ sau cố ý xây dựng một **BST có con trỏ `parent`**, **không tự cân bằng**, để tách riêng các quy tắc **quay, duyệt, xóa và bảo toàn tham chiếu** khỏi thuật toán chọn thời điểm quay của AVL/RB/splay. Các phép quay tương tự là thành phần cấu trúc trong cả ba họ cây.

**Hợp đồng của ví dụ:**

- Khóa là **`int`**, phân biệt; `bool` không được nhận dù Python coi `True == 1`.
- `insert(key,value)` trả `(node,is_new)`; khóa cũ cập nhật giá trị và **tăng epoch**.
- `find_node(key)` trả đối tượng nút đang thuộc cây, hoặc `None` nếu không tồn tại.
- `rotate_left/rotate_right` thay đổi **liên kết**, không thay `key/value` của bất kỳ nút nào.
- `remove_node(node)` xóa **chính đối tượng được truyền vào**, dùng **physical transplant** nếu cần successor; handle của nút bị xóa không còn hợp lệ.
- Mỗi nút có `_owner` là một **token của cây**; sau xóa, token bị xóa khỏi nút. API truy cập handle kiểm tra token này.
- `items_failfast()` là iterator ngăn xếp, ghi epoch **ngay khi tạo**; quay/chèn/xóa/đổi giá trị làm nó phát sinh `RuntimeError` ở lượt `next()` kế tiếp.
- `nodes_live()` trả các đối tượng nút theo thứ tự hiện tại bằng `successor`; nó **không phải snapshot**, nhưng có thể tiếp tục sau phép quay tại chỗ khi nút hiện tại còn sống.
- `items_snapshot()` chụp **danh sách các cặp `(key,value)`** ngay tại lúc gọi. Đó là snapshot **nông**.

**Giới hạn:** Mã không phải một AVL/Red–Black hoàn chỉnh, vì chưa có thuật toán tự kiểm tra `height/color` hoặc tái cân bằng sau chèn/xóa. Nó chỉ minh họa **cơ chế giữ tham chiếu và iterator**. Không dùng mã làm bằng chứng rằng BST thường bảo đảm `h=O(log n)`.

### 10.1. Định nghĩa nút, cây và thao tác tìm/chèn

Các khối ở mục **10.1–10.5** chứa các phương thức thuộc **cùng lớp `OrderedBST`**, được trình bày tách ra để dễ giải thích. Nếu muốn chạy, hãy ghép chúng theo thứ tự vào **một tệp Python**, giữ đúng thụt lề.

```python
class Node:
    def __init__(self, key, value, owner):
        self.key = key
        self.value = value
        self.left = None
        self.right = None
        self.parent = None
        self._owner = owner


class OrderedBST:
    def __init__(self):
        self.root = None
        self.size = 0
        self._token = object()  # Định danh riêng của đúng cây này.
        self._epoch = 0

    @staticmethod
    def _check_key(key):
        if type(key) is not int:
            raise TypeError("Ví dụ chỉ dùng khóa int")

    def _require_node(self, node):
        if not isinstance(node, Node) or node._owner is not self._token:
            raise ReferenceError("Handle đã bị xóa hoặc thuộc cây khác")

    def find_node(self, key):
        self._check_key(key)
        node = self.root
        while node is not None:
            if key == node.key:
                return node
            node = node.left if key < node.key else node.right
        return None

    def insert(self, key, value):
        """Trả (node, is_new); luôn dùng đúng thứ tự BST."""
        self._check_key(key)
        parent = None
        node = self.root

        while node is not None:
            parent = node
            if key == node.key:
                node.value = value
                self._epoch += 1  # Chính sách nghiêm: cả cập nhật value.
                return node, False
            node = node.left if key < node.key else node.right

        fresh = Node(key, value, self._token)
        fresh.parent = parent
        if parent is None:
            self.root = fresh
        elif key < parent.key:
            parent.left = fresh
        else:
            parent.right = fresh

        self.size += 1
        self._epoch += 1
        return fresh, True

    def update_value(self, node, value):
        """Đổi value qua API để bộ duyệt fail-fast nhận biết."""
        self._require_node(node)
        node.value = value
        self._epoch += 1
```

**Giới hạn an toàn của ví dụ:** trường `Node.key/value/left/right/parent` vẫn **public** trong Python để mã dễ học. Nếu người dùng ngoài API tự gán `node.key` hoặc `node.parent`, họ có thể phá BST hoặc bỏ qua việc tăng `_epoch`. Một thư viện production cần **đóng gói trường**, không xuất handle có quyền sửa trực tiếp, hoặc áp quy tắc bất biến mạnh hơn.

### 10.2. Quay tại chỗ: nút vẫn là chính nó

```python
    def rotate_left(self, x):
        self._require_node(x)
        y = x.right
        if y is None:
            raise ValueError("Quay trái cần con phải")

        # Chuyển cây con giữa.
        x.right = y.left
        if y.left is not None:
            y.left.parent = x

        # Đưa y thay x ở vị trí của cha ngoài cụm.
        y.parent = x.parent
        if x.parent is None:
            self.root = y
        elif x is x.parent.left:
            x.parent.left = y
        else:
            x.parent.right = y

        y.left = x
        x.parent = y
        self._epoch += 1
        return y

    def rotate_right(self, y):
        self._require_node(y)
        x = y.left
        if x is None:
            raise ValueError("Quay phải cần con trái")

        y.left = x.right
        if x.right is not None:
            x.right.parent = y

        x.parent = y.parent
        if y.parent is None:
            self.root = x
        elif y is y.parent.left:
            y.parent.left = x
        else:
            y.parent.right = x

        x.right = y
        y.parent = x
        self._epoch += 1
        return x
```

Mỗi phép quay trả về **đối tượng nút mới ở gốc cụm**, nhưng **không tạo mới đối tượng** đó. `self.root` được cập nhật nếu phép quay diễn ra tại gốc toàn cây.

Tăng `_epoch` cho mỗi phép quay là **chính sách minh họa**: bộ duyệt strict sẽ phát hiện thay đổi cấu trúc, dù tập khóa không đổi.

### 10.3. Các phép duyệt theo nút, khóa và snapshot

```python
    def minimum_node(self, node=None):
        """Nếu không truyền node, lấy min của toàn cây."""
        if node is None:
            node = self.root
        else:
            self._require_node(node)

        while node is not None and node.left is not None:
            node = node.left
        return node

    def maximum_node(self, node=None):
        if node is None:
            node = self.root
        else:
            self._require_node(node)

        while node is not None and node.right is not None:
            node = node.right
        return node

    def successor(self, node):
        """Tìm kế tiếp từ parent hiện tại của nút còn thuộc cây."""
        self._require_node(node)
        if node.right is not None:
            current = node.right
            while current.left is not None:
                current = current.left
            return current

        current = node
        ancestor = current.parent
        while ancestor is not None and current is ancestor.right:
            current = ancestor
            ancestor = ancestor.parent
        return ancestor

    def predecessor(self, node):
        self._require_node(node)
        if node.left is not None:
            current = node.left
            while current.right is not None:
                current = current.right
            return current

        current = node
        ancestor = current.parent
        while ancestor is not None and current is ancestor.left:
            current = ancestor
            ancestor = ancestor.parent
        return ancestor

    def lower_bound_node(self, key):
        self._check_key(key)
        current = self.root
        candidate = None
        while current is not None:
            if current.key >= key:
                candidate = current
                current = current.left
            else:
                current = current.right
        return candidate

    def nodes_live(self):
        """Duyệt live: successor tính từ liên kết hiện tại.

        Nếu nút vừa yield bị xóa, lượt kế tiếp sẽ báo ReferenceError.
        """
        current = self.minimum_node()
        while current is not None:
            yield current
            current = self.successor(current)

    def range_items_live(self, low, high):
        """Trả cặp (key,value) cho khóa trong [low, high]."""
        self._check_key(low)
        self._check_key(high)
        if low > high:
            return

        node = self.lower_bound_node(low)
        while node is not None and node.key <= high:
            yield node.key, node.value
            node = self.successor(node)

    def items_snapshot(self):
        """Lập tức chụp danh sách cặp khóa/giá trị: O(n)."""
        return [
            (node.key, node.value) for node in self.nodes_live()
        ]

    def items_failfast(self):
        """Ngăn xếp inorder + so epoch trước mỗi bước.

        Quan trọng: expected được chụp NGAY KHI GỌI hàm,
        không đợi lần next đầu tiên của generator bên trong.
        """
        expected = self._epoch

        def walk():
            stack = []
            current = self.root

            while stack or current is not None:
                if self._epoch != expected:
                    raise RuntimeError("Cây đổi sau khi tạo iterator")

                while current is not None:
                    stack.append(current)
                    current = current.left

                current = stack.pop()
                yield current.key, current.value

                # Được chạy khi gọi next sau khi yield ở trên.
                if self._epoch != expected:
                    raise RuntimeError("Cây đổi khi iterator tạm dừng")
                current = current.right

        return walk()
```

**Lưu ý `minimum_node(None)` trong ví dụ:** nó được hiểu là “không truyền nút, lấy minimum của cả cây”. Vì vậy phương thức này **không dùng để hỏi minimum của một cây con rỗng riêng biệt**. Trong những bước xóa nội bộ, mã chỉ gọi minimum khi đã biết con phải tồn tại.

**Không suy thành cam kết chạy song song:** các phép `nodes_live()`/`items_failfast()` đều giả định thao tác nối con trỏ đã hoàn tất. Bộ đếm epoch chỉ **phát hiện thay đổi** trong lịch thực thi tuần tự; nó không thay thế lock khi có sửa đổi đồng thời.

### 10.4. Xóa đúng đối tượng nút bằng transplant

```python
    def _transplant(self, old, replacement):
        """Thay old ở liên kết từ cha, chưa làm mất old."""
        if old.parent is None:
            self.root = replacement
        elif old is old.parent.left:
            old.parent.left = replacement
        else:
            old.parent.right = replacement

        if replacement is not None:
            replacement.parent = old.parent

    def remove_node(self, node):
        """Xóa chính node; giữ đối tượng successor nếu có hai con."""
        self._require_node(node)
        removed_value = node.value

        if node.left is None:
            self._transplant(node, node.right)
        elif node.right is None:
            self._transplant(node, node.left)
        else:
            successor = self.minimum_node(node.right)

            if successor.parent is not node:
                # Cắt successor khỏi vị trí cũ.
                self._transplant(successor, successor.right)

                # Successor nhận cả cây phải cũ của node.
                successor.right = node.right
                successor.right.parent = successor

            # Successor thay vị trí node; nếu là con phải trực
            # tiếp của node thì successor.right đã đúng.
            self._transplant(node, successor)
            successor.left = node.left
            successor.left.parent = successor

        # Đánh dấu node bị loại, giữ mọi node khác còn sống.
        node.left = None
        node.right = None
        node.parent = None
        node._owner = None

        self.size -= 1
        self._epoch += 1
        return removed_value

    def delete_key(self, key):
        self._check_key(key)
        node = self.find_node(key)
        if node is None:
            raise KeyError(key)
        return self.remove_node(node)
```

**Hai trường hợp successor cần phân biệt:**

1. `successor.parent is node`: successor là **con phải trực tiếp**. Không cần tách từ bên trong; `successor.right` giữ nguyên. Chỉ chuyển successor lên thay nút cũ rồi gắn cây trái.
2. `successor.parent is not node`: successor nằm **sâu hơn trong cây phải**. Cần chuyển `successor.right` (nếu có) vào vị trí cũ của successor, gắn cây phải của nút bị xóa vào successor và cuối cùng đặt successor thay nút cũ.

Trong cả hai trường hợp, **nút `node` bị xóa** mới bị đánh dấu `_owner=None`. Đối tượng successor **không bị hủy** hay đổi khóa/giá trị.

Lưu ý: `remove_node` là **xóa BST cơ sở**, chưa duy trì AVL hoặc RB Tree nếu cây là một chỉ mục cân bằng; các cài đặt ấy phải gọi thêm thủ tục tái cân bằng riêng.

### 10.5. Kiểm tra bất biến độc lập

Không chỉ so dãy inorder, bởi dãy ấy có thể đúng dù `parent` sai. Validator dùng stack và cận toàn cây:

```python
    def validate(self):
        """Trả (số nút thật, chiều cao theo số nút)."""
        if self.root is None:
            assert self.size == 0
            return 0, 0

        assert self.root.parent is None
        seen = set()
        count = 0
        max_depth = 0
        stack = [(self.root, None, None, None, 1)]

        while stack:
            node, expected_parent, lower, upper, depth = stack.pop()
            marker = id(node)
            assert marker not in seen, "Chu trình hoặc nút được gắn hai lần"
            seen.add(marker)

            assert node._owner is self._token, "Nút không thuộc cây"
            assert node.parent is expected_parent, "Parent không khớp"
            assert type(node.key) is int
            if lower is not None:
                assert lower < node.key, "Vi phạm cận dưới BST"
            if upper is not None:
                assert node.key < upper, "Vi phạm cận trên BST"

            count += 1
            max_depth = max(max_depth, depth)
            if node.right is not None:
                stack.append((
                    node.right, node, node.key, upper, depth + 1
                ))
            if node.left is not None:
                stack.append((
                    node.left, node, lower, node.key, depth + 1
                ))

        assert count == self.size, "Sai kích thước cây"
        return count, max_depth
```

Trong cây có thể tạm lệch sâu, validator **không đệ quy** tránh phụ thuộc giới hạn đệ quy Python. Nó không kiểm tra màu/BF vì bài đang minh họa **BST và node handle**, không phải toàn bộ AVL/Red–Black Tree.

**Giới hạn của owner token:** Cơ chế này phù hợp khi mọi thay đổi đều đi qua API `OrderedBST` đã cung cấp. Nó không tự phát hiện mọi trường hợp đối tượng bị sửa con trỏ **trực tiếp từ bên ngoài**, cũng không hỗ trợ chuyển quyền sở hữu node giữa hai cây qua split/join khi chưa viết thêm quy tắc cập nhật owner.

## 11. Thực hành kiểm chứng: một phép quay, ba loại bộ duyệt

Các khối mã trong phần này được dùng **sau khi ghép đầy đủ lớp `OrderedBST`**. Chúng minh họa kết quả mong đợi bằng `assert`, không phải báo cáo số đo hiệu năng đã chạy trên máy.

### 11.1. Handle nút giữ nguyên, gốc thay đổi

```python
tree = OrderedBST()
h20, new20 = tree.insert(20, "v20")
h30, new30 = tree.insert(30, "v30")
h40, new40 = tree.insert(40, "v40")

assert new20 and new30 and new40
assert tree.validate() == (3, 3)
assert tree.root is h20
assert h30.parent is h20

# Chụp vai trò gốc và một liên kết cha ở thời điểm cũ.
old_root = tree.root
old_parent_of_30 = h30.parent
snapshot = tree.items_snapshot()

# Tạo hai iterator và lấy phần tử đầu.
strict = tree.items_failfast()
live = tree.nodes_live()
assert next(strict) == (20, "v20")
assert next(live) is h20

# Quay trái tại gốc, KHÔNG tạo lại nút nào.
tree.rotate_left(h20)
assert tree.validate() == (3, 2)
assert tree.root is h30
assert old_root is h20
assert old_root is not tree.root
assert old_parent_of_30 is h20    # Tham chiếu cũ vẫn là h20.
assert h30.parent is None         # Nhưng cha hiện tại đã thay đổi.
assert h20.parent is h30
assert h20.right is None
assert h30.left is h20
assert h30.right is h40

# Từng node handle vẫn có key/value và thuộc đúng cây.
assert tree.find_node(20) is h20
assert tree.find_node(30) is h30
assert tree.find_node(40) is h40

# Snapshot cặp khóa/chuỗi bất biến không đổi.
assert snapshot == [
    (20, "v20"), (30, "v30"), (40, "v40")
]

# Strict iterator phải phát hiện epoch đã đổi.
try:
    next(strict)
except RuntimeError:
    pass
else:
    raise AssertionError("Phải fail-fast sau phép quay")

# Live cursor tính successor từ liên kết MỚI của h20.
assert next(live) is h30
assert next(live) is h40
try:
    next(live)
except StopIteration:
    pass
else:
    raise AssertionError("Iterator phải hết sau khóa 40")
```

**Điều cần ghi nhớ:** `old_root` và `old_parent_of_30` là các **tham chiếu tới đối tượng** hợp lệ, nhưng tên biến mô tả **vai trò cũ**. Sau quay, không được dùng chúng để suy “nút này vẫn là gốc” hoặc “nút này vẫn là cha”.

### 11.2. Phép quay có cây con giữa không rỗng

```python
tree = OrderedBST()
for key in [40, 20, 60, 50, 70, 55]:
    tree.insert(key, f"v{key}")

assert tree.validate() == (6, 4)
root40 = tree.find_node(40)
node60 = tree.find_node(60)
node50 = tree.find_node(50)
node55 = tree.find_node(55)
before = tree.items_snapshot()

tree.rotate_left(root40)
assert tree.root is node60
assert node60.left is root40
assert root40.right is node50   # Cây con giữa B.
assert node50.parent is root40
assert node50.right is node55
assert node55.parent is node50
assert tree.items_snapshot() == before
tree.validate()

# Quay phải trở lại, nút và thứ tự vẫn không đổi.
tree.rotate_right(node60)
assert tree.root is root40
assert tree.find_node(50) is node50
assert tree.find_node(55) is node55
assert tree.items_snapshot() == before
tree.validate()
```

Kiểm tra này giúp phát hiện lỗi dễ bỏ sót: quay chỉ đúng khi `B=None` nhưng sai khi `B` có một hoặc nhiều nút.

### 11.3. Chuyển successor vật lý khi xóa nút có hai con

```python
tree = OrderedBST()
handles = {}
for key in [40, 20, 60, 50, 70]:
    handles[key], is_new = tree.insert(key, f"v{key}")
    assert is_new

assert tree.items_snapshot() == [
    (20, "v20"),
    (40, "v40"),
    (50, "v50"),
    (60, "v60"),
    (70, "v70"),
]
assert tree.root is handles[40]

deleted_handle = handles[40]
successor_handle = handles[50]

# 50 là successor của 40, nhưng nằm SÂU trong nhánh trái của 60.
assert successor_handle.parent is handles[60]
assert tree.remove_node(deleted_handle) == "v40"
assert tree.validate()[0] == 4

assert tree.root is successor_handle
assert tree.find_node(50) is successor_handle
assert successor_handle.key == 50
assert successor_handle.value == "v50"
assert tree.find_node(20) is handles[20]
assert tree.find_node(60) is handles[60]
assert tree.find_node(70) is handles[70]
assert tree.items_snapshot() == [
    (20, "v20"), (50, "v50"), (60, "v60"), (70, "v70")
]

# Node bị xóa đã được đánh dấu không còn thuộc cây.
assert deleted_handle._owner is None
assert tree.find_node(40) is None
try:
    tree.successor(deleted_handle)
except ReferenceError:
    pass
else:
    raise AssertionError("Không được dùng handle nút đã xóa")

# Chèn LẠI cùng khóa 40: đối tượng mới, không hồi sinh handle cũ.
fresh40, is_new = tree.insert(40, "reborn")
assert is_new
assert fresh40 is not deleted_handle
assert tree.find_node(40) is fresh40
assert deleted_handle._owner is None
tree.validate()
```

Với cách **sao chép khóa successor vào đối tượng cũ**, các assert về `tree.root is successor_handle` sẽ **không đúng**. Điều đó không chứng minh cách sao chép sai về mặt BST; nó chứng minh hai cách xóa có **hợp đồng danh tính đối tượng khác nhau**.

### 11.4. Successor là con phải trực tiếp

```python
tree = OrderedBST()
for key in [40, 20, 60, 70]:
    tree.insert(key, f"v{key}")

node40 = tree.find_node(40)
node60 = tree.find_node(60)
node70 = tree.find_node(70)
assert node60.parent is node40

assert tree.remove_node(node40) == "v40"
assert tree.root is node60
assert node60.left.key == 20
assert node60.right is node70
assert node70.parent is node60
assert tree.items_snapshot() == [
    (20, "v20"), (60, "v60"), (70, "v70")
]
assert tree.validate() == (3, 2)
```

Trong trường hợp này, `successor.parent is node`. Nếu mã xử lý như trường hợp successor sâu hơn mà **gán sai `successor.right`**, có thể tạo vòng tự tham chiếu hoặc mất cây con phải cũ.

### 11.5. Xóa nút hiện tại của live cursor

```python
tree = OrderedBST()
for key in [10, 20, 30]:
    tree.insert(key, f"v{key}")

live = tree.nodes_live()
first = next(live)
assert first.key == 10

tree.remove_node(first)
assert tree.items_snapshot() == [
    (20, "v20"), (30, "v30")
]

# Bước tiếp theo cần dùng successor(first), nhưng first đã bị xóa.
try:
    next(live)
except ReferenceError:
    pass
else:
    raise AssertionError("Không được tiếp tục từ handle đã xóa")
```

Nếu API muốn **xóa ngay phần tử đang duyệt**, cần cung cấp một thao tác phối hợp riêng, ví dụ lưu **successor trước khi xóa**, rồi xóa và chuyển cursor đúng cách. Ngay cả vậy, việc xóa có thể quay và thay đổi cây; phải bảo vệ tính nhất quán, đặc biệt khi đang dùng cây cân bằng có thao tác tự điều chỉnh.

### 11.6. Fail-fast bắt cả thay đổi trước lần `next()` đầu tiên

```python
tree = OrderedBST()
node10, _ = tree.insert(10, "old")
tree.insert(20, "v20")

iterator = tree.items_failfast()  # Chụp epoch tại lời gọi này.
tree.update_value(node10, "new")

try:
    next(iterator)
except RuntimeError:
    pass
else:
    raise AssertionError("Phải phát hiện update trước next đầu tiên")

assert tree.items_snapshot() == [(10, "new"), (20, "v20")]

# Một cây khác không nhận handle của cây này.
another = OrderedBST()
another.insert(10, "elsewhere")
try:
    another.successor(node10)
except ReferenceError:
    pass
else:
    raise AssertionError("Không được dùng handle của cây khác")
```

**Điểm thiết kế:** nếu `expected_epoch` được gán **bên trong thân một hàm generator** ở lần `next()` đầu tiên, nó sẽ bỏ sót thay đổi từ lúc tạo bộ duyệt đến lúc bắt đầu duyệt. Mã `items_failfast` dùng một hàm **ngoài** để lấy epoch ngay lúc tạo và một generator **trong** để duyệt.

### 11.7. Duyệt khoảng, predecessor và successor

```python
tree = OrderedBST()
for key in [40, 20, 60, 10, 30, 50, 70]:
    tree.insert(key, f"v{key}")

assert tree.lower_bound_node(25).key == 30
assert tree.lower_bound_node(70).key == 70
assert tree.lower_bound_node(71) is None
assert tree.successor(tree.find_node(30)).key == 40
assert tree.predecessor(tree.find_node(50)).key == 40
assert tree.successor(tree.find_node(70)) is None
assert tree.predecessor(tree.find_node(10)) is None

assert list(tree.range_items_live(25, 55)) == [
    (30, "v30"), (40, "v40"), (50, "v50")
]
assert list(tree.range_items_live(55, 25)) == []
assert tree.validate() == (7, 3)
```

Giá trị `(7,3)` trong ví dụ là **(bảy nút, chiều cao ba nút)**; đây là hình dạng của chính dãy chèn đã chọn, **không phải cam kết BST thường luôn cao ba mức**.

## 12. Độ phức tạp của các cách duyệt và giữ handle

Đặt:

- `n`: số nút thật.
- `h`: chiều cao cây tại thời điểm duyệt, đếm theo số nút.
- `k`: số phần tử thực sự được trả.

| Thao tác/thiết kế | Thời gian | Bộ nhớ phụ | Lưu ý |
| --- | --- | --- | --- |
| Quay trái/phải tại nút đã có | O(1) | O(1) | Không kể việc tìm nút và sửa metadata tăng cường |
| Tìm nút theo khóa | O(h) | O(1) nếu lặp | AVL/RB có `h=O(log n)` |
| `lower_bound` | O(h) | O(1) nếu lặp | Chỉ tìm một đường BST |
| Một `successor` | O(h) xấu nhất | O(1) với parent | Có thể phải leo nhiều tổ tiên |
| `k` successor liên tiếp, cây không đổi | O(h+k) gồm tìm cận đầu | O(1) handle với parent | Không tìm lại từ gốc mỗi lần |
| Iterator stack inorder, toàn cây | O(n) | O(h) | Cần cấu trúc ổn định hoặc fail-fast |
| Snapshot toàn cây | O(n) khởi tạo | O(n) | Phần tử đã chụp; giá trị có thể mutable |
| Cursor khóa gọi upper bound từng lần | O(kh) cho `k` bước | O(1) | Có thể phục hồi khi nút cũ không tồn tại |
| Xóa BST thông thường | O(h) | O(1) với parent | Không tính tái cân bằng AVL/RB |
| Validator ở mục 10 | O(n) | O(n) | Duyệt toàn cây và tập `seen` |

**Quan trọng:** phương thức `nodes_live` với một generator Python lưu vài biến trạng thái có O(1) phụ trợ, nhưng các bước successor riêng có thể O(h). Khi xét cả chuỗi liên tiếp không bị sửa, tổng có cận tốt hơn do mỗi cạnh được đi qua hữu hạn lần.

### 12.1. Metadata tăng cường có thể đổi chi phí cập nhật

Với cây AVL, nếu mỗi nút lưu `height` thì sau quay cần cập nhật chiều cao theo thứ tự đúng. Với RB Tree, phải giữ màu/black-height theo quy tắc riêng. Nếu thêm `subtree_size`, mỗi phép quay còn phải tính:

\[
\operatorname{size}(v)=1+
\operatorname{size}(v.left)+
\operatorname{size}(v.right).
\]

Trong quay trái tại `x`, đưa `y=x.right` lên:

1. Nối các con trỏ.
2. Tính lại `size(x)` vì cây con của nút đi xuống đã đổi.
3. Tính lại `size(y)` theo `size(x)` mới.

Quên metadata có thể làm `rank/select` sai dù inorder và `parent` đều đúng. Một validator đầy đủ cho AVL/RB có tăng cường phải kiểm cả **bất biến riêng của cấu trúc** và các thống kê cây con.

## 13. Hợp đồng API: vô hiệu hóa ở mức nào?

Khi thiết kế thư viện cây có thứ tự, nên xác định **rõ ràng** những điều gì còn hợp lệ sau từng loại thay đổi. Một mẫu hợp đồng cho cấu trúc **quay tại chỗ, không cấp phát lại nút**:

| Thao tác | Node handle tới nút không bị xóa | `root`/`parent` đã lưu từ trước | Iterator stack thô | Live cursor tại nút còn sống |
| --- | --- | --- | --- | --- |
| Tìm thường không quay | Giữ nguyên | Giữ nguyên | Có thể tiếp tục nếu không sửa | Có thể tiếp tục |
| Quay trái/phải | Giữ đối tượng và khóa | **Có thể cũ** | **Không được bảo đảm** | Có thể tiếp tục sau khi quay hoàn tất |
| Chèn khóa mới + cân bằng | Các nút cũ còn sống | Có thể cũ | Không được bảo đảm | Live, có thể thấy khóa mới |
| Đổi `value`, không đổi `key` | Giữ đối tượng và khóa | Không đổi nếu không quay | Phụ thuộc chính sách epoch | Live, có thể thấy value mới |
| Xóa một nút khác | Nút giữ vẫn sống nếu không bị xóa | Có thể cũ | Không được bảo đảm | Live, tập khóa đã đổi |
| Xóa chính nút đang giữ | **Không hợp lệ** | Không được dùng | Không được bảo đảm | Phải dừng/báo lỗi |
| Dựng lại bằng nút mới | Handle cũ không còn trong cây mới | Không còn đại diện cấu trúc mới | Không được bảo đảm | Không được bảo đảm |
| Split/join chuyển nút | Tùy hợp đồng owner | Thay đổi giữa các cây | Không được bảo đảm | Tùy API và owner |

Đây là **hợp đồng của một thiết kế cụ thể**, không phải một quy tắc chung cho mọi phiên bản thư viện. Một API immutable/versioned, một RB Tree của thư viện chuẩn, một cây AVL tự viết và một B+ tree lưu theo trang có thể có chính sách khác.

### 13.1. Không dùng `root` được lưu như một “địa chỉ bất biến”

```python
cached_root = tree.root
tree.rotate_left(cached_root)

# cached_root vẫn là nút cũ, nhưng vai trò root đã đổi.
assert cached_root is not tree.root
```

Nếu chương trình muốn hỏi “gốc hiện tại là gì?”, phải đọc lại **`tree.root`**. Một biến `cached_root` giữ nút cũ không tự cập nhật khi `tree.root` đổi sang đối tượng khác.

### 13.2. “Handle còn sống” không có nghĩa “handle còn thuộc đúng cây”

Nếu một thao tác **split** chuyển một nút từ cây A sang cây B, handle tới nút vẫn có thể sống trong bộ nhớ, nhưng không thể tiếp tục gọi `treeA.successor(handle)` nếu API yêu cầu handle thuộc cây A.

Có thể chọn:

- **Handle theo object identity + owner token**, cập nhật owner khi chuyển.
- **Handle theo khóa logic**, mỗi lần truy cập tìm lại nút trong đúng cây.
- **Handle gián tiếp qua bảng ánh xạ ID→node**, có thể cập nhật ánh xạ khi rebuild.
- **Handle theo phiên bản/generation**, giúp phát hiện đối tượng cũ hoặc nút đã tái sử dụng.

Lựa chọn phải đi cùng quy tắc **xóa, di chuyển, tạo lại và đồng thời**, không thể thiết kế riêng một phép quay rồi bỏ qua các thao tác khác.

### 13.3. Hiện tượng ABA khi vị trí bộ nhớ được tái sử dụng

Trong môi trường quản lý bộ nhớ thủ công hoặc hệ thống đồng thời cấp thấp, một địa chỉ có thể trải qua:

```text
Địa chỉ X chứa nút khóa 40 (đời A)
    -> xóa nút
    -> trả vùng nhớ cho allocator
    -> cấp phát nút khóa 90 (đời B) tại cùng địa chỉ X
```

So sánh riêng **địa chỉ X** không đủ chứng minh “đây vẫn là nút khóa 40 trước đó”. Những thiết kế handle an toàn có thể dùng **generation counter**, cơ chế reclamation phù hợp hoặc **định danh logic** ổn định.

Ví dụ Python của bài chỉ đánh dấu `_owner=None` trên đối tượng nút bị xóa, không mô phỏng allocator hoặc giải quyết đồng thời lock-free. Không sử dụng mã đó để chứng minh hệ thống C++ không có use-after-free/ABA.

### 13.4. Hai loại phiên bản có thể cần được tách

Trong một thư viện, có thể tồn tại:

- **Structural epoch:** tăng khi thay đổi liên kết, thêm/xóa, quay hoặc rebuild.
- **Content epoch:** tăng khi giá trị bản ghi được thay đổi dù không đổi hình dạng.

Một iterator chỉ trả **khóa** có thể không cần báo lỗi khi `value` đổi; một iterator trả **cặp khóa/giá trị** yêu cầu snapshot hoặc strict consistency có thể cần báo lỗi.

Mã `OrderedBST` chọn **một epoch duy nhất tăng với cả hai loại** để hợp đồng dễ hiểu và bảo thủ. Đây không phải lựa chọn bắt buộc cho mọi cấu trúc.

## 14. Sửa đổi đồng thời: fail-fast không phải lock

Một lỗi phổ biến là tin rằng “iterator có `epoch` nên đã an toàn để đọc và ghi từ nhiều luồng cùng lúc”. Điều này không đúng.

### 14.1. Vì sao kiểm tra epoch vẫn có race?

Xem trình tự:

```text
Luồng đọc                        Luồng ghi

kiểm tra epoch == expected
                                 bắt đầu quay cây
                                 sửa x.right, y.left, parent...
đọc x.right giữa lúc chưa xong
                                 hoàn tất quay, tăng epoch
```

Bộ duyệt đã vượt qua bước kiểm tra phiên bản **trước khi luồng ghi sửa cây**. Nó có thể nhìn thấy một trạng thái liên kết **chưa nhất quán**, ngay cả khi luồng ghi tăng epoch sau cùng.

Một con trỏ `parent` được cập nhật đúng **sau khi quay hoàn tất** không bảo đảm an toàn khi luồng khác đọc **giữa những câu lệnh cập nhật con trỏ**.

### 14.2. Các hướng thiết kế an toàn hơn

- **Khóa đọc/ghi (read–write lock):** ngăn sửa cấu trúc khi đang duyệt, hoặc bảo vệ toàn bộ thao tác theo chính sách khóa.
- **Khóa riêng cho thời gian duyệt:** một iterator giữ khóa đọc đến khi kết thúc; cần cân nhắc thời gian giữ khóa và nguy cơ deadlock.
- **Snapshot dữ liệu:** chụp dưới đồng bộ phù hợp, sau đó duyệt dữ liệu đã tách khỏi cây.
- **Cấu trúc bất biến/versioned:** bộ đọc giữ gốc của một phiên bản không thay đổi, bộ ghi tạo phiên bản mới; cần quản lý vòng đời các nút.
- **Thiết kế đồng thời chuyên dụng:** dùng quy tắc đồng bộ, publish trạng thái nhất quán và reclamation phù hợp; không tự suy từ mã BST tuần tự.

**Lưu ý về splay:** ngay cả `get` cũng có thể quay cây, nên cơ chế khóa chỉ phân biệt “đọc” và “ghi” theo tên phương thức sẽ không đủ nếu `get` thực sự sửa cấu trúc.

### 14.3. Iterator và snapshot là hai hợp đồng khác nhau

Một iterator có thể cho phép **đọc live** nhưng yêu cầu không có thay đổi đồng thời. Snapshot có thể giữ **một tập kết quả cố định** qua các cập nhật. Tuy nhiên, snapshot danh sách các **tham chiếu tới đối tượng value khả biến** chưa chắc cho một bản chụp **trạng thái sâu**.

Ví dụ:

```python
record = {"title": "Array"}
snapshot = [(10, record)]
record["title"] = "Updated Array"

# Snapshot nông vẫn giữ cùng dict.
assert snapshot[0][1]["title"] == "Updated Array"
```

Muốn snapshot không đổi nội dung bản ghi, có thể lưu **giá trị bất biến**, sao chép sâu khi phù hợp, hoặc dùng phiên bản dữ liệu bất biến. Không có giải pháp nào hoàn toàn miễn phí.

## 15. Ứng dụng vào danh mục bài học có nhiều chỉ mục

Giả sử hệ thống học tập giữ:

- `by_id`: bảng băm `lesson_id → Lesson` để tra ID.
- `by_duration`: BST có thứ tự theo `(duration_minutes, lesson_id)`.
- `prerequisites`: đồ thị thể hiện điều kiện tiên quyết giữa các bài.

Người dùng mở một trang danh sách bài, duyệt dần theo thời lượng trong khi quản trị viên chỉnh sửa danh mục.

### 15.1. Quy trình xem danh sách trong một thời điểm ổn định

Nếu người dùng yêu cầu “xuất tất cả bài có thời lượng 20–45 phút, đúng tại thời điểm bắt đầu xuất”:

1. Xác định chính xác **ranh giới snapshot** theo yêu cầu nghiệp vụ.
2. Tạo snapshot kết quả dưới cơ chế đồng bộ/phiên bản thích hợp.
3. Trả danh sách đã chụp mà không dùng con trỏ tới một cây có thể đang được quay hoặc sửa dở.

Nếu chỉ cần xem **danh sách live đang thay đổi**, có thể dùng cursor `last_key` và tìm cận lại trên cây hiện tại, nhưng phải chấp nhận rằng các mục được thêm/xóa giữa các trang có thể làm nội dung thay đổi.

### 15.2. Khi chỉnh sửa thời lượng

Ví dụ bài `ds-queue` đổi từ 30 lên 45 phút:

```text
Khóa cũ: (30, "ds-queue")
Khóa mới: (45, "ds-queue")
```

Cần xóa khóa cũ trong `by_duration` rồi chèn khóa mới, đồng thời đồng bộ `by_id` và các thông tin liên quan theo mô hình dữ liệu. Không đổi trường khóa trong nút đã nằm trong cây mà không tái chỉ mục.

Các cursor đang giữ:

- **Node handle của khóa cũ:** có thể bị vô hiệu nếu nút cũ bị xóa.
- **Cursor theo khóa cũ:** có thể tìm lại vị trí `upper_bound(last_key)` trên cây mới, nhưng phải xác định việc xuất bản ghi di chuyển vị trí có thể bị lặp hay bỏ qua.
- **Snapshot:** giữ bộ kết quả ở thời điểm đã chụp, với điều kiện nội dung bản ghi cũng được snapshot đúng mức.

### 15.3. Khi trang danh sách có phân trang

Hai chiến lược phổ biến:

1. **Offset-based:** trang số `p` sau khi tập khóa đổi có thể bị xê dịch; không đảm bảo tránh lặp/mất phần tử dưới cập nhật.
2. **Keyset-based:** trang sau tiếp tục từ khóa ghép cuối cùng đã trả, dùng `upper_bound(last_key)`. Nó có thể chịu thay đổi tập khóa tốt hơn trong nhiều trường hợp, nhưng **không tạo snapshot** và vẫn cần thứ tự khóa đủ phân biệt.

Đặc biệt khi nhiều bài cùng 30 phút, chỉ dùng `duration_minutes` để phân trang sẽ không phân biệt được chúng. Khóa ghép `(duration_minutes,lesson_id)` giúp xác định thứ tự ổn định hơn.

### 15.4. Quyết định chiến lược

| Yêu cầu sản phẩm | Hướng tiếp cận |
| --- | --- |
| Một lần xuất toàn bộ danh sách nhất quán | Snapshot/phiên bản và đồng bộ phù hợp |
| Duyệt live theo thứ tự, ít cập nhật trong phiên | Cursor nút + successor, hoặc iterator của thư viện có hợp đồng rõ |
| Cần phát hiện mọi chỉnh sửa trong lúc duyệt | Fail-fast epoch + đồng bộ khi cần |
| Có thể rebuild/chuyển nút qua các cây | Handle theo khóa/ID hoặc lớp indirection/generation |
| Muốn phân trang khi dữ liệu có thay đổi | Cursor theo khóa ghép + định nghĩa consistency |
| Tải đọc đồng thời rất cao | Cân nhắc cấu trúc không sửa cây khi tìm, snapshot/versioning |
| Có nhiều truy cập nóng và chấp nhận splay | Nhớ rằng **`get` cũng có thể làm epoch thay đổi** |

Điểm mấu chốt là **đặt hợp đồng truy cập và vòng đời tham chiếu trước khi tối ưu số phép quay**.

## 16. Những sai lầm phổ biến khi duy trì bộ duyệt và tham chiếu

### 16.1. Nhầm tham chiếu nút với tham chiếu vai trò

- **“Tôi giữ `old_root`, nên nó luôn là gốc.”** Sai: nó chỉ là đối tượng từng ở gốc; `tree.root` có thể đổi sau quay.
- **“Con trỏ `parent` đọc trước phép quay vẫn mô tả cha hiện tại.”** Sai: phải đọc lại `node.parent` từ cấu trúc mới.
- **“Sau phép quay, tất cả địa chỉ nút đều thay đổi.”** Không đúng với phép quay **tại chỗ chỉ nối lại liên kết**.
- **“Inorder giữ nguyên nên mọi iterator đang dùng vẫn hợp lệ.”** Sai: iterator stack có thể lưu đường đi cũ.
- **“Quay không thay tập khóa nên không cần tăng epoch.”** Phụ thuộc hợp đồng. Với iterator strict phải phát hiện **thay đổi hình dạng**, phép quay phải được tính là thay đổi.
- **“Iterator chỉ cần biết khóa kế tiếp, không cần kiểm liên kết.”** Phụ thuộc thiết kế; cursor theo khóa có thể tìm lại `upper_bound`, nhưng cursor theo nút phải biết nút còn sống và liên kết nhất quán.

### 16.2. Lỗi con trỏ khi quay và xóa

- **Quên cập nhật `root` khi quay ở gốc:** một phần cây có thể không truy cập được từ gốc được công bố.
- **Quên cập nhật `parent` của cây con giữa:** inorder có thể vẫn đúng nhưng `successor` leo sai tổ tiên.
- **Đặt `y` vào sai phía của cha ngoài cụm:** một vùng khóa có thể nằm sai khoảng BST.
- **Chỉ sửa một chiều của liên kết:** `parent.left` trỏ tới con mới nhưng `child.parent` còn trỏ cha cũ.
- **Không gỡ liên kết của nút bị xóa:** handle cũ có thể đi vào những nhánh không còn thuộc cây.
- **Sao chép khóa successor nhưng không thông báo thay đổi danh tính handle:** người dùng API giữ handle gắn với bản ghi có thể đọc nhầm ID.
- **Tách successor khỏi cây nhưng quên nối `successor.right` vào chỗ cũ:** làm mất cây con nếu successor có con phải.
- **Xử lý successor là con phải trực tiếp như successor ở sâu:** có thể tạo vòng self-link hoặc ghi đè con phải.
- **Dùng lại handle sau xóa/chèn cùng khóa:** khóa mới không biến handle cũ thành nút mới.
- **Quên metadata tăng cường:** quay đúng về BST nhưng `height/subtree_size` có thể sai.

### 16.3. Lỗi trong iterator và phiên bản

- **“Epoch chỉ cần kiểm tra ở lúc tạo iterator.”** Sai: phải kiểm trước mỗi bước hoặc tại những điểm đồng bộ theo hợp đồng.
- **“Chụp epoch trong thân generator tương đương chụp khi gọi hàm.”** Không trong Python: thân generator thường chạy khi gọi `next()` đầu tiên.
- **“Fail-fast epoch tự khóa cây trước race condition.”** Sai: bộ đếm không bảo đảm đọc nhất quán giữa các lệnh quay.
- **“Cursor theo nút có thể sống qua xóa chính nó.”** Không có bảo đảm nếu không có hợp đồng riêng.
- **“Cursor theo khóa tạo snapshot.”** Sai: nó có thể thấy tập khóa mới sau cập nhật.
- **“Snapshot danh sách các cặp luôn giữ nguyên trạng thái đối tượng value.”** Sai khi các value khả biến được chia sẻ.
- **“Bộ duyệt successor luôn O(1) ở mỗi lần gọi.”** Sai: một lần có thể O(h); chuỗi nhiều bước liên tiếp trên cây tĩnh có cận tổng tốt hơn.
- **“Duyệt bằng `find` từ gốc cho từng phần tử là O(log n+k).”** Sai: thường O(k log n) trên cây cân bằng, chưa kể khởi tạo.
- **“Có thể splay mỗi phần tử nhưng vẫn áp nguyên chứng minh O(h+k) của một cây không đổi.”** Không được nếu chưa phân tích thuật toán mới.

### 16.4. Lỗi về hệ thống và tính nhất quán

- **“Một node handle chỉ cần địa chỉ vật lý, không cần xác định chủ sở hữu.”** Sai nếu nút có thể được xóa, chuyển cây hoặc cấp phát lại.
- **“B+ tree split trang cũng giống quay BST nên slot tham chiếu ổn định.”** Sai: khóa có thể chuyển trang/vị trí.
- **“Cây persistent và cây sửa tại chỗ cho cùng chính sách iterator.”** Sai: persistent dùng phiên bản/nút chia sẻ, cần hợp đồng riêng.
- **“Đọc `get` luôn chỉ đọc.”** Sai trong splay tree: truy cập có thể làm thay đổi nhiều con trỏ.
- **“Phân trang theo offset không thể bị lặp khi có chèn/xóa.”** Sai: các phần tử có thể dịch vị trí.
- **“Có khóa ghép thì mọi vấn đề đồng thời được giải quyết.”** Sai: khóa ghép giúp định danh và thứ tự; vẫn cần chính sách snapshot hoặc đồng bộ.

### 16.5. Checklist trước khi công bố iterator

Hãy kiểm tra các câu hỏi:

1. Node handle là **con trỏ đối tượng**, **khóa logic**, hay **ID + generation**?
2. Phép quay có **cấp phát lại** nút hay chỉ đổi liên kết?
3. API có thể **xóa nút đang được iterator giữ** không? Khi đó báo lỗi hay tự tìm vị trí kế tiếp?
4. Khi xóa có hai con, mã **sao chép payload** hay **chuyển successor vật lý**?
5. Một phép `get` có thể **quay/splay** không?
6. Thao tác nào tăng **epoch**, và epoch được chụp ở thời điểm nào?
7. Iterator lưu **stack**, **node**, **last_key**, hay **snapshot**?
8. Có thể tiếp tục sau **split/join/rebuild** không? Owner có được cập nhật?
9. Đơn luồng hay nhiều luồng? Có **khóa/snapshot/versioning** để tránh đọc trạng thái quay dở không?
10. Validator có kiểm **BST toàn cây, `parent`, vòng/nút lặp, size và metadata** không?
11. Chi phí thực tế cần đo **duyệt k phần tử**, **tìm cận**, **số quay**, hay **thời gian xuất bản ghi**?
12. Kết quả yêu cầu là **live**, **fail-fast**, hay **snapshot nhất quán tại một thời điểm**?

## 17. Bài tập vận dụng

### Bài 1 — Node handle và gốc hiện tại

Cho gốc `20`, con phải `30`. Giữ `old_root=tree.root` rồi quay trái tại `20`. `old_root` còn là một đối tượng hợp lệ không? Có còn là `tree.root` không?

*Gợi ý:* Vẫn trỏ tới nút `20` nếu quay tại chỗ, nhưng `tree.root` mới là `30`.

### Bài 2 — Inorder không đổi, liên kết thay đổi

Cho cây `20→phải 30→phải 40`. Vẽ cây sau quay trái tại `20`. Liệt kê giá trị của `20.parent`, `20.right`, `30.parent` và `tree.root`.

*Gợi ý:* Gốc `30`; `20.parent=30`, `20.right=None`, `30.parent=None`.

### Bài 3 — Cây con giữa trong quay trái

Một nút `x=20` có con phải `y=40`; `y.left=B` chứa `25,30`. Sau quay trái, `B` chuyển thành con nào và vì sao?

*Gợi ý:* `x.right=B` vì mọi khóa của `B` nằm giữa `20` và `40`.

### Bài 4 — Quay phải có cây con giữa

Cho `y=40` có con trái `x=20`, `x.right=B` chứa `30`. Sau quay phải, nút `30` phải có cha nào?

*Gợi ý:* `B` trở thành `40.left`, nên `30.parent=40`.

### Bài 5 — Validator chỉ kiểm inorder có đủ không?

Một phép quay sửa đúng `left/right` nhưng quên `parent` của cây con giữa. Duyệt inorder có thể vẫn đúng không? Chỉ ra hai phép kiểm tra bổ sung cần có.

*Gợi ý:* Có thể vẫn đúng; kiểm `child.parent is expected_parent` và cận BST toàn cây.

### Bài 6 — Iterator stack bị bỏ sót

Iterator inorder vừa trả khóa `20` từ cây `20→phải 30→phải 40`. Một phép quay trái tại `20` xảy ra trước `next()`. Vì sao iterator thô có thể bỏ sót `30` và `40`?

*Gợi ý:* Nó có thể đọc `20.right` sau quay, lúc đó bằng `None`.

### Bài 7 — Fail-fast sau quay

Giả sử iterator lưu `expected_epoch=7`, cây có `_epoch=7`. Một phép quay làm epoch thành 8. Lần `next()` kế tiếp nên làm gì theo hợp đồng strict của bài?

*Gợi ý:* Phát sinh `RuntimeError` thay vì tiếp tục với stack cũ.

### Bài 8 — Thời điểm chụp epoch

Một generator Python chỉ gán `expected=tree.epoch` ở **dòng đầu bên trong thân generator**. Tại sao thay đổi cây sau khi tạo generator nhưng trước `next()` đầu có thể không được phát hiện?

*Gợi ý:* Thân generator chưa chạy khi đối tượng iterator vừa được tạo.

### Bài 9 — Fail-fast khác khóa đồng thời

Một luồng kiểm tra epoch rồi bị tạm dừng; luồng khác bắt đầu quay và chưa cập nhật xong các con trỏ. Luồng đầu đọc `left/right` trong lúc này. Epoch có đảm bảo nó thấy một cây nhất quán không?

*Gợi ý:* Không; kiểm tra phiên bản có thể xảy ra trước sửa đổi. Cần đồng bộ/phiên bản đúng cách.

### Bài 10 — Cursor theo nút sau quay

Một cursor vừa trả tham chiếu tới nút `20`. Cây quay trái và `20` trở thành con trái của `30`. Nếu cursor tìm successor từ `20.parent` **hiện tại**, nút nào được trả?

*Gợi ý:* `30`, nếu không có khóa nào xen giữa và liên kết đã được cập nhật hoàn chỉnh.

### Bài 11 — Một successor có thể O(h)

Vẽ hoặc mô tả một cây mà nút không có con phải phải leo qua nhiều tổ tiên trước khi gặp một tổ tiên lớn hơn. Vì sao một lần `successor` có thể tốn O(h)?

*Gợi ý:* Đi lên từ một chuỗi con phải đến tổ tiên đầu tiên mà đường đi vừa bước lên từ con trái.

### Bài 12 — Duyệt `k` phần tử liên tiếp

Vì sao duyệt các successor liên tiếp từ `lower_bound` trên **cây không đổi** có tổng thời gian O(h+k), dù một bước successor riêng có thể O(h)?

*Gợi ý:* Trong toàn bộ hành trình inorder, các cạnh trên đoạn đã duyệt chỉ bị đi lên/xuống một số lần bị chặn.

### Bài 13 — Kết quả khoảng

Cho khóa `10,20,30,40,50,60,70`. Truy vấn `range_items_live(25,55)` cần trả những khóa nào? Nếu cây cân bằng có `n` phần tử, cận thời gian là gì với `k` kết quả?

*Gợi ý:* `30,40,50`; O(log n + k) khi dùng cận dưới và duyệt successor đúng cách.

### Bài 14 — Cursor theo khóa so với cursor theo nút

Giải thích vì sao một cursor lưu `last_key=30` và gọi `upper_bound(30)` trên cây hiện tại có thể phục hồi sau rebuild bằng **nút mới**, trong khi cursor lưu node handle cũ không thể.

*Gợi ý:* Khóa logic còn dùng được để tìm vị trí; đối tượng nút cũ không còn nằm trong cây mới.

### Bài 15 — Snapshot nông

Một snapshot lưu cặp `(10, record_dict)`, sau đó bên ngoài sửa `record_dict["title"]`. Giá trị trong snapshot có thể thay đổi không?

*Gợi ý:* Có, nếu snapshot chỉ sao chép tham chiếu đến dict. Cần giá trị bất biến hoặc copy phù hợp nếu muốn snapshot sâu.

### Bài 16 — Xóa bằng sao chép khóa

Trong cây gốc `40` có successor `50`, một cài đặt sao chép `key/value` từ `50` sang đối tượng vốn chứa `40` rồi xóa đối tượng `50`. Hai handle bên ngoài từng trỏ tới hai nút này có ý nghĩa gì sau thao tác?

*Gợi ý:* Handle của `40` giờ có thể mang dữ liệu `50`; handle `50` cũ đã bị tách. Cây có thể đúng BST nhưng hợp đồng định danh thay đổi.

### Bài 17 — Xóa bằng chuyển nút vật lý

Với cây gốc `40`, phải `60` và `60.left=50`, hãy thực hiện transplant khi xóa `40`. Đối tượng nào là gốc mới? Handle của nút `50` có còn đúng đối tượng không?

*Gợi ý:* Chính đối tượng `50` được đưa lên thay `40`, handle của `50` không đổi; handle `40` hết hiệu lực.

### Bài 18 — Successor là con trực tiếp

Cho `40.right=60`, `60.right=70` và `60.left=None`. Khi xóa `40` theo transplant, vì sao không được gắn `60.right` trở lại thành `40.right` như thể successor ở sâu?

*Gợi ý:* `60` chính là con phải trực tiếp; phải giữ cây `70` và tránh vòng tự tham chiếu.

### Bài 19 — Node đã xóa không sống lại

Giữ handle của nút khóa `40`, xóa nút ấy rồi chèn lại khóa `40`. Có thể dùng lại handle cũ vì khóa giống nhau không?

*Gợi ý:* Không. Đối tượng mới có cùng khóa nhưng khác danh tính và vòng đời.

### Bài 20 — Chuyển owner giữa hai cây

Một thao tác split chuyển nút có khóa `30` từ cây A sang cây B mà không tạo nút mới. Điều gì có thể đúng với **object identity** nhưng không còn đúng với `treeA.successor(handle)`?

*Gợi ý:* Đối tượng nút vẫn sống, nhưng không còn thuộc cây A; cần cập nhật hoặc kiểm tra owner.

### Bài 21 — Rebuild với nút mới

Một thuật toán xuất inorder rồi dựng lại cây cân bằng bằng cách cấp phát **tất cả nút mới**. Những gì được giữ: tập khóa, thứ tự hay địa chỉ đối tượng nút?

*Gợi ý:* Có thể giữ tập khóa và inorder, nhưng không giữ identity của nút cũ.

### Bài 22 — Slot trong B-tree

Một con trỏ logic tới `page.keys[3]` trỏ vào slot của một trang B-tree. Khi trang split và khóa bị chuyển sang trang khác, có thể mặc định con trỏ slot cũ vẫn chỉ đúng khóa không?

*Gợi ý:* Không. Cần handle/ID của bản ghi hoặc cơ chế cursor của B-tree có hợp đồng rõ.

### Bài 23 — Splay thay đổi cây khi đọc

Tại sao một iterator stack đang duyệt có thể bị ảnh hưởng bởi `get(k)` của một splay tree, ngay cả khi `get` không chèn/xóa phần tử?

*Gợi ý:* `get` có thể quay và làm đường đi được iterator lưu trở nên cũ.

### Bài 24 — Hai lớp phiên bản

Trong một Map, cập nhật `value` mà không đổi khóa có nên làm iterator chỉ trả `key` bị fail-fast không? Có câu trả lời duy nhất cho mọi thư viện không?

*Gợi ý:* Phụ thuộc hợp đồng. Có thể tách structural epoch và content epoch.

### Bài 25 — Phân trang theo khóa ghép

Danh mục có hai bài cùng 30 phút: `(30,"ds-stack")` và `(30,"ds-queue")`. Tại sao dùng **chỉ phút** làm `last_key` dễ làm mất kết quả trang sau? Đề xuất cách đặt khóa duy nhất.

*Gợi ý:* Dùng khóa ghép `(duration_minutes,lesson_id)` và `upper_bound` theo thứ tự ghép.

### Bài 26 — Duyệt live hay snapshot?

Một ứng dụng cần xuất báo cáo sao cho kết quả không đổi dù quản trị viên thêm/xóa bài trong lúc xuất. Chọn `nodes_live`, fail-fast, cursor theo khóa hay snapshot/versioning? Giải thích đánh đổi.

*Gợi ý:* Snapshot/phiên bản nhất quán phù hợp hơn; cần chi phí bộ nhớ hoặc quản lý phiên bản.

### Bài 27 — Validator độc lập

Ngoài kiểm tra dãy khóa inorder tăng, hãy liệt kê ít nhất **năm điều** cần kiểm tra để xác nhận một cây sau nhiều phép quay và xóa vẫn đúng cấu trúc.

*Gợi ý:* Cận BST toàn cây, `root.parent=None`, parent khớp, không chu trình, không nút lặp, size, owner, metadata tăng cường.

### Bài 28 — Chọn chiến lược cho hệ thống nhiều người dùng

Một dịch vụ có nhiều yêu cầu đọc đồng thời, cập nhật thường xuyên, cần duyệt khoảng và có một số khóa nóng. Bạn sẽ đặt câu hỏi nào trước khi chọn AVL, RB, splay hoặc snapshot?

*Gợi ý:* Yêu cầu worst-case latency, sửa cấu trúc khi get, tính cục bộ, iterator stability, snapshot consistency, khóa/đồng bộ và chi phí bộ nhớ.

## 18. Tổng kết

Trong **cây tìm kiếm cân bằng**, một phép quay **tại chỗ** giữ nguyên đối tượng nút, khóa/giá trị và dãy inorder, nhưng làm thay đổi **`root`, `parent`, `left` và `right`**. Vì vậy, tham chiếu tới **nút** có thể vẫn hợp lệ trong khi tham chiếu tới **vai trò cũ** hoặc trạng thái **ngăn xếp bộ duyệt** đã lỗi thời. Cây vẫn là BST đúng nhưng iterator đang chạy vẫn có thể **bỏ qua, lặp hoặc trả sai phần tử** nếu nó tiếp tục với cấu trúc cũ.

Không có một chính sách iterator áp dụng cho mọi thuật toán và thư viện. **Fail-fast** phát hiện thay đổi theo epoch nhưng không thay thế đồng bộ; **live cursor + successor** có thể theo liên kết mới nếu nút vẫn sống và cây đã được sửa hoàn chỉnh; **cursor theo khóa** có thể tìm lại sau rebuild nhưng phải trả chi phí tìm cận; **snapshot** giữ kết quả đã chụp với chi phí thời gian/bộ nhớ và mức sao chép rõ ràng.

Đặc biệt khi **xóa nút có hai con**, cách **sao chép successor vào nút cũ** và cách **chuyển đối tượng successor vật lý** có thể tạo ra cùng dãy khóa nhưng **khác hợp đồng node handle**. Các thao tác split/join, rebuild, splay hoặc B-tree split còn đưa ra những mô hình vô hiệu hóa khác nhau. Một hệ thống vững chắc cần xác định **identity, owner, vòng đời, epoch, iterator và tính nhất quán đồng thời** cùng với bất biến BST.

Cuối cùng, để duyệt `k` phần tử trong một khoảng, tìm cận dưới rồi đi successor trên cấu trúc ổn định cho **O(h+k)**, và cho **O(log n+k)** trên cây AVL/Red–Black có `h=O(log n)`. Nhưng **độ phức tạp tốt không cứu được một iterator sai hợp đồng**: hãy kiểm chứng đồng thời **thứ tự, liên kết, kích thước, danh tính nút và trạng thái bộ duyệt** sau những phép quay hoặc tổ chức lại cây.

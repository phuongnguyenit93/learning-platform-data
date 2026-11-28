# Sao chép đường đi trong cây khi cập nhật một khóa

## 1. Bài toán: cập nhật dữ liệu mà vẫn giữ được trạng thái trước đó

Trong học phần **Cấu trúc dữ liệu**, cây tìm kiếm nhị phân (Binary Search Tree – BST) thường được sử dụng để lưu tập khóa có thứ tự. Một phiên bản **khả biến** (*mutable*) có thể cập nhật cây bằng cách thay đổi trực tiếp liên kết hoặc giá trị của các nút.

Ví dụ một ứng dụng lưu trọng số theo khóa:

```text
Khóa:       10   20   30   40   50   60   70
Trọng số:    1    2    3    4    5    6    7
```

Nếu người dùng sửa trọng số của khóa `30` từ `3` thành `300`, cấu trúc khả biến có thể tìm nút có khóa `30` rồi gán:

```python
node.value = 300
```

Cách này phù hợp khi ứng dụng chỉ cần **một trạng thái hiện hành**. Nhưng nó có vấn đề nếu hệ thống muốn:

- Truy vấn bản dữ liệu **trước khi cập nhật**.
- Tạo **undo/redo** mà không sao chép cả tập dữ liệu sau mỗi thao tác.
- Cho hai nhánh phiên bản cùng phát triển từ một trạng thái gốc.
- Đọc một trạng thái ổn định trong lúc một phiên bản khác đang được tạo.
- So sánh dữ liệu giữa các thời điểm.
- Giữ snapshot đã phát hành cho một báo cáo hoặc thuật toán phân tích.

Để thực hiện, ta cần một cách cập nhật sao cho **cây cũ không bị sửa**, nhưng cũng không muốn **sao chép toàn bộ `n` nút** chỉ vì một giá trị thay đổi.

Kỹ thuật **sao chép đường đi (*path copying*)** tạo **nút mới chỉ trên đường đi từ gốc tới vị trí cần cập nhật**, rồi **chia sẻ các cây con không thay đổi**. Kết quả là một **gốc mới** đại diện cho phiên bản mới, còn gốc cũ tiếp tục đại diện cho phiên bản cũ.

> Ý tưởng quan trọng: **một phiên bản là một tham chiếu tới gốc của một cây bất biến**. Khi cập nhật, không thay đổi bất kỳ nút nào đã thuộc phiên bản cũ; tạo đường nút mới cần thiết và nối tới các cây con cũ còn nguyên.

Bài này phân tích bất biến, thuật toán cập nhật một khóa, cách hỗ trợ chèn/xóa, các phép xoay AVL và metadata cây con, chi phí thời gian–bộ nhớ, cài đặt Python bằng nút bất biến, kiểm tra phiên bản cũ và các giới hạn thực tế.

## 2. Phân biệt sao chép toàn cây, sao chép nông và sao chép đường đi

### 2.1. Sao chép toàn bộ cây sau mỗi cập nhật

Một lựa chọn đơn giản để giữ bản cũ là:

1. Duyệt và tạo bản sao của **mọi nút**.
2. Áp dụng thay đổi vào cây mới.
3. Giữ cả gốc cũ và gốc mới.

Với cây có `n` nút, một lần sao chép đầy đủ có chi phí:

\[
T_{\text{copy}}=\Theta(n),\qquad
S_{\text{new}}=\Theta(n).
\]

Nếu có nhiều bản cập nhật rất nhỏ, cách này tốn nhiều bộ nhớ và thời gian dù phần lớn cây không thay đổi.

### 2.2. Sao chép nông chỉ gốc rồi sửa con

Một cách **sai** thường gặp:

```python
new_root = copy.copy(old_root)
new_root.left.right.value = 300
```

Dù gốc mới là một đối tượng khác, `new_root.left` có thể vẫn **trỏ tới cùng một nút** mà `old_root.left` dùng. Gán vào nút dùng chung sẽ làm thay đổi **cả hai phiên bản**.

**Sao chép nông (shallow copy) không đồng nghĩa persistence** nếu các nút con vẫn có thể bị sửa tại chỗ.

### 2.3. Sao chép đường đi

Với thao tác sửa **một khóa** trong BST:

- Từ gốc, tìm đường tới khóa theo thứ tự BST.
- Tạo nút mới đại diện cho nút bị thay đổi.
- Khi quay ngược lên, tạo nút mới cho mỗi tổ tiên, trỏ tới **nhánh mới đã dựng** và **nhánh đối diện cũ**.
- Trả gốc mới.
- Không ghi đè nút nào của cây cũ.

Nếu chiều cao của cây là `h` theo số cạnh, đường tìm kiếm gồm tối đa `h+1` nút. Trong BST không cần tái cân bằng, cập nhật một giá trị đã tồn tại tạo **`O(h+1)` nút mới** thay vì `O(n)`.

### 2.4. Bảng so sánh

| Cách cập nhật | Trạng thái cũ còn nguyên? | Số nút mới cho sửa một khóa | Lưu ý |
|---|---|---|---|
| Ghi trực tiếp vào nút | Không | `O(1)` | Nhanh, chỉ một bản hiện hành |
| Sao chép toàn cây | Có | `\Theta(n)` | Đơn giản nhưng tốn tài nguyên |
| Sao chép nông gốc rồi sửa con | **Không bảo đảm** | Một hoặc vài nút | Vẫn có tham chiếu tới con khả biến |
| **Path copying trên cây bất biến** | **Có** | `O(h+1)` | Chia sẻ cây con không đổi |
| Persistent balanced BST/AVL | Có | `O(\log(n+1))` với trường hợp AVL | Tính thêm chi phí tái cân bằng |

**Lưu ý:** “sao chép đường đi” là một **kỹ thuật biến đổi cấu trúc**, không tự động bảo đảm cây cân bằng hay truy vấn nhanh. Chi phí vẫn phụ thuộc **chiều cao** và cách cập nhật.

## 3. Persistence là gì? Phải hiểu đúng phạm vi

### 3.1. Cấu trúc dữ liệu bất biến

Một nút **bất biến** (*immutable*) là nút không bị thay đổi dữ liệu hoặc liên kết sau khi được tạo hoàn chỉnh.

Ví dụ về ngữ nghĩa:

```text
Node(key, value, left, right)
```

Khi muốn sửa `value`, thay vì gán trường vào nút, ta tạo một **Node mới** giữ khóa và các con thích hợp.

Nếu tất cả nút có thể được chia sẻ đều bất biến, một nhánh của phiên bản mới có thể **trỏ trực tiếp tới cây con của phiên bản cũ** mà không sợ bị đổi sau đó.

### 3.2. Cấu trúc dữ liệu persistent

Một cấu trúc **persistent** giữ các phiên bản trước có thể truy cập được sau các lần cập nhật.

Ví dụ:

```text
V0 --update(30,300)--> V1
 |
 +--insert(25,25)---> V2
```

Cả `V1` và `V2` đều xuất phát từ `V0`. Mỗi phiên bản có một tham chiếu gốc riêng; những cây con không thay đổi có thể được **chia sẻ**.

### 3.3. Phân biệt các mô hình phiên bản

| Mô hình | Có thể đọc phiên bản cũ? | Có thể cập nhật từ phiên bản cũ? |
|---|---|---|
| Ephemeral (chỉ hiện hành) | Thường không | Không áp dụng |
| Partially persistent | Có | Thường chỉ cập nhật phiên bản mới nhất |
| Fully persistent | Có | Có, có thể rẽ nhánh từ bất kỳ phiên bản |
| Confluently persistent | Có | Có thể kết hợp dữ liệu từ các phiên bản khác nhau theo mô hình đã định |

Nếu API nhận **gốc phiên bản bất kỳ** rồi trả một gốc mới, mô hình phù hợp là **fully persistent theo thao tác đã hỗ trợ**, vì có thể rẽ nhánh lịch sử.

**Không được đồng nhất** khả năng đọc nhiều phiên bản với hệ thống lưu phiên bản trên đĩa, khả năng chống mất điện, hay giao dịch cơ sở dữ liệu. Đó là các yêu cầu khác.

### 3.4. “Phiên bản” không có nghĩa là sao chép giá trị dữ liệu tùy ý

Nếu trong nút lưu một **đối tượng khả biến** như `list`, `dict` hay một instance có trường thay đổi được, việc giữ nguyên tham chiếu đến đối tượng ấy vẫn có thể làm thay đổi dữ liệu quan sát trong nhiều phiên bản.

Ví dụ nguy hiểm:

```python
# Ý tưởng minh họa lỗi, không phải mã persistent đúng.
payload = [1, 2]
old = Node(key=10, value=payload, left=None, right=None)

# Phiên bản mới sao chép đường đi nhưng cùng dùng payload.
payload.append(3)

# Cả hai phiên bản có thể thấy [1,2,3].
```

Vì vậy, để có bất biến **theo ngữ nghĩa**, dữ liệu được chia sẻ phải:

- Là giá trị bất biến, chẳng hạn số nguyên hoặc chuỗi bất biến.
- Hoặc được sao chép/đóng băng thích hợp khi đưa vào phiên bản.
- Hoặc có hợp đồng ownership nghiêm ngặt: không ai được sửa đối tượng đã chia sẻ.

Trong cài đặt Python ở bài này, **khóa và trọng số đều là `int`**, nút là `@dataclass(frozen=True)`, và các liên kết con chỉ trỏ tới những nút tương tự. Điều đó giúp tránh lỗi tham chiếu tới payload khả biến.

## 4. Ví dụ hình học: đường đi mới, cây con cũ

### 4.1. Phiên bản `V0`

Giả sử một BST cân bằng lưu các khóa:

```text
                         40
                       /    \
                     20      60
                    /  \    /  \
                  10   30  50   70
```

Kèm trọng số tại từng khóa:

```text
(10:1), (20:2), (30:3), (40:4), (50:5), (60:6), (70:7)
```

Giờ cần đổi **trọng số tại khóa `30` từ `3` thành `300`**.

Đường BST từ gốc tới nút cần sửa là:

```text
40 → 20 → 30
```

Những cây con **không nằm trên đường này** không cần thay đổi.

### 4.2. Các đối tượng mới được tạo

Bắt đầu từ nút bị thay đổi:

1. Tạo `30'` với khóa `30`, trọng số `300` và các con như cũ.
2. Tạo `20'` với `left=10` **dùng chung** và `right=30'`.
3. Tạo `40'` với `left=20'` và `right=60` **dùng chung**, trong đó nguyên cây con dưới `60` được tái sử dụng.

Sơ đồ:

```text
Phiên bản cũ V0:                    Phiên bản mới V1:

          40 (cũ)                          40'
         /       \                        /    \
       20 (cũ)    60 ───────────────┐    20'    │
      /     \     / \               │   /   \   │
    10       30 50  70              ├──10   30' 60
      ╲         [các nút dùng chung] │      (300) / \
       └─────────────────────────────┘           50  70

Nút mới: 30', 20', 40'
Nút cũ được dùng chung: 10 và toàn bộ cây con gốc 60
```

Để tránh hiểu nhầm sơ đồ: **`V0` vẫn trỏ tới nút `30` có trọng số `3`**; `V1` trỏ tới nút `30'` có trọng số `300`. Nút `10` và gốc cây con `60` là **chính các đối tượng cũ**, không phải bản sao.

Sơ đồ tham chiếu tối giản:

```text
root(V0) = 40 ──left──> 20 ──right──> 30(value=3)
              └─right──> 60 ──> {50,70}

root(V1) = 40'──left──> 20'──right──> 30'(value=300)
               └─right──> 60 ──> {50,70}  [SHARED]
                          20'.left──>10  [SHARED]
```

### 4.3. Điều gì đã được tiết kiệm?

- Sao chép toàn cây: cần tạo **7 nút mới**.
- Sao chép đường đi trong BST không xoay: tạo **3 nút mới**.
- Các nút `10,50,60,70` được **dùng chung** giữa hai phiên bản.

Với cây lớn cân bằng có `n` nút, số nút trên đường tìm kiếm thường tỷ lệ `\log n`, nên lượng sao chép nhỏ hơn rất nhiều so với `n`.

### 4.4. Có phải mọi cập nhật đều tạo đúng một nút mới mỗi tầng?

**Không.** Thay trọng số một nút đã tồn tại trong BST đơn giản thường tạo một bản sao mỗi tầng đường tìm kiếm.

Nhưng khi có **xoay AVL hoặc Red–Black Tree**, có thể cần tạo **một số hằng nút bổ sung** để biểu diễn các liên kết đã xoay mà không sửa nút cũ.

Kết luận tổng quát cho triển khai persistent AVL đúng là **`O(h+1)` nút mới**, không nhất thiết bằng **đúng `h+1`** nút.

## 5. Ba bất biến đồng thời phải giữ

Sao chép đường đi chỉ đúng khi giữ ít nhất ba nhóm bất biến.

### 5.1. Bất biến thứ tự của BST

Với khóa phân biệt và nút `u`:

\[
\forall k\in left(u): k<key(u)
\]

và:

\[
\forall k\in right(u): k>key(u).
\]

Đối với truy vấn một khóa `x`:

- Nếu `x<key(u)`, chỉ cần xuống trái.
- Nếu `x>key(u)`, chỉ cần xuống phải.
- Nếu bằng, tìm thấy bản ghi cần sửa.

Khi chỉ thay **trọng số `value`** mà không thay `key`, thứ tự BST không đổi. Khi chèn/xóa khóa, thuật toán phải bảo toàn thứ tự.

### 5.2. Bất biến không sửa nút đã công bố

Sau khi một phiên bản đã lưu gốc:

```text
versions[v] = root_v
```

mọi nút có thể truy cập từ `root_v` đều phải **không bị sửa tại chỗ** nếu muốn bảo đảm phiên bản `v` tiếp tục trả cùng dữ liệu.

Hệ quả:

- Không gán `old_node.left = new_child`.
- Không gán `old_node.value = new_value`.
- Không xoay bằng cách thay `left/right` của những nút cũ.
- Không cập nhật metadata `size/height/sum` trên những nút đang được chia sẻ.
- Không truyền một tham chiếu tới đối tượng payload khả biến cho mã ngoài rồi để mã ấy sửa.

### 5.3. Bất biến gốc phiên bản

Mỗi phiên bản có **một gốc**:

```text
version 0 -> root0
version 1 -> root1
version 2 -> root2
```

Gốc mới là kết quả trả về của hàm cập nhật thuần:

\[
root'=update(root,key,value).
\]

Hàm cập nhật **không làm thay đổi `root`**.

Chỉ thêm `root'` vào bộ quản lý phiên bản; các gốc cũ vẫn còn cho tới khi chính sách lưu phiên bản cho phép bỏ chúng.

### 5.4. Nếu có metadata cây con

Khi nút lưu thêm:

\[
size(u)=1+size(left)+size(right)
\]

hoặc:

\[
sum(u)=value(u)+sum(left)+sum(right),
\]

các giá trị phải đúng **trên mỗi nút mới**. Không thể cập nhật một trường của nút cũ rồi xem nó là “cache” dùng chung.

Cách an toàn: **tạo nút bất biến qua một hàm `make_node` tính lại tất cả metadata từ hai con**.

### 5.5. Nếu có bất biến cân bằng

Với AVL:

\[
|height(left)-height(right)|\le 1
\]

tại mọi nút. Sau chèn/xóa, thuật toán có thể cần xoay. Mọi phép xoay trong persistent AVL phải được **xây bằng các nút mới**, không dùng các phép gán con trỏ tại chỗ của AVL khả biến.

## 6. Cập nhật trọng số của một khóa đã tồn tại

### 6.1. Mục tiêu và hợp đồng

Giả sử cây lưu ánh xạ:

```text
key -> value
```

Ta muốn:

```text
new_root = set(root, x, new_value)
```

Hợp đồng:

- Mỗi khóa chỉ xuất hiện một lần.
- Nếu `x` tồn tại, chỉ thay `value` tương ứng trong phiên bản mới.
- Nếu `x` chưa tồn tại, có thể **chèn một khóa mới** (hợp đồng `put/upsert`), hoặc báo lỗi tùy API.
- Gốc `root` cũ và mọi nút reachable từ nó giữ nguyên.
- Gốc `new_root` biểu diễn ánh xạ sau cập nhật.

Trong mã hoàn chỉnh ở phần sau, `put` chọn ngữ nghĩa **upsert**: chèn khóa chưa có, thay giá trị khóa đã có.

### 6.2. Mã giả thuần cho thay giá trị của khóa đã tồn tại

```text
REPLACE_VALUE(u, key, new_value):
    require key tồn tại trong cây u

    if key == u.key:
        return NEW_NODE(
            key=u.key,
            value=new_value,
            left=u.left,           # CHIA SẺ
            right=u.right          # CHIA SẺ
        )

    if key < u.key:
        changed_left = REPLACE_VALUE(u.left, key, new_value)
        return NEW_NODE(
            key=u.key,
            value=u.value,
            left=changed_left,     # nhánh MỚI
            right=u.right          # nhánh CŨ dùng chung
        )

    changed_right = REPLACE_VALUE(u.right, key, new_value)
    return NEW_NODE(
        key=u.key,
        value=u.value,
        left=u.left,               # nhánh CŨ dùng chung
        right=changed_right        # nhánh MỚI
    )
```

Hàm `NEW_NODE` tạo đối tượng mới, không ghi vào `u`. Nếu có metadata, nó đồng thời tính lại từ hai cây con đã đúng.

### 6.3. Ví dụ chi tiết cho một đường dài ba nút

Ở cây mục 4, cập nhật khóa `30`:

```text
REPLACE_VALUE(40, 30, 300)
  vì 30 < 40 → gọi REPLACE_VALUE(20,...)
    vì 30 > 20 → gọi REPLACE_VALUE(30,...)
      bằng khóa → tạo nút 30'
    quay lại 20 → tạo nút 20' với right=30'
  quay lại 40 → tạo nút 40' với left=20'
return 40'
```

Đường đi:

```text
40  → 20  → 30
40' ← 20' ← 30'
```

Ở mỗi tầng:

- Chỉ **một nhánh** chứa đường cần sửa.
- Nhánh còn lại **không thay đổi** và được chia sẻ.
- Khi có metadata như tổng, nút mới tính lại trường của nó dựa trên nhánh mới và nhánh cũ.

### 6.4. Trường hợp không đổi giá trị

Nếu giá trị mới bằng giá trị cũ, có thể trả **chính đối tượng nút cũ**:

```python
if new_value == node.value:
    return node
```

Khi lan lên, nếu cây con trả về **cùng đối tượng**, tổ tiên cũng có thể trả lại nguyên nút cũ mà không cấp phát:

```python
new_left = replace(node.left, key, new_value)
if new_left is node.left:
    return node
```

Điều này tạo một **no-op update**: phiên bản mới có thể lưu **chính cùng gốc** với phiên bản cũ, vì về mặt nội dung chúng giống hệt nhau.

**Phải dùng so sánh định danh đối tượng `is` cho kiểm tra nhánh có được thay thế hay không**, không nhầm với phép so sánh giá trị khóa.

### 6.5. Chi phí

Nếu cây có chiều cao `h`:

- Tìm khóa: `O(h+1)`.
- Tạo tối đa một nút trên mỗi tầng cho cập nhật giá trị đơn giản: `O(h+1)` nút mới.
- Bộ nhớ stack đệ quy: `O(h+1)`.
- Các cây con ngoài đường đi: **không được sao chép**.

Nếu cây là AVL cân bằng: `h=O(\log(n+1))`. Nếu BST không cân bằng suy biến thành đường dài: `h=\Theta(n)`.

## 7. Chèn một khóa mới cũng là sao chép đường đi

### 7.1. Cơ sở của đệ quy thay đổi

Nếu đang tìm khóa `x` mà gặp cây rỗng:

```text
INSERT(None, x, value)
    → new_leaf(x, value)
```

Đây là **một nút mới**, không có phiên bản cũ của nút ấy.

Ở mỗi tổ tiên trên đường đi, tạo bản sao bất biến trỏ tới nhánh đã chèn và chia sẻ nhánh còn lại.

### 7.2. Ví dụ chèn khóa `25`

Từ cây phiên bản gốc:

```text
                         40
                       /    \
                     20      60
                    /  \    /  \
                  10   30  50   70
```

Tìm vị trí `25`:

```text
25 < 40 → trái
25 > 20 → phải
25 < 30 → trái
gặp None → tạo 25
```

Cây phiên bản mới có cùng inorder tăng dần, thêm khóa `25`:

```text
                         40'
                       /     \
                     20'      60 [dùng chung]
                    /   \     / \
        [dùng chung]10   30' 50 70
                        /
                      25 [mới]
```

Trong ví dụ này, cây vẫn cân bằng AVL nên không cần xoay. Các nút mới gồm:

```text
25, 30', 20', 40'
```

Cây con gốc `60` và nút `10` không thay đổi và được chia sẻ.

### 7.3. Khi chèn làm cây mất cân bằng

Ở cây AVL, chèn vào một nhánh có thể làm chênh lệch chiều cao tại tổ tiên vượt `1`. Thuật toán phải:

1. Sao chép đường đi như trên.
2. Tính lại chiều cao/metadata của các nút mới.
3. Thực hiện phép xoay **thuần**, xây các nút mới nếu cần.
4. Trả gốc mới của cây con sau xoay.

Các nút cũ trên mọi phiên bản cũ **không được sửa**.

**Không đủ** chỉ sao chép đường đi rồi gọi một hàm `rotate_left` khả biến đã viết cho cây thường: hàm ấy có thể sửa liên kết của nút đang được chia sẻ.

## 8. Xóa một khóa: ba tình huống cần xét riêng

Xóa khóa có thể phức tạp hơn thay trọng số vì cấu trúc cây thay đổi.

### 8.1. Khóa không có trong cây

Nếu tìm tới `None` mà chưa gặp khóa cần xóa:

```text
DELETE(None, x) → None
```

Ta có thể truyền kết quả **không thay đổi** ngược lên mà **không tạo bất kỳ nút mới nào**.

Trong Python, một cách là kiểm tra:

```python
new_left = delete(old_left, x)
if new_left is old_left:
    return old_node
```

Vì hàm xóa có hợp đồng thuần và mỗi thay đổi thật đều dẫn tới một gốc cây con khác (trừ `None` trong những trường hợp được nhận diện riêng), kiểm tra định danh giúp tránh sao chép khi xóa khóa không tồn tại.

### 8.2. Nút cần xóa có không quá một con

Trường hợp nút là lá:

```text
     20
    /
  10

Xóa 10 → trả None cho vị trí cũ của 10
```

Trường hợp chỉ có một con:

```text
     20
    /
  10
    \
    15

Xóa 10 → cây con thay thế là nút 15 CŨ
```

Nếu `10` không có con trái, trả **con phải**; nếu không có con phải, trả **con trái**. Con duy nhất và toàn bộ cây bên dưới nó có thể được **dùng chung** vì nút ấy không bị sửa.

Những tổ tiên trên đường về gốc được **dựng lại**, để cập nhật liên kết và metadata theo phiên bản mới.

### 8.3. Nút cần xóa có hai con

Với BST, có thể thay bằng:

- **Kế nhiệm inorder**: khóa nhỏ nhất ở cây con phải; hoặc
- **Tiền nhiệm inorder**: khóa lớn nhất ở cây con trái.

Ví dụ:

```text
             40
            /  \
          20    60
               /  \
              50   70
```

Xóa khóa `40`:

1. Chọn kế nhiệm `50` (khóa nhỏ nhất ở cây phải).
2. Tạo cây con phải mới là kết quả **xóa `50` ra khỏi cây phải**.
3. Tạo nút mới mang **cả khóa và trọng số** của `50`, nối cây trái cũ và cây phải mới.
4. Tái cân bằng thuần nếu cần.

Một hình dạng trước/sau hợp lệ:

```text
Trước:                       Sau:

       40                          50'
      /  \                        /   \
    20    60                    20     60'
         /  \                            \
       50    70                           70
```

Chú ý:

- Nút `50` cũ vẫn phải tồn tại trong **phiên bản trước**.
- Một nút mới `50'` đại diện cho kế nhiệm ở vị trí mới trong phiên bản sau.
- Không được làm mất cây con phải của kế nhiệm nếu kế nhiệm có con phải.
- Nếu mỗi nút có cả `key` và `value`, phải chuyển **cả cặp dữ liệu**; không chỉ chuyển khóa.
- Nếu cần cân bằng AVL, phải tái cân bằng trên đường loại kế nhiệm và tại nút thay thế.

### 8.4. Hàm lấy phần tử nhỏ nhất theo phong cách thuần

Mã giả:

```text
EXTRACT_MIN(u):
    require u != None

    if u.left == None:
        # Không sửa u.
        return (u.key, u.value, u.right)

    (k, v, new_left) = EXTRACT_MIN(u.left)

    rebuilt = NEW_NODE(
        key=u.key, value=u.value,
        left=new_left, right=u.right
    )

    return (k, v, REBALANCE_PURE(rebuilt))
```

Khác với một biến thể mutable, hàm này **không tách con trỏ khỏi nút `u` cũ**. Nó **đọc** dữ liệu kế nhiệm và dựng cây phải mới, còn cây con của phiên bản cũ vẫn nguyên vẹn.

### 8.5. So sánh xóa và cập nhật trọng số

| Thao tác | Đường chịu ảnh hưởng | Có thể cần xoay? | Nút cũ bị sửa? |
|---|---|---|---|
| Thay trọng số khóa đã có | Đường tìm tới khóa | Không nếu cấu trúc không đổi | Không |
| Chèn khóa mới | Đường tìm tới vị trí trống | Có, trong AVL | Không |
| Xóa lá | Đường từ lá tới gốc | Có | Không |
| Xóa nút một con | Đường tổ tiên; cây con giữ nguyên | Có | Không |
| Xóa nút hai con | Đường tới nút bị xóa và tới kế nhiệm/tiền nhiệm | Có | Không |
| Xóa khóa không tồn tại | Đường tìm kiếm, nhưng không đổi nội dung | Không | Không; có thể 0 nút mới |

Mọi thao tác ở bảng đều có thể thực hiện **không làm thay đổi phiên bản cũ** bằng path copying và những phép tái cân bằng thuần.

## 9. Vì sao AVL phù hợp để minh họa path copying?

### 9.1. BST tự cân bằng và bảo đảm chiều cao

Một BST thường không có bảo đảm chiều cao. Nếu chèn khóa tăng dần vào một BST không cân bằng, cây có thể thành:

```text
1
 \
  2
   \
    3
     \
      4
       ...
```

Khi đó cập nhật khóa sâu có thể phải tạo `\Theta(n)` nút mới.

Cây AVL giữ:

\[
\boxed{|height(left)-height(right)|\le 1}
\]

tại mọi nút. Với `n` nút, chiều cao AVL là:

\[
\boxed{h=O(\log(n+1))}.
\]

Do đó:

- Tìm một khóa: `O(\log(n+1))`.
- Chèn, xóa, sửa giá trị: `O(\log(n+1))` thời gian.
- Sao chép đường đi và các phép xoay thuần: `O(\log(n+1))` nút mới.

Đây là **bảo đảm xấu nhất theo kích thước cây** đối với AVL, khác với bảo đảm **kỳ vọng** của treap dùng priority ngẫu nhiên.

### 9.2. Metadata chọn trong bài

Để hiểu vì sao phải **tính lại metadata trên nút mới**, ta lưu:

- `height`: phục vụ cân bằng AVL.
- `size`: số nút trong cây con, phục vụ truy vấn thứ hạng.
- `subtree_sum`: tổng trọng số của cây con, phục vụ tổng theo khoảng khóa.

Với quy ước:

\[
height(\varnothing)=0,
\]

\[
height(u)=1+\max(height(u.left),height(u.right)),
\]

\[
size(\varnothing)=0,\qquad
size(u)=1+size(u.left)+size(u.right),
\]

\[
sum(\varnothing)=0,\qquad
sum(u)=value(u)+sum(u.left)+sum(u.right).
\]

**Nút lá có chiều cao `1`** trong bài. Có những giáo trình chọn nút lá cao `0` và cây rỗng cao `-1`; hai cách đều đúng nếu nhất quán.

### 9.3. Vì sao metadata phải được tạo mới, không `pull` vào nút cũ?

Một hàm xây nút thuần:

```text
MAKE(key, value, left, right):
    return NEW_NODE(
        key, value, left, right,
        height = 1 + max(height(left),height(right)),
        size = 1 + size(left)+size(right),
        subtree_sum = value+sum(left)+sum(right)
    )
```

Mỗi lần tạo một nút mới, hàm `MAKE` tính metadata đúng theo hai cây con đã hoàn chỉnh.

Vì vậy không cần gọi:

```python
old_node.size = ...
old_node.height = ...
```

trên nút cũ. Những lệnh gán này sẽ phá bất biến phiên bản nếu nút cũ đang được nhiều gốc dùng chung.

### 9.4. Phép xoay trái phải thuần

Giả sử cần xoay trái tại `x`:

```text
Trước:                        Sau:

       x                            y'
      / \                          /  \
     A   y                        x'   C
        / \                      /   \
       B   C                    A     B
```

Không sửa `x` hoặc `y` cũ. Thay vào đó:

```text
x' = MAKE(x.key, x.value, A, B)
y' = MAKE(y.key, y.value, x', C)
return y'
```

Các cây con `A,B,C` được **chia sẻ**, miễn là chúng bất biến.

Xoay phải làm ngược lại:

```text
Trước:                        Sau:

         y                          x'
        / \                        /  \
       x   C                      A    y'
      / \                             / \
     A   B                           B   C
```

Dựng:

```text
y' = MAKE(y.key, y.value, B, C)
x' = MAKE(x.key, x.value, A, y')
return x'
```

### 9.5. Xoay kép

Nếu AVL cần xoay trái–phải hoặc phải–trái, có thể tổ hợp các hàm xoay thuần:

```text
Left-Right:
    new_left = ROTATE_LEFT(node.left)
    node2 = MAKE(node.key,node.value,new_left,node.right)
    return ROTATE_RIGHT(node2)

Right-Left:
    new_right = ROTATE_RIGHT(node.right)
    node2 = MAKE(node.key,node.value,node.left,new_right)
    return ROTATE_LEFT(node2)
```

Số lần tạo nút mới vẫn là **hằng số cho mỗi lần tái cân bằng**, nên tổng số nút mới trên đường cập nhật dài `O(h)` vẫn là `O(h)`.

### 9.6. Nhiều phiên bản có thể chứa các hình dạng cây khác nhau

Với cùng một tập khóa, AVL không bắt buộc có một hình dạng duy nhất. Sau cập nhật:

- Phiên bản cũ giữ cây cũ với các phép xoay đã xảy ra trước đó.
- Phiên bản mới có thể có một hình dạng khác do chèn/xóa và tái cân bằng.
- Những cây con vẫn giữ nguyên về mặt đối tượng có thể được chia sẻ.
- Những nút bị thay đổi liên kết do xoay phải được tái tạo.

**Không nên kiểm thử bằng cách bắt mọi phiên bản phải có cùng hình dạng nút.** Điều cần kiểm là thứ tự BST, giá trị, cân bằng, metadata và sự bất biến của các phiên bản cũ.

## 10. Cài đặt Python: nút AVL bất biến và hàm tạo metadata

### 10.1. Phạm vi cài đặt

Ta xây một **persistent AVL map** từ khóa nguyên sang trọng số nguyên. Mỗi cập nhật trả một **gốc cây mới**. Cấu trúc bao gồm:

- Tìm, chèn/cập nhật và xóa khóa.
- Cân bằng AVL bằng các phép xoay **không thay đổi đối tượng cũ**.
- Lưu `height`, `size` và `subtree_sum` tại mỗi nút.
- Lưu nhiều gốc phiên bản và cập nhật từ **bất kỳ phiên bản hợp lệ**.
- Truy vấn bản cũ và bản mới riêng biệt.
- Không lưu `parent` trong nút, bởi một nút được chia sẻ có thể có **cha khác nhau giữa các phiên bản**.

**Hợp đồng dữ liệu:** khóa và trọng số là số nguyên Python; mỗi khóa xuất hiện tối đa một lần trong một phiên bản; `put` thêm khóa mới hoặc thay giá trị khóa cũ; `remove` xóa một khóa, không ném lỗi nếu khóa không tồn tại.

### 10.2. Khai báo nút bất biến

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, eq=False)
class Node:
    key: int
    value: int

    left: Node | None
    right: Node | None

    height: int
    size: int
    subtree_sum: int


def height_of(node: Node | None) -> int:
    return 0 if node is None else node.height


def size_of(node: Node | None) -> int:
    return 0 if node is None else node.size


def total_of(node: Node | None) -> int:
    return 0 if node is None else node.subtree_sum


def make_node(
    key: int,
    value: int,
    left: Node | None = None,
    right: Node | None = None,
) -> Node:
    """Tạo nút MỚI và tính metadata, không sửa hai cây con."""
    return Node(
        key=key,
        value=value,
        left=left,
        right=right,
        height=1 + max(height_of(left), height_of(right)),
        size=1 + size_of(left) + size_of(right),
        subtree_sum=value + total_of(left) + total_of(right),
    )


def balance_factor(node: Node) -> int:
    return height_of(node.left) - height_of(node.right)
```

**Vì sao `frozen=True`?** Một thao tác như:

```python
# Không hợp lệ: nút đã tạo là frozen dataclass.
# root.left = some_new_left
```

sẽ không được chấp nhận thông qua phép gán trường thông thường. Thay đổi cây phải đi qua `make_node`, tạo đối tượng mới.

**Vì sao `eq=False`?** Để các đối tượng nút được nhận diện theo **identity** khi quan sát chia sẻ cấu trúc. Nếu để dataclass so sánh đệ quy tất cả trường, so sánh/hash của nút có thể phải đi sâu toàn bộ cấu trúc. Trong bài, ta quan tâm **hai tham chiếu có trỏ tới cùng một nút hay không**, dùng `is`.

**Phạm vi bất biến:** `frozen=True` không phải ranh giới bảo mật tuyệt đối trước các kỹ thuật thao tác runtime cấp thấp, nhưng đủ thể hiện hợp đồng **không sửa nút thông qua API thông thường**. Vì `key,value` là số nguyên và con là các nút bất biến, tham chiếu dùng chung an toàn trong mô hình bài học.

### 10.3. Phép xoay thuần

```python
def rotate_left(root: Node) -> Node:
    right = root.right
    if right is None:
        raise ValueError("Không thể xoay trái nếu thiếu con phải")

    # A = root.left, B = right.left, C = right.right
    lower = make_node(
        root.key,
        root.value,
        root.left,
        right.left,
    )
    return make_node(
        right.key,
        right.value,
        lower,
        right.right,
    )


def rotate_right(root: Node) -> Node:
    left = root.left
    if left is None:
        raise ValueError("Không thể xoay phải nếu thiếu con trái")

    # A = left.left, B = left.right, C = root.right
    lower = make_node(
        root.key,
        root.value,
        left.right,
        root.right,
    )
    return make_node(
        left.key,
        left.value,
        left.left,
        lower,
    )
```

Cả hai hàm đều **chỉ đọc** nút đầu vào:

- `rotate_left` tạo nút mới cho vị trí gốc thấp hơn, rồi nút gốc mới.
- `rotate_right` làm đối xứng.
- Các cây con `A,B,C` được truyền vào `make_node` **bằng tham chiếu**, không nhân bản toàn bộ.

Sau xoay, **hai phiên bản** có thể giữ hai hình dạng khác nhau, nhưng mỗi phiên bản vẫn biểu diễn đúng thứ tự khóa của mình.

### 10.4. Tái cân bằng AVL thuần

```python
def rebalance(node: Node) -> Node:
    """node đã được dựng bằng make_node và có con hợp lệ."""
    bf = balance_factor(node)

    if bf > 1:
        left = node.left
        assert left is not None

        if balance_factor(left) < 0:
            fixed_left = rotate_left(left)
            node = make_node(
                node.key, node.value,
                fixed_left, node.right
            )

        return rotate_right(node)

    if bf < -1:
        right = node.right
        assert right is not None

        if balance_factor(right) > 0:
            fixed_right = rotate_right(right)
            node = make_node(
                node.key, node.value,
                node.left, fixed_right
            )

        return rotate_left(node)

    return node
```

Hàm `rebalance` không thực hiện phép gán nào lên `node.left`, `node.right` hoặc `node.height`. Nếu cần xoay kép, nó **dựng nút trung gian mới** trước khi xoay tiếp.

Giả thiết: hai cây con đã hợp lệ AVL, và cập nhật từ một thao tác chuẩn làm lệch chiều cao có thể xử lý bằng các trường hợp xoay AVL thông thường.

## 11. Chèn và cập nhật một khóa bằng path copying

### 11.1. Cài đặt hàm `put_key`

```python
def put_key(
    root: Node | None,
    key: int,
    value: int,
) -> Node:
    """Chèn khóa mới hoặc thay value của khóa đã tồn tại."""
    if root is None:
        return make_node(key, value)

    if key < root.key:
        changed_left = put_key(root.left, key, value)

        # Tránh tạo nút mới nếu thật sự không thay đổi.
        if changed_left is root.left:
            return root

        rebuilt = make_node(
            root.key,
            root.value,
            changed_left,
            root.right,
        )
        return rebalance(rebuilt)

    if key > root.key:
        changed_right = put_key(root.right, key, value)

        if changed_right is root.right:
            return root

        rebuilt = make_node(
            root.key,
            root.value,
            root.left,
            changed_right,
        )
        return rebalance(rebuilt)

    # key == root.key: chỉ thay value, không thay hình dạng.
    if value == root.value:
        return root

    return make_node(
        root.key,
        value,
        root.left,
        root.right,
    )
```

Có ba đường đi:

1. **Khóa chưa có:** cuối cùng gặp `None`, tạo một nút lá, rồi xây lại tổ tiên và tái cân bằng.
2. **Khóa đã có, giá trị khác:** tạo một nút mới với giá trị mới, rồi xây lại tổ tiên. Không cần xoay nếu chỉ thay trọng số.
3. **Khóa đã có, giá trị giống hệt:** trả nút cũ ở vị trí tìm thấy; đường quay về sẽ trả lại nguyên các nút tổ tiên → **không có cấp phát mới**.

### 11.2. Vì sao nhánh còn lại được phép dùng chung?

Trong nhánh `key<root.key`, chỉ có cây trái mới được cập nhật; cây phải **không chứa khóa cần sửa** theo bất biến BST. Vì vậy:

```python
rebuilt = make_node(
    root.key,
    root.value,
    changed_left,
    root.right,    # cùng đối tượng cũ
)
```

không làm sai kết quả.

Điều kiện **bất biến theo ngữ nghĩa** là `root.right` không bị sửa trong tương lai. Vì tất cả thao tác cập nhật của cấu trúc cũng là thuần, điều kiện này được giữ theo quy nạp.

### 11.3. Khi nào cần tạo lại cả gốc mặc dù chỉ sửa lá?

Nút gốc mới phải trỏ tới **một nhánh con mới**. Vì nút gốc cũ là bất biến, ta không thể cập nhật trường con của nó. Do đó phải tạo **một bản sao gốc** có các liên kết thích hợp.

Đây chính là lý do path copying tạo các bản sao của **mọi tổ tiên cần thay đổi đường liên kết**, không chỉ một bản sao nút lá.

## 12. Xóa một khóa trong persistent AVL

### 12.1. Hàm lấy kế nhiệm mà không sửa cây cũ

```python
def extract_min(
    root: Node,
) -> tuple[int, int, Node | None]:
    """Trả (min_key, min_value, cây còn lại).

    Không sửa root hoặc các nút cũ.
    """
    if root.left is None:
        # Nút nhỏ nhất có thể có con phải.
        return root.key, root.value, root.right

    key, value, changed_left = extract_min(root.left)

    rebuilt = make_node(
        root.key,
        root.value,
        changed_left,
        root.right,
    )
    return key, value, rebalance(rebuilt)
```

**Cơ sở:** nút nhỏ nhất của một BST là nút **không có con trái**. Cây còn lại sau khi bỏ nút ấy là **con phải của nó** (có thể rỗng).

**Bước đệ quy:** khi nút nhỏ nhất nằm sâu trong cây trái, trả cây trái mới rồi dựng bản sao cha, giữ nguyên cây phải.

### 12.2. Hàm `delete_key`

```python
def delete_key(
    root: Node | None,
    key: int,
) -> Node | None:
    """Xóa key nếu có, giữ nguyên tất cả nút thuộc bản cũ."""
    if root is None:
        return None

    if key < root.key:
        changed_left = delete_key(root.left, key)

        if changed_left is root.left:
            return root

        rebuilt = make_node(
            root.key,
            root.value,
            changed_left,
            root.right,
        )
        return rebalance(rebuilt)

    if key > root.key:
        changed_right = delete_key(root.right, key)

        if changed_right is root.right:
            return root

        rebuilt = make_node(
            root.key,
            root.value,
            root.left,
            changed_right,
        )
        return rebalance(rebuilt)

    # key == root.key: xóa chính nút đang xét.
    if root.left is None:
        return root.right

    if root.right is None:
        return root.left

    # Hai con: chuyển cả khóa và giá trị kế nhiệm.
    successor_key, successor_value, new_right = (
        extract_min(root.right)
    )

    rebuilt = make_node(
        successor_key,
        successor_value,
        root.left,
        new_right,
    )
    return rebalance(rebuilt)
```

### 12.3. Bảo toàn phiên bản cũ khi xóa nút hai con

Giả sử bản cũ có nút `u` với hai con:

```text
u.left  → A
u.right → B
```

Hàm `extract_min(B)` tạo cây `B'` mà **không sửa B**. Sau đó `delete_key` tạo nút mới mang:

```text
successor_key
successor_value
left  = A
right = B'
```

Tập khóa của cây mới là tập khóa cũ **trừ đúng một khóa cần xóa**. Các nút trong `A` vẫn được dùng chung; những nút trong `B` không thuộc đường xóa kế nhiệm cũng được chia sẻ.

### 12.4. Không tìm thấy khóa có thể trả lại chính gốc cũ

Ở nhánh tìm kiếm khi `key` không tồn tại, đệ quy tới `None` rồi trả về `None`. Nếu cây con trả về **chính con cũ**, ta trả lại **chính nút cha cũ**.

Kết quả là:

```python
new_root = delete_key(old_root, 999)
assert new_root is old_root   # Nếu 999 không có.
```

Một lệnh xóa không làm gì không cần tạo bất kỳ nút mới nào, dù vẫn tốn thời gian đi tìm khóa.

## 13. Bộ quản lý phiên bản: lưu gốc, không nhân bản toàn cây

### 13.1. Vì sao cần một lớp lưu phiên bản?

Các hàm `put_key` và `delete_key` có thể hoạt động trực tiếp với tham chiếu gốc. Nhưng ứng dụng có thể muốn đặt tên hoặc đánh số các phiên bản.

Ta dùng một danh sách Python chứa các gốc:

```text
_roots[0] = None             # Phiên bản rỗng.
_roots[1] = root_1
_roots[2] = root_2
...
```

Danh sách quản lý phiên bản **có thể thay đổi** để thêm gốc. Điều quan trọng là **các nút cây được lưu bên trong các gốc là bất biến**.

Cấu trúc “một danh sách mutable chứa các tham chiếu tới cây immutable” là cách tổ chức phổ biến; nó không mâu thuẫn với persistence của **dữ liệu cây**.

### 13.2. Các hàm truy vấn theo một gốc

```python
def find_value(root: Node | None, key: int) -> int | None:
    node = root

    while node is not None:
        if key < node.key:
            node = node.left
        elif key > node.key:
            node = node.right
        else:
            return node.value

    return None


def rank_lt_root(root: Node | None, key: int) -> int:
    """Số khóa phân biệt nhỏ hơn key."""
    result = 0
    node = root

    while node is not None:
        if key <= node.key:
            node = node.left
        else:
            result += size_of(node.left) + 1
            node = node.right

    return result


def prefix_sum_root(
    root: Node | None,
    key: int,
    inclusive: bool,
) -> int:
    """Tổng value với khóa < key hoặc <= key."""
    result = 0
    node = root

    while node is not None:
        if key < node.key or (
            key == node.key and not inclusive
        ):
            node = node.left
        else:
            result += total_of(node.left) + node.value
            node = node.right

    return result
```

Những truy vấn này chỉ **đọc** gốc và các nút. Không có lời gọi `push` kiểu mutating hoặc thay con trỏ.

### 13.3. Lớp `VersionStore`

```python
class VersionStore:
    def __init__(self):
        # Phiên bản 0 là cây rỗng.
        self._roots: list[Node | None] = [None]

    @staticmethod
    def _check_int(value, name):
        if type(value) is not int:
            raise TypeError(f"{name} phải là int")

    def _root(self, version: int) -> Node | None:
        if (
            type(version) is not int
            or version < 0
            or version >= len(self._roots)
        ):
            raise IndexError("Phiên bản không hợp lệ")

        return self._roots[version]

    @property
    def version_count(self) -> int:
        return len(self._roots)

    def put(self, version: int, key: int, value: int) -> int:
        """Tạo phiên bản mới từ version, thêm/thay key."""
        root = self._root(version)
        self._check_int(key, "key")
        self._check_int(value, "value")

        new_root = put_key(root, key, value)
        self._roots.append(new_root)
        return len(self._roots) - 1

    def delete(self, version: int, key: int) -> int:
        """Tạo phiên bản mới từ version, xóa key nếu có."""
        root = self._root(version)
        self._check_int(key, "key")

        new_root = delete_key(root, key)
        self._roots.append(new_root)
        return len(self._roots) - 1

    def get(self, version: int, key: int) -> int | None:
        root = self._root(version)
        self._check_int(key, "key")
        return find_value(root, key)

    def length(self, version: int) -> int:
        return size_of(self._root(version))

    def total(self, version: int) -> int:
        return total_of(self._root(version))

    def rank_lt(self, version: int, key: int) -> int:
        root = self._root(version)
        self._check_int(key, "key")
        return rank_lt_root(root, key)

    def select(self, version: int, k: int) -> tuple[int, int]:
        """Phần tử khóa nhỏ thứ k, với k 1-based."""
        root = self._root(version)
        self._check_int(k, "k")

        if not 1 <= k <= size_of(root):
            raise IndexError("k ngoài [1,n]")

        node = root

        while node is not None:
            left_size = size_of(node.left)

            if k <= left_size:
                node = node.left
            elif k == left_size + 1:
                return node.key, node.value
            else:
                k -= left_size + 1
                node = node.right

        raise RuntimeError("Metadata size không nhất quán")

    def sum_between(
        self,
        version: int,
        low: int,
        high: int,
    ) -> int:
        """Tổng value của các khóa trong [low, high] đóng."""
        root = self._root(version)
        self._check_int(low, "low")
        self._check_int(high, "high")

        if low > high:
            return 0

        # <= high trừ đi < low: không cần high + 1.
        return (
            prefix_sum_root(root, high, True)
            - prefix_sum_root(root, low, False)
        )

    def items(self, version: int) -> list[tuple[int, int]]:
        """Xuất snapshot theo khóa tăng, không sửa cây."""
        root = self._root(version)
        output = []
        stack = []
        node = root

        while node is not None or stack:
            while node is not None:
                stack.append(node)
                node = node.left

            node = stack.pop()
            output.append((node.key, node.value))
            node = node.right

        return output
```

**Hợp đồng phiên bản:**

- `put(version,...)` hoặc `delete(version,...)` tạo thêm **một ID phiên bản mới** và trả ID đó.
- Mọi phiên bản cũ tiếp tục tồn tại trong `_roots`.
- Có thể **rẽ nhánh** bằng cách dùng bất kỳ ID phiên bản nào làm đầu vào cho thao tác cập nhật.
- Nếu thao tác không đổi nội dung, mã vẫn tạo **một ID mới** nhưng có thể **dùng lại cùng tham chiếu gốc**.
- Các nút immutable, nhưng **danh sách `_roots` bản thân vẫn mutable**; bài không triển khai giao dịch/đồng bộ nhiều luồng hoặc lưu bền xuống đĩa.

### 13.4. Cấu trúc một chương trình Python hoàn chỉnh

Để chạy các ví dụ, ghép **theo thứ tự**:

1. Toàn bộ mã trong mục 10.2: `Node`, các hàm `height_of/size_of/total_of/make_node/balance_factor`.
2. Mục 10.3–10.4: `rotate_left/rotate_right/rebalance`.
3. Mục 11.1: `put_key`.
4. Mục 12.1–12.2: `extract_min/delete_key`.
5. Mục 13.2: `find_value/rank_lt_root/prefix_sum_root`.
6. Mục 13.3: `VersionStore`.

Tất cả các đoạn mã ở các mục trên dùng cùng định nghĩa `Node` và **không cần gói ngoài** ngoại trừ thư viện chuẩn Python `dataclasses`. Cú pháp annotation `Node | None` và `slots=True` yêu cầu **Python 3.10 trở lên**.

## 14. Truy vết các phiên bản và chia sẻ cấu trúc

### 14.1. Xây phiên bản gốc bằng chuỗi cập nhật

```python
store = VersionStore()

v = 0  # Phiên bản 0: cây rỗng.

records = [
    (40, 4),
    (20, 2),
    (60, 6),
    (10, 1),
    (30, 3),
    (50, 5),
    (70, 7),
]

for key, value in records:
    v = store.put(v, key, value)

base = v

assert store.length(base) == 7
assert store.total(base) == 28
assert store.items(base) == [
    (10, 1), (20, 2), (30, 3), (40, 4),
    (50, 5), (60, 6), (70, 7),
]
```

Ta đã tạo một chuỗi phiên bản trong quá trình xây cây. `base` trỏ tới phiên bản chứa toàn bộ bảy khóa.

### 14.2. Tạo hai nhánh từ cùng một phiên bản

```python
# Nhánh A: thay trọng số tại khóa 30.
v_update = store.put(base, 30, 300)

# Nhánh B: chèn khóa 25 dựa trên base, không dựa v_update.
v_insert = store.put(base, 25, 25)

assert store.get(base, 30) == 3
assert store.get(v_update, 30) == 300
assert store.get(v_insert, 30) == 3

assert store.get(base, 25) is None
assert store.get(v_update, 25) is None
assert store.get(v_insert, 25) == 25

assert store.total(base) == 28
assert store.total(v_update) == 325
assert store.total(v_insert) == 53
```

Sơ đồ lịch sử:

```text
   base: {10,20,30,40,50,60,70}
     |
     +-- put(30,300) --> v_update
     |
     +-- put(25,25)  --> v_insert
```

Đây là **rẽ nhánh phiên bản**, không phải trộn hai phiên bản. Cả hai nhánh tiếp tục đọc được trạng thái `base`.

### 14.3. Nhánh tiếp tục xóa một khóa

```python
v_delete = store.delete(v_update, 60)

assert store.get(v_update, 60) == 6
assert store.get(v_delete, 60) is None
assert store.get(base, 60) == 6

assert store.total(v_delete) == 319
assert store.length(v_delete) == 6

assert store.select(v_delete, 3) == (30, 300)
assert store.rank_lt(v_delete, 40) == 3
assert store.sum_between(v_delete, 20, 50) == (
    2 + 300 + 4 + 5
)
```

Sau đó lịch sử có dạng:

```text
base
  ├── v_update ──delete(60)──> v_delete
  └── v_insert
```

### 14.4. Kiểm tra chia sẻ cây con bằng identity

Vì chỉ đổi **trọng số** khóa `30`, cấu trúc của phiên bản gốc đang dùng AVL đối xứng và không cần xoay. Cây con phải gốc `60` được chia sẻ:

```python
base_root = store._root(base)
update_root = store._root(v_update)

assert base_root is not None
assert update_root is not None

assert base_root is not update_root

# Nhánh đối diện đường 40 -> 20 -> 30 được chia sẻ.
assert base_root.right is update_root.right

# Nút 10 dưới nhánh trái 20 cũng được chia sẻ.
assert base_root.left is not None
assert update_root.left is not None
assert base_root.left.left is update_root.left.left

# Nhưng các nút trên đường thay đổi là đối tượng khác.
assert base_root.left is not update_root.left
```

Các phép `is` ở đây kiểm tra **dùng cùng đối tượng**. Nếu dùng `==` với một kiểu nút có so sánh theo giá trị, hai nút khác nhau nhưng cùng dữ liệu có thể bị xem là bằng; điều đó **không chứng minh chia sẻ cấu trúc**.

### 14.5. Cập nhật không thay đổi nội dung

```python
same = store.put(base, 30, 3)

assert store._root(same) is store._root(base)
assert store.items(same) == store.items(base)

# Xóa khóa không có: root cũng có thể được dùng lại.
missing = store.delete(base, 999)

assert store._root(missing) is store._root(base)
assert store.items(missing) == store.items(base)
```

Kết quả có một **ID phiên bản mới** nhưng **không có nút cây mới** vì ánh xạ dữ liệu không thay đổi.

### 14.6. Phiên bản cũ có thực sự không đổi không?

```python
before = store.items(base)

another = store.put(base, 10, -50)
another = store.put(another, 75, 75)
another = store.delete(another, 30)

assert store.items(base) == before
assert store.get(base, 10) == 1
assert store.get(base, 30) == 3
assert store.get(base, 75) is None

assert store.get(another, 10) == -50
assert store.get(another, 30) is None
assert store.get(another, 75) == 75
```

Kết quả mong đợi là phiên bản `base` có đúng bản ghi như trước, bất kể các nhánh sau nó được cập nhật thế nào.

## 15. Validator độc lập: kiểm tra cả BST, AVL và metadata

### 15.1. Những bất biến phải được xác thực

Một cây vừa có khả năng phiên bản hóa, vừa có cân bằng AVL và metadata tổng hợp có nhiều điều kiện:

1. Cấu trúc từng phiên bản là một **cây**: không có chu trình hay một nút được lặp ở hai vị trí trong cùng một cây.
2. Khóa BST đúng theo **cận từ tất cả tổ tiên**.
3. Mỗi nút lưu `height` bằng chiều cao tính lại từ hai con.
4. Chênh lệch chiều cao hai cây con không vượt `1`.
5. `size` bằng số nút tính lại từ cấu trúc.
6. `subtree_sum` bằng tổng trọng số tính lại.
7. Giá trị `key,value` thuộc kiểu đầu vào được hỗ trợ.
8. Giữa các phiên bản được phép **chia sẻ nút bất biến**; validator không được nhầm chia sẻ **giữa hai phiên bản** với chia sẻ hai đường **trong cùng một phiên bản**.

### 15.2. Validator hậu thứ tự không sửa cây

```python
def validate_avl(root: Node | None) -> bool:
    """Kiểm tra cây, thứ tự BST, AVL, size/sum/height."""
    if root is None:
        return True

    seen = set()
    actual = {}

    # lower/upper là cận LOẠI TRỪ.
    # frame = (node, lower, upper, ready)
    frames = [(root, None, None, False)]

    while frames:
        node, lower, upper, ready = frames.pop()

        if node is None:
            continue

        if not isinstance(node, Node):
            return False

        marker = id(node)

        if not ready:
            if marker in seen:
                return False
            seen.add(marker)

            if (
                type(node.key) is not int
                or type(node.value) is not int
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
                ls, lsum, lh = 0, 0, 0
            else:
                ls, lsum, lh = actual[id(node.left)]

            if node.right is None:
                rs, rsum, rh = 0, 0, 0
            else:
                rs, rsum, rh = actual[id(node.right)]

            expected_size = 1 + ls + rs
            expected_sum = node.value + lsum + rsum
            expected_height = 1 + max(lh, rh)

            if node.size != expected_size:
                return False
            if node.subtree_sum != expected_sum:
                return False
            if node.height != expected_height:
                return False
            if abs(lh - rh) > 1:
                return False

            actual[marker] = (
                expected_size, expected_sum, expected_height
            )

    return True
```

**Tại sao dùng `id(node)`?** Validator cần nhận diện **đối tượng vật lý**, không phụ thuộc so sánh cấu trúc giữa các nút. Nó tính lại metadata từ hai con và lưu kết quả tạm theo identity.

Chi phí kiểm tra một phiên bản có `n` nút:

- Thời gian: `O(n)`.
- Bộ nhớ phụ: `O(n)` cho `seen`, `actual` và stack.

Do đó validator **không nằm trong độ phức tạp `O(\log n)` của một cập nhật**. Nó là công cụ học và kiểm thử.

### 15.3. So sánh với từ điển tham chiếu

```python
store = VersionStore()
reference = {}
v = 0

actions = [
    ("put", 40, 4),
    ("put", 20, 2),
    ("put", 60, 6),
    ("put", 10, 1),
    ("put", 30, 3),
    ("put", 50, 5),
    ("put", 70, 7),
    ("put", 30, 300),
    ("delete", 20, None),
    ("put", 25, 25),
    ("delete", 999, None),
]

for action, key, value in actions:
    if action == "put":
        reference[key] = value
        v = store.put(v, key, value)
    else:
        reference.pop(key, None)
        v = store.delete(v, key)

    assert validate_avl(store._root(v))
    assert store.items(v) == sorted(reference.items())
    assert store.length(v) == len(reference)
    assert store.total(v) == sum(reference.values())

    for i, (k, w) in enumerate(
        sorted(reference.items()), start=1
    ):
        assert store.select(v, i) == (k, w)

    for x in [0, 20, 25, 45, 100]:
        expected_rank = sum(k < x for k in reference)
        assert store.rank_lt(v, x) == expected_rank
```

**Lưu ý:** các đoạn `assert` là ví dụ **người học có thể tự thực hành**, không phải tuyên bố rằng tác vụ biên soạn bài này đã chạy chương trình.

### 15.4. Kiểm tra sự bất biến qua nhiều phiên bản

Một phương pháp kiểm thử quan trọng là lưu **kết quả snapshot mong đợi của tất cả phiên bản** trong một mảng tham chiếu riêng:

```python
store = VersionStore()
reference_by_version = [{}]  # Phiên bản 0 rỗng.

v1 = store.put(0, 10, 100)
reference_by_version.append({10: 100})

v2 = store.put(v1, 20, 200)
reference_by_version.append({10: 100, 20: 200})

v3 = store.put(v1, 30, 300)  # Rẽ nhánh từ v1.
reference_by_version.append({10: 100, 30: 300})

for version, expected in enumerate(reference_by_version):
    assert store.items(version) == sorted(expected.items())
    assert validate_avl(store._root(version))
```

**Điểm quan trọng:** kiểm thử không chỉ kiểm bản mới. Phải đọc lại **tất cả phiên bản còn giữ** sau nhiều cập nhật để phát hiện một phép sửa in-place vô tình làm thay đổi dữ liệu cũ.

## 16. Chứng minh path copying giữ bất biến phiên bản

### 16.1. Mệnh đề

Cho một cây `T` mà mọi nút đều bất biến. Hàm cập nhật `U(T,x)`:

1. Chỉ đọc các nút của `T`.
2. Tạo những nút mới trên các đường bị ảnh hưởng.
3. Dùng lại nguyên các cây con không thay đổi.
4. Không sửa bất kỳ nút nào có thể đi tới từ `T`.

Khi đó:

- `T` tiếp tục biểu diễn chính xác dữ liệu ban đầu.
- Gốc `T'=U(T,x)` biểu diễn dữ liệu sau cập nhật, nếu thuật toán cập nhật BST đúng.
- Mọi cây con được chia sẻ giữa `T` và `T'` có **cùng nội dung bất biến**.

### 16.2. Cơ sở quy nạp

Với cây rỗng:

- Chèn khóa mới tạo một nút lá bất biến.
- Xóa khóa không có trả cây rỗng.
- Không có nút cũ nào bị sửa.

Với một nút lá:

- Cập nhật trọng số tạo một nút mới (trừ trường hợp no-op).
- Xóa trả `None`.
- Chèn con tạo nút mới và dựng lại gốc, tái cân bằng nếu cần.

Các kết quả đều giữ nguyên đối tượng nút cũ.

### 16.3. Bước quy nạp cho chèn/cập nhật

Giả sử các lời gọi cập nhật cây con đều giữ nguyên cây cũ của chúng và trả cây con mới đúng.

Tại một nút `u`:

- Nếu sửa bên trái, hàm tạo `u'` với `left` là cây trái mới và `right` là cây phải **cũ**.
- Nếu sửa bên phải, làm đối xứng.
- Nếu sửa ngay dữ liệu nút, tạo một bản ghi nút mới với hai con **cũ**.
- Nếu không thay đổi, trả nguyên `u`.

Như vậy:

1. `u` và hai liên kết của nó không đổi.
2. Cây mới biểu diễn đúng thay đổi ở đúng một nhánh.
3. Các nhánh không đổi được dùng lại an toàn.
4. Metadata của `u'` được tính lại từ các con đúng.

Nếu cây bị mất cân bằng, phép xoay thuần xây các nút mới từ những cây con đã đúng mà không sửa nút cũ; do xoay giữ nguyên thứ tự inorder, bất biến BST vẫn giữ.

### 16.4. Bước quy nạp cho xóa

Với khóa cần xóa:

- **Không tìm thấy:** trả lại các nút cũ, nên trạng thái không đổi.
- **Không quá một con:** trả nút con còn lại (bất biến), rồi dựng lại các tổ tiên trên đường tìm kiếm.
- **Hai con:** chọn kế nhiệm inorder, `extract_min` dựng cây phải mới mà không sửa cây cũ, rồi tạo nút thay thế mang cả khóa và giá trị kế nhiệm.

Theo tính chất BST, kế nhiệm là khóa nhỏ nhất lớn hơn khóa bị xóa; thay nút bị xóa bằng kế nhiệm rồi loại kế nhiệm ở vị trí cũ bảo toàn thứ tự khóa và giảm số nút đúng một.

Cách dựng nút mới và xoay thuần tiếp tục bảo toàn tính bất biến của cây cũ.

### 16.5. Hệ quả với nhiều phiên bản

Áp dụng quy nạp qua **chuỗi các lần cập nhật**:

- Phiên bản `V0` giữ nguyên sau khi tạo `V1`.
- Vì `V1` cũng gồm toàn nút bất biến, tạo `V2` từ `V1` không ảnh hưởng `V0` hoặc `V1`.
- Nếu `V3` được tạo trực tiếp từ `V0`, nó cũng không thay đổi `V1` hoặc `V2`.

Đó là nền tảng của **lịch sử rẽ nhánh** mà không cần sao chép toàn bộ dữ liệu cho mỗi nhánh.

## 17. Độ phức tạp: đường đi, nút mới và số phiên bản

### 17.1. Ký hiệu phân tích

Gọi:

- `n`: số nút trong phiên bản đang cập nhật.
- `h`: chiều cao phiên bản ấy theo số cạnh.
- `U`: số lần cập nhật phiên bản.
- `V`: số gốc phiên bản được giữ lại.
- `h_t`: chiều cao cây đầu vào của cập nhật thứ `t`.

Giả sử:

- Khóa và trọng số có kích thước phù hợp để so sánh/cộng trong `O(1)`.
- Mỗi nút chứa một số **hằng** trường.
- Cập nhật một khóa dùng đường tìm kiếm BST và một số lượng hằng phép xoay tại mỗi tầng cần tái cân bằng.
- Các nút đã tạo là bất biến; không cần copy những cây con không thay đổi.

### 17.2. Một lần thay trọng số

Một lần cập nhật khóa đã có:

1. Tìm khóa theo một đường dài tối đa `h+1` nút.
2. Tạo nút mới tại vị trí đổi giá trị (nếu dữ liệu thay đổi).
3. Tạo bản sao những tổ tiên trên đường về gốc.

Do đó:

\[
\boxed{
T_{\text{update}}=O(h+1),
\qquad
S_{\text{new-nodes}}=O(h+1).
}
\]

Nếu khóa đã có nhưng giá trị giống hệt, chương trình vẫn mất `O(h+1)` để tìm, nhưng có thể cấp phát **`0` nút mới**.

### 17.3. Chèn và xóa

Trong persistent AVL:

- Chèn một khóa mới: tìm một đường, dựng lại đường ấy, tái cân bằng thuần.
- Xóa khóa lá/một con: thay cây con, dựng lại tổ tiên.
- Xóa khóa hai con: đi tới nút cần xóa và lấy kế nhiệm trên một đường trong cây phải, dựng lại các đường liên quan.
- Mỗi phép xoay thuần tạo một số hằng nút mới.

Tổng số tầng ảnh hưởng là `O(h+1)`, nên:

\[
\boxed{
T_{\text{put/delete}}=O(h+1),
\qquad
S_{\text{allocated}}=O(h+1).
}
\]

Với AVL:

\[
\boxed{
h=O(\log(n+1)).
}
\]

Do đó mỗi cập nhật thật có thời gian và số nút tạo mới **`O(\log(n+1))` trong trường hợp xấu nhất** theo kích thước phiên bản đầu vào.

### 17.4. Bảng tóm tắt

| Thao tác | BST bất kỳ | Persistent AVL của bài | Nút cây cấp phát mới |
|---|---:|---:|---:|
| Đọc một khóa | `O(h+1)` | `O(\log(n+1))` | 0 |
| Rank theo khóa | `O(h+1)` | `O(\log(n+1))` | 0 |
| Chọn khóa thứ `k` | `O(h+1)` | `O(\log(n+1))` | 0 |
| Tổng trọng số theo khoảng khóa | `O(h+1)` | `O(\log(n+1))` | 0 |
| Thay trọng số khóa đã có | `O(h+1)` | `O(\log(n+1))` | `O(h+1)` |
| Chèn khóa mới | `O(h+1)` với bảo trì cấu trúc đúng | `O(\log(n+1))` | `O(h+1)` |
| Xóa khóa | `O(h+1)` với bảo trì cấu trúc đúng | `O(\log(n+1))` | `O(h+1)` |
| Đọc gốc phiên bản theo ID | `O(1)` | `O(1)` | 0 |
| Thêm gốc vào danh sách phiên bản | `O(1)` khấu hao | `O(1)` khấu hao | 0 nút cây |
| Liệt kê toàn bộ phiên bản có `n` khóa | `O(n)` | `O(n)` | 0 |

**Lưu ý:** thao tác thêm ID phiên bản vào `list` Python là `O(1)` **khấu hao**, không phải bảo đảm worst-case khi mảng quản lý phiên bản cần cấp phát lại. Chi phí đó tách biệt với chi phí nút của cây.

### 17.5. So sánh với sao chép toàn cây

Giả sử một cây AVL có khoảng `n=1\,000\,000` nút. Chiều cao logarit làm một đường tìm kiếm ngắn hơn nhiều so với `n`.

Nếu mỗi cập nhật phải sao chép **toàn bộ một triệu nút**, chi phí tăng theo `n` cho mỗi lần.

Với path copying:

- Sửa một khóa chủ yếu tạo **các nút trên đường liên quan**.
- Các nhánh khác, dù chứa hàng trăm nghìn nút, được **dùng chung**.
- Thời gian và bộ nhớ cấp phát thêm tăng theo **độ cao cây**, không theo tổng kích thước dữ liệu.

Con số nút mới chính xác còn phụ thuộc hình dạng cây, vị trí cập nhật và số phép xoay; không nên khẳng định “mỗi lần chỉ cấp phát đúng `\lceil\log_2 n\rceil` nút”.

### 17.6. Tổng bộ nhớ qua nhiều lần cập nhật

Cho một phiên bản cơ sở có `n_0` nút và tiếp tục lưu tất cả gốc sinh ra bởi `U` cập nhật.

Giới hạn tổng quát theo số nút mới thực sự tạo ra:

\[
Memory
=
O\left(
n_0+V+\sum_{t=1}^{U}(h_t+1)
\right)
\]

với một số hằng nút mới mỗi tầng; trong trường hợp no-op, số cấp phát thực tế còn ít hơn.

Nếu mọi phiên bản đầu vào đều là AVL và có không quá `N` nút, thì:

\[
\boxed{
Memory=O\left(n_0+V+U\log(N+1)\right).
}
\]

Đây là **chặn trên của tổng số nút vật lý được giữ**, không phải bộ nhớ cho từng phiên bản riêng. Những nút dùng chung chỉ chiếm bộ nhớ **một lần**.

### 17.7. Khi bỏ một phiên bản có giải phóng được nút không?

Không phải lúc nào cũng giải phóng ngay.

Nếu có nhiều gốc:

```text
root0 → A → B → shared_subtree
root1 → C → D → shared_subtree
```

bỏ `root0` không có nghĩa `shared_subtree` biến mất, vì `root1` vẫn trỏ tới nó.

Với bộ thu gom rác có quản lý tham chiếu như Python, nút có thể được thu hồi khi **không còn đường tham chiếu nào tới nó** từ những gốc hoặc đối tượng còn sống. Nếu các gốc cũ được giữ mãi trong `_roots`, những phần cây chỉ có bản cũ dùng vẫn **không đủ điều kiện giải phóng**.

Trong hệ thống C/C++, có thể dùng reference counting, arena quản lý theo thời gian, tracing GC hoặc kỹ thuật thu hồi tương ứng. **Persistence không tự giải quyết bài toán quản lý vòng đời bộ nhớ.**

### 17.8. Bộ nhớ stack của mã Python

Các hàm `put_key`, `delete_key` và `extract_min` dùng **đệ quy**, nên ngoài các nút mới còn có:

\[
S_{\text{stack}}=O(h+1).
\]

Với AVL, đây là `O(\log(n+1))`. Với BST không cân bằng, stack có thể dài `O(n)` và dễ chạm giới hạn đệ quy của Python.

Các truy vấn `get/rank/select/prefix_sum` trong bài dùng vòng lặp, nên **bộ nhớ phụ `O(1)`** ngoài kết quả.

## 18. Chia sẻ cấu trúc không phải “chia sẻ quyền được sửa”

### 18.1. Gốc khác nhau có thể cùng trỏ tới một cây con

Khi hai phiên bản cùng tham chiếu `subtree`:

```text
root_A -----> subtree
root_B -----> subtree
```

chúng **đọc cùng một đối tượng**. Đây là điểm tiết kiệm bộ nhớ của persistence.

Nhưng điều đó chỉ an toàn khi mọi thao tác sửa **luôn xây phiên bản mới**. Nếu một hàm nào đó vẫn gọi:

```python
subtree.left = new_child
```

thì cây con dùng chung bị thay đổi và có thể làm hỏng **nhiều phiên bản cùng lúc**.

### 18.2. Không lưu `parent` thông thường trong nút dùng chung

Một nút trong cây cũ có thể là con của `P`, nhưng trong phiên bản mới lại là con của `P'`. Nếu nút ấy lưu:

```python
node.parent = P
```

thì không có **một giá trị parent duy nhất** phù hợp cho cả hai phiên bản.

Giải pháp:

- Không lưu trường parent trong nút immutable.
- Khi truy vấn đường tổ tiên, đi từ **gốc của phiên bản đang xét**, có thể giữ stack đường đi.
- Hoặc thiết kế một chỉ mục cha **riêng cho từng phiên bản** nếu thật sự cần.

Đây là khác biệt quan trọng giữa **cây được chia sẻ** và một cây mutable có con trỏ `parent`.

### 18.3. Cẩn thận với cache đặt trong nút

Một cache như:

```text
node.subtree_sum
node.size
node.height
```

là an toàn khi được **tính sẵn lúc tạo nút** và không bị thay đổi về sau.

Ngược lại, một phương thức “đọc nhưng ghi cache”:

```python
if node.cached_value is None:
    node.cached_value = expensive_calculation()
```

sẽ ghi vào nút dùng chung. Đây là một dạng mutation ẩn và có thể gây tranh chấp đồng thời.

Có thể dùng cache ngoài cấu trúc theo identity hoặc một cơ chế lazy immutable/phù hợp khác, nhưng phải đánh giá lại chi phí, bộ nhớ và tính an toàn luồng.

### 18.4. Payload là đối tượng khả biến

Một dataclass có `frozen=True` chỉ ngăn gán lại các **trường trực tiếp**, không tự đóng băng nội dung của một `list` hoặc `dict` đang được tham chiếu.

Ví dụ:

```python
@dataclass(frozen=True)
class UnsafePayloadNode:
    value: list[int]

numbers = [1, 2]
node = UnsafePayloadNode(numbers)

numbers.append(3)
assert node.value == [1, 2, 3]
```

**Đối tượng `node` không bị gán trường, nhưng ý nghĩa giá trị mà nó biểu diễn đã đổi.**

Khi cần snapshot đáng tin cậy:

- Lưu kiểu bất biến (`int`, `str`, tuple chứa thành phần bất biến...).
- Sao chép dữ liệu khả biến ở biên API.
- Hoặc dùng cấu trúc persistent cho chính payload.

### 18.5. Cập nhật một bản trong số nhiều bản

Cho hai gốc `rootA` và `rootB` có dùng chung một cây con `S`. Gọi:

```text
rootC = update(rootA, key, value)
```

Không có “lệnh cập nhật đối tượng S” chung. Mọi thông tin mới đi qua **một đường nút mới** chỉ thuộc `rootC`, trừ những nhánh bất biến được chia sẻ.

Phiên bản `rootB` hoàn toàn **không cần biết** về bản cập nhật vừa xảy ra.

## 19. Undo/redo, phân nhánh và truy vấn phiên bản

### 19.1. Undo không cần chạy ngược thao tác khi còn root cũ

Nếu mỗi lần cập nhật trả một gốc mới:

```text
V0 -> V1 -> V2 -> V3
```

thì có thể thực hiện undo bằng cách **chuyển con trỏ phiên bản hiện hành** từ `V3` về `V2`, rồi về `V1`.

Trạng thái cũ vẫn tồn tại, không cần:

- Biết thao tác ngược của từng phép cập nhật.
- Đọc lại bản chụp toàn bộ cây từ bộ nhớ ngoài.
- Khôi phục thủ công giá trị cũ trên từng nút.

### 19.2. Redo và rẽ nhánh

Nếu người dùng undo từ `V3` về `V1` rồi thực hiện cập nhật mới, ta có thể có:

```text
V0 -> V1 -> V2 -> V3
       |
       +-------> V4
```

`V4` là nhánh mới, không tự động hủy `V2` hoặc `V3`. Hệ thống giao diện có thể chọn quy tắc:

- Chỉ cho redo theo một đường tuyến tính.
- Giữ mọi nhánh như lịch sử nhiều phiên bản.
- Có lệnh chuyển nhánh hoặc đánh dấu trạng thái hiện hành.

**Cấu trúc persistent cho phép lưu nhánh**, nhưng UX của undo/redo còn phụ thuộc cách ứng dụng quản lý lịch sử.

### 19.3. Snapshot đọc ổn định

Một truy vấn có thể nhận một tham chiếu:

```text
snapshot_root = store._root(version)
```

Nếu tất cả nút bên dưới bất biến, truy vấn đó **không bị thay đổi nội dung cây** khi một thao tác khác tạo gốc mới bằng path copying.

Tuy nhiên, trong phần mềm đồng thời vẫn phải xử lý:

- Công bố root mới an toàn theo mô hình bộ nhớ của ngôn ngữ.
- Quyền sở hữu và thời gian sống của snapshot.
- Đồng bộ danh sách phiên bản và metadata bên ngoài cây.
- Tính nguyên tử nếu cần cập nhật **nhiều khóa như một giao dịch**.

**Bất biến nút** giúp việc đọc snapshot đơn giản hơn, nhưng **không tự cung cấp transaction hoặc commit đa luồng đúng nghĩa**.

### 19.4. Một thao tác sửa nhiều khóa

Path copying mô tả thuận tiện khi cập nhật **một khóa**. Nếu cần sửa một loạt `q` khóa:

- Có thể áp dụng tuần tự `q` lần cập nhật lên các gốc tạm, chỉ phát hành gốc cuối cùng.
- Chi phí trên AVL thường là `O(q\log(n+q+1))` thời gian, với giả thiết mỗi cập nhật riêng.
- Nếu các đường cập nhật có **nhiều tổ tiên chung**, một thuật toán batch được thiết kế riêng có thể chia sẻ phần tính lại và giảm số nút cấp phát so với `q` lần cập nhật độc lập.
- Để bảo đảm tất cả sửa đổi được thấy **cùng lúc**, chỉ công bố gốc mới sau khi toàn bộ thao tác đã thành công.

Đây là vấn đề **tổ chức giao dịch/batch**, không phải lý do để sửa nút của phiên bản cũ.

## 20. Liên hệ với những cấu trúc persistent khác

### 20.1. Persistent segment tree

Nếu quản lý một mảng theo vị trí và cần **cập nhật một ô**, persistent segment tree cũng có thể dùng path copying:

```text
root_v0
   |
   +-- cập nhật chỉ số i:
         tạo lá mới ở i
         tạo bản sao các nút trên đường từ lá tới gốc
         chia sẻ các cây con khác
   |
root_v1
```

Với cây đoạn cân bằng:

- Cập nhật điểm: `O(\log n)` nút mới và thời gian.
- Tổng/Min/Max trên đoạn: dùng metadata cây con theo thao tác gộp.
- Phiên bản cũ: vẫn truy vấn được qua gốc cũ.

**Giống nhau:** sao chép đường đi và chia sẻ cây con bất biến.

**Khác nhau:** persistent AVL là **BST theo khóa động**; segment tree thường có cấu trúc **theo miền chỉ số/đoạn**. Chèn/xóa khóa và cập nhật một ô mảng không phải cùng một hợp đồng.

### 20.2. Persistent trie và HAMT

Trong trie hoặc HAMT (*Hash Array Mapped Trie*), cập nhật một khóa cũng có thể:

1. Đi theo các chữ số/phần hash của khóa.
2. Tạo nút mới tại đường chịu ảnh hưởng.
3. Dùng chung các nhánh khác.

Chiều dài đường đi phụ thuộc **biểu diễn khóa và độ phân nhánh**, không nhất thiết là chiều cao BST.

Ý tưởng **không sửa nút cũ** và **dùng lại nhánh không thay đổi** vẫn giống path copying trên BST.

### 20.3. Persistent rope hoặc cây dãy

Rope lưu văn bản thành các khối/chuỗi ở nút lá và có thể lưu độ dài cây con tại các nút trong. Khi chèn một đoạn ở một vị trí:

- Tìm lá theo độ dài các nhánh.
- Tạo các nút/khối mới tại nơi chèn.
- Dựng lại đường đi và tái cân bằng nếu cần.
- Chia sẻ nhiều khối văn bản không thay đổi.

Nếu giá trị của một nút lá là một **mảng mutable**, nó phải được xử lý theo quy tắc bất biến (copy-on-write, immutable chunk) trước khi chia sẻ.

### 20.4. Persistent treap

Treap ngẫu nhiên có thể dùng các phép `split` và `merge` theo phong cách thuần:

- Mỗi lời gọi trả nút mới thay vì ghi con trỏ cũ.
- Các cây con không đi vào đường sửa được chia sẻ.
- Priority thường giữ nguyên cho các nút tương ứng.
- Nếu có thẻ lazy, việc `push` phải **sao chép nút cần đẩy thẻ**, không sửa nút dùng chung.

Thời gian đường đi kỳ vọng có thể logarit dưới giả thiết priority thích hợp, nhưng treap có trường hợp xấu nhất chiều cao tuyến tính. Không được sao chép máy móc thuật toán treap mutating rồi tuyên bố persistent.

### 20.5. Persistent B-tree/B+ tree

Với dữ liệu lớn, có thể sao chép **các trang (page)** trên đường từ lá tới gốc và chia sẻ các trang khác. Ý tưởng cùng họ với path copying nhưng đơn vị sao chép là **khối/trang chứa nhiều khóa**, không phải một nút nhị phân.

Chọn đơn vị sao chép phụ thuộc môi trường:

- RAM và đối tượng nhỏ.
- Đĩa/SSD và kích thước trang I/O.
- Cache, kích thước khối và chi phí cấp phát.
- Yêu cầu lưu bền, giao dịch và đồng thời.

**Path copying là mô thức tổng quát**, còn cách cân bằng và bảo trì từng cấu trúc phải được chứng minh riêng.

## 21. Khi nào nên chọn path copying, khi nào nên chọn cách khác?

### 21.1. Những trường hợp path copying có lợi

- Cần giữ nhiều **snapshot phiên bản**.
- Muốn undo/redo hoặc lịch sử rẽ nhánh.
- Cần nhiều truy vấn đọc không muốn bị thay đổi trạng thái nền.
- Mỗi cập nhật chỉ ảnh hưởng một **đường hẹp** trong cấu trúc.
- Có thể tận dụng các cây con bất biến dùng chung.
- Hệ thống chấp nhận cấp phát nút mới thay vì sửa tại chỗ.

### 21.2. Những trường hợp cần cân nhắc

- Không cần bản cũ: cấu trúc mutable có thể dùng ít bộ nhớ và ít cấp phát hơn.
- Cập nhật rất nhiều khóa và mỗi lần giữ mọi phiên bản mãi: số nút giữ lại có thể tăng đáng kể.
- Payload lớn hoặc khả biến: phải giải quyết **sở hữu dữ liệu** và sao chép sâu khi cần.
- Môi trường đòi hỏi độ trễ cấp phát rất thấp: tạo nhiều nút nhỏ có thể gây áp lực lên allocator/GC.
- Dữ liệu nằm trên đĩa: cần cấu trúc phân trang và cơ chế commit phù hợp.
- Có nhu cầu sửa đồng thời nhiều bản ghi như một giao dịch: cần cơ chế giao dịch bên ngoài path copying.

### 21.3. Path copying so với copy-on-write

Hai thuật ngữ liên quan nhưng không hoàn toàn đồng nghĩa:

- **Path copying:** chủ động dựng **một đường nút mới** khi thực hiện cập nhật; cách nào phải được sao chép là một phần của thuật toán.
- **Copy-on-write (COW):** chính sách “nếu muốn sửa dữ liệu đang được chia sẻ, tạo bản riêng trước khi sửa”. Nó có thể được áp dụng cho nút, trang hoặc khối lớn.

Path copying trên cây bất biến là một cách tổ chức theo **tinh thần COW**, nhưng không phải mọi hệ thống COW đều có cấu trúc cây hay chi phí `O(\log n)`.

### 21.4. Path copying so với event sourcing

Event sourcing giữ **chuỗi các sự kiện** và tái dựng trạng thái từ sự kiện hoặc checkpoint. Path copying giữ **các gốc snapshot** với cấu trúc được chia sẻ.

Hai kỹ thuật có thể kết hợp:

- Sự kiện giải thích **vì sao dữ liệu thay đổi**.
- Persistent tree giữ **trạng thái truy vấn được tại từng phiên bản**.
- Hệ thống có thể lưu một số checkpoint theo chính sách tài nguyên.

Nhưng path copying bản thân **không ghi log sự kiện, không lưu bền xuống đĩa và không cung cấp audit log**.

## 22. Các lỗi cài đặt và hiểu nhầm thường gặp

1. **Sao chép gốc rồi sửa nút con tại chỗ.** Các phiên bản vẫn dùng chung con, nên bản cũ có thể đổi.
2. **Gọi mọi shallow copy là persistence.** Phải kiểm soát **mọi nút và payload** được chia sẻ.
3. **Sao chép toàn bộ cây mỗi lần** rồi cho đó là chi phí bắt buộc. Path copying chỉ cần đường ảnh hưởng.
4. **Chỉ sao chép nút lá bị sửa** nhưng không sao chép tổ tiên để nối đường mới tới gốc.
5. **Quên trả/gán gốc mới** từ hàm cập nhật thuần, nên ứng dụng vẫn đọc bản cũ.
6. **Dùng `==` thay `is` để kết luận chia sẻ nút.** Bằng giá trị không có nghĩa là cùng đối tượng.
7. **Thay `key` tại chỗ trong BST** rồi chỉ tính lại metadata. Khóa mới có thể phá thứ tự.
8. **Cho rằng chỉ có `value` đổi thì phải xoay.** Nếu hình dạng không đổi, AVL không cần xoay.
9. **Không tạo nút mới cho metadata** ở tổ tiên, khiến tổng/size của phiên bản mới sai.
10. **Gọi hàm `pull` mutating vào nút được chia sẻ.** Trường size/sum/height của bản cũ bị ghi đè.
11. **Tái sử dụng phép xoay AVL khả biến** trong persistent AVL. Xoay có thể sửa nút bản cũ.
12. **Xoay trái nhưng chỉ tạo gốc `y'`, không tạo bản sao `x'`.** Nút `x` cũ cần liên kết con khác.
13. **Tính metadata của gốc mới từ một nút con có trường cũ.** Phải dựng nút thấp hơn trước nút gốc mới.
14. **Quên xử lý xoay kép** khi AVL gặp cấu hình trái–phải/phải–trái.
15. **Dùng chiều cao lá `0`, cây rỗng `0` mà không đổi công thức.** Quy ước height phải nhất quán.
16. **Xóa nút hai con rồi chỉ chép khóa kế nhiệm, không chép trọng số.** Bản ghi khóa–giá trị bị ghép sai.
17. **Quên con phải của nút kế nhiệm** khi xóa nút nhỏ nhất trong cây phải.
18. **Tháo liên kết của nút kế nhiệm cũ** để “di chuyển” nó. Bản cũ có thể đang dùng nút ấy.
19. **Không tái cân bằng đường đi sau khi xóa** vì chỉ chèn mới nghĩ tới AVL.
20. **Xóa khóa không tồn tại nhưng vẫn dựng lại toàn bộ đường** dù có thể trả nguyên nút cũ.
21. **Coi ID phiên bản mới luôn đồng nghĩa với gốc vật lý khác.** No-op có thể giữ cùng root.
22. **Chỉ lưu một biến `root` hiện hành** rồi quên lưu bản cũ trong khi vẫn muốn truy vấn phiên bản trước.
23. **Giữ `parent` trực tiếp trong nút chia sẻ.** Một nút có thể có cha khác nhau theo phiên bản.
24. **Chia sẻ một `list` payload rồi cho rằng `frozen=True` đóng băng nội dung list.** Bất biến bề mặt không phải bất biến sâu.
25. **Để mã ngoài có quyền ghi trực tiếp vào những nút đã công bố.** Dễ phá mọi bản đang dùng chung.
26. **Gọi hàm đọc có cache mutable trong nút mà không kiểm soát** sự thay đổi trạng thái chia sẻ.
27. **Nhầm cây DAG của nhiều phiên bản với chu trình lỗi trong một phiên bản.** Hai gốc được phép chia sẻ; mỗi gốc vẫn phải dẫn tới một cây hợp lệ.
28. **Cho rằng chia sẻ làm bộ nhớ của mỗi phiên bản bằng `O(1)`.** Một cập nhật thật vẫn có thể tạo `O(h)` nút.
29. **Cho rằng `O(h)` luôn là `O(\log n)`.** BST suy biến có `h=\Theta(n)`.
30. **Gán bảo đảm xấu nhất AVL cho treap ngẫu nhiên.** Treap thường có bảo đảm kỳ vọng theo priority.
31. **Cho rằng cập nhật hai khóa luôn chỉ tạo đúng một đường mới.** Hai khóa có thể tạo những đường khác nhau; có thể cần batch để chia sẻ tổ tiên.
32. **Không định nghĩa khóa trùng.** Cài đặt bài này chọn khóa phân biệt, `put` thay giá trị nếu đã có.
33. **Bỏ qua độ phức tạp của số nguyên lớn hoặc đối tượng payload.** Big-O số học giả định thao tác cơ bản có chi phí hằng.
34. **Giữ toàn bộ gốc phiên bản vô hạn** mà không có chính sách giải phóng, rồi tưởng GC tự thu hết.
35. **Bỏ một gốc và nghĩ tất cả nút nó dùng sẽ bị giải phóng.** Nút được chia sẻ còn sống nếu gốc khác vẫn trỏ tới.
36. **Tưởng immutable tree tự cung cấp lưu bền sau mất điện.** Cần lớp storage/serialization/commit riêng.
37. **Tưởng immutable tree tự cung cấp transaction đa luồng.** Vẫn cần công bố root và đồng bộ metadata ngoài cây.
38. **Chỉ kiểm kết quả phiên bản mới mà không đọc lại phiên bản cũ.** Dễ bỏ sót mutation vô ý trên nút dùng chung.
39. **Chỉ kiểm tổng ở gốc mà bỏ metadata các cây con.** Rank/sum theo khoảng có thể sai dù tổng toàn cây đúng.
40. **Gọi validator `O(n)` sau mọi cập nhật trong benchmark** rồi tuyên bố cập nhật chỉ `O(\log n)`.
41. **Dùng kết quả `items()` để chứng minh có chia sẻ cấu trúc.** Hai cây khác nhau hoàn toàn có thể cho cùng danh sách; cần kiểm identity.
42. **Sử dụng đệ quy sâu mà bỏ qua giới hạn stack.** BST không cân bằng có thể gây tràn stack.
43. **Thay giá trị gốc mà không kiểm tra kiểu/payload.** Trọng số khả biến có thể phá semantics cũ.
44. **Nhầm một lịch sử rẽ nhánh với một thứ tự phiên bản duy nhất.** ID tăng theo thời gian tạo không bắt buộc biểu diễn quan hệ cha–con.
45. **Cho rằng path copying giữ mọi iterator mutable cũ hợp lệ.** Iterator dạng con trỏ cha hoặc offset có thể phụ thuộc một root/phiên bản cụ thể.
46. **Lưu nhiều bản nhưng không nêu phiên bản đầu vào của truy vấn.** Kết quả truy vấn có thể khác giữa các phiên bản; API phải rõ.

## 23. Bài tập thực hành có đáp án

### Bài 1. Xác định đường đi cần sao chép

Cho BST:

```text
        40
       /  \
     20    60
    /  \   / \
   10  30 50 70
```

Sửa trọng số của khóa `30`. Những nút nào nằm trên đường cần dựng lại?

**Đáp án:** Đường `40→20→30`. Bản mới cần nút mới tương ứng `30'`, `20'`, `40'` trong trường hợp không xoay.

### Bài 2. Các cây con được chia sẻ

Trong Bài 1, những nút/cây con có thể giữ nguyên đối tượng?

**Đáp án:** Nút `10` và toàn bộ cây con gốc `60` (các nút `60,50,70`), vì chúng không thuộc đường sửa trọng số khóa `30`.

### Bài 3. Sao chép toàn cây với bảy nút

Nếu sao chép toàn bộ cây ở Bài 1, cần tạo bao nhiêu nút mới?

**Đáp án:** **`7`** nút. Path copying khi chỉ đổi trọng số `30`, không xoay, tạo **`3`** nút.

### Bài 4. Tại sao sao chép nông gốc không đủ?

Nếu tạo gốc mới nhưng giữ `new_root.left is old_root.left` rồi sửa trực tiếp `new_root.left.value`, chuyện gì xảy ra?

**Đáp án:** Gốc cũ cũng tham chiếu tới **cùng nút trái**. Giá trị trong phiên bản cũ bị thay đổi, phá persistence.

### Bài 5. Chèn khóa chưa có

Ở cây Bài 1, chèn khóa `25`. Đường tìm kiếm và các nút mới khi không xoay?

**Đáp án:** Đường `40→20→30→None` ở nhánh trái của `30`. Tạo nút `25` rồi các bản mới `30'`, `20'`, `40'`.

### Bài 6. Xóa lá

Trong cây Bài 1, xóa khóa `10`. Những nút nào cần dựng lại nếu không xoay?

**Đáp án:** Trả `None` tại vị trí con trái của `20`; tạo bản mới `20'` và `40'`. Nút `10` vẫn tồn tại trong phiên bản cũ.

### Bài 7. Xóa nút có một con

Nếu nút `10` chỉ có con phải `15`, xóa `10` có cần sao chép nguyên cây `15` không?

**Đáp án:** **Không.** Trả chính nút `15` bất biến làm cây con thay thế và dựng lại các tổ tiên bị ảnh hưởng.

### Bài 8. Xóa nút có hai con

Trong cây:

```text
     40
    /  \
   20   60
       /  \
      50   70
```

Xóa `40` bằng kế nhiệm inorder. Khóa thay thế là gì?

**Đáp án:** **`50`**, khóa nhỏ nhất trong cây con phải. Phải xóa `50` ở vị trí cũ trên **phiên bản mới**, không sửa cây con cũ.

### Bài 9. Kế nhiệm có con phải

Một nút kế nhiệm không có con trái nhưng có con phải. Khi lấy kế nhiệm ra khỏi cây, cây con còn lại là gì?

**Đáp án:** **Chính con phải của kế nhiệm**. Nếu bỏ luôn con phải sẽ làm mất dữ liệu.

### Bài 10. Giữ payload khi xóa nút hai con

Kế nhiệm có `key=50,value=500`, nút cần xóa có `key=40,value=400`. Nút thay thế phải có dữ liệu nào?

**Đáp án:** **`(50,500)`**, không phải `(50,400)`. Khóa và giá trị thuộc cùng một bản ghi.

### Bài 11. No-op update

Nếu `put(root,30,3)` được gọi khi khóa `30` đã có trọng số `3`, bản triển khai tối ưu có cần cấp phát nút không?

**Đáp án:** **Không.** Có thể trả lại nguyên root. Bộ quản lý vẫn có thể gán một **ID phiên bản mới** cho cùng root.

### Bài 12. Xóa khóa không tồn tại

Một persistent BST hợp lệ không có khóa `999`. Kết quả về identity của `delete(root,999)` có thể như thế nào?

**Đáp án:** **Có thể là chính `root` cũ**, vì dữ liệu không đổi và không cần xây lại đường đi.

### Bài 13. Chặn trên số nút sao chép

Một BST cao `h` (tính theo số cạnh) có thể đi qua tối đa bao nhiêu nút trên một đường gốc–lá?

**Đáp án:** **`h+1`** nút. Cập nhật một trọng số trong BST không xoay cần nhiều nhất một nút mới mỗi tầng đường đi.

### Bài 14. Chiều cao AVL

Với `n` nút, chiều cao AVL có chặn trên bậc nào?

**Đáp án:** **`O(\log(n+1))`**. Vì vậy chi phí path copying cho một cập nhật đơn khóa có thể được chặn worst-case ở bậc logarit.

### Bài 15. BST suy biến

Nếu cây là một chuỗi dài `n` nút, path copying một khóa cuối chuỗi có thể tạo bao nhiêu nút mới?

**Đáp án:** **`\Theta(n)`** trong trường hợp thay trọng số tại khóa cuối, vì phải dựng lại gần toàn bộ đường đi.

### Bài 16. Trường nào phục vụ AVL?

Trong `height,size,subtree_sum`, trường nào trực tiếp phục vụ quyết định xoay AVL?

**Đáp án:** **`height`**. `size` phục vụ thứ hạng, `subtree_sum` phục vụ tổng theo khoảng; cả ba vẫn phải đúng trên mỗi nút mới.

### Bài 17. Metadata khi cập nhật trọng số

Nút có trọng số `4` thay thành `40`. Những metadata nào trong `height,size,subtree_sum` có thể đổi nếu cấu trúc không đổi?

**Đáp án:** **`subtree_sum`** ở nút đó và các tổ tiên tăng thêm `36`; `height` và `size` không đổi.

### Bài 18. Xoay trái thuần

Phép xoay trái có dạng:

```text
    x              y'
   / \            /  \
  A   y    →     x'   C
     / \        / \
    B   C      A   B
```

Những nút nào cần được tạo mới để không sửa `x,y` cũ?

**Đáp án:** Ít nhất các nút đại diện vị trí mới **`x'` và `y'`**. Các cây con bất biến `A,B,C` có thể được chia sẻ.

### Bài 19. Thứ tự tính metadata sau xoay

Vì sao phải tạo `x'` trước `y'` trong phép xoay trái thuần?

**Đáp án:** `y'` nhận `x'` làm con, nên metadata của `y'` cần đọc metadata **đã đúng của `x'`**. `make_node` tính từ các con.

### Bài 20. Cây con dùng chung có thể có hai cha

Tại sao không nên đặt trường `parent` đơn lẻ trong nút bất biến đang được hai phiên bản chia sẻ?

**Đáp án:** Nút đó có thể nằm dưới **hai nút cha khác nhau** ở hai phiên bản. Một trường parent duy nhất không thể đúng cho cả hai; nên truy vết từ root phiên bản.

### Bài 21. Phiên bản rẽ nhánh

Từ `V0` tạo `V1=put(V0,30,300)` và `V2=put(V0,25,25)`. `V2` có bắt buộc mang cập nhật trọng số ở `V1` không?

**Đáp án:** **Không.** `V2` lấy **V0** làm đầu vào, nên giữ trọng số `30` của V0 và chỉ chèn thêm `25`.

### Bài 22. Snapshot không đổi

Một phiên bản `V0` được giữ nguyên root. Sau khi tạo `V1` bằng cập nhật thuần, đọc `V0` phải trả gì?

**Đáp án:** **Dữ liệu như trước cập nhật**, vì không nút cũ nào bị thay đổi; các nhánh dùng chung đều bất biến.

### Bài 23. Tổng trọng số các phiên bản

Phiên bản gốc có trọng số `1,2,3,4,5,6,7`. Thay trọng số `3` thành `300` trong bản mới. Tổng bản cũ và mới?

**Đáp án:** Bản cũ **`28`**. Bản mới **`28-3+300=325`**.

### Bài 24. Nhánh chèn khóa mới

Cũng từ bản cũ có tổng `28`, tạo nhánh khác bằng chèn khóa mới với trọng số `25`. Tổng nhánh mới?

**Đáp án:** **`53`**. Nhánh ấy không nhận thay đổi `3→300` của nhánh khác.

### Bài 25. Xóa trên nhánh đã cập nhật

Nhánh có tổng `325`, xóa một khóa có trọng số `6`. Tổng mới?

**Đáp án:** **`319`**. Phiên bản có tổng `325` vẫn tồn tại nếu root của nó được giữ.

### Bài 26. Tổng bộ nhớ qua U cập nhật

Một phiên bản cơ sở có `n_0` nút; giữ `V` gốc và thực hiện `U` cập nhật đơn khóa trên các AVL có tối đa `N` nút. Chặn trên số nút/đầu mục bộ nhớ?

**Đáp án:** **`O(n_0+V+U\log(N+1))`** dưới các giả thiết trong bài. Các cây con dùng chung chỉ chiếm bộ nhớ một lần.

### Bài 27. Khi bỏ một root

Nếu bỏ `root_A` nhưng một cây con của nó vẫn được `root_B` tham chiếu, cây con ấy có thể được giải phóng ngay không?

**Đáp án:** **Không.** Nó vẫn còn reachable từ `root_B`; chỉ giải phóng khi không còn tham chiếu giữ nó sống và cơ chế quản lý bộ nhớ cho phép.

### Bài 28. Payload khả biến

Một nút frozen chứa `value=[1,2]`, sau đó mã ngoài gọi `value.append(3)`. Persistence có còn đúng theo ngữ nghĩa không?

**Đáp án:** **Không.** Frozen chỉ chặn gán lại trường, không ngăn list được tham chiếu thay đổi. Cần đóng băng hoặc sao chép payload.

### Bài 29. Đọc phiên bản cần cấp phát bao nhiêu nút mới?

Một hàm `get(version,key)` chỉ đi xuống nút bất biến mà không sửa gì. Nó cần cấp phát bao nhiêu nút cây?

**Đáp án:** **`0`**. Chi phí thời gian vẫn theo đường tìm kiếm `O(h+1)`.

### Bài 30. Xác minh chia sẻ bằng Python

Muốn kiểm tra cây con phải gốc được dùng chung giữa hai phiên bản, nên dùng `old_root.right == new_root.right` hay `old_root.right is new_root.right`?

**Đáp án:** Dùng **`is`** để kiểm tra hai tham chiếu trỏ tới **cùng đối tượng vật lý**.

### Bài 31. Cập nhật một khóa vs nhiều khóa

Nếu cần sửa `q` khóa, cách đơn giản dùng persistent AVL là gì? Có bắt buộc là phương án ít nút mới nhất không?

**Đáp án:** Áp dụng `q` lần cập nhật thuần liên tiếp trên các gốc tạm và chỉ công bố gốc cuối. **Không nhất thiết tối ưu nút mới**, vì các đường đi có thể chung tổ tiên; có thể thiết kế batch update riêng.

### Bài 32. Undo bằng root

Nếu giữ `V0→V1→V2`, để undo từ `V2` về `V1` có phải chạy thuật toán xóa/chèn ngược không?

**Đáp án:** **Không.** Chỉ cần chọn lại root của **V1**, miễn là root ấy vẫn được giữ.

### Bài 33. Persistence có tự bảo đảm transaction không?

Nếu hai luồng cùng ghi vào một danh sách phiên bản mutable mà không đồng bộ, việc nút là immutable có đủ bảo đảm commit đúng không?

**Đáp án:** **Không.** Cần đồng bộ/công bố root và các thông tin quản lý phiên bản phù hợp. Bất biến nút không tự bảo đảm transaction hay linearizability.

### Bài 34. So với persistent segment tree

Điểm chung cốt lõi giữa cập nhật một khóa trong persistent BST và cập nhật một ô trong persistent segment tree là gì?

**Đáp án:** **Tạo đường nút mới từ vị trí cập nhật về gốc**, tính lại tóm tắt, chia sẻ các cây con không thay đổi và giữ root cũ để truy vấn.

### Bài 35. Chứng minh tính đúng

Để chứng minh một thao tác path copying đúng, cần chỉ ra ít nhất ba điều gì?

**Đáp án:** (1) **Không sửa bất kỳ nút nào của phiên bản cũ**; (2) cây mới có **đúng dữ liệu sau thao tác** và giữ bất biến BST/cân bằng; (3) metadata ở các nút mới được **tính đúng từ cây con**. Sau đó có thể suy ra các phiên bản trước vẫn không đổi theo quy nạp.

## 24. Checklist triển khai path copying

Trước khi dùng trong một hệ thống thực tế, hãy xác minh:

- [ ] Định nghĩa rõ kiểu phiên bản: chỉ đọc bản cũ hay có thể rẽ nhánh từ bản cũ.
- [ ] Mỗi phiên bản được xác định bằng **root**, không phải chỉ một số nhãn không có tham chiếu dữ liệu.
- [ ] Nút và payload được chia sẻ đều bất biến theo hợp đồng API.
- [ ] Hàm cập nhật trả **gốc mới**, không sửa liên kết hoặc metadata của nút cũ.
- [ ] Khi sửa một khóa, chỉ các đường có thể bị ảnh hưởng được dựng lại; các cây con còn lại dùng chung.
- [ ] Nếu thao tác không đổi nội dung, hàm có thể trả nguyên root để tránh cấp phát.
- [ ] Chèn khóa mới giữ thứ tự BST; khóa trùng có chính sách rõ.
- [ ] Xóa lá/một con/hai con đều bảo toàn dữ liệu và không bỏ mất cây con của kế nhiệm.
- [ ] Nếu cây có tái cân bằng, **phép xoay là thuần**, tạo nút mới và tính metadata theo đúng thứ tự.
- [ ] Metadata như `height/size/subtree_sum` đúng tại **mọi nút mới**.
- [ ] Chiều cao cây nền được phân tích; không áp `O(\log n)` cho BST suy biến.
- [ ] API truy vấn nhận đúng gốc hoặc ID phiên bản.
- [ ] Bộ quản lý phiên bản có chính sách giữ/bỏ root và giới hạn bộ nhớ.
- [ ] Có cơ chế đồng bộ khi nhiều luồng cùng phát hành phiên bản.
- [ ] Validator kiểm tra BST, chiều cao, metadata và chu trình trong **từng phiên bản**.
- [ ] Bộ kiểm thử đọc lại **các bản cũ** sau chuỗi cập nhật và so sánh với snapshot tham chiếu.
- [ ] Đã xem xét đệ quy, bộ nhớ cấp phát, GC và chi phí payload đối với dữ liệu thực tế.

## 25. Tổng kết

**Sao chép đường đi (*path copying*)** là một phương pháp căn bản để tạo cấu trúc dữ liệu **persistent**: thay vì sửa các nút của phiên bản cũ, mỗi lần cập nhật một khóa tạo những nút mới trên đường bị ảnh hưởng, giữ nguyên các cây con còn lại và trả **một gốc phiên bản mới**.

Cốt lõi của thiết kế là ba bất biến:

1. **Cấu trúc theo khóa:** cây mới và cây cũ đều giữ thứ tự BST.
2. **Nút bất biến:** không nút nào đã thuộc bản cũ bị sửa tại chỗ, kể cả metadata, con trỏ và payload dùng chung.
3. **Gốc phiên bản:** mỗi bản được truy cập qua một root riêng; các root có thể chia sẻ nhiều nút mà không thay đổi nội dung của nhau.

Với một BST có chiều cao `h`, cập nhật đơn khóa có thể dùng **`O(h+1)` thời gian và nút mới**. Nếu dùng **persistent AVL** bảo đảm `h=O(\log(n+1))`, ta có **`O(\log(n+1))` thời gian và bộ nhớ cấp phát thêm cho một cập nhật** theo mô hình thao tác cơ bản, thay vì sao chép `\Theta(n)` nút của cả cây.

Kỹ thuật này áp dụng cho chèn, cập nhật trọng số, xóa (kể cả nút có hai con) và cân bằng cây, miễn là **mọi phép tái cấu trúc như xoay đều được viết theo phong cách thuần**. Metadata phục vụ truy vấn như `size` và `subtree_sum` phải được tính từ những cây con đã đúng khi tạo nút mới.

Giữ nhiều root cho phép **đọc lịch sử, undo/redo và rẽ nhánh phiên bản** với **chia sẻ cấu trúc**. Đổi lại, hệ thống phải quản lý số phiên bản, quyền sở hữu payload, vòng đời bộ nhớ và cơ chế phát hành snapshot nếu có nhiều luồng hoặc yêu cầu giao dịch.

Điểm cần nhớ nhất: **chỉ chia sẻ những gì sẽ không bị sửa**. Sao chép đường đi không phải sao chép nông tùy ý, và sự đúng đắn không nằm ở việc gốc cũ và gốc mới khác nhau, mà ở chỗ **mọi nút mà hai gốc có thể cùng nhìn thấy đều giữ nguyên nội dung**. Đó là nền tảng để xây dựng các phiên bản cấu trúc dữ liệu vừa tiết kiệm tài nguyên vừa bảo toàn trạng thái lịch sử.

# Tìm phần tử theo hạng và tính hạng của một khóa

## 1. Đặt vấn đề: không chỉ tìm theo khóa mà còn hỏi “đứng thứ mấy?”

Một cây tìm kiếm nhị phân (*binary search tree*, BST) thường được dùng để tìm khóa, chèn hoặc xóa theo khóa. Nhưng nhiều bài toán còn cần trả lời:

- **Phần tử nhỏ thứ `k` là gì?** Ví dụ: giao dịch có giá trị nhỏ thứ 100, điểm trung vị trong bảng điểm hoặc sản phẩm đứng thứ 5 theo giá.
- **Có bao nhiêu phần tử nhỏ hơn khóa `x`?** Ví dụ: điểm 82 đứng sau bao nhiêu điểm khác, một mức giá có bao nhiêu đơn hàng thấp hơn.
- **Khóa `x` đứng ở hạng nào?** Nếu có nhiều phần tử cùng khóa, phải hiểu là **vị trí xuất hiện đầu tiên, cuối cùng hay một quy tắc khác**.
- **Có bao nhiêu phần tử nằm trong khoảng `[a,b]`?** Có thể tính bằng hiệu hai phép hỏi hạng.

Một BST bình thường chỉ biết khóa của từng nút và hai con, nên có thể phải duyệt nhiều nút để **đếm**. Để giải quyết nhanh, ta **tăng cường** (*augment*) mỗi nút bằng thông tin **số phần tử trong cây con**.

```text
        BST thông thường                   BST tăng cường

                5                             5 (size=8)
              /   \                          /           \
             3     7               3 (size=3)          7 (size=4)
            /       \             /                       \
           2        10         2 (size=1)                10 (size=1)

Ở ví dụ tăng cường, khóa 3 xuất hiện 2 lần, khóa 7 xuất hiện 3 lần.
Size đếm SỐ LẦN XUẤT HIỆN, không chỉ số nút khác nhau.
```

Nhờ có `size` của từng cây con, ta không cần duyệt toàn bộ cây mỗi lần hỏi hạng: chỉ cần đi theo **một đường từ gốc xuống**, cộng số phần tử của những cây con có thể bỏ qua.

**Chủ đề bài học:** xây dựng và sử dụng *order-statistic tree* — cây tìm kiếm hỗ trợ **select theo hạng** và **rank theo khóa** — từ bất biến đếm cây con, tới thao tác cân bằng và các trường hợp khóa trùng.

### Mục tiêu học tập

Sau bài này, bạn sẽ có thể:

1. Phát biểu rõ **hạng 1-based** và **hạng 0-based**, phân biệt “nhỏ hơn” với “nhỏ hơn hoặc bằng”.
2. Dùng bất biến `size(x)=size(left)+count(x)+size(right)` để chọn phần tử thứ `k`.
3. Tính `rank_lt(key)`, `rank_le(key)` và hạng đầu/cuối khi khóa trùng.
4. Giải thích tại sao `select` và `rank` có độ phức tạp `O(h)` với `h` là chiều cao cây.
5. Duy trì kích thước cây con sau **insert**, **delete** và **rotation** trên cây cân bằng.
6. Hiểu vì sao dữ liệu tăng cường chỉ dùng kích thước cây con thì vẫn cập nhật được bằng thông tin cục bộ.
7. Cài một **AVL tree tăng cường** có khóa trùng bằng Python, kèm thao tác thêm, xóa, chọn theo hạng, đếm hạng và kiểm tra bất biến.
8. So sánh với mảng đã sắp xếp, Fenwick tree, segment tree và các cấu trúc khác theo miền khóa cùng tần suất cập nhật.

Đây là bài của chương **Cây tăng cường** trong học phần **Cấu trúc dữ liệu**. Chủ đề liên hệ trực tiếp với mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị: ta học cách duy trì bất biến và phân tích **thời gian/bộ nhớ** để chọn cấu trúc phù hợp từng dạng truy vấn.

## 2. Chốt quy ước hạng trước khi viết thuật toán

“Hạng của khóa `x`” có thể mang nhiều nghĩa. Để không bị lỗi lệch một đơn vị, bài này dùng các khái niệm sau.

Giả sử dãy đã sắp tăng, **tính cả các giá trị lặp lại**:

```text
Giá trị:       2   3   3   5   7   7   7   10
Hạng 1-based:  1   2   3   4   5   6   7    8
Chỉ số 0-based:0   1   2   3   4   5   6    7
```

### 2.1. Select: lấy phần tử theo hạng

`select(k)`, với **`k` bắt đầu từ 1**, trả phần tử có hạng `k` trong thứ tự tăng:

```text
select(1) = 2
select(3) = 3
select(4) = 5
select(6) = 7
select(8) = 10
```

Chỉ có `1\le k\le n` là hợp lệ, với `n` là **tổng số lần xuất hiện**. Nếu muốn dạng 0-based, định nghĩa riêng `select0(i)=select(i+1)`, hợp lệ khi `0\le i<n`.

### 2.2. Rank nhỏ hơn nghiêm ngặt

`rank_lt(x)` (*less than*) là **số phần tử có khóa nhỏ hơn `x`**:

\[
\boxed{rank_{<}(x)=|\{a:a<x\}|}.
\]

Với dãy trên:

```text
rank_lt(2)  = 0
rank_lt(3)  = 1
rank_lt(5)  = 3
rank_lt(7)  = 4
rank_lt(6)  = 4   # 6 không có trong dãy vẫn tính được.
rank_lt(11) = 8
```

Giá trị `rank_lt(x)` cũng chính là **vị trí chèn 0-based của `x` ở phía trước các giá trị bằng `x`** (*lower bound*).

### 2.3. Rank nhỏ hơn hoặc bằng

`rank_le(x)` (*less than or equal*) là **số phần tử có khóa không lớn hơn `x`**:

\[
\boxed{rank_{\le}(x)=|\{a:a\le x\}|}.
\]

Ví dụ:

```text
rank_le(3) = 3
rank_le(7) = 7
rank_le(6) = 4
```

`rank_le(x)` cũng là **vị trí chèn 0-based sau các phần tử bằng `x`** (*upper bound*).

### 2.4. Hạng của khóa khi có trùng lặp

Nếu `x` có mặt, **các hạng 1-based chứa `x`** là:

\[
\boxed{[\,rank_{<}(x)+1,\ rank_{\le}(x)\,]}
\]

theo khoảng hai đầu **đều bao gồm**. Với `x=7`, các hạng là `5,6,7` — không thể nói “hạng của `7` là 5” mà không giải thích rằng ta lấy **lần xuất hiện đầu tiên**.

Nếu `x` **không tồn tại**, `rank_lt(x)` và `rank_le(x)` vẫn là các số đếm có nghĩa, nhưng **không có hạng của phần tử `x` đang tồn tại**. Khi đó hai giá trị bằng nhau.

## 3. Bất biến tăng cường: kích thước của cây con

Với BST chỉ chứa **mỗi khóa phân biệt trong một nút**, có thể lưu:

```text
node.key
node.left
node.right
node.size
```

Trong đó:

\[
\boxed{size(node)=1+size(node.left)+size(node.right)}.
\]

Quy ước `size(None)=0`.

Khi ứng dụng cho phép **khóa trùng**, ta sẽ dùng một nút cho mỗi **khóa phân biệt** và lưu `count` là số lần khóa ấy xuất hiện:

```text
node.key       # Khóa duy nhất của nút này.
node.count     # Số phần tử bằng key.
node.size      # Số phần tử tính cả các bản sao trong cây con.
node.left
node.right
```

Bất biến khi đó là:

\[
\boxed{size(node)=size(node.left)+count(node)+size(node.right)}.
\]

Ngoài bất biến `size`, cây còn phải giữ:

- **BST-order:** mọi khóa ở cây con trái **nhỏ hơn** `key`; mọi khóa ở cây con phải **lớn hơn** `key`.
- **`count(node)\ge1`** với mọi nút tồn tại.
- Nếu dùng AVL hoặc red-black tree, còn phải giữ bất biến **cân bằng** của cấu trúc ấy.

Nhờ `count`, ta không cần đặt ba nút có khóa `7` vào những vị trí khác nhau để biểu diễn ba lần xuất hiện.

### Size là số nút hay số phần tử?

Có hai cách thiết kế hợp lệ nhưng không được trộn:

| Thiết kế | Ý nghĩa `size` | Khóa lặp |
|---|---|---|
| BST không lặp | Số nút trong cây con | Không cho phép hoặc tạo ID phụ |
| BST đa tập với `count` | **Tổng số lần xuất hiện** trong cây con | Gộp những khóa bằng nhau vào một nút |

Trong bài này, **`size` đếm số lần xuất hiện**. Nếu có `u` khóa phân biệt và tổng `n` phần tử, cây có **`u` nút**, nhưng `size(root)=n`.

## 4. Mô hình cây minh họa có khóa trùng

Xét đa tập:

```text
S = [2, 3, 3, 5, 7, 7, 7, 10]
```

Một BST hợp lệ là:

```text
                          key=5, count=1, size=8
                           /                 \
           key=3, count=2, size=3       key=7, count=3, size=4
                 /                              \
      key=2, count=1, size=1            key=10, count=1, size=1
```

Kiểm tra từ dưới lên:

```text
size(2)  = 1
size(10) = 1
size(3)  = size(2) + count(3) + size(None)
         = 1 + 2 + 0 = 3
size(7)  = 0 + 3 + 1 = 4
size(5)  = 3 + 1 + 4 = 8
```

**Chỉ cần biết kích thước cây con trái và số bản sao tại nút**, ta có thể xác định hạng của chính nút ấy trong thứ tự tăng.

Với một nút `v`:

\[
L=size(v.left),\qquad C=count(v).
\]

Trong **thứ tự của riêng cây con gốc `v`**, các phần tử có khóa `v.key` chiếm các hạng từ **`L+1` đến `L+C`**.

Mọi phần tử ở cây trái đứng **trước**, mọi phần tử ở cây phải đứng **sau**. Đây là quan sát làm nên cả hai thuật toán select và rank.

## 5. SELECT: tìm phần tử có hạng k

**Đầu vào:** gốc cây `root` và một hạng `k` **1-based**, hợp lệ `1\le k\le size(root)`.

Tại nút `v`:

1. Đặt `L=size(v.left)`, `C=count(v)`.
2. Nếu `k\le L`, phần tử cần tìm nằm trong **cây trái**.
3. Nếu `L<k\le L+C`, phần tử cần tìm chính là **khóa của `v`**.
4. Nếu `k>L+C`, phần tử ở **cây phải**; bỏ qua `L+C` phần tử đứng trước nó, rồi tìm với hạng mới `k'=k-L-C`.

### Mã giả

```text
SELECT(v, k):                 # k là hạng 1-based.
    require v != null
    require 1 <= k <= v.size

    while v != null:
        L = size(v.left)
        C = v.count

        if k <= L:
            v = v.left
        else if k <= L + C:
            return v.key
        else:
            k = k - L - C
            v = v.right

    error "Inconsistent tree sizes"
```

### Vì sao không cần duyệt các nút đã bỏ qua?

Nếu `k>L+C`, toàn bộ cây trái và tất cả bản sao tại nút hiện tại **đều chắc chắn đứng trước** phần tử hạng `k`. Bất biến `size` cho biết chính xác số lượng ấy. Ta có thể trừ ngay `L+C` thay vì lần lượt duyệt từng phần tử.

Mỗi vòng lặp đi xuống **một tầng**. Với chiều cao `h`:

\[
\boxed{T_{\mathrm{select}}=O(h)}.
\]

Nếu cây được giữ cân bằng ở mức `h=O(\log u)` với `u` khóa phân biệt, select mất **`O(\log(u+1))`**; vì `u\le n`, cũng thường viết `O(\log(n+1))`.

## 6. Theo dõi SELECT từng bước trên cây mẫu

Cây có gốc `5`, cây trái size `3` và `count(5)=1`.

### Tìm phần tử hạng 6

```text
select(6) trên cây 8 phần tử:

Nút 5:
    L = 3, C = 1
    6 > 3+1  -> đi phải, k = 6 - 4 = 2

Nút 7:
    L = 0, C = 3
    0 < 2 <= 3 -> kết quả: 7
```

Chỉ qua **hai nút**, dù cây biểu diễn tám lần xuất hiện.

### Tìm phần tử hạng 3

```text
Nút 5: L=3, C=1
    3 <= 3 -> đi trái, giữ k=3

Nút 3: L=1, C=2
    1 < 3 <= 3 -> kết quả: 3
```

### Tìm phần tử hạng 8

```text
Nút 5: k=8 -> phải, k=4
Nút 7: L=0, C=3 -> phải, k=1
Nút 10: L=0, C=1 -> kết quả: 10
```

**Cẩn thận:** khi rẽ sang **cây trái**, `k` giữ nguyên; khi rẽ sang **cây phải**, mới trừ kích thước cây trái cộng số lần xuất hiện tại nút.

## 7. RANK: có bao nhiêu phần tử nhỏ hơn khóa x?

Phép `rank_lt(x)` không cần `x` tồn tại trong cây. Nó chỉ đếm các phần tử có khóa **`<x`**.

Tại nút `v`:

- Nếu `x\le v.key`: nút hiện tại và mọi khóa cây phải đều **không nhỏ hơn `x`**; đi **trái** mà không cộng thêm.
- Nếu `x>v.key`: mọi phần tử trong cây trái cùng `count(v)` bản sao tại nút đều **nhỏ hơn `x`**; cộng `size(left)+count(v)` rồi đi **phải**.

### Mã giả

```text
RANK_LT(root, x):
    answer = 0
    v = root

    while v != null:
        if x <= v.key:
            v = v.left
        else:
            answer += size(v.left) + v.count
            v = v.right

    return answer
```

### Theo dõi rank_lt(7)

```text
S = [2, 3, 3, 5, 7, 7, 7, 10]

Nút 5:
    7 > 5 -> cộng size(trái)=3 và count(5)=1
    answer = 4
    đi phải tới 7

Nút 7:
    7 <= 7 -> đi trái (rỗng), không cộng

Kết quả: rank_lt(7) = 4
```

### Theo dõi rank_lt(6), dù 6 không có trong cây

```text
Nút 5: 6 > 5, cộng 3+1=4, đi phải tới 7
Nút 7: 6 <= 7, đi trái (rỗng)
Kết quả: rank_lt(6) = 4
```

Đây là lý do phép hỏi hạng theo **khóa tìm kiếm** rất hữu dụng: ngay cả khi không thấy khóa, ta vẫn tính được **số phần tử nhỏ hơn** và **vị trí chèn hợp lệ**.

## 8. RANK_LE, đếm khóa bằng nhau và khoảng hạng

Để đếm **nhỏ hơn hoặc bằng**, chỉ cần thay điều kiện nhánh:

```text
RANK_LE(root, x):
    answer = 0
    v = root

    while v != null:
        if x < v.key:
            v = v.left
        else:
            answer += size(v.left) + v.count
            v = v.right

    return answer
```

Với dãy mẫu:

```text
rank_lt(7) = 4
rank_le(7) = 7
count(7) = rank_le(7) - rank_lt(7) = 3
```

Vậy các công thức hữu ích:

\[
\boxed{count(x)=rank_{\le}(x)-rank_{<}(x)}.
\]

\[
\boxed{first\_rank(x)=rank_{<}(x)+1}
\quad\text{nếu }count(x)>0.
\]

\[
\boxed{last\_rank(x)=rank_{\le}(x)}
\quad\text{nếu }count(x)>0.
\]

Nếu `count(x)=0` thì `first_rank` và `last_rank` của **một phần tử đang tồn tại** là không xác định; ứng dụng có thể trả `None` hoặc ném lỗi. Không nên trả `rank_lt(x)+1` và nói đó là hạng của một phần tử thực sự có mặt.

### Đếm số phần tử trong khoảng

Với `a\le b`, khoảng đóng `[a,b]`:

\[
\boxed{count_{[a,b]}=rank_{\le}(b)-rank_{<}(a)}.
\]

Khoảng nửa kín `[a,b)`:

\[
\boxed{count_{[a,b)}=rank_{<}(b)-rank_{<}(a)}.
\]

Ví dụ `[3,7]` trong dãy mẫu có `2` bản sao của `3`, `1` số `5` và `3` bản sao của `7`, tổng `6`:

```text
rank_le(7) - rank_lt(3) = 7 - 1 = 6
```

Hai lời gọi rank đều `O(h)`, nên truy vấn đếm khoảng vẫn **`O(h)`** theo bậc độ phức tạp.

## 9. RANK của một nút đã biết và RANK theo khóa không giống nhau hoàn toàn

Trong nhiều tài liệu về **order-statistic tree**, `OS-RANK(T,x)` nhận **con trỏ tới một nút `x` có thật**, không phải khóa tìm kiếm. Với BST không có khóa trùng, có thể tính hạng 1-based từ nút ấy bằng cách đi **ngược qua các cha**:

```text
RANK_OF_NODE(x):           # BST không có khóa trùng.
    r = size(x.left) + 1
    y = x

    while y.parent != null:
        if y is right child of y.parent:
            r += size(y.parent.left) + 1
        y = y.parent

    return r
```

Vì sao cộng khi đi lên từ **con phải**? Khi một nút nằm trong cây con phải của cha, thì **tất cả** phần tử ở cây con trái của cha cùng chính cha đều đứng trước nó.

### Nếu dùng `count` cho nhiều bản sao

Ta có thể định nghĩa hạng của **lần xuất hiện đầu tiên** tại nút `x`:

```text
r = size(x.left) + 1

Khi đi lên từ con phải của một cha p:
    r += size(p.left) + p.count
```

Khoảng hạng của các bản sao nằm tại nút là `[r,r+x.count-1]`.

Trong thực tế, nếu đã có **khóa `key`** và cần số phần tử nhỏ hơn, có thể dùng trực tiếp `rank_lt(key)` đi từ gốc xuống, không cần con trỏ `parent`. Nếu có handle và cần hạng của một nút, thuật toán đi qua cha cũng `O(h)`, nhưng phải duy trì đúng parent pointers sau insert/delete/rotation.

**Điểm cần ghi rõ trong API:** `rank_key(x)` có thể định nghĩa được cho khóa không tồn tại; `rank_of_node(handle)` thì yêu cầu handle hợp lệ thuộc cây.

## 10. SELECT và RANK có phải hai phép nghịch đảo?

Trong **cây không có khóa trùng**, hai phép gần như nghịch đảo:

\[
\boxed{rank_{<}(select(k))=k-1},\qquad 1\le k\le n.
\]

Với **khóa trùng**, kết luận trên **không đúng cho mọi `k`**, vì nhiều hạng khác nhau có thể cho cùng khóa.

Ví dụ:

```text
select(5) = 7
select(6) = 7
select(7) = 7
rank_lt(7) = 4
```

Trong cả ba trường hợp, `rank_lt(select(k))=4` chứ không lần lượt là `4,5,6`.

Đẳng thức đúng cho đa tập là:

\[
\boxed{
rank_{<}(select(k))<k\le rank_{\le}(select(k))
}
\]

với mọi `1\le k\le n`.

Một cặp quan hệ nữa:

- Nếu khóa `x` **có tồn tại**, `select(rank_lt(x)+1)=x`.
- Nếu `x` **không tồn tại**, vị trí `rank_lt(x)+1` là **vị trí chèn giả định 1-based**, không đảm bảo `select` tại vị trí ấy trả `x`.

Những tính chất này rất hữu dụng khi viết **property-based tests** cho order-statistic tree.

## 11. Khóa trùng: chọn chính sách trước khi cài

BST có thể xử lý khóa trùng theo nhiều cách:

| Chính sách | Cách biểu diễn | Ảnh hưởng hạng |
|---|---|---|
| **Tập hợp** (*set*) | Mỗi khóa tối đa một nút, chèn trùng không đổi | Hạng tính theo các khóa phân biệt |
| **Đa tập** (*multiset*) bằng `count` | Một nút cho mỗi khóa, lưu số lần xuất hiện | Hạng tính theo **tổng số lần xuất hiện** |
| **Khóa ghép `(key,id)`** | Mỗi phần tử có khóa thứ tự duy nhất | Mỗi bản ghi có một hạng riêng |
| **Dồn khóa trùng về trái/phải** | Nhiều nút có cùng khóa | Rotation và bất biến so sánh phải được thiết kế rất cẩn thận |

Bài này chọn **multiset với `count`**. Các nút trái và phải luôn có khóa **nghiêm ngặt** nhỏ/lớn hơn khóa cha. Vì vậy, rotation của cây cân bằng không khiến các bản sao của một khóa bị rải ra nhiều vị trí.

### Khi cần phân biệt các đối tượng cùng khóa

Ví dụ, hai học sinh cùng điểm 85 nhưng cần chọn **đúng học sinh thứ `k`**, thay vì chỉ trả về `85`. Khi ấy `count=2` không đủ để xác định ID của học sinh ở hạng đó.

Có thể dùng:

\[
K=(score,unique\_sequence)
\]

và mỗi nút có khóa ghép duy nhất; `size` khi đó tính số **bản ghi**, không cần `count>1`. Hoặc lưu danh sách đối tượng trong nút trùng khóa và định nghĩa rõ hạng nội bộ.

**Tính hạng theo khóa đơn thuần** và **lấy một bản ghi cụ thể theo hạng** là hai hợp đồng khác nhau.

## 12. Cân bằng cây quyết định chi phí thực tế

Việc tăng cường `size` **không tự cân bằng BST**.

Nếu chèn các khóa tăng dần vào BST thường:

```text
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

Chiều cao có thể là `h=\Theta(n)`. `select` hoặc `rank` có thể phải đi qua gần như tất cả nút, nên cũng có thể mất `O(n)`.

Nếu dùng cây cân bằng như **AVL** hoặc **red-black tree**, số nút trên một đường gốc–lá là `O(\log u)`, với `u` khóa phân biệt. Ta giữ được:

\[
\boxed{T_{\mathrm{select}}=T_{\mathrm{rank}}=O(\log(u+1))}.
\]

Tương tự cho insert/delete nếu cấu trúc bảo trì đầy đủ bất biến `size` và cân bằng.

### Sự khác nhau giữa n và u

- `n`: tổng số lần xuất hiện trong multiset.
- `u`: số **khóa phân biệt**, tức số nút thật.
- `1\le u\le n` khi cây không rỗng.

Khi toàn bộ một triệu phần tử đều bằng `7`, cây count-based có **một nút** với `count=1.000.000`. Các truy vấn có thể `O(1)` theo chiều cao cây, dù `n` rất lớn.

## 13. Giữ size khi INSERT

Khi chèn một bản sao của khóa `x`:

1. Tìm `x` theo quy tắc BST.
2. Nếu khóa đã có, **tăng `count` của nút ấy lên một**.
3. Nếu chưa có, tạo một nút `count=1,size=1` tại vị trí lá thích hợp.
4. Trên đường đi ngược lên, tính lại:

\[
size(v)=size(v.left)+count(v)+size(v.right).
\]

5. Nếu là AVL/red-black tree, thực hiện các bước cân bằng; **mọi rotation phải cập nhật size của các nút bị đổi liên kết**.

### Ví dụ

Ban đầu:

```text
              5 (size=5, count=1)
             / \
       3(size=2)  7(size=2)
         /          \
        2           10
```

Chèn một bản sao của `7`:

- `count(7):1\to2`.
- `size(7):2\to3`.
- `size(5):5\to6`.
- Không tạo nút mới, hình dạng cây giữ nguyên.

Chèn khóa mới `8`:

- Tạo nút `8` theo quy tắc BST ở cây con bên phải.
- Cập nhật size các tổ tiên dọc đường chèn.
- Nếu có rotation để cân bằng, tính lại size cho các nút đổi chỗ.

**Đừng quên một nút chứa khóa trùng có thể tăng size mà không tăng chiều cao.**

## 14. Rotation không đổi tập phần tử nhưng làm đổi size của từng nút

Các cây cân bằng thường sửa hình dạng bằng **rotation**.

### Xoay trái

```text
Trước xoay trái tại x:            Sau xoay:

         x                             y
        / \                           / \
       A   y                         x   C
          / \                       / \
         B   C                     A   B
```

Tập khóa theo thứ tự vẫn là `A, x, B, y, C`, nên **thứ tự và tổng số phần tử không đổi**. Nhưng những cây con gốc `x` và `y` **đã đổi phạm vi**.

Với nút mang số lần xuất hiện `count`:

Sau xoay:

\[
\begin{aligned}
size(x)&=size(A)+count(x)+size(B),\\
size(y)&=size(x)+count(y)+size(C).
\end{aligned}
\]

Thứ tự cập nhật **rất quan trọng**: sau khi sửa các con trỏ, tính lại `size(x)` **trước**, rồi mới tính `size(y)`.

### Mã giả xoay trái

```text
ROTATE_LEFT(x):
    y = x.right
    B = y.left

    y.left = x
    x.right = B

    RECALCULATE(x)      # size/height của nút thấp hơn.
    RECALCULATE(y)      # size/height của gốc mới.
    return y
```

Xoay phải đối xứng: tính lại nút vừa đi xuống trước, rồi tính gốc mới.

**Sai lầm điển hình:** chỉ cập nhật chiều cao AVL hoặc màu red-black mà quên `size`. Cây vẫn có thể tìm theo khóa đúng nhưng trả **rank/select sai**.

## 15. DELETE là tình huống dễ làm sai số đếm

Xóa một bản sao của khóa `x` có hai trường hợp lớn.

### 15.1. Nút có count lớn hơn 1

Chỉ cần:

```text
count(x) -= 1
recalculate size on ancestors
```

Nút vẫn ở cây. Số phần tử toàn cây giảm một, nhưng số **nút phân biệt** có thể không đổi.

### 15.2. Nút có count bằng 1

Phải **xóa nút vật lý** theo quy tắc BST:

- Nút không có con: bỏ nút.
- Nút có một con: nối con thay nút.
- Nút có **hai con**: có thể lấy **nút kế tiếp theo thứ tự** (*inorder successor*, nhỏ nhất ở cây phải) thế chỗ.

### Lưu ý đặc biệt khi successor có count lớn hơn 1

Giả sử nút `x` cần xóa có hai con; successor `s` có `count(s)=3`.

Nếu chỉ copy `s.key` sang `x` rồi **giảm count của s từ 3 xuống 2**, cây sẽ có **hai nút cùng khóa s**, phá chính sách “một khóa ở một nút” và dễ làm sai các công thức rank.

Cách đúng cho cài đặt count-based:

1. **Gỡ nguyên nút successor `s`** khỏi cây con phải, bao gồm toàn bộ `count(s)` bản sao.
2. **Chuyển cả `s.key` và `s.count`** lên nút đang thay thế `x`.
3. Cập nhật `size` và cân bằng trên các đường bị ảnh hưởng.

Tổng số lần xuất hiện của toàn cây **giảm đúng một**: bản sao duy nhất của `x` bị xóa, còn tất cả bản sao của `s` vẫn tồn tại nhưng đã được chuyển vị trí.

Đây là một lỗi không dễ phát hiện nếu chỉ kiểm tra tìm khóa mà không kiểm tra cả `size` lẫn cấu trúc đa tập.

## 16. Mã Python hoàn chỉnh: AVL tree tăng cường hỗ trợ multiset

Đoạn mã sau độc lập, không dùng thư viện cây ngoài. Ta chọn **AVL** để có chiều cao `O(\log u)` trong trường hợp xấu nhất và thêm một trường `size` để hỗ trợ order statistics.

### Hợp đồng của lớp

- Khóa là **số nguyên**, có thứ tự so sánh chuẩn.
- Mỗi khóa phân biệt được lưu trong một nút `Node`.
- `count` là số bản sao, `size` là tổng bản sao trong cây con.
- `select(k)` dùng hạng **1-based** và ném `IndexError` khi ngoài `[1,n]`.
- `rank_lt(x)`, `rank_le(x)` trả **số phần tử**, kể cả khi `x` không tồn tại.
- `remove(x)` xóa **một** bản sao và ném `KeyError` nếu không có `x`.
- `first_rank(x)` và `last_rank(x)` trả `None` nếu không tồn tại.
- Không hỗ trợ truy cập đồng thời không đồng bộ.

### 16.1. Định nghĩa nút và bảo trì metadata

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Node:
    key: int
    count: int = 1
    height: int = 1
    size: int = 1
    left: Node | None = None
    right: Node | None = None


def height(node: Node | None) -> int:
    return 0 if node is None else node.height


def size(node: Node | None) -> int:
    return 0 if node is None else node.size


def recalc(node: Node) -> None:
    node.height = 1 + max(height(node.left), height(node.right))
    node.size = size(node.left) + node.count + size(node.right)


def balance_factor(node: Node) -> int:
    return height(node.left) - height(node.right)
```

`height` phục vụ cân bằng AVL; `size` phục vụ hạng. Cả hai đều được tính từ hai con và metadata tại nút.

### 16.2. Rotation và rebalance

Các hàm sau tiếp tục dùng `Node`, `height`, `size`, `recalc` và `balance_factor` ở trên:

```python
def rotate_right(y: Node) -> Node:
    x = y.left
    assert x is not None
    middle = x.right

    x.right = y
    y.left = middle

    recalc(y)  # Nút đi xuống.
    recalc(x)  # Gốc mới.
    return x


def rotate_left(x: Node) -> Node:
    y = x.right
    assert y is not None
    middle = y.left

    y.left = x
    x.right = middle

    recalc(x)  # Nút đi xuống.
    recalc(y)  # Gốc mới.
    return y


def rebalance(node: Node) -> Node:
    recalc(node)
    bf = balance_factor(node)

    if bf > 1:  # Lệch trái.
        assert node.left is not None
        if balance_factor(node.left) < 0:
            node.left = rotate_left(node.left)
        return rotate_right(node)

    if bf < -1:  # Lệch phải.
        assert node.right is not None
        if balance_factor(node.right) > 0:
            node.right = rotate_right(node.right)
        return rotate_left(node)

    return node
```

`rebalance` xử lý bốn mẫu cân bằng AVL: **LL, RR, LR, RL**. Với các nút đổi vị trí sau rotation, `size` và `height` đều được cập nhật lại theo thứ tự từ dưới lên.

### 16.3. Insert và delete, kể cả successor có count lớn

```python
def insert_node(node: Node | None, key: int) -> Node:
    if node is None:
        return Node(key)

    if key < node.key:
        node.left = insert_node(node.left, key)
    elif key > node.key:
        node.right = insert_node(node.right, key)
    else:
        node.count += 1
        recalc(node)
        return node

    return rebalance(node)


def detach_min(node: Node) -> tuple[Node | None, Node]:
    """Gỡ TOÀN BỘ nút nhỏ nhất và trả (gốc mới, nút đã gỡ)."""
    if node.left is None:
        return node.right, node

    node.left, smallest = detach_min(node.left)
    return rebalance(node), smallest


def delete_node(node: Node | None, key: int) -> Node | None:
    if node is None:
        raise KeyError(key)

    if key < node.key:
        node.left = delete_node(node.left, key)
    elif key > node.key:
        node.right = delete_node(node.right, key)
    else:
        if node.count > 1:
            node.count -= 1
            recalc(node)
            return node

        if node.left is None:
            return node.right
        if node.right is None:
            return node.left

        # Hai con: đưa CẢ key và count của successor lên.
        node.right, successor = detach_min(node.right)
        node.key = successor.key
        node.count = successor.count

    return rebalance(node)
```

**Điểm quan trọng:** `detach_min` lấy **toàn bộ nút nhỏ nhất**, không phải một bản sao. Nếu successor có `count>1`, ta chuyển cả `count` lên nút thay thế. Cách này giữ mỗi khóa phân biệt tại đúng một nút và làm kích thước toàn cây giảm đúng một sau `delete_node`.

### 16.4. Lớp OrderStatisticAVL và các truy vấn

```python
class OrderStatisticAVL:
    def __init__(self) -> None:
        self.root: Node | None = None

    def __len__(self) -> int:
        return size(self.root)

    def add(self, key: int) -> None:
        self.root = insert_node(self.root, key)

    def remove(self, key: int) -> None:
        self.root = delete_node(self.root, key)

    def count(self, key: int) -> int:
        node = self.root
        while node is not None:
            if key < node.key:
                node = node.left
            elif key > node.key:
                node = node.right
            else:
                return node.count
        return 0

    def select(self, k: int) -> int:
        """Phần tử hạng k (1-based, tính cả bản sao)."""
        if not 1 <= k <= len(self):
            raise IndexError("Hạng k nằm ngoài [1, len(tree)]")

        node = self.root
        while node is not None:
            left_count = size(node.left)
            if k <= left_count:
                node = node.left
            elif k <= left_count + node.count:
                return node.key
            else:
                k -= left_count + node.count
                node = node.right

        raise RuntimeError("Metadata size không nhất quán")

    def select0(self, index: int) -> int:
        """Phần tử tại vị trí 0-based."""
        return self.select(index + 1)

    def rank_lt(self, key: int) -> int:
        """Số phần tử có khóa < key."""
        answer = 0
        node = self.root
        while node is not None:
            if key <= node.key:
                node = node.left
            else:
                answer += size(node.left) + node.count
                node = node.right
        return answer

    def rank_le(self, key: int) -> int:
        """Số phần tử có khóa <= key."""
        answer = 0
        node = self.root
        while node is not None:
            if key < node.key:
                node = node.left
            else:
                answer += size(node.left) + node.count
                node = node.right
        return answer

    def first_rank(self, key: int) -> int | None:
        if self.count(key) == 0:
            return None
        return self.rank_lt(key) + 1

    def last_rank(self, key: int) -> int | None:
        if self.count(key) == 0:
            return None
        return self.rank_le(key)

    def count_closed(self, low: int, high: int) -> int:
        """Số phần tử trong đoạn đóng [low, high]."""
        if low > high:
            return 0
        return self.rank_le(high) - self.rank_lt(low)

    def check_invariants(self) -> bool:
        """Kiểm tra toàn cây, O(u); thích hợp cho debug/test."""
        def walk(
            node: Node | None,
            low: int | None,
            high: int | None,
        ) -> tuple[int, int]:
            if node is None:
                return 0, 0  # (size, height)

            assert node.count >= 1
            assert low is None or low < node.key
            assert high is None or node.key < high

            left_size, left_height = walk(node.left, low, node.key)
            right_size, right_height = walk(node.right, node.key, high)

            expected_size = left_size + node.count + right_size
            expected_height = 1 + max(left_height, right_height)

            assert node.size == expected_size
            assert node.height == expected_height
            assert abs(left_height - right_height) <= 1
            return expected_size, expected_height

        try:
            total, _ = walk(self.root, None, None)
            return total == len(self)
        except AssertionError:
            return False
```

Mã được trình bày thành bốn khối **theo thứ tự định nghĩa** để dễ đọc; ghép bốn khối đó vào **cùng một tệp Python** là có đủ định nghĩa cần thiết. Đây là mã học thuật minh họa, **chưa được thực thi như một bước kiểm thử dự án** trong phạm vi biên soạn tài liệu.

## 17. Ví dụ sử dụng lớp AVL tăng cường

```python
tree = OrderStatisticAVL()

for key in [7, 3, 10, 5, 7, 2, 3, 7]:
    tree.add(key)

assert len(tree) == 8
assert tree.check_invariants()

all_keys = [tree.select(k) for k in range(1, len(tree) + 1)]
print(all_keys)
# [2, 3, 3, 5, 7, 7, 7, 10]

print(tree.select(6))          # 7
print(tree.select0(0))         # 2
print(tree.rank_lt(7))         # 4
print(tree.rank_le(7))         # 7
print(tree.count(7))           # 3
print(tree.first_rank(7))      # 5
print(tree.last_rank(7))       # 7

print(tree.rank_lt(6))         # 4: 6 không tồn tại.
print(tree.first_rank(6))      # None
print(tree.count_closed(3, 7)) # 6

tree.remove(7)                 # Xóa MỘT bản sao của 7.
assert tree.count(7) == 2
assert len(tree) == 7
assert tree.check_invariants()

tree.remove(5)                 # Xóa nút có thể có hai con.
assert len(tree) == 6
assert tree.check_invariants()

print([tree.select(k) for k in range(1, len(tree) + 1)])
# [2, 3, 3, 7, 7, 10]
```

### Những gì ví dụ kiểm tra

- `size(root)` phải bằng **tổng số lần xuất hiện**, không phải số khóa phân biệt.
- `select` có thể trả cùng khóa ở nhiều hạng.
- `rank_lt` vẫn có ý nghĩa nếu khóa chưa xuất hiện.
- `remove` một bản sao chỉ giảm `count` trước khi cần xóa nút vật lý.
- `check_invariants` xác nhận **BST-order, count, size, height và cân bằng AVL** sau cập nhật.

Không nên gọi `check_invariants()` sau **mỗi** thao tác trong đường chạy hiệu năng cao: hàm duyệt toàn bộ `u` nút nên mất `O(u)`, làm mất lợi thế cập nhật `O(\log u)`.

## 18. Chứng minh đúng đắn của SELECT

Ta có thể chứng minh bằng **bất biến vòng lặp**.

Khi `select` đang ở nút `v` với hạng mục tiêu `k`:

> Phần tử cần tìm có hạng `k` trong dãy đã sắp của **cây con gốc `v`**.

**Khởi đầu:** tại gốc, `k` chính là hạng cần tìm của toàn cây, nên bất biến đúng.

**Duy trì:**

- Nếu `k\le L`, phần tử nằm trong dãy đã sắp của cây trái, vẫn là hạng `k` ở cây trái.
- Nếu `L<k\le L+C`, khóa của nút `v` xuất hiện ở đúng vị trí cần tìm, thuật toán trả đáp án.
- Nếu `k>L+C`, bỏ đi đúng `L+C` phần tử chắc chắn đứng trước mục cần tìm; phần tử có hạng `k-(L+C)` trong cây phải.

**Kết thúc:** tại một nút có `L<k\le L+C`, trả `v.key`. Vì bất biến được giữ, đó chính là khóa ở hạng gốc ban đầu.

Mỗi lần chưa trả đáp án, thuật toán đi xuống **một cây con thực sự nhỏ hơn**, nên kết thúc sau tối đa `h` bước nếu metadata và đầu vào hợp lệ.

## 19. Chứng minh đúng đắn của RANK_LT

Duy trì biến `answer`:

> `answer` bằng số phần tử **nhỏ hơn `x`** nằm trong các phần cây mà thuật toán đã quyết định **bỏ qua hoàn toàn**.

Ở nút `v`:

- Nếu `x\le v.key`, nút hiện tại và mọi phần tử cây phải **không nhỏ hơn `x`**; không cộng, chỉ cần khám phá cây trái.
- Nếu `x>v.key`, toàn bộ cây trái và `count(v)` bản sao tại nút đều **nhỏ hơn `x`**; cộng chính xác `size(left)+count(v)` và tiếp tục cây phải.

Khi con trỏ đi tới `None`, không còn phần chưa xét. Khi đó `answer` bằng tổng số phần tử khóa `<x` trong cây.

Đối với `rank_le`, đổi bất đẳng thức tương ứng để tính `\le x`. Cách cộng số lượng vẫn đúng vì BST-order là nghiêm ngặt giữa các nút phân biệt.

**Độ phức tạp:** một nút mỗi tầng và cộng số nguyên hằng số lần, `O(h)` thời gian, `O(1)` bộ nhớ phụ cho phiên bản lặp (không tính cây).

## 20. Phân tích thời gian và bộ nhớ

Gọi `u` là số khóa phân biệt, `n` là số lần xuất hiện và `h` là chiều cao cây.

| Thao tác | BST có size nhưng không cân bằng | AVL có size/count |
|---|---|---|
| `select(k)` | `O(h)`, xấu nhất `O(u)` | `O(\log(u+1))` |
| `rank_lt(x)` / `rank_le(x)` | `O(h)` | `O(\log(u+1))` |
| `count(x)` | `O(h)` | `O(\log(u+1))` |
| `first_rank` / `last_rank` | `O(h)` | `O(\log(u+1))` |
| `count_closed(a,b)` | `O(h)` | `O(\log(u+1))` |
| `add(x)` | `O(h)` nếu bảo trì size | `O(\log(u+1))` |
| `remove(x)` | `O(h)` nếu bảo trì size | `O(\log(u+1))` |
| `check_invariants()` toàn cây | `O(u)` | `O(u)` |
| Bộ nhớ lưu cây | `O(u)` nút | `O(u)` nút |

**Không nhầm:** `count` có thể lưu nhiều bản sao trong một nút, nên bộ nhớ cây thường `O(u)` thay vì phải có một nút cho **mỗi** lần xuất hiện. Nếu lưu cả ID/payload riêng cho từng bản sao, phần lưu payload vẫn có thể cần `O(n)`.

### Bộ nhớ tạm thời của mã Python

- `select` và `rank` viết dạng `while`: `O(1)` biến phụ.
- `insert` và `delete` của ví dụ AVL dùng đệ quy: ngăn xếp `O(\log(u+1))` nhờ cây cân bằng.
- Các phép xoay chỉ thay một số con trỏ/metadata: `O(1)` công việc và bộ nhớ ngoài lời gọi.

Nếu triển khai có nhiều khóa rất lớn, phép so sánh khóa có thể không còn `O(1)` theo kích thước biểu diễn. Cận trên mặc định mô hình so sánh khóa hằng số.

## 21. Vì sao augmentation này tương thích với rotation?

Ta muốn mỗi phép xoay, vốn là công cụ sửa cân bằng của AVL/red-black, không phải duyệt cả cây để tính lại metadata.

Với `size`, giá trị của một nút chỉ phụ thuộc vào:

\[
(\text{size của con trái},\text{count tại nút},\text{size của con phải}).
\]

Một phép xoay chỉ đổi **một số liên kết cục bộ**. Khi những cây con `A,B,C` không thay đổi bên trong, chỉ cần tính lại `size` ở các nút `x,y` trực tiếp tham gia xoay.

```text
Trước:         x                   Sau:          y
              / \                               / \
             A   y                             x   C
                / \                           / \
               B   C                         A   B
```

Sau xoay trái:

```text
recalc(x)
recalc(y)
```

Không phải cập nhật từng nút của `A,B,C`, vì số phần tử **bên trong các cây con ấy không đổi**.

Điều này là mẫu thiết kế phổ biến của **cây tăng cường**: chọn metadata có thể kết hợp từ các con trong `O(1)`, sau đó bảo trì nó trên đường insert/delete và trong các rotation. Các augmentation khác như **tổng cây con**, **min/max cây con**, hoặc **độ dài đoạn con** cũng khai thác tư duy tương tự, tùy yêu cầu.

## 22. Phân vị, trung vị và k-th lớn nhất

### 22.1. Trung vị

Với `n` phần tử:

- Nếu `n` lẻ: trung vị là `select((n+1)/2)`.
- Nếu `n` chẵn: hai phần tử giữa là `select(n/2)` và `select(n/2+1)`; **trung vị số học** thường lấy trung bình hai giá trị nếu kiểu số và ứng dụng cho phép.

Ví dụ dãy mẫu tám phần tử:

```text
[2,3,3,5,7,7,7,10]
select(4)=5
select(5)=7
median=(5+7)/2=6
```

### 22.2. K-th lớn nhất

Nếu chỉ cần lấy **khóa lớn thứ `k`**, với `1\le k\le n`:

\[
\boxed{kth\_largest(k)=select(n-k+1)}.
\]

Với `n=8`:

```text
K-th lớn nhất k=1: select(8)=10
K-th lớn nhất k=2: select(7)=7
K-th lớn nhất k=4: select(5)=7
```

### 22.3. Phân vị

Phân vị có nhiều định nghĩa thống kê (nearest-rank, nội suy, xử lý biên). Nếu dùng quy tắc **nearest rank** cho `p\in(0,1]`:

\[
quantile_p=select(\lceil pn\rceil).
\]

Đây **không phải định nghĩa duy nhất** của percentile. Khi tích hợp với thư viện thống kê hoặc báo cáo nghiệp vụ, phải ghi rõ quy tắc làm tròn/nội suy để tránh lệch kết quả.

Một cây tăng cường cho phép cập nhật dữ liệu rồi hỏi `select` nhiều lần, phù hợp khi tập phần tử **thay đổi liên tục**.

## 23. So sánh với mảng đã sắp xếp

Nếu tất cả `n` khóa đã ở trong một **mảng tăng dần**, một số thao tác thậm chí đơn giản hơn:

| Thao tác | Mảng đã sắp | AVL với size |
|---|---|---|
| Chọn phần tử hạng `k` | `O(1)` bằng `A[k-1]` | `O(\log u)` |
| Tìm `rank_lt(x)` | `O(\log n)` bằng binary search/lower_bound | `O(\log u)` |
| Tìm `rank_le(x)` | `O(\log n)` bằng upper_bound | `O(\log u)` |
| Chèn/xóa một mục ở giữa | `O(n)` do dịch chuyển | `O(\log u)` |
| Bộ nhớ | `O(n)` ô liên tiếp | `O(u)` nút kèm con trỏ/metadata |
| Locality | Tốt, liên tiếp | Phụ thuộc vị trí cấp phát nút |

Ví dụ Python dùng `bisect`:

```python
from bisect import bisect_left, bisect_right

data = [2, 3, 3, 5, 7, 7, 7, 10]

print(data[5])                 # 7: select(6) 1-based.
print(bisect_left(data, 7))    # 4: rank_lt(7).
print(bisect_right(data, 7))   # 7: rank_le(7).
print(bisect_right(data, 7) - bisect_left(data, 7))  # 3.
```

**Nếu dữ liệu chủ yếu tĩnh:** mảng đã sắp thường là lựa chọn đơn giản và rất nhanh cho `select`/`rank`. **Nếu chèn/xóa thường xuyên ở vị trí bất kỳ:** cây cân bằng tăng cường tránh phải dịch chuyển `O(n)` ô mỗi lần.

## 24. So sánh với Fenwick tree và segment tree

Nếu khóa là **số nguyên trong miền nhỏ hoặc có thể nén tọa độ**, ta có thể lưu **tần suất theo khóa** rồi hỏi tổng tiền tố.

### 24.1. Fenwick tree (Binary Indexed Tree)

Cho `freq[v]` là số lần khóa `v` xuất hiện:

\[
rank_{<}(x)=\sum_{v<x}freq[v].
\]

Fenwick tree hỗ trợ:

- Cộng hoặc trừ một đơn vị tần suất tại một vị trí: `O(\log U)`.
- Tổng tiền tố: `O(\log U)`.
- Tìm thứ tự `k` theo tổng tần suất (binary lifting trên cây Fenwick): `O(\log U)` với các tần suất **không âm**.

Với miền số nguyên `0,\ldots,U-1`, bộ nhớ thường `O(U)`. Nếu `U` rất lớn nhưng chỉ có `u` khóa xuất hiện, có thể **nén tọa độ** xuống `u` vị trí — với lưu ý cần biết hoặc quản lý tập khóa sẽ cập nhật.

### 24.2. Segment tree

Lưu tổng tần suất trong mỗi đoạn của miền khóa:

- `rank_lt(x)`: truy vấn tổng miền nhỏ hơn `x`.
- `select(k)`: bắt đầu từ gốc, xem tổng tần suất đoạn trái; rẽ trái hoặc trừ rồi rẽ phải.
- Chèn/xóa một khóa: cập nhật số đếm của lá tương ứng, rồi cập nhật tổng các đoạn tổ tiên.

Độ phức tạp thường `O(\log U)` cho mỗi thao tác, với bộ nhớ `O(U)` trong cách lưu cây đoạn đầy đủ trên miền đã biết.

### 24.3. Khi nào tree theo khóa phù hợp hơn BST tăng cường?

| Tình huống | Cấu trúc đáng cân nhắc |
|---|---|
| Khóa số nguyên trong miền nhỏ cố định | Fenwick/segment tree |
| Có danh sách mọi khóa trước khi chạy, cập nhật nhiều | Nén tọa độ + Fenwick |
| Khóa thay đổi linh hoạt, không biết hết miền | Cây cân bằng với `size` |
| Muốn thêm augmentation khác trên khóa linh hoạt | BST cân bằng tăng cường |
| Chỉ truy vấn tĩnh trên mảng đã sắp | Mảng + binary search |

**Lưu ý nén tọa độ động:** nếu có một khóa mới chưa xuất hiện trong bảng nén, không thể luôn chèn nó vào “giữa” các chỉ số Fenwick có sẵn mà vẫn giữ cùng trật tự với chi phí `O(\log U)` đơn giản. Có thể cần **xây lại mapping** hoặc dùng một cấu trúc động phù hợp.

## 25. Treap và red-black tree cũng có thể tăng cường size

Ví dụ cài đặt chọn **AVL** để có một giải pháp tự chứa, nhưng nguyên tắc `size(left)+count+size(right)` không phụ thuộc riêng AVL.

### Red-black tree

Red-black tree duy trì độ cao `O(\log u)` nhờ màu và các phép xoay. Thêm `size` vào từng nút, cập nhật khi đi qua đường chèn/xóa và khi xoay, ta có **order-statistic red-black tree**. Hai phép `select`/`rank` vẫn đi một đường nên `O(\log u)`.

### Treap

Treap kết hợp **BST-order trên key** với **heap-order trên một priority ngẫu nhiên**. Nếu thứ tự priority được sinh với giả định thích hợp, chiều cao có kỳ vọng `O(\log u)`. Thêm `size` và cập nhật trong split/merge/rotation cho phép `select`/`rank` với **thời gian kỳ vọng `O(\log u)`**, không tự nhiên là cận xấu nhất.

### Khi nào không nên dùng BST chưa cân bằng?

Nếu đầu vào có thể đối kháng hoặc gần như tăng dần, một BST thường có thể thành danh sách liên kết, khiến `select` và `rank` suy giảm tới `O(u)`. Có `size` thôi **không giải quyết** điều này.

## 26. Những lỗi thường gặp và cách tránh

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Lấy hạng 0-based nhưng dùng mã select 1-based | Lệch một phần tử hoặc báo lỗi | Ghi rõ `select(k)` bắt đầu từ `1` |
| Viết `size=1+left+right` dù nút có `count>1` | Bỏ qua các bản sao | Dùng `size=left+count+right` |
| Gọi `rank_lt(x)` là “hạng của x” dù x không có | Nhầm vị trí chèn với hạng thực | Phân biệt số đếm và `first_rank` |
| Không phân biệt `<x` với `\le x` | Sai ở khóa trùng và biên khoảng | Dùng hai API `rank_lt`, `rank_le` |
| Khi đi sang cây phải trong select không trừ `L+C` | Chọn sai vị trí | `k -= size(left)+count` |
| Khi đi sang cây trái lại trừ `L` | Làm mất vị trí trong cây trái | Giữ nguyên `k` |
| Sau rotation chỉ sửa height/màu mà quên size | BST tìm khóa đúng nhưng rank/select sai | `recalc` cả hai nút sau xoay |
| Cập nhật size chỉ tại lá vừa chèn | Tổ tiên vẫn mang số đếm cũ | Cập nhật ngược đường đi tới gốc |
| Xóa một bản sao nhưng xóa cả nút `count>1` | Mất nhiều phần tử | Giảm count trước |
| Thay khóa nút hai con bằng successor nhưng không chuyển count | Tạo hai nút cùng khóa hoặc mất bản sao | Gỡ **nguyên nút** successor và chuyển key+count |
| Dùng BST lệch nhưng tuyên bố `O(\log n)` | Không có bất biến cân bằng | Dùng AVL/RB hoặc nêu `O(h)` |
| Coi `size(root)` là số khóa phân biệt | Sai khi có lặp | Phân biệt `n` tổng mục với `u` số nút |
| Giả định mọi `k` tương ứng một khóa duy nhất | Với duplicates, nhiều k có cùng select | Dùng bất đẳng thức rank/select |
| Dùng chỉ số/rank cũ sau khi cây bị chèn/xóa | Hạng có thể thay đổi | Tính lại khi truy vấn |
| Sửa trực tiếp `node.count` từ bên ngoài | Làm sai size tổ tiên | Đi qua API add/remove |
| Quên xử lý cây rỗng, k=0, k>n | Truy cập None hoặc trả sai | Kiểm tra biên |
| Quên kiểm tra khoảng `low>high` | Đếm âm hoặc vô nghĩa | Trả 0 hoặc báo lỗi theo hợp đồng |
| Dữ liệu thực có ID phân biệt nhưng chỉ lưu count | Không thể trả đúng bản ghi theo hạng | Dùng khóa ghép `(key,id)` hoặc bucket có thứ tự |
| Gọi `check_invariants` sau mỗi truy vấn production | Thêm `O(u)` công việc vô ích | Dùng trong test/debug |
| Trộn comparator giữa các thao tác | BST-order không nhất quán | Dùng một quan hệ thứ tự xuyên suốt |

## 27. Trường hợp biên và tính nhất quán

### Cây rỗng

```text
len(tree) = 0
rank_lt(anything) = 0
rank_le(anything) = 0
count(anything) = 0
select(1) -> IndexError
first_rank(x) -> None
```

### Một nút với nhiều bản sao

```text
S = [9,9,9,9]
root: key=9, count=4, size=4

select(1)=select(2)=select(3)=select(4)=9
rank_lt(9)=0
rank_le(9)=4
first_rank(9)=1
last_rank(9)=4
```

### Khóa nhỏ hơn tất cả hoặc lớn hơn tất cả

```text
S = [2,3,3,5]

rank_lt(0)=0
rank_le(0)=0
rank_lt(99)=4
rank_le(99)=4
```

### Chèn và xóa bản sao cuối

Nếu `count(x)=2` rồi xóa một bản sao, nút còn `count=1` và BST-order không đổi. Nếu xóa tiếp bản sao cuối, nút phải được **loại khỏi cấu trúc vật lý** và các ancestor size cập nhật đúng.

### Số nguyên lớn và tràn kiểu

Trong Python, `int` có độ dài linh hoạt. Trong C/C++/Java với kiểu số nguyên hữu hạn, `size` và `count` phải đủ lớn để biểu diễn **tổng số phần tử**, đặc biệt khi khóa bị lặp rất nhiều; phép cộng `left_size + count + right_size` phải không tràn.

### Khóa khó so sánh

Nếu dùng số thực có `NaN`, phép so sánh không tuân theo quan hệ thứ tự toàn phần thông thường, có thể làm bất biến BST sai. Cần chuẩn hóa khóa hoặc từ chối giá trị không so sánh nhất quán. Với chuỗi/đối tượng, phải dùng comparator cố định và bảo đảm comparator không thay đổi sau khi chèn.

## 28. Kiểm thử bằng mô hình tham chiếu và bất biến

Một cách kiểm thử đáng tin cậy là so AVL tăng cường với **mảng đã sắp** trên những chuỗi thêm/xóa hợp lệ.

### Kiểm thử cơ bản

```python
from bisect import bisect_left, bisect_right, insort


tree = OrderStatisticAVL()
reference: list[int] = []

for key in [5, 3, 7, 3, 2, 7, 10, 7]:
    tree.add(key)
    insort(reference, key)

assert tree.check_invariants()
assert len(tree) == len(reference)

for index, expected in enumerate(reference):
    assert tree.select(index + 1) == expected

for key in [0, 2, 3, 4, 5, 6, 7, 10, 11]:
    assert tree.rank_lt(key) == bisect_left(reference, key)
    assert tree.rank_le(key) == bisect_right(reference, key)
    assert tree.count(key) == bisect_right(reference, key) - bisect_left(reference, key)

for key in [7, 3, 5]:
    tree.remove(key)
    reference.remove(key)
    assert tree.check_invariants()
    assert [tree.select(k) for k in range(1, len(tree) + 1)] == reference
```

### Kiểm tra quan hệ select/rank

Với mỗi `k\in[1,n]`, đặt `x=select(k)`. Phải luôn đúng:

\[
rank_{<}(x)<k\le rank_{\le}(x).
\]

Đồng thời, với mọi khóa `x`:

\[
rank_{\le}(x)-rank_{<}(x)=count(x).
\]

Hai tính chất bắt lỗi:

- Sai `size` sau rotation.
- Sai khi xóa successor có `count>1`.
- Sai điều kiện `<` và `\le` ở khóa trùng.
- Sai quy ước `k` 1-based.

### Kiểm tra độc lập cấu trúc

`check_invariants()` của ví dụ kiểm:

1. BST-order nghiêm ngặt.
2. `count\ge1`.
3. `size` chính xác theo công thức tăng cường.
4. `height` chính xác.
5. `|height(left)-height(right)|\le1`.

Nhờ kiểm tra đồng thời, một cây có thể còn **tìm khóa đúng** nhưng đã **hỏng size** sẽ bị phát hiện.

## 29. Tình huống ứng dụng và cách chọn cấu trúc

### 29.1. Bảng xếp hạng điểm động

Mỗi lần người chơi cập nhật điểm, xóa điểm cũ và chèn điểm mới. `rank_lt(score)` cho biết bao nhiêu điểm thấp hơn; `select(k)` cho biết ngưỡng điểm hạng k.

Nếu cần phân biệt người chơi có cùng điểm, dùng khóa ghép `(score,player_id)` hoặc một chiến lược lưu ID trong nhóm điểm và quy tắc hòa rõ ràng.

### 29.2. Trung vị trong cửa sổ trượt

Khi cửa sổ dữ liệu chuyển, xóa giá trị hết hạn và thêm giá trị mới, rồi lấy trung vị bằng một hoặc hai lần `select`. Với cây cân bằng tăng cường:

- Cập nhật `O(\log u)`.
- Lấy trung vị `O(\log u)`.
- Xử lý khóa trùng tự nhiên bằng `count`.

Hai heap cũng có thể duy trì trung vị hiệu quả, nhưng hỗ trợ xóa **một mục tùy ý** thường cần bảng phụ hoặc xóa lười; order-statistic tree còn hỗ trợ các phân vị khác trực tiếp.

### 29.3. Đếm mức giá trong đoạn

Với tập đơn hàng có giá là số nguyên, `count_closed(100,500)` cho số đơn có giá trong khoảng. Nếu miền giá nhỏ và cố định, Fenwick/segment tree có thể tiết kiệm overhead hơn cây liên kết; nếu giá động và rất thưa, BST tăng cường hợp lý.

### 29.4. Hàng đợi cần lấy theo hạng thay vì cực trị

Heap chỉ cung cấp cực trị ở gốc, không cho ngay phần tử hạng 100. Order-statistic tree cho `select(100)` hiệu quả khi dữ liệu động, đổi lại phải duy trì thêm metadata cân bằng.

### 29.5. Phân tích log sự kiện

Nếu dữ liệu hầu như **không cập nhật**, một mảng đã sắp cộng `bisect` thường đơn giản hơn. Không nên tạo cấu trúc nút phức tạp khi chi phí xây và bộ nhớ không được bù bởi lợi thế cập nhật động.

## 30. Bài tập tự kiểm tra

**Bài 1.** Với `S=[2,3,3,5,7,7,7,10]`, cho biết `select(1)`, `select(4)`, `select(6)` và `select(8)`.

**Bài 2.** Với cùng `S`, tính `rank_lt(7)`, `rank_le(7)`, `rank_lt(6)` và `rank_le(6)`.

**Bài 3.** Giá trị `7` xuất hiện ở những hạng 1-based nào? Nêu công thức hạng đầu và hạng cuối từ hai phép rank.

**Bài 4.** Một nút có `count=3`, cây trái size `4` và cây phải size `6`. Tính `size` của nút. Các bản sao khóa tại nút chiếm những hạng nào **trong cây con ấy**?

**Bài 5.** Khi `SELECT` đang ở nút có `L=5`, `count=2` và cần hạng `k=10`, thuật toán rẽ hướng nào và hạng mới là gì?

**Bài 6.** Tại sao khi `SELECT` rẽ trái thì không được trừ `size(left)` khỏi `k`?

**Bài 7.** Viết quy tắc cộng vào biến `answer` của `rank_lt(x)` khi `x>node.key`. Vì sao cộng như vậy là chính xác?

**Bài 8.** Tại sao `rank_lt(x)` vẫn có thể trả kết quả hữu ích nếu `x` không tồn tại trong cây?

**Bài 9.** Nếu `rank_lt(9)=6` và `rank_le(9)=10`, khóa `9` xuất hiện bao nhiêu lần và chiếm hạng nào?

**Bài 10.** Chứng minh trong một câu vì sao `rank_lt(select(k))=k-1` **không luôn đúng** với dữ liệu có khóa trùng.

**Bài 11.** Giải thích bất đẳng thức đúng cho mọi `k` hợp lệ: `rank_lt(select(k))<k<=rank_le(select(k))`.

**Bài 12.** Một BST chèn lần lượt `1,2,3,4,5` mà không tự cân bằng. Chiều cao và thời gian xấu nhất của `select` có thể là bao nhiêu?

**Bài 13.** Sau khi chèn một bản sao của khóa đã tồn tại, `count` thay đổi nhưng cây không đổi hình dạng. Những trường `size` nào phải được cập nhật?

**Bài 14.** Khi xoay trái tại nút `x` có con phải `y`, tại sao phải `recalc(x)` trước `recalc(y)`?

**Bài 15.** Khi xóa nút hai con có `count=1` và successor có `count=4`, vì sao phải chuyển cả `count=4` vào nút thay thế?

**Bài 16.** Cho `S=[1,2,2,4,6,6,9]`. Tính số phần tử trong khoảng đóng `[2,6]` và trong khoảng nửa kín `[2,6)` bằng hai phép rank.

**Bài 17.** Với `n=8` phần tử, trung vị số học (khi giá trị có thể lấy trung bình) cần những lần select nào?

**Bài 18.** Một cây có `n=1000` lần xuất hiện nhưng chỉ `u=10` khóa phân biệt. Nếu AVL lưu `count`, số nút là bao nhiêu và chi phí hạng phụ thuộc chủ yếu `u` hay `n`?

**Bài 19.** So sánh `select(k)` và chèn một khóa vào **mảng đã sắp** với AVL có size.

**Bài 20.** Nếu khóa là số nguyên trong miền nhỏ `0,\ldots,U-1` và có nhiều cập nhật tần suất, Fenwick tree hỗ trợ rank và select bằng cách nào?

**Bài 21.** Khi thêm một khóa mới chưa có trong bảng **nén tọa độ** của Fenwick, vì sao không thể luôn giữ nguyên mọi chỉ số đã nén mà vẫn đúng thứ tự?

**Bài 22.** Một AVL kiểm tra height đúng nhưng `size` sai sau rotation. Kết quả tìm khóa có thể đúng không? Kết quả rank/select có chắc đúng không?

**Bài 23.** Ứng dụng có hai học sinh cùng điểm `85`. Vì sao chỉ lưu `key=85,count=2` không đủ để `select(k)` trả **ID học sinh** cụ thể? Đề xuất cách thiết kế khác.

**Bài 24.** Đề xuất ba thuộc tính cần kiểm thử trên một cây AVL tăng cường sau chuỗi insert/delete ngẫu nhiên.

### Đáp án và giải thích

1. `select(1)=2`; `select(4)=5`; `select(6)=7`; `select(8)=10`.
2. `rank_lt(7)=4`, `rank_le(7)=7`; `rank_lt(6)=4`, `rank_le(6)=4`.
3. `7` ở các hạng `5,6,7`. Hạng đầu `rank_lt(7)+1=5`, hạng cuối `rank_le(7)=7`.
4. `size=4+3+6=13`. Khóa tại nút chiếm các hạng `5,6,7` trong cây con của nút.
5. `10>5+2=7` nên rẽ **phải**, với `k'=10-7=3`.
6. Hạng `k` trong cây trái vẫn là hạng `k` tương ứng, vì mọi phần tử được xét vẫn thuộc cây trái; không có phần tử đứng trước trong cây trái bị loại khỏi đoạn cần tìm.
7. Cộng `size(node.left)+node.count`: toàn bộ cây trái và tất cả bản sao tại nút đều nhỏ hơn `x` khi `x>node.key`.
8. Nó là số phần tử nhỏ hơn `x`, chính là vị trí chèn lower-bound, nên không cần có một bản ghi bằng `x`.
9. `count(9)=10-6=4`; các hạng là `7,8,9,10`.
10. Nhiều hạng `k` có thể cùng trả về một khóa `x`; `rank_lt(x)` chỉ đếm các khóa **nhỏ hơn**, không phân biệt thứ tự các bản sao bằng nhau.
11. Nếu `x=select(k)` thì phần tử hạng `k` nằm sau tất cả khóa nhỏ hơn `x` và không nằm sau toàn bộ các khóa bằng `x`; do đó `rank_lt(x)<k<=rank_le(x)`.
12. BST có thể thành đường thẳng chiều cao `\Theta(u)`; `select` đi dọc đường ấy, nên thời gian xấu nhất `O(u)`, ở đây `u=5`.
13. `size` tại nút chứa khóa và mọi tổ tiên trên đường về gốc phải tăng thích hợp, thông qua `recalc`; không nhất thiết đổi `height`.
14. Sau rotation, `y.left=x` nên `size(y)` phụ thuộc `size(x)` **mới**; phải cập nhật `x` trước rồi mới `y`.
15. Để giữ đủ bốn bản sao của successor sau khi bỏ nút cũ. Nếu chỉ chuyển khóa và giảm count ở successor, sẽ tạo hai nút có cùng khóa hoặc đếm sai số phần tử.
16. `rank_le(6)=6`, `rank_lt(2)=1`, `rank_lt(6)=4`. `count_[2,6]=6-1=5`; `count_[2,6)=4-1=3`.
17. Hai giá trị giữa là `select(4)` và `select(5)`; trung vị số học là trung bình của hai giá trị.
18. Có `u=10` nút nếu dùng một nút mỗi khóa; chiều cao AVL và thời gian hạng là `O(\log(u+1))`, không phụ thuộc tuyến tính vào `n=1000`.
19. Mảng đã sắp lấy `select` `O(1)` nhưng chèn giữa có thể `O(n)` dịch chuyển; AVL `select` và chèn đều `O(\log u)`.
20. Fenwick lưu tần suất, `rank_lt(x)` bằng tổng tiền tố đến khóa ngay trước `x`; `select(k)` tìm vị trí nhỏ nhất có tổng tiền tố `\ge k` bằng binary lifting trên Fenwick, `O(\log U)`.
21. Một khóa mới có thể phải nằm **giữa** hai khóa đã nén; thứ tự index cũ không còn phản ánh đầy đủ thứ tự so sánh nếu không cấp chỗ/tái ánh xạ, nên có thể phải xây lại hoặc chọn cấu trúc động.
22. Có, vì BST-order và cân bằng có thể vẫn đúng. Rank/select dựa trực tiếp vào `size`, nên có thể sai dù tìm theo khóa vẫn đúng.
23. `count=2` chỉ ghi nhận số bản sao `85`, không cho biết bản nào là ai hay thứ tự giữa hai ID. Dùng khóa ghép `(score,student_id)` hoặc lưu bucket ID có quy tắc thứ tự.
24. Ví dụ: kiểm tra `size=size(left)+count+size(right)` cho mọi nút; kiểm tra BST-order và AVL-height; so toàn bộ `select(k)`/`rank_lt(x)` với một mảng đã sắp tham chiếu, đặc biệt khi khóa trùng.

## 31. Ghi nhớ

**Order-statistic tree** là cây tìm kiếm được tăng cường **số phần tử trong mỗi cây con**. Với multiset, bất biến cốt lõi là **`size(node)=size(left)+count(node)+size(right)`**. Khi tìm phần tử hạng `k` theo quy ước **1-based**, so `k` với `size(left)` và `count` để rẽ trái, trả khóa nút hoặc trừ rồi rẽ phải. Khi tính `rank_lt(x)`, ta cộng `size(left)+count` mỗi lần rẽ sang phải vì tất cả những phần tử ấy chắc chắn **nhỏ hơn `x`**; `rank_le(x)` đếm thêm các bản sao bằng `x`. Hai phép rank cho phép tính số lần khóa xuất hiện, hạng đầu/cuối và số mục trong khoảng, **ngay cả khi một khóa tìm kiếm không tồn tại**. Với cây cân bằng như AVL/red-black tree, các thao tác đạt **`O(\log(u+1))`** theo số khóa phân biệt `u`, miễn là **size được bảo trì sau insert, delete và mọi rotation**. Với dữ liệu tĩnh, mảng đã sắp có thể đơn giản hơn; với miền khóa nguyên nhỏ, Fenwick/segment tree là lựa chọn khác. Hãy chốt **quy ước hạng, chính sách khóa trùng và cách cập nhật metadata** trước khi lập trình để tránh những lỗi lệch một đơn vị và kết quả rank/select sai.

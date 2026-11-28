# Cây đoạn nhiều phiên bản cho truy vấn lịch sử

## 1. Bài toán: cần truy vấn lại dữ liệu ở nhiều thời điểm

Trong một hệ thống quản lý dữ liệu, mỗi lần cập nhật mảng có thể làm thay đổi tổng, giá trị nhỏ nhất, số lượng phần tử hoặc thứ hạng. Nếu chỉ lưu **mảng hiện tại**, trạng thái ở các thời điểm trước đã biến mất.

Giả sử mảng ban đầu là:

```text
A(v0) = [2, 1, 3, 0, 4, 2]
          0  1  2  3  4  5     ← chỉ số 0-based
```

Một loạt cập nhật:

- `v1`: đặt `A[2]=7`.
- `v2`: từ `v1`, đặt `A[4]=1`.
- `v3`: từ `v0`, đặt `A[1]=9`, tạo **nhánh phiên bản mới**.

Mảng trong từng phiên bản:

| Phiên bản | Cha | Nội dung |
|---|---|---|
| `v0` | — | `[2,1,3,0,4,2]` |
| `v1` | `v0` | `[2,1,7,0,4,2]` |
| `v2` | `v1` | `[2,1,7,0,1,2]` |
| `v3` | `v0` | `[2,9,3,0,4,2]` |

Ta muốn trả lời:

1. `sum(v0,1,5)` là bao nhiêu?
2. `sum(v1,1,5)` có gì khác?
3. Dữ liệu ở `v2` và `v3` còn có thể đọc song song không?
4. Có thể tạo một phiên bản mới từ **bất kỳ bản cũ nào** mà không chép toàn bộ mảng?
5. Với một dãy giá trị lớn và nhiều truy vấn `k`-th smallest trên các đoạn của **dãy gốc**, có thể dùng nhiều cây đoạn để trả lời nhanh không?

Giải pháp trung tâm của bài: **cây đoạn nhiều phiên bản** (*persistent segment tree*).

Đây là cây đoạn (*segment tree*) mà mỗi phiên bản được biểu diễn bởi **một gốc riêng**. Khi cập nhật một vị trí, ta **sao chép các nút trên đường từ gốc tới lá cần sửa**, trong khi những cây con không đổi được **dùng chung** giữa các phiên bản.

Bài học thuộc chủ đề **Bất biến và phiên bản** của môn Cấu trúc dữ liệu, kết nối kiến thức về mảng, cây nhị phân, bất biến, phép truy vấn đoạn, thời gian và bộ nhớ. Ta sẽ xây hai ứng dụng:

- **Persistent range-sum segment tree:** cập nhật điểm, truy vấn tổng đoạn tại bất kỳ phiên bản.
- **Persistent frequency segment tree:** lưu tần suất theo **tiền tố dãy**, dùng hiệu hai gốc để tìm phần tử thứ `k` trong đoạn `A[l:r]`.

> Cần phân biệt: **truy vấn lại phiên bản cũ của cùng một mảng** và **truy vấn thứ hạng trong một đoạn bằng hiệu hai prefix roots** dùng chung kỹ thuật lưu nhiều gốc, nhưng có **ngữ nghĩa và điều kiện hợp lệ khác nhau**.

## 2. Nhắc lại cây đoạn thông thường

### 2.1. Mỗi nút quản lý một khoảng chỉ số

Với mảng `A` dài `n`, quy ước sử dụng đoạn **nửa mở** `[l,r)`:

\[
[l,r)=\{l,l+1,\ldots,r-1\}.
\]

Độ dài đoạn là:

\[
r-l.
\]

Nút gốc quản lý `[0,n)`. Nếu `r-l>1`, chia tại:

\[
m=\left\lfloor\frac{l+r}{2}\right\rfloor.
\]

Hai con quản lý:

\[
[l,m)\quad\text{và}\quad[m,r).
\]

Lá quản lý đúng **một phần tử** khi `r-l=1`.

### 2.2. Với truy vấn tổng

Lưu trường:

\[
sum(u)=\sum_{i\in segment(u)} A[i].
\]

Bất biến:

- Ở lá `[i,i+1)`: `sum(leaf)=A[i]`.
- Ở nút trong: `sum(u)=sum(u.left)+sum(u.right)`.

Ví dụ với `A=[2,1,3,0]`:

```text
                     [0,4):6
                    /       \
             [0,2):3         [2,4):3
             /    \          /     \
          [0,1):2 [1,2):1 [2,3):3 [3,4):0
```

Truy vấn tổng `[1,4)` là `1+3+0=4`. Không cần duyệt mọi phần tử: ta có thể cộng các nút phân đoạn phủ đúng vùng được hỏi.

### 2.3. Vì sao cây đoạn có thể truy vấn nhanh?

Với cây đoạn nhị phân cân bằng, số tầng là:

\[
h=O(\log(n+1)).
\]

Một truy vấn tổng đoạn tiêu chuẩn chỉ cần thăm `O(\log(n+1))` nút/cụm nhánh hữu ích trong cách phân rã chuẩn. Cập nhật một vị trí chỉ ảnh hưởng đường gốc–lá dài `O(\log(n+1))`.

**Cây đoạn khả biến** sửa trực tiếp trường `sum` và các con trỏ tại các nút trên đường đi. Điều đó làm mất metadata của những phiên bản trước — trừ khi có cơ chế lưu phiên bản.

## 3. Cây đoạn persistent lưu phiên bản thế nào?

### 3.1. Một root cho mỗi snapshot

Thay vì biến `root` bị thay thế theo thời gian:

```text
root = update(root, index, value)
```

ta lưu các gốc:

```text
roots[0] = root_v0
roots[1] = update(root_v0, index, value)
roots[2] = update(root_v1, index, value)
roots[3] = update(root_v0, another_index, value)
```

Hàm `update` là **thuần** (*pure*): không sửa bất kỳ nút nào trong `root_v0`. Nó trả một đối tượng root khác khi dữ liệu thay đổi.

Sơ đồ lịch sử:

```text
             v0
            /  \
          v1    v3
          |
          v2
```

Vì có thể cập nhật từ `v0` sau khi `v2` đã tồn tại, API này hỗ trợ **bền vững toàn phần (full persistence)** cho cập nhật điểm.

Nếu API chỉ cho cập nhật phiên bản mới nhất, dù cách triển khai vẫn dùng path copying, nó chỉ cung cấp **hành vi partial persistence**.

### 3.2. Nút chia sẻ phải bất biến

Một nút được chia sẻ giữa hai phiên bản không được thay đổi:

```text
version 0 --> old_parent ----+
                            |
                            v
                       shared_subtree
                            ^
                            |
version 1 --> new_parent ----+
```

**Dùng chung** ở đây là cùng tham chiếu tới **một đối tượng bất biến**. Không có deep copy của toàn bộ cây con.

Nút có thể được lưu bằng kiểu cấu trúc:

```text
Node(
    left,
    right,
    aggregate
)
```

Với tổng đoạn, `aggregate=sum`. Khi có một con thay đổi, tạo nút cha mới với con mới và con còn lại **giữ nguyên tham chiếu cũ**.

### 3.3. Cập nhật một điểm bằng sao chép đường đi

Giả sử sửa `A[2]` từ `3` thành `7` ở cây bốn phần tử:

```text
Cây v0:                                  Cây v1:

                    [0,4):6                                [0,4):10'
                  /         \                            /          \
              [0,2):3       [2,4):3                    [0,2):3     [2,4):7'
               /    \       /     \                      (shared)    /    \
              2      1     3       0                             7'      0
                        (old leaf)                              (new leaf)
```

Đường bị ảnh hưởng:

```text
[0,4) → [2,4) → [2,3)
```

Các nút mới:

```text
leaf([2,3), value=7)
node([2,4), sum=7)
node([0,4), sum=10)
```

Những cây con khác được **chia sẻ**:

- Toàn bộ `[0,2)`, gồm hai lá `2` và `1`.
- Lá `[3,4)` có giá trị `0`.

Phiên bản `v0` vẫn có lá `3` và tổng gốc `6`. Phiên bản `v1` có lá `7` và tổng gốc `10`.

**Số nút mới:** `O(\log(n+1))`, không phải `O(n)`.

### 3.4. Tại sao không sao chép chỉ lá?

Gốc cũ vẫn trỏ tới cha cũ; cha cũ vẫn trỏ tới lá cũ. Nếu chỉ tạo lá mới mà không tạo lại các nút tổ tiên, **không có đường nào từ gốc mới đến lá mới** trừ khi ta sửa con trỏ của nút cũ — hành vi làm hỏng phiên bản cũ.

Vì vậy cần sao chép **cả đường đi từ lá lên gốc**, không chỉ ô dữ liệu được sửa.

## 4. Bất biến cốt lõi phải duy trì

### 4.1. Bất biến phân hoạch

Mỗi nút gắn với một đoạn xác định `[l,r)`.

Nếu `r-l>1` và `m=(l+r)//2`:

- Con trái quản lý `[l,m)`.
- Con phải quản lý `[m,r)`.
- Hai đoạn con không giao nhau, hợp của chúng bằng đoạn cha.

Trong triển khai cây đoạn cố định miền, **ranh giới đoạn có thể do tham số đệ quy quản lý**, không bắt buộc lưu `l,r` trên mỗi nút. Điều đó giảm bộ nhớ mỗi nút.

### 4.2. Bất biến tổng

Với mọi phiên bản và mọi nút:

\[
sum(node_{[l,r)})=\sum_{i=l}^{r-1}A_{\text{version}}[i].
\]

Ở nút trong:

\[
sum(node)=sum(left)+sum(right).
\]

Với cây rỗng `n=0`, ta quy ước tổng đoạn rỗng bằng `0`; không có root cây chứa phần tử.

### 4.3. Bất biến không sửa bản cũ

Sau khi `roots[v]` đã được công bố, mọi nút có thể truy cập từ gốc ấy:

- Không bị thay đổi giá trị `sum`.
- Không bị thay đổi con trỏ `left/right`.
- Không chứa payload khả biến có thể bị mã ngoài chỉnh sửa.

Một bản cập nhật tạo các nút mới nhưng không sửa các nút cũ.

### 4.4. Bất biến phiên bản và hợp đồng cập nhật

Một lời gọi:

```text
new_version = set(base_version, index, new_value)
```

phải:

1. Chỉ đọc cấu trúc ở `base_version`.
2. Trả một ID mới với cây chứa đúng dữ liệu đã sửa.
3. Giữ nguyên các ID phiên bản trước.
4. Chia sẻ mọi cây con không thay đổi.

Nếu giá trị mới bằng giá trị cũ, có thể tạo ID mới nhưng dùng lại **chính cùng root**, vì không có thay đổi nội dung.

### 4.5. Bất biến phụ thuộc phép gộp

Nếu thay tổng bằng giá trị nhỏ nhất, tại nút trong cần:

\[
minimum(node)=\min(minimum(left),minimum(right)).
\]

Nếu cần lưu đồng thời `sum` và `minimum`, metadata có thể là cặp `(sum,min)` với phép gộp tương ứng.

**Persistence không bắt buộc phải dùng tổng.** Nó là một kỹ thuật lưu phiên bản có thể áp dụng cho nhiều phép gộp kết hợp với chi phí cục bộ phù hợp.

## 5. Mã giả cập nhật một vị trí

### 5.1. Đặt giá trị mới

```text
SET(old_node, l, r, index, new_value):
    require l <= index < r

    if r-l == 1:
        return NEW_LEAF(sum=new_value)

    m = (l+r)//2

    if index < m:
        new_left = SET(old_node.left, l, m,
                       index, new_value)
        new_right = old_node.right       # SHARED
    else:
        new_left = old_node.left         # SHARED
        new_right = SET(old_node.right, m, r,
                        index, new_value)

    return NEW_NODE(
        left=new_left,
        right=new_right,
        sum=new_left.sum + new_right.sum
    )
```

Ở lá, thay nội dung bằng một nút mới; ở các tầng trên, tạo nút cha mới chứa một nhánh mới và một nhánh dùng chung.

### 5.2. Vì sao đệ quy không sửa cây cũ?

Mỗi lời gọi:

- Đọc `old_node.left/right/sum`.
- Không thực hiện `old_node.left=...` hay `old_node.sum=...`.
- Trả một đối tượng mới.

Cây con không đi vào nhánh cập nhật vẫn là **đối tượng old_node.child** tương ứng. Sau đó nhiều gốc phiên bản có thể cùng tham chiếu đối tượng này mà không lo mutation.

### 5.3. Tối ưu không cấp phát khi no-op

Tại lá:

```text
if old_leaf.sum == new_value:
    return old_leaf
```

Ở cha:

```text
if new_child is old_child:
    return old_parent
```

Nhờ kiểm tra **định danh đối tượng**, một cập nhật không làm đổi dữ liệu có thể trả **nguyên gốc cũ**, tạo `0` nút mới.

### 5.4. Cập nhật cộng thêm một lượng

Hai loại thao tác khác nhau:

- **Point assignment:** `A[i] = x`.
- **Point add:** `A[i] += delta`.

Cây persistent có thể hỗ trợ cả hai. Với point add, đọc giá trị cũ ở lá, tạo lá mới có tổng:

\[
newValue=oldValue+\Delta.
\]

Không được nhầm `set(i,\Delta)` với `add(i,\Delta)`; một phép **ghi đè**, phép kia **cộng dồn**.

## 6. Truy vấn tổng đoạn ở một phiên bản lịch sử

### 6.1. Thuật toán không cần thay đổi

Một cây persistent vẫn là cây đoạn bình thường khi chỉ **đọc**. Truy vấn:

```text
QUERY(node, l, r, ql, qr):
    if qr <= l or r <= ql:
        return 0                          # Không giao.

    if ql <= l and r <= qr:
        return node.sum                   # Phủ hoàn toàn.

    m = (l+r)//2

    return QUERY(node.left, l, m, ql, qr)
         + QUERY(node.right, m, r, ql, qr)
```

Với `ql,qr` là đoạn nửa mở `[ql,qr)`.

Hàm này **không cấp phát nút mới**, chỉ đọc những nút trong phiên bản được chỉ định.

### 6.2. Truy vết với mảng ví dụ

Xét:

```text
v0 = [2,1,3,0,4,2]
v1 = [2,1,7,0,4,2]    # set(2,7) từ v0
v2 = [2,1,7,0,1,2]    # set(4,1) từ v1
v3 = [2,9,3,0,4,2]    # set(1,9) từ v0
```

Truy vấn `[1,5)` bao gồm các chỉ số `1,2,3,4`:

| Phiên bản | Phần tử trong `[1,5)` | Tổng |
|---|---|---:|
| `v0` | `[1,3,0,4]` | `8` |
| `v1` | `[1,7,0,4]` | `12` |
| `v2` | `[1,7,0,1]` | `9` |
| `v3` | `[9,3,0,4]` | `16` |

Cùng một truy vấn đoạn, chỉ đổi **root phiên bản** là nhận kết quả ở thời điểm khác.

### 6.3. Hiệu hai kết quả lịch sử

Muốn biết **tổng đoạn** thay đổi bao nhiêu giữa hai phiên bản:

\[
deltaSum(v_a,v_b,l,r)=
sum(v_b,l,r)-sum(v_a,l,r).
\]

Ví dụ:

\[
deltaSum(v0,v1,1,5)=12-8=4.
\]

Nếu trọng số được phép âm, hiệu có thể âm; điều này hoàn toàn hợp lệ.

**Lưu ý:** hiệu hai tổng không phải danh sách thao tác đã thực hiện. Nhiều cập nhật có thể triệt tiêu nhau, và hai phiên bản có thể nằm trên **hai nhánh khác nhau**. Kết quả phản ánh **chênh lệch trạng thái**, không nhất thiết là số lượng sự kiện.

## 7. So sánh snapshot bằng cây đoạn

### 7.1. Những thứ có thể so sánh

Với nhiều root, ta có thể:

- So sánh tổng một đoạn giữa hai bản.
- Lấy hiệu tổng trên từng đoạn.
- Dò những vị trí có giá trị thay đổi.
- Phân tích sự khác biệt giữa hai nhánh lịch sử.
- Theo dõi một chỉ số qua nhiều thời điểm.

### 7.2. Identity giúp bỏ qua cây con chung

Nếu tại cùng một vùng chỉ số:

```python
node_a is node_b
```

thì hai phiên bản chia sẻ **chính cùng một cây con bất biến**, nên vùng ấy chắc chắn có cùng các giá trị và có thể bỏ qua mà không duyệt sâu.

Ngược lại:

```python
node_a is not node_b
```

**chưa đủ để kết luận nội dung khác**: một nút mới có thể biểu diễn cùng tổng và cùng các phần tử do thao tác đã đảo ngược.

### 7.3. Hai tổng bằng nhau không chứng minh hai đoạn bằng nhau

Ví dụ:

```text
A = [1,4]
B = [2,3]
```

Cả hai có tổng `5`, nhưng các phần tử khác nhau. Nếu muốn kiểm tra mọi vị trí thay đổi, **chỉ so `sum` là không đủ**.

Có thể duyệt hai cây song song:

```text
COMPARE(nodeA, nodeB, l, r):
    if nodeA is nodeB:
        return

    if r-l == 1:
        if nodeA.sum != nodeB.sum:
            OUTPUT position l
        return

    m=(l+r)//2
    COMPARE(leftA,leftB,l,m)
    COMPARE(rightA,rightB,m,r)
```

Phép duyệt có thể chạm tới `O(n)` nút khi hai cây khác nhau ở nhiều vị trí; các nút dùng chung giúp cắt nhánh nhanh khi dữ liệu được cập nhật qua path copying.

**Không** có bảo đảm mọi cặp phiên bản chỉ khác `d` vị trí sẽ luôn được so sánh trong `O(d\log n)` nếu chưa phân tích mô hình biểu diễn và kiểu chia sẻ thực tế. Hai cây cùng nội dung nhưng được dựng độc lập có thể không chia sẻ nút nào.

## 8. Phân tích chi phí cho persistent range-sum tree

Gọi `n` là độ dài mảng cố định, `U` là số lần cập nhật điểm được giữ thành phiên bản và `V` là số root phiên bản.

### 8.1. Xây cây ban đầu

Cây đoạn nhị phân đầy đủ theo phân hoạch tới từng phần tử có:

- `n` nút lá.
- `n-1` nút trong nếu `n≥1`.
- Tổng `2n-1` nút.

Do đó:

\[
T_{\text{build}}=\Theta(n),\qquad
S_{\text{build}}=\Theta(n).
\]

Với `n=0`, có thể lưu một root rỗng và bỏ bước dựng cây.

### 8.2. Cập nhật điểm

Mỗi cập nhật đi qua một đường gốc–lá dài `O(\log(n+1))`, tạo nhiều nhất một nút mới cho mỗi tầng trong bản đơn giản.

\[
\boxed{
T_{\text{point-update}}=O(\log(n+1))
}
\]

\[
\boxed{
S_{\text{new nodes per update}}=O(\log(n+1)).
}
\]

Nếu cập nhật không đổi dữ liệu, triển khai tối ưu có thể cấp phát **0 nút**.

### 8.3. Truy vấn đoạn

\[
\boxed{
T_{\text{range-query}}=O(\log(n+1))
}
\]

trong cây đoạn cố định phân hoạch cân bằng và phép gộp `O(1)`. Nếu hàm dùng đệ quy, bộ nhớ stack là `O(\log(n+1))`; không tạo nút dữ liệu mới.

### 8.4. Bộ nhớ nhiều phiên bản

Nếu có `U` cập nhật đơn điểm và giữ `V` root:

\[
\boxed{
S_{\text{total}}=O(n+U\log(n+1)+V).
}
\]

Chặn trên này đếm:

- Cây đầu `O(n)`.
- Những nút mới trên các đường cập nhật.
- Danh sách tham chiếu root/metadata phiên bản `O(V)`.

Nhiều root có thể **chia sẻ cùng một cây con**, vì vậy không cần `O(Vn)` nút như sao chép toàn cây cho từng bản.

### 8.5. Bảng so sánh

| Cách lưu các bản | Xây ban đầu | Một cập nhật điểm | Một truy vấn tổng đoạn ở bản đã lưu | Bộ nhớ nhiều bản |
|---|---:|---:|---:|---:|
| Lưu mảng sao chép sau từng sửa | `O(n)` | `O(n)` sao chép | `O(r-l)` nếu quét trực tiếp | `O(Vn)` |
| Mảng snapshot + prefix sum riêng mỗi bản | `O(n)` | `O(n)` để cập nhật bản prefix | `O(1)` | `O(Vn)` |
| Cây đoạn mutable, không lưu bản cũ | `O(n)` | `O(\log n)` | `O(\log n)` ở bản hiện hành | `O(n)` |
| **Persistent segment tree** | `O(n)` | **`O(\log n)`** | **`O(\log n)`** | **`O(n+U\log n+V)`** |

Các biểu thức `\log n` trong bảng hiểu với `n≥2`; dùng `\log(n+1)` để bao gồm trường hợp nhỏ.

**Đánh đổi:** persistent segment tree phát sinh nhiều đối tượng nhỏ và nhiều con trỏ hơn mảng liên tiếp; vì vậy Big-O tốt không tự đảm bảo hiệu năng cache hoặc chi phí cấp phát tốt nhất trong mọi workload.

## 9. Cài đặt Python: nút bất biến và tổng đoạn theo phiên bản

### 9.1. Hợp đồng của ví dụ

Cài đặt dưới đây hỗ trợ:

- Mảng **có độ dài cố định** `n≥0`.
- Phần tử là số nguyên Python; trọng số âm được phép.
- Chỉ số từ `0`.
- Đoạn truy vấn nửa mở `[left,right)`.
- `set(base_version,index,value)`: tạo bản mới bằng **ghi đè** tại một vị trí.
- `add(base_version,index,delta)`: tạo bản mới bằng **cộng** tại vị trí ấy.
- `sum(version,left,right)`: tổng của đoạn trong snapshot được chỉ định.
- `get(version,index)`: đọc một phần tử.
- Có thể cập nhật từ **bất kỳ phiên bản đã giữ**.
- Mỗi thao tác cập nhật hợp lệ tạo một ID mới, kể cả no-op.

**Python:** dùng type annotation từ Python 3.10 và `dataclass(slots=True)`, nên ví dụ yêu cầu **Python 3.10 trở lên**.

### 9.2. Nút bất biến

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, eq=False)
class SumNode:
    total: int
    left: SumNode | None = None
    right: SumNode | None = None


def total_of(node: SumNode | None) -> int:
    return 0 if node is None else node.total
```

`frozen=True` chặn phép gán trường thông thường; `eq=False` giúp dùng identity đối tượng khi nhận diện cây con dùng chung.

Trường `total` là metadata tổng của toàn đoạn do nút quản lý. Ranh giới đoạn được suy ra từ tham số đệ quy, không lưu trên nút.

### 9.3. Dựng cây ban đầu

```python
def build_sum_tree(
    values: list[int],
    lo: int,
    hi: int,
) -> SumNode:
    """Điều kiện: 0 <= lo < hi <= len(values)."""
    if hi - lo == 1:
        return SumNode(total=values[lo])

    mid = (lo + hi) // 2

    left = build_sum_tree(values, lo, mid)
    right = build_sum_tree(values, mid, hi)

    return SumNode(
        total=left.total + right.total,
        left=left,
        right=right,
    )
```

Với `n=0`, lớp quản lý **không gọi** `build_sum_tree` mà lưu `root=None`.

### 9.4. Hàm cập nhật điểm thuần

```python
def point_set(
    node: SumNode,
    lo: int,
    hi: int,
    index: int,
    new_value: int,
) -> SumNode:
    """Tạo đường mới đến index; không sửa node cũ."""
    if hi - lo == 1:
        if node.total == new_value:
            return node  # No-op, giữ nguyên đối tượng.
        return SumNode(total=new_value)

    mid = (lo + hi) // 2

    if index < mid:
        old_left = node.left
        old_right = node.right
        assert old_left is not None
        assert old_right is not None

        new_left = point_set(
            old_left, lo, mid, index, new_value
        )
        if new_left is old_left:
            return node

        return SumNode(
            total=new_left.total + old_right.total,
            left=new_left,
            right=old_right,  # Cây con cũ dùng chung.
        )

    old_left = node.left
    old_right = node.right
    assert old_left is not None
    assert old_right is not None

    new_right = point_set(
        old_right, mid, hi, index, new_value
    )
    if new_right is old_right:
        return node

    return SumNode(
        total=old_left.total + new_right.total,
        left=old_left,     # Cây con cũ dùng chung.
        right=new_right,
    )
```

**Điểm cần đọc kỹ:** không có phép gán nào như `node.left=...`, `node.right=...` hoặc `node.total=...`. Mọi cập nhật thật đều trả **nút mới**.

### 9.5. Hàm truy vấn đoạn

```python
def range_sum(
    node: SumNode,
    lo: int,
    hi: int,
    ql: int,
    qr: int,
) -> int:
    if qr <= lo or hi <= ql:
        return 0

    if ql <= lo and hi <= qr:
        return node.total

    mid = (lo + hi) // 2
    assert node.left is not None
    assert node.right is not None

    return (
        range_sum(node.left, lo, mid, ql, qr)
        + range_sum(node.right, mid, hi, ql, qr)
    )
```

Khi một cây con nằm ngoài truy vấn, trả phần tử trung hòa `0`. Nếu toàn bộ đoạn cây con được bao phủ, trả ngay tổng lưu ở nút, không duyệt tiếp.

## 10. Bộ quản lý nhiều phiên bản của cây tổng

### 10.1. Lưu gốc và kiểm tra hợp đồng đầu vào

```python
class PersistentRangeSum:
    def __init__(self, values: list[int]):
        if any(type(x) is not int for x in values):
            raise TypeError("Mọi phần tử phải là int")

        self.n = len(values)
        initial_root = (
            None
            if self.n == 0
            else build_sum_tree(values, 0, self.n)
        )

        # Mỗi phần tử danh sách là một gốc phiên bản.
        self._roots: list[SumNode | None] = [initial_root]

    @property
    def version_count(self) -> int:
        return len(self._roots)

    def _root(self, version: int) -> SumNode | None:
        if (
            type(version) is not int
            or not 0 <= version < len(self._roots)
        ):
            raise IndexError("Phiên bản không hợp lệ")
        return self._roots[version]

    def _check_index(self, index: int) -> None:
        if (
            type(index) is not int
            or not 0 <= index < self.n
        ):
            raise IndexError("index ngoài [0,n)")

    def _check_range(self, left: int, right: int) -> None:
        if (
            type(left) is not int
            or type(right) is not int
            or not 0 <= left <= right <= self.n
        ):
            raise IndexError("Đoạn phải thỏa 0<=left<=right<=n")

    def get(self, version: int, index: int) -> int:
        node = self._root(version)
        self._check_index(index)
        assert node is not None

        lo, hi = 0, self.n

        while hi - lo > 1:
            mid = (lo + hi) // 2
            if index < mid:
                assert node.left is not None
                node = node.left
                hi = mid
            else:
                assert node.right is not None
                node = node.right
                lo = mid

        return node.total

    def set(self, base_version: int, index: int, value: int) -> int:
        old_root = self._root(base_version)
        self._check_index(index)
        if type(value) is not int:
            raise TypeError("value phải là int")
        assert old_root is not None

        new_root = point_set(
            old_root, 0, self.n, index, value
        )

        self._roots.append(new_root)
        return len(self._roots) - 1

    def add(self, base_version: int, index: int, delta: int) -> int:
        self._root(base_version)
        self._check_index(index)
        if type(delta) is not int:
            raise TypeError("delta phải là int")

        old_value = self.get(base_version, index)
        return self.set(base_version, index, old_value + delta)

    def sum_range(
        self, version: int, left: int, right: int
    ) -> int:
        root = self._root(version)
        self._check_range(left, right)

        if left == right:
            return 0

        assert root is not None
        return range_sum(
            root, 0, self.n, left, right
        )

    def delta_sum(
        self,
        from_version: int,
        to_version: int,
        left: int,
        right: int,
    ) -> int:
        """Hiệu tổng trạng thái: to - from."""
        return (
            self.sum_range(to_version, left, right)
            - self.sum_range(from_version, left, right)
        )

    def materialize(self, version: int) -> list[int]:
        """Xuất toàn mảng ở phiên bản, O(n) thời gian."""
        root = self._root(version)
        if root is None:
            return []

        result = []

        def visit(node: SumNode, lo: int, hi: int):
            if hi - lo == 1:
                result.append(node.total)
                return

            mid = (lo + hi) // 2
            assert node.left is not None
            assert node.right is not None
            visit(node.left, lo, mid)
            visit(node.right, mid, hi)

        visit(root, 0, self.n)
        return result
```

**Hợp đồng cụ thể:**

- `PersistentRangeSum(values)` tạo `version=0`; độ dài mảng cố định trong suốt đời đối tượng.
- `get(v,i)` trả phần tử `i` của phiên bản `v`.
- `set(v,i,x)` và `add(v,i,delta)` **trả ID phiên bản mới**, không trả root trực tiếp.
- `sum_range(v,l,r)` đọc tổng đoạn nửa mở, trả `0` khi `l=r`.
- `delta_sum(a,b,l,r)` lấy **tổng phiên bản b trừ tổng phiên bản a**; không yêu cầu `a` là tổ tiên của `b`.
- `materialize(v)` **xuất bản sao giá trị dạng list**, không trả các nút để bên ngoài sửa.
- Với mảng rỗng, chỉ truy vấn tổng `[0,0)` là hợp lệ; không có vị trí nào để `set/add/get`.
- Mã từ chối `bool` dù Python xem `bool` là lớp con của `int`: đầu vào chỉ nhận `type(x) is int`.

### 10.2. Truy vết bốn phiên bản

```python
tree = PersistentRangeSum([2, 1, 3, 0, 4, 2])

v0 = 0
v1 = tree.set(v0, 2, 7)
v2 = tree.set(v1, 4, 1)
v3 = tree.set(v0, 1, 9)  # Rẽ nhánh từ v0.

assert (v1, v2, v3) == (1, 2, 3)

assert tree.materialize(v0) == [2, 1, 3, 0, 4, 2]
assert tree.materialize(v1) == [2, 1, 7, 0, 4, 2]
assert tree.materialize(v2) == [2, 1, 7, 0, 1, 2]
assert tree.materialize(v3) == [2, 9, 3, 0, 4, 2]

assert tree.sum_range(v0, 1, 5) == 8
assert tree.sum_range(v1, 1, 5) == 12
assert tree.sum_range(v2, 1, 5) == 9
assert tree.sum_range(v3, 1, 5) == 16

assert tree.delta_sum(v0, v1, 1, 5) == 4
assert tree.delta_sum(v1, v2, 1, 5) == -3
assert tree.delta_sum(v2, v3, 1, 5) == 7
```

Cùng một root `v0` được dùng làm đầu vào cho `v1` và `v3`; các cập nhật không sửa `v0`.

### 10.3. Cập nhật cộng thêm

```python
v4 = tree.add(v3, 0, -5)

assert tree.materialize(v4) == [-3, 9, 3, 0, 4, 2]
assert tree.get(v3, 0) == 2
assert tree.get(v4, 0) == -3
assert tree.sum_range(v4, 0, 6) == 15
```

Cài đặt `add` dùng hai đường tìm kiếm: đọc giá trị cũ rồi gọi `set`, tức `O(\log(n+1))` + `O(\log(n+1))` = `O(\log(n+1))`. Có thể viết `point_add` chuyên biệt để chỉ đi một lần, nhưng tính chất bất biến và độ phức tạp tiệm cận không đổi.

### 10.4. Cập nhật no-op và chia sẻ cấu trúc

```python
same = tree.set(v0, 2, 3)  # Giá trị đã là 3.

assert tree.materialize(same) == tree.materialize(v0)
assert tree._root(same) is tree._root(v0)

root0 = tree._root(v0)
root1 = tree._root(v1)

assert root0 is not None
assert root1 is not None
assert root0 is not root1

# n=6, root chia tại index 3. Sửa index 2
# không đụng tới cây con bên phải [3,6).
assert root0.right is root1.right
```

**Quan sát:** Root giống nhau về identity có nghĩa là cùng đối tượng được dùng cho hai ID. Nhưng root khác nhau không nhất thiết có dữ liệu khác: hai cây có thể cùng dữ liệu nhưng xây độc lập.

### 10.5. Rỗng và lỗi chỉ số

```python
empty = PersistentRangeSum([])

assert empty.version_count == 1
assert empty.materialize(0) == []
assert empty.sum_range(0, 0, 0) == 0

try:
    empty.set(0, 0, 7)
except IndexError:
    pass
else:
    raise AssertionError("Không thể sửa index của mảng rỗng")

try:
    tree.sum_range(v0, 4, 3)
except IndexError:
    pass
else:
    raise AssertionError("left>right phải báo lỗi")
```

Không được nhầm ***lỗi đoạn không hợp lệ*** với ***đoạn rỗng hợp lệ***: `[2,2)` trả tổng `0`; `[4,3)` có thứ tự đầu mút sai nên ví dụ chọn báo lỗi.

## 11. Xác thực cây và các phiên bản độc lập

### 11.1. Validator phải tính lại từ lá

Một mã sai có thể lưu root.total đúng nhưng tổng ở cây con bị sai. Vì vậy, validator không chỉ kiểm tổng tại gốc mà cần:

1. Xác thực cây nhị phân theo phân hoạch `[l,r)`.
2. Mỗi nút trong có đủ hai con.
3. Lá không có con.
4. Tổng cha bằng tổng **tính lại từ các lá**, không chỉ đọc hai trường `total` có thể đều sai.
5. Không có chu trình hoặc một đối tượng nút xuất hiện hai vị trí trong **cùng một root**.

### 11.2. Validator hậu thứ tự

```python
def validate_sum_root(
    root: SumNode | None, n: int
) -> bool:
    if type(n) is not int or n < 0:
        return False

    if n == 0:
        return root is None

    if root is None:
        return False

    seen = set()
    actual = {}
    stack = [(root, 0, n, False)]

    while stack:
        node, lo, hi, ready = stack.pop()

        if not isinstance(node, SumNode):
            return False

        marker = id(node)

        if not ready:
            if marker in seen:
                return False
            seen.add(marker)

            if type(node.total) is not int:
                return False

            if hi - lo == 1:
                if node.left is not None or node.right is not None:
                    return False

                actual[marker] = node.total
                continue

            if node.left is None or node.right is None:
                return False

            mid = (lo + hi) // 2
            stack.append((node, lo, hi, True))
            stack.append((node.right, mid, hi, False))
            stack.append((node.left, lo, mid, False))

        else:
            expected = (
                actual[id(node.left)]
                + actual[id(node.right)]
            )

            if node.total != expected:
                return False

            actual[marker] = expected

    return True
```

Dùng `id(node)` để theo dõi **định danh nút vật lý**, tránh so sánh đệ quy toàn cây. Giữa các root phiên bản khác nhau được phép dùng chung nút, nên validator khởi tạo `seen` mới cho **mỗi lần kiểm một root**.

### 11.3. Đối chiếu với mảng tham chiếu

```python
values = [2, 1, 3, 0, 4, 2]
tree = PersistentRangeSum(values)
reference = [values[:]]

actions = [
    ("set", 0, 2, 7),
    ("set", 1, 4, 1),
    ("set", 0, 1, 9),
    ("add", 2, 0, -3),
    ("add", 3, 5, 8),
]

for operation, parent, index, x in actions:
    candidate = reference[parent][:]

    if operation == "set":
        candidate[index] = x
        new_version = tree.set(parent, index, x)
    else:
        candidate[index] += x
        new_version = tree.add(parent, index, x)

    reference.append(candidate)
    assert new_version == len(reference) - 1

    # Kiểm tất cả bản cũ, không chỉ bản mới.
    for version, expected in enumerate(reference):
        assert validate_sum_root(
            tree._root(version), len(values)
        )
        assert tree.materialize(version) == expected

        for left, right in [(0, 0), (0, 6), (1, 5), (3, 6)]:
            assert tree.sum_range(version, left, right) == (
                sum(expected[left:right])
            )
```

Các đoạn trên là **mã thực hành người học tự chạy**; không phải kết quả một bộ test chuyên môn đã chạy trong bước biên soạn.

## 12. Từ tổng lịch sử tới thống kê thứ tự lịch sử

Một mục tiêu khác là:

> Cho dãy gốc `A=[a_0,a_1,\ldots,a_{n-1}]`, tìm **phần tử nhỏ thứ `k`** trong đoạn vị trí `A[l:r]`.

Ví dụ:

```text
A = [5, 1, 5, 2, 7, 2, 4]

A[1:6] = [1, 5, 2, 7, 2]
Sắp tăng = [1, 2, 2, 5, 7]
Kết quả phần tử nhỏ thứ 3 = 2
```

Một cây tổng trên **vị trí** không đủ trả kết quả này: tổng của một đoạn không cho biết phân bố giá trị.

Ta dùng một loại cây đoạn **khác cách phân hoạch**:

- Lá tương ứng **giá trị hoặc hạng giá trị**, không phải chỉ số vị trí.
- Mỗi nút lưu **số lần xuất hiện** của những giá trị thuộc vùng nó quản lý.
- Mỗi phiên bản `P_i` đại diện **tần suất của tiền tố `A[0:i]`**.

Kỹ thuật này thường được gọi là **persistent frequency segment tree** hoặc *Chairman tree* trong một số tài liệu/giải thuật.

### 12.1. Tiền tố tần suất là những phiên bản nào?

Định nghĩa:

\[
P_0=\text{cây tần suất rỗng}.
\]

\[
P_i=\text{cây tần suất của }A[0:i]\quad(0\le i\le n).
\]

Từ `P_i`, thêm **một lần xuất hiện** của `A[i]` để tạo `P_{i+1}`:

\[
P_{i+1}=\text{addCount}(P_i,A[i],1).
\]

Danh sách root:

```text
P0: {}
P1: {5:1}
P2: {1:1, 5:1}
P3: {1:1, 5:2}
P4: {1:1, 2:1, 5:2}
...
Pn: tần suất của toàn bộ A
```

Những phiên bản này có **quan hệ tuyến tính, tăng tần suất đúng một đơn vị ở mỗi bước**. Đây là điều kiện quan trọng để lấy hiệu hai cây sau này.

### 12.2. Tại sao hiệu hai tiền tố cho đúng tần suất đoạn?

Với mỗi giá trị `x`:

\[
count_{P_r}(x)
=\#\{i:0\le i<r,\ A[i]=x\}.
\]

\[
count_{P_l}(x)
=\#\{i:0\le i<l,\ A[i]=x\}.
\]

Lấy hiệu:

\[
\boxed{
count_{A[l:r]}(x)=count_{P_r}(x)-count_{P_l}(x).
}
\]

Vì `[0,r)=[0,l)\cup[l,r)` và hai đoạn không giao nhau nên công thức đúng.

**Không cần tạo một cây mới thực sự bằng cách trừ hai cây.** Khi duyệt đồng thời hai root, ta lấy **hiệu trường count của hai nút tương ứng** ở mỗi bước.

### 12.3. Ví dụ số đếm

Với `A=[5,1,5,2,7,2,4]`, lấy `l=1,r=6`:

```text
P6 chứa tiền tố [5,1,5,2,7,2].
P1 chứa tiền tố [5].

P6 - P1 có tần suất:
value 1 → 1
value 2 → 2
value 4 → 0
value 5 → 1
value 7 → 1

Tổng số phần tử: 1+2+0+1+1=5=r-l.
```

Danh sách tăng: `[1,2,2,5,7]`. Phần tử nhỏ thứ `3` là `2`.

### 12.4. Cần cẩn thận với số lần xuất hiện trùng

Nếu `A=[2,2,2]`, cả ba vị trí đều chứa giá trị `2`. Trong truy vấn `k`-th trên **đa tập**, ba bản sao được đếm **ba lần**:

```text
A[0:3] sorted = [2,2,2].
k=1, k=2, k=3 đều trả 2.
```

Đừng nhầm **phần tử thứ `k` có tính trùng** với **giá trị phân biệt thứ `k`**.

## 13. Nén tọa độ: biến giá trị thành miền chỉ số nhỏ

### 13.1. Tại sao cần nén?

Một dãy có thể chứa giá trị:

```text
[-1_000_000_000, 42, 9_000_000_000, 42]
```

Không thể xây cây đoạn đầy đủ cho mọi số nguyên giữa giá trị nhỏ nhất và lớn nhất vì miền quá rộng.

Ta lấy **tập giá trị phân biệt**, sắp tăng, rồi gán rank:

```text
sorted_unique = [-1_000_000_000, 42, 9_000_000_000]

rank(-1_000_000_000) = 0
rank(42)             = 1
rank(9_000_000_000)  = 2
```

Với `m` giá trị phân biệt, ta xây cây đoạn trên rank:

\[
[0,m).
\]

### 13.2. Nén phải bảo toàn thứ tự

Tìm phần tử nhỏ thứ `k` cần thứ tự giá trị. Vì vậy rank phải tuân theo:

\[
x<y\Rightarrow rank(x)<rank(y).
\]

Không được gán rank theo **thứ tự xuất hiện đầu tiên** rồi cho rằng rank nhỏ là giá trị nhỏ. Nén bằng `sorted(set(values))` đảm bảo tính thứ tự.

### 13.3. Các bước chi phí

Với dãy có `n` phần tử, `m≤n` giá trị phân biệt:

- Lấy tập, sắp: `O(n\log(n+1))` theo mô hình so sánh.
- Xây bảng `value→rank`: `O(m)`.
- Chèn `n` lần vào cây tần suất: `O(n\log(m+1))` nút mới và thời gian.
- Mỗi truy vấn `k`-th: `O(\log(m+1))`.

**Giới hạn:** nén tọa độ theo **toàn bộ dãy đã biết** là giải pháp phù hợp cho bài **offline**. Nếu sau đó xuất hiện một giá trị mới chưa có trong bảng, không thể nhét nó tùy ý vào rank cũ mà vẫn bảo toàn thứ tự. Có thể cần thu thập trước các giá trị cập nhật, xây lại nén, hoặc dùng một cây trên miền giá trị động.

## 14. Truy vấn phần tử thứ `k` từ hai root

### 14.1. Ý tưởng chọn nhánh

Tại cùng một nút đại diện một khoảng rank `[lo,hi)`, có hai phiên bản:

```text
right_root = P_r
left_root  = P_l
```

Số phần tử của đoạn `A[l:r]` nằm trong **nửa miền rank bên trái** bằng:

\[
\boxed{
leftCount=
count(P_r.left)-count(P_l.left).
}
\]

Nếu:

- `k≤leftCount`: phần tử thứ `k` nằm trong nửa trái.
- `k>leftCount`: bỏ qua `leftCount` phần tử nhỏ hơn ở trái, đi phải với `k'=k-leftCount`.

Khi còn một rank `[t,t+1)`, trả giá trị `sorted\_unique[t]`.

### 14.2. Mã giả

```text
KTH(right_root, left_root, lo, hi, k):
    require 1 <= k <= count(right_root)-count(left_root)

    if hi-lo == 1:
        return value_by_rank[lo]

    m = (lo+hi)//2

    left_count =
        COUNT(right_root.left) - COUNT(left_root.left)

    if k <= left_count:
        return KTH(right_root.left, left_root.left,
                   lo, m, k)

    return KTH(right_root.right, left_root.right,
               m, hi, k-left_count)
```

Ta không đi về hai bên cùng lúc, mà **chỉ đi một đường** theo vị trí thứ hạng.

### 14.3. Truy vết

Lấy `A[1:6]` trong ví dụ:

```text
Dãy đoạn = [1,5,2,7,2]
Tần suất rank của [1,2,4,5,7]:
[1,2,0,1,1]
```

Nếu cây gốc chia rank `[0,5)` tại `mid=2`:

- Nửa trái `[0,2)` chứa các giá trị `1,2`, tổng tần suất `1+2=3`.
- Với `k=3`, `3≤leftCount=3`, đi trái.
- Nửa `[0,2)` chia tại `1`:
  - Rank `0` (giá trị `1`) có count `1`.
  - `k=3>1`, đi phải với `k'=2`.
- Đến lá rank `1`, giá trị `2` có tần suất `2`, trả **`2`**.

**Kết quả đúng:** `kth(1,6,3)=2`.

### 14.4. Điều kiện phải kiểm

- `0≤l<r≤n`: đoạn phải **không rỗng** nếu yêu cầu k-th.
- `1≤k≤r-l`.
- Dãy ban đầu và tất cả prefix roots xây từ **cùng bảng nén tọa độ**.
- Mỗi bước tiền tố tăng một đơn vị ở đúng một giá trị; khi lấy hiệu, count của từng miền là số nguyên **không âm**.
- Phải dùng `P_r-P_l`, không lấy ngược `P_l-P_r`.

Nếu gọi `kth(2,2,1)` thì đoạn rỗng, không tồn tại phần tử thứ nhất: ví dụ chọn báo `IndexError`.

## 15. Vì sao không thể lấy hiệu tùy ý hai phiên bản?

### 15.1. Các bản full persistence có thể rẽ nhánh

Giả sử hai cây tần suất được tạo từ cùng một base rỗng:

```text
left_branch : {1:1}
right_branch: {2:1}
```

Nếu lấy `count(right)-count(left)` theo từng giá trị:

```text
value 1: 0 - 1 = -1
value 2: 1 - 0 = +1
```

Đây **không phải tần suất của một đa tập** vì xuất hiện count âm. Cộng tổng lại được `0`, càng cho thấy không thể coi đó là một đoạn chứa một phần tử.

### 15.2. Ngay cả quan hệ tổ tiên cũng chưa đủ nếu có xóa

Giả sử `P_a` có một bản sao của giá trị `3`, phiên bản hậu duệ `P_b` xóa giá trị `3`. Khi trừ `P_b-P_a`, count tại giá trị `3` là `-1`.

Vì thế không thể dùng hiệu hai phiên bản ấy làm **đa tập** để tìm phần tử nhỏ thứ `k`.

### 15.3. Điều kiện đúng của “Chairman tree” tiền tố

Trong bài toán dãy tĩnh:

\[
P_{i+1}=P_i+\{\text{một lần xuất hiện của }A[i]\}.
\]

Với `r≥l`, mỗi rank có:

\[
count(P_r)-count(P_l)\ge 0.
\]

Ngoài ra:

\[
count(P_r)-count(P_l)=r-l
\]

ở gốc. Đó là lý do hiệu hai prefix roots chính xác là **tần suất của đoạn vị trí**, và phép chọn nhánh luôn hợp lệ.

**Kết luận quan trọng:** kỹ thuật “hai root trừ nhau” không phải phép màu của persistence; nó đúng do **bất biến tích lũy theo tiền tố của mô hình dữ liệu**.

## 16. Cài đặt Python: cây tần suất persistent theo tiền tố

### 16.1. Cây thưa chỉ tạo những nhánh cần dùng

Khác cây tổng ban đầu có đủ lá cho mảng, phiên bản `P_0` của cây tần suất là **rỗng**, mọi giá trị có count `0`. Một cây con chưa từng có phần tử có thể dùng `None`. Mỗi lần thêm một phần tử:

- Tăng count trên đường từ gốc tới rank của giá trị đó.
- Tạo nút mới trên đường đi; những nhánh còn lại được chia sẻ.
- Không sửa các nút của phiên bản tiền tố trước.

Ranh giới rank được truyền vào hàm đệ quy, không cần lưu trên từng nút.

### 16.2. Nút đếm và phép tăng một lần xuất hiện

```python
from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_left, bisect_right


@dataclass(frozen=True, slots=True, eq=False)
class FreqNode:
    count: int
    left: FreqNode | None = None
    right: FreqNode | None = None


def count_of(node: FreqNode | None) -> int:
    return 0 if node is None else node.count


def insert_one(
    node: FreqNode | None,
    lo: int,
    hi: int,
    rank: int,
) -> FreqNode:
    """Tăng count một đơn vị tại rank; không sửa node cũ.

    Điều kiện: lo <= rank < hi.
    """
    if hi - lo == 1:
        return FreqNode(count=count_of(node) + 1)

    mid = (lo + hi) // 2
    old_left = None if node is None else node.left
    old_right = None if node is None else node.right

    if rank < mid:
        new_left = insert_one(old_left, lo, mid, rank)
        return FreqNode(
            count=count_of(node) + 1,
            left=new_left,
            right=old_right,
        )

    new_right = insert_one(old_right, mid, hi, rank)
    return FreqNode(
        count=count_of(node) + 1,
        left=old_left,
        right=new_right,
    )
```

Mỗi bước từ `P_i` sang `P_{i+1}` tăng một count trong đúng một lá và tất cả tổ tiên của nó:

\[
count(root_{i+1})=count(root_i)+1.
\]

Cây con `None` là phần tử không có lần xuất hiện nào.

### 16.3. Đếm các rank nhỏ hơn một mốc

```python
def count_rank_prefix(
    node: FreqNode | None,
    lo: int,
    hi: int,
    bound: int,
) -> int:
    """Tổng số phần tử có rank < bound."""
    if node is None or bound <= lo:
        return 0

    if hi <= bound:
        return node.count

    mid = (lo + hi) // 2
    return (
        count_rank_prefix(node.left, lo, mid, bound)
        + count_rank_prefix(node.right, mid, hi, bound)
    )
```

Với cây phân hoạch cân bằng, phép đếm tiền tố rank chạy trong `O(\log(m+1))`. Nó dùng các nhánh được phủ toàn bộ thay vì đi hết mọi lá.

### 16.4. Lớp `PrefixKth`

```python
class PrefixKth:
    def __init__(self, values: list[int]):
        if any(type(x) is not int for x in values):
            raise TypeError("Giá trị phải là int")

        self.n = len(values)
        self.sorted_values = sorted(set(values))
        self.m = len(self.sorted_values)

        rank_of = {
            value: rank
            for rank, value in enumerate(self.sorted_values)
        }

        # roots[i] là tần suất tiền tố values[0:i].
        self.roots: list[FreqNode | None] = [None]

        for value in values:
            new_root = insert_one(
                self.roots[-1],
                0,
                self.m,
                rank_of[value],
            )
            self.roots.append(new_root)

    def _check_range(self, left: int, right: int):
        if (
            type(left) is not int
            or type(right) is not int
            or not 0 <= left <= right <= self.n
        ):
            raise IndexError("Đoạn ngoài [0,n]")

    def kth(self, left: int, right: int, k: int) -> int:
        """Giá trị nhỏ thứ k (1-based) trên values[left:right]."""
        self._check_range(left, right)
        if (
            type(k) is not int
            or not 1 <= k <= right - left
        ):
            raise IndexError("k ngoài [1,right-left]")

        lo, hi = 0, self.m
        left_root = self.roots[left]
        right_root = self.roots[right]

        while hi - lo > 1:
            mid = (lo + hi) // 2

            ll = None if left_root is None else left_root.left
            rl = None if right_root is None else right_root.left
            left_count = count_of(rl) - count_of(ll)

            if k <= left_count:
                left_root = ll
                right_root = rl
                hi = mid
            else:
                k -= left_count
                left_root = (
                    None if left_root is None else left_root.right
                )
                right_root = (
                    None if right_root is None else right_root.right
                )
                lo = mid

        return self.sorted_values[lo]

    def count_lt(
        self, left: int, right: int, x: int
    ) -> int:
        """Số phần tử < x trong đoạn [left,right)."""
        self._check_range(left, right)
        if type(x) is not int:
            raise TypeError("x phải là int")

        bound = bisect_left(self.sorted_values, x)
        return (
            count_rank_prefix(
                self.roots[right], 0, self.m, bound
            )
            - count_rank_prefix(
                self.roots[left], 0, self.m, bound
            )
        )

    def count_le(
        self, left: int, right: int, x: int
    ) -> int:
        """Số phần tử <= x trong đoạn [left,right)."""
        self._check_range(left, right)
        if type(x) is not int:
            raise TypeError("x phải là int")

        bound = bisect_right(self.sorted_values, x)
        return (
            count_rank_prefix(
                self.roots[right], 0, self.m, bound
            )
            - count_rank_prefix(
                self.roots[left], 0, self.m, bound
            )
        )

    def count_between(
        self,
        left: int,
        right: int,
        low: int,
        high: int,
    ) -> int:
        """Đếm các giá trị thuộc đoạn đóng [low,high]."""
        self._check_range(left, right)
        if type(low) is not int or type(high) is not int:
            raise TypeError("Hai cận phải là int")
        if low > high:
            return 0

        return (
            self.count_le(left, right, high)
            - self.count_lt(left, right, low)
        )
```

Ở `kth`, hai root được đi **đồng thời**. Phép hiệu count bên trái định hướng nhánh; ở nhánh phải phải giảm `k` đi đúng số phần tử của nhánh trái.

### 16.5. Truy vết

```python
a = [5, 1, 5, 2, 7, 2, 4]
tree = PrefixKth(a)

assert len(tree.roots) == len(a) + 1
assert count_of(tree.roots[0]) == 0
assert count_of(tree.roots[6]) == 6
assert count_of(tree.roots[7]) == 7

# A[1:6] = [1,5,2,7,2], sorted = [1,2,2,5,7].
assert tree.kth(1, 6, 1) == 1
assert tree.kth(1, 6, 2) == 2
assert tree.kth(1, 6, 3) == 2
assert tree.kth(1, 6, 4) == 5
assert tree.kth(1, 6, 5) == 7

assert tree.count_lt(1, 6, 5) == 3
assert tree.count_le(1, 6, 5) == 4
assert tree.count_between(1, 6, 2, 5) == 3

assert tree.kth(0, 1, 1) == 5
assert tree.kth(6, 7, 1) == 4
```

### 16.6. Âm, trùng và mảng rỗng

```python
tree = PrefixKth([-10, 3, -10, 3, 0])

assert tree.kth(0, 5, 1) == -10
assert tree.kth(0, 5, 2) == -10
assert tree.kth(0, 5, 3) == 0
assert tree.kth(0, 5, 4) == 3
assert tree.kth(0, 5, 5) == 3

assert tree.count_lt(0, 5, 0) == 2
assert tree.count_le(0, 5, 0) == 3

empty = PrefixKth([])
assert empty.roots == [None]
assert empty.count_lt(0, 0, 10) == 0

try:
    empty.kth(0, 0, 1)
except IndexError:
    pass
else:
    raise AssertionError("Đoạn rỗng không có k-th")
```

**Điểm quan trọng:** giá trị phần tử có thể âm; điều cần không âm là **số lần xuất hiện và hiệu count của các cây tiền tố**, không phải bản thân các giá trị.

### 16.7. Đối chiếu với thuật toán sắp trực tiếp

```python
a = [5, 1, 5, 2, 7, 2, 4]
tree = PrefixKth(a)

for left in range(len(a) + 1):
    for right in range(left, len(a) + 1):
        expected = sorted(a[left:right])

        for k in range(1, len(expected) + 1):
            assert tree.kth(left, right, k) == expected[k - 1]

        for x in [-1, 1, 2, 4, 5, 7, 10]:
            assert tree.count_lt(left, right, x) == sum(
                value < x for value in a[left:right]
            )
            assert tree.count_le(left, right, x) == sum(
                value <= x for value in a[left:right]
            )
```

Đây là **mã kiểm tra tham chiếu cho người học tự chạy**, không phải tuyên bố đã thực thi các test khi biên soạn bài.

## 17. Chứng minh tính đúng của `k`-th hai root

### 17.1. Quy nạp cho quá trình xây prefix root

Base `P_0` có mọi count bằng `0`, biểu diễn đúng tiền tố rỗng.

Giả sử `P_i` biểu diễn đúng tần suất `A[0:i]`. Khi thêm một bản sao của `A[i]`:

- Count ở lá rank đó tăng một.
- Count ở các tổ tiên tăng một.
- Các nhánh khác giữ nguyên.
- Phiên bản `P_i` không bị sửa.

Suy ra `P_{i+1}` biểu diễn đúng `A[0:i+1]`.

### 17.2. Hiệu count là số phần tử đoạn

Với một tập rank bất kỳ tương ứng một cây con `S`:

\[
count_{P_r}(S)-count_{P_l}(S)
=\#\{i:l\le i<r,\ rank(A[i])\in S\}.
\]

Bởi `[0,r)` chứa đúng hai phần không giao nhau `[0,l)` và `[l,r)`, hiệu ở vế trái là một **số nguyên không âm**.

Ở gốc:

\[
count(P_r)-count(P_l)=r-l.
\]

### 17.3. Bước chọn nhánh đúng

Giả sử trong miền rank hiện tại có `c` phần tử và cần tìm phần tử nhỏ thứ `k`, `1≤k≤c`.

Gọi `c_L` là số phần tử ở nửa rank bên trái. Do mọi rank trái nhỏ hơn mọi rank phải:

- `k≤c_L`: phần tử cần tìm nằm bên trái, giữ `k`.
- `k>c_L`: bỏ `c_L` phần tử nhỏ hơn, đi bên phải với `k-c_L`.

Tại lá, mọi phần tử còn lại có **cùng rank**, nên trả giá trị theo bảng nén. Theo quy nạp qua số tầng, thuật toán luôn trả đúng phần tử nhỏ thứ `k`, **có tính các bản sao trùng lặp**.

### 17.4. Khi chứng minh không còn hợp lệ

Không thể thay `P_l,P_r` bằng hai root tùy ý nếu:

- Chúng không là hai tiền tố của **cùng một dãy**.
- Các bước cập nhật có xóa khiến hiệu count của nhánh có thể âm.
- Chúng dùng hai bảng nén tọa độ **khác nhau**.
- Thứ tự lấy hiệu bị đảo.
- `k` vượt số phần tử thực của đoạn.

Một cây persistent dùng được cho nhiều phiên bản **không tự bảo đảm** phép hiệu hai root mô tả một đa tập hợp lệ.

## 18. Chi phí của cây tần suất tiền tố

Đặt:

- `n`: độ dài dãy.
- `m`: số giá trị phân biệt (`m≤n`).
- Mỗi phép so sánh/cập nhật số nguyên cơ bản có chi phí `O(1)`.

| Thao tác | Thời gian | Bộ nhớ/nút mới |
|---|---:|---:|
| Thu thập, sắp và nén giá trị | `O(n\log(n+1))` | `O(m)` bảng nén |
| Tạo `P_0` | `O(1)` | `O(1)` |
| Thêm một phần tử | `O(\log(m+1))` | `O(\log(m+1))` nút |
| Tạo `n+1` prefix roots | `O(n\log(m+1))` sau nén | `O(n\log(m+1))` nút và `O(n)` root |
| `kth(l,r,k)` | `O(\log(m+1))` | `O(1)` phụ (vòng lặp) |
| `count_lt / count_le` | `O(\log(m+1))` | `O(\log(m+1))` stack |
| `count_between` | `O(\log(m+1))` | `O(\log(m+1))` stack |

Tổng bộ nhớ các cây, root và bảng nén:

\[
\boxed{O(n\log(m+1)+m+n).}
\]

Nếu `m=1`, mỗi lần thêm chỉ tạo một lá, tương ứng chi phí hằng cho một cập nhật.

Nếu có ít truy vấn, lấy `sorted(A[l:r])` có thể đơn giản hơn. Với **rất nhiều truy vấn thứ hạng đoạn trên một dãy tĩnh**, chi phí tiền xử lý được phân bổ cho nhiều lần `kth` nhanh.

## 19. Biến thể và giới hạn nâng cao

### 19.1. Đếm trên một miền giá trị

Số phần tử trong đoạn vị trí `[l,r)` có giá trị thuộc đoạn đóng `[a,b]` là:

\[
count_{[l,r)}([a,b])
=
countLE(l,r,b)-countLT(l,r,a).
\]

Vì thế có thể trả lời count theo miền giá trị trên cùng một cây tần suất prefix.

### 19.2. Trung vị và phân vị

Với đoạn có độ dài `s=r-l>0`:

- **Trung vị dưới**: thứ hạng `k=\lfloor(s+1)/2\rfloor`.
- **Trung vị trên**: thứ hạng `k=\lfloor s/2\rfloor+1`.

Khi `s` lẻ, hai thứ hạng trùng nhau. Khi `s` chẵn, chúng có thể khác.

Ví dụ đoạn đã sắp `[1,2,8,10]`:

```text
lower median: k=2 → 2
upper median: k=3 → 8
```

Nếu định nghĩa trung vị số học là trung bình hai số giữa, cần lấy **cả hai** rồi tính trung bình; đó là quy ước thống kê riêng, không phải tự động do cây quyết định.

### 19.3. Không được trừ số lượng giá trị phân biệt của hai prefix

Giả sử:

```text
P1 = [5]              distinct=1
P2 = [5,5]            distinct=1

Đoạn A[1:2] = [5]     distinct=1
distinct(P2)-distinct(P1)=0  # SAI.
```

“Distinct count” không tuyến tính theo phép nối hai đa tập có trùng giá trị. Cây tần suất đếm đúng số **lần xuất hiện**, nhưng không thể lấy hiệu hai trường distinct của prefix để suy ra distinct của đoạn.

### 19.4. Cây thưa trên miền số lớn

Nếu giá trị mới có thể xuất hiện sau thời điểm xây cây và không thể nén tọa độ offline, có thể xây một **dynamic/sparse segment tree** trên một miền rộng.

Ưu điểm: không cần bảng nén cố định. Đổi lại, độ cao phụ thuộc **độ rộng miền số nguyên hoặc độ dài biểu diễn bit**, cần cận miền và chi phí con trỏ/bộ nhớ phù hợp. Không thể cho một cây có miền hữu hạn cố định tự chứa **mọi số nguyên không giới hạn**.

### 19.5. Persistent lazy propagation

Để cộng `delta` vào cả một đoạn vị trí, có thể dùng node với:

```text
sum
lazy_add
left
right
```

Nếu đoạn có độ dài `len`:

\[
sum'=sum+\Delta\cdot len.
\]

Nhưng khi cần truyền `lazy_add` xuống dưới, **không được sửa trực tiếp các nút con có thể đang được phiên bản cũ chia sẻ**.

Có thể:

- Sao chép nút và con cần cập nhật rồi xử lý lazy theo hướng thuần.
- Hoặc mang tag tích lũy trong lời gọi truy vấn mà không ghi vào cây.
- Định nghĩa rõ phép hợp thành tag, cách cập nhật `sum` và thời điểm tính lại.

Một persistent lazy segment tree được thiết kế đúng có thể giữ truy vấn/cập nhật đoạn `O(\log(n+1))` trên miền cố định, nhưng cách `push` và số nút sao chép phức tạp hơn cập nhật một điểm trong bài.

### 19.6. Nhiều phiên bản không đồng nghĩa có lịch sử sự kiện

Lưu root giúp truy vấn **trạng thái tại phiên bản**. Nhưng nếu hai lần cập nhật triệt tiêu nhau, hai snapshot có thể giống hệt nhau dù lịch sử thao tác khác.

Nếu cần audit trail, thời điểm thực hiện, người thao tác hoặc loại sự kiện, phải lưu thêm **metadata/lịch sử thao tác** bên ngoài cây.

### 19.7. Metadata gộp khác tổng

Có thể lưu `min`, `max`, `gcd`, count hoặc nhiều trường trong mỗi nút nếu phép gộp từ hai con được xác định. Path copying vẫn giữ nguyên nguyên tắc **tạo nút mới trên đường thay đổi**.

Nhưng không phải mọi metadata đều hỗ trợ mọi phép cập nhật lazy. Phải chứng minh riêng công thức **gộp kết quả** và công thức **biến đổi do cập nhật**.

## 20. Quy trình chọn thiết kế cho bài toán lịch sử

### 20.1. Câu hỏi đầu tiên: lịch sử “thời điểm” hay “tiền tố”?

Nếu hệ thống hỏi:

> Tổng doanh thu ở các cửa hàng 10–20 vào **snapshot ngày hôm qua** là bao nhiêu?

thì mô hình phù hợp là **mảng theo vị trí và root snapshot**, sử dụng tổng đoạn ở phiên bản tương ứng.

Nếu hệ thống hỏi:

> Trong **các giao dịch từ vị trí l đến r-1**, số tiền lớn thứ k là bao nhiêu?

và toàn bộ dãy giao dịch **đã biết**, mô hình phù hợp có thể là **các prefix roots của cây tần suất**, sau khi nén tọa độ.

Cả hai đều dùng nhiều root, nhưng không thay thế công thức của nhau.

### 20.2. Câu hỏi thứ hai: có cập nhật về sau không?

- **Dãy tĩnh, rất nhiều truy vấn `k`-th:** prefix frequency tree rất phù hợp.
- **Mảng thường xuyên được sửa điểm và hỏi tổng lịch sử:** persistent range-sum tree.
- **Muốn sửa điểm và hỏi `k`-th trên mọi đoạn ở các snapshot động:** cần cấu trúc phức tạp hơn, có thể là sự kết hợp của cây theo vị trí và cây theo giá trị, hoặc thuật toán offline phù hợp; không thể chỉ dùng hai prefix root được xây cho mảng ban đầu mà bỏ qua các cập nhật.
- **Chỉ hỏi trạng thái mới nhất:** segment tree mutable có thể đơn giản hơn.

### 20.3. Câu hỏi thứ ba: một version có thể rẽ nhánh không?

Với mảng snapshot, API có thể cho:

```text
v1 = set(v0, 2, 7)
v2 = set(v1, 4, 1)
v3 = set(v0, 1, 9)
```

Đây là full persistence đối với cập nhật điểm.

Với cây tần suất của dãy tĩnh, các prefix roots:

```text
P0 -> P1 -> P2 -> ... -> Pn
```

được xây theo thứ tự tiền tố. Mặc dù cấu trúc nút bất biến, phép trừ `P_r-P_l` **dựa vào tính chất tuyến tính và tích lũy** của dãy prefix. Việc tự ý tạo nhánh tần suất rồi lấy hiệu không còn mô tả đoạn vị trí của dãy ban đầu.

### 20.4. Câu hỏi thứ tư: phép tổng hợp có phù hợp không?

Một cấu trúc tăng cường chỉ hiệu quả khi thông tin trong nút **đủ để trả lời truy vấn**:

| Yêu cầu | Miền phân hoạch | Metadata cần | Điều kiện |
|---|---|---|---|
| Tổng đoạn ở snapshot | Chỉ số vị trí | `sum` | Phép cộng, đoạn nửa mở |
| Min/max đoạn ở snapshot | Chỉ số vị trí | `min/max` | Có sentinel cho đoạn rỗng |
| Đếm phần tử thuộc miền giá trị | Rank giá trị | `count` | Cùng bảng rank |
| K-th trên đoạn dãy tĩnh | Rank giá trị, nhiều prefix roots | `count` | Hiệu prefix count không âm |
| Trung vị trên đoạn dãy tĩnh | Như k-th | `count` | Quy ước median khi chẵn |
| Đếm số giá trị phân biệt trên đoạn | Thường cần cấu trúc khác | Không đủ nếu chỉ trừ distinct(prefix) | Xử lý giá trị xuất hiện lặp qua hai prefix |
| Tổng lịch sử trên nhiều nhánh | Vị trí, root theo phiên bản | `sum` | Cần biết ID/root snapshot |

Một cây đoạn persistent là **khung cấu trúc**, còn các trường tăng cường và bất biến phải chọn theo truy vấn.

## 21. Những lỗi dễ gặp và cách phát hiện

1. **Sửa `node.total` tại chỗ.** Cây con đó có thể đang được phiên bản cũ dùng chung.
2. **Sửa `left/right` của nút cũ khi cập nhật.** Các root cũ mất tính bất biến.
3. **Chỉ tạo lá mới mà không tạo tổ tiên.** Gốc mới không có đường tới lá mới.
4. **Sao chép toàn cây sau mỗi cập nhật rồi gọi đó là yêu cầu của persistence.** Path copying chỉ cần đường ảnh hưởng.
5. **Tạo root mới nhưng quên lưu ID/root cũ.** Không còn cách truy vấn lịch sử.
6. **Chỉ giữ một biến root và overwrite nó.** Hành vi trở lại ephemeral nếu không giữ snapshot.
7. **Không phân biệt segment `[l,r)` với `[l,r]`.** Gây lỗi lệch một và tính sai độ dài.
8. **Truy vấn `[l,l)` rồi cố đọc một lá.** Đoạn rỗng phải có kết quả theo monoid, với tổng là `0`.
9. **Nhầm `set(i,x)` với `add(i,x)`.** Một phép ghi đè, một phép cộng thêm.
10. **Không kiểm tra ID phiên bản.** Có thể đọc nhầm root hoặc phát sinh lỗi khó hiểu.
11. **Cho rằng version ID lớn hơn đồng nghĩa là hậu duệ.** Lịch sử có thể rẽ nhánh.
12. **Cho rằng root khác identity nghĩa là mảng khác nội dung.** Có thể một no-op hoặc hai cây xây độc lập.
13. **Cho rằng hai nút cùng `sum` thì mọi lá giống nhau.** `[1,4]` và `[2,3]` đều có tổng `5`.
14. **Truy vấn lịch sử bằng `roots[-1]` thay vì root được yêu cầu.** Chỉ trả trạng thái mới nhất.
15. **Cập nhật một nhánh từ phiên bản cũ nhưng lại xuất phát từ root mới nhất.** Lịch sử phân nhánh bị sai.
16. **Gọi validator sau mọi cập nhật rồi báo tổng thời gian là `O(\log n)`.** Validator `O(n)` thuộc kiểm thử, không phải đường vận hành.
17. **Cho rằng nút frozen tự đóng băng một payload dạng list.** Bất biến bề mặt không đủ nếu payload còn mutable.
18. **Lưu cả `l,r` trên từng node mà không thực sự cần.** Có thể tăng bộ nhớ không cần thiết; ở cây cố định, ranh giới có thể là tham số đệ quy.
19. **Quên rằng mảng có thể rỗng.** Không được gọi build cho đoạn `[0,0)` như một nút thật.
20. **Bỏ qua kiểu `bool` khi kiểm int Python.** Có thể nhận `True` như chỉ số `1` ngoài ý định API.
21. **Dùng cây tổng vị trí để trả k-th bằng `sum`.** Tổng không chứa phân bố giá trị.
22. **Dùng prefix frequency tree mà không nén tọa độ theo thứ tự.** K-th theo rank không còn là k-th theo giá trị.
23. **Nén theo thứ tự xuất hiện thay vì thứ tự tăng giá trị.** Tìm k-th cho kết quả sai.
24. **Không tính các giá trị trùng nhiều lần.** K-th trên đa tập đếm mọi bản sao.
25. **Cho rằng giá trị âm không dùng được trong cây tần suất.** Count phải không âm, còn giá trị có thể âm.
26. **Dùng `P_l-P_r` thay vì `P_r-P_l`.** Có thể tạo count âm.
27. **Lấy hiệu hai root tần suất bất kỳ rồi coi là một đoạn dãy.** Cần quan hệ tiền tố tích lũy.
28. **Cho rằng hai phiên bản có quan hệ tổ tiên là đủ cho k-th hai root khi có xóa.** Count có thể giảm; hiệu âm.
29. **Không kiểm `1≤k≤r-l`.** Có thể đi xuống một nhánh không chứa phần tử thứ k.
30. **Gọi k-th trên đoạn rỗng.** Không có phần tử thứ nhất.
31. **Tạo `P_1` bằng tần suất của cả dãy.** Prefix root `P_i` phải chứa đúng `i` phần tử đầu.
32. **Quên rằng cần `n+1` prefix roots, gồm `P_0` rỗng.** Dễ bị lệch chỉ số truy vấn.
33. **Nhầm nén tọa độ với hash không giữ thứ tự.** Map rank phải bảo toàn quan hệ nhỏ/lớn.
34. **Dùng hai bảng nén khác nhau cho hai root đem trừ.** Các nhánh không còn đại diện cùng vùng giá trị.
35. **Xuất hiện giá trị mới sau nén nhưng tự gán rank bừa.** Có thể làm hỏng thứ tự.
36. **Lấy hiệu distinct count của hai prefix để ra distinct đoạn.** Tính phân biệt không tuyến tính theo phép nối.
37. **Tính `left_count` từ cùng một root thay vì từ hiệu hai root.** Thuật toán sẽ tìm k-th của một tiền tố, không phải đoạn.
38. **Đi phải mà quên giảm `k` đi `left_count`.** Thứ hạng trong nhánh phải sai.
39. **Khi có count bằng `0` vẫn ép đi xuống nút `None`.** Chỉ được đi vào nhánh chứa thứ hạng hợp lệ.
40. **Cho rằng prefix kth hỗ trợ cập nhật A[i] ở mọi snapshot chỉ bằng append một prefix root.** Cập nhật động đổi tần suất của nhiều đoạn tiền tố, cần thiết kế khác.
41. **Đánh đồng số vị trí `n` với số giá trị phân biệt `m`.** Cây rank có độ cao theo `m` nhưng vẫn cần `n` prefix roots.
42. **Bỏ qua bộ nhớ cho tất cả root.** Dù mỗi root chỉ là một tham chiếu, có `O(V)` metadata.
43. **Bỏ root cũ và cho rằng mọi nút mà nó từng dùng đều được giải phóng.** Nút còn được root khác chia sẻ vẫn sống.
44. **Giữ mọi root vô hạn nhưng không có chính sách tài nguyên.** Bộ nhớ vẫn tăng theo số nút mới.
45. **Quảng cáo persistence tự có transaction hay lưu bền sau mất điện.** Cần cơ chế commit/storage/đồng bộ riêng.
46. **Cho rằng lazy push có thể sửa con trực tiếp.** Trong cây persistent, con có thể được nhiều phiên bản dùng chung.
47. **Cho rằng metadata đúng sau point set thì tự đúng cho range add.** Lazy cần luật cập nhật và hợp thành tag.
48. **Không nêu thứ hạng `k` là 1-based hay 0-based.** Bài dùng 1-based.
49. **Tìm trung vị đoạn chẵn mà không định nghĩa lower/upper/average.** Có nhiều quy ước hợp lệ.
50. **So sánh hai snapshot chỉ qua tổng gốc để kết luận mọi phần tử giống nhau.** Trạng thái khác có thể có cùng tổng.

## 22. Bài tập thực hành có đáp án

### Bài 1. Phân biệt persistent và mutable

Một cây đoạn cập nhật trực tiếp trường `sum` trên đường tới lá. Có thể đọc chính xác trạng thái trước đó chỉ bằng lưu tham chiếu root cũ không?

**Đáp án:** **Không**. Root cũ có thể trỏ tới những nút vừa bị thay đổi. Cần nút bất biến/path copying hoặc cơ chế lưu phiên bản khác.

### Bài 2. Đường cập nhật

Cho cây đoạn của mảng bốn phần tử. Cập nhật `A[2]` tạo nút mới ở những đoạn nào?

**Đáp án:** Các đoạn `[2,3)`, `[2,4)` và `[0,4)`. Những nhánh khác có thể chia sẻ.

### Bài 3. Số nút mới

Một cây đoạn cân bằng có độ cao `h` theo số cạnh. Point update path copying tạo bao nhiêu nút mới trong bản đơn giản?

**Đáp án:** Tối đa **`h+1`**, một nút trên mỗi tầng gốc–lá, tức `O(\log(n+1))`.

### Bài 4. Tổng cây mới

Với `A=[2,1,3,0]`, cập nhật chỉ số `2` thành `7`. Tổng gốc cũ và mới?

**Đáp án:** Gốc cũ **`6`**, gốc mới **`10`**. Phiên bản cũ không thay đổi.

### Bài 5. Truy vấn đoạn nửa mở

Với `A=[2,1,3,0,4,2]`, tổng `A[1:5]` là bao nhiêu?

**Đáp án:** **`8`** vì `1+3+0+4=8`.

### Bài 6. Hai phiên bản

Nếu thay `A[2]=7` để có `v1`, tổng `A[1:5]` của `v1` là bao nhiêu?

**Đáp án:** **`12`**, vì đoạn mới là `[1,7,0,4]`.

### Bài 7. Từ phiên bản 1 đến phiên bản 2

Từ `v1`, thay `A[4]=1`. Tổng `[1,5)` ở `v2`?

**Đáp án:** **`9`**, từ `[1,7,0,1]`.

### Bài 8. Rẽ nhánh

Từ `v0`, thay `A[1]=9` để có `v3`. `v3` có tự mang thay đổi `A[2]=7` ở `v1` không?

**Đáp án:** **Không**. `v3` lấy `v0` làm nền; `A[2]` vẫn bằng `3`.

### Bài 9. Hiệu tổng hai phiên bản

Với ví dụ bài 5–8, `sum(v3,1,5)-sum(v2,1,5)` bằng bao nhiêu?

**Đáp án:** **`16-9=7`**. Hai phiên bản ở hai nhánh; hiệu là thay đổi trạng thái, không phải số thao tác.

### Bài 10. No-op

Gọi `set(v0,2,3)` khi `A[2]` đã bằng `3`. Có cần tạo nút mới không?

**Đáp án:** **Không** nếu triển khai có kiểm tra no-op; có thể lưu một ID mới trỏ tới chính root cũ.

### Bài 11. Root cùng identity

Nếu `roots[a] is roots[b]` và nút bất biến, có thể khẳng định gì?

**Đáp án:** Hai phiên bản cùng trỏ tới **một cây vật lý**, nên dữ liệu theo mọi đoạn giống nhau.

### Bài 12. Root khác identity

Nếu `roots[a] is not roots[b]`, có chắc mảng khác nội dung không?

**Đáp án:** **Không**. Hai cây có thể biểu diễn cùng mảng nhưng được tạo từ những đường sao chép khác nhau.

### Bài 13. Tổng bằng nhau

Hai mảng `[1,4]` và `[2,3]` có cùng tổng `5`. Điều này có chứng minh chúng là cùng snapshot không?

**Đáp án:** **Không**. Muốn biết các phần tử khác nhau, phải so sâu hoặc dùng metadata bảo đảm nhận diện nội dung phù hợp.

### Bài 14. Thời gian cập nhật điểm

Trên cây đoạn có độ dài `n`, point update persistent có thời gian và nút mới bậc nào?

**Đáp án:** **`O(\log(n+1))`** cho thời gian và số nút cấp phát thêm trong mô hình chuẩn.

### Bài 15. Tổng bộ nhớ nhiều bản

Xây một cây tổng với `n` phần tử và lưu `U` bản cập nhật điểm, `V` root. Chặn trên bộ nhớ?

**Đáp án:** **`O(n+U\log(n+1)+V)`** dưới giả thiết mỗi nút có số trường hằng.

### Bài 16. Dãy rỗng

Một `PersistentRangeSum([])` có thể trả kết quả gì cho `sum(0,0,0)`?

**Đáp án:** **`0`**. Nhưng `set(0,0,x)` không hợp lệ vì không tồn tại vị trí.

### Bài 17. Phân biệt set và add

Mảng đang có `A[2]=3`. `set(2,5)` và `add(2,5)` tạo giá trị mới lần lượt là gì?

**Đáp án:** **`5`** và **`8`**.

### Bài 18. Cây tần suất quản lý miền nào?

Trong mô hình `PrefixKth`, lá cây đại diện cho **chỉ số vị trí** hay **rank của giá trị**?

**Đáp án:** **Rank của giá trị** sau nén tọa độ. Chỉ số vị trí được thể hiện qua thứ tự các root tiền tố.

### Bài 19. Số prefix roots

Dãy `A` có `n=7` phần tử. Cần bao nhiêu prefix roots tính cả tiền tố rỗng?

**Đáp án:** **`8`**, từ `P0` đến `P7`.

### Bài 20. Tần suất của đoạn

Với `P_r` và `P_l` đúng theo dãy tiền tố, tần suất của giá trị `x` trong `A[l:r]` là gì?

**Đáp án:**

\[
count_{P_r}(x)-count_{P_l}(x).
\]

### Bài 21. Tính thứ hạng

Với `A=[5,1,5,2,7,2,4]`, sắp `A[1:6]` rồi lấy phần tử nhỏ thứ `3`.

**Đáp án:** `A[1:6]=[1,5,2,7,2]`, sắp được `[1,2,2,5,7]`; kết quả **`2`**.

### Bài 22. Trùng lặp

Với `A=[2,2,2]`, truy vấn `kth(0,3,3)` trả gì?

**Đáp án:** **`2`** vì cả ba lần xuất hiện được đếm trong đa tập.

### Bài 23. Tần suất đoạn bằng hiệu prefix

Trong dãy `[5,1,5,2,7,2,4]`, giá trị `2` xuất hiện bao nhiêu lần ở đoạn `[1,6)`?

**Đáp án:** **`2` lần**.

### Bài 24. Đếm nhỏ hơn ngưỡng

Với `A[1:6]=[1,5,2,7,2]`, có bao nhiêu phần tử nhỏ hơn `5`?

**Đáp án:** **`3`**, gồm `1,2,2`.

### Bài 25. Đếm ≤ ngưỡng

Cũng đoạn trên, có bao nhiêu phần tử `≤5`?

**Đáp án:** **`4`**, gồm `1,2,2,5`.

### Bài 26. Count trong miền giá trị

Với đoạn ở bài 24, có bao nhiêu giá trị thuộc `[2,5]`?

**Đáp án:** **`3`**, gồm `2,2,5`.

### Bài 27. Nén tọa độ

Nén tăng dần dãy `[10^9,-3,10^9,8]`. Rank của `-3`, `8`, `10^9` lần lượt là?

**Đáp án:** **`0,1,2`** vì bảng đã sắp là `[-3,8,10^9]`.

### Bài 28. Vì sao không dùng thứ tự xuất hiện?

Nếu lấy rank theo thứ tự phần tử gặp đầu tiên, vì sao k-th có thể sai?

**Đáp án:** Rank không bảo toàn quan hệ **nhỏ hơn giữa giá trị**. K-th dựa vào thứ tự rank nên phải nén theo thứ tự tăng.

### Bài 29. Count nửa trái

Một truy vấn có `k=5` và `left_count=3`. Đi nhánh nào và k mới là bao nhiêu?

**Đáp án:** **Đi phải**, với `k'=5-3=2`.

### Bài 30. Không đủ phần tử

Nếu đoạn dài `4` mà hỏi `k=5`, hàm k-th nên làm gì?

**Đáp án:** **Báo lỗi**, vì thứ hạng hợp lệ chỉ từ `1` đến `4`.

### Bài 31. Hiệu tần suất âm

Một root có tần suất `{1:1}` và root khác `{2:1}`. Lấy hiệu root thứ hai trừ root thứ nhất có biểu diễn một đa tập không?

**Đáp án:** **Không**, vì count của giá trị `1` là `-1`. Hiệu hai root tùy ý không thể dùng như tần suất đoạn.

### Bài 32. Quan hệ tổ tiên có đủ không?

Một phiên bản có một bản sao `3` rồi phiên bản con xóa `3`. Lấy count con trừ count cha có dùng để tìm k-th của một tập thêm mới không?

**Đáp án:** **Không**. Count ở rank `3` là `-1`, vi phạm điều kiện tần suất không âm.

### Bài 33. Cần cùng bảng nén

Nếu `P_l` và `P_r` dùng hai bảng nén rank khác nhau, lấy hiệu count ở cùng vị trí rank có ý nghĩa gì?

**Đáp án:** **Không đáng tin**: hai lá cùng rank có thể đại diện cho hai giá trị khác nhau.

### Bài 34. K-th với giá trị âm

Với `A=[-10,3,-10,3,0]`, `kth(0,5,3)` là bao nhiêu?

**Đáp án:** **`0`**, từ dãy đã sắp `[-10,-10,0,3,3]`.

### Bài 35. Trung vị chẵn

Một đoạn đã sắp là `[1,2,8,10]`. Trung vị dưới, trung vị trên và trung vị số học lần lượt là?

**Đáp án:** **`2`, `8` và `5`**. Cần chọn quy ước theo yêu cầu.

### Bài 36. Distinct count

Tại sao `distinct(P_r)-distinct(P_l)` không luôn là số giá trị phân biệt trong `A[l:r]`?

**Đáp án:** Một giá trị có thể xuất hiện ở cả phần `[0,l)` và phần `[l,r)`. Ví dụ `[5]` rồi `[5,5]` đều có distinct count `1`, hiệu `0` nhưng đoạn mới có `1` giá trị phân biệt.

### Bài 37. Độ phức tạp k-th

Với `m` giá trị phân biệt, một truy vấn `kth(l,r,k)` trên hai prefix roots tốn thời gian bao nhiêu?

**Đáp án:** **`O(\log(m+1))`**, vì mỗi tầng chỉ đi một nhánh theo hiệu count.

### Bài 38. Độ phức tạp xây prefix roots

Dãy có `n` phần tử và `m` giá trị phân biệt, chi phí tạo các prefix roots sau bước nén?

**Đáp án:** **`O(n\log(m+1))`** thời gian và nút mới, cộng `O(n)` tham chiếu root.

### Bài 39. Lazy persistence

Vì sao không được dùng một hàm `push` sửa trực tiếp hai con của một nút có lazy tag trong cây persistent?

**Đáp án:** Hai con có thể đang được phiên bản cũ chia sẻ. Phải sao chép nút/con cần sửa hoặc xử lý tag thuần.

### Bài 40. Chọn cấu trúc

Ứng dụng A hỏi tổng bán hàng theo vùng ở nhiều snapshot sau các cập nhật điểm; ứng dụng B có một dãy giao dịch tĩnh và hàng triệu truy vấn k-th theo đoạn. Nên chọn gì?

**Đáp án:** A cân nhắc **persistent range-sum segment tree theo vị trí**; B cân nhắc **persistent frequency segment tree theo prefix và rank giá trị**. Cần dựa trên workload, bộ nhớ và loại cập nhật thực tế.

## 23. Checklist khi triển khai cây đoạn nhiều phiên bản

- [ ] Phân biệt truy vấn lịch sử snapshot với truy vấn đoạn dãy tĩnh bằng prefix frequency roots.
- [ ] Định nghĩa kiểu phiên bản: tuyến tính hay có thể rẽ nhánh từ bản cũ.
- [ ] Lưu root cho mỗi phiên bản cần truy vấn.
- [ ] Nút và payload được chia sẻ là bất biến.
- [ ] Cập nhật điểm tạo nút mới từ lá lên gốc, không ghi vào nút cũ.
- [ ] Có tối ưu no-op nếu cần để tránh cấp phát không cần thiết.
- [ ] Phân hoạch `[l,r)`, chỉ số 0-based và điều kiện rỗng được nêu rõ.
- [ ] Metadata có phần tử trung hòa và phép gộp phù hợp.
- [ ] Test các đoạn đầy đủ, một phần tử, rỗng và đầu mút sát n.
- [ ] Test cả phiên bản trước và sau khi cập nhật.
- [ ] Có validator độc lập kiểm tra phân hoạch và metadata từng nút.
- [ ] Nêu đúng chi phí build, point update, query, tổng bộ nhớ nhiều bản.
- [ ] Với k-th, xác định rank theo giá trị tăng dần; có bảng nén chung.
- [ ] Xây đúng `n+1` prefix roots, bắt đầu từ cây tần suất rỗng.
- [ ] Hiệu count dùng `P_r-P_l` và cần có tần suất không âm ở mọi nhánh.
- [ ] Thứ hạng `k` 1-based, phải thỏa `1≤k≤r-l`.
- [ ] Giá trị trùng được đếm theo số lần xuất hiện.
- [ ] Không áp dụng hai-root-kth cho mọi cặp snapshot có chèn/xóa tùy ý.
- [ ] Nếu có giá trị mới chưa được nén, đã có chính sách mở rộng/chuyển cấu trúc.
- [ ] Nếu cần lazy, có thuật toán push/apply thuần và chứng minh bảo trì metadata.
- [ ] Có chính sách giữ/bỏ root và quản lý vòng đời bộ nhớ.
- [ ] Nếu dùng đa luồng hoặc lưu bền, có cơ chế công bố root/commit riêng.

## 24. Tổng kết

**Cây đoạn nhiều phiên bản (persistent segment tree)** phát triển từ cây đoạn thông thường bằng cách **giữ mỗi snapshot qua một tham chiếu root**. Khi cập nhật một điểm:

1. Tìm đường từ gốc tới lá tương ứng vị trí cần sửa.
2. Tạo nút mới cho lá và các tổ tiên chịu ảnh hưởng.
3. Dùng lại các cây con không thay đổi.
4. Trả root mới, đồng thời mọi root cũ vẫn hợp lệ.

Trên mảng độ dài `n` với phân hoạch cân bằng:

\[
\boxed{
\text{Point update: }O(\log(n+1))\text{ thời gian và nút mới}
}
\]

\[
\boxed{
\text{Range query ở một version: }O(\log(n+1))
}
\]

Giữ `U` cập nhật điểm và `V` root cần bộ nhớ bậc:

\[
\boxed{O(n+U\log(n+1)+V).}
\]

Một ứng dụng khác dùng **cây tần suất theo tiền tố**. Với dãy tĩnh, root `P_i` lưu tần suất của `A[0:i]`. Do các tiền tố chỉ **tích lũy bằng thêm một lần xuất hiện**, hiệu count `P_r-P_l` là số lần xuất hiện trong `A[l:r]`. Nhờ đó có thể tìm **phần tử nhỏ thứ `k`**, có tính trùng, trong `O(\log(m+1))` với `m` giá trị phân biệt sau nén tọa độ.

Điều quan trọng nhất không phải chỉ là “có nhiều root”, mà là **bất biến của dữ liệu được mỗi root biểu diễn**:

- Với cây tổng lịch sử, một root là **một snapshot mảng**, có thể cập nhật từ phiên bản cũ bất kỳ.
- Với cây tần suất tiền tố, một root là **tần suất của một tiền tố**; hiệu hai root hợp lệ vì các tiền tố **lồng nhau và không giảm số đếm**.
- Với hai phiên bản tùy ý có chèn/xóa hoặc các nhánh độc lập, hiệu count có thể âm, nên **không thể tự xem đó là một đa tập**.

Hiểu đúng sự khác nhau giữa phân hoạch **theo vị trí** và **theo giá trị**, giữa truy vấn snapshot và truy vấn hiệu prefix, cùng chi phí sao chép đường đi sẽ giúp lựa chọn cấu trúc dữ liệu **đúng về bất biến, hiệu quả về thời gian và bộ nhớ, và hỗ trợ được những truy vấn lịch sử mà ứng dụng thực sự cần**.

# Duy trì thông tin cây con sau chèn, xóa và quay

## 1. Tại sao cây tăng cường phải chăm sóc metadata sau mỗi lần sửa?

Một **cây tăng cường (augmented tree)** là cây nền được bổ sung thông tin tại các nút để tăng tốc truy vấn. Ví dụ, trong cây tìm kiếm nhị phân (BST), ta có thể lưu:

- `size(u)`: số nút thuộc cây con gốc `u`, **bao gồm `u`**;
- `total(u)`: tổng khóa số trong cây con gốc `u`;
- `height(u)`: chiều cao cây con gốc `u`, tính theo **số cạnh**.

Giữ các trường này đúng giúp thực hiện những việc như tìm **khóa nhỏ thứ `k`**, đếm số khóa trước `x`, tính tổng một đoạn khóa, hoặc điều chỉnh cân bằng theo chiều cao.

Nhưng khi **chèn, xóa hoặc xoay cây**, các cây con thay đổi. Nếu chỉ sửa con trỏ mà quên tính lại metadata, cây có thể vẫn trông như BST hợp lệ nhưng truy vấn tăng cường sẽ trả kết quả sai.

Ví dụ, trước khi thêm `5`:

```text
              8                         size(8)=3
             / \
            4  12                       total(8)=24
```

Sau khi thêm `5` làm con phải của `4`:

```text
              8
             / \
            4  12
             \
              5

Số nút thực: 4, tổng khóa thực: 29.
```

Nếu `size(8)` vẫn bằng `3` hoặc `total(8)` vẫn bằng `24`, những kết quả dùng metadata sẽ sai. Việc **cập nhật toàn bộ thông tin phụ bị ảnh hưởng** là một phần của chính thao tác chèn, không phải việc tùy chọn làm sau.

Bài này tập trung vào kỹ thuật bảo trì metadata sau:

1. **Chèn** nút mới vào BST.
2. **Xóa** nút lá, nút một con và nút hai con.
3. **Quay/xoay cây (rotation)** để tái cân bằng.
4. **Xoay kép** và tích hợp bảo trì metadata vào một cây AVL minh họa.

Mục tiêu là có một quy tắc thao tác và chứng minh rõ ràng, thay vì dùng các phép `size += 1` hoặc `total -= key` rải rác dễ bị bỏ sót.

## 2. Bất biến nền và bất biến thông tin cây con

### 2.1. Cây nền được dùng trong bài

Ta xét **BST lưu khóa nguyên phân biệt**:

\[
\forall u:\qquad
\text{mọi khóa bên trái }<key(u)<\text{mọi khóa bên phải}.
\]

Khi cần cân bằng, ta sử dụng **AVL tree**, tức BST có thêm ràng buộc:

\[
-1\le height(u.left)-height(u.right)\le 1
\]

tại **mọi** nút.

Một BST không cân bằng có thể cao tới `n-1` cạnh với `n` nút. Cây AVL duy trì chiều cao `O(\log n)`; chính sự cân bằng này, chứ không phải việc lưu `size`, tạo ra chặn trên logarit cho đường đi tìm kiếm.

### 2.2. Quy ước chính thức của ba trường

Với cây rỗng:

\[
size(\varnothing)=0,\quad total(\varnothing)=0,\quad height(\varnothing)=-1.
\]

Với nút `u` có hai cây con `L=u.left` và `R=u.right`:

\[
\boxed{size(u)=1+size(L)+size(R)}
\]

\[
\boxed{total(u)=key(u)+total(L)+total(R)}
\]

\[
\boxed{height(u)=1+\max(height(L),height(R))}
\]

**Theo quy ước đếm cạnh:** lá có `height=0`. Nếu tài liệu khác tính chiều cao theo số nút, cây rỗng có thể lấy `0` và lá có chiều cao `1`; không được pha hai quy ước trong cùng thuật toán.

Ví dụ:

```text
                    20
                   /  \
                 10    30
                / \   / \
               5  15 25 35

key   size  total  height
5       1     5      0
15      1    15      0
10      3    30      1
25      1    25      0
35      1    35      0
30      3    90      1
20      7   140      2
```

Ở gốc:

\[
size(20)=1+3+3=7;
\quad total(20)=20+30+90=140;
\quad height(20)=1+\max(1,1)=2.
\]

### 2.3. Hai nhóm bất biến phải đúng đồng thời

| Nhóm | Nội dung | Hậu quả nếu vi phạm |
|---|---|---|
| **Cấu trúc/BST** | Một cây không chu trình, khóa bên trái nhỏ hơn khóa gốc, khóa bên phải lớn hơn | Tìm theo khóa, `rank`, `select` có thể đi sai |
| **Thông tin tăng cường** | `size`, `total`, `height` bằng đúng công thức từ cây con **hiện tại** | Đếm, tổng, xếp hạng hoặc quyết định xoay sai |
| **Cân bằng AVL** | Chênh lệch chiều cao hai nhánh tại mọi nút không quá `1` | Có thể mất bảo đảm chiều cao `O(\log n)` |

Một đoạn mã có thể sửa BST đúng nhưng quên metadata, hoặc giữ metadata đúng mà phá cấu trúc BST. Phải kiểm tra **từng bất biến**, không suy ra cái này từ cái kia.

## 3. Quy tắc nền tảng: tính lại một nút từ hai con đúng

Tại mỗi nút, chỉ cần một phép **tổng hợp cục bộ** (*pull / recompute*):

```text
PULL(u):
    u.size   ← 1 + size(u.left) + size(u.right)
    u.total  ← key(u) + total(u.left) + total(u.right)
    u.height ← 1 + max(height(u.left), height(u.right))
```

Đặc điểm quan trọng:

- `PULL(u)` chỉ đọc dữ liệu nút `u` và ba trường từ **hai cây con trực tiếp**.
- Nếu mỗi trường có kích thước cố định và phép cộng/so sánh mất `O(1)`, một lần `PULL` tốn **`O(1)`**.
- **Tiền điều kiện:** hai cây con đã có metadata đúng sau thay đổi.
- **Hậu điều kiện:** metadata tại `u` đúng với các liên kết mới.

Vì vậy, sau khi sửa ở một vị trí sâu, ta **tính từ dưới lên**:

```text
                     gốc
                      ▲  3. pull(gốc)
                      │
                   tổ tiên
                      ▲  2. pull(tổ tiên)
                      │
                cha của nút sửa
                      ▲  1. pull(cha)
                      │
                 nút được sửa
```

### 3.1. Tại sao không tính cha trước?

Giả sử cha `p` đọc `size(child)=3`, nhưng cây con vừa được chèn thêm một nút và thực tế có `4` nút. Nếu gọi `pull(p)` trước `pull(child)`, cha sẽ **sao chép lỗi** từ con. Sau đó dù `child` được sửa đúng, `p` vẫn còn cũ.

**Thứ tự phụ thuộc dữ liệu:** con → cha → ông/bà → ... → gốc.

### 3.2. Có thể chỉ cộng/trừ chênh lệch không?

Một số thao tác đơn giản cho phép tăng nhanh:

```text
Sau chèn khóa 5 vào cây:
size(ancestor)  += 1
total(ancestor) += 5
```

Nhưng cách này dễ sai khi:

- Chèn **khóa trùng** bị từ chối.
- Xóa nút có **hai con** rồi thay khóa bằng kế nhiệm.
- Xoay đơn hoặc xoay kép, khiến **tập nút tại từng nút quay** thay đổi.
- Thay giá trị hoặc trọng số mà không thay số nút.
- Có thêm metadata không có phép nghịch đảo đơn giản, như `min`, `max` hay `height`.

Vì thế **ưu tiên dùng một hàm `pull` thống nhất** cho mỗi nút bị ảnh hưởng, thay vì các phép tăng/giảm rời rạc. Chỉ dùng cập nhật chênh lệch khi đã chứng minh được bất biến và xử lý đầy đủ các tình huống.

## 4. Xác định đúng những nút bị ảnh hưởng

**Không phải mọi nút đều cần cập nhật sau mỗi thao tác.** Đó là lý do cây tăng cường có thể hoạt động hiệu quả.

### 4.1. Chèn/xóa không xoay

Khi thay đổi một nhánh con, những nút có tập hậu duệ hoặc đường cao nhất có thể đổi chính là các **tổ tiên trên đường từ vị trí sửa tới gốc**.

Ví dụ thêm khóa `13` vào cây:

```text
            20
           /  \
         10    30
        / \   / \
       5  15 25 35
          /
         13

Vị trí bị sửa: dưới 15
Đường pull: 15 → 10 → 20
Các cây con gốc 5, 25, 35, 30 không đổi.
```

**Không cần duyệt toàn bộ cây `O(n)`** sau mỗi lần chèn. Chiều dài đường sửa phụ thuộc chiều cao `h`:

- BST bất kỳ: tối đa `O(h+1)`, có thể `O(n)`.
- AVL/Red–Black với chiến lược bảo trì đúng: `O(\log n)`.

### 4.2. Khi thay đổi khóa mà không đổi liên kết

Nếu một nút đổi `key` thành giá trị khác, **total** của nó và các tổ tiên có thể đổi, còn **size** không đổi. Nhưng không được chỉ sửa metadata rồi giữ nguyên vị trí khóa nếu điều đó phá **bất biến BST**.

Với một BST, thay khóa thường cần xóa khóa cũ và chèn khóa mới hoặc dùng một phép cập nhật đã chứng minh duy trì thứ tự. Nếu `key` là mã dùng để sắp xếp nhưng `total` tổng hợp một `weight` riêng, thay đổi `weight` có thể giữ cấu trúc BST và chỉ cần bảo trì metadata dọc đường tổ tiên.

### 4.3. Khi xoay cây

Phép xoay không thêm/xóa khóa, nhưng **tập nút trong cây con gốc tại các nút xoay thay đổi**. Vì thế:

- Metadata ở **các nút tham gia xoay** cần tính lại.
- Metadata ở những cây con không bị thay đổi vẫn có thể giữ nguyên.
- Đối với `size` và `total`, tổng hợp tại gốc mới của toàn vùng xoay bằng tổng hợp của gốc cũ trước xoay, vì **tập khóa vùng xoay không đổi**.
- Đối với `height`, hình dạng mới có thể thay đổi chiều cao vùng xoay, nên tổ tiên ở bên trên có thể cần kiểm tra và cập nhật.

Đây là lý do thứ tự cập nhật khi xoay phải được thiết kế cùng thuật toán tái cân bằng.

## 5. Chèn nút: bảo trì từ lá mới lên gốc

### 5.1. Tình huống không cần xoay

Bắt đầu với cây bảy khóa ở mục 2. Chèn khóa `13`:

```text
Trước:                              Sau:

          20                               20
        /    \                           /    \
      10      30                        10      30
     /  \    /  \                      /  \    /  \
    5   15  25  35                    5   15  25  35
                                          /
                                         13
```

Khóa `13` đi theo đường:

```text
13 < 20 → trái tới 10
13 > 10 → phải tới 15
13 < 15 → trái rỗng → chèn
```

Nút mới có:

\[
size(13)=1,\quad total(13)=13,\quad height(13)=0.
\]

Các nút được tính lại từ dưới lên:

| Nút | Trước chèn (size, total, height) | Sau chèn (size, total, height) |
|---|---|---|
| `15` | `(1,15,0)` | `(2,28,1)` |
| `10` | `(3,30,1)` | `(4,43,2)` |
| `20` | `(7,140,2)` | `(8,153,3)` |

**Kiểm tra:** đúng `8` nút, tổng khóa `140+13=153`. Cây vẫn thỏa AVL: tại gốc, hai chiều cao con là `2` và `1`, chênh nhau `1`. Không cần xoay.

### 5.2. Cây AVL có thể cần xoay ngay sau chèn

Nếu chèn `30,20,10` theo thứ tự:

```text
Sau khi chèn 10, trước xoay:      Sau xoay phải:

          30                            20
         /                             /  \
        20                            10   30
       /
      10
```

Tại nút `30`, chiều cao hai con lần lượt là `1` và `-1`, chênh `2` nên vi phạm AVL.

Sau khi nối nút `10`:

1. Tính đúng metadata của `20` và `30` theo cấu trúc hiện tại.
2. Nhận biết `balance(30)=2`.
3. Thực hiện **xoay phải** tại `30`.
4. Tính lại metadata của các nút có con thay đổi **theo thứ tự đúng**.
5. Trả về **gốc cây con mới `20`** để cha bên trên (nếu có) nối vào.

Các nút vẫn là `10,20,30`; không nút nào mất đi. Metadata cuối:

```text
node=10: size=1, total=10, height=0
node=30: size=1, total=30, height=0
node=20: size=3, total=60, height=1
```

### 5.3. Khi khóa đã tồn tại

Nếu chính sách BST không cho khóa trùng, chèn một khóa đã có phải trả kết quả **không thay đổi**:

- Không tạo nút mới.
- Không tăng `size`.
- Không cộng lại `total`.
- Không bắt buộc xoay hoặc tính lại metadata.

Một lỗi phổ biến là đi qua tổ tiên rồi cộng `size += 1` trước khi biết việc chèn có thành công hay không. Trong triển khai ở mục 9, phép chèn trả cờ `inserted` để quyết định có cần bảo trì hay không.

## 6. Xóa nút: ba trường hợp và đường cập nhật

Xóa BST phải giữ thứ tự khóa của cây **và** cập nhật metadata. Có ba trường hợp cấu trúc cơ bản.

### 6.1. Xóa lá

Xét cây:

```text
             20
            /  \
          10    30
         / \   / \
        5  15 25 35
```

Xóa lá `5` bằng cách cho `10.left=None`.

Trước xóa:
```text
size(10)=3, total(10)=30, height(10)=1
size(20)=7, total(20)=140, height(20)=2
```

Sau khi cập nhật từ dưới lên:

```text
size(10)=2, total(10)=25, height(10)=1
size(20)=6, total(20)=135, height(20)=2
```

Các cây con gốc `15`, `25`, `35`, `30` không đổi.

### 6.2. Xóa nút có đúng một con

Ví dụ:

```text
Trước xóa 10:              Sau xóa 10:

          20                       20
         / \                      / \
        10  30                   5   30
       /
      5
```

Ta nối liên kết của cha `20` tới con `5` thay vì `10`. **Tổng các khóa tại vùng cha thay đổi**: từ `20+10+5+30=65` thành `20+5+30=55`. Metadata của `5` và `30` vẫn đúng; metadata của `20` phải được tính lại.

Trong hàm đệ quy, khi nhánh con trả về gốc mới `5`, khung gọi của `20` nhận `node.left=5` rồi mới `pull(20)` hoặc `rebalance(20)`.

### 6.3. Xóa nút có hai con: thao tác phức tạp nhất

Với BST:

```text
                    20
                   /  \
                 10    30
                / \   / \
               5  15 25 35
```

Muốn xóa `20`, ta có thể chọn **nút kế nhiệm inorder** (khóa nhỏ nhất trong cây con phải). Ở đây kế nhiệm là `25`.

Một cách cài đặt là:

1. **Sao chép khóa `25`** lên vị trí nút `20`, làm gốc tạm mang khóa `25`.
2. **Xóa nút chứa `25` cũ** trong cây con phải.
3. Tính lại metadata của các nút trên đường xóa kế nhiệm và của **nút đã thay khóa**.
4. Nếu là AVL, tái cân bằng từ dưới lên tại những nút bị ảnh hưởng.

Trước:

```text
                    20
                   /  \
                 10    30
                / \   / \
               5  15 25 35
```

Sau:

```text
                    25
                   /  \
                 10    30
                / \      \
               5  15      35
```

Metadata tại gốc sau xóa:

\[
size=6,\qquad total=140-20=120.
\]

Metadata ở nhánh phải:

\[
size(30)=2,\qquad total(30)=30+35=65.
\]

**Chi tiết dễ bỏ sót:** trong chiến lược **chép khóa kế nhiệm**, dù số nút của vị trí gốc mới chỉ giảm một, **khóa tại nút gốc thay đổi từ `20` sang `25`**. Nếu trường `total` phụ thuộc vào khóa, phải tính lại sau thay đổi này. Chỉ giảm `size` mà giữ nguyên `total` của gốc sẽ sai.

Cũng cần chú ý nút kế nhiệm **không có con trái**, nhưng **có thể có con phải**. Khi xóa nút kế nhiệm ở vị trí cũ, phải nối con phải của nó vào đúng nơi, không được mặc định kế nhiệm luôn là lá.

### 6.4. Trường hợp khóa không tồn tại

Xóa một khóa không có trong cây phải trả cờ `removed=False` và **không làm thay đổi metadata**. Nếu luôn giảm `size` khi quay về từ đệ quy mà không kiểm tra kết quả, một lần xóa thất bại cũng đủ làm hỏng toàn bộ cây.

### 6.5. Duy trì metadata sau xóa có thể kéo theo nhiều lần xoay

Khác một số đường chèn AVL có thể dừng tái cân bằng sớm, **xóa** có thể làm giảm chiều cao cây con ở nhiều mức, khiến nhiều tổ tiên mất cân bằng. Một triển khai đúng tiếp tục kiểm tra và tái cân bằng **trên đường quay về gốc**.

Vì chiều cao AVL là `O(\log n)`, toàn bộ đường cập nhật vẫn có độ dài `O(\log n)`. Nhưng việc “đã xoay một lần thì chắc xong” **không phải quy tắc tổng quát cho xóa**.

## 7. Xoay trái/phải: không mất khóa, nhưng đổi cây con

Một phép **rotation** là một thay đổi liên kết cục bộ được dùng trong cây tự cân bằng để điều chỉnh hình dạng và giữ thứ tự inorder.

### 7.1. Xoay trái tại `x`

Giả sử `y=x.right`:

```text
Trước xoay trái:              Sau xoay trái:

         x                           y
        / \                         / \
       A   y                       x   C
          / \                     / \
         B   C                   A   B
```

Với bất biến BST, ta có thứ tự:

```text
mọi khóa A < key(x) < mọi khóa B < key(y) < mọi khóa C
```

Thứ tự inorder **trước và sau như nhau**. Nhưng:

- Trước xoay, cây con gốc `x` chứa `A,x,B,y,C`.
- Sau xoay, cây con gốc `x` **chỉ còn** `A,x,B`.
- Cây con gốc `y` sau xoay chứa trọn vùng cũ.

Do đó phải:

1. Sửa `x.right = B` và `y.left = x`.
2. **`pull(x)` trước** vì hai con mới của `x` đã sẵn sàng.
3. **`pull(y)` sau** vì `y.left=x`, nên `y` cần metadata mới của `x`.
4. Trả `y` làm **gốc mới của vùng xoay**.

**Nếu gọi `pull(y)` trước `pull(x)`,** trường của `y` sẽ đọc metadata cũ của `x` và có thể sai.

### 7.2. Xoay phải tại `y`

Tương tự, với `x=y.left`:

```text
Trước xoay phải:             Sau xoay phải:

         y                           x
        / \                         / \
       x   C                       A   y
      / \                             / \
     A   B                           B   C
```

Thứ tự thao tác:

1. `y.left = B`.
2. `x.right = y`.
3. **`pull(y)` trước**.
4. **`pull(x)` sau**.
5. Trả `x` làm gốc mới.

**Quy tắc nhớ:** luôn tính metadata của **nút bị đẩy xuống** trước, rồi mới tính **nút được nâng lên**.

### 7.3. Truy vết số liệu cụ thể

Cây ba khóa trước xoay phải:

```text
       30                  key  size  total  height
      /                    10     1    10      0
     20                    20     2    30      1
    /                      30     3    60      2
   10
```

Sau xoay:

```text
       20                  key  size  total  height
      /  \                 10     1    10      0
     10  30                30     1    30      0
                           20     3    60      1
```

Metadata tại **gốc mới** của vùng vẫn là `size=3`, `total=60`. Nhưng metadata tại **nút `30`** giảm từ `size=3` xuống `1` vì nó không còn chứa `20` và `10` trong cây con. Chiều cao của vùng giảm từ `2` xuống `1`.

Điều này giải thích vì sao không thể bỏ qua cập nhật cục bộ chỉ vì “phép xoay không làm thay đổi tập khóa toàn vùng”.

## 8. Xoay kép: cập nhật metadata theo từng phép xoay

Trong AVL có bốn tình huống mất cân bằng thường gọi là **LL, RR, LR và RL**.

| Trường hợp | Hình dạng mất cân bằng | Cách xử lý |
|---|---|---|
| **LL** | Nhánh trái cao, và nhánh trái của con trái cao hơn | Xoay phải |
| **RR** | Nhánh phải cao, và nhánh phải của con phải cao hơn | Xoay trái |
| **LR** | Nhánh trái cao, nhưng con trái nghiêng phải | Xoay trái ở con trái, rồi xoay phải |
| **RL** | Nhánh phải cao, nhưng con phải nghiêng trái | Xoay phải ở con phải, rồi xoay trái |

### 8.1. Ví dụ LR

Chèn lần lượt các khóa `30,10,20`:

```text
Ban đầu sau chèn:            Sau xoay trái ở 10:

       30                           30
      /                            /
     10                           20
       \                         /
        20                      10

Sau xoay phải ở 30:

       20
      /  \
     10   30
```

Ở mỗi phép xoay đơn, gọi `pull` theo đúng thứ tự. Xoay kép không cần một công thức metadata bí ẩn riêng:

1. `node.left = rotate_left(node.left)`.
2. `node = rotate_right(node)`.
3. Mỗi hàm xoay tự tính lại **hai nút** vừa đổi con.

Tổng số lần `pull` ở một lần xoay kép là hằng số, nên chi phí metadata **`O(1)`** cho vùng xoay, chưa tính việc đi lên và cập nhật các tổ tiên của vùng đó.

### 8.2. Ví dụ RL

Chèn `10,30,20`:

```text
Trước:                    Xoay phải ở 30:      Xoay trái ở 10:

      10                        10                    20
        \                         \                  /  \
         30                        20               10   30
        /                            \
       20                             30
```

Lần lượt:

1. `node.right = rotate_right(node.right)`.
2. `node = rotate_left(node)`.

### 8.3. Cẩn thận với xoay trong khi xóa

Khi **xóa** khỏi AVL, hệ số cân bằng của con nặng có thể bằng `0`. Trong trường hợp đó, cách quyết định xoay đơn/kép vẫn phải rõ:

- Nút lệch trái có `balance>1`: nếu con trái có `balance≥0`, xoay phải đơn; nếu `balance<0`, xoay trái con rồi xoay phải.
- Nút lệch phải có `balance<-1`: nếu con phải có `balance≤0`, xoay trái đơn; nếu `balance>0`, xoay phải con rồi xoay trái.

Sự khác biệt giữa `<0`, `>0` và điều kiện có dấu bằng rất dễ gây lỗi nếu chỉ nhớ sơ đồ chèn mà không xét xóa.

## 9. Python đầy đủ: AVL tăng cường `size`, `total` và `height`

Để có một ví dụ **có thể đọc và thực hành độc lập**, đoạn mã dưới đây gói gọn:

- Khởi tạo nút với metadata hợp lệ.
- Tính lại một nút từ hai con.
- Xoay trái và xoay phải.
- Cân bằng AVL với các trường hợp đơn/kép.
- Chèn khóa phân biệt.
- Xóa khóa, gồm cả **nút có hai con**.

**Phạm vi:** khóa là số nguyên có thứ tự, không có khóa trùng; `total` là tổng **khóa**. Thuật toán dùng đệ quy cho chèn/xóa, nhưng vì mọi trạng thái sau thao tác đều là AVL hợp lệ, chiều sâu lời gọi bị chặn bởi `O(\log n)` nếu đầu vào ban đầu hợp lệ. Không áp dụng trực tiếp cho đồ thị có chu trình hoặc một BST hỏng cân bằng.

### 9.1. Lớp nút và các hàm tổng hợp

```python
class AugNode:
    def __init__(self, key: int):
        self.key = key
        self.left = None
        self.right = None

        # Cây một nút: bất biến đúng ngay từ lúc tạo.
        self.size = 1
        self.total = key
        self.height = 0


def subtree_size(node):
    return 0 if node is None else node.size


def subtree_total(node):
    return 0 if node is None else node.total


def subtree_height(node):
    return -1 if node is None else node.height


def pull(node):
    """Tính lại metadata của một nút từ hai cây con đã đúng."""
    if node is None:
        return

    node.size = (
        1 + subtree_size(node.left) + subtree_size(node.right)
    )
    node.total = (
        node.key + subtree_total(node.left) + subtree_total(node.right)
    )
    node.height = (
        1 + max(subtree_height(node.left), subtree_height(node.right))
    )


def balance_factor(node):
    if node is None:
        return 0
    return (
        subtree_height(node.left) - subtree_height(node.right)
    )
```

Mọi thao tác thay đổi cây đều dùng **chung hàm `pull`**. Nếu sau này muốn thêm `min_key`, `max_key` hoặc một giá trị tổng hợp khác, cần mở rộng `pull` cùng các điều kiện tương ứng, thay vì sửa riêng từng nhánh chèn/xóa.

### 9.2. Hai phép xoay có cập nhật metadata

```python
def rotate_left(x):
    y = x.right
    if y is None:
        raise ValueError("Không thể xoay trái nếu thiếu con phải")

    middle = y.left
    x.right = middle
    y.left = x

    # Nút bị đẩy xuống trước, gốc mới sau.
    pull(x)
    pull(y)
    return y


def rotate_right(y):
    x = y.left
    if x is None:
        raise ValueError("Không thể xoay phải nếu thiếu con trái")

    middle = x.right
    y.left = middle
    x.right = y

    pull(y)
    pull(x)
    return x
```

Mỗi phép xoay chỉ sửa một số hằng các tham chiếu và chỉ gọi `pull` hai lần, nên có **`O(1)` thời gian và bộ nhớ phụ**.

Hàm **trả về gốc mới**. Mã gọi phải gán gốc này vào `node.left`, `node.right` hoặc biến `root` thích hợp. Nếu không gắn lại, cây có thể mất một phần liên kết dù các phép xoay cục bộ đã đúng.

### 9.3. Hàm tái cân bằng

```python
def rebalance(node):
    """Hai cây con đã cân bằng và có metadata đúng."""
    if node is None:
        return None

    # Đầu tiên tổng hợp thông tin mới từ hai con.
    pull(node)
    bf = balance_factor(node)

    if bf > 1:
        # Nặng bên trái: LL hoặc LR.
        if balance_factor(node.left) < 0:
            node.left = rotate_left(node.left)  # LR: bước 1
        return rotate_right(node)              # LL hoặc LR: bước cuối

    if bf < -1:
        # Nặng bên phải: RR hoặc RL.
        if balance_factor(node.right) > 0:
            node.right = rotate_right(node.right)  # RL: bước 1
        return rotate_left(node)                  # RR hoặc RL

    return node
```

**Tiền điều kiện:** trước khi gọi `rebalance(node)`, hai cây con của `node` đã được thao tác xong, cân bằng và có metadata đúng. Hàm sẽ:

1. Tính lại thông tin của `node`.
2. Đọc chiều cao hai con để xác định có lệch AVL hay không.
3. Thực hiện một hoặc hai phép xoay nếu cần.
4. Trả gốc cây con mới, với metadata đã được cập nhật.

Trong AVL hợp lệ trước một lần chèn/xóa thông thường, mỗi mức trở về đệ quy chỉ cần số hữu hạn xoay như trên. Với các trường cục bộ `size/total/height`, chi phí mỗi lần gọi `rebalance` là **`O(1)`**.

### 9.4. Chèn khóa và trả cờ thành công

```python
def avl_insert(node, key):
    """Trả (gốc_mới, inserted). Không cho khóa trùng."""
    if node is None:
        return AugNode(key), True

    if key < node.key:
        node.left, inserted = avl_insert(node.left, key)
    elif key > node.key:
        node.right, inserted = avl_insert(node.right, key)
    else:
        return node, False

    # Không thay đổi cây thì không cần cập nhật metadata.
    if not inserted:
        return node, False

    return rebalance(node), True
```

Khi một khung đệ quy nhận cây con mới, nó **gắn liên kết mới trước**, sau đó gọi `rebalance`. Vì khung của con đã hoàn tất trước khung cha, thứ tự tính từ dưới lên được bảo đảm tự nhiên.

### 9.5. Xóa khóa: bao quát cả ba trường hợp

Hàm xóa dưới đây dùng chiến lược **chép khóa kế nhiệm inorder** khi nút có hai con:

```python
def avl_delete(node, key):
    """Trả (gốc_mới, removed). Xóa đúng một khóa nếu có."""
    if node is None:
        return None, False

    if key < node.key:
        node.left, removed = avl_delete(node.left, key)

    elif key > node.key:
        node.right, removed = avl_delete(node.right, key)

    else:
        # Đã tìm thấy nút có khóa cần xóa.
        if node.left is None:
            return node.right, True

        if node.right is None:
            return node.left, True

        # Hai con: tìm khóa kế nhiệm (cực trái cây con phải).
        successor = node.right
        while successor.left is not None:
            successor = successor.left

        replacement_key = successor.key

        # Cập nhật khóa nút hiện tại trước khi tính lại total.
        node.key = replacement_key

        # Xóa nút kế nhiệm cũ ở nhánh phải.
        node.right, removed = avl_delete(
            node.right, replacement_key
        )
        assert removed  # Vì đã tìm được kế nhiệm trong cây con phải.

    if not removed:
        return node, False

    # Tính lại và tái cân bằng ở tất cả mức bị ảnh hưởng.
    return rebalance(node), True
```

**Vì sao trường hợp hai con không làm mất dữ liệu?** Nút cần xóa được thay bằng khóa kế nhiệm. Sau đó nút kế nhiệm **ở vị trí cũ** bị xóa, do đó số nút giảm **đúng một**, không tạo khóa trùng ở trạng thái cuối.

**Giới hạn của chiến lược chép khóa:** nếu mỗi nút có thêm một `payload` gắn với `key`, ta phải chuyển/copy **đúng payload tương ứng** cùng khóa, hoặc dùng chiến lược chuyển nguyên **đối tượng nút**. Chỉ chép `key` và bỏ `payload` cũ sẽ làm dữ liệu sai. Mã minh họa chỉ lưu một khóa nguyên làm dữ liệu.

Trong lúc xóa đang thực hiện dở, nội bộ có thể tạm có hai nút cùng khóa kế nhiệm. Thuật toán giả định không có tác vụ khác đọc cây tại thời điểm chưa hoàn tất. Để có tính nguyên tử trong ứng dụng đa luồng, cần cơ chế đồng bộ/phiên bản phù hợp.

### 9.6. Một lớp bọc để không quên gán lại gốc

```python
class AugmentedAVL:
    def __init__(self):
        self.root = None

    def insert(self, key):
        self.root, changed = avl_insert(self.root, key)
        return changed

    def delete(self, key):
        self.root, changed = avl_delete(self.root, key)
        return changed

    def __len__(self):
        return subtree_size(self.root)

    def total(self):
        return subtree_total(self.root)
```

Nếu không có lớp bọc này, người sử dụng phải luôn viết:

```python
root, inserted = avl_insert(root, key)
root, removed = avl_delete(root, key)
```

**Không được bỏ qua gốc mới:** một phép xoay hoặc xóa gốc có thể làm đối tượng gốc thay đổi. Việc tiếp tục giữ biến gốc cũ có thể khiến một phần cây không còn được truy cập đúng.

## 10. Truy vết các lần cập nhật cụ thể

### 10.1. Chèn và bảo trì metadata

```python
tree = AugmentedAVL()

for key in [20, 10, 30, 5, 15, 25, 35]:
    assert tree.insert(key)

print(len(tree))       # 7
print(tree.total())    # 140
print(tree.root.key)   # 20
print(tree.root.height)  # 2

assert tree.insert(13)
print(len(tree))       # 8
print(tree.total())    # 153
print(tree.root.height)  # 3

assert not tree.insert(13)
print(len(tree))       # 8
print(tree.total())    # 153
```

Sau thêm `13`, các nút `15,10,20` được cập nhật trên đường quay về gốc, còn vùng cây con gốc `30` không đổi. Không có xoay vì chênh chiều cao của từng nút vẫn trong `[-1,1]`.

### 10.2. Xóa lá trong cây cân bằng

Để minh họa xóa từ trạng thái ban đầu:

```python
tree = AugmentedAVL()
for key in [20, 10, 30, 5, 15, 25, 35]:
    tree.insert(key)

assert tree.delete(5)
print(len(tree))       # 6
print(tree.total())    # 135
print(tree.root.key)   # 20

assert not tree.delete(999)
print(len(tree))       # 6: không đổi
print(tree.total())    # 135: không đổi
```

Sau khi xóa `5`, đường quay về gồm nút `10` rồi `20`. Mỗi mức tính lại số nút, tổng khóa, chiều cao và kiểm tra cân bằng.

### 10.3. Xóa nút có hai con

```python
tree = AugmentedAVL()
for key in [20, 10, 30, 5, 15, 25, 35]:
    tree.insert(key)

assert tree.delete(20)
print(len(tree))       # 6
print(tree.total())    # 120
print(tree.root.key)   # 25 (kế nhiệm của 20)
```

Tại thời điểm xóa, `20` có hai con, nên:

1. Tìm cực trái của cây con phải: `25`.
2. Gán khóa gốc thành `25`.
3. Xóa nút chứa `25` cũ dưới `30`.
4. Tính lại `30`, rồi gốc `25`, đồng thời cân bằng nếu cần.

### 10.4. Xóa gây mất cân bằng và phải xoay

Xây cây:

```text
          30
         /  \
        20   40
       /  \
      10  25
```

Đây là AVL hợp lệ. Nếu xóa `40`, gốc `30` có:

- Cây con trái chiều cao `1`.
- Cây con phải rỗng chiều cao `-1`.
- `balance(30)=1-(-1)=2` → mất cân bằng.

Con trái `20` có hai nhánh cùng chiều cao, nên `balance(20)=0`. Theo quy tắc khi **xóa**, trường hợp này xử lý bằng **xoay phải đơn** tại `30`:

```text
Trước xóa:                Sau xóa, trước xoay:       Sau xoay:

       30                         30                      20
      /  \                       /                       /  \
     20   40                    20                      10   30
    /  \                       /  \                         /
   10  25                     10  25                       25
```

Kết quả cuối gồm `10,20,25,30`:

\[
size(root)=4,\qquad total(root)=85.
\]

Có thể minh họa bằng code:

```python
tree = AugmentedAVL()
for key in [30, 20, 40, 10, 25]:
    tree.insert(key)

assert tree.root.key == 30

assert tree.delete(40)
print(tree.root.key)  # 20: xoay phải ở vùng gốc
print(len(tree))      # 4
print(tree.total())   # 85
```

**Ý nghĩa:** xóa không chỉ là giảm `size` và `total`. Nó có thể làm thay đổi chiều cao và **kích hoạt phép xoay**; sau xoay, metadata tại các nút tham gia phải được tính lại theo đúng liên kết mới.

### 10.5. Trường hợp LR và RL

```python
for values in (
    [30, 20, 10],  # LL
    [10, 20, 30],  # RR
    [30, 10, 20],  # LR
    [10, 30, 20],  # RL
):
    t = AugmentedAVL()
    for value in values:
        t.insert(value)

    assert t.root.key == 20
    assert len(t) == 3
    assert t.total() == 60
    assert t.root.height == 1
```

Cả bốn trường hợp sau xoay đều có gốc `20`, hai lá `10` và `30`. Đó là cách kiểm tra trực quan rằng thuật toán cân bằng không làm mất giá trị và không để metadata sai.

## 11. Metadata giúp truy vấn gì sau khi được duy trì đúng?

Bài này tập trung vào **bảo trì**, nhưng để hiểu lợi ích ta cần thấy ít nhất một truy vấn sử dụng trực tiếp thông tin tăng cường.

### 11.1. Chọn khóa nhỏ thứ `k`

BST có thứ tự khóa từ trái sang phải. Tại nút `u`:

\[
leftCount=size(u.left).
\]

- Nếu `k=leftCount+1`, khóa cần tìm là `key(u)`.
- Nếu `k\le leftCount`, đi trái.
- Nếu `k>leftCount+1`, đi phải với `k'=k-leftCount-1`.

```python
def select_kth(root, k):
    """k đếm từ 1; trả khóa nhỏ thứ k."""
    if not 1 <= k <= subtree_size(root):
        raise IndexError("k ngoài phạm vi")

    current = root
    while current is not None:
        left_count = subtree_size(current.left)

        if k == left_count + 1:
            return current.key

        if k <= left_count:
            current = current.left
        else:
            k -= left_count + 1
            current = current.right

    raise RuntimeError("size metadata không nhất quán")
```

### 11.2. Đếm khóa nhỏ hơn `x`

```python
def rank_lt(root, x):
    count = 0
    current = root

    while current is not None:
        if x <= current.key:
            current = current.left
        else:
            count += subtree_size(current.left) + 1
            current = current.right

    return count
```

Với mỗi bước đi sang phải, ta **cộng luôn cả cây con trái** mà không cần thăm từng phần tử.

### 11.3. Tổng các khóa nhỏ hơn hoặc bằng `x`

```python
def prefix_total_le(root, x):
    result = 0
    current = root

    while current is not None:
        if x < current.key:
            current = current.left
        else:
            result += subtree_total(current.left) + current.key
            current = current.right

    return result
```

Nếu cây có `h` cạnh trên đường sâu nhất, cả ba truy vấn trên đi theo **một đường**: thời gian **`O(h+1)`**, bộ nhớ phụ **`O(1)`**. Với AVL, là **`O(\log n)`**.

### 11.4. Xác nhận sau nhiều phép sửa

```python
tree = AugmentedAVL()
for key in [20, 10, 30, 5, 15, 25, 35]:
    tree.insert(key)

assert select_kth(tree.root, 1) == 5
assert select_kth(tree.root, 4) == 20
assert rank_lt(tree.root, 20) == 3
assert prefix_total_le(tree.root, 20) == 50

# Chèn 13 và xóa 20, bao gồm cập nhật metadata.
assert tree.insert(13)
assert tree.delete(20)

# Các khóa còn lại: 5, 10, 13, 15, 25, 30, 35
assert len(tree) == 7
assert tree.total() == 133
assert select_kth(tree.root, 4) == 15
assert rank_lt(tree.root, 20) == 4
assert prefix_total_le(tree.root, 15) == 43
```

Những kết quả này phụ thuộc **đồng thời** vào bất biến BST và `size/total` đúng ở các nút. Một sai sót khi xóa hoặc xoay có thể không làm lộ lỗi khi tìm khóa bình thường nhưng sẽ biểu hiện qua `select`, `rank` hoặc tổng.

## 12. Chứng minh tính đúng của kỹ thuật bảo trì

Một cấu trúc tăng cường không chỉ cần chạy đúng vài ví dụ: quy tắc bảo trì phải đúng **cho mọi cây hợp lệ** trong phạm vi giả định.

### 12.1. Cơ sở quy nạp

Với cây rỗng:

\[
size=0,\quad total=0,\quad height=-1.
\]

Với nút mới tạo:

\[
size=1,\quad total=key,\quad height=0.
\]

Cả hai đều đúng theo định nghĩa.

### 12.2. Bước quy nạp tại một nút

Giả sử hai cây con của `u` đã có metadata đúng. Khi gọi:

```text
pull(u):
    size   = 1 + size(left) + size(right)
    total  = key + total(left) + total(right)
    height = 1 + max(height(left), height(right))
```

ta nhận được:

- Tổng số nút đúng: một nút hiện tại cộng hai tập nút ở hai cây con.
- Tổng khóa đúng: khóa hiện tại cộng hai tổng cây con.
- Chiều cao đúng: đường sâu nhất đi qua cây con có chiều cao lớn hơn rồi cộng một cạnh.

Vì vậy `pull(u)` là đúng **nếu hai con đã đúng**.

### 12.3. Bất biến của chèn

1. Nút mới có metadata đúng.
2. Những cây con ngoài đường chèn không thay đổi.
3. Khung con hoàn tất trước và trả về gốc cây con hợp lệ.
4. Khung cha gắn liên kết mới, rồi `pull/rebalance`.
5. Quy nạp theo đường quay về bảo đảm metadata đúng tới gốc.

Nếu chèn khóa trùng bị từ chối, không có thay đổi và metadata giữ nguyên.

### 12.4. Bất biến của xóa

- Xóa lá: thay cây con bằng cây rỗng đã có quy ước metadata đúng.
- Xóa nút một con: cây con còn lại vốn đúng và được nối lên.
- Xóa nút hai con: chép khóa kế nhiệm, rồi xóa **nút kế nhiệm cũ** trong cây con phải; sau khi khung xóa trả về, hai cây con và khóa mới xác định được một cây BST hợp lệ.
- Ở mọi khung trên đường quay về, gọi `rebalance` sau khi cây con được sửa xong.

Do đó metadata đúng sau từng mức; các phép xoay bên trong `rebalance` có chứng minh riêng ở mục kế tiếp.

### 12.5. Bất biến của xoay

Với xoay trái:

1. Các cây con `A,B,C` không đổi.
2. Nút `x` nhận con mới `A,B` và được `pull(x)`, nên đúng.
3. Nút `y` nhận con mới `x,C` và được `pull(y)`, nên đúng.
4. Thứ tự inorder `A,x,B,y,C` giữ nguyên, nên bất biến BST cũng đúng.

Xoay phải tương tự với thứ tự `pull(y)` trước `pull(x)`.

Xoay kép là **hai phép xoay đơn liên tiếp**, mỗi phép đã giữ đúng bất biến, nên kết quả cuối cũng đúng.

### 12.6. Kết hợp với cân bằng AVL

AVL dùng chính metadata `height` để phát hiện chênh lệch và chọn xoay. Khi hai cây con đã cân bằng, quy tắc rebalance chuẩn phục hồi điều kiện AVL ở nút đang xét, trong khi các phép xoay không phá thứ tự khóa hoặc metadata.

Tính đúng toàn bộ thuật toán được xây từ **ba tính chất**: cập nhật con trước cha, xoay giữ thứ tự BST, và cập nhật `height` đúng ở mỗi nút tham gia xoay.

## 13. Độ phức tạp thời gian và bộ nhớ

Ký hiệu `n` là số khóa, `h` là chiều cao theo số cạnh; giả định các trường metadata có kích thước cố định và mỗi phép gộp `O(1)`.

| Công việc | BST tăng cường không cân bằng | AVL tăng cường |
|---|---|---|
| Khởi tạo một lá | `O(1)` | `O(1)` |
| Tính lại một nút bằng `pull` | `O(1)` | `O(1)` |
| Chèn và duy trì metadata | `O(h+1)`, xấu nhất `O(n)` | `O(\log n)` |
| Xóa và duy trì metadata | `O(h+1)`, xấu nhất `O(n)` | `O(\log n)` |
| Một phép xoay đơn + tính lại hai nút | `O(1)` | `O(1)` |
| Một phép xoay kép + tính lại các nút liên quan | `O(1)` | `O(1)` |
| Tìm khóa theo BST | `O(h+1)` | `O(\log n)` |
| `select_kth`, `rank_lt`, tổng tiền tố | `O(h+1)` | `O(\log n)` |
| Xây metadata cho cây đã có bằng hậu thứ tự | `O(n)` | `O(n)` |
| Bộ nhớ metadata thêm trên toàn cây | `O(n)` | `O(n)` |

### 13.1. Tại sao xoay `O(1)` không có nghĩa chèn `O(1)`?

Phép xoay tự thân sửa một số hằng tham chiếu, nhưng để **tìm vị trí chèn** phải đi xuống một đường dài `O(h)`; sau chèn còn phải **đi ngược lên đường đó** để cập nhật metadata và cân bằng. Do đó toàn bộ phép chèn AVL vẫn là **`O(\log n)`**, dù mỗi xoay đơn chỉ `O(1)`.

### 13.2. Bộ nhớ phụ của code Python

Hàm `avl_insert`/`avl_delete` dùng đệ quy, nên tốn **`O(h+1)` khung gọi**, tức `O(\log n)` trên AVL hợp lệ. Các hàm xoay và `pull` dùng **`O(1)` bộ nhớ phụ**.

Nếu xây BST không cân bằng rồi dùng thuật toán đệ quy tương tự nhưng **không cân bằng**, chiều sâu có thể `O(n)`, thậm chí chạm giới hạn đệ quy của Python.

Mỗi nút lưu thêm ba trường `size,total,height`, nên chi phí metadata toàn cây là **`O(n)` bộ nhớ bổ sung**. Tổng bộ nhớ lưu nút và liên kết vẫn là `O(n)` theo Big-O, nhưng số byte trên mỗi nút tăng.

### 13.3. Chi phí kiểm tra toàn cây không phải chi phí cập nhật

Một hàm xác thực mọi nút sau chèn có thể mất `O(n)`, dù bản thân chèn chỉ `O(\log n)`. Khi phân tích hiệu năng, cần tách:

- **Đường cập nhật thực tế:** các phép `pull` và xoay ở vị trí bị ảnh hưởng.
- **Đường kiểm thử/xác minh:** duyệt toàn cây để phát hiện lỗi.

Không nên gọi hàm kiểm tra toàn cây sau **mỗi** thao tác sản xuất rồi vẫn tuyên bố tổng chi phí cập nhật chỉ `O(\log n)`.

## 14. Hàm xác thực độc lập: kiểm tra cả BST, AVL và metadata

Mã sau có thể dùng trong bài thực hành để xác minh **toàn bộ** các bất biến trên một cây đã xây:

- Một nút không được xuất hiện hai lần hoặc trong chu trình.
- Mọi khóa ở các cây con phải nằm trong khoảng hợp lệ do **tất cả tổ tiên** xác định.
- `size,total,height` phải bằng giá trị **tính lại độc lập** từ nút và hai cây con.
- Chênh chiều cao tại mỗi nút không quá một.

Để tránh lệ thuộc độ sâu đệ quy khi phân tích cấu trúc lỗi, hàm duyệt hậu thứ tự bằng **stack tường minh**.

```python
def validate_augmented_avl(root):
    """Kiểm tra toàn bộ cây. Trả True hoặc False."""
    if root is None:
        return True

    seen = set()
    actual = {}
    # (node, low_bound, high_bound, ready)
    frames = [(root, None, None, False)]

    while frames:
        node, low, high, ready = frames.pop()

        if node is None:
            continue

        if not isinstance(node, AugNode):
            return False

        if not ready:
            marker = id(node)

            if marker in seen:
                return False
            seen.add(marker)

            if low is not None and node.key <= low:
                return False
            if high is not None and node.key >= high:
                return False

            # Đưa cha trở lại stack để xử lý SAU hai con.
            frames.append((node, low, high, True))
            frames.append((node.right, node.key, high, False))
            frames.append((node.left, low, node.key, False))

        else:
            ls, lt, lh = actual.get(node.left, (0, 0, -1))
            rs, rt, rh = actual.get(node.right, (0, 0, -1))

            expected_size = 1 + ls + rs
            expected_total = node.key + lt + rt
            expected_height = 1 + max(lh, rh)

            if node.size != expected_size:
                return False
            if node.total != expected_total:
                return False
            if node.height != expected_height:
                return False
            if abs(lh - rh) > 1:
                return False

            actual[node] = (
                expected_size, expected_total, expected_height
            )

    return True
```

**Độ phức tạp:** với cây hợp lệ `n` nút, tổng thời gian **`O(n)`**, bộ nhớ phụ **`O(n)`** cho bảng giá trị tính độc lập, tập `seen` và stack.

Hàm này là một công cụ **tự xác minh khi thực hành**, không phải thuật toán cần gọi ở mọi bước chèn/xóa. Lưu ý rằng `AugNode` mặc định được so sánh/hash theo định danh đối tượng; nếu sau này định nghĩa `__eq__` hoặc thay chính sách hash, cần điều chỉnh cách lưu khóa trong bảng `actual` cho nhất quán.

### 14.1. Những ví dụ kiểm tra

```python
t = AugmentedAVL()

assert validate_augmented_avl(t.root)  # Cây rỗng.

for x in [20, 10, 30, 5, 15, 25, 35]:
    assert t.insert(x)
    assert validate_augmented_avl(t.root)

assert t.delete(20)                   # Hai con.
assert validate_augmented_avl(t.root)
assert t.delete(5)                    # Lá.
assert validate_augmented_avl(t.root)
assert not t.delete(999)              # Không có khóa.
assert validate_augmented_avl(t.root)

# Gây lỗi nhân tạo ở metadata để thấy validator phát hiện.
t.root.size += 100
assert not validate_augmented_avl(t.root)

# Tính lại gốc (chỉ đúng vì metadata hai cây con đang đúng).
pull(t.root)
assert validate_augmented_avl(t.root)
```

### 14.2. Các kiểm thử cần chú ý

- Cây rỗng và cây một nút.
- Chèn khóa nhỏ hơn tất cả, lớn hơn tất cả và khóa đã tồn tại.
- Xóa khóa không tồn tại.
- Xóa gốc khi là lá, có một con hoặc có hai con.
- Xóa kế nhiệm có **một con phải**.
- Chèn/xóa làm phát sinh từng trường hợp LL, RR, LR, RL.
- Xóa dẫn đến **nhiều mức** phải tái cân bằng.
- Khóa âm và tổng bằng `0`.
- Một lần xoay làm gốc cây con thay đổi.
- Truy vấn `select` với `k=1`, `k=n` và `k` ngoài phạm vi.

Mỗi kiểm thử nên đối chiếu không chỉ danh sách khóa thu được từ inorder, mà cả **metadata tại từng nút**. Một cây có dãy inorder đúng vẫn có thể lưu `size` hoặc `height` sai.

## 15. Tích hợp vào cây có `parent` và các cấu trúc tăng cường khác

### 15.1. Khi mỗi nút còn có liên kết cha

Mã AVL ở mục 9 sử dụng `left/right` và **trả gốc cây con mới**, không lưu `parent`. Nếu triển khai nút có thêm `parent`, một phép xoay cần cập nhật nhiều hơn:

- Liên kết từ **cha cũ của vùng xoay** tới gốc mới.
- `parent` của gốc mới.
- `parent` của nút bị đẩy xuống.
- `parent` của cây con trung gian `B` nếu `B` không rỗng.

Ví dụ xoay trái tại `x` có `y=x.right` và `B=y.left`:

```text
x.right = B
if B != None: B.parent = x
y.left = x
y.parent = old_parent_of_x
x.parent = y

Nếu old_parent_of_x != None:
    old_parent_of_x.left hoặc .right = y
Ngược lại:
    root = y
```

**Thứ tự thao tác phải tránh trạng thái trung gian bị đọc đồng thời.** Mã giả nêu các liên kết cần sửa, không phải một giao thức đồng bộ hay cài đặt nguyên tử. Sau khi các liên kết liên quan đã đúng, tính lại metadata của `x` rồi `y` và các tổ tiên nếu cần.

### 15.2. Chuyển sang một metadata khác

Quy tắc `pull` không chỉ dành cho tổng và kích thước. Ví dụ:

| Metadata tại `u` | Công thức tổng hợp | Chú ý khi cập nhật |
|---|---|---|
| Số nút `size` | `1+size(L)+size(R)` | Khóa trùng có thể phải lưu số lần xuất hiện |
| Tổng trọng số `weightSum` | `weight(u)+sum(L)+sum(R)` | Không nhầm trọng số với khóa tìm kiếm |
| Chiều cao `height` | `1+max(height(L),height(R))` | Thay đổi sau xoay |
| Giá trị nhỏ nhất trong cây con `subtreeMin` | `min(value(u),min(L),min(R))` | Cần giá trị trung hòa phù hợp khi rỗng |
| Giá trị lớn nhất `subtreeMax` | `max(value(u),max(L),max(R))` | Xóa giá trị cực trị phải tổng hợp lại |
| Đầu mút cao nhất trong interval tree `maxHigh` | `max(high(u),maxHigh(L),maxHigh(R))` | Dùng để loại nhánh không thể giao với khoảng truy vấn |

Nếu hai con cung cấp đúng metadata và phép gộp mất `O(1)`, ta có thể dùng cùng nguyên tắc **cập nhật từ dưới lên và sửa cục bộ sau xoay**.

Tuy nhiên, **không phải mọi metadata đều chỉ phụ thuộc vào tập khóa**: chiều cao hay các đại lượng theo đường đi còn phụ thuộc hình dạng. Phải phân tích rõ phạm vi ảnh hưởng mỗi khi xoay.

### 15.3. Cây tổng quát có nhiều con

Với nút `u` có `k` con:

\[
size(u)=1+\sum_{v\in children(u)}size(v).
\]

Nếu phải duyệt lại đủ `k` con để tính tổng, một lần `pull(u)` có thể mất **`O(k)`**, không còn `O(1)`. Muốn cập nhật hiệu quả có thể dùng phép điều chỉnh chênh lệch đã được chứng minh, lưu thêm một cấu trúc tổng hợp trên danh sách con hoặc chọn một dạng cây nền phù hợp hơn.

**Không được suy luận** rằng mọi cây tăng cường luôn cập nhật metadata trong `O(\log n)`; giới hạn đó cần **cây nền thấp** và **phép gộp cục bộ rẻ**.

## 16. Lưu ý về tính nhất quán khi cập nhật thực tế

### 16.1. Không để truy vấn nhìn thấy metadata “nửa mới nửa cũ”

Một thao tác chèn có thể:

1. Gắn nút con mới.
2. Cập nhật metadata cha.
3. Tính tiếp metadata ông/bà.
4. Xoay một vùng cây.
5. Nối gốc vùng xoay vào tổ tiên.

Trong lúc các bước này chưa hoàn tất, một truy vấn khác đọc cây có thể thấy **con trỏ mới nhưng `size/total` cũ**, rồi trả kết quả sai.

Trong hệ thống đa luồng cần dùng **khóa**, cập nhật theo phiên bản/snapshot hoặc cơ chế bảo vệ nhất quán tương đương. Không nên diễn giải thuật toán xoay và `pull` đơn luồng là tự động an toàn trước thao tác đồng thời.

### 16.2. Cẩn thận với lỗi khi thao tác đang dở

Code Python minh họa giả định:

- So sánh khóa không ném lỗi bất thường.
- Các giá trị dùng phép cộng là số hợp lệ.
- Không có lỗi bộ nhớ/ngoại lệ trong lúc đang thay nhiều liên kết.
- Không có mã khác can thiệp vào cây giữa các bước.

Nếu ứng dụng phải đáp ứng giao dịch/rollback, cần thiết kế một tầng điều khiển rõ ràng. Không đủ chỉ đặt `try/except` quanh `rotate_left`, bởi ngoại lệ có thể xảy ra sau khi một vài tham chiếu đã đổi.

### 16.3. Khóa trùng, payload và kiểu dữ liệu lớn

Bài dùng khóa nguyên **phân biệt**. Khi có khóa trùng, ta có thể:

- Lưu `count` tại nút và định nghĩa `size` là số phần tử kể cả số lần xuất hiện.
- Hoặc dùng chính sách chèn khóa bằng nhau theo một tiêu chí thứ tự phụ.

Mỗi chính sách yêu cầu sửa công thức tổng hợp và cách tính `select/rank`. Nếu dùng `count`:

\[
size(u)=count(u)+size(L)+size(R).
\]

Nếu mỗi nút còn lưu `weight` hoặc `payload`, xóa bằng cách chép **chỉ khóa** của kế nhiệm không đủ; phải chuyển cả dữ liệu gắn với khóa hoặc thay bằng thao tác di chuyển đối tượng nút.

Ngoài ra, tổng trên số nguyên cố định có thể tràn, số thực có thể bị ảnh hưởng bởi thứ tự cộng và sai số làm tròn. Các điều này phải được nêu trong hợp đồng ứng dụng khi dữ liệu lớn hoặc yêu cầu chính xác cao.

## 17. Các sai lầm thường gặp

1. **Cập nhật `size` ở gốc nhưng bỏ qua các nút trung gian.** Truy vấn xếp hạng dựa vào `size(left)` ở từng mức.
2. **Tính cha trước con.** Cha đọc metadata cũ khiến sai số lan lên gốc.
3. **Gọi `pull` trước khi sửa xong các liên kết con.** Tính từ cấu trúc cũ rồi quên sửa lại.
4. **Chèn trùng khóa mà vẫn tăng `size/total`.** Nếu chính sách là từ chối khóa trùng, không có gì phải cập nhật.
5. **Xóa khóa không tồn tại mà vẫn trừ metadata.** Cần trả cờ `removed`.
6. **Xóa nút có hai con nhưng quên xóa kế nhiệm ở vị trí cũ.** Dễ tạo khóa trùng hoặc giảm sai số nút.
7. **Chép khóa kế nhiệm mà quên tính lại `total`.** Tổng tại nút đã thay khóa có thể thay đổi.
8. **Giả định kế nhiệm luôn là lá.** Nút cực trái của cây con phải có thể có **con phải**.
9. **Quên cập nhật metadata khi thay gốc bằng con sau xóa.** Cha nhận gốc cây con mới và phải được `pull`.
10. **Dừng bảo trì ngay sau một phép xoay trong lúc xóa AVL.** Các tổ tiên cao hơn vẫn có thể đổi chiều cao và cần rebalance.
11. **Xoay trái nhưng tính `y` trước `x`.** Metadata của `y` phụ thuộc vào metadata mới của `x`.
12. **Xoay phải nhưng tính `x` trước `y`.** Tương tự, phải tính nút bị đẩy xuống trước.
13. **Xoay xong nhưng không nối lại gốc vùng xoay.** Có thể mất liên kết từ cha hoặc biến gốc toàn cây.
14. **Nhầm phép xoay không đổi tập khóa với metadata ở từng nút không đổi.** Tập nút cây con của các nút xoay đã thay đổi.
15. **Chỉ lưu `height` nhưng quên tái tính sau xoay.** Hệ số cân bằng sẽ sai, dẫn tới chọn xoay sai.
16. **Dùng chiều cao rỗng `0` cùng công thức lá cao `0`.** Với chiều cao tính theo cạnh, cây rỗng cần `-1`.
17. **Nhầm AVL với BST tăng cường thông thường.** Lưu `size/total` không tự bảo đảm cây cân bằng.
18. **Suy ra tìm/chèn/xóa luôn `O(\log n)` mà không xét cây nền.** BST suy biến có thể tốn `O(n)`.
19. **Chỉ kiểm tra inorder mà không kiểm tra metadata.** Dãy khóa vẫn có thể tăng dần khi `size` sai.
20. **Chỉ kiểm tra metadata mà bỏ qua bất biến khóa.** Metadata đúng không chứng minh cây là BST hợp lệ.
21. **Coi một phép `pull` luôn `O(1)`.** Với cây nhiều con hoặc dữ liệu tổng hợp lớn, phép gộp có thể tốn `O(k)` hoặc hơn.
22. **Sửa trực tiếp `key` mà không xem xét `payload` hoặc thứ tự BST.** Có thể tạo liên kết giữa dữ liệu và khóa không nhất quán.
23. **Đọc cây đồng thời với thao tác xoay chưa hoàn tất.** Truy vấn có thể quan sát trạng thái trung gian không hợp lệ.
24. **Quên tính bộ nhớ phụ của đường đệ quy.** Chèn/xóa AVL dùng `O(\log n)` stack, còn metadata trên toàn cây thêm `O(n)`.
25. **Gọi xác thực toàn cây `O(n)` trong đường cập nhật rồi tuyên bố thao tác chỉ `O(\log n)`.** Phải phân biệt kiểm thử và vận hành.

## 18. Bài tập thực hành có đáp án

### Bài 1. Công thức tại một nút

Nút `u` có khóa `10`, cây con trái có `size=3` và `total=12`, cây con phải có `size=2` và `total=35`. Tính metadata mới.

**Đáp án:** `size(u)=1+3+2=6` và `total(u)=10+12+35=57`. Chiều cao còn cần `height` của hai con.

### Bài 2. Chiều cao theo số cạnh

Hai cây con của `u` có chiều cao `1` và `-1`. Chiều cao và hệ số cân bằng của `u` bằng bao nhiêu?

**Đáp án:** `height(u)=1+max(1,-1)=2`; `balance(u)=1-(-1)=2`. Nếu đang duy trì AVL, nút bị mất cân bằng.

### Bài 3. Đường cập nhật khi chèn

Từ cây gốc `20`, các con `10,30`; `10` có hai con `5,15`, `30` có `25,35`. Chèn `13` vào đâu và cập nhật nút nào?

**Đáp án:** `13` là con trái của `15`. Tính lại `15→10→20`, theo thứ tự từ dưới lên. Vùng cây con gốc `30` không đổi.

### Bài 4. Tổng sau chèn

Cây ban đầu có bảy khóa `5,10,15,20,25,30,35` với tổng `140`. Chèn thành công `13`. `root.size` và `root.total` mới là bao nhiêu?

**Đáp án:** `size=8` và `total=140+13=153`.

### Bài 5. Chèn trùng

Trong BST có chính sách từ chối khóa trùng, chèn khóa `15` khi `15` đã tồn tại. Có được cộng `size += 1` không?

**Đáp án:** **Không.** Phép chèn thất bại nên số nút, tổng khóa và chiều cao đều giữ nguyên.

### Bài 6. Xóa lá

Cây bảy khóa ở Bài 4 xóa khóa `5`. Metadata ở nút `10` và gốc `20` thay đổi ra sao?

**Đáp án:** `size(10):3→2`, `total(10):30→25`. `size(20):7→6`, `total(20):140→135`.

### Bài 7. Xóa một con

Cây có gốc `20`, con trái `10`, con phải `30`; nút `10` chỉ có con trái `5`. Xóa `10` cần nối liên kết thế nào?

**Đáp án:** Thay `20.left=10` bằng `20.left=5`. Giữ nguyên cây con gốc `5`, rồi tính lại metadata tại `20`. Tổng khóa mới `55`, số nút mới `3`.

### Bài 8. Xóa hai con

Từ cây bảy khóa `5,10,15,20,25,30,35`, xóa gốc `20` bằng kế nhiệm. Khóa thay thế là gì? Metadata mới ở gốc là gì?

**Đáp án:** Kế nhiệm inorder là `25`. Gốc mới mang khóa `25`, nút `25` cũ bị xóa. Có `6` nút, tổng `140-20=120`.

### Bài 9. Kế nhiệm có con phải

Khi xóa một nút hai con, cực trái của cây con phải có thể có con phải không? Nếu có, phải làm gì?

**Đáp án:** **Có.** Nó không có con trái nhưng có thể có con phải. Khi xóa nút kế nhiệm khỏi vị trí cũ, phải **nối cha của kế nhiệm với con phải của kế nhiệm** để không làm mất cây con ấy.

### Bài 10. Xóa khóa không có

Một lần `delete(999)` trên cây không chứa `999` phải trả gì và metadata có đổi không?

**Đáp án:** Trả cờ `removed=False` (hoặc kết quả tương đương) và **giữ nguyên** liên kết, `size,total,height`.

### Bài 11. Thứ tự sau xoay trái

Trước xoay trái tại `x` có `y=x.right`. Phải gọi `pull(x)` hay `pull(y)` trước?

**Đáp án:** Sau đổi liên kết, gọi **`pull(x)` trước** rồi **`pull(y)`**. `y` có con trái mới là `x` nên cần metadata mới của `x`.

### Bài 12. Thứ tự sau xoay phải

Trước xoay phải tại `y` có `x=y.left`. Gọi `pull` theo thứ tự nào?

**Đáp án:** **`pull(y)` trước**, rồi **`pull(x)`**; nút `y` bị đẩy xuống cần được tính lại trước gốc mới `x`.

### Bài 13. Xoay không mất khóa

Cây lệch trái `30→20→10` được xoay phải. Gốc mới là gì, tổng và kích thước vùng xoay có đổi không?

**Đáp án:** Gốc mới là `20`, có hai con `10` và `30`. Tập khóa vùng xoay vẫn là `{10,20,30}`, nên tổng toàn vùng `60` và kích thước `3` không đổi. Nhưng metadata tại nút `30` phải đổi.

### Bài 14. Bốn trường hợp AVL

Chèn lần lượt `30,10,20` gây trường hợp nào? Cần các phép xoay nào?

**Đáp án:** **LR**: xoay trái tại `10`, rồi xoay phải tại `30`. Gốc cuối là `20`.

### Bài 15. Trường hợp RL

Chèn lần lượt `10,30,20` gây trường hợp nào và sửa ra sao?

**Đáp án:** **RL**: xoay phải tại `30`, sau đó xoay trái tại `10`. Gốc cuối là `20`.

### Bài 16. Xóa gây xoay

AVL có gốc `30`, con trái `20`, con phải `40`, và `20` có hai con `10,25`. Sau xóa `40`, phải xử lý thế nào?

**Đáp án:** Gốc `30` lệch trái `2` mức; con trái `20` cân bằng bằng `0`. Xoay phải đơn tại `30`. Gốc mới là `20`; cây có `4` nút và tổng `85`.

### Bài 17. Giá trị `height(None)`

Bài dùng chiều cao theo số cạnh, lá có `height=0`. Nên quy ước `height(None)` bằng bao nhiêu để công thức `1+max` đúng?

**Đáp án:** `height(None)=-1`. Khi hai con của lá đều rỗng, `height(leaf)=1+max(-1,-1)=0`.

### Bài 18. Truy vấn thứ hạng

Một BST tăng cường có gốc `20` với `size(left)=3`. Khóa ở gốc có thứ hạng bao nhiêu nếu đánh số từ `1`?

**Đáp án:** **Thứ hạng `4`**, vì có đúng `3` khóa nhỏ hơn nằm ở cây con trái.

### Bài 19. Metadata sai và kết quả truy vấn

Nếu cây thực tế có `7` nút nhưng `root.size=6`, `select_kth(root,7)` ở code minh họa có thể xảy ra điều gì?

**Đáp án:** Hàm kiểm tra biên `k≤root.size` sẽ từ chối `k=7` dù khóa nhỏ thứ bảy thật sự tồn tại. Metadata sai có thể làm truy vấn **báo lỗi hoặc đi nhánh sai**.

### Bài 20. Độ phức tạp cập nhật

Vì sao chèn/xóa trong AVL tăng cường thường là `O(\log n)` dù mỗi `pull` và phép xoay đều `O(1)`?

**Đáp án:** Phải tìm vị trí thao tác và cập nhật/tái cân bằng trên đường từ vị trí đó tới gốc. Độ dài đường là `O(\log n)` trong AVL, nên tổng các công việc cục bộ vẫn là `O(\log n)`.

### Bài 21. Xác thực toàn cây

Một hàm xác thực cả BST, AVL và metadata bằng cách duyệt mọi nút mất bao nhiêu thời gian? Có nên gọi nó sau mọi lần chèn trong đường vận hành tối ưu không?

**Đáp án:** **`O(n)` thời gian** và thường `O(n)` bộ nhớ phụ nếu lưu tập đã thăm/tổng hợp độc lập. Không nên gộp nó vào mọi thao tác sản xuất nếu muốn giữ chèn `O(\log n)`; đây là công cụ kiểm thử hoặc kiểm tra định kỳ.

### Bài 22. Trường trọng số riêng

BST sắp theo `employee_id`, nhưng mỗi nút còn có `salary` và muốn truy vấn tổng lương. Công thức `total` phải dùng trường nào? Khi xóa nút hai con bằng kế nhiệm, phải chú ý gì?

**Đáp án:** `total(u)=salary(u)+total(left)+total(right)`. Khi thay khóa bằng kế nhiệm, phải thay **đúng bản ghi employee_id + salary tương ứng** hoặc chuyển cả nút, tránh ghép ID mới với lương cũ không thuộc bản ghi đó.

### Bài 23. Cây có nhiều con

Trong cây tổng quát, một nút có `k` con và `size(u)=1+\sum size(child)`. Tính lại từ đầu có mất `O(1)` không?

**Đáp án:** Nói chung mất **`O(k)`** nếu phải đọc đủ `k` con. Muốn cập nhật nhanh hơn cần thiết kế thêm phép cập nhật gia tăng hoặc một cấu trúc tổng hợp phù hợp.

### Bài 24. Khi nào metadata không cần cập nhật ở tổ tiên?

Một phép xoay chỉ đổi hình dạng bên trong cây con, không thêm/xóa khóa. Nếu tổ tiên bên ngoài chỉ lưu `size` và `total` của toàn cây con, chúng có nhất thiết phải đổi giá trị không?

**Đáp án:** **Không nhất thiết**: tập nút và tổng khóa của cả vùng xoay không đổi, nên `size/total` của những tổ tiên bên ngoài vẫn đúng nếu liên kết gốc vùng được nối lại. Nhưng metadata **phụ thuộc hình dạng** như `height` của tổ tiên có thể cần được kiểm tra/tính lại.

### Bài 25. Kiểm thử sau nhiều thao tác

Đề xuất cách kiểm tra một AVL tăng cường sau một chuỗi chèn, xóa và xoay ngẫu nhiên mà không phụ thuộc vào metadata đang lưu.

**Đáp án:** Duyệt độc lập các nút từ gốc; kiểm tra mỗi nút xuất hiện đúng một lần, không chu trình và mọi khóa tuân thủ giới hạn BST từ tổ tiên. Duyệt hậu thứ tự để **tự tính lại** `size,total,height` từ dữ liệu thật, đối chiếu các trường đã lưu và xác nhận `|height(left)-height(right)|≤1` tại mọi nút. Có thể đối chiếu thêm inorder với một danh sách khóa được quản lý độc lập.

## 19. Tổng kết

**Duy trì thông tin cây con** là trách nhiệm bắt buộc của mọi phép sửa đổi trên cây tăng cường. Với các trường `size`, `total` và `height`, nguyên tắc cốt lõi là:

1. **Định nghĩa bất biến** bằng công thức từ dữ liệu nút và metadata hai con.
2. **Sửa cấu trúc trước, tính lại từ dưới lên** để không dùng metadata con đã cũ.
3. **Sau chèn**, cập nhật trên đường từ nút mới về gốc và tái cân bằng nếu cần.
4. **Sau xóa**, xử lý đúng cả trường hợp hai con và kế nhiệm, rồi cập nhật/tái cân bằng trên đường trở về; xóa có thể dẫn tới xoay ở nhiều mức.
5. **Sau xoay**, tính metadata của **nút bị đẩy xuống trước**, rồi nút được nâng lên; phải nối lại gốc vùng xoay với cha hoặc gốc toàn cây.
6. **Tách đường cập nhật khỏi kiểm thử toàn cây**, kiểm tra định kỳ cả bất biến BST, cân bằng và metadata.

Một lần `pull` hay xoay đơn chỉ cần **`O(1)`** khi phép tổng hợp rẻ. Trên **AVL hợp lệ** có chiều cao `O(\log n)`, việc bảo trì metadata sau chèn/xóa vẫn giữ được **`O(\log n)` thời gian** và thêm `O(n)` bộ nhớ metadata trên toàn cây.

Điểm quan trọng nhất: **cây vẫn còn đúng hình dạng không có nghĩa thông tin cây con đã đúng**. Chỉ khi mọi lần gắn, tháo, thay khóa và xoay đều bảo vệ bất biến metadata, các truy vấn nhanh như `select`, `rank` hay tổng tiền tố mới có thể được tin cậy.

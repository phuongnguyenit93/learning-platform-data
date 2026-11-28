# Đại diện của tập hợp và rừng cây cha

Một hệ thống theo dõi các thành phần liên thông của mạng có thể biết rằng máy 0, 1, 2 và 3 thuộc cùng một nhóm mà không lưu một bản sao danh sách `{0,1,2,3}` ở từng máy. Thay vào đó, nó lưu **một quan hệ cha**: mỗi máy chỉ biết “nút cha” của mình; đi lần theo các nút cha sẽ gặp một **gốc (root)** chung. Gốc đóng vai trò **đại diện (representative)** của cả nhóm.

Đây là ý tưởng cốt lõi của **Disjoint Set Union (DSU)** hay **Union–Find**. Trong chương **Tập hợp rời nhau** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**, bài này tập trung vào hai câu hỏi: *đại diện biểu thị điều gì?* và *vì sao một mảng cha lại đủ để mô tả nhiều nhóm không giao nhau?* Từ đó, ta xây dựng bất biến, thao tác `find`/`union`, ví dụ truy vết, tối ưu hình dạng cây và phân tích độ phức tạp thời gian, bộ nhớ.

## 1. Từ phân hoạch đến một đại diện cho mỗi nhóm

Cho miền gồm `n` phần tử có chỉ số:

\[
U = \{0,1,\ldots,n-1\}.
\]

Các nhóm tại một thời điểm tạo thành **phân hoạch**:

\[
P=\{G_1,G_2,\ldots,G_c\},
\]

trong đó mọi `G_i` đều khác rỗng, hai nhóm khác nhau không giao nhau và hợp tất cả nhóm bằng `U`. Vì thế, **mỗi phần tử thuộc đúng một nhóm**.

Ví dụ:

```text
U = {0,1,2,3,4,5,6,7}

G1 = {0,1,2,3}
G2 = {4}
G3 = {5,6,7}

P = {G1, G2, G3}
```

Ta muốn biểu diễn một hàm `representative(x)` sao cho:

\[
x \text{ và } y \text{ cùng nhóm}
\quad\Longleftrightarrow\quad
\operatorname{representative}(x)=\operatorname{representative}(y).
\]

Mỗi nhóm cần **một đại diện duy nhất tại thời điểm đó**, nhưng đại diện có thể là bất kỳ phần tử nào được chọn theo quy tắc triển khai. Ví dụ:

```text
Đại diện nhóm {0,1,2,3}: 0
Đại diện nhóm {4}:       4
Đại diện nhóm {5,6,7}:   5
```

Đại diện cho phép kiểm tra **cùng nhóm** bằng cách so sánh hai giá trị trả về, thay vì duyệt mọi thành viên hoặc lưu cặp quan hệ giữa tất cả phần tử.

### Quan hệ tương đương

Định nghĩa `x ~ y` khi x và y cùng nhóm. Quan hệ này có tính:

- **Phản xạ:** `x ~ x`.
- **Đối xứng:** nếu `x ~ y` thì `y ~ x`.
- **Bắc cầu:** nếu `x ~ y` và `y ~ z` thì `x ~ z`.

Các nhóm chính là những **lớp tương đương**. DSU duy trì quan hệ này bằng cách đại diện hóa từng lớp, thay vì lưu riêng từng mệnh đề “x có liên hệ với y”.

**Điều kiện quan trọng:** mô hình này phù hợp khi các nhóm thực sự **không giao nhau**. Nếu một người đồng thời thuộc hai câu lạc bộ khác nhau, việc dùng một DSU duy nhất để đại diện cho “thành viên câu lạc bộ” sẽ làm sai yêu cầu nhóm chồng lấn.

## 2. Vì sao gọi là “rừng cây cha”?

Ta lưu cho mỗi phần tử x một giá trị:

```text
parent[x] = cha của x
```

Nếu x là gốc, ta quy ước:

```text
parent[x] = x
```

Các liên kết cha tạo nên một tập các **cây có gốc**, còn gọi là **rừng (forest)**. Mỗi cây tương ứng **một nhóm**.

Ví dụ:

```text
Cây A                  Cây B        Cây C

       0                    4            5
      / \                               / \
     1   2                             6   7
         |
         3

Nhóm {0,1,2,3}       Nhóm {4}      Nhóm {5,6,7}
Gốc = 0               Gốc = 4      Gốc = 5
```

Mảng cha có thể ghi:

```text
x:          0  1  2  3  4  5  6  7
parent[x]:  0  0  0  2  4  5  5  5
```

Từ phần tử 3, ta đi:

```text
3 → parent[3]=2 → parent[2]=0 → parent[0]=0
                                            ^
                                            gốc
```

Vì vậy `find(3)=0`. Từ 7, ta đi `7→5` và dừng vì `parent[5]=5`, nên `find(7)=5`.

### “Rừng” không phải một đồ thị tùy ý

Một đồ thị vô hướng tổng quát có thể chứa chu trình, cạnh song song và nhiều đường đi giữa hai đỉnh. **Rừng cha của DSU** có cấu trúc chặt chẽ hơn:

- Mỗi nút có đúng **một trường cha**.
- Gốc tự trỏ về nó theo quy ước lưu trữ.
- Các nút khác không được tạo **chu trình cha**.
- Mọi đường lần cha đều kết thúc tại một gốc.

Vòng tự trỏ `parent[root]=root` là **ký hiệu kết thúc** của thuật toán, không được coi như một chu trình nhiều nút.

Khi ứng dụng dùng DSU cho đồ thị, rừng cha **không nhất thiết là các cạnh thật của đồ thị đầu vào**. Nó chỉ là cấu trúc phụ để quản lý các thành phần liên thông. Không nên suy ra một cạnh `(x,parent[x])` luôn tồn tại trong đồ thị gốc.

## 3. Các bất biến cốt lõi của biểu diễn cha

Gọi `parent` là mảng có `n` phần tử, mỗi phần tử đã được đăng ký. Một DSU hợp lệ cần thỏa:

**Bất biến 1 — Cha thuộc miền.**

\[
0\le \operatorname{parent}[x]<n
\quad\text{với mọi }0\le x<n.
\]

Không được trỏ tới phần tử không tồn tại hoặc chỉ số đã bị giải phóng.

**Bất biến 2 — Đường đi kết thúc.**

Từ mỗi x, việc liên tục thay `x = parent[x]` phải đến một r có `parent[r] = r` sau hữu hạn bước. Không tồn tại chu trình cha dài từ hai nút trở lên.

**Bất biến 3 — Một gốc cho một cây.**

Mỗi thành phần theo quan hệ cha có **đúng một gốc**; hai cây khác nhau không chia sẻ nút.

**Bất biến 4 — Gốc xác định chính xác nhóm.**

\[
x \sim y \quad\Longleftrightarrow\quad
\operatorname{root}(x)=\operatorname{root}(y).
\]

Hai phần tử có cùng gốc thì cùng nhóm; khác gốc thì khác nhóm.

**Bất biến 5 — Mọi nút thuộc đúng một cây.**

Các cây tạo thành phân hoạch của toàn bộ miền `U`.

Nếu lưu thêm metadata:

- `componentCount` phải bằng **số gốc hiện tại**.
- `size[r]` tại **mỗi gốc r** bằng số nút trong cây của r.
- Tổng `size[r]` trên tất cả gốc phải bằng `n`.

Đây là những điều kiện quan trọng hơn hình dạng cụ thể của mảng cha. **Hai mảng `parent` khác nhau vẫn có thể biểu diễn cùng một phân hoạch.**

## 4. Hai rừng khác nhau có thể mô tả cùng một nhóm

Xét nhóm `{0,1,2,3}`.

**Rừng dạng chuỗi:**

```text
0 ← 1 ← 2 ← 3

parent = [0, 0, 1, 2]
```

**Rừng dạng sao:**

```text
      0
    / | \
   1  2  3

parent = [0, 0, 0, 0]
```

Trong cả hai trường hợp:

```text
find(0) = 0
find(1) = 0
find(2) = 0
find(3) = 0
```

Hai cấu trúc biểu diễn **cùng nhóm logic**, nhưng độ dài đường tới gốc khác nhau:

| Nút | Số cạnh tới gốc trong chuỗi | Số cạnh tới gốc trong sao |
|---:|---:|---:|
| 0 | 0 | 0 |
| 1 | 1 | 1 |
| 2 | 2 | 1 |
| 3 | 3 | 1 |

Nếu phải gọi `find(3)` nhiều lần, cấu trúc dạng sao có lợi hơn. Đó là lý do DSU có các chiến lược **kiểm soát chiều cao** và **nén đường đi**.

### Đại diện không mang ngữ nghĩa “nhỏ nhất”

Ngay cả cùng tập `{0,1,2,3}`, ta có thể chọn gốc là 2:

```text
      2
    / | \
   0  1  3

parent = [2, 2, 2, 2]
```

Lúc đó `find(0)=2`, không phải 0. **Giá trị đại diện chỉ là dấu nhận biết nhóm** do cấu trúc chọn. Nếu ứng dụng yêu cầu “ID nhóm luôn là ID nhỏ nhất”, cần quản lý thêm metadata hoặc dùng chiến lược có hợp đồng khác; không được dựa vào giá trị root của DSU tối ưu thông thường.

## 5. Khởi tạo rừng: mỗi phần tử là một gốc

Với `n` phần tử `0..n-1`, trạng thái ban đầu thường là **n nhóm đơn**:

```text
make_set_all(n):
    for x from 0 to n-1:
        parent[x] = x
        size[x] = 1
    componentCount = n
```

Ví dụ `n=5`:

```text
x:          0  1  2  3  4
parent[x]:  0  1  2  3  4
size[x]:    1  1  1  1  1

Số gốc = 5
Số nhóm = 5
```

Không có liên kết cha giữa hai phần tử khác nhau. Mỗi phần tử vừa là thành viên vừa là đại diện của nhóm đơn.

Khởi tạo có chi phí **`O(n)` thời gian** và **`O(n)` bộ nhớ** cho `parent`, `size`. Nếu `n=0`, cả hai mảng rỗng và số nhóm bằng 0; thuật toán không được tìm “gốc của từ cuối” khi không có phần tử.

### Trường hợp ID không liên tục

Nếu ID là `"acct-A"`, `"acct-B"` hoặc số nguyên rất lớn, ta có thể:

- Dùng `hash map` lưu `parent[id]` và `size[id]` cho các ID đã đăng ký.
- Hoặc ánh xạ ID ngoài sang chỉ số liên tục `0..n-1`, rồi dùng mảng DSU.

Trong cả hai cách, **mỗi phần tử được đăng ký đúng một lần**. Gọi `make_set` trùng và tùy tiện đặt `parent[x]=x` có thể làm phá nhóm cũ, nên API phải từ chối hoặc xử lý như no-op.

## 6. `find(x)` đi tìm gốc như thế nào?

Thuật toán cơ bản đi theo liên kết cha cho tới khi gặp một nút tự trỏ:

```text
find(x):
    require 0 <= x < n
    while parent[x] != x:
        x = parent[x]
    return x
```

Trong rừng hợp lệ, thuật toán **luôn dừng** vì không có chu trình cha dài từ hai nút trở lên. Giá trị trả về chính là đại diện nhóm.

### Truy vết chi tiết

Cho:

```text
parent = [0,0,1,2,4,4,5,6]

Nhóm 1: 0 ← 1 ← 2 ← 3
Nhóm 2: 4 ← 5 ← 6 ← 7
```

Truy vấn `find(3)`:

| Bước | `x` trước bước | `parent[x]` | Hành động |
|---:|---:|---:|---|
| 1 | 3 | 2 | Chuyển sang 2 |
| 2 | 2 | 1 | Chuyển sang 1 |
| 3 | 1 | 0 | Chuyển sang 0 |
| 4 | 0 | 0 | Đã là gốc; trả 0 |

`find(7)` trả 4 theo đường `7→6→5→4`.

Vậy:

```text
find(3) == find(0)  → true
find(3) == find(7)  → false
find(4) == find(7)  → true
```

### Chi phí tìm gốc

Nếu chiều cao cây là `h`, `find(x)` có độ phức tạp **`O(h)`** trong trường hợp x nằm gần đáy.

- Cây hình sao: `h≤1`.
- Cây cân bằng: `h` có thể khoảng `O(log n)`.
- Cây chuỗi không tối ưu: `h` có thể là `Θ(n)`.

Mảng `parent` cho phép **đọc cha từng nút trong `O(1)`**, nhưng toàn bộ phép `find` không tự động là `O(1)` vì có thể phải đi qua nhiều nút cha.

## 7. Vì sao phải hợp hai gốc chứ không nối hai nút tùy ý?

Để hợp hai nhóm chứa x và y, trước hết lấy:

```text
rx = find(x)
ry = find(y)
```

Nếu `rx == ry`, hai phần tử **đã cùng nhóm**; không cần sửa gì. Nếu `rx != ry`, có thể gắn một **gốc** dưới gốc còn lại:

```text
parent[ry] = rx
```

Kết quả: mọi nút trước đây đi tới `ry` sẽ đi tiếp từ `ry` tới `rx`, nên cả hai cây được hợp thành **một cây**.

### Ví dụ hợp nhóm đúng

Trước:

```text
Nhóm A:                Nhóm B:

    0                     4
   / \                    |
  1   2                   5
      |
      3

find(3) = 0            find(5) = 4
```

Gọi `union(3,5)`. Ta phải nối **gốc 0** với **gốc 4**, chẳng hạn `parent[4] = 0`:

```text
       0
     / | \
    1  2  4
       |  |
       3  5

Tất cả {0,1,2,3,4,5} trở thành một nhóm.
```

Ngược lại, nếu chỉ gán `parent[5]=3`:

- Nút 5 sẽ đi tới 0.
- Nút 4 **vẫn là gốc riêng** vì `parent[4]=4`.
- Nhóm trước đó `{4,5}` bị tách sai, thay vì được hợp toàn bộ.

**Kết luận:** phải xác định và nối **hai đại diện**, không đơn thuần nối hai phần tử nhận từ yêu cầu.

### Không nối hai gốc đã bằng nhau

Giả sử `rx=ry=0` mà thuật toán vẫn gắn một nút khác trong cùng cây sai quy tắc. Có thể tạo chu trình cha:

```text
Trước: parent[0]=0, parent[1]=0

Sai:   parent[0]=1
       parent[1]=0

Vòng cha: 0 → 1 → 0 → ...
```

Lúc này `find(0)` không kết thúc. Vì vậy, điều kiện `if rx == ry: return false` là một bước bảo vệ bất biến quan trọng, không chỉ là tối ưu.

## 8. Union by size: chọn gốc để kiểm soát chiều cao

Nếu cứ nối gốc này dưới gốc kia tùy tiện, có thể tạo cây rất dài. **Union by size** giải quyết bằng cách ưu tiên **giữ gốc của nhóm lớn hơn**:

```text
union(x, y):
    rx = find(x)
    ry = find(y)

    if rx == ry:
        return false

    if size[rx] < size[ry]:
        swap(rx, ry)

    parent[ry] = rx
    size[rx] += size[ry]
    componentCount -= 1
    return true
```

Ở đây `size[root]` là số nút trong cây của **gốc hiện tại**.

Ví dụ:

```text
Gốc 0: nhóm {0,1}, size[0] = 2
Gốc 2: nhóm {2,3,4}, size[2] = 3

union(0,2):
    rx = 0, ry = 2
    size[0] < size[2] → đổi rx và ry
    parent[0] = 2
    size[2] = 5

Gốc mới của cả nhóm là 2, không phải 0.
```

Đại diện có thể thay đổi sau `union`. Nếu trước phép hợp ta lưu `oldRoot = find(1) = 0` rồi sau đó tra cứu nhóm qua `oldRoot` mà không gọi lại `find(oldRoot)`, ta có thể đọc metadata đã lỗi thời.

### Bất biến `size`

Chỉ dựa vào `size[r]` khi `r` là gốc:

\[
\operatorname{componentSize}(x)
=\operatorname{size}[\operatorname{find}(x)].
\]

Sau khi nối `ry` dưới `rx`, `size[rx]` được cộng, còn `size[ry]` có thể giữ giá trị cũ. Không được hiểu `size[ry]` là kích thước nhóm sau hợp khi `ry` không còn là gốc.

Tổng kích thước ở **tất cả các gốc hiện tại** vẫn bằng `n`:

\[
\sum_{\text{r: parent[r] = r}}\operatorname{size}[r]=n.
\]

### Vì sao union by size hạn chế chiều cao?

Khi cây kích thước `a` được nối dưới cây kích thước `b≥a`, nhóm mới có ít nhất `2a` nút. Mỗi lần độ sâu của một nút tăng vì cây chứa nó bị nối dưới cây khác, kích thước nhóm chứa nó ít nhất **gấp đôi**.

Một nhóm không thể có hơn `n` nút, nên độ sâu của một nút chỉ có thể tăng nhiều nhất `⌊log₂ n⌋` lần. Vì vậy, **union by size mà chưa nén đường đi** cho chiều cao cây `O(log n)`.

Đây là ưu điểm của chính sách chọn đại diện: không cần đại diện có ý nghĩa nghiệp vụ; ta chọn gốc giúp đường tìm ngắn hơn.

### Union by rank là biến thể liên quan

Union by rank thay `size` bằng một chỉ số `rank` để ước lượng/giới hạn độ cao. Khi rank của hai gốc khác nhau, nối gốc rank thấp vào gốc rank cao; khi bằng nhau, tăng rank của gốc mới.

Sau path compression, `rank` **không nhất thiết bằng chiều cao thực tế**. `Rank` cũng không phải số thành viên. Nếu cần hỏi kích thước nhóm, phải lưu metadata kích thước riêng hoặc dùng union by size.

## 9. Path compression: thay hình dạng cây mà không đổi đại diện logic

Khi nhiều lần gọi `find` trên những nút sâu, ta có thể **rút ngắn đường cha** bằng cách cho các nút đã đi qua trỏ thẳng tới gốc.

Trước `find(3)`:

```text
       0
       |
       1
       |
       2
       |
       3
```

Sau **full path compression**:

```text
       0
     / | \
    1  2  3
```

Mảng trước:

```text
parent = [0,0,1,2]
```

Mảng sau:

```text
parent = [0,0,0,0]
```

Cả trước và sau, `find(3)=0`. Ta chỉ đổi những cạnh cha **trong cùng một cây**, nên nhóm `{0,1,2,3}` không đổi.

### Cách viết đệ quy

```text
find(x):
    if parent[x] != x:
        parent[x] = find(parent[x])
    return parent[x]
```

Sau khi lời gọi sâu hơn trả về gốc, dòng gán cập nhật cha của x thành gốc.

### Cách viết lặp, hai lượt

```text
find(x):
    root = x

    while parent[root] != root:
        root = parent[root]

    while parent[x] != x:
        next = parent[x]
        parent[x] = root
        x = next

    return root
```

Phải lưu `next` **trước khi sửa** `parent[x]` để không mất đường cha cũ trong lượt nén.

Cách lặp phù hợp khi không muốn phụ thuộc vào độ sâu đệ quy. Một biến thể khác là **path halving**, cho mỗi nút trỏ tới ông/bà trong lúc đi; nó có thể cho mảng cha cuối khác full compression nhưng vẫn giữ đúng các đại diện.

### Hai bất biến được giữ nguyên

- Mỗi nút được nén vẫn thuộc **cùng cây và cùng gốc**.
- Tổng số nhóm và `size[root]` **không thay đổi** khi chỉ gọi `find`.

Nén đường đi không phải một phép `union` và không được cập nhật `componentCount`.

**Lưu ý về đồng thời:** `find` có path compression **có thể ghi** vào mảng `parent`, dù giao diện trông giống truy vấn. Cần cơ chế đồng bộ hoặc thuật toán concurrent chuyên dụng nếu nhiều luồng cùng thao tác trên một DSU.

## 10. Mô phỏng rừng qua một chuỗi phép hợp và tìm

Khởi tạo 8 phần tử:

```text
parent = [0,1,2,3,4,5,6,7]
size   = [1,1,1,1,1,1,1,1]
components = 8
```

Giả sử dùng **union by size**, và khi hai nhóm bằng kích thước thì giữ gốc của đối số đầu sau khi tìm gốc.

| Bước | Phép toán | `parent` sau phép toán | Số nhóm |
|---:|---|---|---:|
| 0 | Khởi tạo | `[0,1,2,3,4,5,6,7]` | 8 |
| 1 | `union(0,1)` | `[0,0,2,3,4,5,6,7]` | 7 |
| 2 | `union(2,3)` | `[0,0,2,2,4,5,6,7]` | 6 |
| 3 | `union(1,2)` | `[0,0,0,2,4,5,6,7]` | 5 |
| 4 | `find(3)`, nén đầy đủ | `[0,0,0,0,4,5,6,7]` | 5 |
| 5 | `union(4,5)` | `[0,0,0,0,4,4,6,7]` | 4 |
| 6 | `union(5,0)` | `[0,0,0,0,0,4,6,7]` | 3 |
| 7 | `union(6,7)` | `[0,0,0,0,0,4,6,6]` | 2 |
| 8 | `find(5)`, nén đầy đủ | `[0,0,0,0,0,0,6,6]` | 2 |

Giải thích:

- **Bước 3:** hai nhóm `{0,1}` và `{2,3}` đều có kích thước 2. Gốc 2 nối dưới gốc 0, nhưng `parent[3]` vẫn là 2.
- **Bước 4:** `find(3)` tìm đường `3→2→0` rồi đổi `parent[3]=0`. **Không hợp thêm nhóm**, số nhóm vẫn 5.
- **Bước 6:** nhóm gốc 4 chỉ có 2 thành viên, còn nhóm gốc 0 có 4 thành viên. Vì dùng union by size, gốc 4 nối dưới gốc 0, còn `parent[5]=4` cho tới khi được nén.
- **Bước 8:** `find(5)` nén `5→4→0` thành `5→0`, không thay đổi phân hoạch.

Trạng thái cuối:

```text
Gốc 0: {0,1,2,3,4,5}  (size[0] = 6)
Gốc 6: {6,7}          (size[6] = 2)

Số nhóm = 2
Tổng kích thước tại các gốc = 6 + 2 = 8
```

Các phép kiểm tra:

```text
find(2) == find(5)   → true
find(0) == find(7)   → false
size[find(5)]        → 6
size[find(7)]        → 2
```

Một triển khai chọn gốc khác có thể tạo mảng cha khác, nhưng phải cho **cùng phân hoạch và số phần tử**.

## 11. Python: DSU đầy đủ với rừng cha và metadata kích thước

Đoạn mã dưới đây làm rõ mảng `parent`, gốc, `size`, số nhóm và các thao tác. `find` dùng full path compression dạng lặp; `union` áp dụng union by size.

```python
class DSU:
    def __init__(self, n: int):
        if n < 0:
            raise ValueError("n phải không âm")
        self.parent = list(range(n))
        self.size = [1] * n
        self.component_count = n

    def _check(self, x: int) -> None:
        if not 0 <= x < len(self.parent):
            raise IndexError("Phần tử ngoài miền")

    def find(self, x: int) -> int:
        self._check(x)

        # Lượt 1: tìm gốc.
        root = x
        while self.parent[root] != root:
            root = self.parent[root]

        # Lượt 2: nén đường tới gốc.
        while self.parent[x] != x:
            next_x = self.parent[x]
            self.parent[x] = root
            x = next_x

        return root

    def union(self, x: int, y: int) -> bool:
        rx = self.find(x)
        ry = self.find(y)

        if rx == ry:
            return False

        if self.size[rx] < self.size[ry]:
            rx, ry = ry, rx

        self.parent[ry] = rx
        self.size[rx] += self.size[ry]
        self.component_count -= 1
        return True

    def same(self, x: int, y: int) -> bool:
        return self.find(x) == self.find(y)

    def component_size(self, x: int) -> int:
        return self.size[self.find(x)]

    def groups(self) -> dict[int, list[int]]:
        # Chỉ xây danh sách thành viên khi cần xuất nhóm.
        result: dict[int, list[int]] = {}
        for x in range(len(self.parent)):
            r = self.find(x)
            result.setdefault(r, []).append(x)
        return result


dsu = DSU(8)
assert dsu.component_count == 8

assert dsu.union(0, 1)
assert dsu.union(2, 3)
assert dsu.union(1, 2)
assert dsu.same(0, 3)

assert dsu.component_size(3) == 4
assert dsu.union(4, 5)
assert dsu.union(5, 0)
assert dsu.union(6, 7)

assert dsu.component_count == 2
assert dsu.component_size(5) == 6
assert dsu.component_size(7) == 2
assert dsu.union(1, 5) is False  # Đã cùng nhóm.

print(dsu.groups())
# {0: [0, 1, 2, 3, 4, 5], 6: [6, 7]}
```

### Những điểm cần chú ý trong triển khai

- `_check` bảo vệ khỏi chỉ số âm và chỉ số lớn hơn `n-1`. Trong Python, `parent[-1]` có nghĩa hợp lệ đối với list nhưng **không phải** thành viên `-1` của DSU này.
- `find` luôn trả **gốc tự trỏ**. Mọi lần nén đường đi đều giữ gốc đó.
- `union` chỉ nối khi hai gốc khác nhau, vì vậy không tạo vòng cha và không trừ số nhóm nhiều lần.
- `size[ry]` sau khi nối có thể còn giá trị cũ; chỉ `size[root]` của **gốc hiện tại** được dùng để trả kích thước.
- `groups()` quét toàn bộ miền, vì DSU không bắt buộc lưu các thành viên trong mỗi cây.

**Độ phức tạp `groups()`:** phải xét hết `n` phần tử và tạo `n` phần tử đầu ra, nên ít nhất là `Ω(n)` thời gian và `O(n)` bộ nhớ bổ sung. Nếu không cần liệt kê các nhóm, chỉ lưu `parent` và `size` tiết kiệm thao tác và dữ liệu phụ hơn.

## 12. C++: nhìn mảng cha như một cấu trúc liên tiếp trong bộ nhớ

Khi các phần tử là những chỉ số liên tục, có thể dùng hai `std::vector` để giữ `parent` và `size`. Cách này tránh hash map và thường cho khả năng truy cập bộ nhớ tốt.

Ví dụ C++17:

```cpp
#include <algorithm>
#include <cstddef>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <vector>

class DSU {
public:
    explicit DSU(std::size_t n)
        : parent_(n), size_(n, 1), groups_(n) {
        std::iota(parent_.begin(), parent_.end(), std::size_t{0});
    }

    std::size_t find(std::size_t x) {
        if (x >= parent_.size()) {
            throw std::out_of_range("Invalid DSU index");
        }

        // Full path compression lặp, không dùng đệ quy.
        std::size_t root = x;
        while (parent_[root] != root) {
            root = parent_[root];
        }
        while (parent_[x] != x) {
            std::size_t next = parent_[x];
            parent_[x] = root;
            x = next;
        }
        return root;
    }

    bool unite(std::size_t x, std::size_t y) {
        x = find(x);
        y = find(y);

        if (x == y) return false;

        if (size_[x] < size_[y]) std::swap(x, y);

        parent_[y] = x;
        size_[x] += size_[y];
        --groups_;
        return true;
    }

    bool same(std::size_t x, std::size_t y) {
        return find(x) == find(y);
    }

    std::size_t component_size(std::size_t x) {
        return size_[find(x)];
    }

    std::size_t component_count() const {
        return groups_;
    }

private:
    std::vector<std::size_t> parent_;
    std::vector<std::size_t> size_;
    std::size_t groups_;
};

int main() {
    DSU dsu(6);
    dsu.unite(0, 1);
    dsu.unite(2, 3);
    dsu.unite(1, 2);

    std::cout << dsu.same(0, 3) << '\n';       // 1
    std::cout << dsu.component_size(1) << '\n'; // 4
    std::cout << dsu.component_count() << '\n'; // 3
}
```

**Chú ý:** `std::size_t` là kiểu không dấu, vì vậy không có giá trị x âm trong giao diện này; vẫn phải kiểm tra `x >= parent_.size()`. Việc dùng vector bảo đảm mảng cha có vùng lưu trữ đủ cho `n` phần tử, nhưng **chính các thao tác `unite`/`find` mới duy trì bất biến rừng**, không phải việc chọn vector tự đảm bảo đúng.

## 13. Chứng minh rừng còn hợp lệ sau các thao tác

Ta có thể chứng minh tính đúng đắn bằng **quy nạp** trên chuỗi thao tác.

### Bước cơ sở: khởi tạo

Mỗi phần tử x có `parent[x]=x`. Có `n` cây đơn, mỗi cây một gốc. Các cây rời nhau, hợp thành toàn miền. Do đó mọi bất biến đều đúng.

### `find` không nén đường đi

Thuật toán chỉ đọc theo các liên kết cha, không thay `parent`. Nó tới đúng một gốc vì rừng hợp lệ. Phân hoạch không đổi.

### `find` có nén đường đi

Mỗi nút trên đường từ x tới gốc r được cho trỏ **trực tiếp tới r**, vốn là một tổ tiên của nó trong cùng cây. Vì vậy:

- Không phần tử nào bị chuyển sang cây khác.
- Gốc r vẫn là gốc.
- Không tạo chu trình mới: đường mới chỉ đi thẳng lên gốc.
- Số nhóm và kích thước các nhóm giữ nguyên.

### `union` khi hai gốc bằng nhau

Nếu `rx==ry`, x và y đã cùng cây. Thuật toán không thay liên kết cha, nên mọi bất biến giữ nguyên.

### `union` khi hai gốc khác nhau

Hai gốc thuộc **hai cây rời nhau**. Gắn gốc `ry` dưới gốc `rx`:

- Không thể tạo chu trình, vì trước đó không có đường cha từ `rx` tới `ry` trong cùng cây.
- Mọi nút trong cây cũ của `ry` giờ tới được gốc `rx`.
- Các cây khác không đổi.
- Hai nhóm được hợp thành đúng một nhóm; số nhóm giảm 1.
- Nếu dùng `size`, đặt `size[rx] = size[rx] + size[ry]` để phản ánh kích thước mới.

Vậy các bất biến tiếp tục đúng sau mọi thao tác.

### Một điểm thường nhầm khi diễn giải rừng

**Đại diện thay đổi không có nghĩa một phần tử chuyển sang một nhóm “khác” theo ý nghĩa nghiệp vụ.** Khi hai nhóm được hợp, toàn bộ hai nhóm hình thành một lớp tương đương mới. Gốc mới đơn thuần được chọn để hiện thực lớp đó. Những gì phải ổn định là **kết quả câu hỏi cùng nhóm**, chứ không phải giá trị nguyên của đại diện qua thời gian.

## 14. Độ phức tạp: đại diện càng dễ tới, truy vấn càng nhanh

Đặt:

- `n`: số phần tử.
- `m`: số lần gọi `find`, `union`, `same` trong một chuỗi thao tác.
- `h`: chiều cao cây.
- `α`: hàm Ackermann ngược, tăng cực kỳ chậm.

| Chiến lược | `find(x)` | `union(x,y)` | Bộ nhớ |
|---|---|---|---|
| Rừng cha, nối gốc tùy ý, không nén | `O(h)`, xấu nhất `O(n)` | `O(h)` cho hai lần tìm | `O(n)` |
| Union by size, không nén | `O(log n)` xấu nhất | `O(log n)` xấu nhất | `O(n)` |
| Union by size + path compression | `O(α(n))` **khấu hao** theo chuỗi thao tác, dạng phát biểu thông dụng | `O(α(n))` **khấu hao** | `O(n)` |

Khởi tạo hai mảng mất `O(n)` thời gian và `O(n)` bộ nhớ.

Chi phí của `find` phải cộng qua **các cạnh cha đã đi**, không chỉ tính một lần truy cập mảng. Path compression khiến các lần tìm sau thường ngắn hơn. Với union by size và path compression, tổng chi phí các thao tác có chặn gần tuyến tính theo số thao tác, thường mô tả bằng các biểu thức liên quan `α(n)`; cách viết chính xác có thể phụ thuộc cả số lần thao tác và cách tính khởi tạo.

**Khấu hao không phải worst-case mỗi lời gọi.** Một lần `find` vẫn có thể đi qua nhiều cạnh trước khi nén. Không được khẳng định `find` chắc chắn mất đúng một bước hoặc `O(1)` worst-case chỉ vì `α(n)` rất nhỏ trên dữ liệu thực tế.

### Bộ nhớ và vấn đề định danh

Mảng `parent` có `n` mục, `size` có `n` mục và biến đếm số nhóm cần bộ nhớ hằng số; tổng là **`O(n)`**.

Nếu mỗi phần tử mang ID chuỗi hoặc số nguyên rải rác, có thể cần bảng ánh xạ `externalID→index`. Khi đó phải cộng overhead của bảng, và không thể suy bộ nhớ chỉ từ `2n` số nguyên.

## 15. Sử dụng đại diện để giải quyết bài toán đồ thị

Với đồ thị **vô hướng**, thành phần liên thông là tập đỉnh có đường đi qua các cạnh. Khi chỉ **thêm cạnh**, mỗi lần thêm cạnh `(u,v)` có thể gọi `union(u,v)`. Hai đỉnh liên thông khi:

\[
\operatorname{find}(u)=\operatorname{find}(v).
\]

Ví dụ:

```text
Đỉnh: 0 1 2 3 4 5
Thêm cạnh: (0,1), (2,3), (1,2)

Thành phần cuối:
{0,1,2,3}, {4}, {5}
```

DSU không cần giữ lại toàn bộ cạnh để trả lời **liên thông hiện tại** sau các phép thêm cạnh. Nhưng nếu ứng dụng muốn tìm **đường đi cụ thể** giữa 0 và 3, rừng cha không đủ: cạnh cha có thể chỉ là liên kết đại diện, không phải cạnh thực. Phải lưu đồ thị và dùng BFS/DFS hoặc một cấu trúc đường đi thích hợp.

### Phát hiện chu trình khi xây rừng

Khi xây một rừng cạnh đã chấp nhận, nếu cạnh mới nối hai đỉnh có **cùng đại diện**, thêm nó sẽ tạo chu trình trong rừng. Nếu đại diện khác nhau, ta có thể chấp nhận cạnh và hợp hai thành phần.

```text
for each undirected edge (u, v):
    if find(u) == find(v):
        reject(edge)   // Hai đầu đã có đường đi trong rừng.
    else:
        accept(edge)
        union(u, v)
```

Đây là nền tảng thao tác nhóm trong **thuật toán Kruskal** tìm cây khung nhỏ nhất. Thời gian của toàn Kruskal còn bao gồm sắp xếp cạnh; không được đánh đồng nó với riêng chi phí `union`/`find`.

### Vì sao xóa cạnh không được giải bằng DSU cơ bản?

Một phép xóa cạnh có thể tách một thành phần liên thông thành hai thành phần hoặc không tách nếu còn đường khác. DSU cơ bản chỉ biết **hợp nhóm**, không có đủ thông tin về các cạnh để **tách nhóm**. Cần dựng lại trạng thái từ các cạnh còn lại hoặc dùng thuật toán liên thông động thích hợp.

## 16. Đại diện là chi tiết kỹ thuật, không phải ID nhóm bền vững

Xét trình tự:

```text
union(0,1)   → nhóm {0,1}, gốc 0, size 2
union(2,3)   → nhóm {2,3}, gốc 2, size 2
union(2,4)   → nhóm {2,3,4}, gốc 2, size 3

Trước khi hợp:
find(1) = 0

union(0,2)
  → nhóm {0,1} nhỏ hơn {2,3,4}
  → parent[0] = 2

Sau khi hợp:
find(1) = 2
find(0) = 2
```

**Root của nhóm chứa 1 đã đổi từ 0 sang 2**, dù 1 không bị xóa hay được đăng ký lại.

Nếu hệ thống hiển thị ID nhóm cho người dùng, hoặc dùng ID đó trong khóa ngoại cơ sở dữ liệu, không nên dùng trực tiếp giá trị trả về của `find` làm ID vĩnh viễn. Có thể:

- Quản lý **một mã nhóm nghiệp vụ** tách biệt, rồi cập nhật/ánh xạ theo quy tắc khi hợp.
- Định nghĩa **metadata được gộp** theo một chính sách rõ ràng, ví dụ tên hiển thị ưu tiên hay thời điểm tạo cũ nhất.
- Trả về một **đối tượng nhóm nghiệp vụ ổn định** thay vì lộ giá trị root nội bộ.

Chính sách chọn root của DSU nhằm tối ưu hiệu năng; chính sách ID nghiệp vụ phải đáp ứng yêu cầu sản phẩm và dữ liệu.

## 17. Kiểm chứng rừng và bắt lỗi triển khai

Một bài kiểm thử nhỏ có thể kiểm tra trực tiếp bất biến sau một chuỗi thao tác.

### Kiểm tra nhóm bằng cách dựng lại theo đại diện

```python
def validate_partition(dsu: DSU) -> None:
    n = len(dsu.parent)

    # parent[x] luôn trỏ tới phần tử hợp lệ.
    assert all(0 <= p < n for p in dsu.parent)

    # Gọi find(x) để kiểm tra mọi nút tới được gốc.
    groups: dict[int, list[int]] = {}
    for x in range(n):
        root = dsu.find(x)
        assert dsu.parent[root] == root
        groups.setdefault(root, []).append(x)

    assert len(groups) == dsu.component_count

    # size đúng ở từng gốc.
    for root, members in groups.items():
        assert dsu.size[root] == len(members)

    assert sum(dsu.size[r] for r in groups) == n


check = DSU(6)
check.union(0, 1)
check.union(2, 3)
check.union(1, 2)
validate_partition(check)
```

**Giới hạn của phép kiểm tra:** đoạn này giả định DSU đã có rừng hợp lệ để `find` kết thúc. Nếu nghi ngờ dữ liệu `parent` bị hỏng và có chu trình, cần một trình kiểm tra riêng có **phát hiện chu trình/giới hạn số bước** trước khi gọi `find` thông thường, tránh vòng lặp vô hạn.

### Kiểm tra chu trình cha trên dữ liệu có thể đã hỏng

Với mảng `parent` đầu vào, có thể dò đường cha của từng nút bằng trạng thái ba màu hoặc tập các nút trên đường. Nếu gặp lại một nút chưa phải gốc tự trỏ, đã phát hiện **chu trình không hợp lệ**. Một phép kiểm tra đầy đủ phải phân biệt vòng tự trỏ tại gốc với chu trình hai nút trở lên.

Nếu DSU chỉ thay đổi qua `find`/`union` được triển khai đúng, không cần chạy kiểm tra toàn rừng sau mỗi thao tác. Phép kiểm tra phù hợp trong **unit test, debug hoặc kiểm tra dữ liệu nhập**.

### Các trường hợp nên đưa vào test

- `n=0`: rừng rỗng và số nhóm bằng 0.
- `n=1`: `find(0)=0`, gọi `union(0,0)` không thay đổi nhóm.
- Chỉ số âm, `x=n` hoặc phần tử chưa đăng ký: phải có cách báo lỗi rõ ràng.
- `union` hai phần tử vốn đã cùng gốc: không cập nhật `size` và `componentCount`.
- Nhiều phép hợp tạo đường cha dài rồi `find`: nén đường đi nhưng không đổi phân hoạch.
- Hợp hai nhóm bằng kích thước: chọn root tùy quy tắc nhưng kết quả same/size/count phải đúng.
- Hợp nhóm có root đã đổi: mọi phần tử nhóm cũ vẫn truy được gốc mới.
- Nếu có nhiều luồng: kiểm tra hoặc chứng minh cơ chế đồng bộ, không dựa vào mã đơn luồng.

## 18. Lỗi phổ biến khi đọc hoặc sửa mảng `parent`

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Coi `parent[x]` luôn là đại diện của x | Có thể chỉ là cha trung gian | Gọi `find(x)` để đi tới gốc |
| Coi mọi phần tử có cùng cha trực tiếp mới cùng nhóm | Bỏ sót các nhánh và đường cha dài | So sánh **gốc**, không so sánh cha trực tiếp |
| Gắn `parent[y]=x` khi union | Chỉ chuyển một nút, không hợp trọn hai cây | Tìm hai gốc và nối gốc với gốc |
| Không kiểm tra hai gốc trùng nhau | Có thể tạo chu trình hoặc cập nhật sai metadata | Khi `rx==ry`, trả no-op |
| Coi root là phần tử nhỏ nhất | Sai nếu union by size/rank chọn root khác | Coi root là nhãn kỹ thuật |
| Dùng `size[x]` khi x không là gốc | Có thể đọc kích thước cũ | Dùng `size[find(x)]` |
| Tưởng nén đường đi làm đổi nhóm | Nhầm hình dạng rừng với phân hoạch | Theo dõi tập các nút có cùng gốc |
| Tưởng `find` có nén là hàm chỉ đọc | Có thể ghi vào nhiều ô `parent` | Xem lại yêu cầu đồng thời |
| Truy cập `parent[-1]` trong Python | Lấy phần tử cuối thay vì báo lỗi | Kiểm tra chỉ số thuộc `[0,n)` |
| Giả sử cạnh cha là cạnh đồ thị gốc | Suy ra đường đi không tồn tại | Giữ đồ thị riêng nếu cần đường đi |
| Xóa cạnh rồi mong DSU tự tách nhóm | Trạng thái liên thông có thể sai | Dựng lại hoặc dùng dynamic connectivity |
| Phân tích `find` chỉ bằng một lần đọc mảng | Bỏ qua đường cha độ cao `h` | Tính chi phí theo số cạnh đã đi |

## 19. Chọn cấu trúc dựa trên thao tác cần thiết

| Yêu cầu | Cấu trúc/gợi ý | Giải thích |
|---|---|---|
| Hợp dần các nhóm, kiểm tra cùng nhóm | **DSU rừng cha** | Đại diện cho phép kiểm tra hiệu quả |
| Các ID liên tục `0..n-1` | **Mảng `parent`, `size`** | Truy cập nhanh, bộ nhớ `O(n)` |
| ID chuỗi hoặc ID rất thưa | **Hash map** hoặc remapping rồi dùng DSU | Không cần cấp phát tới ID lớn nhất |
| Cần đọc kích thước nhóm thường xuyên | **Union by size + `size[root]`** | Có sẵn thông tin sau `find` |
| Cần liệt kê mọi thành viên nhóm liên tục | DSU + chỉ mục thành viên, hoặc cấu trúc khác | Rừng cha không lưu sẵn danh sách thành viên |
| Cần đường đi giữa hai đỉnh | **BFS/DFS trên đồ thị** | Root chỉ cho biết liên thông |
| Cần xóa cạnh, tách thành phần | **Dynamic connectivity/offline phù hợp** | DSU kinh điển không có split |
| Cần đại diện ổn định theo nghĩa nghiệp vụ | **Metadata/ID nhóm riêng** | Root có thể thay đổi khi union |
| Cần truy cập đồng thời từ nhiều luồng | Đồng bộ hoặc concurrent DSU chuyên dụng | `find` nén đường và `union` đều có thể ghi |

DSU là một lựa chọn mạnh khi **bài toán chủ yếu là hợp nhóm và hỏi cùng nhóm**, nhưng không thay thế mọi cấu trúc tập hợp, cây hay đồ thị. Phải cân nhắc **ngữ nghĩa nhóm, thao tác chủ đạo, cách đánh ID, chi phí và tính đúng đắn**.

## 20. Bài tập tự kiểm tra có lời giải

**Câu 1.** Với `parent=[0,0,0,2,4,5,5,5]`, gốc của phần tử 3 và 7 là gì? Có bao nhiêu nhóm?

**Đáp án:** `find(3)=0` qua đường `3→2→0`; `find(7)=5` qua `7→5`. Các gốc là 0, 4, 5 nên có **3 nhóm**.

**Câu 2.** Hai mảng `[0,0,1,2]` và `[0,0,0,0]` có biểu diễn cùng phân hoạch trên miền `{0,1,2,3}` không?

**Đáp án:** Có. Trong cả hai, mọi phần tử đều tìm tới gốc 0, nên chỉ có một nhóm `{0,1,2,3}`, dù hình dạng cha khác nhau.

**Câu 3.** Vì sao so sánh `parent[x] == parent[y]` không phải cách đúng tổng quát để biết x và y cùng nhóm?

**Đáp án:** Hai nút trong cùng cây có thể có **cha trực tiếp khác nhau**. Cần so sánh `find(x) == find(y)`, tức gốc cuối cùng.

**Câu 4.** Nếu gốc của nhóm `{0,1}` là 0 và gốc của nhóm `{2,3,4}` là 2, union by size sẽ chọn gốc nào khi hợp hai nhóm?

**Đáp án:** Nhóm kích thước 3 lớn hơn, nên gốc 2 được giữ; gốc 0 nối dưới 2. `find(1)` sau hợp trả 2 dù trước đó trả 0.

**Câu 5.** Với `n=8` có 8 nhóm đơn, thực hiện 5 phép `union` hợp được **hai gốc khác nhau** và một phép hợp trùng. Cuối cùng còn bao nhiêu nhóm?

**Đáp án:** Còn `8−5=3` nhóm. Phép hợp trùng không giảm số nhóm.

**Câu 6.** Một DSU có `parent[0]=1` và `parent[1]=0`. Đây có phải rừng hợp lệ không?

**Đáp án:** Không. Hai nút tạo chu trình `0→1→0` không có gốc tự trỏ. `find` kiểu đơn giản không kết thúc.

**Câu 7.** Tại sao gắn gốc của một cây vào gốc của một cây **khác** không tạo chu trình cha?

**Đáp án:** Trước khi nối, không có đường cha giữa hai cây rời nhau. Liên kết mới đi từ một gốc sang gốc của cây kia, không có đường quay lại gốc cũ, nên vẫn là cây.

**Câu 8.** `find(3)` nén đường `3→2→0` thành `3→0`. Số nhóm và kích thước nhóm thay đổi thế nào?

**Đáp án:** Không thay đổi. Chỉ rút ngắn đường cha nội bộ trong cùng một cây; số nhóm và `size[root]` giữ nguyên.

**Câu 9.** Khi dùng union by size nhưng không path compression, chiều cao cây bị chặn thế nào?

**Đáp án:** `O(log n)`. Mỗi lần độ sâu của nút tăng vì cây chứa nó bị nối dưới cây khác, số phần tử nhóm chứa nó ít nhất gấp đôi.

**Câu 10.** Vì sao DSU có union by size và path compression không nên được mô tả là `find` luôn `O(1)` worst-case?

**Đáp án:** Kết quả gần hằng số là **khấu hao trên chuỗi thao tác**, thường mô tả qua hàm Ackermann ngược. Một lần tìm cụ thể vẫn có thể đi qua nhiều cạnh trước khi nén.

**Câu 11.** Có thể coi `parent[x]` là một đỉnh kề trực tiếp của x trong đồ thị vô hướng ban đầu không?

**Đáp án:** Không. Cha trong DSU là quan hệ **quản lý đại diện**, có thể được tạo bằng union của hai nhóm và path compression, không nhất thiết tương ứng cạnh đồ thị đầu vào.

**Câu 12.** Muốn hiển thị mã nhóm cố định trong giao diện người dùng, có nên lưu trực tiếp `find(x)` làm ID vĩnh viễn không?

**Đáp án:** Không nên. Root có thể đổi sau union. Cần duy trì một ID nghiệp vụ riêng và quy tắc ánh xạ/gộp metadata rõ ràng.

**Câu 13.** Một nhóm có 6 nút; `size` tại các nút con có thể lần lượt là 1, 2, 1, 3. Cần đọc ô `size` nào để biết kích thước nhóm hiện tại?

**Đáp án:** Chỉ dùng `size[find(x)]` — metadata của **gốc hiện tại**. Các giá trị tại nút con có thể là dữ liệu cũ.

**Câu 14.** Nếu cần quản lý kết nối của mạng khi vừa thêm **vừa xóa** cạnh liên tục, rừng cha của DSU kinh điển có đủ không?

**Đáp án:** Không trực tiếp. DSU chuẩn chỉ gộp các thành phần, không chia tách khi một cạnh bị xóa. Cần dựng lại hoặc dùng thuật toán liên thông động.

**Câu 15.** Sau một chuỗi thao tác trên 8 phần tử, có hai gốc với `size` lần lượt 6 và 2. Điều gì phải đúng với tổng số nhóm và tổng kích thước?

**Đáp án:** `componentCount=2` và tổng `size` của **hai gốc hiện tại** bằng `6+2=8`. Đây là các bất biến cần thiết để metadata nhất quán với phân hoạch.

## Ghi nhớ

- **Đại diện của nhóm** là **gốc** của cây cha. Hai phần tử cùng nhóm **khi và chỉ khi** `find(x) == find(y)`; không được suy chỉ từ cha trực tiếp.
- **Rừng cây cha** gồm các cây rời nhau. Mỗi gốc tự trỏ `parent[root]=root`, mọi đường cha phải tới một gốc và không được có chu trình cha khác.
- **Union** phải nối **hai gốc của hai cây khác nhau**, nhờ đó gộp trọn nhóm và giảm số nhóm đúng một lần. **Union by size** chọn gốc giúp hạn chế chiều cao; **path compression** rút ngắn đường cha mà không đổi phân hoạch.
- **Đại diện không phải ID nhóm bền vững**: nó có thể thay đổi sau hợp. Metadata `size` chỉ được tin khi đọc tại **gốc hiện tại**.
- Mảng `parent` và `size` dùng **`O(n)` bộ nhớ**; union by size không nén cho truy vấn `O(log n)` xấu nhất, kết hợp nén đường đi cho chi phí gần hằng số **khấu hao** qua chuỗi thao tác.
- DSU rất phù hợp với **hợp nhóm và kiểm tra liên thông khi thêm cạnh**, nhưng rừng cha không nhất thiết là cạnh đồ thị gốc, và DSU chuẩn **không hỗ trợ trực tiếp tách nhóm, xóa cạnh hay tìm đường đi cụ thể**.

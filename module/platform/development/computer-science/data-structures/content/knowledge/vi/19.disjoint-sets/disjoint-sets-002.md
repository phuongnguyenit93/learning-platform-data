# Các phép make-set, find và union

Một dịch vụ quản lý những máy tính đang kết nối trong mạng. Ban đầu mỗi máy là một thành phần riêng; khi xuất hiện một liên kết hai chiều mới, hệ thống cần **hợp hai thành phần**. Người quản trị hỏi liên tục: “Máy A và máy D có đang ở cùng thành phần liên thông?”, “Nhóm chứa máy C có bao nhiêu máy?” và “Việc thêm liên kết A–D có thực sự làm giảm số nhóm không?”.

Cấu trúc dữ liệu **Disjoint Set Union (DSU)**, còn gọi là **Union–Find**, được thiết kế cho đúng chuỗi yêu cầu này. Nó duy trì một **phân hoạch** của tập phần tử: mỗi phần tử thuộc đúng một nhóm, các nhóm không giao nhau, và một lần hợp nhóm có thể khiến nhiều phần tử trở thành cùng nhóm mà không cần cập nhật riêng từng cặp.

Trong chương **Tập hợp rời nhau** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**, bài này phân tích chi tiết **ba phép nền tảng `make-set`, `find`, `union`**, bất biến của biểu diễn bằng rừng cây, hai tối ưu **union by size** và **path compression**, cách kiểm tra tính đúng đắn, cùng độ phức tạp thời gian và bộ nhớ. Đây là một tình huống điển hình để chọn cấu trúc phù hợp giữa mảng, bảng băm, cây và đồ thị dựa trên thao tác thực sự cần thực hiện.

## 1. Hợp đồng bài toán: các nhóm là một phân hoạch

Gọi `U` là tập tất cả phần tử đã đăng ký, chẳng hạn:

\[
U=\{0,1,2,3,4,5\}.
\]

Ở một thời điểm, `U` được chia thành các nhóm:

\[
P=\{G_1,G_2,\ldots,G_c\}.
\]

Bất biến **phân hoạch** gồm ba điều kiện:

1. Không có nhóm rỗng: `G_i ≠ ∅`.
2. Hai nhóm khác nhau không có thành viên chung: `G_i ∩ G_j = ∅` nếu `i ≠ j`.
3. Mọi phần tử đã đăng ký nằm trong đúng một nhóm: `G_1 ∪ ... ∪ G_c = U`.

Ví dụ:

```text
Ban đầu:
  {0}  {1}  {2}  {3}  {4}  {5}

Sau union(0,1):
  {0,1}     {2}  {3}  {4}  {5}

Sau union(2,3):
  {0,1}     {2,3}    {4}  {5}

Sau union(1,2):
  {0,1,2,3}          {4}  {5}
```

Điểm mấu chốt: phép `union(1,2)` hợp **toàn bộ nhóm chứa 1** với **toàn bộ nhóm chứa 2**. Nó không chỉ ghi rằng hai phần tử 1 và 2 có một liên kết trực tiếp.

Ký hiệu `same(x,y)` biểu thị “`x` và `y` thuộc cùng nhóm”. Quan hệ này luôn có tính **phản xạ, đối xứng và bắc cầu**. Do đó `same(0,3)` sẽ đúng sau khi ba nhóm được nối lại, dù `union(0,3)` chưa từng được gọi.

## 2. Ba phép cốt lõi cần bảo đảm điều gì?

| Phép | Tiền điều kiện | Hành vi mong đợi | Bất biến cần giữ |
|---|---|---|---|
| `make_set(x)` | `x` chưa tồn tại trong miền đã đăng ký | Tạo nhóm đơn `{x}` | `x` thuộc đúng một nhóm mới; số nhóm tăng 1 |
| `find(x)` | `x` đã được đăng ký | Trả đại diện hiện tại của nhóm chứa `x` | Hai phần tử cùng nhóm khi và chỉ khi đại diện bằng nhau |
| `union(x,y)` | `x,y` đã được đăng ký | Hợp hai nhóm chứa `x,y` nếu chúng khác nhóm | Không mất/nhân đôi phần tử; số nhóm giảm 1 **chỉ khi hợp thành công** |

Một API cũng thường cung cấp:

```text
same(x, y)           = (find(x) == find(y))
component_size(x)    = số phần tử của nhóm chứa x
component_count()    = số nhóm hiện có
```

Các phương thức phụ không thay thế ba phép cốt lõi; chúng được xây dựng trên `find`, `union` và metadata nhóm.

### Tại sao tên `find` dễ gây hiểu nhầm?

`find(x)` không tìm “một phần tử có giá trị `x`” theo nghĩa tìm kiếm trong mảng hoặc bảng băm. Nó trả về **đại diện của lớp tương đương** chứa `x`. Khi đã biết x thuộc miền, ta dùng `find` để biết x đang nằm trong **nhóm nào**.

Không được tự suy diễn rằng đại diện là phần tử nhỏ nhất, phần tử được tạo trước tiên hay một ID nhóm có ý nghĩa nghiệp vụ. Với DSU tối ưu theo kích thước/rank, đại diện có thể thay đổi sau mỗi lần hợp.

## 3. Phép `make-set(x)`: tạo một nhóm mới

`make-set(x)` đăng ký một phần tử mới và đặt nó vào nhóm chỉ chứa chính nó.

Với biểu diễn bằng con trỏ cha, một nút mới ban đầu là **gốc**:

```text
make_set(x):
    require x chưa được đăng ký
    parent[x] = x
    size[x] = 1
    componentCount += 1
```

Ví dụ đăng ký các máy `"A"`, `"B"`, `"C"`:

```text
make_set("A") → {A}
make_set("B") → {A}, {B}
make_set("C") → {A}, {B}, {C}
                  componentCount = 3
```

### Bất biến sau `make-set`

- `parent[x] == x`: x là đại diện của nhóm đơn.
- `size[x] == 1`: nhóm có đúng một phần tử.
- Những phần tử đã tồn tại không đổi nhóm.
- `componentCount` tăng đúng một.
- Nếu hàm từ chối đăng ký trùng, lần gọi lặp `make_set(x)` không tạo một nhóm thứ hai chứa x.

### Hai kiểu thiết kế API

**Khởi tạo hàng loạt cho miền đã biết trước.** Nếu phần tử có chỉ số `0..n-1`, thường dùng:

```text
parent = [0, 1, 2, ..., n-1]
size   = [1, 1, 1, ..., 1]
componentCount = n
```

Đây chính là thực hiện `make-set` cho mọi phần tử một lần. Khởi tạo mất **`O(n)` thời gian** và **`O(n)` bộ nhớ**.

**Đăng ký động theo ID bất kỳ.** Nếu ID là chuỗi hoặc những số nguyên không liên tiếp, ta có thể dùng dictionary/hash map từ ID tới cha và kích thước. Một `make_set(x)` mới thường cần **`O(1)` kỳ vọng** cho thao tác bảng băm và dung lượng hằng số trên mỗi phần tử, nhưng còn phụ thuộc cách lưu ID, hash và cấp phát.

Hai kiểu triển khai có cùng ngữ nghĩa phân hoạch; khác cách đánh chỉ số, cấp phát và xử lý phần tử chưa tồn tại.

### Nếu gọi `make-set` trên phần tử đã tồn tại?

Một hợp đồng rõ ràng phải quyết định hành vi. Hai lựa chọn phổ biến:

- **Từ chối hoặc báo lỗi** để không âm thầm phá nhóm cũ.
- **No-op** và trả `false` để báo không đăng ký phần tử mới.

Không được gán lại `parent[x] = x` một cách tùy tiện khi x đang thuộc nhóm lớn, vì hành động đó có thể làm mất liên kết của x với nhóm cũ và phá phân hoạch mà DSU đang quản lý.

Trong mã Python ở dưới, ta chọn hợp đồng: **`make_set(x)` trả `true` nếu tạo mới, `false` nếu x đã tồn tại**.

## 4. Biểu diễn bằng rừng cây cha

Một DSU thông dụng lưu mảng hoặc bảng:

```text
parent[x] = nút cha của x
```

Các phần tử của **mỗi nhóm** tạo thành một cây có gốc. Gốc tự trỏ về chính nó: `parent[root] = root`.

Ví dụ sau các phép hợp:

```text
     0                     4
   /   \                   |
  1     2                  5
        |
        3

Nhóm {0,1,2,3}          Nhóm {4,5}
```

Có thể mã hóa bằng mảng:

```text
x:          0  1  2  3  4  5
parent[x]:  0  0  0  2  4  4
```

Từ nút 3, lần lượt đi theo `3 → 2 → 0`. Vậy `find(3) = 0`. Từ nút 5, ta đi `5 → 4`, nên `find(5) = 4`.

### Bất biến cấu trúc phải giữ

1. Mọi phần tử đã đăng ký có một giá trị `parent` hợp lệ.
2. Trong mỗi cây có đúng **một gốc** với `parent[root] == root`.
3. Không có chu trình cha ngoại trừ vòng tự trỏ của gốc; đi theo cha từ bất kỳ phần tử nào sẽ tới gốc.
4. Hai phần tử thuộc cùng nhóm **khi và chỉ khi** đường cha của chúng kết thúc ở cùng gốc.
5. Những cây khác nhau không có nút chung, và hợp các nút của mọi cây bằng toàn bộ miền đã đăng ký.

Khi chỉ dùng `parent`, DSU đã có thể triển khai `find` và `union`. Mảng `size`, `rank` hoặc `componentCount` là **metadata bổ sung** để cải thiện hiệu năng và hỗ trợ truy vấn.

## 5. Phép `find(x)`: tìm đại diện của nhóm

Phiên bản đơn giản nhất:

```text
find(x):
    require x đã được đăng ký
    while parent[x] != x:
        x = parent[x]
    return x
```

Đầu ra là **gốc hiện tại** của cây chứa x.

Với:

```text
parent[0] = 0
parent[1] = 0
parent[2] = 0
parent[3] = 2
```

ta có:

```text
find(0) → 0
find(1) → 0
find(2) → 0
find(3) → 0  (đường 3 → 2 → 0)
```

Từ đây, kiểm tra cùng nhóm chỉ là:

```text
same(x, y):
    return find(x) == find(y)
```

### Độ phức tạp chưa tối ưu

Gọi `h` là độ cao cây đang chứa x. Một `find(x)` cần đi qua tối đa `h` cạnh cha, nên mất **`O(h)`**.

Nếu hợp tùy ý tạo chuỗi dài:

```text
0 → 1 → 2 → 3 → 4 → 5 → root 6
```

`find(0)` phải đi qua 6 cạnh. Trong trường hợp xấu, cây có thể cao `n-1`, khiến phép tìm là **`O(n)`**.

Cách cải thiện gồm **hợp theo kích thước/rank** (giữ cây thấp từ khi gộp) và **nén đường đi** (rút ngắn đường truy vấn khi tìm gốc).

## 6. Nén đường đi trong `find`

**Path compression** điều chỉnh cha của những nút trên đường từ x đến gốc để trỏ **trực tiếp vào gốc** sau khi tìm được gốc.

Trước và sau `find(3)`:

```text
Trước:

    0
    |
    2
    |
    3

parent[3] = 2
parent[2] = 0

Sau find(3):

    0
   / \
  2   3

parent[3] = 0
parent[2] = 0
```

Kết quả `find(3)` vẫn là 0. Các nhóm không đổi; chỉ cấu trúc con trỏ cha được rút ngắn.

### Pseudocode đệ quy

```text
find(x):
    if parent[x] != x:
        parent[x] = find(parent[x])
    return parent[x]
```

Dòng gán `parent[x] = find(parent[x])` là nơi thực hiện nén đường đi: khi lời gọi đệ quy trả về gốc, mọi nút trên đường lần lượt cập nhật con trỏ cha.

### Phiên bản lặp hai lượt

Để không phụ thuộc giới hạn ngăn xếp đệ quy, có thể tách làm hai lượt:

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

**Vì sao phải lưu `next` trước khi gán?** Nếu thay `parent[x]` bằng root trước khi ghi nhớ cha cũ, ta có thể mất đường cần đi tiếp để nén những nút còn lại.

### Một tối ưu liên quan: path halving

Thay vì nối mọi nút trực tiếp tới gốc sau hai lượt, có thể để mỗi nút trỏ tới **ông/bà** của nó trong lúc đi:

```text
find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x
```

Cách này gọi là **path halving**. Nó cũng rút ngắn nhiều đường cha nhưng không nhất thiết cho trạng thái mảng `parent` giống hoàn toàn với full path compression ngay sau một lần gọi. Khi dạy và kiểm thử, cần phân biệt **kết quả đại diện** với **chi tiết hình dạng rừng**.

### `find` có thực sự “chỉ đọc” không?

Về mặt **quan sát nhóm**, `find` chỉ trả về đại diện. Nhưng khi dùng path compression, nó có thể **ghi** vào `parent`. Vì vậy, trong môi trường nhiều luồng, không thể tự mặc định các lời gọi `find` đồng thời là an toàn chỉ vì người gọi xem nó như một truy vấn.

## 7. Phép `union(x,y)`: hợp hai nhóm

Để hợp hai nhóm, trước hết xác định **hai gốc**:

```text
union(x, y):
    rx = find(x)
    ry = find(y)

    if rx == ry:
        return false  // Đã ở cùng nhóm.

    parent[ry] = rx
    componentCount -= 1
    return true
```

Phiên bản trên có ngữ nghĩa đúng nhưng có thể sinh cây cao vì luôn gắn gốc `ry` dưới `rx` bất kể kích thước.

### Tại sao không chỉ đặt `parent[y] = x`?

Giả sử:

```text
Nhóm A: 0 ← 1 ← 2
Nhóm B: 3 ← 4

parent[0] = 0
parent[1] = 0
parent[2] = 1

parent[3] = 3
parent[4] = 3
```

Nếu muốn gộp nhóm chứa 2 với nhóm chứa 4 mà chỉ viết `parent[4] = 2`:

- Nút 4 được chuyển vào cây của 0.
- Nhưng nút 3 **vẫn là gốc của một nhóm khác**, dù đáng lẽ toàn bộ nhóm `{3,4}` phải được hợp.
- Dữ liệu logic không còn phản ánh đúng phép hợp toàn nhóm.

Cách đúng là lấy `rx = find(2) = 0`, `ry = find(4) = 3` rồi gắn **một gốc** dưới gốc kia, chẳng hạn `parent[3] = 0`.

Nếu không kiểm tra hai gốc có trùng nhau, còn có thể vô tình tạo chu trình cha khi nối nút trong cùng cây. Vì vậy **`rx != ry` là điều kiện quan trọng trước khi sửa con trỏ**.

### Kết quả trả về và tính lũy đẳng

Một giao diện hữu ích là:

- `union(x,y)` trả `true` khi hợp **hai nhóm khác nhau**.
- Trả `false` khi `find(x) == find(y)`; không giảm số nhóm.
- Các tham số ngoài miền gây lỗi rõ ràng, không trả `false` như thể hai nhóm vốn đã cùng nhau.

Gọi `union(x,y)` hai lần liên tiếp không làm thay đổi phân hoạch sau lần đầu. Tính chất này tương tự **lũy đẳng** về mặt phân hoạch.

Chú ý: `union(x,y)` và `union(y,x)` tạo cùng **phân hoạch logic**, nhưng có thể tạo **gốc đại diện và hình dạng cây khác nhau** nếu thuật toán giải quyết các trường hợp bằng nhau theo thứ tự tham số.

## 8. Union by size: gắn cây nhỏ dưới cây lớn

Để giảm chiều cao cây, lưu `size[root]`: số phần tử của nhóm có gốc `root`. Khi hai nhóm khác nhau được hợp:

```text
union(x, y):
    rx = find(x)
    ry = find(y)

    if rx == ry:
        return false

    if size[rx] < size[ry]:
        swap(rx, ry)

    parent[ry] = rx
    size[rx] = size[rx] + size[ry]
    componentCount -= 1
    return true
```

Với điều kiện `size[rx] ≥ size[ry]`, ta gắn gốc nhóm nhỏ vào gốc nhóm lớn.

### Ví dụ

```text
Nhóm A: {0,1,2,3}, gốc 0, size[0] = 4
Nhóm B: {4,5},     gốc 4, size[4] = 2

union(3,5):
    rx = find(3) = 0
    ry = find(5) = 4
    size[0] >= size[4]
    parent[4] = 0
    size[0] = 6
```

Sau hợp, các phần tử 4 và 5 cùng thuộc nhóm gốc 0. Nếu vẫn giữ `size[4] = 2` như giá trị cũ, **không được dùng `size[4]` để hỏi kích thước nhóm** vì 4 không còn là gốc. Phải đọc:

```text
component_size(x) = size[find(x)]
```

### Vì sao giữ cây không quá cao?

Khi một cây có kích thước `a` bị gắn dưới cây kích thước `b≥a`, mọi nút ở cây nhỏ có thể tăng độ sâu 1. Nhưng nhóm mới chứa mỗi nút đó có kích thước ít nhất `a+b≥2a`.

Do kích thước nhóm không vượt tổng số phần tử `n`, một nút không thể trải qua quá `⌊log₂ n⌋` lần tăng độ sâu vì được gắn dưới cây có kích thước lớn hơn hoặc bằng. Vì vậy, **union by size không dùng nén đường đi vẫn bảo đảm độ cao `O(log n)`**.

### Union by rank có giống union by size không?

Cả hai cùng tránh cây quá sâu nhưng dùng metadata khác nhau:

- **Union by size:** so sánh số thành viên của hai nhóm; có thể trả lời trực tiếp `component_size(x)` tại gốc.
- **Union by rank:** so sánh một chặn/ước lượng độ cao gọi là `rank`. Nếu hai rank bằng nhau, tăng rank của gốc mới.

Sau path compression, `rank` **không nhất thiết là chiều cao thực tế hiện tại**. Không được xem `rank` như kích thước nhóm.

Bài này dùng **union by size** vì nó vừa dễ minh họa vừa phục vụ truy vấn kích thước nhóm.

## 9. Mô phỏng chính xác từng thay đổi của `parent` và `size`

Khởi tạo 6 phần tử `0..5`:

```text
parent = [0, 1, 2, 3, 4, 5]
size   = [1, 1, 1, 1, 1, 1]
componentCount = 6
```

Thực hiện lần lượt các thao tác sau, dùng **union by size**; khi hai nhóm bằng nhau, chọn gốc của đối số đầu sau khi gọi `find`.

| Bước | Thao tác | Mảng `parent` sau bước | Số nhóm |
|---:|---|---|---:|
| 0 | Khởi tạo | `[0,1,2,3,4,5]` | 6 |
| 1 | `union(0,1)` | `[0,0,2,3,4,5]` | 5 |
| 2 | `union(2,3)` | `[0,0,2,2,4,5]` | 4 |
| 3 | `union(1,2)` | `[0,0,0,2,4,5]` | 3 |
| 4 | `find(3)` với full compression | `[0,0,0,0,4,5]` | 3 |
| 5 | `union(4,5)` | `[0,0,0,0,4,4]` | 2 |
| 6 | `union(3,5)` | `[0,0,0,0,0,4]` | 1 |
| 7 | `find(5)` với full compression | `[0,0,0,0,0,0]` | 1 |

**Diễn giải bước 3:** `find(1)=0` và `find(2)=2`. Hai nhóm đều có kích thước 2, ta giữ gốc 0, gắn `parent[2]=0` và cập nhật `size[0]=4`. Nút 3 vẫn trỏ tới 2 cho đến khi thực hiện `find(3)`.

**Diễn giải bước 6:** `find(3)=0`, `find(5)=4`. Nhóm gốc 0 có 4 phần tử, nhóm gốc 4 có 2 phần tử; gắn `parent[4]=0`, cập nhật `size[0]=6`. Nút 5 vẫn trỏ tới 4. Sau `find(5)`, con trỏ của nó được nén trực tiếp về 0.

### Truy vấn trong từng bước

- Sau bước 2: `same(0,3) == false`.
- Sau bước 3: `same(0,3) == true`.
- Sau bước 4: `component_size(3) == 4`.
- Sau bước 5: `component_count == 2`.
- Sau bước 7: `same(1,5) == true` và `component_size(5) == 6`.
- Nếu gọi tiếp `union(1,5)`, kết quả trả về `false` vì hai phần tử đã cùng nhóm; số nhóm vẫn bằng 1.

Bảng chỉ mô tả **một quy tắc chọn gốc cụ thể**. Nếu đổi thứ tự đối số hoặc thay chiến lược union, mảng `parent` có thể khác nhưng các kết quả về **cùng nhóm, kích thước và số nhóm** phải giống nhau.

## 10. Triển khai Python: `make-set` động theo ID bất kỳ

Trong thực tế, ID có thể là chuỗi `"A"`, `"B"` hoặc số nguyên không liên tiếp. Ta xây một DSU động dùng hai dictionary:

- `parent[x]` lưu cha của phần tử x.
- `size[r]` lưu số thành viên của nhóm có gốc r.
- `component_count` đếm số nhóm.

Hợp đồng được xác định rõ:

- `make_set(x)` trả `true` khi tạo phần tử mới, `false` nếu phần tử đã tồn tại.
- `find(x)` gây `KeyError` nếu x chưa được đăng ký.
- `union(x,y)` trả `true` nếu gộp hai nhóm khác nhau; `false` nếu đã cùng nhóm.
- `same(x,y)` và `component_size(x)` yêu cầu các ID tồn tại.
- ID phải là **khóa hashable ổn định** trong thời gian nằm trong các dictionary.

```python
class DisjointSetUnion:
    def __init__(self):
        self.parent = {}
        self.size = {}
        self.component_count = 0

    def make_set(self, x):
        if x in self.parent:
            return False

        self.parent[x] = x
        self.size[x] = 1
        self.component_count += 1
        return True

    def find(self, x):
        if x not in self.parent:
            raise KeyError(f"Phần tử chưa đăng ký: {x!r}")

        # Lượt 1: tìm gốc hiện tại.
        root = x
        while self.parent[root] != root:
            root = self.parent[root]

        # Lượt 2: nén các nút trên đường về gốc.
        while self.parent[x] != x:
            next_x = self.parent[x]
            self.parent[x] = root
            x = next_x

        return root

    def union(self, x, y):
        rx = self.find(x)
        ry = self.find(y)

        if rx == ry:
            return False

        # rx là gốc của nhóm lớn hơn hoặc bằng.
        if self.size[rx] < self.size[ry]:
            rx, ry = ry, rx

        self.parent[ry] = rx
        self.size[rx] += self.size[ry]
        self.component_count -= 1
        return True

    def same(self, x, y):
        return self.find(x) == self.find(y)

    def component_size(self, x):
        return self.size[self.find(x)]

    def groups(self):
        # Chỉ dựng danh sách thành viên khi có yêu cầu.
        result = {}
        for x in self.parent:
            root = self.find(x)
            result.setdefault(root, []).append(x)
        return list(result.values())


dsu = DisjointSetUnion()

for identifier in ("A", "B", "C", "D", "E", "F"):
    assert dsu.make_set(identifier)

assert dsu.component_count == 6
assert dsu.make_set("A") is False  # Không tạo trùng.
assert dsu.component_count == 6

assert dsu.union("A", "B") is True
assert dsu.union("C", "D") is True
assert dsu.union("B", "C") is True

assert dsu.same("A", "D") is True
assert dsu.same("A", "E") is False
assert dsu.component_size("D") == 4

assert dsu.union("A", "D") is False  # Không hợp trùng.

assert dsu.union("E", "F") is True
assert dsu.component_count == 2

assert dsu.union("D", "E") is True
assert dsu.component_count == 1
assert dsu.component_size("F") == 6

print(dsu.groups())  # Một nhóm chứa A, B, C, D, E, F.
```

### Vì sao `groups()` không tự động là thao tác nhanh?

DSU chỉ đảm bảo đường dẫn **từ phần tử tới gốc**; nó không bắt buộc lưu danh sách con hoặc danh sách thành viên cho mỗi gốc. Để tạo danh sách các nhóm, `groups()` ở trên duyệt qua **toàn bộ `n` phần tử**, gọi `find` cho mỗi phần tử và gom vào dictionary.

Do đó thao tác này cần ít nhất `Ω(n)` thời gian để xuất đủ phần tử. Với một chuỗi thao tác có nén đường đi và union by size, có thể ước lượng gần `O(nα(n))` khi bao gồm các lần tìm, cộng chi phí tạo đầu ra và bảng băm. Bộ nhớ phụ để trả kết quả là **`O(n)`**.

Nếu bài toán liên tục yêu cầu “liệt kê mọi thành viên của nhóm X”, có thể phải duy trì thêm danh sách thành viên hoặc cân nhắc một cấu trúc khác.

### Phần tử chưa đăng ký không được tự coi là một nhóm ngầm định

`find("Z")` sẽ báo `KeyError` vì `"Z"` chưa từng được `make_set`. Một số API tự đăng ký khi truy vấn, nhưng cách đó có thể gây thay đổi trạng thái bất ngờ. Trong mã này, chỉ `make_set` làm thay đổi miền phần tử; các phương thức khác kiểm tra tồn tại và không tạo ID mới.

## 11. Triển khai C++ cho miền chỉ số liên tục

Khi phần tử là các chỉ số `0..n-1`, hai mảng `parent` và `size` liên tiếp trong bộ nhớ thường đơn giản và gọn hơn bảng băm. Ví dụ C++17:

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
        : parent_(n), size_(n, 1), components_(n) {
        std::iota(parent_.begin(), parent_.end(), std::size_t{0});
    }

    std::size_t find(std::size_t x) {
        if (x >= parent_.size()) {
            throw std::out_of_range("Invalid DSU index");
        }

        // Path halving: đưa nút lên cha của cha.
        while (parent_[x] != x) {
            parent_[x] = parent_[parent_[x]];
            x = parent_[x];
        }
        return x;
    }

    bool unite(std::size_t x, std::size_t y) {
        x = find(x);
        y = find(y);
        if (x == y) return false;

        if (size_[x] < size_[y]) std::swap(x, y);

        parent_[y] = x;
        size_[x] += size_[y];
        --components_;
        return true;
    }

    bool same(std::size_t x, std::size_t y) {
        return find(x) == find(y);
    }

    std::size_t component_size(std::size_t x) {
        return size_[find(x)];
    }

    std::size_t component_count() const {
        return components_;
    }

private:
    std::vector<std::size_t> parent_;
    std::vector<std::size_t> size_;
    std::size_t components_;
};

int main() {
    DSU dsu(6);               // Tương đương make_set cho 0..5.
    dsu.unite(0, 1);
    dsu.unite(2, 3);
    dsu.unite(1, 2);

    std::cout << dsu.same(0, 3) << '\n'; // 1
    std::cout << dsu.component_size(3) << '\n'; // 4
    std::cout << dsu.component_count() << '\n'; // 3

    std::cout << dsu.unite(0, 3) << '\n'; // 0: đã cùng nhóm
}
```

Các tính chất quan trọng của ví dụ:

- Constructor là dạng **make-set hàng loạt** cho toàn miền.
- `find` kiểm tra giới hạn, nên chỉ số sai không làm đọc mảng ngoài biên.
- `find` dùng **path halving**, khác chi tiết cách nén với Python nhưng trả cùng đại diện đúng.
- `unite` chỉ giảm `components_` sau khi xác định hai gốc khác nhau.
- `size_` là metadata của **gốc**; `component_size` luôn gọi `find` trước.

Đoạn mã được viết như một ví dụ thuật toán; lựa chọn `std::size_t`, xử lý ngoại lệ và chính sách kiểm tra biên là một phần hợp đồng của API cụ thể.

## 12. Độ phức tạp thời gian và bộ nhớ

Đặt:

- `n` là số phần tử đang được quản lý.
- `m` là số lần gọi `find`/`union`/`same` trong một chuỗi thao tác.
- `h` là chiều cao của cây hiện tại.
- `α(n)` là hàm **Ackermann ngược**, tăng cực kỳ chậm.

| Cách triển khai | `make-set` | `find` | `union` | Bộ nhớ |
|---|---|---|---|---|
| Mảng nhãn nhóm, hợp bằng quét toàn bộ | `O(1)` cho một phần tử mới nếu hỗ trợ cấp phát tương ứng | `O(1)` đọc nhãn | `O(n)` cho mỗi lần hợp khác nhóm | `O(n)` |
| Quick-union gắn gốc tùy ý | `O(1)` cho phần tử mới đã có chỗ | `O(h)`, xấu nhất `O(n)` | Hai lần find, xấu nhất `O(n)` | `O(n)` |
| Union by size, chưa nén đường đi | `O(1)` cho phần tử mới đã có chỗ | `O(log n)` xấu nhất | `O(log n)` xấu nhất | `O(n)` |
| Union by size + path compression | `O(1)` cho phần tử mới đã có chỗ | `O(α(n))` **khấu hao** theo chuỗi thao tác | `O(α(n))` **khấu hao** theo chuỗi thao tác | `O(n)` |

**Giải thích điều kiện:** nếu dùng mảng kích thước cố định đã khởi tạo hết, `make-set` cho phần tử mới không còn ý nghĩa ở mức runtime: constructor thực hiện toàn bộ trong `O(n)`. Nếu dùng mảng động hoặc dictionary, thêm phần tử có thể tốn cấp phát hoặc rehash; giá trị `O(1)` ở bảng là chi phí kỳ vọng/khấu hao dưới những giả định thông thường.

### Không nhầm “gần hằng số khấu hao” với “hằng số tuyệt đối”

Đối với DSU có **union by size/rank và path compression**, kết quả kinh điển thường viết tổng công cho chuỗi thao tác là cỡ:

\[
O\bigl((n+m)\,\alpha(n+m)\bigr)
\]

trong một cách phát biểu đơn giản cho khởi tạo và `m` thao tác, với `α` tăng rất chậm. Có những công thức chính xác hơn tùy số lượng thao tác và mô hình phân tích.

Điều này **không** khẳng định một lần `find` riêng lẻ luôn `O(1)` trong trường hợp xấu. Trên một cây có độ cao `O(log n)` nhờ union by size, một lần tìm gốc vẫn có thể đi qua `O(log n)` cạnh trước khi nén đường đi, nhưng tổng chi phí của nhiều lần tìm/hợp được trải đều rất tốt.

### Truy vấn thành phần không có sẵn trong DSU gốc

- `component_count()` là **`O(1)`** nếu lưu biến đếm và cập nhật đúng.
- `component_size(x)` là một `find` cộng một lần đọc metadata, nên có cùng bậc chi phí với `find`.
- Liệt kê **mọi thành viên** của nhóm có thể cần quét qua tất cả phần tử `O(n)` nếu không lưu chỉ mục phụ.
- Số thành viên của mỗi nhóm không tự động bằng số con trực tiếp trong rừng cha; cần `size[root]` nếu muốn đọc nhanh.

## 13. Chứng minh tính đúng đắn của `make-set`, `find` và `union`

Một lập luận chuẩn dùng quy nạp theo số thao tác thay đổi phân hoạch.

### Bước cơ sở

Ban đầu chưa có phần tử thì phân hoạch rỗng là hợp lệ. Mỗi `make_set(x)` hợp lệ thêm đúng một cây đơn `{x}`, không giao với các cây đang có vì x chưa tồn tại. Do đó vẫn là một phân hoạch.

### Bất biến của `find`

Giả sử rừng đang hợp lệ. Đi theo `parent` từ x sẽ tới đúng một gốc của cây chứa x. Do mọi nút trong cùng cây có cùng gốc, `find(x)` trả đại diện của nhóm chứa x.

Path compression thay cha của các nút **trong cùng cây** thành gốc hiện tại; do đó không làm thay đổi tập thành viên, chỉ thay đường đi. Bất biến tiếp tục đúng.

### Bước `union` khi hai gốc bằng nhau

Nếu `rx == ry`, x và y đã thuộc cùng cây. Thuật toán **không nối thêm cạnh cha**; số nhóm và kích thước không đổi. Phân hoạch giữ nguyên.

### Bước `union` khi hai gốc khác nhau

Nếu `rx != ry`, hai cây hiện tại không có nút chung. Nối gốc `ry` dưới gốc `rx`:

- Không làm mất nút nào.
- Không tạo chu trình vì hai cây trước đó khác nhau.
- Hợp toàn bộ thành viên của hai cây thành đúng một cây mới.
- Giảm số nhóm đi một.
- Kích thước gốc mới bằng tổng kích thước hai nhóm.

Các cây còn lại không đổi. Vậy bất biến phân hoạch được duy trì sau mỗi phép hợp.

### Ba kiểm tra bất biến hữu ích

Nếu các gốc hiện tại là `r₁,...,r_c` thì:

\[
\sum_{j=1}^{c} \mathrm{size}[r_j] = n.
\]

Đồng thời:

\[
\mathrm{componentCount}=c,
\qquad
\mathrm{parent}[r_j]=r_j.
\]

Các đại lượng này giúp phát hiện lỗi như:

- Giảm số nhóm dù hai phần tử đã cùng gốc.
- Cộng kích thước nhóm hai lần.
- Gán cha ở một nút không phải gốc, khiến cây không phản ánh phép hợp toàn nhóm.

Trong một bài kiểm thử nhỏ, có thể dựng lại các nhóm theo kết quả `find` của từng phần tử rồi đối chiếu số lượng thành viên với `size[root]`.

## 14. Ứng dụng: theo dõi thành phần liên thông khi thêm cạnh

Trong đồ thị **vô hướng**, các đỉnh thuộc cùng thành phần liên thông khi có đường đi giữa chúng. Có thể:

1. Tạo `make_set(v)` cho từng đỉnh.
2. Với mỗi cạnh được thêm `(u,v)`, gọi `union(u,v)`.
3. Trả lời “u và v có liên thông?” bằng `find(u) == find(v)`.

```text
Đỉnh: A, B, C, D, E

Khởi tạo:
{A}, {B}, {C}, {D}, {E}

Thêm cạnh A-B:
{A,B}, {C}, {D}, {E}

Thêm cạnh C-D:
{A,B}, {C,D}, {E}

Thêm cạnh B-C:
{A,B,C,D}, {E}
```

`same(A,D)` đúng sau cạnh B-C; `same(A,E)` vẫn sai.

### Điểm DSU không trả lời

DSU chỉ lưu **trạng thái phân hoạch**. Nó không biết:

- Cạnh trực tiếp nào nối hai đỉnh.
- Đường đi cụ thể từ A tới D.
- Trọng số nhỏ nhất hoặc số cạnh trên đường đi.
- Các thành phần sẽ thế nào nếu **xóa** một cạnh.

Muốn tìm đường đi có thể dùng BFS/DFS trên cấu trúc đồ thị. Muốn xử lý xóa cạnh trực tuyến thường cần cấu trúc liên thông động phức tạp hơn. Không nên dùng DSU để biểu diễn nhóm có thành viên **chồng lấn** hoặc quan hệ có hướng không phải tương đương.

### Phát hiện cạnh tạo chu trình khi xây rừng

Khi đang xây một rừng từ những cạnh đã chấp nhận:

```text
if find(u) == find(v):
    bỏ qua cạnh  // Nối hai đỉnh đã có đường đi sẽ tạo chu trình.
else:
    chấp nhận cạnh
    union(u, v)
```

Đây là thao tác Union–Find trong thuật toán **Kruskal** để tìm cây khung nhỏ nhất: thuật toán duyệt cạnh theo trọng số rồi chỉ chấp nhận cạnh nối **hai thành phần khác nhau**.

Phần DSU xử lý mỗi cạnh bằng một số nhỏ phép `find`/`union`, nhưng tổng độ phức tạp Kruskal còn phải tính thời gian **sắp xếp cạnh**.

## 15. Những lỗi triển khai thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| `make_set(x)` ghi đè phần tử đã tồn tại | Có thể cắt x khỏi nhóm cũ hoặc làm sai metadata | Kiểm tra trùng; trả false hoặc báo lỗi |
| Gọi `find(x)` trên phần tử chưa đăng ký | Không có chuỗi cha hợp lệ để lần theo | Kiểm tra miền, báo lỗi rõ ràng |
| Gán `parent[y] = x` với hai nút tùy ý | Chỉ nối một nút, không đảm bảo hợp hai **nhóm** | Luôn tìm và nối **hai gốc** |
| Không kiểm tra `rx == ry` trước `union` | Gộp trùng, cập nhật sai size/count, có thể tạo chu trình | Trả false và không nối |
| Dùng `size[x]` khi x không phải gốc | Giá trị có thể là metadata cũ | Đọc `size[find(x)]` |
| Coi root là ID nhóm ổn định | Union by size có thể đổi đại diện | Lưu ID nghiệp vụ riêng |
| Trả `false` cho cả “đã cùng nhóm” và “ID sai” | Người gọi không phân biệt trạng thái và lỗi | Thiết kế hợp đồng lỗi riêng |
| Dùng đệ quy find trên cây dài mà không kiểm soát | Có thể vượt giới hạn stack ở một số môi trường | Dùng phiên bản lặp hoặc bảo đảm chiều cao |
| Tưởng path compression không ghi dữ liệu | `find` có thể sửa nhiều `parent` | Đồng bộ truy cập đa luồng |
| Chỉ đếm số lần gọi union để suy số nhóm | Union trùng không làm giảm số nhóm | Chỉ trừ khi nối hai gốc khác nhau |
| Coi `rank` là số thành viên | Rank không phải size; đặc biệt sai sau nén đường đi | Tách metadata `rank` và `size` |
| Cần split/undo mà dùng DSU chuẩn | DSU chuẩn chỉ hợp, không có phép chia nhóm | Chọn bài toán rollback/dynamic connectivity phù hợp |

### Ghi chú về đồng thời

Trong những môi trường có nhiều luồng, ngay cả `find` đã nén đường đi cũng có thể ghi vào `parent`. Các lời gọi `union` đồng thời trên cùng vùng dữ liệu có thể tạo cạnh cha không nhất quán nếu thiếu đồng bộ. Hãy dùng khóa hoặc thuật toán concurrent Union–Find được thiết kế đúng; không mặc định mã đơn luồng trong các ví dụ tự an toàn đa luồng.

## 16. Chọn kiểu hiện thực nào theo bài toán?

| Nhu cầu | Cách nên cân nhắc | Lý do |
|---|---|---|
| `n` biết trước, ID liên tục `0..n-1` | Mảng `parent`, `size` | Bộ nhớ liên tiếp, `O(n)`, thao tác đơn giản |
| ID là chuỗi hoặc số nguyên thưa, thêm động | Hash map `parent`/`size` | Không cần cấp phát theo ID lớn nhất |
| Nhiều lần hợp và kiểm tra cùng nhóm | Union by size + path compression | Thời gian rất nhỏ theo khấu hao |
| Cần kích thước nhóm | Lưu `size[root]` | Đọc sau `find` |
| Cần số nhóm hiện tại | Lưu `componentCount` | Trả `O(1)` |
| Cần liệt kê nhóm thường xuyên | Chỉ mục thành viên bổ sung hoặc cấu trúc khác | DSU chuẩn không duy trì sẵn danh sách thành viên |
| Cần xóa/tách nhóm | Thuật toán liên thông động/rollback theo yêu cầu | DSU kinh điển không hỗ trợ trực tiếp |
| Cần ID đại diện bền vững | Metadata định danh nghiệp vụ riêng | Gốc kỹ thuật có thể thay đổi |

Một nguyên tắc có ích: chọn **hợp đồng của các phép toán** trước khi quyết định mảng hay bảng băm. Mảng và dictionary có thể lưu cùng một mô hình DSU, nhưng chúng có chi phí và điều kiện tiên quyết khác nhau.

## 17. Bài tập tự kiểm tra có lời giải

**Câu 1.** Với `U={0,1,2,3}`, sau khi `make_set` cho cả bốn phần tử, `componentCount` bằng bao nhiêu? `find(2)` trả giá trị nào?

**Đáp án:** Có 4 nhóm đơn, nên `componentCount=4`; ban đầu `parent[2]=2`, vậy `find(2)=2`.

**Câu 2.** Sau `union(0,1)` và `union(2,3)`, gọi `union(1,2)` thì những phần tử nào cùng nhóm?

**Đáp án:** Tất cả `{0,1,2,3}` cùng nhóm vì phép hợp nối **cả hai nhóm**. Số nhóm giảm từ 2 xuống 1.

**Câu 3.** `union(0,3)` sau câu 2 có phải một phép hợp thành công không? Vì sao?

**Đáp án:** Không. Hai phần tử đã có cùng gốc, nên phép hợp không thay đổi phân hoạch và không giảm `componentCount`.

**Câu 4.** Vì sao `make_set(x)` cần kiểm tra `x` đã có trong miền chưa?

**Đáp án:** Nếu ghi đè `parent[x]=x` khi x đã thuộc một nhóm, có thể phá liên kết nhóm cũ hoặc metadata. Phần tử chỉ được tạo nhóm đơn **một lần** theo hợp đồng đăng ký.

**Câu 5.** Cho `parent=[0,0,0,2,4,4]`. `find(3)` trả gì? Sau full path compression, `parent[3]` bằng gì?

**Đáp án:** Đường `3→2→0` cho gốc 0. Sau nén đầy đủ, `parent[3]=0`.

**Câu 6.** Hai nhóm có kích thước 4 và 2 được union by size. Gốc của nhóm nào thường giữ vai trò đại diện sau hợp?

**Đáp án:** Gốc của nhóm kích thước 4 được giữ, gốc của nhóm kích thước 2 nối dưới nó. Kích thước nhóm mới là 6. Khi hai kích thước bằng nhau, chính sách chọn gốc có thể phụ thuộc triển khai.

**Câu 7.** Tại sao `size[x]` không nhất thiết đúng khi `x` là một nút không phải gốc?

**Đáp án:** Metadata `size` có thể chỉ cập nhật ở gốc của nhóm sau mỗi lần hợp. Phải dùng `size[find(x)]` để lấy số thành viên hiện tại.

**Câu 8.** DSU có `n` phần tử, ban đầu `n` nhóm; sau một chuỗi thao tác có `s` lần nối hai **gốc khác nhau**. Có bao nhiêu nhóm?

**Đáp án:** `n-s` nhóm (khi chưa thêm phần tử mới trong thời gian đó), vì mỗi phép hợp thành công giảm đúng 1 nhóm.

**Câu 9.** Nếu không có union by size/rank, cây cha có thể cao đến mức nào và `find` có chi phí xấu nhất nào?

**Đáp án:** Cây có thể cao `Θ(n)` nếu nối gốc tùy ý thành một chuỗi; `find` xấu nhất `O(n)`.

**Câu 10.** Union by size không có path compression cho `find` chặn trên bao nhiêu?

**Đáp án:** `O(log n)` trong trường hợp xấu nhờ nhóm chứa một nút ít nhất tăng gấp đôi khi độ sâu của nút đó tăng.

**Câu 11.** Vì sao có thể nói union by size kết hợp path compression “gần `O(1)` khấu hao” nhưng không được nói mọi lần `find` đều `O(1)` worst-case?

**Đáp án:** Chặn rất tốt dựa trên tổng công của **chuỗi thao tác** với hàm Ackermann ngược. Một lần tìm riêng có thể đi qua nhiều cạnh trước khi rút ngắn đường; `α(n)` không phải hằng số toán học tuyệt đối.

**Câu 12.** Với các ID `"A"` và `"B"`, tại sao dùng dictionary DSU có thể thuận lợi hơn lấy trực tiếp ID làm chỉ số mảng?

**Đáp án:** ID dạng chuỗi không phải chỉ số nguyên liên tục. Dictionary lưu ánh xạ cha theo khóa và thêm động mà không cần tạo một mảng khổng lồ hay tự thay ID bằng chỉ số.

**Câu 13.** Trong đồ thị vô hướng, nếu hai đỉnh đã cùng thành phần liên thông, thêm một cạnh trực tiếp giữa chúng có làm thay đổi kết quả `same` không?

**Đáp án:** Không. Phân hoạch thành phần liên thông giữ nguyên; gọi union trên hai đầu cạnh đã cùng gốc là no-op. Nếu xây rừng, cạnh đó sẽ tạo chu trình nên không được chọn vào rừng.

**Câu 14.** Có thể dùng DSU chuẩn để xóa liên kết khiến một nhóm tách thành hai nhóm không?

**Đáp án:** Không trực tiếp. DSU chuẩn hỗ trợ hợp nhóm và truy vấn đại diện, không có thao tác split. Cần dựng lại từ những liên kết còn lại hoặc chọn thuật toán dynamic connectivity/rollback thích hợp.

## Ghi nhớ

- **`make-set(x)`** tạo nhóm đơn cho phần tử mới; **`find(x)`** trả đại diện của nhóm; **`union(x,y)`** hợp **hai nhóm chứa x và y**, không chỉ nối hai nút.
- Trong DSU dạng rừng cha, **mỗi nhóm là một cây có gốc tự trỏ**, và hai phần tử cùng nhóm khi và chỉ khi `find` của chúng bằng nhau. Luôn nối **gốc với gốc** sau khi kiểm tra khác nhau.
- **Union by size** gắn nhóm nhỏ dưới nhóm lớn, duy trì `size` tại **gốc**; **path compression** rút ngắn đường tìm đại diện mà không đổi nhóm logic.
- Một phép `union` chỉ làm giảm số nhóm **khi hai đại diện khác nhau**. `make-set` trùng, `union` trùng và ID không hợp lệ phải có hợp đồng xử lý rõ ràng.
- Với mảng chỉ số liên tục, DSU dùng `O(n)` bộ nhớ; với ID rời rạc có thể dùng bảng băm. Kết hợp union by size/rank và path compression đem lại **chi phí gần hằng số khấu hao** trên chuỗi thao tác.
- DSU phù hợp với **gộp dần nhóm, kiểm tra liên thông và phát hiện cạnh tạo chu trình**; không tự giải quyết **xóa/tách nhóm, truy vấn đường đi, liệt kê sẵn thành viên hoặc đồng thời không đồng bộ**.

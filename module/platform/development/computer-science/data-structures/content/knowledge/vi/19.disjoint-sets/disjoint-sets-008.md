# Phân biệt hạng với chiều cao thực sau khi nén đường đi

Giả sử một **Disjoint Set Union (DSU)** đã hợp tám phần tử thành một nhóm. Gốc có `rank = 3`. Sau một vài lần gọi `find` có **nén đường đi (path compression)**, mọi phần tử có thể trỏ trực tiếp tới gốc; chiều cao cây còn đúng **1 cạnh**, nhưng `rank` của gốc vẫn là **3**.

Điều này có phải lỗi? **Không.** Trong Union–Find dùng **union by rank** và path compression, **hạng (rank) là metadata lịch sử dùng làm chặn trên cho chiều cao**, không nhất thiết bằng chiều cao thực tế của cây ở thời điểm đang xét. Nếu tùy ý giảm rank mỗi lần đường cha được rút ngắn, ta có thể phá các bất biến làm nền tảng cho thuật toán.

Bài này thuộc chương **Tập hợp rời nhau** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Học phần cung cấp nền tảng cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; nhấn mạnh **bất biến, thao tác và độ phức tạp thời gian/bộ nhớ** để chọn cấu trúc phù hợp. Trọng tâm của bài là phân biệt ba đại lượng **rank**, **chiều cao thực** và **kích thước nhóm** trong rừng cha, đặc biệt trước và sau nén đường đi.

## 1. Mục tiêu và các khái niệm cần phân biệt

Sau khi học, bạn cần:

1. Tính được **độ sâu nút** và **chiều cao cây** từ mảng `parent`.
2. Giải thích cách **union by rank** khởi tạo và thay đổi `rank`.
3. Phân biệt thời điểm `rank[root]` **bằng** chiều cao thật và thời điểm nó chỉ còn là **chặn trên**.
4. Truy vết thay đổi mảng cha trong **full path compression**, **path halving** và **path splitting**.
5. Chứng minh các bất biến: rank trên đường cha tăng nghiêm ngặt, `rank[root]≤⌊log₂ n⌋` và kích thước nhóm tối thiểu là `2^{rank[root]}`.
6. Hiểu vì sao giảm rank theo chiều cao hiện tại là cách sửa **không thuộc thuật toán chuẩn**.
7. Cài đặt, đo và kiểm tra DSU bằng Python/C++ mà không nhầm metadata với hình dạng cây.
8. Đọc chính xác chặn **`O(log n)` worst-case một lần tìm** và **`O(α(n))` khấu hao** trên chuỗi thao tác.

Ta sẽ dùng miền có chỉ số liên tục:

\[
U=\{0,1,\ldots,n-1\}.
\]

Mỗi nhóm của DSU là một cây trong rừng cha. Mỗi gốc `r` tự trỏ `parent[r]=r`, và các phần tử thuộc cùng nhóm khi có cùng gốc.

## 2. Ba đại lượng: size, height và rank

Đây là ba đại lượng có liên quan, nhưng **không đồng nghĩa**.

| Đại lượng | Ký hiệu | Định nghĩa hoặc ý nghĩa |
|---|---|---|
| **Kích thước nhóm** | `size[root]` | **Số phần tử thực** trong cây có gốc `root` |
| **Độ sâu nút** | `depth(x)` | Số cạnh từ x đi theo cha tới gốc |
| **Chiều cao thực của cây** | `height(root)` | Độ sâu lớn nhất trong các nút thuộc cây |
| **Hạng** | `rank[root]` | Giá trị được duy trì theo **quy tắc union by rank** để kiểm soát chiều cao |

Ví dụ:

```text
        0
       / \
      1   2
          |
          3
```

Trong cây trên:

- `depth(0)=0`.
- `depth(1)=1`.
- `depth(2)=1`.
- `depth(3)=2`.
- `height(0)=2`.
- `size[0]=4` nếu dùng metadata kích thước.

Nếu cây được tạo bằng **union by rank không có nén đường đi**, gốc có thể có `rank[0]=2`; lúc đó rank **bằng** height.

Nếu `find(3)` nén đường và sửa `parent[3]=0`, chiều cao giảm xuống 1, còn rank có thể vẫn bằng 2.

### Quy ước đếm chiều cao

Trong bài này, chiều cao được đo bằng **số cạnh** trên đường dài nhất từ một nút đến gốc:

- Cây chỉ có một nút: chiều cao **0**.
- Cây hình sao với ít nhất hai nút: chiều cao **1**.
- Chuỗi gồm bốn nút: chiều cao **3**.

Một số tài liệu tính chiều cao bằng số nút/tầng. Nếu dùng quy ước ấy, số cụ thể chênh một đơn vị. Cần nêu quy ước trước khi so sánh rank với height; thuật toán union by rank bên dưới khởi tạo rank của nút đơn bằng **0**.

## 3. Rừng cha là trạng thái logic, hình dạng cây là chi tiết cài đặt

DSU duy trì một **phân hoạch**: các nhóm không giao nhau và bao phủ toàn bộ tập phần tử. Mảng `parent` lưu cạnh cha của từng phần tử.

Ví dụ:

```text
x:          0 1 2 3
parent[x]:  0 0 1 2

Cây:
3 → 2 → 1 → 0 (gốc)
```

Ta có:

```text
find(0) = 0
find(1) = 0
find(2) = 0
find(3) = 0
```

Một cách lưu khác:

```text
parent = [0,0,0,0]

Cây:
  1 ─┐
  2 ─┼→ 0 (gốc)
  3 ─┘
```

Hai mảng trên biểu diễn **cùng một nhóm** `{0,1,2,3}`, nhưng chiều cao lần lượt là **3** và **1**.

### Bất biến rừng bắt buộc

1. `parent[x]` là một chỉ số hợp lệ.
2. Mỗi cây có đúng một gốc tự trỏ.
3. Không có chu trình cha gồm từ hai nút trở lên.
4. Đi theo cha từ mọi phần tử sẽ tới một gốc.
5. Hai phần tử cùng nhóm **khi và chỉ khi** có chung gốc.
6. Các cây khác nhau không chia sẻ nút.

**Nén đường đi chỉ thay hình dạng cây**, không thêm, bớt hoặc chuyển phần tử sang nhóm khác. Ngược lại, `union` giữa hai gốc khác nhau thay đổi phân hoạch bằng cách hợp hai cây thành một.

## 4. Union by rank chọn gốc bằng cách nào?

Để cây không thành chuỗi quá dài, union by rank so sánh **rank của hai gốc** trước khi nối.

Khởi tạo n phần tử:

```text
for x in 0..n-1:
    parent[x] = x
    rank[x] = 0

components = n
```

Mọi cây ban đầu gồm một nút, có chiều cao 0 và rank 0.

Giả mã:

```text
union_by_rank(x, y):
    rx = find(x)
    ry = find(y)

    if rx == ry:
        return false

    if rank[rx] < rank[ry]:
        swap(rx, ry)

    parent[ry] = rx

    if rank[rx] == rank[ry]:
        rank[rx] += 1

    components -= 1
    return true
```

Ba trường hợp:

- `rank[rx]>rank[ry]`: gốc `ry` được treo dưới `rx`; rank của `rx` **không đổi**.
- `rank[rx]<rank[ry]`: hoán đổi để gốc có rank cao hơn được giữ; rank của gốc mới **không đổi**.
- `rank[rx]==rank[ry]`: chọn một gốc làm cha và **chỉ tăng rank của gốc đó đúng một**.

Nếu hai gốc bằng nhau, không nối và **không** tăng rank. Hợp trùng cũng không làm giảm số nhóm.

### Rank không phải nhãn ID nhóm

Đại diện `find(x)` là **gốc hiện tại**. Khi hai nhóm được hợp, một gốc cũ có thể trở thành nút con. Vì vậy root không phải một ID nghiệp vụ bền vững. Rank cũng không phải “độ ưu tiên” của khách hàng hoặc tên nhóm: nó chỉ phục vụ chiến lược giữ cây nông.

## 5. Vì sao rank bằng chiều cao khi chưa nén đường?

Giả sử ta **chỉ thực hiện `union by rank` từ trạng thái nhóm đơn**, và hàm `find` **không** sửa mảng cha.

Ta chứng minh bằng quy nạp rằng:

\[
\mathrm{rank}[r]=\mathrm{height}(r)
\]

với mọi **gốc hiện tại** r.

### Bước cơ sở

Cây đơn có một nút:

\[
\mathrm{rank}[r]=0,\quad \mathrm{height}(r)=0.
\]

### Hợp hai cây có rank khác nhau

Giả sử:

\[
\mathrm{rank}[r_A]=a,\quad
\mathrm{rank}[r_B]=b,\quad a>b.
\]

Ta giữ gốc `r_A` và treo `r_B` bên dưới. Chiều cao mới là:

\[
h_{\mathrm{new}}=\max(a,b+1).
\]

Vì a và b là số nguyên và `a>b`, ta có `a≥b+1`. Do đó:

\[
h_{\mathrm{new}}=a.
\]

Thuật toán **không đổi rank** của `r_A`, nên rank vẫn bằng chiều cao.

### Hợp hai cây có rank bằng nhau

Nếu cả hai cây đều cao r và có rank r, treo một gốc dưới gốc kia làm chiều cao mới thành:

\[
h_{\mathrm{new}}=\max(r,r+1)=r+1.
\]

Thuật toán tăng rank của gốc mới từ r lên `r+1`. Vậy rank tiếp tục bằng chiều cao.

**Kết luận:** khi **không có thao tác nén đường, và cây chỉ được hình thành bởi union by rank chuẩn**, rank tại gốc bằng chiều cao thực đo bằng số cạnh. Kết luận này **không áp dụng nguyên vẹn sau khi cho phép path compression**.

## 6. Nén đường đi làm thay đổi điều gì?

**Full path compression** tìm gốc trước rồi cho từng nút trên đường cũ trỏ trực tiếp tới gốc.

```text
find_full(x):
    root = x

    while parent[root] != root:
        root = parent[root]

    while parent[x] != x:
        old_parent = parent[x]
        parent[x] = root
        x = old_parent

    return root
```

Nén đường đi có các tác động:

- Có thể làm giảm **depth** của những nút trên đường.
- Có thể làm giảm **height** của cả cây nếu những đường sâu nhất được rút ngắn.
- **Không đổi gốc** của cây.
- **Không đổi** số thành viên hoặc số nhóm.
- **Không cập nhật rank**, theo thuật toán chuẩn.

Ta có bất đẳng thức quan trọng sau khi dùng nén đường:

\[
\boxed{\mathrm{height}(r)\le\mathrm{rank}[r]}
\]

nhưng dấu bằng **không còn luôn đúng**.

### Khi nén mà chiều cao không giảm

Nếu cây có **hai nhánh sâu bằng nhau**, việc nén một nhánh có thể rút ngắn nhiều đường tới gốc nhưng vẫn còn nhánh sâu kia. Khi đó `height` của **toàn cây** giữ nguyên.

Vì thế, không được suy “mỗi `find` có compression làm chiều cao của cây giảm ít nhất 1”. Lợi ích có thể chỉ nằm trên những đường được truy vấn và các nút đi qua.

## 7. Mô phỏng tám phần tử: trước và sau compression

Ta dựng một cây có rank 3 bằng cách **hợp những cây có rank bằng nhau**.

Khởi tạo:

```text
parent = [0,1,2,3,4,5,6,7]
rank   = [0,0,0,0,0,0,0,0]
components = 8
```

Thực hiện:

```text
union(0,1)
union(2,3)
union(0,2)

union(4,5)
union(6,7)
union(4,6)

union(0,4)
```

Trong trường hợp hai rank bằng nhau, ta giữ gốc nhóm của đối số đầu. Tất cả đối số dùng ở những phép hợp trên đều là gốc lúc được hợp nên `find` không nén thêm đường trước phần mô phỏng.

| Bước | Thao tác | `parent` sau thao tác | Rank của gốc chính |
|---:|---|---|---|
| 0 | Khởi tạo | `[0,1,2,3,4,5,6,7]` | Các gốc rank 0 |
| 1 | `union(0,1)` | `[0,0,2,3,4,5,6,7]` | `rank[0]=1` |
| 2 | `union(2,3)` | `[0,0,2,2,4,5,6,7]` | `rank[2]=1` |
| 3 | `union(0,2)` | `[0,0,0,2,4,5,6,7]` | `rank[0]=2` |
| 4 | `union(4,5)` | `[0,0,0,2,4,4,6,7]` | `rank[4]=1` |
| 5 | `union(6,7)` | `[0,0,0,2,4,4,6,6]` | `rank[6]=1` |
| 6 | `union(4,6)` | `[0,0,0,2,4,4,4,6]` | `rank[4]=2` |
| 7 | `union(0,4)` | `[0,0,0,2,0,4,4,6]` | `rank[0]=3` |

Tại bước 7, ta có một nhóm với gốc 0. Hình dạng cây:

```text
          0                     rank[0] = 3
       /  |  \
      1   2   4
          |  / \
          3 5   6
                |
                7
```

Các đường sâu:

```text
7 → 6 → 4 → 0  (3 cạnh)
5 → 4 → 0      (2 cạnh)
3 → 2 → 0      (2 cạnh)
```

Do đó:

\[
\mathrm{rank}[0]=3,\qquad\mathrm{height}(0)=3.
\]

**Đây là trạng thái trước khi nén đường.**

## 8. Lần nén thứ nhất: rank 3, chiều cao 2

Gọi `find(7)` dùng full compression:

```text
Đường cũ:
7 → 6 → 4 → 0

Cập nhật:
parent[7] = 0
parent[6] = 0
parent[4] = 0   (đã bằng 0)
```

Mảng cha mới:

```text
parent = [0,0,0,2,0,4,0,0]
```

Cây mới có thể vẽ:

```text
          0
      / / | \ \
     1 2  4 6 7
       |  |
       3  5
```

Những đường dài nhất còn lại:

```text
3 → 2 → 0 (2 cạnh)
5 → 4 → 0 (2 cạnh)
```

Vì vậy:

\[
\mathrm{rank}[0]=3,\qquad\mathrm{height}(0)=2.
\]

Rank không giảm dù chiều cao thực đã giảm từ 3 xuống 2.

**Quan sát thêm:** `rank[4]=2` vẫn được giữ như metadata lịch sử của nút 4, nhưng 4 **không còn là gốc**. Không được đọc `rank[4]` như “rank của nhóm chứa phần tử 4”. Rank nhóm phải đọc tại `rank[find(4)] = rank[0] = 3`.

## 9. Nén thêm các nhánh: rank 3, chiều cao 1

Tiếp tục gọi:

```text
find(3):
  3 → 2 → 0
  parent[3] = 0

find(5):
  5 → 4 → 0
  parent[5] = 0
```

Mảng sau cả hai lần:

```text
parent = [0,0,0,0,0,0,0,0]
```

Hình dạng là một cây **hình sao**:

```text
            0
    / / / / | \ \
   1 2 3 4 5 6 7
```

Mọi nút khác gốc chỉ cách gốc **một cạnh**, nên:

\[
\boxed{\mathrm{rank}[0]=3,\qquad\mathrm{height}(0)=1.}
\]

Điều này **hoàn toàn hợp lệ**. `rank[0]` vẫn ghi nhận lịch sử cây đã từng được hợp từ những cây rank thấp hơn. Nén đường không làm mất thông tin phân hoạch và không yêu cầu tính lại rank.

### Bảng đối chiếu ba thời điểm

| Thời điểm | `parent` | `rank[0]` | `height(0)` | Số nhóm |
|---|---|---:|---:|---:|
| Sau bảy phép hợp | `[0,0,0,2,0,4,4,6]` | 3 | 3 | 1 |
| Sau `find(7)` | `[0,0,0,2,0,4,0,0]` | 3 | 2 | 1 |
| Sau `find(3), find(5)` | `[0,0,0,0,0,0,0,0]` | 3 | 1 | 1 |

Đây là ví dụ cốt lõi để phân biệt **rank** với **chiều cao thực hiện tại**.

## 10. Vì sao không được tùy tiện giảm rank theo height?

Một cài đặt mới học có thể muốn “đồng bộ rank” như sau:

```text
find(x):
    root = ...   // Tìm gốc và nén đường.
    rank[root] = current_height(root)  // Sai với union by rank chuẩn.
    return root
```

Việc này không thuộc quy tắc của **union by rank** và có thể phá các bất biến dùng để chứng minh tính đúng đắn về độ phức tạp.

### Phản ví dụ dùng chính tám phần tử

Sau khi nén đầy đủ, mảng cha:

```text
parent = [0,0,0,0,0,0,0,0]

rank[0] = 3
rank[4] = 2   // Metadata cũ của nút nay không là gốc
```

Nếu cưỡng ép `rank[0]=height(0)=1`:

```text
parent[4] = 0
rank[4] = 2
rank[0] = 1
```

Khi đi theo cha `4→0`, rank **giảm từ 2 xuống 1**. Điều này vi phạm tính chất quan trọng của union by rank chuẩn:

\[
\mathrm{rank}[x]<\mathrm{rank}[\mathrm{parent}[x]]
\quad\text{khi }x\text{ không phải gốc}.
\]

Mặc dù phân hoạch hiện tại **chưa chắc sai**, ta đã phá điều kiện để sử dụng các chứng minh chuẩn về chiều cao, hạng và phân tích khấu hao của thuật toán đó.

### Vì sao không xóa luôn rank ở mọi nút con?

Có thể nghĩ tới việc tính lại toàn bộ rank của mọi nút sao cho cấu trúc mới có một bộ metadata hợp lệ. Nhưng như vậy:

- Cần một thuật toán tái tính rõ ràng trên **toàn cây hoặc nhiều phần tử**.
- Mất công duyệt và cập nhật không có trong `find` chuẩn.
- Là một **biến thể thuật toán khác**, cần tự chứng minh bất biến và phân tích độ phức tạp.
- Không cần thiết để tìm gốc hoặc hợp nhóm đúng theo Union–Find kinh điển.

**Quy tắc thực hành:** với union by rank chuẩn, chỉ **tăng rank khi hợp hai gốc có rank bằng nhau**; `find` không sửa rank.

## 11. Hai bất biến rank quan trọng hơn chiều cao tức thời

Khi kết hợp union by rank với nén đường, hai bất biến thường dùng vẫn đúng.

### Bất biến A — Rank tăng nghiêm ngặt trên đường cha

Với mọi nút không phải gốc:

\[
\mathrm{rank}[x]<
\mathrm{rank}[\mathrm{parent}[x]].
\]

**Tại sao đúng khi khởi tạo?** Ban đầu không có nút không phải gốc; tất cả đều tự trỏ.

**Khi union hai gốc khác rank:** gốc rank thấp trở thành con của gốc rank cao, nên có bất đẳng thức nghiêm ngặt.

**Khi union hai gốc cùng rank r:** gốc được giữ tăng rank lên r+1, còn gốc trở thành con giữ rank r.

**Khi nén đường:** một nút thay cha bằng **tổ tiên có rank lớn hơn**. Rank của mỗi nút không đổi, nên bất đẳng thức vẫn đúng.

Bất biến này không đòi rank của gốc bằng chiều cao thực sau nén.

### Bất biến B — Một gốc rank r đại diện ít nhất `2^r` phần tử

Với mọi gốc hiện tại r:

\[
\operatorname{size}(G_r)\ge 2^{\operatorname{rank}[r]}.
\]

Lập luận:

- Gốc nhóm đơn có rank 0 và một phần tử: `1=2^0`.
- Hợp hai cây khác rank: gốc rank lớn hơn giữ nguyên rank, nhóm mới nhiều phần tử hơn.
- Hợp hai cây cùng rank k: mỗi nhóm ít nhất `2^k` phần tử; nhóm mới ít nhất `2^{k+1}`, gốc tăng rank thành k+1.
- Nén đường không đổi số phần tử hoặc rank, nên bất biến vẫn đúng.

Hệ quả khi `n≥1`:

\[
\operatorname{rank}[r]\le\lfloor\log_2 n\rfloor.
\]

Đây là chặn trên cho rank, **không phải công thức để suy ra chính xác số thành viên nhóm**.

## 12. Rank là chặn trên cho chiều cao: chứng minh từng thao tác

Ta xét một cây có gốc r và đại lượng:

\[
H(r)=\max_{x\in G_r}\operatorname{depth}(x).
\]

Ta muốn duy trì:

\[
H(r)\le \operatorname{rank}[r].
\]

### Khởi tạo

Cây một nút có `H(r)=0` và `rank[r]=0`, nên bất đẳng thức đúng.

### Nén đường

Khi cho x trỏ tới **một tổ tiên** trên đường cha, đường từ x tới gốc ngắn đi; các phần tử khác hoặc giữ nguyên đường hoặc cũng có thể được hưởng một đường đi ngắn hơn khi qua x.

Nén đường chuẩn **không làm tăng độ sâu bất kỳ nút nào**; chiều cao của cây không tăng. Rank không đổi. Vậy bất đẳng thức tiếp tục đúng.

### Hợp hai cây khác rank

Giả sử giữ gốc A có rank a, treo gốc B rank b dưới A, với `a>b`. Chiều cao sau hợp thỏa:

\[
H_{\mathrm{new}}
=\max(H_A,H_B+1).
\]

Vì `H_A≤a` và `H_B≤b`, đồng thời `a≥b+1` do rank nguyên:

\[
H_{\mathrm{new}}\le\max(a,b+1)\le a.
\]

Rank gốc A không tăng, nên vẫn chặn chiều cao mới.

### Hợp hai cây cùng rank

Với `rank[A]=rank[B]=r`, chọn A làm gốc, tăng rank A thành `r+1`:

\[
H_{\mathrm{new}}
=\max(H_A,H_B+1)
\le\max(r,r+1)=r+1.
\]

Vậy rank mới vẫn chặn chiều cao, **cho dù `H_A` hoặc `H_B` nhỏ hơn r vì đã nén**.

**Kết luận:** khi dùng union by rank và compression chuẩn, mọi gốc hiện tại luôn thỏa `height≤rank≤⌊log₂ n⌋`. Dấu bằng giữa height và rank không còn được bảo đảm.

## 13. Sau nén, union hai cây cùng rank sẽ thế nào?

Giả sử có **hai cây riêng biệt** cùng rank 2, nhưng cả hai đã được nén thành dạng sao và có chiều cao thực bằng 1.

```text
Cây A: rank 2, height 1
Cây B: rank 2, height 1
```

Gọi `union(A,B)`:

- Hai rank bằng nhau.
- Chọn gốc A làm cha.
- Tăng rank A từ 2 thành **3**.
- Chiều cao thực mới là:

\[
H_{\mathrm{new}}=\max(1,1+1)=2.
\]

Do đó:

\[
\mathrm{rank}(A)=3,\quad H_{\mathrm{new}}=2.
\]

Đây **không phải** lỗi tăng rank. Rank được cập nhật bằng **quy tắc lịch sử của heuristic**, không phải thao tác “đo và đặt lại bằng chiều cao mới”.

### Có khiến union chọn gốc “không tối ưu” ở một trường hợp cụ thể không?

Có thể. Vì rank là **chặn trên**, hai cây có chiều cao thực khác thứ tự rank lịch sử. Union by rank có thể chọn gốc dựa trên hạng mà không trùng với cách chọn gốc theo **chiều cao thực hiện tại** hoặc **kích thước**.

Tuy vậy, việc giữ nguyên bất biến rank khiến chiến lược có **chặn lý thuyết mạnh và cập nhật O(1)** cho metadata mỗi lần hợp. Việc đo lại chiều cao thật để tối ưu một quyết định riêng thường quá tốn kém và không phải cách vận hành của DSU chuẩn.

## 14. Phân biệt union by rank và union by size

**Union by size** dùng số thành viên ở gốc:

```text
size[root] = số phần tử thực của nhóm root
```

**Union by rank** dùng hạng:

```text
rank[root] = metadata tăng theo quy tắc hợp các cây
```

| Thuộc tính | Union by size | Union by rank |
|---|---|---|
| Khởi tạo nhóm đơn | `size=1` | `rank=0` |
| Chọn gốc | Giữ nhóm lớn hơn | Giữ cây có rank lớn hơn |
| Khi metadata bằng nhau | Chọn một gốc và cộng size | Chọn một gốc và **tăng rank 1** |
| Sau hợp khác nhóm | `size[newRoot]=size[A]+size[B]` | Rank giữ nguyên nếu hai rank khác nhau |
| Sau path compression | Size vẫn là số thành viên thực | Rank có thể lớn hơn chiều cao thực |
| Truy vấn kích thước nhóm | `size[find(x)]` | Không thể lấy kích thước từ rank |
| Bảo đảm chiều cao chưa nén | `O(log n)` | `O(log n)` |
| Bộ nhớ cơ bản | `O(n)` | `O(n)` |

### Một ví dụ size lớn, rank nhỏ

Khởi tạo một nhóm gồm hai phần tử bằng `union(0,1)`, rank gốc tăng từ 0 lên 1. Sau đó liên tục gộp thêm từng nhóm đơn vào gốc rank 1:

```text
union(0,2)
union(0,3)
union(0,4)
...
```

Mỗi nhóm mới có rank 0 nên được treo dưới gốc rank 1. Rank của gốc **vẫn bằng 1**, dù nhóm có thể có hàng trăm hoặc hàng nghìn thành viên.

Vì thế, `rank=1` không có nghĩa “nhóm có một phần tử”, cũng không có nghĩa “nhóm có đúng hai phần tử”. Nó chỉ đưa ra **giới hạn tối thiểu** `size≥2^1=2`.

### Khi nào nên chọn size?

Nếu bài toán cần trả lời “nhóm chứa x hiện có bao nhiêu thành viên?”, union by size là lựa chọn tiện lợi vì `size[find(x)]` có sẵn. Union by rank có thể lưu thêm `size` nếu muốn, nhưng phải cập nhật size riêng khi hợp; không thể suy size từ rank.

## 15. Cài đặt Python: quan sát rank và chiều cao riêng biệt

Đoạn mã sau dùng **union by rank + full path compression**. Ta cũng lưu `size` để kiểm thử bất biến, nhưng **chiến lược chọn gốc chỉ dựa trên rank**.

Hàm `actual_height()` cố ý **không nén đường** khi đo, vì nếu nó gọi `find` có compression thì phép đo sẽ tự làm thay đổi đối tượng đang đo.

```python
class RankedDSU:
    def __init__(self, n: int):
        if not isinstance(n, int) or isinstance(n, bool):
            raise TypeError("n phải là số nguyên")
        if n < 0:
            raise ValueError("n phải không âm")

        self.parent = list(range(n))
        self.rank = [0] * n
        self.size = [1] * n
        self.components = n

    def _check(self, x: int) -> None:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError("Chỉ số phải là số nguyên")
        if not 0 <= x < len(self.parent):
            raise IndexError("Chỉ số ngoài miền")

    def find(self, x: int) -> int:
        self._check(x)

        root = x
        while self.parent[root] != root:
            root = self.parent[root]

        # Nén đường đầy đủ, lặp hai lượt.
        while self.parent[x] != x:
            old_parent = self.parent[x]
            self.parent[x] = root
            x = old_parent

        return root

    def union(self, x: int, y: int) -> bool:
        rx = self.find(x)
        ry = self.find(y)

        if rx == ry:
            return False

        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx

        self.parent[ry] = rx
        self.size[rx] += self.size[ry]

        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1

        self.components -= 1
        return True

    def same(self, x: int, y: int) -> bool:
        return self.find(x) == self.find(y)

    def component_size(self, x: int) -> int:
        return self.size[self.find(x)]

    def actual_height(self) -> int:
        # Ví dụ này trả chiều cao lớn nhất của mọi cây.
        # Không gọi find(), vì find() có thể nén đường.
        maximum = 0
        for start in range(len(self.parent)):
            x = start
            depth = 0
            while self.parent[x] != x:
                x = self.parent[x]
                depth += 1
            maximum = max(maximum, depth)
        return maximum


dsu = RankedDSU(8)

for x, y in [
    (0, 1), (2, 3), (0, 2),
    (4, 5), (6, 7), (4, 6),
    (0, 4)
]:
    assert dsu.union(x, y)

assert dsu.parent == [0, 0, 0, 2, 0, 4, 4, 6]
assert dsu.rank[0] == 3
assert dsu.actual_height() == 3

assert dsu.find(7) == 0
assert dsu.parent == [0, 0, 0, 2, 0, 4, 0, 0]
assert dsu.rank[0] == 3
assert dsu.actual_height() == 2

assert dsu.find(3) == 0
assert dsu.find(5) == 0
assert dsu.parent == [0, 0, 0, 0, 0, 0, 0, 0]
assert dsu.rank[0] == 3
assert dsu.actual_height() == 1

assert dsu.components == 1
assert dsu.component_size(7) == 8
assert dsu.union(1, 7) is False  # Hợp trùng.

print("rank =", dsu.rank[0])            # 3
print("height =", dsu.actual_height()) # 1
```

### Những gì mã chứng minh bằng một ví dụ

- Ban đầu, khi chưa có nén đường, rank và height của gốc đều bằng 3.
- Một `find(7)` giảm height xuống 2 nhưng rank vẫn là 3.
- Hai `find(3)` và `find(5)` tiếp theo giảm height xuống 1 nhưng rank vẫn là 3.
- Số nhóm và kích thước nhóm không đổi khi chỉ gọi `find`.
- Gọi lại `union` trong cùng nhóm trả `False` và không tăng rank.

**Lưu ý:** `actual_height()` ở trên chỉ dành cho quan sát/kiểm thử. Nó có thể đi theo nhiều đường cha, nên không nên gọi sau mỗi thao tác trong một DSU lớn cần hiệu năng cao.

## 16. Tại sao đo chiều cao thực có thể tốn kém?

Để tính `height(root)` chính xác, ta cần biết **độ sâu lớn nhất trong toàn bộ cây**. Mảng `parent` chỉ lưu cạnh từ nút tới cha, không tự lưu danh sách các con cho từng gốc.

Một cách đơn giản là quét mọi nút, đi theo cha đến gốc và lấy độ sâu lớn nhất. Với n phần tử và chiều cao tối đa h:

\[
T_{\mathrm{naiveHeight}}=O(nh).
\]

Nếu rừng đang có union by rank thì `h=O(log n)`, cho chặn **`O(n\log n)`** của cách đo ngây thơ ở trên. Nếu muốn đo nhiều lần, tổng chi phí có thể đáng kể.

Có thể xây danh sách con từ `parent` trong `O(n)` rồi duyệt các cây bằng DFS/BFS trong `O(n)` để tính chiều cao của toàn rừng ở **một thời điểm cố định**. Nhưng đó vẫn là công việc quét rộng, không phải cập nhật metadata `O(1)` trong mỗi `union`.

**Một lý do rank hữu ích:** rank được cập nhật cực rẻ bằng quy tắc cục bộ tại **hai gốc**, thay vì phải đo hình dạng cây sau mỗi phép nén.

### Cẩn trọng với phép đo làm thay đổi kết quả

Nếu viết:

```python
for x in range(n):
    root = dsu.find(x)
    # Tính depth bằng cách đi theo parent sau lời gọi...
```

thì bản thân `find` đã **nén đường**, khiến cây khác với trạng thái ban đầu cần đo. Để so sánh đúng trước/sau, phải đo bằng hàm không sửa dữ liệu hoặc chụp bản sao mảng cha rồi đo trên bản sao.

## 17. Kiểm tra bất biến rank bằng chương trình

Một test đúng cần quan sát cả **phân hoạch**, **rank** và **metadata tại gốc**.

### Kiểm tra rank tăng theo cha

```python
def check_rank_edges(dsu: RankedDSU) -> None:
    n = len(dsu.parent)

    for x in range(n):
        p = dsu.parent[x]
        assert 0 <= p < n

        if x != p:
            assert dsu.rank[x] < dsu.rank[p]


check_rank_edges(dsu)
```

Điều kiện này áp dụng cả sau compression vì cha mới của x là **tổ tiên có rank lớn hơn**, không phải một nút bất kỳ.

### Kiểm tra kích thước và giới hạn rank

```python
def check_root_metadata(dsu: RankedDSU) -> None:
    groups: dict[int, list[int]] = {}

    for x in range(len(dsu.parent)):
        root = dsu.find(x)
        groups.setdefault(root, []).append(x)

    assert len(groups) == dsu.components

    for root, members in groups.items():
        assert dsu.parent[root] == root
        assert dsu.size[root] == len(members)
        assert (1 << dsu.rank[root]) <= len(members)

    assert sum(len(members) for members in groups.values()) == len(dsu.parent)


check_root_metadata(dsu)
```

Dòng `1 << rank` tính `2^{rank}` cho rank nguyên không âm. Bất biến chỉ yêu cầu **nhóm có ít nhất `2^{rank}` phần tử**, không đòi bằng.

**Giới hạn kiểm thử:** các hàm trên dựa vào việc `find` có thể kết thúc. Nếu mảng cha đã bị sửa hỏng và có chu trình, cần kiểm tra chu trình riêng trước khi gọi `find` tiêu chuẩn.

### Vì sao không kiểm tra `rank[root]==actual_height()`?

Vì kiểm tra ấy sẽ **đánh trượt một DSU hợp lệ** sau path compression. Quan hệ đúng là:

```text
actual_height(root) <= rank[root]
```

với union by rank chuẩn, không phải luôn bằng nhau.

## 18. C++17: giữ rank nguyên khi dùng path halving

Trong nhiều bài toán đồ thị, phần tử là các chỉ số `0..n-1` và có thể lưu `parent` cùng `rank` trong `std::vector`.

Đoạn C++17 này dùng **path halving**: trong khi tìm gốc, cập nhật cha của x thành **ông/bà**, rồi chuyển sang cha mới. Đó là một biến thể nén đường, nhưng `rank` vẫn chỉ được cập nhật khi `unite` hợp hai gốc có hạng bằng nhau.

```cpp
#include <algorithm>
#include <cstddef>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <vector>

class RankedDSU {
public:
    explicit RankedDSU(std::size_t n)
        : parent_(n), rank_(n, 0), components_(n) {
        std::iota(parent_.begin(), parent_.end(), std::size_t{0});
    }

    std::size_t find(std::size_t x) {
        if (x >= parent_.size()) {
            throw std::out_of_range("DSU index out of range");
        }

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

        if (rank_[x] < rank_[y]) {
            std::swap(x, y);
        }

        parent_[y] = x;

        if (rank_[x] == rank_[y]) {
            ++rank_[x];
        }

        --components_;
        return true;
    }

    bool same(std::size_t x, std::size_t y) {
        return find(x) == find(y);
    }

    std::size_t component_count() const {
        return components_;
    }

private:
    std::vector<std::size_t> parent_;
    std::vector<unsigned> rank_;
    std::size_t components_;
};

int main() {
    RankedDSU dsu(8);

    dsu.unite(0, 1);
    dsu.unite(2, 3);
    dsu.unite(0, 2);
    dsu.unite(4, 5);
    dsu.unite(6, 7);
    dsu.unite(4, 6);
    dsu.unite(0, 4);

    std::cout << dsu.same(3, 7) << '\n';   // 1
    std::cout << dsu.component_count() << '\n'; // 1
}
```

### Vì sao `find` không giảm rank?

Path halving chỉ nối một nút tới **tổ tiên**. Nó có thể làm giảm chiều cao thực nhưng không hề thay đổi lịch sử các phép hợp đã tạo rank. Việc sửa `rank_` trong `find` không cần thiết, làm code phức tạp và phá khả năng dùng trực tiếp các lập luận union by rank chuẩn.

Cả path splitting lẫn full compression đều có cùng nguyên tắc: **chỉ sửa cha, không sửa rank** khi tìm gốc.

## 19. Độ phức tạp: rank, chiều cao và khấu hao

Chặn thời gian của DSU có nhiều mức cần phân biệt.

### 19.1. Chưa dùng heuristic

Nếu nối hai gốc tùy ý và không nén đường, cây có thể cao `Θ(n)`. Một `find` riêng lẻ có thể mất `Θ(n)`.

### 19.2. Union by rank, không nén

Ta đã chứng minh `rank[root]=height(root)≤⌊log₂ n⌋`. Do đó:

\[
T_{\mathrm{find}}=O(\log n)
\]

trong trường hợp xấu một lần gọi. Một `union` gọi hai `find`, cộng một lượng công việc hằng số, nên cũng có `O(log n)` worst-case.

### 19.3. Union by rank + path compression

Mỗi đường cha vẫn có chiều dài **không vượt rank tại gốc**, nên một `find` riêng lẻ có chặn `O(log n)` worst-case. Nhưng nén đường làm những truy vấn về sau thường ngắn hơn.

Theo định lý kinh điển về Union–Find, một chuỗi dài các phép tìm/hợp có tổng thời gian gần tuyến tính, thường mô tả:

\[
O\bigl(n+m\,\alpha(n)\bigr)
\]

trong phát biểu thông dụng với n phần tử được khởi tạo và m thao tác, `α` là một dạng hàm Ackermann ngược tăng rất chậm. Các phát biểu chính xác hơn có thể dùng `α(m,n)` và quy ước đếm thao tác khác.

**Không được suy ra một lần `find` luôn có `O(1)` worst-case.** Một lần gọi trước khi đường được nén vẫn có thể đi qua `Θ(log n)` cạnh.

### 19.4. Rank nhỏ không có nghĩa depth hiện tại bằng rank

Rank của **gốc** là chặn trên cho mọi độ sâu trong cây. Rank của **một nút con** không phải độ sâu của nút đó. Ví dụ sau nén đầy đủ ở phần 9:

```text
rank[4] = 2
depth(4) = 1
rank[0] = 3
height(0) = 1
```

Ta có **rank lịch sử tại 4 lớn hơn depth(4)**, và gốc có rank lớn hơn height hiện tại. Để biết nhóm của 4, phải dùng `find(4)=0`; để đọc rank đại diện, dùng `rank[0]`.

## 20. Kết hợp hai nhóm đã nén không cần tính lại height

Xét một hệ thống tiếp nhận nhiều đỉnh và các cạnh mới.

Sau một giai đoạn, một nhóm có rank 3 nhưng chiều cao thực chỉ 1 vì nhiều truy vấn đã nén đường. Nhóm khác có rank 2, chiều cao thực 2.

Nếu gọi `union(x,y)` với x thuộc nhóm rank 3 và y thuộc nhóm rank 2:

1. Lấy hai gốc bằng `find`.
2. So sánh `rank[rx]` và `rank[ry]`.
3. Gắn gốc rank 2 dưới gốc rank 3.
4. **Không tăng rank 3**.
5. Không cần tính chiều cao thực.

Chiều cao mới không vượt:

\[
\max(1,2+1)=3.
\]

Rank gốc mới vẫn bằng 3, nên chặn trên vẫn đúng.

Nếu hai nhóm có cùng rank 3 nhưng chiều cao thực có thể lần lượt là 1 và 2, thì sau hợp rank mới thành 4. Chiều cao thực không quá `max(1,2+1)=3`, **vẫn nhỏ hơn rank mới**. Quy tắc không cần “đo lại và chỉnh rank”.

## 21. Những lỗi thường gặp

| Nhầm lẫn | Điều gì sai? | Cách sửa |
|---|---|---|
| `rank[root]` luôn là chiều cao thực | Sai sau path compression | Hiểu `height(root)≤rank[root]` |
| `rank[root]` là số thành viên | Rank không phải kích thước | Dùng `size[find(x)]` |
| `rank[x]` là độ sâu của x | Rank là metadata heuristic, không phải depth | Đo đường cha để có depth nếu cần |
| Nén đường phải giảm rank | Phá bất biến lịch sử và chứng minh chuẩn | Không sửa rank trong `find` |
| Đo height bằng cách gọi `find` có nén trên mọi nút | Phép đo tự đổi trạng thái | Dùng hàm không ghi hoặc bản sao |
| Tăng rank sau mọi phép union | Rank không còn đúng quy tắc chuẩn | Chỉ tăng khi hai rank bằng nhau |
| Hợp trùng vẫn tăng rank | Không có hai cây mới được nối | Nếu hai gốc trùng, return no-op |
| So sánh rank ở x/y bất kỳ | Nút con có rank cũ | Gọi `find` rồi so sánh rank tại gốc |
| Buộc hai DSU có cùng mảng parent | Heuristic/tie-break/nén có thể tạo rừng khác | So sánh phân hoạch và bất biến |
| Xem `rank=3` là cây có đúng 8 nút | `2^3` chỉ là kích thước **tối thiểu** | Không suy size chính xác từ rank |
| Đặt `parent[x]` thành một nút ở cây khác trong `find` | Có thể chuyển nhóm mà không union | Chỉ đi tắt tới tổ tiên cùng cây |
| Đổi cha của gốc thành hậu duệ tùy ý | Tạo chu trình cha | Chỉ nối hai gốc khác nhau qua `union` |
| Xem `find` có nén là thao tác chỉ đọc | Có thể ghi chung vùng nhớ | Đồng bộ khi xử lý đa luồng |
| Đánh đồng khấu hao với worst-case mỗi lời gọi | Dùng sai định lý `α(n)` | Tách phân tích đơn lẻ và chuỗi thao tác |

## 22. Biên và những tình huống cần kiểm thử

**Miền rỗng (`n=0`).** Mảng cha và rank rỗng, số nhóm bằng 0. Không có phần tử nào để `find`; lời gọi tìm trên một chỉ số bất kỳ phải báo lỗi.

**Một phần tử (`n=1`).** `parent=[0]`, `rank=[0]`, height 0. Gọi `find(0)` không thay đổi gì; `union(0,0)` không tăng rank.

**Chỉ số âm trong Python.** `parent[-1]` bình thường truy cập phần tử cuối list, nhưng không được chấp nhận nếu miền DSU là `0..n-1`.

**Hợp hai gốc cùng rank.** Phải tăng rank ở **gốc được giữ**, không tăng ở gốc đã thành con.

**Hợp khác rank.** Phải giữ rank gốc cao hơn, không tăng hạng chỉ vì nhóm mới có thêm phần tử.

**Nén nhiều lần.** `find` có thể liên tục rút ngắn đường nhưng rank không thay đổi nếu không có union mới.

**Có nhiều nhóm.** Nén một cây không được chuyển nút sang cây khác. Chỉ so sánh metadata tại gốc sau khi đã tìm gốc.

**Dữ liệu parent bị hỏng.** Nếu có chu trình `0→1→0`, hàm `find` chuẩn có thể lặp mãi. Cần phát hiện chu trình trước khi gọi `find` trên dữ liệu không đáng tin.

**Truy cập đồng thời.** Full compression, halving, splitting đều có thể ghi vào `parent`, nên không mặc định thread-safe; C++ có thể xảy ra data race nếu thiếu đồng bộ.

## 23. Ứng dụng trong đồ thị và vì sao rank hữu ích

Với đồ thị **vô hướng** có n đỉnh, DSU hỗ trợ thêm cạnh và kiểm tra liên thông:

```text
add_edge(u, v):
    union(u, v)

connected(u, v):
    return find(u) == find(v)
```

Khi nhiều cạnh được thêm, union by rank giúp rừng không quá sâu. Khi nhiều truy vấn `connected` được thực hiện, path compression làm đường truy vấn ngắn đi. Dù rank của một gốc có thể **cao hơn chiều cao thực hiện tại**, việc giữ nó theo quy tắc chuẩn vẫn bảo đảm chặn phân tích của Union–Find.

### Kruskal và phát hiện chu trình

Trong thuật toán **Kruskal** cho cây khung nhỏ nhất, cạnh `(u,v)` chỉ được chọn khi hai đầu có **gốc khác nhau**. Khi đã cùng gốc, cạnh đó sẽ tạo chu trình trong rừng cạnh được chấp nhận.

Chi phí DSU với rank + compression rất nhỏ theo khấu hao, nhưng toàn thuật toán Kruskal còn có bước **sắp xếp cạnh**. Không được đánh đồng tổng thời gian Kruskal với riêng chi phí `find/union`.

### Những yêu cầu DSU chuẩn không phục vụ

- **Xóa cạnh hoặc tách nhóm:** DSU cơ bản không có `split`.
- **Tìm đường đi cụ thể:** rừng cha là cấu trúc đại diện, không nhất thiết trùng các cạnh đồ thị.
- **Quan hệ có hướng không đối xứng:** truy vấn đường đi một chiều không được giải bằng cùng-gốc đơn giản.
- **Nhóm chồng lấn:** DSU biểu diễn một phân hoạch, không phải nhiều tập có giao nhau.

Những giới hạn đó không thay đổi dù dùng union by rank hay path compression.

## 24. Bài tập tự kiểm tra có lời giải

**Câu 1.** Với cây hình sao có tám nút và gốc 0, chiều cao (đếm theo số cạnh) là bao nhiêu?

**Đáp án:** Bằng **1**, vì mọi nút khác gốc cách gốc đúng một cạnh.

**Câu 2.** Một cây chỉ có gốc 0, `parent[0]=0`. Height và rank khởi tạo bằng bao nhiêu?

**Đáp án:** Cả hai đều bằng **0**.

**Câu 3.** Khi nào rank tại gốc bằng chiều cao thực trong union by rank chuẩn?

**Đáp án:** Khi cây được tạo từ các nhóm đơn bằng union by rank mà **không có nén đường**, với rank khởi tạo bằng 0 và height tính theo số cạnh.

**Câu 4.** Sau compression, quan hệ tổng quát giữa height và rank tại gốc là gì?

**Đáp án:** `height(root)≤rank[root]`. Có thể nhỏ hơn nghiêm ngặt.

**Câu 5.** Trong ví dụ tám phần tử ở bài, trước khi gọi `find(7)`, root 0 có rank và height bao nhiêu?

**Đáp án:** `rank[0]=3` và `height(0)=3`.

**Câu 6.** Sau `find(7)` nén đầy đủ, mảng cha và chiều cao trở thành gì?

**Đáp án:** `parent=[0,0,0,2,0,4,0,0]`, height bằng **2**, còn rank gốc vẫn **3**.

**Câu 7.** Sau khi tiếp tục nén `find(3)` và `find(5)`, height và rank gốc là bao nhiêu?

**Đáp án:** Height còn **1**, rank vẫn **3**; mảng cha là `[0,0,0,0,0,0,0,0]`.

**Câu 8.** Vì sao không đặt `rank[0]=1` sau khi cây ở câu 7 thành hình sao?

**Đáp án:** Union by rank chuẩn **không giảm rank trong `find`**. Nếu giảm, rank của gốc có thể thấp hơn rank lịch sử của nút con, phá bất biến rank tăng theo đường cha và các chứng minh chuẩn.

**Câu 9.** Cho `rank[4]=2` nhưng `parent[4]=0` và `rank[0]=3`. Rank nào mô tả nhóm của phần tử 4?

**Đáp án:** `rank[find(4)] = rank[0] = 3`. `rank[4]` là metadata cũ ở nút không còn là gốc.

**Câu 10.** Union by rank nối hai gốc có rank 2 và 5 thì rank của gốc sau hợp bằng bao nhiêu?

**Đáp án:** **5**, vì gốc rank 2 được treo dưới gốc rank 5; hạng không tăng khi hai hạng khác nhau.

**Câu 11.** Union by rank nối hai gốc có cùng rank 2 thì rank gốc mới bao nhiêu?

**Đáp án:** **3**, vì chỉ khi hai rank bằng nhau mới tăng hạng đúng một.

**Câu 12.** Một gốc có rank 4 thì nhóm của nó phải có ít nhất bao nhiêu thành viên?

**Đáp án:** Ít nhất `2^4=16` phần tử. Có thể có nhiều hơn.

**Câu 13.** Rank của một gốc có 100 phần tử có bắt buộc bằng `⌊log₂ 100⌋=6` không?

**Đáp án:** Không. Rank chỉ có **chặn trên** bằng 6; một nhóm lớn dạng sao có thể có rank 1.

**Câu 14.** Hai cây đều rank 2 nhưng đã nén thành height 1. Sau khi hợp theo rank, rank và chiều cao mới có thể là bao nhiêu?

**Đáp án:** Rank gốc mới **3**; chiều cao thực **2** nếu gắn một gốc dưới gốc kia.

**Câu 15.** Nén đường đi có cập nhật `size[root]` hay `components` không?

**Đáp án:** Không. Nó chỉ rút ngắn đường cha, không thêm/bớt phần tử hoặc hợp nhóm.

**Câu 16.** Rank của một nút con có bằng độ sâu của nó sau nén không?

**Đáp án:** Không bắt buộc. Rank là metadata theo quy tắc union; depth là số cạnh hiện tại từ nút tới gốc.

**Câu 17.** Vì sao đo height bằng cách gọi `find` nén đường trên mọi nút có thể gây sai mục tiêu phép đo?

**Đáp án:** Vì `find` **thay đổi mảng cha trong lúc đo**. Kết quả đo là trạng thái đã bị tối ưu, không nhất thiết là chiều cao ban đầu.

**Câu 18.** Với union by rank không compression, `find` có chặn thời gian worst-case nào?

**Đáp án:** `O(log n)` vì height bằng rank tại gốc và rank không vượt `⌊log₂ n⌋`.

**Câu 19.** Union by rank kết hợp compression có độ phức tạp khấu hao điển hình nào?

**Đáp án:** Gần `O(α(n))` khấu hao mỗi thao tác trong cách trình bày phổ biến, với `α` là hàm Ackermann ngược; **không** đồng nghĩa worst-case `O(1)` mỗi lần.

**Câu 20.** Hai phiên bản DSU có cùng phân hoạch nhưng `parent` khác nhau do compression. Có đủ kết luận một phiên bản sai không?

**Đáp án:** Không. Mảng cha có thể biểu diễn cùng nhóm dưới những hình dạng cây khác nhau. Cần kiểm tra root, bất biến, rank và kết quả truy vấn.

## Ghi nhớ

- **Chiều cao thực** `height(root)` là đường dài nhất theo **số cạnh** từ phần tử tới gốc. **Rank** là metadata của **union by rank**, không phải kích thước nhóm hoặc độ sâu nút.
- Khi **chưa có nén đường**, union by rank chuẩn từ các nhóm đơn có `rank[root]=height(root)`. Sau **path compression**, ta chỉ bảo đảm `height(root)≤rank[root]`.
- Nén đường có thể làm height giảm từ **3 xuống 2 rồi 1** trong khi rank vẫn **3**. Đây là kết quả đúng, không phải lỗi.
- **Không tự giảm rank theo chiều cao mới.** Rank chỉ tăng **khi hợp hai gốc có rank bằng nhau**; `find` không cập nhật rank.
- Hai bất biến quan trọng là **rank tăng nghiêm ngặt theo cha** và **nhóm có gốc rank r chứa ít nhất `2^r` phần tử**. Nhờ đó rank chặn trên bởi `⌊log₂ n⌋` và cũng chặn chiều cao thực.
- **Union by size** lưu số thành viên thực tại gốc; **union by rank** lưu hạng, không dùng rank để trả kích thước nhóm.
- Với union by rank + path compression, mỗi `find` vẫn có thể mất `O(log n)` worst-case nhưng chuỗi thao tác có chi phí gần `O(α(n))` **khấu hao**. Chọn cấu trúc và phân tích dựa trên thao tác cần dùng, không đánh đồng rank với hình dạng cây tức thời.

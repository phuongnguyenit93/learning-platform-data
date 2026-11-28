# DSU hoàn tác và lý do thường không dùng nén đường đi tùy ý

**Disjoint Set Union (DSU)**, còn gọi là **Union–Find**, được thiết kế để quản lý một phân hoạch khi các nhóm **chỉ nhập lại**. Trong phiên bản thông dụng, `union(x,y)` nối hai nhóm, `find(x)` xác định đại diện, còn **union by size/rank** kết hợp **path compression** cho hiệu năng gần hằng số theo khấu hao.

Nhưng một số bài toán không chỉ hỏi trạng thái hiện tại. Ta có thể cần thử một giả định, thực hiện vài phép hợp, trả lời truy vấn rồi **quay trở lại đúng trạng thái trước khi thử**. Đó là động cơ của **DSU hoàn tác (rollback DSU)**.

Điểm quan trọng nhất: **rollback không đồng nghĩa với xóa một cạnh bất kỳ**. Rollback đưa cấu trúc về một mốc lịch sử theo **thứ tự ngược của các thay đổi**; xóa cạnh trong đồ thị lại có thể khiến thành phần tách ra hoặc vẫn liên thông qua đường khác. Ngoài ra, `find` có nén đường đi có thể sửa nhiều con trỏ cha, khiến một bản ghi hoàn tác đơn giản không còn đủ.

Bài này thuộc chương **Tập hợp rời nhau** trong học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Ta tập trung vào bất biến, cách ghi nhật ký thay đổi, triển khai Python/C++, chi phí thời gian/bộ nhớ, kiểm thử và ứng dụng xử lý liên thông theo trục thời gian.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nêu đúng hợp đồng của `find`, `union`, `snapshot` và `rollback`.
2. Phân biệt **rollback một đoạn lịch sử** với **xóa cạnh tùy ý**.
3. Giải thích vì sao rollback DSU thông dụng dùng **union by size/rank nhưng không path compression**.
4. Chứng minh `find` vẫn có chặn `O(log n)` worst-case khi hợp theo kích thước mà không nén.
5. Thiết kế nhật ký đủ để khôi phục `parent`, `size`, số nhóm và metadata tổng hợp.
6. Xử lý chính xác `union` không đổi nhóm và checkpoint lồng nhau.
7. Viết mã Python và C++17 thực hiện snapshot/rollback theo stack.
8. Hiểu vì sao có thể *vẫn* kết hợp nén đường với rollback khi ghi log đầy đủ, nhưng phải phân tích lại chi phí.
9. Dùng rollback DSU trong duyệt nhánh thử nghiệm hoặc cây đoạn trên trục thời gian để xử lý truy vấn offline.
10. Phân tích những giới hạn của rollback, độ phức tạp và các lỗi thường gặp.

## 2. Nhắc lại DSU: phân hoạch và rừng cha

Cho tập phần tử:

\[
U=\{0,1,\ldots,n-1\}.
\]

DSU quản lý một **phân hoạch** của U thành các nhóm không giao nhau. Mỗi nhóm là một cây có gốc trong rừng cha:

```text
parent[x] = cha của x
parent[r] = r   nếu r là gốc

find(x)  = gốc của cây chứa x
same(x,y) = (find(x) == find(y))
```

Ví dụ:

```text
        0             4
       / \           / \
      1   2         5   6
          |
          3

Nhóm A: {0,1,2,3}
Nhóm B: {4,5,6}
```

Nếu `union(3,6)`, ta tìm gốc 0 và 4 rồi gắn **một gốc dưới gốc kia**. Hai cây trở thành một cây, và số nhóm giảm đúng một.

### Bất biến cấu trúc

Một rừng cha hợp lệ cần giữ:

- `0≤parent[x]<n` với mọi phần tử x.
- Mỗi cây có đúng một gốc r tự trỏ.
- Không có chu trình cha gồm nhiều nút.
- Từ mỗi phần tử đi theo cha phải tới một gốc.
- `find(x)==find(y)` khi và chỉ khi x và y cùng nhóm.
- `size[r]` chỉ được xem là số thành viên nhóm khi r là **gốc hiện tại**.
- `components` bằng số gốc của rừng, nếu có duy trì bộ đếm.

Trong rollback DSU, ngoài việc giữ các bất biến sau mỗi phép hợp, ta còn phải bảo đảm **phục hồi tất cả giá trị từng bị thay đổi** khi trở về checkpoint.

## 3. Tại sao cần hoàn tác?

Tưởng tượng một bộ giải bài toán có nhiều phương án thử:

```text
Trạng thái ban đầu
      |
   thử A: union(0,1)
      |
   thử B: union(2,3)
      |
   tính kết quả
      |
   hoàn tác B
      |
   thử C: union(1,4)
      |
   tính kết quả
      |
   hoàn tác C và A
```

Nếu tạo bản sao toàn bộ mảng `parent` và `size` trước **mỗi** nhánh, mỗi lần sao chép có thể tốn `Θ(n)` thời gian/bộ nhớ. Với nhiều nhánh, chi phí trở nên lớn.

Rollback DSU khai thác một đặc điểm của **union by size/rank không nén**: mỗi phép hợp thành công chỉ phải cập nhật **một số hằng ô dữ liệu**. Ta lưu giá trị cũ vào stack và khôi phục bằng cách pop.

### Giao diện mong muốn

```text
cp = snapshot()
union(a,b)
union(c,d)

... chạy truy vấn ...

rollback(cp)
```

Sau `rollback(cp)`, trạng thái phải tương đương với thời điểm chụp cp, gồm:

- Phân hoạch và đại diện.
- Mảng cha và metadata được bảo đảm khôi phục.
- Kích thước và số lượng nhóm.
- Các tổng hợp khác nếu giao diện có hỗ trợ.

**Không được chỉ khôi phục số nhóm mà để nguyên con trỏ cha đã sửa.** Khi đó các truy vấn `find` tiếp theo vẫn có thể báo kết quả sai.

## 4. Rollback khác xóa cạnh của đồ thị

Xét đồ thị vô hướng:

```text
0 — 1 — 2
 \     /
  \---/
```

Ba cạnh thực:

```text
a=(0,1)
b=(1,2)
c=(0,2)
```

DSU xử lý:

```text
add a => union(0,1) thành công
add b => union(1,2) thành công
add c => union(0,2) là no-op (đã liên thông)
```

Nếu **xóa cạnh b** khỏi đồ thị, 1 vẫn nối 2 qua đường `1—0—2`. Nhóm phải tiếp tục là `{0,1,2}`.

Nhưng nếu “undo” chính phép hợp do b từng gây ra, DSU có thể quay lại trạng thái chưa tính đến c, tức tạo ra phân hoạch sai với đồ thị hiện hành.

### Bảng phân biệt

| Thao tác | Ý nghĩa | Điều kiện |
|---|---|---|
| `union(x,y)` | Hợp hai nhóm hiện tại | Chỉ nối hai gốc khác nhau |
| `rollback(cp)` | Phục hồi trạng thái tại mốc cp | Lùi lại một đoạn thay đổi **gần nhất** |
| Xóa cạnh `(u,v)` | Loại bỏ cạnh thật khỏi đồ thị | Phải xác định còn đường thay thế hay không |
| Tách một nhóm | Chia các thành viên theo quy tắc mới | DSU chuẩn không có `split` |
| Truy vấn phiên bản cũ | Đọc một trạng thái lịch sử | Có thể cần persistent DSU hoặc lịch sử riêng |

**Rollback không cung cấp phép `delete_edge(edgeID)` tùy ý.** Nó chỉ hữu ích cho bài toán xóa khi ta thiết kế thuật toán **sắp xếp các phép hợp** để thao tác cần hoàn tác nằm ở cuối stack, chẳng hạn khi duyệt các nhánh thời gian offline.

## 5. Union by size không nén: nền tảng cho nhật ký ngắn

Đầu tiên, chọn **union by size** và hàm `find` **không sửa mảng cha**.

```text
find(x):
    while parent[x] != x:
        x = parent[x]
    return x

union(x,y):
    a = find(x)
    b = find(y)

    if a == b:
        return false

    if size[a] < size[b]:
        swap(a,b)

    parent[b] = a
    size[a] += size[b]
    components -= 1
    return true
```

Với một phép hợp thành công:

- Gốc b trở thành con của gốc a.
- `size[a]` tăng thêm `size[b]`.
- `components` giảm một.
- Không có đường cha khác bị sửa bởi `find`.

Do đó, để hoàn tác phép hợp này ta chỉ cần nhớ:

```text
childRoot      = b
parentRoot     = a
oldSizeOfA     = size[a] trước khi hợp
```

Sau khi hoàn tác các phép hợp **mới hơn**, ta phục hồi:

```text
parent[b] = b
size[a] = oldSizeOfA
components += 1
```

`size[b]` không cần khôi phục trong thiết kế này, vì nó **không bị sửa** khi b trở thành con. Nếu hệ thống sửa thêm các trường khác, phải lưu giá trị cũ của chúng.

## 6. Vì sao union by size giữ `find` ở `O(log n)`?

Không nén đường có thể khiến một số đường cha dài hơn phiên bản tối ưu, nhưng hợp theo kích thước vẫn giới hạn chiều cao.

Giả sử gốc của cây A kích thước a được treo dưới cây B kích thước b và `a≤b`.

Khi độ sâu của một nút trong A tăng một, kích thước nhóm mới chứa nó là:

\[
a+b\ge 2a.
\]

Như vậy, **mỗi lần độ sâu của một nút tăng do union, kích thước nhóm chứa nó ít nhất gấp đôi**. Bắt đầu từ kích thước 1, sau k lần tăng độ sâu, nhóm cần có ít nhất `2^k` nút. Vì chỉ có n phần tử:

\[
2^k\le n
\quad\Longrightarrow\quad
k\le\lfloor\log_2 n\rfloor.
\]

Do đó chiều cao cây ở mọi trạng thái hợp lệ được tạo từ n nhóm đơn bằng union by size là:

\[
h=O(\log n).
\]

Suy ra:

- `find` có `O(log n)` **worst-case mỗi lần gọi**.
- `union` có `O(log n)` **worst-case**, do gọi hai `find` và cập nhật `O(1)` ô.
- Việc **hoàn tác một thay đổi union thành công** là `O(1)` sau khi biết bản ghi phải pop.

Rollback khôi phục những trạng thái từng tồn tại và hợp lệ; vì vậy chặn chiều cao cũng đúng sau rollback.

### Không nhầm với chặn Ackermann ngược

Với DSU thường, **union by size/rank + path compression** mang lại chặn khấu hao gần `O(α(n))` mỗi thao tác. Bản rollback đơn giản **chủ động bỏ path compression**, nên dùng chặn **`O(log n)` worst-case cho `find`/`union`**. Không được tự áp chặn `O(α(n))` từ cấu trúc khác.

## 7. Lịch sử thay đổi là stack, không phải tập các cạnh

Ta quản lý:

```text
history = stack các thay đổi thành công
snapshot() = history.length
rollback(cp) = pop mọi thay đổi cho tới độ dài cp
```

Ví dụ:

```text
history:
  0: union(0,1)
  1: union(2,3)
  2: union(0,2)
  3: union(4,5)
  4: union(3,5)
```

Nếu gọi `rollback(3)`, ta hoàn tác lần lượt:

```text
union(3,5)   // log cuối cùng
union(4,5)   // log trước đó
```

Còn lại ba thay đổi đầu.

**Không có thao tác “xóa bản ghi thứ 1 rồi giữ nguyên thứ 2, 3, 4”** trong giao diện này. Các phép hợp sau được quyết định dựa trên những gốc, kích thước và trạng thái do các phép hợp trước tạo ra. Pop từ giữa có thể phá hoàn toàn điều kiện cần để phục hồi.

### Snapshot là một độ dài stack

Một checkpoint `cp` kiểu này **không phải mã phiên bản bất biến**. Nếu:

1. Chụp checkpoint ở độ dài 5.
2. Rollback về độ dài 2.
3. Thực hiện những phép hợp khác tạo lại stack dài 5.

thì số 5 mới không còn đại diện cho lịch sử cũ. Cần chỉ sử dụng checkpoint còn hợp lệ trên **nhánh lịch sử hiện tại**; thường quản lý checkpoint theo cấu trúc lời gọi DFS lồng nhau.

## 8. Truy vết cụ thể với sáu phần tử

Khởi tạo:

```text
U = {0,1,2,3,4,5}
parent = [0,1,2,3,4,5]
size   = [1,1,1,1,1,1]
components = 6
history = []
```

Duy trì nguyên tắc nếu size bằng nhau thì giữ gốc của đối số thứ nhất sau khi tìm gốc.

| Bước | Thao tác | Gốc bị treo dưới gốc nào? | Các nhóm | Số nhóm | Log |
|---:|---|---|---|---:|---:|
| 0 | Khởi tạo | — | `{0}{1}{2}{3}{4}{5}` | 6 | 0 |
| 1 | `union(0,1)` | `1→0` | `{0,1}{2}{3}{4}{5}` | 5 | 1 |
| 2 | `snapshot()=1` | — | Giữ nguyên | 5 | 1 |
| 3 | `union(2,3)` | `3→2` | `{0,1}{2,3}{4}{5}` | 4 | 2 |
| 4 | `union(0,2)` | `2→0` | `{0,1,2,3}{4}{5}` | 3 | 3 |
| 5 | `snapshot()=3` | — | Giữ nguyên | 3 | 3 |
| 6 | `union(4,5)` | `5→4` | `{0,1,2,3}{4,5}` | 2 | 4 |
| 7 | `union(3,5)` | `4→0` | `{0,1,2,3,4,5}` | 1 | 5 |

Trạng thái sau bước 7:

```text
parent = [0,0,0,2,0,4]

       0
    /  |  \
   1   2   4
       |   |
       3   5

size[0] = 6
components = 1
history.length = 5
```

### Rollback về checkpoint thứ hai: `cp=3`

Pop hai bản ghi mới nhất:

1. Hoàn tác `union(3,5)`: `parent[4]=4`, `size[0]` từ 6 về 4, số nhóm tăng từ 1 lên 2.
2. Hoàn tác `union(4,5)`: `parent[5]=5`, `size[4]` từ 2 về 1, số nhóm tăng từ 2 lên 3.

Kết quả:

```text
parent = [0,0,0,2,4,5]

Nhóm: {0,1,2,3}, {4}, {5}
components = 3
history.length = 3
```

### Thử nhánh mới và rollback về checkpoint đầu: `cp=1`

Từ trạng thái trên, gọi `union(4,0)`: vì nhóm chứa 0 có size 4 lớn hơn nhóm chứa 4 có size 1, gốc 4 được treo dưới gốc 0.

Sau đó rollback về cp=1 sẽ hoàn tác:

```text
union(4,0)  // nhánh mới
union(0,2)
union(2,3)
```

Còn các nhóm:

```text
{0,1}, {2}, {3}, {4}, {5}

components = 5
history.length = 1
```

**Nhóm `{0,1}` vẫn giữ nguyên** vì phép hợp ở bước 1 nằm trước checkpoint đầu tiên.

## 9. Nén đường đi có thể sửa nhiều hơn một liên kết

Đây là lý do kỹ thuật chính khiến rollback DSU đơn giản thường **không** nén đường.

Giả sử trước một phép hợp có hai cây:

```text
A:                  B:
     0                   4
    / \                 / \
   1   2               5   6
       |                     |
       3                     7
```

Trong mảng cha:

```text
parent = [0,0,0,2,4,4,4,6]
```

Giả sử hai nhóm có cùng kích thước 4. Phép `union(0,4)` nối gốc 4 dưới 0:

```text
parent = [0,0,0,2,0,4,4,6]
```

Đường tới gốc từ 7 lúc này là:

```text
7 → 6 → 4 → 0
```

Gọi `find(7)` với **full path compression** sẽ sửa thêm:

```text
parent[7] = 0
parent[6] = 0
parent[4] = 0   // Đã bằng 0.
```

Kết quả:

```text
parent = [0,0,0,2,0,4,0,0]
```

### Điều gì xảy ra nếu chỉ undo bản ghi union?

Rollback ngây thơ chỉ biết phép `union(0,4)` đã đặt `parent[4]=0`; nó sửa lại `parent[4]=4` và khôi phục `size[0]`.

Mảng còn:

```text
parent = [0,0,0,2,4,4,0,0]
```

Nhưng lúc này:

```text
find(6) = 0
find(7) = 0
```

trong khi **trước union**, 6 và 7 phải thuộc nhóm có gốc 4.

Chỉ hoàn tác **một liên kết cha của union** là **không đủ**, bởi `find(7)` đã rút ngắn đường qua ranh giới của phép hợp cần phục hồi.

Đây là **phản ví dụ trực tiếp** cho việc kết hợp path compression tùy ý với nhật ký chỉ ghi những thay đổi của union.

## 10. Vậy path compression và rollback có hoàn toàn bất khả thi?

**Không.** Đây là điểm cần diễn đạt chính xác.

Về mặt kỹ thuật, ta *có thể* cho `find` nén đường và **ghi vào nhật ký mọi phép ghi `parent[x]` cần được hoàn tác**. Khi rollback, phải khôi phục chúng theo đúng thứ tự ngược, cùng với các thay đổi do union gây ra.

Ví dụ cho một phép nén:

```text
oldParent = parent[x]

if oldParent != root:
    history.push((x, oldParent))
    parent[x] = root
```

Nếu một `find` sửa h nút cha, nó có thể thêm **`Θ(h)` bản ghi** vào lịch sử. Nhiều lần `find` hoặc các biến thể halving/splitting cũng có thể sửa nhiều cha theo các truy vấn liên tiếp.

### Đánh đổi phát sinh

- Nhật ký có thể tăng ngay cả khi chỉ thực hiện **truy vấn `same`**.
- `snapshot()` vẫn có thể là `O(1)`, nhưng `rollback` phải pop cả các sửa đổi do `find`.
- Thời gian và bộ nhớ hoàn tác không còn chỉ tỷ lệ với số **union thành công**.
- Các chặn khấu hao từ DSU thông dụng **không tự động áp dụng** cho chuỗi có rollback, vì một đường đã nén có thể bị khôi phục về trạng thái sâu rồi lại được truy vấn nhiều lần.
- Cần thiết kế rõ **thứ tự log**, **điều kiện ghi** và **định nghĩa snapshot** để bảo toàn bất biến.

Với union by size/rank, ta vẫn có chặn chiều cao `O(log n)` cho từng trạng thái hợp lệ, nên việc ghi đầy đủ mọi cập nhật cũng có thể được phân tích. Nhưng đó là **một biến thể khác**, phức tạp hơn nhật ký ngắn của rollback DSU cổ điển.

**Quy tắc thực hành:** nếu không có lý do và chứng minh đặc biệt, dùng **union by size/rank + `find` không ghi** cho rollback DSU.

## 11. Thiết kế bản ghi hoàn tác tối thiểu

Với Union–Find chỉ quản lý kích thước và số nhóm:

```text
Change {
    childRoot,
    parentRoot,
    oldSizeOfParentRoot
}
```

Ta **không cần lưu `oldParentOfChildRoot`** nếu bảo đảm chỉ nối **hai gốc**, bởi trước khi nối, gốc bị treo tự trỏ: `parent[childRoot]=childRoot`.

Ta cũng không nhất thiết phải lưu `oldComponents`, vì mỗi union thành công **giảm đúng một** và rollback mỗi bản ghi **tăng đúng một**. Tuy nhiên, lưu giá trị cũ của `components` có thể hữu ích nếu API có nhiều loại thay đổi hoặc muốn cơ chế ghi log tổng quát.

### Nếu metadata có nhiều trường

Giả sử còn lưu:

```text
total[root]      Tổng trọng số thành viên.
minimum[root]    Giá trị nhỏ nhất.
flagOr[root]     OR các cờ.
edgeCount[root]  Số cạnh trong thành phần.
```

Một phép hợp có thể sửa tất cả các trường này. Muốn rollback đúng, có hai phương án:

1. Lưu **giá trị cũ** của từng trường được sửa.
2. Lưu một **bản ghi thay đổi tổng quát**, đủ để hoàn tác mọi phép ghi.

Không phải metadata nào cũng có phép trừ ngược. Ví dụ min, max và OR **không thể phục hồi** chỉ bằng phép toán ngược đơn giản sau khi đã gộp. **Lưu giá trị cũ** là cách an toàn.

### Bất biến nhật ký

Sau khi đã thực hiện k phép hợp thành công chưa được hoàn tác:

```text
history.length = k
components = n - k
```

nếu ban đầu có n nhóm đơn, không thêm phần tử mới và không ghi các loại thay đổi khác vào lịch sử. Các phép hợp trùng nhóm là no-op **không tăng k**.

## 12. Python: rollback DSU với kích thước và tổng trọng số

Cài đặt sau dùng:

- `parent`, `size` và `total` tại **gốc**.
- `find` **không nén đường**.
- `union by size`.
- `history` lưu **giá trị cũ** của mỗi trường bị thay đổi ở phép hợp thành công.
- `snapshot()` trả độ dài stack.
- `rollback(cp)` đưa DSU về trạng thái ở checkpoint hợp lệ.

Giả định trọng số của các phần tử là **cố định**. Không có hàm thay đổi trọng số giữa các checkpoint; nếu thêm hàm đó, phải ghi log thay đổi trọng số và tổng nhóm.

```python
class RollbackDSU:
    def __init__(
        self, n: int, weights: list[int] | None = None
    ):
        if not isinstance(n, int) or isinstance(n, bool):
            raise TypeError("n phải là số nguyên")
        if n < 0:
            raise ValueError("n phải không âm")

        if weights is None:
            weights = [0] * n
        if len(weights) != n:
            raise ValueError("weights phải có đúng n phần tử")
        if any(
            not isinstance(v, int) or isinstance(v, bool)
            for v in weights
        ):
            raise TypeError("Trọng số phải là số nguyên")

        self.parent = list(range(n))
        self.size = [1] * n
        self.total = weights.copy()
        self.components = n

        # (child_root, parent_root, old_size, old_total)
        self.history: list[tuple[int, int, int, int]] = []

    def _check(self, x: int) -> None:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError("ID phải là số nguyên")
        if not 0 <= x < len(self.parent):
            raise IndexError("ID ngoài miền DSU")

    def find(self, x: int) -> int:
        self._check(x)

        # KHÔNG path compression.
        while self.parent[x] != x:
            x = self.parent[x]
        return x

    def same(self, x: int, y: int) -> bool:
        return self.find(x) == self.find(y)

    def component_size(self, x: int) -> int:
        return self.size[self.find(x)]

    def component_sum(self, x: int) -> int:
        return self.total[self.find(x)]

    def snapshot(self) -> int:
        return len(self.history)

    def union(self, x: int, y: int) -> bool:
        a = self.find(x)
        b = self.find(y)

        if a == b:
            return False  # Không đổi gì và không tạo log.

        if self.size[a] < self.size[b]:
            a, b = b, a

        self.history.append(
            (b, a, self.size[a], self.total[a])
        )
        self.parent[b] = a
        self.size[a] += self.size[b]
        self.total[a] += self.total[b]
        self.components -= 1
        return True

    def rollback(self, checkpoint: int) -> None:
        if (
            not isinstance(checkpoint, int)
            or isinstance(checkpoint, bool)
        ):
            raise TypeError("checkpoint phải là số nguyên")
        if not 0 <= checkpoint <= len(self.history):
            raise ValueError("checkpoint không hợp lệ")

        while len(self.history) > checkpoint:
            child, root, old_size, old_total = self.history.pop()

            self.parent[child] = child
            self.size[root] = old_size
            self.total[root] = old_total
            self.components += 1


d = RollbackDSU(6, [4, -2, 7, 1, 3, 5])

assert d.components == 6
assert d.union(0, 1)
assert d.component_sum(1) == 2
cp_a = d.snapshot()  # 1

assert d.union(2, 3)
assert d.union(0, 2)
assert d.component_size(3) == 4
assert d.component_sum(3) == 10
cp_b = d.snapshot()  # 3

assert d.union(4, 5)
assert d.union(3, 5)
assert d.components == 1
assert d.component_sum(5) == 18

d.rollback(cp_b)
assert d.components == 3
assert d.same(0, 3)
assert not d.same(0, 5)
assert d.component_size(0) == 4
assert d.component_sum(0) == 10

assert d.union(4, 0)      # Thử nhánh khác.
assert d.components == 2
assert d.component_sum(4) == 13

d.rollback(cp_a)
assert d.components == 5
assert d.same(0, 1)
assert not d.same(2, 3)
assert not d.same(0, 4)
assert d.component_sum(0) == 2

# Union trùng: không sửa trạng thái hoặc history.
checkpoint = d.snapshot()
assert d.union(0, 1) is False
assert d.snapshot() == checkpoint
```

### Tại sao mã khôi phục cả tổng nhóm?

Giả sử trước khi hợp, gốc a có tổng 10, gốc b có tổng 8. Sau `union`, `total[a]=18`. Nếu rollback chỉ sửa `parent[b]=b` nhưng quên `total[a]`, nhóm của a đã mất các phần tử b nhưng vẫn báo tổng 18.

Vì vậy log chứa `old_total` và khôi phục nó khi pop. Trường `total[b]` không đổi trong phép hợp (b chỉ mất vai trò gốc), nên không cần log trường đó.

### Vì sao không log khi `union` trả false?

Khi `find(x)==find(y)`, không có liên kết hay metadata nào bị thay đổi vì `find` không nén. Không có gì cần khôi phục, nên không tạo bản ghi.

Nếu API khác yêu cầu **undo chính xác từng lệnh**, kể cả no-op, có thể ghi sentinel cho lệnh không đổi trạng thái; lúc ấy cách tính checkpoint và quy tắc pop phải được thiết kế lại nhất quán.

## 13. Chứng minh rollback trả đúng trạng thái trước đó

Giả sử trước phép hợp, hai nhóm khác nhau có gốc a và b với `size[a]≥size[b]`.

Trong `union`:

```text
history.push((b,a,oldSizeA,oldTotalA))
parent[b] = a
size[a] = oldSizeA + size[b]
total[a] = oldTotalA + total[b]
components -= 1
```

### Bước hoàn tác một bản ghi cuối

Khi bản ghi đó là phần tử cuối của stack, mọi thay đổi được thực hiện **sau** nó đã được hoàn tác trước. Ta khôi phục:

```text
parent[b] = b
size[a] = oldSizeA
total[a] = oldTotalA
components += 1
```

Vì b là **gốc trước khi hợp**, `parent[b]` vốn bằng b. `size[b]` và `total[b]` không bị sửa lúc hợp nên vẫn mang giá trị cũ. Các nút nằm dưới b đi theo cha tới b như trước.

Do đó, hai cây ban đầu được khôi phục đúng, metadata tại hai gốc và số nhóm cũng đúng.

### Hoàn tác nhiều bản ghi

Áp dụng lập luận trên lần lượt cho bản ghi **cuối rồi kế cuối**, ... cho tới checkpoint. Mỗi lần pop đưa DSU về trạng thái **trước một phép hợp thành công gần nhất**. Bằng quy nạp, sau khi pop hết những bản ghi từ `history.length` xuống cp, trạng thái bằng trạng thái tại checkpoint cp.

Điều kiện mấu chốt:

- `find` không ghi.
- Không có thay đổi khác ngoài `union` đã được log.
- Rollback chỉ phục hồi theo thứ tự **LIFO**.
- Không dùng checkpoint của một nhánh lịch sử đã bị loại bỏ.

## 14. Độ phức tạp của mã Python

Đặt n là số phần tử và k là số **phép hợp thành công** bị hoàn tác trong một lần `rollback`.

| Thao tác | Thời gian | Bộ nhớ phụ |
|---|---|---|
| Khởi tạo | `O(n)` | `O(n)` cho các mảng |
| `find(x)` | `O(log n)` worst-case | `O(1)` |
| `same(x,y)` | `O(log n)` worst-case | `O(1)` |
| `component_size(x)` | `O(log n)` worst-case | `O(1)` |
| `component_sum(x)` | `O(log n)` worst-case | `O(1)` |
| `union(x,y)` | `O(log n)` worst-case | `O(1)` bản ghi nếu thành công |
| `snapshot()` | `O(1)` | `O(1)` |
| `rollback(cp)` | `O(k)` | `O(1)` biến tạm |

Trong một DSU cố định n phần tử chỉ hợp nhóm, số union thành công **đang có hiệu lực** không thể vượt `n-1`. Do vậy stack `history` tại một trạng thái của lớp này chứa tối đa `n-1` bản ghi, cho tổng bộ nhớ **`O(n)`**.

Nhưng số lượng thao tác trong toàn bộ quá trình duyệt nhiều nhánh **có thể rất lớn**: sau mỗi rollback, chương trình có thể thực hiện nhiều phép union khác, rồi rollback tiếp. `O(n)` là **kích thước lịch sử đồng thời**, không phải giới hạn tổng số phép hợp đã thực hiện trong suốt chương trình.

## 15. C++17: rollback DSU bằng stack thay đổi

Đây là một cài đặt độc lập chỉ giữ `parent`, `size` và `components`. `find` không có nén đường, còn `snapshot` là độ dài vector `history_`.

```cpp
#include <cassert>
#include <cstddef>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <utility>
#include <vector>

class RollbackDSU {
public:
    explicit RollbackDSU(std::size_t n)
        : parent_(n), size_(n, 1), components_(n) {
        std::iota(parent_.begin(), parent_.end(),
                  std::size_t{0});
    }

    std::size_t find(std::size_t x) const {
        if (x >= parent_.size()) {
            throw std::out_of_range("DSU index out of range");
        }
        // Tuyệt đối không nén cha tại đây.
        while (parent_[x] != x) {
            x = parent_[x];
        }
        return x;
    }

    bool same(std::size_t x, std::size_t y) const {
        return find(x) == find(y);
    }

    bool unite(std::size_t x, std::size_t y) {
        x = find(x);
        y = find(y);

        if (x == y) return false;

        if (size_[x] < size_[y]) {
            std::swap(x, y);
        }

        history_.push_back({y, x, size_[x]});
        parent_[y] = x;
        size_[x] += size_[y];
        --components_;
        return true;
    }

    std::size_t snapshot() const {
        return history_.size();
    }

    void rollback(std::size_t checkpoint) {
        if (checkpoint > history_.size()) {
            throw std::out_of_range("Invalid checkpoint");
        }

        while (history_.size() > checkpoint) {
            const Change c = history_.back();
            history_.pop_back();

            parent_[c.child] = c.child;
            size_[c.root] = c.old_size;
            ++components_;
        }
    }

    std::size_t component_size(std::size_t x) const {
        return size_[find(x)];
    }

    std::size_t component_count() const {
        return components_;
    }

private:
    struct Change {
        std::size_t child;
        std::size_t root;
        std::size_t old_size;
    };

    std::vector<std::size_t> parent_;
    std::vector<std::size_t> size_;
    std::vector<Change> history_;
    std::size_t components_;
};

int main() {
    RollbackDSU d(5);

    assert(d.unite(0, 1));
    const auto cp = d.snapshot();

    assert(d.unite(2, 3));
    assert(d.unite(1, 3));
    assert(d.same(0, 2));
    assert(d.component_size(0) == 4);

    d.rollback(cp);
    assert(d.same(0, 1));
    assert(!d.same(0, 2));
    assert(d.component_count() == 4);

    assert(d.unite(3, 4));
    assert(d.same(3, 4));
    assert(!d.same(1, 4));

    std::cout << "Rollback DSU OK\n";
}
```

### Ghi chú về C++

`std::size_t` là kiểu không dấu: cần bảo đảm dữ liệu đầu vào được kiểm tra trước khi chuyển từ số âm, hoặc dùng kiểm tra miền phù hợp. Trong `find`, điều kiện `x>=parent_.size()` loại bỏ mọi giá trị không thuộc miền sau khi chuyển kiểu.

Vector `history_` chỉ lưu các phép hợp **đã làm thay đổi cấu trúc**. Nếu muốn truy vấn theo **số lệnh** thay vì độ dài lịch sử union thành công, phải bổ sung cơ chế ánh xạ hoặc log sentinel.

Bản C++ trên không lưu trọng số; nếu thêm `total_`/`minimum_`, phải bổ sung trường tương ứng vào `Change` và khôi phục đầy đủ.

## 16. Khi nào cần lưu no-op vào history?

Hai thiết kế đều có thể hợp lệ, nhưng **không được trộn quy ước**.

### Thiết kế A — Snapshot theo số thay đổi

```text
union(x,y) cùng gốc → không đẩy lịch sử.
snapshot() = số lần thay đổi cấu trúc chưa rollback.
```

Đây là cách của hai lớp đã trình bày. Nó gọn và đủ cho thuật toán duyệt nhánh dùng checkpoint ngay trước một loạt phép hợp.

### Thiết kế B — Nhật ký theo từng lệnh union

```text
union(x,y) cùng gốc → đẩy sentinel NO_CHANGE.
union(x,y) khác gốc → đẩy Change.
```

Cách này hữu ích nếu API yêu cầu:

```text
undo_last_union_command()
```

tức mỗi lệnh union, kể cả no-op, có một đơn vị để undo. Khi pop sentinel, không sửa `parent` hay `components`.

**Không được viết `components += 1` cho bản ghi no-op.** Chỉ có hợp hai nhóm khác nhau mới làm số nhóm giảm.

### Khi metadata vẫn thay đổi dù không hợp nhóm

Một số ứng dụng vừa quản lý liên thông vừa đếm **mọi cạnh được thêm**. Nếu cạnh `(u,v)` nối hai đỉnh đã cùng nhóm:

- Phân hoạch không thay đổi.
- Nhưng `edgeCount[root]` **tăng một** nếu đây là một cạnh thật mới.

Trong trường hợp đó, `add_edge` không còn là một phép `union` thuần. Nó **vẫn phải log** thay đổi `edgeCount` nếu muốn rollback, dù `union` trả false.

## 17. Rollback metadata: tổng, cờ, số cạnh và tính nhất quán

Giả sử mỗi đỉnh có trọng số tĩnh và mỗi gốc chứa:

```text
size[root]
total[root]
minimum[root]
flagOr[root]
```

Khi hợp hai gốc a và b, gốc a được giữ:

```text
size[a]    += size[b]
total[a]   += total[b]
minimum[a]  = min(minimum[a], minimum[b])
flagOr[a]  |= flagOr[b]
```

Để rollback, bản ghi có thể là:

```text
Change:
    child = b
    root = a
    oldSize = size[a] trước khi sửa
    oldTotal = total[a] trước khi sửa
    oldMinimum = minimum[a] trước khi sửa
    oldFlagOr = flagOr[a] trước khi sửa
```

Khôi phục các giá trị **cũ** theo thứ tự ngược, rồi cho b tự trỏ và tăng số nhóm.

### Không thể suy min/OR cũ chỉ từ min/OR mới

Ví dụ hai nhóm có min lần lượt 2 và 5, min sau hợp là 2. Chỉ biết min mới 2 không đủ để biết min của mỗi nhóm trước khi hợp nếu metadata đã bị ghi đè.

Với OR bit, `0010 OR 0010 = 0010`; từ OR kết quả không suy ra mỗi nhóm cũ đóng góp bit nào.

**Vì vậy rollback metadata tổng quát nên lưu giá trị trước khi cập nhật**, không giả định phép gộp nào cũng có nghịch đảo.

### Thay đổi giá trị của một đỉnh

Nếu hệ thống hỗ trợ `set_value(x,new)` trong nhánh thử nghiệm, phép cập nhật này cũng phải ghi log:

- Giá trị cũ của đỉnh x.
- Tổng nhóm cũ và các metadata chịu ảnh hưởng.
- Mọi cấu trúc bổ sung bị thay đổi.

Nếu chỉ log `union` mà không log `set_value`, rollback checkpoint sẽ **không khôi phục toàn bộ trạng thái**.

## 18. Bẫy checkpoint trên các nhánh lịch sử

Ví dụ:

```text
cp0 = snapshot()       // độ dài 0
union(0,1)             // độ dài 1
cp1 = snapshot()       // độ dài 1

union(1,2)             // độ dài 2, thuộc nhánh A
cpA = snapshot()       // độ dài 2

rollback(cp1)          // về độ dài 1
union(3,4)             // độ dài 2, thuộc nhánh B
```

`cpA` vẫn là **số 2**, nhưng trạng thái có độ dài 2 hiện tại đã **khác** trạng thái nhánh A trước đó.

Nếu gọi `rollback(cpA)` ngay lúc này, không có bản ghi nào bị pop vì độ dài đã bằng 2; DSU **không** quay lại nhánh A.

### Quy tắc sử dụng

- Dùng checkpoint trong **ngữ cảnh DFS**: trước khi vào nhánh, chụp; khi rời nhánh, rollback đúng mốc.
- Không coi checkpoint là một “mã thời điểm” có thể quay lại tùy ý.
- Nếu cần lưu nhiều phiên bản và truy cập ngẫu nhiên, tìm hiểu **persistent DSU** hoặc thiết kế lưu trạng thái khác.
- Đối với ứng dụng bất đồng bộ, cần tránh nhiều tác vụ cùng thay đổi một history stack mà không có cơ chế điều phối.

## 19. Ứng dụng 1: thử những lựa chọn hợp nhóm trong quay lui

Giả sử một bộ giải đang duyệt cây quyết định, ở mỗi nhánh nó có thể áp thêm quan hệ “x và y thuộc cùng nhóm”.

Mẫu xử lý:

```text
search(node):
    checkpoint = dsu.snapshot()

    for each constraint in node.localConstraints:
        dsu.union(constraint.x, constraint.y)

    if node is leaf:
        answer(node, dsu)
    else:
        for child in node.children:
            search(child)

    dsu.rollback(checkpoint)
```

Mỗi nút của cây quyết định được xử lý trên trạng thái kế thừa từ tổ tiên. Sau khi rời nút, các thay đổi cục bộ bị gỡ, nên nhánh khác không nhận nhầm quan hệ của nhánh trước.

### Vì sao snapshot đặt trước các thay đổi?

Nếu chụp snapshot **sau** khi đã hợp các ràng buộc của nút rồi rollback về đó, những phép hợp ấy vẫn còn. Muốn gỡ cả ràng buộc cục bộ khi rời nhánh, phải chụp **trước** khi cập nhật.

### Khi nào không phù hợp?

Nếu ràng buộc có yêu cầu “hai phần tử bắt buộc khác nhóm”, DSU thuần chỉ thể hiện quan hệ **cùng nhóm**. Cần bổ sung kiểm tra hoặc một DSU có trọng số/parity và thiết kế rollback tương ứng. Không được kết luận một mâu thuẫn logic chỉ từ việc hai gốc khác nhau mà chưa định nghĩa các điều kiện bổ sung.

## 20. Ứng dụng 2: xử lý liên thông động offline

Với đồ thị vô hướng có các thao tác:

```text
add_edge(id,u,v)
remove_edge(id)
connected(u,v)
```

Nếu biết trước toàn bộ chuỗi sự kiện, ta có thể dùng kỹ thuật **cây đoạn trên trục thời gian**.

Không xóa cạnh trực tiếp khỏi DSU. Thay vào đó:

1. Chuyển mỗi khoảng một cạnh còn hoạt động thành `[l,r)`.
2. Phân bổ cạnh đó vào các nút của cây đoạn mà khoảng nút nằm trong `[l,r)`.
3. Duyệt cây đoạn bằng DFS:
   - Chụp checkpoint.
   - Hợp các cạnh được gán cho nút.
   - Tới lá thời gian t thì trả truy vấn ở t.
   - Rollback về checkpoint khi rời nút.

### Ví dụ chuỗi sự kiện

```text
t=0: add a=(0,1)
t=1: ask(0,2)       → false
t=2: add b=(1,2)
t=3: ask(0,2)       → true
t=4: remove a
t=5: ask(0,2)       → false
t=6: add c=(0,2)
t=7: ask(1,2)       → true
t=8: remove b
t=9: ask(1,2)       → false
```

Các khoảng sống:

```text
a=(0,1): [0,4)
b=(1,2): [2,8)
c=(0,2): [6,10)
```

Trạng thái ở `t=3` chứa a và b, nên 0 nối 2. Ở `t=5` chỉ còn b, nên 0 bị tách. Ở `t=7` còn b và c, nên 1 nối 2. Ở `t=9` chỉ còn c, nên 1 không nối 2.

**Rollback là công cụ phục hồi trạng thái giữa các nhánh thời gian**, chứ không phải một lệnh xóa cạnh tương ứng trực tiếp với `remove_edge`.

## 21. Vì sao các cạnh hoạt động ở lá thời gian là đúng?

Cây đoạn biểu diễn khoảng `[0,T)`. Mỗi cạnh có khoảng hoạt động `[l,r)`, và được gán vào **một tập các nút có khoảng rời nhau**, hợp lại đúng `[l,r)`.

Khi đi từ gốc cây đoạn tới lá t:

- Nếu `l≤t<r`, đường đi tới t gặp **đúng một** nút có lưu cạnh ấy.
- Nếu t nằm ngoài `[l,r)`, không nút nào trên đường tới lá t chứa cạnh ấy.

Vì vậy, tại lá t, DSU đã hợp **đúng các cạnh đang hoạt động** tại thời điểm t.

Các phép hợp của cạnh song song hoặc cạnh nội bộ có thể là no-op; điều đó không làm sai quan hệ liên thông. Nếu cần duy trì số **cạnh thực**, những phép add no-op về liên thông vẫn phải được tính trong metadata riêng và được rollback.

### Vì sao rollback sau khi duyệt lá?

Nếu không khôi phục khi quay ra khỏi nhánh, các cạnh được gán cho thời điểm bên trái sẽ còn tồn tại khi xử lý thời điểm bên phải, gây **liên thông giả**. `rollback(checkpoint)` đảm bảo mỗi nhánh bắt đầu từ trạng thái của **tổ tiên chung**, không nhiễm dữ liệu từ nhánh đã duyệt.

## 22. Giả mã cây đoạn thời gian và rollback

```text
build_intervals(events):
    // Mỗi ID cạnh có một khoảng hoạt động [l,r).
    // Nếu chưa bị xóa, r=T.

for (l,r,u,v) in intervals:
    segment_tree.add_to_covering_nodes(l,r,(u,v))

dfs(node, left, right):
    cp = dsu.snapshot()

    for (u,v) in segment_tree[node]:
        dsu.union(u,v)

    if right-left == 1:
        if event[left] is connected_query(u,v):
            answer[left] = dsu.same(u,v)
    else:
        mid = (left+right)//2
        dfs(leftChild,left,mid)
        dfs(rightChild,mid,right)

    dsu.rollback(cp)
```

### Một điểm dễ sai: thời điểm có hiệu lực

Ta dùng quy ước cạnh được thêm tại thời điểm `l` có hiệu lực **kể từ sự kiện add đó**, và khi bị xóa tại `r` thì **không còn hiệu lực ở hoặc sau r**.

Do đó khoảng sống là **`[l,r)`**.

Vì mỗi thời điểm chỉ có một sự kiện trong ví dụ, không có truy vấn cùng chỉ số t với add/remove. Nếu hệ thống cho phép nhiều sự kiện cùng timestamp, phải xác định rõ **thứ tự xử lý** các sự kiện trong timestamp trước khi dựng khoảng.

## 23. Python: segment tree + rollback trên một chuỗi offline

Đoạn mã dưới đây dùng chính lớp `RollbackDSU` đã định nghĩa ở phần 12, với `weights=None`. Mỗi ID cạnh được thêm tối đa một lần và được xóa tối đa một lần; nếu cần nhiều khoảng hoạt động cho cùng ID, phải mở rộng bộ phân tích sự kiện.

```python
class OfflineConnectivity:
    def __init__(self, n: int):
        self.n = n
        self.events: list[tuple] = []
        self.query_count = 0

    def add(self, eid: str, u: int, v: int) -> None:
        self.events.append(("add", eid, u, v))

    def remove(self, eid: str) -> None:
        self.events.append(("remove", eid))

    def ask(self, u: int, v: int) -> None:
        self.events.append(("ask", self.query_count, u, v))
        self.query_count += 1

    def solve(self) -> list[bool]:
        T = len(self.events)
        answers = [False] * self.query_count
        if T == 0:
            return answers

        opened: dict[str, tuple[int, int, int]] = {}
        used: set[str] = set()
        intervals: list[tuple[int, int, int, int]] = []

        # Biến add/remove thành các khoảng cạnh tồn tại.
        for t, event in enumerate(self.events):
            kind = event[0]

            if kind == "add":
                _, eid, u, v = event
                if eid in used:
                    raise ValueError("ID cạnh dùng lại")
                if not (0 <= u < self.n and 0 <= v < self.n):
                    raise IndexError("Đỉnh ngoài miền")
                used.add(eid)
                opened[eid] = (t, u, v)

            elif kind == "remove":
                _, eid = event
                if eid not in opened:
                    raise ValueError("Xóa cạnh không hoạt động")
                l, u, v = opened.pop(eid)
                intervals.append((l, t, u, v))

            elif kind == "ask":
                _, _, u, v = event
                if not (0 <= u < self.n and 0 <= v < self.n):
                    raise IndexError("Đỉnh ngoài miền")

            else:
                raise ValueError("Sự kiện lạ")

        for l, u, v in opened.values():
            intervals.append((l, T, u, v))

        buckets: list[list[tuple[int, int]]] = [
            [] for _ in range(4 * T)
        ]

        def insert(
            node: int, left: int, right: int,
            ql: int, qr: int, edge: tuple[int, int]
        ) -> None:
            if qr <= left or right <= ql:
                return
            if ql <= left and right <= qr:
                buckets[node].append(edge)
                return

            mid = (left + right) // 2
            insert(node * 2, left, mid, ql, qr, edge)
            insert(node * 2 + 1, mid, right, ql, qr, edge)

        for l, r, u, v in intervals:
            if l < r:
                insert(1, 0, T, l, r, (u, v))

        dsu = RollbackDSU(self.n)

        def visit(node: int, left: int, right: int) -> None:
            cp = dsu.snapshot()

            for u, v in buckets[node]:
                dsu.union(u, v)

            if right - left == 1:
                event = self.events[left]
                if event[0] == "ask":
                    _, idx, u, v = event
                    answers[idx] = dsu.same(u, v)
            else:
                mid = (left + right) // 2
                visit(node * 2, left, mid)
                visit(node * 2 + 1, mid, right)

            dsu.rollback(cp)

        visit(1, 0, T)
        return answers


offline = OfflineConnectivity(3)

offline.add("a", 0, 1)
offline.ask(0, 2)          # False
offline.add("b", 1, 2)
offline.ask(0, 2)          # True
offline.remove("a")
offline.ask(0, 2)          # False
offline.add("c", 0, 2)
offline.ask(1, 2)          # True
offline.remove("b")
offline.ask(1, 2)          # False

assert offline.solve() == [
    False, True, False, True, False
]
```

### Phạm vi của cài đặt

- Đây là **offline connectivity**: phải thu thập tất cả thao tác trước khi gọi `solve`.
- Mã chỉ kiểm tra **liên thông vô hướng**, không trả đường đi.
- Các ID cạnh là duy nhất; hai cạnh song song cần **hai ID khác nhau**.
- `RollbackDSU` không nén đường, nên mỗi phép `find` chỉ đọc.
- Tham số đỉnh phải là số nguyên hợp lệ; ví dụ kiểm tra khoảng ở bước giải, ứng dụng thực tế nên xác minh kiểu và ID ngay ở phương thức `add/ask`.
- Mã minh họa dùng đệ quy trên cây đoạn có độ sâu `O(log T)`; không lưu snapshot vĩnh viễn cho mỗi sự kiện, mà hoàn tác theo các khung DFS.

## 24. Độ phức tạp của segment tree thời gian

Gọi:

- n: số đỉnh.
- T: số sự kiện thời gian, `T≥1`.
- K: số khoảng hoạt động của cạnh.
- Q: số truy vấn liên thông.

Một khoảng `[l,r)` được gán vào `O(log T)` nút cây đoạn. Vậy có:

\[
O(K\log T)
\]

bản sao cạnh trong các bucket, cũng là số **lần thử union** khi DFS đi qua các nút.

Mỗi `union` của rollback DSU có chặn `O(log n)` worst-case. Một `same` cũng `O(log n)`. Chi phí hoàn tác tổng cộng tỷ lệ với số thay đổi đã log; mỗi union thành công tạo tối đa một bản ghi và mỗi bản ghi được pop đúng một lần khi rời nhánh.

Do đó tổng thời gian:

\[
\boxed{
O\bigl(n+T+(K\log T+Q)\log n\bigr)
}
\]

theo mô hình sử dụng cây đoạn, union by size không nén và truy vấn same.

Bộ nhớ:

\[
O(n+T+K\log T),
\]

bao gồm mảng DSU, cây đoạn/bucket, sự kiện, khoảng và nhật ký rollback. Tại một thời điểm trên **một đường DFS**, số union thành công hiện hành không vượt n−1, nên lịch sử đồng thời của DSU có kích thước `O(n)`.

### Không suy ra `O(α(n))` cho toàn bộ thuật toán

Ở đây `find` cố ý không nén, nên chặn là `O(log n)`. Ta cũng tốn `O(log T)` lần thử union cho mỗi khoảng sống cạnh. Không được bỏ hệ số theo thời gian hoặc chi phí quản lý cây đoạn chỉ vì DSU thông thường có kết quả gần hằng số khấu hao.

## 25. Rollback DSU và persistent DSU khác nhau thế nào?

**Rollback DSU**:

- Lưu những thay đổi trên một **stack**.
- Phù hợp với nhánh DFS, thử nghiệm rồi hoàn nguyên.
- Truy cập phiên bản theo quy tắc **LIFO**.
- `snapshot()` thường chỉ là độ dài history, không phải ID phiên bản bền vững.

**Persistent DSU**:

- Thiết kế để lưu/đọc nhiều **phiên bản** theo một mô hình persistent cụ thể.
- Có thể truy vấn phiên bản cũ mà không phải undo toàn bộ trạng thái hiện tại.
- Cách cập nhật, bộ nhớ và độ phức tạp có thể khác rất nhiều.
- Không tự có phép **xóa cạnh bất kỳ** trong đồ thị hiện tại chỉ vì có thể truy vấn lịch sử.

Ví dụ, nếu thêm `(0,1)`, rồi `(1,2)`, rồi `(0,2)`, sau đó xóa `(1,2)`, trạng thái đồ thị còn các cạnh `(0,1)` và `(0,2)`. **Đó không phải** phiên bản trước khi `(1,2)` được thêm vì phiên bản ấy chưa có `(0,2)`.

Persistence giải quyết **quản lý phiên bản**; động học xóa cạnh cần thông tin cạnh còn hoạt động và cơ chế xác định liên thông tương ứng.

## 26. Các lỗi có thể phá rollback mà khó phát hiện

| Lỗi | Vì sao sai | Cách phòng tránh |
|---|---|---|
| `find` nén đường, nhưng chỉ log thay đổi của `union` | Rollback không khôi phục các nút bị nén qua ranh giới nhóm cũ | Không nén, hoặc log đầy đủ mọi ghi vào `parent` |
| Nối `parent[y]=x` thay vì nối hai **gốc** | Có thể phá bất biến rừng và gây khó undo | Gọi `find` cho hai đầu trước |
| Quên log `old_size` của gốc giữ lại | Sau undo, size vẫn tính các phần tử đã tách | Lưu size cũ trước khi tăng |
| Quên log `old_total`/min/OR | Phân hoạch đúng nhưng metadata sai | Log mọi trường được sửa |
| `union` cùng gốc vẫn giảm `components` | Số nhóm sai và rollback không nhất quán | No-op khi hai gốc bằng nhau |
| Pop no-op nhưng lại tăng `components` | Tạo nhóm “ma” | Chỉ hoàn tác những thay đổi thực |
| Rollback các bản ghi không theo LIFO | Các phụ thuộc root/size có thể không còn hợp lệ | Chỉ rollback về checkpoint trên stack |
| Dùng checkpoint từ nhánh lịch sử đã bỏ | Số độ dài có thể trùng nhưng trạng thái khác | Quản lý checkpoint theo DFS có cấu trúc |
| Quên rollback khi rời một nhánh DFS | Cạnh/quan hệ của nhánh trước rò sang nhánh sau | Chụp ngay đầu, rollback trước khi return |
| Chụp checkpoint sau các phép hợp muốn hoàn tác | Rollback không gỡ những phép hợp đó | Chụp trước khi sửa |
| Coi rollback là xóa cạnh tùy ý | Cạnh khác có thể tạo đường thay thế | Dùng mô hình thời gian/offline hoặc dynamic connectivity |
| Không có ID cạnh trong đa đồ thị | Không biết bản sao nào bị xóa | Gán ID riêng cho mỗi cạnh |
| Khoảng sống dùng `[l,r]` thay vì `[l,r)` | Cạnh còn hiệu lực tại lúc đã bị xóa | Quy ước rõ và kiểm thử biên |
| Trộn history theo số lệnh với history theo số union thành công | Checkpoint/undo lệch số lượng | Chọn một chính sách, xử lý sentinel nhất quán |
| Không hoàn tác cập nhật thuộc tính phần tử | `total` và dữ liệu gốc lệch sau rollback | Đưa cập nhật thuộc tính vào nhật ký |
| Giả định thread-safe do `find` không ghi | `union` và `rollback` vẫn ghi nhiều mảng | Đồng bộ/điều phối truy cập |

## 27. Kiểm thử biên và tính đúng đắn

Một bộ test rollback nên có ít nhất:

- **Không phần tử** (`n=0`): không có chỉ số hợp lệ; `snapshot()=0`, `rollback(0)` hợp lệ.
- **Một phần tử** (`n=1`): `union(0,0)` là no-op, không thay log.
- **Hai nhóm khác nhau:** union thành công, size và số nhóm cập nhật đúng.
- **Union trùng:** không cộng size hoặc total lần hai.
- **Snapshot lồng nhau:** rollback mốc trong rồi mốc ngoài đều phục hồi đúng.
- **Tạo nhánh mới sau rollback:** không mang theo quan hệ từ nhánh đã bỏ.
- **Hợp ngược thứ tự tham số:** tie-break có thể đổi root, nhưng phân hoạch đúng.
- **Trọng số âm hoặc bằng 0:** phép gộp tổng và hoàn tác phải đúng.
- **Chỉ số âm và vượt n:** cần báo lỗi, không dùng `parent[-1]` của Python.
- **Checkpoint lớn hơn history hiện tại:** phải từ chối.
- **Metadata mở rộng:** hoàn tác đúng tất cả trường bị sửa.
- **Segment tree:** truy vấn ngay trước và sau thời điểm xóa phải khác nếu cạnh là cầu.
- **Cạnh song song:** xóa một bản sao không được làm mất kết nối nếu còn bản sao khác.
- **Khuyên:** `union(u,u)` không thay phân hoạch; nếu đếm cạnh, khuyên vẫn là cạnh thật.

### Test bất biến bằng tái dựng nhóm

Trên n nhỏ, kiểm tra:

```text
roots = { find(x) : x in 0..n-1 }

len(roots) == components

for each root r:
    size[r] == số x có find(x) == r
    total[r] == tổng trọng số của những x đó
```

Có thể thêm một mô hình tham chiếu chậm: lưu một **bản sao danh sách nhãn nhóm** tại mỗi checkpoint cho n nhỏ, rồi đối chiếu `same(x,y)` sau rollback. Các kiểm tra như thế chủ đích tốn `O(n^2)` hoặc hơn nhưng có ích trong unit test, không cần chạy trong vòng truy vấn sản xuất.

## 28. Tự kiểm tra kiến thức có lời giải

**Câu 1.** Rollback DSU thêm thao tác gì so với DSU chuẩn?

**Đáp án:** `snapshot()` để lấy checkpoint và `rollback(cp)` để phục hồi những thay đổi **đã xảy ra sau checkpoint** theo thứ tự ngược.

**Câu 2.** Rollback một đoạn lịch sử có giống xóa cạnh `(u,v)` bất kỳ khỏi đồ thị không?

**Đáp án:** **Không.** Các cạnh khác có thể duy trì liên thông và phép xóa có thể không tương ứng duy nhất với một thay đổi union.

**Câu 3.** Tại sao `find` của rollback DSU cổ điển thường không nén đường?

**Đáp án:** Nén có thể sửa nhiều `parent[x]`; nếu chỉ log thay đổi union, rollback sẽ không khôi phục được mọi con trỏ đã sửa.

**Câu 4.** Có thể dùng path compression với rollback khi ghi log mọi thay đổi không?

**Đáp án:** **Có về mặt kỹ thuật**, nhưng phải log các phép ghi trong `find`, hoàn tác chúng đúng thứ tự và phân tích lại thời gian/bộ nhớ. Không được tự nhận chặn khấu hao của DSU chuẩn vẫn giữ nguyên.

**Câu 5.** Không nén đường, union by size cho `find` worst-case bao nhiêu?

**Đáp án:** **`O(log n)`**, vì mỗi lần độ sâu một nút tăng do union, kích thước nhóm chứa nó ít nhất gấp đôi.

**Câu 6.** Một phép `union` thành công trong lớp Python của bài sửa những trường nào?

**Đáp án:** `parent[child]`, `size[root]`, `total[root]` và `components`; nhật ký ghi đủ dữ liệu để phục hồi các trường ấy.

**Câu 7.** Khi `union(x,y)` phát hiện hai gốc bằng nhau, lớp ví dụ có đẩy lịch sử không?

**Đáp án:** **Không**, vì không có thay đổi nào. Nếu giao diện khác undo theo số lệnh, có thể dùng sentinel no-op nhưng phải thiết kế nhất quán.

**Câu 8.** `snapshot()` trong cài đặt này trả gì?

**Đáp án:** **Độ dài stack history** tại thời điểm gọi.

**Câu 9.** `rollback(cp)` với k bản ghi cần pop có chi phí bao nhiêu?

**Đáp án:** **`O(k)`**, vì mỗi bản ghi khôi phục số hằng trường trong `O(1)`.

**Câu 10.** Nếu snapshot ở history dài 1, tiếp theo có thêm hai union thành công, rollback về 1 phải pop mấy bản ghi?

**Đáp án:** **Hai** bản ghi, theo thứ tự ngược lúc tạo.

**Câu 11.** Trong ví dụ sáu phần tử, rollback về `cp_b=3` sau năm union thành công cho còn bao nhiêu nhóm?

**Đáp án:** **Ba** nhóm: `{0,1,2,3}`, `{4}` và `{5}`.

**Câu 12.** Nếu `total[root]` không được khôi phục khi rollback, hậu quả gì?

**Đáp án:** Nhóm có thể đã tách nhưng tổng vẫn chứa phần tử của nhóm cũ, nên truy vấn tổng sai dù kết quả `same` có thể đúng.

**Câu 13.** Rank hoặc size của một nút không còn là gốc có thể dùng như thông tin nhóm hiện tại không?

**Đáp án:** **Không.** Với metadata nhóm, trước hết gọi `find(x)` rồi đọc tại gốc trả về.

**Câu 14.** Vì sao checkpoint bằng số 3 không phải ID bền vững cho một phiên bản?

**Đáp án:** Sau rollback rồi tạo nhánh mới, stack có thể lại dài 3 nhưng chứa **những thay đổi khác**. Số 3 không xác định duy nhất một trạng thái trong mọi nhánh.

**Câu 15.** Khi duyệt DFS các phương án, snapshot nên đặt trước hay sau các union cục bộ?

**Đáp án:** **Trước** những union cần bỏ khi rời nhánh; sau đó rollback về mốc ấy.

**Câu 16.** Segment tree thời gian gán một khoảng hoạt động `[l,r)` vào bao nhiêu nút?

**Đáp án:** **`O(log T)`** nút khi T là số thời điểm và dùng phân tách khoảng chuẩn.

**Câu 17.** Tại thời điểm `t=r`, một cạnh sống trong `[l,r)` còn hoạt động không?

**Đáp án:** **Không**. Khoảng nửa mở chỉ bao gồm l tới r−1.

**Câu 18.** Vì sao rollback sau khi rời nút segment tree là bắt buộc?

**Đáp án:** Để quan hệ thuộc riêng khoảng thời gian của nhánh đó không **rò sang nhánh kế tiếp**.

**Câu 19.** Trong ví dụ thời gian `a:[0,4), b:[2,8), c:[6,10)`, `connected(0,2)` tại t=3 và t=5 lần lượt là gì?

**Đáp án:** **True ở t=3** vì a và b còn hoạt động; **False ở t=5** vì a đã bị xóa và c chưa xuất hiện.

**Câu 20.** Cùng ví dụ, `connected(1,2)` tại t=7 và t=9 lần lượt là gì?

**Đáp án:** **True ở t=7** nhờ b hoặc đường qua a/c tùy tập cạnh đang hoạt động; cụ thể b trực tiếp nối 1–2. **False ở t=9** vì b đã hết hiệu lực và chỉ còn c nối 0–2, đỉnh 1 cô lập.

**Câu 21.** Một thuật toán segment tree + rollback dùng K khoảng cạnh, T thời điểm và Q truy vấn trên n đỉnh có chặn thời gian tham khảo nào?

**Đáp án:** **`O(n+T+(K log T+Q) log n)`** khi dùng union by size không nén và mỗi truy vấn liên thông được trả bằng `same`.

**Câu 22.** Vì sao `history` đồng thời của rollback DSU trên n phần tử chỉ có tối đa `n-1` bản ghi union thành công?

**Đáp án:** Mỗi union thành công giảm số nhóm đúng một; không thể giảm từ n nhóm xuống dưới một nhóm nếu n dương. Sau rollback, các bản ghi đã pop không còn trong stack.

**Câu 23.** Nếu có cạnh song song cùng hai đỉnh, xóa một cạnh có chắc tách thành phần không?

**Đáp án:** **Không.** Cạnh song song khác vẫn có thể nối hai đỉnh; cần quản lý cạnh bằng ID hoặc số lượng.

**Câu 24.** Có nên dùng rollback DSU thay cho fully dynamic connectivity trực tuyến khi truy vấn tương lai chưa biết không?

**Đáp án:** **Không mặc định.** Rollback phù hợp với lịch sử theo stack và offline; xóa cạnh trực tuyến tùy ý trong đồ thị tổng quát cần thuật toán động chuyên dụng hoặc cách tính lại.

**Câu 25.** Nếu metadata lưu min và OR, có thể undo bằng “trừ kết quả nhóm con” sau union không?

**Đáp án:** **Không tổng quát.** Min và OR không có phép nghịch đảo đơn giản cho từng đóng góp. Nên lưu giá trị cũ của các trường đã sửa.

**Câu 26.** Phép `find` có path halving có phải thao tác chỉ đọc không?

**Đáp án:** **Không.** Nó sửa các ô `parent` khi rút ngắn đường, nên cũng cần ghi log nếu một rollback muốn phục hồi chính xác trạng thái trước truy vấn.

## Ghi nhớ

- **Rollback DSU** khôi phục **một đoạn lịch sử theo LIFO**, không phải phép xóa cạnh tùy ý hay tách nhóm tổng quát.
- Thiết kế phổ biến là **union by size/rank không path compression**. Khi đó `find` không ghi; mỗi union thành công sửa số hằng trường và chỉ cần một bản ghi nhỏ để undo.
- **`find`/`union` có `O(log n)` worst-case**, `snapshot()` `O(1)` và rollback k thay đổi `O(k)`. Không áp chặn Ackermann ngược của DSU có nén đường một cách máy móc.
- **Path compression/halving/splitting** có thể sửa nhiều cha trong `find`. Chỉ log những thay đổi của union có thể gây **sai phân hoạch khi rollback**; nếu muốn nén, phải ghi log và phân tích riêng đầy đủ.
- **Snapshot thường chỉ là độ dài history**, không phải ID phiên bản bền vững khi đã rollback rồi rẽ nhánh khác. Luôn quản lý checkpoint theo nhánh hợp lệ.
- Nếu cập nhật `size`, `total`, min/max, cờ, số cạnh hoặc thuộc tính phần tử, cần **rollback tất cả metadata đã đổi**, kể cả thay đổi không dẫn đến union.
- Với **liên thông động offline**, xác định khoảng sống cạnh `[l,r)`, gán cạnh vào **cây đoạn thời gian**, hợp trên đường DFS tới lá rồi **rollback khi rời nhánh**. Nếu phải xóa cạnh **trực tuyến tùy ý**, cần thuật toán dynamic connectivity hoặc giải pháp dựng lại phù hợp.

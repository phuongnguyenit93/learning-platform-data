# Mô hình I/O và đơn vị truyền dữ liệu theo khối

## 1. Vấn đề: một phần tử rất nhỏ vẫn có thể cần đọc cả khối

Cho một tệp chứa hàng trăm triệu bản ghi. Người dùng muốn tìm một bản ghi theo mã, quét toàn bộ tệp để tính tổng, hoặc sắp xếp tệp theo thời gian. Trong mô hình cấu trúc dữ liệu cơ bản, một phép đọc `A[i]` thường được tính là một thao tác `O(1)`. Nhưng khi `A` nằm trên SSD hoặc HDD và không đủ chỗ trong RAM, một lần đọc `A[i]` có thể phải **chuyển một khối dữ liệu lớn chứa phần tử đó** vào RAM.

Giả sử mỗi bản ghi chiếm `100 byte`, một khối I/O mô hình chứa `40` bản ghi:

```text
Một khối trên bộ nhớ ngoài:
+---------------------------------------------------------+
| record 0 | record 1 | ... | record 39                  |
+---------------------------------------------------------+
                       40 bản ghi

Muốn đọc record 17 khi khối chưa ở RAM:
    Đọc khối chứa record 17 -> vào buffer RAM
    Sau đó mới lấy record 17 trong buffer.
```

Nếu tiếp theo cần record `18`, nó có thể nằm trong **cùng khối đã nạp** và không cần thêm I/O. Nếu nhảy tới record ở một khối khác, có thể phải đọc thêm một khối nữa.

Điểm chính của chương **Dữ liệu ngoài bộ nhớ** là: **một phép truy cập logic vào phần tử không đồng nghĩa một phép chuyển vật lý duy nhất của phần tử ấy**. Thuật toán tốt phải tận dụng dữ liệu đã nằm trong block, thay vì thường xuyên đọc các block mới.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nêu đúng các giả định của **mô hình bộ nhớ ngoài hai tầng** (*external-memory / I/O model*).
2. Dùng nhất quán `N`, `M`, `B` và phân biệt bản ghi, byte, cache line, trang ảo và block I/O.
3. Phân tích **số lần truyền khối** cho quét tuần tự, truy cập ngẫu nhiên, tìm kiếm và sắp xếp.
4. Phân biệt **cache hit/miss** với **đọc/ghi block** trong mô hình; hiểu ảnh hưởng của buffer pool, khối bẩn và flush.
5. Tính chính xác số block chạm tới khi một khoảng dữ liệu **không bắt đầu đúng ranh giới khối**.
6. Hiểu vì sao B-tree/B+ tree và external merge sort khác với thuật toán chỉ tối ưu số phép toán CPU.
7. Đọc và suy luận các cận `O(N/B)`, `O(\log_B N)` và `O((N/B)\log_{M/B}(N/B))` theo **đúng giả định**.
8. Thực hành bằng một bộ mô phỏng I/O lý tưởng hóa có LRU buffer bằng Python.
9. Nhận biết khi nào mô hình số khối chưa đủ và cần đo thêm latency, bandwidth, queue depth, page cache, durability.

Bài thuộc học phần **Cấu trúc dữ liệu**, vốn xây nền tảng qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, đồng thời rèn luyện cách phân tích bất biến, thời gian và bộ nhớ để chọn biểu diễn phù hợp. Ở đây, trọng tâm là **chi phí đưa dữ liệu từ thiết bị lưu trữ vào bộ nhớ trong**.

## 2. Định nghĩa mô hình I/O hai tầng

Mô hình external memory chuẩn giản lược hệ thống thành hai tầng:

```text
          BỘ NHỚ TRONG (internal memory)
               RAM / fast memory
            chứa tối đa M phần tử
                       ^
                       |  Chuyển từng block B phần tử
                       v
          BỘ NHỚ NGOÀI (external memory)
                 SSD / HDD
            chứa tập dữ liệu N phần tử
```

Các ký hiệu được chọn **thống nhất theo số phần tử**:

| Ký hiệu | Ý nghĩa | Đơn vị trong bài |
|---|---|---|
| `N` | Kích thước dữ liệu cần xử lý | Số phần tử/bản ghi |
| `M` | Số phần tử chứa được trong vùng RAM dành cho thuật toán | Số phần tử |
| `B` | Số phần tử nằm trong một block được chuyển | Số phần tử/block |
| `N/B` | Số block xấp xỉ của dữ liệu | Số block |
| `M/B` | Số block vừa trong RAM | Số block |
| `K` | Số phần tử phải xuất ra của một truy vấn | Số phần tử |

Các giả định thông dụng:

- `B\ge1`, `M\ge B`, và thường xét miền không suy biến với **nhiều block có thể ở RAM**, chẳng hạn `M\ge2B`.
- **Một I/O** là chuyển **một block** giữa hai tầng; thường đếm cả đọc và ghi, nếu không nói khác.
- Một phần tử đã nằm trong RAM có thể được xử lý bằng các phép toán bộ nhớ trong mà **không làm tăng bộ đếm I/O**.
- Nội dung dữ liệu trên bộ nhớ ngoài không thể được sử dụng trong phép toán CPU nếu block tương ứng chưa được đưa vào RAM.
- Cấu trúc dữ liệu có thể chọn cách bố trí phần tử thành các block và thứ tự đọc/ghi chúng.

Mô hình bỏ qua nhiều chi phí khác để tập trung vào số **block transfer**. Nó là một công cụ phân tích thuật toán, không phải mô phỏng chính xác trình điều khiển SSD/HDD hoặc bộ quản lý trang của hệ điều hành.

### Đọc một block và ghi một block đều được tính

Nếu thuật toán đọc một block, sửa nội dung trong RAM rồi ghi block đó trở lại thiết bị:

```text
read block -> 1 I/O
compute     -> 0 I/O trong mô hình
write block -> 1 I/O
Tổng        -> 2 I/O
```

Nếu block vẫn đang có trong RAM ở thời điểm đọc lại, việc đọc lại phần tử trong block **không tốn I/O mới**. Không được cộng một I/O cho mỗi lần đọc `A[i]` trong khi `A[i]` đang ở buffer.

## 3. RAM model và I/O model trả lời hai câu hỏi khác nhau

Xét tìm kiếm tuyến tính trong một tệp `N` phần tử:

```text
for each record in file:
    if record.key == target:
        return record
```

Trong **RAM model**:

- Mỗi lần truy cập/so sánh thường là `O(1)`.
- Kịch bản xấu nhất kiểm tra `N` phần tử → `O(N)` phép toán.

Trong **I/O model**:

- Một block chứa `B` phần tử.
- Có thể đọc một block rồi so sánh cả `B` phần tử khi nó còn trong RAM.
- Nếu phải quét toàn bộ dữ liệu lạnh, cần khoảng `\lceil N/B\rceil` block reads.

Vì vậy:

\[
\boxed{\text{CPU work}=\Theta(N),\qquad
\text{block I/O}=\Theta\!\left(\left\lceil N/B\right\rceil\right)}
\]

cho trường hợp quét toàn bộ `N` bản ghi và mỗi block chứa tối đa `B` bản ghi.

Hai biểu thức **không mâu thuẫn**: chúng đo **hai tài nguyên khác nhau**.

### Một thuật toán ít so sánh có thể vẫn gây nhiều I/O

Tìm kiếm nhị phân dùng `O(\log N)` lần so sánh thay vì quét `O(N)` phần tử. Nhưng nếu mỗi bước nhảy tới một block xa và block chưa ở RAM, số I/O có thể gần số bước so sánh.

Ngược lại, một thuật toán duyệt nhiều phần tử **liền nhau trong cùng block** có thể làm nhiều phép toán CPU nhưng ít I/O hơn.

### Không có nghĩa CPU work luôn miễn phí ngoài đời

I/O model **cố ý** không tính chi phí tính toán trong RAM. Khi dữ liệu đã cache, CPU work có thể là yếu tố chính của wall-clock time. Vì vậy trong dự án thật nên phân tích **cả hai**: số phép toán nội bộ và số block I/O.

## 4. Các đơn vị truyền dữ liệu dễ bị nhầm

Từ phần cứng tới API phần mềm, từ “khối” có thể mang nhiều nghĩa:

| Đơn vị | Tầng thường gặp | Ví dụ để hình dung | Vai trò |
|---|---|---|---|
| **Cache line** | CPU cache | `64 byte` trên nhiều CPU | Nạp/đẩy dữ liệu qua cache |
| **Virtual memory page** | MMU / hệ điều hành | `4 KiB` trang cơ sở ở nhiều hệ | Ánh xạ và bảo vệ bộ nhớ |
| **File-system block** | Hệ thống file | Có thể `4 KiB` | Tổ chức dữ liệu và cấp phát |
| **Logical sector** | Giao diện thiết bị lưu trữ | Có thể `512 B` hoặc `4 KiB` | Đơn vị địa chỉ hóa thiết bị |
| **I/O request** | API/driver/storage stack | Có thể `4 KiB`, `64 KiB` hoặc hơn | Đơn vị yêu cầu đọc/ghi thực tế |
| **Block `B` trong mô hình** | Phân tích thuật toán | `B` *phần tử/block* | Đơn vị chuyển được giả định để đếm I/O |

**Không được mặc định các kích thước này bằng nhau.** Mô hình có thể chọn block bằng một trang dữ liệu của B+ tree, một request đọc tuần tự, hoặc một mức trừu tượng phù hợp với bài toán. CPU cache line không tự động là một I/O disk và một page fault không luôn tương ứng một block transfer theo mô hình.

### KiB và KB

- `1\text{ KiB}=1024\text{ byte}`.
- `1\text{ KB}=1000\text{ byte}` theo tiền tố thập phân.
- `4\text{ KiB}=4096\text{ byte}`.

Khi chuyển từ byte sang số bản ghi/block, ghi rõ hệ đơn vị và **trừ dung lượng metadata** nếu có header, pointer hay slot directory.

## 5. Quy đổi từ kích thước block tính bằng byte sang `B` phần tử

Giả sử một trang lưu trữ có:

- Kích thước vật lý/logical page `P=4096` byte.
- Header và metadata chiếm `H=128` byte.
- Bản ghi kích thước cố định `s=120` byte, không cho cắt qua hai trang.

Dung lượng payload:

\[
P-H=4096-128=3968\text{ byte}.
\]

Số bản ghi tối đa mỗi trang:

\[
\boxed{B=\left\lfloor\frac{P-H}{s}\right\rfloor
=\left\lfloor\frac{3968}{120}\right\rfloor
=33\text{ bản ghi}.}
\]

Với `N=1{,}000{,}000` bản ghi, số trang ít nhất nếu xếp kín theo giả định là:

\[
\boxed{\left\lceil\frac{1{,}000{,}000}{33}\right\rceil
=30{,}304\text{ trang}.}
\]

### Vì sao không dùng `4096/120≈34.13` rồi lấy `B=34`?

Vì phép chia ấy **bỏ quên header `128` byte**, làm trang chứa 34 bản ghi chiếm:

\[
34\times120+128=4208>4096\text{ byte}.
\]

Một trang như vậy không hợp lệ. Nếu bản ghi có kích thước biến thiên, cần xét thêm fragmentation, slot directory, overflow pages, compression, alignment hoặc chính sách bố trí của engine.

### Khi `N` và `B` được tính bằng byte

Nếu chọn `N_{\text{bytes}}` là tổng số byte và `B_{\text{bytes}}` là số byte chuyển mỗi I/O, có thể dùng:

\[
\left\lceil\frac{N_{\text{bytes}}}{B_{\text{bytes}}}\right\rceil
\]

cho vùng liên tiếp, căn chỉnh phù hợp. Nhưng **không được lấy số bản ghi `N` chia trực tiếp cho số byte `B_{\text{bytes}}`**.

## 6. Truy vấn một vị trí: từ chỉ số phần tử đến số hiệu block

Giả sử dữ liệu là một mảng phẳng, mỗi block chứa đúng `B` phần tử, chỉ số từ `0`:

\[
\boxed{block(i)=\left\lfloor\frac{i}{B}\right\rfloor,}
\]

\[
\boxed{offset(i)=i\bmod B.}
\]

Với `B=4`:

```text
block 0        block 1        block 2
+--+--+--+--+ +--+--+--+--+ +--+--+--+--+
|0 |1 |2 |3 | |4 |5 |6 |7 | |8 |9 |10|11|
+--+--+--+--+ +--+--+--+--+ +--+--+--+--+
```

Phần tử `i=9`:

```text
block(9)  = 9 // 4 = 2
offset(9) = 9 % 4  = 1
```

Nếu block `2` chưa có trong buffer RAM, cần nạp block này rồi truy cập phần tử thứ `1` trong block. Nếu block `2` đã ở buffer thì không cần I/O mới.

### Chỉ số ảo trên file không tự chứng minh có một I/O

Với B-tree, hash file hoặc record có độ dài biến thiên, vị trí của một khóa không nhất thiết suy ra từ `i//B`. Công thức trên chỉ đúng cho **mảng bản ghi cố định được xếp tuần tự theo chỉ số**. Một index cần đọc các node/page của riêng nó trước khi xác định vị trí bản ghi.

## 7. Một đoạn dữ liệu không căn theo biên block

Nếu cần đọc `q` phần tử liên tiếp, bắt đầu tại chỉ số `s` của mảng phẳng, và `q>0`, số block bị chạm tới là:

\[
\boxed{
\#blocks(s,q)
=\left\lfloor\frac{s+q-1}{B}\right\rfloor
-\left\lfloor\frac{s}{B}\right\rfloor+1.
}
\]

Tương đương:

\[
\boxed{
\#blocks(s,q)=
\left\lceil\frac{(s\bmod B)+q}{B}\right\rceil.
}
\]

Nếu `q=0`, cần `0` block.

### Ví dụ `B=4`

```text
Chỉ số:        0 1 2 3 | 4 5 6 7 | 8 9 10 11
block:             0          1          2

Đọc s=3, q=6:
    các chỉ số 3,4,5,6,7,8
    chạm block 0,1,2 -> 3 block.

Đọc s=4, q=6:
    các chỉ số 4,5,6,7,8,9
    chạm block 1,2 -> 2 block.
```

Dù hai truy vấn đều lấy **6 phần tử**, truy vấn bắt đầu ở biên block có thể cần ít hơn một block.

### Phân biệt “số block bị chạm” và “I/O thực sự phát sinh”

Nếu các block đã ở RAM cache, số I/O đọc thiết bị thực tế có thể **bằng 0**. Công thức chỉ xác định **bao nhiêu block chứa dữ liệu cần truy cập**, trong giả định layout liên tiếp. Để tính I/O thật cần thêm **trạng thái cache** và đường truy cập.

## 8. Cold buffer và warm buffer: vì sao cùng thuật toán có số I/O khác nhau?

Xét một buffer RAM có thể giữ `C=\lfloor M/B\rfloor` block.

- **Cold buffer:** ban đầu chưa có block của workload; lần đọc đầu phải nạp từ bộ nhớ ngoài.
- **Warm buffer:** có một số block liên quan đã được nạp từ thao tác trước.

Giả sử tệp có `5` block:

```text
block: 0 1 2 3 4
```

Nếu buffer đủ giữ cả `5` block:

1. Quét lần đầu: cần **5 block reads**.
2. Quét lần hai ngay sau đó: có thể **0 reads mới**.

Nếu buffer chỉ giữ `2` block, trong mô hình LRU và quét lặp `0,1,2,3,4`:

1. Lần đầu: **5 reads**.
2. Lần hai: mỗi block đã bị thay thế trước khi đến lượt dùng → có thể lại **5 reads**.

Vì thế, phát biểu “quét `N` phần tử tốn `\Theta(N/B)` I/O” thường ngầm xét **một lần quét dữ liệu chưa nằm sẵn trong RAM**, hoặc một bài toán buộc phải chuyển tất cả block từ ngoài vào trong.

### Phải tính cả chỗ chứa dữ liệu khác

RAM dành cho buffer không nhất thiết bằng toàn bộ RAM vật lý: thuật toán còn cần stack, heap, bảng chỉ mục, kết quả trung gian và runtime overhead. Trong I/O model, `M` phải là phần bộ nhớ **khả dụng thực sự theo giả định**.

## 9. Đọc block và ghi block: dirty pages, write-back và read-modify-write

Giả sử một trang dữ liệu đã nằm trong RAM buffer:

```text
Disk block -> RAM buffer
                 |
           sửa record 5
                 |
            block dirty
                 |
          ghi lại block
                 v
           Disk block mới
```

Trong mô hình đơn giản:

- Đọc block lạnh: **1 read I/O**.
- Sửa một record trong block đã có: **0 I/O ngay tại thời điểm sửa**.
- Ghi block dirty trở lại bộ nhớ ngoài: **1 write I/O**.

Nếu sửa nhiều record thuộc **cùng block** trước khi flush, có thể chỉ cần **một write** cho bản cuối cùng của block, thay vì ghi riêng cho từng record.

### Write miss

Nếu chỉ muốn sửa một record nhỏ mà block chưa ở RAM, cách triển khai **read-modify-write** có thể phải đọc block trước, sửa record rồi ghi cả block trở lại: ít nhất **một read và một write** theo chính sách giả định.

Một cơ chế ghi khác (append-only log, out-of-place update, write buffer, device sub-block write) có thể đổi mẫu I/O; không được áp một quy tắc read-modify-write cho mọi engine lưu trữ.

### Dirty eviction

Khi buffer đầy và phải đẩy một block **dirty** ra, hệ thống phải bảo đảm nội dung đã sửa không bị mất: ghi xuống tầng ngoài hoặc giữ một bản ghi bền vững/thay thế theo giao thức tương ứng. Trong mô hình buffer pool đơn giản, eviction dirty block tính **1 write I/O**, còn eviction clean block **không cần ghi lại**.

### Durability không chỉ là bộ đếm write

Trong hệ thống thật, việc hệ điều hành chấp nhận một write không tự động chứng minh dữ liệu đã an toàn khi mất điện. Các yêu cầu giao dịch cần thêm WAL, flush/fsync, barriers và thiết bị bảo đảm thứ tự ghi phù hợp. I/O model chỉ đếm chuyển khối, **không mô tả đầy đủ durability semantics**.

## 10. Vì sao đọc tuần tự thường hiệu quả hơn đọc ngẫu nhiên?

Mô hình block transfer cơ bản tính **mỗi block bằng một đơn vị I/O**. Tuy nhiên, trên thiết bị thật, hai pattern có thể có thời gian rất khác nhau:

**Đọc tuần tự:**

```text
block 0 -> block 1 -> block 2 -> block 3 -> ...
```

**Đọc ngẫu nhiên:**

```text
block 190 -> block 2 -> block 887 -> block 41 -> ...
```

Với HDD, đọc ngẫu nhiên có thể phát sinh seek và rotational latency. Với SSD, không có seek cơ học, nhưng vẫn có độ trễ request nhỏ, giới hạn IOPS, hàng đợi, firmware/FTL, tác động garbage collection và giao diện.

### Cách ước lượng thời gian bổ sung cho I/O model

Một mô hình thô cho `q` yêu cầu I/O **không chồng lấp** có thể là:

\[
\boxed{T_{\mathrm{I/O}}\approx
q\cdot L+\frac{\text{tổng byte truyền}}{\text{băng thông hiệu dụng}}}
\]

trong đó `L` là overhead/latency cố định trung bình mỗi yêu cầu, còn băng thông phải được đo theo workload. Đây không phải đẳng thức chung: **queue depth, read-ahead, caching và mức song song** có thể làm các yêu cầu chồng lấp hoặc được gộp lại.

### I/O model giúp được gì dù bỏ qua địa chỉ vật lý?

Một thuật toán làm `100` lần chuyển block thường có ít cơ hội trả giá I/O hơn một thuật toán làm `10{,}000` lần chuyển block có mọi điều kiện khác như nhau. Nhưng nếu `100` lần ấy là yêu cầu ngẫu nhiên đồng bộ còn `10{,}000` lần là yêu cầu lớn tuần tự và chồng lấp tốt, **thời gian thực tế vẫn cần đo**.

Vì thế cần phân biệt:

1. **Số block transfer** (thước đo tiệm cận của thuật toán).
2. **Mẫu địa chỉ, kích thước request và concurrency** (thước đo hành vi thiết bị).
3. **Wall-clock time** (kết quả đo cuối cùng).

## 11. SCAN: quét toàn bộ tệp theo block

Với `N` bản ghi xếp liên tiếp, mỗi block chứa `B` bản ghi, số block cần chạm:

\[
\boxed{\operatorname{Scan}(N)=
\left\lceil\frac NB\right\rceil}
\]

cho một bản dữ liệu bắt đầu đúng biên và phần block cuối có thể chưa đầy.

Trong phân tích tiệm cận với `N\ge B`:

\[
\boxed{\operatorname{Scan}(N)=\Theta(N/B).}
\]

Ở miền `N<B`, vẫn cần **1 block** nếu dữ liệu không rỗng; cách viết có dấu trần `\lceil N/B\rceil` tránh vô tình nói chi phí nhỏ hơn một thao tác I/O.

### Tại sao đây là một cận dưới khi phải xem mọi phần tử?

Nếu thuật toán phải kiểm tra **từng phần tử** và không có thống kê/chỉ mục dùng để bỏ qua dữ liệu, mỗi block chứa tối đa `B` phần tử. Để xem cả `N` phần tử cần đọc ít nhất `\lceil N/B\rceil` block **từ ngoài vào**, trong trạng thái các block chưa nằm trong RAM.

Một thuật toán quét đơn giản đọc mỗi block đúng một lần đạt cận đó, nên tối ưu theo **số block reads** trong giả định ấy.

### Ví dụ

`N=1{,}000{,}000`, `B=1000`:

\[
\operatorname{Scan}(N)=1000\text{ block reads}.
\]

Nếu thuật toán còn tạo một tệp kết quả khác chứa đúng `N` phần tử, phải tính thêm **khoảng 1000 block writes**, không được gộp cả hai vào con số 1000.

## 12. Chi phí đọc–xử lý–ghi một tệp lớn

Giả sử muốn biến đổi từng bản ghi:

```text
Input:  [a0 a1 a2 ... a(N-1)]
Output: [f(a0) f(a1) ... f(a(N-1))]
```

Để tạo một tệp mới trên thiết bị ngoài, dưới giả định:

- Mỗi bản ghi đầu vào/đầu ra có cùng kích thước cố định.
- Dữ liệu được tổ chức theo block `B` phần tử.
- Buffer RAM đủ cho ít nhất một block input và một block output.
- Input chưa có trong RAM và output cần thực sự ghi ra ngoài.

Ta cần xấp xỉ:

\[
\boxed{
\lceil N/B\rceil\text{ reads}
+\lceil N/B\rceil\text{ writes}
=2\lceil N/B\rceil\text{ I/O}.
}
\]

**Nếu chỉ muốn tính tổng mà không xuất N phần tử**, chi phí ghi đầu ra có thể là `O(1)` hoặc bằng 0 trong mô hình tùy cách trả kết quả. **Nếu dữ liệu đã nằm trong RAM**, phần reads từ thiết bị có thể bằng 0.

### Quét theo khối không làm giảm số phép biến đổi

Hàm `f` vẫn cần áp dụng `N` lần. Ta tối ưu **đường truyền dữ liệu**, không biến `N` phép tính thành `N/B` phép tính CPU.

## 13. Truy cập rời rạc: tình huống một block cho mỗi yêu cầu

Giả sử một file có rất nhiều block, buffer RAM chỉ giữ được ít block và cần đọc các vị trí:

```text
i0, i1, i2, ..., i(Q-1)
```

Nếu những vị trí liên tiếp nằm ở các block khác nhau và block cũ bị đẩy khỏi buffer trước khi tái sử dụng, có thể xảy ra:

\[
\boxed{\text{I/O reads}\approx Q.}
\]

Trong khi một lượt quét toàn bộ `N` bản ghi có chi phí cỡ `N/B` block. Vì thế, với cùng số phần tử được kiểm tra, mẫu truy cập rải rác có thể tốn **nhiều block reads hơn**.

### Nhưng `Q` không phải một định luật

Ví dụ:

- Hai vị trí khác nhau có thể nằm trong **cùng block**.
- Một block có thể đã ở RAM hoặc OS page cache.
- Bộ đệm đủ lớn có thể giữ các block dùng lại.
- Reordering/batching nhiều yêu cầu có thể giảm I/O thực.

Do đó, **cần biết trạng thái bộ đệm và thứ tự truy cập** mới tính chính xác số lần truyền, chứ không lấy số lần gọi `get(i)` làm số I/O mặc định.

## 14. Đổi thứ tự yêu cầu để gom truy cập cùng block

Giả sử người dùng cần đọc `Q` bản ghi nhưng **không yêu cầu trả kết quả theo đúng thứ tự đọc**. Ta có thể:

1. Tính số block chứa mỗi bản ghi.
2. Gom yêu cầu theo block.
3. Đọc mỗi block cần thiết một lần nếu đủ bộ đệm.
4. Xử lý mọi yêu cầu thuộc block đó, sau đó chuyển sang block tiếp theo.

Ví dụ `B=4`:

```text
Yêu cầu gốc:       [0, 8, 1, 9, 2, 10]
Block tương ứng:   [0, 2, 0, 2, 0,  2]

Gom theo block:
    block 0: index 0,1,2
    block 2: index 8,9,10
```

Nếu buffer chỉ giữ một block:

- Xử lý theo thứ tự gốc: có thể cần **6 block reads**.
- Xử lý sau khi gom: cần **2 block reads**.

Nếu kết quả phải được trả theo thứ tự yêu cầu gốc, vẫn có thể gắn **ID yêu cầu** rồi sắp lại kết quả trong RAM/bộ nhớ ngoài. Tuy nhiên, chính bước phân nhóm/sắp xếp yêu cầu cũng có chi phí:

- Khi `Q` nhỏ và vừa RAM: overhead có thể chấp nhận.
- Khi `Q` rất lớn và vượt RAM: sắp xếp các yêu cầu có thể cần **external sorting**.

Không nên khẳng định gom block luôn tốt nếu chi phí tổ chức yêu cầu lớn hơn phần I/O tiết kiệm.

## 15. Tìm kiếm nhị phân trên file sắp thứ tự: RAM nhanh chưa chắc ít I/O

Giả sử `N` bản ghi có khóa tăng trong một mảng phẳng trên SSD. Tìm kiếm nhị phân:

```text
lo = 0, hi = N-1
while lo <= hi:
    mid = (lo+hi)//2
    đọc A[mid]
    so sánh khóa
    chọn nửa còn lại
```

Số lần so sánh là:

\[
O(\log_2 N).
\]

Nhưng các vị trí `mid` ở các bước đầu thường cách nhau **rất xa** trong file, có thể thuộc các block khác nhau. Khi các block chưa ở RAM, chi phí I/O của cách tìm ấy có thể là:

\[
\boxed{O(\log N)\text{ block I/O}}
\]

trong mô hình ngây thơ một block mỗi lần đọc `A[mid]`.

### Ví dụ `N\approx10^6`

Tìm kiếm nhị phân có khoảng `20` bước. Nếu mỗi bước cần một block mới thì cần khoảng `20` block reads, dù thuật toán chỉ kiểm tra khoảng 20 phần tử.

### Có thể ít hơn nhờ cache

Khi khoảng tìm kiếm cuối nằm trong cùng block hoặc các block trên đường tìm đã được cache, số I/O thực có thể thấp hơn số bước. Trong một layout mảng thường, **các lần nhảy đầu tiên** mới là nguồn I/O ngẫu nhiên tốn kém; không nên coi mọi truy vấn luôn đúng 20 I/O.

Đây là động lực để thiết kế **nút chỉ mục nhiều khóa cùng một block**, thay vì chỉ tối ưu số phép so sánh.

## 16. B-tree/B+ tree: thay binary branching bằng block branching

Một **B-tree** hoặc **B+ tree** cân bằng có thể đặt nhiều khóa phân cách/con trỏ trong một node page. Đọc một page cho phép chọn **một trong nhiều nhánh**, khác với BST nhị phân chỉ chọn trái/phải.

```text
               [ 20 | 40 | 60 ]       (một trang chỉ mục)
                /     |     |    \
          page A   page B page C  page D

Mỗi lần nạp trang gốc cho phép chọn một trong 4 nhánh.
```

Gọi `F` là số nhánh tối đa/hiệu dụng của node trong:

\[
\boxed{h=O(\log_F N)}
\]

trong những giả định cân bằng và độ lấp đầy phù hợp.

Nếu mỗi block chứa cỡ `B` khóa/con trỏ theo mô hình phần tử kích thước cố định, ta thường có `F=\Theta(B)`, dẫn đến:

\[
\boxed{T_{\mathrm{lookup}}=O(\log_B N)\text{ I/O}}
\]

hoặc dạng `O(1+\log_B N)` để nêu rõ chi phí tối thiểu một lần nạp trong trường hợp lạnh và `N` nhỏ.

### Chỗ dễ nhầm nhất: `B` phần tử không phải `B` byte

Nếu page dài `4096 byte`, một key chiếm `16 byte` và con trỏ `8 byte`, một node **không chứa 4096 khóa con**. Fanout còn bị giới hạn bởi header, slot directory, fill factor và cách tổ chức. Chỉ khi `B` đã được định nghĩa là **số mục phù hợp trong block**, các cận `\log_B N` mới mang nghĩa như ký hiệu thường dùng.

### Một phần cây thường ở RAM

Trang gốc và những node gần gốc hay được truy cập có thể nằm trong buffer pool. Khi đó số **I/O thực** để lookup có thể thấp hơn chiều cao cây. Công thức logarithmic mô tả **cận trong mô hình truyền khối**, không phải số đọc thiết bị bắt buộc cho mỗi truy vấn.

## 17. Truy vấn khoảng trong B+ tree: tìm đầu đoạn rồi quét các lá

Giả sử một B+ tree tổ chức các khóa tăng dần; các trang lá chứa dữ liệu hoặc tham chiếu bản ghi và có liên kết logic để đọc theo thứ tự khóa.

Với truy vấn:

```text
SELECT * WHERE 100 <= key <= 999;
```

thuật toán điển hình:

1. Đi từ gốc tới trang lá chứa khóa bắt đầu `100`.
2. Tìm vị trí đầu tiên có khóa `\ge100` trong trang lá đó.
3. Duyệt các bản ghi theo thứ tự trong trang và các trang lá tiếp theo.
4. Dừng khi gặp khóa `>999`.

Nếu truy vấn trả `K` bản ghi, một trang chứa cỡ `B` bản ghi phù hợp, và các trang lá được đọc theo thứ tự:

\[
\boxed{
T_{\mathrm{range}}=
O\left(1+\log_B N+\left\lceil\frac{K}{B}\right\rceil\right)
\text{ I/O}
}
\]

trong mô hình lý tưởng với các giả định về fill factor và thứ tự lá.

### Vì sao có cả `\log_B N` và `K/B`?

- `\log_B N` là chi phí **tìm trang đầu tiên**.
- `K/B` là chi phí **xuất/duyệt các trang chứa kết quả**.

Nếu `K` rất lớn, phần quét chiếm ưu thế. Nếu `K` chỉ vài bản ghi, chi phí tìm điểm bắt đầu chiếm ưu thế.

### Liên kết lá không bảo đảm các trang sát nhau vật lý

Các lá có thể được phân bố rải rác do cấp phát/xóa/tách trang. Vì vậy, quét theo **thứ tự khóa logic** không luôn đạt tốc độ tuần tự tối đa của thiết bị. Để mô hình hóa thời gian thật, còn cần xem layout trang, buffer pool, read-ahead và phân mảnh.

### Tệp đã sắp nhưng không có B+ tree?

Một mảng phẳng sắp thứ tự có thể tìm `lo` bằng binary search rồi quét đoạn liên tiếp. Nếu nhiều truy vấn và dữ liệu lạnh, một cây nhiều nhánh giúp giảm số I/O tìm điểm bắt đầu; nhưng khi tệp nhỏ/vừa RAM, lựa chọn đơn giản hơn cũng có thể hiệu quả.

## 18. Băm trên bộ nhớ ngoài: kỳ vọng ít I/O cho tìm khóa chính xác

Một **hash table trên đĩa** có thể ánh xạ khóa tới **bucket/page**. Nếu hàm băm phân bố tốt và bucket có đủ chỗ, tìm khóa chính xác thường chỉ cần:

1. Xác định bucket (từ hàm băm và thông tin directory phù hợp).
2. Đọc page bucket nếu chưa ở RAM.
3. Tìm khóa bên trong page đã được nạp.

Trong các giả định tải hợp lý, directory truy cập được và số overflow buckets được kiểm soát:

\[
\boxed{T_{\mathrm{exact\,lookup}}=O(1)\text{ I/O kỳ vọng}.}
\]

### Các giả định quan trọng

- Directory hoặc metadata có thể phải đọc từ đĩa, nếu không ở RAM.
- Va chạm hash/overflow chain làm tăng số page cần đọc.
- Load factor và chính sách mở rộng ảnh hưởng chi phí cập nhật.
- Kẻ tấn công hoặc dữ liệu có phân bố không phù hợp có thể làm hiệu năng xấu hơn.
- Đọc bản ghi lớn nằm ngoài page index có thể cần thêm I/O.

### Hash index kém thuận lợi cho range scan

Nếu dữ liệu phân phối bằng hàm băm, các khóa `100,101,\ldots,999` thường không nằm trong những bucket **liền kề theo thứ tự giá trị**. Vì vậy, băm thường phù hợp với **exact-match lookup**, nhưng **B+ tree** thuận tiện hơn cho **truy vấn đoạn có thứ tự**.

Đây là ví dụ chọn cấu trúc theo workload: không phải cấu trúc có số I/O kỳ vọng thấp nhất cho truy vấn điểm cũng tối ưu cho mọi loại truy vấn.

## 19. Vì sao sắp xếp một tệp vượt RAM cần nhiều lượt đọc/ghi?

Giả sử tệp chứa `N` bản ghi và RAM chỉ chứa được `M` bản ghi, với `N>M`.

**Sắp xếp trong RAM** đòi đưa mọi phần tử vào RAM cùng lúc nếu dùng một lời gọi sort truyền thống trên toàn bộ tập. Khi không thể làm vậy, ta dùng **external merge sort**:

```text
                TỆP CHƯA SẮP
                      |
            Đọc từng nhóm <= M mục
                      |
                Sắp trong RAM
                      |
              Ghi thành các RUN
          /-----------+-----------\
        run 0        run 1       run 2 ... (đã sắp)
          \-----------+-----------/
                      |
          MULTIWAY MERGE theo block
                      |
               TỆP ĐÃ SẮP
```

### Giai đoạn 1 — tạo run

Mỗi lượt:

1. Đọc tối đa `M` bản ghi từ tệp đầu vào.
2. Sắp xếp chúng **trong RAM**.
3. Ghi chúng thành một **run đã sắp** trên bộ nhớ ngoài.

Số run ban đầu:

\[
\boxed{R=\left\lceil\frac NM\right\rceil.}
\]

Với cùng kích thước bản ghi và khối, giai đoạn này đọc toàn `N` và ghi toàn `N`:

\[
\boxed{2\left\lceil\frac NB\right\rceil\text{ block I/O}}
\]

trong mô hình cơ bản, bỏ qua các trường hợp block cuối và overhead tệp.

### Bản ghi có thể được sắp trong RAM mà không tăng I/O disk

Sắp `M` phần tử bằng quicksort/mergesort/heap sort vẫn tốn CPU work và RAM work, nhưng **không bị cộng thêm block I/O** nếu toàn bộ các phần tử đang nằm trong bộ nhớ trong.

Đây chính là điểm mô hình tách **I/O complexity** khỏi **time complexity**.

## 20. Gộp run: cần bao nhiêu buffer block?

Để gộp `F` run đã sắp cùng lúc, cách đơn giản giữ:

- Một **input block buffer** cho mỗi run.
- Một **output block buffer** cho tệp được ghi.
- Một số metadata nhỏ, chẳng hạn phần tử đầu mỗi run trong heap.

Nếu RAM chứa được `C=\lfloor M/B\rfloor` block và tạm bỏ chi phí metadata:

\[
\boxed{F\le C-1=\left\lfloor\frac MB\right\rfloor-1.}
\]

Đây là **fan-in** của một lượt gộp theo mô hình một buffer vào/run và một buffer ra.

Ví dụ:

```text
RAM chứa 8 block:

Input buffers:
  Run0 Run1 Run2 Run3 Run4 Run5 Run6

Output buffer:
  Out

Fan-in tối đa: 7 run.
```

Với `R` run ban đầu, sau mỗi pass gộp tối đa `F` run làm một:

```text
R_0 = R
R_1 = ceil(R_0/F)
R_2 = ceil(R_1/F)
...
cho đến khi còn 1 run.
```

Số pass gộp sau giai đoạn tạo run (khi `R>1` và `F\ge2`):

\[
\boxed{
\left\lceil\log_F R\right\rceil.
}
\]

### Không được quên output buffer

Nếu `M/B=8`, không được kết luận “gộp cùng lúc 8 run” khi thuật toán còn cần **một block output**. Trong cách tổ chức này, chỉ còn **7 input buffers**. Một triển khai thực có thể cần thêm vùng heap, read-ahead, buffer giải mã; vì vậy fan-in hiệu dụng có thể nhỏ hơn.

### Nếu `M/B\le2`?

Với một input buffer/run và một output buffer, khi chỉ có hai block RAM sẽ không thể thực hiện **2-way merge** theo cách trên. Cần điều chỉnh giả định, cấp thêm RAM hoặc dùng một thuật toán khác. Các công thức log có cơ số `M/B` thường ngầm yêu cầu miền không suy biến đủ lớn.

## 21. Bài toán số: 12 run ban đầu và hai pass gộp

Chọn các tham số nhất quán:

\[
N=9600,\qquad M=800,\qquad B=100
\]

(đều theo **số bản ghi**, `B=100` bản ghi/block).

### Bước 1 — số block dữ liệu

\[
\frac NB=\frac{9600}{100}=96\text{ block}.
\]

### Bước 2 — tạo run

Mỗi run chứa tối đa `800` bản ghi = `8` block:

\[
R=\frac{9600}{800}=12\text{ run}.
\]

Tạo run đọc `96` block và ghi `96` block:

\[
96+96=192\text{ I/O}.
\]

### Bước 3 — fan-in gộp

RAM chứa:

\[
\frac MB=\frac{800}{100}=8\text{ block}.
\]

Dành một block output, có `F=7` input buffers:

```text
Sau pass gộp 1:
    12 run -> ceil(12/7)=2 run.

Sau pass gộp 2:
    2 run -> 1 run (đã sắp toàn bộ).
```

Mỗi pass gộp đọc toàn `96` block và ghi toàn `96` block: `192` I/O.

### Kết quả nếu ghi tệp kết quả ra bộ nhớ ngoài

```text
Tạo run:       192 I/O
Merge pass 1:  192 I/O
Merge pass 2:  192 I/O
------------------------
Tổng:          576 block I/O
```

\[
\boxed{T_{\mathrm{sort}}=576\text{ block transfers}}
\]

trong mô hình các run và file kết quả được đọc/ghi đầy đủ mỗi pass, bỏ qua metadata và các block chưa đầy.

**Lưu ý:** nếu kết quả gộp cuối được **tiêu thụ trực tiếp bởi phép tính khác** thay vì ghi tệp đã sắp lên bộ nhớ ngoài, có thể tiết kiệm **lượt ghi cuối**. Ngược lại, nếu phải bảo đảm durability với log/fsync, số request và thời gian thực có thể khác đáng kể.

## 22. Công thức tổng quát cho external merge sort

Trong mô hình so sánh với bộ nhớ trong `M` và block `B`, độ phức tạp I/O sắp xếp tổng quát, với các giả định chuẩn về miền tham số, thường biểu diễn:

\[
\boxed{
\operatorname{Sort}(N)=
\Theta\left(
\frac NB\left(1+\log_{M/B}\frac NB\right)
\right).
}
\]

Một cách viết khác là:

\[
\Theta\left(\frac NB\log_{M/B}\frac NB\right)
\]

khi xét miền `N` đủ lớn để phần logarithmic chi phối và `M/B>1`.

### Giải thích hai nhân tử

- `N/B`: mỗi lượt phải truyền cỡ `N/B` block.
- `\log_{M/B}(N/B)`: số lượt chia/gộp khi bộ nhớ trong chứa được cỡ `M/B` block và gộp nhiều run cùng lúc.

### Công thức không được áp dụng máy móc ở mọi `N`

- Nếu `N\le M`, dữ liệu có thể vừa RAM: đọc một lượt, sắp trong RAM, rồi ghi nếu cần; `O(\lceil N/B\rceil)` I/O.
- Nếu `B>M`, giả định “giữ một block” không hợp lý trong mô hình này.
- Nếu `M/B` quá nhỏ để thực hiện multiway merge, phải xử lý trường hợp đặc biệt.
- Nếu data đã có trong buffer, hoặc output không cần ghi ra thiết bị, bộ đếm I/O thực thay đổi.
- Nếu dữ liệu có cấu trúc đặc biệt, key có miền nhỏ hoặc đã gần sắp, có thuật toán khác tận dụng tính chất đó; công thức trên là chuẩn cho **sắp xếp so sánh tổng quát** theo những giả định thông thường.

### Không trộn “số pass” với “số I/O”

Trong ví dụ phần 21, có **3 lượt quét toàn bộ tệp theo nghĩa tạo run + hai merge passes**. Mỗi lượt đầy đủ là `96` reads + `96` writes. Vì vậy tổng là `3\times192=576` block transfers, **không phải 3 hoặc 96**.

## 23. Cận dưới từ số bản ghi: một khối phục vụ nhiều yêu cầu

Giả sử có `K` kết quả bắt buộc phải xuất ra bộ nhớ ngoài, kích thước mỗi bản ghi bằng nhau, mỗi block output chứa `B` kết quả.

Ít nhất cần:

\[
\boxed{\left\lceil\frac KB\right\rceil\text{ block writes}}
\]

nếu kết quả phải được lưu ở một tệp mới trên thiết bị, không tính các ràng buộc bổ sung.

Tương tự, để kiểm tra toàn bộ `N` phần tử của một tập lạnh mà chưa có metadata giúp bỏ qua, ít nhất phải đọc:

\[
\boxed{\left\lceil\frac NB\right\rceil\text{ block reads}.}
\]

### Cận dưới không áp dụng khi không cần xem mọi bản ghi

Nếu có index trả lời “tệp có bao nhiêu bản ghi?” từ một trang metadata, ta không cần quét toàn tệp. Nếu có tổng hợp theo khối được cập nhật đúng, có thể tính nhiều truy vấn bằng các tổng hợp ấy.

Vì vậy, phát biểu cận dưới phải có **điều kiện thông tin mà thuật toán cần đọc/ghi**. Không được nói mọi truy vấn trên `N` phần tử đều mất `\Omega(N/B)` I/O.

## 24. Giữ khối lâu hơn: blocking, batching và buffer reuse

Một chiến lược thiết kế external-memory thường có ba bước:

1. **Nạp khối** đang cần vào buffer RAM.
2. **Xử lý nhiều mục cùng khối** trước khi thay nó.
3. Nếu sửa, **ghi theo lô** khi cần, thay vì ghi mỗi mục ngay.

### Ví dụ cập nhật nhiều record cùng trang

Giả sử có `100` cập nhật rơi vào cùng một trang và trang ban đầu lạnh:

**Cách A — không có cache/batching:** mỗi cập nhật có thể read-modify-write một lần → tới `100` reads + `100` writes.

**Cách B — giữ trang trong RAM:** đọc một lần → sửa `100` mục trong RAM → ghi một lần → **1 read + 1 write**.

Điều này giải thích vì sao **gom cập nhật theo page** có thể tiết kiệm rất nhiều block I/O.

### Tính đúng dữ liệu vẫn là bắt buộc

Không thể tự do hoãn mọi lần ghi nếu ứng dụng có yêu cầu giao dịch, khôi phục sau sự cố hoặc nhiều người dùng cùng cập nhật. Buffering phải đi cùng chính sách logging, transaction isolation và flush phù hợp; mô hình block I/O không tự bảo đảm các thuộc tính đó.

## 25. Một thuật toán I/O-efficient thường chọn bố trí dữ liệu trước

Cùng một tập bản ghi có thể lưu theo hai cách:

**Layout A — các mục liên quan nằm gần nhau:**

```text
block 0: khách hàng vùng A
block 1: khách hàng vùng A
block 2: khách hàng vùng B
block 3: khách hàng vùng B
```

**Layout B — các mục rải rác:**

```text
block 0: A B A B
block 1: B A B A
block 2: A B A B
block 3: B A B A
```

Nếu phần lớn truy vấn chỉ xem vùng A, layout A có thể đọc ít block hơn do **clustering**. Nếu truy vấn phân bố hoàn toàn ngẫu nhiên theo nhiều tiêu chí, bố trí khác có thể phù hợp hơn.

### Dữ liệu có thứ tự và chỉ mục

Một B+ tree cung cấp thứ tự truy vấn theo key. Nhưng nếu payload nằm ở một file khác theo thứ tự ngẫu nhiên, việc lấy từng payload từ record ID có thể tạo thêm I/O. Vì vậy các hệ quản trị cơ sở dữ liệu phải cân nhắc:

- **Clustered index:** tổ chức dữ liệu chính gần theo một thứ tự.
- **Secondary index:** tìm khóa phụ rồi tra vị trí dữ liệu.
- **Covering index:** chứa đủ trường cần trả để tránh lookup bảng gốc khi phù hợp.

Chi phí một index lookup không tự động bằng **chi phí lấy toàn bộ bản ghi**.

## 26. Bộ nhớ trong có hạn: không thể giữ mọi block nóng

Giả sử tệp có `D=N/B` block, nhưng RAM dành cho thuật toán chỉ giữ `C=M/B` block, với `D\gg C`.

Nếu workload liên tục đi qua nhiều hơn `C` block giữa hai lần tái sử dụng một block, block đó có thể bị **evict** trước khi được dùng lại.

### Ví dụ tuần tự lặp trong buffer nhỏ

```text
Cache LRU chứa 2 block.
Truy cập: 0,1,2,3,4, 0,1,2,3,4
```

Mỗi lần đọc một block mới đẩy block lâu dùng nhất. Sau chuỗi `0,1,2,3,4`, cache chỉ giữ `3,4`. Bắt đầu lượt thứ hai ở `0` sẽ đẩy `3`; tới `1` lại đẩy `4`. Tổng cộng **10 miss**, không có hit trong ví dụ.

Nếu cache giữ được cả `5` block, chuỗi ấy chỉ **5 miss đầu**, rồi **5 hit sau**.

### Thuật toán block-aware

Một thuật toán được thiết kế theo block có thể:

- Quét tuần tự để tránh dùng lại block đã bị đẩy.
- Chọn kích thước nhóm xử lý vừa trong RAM.
- Tái sử dụng các khối đang mở (ví dụ input buffers của merge sort).
- Hạn chế số khối sống đồng thời.

Nhưng cache replacement thật có thể không phải LRU; CPU cache, OS page cache và buffer pool của database có các mục đích/chính sách khác nhau. Mô hình LRU trong bài chỉ minh họa cơ chế tái sử dụng.

## 27. Cache-aware và cache-oblivious khi thiết kế thuật toán I/O

### Cache-aware

Thuật toán **cache-aware** có thể sử dụng `M` và `B` để chọn kích thước buffer hoặc cách chia nhóm.

Ví dụ:

- External merge sort dùng `M/B` để quyết định số input buffers.
- B+ tree đặt nhiều key/con trỏ vào một page gần kích thước block.
- Bài toán xử lý ma trận chọn tile vừa cache/buffer theo khả năng phần cứng.

Ưu điểm: có thể tối ưu trực tiếp cho cấu hình mục tiêu. Hạn chế: nếu cấu hình khác đi nhiều, tham số tối ưu cần điều chỉnh.

### Cache-oblivious

Thuật toán **cache-oblivious** không cần biết trực tiếp `M,B` trong mã, nhưng có cách tổ chức dữ liệu và phân chia công việc tạo tính cục bộ ở nhiều kích thước block.

Ví dụ ý tưởng:

```text
Dữ liệu lớn
   |
   +-- Chia thành phần trái/phải
          |
          +-- Tiếp tục chia đệ quy
                 |
                 +-- Một vùng con có thể vừa một tầng cache
```

**Không phải mọi thuật toán đệ quy đều cache-oblivious tối ưu.** Phải có chứng minh về cách bố trí dữ liệu, trật tự truy cập và giả định mô hình (ví dụ *tall-cache assumption* trong một số kết quả).

### Phân tích theo nhiều tầng

Hệ thống thật có thanh ghi, L1/L2/L3, RAM, OS page cache và thiết bị lưu trữ. Một thuật toán tối ưu số block transfer **RAM↔SSD** chưa chắc tối ưu CPU cache miss **L1↔RAM**. Cần đo workload cụ thể, dù ý tưởng tăng tính cục bộ thường hữu ích ở nhiều tầng.

## 28. Đọc/ghi song song: mô hình một I/O khác thời gian thực có queue depth

Mô hình cổ điển thường giả sử **mỗi I/O truyền một block** giữa hai tầng. Nhưng SSD và controller hiện đại có thể xử lý **nhiều yêu cầu đang chờ**.

### Queue depth

Nếu chỉ có một request đang chạy, CPU/ứng dụng có thể phải chờ độ trễ của request đó. Nếu có nhiều request độc lập và thiết bị có các kênh xử lý song song, thông lượng tổng có thể tăng.

Ví dụ minh họa:

```text
Một luồng đồng bộ:
   read A -> wait -> read B -> wait -> read C

Nhiều yêu cầu độc lập:
   submit A, submit B, submit C
   -> thiết bị xử lý chồng lấp một phần
   -> nhận kết quả
```

**Số block I/O vẫn là 3** trong hai cách theo mô hình; thời gian thực có thể khác do chồng lấp. Ngược lại, yêu cầu quá nhiều làm hàng đợi dài và p95/p99 latency tăng.

### Mô hình song song nhiều thiết bị

Nếu có `D` thiết bị độc lập và dữ liệu được phân phối đều, một biến thể parallel-disk model có thể xem **một vòng I/O song song** chuyển tới `D` block, một block mỗi thiết bị:

\[
\text{scan rounds}\approx\left\lceil\frac{N}{D B}\right\rceil
\]

trong điều kiện phân phối dữ liệu, cân bằng tải và lịch truy cập cho phép song song hiệu quả.

**Không được tự lấy công thức một đĩa rồi chia `D` trong mọi hệ thống:** nếu mọi block cần đọc đều nằm trên một thiết bị, hoặc bị ràng buộc tuần tự bởi phụ thuộc dữ liệu, không thể tận dụng đầy đủ `D`.

## 29. Những giới hạn cần nhớ khi dùng số lần block transfer

I/O model **không trực tiếp tính**:

- **Thời gian seek/rotational latency** trên HDD.
- **IOPS** và các giới hạn queue/controller của SSD.
- **Compression** và cách dữ liệu giải nén thành bản ghi.
- **Chi phí CPU** khi sort, tính hash, giải mã hoặc so sánh khóa.
- **Kích thước dữ liệu biến thiên** và fragmentation nếu `B` được lấy cố định quá đơn giản.
- **Hệ thống file**, metadata, journaling, WAL, fsync, consistency/durability.
- **Bộ nhớ đệm nhiều tầng**, TLB/page faults, CPU cache miss.
- **Yêu cầu đa luồng**, lock contention hoặc mạng.

### Vậy khi nào số I/O có giá trị?

Đặc biệt hữu ích khi:

1. `N` vượt xa RAM và cần đọc nhiều trang từ thiết bị.
2. Workload cần hàng triệu thao tác, một thay đổi nhỏ trong số I/O/truy vấn sẽ tích lũy lớn.
3. Phải chọn layout/index: sorted file, hash bucket, B+ tree, LSM-tree.
4. Phải sắp xếp hoặc join dữ liệu lớn theo nhiều lượt.
5. Muốn so sánh thiết kế **độc lập tương đối với tốc độ CPU**.

Không nên vứt bỏ mô hình chỉ vì nó giản lược: cần hiểu **nó đo được gì và chưa đo được gì**.

## 30. Mã Python: mô phỏng buffer pool có LRU và block bẩn

Để kiểm tra trực giác về **cache hit, đọc block lạnh, ghi dirty page và flush**, ta cài một **bộ mô phỏng khối**.

Các giả định:

- `disk` ở đây là một **danh sách Python đóng vai trò dữ liệu ngoài**; không đọc/ghi thiết bị thật.
- Mỗi block chứa tối đa `B` phần tử.
- Buffer RAM chứa tối đa `C` block.
- Nếu cache đầy thì thay thế **Least Recently Used (LRU)**.
- Nếu block bị thay thế đang dirty, ghi nó về `disk` trong mô phỏng.
- Việc ghi một phần tử làm bẩn block; `flush()` ghi tất cả block dirty còn trong buffer.
- Mọi lần **cache miss** dẫn tới một block read; không có read-ahead hoặc I/O concurrency.

Chép nguyên khối mã sau thành một tệp Python để tự chạy:

```python
from collections import OrderedDict


class BlockBuffer:
    """
    Mô phỏng two-level I/O model, KHÔNG truy cập SSD/HDD thật.

    disk: danh sách phần tử biểu diễn backing storage.
    cache: LRU các block đã nạp trong RAM.
    """

    def __init__(
        self,
        data: list[int],
        block_size: int,
        capacity_blocks: int,
    ) -> None:
        if block_size < 1 or capacity_blocks < 1:
            raise ValueError("block_size và capacity_blocks phải >= 1")

        self.disk = list(data)
        self.block_size = block_size
        self.capacity_blocks = capacity_blocks
        self.cache: OrderedDict[int, list[int]] = OrderedDict()
        self.dirty: set[int] = set()
        self.read_ios = 0
        self.write_ios = 0

    def _store(self, block_id: int, page: list[int]) -> None:
        """Ghi nguyên block về bộ nhớ ngoài mô phỏng."""
        start = block_id * self.block_size
        self.disk[start:start + len(page)] = page
        self.write_ios += 1

    def _page(self, block_id: int) -> list[int]:
        """Lấy block trong RAM; miss thì nạp và có thể evict."""
        if block_id in self.cache:
            self.cache.move_to_end(block_id)
            return self.cache[block_id]

        if len(self.cache) == self.capacity_blocks:
            old_id, old_page = self.cache.popitem(last=False)
            if old_id in self.dirty:
                self._store(old_id, old_page)
                self.dirty.remove(old_id)

        start = block_id * self.block_size
        page = self.disk[start:start + self.block_size]
        self.read_ios += 1
        self.cache[block_id] = page
        return page

    def read(self, index: int) -> int:
        if not 0 <= index < len(self.disk):
            raise IndexError(index)

        block_id, offset = divmod(index, self.block_size)
        return self._page(block_id)[offset]

    def write(self, index: int, value: int) -> None:
        if not 0 <= index < len(self.disk):
            raise IndexError(index)

        block_id, offset = divmod(index, self.block_size)
        self._page(block_id)[offset] = value
        self.dirty.add(block_id)

    def flush(self) -> None:
        for block_id in list(self.dirty):
            self._store(block_id, self.cache[block_id])
        self.dirty.clear()

    def io_counts(self) -> tuple[int, int]:
        return self.read_ios, self.write_ios
```

### Hai tầng “disk” và “cache” là các đối tượng Python

Chương trình mô phỏng có thể **bản thân nằm hoàn toàn trong RAM thật**, nên các bộ đếm chỉ là **số block transfer lý tưởng** theo quy tắc đã đặt, không phải đo page fault hoặc I/O OS. Điều đó là chủ ý để học thuật toán mà không bị tốc độ thiết bị và cache hệ thống làm nhiễu.

### Đọc đúng vị trí trong block

Với `index=9`, `block_size=4`:

```text
divmod(9,4) -> (2,1)
```

Hàm `read(9)` nạp block `2` nếu chưa có, rồi trả phần tử offset `1`.

### Vì sao khi ghi không cập nhật disk ngay?

Hàm `write` sửa dữ liệu trong **RAM buffer** và ghi nhận block dirty. Chỉ `flush` hoặc eviction dirty mới làm tăng `write_ios`. Điều này mô phỏng **write-back buffering**.

Với một đối tượng thật chứa dữ liệu quan trọng, còn cần quản lý lỗi I/O, đồng bộ và durability; những cơ chế ấy không nằm trong mã giảng dạy.

## 31. Ví dụ mô phỏng: working set và ghi một lần cho nhiều thay đổi

Sử dụng lớp `BlockBuffer` vừa định nghĩa:

```python
buffer = BlockBuffer(
    data=list(range(12)),
    block_size=4,
    capacity_blocks=2,
)

# Lần quét 1 qua 12 phần tử = 3 block.
assert [buffer.read(i) for i in range(12)] == list(range(12))
print(buffer.io_counts())  # (3, 0)

# Buffer chỉ giữ 2/3 block; lần quét lại vẫn miss cả 3.
assert [buffer.read(i) for i in range(12)] == list(range(12))
print(buffer.io_counts())  # (6, 0)

# Block 0 đã bị đẩy; đọc index 0 cần nạp lại block 0.
assert buffer.read(0) == 0
print(buffer.io_counts())  # (7, 0)

# Sửa index 0 trong block 0 đang nằm trong buffer:
buffer.write(0, 99)
assert buffer.read(0) == 99
print(buffer.io_counts())  # (7, 0): chưa ghi ra disk.

buffer.flush()
print(buffer.io_counts())  # (7, 1)
assert buffer.disk[0] == 99
```

### Thay đổi capacity

```python
large = BlockBuffer(
    data=list(range(12)),
    block_size=4,
    capacity_blocks=3,
)

for _ in range(2):
    for i in range(12):
        large.read(i)

print(large.io_counts())  # (3, 0)
```

Vì `large` giữ được cả `3` block, lượt quét thứ hai chỉ hit cache.

### Đọc ngẫu nhiên lặp cùng nhóm block

```python
small = BlockBuffer(
    data=list(range(20)),
    block_size=4,
    capacity_blocks=2,
)

positions = [0, 4, 8, 12, 16] * 2
for index in positions:
    small.read(index)

print(small.io_counts())  # (10, 0)
```

Mỗi vị trí thuộc một block khác nhau. Vì buffer chỉ giữ hai block, tất cả mười lần truy cập trong chuỗi gây miss theo LRU.

### Bộ mô phỏng bỏ qua những gì?

- Tốc độ thực tế của SSD/HDD và chênh lệch random–sequential.
- Các lớp cache CPU/TLB/OS page cache khác.
- Tối ưu hóa prefetch, batching và xử lý I/O song song.
- Chi phí giải mã bản ghi, cấp phát và copy byte.
- Hệ thống file, transaction/WAL, durability hoặc lỗi thiết bị.

Vì vậy, kết quả được dùng để **kiểm tra logic số block** chứ không để dự báo **ms** hoặc **GB/s** của một máy cụ thể.

## 32. Mã Python: đếm block của một đoạn và pass external merge sort

Đây là các phép tính số học có thể dùng để tự kiểm tra bài tập.

```python
def ceil_div(a: int, b: int) -> int:
    if a < 0 or b <= 0:
        raise ValueError("Cần a >= 0 và b > 0")
    return (a + b - 1) // b


def blocks_for_range(start: int, count: int, B: int) -> int:
    """Số block chạm tới đoạn count phần tử từ chỉ số start."""
    if start < 0 or count < 0 or B <= 0:
        raise ValueError("Tham số không hợp lệ")
    if count == 0:
        return 0
    first = start // B
    last = (start + count - 1) // B
    return last - first + 1


def sort_block_io(
    N: int, M: int, B: int
) -> tuple[int, int, int]:
    """
    Trả (initial_runs, merge_passes, total_block_IO).

    Giả sử:
      - File input ban đầu ở bộ nhớ ngoài.
      - Tạo mỗi run bằng đọc và ghi.
      - Mỗi merge pass đọc + ghi toàn bộ file.
      - Output cuối cùng phải ghi ra bộ nhớ ngoài.
      - Một input buffer/run và một output buffer.
      - N,M,B cùng đơn vị phần tử.
    """
    if N < 0 or B < 1 or M < B:
        raise ValueError("Cần N >= 0 và M >= B >= 1")
    if N == 0:
        return 0, 0, 0

    runs = ceil_div(N, M)
    initial_runs = runs
    fanin = (M // B) - 1

    if runs > 1 and fanin < 2:
        raise ValueError("Không đủ buffer để gộp 2 run")

    merge_passes = 0
    while runs > 1:
        runs = ceil_div(runs, fanin)
        merge_passes += 1

    blocks = ceil_div(N, B)
    io_count = 2 * blocks * (1 + merge_passes)
    return initial_runs, merge_passes, io_count


assert blocks_for_range(3, 6, 4) == 3
assert blocks_for_range(4, 6, 4) == 2
assert blocks_for_range(4, 0, 4) == 0

print(sort_block_io(9600, 800, 100))
# (12, 2, 576)

print(sort_block_io(1000, 2000, 100))
# (1, 0, 20): Đọc 10 block, ghi 10 block.
```

### Vì sao kết quả `(1,0,20)` ở ví dụ cuối?

`N=1000\le M=2000`, dữ liệu có thể sắp trong RAM sau khi đọc 10 block; do yêu cầu **ghi tệp kết quả lên bộ nhớ ngoài**, cần thêm 10 block writes. Không có pass gộp.

### Cảnh báo về số block chưa đầy

Mã dùng `ceil(N/B)` cho mỗi lượt, giả định run cuối có thể xử lý bằng block chưa đầy và mỗi pass có thể ghi những block output gần kín. Với các run riêng lẻ, yêu cầu căn chỉnh và metadata của từng file có thể khiến tổng block thực tế cao hơn một chút. Khi `B`, `M` và `N` không chia hết cho nhau, mô hình trên là **ước lượng đơn giản**, không phải kế toán hệ thống file bit-perfect.

## 33. Đánh giá ngoài đời: I/O count và thời gian có thể khác nhau

Sau khi đã phân tích `O(N/B)` hoặc `O(\log_B N)`, cần kiểm tra **mô hình có khớp với workload thật hay không**.

### Dữ liệu đang nằm ở tầng nào?

```text
Ứng dụng hỏi một bản ghi.
        |
        v
Đã ở buffer pool của ứng dụng/database?
        |
  Có -> không cần đọc thiết bị.
        |
  Không -> dữ liệu file còn ở OS page cache?
                   |
           Có -> đọc từ RAM OS.
                   |
           Không -> yêu cầu I/O tới SSD/HDD.
```

CPU vẫn có thể gặp cache/TLB miss ở nhiều nhánh trên, nhưng đó **không phải cùng bộ đếm I/O thiết bị**.

### Đo cái gì?

| Phép đo | Trả lời câu hỏi |
|---|---|
| Block reads/writes của engine | Thuật toán yêu cầu bao nhiêu page từ buffer/storage manager? |
| Physical bytes read/written | Thiết bị thật truyền bao nhiêu byte? |
| IOPS | Có bao nhiêu request hoàn thành mỗi giây? |
| Average/p95/p99 latency | Yêu cầu thường và đuôi chậm kéo dài bao lâu? |
| Throughput MiB/s hoặc MB/s | Có thể chuyển tổng lượng dữ liệu nhanh tới mức nào? |
| Request size | Một I/O có phải 4 KiB, 64 KiB hay lớn hơn? |
| Queue depth / concurrency | Bao nhiêu yêu cầu được xử lý cùng lúc? |
| Page cache/buffer pool hit rate | Bao nhiêu truy cập không cần tới thiết bị? |
| CPU usage và stalls | Phần xử lý nội bộ có chi phối thời gian không? |
| Memory usage / working set | Có nguy cơ eviction/thrashing không? |

### Phân biệt cold run và warm run

Một truy vấn đầu tiên sau khi mở dữ liệu có thể phát sinh I/O, nhưng truy vấn thứ hai hit cache. Nếu chỉ benchmark lần thứ hai rồi công bố “truy vấn không bao giờ đọc đĩa” thì kết luận sai.

**Cold ở cấp nào?** CPU cache, OS page cache và buffer pool database là ba tầng khác nhau. Việc ứng dụng vừa khởi động không đảm bảo OS page cache rỗng, và việc khởi động lại ứng dụng không tự làm mất dữ liệu được cache trong kernel.

### Đừng tự ý xóa cache hệ thống trên máy đang dùng chung

Nếu cần thử nghiệm cold-cache, nên làm trong môi trường chuyên dụng có quyền và phương pháp kiểm soát phù hợp. Thao tác thay đổi cache của hệ điều hành có thể làm chậm hay ảnh hưởng dữ liệu/truy vấn của các tiến trình khác.

### Durability và số lần ghi

Một engine có thể báo “đã ghi dữ liệu vào buffer” nhưng vẫn chưa flush ra thiết bị. Nếu hệ thống yêu cầu commit bền vững, cần đo thêm WAL, fsync, journal, flush/barrier và cách thiết bị xử lý cache ghi. Mô hình `read+write=2` chỉ đếm block transfer, không đại diện toàn bộ yêu cầu bền vững.

## 34. Chọn thuật toán và layout theo loại thao tác

| Workload | Cấu trúc/chiến lược nên cân nhắc | Đặc điểm I/O nổi bật |
|---|---|---|
| Quét tất cả bản ghi một lần | File tuần tự, streaming, quét block | `\Theta(N/B)` block reads |
| Nhiều truy vấn khóa chính xác | Hash index hoặc B+ tree | Kỳ vọng `O(1)` hoặc `O(\log_B N)` theo giả định |
| Truy vấn khoảng khóa tăng dần | B+ tree / dữ liệu được sắp phù hợp | Tìm đầu đoạn + quét `K/B` trang |
| Sắp dữ liệu không vừa RAM | External merge sort | Các pass đọc–ghi tuần tự |
| Nhiều cập nhật nhỏ cùng trang | Buffering, grouping, write-back | Tránh read/write lặp cùng block |
| Cập nhật nhiều khóa rải rác | Gom cập nhật theo page; cân nhắc cấu trúc ghi theo lô | Giảm số request rời rạc và page churn |
| Ghi key/value cường độ cao | Cân nhắc LSM-tree với memtable và compaction | Đổi ghi nhỏ thành flush/merge; đánh đổi write amplification |
| Tính toán lặp trên nhiều vùng dữ liệu | Blocked/tiled algorithm | Tăng tái sử dụng dữ liệu trong RAM/cache |

### Quy trình ra quyết định

1. **Xác định mục tiêu:** lấy 1 bản ghi, lấy `K` bản ghi theo khoảng, cập nhật hay quét `N` bản ghi?
2. **Chốt đơn vị:** record, byte, page, block hay line? Đổi về cùng đơn vị trước khi dùng `B,M,N`.
3. **Xác định chỗ chứa:** `N\le M` hay `N\gg M`? Working set nóng có vừa buffer không?
4. **Phân tích chi phí I/O:** cần đọc/ghi bao nhiêu block và qua mấy pass?
5. **Đưa CPU work trở lại:** sort, giải mã, tính hash, so sánh chuỗi, copy.
6. **Xét kiểu thiết bị:** HDD hay SSD, request size, queue depth, layout/fragmentation?
7. **Đo với workload đại diện:** cold/warm, cả truy vấn điểm và range scan, đọc và ghi, thời gian trung bình và p95/p99.

### Một phép tính “ít I/O” chưa chắc có tổng chi phí nhỏ hơn

Ví dụ, một phương pháp đòi ít block reads hơn nhưng phải **giải nén dữ liệu rất nặng** có thể tốn CPU hơn. Một chỉ mục lớn giúp tìm điểm nhanh nhưng làm **ghi/cập nhật đắt hơn**. Một hệ thống batch ghi có thể tăng throughput nhưng thay đổi độ trễ và yêu cầu durability.

I/O model giúp đưa ra **lập luận ban đầu có cơ sở**, còn quyết định sản phẩm cần kết hợp mô hình với phép đo.

## 35. Những lỗi và ngộ nhận thường gặp

| Lỗi | Hậu quả | Cách tránh |
|---|---|---|
| Dùng `N` tính bằng bản ghi, `B` tính bằng byte rồi viết `N/B` | Sai đơn vị, kết quả không có nghĩa | Quy đổi `B` sang bản ghi/block hoặc `N` sang byte |
| Quên header/page metadata | Ước lượng quá số bản ghi/page | Dùng `B=\lfloor(P-H)/s\rfloor` với giả định layout rõ |
| Coi 1 block I/O = 1 phần tử | Đếm quá nhiều I/O khi quét | Đọc block rồi xử lý các phần tử trong RAM |
| Coi 1 lời gọi `read()` = 1 block I/O | Syscall, page cache và I/O vật lý không trùng 1:1 | Phân biệt API-level và device-level |
| Tính `\lceil q/B\rceil` cho mọi đoạn bất kể offset | Sai nếu đoạn lệch biên block | Dùng `\lceil((s\bmod B)+q)/B\rceil` |
| Đoạn rỗng vẫn tính 1 block | Đếm thừa | `q=0` thì 0 block |
| Coi mọi block cần chạm đều phải đọc lại | Bỏ qua cache hit | Xét cache state, working set, eviction |
| Coi mọi read vào RAM đều từ SSD/HDD | Có thể hit OS page cache | Phân biệt tầng dữ liệu |
| Đồng nhất cache line CPU với disk page | Hai tầng, đơn vị và chức năng khác nhau | Nêu đúng đơn vị |
| Mặc định mỗi lần sửa một record phải ghi ngay | Không xét buffering và dirty page | Xét write-back/flush |
| Đếm mỗi dirty write, quên read miss | Bỏ qua read-modify-write | Nêu rõ update policy |
| Quên write output của external sort | Kết quả I/O thấp hơn thực tế | Đếm read + write mỗi pass |
| Quên một output buffer khi tính fan-in | Gộp nhiều run hơn RAM cho phép | `F\le\lfloor M/B\rfloor-1` trong mô hình mẫu |
| Dùng `\log_{M/B}` khi `M/B\le1` | Cơ số log không hợp lệ | Kiểm tra miền tham số |
| Áp công thức sort lớn cho `N\le M` | Bỏ qua trường hợp dữ liệu vừa RAM | Đọc–sort trong RAM–ghi một lần |
| Gọi `O(\log_B N)` nhưng `B` là byte chưa quy đổi | Đọc sai vai trò fanout | `B` phải biểu diễn số mục/block phù hợp |
| Cho rằng B+ tree leaf links bảo đảm liền nhau vật lý | Sai về layout file thực | Phân biệt thứ tự logic và vị trí vật lý |
| Coi hash lookup luôn 1 I/O | Va chạm, directory, overflow, payload | Ghi đủ giả định và tính I/O bổ sung |
| Cho rằng càng ít I/O càng chắc nhanh hơn | I/O request còn khác latency/bandwidth/queue | Benchmark trên thiết bị mục tiêu |
| Ghi `O(N/B)` cho truy vấn chỉ hỏi một metadata | Có thể không cần quét dữ liệu | Chỉ áp cận dưới khi phải xem toàn bộ |
| Coi `M` là toàn bộ RAM máy | Còn OS, runtime, index, buffers khác | Lấy RAM khả dụng cho thuật toán |
| Tự xóa cache hệ thống để “benchmark lạnh” trên máy chung | Ảnh hưởng tiến trình khác | Dùng môi trường đo riêng |
| Cho rằng có thể đếm chính xác số device I/O từ Python list | List chỉ ở RAM, mô phỏng không đọc đĩa | Ghi rõ mô hình giả lập |
| Coi block writes đã chứng minh durability | WAL/flush/ordering còn riêng | Xác định hợp đồng bền vững |
| Quên số pass của merge sort | Đếm sai toàn bộ dữ liệu qua các lượt | Tính `R` và fan-in `F`, lặp tới 1 run |
| So sánh thuật toán chỉ theo Big-O I/O | Không đo CPU work và tail latency | Phân tích đa thước đo |

## 36. Bài tập tự kiểm tra

**Bài 1.** Mô hình external memory hai tầng gồm những tầng nào? Một lần I/O được tính theo đơn vị gì?

**Bài 2.** Phát biểu ý nghĩa và đơn vị của `N,M,B` trong bài. Điều kiện tối thiểu nào để giữ một block trong RAM?

**Bài 3.** Một page `4096 byte` có header `128 byte`, mỗi bản ghi `120 byte` và không cho bản ghi vượt trang. Tính `B` bản ghi/trang.

**Bài 4.** Với dữ liệu ở bài 3 có `1{,}000{,}000` bản ghi, ít nhất cần bao nhiêu trang nếu xếp kín như giả định?

**Bài 5.** Một mảng phẳng có `B=4` phần tử/block. Phần tử chỉ số `9` nằm ở block nào, offset nào?

**Bài 6.** Trong mảng của bài 5, đọc đoạn bắt đầu `s=3` gồm `q=6` phần tử chạm bao nhiêu block?

**Bài 7.** Nếu đoạn ở bài 6 bắt đầu tại `s=4` nhưng vẫn dài `q=6`, kết quả thay đổi ra sao?

**Bài 8.** Vì sao `\lceil q/B\rceil` có thể sai nếu đoạn không bắt đầu đúng biên block? Viết công thức đúng với `q>0`.

**Bài 9.** Một truy vấn đoạn có `q=0`. Phải tính bao nhiêu block?

**Bài 10.** Với `N=9600` phần tử, `B=100` phần tử/block, một lần quét lạnh đọc toàn bộ cần bao nhiêu block?

**Bài 11.** Nếu quét `N=9600` phần tử lạnh rồi ghi một tệp output cũng gồm `9600` phần tử cùng kích thước, cần bao nhiêu block reads và block writes?

**Bài 12.** Buffer LRU giữ 5 block; một tệp có 5 block được quét hai lần liên tiếp từ `0` đến `4`. Tổng số reads lạnh qua cả hai lượt?

**Bài 13.** Buffer LRU chỉ giữ 2 block, quét chuỗi `0,1,2,3,4,0,1,2,3,4`. Có bao nhiêu misses?

**Bài 14.** Với `B=4` và buffer một block, xử lý các chỉ số `0,8,1,9,2,10` theo đúng thứ tự có thể tốn bao nhiêu block reads? Nếu gom theo block thì sao?

**Bài 15.** Tại sao tìm kiếm nhị phân trên mảng lưu trên đĩa có thể cần `O(\log N)` I/O dù mỗi lần chỉ so sánh một khóa?

**Bài 16.** B+ tree có gì khác để đạt cận dạng `O(\log_B N)` I/O? Khi nào cần dùng cách viết `O(1+\log_B N)`?

**Bài 17.** Một truy vấn B+ tree trả `K` bản ghi nằm trên khoảng khóa liên tục. Nêu hai thành phần chính của chi phí `O(\log_B N+K/B+1)`.

**Bài 18.** Vì sao hash index phù hợp với truy vấn đúng một khóa nhưng có thể không tối ưu cho range scan?

**Bài 19.** External merge sort dùng `N=9600`, `M=800`, `B=100`. Có bao nhiêu run ban đầu và mỗi run tối đa bao nhiêu block?

**Bài 20.** Với `M=800`, `B=100` và cách tổ chức một input buffer/run + một output buffer, fan-in tối đa là bao nhiêu?

**Bài 21.** Với `12` run và fan-in `7`, cần bao nhiêu pass gộp để còn một run? Mô tả số run sau mỗi pass.

**Bài 22.** Dùng dữ liệu bài 19–21, nếu mỗi pass đọc và ghi toàn file và output cuối phải ghi ra đĩa, tổng I/O gồm cả giai đoạn tạo run là bao nhiêu?

**Bài 23.** Nếu `N=1000`, `M=2000`, `B=100`, sắp trong RAM rồi ghi kết quả ra thiết bị cần bao nhiêu block reads + writes theo mô hình?

**Bài 24.** Nếu `N=10{,}000`, `M=2000`, `B=200`, tính `R`, `F`, số pass gộp và tổng I/O đọc+ghi (input/output đều ở bộ nhớ ngoài).

**Bài 25.** Vì sao khi tính fan-in không được chỉ lấy `M/B` run đầu vào trong trường hợp cần một output buffer riêng?

**Bài 26.** Giải thích hai nhân tử `N/B` và `\log_{M/B}(N/B)` trong độ phức tạp external merge sort.

**Bài 27.** Một block đã có trong RAM buffer, thay `20` record thuộc block đó rồi flush một lần. Trong mô hình write-back đơn giản, số write I/O tối thiểu là bao nhiêu?

**Bài 28.** Buffer chỉ giữ một block. Đọc block 0 lạnh, sửa một phần tử trong block 0, rồi đọc block 1 lạnh. Trong mô hình LRU write-back, bộ đếm read I/O và write I/O là bao nhiêu?

**Bài 29.** Vì sao một Python `list` và các lần gọi `BlockBuffer.read` trong phần 30 không phản ánh I/O thiết bị thật?

**Bài 30.** Phân biệt cache line CPU, page bộ nhớ ảo và block `B` của external-memory model. Tại sao không được lấy kích thước cả ba bằng nhau mặc định?

**Bài 31.** Nêu một trường hợp có `N` bản ghi nhưng truy vấn chỉ tốn vài I/O, không phải `\Omega(N/B)`.

**Bài 32.** Khi đo một chỉ mục trên SSD, vì sao phải quan sát cả số block I/O, request size, queue depth, cold/warm cache, throughput và p95/p99 latency?

## 37. Đáp án và giải thích

**Bài 1.** Hai tầng là bộ nhớ trong (RAM/fast memory) và bộ nhớ ngoài (SSD/HDD/slow memory). Một I/O lý tưởng là truyền **một block `B` phần tử** giữa hai tầng.

**Bài 2.** `N` = số bản ghi dữ liệu, `M` = số bản ghi giữ được trong RAM dành cho thuật toán, `B` = số bản ghi/block. Cần `M\ge B` để giữ ít nhất một block; nhiều thuật toán cần vài block đồng thời.

**Bài 3.** `B=\lfloor(4096-128)/120\rfloor=\lfloor3968/120\rfloor=33` bản ghi/page.

**Bài 4.** `\lceil1{,}000{,}000/33\rceil=30{,}304` trang.

**Bài 5.** `block(9)=\lfloor9/4\rfloor=2`, `offset(9)=9\bmod4=1`.

**Bài 6.** Đoạn là các chỉ số `3,4,5,6,7,8`, chạm ba block `0,1,2`.

**Bài 7.** Đoạn `4..9` chỉ chạm block `1` và `2`, tức hai block.

**Bài 8.** Vì đoạn có thể bắt đầu giữa một block; số block đúng là `\lceil((s\bmod B)+q)/B\rceil` khi `q>0`.

**Bài 9.** `0` block; không có phần tử nào cần đọc.

**Bài 10.** `9600/100=96` block reads.

**Bài 11.** `96` block reads + `96` block writes, tổng `192` block transfers.

**Bài 12.** `5` reads lần đầu, `0` reads mới lần hai vì giữ được mọi block; tổng `5`.

**Bài 13.** `10` misses, vì buffer 2 block không giữ được block từ lượt trước khi quay lại sau năm block khác nhau.

**Bài 14.** Dùng thứ tự gốc và cache một block: `6` reads vì chuyển block `0↔2` qua các yêu cầu. Gom theo block `0` rồi block `2`: `2` reads.

**Bài 15.** Các giá trị `mid` được truy cập ở những vị trí xa nhau; mỗi bước có thể yêu cầu một block khác chưa nằm trong RAM. `O(\log N)` so sánh không biến thành `O(\log_B N)` I/O nếu layout không giúp tăng fanout mỗi lần đọc.

**Bài 16.** Một node/page B+ tree chứa nhiều khóa phân cách và con trỏ, nên một I/O cho phép rẽ sang một trong `F=\Theta(B)` nhánh với điều kiện kích thước mục phù hợp. `O(1+\log_B N)` giữ rõ chi phí hằng số khi dữ liệu rất nhỏ hoặc `\log_B N<1`.

**Bài 17.** `\log_B N` để tìm trang lá bắt đầu của khoảng, `K/B` để đọc/xuất khoảng `K` bản ghi qua các trang lá; `+1` xét chi phí tối thiểu/khối biên.

**Bài 18.** Hash phân tán khóa vào buckets, thuận lợi cho exact-match lookup dưới phân bố tốt. Các khóa lân cận theo thứ tự giá trị có thể rơi vào buckets rời rạc, kém hiệu quả cho range scan theo khóa.

**Bài 19.** `R=\lceil9600/800\rceil=12` run; mỗi run `800/100=8` block.

**Bài 20.** RAM giữ `M/B=8` block; dành một block output nên còn `F=7` input buffers.

**Bài 21.** Pass 1: `12\to\lceil12/7\rceil=2` run. Pass 2: `2\to1` run. Vậy **2 merge passes**.

**Bài 22.** Mỗi pass tạo run/merge đọc `96` và ghi `96` = `192` I/O. Có `1` pass tạo run + `2` merge passes = `3` pass, tổng `576` I/O.

**Bài 23.** Có `1000/100=10` block; đọc 10, sắp trong RAM, ghi 10, tổng **20 I/O**.

**Bài 24.** `R=\lceil10000/2000\rceil=5`; `M/B=10` ⇒ `F=9`. Gộp 5 run trong **1 pass**. `N/B=50` block; giai đoạn tạo run và một merge pass, mỗi giai đoạn 50 reads + 50 writes → **200 I/O**.

**Bài 25.** Vì dữ liệu đầu ra cũng phải được gom vào một block buffer trước khi ghi; nếu dùng hết RAM cho input buffers, không còn block output trong thiết kế đã chọn.

**Bài 26.** `N/B` là số block cần đọc/ghi trong một lượt; log với cơ số `M/B` phản ánh số lượt nhóm/gộp nhiều run khi mỗi lượt có thể xử lý nhiều block trong RAM. Mỗi lượt quét dữ liệu tạo chi phí tỷ lệ `N/B`.

**Bài 27.** **Một write block** nếu block còn trong RAM, các sửa đổi được gộp và chỉ flush một lần; chưa tính lần đọc block nếu nó chưa có trong RAM.

**Bài 28.** Đọc block 0 = 1 read; sửa khiến nó dirty nhưng chưa write; đọc block 1 = 1 read và phải evict dirty block 0 = 1 write. Tổng **2 reads + 1 write**.

**Bài 29.** Cả `disk` và `cache` trong code đều là cấu trúc dữ liệu Python nằm trong RAM thật. Các bộ đếm tăng theo quy tắc giả lập, không đo syscall/page fault hoặc I/O thật của SSD/HDD.

**Bài 30.** Cache line là đơn vị dữ liệu CPU cache; page là đơn vị ánh xạ/bảo vệ VM; block `B` là đơn vị truyền giữa RAM và bộ nhớ ngoài **được chọn trong mô hình**. Kích thước/chức năng không bắt buộc giống nhau.

**Bài 31.** Ví dụ index B+ tree tìm một khóa trong `O(\log_B N)` I/O, hoặc một trang metadata đã lưu tổng số bản ghi và truy vấn chỉ đọc trang ấy. Cận `\Omega(N/B)` chỉ áp dụng nếu bài toán **buộc kiểm tra/xuất hết `N` mục** trong giả định lạnh.

**Bài 32.** Hai thiết kế có cùng số block transfers vẫn có thể khác thời gian vì sequential/random layout, request size, queue depth và caching. Throughput đo tải lớn, latency p95/p99 đo đuôi chậm; cần điều kiện cold/warm rõ ràng để kết quả có nghĩa.

## 38. Ghi nhớ

**Mô hình I/O (external-memory model)** đếm số lần **truyền nguyên block `B` phần tử** giữa bộ nhớ ngoài và RAM có sức chứa `M` phần tử, khi tập dữ liệu gồm `N` phần tử. Hãy dùng `N,M,B` **cùng đơn vị**, phân biệt block mô hình với CPU cache line, trang ảo và block hệ thống file. Một khi block đã ở RAM, xử lý nhiều phần tử trong đó **không tốn thêm I/O mô hình**; chi phí đọc/ghi phát sinh khi block cần được nạp, đẩy ra hoặc flush. Với dữ liệu lạnh và cần quét toàn bộ, `\operatorname{Scan}(N)=\Theta(\lceil N/B\rceil)`; với đoạn lệch biên, số block bị chạm còn phụ thuộc **offset bắt đầu**. Tìm kiếm nhị phân trên mảng lưu đĩa có thể cần `O(\log N)` I/O, trong khi B-tree/B+ tree dùng **fanout theo block** để có cận `O(1+\log_B N)`; external merge sort tạo các **run vừa RAM** và gộp nhiều run theo `M/B` buffer, đạt độ phức tạp I/O chuẩn cỡ `(N/B)(1+\log_{M/B}(N/B))` với giả định thích hợp. Đây là **mô hình số khối**, không tự suy ra latency, bandwidth, durability hay hiệu năng CPU; khi thiết kế cấu trúc dữ liệu thực tế phải kết hợp **bố trí trang, buffer reuse, mẫu truy cập, cập nhật và benchmark đúng workload**.

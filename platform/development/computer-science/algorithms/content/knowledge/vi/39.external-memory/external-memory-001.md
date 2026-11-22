# Mô hình khối dữ liệu và chi phí đọc, ghi

Khi bộ dữ liệu lớn hơn RAM, thuật toán không thể giả định mọi lần lấy phần tử đều có chi phí tương đương nhau. Một phép so sánh trong CPU có thể rất rẻ, trong khi việc đưa dữ liệu từ SSD/HDD vào RAM, ghi một trang bẩn ra thiết bị hoặc truy cập ngẫu nhiên hàng triệu vùng dữ liệu có thể chiếm phần lớn thời gian chạy. Vì vậy, **thuật toán ngoài bộ nhớ** (*external-memory algorithms*, *out-of-core algorithms*) thường phân tích **số lần truyền khối dữ liệu** thay vì chỉ đếm phép toán CPU.

Bài thuộc chủ đề **Ngoài bộ nhớ** (*External Memory*). Trọng tâm là **mô hình khối dữ liệu và chi phí đọc, ghi**: định nghĩa `N`, `M`, `B`; khác biệt giữa đọc một bản ghi và đọc một khối; đọc tuần tự so với truy cập ngẫu nhiên; page cache, eviction, write-back/flush; phép trộn có bộ đệm; B-tree và sắp xếp ngoài bộ nhớ; cũng như cách chuyển phân tích số khối sang thiết kế hệ thống thực tế.

Chương trình Java 17+ ở cuối bài mô phỏng một thiết bị khối, bộ đệm **LRU** và phép trộn hai đoạn đã sắp xếp. Nó đếm chính xác **block reads / block writes** trong mô hình, kiểm tra độ đúng bằng mảng đối chiếu, và phân biệt **số I/O mô phỏng** với **thời gian thực của hệ điều hành hoặc SSD**.

## 1. Vì sao mô hình RAM thông thường chưa đủ?

Trong mô hình **RAM** đơn giản, ta thường tính:

```text
Đọc a[i]:          O(1)
Ghi a[i]:          O(1)
So sánh hai số:    O(1)
```

Mô hình này rất hữu ích khi dữ liệu ở RAM và truy cập tương đối đồng đều. Tuy nhiên, nếu tập dữ liệu gồm hàng terabyte trên đĩa còn RAM chỉ có vài gigabyte, lệnh đọc `a[i]` có thể khiến hệ thống phải **nạp cả một trang/khối**. Một truy cập tiếp theo tới bản ghi gần đó có thể được phục vụ từ bộ đệm, trong khi một truy cập tới vị trí xa lại cần I/O khác.

Đặc biệt, hai thuật toán cùng đọc N phần tử có thể tốn số lần truyền khối rất khác:

- **Quét tuần tự:** đọc các phần tử theo thứ tự vật lý, tận dụng cả khối vừa nạp.
- **Truy cập phân tán:** mỗi phần tử nằm trong khối khác và khối cũ bị đẩy khỏi cache trước khi dùng lại.

Trong thực tế, các thiết bị lưu trữ còn có độ trễ, băng thông, hàng đợi, page cache và write amplification khác nhau. **Mô hình I/O** cố ý trừu tượng hóa các yếu tố đó để tập trung câu hỏi căn bản: *Thuật toán phải chuyển bao nhiêu khối giữa bộ nhớ nhanh và bộ nhớ chậm?*

## 2. Mô hình hai tầng bộ nhớ (*external-memory / I/O model*)

Mô hình cổ điển thường gắn với **Aggarwal–Vitter** có hai tầng:

1. **Bộ nhớ trong** (*internal memory*), kích thước chứa tối đa `M` mục dữ liệu.
2. **Bộ nhớ ngoài** (*external memory*, đĩa hoặc SSD), chứa tập dữ liệu lớn hơn.
3. Mỗi thao tác I/O chuyển một **khối** gồm `B` mục liên tiếp giữa hai tầng.
4. Thuật toán xử lý dữ liệu đang nằm trong bộ nhớ trong và bị giới hạn dung lượng `M`.

Trong ký hiệu đơn giản cho các bản ghi có kích thước cố định:

```text
N = tổng số bản ghi cần xử lý.
M = số bản ghi có thể nằm trong RAM dành cho thuật toán.
B = số bản ghi chứa trong một khối truyền I/O.

1 <= B <= M, thường N >> M.
```

Trong hệ thống thực, `B` thường được đo bằng **byte mỗi page** (ví dụ page size), còn M đo bằng byte. Khi bản ghi kích thước thay đổi, “B bản ghi mỗi khối” chỉ là cách đơn giản hóa để học thuật toán; muốn chuyển sang byte phải tính kích thước và cách đóng gói bản ghi.

### 2.1. Một lần I/O là một lần truyền khối

Nếu một khối chứa 4 số nguyên:

```text
Block 0: [8, 3, 7, 1]
Block 1: [6, 2, 5, 4]
Block 2: [13,11,15,9]
Block 3: [10,16,12,14]
```

đọc một phần tử của Block 0 từ đĩa vào RAM thường kéo theo việc **nạp toàn bộ Block 0** trong mô hình. Khi Block 0 đã ở bộ đệm, đọc thêm ba phần tử cùng block **không tốn thêm truyền khối**, miễn block chưa bị đẩy ra.

Chi phí được mô tả:

```text
Q_read  = số lần tải khối từ bộ nhớ ngoài vào bộ nhớ trong.
Q_write = số lần ghi khối từ bộ nhớ trong ra bộ nhớ ngoài.

Q_total = Q_read + Q_write.
```

Các ký hiệu này là **bộ đếm I/O**, không phải thời gian tính bằng mili giây. Một block read và một block write có thể khác chi phí thực tế; mô hình cơ bản vẫn đếm chúng cùng đơn vị *một lần truyền khối*.

### 2.2. Ví dụ N=16, B=4, M=8

```text
N = 16 bản ghi.
B =  4 bản ghi / khối.
M =  8 bản ghi trong RAM.

Số khối đĩa: N/B = 4.
Số frame chứa khối trong RAM: M/B = 2.
```

Hình dung:

```text
DISK                            RAM: tối đa 2 frame
+-----------+                   +-----------+
| block 0   | -- read -->       | frame A   |
+-----------+                   +-----------+
| block 1   | -- read -->       | frame B   |
+-----------+                   +-----------+
| block 2   |                   Khi cần block 2:
+-----------+                   đẩy một frame cũ,
| block 3   |                   có thể phải ghi nếu dirty.
+-----------+
```

Nếu chương trình cần block 2 khi cả hai frame đã đầy, nó phải **thay thế một trang** (*eviction*). Nếu trang bị thay thế đã được sửa và chưa ghi xuống đĩa, phải phát sinh **block write** trong chính sách write-back.

### 2.3. Đếm block khác đếm record và phép so sánh

Ví dụ quét 16 số:

```text
16 lần xử lý record
4 lần block read (trong tình huống dữ liệu chưa ở cache)
0 lần block write nếu chỉ đọc
```

Một thuật toán có thể thực hiện hàng nghìn phép tính nội bộ trên dữ liệu đã nạp mà không tăng `Q_total`. Ngược lại, thuật toán chỉ làm vài phép tính nhưng liên tục tải các block khác nhau có thể rất tốn I/O.

**Không đồng nhất `Q_total` với số lệnh Java, số phần tử truy cập, hoặc tổng byte đọc từ thiết bị khi có nén/ghi log/prefetch.**

## 3. Chi phí quét tuần tự: `Scan(N)`

Nếu cần đọc **toàn bộ N bản ghi**, chúng được xếp liên tiếp thành các block B bản ghi, và bộ nhớ ban đầu chưa có dữ liệu:

```text
Scan(N) = ceil(N/B) block reads.
```

Khi N chia hết B:

```text
Scan(N) = N/B.
```

Ví dụ:

```text
N=16, B=4
Đọc a[0],a[1],...,a[15]

Block 0: 1 lần đọc.
Block 1: 1 lần đọc.
Block 2: 1 lần đọc.
Block 3: 1 lần đọc.

Q_read=4.
```

Độ phức tạp I/O:

```text
Theta(1 + N/B)
```

khi tính cả chi phí bắt đầu nhỏ nhất; với N≥B, thường viết **Theta(N/B)**. Trong trường hợp đầu vào phải đọc hết và chưa nằm sẵn trong RAM, **ít nhất** phải chuyển số khối chứa toàn bộ dữ liệu cần thiết, nên scan gần tối ưu về số block transfers.

### 3.1. Nếu N không chia hết B

Ví dụ:

```text
N=10, B=4
Các block có 4,4,2 bản ghi hữu ích.

ceil(10/4)=3 lần đọc khối.
```

Block cuối có thể chứa vùng padding hoặc vài bản ghi không dùng. Một phép toán block I/O vẫn tính như một lần truyền nguyên block trong mô hình đơn giản.

### 3.2. Quét nhiều lần có tốn cùng số I/O không?

Không nhất thiết. Nếu toàn bộ tập dữ liệu vừa với RAM `N<=M` và không bị đuổi khỏi cache, quét lần hai có thể không phát sinh block read. Nếu `N>>M`, mỗi lượt quét thường phải đọc lại nhiều block và tốn gần `N/B` I/O, trừ khi có tầng cache khác hoặc hệ thống phân phối lại dữ liệu.

Một thuật toán đọc cùng dữ liệu p lượt có cận trực giác:

```text
O(p * N/B) block reads
```

khi mỗi lượt phải nạp lại dữ liệu. Tuy nhiên đây không phải đẳng thức bất biến: cache và thứ tự xử lý có thể làm kết quả khác.

### 3.3. Prefetch và quét song song

Hệ điều hành có thể đoán rằng chương trình đang quét tuần tự và **nạp trước** các block tiếp theo. Điều này có thể giảm thời gian chờ và tận dụng băng thông, nhưng không nhất thiết làm số khối dữ liệu thực sự truyền xuống thấp hơn `ceil(N/B)` khi bắt buộc phải đọc hết. Vì thế **chi phí I/O theo số khối** và **độ trễ wall-clock** phải báo riêng.

## 4. Truy cập ngẫu nhiên và working set vượt RAM

Đọc `a[i]` cần block:

```text
blockId = floor(i / B).
offset  = i mod B.
```

Nếu block tương ứng đã có trong RAM:

```text
Q_read tăng 0.
```

Nếu chưa có:

```text
Q_read tăng 1.
```

Bởi vậy t truy vấn theo vị trí có thể tốn **t lượt đọc khối** nếu mỗi truy vấn gây cache miss, mặc dù chỉ có t bản ghi được sử dụng.

### 4.1. Ví dụ cache 2 frame và bốn block

Với `B=4`, bộ đệm chứa **2 block**, xét thứ tự:

```text
Truy cập record index:
0, 4, 8, 12, 0, 4, 8, 12.

Tương ứng block:
0, 1, 2, 3, 0, 1, 2, 3.
```

Chính sách **LRU** (*least recently used*) giữ hai block truy cập gần nhất. Vì mỗi lần quay lại block cũ thì hai frame đã bị các block khác chiếm, cả **8 truy vấn đều miss**:

```text
Q_read=8.
Q_write=0.
LRU evictions=6.
```

Trong khi đó quét **16 bản ghi liên tục** của cùng tập dữ liệu chỉ tốn `4 block reads`. Đây là **sự khác nhau về locality**, không phải chỉ số lượng record.

### 4.2. Locality theo không gian và thời gian

**Spatial locality**: truy cập các bản ghi gần nhau trong cùng block.

```text
0,1,2,3      => chỉ cần tải block 0 một lần.
```

**Temporal locality**: truy cập lại block vừa dùng khi nó còn trong cache.

```text
0,2,1,3      => cả bốn index cùng block 0.
```

Cấu trúc dữ liệu đặt các phần tử liên quan gần nhau có thể giảm I/O mạnh. Ngược lại, danh sách liên kết có các node nằm ở những block xa nhau có thể phát sinh gần một I/O mỗi bước truy cập nếu không cache được.

### 4.3. LRU là chính sách cache, không phải định lý tối ưu

LRU đẩy block **lâu nhất chưa được sử dụng**. Nó thường tốt cho workload có tính thời gian cục bộ, nhưng có thể bị *thrashing* khi working set lớn hơn số frame. LRU không phải thuật toán thay thế tối ưu cho mọi chuỗi truy cập. Một chính sách có quyền biết tương lai có thể quyết định tốt hơn, nhưng trong thực tế không thể giả định biết trước mọi truy vấn.

**Bài toán thuật toán ngoài bộ nhớ** đôi khi phân tích một lịch I/O tối ưu trong mô hình lý tưởng thay vì yêu cầu LRU cụ thể. Chương trình Java dùng LRU để minh họa chính xác tác động của buffer capacity và thứ tự truy cập.

## 5. Chi phí ghi: dirty page, write-back, flush

Đọc một block để sửa một bản ghi rồi ghi lại xuống đĩa có thể cần:

```text
1 block read
1 block write.
```

Tuy nhiên, nếu nhiều bản ghi trong **cùng một block** được sửa khi block còn ở RAM, hệ thống có thể **gom nhiều sửa đổi** thành **một block write**.

### 5.1. Write-through và write-back

**Write-through** là chính sách ghi thay đổi xuống tầng dưới sớm hoặc ngay khi có thao tác ghi theo hợp đồng. Ưu điểm là việc đồng bộ có thể dễ hiểu hơn; nhược điểm là nhiều sửa đổi nhỏ có thể tạo nhiều ghi.

**Write-back** chỉ đánh dấu block **dirty**, chờ đến khi eviction hoặc flush mới ghi block xuống thiết bị:

```text
cache.set(index,value):
  ensure owning block is in RAM
  change buffered value
  mark page dirty

cache.flush():
  write each dirty page to device
  mark clean
```

Trong ví dụ, cập nhật bốn record ở **cùng block** rồi flush:

```text
4 logical record edits
1 block read
1 block write
```

Đây là **coalescing**: một lần ghi block chứa toàn bộ bốn thay đổi. Không nên cộng “bốn lần sửa record = bốn block write” khi dùng write-back.

### 5.2. Eviction trang dirty

Với 2 frame, giả sử lần lượt sửa một record trong block 0,1,2,3, rồi flush.

```text
Update block 0: load 0, dirty 0.
Update block 1: load 1, dirty 1.

Update block 2:
  evict dirty block 0 -> one write;
  load block 2 -> one read.

Update block 3:
  evict dirty block 1 -> one write;
  load block 3 -> one read.

Flush:
  write dirty blocks 2 and 3.
```

Tổng:

```text
Q_read = 4
Q_write = 4
evictions = 2
```

Không có lỗi nếu một trang bị ghi nhiều lần qua nhiều vòng đọc–sửa–đẩy: bộ đệm hạn chế có thể phải tải lại và ghi lại cùng block trong một workload dài.

### 5.3. Khác biệt giữa partial-block update và bulk write

Nếu muốn sửa **một phần** của một block nhưng chưa có bản sao block trong RAM, mô hình trang thường cần **đọc block hiện tại** trước khi sửa để không làm mất các bản ghi khác trong block. Ngược lại, nếu thuật toán tạo mới **toàn bộ block đầu ra** từ các giá trị đã tính trong RAM, có thể **ghi nguyên block trực tiếp mà không đọc block đầu ra cũ**.

Đó là lý do phép trộn ngoại vi trong Java:

```text
Đọc toàn bộ block đầu vào: block reads.
Tạo block đầu ra hoàn chỉnh trong RAM.
Ghi nguyên block đầu ra: block writes.
```

Bộ ghi block đầu ra không cần gọi `readBlock` để biết các giá trị cũ mà nó sẽ ghi đè hoàn toàn.

### 5.4. Dirty buffer không giống tính bền vững của dữ liệu

Một bản ghi đã được cập nhật trong RAM chưa chắc đã **bền vững sau mất điện**. Flush trong mô phỏng Java chỉ chuyển dữ liệu vào mảng đại diện thiết bị, không phải cam kết tương đương `fsync` trên hệ thống tệp, FUA, journal hoặc tính năng lưu trữ bền vững của ổ đĩa.

Trong hệ thống thật phải phân biệt:

- Sửa giá trị logic.
- Sửa page cache.
- Gửi lệnh write tới thiết bị.
- Thiết bị đã hoàn thành ghi.
- Dữ liệu đã đạt yêu cầu durability sau sự cố.

Mô hình I/O cơ bản chỉ **đếm truyền khối**, không tự chứng minh ACID, crash consistency hoặc tính an toàn giao dịch.

## 6. Mô hình chi phí có hai hướng đọc và ghi

Có thể dùng cặp:

```text
(Q_read, Q_write)
```

thay vì chỉ ghi tổng để thấy workload thiên về đọc hay ghi. Trong mô hình hai tầng cơ bản:

```text
Q_total = Q_read + Q_write.
```

Nếu cần dự báo thời gian thực tế, có thể dùng một ước lượng kỹ thuật đơn giản:

```text
Time_IO ≈ Q_read * time_per_read
        + Q_write * time_per_write
```

Nhưng đây **không phải công thức thời gian chính xác phổ quát**, vì I/O có thể chồng lấp, thực hiện song song, được cache/nén, gom lệnh hoặc bị ảnh hưởng bởi truy cập ngẫu nhiên, độ dài request và bandwidth.

Cách báo có trách nhiệm thường tách:

1. **Block transfers trong mô hình** (`Q_read`, `Q_write`).
2. **Dung lượng byte** được truyền, gần `B * recordSize * Q_total` với fixed-size records và block đầy.
3. **Số seek/lệnh random I/O** nếu workload quan tâm.
4. **Thời gian CPU**, gồm so sánh, sắp xếp nội bộ, giải mã/nén.
5. **Wall-clock**, đo trên hệ điều hành/hardware thực tế.

**Không dùng Big-O thời gian CPU để kết luận ưu thế I/O**, và cũng không dùng số I/O mô phỏng để tự khẳng định một tốc độ MB/s trên phần cứng chưa đo.

## 7. Phép trộn hai đoạn đã sắp xếp với bộ đệm khối

Xét hai đoạn liên tiếp đã sắp xếp trong một tập dữ liệu ngoài RAM:

```text
Run A: [1,4,7,10,13,16,19,22]
Run B: [2,3,8,9,14,15,20,21]
```

Giả sử mỗi block chứa 4 số:

```text
Input disk:
  Block 0: [1,4,7,10]
  Block 1: [13,16,19,22]
  Block 2: [2,3,8,9]
  Block 3: [14,15,20,21]
```

Để trộn hai run:

- Giữ **một block đầu vào của Run A**.
- Giữ **một block đầu vào của Run B**.
- Giữ **một block đầu ra**.
- So hai phần tử đầu chưa dùng của mỗi run, chọn nhỏ hơn, append vào output buffer.
- Khi một input buffer hết, đọc block tiếp theo của run đó.
- Khi output buffer đầy, ghi block mới ra thiết bị đầu ra.
- Đến cuối, output là một run đã sắp xếp.

### 7.1. Số block transfers cho hai-run merge

Với tổng N=16, B=4, giả sử mỗi block đầu vào được đọc một lần và output mỗi block được ghi một lần:

```text
Q_read  = 16/4 = 4
Q_write = 16/4 = 4

Q_total = 8 block transfers.
```

Output:

```text
[1,2,3,4,7,8,9,10,13,14,15,16,19,20,21,22]
```

**Quan trọng:** Phép trộn này cần ít nhất **3 frame khối** khi muốn giữ một block cho mỗi run đầu vào và một block đầu ra. Đó là **M>=3B** trong cách tổ chức này. Nó là một ví dụ **khác cấu hình** với cache LRU hai frame ở phần 2: nếu chỉ có `M=2B`, không thể đồng thời giữ nguyên ba buffer B bản ghi như trên.

### 7.2. Chứng minh tính đúng của merge

Bất biến sau khi tạo p phần tử output:

```text
Output[0..p-1] gồm p phần tử nhỏ nhất
đã lấy từ hai tiền tố đã tiêu thụ,
theo thứ tự không giảm.
```

Vì từng run đã được sắp xếp, phần tử chưa lấy nhỏ nhất của run nằm ở vị trí đầu còn lại. Lấy min của hai đầu run là phần tử nhỏ nhất trong toàn bộ phần tử chưa sử dụng. Quy nạp theo p chứng minh output cuối là hợp của hai run được sắp xếp đúng, giữ nguyên đa tập phần tử.

**Bộ nhớ** cho hai input block và một output block là `O(B)` bản ghi (hằng số ba khối). **Số thao tác so sánh** là `O(N)`, còn **I/O** là `O(N/B)` reads và `O(N/B)` writes. Đây là ví dụ tiêu biểu cho việc I/O có thể thấp hơn đáng kể số record được xử lý.

### 7.3. Đầu ra cần đọc lại block cũ không?

Không, vì code xây **nguyên block output từ đầu**, rồi gọi `writeBlock(blockId,values)` để ghi trực tiếp. Nếu thay vào đó sửa từng bản ghi của một block output đã tồn tại bằng API read-modify-write, có thể phát sinh các reads không cần thiết. **Chọn primitive I/O phù hợp** là một phần của thiết kế external-memory algorithm.

## 8. Multiway merge và cách sử dụng M/B frame

Đối với nhiều run đã sắp xếp, thay vì trộn hai run một lần, ta có thể trộn **F run cùng lúc** nếu RAM đủ chỗ:

```text
F input buffers: mỗi buffer một block B bản ghi.
1 output buffer: một block B bản ghi.

(F+1)*B <= M.
```

Do đó trong mô hình buffer đơn giản:

```text
F <= floor(M/B)-1.
```

Nếu M=12B, có thể cấp 11 buffer đầu vào và 1 buffer đầu ra, tức trộn **11 run cùng một pass**. Nếu chỉ cần 10 run, 11 buffer đầu vào không bắt buộc dùng hết. Với M<3B, cách trộn hai run có một output buffer cần một thiết kế khác hoặc giảm yêu cầu buffer; các công thức multiway dưới đây giả định **ít nhất ba block frame**.

### 8.1. Một pass trộn F-way tốn bao nhiêu I/O?

Nếu tổng N bản ghi nằm trong F run đã sắp xếp, mỗi record được đưa vào output đúng một lần:

```text
Q_read  ≈ ceil(N/B)
Q_write ≈ ceil(N/B)
Q_pass  ≈ 2*ceil(N/B)
```

Bỏ qua phần block cuối và bookkeeping, dùng ký hiệu:

```text
Theta(N/B) block transfers per merge pass.
```

CPU còn phải chọn phần tử nhỏ nhất trong F đầu run, có thể dùng **priority queue / loser tree** để giảm chi phí chọn xuống `O(log F)` so sánh mỗi record. Điều đó ảnh hưởng **CPU**, nhưng không đổi bậc I/O của một merge pass khi các input buffer được quản lý tốt.

### 8.2. Vì sao merge fan-in lớn giúp giảm số pass?

Nếu có R run ban đầu, mỗi pass trộn được F run thành một:

```text
R -> ceil(R/F) -> ceil(R/F^2) -> ...
```

Số merge pass:

```text
ceil(log_F R)
```

khi F≥2, với quy ước không cần pass nếu R=1. Vì mỗi pass quét và ghi lại toàn bộ N phần tử, **giảm số pass** là mục tiêu then chốt trong sắp xếp ngoài bộ nhớ.

## 9. Sắp xếp ngoài bộ nhớ (*external merge sort*)

Khi `N>>M`, không thể nạp toàn bộ tập vào RAM rồi gọi `Arrays.sort`. Một chiến lược quen thuộc:

**Pha 1 — tạo run:**

1. Đọc tối đa M record từ đĩa.
2. Sắp xếp hoàn toàn trong RAM bằng thuật toán phù hợp.
3. Ghi run đã sắp xếp ra bộ nhớ ngoài.
4. Lặp cho đến khi xử lý hết N record.

Số run khoảng:

```text
R = ceil(N/M).
```

I/O pha tạo run khi toàn bộ input/output nằm ngoài RAM:

```text
Q_read  ≈ N/B
Q_write ≈ N/B
Q_run   ≈ 2N/B.
```

**Pha 2 — trộn nhiều run:** Giữ F block đầu vào cộng một output block trong RAM. Mỗi merge pass có khoảng:

```text
Q_mergePass ≈ 2N/B.
```

Cần khoảng `ceil(log_F R)` pass. Tổng I/O cho một triển khai đơn giản:

```text
Q_sort ≈ 2(N/B) * [1+ceil(log_F ceil(N/M))],
F=floor(M/B)-1, F>=2.
```

Biểu thức này bỏ qua chi phí block chưa đầy, quản lý file, và việc **loại bớt một lần ghi/đọc** trong một vài tình huống tối ưu pipeline. Nó vẫn là một mô hình bậc lớn hữu ích để thiết kế.

### 9.1. Cận Big-O quan trọng

Trong mô hình external-memory với giả thiết phù hợp `M/B` đủ lớn cho trộn nhiều ngả, sorting comparison-based có cận I/O kinh điển dạng:

```text
Sort(N) =
  Theta((N/B) *
    (1 + log_{M/B}(N/B)))
```

cho miền N lớn hơn M và điều kiện mô hình chuẩn (có thể dùng dạng log có cắt dưới để tránh số âm khi N<=B). Với `N<=M`, có thể đọc dữ liệu vào RAM, sort CPU, ghi kết quả, dùng **Theta(1+N/B)** I/O, nếu bắt buộc lưu kết quả ra bộ nhớ ngoài.

Cách ghi phổ biến khác:

```text
O((N/B) * log_{M/B}(N/B))
```

ở miền ngoài bộ nhớ thực sự, khi logarithm đủ lớn và các giả thiết asymptotic áp dụng. **Đừng bỏ term đọc/ghi đầu vào tối thiểu** khi N nhỏ hoặc dữ liệu đã nằm RAM.

### 9.2. Ví dụ với N=1.000.000, B=1.000, M=100.000

```text
N = 1,000,000 records.
B = 1,000 records / block.
M = 100,000 records RAM.

N/B = 1000 disk blocks.
M/B = 100 input/output block frames.
R = ceil(N/M) = 10 sorted runs.
F = floor(M/B)-1 = 99 possible input runs.
```

Chỉ cần **một merge pass** vì `R=10<=F=99`:

```text
Create runs:
  1000 block reads + 1000 block writes = 2000 I/O.

Merge 10 runs:
  1000 block reads + 1000 block writes = 2000 I/O.

TOTAL ≈ 4000 block transfers.
```

Đây là một **ước lượng của kế hoạch sắp xếp cụ thể**, không phải đồng nghĩa 4000 câu lệnh Java và không bao gồm ghi log, metadata, paging phụ, filesystem cache hoặc tối ưu thực tế như in-place final output.

### 9.3. Vì sao không gọi sort trong RAM trên toàn N?

Nếu dùng `Arrays.sort` cho mảng N bản ghi mà RAM chỉ cấp M nhỏ hơn N, chương trình không thể chứa toàn bộ array theo giả thiết. Hệ điều hành có thể swap/page, nhưng số I/O phát sinh không được kiểm soát như một chiến lược ngoại vi có **buffering rõ ràng**. Kỹ thuật external merge sort bảo đảm thứ tự quét và bộ nhớ làm việc phù hợp giới hạn M.

### 9.4. CPU time và I/O time của external sort

Mỗi run sort trong RAM có thể tốn `O(M log M)` so sánh, tổng gần `O(N log M)`; merge F-way dùng queue/loser tree có thể thêm `O(N log F)` so sánh mỗi pass, tổng vẫn có chi phí CPU đáng kể. Tuy vậy số lần truyền block được thiết kế gần các pass tuần tự. Không được gọi một thuật toán là “tốt hơn” chỉ vì I/O ít hơn nếu CPU/disk write bandwidth/khả năng song song thực tế làm thay đổi kết quả; **đánh giá đa mục tiêu** là cần thiết.

## 10. B-tree, B+tree và số I/O truy vấn

Một cây tìm kiếm nhị phân thông thường có chiều cao `O(log_2 N)`, nhưng nếu mỗi node ở một block đĩa khác nhau thì một lần search có thể đi qua **nhiều block**.

**B-tree / B+tree** đặt nhiều key và con trỏ liên quan vào **mỗi node có kích thước gần một page**, giúp fan-out khoảng Theta(B) trong mô hình khóa/record cố định. Với cây cân bằng, chiều cao theo block thường là:

```text
O(log_B N)
```

hoặc viết chính xác hơn theo số phần tử/keys mỗi node và mức lấp đầy của cây.

### 10.1. Lý do base B xuất hiện

Trong một BST nhị phân, mỗi node có tối đa hai nhánh, nên đường đi dài khoảng log base2 của N.

Trong một B-tree được đóng gói page tốt, một node có thể chỉ tới **nhiều block con**. Với fan-out F:

```text
level 0: 1 node/page
level 1: F pages
level 2: F^2 pages
...
```

Chiều cao nhỏ nhất đạt để bao phủ N key là cỡ `log_F N`. Vì mỗi level có thể đọc một page, chi phí search là `O(log_F N)` I/O, thường mô tả thành `O(log_B N)` khi F=Theta(B).

**Không nên hiểu** một B-tree search chắc chắn đòi `log_B N` I/O thực tế trên mọi lần: root và các node cấp cao có thể được cache, dữ liệu mới có thể đã nằm RAM, hoặc index chỉ chứa con trỏ khiến cần thêm page read để lấy record.

### 10.2. Truy cập index vs full scan

Nếu truy vấn tìm một key:

- Full scan không index có thể tốn `Theta(N/B)` I/O.
- B-tree cân bằng có thể tốn `O(log_B N)` I/O tìm index, cộng I/O lấy record nếu record nằm ngoài leaf.
- Hash index có thể gần `O(1)` I/O trung bình cho lookup theo khóa dưới giả thiết phân bố/load factor tốt, nhưng không tự hỗ trợ range query theo thứ tự.
- Nếu truy vấn cần lấy **phần lớn toàn bộ bảng**, quét tuần tự có thể tốt hơn việc đi qua index rồi đọc hàng loạt page phân tán.

Chọn cấu trúc dữ liệu phải dựa trên **mẫu truy vấn**: point lookup, range scan, append/update, batch processing, hay sort/merge.

## 11. Blocked binary search và cây tìm kiếm ngoài RAM

Giả sử một file đã sắp xếp liên tục. Binary search trên vị trí record cần `O(log_2 N)` phép so sánh. Nhưng nếu từng phép so sánh yêu cầu tìm record ở một block chưa cache, số block I/O có thể cao hơn thuật toán được thiết kế theo page.

### 11.1. Vì sao count comparisons chưa đủ?

Hai cách tổ chức:

```text
A. sorted array nằm trên disk:
   tìm giữa đoạn, rồi giữa nửa còn lại...
   Các vị trí có thể rơi vào block khác nhau.

B. B-tree có node tương ứng page:
   mỗi lần đọc một page biết được nhiều mốc phân hoạch;
   chọn một trong nhiều nhánh ngay khi page còn ở RAM.
```

Cả hai có thể dùng O(log N) phép so sánh CPU, nhưng số block I/O khác. B-tree tổ chức mốc tìm kiếm theo khả năng mang **nhiều key trên một block**, nên giảm số cấp cần nạp.

### 11.2. Có trường hợp binary search đã tốt?

Có. Nếu toàn bộ array vừa RAM, binary search không cần I/O sau lần nạp đầu. Nếu index nhỏ và cache tốt, chi phí vật lý rất thấp. Mô hình block có giá trị để làm rõ **điều kiện** dẫn tới I/O, không phải cấm binary search trên file.

## 12. Block-aware, cache-aware và cache-oblivious

**Cache-aware algorithm** biết hoặc sử dụng các tham số M và B để chọn kích thước run, block buffer, branching factor và chiến lược quét.

Ví dụ external merge sort từ M,B tính:

```text
runSize ≈ M
fanIn   ≈ floor(M/B)-1.
```

**Cache-oblivious algorithm** không hardcode M và B trong logic phân chia, nhưng có thể đạt cận số cache misses tốt trong mô hình lý tưởng với giả thiết thích hợp. Nó thường dựa vào cấu trúc đệ quy và locality tự nhiên; không phải cứ viết mã đệ quy là “cache-oblivious”, và không phải nó không dùng cache thực tế.

Cần phân biệt:

- **Cache-aware:** thuật toán chủ động kích thước block/buffer.
- **Cache-oblivious:** thuật toán không biết tham số nhưng phân tích I/O dưới mô hình cache lý tưởng.
- **Cache-unfriendly:** truy cập phân tán khiến thiếu locality, dù CPU complexity tốt.
- **Cache simulation:** như mã Java demo, tự mô phỏng cơ chế LRU; nó minh họa cache behavior, không phải thực hiện I/O thật.

## 13. Cấu trúc ghi nhiều: vì sao LSM tree được nhắc tới?

Một số hệ thống lưu trữ phải nhận rất nhiều cập nhật nhỏ. Nếu mỗi update sửa page rời rạc của một index trên đĩa, nhiều lần random I/O có thể đắt. Ý tưởng **Log-Structured Merge Tree (LSM-tree)** là tích lũy update trong RAM rồi ghi thành các **run/sorted files lớn**, định kỳ **merge/compact** chúng.

Điều này chuyển một phần workload từ random writes thành sequential writes, thường cải thiện throughput ghi trong nhiều tình huống. Tuy vậy, compaction có thể đọc và ghi lại dữ liệu nhiều lần, sinh **write amplification**. Số pass, chính sách compaction, mức dữ liệu, query amplification và bộ lọc thường ảnh hưởng kết quả.

**Không đồng nhất LSM với external merge sort của bài:** chúng cùng dùng tư tưởng run và merge, nhưng mục tiêu và lịch ghi khác nhau. Muốn phân tích LSM cần mô tả rõ kiến trúc level/size ratio, buffer, flush, compaction và workload; không thể áp máy móc `2N/B` cho cả đời sống một LSM.

### 13.1. Write amplification là gì?

Một record có thể bị ghi nhiều lần qua nhiều cấp hoặc đợt compaction. Một tỷ số đơn giản:

```text
write amplification =
    bytes actually written by storage engine /
    logical bytes inserted or updated.
```

Tỷ số thực tế phụ thuộc định nghĩa đo, ghi metadata, WAL, compaction, compression và việc dữ liệu được viết lại nhiều lần. Trong mô hình khối, một workload thường xuyên đẩy dirty pages ra rồi nạp lại cũng cho thấy **nhiều block writes hơn số block dữ liệu duy nhất**.

## 14. Chi phí đọc, ghi bất đối xứng và mô hình thực tế

Mô hình I/O cơ bản coi block read và block write là một lần truyền. Nhưng thiết bị và hệ thống có thể cho chúng chi phí rất khác:

- HDD có thể chịu **seek/rotation** lớn với truy cập ngẫu nhiên; đọc liên tiếp thường tận dụng băng thông tốt hơn.
- SSD giảm nhiều chi phí seek cơ học, nhưng random vs sequential I/O vẫn khác về request size, queue depth, cache và write amplification.
- Tầng OS page cache có thể khiến một read logic được phục vụ hoàn toàn từ RAM, không đụng thiết bị vật lý.
- Write-back thường có độ trễ phát sinh sau thời điểm record logic được sửa.
- Hệ thống có thể dùng DMA, batching, prefetch hoặc I/O bất đồng bộ; **độ trễ tổng không bằng tổng tuần tự mọi request** nếu có chồng lấp/parallelism.

Do đó, khi benchmark hệ thống thật cần ghi:

```text
N, M, B, record size
trình tự truy cập
số page faults / cache hits
logical reads / writes
physical reads / writes
bytes read / written
latency / throughput
hardware, filesystem, cache state
```

Ví dụ không được so “4 block read” của simulator với “8 page faults” của JVM như cùng đơn vị nếu hai hệ thống đang đo những sự kiện khác nhau. Simulator có khối B gồm số nguyên cố định; JVM và OS có cache và page size riêng.

### 14.1. Dữ liệu có thể bị nén

Nếu dữ liệu ngoài bộ nhớ được nén, một block vật lý có thể chứa số record thay đổi. CPU phải giải nén trước khi truy cập record; hiệu quả I/O có thể tăng vì chuyển ít byte hơn nhưng CPU tốn hơn. Mô hình fixed-size B-records là nền tảng để phân tích, còn hệ thống có nén cần đo các chi phí bổ sung.

### 14.2. Random write có thể thành sequential write trong tầng dưới

Bộ nhớ đệm, hệ thống file hoặc storage engine có thể gom và sắp xếp các dirty pages trước khi ghi. Vì thế từ code gọi update ngẫu nhiên **không thể mặc định** thiết bị vật lý nhận số write ngẫu nhiên bằng số update logic. Mô hình block giúp chỉ ra cơ hội gom, chứ không dự đoán mọi tối ưu ở tầng dưới.

## 15. Java 17+: thiết bị khối, cache LRU và merge

Tệp **`ExternalMemoryBlockCostDemo.java`** chứa một mô phỏng **hoàn toàn trong RAM của JVM**, với hai tầng logic `BlockDevice` và `LruBuffer`. Không có file thật, không có `FileChannel`, không đo seek/SSD thực. Nó cố ý đếm **logical block transfers** để các ví dụ có stdout ổn định và dễ kiểm chứng.

Các thành phần:

- `BlockDevice`: giữ mảng record, `blockSize`, bộ đếm `reads`,`writes`; chỉ nạp/ghi **nguyên block**.
- `LruBuffer`: cache tối đa một số frame. Khi miss đọc block; khi eviction trang dirty thì ghi block trước khi xóa; `flush()` ghi tất cả trang dirty còn trong cache.
- `RunCursor`: giữ một block của một run đã sắp xếp, gọi `readBlock` khi cursor sang block mới.
- `mergeTwoSortedRuns`: giữ hai input buffers và một output buffer; trực tiếp ghi mỗi block đầu ra đầy, **không đọc output cũ**.
- `example`: quét tuần tự, truy cập luân phiên gây thrashing, ghi phân tán, nhiều sửa trong một block và trộn hai run.
- `randomOracleTests`: **500 workload cache**, mỗi workload **120 thao tác record** đối chiếu với mảng chính xác, tổng 60.000 thao tác; **300 bài merge hai run** đối chiếu với `Arrays.sort`, bao gồm số lần đọc/ghi khối đúng.
- `check`: dừng ngay nếu bất biến bị sai.

**Phạm vi giản lược:** Đầu vào không rỗng, số record chia hết B, block chứa số nguyên `int`, cache không dùng đồng bộ đa luồng. Dữ liệu được sao chép khi truyền khối. Đây là **mô hình khối**, không phải mã external sort dùng file thật. Muốn áp dụng với file lớn cần thay `BlockDevice` bằng đọc/ghi page qua `FileChannel` hoặc cơ chế phù hợp, quản lý block cuối, lỗi I/O, crash recovery và durability riêng.

### 15.1. Mã Java đầy đủ

```java
import java.util.*;

public class ExternalMemoryBlockCostDemo {
    static final class BlockDevice {
        final int[] data;
        final int blockSize;
        long reads, writes;

        BlockDevice(int[] values, int blockSize) {
            Objects.requireNonNull(values);
            if (blockSize <= 0 || values.length == 0
                    || values.length % blockSize != 0) {
                throw new IllegalArgumentException(
                        "Nonempty data size must be divisible by block size");
            }
            data = values.clone();
            this.blockSize = blockSize;
        }

        int blocks() {
            return data.length / blockSize;
        }

        int[] readBlock(int blockId) {
            checkBlock(blockId);
            reads++;
            return Arrays.copyOfRange(data,
                    blockId * blockSize, (blockId + 1) * blockSize);
        }

        void writeBlock(int blockId, int[] block) {
            checkBlock(blockId);
            if (block == null || block.length != blockSize) {
                throw new IllegalArgumentException("Wrong block length");
            }
            System.arraycopy(block, 0,
                    data, blockId * blockSize, blockSize);
            writes++;
        }

        void checkBlock(int blockId) {
            if (blockId < 0 || blockId >= blocks()) {
                throw new IndexOutOfBoundsException(
                        "Block index out of bounds");
            }
        }

        int[] snapshot() {
            return data.clone();
        }
    }

    static final class Page {
        final int[] values;
        boolean dirty;

        Page(int[] values) {
            this.values = values;
        }
    }

    static final class LruBuffer {
        final BlockDevice device;
        final int capacityBlocks;
        final LinkedHashMap<Integer, Page> pages =
                new LinkedHashMap<>(16, 0.75f, true);
        long evictions;

        LruBuffer(BlockDevice device, int capacityBlocks) {
            this.device = Objects.requireNonNull(device);
            if (capacityBlocks < 1) {
                throw new IllegalArgumentException(
                        "Need at least one buffer frame");
            }
            this.capacityBlocks = capacityBlocks;
        }

        Page page(int blockId) {
            Page found = pages.get(blockId);
            if (found != null) return found;
            if (pages.size() == capacityBlocks) {
                Iterator<Map.Entry<Integer, Page>> it =
                        pages.entrySet().iterator();
                Map.Entry<Integer, Page> eldest = it.next();
                if (eldest.getValue().dirty) {
                    device.writeBlock(
                            eldest.getKey(), eldest.getValue().values);
                }
                it.remove();
                evictions++;
            }
            Page loaded = new Page(device.readBlock(blockId));
            pages.put(blockId, loaded);
            return loaded;
        }

        int read(int index) {
            checkIndex(index);
            Page p = page(index / device.blockSize);
            return p.values[index % device.blockSize];
        }

        void set(int index, int value) {
            checkIndex(index);
            Page p = page(index / device.blockSize);
            p.values[index % device.blockSize] = value;
            p.dirty = true;
        }

        void checkIndex(int index) {
            if (index < 0 || index >= device.data.length) {
                throw new IndexOutOfBoundsException(
                        "Record index out of bounds");
            }
        }

        void flush() {
            for (Map.Entry<Integer, Page> entry : pages.entrySet()) {
                if (entry.getValue().dirty) {
                    device.writeBlock(
                            entry.getKey(), entry.getValue().values);
                    entry.getValue().dirty = false;
                }
            }
        }
    }

    static final class RunCursor {
        final BlockDevice disk;
        final int endExclusive;
        int position;
        int loadedBlock = -1;
        int[] buffer;

        RunCursor(BlockDevice disk, int begin, int end) {
            this.disk = disk;
            position = begin;
            endExclusive = end;
        }

        boolean hasNext() {
            return position < endExclusive;
        }

        int peek() {
            if (!hasNext()) throw new NoSuchElementException();
            int blockId = position / disk.blockSize;
            if (blockId != loadedBlock) {
                buffer = disk.readBlock(blockId);
                loadedBlock = blockId;
            }
            return buffer[position % disk.blockSize];
        }

        int take() {
            int result = peek();
            position++;
            return result;
        }
    }

    // Input: two individually sorted contiguous runs.
    // Boundaries must align to B and output has its own device.
    static void mergeTwoSortedRuns(
            BlockDevice source, int split, BlockDevice output) {
        Objects.requireNonNull(source);
        Objects.requireNonNull(output);
        int b = source.blockSize;
        if (output.blockSize != b
                || source.data.length != output.data.length
                || source == output
                || split <= 0 || split >= source.data.length
                || split % b != 0) {
            throw new IllegalArgumentException(
                    "Require aligned independent input/output");
        }
        RunCursor left = new RunCursor(source, 0, split);
        RunCursor right = new RunCursor(
                source, split, source.data.length);
        int[] out = new int[b];
        int used = 0, outBlock = 0, produced = 0;

        while (left.hasNext() || right.hasNext()) {
            int value;
            if (!right.hasNext()
                    || left.hasNext()
                    && left.peek() <= right.peek()) {
                value = left.take();
            } else {
                value = right.take();
            }
            out[used++] = value;
            produced++;
            if (used == b) {
                output.writeBlock(outBlock++, out);
                used = 0;
                out = new int[b];
            }
        }
        if (produced != source.data.length || used != 0) {
            throw new AssertionError("Incomplete merged run");
        }
    }

    static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    static final int[] SAMPLE = {
            8, 3, 7, 1, 6, 2, 5, 4,
            13, 11, 15, 9, 10, 16, 12, 14
    };

    static void example() {
        BlockDevice scanDisk = new BlockDevice(SAMPLE, 4);
        LruBuffer scan = new LruBuffer(scanDisk, 2);
        int sum = 0;
        for (int i = 0; i < SAMPLE.length; i++) {
            sum += scan.read(i);
        }
        check(sum == 136 && scanDisk.reads == 4
                && scanDisk.writes == 0,
                "Sequential scan has one transfer per block");
        System.out.println("Sequential scan: sum=" + sum
                + ", blockReads=" + scanDisk.reads
                + ", blockWrites=" + scanDisk.writes);

        BlockDevice randomDisk = new BlockDevice(SAMPLE, 4);
        LruBuffer random = new LruBuffer(randomDisk, 2);
        int randomSum = 0;
        for (int index : new int[] {0, 4, 8, 12, 0, 4, 8, 12}) {
            randomSum += random.read(index);
        }
        check(randomSum == 74 && randomDisk.reads == 8,
                "Round-robin working set thrashes 2 frames");
        System.out.println("Round-robin reads: sum=" + randomSum
                + ", blockReads=" + randomDisk.reads
                + ", evictions=" + random.evictions);

        BlockDevice writeDisk = new BlockDevice(SAMPLE, 4);
        LruBuffer writeBack = new LruBuffer(writeDisk, 2);
        for (int index : new int[] {0, 4, 8, 12}) {
            writeBack.set(index, writeBack.read(index) + 100);
        }
        writeBack.flush();
        int[] changed = {
                108, 3, 7, 1, 106, 2, 5, 4,
                113, 11, 15, 9, 110, 16, 12, 14
        };
        check(Arrays.equals(writeDisk.snapshot(), changed)
                && writeDisk.reads == 4 && writeDisk.writes == 4
                && writeBack.evictions == 2,
                "Dirty pages require write-back on eviction/flush");
        System.out.println("Write-back: blockReads="
                + writeDisk.reads + ", blockWrites="
                + writeDisk.writes + ", evictions="
                + writeBack.evictions);
        System.out.println("Write-back data: "
                + Arrays.toString(writeDisk.snapshot()));

        BlockDevice localDisk = new BlockDevice(SAMPLE, 4);
        LruBuffer local = new LruBuffer(localDisk, 2);
        for (int i = 0; i < 4; i++) {
            local.set(i, local.read(i) + 1);
        }
        local.flush();
        check(localDisk.reads == 1 && localDisk.writes == 1,
                "Four record writes share one dirty disk block");
        System.out.println("Four edits in one block: blockReads="
                + localDisk.reads + ", blockWrites=" + localDisk.writes);

        int[] runs = {
                1, 4, 7, 10, 13, 16, 19, 22,
                2, 3, 8, 9, 14, 15, 20, 21
        };
        BlockDevice input = new BlockDevice(runs, 4);
        BlockDevice output = new BlockDevice(new int[16], 4);
        mergeTwoSortedRuns(input, 8, output);
        int[] merged = output.snapshot();
        int[] expected = runs.clone();
        Arrays.sort(expected);
        check(Arrays.equals(merged, expected)
                && input.reads == 4 && input.writes == 0
                && output.reads == 0 && output.writes == 4,
                "Two-way merge must read/write each block once");
        System.out.println("Two-run merge: readBlocks=" + input.reads
                + ", writtenBlocks=" + output.writes
                + ", sorted=" + Arrays.toString(merged));
    }

    static void randomOracleTests() {
        SplittableRandom rng = new SplittableRandom(20261110L);
        for (int trial = 0; trial < 500; trial++) {
            int[] seedData = new int[32];
            for (int i = 0; i < seedData.length; i++) {
                seedData[i] = rng.nextInt(-1000, 1001);
            }
            int[] oracle = seedData.clone();
            BlockDevice disk = new BlockDevice(seedData, 4);
            LruBuffer cache = new LruBuffer(disk, 1 + rng.nextInt(4));
            for (int step = 0; step < 120; step++) {
                int index = rng.nextInt(oracle.length);
                if (rng.nextBoolean()) {
                    int value = rng.nextInt(-5000, 5001);
                    cache.set(index, value);
                    oracle[index] = value;
                } else {
                    check(cache.read(index) == oracle[index],
                            "Cache returned stale data");
                }
                if (step % 17 == 0) cache.flush();
            }
            cache.flush();
            check(Arrays.equals(disk.snapshot(), oracle),
                    "Flushed disk differs from independent array");
        }

        for (int trial = 0; trial < 300; trial++) {
            int[] values = new int[16];
            for (int i = 0; i < values.length; i++) {
                values[i] = rng.nextInt(-100, 101);
            }
            Arrays.sort(values, 0, 8);
            Arrays.sort(values, 8, 16);
            BlockDevice input = new BlockDevice(values, 4);
            BlockDevice output = new BlockDevice(new int[16], 4);
            mergeTwoSortedRuns(input, 8, output);
            int[] oracle = values.clone();
            Arrays.sort(oracle);
            check(Arrays.equals(output.snapshot(), oracle),
                    "Random merge mismatches Array.sort");
            check(input.reads == 4 && output.writes == 4
                    && input.writes == 0 && output.reads == 0,
                    "Unexpected transfer count");
        }
        System.out.println(
                "Oracle QA: PASS (500 cached workloads, "
                + "60000 record operations, 300 merges)");
    }

    public static void main(String[] args) {
        example();
        randomOracleTests();
    }
}
```

### 15.2. Chạy bằng JDK 17+

Lưu đúng tên file rồi chạy:

```bash
javac ExternalMemoryBlockCostDemo.java
java ExternalMemoryBlockCostDemo
```

**Stdout chính xác với seed trong chương trình:**

```text
Sequential scan: sum=136, blockReads=4, blockWrites=0
Round-robin reads: sum=74, blockReads=8, evictions=6
Write-back: blockReads=4, blockWrites=4, evictions=2
Write-back data: [108, 3, 7, 1, 106, 2, 5, 4, 113, 11, 15, 9, 110, 16, 12, 14]
Four edits in one block: blockReads=1, blockWrites=1
Two-run merge: readBlocks=4, writtenBlocks=4, sorted=[1, 2, 3, 4, 7, 8, 9, 10, 13, 14, 15, 16, 19, 20, 21, 22]
Oracle QA: PASS (500 cached workloads, 60000 record operations, 300 merges)
```

### 15.3. Giải thích kết quả Java

**Sequential scan:** Quét 16 record nằm trong bốn block, mỗi block B=4 được đọc một lần. Tổng giá trị 136 xác nhận dữ liệu trả về đúng.

**Round-robin reads:** Tám truy cập tới các block 0,1,2,3,0,1,2,3. Với cache LRU chỉ chứa hai block, tất cả miss, dẫn đến 8 lần read và 6 lần eviction. Các eviction này đều clean nên **không ghi**.

**Write-back:** Mỗi trong bốn block bị sửa đúng một lần. Hai dirty block đầu bị ghi khi eviction, hai dirty block cuối được ghi khi flush. Bốn block reads và bốn block writes, dữ liệu cuối đúng mảng mong đợi. Nếu quên flush, hai trang cuối vẫn có thể chỉ nằm trong RAM mô phỏng.

**Four edits in one block:** Bốn lần read-modify-write ở cùng block chỉ làm phát sinh một block read và một block write khi flush. Đây là lợi ích của locality và write coalescing.

**Two-run merge:** Hai run đã sắp xếp có tổng 16 phần tử. Thuật toán dùng hai input buffers và một output buffer, đọc mỗi block input đúng một lần và ghi mỗi block output đúng một lần. Kết quả tăng dần chính xác như `Arrays.sort` trên toàn mảng, tổng 4 reads +4 writes.

**Oracle QA:** 500 workload ×120 truy cập = **60.000 thao tác bản ghi** đối chiếu với mảng chính xác, với số frame cache ngẫu nhiên từ 1 tới 4. Ngoài ra 300 lần tạo hai run sorted ngẫu nhiên rồi merge, so toàn bộ kết quả với `Arrays.sort`. Đếm khối được kiểm thử cùng bất biến về nội dung. Các kết quả này xác minh **mã mô phỏng**, không chứng minh thời gian SSD thật hoặc hiệu năng trên mọi workload ngoài máy.

## 16. Chứng minh bất biến cache và I/O

### 16.1. Bất biến “mỗi block trong cache có đúng nội dung logic mới nhất”

Với một block b:

- Nếu nó không nằm trong cache, phiên bản bền vững đã commit sau lần eviction/flush cuối nằm trong `BlockDevice`.
- Nếu nó ở cache và sạch, nội dung cache bằng nội dung device.
- Nếu nó ở cache và dirty, cache chứa các sửa đổi chưa được ghi vào device.
- Khi eviction dirty, ghi toàn bộ block về device trước khi loại trang.
- Khi flush, ghi mọi trang dirty còn lại rồi đánh dấu sạch.

Bằng quy nạp trên `read`, `set`, eviction và `flush`, mọi `read(index)` đi qua cache đều nhìn thấy **giá trị logic mới nhất trong chuỗi thao tác một luồng**. Sau `flush` thành công, `snapshot()` của disk mô phỏng khớp mảng oracle.

**Chú ý:** Nếu một `writeBlock` thất bại do lỗi I/O thật, cần xử lý lỗi và chính sách phục hồi; `BlockDevice` chỉ là một mảng không có lỗi thiết bị. Chứng minh trên không tự áp dụng khi nhiều luồng đồng thời thay đổi dữ liệu không được đồng bộ.

### 16.2. Đếm số read trong merge

Mỗi `RunCursor` giữ một block tại một thời điểm. Khi vị trí cursor tiến sang block mới, nó gọi `readBlock` một lần. Vì cursor chỉ **tăng vị trí**, không quay lại, mỗi block thuộc run đó được đọc tối đa một lần. Hai run bao phủ toàn bộ N record, không chồng lấn và chia đúng theo block, nên:

```text
Q_read = N/B.
```

Output buffer cứ đủ B record thì ghi một lần; tổng N chia hết B trong mã, nên:

```text
Q_write = N/B.
```

Vì hai run được trộn đúng và không bỏ/thêm record:

```text
Q_total = 2N/B.
```

Đây là **đẳng thức của ví dụ được thiết kế với block đầy**, không phải lời hứa cho mọi file chưa căn chỉnh hoặc mọi pipeline đọc ghi có nén/cache.

## 17. Các lỗi thường gặp

1. Chỉ đếm phép so sánh CPU khi dữ liệu lớn hơn RAM.
2. Đồng nhất một lần đọc record với một lần đọc block.
3. Coi mọi truy cập `a[i]` trên disk đều có chi phí ngang nhau.
4. Không định nghĩa N, M, B và đơn vị **record/byte** rõ ràng.
5. Lấy `N/B` nhưng quên làm tròn lên khi block cuối chưa đầy.
6. Giả định dữ liệu đã nằm RAM nhưng vẫn đếm nạp đĩa lần đầu như miss chắc chắn.
7. Coi quét lại dữ liệu luôn cần N/B I/O dù toàn bộ N có thể vẫn trong cache.
8. Coi truy cập random có cùng locality như quét liên tục.
9. Không xét working set lớn hơn số frame RAM.
10. Cho rằng LRU luôn tối ưu cho mọi chuỗi truy cập.
11. Nhầm cache hit với block read.
12. Nhầm eviction của trang clean với block write.
13. Quên ghi dirty page trước khi eviction.
14. Quên `flush` và tưởng dữ liệu disk đã phản ánh mọi update trong RAM.
15. Đếm một write cho mỗi thao tác set trong cơ chế write-back.
16. Không gom nhiều sửa cùng block trước khi ghi.
17. Ghi đè toàn block mới nhưng vẫn đọc output block cũ không cần thiết.
18. Sửa một phần block mà không bảo toàn các record không được thay đổi.
19. Coi flush mô phỏng đồng nghĩa đã đạt durable fsync trên SSD.
20. Coi I/O count là thời gian wall-clock chính xác.
21. Coi một block read và block write luôn có cùng latency thực tế.
22. Tuyên bố thiết bị SSD không còn chênh lệch random/sequential I/O.
23. Không tính chi phí write amplification hoặc compaction trong storage engine.
24. Trộn hai run với chỉ một input buffer và không quản lý các trang luân phiên.
25. Cấp hai input blocks cộng một output block khi M<3B.
26. Quên mỗi run phải được sắp xếp trước khi dùng merge logic.
27. Quên ghi phần block output cuối khi số record không chia hết B.
28. Gán kết quả trộn đúng nhưng làm mất/lặp các phần tử có khóa bằng nhau.
29. Không phân biệt số lần truyền khối và số phép so sánh trong priority queue.
30. Chỉ tăng fan-in mà quên RAM phải có ít nhất một output buffer.
31. Dùng `log_F R` khi F=1, phép log không hợp lệ và không giảm run count.
32. Gọi sắp xếp một triệu phần tử ngoài RAM là O(N log N) I/O mà không phân tích B,M.
33. Bỏ I/O của pha tạo run khi tính external merge sort.
34. Đếm một merge pass như N/B reads mà quên ghi N/B output blocks.
35. Bỏ sự khác biệt giữa index lookup và đọc record data page.
36. Coi B-tree luôn cần đúng một page read cho toàn bộ lookup.
37. Coi binary search trên disk giống hệt binary search trong RAM.
38. Không tính root/index pages được cache khi ước lượng lookup thực tế.
39. Gắn nhãn “cache-oblivious” chỉ vì mã có đệ quy.
40. Coi một benchmark với OS page cache nóng là chi phí I/O đĩa lạnh.
41. So một bộ đếm I/O mô phỏng với cache miss hardware như cùng đơn vị.
42. Đo dung lượng khối theo byte nhưng áp trực tiếp B như số record cố định.
43. Bỏ qua chi phí nén/giải nén hoặc serialization khi chuyển sang hệ thống thật.
44. Thiết kế thuật toán out-of-core nhưng giữ toàn bộ N trong một mảng RAM trước khi bắt đầu.
45. Không kiểm thử random read/write, dirty eviction, flush và merge bằng oracle độc lập.

## 18. Bài tập tự luyện có đáp án

**Bài 1.** N,M,B lần lượt biểu thị gì?

**Đáp án:** N là số record đầu vào; M là dung lượng RAM dành cho thuật toán; B là số record trên một block I/O trong mô hình giản lược.

**Bài 2.** Nếu N=1000, B=100, quét toàn bộ từ disk lạnh cần bao nhiêu block reads?

**Đáp án:** 10.

**Bài 3.** Nếu N=1001, B=100?

**Đáp án:** `ceil(1001/100)=11`.

**Bài 4.** N=16, B=4, M=8, có bao nhiêu disk blocks và RAM frames?

**Đáp án:** 4 disk blocks và 2 RAM frames.

**Bài 5.** Đọc index 0,1,2,3 với B=4 và cache trống cần bao nhiêu block read?

**Đáp án:** 1, nếu block 0 không bị đẩy ra giữa các đọc.

**Bài 6.** Đọc index 0,4,8,12 với B=4, cache lạnh 2 frames, bao nhiêu reads?

**Đáp án:** 4 block reads.

**Bài 7.** Lặp dãy 0,4,8,12 hai lần, cache LRU 2 frames, bao nhiêu reads?

**Đáp án:** 8 block reads; 6 evictions.

**Bài 8.** Evict một trang clean có tạo block write không?

**Đáp án:** Không, vì dữ liệu không thay đổi so với device.

**Bài 9.** Evict một trang dirty ở write-back có tạo write không?

**Đáp án:** Có, nếu chưa có cơ chế ghi khác lưu các thay đổi; mô hình demo ghi trước khi loại.

**Bài 10.** Sửa bốn record thuộc cùng một block rồi flush, block đọc/ghi bao nhiêu lần?

**Đáp án:** Nếu block ban đầu chưa có cache, 1 read và 1 write.

**Bài 11.** Sửa một record trong mỗi bốn block, LRU 2 frames, rồi flush?

**Đáp án:** 4 reads, 4 writes, 2 evictions dirty.

**Bài 12.** Một thuật toán thực hiện 1 triệu phép cộng trên dữ liệu vừa ở cache có cần 1 triệu I/O không?

**Đáp án:** Không. I/O đếm truyền khối, không đếm phép toán nội bộ.

**Bài 13.** Khi nào quét dữ liệu N record có I/O Theta(N/B)?

**Đáp án:** Khi phải đọc toàn bộ dữ liệu từ bộ nhớ ngoài và các record được lưu tuần tự theo block B.

**Bài 14.** Hai run có tổng N=16, B=4, một merge pass đọc bao nhiêu block?

**Đáp án:** 4.

**Bài 15.** Cùng phép trộn, nếu output được ghi full-block thì cần bao nhiêu block writes?

**Đáp án:** 4.

**Bài 16.** Hai-run merge buffer một block mỗi input và một output cần ít nhất bao nhiêu RAM?

**Đáp án:** 3B record.

**Bài 17.** Tại sao two-way merge có thể đạt O(N/B) I/O dù làm O(N) so sánh?

**Đáp án:** Vì mỗi block đầu vào chỉ đọc một lần, mỗi block đầu ra chỉ ghi một lần, còn so sánh diễn ra trong RAM.

**Bài 18.** M/B=10 frame, cần 1 output frame, fan-in tối đa bao nhiêu?

**Đáp án:** 9 run đầu vào trong mô hình buffer đơn giản.

**Bài 19.** Có R=81 run, fan-in F=3, cần bao nhiêu pass merge?

**Đáp án:** `ceil(log_3 81)=4`.

**Bài 20.** Tạo run từ N record khi mỗi run được sort trong RAM cần cỡ bao nhiêu I/O?

**Đáp án:** Khoảng N/B reads + N/B writes, tổng 2N/B.

**Bài 21.** Vì sao merge pass thêm chi phí ghi?

**Đáp án:** Vì phải lưu run đầu ra đã trộn ra bộ nhớ ngoài, không chỉ đọc input.

**Bài 22.** Với N=1.000.000, B=1.000, M=100.000, có mấy run ban đầu?

**Đáp án:** 10 run.

**Bài 23.** Fan-in tối đa theo buffer đơn giản ở bài 22?

**Đáp án:** `floor(100000/1000)-1=99`.

**Bài 24.** Với 10 run và fan-in 99, cần mấy merge pass?

**Đáp án:** 1.

**Bài 25.** Tổng I/O ước lượng ở bài 22–24?

**Đáp án:** 2000 truyền khối tạo run +2000 truyền khối merge = khoảng 4000.

**Bài 26.** Vì sao B-tree có ít I/O hơn BST node-per-page trong nhiều trường hợp?

**Đáp án:** B-tree lưu nhiều key/con trỏ trên một page, fan-out lớn, giảm chiều cao tính theo page.

**Bài 27.** B-tree search có độ phức tạp block transfers thường viết thế nào?

**Đáp án:** O(log_B N), dưới giả thiết fan-out Theta(B) và cấu trúc cân bằng.

**Bài 28.** B-tree có bảo đảm cần đúng O(log_B N) page từ disk lạnh cho từng query không?

**Đáp án:** Đây là cận asymptotic; các trang đã cache và cách bố trí dữ liệu có thể giảm I/O thực.

**Bài 29.** Full scan có thể tốt hơn index khi nào?

**Đáp án:** Khi truy vấn lấy phần lớn dữ liệu liên tiếp, index có thể gây nhiều lần đọc record rải rác.

**Bài 30.** Phân biệt cache-aware với cache-oblivious.

**Đáp án:** Cache-aware dùng M,B trong cấu hình/thuật toán; cache-oblivious không hardcode chúng nhưng được phân tích trong mô hình cache thích hợp.

**Bài 31.** Trong write-back, vì sao nhiều sửa đổi gần nhau có thể ít I/O hơn sửa phân tán?

**Đáp án:** Vì những sửa đổi chung block có thể gom trước khi ghi một lần.

**Bài 32.** Ghi 1 record logic có luôn tương đương 1 SSD write vật lý không?

**Đáp án:** Không; buffer cache, filesystem, WAL, compaction và thiết bị có thể thay đổi số ghi thật.

**Bài 33.** Một thuật toán chỉ so 100 key nhưng lần nào cũng load block mới có thể tốn hơn scan 1000 key không?

**Đáp án:** Có thể, nếu scan có locality và B đủ lớn; phải so block I/O, không chỉ số phép so.

**Bài 34.** Chương trình Java trong bài có đo latency SSD thật không?

**Đáp án:** Không; `BlockDevice` dùng mảng trong RAM và đếm block transfers logic.

**Bài 35.** Nêu hai tiêu chí QA quan trọng cho bộ đệm write-back.

**Đáp án:** Đọc luôn trả dữ liệu logic mới nhất, và sau flush nội dung device khớp oracle; đồng thời đếm read/write và dirty eviction đúng.

## 19. Checklist triển khai

- [ ] Đã định nghĩa N, M, B và đơn vị record/byte?
- [ ] N có vượt RAM không; dữ liệu nào thật sự nằm trong RAM?
- [ ] Có phân biệt record operations với block transfers?
- [ ] Đã tính `ceil(N/B)` khi block cuối không đầy?
- [ ] Đã xác định trình tự truy cập và locality?
- [ ] Số RAM frames `floor(M/B)` có đủ cho các input/output buffers?
- [ ] Có xét cache hit/miss và eviction khi working set vượt RAM?
- [ ] Dirty page có được ghi đúng trước khi bị thay thế?
- [ ] Có flush và kiểm tra dữ liệu bền vững theo đúng hợp đồng hệ thống?
- [ ] Những sửa đổi cùng block có thể gom ghi không?
- [ ] Đầu ra mới có thể ghi nguyên block mà không đọc lại?
- [ ] Với merge, mỗi run đã sorted và output không bỏ/trùng record?
- [ ] Với external sort, đã tính **pha tạo run và mọi merge pass**?
- [ ] Fan-in F≥2 và không vượt số frame RAM trừ output buffer?
- [ ] Đã phân tích CPU complexity riêng với I/O complexity?
- [ ] Nếu dùng B-tree/index, đã phân biệt index pages và data pages?
- [ ] Nếu dùng LSM/compaction, đã tính write amplification?
- [ ] Có xác định read/write tương ứng logical block hay physical device I/O?
- [ ] Benchmark có kiểm soát page cache nóng/lạnh và record size?
- [ ] Có bài test oracle cho scan, random access, dirty eviction, flush và merge?

## Kết luận

Trong mô hình ngoài bộ nhớ, **đơn vị chi phí chính là một lần truyền block gồm B record** giữa RAM sức chứa M và vùng dữ liệu N record trên bộ nhớ ngoài:

```text
Q_total = Q_read + Q_write.

Scan(N) = Theta(1+N/B).

Two-way block merge:
  ~N/B reads + N/B writes.

External comparison sorting, N>>M:
  O((N/B)*(1+log_{M/B}(N/B))) I/Os
  under appropriate model assumptions.

B-tree point lookup:
  O(log_B N) I/Os in a balanced page-oriented layout.
```

Cùng một số thao tác record, thuật toán **quét tuần tự, tận dụng block và gom write** thường cần ít truyền khối hơn thuật toán truy cập phân tán hoặc liên tục gây cache eviction. Thiết kế dữ liệu theo block, sử dụng buffer có chủ đích, chọn fan-in phù hợp RAM và tách **số I/O** khỏi **thời gian CPU/thiết bị thực** là nền tảng của thuật toán ngoài bộ nhớ.

Chương trình Java đã cho thấy sự khác biệt này bằng các bộ đếm chính xác, chứng minh bất biến read/write-back và kiểm thử bằng oracle. Khi chuyển sang hệ thống thực, phải bổ sung I/O thật, lỗi thiết bị, concurrency và durability; bản thân mô hình khối là công cụ **phân tích thuật toán**, không phải cam kết về tốc độ hoặc an toàn dữ liệu của một hệ lưu trữ cụ thể.

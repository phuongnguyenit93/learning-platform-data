# Giảm truy cập ngẫu nhiên và số lượt quét

Khi dữ liệu lớn hơn RAM, một thuật toán có thời gian CPU O(n log n) vẫn có thể chạy rất chậm nếu nó liên tục yêu cầu những bản ghi nằm rải rác trên ổ lưu trữ. Trong các bài toán **ngoài bộ nhớ (external-memory algorithms)**, không thể chỉ đếm phép so sánh, phép cộng hoặc vòng lặp: phải hỏi **dữ liệu di chuyển giữa RAM và bộ nhớ ngoài thành bao nhiêu khối, có bao nhiêu lần tìm vị trí ngẫu nhiên và phải đọc đi đọc lại toàn bộ tập dữ liệu bao nhiêu lượt**.

Hai chiến lược cốt lõi:

1. **Giảm truy cập ngẫu nhiên:** nhóm các yêu cầu nhỏ, đọc/ghi theo khối lớn và theo thứ tự vật lý hoặc thứ tự key, hạn chế nhảy giữa các vị trí xa nhau.
2. **Giảm số lượt quét (passes):** xử lý nhiều công việc trong cùng một lần đọc, tạo run dài, trộn nhiều run đồng thời, phân vùng đủ lớn để xử lý mỗi phân vùng một lần và tránh đọc lại toàn bộ tệp cho từng truy vấn.

Đây là bài thuộc nhóm **Ngoài bộ nhớ**, tập trung vào mô hình I/O theo khối, thuật toán quét tuần tự, **external merge sort**, số lượt trộn và fan-in, blocking/buffering, batch processing, sort-based processing, hash partition, tác động của HDD/SSD, tính đúng khi streaming và các phép đo thực tế.

Một bài toán mẫu là sắp xếp **N bản ghi nguyên** khi chỉ có đủ RAM cho một đoạn nhỏ dữ liệu. Bài cung cấp chương trình **Java 17+ độc lập** thực sự ghi dữ liệu ra **tệp nhị phân tạm**, đọc từng đoạn được giới hạn kích thước, tạo các run đã sắp xếp, rồi **trộn nhiều run bằng các luồng tuần tự**. Kết quả mẫu và thống kê số lượt đọc/ghi **bản ghi logic** được kiểm thử độc lập. Đừng nhầm thống kê bản ghi logic với số thao tác I/O vật lý: cache của hệ điều hành và kích thước buffer làm hai số này khác nhau.

## 1. Bài toán đặt ra khi dữ liệu không nằm trọn trong RAM

Giả sử cần xử lý một tệp chứa N=100 triệu bản ghi, nhưng RAM có thể cấp cho thuật toán chỉ đủ giữ một phần nhỏ.

Nếu một thuật toán liên tục nhảy tới một bản ghi ngẫu nhiên:

- Mỗi lần nhảy có thể khiến hệ thống phải đọc một trang hoặc block chưa có trong cache.
- Với ổ đĩa cơ học, thao tác tìm vị trí (seek) có thể đắt hơn rất nhiều so với việc đọc tuần tự các block liền kề.
- Với SSD/NVMe, chi phí seek cơ học biến mất nhưng random I/O nhỏ vẫn có overhead, giới hạn IOPS, contention và write amplification; truy cập tuần tự hoặc batched thường vẫn có lợi.
- Nếu RAM không chứa đủ working set, cache có thể bị thay trang liên tục, dẫn tới nhiều lần đọc cùng dữ liệu.

Trong khi đó, một chương trình đọc liên tiếp các block và gom nhiều bản ghi mỗi lần có thể tận dụng:

- Bộ nhớ đệm cấp tệp và cache của hệ điều hành.
- Readahead/prefetch.
- I/O request lớn.
- Ít lần gọi hệ thống hơn trên mỗi bản ghi.
- Băng thông đọc/ghi tuần tự ổn định.

**Kết luận đầu tiên:** cùng một số phép toán CPU, hai lịch truy cập dữ liệu khác nhau có thể có thời gian chạy thực tế khác nhau rất lớn.

## 2. Hai mô hình chi phí phải tách riêng

**Mô hình RAM** truyền thống thường coi truy cập một phần tử mảng hoặc một phép toán word là O(1), rồi phân tích tổng số phép toán.

**Mô hình ngoài bộ nhớ (external-memory/I/O model)** thường xét:

- **N:** số bản ghi (hoặc phần tử) đầu vào.
- **M:** số bản ghi có thể giữ trong RAM làm việc.
- **B:** số bản ghi trong một block truyền giữa RAM và bộ nhớ ngoài.
- **I/O:** một lần truyền một block giữa hai tầng.
- Thường giả sử **M≥2B**, và muốn trộn nhiều luồng hiệu quả thì cần M lớn hơn số input/output buffers.
- Giả sử các bản ghi cùng kích thước trong phân tích cơ bản; trường hợp variable-length phải chuyển sang byte capacity và các thuật toán packing phù hợp.

Đơn vị của M và B phải **giống nhau**. Nếu N đếm số bản ghi, thì M và B cũng tính theo bản ghi. Nếu một bản ghi dài 100 byte và buffer có 1 MB, số bản ghi mỗi buffer phải tính từ kích thước thực (bao gồm encoding/metadata), không tự lấy B=1 MB rồi đưa vào công thức N/B của số bản ghi.

### Chi phí scan

Đọc tuần tự toàn bộ N bản ghi cần khoảng:

**Scan(N)=Θ(⌈N/B⌉) lần truyền block**,

bỏ qua hiệu ứng block đầu/cuối chưa đầy.

Nếu đọc rồi ghi lại toàn bộ dữ liệu sang tệp khác, cần xấp xỉ:

**2⌈N/B⌉ lần truyền block**,

một lượt đọc và một lượt ghi, chưa tính metadata, cache miss khác, đồng bộ dữ liệu và write amplification.

### RAM model và I/O model không phủ định nhau

Cần phân tích **cả CPU lẫn I/O**. Một thuật toán có ít block transfers nhưng nén/giải nén hoặc so sánh bản ghi quá đắt vẫn có thể chậm; một thuật toán ít phép so sánh nhưng random I/O quá nhiều cũng có thể chậm.

## 3. Truy cập ngẫu nhiên, tuần tự và số lượt quét khác nhau thế nào?

**Random access** trong ngữ cảnh này là đọc/ghi những vị trí không liên tiếp, khiến hệ thống có thể phải chuyển block, chuyển vị trí hoặc phát nhiều request nhỏ.

**Sequential access** là đi qua dữ liệu theo thứ tự vật lý, thường đọc/ghi các block liền kề và dễ gom thành request lớn.

**Pass/scan** là một lượt đi qua toàn bộ hoặc một phần đáng kể của tập dữ liệu.

Ba đại lượng không đồng nhất:

- Một pass tuần tự có thể đọc N bản ghi bằng khoảng N/B block transfers.
- Một pass xử lý các record theo thứ tự key ngẫu nhiên có thể vẫn tạo rất nhiều random I/O, dù mỗi record được đọc đúng một lần ở mức logic.
- Một thuật toán không nhảy ngẫu nhiên nhưng quét toàn bộ tệp 100 lần vẫn rất tốn I/O.
- Một chương trình đọc nhiều lần cùng block từ page cache có thể không phát I/O vật lý tương ứng, nhưng vẫn có chi phí RAM/cache và syscall.

**Không được báo “1 pass” rồi suy ra chắc chắn tối ưu I/O.** Cần xem pass đó được thực hiện như thế nào và dữ liệu thực tế được truyền từ tầng nào.

## 4. Ước lượng kích thước trước khi chọn thuật toán

Giả sử bản ghi có kích thước cố định s byte. Tổng kích thước thô:

**D≈N·s byte**,

chưa tính headers, index, alignment, checksum và nén.

Với RAM làm việc R byte và block size b byte:

**M≈floor(R/s)** bản ghi.

**B≈floor(b/s)** bản ghi.

Trong thực tế không nên cấp toàn bộ R cho một mảng dữ liệu: còn heap, GC, các input/output buffers, file descriptors, hàng đợi, metadata và bộ nhớ cho runtime.

### Ví dụ mô hình tính theo bản ghi

Cho:

**N=12.000.000** bản ghi.

**M=1.048.576** bản ghi trong RAM.

**B=1.024** bản ghi/block.

Có thể tạo:

**ceil(N/M)=12** run ban đầu.

Nếu trộn bằng 1 output block và một input block cho mỗi run, số input streams tối đa theo mô hình đệm là:

**k≤floor(M/B)−1=1.023**.

Vì chỉ có 12 run, một merge round là đủ sau run generation.

Một lượt đọc tuần tự cần khoảng **ceil(N/B)=11.719 block reads**. Nếu run generation và lượt merge đều đọc rồi ghi toàn bộ N bản ghi, số block transfers lý tưởng là khoảng:

**2 stages × (11.719 reads + 11.719 writes)=46.876**.

Đây là **ước lượng mô hình**. Số block ở đuôi từng run, kích thước vật lý, tệp đích, filesystem và cache có thể làm con số I/O thật khác.

## 5. Từ đọc một bản ghi đến đọc theo block

Cách tiếp cận kém khi dữ liệu trên đĩa:

~~~text
for each requested record id:
    seek to its offset
    read just that record
    process it
~~~

Nếu ID gần như ngẫu nhiên và dataset lớn hơn RAM, mỗi record có thể kéo theo một block transfer riêng. Chi phí có thể gần **Θ(N)** I/Os cho N yêu cầu, thay vì **Θ(N/B)** I/Os khi dữ liệu được đọc theo thứ tự block.

### Batch và sắp xếp yêu cầu I/O

Nếu các request cho phép reorder:

1. Gom một batch các ID cần đọc.
2. Sắp xếp theo block offset vật lý.
3. Đọc các block theo thứ tự tăng dần.
4. Trong mỗi block, xử lý mọi ID liên quan.
5. Ghi kết quả theo **original request ID** để giữ đúng thứ tự trả về.

Nếu có nhiều ID cùng nằm trong một block, chỉ cần một lần đọc block trong batch nếu buffer còn giữ được nó.

### Khi không được reorder?

Nếu các thao tác có phụ thuộc thứ tự hoặc side effects, sắp xếp lại có thể làm thay đổi kết quả. Ví dụ các phép ghi xen kẽ vào cùng bản ghi, hay query cần nhìn đúng snapshot tại một thời điểm, không được tự hoán vị.

**Optimization chỉ hợp lệ nếu bảo toàn ngữ nghĩa dữ liệu và ràng buộc nhất quán.**

## 6. Giảm số lần gọi hệ thống bằng buffering

Một lời gọi read cho mỗi số nguyên 4 byte thường không phải cách hiệu quả để xử lý tệp lớn.

Sử dụng **buffered streams hoặc NIO ByteBuffer/FileChannel** để gom nhiều bản ghi:

~~~text
disk/filesystem
      |
   large block read
      |
memory buffer [many records]
      |
parse many records in memory
~~~

Ở chiều ghi:

~~~text
produce records
      |
append into output buffer
      |
flush large blocks
      |
filesystem/storage
~~~

### Không có buffer size tối ưu cho mọi hệ thống

Tăng buffer có thể giảm syscall và cải thiện throughput đến một ngưỡng. Quá nhiều buffer có thể:

- Chiếm RAM dành cho xử lý/merge fan-in.
- Tăng GC hoặc memory pressure.
- Tăng số dữ liệu dirty chưa flush.
- Làm mất cân bằng giữa các luồng I/O.

Trong ví dụ Java, mỗi stream dùng BufferedInputStream/BufferedOutputStream với bộ đệm byte cố định, nhưng số **lần I/O vật lý** vẫn do runtime và OS quyết định.

## 7. Một lượt quét, làm nhiều việc

Giảm số passes không nhất thiết phải có thuật toán phức tạp. Nếu một file lớn cần tính:

- Tổng một cột.
- Số bản ghi.
- Giá trị nhỏ nhất/lớn nhất.
- Số bản ghi thỏa điều kiện.
- Histogram trong miền hữu hạn.

Có thể **fuse** các phép tổng hợp vào **một lần đọc tuần tự**.

~~~text
count = 0
sum = 0
min = +infinity
max = -infinity

for each record in a single sequential scan:
    count++
    sum += value(record)
    min = min(min, value(record))
    max = max(max, value(record))
~~~

Nếu trước đó mỗi phép tính đọc lại cả tệp, số block reads có thể gần 4·N/B. Khi fuse, chỉ cần một lượt đọc gần N/B; đổi lại dùng thêm một ít RAM cho các accumulators.

### Trường hợp không thể fusion đơn giản

Nếu bước thứ hai cần **kết quả cuối** của bước thứ nhất để quyết định cách xử lý từng record, việc fuse có thể không khả thi. Ví dụ cần biết median toàn cục trước khi đánh dấu mỗi record lớn hơn median, trong một mô hình streaming chính xác và không đủ RAM lưu tất cả record. Khi đó có thể cần pass bổ sung, dữ liệu tạm hoặc thuật toán khác.

## 8. Pipeline, filter và projection sớm

Trong một pipeline dữ liệu, việc đọc những cột không dùng hoặc ghi tạm mọi bản ghi rồi mới lọc có thể tạo I/O thừa.

Các cải tiến thường có:

**Predicate pushdown:** lọc sớm những record không thỏa điều kiện trước khi đẩy vào các bước nặng như sort/join.

**Projection pushdown:** chỉ giữ các trường cần thiết; nếu định dạng lưu trữ columnar hỗ trợ đọc cột chọn lọc, có thể không phải đọc toàn bộ row payload.

**Pipeline operators:** nối các stage theo luồng để output của filter đi thẳng vào aggregate hoặc writer, không tạo tệp trung gian chỉ để đọc lại một lần.

**Late materialization:** trì hoãn đọc dữ liệu lớn cho tới khi có danh sách ID thực sự cần, nếu phù hợp với storage layout.

### Cần tránh lợi ích giả

Đọc một file row-oriented vẫn có thể phải mang toàn block vào RAM dù cuối cùng chỉ dùng một cột. Projection chỉ giảm I/O vật lý rõ khi bố trí dữ liệu và API hỗ trợ. Mỗi cải tiến phải được đánh giá trên **định dạng dữ liệu cụ thể**.

## 9. External merge sort: khung giải pháp

Khi N≫M, không thể gọi Arrays.sort lên toàn bộ file một cách an toàn nếu nó đòi đưa tất cả dữ liệu vào heap.

**External merge sort** gồm hai giai đoạn:

**Giai đoạn 1 — Run generation:**

1. Đọc tuần tự tối đa M bản ghi vào RAM.
2. Sắp xếp đoạn ấy trong RAM.
3. Ghi tuần tự ra một **run file** đã được sắp.
4. Lặp đến hết input.

Có khoảng:

**r=ceil(N/M)** run ban đầu,

nếu mỗi run giữ tối đa M bản ghi và bỏ qua overhead buffer.

**Giai đoạn 2 — Multiway merge:**

1. Mở tối đa k input run.
2. Mỗi input giữ một bộ đệm đọc; có một bộ đệm ghi output.
3. Dùng min-heap chứa phần tử đầu tiên của mỗi run.
4. Luôn lấy phần tử nhỏ nhất, ghi ra output, đọc phần tử tiếp theo từ chính run ấy.
5. Lặp cho tới khi tất cả input run cạn.
6. Nếu vẫn còn nhiều run sau một round, lặp merge round tiếp.

Mỗi lượt merge có thể biến tối đa k run thành một run mới mà vẫn duy trì thứ tự tăng dần.

## 10. Run generation: vì sao ghi run tuần tự tốt hơn sort ngẫu nhiên?

Một phương án sai hướng là giữ mọi record trong các cấu trúc nhỏ rồi cập nhật trực tiếp từng vị trí trên file kết quả theo thứ tự sắp xếp. Các phép ghi có thể trở thành random writes.

Thay vào đó, run generation:

- Chỉ đọc input theo thứ tự.
- Sort trong RAM, nơi random access rẻ hơn nhiều so với random disk access.
- Ghi output run theo thứ tự tăng dần, liên tiếp.

Ví dụ:

~~~text
Input:  [14, -5, 8, 8, 1, 0, 27, -9, 6, 3, 2, 2, -1, 13, 4, 7, -3]

Chunk size = 4 records

Run 0: [-5, 8, 8, 14]
Run 1: [-9, 0, 1, 27]
Run 2: [2, 2, 3, 6]
Run 3: [-1, 4, 7, 13]
Run 4: [-3]
~~~

Tất cả run đều được sort, nhưng **toàn bộ file đầu vào chưa được sort**. Cần merge các run trước khi xuất bản kết quả.

### Run generation có thể tối ưu thêm

**Replacement selection** dùng heap và các điều kiện để kéo dài run; trong một số mô hình dữ liệu ngẫu nhiên có thể tạo run dài trung bình gần 2M, nhưng **không được hứa gấp đôi cho mọi input**. Khi input phân phối xấu, lợi ích có thể biến mất.

Chương trình Java trong bài dùng fixed-size chunks vì có cận RAM rõ, dễ kiểm chứng và không phụ thuộc giả thiết phân phối.

## 11. Multiway merge giảm số lượt so với trộn hai đường

Giả sử có r run và mỗi merge round có thể hợp nhất tối đa k run, k≥2.

Sau một round, số run mới khoảng:

**ceil(r/k)**.

Sau p rounds, tối đa còn:

**ceil(r/k^p)** run.

Số rounds cần để còn một run là:

**p=ceil(log_k r)** với r>1, còn p=0 nếu r≤1.

### Vì sao k quan trọng?

Với r=100 run:

- Merge 2-way cần khoảng ceil(log₂100)=7 rounds.
- Merge 4-way cần ceil(log₄100)=4 rounds.
- Merge 16-way cần ceil(log₁₆100)=2 rounds.
- Merge đủ 100-way có thể cần 1 round, nếu RAM và giới hạn file descriptors cho phép.

Mỗi round thường phải đọc và ghi lại phần lớn dữ liệu. Tăng fan-in k có thể giảm rất nhiều **passes**, nhưng mỗi input stream cần buffer và heap entry.

### Giới hạn memory

Nếu mỗi input buffer chứa B records và output cũng cần B records, ta có xấp xỉ:

**(k+1)B ≤ M**.

Suy ra:

**k ≤ floor(M/B)−1**.

Đây là **cận ý tưởng**; thực tế còn dùng RAM cho heap, metadata, JVM, object overhead và I/O pipeline. Không nên dùng toàn bộ M chỉ cho các buffers rồi bỏ qua phần còn lại.

## 12. Độ phức tạp I/O của external merge sort

Với N records, RAM M và block B (đều tính cùng đơn vị), các giai đoạn full input/output scan có chi phí:

- Run generation: khoảng **2N/B I/Os**.
- Mỗi merge round đầy đủ: khoảng **2N/B I/Os**.
- Có khoảng **ceil(log_k ceil(N/M))** merge rounds với k-way merge.

Một cận dạng:

**O((N/B)·[1+log_k max(1,N/M)])**,

cho k≥2 và bỏ qua hiệu ứng trần, với hằng số tương ứng đọc/ghi ở mỗi stage.

Trong mô hình external-memory chuẩn, cận I/O của sorting tổng quát thường được viết:

**Sort(N)=Θ((N/B)·[1+log_{M/B}(N/B)])**,

với cách diễn giải log được chặn phía dưới bởi 0, và các điều kiện thông thường về M,B,mô hình so sánh/indivisibility. Các công thức là **asymptotic**, không phải lời hứa số syscall chính xác.

### CPU và I/O

Run generation sort mỗi chunk trong RAM có chi phí so sánh. Merge heap k-way xử lý N phần tử/round, khoảng O(N log k) CPU cho mỗi merge round.

Do đó cần phân tích:

**Time_CPU** và **I/O_block_transfers** riêng.

Một thuật toán có I/O gần tối ưu nhưng so sánh key rất đắt vẫn có thể bị CPU-bound.

## 13. Ví dụ số lần merge trên 17 record

Với dữ liệu 17 phần tử ở mục 10:

**Chunk size=4** tạo 5 run, có độ dài:

**[4,4,4,4,1]**.

Chọn **fan-in k=3**:

**Round 1:**

- Merge ba run đầu: 4+4+4=12 phần tử.
- Merge hai run còn lại: 4+1=5 phần tử.
- Còn **2 run**, độ dài [12,5].

**Round 2:**

- Merge hai run: 12+5=17 phần tử.
- Còn **1 run đã sắp xếp hoàn toàn**.

Vậy:

**initialRuns=5**.

**mergeRounds=2**.

**mergeBatches=3** (hai batch ở round 1 và một batch ở round 2).

### Đếm bản ghi logic, không phải block I/O

Run generation:

- Đọc 17 records.
- Ghi 17 records.

Hai merge rounds đều xử lý toàn bộ 17 records:

- Round 1 đọc/ghi 17.
- Round 2 đọc/ghi 17.

Tổng trong **phần sorter, không gồm tạo input ban đầu và đọc kết quả để in**:

**logicalReads=17+17+17=51**.

**logicalWrites=17+17+17=51**.

Những số 51 là **lượt đọc/ghi từng record ở cấp thuật toán**. Với binary int 4 byte, mỗi phía tương ứng 204 byte dữ liệu payload đi qua sorter, nhưng **không phải 51 I/O vật lý**.

## 14. Trường hợp một run được chuyển thẳng sang round sau

Không nhất thiết mỗi round phải đọc/ghi **mọi** phần tử.

Nếu một nhóm chỉ có **một run**, ta có thể chuyển nguyên path của run ấy sang round sau, không mở đọc và ghi lại nó. Đây là **carry-over**.

Ví dụ 9 phần tử, chunk=3, fan-in=2:

~~~text
Initial runs: [3,3,3]
Round 1: merge [3,3] -> [6]; carry [3]
Round 2: merge [6,3] -> [9]
~~~

Logical record reads:

- Run generation: 9.
- Round 1: 6, vì một run dài 3 được carry nguyên.
- Round 2: 9.

**Total reads=24**, writes=24.

Nếu chỉ dùng công thức mỗi round đọc/ghi N=9, ta sẽ dự báo 27 reads và 27 writes. Đó là **một cận trên đơn giản**, còn implementation có carry-over tiết kiệm được 3 reads và 3 writes ở round 1.

### Đếm rounds và batches khác nhau

Một round có thể chứa nhiều **batch merges**. Số lượt quét lớn liên quan rounds; số files mới và CPU heap setup liên quan số batches. Nên đo riêng cả hai.

## 15. Heap cho k-way merge và sự đúng đắn

Mỗi input run đã được sắp tăng. Heap luôn chứa **phần tử hiện tại nhỏ nhất chưa tiêu thụ** của mỗi run chưa cạn.

Bất biến:

**Phần tử nhỏ nhất của toàn bộ dữ liệu chưa ghi ra nằm trong heap**.

Vì nếu ở một run vẫn còn phần tử, phần tử đầu của suffix run ấy không lớn hơn mọi phần tử đứng sau nó. Lấy phần tử nhỏ nhất trong số các đầu run chính là phần tử nhỏ nhất của tất cả suffix.

Sau khi lấy phần tử từ run j:

1. Ghi nó vào output.
2. Đọc phần tử kế tiếp từ **chính run j**.
3. Đưa phần tử mới vào heap nếu còn.

Bằng quy nạp, output luôn không giảm và chứa đúng multiset phần tử của tất cả input runs.

### Duplicates

Nếu hai run cùng có giá trị 8, cả hai giá trị 8 vẫn phải được ghi. Comparator có thể tie-break theo chỉ số run để kết quả deterministic. Với record có payload và yêu cầu **stable sorting**, cần mang thêm original sequence number hoặc chọn chiến lược stable merge phù hợp; chỉ sort int không minh họa tính ổn định của payload.

## 16. Multiway merge và bộ đệm thực tế

Trong mô hình ý tưởng, mỗi input run có một block buffer, output có một block buffer, heap giữ tối đa k phần tử đầu.

Cách tổ chức:

~~~text
input run 0 --> buffered reader --\
input run 1 --> buffered reader ---\ 
input run 2 --> buffered reader ----> min-heap --> buffered writer --> output run
...
input run k --> buffered reader ---/
~~~

Chỉ mở tối đa **k input streams** mỗi batch, giúp tránh vượt giới hạn file descriptors.

### Fan-in lớn không phải lúc nào cũng tốt

- Mỗi stream cần buffer.
- Heap lớn hơn, mỗi pop/push có chi phí O(log k).
- Nhiều streams có thể khiến I/O scheduler và cache bận rộn.
- Bộ nhớ còn cần cho output buffer, parsing, key comparison và runtime.
- Số tệp mở tối đa phụ thuộc hệ điều hành và cấu hình tiến trình.

Nên chọn k từ **RAM budget, block size, file descriptors và benchmark**, thay vì luôn chọn k bằng tổng số run bất kể tài nguyên.

## 17. Giảm số lượt đọc trong truy vấn tổng hợp

Nếu có nhiều phép thống kê trên cùng data, tổ chức một **streaming aggregation**:

~~~text
read each record once:
    if record passes filter:
        update count
        update sum
        update min/max
        update per-group aggregate if memory permits
~~~

Với dữ liệu nhóm theo key, có thể tính group-by với **một sequential pass** và O(1) state cho nhóm hiện tại.

Nếu input chưa group/sort và số nhóm quá lớn cho RAM, có thể:

- Sort theo group key ngoài bộ nhớ rồi aggregate khi quét.
- Hash-partition các record thành bucket đủ nhỏ, aggregate từng bucket.
- Dùng approximate sketches khi bài toán cho phép sai số.
- Spill các nhóm ít dùng xuống đĩa có kiểm soát.

### Khi số nhóm không vừa RAM

Một HashMap grouping lớn hơn RAM có thể tạo page faults và random accesses rất tệ. Để tránh, partition dữ liệu thành các file bucket được **ghi tuần tự theo buffer**, rồi xử lý mỗi bucket trong RAM nếu kích thước đủ nhỏ.

Không được khẳng định phân vùng luôn chỉ cần hai passes; dữ liệu skew có thể tạo bucket lớn bất thường và phải repartition hoặc dùng sort-based fallback.

## 18. Sort-based grouping và hash partitioning

Hai kỹ thuật giảm random access thường dùng trong database engines:

**Sort-based:**

1. External sort records theo group key.
2. Quét output đã sắp.
3. Aggregate các record liên tiếp có cùng key.

Đổi lại phải trả I/O sorting, nhưng việc xử lý các key liền nhau đơn giản và dễ stream.

**Hash-based partitioning:**

1. Dùng hash(key) để chia record vào một số partitions.
2. Buffer output của từng partition, ghi theo block.
3. Đọc từng partition vào RAM và aggregate.
4. Nếu partition không vừa RAM, tiếp tục phân vùng hoặc fallback.

Ưu điểm hash là không phải sắp toàn bộ khi chỉ cần nhóm. Nhược điểm là **skew, số partitions, buffer memory, overflow buckets**.

### Đừng viết từng record vào bucket ngay lập tức

Nếu có 1000 buckets và ghi mỗi record một syscall nhỏ, các thao tác sẽ xen kẽ giữa các file và tạo random writes nhiều. Cần **buffer theo bucket**, flush theo block, hoặc giới hạn số bucket mở và xử lý theo nhiều passes có kiểm soát.

## 19. Block nested-loop join thay vì nested-loop từng record

Giả sử join hai quan hệ R và S, dữ liệu không nằm trọn RAM.

Một nested loop ngây thơ:

~~~text
for each record r in R:
    scan all records s in S:
        if joinKey(r) == joinKey(s):
            output pair
~~~

Khi R có rất nhiều records, S có thể bị quét lại rất nhiều lần.

### Chia outer relation theo block RAM

Nếu một buffer có thể giữ **m−2 block** của R (dành một block cho input S và một block cho output), xử lý cả nhóm R trong RAM rồi quét S một lần cho nhóm ấy.

Gọi:

- **r** = số block của R.
- **s** = số block của S.
- **m** = số block RAM dành cho join.

Chi phí I/O sơ bộ cho **block nested-loop join** khi R là outer:

**r + ceil(r/(m−2))·s**,

với m>2, bỏ qua I/O ghi output.

So với quét S cho từng record R, số lượt scan S giảm nhiều khi m lớn.

### Khi nào sort-merge join tốt hơn?

Nếu R và S đã sort theo join key, có thể quét hai phía gần tuyến tính theo số block, cộng chi phí xử lý các nhóm key trùng.

Nếu chưa sort, external sorting có giá phải trả nhưng còn dùng lại index/order cho các query khác. Chọn phương án cần tính **input order, RAM và output size**.

## 20. Giảm truy cập ngẫu nhiên trong xử lý đồ thị lớn

Trên đồ thị có hàng tỷ cạnh, việc duyệt hàng xóm ngẫu nhiên bằng cách đi theo object pointers rải rác có thể tạo rất nhiều cache misses và I/O.

Các cách cải thiện:

- Lưu adjacency lists trong một biểu diễn gọn như **CSR/CSC**, gom cạnh kề nhau theo đỉnh.
- Gom xử lý các đỉnh thuộc cùng partition.
- Sort các edge update theo đỉnh đích trước khi ghi state.
- Batch request tới cùng block/chunk.
- Nếu cần nhiều iterations, giữ những cấu trúc nhỏ như vertex metadata trong RAM.
- Chọn thuật toán **scan/partition based** thay vì truy cập random edge-per-query.

### Không đổi thứ tự khi nó ảnh hưởng thuật toán

Một số bài graph có phụ thuộc thứ tự hoặc frontier: cập nhật trạng thái theo round, độ dài đường đi hoặc tính nhất quán giữa bước. Chỉ reorder I/O khi bảo toàn các **điều kiện logic**.

Có thể cần double buffering (old state/new state) để một pass không đọc lẫn dữ liệu đã cập nhật của pass hiện tại.

## 21. Index: giảm lượng đọc nhưng có thể tăng random I/O

Một B-tree index cho phép truy vấn chọn lọc tránh scan toàn file:

- Truy vấn tìm một key hiếm có thể chỉ đọc một vài trang index và data.
- Range scan qua các leaf pages liền nhau có thể rất hiệu quả.
- Nếu cần lấy một tỷ lệ lớn records nằm rải rác, nhiều random row fetches có thể chậm hơn một sequential scan.

### Covering index

Nếu index chứa đủ các cột cần cho query, engine có thể trả lời từ index mà không phải đọc từng base row. Điều này làm giảm random table lookups.

### Thống kê và query planner

Ngưỡng chọn index scan hay full table scan phụ thuộc selectivity, clustering, page cache, storage characteristics và optimizer statistics.

Đừng kết luận “index luôn ít I/O hơn scan”; nếu query trả phần lớn bảng, scan có thể tốt hơn.

## 22. LSM tree, B-tree và đánh đổi đọc/ghi

**B-tree** hỗ trợ cập nhật và tìm kiếm bằng cấu trúc trang, nhưng insert/update ngẫu nhiên có thể đòi sửa nhiều pages không liền nhau.

**LSM tree** thường gom writes vào bộ nhớ rồi flush thành các file bất biến đã sắp (SSTable); background compaction trộn/chuyển dữ liệu để tạo cấu trúc tra cứu.

Lợi ích LSM:

- Biến nhiều random writes nhỏ thành các luồng ghi tuần tự lớn hơn.
- Dùng batching và merge/compaction.

Đổi lại:

- **Write amplification:** một record có thể được ghi nhiều lần qua các levels.
- **Read amplification:** cần tra cứu nhiều sources/levels, thường có Bloom filters/indexes hỗ trợ.
- **Space amplification:** có dữ liệu trùng hoặc phiên bản cũ tạm thời.
- Compaction gây I/O nền có thể cạnh tranh với workload chính.

### Tránh phát biểu tuyệt đối

Không nói “LSM luôn nhanh hơn B-tree” hoặc “B-tree luôn có random I/O”. Hiệu quả còn tùy cache, workload read/write, key distribution, implementation, storage và chính sách compaction.

## 23. HDD, SSD, NVMe: logic I/O và vật lý I/O

**HDD:** seek và rotational latency khiến random I/O nhỏ thường kém hiệu quả so với sequential streaming.

**SSD/NVMe:** không có seek cơ học, nhưng random reads/writes vẫn có:

- Overhead request và thiết bị.
- Giới hạn IOPS, queue depth và latency.
- Write amplification, erase blocks, internal mapping.
- Ảnh hưởng của request size và mức song song.

Điều này làm chênh lệch random/sequential **nhỏ hơn một số tình huống HDD**, nhưng không có nghĩa truy cập ngẫu nhiên miễn phí.

### Cần đo đúng thiết bị và điều kiện

Một benchmark đọc file vừa được truy cập có thể được OS page cache phục vụ mà không chạm SSD. Nếu muốn đo lưu trữ thật, phải quản lý cache/warmup và quyền I/O phù hợp, đồng thời tránh thao tác phá dữ liệu.

Đối với nhiệm vụ giáo dục này, chương trình Java báo **logical record transfers**, không hứa đo seek hay throughput vật lý.

## 24. Readahead, async I/O và song song

Khi đọc tuần tự, hệ thống có thể dự đoán block tiếp theo và **prefetch** vào RAM. Một pipeline với đọc bất đồng bộ có thể chồng lấp:

**I/O đọc → CPU xử lý → I/O ghi**.

Các cách cải thiện:

- Double buffering.
- Đọc trước từ từng input run khi merge.
- Ghi các chunk lớn thay vì flush từng record.
- Điều chỉnh số luồng I/O để không overload thiết bị.
- Tách queue đọc/ghi nếu throughput và latency có nhu cầu khác nhau.

### Song song không tự giảm số passes

Chạy 8 threads cùng quét một tệp 8 lần có thể tạo nhiều tổng I/O hơn một pass duy nhất, thậm chí làm bandwidth contention. Parallelism chủ yếu giúp **thời gian hoàn thành** nếu có đủ I/O bandwidth và công việc độc lập.

Cần phân biệt:

- **I/O volume:** tổng số byte/block được truyền.
- **I/O operations:** số request.
- **Wall-clock latency:** thời gian hoàn thành.
- **CPU utilization:** mức sử dụng CPU.

Một tối ưu có thể giảm latency nhưng không giảm bytes, hoặc giảm IOPS mà số bytes vẫn bằng nhau.

## 25. Nén dữ liệu và giảm block transfers

Nén có thể giảm dữ liệu phải đọc/ghi:

- Input/outputs nhỏ hơn ⇒ ít bytes đi qua bus/disk.
- Tăng số bản ghi hiệu quả mỗi block.
- Có thể tăng tốc khi I/O-bound.

Nhưng nén cần CPU và đôi khi ngăn random access vào giữa tệp nén.

### Nén theo chunk

Chia file thành các **compressed blocks** độc lập có index offset thường giúp cân bằng:

- Đọc tuần tự hiệu quả.
- Có khả năng đọc đúng một chunk khi cần.
- Decompress từng phần, không cần giải nén toàn bộ tệp.

### Đừng chỉ đo compression ratio

Phải đo thêm CPU decompress, latency, cache pressure và khả năng skip block dựa trên metadata. Một định dạng nén tốt cho archival scan chưa chắc tốt cho random point lookups.

## 26. Spill-to-disk và quản lý bộ nhớ nghiêm ngặt

**Spilling** là chuyển dữ liệu tạm từ RAM ra đĩa khi bộ nhớ không đủ.

Các lỗi phổ biến:

- Cố giữ toàn bộ N records trong ArrayList rồi mới ghi ra file, khiến external algorithm thực chất vẫn cần O(N) RAM.
- Mở hàng nghìn runs cùng lúc, vượt file descriptor limit.
- Cấp phát input buffers cho mọi run cùng lúc nhưng không trừ chúng khỏi memory budget.
- Ghi mỗi record một file riêng, tạo metadata operations lớn.
- Không xóa temp files khi job lỗi, làm đầy disk.
- Không theo dõi dung lượng tệp tạm cực đại, dù RAM thấp.

### Nguyên tắc thiết kế

Giới hạn rõ:

- Số records trong mỗi in-memory sort chunk.
- Số input streams trong một merge batch.
- Kích thước mỗi stream buffer.
- Kích thước output buffer.
- Số tệp tạm và dung lượng đĩa.
- Chính sách dọn dẹp khi fail hoặc job bị hủy.

Bản Java dưới đây dùng **chunkSize** và **fanIn** là các tham số minh họa, mỗi lần merge giữ tối đa một record ở heap cho mỗi input stream. Các BufferedInputStream nội bộ còn chiếm RAM, nên chunkSize **không** phải toàn bộ budget M thực trong đơn vị số nguyên.

## 27. Đo chi phí logic và vật lý tách biệt

Để so hai implement external sort, có thể ghi:

**LogicalReads:** số record được đọc bởi run generation và merge phases.

**LogicalWrites:** số record được ghi ra các run.

**InitialRuns:** số run sau giai đoạn chia chunk.

**MergeRounds:** số vòng trộn lớn.

**MergeBatches:** số nhóm từ ít nhất hai run được merge thành một run.

**PhysicalReads/Writes:** số block hoặc bytes thực sự được thiết bị xử lý; thường phải lấy từ hệ điều hành, runtime instrumentation hoặc tracing, không suy trực tiếp từ counters record-level.

### Vì sao không dùng số readInt làm IOPS?

Trong Java, DataInputStream.readInt có thể đọc 4 byte từ BufferedInputStream đã nạp sẵn một block 8192 byte. Hàng nghìn lần readInt có thể tương ứng chỉ vài lần đọc hệ điều hành, và các lần đọc hệ điều hành có thể lại được OS page cache phục vụ.

Do vậy:

**recordReads=51 không có nghĩa physicalDiskReads=51**.

Tương tự, số writes cũng không tương ứng một-một với syscall write hay device write.

## 28. Java 17+ — External Sequential Sort thực sự dùng tệp tạm

Chương trình dưới đây:

1. Sinh một **tệp input binary int** cho từng ca kiểm thử (chỉ phục vụ demo).
2. **Đọc tuần tự** input, mỗi lần tối đa chunkSize số nguyên, sort đoạn trong RAM.
3. Ghi một run binary int đã sắp ra tệp tạm bằng buffered stream.
4. Trộn nhóm tối đa fanIn run bằng **PriorityQueue**, giữ một phần tử đầu mỗi stream và dùng buffered reads/writes.
5. Nếu một round còn đúng một run lẻ, **chuyển path nguyên trạng** thay vì đọc/ghi lại.
6. Lặp cho đến khi còn một output run.
7. Trên các input demo nhỏ, đọc output vào RAM để **kiểm thử đúng** với Arrays.sort và in stdout. Việc đọc toàn bộ output để in **không nằm trong core external sort** và không phải cách dùng cho dữ liệu lớn.
8. Xóa các tệp tạm khi kết thúc.

**Tên tệp: ExternalSequentialSortDemo.java**

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;
import java.util.stream.Stream;

public class ExternalSequentialSortDemo {

    static final int IO_BUFFER_BYTES = 8192;

    static final class Counters {
        long reads;
        long writes;
    }

    record Head(int value, int source) {}

    record Result(
            Path sortedFile,
            int initialRuns,
            int mergeRounds,
            int mergeBatches) {}

    static DataInputStream openRead(Path path)
            throws IOException {
        return new DataInputStream(
                new BufferedInputStream(
                        Files.newInputStream(path),
                        IO_BUFFER_BYTES));
    }

    static DataOutputStream openWrite(Path path)
            throws IOException {
        return new DataOutputStream(
                new BufferedOutputStream(
                        Files.newOutputStream(path),
                        IO_BUFFER_BYTES));
    }

    // Create the demo input. Not counted as sort I/O.
    static void writeDemoInput(Path file, int[] values)
            throws IOException {
        try (DataOutputStream out = openWrite(file)) {
            for (int value : values) {
                out.writeInt(value);
            }
        }
    }

    // At most chunkSize int records are sorted in RAM.
    static List<Path> createSortedRuns(
            Path input, Path dir, int chunkSize,
            Counters counters) throws IOException {

        List<Path> runs = new ArrayList<>();

        try (DataInputStream in = openRead(input)) {
            boolean reachedEnd = false;

            while (!reachedEnd) {
                int[] chunk = new int[chunkSize];
                int count = 0;

                while (count < chunkSize) {
                    try {
                        chunk[count] = in.readInt();
                        counters.reads++;
                        count++;
                    } catch (EOFException end) {
                        reachedEnd = true;
                        break;
                    }
                }

                if (count == 0) {
                    break;
                }

                Arrays.sort(chunk, 0, count);

                Path run = Files.createTempFile(
                        dir, "sorted-run-", ".bin");

                try (DataOutputStream out =
                             openWrite(run)) {
                    for (int i = 0; i < count; i++) {
                        out.writeInt(chunk[i]);
                        counters.writes++;
                    }
                }

                runs.add(run);
            }
        }

        return runs;
    }

    // The input files are already individually sorted.
    static void mergeGroup(
            List<Path> group, Path output,
            Counters counters) throws IOException {

        List<DataInputStream> readers = new ArrayList<>();

        PriorityQueue<Head> heap =
                new PriorityQueue<>(
                        Comparator.comparingInt(Head::value)
                                .thenComparingInt(Head::source));

        try (DataOutputStream out = openWrite(output)) {
            for (int source = 0; source < group.size();
                    source++) {
                DataInputStream in = openRead(
                        group.get(source));
                readers.add(in);
                pushNext(in, source, heap, counters);
            }

            while (!heap.isEmpty()) {
                Head head = heap.remove();

                out.writeInt(head.value());
                counters.writes++;

                pushNext(
                        readers.get(head.source()),
                        head.source(),
                        heap,
                        counters);
            }
        } finally {
            for (DataInputStream in : readers) {
                in.close();
            }
        }
    }

    static void pushNext(
            DataInputStream in, int source,
            PriorityQueue<Head> heap, Counters counters)
            throws IOException {

        try {
            int value = in.readInt();
            counters.reads++;
            heap.add(new Head(value, source));
        } catch (EOFException end) {
            // This run is exhausted.
        }
    }

    static Result sort(
            Path input, Path dir,
            int chunkSize, int fanIn, Counters counters)
            throws IOException {

        if (chunkSize < 1 || fanIn < 2) {
            throw new IllegalArgumentException(
                    "chunkSize >= 1 and fanIn >= 2 required");
        }

        // The binary format is exactly 4 bytes per int.
        if (Files.size(input) % Integer.BYTES != 0) {
            throw new IOException(
                    "Input length is not a multiple of 4");
        }

        List<Path> runs = createSortedRuns(
                input, dir, chunkSize, counters);

        int initialRuns = runs.size();
        int rounds = 0;
        int batches = 0;

        if (runs.isEmpty()) {
            Path empty = Files.createTempFile(
                    dir, "empty-result-", ".bin");

            return new Result(empty, 0, 0, 0);
        }

        while (runs.size() > 1) {
            List<Path> next = new ArrayList<>();

            for (int i = 0; i < runs.size(); i += fanIn) {
                int to = Math.min(i + fanIn, runs.size());
                List<Path> group = runs.subList(i, to);

                if (group.size() == 1) {
                    // Carry the run without rereading/rewriting.
                    next.add(group.get(0));
                    continue;
                }

                Path merged = Files.createTempFile(
                        dir, "merged-run-", ".bin");

                mergeGroup(group, merged, counters);
                next.add(merged);
                batches++;

                for (Path old : group) {
                    Files.delete(old);
                }
            }

            runs = next;
            rounds++;
        }

        return new Result(
                runs.get(0), initialRuns, rounds, batches);
    }

    // Only the DEMO verifier loads all output into RAM.
    static int[] readDemoOutput(Path file)
            throws IOException {

        List<Integer> values = new ArrayList<>();

        try (DataInputStream in = openRead(file)) {
            while (true) {
                try {
                    values.add(in.readInt());
                } catch (EOFException end) {
                    break;
                }
            }
        }

        return values.stream()
                .mapToInt(Integer::intValue)
                .toArray();
    }

    static void runCase(
            String name, int[] values,
            int chunkSize, int fanIn, Path tempDir)
            throws IOException {

        Path input = Files.createTempFile(
                tempDir, "input-", ".bin");

        writeDemoInput(input, values);

        Counters counters = new Counters();

        Result result = sort(
                input, tempDir, chunkSize, fanIn, counters);

        int[] actual = readDemoOutput(result.sortedFile());
        int[] expected = values.clone();
        Arrays.sort(expected);

        if (!Arrays.equals(expected, actual)) {
            throw new AssertionError(
                    "External sort mismatch: " + name);
        }

        System.out.println(
                name + " sorted: " + Arrays.toString(actual));

        System.out.println(
                name + " runs=" + result.initialRuns()
                + ", rounds=" + result.mergeRounds()
                + ", batches=" + result.mergeBatches()
                + ", reads=" + counters.reads
                + ", writes=" + counters.writes);
    }

    public static void main(String[] args)
            throws Exception {

        Path tempDir = Files.createTempDirectory(
                "external-sequential-sort-demo-");

        try {
            runCase("Mixed",
                    new int[] {
                            14, -5, 8, 8, 1, 0, 27, -9, 6,
                            3, 2, 2, -1, 13, 4, 7, -3
                    }, 4, 3, tempDir);

            runCase("Single run",
                    new int[] {5, -1, 5},
                    4, 3, tempDir);

            runCase("Empty",
                    new int[] {},
                    4, 3, tempDir);

            runCase("Duplicates",
                    new int[] {
                            4, 4, 4, -2, -2,
                            4, 1, 1, 1, 0
                    }, 3, 2, tempDir);

            runCase("Carry over",
                    new int[] {9, 7, 5, 3, 1, 2, 4, 6, 8},
                    3, 2, tempDir);
        } finally {
            // Only flat temp files are created by this demo.
            try (Stream<Path> files = Files.list(tempDir)) {
                for (Path file : files.toList()) {
                    Files.deleteIfExists(file);
                }
            }

            Files.deleteIfExists(tempDir);
        }

        System.out.println("All cases verified.");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ExternalSequentialSortDemo.java
java ExternalSequentialSortDemo
~~~

**Đầu ra chính xác của chương trình:**

~~~text
Mixed sorted: [-9, -5, -3, -1, 0, 1, 2, 2, 3, 4, 6, 7, 8, 8, 13, 14, 27]
Mixed runs=5, rounds=2, batches=3, reads=51, writes=51
Single run sorted: [-1, 5, 5]
Single run runs=1, rounds=0, batches=0, reads=3, writes=3
Empty sorted: []
Empty runs=0, rounds=0, batches=0, reads=0, writes=0
Duplicates sorted: [-2, -2, 0, 1, 1, 1, 4, 4, 4, 4]
Duplicates runs=4, rounds=2, batches=3, reads=30, writes=30
Carry over sorted: [1, 2, 3, 4, 5, 6, 7, 8, 9]
Carry over runs=3, rounds=2, batches=2, reads=24, writes=24
All cases verified.
~~~

### Vì sao đây là external sort thật?

Trong **core sort**, dữ liệu đến từ một tệp binary qua BufferedInputStream. Run generation chỉ giữ tối đa **chunkSize int** trong mảng đang sort. Multiway merge chỉ giữ **một Head trên heap cho mỗi input stream**, ngoài I/O buffers.

Các run trung gian thực sự là tệp trên bộ nhớ ngoài; dữ liệu không được nối thành một mảng N phần tử để sort toàn cục.

**Ngoại lệ chỉ thuộc trình diễn:** hàm readDemoOutput nạp kết quả nhỏ vào RAM để so với Arrays.sort và in. Với dữ liệu lớn, thay bước này bằng **consumer đọc tuần tự output** hoặc **so hai luồng theo từng record**, không đọc toàn bộ.

### Thống kê reads/writes có nghĩa gì?

Counters chỉ đếm các lần readInt/writeInt thành công trong **run generation + merge**.

Chúng **không bao gồm**:

- Lần đầu ghi mảng demo ra input file.
- Đọc output để in.
- Metadata operations.
- Actual block I/O và OS page-cache behavior.

Vì vậy 51 reads/51 writes của Mixed là **lượt xử lý record logic**, không phải 51 disk read commands.

## 29. Phân tích chi phí của chính chương trình Java

**Run generation:**

- Đọc tất cả N records một lần.
- Sort từng chunk tối đa C records, với C=chunkSize.
- Ghi mỗi chunk thành một run.
- Tổng CPU sorting O(N log C) trong trường hợp chung.
- Logical reads=N, writes=N.

**Merge rounds:**

- r=ceil(N/C) run ban đầu.
- Mỗi round giảm số run về tối đa ceil(r/k), k=fanIn.
- P=ceil(log_k r) rounds khi r>1.
- Mỗi record tham gia tối đa P round merges.
- CPU heap O(NP log k) cho các record thực sự trộn.
- Logical reads/writes mỗi phía **≤N(1+P)**; có thể thấp hơn vì carry-over.

**Memory ngoài buffers:**

- Run generation: O(C) số nguyên.
- Merge: O(k) Head records và streams.
- Danh sách Path và temporary-file bookkeeping: O(r) references, có thể là vấn đề khi có cực nhiều runs.

### Thực tế bộ nhớ của Java

BufferedInputStream/BufferedOutputStream cấp bộ đệm byte cho mỗi stream. Nếu fanIn=k, riêng byte buffers cho batch có thể gần:

**(k+1)·IO_BUFFER_BYTES**,

không kể heap nodes, ArrayList, Path objects và JVM.

Vì vậy một cấu hình production phải chọn **C, k và buffer size** sao cho tổng RAM nằm trong budget, không chỉ nhìn O(C+k) rồi cho rằng không tốn gì khác.

### Độ phức tạp theo block

Nếu C≈M records và các buffers thực sự đọc/ghi B records/block, mô hình I/O lý tưởng trở về:

**O((N/B)·[1+ceil(log_k ceil(N/M))])**.

Đây là cầu nối giữa code streaming và phân tích ngoài bộ nhớ.

## 30. QA độc lập cho bài sắp xếp ngoài bộ nhớ

Một oracle đơn giản cho input nhỏ:

**expected = bản sao input được sort trong RAM bằng một thuật toán độc lập**.

Sau khi external sorter hoàn tất:

1. Đọc output, so đúng số lượng records.
2. So từng vị trí với expected.
3. Kiểm tra duplicates và số âm không bị mất.
4. Kiểm tra output không giảm.
5. So multiset input với multiset output.
6. Kiểm tra mergeRounds và initialRuns theo cấu trúc run.
7. Đếm record reads/writes để so với số phần tử thực tế được đọc và ghi ở từng batch.
8. Kiểm tra input file gốc vẫn được giữ nguyên trong ví dụ.

### Các ca bắt buộc

- N=0: không run, output rỗng, 0 rounds.
- N<C: 1 run, không cần merge.
- N=C: một run đầy, không tạo run rỗng bổ sung.
- N=C+1: hai run, cần một merge round nếu fanIn≥2.
- N không chia hết C: run cuối ngắn.
- Duplicates.
- Giá trị âm, Integer.MIN_VALUE và Integer.MAX_VALUE.
- Input đã tăng, input giảm, input toàn bằng nhau.
- Fan-in=2 và fan-in lớn hơn số run.
- Số run không chia hết fan-in, có thể carry-over.
- Tệp input lỗi không chia hết 4 byte: chương trình phải từ chối định dạng.
- Tệp lớn hơn RAM thực: xác nhận không có thao tác readAll trong core.

### Vì sao cần oracle độc lập?

Nếu chỉ so hai implementation external merge dùng cùng sai lầm heap, chúng có thể cùng trả sai. Oracle Arrays.sort trên mảng **nhỏ** và kiểm tra multiset giúp phát hiện mất record hoặc trộn sai.

Việc thử random nhiều lần không tự chứng minh performance bound cho mọi input; correctness chứng minh qua sorted runs và k-way merge, cost bound qua số lần đọc/ghi trong các vòng.

## 31. Tối ưu thêm số passes: lựa chọn kiến trúc

Nếu initial runs nhiều, có các hướng:

**Tăng kích thước run ban đầu:** cho phép chunk C lớn hơn khi memory budget thực sự đủ. Từ r=ceil(N/C), r giảm sẽ giảm số rounds.

**Tăng fan-in:** nếu có đủ RAM cho k input buffers và 1 output buffer, trộn nhiều run trong một round.

**Tạo run dài với replacement selection:** có thể hữu ích trên một số phân phối input, nhưng có chi phí CPU và không đảm bảo run dài trong mọi trường hợp.

**Không merge lại run đơn:** carry-over giúp bớt logical transfers.

**Pipeline bước sau với merge output:** nếu giai đoạn sau chỉ cần đọc output tuần tự, có thể tiêu thụ ngay luồng merge cuối thay vì ghi output rồi đọc lại, nhưng phải xét retry/recovery và API contract.

**Tránh materialize dữ liệu tạm không cần thiết:** nếu consumer có thể xử lý streaming output, không phải luôn lưu một file trung gian hoàn chỉnh.

### Giới hạn của tối ưu

Giảm passes có thể tăng RAM và số file streams, hoặc tăng độ phức tạp xử lý lỗi. Với workload nhỏ, chi phí mở tệp và quản lý heap có thể lớn hơn lượng I/O tiết kiệm được.

Nên bắt đầu bằng phép đo bottleneck thật, sau đó chọn sự đánh đổi.

## 32. Xử lý lỗi, tính bền vững và dữ liệu tạm

Chương trình demo dọn temp files khi thoát bình thường hoặc khi exception được ném trong khối try. Trong hệ thống production, vẫn cần cân nhắc:

- Crash của tiến trình hoặc máy có thể bỏ lại temporary files.
- Thiết bị hết dung lượng khi đang ghi run.
- Không được xuất bản một output chưa ghi xong như file kết quả hợp lệ.
- Cần atomic publish/rename khi filesystem hỗ trợ và cùng vùng lưu trữ, đồng thời cân nhắc fsync/durability khi hợp đồng yêu cầu.
- Retry phải phân biệt giai đoạn nào đã hoàn thành và tránh trộn trùng record.
- Kiểm tra checksum, record count, file lengths, schema version và encoding.
- Giới hạn số temporary files, không giữ tất cả forever.
- Tránh xóa input gốc khi cleanup.
- Monitor disk pressure và free space trước khi bắt đầu job quá lớn.

### Không đồng nhất flush với durability

Đẩy bytes từ BufferedOutputStream xuống file descriptor chưa mặc nhiên có nghĩa bytes đã được commit bền vững xuống thiết bị. Với yêu cầu durability mạnh, cần chính sách fsync/force, rename và recovery được thiết kế đúng môi trường.

Ví dụ Java là **trình diễn thuật toán và luồng I/O tuần tự**, không phải một storage engine có giao dịch bền vững hay khả năng khôi phục sau crash.

## 33. Những lỗi thường gặp

1. **Chỉ đếm CPU O(n log n), quên block I/O** khi dữ liệu vượt RAM.
2. **Nhầm một readInt với một physical disk I/O**, bỏ buffered streams và OS page cache.
3. **Nhầm số passes với số seeks**, hai metric khác nhau.
4. **Đọc từng record ở vị trí ngẫu nhiên** dù có thể sort ID rồi batch theo block.
5. **Sắp ID request nhưng không lưu original ID**, trả kết quả sai thứ tự.
6. **Reorder thao tác ghi có phụ thuộc**, làm sai ngữ nghĩa.
7. **Quét lại tệp nhiều lần cho những thống kê có thể fuse**, tốn block reads.
8. **Tạo tệp trung gian không cần thiết**, phải ghi rồi đọc lại.
9. **Coi predicate pushdown luôn giảm I/O vật lý trên mọi row-store**, thiếu điều kiện layout.
10. **Giữ toàn bộ N trong ArrayList rồi gọi là external sorting**, RAM vẫn O(N).
11. **Ghi run chưa sort**, làm merge heap trả sai.
12. **Gộp run bằng cách lấy ngẫu nhiên một stream thay vì head nhỏ nhất**, sai ordering.
13. **Không đọc phần tử kế tiếp từ đúng stream vừa pop**, mất hoặc lặp record.
14. **Không xử lý nhiều giá trị trùng**, mất multiset semantics.
15. **Nhầm stable sorting với numeric sortedness**, payload order có thể đổi.
16. **Mở mọi run cùng lúc dù không có RAM/file descriptors**, lỗi tài nguyên.
17. **Tăng fan-in nhưng quên input/output buffers**, vượt memory budget.
18. **Dùng chunkSize làm toàn bộ M mà không tính stream buffers**, dự toán sai.
19. **Không xử lý N=0 hoặc một run**, cố merge queue rỗng.
20. **Khi nhóm còn một run, ép ghi lại không cần thiết**, tốn I/O.
21. **Đếm merge batches thành merge rounds**, thống kê sai.
22. **Coi mỗi round nhất thiết đọc toàn bộ N**, bỏ khả năng carry-over.
23. **Tuyên bố 51 logical reads nghĩa là 51 disk reads**, hoàn toàn khác metric.
24. **Đếm số bytes output demo verifier vào sort counters**, mất khả năng so thuật toán.
25. **Không dùng buffered writes**, tạo nhiều syscall nhỏ.
26. **Ghi một record vào một tệp partition riêng**, metadata overhead lớn.
27. **Phân vùng bằng hash nhưng không xử lý skew**, bucket không vừa RAM.
28. **Dùng nested-loop join từng record** dù có thể xử lý theo block.
29. **Gán lợi ích seek của HDD cho SSD một cách định lượng tùy ý**, cần benchmark.
30. **Đo file đã ở page cache rồi kết luận disk random access rất nhanh**, đo sai tầng.
31. **Tăng luồng I/O và tự cho rằng tổng bytes giảm**, thường chỉ thay latency/parallelism.
32. **Không theo dõi temporary disk space**, có thể đầy đĩa giữa job.
33. **Không xử lý malformed/truncated input**, biến lỗi bytes thành record mất.
34. **Không kiểm tra output record count**, có thể mất phần tử trong merge.
35. **Không phân biệt read amplification và write amplification**, báo thiếu cost.
36. **Dùng memory-mapped file rồi coi mọi page fault là miễn phí**, còn paging/I/O.
37. **Không giải thích điều kiện M,B,N của công thức Sort(N)**, áp dụng sai.
38. **Nói luôn có đúng ceil(log_k r) passes data đầy đủ**, carry-over hoặc tối ưu pipeline có thể khác.
39. **Không tính O(q log q) sort IDs hoặc O(N log C) CPU**, phân tích thiếu.
40. **Không tính CPU decompress trong tối ưu compression**, có thể đổi bottleneck.
41. **Dùng nhiều bucket buffers hơn RAM cho phép**, lại spill hoặc thrash.
42. **Coi file compression bất kỳ cho random-access O(1)**, thiếu index chunk.
43. **Nhầm scan sequential trên disk với scan metadata qua database index**, layout rất quan trọng.
44. **Tuyên bố index luôn thắng full scan**, không xét selectivity.
45. **Tuyên bố LSM luôn thắng B-tree**, bỏ read/write amplification.
46. **Không kiểm tra tính nhất quán của snapshot** khi pipeline xử lý dữ liệu đang đổi.
47. **Không thiết kế publish/cleanup**, có thể lộ output chưa hoàn chỉnh.
48. **Coi flush là đã durable trên thiết bị**, cần yêu cầu rõ.
49. **Tối ưu passes bằng cách thay đổi thứ tự record có ý nghĩa**, phá correctness.
50. **Chỉ benchmark một workload nhỏ**, không đại diện production.

## 34. Bài tập tự luyện có đáp án

**Bài 1.** Với N records và B records/block, một full sequential scan cần bao nhiêu block reads theo mô hình?  
**Đáp án:** Θ(⌈N/B⌉).

**Bài 2.** Đọc rồi ghi một bản sao toàn bộ N records cần I/O lý tưởng cỡ bao nhiêu?  
**Đáp án:** Khoảng 2⌈N/B⌉ block transfers.

**Bài 3.** N=12.000.000, M=1.048.576 records; có khoảng bao nhiêu initial runs nếu mỗi run tối đa M?  
**Đáp án:** ceil(12.000.000/1.048.576)=12.

**Bài 4.** Với M/B=1024 buffers và dành 1 output buffer, tối đa bao nhiêu input buffers theo mô hình đơn giản?  
**Đáp án:** 1023.

**Bài 5.** 12 run, fan-in=1023 cần bao nhiêu merge rounds?  
**Đáp án:** 1.

**Bài 6.** 100 run, fan-in=2, số rounds?  
**Đáp án:** ceil(log₂100)=7.

**Bài 7.** 100 run, fan-in=16, số rounds?  
**Đáp án:** ceil(log₁₆100)=2.

**Bài 8.** 17 record, chunk 4 tạo bao nhiêu run và độ dài?  
**Đáp án:** 5 run, độ dài [4,4,4,4,1].

**Bài 9.** Năm run ấy merge fan-in 3 cần bao nhiêu rounds và batches?  
**Đáp án:** 2 rounds, 3 merge batches.

**Bài 10.** Run generation và hai merge rounds đều xử lý 17 record; sorter đếm bao nhiêu logical reads mỗi phía?  
**Đáp án:** 51 reads và 51 writes.

**Bài 11.** 51 logical reads có nghĩa 51 disk I/Os không?  
**Đáp án:** Không; buffered I/O và OS caching thay đổi ánh xạ.

**Bài 12.** Có ba run dài [3,3,3], fan-in=2; round 1 cần đọc/ghi bao nhiêu records nếu carry run thứ ba?  
**Đáp án:** 6 records mỗi phía.

**Bài 13.** Sau round 1, có hai run [6,3], round 2 phải merge bao nhiêu records?  
**Đáp án:** 9.

**Bài 14.** Tổng reads cho run generation 9, round1 6, round2 9 là bao nhiêu?  
**Đáp án:** 24.

**Bài 15.** Vì sao multiway merge giảm passes?  
**Đáp án:** Mỗi round gộp tối đa k run thành một, nên cần khoảng log_k r rounds.

**Bài 16.** Vì sao không chọn fan-in vô hạn?  
**Đáp án:** RAM buffers, heap, file descriptors và I/O scheduler có giới hạn.

**Bài 17.** Vì sao tính readInt calls không bằng số I/O vật lý?  
**Đáp án:** Một buffered read cấp dữ liệu cho nhiều readInt và OS cache có thể phục vụ.

**Bài 18.** Nhiều thống kê độc lập cùng trên một file lớn: tối ưu đơn giản nhất?  
**Đáp án:** Fuse vào cùng một sequential scan.

**Bài 19.** Hash partition không buffer từng bucket gây điều gì?  
**Đáp án:** Nhiều writes nhỏ, random interleaving và overhead cao.

**Bài 20.** Với block nested-loop join, r,s là số pages và RAM m pages, chi phí quét inner S thế nào?  
**Đáp án:** Khoảng ceil(r/(m−2)) lượt, khi m>2, bỏ output cost.

**Bài 21.** Tại sao covering index giúp giảm random I/O?  
**Đáp án:** Có thể trả dữ liệu ngay từ index mà không fetch từng base row.

**Bài 22.** SSD có khiến random I/O miễn phí?  
**Đáp án:** Không; vẫn có overhead request, IOPS, queue và flash behavior.

**Bài 23.** Vì sao external sort phải giữ số lượng records sau merge?  
**Đáp án:** Sắp xếp chỉ đổi thứ tự, không được mất hoặc nhân bản records.

**Bài 24.** Core external sort có nên dùng readAll của toàn output để kiểm chứng dataset terabyte không?  
**Đáp án:** Không; chỉ dùng ở demo nhỏ, với dataset lớn so tuần tự hoặc dùng checksum/record counts và validation phù hợp.

**Bài 25.** Nếu input records có payload cần stable order, sort int đơn thuần đã đủ chưa?  
**Đáp án:** Chưa; phải mang original-order tie-break hoặc dùng stable run/merge theo hợp đồng.

**Bài 26.** Nếu job crash giữa merge, có thể coi output partial là kết quả cuối không?  
**Đáp án:** Không; cần publish atomically hoặc metadata/checkpoint/recovery theo hệ thống.

## 35. Checklist áp dụng và kết luận

Trước khi thiết kế thuật toán ngoài bộ nhớ:

1. **Xác định N, M, B theo cùng đơn vị**; nếu records biến dài, tính byte budget.
2. **Đo dataset có vượt RAM không**, và RAM còn dành cho buffer/metadata bao nhiêu.
3. **Phân biệt block transfers, seeks, passes, bytes và wall-clock**.
4. **Tận dụng sequential scan trước random lookup** khi không làm đổi ngữ nghĩa.
5. **Gom các yêu cầu theo block/offset** nếu có thể reorder và trả theo original IDs.
6. **Dùng buffered read/write**, tránh syscall nhỏ cho mỗi record.
7. **Fuse nhiều phép tổng hợp cùng một pass** nếu chúng độc lập và state đủ nhỏ.
8. **Filter/project sớm** khi storage layout hỗ trợ.
9. **Với sort ngoài RAM, chia thành sorted runs** rồi k-way merge.
10. **Chọn chunk size từ memory budget**, không đặt bằng toàn RAM rồi bỏ buffers.
11. **Chọn fan-in từ input/output buffers và file descriptor limit**.
12. **Đếm initial runs, merge rounds và batches riêng**.
13. **Tính carry-over**, tránh đọc/ghi run đơn khi không cần.
14. **Giữ invariant mỗi run đã sorted** và heap chứa head của từng run.
15. **So output với oracle nhỏ**, xác minh số phần tử/multiset.
16. **Không nạp toàn bộ output vào RAM trong production**.
17. **Với group-by, chọn sort hoặc hash partition theo skew và memory**.
18. **Với join, xét block nested-loop, sort-merge hoặc hash join** thay vì quét inner từng record.
19. **Với graph, bố trí adjacency và update theo khối**, nhưng bảo toàn trạng thái theo round.
20. **Đối với index, xét selectivity**, không coi index scan luôn thắng full scan.
21. **Phân biệt HDD/SSD và OS page cache**, đo đúng tầng lưu trữ.
22. **Nếu dùng nén/prefetch, đo CPU và tail latency ngoài byte throughput**.
23. **Thiết kế temp-file cleanup, disk space, publish và recovery**.
24. **Báo logical record I/O riêng physical I/O** để không đánh tráo metric.
25. **Kiểm thử rỗng, một run, nhiều run, duplicates, extreme ints và fan-in nhỏ**.
26. **Kết luận dựa trên dữ liệu thực tế**, không chỉ Big O trong RAM model.

**Kết luận:** hai cách cải thiện quan trọng nhất khi dữ liệu vượt RAM là **biến những truy cập rải rác thành luồng đọc/ghi theo khối** và **giảm số lần phải đọc lại toàn bộ dữ liệu**. External merge sort là ví dụ điển hình: tạo sorted runs bằng những lần scan tuần tự, sau đó trộn nhiều run trong mỗi round để giảm passes. Khi vận dụng vào group-by, join, đồ thị, cache hay hệ thống lưu trữ, vẫn phải xác nhận tính đúng của việc reorder và đo cả số block transfers, seek/random I/O, thời gian CPU và chi phí đĩa tạm. Những tối ưu thực sự hiệu quả là những tối ưu **giảm dữ liệu di chuyển mà vẫn giữ nguyên hợp đồng kết quả**.

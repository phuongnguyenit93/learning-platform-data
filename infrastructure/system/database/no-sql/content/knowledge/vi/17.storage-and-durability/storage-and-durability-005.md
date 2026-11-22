# SSTable hoặc cấu trúc bất biến và hoạt động hợp nhất dữ liệu

## 1. Một bản ghi được cập nhật nhiều lần: dữ liệu thật nằm ở đâu?

Hãy tưởng tượng một ứng dụng học trực tuyến lưu tiến độ của người học:

~~~text
Khóa:    (learnerId = L001, courseId = C101)
Giá trị: progressPercent
~~~

Người học hoàn thành thêm bài, khiến tiến độ tăng liên tục:

~~~text
09:00  progressPercent = 10
09:05  progressPercent = 20
09:10  progressPercent = 35
09:15  progressPercent = 50
~~~

Trong một hệ thống lưu trữ **Log-Structured Merge Tree (LSM-tree)**, mỗi lần cập nhật không nhất thiết tìm đúng một vị trí trên đĩa rồi ghi đè ngay. Thay vào đó, dữ liệu mới thường đi qua một bộ nhớ ghi (**memtable**), có nhật ký phục hồi (**write-ahead log/commit log**) và được xả thành những file có thứ tự, gần như **bất biến** trên đĩa.

Kết quả là nhiều file có thể cùng chứa **các phiên bản khác nhau của một khóa**:

~~~text
SSTable-A (cũ): L001/C101 -> 10
SSTable-B:      L001/C101 -> 20
SSTable-C:      L001/C101 -> 35
Memtable (mới): L001/C101 -> 50
~~~

Khi ứng dụng đọc, storage engine phải xác định giá trị nào còn hiệu lực theo thứ tự mutation, timestamp hoặc sequence number của hệ. Về sau, quá trình **compaction (hợp nhất dữ liệu)** có thể đọc những file cũ, loại bản ghi đã bị thay thế khi an toàn và tạo file mới gọn hơn.

Đây là trọng tâm bài học: **tại sao lưu dữ liệu thành những cấu trúc bất biến giúp ghi hiệu quả, và tại sao điều đó buộc hệ thống phải đọc, hợp nhất, thu gom bản ghi cũ và quản lý dấu xóa cẩn thận**.

Sau bài học, bạn cần có thể:

1. Mô tả đường ghi và đường đọc của một hệ LSM với WAL, memtable và SSTable.
2. Giải thích tính bất biến của SSTable và ý nghĩa của compaction.
3. Phân biệt flush với compaction; commit với flush; compaction với backup.
4. Hiểu read amplification, write amplification và space amplification.
5. So sánh các chiến lược size-tiered, leveled, time-window và các biến thể khác trong phạm vi hệ hỗ trợ.
6. Giải thích tombstone, TTL, replica repair và nguy cơ dữ liệu đã xóa xuất hiện lại.
7. Đánh giá cách cấu hình, theo dõi và thử nghiệm workload thay vì chỉ chọn chiến lược theo tên.

**Lưu ý về phạm vi:** Không phải mọi NoSQL đều dùng SSTable hoặc LSM-tree. Apache Cassandra và ScyllaDB dùng những cấu trúc SSTable theo thiết kế riêng; RocksDB và những hệ dựa trên RocksDB cũng thuộc họ LSM. Trong HBase có HFile và quy trình flush/compaction tương đồng ở mức khái niệm. MongoDB/WiredTiger thường được triển khai với B-tree; Redis chủ yếu dùng mô hình dữ liệu trong RAM kèm các cơ chế persistence riêng. Các thuật ngữ và lựa chọn cấu hình ở mỗi hệ không hoàn toàn giống nhau.

## 2. SSTable là gì?

### 2.1. Sorted String Table

**SSTable (Sorted String Table)** thường chỉ một cấu trúc dữ liệu bền vững trên đĩa, có các entry được tổ chức theo thứ tự khóa và **không bị sửa trực tiếp sau khi được tạo** trong hoạt động ghi thông thường.

Ví dụ nội dung logic:

~~~text
SSTable-001
--------------------------------
Key          Sequence   Value
C001         11         value-A
C015         15         value-B
C027         13         value-C
C099         21         value-D
--------------------------------
~~~

Tên “String Table” mang tính lịch sử; key/value **không nhất thiết là chuỗi văn bản**. Một SSTable thực có thể chứa binary serialization, timestamp, cell, column, tombstone, checksum, block nén và nhiều metadata khác tùy engine.

### 2.2. Hai đặc điểm quan trọng

**Có thứ tự theo khóa:** Hệ có thể dùng index để tìm vùng cần đọc, đọc tuần tự một phạm vi và trộn những luồng dữ liệu đã sắp xếp từ nhiều file.

**Bất biến sau khi tạo:** Khi cần cập nhật giá trị, hệ ghi một phiên bản mới ở cấu trúc đang ghi, thay vì sửa các entry của file SSTable cũ tại chỗ.

Tính bất biến có lợi vì:

- Đường ghi chủ yếu tạo dữ liệu mới, phù hợp ghi tuần tự theo đợt.
- Dễ duy trì checksum và các cấu trúc index bên cạnh file.
- Một file đã hoàn tất có thể được nhiều reader sử dụng mà không cần cho reader nhìn thấy thao tác sửa giữa chừng.
- Compaction có thể tạo file mới rồi chuyển sang sử dụng file đó khi an toàn.
- Snapshot có thể tận dụng file bất biến trong một số hệ, tùy cơ chế tham chiếu và retention.

Đổi lại, hệ phải có cơ chế quản lý nhiều file, nhiều phiên bản và thời điểm loại dữ liệu cũ.

### 2.3. Một SSTable không phải toàn bộ database

Trong Cassandra, một bảng có thể có nhiều SSTable trên mỗi node, trải qua nhiều memtable flush và compaction. Trong một LSM implementation khác, file có thể được nhóm theo các **level** hoặc những tập sorted runs.

Không nên hình dung “mỗi bảng đúng một SSTable” hoặc “mỗi khóa chỉ xuất hiện trong một file” tại mọi thời điểm.

### 2.4. Sorted run và SSTable

Một **sorted run** là tập dữ liệu đã sắp theo khóa. Nó có thể được biểu diễn bằng một hoặc nhiều file. SSTable là một cách hiện thực sorted run được nhiều hệ lưu trữ sử dụng.

Trong bài, ta thường nói “SSTable/file bất biến” để mô tả nguyên lý; định dạng file, chỉ mục, phân mảnh và giao thức commit file tùy engine.

## 3. Kiến trúc LSM-tree: WAL, memtable và SSTable

### 3.1. Sơ đồ tổng thể

~~~mermaid
flowchart TD
    A["Client ghi key/value"] --> B["Write-Ahead Log / Commit Log"]
    A --> C["Memtable trong RAM"]
    C --> D["Flush"]
    D --> E["SSTable mới, bất biến"]
    E --> F["Compaction"]
    G["Các SSTable cũ"] --> F
    F --> H["SSTable hợp nhất"]
    H --> I["Cập nhật metadata và thu hồi file cũ khi an toàn"]
~~~

Sơ đồ nhấn mạnh **các thành phần** chứ không quy định một thứ tự I/O tuyệt đối. Đường ghi và cách ACK/đồng bộ WAL–memtable khác nhau theo engine. Không phải cứ xuất hiện mũi tên từ client sang WAL rồi memtable là mọi thao tác đều fsync WAL trước khi cập nhật RAM.

### 3.2. Write-ahead log / commit log

RAM là bộ nhớ mất dữ liệu khi tiến trình hoặc máy bị mất điện. Nếu ứng dụng chỉ ghi memtable mà chưa đưa dữ liệu đến nơi bền vững, một crash có thể làm mất những mutation gần nhất.

**WAL/commit log** lưu thông tin mutation phục vụ khôi phục:

~~~text
Log:
  seq 101: PUT K1 = A
  seq 102: PUT K2 = B
  seq 103: PUT K1 = C
  seq 104: DELETE K2
~~~

Sau crash, storage engine có thể nạp SSTable đã hoàn tất rồi replay các mutation hợp lệ trong log còn cần thiết để tái tạo memtable/trạng thái mới.

**Quan trọng:** Việc ghi vào log được ACK là bền vững tới mức nào phụ thuộc cơ chế flush/fsync, cấu hình durability, thiết bị lưu và chính sách replica. Một lời gọi append ở API không tự đồng nghĩa dữ liệu đã tới phương tiện bền vững. Phải hiểu hợp đồng ACK của sản phẩm.

### 3.3. Memtable

**Memtable** là cấu trúc trong bộ nhớ giữ những mutation gần đây, thường được tổ chức để tra cứu hoặc xuất dữ liệu theo khóa.

~~~text
Memtable:
  K1 -> C, seq 103
  K2 -> DELETE, seq 104
~~~

Nhiều cập nhật cùng khóa có thể được biểu diễn/ghép trong memtable theo ngữ nghĩa engine. Đừng mặc định memtable luôn lưu tất cả mutation như danh sách tuyến tính; ví dụ các hệ lưu nhiều version hoặc cell có thể có cách tổ chức khác.

### 3.4. Flush

Khi memtable đạt ngưỡng hoặc có lý do vận hành khác, engine **flush** nội dung ra đĩa thành SSTable mới:

~~~text
Memtable  -> serialize/sort -> SSTable-002
~~~

Các engine thường có cách luân chuyển memtable đang ghi và memtable chờ flush để tiếp tục nhận request.

Flush **không phải compaction**. Flush tạo file mới từ dữ liệu trong RAM; compaction xử lý nhiều file đã tồn tại nhằm tổ chức lại hoặc loại dữ liệu cũ.

### 3.5. Khi nào log có thể được dọn?

Khi những mutation được bảo vệ bởi một segment WAL đã được ghi sang các cấu trúc bền vững đủ điều kiện, engine có thể thu hồi segment log tương ứng.

Nếu crash giữa flush, việc khôi phục phải biết file nào đã hoàn tất và log nào vẫn cần replay. Vì vậy cần metadata, checksum, manifest/commit protocol và thứ tự ghi thích hợp tùy implementation.

Không nên tự xóa file WAL chỉ vì “đã nhìn thấy vài SSTable mới”.

## 4. Ví dụ từng bước: cập nhật cùng một khóa

Giả sử giá trị stock của sản phẩm P101 được cập nhật:

~~~text
t1: PUT P101 = 12
t2: PUT P101 = 10
t3: PUT P101 = 9
~~~

Một chuỗi hoạt động minh họa:

| Thời điểm | Memtable | SSTable trên đĩa |
|---|---|---|
| Sau t1 | P101 → 12 | Chưa flush |
| Sau flush 1 | Rỗng/đã luân chuyển | S1: P101 → 12 |
| Sau t2 | P101 → 10 | S1: P101 → 12 |
| Sau flush 2 | Rỗng/đã luân chuyển | S1: 12; S2: 10 |
| Sau t3 | P101 → 9 | S1: 12; S2: 10 |
| Sau flush 3 | Rỗng/đã luân chuyển | S1: 12; S2: 10; S3: 9 |
| Sau compaction phù hợp | Không đổi logic | File mới có giá trị hợp lệ 9 |

Đây là mô hình khái niệm. Các engine khác nhau về version visibility, timestamp, sequence number và snapshot. **Không được lấy “giá trị ghi cuối theo đồng hồ thực” làm quy tắc chung**: một hệ có thể phân giải xung đột bằng mutation timestamp, sequence number, MVCC hoặc điều kiện ghi.

Khi compaction thay các SSTable cũ bằng file mới, giá trị ứng dụng nhìn thấy không được tự nhiên chuyển từ 9 về 10 hay 12. Hợp nhất dữ liệu là một hoạt động **vật lý** và phải giữ các bảo đảm **logic** của storage engine.

## 5. Đường đọc: tìm khóa trong nhiều file bất biến

### 5.1. Đọc một khóa không chỉ là mở đúng một file

Ví dụ:

~~~text
Memtable:       K -> version 7
SSTable S3:     K -> version 6
SSTable S2:     K -> version 4
SSTable S1:     K -> version 1
~~~

Reader phải biết:

1. Memtable có dữ liệu nào liên quan?
2. Những SSTable nào **có khả năng chứa khóa hoặc phạm vi khóa**?
3. Trong mỗi file, dữ liệu nào có hiệu lực theo timestamp/sequence number?
4. Có tombstone hoặc TTL đã hết hạn không?
5. Reader cần một snapshot tại mốc nào, nếu hệ hỗ trợ snapshot/MVCC?

Không thể đơn giản tìm thấy giá trị ở file đầu tiên rồi trả về nếu file đó không bảo đảm mới nhất theo quy tắc của engine.

### 5.2. Chỉ mục trong SSTable

Vì file có thứ tự, engine có thể dùng các cấu trúc như:

- **Sparse index:** Giữ một số mốc khóa và offset của block, thay vì mọi entry.
- **Index summary:** Thu hẹp vùng tìm trước khi đọc index đầy đủ.
- **Block index:** Định vị block chứa phạm vi khóa.
- **Key range metadata:** Biết min/max key để bỏ qua file không thể chứa khóa cần tìm.
- **Compression metadata:** Xác định block nén cần giải mã.
- **Checksum:** Phát hiện dữ liệu hoặc block bị hỏng.

Tên và cấu trúc cụ thể tùy Cassandra, RocksDB, HBase hoặc engine khác.

### 5.3. Bloom filter

**Bloom filter** là cấu trúc xác suất giúp kiểm tra xem một SSTable **có thể chứa** khóa K hay không.

~~~text
Bloom(K) = "definitely not present" -> bỏ qua file.
Bloom(K) = "possibly present"       -> kiểm tra index/data.
~~~

Với Bloom filter được xây và sử dụng đúng:

- **False positive** có thể xảy ra: filter nói “có thể có” dù file không chứa K.
- **False negative** không xảy ra trong mô hình Bloom filter chuẩn khi dữ liệu và metadata không bị lỗi: nếu file thực sự có K mà filter nói chắc chắn không, logic lọc đã sai.

Bloom filter **không cho biết giá trị mới nhất**, không thay thế đọc dữ liệu, cũng không đảm bảo query range có thể bỏ qua toàn bộ SSTable.

### 5.4. Bloom filter có chi phí bộ nhớ

Nếu filter dùng m bit cho n khóa và k hàm băm, xác suất false positive lý tưởng thường được xấp xỉ:

\[
f \approx \left(1-e^{-kn/m}\right)^k.
\]

Với mật độ bit/khóa cố định, số hàm băm tối ưu xấp xỉ:

\[
k \approx \frac{m}{n}\ln 2.
\]

Tăng số bit cho mỗi khóa có thể giảm false positive nhưng tăng RAM/metadata. Một hệ có rất nhiều SSTable có thể tốn đáng kể bộ nhớ cho Bloom filters và index summaries.

**Tối ưu** không phải luôn đặt false-positive probability thấp nhất, mà là cân bằng RAM, disk reads và workload truy vấn.

### 5.5. Point lookup so với range scan

**Point lookup:**

~~~text
GET key = P101
~~~

Bloom filter và key range có thể giảm số file phải đọc.

**Range scan:**

~~~text
GET keys từ P100 tới P200
~~~

Nhiều file có thể chứa các khóa trong khoảng đó. Engine thường phải duyệt những iterator đã sắp xếp rồi merge các luồng, loại version đã cũ và tombstone theo ngữ nghĩa.

Vì vậy, một workload 99% point reads có thể ưu tiên cấu hình khác workload đọc phạm vi dài.

## 6. K-way merge: nền tảng của hoạt động hợp nhất

### 6.1. Hợp nhất các luồng đã sắp

Giả sử:

~~~text
S1: A=1, C=3, E=5
S2: B=2, C=4, F=6
S3: A=7, D=8, G=9
~~~

Các file đều đã sắp theo khóa. Compaction có thể duyệt đồng thời ba luồng và xuất file mới vẫn được sắp:

~~~text
Output keys: A, B, C, D, E, F, G
~~~

Với những bản ghi trùng khóa, phải áp dụng **quy tắc phiên bản/timestamp**, không phải tùy ý lấy file đến trước.

Trong mô hình giá trị đơn giản không có snapshot/tombstone:

~~~text
A -> 7 (thay A=1)
B -> 2
C -> 4 (thay C=3)
D -> 8
E -> 5
F -> 6
G -> 9
~~~

Nhưng kết quả thực tế có thể cần giữ nhiều version nếu reader snapshot cũ còn sử dụng hoặc nếu engine lưu nhiều cell với timestamp khác nhau.

### 6.2. Vì sao merge có thể hiệu quả?

Nếu k luồng đã sắp có tổng n entry, thuật toán merge thường không cần sắp xếp lại n entry từ đầu. Có thể dùng min-heap hoặc những iterator theo khóa để chọn entry tiếp theo.

Mô hình chi phí lý thuyết thường là:

\[
O(n\log k)
\]

cho phép duyệt k-way merge với heap, chưa tính chi phí giải mã block, đọc/ghi storage, lọc tombstone và các tối ưu khác của implementation.

**Lợi ích thực tế:** Hợp nhất dữ liệu theo luồng có thể tận dụng truy cập tuần tự và tránh nhiều thao tác ghi ngẫu nhiên nhỏ.

### 6.3. Bất biến không có nghĩa luôn tạo đúng một file mới

Một compaction có thể:

- Đọc một nhóm SSTable.
- Tạo **nhiều SSTable đầu ra** theo kích thước, level hoặc phạm vi khóa.
- Cập nhật metadata/manifest để công bố file mới.
- Chỉ thu hồi file cũ khi không còn reader/snapshot hoặc tham chiếu cần thiết.

Đây là quá trình đổi một **tập file** thành một **tập file mới** nhưng giữ quan sát dữ liệu hợp lệ.

## 7. Flush và compaction khác nhau thế nào?

| Tiêu chí | Flush | Compaction |
|---|---|---|
| Nguồn dữ liệu | Memtable trong RAM | Một hoặc nhiều SSTable có sẵn |
| Đầu ra | SSTable mới | SSTable được tổ chức/hợp nhất lại |
| Mục đích chính | Đưa dữ liệu RAM thành cấu trúc trên đĩa | Giảm trùng phiên bản, tổ chức level/run, tối ưu đọc/dung lượng |
| Có thể giảm dữ liệu cũ? | Tùy nội dung memtable, không phải mục tiêu chính | Có thể loại dữ liệu bị thay thế/tombstone khi an toàn |
| Gây disk I/O? | Có | Có, đôi khi rất nhiều |
| Liên quan durability? | Có vai trò trong bảo vệ dữ liệu được flush | Không phải định nghĩa duy nhất của commit/durability |
| Thời điểm | Theo ngưỡng hoặc điều kiện memtable | Theo chiến lược compaction, tải và tài nguyên |

Một lệnh ghi có thể đã được ACK theo chính sách WAL/replication **trước khi memtable được flush**. Không nên dùng câu “chưa xuất hiện trong SSTable thì chưa được commit” làm quy tắc chung.

Ngược lại, dữ liệu nằm trong SSTable không đồng nghĩa mọi replica khác cũng đã có nó hay mọi backup đều chứa dữ liệu đó.

## 8. Tại sao phải compaction?

### 8.1. Giảm số file cần xét

Sau hàng nghìn lần flush, nếu không hợp nhất, một point read có thể phải kiểm tra rất nhiều SSTable. Bloom filter giúp giảm tìm kiếm âm nhưng không tự xóa số file vật lý hoặc tất cả phiên bản cũ.

Compaction có thể giảm số sorted runs/file chồng lắp, nhờ đó cải thiện read amplification.

### 8.2. Loại version đã bị thay thế

Giả sử:

~~~text
K1 -> version 1 ở S1
K1 -> version 2 ở S2
K1 -> version 3 ở S3
~~~

Nếu các reader/snapshot không còn cần version cũ và điều kiện ngữ nghĩa được thỏa, compaction có thể chỉ giữ version 3 trong đầu ra.

Điều này làm giảm **space amplification** do dữ liệu cũ.

### 8.3. Dọn tombstone và dữ liệu hết TTL khi an toàn

DELETE thường tạo dấu xóa, còn TTL hết hạn có thể làm dữ liệu không còn hiệu lực. Compaction có thể loại dấu xóa cùng dữ liệu liên quan **chỉ khi an toàn theo cơ chế của hệ**.

Trong Cassandra, replica có thể bỏ lỡ DELETE, vì vậy việc dọn tombstone liên quan tới grace period và repair. Trong một engine snapshot/MVCC, khả năng giữ version còn phụ thuộc các reader snapshot đang hoạt động và mức bảo vệ dữ liệu.

### 8.4. Tạo layout phù hợp chiến lược

Một số chiến lược tổ chức SSTable theo kích thước; một số theo level với phạm vi khóa ít chồng lắp; một số theo khoảng thời gian. Compaction giúp tạo và duy trì layout đó.

### 8.5. Đổi lại phải đọc và ghi dữ liệu nhiều lần

Compaction đọc file đầu vào và ghi file đầu ra. Đó là **write amplification**, đồng thời tiêu thụ:

- Disk bandwidth/IOPS.
- CPU cho merge, nén và checksum.
- Bộ nhớ đệm và metadata.
- Dung lượng tạm khi file mới cùng tồn tại với file cũ.

Vì vậy không thể “compaction càng nhiều càng tốt”.

## 9. Ba loại amplification cần hiểu

### 9.1. Write amplification

**Write amplification** diễn đạt lượng dữ liệu vật lý được ghi nhiều hơn dữ liệu ghi logic.

Một cách đo ở tầng storage:

\[
\text{WA} =
\frac{\text{Tổng số byte được ghi vào thiết bị}}
{\text{Số byte ghi logic từ ứng dụng}}.
\]

Ví dụ minh họa:

~~~text
Ứng dụng ghi logic:           100 GB
WAL và SSTable flush:         180 GB
Compaction ghi thêm:          420 GB
Tổng byte ghi đo được:        600 GB
WA quan sát được:               6
~~~

Con số chỉ minh họa. WA thay đổi tùy tầng đo (có/không tính WAL, replication, filesystem, compression), nên khi so hai kết quả phải thống nhất **định nghĩa tử số và mẫu số**.

### 9.2. Read amplification

**Read amplification** có thể đo bằng số file/block/byte vật lý cần đọc so với một yêu cầu logic. Một point lookup duy nhất nhưng phải kiểm tra nhiều SSTable là ví dụ.

~~~text
GET K -> kiểm tra memtable
      -> Bloom S4
      -> Index S4
      -> Bloom S3
      -> Index S3
      -> Data block
~~~

Đây là một đường đọc phức tạp hơn tra cứu trực tiếp một block phù hợp, dù Bloom filter có thể giúp bỏ qua nhiều file.

### 9.3. Space amplification

**Space amplification** là phần dung lượng lưu thêm do nhiều phiên bản, tombstone, metadata và quá trình compaction, tùy cách định nghĩa.

Ví dụ:

~~~text
Dữ liệu logic còn hiệu lực: 200 GB
SSTable đang sử dụng:        300 GB
Tạm thời khi compaction:     thêm 100 GB
~~~

Tỉ lệ storage theo thời điểm có thể khác nhau khi compaction bắt đầu, đang chạy hoặc hoàn tất. Nếu không dự phòng chỗ trống cho file đầu ra, compaction có thể kẹt vì **disk full**.

### 9.4. Tam giác đánh đổi

Tối ưu đường ghi bằng nhiều file nhỏ có thể tăng số file phải đọc. Hợp nhất aggressively có thể giảm file/space nhưng tăng byte ghi. Một số chiến lược ưu tiên đọc, số khác ưu tiên ghi hoặc dữ liệu có TTL.

**Không có chiến lược đồng thời tối ưu read amplification, write amplification và space amplification ở mọi workload.**

## 10. Size-Tiered Compaction Strategy (STCS)

### 10.1. Ý tưởng

**Size-tiered compaction** thường chọn những SSTable có kích thước gần nhau thành nhóm rồi hợp nhất chúng.

~~~text
S1  64 MB --\
S2  70 MB ---+--> Compaction --> SSTable khoảng 270 MB
S3  66 MB ---+
S4  70 MB --/
~~~

Con số và cách chọn nhóm là minh họa, không phải cấu hình cố định.

Trong Cassandra có chiến lược **SizeTieredCompactionStrategy (STCS)** với những thông số cụ thể; các phiên bản/cấu hình có thể khác.

### 10.2. Lợi ích

- Có thể phù hợp với workload ghi nhiều.
- Hợp nhất theo lô và tránh liên tục viết lại dữ liệu ở mỗi level nhỏ.
- Cấu trúc tương đối dễ hiểu.

### 10.3. Hạn chế

- Có thể tồn tại nhiều SSTable chồng lắp phạm vi khóa.
- Point read và range read có thể phải xét nhiều file.
- Space amplification có thể cao khi bản ghi cũ bị che nhưng chưa gặp nhóm compaction phù hợp.
- Nhu cầu dung lượng tạm có thể đáng kể khi nhiều file lớn được hợp nhất.

### 10.4. Khi cân nhắc STCS

Thường cần xét nếu workload chủ yếu ghi, ít cập nhật chồng lắp hay có yêu cầu đọc không quá chặt. Nhưng việc lựa chọn dựa trên đúng sản phẩm, metric và phân bố dữ liệu, không chỉ nhãn “write-heavy”.

Nếu hệ có TTL đồng đều và workload time-series, chiến lược theo thời gian có thể phù hợp hơn tùy điều kiện.

## 11. Leveled Compaction Strategy (LCS)

### 11.1. Ý tưởng chia level

**Leveled compaction** tổ chức dữ liệu vào các level, thường với mục tiêu hạn chế **phạm vi khóa chồng lắp giữa các file trong cùng những level được tổ chức**.

Ví dụ khái niệm:

~~~text
L0: [S1: A..Z] [S2: C..T] [S3: A..F]
      (có thể chồng lắp)

L1: [A..F] [G..M] [N..T] [U..Z]
      (ít hoặc không chồng lắp trong level theo thiết kế)

L2: [A..D] [E..H] [I..L] [M..P] [Q..T] [U..Z]
      (tập lớn hơn; phạm vi được tổ chức)
~~~

Một compaction từ level nhỏ sang level lớn có thể phải lấy cả những file ở level đích **chồng lắp khoảng khóa**.

### 11.2. Lợi ích

- Đường đọc có thể ít phải xét file hơn ở những level không chồng lắp.
- Có thể cải thiện read amplification và giới hạn số phiên bản chồng lắp.
- Thường được cân nhắc khi workload đọc point/range nhạy cảm độ trễ.

### 11.3. Chi phí

- Một key range ở level đích có thể bị viết lại nhiều lần khi dữ liệu từ level nhỏ chảy xuống.
- Write amplification có thể cao hơn trong những workload so với chiến lược size-tiered.
- Compaction cần disk bandwidth ổn định.
- L0 chồng lắp hoặc compaction backlog có thể khiến reads/ghi bị ảnh hưởng.

### 11.4. Hiểu level không phải hiểu “mỗi level là một file”

Level thường gồm **nhiều SSTable**. Mục đích là tổ chức các phạm vi khóa và dung lượng để giới hạn chồng lắp, không phải gom toàn database vào một file ở mỗi level.

### 11.5. Khi cân nhắc LCS

Đọc point/range thường xuyên, cập nhật lặp trên cùng khóa và yêu cầu latency ổn định có thể là lý do cân nhắc. Nhưng nếu compaction không theo kịp tốc độ ghi, ưu điểm đọc có thể bị suy giảm và áp lực ghi tăng.

## 12. Time-Window Compaction Strategy (TWCS)

### 12.1. Tổ chức theo cửa sổ thời gian

**Time-window compaction** nhóm dữ liệu theo cửa sổ thời gian, thường phù hợp với dữ liệu có TTL/retention và được ghi theo thời gian tương đối đều đặn.

~~~text
Window 2026-11-12: [SSTables của khoảng thời gian này]
Window 2026-11-13: [SSTables của khoảng thời gian này]
Window 2026-11-14: [SSTables của khoảng thời gian này]
~~~

Khi một cửa sổ cũ đã ổn định và toàn bộ nội dung đủ điều kiện hết hạn, engine có thể dọn hiệu quả hơn so với các file chứa lẫn dữ liệu rất cũ và rất mới.

Trong Cassandra, **TimeWindowCompactionStrategy (TWCS)** có hành vi và tham số cụ thể. Đừng nhầm mọi phương án time bucketing ở schema với TWCS ở tầng storage: chúng giải quyết những vấn đề liên quan nhưng ở **hai lớp khác nhau**.

### 12.2. Điều kiện phù hợp

TWCS thường được cân nhắc cho:

- Telemetry/time-series.
- Log sự kiện ghi theo thời gian.
- Retention TTL tương đối đồng đều.
- Dữ liệu cũ ít bị cập nhật sau khi cửa sổ đóng.

### 12.3. Late writes và out-of-order data

Nếu liên tục ghi sự kiện có timestamp cũ, hoặc cập nhật lại key cũ ở nhiều cửa sổ, những file thuộc các cửa sổ có thể chứa dữ liệu có phiên bản liên quan nhưng không được hợp nhất theo giả định ban đầu.

Điều này có thể làm giảm khả năng purge đơn giản, tạo tombstone/phiên bản tồn tại lâu hoặc ảnh hưởng kỳ vọng đọc. Vì vậy workload có late-arriving events hoặc backfill lịch sử cần đánh giá kỹ trước khi chọn TWCS.

### 12.4. TTL không đồng đều

Nếu một file chứa dữ liệu TTL 7 ngày cùng dữ liệu TTL 2 năm, không thể mặc định cả file được loại khi phần 7 ngày hết hạn. Retention hỗn hợp làm giảm lợi ích của việc tổ chức theo cửa sổ.

### 12.5. TWCS không thay thế repair

Dù dữ liệu theo thời gian có thể thuận lợi cho compaction, việc xóa/TTL trong hệ replicated vẫn phải tuân thủ nguyên tắc an toàn về tombstone, gc grace và repair tương ứng.

## 13. Universal compaction và các biến thể khác

Một số engine như RocksDB hỗ trợ **universal compaction** hoặc các chế độ/heuristic khác. Chúng có thể chọn sorted runs theo số lượng, kích thước hoặc mức độ chồng lắp để cân bằng chi phí ghi, đọc và dung lượng.

Với Cassandra/ScyllaDB cũng có các chiến lược và phiên bản bổ sung; tên và khả năng không hoàn toàn tương đương với compaction style của RocksDB.

Khi đọc tài liệu cấu hình, cần xác định rõ:

- Đây là cơ chế của engine nào?
- File được nhóm theo size, level, time window hay heuristic khác?
- Có hỗ trợ thay chiến lược khi bảng đang có dữ liệu không?
- Có backfill/rewrite lớn khi đổi cấu hình không?
- Những giới hạn tương thích phiên bản là gì?

Không nên lấy tham số của RocksDB đưa nguyên xi vào cấu hình Cassandra hoặc ngược lại chỉ vì cả hai đều thuộc họ LSM.

## 14. So sánh các chiến lược ở cấp độ tư duy

| Khía cạnh | Size-tiered | Leveled | Time-window |
|---|---|---|---|
| Tiêu chí nhóm file chính | Kích thước tương tự | Level và phạm vi khóa | Cửa sổ thời gian |
| Thích hợp tương đối | Workload ghi nhiều | Workload chú trọng đọc và kiểm soát chồng lắp | Time-series/TTL có tính thời gian rõ |
| Read amplification | Có thể cao khi nhiều file chồng lắp | Thường được kiểm soát tốt hơn khi các level ổn định | Tùy query và số cửa sổ |
| Write amplification | Có thể tiết kiệm hơn với một số workload | Có thể cao do viết lại giữa các level | Tùy cập nhật trễ và cách ghi dữ liệu |
| Space amplification | Có thể đáng kể giữa các đợt merge | Thường có cấu trúc giới hạn chồng lắp, vẫn cần chỗ tạm | Có lợi khi cửa sổ hết hạn đồng đều |
| Rủi ro chính | Nhiều file, compaction lớn, space | Compaction backlog và write pressure | Late writes, TTL không đồng nhất |

Đây là bảng **định hướng**, không phải bảng đảm bảo định lượng. Kết quả phụ thuộc engine, compression, kích thước file, tỷ lệ cập nhật, phân bố khóa, cache, replica và thiết bị lưu.

## 15. Tombstone: vì sao DELETE không thể chỉ “bỏ hàng khỏi file”?

### 15.1. Replica có thể giữ dữ liệu cũ

Giả sử cùng khóa K nằm trên ba replica:

~~~text
Replica A: K = active, timestamp=100
Replica B: K = active, timestamp=100
Replica C: K = active, timestamp=100
~~~

Replica C offline. A/B nhận DELETE:

~~~text
Replica A: tombstone K, timestamp=110
Replica B: tombstone K, timestamp=110
Replica C: K = active, timestamp=100
~~~

Nếu A/B dọn tombstone **trước khi C được sửa**, C có thể mang dữ liệu cũ trở lại trong quá trình đồng bộ. Đây là nguy cơ **data resurrection/zombie data**.

### 15.2. Dấu xóa cần tồn tại đủ lâu

Trong Cassandra, **gc_grace_seconds** là một cấu hình liên quan khoảng thời gian tombstone đủ điều kiện được thu gom, cùng những điều kiện khác. Cần kết hợp lịch repair và các cơ chế vận hành để những replica có liên quan không bỏ lỡ xóa.

**Không nên giảm gc_grace_seconds tùy tiện** chỉ vì muốn compaction nhanh hoặc giảm tombstone, bởi nó có thể ảnh hưởng tính đúng đắn.

### 15.3. Compaction không được purge tombstone thiếu điều kiện

Một compaction chỉ hợp nhất vài SSTable có thể chưa bao phủ mọi file chứa dữ liệu cũ liên quan. Nếu xóa tombstone khỏi đầu ra mà vẫn còn version cũ trong file không được compaction, một read sau này có thể nhìn thấy dữ liệu bị xóa.

Do đó, engine phải dùng các quy tắc về **phạm vi file, timestamp, grace, snapshot, replica/repair và metadata** phù hợp để xác định khi nào có thể an toàn loại tombstone.

### 15.4. TTL cũng tạo nhu cầu dọn dữ liệu cũ

Ví dụ CQL:

~~~sql
INSERT INTO activity_by_device_day (
    device_id, activity_day, occurred_at, event_id, payload
) VALUES (
    'D17', '2026-11-14', '2026-11-14T09:00:00Z',
    550e8400-e29b-41d4-a716-446655440001, 'reading'
) USING TTL 2592000;
~~~

Con số 2.592.000 giây tương đương 30 ngày theo cách tính 30 × 24 × 3600. Bảng và khóa trong ví dụ giả định đã được tạo tương ứng.

Sau TTL, dữ liệu hết hiệu lực theo semantics Cassandra, nhưng việc dọn vật lý không có nghĩa diễn ra chính xác khi đồng hồ đạt mốc 30 ngày.

### 15.5. Hinted handoff và anti-entropy repair

Hinted handoff có thể giúp chuyển mutation tới replica tạm thời không khả dụng, nhưng hint có giới hạn retention. Nếu replica mất kết nối lâu, **anti-entropy repair** là thành phần quan trọng để đồng bộ, trong đó có thông tin DELETE.

Chọn grace, compaction và repair phải là một quyết định thống nhất, không phải ba nút cấu hình độc lập.

## 16. Dữ liệu có TTL và time-series: thiết kế schema phối hợp với storage

### 16.1. Một bảng theo ngày

Ví dụ:

~~~sql
CREATE TABLE activity_by_device_day (
    device_id text,
    activity_day date,
    occurred_at timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY (
        (device_id, activity_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

Partition key (device_id, activity_day) cho phép truy vấn theo thiết bị/ngày và giới hạn lượng dữ liệu tăng trong mỗi partition. Nếu một thiết bị ghi hàng triệu event/ngày, cần đánh giá bucket nhỏ hơn hoặc chia shard, không coi mỗi ngày luôn vừa đủ.

### 16.2. Schema bucketing và compaction window khác nhau

**Schema bucket** là cách chia logical partitions theo khóa như deviceId và activityDay.

**Compaction window** là cách storage engine nhóm các SSTable theo thời gian.

Hai cơ chế có thể bổ trợ nhau, nhưng không đồng nhất. Một bảng có partition key theo ngày không tự động làm SSTable được nhóm theo ngày; phải chọn compaction strategy nếu engine hỗ trợ và workload phù hợp.

### 16.3. Retention theo event time hay ingest time?

Giả sử event đo lúc ngày 1 nhưng đến hệ thống ngày 40, trong khi chính sách giữ 30 ngày kể từ thời điểm đo.

Nếu ứng dụng cấp TTL mới 30 ngày kể từ khi ingest, dữ liệu sẽ được giữ lâu hơn chính sách. Cần quy tắc:

- Bỏ qua event đã quá hạn, hoặc
- Tính TTL còn lại theo event time, nếu hợp lệ, hoặc
- Lưu theo một khu vực archive có chính sách riêng.

Late writes không chỉ là vấn đề nghiệp vụ: chúng còn ảnh hưởng layout compaction theo cửa sổ thời gian.

### 16.4. Cập nhật lịch sử

Nếu event cũ bị sửa liên tục, cùng khóa có thể tạo version ở SSTable thuộc những thời gian ghi khác nhau. Với TWCS, hành vi này cần được đánh giá cẩn thận vì giả định cửa sổ cũ gần như bất biến không còn đúng.

Một workload thực sự là **append-mostly** thường phù hợp hơn workload luôn cập nhật lại dữ liệu nhiều tháng trước.

## 17. Compaction backlog và tác động lên ghi

### 17.1. Khi flush nhanh hơn compaction

Giả sử hệ tạo SSTable mới ở tốc độ:

~~~text
Flush tạo:           500 MB/phút
Compaction xử lý:    300 MB/phút
Chênh lệch:          200 MB/phút
~~~

Nếu kéo dài, số file hoặc byte chờ compaction có thể tăng. Hệ có thể:

- Tăng read amplification do file chồng lắp.
- Tăng nhu cầu disk.
- Tăng CPU và IO sử dụng cho compaction.
- Bắt đầu **write stall/throttling** theo cơ chế engine.
- Có p95/p99 latency xấu đi.

Đây là ví dụ nguyên lý. “MB compaction/ phút” không trực tiếp so được với “MB flush/ phút” nếu một byte logic cần được đọc/ghi nhiều lần trong các level; phải dùng các metric thực tế của engine.

### 17.2. Write stall

Một số engine LSM có cơ chế làm chậm hoặc dừng nhận ghi tạm thời khi:

- Có quá nhiều immutable memtable chờ flush.
- L0 có quá nhiều file.
- Compaction không theo kịp.
- Bộ nhớ hoặc disk đạt ngưỡng.

Write stall có thể là biện pháp bảo vệ hệ khỏi quá tải kéo dài, chứ không phải một lỗi ngẫu nhiên cần tắt bằng mọi giá.

### 17.3. Backpressure

Nếu đẩy workload ghi liên tục vượt năng lực lưu trữ, hệ có thể cần backpressure:

~~~text
Client requests
      |
      v
Ingestion queue có giới hạn
      |
      v
Storage writes
      |
      v
Flush + compaction
~~~

Cần kiểm soát tốc độ producer, kích thước queue, retry, timeout và tính idempotent. Nếu chỉ tăng memory buffer mà không cải thiện disk throughput, vấn đề có thể xuất hiện muộn hơn nhưng lớn hơn.

## 18. Dung lượng trống và compaction

### 18.1. Compaction cần chỗ cho file đầu ra

Một compaction có thể đọc tổng cộng 120 GB SSTable và ghi ra một tập file mới trong lúc những file cũ vẫn cần được giữ đến khi chuyển trạng thái an toàn.

Trong thời gian đó, dung lượng đĩa cần có thể **tăng tạm thời**. Nếu filesystem gần đầy, compaction có thể không đủ chỗ để kết thúc, dù file đầu ra sau khi loại version cũ sẽ nhỏ hơn về lâu dài.

### 18.2. Không có một tỉ lệ dự phòng chung

Nhu cầu chỗ trống phụ thuộc:

- Loại compaction.
- Kích thước và số file được chọn.
- Compression ratio cũ/mới.
- Concurrent compactions.
- Snapshot/hard links giữ SSTable cũ.
- Disk placement và chính sách cleanup của engine.

Không nên đề xuất “chừa đúng 10% disk là đủ” như quy tắc chung. Phải theo dõi **peak temporary space** và hướng dẫn của storage engine/cấu hình cụ thể.

### 18.3. Snapshot và file bất biến

Trong một số hệ, snapshot có thể giữ tham chiếu/hard link tới SSTable bất biến. Vì vậy compaction đã tạo file mới **không tự giải phóng** mọi bytes của SSTable cũ nếu snapshot vẫn tham chiếu chúng.

Khi thấy dung lượng không giảm sau compaction, cần kiểm tra snapshot retention và các thành phần khác thay vì cho rằng compaction đã thất bại.

## 19. Compression và checksum trong SSTable

### 19.1. Nén theo block

SSTable thường có cơ chế nén block/file tùy engine. Nén giảm byte trên disk và đôi khi giảm byte phải đọc, nhưng cần CPU để giải nén.

~~~text
Logical data       1.000 MB
Compressed blocks    450 MB
Metadata              30 MB
--------------------------------
Stored approx.       480 MB
~~~

Đây là ví dụ minh họa, không phải compression ratio mặc định.

### 19.2. Vì sao compaction có thể thay đổi dung lượng nén?

Khi hợp nhất, dữ liệu được sắp lại và các bản ghi cũ có thể bị loại; block được tạo lại với tập giá trị khác. Compression ratio có thể thay đổi ngay cả khi số bản ghi logic không đổi nhiều.

### 19.3. Checksum và dữ liệu hỏng

Checksum có thể phát hiện một số kiểu hỏng block/file khi đọc hoặc xác minh. Nó không thay thế replication, backup và cơ chế phục hồi dữ liệu, vì checksum phát hiện lỗi chứ không tự cung cấp bản sao lành.

Nếu một file SSTable bị hỏng, việc sửa thường cần các cơ chế của sản phẩm: repair, restore hoặc công cụ kiểm tra/sửa chuyên biệt. Không nên tự sửa byte trong file bất biến bằng trình soạn thảo.

## 20. Durability: WAL, flush, compaction, replication và backup

### 20.1. Một chuỗi ghi có nhiều mức bảo đảm

Ví dụ:

~~~text
Client gửi mutation
  |
  +--> WAL/commit log theo durability policy
  |
  +--> Memtable
  |
  +--> Replica ACK theo consistency/durability level
  |
  +--> Flush thành SSTable
  |
  +--> Compaction về sau
~~~

Sơ đồ chỉ mô tả các khái niệm; thứ tự ACK và thời điểm fsync phụ thuộc sản phẩm.

Đừng nhầm:

- **Durability của một ghi đã ACK:** Khả năng bảo tồn mutation theo hợp đồng khi crash/failover.
- **Flush:** Chuyển dữ liệu từ bộ nhớ thành file trên đĩa.
- **Compaction:** Tổ chức lại các file và dọn dữ liệu cũ khi an toàn.
- **Replication:** Duy trì bản sao trên nhiều node/Region theo chính sách.
- **Backup:** Khả năng khôi phục trạng thái từ bản sao lịch sử.

### 20.2. Replication không thay thế backup

Nếu ứng dụng DELETE nhầm một bảng, thao tác có thể được sao chép tới mọi replica. Replication giúp chịu lỗi node, nhưng không tự khôi phục trạng thái trước khi xóa nhầm.

Backup/snapshot có mục đích khác: hỗ trợ phục hồi lịch sử. Tuy nhiên restore backup cũ cần áp dụng những quyết định xóa hợp lệ đã xảy ra sau snapshot nếu không muốn hồi sinh dữ liệu đã bị xóa theo yêu cầu.

### 20.3. Backup dựa trên SSTable

Tính bất biến có thể giúp hệ tạo snapshot bằng cách giữ tham chiếu tới những file đã hoàn tất. Song file snapshot thôi có thể chưa đủ để khôi phục tới một mốc mong muốn nếu còn mutation trong log chưa được bao phủ; cần quy trình backup/WAL archival của engine.

Không nên copy ngẫu nhiên những SSTable từ một node đang hoạt động rồi coi đó là bản backup nhất quán, đặc biệt trong hệ distributed.

### 20.4. Recovery sau crash

Một quá trình khôi phục khái niệm:

1. Đọc metadata xác định các file SSTable đã commit.
2. Bỏ qua hoặc xử lý file compaction/flush dang dở theo giao thức của engine.
3. Mở những SSTable hợp lệ.
4. Replay những mutation trong WAL còn cần thiết.
5. Tái tạo memtable/index metadata như thiết kế.
6. Tham gia replication/repair để hội tụ dữ liệu nếu cần.

Đây không phải hướng dẫn chạy công cụ phục hồi thủ công. Quy trình thực tế phụ thuộc engine và cần dùng công cụ chính thức của sản phẩm.

## 21. Những hệ dùng cấu trúc bất biến nhưng khác chi tiết

### 21.1. Cassandra

Apache Cassandra có memtable, commit log, SSTable, compaction strategies và cơ chế repair trong một cơ sở dữ liệu wide-column phân tán. Bài học này khớp trực tiếp nhiều khái niệm của Cassandra.

Tuy nhiên, trong Cassandra, thông tin thường ở cấp **cell/column/partition**, có timestamp và TTL. Không được giả định mỗi SSTable chỉ lưu “một cặp key → một JSON value”.

### 21.2. ScyllaDB

ScyllaDB triển khai nhiều ý tưởng wide-column/LSM/SSTable tương tự Cassandra nhưng có những khác biệt kỹ thuật về runtime, tối ưu IO, compaction, shard per core và các lựa chọn theo phiên bản.

Không nên chuyển nguyên thông số thread count, memory hoặc công cụ quản trị từ Cassandra sang ScyllaDB nếu chưa kiểm tra tài liệu của sản phẩm cụ thể.

### 21.3. RocksDB

RocksDB là một embedded key–value storage engine thuộc họ LSM, thường dùng WAL, memtable và SSTables, với compaction style và tham số riêng.

RocksDB không tự cung cấp đầy đủ **distributed replication/consensus** cho một ứng dụng chỉ vì nó dùng SSTable; những bảo đảm phân tán phụ thuộc hệ bao quanh.

### 21.4. HBase

HBase có MemStore, HFile, WAL và minor/major compaction trong kiến trúc phù hợp với mô hình storage phân tán của nó. HFile là định dạng file có thứ tự/bất biến ở mức khái niệm, nhưng giao thức, layout và repair không giống Cassandra.

### 21.5. MongoDB và Redis

MongoDB/WiredTiger thường dùng cơ chế B-tree và checkpoint/journal theo kiến trúc riêng; không nên nói mọi document update của MongoDB đều tạo SSTable mới rồi chờ LSM compaction.

Redis chủ yếu lưu dữ liệu trong bộ nhớ với các hình thức persistence như RDB/AOF. Redis cũng có cơ chế rewrite/compaction kiểu khác ở những tầng liên quan, nhưng chúng không đồng nhất với LSM compaction của Cassandra.

**Nguyên tắc:** Trước khi chọn tham số compaction, hãy xác nhận hệ thật sự dùng storage engine nào.

## 22. So sánh LSM và B-tree theo đánh đổi cơ bản

| Khía cạnh | LSM/SSTable điển hình | B-tree điển hình |
|---|---|---|
| Đường ghi | Ghi log/buffer, tạo sorted runs, merge về sau | Cập nhật page/index theo tổ chức cây, thường có logging |
| Ghi nhỏ ngẫu nhiên | Có thể gom thành ghi tuần tự/batch | Có thể phải cập nhật page ở vị trí khác nhau, tùy cache |
| Point read | Có thể xét memtable và nhiều run/file | Thường duyệt cấu trúc cây tới page chứa khóa |
| Range scan | Merge các sorted runs, có thể khá tốt | Duyệt các page lá có thứ tự |
| Phiên bản cũ | Có thể tồn tại đến compaction/GC | Có cơ chế reclaim/MVCC riêng |
| Dọn dữ liệu | Compaction và GC tombstone/old versions | Page management, vacuum/cleanup tùy engine |
| Chi phí nền | Compaction I/O/CPU | Page split, checkpoint, vacuum hoặc các cơ chế khác |

Đây là so sánh định hướng, không phải khẳng định “LSM luôn ghi nhanh hơn B-tree” hay “B-tree luôn đọc nhanh hơn LSM”. Cache, compression, flash storage, workload, đồng thời, phạm vi query và tối ưu của sản phẩm có thể đảo kết quả thực tế.

## 23. Theo dõi compaction trong vận hành

### 23.1. Những metric quan trọng

| Metric | Ý nghĩa |
|---|---|
| Số SSTable/table hoặc level | Nhiều file có thể tăng read overhead |
| Pending compaction tasks/bytes | Mức backlog |
| Compaction throughput | Tốc độ xử lý/ghi lại dữ liệu |
| Flush frequency và duration | Đường memtable ra disk |
| Immutable memtable count | Áp lực flush ở những engine hỗ trợ |
| WAL/commit-log size | Dữ liệu chưa được bảo vệ qua flush theo cách engine cần |
| Read amplification/file checks | Chi phí xét nhiều file cho một read |
| Write amplification/bytes rewritten | Chi phí ghi nền |
| Tombstone scans/warnings | Dấu xóa gây áp lực query |
| Disk free và temporary peak | Khả năng compaction hoàn tất |
| Read p50/p95/p99 | Độ trễ đường đọc |
| Write p50/p95/p99, stall time | Độ trễ ghi và backpressure |
| CPU/disk utilization | Tranh chấp tài nguyên giữa traffic và compaction |
| Repair backlog/health | An toàn replica và tombstone |

### 23.2. Một chỉ số riêng lẻ không nói đủ

“Có 1.000 SSTable” chưa đủ để kết luận xấu nếu chúng thuộc nhiều bảng/partition hoặc level được tổ chức khác nhau. Cần biết:

- File có chồng lắp phạm vi khóa không?
- Query thường đọc point hay range?
- Bloom filters và index summaries đang hoạt động thế nào?
- Chỉ số reads examined/file và latency có tăng không?
- Compaction backlog có tăng lâu dài không?

Tương tự, một đợt compaction ghi hàng trăm GB có thể bình thường khi thay chiến lược hoặc rebuild, nhưng đáng lo nếu lặp liên tục trong điều kiện workload không đổi.

### 23.3. Cảnh báo theo xu hướng

Những tín hiệu nên xem như nhóm:

~~~text
SSTable count tăng liên tục
  + pending compaction bytes tăng
  + write stall tăng
  + disk free giảm
  + p99 read latency tăng
~~~

Tổ hợp này có thể cho thấy compaction không theo kịp. Cần xác định nguyên nhân là disk throughput, CPU, compaction configuration, lưu lượng ghi tăng đột biến, snapshot giữ file hay một vấn đề khác.

## 24. Chọn chiến lược theo workload thực tế

### 24.1. Workload A: ghi nhiều, đọc theo key ít

~~~text
100.000 mutation/giây
80% INSERT mới
15% UPDATE
5% DELETE
Phần lớn đọc point lookup
~~~

Cần đo tốc độ flush, write amplification, số file và p99 lookup. Một chiến lược tiết kiệm ghi có thể hấp dẫn, nhưng nếu đọc vẫn phải kiểm tra quá nhiều file thì chi phí chuyển sang read path.

### 24.2. Workload B: đọc nhiều, cập nhật chồng lắp

~~~text
20.000 mutation/giây
Nhiều UPDATE cùng tập 1 triệu khóa
200.000 GET/giây
SLO đọc p99 rất chặt
~~~

Một chiến lược kiểm soát chồng lắp file tốt có thể đáng ưu tiên dù phải viết lại dữ liệu nhiều hơn. Phải đo write stalls và disk bandwidth để không đẩy hệ vào quá tải nền.

### 24.3. Workload C: telemetry có TTL

~~~text
Hàng triệu sự kiện mới mỗi ngày
Phần lớn append theo thời gian
TTL 30 ngày tương đối đồng nhất
Đọc chủ yếu sự kiện gần đây
~~~

Time-window compaction có thể hợp lý trong những hệ hỗ trợ và khi late writes không làm hỏng giả định cửa sổ. Cần đồng thời thiết kế partition/time bucket, cách xử lý event trễ và chính sách repair.

### 24.4. Workload D: dữ liệu lịch sử được cập nhật thường xuyên

~~~text
Lưu hoạt động 2 năm
Khách liên tục sửa hoặc bổ sung bản ghi 3–6 tháng trước
Query range dài
TTL khác nhau giữa các loại bản ghi
~~~

Không nên chọn TWCS chỉ vì dữ liệu có timestamp. Việc cập nhật lại quá khứ và TTL hỗn hợp có thể làm cách dọn theo cửa sổ kém hiệu quả.

### 24.5. Đừng chỉ tối ưu trung bình

Một hệ có latency trung bình 3 ms nhưng cứ mỗi đợt compaction lớn p99 tăng lên vài trăm ms có thể không đáp ứng SLO. Benchmark cần bao gồm **thời gian compaction đang hoạt động**, không chỉ lúc hệ yên tĩnh.

## 25. Ví dụ tính tải ghi và dung lượng

Một dịch vụ ghi 1.000 sự kiện/giây, mỗi sự kiện trung bình 1 KB **dữ liệu logic** theo quy ước 1 KB = 1.000 byte.

Trong một ngày:

\[
1.000 \times 86.400 = 86.400.000\ \text{sự kiện}.
\]

Dung lượng logic:

\[
86.400.000 \times 1.000
= 86.400.000.000\ \text{byte}
= 86,4\ \text{GB/ngày}.
\]

Đây là dung lượng trước compression, replication, index, WAL và compaction.

Giả sử workload quan sát được có **write amplification ở tầng một node = 4** theo cách đo đã chọn, thì lượng bytes ghi vật lý tại node tương ứng có thể lớn hơn gấp nhiều lần byte logic gửi tới node. Không thể nhân 86,4 GB × 4 rồi coi đó là dung lượng cuối cùng trên disk: **WA đo tổng ghi theo thời gian**, không phải tổng dung lượng còn đang lưu.

Nếu dữ liệu được nhân bản RF=3, tổng lưu trữ qua cluster còn phụ thuộc phân phối replica, compression và topology. Cần tách:

- **Daily ingest logical bytes**.
- **Physical bytes written/day**.
- **Current live data bytes**.
- **Disk occupied including old versions, tombstones, snapshots**.
- **Peak free-space requirement during compaction**.

Một kế hoạch dung lượng chỉ nhìn ingest volume sẽ thiếu nhiều chi phí nền.

## 26. Bài tập thực hành

### Bài 1. Phân biệt flush và compaction

Giả sử:

~~~text
Memtable: K1=V3, K2=V1
SSTable S1: K1=V1
SSTable S2: K1=V2, K3=V1
~~~

Hãy:

1. Mô tả bước flush memtable.
2. Liệt kê các file có thể cùng chứa K1 sau flush.
3. Giải thích compaction nhằm giải quyết vấn đề gì.
4. Phân biệt điều kiện để bỏ các phiên bản K1 cũ so với tình huống có snapshot cần version cũ.

**Gợi ý:** Flush tạo một SSTable mới, không đồng nghĩa đã hợp nhất S1/S2.

### Bài 2. Bloom filter

Một SSTable không chứa khóa K nhưng Bloom filter trả “possibly present”.

1. Đây là false positive hay false negative?
2. Hệ nên làm gì tiếp?
3. Vì sao Bloom filter có thể tiết kiệm disk reads dù đôi khi trả sai theo chiều này?
4. Tăng số bit/khóa ảnh hưởng RAM và tỉ lệ false positive thế nào?

### Bài 3. K-way merge

Ba sorted runs:

~~~text
S1: A@1, C@1, E@1
S2: A@3, B@2, D@2
S3: B@4, C@5, F@2
~~~

Giả sử số sau @ là version và luôn chọn version lớn nhất, không có snapshot/tombstone.

Hãy tạo tập key–version sau merge theo thứ tự khóa. Sau đó giải thích vì sao quy tắc “version lớn nhất” trong bài tập là **giả định mô hình**, không phải quy tắc chung cho mọi storage engine.

### Bài 4. Chọn size-tiered hay leveled

Một hệ có:

- 90% read point lookup.
- Dữ liệu bị update thường xuyên.
- SLO p99 đọc rất chặt.
- SSD có dung lượng ghi giới hạn.

Hãy nêu lý do có thể cân nhắc LCS, đồng thời xác định chi phí compaction/write amplification cần đo trước khi chọn. Không được chỉ trả lời “LCS luôn tốt hơn”.

### Bài 5. Time-series và late writes

Một bảng nhận cảm biến theo thời gian, TTL 30 ngày, nhưng 20% sự kiện được backfill sau 45 ngày.

1. TWCS có những giả định nào đang bị vi phạm?
2. Nếu retention tính theo event time, những sự kiện đến sau 45 ngày phải được xử lý thế nào?
3. Bucket theo day ở schema khác compaction window ở tầng storage ra sao?
4. Cần đo những metric nào trước khi thay đổi chiến lược?

### Bài 6. Zombie data

Cụm Cassandra RF=3: A/B nhận tombstone cho K, C offline lâu và vẫn lưu K cũ. Compaction ở A/B dọn tombstone trước khi C repair.

1. Dữ liệu K có thể hồi sinh thế nào?
2. gc_grace_seconds và anti-entropy repair liên quan ra sao?
3. Vì sao hinted handoff không phải bảo đảm đủ trong mọi tình huống?
4. Tại sao không nên đặt gc_grace_seconds=0 để chữa đọc chậm do tombstone?

### Bài 7. Tính lưu lượng ingest

Hệ ghi 1.500 sự kiện/giây, mỗi sự kiện 2 KB theo quy ước 1 KB = 1.000 byte.

1. Có bao nhiêu sự kiện trong ngày?
2. Bao nhiêu GB logic/ngày?
3. Nếu physical write amplification quan sát là 5, số byte ghi vật lý theo định nghĩa đo tương ứng là bao nhiêu?
4. Tại sao kết quả ở câu 3 không được coi là dung lượng disk cuối cùng cần lưu?
5. Cần tính thêm những chi phí nào cho replication, snapshot và compaction?

### Bài 8. Điều tra compaction backlog

Dashboard cho thấy:

~~~text
SSTable count:         tăng liên tục
Pending compaction:    tăng
Disk usage:            92%
Write stall time:      tăng
Read p99:              tăng
Snapshot retention:    14 ngày
~~~

Hãy đưa ra kế hoạch điều tra: xác nhận workload, metric compaction, I/O/CPU, file snapshot còn giữ, free-space tạm, cấu hình hiện tại và mức rủi ro. Phân biệt hành động **giảm tải** với việc tự ý **xóa SSTable/WAL** trên disk.

### Bài 9. Durability sau crash

Một mutation đã được API ACK nhưng memtable chưa flush khi node mất điện.

1. Có thể khôi phục mutation bằng cơ chế nào?
2. Cần điều kiện gì ở WAL/commit log để mức ACK thực sự bền vững?
3. Replication giúp gì nếu node hỏng hẳn?
4. Vì sao không nên coi compaction là hoạt động quyết định mọi tính chất durability?

### Bài 10. Thiết kế thử nghiệm

Thiết kế một benchmark A/B cho hai chiến lược compaction trên dữ liệu có:

- 40% INSERT mới.
- 50% UPDATE lặp theo khóa.
- 10% DELETE.
- 70% point reads, 30% range reads.

Yêu cầu nêu cách giữ workload tương đương, thời gian warm-up, metric đọc/ghi/compaction, cách quan sát trong lúc nền chạy, tiêu chí dừng và lý do không kết luận từ một lần chạy ngắn.

## 27. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| SSTable là bảng có thể sửa trực tiếp như file CSV | SSTable thường bất biến; cập nhật được phản ánh bằng mutation mới |
| Một key chỉ có trong một SSTable | Nhiều file có thể chứa các phiên bản liên quan tới cùng key |
| Flush đồng nghĩa compaction | Flush chuyển memtable ra file; compaction hợp nhất file có sẵn |
| Ghi chưa flush thì chắc chắn mất sau crash | Còn tùy WAL/commit log, fsync và hợp đồng durability |
| WAL đã append nghĩa là fsync chắc chắn hoàn tất | Phụ thuộc cấu hình và cơ chế ACK |
| Compaction tạo đúng một SSTable | Có thể tạo nhiều file đầu ra |
| Compaction chỉ làm nhỏ dung lượng | Còn điều chỉnh layout, số runs và read amplification |
| Bloom filter xác nhận khóa chắc chắn tồn tại | Nó có thể false positive; chỉ trả “definitely not” hoặc “possibly” |
| Xóa dữ liệu là xóa bytes ngay lập tức | Có thể còn tombstone, version cũ và snapshot |
| Dọn tombstone nhanh hơn luôn tốt | Có thể gây data resurrection khi replica bỏ lỡ DELETE |
| gc_grace_seconds là TTL | Là khái niệm khác, phục vụ an toàn GC tombstone |
| TWCS luôn tốt với mọi dữ liệu có timestamp | Late updates và TTL không đồng nhất có thể làm mất lợi ích |
| LCS luôn nhanh hơn STCS | Đọc có thể tốt hơn nhưng chi phí ghi và backlog có thể cao hơn |
| WA = 4 nghĩa disk cần đúng 4 lần dung lượng live | WA là lượng bytes ghi qua thời gian, không phải occupied disk |
| Replication thay thế backup | Một lệnh xóa sai có thể được sao chép tới mọi replica |
| Nhiều SSTable luôn gây chậm như nhau | Cần xem level, overlap, cache, Bloom và query pattern |
| Có thể tự xóa file SSTable/WAL khi disk đầy | Rất nguy hiểm; phải dùng quy trình chính thức của engine |

## 28. Tổng kết

**SSTable và các cấu trúc bất biến** là nền tảng cho nhiều hệ lưu trữ NoSQL sử dụng LSM-tree. Thay vì sửa trực tiếp các file dữ liệu cũ sau mỗi mutation, hệ ghi dữ liệu mới vào memtable, bảo vệ bằng WAL/commit log theo chính sách durability, rồi flush thành những file có thứ tự trên đĩa.

Hệ đọc phải phối hợp memtable và các SSTable, dùng chỉ mục, metadata và Bloom filter để tránh đọc file không cần thiết, sau đó hòa giải những phiên bản còn hiệu lực. **Compaction** định kỳ hợp nhất các file, giảm sự chồng lắp, dọn version cũ/tombstone khi an toàn và duy trì layout phù hợp với workload.

Điểm đánh đổi cốt lõi là:

1. **Ghi nhanh nhờ tạo file mới** nhưng cần chi phí hợp nhất về sau.
2. **Giảm read amplification** thường phải cân bằng với write amplification và dung lượng tạm.
3. **Size-tiered, leveled và time-window** phục vụ những workload khác nhau; không có lựa chọn tối ưu chung.
4. **Tombstone và repair** bảo vệ quyết định xóa trong hệ có replica; compaction không được loại bằng chứng xóa quá sớm.
5. **Flush, compaction, durability, replication và backup** có vai trò riêng, cần thiết kế và giám sát cùng nhau.
6. **Hiệu quả thực tế phải được đo** qua số SSTable, backlog, disk bytes, p95/p99, stall, TTL, snapshot và đặc điểm cập nhật theo thời gian.

Câu hỏi cuối cùng không chỉ là “Compaction có làm dữ liệu gọn hơn không?” mà là: **“Trong workload thực, việc tạo các file bất biến làm đổi chi phí đọc, ghi, dung lượng, bảo vệ xóa và khả năng chịu lỗi ra sao — và khi nào có thể hợp nhất dữ liệu mà vẫn giữ nguyên ngữ nghĩa được người dùng quan sát?”**

# Bộ đệm ghi, memtable và dữ liệu đã lưu bền trên thiết bị

Khi ứng dụng ghi một tài liệu vào cơ sở dữ liệu NoSQL và nhận phản hồi “thành công”, câu hỏi quan trọng là: **dữ liệu đang ở đâu và điều gì xảy ra nếu máy chủ mất điện ngay sau đó?**

Nhiều hệ lưu trữ tối ưu tốc độ ghi bằng cách **đệm thao tác trong bộ nhớ**. Thay vì cập nhật ngay nhiều vị trí trên đĩa, chúng ghi một bản ghi tuần tự vào **write-ahead log (WAL)** hoặc **commit log**, cập nhật **memtable**, rồi chuyển dữ liệu thành các file lưu trữ lâu dài trong nền. Một số engine sử dụng cấu trúc **LSM-tree** (*Log-Structured Merge-tree*); những engine khác dùng B-tree, journal, checkpoint và cache theo cách khác.

Cần phân biệt ba điều:

1. **Ghi được nhìn thấy khi đọc** (*visibility*): truy vấn có trả về giá trị mới không?
2. **Ghi được xác nhận** (*acknowledgment*): database đã đáp ứng điều kiện trả lời client chưa?
3. **Ghi đã bền vững** (*durability*): sau loại sự cố được mô hình hóa, dữ liệu có thể được phục hồi không?

Ba điều này có liên quan nhưng **không phải một khái niệm**. Ví dụ, một giá trị có thể nằm trong memtable và được truy vấn nhìn thấy, nhưng nếu bản ghi log tương ứng chưa được đồng bộ xuống thiết bị lưu trữ ổn định, một sự cố mất điện có thể khiến giá trị đó biến mất.

Bài học giải thích đường ghi từ ứng dụng tới thiết bị, vai trò của write buffer, WAL, memtable, SSTable, flush, compaction và checkpoint; sau đó liên hệ tới Cassandra, RocksDB, Redis và MongoDB WiredTiger.

## 1. Vì sao database không ghi trực tiếp từng thay đổi vào file dữ liệu chính?

Giả sử một hệ thống nhận 30.000 sự kiện thiết bị mỗi giây. Nếu mỗi sự kiện phải cập nhật ngay một cấu trúc dữ liệu nằm rải rác trên đĩa, công việc có thể gồm:

- Tìm vị trí bản ghi hoặc trang cần sửa.
- Đọc/ghi các trang dữ liệu và trang chỉ mục.
- Ghi thông tin phục hồi để tránh hỏng dữ liệu nếu dừng giữa chừng.
- Đồng bộ các thay đổi theo yêu cầu về độ bền.
- Xử lý nhiều writer đồng thời.
- Quản lý phân bổ dung lượng, nén và phân mảnh.

Cập nhật ngẫu nhiên (*random write*) có thể tốn kém hơn ghi tuần tự, nhất là khi lưu trữ, filesystem và workload không thuận lợi. Vì vậy, nhiều hệ sử dụng mô hình:

**Ghi tuần tự vào log → cập nhật cấu trúc trong RAM → gom và ghi thành file có tổ chức trong nền.**

Ý tưởng này không bảo đảm mọi hệ NoSQL đều có memtable. Nó đặc biệt điển hình ở các engine dựa trên **LSM**, như Cassandra và RocksDB. Đối với MongoDB WiredTiger, ta cần nói về **cache, journal và checkpoint** theo kiến trúc riêng chứ không gọi mọi bộ đệm là memtable.

### Mục tiêu của write buffering

| Mục tiêu | Cách bộ đệm hỗ trợ | Đánh đổi |
| --- | --- | --- |
| Giảm ghi ngẫu nhiên | Gom nhiều thay đổi để ghi thành khối/file | Cần xử lý khi RAM đầy |
| Tăng thông lượng | Giảm overhead cho mỗi thao tác | Phải kiểm soát áp lực ghi |
| Giảm latency | Một số ghi có thể được xác nhận trước khi file dữ liệu chính được cập nhật | Durability phụ thuộc log và chính sách đồng bộ |
| Giảm truy cập đĩa khi đọc dữ liệu mới | Dữ liệu gần đây nằm trong RAM | Tốn RAM, cần cấu trúc chỉ mục |
| Hỗ trợ recovery | WAL ghi lại những thay đổi chưa có trong file bền | Log phải được bảo vệ và phát lại chính xác |

**Tốc độ cao không tự tạo độ bền.** Bộ đệm càng lớn mà không có bảo đảm log phù hợp có thể làm tăng lượng dữ liệu mất khi sự cố.

## 2. Bộ đệm ghi là gì?

**Write buffer** là tên rộng cho vùng nhớ hoặc cơ chế dùng để tập hợp công việc ghi trước khi chuyển sang tầng kế tiếp. Trong hệ thống dữ liệu, nó có thể xuất hiện ở nhiều lớp:

~~~text
Ứng dụng
    |
    | batch/queue phía client
    v
Driver và mạng
    |
    | request đã tới database
    v
Storage engine
    |                         |
    +--> WAL/commit log       +--> Memtable / cache / write buffer
    |                         |
    v                         v
Hệ điều hành: page cache, buffer I/O
    |
    v
Filesystem / block layer
    |
    v
SSD / HDD / thiết bị lưu trữ
    |
    v
Dữ liệu bền theo bảo đảm của thiết bị và hệ thống
~~~

Không nên gọi tất cả các lớp này là **memtable**.

- **Batch phía client** có thể chỉ là danh sách request chưa gửi.
- **Bộ đệm mạng** có thể chứa dữ liệu đã gửi nhưng chưa được server xác nhận.
- **Write buffer của storage engine** phục vụ việc quản lý trạng thái, sắp xếp hoặc tích lũy các thay đổi.
- **OS page cache** có thể chứa dữ liệu file đã được ghi bằng system call nhưng chưa được flush xuống thiết bị.
- **Cache trong SSD** có thể có cơ chế volatile/non-volatile riêng và phải tuân thủ lệnh flush.

Nếu chỉ biết “dữ liệu đã vào RAM”, ta **chưa biết** dữ liệu có thể sống sót sau process crash, OS crash hoặc mất điện hay không.

### Process crash, OS crash và mất thiết bị khác nhau

| Sự cố | Ví dụ | Dữ liệu còn có thể ở đâu? |
| --- | --- | --- |
| **Process crash** | Database process bị dừng, OS vẫn hoạt động | OS cache và những byte đã ghi có thể còn |
| **OS crash** | Kernel panic hoặc reboot bất thường | Nội dung RAM/OS cache chưa bền có thể mất |
| **Mất điện** | Máy chủ bị cắt nguồn | Cache volatile ở OS/thiết bị có thể mất |
| **Mất thiết bị** | SSD hỏng không thể đọc | Dữ liệu trên thiết bị đó có thể mất dù đã fsync |
| **Mất node/vùng** | Máy chủ hoặc datacenter không còn truy cập | Cần replication và chiến lược khôi phục rộng hơn |

**Durability phải luôn gắn với mô hình sự cố.** `fsync` thành công có ý nghĩa chống mất dữ liệu do một số kiểu crash khi nền tảng lưu trữ thực thi đúng hợp đồng, nhưng không thể bảo đảm dữ liệu tồn tại khi toàn bộ thiết bị bị phá hỏng.

## 3. Memtable là gì?

**Memtable** (*memory table*) là cấu trúc dữ liệu trong RAM lưu những bản cập nhật gần đây, thường theo khóa và hỗ trợ đọc/tìm kiếm hiệu quả trước khi các bản cập nhật được chuyển sang file lưu trữ.

Trong hệ LSM, memtable thường:

1. Nhận các thao tác ghi mới sau hoặc song song với bước ghi log theo quy trình engine.
2. Duy trì một cấu trúc tìm kiếm theo key, thường có thứ tự, với biểu diễn version/tombstone nếu cần.
3. Phục vụ truy vấn đọc dữ liệu mới mà chưa có trong SSTable.
4. Khi đạt ngưỡng hoặc theo chính sách, chuyển sang trạng thái **immutable**.
5. Được **flush** thành một hoặc nhiều file dữ liệu trên thiết bị.
6. Sau khi flush và metadata được xử lý an toàn, cho phép dọn phần WAL không còn cần cho recovery.

Sơ đồ đơn giản:

~~~text
                        GHI MỚI
                          |
                          v
                   WAL / COMMIT LOG
                          |
                          v
                  Mutable memtable
                          |
             Đạt ngưỡng / yêu cầu flush
                          |
                          v
                 Immutable memtable
                          |
                    Background flush
                          |
                          v
                    SSTable mới
                          |
                 Background compaction
                          |
                          v
                 SSTables đã hợp nhất
~~~

Memtable **không phải một bảng SQL nằm trong RAM**. Đây là cấu trúc nội bộ của storage engine. Tùy sản phẩm, memtable có thể được hiện thực bằng skip list, cây, hash structure hoặc giải pháp khác.

### Một memtable thường chứa những gì?

Giả sử một key–value store nhận:

~~~text
PUT user:01 -> "ACTIVE"
PUT user:02 -> "PENDING"
PUT user:01 -> "SUSPENDED"
DELETE user:02
~~~

Một dạng biểu diễn logic để hiểu memtable:

~~~text
user:01 -> SUSPENDED, sequence=3
user:02 -> TOMBSTONE, sequence=4
~~~

Dữ liệu thực tế có thể giữ nhiều version theo mục đích MVCC/snapshot, không nhất thiết chỉ giữ giá trị cuối. Dấu **tombstone** thể hiện việc xóa logic, để giá trị cũ trong những file chưa compaction **không bị hiển thị trở lại**.

Memtable là lớp **phục vụ read/write đang diễn ra**; WAL là lớp **phục hồi dữ liệu khi RAM mất**. Hai vai trò khác nhau dù thường đi cùng nhau.

## 4. WAL/commit log: viết trước để có thể phục hồi

**Write-Ahead Log (WAL)** là nhật ký ghi lại những thay đổi cần thiết **trước khi coi dữ liệu được áp dụng bền theo hợp đồng**. Trong nhiều LSM engine, một bản cập nhật được append vào WAL và đưa vào memtable; khi process hoặc máy chủ khởi động lại sau crash, log được phát lại để tái tạo những phần chưa được flush.

Hình dung một ghi:

~~~text
PUT key=order:17, value=PAID

1. Nhận request
2. Kiểm tra cú pháp/ràng buộc
3. Ghi record vào WAL
4. Cập nhật memtable
5. Đồng bộ log xuống thiết bị nếu chính sách yêu cầu
6. Xác nhận cho client khi đã đạt điều kiện
7. Trong nền: flush memtable thành SSTable
~~~

**Thứ tự thực tế giữa các bước và thời điểm acknowledgment phụ thuộc engine, cấu hình, batching và concurrency.** Sơ đồ chỉ mô tả những thành phần logic, không phải một giao thức cố định của mọi hệ NoSQL.

### 4.1. Ghi vào log chưa chắc đã bền

Có các mức khác nhau:

- **Append vào buffer của process:** dữ liệu còn nằm trong vùng nhớ của ứng dụng.
- **Gọi write và được OS nhận:** byte có thể mới chỉ vào **page cache**, chưa bền khi OS crash/mất điện.
- **Yêu cầu fsync/fdatasync (hoặc cơ chế tương đương) và nhận xác nhận:** nền tảng được yêu cầu đẩy nội dung thích hợp tới tầng lưu trữ bền theo hợp đồng.
- **Thiết bị xác nhận lưu bền:** còn phụ thuộc firmware, cache và phần cứng thực thi đúng lệnh flush.

Vì vậy, hai câu sau **không đồng nghĩa**:

> “WAL đã được ghi bằng một lệnh write.”

> “WAL đã được xác nhận bền dưới mô hình sự cố mất điện của cấu hình này.”

Khi đánh giá durability, phải đọc đúng **chế độ sync log** và thời điểm database trả acknowledgment.

### 4.2. Log thường lưu thêm metadata

Một entry khái niệm:

~~~json
{
  "sequenceNumber": 1042,
  "operation": "PUT",
  "key": "order:17",
  "value": "PAID",
  "checksum": "illustrative-checksum"
}
~~~

Đây là biểu diễn sư phạm, không phải wire format của RocksDB hay Cassandra.

Những hệ thực tế có thể dùng số thứ tự, checksum, độ dài record, marker của batch/transaction và metadata khác để:

- Phát hiện record bị cắt dở hoặc hỏng.
- Xác định ranh giới thao tác/nhóm thao tác.
- Phát lại theo thứ tự thích hợp.
- Tránh áp dụng trùng những cập nhật đã hiện diện trong file bền.
- Xác định log nào có thể giải phóng.

**Không phải log chỉ cần chứa câu SQL hoặc chuỗi key/value thô là đủ** cho recovery an toàn.

## 5. Đường ghi của một LSM-based store

Một mô hình đơn giản:

~~~mermaid
flowchart TD
    A[Client PUT] --> B[Validate / assign sequence]
    B --> C[Append WAL]
    C --> D[Update memtable]
    D --> E{Durability policy}
    E -->|Sync required| F[Wait for durable log sync]
    E -->|Async policy| G[May acknowledge earlier]
    F --> H[Acknowledge]
    G --> H
    D --> I[Memtable reaches flush threshold]
    I --> J[Freeze immutable memtable]
    J --> K[Flush to SSTable]
    K --> L[Publish file metadata safely]
    L --> M[Retire obsolete WAL segments]
    K --> N[Compaction later]
~~~

Các nhánh nhằm giải thích cơ chế, không biểu thị rằng mọi sản phẩm dùng cùng thuật toán, thứ tự lock hoặc khả năng acknowledgment.

### 5.1. Khi nào client được nhận “thành công”?

Không có một mốc chung cho mọi NoSQL. Có hệ trả lời khi:

- Ghi đã nằm trong memtable và log buffer theo chế độ async.
- WAL đã được đồng bộ theo chế độ sync.
- Một số replica hoặc quorum đã xác nhận theo consistency/write concern.
- Transaction đã commit theo điều kiện đã chọn.

**Memtable đã flush thành SSTable không phải điều kiện bắt buộc cho mỗi acknowledgment** ở mọi LSM engine. Nếu hệ luôn chờ flush mỗi lần ghi, nó sẽ mất phần lớn lợi ích gom ghi của memtable.

Đồng thời, **trả thành công trước khi log được fsync** có thể phù hợp một workload chấp nhận mất phần ghi rất mới, nhưng không phù hợp những nghiệp vụ đòi durable commit ngay.

### 5.2. Đọc dữ liệu mới như thế nào?

Một truy vấn `GET order:17` có thể kiểm tra:

1. Memtable đang ghi.
2. Các immutable memtable chưa flush xong.
3. SSTable ở những tầng lưu trữ, qua index/filter thích hợp.
4. Version/tombstone để chọn trạng thái hiện hành.

Database phải duy trì **ngữ nghĩa phiên bản và tính nhất quán** dù cùng một key xuất hiện ở RAM và nhiều SSTable.

Không nên suy rằng “dữ liệu chưa flush thì không đọc được”. Memtable chính là một nguồn dữ liệu để đọc trong nhiều LSM engine.

## 6. Flush: đưa memtable thành file bền

**Memtable flush** là quá trình chuyển dữ liệu trong một memtable, thường đã chuyển thành immutable, thành file trên thiết bị như **SSTable** (*Sorted String Table*).

SSTable thường là file được tạo theo thứ tự khóa và không sửa tại chỗ theo kiểu mỗi PUT cập nhật một phần tử. Nó có thể kèm index, filter, metadata và checksum để phục vụ truy vấn.

~~~text
Mutable memtable
  key a -> v3
  key b -> v1
  key c -> tombstone
        |
        | freeze
        v
Immutable memtable
        |
        | flush
        v
SSTable-001.sst  (sorted by key)
  a : v3
  b : v1
  c : tombstone
~~~

### 6.1. Flush không chỉ là gọi một hàm ghi file

Để được coi là **an toàn cho recovery**, hệ lưu trữ cần xử lý:

- File dữ liệu mới và nội dung của nó.
- Đồng bộ nội dung file theo chính sách durability.
- Metadata chỉ ra file nào thuộc tập dữ liệu hợp lệ.
- Thứ tự công bố metadata, rename/manifest và yêu cầu sync thư mục khi cần.
- Khả năng xử lý file chưa hoàn chỉnh hoặc file mồ côi sau crash.
- Quan hệ giữa file mới và các WAL segment còn cần thiết.

Vì vậy, việc hệ thống báo “đã ghi một SSTable” và việc “SSTable được gắn an toàn vào trạng thái database sau crash” là hai bước khái niệm khác nhau.

**Recovery không nên dựa vào một file chưa được công bố hợp lệ** chỉ vì file đó xuất hiện trong thư mục.

### 6.2. Vì sao cần immutable memtable?

Khi một memtable đạt ngưỡng:

~~~text
Memtable A (immutable) -> đang flush
Memtable B (mutable)   -> tiếp tục nhận ghi mới
~~~

Cách này cho phép hệ tiếp tục nhận ghi trong khi bộ nhớ cũ đang được đẩy xuống thiết bị. Tuy nhiên, nếu flush chậm hơn tốc độ ghi, số immutable memtable hoặc write buffer bị giữ lại có thể tăng, gây **write stall** hoặc áp lực bộ nhớ.

Không nên nghĩ RAM có thể tăng vô hạn để che sự chậm trễ của thiết bị.

## 7. Compaction: sắp xếp lại file, không phải “lưu bền lần đầu”

Qua thời gian, các lần flush tạo nhiều SSTable. Một key có thể có nhiều phiên bản:

~~~text
SSTable mới:
  user:01 -> SUSPENDED
  user:03 -> ACTIVE

SSTable cũ:
  user:01 -> ACTIVE
  user:02 -> PENDING
~~~

**Compaction** đọc những file thích hợp, hợp nhất theo chính sách của engine, loại hoặc giữ version/tombstone theo quy tắc và ghi file mới có tổ chức hơn.

~~~text
SSTable A ----+
              +--> Compaction --> SSTable C
SSTable B ----+
~~~

Compaction giúp:

- Giảm số file phải xem khi đọc.
- Hạn chế trùng lặp các version cũ khi được phép.
- Sắp dữ liệu thành những level/nhóm phù hợp.
- Xử lý tombstone và lịch sử theo điều kiện an toàn.
- Cân đối chi phí đọc, ghi và dung lượng.

**Compaction không phải bước cần chờ trước khi xác nhận mọi PUT.** Dữ liệu có thể đã durable trong WAL hoặc SSTable từ trước.

### 7.1. Write amplification và compaction

Một bản ghi logic có thể được ghi:

1. Vào WAL.
2. Vào SSTable khi flush.
3. Vào SSTable khác khi compaction.
4. Vào các replica nếu hệ phân tán.

Tổng byte ghi vật lý có thể **lớn hơn nhiều** dữ liệu mới của ứng dụng, gọi là **write amplification**. Quy mô phụ thuộc chiến lược compaction, số level, phân bố cập nhật, kích thước key/value và workload.

Đây là lý do **ghi tuần tự thường nhanh** nhưng hệ LSM vẫn có thể tiêu tốn đáng kể dung lượng đĩa, I/O và CPU do compaction nền.

## 8. Flush, fsync và checkpoint khác nhau thế nào?

| Từ khóa | Câu hỏi nó giải quyết | Không đồng nghĩa |
| --- | --- | --- |
| **Flush memtable** | Đưa dữ liệu trong RAM thành SSTable/file ở tầng lưu trữ | Không nhất thiết cùng thời điểm acknowledge mỗi ghi |
| **Flush buffer I/O** | Đẩy byte từ một lớp đệm sang lớp kế tiếp | Không mặc nhiên durable nếu còn cache volatile |
| **fsync/fdatasync** | Yêu cầu đồng bộ file xuống lưu trữ theo hợp đồng OS/storage | Không bảo vệ mất hoàn toàn thiết bị |
| **Checkpoint** | Đánh dấu một trạng thái nhất quán có thể phục hồi, giảm phạm vi log phải replay | Không phải lúc nào cũng là LSM memtable flush |
| **Compaction** | Hợp nhất/tái tổ chức SSTable, xử lý version/tombstone | Không phải ghi WAL lần đầu |
| **Snapshot** | Bản chụp logic/vật lý theo cơ chế sản phẩm | Không tự bảo đảm backup độc lập hoặc đồng bộ mọi hệ |
| **Replication** | Giữ dữ liệu ở nhiều node/bản sao | Không thay thế log sync nếu replica cũng có thể mất dữ liệu |

Đặc biệt, từ `flush` trong các API có thể mang **ngữ nghĩa khác nhau**. Một API flush của RocksDB và lệnh flush cache của một filesystem không nhất thiết đảm bảo cùng điều kiện.

## 9. Điều gì xảy ra khi có sự cố tại từng thời điểm?

Giả sử có một PUT:

~~~text
PUT k = "v2"
~~~

Với mô hình LSM có WAL, xét những điểm lỗi khái niệm:

| Mốc sự cố | Đã có gì? | Khả năng phục hồi dưới giả định phù hợp |
| --- | --- | --- |
| **Trước khi WAL được nhận** | Chưa có bản ghi log hợp lệ | Không có bằng chứng để phục hồi v2 |
| **Sau khi append vào OS cache nhưng chưa sync** | WAL có thể mới nằm trong RAM của OS | Process crash có thể giữ được, OS/power crash có thể mất |
| **Sau khi WAL đã sync và memtable cập nhật** | Log được xem là bền theo cấu hình | Có thể replay v2 sau crash dù chưa flush SSTable |
| **Đang flush memtable** | Có thể có SSTable dở dang hoặc chưa công bố | Recovery phải dùng WAL/metadata hợp lệ, không tin file dở |
| **Sau khi SSTable được công bố bền** | v2 có thể phục hồi từ file dữ liệu | WAL cũ có thể được retire theo quy tắc an toàn |
| **Trong compaction** | Có file mới và cũ ở trạng thái chuyển tiếp | Engine phải giữ trạng thái nhất quán qua crash |
| **Sau khi toàn bộ thiết bị hỏng** | File trên thiết bị mất | Cần bản sao/backup ngoài phạm vi thiết bị |

Bảng dựa trên giả định hệ đã xử lý log/metadata đúng và thiết bị tôn trọng hợp đồng đồng bộ. **Không có bảo đảm tuyệt đối** trước mọi lỗi phần cứng hoặc vận hành.

### 9.1. “Client nhận thành công” phải được gắn vào bảng

Nếu engine dùng chính sách **sync WAL trước acknowledgment**, mốc xác nhận được thiết kế tương ứng với điều kiện log đã bền. Nếu engine dùng **async WAL**, client có thể nhận thành công khi dữ liệu mới chỉ ở RAM/OS cache.

Trong vận hành, cần xác định:

- Chế độ sync mặc định.
- Những thao tác nào có thể override.
- Khi nào acknowledgment trả về.
- Những replica nào phải xác nhận.
- Có transaction hoặc group commit không.
- Mô hình failure mà tài liệu sản phẩm cam kết.

Cùng một engine nhưng cấu hình khác nhau có thể cho **hợp đồng durability khác nhau**.

## 10. Recovery: phát lại WAL sau khi khởi động

Một kịch bản:

~~~text
Disk:
  SSTable-001 có order:01 = PENDING
  WAL có PUT order:01 = PAID (đã bền)

RAM trước crash:
  memtable order:01 = PAID

Crash làm mất RAM
        |
        v
Restart:
  1. Đọc metadata và SSTable hợp lệ
  2. Phát hiện WAL còn cần replay
  3. Kiểm tra record/checksum/sequence
  4. Áp dụng thay đổi chưa phản ánh trong trạng thái bền
  5. Khôi phục order:01 = PAID
~~~

WAL phải được replay **theo quy tắc của engine**: xử lý record hoàn chỉnh, ranh giới batch, sequence, transaction và tombstone. Một bản ghi log bị cắt giữa chừng không được tùy tiện biến thành thao tác hợp lệ.

### 10.1. Vì sao có thể xóa WAL cũ?

Nếu một phần dữ liệu đã được flush an toàn thành SSTable và metadata đã được công bố bền, WAL chứa **chỉ các thao tác thuộc phần đó** có thể không còn cần cho recovery.

Nhưng nếu một WAL segment chứa bản ghi của **nhiều memtable/column family/table**, không thể xóa segment chỉ vì một memtable đã flush; phải xét mọi dữ liệu mà segment còn chịu trách nhiệm.

### 10.2. Recovery có thể mất thời gian

Nếu log cần replay rất dài, quá trình khởi động sau crash có thể mất nhiều thời gian. Đó là **Recovery Time Objective (RTO)** cần quan tâm, khác với **Recovery Point Objective (RPO)** về mức mất dữ liệu được chấp nhận.

- **RPO nhỏ:** có thể yêu cầu sync bền thường xuyên và replication phù hợp.
- **RTO nhỏ:** có thể cần checkpoint/flush đều đặn, log không quá dài và quy trình recovery nhanh.

Một hệ có thể phục hồi **không mất dữ liệu đã commit** nhưng vẫn mất nhiều thời gian để mở lại dịch vụ.

## 11. Thực hành tư duy: ba chế độ ghi vào một LSM engine

Đặt một workload ghi cùng key/value và so sánh ba chính sách dưới đây:

| Chính sách | WAL | Đồng bộ log trước xác nhận? | Điểm mạnh | Rủi ro |
| --- | --- | --- | --- | --- |
| **A: WAL + sync** | Có | Có, theo API/chính sách đã chọn | Hợp đồng durability mạnh hơn trước crash | Chi phí sync |
| **B: WAL + async** | Có | Không bắt buộc mỗi ghi | Throughput/latency có thể tốt hơn | Ghi gần nhất có thể mất khi OS/power crash |
| **C: Tắt WAL** | Không | Không có WAL cho ghi đó | Tránh chi phí log | Dữ liệu chưa flush có thể mất hoàn toàn sau crash |

**Cảnh báo:** Chế độ C chỉ phù hợp cho dữ liệu có thể xây lại, bulk import được thiết kế chống lỗi hoặc tình huống không cần bảo vệ mỗi cập nhật. Không dùng nó cho đơn hàng/ledger chỉ để đạt benchmark đẹp.

Chế độ A không thay thế backup và replication; nó chủ yếu bảo vệ dữ liệu trên **thiết bị hiện hành** trước những kiểu crash thuộc phạm vi hệ.

## 12. Ví dụ RocksDB với Java: WriteOptions và WAL

RocksDB là thư viện storage engine key–value dựa trên LSM, thường được nhúng trong một ứng dụng. Đoạn Java dưới đây minh họa **ghi với WAL được bật và yêu cầu sync**.

Cần có dependency `org.rocksdb:rocksdbjni` tương thích với runtime và hệ điều hành. Ví dụ không triển khai ứng dụng server, replication hoặc transaction phân tán.

~~~java
import org.rocksdb.Options;
import org.rocksdb.RocksDB;
import org.rocksdb.RocksDBException;
import org.rocksdb.WriteOptions;

import java.nio.charset.StandardCharsets;

public class RocksDbDurabilityExample {
    static {
        RocksDB.loadLibrary();
    }

    private static byte[] bytes(String value) {
        return value.getBytes(StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws RocksDBException {
        String path = "./rocksdb-durability-lab";

        try (
            Options options = new Options().setCreateIfMissing(true);
            WriteOptions writeOptions = new WriteOptions()
                .setDisableWAL(false)
                .setSync(true);
            RocksDB db = RocksDB.open(options, path)
        ) {
            if (args.length > 0 && args[0].equals("write")) {
                db.put(
                    writeOptions,
                    bytes("order:01"),
                    bytes("PAID")
                );
                System.out.println("Write returned successfully.");
            } else {
                byte[] value = db.get(bytes("order:01"));
                System.out.println(
                    value == null
                        ? "Not found"
                        : new String(value, StandardCharsets.UTF_8)
                );
            }
        }
    }
}
~~~

Chạy chương trình với đối số `write` để tạo bản ghi, rồi mở lại không có đối số để đọc từ cùng thư mục. Ví dụ giúp thấy **giá trị tồn tại sau khi đóng/mở database bình thường**, nhưng **không chứng minh được hành vi khi mất điện**, vì đóng database bình thường có thể tự flush và dọn tài nguyên.

### 12.1. Ý nghĩa hai tùy chọn quan trọng

~~~java
new WriteOptions()
    .setDisableWAL(false)
    .setSync(true);
~~~

- `setDisableWAL(false)`: không tắt WAL cho các ghi sử dụng `WriteOptions` này.
- `setSync(true)`: yêu cầu đường ghi đồng bộ log theo ngữ nghĩa RocksDB; phù hợp thí nghiệm cần xác nhận durability mạnh hơn.

Nếu thay `setSync(false)`, một ghi được xác nhận có thể chưa được đồng bộ log bền trước power/OS crash. Nếu bật `setDisableWAL(true)`, dữ liệu ghi vào memtable có thể mất trước khi được flush nếu gặp sự cố.

Thực nghiệm để kiểm chứng durability khi crash phải chạy trong **môi trường disposable có quyền kiểm soát**, có thể mô phỏng dừng đột ngột hoặc mất điện ở lớp phù hợp. **Không cố tình kill database hoặc cắt nguồn môi trường có dữ liệu thật.**

### 12.2. WriteBatch của RocksDB không tự thay độ bền

RocksDB có `WriteBatch` để nhóm các thay đổi và áp dụng chúng theo ngữ nghĩa batch của engine. Nhưng **durability vẫn phụ thuộc WAL và WriteOptions**. Khái niệm nhóm nhiều thay đổi không tự trả lời câu hỏi “đã fsync chưa?”.

Khi nhiều record cần cùng thay đổi ở tầng một RocksDB instance, cần đọc đúng bảo đảm atomic batch của phiên bản RocksDB. Nếu ứng dụng còn ghi hệ ngoài, atomic batch nội bộ không mở rộng tới những hệ đó.

## 13. Cassandra: commit log, memtable và SSTable

Cassandra là một ví dụ tiêu biểu của thiết kế **LSM-oriented** trong hệ dữ liệu phân tán.

### 13.1. Đường ghi khái niệm

~~~text
Client gửi mutation
          |
          v
Coordinator gửi tới các replica theo topology
          |
          v
Tại từng replica:
    +------------------+
    | Commit log       | <- nhật ký phục hồi
    +------------------+
             |
             v
    +------------------+
    | Memtable         | <- trạng thái trong RAM
    +------------------+
             |
         flush nền
             v
    +------------------+
    | SSTables         | <- file lưu bền
    +------------------+
             |
         compaction nền
             v
    +------------------+
    | SSTables hợp nhất|
    +------------------+
~~~

Commit log giúp phục hồi các mutation chưa xuất hiện trong SSTable an toàn. Memtable phục vụ việc tổ chức dữ liệu mới; SSTable là file dữ liệu được ghi sau flush. Hệ đọc có thể phải phối hợp memtable và nhiều SSTable, áp dụng timestamp/tombstone và các quy tắc consistency tương ứng.

### 13.2. Commit log synchronization

Cassandra có cấu hình về đồng bộ commit log, thường có các cách tiếp cận như **periodic** và **batch** tùy phiên bản:

- **Periodic:** tối ưu throughput bằng các lần sync theo chu kỳ; có cửa sổ rủi ro mất ghi mới chưa bền trên thiết bị nếu gặp crash thuộc phạm vi tương ứng.
- **Batch:** điều phối sync với nhóm ghi theo chính sách được hỗ trợ; thường ảnh hưởng latency và độ bền.

Không được đánh đồng `CONSISTENCY QUORUM` với “mọi replica đã fsync từng mutation”. Consistency level chủ yếu xác định **mức xác nhận từ các replica theo giao thức**, còn cách mỗi replica đồng bộ commit log là một lớp cấu hình khác.

### 13.3. Flush không phải bước duy nhất quyết định acknowledged write

Một replica có thể xác nhận ghi theo cấu hình trước khi memtable được flush ra SSTable. Nếu commit log đủ bền theo chính sách, sự cố mất RAM vẫn có thể được phục hồi bằng log.

Ngược lại, nếu log chưa bền và toàn bộ replica liên quan cùng mất điện, sự tồn tại của giá trị trong memtable **không bảo đảm** dữ liệu còn sau khởi động.

### 13.4. Commit log segment recycling

Khi memtable được flush an toàn, những commit log segment không còn chứa mutation cần recovery có thể được giải phóng/tái sử dụng. Với segment chứa mutation của nhiều bảng/memtable, thời điểm thu hồi còn phụ thuộc các phần dữ liệu liên quan.

Đây là một lý do việc flush và quản lý commit log liên quan chặt chẽ, dù **không phải cùng một thao tác**.

## 14. Redis: bộ nhớ, AOF và RDB không phải memtable LSM

Redis thường lưu cấu trúc dữ liệu chính trong RAM. Nếu cần persistence, các cơ chế quen thuộc là:

- **RDB snapshot:** lưu ảnh chụp dữ liệu tại một thời điểm theo chính sách.
- **AOF (Append Only File):** ghi lại các thao tác thay đổi để có thể tái tạo dữ liệu, với chính sách đồng bộ riêng.
- Một số cấu hình có thể kết hợp các cơ chế trên.

Redis không nên được mô tả đơn giản là “memtable rồi flush thành SSTable”, bởi đó **không phải write path LSM tương ứng**.

### 14.1. Ba cách hiểu về persistence

| Cấu hình/ý tưởng | Điểm cần hiểu |
| --- | --- |
| Redis chỉ lưu RAM, không persistence | Dữ liệu có thể mất khi restart/crash |
| RDB snapshot định kỳ | Các thay đổi sau snapshot cuối có thể chưa được lưu |
| AOF với chế độ fsync | Mức mất dữ liệu có thể xảy ra phụ thuộc chính sách đồng bộ và sự cố |

Một chính sách AOF `everysec` thường đánh đổi throughput để giảm chi phí fsync so với đồng bộ từng thao tác; vẫn có **cửa sổ mất dữ liệu gần đây** khi sự cố. Không nên diễn giải “everysec” thành một bảo đảm tuyệt đối rằng trong mọi điều kiện chỉ mất đúng một giây.

### 14.2. Một giá trị được đọc thấy chưa chắc đã có trong snapshot

~~~text
SET order:01 PAID
  -> RAM Redis cập nhật
  -> GET order:01 trả PAID
  -> RDB snapshot chưa chạy
  -> server crash
~~~

Nếu chỉ dùng snapshot cũ, giá trị mới có thể mất sau khởi động. Điều này minh họa rõ **visibility khác durability**.

Với ứng dụng dùng Redis như cache có thể tái xây từ database nguồn, mất một phần cache không nhất thiết làm sai dữ liệu nghiệp vụ. Với Redis làm nguồn chân lý, phải thiết kế persistence/replication và RPO/RTO theo yêu cầu.

## 15. MongoDB WiredTiger: cache, journal và checkpoint

MongoDB WiredTiger là ví dụ quan trọng cho thấy **không phải mọi NoSQL sử dụng memtable của LSM**.

WiredTiger thường được mô tả bằng cấu trúc lưu trữ **B-tree**, cache, journaling và checkpoint. Một cập nhật có thể thay đổi trạng thái trong bộ nhớ của storage engine, đồng thời được hỗ trợ bởi cơ chế journal/log theo cấu hình; checkpoint đưa một trạng thái nhất quán của file dữ liệu về điểm có thể phục hồi.

### 15.1. Khác biệt kiến trúc

| LSM-oriented storage | WiredTiger dạng B-tree |
| --- | --- |
| Memtable tổ chức các ghi mới | Cache quản lý dữ liệu/trang đang hoạt động |
| Flush memtable thành SSTable | Checkpoint và cơ chế cập nhật trang dữ liệu theo thiết kế B-tree |
| Compaction nhiều SSTable là công việc nền đặc trưng | Không dùng chính chu trình LSM memtable → SSTable làm mô hình mặc định |
| WAL/commit log phục hồi thay đổi mới | Journal/checkpoint phục vụ durability và recovery theo cấu hình |

Không nên khẳng định tất cả sản phẩm gọi thứ gì đó là “bộ đệm ghi” thì chúng có cùng định dạng file và quy trình crash recovery.

### 15.2. Write concern và journaling

Trong MongoDB, write concern có thể biểu diễn mức xác nhận mong muốn, ví dụ:

- `w: 1`: xác nhận từ primary theo quy tắc vận hành.
- `w: "majority"`: xác nhận theo điều kiện đa số replica của replica set.
- Thuộc tính journal như `j` có thể ảnh hưởng yêu cầu ghi journal bền theo cấu hình/version.

**Không suy rằng `w:1` và `w:"majority"` tự mô tả hoàn chỉnh trạng thái fsync tại mọi replica.** Cần xem cấu hình MongoDB, journaling, defaults, replica set và điều kiện write concern của hệ cụ thể.

Với một giao dịch nhạy cảm, “đã ghi vào cache” không phải điều kiện đầy đủ để khẳng định durable commit theo một SLO đã thỏa thuận.

## 16. Replication không thay thế độ bền của từng replica

Giả sử hệ có ba replica:

~~~text
Client write X
      |
      +--> Replica A: X trong RAM, log chưa sync
      +--> Replica B: X trong RAM, log chưa sync
      +--> Replica C: chưa nhận X
~~~

Nếu client nhận ACK từ A và B, tùy giao thức có thể đáp ứng một mức consistency/acknowledgment nào đó. Nhưng nếu A và B cùng mất nguồn trước khi log bền, **có thể xảy ra mất ghi** dù đã có hai xác nhận.

Ngược lại:

~~~text
Replica A: X trong WAL đã fsync
Replica B: X trong WAL đã fsync
Replica C: chưa nhận X
~~~

Khả năng chịu lỗi mạnh hơn đối với một số sự cố, nhưng vẫn cần xét giao thức leader/consensus, quorum, failover, split-brain, rollback và tình huống mất đồng thời thiết bị.

**Replication, consistency, journal sync và backup là các lớp bảo vệ bổ trợ nhau.**

### 16.1. Vì sao write concern không thể được giải thích bằng một câu chung?

Các hệ NoSQL có những cơ chế khác nhau:

- Cassandra dùng consistency level với replication và commit log.
- MongoDB có write concern, journal và replica set.
- RocksDB bản thân là thư viện nhúng; nhiều triển khai chỉ là một instance local.
- Redis có replication và persistence với bảo đảm riêng.

Do đó, câu “quorum là đã lưu bền trên đĩa” **không đúng như một quy tắc phổ quát**. Cần đọc giao thức và cấu hình đồng bộ của sản phẩm thực tế.

## 17. Bộ đệm đầy: backpressure và write stall

Memtable và immutable memtable tiêu thụ RAM. Giả sử:

- Ứng dụng sinh dữ liệu nhanh hơn thiết bị có thể flush.
- Compaction cạnh tranh I/O với flush.
- Có nhiều memtable immutable đang chờ ghi.

Khi đó hệ có thể:

1. Giảm tốc độ nhận ghi.
2. Tăng latency của các request ghi.
3. Chặn ghi tạm thời khi vượt giới hạn.
4. Phát cảnh báo write stall/backpressure.
5. Trong trường hợp xấu, hết tài nguyên hoặc không thể duy trì SLO.

~~~text
Write rate từ client
        |
        v
    Memtable
        |      Flush rate < Write rate
        v
Immutable memtables chờ flush
        |
        v
Hết ngân sách bộ đệm
        |
        v
Write stall / throttling
~~~

**Tăng RAM có thể dời điểm nghẽn nhưng không giải quyết được mất cân bằng bền vững giữa tốc độ ghi vào và tốc độ đẩy ra.**

### 17.1. Một phép tính sức chứa đơn giản

Giả sử tốc độ ghi mới sau overhead là khoảng **10 MiB/giây** và bộ đệm có thể giữ 300 MiB trước khi cần xử lý.

Nếu không có flush, thời gian lấp đầy xấp xỉ:

\[
T \approx \frac{300\ \mathrm{MiB}}{10\ \mathrm{MiB/s}} = 30\ \mathrm{s}
\]

Đây chỉ là tính toán năng lực sơ bộ; thực tế có overhead cấu trúc, nhiều memtable, nén, overwrite cùng key, số lượng index và tốc độ flush diễn ra song song.

Muốn vận hành ổn định, phải quan sát **tốc độ ghi thực tế và tốc độ drain** của pipeline trong thời gian dài, không chỉ dung lượng buffer.

## 18. Group commit và đánh đổi latency–throughput

`fsync` cho từng thao tác có thể tốn overhead đáng kể. Nhiều storage engine có cách **nhóm nhiều ghi để cùng chịu chi phí đồng bộ log**, thường được gọi là *group commit* hoặc cơ chế tương đương.

~~~text
PUT A ----+
PUT B ----+----> WAL append / group sync ----> ACK theo chính sách
PUT C ----+
~~~

Lợi ích:

- Giảm số lần yêu cầu đồng bộ riêng lẻ.
- Duy trì độ bền mà không phải thực hiện một fsync cho mỗi logical write theo cách ngây thơ.
- Tăng throughput khi có nhiều client ghi đồng thời.

Đổi lại:

- Có thể cần đợi một khoảng để hình thành nhóm.
- Các request chịu latency theo thời điểm batch được commit.
- Thiết kế phải giữ chính xác ranh giới và thứ tự commit.

**Group commit không đồng nghĩa “bỏ đồng bộ để nhanh hơn”.** Đây là cách chia sẻ chi phí đồng bộ cho nhiều thao tác, nếu engine thực hiện đúng các bảo đảm của nó.

## 19. Read amplification, write amplification và space amplification

Một engine LSM đạt ghi nhanh bằng cách phân lớp dữ liệu. Đánh đổi có thể được mô tả qua ba loại amplification:

| Loại | Ý nghĩa | Nguồn gây tăng |
| --- | --- | --- |
| **Write amplification** | Byte ghi vật lý lớn hơn byte cập nhật logic | WAL, flush, compaction, replication |
| **Read amplification** | Một lần đọc phải xem nhiều vị trí/file | Nhiều SSTable, version, tombstone |
| **Space amplification** | Dung lượng lưu trữ lớn hơn dữ liệu live | Version cũ, tombstone, file chờ compaction |

Không có một thuật toán compaction tối ưu tuyệt đối cho mọi workload.

- **Leveled compaction:** thường hướng tới kiểm soát read/space amplification, nhưng có thể phát sinh nhiều byte ghi.
- **Size-tiered compaction:** có thể giảm chi phí ghi trong một số workload, đổi lại nhiều file/trùng lặp trong những thời điểm nhất định.
- **Time-window compaction:** có thể hữu ích với dữ liệu theo thời gian và chính sách TTL, nếu được cấu hình đúng.

Những mô tả này là khuynh hướng; chi phí thực tế phụ thuộc engine, version, key distribution, delete/TTL và thiết lập hệ thống.

### 19.1. Tombstone và xóa

Khi `DELETE key=a` được ghi, engine LSM không nhất thiết xóa ngay mọi bản sao cũ của `a` trong SSTable. Nó có thể ghi **tombstone**, để các lần đọc hiểu rằng key hiện đã bị xóa.

Tombstone chỉ có thể được loại bỏ hoàn toàn khi **đủ điều kiện an toàn** theo chính sách lưu trữ, replica, thời hạn và version. Xóa tombstone quá sớm có thể làm giá trị cũ ở một SSTable/replica khác **tái xuất hiện**.

Điều này giải thích vì sao dữ liệu đã xóa logic không nhất thiết làm dung lượng đĩa giảm ngay.

## 20. Những thước đo cần quan sát trong production

Khi điều tra ghi chậm hoặc rủi ro durability, không nên chỉ xem CPU hoặc số request/giây.

| Chỉ số/nhóm chỉ số | Câu hỏi |
| --- | --- |
| Write latency p50/p95/p99 | Thời gian từ yêu cầu tới acknowledgment thay đổi ra sao? |
| WAL append/sync latency | Có đang chậm ở đồng bộ log không? |
| Bytes/log records pending | Có nhiều dữ liệu mới chưa được bảo vệ theo chính sách? |
| Memtable size/count | RAM cho dữ liệu mới đang tăng đến mức nào? |
| Immutable memtables waiting | Flush có theo kịp ghi không? |
| Flush duration/bytes | Thiết bị có đáp ứng được tốc độ đưa dữ liệu ra không? |
| Compaction backlog | Có file chờ hợp nhất quá nhiều không? |
| Write stall count/duration | Client có bị chặn do áp lực lưu trữ không? |
| SSTable count/levels | Chi phí đọc và compaction có đang tăng? |
| Disk space, IOPS, bandwidth | Có đủ nguồn lực cho flush và compaction? |
| Replication lag/ack timing | Các replica bắt kịp và xác nhận theo chính sách không? |
| Recovery time và log replay | Sau crash dịch vụ có thể mở lại đủ nhanh không? |

Tên metric cụ thể phụ thuộc RocksDB/Cassandra/Redis/MongoDB và hệ giám sát. Không nên xem một con số tổng hợp rồi suy ra nguyên nhân; ví dụ write latency tăng có thể do fsync chậm, compaction đẩy nghẽn I/O, network, hot partition hoặc replica lag.

### 20.1. Phân biệt số liệu thiết kế và số liệu đo

Một bảng thực nghiệm nên ghi:

| Phương án | Policy log | p95 latency | Throughput | Số ghi mất sau crash test | Recovery time |
| --- | --- | --- | --- | --- | --- |
| A | WAL + sync | **Đo thực tế** | **Đo thực tế** | **Quan sát** | **Đo** |
| B | WAL + async | **Đo thực tế** | **Đo thực tế** | **Quan sát** | **Đo** |
| C | WAL disabled | **Đo thực tế** | **Đo thực tế** | **Quan sát** | **Đo** |

Không điền số “ước lượng” vào các ô rồi trình bày như kết quả benchmark. Tính đúng và kết quả crash test phải có điều kiện rõ ràng.

## 21. Thiết kế thí nghiệm durability có kiểm soát

Một thí nghiệm đáng tin không phải chỉ là:

~~~text
Ghi dữ liệu
Đóng database bình thường
Mở lại
Đọc thấy dữ liệu
=> Kết luận dữ liệu luôn durable
~~~

**Đóng bình thường có thể flush dữ liệu**, nên kiểm tra đó không mô phỏng process crash hoặc mất điện.

Một quy trình tốt hơn trong **môi trường thử nghiệm riêng**:

1. Dựng database thử trên một filesystem và thiết bị được biết cấu hình.
2. Gắn sequence/ID tăng cho mỗi thao tác ghi.
3. Ghi nhận những ID đã nhận acknowledgment.
4. Chọn rõ chính sách WAL sync và replication.
5. Tạo tải đại diện trong một khoảng thời gian.
6. Tại một mốc kiểm soát, mô phỏng loại sự cố đã chọn **trên môi trường disposable**.
7. Khởi động lại bằng recovery bình thường của sản phẩm.
8. So sánh tập ID được acknowledge với dữ liệu còn đọc được.
9. Đo mất dữ liệu, time-to-recovery và lỗi checksum/file.
10. Lặp lại qua nhiều mốc và tải để quan sát phân bố.

Không dùng thử nghiệm phá hủy trên cluster production. Không thực hiện thao tác cắt nguồn thật khi chưa có môi trường và quy trình an toàn.

### 21.1. Phân biệt process kill với mất điện

Một thử nghiệm dừng process đột ngột **không nhất thiết xóa OS page cache**. Vì thế nó có thể không phát hiện những rủi ro khi log mới nằm trong page cache và OS vẫn còn.

Muốn kết luận về mất điện, cần mô phỏng đúng tầng lỗi hoặc thiết bị thử được thiết kế cho mục đích đó. Kết quả thử trên máy ảo cũng phụ thuộc hypervisor và cơ chế lưu trữ phía dưới.

**Mỗi kết luận durability phải nói rõ loại crash đã thử.**

### 21.2. Đúng dữ liệu sau recovery không chỉ là “có key”

Ngoài việc kiểm tra số lượng key, cần xem:

- Giá trị của từng key có đúng không?
- Những update đã được acknowledge có bị lùi phiên bản?
- Có thao tác insert bị lặp ngoài nghiệp vụ không?
- Tombstone có còn ngăn giá trị cũ xuất hiện?
- Có record bị cắt dở hoặc checksum lỗi không?
- Trạng thái transaction/batch có nhất quán với cam kết không?
- Dữ liệu có thể đọc sau khi replica failover không?

Một hệ trả lại đủ số key nhưng **sai giá trị hoặc thứ tự sự kiện** vẫn có thể vi phạm yêu cầu durability/consistency của ứng dụng.

## 22. Chọn cấu hình theo loại dữ liệu

Không phải dữ liệu nào cũng yêu cầu cùng RPO, RTO hoặc độ trễ ghi.

| Workload | Có thể ưu tiên | Cần tránh |
| --- | --- | --- |
| Cache có thể tái tạo | Throughput, RAM, chấp nhận mất cache | Tưởng cache là nguồn chân lý |
| Event log quan trọng | WAL sync/replication theo cam kết, idempotency | ACK sớm mà không công bố rủi ro |
| Đơn hàng, thanh toán | Durability, tính nguyên tử nghiệp vụ, audit | Tắt WAL để benchmark nhanh |
| Telemetry tần suất cao | Batch, tối ưu write path, chính sách mất dữ liệu rõ | Dùng một cấu hình cho mọi mức quan trọng |
| Dữ liệu phân tích tái tính được | Ingest throughput, checkpoint/replay | Không có nguồn để phát lại khi batch mất |
| Session ngắn hạn | TTL, cache, chính sách chấp nhận mất session | Không phân biệt session với giao dịch bền |
| Metadata cấu hình | Bảo toàn phiên bản/khả năng khôi phục | Tùy tiện ghi async không có backup |

Cấu hình cần xuất phát từ:

- **RPO:** có chấp nhận mất các ghi đã được hệ xác nhận không? Bao nhiêu?
- **RTO:** thời gian khôi phục tối đa là bao lâu?
- **Latency SLO:** client cần nhận phản hồi trong bao lâu?
- **Throughput:** bao nhiêu byte/ghi mỗi giây, đỉnh tải ra sao?
- **Fault model:** process crash, power loss, disk failure hay node failure?
- **Chi phí:** SSD, replication, backup, CPU cho compaction và RAM.
- **Kiểm chứng:** có crash test và giám sát phù hợp không?

Không nên chỉnh `sync=false` hay disable WAL cho dữ liệu quan trọng nếu chưa đánh giá được **giới hạn mất dữ liệu**.

## 23. Các hiểu lầm phổ biến

### 23.1. “Đã vào memtable nghĩa là đã nằm trên đĩa”

Sai. Memtable là **bộ nhớ**. WAL hoặc file dữ liệu bền mới là cơ sở phục hồi, theo chính sách từng engine.

### 23.2. “Có WAL là chắc chắn không mất dữ liệu”

Không đủ. WAL có thể chỉ mới vào OS cache nếu chưa được sync; thiết bị có thể hỏng; ghi có thể chưa đạt điều kiện xác nhận. Cần hiểu write concern/fsync và fault model.

### 23.3. “Đã ACK nghĩa là SSTable đã được flush”

Không nhất thiết. Nhiều LSM engine ACK trên cơ sở log và memtable mà chưa flush SSTable. Đó là một phần quan trọng của tối ưu write path.

### 23.4. “Flush memtable chính là compaction”

Khác nhau. Flush tạo file từ memtable; compaction tái tổ chức/hợp nhất file đã có.

### 23.5. “Mọi NoSQL đều có memtable”

Không đúng. Cassandra/RocksDB điển hình cho LSM; Redis và WiredTiger có đường lưu trữ khác.

### 23.6. “Quorum đã ACK nghĩa là mọi replica đều fsync”

Không thể suy ra chỉ từ chữ quorum. Mỗi hệ có quy tắc ghi log, sync, consistency và acknowledgment riêng.

### 23.7. “Process restart thành công là đã chứng minh power-loss durability”

Chưa. Đóng bình thường có thể flush; process crash vẫn để OS cache tồn tại. Cần test đúng kiểu lỗi.

### 23.8. “Tăng write buffer sẽ giải quyết mọi write stall”

Không, nếu tốc độ ghi vào vượt tốc độ flush lâu dài. Buffer lớn chỉ che nghẽn trong một khoảng thời gian.

### 23.9. “Xóa một key là SSTable cũ cũng mất key ngay”

Nhiều LSM engine ghi tombstone và chờ compaction theo quy tắc an toàn. Dữ liệu cũ có thể còn trong file vật lý một thời gian.

### 23.10. “Fsync bảo vệ khỏi mọi sự cố”

Fsync không thay thế replication, backup, bảo vệ thiết bị, checksum và kiểm thử recovery. Nó còn phụ thuộc storage stack thực thi đúng hợp đồng.

### 23.11. “Chỉ tối ưu ghi, không cần xem ảnh hưởng tới đọc”

Compaction và nhiều SSTable có thể tăng chi phí đọc, I/O và dung lượng. Cần đo read/write/space amplification.

### 23.12. “Độ bền và tính nhất quán là một”

Một ghi có thể durable nhưng chưa được replica khác nhìn thấy theo consistency model; hoặc đọc thấy giá trị trong RAM nhưng giá trị chưa durable. Phải kiểm tra hai trục riêng.

## 24. Bài tập thực hành

### Bài 1: memtable hay WAL?

Một bản ghi mới đã xuất hiện trong memtable nhưng chưa được flush thành SSTable. Thành phần nào thường giúp LSM engine khôi phục ghi đó sau crash?

**Gợi ý:** WAL/commit log đã được ghi và đồng bộ đủ bền theo chính sách của hệ. Memtable bị mất khi RAM mất.

### Bài 2: đọc trước flush

Một key mới chưa có trong SSTable nhưng truy vấn trả đúng giá trị. Điều đó có bất thường không?

**Gợi ý:** Không. Đường đọc của nhiều LSM engine kết hợp memtable với các SSTable.

### Bài 3: ACK và durability

Hai hệ đều trả ACK sau PUT. Hệ A sync WAL trước ACK, hệ B không yêu cầu sync mỗi ghi. Có được khẳng định hai ACK có cùng bảo đảm durability không?

**Gợi ý:** Không; cần xét chính sách đồng bộ và fault model.

### Bài 4: flush và compaction

Hệ có 10 immutable memtable đang chờ flush và 50 SSTable chờ compaction. Hai hàng đợi này đang đại diện cho những công việc gì?

**Gợi ý:** Flush chuyển dữ liệu RAM sang SSTable; compaction hợp nhất/tổ chức lại SSTable đã có.

### Bài 5: viết lại luồng crash recovery

Giả sử PUT `user:01 = ACTIVE` đã flush trong SSTable. Sau đó PUT `user:01 = SUSPENDED` chỉ nằm trong memtable nhưng WAL đã sync. OS crash. Trạng thái sau recovery nên là gì?

**Gợi ý:** SUSPENDED nếu WAL recovery thành công theo bảo đảm hệ, không lùi về ACTIVE.

### Bài 6: chọn chế độ RocksDB

Dữ liệu có thể tái nhập từ nguồn đáng tin cậy và cần thông lượng lớn. Vì sao một ứng dụng có thể cân nhắc tắt WAL, và điều kiện tiên quyết là gì?

**Gợi ý:** Giảm chi phí log, nhưng phải có khả năng **replay/rebuild** mọi ghi chưa flush và chấp nhận rủi ro mất dữ liệu khi crash.

### Bài 7: bộ đệm bị đầy

Write rate 20 MiB/s, flush rate trung bình chỉ 12 MiB/s trong thời gian dài. Tăng RAM có giải quyết được tận gốc không?

**Gợi ý:** Không. Chênh lệch 8 MiB/s liên tục làm backlog tăng; cần điều tiết ingest hoặc tăng năng lực flush/compaction.

### Bài 8: Redis khác LSM ở đâu?

Redis dùng AOF và RDB. Vì sao không nên mô tả Redis như “memtable flush thành SSTable”?

**Gợi ý:** Các cấu trúc và cơ chế persistence khác; không phải write path LSM giống RocksDB/Cassandra.

### Bài 9: replication và fsync

Một hệ ghi đến 2 replica nhưng cả hai mới giữ log trong OS cache. Nếu mất điện đồng thời, liệu chỉ vì đã có 2 ACK mà chắc chắn dữ liệu còn?

**Gợi ý:** Không. Cần xét durability của từng replica và giao thức xác nhận cụ thể.

### Bài 10: kiểm chứng mất điện

Thử nghiệm ghi dữ liệu rồi **đóng database bình thường**, mở lại thấy dữ liệu. Có được kết luận hệ chống mất điện tốt không?

**Gợi ý:** Không. Đóng bình thường có thể flush; phải thử đúng fault model trong môi trường kiểm soát.

### Bài 11: tombstone

Một key bị xóa nhưng version cũ còn trong SSTable. Nếu xóa tombstone quá sớm, có thể xảy ra điều gì?

**Gợi ý:** Giá trị cũ có thể tái xuất hiện khi đọc/merge hoặc sau đồng bộ không đúng.

### Bài 12: bảng đo

Thiết kế một bảng đo so sánh WAL sync và WAL async ở cùng workload. Cần những cột nào?

**Gợi ý:** Write latency p95/p99, throughput, số ghi ACK mất sau loại crash đã mô phỏng, RTO, WAL sync latency, memtable/flush backlog và cấu hình phần cứng.

### Bài 13: ba khái niệm

Nêu một tình huống giá trị **đọc được nhưng chưa durable**, và một tình huống giá trị **durable nhưng chưa xuất hiện ở một replica được đọc**.

**Gợi ý:** Trường hợp đầu là memtable được đọc trong khi WAL chưa sync. Trường hợp sau là WAL đã bền ở primary nhưng replica bị trễ hoặc đọc theo consistency model cho phép kết quả cũ.

### Bài 14: phân biệt thao tác

Ghép thuật ngữ phù hợp:

1. Gom nhiều bản cập nhật trên RAM theo khóa.
2. Ghi tuần tự để phục hồi sau crash.
3. Tạo file dữ liệu từ memtable.
4. Hợp nhất những file đã flush.
5. Yêu cầu OS đồng bộ nội dung file.
6. Chia sẻ chi phí sync cho nhiều ghi.

**Đáp án:** (1) memtable, (2) WAL/commit log, (3) flush, (4) compaction, (5) fsync/fdatasync, (6) group commit.

## 25. Quy trình phân tích một NoSQL storage engine

Khi đọc tài liệu kỹ thuật của một engine, hãy tự lần lượt trả lời:

1. **Dữ liệu mới được đặt ở đâu?** Memtable, cache, append log hay cấu trúc khác?
2. **Khôi phục sau crash dựa vào đâu?** WAL, journal, snapshot/checkpoint hay bản sao?
3. **Điều kiện acknowledgment là gì?** Có chờ sync log hay chờ replica không?
4. **Flush có nghĩa gì trong sản phẩm này?** Flush memtable, cache hay journal?
5. **Khi nào log được giải phóng?** Sau checkpoint, SSTable flush hoặc điều kiện khác?
6. **Có compaction không?** Nó ảnh hưởng byte ghi, đọc và không gian ra sao?
7. **OS và thiết bị có bảo đảm nào?** Fsync, storage cache, mất nguồn và disk failure?
8. **Có replication không?** Consistency và durability của mỗi bản sao được kết hợp thế nào?
9. **Tải cao gây backpressure ở đâu?** Memtable, WAL, flush, compaction, replica?
10. **Khi crash, làm sao đo đúng RPO/RTO?** Những ghi nào đã ACK nhưng mất, bao lâu mở lại được?
11. **Cần dữ liệu đại diện nào?** Key nóng, bản ghi lớn, TTL/tombstone, nhiều writer và tỉ lệ update?
12. **Cấu hình có hợp đồng vận hành rõ không?** Không thay đổi `sync`, WAL hoặc TTL chỉ vì benchmark nhanh hơn.

**Kết luận:** Bộ đệm ghi và memtable giúp NoSQL hấp thụ tải ghi hiệu quả bằng RAM rồi đưa dữ liệu xuống thiết bị theo đợt. Nhưng **memtable không phải nơi lưu bền**. Trong các hệ LSM, **WAL/commit log cùng chính sách đồng bộ** là thành phần chủ chốt giúp phục hồi ghi chưa được flush; **SSTable** giữ dữ liệu sau flush; **compaction** tối ưu cấu trúc file theo thời gian. Muốn hiểu một thao tác ghi có thật sự an toàn hay không, phải lần theo **đường đi của dữ liệu, thời điểm ACK, mức sync, metadata recovery, replication và mô hình sự cố** — không chỉ nhìn thấy chữ “write successful”.

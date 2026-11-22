# SSTable bất biến và các thành phần metadata/index/data trong Apache Cassandra

**SSTable (Sorted String Table)** là cấu trúc lưu trữ dữ liệu **bất biến** trên đĩa của **Apache Cassandra**. Sau khi một SSTable được tạo hoàn chỉnh từ dữ liệu trong *memtable* hoặc từ compaction/streaming, Cassandra không sửa trực tiếp những byte dữ liệu của SSTable đó để thực hiện `INSERT`, `UPDATE` hay `DELETE` tiếp theo. Thay vào đó, các phiên bản mới và **tombstone** được ghi vào memtable rồi thành các SSTable mới; **compaction** sẽ hợp nhất các SSTable khi thích hợp.

Một SSTable **không phải chỉ một tệp `Data.db`**. Nó là **một bộ thành phần cùng định danh**: dữ liệu đã sắp xếp, chỉ mục để tìm partition/row, bộ lọc Bloom, thống kê, thông tin nén, checksum và danh sách thành phần. Từ **Apache Cassandra 5.0**, định dạng SSTable **BTI (Big Trie-Indexed)** có thể dùng `Partitions.db` và `Rows.db` thay cho bộ `Index.db`/`Summary.db` của định dạng **BIG**. Vì vậy cần phân biệt *khái niệm* với *tên tệp theo phiên bản/format*.

Bài thuộc chương **SSTable và compaction** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**: hiểu kiến trúc phân tán và mô hình wide-column, partition key, thiết kế bảng theo truy vấn, consistency đọc/ghi, CQL, replication, compaction, repair, xử lý lỗi và ứng dụng Java. Mục tiêu ở đây là nắm vững **tính bất biến của SSTable và vai trò từng thành phần metadata/index/data**, từ đó giải thích đường ghi/đọc, vì sao một partition xuất hiện trong nhiều SSTable và cách chẩn đoán mà không phá dữ liệu.

## 1. Ba khái niệm không nên nhầm lẫn

| Khái niệm | Vai trò | Có phải SSTable không? |
|---|---|---|
| **Commit log** | Nhật ký ghi tuần tự giúp khôi phục những mutation chưa được flush khi node gặp sự cố | **Không**; quản lý vòng đời riêng |
| **Memtable** | Cấu trúc dữ liệu có tổ chức trong bộ nhớ nhận mutation mới của một bảng | **Không**; nguồn dữ liệu để tạo SSTable qua flush |
| **SSTable** | Tập tệp bất biến trên đĩa chứa dữ liệu đã được sắp và các chỉ mục/metadata liên quan | **Có**; đơn vị đọc, compaction, snapshot, streaming |
| **SAI index** (*Storage-Attached Index*) | Cấu trúc chỉ mục phụ, gắn với vòng đời memtable/SSTable khi bảng có SAI | **Không đồng nghĩa primary index**; có thể bổ sung tệp theo SSTable |
| **Snapshot** | Bản chụp nhất quán ở mức tệp SSTable, thường thông qua hard links trên hệ tệp hỗ trợ | Không tạo một “loại dữ liệu mới”; tham chiếu các SSTable bất biến |

**Một SSTable thuộc một bảng trên một node**, không phải “tệp chung duy nhất cho cả cluster”. Nhiều replica có dữ liệu cần sao chép nhưng **các tệp SSTable không nhất thiết trùng byte hoặc cùng số lượng**: flush, compaction, repair và streaming xảy ra độc lập theo node.

Cũng đừng hiểu **mỗi partition chỉ nằm trong một SSTable**. Một partition có thể có dữ liệu trong nhiều SSTable và memtable, vì các lần ghi của nó xuất hiện ở những đợt flush khác nhau.

### 1.1. Tính bất biến bảo đảm điều gì?

- **Không overwrite tại chỗ** nội dung hàng đã nằm trong SSTable khi có mutation mới.
- **Đọc và ghi có thể diễn ra đồng thời** mà không phải cập nhật cấu trúc dữ liệu cũ theo kiểu in-place.
- **Compaction viết đầu ra mới** rồi chuyển trạng thái active SSTables; các tệp đầu vào chỉ được loại bỏ khi có thể làm vậy an toàn, bao gồm chờ những reader đang dùng.
- **Snapshot/hard link** thuận lợi vì nội dung SSTable được tham chiếu không còn bị sửa tại chỗ.
- **Metadata và index** được tạo theo bộ dữ liệu SSTable tương ứng; nếu dữ liệu thay đổi do compaction, các cấu trúc đó của SSTable mới cũng được tạo lại.

Bất biến **không** có nghĩa dữ liệu nghiệp vụ không thể cập nhật. `UPDATE` và `DELETE` vẫn hợp lệ; chỉ **cách lưu trữ các phiên bản** là khác cơ sở dữ liệu cập nhật block tại chỗ.

## 2. Write path: từ CQL mutation đến SSTable

Một sơ đồ đơn giản cho mutation đã đi đến một **replica node**:

~~~text
Java/CQL client
      |
      v
Coordinator nhận yêu cầu -> chọn replica theo partition token
      |
      v
Replica node
  +------------------------------+
  | commit log (durability)      |
  | memtable (dữ liệu đang sống) |
  +------------------------------+
      |
      | flush: chuyển memtable hiện tại sang trạng thái
      | chỉ đọc, tiếp tục ghi vào memtable mới
      v
  +------------------------------+
  | SSTable mới, BẤT BIẾN        |
  | Data + index + metadata      |
  +------------------------------+
      |
      | các mutation sau đi vào memtable mới,
      | không sửa SSTable cũ
      v
  Compaction có thể hợp nhất nhiều SSTable thành SSTable mới
~~~

Ở Cassandra, đường ghi điển hình ghi mutation vào **commit log** và **memtable**; commit log cung cấp khả năng **replay** sau crash đối với dữ liệu chưa flush. Chính sách durability, cấu hình commit log, consistency level và tình trạng replica ảnh hưởng điều kiện một request được xác nhận. Vì vậy, **client nhận ACK không đồng nghĩa mutation đã được flush thành SSTable**.

**Flush** xảy ra khi memtable đạt các ngưỡng/điều kiện hệ thống hoặc khi được yêu cầu qua công cụ quản trị. Cassandra chuyển memtable cũ sang chế độ chỉ đọc để flush trong khi nhận ghi mới vào memtable khác; ghi dữ liệu đã sắp ra SSTable cùng các component đi kèm. Khi một khoảng commit log đã được ghi bền vững vào SSTable, các segment commit log tương ứng mới có thể đủ điều kiện tái sử dụng/xóa theo cơ chế của node.

Lý do gọi **Sorted**: trong mỗi SSTable, các partition được tổ chức theo **token order** (với `Murmur3Partitioner` là token từ hash partition key); các hàng bên trong một partition được tổ chức theo **clustering key order**. Điều này giúp tra cứu và merge tuần tự, nhưng **không** nghĩa các partition trên toàn cluster được sắp theo giá trị khóa dạng số hay ngày lịch.

### 2.1. Một row có nhiều phiên bản mà không vi phạm PRIMARY KEY

Giả sử một bảng có `PRIMARY KEY (account_id)` và cột `display_name text`.

~~~text
Lúc t1: display_name = "Mai"       -> memtable -> SSTable A
Lúc t2: display_name = "Mai Anh"   -> memtable -> SSTable B
Lúc t3: DELETE display_name        -> memtable -> SSTable C

Đọc logic tại t3: giá trị không còn sống
Đĩa trước compaction: A, B, C vẫn có thể cùng tồn tại
~~~

Cassandra **không** có ba row logic khác nhau chỉ vì ba SSTable mang cùng `account_id`. Chúng là những **phiên bản của các cell hoặc dấu xóa** được hòa giải theo metadata ghi. `PRIMARY KEY` vẫn xác định **một row logic** trong bảng.

Cần lưu ý write timestamp trong metadata của mutation thường tính bằng **micro giây**, **khác** cột CQL `timestamp` lưu thời gian nghiệp vụ bằng **mili giây**. Khi hòa giải phiên bản, Cassandra so sánh metadata write timestamp và quy tắc xử lý xung đột, không so `updated_at` do ứng dụng tự khai báo trừ khi ứng dụng thiết kế logic riêng.

## 3. SSTable là một bộ tệp: tên, thư mục và định dạng

Trên node, Cassandra lưu SSTable trong thư mục dữ liệu tương ứng **keyspace/bảng**. Đường dẫn phụ thuộc `data_file_directories`, hệ điều hành, triển khai và phiên bản.

Một cách biểu diễn giản lược:

~~~text
<data_directory>/
  demo_ks/
    events_by_device_day-<table-id>/
      nb-1-big-Data.db
      nb-1-big-Index.db
      nb-1-big-Summary.db
      nb-1-big-Filter.db
      nb-1-big-Statistics.db
      nb-1-big-CompressionInfo.db
      nb-1-big-Digest.crc32
      nb-1-big-TOC.txt

      nb-2-big-Data.db
      nb-2-big-Index.db
      ...các component của một SSTable khác...
~~~

Đây là **ví dụ định dạng BIG có nén**, không phải tên file bắt buộc. Mỗi tập có **descriptor chung** như `nb-1-big`; phần cuối `Data.db`, `Index.db` xác định component. Trong tên ví dụ:

- `nb`: mã **SSTable version** ở một dòng định dạng BIG.
- `1`: mã/generation identifier theo quy tắc của phiên bản.
- `big`: **SSTable format** BIG.
- `Data.db`, `Index.db`, `TOC.txt`: tên các thành phần.

Trên Cassandra 5.0, bản BIG có thể dùng mã version `oa`; tùy cấu hình có thể xuất hiện **BTI**. Không suy phiên bản Cassandra chỉ từ **một** tệp hoặc cố hard-code pattern `nb-*-big-*` cho mọi cluster. Một bảng đang nâng cấp/di chuyển định dạng cũng có thể có các SSTable format/version khác nhau mà node hiện tại vẫn đọc được.

### 3.1. Không có nghĩa một component là một partition

`Data.db` có thể chứa **nhiều partition**. `Index.db`/ `Partitions.db` là chỉ mục **trong cùng SSTable**, không phải một tệp cho từng partition. `Summary.db` cũng không chứa toàn bộ kết quả SELECT đã tổng hợp; nó là **index summary** để tăng tốc tìm kiếm.

Một SSTable thường có **đường dữ liệu chính** và **các tệp phụ** phục vụ tìm kiếm, integrity, thống kê. Khi một component bị mất hoặc hỏng, cách xử lý tùy component và phiên bản; **không tự xóa/chỉnh một tệp thành phần** vì nghĩ Cassandra sẽ tự tái tạo an toàn.

## 4. Data.db: nơi chứa dữ liệu thực sự

`Data.db` là thành phần dữ liệu chính, chứa dữ liệu được mã hóa theo SSTable format. Có thể hình dung:

~~~text
Data.db
  partition(token/key A)
    partition metadata
    static row (nếu có)
    clustering row #1
       columns/cells, write timestamps, TTL/tombstone metadata
    clustering row #2
       ...
  partition(token/key B)
    ...
  partition(token/key C)
    ...
~~~

Đây là **sơ đồ logic**, không phải dump nhị phân byte-for-byte. Trong thực tế, cách biểu diễn row liveness, cell, static columns, range tombstones và row index block phụ thuộc format/version.

Các điểm cần hiểu:

1. **Partition key quyết định nhóm partition**, token/partitioner định vị nhóm trên vòng dữ liệu.
2. **Clustering columns quyết định thứ tự các row** trong cùng partition; khai báo `WITH CLUSTERING ORDER BY` ảnh hưởng cách dữ liệu được tổ chức/truy vấn theo schema.
3. **Cell có metadata viết/xóa**: write timestamp, TTL/expiration theo loại cell, tombstone... nên cùng một cột có thể có các phiên bản ở nhiều SSTable.
4. **Row/partition/range tombstones** có thể che nhiều cell, không chỉ một giá trị scalar.
5. **Một partition có thể rất rộng (wide partition)**: nhiều clustering rows, nhiều index blocks; lúc đó phải quan tâm tới row index và kích thước partition, không chỉ tổng số SSTable.

**Không chỉnh trực tiếp `Data.db`** để “sửa một record” hoặc “xóa tombstone”. Nó là dữ liệu nhị phân có index/checksum/metadata liên quan; thay byte thủ công có thể gây corruption hoặc sai khác replica. Mọi sửa dữ liệu nghiệp vụ phải qua CQL/API được hỗ trợ hoặc quy trình khôi phục vận hành có kiểm soát.

### 4.1. Data.db thường nén theo khối

Khi bật compression, Cassandra nén `Data.db` thành các **compression chunks**. Một yêu cầu đọc một phần partition có thể cần tìm khối liên quan, đọc dữ liệu nén và giải nén khối đó; không đồng nghĩa phải giải nén **toàn bộ SSTable**.

Hiệu quả compression phụ thuộc loại dữ liệu, block size, codec, số lượng tombstone và pattern truy cập. Nén giảm disk và I/O trong một số trường hợp nhưng đổi lấy CPU và chi phí đọc khối. Thay cấu hình compression trên bảng không tự viết lại mọi SSTable cũ ngay lập tức; cần tính tới vòng đời flush/compaction/rewrite.

## 5. Primary index của định dạng BIG: Index.db

Ở **BIG format** truyền thống, `Index.db` lưu chỉ mục **partition key → vị trí dữ liệu** trong `Data.db`. Những partition rất rộng còn có **thông tin vị trí/index theo các vùng clustering row** (thường được gọi là promoted index hoặc row index trong BIG).

Ví dụ khái niệm:

~~~text
Index.db (BIG):
  key A -> Data.db offset 0x001000
  key B -> Data.db offset 0x03B800
  key C -> Data.db offset 0x070400
  ... các entry ở thứ tự index ...

Data.db:
  [partition A ...][partition B ...][partition C ...]
~~~

Địa chỉ hex là **minh họa**, không phải các offset có thật. Chỉ mục giúp Cassandra tìm đúng vùng byte thay vì scan tuần tự toàn bộ `Data.db` cho một partition key.

Với wide partition, khi truy vấn theo clustering range:

~~~cql
-- Sau khi đã có đầy đủ partition key:
SELECT *
FROM demo_ks.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T09:00:00Z';
~~~

Cassandra có thể sử dụng index ở mức partition và **row blocks** để thu hẹp khu vực cần đọc. Tuy nhiên, index **không biến một partition quá rộng thành nhiều partition độc lập**, và không thay partition key bằng một global secondary index.

### 5.1. Primary index khác secondary index

Tên `Index.db` ở đây là **primary on-disk index nội bộ SSTable**, phục vụ **định vị dữ liệu có khóa partition đã biết**.

Nó **không** có nghĩa Cassandra tạo một B-tree/query index tổng quát trên mọi cột của bảng. Để truy vấn `WHERE event_type = 'LOGIN'` trên toàn bộ tenant, vẫn cần **bảng theo truy vấn** hoặc index được thiết kế và kiểm thử riêng. SAI sẽ tạo **những component riêng** khi được kích hoạt.

## 6. Index summary của BIG: Summary.db

Với định dạng BIG, `Summary.db` là một **mẫu các entry trong `Index.db`** giúp định vị nhanh vị trí gần khóa cần tìm. Tài liệu mô tả mức lấy mẫu điển hình **mỗi 128 entry** theo cấu hình mặc định, nhưng sampling có thể thay đổi theo memory budget, cấu hình và version.

Hình dung:

~~~text
Index.db:
  A  B  C  D  E  F  G  H  I  J  K  ...

Summary.db:
  A  ..........  G  ..........   (ví dụ mẫu minh họa)
~~~

Khi tìm khóa `E`, Cassandra có thể dùng summary để **nhảy tới vùng chỉ mục gần E**, rồi đọc phần `Index.db` cần thiết để xác định offset `Data.db`. Vì summary là **mẫu**, nó không phải bộ chỉ mục đầy đủ và không tự khẳng định khóa nào tồn tại.

| Cấu trúc | Trả lời câu hỏi gì? | Có đủ để đọc giá trị cột không? |
|---|---|---|
| `Summary.db` | Phải bắt đầu tìm ở vùng nào của partition index? | **Không** |
| `Index.db` | Partition key này nằm ở offset nào trong `Data.db`? | **Không** |
| `Data.db` | Giá trị/cell/row cụ thể chứa gì? | **Có**, khi được giải mã với metadata phù hợp |

**Lưu ý phiên bản:** BTI ở Cassandra 5.0 có cấu trúc trie khác nên **không sử dụng index summary kiểu BIG**. Vì vậy, nếu bạn không thấy `Summary.db` trong bộ tệp BTI, đó **không phải** dấu hiệu SSTable thiếu thành phần.

## 7. Bloom filter: Filter.db

`Filter.db` chứa cấu trúc **Bloom filter** của các **partition key** xuất hiện trong một SSTable. Bloom filter giúp trả lời:

- **Chắc chắn không có** partition key trong SSTable này.
- **Có thể có** partition key trong SSTable này, cần kiểm tra chỉ mục/dữ liệu để xác nhận.

Bloom filter là **bộ lọc xác suất**, có thể xảy ra **false positive**: nó nói *có thể có*, nhưng key thực tế không nằm trong SSTable. Với Bloom filter hoạt động đúng theo thiết kế, nó không làm mất key thật bằng một **false negative**.

~~~text
Tìm partition key = P trong SSTable S

                Bloom filter S
                     |
           +---------+---------+
           |                   |
        "không"            "có thể"
           |                   |
    bỏ qua SSTable S     dùng index -> Data.db
                               |
                         kiểm tra key thật
~~~

Điều này giúp một truy vấn đọc partition không phải truy cập dữ liệu của **tất cả** SSTable một cách mù quáng, đặc biệt khi số SSTable lớn nhưng một partition chỉ xuất hiện ở một vài tệp.

### 7.1. Bloom filter không lọc clustering row

Bloom filter nội bộ này **không** trả lời “có hàng với `occurred_at = T` không?” bằng cách kiểm từng clustering key. Nó lọc ở **mức partition key**. Khi partition P có thật trong S, Cassandra vẫn cần đọc index/data phù hợp để biết các clustering rows và cell.

Bloom filter cũng **không** là index cho `WHERE status_code = 500` hoặc `WHERE tag CONTAINS ...` trên mọi partition.

### 7.2. Bộ nhớ và false-positive chance

Bloom filter thường được lưu dưới dạng `Filter.db` trên đĩa và nạp/giữ trong **bộ nhớ ngoài heap (off-heap)** khi dùng cho read path. Cấu hình `bloom_filter_fp_chance` cho bảng xác định mức chấp nhận false positive.

Ví dụ:

~~~cql
-- Chỉ minh họa cấu hình; cần đo thực tế trước khi đổi.
ALTER TABLE demo_ks.events_by_device_day
WITH bloom_filter_fp_chance = 0.01;
~~~

Giảm `bloom_filter_fp_chance` có thể giảm số lần I/O lãng phí do false positive nhưng **tăng tiêu thụ bộ nhớ**; không có giá trị tối ưu chung cho mọi workload. Bloom filter của SSTable đã được tạo khi flush/compaction; thay thông số bảng **không tự cập nhật ngay filter của các SSTable bất biến cũ**. Chúng cần được viết lại thông qua vòng đời SSTable thích hợp để nhận cấu hình mới.

Không chỉnh tham số trong production khi chưa có baseline **BloomFilterFalseRatio**, **BloomFilterOffHeapMemoryUsed**, latency và disk I/O. Với bảng chủ yếu append và ít read, cấu hình tối ưu có thể khác bảng lookup key cường độ cao.

## 8. Định dạng mới BTI: Partitions.db và Rows.db

**Cassandra 5.0** bổ sung định dạng **BTI (Big Trie-Indexed)** từ CEP-25. Khi node được cấu hình dùng BTI để tạo SSTable, cơ chế primary index khác BIG:

| BIG (truyền thống) | BTI (Cassandra 5.0+) | Ý nghĩa |
|---|---|---|
| `Index.db` | `Partitions.db` | Định vị partition bằng trie/prefix thay cho partition index kiểu BIG |
| Promoted row index nằm trong cơ chế BIG | `Rows.db` | Chỉ mục row blocks riêng cho những partition đủ rộng |
| `Summary.db` | **Không cần bản tương đương** | Trie hỗ trợ tìm key trực tiếp; không dùng index summary theo BIG |
| `Data.db` | `Data.db` | Thành phần dữ liệu chính vẫn tồn tại |
| `Filter.db`, `Statistics.db`, ... | Các thành phần tương ứng | Chức năng lọc, metadata, integrity vẫn cần thiết theo format |

### 8.1. Partitions.db làm gì?

Ở BTI, `Partitions.db` chứa chỉ mục dựa trên **trie (cây tiền tố)** để ánh xạ những phần key đủ phân biệt đến offset trong `Data.db` hoặc vào thông tin row index phù hợp. Tries tận dụng các **prefix byte chung** để giảm chi phí tra cứu và kích thước index trong nhiều trường hợp.

Không hiểu từ `Partitions.db` là “mỗi partition có một file”. Nó vẫn là một **component của toàn SSTable**.

### 8.2. Rows.db làm gì?

`Rows.db` phục vụ việc đi tới **vùng hàng (row blocks)** trong những partition rộng cần index sâu hơn. Với partition nhỏ không cần index nhiều row blocks, đường tra cứu có thể trỏ trực tiếp vào `Data.db`. Tệp `Rows.db` giúp hệ thống tránh phải nạp một promoted index khổng lồ vào bộ nhớ khi partition có rất nhiều clustering rows.

Mục tiêu là **tìm nhanh cả partition lẫn lát cắt clustering** mà không phụ thuộc cơ chế key cache/index summary của BIG.

### 8.3. Có cần cấu hình BTI không?

BTI **không** phải mặc định chắc chắn trong mọi Cassandra 5.x/bản phân phối. Tài liệu Apache mô tả cấu hình ví dụ trong `cassandra.yaml`:

~~~yaml
sstable:
  selected_format: bti
~~~

**Đây chỉ là ví dụ để hiểu định dạng. Không chỉnh `cassandra.yaml` hoặc restart node trên production theo bài học này.** Phải xác minh cách chọn format trên bản build thật, tương thích nâng cấp/hạ cấp, streaming, tài nguyên và kế hoạch rollout.

**Chọn BTI** ảnh hưởng các **SSTable mới được ghi** (flush/compaction/rewrite); không tự biến mọi SSTable BIG cũ thành BTI ngay tức thì. Một node có thể đọc cả các SSTable BIG và BTI nếu phiên bản hỗ trợ. Do đó, công cụ vận hành phải dựa trên **format trong descriptor** chứ không giả định `Index.db` luôn hiện diện.

## 9. Các thành phần metadata và integrity

Những tệp sau không phải dữ liệu nghiệp vụ chính nhưng quan trọng để đọc, khôi phục và quản trị SSTable.

| Component | Nội dung / công dụng | Điều **không** nên suy ra |
|---|---|---|
| **`Statistics.db`** | Metadata thống kê: min/max write timestamp, TTL, tombstone/deletion, clustering range, repair state, compaction level, một số histogram... | Không phải nội dung row thực tế hay một bảng thống kê truy vấn SQL |
| **`CompressionInfo.db`** | Offset/metadata các compression chunks để tìm và giải nén vùng `Data.db` thích hợp | Không phải bản sao dữ liệu nén hoàn chỉnh |
| **`Digest.crc32`** | Digest/CRC-32 để kiểm tra tính toàn vẹn `Data.db` theo format | CRC không phải bằng chứng bảo mật/chữ ký chống sửa có chủ đích |
| **`CRC.db`** | Checksum theo chunks cho một số trường hợp **không nén**/format phù hợp | Không phải mọi SSTable đều có đồng thời `CRC.db` và `CompressionInfo.db` |
| **`TOC.txt`** | Danh sách component thuộc **cùng SSTable** | Không phải danh sách tất cả SSTable của cả bảng/cluster |
| **`SAI*.db`** | Các component gắn với secondary index SAI khi được bật | Không thay thế `Index.db` hoặc `Partitions.db` cho primary-key lookup |

Tên tệp phụ thuộc phiên bản và loại format; không dùng bảng này làm hợp đồng “phải có chính xác 8 tệp”. Ví dụ, một bảng không nén có thể không có `CompressionInfo.db`; một bảng không bật SAI không có component SAI. **TOC.txt của SSTable cụ thể mới là nguồn tham chiếu trực tiếp** để nhận biết bộ component thực tế.

### 9.1. Statistics.db và tombstone metadata

`Statistics.db` có các giá trị được công cụ như `sstablemetadata` sử dụng để hiển thị:

- **Min/max timestamp** của các cell trong SSTable, liên quan tới metadata ghi.
- **Min/max local deletion time** theo cách mã hóa deletion/TTL.
- **TTL min/max**, histograms và ước lượng khả năng thu hồi tombstone.
- **Repaired-at**, pending repair/session metadata theo các phiên bản hỗ trợ.
- **Compaction level** khi chiến lược compaction dùng level.
- **First/last token/key**, partition size estimates và compression information liên quan.

Không nhầm **write timestamp micro giây trong statistics** với cột CQL `timestamp` thường biểu diễn `Instant` ở mức mili giây. Statistics được tổng hợp theo SSTable, không đủ để khẳng định “row nào có cột `event_type = LOGIN`”.

Giá trị **estimated droppable tombstones** chỉ là **ước lượng** dựa trên thời gian/metadata; không bảo đảm một compaction thực tế sẽ xóa đúng số đó. Việc có thể purge còn chịu các ràng buộc **overlap** với SSTable khác, repair state và cấu hình.

### 9.2. CompressionInfo.db dùng thế nào?

Với Data.db nén theo chunks:

~~~text
Cần đọc offset logic trong Data.db
       |
       v
CompressionInfo.db:
  chunk index -> vị trí và thông tin nén trên đĩa
       |
       v
Đọc chunk nén liên quan
       |
       v
Giải nén -> giải mã partition/row/cell
~~~

Vì nén theo khối, đọc vài byte logic có thể cần đọc/giải nén một chunk; do đó kích thước chunk ảnh hưởng **read amplification** và **compression ratio**. Không tự ý chỉnh `CompressionInfo.db`: vị trí byte sẽ không còn khớp với dữ liệu.

### 9.3. Digest, CRC và tính toàn vẹn

Digest/CRC giúp phát hiện lỗi dữ liệu do hỏng storage hoặc truyền/ghi sai ở các lớp phù hợp. Nhưng:

- CRC-32 **không** là mật mã để chống người có quyền ghi cố ý thay đổi file.
- Kiểm tra checksum **không** đảm bảo mọi dữ liệu nghiệp vụ đúng — một timestamp bị parse sai vẫn có checksum hợp lệ.
- Không thể tự “sửa corruption” bằng cách thay `Digest.crc32` cho vừa file đã hỏng.
- Khi có nghi ngờ corruption, cần quy trình backup/snapshot, xác minh replica và công cụ phục hồi của Cassandra, không sửa một component đơn lẻ.

### 9.4. TOC.txt có vai trò gì?

`TOC.txt` mô tả các component của một SSTable theo descriptor. Với BIG có nén, TOC có thể liệt kê:

~~~text
Data.db
Index.db
Summary.db
Filter.db
Statistics.db
CompressionInfo.db
Digest.crc32
TOC.txt
~~~

Với BTI, nó có thể liệt kê `Partitions.db`, `Rows.db` thay cho `Index.db`/`Summary.db`. Dù tên file là text, **đừng chỉnh TOC trực tiếp** để “ẩn” component: có thể khiến SSTable trở nên không đọc được hoặc gây sai sót trong quản lý tệp.

## 10. Read path: Cassandra dùng các thành phần thế nào?

Với truy vấn theo đầy đủ partition key, một replica cần đọc trạng thái đang sống từ **memtable và các SSTable liên quan**:

~~~text
SELECT WHERE partition_key = P
              |
              v
        Memtable / cache
              |
              v
       Các SSTable có thể chứa P
              |
     +--------+-------------------------+
     |                                  |
  Filter.db                         min/max key,
  (Bloom filter)                     token/metadata
     |                                  |
     +------- chọn candidate SSTables --+
                        |
                        v
             BIG: Summary.db + Index.db
               hoặc BTI: Partitions.db
                        |
                        v
          offset Data.db và row blocks
            (Rows.db/row index nếu cần)
                        |
                        v
          đọc/giải nén/giải mã cell
                        |
                        v
           merge với memtable và dữ liệu
             từ SSTables khác có P
                        |
                        v
             xung đột, TTL, tombstone
                        |
                        v
                 Kết quả Row/Column
~~~

Đây là sơ đồ **mô hình hóa**, không phải thứ tự gọi hàm cố định ở mọi phiên bản. Cassandra có thể sử dụng key cache, row cache, index summary, min/max metadata, partition read optimizations và nhiều đường tắt khác. Đường đọc thực tế cũng tùy loại truy vấn (row/range/collection/SAI) và mức nhất quán.

Một điểm mấu chốt: **Bloom filter chỉ loại SSTable không có partition key**. Nếu cùng partition P xuất hiện trong A, B và C thì replica có thể phải đọc dữ liệu từ **nhiều SSTable** và hợp nhất phiên bản.

### 10.1. Ví dụ ba SSTable với cùng partition

~~~text
SSTable A (cũ):
  P -> status = "PENDING", amount = 100

SSTable B (mới hơn):
  P -> status = "PAID"

SSTable C (mới hơn nữa):
  P -> tombstone(amount)

Memtable hiện tại:
  P -> note = "checked"

Kết quả logic khi đọc P:
  status = "PAID"
  amount = null   (bị tombstone che)
  note = "checked"
~~~

Metadata **write timestamp** và quy tắc reconciliation (kể cả xung đột cùng timestamp) quyết định cell nào đang sống; sơ đồ chỉ minh họa thứ tự thời gian thông thường. Cassandra không luôn lấy “cả row mới nhất” để bỏ hết cột của phiên bản cũ — **các cột có thể được ghi ở những lần mutation khác nhau**.

### 10.2. Read amplification và số SSTable

Một cách hình dung **read amplification** là số khối, chỉ mục, bộ lọc và phiên bản phải được xét để trả về **một kết quả logic**. Cùng một partition ở nhiều SSTable có thể tăng công việc đọc; Bloom filter và index giúp **bỏ qua** dữ liệu không liên quan, nhưng không loại được nhu cầu hòa giải các phiên bản thực sự liên quan.

Khi nhiều SSTable chồng lấn theo key range, các truy vấn đọc partition đã biết có thể phải kiểm tra nhiều tệp. Đó là một lý do **compaction** cần thiết.

Đừng kết luận “có 20 SSTable thì mọi SELECT đọc đủ 20 `Data.db`”: phần lớn có thể bị Bloom filter/range/index loại bỏ. Cũng đừng kết luận “SSTable count thấp thì latency luôn tốt”: một partition rất rộng hoặc tombstone dày đặc vẫn có thể gây đọc chậm.

## 11. Compaction: viết SSTable mới, không sửa SSTable cũ

Compaction đọc một nhóm SSTable được chọn, **hợp nhất** các phiên bản dữ liệu theo key/timestamp và viết một hoặc nhiều SSTable **mới**. Sau khi đầu ra đã được ghi/xác nhận theo cơ chế quản lý tệp, SSTable đầu vào được loại khỏi tập active và có thể được thu dọn khi không còn reader/snapshot giữ tham chiếu.

~~~text
Trước:
  SSTable A: P(status=PENDING), Q(...)
  SSTable B: P(status=PAID),   R(...)
  SSTable C: P(tombstone),    S(...)

                 compaction
                     |
                     v
Sau:
  SSTable D: các cell/row đang sống,
             tombstone phải còn giữ,
             metadata/index/filter mới

  A, B, C không còn thuộc live set khi swap thành công,
  nhưng chỉ được xóa file khi bảo đảm an toàn.
~~~

**Lưu ý:** compaction không nhất thiết chọn mọi SSTable chứa một partition trong một lần. Nếu có SSTable khác ngoài tập compaction đang giữ giá trị cũ, Cassandra phải **giữ dấu xóa phù hợp** để không làm dữ liệu ấy sống lại.

### 11.1. Khi nào tombstone được purge?

Không phải cứ `gc_grace_seconds` trôi qua là tombstone được xóa ngay:

1. Tombstone cần **đủ tuổi** theo chính sách grace/gc của bảng.
2. Compaction cần bảo đảm **không có dữ liệu cũ ở SSTable khác mà tombstone vẫn phải che**; có các kiểm tra overlap/coverage.
3. Trạng thái **repaired/unrepaired** và các cấu hình liên quan có thể hạn chế purge.
4. Compaction thích hợp phải **thực sự diễn ra**; thời gian grace chỉ xác định điều kiện được xét purge, không phải một job xóa có đồng hồ chính xác.

**Không tùy tiện đặt `gc_grace_seconds=0`** để làm hết tombstone nhanh. Nếu replica bỏ lỡ xóa và không được repair đúng hạn, dữ liệu cũ có thể được đồng bộ lại thành **zombie data**. Cần phối hợp retention, lịch repair, node outage, compaction và đặc tính dữ liệu.

### 11.2. Các chiến lược compaction chỉ định SSTable nào sẽ hợp nhất

Một số chiến lược:

| Chiến lược | Ý tưởng chính | Mẫu tải phù hợp cần đánh giá |
|---|---|---|
| **STCS** — SizeTieredCompactionStrategy | Nhóm các SSTable kích thước gần nhau để merge | Write-heavy, muốn hạn chế write amplification trong một số tải |
| **LCS** — LeveledCompactionStrategy | Tổ chức SSTable theo level để giới hạn overlap ở các level | Read-heavy, lookup cần ổn định hơn |
| **TWCS** — TimeWindowCompactionStrategy | Nhóm SSTable theo cửa sổ thời gian | Dữ liệu time-series với TTL/đợt ghi có đặc tính phù hợp |
| **UCS** — UnifiedCompactionStrategy (Cassandra 5.0+) | Điều chỉnh cách chọn compaction theo overlap/size, cho phép tinh chỉnh trade-off | Cần benchmark đúng phiên bản, tải đọc/ghi và tài nguyên |

Chiến lược quyết định **khi nào và những SSTable nào** được viết lại, chứ không biến **SSTable bất biến thành tệp cập nhật tại chỗ**. Các thành phần `Data.db`, index, filter, statistics của SSTable đầu ra vẫn được tạo theo format tương ứng.

Không chọn TWCS chỉ vì cột có `timestamp`; TTL khác nhau, late writes, backfill và dữ liệu cũ/sống lâu có thể phá kỳ vọng “cửa sổ tự hết hạn”. Cần đo data distribution và mô hình retention.

### 11.3. Compaction không thay repair

**Compaction** hợp nhất dữ liệu **trên một node**. **Repair** đối chiếu/phối hợp dữ liệu **giữa replica** nhằm sửa khác biệt. **Replication factor** và consistency level quyết định nhân bản và xác nhận theo schema/cấu hình, nhưng không tự thay việc repair khi có node bỏ lỡ mutation.

Một SSTable có metadata repaired/unrepaired có thể ảnh hưởng việc chọn compaction. Vì thế, không khẳng định “mọi SSTable có cùng token range sẽ được merge với nhau ngay” nếu phân nhóm repaired/compaction strategy khác nhau.

## 12. Thực hành CQL: tạo nhiều phiên bản SSTable một cách có kiểm soát

Bài lab sau **chỉ dành cho cluster thử nghiệm được phép quản trị**. `nodetool flush`, compaction và thay đổi schema ảnh hưởng tài nguyên node; không chạy mù trên production.

### 12.1. Schema wide-column theo thiết bị/ngày

~~~cql
-- Ví dụ chọn keyspace demo_ks đã tồn tại và được phép sử dụng.
CREATE TABLE demo_ks.events_by_device_day (
    device_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Mẫu truy vấn phục vụ: “Đọc 50 sự kiện mới nhất của một thiết bị trong một ngày UTC”, khi đã biết đủ `(device_id,event_day)`. Thiết kế này giảm nguy cơ một partition chứa **mọi sự kiện nhiều năm** của thiết bị, nhưng nếu một thiết bị phát quá nhiều dữ liệu/ngày thì vẫn cần đo size, shard hoặc bucket nhỏ hơn.

### 12.2. Ghi lần đầu, flush rồi ghi sửa

~~~cql
INSERT INTO demo_ks.events_by_device_day (
    device_id, event_day, occurred_at, event_id, event_type, payload
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    22222222-2222-4222-8222-222222222222,
    'LOGIN', 'v1'
);
~~~

Nếu có quyền trên node thử nghiệm:

~~~text
nodetool flush demo_ks events_by_device_day
~~~

Lệnh flush **không** khẳng định mọi replica khác của cluster đã flush cùng lúc. Nó yêu cầu node được kết nối thực hiện flush cho bảng/keyspace tương ứng.

Ghi bản sửa với **cùng primary key**:

~~~cql
UPDATE demo_ks.events_by_device_day
SET payload = 'v2'
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:00:00Z'
  AND event_id = 22222222-2222-4222-8222-222222222222;
~~~

Flush lại node lab, rồi xóa cột `payload`:

~~~cql
DELETE payload
FROM demo_ks.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:00:00Z'
  AND event_id = 22222222-2222-4222-8222-222222222222;
~~~

Nếu lại flush, một node có thể có **nhiều SSTable cho cùng partition**, mang `payload='v1'`, `payload='v2'` và tombstone. Thời điểm actual flush/compaction/background tasks có thể khiến **số lượng SSTable quan sát khác dự đoán**; không dựa vào đúng “3 tệp Data.db” trong mọi lần chạy.

### 12.3. SELECT và WRITETIME: quan sát trạng thái logic

~~~cql
SELECT occurred_at, event_id, event_type, payload
FROM demo_ks.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

`payload` có thể trả `null` vì đã bị xóa, dù `Data.db` cũ vẫn chứa byte của giá trị `'v1'`/`'v2'`. `SELECT` phản ánh **dữ liệu logic đã reconciliation**, không liệt kê mọi phiên bản SSTable.

Có thể xem write timestamp của **cột thường đang có giá trị**:

~~~cql
SELECT event_type, WRITETIME(event_type) AS event_type_write_us
FROM demo_ks.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21';
~~~

`WRITETIME(event_type)` có đơn vị **micro giây**. Không dùng `WRITETIME(occurred_at)` vì `occurred_at` là clustering column, không phải cột dữ liệu thường để lấy write time.

### 12.4. Java Driver: khóa và timestamp vẫn phải ổn định khi retry

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

// CqlSession session = ...; // Kết nối keyspace/cluster ở ngoài ví dụ.
UUID deviceId =
    UUID.fromString("11111111-1111-4111-8111-111111111111");
UUID eventId =
    UUID.fromString("22222222-2222-4222-8222-222222222222");

Instant occurredAt = Instant.parse("2026-11-21T08:00:00Z");
LocalDate dayUtc = occurredAt.atZone(ZoneOffset.UTC).toLocalDate();

PreparedStatement insert = session.prepare(
    "INSERT INTO demo_ks.events_by_device_day "
  + "(device_id,event_day,occurred_at,event_id,event_type,payload) "
  + "VALUES (?, ?, ?, ?, ?, ?)");

BoundStatement bound = insert.boundStatementBuilder()
    .setUuid(0, deviceId)
    .setLocalDate(1, dayUtc)
    .setInstant(2, occurredAt)
    .setUuid(3, eventId)
    .setString(4, "LOGIN")
    .setString(5, "v1")
    .build();

session.execute(bound);
~~~

**Retry sau timeout**: vẫn dùng `deviceId`, `dayUtc`, `occurredAt` và `eventId` đó. Nếu sinh ID/timestamp mới, bạn tạo **row mới** thay vì một mutation khác của cùng row. Điều này vừa làm sai dữ liệu nghiệp vụ vừa khiến nhiều version/SSTable phải lưu thêm nội dung không cần thiết.

Tính bất biến của SSTable là **chi tiết lưu trữ**; Java Driver không ghi trực tiếp `Data.db`, `Index.db` hay `Statistics.db`. Ứng dụng chỉ biết CQL và consistency/mutation. Không thiết kế business logic dựa trên việc “dữ liệu chắc đã nằm trong SSTable số 3”.

## 13. Chẩn đoán an toàn: nodetool, metadata và metrics

### 13.1. Quan sát node/table bằng nodetool

Một số lệnh hữu ích khi có quyền quản trị:

~~~text
nodetool tablestats demo_ks.events_by_device_day
nodetool compactionstats
nodetool status
~~~

Những thông số nên tìm:

| Chỉ số | Gợi ý ý nghĩa | Không được kết luận vội |
|---|---|---|
| **SSTable count** | Số SSTable live của bảng/node | Không phải số lần INSERT hay số partition |
| **SSTables per read** | Số SSTable data file thực sự đọc cho mỗi partition read | Không phải mọi file mà Bloom/index đã loại bỏ |
| **Bloom filter false positives/ratio** | Tần suất bộ lọc báo có thể có nhưng data không có | Không phải số row bị mất |
| **Bloom off-heap memory** | Bộ nhớ dành cho Bloom filter | Không phải toàn bộ Java heap |
| **Index summary off-heap memory** | Chi phí summary BIG khi có | Không áp dụng giống nhau cho BTI |
| **Compression metadata memory** | Bộ nhớ để định vị/decompress chunks | Không phải raw Data.db trong RAM |
| **Pending compactions** | Công việc compaction đang chờ | Không tự đồng nghĩa lỗi; cần xem xu hướng |
| **Space used live/total** | Dung lượng SSTable theo nhiều cách tính | Snapshot, hard link và filesystem có thể ảnh hưởng dung lượng quan sát |
| **Estimated partition size** | Dấu hiệu partition rộng/hotspot | Chỉ là estimate/histogram, cần điều tra theo workload |

**Nên xem xu hướng** trên thời gian và tương quan với p95/p99 read latency, write latency, disk I/O, free disk, flush queue. Một ảnh chụp số liệu đơn lẻ thường không đủ để quyết định đổi compaction strategy.

### 13.2. sstablemetadata, sstabledump, sstablepartitions

Các công cụ `sstablemetadata`, `sstabledump` và (trên phiên bản hỗ trợ) `sstablepartitions` giúp **kiểm tra SSTable ở mức tệp**. Ví dụ minh họa:

~~~text
sstablemetadata /path/to/oa-1-big-Data.db
sstabledump /path/to/oa-1-big-Data.db
sstablepartitions /path/to/oa-1-big-Data.db
~~~

**Quan trọng về an toàn:**

- Đường dẫn chỉ là **placeholder**. Không tự dò rồi chạy bừa trên production.
- Công cụ, tham số và yêu cầu node đang chạy hay dừng **phụ thuộc từng lệnh/phiên bản**. Hãy đọc hướng dẫn chính thức của đúng bản triển khai.
- Khi có thể, dùng **snapshot hoặc bản sao SSTable nhất quán** để điều tra, tránh thay đổi file đang được Cassandra quản lý.
- `sstabledump` có thể hiển thị **dữ liệu thật và thông tin nhạy cảm**, cần quản lý quyền, đầu ra log và redaction.
- **Không tự chạy scrub, upgradesstables, compact hoặc major compaction** chỉ để “xem thử”; các công cụ đó có thể rewrite tệp và tiêu tốn nhiều disk/CPU.
- Nếu gặp checksum mismatch/corruption, **không xóa một component** để thử tự hồi phục; tuân theo runbook sự cố và phương án restore/repair đã được xác nhận.

### 13.3. Nhìn đúng phiên bản/định dạng

Khi đọc một thư mục SSTable, trước tiên xác minh:

1. **Đây là node và keyspace/table nào?**
2. **SSTable descriptor nào?** Ví dụ BIG hay BTI, version nào.
3. **Các component nào thực sự nằm trong TOC của bộ đó?**
4. **SSTable có nén không? Có index SAI không?**
5. **Bảng dùng chiến lược compaction nào? Metadata repaired/unrepaired thế nào?**

Chỉ sau đó mới so sánh size hoặc giả thuyết “thiếu Index.db”. Đối với **BTI**, không thấy `Index.db`/`Summary.db` là **bình thường**; phải tìm `Partitions.db` và các thành phần phù hợp.

## 14. Những hiểu lầm thường gây sự cố

| Hiểu lầm | Thực tế | Hành động đúng |
|---|---|---|
| “SSTable là một tệp Data.db.” | SSTable là **bộ component** dữ liệu/index/metadata/integrity. | Nhận diện theo descriptor + TOC. |
| “UPDATE sửa record trong Data.db cũ.” | SSTable cũ **bất biến**; mutation mới vào memtable rồi SSTable mới. | Hiểu read reconciliation và compaction. |
| “DELETE phải xóa byte ngay.” | Xóa tạo tombstone; byte cũ có thể còn trên đĩa. | Thiết kế TTL/repair/compaction an toàn. |
| “Mỗi partition chỉ xuất hiện trong một SSTable.” | Một partition có thể ở nhiều SSTable và memtable. | Quan sát SSTables per read. |
| “Index.db là secondary index cho mọi cột.” | Đó là **primary on-disk index của BIG**. | Dùng đúng partition key/SAI/bảng truy vấn. |
| “Summary.db chứa tóm tắt dữ liệu nghiệp vụ.” | Nó là **sampling của Index.db** trong BIG. | Dùng index summary để hiểu đường đọc. |
| “Bloom báo có thì chắc chắn có.” | Bloom có **false positive**. | Phải tra index/data để xác nhận. |
| “Bloom báo không nhưng vẫn có thể có.” | Bộ lọc hoạt động đúng **không có false negative** cho key đã thêm. | Kiểm tra phần mềm/data integrity nếu có dấu hiệu ngược. |
| “Index.db bắt buộc trên mọi Cassandra 5.0.” | **BTI** dùng `Partitions.db`/`Rows.db`; BIG vẫn có Index/Summary. | Kiểm tra format thay vì suy từ phiên bản. |
| “Có CompressionInfo.db nghĩa toàn SSTable phải giải nén khi đọc.” | Data được nén theo chunks; chỉ đọc những chunks cần thiết. | Đánh giá chunk size/CPU/I/O. |
| “Statistics.db là một bảng có thể SELECT trong CQL.” | Là **metadata nội bộ**, không phải CQL table. | Dùng `sstablemetadata`/metrics. |
| “CRC chứng minh dữ liệu đúng nghiệp vụ.” | Checksum chỉ giúp kiểm integrity theo format. | Validate ở API và test round-trip. |
| “Sau gc_grace_seconds tombstone biến mất đúng giờ.” | Cần compaction và kiểm tra an toàn/overlap/repair. | Theo dõi repair và purge eligibility. |
| “Compaction sửa tất cả replica.” | Compaction **cục bộ từng node**; repair **giữa replica**. | Phân biệt mục đích hai cơ chế. |
| “Nhiều SSTable luôn có nghĩa mọi read mở đủ bấy nhiêu Data.db.” | Bloom, min/max và index có thể skip phần lớn. | Đo SSTablesPerRead, latency, false positives. |
| “Giảm gc_grace_seconds về 0 để dọn nhanh.” | Có thể gây zombie nếu replica bỏ lỡ xóa. | Chỉ thay đổi theo runbook và repair guarantees. |
| “Có 1000 rows nên partition chắc nhỏ.” | Payload lớn hoặc nhiều phiên bản/tombstone vẫn gây tải. | Đo bytes/partition, wide partitions, tombstone. |
| “Client ACK nghĩa chắc Data.db đã được ghi.” | ACK không đồng nghĩa flush SSTable. | Hiểu commitlog, consistency và recovery. |

## 15. Bài tập kiểm tra hiểu biết

### Bài 1 — Component nào chứa gì?

Cho các mô tả: “bytes của các row”, “partition index”, “bloom filter”, “thống kê TTL/tombstone”, “định vị chunk nén”, “danh sách component”.

**Đáp án:** lần lượt là **`Data.db`**, **`Index.db` của BIG hoặc `Partitions.db` của BTI**, **`Filter.db`**, **`Statistics.db`**, **`CompressionInfo.db`**, **`TOC.txt`**.

### Bài 2 — Tại sao UPDATE không sửa SSTable?

Một client đọc `balance = 100`; sau đó `UPDATE balance = 120`. Có phải Cassandra mở `Data.db` chứa giá trị 100 rồi ghi đè trực tiếp?

**Đáp án:** không. Mutation ghi qua **commit log/memtable**, sau đó thành SSTable mới; khi đọc Cassandra hòa giải phiên bản. Compaction có thể về sau thay tập SSTable bằng SSTable mới có phiên bản thích hợp.

### Bài 3 — Bloom filter dương tính giả

Một Bloom filter trả “có thể có” đối với partition P nhưng `Index.db` không thấy key đó. Đã hỏng dữ liệu chưa?

**Đáp án:** chưa chắc; đó có thể là **false positive bình thường**. Nó làm tốn thêm tra cứu nhưng không làm mất dữ liệu. Ngược lại, nếu filter trả “không” với key thực sự trong đúng SSTable, cần điều tra integrity/corruption vì không phù hợp giả định thiết kế Bloom filter.

### Bài 4 — BIG và BTI

Bạn thấy các tệp `da-10-bti-Data.db`, `da-10-bti-Partitions.db`, `da-10-bti-Rows.db`, nhưng không thấy `Index.db` hoặc `Summary.db`.

**Câu hỏi:** đây có phải SSTable bị thiếu index?

**Đáp án:** không. Đây là **BTI**, dùng trie-indexed partition/row components. Hãy xem descriptor/TOC và phiên bản, không áp checklist BIG lên BTI.

### Bài 5 — Tombstone đủ 10 ngày nhưng chưa purge

Một bảng có tombstone đã qua `gc_grace_seconds` nhưng vẫn còn trong SSTable.

**Hỏi:** điều đó có phải lỗi Cassandra?

**Đáp án:** chưa chắc. Chưa có compaction phù hợp, hoặc còn SSTable chứa dữ liệu cũ mà tombstone phải che, hoặc điều kiện repair/overlap chưa đạt. Không xóa thủ công tombstone. Điều tra compaction, metadata, overlap và lịch repair.

### Bài 6 — Một partition nằm nhiều SSTable

Sau ba lần ghi/flushing trên cùng partition P, trên node có ba SSTable chứa các phần khác nhau của P. SELECT trả đủ các trường mới nhất.

**Câu hỏi:** Cassandra làm thế nào? Có biến P thành ba partition CQL khác nhau không?

**Đáp án:** không. Nó tra các SSTable/memtable liên quan và **merge/reconcile** theo metadata ghi; P vẫn là **một partition logic**. Compaction có thể gộp các phiên bản thành SSTable mới.

### Bài 7 — Java retry và row trùng

Worker Java ghi event có `event_id=UUID.randomUUID()`. Sau timeout, worker sinh UUID mới rồi ghi lại. Có khả năng tạo hai dòng không?

**Đáp án:** có. Chúng có **primary key khác nhau**; Cassandra không biết đó là cùng một sự kiện nghiệp vụ. Hãy cấp event ID **một lần**, giữ timestamp/bucket/ID ổn định qua retry.

### Bài 8 — Chọn công cụ điều tra

Mục tiêu: “Biết table có bao nhiêu SSTable live và Bloom false-positive ratio”; “Xem metadata min/max timestamp, repaired-at của một SSTable cụ thể”; “Xem các partition rộng có nhiều tombstone”.

**Đáp án:** tương ứng dùng **`nodetool tablestats`/metrics**, **`sstablemetadata`**, **`sstablepartitions`** (nếu bản Cassandra hỗ trợ), trên môi trường/đường dẫn được kiểm soát. Đừng dùng `DELETE` file hoặc major compaction chỉ để lấy số liệu.

## 16. Checklist thiết kế và vận hành SSTable

- [ ] Đã phân biệt **commit log**, **memtable** và **SSTable** trong write path?
- [ ] Hiểu **ACK ghi không đồng nghĩa flush**, và crash recovery có liên quan commit log?
- [ ] Đã hiểu SSTable là **bất biến**; UPDATE/DELETE tạo mutation/phiên bản thay vì sửa Data.db cũ?
- [ ] Biết một SSTable là **bộ nhiều tệp** cùng descriptor, không chỉ `Data.db`?
- [ ] Biết `Data.db` chứa row/cell/tombstone theo partition token và clustering order?
- [ ] Phân biệt `Index.db` (BIG) và `Partitions.db`/`Rows.db` (BTI)?
- [ ] Hiểu `Summary.db` là sampling của index BIG, không có bản tương tự bắt buộc ở BTI?
- [ ] Hiểu `Filter.db` là Bloom filter **partition key**, có false positives nhưng không false negatives?
- [ ] Biết `CompressionInfo.db` định vị chunks nén, không là dữ liệu kinh doanh?
- [ ] Biết `Statistics.db` chứa metadata timestamp/tombstone/TTL/repair/compaction?
- [ ] Biết `Digest.crc32`, `CRC.db`, `TOC.txt` có vai trò integrity/component discovery theo format?
- [ ] Nếu bật SAI, đã phân biệt component SAI với **primary-key index**?
- [ ] Đã đo SSTablesPerRead, BloomFilterFalseRatio, index summary/off-heap memory và compaction pending?
- [ ] Biết tombstone purge còn phụ thuộc **gc_grace_seconds, overlap, compaction, repair**, không chỉ thời gian?
- [ ] Không dùng `gc_grace_seconds=0`, `scrub` hay major compaction như thao tác chữa cháy tùy tiện?
- [ ] Đã chọn partition/bucket theo truy vấn để tránh wide partitions và nhiều dữ liệu chồng lấn?
- [ ] Nếu sử dụng Java Driver, mutation/retry giữ ID, timestamp, bucket ổn định?
- [ ] Có quy trình snapshot/backup, repair và điều tra corruption **không chỉnh trực tiếp các tệp SSTable**?
- [ ] Đã xác nhận phiên bản Cassandra, SSTable format và yêu cầu của công cụ trước khi thao tác?
- [ ] Khi thay compaction/compression/Bloom settings, có benchmark và đánh giá vòng đời rewrite của SSTable?

## Tài liệu tham khảo

- [Apache Cassandra — Storage Engine (SSTable components, BIG/BTI)](https://cassandra.apache.org/doc/latest/cassandra/architecture/storage-engine.html).
- [Apache Cassandra — Compaction Overview](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html).
- [Apache Cassandra — Tombstones, gc_grace_seconds và điều kiện purge](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/compaction/tombstones.html).
- [Apache Cassandra — Bloom Filters](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/bloom_filters.html).
- [Apache Cassandra — Trie-Indexed SSTables / BTI (Cassandra 5.0)](https://cassandra.apache.org/_/blog/Apache-Cassandra-5.0-Features-Trie-Memtables-and-Trie-Indexed-SSTables.html).
- [Apache Cassandra — nodetool tablestats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tablestats.html).
- [Apache Cassandra — sstablemetadata](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/sstablemetadata.html).
- [Apache Cassandra — sstablepartitions](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/sstablepartitions.html).
- [Apache Cassandra — Metrics](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/metrics.html).

**Ghi nhớ:** **SSTable bất biến** là nền tảng của storage engine Cassandra: ghi mới không overwrite `Data.db` cũ, mà sinh SSTable mới rồi để **read reconciliation và compaction** xử lý nhiều phiên bản. **`Data.db` chứa dữ liệu**, **index định vị partition/row** (BIG dùng `Index.db`/`Summary.db`; BTI dùng `Partitions.db`/`Rows.db`), **`Filter.db` loại SSTable chắc chắn không liên quan**, còn **`Statistics.db`, `CompressionInfo.db`, digest/CRC và `TOC.txt`** phục vụ metadata, hiệu năng và tính toàn vẹn. Hiểu từng thành phần giúp thiết kế truy vấn đúng, vận hành compaction/repair an toàn và tránh “sửa nhanh” bằng thao tác trực tiếp lên tệp bất biến.


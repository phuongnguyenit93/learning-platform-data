# Chi phí ghi, lưu trữ, xây dựng lại và truyền chỉ mục trong Apache Cassandra

## 1. Đặt vấn đề: chỉ mục giúp đọc, nhưng ai trả chi phí?

Trong Apache Cassandra, dữ liệu được phân phối qua nhiều node theo **partition key**, sao chép theo **replication factor (RF)** và tổ chức thành các **wide-column partition**. Khi truy vấn dùng đúng partition key, Cassandra có thể xác định tương đối trực tiếp replica cần đọc. Khi muốn lọc theo cột không nằm trong khóa, ta có thể tạo chỉ mục phụ để tăng khả năng tìm kiếm.

Ví dụ ứng dụng có bảng đơn hàng theo khách hàng và ngày: truy vấn `WHERE tenant_id = ? AND order_day = ?` định vị một partition, nhưng nghiệp vụ còn muốn lọc `status = 'PAID'`. Chỉ mục trên `status` có thể giúp lọc kết quả. Tuy nhiên, kể từ khi tạo chỉ mục, **mỗi thay đổi liên quan đến cột ấy cũng tạo thêm công việc lưu trữ và bảo trì**.

Bốn loại chi phí chính của bài học:

1. **Ghi:** xử lý giá trị được lập chỉ mục tại các replica, cập nhật cấu trúc in-memory và/hoặc cấu trúc phụ.
2. **Lưu trữ:** dữ liệu chỉ mục nằm thêm trên đĩa, cạnh SSTable dữ liệu, cùng không gian tạm trong lúc flush, compaction và rebuild.
3. **Xây dựng lại:** khi tạo chỉ mục trên bảng đã có dữ liệu, mất/hỏng chỉ mục hoặc thay đổi cấu hình, node phải xử lý lại dữ liệu hiện hữu.
4. **Truyền/streaming:** khi cluster bootstrap, thay node, cân bằng token range hay repair, các file dữ liệu và thành phần chỉ mục có thể cần truyền qua mạng hoặc tạo lại tại nơi nhận.

**Thông điệp chính:** một chỉ mục không phải “miễn phí sau `CREATE INDEX`”. Nó đổi chi phí đọc truy vấn lấy chi phí trên đường ghi, disk, CPU, bộ nhớ, vận hành và đôi khi cả băng thông mạng.

> Phạm vi ví dụ: Apache Cassandra 5.0 với **Storage-Attached Indexing (SAI)**; đồng thời đối chiếu **legacy secondary index (2i)**. Cassandra 4.x không có SAI tích hợp tương tự Cassandra 5.0, nên cần xem đúng phiên bản và bản phân phối trước khi áp dụng cú pháp hay kỳ vọng vận hành.

## 2. Phân biệt primary index, 2i, SAI và bảng phục vụ truy vấn

| Cơ chế | Nơi lưu/duy trì | Khi nào hữu ích | Chi phí chính |
|---|---|---|---|
| **Primary index** theo partition key | Cơ chế tra cứu SSTable gốc, có trên mỗi replica chứa dữ liệu | Truy vấn xác định partition | Chi phí nền tảng của mọi bảng Cassandra |
| **Secondary index truyền thống (2i)** | Cấu trúc **local** trên từng node, triển khai như bảng chỉ mục ẩn | Truy vấn theo cột ngoài khóa trong trường hợp được chọn kỹ | Ghi/bảo trì bảng phụ, đĩa, quét các token range nếu truy vấn không xác định partition |
| **Storage-Attached Indexing (SAI)** | Chỉ mục trên memtable và các thành phần gắn với SSTable trên replica | Lọc theo cột ngoài khóa; Cassandra 5.0 | Duy trì chỉ mục theo mutation, flush, compaction; tiêu thụ bộ nhớ/đĩa; chi phí đọc phân tán |
| **Bảng phi chuẩn hóa do ứng dụng duy trì** | Một bảng CQL riêng với partition key theo truy vấn | Query pattern ổn định, cần truy cập định vị chính xác | Ghi thêm bảng, replication riêng, nhất quán giữa các bảng do ứng dụng quản lý |

**SAI và 2i đều có cấu trúc chỉ mục local ở các node chứa dữ liệu tương ứng.** Một truy vấn không có partition key vẫn có thể phải liên hệ nhiều replica/token range. Đừng hiểu “index phân tán” là có một danh bạ toàn cụm duy nhất giúp mọi truy vấn thành thao tác point lookup.

Một bảng như `orders_by_tenant_day` có thể cho hiệu quả tốt khi xác định tenant và ngày rồi lọc thêm bằng SAI. Nhưng `WHERE status = 'PAID'` trên toàn bộ cluster vẫn là một truy vấn phân tán, dù có chỉ mục.

## 3. Đường ghi và nơi phát sinh công việc chỉ mục

Giả sử một client thực hiện:

~~~cql
UPDATE shop.orders_by_tenant_day
SET status = 'PAID'
WHERE tenant_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
  AND order_day = '2026-11-21'
  AND order_id = bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb;
~~~

Ở mức khái niệm, đường ghi có các phần sau:

1. **Coordinator** xác định token/replica từ `(tenant_id, order_day)` và chuyển mutation tới các replica.
2. **Mỗi replica nhận mutation** theo đường ghi Cassandra, gồm commit log và memtable cho dữ liệu gốc.
3. **Cột có chỉ mục được xử lý tại replica.** Với SAI, mutation được phản ánh vào chỉ mục memtable; đường ghi SAI có tính đồng bộ với ghi dữ liệu. Với 2i, node duy trì cấu trúc chỉ mục local theo cơ chế 2i.
4. Khi đạt yêu cầu **write consistency level** (`ONE`, `LOCAL_QUORUM`,...), coordinator phản hồi cho client. Consistency level không bỏ qua chi phí index phát sinh ở các replica.
5. Về sau, **flush** và **compaction** tạo hoặc viết lại các cấu trúc chỉ mục trên đĩa; đây là chi phí có thể xuất hiện **sau** thời điểm request nhận ACK.

~~~mermaid
flowchart TD
    A["Client INSERT/UPDATE/DELETE"] --> B["Coordinator: xác định replica"]
    B --> R1["Replica 1"]
    B --> R2["Replica 2"]
    B --> R3["Replica 3"]
    R1 --> W1["Commit log + memtable dữ liệu"]
    R2 --> W2["Commit log + memtable dữ liệu"]
    R3 --> W3["Commit log + memtable dữ liệu"]
    W1 --> I1["Duy trì index local"]
    W2 --> I2["Duy trì index local"]
    W3 --> I3["Duy trì index local"]
    I1 --> F1["Flush: SSTable và index files"]
    I2 --> F2["Flush: SSTable và index files"]
    I3 --> F3["Flush: SSTable và index files"]
    F1 --> C["Compaction / streaming / rebuild về sau"]
    F2 --> C
    F3 --> C
~~~

Sơ đồ minh họa **RF = 3**, không cố định thứ tự nội bộ của mọi phương pháp lập chỉ mục. Trong thực tế, các replica có thể cùng giữ nhiều dữ liệu, lịch flush/compaction khác nhau và thành phần SAI/2i được quản lý theo cách khác nhau.

### Vì sao nhiều index làm giảm tốc độ ghi?

Với SAI, mỗi cột được index cần ghi nhận giá trị và liên kết tới khóa/row ID phù hợp, giữ thêm cấu trúc trong bộ nhớ và viết file trên đĩa lúc flush. Số index nhiều có thể tăng ước lượng mức dùng heap của memtable, khiến flush xảy ra thường hơn; nhiều SSTable nhỏ hơn có thể tạo thêm công việc compaction.

Với 2i, việc duy trì bảng chỉ mục ẩn cũng dùng CPU, ghi local và tài nguyên nền. Dù triển khai khác nhau, **mỗi chỉ mục vẫn là một write path bổ sung**.

Không nên dùng công thức “n index nghĩa là write latency tăng đúng n lần”. Chi phí phụ thuộc vào loại dữ liệu, số cột được thay, độ dài giá trị, số distinct values, TTL, tombstone, bộ nhớ, chiến lược compaction, tải nền và phiên bản Cassandra.

## 4. Lập mô hình chi phí ghi và replication

Một mô hình ước lượng để lập ngân sách tài nguyên:

~~~text
Số mutation logic/giây tại client = W
Số bản sao dữ liệu (RF)             = R
Số chỉ mục trên cột bị ảnh hưởng    = I

Mutation dữ liệu tại replica/giây   ≈ W × R
Công việc cập nhật index local      ≈ W × R × I
~~~

Mô hình này chỉ là **đếm các lượt công việc tiềm năng** khi tất cả mutation đều thay cả I cột đã index, không phải metric Cassandra thực tế, cũng không phải công thức tính latency hoặc packet mạng.

**Ví dụ minh họa:** một workload 1.200 update/giây, RF = 3, mỗi update thay đổi hai cột có index. Có thể phải xử lý khoảng 3.600 replica-mutation/giây và tối đa theo mô hình đơn giản là 7.200 lượt xử lý chỉ mục local/giây. Nếu chỉ một cột có index được thay, số lượt liên quan giảm theo cách triển khai.

Cần tránh một phép nhân sai rất phổ biến: **không phải thêm hai index thì hệ thống nhất thiết gửi hai lần dữ liệu gốc giữa các replica**. Ghi vẫn được replica hóa theo partition/RF; tại mỗi replica, index được duy trì **từ mutation nhận được**. Chi phí truyền mạng bổ sung chủ yếu có thể thể hiện qua xây dựng lại, streaming, dữ liệu giữa các node và cách truy vấn phân tán, chứ không phải một bản broadcast riêng của mỗi index cho mọi write.

### Dấu hiệu đường ghi đang chịu tải vì index

- P95/P99 write latency tăng sau khi `CREATE INDEX` hoặc thêm nhiều cột index.
- CPU/heap tăng, memtable flush và compaction tăng.
- Số SSTable và hàng đợi compaction tăng; disk I/O sát giới hạn.
- Độ trễ lúc rebuild hoặc bootstrap cùng lúc với traffic ghi cao.
- Tăng garbage collection hoặc áp lực heap khi index nhiều cột/giá trị.

Phải đo **trước/sau trên cùng dạng workload**. Một index không đương nhiên là nguyên nhân duy nhất khi write latency tăng.

## 5. Chi phí lưu trữ: dung lượng index nhân với số replica và thời gian

### 5.1. Index không thay thế dữ liệu gốc

Chỉ mục lưu thông tin tìm kiếm như giá trị cột và ánh xạ về hàng/partition, nhưng Cassandra vẫn giữ dữ liệu gốc trong SSTable. Tạo index làm tăng tổng dung lượng cần thiết trên node.

- **2i** lưu index trong bảng ẩn riêng trên từng node. Chi phí gắn với dữ liệu được lập chỉ mục, cách tổ chức bảng phụ và thao tác bảo trì.
- **SAI** lưu các thành phần chỉ mục gắn với SSTable, gồm thành phần riêng theo cột và thành phần có thể dùng chung ở mức SSTable. Thiết kế chia sẻ giúp tiết kiệm hơn một mô hình lưu bản sao đầy đủ cho từng index.
- **Replication** làm dữ liệu và index local xuất hiện trên nhiều replica. Một table 500 GB dữ liệu gốc logical với RF = 3 không chỉ tốn 500 GB tổng đĩa; còn phải tính ba bản sao dữ liệu, index, compaction và các thành phần khác.

Không nên áp dụng một tỷ lệ “index luôn chiếm 10% dữ liệu” cho mọi cột. Cột kiểu `text` dài, phân phối giá trị, độ nén và nhiều update có thể cho kết quả khác xa cột số có phân phối hẹp.

### 5.2. Chỉ số đĩa nên được đọc đúng

Với **Cassandra 5.0 SAI**, virtual table `system_views.indexes` có các cột:

- `per_column_disk_size`: bytes của thành phần riêng cho index của cột.
- `per_table_disk_size`: bytes của thành phần index cấp SSTable được chia sẻ giữa các index trong bảng.
- `indexed_sstable_count`: số SSTable có dữ liệu tương ứng được index.
- `is_building` và `is_queryable`: trạng thái xây dựng và dùng được của index.

Khi ước tính tổng dung lượng từ nhiều row `system_views.indexes`, **đừng cộng lặp phần `per_table_disk_size` cho từng cột**: đây là phần **dùng chung**, cần tính một lần theo thực tế bố trí của bảng/SSTable.

Cũng cần theo dõi dung lượng dành cho:

1. SSTable gốc và commit log/memtable hoạt động.
2. Thành phần index on-disk.
3. SSTable/index tạm thời trong compaction hoặc rebuild.
4. Snapshot/backup, repair/streaming hoặc dữ liệu được giữ cho vận hành.

**Disk dùng lúc build/compaction có thể cao hơn disk ở trạng thái ổn định.** Khi lập kế hoạch không được giả định chỉ có bản dữ liệu sau cùng.

### 5.3. TTL, delete và tombstone

Một trường có TTL hoặc bị xóa thường xuyên không biến mất khỏi tất cả file ngay tại thời điểm client nhận ACK. Cassandra dùng tombstone và cơ chế compaction/garbage collection theo quy tắc của hệ thống. Với SAI, candidate từ index có thể phải được **post-filter** khi dữ liệu đã bị tombstone che khuất; hệ thống xử lý xóa theo cơ chế tích hợp storage engine.

Hệ quả thực tế: churn cao có thể làm tăng tổng công việc index, SSTable/index files và chi phí compaction, ngay cả khi **số row sống tại một thời điểm** không tăng nhiều.

## 6. Xây dựng chỉ mục ban đầu trên bảng đã có dữ liệu

Một tình huống hay gặp: bảng đã chứa hàng trăm triệu row, đến hôm nay mới cần filter theo `status`. Khi tạo index, hệ thống phải **lập index cho dữ liệu hiện hữu**.

### 6.1. Chi phí build ban đầu

Quá trình có thể cần đọc các SSTable hiện có, xây dựng ánh xạ giá trị → row/partition và ghi các thành phần index xuống disk. Trong khi đó, ứng dụng vẫn phát sinh write mới và node còn chạy compaction, repair hoặc truy vấn bình thường.

- **I/O đọc:** quét dữ liệu cũ để tạo nội dung index.
- **CPU/heap:** xử lý terms, row IDs và cấu trúc tìm kiếm.
- **I/O ghi:** tạo file chỉ mục và metadata.
- **Áp lực đồng thời:** cạnh tranh I/O/CPU với write, flush, compaction và read.
- **Thời điểm query dùng được:** đừng mặc định index lập tức queryable chỉ vì câu `CREATE INDEX` đã trả về thành công.

Cassandra thực hiện xây dựng index nền theo cơ chế của phiên bản/index implementation. Với SAI 5.0, có thể kiểm tra `is_building`/`is_queryable` **trên các node liên quan** trước khi chuyển traffic truy vấn mới sang index. Query dựa trên index đang build có thể không sẵn sàng hoặc bị từ chối tùy trạng thái node.

### 6.2. Ví dụ CQL: SAI trên Cassandra 5.0

Giả sử keyspace `shop` đã tồn tại và có replication phù hợp; thực hành trên môi trường thử nghiệm trước:

~~~cql
CREATE TABLE shop.orders_by_tenant_day (
    tenant_id uuid,
    order_day date,
    order_id uuid,
    status text,
    channel text,
    amount decimal,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id, order_day), order_id)
);

-- Cassandra 5.0: index SAI trên cột ngoài khóa.
CREATE INDEX orders_status_sai
ON shop.orders_by_tenant_day (status)
USING 'sai';

CREATE INDEX orders_channel_sai
ON shop.orders_by_tenant_day (channel)
USING 'sai';
~~~

Thử thao tác dữ liệu, dùng đúng partition key để phạm vi đọc rõ ràng:

~~~cql
INSERT INTO shop.orders_by_tenant_day
    (tenant_id, order_day, order_id, status, channel, amount, updated_at)
VALUES (
    aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa,
    '2026-11-21',
    bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb,
    'NEW', 'WEB', 250000, toTimestamp(now())
);

UPDATE shop.orders_by_tenant_day
SET status = 'PAID', updated_at = toTimestamp(now())
WHERE tenant_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
  AND order_day = '2026-11-21'
  AND order_id = bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb;

SELECT order_id, status, amount
FROM shop.orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
  AND order_day = '2026-11-21'
  AND status = 'PAID';
~~~

Khi update `status = 'NEW' → 'PAID'`, index phải phản ánh giá trị mới trong cơ chế lưu trữ Cassandra; chỉ lưu lại SSTable dữ liệu gốc thôi chưa đủ để truy vấn index cho kết quả đúng.

### 6.3. Xem trạng thái build và disk usage

~~~cql
-- Virtual table Cassandra 5.0 SAI: truy vấn metadata cục bộ trên node kết nối.
SELECT index_name, table_name, is_building, is_queryable,
       indexed_sstable_count, per_column_disk_size, per_table_disk_size
FROM system_views.indexes
WHERE keyspace_name = 'shop'
  AND index_name = 'orders_status_sai';
~~~

Chú ý virtual table cung cấp trạng thái **của node được hỏi**. Trong cluster nhiều node, cần kiểm tra các node/replica liên quan, không lấy một kết quả local làm bằng chứng index trên cả cluster đã sẵn sàng.

Có thể truy vấn thêm `system_views.sstable_indexes` để xem chi tiết theo SSTable khi cần điều tra sự chênh lệch dung lượng.

## 7. Rebuild index: vì sao và bằng cách nào?

**Rebuild index** nghĩa là **tạo lại cấu trúc chỉ mục từ dữ liệu của bảng**. Nó khác với sửa row nghiệp vụ và khác với thao tác lấy dữ liệu token range từ các node khác.

Các tình huống có thể cần build/rebuild:

- Tạo chỉ mục khi bảng đã có dữ liệu.
- File thành phần chỉ mục bị thiếu hoặc cần tạo lại sau một sự cố.
- Thay cấu hình/index: với SAI, thường phải **drop và tạo lại** vì không thể `ALTER` trực tiếp định nghĩa SAI index.
- Khôi phục/vận hành theo hướng dẫn tương ứng với phiên bản và index implementation.

**Câu lệnh quản trị:** Apache Cassandra có `nodetool rebuild_index`, cú pháp:

~~~bash
nodetool rebuild_index <keyspace> <table> <indexName...>
~~~

Ví dụ, chạy trên node cần rebuild index (sau khi đã xác nhận version/loại index và kế hoạch vận hành):

~~~bash
nodetool rebuild_index shop orders_by_tenant_day orders_status_sai
~~~

Ý nghĩa: tạo lại **native secondary index** được chỉ định của bảng trên **node đang được thao tác**. Không nên giả định chạy một lần từ một node là đã rebuild tất cả node trong cluster. Cần xác minh khả năng hỗ trợ/đặc điểm của phương pháp chỉ mục đang dùng theo bản phát hành.

### Rebuild index không phải rebuild dữ liệu

| Lệnh/hoạt động | Nội dung chính | Tài nguyên đáng chú ý |
|---|---|---|
| `CREATE INDEX` trên bảng có dữ liệu | Khởi tạo index và build từ dữ liệu hiện có | Quét SSTable, CPU, heap, disk index |
| `nodetool rebuild_index` | Rebuild index native của một bảng trên node được chỉ định | Đọc dữ liệu local, ghi lại index |
| `nodetool rebuild` | Lấy **dữ liệu** từ những node khác bằng streaming, thường gắn với datacenter/token range | Băng thông, disk I/O, xử lý SSTable |
| `nodetool repair` | Đối soát dữ liệu giữa replica, có thể gây streaming dữ liệu | Merkle/diff, streaming, compaction và hiệu ứng index liên quan |
| Compaction | Tổ chức lại/ghi SSTable dữ liệu mới | I/O dữ liệu và cập nhật/generate index gắn với SSTable |

Hai lệnh `rebuild_index` và `rebuild` có tên gần nhau nhưng **không thay thế nhau**. `nodetool rebuild` không phải “xây dựng lại chỉ mục của bảng”.

Khi sửa thiếu index, trước hết kiểm tra liệu node đang build hay index đã queryable, log lỗi và disk headroom. Không chạy rebuild lặp lại khi quy trình build đang diễn ra mà không có nguyên nhân rõ.

## 8. “Truyền chỉ mục” khi replication, bootstrap, repair và streaming

Cụm từ **truyền chỉ mục** có thể chỉ ba hoạt động khác nhau. Phân biệt chúng giúp không tính nhầm network bandwidth.

### 8.1. Mutation được replicate, index được duy trì local

Trong write thường, coordinator **truyền mutation** tới các replica của partition; các replica cập nhật index local. Không có một “global index server” nhận tất cả bản sao index ở mỗi lần ghi của Cassandra 2i/SAI.

Ví dụ RF = 3, ghi một row có cột `status` được index: **ba replica nhận mutation dữ liệu theo protocol ghi** và mỗi node duy trì index phù hợp. Vì vậy, thêm index ảnh hưởng CPU/heap/disk local trực tiếp hơn là nhân số packet replication theo số index.

### 8.2. Schema và trạng thái index được truyền khác với dữ liệu index

Cấu hình `CREATE INDEX` là **schema metadata** phân phối qua cluster để các node biết định nghĩa index. Đây không phải luồng truyền toàn bộ postings/terms của index mỗi lần schema thay đổi.

Riêng SAI còn có **trạng thái queryable/building** được các node thông tin cho coordinator (ví dụ qua cơ chế gossip). Việc lan truyền **trạng thái** giúp coordinator tránh replica có index không thể query, nhưng không đồng nghĩa tất cả node đang giữ bản sao giống hệt một file index toàn cục.

### 8.3. Truyền SSTable khi bootstrap, thay node hoặc repair

Khi node mới bootstrap, node bị thay thế, dịch chuyển token range hoặc repair, Cassandra có thể phải **stream SSTable/data** giữa các node. Index gắn với dữ liệu sẽ bị ảnh hưởng tùy implementation và đường streaming.

**Điểm quan trọng đối với SAI 5.0:** SAI tương thích với **zero-copy streaming (ZCS)**. Khi stream một SSTable **nguyên vẹn và đủ điều kiện**, các thành phần chỉ mục SAI có thể được truyền **cùng SSTable**, giúp tránh tạo index từ đầu ở nơi nhận. Nếu việc streaming không theo đường gửi nguyên file hoặc điều kiện không thỏa, không được giả định mọi index file luôn được sao chép nguyên trạng; cần tham khảo xử lý ở phiên bản triển khai và kiểm tra trạng thái index.

**Với legacy 2i**, index local nằm trong cấu trúc riêng, nên không áp dụng nguyên xi khẳng định “index luôn được truyền cùng SSTable” của SAI. Trong những đường nhận dữ liệu hoặc khôi phục, cấu trúc index có thể phải được duy trì/xây dựng trên node nhận theo cơ chế 2i.

~~~mermaid
flowchart TD
    A["Một partition được replicate"] --> B["Replica A: data + index local"]
    A --> C["Replica B: data + index local"]
    A --> D["Replica C: data + index local"]
    B --> E{"Bootstrap / replace / repair?"}
    E -->|Có| F["Stream dữ liệu/SSTable phù hợp"]
    F --> G{"SAI + nguyên SSTable đủ điều kiện ZCS?"}
    G -->|Có| H["Truyền thành phần index cùng SSTable"]
    G -->|Không| I["Tạo/duy trì index theo đường stream và implementation"]
    H --> J["Xác nhận index queryable trên node nhận"]
    I --> J
~~~

**Đừng trộn hai khái niệm:**
- **Network replication theo write CL/RF**: phục vụ dữ liệu mới.
- **Streaming khi topology/repair thay đổi**: truyền lượng dữ liệu có thể rất lớn trong một thời gian ngắn, và có thể kèm index component.

Cả hai cùng tạo network traffic, nhưng khác thời điểm và cách kiểm soát. `nodetool netstats` và streaming metrics giúp quan sát loại thứ hai.

## 9. Flush, compaction và repair có thể nhân chi phí index thế nào?

### Flush

Khi memtable flush thành SSTable, SAI ghi các thành phần chỉ mục tương ứng với SSTable mới. Nhiều index đồng nghĩa thêm công việc tạo index file; bộ nhớ ước lượng của index memtable có thể ảnh hưởng tần suất flush.

### Compaction

Compaction đọc/merge các SSTable và tạo SSTable mới; với SAI, index component gắn với SSTable mới cũng được sinh trong tiến trình này. Các file cũ được thay thế sau khi không còn được tham chiếu. Vì vậy, chi phí index tồn tại **cả khi không có request ghi mới**, miễn là còn nền compaction.

Nếu workload churn cao hoặc dùng chiến lược compaction có mức rewrite lớn, thêm index có thể góp phần tăng write amplification. Không nên kết luận “compaction chỉ động đến base data, index không ảnh hưởng”.

### Repair

Repair so sánh replica và có thể stream dữ liệu khác biệt. Tác động tới index phụ thuộc đường nhận SSTable và implementation. Về mặt vận hành, repair tiêu thụ disk/network và có thể chồng tải với build index, flush, compaction. Repair giúp **hòa hợp dữ liệu giữa replica**; nó không bảo đảm định nghĩa index đã build xong trên mọi node chỉ vì lệnh repair kết thúc.

### Backup/snapshot và restore

Cần hiểu rõ phương án snapshot/restore và thành phần SSTable/index được bảo tồn với bản phân phối đang dùng. Phần index có thể làm tăng kích thước backup. Sau restore, kiểm tra khả năng query qua index, không chỉ kiểm tra dữ liệu base table còn đọc được.

## 10. Ứng dụng Java: index được duy trì ở server, nhưng latency phản ánh lên client

Trong ứng dụng Java, DataStax Java Driver 4.x không cần lệnh “update index” riêng cho mỗi write. Ứng dụng phát mutation CQL bình thường; Cassandra duy trì index tại replica.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.util.UUID;

// session đã kết nối; bảng và chỉ mục được tạo bởi migration.
PreparedStatement update = session.prepare(
    "UPDATE shop.orders_by_tenant_day SET status = ? " +
    "WHERE tenant_id = ? AND order_day = ? AND order_id = ?"
);

UUID tenantId = UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
UUID orderId  = UUID.fromString("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb");
java.time.LocalDate orderDay = java.time.LocalDate.of(2026, 11, 21);

BoundStatement statement = update.bind(
        "PAID", tenantId, orderDay, orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

session.execute(statement);
// Cassandra duy trì SAI/2i tại replica; không có lệnh cập nhật index ở driver.
~~~

Ở đây `LOCAL_QUORUM` chỉ là cấu hình minh họa cho topology có RF phù hợp trong datacenter. Nó không biến index thành dữ liệu chung toàn cluster, cũng không đổi bản chất **query dựa trên index** thành point lookup.

Ứng dụng nên đo latency của chính request `UPDATE`, tỉ lệ timeout, retry và hiệu suất truy vấn indexed trước và sau khi thêm index. Nếu muốn giảm độ trễ, cần phân biệt network/cross-DC, tranh chấp partition, disk backlog và tác động index, thay vì gán mọi biến động cho driver.

## 11. Quan sát và lập kế hoạch dung lượng trước khi đưa index vào production

### Các quan sát quan trọng

| Cần đo | Vì sao cần | Gợi ý nguồn |
|---|---|---|
| Write throughput, P95/P99 latency và timeout | Phát hiện tác động trên request client | Metrics driver + Cassandra |
| Heap, GC, memtable usage, flush rate | Index có thể tăng bộ nhớ và tần suất flush | JMX/Cassandra metrics |
| Số SSTable, compaction queue và bytes compacted | Index được tạo/viết lại khi SSTable thay đổi | `nodetool compactionstats`, metrics |
| Disk size index và trạng thái build | Tránh đọc index khi chưa sẵn sàng, đo footprint | `system_views.indexes` (SAI 5.0) |
| Streaming incoming/outgoing bytes, active streams | Đo bootstrap, repair, replacement | `nodetool netstats`, streaming metrics |
| Latency truy vấn theo index, số partition/token range cần đọc | Đánh giá lợi ích có bù được chi phí ghi không | Tracing, metrics, workload test |

**Không chỉ dùng kích thước index để quyết định.** Index nhỏ nhưng truy vấn phải quét nhiều token range vẫn có thể đắt. Index tiết kiệm rất nhiều read I/O có thể đáng giá dù tăng write latency một chút. Quyết định phải dựa trên mục tiêu SLO của hệ thống.

### Quy trình đưa index mới vào hoạt động

1. **Xác định query thật:** có đủ partition key chưa, filter theo cột nào, cardinality/selectivity bao nhiêu, giới hạn trả về thế nào?
2. **Kiểm tra bản Cassandra:** SAI có sẵn ở Cassandra 5.0; nếu cluster 4.x phải xem khả năng hỗ trợ khác, không sao chép cú pháp `USING 'sai'` máy móc.
3. **Đo baseline:** write latency, throughput, disk utilization, compaction backlog, read latency; ghi nhận cả peak traffic.
4. **Thử ở staging với dữ liệu và workload tương tự:** tạo index trên dữ liệu đã tồn tại để đo **thời gian build ban đầu**, CPU/IO và dung lượng.
5. **Dự phòng disk/IO/CPU và chọn thời điểm:** tránh build hàng loạt nhiều index khi đang repair, streaming hoặc gần full disk.
6. **Tạo và theo dõi trạng thái index:** chỉ chuyển traffic đọc phụ thuộc index khi những replica được dùng đã **queryable**.
7. **Quan sát sau khi triển khai:** nếu p99 write tăng hoặc backlog kéo dài, điều chỉnh workload/query design, số index hoặc cách rollout.
8. **Chuẩn bị đường rollback:** biết cách `DROP INDEX` và chuyển truy vấn về phương án cũ; nhưng việc drop/recreate có thể đòi **build lại** trước khi dùng lần nữa.

Khi bảng cập nhật liên tục và có nhiều index, cần giữ mức disk headroom cho compaction/rebuild/repair. Không thể suy từ chỉ số sử dụng disk trong trạng thái bình thường rằng đủ chỗ thực hiện các hoạt động nền.

## 12. Sự cố thường gặp và cách phân tích

### Sự cố A — Sau khi tạo index, write p99 tăng mạnh

**Giả thuyết:** index duy trì nhiều cột, memtable index dùng thêm heap, flush/compaction tăng; build dữ liệu cũ đang tranh I/O. Kiểm tra `is_building`, heap/GC, compaction queue, disk throughput và so sánh với baseline. Nếu build còn chạy, cần xem ảnh hưởng tạm thời riêng với chi phí steady state.

### Sự cố B — Node vừa bootstrap, truy vấn SAI lỗi hoặc trả kết quả thiếu

**Đừng vội kết luận “SAI chưa được truyền từ node khác”.** Cần phân biệt đang stream dữ liệu, phần SAI nào được stream với SSTable, build local có hoàn tất chưa, và coordinator có chọn replica `is_queryable` hay không. Kiểm tra node cụ thể qua `system_views.indexes`, log, `nodetool netstats` và phiên bản hệ thống.

### Sự cố C — Disk tăng sau compaction/rebuild

SSTable cũ và mới hoặc index file cũ và mới có thể cùng tồn tại tạm thời, nhất là lúc file còn được truy vấn tham chiếu. Quan sát disk theo thời gian, task compaction, snapshot/backup và thành phần SAI; không coi mọi disk tăng tạm là rò rỉ.

### Sự cố D — Cần “rebuild” sau sửa index

Xác định đầu tiên mục tiêu là **cấu trúc chỉ mục**, **dữ liệu từ replica khác**, hay **đối soát replica**. Dùng `rebuild_index` khi phù hợp với index, `rebuild` cho streaming dữ liệu theo mục đích quản trị, và `repair` khi cần đối soát replica. Không dùng lệnh sai chỉ vì chúng cùng có từ “build”.

### Sự cố E — Index có rồi nhưng truy vấn vẫn quá chậm

Đánh giá lại mô hình bảng theo truy vấn: có đang dùng index cho truy vấn toàn cluster không? Cột `status` có rất nhiều row cùng giá trị không? Có cần nhiều điều kiện lọc, limit, pagination hay trả dữ liệu quá lớn không? SAI giảm công việc lọc nhưng **không xóa chi phí phân tán dữ liệu và đọc kết quả**. Nếu query pattern cố định và cần point lookup, bảng phi chuẩn hóa phù hợp có thể là lựa chọn tốt hơn.

## 13. Bài tập áp dụng

**Bài 1.** Có 2.000 ghi logic/giây, RF = 3 và ba index. Có được kết luận hệ thống gửi 18.000 thông điệp replication riêng cho index mỗi giây không?

**Trả lời:** Không. Công việc index chủ yếu diễn ra local trên replica. Con số `2.000 × 3 × 3` chỉ có thể dùng như mô hình ước lượng lượt xử lý index khi cả ba cột indexed được thay đổi, không phải số packet network hoặc tốc độ ghi thực.

**Bài 2.** Bảng đã có 5 TB dữ liệu; thêm một SAI index rồi lập tức chuyển toàn bộ truy vấn production sang nó. Rủi ro?

**Trả lời:** Build dữ liệu cũ tốn CPU, disk IO và dung lượng; index trên các node có thể chưa queryable. Phải theo dõi trạng thái xây dựng trên replica liên quan và chuẩn bị giới hạn tải.

**Bài 3.** Một node mới bootstrap bằng zero-copy streaming đủ điều kiện và nhận SSTable có thành phần SAI. Có phải luôn rebuild index từ đầu ở node mới không?

**Trả lời:** Không. Với SAI, các thành phần index có thể được stream cùng SSTable theo đường ZCS đủ điều kiện. Nhưng phải kiểm tra tình huống streaming thực tế và trạng thái queryable; không khái quát cho 2i hoặc mọi đường truyền.

**Bài 4.** Admin cần lập lại native index của bảng `orders_by_tenant_day`, người khác đề xuất `nodetool rebuild`. Có đúng mục tiêu không?

**Trả lời:** Không. `nodetool rebuild` là streaming **dữ liệu**; `nodetool rebuild_index` dành cho rebuild **native secondary index** phù hợp trên node.

**Bài 5.** Nếu có SAI index trên `status` và `channel`, `system_views.indexes` hiển thị `per_table_disk_size` ở hai row. Có thể cộng hai số đó để biết toàn bộ shared disk size không?

**Trả lời:** Không nên cộng đôi chi phí thành phần dùng chung. Cần tính riêng phần shared theo đúng SSTable/table và cộng với phần riêng từng cột.

## 14. Ghi nhớ

Chỉ mục trong Cassandra có ích khi workload truy vấn cần lọc ngoài partition key, nhưng **write nào tạo hoặc đổi giá trị indexed cũng kéo theo việc duy trì chỉ mục trên replica**. Với SAI, phần lớn vòng đời chỉ mục đi sát memtable/SSTable, nên chi phí không dừng ở request ghi: flush, compaction, rebuild, bootstrap, repair và streaming đều có thể ảnh hưởng tài nguyên. Với 2i, index local dạng bảng ẩn có cơ chế bảo trì và đặc điểm khác.

Tính **tổng chi phí sở hữu** bằng cách cân đối lợi ích giảm scan/read với write amplification, disk footprint, thời gian build và vận hành cluster. Phân biệt chắc chắn **replication mutation**, **truyền schema/trạng thái index**, **streaming SSTable**, **rebuild index** và **rebuild dữ liệu** sẽ giúp thiết kế hệ thống đáng tin cậy hơn.

### Tài liệu chính thức để đối chiếu theo phiên bản

- [Apache Cassandra — Indexing concepts](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/indexing/indexing-concepts.html)
- [Apache Cassandra — SAI write and read paths](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-read-write-paths.html)
- [Apache Cassandra — SAI concepts và zero-copy streaming](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-concepts.html)
- [Apache Cassandra — SAI virtual tables](https://cassandra.apache.org/doc/stable/cassandra/reference/sai-virtual-table-indexes.html)
- [Apache Cassandra — Rebuild native secondary indexes](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/rebuild_index.html)
- [Apache Cassandra — Streaming architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/streaming.html)

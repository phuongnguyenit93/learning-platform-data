# Định dạng SSTable và tương thích qua các phiên bản Apache Cassandra

> **Chương:** SSTable và compaction  
> **Trọng tâm:** Cách đọc cấu trúc file SSTable, nhận biết mã định dạng BIG/BTI và mức tương thích khi nâng cấp/khôi phục một cluster Apache Cassandra. Ví dụ ưu tiên Cassandra 3.11, 4.0/4.1 và 5.0.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao Cassandra lưu một bảng thành **nhiều SSTable bất biến**, mỗi SSTable lại gồm **nhiều file thành phần**.
2. Đọc tên file như `oa-12-big-Data.db` hay `da-21-bti-Data.db`, phân biệt **mã phiên bản SSTable**, **thế hệ file**, **định dạng** và **thành phần**.
3. Nêu vai trò `Data.db`, `Index.db`/`Summary.db`, `Partitions.db`/`Rows.db`, `Filter.db`, `Statistics.db` và các component khác.
4. Phân biệt BIG và BTI từ Cassandra 5.0; biết ảnh hưởng của cấu hình `sstable.selected_format`, compaction và `storage_compatibility_mode`.
5. Nhận diện ranh giới **đọc dữ liệu của bản cũ trên bản mới** so với **rollback từ bản mới về bản cũ** và vì sao snapshot không tự chuyển đổi định dạng.
6. Thực hành quan sát/đánh giá nâng cấp SSTable với các lệnh hỗ trợ, đồng thời tránh thay đổi dữ liệu đang phục vụ người dùng.

**Phạm vi:** Đây là định dạng **on-disk của Apache Cassandra**, không phải định dạng CQL, driver Java hay giao thức native protocol. Bài không giả định các bản phân phối Cassandra do hãng khác phát hành có chung chính sách tương thích.

## 2. SSTable ở đâu trong storage engine?

Cassandra dùng kiến trúc gần với **Log-Structured Merge Tree (LSM-tree)**. Replica ghi mutation vào **commit log** và **memtable**; khi flush, memtable được ghi thành SSTable trên đĩa. SSTable là **immutable**: một UPDATE hoặc DELETE về sau không chỉnh sửa trực tiếp nội dung file cũ.

~~~text
             CQL write từ ứng dụng
                       |
                  Coordinator
                       |
                  Replica node
                    /      \
               Commit log   Memtable (theo bảng)
                                  |
                              [flush]
                                  |
                            SSTable #101
                                  |
           UPDATE/DELETE -------> Memtable mới
                                  |
                              [flush]
                                  |
                            SSTable #102
                             \     /
                           [compaction]
                                |
                           SSTable #103
                       (đầu ra bất biến mới)
~~~

SSTable **không phải một file `.db` đơn lẻ**. Một SSTable được nhận diện bằng một descriptor chung; các file thành phần cùng descriptor lưu dữ liệu, chỉ mục, bloom filter, thống kê và thông tin checksum. Mỗi table có nhiều SSTable, vì một partition có thể có các phiên bản dữ liệu nằm rải rác trên nhiều thế hệ.

### 2.1. Cách Cassandra sắp thứ tự dữ liệu

- Các partition trong SSTable được sắp theo **thứ tự token** của partition key (với Murmur3Partitioner); các key có cùng token được xử lý theo bộ so sánh phù hợp.
- Các row trong một partition được sắp theo **clustering key** theo quy tắc CQL của bảng.
- Timestamp, TTL và tombstone được lưu để có thể **hợp nhất giá trị mới nhất** khi đọc qua nhiều SSTable và memtable.
- SSTable có thể **nén theo block**; khả năng đọc một key không đòi giải nén toàn bộ file `Data.db`.

Việc đổi format SSTable không đổi **partition key**, **token ring**, **replication factor** hay cách phân phối partition đến replica. Nó thay cách lưu và tìm dữ liệu **cục bộ trên mỗi node**.

## 3. Một SSTable gồm những thành phần nào?

Ví dụ bộ file **BIG** trên một node Cassandra 5.0, tên file được minh họa:

~~~text
<data_dir>/sstable_lab/events-<table_uuid>/
  oa-12-big-Data.db
  oa-12-big-Index.db
  oa-12-big-Summary.db
  oa-12-big-Filter.db
  oa-12-big-Statistics.db
  oa-12-big-CompressionInfo.db
  oa-12-big-Digest.crc32
  oa-12-big-TOC.txt
~~~

Đây là **ví dụ tên file**, không bảo đảm mọi node/bảng luôn có đủ các component liệt kê. Chẳng hạn `CompressionInfo.db` chỉ có khi dùng compression phù hợp; tên và số component khác nhau giữa **BIG**, **BTI**, các phiên bản và tính năng index.

| Thành phần | Chức năng | Lưu ý |
|---|---|---|
| `Data.db` | Dữ liệu partition, row, cell, tombstone | File dữ liệu chính, **immutable** |
| `Index.db` | Primary index của **BIG**: partition key → vị trí dữ liệu; có thông tin row index khi cần | Khác với secondary index/SAI |
| `Summary.db` | Mẫu thưa của BIG `Index.db`, giúp khoanh vùng index cần đọc | Không chứa mọi row |
| `Filter.db` | Bloom filter cho partition key | Có false positive; không false negative nếu cấu trúc hợp lệ |
| `CompressionInfo.db` | Offset và kích thước các block nén trong `Data.db` | Chỉ có khi phù hợp cấu hình compression |
| `Statistics.db` | Metadata như token, min/max timestamp, deletion time, compaction level, repaired state, compression, TTL | Rất hữu ích khi phân tích nâng cấp/sự cố |
| `Digest.crc32` | Digest CRC để kiểm tra dữ liệu `Data.db` | Không thay thế backup/replica repair |
| `TOC.txt` | Liệt kê thành phần thuộc SSTable | File mô tả, không phải dữ liệu CQL |
| `Partitions.db` | Partition index dạng trie của **BTI** | Thay vai trò tìm partition của `Index.db` trong BIG |
| `Rows.db` | Index cho các row/block trong partition lớn của **BTI** | Không phải SSTable nào cũng có dữ liệu row index như nhau |
| `SAI*.db` | Cấu trúc của Storage-Attached Indexing nếu bảng có SAI | SAI là **chỉ mục phụ**, khác BTI primary index |

### 3.1. Đọc theo khóa partition trong BIG

Luồng đọc được đơn giản hóa:

~~~text
SELECT ... WHERE tenant_id = ?
             |
        tính token/key
             |
    [Bloom Filter: Filter.db]
       |            |
  chắc chắn không   có thể có
       |            |
      bỏ qua     Summary.db -> Index.db
                              |
                         Data.db (vị trí partition)
                              |
                       đọc row và hòa giải
~~~

Bloom filter chỉ loại nhanh những SSTable **chắc chắn không chứa partition**. Nếu Bloom filter báo “có thể có”, Cassandra phải xác minh qua index và dữ liệu thật. `Index.db` là **primary partition index**, không phải SAI và không đồng nghĩa với `CREATE INDEX` ở CQL.

### 3.2. Đọc theo partition trong BTI

BTI (*Big Trie-Indexed*, có từ Cassandra 5.0) dùng index dựa trên trie thay vì cách tra cứu primary index theo kiểu BIG truyền thống:

~~~text
SELECT ... WHERE tenant_id = ?
             |
          token/key
             |
        Partitions.db  (trie theo partition key)
             |
         Data.db
             |
      Rows.db khi cần tra row/block trong wide partition
             |
          trả dữ liệu
~~~

BTI thay phần **index** của SSTable bằng các cấu trúc như `Partitions.db` và `Rows.db`, giúp giảm chi phí tìm kiếm của một số workload, đặc biệt với partition lớn hoặc truy vấn có điều kiện clustering. `Data.db` vẫn lưu dữ liệu hàng. Đây không phải chỉ mục SAI, dù cả BTI và SAI có thể sử dụng ý tưởng trie.

> **Quan trọng:** Tài liệu kiến trúc Cassandra thường liệt kê thành phần của cả BIG và BTI chung trên một trang. Không có nghĩa mỗi SSTable đồng thời có `Index.db`, `Partitions.db` và `Rows.db`. Hãy nhìn descriptor `big`/`bti` và tập file thực tế.

## 4. Cách giải mã tên file SSTable

Với cách đặt tên hiện đại:

~~~text
oa-12-big-Data.db
│  │   │   └── component: nội dung dữ liệu
│  │   └────── format implementation: BIG
│  └────────── generation/id: nhận diện một SSTable trên node
└───────────── version code: phiên bản on-disk của BIG

da-21-bti-Partitions.db
│  │   │   └── component: trie partition của BTI
│  │   └────── format implementation: BTI
│  └────────── generation/id: SSTable khác
└───────────── version code: phiên bản on-disk của BTI
~~~

- **Version code** (`mc`, `nb`, `oa`, `da`...) biểu diễn phiên bản *định dạng file*, **không phải số phát hành server** như 5.0.9 và **không phải CQL protocol version**.
- **Generation/ID** dùng phân biệt một SSTable với SSTable khác của cùng bảng/node; không phải RF, token hay row count.
- **Format identifier** (`big`, `bti`) chọn bộ triển khai format, tách biệt **version code**. Ví dụ `oa` thuộc BIG còn `da` thuộc BTI.
- **Component** cho biết file cụ thể làm gì. Không dựa vào riêng `Data.db` để kết luận đủ dữ liệu SSTable; phải giữ các component liên quan.

Các bản Cassandra rất cũ có cách đặt tên khác; không parse filename bằng biểu thức tự viết rồi áp đặt cho mọi đời. Với môi trường thực, dùng công cụ Cassandra đúng phiên bản để đọc descriptor.

### 4.1. Bảng mã phiên bản tham khảo

| Dòng Cassandra | Định dạng | Mã SSTable đáng chú ý | Điểm cần nhớ |
|---|---|---|---|
| 2.1–2.2 | BIG đời cũ | `ka`, `la`, `lb` | Đây là dữ liệu lịch sử, không suy luận có thể đọc vô điều kiện trên mọi bản mới |
| 3.0/3.11 | BIG | `ma`, `mb`, `mc`, `md`, `me` | Mỗi mã gắn thay đổi metadata/on-disk theo bản phát hành; ví dụ `mc` ở 3.0.8/3.9, `md` ở 3.0.18/3.11.4 |
| 4.0/4.1 | BIG | `na` (4.0 RC), `nb` (4.0 GA và các bản tiếp theo) | Thay đổi format metadata, Bloom filter, tracking repair và host id |
| 5.0 | BIG | `oa` | Có metadata/token coverage và thay đổi deletion-time mới |
| 5.0 | BTI | `da` | Phiên bản BTI đầu tiên, cùng lúc bản 5.0 vẫn có thể hỗ trợ BIG |

Bảng này mô tả **mốc mã on-disk theo tài liệu Apache**, không phải mapping “cứ chạy server 5.0 là mọi file tự có tiền tố `oa`”. Cluster có thể giữ các SSTable cũ sau upgrade, dùng cấu hình tương thích, hoặc đã chọn `bti`. Vì vậy **một thư mục bảng có thể đồng thời tồn tại nhiều mã phiên bản và nhiều SSTable** trong quá trình chuyển đổi.

Mỗi phiên bản server chỉ đọc được một tập định dạng nhất định; ngoài version code còn có **storage compatibility mode**, cấu hình compression, định dạng index, partitioner và các điều kiện triển khai khác cần được xét.

## 5. BIG và BTI của Cassandra 5.0: khác nhau ở đâu?

Từ Cassandra 5.0, Apache Cassandra hỗ trợ cả hai:

| Khía cạnh | BIG (định dạng legacy) | BTI (trie-indexed) |
|---|---|---|
| Được giới thiệu | BIG hiện đại dùng rộng rãi từ Cassandra 3.x | Cassandra 5.0 |
| Primary index | `Index.db` và `Summary.db` | `Partitions.db` và `Rows.db` |
| Định vị partition | Bloom filter, index summary và partition index | Trie index và các cấu trúc tương ứng |
| Truy cập row trong wide partition | Collation/row index trên BIG | Cấu trúc `Rows.db` hỗ trợ tìm row/block |
| Mã phiên bản trong 5.0 | `oa` (khi dùng format/version mới) | `da` |
| Tương thích Cassandra 4.x | Dựa trên **version code** BIG mà node 4.x hỗ trợ | 4.x không có BTI reader tích hợp |
| Tạo mới trong 5.0 | `selected_format: big` | `selected_format: bti` |

**Mặc định:** `cassandra.yaml` tương thích của Cassandra 5.0 giữ `big` là mặc định khi phần cấu hình `sstable` đang comment; file `cassandra_latest.yaml` hướng đến tính năng mới và có thể chọn `bti`. Không suy từ “đang dùng Cassandra 5.0” ra “đã bật BTI”. Xem cấu hình thực trên từng node.

Ví dụ chọn format trên một node/lab đã cho phép thay cấu hình:

~~~yaml
# cassandra.yaml, Cassandra 5.0+.
sstable:
  selected_format: bti
~~~

Khi bật format khác, **những SSTable cũ không được tự viết lại chỉ vì sửa YAML**. Các SSTable sinh từ flush, compaction hoặc thao tác rewrite phù hợp có thể dùng format đích; file cũ tồn tại cho đến khi được thay theo vòng đời. Cần kiểm tra tương thích và thủ tục restart tương ứng.

### 5.1. Hiệu năng không chỉ phụ thuộc tên format

BTI giúp cải thiện một số workload index lookup, nhưng hiệu quả phụ thuộc:

1. Kích thước partition, số row, độ dài clustering key.
2. Tỷ lệ đọc theo partition/row so với scan nhiều partition.
3. Bloom filter false positives, cache, chunk compression.
4. Số SSTable phải đọc sau nhiều flush và trạng thái compaction.
5. Disk I/O, bộ nhớ, CPU, request concurrency và topology nhiều replica.

Tham số `column_index_size` áp dụng cho cả BIG/BTI trong Cassandra 5.0, với mặc định khác theo format; giảm block index có thể tăng tốc đọc trong partition nhưng cũng tăng kích thước index. Không sao chép cài đặt BIG sang BTI mà không benchmark.

### 5.2. BTI và SAI khác nhau

**BTI** là kiểu primary SSTable index để xác định partition và row/block trong dữ liệu đã nằm trên node. **SAI (Storage-Attached Indexing)** là chỉ mục phụ trên những cột được khai báo bằng CQL `CREATE INDEX ... USING 'sai'` để hỗ trợ lọc giá trị. Một bảng có thể dùng **SSTable BTI** và **SAI** đồng thời; file SAI thêm component riêng.

~~~text
Format SSTable: bti
  -> primary lookup: Partitions.db / Rows.db

SAI trên cột status:
  -> secondary lookup theo giá trị status
  -> xác định row ID/partition, đọc dữ liệu gốc
~~~

Không đổi `selected_format` để “bật SAI”, và không dùng `CREATE INDEX` để chuyển `big` thành `bti`.

## 6. “Tương thích qua phiên bản” nghĩa là những gì?

Đừng gộp mọi loại tương thích vào một câu “Cassandra X đọc được dữ liệu Cassandra Y”. Ít nhất có **năm ranh giới riêng**:

| Loại tương thích | Câu hỏi đúng | Không được đánh đồng với |
|---|---|---|
| **On-disk SSTable** | Binary server có reader cho format/version file này không? | CQL schema hợp lệ |
| **Storage compatibility mode** | Node đang cho phép ghi version file/commit log/hints nào? | Chỉ riêng `sstable.selected_format` |
| **Streaming giữa node** | Cặp node/version có thương lượng và truyền dữ liệu thành công không? | Việc copy file trực tiếp bằng OS |
| **Snapshot/restore** | File snapshot có thể khởi động/nhập lại trên binary đích và đúng schema không? | Tạo snapshot thành công |
| **Native protocol/Java driver** | Ứng dụng gửi và nhận CQL qua driver có tương thích không? | Reader của SSTable trên đĩa |

### 6.1. Hướng nâng cấp và hướng hạ cấp không đối xứng

Trong lộ trình nâng cấp **được Apache hỗ trợ**, binary mới thường có khả năng **đọc các file SSTable cũ** ở những phiên bản nguồn thuộc phạm vi hỗ trợ. Điều này giúp rolling upgrade không bắt buộc rewrite toàn bộ dữ liệu tức thì.

Chiều ngược lại **không được bảo đảm**:

- Cassandra 4.1 không thể coi là reader hợp lệ cho `oa`/`da` sinh bởi Cassandra 5.0.
- Một node cũ không tự hiểu cấu trúc trie index BTI, kể cả khi file `Data.db` mang nội dung tương tự BIG.
- Nếu format/metadata mới đã được ghi, thay lại binary cũ trên cùng data directory có thể **không khởi động được** hoặc không đọc đúng dữ liệu.
- Một snapshot được tạo từ SSTable cũ giúp có vật liệu để rollback, nhưng snapshot đó phải thuộc **thời điểm và trạng thái dữ liệu** phù hợp với RPO; rollback còn liên quan schema, commit log, hints, feature flags và phiên bản Cassandra.

Không có quy tắc “mọi phiên bản mới đều đọc mọi file từ tất cả phiên bản trước” bất kể khoảng cách nâng cấp. Phải đọc **upgrade path chính thức**, giới hạn version nguồn/đích, NOTES/NEWS và chạy thử.

### 6.2. Vì sao compaction có thể làm mất khả năng rollback?

~~~text
Trước khi nâng cấp:
  4.1 node -> SSTable BIG version nb
  Snapshot trước nâng cấp -> lưu bộ file nb

Trong giai đoạn nâng cấp:
  5.0 node còn tương thích 4.x -> vẫn đọc được nb

Sau khi bật tính năng format/storage mới:
  Flush hoặc compaction -> SSTable version mới (ví dụ oa / da)

Thử chạy lại 4.1 trên data directory mới:
  Reader 4.x không biết version mới -> không phải rollback hợp lệ
~~~

**Compaction rewrite dữ liệu**, vì vậy thời điểm bật tính năng tạo format mới quan trọng không kém thời điểm chạy `nodetool upgradesstables`. Ngoài compaction, flush hoặc file streaming từ node đã cập nhật cũng cần xem xét theo chính sách phiên bản.

## 7. Storage compatibility mode của Cassandra 5.0

Cassandra 5.0 đưa ra tham số `storage_compatibility_mode` để triển khai dần tính năng on-disk và messaging mới khi nâng cấp từ Cassandra 4.x. Trong cấu hình tương thích của 5.0, chế độ mặc định là `CASSANDRA_4`.

| Chế độ | Ý nghĩa vận hành | Thời điểm phù hợp |
|---|---|---|
| `CASSANDRA_4` | Giữ compatibility với dòng 4.x cho các thành phần do mode quản lý: format file, commit log/hints và tính năng liên quan; chưa bật hành vi mới gây mất tương thích | Giai đoạn rolling binary upgrade ban đầu |
| `UPGRADING` | Chế độ trung gian: cluster theo dõi trạng thái từng node và chỉ kích hoạt hành vi mới sau khi đã đáp ứng điều kiện version của toàn cụm | Khi toàn bộ binary đã ổn định, tiến hành chuyển trạng thái có kiểm soát |
| `NONE` | Bỏ ràng buộc tương thích với 4.x để dùng các tính năng/storage mới phù hợp 5.0 | Sau khi xác định không còn rollback theo cách cũ |

Mô hình quy trình:

~~~text
Tất cả node 4.x
      |
      | backup/snapshot, kiểm tra bản nâng cấp được hỗ trợ
      v
Rolling binary upgrade lên Cassandra 5.0
      |
      | storage_compatibility_mode = CASSANDRA_4
      | kiểm thử ứng dụng, node, repair, compaction
      v
Rolling restart tất cả node với UPGRADING
      |
      | Đợi điều kiện kích hoạt tính năng mới toàn cluster
      v
Rolling restart tất cả node với NONE
      |
      v
Được phép dùng các định dạng/tính năng mới phù hợp phiên bản
      |
      | cân nhắc chọn bti, rewrite SSTable theo runbook riêng
      v
Đánh giá ổn định, disk, latency và phương án khôi phục
~~~

Đây là **minh họa của chuỗi chế độ**, không phải runbook đủ để copy thẳng vào mọi cluster. Thứ tự và bước thực thi phải theo hướng dẫn đúng minor release, đúng cấu hình hiện hành; đặc biệt không bắt đầu ép chuyển định dạng trên cluster còn node 4.x hoặc còn cần quyền rollback.

Ví dụ biểu diễn tham số:

~~~yaml
# cassandra.yaml, một trong các chế độ của Cassandra 5.0
storage_compatibility_mode: CASSANDRA_4

# Sau khi hoàn tất bước rolling upgrade và kiểm chứng,
# có kế hoạch riêng để chuyển toàn cụm qua UPGRADING rồi NONE.
~~~

**Chi tiết điển hình:** Cassandra 5.0 còn thay đổi thời gian xóa tối đa (deletion time) để mở rộng giới hạn TTL sang năm 2106 khi tính năng storage mới được kích hoạt; ở chế độ tương thích 4.x, giới hạn cũ năm **2038** tiếp tục áp dụng. Đây là ví dụ cho thấy một thay đổi on-disk có thể ảnh hưởng **ngữ nghĩa dữ liệu**, không chỉ tốc độ đọc.

### 7.1. Quan hệ với `sstable.selected_format`

Hai tham số giải quyết hai vấn đề khác nhau:

1. `storage_compatibility_mode` đặt **ranh giới khả năng tương thích** của hệ thống khi nâng cấp.
2. `sstable.selected_format` chọn **triển khai SSTable cho file được tạo mới** (`big` hoặc `bti` trên Cassandra 5.0).

Không chọn BTI trên một node chỉ vì đã thấy tên tham số trong `cassandra.yaml`. Cần bảo đảm **mọi node liên quan hỗ trợ format**, các chế độ tương thích đã chuyển đúng theo runbook và kế hoạch rollback cho phép thao tác đó.

**Lưu ý:** Các bản phân phối và tệp `cassandra.yaml`/`cassandra_latest.yaml` có mặc định khác nhau; có thể cấu hình không được khai báo thì áp dụng mặc định tương thích. Đừng suy trạng thái thực từ một dòng cấu hình đang bị comment.

## 8. Công cụ thao tác định dạng SSTable

### 8.1. `nodetool upgradesstables` — rewrite trên node đang chạy

Trong Cassandra 5.0, lệnh:

~~~bash
# Trên node cần cập nhật, chỉ định đúng keyspace/table.
nodetool upgradesstables -- sstable_lab events

# -a: bao gồm cả SSTable đang ở current version.
nodetool upgradesstables -a -- sstable_lab events

# Có thể hạn chế số job đồng thời; kiểm tra help của version đang dùng.
nodetool upgradesstables -j 1 -- sstable_lab events
~~~

Ý nghĩa:

- **Không có `-a`:** chọn SSTable chưa ở phiên bản đích hiện tại mà node xác định phải nâng cấp.
- **`-a` / `--include-all-sstables`:** bao gồm cả các SSTable đang ở *current version*; có thể hữu ích khi chủ đích rewrite toàn bộ theo cấu hình hiện tại nhưng **tăng đáng kể chi phí I/O**.
- **`-j`:** giới hạn số SSTable xử lý đồng thời, tùy engine/phiên bản; `-j 0` có thể sử dụng tất cả compaction thread và không phải mặc định nên chọn cho production.
- Đây là lệnh **cục bộ theo node**; chỉ chạy trên một node không có nghĩa các replica khác đã chuyển định dạng.
- Nó **ghi lại file** theo format/version mà binary và cấu hình hiện hành cho phép; không đổi CQL schema, replication factor hay partition key.

**Quan trọng:** `upgradesstables` không phải phương tiện cứu node đang khởi động lỗi do nó không đọc được format file. Lệnh chạy qua `nodetool` khi node đang hoạt động, phải có headroom đĩa/CPU/I/O và phải nằm trong kế hoạch nâng cấp đúng phiên bản. Không kích hoạt rewrite đại trà trong lúc cluster vẫn ở rolling upgrade và còn dự tính rollback.

### 8.2. `sstableupgrade` — công cụ offline

Apache Cassandra cũng cung cấp công cụ standalone `sstableupgrade` để rewrite SSTable của bảng hoặc snapshot bằng binary được cài đặt:

~~~bash
# Chỉ sau khi đã dừng Cassandra trên node lab và sao lưu.
sstableupgrade sstable_lab events
~~~

**Phải dừng Cassandra** trước khi chạy công cụ standalone. Tài liệu Apache cảnh báo việc dùng các công cụ SSTable offline trong khi daemon còn chạy có thể gây kết quả không dự đoán được. `sstableupgrade` cũng hỗ trợ chuyển đổi SSTable của **snapshot** trong những trường hợp cần restore qua major version, nhưng cách dùng phải theo tài liệu của binary đích và kế hoạch backup.

Đừng nhầm:

| Lệnh | Dùng khi nào? | Phạm vi |
|---|---|---|
| `nodetool upgradesstables` | Node đang chạy, muốn rewrite SSTable được chọn | Trên node được gọi, các bảng chỉ định |
| `sstableupgrade` | Node **đã dừng**, thao tác offline với SSTable/snapshot | Bảng hoặc snapshot cục bộ |
| `nodetool compact` | Cần compaction theo yêu cầu | Hợp nhất SSTable theo kế hoạch compaction; **không** là migration format được kiểm soát đầy đủ |
| `nodetool repair` | Dữ liệu các replica không đồng bộ | Chuyển/chữa dữ liệu giữa replica; **không** có mục tiêu đổi format mọi SSTable |
| `nodetool flush` | Cần ghi memtable thành SSTable | Chỉ dữ liệu đang trong memtable; không rewrite SSTable cũ |

### 8.3. Công cụ quan sát an toàn và công cụ cần tắt node

~~~bash
# Lấy thông tin server và sức khỏe cluster.
nodetool version
nodetool status
nodetool tablestats sstable_lab
nodetool compactionstats

# Kiểm tra trạng thái SSTable qua JMX trên node đang chạy.
nodetool verify sstable_lab events
~~~

`nodetool verify` có thể tốn I/O khi xác minh file, nên không coi đây là lệnh kiểm tra vô hại ở mọi tải. Để xem chi tiết metadata của SSTable bằng `sstablemetadata` hoặc xác minh offline bằng `sstableverify`, cần **dừng Cassandra trên node** trước:

~~~bash
# Chỉ sau khi dừng Cassandra ở node lab, và xác nhận data directory thật.
sstablemetadata /path/to/oa-12-big-Data.db

# Khi đã kiểm tra rủi ro của bản công cụ:
sstableverify --help
~~~

`sstablemetadata` cho biết các trường như partitioner, min/max timestamp, token range, compression ratio, repaired-at, pending-repair, compaction level, TTL và thống kê tombstone. `sstableverify` có cảnh báo về rủi ro thay đổi repaired state khi verification thất bại; trên các bản mới có thể yêu cầu `--force` mới chạy. **Không** dùng `--force` như một thao tác mặc định cho production.

Các lệnh và tùy chọn thay đổi theo minor version. Trước mỗi lệnh thực thi thật, kiểm tra `nodetool help <command>` hoặc `<tool> --help` trên **binary đang chạy**. Trong bài này, các lệnh offline được đưa ra để học quy trình chứ **không được thực thi** trên cluster đang mở dịch vụ.

## 9. Snapshot, streaming và restore có tự giải quyết tương thích không?

### 9.1. Snapshot không chuyển đổi SSTable

Snapshot Cassandra thường được tạo bằng hard link tới SSTable hiện có trên filesystem hỗ trợ. Khi node tiếp tục flush/compaction, snapshot giữ **phiên bản file tại thời điểm chụp**, không tự nâng cấp theo daemon. Hệ quả:

- Snapshot `nb` không tự thành `oa` hoặc `da` sau khi server đã lên Cassandra 5.0.
- Snapshot giữ dung lượng đĩa khi compaction muốn xóa file live cũ; phải tính dung lượng thực theo hard link.
- Restore snapshot vào binary khác cần kiểm tra **on-disk format**, schema và cả đường upgrade được hỗ trợ; trong một số trường hợp phải upgrade SSTable snapshot bằng công cụ offline.
- Snapshot không thay thế backup/restore đã kiểm chứng, vì backup còn cần tính tới schema, cấu hình, commit log và mục tiêu phục hồi RPO/RTO.

### 9.2. Streaming có thể truyền dữ liệu giữa node khác version, nhưng có giới hạn

Khi bootstrap, decommission, rebuild hoặc repair, Cassandra có thể stream dữ liệu giữa các node. Streaming **không tương đương sao chép thư mục SSTable bằng OS**: phải xét giao thức, reader/writer, version negotiation, SSTable components và trạng thái đích.

Một số đường streaming có thể truyền nội dung dữ liệu theo cách tái tạo thành SSTable phù hợp binary đích; nhưng không có cam kết **mọi node Cassandra 4.x** sẽ nhận trực tiếp **mọi file BTI 5.0**. Nếu tài liệu lộ trình nâng cấp quy định chỉ trộn một tập version trong rolling upgrade, hãy tuân thủ ranh giới đó.

Không dùng `scp`, `robocopy` hoặc copy file `Data.db` riêng lẻ để di chuyển partition giữa các replica. Điều phối bằng giao thức Cassandra/công cụ SSTable loader tương ứng với phiên bản và cách restore đã thử nghiệm.

### 9.3. Khi nào file bị “không tương thích”?

| Triệu chứng | Nguyên nhân nghi ngờ | Bước chẩn đoán |
|---|---|---|
| Node cũ không mở được SSTable mới | Version code `oa`/`da` không có reader trong binary cũ | Ghi lại tên file, binary, storage mode và lộ trình downgrade |
| Cùng daemon 5.0 có cả `nb` và `oa` | Còn file cũ từ trước upgrade, rewrite chưa phủ hết | Kiểm tra trạng thái nâng cấp và runbook; không xóa file vì tưởng “rác” |
| SSTable có `big` và `bti` trong một bảng | Đã chuyển selected_format; chưa rewrite toàn bộ | Đánh giá mức hỗ trợ và trạng thái compaction/upgradesstables |
| File `Data.db` có nhưng query báo thiếu component | Copy/restore thiếu `TOC.txt` hoặc index/component khác, hoặc corruption | Kiểm bộ file và log, không viết component tay |
| `sstablemetadata` báo không hiểu format | Chạy tool không cùng phiên bản với file hoặc dùng sai binary | Kiểm `nodetool version` và binary của tool; dùng công cụ đích được hỗ trợ |
| Latency tăng sau format migration | Nhiều file/index đang rewrite, cache ấm lại, disk bận | Xem compactionstats, disk I/O, GC, read latency và cache |
| Snapshot restore không đọc được | Snapshot chứa file format ngoài phạm vi reader đích | Lập kế hoạch convert/restore offline đúng version và kiểm dữ liệu |

## 10. Runbook chuyển định dạng khi nâng cấp Cassandra 4.1 → 5.0

Đây là **khung ra quyết định** cho một cluster phân tán đang sử dụng bảng theo query, nhiều replica, consistency level và compaction định kỳ. Các bước thực thi chi tiết phải khớp tài liệu nâng cấp đúng phiên bản, hệ điều hành và cấu hình thực tế.

### Bước 1 — Chốt phiên bản và nhu cầu

Trước khi làm bất kỳ thao tác rewrite nào, trả lời:

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Node đang chạy phiên bản nào? | `nodetool version` và danh sách binary trên từng node |
| SSTable hiện ở format/version nào? | Filename descriptor; thống kê một số file đại diện |
| Cluster có đang trộn phiên bản? | Inventory node/rack/DC, trạng thái rolling upgrade |
| Có cần rollback về 4.1 không? | Quy định cửa sổ rollback, backup/snapshot kiểm chứng |
| Đang ở storage compatibility mode nào? | `cassandra.yaml` từng node và quy trình cấu hình |
| Định chọn `big` hay `bti`? | Benchmark và `sstable.selected_format` đã review |
| Dung lượng còn đủ cho rewrite? | SSTable sống, snapshot, temporary compaction, disk free |
| Workload có SAI, TTL, nhiều tombstone, wide partition không? | Danh sách bảng/index, compaction strategy, các workload truy vấn |

Không chọn `bti` chỉ vì nó có tên “mới hơn”; hãy đo một workload có **nhiều partition, truy vấn clustering, hàng lớn** hoặc độ trễ đọc thực sự đang bị ảnh hưởng bởi primary index.

### Bước 2 — Giảm rủi ro trước khi đổi binary

1. Xác nhận mọi replica đủ khỏe, các hoạt động repair quan trọng đã hoàn tất và không có node đang bootstrap/decommission bất thường.
2. Lưu cấu hình, schema và version inventory; chụp snapshot trên các node theo quy trình backup; **thử restore** trên môi trường riêng.
3. Kiểm tra mức sử dụng đĩa hiện tại và dự trù **tạm thời giữ cả SSTable cũ và mới** trong lúc compaction/rewrite. Snapshot hard link có thể giữ file cũ lâu hơn.
4. Xác định thứ tự node nâng cấp theo DC/rack, mức CL của ứng dụng Java, ngưỡng lỗi/timeout và điều kiện dừng rollout.
5. Kiểm tra rõ **đường nâng cấp được hỗ trợ**. Nếu cluster ở 3.11, không tự suy rằng có thể nâng trực tiếp lên 5.0 bỏ qua các yêu cầu của 4.x.

### Bước 3 — Nâng binary, giữ compatibility

Theo lộ trình phù hợp Cassandra 5.0, nâng từng node từ 4.1 và khởi động ở chế độ `storage_compatibility_mode: CASSANDRA_4`. Trong giai đoạn này:

- Tránh kích hoạt tính năng mới cần format chỉ 5.0 mới hiểu.
- Không chạy `upgradesstables -a` đại trà và không chuyển BTI tùy tiện.
- Kiểm tra CQL CRUD, đọc theo partition key, latency, timeout, replication, node Up/Normal, repair/compaction và streaming.
- Ghi lại node đã nâng, SSTable version nhìn thấy và mọi lỗi loader. Có thể tồn tại **nhiều thế hệ SSTable**; điều đó không tự động là lỗi.

### Bước 4 — Quyết định điểm không quay lại theo kiểu cũ

Khi **tất cả** node đã lên phiên bản 5.0 tương thích, ổn định và người vận hành đã chấp nhận kết thúc giai đoạn rollback, chuyển toàn cluster qua `UPGRADING` rồi `NONE` bằng chuỗi rolling restart theo tài liệu Cassandra 5.0.

Từ đây, node có thể tạo thành phần/format không còn tương thích Cassandra 4.x. Cơ chế khôi phục là **runbook restore có backup/format hợp lệ**, không phải chỉ hạ gói binary.

### Bước 5 — Nếu cần BTI, đổi định dạng và rewrite có kiểm soát

Sau khi thỏa các điều kiện ở bước trước, triển khai `sstable.selected_format: bti` trên phạm vi định trước, theo quy trình thay đổi cấu hình và restart. Chọn một bảng/nhóm node thử nghiệm trước, đo:

- **Trước:** số SSTable, read latency p95/p99, CPU, disk read IOPS, cache hit, write latency, compaction backlog.
- **Trong:** tốc độ rewrite, disk free, temporary files, số file BIG/BTI, độ trễ dưới tải.
- **Sau:** format descriptor thực tế, độ đúng của truy vấn, latency/throughput và tốc độ compaction.

Để chủ động rewrite cả SSTable đã ở version hiện hành sau khi đổi format, có thể cân nhắc:

~~~bash
# Mẫu trên node được chọn, sau khi đã đổi cấu hình/hợp thức hóa mode.
nodetool upgradesstables -a -j 1 -- sstable_lab events
~~~

Đây là lệnh **tốn tài nguyên**. Một node được rewrite không đồng nghĩa tất cả replica cũng đã rewrite; phải theo dõi tiến độ độc lập trên từng node. Nếu mục tiêu chỉ là nâng các file **lỗi thời về version** thì không luôn cần `-a`.

### Bước 6 — Kiểm chứng toàn bộ phạm vi

Các tiêu chí hoàn thành:

1. Tất cả node liên quan đang chạy đúng server version, storage mode và selected_format dự kiến.
2. Mỗi node đã xử lý hết SSTable cần rewrite, không còn job lỗi hoặc backlog chưa được giải thích.
3. Trên các thư mục bảng liên quan, có thể giải thích mọi mã version/format còn lại; không giả định chỉ còn một kiểu file nếu vẫn có snapshot hoặc dữ liệu chưa rewrite.
4. Read/write với CL của ứng dụng Java vẫn thành công; kiểm tra dữ liệu viết **trước** và **sau** thay đổi, trên nhiều partition/token range.
5. Các chỉ số disk, CPU, p95/p99 latency, compaction, SSTable count, repair và read errors trở lại mức chấp nhận được.
6. Backup/restore mới được thử trên **binary và format đích**, bao gồm trường hợp lỗi một replica.

Một câu SELECT trả đúng một hàng chưa chứng minh toàn bộ dữ liệu đã chuyển định dạng hoặc không có corruption.

## 11. Bài thực hành trên cluster lab Cassandra 5.0

**Yêu cầu:** Cassandra 5.0 **lab một node** hoặc node thử nghiệm được phép thay đổi cấu hình, cqlsh và nodetool. Không thực hiện `upgradesstables` hoặc restart trên production trong bài thực hành. Các bước đọc tên file dưới đây minh họa trên Linux, cần dùng **đường dẫn data directory thực tế** của node lab.

### Bài 1 — Tạo hai thế hệ SSTable BIG

Để đơn giản, tạo keyspace RF=1 cho lab một node:

~~~sql
CREATE KEYSPACE IF NOT EXISTS sstable_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS sstable_lab.events (
  tenant_id text,
  event_time timestamp,
  event_id uuid,
  status text,
  payload text,
  PRIMARY KEY ((tenant_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO sstable_lab.events
  (tenant_id, event_time, event_id, status, payload)
VALUES (
  'team_a', '2026-11-20T09:00:00Z',
  11111111-1111-1111-1111-111111111111,
  'NEW', 'created'
);

INSERT INTO sstable_lab.events
  (tenant_id, event_time, event_id, status, payload)
VALUES (
  'team_a', '2026-11-20T10:00:00Z',
  22222222-2222-2222-2222-222222222222,
  'NEW', 'created'
);

SELECT event_time, event_id, status
FROM sstable_lab.events
WHERE tenant_id = 'team_a';
~~~

Yêu cầu flush trên node lab:

~~~bash
nodetool flush sstable_lab events
~~~

Tiếp tục UPDATE và ghi thêm hàng, tạo thế hệ thứ hai:

~~~sql
UPDATE sstable_lab.events
SET status = 'DONE'
WHERE tenant_id = 'team_a'
  AND event_time = '2026-11-20T09:00:00Z'
  AND event_id = 11111111-1111-1111-1111-111111111111;

INSERT INTO sstable_lab.events
  (tenant_id, event_time, event_id, status, payload)
VALUES (
  'team_b', '2026-11-20T11:00:00Z',
  33333333-3333-3333-3333-333333333333,
  'NEW', 'created'
);
~~~

~~~bash
nodetool flush sstable_lab events
nodetool tablestats sstable_lab
~~~

**Quan sát:** Thư mục bảng thường có ít nhất hai thế hệ file. Một thế hệ còn giữ giá trị `NEW` cũ của hàng `team_a`, thế hệ sau giữ `DONE`; CQL SELECT phải hợp nhất phiên bản. Không kết luận có hai **hàng sống** chỉ vì có hai file `Data.db`.

### Bài 2 — Phân loại file bằng tên

Chỉ liệt kê file, không đổi/xóa nội dung:

~~~bash
# Thay đường dẫn bằng data directory thật của node lab.
# Liệt kê thư mục bảng được cấp phép đọc.
find /var/lib/cassandra/data/sstable_lab/ -type f -name '*-Data.db'
~~~

Kết quả ví dụ (không phải output bắt buộc):

~~~text
/var/lib/cassandra/data/sstable_lab/events-<uuid>/oa-7-big-Data.db
/var/lib/cassandra/data/sstable_lab/events-<uuid>/oa-8-big-Data.db
~~~

Ghi các giá trị cho từng file:

| Descriptor | Version code | Generation | Format | Component |
|---|---|---:|---|---|
| `oa-7-big-Data.db` | oa | 7 | big | Data.db |
| `oa-8-big-Data.db` | oa | 8 | big | Data.db |
| `da-9-bti-Partitions.db` | da | 9 | bti | Partitions.db |

**Chú ý:** Nếu node 5.0 đang ở compatibility mode với 4.x, file có thể mang mã `nb` thay vì `oa`. Nếu cấu hình dùng BTI, có thể gặp `da` thay vì `oa`. Hãy ghi nhận **kết quả thật** và lý giải bằng cấu hình.

### Bài 3 — Xem metadata an toàn

Trên node **đã dừng** trong lab, đọc metadata một `Data.db`:

~~~bash
# Chạy sau khi dừng Cassandra trên node lab.
sstablemetadata /var/lib/cassandra/data/sstable_lab/events-<uuid>/oa-7-big-Data.db
~~~

Quan sát các trường, không cần trích toàn bộ:

- `Partitioner` và first/last token: file chứa khoảng dữ liệu nào.
- `Minimum timestamp`, `Maximum timestamp`: thời gian mutation, khác với thời gian tạo file theo filesystem.
- `Repaired at`, `Pending repair`: trạng thái repair quan trọng khi lập kế hoạch compaction/restore.
- `Compressor` và `Compression ratio`: ảnh hưởng kích thước/đọc block.
- `SSTable level`, thống kê tombstone, TTL: ảnh hưởng compaction và dọn dữ liệu.

Vì `sstablemetadata` là standalone tool, **không chạy trên node đang mở Cassandra** theo tài liệu Apache. Sau khi khởi động lại lab, có thể quan sát số SSTable/độ trễ bằng `nodetool tablestats`.

### Bài 4 — Thử chuyển BIG → BTI trên môi trường bỏ được

Chỉ thực hiện sau khi:

1. Xác minh Cassandra 5.0 và các điều kiện tương thích cho phép format mới.
2. Có snapshot/backup của môi trường lab; không cần rollback binary 4.x.
3. Đã đo số SSTable, trạng thái index, disk free và truy vấn CQL ban đầu.

Sửa `cassandra.yaml` trong lab:

~~~yaml
sstable:
  selected_format: bti
~~~

Áp dụng restart theo hướng dẫn đúng version. Sau đó có thể dùng `nodetool upgradesstables -a` **có giới hạn concurrency** trên bảng lab để tạo lại những file được chọn theo format được phép:

~~~bash
nodetool upgradesstables -a -j 1 -- sstable_lab events
~~~

Liệt kê file lại và quan sát descriptor mới. Trong khi rewrite, có thể tạm thời thấy cả BIG và BTI. Kết quả CQL của `team_a` và `team_b` **phải giữ nguyên về mặt logic**. Nếu metadata/format không chuyển như dự định, kiểm binary, mode, cấu hình, log và lệnh đã thực thi; không xóa thủ công file BIG để ép sự chuyển đổi.

~~~sql
SELECT event_time, event_id, status, payload
FROM sstable_lab.events
WHERE tenant_id = 'team_a';

SELECT event_time, event_id, status, payload
FROM sstable_lab.events
WHERE tenant_id = 'team_b';
~~~

**Kỳ vọng:** `team_a` có hai event, trong đó event `1111...` có status `DONE`; `team_b` có một event status `NEW`. Vị trí và tên file mới là hiện tượng lưu trữ, không được thay đổi kết quả dữ liệu CQL.

### Bài 5 — Phân tích tình huống rollback

Giả sử trước nâng cấp node dùng Cassandra 4.1 với file `nb-20-big-Data.db`. Sau nâng cấp 5.0 và chuyển BTI, node sinh `da-21-bti-Data.db`.

Hãy đánh giá:

- Có thể thay lại binary 4.1 rồi khởi động trực tiếp cùng data directory có `da` không? **Không coi là tương thích.**
- Có snapshot `nb` trước nâng cấp thì đã đủ chưa? **Chưa**: phải xét thời điểm dữ liệu, schema và thao tác restore phù hợp.
- Chạy `nodetool repair` có chuyển mọi file `da` thành `nb` không? **Không**: mục tiêu repair là đồng bộ replica.
- Thay `sstable.selected_format: big` trên 5.0 có tự chuyển file `da` về BIG không? **Không**: cần quy trình rewrite phù hợp, không có bảo đảm rollback binary.

### Bài 6 — Quan sát ảnh hưởng của compaction

Sau hai hoặc nhiều đợt flush, có thể chạy compaction chủ động **chỉ trong lab**:

~~~bash
nodetool compact sstable_lab events
nodetool compactionstats
~~~

Kiểm tra tên file mới và dữ liệu truy vấn. Nếu compaction chạy và hoàn thành, đầu ra mang định dạng mà node cấu hình/khả năng hiện tại hỗ trợ. Các file cũ có thể còn do snapshot hoặc reader giữ tham chiếu. Nếu lệnh không có việc cần làm, không suy ra cluster lỗi chỉ vì không thấy file mới.

## 12. Ảnh hưởng đến ứng dụng Java

Java Driver dùng **CQL qua native protocol**, không cần biết `Data.db`, `Index.db` hay `Partitions.db`. Khi nâng server hay đổi SSTable format, ứng dụng Java vẫn dùng schema CQL hiện có; cần kiểm thử vì hiệu năng, lỗi đọc, timeout và chính sách version cluster có thể thay đổi.

Ví dụ Cassandra Java Driver 4.x đọc một partition:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

public final class EventReader {
    // session được tạo và tái sử dụng theo vòng đời ứng dụng.
    public static ResultSet findByTenant(CqlSession session, String tenantId) {
        SimpleStatement query = SimpleStatement.builder(
                "SELECT event_time, event_id, status, payload " +
                "FROM sstable_lab.events WHERE tenant_id = ?")
            .addPositionalValue(tenantId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(100)
            .build();
        return session.execute(query);
    }
}
~~~

Trong lab RF=1, LOCAL_QUORUM chỉ cần một replica. Ở production nhiều DC, hãy chọn CL, local datacenter, retry, timeout và chính sách phân trang theo SLA; **đổi định dạng SSTable không thay thế thiết kế consistency**. Nên so sánh các chỉ số:

| Mức kiểm thử | Trước nâng cấp/đổi format | Sau nâng cấp/đổi format |
|---|---|---|
| Đúng dữ liệu | Cùng SELECT theo khóa phân vùng | Kết quả logic giống nhau, gồm UPDATE/DELETE/TTL |
| Hiệu năng đọc | p50/p95/p99, timeout, throughput | Đo cùng workload và cache warmup |
| Ghi và compaction | write p99, flush, compaction backlog | Không có write stalls hoặc disk đầy |
| Tính sẵn sàng | RF, CL, số node Up/Normal | Không mất replica hoặc lỗi schema/streaming |
| Restore | Backup và trình tự khôi phục cũ | Backup khôi phục được trên binary/format đích |

Nếu ứng dụng đang dùng SAI trên Cassandra 5.0, cần kiểm thêm tình trạng index/SSTable index sau rewrite. **BTI là primary SSTable index**, còn SAI là secondary index: mỗi lớp có thể tác động tới latency theo cách khác nhau.

## 13. Những ngộ nhận gây lỗi khi nâng cấp

| Nhận định sai | Điều đúng |
|---|---|
| “SSTable chỉ là một file Data.db.” | Một SSTable gồm **nhiều component** có chung descriptor. |
| “Mã oa là Cassandra 5.0.9.” | `oa` là **mã on-disk của BIG**, không phải patch version server. |
| “Cassandra 5.0 tự đổi mọi file cũ thành oa/da ngay khi restart.” | File cũ có thể vẫn tồn tại; rewrite cần flush/compaction/upgrade phù hợp. |
| “BTI và SAI là một.” | BTI đổi **primary SSTable index**; SAI là **secondary index CQL**. |
| “Đổi selected_format thành bti chắc chắn rollback được sang 4.1.” | Node 4.x không có BTI reader; cần tính storage mode và kế hoạch restore. |
| “-a nghĩa là tăng số replica.” | `upgradesstables -a` là **include all SSTables**, không liên quan RF. |
| “Repair sẽ chuyển định dạng mọi SSTable.” | Repair xử lý đồng bộ dữ liệu replica; format migration là mục tiêu khác. |
| “Copy Data.db sang node khác là restore.” | Thiếu components/schema/ownership và có thể khác format/version. |
| “Snapshot được tạo trước upgrade thì sau upgrade sẽ tự dùng format mới.” | Snapshot giữ bản file tại thời điểm chụp; cần kiểm version khi restore. |
| “SSTable 5.0 đọc được thì driver Java cũng không còn vấn đề tương thích.” | Tương thích on-disk và native protocol/CQL của driver là **hai trục khác nhau**. |
| “Nén, tombstone và repair metadata không ảnh hưởng format migration.” | Đây là các yếu tố phải giữ/kiểm chứng khi rewrite và khi khôi phục dữ liệu. |

## 14. Tự kiểm tra

**Câu 1.** Với tên file `nb-17-big-Statistics.db`, hãy chỉ ra bốn thành phần descriptor và cho biết số 17 **không** biểu diễn điều gì.  
**Gợi ý:** nb = on-disk version, 17 = generation/ID, big = format, Statistics.db = metadata; 17 không phải RF hay số dòng.

**Câu 2.** Tại sao UPDATE thành công không làm giảm ngay số SSTable?  
**Gợi ý:** Memtable và SSTable mới nhận mutation; SSTable cũ immutable, chỉ compaction mới hợp nhất được các thế hệ phù hợp.

**Câu 3.** Một bảng Cassandra 5.0 có cả `nb-3-big-Data.db` và `oa-4-big-Data.db`. Có chắc bị hỏng dữ liệu không?  
**Gợi ý:** Không; có thể là file qua các giai đoạn upgrade, cần kiểm storage mode và reader hỗ trợ.

**Câu 4.** BTI dùng cấu trúc nào để tìm partition và tra row trong wide partition?  
**Gợi ý:** `Partitions.db` và `Rows.db` thay cách index kiểu `Index.db`/`Summary.db` của BIG.

**Câu 5.** Vì sao bật `selected_format: bti` chưa đủ để tất cả file cũ thành BTI?  
**Gợi ý:** Cấu hình chọn format của **file sinh sau**, không sửa SSTable bất biến đã tồn tại.

**Câu 6.** Khi nào cần `nodetool upgradesstables -a` và vì sao phải dè chừng?  
**Gợi ý:** Khi cố ý rewrite cả file đang ở current version; chi phí disk, CPU, I/O và nguy cơ phá cửa sổ rollback.

**Câu 7.** Khác biệt giữa `nodetool upgradesstables` và `sstableupgrade` về trạng thái Cassandra là gì?  
**Gợi ý:** Một công cụ vận hành qua nodetool trên node đang chạy, công cụ standalone đòi dừng daemon.

**Câu 8.** Một snapshot chứa `da-12-bti-Data.db` có thể restore thẳng vào node Cassandra 4.1 không?  
**Gợi ý:** Không mặc định; node cũ không có BTI reader và cần runbook restore/format hợp lệ.

**Câu 9.** Tại sao đánh giá chuyển format phải nhìn cả `storage_compatibility_mode` và `sstable.selected_format`?  
**Gợi ý:** Một tham số giới hạn tính năng/format được phép vì rollback; tham số kia chọn triển khai SSTable mới.

**Câu 10.** Khi Java driver báo read timeout sau format migration, bạn điều tra điều gì trước khi tăng timeout?  
**Gợi ý:** Disk I/O, compaction/rewrite đang chạy, cache, số SSTable, node health, CL, query plan và latency theo percentile.

## 15. Tổng kết bằng sơ đồ

~~~text
Cassandra storage engine
  Commit log + memtable
         |
       Flush
         v
   SSTable bất biến
         |
         +-- BIG: Data.db + Index.db + Summary.db + ...
         |
         +-- BTI: Data.db + Partitions.db + Rows.db + ...
         |
   Compaction / SSTable rewrite
         |
         v
   SSTable mới ở format/version được phép

Compatibility:
  Đọc cũ bằng binary mới: chỉ trong phạm vi hỗ trợ.
  Đọc mới bằng binary cũ: KHÔNG giả định.
  Cassandra 5.0: storage compatibility mode quyết định ranh giới,
                 selected_format chọn BIG/BTI cho file được tạo.
  Snapshot/restore: lưu và kiểm phiên bản file thực tế.
~~~

Quy tắc học thuộc: **“SSTable immutable, descriptor có version và format riêng, file được thay khi rewrite, còn khả năng rollback phụ thuộc storage mode và backup được kiểm chứng.”** Đây là nền tảng để vận hành Cassandra phân tán với đúng mức nhất quán đọc/ghi, repair/compaction và hiệu năng Java ổn định.

## Tài liệu tham khảo

- [Apache Cassandra 5.0 — Storage Engine: SSTable components, versions, BIG/BTI](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html) — cấu trúc SSTable, mã `ma`/`nb`/`oa`/`da` và primary index.
- [Apache Cassandra 5.0 — cassandra.yaml configuration](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html) — `storage_compatibility_mode`, `sstable.selected_format` và khác biệt cấu hình tương thích/`cassandra_latest.yaml`.
- [Apache Cassandra 5.0 — nodetool upgradesstables](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/upgradesstables.html) — `-a`, `-j`, scope và cách rewrite.
- [Apache Cassandra 5.0 — sstableupgrade offline](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/sstable/sstableupgrade.html) — rewrite bảng/snapshot và yêu cầu dừng daemon.
- [Apache Cassandra 5.0 — sstablemetadata](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/sstable/sstablemetadata.html) — đọc token range, timestamp, tombstone, repaired state, compression và compaction level.
- [Apache Cassandra 5.0 — sstableverify](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/sstable/sstableverify.html) — cảnh báo khi chạy offline và xác minh dữ liệu.
- [Apache Cassandra NEWS](https://github.com/apache/cassandra/blob/trunk/NEWS.txt) — hướng dẫn snapshot trước nâng cấp, tương thích định dạng theo chiều nâng/hạ và các giai đoạn major upgrade.
- [Apache Cassandra CASSANDRA-14092 — TTL expiration and storage compatibility](https://github.com/apache/cassandra/blob/trunk/CASSANDRA-14092.txt) — mốc 2038/2106, `CASSANDRA_4`/`UPGRADING`/`NONE`.
- [Apache Cassandra CEP-25 — Trie-indexed SSTable format](https://cwiki.apache.org/confluence/display/CASSANDRA/CEP-25%3A+Trie-indexed+SSTable+format) — bối cảnh thiết kế BTI và kế hoạch chuyển đổi từ BIG.

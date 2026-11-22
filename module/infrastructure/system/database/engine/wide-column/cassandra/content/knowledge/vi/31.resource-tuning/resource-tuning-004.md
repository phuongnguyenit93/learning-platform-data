# Bộ nhớ đệm, compression chunk và tập dữ liệu thường truy cập

> **Chương:** Tối ưu tài nguyên  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra, hệ cơ sở dữ liệu phân tán theo mô hình wide-column; tập trung vào khóa phân vùng, bảng thiết kế theo truy vấn, nhất quán đọc/ghi và vận hành CQL, replication, compaction, repair, xử lý lỗi, kết nối Java.

Khi truy vấn Cassandra chậm, tăng kích thước cache hoặc giảm `chunk_length_in_kb` thường là những thay đổi đầu tiên được nghĩ tới. Nhưng **cache nào đang thiếu**, **đọc dữ liệu gì**, và **mỗi lần đọc phải giải nén bao nhiêu byte** mới là những câu hỏi quyết định. Một workload đọc đi đọc lại vài partition nhỏ khác xa workload đọc ngẫu nhiên hàng triệu partition; thay đổi compression chunk có thể giảm read amplification cho workload thứ nhất nhưng tăng metadata hoặc chi phí compaction cho workload khác.

Bài này giải thích mối liên hệ giữa **tầng bộ nhớ đệm**, **compression chunk của SSTable** và **hot working set** — phần dữ liệu thực sự được truy cập thường xuyên. Mục tiêu là chọn cấu hình theo số liệu đọc/ghi, thay vì giả định “cache hit rate cao” hoặc “file nhỏ hơn” luôn dẫn đến p99 thấp hơn.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt `memtable`, `key cache`, `row cache`, `counter cache`, `chunk cache`, **OS page cache** và cache của ứng dụng Java.
2. Giải thích đơn vị `chunk_length_in_kb` trong nén SSTable và vì sao đọc một ô nhỏ có thể cần đọc/giải nén cả chunk.
3. Mô tả tác động của kích thước chunk tới **độ nén**, **CPU**, **I/O**, **metadata off-heap** và **độ trễ truy vấn**.
4. Ước lượng kích thước hot working set, nhận diện hot partition và cache thrashing bằng số liệu.
5. Lập thí nghiệm có đối chứng giữa chunk 4/16/64 KiB và các cấu hình cache, đo cả p50/p95/p99, I/O và chi phí ghi.
6. Vận hành đúng với Cassandra 3.11/4.x/5.x mà không sao chép các tham số đã đổi tên hoặc áp tùy chọn không được hỗ trợ.

## 2. Một truy vấn đi qua những tầng nào?

Đối với `SELECT` có **partition key đầy đủ**, coordinator chọn các replica dựa trên token, RF và consistency level; mỗi replica phục vụ đọc theo dữ liệu hiện có trong memtable, SSTable và các cấu trúc hỗ trợ. Mỗi node có cache **riêng**, không có một bộ đệm toàn cụm tự chia sẻ mọi kết quả truy vấn.

~~~mermaid
flowchart TD
    A["Ứng dụng Java / driver"] --> B["Coordinator và CL"]
    B --> C["Replica phục vụ đọc"]
    C --> D{"Dữ liệu mới trong memtable?"}
    D -->|Có phần cần đọc| E["Đọc và hợp nhất phiên bản"]
    D -->|Cần SSTable| F["Bloom filter + chỉ mục partition"]
    F --> G["KeyCache / index summary / index"]
    G --> H["Vị trí các SSTable và compression chunks"]
    H --> I{"Chunk uncompressed có trong ChunkCache?"}
    I -->|Hit| J["Dùng buffer đã giải nén"]
    I -->|Miss| K["OS page cache hoặc disk I/O"]
    K --> L["Đọc chunk nén và giải nén"]
    L --> J
    J --> E
    E --> M["Hợp nhất row/tombstone, phân trang"]
    M --> B
    B --> A
~~~

Sơ đồ là **mô hình khái niệm**: các bước chi tiết và short-circuit có thể khác theo phiên bản/định dạng SSTable, loại truy vấn, dữ liệu còn ở memtable và các cache được bật. `RowCache` nếu có thể phục vụ một phần dữ liệu sớm hơn đường đọc SSTable; không nên xem mọi request luôn đi qua đầy đủ từng nút trong hình.

### 2.1. So sánh các tầng bộ nhớ

| Tầng | Lưu gì? | Lợi ích chính | Điểm cần lưu ý |
|---|---|---|---|
| **Memtable** | Mutation mới trong bộ nhớ trước flush | Ghi nhanh, có thể phục vụ đọc dữ liệu chưa thành SSTable | Bộ đệm của đường ghi; không phải cache LRU được tăng tùy ý để giữ hot data |
| **Key cache** | Thông tin vị trí partition trong một số định dạng SSTable | Tránh một số lần tra chỉ mục/seek khi đọc cùng partition | **Không** lưu payload của tất cả hàng; hiệu lực phụ thuộc SSTable format |
| **Row cache** | Các hàng thuộc partition theo chính sách caching của bảng | Giảm đọc dữ liệu nền khi một tập hàng được truy vấn lặp lại | Tốn nhiều RAM/off-heap; cập nhật làm lợi ích suy giảm; mặc định thường tắt |
| **Counter cache** | Thông tin cục bộ phục vụ cập nhật counter | Giảm tranh chấp và một phần chi phí đọc trước ghi counter | Chỉ liên quan bảng counter; không thay thế key/row cache |
| **Chunk cache** | Buffer SSTable **đã giải nén** trong process Cassandra | Tránh đọc/giải nén lại vùng SSTable nóng | Tốn off-heap; muốn dùng phải kiểm tra `file_cache_enabled` và pool |
| **OS page cache** | Trang file vừa đọc ở bộ nhớ kernel | Tránh I/O vật lý khi dữ liệu trong trang còn nóng | Có thể chứa byte **nén** của SSTable; hit vẫn cần giải nén nếu ChunkCache miss |
| **Cache ứng dụng** | DTO/kết quả/giá trị nghiệp vụ ở Java hoặc Redis | Tránh gọi Cassandra cho dữ liệu phù hợp TTL/invalidation | Phải tự xử lý nhất quán và hết hạn; không phản ánh trong KeyCache hit rate |

Ngoài ra Cassandra dùng **Bloom filter** và **index summary** để tránh tra những SSTable không chứa partition hoặc định vị vùng chỉ mục nhanh hơn. Chúng cũng tiêu tốn bộ nhớ, nhưng không phải bản sao hàng dữ liệu như row cache. Khả năng dùng KeyCache khác nhau giữa định dạng SSTable truyền thống (ví dụ BIG) và các định dạng mới; cần kiểm tra format/phiên bản trước khi diễn giải metric.

### 2.2. Key cache hit cao vẫn có thể đọc disk nhiều

Ví dụ một endpoint thường xuyên đọc `device_id = X, event_day = D`. KeyCache biết nơi tìm partition trong SSTable nên có thể bỏ qua bước tra vị trí, nhưng **payload và các SSTable liên quan vẫn phải được đọc/hợp nhất**. Khi request gặp nhiều SSTable, tombstone hoặc dữ liệu chưa nằm trong OS/ChunkCache, disk I/O và độ trễ vẫn cao.

Vì vậy, `KeyCache.HitRate = 95%` (ví dụ giả định) **không** tương đương “95% truy vấn không đụng disk”. Muốn tìm nguyên nhân p99 còn cao, đối chiếu số SSTable mỗi lần đọc, OS disk metrics, ChunkCache miss, partition size và lượng tombstone được quét.

### 2.3. Row cache chỉ có ích với đúng mẫu truy vấn

Trong CQL, cấu hình ở **cấp bảng** cho phép:

~~~sql
WITH caching = {
    'keys': 'ALL',
    'rows_per_partition': 32
}
~~~

Theo tài liệu CQL, `keys` nhận `ALL` hoặc `NONE`; `rows_per_partition` có thể là `NONE`, `ALL` hoặc số lượng hàng. Nó quy định phạm vi dữ liệu được cache khi đọc partition, **không** cam kết mọi truy vấn luôn được trả trọn từ cache.

Thay đổi thuộc tính bảng chưa chắc đủ: **row cache còn cần ngân sách ở cấp node**, ví dụ `row_cache_size` trong cấu hình Cassandra 5.0; giá trị mặc định của tham số này là **0 (tắt)**. Các bảng ghi cập nhật thường xuyên, truy vấn nhiều range khác nhau hoặc có partition lớn có thể làm row cache tiêu tốn bộ nhớ mà tỷ lệ hit thấp. Cân nhắc row cache khi có **hot partition/row nhỏ, ít biến động và được đọc lặp lại**, rồi đo trước/sau.

## 3. Compression chunk là gì?

### 3.1. Khối nén nằm ở SSTable, không phải ở CQL result page

SSTable bất biến được chia thành các **chunk dữ liệu chưa nén** có kích thước mục tiêu `chunk_length_in_kb` rồi nén thành các block ghi trên disk. Mỗi chunk có metadata cho phép định vị; lúc đọc, Cassandra xác định các chunk chứa byte cần thiết, đọc **toàn bộ chunk nén liên quan** và giải nén để tìm dữ liệu.

Ví dụ một ô dữ liệu payload 300 byte nằm trong chunk không nén 16 KiB. Nếu không có cache hit, Cassandra có thể cần đọc và giải nén **chunk chứa ô đó**, tức lượng dữ liệu đưa qua codec lớn hơn payload người dùng nhận. Thực tế số byte **trên disk** phụ thuộc tỷ lệ nén; 16 KiB là kích thước trước nén, không phải cam kết I/O đúng 16 KiB. Một truy vấn có thể chạm nhiều chunk, nhiều SSTable hoặc dùng block đã có trong cache.

~~~text
SSTable trước nén, mô hình:
|------ chunk A 16 KiB ------|------ chunk B 16 KiB ------|
| ... record X (300 B) ...   | ... các record khác ...   |

Read record X, khi miss mọi cache phù hợp:
  định vị chunk A -> đọc bytes nén của A -> giải nén A -> tách record X

Nếu chunk A đã nằm trong in-process ChunkCache:
  có thể dùng buffer đã giải nén -> tiết kiệm I/O/codec tương ứng
~~~

Không nhầm ba loại kích thước:

- **`chunk_length_in_kb`:** kích thước dữ liệu **chưa nén** trên mỗi chunk SSTable.
- **Driver `page size`:** số hàng gợi ý tải mỗi trang kết quả; không điều khiển chunk nén.
- **Filesystem page/OS readahead:** cách kernel/thiết bị tải dữ liệu; có thể khiến lượng đọc thực lớn hơn vùng yêu cầu của Cassandra.

### 3.2. Đánh đổi giữa chunk nhỏ và chunk lớn

| Kích thước chunk | Điểm mạnh tiềm năng | Chi phí/rủi ro cần đo | Workload nên thử |
|---|---|---|---|
| **4 KiB** | Ít byte dư phải giải nén khi đọc hàng nhỏ, chọn lọc | Nhiều chunk, metadata/index và overhead codec cao hơn; có thể nén kém | Point read rất nhỏ và phân tán |
| **16 KiB** | Điểm xuất phát cân bằng trên Cassandra 4.x/5.x | Không chắc tối ưu khi hàng quá nhỏ hoặc scan rộng | Hỗn hợp point/range read |
| **64 KiB** | Nhiều ngữ cảnh nén hơn; thường có tỷ lệ nén tốt hơn với dữ liệu có tính lặp | Có thể phải đọc/giải nén nhiều byte thừa cho point read; tăng áp lực cache | Đọc các range liên tục, đọc nhiều hàng gần nhau |

Các con số chỉ là **biến thể thí nghiệm**, không phải xếp hạng cố định. Tài liệu Cassandra 5.0 nêu chunk mặc định là **16 KiB**, còn tài liệu nhánh cũ 3.x từng dùng **64 KiB**. Luôn kiểm tra schema thực tế bằng `DESCRIBE TABLE`; không suy ra chunk từ phiên bản hoặc giá trị mặc định khi bảng đã được tạo từ lâu.

Tình huống minh họa: một request lấy 1 hàng 400 byte ở vị trí ngẫu nhiên. 4 KiB có thể giảm phần dữ liệu phải giải nén so với 64 KiB. Ngược lại, lấy liên tiếp 100 hàng trong cùng partition có thể hưởng lợi từ chunk 64 KiB vì ít lần định vị và codec hơn; **cache hit, kích thước hàng, compression ratio và SSTable count** quyết định kết quả cuối cùng.

### 3.3. Chọn codec cùng lúc với chunk

Các codec thường gặp trong Cassandra:

| Codec | Đặc tính khái quát | Khi nào cân nhắc |
|---|---|---|
| `LZ4Compressor` | Nén/giải nén nhanh, cân bằng CPU và tỷ lệ | Baseline tốt cho nhiều workload nhạy latency |
| `ZstdCompressor` | Có thể nén tốt hơn, mức CPU phụ thuộc cấu hình | Khi dung lượng/disk bandwidth đáng kể, cần benchmark |
| `SnappyCompressor` | Codec cũ vẫn được hỗ trợ | Tương thích hoặc baseline với cụm đang dùng |
| `DeflateCompressor`/LZ4HC | Có thể tăng tỷ lệ nén, thường tốn CPU nén hơn | Chỉ chọn khi đo đủ CPU và write/compaction overhead |

**Đừng tách riêng lựa chọn chunk khỏi codec.** Kết quả “64 KiB giảm disk” có thể đến từ tỷ lệ nén tốt hơn nhưng p99 tăng vì giải nén nhiều byte và compaction tốn CPU. Nếu dữ liệu đã nén hoặc ngẫu nhiên, tăng chunk thường không tạo lợi ích nén đáng kể.

### 3.4. Metadata và chi phí RAM ngoài heap

Mỗi SSTable nén cần metadata ánh xạ chunk sang offset, kích thước và checksum. Khi chunk nhỏ hơn, cùng một dung lượng dữ liệu thường có **nhiều chunk hơn**, metadata và quản lý buffer có thể tăng. Tài liệu vận hành Cassandra 5.x lưu ý compression metadata dùng **off-heap RAM** và tăng theo dung lượng disk.

Một thay đổi từ 64 KiB xuống 4 KiB có thể làm số chunk lý thuyết **tăng 16 lần** với cùng lượng dữ liệu trước nén; không có nghĩa RAM metadata hay I/O tăng chính xác 16 lần. Tỷ lệ nén, tổ chức SSTable và các cấu trúc đi kèm khiến chi phí thực khác nhau.

Vì vậy, bên cạnh heap/GC cần quan sát **RSS, direct/off-heap memory, OS page cache, free RAM và swap**. Không nên cấp hết RAM cho cache Cassandra mà làm kernel thiếu bộ nhớ đệm file.

## 4. Hot working set: chính xác dữ liệu nào cần nằm trong cache?

### 4.1. Làm rõ “tập dữ liệu thường truy cập”

**Working set** là tập khóa/phân vùng/chunk mà một workload cần trong một khoảng thời gian đo cụ thể. **Hot working set** là phần nhận tỷ lệ truy cập lớn nhất. Nó thay đổi theo thời gian, loại truy vấn và node được định tuyến:

- Một dashboard đọc 500 thiết bị nổi bật mỗi phút có thể truy cập đi truy cập lại cùng partition/chunk.
- Một job báo cáo quét dữ liệu cả năm có thể đọc **rất nhiều dữ liệu lạnh**; cache kích thước nhỏ không làm scan trở thành truy vấn nóng.
- Một hệ thống IoT ghi liên tục vào vài thiết bị có thể tạo **hot partition**. Dù các chunk liên quan vào cache, nhóm replica sở hữu partition vẫn bị quá tải do CPU, mạng hoặc compaction.
- Với RF=3, mỗi replica có cache riêng. Một partition hot được nhiều replica phục vụ có thể làm các working set **trùng lặp giữa node**, phụ thuộc CL và cách chọn replica.

Sử dụng “top 1% khóa chiếm 60% lưu lượng đọc” là một **giả thuyết cần đo**, không được suy từ histogram keycache tổng thể. Cần sampling/telemetry từ ứng dụng về tenant/device, khối lượng dữ liệu/hàng và thời gian, đồng thời tránh log raw key có thông tin nhạy cảm.

### 4.2. Ước lượng đủ chặt để ra quyết định

Giả sử trên **một replica**, trong cửa sổ 15 phút có 120.000 partition được đọc nhiều lần. Trung bình mỗi partition có khoảng 8 KiB dữ liệu **chưa nén thực sự cần** cho các truy vấn nóng. Ước lượng rất thô:

~~~text
Working set logic nóng ≈ 120.000 × 8 KiB
                      ≈ 937,5 MiB
~~~

Kết quả này **không** có nghĩa 1 GiB row cache sẽ đạt 100% hit:

1. Row cache có overhead, giới hạn số hàng được cache, eviction và invalidation khi ghi.
2. Một partition có thể trải qua nhiều SSTable, chunk phải chứa thêm byte lân cận, metadata và tombstone.
3. ChunkCache giữ buffer theo **chunk**, không theo “8 KiB hữu ích của partition”; nếu đọc rải rác, footprint thực có thể lớn hơn nhiều.
4. OS page cache cạnh tranh RAM với heap/off-heap; hot set còn thay đổi theo giờ và phụ thuộc phân bố khóa giữa node.

Một mục tiêu hữu ích là tìm xem **tỷ lệ request/byte truy cập lặp lại trong khoảng Δt** có thể nằm vừa trong ngân sách cache hay không. Ví dụ cache 1 GiB không tạo nhiều lợi ích nếu mỗi request đụng vùng dữ liệu 4 GiB hoàn toàn mới mà không lặp lại trong thời gian đủ ngắn.

### 4.3. Skew, churn và cache thrashing

| Hiện tượng | Tín hiệu | Ý nghĩa khi tuning |
|---|---|---|
| **Hot set nhỏ, lặp lại** | Cache hit tăng sau warm-up; disk read giảm, p99 giảm | Ưu tiên cache đúng loại, giữ đủ headroom |
| **Hot set lớn hơn cache** | Hit dao động, eviction/occupancy cao, disk I/O vẫn lớn | Mở rộng cache có thể không kinh tế; xét query/model |
| **Churn** (hot keys thay đổi liên tục) | Cache warm ngắn, lúc nào cũng miss nhiều | Cần đo theo giờ/ngày thay vì snapshot |
| **Hot partition đơn lẻ** | Một vài partition/hot replica chậm dù hit tốt | Chia bucket/shard, thay đường đọc/ghi, không chỉ tăng RAM |
| **Scan lớn làm đẩy cache nóng ra** | Sau batch job, p99 request nghiệp vụ tăng | Cô lập tài nguyên/job, điều tiết scan, lựa chọn window |
| **Tombstone/SSTable chồng lấn** | SSTables per read và tombstones scanned cao | Xem write pattern, TTL, compaction/repair; cache không giải quyết hết |

## 5. Cấu hình cache trong CQL và cassandra.yaml

### 5.1. Cấp bảng: key/row cache và compression

Đây là ví dụ CQL cho Cassandra 4.x/5.x:

~~~sql
CREATE TABLE example_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND caching = {'keys': 'ALL', 'rows_per_partition': 'NONE'}
  AND compression = {'class': 'LZ4Compressor', 'chunk_length_in_kb': 16};
~~~

Sau này có thể sửa riêng policy:

~~~sql
ALTER TABLE example_by_device_day
WITH caching = {'keys': 'ALL', 'rows_per_partition': 32};

ALTER TABLE example_by_device_day
WITH compression = {'class': 'LZ4Compressor', 'chunk_length_in_kb': 4};
~~~

**Hai lệnh ALTER khác nhau về thời gian có tác dụng:**

- Chính sách caching ảnh hưởng cách hệ thống xử lý các truy vấn tiếp theo, nhưng dữ liệu cache không tức thì được làm nóng hoặc có hiệu quả nếu ngân sách cache ở node bằng 0.
- **SSTable bất biến**, nên thay đổi `compression` chỉ chi phối dữ liệu SSTable được **ghi lại về sau** (flush/compaction/rewrite). Các SSTable cũ vẫn dùng cấu hình nén của chúng cho đến khi được viết lại. Không đo “4 KiB vs 16 KiB” ngay sau một `ALTER` rồi kết luận khi toàn bộ file còn giữ chunk cũ.

Không cần tắt nén chỉ vì CPU tăng nhẹ: nén có thể làm giảm lượng disk I/O và network/streaming đáng kể. Đánh đổi cần được đo ở **cả đọc và ghi**, bao gồm compaction.

### 5.2. Cấp node: ngân sách cache và khác biệt phiên bản

Một số tên tham số **Cassandra 5.x** xuất hiện trong `cassandra.yaml`:

~~~yaml
# Chỉ minh họa tên khóa, không phải cấu hình production đề xuất.
# Kiểm tra bản phân phối/release đang chạy trước khi áp dụng.
key_cache_size: 100MiB
row_cache_size: 0MiB
file_cache_enabled: false
file_cache_size: 512MiB
~~~

**Không sao chép YAML này sang Cassandra 4.0**: tài liệu phiên bản cũ dùng tên có hậu tố đơn vị, như `key_cache_size_in_mb` và `row_cache_size_in_mb`. Hướng dẫn Cassandra mới đã đổi một số khóa sang dạng hỗ trợ đơn vị. Cần xem file cấu hình của bản đang chạy, quyền áp dụng/restart và điều kiện off-heap của chính phiên bản đó.

Theo tài liệu 5.x, `row_cache_size` mặc định là **0**; `file_cache_enabled` mặc định **false**. Khi bật, ChunkCache lưu các buffer SSTable **đã giải nén**; `file_cache_size` là ngân sách off-heap cho chunk cache **và buffer pooling**, không phải toàn bộ byte đều được cấp cho cache. Các con số minh họa trong YAML không có nghĩa cache nên có các kích thước ấy trên mọi máy.

Khi phân bổ RAM, giữ chỗ cho **JVM heap, memtable, Bloom filters/index summaries, metadata nén, networking/buffer pools và OS page cache**. Bật một cache off-heap lớn có thể giảm số trang OS giữ được, gây swap hoặc out-of-memory trong một workload khác.

### 5.3. Định dạng SSTable và tác dụng thực của cache

Với một số SSTable format (ví dụ BIG), KeyCache giúp tra partition đến offset nhanh hơn. Các định dạng SSTable mới hơn có thể sử dụng cấu trúc chỉ mục khác và **không dùng key cache theo cùng cách**. Vì vậy, trước khi tăng `key_cache_size`:

1. Xác nhận phiên bản và SSTable format thực sự của bảng.
2. Kiểm tra Cache Metrics có request/hit tăng hay không; nếu hoàn toàn không dùng loại cache này, tăng capacity không giúp ích.
3. Đối chiếu với LocalReadLatency, SSTables per read và disk I/O.

Không suy ra “tăng key cache giải quyết p99” chỉ từ một thông số hit rate.

## 6. Lab: ba kích thước compression chunk trên cùng dữ liệu

### 6.1. Điều kiện thí nghiệm

Chuẩn bị cluster Cassandra **lab cô lập**, cqlsh, nodetool và bộ tạo dữ liệu/Java client có thể đo latency. Ví dụ này giả định datacenter tên `dc1` có **ít nhất ba node**; kiểm tra bằng `nodetool status`. Nếu topology khác, sửa RF/DC của keyspace và CL trước khi thực hành.

Ghi nhận phiên bản với:

~~~sql
SELECT release_version FROM system.local;
~~~

Lưu ý `IF NOT EXISTS` sẽ **không thay đổi schema cũ**. Nếu đã tạo các bảng tên tương tự, kiểm tra định nghĩa thật hoặc dùng keyspace lab mới để tránh dữ liệu/chunk còn sót từ thí nghiệm trước.

### 6.2. Tạo ba bảng chỉ khác compression chunk

~~~sql
CREATE KEYSPACE IF NOT EXISTS lab_resource
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS lab_resource.events_4k (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND caching = {'keys': 'ALL', 'rows_per_partition': 'NONE'}
  AND compression = {'class': 'LZ4Compressor', 'chunk_length_in_kb': 4};

CREATE TABLE IF NOT EXISTS lab_resource.events_16k (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND caching = {'keys': 'ALL', 'rows_per_partition': 'NONE'}
  AND compression = {'class': 'LZ4Compressor', 'chunk_length_in_kb': 16};

CREATE TABLE IF NOT EXISTS lab_resource.events_64k (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND caching = {'keys': 'ALL', 'rows_per_partition': 'NONE'}
  AND compression = {'class': 'LZ4Compressor', 'chunk_length_in_kb': 64};
~~~

Ba bảng có cùng partition/clustering key, codec và cache policy. **Biến được chủ động thay đổi chỉ là chunk size.** Để thí nghiệm có ý nghĩa, nạp cùng tập dữ liệu logic vào từng bảng với cùng timestamp, phân bố khóa, kích thước payload, TTL và nhịp ghi; giữ RF/CL, compaction strategy và điều kiện cluster tương đương.

Nạp thử một hàng để xác minh cú pháp:

~~~sql
INSERT INTO lab_resource.events_16k (
    device_id, event_day, event_time, event_id, payload
) VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T08:30:00Z',
    285f4c95-6fc7-4950-9e3b-1250900aecea,
    'sample-0001'
);
~~~

Đây chỉ là dữ liệu kiểm tra. Khi so sánh A/B/C, **chính hàng logic này và các hàng khác phải có ở cả ba bảng**. Một hàng không thể tạo ra kết luận đáng tin cậy về compression ratio hoặc latency.

### 6.3. Hai nhóm truy vấn phải benchmark riêng

**Q1 — Point/range nhỏ, ít hàng của một partition:**

~~~sql
SELECT event_time, event_id, payload
FROM lab_resource.events_16k
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T09:00:00Z'
LIMIT 10;
~~~

**Q2 — Scan một vùng lớn hơn, tiêu thụ nhiều hàng/trang:**

~~~sql
SELECT event_time, event_id, payload
FROM lab_resource.events_16k
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time <  '2026-11-22T00:00:00Z';
~~~

Lặp lại hai query tương đương bằng cách thay **duy nhất tên bảng** `events_4k` / `events_16k` / `events_64k`, sử dụng các partition có dữ liệu tương đương. Với Q2, driver phải **tiêu thụ hết các trang** nếu mục tiêu là đo toàn bộ scan; không dừng ở trang đầu rồi báo latency.

### 6.4. Các trục dữ liệu và tải

| Trục | Các mức khảo sát | Vì sao quan trọng |
|---|---|---|
| Payload trung bình | 200 B; 2 KiB; 20 KiB | Đọc một hàng có thể vượt nhiều chunk |
| Kiểu payload | Văn bản lặp, JSON, dữ liệu đã nén/ngẫu nhiên | Compression ratio không giống nhau |
| Số hàng/partition | 10; 1.000; 100.000 | Tác động tới range read, scan và hot partition |
| Phân bố khóa | Phân bố đều; 1% key rất nóng | Hot set và cache thrash |
| Thời gian làm nóng | Cold-ish; warm ổn định | Tách disk/cache effect |
| Concurrency | 1; 16; 64 client (điều chỉnh theo máy lab) | Tail latency và CPU/IO saturation |
| Tỷ lệ read/write | Read-only; 90/10; 50/50 | Chi phí codec, flush và compaction |
| Page size | 50; 500 hàng | Network, paging và số lần gọi |

**Không gọi cold cache** chỉ vì vừa đổi tên bảng; OS cache và các buffer khác có thể còn dữ liệu tương tự. Nếu cần cold test thực sự, dùng quy trình lab có kiểm soát, nêu cách làm nóng/làm nguội và tránh reboot, drop cache hoặc ép compaction giữa lượt đo mà không ghi rõ ảnh hưởng.

### 6.5. Đo và đối chiếu trên từng node

Các lệnh thông tin:

~~~bash
nodetool status
nodetool info
nodetool tablestats lab_resource.events_4k
nodetool tablestats lab_resource.events_16k
nodetool tablestats lab_resource.events_64k
nodetool tablehistograms lab_resource events_16k
nodetool compactionstats
nodetool tpstats
~~~

Trong `nodetool tablestats`, xem **SSTable Compression Ratio**, kích thước lưu trữ, SSTable count, local read/write latency và thống kê partition. Có thể đo tương ứng `tablehistograms` cho hai bảng còn lại. Lệnh `nodetool info` có thể cho thông tin cache tóm tắt theo node; số metric chính xác còn tùy release.

Đối chiếu thêm JMX/monitoring theo tài liệu [Cassandra Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html):

| Nhóm metric | Giá trị cần đọc | Diễn giải đúng |
|---|---|---|
| `Cache.KeyCache.*` | `Hits`, `Requests`, `HitRate`, `Size`, `Capacity` | Hit index-position, **không** phải payload hit |
| `Cache.RowCache.*` | Hit rate, entries, size nếu đã bật | Hiệu quả lưu hàng nóng theo policy và ngân sách |
| `Cache.ChunkCache.*` | Hits, misses, miss latency, size nếu đã bật | Khả năng tránh đọc/giải nén chunk mới |
| `Table.*.SSTablesPerReadHistogram` | SSTable tham gia một lần đọc | Read amplification do nhiều SSTable |
| `Table.*.ReadLatency` | Độ trễ đọc ở replica theo bảng | Chưa bao gồm toàn bộ coordinator/client |
| `ClientRequest.Read.Latency` | Độ trễ coordinator | Có thể khác p99 đầu-cuối Java |
| OS CPU/GC/RSS/free RAM | Tải CPU, bộ nhớ heap/off-heap, áp lực RAM | Tránh dùng cache lớn làm swap |
| OS disk read IOPS/bytes/latency | Lượng và thời gian I/O vật lý | Đo tác động của chunk size dưới điều kiện cache giống nhau |

Tên metric có thể thay đổi theo phiên bản/exporter; coi bảng là **tên nhóm và ý nghĩa**, xác nhận tên thực qua JMX đang chạy. Metric cache ở **cấp node** không tự tách riêng từng bảng: thử ba bảng tuần tự hoặc cô lập workload để tránh đánh đồng hit của bảng A với bảng B.

### 6.6. Bảng kết quả để điền số thực

Không dùng giá trị giả định làm kết quả; ghi số được đo từ cluster:

| Biến thể | Q1 p50/p95/p99 (ms) | Q2 p50/p95/p99 (ms) | Disk read MiB/s | CPU % | Compression ratio | Hot cache hit | Timeout % |
|---|---|---|---:|---:|---:|---:|---:|
| LZ4 / 4 KiB | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ |
| LZ4 / 16 KiB | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ |
| LZ4 / 64 KiB | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ |

Thêm bảng riêng cho **write p95/p99, flush/compaction backlog, dung lượng disk, metadata off-heap**. So sánh cùng client driver/CL/partition size và concurrency, lặp nhiều lượt với thứ tự đảo A/B/C để giảm bias cache/compaction. Chỉ kết luận khi dữ liệu đầu vào, row count và điều kiện tải tương đương.

## 7. Thử row cache và ChunkCache: một biến mỗi lượt

### 7.1. Thí nghiệm row cache

Với hot set nhỏ và nhiều lượt đọc cùng các hàng đầu partition, thử ở **lab**:

~~~sql
ALTER TABLE lab_resource.events_16k
WITH caching = {'keys': 'ALL', 'rows_per_partition': 32};
~~~

Điều kiện: cấu hình `row_cache_size`/`row_cache_size_in_mb` trên node phải cấp ngân sách lớn hơn 0 ở bản tương ứng, theo quy trình quản trị và có khả năng restart/apply hợp lệ. So sánh chính sách `NONE` với `32` sau warm-up cùng truy vấn; đo **RowCache hit, RSS/off-heap và p99**, đặc biệt khi cập nhật một số hàng nóng.

Không dùng kết quả một phần mềm benchmark chỉ đọc để kết luận row cache tốt cho workload có rất nhiều ghi. Hãy chạy thêm pha cập nhật và đo cache invalidation, áp lực bộ nhớ, read/write latency.

### 7.2. Thí nghiệm ChunkCache

Tài liệu `cassandra.yaml` 5.x mô tả `file_cache_enabled` để bật **SSTable ChunkCache** và `file_cache_size` để giới hạn vùng off-heap cho chunk cache/buffer pool. Bật ở **cluster lab** có ngân sách RAM rõ ràng, so với trạng thái mặc định/tắt. Không kỳ vọng row cache và ChunkCache có cùng hiệu quả: một bên giữ hàng, một bên giữ **chunk SSTable đã giải nén**.

Ma trận nên có ít nhất:

| Kịch bản | RowCache | ChunkCache | Phân bố truy cập |
|---|---|---|---|
| A — baseline | Tắt | Tắt | Nhiều partition, read/write thực tế |
| B — row cache | Bật có giới hạn | Tắt | Ít hot partition, đọc lặp lại |
| C — chunk cache | Tắt | Bật có giới hạn | Nhiều point/range read lặp lại ở SSTable |
| D — kết hợp | Bật có giới hạn | Bật có giới hạn | Chỉ thử sau khi hiểu B/C và đủ RAM |

**Giữ nguyên chunk size** khi đo tác động của cache. Ngược lại, **giữ cache policy cố định** khi so sánh 4/16/64 KiB. Trộn cả hai thay đổi làm không thể biết nguyên nhân thắng/thua.

### 7.3. Khi cache “có hit” nhưng p99 vẫn xấu

Hãy kiểm tra lần lượt: query có thiếu partition key không, có đọc quá nhiều hàng/SSTable/tombstone không, partition nào quá nóng, đợi replica/CL bao lâu, GC/CPU disk ra sao, driver có giới hạn pool/paging không. Cache không giải quyết được:

- Truy vấn quét cả cluster do thiết kế bảng không theo access pattern.
- Đọc lượng payload lớn hơn network/CPU có thể xử lý.
- Write amplification/compaction nghẽn disk.
- Replica chậm hoặc mất kết nối khiến quorum phải chờ.
- Ứng dụng dùng paging/deserialize không hợp lý.

## 8. Java Driver: đo latency đúng với lượng dữ liệu thật

Trong Java Driver 4.x, prepared statement và paging cho phép đo workload sát ứng dụng. Ví dụ sau giả định đã có `CqlSession session` kết nối tới cluster và local DC phù hợp, trên bảng `events_16k` đã được nạp dữ liệu:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement prepared = session.prepare(
    "SELECT event_time, event_id, payload " +
    "FROM lab_resource.events_16k " +
    "WHERE device_id = ? AND event_day = ? " +
    "AND event_time >= ? AND event_time < ? LIMIT ?");

BoundStatement statement = prepared.bind(
        UUID.fromString("0f94e3b9-0b36-4930-91f2-606b44b5231b"),
        LocalDate.of(2026, 11, 21),
        Instant.parse("2026-11-21T08:00:00Z"),
        Instant.parse("2026-11-21T09:00:00Z"),
        1000)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(100);

long start = System.nanoTime();
ResultSet results = session.execute(statement);
long payloadChars = 0;
int rows = 0;
for (Row row : results) {
    String payload = row.getString("payload");
    if (payload != null) payloadChars += payload.length();
    rows++;
}
long elapsedNs = System.nanoTime() - start;
double elapsedMs = elapsedNs / 1_000_000.0;
// Ghi vào histogram: elapsedMs, rows, payloadChars, table variant, request key.
~~~

Quan trọng:

- Thời gian trên là **end-to-end để lấy hết kết quả đã lặp**, bao gồm các trang tiếp theo; nó không chỉ đo thời gian trang đầu. Nếu UI chỉ cần trang đầu, đo **một metric riêng**.
- `LIMIT 1000` giới hạn số hàng trả về; `setPageSize(100)` kiểm soát kích thước trang đọc, **không** thay đổi compression chunk. Một request có thể cần nhiều trang và nhiều chunk.
- Tính p50/p95/p99 trên **nhiều partition và nhiều lần lặp độc lập**. Tránh so một lần query warm với query khác cold.
- Khi đổi tên bảng trong prepared statement, tạo/prepared statement tương ứng; giữ cùng bind values, CL, page size, concurrent clients và payload thực.
- Nếu data skew cao, theo dõi latency theo nhóm **hot keys/cold keys** thay vì chỉ một p99 tổng.

## 9. Quy trình ra quyết định có kiểm chứng

~~~mermaid
flowchart TD
    A["Xác định mẫu truy vấn và SLO"] --> B["Đo hot working set, skew, disk, CPU, p99"]
    B --> C{"Bottleneck chính?"}
    C -->|Lookup partition| D["Đo KeyCache, SSTables/Read và format"]
    C -->|Lặp lại cùng hàng| E["Thử row cache có giới hạn"]
    C -->|Giải nén và đọc SSTable| F["Thử chunk size/ChunkCache"]
    C -->|Hot partition hoặc scan rộng| G["Chỉnh partition key, bucket, truy vấn"]
    D --> H["Benchmark đồng điều kiện"]
    E --> H
    F --> H
    G --> H
    H --> I{"p99, throughput, RAM, I/O, write đạt SLO?"}
    I -->|Đạt| J["Ghi cấu hình, metric và điều kiện kiểm chứng"]
    I -->|Chưa| K["Phân tích metric rồi đổi một biến"]
    K --> B
~~~

### 9.1. Giữ cấu hình có lợi cho toàn hệ thống

Khi chọn một thiết lập, lưu cùng báo cáo:

1. **Truy vấn chính:** tỷ lệ point/range/scan, điều kiện partition key, số hàng/trang và kích thước payload.
2. **Tập dữ liệu:** số partition, hot set theo thời gian, TTL/tombstone, tỷ lệ dữ liệu có khả năng nén.
3. **Môi trường:** Cassandra release, SSTable format, RF/CL, node/CPU/RAM/SSD, JVM heap, OS page cache, compaction strategy.
4. **Biến thay đổi:** chunk 4/16/64 KiB hoặc cache policy, chỉ một biến mỗi thí nghiệm.
5. **Đo cả hai chiều:** p50/p95/p99 đọc, throughput, read/write latency, flush/compaction, disk footprint, CPU, off-heap/RSS, lỗi.
6. **Khả năng quay lại:** lưu schema/cấu hình gốc, phạm vi rollout và cách giám sát; nhớ rằng compression thay đổi trên SSTable mới nên kết quả không lập tức đồng nhất.

Nếu p99 thấp hơn nhưng RSS tăng sát giới hạn, OS page cache mất nhiều hoặc write/compaction chậm, thay đổi có thể **không đáng triển khai**. Ưu tiên đánh giá SLO của sản phẩm và chi phí tài nguyên, không chỉ một tỷ lệ nén đẹp.

### 9.2. Các nhận định dễ sai

| Nhận định | Vì sao sai hoặc thiếu | Cách kiểm chứng |
|---|---|---|
| “KeyCache hit 99% nên disk không còn được đọc” | KeyCache không chứa payload; nhiều SSTable/chunk vẫn cần truy cập | So disk I/O, ChunkCache, SSTables per read |
| “Tăng row cache sẽ giúp mọi truy vấn” | Hot set có thể lớn, thay đổi nhiều, hàng cache nặng | So p99 và eviction/hit ở workload thật |
| “Chunk 4 KiB luôn nhanh nhất” | Scan lớn, codec/metadata overhead và compression ratio có thể xấu | Benchmark cùng data point và range |
| “Chunk 64 KiB luôn tiết kiệm disk” | Dữ liệu ngẫu nhiên/đã nén ít lợi ích, metadata và codec vẫn tiêu tốn | Đo compression ratio, disk footprint, CPU |
| “ALTER compression xong toàn bảng đổi ngay” | SSTable cũ bất biến và chỉ đổi khi được ghi lại | Kiểm tra metadata/SSTable sau compaction hợp lệ |
| “ChunkCache là OS page cache” | ChunkCache giữ buffer đã giải nén trong Cassandra, OS giữ trang file | Đọc metric hai tầng và RSS/disk |
| “Row cache đang bật vì đã đặt caching trong CQL” | Node có thể cấu hình row cache size = 0 | Kiểm tra YAML/JMX và cache entries |
| “Working set toàn cluster vừa RAM nghĩa là node nào cũng đủ” | Mỗi replica có dữ liệu/cache riêng, hot key có thể lệch | Đo per-node hot set và traffic |
| “Cache giải quyết hot partition” | Hot key vẫn có giới hạn CPU/IO/replica | Sửa thiết kế partition/bucket/shard |
| “p50 cải thiện nghĩa là đã tối ưu” | Tail latency, GC, compaction và lỗi có thể xấu hơn | So p95/p99, timeout, resource budget |

## 10. Bài tập thực hành

**Tình huống A — point read và chunk size.** Một bảng chứa hàng nhỏ 300 byte, truy vấn thường đọc 1–2 hàng ngẫu nhiên. Thử `LZ4 4 KiB` so với `LZ4 64 KiB`; hãy nêu hai metric ngoài p99 cần đo.

**Gợi ý:** disk bytes/read và CPU/decompression; thêm compression ratio, ChunkCache hit, SSTables per read và metadata/RSS. Chunk nhỏ **có thể** giảm read amplification, nhưng chưa đủ số đo để khẳng định thắng.

**Tình huống B — cache cao nhưng truy vấn vẫn chậm.** `KeyCache.HitRate` đạt 98%, `SSTablesPerReadHistogram` và disk read latency đều cao. Điều gì có thể đang xảy ra?

**Gợi ý:** KeyCache chỉ giúp tìm vị trí partition; payload có thể nằm ở nhiều SSTable/chunk, có tombstone hoặc bị miss OS/ChunkCache. Điều tra disk và compaction trước khi chỉ tăng key cache.

**Tình huống C — thay compression nhưng không thấy khác.** Vừa chạy `ALTER TABLE ... chunk_length_in_kb: 4` nhưng disk usage và latency gần như cũ. Tại sao?

**Gợi ý:** SSTable đã có vẫn giữ nén cũ; cần chờ file được ghi lại bởi flush/compaction hoặc quy trình rewrite phù hợp phiên bản. Không ép major compaction trên production chỉ để có số benchmark.

**Tình huống D — hot set 2 GiB, row cache 1 GiB.** Có 250.000 partition nóng, cache hit rate dao động và GC/OS cache pressure tăng. Có nên tăng row cache lên 3 GiB?

**Gợi ý:** không thể quyết định từ phép cộng đơn giản. Cần đo overhead, per-node distribution, tỷ lệ write/invalidation, memory headroom và p99. Có thể phải giảm payload, đổi partition/bucket hoặc chỉ cache phần read model thực sự hữu ích.

**Tình huống E — phiên bản khác nhau.** Runbook Cassandra 4.0 có `key_cache_size_in_mb`; môi trường 5.0 có `key_cache_size`. Hãy mô tả các bước kiểm tra trước khi chuyển cấu hình.

**Gợi ý:** xác nhận `release_version`, đọc `cassandra.yaml` và tài liệu tương ứng, xác định đơn vị/giá trị mặc định, SSTable format, ngân sách heap/off-heap, cách áp dụng và rollback; thử lab với metric.

### Checklist nộp bài lab

- [ ] Giải thích được chức năng khác nhau của KeyCache, RowCache, ChunkCache và OS page cache.
- [ ] Nêu được vì sao đọc một giá trị nhỏ có thể cần giải nén cả chunk SSTable.
- [ ] Đã xác minh release/version, tên DC, RF/CL và schema/caching/compression của ba bảng.
- [ ] Dữ liệu logic và điều kiện benchmark của 4/16/64 KiB tương đương.
- [ ] Có số p50/p95/p99, compression ratio, CPU, disk bytes, RSS/off-heap, write latency và lỗi.
- [ ] Có thí nghiệm hot/cold working set và phân bố khóa; không dùng một hot key duy nhất.
- [ ] Hiểu row cache cần cả chính sách CQL và ngân sách cấp node.
- [ ] Không suy kết quả compression ngay sau `ALTER TABLE` khi SSTable cũ chưa được viết lại.
- [ ] Chọn cấu hình theo SLO thực nghiệm và có kế hoạch theo dõi/rollback.

## 11. Tài liệu tham khảo

1. Apache Cassandra Documentation — [Storage Engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html): read path, SSTable, memtable, Bloom filter và các thành phần chỉ mục.
2. Apache Cassandra Documentation — [Compression](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compression.html): codec, chunk size, read amplification, chi phí metadata và thời điểm `ALTER TABLE` có tác dụng.
3. Apache Cassandra Documentation — [CQL Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): thuộc tính `caching` và `compression` của bảng.
4. Apache Cassandra Documentation — [cassandra.yaml](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): ngân sách cache cấp node, `file_cache_enabled` và off-heap.
5. Apache Cassandra Documentation — [Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): Cache Metrics, Table Metrics và ClientRequest Latency.
6. Apache Cassandra Documentation — [Configuration naming changes](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/configuration.html) và [Cassandra 4.0 cassandra.yaml](https://cassandra.apache.org/doc/4.0/cassandra/configuration/cass_yaml_file.html): khác biệt tham số theo phiên bản.
7. Apache Cassandra Documentation — [Production recommendations](https://cassandra.apache.org/doc/stable/cassandra/getting-started/production.html): I/O read ahead và kích thước compression chunk.

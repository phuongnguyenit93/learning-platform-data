# Ước lượng, đo thực tế và kiểm chứng giới hạn phân vùng

Một trong những quyết định ảnh hưởng mạnh nhất đến hiệu năng Apache Cassandra là chọn **partition key**. Khóa này xác định dữ liệu nào thuộc cùng một phân vùng logic và replica nào chịu trách nhiệm lưu, đọc và ghi phân vùng đó. Nếu một khóa gom quá nhiều hàng, cell hoặc byte, phân vùng có thể trở nên quá lớn; nếu khóa nhận lưu lượng tập trung, nó có thể trở thành **hot partition** ngay cả khi dữ liệu chưa nhiều.

Vì thế, câu hỏi “Một phân vùng Cassandra được phép lớn đến đâu?” không nên trả lời bằng một con số MB duy nhất. Cần đi qua **ba bước bổ sung cho nhau**:

1. **Ước lượng trước khi triển khai** từ lưu lượng, kích thước bản ghi, thời gian tồn tại và cách chọn khóa.
2. **Đo dữ liệu và tải thực tế** bằng thống kê bảng/SSTable, histogram, metrics, mẫu dữ liệu và các phép đo an toàn.
3. **Kiểm chứng giới hạn vận hành** qua thử tải với phân bố điển hình lẫn ngoại lệ, tiêu chí độ trễ, cảnh báo và quy trình điều chỉnh schema.

Bài học thuộc chương **Khóa và phân vùng** của module Apache Cassandra, đặt việc định cỡ phân vùng vào bối cảnh mô hình wide-column phân tán, CQL, replication, consistency level, TTL, compaction, repair, xử lý lỗi và kết nối ứng dụng Java.

Sau bài học, bạn có thể:

- Tính số **hàng**, số **giá trị/cell** và lượng **byte** dự kiến trong một phân vùng.
- Phân biệt **dung lượng logic**, **footprint vật lý trên mỗi replica** và **dung lượng toàn cluster**.
- Đọc kết quả `nodetool tablestats`, `nodetool tablehistograms` và các chỉ số liên quan đúng phạm vi.
- Phát hiện **phân vùng ngoại lệ**, **hot partition** và chi phí do tombstone dù số hàng còn sống thấp.
- Xây dựng bài thử tải, ngưỡng cảnh báo và tiêu chí đạt/không đạt cho thiết kế partition key.
- Chọn time bucket hoặc shard theo dữ liệu đo được, đồng thời giữ các truy vấn CQL/Java đúng khóa.

## 1. “Kích thước phân vùng” có nhiều ý nghĩa

Giả sử bảng lưu các bản đo của thiết bị:

```sql
CREATE TABLE measurements_by_device (
    tenant_id       text,
    device_id       uuid,
    measured_at     timestamp,
    measurement_id  uuid,
    temperature     double,
    humidity        double,
    payload         text,
    PRIMARY KEY (
        (tenant_id, device_id),
        measured_at,
        measurement_id
    )
) WITH CLUSTERING ORDER BY (
    measured_at DESC,
    measurement_id ASC
);
```

Trong schema này, partition key là **`(tenant_id, device_id)`**. Các giá trị `measured_at` và `measurement_id` là **clustering columns**, giúp định danh và sắp các hàng **bên trong** phân vùng. Thêm nhiều bản đo không tạo thêm partition keys nếu tenant và device không đổi.

```text
Partition ('acme', device-01)
│
├── (2026-11-21 08:15, M3) -> temperature, humidity, payload
├── (2026-11-21 08:10, M2) -> temperature, humidity, payload
├── (2026-11-21 08:05, M1) -> temperature, humidity, payload
│
└── ... hàng tháng hoặc nhiều năm dữ liệu ...
```

Mỗi lần thêm một **tổ hợp clustering key mới**, số hàng logic có thể tăng. Ngược lại, ghi lại **đúng toàn bộ primary key** là upsert vào cùng hàng logic, không tự tạo hàng thứ hai.

### Những đơn vị cần phân biệt

| Đại lượng | Nó trả lời câu hỏi gì? | Điều chưa nói lên |
| --- | --- | --- |
| **Số hàng logic** | Có bao nhiêu tổ hợp clustering key còn tồn tại? | Không cho biết payload lớn hay nhỏ. |
| **Số cell/giá trị** | Có bao nhiêu giá trị dữ liệu, phần tử collection, metadata liên quan? | Không tương đương số cột CQL khai báo. |
| **Byte payload logic** | Ứng dụng tạo bao nhiêu byte dữ liệu bản ghi? | Chưa tính key, overhead, nén, tombstone. |
| **Footprint SSTable trên một replica** | Dữ liệu chiếm bao nhiêu trên đĩa của replica ở trạng thái hiện tại? | Có thể chứa nhiều phiên bản, tombstone và chênh lệch do compaction. |
| **Footprint toàn cluster** | Cluster phải chứa bao nhiêu bản sao và overhead? | Không thể suy chính xác chỉ bằng payload × RF. |
| **Lưu lượng theo partition key** | Một khóa nhận bao nhiêu read/write mỗi giây? | Partition nhỏ vẫn có thể rất nóng. |

Nói “mỗi phân vùng tối đa 100.000 hàng” hoặc “mỗi phân vùng tối đa 100 MB” chỉ là **một giả định vận hành có điều kiện**, không phải chuẩn phổ quát cho mọi phiên bản và workload Cassandra.

## 2. Hiểu hàng, cell và byte trong mô hình wide-column

Một schema có năm cột thường **không có nghĩa** Cassandra lưu đúng năm cell vật lý cho mọi hàng. Một số cột có thể vắng mặt; collection không `frozen` có thể được biểu diễn qua nhiều cell; cập nhật/xóa có thể để lại tombstone; thông tin clustering key, row marker và metadata có chi phí riêng.

```sql
CREATE TABLE audit_events_by_user (
    tenant_id  text,
    user_id    uuid,
    event_day  date,
    created_at timestamp,
    event_id   uuid,
    action     text,
    attributes map<text, text>,
    details    blob,
    PRIMARY KEY (
        (tenant_id, user_id, event_day),
        created_at,
        event_id
    )
);
```

Ví dụ:

- 100.000 hàng có `action` ngắn, `details` trống và `attributes` nhỏ có footprint khác hẳn 100.000 hàng có `details` vài KiB.
- Một `map<text,text>` rất lớn có thể tạo ra nhiều cell cùng chi phí cập nhật, đặc biệt khi xóa phần tử thường xuyên.
- Một vài hàng chứa `blob` nhiều MiB có thể khiến phân vùng nặng mặc dù số hàng thấp.
- Nếu có static columns, giá trị static thuộc **phân vùng**, không cần nhân theo số hàng clustering khi lập ước lượng logic.

Để lập kế hoạch, có thể dùng mô hình gần đúng:

```text
Giá trị dữ liệu mỗi phân vùng
  ≈ số hàng × giá trị/cell trung bình trên một hàng
    + các giá trị static chung

Byte logic mỗi phân vùng
  ≈ số hàng × byte logic trung bình trên một hàng
    + byte static
```

Đây **không phải cách tính chính xác cell vật lý trong SSTable**. Mục đích là kiểm tra sơ bộ schema trước khi dùng số liệu quan sát và benchmark.

## 3. Công thức ước lượng số hàng theo thời gian

Với dữ liệu sự kiện hoặc chuỗi thời gian, bắt đầu từ **tốc độ tạo khóa mới**:

```text
N_rows ≈ R_unique × T_bucket

R_unique : số full primary keys mới mỗi giây
T_bucket : số giây trong một bucket
```

Nếu hệ thống sinh 100 request ghi/giây nhưng 30% là retry/upsert vào cùng khóa đã tồn tại, số **hàng logic mới** có thể thấp hơn 100/giây. Với workload append-only, mỗi event có full primary key riêng, số hàng mới thường gần bằng số event.

Nếu một thiết bị ghi **90 sự kiện/giây**, mỗi sự kiện có định danh mới:

| Khoảng thời gian | Số giây | Hàng logic dự kiến |
| --- | ---: | ---: |
| 1 phút | 60 | 5.400 |
| 15 phút | 900 | 81.000 |
| 1 giờ | 3.600 | 324.000 |
| 1 ngày | 86.400 | 7.776.000 |
| 30 ngày liên tục | 2.592.000 | 233.280.000 |

Nếu partition key chỉ là `(tenant_id, device_id)` và không giới hạn dữ liệu, lịch sử 30 ngày của thiết bị này có thể tích lũy **hơn 233 triệu hàng trong một partition**. Nếu partition key thêm bucket 15 phút, một partition chứa khoảng **81.000 hàng** theo mức trung bình giả định.

**Không chỉ tính trung bình.** Trong thực tế, một thiết bị hoặc tenant có thể tạo lưu lượng gấp 5–20 lần mức thông thường vào giờ cao điểm. Độ lớn **phân vùng ở tải đỉnh** có thể quan trọng hơn phân vùng trung bình.

### Tính tỷ lệ tăng trưởng khi có TTL

Giả sử bảng giữ dữ liệu bảy ngày bằng TTL. Điều này có thể giới hạn **hàng còn sống** trong khoảng retention, nhưng không bảo đảm footprint SSTable chỉ bằng đúng bảy ngày payload:

- TTL hết hạn sinh trạng thái xóa logic và có thể để lại tombstone.
- Dữ liệu cũ chỉ được dọn vật lý khi compaction và các điều kiện an toàn cho phép.
- Nếu partition key không có bucket thời gian, dù chỉ giữ dữ liệu sống bảy ngày, mọi hoạt động vẫn tập trung vào **một khóa** của thiết bị.
- Nếu ghi vào cùng partition với tốc độ rất cao, nó vẫn có thể **hot** trong từng giây.

## 4. Ước lượng byte: payload, khóa và overhead

Một mô hình lập ngân sách ban đầu:

```text
B_logical_estimated
    = N_rows × (B_payload_avg + B_key_and_row_overhead_assumed)
      + B_static

B_payload_avg
    = tổng byte payload mẫu / số hàng mẫu

B_key_and_row_overhead_assumed
    = giả định sơ bộ về clustering keys, row/cell metadata
      (chỉ dùng để dự báo, phải hiệu chỉnh bằng đo thực tế)
```

Cần lấy mẫu **phân bố kích thước payload**, thay vì chỉ một giá trị trung bình. Ví dụ ứng dụng ghi `text`/`blob` thường có một số sự kiện lớn hơn phần còn lại rất nhiều.

### Ví dụ chi tiết

Giả sử một loại thiết bị có:

- 90 event/giây, mỗi event có full primary key riêng.
- Bucket 15 phút.
- Payload trung bình từ mẫu là **600 byte/event**.
- Giả định thêm **200 byte/event** cho khóa và overhead logic dùng trong bài toán định cỡ.

```text
Hàng mỗi bucket:
    90 × 900 = 81.000

Payload:
    81.000 × 600 = 48.600.000 byte = 48,6 MB

Khóa + overhead giả định:
    81.000 × 200 = 16.200.000 byte = 16,2 MB

Tổng dự báo sơ bộ:
    64.800.000 byte = 64,8 MB ≈ 61,8 MiB
```

**Không coi 200 byte là overhead chuẩn của Cassandra.** Nó là giả định để minh họa phép tính; overhead vật lý thực tế phụ thuộc schema, kiểu dữ liệu, compression, phiên bản, cấu trúc SSTable và trạng thái compaction.

Nếu một thiết bị ngoại lệ đạt **5 lần** tốc độ này trong 15 phút, riêng dự báo trên đã thành khoảng **324 MB** trước khi xét lưu trữ vật lý. Vì vậy cần thiết kế cho phân bố tốc độ theo key và lập bảng kịch bản.

### Kịch bản theo phân vị

| Kịch bản | Event/giây | Hàng/bucket 15 phút | Byte dự báo theo 800 B/hàng |
| --- | ---: | ---: | ---: |
| Thiết bị điển hình | 90 | 81.000 | 64,8 MB |
| Thiết bị cao tải | 180 | 162.000 | 129,6 MB |
| Thiết bị ngoại lệ | 450 | 405.000 | 324,0 MB |
| Thiết bị cực đoan | 900 | 810.000 | 648,0 MB |

Bảng này **không phải histogram đo được**; chỉ là phân tích tình huống. Phân vị p95/p99 thật phải tính từ số liệu thực theo **các partition keys**, không suy ra bằng cách gắn nhãn tùy ý cho các mốc nhân tải.

## 5. Ba lớp dung lượng: logic, replica và cluster

Cassandra là hệ cơ sở dữ liệu phân tán và dùng LSM tree. Dữ liệu được ghi qua commit log/memtable, flush thành SSTable, rồi được tổ chức lại qua compaction. Một partition có thể hiện diện ở nhiều SSTable trước khi được hợp nhất về mặt lưu trữ.

Cần tách ba lớp:

1. **Logical data size:** các giá trị hiện hành mà mô hình dữ liệu đại diện.
2. **Replica on-disk footprint:** các SSTable, compression, index, cell metadata, tombstone và các phiên bản chưa compact mà một replica đang giữ.
3. **Cluster footprint:** bản sao trên nhiều replica cộng các chi phí vận hành theo node, compaction/streaming và trạng thái phân phối thực.

```text
Payload/row × số row
      |
      v
Ước lượng logic của một partition
      |
      +--> overhead, nén, tombstone, SSTable và compaction
      |          |
      |          v
      |    footprint của một replica (có thể thay đổi theo thời gian)
      |
      +--> replication factor, topology, số replica, trạng thái node
                 |
                 v
             footprint toàn cluster
```

Ví dụ keyspace có **replication factor 3**. Một partition có 50 MiB dữ liệu logic thì dữ liệu tương ứng có thể tồn tại trên ba replica theo chính sách replication. Nhưng phát biểu “partition đó chiếm chính xác 150 MiB trên toàn cluster” là **không có cơ sở**, vì footprint vật lý chịu ảnh hưởng nén, overhead, nhiều SSTable, tombstone và quá trình bảo trì.

**Không lấy dung lượng toàn cluster chia tổng số partition để suy ra partition lớn nhất.** Số trung bình có thể che giấu một vài tenant/thiết bị rất lớn.

## 6. Large partition và hot partition cần hai bộ phép đo

Một partition có thể chỉ 2 MiB nhưng nhận 30.000 request/giây. Partition khác có thể chứa 400 MiB dữ liệu nhưng mỗi ngày chỉ được đọc một lần.

| Loại vấn đề | Đo trước tiên | Rủi ro |
| --- | --- | --- |
| **Large partition** | Số hàng, cell count, byte/partition, tombstone | Đọc slice rộng, compaction, streaming, repair tốn tài nguyên. |
| **Hot partition** | Read/write request rate và độ trễ theo key, node/replica | Tập trung CPU/I/O/network, queue và timeout. |
| **Large + hot** | Cả kích thước và lưu lượng | Các vấn đề cộng hưởng, dễ gây đuôi độ trễ lớn. |
| **Tombstone-heavy** | Tombstones scanned/read, TTL/delete patterns | Trả ít hàng nhưng vẫn phải xử lý nhiều dữ liệu đã xóa. |

Hashing partition key bằng `Murmur3Partitioner` phân phối **các khóa khác nhau** đến các token, nhưng không chia một khóa nóng thành nhiều partition keys. Clustering columns giúp định vị dải hàng trong một partition, **không** chia tải của partition sang các replica sets khác.

Vì vậy, khi dự báo giới hạn, đừng chỉ đặt “max size per partition”; cần có mục tiêu **max read/write rate per active key**, **p95/p99 latency** và ngân sách compaction/repair.

## 7. Đo thực tế bằng `nodetool tablestats`

Cassandra cung cấp thông số quan sát ở nhiều mức: node, bảng, SSTable, truy vấn và (tùy công cụ/phiên bản) các partition key được lấy mẫu. Các lệnh sau dùng keyspace/bảng minh họa:

```bash
nodetool tablestats app_ks.measurements_by_device
```

Các trường có thể hữu ích, với **tên và sự sẵn có phụ thuộc phiên bản**:

- **SSTable count, space used (live/total):** mức sử dụng SSTable của bảng **trên node được hỏi**, không phải kích thước chính xác của một partition.
- **Compacted partition minimum/mean/maximum bytes:** thống kê kích thước partition sau compaction hoặc trên dữ liệu SSTable theo cơ chế thống kê của phiên bản; hữu ích để nhận diện đuôi phân bố lớn.
- **Read latency, write latency:** dấu hiệu chi phí truy cập ở mức bảng/node; giá trị trung bình không thay thế p95/p99.
- **Average live cells per slice và tombstones per slice:** gợi ý lượng dữ liệu được duyệt trong một lát đọc.
- **Bloom filter, memtable, pending flush/compaction metrics** nếu có: giúp hiểu chi phí đi kèm.

**Điểm giới hạn:** `tablestats` không cung cấp bản ghi đầy đủ `partition_key → exact current bytes` cho mọi khóa. Một partition có thể trải trên nhiều SSTable, có nén, tombstone và nhiều replica. Vì vậy số liệu thống kê **không nên được diễn giải là kết quả đếm tức thời, chính xác của một partition sống cụ thể**.

Một phương pháp đọc kết quả:

1. So sánh **mean** với **maximum**; nếu max lớn hơn nhiều lần trung bình, có outlier cần điều tra.
2. Đối chiếu **latency** và số SSTable/tombstone với cảnh báo large partition.
3. Chạy trên **các replica/node liên quan** nếu nghi ngờ sự phân bố không đều.
4. Giữ lại mốc thời gian và phiên bản Cassandra để so các lần đo.
5. Không cộng hoặc so các trường khác định nghĩa như thể chúng là cùng một đại lượng.

## 8. Xem phân phối bằng `nodetool tablehistograms`

Để hiểu phần đuôi dữ liệu, histogram hữu ích hơn một con số trung bình:

```bash
nodetool tablehistograms app_ks measurements_by_device
```

Tùy phiên bản, công cụ có thể trình bày phân vị của:

- **Partition size:** phân bố kích thước partition theo cơ chế lấy mẫu/thống kê được triển khai.
- **Cell count:** phân bố số cell của partition.
- **Read/write latency hoặc SSTables per read:** các trường khác có thể giúp liên hệ độ lớn dữ liệu với đường đọc.

Ví dụ **số giả định**, không phải kết quả của một cluster thật:

| Phân vị thống kê partition size | Giá trị giả định |
| --- | ---: |
| Trung vị | 4 MiB |
| p95 | 18 MiB |
| p99 | 72 MiB |
| Max được quan sát/thống kê | 530 MiB |

Nếu chỉ nhìn trung vị 4 MiB, có thể bỏ sót một số partition rất lớn. Trong khi đó, p99 = 72 MiB chưa chứng minh mọi partition dưới 72 MiB; phần 1% còn lại có thể bao gồm outlier lớn hơn nhiều.

Không nên tính các phân vị này như thể chúng là **phân vị chính xác của toàn bộ partition logic đang sống**, vì cách thu thập, cỡ mẫu, SSTable và tính hiện thời khác nhau theo phiên bản. Hãy ghi rõ **nguồn đo và khoảng thời gian** trên dashboard.

### Đọc histogram cần đặt trong bối cảnh workload

- **Byte cao, cell count thấp:** nghi ngờ payload lớn hoặc collection/blob lớn.
- **Cell count cao, byte trung bình thấp:** nhiều giá trị nhỏ, overhead hàng/cell và chi phí clustering đáng kể.
- **Read latency tăng, size ổn định:** có thể do hot partition, tombstone, compaction hoặc yếu tố node/network.
- **Max size tăng liên tục:** xem lại bucket, retention, tốc độ ghi, backfill và các tenant ngoại lệ.

## 9. Tìm partition key đáng điều tra mà không quét toàn bảng

Khi histogram cho thấy outlier, bước tiếp theo là **xác định khóa nào** chịu trách nhiệm. Đây không phải lúc chạy `SELECT *` hoặc `COUNT(*)` trên toàn bộ bảng production.

Các lựa chọn, tùy hệ thống:

1. **Thống kê ở tầng ứng dụng/ingest:** ghi số event và byte theo `tenant_id + device_id + bucket` theo các nhóm có kiểm soát.
2. **Sampling các partition keys được truy vấn:** ghi số request hoặc kích thước payload của một tập key lấy mẫu, tránh biến metrics thành bảng với label cardinality vô hạn.
3. **Công cụ hot partitions của phiên bản Cassandra:** một số phiên bản cung cấp `nodetool toppartitions` hoặc cơ chế thống kê/sampling tương tự; phải kiểm tra chính xác cú pháp và cách đo ở phiên bản đang chạy.
4. **Log/cảnh báo large partition:** dựa vào ngưỡng cảnh báo của compaction hoặc các tính năng quan sát được hỗ trợ.
5. **Phân tích SSTable/snapshot có kiểm soát:** công cụ ngoại tuyến như `sstablemetadata` và các công cụ liên quan có thể cung cấp thông tin bổ sung; cần kiểm tra tính tương thích phiên bản, dùng trên bản sao an toàn khi có nguy cơ ảnh hưởng I/O production.

Nếu cần kiểm tra một phân vùng đã biết khóa, hãy bắt đầu bằng truy vấn **giới hạn dữ liệu**:

```sql
SELECT measured_at, measurement_id, temperature
FROM measurements_by_device
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
LIMIT 20;
```

Truy vấn trên chỉ chứng minh có thể đọc một số hàng theo clustering order. Nó **không đo được số byte của cả partition**.

### Tại sao `COUNT(*)` không phải phép đo miễn phí?

```sql
-- Chỉ minh họa; cân nhắc chi phí trước khi chạy trên partition lớn:
SELECT COUNT(*)
FROM measurements_by_device
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12;
```

Để tính kết quả, Cassandra phải xử lý dữ liệu liên quan; khi có hàng triệu hàng/tombstone, truy vấn có thể tốn đáng kể CPU/I/O và thời gian. `COUNT(*)` chỉ cho **số hàng mà truy vấn quan sát**, không cho exact physical byte size và không phải công cụ giám sát định kỳ tốt cho hot partition.

Nếu cần số đếm nghiệp vụ liên tục, nên thiết kế **pipeline thống kê, bảng tổng hợp hoặc bộ đếm được điều phối phù hợp**, thay vì quét nguyên partition mỗi lần cần hiển thị.

## 10. Kiểm chứng giới hạn bằng benchmark giống production

Số liệu ước lượng và histogram phải được nối với **mục tiêu độ trễ, throughput và tính sẵn sàng**. Một mô hình partition có 100 MiB dữ liệu có thể phù hợp cho workload đọc slice 100 hàng, nhưng không phù hợp nếu sản phẩm liên tục quét toàn partition trong khoảng hẹp về SLA.

### Thiết kế test matrix

Với bảng time-series, chuẩn bị các nhóm kịch bản:

| Trường hợp | Dữ liệu/tải cần mô phỏng | Điều phải đo |
| --- | --- | --- |
| Bình thường | Partition trung vị, sự kiện nhỏ, ít tombstone | p50/p95/p99 read/write và throughput. |
| Dài hạn | Partition gần mức max dự báo, nhiều SSTable | Latency của LIMIT, range read và paging. |
| Tenant ngoại lệ | Một khóa gấp 5–10 lần tốc độ trung bình | Hot partition, replica CPU/I/O/network, timeout. |
| Payload lớn | Một số hàng có blob/text rất dài | Kích thước response, heap/GC, mạng và disk. |
| TTL/xóa | Dữ liệu hết hạn hoặc xóa thường xuyên | Tombstone scans, latency, compaction. |
| Compaction/repair | Công việc nền chạy cùng tải truy vấn | p99, disk headroom, pending compactions, throughput. |
| Sự kiện đến trễ/backfill | Ghi vào bucket cũ, nhiều request replay | I/O, trạng thái compaction và tính đúng khóa. |

Không nên thử chỉ một “ghi 1 triệu dòng với dữ liệu ngẫu nhiên rồi đo TPS”. Phân phối khóa của generator có thể **đều hơn thực tế rất nhiều** và không thể hiện tenant cực nóng.

### Cần giữ các biến quan trọng tương đồng

- Phiên bản Cassandra, topology node/data center, số node và cấu hình replica.
- Kích thước row/cell thực, tỷ lệ payload lớn, collection và compression.
- RF và consistency level của từng nhóm truy vấn.
- Tỷ lệ đọc/ghi, khoảng clustering query, LIMIT, page size và concurrency.
- TTL, update/delete rate, compaction strategy và phân bố tuổi dữ liệu.
- Phân phối theo **partition key**: trung vị, p95/p99, max read/write rate.
- Khoảng thời gian test đủ dài để thấy flush, compaction, cache và workload nền.

Có thể dùng `cassandra-stress` để tạo nền tải hoặc viết generator theo data model thực. **Điều quyết định là workload và phân bố khóa tương đồng**, không phải tên công cụ.

## 11. Đặt guardrail: cảnh báo, từ chối và giới hạn ở ứng dụng

Nên phân biệt **hard limit**, **guardrail của phiên bản Cassandra** và **ngân sách vận hành do nhóm hệ thống tự đặt**.

| Loại giới hạn | Nguồn | Cách hiểu |
| --- | --- | --- |
| **Ràng buộc kỹ thuật/định dạng** | Kiểu dữ liệu, giới hạn giao thức/định dạng và triển khai | Có thể khiến thao tác không hợp lệ hoặc thất bại; phải tra theo phiên bản. |
| **Server warning/guardrail** | Cấu hình Cassandra và phiên bản đang dùng | Có thể phát cảnh báo hoặc chặn thao tác khi điều kiện được cấu hình xảy ra. |
| **SLO/định mức nội bộ** | Kết quả benchmark và yêu cầu sản phẩm | Thường thấp hơn mức mà server còn chấp nhận; dùng để quyết định schema/bucket. |
| **Quota tầng ứng dụng** | API, ingest, hệ thống điều phối | Hạn chế request, byte, fan-out hoặc retention theo tenant. |

Một số phiên bản Cassandra có **các ngưỡng cảnh báo liên quan partition size khi compaction**, với tên tùy phiên bản (chẳng hạn dòng cấu hình cảnh báo large partition). Việc có log warning **không có nghĩa** mọi phân vùng vượt mức cảnh báo đều bị từ chối ghi ngay, và không có log **không chứng minh** phân vùng luôn an toàn.

Không nên sao chép một giá trị cảnh báo từ blog hoặc phiên bản khác rồi gọi đó là “giới hạn tối đa của Cassandra”. Để chốt ngưỡng phải:

1. Xác nhận **đúng phiên bản/phân phối Cassandra** và cấu hình hiện hành.
2. Hiểu rõ ngưỡng đó áp dụng cho **partition size, row size, mutation size hay batch size**.
3. Xác định hành vi **warning hay failure**, thời điểm kiểm tra, phạm vi đo.
4. Thử tải đủ để chứng minh mục tiêu latency/repair/compaction ở dưới ngưỡng.
5. Có kế hoạch xử lý khi một tenant hoặc khóa vượt ngân sách.

### Ví dụ policy nội bộ minh họa

```text
Policy dự kiến của một hệ thống (không phải mặc định Cassandra):

- Theo dõi phân bố partition size ở tất cả bảng time-series.
- Điều tra khi max hoặc p99 tăng vượt baseline thử tải.
- Giới hạn số bucket/shard được đọc trong một API request.
- Giới hạn đồng thời read/write/backfill theo tenant.
- Dừng tăng tải backfill nếu p99 sản xuất, compaction backlog,
  disk headroom hoặc timeout vượt ngân sách.
- Chọn bucket mới và migration khi partition thường xuyên
  vượt năng lực thực tế của cluster.
```

Sự khác biệt giữa **cảnh báo vận hành** và **lỗi bị server từ chối** cần được ghi rõ trong runbook để tránh phản ứng sai.

## 12. Chọn bucket dựa trên ngưỡng đã kiểm chứng

Giả sử bảng cũ lưu mọi bản đo của thiết bị trong một partition:

```sql
PRIMARY KEY (
    (tenant_id, device_id),
    measured_at,
    measurement_id
)
```

Sau khi đo, nhóm vận hành thấy thiết bị cao tải tích lũy nhiều tháng dữ liệu, và thử tải cho thấy các truy vấn lịch sử bị chậm khi phạm vi partition ngày càng lớn. Một phương án là chia theo **bucket giờ**:

```sql
CREATE TABLE measurements_by_device_hour (
    tenant_id       text,
    device_id       uuid,
    hour_bucket     timestamp,
    measured_at     timestamp,
    measurement_id  uuid,
    temperature     double,
    humidity        double,
    payload         text,
    PRIMARY KEY (
        (tenant_id, device_id, hour_bucket),
        measured_at,
        measurement_id
    )
) WITH CLUSTERING ORDER BY (
    measured_at DESC,
    measurement_id ASC
);
```

`hour_bucket` được định nghĩa là **đầu giờ UTC** của `measured_at`. Ví dụ:

```text
measured_at = 2026-11-21T08:43:12Z
hour_bucket = 2026-11-21T08:00:00Z
```

Truy vấn CQL trong một bucket:

```sql
SELECT measured_at, measurement_id, temperature, humidity
FROM measurements_by_device_hour
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND hour_bucket = '2026-11-21T08:00:00Z'
  AND measured_at >= '2026-11-21T08:15:00Z'
  AND measured_at <  '2026-11-21T08:30:00Z'
LIMIT 100;
```

Đây là một partition lookup với khoảng clustering key. Nếu truy vấn trải qua **hai giờ**, ứng dụng phải đọc hai partition keys rồi hợp nhất kết quả, vì clustering order chỉ có hiệu lực trong từng phân vùng.

### Bảng đánh đổi

| Phương án | Lợi ích | Rủi ro cần đo |
| --- | --- | --- |
| Không bucket | Dễ đọc toàn lịch sử một thiết bị theo partition | Partition tích lũy và có thể lớn/hot. |
| Bucket ngày | Ít partition lookups cho lịch sử một tuần | Một ngày của thiết bị nóng vẫn có thể quá lớn. |
| Bucket giờ | Giảm hàng/byte trên một partition | 24–25 partition lookups cho khoảng 24 giờ tùy ranh giới. |
| Bucket phút | Giảm further kích thước từng partition | Fan-out tăng mạnh cho lịch sử dài. |
| Bucket + shard | Chia tải ngay trong một khoảng thời gian | Reader phải quét các shard liên quan, merge và quản lý phiên bản hash/shard count. |

**Time bucket không tự xử lý write hotspot trong bucket đang hoạt động.** Nếu một thiết bị sinh 10.000 sự kiện/giây, tất cả sự kiện trong giờ hiện tại vẫn thuộc cùng `(tenant_id, device_id, hour_bucket)`. Khi đó phải thử thêm bucket ngắn hơn, shard hoặc thiết kế ingest khác dựa trên chi phí đọc.

## 13. TTL, tombstone và compaction làm thay đổi kết quả đo

Một partition có thể chứa **rất ít hàng sống** nhưng vẫn tiêu tốn I/O khi đọc vì tombstone hoặc nhiều SSTable.

Ví dụ ghi một sự kiện vào bucket giờ với TTL bảy ngày:

```sql
INSERT INTO measurements_by_device_hour (
    tenant_id, device_id, hour_bucket,
    measured_at, measurement_id,
    temperature, humidity, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21T08:00:00Z',
    '2026-11-21T08:43:12Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    38.1,
    67.5,
    'sensor=ok'
) USING TTL 604800;
```

TTL làm cell hết hạn theo thời gian kể từ **lúc ghi**, theo semantics của Cassandra. Nhưng dữ liệu vật lý có thể còn trên SSTable cho đến khi đủ điều kiện dọn trong quá trình compaction. Nếu xảy ra nhiều UPDATE/DELETE, tombstone có thể tăng nhanh.

**Hệ quả khi đo:**

- **COUNT(*) thấp** không đồng nghĩa footprint SSTable nhỏ.
- Histogram/compaction metric có thể phản ánh dữ liệu chưa được dọn.
- Read latency có thể tăng vì phải xét qua tombstone để tìm đủ số hàng sống.
- Repair và cấu hình vòng đời tombstone ảnh hưởng tính an toàn của xóa; không nên giảm tùy tiện `gc_grace_seconds` để dọn nhanh.
- `TimeWindowCompactionStrategy` có thể phù hợp với một số workload time-series TTL/append-mostly, nhưng **không chia partition key** và cần được đánh giá theo mẫu ghi, dữ liệu đến trễ, TTL không đồng đều.

Khi đặt ngưỡng vận hành, nên đo trong giai đoạn **ghi ổn định, sau khi TTL bắt đầu hết hạn, trong/ngoài lúc compaction và khi repair**. Một benchmark ngắn chưa có tombstone có thể đánh giá quá lạc quan.

## 14. Truy vấn giới hạn và paging từ Java Driver 4.x

Ứng dụng thường không cần đọc mọi hàng của một partition. Với bảng `measurements_by_device_hour`, Java Driver có thể dùng prepared statement và page size để giảm kích thước mỗi phản hồi.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class MeasurementRepository {
    private final CqlSession session;
    private final PreparedStatement readSlice;

    public MeasurementRepository(CqlSession session) {
        this.session = session;
        this.readSlice = session.prepare(
            "SELECT measured_at, measurement_id, temperature, humidity " +
            "FROM measurements_by_device_hour " +
            "WHERE tenant_id = ? AND device_id = ? AND hour_bucket = ? " +
            "AND measured_at >= ? AND measured_at < ? " +
            "LIMIT 100"
        );
    }

    public ResultSet readOneHour(
            String tenantId,
            UUID deviceId,
            Instant startInclusive,
            Instant endExclusive) {

        Instant hour = startInclusive.truncatedTo(ChronoUnit.HOURS);
        Instant hourEnd = hour.plus(1, ChronoUnit.HOURS);

        if (!startInclusive.isBefore(endExclusive) ||
            endExclusive.isAfter(hourEnd)) {
            throw new IllegalArgumentException(
                "Khoang doc phai nam trong mot bucket gio UTC");
        }

        BoundStatement query = readSlice.bind(
            tenantId, deviceId, hour, startInclusive, endExclusive
        ).setPageSize(50);

        return session.execute(query);
    }
}
```

Điều cần phân biệt:

- `LIMIT 100`: tối đa 100 hàng trả về từ câu truy vấn, **không phải** giới hạn kích thước partition.
- `setPageSize(50)`: kích thước trang mong muốn của driver; **không** thay đổi số hàng lưu hoặc bảo đảm tổng chi phí đọc nhỏ.
- `Instant` + `truncatedTo(HOURS)`: tính bucket giờ theo thời gian UTC tương ứng, phải đồng nhất với producer.
- Khoảng `[startInclusive, endExclusive)`: tránh trùng hàng đúng ranh giới khi ghép nhiều khoảng.
- Nếu khoảng truy vấn vượt qua một giờ, tầng dịch vụ phải chia thành nhiều bucket, đọc các partition liên quan và merge kết quả; không được chỉ chọn bucket đầu rồi âm thầm bỏ dữ liệu.

Đo latency thực tế nên tách **thời gian server phản hồi trang đầu**, **thời gian fetch các trang tiếp theo** và **thời gian ứng dụng merge/sắp xếp**. Một truy vấn có trang đầu nhanh nhưng đọc toàn lịch sử qua 10.000 trang vẫn có chi phí lớn.

## 15. Quy trình kiểm chứng sau khi đổi partition key

Thay từ `measurements_by_device` sang `measurements_by_device_hour` thường đòi hỏi bảng mới và migration. Không thể chỉ thêm `hour_bucket` làm regular column rồi mong dữ liệu tự chia.

Một quy trình triển khai có thể kiểm chứng:

1. **Chốt mục tiêu:** truy vấn nào phải nhanh, max/p99 partition size sau thay đổi dự kiến ra sao, số partition lookups cho một API.
2. **Tạo bảng mới:** dùng khóa ghép có bucket, kiểu dữ liệu và clustering order phù hợp.
3. **Tính hàm bucket xác định:** producer, backfill và reader dùng một quy tắc UTC; event ID/occurredAt phải ổn định khi retry.
4. **Duy trì dữ liệu mới trong lúc chuyển:** dual-write được giám sát hoặc replay từ nguồn sự kiện tin cậy; không mặc định hai bảng được cập nhật nguyên tử.
5. **Backfill có paging/checkpoint:** chia công việc theo partition nguồn và khoảng clustering time, giới hạn concurrency.
6. **Xử lý TTL/update/delete:** không chỉ copy hàng đang sống rồi cho là đủ nếu nguồn có thay đổi đồng thời; cần delta log hoặc quy trình đồng bộ cuối.
7. **Đối chiếu dữ liệu:** kiểm chứng key, payload, ranh giới bucket, trạng thái xóa/TTL và các truy vấn mới.
8. **Kiểm chứng hiệu năng:** chạy cùng tải đại diện, đo lại partition histogram, p99 latency, hot keys, compaction và số truy vấn fan-out.
9. **Cutover có rollback:** chuyển read/write path theo mốc rõ ràng, giữ khả năng replay delta về đường cũ nếu cần.
10. **Dọn schema cũ** chỉ sau khi hết cửa sổ rollback và được chấp thuận.

**Số liệu cần so sánh trước/sau** không chỉ là kích thước trung bình của partition. Ví dụ:

| Kiểm chứng | Trước | Sau | Tiêu chí |
| --- | --- | --- | --- |
| Max/p99 partition size | Giá trị đo trên bảng cũ | Giá trị đo trên bảng mới | Phần đuôi giảm theo ngân sách đã chốt. |
| p99 đọc Q1/Q2 | Baseline | Theo tải đại diện | Không vượt SLO. |
| Top write key rate | Tập trung vào partition thiết bị | Phân chia theo thiết bị/giờ | Không còn điểm nóng vượt năng lực replica. |
| Tombstones scanned | Baseline | Theo TTL/xóa của bảng mới | Không có read amplification bất thường. |
| Partition lookups/API | Ít nhưng partition lớn | Có thể nhiều hơn | Fan-out vẫn nằm trong ngân sách. |
| Dữ liệu đúng | Source-of-truth | Shadow read/reconciliation | Không mất, trùng hoặc sai bucket. |

Sau khi có dữ liệu đo, **hiệu chỉnh công thức ước lượng**: dùng kích thước row thực, phân bố payload và sai số nén/overhead thực tế thay cho giả định ban đầu.

## 16. Bài tập thực hành: thiết kế ngân sách partition

Một dịch vụ theo dõi giao dịch có **2.000 tài khoản**. Workload giả định:

- Tài khoản thường: **8 event/giây** trong hai giờ cao điểm mỗi ngày.
- Tài khoản lớn: **150 event/giây** trong hai giờ cao điểm mỗi ngày.
- Mỗi event có **900 byte payload logic**, chưa tính khóa/overhead.
- Mỗi event có full primary key riêng.
- Truy vấn chính: 100 event mới nhất **trong một giờ**.
- Truy vấn phụ: lịch sử **bảy ngày**.
- Hệ thống giữ dữ liệu trong 30 ngày theo policy nghiệp vụ.

Nhóm thiết kế cân nhắc hai khóa:

```sql
-- Phương án A: một partition cho mỗi account, mọi thời gian.
PRIMARY KEY (account_id, occurred_at, event_id)

-- Phương án B: một partition cho mỗi account trong một giờ.
PRIMARY KEY ((account_id, hour_bucket), occurred_at, event_id)
```

**Câu hỏi:**

1. Với A, `occurred_at` có tham gia tính token không?
2. Tài khoản thường tạo bao nhiêu hàng trong **một giờ cao điểm**?
3. Tài khoản lớn tạo bao nhiêu hàng và bao nhiêu MB payload logic trong **một giờ cao điểm**?
4. Trong **30 ngày** và giả định ngày nào cũng có hai giờ cao điểm như nhau, A tích lũy bao nhiêu hàng cho tài khoản lớn nếu không có xóa/TTL?
5. B giảm số hàng mỗi partition như thế nào so với A?
6. Với B, truy vấn cửa sổ đúng **bảy ngày** có thể giao tối đa bao nhiêu bucket giờ tùy ranh giới?
7. Vì sao `LIMIT 100` không thể dùng làm bằng chứng rằng B an toàn ở mọi tải?
8. Sau khi chạy `nodetool tablehistograms`, p99 size nhỏ nhưng max size rất cao cho thấy điều gì?
9. Nếu tài khoản lớn phát 150 event/giây trong cả giờ hiện tại, bucket giờ có tự chia tải ghi đồng thời của tài khoản đó không?
10. Nếu đã có TTL 30 ngày, có thể lấy số hàng `COUNT(*)` làm kích thước byte chính xác trên đĩa không?
11. Nếu benchmark chỉ tạo partition keys ngẫu nhiên, đều nhau, nó có thể bỏ sót vấn đề gì?
12. Những loại số liệu nào cần đo cùng nhau để quyết định “đạt giới hạn” trước khi triển khai?

**Đáp án có giải thích:**

1. **Không.** Partition key chỉ là `account_id`; `occurred_at` và `event_id` là clustering columns.
2. `8 × 3.600 = 28.800` hàng.
3. `150 × 3.600 = 540.000` hàng; `540.000 × 900 = 486.000.000 byte = 486 MB ≈ 463,5 MiB` payload, chưa overhead/nén/replica.
4. `540.000 × 2 × 30 = 32.400.000` hàng trong một partition tài khoản ở A theo giả định.
5. B tạo **một partition cho mỗi account/giờ có dữ liệu**, thay vì tích lũy toàn lịch sử. Giờ cao điểm của tài khoản lớn vẫn có thể chứa 540.000 hàng; cần thử tải để xác định đã đủ nhỏ/chưa.
6. Một cửa sổ đúng bảy ngày dài 168 giờ có thể giao **168 hoặc 169 bucket giờ**, tùy điểm đầu/cuối có trùng ranh giới, với khoảng đọc đóng–mở.
7. Vì LIMIT chỉ giới hạn hàng trả về, không giới hạn kích thước vật lý, tombstone, compaction/repair hoặc write hotspot.
8. Có **phân vùng ngoại lệ** đáng điều tra; p99/mean không đại diện cho mọi partition. Cần xác định khóa và lịch sử/tải của outlier.
9. **Không.** Các ghi trong giờ hiện tại của cùng `account_id` vẫn dùng **một partition key `(account_id, hour_bucket)`**; nếu nóng phải cân nhắc bucket ngắn hơn, shard hoặc giảm tải.
10. **Không.** COUNT(*) không đo byte và TTL/tombstone/compaction làm footprint vật lý khác dữ liệu logic.
11. Có thể bỏ sót **skew/hot partition**, một tài khoản chiếm phần lớn lưu lượng và các dải clustering bị quét quá rộng.
12. Cần đo partition size/cell count **p95/p99/max**, top read/write keys, p99 latency, timeout, SSTables/tombstones, I/O/CPU/GC, compaction/repair và fan-out API, dưới workload cùng dữ liệu phù hợp thực tế.

## 17. Checklist áp dụng cho một bảng Cassandra

- [ ] Xác định **đầy đủ partition key** và các clustering columns; không nhầm key tăng theo thời gian với partition key mới.
- [ ] Tính số hàng/partition cho tốc độ bình thường, đỉnh và tenant/thiết bị ngoại lệ.
- [ ] Lấy mẫu byte/row và phần tử collection; ước lượng key/metadata overhead có ghi rõ giả định.
- [ ] Phân biệt payload logic, footprint trên một replica và dung lượng cluster có RF.
- [ ] Đo histogram partition size/cell count, max và phân bố tail; không chỉ theo dõi mean.
- [ ] Đo read/write rate của các key nóng và tài nguyên của replica/coordinator.
- [ ] Theo dõi tombstone, SSTables per read, compaction backlog và hiệu ứng TTL.
- [ ] Không dùng `COUNT(*)` hoặc quét toàn bảng như phép đo dung lượng thường xuyên trên production.
- [ ] Xác minh các guardrail/version-specific warning và phân biệt ngưỡng cảnh báo với hard failure.
- [ ] Benchmark bằng **workload thực** gồm skew, payload lớn, TTL, update/delete và hoạt động nền.
- [ ] Chọn time bucket/shard có tính **chi phí fan-out** của các truy vấn chính.
- [ ] Dùng truy vấn CQL đủ partition key, LIMIT/paging đúng nghĩa và bucket UTC nhất quán trong Java.
- [ ] Đặt cảnh báo, quota/backpressure, ngưỡng dừng backfill và runbook cho outlier.
- [ ] Khi đổi khóa, có kế hoạch bảng mới, replay/dual-write, kiểm chứng và rollback.
- [ ] Chỉ tuyên bố “phân vùng trong giới hạn” khi đạt **tiêu chí đã đo**, không dựa vào một con số MB chung.

## 18. Ghi nhớ

- Ước lượng phân vùng cần tính **số hàng × kích thước dữ liệu**, kết hợp cell/collection, overhead, TTL và **phân bố tải giữa các khóa**.
- Một số liệu trung bình không cho biết **phân vùng lớn nhất** hoặc **khóa nóng nhất**; luôn quan sát tail và outlier.
- `nodetool tablestats` và `nodetool tablehistograms` cung cấp **thống kê có giá trị chẩn đoán**, không phải phép đo tức thời chính xác cho mỗi partition logic sống.
- Không có một **ngưỡng MB/hàng áp dụng cho mọi Cassandra cluster**. Hard limits, server warnings/guardrails và SLO nội bộ là ba khái niệm khác nhau.
- **LIMIT và paging** kiểm soát khối lượng kết quả, nhưng không thu nhỏ dữ liệu đang lưu hay loại bỏ tombstone/compaction cost.
- **Bucket** giới hạn lượng lịch sử trong phân vùng; **shard** giúp tạo thêm partition keys đồng thời, đánh đổi với fan-out đọc.
- **Replication, consistency level, compaction và repair** ảnh hưởng footprint, tính sẵn sàng và độ trễ, nhưng không thay thế việc chọn partition key hợp lý.
- Công thức định cỡ phải được **hiệu chỉnh bằng đo thực tế và benchmark**, rồi xác minh lại sau khi thay đổi schema.

Khi biết cách ước lượng, đo và kiểm chứng giới hạn phân vùng, bạn có thể lựa chọn partition key Cassandra dựa trên bằng chứng, dự kiến chi phí đọc/ghi và vận hành, đồng thời xây dựng ứng dụng Java với ngân sách truy vấn rõ ràng. Đây là nền tảng để phòng ngừa large/hot partition và duy trì hệ thống wide-column phân tán ổn định khi dữ liệu tiếp tục tăng.


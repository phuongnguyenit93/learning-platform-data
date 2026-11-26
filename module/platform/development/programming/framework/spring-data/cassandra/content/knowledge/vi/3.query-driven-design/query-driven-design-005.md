# Ước lượng kích thước, tốc độ tăng và số hàng của partition

Khi thiết kế bảng cho **Apache Cassandra** và truy cập qua **Spring Data Cassandra**, câu hỏi quan trọng không chỉ là “truy vấn này cần những cột nào?” mà còn là **“mỗi partition sẽ chứa bao nhiêu hàng, lớn đến đâu và tăng nhanh thế nào?”**. Một partition quá lớn có thể khiến việc đọc, compaction, streaming, repair và xử lý tombstone tốn nhiều tài nguyên; một partition nhận phần lớn lưu lượng có thể trở thành **hot partition** ngay cả khi dung lượng chưa lớn.

Bài này thuộc phần **Thiết kế theo truy vấn** của Spring Data Cassandra. Ta sẽ đi từ nhu cầu truy vấn đến cách tính kích thước partition, dự báo theo thời gian, chọn bucket/shard, rồi đối chiếu bằng dữ liệu vận hành. Các nguyên tắc cũng áp dụng khi viết CQL, ánh xạ entity, dùng repository hoặc `CassandraTemplate`, phân trang và lựa chọn consistency level.

## 1. Partition cần được ước lượng trước khi tạo bảng

Trong Cassandra, các hàng có **cùng giá trị partition key** nằm trong một partition logic. Partition key xác định token dùng để phân phối dữ liệu đến các replica. **Clustering columns** phân biệt và sắp xếp hàng bên trong partition; chúng không tạo thêm partition.

Giả sử ứng dụng cần hiển thị **100 sự kiện mới nhất của một tenant trong một ngày**, từ mới đến cũ. Thiết kế ban đầu:

```sql
CREATE TABLE telemetry_ks.events_by_tenant_day (
    tenant_id   uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload_ref text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
```

**Partition key** là `(tenant_id, event_day)`. Với một tenant và một ngày cụ thể, mọi sự kiện có cùng hai giá trị này thuộc **một partition**, kể cả khi `occurred_at` và `event_id` khác nhau.

```text
tenant_id = A, event_day = 2026-11-25
└── một partition
    ├── 10:03:22 | event_03
    ├── 09:18:01 | event_02
    └── 08:41:05 | event_01

tenant_id = A, event_day = 2026-11-26
└── một partition khác

tenant_id = B, event_day = 2026-11-25
└── một partition khác
```

Các ký hiệu A, B, `event_01` chỉ để minh họa; cột `uuid` khi thực thi CQL cần giá trị UUID hợp lệ.

Truy vấn phù hợp với thiết kế:

```sql
SELECT occurred_at, event_id, event_type, payload_ref
FROM telemetry_ks.events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
LIMIT 100;
```

Truy vấn theo một partition và thứ tự clustering đã định thường dễ kiểm soát hơn quét nhiều partition. Nhưng cần xác nhận rằng **partition của tenant có nhiều sự kiện nhất trong ngày** vẫn có quy mô và mức tải chấp nhận được. Không thể lấy mức trung bình toàn hệ thống để thay cho trường hợp lớn nhất.

## 2. Ba đại lượng bắt buộc phải tách biệt

| Đại lượng | Câu hỏi cần trả lời | Đơn vị thường dùng |
| --- | --- | --- |
| **Số hàng/partition** (`N_p`) | Một tổ hợp partition key có tối đa bao nhiêu hàng còn tồn tại? | rows/partition |
| **Kích thước/partition** (`S_p`) | Partition đó chiếm bao nhiêu dữ liệu thực tế trên mỗi replica? | byte, MiB, GiB/partition |
| **Tốc độ ghi/partition** (`W_p`) | Trong giờ hoặc giây cao điểm, partition nhận bao nhiêu lần ghi? | writes/s/partition |

Ba đại lượng không thay thế cho nhau:

- Một partition có **nhiều hàng nhỏ** vẫn làm tăng số mục cần xử lý và chi phí scan.
- Một partition có **ít hàng nhưng payload rất lớn** vẫn có thể nặng.
- Một partition dung lượng chỉ vài MiB nhưng bị ghi/đọc hàng nghìn lần mỗi giây vẫn có thể nóng.

Vì vậy cần xét **giá trị trung bình, đỉnh, độ lệch giữa các tenant và xu hướng tăng trưởng**. Với bảng không giới hạn theo thời gian (chỉ dùng `tenant_id` làm partition key), một tenant hoạt động lâu dài sẽ tiếp tục tích lũy hàng trong cùng partition nếu không có cơ chế hết hạn hoặc xóa dữ liệu.

## 3. Công thức ước lượng ban đầu

Định nghĩa:

- `r`: số **hàng mới khác primary key** được tạo trong một giây, tính cho **một tenant** (không phải toàn cluster).
- `T`: thời lượng mỗi time bucket tính bằng giây, ví dụ một ngày là 86.400 giây.
- `k`: số shard trong một time bucket, mặc định `1`.
- `b`: số byte trung bình trên một hàng, được **ước lượng hoặc đo** theo mô hình dữ liệu thực tế.
- `h`: chi phí bổ sung cho partition và cấu trúc lưu trữ, thay đổi theo dữ liệu/phiên bản/cấu hình.

Khi tải tương đối đều giữa các shard:

\[
N_{p} \approx \frac{r\times T}{k}
\]

\[
S_{p} \approx N_{p}\times b+h
\]

Nếu dự báo theo ngày với `V_d` hàng mới của một tenant/ngày và partition theo ngày:

\[
N_{p,\mathrm{day}} \approx \frac{V_d}{k}
\]

Đây là **công thức lập kế hoạch**, không phải định luật cho mọi workload. Cần điều chỉnh khi có cập nhật lại cùng primary key, xóa, TTL, dữ liệu có độ lớn thay đổi, phân phối shard lệch hoặc thời điểm ghi đột biến. Đặc biệt, `COUNT(*)` trên một partition lớn không nên được dùng liên tục để đo số hàng trong production: truy vấn đếm vẫn phải duyệt dữ liệu và có thể tốn tài nguyên.

### Kích thước hàng là gì?

Không nên lấy `length(payload)` rồi coi là kích thước đầy đủ của hàng trên đĩa. Kích thước thực tế còn phụ thuộc vào:

- Byte của partition/clustering key, giá trị các cột, metadata của cell và timestamp.
- Số lượng cột đã ghi, giá trị `null`, collection, kiểu dữ liệu, encoding của chuỗi.
- Cách SSTable tổ chức dữ liệu, compression, index và metadata.
- Update/delete/TTL tạo tombstone, số SSTable cùng tồn tại và compaction.

`b` nên được đo trên **dữ liệu đại diện** sau khi ghi và flush theo cách phù hợp môi trường. Nếu chưa có dữ liệu thật, dùng nhiều kịch bản (nhỏ, thường gặp, lớn) rồi bổ sung hệ số dự phòng; đừng khẳng định một hàng JSON 1 KiB chắc chắn chiếm đúng 1 KiB trên đĩa.

## 4. Ví dụ tính bằng số cụ thể

Giả sử ứng dụng ghi sự kiện cho từng tenant; để đơn giản, **dùng 800 byte/hàng làm giả định lập kế hoạch** sau khi đã tính sơ bộ chi phí lưu trữ. Mỗi ngày là một bucket, chưa chia shard (`k = 1`).

| Mức sử dụng của một tenant | Hàng mới/ngày | Hàng/partition ngày | Dung lượng ước lượng/partition |
| --- | ---: | ---: | ---: |
| Ít hoạt động | 2.000 | 2.000 | 1,6 MB |
| Thông thường | 12.000 | 12.000 | 9,6 MB |
| Hoạt động cao | 120.000 | 120.000 | 96 MB |
| Ngày bùng nổ | 500.000 | 500.000 | 400 MB |

Ở bảng này, **MB là đơn vị thập phân** (`1 MB = 1.000.000 byte`), chưa cộng phần overhead `h`. Số thực tế có thể chênh lệch đáng kể khi dữ liệu được nén, sửa đổi, hết hạn hoặc compact.

Với tenant trung bình 12.000 hàng/ngày:

```text
12.000 hàng/ngày × 800 byte/hàng
  = 9.600.000 byte/ngày
  = 9,6 MB cho partition của tenant trong ngày đó

30 ngày × 9,6 MB/ngày
  = 288 MB dữ liệu logic của tenant trên 30 partition ngày
  ≠ một partition 288 MB
```

Nếu để **cùng dữ liệu của 30 ngày trong một partition theo tháng**, ta có khoảng `360.000` hàng và `288 MB` trên **một partition tháng** (giả sử không hết hạn/ghi đè). Chọn bucket ngày làm giảm số hàng trong từng partition, nhưng các truy vấn đọc 30 ngày phải lấy và ghép dữ liệu từ nhiều partition.

**Tình huống đáng lo:** tenant đạt 500.000 sự kiện trong một ngày tạo partition khoảng 400 MB theo giả định. Dù tổng dữ liệu cluster chưa lớn, partition này có thể gây áp lực riêng lên các replica chứa nó. Đồng thời cần tính **tốc độ ghi cao điểm**: 500.000 sự kiện dồn vào 10 phút rất khác 500.000 sự kiện rải đều 24 giờ.

### Dung lượng logic, replica và dung lượng cluster

Giả sử tổng dữ liệu của một bảng (đã tính ở mức một bản sao) là `D`, và keyspace dùng replication factor `RF = 3` tại một datacenter có đủ node:

```text
Dung lượng dữ liệu trên các replica ≈ D × 3
```

Ví dụ `288 MB × 3 = 864 MB` là ước lượng **tổng dung lượng bản sao** cho 30 ngày của một tenant, không phải kích thước một partition. Nếu nhiều datacenter có RF khác nhau, tính riêng từng datacenter rồi cộng lại. Dung lượng cấp phát thực tế phải chừa chỗ cho SSTable, compaction, repair, snapshot/backup (nếu có), tăng trưởng và phân bố không đều; không chỉ nhân RF là xong.

## 5. Dự báo tốc độ tăng thay vì chỉ đo hiện tại

Hệ thống mới triển khai có thể chưa xuất hiện partition lớn. Vì vậy phải ước tính theo **số tháng hoạt động, mức tăng người dùng và tenant có tải cao nhất**.

Giả sử tenant điển hình bắt đầu ở `12.000` sự kiện/ngày, khối lượng sự kiện tăng `20%` mỗi tháng, kích thước trung bình giữ ở `800 byte/hàng`. Với `m` là số tháng:

\[
V_d(m)=12.000\times(1+0,20)^m
\]

| Thời điểm | Hàng/ngày xấp xỉ | MB/partition ngày nếu chưa shard |
| --- | ---: | ---: |
| Hiện tại (`m=0`) | 12.000 | 9,6 |
| Sau 3 tháng | 20.736 | 16,6 |
| Sau 6 tháng | 35.832 | 28,7 |

Đây là một **kịch bản giả định** chứ không phải dự báo thực tế của mọi sản phẩm. Ngoài tăng trưởng của một tenant, còn cần dự báo:

1. **Số tenant:** ảnh hưởng số partition và tổng dung lượng toàn cluster.
2. **Mức tăng của tenant lớn nhất:** ảnh hưởng partition lớn nhất và hot partition.
3. **Số sự kiện trên một thao tác nghiệp vụ:** thay đổi số hàng/partition ngay cả khi lượng người dùng không đổi.
4. **Thời gian lưu trữ:** ảnh hưởng số bucket còn dữ liệu và tổng dữ liệu đang tồn tại.
5. **Phân phối theo thời gian:** tải có thể dồn vào vài phút, ca làm việc hoặc chiến dịch.
6. **Kích thước hàng theo thời gian:** thêm cột hoặc payload dài hơn làm tăng byte/hàng dù số hàng không đổi.

Nếu retention là 30 ngày và mỗi tenant phát sinh dữ liệu mỗi ngày, với một shard/ngày sẽ có **khoảng 30 partition ngày chứa dữ liệu còn hiệu lực cho mỗi tenant** ở trạng thái ổn định. Với bốn shard/ngày, tối đa khoảng `30 × 4 = 120` partition đang chứa dữ liệu còn hiệu lực cho tenant đó; không có ghi vào một shard/ngày thì partition tương ứng có thể không được tạo. Con số này chưa nói gì về thời điểm SSTable cũ/tombstone thực sự được dọn.

## 6. Chọn bucket theo thời gian: ngày, giờ hay tháng?

Độ rộng time bucket quyết định **số hàng của một partition** khi partition key bao gồm tenant và bucket đó.

| Thiết kế partition key | Mức tăng mỗi partition | Số partition phải đọc cho 30 ngày | Phù hợp khi |
| --- | --- | --- | --- |
| `(tenant_id)` | Có thể tích lũy lâu dài | 1, nhưng có nguy cơ cực lớn | Tập dữ liệu có giới hạn tự nhiên rất nhỏ |
| `(tenant_id, event_month)` | Tổng hàng của cả tháng | Khoảng 1–2 | Lượng sự kiện thấp, chủ yếu xem theo tháng |
| `(tenant_id, event_day)` | Tổng hàng của một ngày | Khoảng 30–31 | Truy vấn theo ngày, lưu lượng vừa phải |
| `(tenant_id, event_hour)` | Tổng hàng của một giờ | Khoảng 720 | Tenant ghi rất nhiều, truy vấn thường theo giờ |

Các con số partition cần đọc chỉ mang tính minh họa khi truy vấn trọn khoảng thời gian; thực tế phụ thuộc cách xác định biên bucket, khoảng truy vấn và số bucket có dữ liệu.

**Bucket quá dài**: partition tích lũy nhiều hàng, phạm vi compaction/đọc có thể nặng. **Bucket quá ngắn**: số partition tăng, truy vấn khoảng dài phải fan-out tới nhiều partition, thêm chi phí định tuyến và ghép kết quả. Hãy bắt đầu từ **truy vấn bắt buộc**, số hàng dự kiến và phân phối tải; không có đáp án “luôn chọn theo ngày”.

**Lưu ý về đồng hồ và múi giờ:** thời điểm sự kiện nên được chuẩn hóa nhất quán (thường UTC), còn bucket ngày/giờ phải có quy ước rõ ràng. Nếu ngày nghiệp vụ dùng múi giờ của tenant, việc tính `event_day` phải ổn định và khớp giữa ghi lẫn đọc, nhất là tại ranh giới ngày hoặc khi có chuyển đổi giờ mùa hè.

## 7. Khi cần chia shard bên trong time bucket

Nếu một tenant có thể ghi 120.000 sự kiện/ngày (ước lượng 96 MB/partition với `b=800` byte), ta có thể cân nhắc thêm `shard` vào partition key:

```sql
CREATE TABLE telemetry_ks.events_by_tenant_day_shard (
    tenant_id   uuid,
    event_day   date,
    shard       smallint,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload_ref text,
    PRIMARY KEY ((tenant_id, event_day, shard), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
```

Nếu chia **bốn shard tương đối đều**:

```text
120.000 hàng/ngày ÷ 4 shard = 30.000 hàng/shard/ngày
96 MB/ngày ÷ 4 shard = khoảng 24 MB/partition
```

Shard có thể được chọn từ một phép băm ổn định của `event_id` rồi lấy phần dư theo số shard, để cùng sự kiện luôn đi vào một shard. Phải xử lý phép modulo âm theo ngôn ngữ lập trình và duy trì cùng quy tắc định tuyến khi đọc/ghi.

```text
tenant A, 2026-11-25
  ├── shard 0 -> partition (A, 2026-11-25, 0)
  ├── shard 1 -> partition (A, 2026-11-25, 1)
  ├── shard 2 -> partition (A, 2026-11-25, 2)
  └── shard 3 -> partition (A, 2026-11-25, 3)
```

CQL đọc **một shard**:

```sql
SELECT occurred_at, event_id, event_type
FROM telemetry_ks.events_by_tenant_day_shard
WHERE tenant_id = ?
  AND event_day = ?
  AND shard = ?
LIMIT 100;
```

**Đánh đổi rất quan trọng:** thêm shard giúp giảm kích thước và tốc độ ghi trên từng partition, nhưng màn hình “100 sự kiện mới nhất của tenant trong ngày” giờ phải **đọc các shard liên quan và merge theo `occurred_at`/`event_id`** ở tầng ứng dụng. Thứ tự clustering chỉ có hiệu lực **trong từng partition**, không tạo thứ tự toàn cục giữa shard. Việc phân trang qua nhiều shard cần giữ paging state của từng luồng và chiến lược ghép/tránh trùng; một paging state Cassandra không đại diện cho toàn bộ kết quả merge.

Với partition theo giờ, đôi khi không cần shard; với tải quá lệch theo giờ, có thể cần cả **hour bucket + shard**. Chọn số shard dựa trên tải xấu nhất và chi phí đọc fan-out. Tăng số shard của dữ liệu cũ mà không có kế hoạch routing/migration có thể khiến việc đọc không biết sự kiện trước đây nằm ở đâu.

## 8. Tốc độ ghi, độ lệch tải và hot partition

Kích thước cuối ngày không phản ánh mọi rủi ro. Cần tính thêm:

\[
W_{p,\mathrm{peak}} \approx \frac{\text{lượt ghi trong khoảng cao điểm}}{\text{số giây của khoảng đó}\times k}
\]

Ví dụ cùng 120.000 sự kiện/ngày:

- Nếu phân bố đều 24 giờ: `120.000 / 86.400 ≈ 1,39` sự kiện/giây cho tenant đó.
- Nếu 60.000 sự kiện dồn vào 10 phút: `60.000 / 600 = 100` sự kiện/giây trong khoảng đỉnh; với bốn shard đều tải, khoảng 25 sự kiện/giây/partition.

Các con số chỉ minh họa; chi phí một ghi còn phụ thuộc kích thước, số cột, read/write mix, replica, consistency level, cấu hình phần cứng và các workload khác trên node. Khi một partition được truy cập liên tục, **ba replica của partition vẫn có thể cùng bị nóng**; RF không tự động biến một partition thành nhiều partition key độc lập.

Hãy đo riêng theo **tenant, khoảng thời gian và partition key**, ít nhất gồm: hàng/partition, byte/partition ước lượng, writes/s, reads/s, kích thước payload, độ trễ p95/p99 và số partition tham gia mỗi truy vấn. Chú ý cả **đỉnh của tenant lớn nhất** lẫn percentiles của toàn bộ tenant; trung bình thấp không chứng minh không có hot partition.

## 9. TTL, update, delete và tombstone thay đổi phép tính

Số hàng “đã từng ghi” khác số hàng “đang tồn tại về mặt logic” và khác cả số byte “hiện vẫn nằm trên đĩa”.

**Trường hợp có TTL:** nếu một bảng/sự kiện có thời gian sống 30 ngày, sau 30 ngày dữ liệu hết hạn về mặt logic. Tuy nhiên dữ liệu hết hạn và tombstone có thể còn nằm trong SSTable cho đến khi đủ điều kiện và được xử lý qua compaction. Thời điểm giải phóng đĩa không đúng bằng thời điểm TTL hết hạn.

**Trường hợp cập nhật cùng primary key:** Cassandra có ngữ nghĩa upsert; ghi lại cùng partition key và clustering key không tạo hàng logic mới, dù vẫn tạo công việc ghi và có thể làm tăng dữ liệu vật lý tạm thời trong SSTable đến khi compaction.

**Trường hợp delete hoặc nhiều cột thay đổi:** tombstone và các phiên bản cell làm chi phí đọc/compaction khác với `N_p × b`. Phần dữ liệu lịch sử chưa được thu gom có thể lớn đáng kể khi workload update/delete thường xuyên.

Vì vậy nên có **hai ước lượng song song**:

1. **Dung lượng logic**: dữ liệu còn hợp lệ theo retention, phục vụ dự đoán số hàng có thể được đọc.
2. **Dung lượng vật lý**: dung lượng SSTable/metadata/replica, tombstone và khoảng trống cần thiết cho compaction/repair, phục vụ dự đoán capacity.

Không nên giả định `TTL = 30 ngày` sẽ giới hạn tất cả dữ liệu trên đĩa chính xác ở 30 ngày, hoặc time bucket tự xóa khi hết ngày.

## 10. Đo bằng dữ liệu đại diện và đối chiếu dự báo

**Bước 1 — Đếm từ nguồn ghi hoặc thống kê nghiệp vụ.** Khi ứng dụng tiếp nhận sự kiện, thống kê theo `(tenant_id, event_day)` hoặc khóa bucket/shard tương ứng: số lần ghi, số **event_id mới**, phân vị số hàng/partition, số hàng tối đa, tần suất theo phút/giờ. Nên sử dụng counter/metric phù hợp ở tầng ingestion thay vì liên tục đếm bằng CQL trên production.

**Bước 2 — Ước lượng byte/hàng từ dữ liệu thật.** Tạo workload thử nghiệm đại diện cho kích thước payload, update, TTL, compression và số cột; ghi đủ dữ liệu để tránh nhiễu do overhead cố định. Từ dung lượng SSTable và số hàng/partition thực tế, suy ra khoảng ước lượng `b` với điều kiện thử nghiệm được ghi rõ.

**Bước 3 — Quan sát Cassandra.** Công cụ quản trị có thể cung cấp số liệu cấp bảng, chẳng hạn:

```bash
nodetool tablestats telemetry_ks.events_by_tenant_day_shard
```

Tùy phiên bản Cassandra, thông tin và cú pháp đối số có thể khác nhau; hãy kiểm tra phần trợ giúp của đúng phiên bản đang vận hành. Các số liệu min/max/mean partition size (nếu có), SSTable count, disk space, tombstones, read/write latency, cùng metrics/JMX/monitoring là **tín hiệu để đối chiếu**, không bảo đảm trực tiếp cho phân vị mỗi tenant. Cần kết hợp với số liệu ứng dụng để nhận diện partition lớn nhất và tải bị lệch.

**Bước 4 — Thử truy vấn thật.** Đọc một ngày, nhiều ngày, lấy trang tiếp theo, kiểm tra ngày lớn nhất và payload lớn nhất. Xem độ trễ, số partition/quy mô dữ liệu được đọc, tombstone scan và ảnh hưởng đến replica dưới tải đồng thời. Paging có thể giảm kích thước một response, nhưng không khắc phục partition cực lớn hoặc truy vấn thiếu partition key.

**Bước 5 — Tính dự phòng và kiểm tra định kỳ.** So sánh dự báo với số liệu sau từng đợt tăng trưởng; cập nhật `b`, tốc độ ghi đỉnh và số tenant. Ưu tiên đặt **ngưỡng vận hành do hệ thống của bạn kiểm chứng**, thay vì coi một con số hàng/partition hay MiB/partition là giới hạn an toàn tuyệt đối cho mọi phiên bản và workload.

> **Cảnh báo thực hành:** Không chạy `SELECT COUNT(*)` hoặc quét toàn bảng định kỳ để tìm partition lớn trên cluster production có tải cao. Cách đo đó tự tạo tải lớn và thường không cho bức tranh phân bố tốt bằng thống kê từ đường ghi kết hợp metrics Cassandra.

## 11. Liên hệ Spring Data Cassandra: mapping đúng khóa và truy vấn

Spring Data Cassandra **không tự giải quyết** vấn đề partition lớn. Entity mapping phải khớp với schema CQL; repository hoặc `CassandraTemplate` chỉ thực thi các truy vấn bạn thiết kế.

Với bảng `events_by_tenant_day_shard`, khóa Java có thể được mô hình hóa như sau (lược bỏ import, constructor, accessor và `equals/hashCode` để tập trung vào phân chia khóa):

```java
@PrimaryKeyClass
public class EventKey implements Serializable {

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
                      type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "event_day", ordinal = 1,
                      type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(name = "shard", ordinal = 2,
                      type = PrimaryKeyType.PARTITIONED)
    private Short shard;

    @PrimaryKeyColumn(name = "occurred_at", ordinal = 3,
                      type = PrimaryKeyType.CLUSTERED)
    private Instant occurredAt;

    @PrimaryKeyColumn(name = "event_id", ordinal = 4,
                      type = PrimaryKeyType.CLUSTERED)
    private UUID eventId;
}

@Table("events_by_tenant_day_shard")
public class EventRow {

    @PrimaryKey
    private EventKey key;

    @Column("event_type")
    private String eventType;

    @Column("payload_ref")
    private String payloadRef;
}
```

Trong ví dụ này:

- `tenantId`, `eventDay`, `shard` được đánh dấu `PARTITIONED`: chúng xác định **một partition**.
- `occurredAt`, `eventId` được đánh dấu `CLUSTERED`: chúng phân biệt và sắp xếp hàng **bên trong partition**. Thứ tự `DESC` được định nghĩa bằng DDL CQL ở trên; entity thực tế cần đồng bộ metadata/mapping với schema và phiên bản Spring Data sử dụng.
- `CassandraRepository<EventRow, EventKey>` có thể thao tác theo **toàn bộ primary key**; câu hỏi “100 sự kiện gần nhất của tenant trong ngày” cần truy vấn riêng cung cấp **đủ partition key**, hoặc nhiều truy vấn và bước merge nếu ngày đã được shard.
- Với paging, ưu tiên các API dựa trên **paging state** của Cassandra/driver. Không coi paging kiểu offset trên bảng quan hệ là thao tác nhảy đến hàng thứ N không tốn chi phí. Với nhiều shard phải quản lý trạng thái từng shard và thứ tự merge.
- Consistency level của lần đọc/ghi ảnh hưởng số replica cần phản hồi và độ trễ; nó **không thay đổi** công thức tính số hàng logic hay giúp giảm kích thước của một partition. RF tăng dung lượng bản sao ở cấp cluster, chứ không chia nhỏ một partition key.

Entity ở trên là minh họa; khi đưa vào ứng dụng cần bổ sung các thành phần Java thích hợp để ánh xạ/khởi tạo khóa, đồng thời xác thực mapping với phiên bản Spring Data Cassandra thực tế.

## 12. Checklist trước khi chốt partition key

| Câu hỏi kiểm tra | Bằng chứng mong muốn |
| --- | --- |
| Truy vấn nóng nhất biết chính xác những thành phần partition key nào? | Có danh sách CQL với điều kiện `WHERE` rõ ràng |
| Tenant lớn nhất ghi bao nhiêu hàng **trong một bucket**? | Trung bình, p95/p99, đỉnh và dự báo |
| Kích thước hàng thực tế biến thiên thế nào? | Đo trên mẫu dữ liệu, tính cả overhead và workload update/TTL |
| Tốc độ ghi/đọc cao điểm vào cùng partition là bao nhiêu? | Metrics theo phút/giây và theo tenant/bucket |
| Trong 3, 6, 12 tháng, partition lớn nhất dự kiến tới đâu? | Kịch bản tăng trưởng và mức dự phòng |
| Bucket ngày/giờ/tháng có phù hợp truy vấn khoảng thời gian? | Số partition cần đọc, chi phí fan-out và latency |
| Có cần shard để tránh partition lớn hoặc nóng không? | Phép tính size/throughput và phương án merge/paging |
| TTL, update, delete và compaction đã được tính chưa? | Dung lượng logic và vật lý được theo dõi riêng |
| RF và số datacenter ảnh hưởng capacity thế nào? | Dự báo dung lượng theo từng datacenter và headroom |

### Tự kiểm tra với ba tình huống

**Tình huống A.** Tenant tạo 24.000 hàng/ngày, mỗi hàng 1.000 byte theo giả định lập kế hoạch. Partition key `(tenant_id, event_day)` chứa bao nhiêu dữ liệu cho một ngày?

**Đáp án:** khoảng 24.000 hàng và `24 MB`/partition, chưa tính overhead và khác biệt nén thực tế.

**Tình huống B.** Một tenant có 240.000 hàng/ngày, chọn bốn shard cân bằng trong một bucket ngày. Dự kiến mỗi partition bao nhiêu hàng? Đổi lại điều gì?

**Đáp án:** khoảng 60.000 hàng/partition. Truy vấn toàn bộ ngày cần truy cập tối đa bốn shard và ghép kết quả theo thứ tự thời gian; paging phức tạp hơn.

**Tình huống C.** Dữ liệu có TTL 14 ngày. Sau ngày thứ 14, có thể khẳng định dữ liệu đã biến mất hoàn toàn khỏi đĩa và không cần tính dung lượng cho compaction không?

**Đáp án:** Không. TTL làm dữ liệu hết hạn về mặt logic; việc thu hồi không gian lưu trữ vật lý còn phụ thuộc tombstone, SSTable và compaction.

---

**Ghi nhớ:** khi thiết kế bảng Cassandra theo truy vấn, hãy dự toán **`số hàng/partition × byte/hàng`**, kiểm tra cả **tốc độ ghi/đọc vào partition lớn nhất** và **tăng trưởng trong tương lai**. Time bucketing và sharding là công cụ điều chỉnh quy mô partition, nhưng tạo thêm chi phí đọc, merge và paging. Spring Data Cassandra giúp ánh xạ và truy vấn theo thiết kế đã chọn; chất lượng partition key vẫn quyết định phần lớn khả năng vận hành hiệu quả của hệ thống phân tán.

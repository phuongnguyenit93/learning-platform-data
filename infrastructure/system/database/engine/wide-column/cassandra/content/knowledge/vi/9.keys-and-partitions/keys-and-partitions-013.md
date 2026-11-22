# Đổi thiết kế khóa bằng bảng mới và kế hoạch di chuyển

Trong Apache Cassandra, lựa chọn `PRIMARY KEY` không chỉ quyết định một hàng được định danh thế nào. **Partition key** xác định token và tập replica lưu dữ liệu; **clustering columns** quy định cách các hàng được tổ chức trong phân vùng và kiểu truy vấn theo khoảng được hỗ trợ. Vì vậy, nếu hệ thống bắt đầu xuất hiện phân vùng quá lớn, khóa nóng, truy vấn phải lọc rộng hoặc khó giới hạn lịch sử, việc sửa thiết kế khóa thường là **một cuộc di chuyển dữ liệu và luồng truy cập**, chứ không phải thay đổi cấu hình đơn giản.

Cassandra **không hỗ trợ đổi tùy ý partition key hay clustering key của một bảng đang tồn tại bằng `ALTER TABLE`**. Cách phổ biến, có thể kiểm soát được là: **tạo bảng mới với khóa phù hợp, chuyển dữ liệu, đồng bộ các thay đổi đang diễn ra, kiểm tra rồi chuyển luồng đọc/ghi**. Quá trình này cần tính đến đặc tính phân tán: replication, consistency level, retry, dữ liệu đến trễ, TTL, tombstone, compaction và repair.

Bài học thuộc chương **Khóa và phân vùng**. Ví dụ xuyên suốt chuyển một bảng lưu toàn bộ lịch sử theo thiết bị sang bảng mới chia **bucket ngày**, để minh họa một kế hoạch từ khảo sát đến cắt chuyển (*cutover*) và quay lui (*rollback*) khi triển khai với CQL và ứng dụng Java.

Sau bài học, bạn có thể:

- Giải thích vì sao phải tạo **bảng mới** khi thay đổi tổ hợp partition/clustering key.
- So sánh truy vấn, kích thước phân vùng và phân phối tải của schema cũ và mới.
- Định nghĩa hàm ánh xạ dữ liệu **xác định, lặp lại được**, gồm khóa, bucket và định danh sự kiện.
- Lập thứ tự **dual-write/change capture → backfill → reconciliation → shadow read → cutover**.
- Nhận biết các rủi ro về cập nhật đồng thời, xóa dữ liệu, TTL, write timestamp và retry khi copy.
- Đặt tiêu chí kiểm chứng, rollback và giám sát hiệu năng sau khi chuyển.
- Viết ví dụ Java Driver 4.x để backfill có paging trong những cửa sổ dữ liệu được kiểm soát.

## 1. Vì sao không chỉ dùng `ALTER TABLE` để đổi khóa?

Cassandra cho phép một số thay đổi schema, chẳng hạn thêm hoặc bỏ cột thường theo các quy tắc và giới hạn của phiên bản. Tuy nhiên, **thành phần của primary key** quyết định định danh hàng và cách dữ liệu phân phối trên cluster.

Ví dụ bảng cũ:

```sql
CREATE TABLE events_by_device_old (
    tenant_id   text,
    device_id   uuid,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY (
        (tenant_id, device_id),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Đây là một phân vùng logic cho **mỗi cặp tenant–thiết bị**. Nếu muốn đổi thành một phân vùng **mỗi tenant–thiết bị–ngày**, thay đổi không chỉ là thêm một cột ngày: toàn bộ tuple dùng để tính token sẽ khác.

```text
Khóa cũ:
  partition key = (tenant_id, device_id)
  clustering    = (occurred_at, event_id)

Khóa mới:
  partition key = (tenant_id, device_id, event_day)
  clustering    = (occurred_at, event_id)

Hệ quả:
  cùng một sự kiện -> token/replica set của partition mới
                     có thể khác token/replica set cũ
```

**Không thực hiện** các cách sau với kỳ vọng khóa tự thay đổi:

- `ALTER TABLE` để “đổi primary key” như sửa cột thường.
- Chỉ thêm `event_day` thành **cột thường** rồi mong Cassandra tự chia dữ liệu theo ngày.
- Thay `CLUSTERING ORDER BY` để đổi vị trí của partition trong token ring.
- Tăng replication factor, chạy compaction hoặc repair để “chia đôi” một partition lớn.
- Thêm `ALLOW FILTERING` để tránh phải thiết kế lại đường truy vấn.

Với thiết kế khóa mới, cần một **bảng mới** và một kế hoạch chuyển đổi luồng đọc/ghi rõ ràng. Có thể đổi tên bảng hoặc dùng phiên bản hóa tên ở tầng ứng dụng, nhưng **đổi tên không thực hiện việc phân phối lại dữ liệu**; bản thân bảng mới mới chứa cấu trúc khóa mới.

## 2. Bắt đầu bằng truy vấn và triệu chứng, không bắt đầu bằng thao tác copy

Giả sử hệ thống IoT có hai kiểu truy vấn chính:

- **Q1:** lấy 100 sự kiện mới nhất của một thiết bị trong một ngày.
- **Q2:** lấy các sự kiện của thiết bị trong khoảng một giờ.
- **Q3:** tra cứu lịch sử thiết bị qua nhiều ngày, không yêu cầu một partition lookup duy nhất.

Bảng cũ `events_by_device_old` từng hoạt động ổn khi mỗi thiết bị có ít sự kiện. Khi một số thiết bị ghi liên tục, partition `(tenant_id, device_id)` có thể tích lũy nhiều tháng dữ liệu, tăng chi phí lưu trữ, compaction, repair và những truy vấn khoảng rộng.

Trước khi đổi schema, cần ghi lại bằng chứng:

| Mục cần khảo sát | Câu hỏi |
| --- | --- |
| **Query patterns** | Có bao nhiêu phần trăm truy vấn đọc 5 phút, một ngày hay nhiều tháng? Có luôn biết tenant và device không? |
| **Data size** | Phân bố hàng/cell/byte mỗi partition ra sao, đặc biệt max và p99? |
| **Access skew** | Thiết bị/tenant nào chiếm phần lớn đọc hoặc ghi? |
| **Retention** | Có TTL hay xóa nghiệp vụ không? Dữ liệu cũ phải được giữ bao lâu? |
| **Mutability** | Dữ liệu sự kiện có bất biến, cập nhật nội dung, hay xóa theo yêu cầu không? |
| **Consistency** | Yêu cầu đọc sau ghi là gì; client retry thế nào sau timeout? |
| **Topology** | RF, data center, replica placement, công suất đĩa và tải nền? |
| **Rollout** | Có thể tạm dừng ghi hay phải vận hành không gián đoạn? Có nguồn event để replay không? |

**Không có một ngưỡng MB hoặc số hàng cố định** phù hợp mọi cluster. Mục tiêu nên được diễn đạt bằng giới hạn đo được: ví dụ p99 đọc dưới SLO, kích thước partition ở tải đỉnh không vượt ngưỡng cảnh báo đã thử tải, và fan-out qua bucket không vượt ngân sách request của dịch vụ.

## 3. Thiết kế bảng mới theo truy vấn mục tiêu

Tạo bảng mới chia mỗi thiết bị thành các partition theo ngày UTC:

```sql
CREATE TABLE events_by_device_day_v2 (
    tenant_id   text,
    device_id   uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Cách phân tích:

| Trường | Bảng cũ | Bảng mới |
| --- | --- | --- |
| Partition key | `(tenant_id, device_id)` | `(tenant_id, device_id, event_day)` |
| Clustering columns | `occurred_at, event_id` | `occurred_at, event_id` |
| Hình dạng partition | Một thiết bị tích lũy toàn lịch sử | Một thiết bị có một partition cho mỗi ngày có dữ liệu |
| Đọc một ngày | Slice theo `occurred_at` trong partition lịch sử | Định vị đúng bucket ngày và slice |
| Đọc nhiều ngày | Một partition (nhưng có thể quá lớn) | Nhiều partition, phải hợp nhất kết quả |
| Chi phí ghi trong ngày | Mọi ghi cùng thiết bị vào một partition | Mọi ghi cùng thiết bị **trong ngày** vẫn vào một partition |

Chuyển sang bucket ngày giúp **giới hạn thời gian tích lũy** mỗi partition, nhưng **không bảo đảm** xử lý hot partition nếu một thiết bị ghi hàng chục nghìn sự kiện/giây trong ngày hiện tại. Khi tải cao, có thể cần bucket giờ/phút hoặc shard theo quy tắc ổn định; đổi lại sẽ tăng số partition phải đọc.

### Truy vấn Q1 trên bảng mới

```sql
SELECT occurred_at, event_id, event_type, payload
FROM events_by_device_day_v2
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 100;
```

Bảng khai báo `occurred_at DESC` nên các sự kiện mới hơn của **ngày đó** xuất hiện trước theo thứ tự clustering.

### Truy vấn Q2 trong một khoảng ngày

```sql
SELECT occurred_at, event_id, event_type, payload
FROM events_by_device_day_v2
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T09:00:00Z'
LIMIT 200;
```

Đây là một **partition lookup** và một đoạn clustering key. Với khoảng cắt qua ngày, ứng dụng phải đọc **mọi bucket liên quan**, rồi merge theo `occurred_at` và `event_id`. `CLUSTERING ORDER BY` không cung cấp thứ tự toàn cục giữa các partitions.

## 4. Định nghĩa phép ánh xạ khóa và nội dung trước khi di chuyển

Một phép di chuyển đáng tin cậy phải có quy tắc biến đổi **không phụ thuộc thời điểm chạy hoặc thứ tự xử lý**.

Giả sử dữ liệu nguồn gồm:

```text
tenant_id   = acme
device_id   = 327a71e9-f562-4b54-94b9-2138a9e30b12
occurred_at = 2026-11-21T23:40:10Z
event_id    = 8817a208-1858-4144-86e9-b24d9083e478
event_type  = temperature
payload     = 38.1
```

Quy tắc ánh xạ:

```text
event_day = UTC_DATE(occurred_at)

old_pk = (
  tenant_id, device_id,
  occurred_at, event_id
)

new_pk = (
  tenant_id, device_id, event_day,
  occurred_at, event_id
)
```

Cùng sự kiện được xử lý lại bao nhiêu lần thì `event_day` và toàn bộ new primary key **phải giữ nguyên**. Không lấy `event_day` từ “ngày hiện tại của máy chạy backfill” hoặc từ múi giờ mặc định không thống nhất.

### Các bất biến cần kiểm tra

1. **Định danh ổn định:** `event_id` không thay đổi qua retry/backfill.
2. **Timestamp ổn định:** `occurred_at` là thời điểm sự kiện đã được xác định và không bị tính lại.
3. **Bucket thống nhất:** writer, backfill và reader đều dùng **ngày UTC** của `occurred_at`.
4. **Payload không bị chuyển nghĩa:** dữ liệu mới phản ánh trường, kiểu và quy tắc biến đổi đã được thống nhất.
5. **Không mất tenant:** tất cả đường ghi/đọc bind `tenant_id` từ ngữ cảnh có quyền.
6. **Phạm vi duy nhất:** hai hàng khác nhau ở bảng cũ không được vô tình map vào cùng full primary key mới.

Nếu phép biến đổi làm **hai khóa cũ khác nhau trùng một khóa mới**, Cassandra sẽ ghi cùng hàng logic theo semantics upsert, có thể mất dữ liệu. Cần giải quyết va chạm định danh **trước** khi copy; không xem `IF NOT EXISTS` là phép sửa lỗi mapping.

### Bảng mapping giúp phát hiện ngoại lệ

| Trường hợp | Rủi ro | Cách quyết định |
| --- | --- | --- |
| Sự kiện đúng 00:00 UTC | Nhầm bucket ngày trước/ngày sau | Quy ước khoảng `[start, end)` và UTC. |
| Sự kiện đến muộn hai ngày | Writer gán vào ngày ghi hiện tại | Tính từ event time cố định. |
| Payload cũ thiếu cột | Giá trị `null`/mặc định khác dự định | Viết quy tắc chuyển đổi tường minh. |
| Event có timestamp bị sửa sau ghi | Partition key đích có thể đổi | Định nghĩa thao tác xóa khóa cũ và ghi khóa mới. |
| Tài khoản/thiết bị đổi tenant | Định danh nguồn và target thay đổi | Thiết kế quy trình move, không chỉ sửa cột thường. |
| Khóa cũ cho phép một ID nhiều lần | Map về cùng khóa mới và ghi đè | Thêm thành phần định danh cần thiết vào schema mới. |

## 5. Tổng quan kế hoạch di chuyển theo các giai đoạn

Với hệ thống cần tiếp tục hoạt động, một khung làm việc thường gồm:

```text
Khảo sát + thiết kế schema v2
             |
             v
Tạo bảng v2, triển khai đọc/ghi v2 ở chế độ kiểm soát
             |
             v
Bật thu nhận thay đổi bền vững (bao gồm delete/update)
             |
             v
Backfill dữ liệu lịch sử có checkpoint
             |
             v
Replay / reconcile mọi thay đổi trong khi backfill
             |
             v
Shadow read + kiểm chứng dữ liệu và hiệu năng
             |
             v
Cutover từng phần đọc/ghi, theo dõi và giữ rollback path
             |
             v
Kết thúc cửa sổ rollback, dừng phụ thuộc bảng cũ
             |
             v
Xóa bảng cũ theo quy trình sau khi được phê duyệt
```

Cấu trúc này **không phải một transaction duy nhất**. Nhiều thao tác xảy ra trên các partitions khác nhau, có thể trên các replica khác nhau; client có thể timeout giữa các bước. Vì thế **mốc tiến độ, cơ chế replay và điều kiện chuyển pha** là phần bắt buộc của kế hoạch.

### Bảng giai đoạn, điều kiện qua cửa

| Pha | Hành động | Điều kiện để chuyển tiếp |
| --- | --- | --- |
| 0. Thiết kế | Chốt query, schema mới, TTL, mapping, capacity | Test schema đáp ứng truy vấn và mục tiêu partition size. |
| 1. Chuẩn bị | Tạo bảng v2, deploy code có feature flag, metrics | Không ảnh hưởng luồng production cũ. |
| 2. Capture | Ghi lại mọi thay đổi cần đồng bộ từ mốc T0 | Replay được mutation và delete, có offset/checkpoint. |
| 3. Backfill | Copy lịch sử theo key/time window với giới hạn tải | Tiến độ bền vững, lỗi có thể retry, có thống kê. |
| 4. Bắt kịp | Replay delta từ T0, đối chiếu các phiên bản | Lag về mức chấp nhận, không bỏ sót thay đổi. |
| 5. Kiểm chứng | Shadow read và so sánh kết quả | Đạt tiêu chí độ đầy đủ, tính đúng và SLO. |
| 6. Cutover | Chuyển read/write path có kiểm soát | Có thể rollback, metrics theo dõi liên tục. |
| 7. Cleanup | Ngừng đường cũ và dọn dữ liệu | Hết cửa sổ rollback, có quyết định vận hành rõ ràng. |

Trong hệ thống nhỏ, có thể **tạm ngừng ghi ngắn hạn** để chụp trạng thái ổn định, copy delta cuối và chuyển. Cách này đơn giản hơn nhưng tạo thời gian gián đoạn. Trong hệ thống lớn không được dừng ghi, cần cơ chế change capture hoặc event log đủ tin cậy để không bỏ lỡ thao tác trong quá trình backfill.

## 6. Bảng mới phải sẵn sàng trước khi có dữ liệu

Cần triển khai schema mới như một tài nguyên độc lập:

```sql
-- Kiểm tra schema mục tiêu đã được tạo ở keyspace phù hợp:
DESCRIBE TABLE events_by_device_day_v2;
```

Trong kế hoạch thực tế, ngoài CQL `CREATE TABLE` còn phải xác nhận:

- **Keyspace replication strategy và RF** phù hợp topology và yêu cầu chịu lỗi.
- Cấu hình compaction/compression/TTL mặc định của bảng mới, nếu có, đã được chốt theo workload.
- Disk headroom đủ cho **hai bản dữ liệu cùng tồn tại**, SSTable tạm trong compaction, repair và thao tác backfill.
- Quyền CQL của tài khoản ứng dụng/backfill được cấp **tối thiểu cần thiết** cho bảng mới.
- Driver và schema metadata đã nhận biết table mới trước khi cho phép ghi.
- Alerts/read/write metrics có thể phân biệt bảng cũ và mới.

Đừng giả định chỉ vì hai bảng nằm cùng keyspace mà chúng có cùng phân bố byte hoặc latency. Partition key mới làm token/replica set thay đổi; cluster có thể cần **thời gian và tài nguyên** cho compaction, streaming/repair và cache warm-up.

**Quan trọng:** khi Cassandra mới tạo bảng, bạn không “đổi khóa” cho các SSTable cũ bằng metadata. Mọi hàng muốn có trong bảng mới phải được **ghi vào bảng mới** thông qua một quy trình copy/replay phù hợp.

## 7. Giữ dữ liệu phát sinh trong khi backfill: dual-write và change capture

Một bài toán khó nhất là **race** giữa copy lịch sử và các thao tác ghi đang diễn ra.

Giả sử backfill đọc sự kiện E ở bảng cũ, rồi một producer cập nhật hoặc xóa E, trong khi luồng copy vẫn đang chạy. Nếu backfill ghi bản cũ lên bảng mới **sau** thay đổi đó, dữ liệu đích có thể sai.

### Phương án A: nguồn sự kiện/đổi dữ liệu có thể replay

Với hệ thống có event log/outbox/CDC được vận hành đúng, một hướng an toàn là:

1. Tại mốc **T0**, bắt đầu ghi lại bền vững **mọi thay đổi làm biến động dữ liệu nguồn**, gồm create, update và delete.
2. Backfill trạng thái/hàng lịch sử từ bảng cũ theo các cửa sổ.
3. Replay các thay đổi từ T0 theo một thứ tự đủ để tái dựng trạng thái đích, kèm **idempotency**.
4. Khi gần bắt kịp, tạo **write barrier** hoặc một cơ chế chuyển quyền ghi có kiểm soát để xác nhận đã xử lý đến **watermark** cuối.
5. Shadow read, kiểm chứng và chỉ sau đó chuyển read path.

**Lưu ý:** dùng từ “CDC” không tự bảo đảm đã thu đủ mọi loại thao tác và thứ tự. Phải xác minh nguồn thay đổi lưu được *delete*, retry, offset và mức ordering cần thiết cho mô hình dữ liệu. Nếu chỉ thu sự kiện **insert** nhưng nghiệp vụ có xóa/cập nhật, replay không tái dựng đúng trạng thái.

### Phương án B: dual-write trong ứng dụng

Trong giai đoạn chuyển đổi, writer có thể gửi mutation tương ứng vào **cả bảng cũ và mới**:

```text
Request nghiệp vụ E
        |
        +--> write old table
        |
        +--> write new table
        |
        +--> ghi lại trạng thái/offset để xử lý khi một nhánh thất bại
```

Nhưng **hai lệnh ghi độc lập không tạo transaction nguyên tử xuyên bảng**. Có thể xảy ra:

| Kết quả | Tình huống |
| --- | --- |
| Old thành công, new thành công | Hai bảng đã nhận mutation theo mức consistency riêng. |
| Old thành công, new timeout | New **có thể đã ghi** hoặc chưa; cần replay/idempotent retry. |
| Old timeout, new thành công | Old có thể đã ghi hoặc chưa; phải giữ quy tắc source-of-truth. |
| Cả hai timeout | Không thể chỉ dựa vào phản hồi client để suy ra trạng thái cluster. |

Một đoạn code kiểu `writeOld(); writeNew();` **không đủ** nếu gặp lỗi giữa hai bước. Cần nguồn sự kiện bền vững, outbox/queue có khả năng replay hoặc một phương án dừng ghi để đồng bộ cuối. Không tuyên bố có “exactly once” toàn nghiệp vụ chỉ vì Cassandra upsert cùng primary key.

### Chốt nguồn dữ liệu có thẩm quyền theo pha

Một quy ước dễ vận hành:

- **Trước cutover:** bảng cũ hoặc event log nguồn là **source of truth**; bảng mới đang được xây dựng và đối chiếu.
- **Trong cutover:** có mốc rõ ràng xác định ghi nào đã thuộc đường mới, các request cũ/in-flight xử lý ra sao.
- **Sau cutover:** bảng mới trở thành source of truth; rollback chỉ được phép khi đường cũ vẫn nhận được mọi thay đổi cần thiết.

Không nên để mỗi instance tự quyết định “bảng nào đúng” dựa trên feature flag chưa được đồng bộ. Điều đó có thể tạo ra split-brain ở tầng ứng dụng.

## 8. Backfill lịch sử: đọc có giới hạn và checkpoint có thể khôi phục

Backfill không nên mở `SELECT *` toàn bộ bảng từ một client rồi giữ kết quả trong RAM. Với Cassandra, cần **lập danh sách các partition keys nguồn** và **cửa sổ clustering time** để đọc theo đường khóa hỗ trợ.

Giả sử có một danh sách tenant/device đã được hệ thống nguồn cung cấp. Với một thiết bị, đọc một giờ dữ liệu của bảng cũ:

```sql
SELECT occurred_at, event_id, event_type, payload
FROM events_by_device_old
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T09:00:00Z';
```

Lệnh trên cung cấp đủ partition key cũ và một khoảng theo clustering column. Đích được xác định bằng `event_day = UTC_DATE(occurred_at)`.

Đối với backfill lượng lớn:

- Chia việc theo **tenant/device + cửa sổ thời gian**; không giả định một giờ luôn nhỏ với mọi thiết bị.
- Dùng **driver paging** để không tải toàn bộ kết quả vào một lần phản hồi.
- **Giới hạn concurrency/throughput**, đặc biệt trên partition nguồn rất lớn để không ảnh hưởng workload đang chạy.
- Lưu **checkpoint bền vững** ở cấp công việc/cửa sổ hoặc vị trí truy cập, chỉ đánh dấu hoàn tất sau khi mọi bản ghi thuộc cửa sổ đã được ghi và xác nhận theo chính sách.
- Khi một worker bị dừng, chạy lại cửa sổ chưa hoàn thành theo **cùng full primary key**; copy phải idempotent về mặt định danh.
- Nếu dùng paging state, không coi nó là dữ liệu bất biến có thể dùng mãi qua thay đổi schema/query/version; cần quy tắc checkpoint phù hợp.
- Theo dõi lỗi phân loại: invalid key, serialization, timeout mơ hồ, tombstone, rate limit, schema mismatch.

### Không lấy danh sách khóa nguồn bằng cách quét vô hạn

Với bảng cũ có phân vùng rất lớn hoặc hệ thống hàng terabyte, tìm mọi partition key bằng CQL quét toàn bảng có thể rất tốn kém. Có thể lấy worklist từ catalog/nghiệp vụ, danh sách thiết bị từ bảng phục vụ tra cứu, nguồn ingest hoặc công cụ bulk export phù hợp đã được đánh giá. Nhưng không đọc các file khác hay tự giả định một danh sách thiết bị luôn đầy đủ: **độ đầy đủ của worklist là một điều kiện kiểm chứng độc lập**.

Một cách ghi checkpoint ở mức khái niệm:

```text
job_id: migrate-device-day-v2
source_partition: ('acme', device-01)
window: [2026-11-21T08:00Z, 2026-11-21T09:00Z)
state: IN_PROGRESS | DONE | FAILED
rows_seen: 15720
rows_written: 15720
retry_attempts: 2
source_watermark: offset/sequence từ event log nếu có
```

Đây là định dạng minh họa cho tiến độ vận hành, **không phải bảng CQL bắt buộc**. Chỉ ghi `DONE` khi bước xác nhận và điều kiện replay/đối chiếu của cửa sổ thực sự đạt.

## 9. Java Driver: ví dụ copy một cửa sổ dữ liệu

Ví dụ Java Driver 4.x sau đây minh họa **phép ánh xạ và đọc theo trang**. Nó phù hợp để hiểu kỹ thuật backfill cho **các bản ghi bất biến, không TTL và không delete/update đang cạnh tranh**; chưa phải hệ thống migration production đầy đủ.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

public final class DeviceEventBackfill {
    private final CqlSession session;
    private final PreparedStatement readOld;
    private final PreparedStatement writeNew;

    public DeviceEventBackfill(CqlSession session) {
        this.session = session;

        this.readOld = session.prepare(
            "SELECT occurred_at, event_id, event_type, payload " +
            "FROM events_by_device_old " +
            "WHERE tenant_id = ? AND device_id = ? " +
            "AND occurred_at >= ? AND occurred_at < ?"
        );

        this.writeNew = session.prepare(
            "INSERT INTO events_by_device_day_v2 " +
            "(tenant_id, device_id, event_day, occurred_at, " +
            "event_id, event_type, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        );
    }

    // Đọc/copy một lát thời gian đã giới hạn bởi bộ điều phối.
    // Checkpoint và nguồn replay phải nằm ngoài phương thức minh họa này.
    public long copyWindow(
            String tenantId,
            UUID deviceId,
            Instant startInclusive,
            Instant endExclusive) {

        if (!startInclusive.isBefore(endExclusive)) {
            throw new IllegalArgumentException("Invalid time range");
        }

        BoundStatement query = readOld.bind(
            tenantId, deviceId, startInclusive, endExclusive
        ).setPageSize(200);

        long copied = 0;

        for (Row row : session.execute(query)) {
            Instant occurredAt = row.getInstant("occurred_at");
            UUID eventId = row.getUuid("event_id");

            // Cố định cách bucket hóa: ngày UTC của thời điểm sự kiện.
            LocalDate eventDay =
                occurredAt.atZone(ZoneOffset.UTC).toLocalDate();

            session.execute(writeNew.bind(
                tenantId,
                deviceId,
                eventDay,
                occurredAt,
                eventId,
                row.getString("event_type"),
                row.getString("payload")
            ));
            copied++;
        }

        return copied;
    }
}
```

**Điều ví dụ làm đúng:**

1. Đọc bảng cũ với **đầy đủ partition key**, ràng buộc một khoảng thời gian.
2. Dùng `setPageSize(200)` để truy vấn được fetch theo trang qua driver.
3. Tính `LocalDate` từ `Instant` bằng `ZoneOffset.UTC`, tránh lệch bucket do timezone.
4. Giữ nguyên `event_id` và `occurred_at`; retry cùng dữ liệu sẽ đến **cùng primary key mới**.
5. Dùng `PreparedStatement` thay vì nối giá trị vào chuỗi CQL.

**Điều ví dụ chưa giải quyết:**

- Ghi đồng bộ từng hàng có throughput hạn chế; production có thể cần async với **bounded concurrency** và backpressure.
- Nó chưa ghi checkpoint bền vững, chưa đánh dấu cửa sổ đã được replay đến watermark nào.
- Nó chưa bảo tồn **TTL, write timestamp**, chưa xử lý tombstone/xóa và cập nhật đồng thời.
- Nếu lệnh ghi new timeout, không thể kết luận chắc chắn lệnh đã thất bại; chỉ có thể retry an toàn khi có đủ cơ chế kiểm soát.
- Nếu dữ liệu nguồn thay đổi giữa lúc SELECT và INSERT, kết quả đích có thể là ảnh chụp cũ; cần pha replay và quy tắc ordering.

**Không dùng trực tiếp phương thức này để tuyên bố đã migration thành công** nếu nguồn có delete, TTL, concurrent update hoặc yêu cầu đối chiếu nghiêm ngặt.

## 10. Các rủi ro tính đúng dữ liệu: TTL, timestamp và tombstone

Chuyển một hàng từ bảng A sang B không đơn giản là đọc các cột sống rồi `INSERT` lại. Cassandra có semantics của **cell TTL**, **write timestamp**, **tombstone**, cập nhật và phân giải xung đột.

### 10.1. TTL: copy có thể vô tình kéo dài tuổi thọ

Giả sử payload ở nguồn được ghi với TTL 30 ngày và đã tồn tại 25 ngày. Nếu backfill đọc payload rồi ghi mới không TTL, dữ liệu có thể tồn tại **vĩnh viễn** ở đích. Nếu ghi lại với TTL **30 ngày từ ngày backfill**, nó lại tồn tại thêm 30 ngày, vượt chính sách retention.

```sql
-- Minh họa xem TTL và write timestamp của một cột thường ở nguồn:
SELECT occurred_at, event_id, TTL(payload), WRITETIME(payload)
FROM events_by_device_old
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at <  '2026-11-21T09:00:00Z';
```

`TTL(payload)` phản ánh thời gian còn lại của cell khi còn TTL và giá trị còn sống; các cell khác có thể có TTL khác nhau. Cần chọn chính sách di chuyển:

- **Bảo toàn thời điểm hết hạn:** biết deadline lưu trữ nguồn, tính TTL còn lại tại thời điểm ghi đích và xử lý các giá trị đã hết hạn.
- **Định nghĩa retention mới rõ ràng:** chỉ làm khi nghiệp vụ cho phép kéo dài/rút ngắn thời hạn, có quy tắc riêng cho backfill.
- **Không copy dữ liệu đã hết hạn** chỉ để đạt số hàng bằng nhau; so sánh phải xét trạng thái sống tại cùng mốc logic.

Việc dùng `USING TTL` trên một mutation mới không tự bảo toàn mọi TTL ở mức cell của hàng nguồn. Với dữ liệu có TTL không đồng đều, cần kế hoạch theo từng loại cell hoặc chiến lược tái dựng thích hợp.

### 10.2. Write timestamp: backfill có thể ghi đè cập nhật mới

Cassandra giải quyết xung đột giá trị cell bằng **write timestamp** và các quy tắc đi kèm. Một bản ghi cũ được backfill **sau** update mới ở đích có thể mang timestamp cao hơn và thắng dữ liệu mới, dù nội dung nó cũ hơn.

```text
08:00  Nguồn có payload = A
08:05  Backfill đọc payload = A
08:06  Writer cập nhật payload = B ở hai bảng
08:07  Backfill ghi payload = A vào bảng mới với timestamp mới
       -> Có nguy cơ A ghi đè B trong bảng mới
```

Vì vậy cần cơ chế **ordering/fencing hoặc versioning**:

- Với dữ liệu **append-only bất biến**, không có update/delete, phép copy idempotent đơn giản hơn.
- Với dữ liệu mutable, cần lưu mutation log có version/offset và áp dụng bản cuối cùng theo quy tắc đã định nghĩa.
- Có thể phải bảo toàn timestamp nguồn hoặc dùng phiên bản nghiệp vụ để chống ghi lùi; sử dụng `USING TIMESTAMP` đòi hỏi hiểu rõ TTL, tombstone và xung đột, không phải công thức áp dụng mù quáng.
- Pha replay delta sau backfill phải được thiết kế sao cho mutation **mới hơn theo nghiệp vụ** không bị bản snapshot cũ ghi đè.

### 10.3. Delete không xuất hiện như một hàng sống trong `SELECT`

Khi người dùng xóa sự kiện nguồn, một câu `SELECT` thông thường không trả về “hàng đã xóa” để backfill có thể copy xóa. Tombstone vẫn có vai trò trong replication/repair và compaction.

Nếu đích đã có sự kiện và source xóa nó **trong khi migration**, một luồng backfill chỉ đọc các hàng còn sống không thể suy ra rằng cần xóa hàng tương ứng ở đích. Cần:

- **Capture thao tác delete** từ nguồn đáng tin cậy rồi replay sang bảng mới.
- Hoặc có **cửa sổ dừng ghi/xóa** đủ để đối chiếu cuối, kèm quy trình xử lý các thay đổi trước đó.
- Không quên xóa **cả phân vùng**, xóa slice, xóa cell, TTL expiry và những thao tác nghiệp vụ làm đổi primary key.

Ngoài ra, bản copy cũ và tombstone có write timestamps khác nhau có thể khiến thao tác xóa không thắng như kỳ vọng. Cần kiểm thử **resurrection** sau replay/repair/compaction, nhất là khi đã có replica bỏ lỡ thao tác xóa.

### 10.4. Static columns, collection và counter

Nếu bảng nguồn có **static columns** chung theo partition cũ, khi chia một partition thành nhiều partition ngày, metadata đó sẽ được ánh xạ ra sao?

- Nếu metadata **thực sự theo thiết bị**, một bảng metadata riêng theo `(tenant_id, device_id)` có thể rõ nghĩa hơn.
- Nếu metadata **theo ngày**, có thể copy đến các partition ngày tương ứng, với quy tắc cập nhật.
- Collection nhiều phần tử hoặc dữ liệu có counter cần kế hoạch chuyên biệt; **không** xem replay phép cộng là idempotent như `INSERT` một payload bất biến.

Các kiểu dữ liệu và semantics không được khẳng định là “đã copy đúng” chỉ vì số hàng gần bằng nhau.

## 11. Consistency, replication, LWT và giới hạn của transaction

Một số kỹ thuật thường bị hiểu nhầm là có thể tự bảo đảm migration:

| Công cụ/cơ chế | Giúp gì | Không tự bảo đảm |
| --- | --- | --- |
| **Replication factor** | Có nhiều bản sao trên tập replica theo keyspace strategy. | Không đồng bộ hai bảng hoặc đổi partition key tự động. |
| **`LOCAL_QUORUM`/quorum thích hợp** | Định nghĩa mức xác nhận đọc/ghi trong data center/topology liên quan. | Không tạo transaction nguyên tử giữa hai bảng. |
| **Read repair/repair** | Hỗ trợ sửa sai khác replica trong phạm vi dữ liệu Cassandra. | Không copy dữ liệu từ bảng cũ sang bảng mới theo mapping nghiệp vụ. |
| **LWT `IF NOT EXISTS`** | Chống hai client đồng thời tạo một full primary key khi điều kiện không tồn tại. | Không bảo toàn thứ tự update/delete xuyên các partition keys hoặc bảng. |
| **Logged batch** | Có semantics batch riêng và cơ chế phục hồi mutation, với chi phí vận hành. | Không thay thế migration workflow, snapshot, reconciliation và read cutover. |
| **`LIMIT`/paging** | Giới hạn phản hồi hoặc phân trang read path. | Không làm partition nhỏ hơn và không xác minh dữ liệu toàn bảng. |

Cần chọn consistency level thích hợp trong từng pha theo topology và SLO. Nhưng **không nên giải thích sự không nhất quán giữa bảng cũ và mới chỉ là vấn đề replica stale**: hai bảng là hai cấu trúc dữ liệu độc lập, không tự nhận các mutation của nhau.

Nếu cần bảo đảm một mã nghiệp vụ chỉ được tạo một lần, phải xét **phạm vi uniqueness của full primary key ở bảng mới**. Việc thêm/bỏ thành phần khóa có thể thay đổi cả phạm vi trùng lặp và ứng xử của `IF NOT EXISTS`.

## 12. Kiểm chứng dữ liệu: nhiều lớp, không chỉ đếm hàng

Một bản migration tốt cần có **kết quả đối chiếu có thể lặp lại** và tiêu chí hoàn tất được chấp thuận trước khi chuyển traffic.

### 12.1. Kiểm chứng schema và truy vấn

- `CREATE TABLE` có đúng kiểu cột, primary key, clustering order và TTL/compaction policy?
- Câu truy vấn Q1/Q2 trong schema mới có **đầy đủ partition key**?
- Khoảng `[start, end)` và bucket UTC xử lý chính xác ngày cuối/tháng cuối?
- Query nhiều bucket có merge theo comparator ổn định và giới hạn concurrency?
- Feature flag có thể định tuyến tenant/thiết bị theo phiên bản bảng đã chọn?

### 12.2. Kiểm chứng độ đầy đủ theo cửa sổ

Có thể đối chiếu theo worklist `(tenant, device, day)`:

| Kiểm chứng | Cách làm | Giới hạn |
| --- | --- | --- |
| Số sự kiện theo cửa sổ | Dùng thống kê ingest/backfill hoặc đếm có kiểm soát ở phạm vi nhỏ | `SELECT COUNT(*)` trên partition cực lớn có thể gây tải nặng. |
| Tập full primary keys | Lấy mẫu có cấu trúc hoặc so sánh key sets của một cửa sổ giới hạn | Đếm bằng nhau không bảo đảm cùng bộ khóa. |
| Checksum payload | Chuẩn hóa serialization/NULL và hash theo từng lô | Phải thống nhất quy tắc hash, ordering và TTL. |
| TTL/expiry | Kiểm tra các sự kiện gần deadline, đã xóa, đã hết TTL | Trạng thái sống có thể thay đổi theo thời gian. |
| Delete/update | Replay mutation log và kiểm tra trạng thái cuối | Chỉ copy insert không đủ. |
| Read semantics | Shadow read Q1/Q2 trên old/new và so kết quả | Hai đường đọc có thể khác thứ tự qua bucket; cần normalize. |

**Không dùng `COUNT(*)` quét toàn bảng production** rồi kết luận migration hoàn hảo chỉ vì hai tổng gần bằng nhau. Cần kết hợp **độ phủ worklist, watermark của change log, mẫu so sánh có chủ đích và thống kê theo từng cửa sổ**.

### 12.3. Shadow read

Tầng dịch vụ vẫn trả kết quả từ bảng cũ, đồng thời **đọc bảng mới ở chế độ bóng** cho một mẫu request:

```text
Client query Q1
      |
      +--> old table -> trả response cho client
      |
      +--> new table -> so sánh nội bộ, không trả ra client
                         |
                         v
               metrics: match / mismatch / timeout
```

Dữ liệu cần được normalize theo cùng logic: nếu hai bảng có khác biệt về thứ tự hoặc trang kết quả, không so nguyên chuỗi JSON khi semantics vẫn tương đương. Kiểm chứng phải bao gồm **query không có dữ liệu, time boundary, duplicate IDs, delete/TTL và event đến trễ**, không chỉ tenant nhỏ có dữ liệu đơn giản.

Shadow read cũng tạo tải mới trên cluster; cần sampling và giới hạn concurrency để việc kiểm thử không làm tăng lỗi production.

## 13. Cutover: chuyển đọc và ghi từng bước

Khi backfill và replay đã đạt điều kiện, có thể chuyển traffic theo từng nhóm tenant/thiết bị hoặc theo phần trăm request có thể định tuyến nhất quán.

### Phương án chuyển có kiểm soát

1. **Chốt mốc đồng bộ:** change log đã replay đến watermark đã định nghĩa, không có lỗi chưa xử lý ở tập dữ liệu sẽ chuyển.
2. **Drain in-flight writes hoặc dùng write barrier:** tránh request đang ghi theo cấu hình cũ đi “lọt” sau mốc chuyển.
3. **Bật read path mới ở tỷ lệ nhỏ:** bắt đầu từ một nhóm tenant/thiết bị ít rủi ro, quan sát mismatch và p99.
4. **Chuyển dần:** tăng traffic khi metrics và điều kiện dữ liệu đạt chuẩn.
5. **Duy trì đường rollback:** nếu còn cần revert về old, phải tiếp tục đồng bộ các thay đổi từ new sang old hoặc có nguồn sự kiện có thể replay cả hai hướng, theo kế hoạch đã chốt.
6. **Ổn định rồi mới dọn:** ngừng đường cũ, chốt checkpoint và thời gian lưu rollback trước khi xóa schema/dữ liệu cũ.

**Lưu ý về phần trăm request:** nếu cùng tenant có request đọc cũ/mới luân phiên, có thể xuất hiện khác biệt trang/cursor. Thường nên dùng định tuyến **ổn định theo tenant, thiết bị hoặc phiên** và kiểm soát các request đang mở, thay vì random từng request không có ngữ nghĩa.

### Điều kiện tự động ngừng rollout

Ví dụ tiêu chí dừng (các giá trị là chính sách giả định, phải hiệu chỉnh theo SLO):

- Mismatch dữ liệu vượt ngưỡng đã thống nhất.
- p99 latency hoặc timeout tăng liên tục so với đường cũ.
- Rate backfill/replay không theo kịp ingest, lag tăng.
- Replica I/O, pending compactions, GC hoặc disk headroom vượt ngân sách.
- Có lỗi phân quyền xuyên tenant hoặc lỗi mapping bucket/shard.
- Phát hiện dữ liệu bị xóa xuất hiện trở lại hoặc TTL bị kéo dài ngoài policy.

Khi có tín hiệu dừng, cần **dừng mở rộng traffic và điều tra**, không tự động xóa bảng mới hoặc cũ khi chưa hiểu trạng thái dữ liệu của từng pha.

## 14. Rollback không đơn giản là đổi cờ đọc

Nếu bảng mới đã trở thành nơi nhận ghi chính, một thao tác “đổi read flag về bảng cũ” có thể làm **mất khả năng nhìn thấy dữ liệu mới** nếu bảng cũ không còn được cập nhật.

Bảng quyết định:

| Trạng thái | Rollback khả thi thế nào? |
| --- | --- |
| Chưa chuyển ghi, old vẫn là source of truth | Có thể dừng shadow read/new path; dữ liệu old không bị bỏ qua. |
| Dual-write và mọi mutation vẫn replay được | Có thể quay về old sau khi xác minh old đã bắt kịp watermark. |
| Đã ngừng ghi old, chỉ new nhận dữ liệu | Cần backfill/replay ngược delta hoặc thực hiện một đợt migration mới. |
| Đã xóa old/table cũ | Không còn rollback nhanh; phải dùng phục hồi từ bản sao/backup nếu chính sách cho phép. |

Một kế hoạch rollback tốt phải ghi rõ:

- **Ai** được phép quyết định rollback và trong điều kiện nào?
- **Bảng nào là source of truth** tại từng pha?
- **Watermark/offset** cần đạt trước khi chuyển lại?
- **TTL/delete/update** đã được đồng bộ sang đường rollback chưa?
- **Client paging token/cursor** có còn tương thích khi đổi read path?
- Khi nào **chấm dứt** khả năng rollback và được phép dọn tài nguyên cũ?

Mục tiêu là tránh trạng thái ứng dụng “đọc bảng cũ nhưng ghi bảng mới” ngoài chủ đích, hoặc một số instance quay về cũ trong khi phần khác vẫn xử lý theo schema mới.

## 15. Quan sát tài nguyên trong migration

Trong nhiều đợt di chuyển lớn, lỗi không chỉ nằm ở dữ liệu sai mà còn ở việc backfill gây **quá tải cluster**.

| Nhóm số liệu | Dùng để làm gì? |
| --- | --- |
| **Source read latency / target write latency** | Biết backfill có làm chậm ứng dụng hay không. |
| **Rate backfill (rows/s, bytes/s)** | Đo tốc độ copy thực tế và ước lượng công việc còn lại. |
| **Checkpoint tiến độ và số lỗi retry** | Phát hiện worker kẹt/đọc lặp hoặc cửa sổ bỏ sót. |
| **Change-log/replay lag** | Biết bảng đích còn chậm bao nhiêu so với source-of-truth. |
| **p95/p99/timeout của production** | Quyết định có giảm tải backfill hoặc dừng rollout không. |
| **SSTables per read / tombstone scans** | Phát hiện read amplification, dữ liệu xóa gây tốn chi phí. |
| **Pending compactions / disk headroom** | Kiểm tra backlog và dung lượng tạm khi hai bảng cùng tồn tại. |
| **CPU/GC/network/I/O của node/replica** | Phát hiện nguồn bị nóng hoặc target phân phối lệch. |
| **Partition size/cell histogram của v2** | Xác nhận schema mới thực sự giảm phần đuôi phân vùng lớn. |
| **Shadow mismatch/permission failures** | Đánh giá đúng dữ liệu và an toàn đa tenant. |

Các lệnh thông thường để điều tra ở mức bảng (tùy phiên bản Cassandra):

```bash
nodetool tablestats app_ks.events_by_device_old
nodetool tablestats app_ks.events_by_device_day_v2

nodetool tablehistograms app_ks events_by_device_day_v2
```

Cần đọc kết quả theo **phạm vi node và phiên bản**, không coi histogram là số đo chính xác tức thời cho tất cả partition sống. Quá trình backfill cũng không làm Cassandra tự chuyển dữ liệu cũ từ một SSTable sang bảng mới: các mutation mới tạo tài nguyên lưu trữ mới và compaction về sau.

### Backpressure và quản lý tải

- Giới hạn số cửa sổ được xử lý đồng thời theo tenant/device và node.
- Ưu tiên tenant nhỏ trước để phát hiện lỗi mapping và xác minh tooling, không bắt đầu bằng tenant nóng nhất.
- Dành tài nguyên cho query production; tự động giảm tốc khi p99, I/O hoặc compaction backlog vượt ngân sách.
- Không dùng batch khổng lồ chỉ để tăng số row mỗi request; kiểm thử chi phí mutation/batch và throughput thực.
- Khi lỗi mạng/timeout, retry phải **giữ nguyên full primary key** và có chính sách backoff, không tạo ID hoặc bucket mới.

## 16. Bài tập tình huống: chuyển khóa để tránh large partition

Một nền tảng quản lý sự kiện có bảng cũ:

```sql
CREATE TABLE user_events_old (
    tenant_id   text,
    user_id     uuid,
    event_time  timestamp,
    event_id    uuid,
    payload     text,
    PRIMARY KEY ((tenant_id, user_id), event_time, event_id)
);
```

Mỗi user có thể sinh **10 sự kiện/giây**, payload logic **700 byte/sự kiện**, giữ dữ liệu theo retention **30 ngày**. Hệ thống vẫn nhận ghi trong thời gian migration. Truy vấn mới chủ lực là đọc một user trong **một ngày**.

Đề xuất bảng mới:

```sql
CREATE TABLE user_events_by_day_v2 (
    tenant_id   text,
    user_id     uuid,
    event_day   date,
    event_time  timestamp,
    event_id    uuid,
    payload     text,
    PRIMARY KEY (
        (tenant_id, user_id, event_day),
        event_time,
        event_id
    )
);
```

**Câu hỏi:**

1. Vì sao không chỉ thêm `event_day` bằng `ALTER TABLE ADD` vào bảng cũ?
2. Nếu user phát sinh 10 sự kiện/giây trong 24 giờ, mỗi partition ngày dự kiến có bao nhiêu hàng và payload logic?
3. Với retention 30 ngày, partition cũ có thể tích lũy bao nhiêu hàng nếu không có giới hạn khác?
4. Nếu backfill dùng ngày **hiện tại** để tính `event_day` cho event cũ, lỗi gì xuất hiện?
5. Nếu dual-write cũ thành công, mới timeout, có thể kết luận bảng mới chưa có hàng không?
6. Nếu event E đã bị xóa khỏi old trong lúc backfill, chỉ copy những hàng `SELECT` còn sống có bảo đảm xóa E ở v2 không?
7. Tại sao ghi lại TTL 30 ngày khi backfill một event đã 25 ngày tuổi có thể sai?
8. `LIMIT 100` và driver paging có tự chứng minh đã chuyển đủ hàng không?
9. Nếu cutover chỉ ghi v2 trong 2 ngày rồi rollback đọc old, điều gì có thể thiếu?
10. Những điều kiện nào cần kiểm tra trước khi xóa `user_events_old`?

**Đáp án gợi ý:**

1. Vì `event_day` cần trở thành **thành phần partition key mới**. Thêm cột thường không làm đổi token/phân vùng của dữ liệu cũ.
2. `10 × 86.400 = 864.000 hàng/ngày`; payload `864.000 × 700 = 604.800.000 byte ≈ 576,8 MiB`, chưa overhead và replica.
3. `864.000 × 30 = 25.920.000 hàng` trong một partition user nếu không có TTL/xóa hoặc cơ chế chia khác; đây chỉ là giả định tính toán.
4. Sự kiện được ghi sai bucket, reader truy vấn ngày sự kiện không tìm đúng partition hoặc các event nhiều ngày dồn vào bucket hiện tại.
5. **Không.** Client timeout có thể xảy ra sau khi cluster đã áp dụng mutation; cần kiểm tra/retry idempotent.
6. **Không.** `SELECT` không trả mutation xóa như một row sống; cần replay delete hoặc quy trình đối chiếu có kiểm soát.
7. TTL mới tính từ thời điểm backfill sẽ kéo dài vòng đời sự kiện vượt retention mong muốn nếu không tính phần thời gian đã trôi qua.
8. **Không.** Chúng chỉ kiểm soát response/paging, không bảo đảm độ phủ worklist, mutational correctness hay không bỏ sót hàng.
9. Bảng old có thể thiếu các sự kiện của hai ngày gần nhất; rollback cần đồng bộ ngược hoặc replay để old bắt kịp.
10. Cần xác nhận data parity, watermark/replay, SLO, client đã chuyển hết, không còn phụ thuộc, hết rollback window và có quyết định cleanup được phê duyệt.

### Bài tập thiết kế mở rộng

Hãy viết kế hoạch gồm **một bảng công việc migration** và **hai tính năng feature flag**:

- Cờ xác định source-of-truth/đường ghi.
- Cờ xác định đường đọc chủ lực và shadow read.

Trong kế hoạch, hãy chỉ ra cách đảm bảo không bỏ sót **event đến trễ**, **update**, **delete**, và cách đo ảnh hưởng lên p99 của tenant đang hoạt động. Mục tiêu không phải chọn một câu lệnh CQL duy nhất, mà tạo một quy trình **có thể khôi phục sau lỗi**.

## 17. Checklist triển khai trước khi công bố hoàn thành

- [ ] Schema v2 được tạo đúng primary key, clustering order, TTL/compaction và replication phù hợp.
- [ ] Hàm mapping old → new được kiểm tra với timestamp UTC, ranh giới ngày và trường hợp va chạm khóa.
- [ ] Có worklist nguồn đầy đủ, partition/time window và checkpoint bền vững.
- [ ] Có cách thu nhận và replay create/update/delete phát sinh khi backfill; thứ tự và semantics đã được thử nghiệm.
- [ ] Có quy tắc bảo toàn hoặc chuyển đổi rõ ràng TTL, write timestamp, tombstone và metadata static/collection nếu sử dụng.
- [ ] Backfill có paging, bounded concurrency, throttle, retry an toàn và metric tiến độ.
- [ ] Đã đối chiếu theo key/window, shadow read các truy vấn chính và xử lý mismatch.
- [ ] Change stream đã bắt kịp watermark cần thiết, các write in-flight đã được kiểm soát.
- [ ] Cutover có owner, runbook, mốc thời gian, ngưỡng dừng và giám sát p95/p99/timeout.
- [ ] Rollback path vẫn có thể thấy đủ dữ liệu từ sau mốc chuyển; không chỉ là đổi cờ.
- [ ] Retention và thời điểm xóa bảng cũ được phê duyệt sau khi hết rollback window.
- [ ] Không coi trạng thái “copy xong” là đủ để khẳng định dữ liệu chính xác hoặc hệ thống đã sẵn sàng.

## 18. Ghi nhớ

- **Đổi partition key hoặc clustering key** trong Cassandra thường đòi hỏi **tạo bảng mới và migration**, vì khóa ảnh hưởng định danh hàng, token, replica set và đường truy vấn.
- **Schema mới phải bắt đầu từ query**: ví dụ thêm bucket ngày vào partition key làm phân vùng ngắn hơn nhưng khiến truy vấn nhiều ngày cần fan-out và merge.
- **Định danh bất biến** — tenant, thiết bị, event time, event ID và bucket — là nền tảng để retry/backfill không tạo hàng trùng.
- **Backfill không tự đồng bộ các ghi đồng thời**: cần change capture, replay, fencing/watermark và kiểm chứng; dual-write đơn giản có thể thất bại từng nhánh.
- **TTL, tombstone, write timestamp và cập nhật/xóa** là những rủi ro tính đúng dữ liệu, không phải chi tiết phụ có thể bỏ qua.
- **Consistency level, replication, compaction và repair** có vai trò riêng; chúng không biến hai bảng thành một transaction hoặc tự thay primary key.
- **Cutover và rollback** phải dựa trên nguồn dữ liệu có thẩm quyền, tiến độ replay và tiêu chí quan sát được, không chỉ thay một feature flag.
- **Hoàn thành migration** nghĩa là dữ liệu, truy vấn, độ trễ, rollback và vận hành cùng đạt điều kiện đã thống nhất; copy hết các hàng có thể nhìn thấy chỉ là một bước.

Khi có một kế hoạch di chuyển gồm schema mới, phép mapping nhất quán, backfill có kiểm soát, thu nhận thay đổi và đối chiếu dữ liệu, hệ thống Cassandra có thể cải thiện hình dạng phân vùng mà vẫn phục vụ các thao tác CQL và ứng dụng Java trong môi trường phân tán. Cách làm này cũng tạo nền tảng an toàn để tiếp tục tối ưu replication, compaction, repair và xử lý lỗi sau khi dữ liệu đã chuyển sang thiết kế khóa mới.


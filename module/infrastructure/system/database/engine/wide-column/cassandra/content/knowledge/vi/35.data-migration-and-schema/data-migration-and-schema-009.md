# Dữ liệu có TTL và giữ đúng thời điểm hết hạn khi di chuyển

> **Chương:** Di chuyển và schema  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — tìm hiểu Apache Cassandra, mô hình wide-column phân tán, partition key, thiết kế bảng theo truy vấn, nhất quán đọc/ghi, thực hành CQL, replication, compaction, repair, xử lý lỗi và kết nối từ Java.

Một hệ thống dùng Apache Cassandra để lưu phiên đăng nhập, sự kiện IoT hoặc dữ liệu tạm thường gắn **TTL (Time To Live)** vào các giá trị. TTL khiến giá trị hết hiệu lực sau một khoảng thời gian. Nếu ứng dụng chuyển dữ liệu sang cluster mới bằng cách đọc rồi `INSERT ... USING TTL 3600` lại, một bản ghi đã tồn tại gần một giờ có thể được cấp thêm **một giờ mới**. Kết quả là dữ liệu sống lâu hơn chính sách lưu trữ ban đầu — có thể gây lỗi nghiệp vụ, lộ dữ liệu phải hết hạn hoặc phình dung lượng SSTable.

Bài học tập trung giải quyết câu hỏi:

> Làm thế nào để dữ liệu ở đích **hết hiệu lực gần với hoặc đúng thời điểm dự kiến ở nguồn**, thay vì bắt đầu đếm TTL lại từ lúc migration?

Cần phân biệt hai loại cam kết:

- **Giữ nguyên metadata vật lý của SSTable**, gồm expiration/tombstone và timestamp, bằng đường sao lưu/streaming tương thích: có khả năng bảo toàn thời điểm hết hạn nội tại nếu toàn bộ điều kiện định dạng, schema và lịch sử mutation được giữ đúng.
- **Chuyển qua tầng CQL**: chỉ thấy dữ liệu còn sống và TTL **còn lại**. Có thể tính lại thời gian còn hiệu lực để xấp xỉ hạn hết hiệu lực; không nên tuyên bố chính xác tới từng giây hoặc khôi phục được lịch sử tombstone nếu không có nguồn metadata bổ sung.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt TTL ban đầu, TTL còn lại, hạn hết hiệu lực tuyệt đối và thời điểm dữ liệu được ghi lại.
2. Giải thích ngữ nghĩa TTL **theo từng cell/giá trị**, `default_time_to_live` cấp bảng, `USING TTL` và tác động của `UPDATE`.
3. Dùng `TTL(column)` và `WRITETIME(column)` để quan sát metadata CQL, hiểu các giới hạn khi tính thời điểm hết hạn.
4. So sánh chuyển bằng `cqlsh/driver/DSBulk` với snapshot + SSTable streaming, biết trường hợp không được phép đổi thời hạn TTL.
5. Thiết kế backfill + CDC/dual-write có watermark, giải quyết ghi đồng thời, delete/tombstone và idempotency.
6. Thực hành CQL và Java Driver 4.x để tính TTL đích từ thời gian còn lại, đo sai lệch và cảnh báo gần hết hạn.
7. Xây checklist kiểm chứng về RPO/RTO, đồng hồ node, RF/CL, topology, TTL, tombstone và kết quả sau cutover.

## 2. Bốn khái niệm thời gian phải tách biệt

### 2.1. TTL được gắn với giá trị, không phải một đồng hồ cho cả partition

Cassandra cho phép đặt TTL khi ghi CQL:

~~~sql
INSERT INTO sessions_by_user (user_id, session_id, token)
VALUES (11111111-1111-4111-8111-111111111111,
        22222222-2222-4222-8222-222222222222,
        'sample-not-a-real-secret')
USING TTL 3600;
~~~

Đây là ví dụ minh họa, **không đưa token xác thực thật vào log hoặc tài liệu**. TTL 3600 là thời gian hiệu lực tính bằng **giây** cho các giá trị được ghi trong mutation, không phải lời hứa dữ liệu sẽ bị xóa byte vật lý đúng sau 3600 giây.

Mỗi cột không thuộc khóa chính có thể có lịch sử TTL khác nhau:

~~~sql
-- Lệnh UPDATE chỉ thay đổi TTL của cột được ghi trong mutation này.
UPDATE sessions_by_user
USING TTL 300
SET last_seen_state = 'ACTIVE'
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND session_id = 22222222-2222-4222-8222-222222222222;
~~~

Sau lệnh này, `token` có thể còn gần một giờ, còn `last_seen_state` chỉ sống thêm năm phút. Không nên lưu một trường `row_ttl` rồi dùng nó áp cho mọi cột nếu nguồn có TTL khác nhau.

**Khóa chính không phải một cell dữ liệu tùy ý có TTL riêng để chỉnh độc lập.** Clustering/partition keys định danh hàng; marker sống của hàng và các cell còn sống quyết định kết quả đọc. Khi di chuyển một phần giá trị, phải kiểm tra hàng có còn hiển thị sau khi cell hết hạn hay không, thay vì nghĩ “cả row hết hạn cùng lúc”.

### 2.2. Từ lúc ghi tới hạn hết hiệu lực

Hãy dùng thời điểm minh họa theo UTC:

| Mốc | Sự kiện | TTL còn lại ước tính |
|---|---|---:|
| 10:00:00 | Ghi cell với `TTL = 7200` giây | 7200 giây |
| 10:45:00 | Đọc dữ liệu ở nguồn | 4500 giây |
| 10:47:00 | Bắt đầu replay vào cluster đích | Khoảng 4380 giây |
| 12:00:00 | Hạn hết hiệu lực mong muốn | 0 |

Nếu ghi vào đích lúc 10:47 với `USING TTL 7200`, dữ liệu có thể sống tới **12:47**: bị gia hạn khoảng 47 phút. Nếu dùng TTL còn lại đã đo ở 10:45 (4500 giây) nhưng mất hai phút để di chuyển, dữ liệu có thể sống tới **12:02**: vẫn bị gia hạn ngoài ý muốn.

Kết luận: **TTL là khoảng thời gian tương đối tại thời điểm áp dụng ghi**, còn chính sách retention thường cần một **deadline tuyệt đối**. Công thức vận hành đơn giản:

~~~text
deadline_estimated = source_observation_time + source_remaining_ttl
target_ttl_seconds  = floor(deadline_estimated - target_write_time) - safety_margin
~~~

Với kết quả `target_ttl_seconds <= 0`, **không nạp lại giá trị đã hoặc sắp hết hạn**. Dấu `floor` có mục đích tránh làm tròn lên rồi vô tình kéo dài hiệu lực. Trong thực tế còn trễ giữa lúc tính TTL và lúc target server nhận mutation; hãy dùng safety margin và đo sai lệch.

### 2.3. Ba thời gian không thể thay thế nhau

| Đại lượng | Là gì? | Dùng cho migration ra sao? |
|---|---|---|
| **Write timestamp** | Microseconds để Cassandra giải quyết phiên bản của mutation; đọc bằng `WRITETIME(column)` | Giữ thứ tự mutation khi cần, nhưng **không tự suy ra expiration deadline** |
| **TTL còn lại** | Seconds trước khi cell hiện tại hết hạn, đọc bằng `TTL(column)` | Có thể xây deadline ước tính tại thời điểm quan sát |
| **Local expiration/deletion time** | Metadata phục vụ hiệu lực hết hạn và quá trình tombstone/compaction | Quan trọng khi chuyển **SSTable metadata**; không lấy trực tiếp từ SELECT CQL thông thường |

Một ứng dụng có thể tự chỉ định `USING TIMESTAMP` trong quá khứ hoặc tương lai. Vì vậy **không tính hạn hết hiệu lực bằng công thức `WRITETIME + TTL ban đầu`** trừ khi hệ thống có metadata nguyên gốc bổ sung và một cơ chế thời gian đã được chứng minh. Trong Cassandra, write timestamp để giải quyết xung đột là một khái niệm khác với thời điểm node tính TTL khi nhận mutation.

### 2.4. Hết TTL không đồng nghĩa đã giải phóng disk

Khi TTL hết, cell không còn hiển thị như dữ liệu sống; metadata hết hạn có thể tồn tại trong SSTable và được xử lý tương tự tombstone. Thu hồi vật lý phụ thuộc compaction, `gc_grace_seconds`, SSTable overlap và an toàn replica. **Đừng dùng dung lượng disk giảm hoặc chưa giảm** để xác định một cell đã hết hạn logic hay chưa.

~~~mermaid
flowchart LR
    A["Ghi với TTL"] --> B["Đọc thấy cell còn sống"]
    B --> C["TTL giảm dần"]
    C --> D["Deadline: cell hết hiệu lực logic"]
    D --> E["Tombstone/expired metadata còn trong SSTable"]
    E --> F["Compaction đủ điều kiện thu hồi vật lý"]
~~~

## 3. Quan sát metadata bằng CQL

### 3.1. TTL(column) và WRITETIME(column)

Với một cột scalar bình thường:

~~~sql
SELECT payload,
       TTL(payload) AS ttl_seconds,
       WRITETIME(payload) AS write_time_us
FROM mig_lab.events_source
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND day_bucket = '2026-11-21'
  AND event_time = '2026-11-21T08:30:00Z'
  AND event_id = df4d2f1a-c74e-48dc-b889-4e18de3cd51b;
~~~

Kết quả dự kiến về **ngữ nghĩa**, không phải số liệu cố định:

| Trường | Ví dụ | Giải thích |
|---|---|---|
| `payload` | `temperature=21` | Giá trị còn sống ở thời điểm đọc |
| `ttl_seconds` | 421 | Giá trị còn 421 giây (ước lượng tới đơn vị giây) |
| `write_time_us` | 1795249800000000 | Timestamp xung đột/phiên bản của cell, microseconds |

Lưu ý `TTL(column)` trả **`null`** nếu giá trị không được gán TTL; `null` không đồng nghĩa bằng 0 và cũng không nhất thiết chứng minh có cell sống khi giá trị gốc là null. `WRITETIME` trả timestamp của giá trị hiện tại. Khi cell đã hết hạn, truy vấn không hiển thị nó như một giá trị sống; bạn **không thể dùng SELECT thông thường để khôi phục mọi tombstone/expired cell đã mất**.

Với collection hoặc UDT không frozen, TTL/WRITETIME có thể khác nhau giữa các thành phần; cú pháp và kiểu trả về tùy phiên bản/loại cột. Một công cụ migration chỉ biết copy `TTL(collection)` thành một số nguyên duy nhất dễ làm sai semantics. Bài này dùng **scalar columns** để minh họa; collection/UDT phải có quy trình chuyên biệt.

### 3.2. Những thông tin CQL không cung cấp đủ

CQL trả trạng thái hiện tại theo consistency level của truy vấn, **không phải log mutation đầy đủ**. Trường hợp:

- Hai cell trong cùng row có TTL khác nhau.
- Một cell đã bị `DELETE`, chỉ còn tombstone ở SSTable.
- Có bản ghi được ghi với timestamp lớn hơn hoặc nhỏ hơn thời gian thực.
- Có nhiều replica lệch do node Down/repair chưa hoàn tất.
- Trong lúc paging qua hàng triệu partition, ứng dụng vẫn đang update/delete.

thì một lần SELECT không đảm bảo tạo ra ảnh chụp nhất quán tại một timestamp toàn cluster. Với **strict retention** và phải giữ lịch sử delete, cần lựa chọn migration hỗ trợ SSTable metadata hoặc CDC/change log được thiết kế phù hợp; không thể chỉ dựa vào `SELECT *`.

### 3.3. Đồng hồ và độ phân giải

TTL đo theo giây, expiration metadata cũng có độ phân giải/giới hạn của định dạng SSTable và phiên bản. Client Java dùng `Instant.now()` trên host ứng dụng nhưng TTL remaining do Cassandra trả về từ replica/đường đọc; chênh lệch đồng hồ, thời gian mạng, rounding và batching khiến deadline ước tính có sai số.

Vì vậy:

1. Đồng bộ NTP/clock monitoring trên node và máy chạy migration.
2. Đo request start/end, replay start/end, queue latency và trễ giữa clusters.
3. Định nghĩa sai số chấp nhận được (ví dụ “không gia hạn hơn 2 giây”, “không bỏ sót quá 1% dữ liệu còn sống”); **không tuyên bố giữ tuyệt đối chính xác** khi dùng CQL TTL tương đối.
4. Nếu chính sách yêu cầu **không bao giờ kéo dài thời hạn**, áp dụng safety margin/bỏ qua near-expiry và kiểm chứng bằng TTL ở đích sau ghi.

## 4. Khi nào phải dùng TTL 0 hoặc default_time_to_live?

### 4.1. TTL do bảng đặt mặc định

Cassandra hỗ trợ property cấp bảng:

~~~sql
CREATE TABLE mig_lab.events_source (
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    payload text,
    status text,
    PRIMARY KEY ((device_id, day_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 0;
~~~

`default_time_to_live = 0` nghĩa là bảng **không tự áp thời hạn mặc định**. Nếu đặt, chẳng hạn, `default_time_to_live = 86400`, những giá trị được ghi không có TTL explicit sẽ nhận TTL mặc định theo semantics của bản Cassandra.

Một migration sang bảng đích đặt default TTL khác nguồn có thể làm:

- Giá trị vốn tồn tại vĩnh viễn ở nguồn **bị hết hạn** ở đích.
- Giá trị vốn hết hạn sau một ngày bị thay thành giá trị vĩnh viễn nếu target default là 0 và loader bỏ TTL.
- Các row/cell có TTL khác nhau bị gộp một thời hạn nếu loader áp `USING TTL` trên cả statement.

**Bắt buộc đối chiếu schema và defaults** trước khi nạp. Không sửa `default_time_to_live` theo phỏng đoán để “giữ nguyên TTL”: phải hiểu mỗi cell của dữ liệu thực.

### 4.2. USING TTL 0 không phải DELETE

Trong CQL, `USING TTL 0` nghĩa là **không áp TTL** cho giá trị đang ghi; nếu bảng có default TTL, TTL=0 có thể bỏ mặc định cho mutation này. Nó **không** nghĩa là “hết hạn ngay lập tức” hoặc “xóa giá trị”.

~~~sql
-- Ví dụ nếu muốn giá trị này không có TTL:
INSERT INTO mig_lab.events_target
    (device_id, day_bucket, event_time, event_id, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T08:30:00Z',
    df4d2f1a-c74e-48dc-b889-4e18de3cd51b,
    'no-expiration'
) USING TTL 0;
~~~

Khi nguồn trả `TTL(payload) IS NULL`, hãy xác định đó là **cell thực sự còn sống không TTL**, chứ không phải cell đã xóa hoặc trường không có giá trị. Sau đó target ghi không TTL **có chủ đích**. Nếu target đang có dữ liệu khác cùng khóa, yêu cầu preserve write timestamp và xung đột phiên bản trở nên rất quan trọng.

### 4.3. Thời gian tối đa và vấn đề năm 2038

Các phiên bản/định dạng của Cassandra có giới hạn thời điểm expiration được biểu diễn và xử lý riêng với phạm vi TTL lớn; tài liệu Cassandra đã lưu ý hành vi **expiration date overflow liên quan 2038** ở các phiên bản nhất định. Không lập kế hoạch TTL dài hàng chục năm mà chưa kiểm tra release, `max_ttl`, policy khi overflow, và kiểm thử giá trị biên. Đối với dữ liệu giữ nhiều năm, cần một mô hình retention đã được kiểm chứng, không dùng một số TTL rất lớn như giải pháp mặc định.

## 5. Chọn đường migration: SSTable metadata hay CQL replay?

### 5.1. Bảng so sánh

| Đường di chuyển | Có thể giữ expiration gốc? | Khả năng đổi schema/partition key | Rủi ro chính |
|---|---|---|---|
| **Snapshot/SSTable backup + restore/streaming tương thích** | Có khả năng bảo toàn metadata TTL, timestamp và tombstone trong SSTable | **Hạn chế**; schema và SSTable format phải tương thích | Mất coverage range, snapshot sai thời điểm, tombstone cũ, loader không tương thích |
| **`sstableloader` trên SSTable hợp lệ** | Stream dữ liệu từ SSTable với metadata tương ứng, không phải “INSERT TTL mới” theo CQL | Chủ yếu dùng khi schema/format tương thích; thay đổi partition key cần thiết kế riêng | Sai target schema, RF/CL, file component thiếu, nguồn không hoàn chỉnh |
| **CQL SELECT → INSERT/UPDATE** | **Không chính xác tuyệt đối mặc định**; phải tính remaining TTL rồi giảm theo trễ | Linh hoạt transform schema, đổi partition/clustering key | TTL reset, thiếu tombstone, xung đột với ghi mới, hàng hết hạn trong lúc load |
| **CSV/JSON/DSBulk export/import** | Phụ thuộc mapping và khả năng preserve TTL/timestamp của **công cụ/phiên bản** | Tốt cho transform tabular | Export thường chỉ chứa giá trị sống; không lưu TTL nếu không cấu hình riêng |
| **CDC/dual-write + backfill** | Có thể truyền cùng retention policy/deadline nếu sự kiện chứa metadata đúng | Linh hoạt và phục vụ cutover online | Thứ tự sự kiện, duplicates, delete, clock skew và race conditions |

**Không khẳng định mọi công cụ bulk load tự giữ TTL.** Một dòng CSV gồm `payload` và `event_time` không mang theo internal TTL. Nếu công cụ có tùy chọn đọc/ghi TTL hoặc writetime, hãy kiểm tra **chính xác hỗ trợ per-cell và ngữ nghĩa timestamp** của phiên bản tool.

### 5.2. Đường SSTable để giữ metadata nội tại

SSTable có dữ liệu và thông tin về timestamp, expiration/tombstone nên **tốt hơn cho yêu cầu không làm mới TTL** khi có thể giữ nguyên mô hình dữ liệu. Snapshot Cassandra lưu các file SSTable bất biến; tài liệu dự án mô tả `nodetool snapshot`, backup và restore bằng `sstableloader`/các quy trình SSTable khác.

Ở cluster **lab**:

~~~bash
# Chạy trên node được quản trị; chỉ là snapshot cục bộ của node đó.
nodetool snapshot -t ttl_migration_lab mig_lab

# Xem snapshot đã được tạo.
nodetool listsnapshots
~~~

Để khôi phục sang đích, sao chép **đầy đủ SSTable components** vào đường dẫn staging tương ứng, kiểm tra schema/partitioner/định dạng và dùng `sstableloader` có hỗ trợ:

~~~bash
# Ví dụ khái niệm: phải thay host/đường dẫn bằng staging lab hợp lệ.
# Kiểm tra sstableloader --help trên bản tool thực tế.
sstableloader --nodes 192.0.2.10 /staging/mig_lab/events_source
~~~

Địa chỉ `192.0.2.10` thuộc dải tài liệu minh họa, **không phải node Cassandra đang hoạt động**. Tên thư mục/đường dẫn quyết định keyspace/table theo quy tắc công cụ; ví dụ chỉ nhắc cú pháp, không đủ để chạy khi chưa có SSTable hợp lệ và schema đích. Không đặt file staging vào data directory đang được Cassandra quản lý nếu tài liệu tool cảnh báo làm vậy.

Điều kiện trước khi kết luận giữ được TTL:

1. Source/target và SSTable format tương thích, schema tương ứng (type, key, table metadata, compression).
2. Snapshot bao phủ **đủ token range**, nhiều replica/node cần thiết; có kiểm soát writes đang diễn ra và schema agreement.
3. Không vô tình làm mất **tombstone** còn cần che dữ liệu cũ; lựa chọn timepoint và `gc_grace_seconds` phù hợp.
4. Kiểm tra trên cluster đích rằng giá trị gần hết hạn **không được gia hạn** chỉ vì đã stream lại.
5. Với CDC/cutover, xử lý các mutation phát sinh **sau snapshot**. Một snapshot tĩnh không mang theo ghi và xóa xảy ra trong quá trình copy.

**Cảnh báo:** sstableloader không thể tự biến khóa phân vùng `(user_id)` thành `(tenant_id, day_bucket)` cho schema mới như một lệnh SQL transform. Nếu đổi data model, thông thường phải tái ghi ở tầng logic, đồng thời chấp nhận khó khăn bảo toàn TTL chính xác.

### 5.3. Đường CQL khi phải đổi mô hình dữ liệu

Nếu đổi partition key, clustering key hoặc chuẩn hóa payload, cần đọc các hàng **còn sống** rồi ghi sang bảng mới theo truy vấn. Khi đó:

- Đọc `TTL(column)` và, khi cần giữ thứ tự mutation, `WRITETIME(column)` **cho từng cột có ý nghĩa**.
- Tính TTL đích theo deadline, không copy TTL ban đầu của chính sách.
- Tách cell có TTL khác nhau thành mutation riêng nếu statement `INSERT`/`UPDATE` không thể diễn đạt các metadata khác biệt.
- Không nạp cell đã hết hạn; xử lý delete/tombstone bằng luồng thay đổi bổ sung hoặc chọn **target sạch** và cutover được kiểm soát.
- Chọn strategy chống ghi chồng dữ liệu mới: timestamp thống nhất, CDC ordering, fencing hoặc chặn ghi tại cutover.

**Giới hạn căn bản:** nếu đã mất dữ liệu về expiration tuyệt đối, không có phép suy luận CQL nào khôi phục metadata đã không được export.

## 6. Thuật toán CQL: bảo toàn deadline tương đối an toàn

### 6.1. Một cell còn sống

Với một cell có TTL, mã giả:

~~~text
1. source_read_started_at = clock.now()
2. SELECT value, TTL(value), WRITETIME(value) FROM source WHERE full_pk = ...
3. Nếu row/value không còn sống -> đừng insert cell đó vào target.
4. Nếu TTL(value) là null -> value không có TTL;
   chỉ ghi không TTL nếu schema và trạng thái source phù hợp.
5. Nếu TTL(value) > 0:
     estimated_deadline = source_read_started_at + TTL(value)
     remaining = floor(estimated_deadline - clock.now()) - margin
     nếu remaining <= 0 -> bỏ qua/reconcile delete, không dùng TTL 0
     nếu remaining > 0 -> ghi USING TTL remaining
6. Ghi nhận độ trễ, số bỏ qua gần hạn, số lỗi/retry.
7. Đọc lại TTL(target_value) và so với source deadline theo dung sai.
~~~

Dùng `source_read_started_at` sớm hơn thời điểm server đo TTL giúp **ước lượng bảo thủ** (không cố tình gia hạn); tuy nhiên chỉ là gần đúng vì thời gian chờ coordinator/server, độ chính xác giây, lệch đồng hồ và độ trễ ghi. Với những lần đọc phân trang dài, lấy timestamp gần sát **từng fetch/page**; nếu dùng một timestamp cho nhiều giờ dữ liệu, estimate sẽ quá bảo thủ và bỏ qua nhiều cell.

### 6.2. Không thể dùng TTL 0 cho cell hết hạn

Một nhầm lẫn rất nguy hiểm:

~~~text
remaining_seconds <= 0
  -> GHI USING TTL 0   # SAI: TTL 0 có nghĩa không hết hạn!
~~~

Đúng là:

~~~text
remaining_seconds <= 0
  -> KHÔNG GHI giá trị còn sống
  -> nếu target đã có phiên bản cũ cùng key, chạy reconciliation/delete
     theo timestamp/CDC/fencing an toàn
~~~

Trong một bảng đích **trống**, bỏ qua cell hết hạn có thể đủ cho pha backfill. Trong một bảng đích **đang có dữ liệu**, bỏ qua không xóa bản sao cũ có thể khiến giá trị ở đích **sống lâu hơn nguồn**. Đây là lý do phải xét cả dữ liệu đích hiện tại và lịch sử delete.

### 6.3. Safety margin là đánh đổi, không phải chứng minh tuyệt đối

Giả sử quan sát ở nguồn: TTL còn 30 giây, trễ client + queue + replay 2 giây, safety margin 2 giây:

~~~text
target TTL ước lượng = floor(30 - 2) - 2 = 26 giây
~~~

Nếu viết và replica xác nhận trong khoảng dự kiến, đích sẽ hết hạn **sớm hơn hoặc xấp xỉ** nguồn một ít thay vì bị gia hạn. Nhưng nếu source/destination clocks lệch nhiều hoặc request bị retry sau hàng phút, công thức vẫn sai. Khi deadline **bắt buộc chính xác tuyệt đối**, dùng metadata SSTable/streaming đã kiểm chứng, hoặc tái thiết kế record mang trường `expires_at_utc` và enforcement ở ứng dụng/đường đọc (đồng thời cân nhắc TTL để dọn disk).

### 6.4. Không nhầm WRITETIME với TTL

CQL hỗ trợ:

~~~sql
-- Cú pháp minh họa cho giá trị scalar:
INSERT INTO mig_lab.events_target (
    device_id, day_bucket, event_time, event_id, payload
) VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T08:30:00Z',
    df4d2f1a-c74e-48dc-b889-4e18de3cd51b,
    'temperature=21'
) USING TTL 300 AND TIMESTAMP 1795249800000000;
~~~

**Giải thích:** `USING TIMESTAMP` đặt write timestamp để giải quyết phiên bản; `USING TTL 300` đặt **thời gian tồn tại tương đối cho lần ghi này**. Việc dùng một timestamp cũ **không tự động** khiến target chỉ sống tới deadline của nguồn.

Một số tình huống cần giữ nguyên `WRITETIME` để bản backfill không ghi đè mutation mới hơn. Song bản CQL SELECT không lộ đầy đủ tombstone hay row liveness marker; nếu có ghi/xóa đồng thời, việc áp timestamp cũ vào mỗi cell vẫn **không đủ** để bảo đảm thứ tự conflict. Cần CDC/order/fencing, test phiên bản và chiến lược rollback.

## 7. Lab CQL: hai cột có hai hạn TTL khác nhau

### 7.1. Chuẩn bị cluster thử nghiệm

Thực hành trong **cluster lab** với Cassandra 4.x–5.x, `cqlsh` và `nodetool`; ví dụ giả định datacenter thật tên `dc1` và có ba node. Nếu chỉ có một node, phải chọn RF/CL tương ứng thay vì lấy RF=3 rồi suy kết quả từ một node.

~~~bash
nodetool status
nodetool describecluster
~~~

Trong `cqlsh`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS mig_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS mig_lab.events_source (
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    payload text,
    status text,
    PRIMARY KEY ((device_id, day_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 0
  AND gc_grace_seconds = 864000;

CREATE TABLE IF NOT EXISTS mig_lab.events_target (
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    payload text,
    status text,
    PRIMARY KEY ((device_id, day_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 0
  AND gc_grace_seconds = 864000;
~~~

`IF NOT EXISTS` không sửa bảng đã tồn tại. Xác minh schema thật và `default_time_to_live` bằng:

~~~text
DESCRIBE TABLE mig_lab.events_source;
DESCRIBE TABLE mig_lab.events_target;
~~~

### 7.2. Ghi dữ liệu có TTL khác nhau

~~~sql
INSERT INTO mig_lab.events_source
    (device_id, day_bucket, event_time, event_id, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T08:30:00Z',
    df4d2f1a-c74e-48dc-b889-4e18de3cd51b,
    'temperature=21'
) USING TTL 600;

UPDATE mig_lab.events_source
USING TTL 120
SET status = 'TEMPORARY'
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND day_bucket = '2026-11-21'
  AND event_time = '2026-11-21T08:30:00Z'
  AND event_id = df4d2f1a-c74e-48dc-b889-4e18de3cd51b;

SELECT payload, status,
       TTL(payload) AS payload_ttl,
       TTL(status) AS status_ttl,
       WRITETIME(payload) AS payload_writetime,
       WRITETIME(status) AS status_writetime
FROM mig_lab.events_source
WHERE device_id = 0f94e3b9-0b36-4930-91f2-606b44b5231b
  AND day_bucket = '2026-11-21'
  AND event_time = '2026-11-21T08:30:00Z'
  AND event_id = df4d2f1a-c74e-48dc-b889-4e18de3cd51b;
~~~

Kỳ vọng: `payload_ttl` ban đầu gần 600 giây; `status_ttl` ban đầu gần 120 giây. Hai trường `WRITETIME` có thể khác nhau. Sau hai phút, `status` hết hạn nhưng `payload` có thể vẫn còn.

**Điều quan trọng:** nếu loader dùng một lệnh `INSERT ... (payload, status) USING TTL 600`, `status` đã bị gia hạn từ 120 thành 600 giây; nếu dùng `USING TTL 120`, `payload` lại bị hết hạn quá sớm. Muốn đúng semantics, phải nạp từng cell hoặc nhóm cell có deadline như nhau, đồng thời xử lý marker/tombstone và độ trễ.

### 7.3. Thí nghiệm phản ví dụ và thí nghiệm đúng

**Phản ví dụ — áp TTL gốc vào đích:**

~~~sql
-- Chỉ chạy trong lab để quan sát lỗi thiết kế, không phải migration đúng.
INSERT INTO mig_lab.events_target
    (device_id, day_bucket, event_time, event_id, payload)
VALUES (
    0f94e3b9-0b36-4930-91f2-606b44b5231b,
    '2026-11-21',
    '2026-11-21T08:30:00Z',
    df4d2f1a-c74e-48dc-b889-4e18de3cd51b,
    'temperature=21'
) USING TTL 600;
~~~

Nếu thao tác diễn ra sau lúc source đã đếm TTL một thời gian, `TTL(payload)` ở đích lớn hơn ở nguồn. Thí nghiệm này **cố ý sai** để nhận diện việc reset TTL.

**Thí nghiệm đúng tương đối — tính TTL còn lại tại lúc nạp:**

1. Đọc `payload_ttl` và `status_ttl` cùng thời điểm bắt đầu một lượt copy.
2. Ghi lại timestamp bắt đầu đọc, kết thúc đọc, bắt đầu ghi, ACK từ đích.
3. Tính TTL cho **mỗi cột** = TTL nguồn lúc quan sát trừ thời gian trôi qua và safety margin, lấy số nguyên giây **làm tròn xuống**.
4. Dùng lệnh `INSERT/UPDATE USING TTL <giá trị tính được>` hoặc Java Driver; **không** dùng một TTL chung cho hai cột.
5. So `TTL(payload)` và `TTL(status)` tại đích với thời gian đến deadline từ nguồn trong cửa sổ kiểm thử.
6. Đợi qua hai mốc hết hạn, kiểm tra `status` biến mất trước `payload`. Lưu ý CQL không phải bằng chứng byte đã được purge vật lý.

Không đưa giá trị TTL tính lúc đọc vào một lệnh CQL cố định trong tài liệu rồi gọi đó là “đúng”; TTL thay đổi theo từng giây và tốc độ di chuyển. Một ứng dụng có logging/metrics mới đo được sai số thực.

### 7.4. Bảng ghi kết quả lab

| Trường | Deadline mong muốn | TTL source lúc đọc | TTL target sau ghi | Lệch ước tính | Đạt? |
|---|---|---|---|---|---|
| `payload` | _ghi UTC_ | _giây đo_ | _giây đo_ | _giây_ | _điền_ |
| `status` | _ghi UTC_ | _giây đo_ | _giây đo_ | _giây_ | _điền_ |
| Cell không TTL (nếu thêm) | Không có deadline | `null` | `null` | Không áp dụng | _điền_ |
| Cell đã hết hạn | Đã qua | Không còn sống | Không được hồi sinh | Không áp dụng | _điền_ |

So sánh **deadline**, không chỉ một cặp TTL được đo ở hai thời điểm khác nhau. Nếu kiểm tra nguồn sau 10 giây và đích ngay sau ghi, raw TTL có thể chênh lệch do sampling; phải quy đổi chúng về cùng mốc UTC và xem sai số.

## 8. Java Driver 4.x: bảo toàn TTL của một cột scalar

### 8.1. Điều kiện của ví dụ

Ví dụ dưới đây trình bày **một hàng với một cell `payload`**, không phải toàn bộ engine migration. Nó dùng hai `CqlSession` đã được cấu hình đúng local DC, TLS và authentication để tránh ghi secret trong mã nguồn. Source và target có schema tương đương, `default_time_to_live = 0`, và bảng đích **chưa có dữ liệu mới hơn tại khóa đang sao chép**.

Trong đoạn code, TTL được đọc trên nguồn, đặt deadline từ thời điểm bắt đầu đọc, sau đó trừ thời gian thực đã qua và một margin. `WRITETIME(payload)` được giữ làm **timestamp cho ví dụ nguồn/đích đồng nhất**. Điều đó giúp làm rõ rằng **timestamp không thay TTL**, không phải một công thức giải quyết mọi xung đột CDC/dual-write.

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

// source và target: CqlSession đã được cấu hình từ secure config.
void migrateOnePayload(CqlSession source, CqlSession target,
                       UUID deviceId, LocalDate day, Instant eventTime, UUID eventId) {
    PreparedStatement read = source.prepare(
        "SELECT payload, TTL(payload) AS ttl_remaining, " +
        "WRITETIME(payload) AS wt_us " +
        "FROM mig_lab.events_source " +
        "WHERE device_id = ? AND day_bucket = ? " +
        "AND event_time = ? AND event_id = ?");

    PreparedStatement write = target.prepare(
        "INSERT INTO mig_lab.events_target " +
        "(device_id, day_bucket, event_time, event_id, payload) " +
        "VALUES (?, ?, ?, ?, ?) USING TTL ? AND TIMESTAMP ?");

    Instant startedAt = Instant.now(); // Mốc bảo thủ trước khi server đọc TTL.
    Row row = source.execute(read.bind(deviceId, day, eventTime, eventId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)).one();
    if (row == null || row.isNull("payload")) {
        // Source không còn giá trị sống; cần reconcile target nếu đã tồn tại.
        return;
    }

    String payload = row.getString("payload");
    if (row.isNull("wt_us")) {
        throw new IllegalStateException("Missing writetime for live payload");
    }
    long writeTimeUs = row.getLong("wt_us");

    final int ttlToWrite;
    if (row.isNull("ttl_remaining")) {
        ttlToWrite = 0; // Giữ non-expiring cell; KHÔNG có nghĩa delete.
    } else {
        int sourceTtl = row.getInt("ttl_remaining");
        Instant estimatedDeadline = startedAt.plusSeconds(sourceTtl);
        long remaining = Duration.between(
                Instant.now(), estimatedDeadline).getSeconds() - 2L;

        if (remaining <= 0L) {
            // Gần/đã hết hạn: không viết TTL 0 làm dữ liệu sống vĩnh viễn.
            return;
        }
        ttlToWrite = Math.toIntExact(remaining);
    }

    target.execute(write.bind(deviceId, day, eventTime, eventId,
                    payload, ttlToWrite, writeTimeUs)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM));
}
~~~

**Giới hạn và cảnh báo bắt buộc:**

- `sourceTtl` là thời gian còn lại tại lúc Cassandra quan sát; mốc `startedAt` và trừ hai giây là **ước lượng bảo thủ**, không chứng minh expiration ở đích đúng từng giây. Nếu clock skew lớn hoặc write queue chậm hơn margin, có thể gia hạn ngoài ý muốn.
- `Duration.between(...).getSeconds()` làm tròn về số giây nguyên; với TTL dương nhỏ cần kiểm tra cả độ chính xác và biên để không viết TTL=0.
- Giữ `writeTimeUs` giúp mô phỏng việc giữ thứ tự cell version, **nhưng** không copy được row liveness marker, tombstone đã bị ẩn hoặc các cell có TTL khác nhau. Không dùng code này trực tiếp cho live migration có writes concurrent.
- Nếu nguồn không TTL, `ttlToWrite = 0` chỉ hợp lệ khi đúng chính sách giữ cell vĩnh viễn; ứng dụng phải kiểm tra target schema/default TTL.
- Khi gặp timeout/retry, write có thể đã thành công trên một số replica. Lần thử lại với cùng writetime nhưng TTL tính mới có thể tạo tác động tinh vi; phải dùng idempotency protocol/CDC ordering, logging và phép kiểm chứng được thiết kế rõ.
- Nếu source payload là dữ liệu bảo mật, không ghi nguyên payload hoặc credential vào migration logs.

### 8.2. Giảm lệch do thời gian nạp quá dài

Với hàng triệu row, một chương trình thực tế cần:

1. **Bounded concurrency** trên source/target, tránh đẩy hàng đợi vượt khả năng coordinator.
2. **Per-page/per-batch observation timestamp**, không dùng một đồng hồ t0 cho nhiều giờ.
3. Theo dõi latency thực từ read start → TTL fetch → target ACK, phân phối p95/p99 của queue lag.
4. Ghi chính sách **near-expiry**: bỏ qua nếu remaining TTL quá nhỏ; cùng lúc phải xử lý target đã có bản stale.
5. Chỉ định CL/RF đúng, tránh hiểu timeout là rollback.
6. Đảm bảo giới hạn TTL hợp lệ theo release, chống overflow và kiểm tra kết quả `TTL(target_column)`.

Nên dùng **UTC** cho deadline/log; tránh tính TTL theo giờ hiển thị có DST hoặc timezone địa phương. TTL giây không quan tâm việc ngày hiển thị đổi múi giờ, nhưng hệ thống đọc CSV và Java có thể parse thời gian sai nếu dùng offset không rõ ràng.

## 9. Backfill, CDC và dual-write: không chỉ là sao chép dữ liệu sống

### 9.1. Race condition khi cluster vẫn nhận ghi

Giả sử trong lúc migration:

~~~text
10:00  Backfill đọc K = "V1" từ source
10:01  Ứng dụng UPDATE K = "V2" trên source và target qua dual-write
10:02  Backfill ghi lại K = "V1" vào target
~~~

Nếu backfill dùng **write timestamp hiện tại** ở 10:02, `V1` có thể thắng `V2` dù nghiệp vụ xem nó là dữ liệu cũ. Thời gian TTL dù đã tính tốt vẫn không cứu được việc mất update. Nếu dùng `WRITETIME` cũ, một tombstone/record mới hơn ở đích có thể ngăn bản cũ ghi đè, nhưng **không thể dựa vào trường hợp đơn giản này để xử lý mọi row marker, collection, LWT và delete**.

### 9.2. Quy trình cắt chuyển có kiểm soát

Một quy trình phổ biến:

~~~mermaid
flowchart TD
    A["Inventory nguồn: schema, TTL, tombstone, CL/RF"] --> B["Tạo target đúng query model"]
    B --> C["Bật CDC/outbox hoặc dual-write đáng tin cậy"]
    C --> D["Ghi nhận watermark và bắt đầu backfill"]
    D --> E["Backfill: TTL theo deadline, chống overwrite"]
    E --> F["Replay thay đổi theo khóa/thứ tự đến watermark mới"]
    F --> G["Kiểm chứng expiry, reads/writes, duplicates, deletes"]
    G --> H["Fencing/cutover writer theo protocol"]
    H --> I["Theo dõi và ngừng source sau cửa sổ rollback"]
~~~

**Watermark** phải phản ánh thứ tự luồng thay đổi thực tế, không chỉ là `Instant.now()` ở máy migration. Ví dụ dùng CDC offset/commit position hoặc outbox sequence đã được thiết kế cho replay. Cassandra không mặc định cung cấp một “global commit sequence” cho mọi partition qua CQL; nếu cần thứ tự tuyệt đối toàn cụm, phải thiết kế bên ngoài.

Khi dùng **dual-write**, hai ghi có thể thành công ở hai thời điểm khác nhau, một phía lỗi, hoặc retry làm đảo thứ tự; không giả định dual-write tự tạo atomic transaction giữa hai cluster. Cần dead-letter queue, idempotency keys, reconciliation và hướng giải quyết sai lệch.

### 9.3. Delete và tombstone là trường hợp đặc biệt

Một lần `SELECT` chỉ đọc các hàng **đang còn sống**, nên không mang theo những deletion markers đã hình thành do `DELETE`/TTL. Nếu target có sẵn một giá trị từng được nạp, sau đó nguồn xóa nó, **backfill lần hai không thấy hàng** không có nghĩa giá trị ở target đã bị xóa.

Để an toàn:

- Di chuyển vào **target trống** với lịch sử ghi đủ điều kiện, hoặc có luồng CDC/outbox biểu diễn delete rõ ràng.
- Bảo toàn/write deletion timestamp và thứ tự cập nhật nếu quy trình cần; không copy `DELETE` thành một tombstone có timestamp thấp hơn cell cũ có thể thắng.
- Theo dõi `gc_grace_seconds` và lịch repair: dữ liệu đã xóa có thể hồi sinh nếu replica bỏ lỡ xóa quá lâu rồi compaction purge tombstone.
- Với dataset có **TTL rất ngắn**, có thể không cần backfill toàn bộ: đặt mốc retention, bắt đầu dual-write/cutover và chờ dữ liệu cũ hết hạn theo chính sách. Phải chứng minh yêu cầu nghiệp vụ cho phép.

### 9.4. Mô hình lưu deadline nghiệp vụ để tránh phụ thuộc CQL TTL

Nếu sản phẩm cần **deadline chính xác** qua nhiều cluster/schema, cân nhắc lưu thêm trường:

~~~sql
-- Trong mô hình mới, thêm trường biểu thị hạn nghiệp vụ do ứng dụng quản lý.
ALTER TABLE mig_lab.events_target
ADD expires_at_utc timestamp;
~~~

Đây chỉ là ví dụ minh họa cho việc thiết kế schema mới; không thực hiện `ALTER` trên bảng production trước khi đánh giá compatibility. Khi viết, ứng dụng tính `expires_at_utc` từ sự kiện/chính sách có nguồn thời gian tin cậy, **không tái tính từ TTL gốc mỗi lần copy**. Đường đọc kiểm tra `now < expires_at_utc` và hạn chế trả dữ liệu đã hết hiệu lực, còn TTL Cassandra giúp dọn dữ liệu về sau.

**Quan trọng:** trường `expires_at_utc` chỉ có tác dụng nếu mọi đường đọc/quyền truy cập đều thực hiện kiểm tra deadline. Nếu một client CQL có quyền đọc trực tiếp bảng mà không qua lớp kiểm soát, nó vẫn có thể thấy dữ liệu còn tồn tại vật lý trước khi TTL dọn; vì thế với dữ liệu nhạy cảm cần **quy tắc retention ở tầng lưu trữ và security** phù hợp, không chỉ filter ở API.

## 10. Kiểm thử đúng sai khi di chuyển dữ liệu có TTL

### 10.1. Ma trận kiểm thử bắt buộc

| Trường hợp | Source | Target mong muốn | Sai lầm cần phát hiện |
|---|---|---|---|
| TTL còn nhiều | Cell với TTL 1 giờ, đọc sau 10 phút | Hết hạn cùng hoặc **sớm hơn chút ít** theo tolerance | Reinsert TTL 1 giờ làm sống thêm 10 phút |
| TTL gần hết | TTL còn 2–5 giây | Bỏ qua hoặc dùng TTL cực ngắn nếu SLA cho phép | Viết `USING TTL 0` làm sống vĩnh viễn |
| Không có TTL | `TTL(column) = null` trên cell sống | Vẫn không TTL nếu retention policy cho phép | Target default TTL vô tình làm hết hạn |
| Hai cột khác TTL | Payload 600 giây, status 120 giây | Mỗi cột hết hạn đúng lịch riêng | Gộp một TTL cho cả row |
| UPDATE reset TTL | Ghi lại cùng cột khi còn TTL | Deadline theo **mutation thắng mới nhất** | Lấy TTL ban đầu của row cũ |
| DELETE sau snapshot | Nguồn đã xóa trong cutover | Target không còn giá trị hoặc giữ tombstone phù hợp | Backfill chỉ SELECT và không replay delete |
| Replay trùng | CDC gửi duplicate | Kết quả nhất quán, không gia hạn | Retry làm tăng TTL/đổi timestamp |
| Write concurrent | Target nhận V2 trước backfill V1 | V2 không bị V1 ghi đè | Dùng timestamp hiện tại cho backfill |
| Khác RF/CL | Destination nhiều replica | Xác nhận đủ replica và repair | Kết luận từ một SELECT CL=ONE |
| SSTable migration | Snapshot chứa expiration/tombstone | Metadata không biến thành TTL mới | Loader/chuyển định dạng không tương thích |

### 10.2. Các metric cần theo dõi

| Nhóm metric | Ví dụ | Giá trị vận hành |
|---|---|---|
| Migration rate | Rows/cells mỗi giây, bytes/s, lag CDC, queue depth | Biết liệu có theo kịp write rate nguồn |
| TTL correctness | Độ lệch deadline, số cell TTL null, near-expiry skipped | Tránh gia hạn dữ liệu hoặc mất trước hạn quá nhiều |
| Read/write outcomes | Timeouts, retries, conflict count, duplicate replay | Phát hiện mất dữ liệu và overwrite |
| Source/target Cassandra | p50/p95/p99, `nodetool tpstats`, disk/compaction load | Bảo vệ SLO ứng dụng thật |
| Tombstones | Tombstones scanned, compaction backlog, repair status | Phát hiện chi phí và zombie risk |
| Data coverage | Sample per token range, partition count, bảng sai lệch | Tránh việc nạp thiếu toàn bộ một miền token |
| Clock | Node/client time sync offset, drift alarms | Chứng minh deadline estimate trong dung sai |

Khi đối chiếu `TTL(payload)`, phải ghi **thời điểm của mỗi lần đọc** và quy đổi về deadline. So raw TTL nguồn 300 giây được đọc lúc 12:00 với raw TTL đích 295 giây được đọc lúc 12:02 rồi kết luận đích hết sớm 5 giây là sai — thời gian quan sát khác nhau.

### 10.3. Có thể chấp nhận sai lệch bao nhiêu?

Đây là quyết định sản phẩm/bảo mật:

- Với cache phiên làm việc, **hết hạn sớm** vài giây có thể chấp nhận; **hết hạn muộn** có thể tạo rủi ro.
- Với telemetry TTL hàng tháng, sai số vài giây có thể ít đáng kể nhưng vẫn cần tính đúng retention policy.
- Với token/auth/session dữ liệu nhạy cảm, cần expiry được kiểm tra ở **tầng xác thực/nghiệp vụ** và có deadline chính xác; TTL Cassandra đóng vai trò dọn lưu trữ chứ không là kiểm soát bảo mật duy nhất.
- Nếu luật yêu cầu xóa dữ liệu ở hạn chính xác, phải hiểu rằng TTL logic, tombstone grace, compaction và backup retention khác nhau; thiết kế cả **xóa khỏi snapshot/backup** theo chính sách.

Không chấp nhận metric “0 timeouts” để thay cho metric correctness của TTL. Workload có thể hoàn tất không lỗi nhưng **tất cả expiration ở đích bị kéo dài**.

## 11. Các ngộ nhận thường gặp

| Ngộ nhận | Vì sao sai | Cách đúng |
|---|---|---|
| “Reinsert cùng TTL thì giữ nguyên hạn” | TTL bắt đầu tính lại khi target ghi | Dùng deadline/remaining TTL hoặc SSTable metadata |
| “TTL trong cột là hằng số ban đầu” | `TTL(column)` trả thời gian **còn lại**, giảm theo giây | Ghi timestamp lấy mẫu và trừ migration lag |
| “WRITETIME + TTL mới cho expiration gốc” | Write timestamp là conflict clock, có thể custom | Dùng metadata expiration gốc hoặc TTL remaining quan sát |
| “TTL=0 nghĩa hết hạn ngay” | `USING TTL 0` nghĩa là **không TTL** | Bỏ qua cell hết hạn; reconcile target nếu có |
| “Một TTL cho cả row là đủ” | TTL áp ở cấp giá trị/cell; cột có lịch khác nhau | Truy xuất metadata từng cell và ghi riêng |
| “SELECT không thấy row thì target đã được xóa” | SELECT không xuất tombstones/deletes | Replay delete qua CDC/outbox hoặc target sạch |
| “Giữ WRITETIME là tự động chống mọi race” | Không có toàn bộ row/tombstone metadata; LWT và order phức tạp | CDC ordering + fencing + reconciliation |
| “Snapshot một node đã có hết cluster” | Node chỉ giữ một phần token ranges và trạng thái replica riêng | Kiểm tra coverage RF/token/node theo manifest |
| “SSTable migration đổi partition key được” | Streaming làm việc với storage layout, không transform tùy ý | Re-model bằng CQL/ETL và xử lý TTL riêng |
| “Đã hết TTL thì disk giảm ngay” | Expired cells/tombstones được dọn qua compaction | Phân biệt hiệu lực logic với reclaim vật lý |
| “Đọc CL=ONE đủ chứng minh target giống source” | Replica có thể chưa đồng bộ | Đọc/repair theo CL/RF và kiểm chứng đa range |
| “Kết quả giống nhau ngay cutover là đủ” | Tập TTL có thể lệch, lỗi chỉ xuất hiện sau hàng giờ | Test trước, tại và sau mốc expiry |

## 12. Tình huống thực hành

### Bài 1 — Tính TTL đích

Một cell được ghi ở nguồn lúc 08:00 với TTL ban đầu 5400 giây. Hệ thống bắt đầu đọc lúc 08:30, nhận giá trị TTL còn 3600 giây và dự kiến target áp dụng mutation lúc 08:31:20. Safety margin 3 giây. TTL đích nên gần bao nhiêu?

**Đáp án:** khoảng `3600 - 80 - 3 = 3517` giây (với giả định đồng hồ/quan sát lý tưởng). Đặt lại `5400` sẽ gia hạn; đặt lại `3600` vẫn gia hạn khoảng 80 giây.

### Bài 2 — Hai cột có TTL khác nhau

Một row có `payload` còn 500 giây, `status` còn 50 giây. Loader gom cả hai vào `INSERT ... USING TTL 500`. Lỗi gì?

**Đáp án:** `status` bị gia hạn khoảng 450 giây; khi nguồn đã hết status, đích vẫn còn. Cần tách mutation hoặc nhóm cell theo cùng deadline và điều chỉnh remaining riêng.

### Bài 3 — TTL hết trong lúc migrate

Nguồn trả TTL 1 giây; sau 4 giây mới tới lượt ghi vào target. Developer chọn `USING TTL 0` để tránh lỗi. Hậu quả?

**Đáp án:** TTL 0 nghĩa **không hết hạn**; giá trị có thể trở thành vĩnh viễn. Không ghi cell đã quá hạn, đồng thời xóa/reconcile stale target bằng luồng dữ liệu có thứ tự nếu nó tồn tại.

### Bài 4 — Backfill sau delete

Nguồn có V1 lúc 10:00. 10:01 ứng dụng DELETE K. 10:02 batch backfill cũ ghi V1 vào target với write timestamp hiện tại. Điều gì xảy ra và cách tránh?

**Đáp án:** V1 có thể sống lại ở đích nếu target không có tombstone/timestamp thắng V1; phải xử lý delete bằng CDC, đặt watermark/fencing, giữ đúng conflict timestamp và tránh backfill ghi đè ghi mới.

### Bài 5 — Strict deadline

Chính sách yêu cầu token hết hạn đúng mốc UTC với sai số tối đa 100 ms. Cassandra CQL TTL lưu số nguyên giây và bulk job mất vài phút. Có thể cam kết yêu cầu chỉ bằng `TTL(column)` và `INSERT USING TTL` không?

**Đáp án:** không thể đưa ra cam kết chính xác 100 ms chỉ dựa vào hai thao tác ấy. Cần deadline gốc ở logic/nghiệp vụ với cơ chế kiểm tra phù hợp, hoặc storage metadata/công cụ có độ chính xác đã xác minh; TTL Cassandra chủ yếu phù hợp dọn lưu trữ theo giây.

### Bài 6 — SSTable và thay đổi partition key

Nguồn `PRIMARY KEY (user_id, event_time)`, đích muốn `PRIMARY KEY ((tenant_id, day_bucket), event_time, user_id)`. Nhóm dự định chạy `sstableloader` để tự tạo partition mới và giữ TTL. Có đúng không?

**Đáp án:** không. SSTable loader dùng dữ liệu lưu trữ theo schema/layout phù hợp, không thực hiện arbitrary transformation partition key. Cần ETL/CQL, mapping key và retention protocol cho các cell.

### Checklist hoàn thành

- [ ] Phân biệt TTL ban đầu, TTL còn lại, WRITETIME và deadline tuyệt đối.
- [ ] Biết `TTL(column)=null` trên cell sống khác `USING TTL 0` và khác cell đã hết hạn.
- [ ] Dùng được CQL `TTL(payload)` và `WRITETIME(payload)`; không lấy timestamp làm deadline.
- [ ] Hiểu TTL có thể khác nhau từng cell, kể cả sau `UPDATE`.
- [ ] Biết chọn SSTable streaming khi cần giữ metadata và schema tương thích.
- [ ] Biết xử lý TTL còn lại, migration lag, rounding/safety margin trong CQL replay.
- [ ] Không ghi TTL 0 cho expired cell, không biến cell đã xóa thành giá trị vĩnh viễn.
- [ ] Có chiến lược CDC/dual-write, delete, idempotency và fencing khi nguồn còn nhận ghi.
- [ ] Đo TTL correctness theo deadline ở nguồn/đích, không chỉ row count và timeout.
- [ ] Kiểm tra RF/CL, clock skew, tombstone grace/repair và sai khác sau cutover.

## 13. Tài liệu tham khảo

1. Apache Cassandra Documentation — [CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `TTL(column)`, `WRITETIME(column)`, `USING TTL` và `USING TIMESTAMP`.
2. Apache Cassandra Documentation — [CQL Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): `default_time_to_live`, schema, primary key, compaction options.
3. Apache Cassandra Documentation — [Backups: snapshots, incremental backups và restore](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/backups.html).
4. Apache Cassandra Documentation — [sstableloader](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/sstable/sstableloader.html): streaming SSTable vào cluster đích.
5. Apache Cassandra Documentation — [Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html): expired data, `gc_grace_seconds` và reclamation.
6. Apache Cassandra Documentation — [Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): đồng bộ replica và rủi ro dữ liệu cũ hồi sinh.
7. Apache Cassandra Java Driver — [Mapper và prepared statement](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/): bind values, xử lý truy vấn ứng dụng khi di chuyển dữ liệu.

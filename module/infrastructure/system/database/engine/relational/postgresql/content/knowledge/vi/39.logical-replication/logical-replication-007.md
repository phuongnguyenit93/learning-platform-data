# Logical replication slot, WAL retention và quan sát tiến độ trong PostgreSQL

## 1. Vì sao logical replication slot quan trọng?

Logical replication cho phép PostgreSQL phát các thay đổi dữ liệu ở mức logic để một subscriber hoặc hệ thống CDC có thể nhận và áp dụng chúng. Khác với physical streaming replication, logical replication chuyển các thay đổi của những objects được publication chọn, chẳng hạn INSERT, UPDATE, DELETE và TRUNCATE trên các tables được publish.

Logical replication slot giữ trạng thái giải mã WAL cho một consumer. Slot cho PostgreSQL biết consumer đã xác nhận đến đâu và WAL cũ nhất nào vẫn có thể cần để tiếp tục logical decoding. Nhờ đó, publisher không xóa WAL mà consumer chưa xử lý.

Cơ chế này giúp consumer tiếp tục đọc thay đổi sau một khoảng gián đoạn, nhưng tạo ra một rủi ro vận hành: nếu consumer ngừng đọc, slot có thể giữ lại một lượng WAL ngày càng lớn trong thư mục pg_wal. Khi ổ đĩa đầy, primary có thể không ghi được WAL mới và toàn bộ workload ghi bị ảnh hưởng.

Để vận hành an toàn, cần theo dõi đồng thời:

- Slot có active hay không và consumer nào đang dùng slot.
- restart_lsn: WAL position cũ nhất còn cần cho decoding.
- confirmed_flush_lsn: vị trí consumer đã xác nhận.
- xmin và catalog_xmin: transaction/catalog horizons mà slot giữ lại.
- WAL bytes có thể đang bị giữ và disk headroom.
- Tiến độ gửi, nhận, apply và initial table synchronization.
- Error counters, slot invalidation và thời gian từ lần consumer tiến triển cuối.
- Tình trạng sau failover và khả năng khôi phục consumer.

```text
              PUBLISHER (wal_level = logical)
                         |
                 WAL records / changes
                         |
                         v
                 LOGICAL SLOT
            restart_lsn / confirmed_flush_lsn
                 xmin / catalog_xmin
                         |
                         v
                Logical decoding
                         |
              +----------+-----------+
              |                      |
              v                      v
        PostgreSQL              CDC connector
        subscriber              / event pipeline
              |                      |
              v                      v
        Apply changes          Persist downstream
              |                      |
              +----------+-----------+
                         |
                         v
                Consumer feedback
                         |
                         v
              Slot progress advances
                         |
                         v
                WAL can be recycled
```

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích logical replication slot bảo vệ WAL như thế nào.
2. Phân biệt logical slot với physical replication slot.
3. Hiểu restart_lsn, confirmed_flush_lsn, xmin và catalog_xmin.
4. Tạo logical slot và liên kết slot với subscription hoặc CDC consumer.
5. Hiểu quan hệ giữa wal_level, max_replication_slots và max_wal_senders.
6. Đọc trạng thái slot qua pg_replication_slots.
7. Ước lượng WAL đang bị giữ bởi một slot.
8. Phân biệt WAL retention với transaction/catalog tuple retention.
9. Hiểu tác động của long-running transactions và transaction chưa commit.
10. Giải thích max_slot_wal_keep_size và trạng thái WAL của slot.
11. Phân biệt max_wal_size, wal_keep_size và slot retention.
12. Theo dõi logical replication sender trên publisher.
13. Theo dõi apply workers và table synchronization trên subscriber.
14. Đọc pg_stat_subscription, pg_subscription_rel và replication origin status.
15. Theo dõi lỗi apply/sync và logical decoding spill khi phiên bản hỗ trợ.
16. Phân biệt received LSN, confirmed LSN, restart LSN và replay/apply progress.
17. Xử lý slot inactive, consumer lag và disk pressure.
18. Hiểu hậu quả khi slot bị invalidated hoặc mất WAL cần thiết.
19. Thiết kế alert và runbook cho CDC/replication consumers.
20. Kiểm chứng tiến độ và khả năng phục hồi bằng lab/restore drills.

## 3. Logical replication slot hoạt động như thế nào?

### 3.1. WAL là nguồn dữ liệu cho logical decoding

Mọi thay đổi cần durability đều được PostgreSQL ghi vào WAL. Với wal_level = logical, WAL chứa đủ thông tin cần thiết để logical decoding tái tạo các thay đổi logic mà plugin hỗ trợ.

Logical decoding đọc WAL, diễn giải các records thành changes và gửi chúng qua output plugin. Consumer nhận các changes, ghi vào đích rồi gửi feedback để publisher biết đến đâu dữ liệu đã được xử lý an toàn.

### 3.2. Slot giữ trạng thái decoding

Một logical slot lưu thông tin để lần đọc tiếp theo tiếp tục đúng vị trí và giữ các dữ liệu cần thiết cho decoding. Nếu consumer tạm ngắt kết nối, slot vẫn tồn tại và publisher giữ WAL cần thiết cho consumer quay lại, miễn là giới hạn retention và storage còn cho phép.

### 3.3. Slot không phải bản sao dữ liệu

Slot không lưu một bản đầy đủ của database, không thay thế backup và không tự gửi changes tới consumer. Nó giữ vị trí/trạng thái decoding cùng các horizons liên quan.

### 3.4. Mỗi consumer cần tiến độ riêng

Một slot là một luồng tiến độ. Nếu nhiều consumer độc lập cùng đọc một slot, feedback của một consumer có thể làm slot tiến qua changes mà consumer còn lại chưa xử lý. Dùng slot riêng cho mỗi consumer độc lập.

Ví dụ:

- Một slot cho subscription orders_sub.
- Một slot khác cho Debezium connector.
- Một slot khác cho pipeline analytics.

Không chia sẻ một slot giữa hai hệ thống chỉ vì chúng cùng cần một publication.

### 3.5. Slot có phạm vi database

Logical slot gắn với một database trên publisher và một output plugin. Nó không đại diện một logical stream duy nhất cho mọi database trong cluster. Khi quản lý nhiều databases, kiểm kê slots theo database và consumer.

## 4. Logical slot và physical slot khác nhau

| Tiêu chí | Logical replication slot | Physical replication slot |
| --- | --- | --- |
| Mục đích | Giữ WAL để logical decoding phát changes | Giữ WAL cho physical standby |
| Consumer | Subscription hoặc CDC client | Physical standby |
| Nội dung chuyển | Logical changes theo output plugin/publication | WAL để dựng trạng thái vật lý |
| confirmed_flush_lsn | Có ý nghĩa với logical consumer | Thường NULL |
| restart_lsn | WAL cũ nhất có thể cần cho decoding | WAL cũ nhất cần cho standby |
| xmin / catalog_xmin | Có thể giữ tuple/catalog horizons | Thường không dùng cùng semantics logical decoding |
| Khôi phục một table | Consumer có thể lọc/apply theo logic | Không cung cấp table-level stream |
| Rủi ro retention | WAL và tuple/catalog retention | WAL retention |

Một slot có thể tồn tại lâu sau khi consumer mất kết nối. Vì vậy, slot đang inactive không có nghĩa slot vô hại.

## 5. Điều kiện cấu hình phía publisher

### 5.1. wal_level = logical

Publisher phải dùng WAL level hỗ trợ logical decoding:

```conf
wal_level = logical
```

wal_level là tham số cần restart server để thay đổi trong các phiên bản PostgreSQL phổ biến. Kiểm tra giá trị hiệu lực:

```sql
SHOW wal_level;
```

Nếu wal_level chưa phải logical, logical replication slot/publication workflow có thể không hoạt động như mong đợi.

### 5.2. max_replication_slots

Đặt đủ slot capacity cho subscribers, CDC consumers và các logical slots khác:

```conf
max_replication_slots = 20
```

Giá trị thực tế phụ thuộc số consumer và slot dự phòng. Đây là giới hạn capacity của server, không phải số slot nên tạo tùy ý.

### 5.3. max_wal_senders

Logical replication dùng WAL sender processes để truyền changes:

```conf
max_wal_senders = 20
```

Cần tính cả physical standbys và các kết nối replication khác. Không đặt bằng đúng số subscribers nếu hệ thống còn physical replicas, backup connections hoặc CDC clients.

### 5.4. Kết nối và quyền

Consumer cần kết nối replication phù hợp và role có quyền cần thiết. pg_hba.conf phải cho phép kết nối từ đúng hosts, database và user. Ưu tiên role chuyên dụng với quyền tối thiểu.

### 5.5. Kiểm tra settings cùng lúc

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_catalog.pg_settings
WHERE name IN (
    'wal_level',
    'max_replication_slots',
    'max_wal_senders',
    'max_slot_wal_keep_size'
)
ORDER BY name;
```

Một số tham số hoặc cột phụ thuộc major version. Nếu không có row, kiểm tra version và tài liệu tương ứng.

## 6. Tạo logical replication slot

### 6.1. Slot cho logical decoding client

Có thể tạo slot trực tiếp bằng SQL:

```sql
SELECT *
FROM pg_catalog.pg_create_logical_replication_slot(
    'orders_cdc_slot',
    'pgoutput'
);
```

pgoutput là output plugin được PostgreSQL dùng cho native logical replication protocol. Một CDC client phải hiểu protocol và feedback semantics tương ứng.

### 6.2. Slot cho native subscription

Một subscription thường có thể tự tạo slot trên publisher:

```sql
CREATE SUBSCRIPTION orders_sub
CONNECTION 'host=publisher.example.internal port=5432 dbname=appdb user=repl_user'
PUBLICATION orders_publication
WITH (
    create_slot = true,
    enabled = true
);
```

Trong ví dụ này, PostgreSQL quản lý slot liên kết với subscription theo tên/option tương ứng. Kiểm tra subscription và slot thực tế sau khi tạo. Không tạo một slot trùng tên trước đó nếu create_slot = true sẽ cố tạo slot mới.

### 6.3. Tạo subscription dùng slot có sẵn

Khi slot đã được tạo trước, subscription có thể được cấu hình dùng slot đó với option phù hợp, chẳng hạn create_slot = false và slot_name rõ ràng. Phải bảo đảm slot tồn tại, thuộc đúng database và chưa bị consumer khác dùng.

### 6.4. Output plugin

Output plugin quyết định cách logical changes được mã hóa. pgoutput phục vụ native logical replication protocol. test_decoding là plugin thường dùng trong lab để xem output dạng text nếu được cài đặt.

Không giả định mọi PostgreSQL installation đều có cùng plugins. Kiểm tra package/extension và quyền trên server.

### 6.5. Một slot cho mỗi consumer độc lập

Mỗi consumer cần tiến độ và retention riêng. Nếu CDC pipeline A bị chậm, nó không nên làm consumer B mất changes hoặc nhận feedback của consumer B.

## 7. Các LSN quan trọng của logical slot

### 7.1. restart_lsn

restart_lsn là WAL position cũ nhất mà slot có thể còn cần để tiếp tục decoding. Publisher phải giữ WAL từ vị trí cần thiết này trở đi.

Nếu restart_lsn đứng yên trong khi current WAL LSN tiếp tục tăng, lượng WAL cần giữ có thể tăng.

### 7.2. confirmed_flush_lsn

Với logical slot, confirmed_flush_lsn là vị trí mà consumer đã xác nhận đã flush/được xử lý theo feedback protocol. Nó thể hiện tiến độ consumer đã xác nhận với publisher.

Không diễn giải nó là mọi event đã được business application xử lý xong nếu consumer chỉ xác nhận sau khi ghi vào queue hoặc một tầng trung gian. Semantics an toàn phụ thuộc cách consumer persist dữ liệu trước khi gửi feedback.

### 7.3. restart_lsn và confirmed_flush_lsn không nhất thiết bằng nhau

confirmed_flush_lsn có thể tiến nhanh hơn restart_lsn. Logical decoding có thể vẫn cần WAL cũ hơn do transaction đang mở, decoding state hoặc các yêu cầu nội bộ khác.

Vì vậy, chỉ nhìn confirmed_flush_lsn có thể bỏ sót WAL retention đang tăng.

### 7.4. xmin

xmin là transaction horizon mà slot có thể giữ để ngăn VACUUM loại bỏ tuple versions còn cần cho decoding. Đây là một loại retention khác với việc giữ WAL files.

### 7.5. catalog_xmin

catalog_xmin giữ lại các catalog rows cần thiết cho logical decoding. Nếu catalog horizon cũ, vacuum trên system catalogs có thể bị hạn chế.

### 7.6. Không có một cột nào mô tả toàn bộ health

Một slot có thể:

- Active nhưng tiến độ không tăng.
- Inactive nhưng vẫn giữ WAL.
- Có confirmed_flush_lsn mới nhưng restart_lsn cũ.
- Giữ xmin/catalog_xmin dù WAL retention chưa lớn.
- Đã mất WAL cần thiết và không thể tiếp tục.

Cần xem toàn bộ trạng thái, consumer và disk trend.

## 8. Đọc pg_replication_slots

Đây là view chính để kiểm kê slot trên publisher:

```sql
SELECT
    slot_name,
    plugin,
    slot_type,
    database,
    active,
    active_pid,
    xmin,
    catalog_xmin,
    restart_lsn,
    confirmed_flush_lsn,
    temporary
FROM pg_catalog.pg_replication_slots
ORDER BY slot_type, slot_name;
```

### 8.1. Các cột chính

| Cột | Ý nghĩa |
| --- | --- |
| slot_name | Tên slot |
| plugin | Output plugin của logical slot |
| slot_type | logical hoặc physical |
| database | Database gắn với logical slot |
| active | Slot đang được consumer sử dụng |
| active_pid | PID của backend đang giữ slot active |
| xmin | Transaction horizon slot giữ |
| catalog_xmin | Catalog horizon slot giữ |
| restart_lsn | WAL position cũ nhất có thể còn cần |
| confirmed_flush_lsn | Logical consumer progress đã xác nhận |
| temporary | Slot tạm thời, không có persistence như slot thường |

Một số cột chỉ có ở các PostgreSQL versions mới. Kiểm tra catalog của major version đang chạy trước khi triển khai query dashboard chung cho nhiều phiên bản.

### 8.2. Tìm slot inactive

```sql
SELECT
    slot_name,
    slot_type,
    database,
    plugin,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    xmin,
    catalog_xmin
FROM pg_catalog.pg_replication_slots
WHERE NOT active
ORDER BY slot_name;
```

Slot inactive cần được điều tra: consumer có đang bảo trì, bị lỗi, đã bị xóa ở phía ứng dụng hay bị bỏ quên?

### 8.3. Ghép active slot với backend

```sql
SELECT
    s.slot_name,
    s.slot_type,
    s.database,
    s.active,
    s.active_pid,
    a.usename,
    a.application_name,
    a.client_addr,
    a.state,
    a.backend_type,
    a.query_start
FROM pg_catalog.pg_replication_slots AS s
LEFT JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = s.active_pid
ORDER BY s.slot_name;
```

active_pid có thể NULL khi slot inactive. Dùng application_name có ý nghĩa để xác định đúng CDC service/subscriber.

## 9. Ước lượng WAL đang bị slot giữ

### 9.1. Tính khoảng cách từ current WAL tới restart_lsn

Trên publisher, có thể ước lượng khoảng WAL phía sau restart_lsn:

```sql
SELECT
    slot_name,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            restart_lsn
        )::bigint
    ) AS estimated_wal_span
FROM pg_catalog.pg_replication_slots
WHERE slot_type = 'logical'
ORDER BY pg_wal_lsn_diff(
    pg_current_wal_lsn(),
    restart_lsn
) DESC NULLS LAST;
```

Đây là khoảng WAL address space, không phải phép đo chính xác số bytes chỉ thuộc riêng slot. Nhiều slots có thể cùng cần các segments; các WAL records khác cũng nằm trong cùng khoảng.

### 9.2. Theo dõi trend thay vì một snapshot

Lưu định kỳ:

- Current WAL LSN.
- restart_lsn từng slot.
- confirmed_flush_lsn.
- Ước lượng khoảng WAL.
- Slot active/inactive.
- Disk usage của WAL directory.
- WAL generation rate.

Một khoảng WAL tăng liên tục là tín hiệu consumer không theo kịp hoặc decoding bị giữ bởi transaction khác.

### 9.3. Xem WAL directory

Một số môi trường cho phép dùng pg_ls_waldir() để đo số files và dung lượng:

```sql
SELECT
    count(*) AS wal_file_count,
    pg_size_pretty(sum(size)::bigint) AS wal_directory_size
FROM pg_catalog.pg_ls_waldir();
```

Quyền gọi hàm này phụ thuộc role/version. Đây là tổng dung lượng WAL directory, không thể quy toàn bộ cho một logical slot.

### 9.4. Không cộng retention estimates của mọi slot một cách máy móc

Các slots có thể cùng giữ một WAL range. Cộng từng estimated_wal_span sẽ đếm trùng các segments và phóng đại tổng dung lượng. Dùng nó để xếp hạng slot nào đang giữ horizon cũ, còn disk metrics là số đo storage thực tế.

### 9.5. Disk headroom quan trọng hơn tên trạng thái

Một slot có thể chưa vượt retention cap nhưng WAL directory vẫn gần đầy do workload WAL lớn, archive backlog, physical slots hoặc checkpoint behavior. Luôn theo dõi filesystem capacity.

## 10. max_slot_wal_keep_size và giới hạn retention

### 10.1. Unlimited retention

Trong các phiên bản hỗ trợ, max_slot_wal_keep_size = -1 có nghĩa không đặt giới hạn dung lượng WAL giữ bởi replication slots. Đây là mặc định phổ biến.

Nếu consumer dừng lâu, slot có thể giữ WAL không giới hạn cho đến khi storage bị đầy.

### 10.2. Đặt giới hạn

Ví dụ:

```conf
max_slot_wal_keep_size = '20GB'
```

Giới hạn này giúp bảo vệ storage khỏi một slot không tiến triển mãi mãi. Nhưng khi vượt giới hạn, PostgreSQL có thể recycle WAL cần thiết và slot trở nên không dùng được để tiếp tục từ vị trí cũ.

### 10.3. Giới hạn được áp dụng tại checkpoint

Slot WAL retention limit được kiểm tra theo cơ chế checkpoint, không phải một hard quota chính xác được thực thi ngay từng byte. WAL có thể vượt giới hạn tạm thời trước khi checkpoint xử lý.

### 10.4. Slot có thể bị invalidated

Khi WAL cần thiết đã bị recycle, logical consumer không thể tiếp tục decoding từ restart_lsn cũ. Cần kiểm tra trạng thái slot và logs. Thường phải tạo slot mới và thực hiện resnapshot/resync hoặc một recovery procedure tương thích với connector.

### 10.5. wal_status và safe_wal_size

Các PostgreSQL versions mới có thể cung cấp wal_status và safe_wal_size trong pg_replication_slots.

- reserved: WAL cần thiết vẫn nằm trong phạm vi được giữ.
- extended: slot đang khiến PostgreSQL giữ WAL vượt quá max_wal_size.
- unreserved: WAL không còn được bảo đảm giữ, dù một số segments có thể vẫn còn.
- lost: WAL cần thiết đã bị loại bỏ; slot không thể tiếp tục như trước.
- safe_wal_size: ước lượng bytes có thể ghi thêm trước khi slot có nguy cơ mất WAL, khi setting/cơ chế version hỗ trợ.

Các giá trị và cột phụ thuộc phiên bản. Nếu có, thêm chúng vào dashboard:

```sql
SELECT
    slot_name,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_catalog.pg_replication_slots
WHERE slot_type = 'logical';
```

### 10.6. max_slot_wal_keep_size không phải kế hoạch recovery

Đặt giới hạn chỉ quyết định mức WAL retention cho phép. Nó không tự tạo backup, không resync consumer và không bảo đảm dữ liệu downstream không bị mất. Phải có runbook xử lý slot lost.

## 11. Phân biệt max_wal_size, wal_keep_size và slot retention

| Setting | Mục đích | Có thay giới hạn slot WAL không? |
| --- | --- | --- |
| max_wal_size | Mục tiêu mềm cho WAL/checkpoint behavior | Không |
| wal_keep_size | Giữ tối thiểu một lượng WAL cho standby streaming theo cơ chế tương ứng | Không thay slot-specific retention |
| max_slot_wal_keep_size | Giới hạn WAL được giữ bởi replication slots | Có |
| archive_timeout | Buộc switch WAL segment theo khoảng thời gian nếu có activity phù hợp | Không |

max_wal_size không phải hard cap cho WAL directory; replication slots và archiving có thể khiến WAL directory lớn hơn. Không giảm max_wal_size để xử lý một logical slot bị kẹt.

wal_keep_size giúp physical standby có khoảng WAL dự phòng trong một số tình huống, nhưng logical slot cần được quản lý bằng slot retention settings và consumer progress.

## 12. Vì sao restart_lsn có thể đứng yên?

### 12.1. Consumer ngừng xác nhận

CDC connector có thể mất kết nối, crash hoặc bị pause. Khi không có feedback mới, slot không thể tiến confirmed position.

### 12.2. Consumer đọc nhưng không persist downstream

Consumer có thể đọc changes nhưng chưa ghi bền vững vào đích. Nếu chưa gửi flush feedback, publisher vẫn phải giữ dữ liệu. Đây là hành vi an toàn: consumer chỉ nên xác nhận sau khi dữ liệu đã được persist theo durability contract của pipeline.

### 12.3. Transaction dài trên publisher

Một transaction ghi dữ liệu lâu nhưng chưa commit có thể làm logical decoding cần giữ WAL cũ. Consumer có thể đã xác nhận phần lớn stream, nhưng restart_lsn vẫn bị giữ bởi transaction chưa hoàn tất.

### 12.4. Large transaction và decoding spill

Một transaction lớn có thể tạo nhiều changes trước khi commit. Logical decoding phải duy trì state cho transaction đó. Khi vượt logical_decoding_work_mem, dữ liệu decoding có thể spill ra disk theo cơ chế/version phù hợp. Spill ảnh hưởng I/O và hiệu năng decoding, còn WAL retention phụ thuộc vị trí cần thiết cho transaction.

### 12.5. Slot không được consumer sử dụng nữa

Slot còn lại sau khi connector bị xóa có thể giữ WAL vô thời hạn nếu không có giới hạn. Cần xác định owner và lifecycle trước khi drop.

### 12.6. Catalog/tuple horizons

Ngay cả khi WAL span không quá lớn, xmin hoặc catalog_xmin cũ có thể ngăn VACUUM dọn tuple/catalog versions. Theo dõi hai loại retention độc lập.

## 13. Theo dõi logical replication trên publisher

### 13.1. pg_stat_replication

View pg_stat_replication hiển thị các WAL sender đang kết nối trực tiếp. Với logical replication, có thể quan sát application name, state và các LSN positions được báo cáo:

```sql
SELECT
    pid,
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag,
    reply_time
FROM pg_catalog.pg_stat_replication
ORDER BY application_name;
```

### 13.2. Diễn giải thận trọng

Các LSN và lag columns trong pg_stat_replication hữu ích để xem sender/receiver feedback, nhưng semantics chi tiết khác nhau theo physical/logical replication và PostgreSQL version. Không đồng nhất replay_lsn của một logical subscriber với mọi bước xử lý business downstream.

### 13.3. Không thấy sender không có nghĩa slot đã bị xóa

pg_stat_replication chỉ hiển thị kết nối sender đang hoạt động. Slot inactive vẫn có thể tồn tại trong pg_replication_slots và tiếp tục giữ WAL.

### 13.4. application_name

Đặt application name rõ ràng trong connection string của CDC connector/subscriber. Nếu tất cả clients dùng tên chung hoặc mặc định, khó ghép sender với slot owner.

## 14. Theo dõi subscriber bằng pg_stat_subscription

### 14.1. View cơ bản

Trên subscriber:

```sql
SELECT
    subid,
    subname,
    pid,
    relid,
    received_lsn,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time
FROM pg_catalog.pg_stat_subscription
ORDER BY subname, relid;
```

### 14.2. Ý nghĩa các cột

| Cột | Ý nghĩa |
| --- | --- |
| subname | Subscription |
| pid | PID của worker |
| relid | Table liên quan nếu worker đang đồng bộ một relation |
| received_lsn | WAL position gần nhất được nhận theo view |
| last_msg_send_time | Thời điểm message cuối được sender gửi |
| last_msg_receipt_time | Thời điểm subscriber nhận message cuối |
| latest_end_lsn | End LSN mới nhất được báo trong feedback |
| latest_end_time | Thời điểm feedback/latest end được ghi nhận |

received_lsn và latest_end_lsn không tự động là bằng chứng mọi thay đổi đã được business service phía sau xử lý. Kết hợp với replication origin và kiểm tra dữ liệu trên subscriber.

### 14.3. Nhiều workers

Một subscription có thể có apply worker và table synchronization workers. Một row với relid có thể đại diện worker đồng bộ một relation; worker chính thường có relid NULL. Số lượng/loại workers và các cột bổ sung phụ thuộc version.

### 14.4. Không có PID

Nếu pid NULL hoặc không có row, worker có thể chưa được khởi động, đã thoát, subscription disabled hoặc đang gặp lỗi. Kiểm tra pg_subscription, logs và worker state.

### 14.5. Theo dõi thời gian message cuối

Nếu last_msg_receipt_time cũ trong khi publisher vẫn ghi WAL, có thể có network disconnect, sender failure hoặc consumer không nhận message. Nếu publisher không có workload, timestamp cũ tự nó chưa chứng minh lỗi.

## 15. Theo dõi trạng thái đồng bộ từng table

### 15.1. pg_subscription_rel

Initial table synchronization có trạng thái riêng trong catalog pg_subscription_rel.

```sql
SELECT
    s.subname,
    r.srrelid::regclass AS relation,
    r.srsubstate,
    r.srsublsn
FROM pg_catalog.pg_subscription_rel AS r
JOIN pg_catalog.pg_subscription AS s
  ON s.oid = r.srsubid
ORDER BY s.subname, r.srrelid::regclass::text;
```

### 15.2. Các trạng thái thường gặp

| State | Ý nghĩa |
| --- | --- |
| i | Initialize: bắt đầu đồng bộ |
| d | Data copy đang diễn ra |
| f | Copy hoàn tất |
| s | Đang đồng bộ/catch up |
| r | Ready: table đã sẵn sàng theo trạng thái subscription |

Các state transitions và cách hiển thị phụ thuộc version. Dùng catalog này để xác định table nào chưa hoàn tất initial sync.

### 15.3. Một subscription có thể hoạt động nhưng một table chưa ready

Apply worker có thể đang chạy cho các tables đã đồng bộ trong khi một table khác còn ở trạng thái copy/catch-up. Đừng chỉ kiểm tra subscription tồn tại rồi kết luận toàn bộ publication đã replicate đầy đủ.

### 15.4. Table sync worker

Khi initial copy, PostgreSQL có thể chạy worker riêng cho từng table. Xem pg_stat_subscription.relid, pg_stat_activity và logs để xác định relation nào đang đồng bộ.

### 15.5. pg_stat_progress_copy

Trong các phiên bản và đường thực thi có hỗ trợ, pg_stat_progress_copy có thể hiển thị tiến độ COPY:

```sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    command,
    type,
    bytes_processed,
    bytes_total,
    tuples_processed,
    tuples_excluded
FROM pg_catalog.pg_stat_progress_copy;
```

Không phải mọi table synchronization worker đều cung cấp một tiến độ bytes/total hữu ích trong mọi version. Nếu bytes_total không biết hoặc không có row, dùng table sync state, worker activity và logs.

## 16. Theo dõi replication origin trên subscriber

### 16.1. Origin giữ vị trí nguồn

Logical replication subscriber dùng replication origin để ghi nhận tiến độ đã áp dụng từ nguồn. pg_replication_origin_status giúp xem remote LSN và local LSN tương ứng.

```sql
SELECT
    local_id,
    external_id,
    remote_lsn,
    local_lsn
FROM pg_catalog.pg_replication_origin_status
ORDER BY external_id;
```

### 16.2. remote_lsn

remote_lsn cho biết vị trí từ nguồn mà origin đã ghi nhận tiến độ. Nó hữu ích để đối chiếu với publisher slot và subscription status.

### 16.3. local_lsn

local_lsn là vị trí WAL local liên quan tới tiến độ origin trên subscriber. Nó không phải cùng một không gian LSN với remote publisher.

### 16.4. Không trừ hai LSN thuộc hai cluster

Không dùng pg_wal_lsn_diff(remote_lsn, local_lsn) để tính lag; hai LSN thuộc hai WAL streams khác nhau. So sánh từng vị trí với đúng source/destination metadata.

### 16.5. Origin name và topology

Khi có nhiều publishers hoặc cascading data pipelines, map external_id với subscription/source identity. Không suy luận chỉ từ numeric local_id.

## 17. Theo dõi lỗi apply và sync

### 17.1. Logs là bằng chứng chính cho lỗi cụ thể

Logical replication worker có thể gặp:

- Vi phạm unique/foreign key constraints.
- Schema hoặc column mismatch.
- Permission errors.
- Network disconnect.
- Missing publication/table.
- Conflict do dữ liệu subscriber đã thay đổi độc lập.
- Slot bị mất hoặc WAL không còn.
- Serialization/type conversion errors.

Lưu logs của cả publisher và subscriber cùng thời điểm để xác định phía gây lỗi.

### 17.2. pg_stat_subscription_stats

Các PostgreSQL versions hỗ trợ có view pg_stat_subscription_stats để theo dõi error counters, ví dụ apply errors và table synchronization errors:

```sql
SELECT *
FROM pg_catalog.pg_stat_subscription_stats;
```

Tên cột, thời điểm có mặt và reset behavior phụ thuộc version. Khi dùng monitoring đa phiên bản, kiểm tra catalog/view trước khi cố định schema metric.

### 17.3. pg_stat_activity

```sql
SELECT
    pid,
    backend_type,
    application_name,
    usename,
    datname,
    state,
    wait_event_type,
    wait_event,
    query_start,
    clock_timestamp() - query_start AS runtime,
    left(query, 300) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE backend_type LIKE '%logical replication%'
   OR application_name ILIKE '%subscription%'
ORDER BY query_start;
```

Tên backend_type và application name có thể khác giữa các major versions và implementation. Dùng logs để bổ sung khi filter không khớp.

### 17.4. Error counters không thay logs

Counters cho biết lỗi đã tăng, nhưng không luôn chứa nguyên nhân, relation hay SQL details. Cần logs và subscription state để chẩn đoán.

### 17.5. Reset statistics

Counters có thể bị reset. Lưu scrape history ở monitoring system và ghi lại thời điểm reset để không hiểu nhầm counter giảm là lỗi đã hết.

## 18. Logical decoding spill và hiệu năng

### 18.1. Transaction lớn

Một transaction lớn có thể tạo nhiều changes trước khi commit. Logical decoder phải giữ state để phát changes đúng thứ tự/transaction semantics.

### 18.2. logical_decoding_work_mem

Tham số logical_decoding_work_mem giới hạn memory được dùng bởi logical decoding trước khi spill state ra disk theo cơ chế hỗ trợ của version:

```sql
SHOW logical_decoding_work_mem;
```

Tăng giá trị có thể giảm spill nhưng tiêu thụ RAM nhiều hơn. Giảm quá thấp có thể tăng disk I/O.

### 18.3. Spill không giống WAL retention

Spill là dữ liệu decoding tạm thời được ghi ra disk để xử lý transaction lớn. WAL retention là việc publisher phải giữ WAL segments vì slot còn cần chúng. Hai vấn đề có thể cùng xuất hiện nhưng phải đo riêng.

### 18.4. pg_stat_replication_slots

Các PostgreSQL versions mới có thể cung cấp pg_stat_replication_slots với metrics như transactions/bytes được spill, stream và tổng decoding. Nếu view có trên server:

```sql
SELECT *
FROM pg_catalog.pg_stat_replication_slots;
```

Các cột thống kê và version availability phụ thuộc major version. Không hard-code dashboard cho một view chưa có trên các server cũ.

### 18.5. Workload lớn và streaming in-progress transactions

Một số logical replication/decoding modes có thể stream nội dung transaction lớn trước khi transaction commit, tùy version và cấu hình. Điều này có thể giảm việc phải giữ toàn bộ transaction trong memory nhưng không xóa yêu cầu về WAL retention và commit semantics.

## 19. Slot retention và vacuum horizon

### 19.1. Hai loại tài nguyên bị giữ

Logical slot có thể ảnh hưởng:

1. **WAL retention:** restart_lsn quyết định WAL cũ nhất còn có thể cần.
2. **Tuple/catalog retention:** xmin và catalog_xmin có thể ngăn VACUUM xóa các row versions/catalog rows cần cho decoding.

Giải quyết disk WAL không tự động giải phóng tuple/catalog horizon nếu slot vẫn giữ xmin.

### 19.2. Tác động tới bảng user

Một slot giữ xmin cũ có thể làm dead tuples tồn tại lâu hơn trên các tables có write churn. Autovacuum vẫn có thể chạy nhưng phải giữ những tuple versions chưa an toàn.

### 19.3. Tác động tới system catalogs

catalog_xmin có thể giữ catalog rows lâu hơn, làm tăng catalog bloat hoặc cản trở cleanup. Theo dõi slot horizon ngay cả khi user tables có dead tuple estimate thấp.

### 19.4. Kiểm tra slot horizons

```sql
SELECT
    slot_name,
    database,
    active,
    xmin,
    CASE WHEN xmin IS NOT NULL THEN age(xmin) END AS xmin_age,
    catalog_xmin,
    CASE
        WHEN catalog_xmin IS NOT NULL
        THEN age(catalog_xmin)
    END AS catalog_xmin_age,
    restart_lsn
FROM pg_catalog.pg_replication_slots
WHERE slot_type = 'logical'
ORDER BY GREATEST(
    COALESCE(age(xmin), 0),
    COALESCE(age(catalog_xmin), 0)
) DESC;
```

### 19.5. Không bỏ qua XID safety

Slot giữ horizon lâu có thể góp phần làm vacuum/freeze progress khó khăn hơn. Theo dõi database/table XID age và anti-wraparound warnings; không chờ đến khi disk đầy mới xử lý.

## 20. Inactive slot và WAL growth

### 20.1. Inactive không đồng nghĩa đã hết giá trị

Slot có thể inactive vì consumer đang restart, bảo trì hoặc network outage. Nhưng cũng có thể là slot orphaned từ connector đã bị xóa. Phải xác định owner trước khi hành động.

### 20.2. WAL tăng nhanh

Nếu workload ghi WAL nhanh và consumer không tiến, khoảng từ current LSN tới restart_lsn sẽ tăng. Một slot inactive trong nhiều giờ có thể giữ nhiều GB/TB tùy workload.

### 20.3. Tính thời gian tới disk exhaustion

Theo dõi disk free và WAL generation rate. Có thể ước lượng:

```text
time_to_full ≈ available_disk_bytes / net_wal_growth_bytes_per_second
```

Đây là ước lượng vận hành. Net growth còn phụ thuộc checkpoint, archive, other slots, WAL recycling và storage cleanup. Không dùng công thức đơn giản để thay alert disk thực tế.

### 20.4. WAL archive có thể vẫn thành công nhưng WAL directory vẫn lớn

Archiving WAL không đồng nghĩa slot đã xác nhận tiến độ. PostgreSQL có thể vẫn phải giữ segments trong WAL directory cho slot dù archive copy đã tồn tại ở storage khác.

### 20.5. Không xóa thủ công WAL files

Không dùng filesystem delete để giải phóng WAL mà PostgreSQL quản lý. Có thể làm hỏng recovery/replication hoặc khiến server không hoạt động. Xử lý qua slot, retention settings và quy trình PostgreSQL.

## 21. Slot bị mất WAL hoặc invalidated

### 21.1. Dấu hiệu

- wal_status = lost ở version có cột này.
- Logs báo slot không còn đủ WAL hoặc slot invalidated.
- Consumer reconnect nhưng không thể tiếp tục từ vị trí cũ.
- Logical decoding báo lỗi vì WAL cần thiết không còn.

### 21.2. Không thể khôi phục changes đã bị bỏ

Nếu WAL segments cần thiết đã bị recycle, slot không thể tái tạo changes đó từ khoảng WAL bị mất. Tăng retention sau khi mất WAL không thể đưa dữ liệu đã xóa trở lại.

### 21.3. Recreate slot

Có thể cần drop/recreate slot và thực hiện initial snapshot/resync hoặc quy trình bootstrap riêng của CDC connector. Việc này có thể tạo tải lớn và cần tránh duplicate/missing events bằng cutover checkpoint có kiểm soát.

### 21.4. Kiểm tra downstream consistency

Sau resync, so sánh row counts, keys, offsets/checkpoints và event sequence. Không chỉ thấy connector chuyển sang running là đủ.

### 21.5. Phòng ngừa

- Đặt giới hạn retention phù hợp.
- Alert sớm khi safe_wal_size thấp.
- Giám sát slot inactive và lag.
- Bảo đảm consumer có retry/backoff phù hợp.
- Có capacity cho resnapshot.
- Không xóa WAL hoặc slot tùy tiện.

## 22. Quản lý lifecycle của slot

### 22.1. Liệt kê trước khi tạo

Kiểm tra tên slot đã tồn tại chưa và có consumer nào đang sử dụng. Slot name phải duy nhất trong phạm vi server.

### 22.2. Drop slot

```sql
SELECT pg_catalog.pg_drop_replication_slot('orders_cdc_slot');
```

Không thể drop một slot đang active. Trước khi drop, xác nhận consumer đã dừng và owner chấp thuận việc mất khả năng đọc tiếp từ slot đó.

### 22.3. Advance slot

PostgreSQL cung cấp hàm advance slot trong các phiên bản hỗ trợ:

```sql
SELECT *
FROM pg_catalog.pg_replication_slot_advance(
    'orders_cdc_slot',
    '0/16B6C50'::pg_lsn
);
```

Advance slot bỏ qua changes trước vị trí được yêu cầu theo semantics của slot. Đây là thao tác có thể gây mất dữ liệu downstream; chỉ dùng khi đã có checkpoint/resync plan rõ ràng.

### 22.4. SQL decoding functions trong lab

Với output plugin dạng text như test_decoding nếu đã cài, có thể quan sát changes:

```sql
SELECT *
FROM pg_catalog.pg_create_logical_replication_slot(
    'lab_text_slot',
    'test_decoding'
);

SELECT *
FROM pg_catalog.pg_logical_slot_peek_changes(
    'lab_text_slot',
    NULL,
    10
);
```

peek_changes đọc mà không advance slot. Hàm pg_logical_slot_get_changes đọc và consume changes, làm slot tiến lên. Không dùng các SQL functions này với output plugin/protocol không hỗ trợ dạng record text như thể mọi plugin đều tương đương.

### 22.5. Temporary slots

Temporary slots tồn tại gắn với session/lifecycle và không có persistence như permanent slots. Không dùng temporary slot cho CDC cần tiếp tục qua restart/disconnect.

## 23. Initial table synchronization

### 23.1. Logical replication có giai đoạn copy dữ liệu ban đầu

Khi subscription được tạo với copy_data = true (mặc định phổ biến), PostgreSQL cần copy dữ liệu hiện có của các tables rồi đồng bộ changes phát sinh trong lúc copy.

### 23.2. Slot giữ changes trong lúc copy

Publisher cần giữ WAL/changes để subscriber có thể bắt kịp snapshot ban đầu. Nếu initial sync kéo dài, WAL retention và storage pressure có thể tăng.

### 23.3. Nhiều tables có thể sync song song

Các worker sync giúp tăng tốc nhưng tiêu thụ connection, CPU, I/O và network. Tuning max_sync_workers_per_subscription cùng max_logical_replication_workers theo version và workload.

### 23.4. Theo dõi trạng thái từng table

Dùng pg_subscription_rel để xác định table nào đang initialize, copy, catch-up hoặc ready. Một subscription có thể chưa hoàn tất toàn bộ initial sync dù apply worker đã chạy.

### 23.5. Initial copy có thể tạo tải lớn

Copy toàn bộ table có thể cạnh tranh với workload production. Lập kế hoạch cho dung lượng subscriber, network, locks và thời gian catch-up.

## 24. Native logical replication không replicate mọi thứ

### 24.1. DDL

Logical replication native tập trung vào row changes. Schema/DDL changes thường phải được triển khai riêng trên subscriber theo migration process.

### 24.2. Sequences

Sequence state không được replicate như row changes thông thường. Khi cutover, cần đồng bộ sequence values theo quy trình phù hợp để tránh duplicate keys.

### 24.3. Large objects

Large objects không được native logical replication tự động replicate theo cách row tables được replicate. Cần chiến lược riêng nếu ứng dụng sử dụng chúng.

### 24.4. Publications

Publication xác định tables/operations được publish. Slot có thể hoạt động bình thường nhưng consumer không nhận một table nếu table không thuộc publication hoặc operation không được publish.

### 24.5. Subscriber writes

Nếu subscriber được phép ghi độc lập vào cùng tables, có thể phát sinh conflicts hoặc divergence. Thiết kế ownership của dữ liệu và write direction rõ ràng.

## 25. Failover và logical slot continuity

### 25.1. Slot là state cần được bảo vệ

Logical slot có progress và horizons riêng. Khi primary failover, không mặc định logical slot trên primary cũ tự xuất hiện đầy đủ trên promoted standby.

### 25.2. Version và topology ảnh hưởng khả năng đồng bộ slots

Các PostgreSQL versions mới có thêm cơ chế failover logical slots và đồng bộ slot state trong topology được cấu hình phù hợp. Availability, prerequisites và behavior thay đổi theo major version. Kiểm tra tài liệu đúng phiên bản trước khi dựa vào failover slots.

### 25.3. Failover slots cần thiết kế trước

Đánh giá:

- Slot nào cần tiếp tục sau promotion?
- Standby có nhận và đồng bộ slot state không?
- WAL cần thiết còn trên promoted server/archive không?
- Consumer có thể reconnect và tiếp tục từ checkpoint nào?
- Có cần resnapshot nếu slot continuity bị mất?

### 25.4. Không để hai consumer cùng xử lý một stream sau failover

Consumer phải biết primary mới và checkpoint hợp lệ. Tránh split-brain CDC hoặc hai instances cùng ghi downstream mà không có idempotency/ownership.

### 25.5. Failover drill

Thử failover trong lab, xác minh slot tồn tại/được đồng bộ theo thiết kế, consumer reconnect, không có gap/duplicate ngoài semantics chấp nhận và downstream state đúng.

## 26. Dashboard monitoring đề xuất

| Nhóm | Metric | Nơi quan sát | Ý nghĩa |
| --- | --- | --- | --- |
| Slot inventory | slot name/type/database/plugin | Publisher pg_replication_slots | Biết owner và scope |
| Consumer state | active, active_pid | Publisher | Consumer có kết nối không |
| WAL retention | restart_lsn, current LSN span | Publisher | Slot giữ WAL cũ đến đâu |
| Consumer progress | confirmed_flush_lsn | Publisher | Vị trí consumer xác nhận |
| Tuple horizon | xmin, age(xmin) | Publisher | User tuple retention |
| Catalog horizon | catalog_xmin, age(catalog_xmin) | Publisher | Catalog retention |
| Slot safety | wal_status, safe_wal_size | Publisher, version-dependent | Nguy cơ slot lost |
| Sender progress | sent/write/flush/replay LSN | Publisher pg_stat_replication | Trạng thái truyền/feedback |
| Subscription | received_lsn, latest_end_lsn/time | Subscriber pg_stat_subscription | Nhận và feedback progress |
| Table sync | srsubstate, srsublsn | Subscriber pg_subscription_rel | Initial sync theo table |
| Apply workers | PID, backend type, wait | Subscriber pg_stat_activity | Worker health |
| Origin progress | remote_lsn, local_lsn | Subscriber origin status | Apply origin checkpoint |
| Errors | apply/sync error counters | Subscriber, version-dependent | Phát hiện lỗi |
| Decoding spill | spill/stream bytes | Publisher, version-dependent | Logical decoding pressure |
| Disk | pg_wal bytes, free bytes | OS/storage | Nguy cơ đầy đĩa |
| WAL rate | WAL bytes per second | pg_stat_wal/monitoring | Ước lượng growth |
| Database health | dead tuples, XID age | Publisher statistics | Tuple retention impact |

### 26.1. Alert slot inactive

Alert khi một slot quan trọng inactive lâu hơn ngưỡng vận hành. Phân biệt maintenance có lịch với consumer bị mất.

### 26.2. Alert restart_lsn đứng yên

Lưu lịch sử LSN. Alert khi restart_lsn không tiến trong khi current WAL LSN tiếp tục tăng và slot retention span vượt baseline.

### 26.3. Alert safe_wal_size

Nếu cột có sẵn, alert khi safe WAL size xuống thấp hoặc wal_status chuyển sang trạng thái không an toàn. Đặt ngưỡng dựa trên WAL generation rate và thời gian xử lý incident.

### 26.4. Alert disk headroom

Alert theo filesystem free bytes và tốc độ tăng WAL directory. Đừng chờ slot status chuyển lost mới cảnh báo.

### 26.5. Alert xmin age

Alert khi slot xmin hoặc catalog_xmin quá cũ so với transaction rate và wraparound safety limits.

### 26.6. Alert subscriber stale

Trên subscriber, theo dõi last_msg_receipt_time, latest_end_time, worker PID và origin progress. Timestamp cũ cần đối chiếu với publisher workload và network state.

### 26.7. Counter phải được lưu thành time series

Apply errors và decoding stats có thể reset. Scrape định kỳ để tính delta/rate, đồng thời lưu reset timestamp.

## 27. Runbook: logical slot giữ WAL tăng nhanh

### Bước 1. Xác định slot và owner

Lấy slot name, database, plugin, consumer, application_name, active_pid và owner. Kiểm tra slot có thuộc subscription hay CDC connector đã ngừng sử dụng.

### Bước 2. Đo retention

Đọc restart_lsn, confirmed_flush_lsn, current WAL LSN, wal_status, safe_wal_size nếu có và disk free.

### Bước 3. Xác định consumer có tiến triển

Trên subscriber/connector, xem received/confirmed positions, last message time, worker PID, errors và downstream persistence.

### Bước 4. Kiểm tra transaction dài

Nếu confirmed progress tăng nhưng restart LSN đứng yên, kiểm tra transaction chưa commit trên publisher và logical decoding state. Xem pg_stat_activity và transaction age.

### Bước 5. Kiểm tra slot horizons

Đọc xmin và catalog_xmin; xem VACUUM/dead tuple estimates và catalog pressure.

### Bước 6. Kiểm tra WAL generation và disk

Đo WAL bytes/second, archive backlog, slot count và filesystem capacity. Tính thời gian còn lại theo tốc độ net growth.

### Bước 7. Chọn hành động

- Consumer tạm ngắt: khôi phục kết nối/worker và xác minh slot tiến lên.
- Consumer lỗi apply: xử lý schema/data conflict theo runbook subscriber.
- Transaction dài: xác định owner và xử lý có kiểm soát.
- Slot orphaned: xác nhận không còn consumer trước khi drop.
- Slot gần retention cap: giảm WAL growth hoặc khôi phục consumer; chuẩn bị resync nếu slot bị mất.
- Disk gần đầy: ưu tiên khôi phục tiến độ/giảm tải theo incident procedure; không xóa file WAL thủ công.

### Bước 8. Nếu slot đã lost

Xác định checkpoint cuối còn dùng được, tạo slot mới nếu cần, resnapshot/resync consumer và kiểm tra duplicates/gaps. Không giả định slot có thể tiếp tục từ LSN cũ.

### Bước 9. Xác minh

Theo dõi restart_lsn và confirmed_flush_lsn tiến lên, WAL directory ổn định, disk headroom hồi phục, subscriber apply state bình thường và downstream data hợp lệ.

### Bước 10. Cập nhật lifecycle

Ghi owner, alert threshold, retention cap, restart/resync procedure và failover plan cho slot.

## 28. Các tình huống chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Bằng chứng tiếp theo |
| --- | --- | --- |
| Slot inactive, WAL tăng | Consumer mất kết nối hoặc bị pause | Owner, logs, active_pid, restart_lsn |
| Active nhưng confirmed_flush_lsn đứng yên | Consumer kết nối nhưng không acknowledge | Connector logs, downstream persistence |
| confirmed_flush_lsn tiến nhưng restart_lsn đứng yên | Transaction dài/decoding state còn giữ WAL | Publisher xact age, decoding metrics |
| WAL directory lớn, slot span nhỏ | Archive backlog, physical slot hoặc WAL workload khác | Archive status, all slots, disk metrics |
| wal_status lost | WAL cần thiết đã bị recycle | Logs, backup/checkpoint, resync plan |
| xmin cũ, dead tuples tăng | Logical slot giữ tuple horizon | Slot xmin, autovacuum, table stats |
| catalog_xmin cũ | Slot giữ catalog horizon | Catalog age, slot lifecycle |
| Subscription có worker nhưng table chưa ready | Initial sync chưa hoàn tất | pg_subscription_rel state |
| Subscriber nhận WAL nhưng data không mới | Apply worker lỗi/chậm hoặc transaction chưa commit | Logs, origin status, constraints |
| LSNs không khớp | So sánh sai cluster hoặc sai loại LSN | Source identity, origin, timeline |
| Slot bị drop | Consumer không thể tiếp tục slot cũ | Consumer checkpoint và bootstrap procedure |
| Disk đầy sau connector outage | Retention không có giới hạn hoặc alert quá muộn | max_slot_wal_keep_size, disk history |
| Failover xong CDC không chạy | Slot không được đồng bộ/không có ở primary mới | Version support, failover slot setup |
| Apply errors tăng | Schema/data mismatch hoặc constraint conflict | Subscriber logs và DDL history |

## 29. Các sai lầm cần tránh

1. Coi logical slot là bản backup.
2. Chỉ theo dõi active mà bỏ qua LSN và retention.
3. Chỉ nhìn confirmed_flush_lsn mà không xem restart_lsn.
4. Coi restart_lsn và confirmed_flush_lsn phải luôn bằng nhau.
5. Coi max_wal_size là hard cap cho WAL được slot giữ.
6. Dùng wal_keep_size thay cho slot retention management.
7. Đặt max_slot_wal_keep_size = -1 mà không có disk alert.
8. Đặt retention cap quá thấp khiến slot bị lost trước khi consumer hồi phục.
9. Drop slot inactive mà không xác định owner.
10. Advance slot để giải phóng WAL mà không có resync plan.
11. Xóa thủ công WAL files trong WAL directory.
12. Dùng chung một slot cho nhiều consumers độc lập.
13. Coi confirmed_flush_lsn là business processing checkpoint.
14. Bỏ qua transaction dài trên publisher.
15. Bỏ qua xmin và catalog_xmin.
16. Coi subscription tồn tại nghĩa mọi tables đã ready.
17. Không theo dõi initial table synchronization.
18. Coi received_lsn là dữ liệu đã được downstream xử lý.
19. So sánh LSN từ hai clusters khác nhau bằng phép trừ.
20. Bỏ qua apply errors và chỉ xem network connection.
21. Giả định slot tự tồn tại sau mọi failover.
22. Bật logical replication mà không kiểm tra wal_level.
23. Không tính physical standbys khi đặt max_wal_senders.
24. Không lưu slot owner và resync procedure.
25. Chỉ kiểm tra backup/WAL archive mà không kiểm tra consumer progress.

## 30. Bài tập thực hành có đáp án

Các bài tập giả định bạn có một PostgreSQL publisher/subscriber lab hoặc CDC connector riêng. Không drop/advance production slot để thử.

### Bài 1. Logical replication slot là gì?

**Đáp án:** Trạng thái decoding và tiến độ giúp publisher giữ WAL cần thiết cho một logical consumer.

### Bài 2. Slot có phải bản sao database không?

**Đáp án:** Không. Nó giữ vị trí/horizon cho decoding, không lưu full database copy.

### Bài 3. Logical slot gắn với phạm vi nào?

**Đáp án:** Một database trên publisher và một output plugin.

### Bài 4. Output plugin phổ biến cho native logical replication?

**Đáp án:** pgoutput.

### Bài 5. Setting WAL level nào cần cho logical replication?

**Đáp án:** wal_level = logical.

### Bài 6. Tham số nào giới hạn số replication slots?

**Đáp án:** max_replication_slots.

### Bài 7. Tham số nào giới hạn WAL sender processes?

**Đáp án:** max_wal_senders.

### Bài 8. restart_lsn là gì?

**Đáp án:** WAL position cũ nhất mà slot có thể còn cần để tiếp tục decoding.

### Bài 9. confirmed_flush_lsn là gì?

**Đáp án:** Vị trí logical consumer đã xác nhận flush/processing theo replication feedback protocol.

### Bài 10. Hai LSN này có luôn bằng nhau?

**Đáp án:** Không. Decoding có thể vẫn cần WAL cũ hơn do transaction hoặc internal state.

### Bài 11. xmin có ý nghĩa gì?

**Đáp án:** Transaction horizon có thể giữ tuple versions để logical decoding còn đọc được dữ liệu cần thiết.

### Bài 12. catalog_xmin có ý nghĩa gì?

**Đáp án:** Catalog horizon giữ các catalog rows cần cho logical decoding.

### Bài 13. View nào kiểm kê slots?

**Đáp án:** pg_replication_slots.

### Bài 14. Cột nào cho biết slot đang được consumer dùng?

**Đáp án:** active, cùng active_pid.

### Bài 15. Slot inactive có thể giữ WAL không?

**Đáp án:** Có. Slot persistent có thể giữ WAL ngay cả khi consumer disconnected.

### Bài 16. Tạo logical slot bằng hàm nào?

**Đáp án:** pg_create_logical_replication_slot().

### Bài 17. Native subscription có thể tự tạo slot không?

**Đáp án:** Có, khi CREATE SUBSCRIPTION dùng create_slot = true.

### Bài 18. Vì sao mỗi consumer độc lập cần slot riêng?

**Đáp án:** Mỗi slot có một tiến độ; consumer này advance slot có thể khiến consumer khác bỏ lỡ changes.

### Bài 19. Ước lượng WAL span từ restart_lsn bằng hàm nào?

**Đáp án:** pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn).

### Bài 20. WAL span có phải dung lượng chính xác riêng của slot?

**Đáp án:** Không. Nó là khoảng WAL address space và có thể trùng giữa nhiều slots.

### Bài 21. max_slot_wal_keep_size điều khiển gì?

**Đáp án:** Giới hạn WAL được giữ bởi replication slots trong các phiên bản hỗ trợ.

### Bài 22. Giá trị -1 thường có nghĩa gì?

**Đáp án:** Không giới hạn slot WAL retention theo setting này.

### Bài 23. Nếu slot vượt retention cap có thể xảy ra gì?

**Đáp án:** WAL cần thiết có thể bị recycle và slot bị invalidated/lost.

### Bài 24. wal_status = lost nghĩa gì?

**Đáp án:** WAL cần thiết cho slot đã bị loại bỏ; slot không thể tiếp tục từ vị trí cũ.

### Bài 25. safe_wal_size giúp gì?

**Đáp án:** Ước lượng bytes còn có thể ghi trước khi slot có nguy cơ mất WAL, khi version hỗ trợ.

### Bài 26. max_wal_size có phải hard cap cho pg_wal?

**Đáp án:** Không. Nó là mục tiêu mềm cho checkpoint/WAL behavior.

### Bài 27. wal_keep_size thay thế logical slot retention không?

**Đáp án:** Không. Nó phục vụ retention tối thiểu cho standby theo cơ chế khác.

### Bài 28. View nào theo dõi logical replication sender trên publisher?

**Đáp án:** pg_stat_replication.

### Bài 29. View nào theo dõi subscription workers trên subscriber?

**Đáp án:** pg_stat_subscription.

### Bài 30. received_lsn có đồng nghĩa mọi changes đã được business service xử lý?

**Đáp án:** Không. Nó là receive progress, cần kiểm tra apply/origin và downstream persistence.

### Bài 31. pg_subscription_rel dùng làm gì?

**Đáp án:** Theo dõi trạng thái initial synchronization của từng table trong subscription.

### Bài 32. State d trong pg_subscription_rel thường có nghĩa gì?

**Đáp án:** Data copy đang diễn ra.

### Bài 33. State r thường có nghĩa gì?

**Đáp án:** Table đã ready theo trạng thái subscription.

### Bài 34. View nào có thể cho biết COPY progress?

**Đáp án:** pg_stat_progress_copy trong các trường hợp/version có hỗ trợ.

### Bài 35. pg_replication_origin_status hiển thị gì?

**Đáp án:** Remote LSN và local LSN liên quan tới replication origin trên subscriber.

### Bài 36. Có thể trừ remote_lsn với local_lsn không?

**Đáp án:** Không. Chúng thuộc hai WAL address spaces khác nhau.

### Bài 37. pg_stat_subscription_stats giúp gì?

**Đáp án:** Theo dõi apply/synchronization error counters ở các phiên bản có view này.

### Bài 38. Vì sao logs vẫn cần thiết?

**Đáp án:** Counters không chứa đủ nguyên nhân và context của từng lỗi.

### Bài 39. logical_decoding_work_mem ảnh hưởng gì?

**Đáp án:** Giới hạn memory decoding trước khi state có thể spill ra disk theo cơ chế hỗ trợ.

### Bài 40. Decoding spill có giống WAL retention?

**Đáp án:** Không. Spill là temporary decoding state; WAL retention là giữ WAL segments cho slot.

### Bài 41. Vì sao restart_lsn có thể đứng yên dù consumer đã xác nhận tiến độ?

**Đáp án:** Transaction chưa commit hoặc decoding state có thể vẫn cần WAL cũ hơn.

### Bài 42. Archive WAL thành công có làm slot tự tiến không?

**Đáp án:** Không. Consumer feedback/decoding progress mới advance slot.

### Bài 43. Có nên xóa WAL thủ công để giải phóng disk?

**Đáp án:** Không. PostgreSQL quản lý WAL lifecycle; xóa thủ công có thể phá recovery/replication.

### Bài 44. Có nên drop inactive slot ngay?

**Đáp án:** Không. Xác minh owner và consumer lifecycle trước.

### Bài 45. pg_replication_slot_advance() làm gì?

**Đáp án:** Advance slot tới LSN chỉ định, bỏ qua changes trước vị trí đó theo semantics của slot.

### Bài 46. Advance slot có rủi ro gì?

**Đáp án:** Consumer có thể mất khả năng nhận changes đã bị bỏ qua và cần resync.

### Bài 47. peek_changes khác get_changes thế nào?

**Đáp án:** Peek đọc mà không advance; get consumes changes và advance slot, với output plugins phù hợp.

### Bài 48. Native logical replication có replicate DDL tự động không?

**Đáp án:** Không. Schema changes thường cần migration riêng trên subscriber.

### Bài 49. Sequence values có được replicate như table rows không?

**Đáp án:** Không. Cần đồng bộ sequence state riêng theo cutover plan.

### Bài 50. Logical slot có tự tồn tại sau failover không?

**Đáp án:** Không nên giả định. Cần cơ chế failover slot phù hợp version/topology hoặc resync plan.

### Bài 51. WAL generation rate dùng để làm gì?

**Đáp án:** Ước lượng tốc độ tăng WAL và thời gian còn lại trước khi disk đầy.

### Bài 52. Vì sao phải xem WAL directory disk usage ngoài slot span?

**Đáp án:** Disk còn chứa WAL do các slots khác, archive backlog và workload/checkpoint behavior.

### Bài 53. Slot active có đảm bảo tiến độ tăng?

**Đáp án:** Không. Connection có thể active nhưng consumer không acknowledge hoặc bị kẹt.

### Bài 54. Subscription có worker nghĩa mọi table đã sync?

**Đáp án:** Không. Kiểm tra pg_subscription_rel từng table.

### Bài 55. xmin retention ảnh hưởng gì?

**Đáp án:** Có thể ngăn VACUUM reclaim tuple versions và làm bloat tăng.

### Bài 56. catalog_xmin retention ảnh hưởng gì?

**Đáp án:** Có thể giữ catalog rows lâu hơn và tạo catalog cleanup pressure.

### Bài 57. Nếu slot lost, tăng max_slot_wal_keep_size có khôi phục WAL cũ không?

**Đáp án:** Không. WAL đã recycle không thể được tái tạo từ setting mới.

### Bài 58. Khi slot lost cần làm gì?

**Đáp án:** Recreate slot và resnapshot/resync consumer theo checkpoint đã xác minh.

### Bài 59. Alert nào quan trọng nhất cho slot?

**Đáp án:** Kết hợp inactive duration, restart_lsn stagnation, safe_wal_size/wal_status, disk free và consumer progress.

### Bài 60. Lập checklist điều tra logical slot giữ WAL tăng

**Đáp án gợi ý:**

1. Xác định slot, database, plugin, owner và consumer.
2. Đọc active/active_pid và ghép với pg_stat_activity.
3. So sánh current WAL LSN, restart_lsn và confirmed_flush_lsn.
4. Ước lượng WAL span, xem safe_wal_size/wal_status nếu có.
5. Kiểm tra disk free và WAL generation rate.
6. Trên subscriber/connector, xem received LSN, worker state, errors và downstream persistence.
7. Kiểm tra pg_subscription_rel và replication origin nếu dùng native subscription.
8. Tìm transaction dài và xmin/catalog_xmin horizon.
9. Chọn khôi phục consumer, xử lý transaction, drop orphan slot hoặc resync nếu slot lost.
10. Xác minh LSN tiến, WAL/disk ổn định và dữ liệu downstream nhất quán.

## 31. Checklist production

| Kiểm tra | Điều cần bảo đảm |
| --- | --- |
| wal_level | logical trên publisher |
| max_replication_slots | Đủ cho subscriptions và CDC |
| max_wal_senders | Tính cả logical và physical consumers |
| Slot owner | Có service/team chịu trách nhiệm |
| Slot naming | Dễ nhận diện database và consumer |
| Slot inventory | Có database/plugin/type |
| active / active_pid | Được theo dõi |
| restart_lsn | Có trend và stagnation alert |
| confirmed_flush_lsn | Được theo dõi |
| xmin | Có age alert |
| catalog_xmin | Có age alert |
| WAL span | Được ước lượng theo slot |
| pg_wal disk | Có free-space alert |
| WAL generation rate | Có baseline |
| max_slot_wal_keep_size | Có policy và capacity rationale |
| wal_status/safe_wal_size | Theo dõi khi version hỗ trợ |
| Consumer health | Có heartbeat/progress |
| pg_stat_replication | Sender progress được quan sát |
| pg_stat_subscription | Receiver/apply progress được quan sát |
| pg_subscription_rel | Initial sync theo table được theo dõi |
| Replication origin | Có checkpoint visibility |
| Apply errors | Có alert và logs |
| Decoding spill | Được theo dõi nếu version hỗ trợ |
| Long transactions | Có cảnh báo trên publisher |
| Archive backlog | Được theo dõi riêng |
| Slot invalidation | Có resync runbook |
| Drop/advance slot | Có owner approval và checkpoint |
| Failover slots | Có design theo version/topology |
| DDL/schema changes | Có migration process cho subscriber |
| Sequence state | Có cutover procedure |
| Restore/resync drill | Được thử định kỳ |
| Downstream consistency | Có reconciliation checks |
| Metrics retention | Có time series và reset context |

## 32. Tổng kết

Logical replication slot là cơ chế giữ trạng thái decoding và WAL cần thiết cho một logical consumer. Nó cho phép subscriber/CDC tiếp tục sau gián đoạn, nhưng consumer không tiến triển có thể giữ WAL và transaction/catalog horizons lâu hơn dự kiến.

Những nguyên tắc quan trọng:

1. **Slot là checkpoint của một consumer.** Dùng slot riêng cho từng consumer độc lập.
2. **restart_lsn và confirmed_flush_lsn trả lời hai câu hỏi khác nhau.** Theo dõi cả hai.
3. **xmin và catalog_xmin giữ tuple/catalog horizons.** WAL retention và vacuum retention là hai tác động riêng.
4. **Slot inactive vẫn có thể giữ WAL.** Kiểm tra owner, active state và LSN trend.
5. **max_slot_wal_keep_size bảo vệ storage nhưng có thể làm slot lost.** Cần resync plan.
6. **max_wal_size không phải hard cap cho slot retention.** Không dùng nó để xử lý slot kẹt.
7. **Archive WAL không làm slot tự advance.** Consumer phải xác nhận progress.
8. **Long-running transactions có thể giữ restart_lsn.** Điều tra publisher transaction age khi confirmed progress tiến mà restart position đứng yên.
9. **Subscriber progress có nhiều lớp.** Xem receive, apply, table sync và replication origin.
10. **Initial table copy cũng cần monitoring.** Subscription có thể chạy trong khi một số tables chưa ready.
11. **Logical decoding spill khác WAL retention.** Theo dõi memory/disk decoding và WAL riêng.
12. **Slot mất WAL không thể tự phục hồi.** Tạo slot mới và resnapshot/resync theo checkpoint an toàn.
13. **Không drop hoặc advance slot tùy tiện.** Đây là thao tác có thể làm mất changes downstream.
14. **Failover slot continuity phụ thuộc version/topology.** Thiết kế và diễn tập trước.
15. **Alert phải kết hợp slot progress và disk headroom.** Phát hiện sớm trước khi WAL directory gây sự cố.

Mô hình điều tra:

```text
WAL directory tăng?
        |
        v
Slot nào giữ restart_lsn cũ?
        |
        v
Slot active?
   +----+----+
   |         |
  Có        Không
   |         |
   v         v
Consumer   Consumer bị dừng,
có tiến?   orphan hay outage?
   |         |
   +----+----+
        |
        v
confirmed_flush_lsn có tiến?
        |
        v
restart_lsn vẫn đứng?
        |
        v
Kiểm tra transaction dài,
xmin/catalog_xmin và decoding
        |
        v
Khôi phục consumer hoặc resync
        |
        v
Xác minh WAL, disk, apply và
downstream consistency
```

**Câu hỏi review cuối cùng:** “Nếu CDC connector ngừng hoạt động trong bốn giờ, chúng ta có biết slot nào đang giữ WAL, còn bao nhiêu disk headroom và consumer đã xác nhận đến LSN nào không? Nếu slot bị lost vì retention cap, chúng ta có checkpoint và quy trình resnapshot để khôi phục downstream mà không tạo gap hoặc duplicate ngoài dự kiến không?” Một hệ thống logical replication an toàn phải trả lời được những câu hỏi đó bằng slot metadata, subscriber progress, disk metrics và một resync drill đã thực hiện.

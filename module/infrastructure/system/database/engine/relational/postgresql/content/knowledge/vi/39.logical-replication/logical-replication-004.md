# Đồng bộ dữ liệu ban đầu và quá trình áp dụng thay đổi trong PostgreSQL Logical Replication

PostgreSQL logical replication chuyển các thay đổi dữ liệu từ một **publisher** sang một hoặc nhiều **subscriber**. Khi tạo subscription mới, PostgreSQL thường phải làm hai việc:

1. **Đồng bộ dữ liệu ban đầu (initial table synchronization):** đưa những rows đã tồn tại trên publisher vào các bảng tương ứng trên subscriber.
2. **Áp dụng thay đổi liên tục (change apply):** chuyển và áp dụng các transaction phát sinh sau đó để subscriber tiếp tục theo kịp publisher.

Hai giai đoạn này phải phối hợp với nhau. Nếu chỉ COPY dữ liệu cũ rồi mới bắt đầu nhận thay đổi, các transaction xảy ra trong lúc COPY có thể bị bỏ sót. Nếu vừa COPY vừa apply cùng một thay đổi mà không có cơ chế phối hợp, dữ liệu có thể bị lặp hoặc xung đột.

Logical replication giải quyết bài toán bằng snapshot, replication slots, table synchronization workers, LSN và apply worker. Bài **“Đồng bộ dữ liệu ban đầu và quá trình áp dụng thay đổi”**, thuộc chương **Sao chép logic** của module **Database Engine Relational PostgreSQL**, trình bày cách các thành phần phối hợp, cách cấu hình subscription, theo dõi trạng thái, xử lý lỗi và chuyển đổi ứng dụng sang subscriber.

> **Cách hình dung:** initial synchronization sao chép trạng thái đã có tại một snapshot; trong khi đó PostgreSQL giữ và phát lại những thay đổi phát sinh quanh thời gian sao chép. Khi từng bảng bắt kịp luồng apply chính, bảng chuyển sang trạng thái replication bình thường.

---

## 1. Publisher và subscriber

Logical replication có hai vai trò:

- **Publisher:** database xuất bản thay đổi thông qua một hoặc nhiều publications.
- **Subscriber:** database đăng ký publication thông qua subscription và áp dụng những thay đổi nhận được.

~~~text
Ứng dụng ghi dữ liệu
        |
        v
    Publisher
        |
        | WAL logical decoding
        v
   Publication stream
        |
        | network / replication protocol
        v
    Subscriber
        |
        v
    Apply worker
        |
        v
  Bảng subscriber
~~~

Publication xác định những bảng và loại thao tác được công bố. Subscription lưu kết nối tới publisher, publication names, replication slot và các tùy chọn vận hành.

Logical replication là cơ chế một chiều theo cấu hình publisher/subscriber. Nó không tự tạo thành hệ thống multi-master.

## 2. Publication và subscription

Tạo publication trên publisher:

~~~sql
CREATE PUBLICATION app_publication
FOR TABLE public.customers, public.orders;
~~~

Tạo subscription trên subscriber:

~~~sql
CREATE SUBSCRIPTION app_subscription
CONNECTION 'host=publisher.example port=5432 dbname=appdb user=repl_user'
PUBLICATION app_publication;
~~~

Khi subscription được bật và tùy chọn `copy_data` giữ giá trị mặc định, PostgreSQL bắt đầu initial synchronization cho những bảng cần đồng bộ, sau đó tiếp tục apply thay đổi.

Ví dụ là cấu hình minh họa. Hãy dùng hostname, database, role, TLS và secret handling phù hợp môi trường thực tế.

### 2.1. Các điều kiện nền tảng

Trên publisher thường cần:

- `wal_level = logical`.
- Đủ `max_replication_slots`.
- Đủ `max_wal_senders`.
- Publication chứa đúng các bảng cần đồng bộ.
- Role kết nối có quyền replication và quyền đọc dữ liệu cần copy.
- `pg_hba.conf` cho phép kết nối replication từ subscriber.

Trên subscriber cần:

- Database và các bảng đích đã tồn tại.
- Schema tương thích.
- Quyền tạo subscription và ghi vào bảng đích.
- Đủ logical replication workers.
- Kết nối ổn định tới publisher.

Một số tham số cần restart để có hiệu lực; kiểm tra context của setting trước khi thay đổi.

## 3. Initial synchronization là gì?

Initial synchronization là quá trình sao chép dữ liệu đã tồn tại trên publisher tại thời điểm snapshot được thiết lập.

Ví dụ bảng publisher có 10 triệu rows khi subscription được tạo. Subscriber cần nhận 10 triệu rows này trước khi có thể được xem là đã đồng bộ đầy đủ.

~~~text
Publisher table tại snapshot S
       |
       | COPY dữ liệu đã có
       v
Subscriber table
~~~

Initial synchronization không chỉ là một câu lệnh COPY độc lập. PostgreSQL còn phải xử lý các thay đổi phát sinh trong khi COPY chạy để subscriber không bị bỏ sót dữ liệu.

## 4. Vì sao cần snapshot?

Giả sử initial copy bắt đầu lúc 10:00 và kết thúc lúc 10:20. Trong khoảng đó publisher vẫn nhận INSERT, UPDATE và DELETE.

Nếu chỉ copy snapshot tại 10:00 mà không giữ các thay đổi sau snapshot, subscriber sẽ thiếu những transaction phát sinh trong 20 phút.

Nếu copy lại dữ liệu sau mỗi thay đổi mà không có ranh giới rõ ràng, có thể xuất hiện duplicate rows hoặc áp dụng sai thứ tự.

Snapshot cung cấp một góc nhìn nhất quán để COPY. WAL logical stream ghi nhận các thay đổi sau ranh giới đó. PostgreSQL phối hợp hai nguồn để tạo trạng thái liên tục.

## 5. Luồng initial table synchronization

Ở mức khái niệm, một bảng được đồng bộ theo các bước:

1. Subscriber nhận biết bảng cần initial sync.
2. PostgreSQL tạo table synchronization worker.
3. Worker lấy snapshot nhất quán từ publisher.
4. Worker COPY dữ liệu snapshot vào bảng subscriber.
5. Các thay đổi phát sinh sau snapshot được giữ trong luồng WAL/replication slot phù hợp.
6. Worker áp dụng phần thay đổi còn thiếu để bắt kịp apply stream chính.
7. Khi bảng đã đồng bộ tới điểm chuyển giao an toàn, trạng thái bảng trở thành ready.
8. Apply worker chính tiếp tục xử lý thay đổi mới cho bảng đó.

~~~text
Publisher snapshot
       |
       v
Table sync worker
       |
       +------ COPY snapshot rows ------> Subscriber table
       |
       +------ Stream changes after snapshot
                         |
                         v
                 Catch-up / apply
                         |
                         v
                 Table state = ready
                         |
                         v
                 Main apply worker
~~~

PostgreSQL quản lý các LSN, replication origins và trạng thái nội bộ để không tạo khoảng trống giữa COPY và streaming apply.

## 6. Table synchronization worker

Một subscription có apply worker chính. Trong initial sync, PostgreSQL có thể khởi chạy thêm table synchronization workers để đồng bộ từng bảng.

Các worker này:

- Kết nối tới publisher.
- Lấy snapshot và COPY dữ liệu của bảng.
- Theo dõi phần WAL changes liên quan đến khoảng snapshot/COPY.
- Bắt kịp luồng apply.
- Bàn giao bảng cho apply worker chính.

Mỗi table sync worker xử lý một bảng trong giai đoạn initial synchronization. Số worker song song bị giới hạn bởi cấu hình subscription và tổng worker capacity của server.

### 6.1. Initial sync có thể diễn ra song song

Nếu publication có nhiều bảng, PostgreSQL có thể đồng bộ nhiều bảng cùng lúc. Điều này giảm tổng thời gian với cluster có đủ CPU, network, disk và worker capacity.

Parallel table sync cũng làm tăng:

- Số kết nối tới publisher.
- Số replication slots tạm thời trong giai đoạn sync.
- Network throughput.
- Disk writes và WAL activity trên subscriber.
- CPU cho COPY, decode và apply.

Không tăng worker chỉ dựa trên số bảng. Đo tài nguyên và tốc độ catch-up thực tế.

## 7. Snapshot và thay đổi đồng thời

Ví dụ bảng `orders` đang được COPY:

| Thời điểm | Publisher | Subscriber |
|---|---|---|
| T0 | Snapshot được thiết lập | Chưa có dữ liệu ban đầu |
| T1 | COPY đang chạy | Đang nhận rows từ snapshot |
| T2 | Transaction INSERT order mới commit | Thay đổi được giữ trong luồng đồng bộ |
| T3 | Transaction UPDATE một order commit | UPDATE chờ được apply theo stream |
| T4 | COPY hoàn tất | Subscriber apply phần thay đổi còn thiếu |
| T5 | Bảng bắt kịp | Apply worker chính tiếp tục đồng bộ |

Nếu không có cơ chế giữ và replay thay đổi trong khoảng COPY, subscriber có thể kết thúc initial sync với trạng thái cũ hơn publisher.

## 8. Replication slot trong logical replication

Subscription thường sử dụng một **logical replication slot** trên publisher để giữ WAL cần cho subscriber.

Slot theo dõi tiến độ consumer. Nếu subscriber ngắt kết nối, publisher vẫn giữ WAL mà slot còn cần, trong giới hạn retention policy.

Điều này giúp subscriber reconnect mà không phải bắt đầu lại toàn bộ replication, miễn là WAL cần thiết vẫn còn.

### 8.1. Permanent slot và temporary table sync slots

Trong quá trình initial sync, PostgreSQL có thể sử dụng các temporary synchronization slots cho từng bảng đang copy, ngoài slot chính của subscription.

Các slot tạm phục vụ việc giữ WAL trong khoảng snapshot/COPY/catch-up. Khi bảng chuyển sang trạng thái ready, slot tạm được dọn theo lifecycle nội bộ.

Không tự drop các slot có tên nội bộ trong lúc initial sync đang chạy. Hãy để PostgreSQL quản lý chúng.

## 9. Logical slot giữ WAL như thế nào?

Trên publisher, xem:

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
WHERE slot_type = 'logical';
~~~

Các cột có thể khác nhau theo PostgreSQL version. `restart_lsn` cho biết WAL cũ nhất slot có thể còn cần; `confirmed_flush_lsn` thể hiện tiến độ đã được consumer xác nhận theo logical slot protocol.

Nếu subscriber dừng lâu, slot có thể giữ nhiều WAL và làm `pg_wal` tăng. Đây là một phần quan trọng của vận hành logical replication.

## 10. Change apply là gì?

Sau khi dữ liệu ban đầu được đồng bộ, subscriber nhận các logical changes từ publisher và apply chúng vào bảng đích.

Những thao tác thường được publication phát:

- INSERT.
- UPDATE.
- DELETE.
- TRUNCATE.

Tập thao tác phụ thuộc publication configuration. Mặc định publication thông thường bao gồm insert, update, delete và truncate; có thể chọn tập nhỏ hơn khi tạo publication.

Apply worker nhận transaction changes và thực hiện chúng trên subscriber theo thứ tự commit được gửi từ publisher trong luồng subscription.

## 11. Apply worker chính

Apply worker chính duy trì subscription sau initial sync.

Nhiệm vụ gồm:

- Nhận logical replication stream.
- Giải mã protocol messages ở phía subscriber.
- Áp dụng row changes vào bảng subscriber.
- Commit transaction tương ứng.
- Cập nhật replication origin/progress.
- Xử lý table membership và trạng thái subscription.

Nếu một transaction apply thất bại, transaction đó không được coi là đã áp dụng thành công. Cần xem log, xác định conflict hoặc lỗi quyền/schema, sửa nguyên nhân và khôi phục worker theo trạng thái subscription.

## 12. Transaction order

Logical replication giữ thứ tự commit của các transaction trong một subscription. Điều này giúp subscriber quan sát thay đổi theo thứ tự publisher commit trong luồng đó.

Tuy nhiên:

- Không có một thứ tự toàn cục giữa nhiều subscriptions độc lập.
- Không nên giả định transaction từ nhiều publishers được áp dụng theo một thứ tự nghiệp vụ chung.
- DDL không được tự động chuyển theo luồng row changes.
- Một transaction có thể cập nhật nhiều bảng; initial sync từng bảng cần hoàn tất trước khi subscriber được xem là đồng bộ toàn bộ publication.

Nếu ứng dụng phụ thuộc invariants liên bảng, hãy thiết kế cutover và validation có kiểm soát.

## 13. Trạng thái đồng bộ từng bảng

Catalog `pg_subscription_rel` theo dõi trạng thái table synchronization.

Các trạng thái thường gặp:

| State | Ý nghĩa |
|---|---|
| `i` | Initialize: bảng vừa được đăng ký để sync |
| `d` | Data copy đang diễn ra |
| `f` | Finished copy: COPY đã hoàn tất, còn giai đoạn catch-up |
| `s` | Synchronized: bảng đã đạt trạng thái đồng bộ trung gian và chờ/bàn giao |
| `r` | Ready: bảng được apply worker chính xử lý bình thường |

Các trạng thái là chi tiết triển khai PostgreSQL và có thể được bổ sung/thay đổi theo version. Dùng catalog để quan sát, không tự UPDATE các catalog rows.

### 13.1. Xem trạng thái từng bảng

Trên subscriber:

~~~sql
SELECT
    s.subname,
    sr.srrelid::regclass AS relation_name,
    sr.srsubstate,
    sr.srsublsn
FROM pg_subscription_rel AS sr
JOIN pg_subscription AS s
  ON s.oid = sr.srsubid
ORDER BY s.subname, relation_name;
~~~

`srsubstate` cho biết bảng đang ở giai đoạn nào. `srsublsn` là thông tin LSN nội bộ gắn với tiến trình đồng bộ; cách diễn giải chi tiết nên đối chiếu tài liệu của major version đang chạy.

## 14. Theo dõi subscription workers

Trên subscriber:

~~~sql
SELECT
    subname,
    pid,
    relid,
    received_lsn,
    latest_end_lsn,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_time
FROM pg_stat_subscription
ORDER BY subname, relid;
~~~

View này có thể hiển thị apply worker và table synchronization workers.

- Row có `relid` NULL thường là apply worker chính.
- Row có `relid` là một bảng thường đại diện worker đang đồng bộ bảng đó.
- `received_lsn` và `latest_end_lsn` giúp theo dõi tiến độ nhận stream.
- Các timestamp hỗ trợ phân biệt luồng đang hoạt động với luồng không có message mới.

Schema view có thể có thêm cột như worker type trên các version mới. Dùng lệnh mô tả schema trong psql để kiểm tra trước khi viết query phụ thuộc cột version-specific.

## 15. Theo dõi replication origin

Subscriber lưu tiến độ logical replication qua replication origins.

Có thể quan sát:

~~~sql
SELECT
    local_id,
    external_id,
    remote_lsn,
    local_lsn
FROM pg_replication_origin_status;
~~~

- `remote_lsn`: tiến độ WAL phía publisher đã được xử lý theo origin.
- `local_lsn`: vị trí WAL local tương ứng trên subscriber.

Replication origin giúp PostgreSQL theo dõi tiến độ và hỗ trợ tránh apply lại những thay đổi đã được xử lý trong các tình huống recovery/restart.

Không chỉnh sửa replication origin state thủ công để “nhảy qua” lỗi apply. Thay đổi sai có thể làm mất dữ liệu hoặc apply trùng.

## 16. Xem tiến độ trên publisher

Trên publisher, logical slot cho biết tiến độ consumer:

~~~sql
SELECT
    slot_name,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_type = 'logical';
~~~

`confirmed_flush_lsn` có thể được dùng làm tín hiệu tiến độ consumer đã xác nhận. `restart_lsn` có thể cũ hơn do decoder cần giữ WAL cho việc tiếp tục giải mã.

Khoảng cách từ current WAL position đến các LSN này là một chỉ báo gần đúng, không phải phép đo latency end-to-end duy nhất.

## 17. Tạo subscription và tùy chọn copy_data

Ví dụ:

~~~sql
CREATE SUBSCRIPTION app_subscription
CONNECTION 'host=publisher.example dbname=appdb user=repl_user'
PUBLICATION app_publication
WITH (
    copy_data = true,
    create_slot = true,
    enabled = true,
    connect = true
);
~~~

Ý nghĩa:

- `copy_data = true`: copy dữ liệu hiện có của các bảng cần sync.
- `create_slot = true`: tạo logical replication slot trên publisher.
- `enabled = true`: bật subscription để bắt đầu hoạt động.
- `connect = true`: kết nối publisher trong quá trình tạo subscription.

Đây là các defaults phổ biến của CREATE SUBSCRIPTION. Tùy chọn và hành vi cụ thể cần xác minh theo PostgreSQL version.

## 18. copy_data=false

Nếu subscriber đã được seed bằng một quy trình khác, có thể bỏ qua initial copy:

~~~sql
CREATE SUBSCRIPTION app_subscription
CONNECTION 'host=publisher.example dbname=appdb user=repl_user'
PUBLICATION app_publication
WITH (copy_data = false);
~~~

Trong trường hợp này, PostgreSQL bắt đầu nhận các thay đổi mới theo điểm khởi tạo subscription, nhưng không copy rows hiện có.

Điều kiện quan trọng: dữ liệu ban đầu trên subscriber phải tương ứng với publisher tại một ranh giới nhất quán phù hợp. Nếu subscriber rỗng hoặc thiếu rows, các UPDATE/DELETE tương lai có thể không tìm thấy row tương ứng; INSERT có thể tạo trạng thái không đầy đủ hoặc conflict.

`copy_data=false` không phải cách bỏ qua initial sync để có ngay một replica hoàn chỉnh.

## 19. Chuẩn bị subscriber đã seed sẵn

Một quy trình seed bên ngoài có thể là:

1. Dừng hoặc kiểm soát writes theo một cutover boundary.
2. Tạo snapshot/export nhất quán từ publisher.
3. Nạp snapshot vào subscriber.
4. Xác định LSN/điểm bắt đầu phù hợp cho replication.
5. Tạo subscription theo quy trình được thiết kế để bắt đầu từ điểm đó.
6. Xác minh không có gap hoặc duplicate giữa snapshot và change stream.

Đây là quy trình nâng cao. Không chỉ chạy pg_dump vào một thời điểm rồi tạo subscription sau đó mà không có cách ghi nhận WAL boundary. Nếu có khoảng trống giữa snapshot và slot start, subscriber sẽ thiếu thay đổi.

## 20. Đồng bộ bảng được thêm vào publication

Khi publication có thêm bảng, subscriber cần refresh publication:

~~~sql
ALTER SUBSCRIPTION app_subscription
REFRESH PUBLICATION;
~~~

Mặc định, các bảng mới được phát hiện có thể được initial sync nếu copy_data được bật trong refresh.

Có thể bỏ qua việc copy dữ liệu ban đầu:

~~~sql
ALTER SUBSCRIPTION app_subscription
REFRESH PUBLICATION WITH (copy_data = false);
~~~

Chỉ dùng lựa chọn này nếu dữ liệu của bảng mới đã được seed và đồng bộ nhất quán từ một quy trình khác.

### 20.1. Xóa bảng khỏi publication

Khi bảng bị loại khỏi publication và subscriber refresh membership, thay đổi tương lai của bảng đó không còn được apply qua subscription. Bảng và dữ liệu đã có trên subscriber không tự động bị DROP.

DDL và việc dọn bảng subscriber phải được xử lý riêng theo migration policy.

## 21. DDL không được tự động replicate

Logical replication truyền row changes. Nó không tự động truyền các lệnh DDL như:

- CREATE TABLE.
- ALTER TABLE.
- CREATE INDEX.
- ALTER TYPE.
- CREATE FUNCTION.
- CREATE EXTENSION.

Vì vậy schema trên subscriber phải được chuẩn bị bằng migration hoặc công cụ schema deployment riêng.

Nếu publisher thêm cột rồi bắt đầu phát row có cột đó nhưng subscriber chưa có cấu trúc tương thích, apply có thể thất bại.

### 21.1. Quy trình thay đổi schema

Một quy trình an toàn thường:

1. Thiết kế thay đổi tương thích ngược.
2. Áp dụng DDL phù hợp trên subscriber và publisher theo thứ tự đã kiểm tra.
3. Xác minh column/type compatibility.
4. Triển khai ứng dụng.
5. Theo dõi apply errors.
6. Chỉ loại bỏ cột/logic cũ khi mọi consumers đã chuyển đổi.

Không giả định logical replication tự mang migration từ publisher sang subscriber.

## 22. Yêu cầu tương thích bảng

Các bảng publisher/subscriber không nhất thiết phải giống nhau về physical layout, nhưng phải tương thích để apply row changes.

Cần kiểm tra:

- Column names và mapping.
- Data types tương thích.
- Defaults cho cột chỉ có ở subscriber.
- Constraints có thể chấp nhận cùng dữ liệu.
- Schema và object dependencies.
- Partitioning strategy nếu dùng partitioned tables.

Logical replication map columns theo tên. Subscriber có thể có extra columns nếu các cột đó có default hoặc cho phép NULL để INSERT hợp lệ; publisher và subscriber cần có những columns tương ứng theo yêu cầu của thao tác được publish.

Không dùng schema drift tùy tiện.

## 23. Replica identity cho UPDATE và DELETE

Publisher cần xác định row nào đã thay đổi khi phát UPDATE/DELETE.

Mặc định PostgreSQL dùng primary key làm replica identity. Có thể kiểm tra:

~~~sql
SELECT
    n.nspname,
    c.relname,
    c.relreplident
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema');
~~~

Nếu bảng không có primary key hoặc unique replica identity phù hợp, UPDATE/DELETE có thể không được publish theo yêu cầu.

### 23.1. REPLICA IDENTITY FULL

Có thể cấu hình:

~~~sql
ALTER TABLE public.audit_events
REPLICA IDENTITY FULL;
~~~

FULL yêu cầu PostgreSQL dùng toàn bộ row cũ làm identity. Nó có thể tăng lượng dữ liệu WAL/logical message và chi phí tìm row trên subscriber.

Ưu tiên primary key hoặc unique index phù hợp khi có thể.

## 24. Publication operations

Publication xác định thao tác nào được phát:

~~~sql
CREATE PUBLICATION insert_only_pub
FOR TABLE public.events
WITH (publish = 'insert');
~~~

Có thể chọn insert, update, delete, truncate theo nhu cầu. Nếu publication không phát một loại thao tác, subscriber sẽ không nhận loại thay đổi đó.

Ví dụ publication chỉ phát INSERT không thể dùng để giữ subscriber phản ánh UPDATE/DELETE đầy đủ của source.

## 25. Row filters và column lists

Publication có thể giới hạn rows hoặc columns được publish trên các PostgreSQL versions hỗ trợ.

Điều này có tác động đến initial copy và change apply:

- Chỉ rows thỏa row filter được copy/phát.
- Column list giới hạn các columns được gửi.
- Thay đổi filter/column list có thể yêu cầu refresh subscription và đồng bộ lại phần dữ liệu bị ảnh hưởng theo version/operation.

Nếu subscriber chỉ chứa một tập con dữ liệu, đừng so sánh row counts toàn bảng như thể hai bên phải giống hệt nhau.

## 26. TRUNCATE trong logical replication

Nếu publication phát TRUNCATE, subscriber có thể nhận thao tác truncate tương ứng.

Cần cẩn trọng với:

- Foreign key dependencies.
- Nhiều bảng liên quan.
- TRUNCATE CASCADE và semantics trên subscriber.
- Row filters, partitioned tables và publication membership.

Không cho phép TRUNCATE trên publisher nếu subscriber không thể chấp nhận tác động tương ứng.

## 27. Sequence không được đồng bộ như row data

Logical replication không tự replicate trạng thái sequence.

Rows có thể được copy/apply nhưng giá trị last_value của sequence trên subscriber không tự theo publisher. Điều này quan trọng khi subscriber chuẩn bị được promote hoặc nhận writes.

Trước cutover/failover có ghi dữ liệu, cần đồng bộ sequence values thủ công hoặc bằng migration/runbook đã kiểm chứng.

Ví dụ kiểm tra sequence:

~~~sql
SELECT
    schemaname,
    sequencename,
    last_value
FROM pg_sequences
WHERE schemaname = 'public';
~~~

Không chỉ đặt sequence bằng MAX(id) một cách máy móc: sequence có thể tăng theo bước khác 1, dùng cache, hoặc có giá trị đã cấp nhưng transaction chưa insert row. Dùng mapping sequence và quy trình setval phù hợp.

## 28. Large Objects và các object khác

Logical replication không đồng bộ mọi loại database object.

Các nội dung cần xử lý riêng gồm:

- Large Objects.
- DDL và schema definitions.
- Sequence state.
- Roles và grants cluster-wide.
- Extensions và server-side files.
- Foreign server/user mapping và một số metadata khác.

Hãy lập danh sách những gì application cần trước khi coi subscriber là bản thay thế đầy đủ.

## 29. Apply conflicts

Logical replication không tự giải quyết mọi xung đột dữ liệu.

Các tình huống thường gặp:

- Duplicate key khi INSERT vào subscriber.
- UPDATE/DELETE không tìm thấy row tương ứng.
- Unique/check/foreign key constraint violation.
- Subscriber có dữ liệu khác với publisher.
- Schema hoặc data type không tương thích.
- Trigger/function/permission gây lỗi.
- Một người dùng ghi trực tiếp vào bảng subscriber và tạo collision.

Khi apply transaction lỗi, subscriber không thể coi transaction đó là đã áp dụng. Kiểm tra log và subscription worker state, xử lý nguyên nhân rồi để worker tiếp tục theo cơ chế restart của server.

## 30. Không coi logical replication là multi-master

Nếu ứng dụng ghi đồng thời vào publisher và subscriber trên cùng các bảng được replicate, có thể tạo duplicate keys hoặc dữ liệu xung đột.

Logical replication thông thường là một chiều. Subscriber nên được bảo vệ khỏi writes ngoài replication apply, trừ khi thiết kế có quy tắc ownership/conflict resolution riêng.

Không bật hai subscriptions hai chiều rồi kỳ vọng PostgreSQL tự hợp nhất dữ liệu như hệ thống multi-master.

## 31. Apply worker và quyền trên subscriber

Apply worker cần có quyền phù hợp để ghi vào bảng đích và thực hiện thao tác replication.

Kiểm tra:

- Owner của bảng subscriber.
- Subscription owner.
- Quyền INSERT/UPDATE/DELETE/TRUNCATE.
- Role membership.
- RLS policies.
- Constraints và triggers.
- Extension/function dependencies.

Khi quyền bị thay đổi sau khi subscription hoạt động, apply có thể bắt đầu lỗi. Quyền trên publisher để COPY dữ liệu ban đầu cũng khác với quyền apply trên subscriber; kiểm tra cả hai phía.

## 32. RLS và trigger behavior

Row-Level Security và triggers trên subscriber có thể ảnh hưởng đến việc apply tùy cấu hình và loại trigger.

Apply worker có cơ chế replication session riêng. Không giả định mọi trigger nghiệp vụ thông thường trên subscriber sẽ chạy giống khi ứng dụng INSERT trực tiếp.

Nếu subscriber cần trigger hoặc RLS behavior đặc biệt, kiểm tra semantics của PostgreSQL version, trigger enable mode và quyền subscription owner trong một môi trường thử nghiệm trước.

## 33. Giới hạn worker

Các setting quan trọng gồm:

~~~sql
SHOW max_logical_replication_workers;
SHOW max_sync_workers_per_subscription;
SHOW max_worker_processes;
SHOW max_replication_slots;
SHOW max_wal_senders;
~~~

- `max_sync_workers_per_subscription`: giới hạn số table sync workers cho một subscription.
- `max_logical_replication_workers`: capacity logical replication workers trên subscriber.
- `max_worker_processes`: giới hạn tổng background worker capacity.
- `max_replication_slots`: capacity slot trên publisher.
- `max_wal_senders`: capacity WAL sender processes trên publisher.

Giá trị cần đủ cho apply workers, table sync workers, physical standbys, logical consumers và backup connections theo topology.

## 34. Initial sync có thể làm tăng tải

COPY một bảng lớn tạo I/O đọc ở publisher và I/O ghi ở subscriber. Đồng thời publisher vẫn xử lý workload và tạo WAL.

Các nguồn tải:

- Sequential scans/reads trên publisher.
- Network transfer.
- COPY inserts trên subscriber.
- WAL writes trên subscriber.
- Index maintenance và constraints.
- Table sync workers.
- Main apply worker xử lý thay đổi mới.
- Vacuum/maintenance và application queries.

Lập lịch initial sync vào thời gian phù hợp, theo dõi disk/network và đặt giới hạn concurrency.

## 35. Table sync và lock trên subscriber

Initial table synchronization phải ghi dữ liệu vào bảng đích. Trong quá trình này PostgreSQL dùng locking để bảo đảm thao tác COPY/sync không xung đột với những thay đổi không tương thích.

Điều này có thể làm các truy vấn hoặc DDL trên subscriber chờ, tùy loại thao tác và version. Không chạy schema migration hoặc ứng dụng ghi trực tiếp vào bảng đang initial sync mà chưa kiểm tra lock behavior.

Dùng `pg_locks`, `pg_stat_activity` và log để chẩn đoán waits.

## 36. Theo dõi lỗi subscription

Trên subscriber, có thể xem thống kê lỗi trên các versions hỗ trợ:

~~~sql
SELECT *
FROM pg_stat_subscription_stats;
~~~

Các trường như apply error count và sync error count giúp phát hiện lỗi apply hoặc initial sync. Tên/cấu trúc view phụ thuộc major version.

Kết hợp với PostgreSQL server logs; statistics không thay thế error details trong log.

## 37. Kiểm tra subscription state

~~~sql
SELECT
    subname,
    subenabled,
    subslotname,
    subpublications
FROM pg_subscription
ORDER BY subname;
~~~

Catalog `pg_subscription` lưu cấu hình subscription. Một số fields và quyền xem có thể khác nhau theo version.

Kiểm tra enabled state và publication names khi điều tra subscription không chạy hoặc bảng mới chưa được replicate.

## 38. Disable và enable subscription

Có thể tạm dừng subscription:

~~~sql
ALTER SUBSCRIPTION app_subscription DISABLE;
~~~

Bật lại:

~~~sql
ALTER SUBSCRIPTION app_subscription ENABLE;
~~~

Khi disable, subscriber không apply các thay đổi mới. Publisher slot có thể tiếp tục giữ WAL cho subscription, khiến WAL retention tăng.

Không để subscription disable lâu mà không giám sát slot và dung lượng publisher.

## 39. Refresh publication

Khi publication membership thay đổi, subscriber cần refresh:

~~~sql
ALTER SUBSCRIPTION app_subscription
REFRESH PUBLICATION WITH (copy_data = true);
~~~

PostgreSQL phát hiện bảng mới và có thể chạy initial sync cho các bảng đó. Những bảng đã ready thường không bị copy lại chỉ vì refresh thông thường.

Nếu bỏ copy_data, bảo đảm dữ liệu mới đã được seed theo cách nhất quán.

## 40. Tạm dừng writes để cutover

Một migration từ publisher sang subscriber thường cần một điểm cutover rõ ràng.

Một quy trình tổng quát:

1. Hoàn tất initial sync của mọi bảng.
2. Xác minh subscription không có apply errors.
3. Giảm hoặc dừng writes trên publisher.
4. Chờ subscriber apply tới LSN cuối cùng cần thiết.
5. Xác minh dữ liệu và constraints.
6. Đồng bộ sequence states và metadata không replicate.
7. Chuyển ứng dụng sang subscriber.
8. Mở writes theo kế hoạch.
9. Theo dõi ứng dụng và giữ đường rollback phù hợp.

Không chuyển writes khi còn bảng ở trạng thái initial sync hoặc apply lag chưa được kiểm soát.

## 41. Xác minh dữ liệu ban đầu

Có thể kiểm tra row counts ở hai phía:

~~~sql
SELECT count(*) FROM public.customers;
SELECT count(*) FROM public.orders;
~~~

Nhưng nếu publisher vẫn nhận writes, hai phép đếm ở hai thời điểm khác nhau có thể khác nhau dù replication đang hoạt động đúng.

Để xác minh chặt chẽ:

- Chọn một thời điểm/LSN boundary.
- Tạm dừng writes hoặc dùng quy trình snapshot nhất quán.
- Chờ subscriber apply tới boundary.
- So sánh row counts và business invariants.
- Kiểm tra các bảng quan trọng bằng key ranges/checksums/sampling.
- Xác minh các objects không replicate riêng.

Không dùng row count đơn lẻ làm bằng chứng toàn diện.

## 42. Xử lý initial sync bị lỗi

Nếu một bảng không hoàn tất sync:

1. Xem trạng thái `pg_subscription_rel`.
2. Xác định bảng đang `i`, `d`, `f` hay trạng thái khác.
3. Kiểm tra `pg_stat_subscription` để tìm table sync worker.
4. Đọc publisher và subscriber logs.
5. Kiểm tra quyền SELECT trên publisher.
6. Kiểm tra quyền/constraints/schema trên subscriber.
7. Kiểm tra network, disk space và worker capacity.
8. Sửa nguyên nhân trước khi thử lại.

Không UPDATE trực tiếp `pg_subscription_rel` để đánh dấu bảng ready.

## 43. Xử lý apply worker bị dừng

Nếu apply worker không tiến triển:

- Kiểm tra subscription enabled.
- Xem worker PID trong `pg_stat_subscription`.
- Kiểm tra log lỗi transaction đầu tiên.
- Kiểm tra subscriber locks và long-running transactions.
- Kiểm tra schema, constraints, role permissions.
- Kiểm tra publisher slot active và WAL retention.
- Kiểm tra network và publisher availability.

Sau khi sửa nguyên nhân, có thể disable/enable subscription theo runbook để yêu cầu worker khởi động lại nếu cần. Trước khi làm, xác định slot và tiến độ để tránh xóa/recreate nhầm subscription.

## 44. WAL retention trên publisher khi subscriber offline

Logical replication slot có thể giữ WAL trong khi subscriber offline.

Trên publisher:

~~~sql
SELECT
    slot_name,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
WHERE slot_type = 'logical';
~~~

Nếu subscriber dừng lâu, `restart_lsn` có thể đứng yên và `pg_wal` tăng. Nếu giới hạn slot retention bị vượt, slot có thể bị invalidated trên các versions hỗ trợ giới hạn.

Cần theo dõi archive, disk capacity và subscription availability. Không xóa WAL files thủ công.

## 45. Không drop/recreate slot để chữa lỗi apply tùy tiện

Drop logical slot có thể làm mất WAL mà subscriber cần. Recreate một slot mới tại vị trí hiện tại không tự bù lại các changes subscriber đã bỏ lỡ.

Nếu slot lost:

- Xác minh WAL archive có đầy đủ từ vị trí cần thiết không.
- Xác minh subscriber có thể tiếp tục từ archive hay không.
- Nếu không có WAL liên tục, cần reseed/recreate subscriber data theo quy trình.
- Chỉ xóa slot cũ khi hiểu rõ consumer và retention impact.

## 46. Dùng subscription copy_data=false trong migration có seed

Một cách chuyển dữ liệu có thể dùng snapshot/backup bên ngoài rồi tạo subscription không copy data. Nhưng phải có LSN boundary rõ ràng.

~~~text
Chốt snapshot + WAL boundary trên publisher
             |
             v
Seed subscriber từ snapshot
             |
             v
Bắt đầu logical stream từ boundary phù hợp
             |
             v
Apply phần thay đổi sau snapshot
             |
             v
Subscriber bắt kịp publisher
~~~

Nếu không phối hợp snapshot và slot start, có thể mất transaction ở khoảng giữa. Đây là quy trình nâng cao; kiểm thử trên môi trường staging và dùng công cụ hỗ trợ consistent logical backup/LSN khi phù hợp.

## 47. Dữ liệu ghi trực tiếp trên subscriber

Nếu subscriber nhận writes trực tiếp trong lúc đang được replicate, những rows đó có thể:

- Tạo duplicate key khi publisher INSERT cùng key.
- Bị UPDATE/DELETE từ publisher theo identity.
- Tạo constraint conflicts.
- Làm dữ liệu hai phía không còn cùng trạng thái.

Với mô hình một chiều, thường giữ subscriber không nhận writes ứng dụng cho các bảng được replicate. Nếu cần write traffic trên cả hai phía, cần thiết kế multi-master/conflict resolution riêng.

## 48. Transaction lớn và streaming

Một transaction lớn trên publisher có thể tạo lượng thay đổi lớn trước khi commit. Apply worker cần xử lý transaction đó theo replication protocol và tài nguyên subscriber.

Tác động có thể gồm:

- WAL retention tăng.
- Apply lag tăng.
- Network burst.
- Disk/WAL pressure trên subscriber.
- Transaction apply kéo dài.

Logical replication có các tùy chọn streaming in-progress transactions trên những PostgreSQL versions hỗ trợ; hành vi và cấu hình phụ thuộc version. Không mặc định một transaction lớn sẽ được apply từng row và commit độc lập.

## 49. Giám sát lag end-to-end

Không có một cột duy nhất mô tả mọi loại lag.

Kết hợp:

- Publisher current WAL LSN.
- Logical slot `restart_lsn` và `confirmed_flush_lsn`.
- Subscriber `pg_stat_subscription.latest_end_lsn`.
- Subscriber `pg_replication_origin_status.remote_lsn`.
- Timestamp send/receive.
- Trạng thái table sync.
- Filesystem và WAL retention.

LSN distance biểu thị lượng WAL ở giữa, còn timestamp thể hiện thời gian message/transaction gần nhất. Khi publisher idle, timestamp cũ không nhất thiết có nghĩa subscriber đang lag.

## 50. Tách initial sync lag và apply lag

Hai vấn đề cần chẩn đoán riêng:

| Triệu chứng | Ý nghĩa | Hướng kiểm tra |
|---|---|---|
| Bảng ở state `d` lâu | Initial COPY chưa xong | Table size, network, disk, worker |
| Bảng ở state `f` lâu | COPY xong nhưng catch-up chưa xong | WAL rate, slot, apply throughput |
| Tất cả bảng ready nhưng LSN lag | Continuous apply chậm | Apply worker, transaction volume, locks |
| Không có sync worker | Worker capacity hoặc sync đã hoàn tất/lỗi | pg_stat_subscription, logs, catalog state |
| Slot giữ WAL tăng | Consumer không xác nhận đủ nhanh | Subscriber, network, apply errors |

Đừng chỉ nhìn tổng row count; xem giai đoạn cụ thể mà bảng đang bị chậm.

## 51. Worker capacity và cấu hình

Một số setting để đánh giá:

~~~sql
SHOW max_sync_workers_per_subscription;
SHOW max_logical_replication_workers;
SHOW max_worker_processes;
~~~

Nếu có nhiều subscriptions và nhiều bảng lớn, tổng số sync workers được yêu cầu có thể vượt capacity. Worker phải chờ slot tài nguyên trước khi bắt đầu.

Tăng `max_sync_workers_per_subscription` mà không tăng/kiểm tra `max_logical_replication_workers` và `max_worker_processes` có thể không tạo thêm concurrency thực tế.

## 52. Lab: tạo publication và subscription

Trong hai PostgreSQL lab databases.

**Publisher:**

~~~sql
CREATE TABLE public.inventory (
    item_id BIGINT PRIMARY KEY,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL
);

INSERT INTO public.inventory VALUES
    (1, 'Keyboard', 20),
    (2, 'Mouse', 35);

CREATE PUBLICATION inventory_pub
FOR TABLE public.inventory;
~~~

**Subscriber:**

~~~sql
CREATE TABLE public.inventory (
    item_id BIGINT PRIMARY KEY,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL
);

CREATE SUBSCRIPTION inventory_sub
CONNECTION 'host=publisher.example dbname=appdb user=repl_user'
PUBLICATION inventory_pub;
~~~

Nếu `copy_data` giữ mặc định true, subscriber sẽ initial copy hai rows hiện có rồi tiếp tục nhận thay đổi.

## 53. Lab: quan sát initial sync

Trên subscriber, chạy trong lúc subscription khởi tạo:

~~~sql
SELECT
    s.subname,
    sr.srrelid::regclass AS table_name,
    sr.srsubstate,
    sr.srsublsn
FROM pg_subscription_rel AS sr
JOIN pg_subscription AS s
  ON s.oid = sr.srsubid;
~~~

Với bảng nhỏ, trạng thái có thể chuyển rất nhanh nên khó quan sát. Thử với một bảng lab lớn hơn và giới hạn worker phù hợp trong môi trường cô lập.

Sau khi bảng ready, kiểm tra:

~~~sql
SELECT * FROM public.inventory ORDER BY item_id;
~~~

## 54. Lab: thay đổi trong lúc initial copy

Với bảng lab đủ lớn:

1. Bắt đầu tạo subscription và theo dõi table sync state.
2. Trong lúc COPY đang chạy, thực hiện INSERT/UPDATE/DELETE trên publisher.
3. Chờ initial sync hoàn tất.
4. Kiểm tra subscriber có phản ánh những thay đổi phát sinh trong khoảng copy không.
5. So sánh trạng thái sau khi luồng apply bắt kịp.

Mục tiêu là quan sát snapshot COPY và change stream phối hợp để tránh bỏ sót thay đổi.

## 55. Lab: copy_data=false

Tạo một bảng subscriber đã được seed bằng dữ liệu nhất quán theo một quy trình riêng. Sau đó tạo subscription với `copy_data=false`.

~~~sql
CREATE SUBSCRIPTION inventory_sub
CONNECTION 'host=publisher.example dbname=appdb user=repl_user'
PUBLICATION inventory_pub
WITH (copy_data = false);
~~~

Thực hiện INSERT/UPDATE trên publisher và quan sát subscriber.

Không dùng lab này với subscriber rỗng rồi kết luận rằng copy_data=false tạo ra bản sao đầy đủ. Nó chỉ bỏ qua initial copy.

## 56. Lab: thêm bảng và refresh publication

Trên publisher:

~~~sql
CREATE TABLE public.warehouses (
    warehouse_id BIGINT PRIMARY KEY,
    warehouse_name TEXT NOT NULL
);

ALTER PUBLICATION inventory_pub
ADD TABLE public.warehouses;
~~~

Trên subscriber, tạo schema tương ứng rồi refresh:

~~~sql
CREATE TABLE public.warehouses (
    warehouse_id BIGINT PRIMARY KEY,
    warehouse_name TEXT NOT NULL
);

ALTER SUBSCRIPTION inventory_sub
REFRESH PUBLICATION WITH (copy_data = true);
~~~

Quan sát `pg_subscription_rel` để thấy bảng mới đi qua initial sync states.

## 57. Lab: theo dõi apply progress

Trên subscriber:

~~~sql
SELECT
    subname,
    pid,
    relid,
    received_lsn,
    latest_end_lsn,
    last_msg_receipt_time,
    latest_end_time
FROM pg_stat_subscription;
~~~

Trên publisher:

~~~sql
SELECT
    slot_name,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_type = 'logical';
~~~

So sánh tiến độ theo thời gian, không chỉ một mẫu đơn lẻ.

## 58. Lab: xử lý apply conflict

Trong lab riêng:

1. Seed subscriber với một row có key sẽ xung đột.
2. Thực hiện INSERT cùng key trên publisher.
3. Quan sát lỗi trong subscriber logs.
4. Xem subscription worker state.
5. Xác định row conflict và cách sửa dữ liệu.
6. Khởi động lại/để worker retry theo runbook.
7. Xác nhận transaction và các thay đổi tiếp theo được apply.

Không thực hiện thử conflict trên production subscription.

## 59. Cutover checklist

Trước khi chuyển ứng dụng sang subscriber:

- Mọi bảng publication đã ở state ready.
- Không có apply/sync errors chưa xử lý.
- Subscriber đã bắt kịp publisher tới LSN boundary đã chọn.
- Row counts và business invariants đã được đối chiếu.
- Schema/DDL và extension tương thích.
- Sequence states đã được xử lý.
- Roles, grants, RLS và application connections đã chuẩn bị.
- Writes trên publisher được dừng hoặc điều phối theo kế hoạch.
- Có kế hoạch rollback và xác định rõ chiều replication sau cutover.

Logical replication không tự động đảo chiều sau khi ứng dụng chuyển sang subscriber. Muốn subscriber trở thành publisher cần cấu hình publication/subscription mới và quy trình dữ liệu phù hợp.

## 60. Những hiểu lầm thường gặp

### 60.1. Initial sync chỉ là COPY rồi kết thúc

Sai. PostgreSQL còn phải xử lý changes phát sinh trong lúc COPY và catch up trước khi bảng ready.

### 60.2. Subscription tạo xong là mọi bảng đã đồng bộ

Sai. Các bảng có thể ở những initial sync states khác nhau.

### 60.3. copy_data=false vẫn copy rows cũ

Sai. Nó bỏ qua initial data copy; subscriber phải được seed theo cách khác.

### 60.4. DDL tự replicate

Sai. Logical replication chủ yếu chuyển row changes; DDL phải được quản lý riêng.

### 60.5. Sequence state tự đồng bộ

Sai. Sequence values không được replicate như row data.

### 60.6. Subscriber có thể ghi tùy ý

Không an toàn trong mô hình một chiều. Writes trực tiếp có thể tạo apply conflicts hoặc divergence.

### 60.7. Slot inactive nghĩa là không giữ WAL

Sai. Logical slot có thể giữ WAL khi subscriber disconnected.

### 60.8. Tăng sync workers luôn làm nhanh hơn

Không chắc. Publisher, subscriber, network, disk và worker capacity có thể trở thành bottleneck.

### 60.9. Row count bằng nhau chứng minh dữ liệu hoàn toàn giống nhau

Sai. Cần so sánh tại cùng boundary và kiểm tra keys, constraints, business invariants.

### 60.10. Một subscription có thể tự merge writes từ hai phía

Sai. Native logical replication không tự cung cấp multi-master conflict resolution.

## 61. Checklist troubleshooting

**Initial sync**

1. Subscription có enabled?
2. Publication có chứa bảng?
3. copy_data có bật?
4. Bảng đích có schema tương thích?
5. Table sync state hiện tại?
6. Sync worker có PID?
7. Publisher SELECT privileges đúng?
8. Subscriber disk/network đủ?
9. Worker capacity còn?

**Continuous apply**

10. Apply worker có hoạt động?
11. pg_stat_subscription LSN có tiến?
12. pg_replication_origin_status có tiến?
13. Publisher logical slot có active?
14. restart_lsn/confirmed_flush_lsn có tiến?
15. Có duplicate key hoặc missing row?
16. Có constraint/permission/schema errors?
17. Subscriber có writes ngoài replication?
18. Transaction lớn hoặc locks có làm chậm apply?

**Cutover**

19. Mọi bảng đã ready?
20. Subscriber đã bắt kịp boundary?
21. Sequence state đã xử lý?
22. DDL/extensions/roles đã đồng bộ?
23. Smoke tests và business invariants đạt?
24. Có rollback/failback plan?

## 62. Bài tập thực hành

### Bài 1 — Publisher

Publisher có vai trò gì?

**Gợi ý:** xuất bản row changes.

### Bài 2 — Subscriber

Subscriber làm nhiệm vụ gì?

**Gợi ý:** nhận và apply changes.

### Bài 3 — Initial sync

Initial table synchronization sao chép dữ liệu nào?

**Gợi ý:** rows tồn tại tại snapshot ban đầu.

### Bài 4 — Snapshot

Vì sao initial copy cần snapshot?

**Gợi ý:** có một góc nhìn dữ liệu nhất quán.

### Bài 5 — Concurrent changes

Vì sao phải giữ changes phát sinh trong lúc COPY?

**Gợi ý:** tránh bỏ sót transaction sau snapshot.

### Bài 6 — Table sync worker

Worker này làm gì?

**Gợi ý:** COPY bảng và catch up tới apply stream chính.

### Bài 7 — Apply worker

Apply worker chính làm gì sau initial sync?

**Gợi ý:** nhận và apply logical changes liên tục.

### Bài 8 — Table states

State d biểu thị điều gì?

**Gợi ý:** data copy đang diễn ra.

### Bài 9 — State f

State f biểu thị điều gì?

**Gợi ý:** copy xong, còn catch-up.

### Bài 10 — State r

State r biểu thị điều gì?

**Gợi ý:** bảng ready cho normal apply.

### Bài 11 — pg_subscription_rel

Catalog này theo dõi gì?

**Gợi ý:** trạng thái initial sync theo bảng.

### Bài 12 — pg_stat_subscription

View này theo dõi gì?

**Gợi ý:** apply/sync workers và LSN progress.

### Bài 13 — Replication origin

Replication origin status giúp gì?

**Gợi ý:** theo dõi remote/local LSN progress.

### Bài 14 — copy_data

Giá trị mặc định thường là gì?

**Gợi ý:** true.

### Bài 15 — copy_data=false

Khi nào có thể dùng?

**Gợi ý:** subscriber đã được seed nhất quán bên ngoài.

### Bài 16 — refresh publication

Lệnh nào cập nhật membership từ publication?

**Gợi ý:** ALTER SUBSCRIPTION ... REFRESH PUBLICATION.

### Bài 17 — DDL

Logical replication có replicate ALTER TABLE không?

**Gợi ý:** không.

### Bài 18 — Sequence

Vì sao cần xử lý sequence khi cutover?

**Gợi ý:** sequence state không tự replicate.

### Bài 19 — Replica identity

Vì sao UPDATE/DELETE cần replica identity?

**Gợi ý:** xác định row cũ ở subscriber.

### Bài 20 — REPLICA IDENTITY FULL

Trade-off chính là gì?

**Gợi ý:** dùng toàn bộ row cũ, tăng WAL/message và chi phí.

### Bài 21 — Logical slot

Slot giữ gì cho subscriber?

**Gợi ý:** WAL cần để tiếp tục logical decoding.

### Bài 22 — Slot inactive

Subscriber offline thì slot có biến mất không?

**Gợi ý:** không.

### Bài 23 — WAL retention

Vì sao subscriber offline có thể làm pg_wal tăng?

**Gợi ý:** logical slot giữ WAL chưa được consumer xác nhận.

### Bài 24 — Apply order

Các transactions trong một subscription được apply theo thứ tự nào?

**Gợi ý:** thứ tự commit của stream publisher.

### Bài 25 — Multi-master

Native logical replication có tự giải quyết conflict hai chiều không?

**Gợi ý:** không.

### Bài 26 — Conflict

Nêu ba nguyên nhân apply conflict.

**Gợi ý:** duplicate key, missing row, constraint violation.

### Bài 27 — Worker capacity

Setting nào giới hạn table sync workers per subscription?

**Gợi ý:** max_sync_workers_per_subscription.

### Bài 28 — max_logical_replication_workers

Setting này điều khiển gì?

**Gợi ý:** logical replication worker capacity.

### Bài 29 — Subscriber schema

Vì sao cần chuẩn bị DDL trên subscriber?

**Gợi ý:** DDL không tự replicate.

### Bài 30 — Column mapping

Logical replication map columns chủ yếu theo yếu tố nào?

**Gợi ý:** column names.

### Bài 31 — TRUNCATE

Publication có thể phát TRUNCATE không?

**Gợi ý:** có nếu operation được publish.

### Bài 32 — Large Objects

Large Objects có tự replicate không?

**Gợi ý:** không.

### Bài 33 — Table sync lag

State d lâu gợi ý điều gì?

**Gợi ý:** COPY chưa hoàn tất; xem table size, network, disk, workers.

### Bài 34 — Catch-up lag

State f lâu gợi ý điều gì?

**Gợi ý:** copy xong nhưng còn WAL changes phải apply.

### Bài 35 — Apply lag

Mọi bảng ready nhưng latest_end_lsn không tiến có thể do gì?

**Gợi ý:** apply worker, network, transaction, locks hoặc publisher activity.

### Bài 36 — Cutover

Vì sao cần dừng/điều phối writes trước cutover?

**Gợi ý:** tạo LSN/data boundary có thể xác minh.

### Bài 37 — Count validation

Vì sao row count hai bên có thể khác dù replication đúng?

**Gợi ý:** writes tiếp tục và query chạy ở thời điểm khác nhau.

### Bài 38 — Slot lost

Nếu logical slot mất WAL cần thiết thì sao?

**Gợi ý:** archive đầy đủ hoặc reseed/rebuild subscriber.

### Bài 39 — Disable subscription

Vì sao disable lâu có thể gây WAL retention?

**Gợi ý:** publisher slot vẫn giữ WAL cho consumer.

### Bài 40 — Migration

Một subscriber được seed bên ngoài cần điều gì để copy_data=false an toàn?

**Gợi ý:** snapshot nhất quán và WAL start boundary không có gap.

## 63. Câu hỏi thường gặp

### Initial synchronization có khóa toàn bộ database không?

Không. Nó làm việc theo bảng và dùng snapshot/COPY; lock và tác động phụ thuộc bảng, thao tác và PostgreSQL version. Kiểm tra pg_locks khi có query chờ.

### Có thể vừa ghi publisher vừa initial sync không?

Có. PostgreSQL phối hợp snapshot với change stream để không bỏ sót thay đổi trong lúc COPY.

### Một subscription có bao nhiêu table sync workers?

Tùy cấu hình worker capacity và số bảng cần sync. max_sync_workers_per_subscription giới hạn số worker đồng bộ bảng cho mỗi subscription.

### Khi nào bảng được coi là ready?

Sau khi snapshot COPY và catch-up đã hoàn tất tới điểm bàn giao an toàn; trạng thái trong pg_subscription_rel chuyển sang r.

### copy_data=false có phù hợp database subscriber mới rỗng không?

Không nếu mục tiêu là replica đầy đủ. Nó không copy rows hiện có.

### Có thể thay đổi publication trong khi subscription chạy không?

Có. Thay đổi membership trên publisher cần refresh publication ở subscriber để cập nhật bảng được replicate.

### Thêm bảng vào publication có tự copy dữ liệu không?

Khi refresh với copy_data bật, PostgreSQL có thể chạy initial table sync cho bảng mới. Nếu bỏ copy_data, phải seed dữ liệu riêng.

### DDL có được gửi qua logical replication không?

Không. DDL cần triển khai riêng và giữ schema hai bên tương thích.

### Vì sao sequence trên subscriber bị lùi?

Sequence state không được logical replication đồng bộ như row changes. Cần cập nhật sequence theo quy trình cutover.

### Subscriber apply conflict có tự chọn bên thắng không?

Không. DBA/app owner phải xử lý conflict và khôi phục apply worker.

### Logical slot có thể làm đầy disk không?

Có. Subscriber offline hoặc apply chậm có thể khiến slot giữ WAL. Cần retention limit, archive và disk monitoring.

### Có thể ghi trực tiếp vào subscriber không?

Có thể về mặt kỹ thuật nếu quyền cho phép, nhưng không an toàn trong mô hình một chiều vì có thể tạo conflict/divergence.

### pg_stat_subscription không có row thì sao?

Subscription có thể disabled, worker chưa khởi động, đang lỗi hoặc không có worker ở trạng thái đó. Kiểm tra catalog, logs và subscription enabled state.

### Làm sao biết initial sync đã hoàn tất?

Kiểm tra tất cả bảng cần replicate trong pg_subscription_rel có state r, đồng thời xác nhận apply worker hoạt động và LSN tiếp tục tiến.

### Khi nào cần rebuild subscriber?

Khi subscriber thiếu WAL cần thiết và không có archive đầy đủ để tiếp tục, hoặc dữ liệu/schema đã divergence không thể sửa an toàn bằng cách tiếp tục apply.

## 64. Tổng kết

Các câu lệnh quan sát và vận hành quan trọng:

~~~sql
-- Trên publisher: publication.
SELECT pubname, puballtables, pubinsert, pubupdate, pubdelete, pubtruncate
FROM pg_publication;

-- Trên subscriber: subscription.
SELECT subname, subenabled, subslotname, subpublications
FROM pg_subscription;

-- Trên subscriber: initial sync state theo bảng.
SELECT
    s.subname,
    sr.srrelid::regclass AS relation_name,
    sr.srsubstate,
    sr.srsublsn
FROM pg_subscription_rel AS sr
JOIN pg_subscription AS s
  ON s.oid = sr.srsubid;

-- Trên subscriber: workers và progress.
SELECT
    subname,
    pid,
    relid,
    received_lsn,
    latest_end_lsn,
    last_msg_receipt_time,
    latest_end_time
FROM pg_stat_subscription;

-- Trên subscriber: replication origin.
SELECT local_id, external_id, remote_lsn, local_lsn
FROM pg_replication_origin_status;

-- Trên publisher: logical slots.
SELECT
    slot_name,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_type = 'logical';

-- Thay đổi publication membership.
ALTER SUBSCRIPTION app_subscription REFRESH PUBLICATION;

-- Tạm dừng/bật subscription khi có runbook phù hợp.
ALTER SUBSCRIPTION app_subscription DISABLE;
ALTER SUBSCRIPTION app_subscription ENABLE;
~~~

Những nguyên tắc cần nhớ:

1. Initial synchronization copy dữ liệu hiện có tại snapshot; change apply chuyển các transaction phát sinh sau đó.
2. Snapshot và WAL stream phải phối hợp để không có khoảng trống giữa COPY và apply.
3. Table sync workers xử lý initial copy/catch-up; apply worker chính duy trì replication liên tục.
4. pg_subscription_rel theo dõi trạng thái đồng bộ từng bảng; r biểu thị ready.
5. pg_stat_subscription giúp quan sát workers và LSN progress.
6. Replication origins lưu tiến độ remote/local.
7. Logical replication slot giữ WAL cần thiết khi subscriber offline; slot có thể làm pg_wal tăng.
8. copy_data=true copy dữ liệu hiện có; copy_data=false yêu cầu subscriber đã được seed nhất quán.
9. Bảng mới trong publication cần refresh subscription và có thể chạy initial sync.
10. DDL, sequence state, Large Objects, roles và nhiều cluster objects cần quản lý riêng.
11. UPDATE/DELETE cần replica identity phù hợp.
12. Subscriber schema, types, constraints, permissions và extensions phải tương thích.
13. Apply conflicts không được PostgreSQL tự giải quyết theo quy tắc nghiệp vụ.
14. Logical replication native không phải multi-master.
15. Giám sát initial sync lag và continuous apply lag riêng.
16. Tăng worker concurrency chỉ khi publisher, subscriber, network và disk đủ capacity.
17. Cutover cần LSN boundary, dữ liệu đã catch up, sequence handling và validation.
18. Không drop slot hoặc sửa replication origin để bỏ qua lỗi khi chưa hiểu WAL continuity.
19. Nếu slot mất WAL cần thiết, cần archive đầy đủ hoặc reseed subscriber.
20. Restore/cutover tests chứng minh subscriber có thể thay thế publisher theo kế hoạch.

Sơ đồ toàn bộ vòng đời:

~~~text
Publication trên publisher
          |
          v
Create subscription
          |
          v
Tạo logical replication slot
          |
          v
Đăng ký các bảng cần đồng bộ
          |
          v
Table sync workers lấy snapshot
          |
          v
COPY dữ liệu ban đầu
          |
          v
Catch-up changes phát sinh trong lúc COPY
          |
          v
Mỗi bảng chuyển sang ready
          |
          v
Apply worker chính nhận stream liên tục
          |
          v
Monitor LSN, errors, slot và lag
          |
          v
Validation + sequence/DDL preparation
          |
          v
Cutover có kiểm soát
~~~

**Kết luận:** Đồng bộ dữ liệu ban đầu và áp dụng thay đổi là hai phần liên tục của PostgreSQL logical replication. Snapshot/COPY thiết lập trạng thái ban đầu; table synchronization workers bắt kịp những thay đổi phát sinh trong lúc copy; apply worker chính duy trì luồng transaction về sau. Vận hành đúng cần **schema tương thích, slot/WAL retention đủ, worker capacity phù hợp, giám sát trạng thái từng bảng và LSN, xử lý conflict có chủ đích, cùng cutover được xác minh**.

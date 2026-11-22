# Dữ liệu đã xóa xuất hiện lại hoặc TTL không như mong đợi

> **Chương:** Xử lý sự cố  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Phạm vi:** Chẩn đoán tombstone, TTL, timestamp, gc_grace_seconds, replica bị bỏ lỡ xóa, repair, compaction và đường đọc/ghi từ ứng dụng Java trong Apache Cassandra.

## 1. Sự cố mở đầu: đã DELETE mà API vẫn thấy dữ liệu

Đội vận hành nhận được ba báo cáo có vẻ giống nhau:

- **Báo cáo A:** Một order được DELETE hôm thứ Hai. Sau khi node Cassandra ngừng hoạt động nhiều ngày rồi quay lại, một số request lại đọc thấy order cũ.
- **Báo cáo B:** Session được INSERT với TTL 120 giây. Sau hai phút, API vẫn trả về session dù cột **state** không còn giá trị.
- **Báo cáo C:** Row bị DELETE lúc 10:00, biến mất khỏi kết quả SELECT, rồi xuất hiện lại lúc 10:03. Toàn bộ replica đều khỏe, không có repair chạy.

Không được vội kết luận cả ba đều là lỗi “Cassandra không xóa được”. Chúng có thể có **ba nguyên nhân khác biệt**:

1. **Zombie data:** Tombstone từng chặn phiên bản cũ nhưng bị loại bỏ trong compaction trước khi một replica mang dữ liệu cũ nhận được thông tin xóa.
2. **TTL theo cell:** Một số cột có TTL hết hạn, các cột khác hoặc row liveness vẫn còn; SELECT có thể tiếp tục thấy row.
3. **Ghi mới/timestamp hoặc nguồn đọc khác:** Một writer tái tạo row sau DELETE, một mutation có timestamp cao hơn tombstone, hoặc cache/materialized view/denormalized table chưa đồng bộ.

Để xử lý, phải truy được **khóa phân vùng, cột nào được xóa, mutation timestamp, TTL tại thời điểm ghi, mức nhất quán, topology RF/DC, replica bị gián đoạn và tuổi tombstone**. Chỉ nhìn một kết quả SELECT hoặc thời điểm ứng dụng ghi log “delete succeeded” là chưa đủ.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Mô tả **tombstone, gc_grace_seconds, TTL, compaction, repair** và điều kiện zombie data.
2. Phân biệt **DELETE logic**, **TTL expiration**, **tombstone purge** và **ghi đè bằng timestamp mới**.
3. Dùng CQL **TTL(column)**, **WRITETIME(column)**, metadata schema và truy vấn theo partition key để điều tra.
4. Hiểu **TTL theo cell**, bảng có **default_time_to_live**, cột không được cập nhật và các thao tác ghi làm TTL đổi.
5. Thiết kế runbook tìm nguyên nhân của dữ liệu “sống lại” mà không xóa chứng cứ hay tạo thêm tải.
6. Đọc dấu hiệu từ Cassandra node logs, repair/compaction và Java Driver.
7. Xây dựng bài test lab cho TTL, delete–reinsert, replica downtime và kết quả đọc theo CL.
8. Ra quyết định **PAUSE/STOP/RESTORE/RECONCILE** khi nguy cơ ảnh hưởng dữ liệu hoặc quyền riêng tư.

> **An toàn:** Không hạ gc_grace_seconds, chạy full repair, ép compaction, thay RF/DC, kill node hay xóa dữ liệu production để tái hiện lỗi. Những thao tác đó cần đánh giá phiên bản Cassandra, runbook, backup và change approval. Ví dụ CQL chỉ dành cho lab/staging với dữ liệu tổng hợp.

## 2. Bốn thời điểm khác nhau trong vòng đời dữ liệu

~~~mermaid
flowchart LR
    A["Ghi dữ liệu"] --> B["DELETE hoặc TTL đến hạn"]
    B --> C["Tombstone/expired cell được xét khi đọc"]
    C --> D["Replica nhận thông tin và repair"]
    D --> E["Compaction có thể purge khi đủ an toàn"]
~~~

**T1 — Ghi:** Cassandra lưu mutation cùng write timestamp, liveness information và TTL nếu có. Dữ liệu được phân phối tới replica theo partition key và replication strategy.

**T2 — Xóa logic:** Với DELETE, Cassandra ghi một **tombstone** có timestamp để các bản sao biết rằng giá trị có timestamp cũ hơn không còn hợp lệ. Với TTL, cell **hết hạn khi đến thời điểm được xác định lúc ghi**; expiration được xử lý về mặt logic trước khi file SSTable vật lý bị xóa.

**T3 — Đồng bộ replica:** Các replica có thể khác trạng thái tạm thời do node DOWN, mất mạng, CL của request hoặc ghi chưa tới đủ replica. Repair định kỳ và các cơ chế đồng bộ được hỗ trợ giúp đưa chúng tới trạng thái phù hợp.

**T4 — Purge:** Sau thời gian grace và khi compaction chứng minh điều kiện cần thiết, dữ liệu/tombstone không còn cần thiết có thể được loại khỏi SSTable. **gc_grace_seconds không phải lịch hẹn xóa file đúng giây**, và compaction không phải transaction nghiệp vụ.

### 2.1. Tombstone không phải dấu hiệu Cassandra xóa thất bại

Tombstone là một phần cơ chế đúng đắn để bảo toàn hiệu lực DELETE trên nhiều replica. Nếu một replica A nhận DELETE trong khi B đang DOWN, A cần giữ dấu xóa đủ lâu để B không mang giá trị cũ quay lại rồi lan truyền.

Tombstone cũng có giá: khi đọc nhiều cell đã xóa/expired, Cassandra có thể phải xét nhiều tombstone; SSTable count, compaction và I/O có thể khiến **read p99** tăng. Mục tiêu không phải “xóa hết tombstone ngay” mà là **giữ đúng thời gian an toàn, đồng bộ replica và quản lý khối lượng tombstone**.

### 2.2. TTL expiration không phải lập tức giải phóng dung lượng

Khi TTL hết:

- Cell không còn được coi là sống khi đánh giá dữ liệu theo thời gian.
- File SSTable có thể vẫn chứa bản ghi và metadata expiration/tombstone.
- Disk free không nhất thiết tăng ngay sau giây TTL kết thúc.
- Compaction có thể loại dữ liệu đã hết hạn sau khi đáp ứng điều kiện an toàn.
- Nhiều cell expire cùng lúc có thể tạo **tombstone pressure**, đặc biệt với table dùng TTL diện rộng hoặc TWCS.

Đừng dùng **ổ đĩa chưa giảm** như bằng chứng TTL không hoạt động; phải kiểm tra kết quả đọc và metadata TTL/timestamp.

## 3. Timestamp quyết định giá trị nào thắng

Cassandra dùng write timestamps (đơn vị microseconds trong các API/CQL liên quan) để giải quyết cạnh tranh giữa các mutation. DELETE có timestamp; update/insert về sau với timestamp cao hơn có thể **tái tạo** dữ liệu. Đây không phải zombie data do replica.

~~~text
T0: INSERT order K, state='OPEN', timestamp=100
T1: DELETE order K, timestamp=200
T2: SELECT order K -> không thấy

T3: INSERT order K, state='OPEN', timestamp=300
T4: SELECT order K -> thấy dữ liệu

Điều này phù hợp quy tắc timestamp: ghi mới 300 thắng xóa 200.
~~~

### 3.1. “DELETE chạy sau” không chắc có timestamp lớn hơn

Giả sử một ứng dụng Java tự chỉ định timestamp hoặc đồng hồ hệ thống lệch:

~~~text
Write ban đầu: timestamp=500
DELETE gửi sau: timestamp=400

Kết quả: giá trị có timestamp 500 có thể thắng tombstone 400.
~~~

Thời gian thực hiện từ góc nhìn người dùng và **write timestamp** là hai khái niệm khác nhau. Clock skew, client-generated timestamps, replay log hoặc backfill có thể khiến thứ tự mong đợi bị đảo.

**Không tự chữa bằng cách tăng timestamp lên cực lớn.** Một mutation ở tương lai có thể che các ghi hợp lệ lâu dài. Cần điều tra nguồn timestamp, đồng bộ thời gian và hợp đồng versioning; dùng conditional update/LWT khi nghiệp vụ thật sự cần compare-and-set.

### 3.2. Cùng timestamp và quy tắc hòa giải

Nếu DELETE và INSERT có **cùng timestamp**, Cassandra có quy tắc hòa giải cụ thể cho tombstone, cell và dữ liệu cùng timestamp. Không thiết kế correctness dựa trên việc hai writers cùng chọn timestamp rồi hy vọng thứ tự mạng sẽ quyết định giá trị cuối.

Đối với test và ứng dụng cần thứ tự chắc chắn, chọn request identity/version rõ ràng, không dùng timestamp làm distributed lock. Kiểm chứng version Cassandra và đặc điểm mutation nếu cần giải quyết tie cases.

### 3.3. Replay/backfill có thể vô tình tái tạo dữ liệu

Những tác nhân cần kiểm tra:

- Kafka consumer nhận lại event cũ và INSERT cùng business key.
- Scheduled backfill chạy từ nguồn đã lỗi thời.
- Job đồng bộ hai bảng denormalized ghi lại row đã bị xóa.
- Cache warmer/reconciliation có luật “thiếu row thì tạo lại”.
- HTTP client retry sau timeout với timestamp mới.
- Service ở DC khác chưa nhận delete và có writer dùng dữ liệu cũ.
- Một bản restore/sstable import chưa có kế hoạch hòa giải với trạng thái mới.

Không chỉ tìm thao tác **DELETE** trong log; phải tìm **mọi writer có thể INSERT/UPDATE lại cùng primary key** sau thời điểm xóa.

## 4. Zombie data: tombstone không còn để chặn replica cũ

Một kịch bản dễ dẫn tới “xóa rồi sống lại”:

- Keyspace có **RF = 3** trong một DC; replica A, B, C sở hữu partition K.
- C **DOWN** trước khi DELETE, nên chưa nhận tombstone.
- DELETE được xác nhận ở A và B với **LOCAL_QUORUM**.
- C tiếp tục DOWN quá lâu; không có repair thành công bao phủ partition/tombstone liên quan.
- Sau khi đủ điều kiện, compaction trên các replica giữ tombstone **loại bỏ** dấu xóa.
- C quay lại với bản giá trị cũ. Khi dữ liệu đồng bộ/đọc/repair, do không còn tombstone để chặn, giá trị cũ **có thể xuất hiện lại và được lan truyền**.

~~~mermaid
sequenceDiagram
    participant J as Java client
    participant A as Replica A
    participant B as Replica B
    participant C as Replica C (DOWN)
    J->>A: DELETE K, CL=LOCAL_QUORUM
    A->>A: Ghi tombstone
    A->>B: Chuyển mutation DELETE
    B->>B: Ghi tombstone
    B-->>J: Đủ xác nhận quorum (mô phỏng)
    Note over A,B: Tombstone được giữ trong grace window
    Note over C: C vẫn chứa dữ liệu cũ K
    Note over A,B: Sau grace + compaction đủ điều kiện, tombstone có thể bị purge
    C-->>A: C trở lại và mang phiên bản K cũ
    Note over A,C: Nếu dấu xóa đã mất, stale data có thể được hồi sinh
~~~

Sơ đồ **đơn giản hóa** coordinator và giao tiếp replica để tập trung vào ý nghĩa. Nó không mô tả chính xác mọi pha networking hoặc bảo đảm zombie sẽ xảy ra mỗi lần node DOWN. Zombie phụ thuộc việc tombstone thực sự bị purge, phạm vi repair, ghi/timestamp và read/streaming path.

### 4.1. gc_grace_seconds là cửa sổ an toàn chống zombie

**gc_grace_seconds** là thuộc tính của table, xác định khoảng grace liên quan đến việc giữ tombstone trước khi có thể được garbage-collected. Mốc **10 ngày = 864.000 giây** từng là giá trị phổ biến ở các cấu hình Cassandra; **phải đọc cấu hình thực của table**, không suy từ mặc định cho mọi phiên bản hay cluster.

Một table có gc_grace_seconds ngắn, replica thường xuyên DOWN lâu hoặc repair không đạt có nguy cơ zombie cao hơn. Nhưng ngược lại, nâng grace rất dài cũng có thể làm tích tụ tombstone, tăng disk/read cost.

**Điều cốt lõi:** không hạ grace để “dọn disk nhanh” nếu chưa bảo đảm các replica nhận xóa theo chiến lược repair/availability. Việc đặt grace phù hợp phải xét **thời gian node có thể DOWN, lịch repair, SLA khôi phục, topology, compaction/TTL và phiên bản Cassandra**.

### 4.2. Không có quy tắc “đúng gc_grace_seconds là tombstone biến mất”

Việc purge còn phụ thuộc:

- Tombstone/expired cell đã đủ tuổi chưa.
- Compaction strategy và có chạy compaction phù hợp chưa.
- SSTable overlap/older versions còn cần tombstone chặn hay không.
- Replica hiện tại có dữ liệu chưa đồng bộ hay không.
- Repair và các điều kiện bảo toàn dữ liệu theo phiên bản/chiến lược vận hành.

Vì vậy:

- **Tombstone tồn tại sau thời hạn grace** không tự động chứng minh lỗi.
- **Không thấy tombstone ở một SSTable** không chứng minh mọi replica đã được repair.
- **Chạy compaction để xóa tombstone** không phải cách khôi phục dữ liệu.
- **Đợi quá grace** khi có replica DOWN mà không sửa repair coverage có thể tăng nguy cơ.

### 4.3. Repair phải hoàn tất đúng phạm vi, đúng thời điểm

Repair không giống snapshot/backup. Anti-entropy repair giúp so sánh dữ liệu giữa replica cho token ranges tương ứng; trong môi trường có tombstone, repair được lập lịch **đủ thường xuyên so với grace window và thời gian gián đoạn** là một yếu tố ngăn stale replica trở lại sau khi dấu xóa bị mất.

Một log “repair completed” của **một table, một range hoặc một DC** không chứng minh cả cluster/all replicas có repair coverage đầy đủ. Nếu repair partial hoặc fail, ghi rõ phạm vi chưa được bảo vệ.

> **Lưu ý phiên bản:** Một số bản Cassandra và compaction strategy có cơ chế tối ưu/lựa chọn repair khác nhau. Không áp dụng mệnh đề “chạy lệnh repair bất kỳ là an toàn” mà chưa xác minh version, lựa chọn full/incremental, phạm vi DC/ranges và tình trạng replica từng bị DOWN.

## 5. TTL là thuộc tính của cell, không tự đồng nghĩa xóa cả row

### 5.1. TTL bắt đầu từ lúc ghi

Khi câu CQL ghi một cột với **USING TTL 120**, Cassandra tính expiration của dữ liệu được ghi dựa trên TTL tính bằng **giây** và cơ chế thời gian của server. Điều này khác với:

- **created_at** do ứng dụng lưu trong một cột timestamp.
- TTL của HTTP session ở Redis hoặc expiry của JWT.
- Thời điểm một job backup/compaction chạy.
- Thời điểm client nhận response thành công.

Nếu dữ liệu được ghi lúc T0 và **created_at** biểu thị T0 − 1 ngày, TTL 120 **không tự hết hạn ngay** vì created_at đã cũ. TTL không tự đọc giá trị created_at để tính expiration.

### 5.2. Mỗi cột có thể có TTL riêng

Giả sử bảng có ba cột không thuộc khóa:

~~~text
Partition key: (tenant_id, order_id)
state            : TTL 120 giây
last_activity_at : Không có TTL
amount           : Không có TTL
~~~

Sau 120 giây, **state** có thể hết hạn nhưng **last_activity_at/amount** vẫn còn. Khi SELECT theo khóa, row có thể tiếp tục hiện với **state = null**.

Khi user nói “TTL không xóa row”, cần hỏi:

1. Câu INSERT/UPDATE có ghi TTL lên **tất cả cột cần hết hạn** hay chỉ một cột?
2. Có cột khác được ghi sau đó mà **không có TTL** không?
3. Table có **default_time_to_live** không và có override trên từng mutation?
4. Có static columns/collection/UDT hoặc liveness marker ảnh hưởng kết quả không?
5. Đang dùng **SELECT***, repository mapper hay API cache? “Row còn tồn tại” được kết luận từ cái gì?

Không kết luận “Cassandra không thực thi TTL” chỉ vì một field hết hạn còn field khác chưa hết.

### 5.3. Ghi lại cột có thể thay đổi TTL

Ví dụ:

~~~text
T0: UPDATE state='ACTIVE' USING TTL 120
T0+80s: UPDATE state='ACTIVE' USING TTL 120
T0+130s: SELECT state
~~~

Lần ghi thứ hai có thể làm **state** còn sống đến thời điểm khác so với dự kiến ban đầu, vì đó là **mutation mới**. Nếu client retry write nhiều lần hoặc consumer liên tục refresh session, thời gian tồn tại có thể kéo dài.

Ngược lại, một UPDATE không mang TTL có thể ghi phiên bản cột **không còn TTL như trước** (theo cấu hình default TTL và cú pháp). Lệnh **USING TTL 0** có ý nghĩa đặc biệt trong Cassandra, thường dùng để ghi cột **không có TTL**; phải kiểm chứng hành vi khi có **default_time_to_live** và phiên bản Cassandra cụ thể.

### 5.4. TTL mặc định của bảng

Một table có thể có **default_time_to_live**. Nếu >0, những mutation không chỉ định TTL tường minh có thể nhận TTL mặc định theo ngữ nghĩa Cassandra.

Các tình huống dễ sai:

- App tưởng **USING TTL 600** luôn được dùng, nhưng một đường writer khác dựa vào **default_time_to_live** khác.
- Sau migration, table option thay đổi, những giá trị ghi **trước** và **sau** migration có thời điểm hết hạn khác nhau.
- Một service ghi **USING TTL 0** vì muốn giữ cột lâu dài, service khác vẫn ghi TTL 600.
- Repository dùng **save/upsert** toàn entity, trong khi code nghiệp vụ chỉ định TTL cho một cột trong phương thức CQL khác.
- Một UPDATE ghi lại cột thường xuyên khiến TTL của nó được refresh, nhưng những cột không được chạm tới vẫn hết hạn theo mốc cũ.

**Đừng suy TTL của row từ duy nhất table default hiện tại.** Phải xét **lịch sử mutation thực tế** và các câu CQL đã chạy.

### 5.5. Khóa chính không bị TTL xóa như một cột dữ liệu

Partition/clustering key xác định vị trí/hình dạng row. TTL không áp cho primary-key columns như một field dữ liệu có TTL riêng. Sự hiện diện của row khi query phụ thuộc liveness information và các non-key cell còn sống; ứng dụng không nên dựa vào **“TTL của primary key”**.

Nếu cần session hết hạn như một đơn vị, hãy thiết kế để **các cell được ghi cùng TTL hợp lệ**, hạn chế update không TTL sau đó, và để **expires_at** trong hợp đồng nghiệp vụ kiểm soát khả năng sử dụng ngay cả khi trạng thái lưu trữ/chính sách retention thay đổi.

## 6. Data model thử nghiệm: order và session theo khóa truy vấn

Bài học dùng keyspace lab một DC, RF=3:

~~~sql
-- Chỉ chạy trên cluster lab có ít nhất 3 replica phù hợp trong dc1.
CREATE KEYSPACE IF NOT EXISTS ttl_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

-- Lịch sử đơn hàng theo một tenant và ngày.
CREATE TABLE IF NOT EXISTS ttl_lab.orders_by_tenant_day (
    tenant_id uuid,
    order_day date,
    created_at timestamp,
    order_id uuid,
    state text,
    amount decimal,
    PRIMARY KEY ((tenant_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);

-- Một session logic theo khóa định danh.
CREATE TABLE IF NOT EXISTS ttl_lab.sessions_by_id (
    tenant_id uuid,
    session_id uuid,
    owner_token text,
    state text,
    issued_at timestamp,
    expires_at timestamp,
    PRIMARY KEY ((tenant_id, session_id))
);
~~~

**Phân tích:**

- **orders_by_tenant_day** có composite partition key **(tenant_id, order_day)**; khi xóa một order cụ thể cần đủ các thành phần của khóa chính, gồm clustering **created_at, order_id**.
- Thiết kế này phục vụ truy vấn lịch sử theo tenant/ngày, không tự cho phép truy vấn hiệu quả theo **order_id** toàn cluster. Nếu app đọc từ bảng lookup khác, xóa ở bảng này **không tự xóa** bảng kia.
- **sessions_by_id** có partition key **(tenant_id, session_id)**, mỗi session thành partition riêng. Nó thuận lợi cho test TTL và read-by-key; cần đánh giá cardinality, request rate và phù hợp workload thực.
- Không dùng **ALLOW FILTERING** để truy vấn kiểm tra rộng cả keyspace; chọn fixture có khóa biết trước.
- RF=3 và LOCAL_QUORUM chỉ hợp lệ khi lab đủ node/replica, không copy sang một container RF=1 rồi suy rằng đã kiểm chứng multi-node.

### 6.1. INSERT session với TTL

~~~sql
INSERT INTO ttl_lab.sessions_by_id (
    tenant_id, session_id, owner_token,
    state, issued_at, expires_at
) VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    'test-owner-A', 'ACTIVE',
    '2026-11-21T08:00:00Z',
    '2026-11-21T08:02:00Z'
) USING TTL 120;
~~~

Cột **expires_at** trong ví dụ là metadata nghiệp vụ được đưa vào payload; **Cassandra không tự kiểm tra expires_at để quyết định expiration**. Với dữ liệu thử nghiệm dùng timestamp lịch sử cố định, TTL vẫn được tính theo **thời điểm mutation được ghi**, không phải **issued_at**. Đừng chạy test ở ngày khác rồi mong expires_at cũ khiến row hết hạn ngay.

Nếu ứng dụng cần bảo đảm hạn tuyệt đối, phải tính TTL từ **deadline hợp lệ tại thời điểm ghi** và kiểm tra trường expires_at ở tầng nghiệp vụ để không sử dụng dữ liệu đã quá hạn. Khi retry, phải tránh kéo dài hạn ngoài hợp đồng.

### 6.2. Query quan sát TTL và timestamp

~~~sql
SELECT owner_token, state, issued_at, expires_at,
       TTL(state) AS state_ttl_left,
       WRITETIME(state) AS state_write_us
FROM ttl_lab.sessions_by_id
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND session_id = 22222222-2222-4222-8222-222222222222;
~~~

**Ý nghĩa:**

- **TTL(state)** trả thời gian sống còn lại cho cell **state** nếu nó có TTL; với cột không TTL hoặc null, kết quả có thể là **null**.
- **WRITETIME(state)** cho biết write timestamp của cell **state**, thường ở đơn vị **microseconds** trong CQL.
- Sau expiration, SELECT có thể không trả row; không phải lúc nào cũng có thể đọc TTL đã hết hạn qua API chuẩn.
- Chỉ đọc TTL của **state** chưa chứng minh TTL của **owner_token, issued_at, expires_at** giống vậy.

> **Giới hạn:** TTL()/WRITETIME() có giới hạn với một số kiểu đặc biệt như counter và các biểu diễn collection; không dùng ngầm trên mọi column type. Cần xem version/CQL type và test schema thật.

### 6.3. Ghi một cột mới không TTL

Ví dụ minh họa việc **state** hết hạn nhưng cột khác còn sống:

~~~sql
-- Câu này ghi lại owner_token và có thể tạo
-- một phiên bản cell không có TTL khi table default TTL = 0.
UPDATE ttl_lab.sessions_by_id
SET owner_token = 'test-owner-B'
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND session_id = 22222222-2222-4222-8222-222222222222;
~~~

Nếu UPDATE chạy sau INSERT và không có default TTL, **owner_token** mới có thể tồn tại sau khi **state** đã expire. Khi đọc sẽ thấy session còn một số dữ liệu, không có nghĩa TTL(state) không hoạt động. Trong production, không dùng owner_token để sửa trạng thái session mà thiếu kiểm tra business owner/authorization; đây chỉ là fixture.

### 6.4. Xóa một order với đủ khóa

~~~sql
DELETE FROM ttl_lab.orders_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-21'
  AND created_at = '2026-11-21T08:00:00Z'
  AND order_id = 33333333-3333-4333-8333-333333333333;
~~~

Không giả định **DELETE theo tenant_id** sẽ chỉ xóa một order: phạm vi DELETE phụ thuộc **partition/clustering restrictions**, ảnh hưởng dữ liệu nhiều row nếu chọn rộng hơn. Cần chuẩn bị SELECT theo khóa để ghi bằng chứng trước khi xóa. Xóa nhầm cả partition có thể tạo tombstones và ảnh hưởng availability.

### 6.5. Xóa một session

~~~sql
DELETE FROM ttl_lab.sessions_by_id
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND session_id = 22222222-2222-4222-8222-222222222222;
~~~

Đây là DELETE logic, không phải lệnh buộc compaction phải xóa SSTable ngay. Không chạy DELETE rồi **nodetool compact** như “bước bắt buộc” của nghiệp vụ.

## 7. Đọc schema metadata trước khi thay đổi giả thuyết

CQL để kiểm tra option quan trọng:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'ttl_lab';

SELECT keyspace_name, table_name,
       gc_grace_seconds, default_time_to_live, compaction
FROM system_schema.tables
WHERE keyspace_name = 'ttl_lab'
  AND table_name = 'sessions_by_id';

SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'ttl_lab'
  AND table_name = 'sessions_by_id';
~~~

**Cần đối chiếu thực tế:**

- **gc_grace_seconds** trên **đúng table** đang điều tra, không lấy từ một table bên cạnh.
- **default_time_to_live** và compaction strategy của table.
- Partition/clustering key, column type và schema agreement.
- Replication strategy/RF tại từng DC, local DC của Java Driver và CL khi đọc/ghi.
- Các schema changes gần sự cố có thực sự áp dụng trên cluster không?

**SELECT system_schema chỉ là metadata coordinator hiện thấy**, chưa chứng minh mọi node đã schema agreement. Nếu metadata trái ngược giữa nodes, phải điều tra schema/topology trước khi chạy DDL/repair.

## 8. Cây quyết định: dữ liệu đang sống ở đâu?

~~~mermaid
flowchart TD
    A["API thấy dữ liệu đã xóa"] --> B{"SELECT trực tiếp đúng table + PK còn thấy?"}
    B -->|Không| C["Kiểm tra cache, bảng denormalized, search index, projection/API mapping"]
    B -->|Có| D{"Row/cell có TTL thực tế?"}
    D -->|TTL còn dương| E["Xem write gần nhất: TTL refresh, default TTL, expiry source"]
    D -->|TTL null/không có| F["Xem column không TTL, row liveness, update mới"]
    D -->|Không đọc được do expire| G["Phân biệt row khác hoặc cache/consistency"]
    E --> H{"Có INSERT/UPDATE sau DELETE/expiry?"}
    F --> H
    H -->|Có| I["Đánh giá timestamp, retry, backfill, CDC/consumer"]
    H -->|Không rõ| J["Đối chiếu replica downtime, repair coverage, grace, compaction"]
    J --> K{"Zombie nguy cơ cao?"}
    K -->|Có| L["PAUSE purge/destructive ops; incident + reconciliation"]
    K -->|Chưa đủ bằng chứng| M["Giữ UNKNOWN, bổ sung logs/metrics/test lab"]
~~~

**Thứ tự ưu tiên:** loại trừ lỗi **đọc sai nguồn**, **TTL không phủ đủ cột**, **ghi mới hợp lệ** trước khi khẳng định zombie data. Nhiều vụ “xóa rồi hiện lại” chỉ là một API sử dụng **cache hoặc bảng thứ hai** vẫn chứa dữ liệu.

### 8.1. Kiểm tra một khóa, một bảng, một projection

Với key **(tenant_id, session_id)**, dùng cùng CQL và bind values, ghi lại:

- Keyspace/table thực của session Java.
- Node/DC và consistency level của request.
- Query statement/cột được select, kết quả **row null hay field null**.
- TTL và writetime của các cột có thể đọc được.
- Thời điểm SELECT theo UTC, sai số clock và driver request timeout.
- ID lần ghi/xóa gần nhất nếu có audit/CDC/event log.

Tránh dùng một bảng hiển thị “orders” rồi so với DELETE tại bảng “orders_by_tenant_day”; có thể thực chất là hai nguồn khác nhau. Khi có nhiều bảng denormalized, cần kiểm tra **từng bảng theo access pattern**.

### 8.2. Phân biệt “row null” với “field null”

Ví dụ kết quả:

~~~text
Case 1:
SELECT ... WHERE full primary key => 0 rows
=> Không có row hiển thị qua query này tại thời điểm/CL đó.

Case 2:
SELECT ... => 1 row, state = null, owner_token = 'A'
=> Cell state có thể expired/xóa, nhưng một phần row vẫn sống.

Case 3:
SELECT ... => 1 row, state = 'ACTIVE', TTL(state) = null
=> Cell state đang có giá trị không có TTL; kiểm tra ghi mới,
   default TTL và lịch sử mutation.

Case 4:
API trả state='ACTIVE' nhưng CQL đúng khóa không có row
=> Kiểm tra cache, read model, index, projection và request routing.
~~~

Tất cả đều là **bằng chứng theo một query cụ thể**, chưa đủ để kết luận replica ở mọi DC cùng trạng thái. Khi CL thấp hoặc cluster lỗi, hai lần đọc có thể nhận khác nhau. Kết luận về toàn hệ thống phải dựa trên topology/CL và đối soát rộng hơn.

## 9. Ma trận nguyên nhân theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm chứng |
|---|---|---|
| Row xuất hiện sau node phục hồi dài ngày | Tombstone đã bị purge, replica cũ chưa nhận xóa (**zombie**) | Node outage duration, repair coverage, gc_grace, compaction và data version |
| Row xuất hiện ngay sau DELETE trong cluster khỏe | Writer mới, retry, backfill, timestamp cao hơn | Audit/CDC/application logs, WRITETIME(cell), request ID |
| DELETE trả success nhưng query khác vẫn thấy | Đọc bảng/cache/projection khác | Đối chiếu keyspace/table/PK, cache invalidation và dual-write |
| TTL 120 giây nhưng state vẫn ACTIVE sau nhiều phút | Ghi refresh TTL, clock/time hoặc effective TTL khác | TTL(state) qua thời gian, writetime, writer logs |
| TTL(state) null dù state có giá trị | Cell không TTL hoặc TTL bị bỏ khi ghi lại | CQL lịch sử, default_time_to_live, update logic |
| State null nhưng row vẫn hiện | Cột khác/liveness không hết hạn | SELECT cột khác và TTL từng cột |
| Disk không giảm sau expiration | SSTables/tombstones chưa purge, snapshot pin | Compaction, disk free, snapshot retention |
| TTL test pass local RF1 nhưng fail cluster nhiều DC | Khác CL/DC, writer khác hoặc replication lag/replica faults | RF/DC, local DC, CL, nhiều node và mutation logs |
| Row hiển thị khác nhau giữa LOCAL_ONE và LOCAL_QUORUM | Replica lệch tạm thời, read path khác | Node health, replica placement, repair/streaming state |
| Query thấy trạng thái cũ sau tombstone purge | Zombie hoặc stale cache/projection | Cùng PK và direct SELECT, logs/reinsert check, repair/grace timeline |
| Session tự hết hạn trước dự tính | TTL ngắn/default, clock lệch, ghi dùng thời điểm trước | TTL() gần lúc ghi, expires_at và time sync |
| Session không bao giờ hết hạn | Writer không TTL, TTL 0, refresh liên tục, cell khác sống | Code và CQL thực, table options, TTL() |

**Không có một metric hoặc câu SELECT duy nhất đủ xác định mọi nguyên nhân.** Cần xây timeline của các mutation, thời gian node DOWN/UP và thay đổi schema.

## 10. Java Driver 4.x: probe đọc TTL và write timestamp

Một Java service có thể đo các thuộc tính của **một row fixture** theo khóa đầy đủ mà không cần quét bảng.

~~~java
import java.net.InetSocketAddress;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class TtlReadProbe {
    private final CqlSession session;
    private final PreparedStatement query;

    public TtlReadProbe(CqlSession session) {
        this.session = session;
        this.query = session.prepare(
            "SELECT state, owner_token, " +
            "TTL(state) AS ttl_left, " +
            "WRITETIME(state) AS write_us " +
            "FROM ttl_lab.sessions_by_id " +
            "WHERE tenant_id = ? AND session_id = ?");
    }

    public Observation read(UUID tenantId, UUID sessionId) {
        BoundStatement statement = query
            .bind(tenantId, sessionId)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);

        Row row = session.execute(statement).one();
        if (row == null) {
            return new Observation(
                false, null, null, null, null);
        }

        return new Observation(
            true,
            row.getString("state"),
            row.getString("owner_token"),
            row.isNull("ttl_left")
                ? null : row.getInt("ttl_left"),
            row.isNull("write_us")
                ? null : row.getLong("write_us"));
    }

    public static final class Observation {
        public final boolean rowReturned;
        public final String state;
        public final String owner;
        public final Integer stateTtlSeconds;
        public final Long stateWriteTimestampMicros;

        Observation(boolean rowReturned,
                String state, String owner,
                Integer stateTtlSeconds,
                Long stateWriteTimestampMicros) {
            this.rowReturned = rowReturned;
            this.state = state;
            this.owner = owner;
            this.stateTtlSeconds = stateTtlSeconds;
            this.stateWriteTimestampMicros =
                stateWriteTimestampMicros;
        }
    }

    public static void main(String[] args) {
        // Chỉ cho lab; production phải cấu hình TLS/auth và DC thật.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {
            TtlReadProbe probe = new TtlReadProbe(session);
            Observation o = probe.read(
                UUID.fromString(
                    "11111111-1111-4111-8111-111111111111"),
                UUID.fromString(
                    "22222222-2222-4222-8222-222222222222"));

            System.out.println(
                "rowReturned=" + o.rowReturned +
                ", statePresent=" + (o.state != null) +
                ", ttlSeconds=" + o.stateTtlSeconds +
                ", writeMicros=" + o.stateWriteTimestampMicros);
        }
    }
}
~~~

### 10.1. Đọc đúng kết quả

- **rowReturned = false:** query không trả row; không suy có tombstone hay hoàn toàn chưa từng tồn tại.
- **state = null:** cell không còn hiển thị hoặc chưa có; có thể vẫn còn row khác sống.
- **stateTtlSeconds > 0:** cell đang có TTL còn lại trong kết quả đọc.
- **stateTtlSeconds = null** với state có giá trị: cell không thể hiện TTL đang hoạt động. Kiểm tra mutation/option, không coi là TTL đã hết.
- **stateWriteTimestampMicros:** timestamp của cell mà query trả về; không nhất thiết là timestamp **DELETE tombstone**. CQL bình thường không phải giao diện đọc mọi lịch sử mutation.
- **TTL giảm:** chỉ chứng minh TTL của cell tại những lần đo, không chứng minh mọi cột/replica đều giống nhau.

Bài học dùng **LOCAL_QUORUM** trên lab RF=3. Nếu cluster chỉ có một node, cần cấu hình RF/CL hợp lệ và ghi giới hạn bài kiểm tra. Trong production, profile thực tế có thể khác; không thay CL khi đang điều tra mà không ghi rõ.

### 10.2. Không dùng probe để suy luận quá mức

Một SELECT không cho biết toàn bộ tombstone history trong SSTable. Muốn điều tra zombie thật sự cần **sự kiện DELETE, logs/CDC/audit, lịch repair/compaction, outage duration, topology và có thể công cụ SSTable chuyên biệt** do DBA dùng trong môi trường được cô lập.

Đừng đọc hoặc chỉnh trực tiếp SSTable trên node production chỉ vì không thấy DELETE trong CQL. Có thể cần forensic snapshot/backup trên bản sao an toàn và công cụ đúng version.

### 10.3. Java Driver lỗi đọc không tương đương TTL

Một probe có **DriverTimeoutException**, **ReadTimeoutException**, **AllNodesFailedException** hay **UnavailableException** phải trả trạng thái **ERROR/UNKNOWN**, không chuyển thành “row absent”.

~~~text
Correct:
  Query success, row == null -> ABSENT_AT_THIS_READ
  Query success, row != null -> OBSERVED_ROW
  Query timeout/failure     -> UNKNOWN_READ_RESULT

Incorrect:
  catch (Exception e) { return null; }
  => Có thể làm ứng dụng tin session đã hết hạn khi DB chưa trả lời.
~~~

Đây là điểm đặc biệt quan trọng khi session còn quyền truy cập dữ liệu nhạy cảm: một read timeout không phải bằng chứng TTL đã thu hồi quyền.

## 11. Đồng hồ, TTL deadline và retry

### 11.1. TTL không là kiểm tra thời hạn nghiệp vụ tuyệt đối

Nếu ứng dụng gửi:

~~~sql
INSERT INTO ttl_lab.sessions_by_id (
    tenant_id, session_id, owner_token,
    state, issued_at, expires_at
) VALUES (?, ?, ?, ?, ?, ?)
USING TTL ?;
~~~

thì **TTL được tính theo mutation thực**, không tự khớp với cột expires_at. Nếu retry cùng statement sau 90 giây với TTL=120, lần ghi sau có thể **kéo dài tuổi thọ cell**, không phù hợp yêu cầu “120 giây kể từ request đầu”.

Đối với deadline nghiệp vụ:

1. Chọn **expires_at** một lần ở đầu logical operation.
2. Khi cần ghi lại, tính **TTL còn lại** theo deadline và clock đáng tin cậy, không tự refresh về 120.
3. Dùng stable request ID, payload và write ordering policy.
4. Ở tầng authorization, kiểm tra **expires_at**; không dùng TTL làm cơ chế duy nhất để đảm bảo quyền truy cập hết hạn chính xác.
5. Chọn cách xử lý request tới hạn mà remaining TTL không còn dương; không “làm tròn” thành một TTL mới vô tình kéo dài quyền.
6. Ghi nhận clock skew giữa client/coordinator/replicas và time synchronization incidents.

TTL là cơ chế lưu trữ/retention hữu ích, không nên được xem như một bộ đếm thời gian tuyệt đối không chịu lỗi đồng hồ.

### 11.2. Giới hạn TTL và thời gian tương lai

Cassandra có ràng buộc biểu diễn expiration/timestamp và chính sách xử lý ngày hết hạn quá xa khác nhau theo **phiên bản và cấu hình**. Không khẳng định mọi TTL cực lớn đều hợp lệ hoặc chính xác. Trong một số phiên bản/đường nâng cấp, các giới hạn thời gian expiration lịch sử có thể gây lỗi hoặc bị điều chỉnh theo policy.

**Runbook:** nếu CQL báo invalid TTL/out-of-range/expiration overflow, phải ghi server version, thông báo nguyên văn đã được làm sạch, table options và hạn mong muốn. Không đổi sang một số TTL lớn hơn hoặc bỏ TTL để “cho qua” khi chưa xem retention/data policy.

### 11.3. Time zones trong ứng dụng Java

CQL **timestamp** biểu diễn mốc thời gian, nhưng UI/log có thể format ở múi giờ khác. Một expiry lúc 08:00Z hiển thị là 15:00 theo Asia/Ho_Chi_Minh. Lỗi chuyển đổi giờ hoặc dùng **LocalDateTime** không kèm zone có thể khiến người dùng nghĩ TTL “sớm/trễ 7 giờ”.

Khi ghi incident timeline, dùng **Instant/UTC** làm mốc thống nhất, lưu offset nếu cần hiển thị. **TTL() trả số giây còn lại**, không phụ thuộc múi giờ hiển thị; **expires_at** được lưu/format đúng cùng là chuyện riêng.

### 11.4. Đồng hồ lệch và timestamp ở tương lai

Cassandra dùng thời gian khi xử lý TTL và write timestamps. Clock skew giữa nodes, clock configuration của client và mutation với timestamp ở tương lai có thể tạo hành vi khó hiểu (ví dụ dữ liệu cũ thắng delete). Đọc **WRITETIME** của cell và so với UTC timeline để phát hiện dấu hiệu bất thường; không lấy nó làm chứng cứ duy nhất nếu history/tombstone không còn hiển thị.

Khi có clock skew nghiêm trọng: ghi bằng chứng, xử lý đồng bộ thời gian theo runbook; không đổi clock giờ tùy tiện trong một cluster đang ghi dữ liệu.

## 12. gc_grace_seconds, repair cadence và rủi ro replica bị gián đoạn

### 12.1. Ba thời lượng phải xem cùng nhau

Không chọn gc_grace_seconds chỉ dựa vào “tombstone quá nhiều” hoặc “data TTL 1 ngày”. Cần xét:

| Thời lượng | Ý nghĩa | Nếu không đo |
|---|---|---|
| **T_down_max** | Replica có thể offline/unreachable trong bao lâu trước khi được xử lý | Stale data không được chặn khi node trở lại |
| **T_repair_coverage** | Thời gian để repair bao phủ đủ các token ranges/replicas liên quan | Log repair “success” dễ đánh lừa về coverage |
| **T_grace** | Cửa sổ bảo vệ tombstone của table | Nguy cơ purge sớm hoặc giữ tombstone quá lâu |

Một trực giác vận hành: **repair coverage phải đủ thường xuyên và hoàn tất trước khi tombstone có thể bị loại**, tính thêm buffer cho outage, job failure, scheduling delay và multi-DC. Đây không phải phép so số cố định áp dụng cho mọi version hay compaction strategy.

Ví dụ cấu hình **giả định**:

~~~text
gc_grace_seconds = 864000 (10 ngày)
repair chạy mỗi 7 ngày theo lịch
node C DOWN 12 ngày, repair bỏ qua C
C trở lại sau khi tombstone đủ điều kiện purge

Nguy cơ zombie tồn tại dù lịch repair "7 ngày một lần".
~~~

Phải hỏi: repair có thật sự chạy **thành công trên các replica cần thiết**, bao phủ đúng table/range, không failed/skipped? Một lịch có tên “weekly repair” chưa bảo đảm an toàn nếu node bị DOWN suốt thời gian đó.

### 12.2. Vì sao không đặt gc_grace_seconds = 0 cho mọi bảng TTL?

Setting grace rất thấp/0 có thể làm tombstone đủ điều kiện bị purge sớm, nguy hiểm nếu replica bỏ lỡ DELETE hoặc TTL expiration chưa được phản ánh/đồng bộ đúng trong cấu hình thực tế. Một số workload/tính năng có hướng dẫn đặc biệt cho TTL + compaction strategy, nhưng chúng cần **điều kiện chặt về replica availability, immutable data, repair và deletion semantics**.

**Không copy một lời khuyên tối ưu TWCS hoặc một blog vào mọi bảng.** Production có hỗn hợp deletes, late writes, TTL, retries, node outages và multi-DC; cần phân tích chi tiết và chạy QA/version-specific trước khi thay grace.

### 12.3. Thay gc_grace không tự phục hồi dữ liệu

Ví dụ lệnh có thể tồn tại về mặt CQL:

~~~sql
-- CHỈ MINH HỌA CÚ PHÁP, KHÔNG THỰC THI TRONG INCIDENT.
ALTER TABLE ttl_lab.sessions_by_id
WITH gc_grace_seconds = 864000;
~~~

Đặt grace lớn hơn **sau khi tombstone đã bị purge** không tái tạo tombstone đó. Đặt grace nhỏ hơn không xử lý nguyên nhân writer hồi sinh row và có thể tạo thêm rủi ro.

Không coi ALTER TABLE thành công là bằng chứng mọi replica có cùng metadata ngay lập tức; phải kiểm tra schema agreement và runbook tương ứng.

### 12.4. Hinted handoff/read repair không thay lịch repair

Cassandra có cơ chế hinted handoff và một số read-repair behavior tùy version/config, nhưng **không dựa duy nhất** vào chúng để đảm bảo tất cả tombstones được mọi replica nhận trước khi purge:

- Hints có thời hạn/lifecycle và không phải bảo đảm bất biến cho outage kéo dài.
- Read repair có phạm vi đường đọc và semantics theo version; những partition không được đọc có thể không được sửa.
- Một SELECT LOCAL_QUORUM thành công không chứng minh replica thứ ba đã nhận tombstone.
- Full/incremental anti-entropy repair cần có scope và verification rõ ràng.

**Tình trạng repair phải được đánh giá bằng coverage/evidence**, không bằng giả định “Cassandra tự đồng bộ rồi”.

## 13. Compaction và tombstone: vì sao xóa không giảm disk ngay?

Cassandra ghi mutations vào memtable/SSTable; một DELETE không trực tiếp sửa mọi SSTable cũ. Trong quá trình compaction, Cassandra hợp nhất dữ liệu và xem xét tombstone/expired cells. Điều kiện purge cần tránh để bản dữ liệu cũ trong SSTable khác hoặc replica khác hồi sinh.

### 13.1. Chẩn đoán compaction đúng mục đích

Quan sát:

- **SSTable count** của table.
- Disk occupied/free, flush/compaction throughput.
- **Pending compaction tasks**, đang compaction trên node nào.
- Tombstone warnings, scanned tombstones và read p95/p99.
- Snapshot/backup hard links có giữ SSTables cũ hay không.
- Repair/streaming tasks đồng thời cạnh tranh I/O.
- Loại compaction strategy (STCS/LCS/TWCS hoặc khác) và phiên bản.

**Đừng ép major compaction chỉ để “xóa nốt tombstone” trong incident.** Major compaction có thể tốn CPU/I/O/disk, tăng p99, và không bảo đảm giải quyết mọi dạng purge/replica safety.

### 13.2. TWCS, TTL và dữ liệu đến muộn

**TimeWindowCompactionStrategy (TWCS)** thường được dùng cho dữ liệu có TTL/time-series theo cửa sổ thời gian. Nhưng nếu có **late writes, out-of-order timestamps, partition updates cũ hoặc nhiều TTL/retention policies**, cách SSTables được chia window và khi nào dữ liệu đủ điều kiện bỏ có thể khác giả định đơn giản.

Ví dụ:

~~~text
Cửa sổ 1 chứa event cũ với TTL 7 ngày.
Một backfill muộn ghi vào key/cell lịch sử.
Một DELETE/UPDATE mới có timestamp khác và vào SSTable mới.
Các SSTables thuộc nhiều window có thể có overlap/hòa giải.
~~~

Không kết luận “cứ sau 7 ngày TWCS tự xóa nguyên SSTable” nếu còn dữ liệu hoặc tombstone/overlap/replica consistency conditions cần xét. Đo disk/compaction và đọc hướng dẫn version/config đang dùng.

### 13.3. Tombstone áp lực đọc khác dữ liệu “sống lại”

| Triệu chứng | Hướng điều tra |
|---|---|
| SELECT thấy dữ liệu đã DELETE | Writer mới, stale replica/zombie, CL/cache/projection |
| SELECT không thấy dữ liệu nhưng p99 cao | Tombstone scan, SSTables, partition size, disk/compaction |
| TTL hết nhưng disk không giảm | Tombstone/expired SSTable chưa purge, snapshot retention |
| Compaction xong rồi dữ liệu xuất hiện lại | Có thể thiếu tombstone khi stale replica quay lại; cần timeline/repair |
| Ngay sau ALTER compaction, disk tăng | Công việc rewrite SSTables và headroom; không mặc nhiên rò rỉ |

Đây là các hướng điều tra, không phải chẩn đoán chắc chắn. Phải so tương quan giữa logs, node outage, read/repair path và query.

## 14. RF/DC, consistency level và dữ liệu cũ khi đọc

Giả sử keyspace có **NetworkTopologyStrategy**, RF=3 ở **dc1**. Khi đọc:

- **LOCAL_ONE** thường có thể hoàn tất với một replica local theo kế hoạch/đường đọc phù hợp. Nếu replica này chưa nhận DELETE, có thể nhìn dữ liệu khác một replica đã nhận tombstone.
- **LOCAL_QUORUM** đòi quorum local, thường **2/3** trong ví dụ. Độ tin cậy quan sát về trạng thái có khác, nhưng vẫn phải hiểu mutation timing, retry, topology và concurrent writes.
- **ALL** đòi mọi replica liên quan theo ngữ nghĩa operation và có thể giảm availability khi node DOWN; không phải cách sửa zombie/sai dữ liệu.
- **SERIAL/LOCAL_SERIAL** áp dụng cho LWT, không phải regular SELECT/DELETE thông thường trừ khi có semantics phù hợp.

**Quorum có điều kiện cần kiểm tra.** Những đảm bảo theo quorum đọc/ghi phụ thuộc RF, CL, replica tập hợp, không có concurrent writes/timestamp anomalies, cùng DC khi local và phiên bản/protocol. Nếu dùng nhiều DC, một cặp **LOCAL_QUORUM trong hai DC khác nhau** không tự được xem như cùng một quorum toàn cục.

### 14.1. Đọc ở CL cao không sửa xóa đã mất tombstone

Nếu tombstone bị purge ở các replica khỏe và node cũ đưa lại giá trị, tăng CL không thể **phát minh lại** dấu xóa đã mất. Muốn khôi phục business truth có thể cần:

- Audit trail/CDC/outbox ghi nhận yêu cầu DELETE.
- Bản backup/snapshot ở thời điểm phù hợp (dùng để forensics/recovery, không restore bừa).
- Nguồn sự thật nghiệp vụ (order status, deletion ledger).
- Reconciliation có idempotency và timestamp/version rules rõ.
- Kế hoạch cô lập/rebuild replica theo runbook khi cần.

**Repair không phân biệt một row được tạo hợp lệ hay là zombie** chỉ từ nghiệp vụ; nó chủ yếu giúp replicas hội tụ trên dữ liệu/tombstone đang có. Nếu tombstone đã bị mất, repair không thể quyết định “row này đáng lẽ bị xóa” nếu không có nguồn chứng cứ khác.

### 14.2. Không suy từ session Java local DC tới tất cả data centers

Một service chạy tại dc1 có thể dùng LOCAL_QUORUM cho cả read/write; service khác chạy dc2 có RF/CL và replica health khác. Khi báo “Cassandra lúc thấy lúc không”, ghi:

- Service instance/region và driver **local datacenter**.
- Contact points thực và coordinator được chọn.
- Regular consistency level, serial consistency nếu LWT.
- Keyspace replication tại mỗi DC.
- Node health/repair status và event timestamps.
- Cùng business key đã được hash/ẩn dữ liệu nhạy cảm.

Không di chuyển traffic sang DC khác hoặc thay CL chỉ để “kiểm tra cho biết” khi có yêu cầu data residency và risk of stale state.

## 15. Lệnh quan sát an toàn trước khi can thiệp

Dùng công cụ read-only đúng phiên bản, với quyền được cấp:

~~~bash
# Sức khỏe node, DC/rack, trạng thái DOWN/UP/JOINING.
nodetool status

# Thông tin node, tài nguyên và trạng thái cục bộ.
nodetool info

# Thread pools và pending/dropped tasks.
nodetool tpstats

# Compaction và công việc nền đang chạy.
nodetool compactionstats

# Streaming sessions và network tasks, nếu version hỗ trợ.
nodetool netstats

# Table statistics (SSTable, reads, tombstones tùy version).
nodetool tablestats ttl_lab.sessions_by_id

# Phân phối partition/row size, khi version hỗ trợ.
nodetool tablehistograms ttl_lab sessions_by_id

# Snapshot retention nếu cần phân biệt pinned SSTables.
nodetool listsnapshots
~~~

Thu thêm:

- Per-node server logs: tombstone warnings, repair failures, node DOWN/UP, compaction errors.
- Repair job logs/schedules: ranges/DC/table, thành công/partial/skipped và timestamps.
- Disk free/await/IOPS, network loss, GC/heap/native RSS, CPU.
- Java Driver/client logs: statement shape, CL, timeout/retries, DC, correlation ID và side effects.
- Audit/CDC/business event log: lần INSERT/UPDATE/DELETE cuối cùng trên logical key.
- Backup manifest/restore records nếu nghi dữ liệu bị hồi sinh và cần xác lập nguồn sự thật.

**Không chạy** nodetool repair, cleanup, compact, rebuild, decommission hoặc clearsnapshot như các lệnh “xem tình trạng”. Chúng làm thay đổi dữ liệu/tải/retention. Đặc biệt, xóa snapshot khi chưa xác nhận backup ngoài miền lỗi có thể làm mất recovery point.

### 15.1. Mẫu timeline sự cố

~~~yaml
incident:
  id: "ttl-zombie-lab-2026-11"
  table: "ttl_lab.sessions_by_id"
  key_reference: "<approved-hashed-key>"
  first_reported_utc: "<time>"
topology:
  rf_by_dc: "dc1:3"
  read_cl: "LOCAL_QUORUM"
  write_cl: "LOCAL_QUORUM"
schema:
  gc_grace_seconds: "<observed>"
  default_time_to_live: "<observed>"
  compaction: "<observed>"
timeline:
  last_known_write: "<time + logical ID>"
  delete_or_ttl_expected: "<time>"
  replica_downtime: "<duration / nodes>"
  last_successful_repair_coverage: "<scope and time>"
  compaction_period: "<time range>"
  reappearance_observed: "<time>"
diagnostics:
  ttl_and_writetime: "<observed if still visible>"
  writer_reinsert_evidence: "<found/none/not_checked>"
  cache_projection_checked: "<yes/no>"
decision:
  classification: "UNKNOWN_PENDING_EVIDENCE"
  next_action: "preserve evidence and compare sources"
~~~

Đây là mẫu báo cáo tự định nghĩa, **không phải config Cassandra hay dữ liệu incident thật**. Nếu không có một trường, ghi **NOT_MEASURED**; không bịa thời điểm repair/cause chỉ để hoàn thiện biểu mẫu.

## 16. Runbook incident: bảo toàn dữ liệu trước khi tối ưu

### 16.1. Phút 0–5: xác định nguy cơ và giữ bằng chứng

1. **Xác định mức ảnh hưởng:** dữ liệu tài chính, hồ sơ người dùng, bản ghi phải xóa theo yêu cầu pháp lý hay session lab? Với dữ liệu cần xóa vì quyền riêng tư, kích hoạt quy trình incident tương ứng.
2. **Ghi mốc UTC:** lúc xóa, TTL dự kiến hết, thời điểm tái xuất hiện, node DOWN/UP, deploy/backfill.
3. **Xác định nguồn:** API trả từ Cassandra, cache hay denormalized read model? Kiểm tra đúng keyspace/table/partition key.
4. **Ghi schema/CL:** gc_grace_seconds, default TTL, compaction, RF/DC, READ/WRITE CL.
5. **Giữ evidence:** audit/CDC/logs, request ID, trạng thái node, repair coverage, snapshot/backup manifest. Không dọn tombstone/snapshot hoặc ép compaction trước khi lấy bằng chứng.
6. **Ngăn lan truyền:** nếu writer/replay/projection tái tạo dữ liệu, cân nhắc tạm dừng riêng nguồn đó qua runbook.
7. **Không retry xóa vô hạn**, gửi mutation timestamp cực lớn hay tắt node chỉ vì một SELECT vẫn thấy dữ liệu.

### 16.2. Phút 5–15: lập giả thuyết

| Bằng chứng | Giả thuyết | Cách kiểm chứng |
|---|---|---|
| TTL(state) dương và tăng lại | Ghi refresh TTL | WRITETIME, app logs, retries |
| TTL(state) null, state vẫn còn | Cell không TTL hoặc ghi lại không TTL | default TTL, TTL 0, UPSERT |
| State null, owner còn | TTL theo cell, row còn sống | Đọc các cột khác và TTL của chúng |
| Row mới có write timestamp cao hơn DELETE | Reinsert/replay với timestamp mới | Audit/CDC/producer logs |
| Node DOWN lâu hơn grace, repair thiếu | Zombie risk | Repair ranges, outage, compaction history |
| Direct SELECT không thấy, API vẫn thấy | Cache/index/bảng khác | Route/read model/invalidation |
| Đọc khác nhau giữa DC/CL | Replica divergence hoặc writers khác | RF/DC, CL, node health |
| TTL expire nhưng disk không giảm | SSTable retention/snapshot pin | Compaction, filesystem accounting |
| DELETE báo timeout | Outcome ghi chưa xác định | Request ID, replica/logs, reconciliation |

**Giả thuyết chưa phải root cause.** Node DOWN lâu hơn grace chỉ chỉ ra điều kiện nguy cơ, chưa chứng minh tombstone đã bị purge hoặc row thực sự đã hồi sinh từ replica đó.

### 16.3. Phút 15–30: chọn nhánh xử lý

**Nhánh A — TTL do code/config:** Sửa writer và expires_at theo contract, bổ sung integration test. Không xóa toàn bộ dữ liệu production khi chưa biết phạm vi.

**Nhánh B — Writer reinsert:** Dừng hoặc điều chỉnh source replay/backfill, dùng requestId/version/idempotency, reconciliation bảng phụ. Không chỉnh gc_grace nếu nguyên nhân là mutation mới hợp lệ về timestamp.

**Nhánh C — Suspected zombie:** Báo DBA/SRE, bảo vệ evidence/backup, đối chiếu repair coverage/grace/replica history. Cần nguồn sự thật nghiệp vụ để reconcile hoặc kế hoạch recovery/cô lập stale replica theo runbook. **Không repair mù**, vì nó có thể làm replicas hội tụ trên giá trị đã sai về ngữ nghĩa.

**Nhánh D — Cache hoặc bảng khác:** Sửa invalidation/projection và xác minh retention của downstream, không ép compaction Cassandra để xóa cache.

### 16.4. STOP và ESCALATE gates

- Dữ liệu phải xóa theo chính sách mà vẫn hiển thị hoặc được tái phát tán.
- Nghi missing quorum, data inconsistency trên nhiều DC hoặc replica cũ trở lại sau outage dài.
- Repair partial/failed hoặc chưa có nguồn sự thật về delete history.
- Disk gần full, compaction/tombstone pressure làm API mất SLO.
- Một hành động đề xuất sẽ đổi RF, compaction/retention, topology hoặc mất recovery point.
- Cần khôi phục backup hoặc sửa dữ liệu diện rộng.
- Chưa thể xác định những logical keys bị ảnh hưởng.

Khi có gate, **PAUSE các hành động phá chứng cứ hoặc có nguy cơ lan truyền sai lệch**, kích hoạt owner/incident commander và xử lý có kiểm soát. Không dùng tăng timeout/đổi CL để che incident.

### 16.5. Điều kiện đóng incident

1. Có bằng chứng về **nguồn gốc** và đã sửa cơ chế gây lỗi.
2. Tập logical keys bị ảnh hưởng được xác định/reconcile theo phạm vi chấp nhận.
3. Writer/cache/projection không còn tái tạo dữ liệu ngoài hợp đồng.
4. RF/DC, repair coverage và cluster health trở lại mức chấp nhận.
5. TTL/deletion verification pass qua thời gian đủ dài để bao gồm retry/replica return nếu cần.
6. Read/write SLO, disk/GC/compaction trong ngưỡng.
7. Incident report có timeline, remediation, backup evidence và test ngăn tái diễn.

**Một SELECT trả 0 rows sau khi DELETE lại không đủ để đóng incident.**

## 17. Bốn ca chẩn đoán cụ thể

### Ca A — TTL 120 giây nhưng API còn session sau 15 phút

**Bằng chứng giả định:**

~~~text
10:00 UTC: INSERT session USING TTL 120
10:01:20 UTC: heartbeat UPDATE owner_token (không TTL)
10:03 UTC: SELECT state = null, owner_token = 'A'
10:15 UTC: API trả "session exists"
~~~

**Diễn giải:** TTL của **state** có thể đã hết đúng, nhưng **owner_token** mới được ghi không TTL nên row vẫn hiển thị. API coi “có row” là “session còn hợp lệ” nên sai business contract.

**Khắc phục:** Kiểm tra expires_at trong service và logic heartbeat; sửa cách ghi TTL từng cell, không vô tình làm sống lại row sau expiry. Bổ sung test có mixed TTL. Không ép compaction vì trong trường hợp này vẫn có cell sống hợp lệ.

### Ca B — DELETE đúng, reinsert sau ba phút

**Bằng chứng giả định:**

~~~text
10:00 UTC: DELETE order K, write timestamp = 500000000
10:03 UTC: replay consumer INSERT K, write timestamp = 600000000
10:03:01 UTC: SELECT K -> thấy row
Nodes: UP; không có node outage hoặc failed repair
~~~

**Diễn giải:** Cassandra có thể xử lý chính xác theo last-write-wins; một **ghi mới** có timestamp cao hơn DELETE. Đây không phải zombie do gc_grace.

**Khắc phục:** Dừng/điều chỉnh replay consumer, dùng deletion ledger hoặc state/version guards và idempotency, reconcile bảng denormalized. Không hạ grace, chạy major compaction hay tăng CL để giải quyết mutation mới.

### Ca C — Replica DOWN lâu, repair chưa bao phủ

**Bằng chứng giả định:**

~~~text
Ngày 1: Replica C DOWN.
Ngày 2: DELETE K thành công với LOCAL_QUORUM ở A+B.
Ngày 10: Repair job partial, ranges của K chưa hoàn tất.
Ngày 13: A/B đã compaction, sau thời gian grace.
Ngày 14: C quay lại vẫn có old K.
Ngày 15: Một số reads thấy old K.
~~~

**Diễn giải:** Timeline phù hợp **nguy cơ zombie**, nhưng cần chứng minh tombstone đã thật sự purge, old row ở C có timestamp thế nào và có writer mới hay không. Không kết luận chỉ từ việc C DOWN 14 ngày.

**Khắc phục:** Bảo toàn logs/backups, DBA đánh giá repair coverage/grace/outage và nguồn sự thật xóa; reconcile theo runbook có khả năng ngăn stale source lan truyền. Repair không thể tự biết giá trị nào “đáng lẽ đã xóa” nếu dấu xóa thực sự biến mất.

### Ca D — Cassandra không còn row, API vẫn trả document

**Bằng chứng giả định:**

~~~text
Direct CQL SELECT đúng keyspace/table/partition key: 0 rows
Cache hoặc search index: còn document cũ
API response: vẫn có document
~~~

**Diễn giải:** Không có bằng chứng row vẫn sống trong table đã đọc; cache/index hoặc bảng phụ chưa invalidation/CDC consumer bị lag. Cần tiếp tục xét CL và table coverage để xác nhận tình trạng Cassandra, nhưng không giả định vấn đề ở compaction.

**Khắc phục:** Sửa invalidation/projection, replay event đúng thứ tự/idempotency và bảo đảm downstream đáp ứng retention policy. Không chạy nodetool repair Cassandra để xóa document trong Redis/search index.

## 18. Thí nghiệm CQL lab: phân biệt TTL theo cell và reinsert

### 18.1. Thí nghiệm 1 — mọi cell có TTL

Dùng **tenant_id, session_id mới** trên table sessions_by_id; chỉ thực hiện trong staging/lab. Giả sử ghi tất cả non-key columns bằng một INSERT:

~~~sql
INSERT INTO ttl_lab.sessions_by_id (
    tenant_id, session_id, owner_token,
    state, issued_at, expires_at
) VALUES (
    44444444-4444-4444-8444-444444444444,
    55555555-5555-4555-8555-555555555555,
    'lab-owner', 'ACTIVE',
    '2026-11-21T08:00:00Z',
    '2026-11-21T08:01:00Z'
) USING TTL 8;
~~~

Ngay sau đó:

~~~sql
SELECT state, owner_token,
       TTL(state) AS ttl_state,
       TTL(owner_token) AS ttl_owner
FROM ttl_lab.sessions_by_id
WHERE tenant_id = 44444444-4444-4444-8444-444444444444
  AND session_id = 55555555-5555-4555-8555-555555555555;
~~~

Kỳ vọng các non-key cells được ghi cùng TTL 8 có thời gian sống gần nhau. Sau khi quá hạn và cho buffer phù hợp, SELECT có thể trả **0 row** nếu không có writer mới/cell thường còn sống. Không lấy việc disk space chưa giảm làm test fail.

### 18.2. Thí nghiệm 2 — cập nhật một cột không TTL

Tạo session mới TTL=8 như trên, sau đó trong cửa sổ TTL chạy:

~~~sql
UPDATE ttl_lab.sessions_by_id
SET owner_token = 'persistent-owner'
WHERE tenant_id = 44444444-4444-4444-8444-444444444444
  AND session_id = 55555555-5555-4555-8555-555555555555;
~~~

**Lưu ý:** Trong thực hành nên dùng khóa fixture mới cho mỗi test, thay vì reuse ví dụ đã expire. Giả định table **không đặt default_time_to_live**.

Sau khi state hết TTL, có thể thấy **state = null**, **owner_token = 'persistent-owner'**, row vẫn hiện. Điều này minh họa lỗi ở giả định “TTL của state xóa cả session”.

### 18.3. Thí nghiệm 3 — reinsert sau DELETE

Trên fixture mới:

~~~sql
INSERT INTO ttl_lab.sessions_by_id (
    tenant_id, session_id, owner_token, state
) VALUES (?, ?, 'first', 'ACTIVE');

DELETE FROM ttl_lab.sessions_by_id
WHERE tenant_id = ? AND session_id = ?;

INSERT INTO ttl_lab.sessions_by_id (
    tenant_id, session_id, owner_token, state
) VALUES (?, ?, 'second', 'ACTIVE');
~~~

Nếu các mutations có write timestamps ngày càng lớn, SELECT có thể thấy owner_token='second'. Đây là **tái tạo hợp lệ sau DELETE**, không cần down replica hoặc garbage collection.

Nếu bài test cần chứng minh thứ tự timestamp, dùng timestamp tường minh theo môi trường lab và kiểm tra WRITETIME; **không đưa timestamps bất thường vào production**.

### 18.4. Thí nghiệm 4 — DELETE với timestamp thấp

CQL hỗ trợ thao tác với timestamp tường minh theo cú pháp/giới hạn Cassandra đang dùng. Trong lab có thể kiểm thử ý tưởng:

~~~sql
-- Các timestamps microseconds bên dưới chỉ là giá trị LAB,
-- không gửi vào môi trường production.
INSERT INTO ttl_lab.sessions_by_id (
    tenant_id, session_id, owner_token, state
) VALUES (?, ?, 'newer', 'ACTIVE')
USING TIMESTAMP 500000;

DELETE FROM ttl_lab.sessions_by_id
USING TIMESTAMP 400000
WHERE tenant_id = ? AND session_id = ?;
~~~

Nếu mutation có cùng full PK và timestamp DELETE thấp hơn các cell đang sống, giá trị có thể vẫn hiển thị. Nguyên nhân là **write ordering**, không phải gc_grace quá ngắn. Các timestamps rất nhỏ thuộc quá khứ ở ví dụ chỉ nhằm minh họa; phải dùng fixture riêng, tránh liên hệ hệ thống thật.

### 18.5. Không chạy test hàng loạt trên một partition nóng

- Mỗi test có tenant/session key riêng; không chạy 1000 deletes cùng partition khi không cần.
- Không test bằng DROP/TRUNCATE hoặc forced compaction của table dùng chung.
- Dùng **LOCAL_QUORUM** nếu RF3/one DC khỏe; trên container RF1 phải cấu hình khác và ghi giới hạn.
- Trong thí nghiệm TTL ngắn, đo với buffer và lặp vài lần; đừng assert hết hạn đúng tuyệt đối ở millisecond.
- Nếu server/driver timeout, kết quả là **INCONCLUSIVE/ERROR**, không phải row đã expire.
- Sau test, cleanup theo ownership của keyspace lab, lưu evidence cần thiết rồi mới xóa.

## 19. Kiểm thử tích hợp Java: TTL hết hạn và cột không TTL còn sống

Mục tiêu của test là đo **ngữ nghĩa nhìn thấy qua CQL**. Test không cần ép compaction hoặc sửa SSTable để xác nhận TTL hoạt động. Dùng JUnit 5 và Java Driver 4.x, tạo session với schema **ttl_lab.sessions_by_id** có sẵn và dữ liệu lab.

### 19.1. JUnit 5: kiểm tra row hết hạn

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.InetSocketAddress;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import org.junit.jupiter.api.Test;

public class TtlSemanticsIT {
    private static CqlSession openLabSession() {
        // Sửa contact point/DC và TLS/auth theo cluster lab.
        return CqlSession.builder()
            .addContactPoint(
                new InetSocketAddress("127.0.0.1", 9042))
            .withLocalDatacenter("dc1")
            .build();
    }

    private static Row read(
            CqlSession session, PreparedStatement select,
            UUID tenantId, UUID sessionId) {
        return session.execute(
            select.bind(tenantId, sessionId)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true))
            .one();
    }

    @Test
    void allWrittenCellsExpireWithoutRefresh()
            throws Exception {
        UUID tenantId = UUID.randomUUID();
        UUID sessionId = UUID.randomUUID();
        Instant issuedAt = Instant.now();

        try (CqlSession session = openLabSession()) {
            PreparedStatement insert = session.prepare(
                "INSERT INTO ttl_lab.sessions_by_id " +
                "(tenant_id, session_id, owner_token, " +
                "state, issued_at, expires_at) " +
                "VALUES (?, ?, ?, ?, ?, ?) USING TTL ?");

            PreparedStatement select = session.prepare(
                "SELECT state, owner_token, " +
                "TTL(state) AS ttl_left " +
                "FROM ttl_lab.sessions_by_id " +
                "WHERE tenant_id = ? AND session_id = ?");

            // TTL test ngắn, chỉ dành cho staging.
            session.execute(insert.bind(
                    tenantId, sessionId, "lab-owner",
                    "ACTIVE", issuedAt,
                    issuedAt.plusSeconds(8), 8)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(false));

            Row initial =
                read(session, select, tenantId, sessionId);
            assertNotNull(initial);
            assertEquals("ACTIVE", initial.getString("state"));
            assertTrue(initial.getInt("ttl_left") > 0);

            // Poll tối đa 20 giây; không yêu cầu đúng từng ms.
            long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(20);
            boolean gone = false;

            while (System.nanoTime() < deadline) {
                Row current =
                    read(session, select, tenantId, sessionId);
                if (current == null) {
                    gone = true;
                    break;
                }
                Thread.sleep(400); // Chỉ trong JUnit lab.
            }

            assertTrue(gone,
                "Expected fully TTL-written session to expire");
        }
    }

    @Test
    void permanentColumnCanOutliveExpiringState()
            throws Exception {
        UUID tenantId = UUID.randomUUID();
        UUID sessionId = UUID.randomUUID();
        Instant issuedAt = Instant.now();

        try (CqlSession session = openLabSession()) {
            PreparedStatement insert = session.prepare(
                "INSERT INTO ttl_lab.sessions_by_id " +
                "(tenant_id, session_id, owner_token, " +
                "state, issued_at, expires_at) " +
                "VALUES (?, ?, ?, ?, ?, ?) USING TTL ?");

            PreparedStatement updateOwner = session.prepare(
                "UPDATE ttl_lab.sessions_by_id " +
                "SET owner_token = ? " +
                "WHERE tenant_id = ? AND session_id = ?");

            PreparedStatement select = session.prepare(
                "SELECT state, owner_token " +
                "FROM ttl_lab.sessions_by_id " +
                "WHERE tenant_id = ? AND session_id = ?");

            session.execute(insert.bind(
                    tenantId, sessionId, "temporary",
                    "ACTIVE", issuedAt,
                    issuedAt.plusSeconds(8), 8)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(false));

            // Không USING TTL và table không có default TTL.
            session.execute(updateOwner
                .bind("persistent", tenantId, sessionId)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM));

            long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(20);
            Row observed = null;

            while (System.nanoTime() < deadline) {
                observed = read(
                    session, select, tenantId, sessionId);
                if (observed != null
                        && observed.getString("state") == null) {
                    break;
                }
                Thread.sleep(400);
            }

            assertNotNull(observed);
            assertNull(observed.getString("state"));
            assertEquals(
                "persistent",
                observed.getString("owner_token"));
        }
    }
}
~~~

### 19.2. Đọc kết quả test đúng phạm vi

Test thứ nhất chứng minh trên môi trường lab: **toàn bộ non-key cells đã ghi với TTL** không còn làm row hiển thị sau khi TTL hết và có buffer. Test thứ hai chứng minh: **cột mới được ghi không TTL** có thể còn sống khi state expire.

**Không suy rộng từ hai test này rằng:**

- Replica RF3 và multi-DC đều đã repair hoàn chỉnh.
- gc_grace_seconds an toàn với outage dài ngày.
- Tombstone vật lý đã được purge khỏi SSTable.
- App/cache/search index đã xóa dữ liệu.
- Every Java writer giữ nguyên TTL và timestamp như fixture.

Cần kiểm thử riêng **delete/reinsert với ghi cạnh tranh**, **mixed TTL/default TTL**, **client retry sau timeout**, và fault nhiều replica.

### 19.3. Tránh test TTL bị flaky

- Dùng UUID mới cho mỗi test; không tái sử dụng row cũ.
- Preflight schema và cluster khỏe; không chạy CREATE TABLE từ từng worker.
- Chọn TTL đủ dài để INSERT và lần đọc đầu hoàn thành, cộng buffer cho quan sát.
- Không assert “đúng 8.000 ms” bằng sleep cố định; poll tới deadline.
- Nếu read timeout/Unavailable, test phải fail/inconclusive, **không hiểu là row đã hết TTL**.
- Đo kết quả từ timestamp UTC và TTL() của cell còn sống.
- Không đặt test suite chạy đồng thời với destructive cleanup/truncate của test khác.
- Một node RF1 có thể chứng minh CQL TTL cơ bản, không chứng minh replica divergence/zombie data.
- Không bật retry vô hạn hoặc dùng speculative execution mù cho mutations có TTL refresh.
- Nếu CI quá tải khiến lần đọc đầu diễn ra sau TTL, tăng TTL lab/điều chỉnh environment thay vì bỏ assertion.

## 20. Test fault phân tán: replica bỏ lỡ DELETE

Thử nghiệm **zombie risk** không nên viết thành một unit test JUnit tự động kill nodes production. Một bài test đúng cần **điều phối staging** với quyền vận hành, đo đầy đủ node states và lập kế hoạch phục hồi.

### 20.1. Điều kiện chuẩn bị

- Cluster lab có ít nhất **RF3 trong một DC**, disk/network đủ headroom.
- Backup/snapshot/restore path trên lab được kiểm tra.
- Table và dữ liệu chỉ phục vụ test, không chứa PII.
- Có runbook điều khiển replica tạm thời không khả dụng và restore sau fault.
- Ghi gc_grace_seconds, lịch repair, compaction strategy, token placement.
- Đặt STOP gates cho quorum, disk free, errors và node health.
- Tất cả test chỉ dùng **một hoặc vài partition keys cô lập**.
- Không thay gc_grace_seconds về 0 chỉ để tạo zombie nhanh nếu không hiểu hậu quả; test có thể tập trung vào **nhận diện stale replica và validation của repair**, thay vì bắt buộc tạo dữ liệu sống lại.

### 20.2. Kịch bản an toàn hơn: quan sát replica chậm rồi sửa trước grace

Một kịch bản minh họa:

~~~text
T0: INSERT K và xác nhận theo CL.
T1: Qua fault orchestration, một replica của K tạm unavailable.
T2: DELETE K theo CL đủ với các replica còn khỏe.
T3: SELECT theo CL và ghi outcome/metrics.
T4: Khôi phục replica trước khi vượt grace.
T5: Chạy repair theo runbook, xác minh coverage.
T6: Đối soát K không xuất hiện lại; thu server logs.
~~~

**Mục tiêu:** kiểm chứng khả năng xử lý outage trong cửa sổ an toàn và test được runbook. Đây **không phải** bài chứng minh tombstone purge hoặc zombie chắc chắn, nhưng có giá trị hơn việc ép làm mất dữ liệu.

### 20.3. Kịch bản mô phỏng zombie chỉ trên cluster vứt bỏ được

Nếu tổ chức thực sự cần tái hiện zombie, phải dùng **test cluster disposable**, dữ liệu tổng hợp, snapshot/restore, operator phối hợp và các tùy chọn version-specific đã được kiểm tra. Cần thu logs thật cho việc tombstone purge, repair coverage và stale replica return.

**Không khuyến nghị các lệnh kill node, chỉnh SSTable trực tiếp hoặc hạ grace về 0 như công thức chung**, vì chúng có thể tạo tình trạng sai lệch vượt mục tiêu hoặc phá dữ liệu test ngoài phạm vi. Không bao giờ dùng cách này trên cluster production.

### 20.4. Phân loại PASS/FAIL/INCONCLUSIVE

| Quan sát | Kết luận |
|---|---|
| DELETE xác nhận, replica sửa trong grace và K không xuất hiện lại | PASS cho **kịch bản đã thử**, không chứng minh mọi outage |
| Retry/replay writer tạo row K có timestamp mới | FAIL của application version/idempotency, không phải zombie |
| Cùng key đọc khác nhau trong lúc fault | Đánh giá theo CL, topology, deadline; có thể tạm thời hoặc là lỗi cần điều tra |
| Fault không xảy ra hoặc thiếu repair logs | INCONCLUSIVE, không tự đánh dấu PASS |
| Client timeout và không biết write/delete outcome | UNKNOWN, cần đối soát |
| Data xuất hiện sau tombstone bị purge và stale replica return | Có bằng chứng zombie; STOP, bảo vệ evidence và xử lý incident |

## 21. Thiết kế ứng dụng Java để tránh tái tạo dữ liệu đã xóa

### 21.1. Hard delete và soft delete có hợp đồng khác nhau

**Hard delete** bằng CQL DELETE tạo tombstone và làm cell/row không còn hợp lệ theo timestamp. Nó không tự gửi tín hiệu cho cache, search index và mọi bảng denormalized.

**Soft delete** dùng cột **deleted_at** hoặc **is_deleted** để ứng dụng lọc dữ liệu. Nó có thể giữ business evidence về việc xóa, nhưng đồng thời giữ dữ liệu vật lý; **không thay thế** quy định phải xóa thật/retention. Phải kiểm tra yêu cầu privacy và DR.

Một thiết kế có thể lưu **deletion ledger** với quyền hạn chế:

~~~text
business_key
deletion_request_id
deletion_version
deletion_effective_at
projection_cleanup_status
retention_policy
~~~

Các field trên chỉ là **mô hình đề xuất**, không phải bảng Cassandra tự sinh. Ledger giúp worker nhận biết delete đã xảy ra, nhưng cần chính sách lưu giữ riêng và không được giữ payload đã bị yêu cầu xóa.

### 21.2. Chống replay event cũ

~~~text
OrderCreated(v1)  -> INSERT K
OrderDeleted(v5)  -> DELETE K
OrderCreated(v1)  -> consumer replay muộn -> INSERT K (sai)
~~~

Cần event ID và version/sequence cho cùng business key; một nguồn sự thật về trạng thái xóa; quy tắc từ chối **stale versions** sau delete; idempotent processing theo event ID và cơ chế reconciliation/outbox/CDC được thiết kế đúng.

**LWT/CAS** với trường revision ở một partition có thể bảo vệ transition nếu thiết kế phù hợp, nhưng không tự tạo transaction đa bảng/broker. Phải xét partition contention và regular/serial consistency.

### 21.3. Không dùng TTL làm lớp duy nhất thu hồi quyền

Nếu session/capability phải hết hạn vào deadline xác định, service cần kiểm tra **expires_at** hoặc authority state trước khi cấp quyền, ngay cả khi CQL row còn tồn tại do một cột khác chưa expire.

Nếu API dùng cache, cache retention cũng phải tuân thủ deadline; không để cache TTL dài hơn thời gian quyền hợp lệ.

### 21.4. Đặt TTL đúng ở mọi writer

Một hệ Java có thể có repository save/upsert, custom CQL, mapping options và background update với TTL khác nhau. Khi review:

- Có service dùng **INSERT USING TTL**, service khác **UPDATE không TTL**?
- Có mapper save toàn entity ghi lại các cột đã hết hạn?
- Có retry đặt lại TTL đầy đủ thay vì deadline còn lại?
- Có bind marker TTL ở đơn vị **giây** và áp vào đúng fields?
- Có background backfill/CDC/consumer không đi qua code path chính?
- Bảng denormalized, cache và search index có cleanup cùng logical delete?
- Khi caller timeout, app có gửi lại mutation với **timestamp mới** không?

Mục tiêu là bảo vệ **logical lifecycle**, không chỉ một câu lệnh.

### 21.5. TTL không phải distributed lock

Một row có TTL không tự bảo đảm chỉ một worker sở hữu lease. Đọc rồi ghi không phải compare-and-set, clock skew/TTL refresh/timeout có thể gây ownership ambiguity. Nếu cần uniqueness/lease, dùng LWT hoặc cơ chế chuyên dụng với idempotency, fencing/version và UNKNOWN outcome handling. Không dựa vào **setIdempotent(true)** để chứng minh một lease an toàn.

## 22. Anti-pattern khi xử lý DELETE/TTL

| Anti-pattern | Nguy cơ | Thay thế |
|---|---|---|
| DELETE success nghĩa tất cả replica đã xóa vật lý | Cassandra dùng tombstone và CL | Phân biệt logical delete, convergence, purge |
| TTL 120 xóa cả row dù cột khác sống | TTL theo cell/row liveness | Kiểm tra từng cột và writers |
| TTL expire thì disk phải giảm ngay | Tombstone, SSTable, snapshot | Đo visibility và compaction riêng |
| Đặt **gc_grace_seconds=0** để dọn disk | Zombie risk với missed replicas | Review outage/repair/compaction/version |
| Ép nodetool compact để chữa zombie | Không biết business truth, I/O cao | Giữ evidence và xác định nguồn |
| Chạy repair mù | Có thể lan truyền dữ liệu sai nếu tombstone mất | Reconcile từ nguồn sự thật, DBA runbook |
| Tin lịch repair không kiểm tra coverage | Failed/skipped ranges | Kiểm tra ranges/DC/node |
| Coi mọi reappear là zombie | Writer mới/cache/TTL per-cell rất phổ biến | Điều tra theo evidence |
| Tăng DELETE timestamp cực lớn | Chặn ghi hợp lệ sau này | Sửa timestamp/versioning policy |
| Retry INSERT với ID mới sau timeout | Duplicate logical rows | Stable request ID, reconciliation |
| Retry TTL đầy đủ sau 90 giây | Refresh deadline ngoài contract | Absolute expiry + remaining TTL |
| Chỉ nhìn TTL(state) để kết luận TTL toàn row | Cột khác vẫn sống | Kiểm tra cell/history |
| API row nghĩa Cassandra chính còn row | Cache/index/read model stale | Direct SELECT theo PK và downstream |
| Đọc khác nhau theo CL rồi đổi CL âm thầm | Đổi consistency contract | Ghi CL/RF/DC, điều tra replica |
| Dùng ALLOW FILTERING để quét tìm row | Scan gây tải, timeout | Known PK + audit keys |
| Spring save toàn entity không review | Có thể ghi lại cột/TTL | Kiểm tra CQL thực và mapping |
| Node DOWN quá grace ⇒ zombie chắc chắn | Chưa chứng minh purge/reinsert | Thu compaction/repair/mutation timeline |
| Restore snapshot cũ không đối soát | Có thể mang dữ liệu bị xóa trở lại | DR cutoff/RPO và reconciliation |
| Bỏ qua delete trên bảng denormalized | Dữ liệu vẫn đọc qua query khác | Projection cleanup |
| Xóa snapshot trước khi backup verified | Mất recovery point/evidence | Manifest/retention approval |

### 22.1. DELETE không phải giao dịch đa bảng

Nếu order nằm ở **orders_by_tenant_day** và **order_lookup_by_id**, hai DELETE riêng có thể có outcome khác nhau khi một câu timeout. Cassandra không tự rollback cả hai vì ứng dụng đã gọi liên tiếp.

Cần event-driven projection, idempotent cleanup và reconciliation. Với yêu cầu xóa dữ liệu theo chính sách, phải kiểm kê mọi vị trí lưu/truyền dữ liệu, không chỉ table chính.

### 22.2. Backup/repair không phải lệnh undo

Backup chỉ hữu ích nếu manifest/cutoff/checksum và restore đã được thử. Repair đồng bộ replica theo dữ liệu hiện có, không hiểu quyết định nghiệp vụ. Trước recovery diện rộng phải xác định:

- Nguồn sự thật, cutoff, RPO/RTO và writes hợp lệ sau snapshot.
- Có delete requests mới hơn snapshot phải áp lại không?
- Có yêu cầu bảo mật/quyền riêng tư khiến restore cần làm sạch dữ liệu không?
- Kế hoạch cô lập, validate CQL và chuyển traffic là gì?

## 23. Bài tập chẩn đoán và đáp án gợi ý

### Bài 1 — Node DOWN lâu hơn gc_grace_seconds

Table có gc_grace_seconds 10 ngày. Replica C DOWN 13 ngày. DELETE K nhận LOCAL_QUORUM khi C DOWN. Sau khi C lên, SELECT thỉnh thoảng thấy K.

**Câu hỏi:** Có thể tuyên bố chắc chắn zombie ngay lập tức không?

**Đáp án:** Chưa. Đây là **tình huống nguy cơ cao**, nhưng cần biết tombstone đã bị compaction purge chưa, repair coverage và có reinsert/timestamp cao hơn hoặc cache khác không. Giữ evidence, DBA đánh giá repair/outage/tombstone timeline và reconcile từ nguồn sự thật.

### Bài 2 — Repair mỗi tuần nhưng thất bại một phần

Lịch repair chạy mỗi bảy ngày; ba lần gần nhất đều có failed token ranges, trong đó có partition K. Team ghi “đã repair tuần này”.

**Câu hỏi:** Có đủ bảo vệ trước tombstone purge không?

**Đáp án:** Không. Một lịch scheduled không tương đương **coverage thành công**. Phải kiểm tra ranges, replica/DC và errors. Điều chỉnh runbook repair frequency/alerting và gc_grace với owner dựa trên outage/recovery SLO.

### Bài 3 — TTL của state hết, row vẫn hiện

INSERT session USING TTL 120. Sau 150 giây, CQL trả state=null, owner_token='worker-A', TTL(state)=null.

**Câu hỏi:** Cassandra có chắc làm TTL sai không?

**Đáp án:** Không. Cột owner_token có thể được ghi lại không TTL sau INSERT, còn state đã hết đúng. Kiểm tra writetime/TTL từng cột, code background update và table default TTL.

### Bài 4 — Có giá trị nhưng TTL(column) null

Ứng dụng tin một column được ghi TTL 600, nhưng SELECT có state='ACTIVE', TTL(state)=null.

**Câu hỏi:** Những nguyên nhân hợp lý?

**Đáp án:** Có writer khác cập nhật không TTL, dùng TTL 0, table default TTL không như kỳ vọng hoặc cell mới từ mapper/upsert. So effective schema, CQL thực, writetime và logs; không giả định TTL hết vì state còn sống.

### Bài 5 — TTL biến mất sau heartbeat

T0: ghi state TTL 120. T0+60: heartbeat ghi lại state TTL 120. T0+130: state vẫn còn.

**Câu hỏi:** Có nhất thiết là bug Cassandra không?

**Đáp án:** Không. Heartbeat có thể refresh TTL của state tại T0+60. Nếu business TTL phải kết thúc T0+120, cần **expires_at cố định** và tính remaining TTL; không cấp lại thời hạn đầy đủ trên retry/heartbeat.

### Bài 6 — DELETE timestamp thấp hơn ghi

Một INSERT có write timestamp=900. Một DELETE gửi sau nhưng timestamp=800.

**Câu hỏi:** Vì sao SELECT vẫn có thể thấy dữ liệu?

**Đáp án:** Cassandra giải quyết mutation theo timestamp, không theo thời điểm HTTP call của người dùng. Tombstone 800 có thể không thắng giá trị 900. Phải sửa nguồn timestamp/ordering, không dùng timestamp cực lớn như mẹo chữa.

### Bài 7 — Row xuất hiện lại sau hai phút, mọi node khỏe

Audit cho thấy DELETE lúc 10:00 và background consumer INSERT lại cùng PK lúc 10:02, timestamp mới.

**Câu hỏi:** Điều tra gc_grace trước hay writer?

**Đáp án:** Writer. Đây là bằng chứng reinsert, không cần cơ chế zombie. Sửa consumer/versioning/deletion ledger và reconcile các row bị tái tạo.

### Bài 8 — Disk không giảm sau TTL

Một table TTL 24 giờ. Sau hai ngày, SELECT không thấy dữ liệu cũ nhưng filesystem vẫn dùng nhiều dung lượng và có snapshot tag lớn.

**Câu hỏi:** Có thể kết luận TTL không chạy không?

**Đáp án:** Không. Logical expiration khác SSTable purge và snapshot có thể pin file cũ. Kiểm tra compaction, SSTable retention, snapshot backup lifecycle và disk free; không xóa snapshot trước khi remote copy được xác minh.

### Bài 9 — TWCS là đủ để tự xóa đúng hạn?

Một table TWCS có TTL 7 ngày, nhưng backfill thường xuyên ghi event cũ với timestamp mới/khác window.

**Câu hỏi:** Có bảo đảm mọi SSTable bị loại đúng ngày thứ bảy?

**Đáp án:** Không. Late writes, window overlap, TTL policies, tombstone/replica safety và compaction có thể ảnh hưởng. Cần xem data pattern, TWCS config, timestamps, SSTable placement và test theo phiên bản.

### Bài 10 — LOCAL_ONE và LOCAL_QUORUM thấy khác nhau

Trong outage, client A đọc LOCAL_ONE thấy row K, client B đọc LOCAL_QUORUM không thấy.

**Câu hỏi:** Có thể lấy kết quả B làm bằng chứng mọi replica đã nhận DELETE không?

**Đáp án:** Không. Quorum local có thể đủ mà replica khác chưa được sửa. Kiểm tra RF/DC, node status, repair scope và mutations. Không tự hạ/nâng CL production mà không ghi rõ hợp đồng consistency.

### Bài 11 — Repair có thể “biết order phải xóa” không?

Tombstone đã bị purge. Stale replica còn order cũ và repair bắt đầu.

**Câu hỏi:** Repair có thể xác định đó là order bị xóa theo business policy không?

**Đáp án:** Không chỉ từ dữ liệu Cassandra hiện có nếu dấu xóa đã mất. Repair so/đồng bộ replica; cần nguồn sự thật như audit/deletion ledger và reconciliation để biết order nào phải xóa.

### Bài 12 — Java catch timeout rồi coi session expired

Java code bắt mọi exception từ SELECT session và trả null. API coi null là session đã hết hạn.

**Câu hỏi:** Có đúng ngữ nghĩa TTL không?

**Đáp án:** Không. Timeout/Unavailable/AllNodesFailed là **UNKNOWN_READ_RESULT**, khác 0 row từ CQL thành công. API cần trả lỗi hoặc xử lý fail-closed theo chính sách bảo mật rõ, không ghi “TTL đã hết” khi DB chưa phản hồi.

### Bài 13 — Hai bảng cùng một order

App DELETE order trong orders_by_tenant_day, nhưng API tra qua order_lookup_by_id vẫn thấy order.

**Câu hỏi:** Có phải tombstone chưa purge không?

**Đáp án:** Không nhất thiết. Đây là hai bảng denormalized, phải có workflow xóa/projection/reconciliation riêng. Kiểm tra CQL trên từng table, query shape và event delivery.

### Bài 14 — Múi giờ khiến sai diễn giải hạn

expires_at được lưu 08:00Z; UI Việt Nam hiển thị 15:00. Một log Java ghi “expire 08:00” và user phản ánh TTL trễ 7 giờ.

**Câu hỏi:** Trước tiên cần làm gì?

**Đáp án:** Chuẩn hóa mốc **Instant/UTC**, kiểm tra format/múi giờ ở UI và so TTL() tại thời điểm quan sát. TTL trả giây còn lại; nó không tự phụ thuộc múi giờ hiển thị.

### Bài 15 — Chỉnh gc_grace lên sau sự cố

Tombstone được cho là đã bị purge; DBA đề xuất tăng gc_grace_seconds từ 1 lên 10 ngày.

**Câu hỏi:** Thay đổi này có khôi phục tombstone đã mất không?

**Đáp án:** Không. Chỉnh table option hiện tại không tái tạo mutation đã bị purge. Cần xác lập business truth/reconciliation và sửa lịch repair/retention trước các sự cố sau; ALTER cần change approval.

### Bài 16 — Test TTL trên một container

Testcontainers một Cassandra node RF1, TTL 5 giây pass. Team tuyên bố đã kiểm chứng zombie safety với RF3 và node down 10 ngày.

**Câu hỏi:** Bằng chứng đủ không?

**Đáp án:** Không. RF1 test chỉ kiểm chứng CQL TTL cơ bản. Zombie phụ thuộc missed replica, repair coverage, gc_grace, compaction và topology. Cần suite staging nhiều node, fault orchestration, timeline và phương án restore.

### Bài 17 — Tự động dùng DELETE lần nữa có an toàn?

Sau khi thấy zombie hoặc reinsert, service gửi DELETE với timestamp rất lớn để “xóa vĩnh viễn”.

**Câu hỏi:** Rủi ro gì?

**Đáp án:** Timestamp tương lai có thể chặn những writes hợp lệ sau đó. DELETE đơn lẻ cũng không sửa cache/bảng phụ và không làm replica cũ nhận tombstone ngay. Cần ngăn source reinsert, xác định version/CL, reconcile và repair theo runbook.

### Bài 18 — Restore backup cũ có thể phục hồi dữ liệu đã xóa

Một bản snapshot tuần trước có order K, trong khi tuần này có delete request theo quyền riêng tư. Team muốn restore nguyên snapshot lên production sau lỗi ổ đĩa.

**Câu hỏi:** Cần kiểm soát gì?

**Đáp án:** Restore có thể làm K xuất hiện lại nếu không replay/reconcile deletion events. Phải phục hồi trên cluster cô lập, kiểm tra RPO/RTO, các writes/delete từ cutoff tới hiện tại, apply cleanup theo retention/privacy policy, rồi mới switch traffic.

## 24. Checklist triển khai và vận hành

### 24.1. Đối với code Java/CQL

- [ ] Mọi writer dùng primary key đúng access pattern, không tạo ID mới khi retry một logical operation.
- [ ] Có request ID/version/fingerprint để phân biệt reinsert hợp lệ và replay cũ.
- [ ] CQL INSERT/UPDATE/DELETE được ghi log theo **query shape**, không lộ bind values nhạy cảm.
- [ ] Có quy tắc write timestamp; không tự đặt timestamp ở tương lai để thắng DELETE.
- [ ] Với TTL, đã kiểm tra **từng cột được ghi** và tác động của UPDATE không TTL.
- [ ] Table default_time_to_live và explicit USING TTL/USING TTL 0 được hiểu theo version.
- [ ] Business expiry dùng **deadline/expires_at** phù hợp; không dựa vào physical purge.
- [ ] Retry giữ logical request ID và không tự refresh TTL ngoài hợp đồng.
- [ ] LWT/conditional updates phân biệt applied=true, false và UNKNOWN.
- [ ] Java Driver read timeout/Unavailable được giữ là ERROR, không biến thành row absent.
- [ ] Cache, search index, bảng lookup/denormalized có delete/invalidation và reconciliation.
- [ ] Có kiểm thử Spring Data mapper/upsert nếu sử dụng framework thay vì CQL trực tiếp.

### 24.2. Đối với Cassandra DBA/SRE

- [ ] Ghi RF/DC, local DC, CL và phạm vi token ranges liên quan.
- [ ] Đọc đúng table options **gc_grace_seconds/default_time_to_live/compaction**.
- [ ] Có node outage monitoring, cảnh báo downtime so với grace và repair policy.
- [ ] Lịch repair có **success coverage**, không chỉ tên cron/job đã chạy.
- [ ] Failed/skipped repair ranges được xử lý với owner và deadline.
- [ ] Compaction/tombstone/disk/snapshot retention được giám sát.
- [ ] Không ép compact/repair hoặc thay grace/RF trong incident trước approval.
- [ ] Có backup ở ngoài miền lỗi, manifest/checksum và restore drill.
- [ ] Có runbook cho stale replica return sau outage dài và reconciliation.
- [ ] Điều tra clock skew, TTL overflow/version limits khi có dấu hiệu.
- [ ] Có timeline sự kiện deployment, repair, streaming, compaction, backup và read/write p99.
- [ ] Không suy “node UP” là dữ liệu nhất quán hoặc TTL đúng.

### 24.3. Khi nghiệm thu một incident

- [ ] Đã xác định **nguồn Cassandra trực tiếp hay cache/projection**.
- [ ] Đã phân biệt **cell null, row không còn, data reinsert và zombie**.
- [ ] Đã thu TTL()/WRITETIME() của những cột phù hợp khi còn đọc được.
- [ ] Đã kiểm tra mutation logs/CDC và writes sau DELETE.
- [ ] Nếu nghi zombie, có evidence outage/grace/repair/compaction, không chỉ timeline mơ hồ.
- [ ] Tập business keys bị ảnh hưởng được xác định hoặc giới hạn rõ.
- [ ] Các thao tác recovery không làm mất xóa hợp lệ hoặc mở lại dữ liệu nhạy cảm.
- [ ] Test TTL theo cell, mixed TTL, retry và delete/reinsert chạy pass.
- [ ] Cluster health, quorum, p99, compaction và repair trở lại ngưỡng vận hành.
- [ ] Báo cáo có root cause, contributing factors, owner và biện pháp ngăn tái diễn.
- [ ] Những điều chưa chứng minh được ghi **UNKNOWN**, không tự bịa evidence.

## 25. Tổng kết

**Dữ liệu đã xóa xuất hiện lại** không chỉ có một nguyên nhân. Có thể là **zombie data** khi tombstone bị purge trước khi replica bỏ lỡ DELETE được đồng bộ; nhưng cũng có thể là **INSERT/UPDATE mới với timestamp cao hơn**, replay/backfill, cache, bảng denormalized hoặc đọc ở các replica/DC khác nhau.

**TTL không như mong đợi** thường liên quan đến **TTL theo cell**, một UPDATE refresh TTL, ghi mới không TTL, default_time_to_live, thời điểm server ghi, clock skew hoặc cách ứng dụng hiểu expires_at. Việc CQL không thấy cell không đồng nghĩa SSTable đã bị xóa vật lý; compaction và snapshot retention quyết định khi nào không gian có thể được thu hồi.

Một quy trình xử lý đáng tin cậy phải đi từ **đúng keyspace/table/partition key → CQL TTL()/WRITETIME() → timeline mutations/DELETE → RF/DC và consistency → replica downtime/repair coverage/gc_grace → compaction/backup → nguồn sự thật nghiệp vụ và reconciliation**. Không hạ gc_grace, ép repair/compaction hoặc tạo timestamp cực lớn khi chưa có bằng chứng và runbook. Với Apache Cassandra và ứng dụng Java, mục tiêu cuối cùng là **dữ liệu đúng theo chính sách, các replica hội tụ an toàn, TTL/retention được kiểm chứng và những lần xóa hợp lệ không bị tái tạo**.

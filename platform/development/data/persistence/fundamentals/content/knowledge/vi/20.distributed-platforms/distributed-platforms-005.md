# Độ trễ bản sao và ảnh hưởng tới đường đọc

Một API Java vừa xác nhận đơn hàng bằng một transaction thành công trên PostgreSQL primary. Ngay sau đó, giao diện gọi API lấy trạng thái đơn, nhưng kết quả lại là PENDING thay vì CONFIRMED. Người dùng nghĩ giao dịch đã bị rollback, trong khi database gốc vẫn lưu CONFIRMED. Điều gì đã xảy ra?

Một nguyên nhân thường gặp là **đường đọc đã được điều hướng tới read replica đang chậm hơn primary**. Bản sao có thể chưa nhận, chưa ghi bền vững hoặc chưa áp dụng transaction vừa commit. Do đó, việc primary xác nhận commit và việc một câu SELECT trên replica nhìn thấy commit **là hai sự kiện khác nhau**.

Bài thuộc chương **Nền tảng phân tán** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Người học kết hợp kiến thức về persistence Java, giao dịch, cô lập, kết nối, độ bền, lỗi và tối ưu truy vấn để thiết kế đường đọc có bảo đảm nhất quán phù hợp, đồng thời khai thác replica đúng mục đích.

> **Thông điệp cốt lõi:** replica giảm tải và có thể tăng khả năng phục vụ lượt đọc, nhưng không tự làm mọi truy vấn nhìn thấy dữ liệu mới nhất. Mọi đường đọc phải có hợp đồng về **độ mới cần thiết**, **nguồn đọc phù hợp** và **cách xử lý khi replica tụt lại**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt primary, replica, replication bất đồng bộ và replication đồng bộ.
- Giải thích độ trễ nhận, ghi/flush và replay log, cũng như thời điểm transaction xuất hiện trong kết quả SELECT.
- Phân tích stale read, read-your-writes, monotonic reads và ảnh hưởng đến các thao tác đọc sau ghi.
- Xác định yêu cầu nhất quán theo từng use case thay vì gửi mọi SELECT đến replica.
- Hiểu ý nghĩa và giới hạn của các số liệu PostgreSQL như pg_stat_replication, replay LSN và thời điểm replay transaction.
- Thiết kế primary/replica routing trong Java/Spring mà không nhầm annotation readOnly với chỉ thị chọn database.
- Đề xuất các cách bảo đảm đọc sau ghi: đọc primary, session affinity, watermark/LSN và fallback khi timeout.
- Nhận diện rủi ro failover, dữ liệu không nằm trên replica được promote, transaction snapshot cũ và replica query conflict.
- Kiểm thử sự cố replication lag, quan sát metric, xác định SLO và đưa ra chính sách vận hành phù hợp.

## 2. Primary và read replica có trách nhiệm khác nhau

Trong một hệ thống cơ sở dữ liệu có replication:

- **Primary (leader/writer):** nơi ứng dụng được phép thực hiện các ghi có thẩm quyền trong một giai đoạn hoạt động. Transaction trên primary có thể tạo log để đồng bộ sang các node khác.
- **Replica (standby/follower):** nhận thay đổi từ primary theo cơ chế của hệ quản trị. Replica có thể được dùng để phục vụ SELECT, hỗ trợ failover hoặc duy trì bản sao ở vị trí địa lý khác.
- **Replication lag:** độ lệch giữa tiến độ/điểm dữ liệu mà primary đã có và tiến độ tương ứng ở replica; cần chỉ rõ đang đo độ lệch nào.

~~~mermaid
flowchart LR
    A["Java Order Service"] -->|INSERT / UPDATE / COMMIT| P[("PostgreSQL primary")]
    P -->|WAL streaming| R1[("Replica A")]
    P -->|WAL streaming| R2[("Replica B")]
    B["GET order"] --> LB{"Read routing"}
    LB -->|Cho phép stale| R1
    LB -->|Cần mới nhất| P
~~~

Việc một node là replica **không đồng nghĩa** nó luôn chỉ chậm đúng một khoảng thời gian cố định. Có lúc lag gần bằng không, có lúc tăng lên vì tải ghi đột biến, mạng trễ, thiếu tài nguyên hoặc một truy vấn standby giữ snapshot quá lâu.

### 2.1. Vì sao hệ thống dùng read replica?

| Mục đích | Lợi ích kỳ vọng | Giới hạn phải đánh giá |
|---|---|---|
| Giảm tải đọc trên primary | Tách nhiều SELECT khỏi node xử lý ghi | SELECT trên replica có thể cũ |
| Đọc gần người dùng ở vùng địa lý khác | Giảm một phần độ trễ mạng | Cross-region replication thường có độ trễ và đường failover riêng |
| Tách workload báo cáo | Giảm ảnh hưởng truy vấn dài tới primary | Long-running query có thể xung đột với replay hoặc làm tăng bloat tùy cấu hình |
| Khả năng phục hồi khi primary hỏng | Một replica có thể được promote | Không phải replica nào cũng chứa mọi commit đã ACK trên primary |
| Thực hiện sao lưu hoặc tác vụ bảo trì phù hợp | Phân tải tác vụ chuyên biệt | Phải xác minh giới hạn DBMS và chính sách vận hành |

Read replica không phải luôn nhanh hơn primary: nếu bản sao yếu hơn, mạng xa hơn hoặc query chạy trên dữ liệu/index không phù hợp, độ trễ SELECT có thể cao hơn. Nó cũng không tạo backup lịch sử để chống xóa nhầm: lệnh xóa có thể được sao chép sang các bản sao.

### 2.2. Replica khác cache ở đâu?

| Thuộc tính | Read replica | Cache ứng dụng |
|---|---|---|
| Dữ liệu | Thường là bản sao DB được đồng bộ qua log hay giao thức replication | Tập kết quả, object hoặc projection theo cache key |
| Tiến độ | Log receive/write/flush/replay, hoặc cơ chế DBMS khác | TTL, refresh, invalidation và version của entry |
| Truy vấn | SQL có thể lọc, JOIN, aggregate theo khả năng replica | GET theo key hoặc data structure của cache |
| Ghi | Read-only standby thường không nhận giao dịch ghi nghiệp vụ | Một số cache cho phép SET/DEL theo chính sách ứng dụng |
| Rủi ro stale | Replica chưa replay commit | Entry chưa refresh/invalidate, hoặc cache loader ghi lại dữ liệu cũ |
| Bằng chứng mới | LSN/watermark, replication progress, nguồn đọc | Version/generation và giao thức bảo đảm freshness |

Một API có thể đọc từ cache **đặt trên read replica**, tạo thành hai lớp bất đồng bộ. Khi dữ liệu cũ xuất hiện, phải xác định nó cũ ở tầng nào thay vì quy tất cả cho database.

## 3. Dòng thời gian: COMMIT ở primary đến SELECT ở replica

Giả sử Order O7 ban đầu có trạng thái PENDING.

~~~mermaid
sequenceDiagram
    participant W as Java writer
    participant P as Primary
    participant R as Read replica
    participant U as Java reader
    W->>P: UPDATE O7 = CONFIRMED
    W->>P: COMMIT
    P-->>W: COMMIT OK
    Note over P,R: WAL đang truyền / chờ replay
    U->>R: SELECT status O7
    R-->>U: PENDING
    P-->>R: WAL chứa COMMIT
    R->>R: Replay transaction
    U->>R: SELECT status O7 lần mới
    R-->>U: CONFIRMED
~~~

Sau khi database gốc xác nhận transaction, một lần đọc trên standby có thể trả trạng thái trước đó vì commit record chưa được replay. Đây là **stale read do replica lag**, không phải chứng cứ cho thấy COMMIT trên primary thất bại.

### 3.1. Một transaction không xuất hiện một phần như một transaction đã commit

Trên PostgreSQL physical standby dùng hot standby queries, các thay đổi được replay theo ngữ nghĩa transaction. Một truy vấn bình thường không nên nhìn thấy “một nửa transaction đã commit” chỉ vì các WAL record đang đến từng đợt. Bản sao có thể **chưa thấy commit mới**, nhưng snapshot truy vấn tuân thủ quy tắc nhất quán của PostgreSQL.

Điều này quan trọng: replica lag thường khiến ta thấy **phiên bản cũ nhất quán trong snapshot**, không nhất thiết một bản ghi bị ghi một nửa. Tuy nhiên dữ liệu từ **hai dịch vụ hoặc hai replica khác nhau** có thể thuộc các thời điểm logic khác nhau; một API tổng hợp nhiều nguồn vẫn có thể tạo kết quả không nhất quán ở cấp nghiệp vụ.

### 3.2. Ba mốc WAL khác nhau

Với mô hình PostgreSQL streaming replication, cần phân biệt:

1. **Received/written:** standby đã nhận WAL và ghi dữ liệu theo tầng của nó.
2. **Flushed:** standby đã flush WAL vào storage theo contract hệ điều hành/thiết bị.
3. **Replayed/applied:** standby đã áp dụng WAL để các transaction đã commit có thể xuất hiện trong snapshot của các truy vấn mới.

**Đã nhận WAL chưa đồng nghĩa truy vấn đọc được thay đổi.** **Đã flush WAL cũng chưa nhất thiết đồng nghĩa đã replay xong.** Đường đọc phụ thuộc tiến độ replay cùng snapshot thực tế của câu SELECT.

~~~text
Primary WAL          Standby receive/write       Standby flush       Standby replay
LSN: 0/5000         LSN: 0/4F00                LSN: 0/4E00        LSN: 0/4C00
     |                      |                          |                    |
     +-- khoảng cách truyền-+-- khoảng cách flush ----+-- khoảng cách apply-+
~~~

Các con số LSN chỉ minh họa thứ tự tiến độ, không phải số đo thời gian. LSN thể hiện **vị trí log**, vì vậy hiệu hai LSN đo lượng byte WAL tương đối chứ không trực tiếp đo “replica chậm bao nhiêu giây”.

## 4. Các kiểu nhất quán đọc cần phân biệt

### 4.1. Eventual consistency

Nếu quá trình sao chép còn hoạt động và hệ thống không có lỗi vĩnh viễn, replica cuối cùng có thể bắt kịp primary. Ứng dụng chấp nhận dữ liệu có thể cũ trong một khoảng thời gian không xác định hoặc có giới hạn theo hợp đồng.

Hợp lý cho: trang danh sách mang tính khám phá, báo cáo chấp nhận lag, tìm kiếm hoặc recommendation. Không nên mặc định hợp lý cho xác nhận thanh toán, phân quyền nhạy cảm hoặc thao tác trừ tồn kho.

### 4.2. Read-your-writes

Một actor đã ghi và nhận xác nhận commit, thì **những lần đọc tiếp theo của actor ấy** cần thấy ít nhất tác động của chính lần ghi đó.

~~~text
POST /orders/O7/confirm -> 200 OK
GET  /orders/O7          -> PENDING (vi phạm mong đợi read-your-writes)
~~~

Một luồng UX thực tế thường mong rằng sau khi nhấn “Xác nhận”, trạng thái sẽ không quay lại PENDING. Nếu GET được định tuyến tới replica không có mốc đảm bảo, ứng dụng chưa cung cấp read-your-writes.

Cách giải quyết đơn giản: cho đường GET ngay sau hành động ghi đọc **primary**, hoặc trả lại representation từ kết quả authoritative đã commit và giữ routing phù hợp ở các lượt đọc tiếp theo.

### 4.3. Monotonic reads

Một actor đã đọc trạng thái CONFIRMED, thì lần đọc tiếp theo không nên tự nhiên thấy PENDING **nếu nghiệp vụ không có một transition ngược hợp lệ**.

Ví dụ:

~~~text
GET qua Replica A -> CONFIRMED (đã replay v12)
GET qua Replica B -> PENDING   (mới replay v11)
~~~

Load balancer chuyển giữa hai replica với tiến độ khác nhau gây **đọc lùi thời gian**. Session affinity, watermark tối thiểu hoặc routing primary có thể giảm hiện tượng này. Chỉ “sticky tới một replica” không đủ nếu replica ấy được reset/rewind hoặc có failover làm mất tiến độ; phải hiểu topology và điều kiện vận hành.

### 4.4. Causal consistency và thứ tự phụ thuộc

Một service vừa tạo order, sau đó phát event và service khác tạo invoice. API tổng hợp order và invoice có thể đọc các bản sao ở những mốc khác nhau: invoice xuất hiện nhưng truy vấn order trên một replica cũ vẫn trả “không tồn tại”.

Cần làm rõ **quan hệ nhân quả** giữa các bước và contract của API tổng hợp, không suy một transaction local trên mỗi service tạo snapshot chung cho toàn bộ hệ thống.

### 4.5. Linearizable hoặc latest-read contract

Nếu nghiệp vụ yêu cầu “mọi SELECT bắt đầu sau khi write được xác nhận phải thấy write đó” theo một giao thức nhất quán mạnh, chỉ dùng read replica bất đồng bộ **không đủ**. Đọc primary cũng cần xét isolation level, transaction snapshot đang mở, leader/failover fencing và các điều kiện hệ thống cụ thể.

Bảng gợi ý:

| Hợp đồng | Ví dụ | Đường đọc khởi đầu |
|---|---|---|
| Có thể stale vài giây/phút | Danh sách tin tức, dashboard không realtime | Replica với SLO lag |
| Read-your-writes | Trạng thái đơn sau POST/PUT | Primary hoặc replica đã qua watermark của commit |
| Không đọc lùi trạng thái | Lịch sử giao dịch của cùng người dùng | Routing gắn với tiến độ tối thiểu của phiên |
| Quyết định phải dựa trên trạng thái hiện hành | Reserve inventory, kiểm tra số dư trước ghi | Giao dịch/UPDATE có điều kiện trên nguồn authoritative |
| Báo cáo nhiều truy vấn cùng snapshot | Chốt số liệu theo một thời điểm | Transaction read-only đúng mức isolation trên cùng DB/snapshot được hỗ trợ |
| Đọc xuyên nhiều hệ thống cùng thời điểm | Order + payment + inventory | Không có sẵn từ một local transaction; cần orchestration và consistency contract rõ |

## 5. Những nguyên nhân tạo ra replica lag

Lag không chỉ đến từ tốc độ mạng. Một danh sách chẩn đoán hữu ích:

| Nhóm nguyên nhân | Biểu hiện | Ví dụ |
|---|---|---|
| Ghi trên primary tăng đột biến | WAL sinh nhanh hơn standby xử lý | Batch INSERT/UPDATE lớn |
| Mạng truyền WAL | Receiver tiến độ chậm, reconnect hoặc mất packet | Cross-region RTT/packet loss |
| I/O trên standby | Nhận WAL nhưng flush/replay chậm | Storage bão hòa |
| CPU hoặc tài nguyên standby | Replay không bắt kịp | Node replica cấu hình yếu |
| Query dài trên hot standby | Replay có thể phải chờ hoặc hủy query theo chính sách | Báo cáo giữ snapshot cũ |
| Maintenance/checkpoint | Tăng tải I/O và latency | Checkpoint, VACUUM hoặc workload phụ trợ |
| Replication slot/stream lỗi | Không truyền được WAL mới | Network partition, slot/cấu hình sai |
| Sự cố topology | Replica đã ngừng theo primary hiện tại | Failover, timeline thay đổi |
| Transaction dài hoặc thay đổi log lớn | Replay có lượng công việc lớn | Thao tác DDL/DML gây áp lực |
| Resource contention khác | Query người dùng tranh CPU/I/O với replay | Analytics chạy trực tiếp trên standby |

Không phải mọi nguyên nhân đều sửa bằng tăng phần cứng. Một query báo cáo giữ tài nguyên quá lâu có thể cần giới hạn thời gian hoặc được chuyển sang data warehouse thích hợp; một ứng dụng chọn nhầm replica cho đọc sau ghi cần **sửa routing/contract**, không chỉ giảm lag trung bình.

## 6. Đường đọc bị ảnh hưởng thế nào?

### 6.1. Hiển thị sai trạng thái ngay sau thao tác

Người dùng hủy đơn, API trả thành công, nhưng trang chi tiết vẫn hiển thị trạng thái cũ. Nếu frontend tự động retry hành động hủy vì tin rằng chưa thành công, có thể tạo tác động nghiệp vụ trùng.

**Khắc phục:** response của command trả trạng thái đã commit, GET sau ghi dùng nguồn đáp ứng read-your-writes, và request lặp có idempotency.

### 6.2. Không tìm thấy record vừa được tạo

~~~text
POST /orders -> 201 Created, id=O7
GET  /orders/O7 trên replica -> 404 Not Found
~~~

Không nên kết luận O7 chưa tồn tại chỉ từ một lần 404 trên replica. Có thể cần giữ đường đọc primary trong thời gian ngắn hoặc phản hồi trạng thái “chưa đồng bộ” theo contract. Cache một kết quả 404 từ replica quá lâu càng làm lỗi kéo dài.

### 6.3. Đọc version cũ rồi gửi cập nhật cạnh tranh

Một form lấy order version 8 từ replica trong khi primary đã ở version 9. Người dùng chỉnh sửa, gửi expectedVersion=8. Nếu persistence dùng optimistic locking, UPDATE trên primary không ảnh hưởng hàng nào và application trả conflict.

Đây là một cơ chế an toàn **phát hiện dữ liệu đọc đã cũ**, nhưng có thể làm trải nghiệm người dùng khó chịu. Đừng bỏ điều kiện version để “sửa” lỗi: điều đó dễ gây lost update. Cần chọn nguồn đọc và thông báo refresh thích hợp.

### 6.4. Quyết định nghiệp vụ sai do đọc replica

Nếu application đọc tồn kho trên replica thấy available=10 nhưng primary còn 1, rồi xác nhận bán 10 hàng mà không kiểm tra trên primary, nó phá invariant. Tương tự với kiểm tra số dư, hạn mức, quota hoặc quyền truy cập đã bị thu hồi.

Với bất biến quan trọng, hãy thực thi kiểm tra và ghi trong **cùng transaction trên nguồn authoritative** hoặc bằng UPDATE nguyên tử có điều kiện:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE tenant_id = :tenantId
  AND sku = :sku
  AND available >= :quantity
RETURNING available;
~~~

Nếu UPDATE trả 0 hàng, chưa giữ được số lượng yêu cầu. Một lượt đọc sớm trên replica chỉ nên phục vụ hiển thị/gợi ý theo contract, không phải quyết định cuối.

### 6.5. API tổng hợp nhiều bảng hoặc nhiều dịch vụ

Một báo cáo có thể truy vấn tổng đơn hàng trên replica A và doanh thu trên replica B: hai kết quả thuộc hai tiến độ khác nhau. Kể cả cùng replica, nếu dùng READ COMMITTED và nhiều câu SELECT riêng, mỗi câu có thể bắt đầu snapshot khác nhau.

Nếu cần một báo cáo cùng thời điểm, hãy dùng **cùng snapshot trong transaction** với isolation phù hợp trên một nguồn dữ liệu; đối với nhiều database, cần thiết kế snapshot logic hoặc cơ chế tổng hợp chuyên dụng. “Cùng gọi read replica” không tự đồng nghĩa “cùng một snapshot”.

## 7. Quan sát replication lag ở PostgreSQL

Một kỹ sư không nên kết luận “replica luôn chậm 1 giây” chỉ từ một biểu đồ. Trước hết phải biết metric đo điều gì: từ lúc primary sinh WAL đến standby **nhận**, **flush**, hay **replay**; theo số byte WAL hay thời gian; và trong trạng thái đang có giao dịch mới hay hệ thống đang idle.

### 7.1. Trên primary: xem tiến độ từng standby

PostgreSQL cung cấp view pg_stat_replication cho các kết nối WAL sender:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
~~~

Ý nghĩa khái quát:

| Trường | Cách hiểu | Không nên suy ra |
|---|---|---|
| sent_lsn | Vị trí WAL primary đã gửi tới standby | Standby đã nhận hoặc replay toàn bộ |
| write_lsn | Standby báo vị trí WAL đã ghi | WAL đã được flush bền vững hay áp dụng |
| flush_lsn | Standby báo vị trí đã flush | Query đã nhìn thấy mọi commit tới vị trí ấy |
| replay_lsn | Standby báo vị trí đã replay | Mọi transaction SELECT đang mở đều tự đổi snapshot |
| write_lag | Thời gian đo liên quan đến mốc standby ghi WAL | Tuổi dữ liệu stale chính xác của mọi câu SELECT |
| flush_lag | Thời gian đo liên quan đến mốc standby flush WAL | Thời gian phục hồi của toàn cụm |
| replay_lag | Thời gian đo liên quan tới mốc standby replay | Độ trễ tuyệt đối hiện tại khi hệ thống idle |
| sync_state | Vai trò đồng bộ của standby theo topology hiện hành | Chắc chắn mọi replica đều được chờ tại commit |

Các cột lag thời gian trong pg_stat_replication mô tả thời gian gần đây để WAL đạt những mốc tương ứng khi primary đang xử lý commit; chúng không phải bộ đo độc lập “những thay đổi còn thiếu từ primary tới replica mất bao nhiêu giây” trong mọi trạng thái. Chúng có thể NULL và không nên dùng như timestamp freshness tuyệt đối.

Để thấy độ lệch WAL theo byte, có thể quan sát:

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    pg_size_pretty(
        GREATEST(
            0,
            pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)
        )::bigint
    ) AS replay_gap_approx
FROM pg_stat_replication
WHERE replay_lsn IS NOT NULL;
~~~

Đây là **độ chênh vị trí log xấp xỉ**, không phải số giây lag hay lượng dữ liệu bảng chưa cập nhật. LSN tăng theo lượng WAL sinh ra; một transaction lớn có thể tạo nhiều byte, còn hệ thống idle có thể rất ít byte. Việc đọc số này cũng là ảnh chụp ở một thời điểm và có thể thay đổi ngay sau SELECT.

### 7.2. Trên standby: nhận WAL và replay WAL

Trên node đang ở recovery, có thể dùng:

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS last_received_lsn,
    pg_last_wal_replay_lsn() AS last_replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit_time;
~~~

Và quan sát chênh lệch tiến độ cục bộ:

~~~sql
SELECT
    pg_wal_lsn_diff(
        pg_last_wal_receive_lsn(),
        pg_last_wal_replay_lsn()
    ) AS received_not_yet_replayed_bytes;
~~~

Nếu receiver đang bắt kịp mạng nhưng replay chậm, hiệu giữa receive và replay có thể tăng. Nếu kết nối replication bị đứt, receive có thể đứng yên trong khi primary tiếp tục sinh WAL; phải quan sát cả primary và trạng thái WAL receiver.

**Không hiểu nhầm timestamp:** pg_last_xact_replay_timestamp() cho thời điểm commit/abort của transaction cuối được replay theo semantics PostgreSQL. Nếu không có transaction mới trong một giờ, lấy clock_timestamp() trừ timestamp ấy sẽ ra một giờ dù replica có thể hoàn toàn bắt kịp primary. Giá trị NULL cũng có thể xuất hiện khi chưa replay transaction nào. Sai lệch đồng hồ giữa các máy và workload idle khiến chênh lệch timestamp này không phải số đo lag phổ quát.

### 7.3. Phân biệt “lag bằng 0” với “đọc được điều mình cần”

Ngay cả khi biểu đồ replay_lag rất thấp, một GET bắt đầu tại đúng cửa sổ trước lúc commit được replay vẫn có thể trả dữ liệu cũ. Và nếu một transaction REPEATABLE READ đã tạo snapshot trước khi commit được replay, bản snapshot đang giữ có thể tiếp tục không thấy thay đổi dù replay đã tiến tới WAL mới.

Vì vậy metric replication là **tín hiệu vận hành**, không tự thay thế bằng chứng nhất quán của từng request. Use case cần read-your-writes phải dựa trên nguồn đọc/điểm tiến độ phù hợp với **commit cụ thể**, không chỉ một ngưỡng lag trung bình.

### 7.4. Quyền và chi phí giám sát

Một số view và thông tin session cần quyền phù hợp. Chỉ cấp quyền quan sát cần thiết, không cho phép API public tùy ý đọc chi tiết replication, địa chỉ hạ tầng hoặc cấu hình nhạy cảm. Query giám sát nên chạy theo chu kỳ và được phân tải phù hợp; không yêu cầu mỗi request người dùng chạy toàn bộ pg_stat_replication.

## 8. Replication lag và transaction snapshot: hai nguyên nhân stale khác nhau

Giả sử standby đã replay version 9 của một order. Nhưng một transaction đọc lâu đã bắt đầu ở thời điểm chỉ có version 8.

~~~text
T1 trên standby: BEGIN ISOLATION LEVEL REPEATABLE READ
T1: SELECT order -> version 8

Standby nhận và replay COMMIT version 9

T1: SELECT order lần nữa -> vẫn có thể version 8 trong snapshot cũ
T1: COMMIT

T2 trên standby: BEGIN; SELECT -> version 9
~~~

Ở PostgreSQL, REPEATABLE READ giữ snapshot ổn định trong transaction. Vì vậy:

1. **Replay đã hoàn tất** là điều kiện cần để một giao dịch vừa commit xuất hiện trên standby.
2. **SELECT được thực hiện trong snapshot mới phù hợp** cũng cần thiết khi yêu cầu đọc thay đổi đó.
3. Không thể chỉ “chờ replica bắt kịp” trong một transaction giữ snapshot cũ rồi kỳ vọng SELECT kế tiếp tự nhìn thấy phiên bản mới.

Với READ COMMITTED, các statement mới thường dùng snapshot mới; tuy nhiên nếu câu SELECT bắt đầu trước mốc replay hoặc dùng connection tới node khác, vẫn có thể đọc stale. Cần xét cả database routing, thời điểm snapshot và chính sách isolation.

### 8.1. Read-only transaction không đồng nghĩa latest-read

Một transaction được đánh dấu read-only chỉ là giao dịch không dự kiến ghi theo contract/framework/DB. Nó không hứa dữ liệu mới nhất. Nếu mở trên một standby trễ 10 giây, tất cả SELECT trong đó có thể đọc dữ liệu theo tiến độ standby.

Tương tự, annotation readOnly trong Spring không tự tạo một snapshot có thể nhìn mọi commit trên primary.

### 8.2. Long-running query có thể làm replay bị ảnh hưởng

Trên PostgreSQL hot standby, replay WAL có thể xung đột với các query đang chạy vì cần thu hồi phiên bản hàng hoặc lock metadata. Tùy cấu hình như max_standby_streaming_delay, standby có thể **chờ** để giữ query hoặc **hủy query** nhằm cho replay tiếp tục.

Tăng giới hạn chờ có thể giúp báo cáo lâu hoàn thành nhưng làm dữ liệu trên replica stale thêm. Bật hot_standby_feedback có thể giúp giảm một số xung đột cleanup nhưng khiến primary giữ phiên bản row lâu hơn, tăng nguy cơ bloat. Đây là đánh đổi giữa freshness, throughput truy vấn và tài nguyên của primary; cần đo trên workload thực.

## 9. Chọn đường đọc theo hợp đồng nghiệp vụ

Có bốn chiến lược khởi đầu phổ biến:

### 9.1. Đọc primary cho các luồng cần đúng ngay sau ghi

Một request thay đổi trạng thái đơn rồi hiển thị trang chi tiết có thể dùng primary cho GET sau ghi. Cách này đơn giản, rõ trách nhiệm và không yêu cầu xây một giao thức đồng bộ replay phức tạp.

Hạn chế: tăng tải và kết nối đọc trên primary. Nếu tất cả SELECT đều bị ép về primary, read replica giảm bớt giá trị. Hãy áp dụng cho đúng các luồng cần freshness cao.

### 9.2. Đọc replica cho những truy vấn chấp nhận stale

Danh sách sản phẩm hoặc báo cáo gần thời gian thực có thể đọc replica nếu contract quy định độ trễ được chấp nhận và hệ thống có cảnh báo khi vượt ngưỡng.

Nếu replica tụt lại quá lâu, có thể:

- Đổi nguồn đọc về primary nếu primary còn năng lực và dữ liệu phải tương đối mới.
- Trả kết quả với timestamp/as-of marker nếu người dùng chấp nhận.
- Tạm ngưng chức năng báo cáo hoặc trả 503 thay vì công bố dữ liệu sai.
- Chuyển query sang replica khác đã đủ mới nếu có.

Không có phương án mặc định đúng cho mọi sản phẩm. Chọn theo nghiệp vụ và khả năng chịu tải.

### 9.3. Session stickiness sau write

Sau khi actor ghi thành công, lưu một cờ “đọc primary” trong một khoảng thời gian ở session/request context. Ví dụ trong vài giây sau POST, các GET liên quan đến cùng actor được đưa tới primary.

Lợi ích là đơn giản và cải thiện UX. Nhưng đây thường là **heuristic theo thời gian**, không phải bảo đảm chặt: nếu replication lag lâu hơn khoảng stickiness, lần đọc chuyển lại replica vẫn có thể stale. Nếu người dùng đổi thiết bị/instance và token không được chia sẻ, cờ có thể biến mất.

Nếu yêu cầu read-your-writes thực sự là điều kiện bắt buộc, cần cách ràng buộc tiến độ mạnh hơn hoặc tiếp tục đọc primary.

### 9.4. Watermark/version và đợi replica bắt kịp

Trong một số hệ, client nhận **token mô tả tiến độ commit cần quan sát**, rồi yêu cầu read service chỉ trả từ replica đã đạt token đó. Nếu chưa bắt kịp sau một giới hạn chờ, fallback primary hoặc trả lỗi có kiểm soát.

Có hai nhóm token:

- **Business version** của một entity, ví dụ order version=12. Đọc replica thấy version=11 là stale; ứng dụng có thể chuyển primary. Token này thích hợp khi yêu cầu có phạm vi một object và version tăng đơn điệu đúng cách.
- **WAL/replication position** (ví dụ PostgreSQL LSN) cho một commit đã xác định. Hữu ích với yêu cầu đọc nhiều hàng/bảng có liên hệ với commit trong cùng cụm; cần quản lý timeline, failover và thời điểm snapshot.

Chiến lược watermark đòi hỏi triển khai cẩn thận hơn, nhưng cho phép bảo vệ freshness theo một mốc cụ thể thay vì hy vọng replica chỉ trễ dưới vài giây.

## 10. Java: phân tách dịch vụ ghi primary và dịch vụ đọc

Trong Spring, có thể khai báo hai DataSource riêng: một hướng tới primary, một hướng tới replica. Tầng ứng dụng chọn một trong hai theo hợp đồng của use case.

Ví dụ có hai JdbcTemplate được cấu hình và phân biệt bằng qualifier:

~~~java
@Service
public class OrderReadService {
    private final JdbcTemplate primaryJdbc;
    private final JdbcTemplate replicaJdbc;

    public OrderReadService(
            @Qualifier("primaryJdbcTemplate") JdbcTemplate primaryJdbc,
            @Qualifier("replicaJdbcTemplate") JdbcTemplate replicaJdbc) {
        this.primaryJdbc = primaryJdbc;
        this.replicaJdbc = replicaJdbc;
    }

    public OrderView readFresh(long tenantId, UUID orderId) {
        return queryOne(primaryJdbc, tenantId, orderId);
    }

    public OrderView readEventually(long tenantId, UUID orderId) {
        return queryOne(replicaJdbc, tenantId, orderId);
    }

    private OrderView queryOne(
            JdbcTemplate jdbc,
            long tenantId,
            UUID orderId) {
        return jdbc.queryForObject(
            """
            SELECT id, status, version
            FROM orders
            WHERE tenant_id = ? AND id = ?
            """,
            (rs, n) -> new OrderView(
                rs.getObject("id", UUID.class),
                rs.getString("status"),
                rs.getLong("version")
            ),
            tenantId, orderId
        );
    }
}

public record OrderView(UUID id, String status, long version) {}
~~~

Method readFresh và readEventually cho người gọi thấy rõ mục đích. Đoạn code minh họa chưa xử lý EmptyResultDataAccessException, replica unavailable hoặc retry policy; trong triển khai thật phải ánh xạ not found đúng với nguồn đọc, tránh trả 404 từ replica stale cho một record vừa tạo.

**Chú ý:** hai JdbcTemplate có thể dùng hai connection pool và hai database endpoint; cùng nằm trong một service Java **không** làm chúng trở thành một transaction.

### 10.1. Đường ghi trong một transaction primary

~~~java
@Service
public class ConfirmOrderService {
    private final JdbcTemplate primaryJdbc;

    public ConfirmOrderService(
            @Qualifier("primaryJdbcTemplate") JdbcTemplate primaryJdbc) {
        this.primaryJdbc = primaryJdbc;
    }

    @Transactional(transactionManager = "primaryTransactionManager")
    public OrderView confirm(long tenantId, UUID orderId) {
        int changed = primaryJdbc.update(
            """
            UPDATE orders
            SET status = 'CONFIRMED', version = version + 1
            WHERE tenant_id = ?
              AND id = ?
              AND status = 'PENDING'
            """,
            tenantId, orderId
        );

        if (changed != 1) {
            throw new IllegalStateException(
                "Order not found or cannot be confirmed"
            );
        }

        return primaryJdbc.queryForObject(
            """
            SELECT id, status, version FROM orders
            WHERE tenant_id = ? AND id = ?
            """,
            (rs, n) -> new OrderView(
                rs.getObject("id", UUID.class),
                rs.getString("status"),
                rs.getLong("version")
            ),
            tenantId, orderId
        );
    }
}
~~~

Ví dụ chỉ dùng một DataSource primary trong transaction. Với lời gọi đi qua Spring proxy và transaction mới được tạo, proxy sẽ commit trước khi return bình thường tới caller; nhưng nếu method **tham gia transaction ngoài**, nó chưa tự commit khi return. Nếu commit thất bại hoặc mất ACK, caller có thể nhận exception mặc dù body đã chạy; phải có idempotency/reconciliation tương ứng.

Nếu một UPDATE ở primary yêu cầu trạng thái hiện hành, cần tính đến concurrency và invariant. Khi dùng read replica để prefill form, hãy đưa expectedVersion và dùng optimistic locking khi ghi để tránh ghi đè những cập nhật đã xảy ra trên primary.

### 10.2. Không suy routing từ @Transactional(readOnly=true)

~~~java
@Transactional(readOnly = true)
public OrderView find(UUID id) {
    // readOnly là hint/transaction setting, không tự chọn replica.
    ...
}
~~~

Annotation readOnly **không tự biết** JDBC URL nào là replica. Nếu hệ thống dùng AbstractRoutingDataSource, phải xác định routing key trước khi connection được lấy, xử lý proxy/propagation đúng và đảm bảo transaction manager tương ứng.

Ngoài ra, với một transaction đã được mở ở primary, method lồng nhau readOnly=true không nên tự ý chuyển sang replica giữa transaction mà application tưởng đang có cùng snapshot. Hãy thiết kế và kiểm thử rõ việc chọn DataSource **ở ranh giới transaction**, không ẩn việc chuyển node trong từng DAO call.

### 10.3. Context routing và tác vụ bất đồng bộ

Nếu dùng ThreadLocal để ghi lại “đọc primary sau write”, phải clear ở cuối request trong finally hoặc cơ chế tương đương. Thread pool tái sử dụng thread, nếu không clear có thể rò chính sách routing giữa hai request; tác vụ @Async có thể chạy trên thread khác và **không tự nhận context**.

Phương án token tường minh trong request/session thường dễ kiểm soát hơn đối với hệ thống đa instance, nhưng phải bảo vệ token khỏi giả mạo nếu nó làm thay đổi quyền hoặc tiêu thụ tài nguyên đặc biệt.

## 11. Đọc sau ghi bằng watermark PostgreSQL: thiết kế đúng thời điểm

PostgreSQL cung cấp các LSN giúp so sánh tiến độ WAL. Một quy trình minh họa để một request GET chỉ dùng standby đã bắt kịp một mốc:

1. Thực thi transaction ghi trên primary và **nhận kết quả COMMIT**.
2. Sau khi commit xong, lấy mốc WAL trên **chính primary hiện hành**, ví dụ một câu SELECT pg_current_wal_lsn() trên kết nối mới hoặc sau khi transaction đã kết thúc. Mốc này ở hoặc sau bản ghi COMMIT của thao tác vừa xong. Không lấy một LSN trước khi COMMIT rồi mặc định đó là commit position.
3. Client/đường đọc giữ mốc dưới dạng token gắn với epoch/timeline hợp lệ của primary hiện tại, với kiểm soát tính tin cậy của token.
4. Trên standby được chọn, kiểm tra pg_last_wal_replay_lsn() đã đạt **ít nhất** mốc yêu cầu chưa.
5. Khi đạt mốc, mở **snapshot/transaction mới** trên chính standby đã xác nhận, rồi thực hiện SELECT.
6. Nếu không đạt trước deadline, fallback primary hoặc trả trạng thái cần thử lại theo contract; không đợi vô hạn.
7. Nếu leader đã failover hoặc timeline đổi, **không so LSN từ timeline cũ như một token toàn cục**. Xác minh topology và dùng cơ chế điều phối thích hợp.

Ví dụ phần kiểm tra trên standby:

~~~sql
SELECT
    pg_last_wal_replay_lsn() AS replay_position,
    pg_last_wal_replay_lsn() >= CAST(:requiredLsn AS pg_lsn)
        AS reached_required_position;
~~~

Cú pháp tham số :requiredLsn chỉ mô tả placeholder do tầng Java/SQL library bind. Mốc requiredLsn phải được cấp từ nguồn đáng tin cậy và xác thực kiểu pg_lsn hợp lệ.

**Giới hạn quan trọng:** mốc lấy sau commit có thể bao gồm WAL của những transaction khác xảy ra giữa commit và lần lấy mốc, nên yêu cầu standby replay xa hơn mức tối thiểu cần thiết. Điều đó là bảo thủ nhưng không làm nó thành bằng chứng cho các commit ở database khác. Nếu request cần nhiều hệ thống, một LSN của PostgreSQL không đủ.

### 11.1. Pseudocode với deadline và fallback

~~~java
public OrderView readAtLeastVersion(
        long tenantId,
        UUID orderId,
        long minVersion) {

    // Mỗi lần thử query replica phải có scope/snapshot phù hợp.
    for (int attempt = 0; attempt < 3; attempt++) {
        try {
            OrderView view = replicaReader.find(tenantId, orderId);
            if (view != null && view.version() >= minVersion) {
                return view;
            }
        } catch (ReplicaUnavailableException ex) {
            // Metric + có thể fallback ngay, theo policy.
            break;
        }

        // Backoff nhỏ và deadline tổng, không block vô hạn.
    }

    return primaryReader.findRequired(tenantId, orderId);
}
~~~

Đây là pseudocode ứng dụng, không phải implementation Java hoàn chỉnh; ReplicaUnavailableException và các reader cần được định nghĩa theo ứng dụng. Đối với cùng một aggregate, version so sánh được khi mọi writer tăng version đúng quy tắc.

Nếu đang đọc **hai đơn hàng khác nhau hoặc dữ liệu tổng hợp**, version của order O7 không chứng minh replica đã có toàn bộ những thay đổi liên quan tới một transaction khác. Khi ấy cần giao thức tiến độ thích hợp hoặc đọc primary.

### 11.2. LSN threshold chưa đủ nếu snapshot cũ

Giả sử standby đã replay tới requiredLsn nhưng GET chạy trong transaction REPEATABLE READ có snapshot tạo **trước** mốc replay. Câu SELECT vẫn có thể không thấy commit cần thiết. Vì vậy không chỉ cần “replica đạt mốc” mà còn cần **đọc bằng snapshot đủ mới** trên cùng replica.

Đây là lỗi tinh vi trong những hệ thống tái sử dụng transaction dài hoặc connection có state không được reset.

## 12. Synchronous replication có xóa hết stale reads không?

Không nên suy “bật replication đồng bộ = mọi read replica luôn có dữ liệu mới nhất”. Cần xác định **standby nào được chờ** và **mốc nào được chờ** tại thời điểm COMMIT.

Ở PostgreSQL, các chế độ synchronous_commit thường gặp có ý nghĩa khái quát sau:

| Chế độ | Mốc chờ cục bộ và/hoặc standby | Ý nghĩa với đường đọc |
|---|---|---|
| off | Có thể ACK trước khi WAL commit được flush cục bộ | Không dùng ACK làm bảo đảm durability cục bộ mạnh |
| local | Chờ WAL commit được flush trên primary | Replica vẫn có thể trễ |
| on | Chờ flush local và, khi cấu hình synchronous standby có hiệu lực, chờ WAL flush ở standby được chọn | Standby được chờ đã flush, nhưng chưa chắc đã **replay** để SELECT nhìn thấy |
| remote_write | Với synchronous standby tương ứng, chờ standby ghi WAL tới OS | Chưa phải remote durable flush, cũng chưa bảo đảm read visibility |
| remote_apply | Khi có synchronous standby được cấu hình phù hợp, chờ standby apply transaction | Có thể giúp standby được chờ thấy commit trong snapshot mới, nhưng không bảo đảm mọi replica khác đã apply |

Các chế độ liên quan standby chỉ tạo bảo đảm từ xa khi **synchronous replication thực sự được cấu hình**, node đang tham gia đúng vai trò và điều kiện chờ được đáp ứng. Một tên cấu hình không tự chứng minh có standby sẵn sàng ở mọi thời điểm.

### 12.1. Đồng bộ với một replica không đồng nghĩa mọi replica đồng bộ

Giả sử primary có ba replica A, B, C, nhưng chính sách commit chỉ cần một standby phù hợp xác nhận. Tại thời điểm primary ACK:

- Replica A đã đạt mốc yêu cầu.
- Replica B và C có thể vẫn trễ.
- Load balancer có thể đưa GET tới B.

**Kết quả:** GET vẫn thấy dữ liệu cũ dù giao dịch đã hoàn tất theo chính sách synchronous commit. Nếu cần đọc từ replica có bảo đảm, routing phải biết **đúng node đã đạt mốc** hoặc kiểm tra tiến độ.

### 12.2. remote_apply không phải snapshot toàn hệ thống

Ngay cả khi standby A đã apply commit trước ACK, một transaction SELECT trên A đã giữ snapshot từ trước có thể tiếp tục thấy bản cũ theo isolation level. Dữ liệu trong cache, replica B hoặc database của dịch vụ khác vẫn có thể cũ.

Synchronous replication chủ yếu là lựa chọn **độ bền/độ sẵn sàng và mốc xác nhận replication**; yêu cầu đọc cuối cùng vẫn cần routing và snapshot chính xác.

### 12.3. Đánh đổi latency và availability

Khi primary phải chờ remote flush/apply, latency commit bị ảnh hưởng bởi mạng, storage và replay. Nếu standby bắt buộc bị gián đoạn, commit có thể phải chờ, làm giảm availability ghi theo chính sách. Đây không chỉ là quyết định tối ưu đọc mà còn liên quan tới RPO, RTO và độ sẵn sàng của hệ thống.

## 13. Failover: replica trở thành primary có thể thay đổi câu trả lời

Một failure scenario:

~~~text
T1 COMMIT order=CONFIRMED trên primary P
P trả ACK thành công
Standby S còn trễ, chưa replay T1
P mất vĩnh viễn
S được promote làm primary mới
GET order trên S -> vẫn có thể PENDING
~~~

Với asynchronous replication, nếu replica được promote chưa có transaction, một commit từng được primary ACK có thể **không tồn tại trên primary mới**. Đây là rủi ro mất dữ liệu qua failover, khác với tình huống replica chỉ tạm thời chưa replay rồi sẽ bắt kịp.

### 13.1. Phân biệt lag tạm thời và data loss sau failover

| Hiện tượng | Replica còn kết nối primary cũ | Replica được promote thành primary mới |
|---|---|---|
| Chưa nhận một commit | Có thể bắt kịp nếu WAL còn và liên kết phục hồi | Nếu nguồn WAL không còn, commit có thể không xuất hiện |
| Đọc PENDING sau khi primary trả CONFIRMED | Thường là stale read | Có thể phản ánh dữ liệu đã mất trong quá trình failover |
| Cách khắc phục | Chờ replay hoặc đọc primary cũ | Cần kiểm tra RPO, log recovery, đối soát và nguồn authoritative mới |
| Watermark từ primary cũ | Có thể so với standby cùng timeline hợp lệ | Không tự dùng lại giữa các timeline/leader epoch |

Không nên đưa logic “không thấy trên replica thì tạo lại” vào application một cách mù quáng. Sau failover, có thể cần đối soát theo business key và hợp đồng durability của cluster.

### 13.2. Fencing và ngăn hai primary cùng ghi

Trong một topology mới promote standby, hệ thống phải bảo đảm primary cũ không tiếp tục nhận ghi như một leader độc lập nếu nó hoạt động trở lại. Đây là vấn đề **split-brain** và fencing trong failover orchestration.

Ứng dụng cần dùng endpoint/driver/pool được cấu hình để chuyển sang primary hiện hành và xử lý kết nối cũ phù hợp. Connection đang mở tới node cũ có thể lỗi hoặc còn nhìn dữ liệu không còn là nguồn chuẩn. Không chỉ đổi DNS rồi giả định mọi connection pool lập tức dùng leader mới.

### 13.3. RPO và RTO

- **RPO:** mức mất dữ liệu chấp nhận khi phải khôi phục sau sự cố. Replication bất đồng bộ có thể có RPO khác 0, tùy tình huống và chính sách.
- **RTO:** thời gian chấp nhận để dịch vụ phục hồi sau lỗi. Tăng yêu cầu đồng bộ và cơ chế xác nhận có thể ảnh hưởng latency, failover, availability.
- **Replica lag:** là một tín hiệu rủi ro liên quan RPO, nhưng **không đồng nghĩa RPO chính thức**. Cần tính đến miền lỗi, độ bền WAL, cách chọn replica promote, lưu trữ log và kịch bản thảm họa.

Một SLO đọc sau ghi không thể được thiết kế tách rời topology và các giới hạn failover mà hệ thống cam kết.

## 14. Fallback khi replica quá chậm hoặc không sẵn sàng

Đọc primary khi cần dữ liệu mới không chỉ là một if đơn giản. Nếu mọi request đều fallback primary cùng lúc, hệ thống có thể làm primary quá tải, khiến cả đường ghi bị chậm.

### 14.1. Chính sách theo use case

| Use case | Khi replica lag vượt ngưỡng | Khi primary cũng quá tải |
|---|---|---|
| Trang catalog cho phép stale | Có thể trả stale kèm mốc cập nhật, hoặc chuyển replica tốt hơn | Tiếp tục stale trong giới hạn hoặc trả lỗi phù hợp |
| GET order ngay sau POST | Fallback primary hoặc chờ ngắn theo watermark | Trả trạng thái đang đồng bộ/503 theo contract, không tự báo dữ liệu sai |
| Kiểm tra tồn kho trước xác nhận | Thực hiện UPDATE có điều kiện tại authoritative DB | Không xác nhận bán hàng khi không thể bảo vệ invariant |
| Dashboard báo cáo | Hiển thị thời điểm dữ liệu, đợi/bỏ qua một số phần theo policy | Giới hạn truy vấn, tách report job hoặc trả lỗi |
| Kiểm tra quyền bị thu hồi | Không tin replica/cache stale | Fail-closed hoặc cơ chế kiểm tra quyền có bảo đảm riêng |
| Đối soát trạng thái sau COMMIT timeout | Đọc nguồn authoritative/leader hiện tại, không từ stale replica | Giữ trạng thái UNKNOWN và kiểm tra lại, không retry bằng ID mới |

### 14.2. Chống fallback storm

Một thiết kế thực tế có thể kết hợp:

- Deadline và giới hạn thời gian chờ replay cho mỗi request.
- Giới hạn concurrency, retry budget, backoff có jitter.
- Circuit breaker riêng cho các replica lỗi.
- Rate limit/bulkhead bảo vệ primary.
- Chia mức ưu tiên: giao dịch cần đúng được ưu tiên hơn truy vấn báo cáo lớn.
- Cache/response stale chỉ cho các use case được phép.
- Queue hoặc workflow bất đồng bộ cho những request không bắt buộc trả kết quả tức thời.

Nếu primary có 100 connection khả dụng và 500 request đồng loạt fallback, việc đọc chính xác có thể biến thành một cuộc khủng hoảng tài nguyên. Định tuyến phải được đo và điều tiết theo năng lực thật.

### 14.3. Không “sửa” stale bằng cách retry SELECT vô hạn

Một vòng GET replica liên tục không có deadline có thể giữ thread, connection và tải DB, đặc biệt khi replica bị mất kết nối hoặc stopped replay. Cần định nghĩa rõ:

1. Chờ trong bao lâu?
2. Chờ phiên bản hoặc LSN nào?
3. Đọc trên replica nào?
4. Nếu hết deadline, được fallback primary hay phải báo UNKNOWN?
5. Có được đọc một phiên bản cũ hơn trong mọi tình huống không?

Nếu không trả lời được những câu này, retry SELECT chỉ che lỗi thiết kế consistency.

## 15. Logging, tracing và SLO cho đường đọc

Các chỉ số cần phân biệt **chất lượng đường đọc** với **tiến độ replication**.

| Metric | Ý nghĩa | Tác dụng |
|---|---|---|
| Replica receive/flush/replay LSN | Tiến độ WAL theo mốc | Phát hiện nghẽn mạng, flush, replay |
| WAL gap theo byte | Khoảng cách tương đối giữa các mốc | Phát hiện backlog lớn, không coi là lag tính bằng giây |
| Replication streaming state | Có đang kết nối đúng primary không? | Chẩn đoán disconnect/reconnect |
| Read latency p50/p95/p99 mỗi endpoint | Độ trễ từ góc nhìn người dùng | Tránh chọn replica chậm hơn primary |
| Read-your-writes violations | GET sau write không thấy phiên bản vừa commit | Đo trực tiếp lỗi hợp đồng |
| Stale version mismatch | Version đọc từ replica thấp hơn marker yêu cầu | Đo freshness theo object |
| Time to catch up | Từ mốc commit đến replica đạt watermark | Đo mốc ứng dụng thực sự cần |
| Primary fallback rate | Bao nhiêu lượt đọc phải rời replica | Theo dõi bão fallback và chi phí |
| Standby query cancellations | Số query bị hủy vì xung đột recovery | Xem cân bằng replay và báo cáo |
| Oldest transaction/query age | Query giữ snapshot lâu | Tìm truy vấn làm ảnh hưởng replay |
| Failover duration và RPO observed | Khả năng phục hồi theo kịch bản | Đối chiếu hợp đồng availability/durability |

### 15.1. Trace một read-after-write

Một trace hữu ích:

~~~text
requestId = R1
orderId   = O7
writePrimary = db-p
writeCommitResult = CONFIRMED
expectedVersion = 12

followupRead:
    endpoint = db-r2
    observedVersion = 11
    routingPolicy = REPLICA_OK
    fallback = PRIMARY
    returnedVersion = 12
~~~

Không ghi số thẻ, mật khẩu, token kết nối hoặc toàn bộ payload nhạy cảm vào log. Metadata như endpoint alias, version, requestId, source role và stale decision thường đủ để chẩn đoán.

### 15.2. SLO phải mô tả điều người dùng cảm nhận

Một SLO như “replay_lag trung bình dưới 2 giây” không đủ đảm bảo GET ngay sau POST không stale. Một yêu cầu cụ thể hơn:

- 100% request đọc trạng thái giao dịch của chính actor sau write phải đáp ứng read-your-writes theo giao thức routing đã công bố.
- Phần lớn lượt đọc catalog có tuổi dữ liệu dưới ngưỡng freshness chấp nhận.
- Báo cáo hiển thị as-of timestamp và có cảnh báo nếu chậm quá ngưỡng.
- Tất cả luồng reserve tồn kho quyết định trên transaction authoritative, không dựa riêng vào replica.

Giữ mục tiêu freshness và mục tiêu latency/availability ở cùng một bảng đánh giá, vì tăng độ nhất quán có thể làm chậm commit hoặc giảm khả năng phục vụ khi replica lỗi.

## 16. Kiểm thử replication lag một cách có kiểm soát

Không thể chứng minh read-your-writes bằng unit test chỉ mock repository. Cần dựng topology thật hoặc môi trường tích hợp phù hợp với DBMS đang dùng.

### 16.1. Kịch bản 1: commit ở primary, standby chưa replay

Trên staging với PostgreSQL streaming standby, có thể tạm **pause WAL replay trên standby** bằng công cụ/quyền quản trị phù hợp, sau đó:

1. Xác nhận standby ở trạng thái recovery.
2. Tạm dừng replay trong môi trường thử nghiệm, không phải production.
3. COMMIT update Order O7 version 12 ở primary.
4. Query bằng kết nối mới trên standby, kiểm tra vẫn thấy version trước đó.
5. Ghi nhận replay LSN và thời gian.
6. Cho standby replay tiếp và đợi tới marker đã chọn.
7. Query bằng snapshot mới, kiểm tra thấy version 12.
8. Xác minh hệ thống đã hoàn nguyên thiết lập và workload bình thường.

Lệnh PostgreSQL hỗ trợ thao tác pause/resume trong môi trường được phép:

~~~sql
-- Chỉ chạy trên standby thử nghiệm theo runbook phù hợp:
SELECT pg_wal_replay_pause();
-- ... test query ...
SELECT pg_wal_replay_resume();
~~~

Một số môi trường quản lý database không cấp quyền dùng các hàm này. Nếu không được phép, có thể mô phỏng chậm replication bằng network fault injection hoặc một topology kiểm thử riêng, nhưng phải xác minh mốc ngắt thực sự tạo lag.

**Không làm trên production:** pause replay có thể khiến dữ liệu đọc cũ, tăng backlog WAL và tác động tới RPO/availability.

### 16.2. Kịch bản 2: đọc lùi giữa hai replica

~~~text
Replica A đã replay version 12
Replica B mới replay version 11

GET O7 qua A -> version 12
GET O7 qua B -> version 11
~~~

Kiểm tra middleware:

- Không vi phạm monotonic reads nếu use case yêu cầu.
- Khi đã nhận minVersion=12, GET tại B phải đợi, chọn node khác, fallback primary hoặc trả kết quả có kiểm soát.
- Việc đổi endpoint qua DNS/pool không làm mất thông tin session consistency.
- Không dùng nhầm replica có timeline từ leader cũ sau failover.

### 16.3. Kịch bản 3: snapshot được mở quá sớm

Mở transaction REPEATABLE READ trên standby, thực hiện SELECT trước khi commit mới được replay. Đợi WAL bắt kịp, rồi SELECT lại trong **cùng transaction**; so với SELECT trong **transaction mới**.

Dùng test này để chứng minh rằng replay progress đạt watermark không tự thay đổi snapshot đã tạo. Đây là điểm dễ sai trong những kiến trúc dùng một transaction read-only để chạy nhiều thao tác.

### 16.4. Kịch bản 4: failover và dữ liệu đã ACK

Trong môi trường fault injection được quản lý, thực hiện một commit trên primary, làm replica trễ và mô phỏng mất primary. Nếu hệ thống promote một replica chưa có commit đó, cần biết rõ:

- Dữ liệu nào xuất hiện trên leader mới.
- RPO thực tế đã đạt hay vi phạm mục tiêu.
- Application nhận biết leader mới bằng cách nào.
- Kết nối cũ có bị loại khỏi pool không.
- Idempotency và reconciliation xử lý yêu cầu đã ACK nhưng không còn trên replica mới thế nào.

Không tự tạo sự cố mất dữ liệu trên production chỉ để kiểm thử khả năng phục hồi.

### 16.5. Ma trận kiểm thử

| Trường hợp | Điều cần assert |
|---|---|
| Replica đuổi kịp primary | GET qua replica mới thấy record sau replay |
| GET ngay sau POST khi lag cao | Không trả sai hợp đồng read-your-writes |
| Hai replica khác tiến độ | Không đọc lùi nếu đã hứa monotonic reads |
| Read-only transaction giữ snapshot cũ | Không nhầm replay tiến lên với snapshot tự cập nhật |
| Replica unavailable | Fallback có deadline, không gây storm |
| Replica query bị hủy do recovery conflict | Lỗi được phân loại, không retry vô hạn |
| Commit timeout | Đọc đối soát authoritative, không tạo request nghiệp vụ mới |
| Failover timeline thay đổi | Không so LSN mù quáng giữa các leader epoch |
| Read từ cache nằm trước replica | Có thể xác định stale nằm ở cache hay replica |
| Kiểm tra quyền/tồn kho | Không quyết định cuối cùng từ dữ liệu stale |

**Chú ý với bài test pause replay:** nếu primary đang chờ chính standby đó theo chế độ remote_apply, một COMMIT có thể phải chờ cho tới lúc standby resume replay. Để tái hiện tình huống “primary đã ACK, standby chưa apply”, phải chọn cấu hình kiểm thử thực sự cho phép primary commit trước replay, chẳng hạn một standby bất đồng bộ hoặc chính sách không chờ remote apply. Không kết luận test bị treo là lỗi ứng dụng khi chính cấu hình replication khiến COMMIT phải đợi.

## 17. Case study: hành trình đặt hàng, đọc và hủy đơn

### 17.1. Bối cảnh

Một hệ thống thương mại điện tử có:

- PostgreSQL primary lưu orders, order_items và outbox.
- Hai PostgreSQL read replica phục vụ phần lớn GET.
- Redis cache bản tóm tắt sản phẩm.
- Java Order Service dùng Spring JdbcTemplate và connection pool riêng cho primary/replica.
- API POST /orders xác nhận ghi đơn sau local transaction.
- API GET /orders/{id} có thể được gọi ngay khi POST trả kết quả.

Yêu cầu:

1. Sau khi POST trả 201, chính người dùng đó phải đọc thấy đơn vừa tạo.
2. Danh sách đơn cũ có thể trễ một ít để giảm tải.
3. Khi hủy đơn, không được dùng trạng thái stale để bỏ qua optimistic version hoặc xác nhận hoàn tiền sai.
4. Khi replica hỏng, primary vẫn cần giữ đủ năng lực cho lệnh ghi.
5. Khi failover, phải biết rõ mức RPO và xử lý được thao tác kết quả chưa rõ.

### 17.2. Thiết kế đường ghi

~~~text
POST /orders (requestKey=R)
    |
    v
Application Service
    |
    +-- BEGIN transaction ở primary
    +-- INSERT requestKey R (UNIQUE theo tenant)
    +-- INSERT orders, order_items
    +-- INSERT outbox event
    +-- COMMIT theo policy durability
    |
    v
HTTP 201 + orderId + trạng thái/phiên bản authoritative
~~~

Không sử dụng replica để xác định requestKey R có tồn tại trong luồng tạo đơn cần idempotency: replica có thể chưa replay một attempt đã commit, khiến service tạo thêm tác động không mong muốn nếu đổi key hoặc bỏ qua unique constraint trên primary.

Nếu COMMIT gặp lỗi mạng và kết quả chưa rõ, client giữ cùng requestKey R. API đối soát tại leader authoritative và dùng UNIQUE/transaction để bảo vệ replay. Không tin một lần not found trên replica trễ là bằng chứng chưa tạo đơn.

### 17.3. Thiết kế đường đọc

~~~mermaid
flowchart TD
    A["GET /orders/O7"] --> B{"Nguồn đọc cần mới tới mức nào?"}
    B -->|Đọc sau write / cần latest| P["Đọc primary"]
    B -->|Cho phép eventual| R["Chọn replica đủ khỏe"]
    B -->|Có token minVersion| V{"Replica đạt phiên bản yêu cầu?"}
    V -->|Có| Q["SELECT với snapshot mới trên replica đó"]
    V -->|Chưa| W["Đợi ngắn có deadline"]
    W --> V
    W -->|Hết deadline| P
    R --> S["Trả dữ liệu kèm as-of khi phù hợp"]
    P --> T["Trả kết quả authoritative"]
    Q --> U["Trả kết quả >= phiên bản yêu cầu"]
~~~

Một implementation cần có điểm dừng rõ cho vòng đợi trong sơ đồ; nó không phải polling vô hạn. Từ “đủ khỏe” phải được định nghĩa bằng availability, tải và replication progress nếu use case yêu cầu.

### 17.4. Đường hủy đơn

~~~text
Client GET order v11 từ replica
Client gửi cancel(orderId, expectedVersion=11)
Primary đã có order v12 do một thao tác khác
UPDATE ... WHERE version=11 -> 0 rows
Application trả CONFLICT hoặc trạng thái nghiệp vụ chính xác
~~~

Đừng bỏ điều kiện version để tạo “trải nghiệm nhanh”. Nếu API GET phục vụ dữ liệu stale được chấp nhận, UI phải chuẩn bị tình huống write conflict và cho người dùng tải lại dữ liệu. Nếu hủy đơn là thao tác quan trọng, transaction trên primary mới quyết định được phép hủy hay không.

### 17.5. Quy trình xử lý khi replica lag tăng

1. Mức lag vượt ngưỡng cảnh báo: đánh dấu replica degraded trong read routing.
2. Đường đọc eventually consistent có thể chuyển replica khác hoặc trả dữ liệu stale có nhãn, tùy hợp đồng.
3. Đường đọc theo minVersion chờ trong deadline nhỏ rồi fallback primary có giới hạn.
4. Đường ghi vẫn dùng primary, với transaction idempotent.
5. On-call kiểm tra WAL receive/flush/replay, long query, I/O, network và topology.
6. Nếu phục hồi thất bại, thực hiện failover theo runbook và đối chiếu RPO/RTO.

Đây là xử lý **trên cả ứng dụng và hạ tầng**. Chỉ sửa một câu SQL không giải quyết được policy data freshness, và chỉ thêm replica không giải quyết được giao thức read-your-writes.

## 18. Những hiểu lầm và anti-pattern

| Nhận định | Vì sao không đúng | Cách thiết kế phù hợp |
|---|---|---|
| “COMMIT OK thì mọi replica đã thấy dữ liệu.” | ACK primary và replay của từng standby là các mốc khác | Đọc primary hoặc kiểm tra tiến độ |
| “Replica đã receive WAL thì SELECT thấy commit.” | Còn flush/replay và snapshot của câu đọc | Theo dõi replay LSN, mở snapshot mới |
| “Lag trung bình 20 ms đủ đảm bảo read-your-writes.” | Một request vẫn có thể rơi vào cửa sổ stale | Routing theo commit/version token |
| “@Transactional(readOnly=true) sẽ tự đưa SQL sang replica.” | Đây là transaction hint, không phải cấu hình endpoint | Explicit routing và test |
| “Read replica luôn nhanh hơn primary.” | Node replica có thể yếu, xa hoặc đang replay quá tải | Benchmark per-endpoint, tách workload |
| “Đọc qua replica để kiểm tra tồn kho trước khi trừ là đủ.” | Dữ liệu có thể cũ; invariant có thể bị phá | UPDATE nguyên tử trên authoritative DB |
| “Chỉ cần sleep 1 giây sau INSERT.” | Lag không có mức cố định | Watermark/deadline hoặc primary |
| “Replay LSN bắt kịp thì transaction đang mở phải thấy dữ liệu mới.” | REPEATABLE READ giữ snapshot cũ | Tạo snapshot mới sau replay |
| “Một replica sync là mọi replica sync.” | Synchronous standbys chỉ là tập được chọn theo policy | Route đúng standby đạt mốc |
| “Standby không thấy order nên primary chắc rollback.” | Replica có thể chậm hoặc failover mất commit | Đối soát nguồn authoritative |
| “Lấy pg_last_xact_replay_timestamp trừ giờ hiện tại là lag tuyệt đối.” | Hệ thống idle vẫn làm hiệu này tăng | Kết hợp tiến độ WAL và workload |
| “Thêm nhiều replica luôn tăng khả năng chịu tải.” | Query và replay tranh CPU/I/O, nhiều pool tạo thêm chi phí | Capacity planning và đo thực tế |
| “Synchronous replication thay thế backup.” | DELETE nhầm có thể sao chép đồng bộ | Backup lịch sử và diễn tập restore |
| “LSN vẫn so được nguyên xi sau mọi failover.” | Timeline và leader epoch có thể đổi | Reset/đối chiếu token theo topology |

## 19. Bài tập tự kiểm tra

### Bài A — Đơn vừa tạo nhưng GET trả 404

Client POST /orders nhận 201 và orderId O7. Ngay sau đó, GET qua replica trả 404.

**Hỏi:** Có thể kết luận đơn chưa được ghi không? Thay đổi nào ở API giúp người dùng không gặp lỗi này?

**Gợi ý:** Không. Replica có thể chưa replay INSERT. Dùng primary cho GET sau ghi, hoặc trả trạng thái đã commit từ POST, hoặc yêu cầu replica đạt watermark/version trước khi trả 404. Không negative-cache 404 từ replica quá lâu.

### Bài B — Hai replica trả kết quả đi lùi

GET lần đầu tới Replica A thấy order v12. GET lần sau tới Replica B thấy order v11.

**Hỏi:** Tính chất nhất quán nào bị vi phạm? Khắc phục bằng cách nào?

**Gợi ý:** Monotonic reads bị vi phạm đối với phiên đọc liên tục của actor. Dùng minVersion token để chỉ chọn replica đã đạt ít nhất v12, hoặc đọc primary. Session affinity là một lựa chọn nhưng phải xử lý failover và trạng thái phiên.

### Bài C — WAL nhận xong nhưng GET vẫn cũ

Standby pg_last_wal_receive_lsn() đã vượt mốc commit, còn pg_last_wal_replay_lsn() vẫn nhỏ hơn mốc.

**Hỏi:** Có thể trả kết quả từ standby để đảm bảo read-your-writes chưa?

**Gợi ý:** Chưa. WAL được nhận không chứng minh đã apply; cần replay đạt mốc và SELECT trong snapshot mới. Nếu hết deadline, fallback primary.

### Bài D — Transaction REPEATABLE READ giữ snapshot

Một transaction read-only trên standby đọc order v6. Sau đó standby replay đến v7, nhưng SELECT tiếp theo trong cùng transaction vẫn trả v6.

**Hỏi:** Có phải replay đã thất bại?

**Gợi ý:** Không nhất thiết. Snapshot REPEATABLE READ được giữ ổn định. Kiểm tra bằng một transaction mới sau khi replay đạt mốc.

### Bài E — Hứa hẹn “đồng bộ” chưa đủ

Primary chờ Replica A flush WAL nhưng GET được load balance tới Replica B chưa apply.

**Hỏi:** Cấu hình synchronous commit có bảo đảm GET thấy ghi mới không?

**Gợi ý:** Không. A flush chưa chắc apply, còn B không nhất thiết là standby được chờ. Phải xác định đúng mốc và đúng replica, hoặc đọc primary.

### Bài F — Đo lag lúc hệ thống không có ghi

Primary không có transaction mới trong một giờ. Replica đã bắt kịp toàn bộ WAL. pg_last_xact_replay_timestamp() vẫn là thời điểm cách đây một giờ.

**Hỏi:** Có thể nói replica lag một giờ không?

**Gợi ý:** Không. Timestamp mô tả transaction replay cuối; hệ thống idle có thể không tạo transaction mới để cập nhật nó. Cần quan sát LSN và tiến độ replication.

### Bài G — Xác nhận bán dựa trên replica

Replica báo available=8 trong khi primary còn 1. Hai request muốn mua 1 món cùng lúc.

**Hỏi:** Có thể xác nhận hai đơn chỉ bằng kiểm tra ở replica không?

**Gợi ý:** Không. Đường ghi phải bảo vệ bất biến bằng UPDATE giảm tồn có điều kiện trên nguồn authoritative cùng transaction phù hợp. Replica chỉ nên làm nguồn gợi ý nếu chấp nhận stale.

### Bài H — Failover làm mất commit đã ACK

Primary P đã ACK transaction T, standby S chưa có WAL T. P mất vĩnh viễn và S được promote.

**Hỏi:** Vì sao đọc primary mới không thấy T? Cần đánh giá yếu tố vận hành nào?

**Gợi ý:** Với asynchronous replication, S có thể chưa có commit đã được ACK ở P; đây có thể là mất dữ liệu sau failover. Xem RPO, cách chọn standby, WAL lưu trữ, replication policy, fencing và reconciliation.

### Bài I — Read-only annotation

Một service khai báo @Transactional(readOnly=true), nhưng connection thực tế lấy từ primaryJdbcTemplate.

**Hỏi:** Có tự chuyển sang replica không? Điều gì nên được kiểm thử?

**Gợi ý:** Không. Annotation không thay JDBC endpoint. Cần cấu hình routing/DataSource/transaction manager cụ thể và kiểm tra thời điểm mượn connection, propagation và scope transaction.

### Bài J — Fallback storm

Replica bị ngắt. Tất cả GET đồng loạt chuyển primary, khiến primary hết connection và đường ghi timeout.

**Hỏi:** Tăng maximumPoolSize có giải quyết gốc rễ không?

**Gợi ý:** Không nhất thiết. Cần bulkhead, giới hạn fallback, priority, cache stale cho use case chấp nhận, circuit breaker và capacity planning trên toàn bộ instance.

## 20. Checklist đưa đường đọc replica vào production

- [ ] Xác định primary và replica trong topology hiện hành; biết cách leader thay đổi khi failover.
- [ ] Biết cơ chế replication là bất đồng bộ hay đồng bộ và **mốc** được chờ khi ACK.
- [ ] Không đồng nhất received/flush WAL với replay và khả năng SELECT nhìn thấy commit.
- [ ] Đã phân loại use case chấp nhận eventual consistency và use case yêu cầu read-your-writes.
- [ ] Đã xác định những đọc phải đến nguồn authoritative để giữ bất biến.
- [ ] Có chính sách routing rõ: explicit DataSource, transaction manager và lựa chọn theo request.
- [ ] Không mặc định @Transactional(readOnly=true) tự chọn replica hoặc bảo đảm snapshot mới nhất.
- [ ] Với read-after-write, có primary routing, version token hoặc WAL watermark đúng topology.
- [ ] Nếu đợi watermark, có deadline, fallback, cùng replica và snapshot đủ mới.
- [ ] Không so token LSN một cách mù quáng qua failover/timeline.
- [ ] Đã xét monotonic reads khi load balance giữa nhiều replica tiến độ khác nhau.
- [ ] Không dùng một lần not found trên replica để kết luận nghiệp vụ chưa commit.
- [ ] Đã xác định retry/idempotency khi write ACK mất hoặc commit outcome chưa rõ.
- [ ] Có metric WAL receive/flush/replay, query latency, replication state và route fallback.
- [ ] Không diễn giải pg_last_xact_replay_timestamp như lag thời gian tuyệt đối khi cluster idle.
- [ ] Có chính sách xử lý replica query conflict, long-running snapshot và replay backlog.
- [ ] Fallback sang primary có giới hạn concurrency để tránh làm nghẽn đường ghi.
- [ ] Failover runbook bao gồm fencing, connection pool reset, RPO/RTO và reconciliation.
- [ ] Có test read-after-write, monotonic reads, stale 404, snapshot cũ và lỗi replica.
- [ ] Đã kiểm thử workload/độ trễ trong môi trường gần production, không chỉ unit test.

**Ghi nhớ:** một replica có thể rất hữu ích cho quy mô đọc nhưng nó phản ánh **một tiến độ riêng** của dữ liệu. Độ trễ bản sao không chỉ là số giây hiển thị trên dashboard: nó quyết định liệu một SELECT có quan sát được commit mà API vừa xác nhận hay không. Thiết kế persistence Java đáng tin cần tách rõ quyền ghi authoritative, hợp đồng đọc theo use case, tiến độ replay, snapshot, failover và cơ chế fallback có giới hạn.

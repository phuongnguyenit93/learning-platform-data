# Đọc sau ghi, tính nhất quán và tác động đến thiết kế ứng dụng

## 1. Vì sao người dùng vừa lưu dữ liệu nhưng đọc lại vẫn thấy giá trị cũ?

Khi ứng dụng chạy trên một máy chủ cơ sở dữ liệu duy nhất, đường đi của thao tác ghi và đọc thường tương đối rõ: ứng dụng gửi lệnh tới database, giao dịch commit, sau đó truy vấn tiếp theo đọc trạng thái đã commit. Khi hệ thống mở rộng, dữ liệu có thể được sao chép sang nhiều replica, cache, search index, materialized view hoặc read model riêng. Các thành phần này cập nhật ở những thời điểm khác nhau.

Vì vậy, một tình huống thường gặp là người dùng cập nhật địa chỉ giao hàng, nhận phản hồi thành công, rồi ngay lập tức tải lại trang nhưng vẫn thấy địa chỉ cũ. Lệnh ghi có thể đã commit trên primary, trong khi replica chưa replay log; request đọc được định tuyến sang replica đang trễ; cache vẫn giữ bản cũ; hoặc read model phục vụ màn hình chưa xử lý sự kiện cập nhật.

Hiện tượng này liên quan đến **read-after-write consistency** (tính nhất quán đọc sau ghi), một bảo đảm về thứ tự và khả năng nhìn thấy dữ liệu sau khi ghi. Nó là một phần của bài toán tính nhất quán trong hệ thống mở rộng. Thiết kế ứng dụng cần xác định người dùng hoặc tiến trình nào phải nhìn thấy kết quả vừa ghi, trong khoảng thời gian nào, và hệ thống sẽ chờ, định tuyến lại hay chấp nhận dữ liệu cũ.

Module DATABASE_PERFORMANCE rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Trong bối cảnh mở rộng hệ thống, hiểu tính nhất quán giúp lựa chọn primary/replica, cache, read model và chiến lược định tuyến mà vẫn giữ được latency và throughput phù hợp. Bài học này tập trung vào đọc sau ghi, các mức bảo đảm nhất quán, tác động của replication lag và cache, cùng những quyết định thiết kế API và ứng dụng.

## 2. Đọc sau ghi là gì?

### 2.1. Định nghĩa

Read-after-write (RAW), thường được gọi là read-your-writes, là bảo đảm rằng sau khi một client ghi dữ liệu và nhận xác nhận thành công, những lần đọc tiếp theo của chính client đó sẽ nhìn thấy giá trị vừa ghi hoặc một giá trị mới hơn theo thứ tự ghi.

Ví dụ:

1. Người dùng gửi lệnh UPDATE profiles SET display_name = 'Lan' WHERE id = 42.
2. Database commit giao dịch và API trả thành công.
3. Người dùng gọi GET /profiles/42.
4. Kết quả cần phản ánh display_name = 'Lan' hoặc một cập nhật mới hơn đã xảy ra sau đó.

Nếu bước 4 đọc được giá trị cũ, hệ thống chưa cung cấp read-your-writes trên đường đọc đó.

### 2.2. Phạm vi của bảo đảm

Read-your-writes thường là bảo đảm theo session, client, user hoặc một luồng nghiệp vụ. Nó không tự động có nghĩa mọi người dùng trên toàn hệ thống đều nhìn thấy thay đổi ngay lập tức. Một người dùng khác có thể vẫn đọc replica trễ nếu hệ thống chỉ yêu cầu nhất quán theo session.

Phạm vi phải được định nghĩa rõ:

- Cùng HTTP request hay các request kế tiếp?
- Cùng browser session, thiết bị, user hay access token?
- Có cần giữ bảo đảm qua nhiều service không?
- Khi request đi qua nhiều region hoặc shard, token nhất quán được truyền thế nào?
- Sau khi người dùng đăng xuất rồi đăng nhập lại, bảo đảm còn hiệu lực không?

Nếu không xác định phạm vi, ứng dụng có thể bảo đảm RAW trong một instance nhưng mất bảo đảm khi load balancer chuyển request sang instance hoặc replica khác.

### 2.3. RAW không đồng nghĩa với strong consistency toàn cục

Read-your-writes bảo đảm một client nhìn thấy cập nhật của chính mình. Nó không nhất thiết bảo đảm mọi client đều thấy cùng một thứ tự cập nhật tại cùng một thời điểm. Strong consistency hoặc linearizability là yêu cầu mạnh hơn: các thao tác phải có thể được xem như xảy ra theo một thứ tự toàn cục phù hợp với thời gian thực.

Một hệ thống có thể cung cấp read-your-writes cho từng session trong khi các session khác vẫn đọc dữ liệu cũ trong một khoảng thời gian. Điều này có thể là lựa chọn hợp lý nếu nghiệp vụ cần phản hồi nhanh nhưng không cần đồng bộ toàn cục cho mọi lần đọc.

## 3. Các mức và thuộc tính nhất quán thường gặp

Không nên gom mọi bảo đảm vào một khái niệm “eventual” hoặc “strong”. Các thuộc tính sau mô tả những điều khác nhau:

| Thuộc tính | Bảo đảm | Ví dụ |
|---|---|---|
| Read-your-writes | Client thấy các ghi trước đó của chính mình | Sau khi đổi tên hồ sơ, lần đọc tiếp theo thấy tên mới |
| Monotonic reads | Một client không quay ngược về phiên bản cũ hơn phiên bản đã từng đọc | Đã thấy trạng thái đơn hàng SHIPPED thì lần đọc sau không trở về PROCESSING |
| Monotonic writes | Các ghi của một client được áp dụng theo thứ tự gửi yêu cầu | Cập nhật địa chỉ lần 2 không bị áp dụng trước lần 1 |
| Writes-follow-reads / causal order | Ghi phụ thuộc vào dữ liệu đã đọc được giữ đúng quan hệ nhân quả | Sau khi đọc phiên bản 7, cập nhật tiếp theo được áp dụng trên phiên bản phù hợp |
| Eventual consistency | Nếu không có ghi mới và hệ thống tiếp tục hoạt động, các bản sao cuối cùng hội tụ | Replica hoặc search index dần nhận dữ liệu mới |
| Bounded staleness | Dữ liệu đọc có thể cũ nhưng độ cũ được giới hạn theo thời gian hoặc số phiên bản | Replica không chậm quá ngân sách đã định |
| Strong consistency / linearizability | Thao tác được quan sát theo thứ tự toàn cục phù hợp với thời gian thực | Đọc sau một ghi đã xác nhận ở bất kỳ client nào đều không thấy trạng thái trước ghi đó |

Một hệ thống có thể kết hợp nhiều thuộc tính. Ví dụ, đọc phân tích chấp nhận eventual consistency; màn hình chi tiết sau thao tác cập nhật yêu cầu read-your-writes; kiểm tra số dư để cho phép thanh toán có thể cần mức nhất quán mạnh hơn.

### 3.1. Monotonic reads khác read-your-writes

Read-your-writes nói về việc nhìn thấy các thay đổi do chính client tạo ra. Monotonic reads nói rằng sau khi client đã quan sát một phiên bản, các lần đọc tiếp theo không được trả về phiên bản cũ hơn.

Giả sử người dùng không ghi gì nhưng đọc trạng thái đơn hàng từ replica A và thấy SHIPPED. Request tiếp theo được gửi tới replica B đang chậm hơn và trả PROCESSING. Hệ thống vi phạm monotonic reads dù người dùng không thực hiện thao tác ghi.

Session affinity hoặc token phiên bản đã đọc có thể hỗ trợ monotonic reads. Chỉ ghim request vào một replica chưa chắc đủ nếu replica đó có thể failover sang node có trạng thái cũ hơn.

### 3.2. Eventual consistency không đặt ra thời hạn tự động

Eventual consistency chỉ nói các bản sao sẽ hội tụ khi hệ thống không còn ghi mới và quá trình truyền/áp dụng tiếp tục. Nó không tự bảo đảm dữ liệu mới xuất hiện trong 100 ms, 1 giây hay 1 phút. Nếu sản phẩm cần một giới hạn, phải định nghĩa bounded staleness hoặc freshness SLO và đo được nó.

### 3.3. Isolation trong transaction khác consistency giữa replica

READ COMMITTED, REPEATABLE READ và SERIALIZABLE mô tả cách các giao dịch tương tác với nhau trong một hệ quản trị theo semantics của engine. Chúng không tự bảo đảm request đọc từ replica hoặc cache khác sẽ nhìn thấy một giao dịch vừa commit ở primary.

Ngược lại, read-your-writes giữa các replica không thay thế isolation. Một ứng dụng vẫn cần transaction isolation phù hợp để tránh lost update, non-repeatable read hoặc write skew trong thao tác đồng thời.

## 4. Đường đi của một lần ghi trong hệ thống có replica

Một hệ thống primary/replica có thể có nhiều mốc thời gian:

~~~text
Client
  |
  | 1. Gửi lệnh ghi
  v
Primary database
  |
  | 2. Commit transaction / tạo log record
  | 3. Flush log theo durability policy
  | 4. Trả ACK cho client
  |
  +--------------------> Replica nhận log
                           |
                           | 5. Ghi/harden log ở replica
                           |
                           | 6. Replay/apply log vào dữ liệu đọc
                           v
                      Replica có thể đọc phiên bản mới

Client đọc lại
  |
  +----> Primary: thường thấy commit đã xác nhận
  |
  +----> Replica: chỉ thấy khi dữ liệu đã replay/apply
  |
  +----> Cache/read model: phụ thuộc invalidation hoặc cập nhật projection
~~~

Các mốc 2–6 không nhất thiết xảy ra đồng thời. Đặc biệt, nhận log, lưu log bền vững và replay log là những trạng thái khác nhau.

### 4.1. Commit trên primary

Primary xác nhận giao dịch sau khi đạt điều kiện durability đã cấu hình, ví dụ local WAL/redo log đã flush. Ở thời điểm đó, giao dịch có thể đã bền vững trên primary nhưng chưa được truyền tới replica.

### 4.2. Replica nhận log

Replica đã nhận được byte log qua network. Dữ liệu có thể mới nằm trong bộ đệm hoặc hàng đợi nhận, chưa chắc đã được lưu bền vững và chưa chắc có thể truy vấn như dữ liệu đã áp dụng.

### 4.3. Replica flush/harden log

Replica đã lưu log theo mức bền vững của nó. Điều này giúp bảo vệ log khi node gặp sự cố, nhưng với kiến trúc cần replay riêng, dữ liệu đọc trên replica vẫn có thể chưa phản ánh log đó.

### 4.4. Replica replay/apply log

Replica áp dụng thay đổi vào trạng thái database có thể đọc. Đây thường là mốc quan trọng đối với truy vấn trên read replica. Nếu ứng dụng chỉ kiểm tra replication transport hoặc log receive lag mà không kiểm tra replay/apply lag, nó có thể định tuyến đọc quá sớm.

### 4.5. Cache và read model là các bản sao khác

Ngay cả khi replica đã replay, cache ứng dụng, Redis, search index hoặc materialized view có thể vẫn giữ dữ liệu cũ. Read-after-write phải đi qua toàn bộ đường đọc thực tế, không chỉ replication database.

## 5. Replication lag và hiện tượng đọc dữ liệu cũ

### 5.1. Nguyên nhân lag

Replication lag có thể đến từ:

- Network RTT, packet loss, băng thông hoặc queue giữa primary và replica.
- Primary sinh WAL/redo nhanh hơn tốc độ replica nhận.
- Replica ghi log chậm do storage latency.
- Replica replay/apply chậm vì CPU, I/O hoặc xung đột với truy vấn đọc.
- Transaction lớn hoặc DDL tạo lượng log lớn.
- Replica bị pause, restart, failover hoặc phải catch up sau gián đoạn.
- Read workload trên replica cạnh tranh với apply worker.

Lag có thể thay đổi theo tải. Một replica có thể gần như bắt kịp vào giờ bình thường nhưng tụt lại trong đợt bulk load hoặc batch job.

### 5.2. Phân biệt transport lag và apply lag

Nếu log chưa đến replica, vấn đề nằm ở send/network/receive. Nếu log đã đến và flush nhưng chưa replay, vấn đề nằm ở apply. Hai loại lag cần cách xử lý khác nhau.

| Quan sát | Khả năng cần điều tra |
|---|---|
| Send queue tăng ở primary | Primary/network không gửi kịp |
| Receive lag tăng ở replica | Network hoặc receiver chậm |
| Log đã nhận nhưng replay LSN/GTID tụt | Apply worker, CPU, I/O hoặc conflict |
| Replica query latency tăng cùng apply lag | Read workload cạnh tranh với replication |
| Lag tăng sau transaction lớn | Log burst, apply transaction lớn hoặc commit ordering |

Không chỉ dùng một con số “replication lag seconds”. Một số hệ thống tính lag dựa trên timestamp của giao dịch cuối cùng; khi primary không có ghi mới, con số thời gian có thể gây hiểu nhầm. Hãy xem cả log position, queue size, receive/flush/replay progress và trạng thái apply.

### 5.3. Đọc replica có thể gây thêm lag

Truy vấn phân tích lớn trên replica có thể cạnh tranh CPU, memory và I/O với tiến trình replay. Một số engine có thể hủy query đọc dài để apply thay đổi; engine khác có thể trì hoãn replay hoặc để lag tăng. Cần đo workload đọc và replication cùng lúc, giới hạn query nặng hoặc dùng replica riêng cho phân tích.

## 6. Thiết kế đường đọc để bảo đảm read-your-writes

Không có một chiến lược duy nhất cho mọi ứng dụng. Các mẫu phổ biến:

### 6.1. Đọc từ primary sau khi ghi

Sau khi ghi thành công, định tuyến các lần đọc tiếp theo của session tới primary. Cách này đơn giản và thường dễ bảo đảm RAW nếu cùng một primary và transaction snapshot phù hợp.

Ưu điểm:

- Không phải chờ replica bắt kịp.
- Dễ giải thích với ứng dụng.
- Hữu ích cho các thao tác quan trọng ngay sau commit.

Nhược điểm:

- Tăng read load trên primary.
- Có thể làm mất lợi ích scale-out đọc.
- Cần biết session nào vừa ghi và khi nào có thể quay lại replica.
- Khi failover, cần bảo đảm node mới chứa giao dịch đã xác nhận theo durability policy.

Có thể ghim session vào primary trong một khoảng thời gian ngắn sau write, nhưng thời gian cố định không bảo đảm replica đã bắt kịp. Nếu cần chuyển về replica chính xác, dùng watermark/token hoặc kiểm tra freshness.

### 6.2. Sticky session hoặc session affinity

Load balancer hoặc tầng truy cập dữ liệu giữ các request liên tiếp của cùng session đi tới cùng node. Cách này có thể hỗ trợ session consistency nếu node đó là primary hoặc có trạng thái đủ mới.

Sticky session không tự bảo đảm RAW khi:

- Session được ghim vào một replica đang trễ.
- Load balancer đổi node khi restart/failover.
- Client mở nhiều thiết bị hoặc nhiều session.
- Một request ghi đi qua service A nhưng request đọc đi qua service B không chia sẻ affinity.

Vì vậy, affinity là một cơ chế định tuyến, không phải một bằng chứng nhất quán độc lập.

### 6.3. Chờ replica đạt watermark rồi mới đọc

Một cách scale-out đọc tốt hơn là gắn một token phiên bản vào phản hồi ghi. Token có thể là LSN, GTID, commit sequence, version number hoặc watermark tương đương. Khi đọc từ replica, ứng dụng hoặc data access layer chờ tới khi replica đã áp dụng ít nhất token đó.

Luồng khái niệm:

~~~text
1. Ghi vào primary
2. Commit thành công
3. Nhận token T đại diện vị trí/version của giao dịch
4. Đọc từ replica R
5. Kiểm tra applied_watermark(R) >= T
       |
       +-- Có: đọc từ R
       |
       +-- Chưa: chờ trong ngân sách hoặc fallback primary
~~~

Token cần gắn với đúng cluster, database, shard hoặc replication stream. Không so sánh LSN của hai cluster độc lập hoặc GTID thuộc các topology khác nhau nếu chưa có quy tắc chuyển đổi.

### 6.4. Chờ có giới hạn, sau đó fallback

Không nên chờ replica vô thời hạn. Thiết kế một ngân sách chờ phù hợp với SLO:

1. Poll hoặc dùng cơ chế wait native cho tới khi replica đạt token.
2. Dừng chờ khi hết deadline.
3. Nếu thao tác quan trọng, đọc từ primary hoặc trả trạng thái retryable theo hợp đồng API.
4. Ghi metric số lần phải fallback và thời gian replica catch-up.

Fallback primary tăng tải, vì vậy cần giới hạn concurrency và tránh retry storm. Nếu primary đang quá tải, có thể trả trạng thái “đang đồng bộ” hoặc retry có backoff thay vì đẩy mọi request về primary.

### 6.5. Dùng read model nhất quán theo phiên

Với CQRS, command side và query side có thể cập nhật không đồng bộ. Sau khi command thành công, API có thể trả operationId hoặc version; query side chỉ trả trạng thái mới khi projection đã xử lý tới version đó. Trong thời gian chờ, UI có thể hiển thị trạng thái đang cập nhật hoặc dùng dữ liệu command response làm bản tạm.

Không giả vờ projection đã cập nhật nếu mới chỉ ghi thành công ở command database. Phân biệt “command accepted/committed” với “read model caught up”.

## 7. Token nhất quán và watermark

### 7.1. Token là gì?

Token nhất quán biểu diễn một ranh giới mà đường đọc phải đạt hoặc vượt qua. Token có thể là:

- LSN/WAL position của một giao dịch.
- GTID hoặc tập GTID trong MySQL.
- Commit sequence/version do database hoặc tầng ứng dụng cấp.
- Event offset hoặc projection sequence trong hệ thống event-driven.
- Version number của một entity.

Token nên được tạo hoặc xác nhận sau khi giao dịch đã commit. Nếu lấy watermark trước commit, token có thể không đại diện cho thay đổi vừa ghi.

### 7.2. Token cần có phạm vi

Một token chỉ có ý nghĩa trong đúng luồng thứ tự của nó. Trong hệ thống sharding, một giao dịch ghi vào shard A không thể dùng LSN của A để kết luận shard B đã bắt kịp. Với giao dịch xuyên shard, có thể cần vector token gồm nhiều thành phần hoặc một cơ chế transaction coordinator.

Token cũng cần gắn với database lineage/epoch để tránh so sánh sai sau restore, rebuild topology hoặc failover sang cluster mới. Thiết kế đơn giản thường dùng token opaque do tầng data access quản lý thay vì để client tự diễn giải.

### 7.3. Token trong API

API có thể trả version trong response:

~~~json
{
  "profileId": 42,
  "displayName": "Lan",
  "consistencyToken": "opaque-version-token"
}
~~~

Client gửi token ở lần đọc kế tiếp, ví dụ qua header X-Read-After-Write. API gateway hoặc data access layer xác minh token và chọn primary/replica phù hợp.

Không đưa thông tin nhạy cảm vào token; không tin token do client tự sửa nếu token có thể ảnh hưởng định tuyến hoặc truy cập dữ liệu. Có thể ký token, giới hạn thời gian sống và ràng buộc token với user/session/tenant.

### 7.4. Token không thay thế authorization

Token chỉ điều khiển mức độ mới của dữ liệu được đọc. Mỗi lần đọc vẫn phải kiểm tra quyền truy cập, tenant boundary và chính sách bảo mật. Không dùng token của một người dùng để mở quyền đọc dữ liệu của người khác.

## 8. Ví dụ theo hệ quản trị

### 8.1. PostgreSQL streaming replication

Primary có thể lấy WAL position hiện tại sau khi commit bằng pg_current_wal_lsn(). Standby có thể quan sát vị trí đã nhận và đã replay qua pg_last_wal_receive_lsn() và pg_last_wal_replay_lsn().

Ví dụ trên primary, sau khi ứng dụng hoàn tất transaction:

~~~sql
SELECT pg_current_wal_lsn();
~~~

Trên standby, kiểm tra vị trí replay:

~~~sql
SELECT
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn;
~~~

Ứng dụng có thể so sánh replay position với token LSN của lần ghi. PostgreSQL cung cấp pg_wait_for_replay_lsn(lsn, timeout) trên standby ở các phiên bản hỗ trợ để chờ replay tới một LSN; hãy xác minh phiên bản và ngữ cảnh gọi. Nếu wait hết thời gian, data access layer có thể fallback sang primary.

Không nên dùng riêng pg_last_xact_replay_timestamp() để đo chính xác độ trễ trong mọi trường hợp. Khi primary không có giao dịch mới, timestamp của giao dịch replay gần nhất có thể cũ dù standby đang bắt kịp hoàn toàn. So sánh LSN và trạng thái WAL thường hữu ích hơn cho token của một write cụ thể.

### 8.2. MySQL với GTID replication

Trong topology GTID, GTID xác định giao dịch đã được thực thi. Ứng dụng hoặc tầng database có thể lấy thông tin GTID phù hợp sau commit, sau đó chờ replica thực thi tập GTID đó.

MySQL cung cấp WAIT_FOR_EXECUTED_GTID_SET(gtid_set, timeout) trong các phiên bản hỗ trợ. Hàm trả kết quả cho biết replica đã thực thi tập GTID hay hết thời gian chờ. Cần xác minh GTID set đại diện đúng giao dịch cần chờ và topology replication đang dùng.

Ví dụ minh họa việc chờ một tập GTID đã biết trên replica:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET('source_uuid:1-120', 2);
~~~

Chuỗi GTID trong ví dụ chỉ minh họa cú pháp, không phải giá trị dùng cho hệ thống thực. Ứng dụng phải lấy token thật từ transaction cần bảo đảm; không tự tạo khoảng GTID bằng cách đoán số thứ tự. Nếu timeout, fallback hoặc trả trạng thái retryable theo chính sách.

### 8.3. SQL Server Availability Groups

Trong Always On Availability Groups, synchronous-commit mode có thể chờ secondary harden log trước khi primary xác nhận commit theo điều kiện cấu hình. Tuy nhiên, harden log và redo log thành trạng thái dữ liệu có thể đọc là hai bước khác nhau. Readable secondary có thể vẫn có redo queue.

Do đó, “synchronous commit” không tự động đồng nghĩa mọi truy vấn đọc trên secondary ngay lập tức thấy thay đổi vừa commit. Nếu yêu cầu RAW nghiêm ngặt, có thể đọc từ primary hoặc dùng cơ chế kiểm tra trạng thái redo phù hợp. Theo dõi send queue, redo queue, synchronization state và wait của availability group.

### 8.4. Hệ thống cache và search index

Redis cache, Elasticsearch/OpenSearch, search service hoặc materialized view thường cập nhật qua event/CDC. Chúng có thể trễ độc lập với database replica. Một write có thể commit trên primary và được replica áp dụng, nhưng search index chưa nhận event.

Nếu API sau ghi đọc từ search index, cần một token hoặc trạng thái indexing riêng. Có thể trả kết quả command trực tiếp trong response, poll operation status, hoặc fallback sang database cho tới khi search projection bắt kịp.

## 9. Cache có thể phá vỡ read-after-write

### 9.1. Cache-aside

Trong cache-aside, ứng dụng đọc cache trước; nếu miss thì đọc database rồi ghi kết quả vào cache. Khi update, ứng dụng thường commit database rồi invalidate cache. Tuy nhiên, nếu invalidation chậm hoặc thất bại, request đọc có thể trả bản cũ.

TTL chỉ giới hạn thời gian tồn tại tối đa theo cấu hình; nó không bảo đảm RAW ngay sau commit. Nếu TTL là 30 giây, người dùng vẫn có thể thấy dữ liệu cũ trong khoảng đó.

### 9.2. Race giữa đọc và invalidate

Một tình huống đua:

1. Reader A cache miss và bắt đầu đọc giá trị cũ từ database.
2. Writer B cập nhật database và commit.
3. Writer B xóa cache key.
4. Reader A hoàn tất truy vấn cũ và ghi giá trị cũ vào cache sau khi key đã bị xóa.
5. Reader tiếp theo nhận giá trị cũ.

Chỉ “commit rồi delete cache” chưa chắc đủ nếu có reader đang tải dữ liệu cũ đồng thời. Cần cân nhắc versioned key, compare-and-set, fencing token, write-through có kiểm soát hoặc cơ chế cache invalidation có thứ tự.

### 9.3. Write-through và versioned cache

Write-through cập nhật database và cache theo một quy trình có kiểm soát. Nếu không có transaction phân tán, hai nơi vẫn có thể lệch khi một bước thành công còn bước kia thất bại. Versioned cache có thể dùng key hoặc value gắn với version của entity; reader không chấp nhận version thấp hơn token của write.

Một mẫu khác là ghi outbox trong cùng transaction database, sau đó consumer invalidate/update cache. Outbox bảo đảm sự kiện được ghi cùng transaction nghiệp vụ, nhưng consumer vẫn xử lý bất đồng bộ; vì vậy API cần cơ chế RAW trong khoảng event chưa được áp dụng.

### 9.4. Negative cache và cache ở nhiều tầng

Không chỉ giá trị cũ mới gây lỗi. Nếu một request trước cache kết quả “không tồn tại”, sau khi tạo bản ghi, negative cache có thể khiến GET vẫn trả 404. Browser cache, CDN, API gateway, ORM second-level cache và cache trong process cũng có thể giữ dữ liệu cũ.

Hãy vẽ toàn bộ đường đọc và xác định mỗi tầng có TTL, invalidation, versioning và bypass behavior thế nào. Xóa Redis key nhưng không xóa local cache ở từng instance vẫn có thể khiến người dùng thấy trạng thái cũ.

## 10. Transaction snapshot và đọc sau ghi

Ngay cả khi đọc từ cùng primary, một transaction snapshot đã mở trước khi giao dịch khác commit có thể tiếp tục nhìn thấy phiên bản cũ theo isolation level. Đây là hành vi isolation, không phải replication lag.

Ví dụ:

1. Transaction A bắt đầu ở mức snapshot/repeatable read và đọc số dư.
2. Transaction B cập nhật số dư rồi commit.
3. Transaction A đọc lại trong cùng snapshot.
4. Transaction A có thể vẫn thấy số dư theo snapshot ban đầu.

Một transaction thường nhìn thấy các thay đổi của chính nó, nhưng không nhất thiết nhìn thấy commit mới của transaction khác nếu snapshot không được làm mới. Nếu ứng dụng cần thấy cập nhật mới từ transaction khác, có thể cần bắt đầu transaction mới hoặc dùng isolation phù hợp.

READ COMMITTED thường tạo snapshot theo statement trong nhiều engine MVCC, nhưng semantics khác nhau theo hệ quản trị. Không dựa vào tên isolation level mà bỏ qua tài liệu cụ thể.

Khi điều tra RAW, hãy ghi lại:

- Request đọc có dùng cùng transaction với request ghi không?
- Transaction snapshot được tạo lúc nào?
- Có connection pool reset transaction đúng không?
- Query có đọc từ replica hoặc cache không?
- Có ORM persistence context hoặc second-level cache trả entity cũ không?

## 11. CQRS, event-driven và read model bất đồng bộ

### 11.1. Command side và query side

CQRS tách mô hình ghi (command model) khỏi mô hình đọc (query model). Command side xác thực và commit thay đổi; event hoặc CDC cập nhật một hay nhiều read model. Cách này giúp tối ưu schema và scale đọc theo nhu cầu, nhưng tạo độ trễ đồng bộ.

Một command trả thành công có thể chỉ xác nhận dữ liệu đã commit ở command database. Search index, dashboard hoặc query projection chưa chắc đã cập nhật. API cần công bố trạng thái rõ ràng.

### 11.2. Outbox để không mất sự kiện

Nếu ứng dụng commit dữ liệu rồi gửi message riêng, có thể xảy ra:

- Database commit thành công nhưng publish message thất bại.
- Message publish thành công nhưng transaction database rollback.

Transactional outbox ghi dữ liệu nghiệp vụ và event record trong cùng transaction. Worker đọc outbox rồi publish; consumer idempotent xử lý event. Cách này giảm nguy cơ mất event, nhưng không biến projection thành đồng bộ tức thời.

### 11.3. Projection version và read-your-writes

Mỗi event hoặc entity có thể mang version tăng dần. Query service theo dõi version đã xử lý. Sau command, API trả version mong đợi; client hoặc gateway chỉ đọc projection khi applied_version >= expected_version.

Nếu projection chưa kịp:

- Trả trạng thái processing cùng operation ID.
- Dùng command response làm dữ liệu tạm cho UI.
- Đọc nguồn authoritative nếu yêu cầu nghiệp vụ cần ngay.
- Poll có backoff hoặc nhận notification khi projection cập nhật.

Không polling quá dày; điều đó có thể làm read model quá tải và khiến nó bắt kịp chậm hơn.

## 12. Tác động đến thiết kế API và trải nghiệm người dùng

### 12.1. Tách “đã ghi” khỏi “đã xuất hiện ở mọi nơi”

API cần phân biệt các mốc:

- Request được nhận.
- Command được xác thực.
- Transaction được commit.
- Event được publish.
- Replica/read model/cache đã cập nhật.

Không trả thông điệp “đã đồng bộ trên toàn hệ thống” nếu mới chỉ commit primary. Với tác vụ bất đồng bộ, có thể trả 202 Accepted cùng operation ID nếu command chỉ được nhận để xử lý; nếu transaction đã commit nhưng projection đang cập nhật, trả trạng thái phù hợp như committed và projectionPending.

### 12.2. Optimistic UI

Ứng dụng có thể cập nhật giao diện ngay sau khi người dùng gửi lệnh, trước khi mọi read model hoàn tất. Đây là optimistic UI. Khi API xác nhận commit, UI có thể giữ trạng thái mới; nếu thất bại, UI phải rollback hoặc hiển thị trạng thái lỗi.

Optimistic UI cải thiện cảm nhận tốc độ nhưng không phải bằng chứng dữ liệu đã bền vững. Đối với thanh toán, tồn kho hoặc quyền truy cập, không được dùng giá trị optimistic để thực hiện hành động nhạy cảm trước khi backend xác nhận.

### 12.3. Polling, long polling và notification

Khi read model cập nhật bất đồng bộ, client có thể:

- Poll trạng thái operation với exponential backoff và jitter.
- Dùng long polling hoặc server-sent events/websocket để nhận thông báo.
- Nhận version mới rồi thực hiện GET có token nhất quán.

Notification chỉ báo có khả năng đã cập nhật; nếu message có thể đến trước khi replica/query projection hoàn tất, client vẫn cần kiểm tra version hoặc retry đọc.

### 12.4. API idempotency và retry

Mất mạng sau khi gửi write có thể khiến client không biết transaction đã commit hay chưa. Retry mù có thể tạo bản ghi trùng hoặc thực hiện nghiệp vụ hai lần. Dùng idempotency key, operation ID hoặc version check để xác định một write đã được xử lý.

Read-after-write token nên gắn với operation ID hoặc phiên bản được server xác nhận. Không tạo token từ timestamp client vì đồng hồ có thể lệch và timestamp không phản ánh thứ tự commit chính xác.

## 13. Chọn consistency theo loại nghiệp vụ

Không phải mọi màn hình cần mức nhất quán như nhau. Hãy phân loại:

| Nghiệp vụ | Mức thường cần | Chiến lược gợi ý |
|---|---|---|
| Xem hồ sơ ngay sau khi cập nhật | Read-your-writes | Đọc primary hoặc dùng version token |
| Giỏ hàng sau khi thêm/xóa sản phẩm | Read-your-writes và monotonic reads | Session token, cache invalidation/version |
| Theo dõi trạng thái đơn hàng | Monotonic reads, freshness có giới hạn | Version/status sequence, không trả trạng thái cũ hơn đã thấy |
| Kiểm tra tồn kho trước khi đặt hàng | Stronger consistency/transactional check | Kiểm tra và giữ/giảm tồn kho trong transaction authoritative |
| Số dư trước khi cho phép chuyển tiền | Strong consistency theo tài khoản | Đọc/ghi trên authority có transaction và concurrency control |
| Dashboard phân tích | Eventual hoặc bounded staleness | Read replica/warehouse với freshness SLO |
| Search kết quả mới tạo | Read-your-writes theo operation hoặc eventual có trạng thái | Chờ index version, trả operation status hoặc fallback |
| Báo cáo tổng hợp nhiều shard | Eventual/bounded staleness thường chấp nhận được | Watermark theo shard và thời điểm snapshot |

Đây là định hướng, không thay thế phân tích nghiệp vụ. Ví dụ, màn hình tồn kho chỉ hiển thị có thể chấp nhận dữ liệu cũ vài giây, nhưng quyết định bán hàng phải kiểm tra lại trong transaction authoritative.

### 13.1. Consistency budget

Một sản phẩm có thể đặt ngân sách nhất quán:

- Thay đổi phải nhìn thấy ngay trong cùng session.
- Các session khác được phép trễ tối đa một khoảng đã định.
- Dashboard chấp nhận dữ liệu trễ vài phút.
- Giao dịch tài chính không chấp nhận mất cập nhật đã xác nhận.

Ngân sách này ảnh hưởng đến kiến trúc, chi phí replication, latency, cache, số lần fallback và khả năng hoạt động khi network partition. Phải được thống nhất giữa product, backend, DBA và vận hành.

## 14. Đo lường read-after-write và freshness

### 14.1. Commit-to-visible latency

Đo thời gian từ lúc commit được xác nhận tới lúc dữ liệu có thể đọc được từ đường đọc mà người dùng thực sự sử dụng. Chỉ số này có thể gọi là commit-to-visible latency.

Thu thập p50, p95, p99 và tỷ lệ vượt freshness SLO. Đo riêng:

- Primary commit acknowledgement.
- Replica receive/flush/replay/apply lag.
- Cache invalidation/update delay.
- Search/read-model projection delay.
- Thời gian token wait và số lần fallback.

### 14.2. Stale read rate

Có thể đo tỷ lệ lần đọc trả về version thấp hơn token mà client yêu cầu hoặc thấp hơn version đã quan sát trước đó. Không cần ghi toàn bộ dữ liệu nhạy cảm; chỉ cần version, source node, timestamp và correlation ID phù hợp.

### 14.3. Đo theo nguồn đọc

Ghi nhận request đọc từ primary, replica nào, cache nào hoặc projection nào. Nếu p99 tăng, cần biết nó tăng do replica lag, cache miss, fallback primary hay wait token. Metric tổng hợp toàn cụm có thể che một replica hoặc một shard bị tụt.

### 14.4. Correlation và tracing

Gắn trace ID, operation ID, shard ID, read source và consistency token vào log/tracing. Nhờ vậy có thể nối một write với các lần đọc sau và xác định điểm nào chưa bắt kịp.

Không log token hoặc query có thể chứa thông tin nhạy cảm ở dạng không được bảo vệ. Cần giới hạn cardinality của metric; không đưa user ID hoặc token duy nhất thành nhãn metric có cardinality không giới hạn.

## 15. Kiểm thử tính nhất quán

Kiểm thử chỉ chạy write rồi đọc ngay trên primary chưa đủ nếu production có replica, cache và nhiều service. Cần kiểm tra toàn đường đi:

1. Ghi một entity với version mới và nhận commit acknowledgement.
2. Đọc qua endpoint bình thường, không ép primary, để xác định routing thực tế.
3. Đọc qua nhiều instance, nhiều replica và nhiều region.
4. Đọc qua cache-aside, local cache, CDN hoặc search projection.
5. Tạo replication lag có kiểm soát và xác nhận RAW wait/fallback hoạt động.
6. Gửi nhiều write liên tiếp rồi kiểm tra monotonic writes và monotonic reads.
7. Thử transaction snapshot đã mở trước write để xác nhận hành vi isolation.
8. Thử failover trong khi có write vừa xác nhận và kiểm tra token/epoch.
9. Mô phỏng mất phản hồi commit, retry cùng idempotency key và xác nhận không tạo dữ liệu trùng.
10. Kiểm tra timeout, overload và network partition; xác nhận request không chờ vô hạn.

### 15.1. Ví dụ test với replica trễ

Giả sử API cập nhật trạng thái đơn hàng từ PROCESSING sang SHIPPED. Sau commit, response chứa version 12. Test có thể cố tình trì hoãn apply trên replica:

- GET không kèm token có thể đọc version 11 nếu endpoint cho phép eventual consistency.
- GET kèm token version 12 phải chờ replica, fallback primary hoặc trả trạng thái retryable theo hợp đồng.
- Khi replica áp dụng version 12, GET phải trả version 12 hoặc mới hơn.
- Nếu client đã thấy version 13, lần đọc tiếp theo không được quay về version 12 nếu endpoint cam kết monotonic reads.

Test phải xác minh cả HTTP status, payload, read source, thời gian chờ và metric fallback.

## 16. Những lỗi thiết kế thường gặp

- **Ghi vào primary rồi đọc từ replica ngay:** replica có thể chưa replay transaction.
- **Cho rằng synchronous replication luôn đồng nghĩa replica đọc được dữ liệu:** log có thể đã harden nhưng chưa replay/apply.
- **Dùng fixed sleep:** thời gian chờ cố định không chứng minh replica đã bắt kịp; lúc lag tăng vẫn đọc cũ, lúc lag thấp thì lãng phí latency.
- **Chỉ đo lag trung bình:** p99 hoặc một shard/replica riêng có thể chậm hơn nhiều.
- **Bỏ qua cache:** replica đã cập nhật nhưng cache hoặc ORM vẫn trả phiên bản cũ.
- **Chỉ invalidate một tầng cache:** local cache, CDN hoặc negative cache còn giữ dữ liệu.
- **Dùng TTL như cam kết RAW:** TTL chỉ giới hạn tuổi cache theo cấu hình, không bảo đảm ngay sau write.
- **Ghim session vào replica bất kỳ:** affinity không làm replica bắt kịp.
- **Dùng timestamp client làm token:** clock skew và thứ tự commit khiến timestamp không phải watermark đáng tin cậy.
- **So sánh token khác shard/cluster:** LSN hoặc sequence không có thứ tự chung giữa các luồng độc lập.
- **Để fallback primary không giới hạn:** replication lag có thể đẩy toàn bộ traffic về primary và tạo quá tải.
- **Nhầm isolation với replication consistency:** transaction snapshot có thể cũ ngay trên primary; read replica lại là một vấn đề khác.
- **Trả “đã đồng bộ” quá sớm:** command commit không chứng minh search index hoặc projection đã cập nhật.
- **Retry write không idempotent:** mất phản hồi commit có thể tạo thao tác trùng.
- **Không kiểm thử failover:** token hoặc session affinity có thể không còn hợp lệ sau khi topology đổi.

## 17. Quy trình thiết kế một luồng read-after-write

1. **Xác định nghiệp vụ:** dữ liệu nào phải thấy ngay, client/session nào được bảo đảm và mức trễ tối đa.
2. **Vẽ đường ghi:** command API, primary, commit acknowledgement, outbox/event và các bản sao.
3. **Vẽ đường đọc:** cache, read replica, search index, projection và routing layer.
4. **Định nghĩa token:** chọn LSN/GTID/version/offset phù hợp, có phạm vi cluster/shard và epoch.
5. **Chọn chính sách đọc:** primary pinning, session affinity, wait-for-watermark, fallback hoặc trạng thái processing.
6. **Đặt deadline:** giới hạn token wait và fallback; tránh chờ vô hạn hoặc retry storm.
7. **Thiết kế cache:** invalidation/versioning, xử lý race, negative cache và local cache.
8. **Thiết kế API:** phân biệt committed, projected và fully visible; hỗ trợ idempotency và operation ID.
9. **Đo baseline:** commit-to-visible latency, stale read rate, replication lag, cache delay và fallback rate.
10. **Kiểm thử sự cố:** lag, overload, failover, network partition, mất phản hồi commit và cache race.
11. **Triển khai từng bước:** bật token/fallback cho một nhóm traffic, theo dõi SLO và tải primary.
12. **Điều chỉnh:** cân bằng consistency, latency, throughput, chi phí và khả năng chịu lỗi.

## 18. Ví dụ thiết kế: cập nhật hồ sơ và tải lại ngay

Một dịch vụ hồ sơ dùng primary để ghi, hai read replica để đọc và Redis cache-aside. Người dùng đổi tên hiển thị rồi reload trang. Nếu GET được định tuyến sang replica B hoặc Redis còn giá trị cũ, người dùng thấy tên cũ.

Một thiết kế có read-your-writes:

1. API PATCH /profiles/42 ghi trên primary và commit.
2. Response trả dữ liệu mới cùng consistency token opaque.
3. API phát invalidation/update cache qua outbox hoặc cơ chế đảm bảo event.
4. Request GET tiếp theo gửi token.
5. Data access layer kiểm tra replica replay watermark; nếu replica chưa đạt token, chờ trong ngân sách.
6. Nếu hết ngân sách, đọc primary hoặc trả response retryable theo SLO.
7. Cache không được trả version thấp hơn token; nếu cache chưa đạt, bypass cache và đọc nguồn phù hợp.
8. Khi replica và cache đã bắt kịp, request sau có thể quay về đường đọc scale-out.

Với một màn hình hồ sơ, primary fallback trong thời gian ngắn có thể hợp lý. Với dashboard phân tích, có thể không cần token và chấp nhận bounded staleness. Hai đường đọc có thể cùng tồn tại nếu API thể hiện rõ consistency contract.

## 19. Checklist vận hành

### Trước khi phát hành

- [ ] Đã xác định RAW áp dụng theo user, session, thiết bị hay operation.
- [ ] Đã phân loại nghiệp vụ cần strong, session, bounded hay eventual consistency.
- [ ] Đã xác định mốc ACK của primary và mốc apply của replica.
- [ ] Đã kiểm tra cache, ORM, CDN, search index và read model trên toàn đường đọc.
- [ ] Token được tạo sau commit và có phạm vi cluster/shard/epoch rõ.
- [ ] Có timeout, fallback và giới hạn concurrency.
- [ ] Retry write có idempotency key hoặc cơ chế tra cứu trạng thái.
- [ ] Đã kiểm thử transaction snapshot và connection/session behavior.

### Trong vận hành

- [ ] Theo dõi commit-to-visible latency p50/p95/p99.
- [ ] Theo dõi send/receive/flush/replay/apply lag theo replica và shard.
- [ ] Theo dõi cache invalidation delay và projection lag.
- [ ] Theo dõi stale read rate, token wait và fallback rate.
- [ ] Theo dõi tải primary khi fallback tăng.
- [ ] Theo dõi timeout, retry, error rate và operation đang pending.

### Sau sự cố hoặc failover

- [ ] Xác nhận replica mới chứa các giao dịch đã được xác nhận theo durability policy.
- [ ] Xác minh token/epoch còn hợp lệ sau thay đổi topology.
- [ ] Kiểm tra cache và read model được invalidate hoặc catch up.
- [ ] Xác nhận monotonic/read-your-writes không bị phá vỡ.
- [ ] Đối soát operation có commit outcome không rõ.

## 20. Bài tập tự kiểm tra

**Bài 1.** Người dùng cập nhật email thành công rồi GET ngay từ read replica nhưng nhận email cũ. Những nguyên nhân nào có thể xảy ra?

*Gợi ý:* Replica chưa nhận hoặc chưa replay log, request đọc được route tới replica khác, cache còn giá trị cũ, ORM persistence context hoặc transaction snapshot vẫn cũ.

**Bài 2.** Read-your-writes có bắt buộc mọi người dùng đều thấy thay đổi ngay không?

*Gợi ý:* Không. RAW thường là bảo đảm theo client/session. Strong consistency toàn cục là yêu cầu mạnh hơn.

**Bài 3.** Vì sao synchronous commit ở SQL Server Availability Group chưa chắc làm readable secondary thấy dữ liệu ngay?

*Gợi ý:* Secondary có thể đã harden log nhưng redo/apply chưa hoàn tất. Đọc dữ liệu cần trạng thái đã được áp dụng.

**Bài 4.** Vì sao fixed sleep 500 ms sau commit không phải giải pháp RAW đáng tin cậy?

*Gợi ý:* Lag thay đổi theo tải và sự cố. 500 ms có thể quá ngắn lúc lag cao và quá dài lúc replica đã bắt kịp. Dùng watermark và deadline.

**Bài 5.** Một API trả token LSN từ shard A rồi yêu cầu shard B chờ tới LSN đó. Sai ở đâu?

*Gợi ý:* LSN chỉ có thứ tự trong WAL stream của cluster/shard tương ứng; không thể so sánh trực tiếp giữa các stream độc lập.

**Bài 6.** Database replica đã bắt kịp nhưng GET vẫn trả dữ liệu cũ. Bạn kiểm tra gì?

*Gợi ý:* Redis, local cache, CDN, ORM second-level cache, negative cache, read model/search index và transaction snapshot.

**Bài 7.** Client timeout khi commit rồi retry lệnh tạo đơn hàng. Làm sao tránh tạo đơn trùng?

*Gợi ý:* Idempotency key/operation ID được lưu cùng transaction; tra cứu kết quả trước khi thực hiện lại.

## 21. Ghi nhớ khi tối ưu

Read-after-write bảo đảm client nhìn thấy thay đổi của chính mình sau khi write được xác nhận. Nó khác strong consistency toàn cục, monotonic reads và isolation trong transaction. Trong hệ thống mở rộng, một lần ghi có thể đi qua commit primary, truyền log, flush/harden ở replica, replay/apply, cache invalidation và cập nhật read model; các mốc này không đồng thời.

Thiết kế ứng dụng cần chọn rõ nguồn đọc sau write: primary, session-affinity, replica đã đạt watermark, cache có version hoặc read model đã xử lý tới operation version. Token phải đại diện đúng thứ tự trong đúng cluster/shard; wait cần có deadline và fallback có giới hạn. Cache, ORM và transaction snapshot đều có thể làm đọc sau ghi trả dữ liệu cũ dù primary đã commit.

Hãy định nghĩa consistency contract theo nghiệp vụ, đo commit-to-visible latency và stale read rate, theo dõi transport/apply/cache lag, kiểm thử failover và retry. Mục tiêu là bảo đảm mức nhất quán cần thiết cho từng luồng trong khi giữ latency, throughput và khả năng mở rộng trong giới hạn vận hành.

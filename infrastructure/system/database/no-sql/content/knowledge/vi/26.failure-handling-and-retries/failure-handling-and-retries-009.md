# Thực thi dự phòng và nguy cơ nhiều nút cùng áp dụng thao tác

## 1. Một yêu cầu, hai lần thực thi: sự cố bắt đầu như thế nào?

Một ứng dụng bán vé sử dụng cơ sở dữ liệu NoSQL phân tán. Khi người mua xác nhận thanh toán, API gửi yêu cầu tới một node điều phối. Sau 800 ms chưa có phản hồi, client thử lại qua node khác với hy vọng nhanh hơn.

~~~text
t=000 ms  Client gửi CHARGE(order=O101, amount=500000) tới Node A
t=700 ms  Node A đã ghi nhận giao dịch, chưa kịp gửi kết quả
t=800 ms  Client timeout, gửi lại CHARGE tới Node B
t=900 ms  Node B cũng chấp nhận yêu cầu
t=950 ms  Client nhận thành công từ B
t=980 ms  Phản hồi từ A đến muộn hoặc mất hẳn
~~~

Nếu ứng dụng xem hai request như hai giao dịch độc lập, người mua có thể bị thu tiền hai lần. Không phải vì NoSQL “ghi trùng dữ liệu” theo nghĩa một replica nhân bản bản ghi; mà vì **hai lần thực thi cùng một ý định nghiệp vụ** đã được chấp nhận.

Để giảm độ trễ đuôi (*tail latency*), hệ phân tán đôi khi gửi **nhiều bản sao của một yêu cầu** hoặc thử lại sau một khoảng chờ. Kỹ thuật này có thể rất hiệu quả cho những thao tác đọc phù hợp, nhưng nguy hiểm nếu kết quả từ một request được lấy làm lý do để tin rằng các bản sao còn lại đã dừng.

Đây là bài **“Thực thi dự phòng và nguy cơ nhiều nút cùng áp dụng thao tác”**, thuộc chương **Lỗi phân tán và retry** của module **Database No SQL**.

### Mục tiêu học tập

Sau bài này, bạn sẽ có thể:

1. Phân biệt **speculative execution**, **hedged request**, **retry**, **parallel replica read** và **replication**.
2. Mô tả các cuộc đua giữa timeout, commit, response và cancellation.
3. Giải thích vì sao **nhận phản hồi sớm nhất không chứng minh những lần thực thi khác đã được hủy**.
4. Chọn thao tác có thể thực thi dự phòng một cách an toàn và những thao tác cần bảo vệ đặc biệt.
5. Thiết kế idempotency key, conditional mutation, dedup record, fencing epoch và reconciliation.
6. Nhận diện những dạng duplicate do client, driver, load balancer, queue, failover và worker.
7. Xem xét tác động của speculative reads/writes lên consistency, throughput và chi phí.
8. Đọc hiểu các ví dụ liên quan Cassandra/ScyllaDB, MongoDB, DynamoDB, Redis và các hệ có leader/quorum.
9. Thiết kế metric, benchmark, alert và bài tập kiểm tra các cuộc đua trong mạng phân tán.

## 2. Các thuật ngữ gần nhau nhưng không đồng nghĩa

### 2.1. Retry — thử lại

Client gửi lần đầu, thấy timeout hoặc lỗi tạm thời rồi gửi một lần khác:

~~~text
Client -> A: Request #1
         ...
         Timeout
Client -> B: Request #2
~~~

Retry có thể xảy ra sau khi request đầu thực sự đã commit. Timeout chỉ cho thấy **client không nhận được kết quả trong thời hạn**, không xác nhận server chưa xử lý.

### 2.2. Hedged request — yêu cầu dự phòng có trễ

Gửi một yêu cầu trước; nếu chưa nhận kết quả đủ nhanh, gửi thêm bản sao đến một đường xử lý khác:

~~~text
Client --------> Replica A: GET K
       80 ms -> Replica B: GET K
                |
             lấy kết quả hợp lệ đầu tiên
~~~

Mục tiêu thường là né một replica chậm bất thường. Lần thứ hai có thể chạy **đồng thời** với lần đầu, không nhất thiết thay thế nó.

### 2.3. Speculative execution — thực thi suy đoán/dự phòng

Khái niệm rộng hơn: hệ chủ động thực hiện thêm một phương án tính toán, query hoặc request trước khi biết chắc kết quả phương án đầu. Trong driver NoSQL, đôi khi thuật ngữ này chỉ chính **speculative retry/query execution** để giảm tail latency.

Không phải mọi sản phẩm dùng từ *speculative execution* đều có cùng chính sách, default hay phạm vi thao tác.

### 2.4. Parallel reads / quorum reads

Một thuật toán đọc có thể cần gửi tới nhiều replicas và **kết hợp kết quả** để đáp ứng consistency level:

~~~text
Read coordinator -> Replica A
                 -> Replica B
Read requires consistent quorum/merge
~~~

Điều này khác chiến lược **“lấy phản hồi nhanh nhất và bỏ phần còn lại”**. Nếu hợp đồng đòi quorum, chỉ chọn response đầu tiên có thể sai.

### 2.5. Replication

Replication sao chép trạng thái giữa các replicas theo protocol của database:

~~~text
One logical write -> replicated to A, B, C
~~~

Đây không tự là ba giao dịch nghiệp vụ. Ngược lại:

~~~text
Client sends INSERT twice as two logical operations
~~~

có thể thực sự tạo hai side effects, dù mỗi lần lại được replicate nhiều lần.

### 2.6. Duplicate delivery và duplicate execution

**Duplicate delivery:** Cùng thông điệp được phát/giao tới consumer nhiều lần.

**Duplicate execution:** Cùng ý định được xử lý nhiều lần.

**Duplicate effect:** Thao tác tạo thêm hậu quả nghiệp vụ như double charge, double increment, gửi hai email hoặc tạo hai reservation.

Một hệ có thể chấp nhận duplicate delivery nhưng ngăn duplicate effect nhờ idempotency/atomic dedup.

## 3. Vì sao có nhu cầu gửi yêu cầu dự phòng?

### 3.1. Tail latency

Giả sử hầu hết GET hoàn tất trong 15 ms nhưng một số request mất 1.000 ms do:

- GC pause.
- Disk compaction hoặc page cache miss.
- CPU throttling.
- Network jitter.
- Connection queue.
- Một replica đang catch up.
- Một máy có I/O bất thường.

Nếu API có deadline 200 ms, một phần trăm nhỏ slow requests có thể làm trải nghiệm người dùng kém dù latency trung bình tốt.

### 3.2. Chọn đường xử lý khác

Nếu Replica A bị chậm cục bộ nhưng Replica B khỏe, một GET dự phòng tới B có thể trả nhanh hơn.

~~~text
A: hoàn tất sau 800 ms
B: hoàn tất sau 20 ms

Hedge gửi B ở t=100 ms
Client có kết quả từ B quanh t=120 ms
~~~

Ví dụ này giả định cả hai phản hồi **đều hợp lệ theo consistency contract**.

### 3.3. Khi cả hai cùng chịu sự cố

Nếu nguyên nhân là một hot partition, shared storage bottleneck hoặc network congestion trên cùng tuyến, gửi thêm request có thể:

- Tăng tải cho chính thành phần đang quá tải.
- Làm hàng đợi dài hơn.
- Tạo thêm timeout.
- Kích hoạt retry storm.

Hedging chỉ có ích khi có đủ **đa dạng đường xử lý và capacity dự phòng**; không thể coi là “bật lên là p99 luôn giảm”.

## 4. Dòng thời gian: response mất không đồng nghĩa commit thất bại

Một request ghi đi qua những mốc khác nhau:

~~~text
Client send
   |
   v
Server receive
   |
   v
Validate condition
   |
   v
Commit / durable decision
   |
   v
Apply / trigger downstream work
   |
   v
Send response
   |
   v
Client receive response
~~~

### 4.1. Timeout giữa commit và nhận phản hồi

~~~text
t1  Server commit reservation.
t2  Server gửi success.
t3  Mạng làm mất response.
t4  Client timeout.
~~~

Client chỉ biết **kết quả chưa rõ (unknown outcome)**, không biết request thất bại.

### 4.2. Hedged request đua với request gốc

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Node A
    participant B as Node B
    C->>A: Operation K, attempt 1
    Note over A: Đang xử lý
    C->>B: Operation K, hedge attempt 2
    B-->>C: Success
    Note over C: Client chọn response B
    Note over A: A có thể vẫn tiếp tục và commit
    A-->>C: Success đến muộn hoặc mất
~~~

Nếu A và B đều có thể apply cùng effect độc lập, việc **chọn response B** không hoàn tác side effect ở A.

### 4.3. Hủy network request không phải rollback

Client gọi cancel, đóng socket hoặc ngừng chờ một future:

~~~text
Client cancel -> không nhận response nữa
~~~

không có nghĩa:

~~~text
Server rollback -> thao tác chưa từng xảy ra
~~~

Server có thể đã commit, chuẩn bị commit hoặc tiếp tục xử lý sau khi client ngắt kết nối. Cancellation là cơ chế kiểm soát tài nguyên/best effort tùy protocol, không phải primitive transaction.

### 4.4. Một response success không đóng mọi attempt

Một response thắng cuộc chỉ cho biết attempt đó đáp ứng tiêu chí thành công theo contract. Nếu những attempt khác dùng operationId khác, có thể còn hậu quả sau đó.

Ứng dụng phải đánh giá **logical operation**, không lấy số future đã hoàn tất để đếm giao dịch nghiệp vụ.

## 5. Một logical operation và nhiều physical attempts

Một mô hình chính xác:

~~~text
Logical operation:
    opId = RESERVE-2026-0001
    businessKey = EVENT#E01#SEAT#S101
    requestedOwner = U17

Physical attempts:
    attempt 1 -> Node A
    attempt 2 -> Node B
    attempt 3 -> Node C
~~~

Các attempts có thể có requestId transport riêng để tracing, nhưng phải giữ **cùng định danh ý định** và cùng payload được xác thực.

### 5.1. Đếm thành công theo logical operation

Nếu một user nhấn đặt ghế một lần:

~~~text
1 logical operation
3 network attempts
1 business outcome
~~~

Không nên ghi ba successful orders chỉ vì ba attempts nhận ACK.

### 5.2. Định danh attempt khác operationId

| Trường | Mục đích | Có thay khi retry/hedge không? |
|---|---|---|
| operationId / idempotency key | Nhận diện một ý định nghiệp vụ | **Không** |
| attemptId | Nhận diện lần gửi thực tế | Có |
| traceId | Tương quan luồng tracing | Thường giữ hoặc liên kết cùng logical trace |
| businessKey | Resource chịu ràng buộc như ghế/username | Không đổi theo ý định |
| payloadHash | Ngăn dùng lại operationId với payload khác | Không |
| leaderEpoch | Bảo vệ quyền owner hiện hành | Có thể tăng sau failover |

### 5.3. Request ID ngẫu nhiên mỗi lần có thể gây hại

Nếu server dedup theo requestId được client tạo mới sau mỗi retry, mỗi attempt trông như yêu cầu mới hoàn toàn.

Dedup phải gắn với **ý định nghiệp vụ ổn định**, không chỉ ID của HTTP request hiện thời.

## 6. Phân loại thao tác trước khi thực thi dự phòng

### 6.1. Bảng quyết định

| Thao tác | Hedging/retry có thể an toàn? | Điều kiện và rủi ro |
|---|---|---|
| GET dữ liệu immutable | Thường phù hợp | Cùng snapshot/version, không side effect |
| GET dữ liệu eventual | Có thể phù hợp | Chấp nhận stale theo contract |
| GET cần linearizable | Chỉ khi đường đọc dự phòng đáp ứng protocol | Fastest stale replica có thể sai |
| PUT K=V với cùng value | Thường idempotent ở phạm vi key | Không che mất concurrent update hoặc side effect khác |
| DELETE một key | Có thể idempotent về trạng thái cuối | Audit/notification, tombstone/version vẫn cần xem |
| INCREMENT counter | **Không mặc định** | Hai lần thực thi có thể tăng hai lần |
| APPEND event | **Không mặc định** | Hai records/event IDs nếu thiếu dedup |
| CREATE với ID sinh tại server | **Không mặc định** | Retry có thể tạo hai IDs |
| Conditional create cùng business key | Có thể với contract phù hợp | Condition bảo vệ resource; xử lý unknown outcome |
| Chuyển tiền / charge | **Không mặc định** | Cần idempotency và transaction/provider semantics |
| Gửi email/SMS | Không mặc định | Có thể gửi trùng; outbox + dedup |
| Đặt ghế cuối | Chỉ với một nguồn quyết định | Không được cấp hai owner |
| Thao tác quản trị schema | Thường không hedge tùy tiện | Migration/DDL có thể có trạng thái trung gian |

### 6.2. Idempotent không đồng nghĩa read-only

Một PUT gán lại cùng giá trị có thể idempotent về trạng thái:

~~~text
PUT K=42
PUT K=42
~~~

Kết quả cuối vẫn K=42. Nhưng trigger, updatedAt, audit log, CDC hoặc email có thể chạy hai lần nếu implementation thiết kế như vậy.

### 6.3. Đọc cũng có thể có side effect

GET đôi khi bị triển khai sai dưới dạng:

~~~text
GET /report -> tạo một report mới
GET /view  -> increment view count bắt buộc
~~~

Đây không còn là pure read về mặt hiệu ứng nghiệp vụ. Hedging request có thể tạo nhiều reports hoặc tăng count nhiều lần.

### 6.4. Commutative không nghĩa duplicate-safe

Phép cộng có tính giao hoán:

\[
2+3=3+2.
\]

Nhưng thực thi cùng phép cộng 3 hai lần sẽ cho kết quả khác:

\[
x+3+3\ne x+3.
\]

Commutativity hỗ trợ thay đổi thứ tự; **idempotency** xử lý việc lặp lại cùng thao tác. Hai thuộc tính khác nhau.

## 7. Thực thi dự phòng cho READ: “nhanh nhất” chưa chắc “đúng nhất”

### 7.1. Hai replicas có độ mới khác nhau

~~~text
Primary:   profile version 12
Replica B: profile version 11
~~~

Client vừa cập nhật profile lên version 12. Nó gửi hedge GET tới B vì primary chậm. B trả version 11 sau 3 ms.

Nếu API hứa **read-your-writes**, việc chọn kết quả đến nhanh nhất từ B là sai hợp đồng.

### 7.2. Fastest valid response, không phải fastest bytes

Một policy đọc có thể yêu cầu:

- Replica đạt minimum revision.
- Query qua một leader/read-index hợp lệ.
- Result thuộc snapshot yêu cầu.
- Quorum response đủ để hòa giải.
- Không nhận kết quả từ node bị mất quyền.

Nếu không thỏa, response nhanh vẫn phải bị loại hoặc chờ.

### 7.3. Hedged quorum read

Giả sử ứng dụng cần quorum 2/3. Gửi đến A và B; B quá chậm, sau ngưỡng hedge gửi C để **thay vai trò một thành viên chậm**.

~~~text
Initial: A + B
Hedge:   C
Read completes when contract's quorum is satisfied.
~~~

Hệ vẫn phải kết hợp phiên bản/giá trị theo protocol; không chọn một ACK bất kỳ.

### 7.4. Non-idempotent read triggers

Một query đọc trên storage có thể kích hoạt refresh của cache hoặc read-repair nội bộ. Đây thường không phải business side effect độc lập, nhưng vẫn tiêu thụ tài nguyên.

Thực thi dự phòng có thể tăng network, CPU, disk seeks và read repair work. Đánh giá **resource amplification** ngay cả khi business result không đổi.

## 8. Phân biệt speculative read và speculative write

### 8.1. Read

Với thao tác thuần đọc:

~~~text
send GET to A
after hedgeDelay, send GET to B
accept first valid response according to consistency requirements
best-effort cancel loser
~~~

Chi phí tăng chủ yếu ở tài nguyên, tính nhất quán của dữ liệu đọc và các tác dụng phụ ngầm của query.

### 8.2. Write

Với một side effect:

~~~text
send INCREMENT to A
after hedgeDelay, send INCREMENT to B
~~~

Nếu hai điều phối viên coi đây là hai logical commands, counter có thể tăng hai lần.

### 8.3. “Driver hỗ trợ speculative execution” chưa đủ

Phải xem:

1. Driver có hedge chỉ các query idempotent không?
2. Ứng dụng có phải đánh dấu query idempotent hay không?
3. Có thể gửi tới replicas khác nhau trong cùng consistency context không?
4. Số speculative attempts tối đa bao nhiêu?
5. Trường hợp lỗi/timeout được trả cho client thế nào?
6. Các attempts chạy đồng thời có thể tạo duplicate side effects không?

Không suy chính sách an toàn chỉ từ tên cấu hình.

## 9. At-most-once, at-least-once và exactly-once effect

### 9.1. At-most-once attempt

Không gửi lại một command sau khi mất phản hồi:

~~~text
Send once -> nếu mất response, client chấp nhận UNKNOWN
~~~

Tránh client cố ý tạo thêm attempt, nhưng thao tác có thể đã hoặc chưa commit. Không phải bảo đảm business outcome đã thành công.

### 9.2. At-least-once delivery

Retry tới khi được xác nhận hoặc vượt một chính sách:

~~~text
Same message can be delivered more than once.
~~~

Giúp giảm nguy cơ mất công việc khi lỗi tạm thời, nhưng đòi xử lý duplicate.

### 9.3. Exactly-once effect

Mục tiêu hữu ích hơn cho giao dịch là:

> Một **logical operation** có side effect đúng một lần, dù được gửi hoặc xử lý nhiều lần.

Đạt điều này thường cần:

- Idempotency key/operation ID.
- Dedupe state bền vững.
- Atomic conditional/transaction với effect.
- Replay/reconciliation.
- Phạm vi và retention rõ ràng.

Không thể kết luận hệ có exactly-once end-to-end chỉ vì message broker, Raft log hoặc database có một tính năng mang tên “exactly once”.

### 9.4. Giới hạn giữa các hệ độc lập

Nếu mutation ở database và gửi tiền qua payment provider không nằm trong một transaction chung, exactly-once end-to-end cần idempotency ở provider, outbox/inbox hoặc protocol nghiệp vụ tương ứng.

## 10. Giải pháp nền tảng: idempotency key theo ý định nghiệp vụ

### 10.1. Ví dụ request

~~~http
POST /reservations
Idempotency-Key: reserve-T17-O101
Content-Type: application/json

{"eventId":"E01","seatId":"S101","userId":"U17"}
~~~

Client giữ nguyên key này trong mọi retry/hedge của **cùng hành động đặt chỗ**.

### 10.2. Phạm vi khóa

Một key nên được namespace theo context, ví dụ:

~~~text
(tenantId, operationType, idempotencyKey)
~~~

Không nên cho một tenant dùng key của tenant khác để đọc lại kết quả hoặc ảnh hưởng request.

### 10.3. Payload fingerprint

Nếu cùng key được gửi với payload khác:

~~~text
opId=R101, seat=S101
opId=R101, seat=S102
~~~

server không được âm thầm coi request thứ hai là retry hợp lệ của request đầu.

Lưu hash/fingerprint canonical của payload và trả conflict khi không khớp. Việc canonical hóa cần thống nhất kiểu số, JSON field order, Unicode, optional fields và danh sách fields ảnh hưởng semantic.

### 10.4. Giữ kết quả cuối

Một ledger:

~~~text
Key: (tenantId, opType, operationId)
PayloadHash: H
State: SUCCEEDED
Result: reservationId=R901
~~~

Khi attempt sau tới, trả lại kết quả đã được ghi nhận theo contract thay vì tạo reservation khác.

### 10.5. Retention

Nếu dedup record hết TTL sau 24 giờ nhưng client retry sau 25 giờ, request có thể bị xử lý mới.

Retention phải dựa trên:

- Vòng đời retry thực tế.
- Độ quan trọng nghiệp vụ.
- Thời gian đối soát.
- Rủi ro event đến rất muộn.
- Privacy/retention policy.

Không dùng TTL tùy tiện cho payment idempotency mà không xét hậu quả của duplicate xuất hiện muộn.

### 10.6. Một key chỉ nên đại diện một ý định

Không tái sử dụng một idempotency key cho mọi lần đặt vé của cùng user. Nếu không, các ý định mới hợp lệ có thể bị coi nhầm là retry của thao tác cũ.

## 11. Idempotency ledger: trạng thái và các cuộc đua

### 11.1. State machine cho một operation

~~~mermaid
flowchart TD
    A["NOT_SEEN"] -->|"Atomic claim"| B["IN_PROGRESS"]
    B -->|"Commit success"| C["SUCCEEDED"]
    B -->|"Business reject"| D["REJECTED"]
    B -->|"Worker crash / uncertain outcome"| E["RECOVERY_REQUIRED"]
    E -->|"Reconcile committed effect"| C
    E -->|"Verified absent / resume safely"| B
~~~

Các tên state là ví dụ. Nhiều hệ thực hiện toàn bộ mutation và lưu idempotency result trong **một atomic transaction**, khiến không cần trạng thái IN_PROGRESS bền vững riêng cho từng bước.

### 11.2. Một câu lệnh “SELECT rồi INSERT” chưa đủ

Hai nodes A và B đồng thời:

~~~text
A: GET opId=R101 -> not found
B: GET opId=R101 -> not found
A: process reservation
B: process reservation
~~~

Kiểm tra trước rồi mới ghi độc lập tạo **time-of-check/time-of-use race**.

### 11.3. Claim phải là thao tác nguyên tử

Thay vì đọc rồi ghi:

~~~text
Conditional INSERT opId=R101 IF ABSENT
~~~

Chỉ một attempt thắng claim theo consistency contract của storage. Các attempts còn lại đọc trạng thái operation hoặc chờ kết quả.

**Nhưng claim không phải effect.** Nếu A thắng claim rồi chết trước khi tạo reservation, operation có thể mắc IN_PROGRESS mãi. Cần lease/recovery protocol và cách xác định effect đã xảy ra hay chưa.

### 11.4. Atomic ledger + effect

Trường hợp thuận lợi: một transaction có thể đồng thời:

1. Xác minh business invariant.
2. Tạo reservation.
3. Ghi operationId và terminal result.

~~~text
TRANSACTION:
    require seat not owned
    require opId not already completed
    create reservation R901 owned by U17
    mark opId=R101 SUCCEEDED(result=R901)
COMMIT
~~~

Khi đó hai attempts cùng operationId không thể tạo hai reservation nếu store thật sự bảo đảm transaction/conditional semantics ở phạm vi liên quan.

### 11.5. Idempotency và invariant là hai lớp khác nhau

Hai người dùng khác nhau có operation IDs khác nhau nhưng cùng muốn ghế S101:

~~~text
opId=R101 -> user X -> seat S101
opId=R102 -> user Y -> seat S101
~~~

Dedup theo opId **không ngăn bán trùng ghế**. Cần thêm điều kiện duy nhất/quyền sở hữu trên seatId.

Ngược lại, điều kiện duy nhất trên ghế ngăn double booking nhưng chưa chắc xử lý retry của cùng user mượt mà nếu một attempt bị timeout và lần sau nhận conflict.

### 11.6. Terminal result cần ổn định

Khi cùng opId được thử lại, service nên trả lại cùng logical result, không tự tạo ID mới:

~~~text
Attempt 1 -> committed reservation R901, response lost
Attempt 2 -> lookup opId R101 -> returns R901
~~~

### 11.7. Failure terminal và transient khác nhau

Nếu nghiệp vụ từ chối vì ghế đã bán, có thể lưu terminal REJECTED theo policy. Nếu database unavailable, không nên vĩnh viễn lưu FAILED như business outcome nếu không biết operation đã commit hay chưa.

## 12. Tài nguyên ngoài transaction: inbox, outbox và reconciliation

### 12.1. Vấn đề dual write

Một service muốn:

~~~text
1. Commit order vào NoSQL.
2. Gọi payment provider charge.
3. Gửi email.
~~~

Các bước chạy ở ba hệ khác nhau. Một transaction cục bộ ở NoSQL không bao trùm mọi hệ.

### 12.2. Outbox

Trong transaction tạo order, ghi thêm một outbox event:

~~~text
TRANSACTION:
  create Order O101 state=PENDING_PAYMENT
  record operationId=CREATE-O101
  write OutboxEvent EVT-PAY-O101
COMMIT
~~~

Worker lấy outbox event, gọi payment provider với idempotency key ổn định, rồi cập nhật trạng thái. Nếu worker chết sau khi provider charge nhưng trước khi checkpoint, retry vẫn dùng **cùng provider idempotency key** hoặc một API đối soát được hỗ trợ.

### 12.3. Inbox/dedup ở consumer

~~~text
Consumer receives eventId=EVT-PAY-O101
IF eventId already handled:
    skip or return stored result
ELSE:
    process and record eventId atomically when possible
~~~

Nếu inbox marker và effect được ghi ở hai stores tách biệt, cần reconciliation vì không thể giả định cả hai commit cùng lúc.

### 12.4. Event delivered twice vẫn có thể đúng

~~~text
Message broker: at-least-once delivery
Consumer: idempotent business handling
External provider: stable idempotency key
~~~

Đây có thể là một kiến trúc thực tế hơn việc đòi mạng và broker không bao giờ giao lại tin nhắn.

### 12.5. Không lẫn việc gửi sự kiện và thực thi command

Nếu consumer xử lý hai lần cùng **event có eventId giống nhau**, có thể dedup.

Nếu người dùng thực sự thực hiện hai hành động riêng biệt, dù payload giống hệt, chúng có thể là **hai operations hợp lệ**. Không dedup theo payload đơn thuần mà làm mất hành động thật.

## 13. Conditional write và compare-and-set bảo vệ resource

### 13.1. Nguyên tắc

Một thao tác dạng:

~~~text
UPDATE seat=S101
SET owner=U17
ONLY IF owner is absent
~~~

đòi storage kiểm tra điều kiện và ghi như một **hành động nguyên tử trong phạm vi được hỗ trợ**.

### 13.2. Race hai users

~~~text
Node A -> IF owner absent, claim S101 for X
Node B -> IF owner absent, claim S101 for Y
~~~

Nếu cùng đến một nguồn quyết định có tính nguyên tử phù hợp, tối đa một request có thể thắng condition. Đây là safety quan trọng độc lập với idempotency key.

### 13.3. Optimistic concurrency

Với version:

~~~text
Read document version=17
Update IF version=17 SET value=newValue, version=18
~~~

Hai writers cùng version=17 không được cùng thành công với một storage hỗ trợ CAS đúng nghĩa.

### 13.4. Version/epoch không phải timestamp thông thường

Version tăng có kiểm soát hoặc fencing epoch giúp phát hiện owner cũ. Timestamp wall-clock do client gửi có thể lệch giờ hoặc bị lặp nên không tự là fencing token đáng tin.

### 13.5. LWW không xử lý side effect bên ngoài

Hai nodes cùng ghi:

~~~text
X claims S101, sends success email
Y claims S101, sends success email
Conflict resolution LWW keeps Y
~~~

Database hội tụ về Y không thu hồi được email hoặc charge của X. Không dùng last-write-wins thay cơ chế reservation độc quyền nếu invariant yêu cầu một winner.

## 14. Fencing epoch: chặn worker/leader cũ còn chạy

### 14.1. Thí nghiệm với lease

~~~text
t1 Worker A nhận lease cho job J101, epoch=41
t2 A bị GC pause 60 giây
t3 Lease hết hạn
t4 Worker B nhận lease mới, epoch=42
t5 B bắt đầu thực thi
t6 A thức dậy, tiếp tục ghi
~~~

Nếu chỉ có TTL lock mà resource đích không kiểm tra owner, **A và B đều có thể tác động**.

### 14.2. Fencing token

Một protocol có thể gửi:

~~~text
WRITE resource J101
ownerEpoch = 42
~~~

Resource đích chỉ chấp nhận những writes không thuộc epoch cũ hơn epoch có hiệu lực và phải kiểm tra quyền đồng thời với mutation theo semantics nguyên tử.

### 14.3. Bảo vệ quyền thực thi khác dedup

- **Idempotency:** Ngăn cùng logical operation tạo effect thêm lần nữa.
- **Fencing:** Ngăn actor giữ quyền đã hết hiệu lực tiếp tục ghi.
- **CAS/version:** Ngăn mutation trên trạng thái đã thay đổi.

Một workflow có thể cần cả ba.

### 14.4. Không tự mở rộng quyền của Raft

Một database dùng Raft có thể có leader được chọn đúng, nhưng worker cũ vẫn có thể gửi request tới object storage hoặc payment provider ngoài replication group.

Đồng thuận trong database **không tự fence mọi side effect ở hệ thống khác**.

### 14.5. Resource không hỗ trợ fencing

Nếu payment provider không hỗ trợ ownerEpoch, xem khả năng dùng một provider idempotency key, trạng thái đơn hàng bền vững và reconciliation. Không giả vờ một lease cục bộ biến API bên ngoài thành transaction phân tán.

## 15. Java: minh họa một hedged read có ngưỡng kích hoạt

Mục tiêu: gọi hai nguồn **GET thuần đọc**; gửi nguồn B nếu A chưa hoàn tất sau 80 ms. Đây là ví dụ mô hình hóa, không là thư viện có retry policy production.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

public final class HedgedRead {
    public static <T> CompletableFuture<T> query(
            Supplier<T> replicaA,
            Supplier<T> replicaB,
            Executor ioExecutor,
            ScheduledExecutorService scheduler
    ) {
        CompletableFuture<T> result = new CompletableFuture<>();

        CompletableFuture<T> first =
                CompletableFuture.supplyAsync(replicaA, ioExecutor);

        first.whenComplete((value, error) -> {
            if (error == null) {
                result.complete(value);
            }
            // Lỗi của A chưa nhất thiết nghĩa B cũng lỗi.
        });

        scheduler.schedule(() -> {
            if (result.isDone()) {
                return;
            }
            CompletableFuture<T> second =
                    CompletableFuture.supplyAsync(replicaB, ioExecutor);
            second.whenComplete((value, error) -> {
                if (error == null) {
                    result.complete(value);
                } else if (first.isCompletedExceptionally()) {
                    result.completeExceptionally(error);
                }
            });
        }, 80, TimeUnit.MILLISECONDS);

        // Bắt buộc đặt deadline tổng ở caller:
        // result.orTimeout(300, TimeUnit.MILLISECONDS);
        return result;
    }
}
~~~

### 15.1. Giới hạn cố ý của ví dụ

Đây chỉ minh họa cách **lên lịch thêm attempt và chọn success đầu tiên**. Để dùng production cần:

1. Handle đúng mọi race giữa hai failures; ví dụ trên có thể bị treo nếu A thất bại sau khi B đã thất bại vì callback A không hoàn tất result lỗi.
2. Dùng deadline/cancellation propagating tới network clients.
3. Chỉ chấp nhận result đạt consistency/minimum revision, không chỉ error==null.
4. Giới hạn số speculative attempts và concurrency.
5. Bảo đảm IO calls không chặn vô hạn, có driver timeouts riêng.
6. Đo extra requests và adaptive hedge threshold.
7. Kiểm soát khi executor/scheduler bị shutdown.
8. Không dùng nguyên dạng cho POST/INCREMENT/charge.

### 15.2. Vì sao không gọi cancel trên first để đảm bảo an toàn?

Ngay cả nếu gọi:

~~~java
first.cancel(true);
~~~

thì **CompletableFuture cancellation không chắc ngắt tác vụ IO đang chạy hoặc server-side work**. Nó không rollback thao tác nào đã commit. Đối với read, cancellation chủ yếu giúp tiết kiệm tài nguyên nếu driver hỗ trợ và đường xử lý có thể hủy.

### 15.3. Một lựa chọn tốt hơn

Khi database driver hỗ trợ speculative execution có policy, timeout, idempotence flag và topology awareness, thường nên dùng cơ chế chính thức thay vì tự viết router hedging không biết quorum/consistency.

## 16. Java: phân biệt logical command và transport attempt

Một kiểu dữ liệu có thể được truyền xuyên nhiều attempts:

~~~java
public record ReservationCommand(
        String operationId,
        String tenantId,
        String eventId,
        String seatId,
        String userId
) {
}

public record TransportAttempt(
        String attemptId,
        String targetNode,
        ReservationCommand command
) {
}
~~~

Một ứng dụng retry đúng ý định:

~~~java
ReservationCommand cmd = new ReservationCommand(
        "RESERVE-REQ-101",
        "T17", "E01", "S101", "U17"
);

TransportAttempt first = new TransportAttempt(
        "attempt-a", "node-A", cmd
);
TransportAttempt retry = new TransportAttempt(
        "attempt-b", "node-B", cmd
);
~~~

Ở đây operationId và business fields giữ nguyên; attemptId và node đích khác nhau.

**Tuy nhiên**, chỉ mang cùng operationId trong Java không tự tạo idempotency. Phía server phải enforce dedup và business invariant trên một storage có consistency phù hợp.

## 17. Pseudocode: một reservation handler idempotent

Giả sử storage hỗ trợ **một transaction nguyên tử** trên operation ledger và seat ownership record, theo contract và phạm vi keys đã chọn:

~~~text
handle(command):
    assert authenticatedPrincipal can reserve command.seatId
    namespace = (command.tenantId, "reserve", command.operationId)
    fingerprint = canonicalHash(command)

    TRANSACTION:
        previous = readOperation(namespace)

        if previous exists:
            if previous.fingerprint != fingerprint:
                return IDEMPOTENCY_KEY_CONFLICT
            return previous.terminalResult

        seat = readSeatForUpdate(command.eventId, command.seatId)

        if seat.owner exists:
            storeOperation(namespace, fingerprint, REJECTED_ALREADY_OWNED)
            return REJECTED_ALREADY_OWNED

        reservationId = deterministicOrAllocatedReservationId()
        updateSeatOwnerAtomically(command.userId, reservationId)
        storeOperation(namespace, fingerprint, SUCCEEDED(reservationId))

    COMMIT
    return storedTerminalResult
~~~

### 17.1. Cần transaction scope thực sự

Không chuyển pseudocode thành:

~~~text
GET operation
GET seat
PUT seat
PUT operation
~~~

với bốn calls tách biệt rồi tuyên bố race-free.

Nếu database không hỗ trợ transaction nguyên tử giữa những records này, phải đổi data model để đưa invariant vào một conditional item hoặc thiết kế workflow và đối soát khác.

### 17.2. Một attempt thắng, attempt kia đọc lại

Hai attempts cùng opId nếu được serialize đúng:

~~~text
Attempt A: writes seat+ledger, commits
Attempt B: sees matching ledger, returns same result
~~~

Hai attempts **khác opId nhưng cùng seat**:

~~~text
Attempt X: wins condition, owns seat
Attempt Y: business rejection
~~~

### 17.3. Unknown outcome sau transaction

Ngay cả một transaction nguyên tử vẫn có thể commit rồi mất response. Client phải retry với cùng opId hoặc query trạng thái.

### 17.4. Authorization không do idempotency thay thế

Không cho một người dùng khác đoán operationId và lấy kết quả nhạy cảm. Dedup lookup phải có tenant/user scoping và kiểm tra quyền trước khi trả kết quả.

## 18. Cassandra/ScyllaDB: speculative execution ở driver

### 18.1. Bối cảnh

Cassandra/ScyllaDB có thể có nhiều coordinators và replicas. Một client gửi truy vấn qua coordinator, coordinator phối hợp với những replicas cần thiết theo consistency level và topology.

Một driver có thể hỗ trợ **speculative execution policy**: nếu query chậm quá ngưỡng, driver gửi thêm execution attempt tới một coordinator khác. Đây là tối ưu hóa tail latency, không phải thay đổi bản chất một CQL mutation.

### 18.2. Cấu hình theo query và policy

Những câu hỏi quan trọng:

- Query có được đánh dấu **idempotent** không?
- Driver mặc định speculative execution đang tắt hay bật trong version/cấu hình sử dụng?
- Delay được tính tĩnh hay theo latency distribution?
- Có giới hạn số speculative executions không?
- Driver chọn coordinator nào, có tránh node chậm không?
- Consistency level và serial consistency có được giữ theo yêu cầu không?

Không sao chép một đoạn cấu hình không rõ phiên bản mà cho rằng cùng default ở mọi driver.

### 18.3. Một UPDATE gán cùng giá trị

~~~sql
UPDATE profiles
SET display_name = 'An'
WHERE tenant_id = 'T17'
  AND user_id = 'U101';
~~~

Thao tác này **có thể** idempotent về trạng thái field, nhưng cần lưu ý:

- CQL timestamp semantics, write-time và reconciliation.
- TTL nếu được chỉ định hoặc tự tính.
- Các reads/queries đồng thời khác.
- Side effects ở application/CDC.

Không tự đánh dấu idempotent chỉ vì câu SQL có từ UPDATE.

### 18.4. Counter update

~~~sql
UPDATE page_views
SET view_count = view_count + 1
WHERE page_id = 'P101';
~~~

Một counter increment **không idempotent**: hai executions có thể tăng hai lần. Không bật speculative execution/retry mù quáng cho thao tác này.

### 18.5. List append/prepend

Một phép thêm phần tử vào list có thể tạo nhiều occurrences khi retry. Việc data structure là collection không tự khiến operation an toàn để gửi nhiều lần.

### 18.6. LWT / conditional mutation

~~~sql
INSERT INTO username_claims (
    tenant_id, username, owner_id
) VALUES (
    'T17', 'alice', 'U101'
) IF NOT EXISTS;
~~~

LWT được thiết kế để chỉ một giá trị thắng theo conditional semantics trong phạm vi phù hợp. Nhưng khi attempt đầu đã thắng rồi response mất, attempt sau có thể thấy condition failed.

Ứng dụng vẫn phải đối soát **ai thắng** và xem đó có phải chính operation đang retry hay không. Conditional rejection không tự tương đương idempotency response replay.

### 18.7. Nguy cơ từ application

Nếu một service nhận ba success responses cho cùng lệnh rồi gọi webhook ba lần, storage conditional semantics cũng không cứu được external side effect. Phải gắn external effect vào operation ledger/outbox có dedup.

## 19. MongoDB: retryable writes không phải giấy phép gửi ghi hai lần tùy ý

### 19.1. Driver retryable writes

MongoDB hỗ trợ cơ chế **retryable writes** cho những operations và topology được hỗ trợ. Driver dùng thông tin session và định danh statement/transaction phù hợp để server phân biệt một driver retry của cùng logical write.

Điều này khác với việc ứng dụng tự gọi:

~~~javascript
await db.collection("counters").updateOne(
  { _id: "P101" },
  { $inc: { value: 1 } }
);

// Application coi timeout là thất bại
// rồi gọi thêm một updateOne độc lập.
await db.collection("counters").updateOne(
  { _id: "P101" },
  { $inc: { value: 1 } }
);
~~~

Nếu đây là hai lệnh mới không được dedup theo một logical-operation contract, counter có thể tăng hai lần.

### 19.2. Không đánh đồng retry ở hai tầng

~~~text
Driver retry cùng retryable write/session semantics
    khác
Application gọi API một lần thứ hai như business operation mới
~~~

Nếu ứng dụng bọc nhiều tầng retry, cần biết driver đã retry bên trong hay chưa để đánh giá request amplification và unknown outcome.

### 19.3. Transactions callback có thể chạy lại

Một số driver/helper hỗ trợ retry transaction callback khi gặp lỗi giao dịch đủ điều kiện. Nếu callback vừa mutate MongoDB vừa gọi email/payment:

~~~text
transaction callback:
    update order
    charge external provider
~~~

việc callback chạy lại có thể lặp external side effect. Không đưa side effects không thể rollback vào callback chỉ vì nó được chạy “trong transaction”.

### 19.4. Unique index và idempotency

Một collection có unique key theo (tenantId, operationId) có thể hỗ trợ dedup storage. Nhưng vẫn cần atomicity giữa ledger và business mutation hoặc một workflow có thể phục hồi nếu hai writes nằm ở các transaction boundaries khác nhau.

### 19.5. Sharded cluster

Nếu mutation và ledger nằm trên shards khác nhau, hành vi transaction, retry và failover khác thao tác một document. Hãy kiểm tra phạm vi transaction, write concern, read concern và session configuration của deployment.

## 20. DynamoDB: conditional writes, transactions và multi-Region

### 20.1. Conditional PutItem

Một item:

~~~text
PK = IDEMPOTENCY#T17#RESERVE-101
~~~

có thể được tạo với:

~~~text
ConditionExpression: attribute_not_exists(PK)
~~~

Đây là atomic condition cho một item theo phạm vi API cung cấp, giúp hai attempts không cùng tạo marker.

### 20.2. Chỉ có marker chưa đủ

~~~text
Attempt A creates marker.
Attempt A crashes before writing reservation.
Attempt B sees marker, refuses to process.
~~~

Nếu không có recovery protocol, logical operation kẹt mãi dù chưa tạo hiệu ứng.

### 20.3. TransactWriteItems

Nếu trong phạm vi DynamoDB hỗ trợ, dùng transaction để:

~~~text
Put idempotency result/claim with condition
Update seat if unowned
Put reservation
~~~

Cần xem giới hạn và cấu hình của API, vì không phải mọi nhóm items hoặc deployment đều được hỗ trợ giống nhau.

### 20.4. ClientRequestToken

Một số transactional APIs của DynamoDB hỗ trợ **client request token** để tăng tính idempotent trong một **cửa sổ thời gian được dịch vụ quy định**.

Không dùng token đó làm chứng minh business dedup tồn tại mãi mãi. Nếu retry xảy ra sau cửa sổ, hoặc ứng dụng tạo transaction khác, vẫn cần domain operation ledger khi nghiệp vụ yêu cầu.

### 20.5. GSI không phải điểm quyết định uniqueness

GSI có eventual consistency, nên hai attempts có thể cùng Query GSI rồi đều thấy chưa có claim. Cần conditional write trên key có thẩm quyền thay vì read-before-write qua GSI.

### 20.6. Global Tables

Với chế độ multi-Region eventual, một conditional write thành công ở Region A không tự bảo đảm không có Region B cùng lúc thực hiện một claim đối kháng theo bản sao local.

Nếu cần một winner toàn cầu, phải chọn consistency mode/architecture có bảo đảm phù hợp, một authority, hoặc quota/escrow model được thiết kế chính xác. Conflict resolution LWW không sửa side effect gửi cho cả hai người.

## 21. Redis: SET NX, INCR, Lua và lock TTL

### 21.1. SET NX như một claim

~~~text
SET op:RESERVE-101 IN_PROGRESS NX PX 30000
~~~

Một process thắng claim trong Redis tại thời điểm đó, nhưng không được suy ra toàn bộ effect được thực hiện exactly once.

### 21.2. TTL hết trước khi công việc kết thúc

~~~text
t1 A SET NX thành công, xử lý 40 giây
t2 TTL 30 giây hết hạn
t3 B SET NX cũng thành công
t4 A và B cùng tiếp tục
~~~

Đây là lý do TTL lock **không thay fencing**.

### 21.3. Lua atomically cập nhật state trong Redis

Một Lua script có thể kiểm tra marker và cập nhật một counter trong **một lần thực thi nguyên tử ở phạm vi Redis node/slot thích hợp**:

~~~lua
-- KEYS[1] = dedup marker
-- KEYS[2] = counter
-- ARGV[1] = operationId, dùng để audit nếu cần
if redis.call("EXISTS", KEYS[1]) == 1 then
    return 0
end
redis.call("SET", KEYS[1], ARGV[1])
redis.call("INCR", KEYS[2])
return 1
~~~

Điều này có thể ngăn duplicate updates ở phạm vi một Redis primary đang xử lý script đúng thứ tự. Nhưng còn:

- Trong Redis Cluster, multi-key script yêu cầu slot compatibility.
- Marker retention/eviction là chính sách quan trọng.
- Durability, replication và failover của Redis có thể ảnh hưởng sự tồn tại của kết quả.
- Không mở rộng tính nguyên tử của Lua sang payment provider hay database khác.

### 21.4. Redlock/leases cũng không là business transaction

Các cơ chế distributed lock dùng Redis có các giả định và giới hạn riêng. Với effect quan trọng, vẫn phải có fencing/idempotency và khả năng reconciliation.

## 22. Consensus/leader-based NoSQL: chỉ một owner có quyền commit

### 22.1. Split-brain perception

Network partition:

~~~text
Old leader A (epoch 41) | New leader B (epoch 42)
~~~

A có thể chưa biết nó mất quyền, nhưng nếu protocol yêu cầu quorum, A không được commit entry mới khi không đủ majority.

### 22.2. Thực thi dự phòng không được bypass leader

Nếu client gửi cùng mutation tới A và B để “node nào nhanh thì dùng”, driver/router phải bảo đảm chỉ path có thẩm quyền được commit theo protocol.

Không gọi trực tiếp physical replicas rồi tự quyết chọn winner dựa trên response-time.

### 22.3. Operation ID trong replicated log

Ngay cả khi Raft/Paxos chỉ commit một thứ tự log hợp lệ, hai commands:

~~~text
index 101: INCREMENT counter
index 102: INCREMENT counter
~~~

đều có thể được commit hợp lệ. Consensus bảo vệ log, **không tự biết chúng là duplicate của một user action**.

### 22.4. Dedupe là state-machine concern

Nếu state machine lưu operation IDs đã xử lý và kiểm tra chúng khi apply, hai log entries cùng opId có thể tạo một effect trong phạm vi dedup state bền vững.

Nếu dedup chỉ ở client, failover có thể khiến client gửi tới leader mới và tạo duplicate command.

### 22.5. Follower đọc cũ

Một hedged read tới follower vừa bị lag có thể trả stale. ReadIndex/lease/read quorum/session semantics phải được xét theo contract trước khi dùng “first response wins”.

## 23. Nhiều tầng retry: khuếch đại số attempts

Một request có thể được retry bởi:

~~~text
Mobile SDK
   |
   v
API Gateway / Proxy
   |
   v
Backend service
   |
   v
Database driver
   |
   v
Database coordinator
~~~

Nếu mỗi trong bốn tầng đầu thử tối đa ba lần, số attempts ở tầng cuối **trong trường hợp xấu** có thể lên đến:

\[
3^4=81.
\]

Đây là upper-bound trong mô hình đơn giản giả định tất cả retry lồng nhau đều diễn ra, không phải số mặc định của một framework.

### 23.1. Deadline tổng

~~~text
Client overall deadline = 2 giây
Gateway remaining budget -> Backend
Backend remaining budget -> DB driver
~~~

Không nên đặt mỗi tầng timeout 2 giây rồi retry ba lần khiến tổng trải nghiệm kéo dài hàng chục giây.

### 23.2. Ai sở hữu retry?

Đối với một thao tác, quy định rõ:

- Driver có retry tự động không?
- Service có retry ở tầng ứng dụng không?
- Gateway có retry POST không?
- Client mobile có retry sau background resume không?
- Có thể xảy ra retry muộn sau khi user đã rời trang không?

Tránh để mọi tầng tự quyết và cùng hedge/retry mà không chia sẻ budget.

### 23.3. Retry amplification

Một chỉ số:

\[
\text{AttemptAmplification}=
\frac{\text{physical attempts}}
{\text{logical operations}}.
\]

Ví dụ 10.000 ý định tạo ra 12.000 network attempts:

\[
12.000/10.000=1,2.
\]

Hệ phát sinh trung bình 20% attempts bổ sung. Đây là một con số tốt để quan sát cùng p99 và request failure rate.

### 23.4. Retry storm

Nếu database chậm, nhiều clients cùng retry đúng 100 ms:

~~~text
DB slow -> client timeout -> synchronized retry -> DB slower
~~~

Exponential backoff với jitter, token retry budget, circuit breaker và admission control giúp tránh vòng lặp khuếch đại.

### 23.5. Hedging và retry cùng bật

Một query có ba retry attempts và mỗi attempt lại hedge hai replicas có thể tạo nhiều truy vấn vật lý cho một ý định. Cần giới hạn **combined attempt budget**, không cấu hình mỗi chính sách độc lập mà bỏ qua tổng.

## 24. Chọn ngưỡng hedging: độ trễ và chi phí

### 24.1. Không hedge ngay lập tức mọi GET

Nếu luôn gửi cùng một GET tới hai replicas từ t=0:

~~~text
10.000 logical GETs
20.000 physical GET attempts
~~~

Đây là gần gấp đôi read workload ngay cả khi hầu hết requests vốn đã nhanh.

### 24.2. Hedge sau một ngưỡng

Ví dụ:

~~~text
Request A starts at t=0
If no valid response at t=100 ms:
    start B
When one response satisfies read contract:
    finish logical request
~~~

Nếu chỉ 5% GET còn đang chờ ở 100 ms và mọi request pending sinh đúng một hedge, khoảng 5% thêm attempts trong mẫu ổn định, trước khi tính những điều kiện khác.

### 24.3. Ngưỡng tĩnh vs phân vị động

- **Fixed delay:** Dễ giải thích, nhưng không tự điều chỉnh khi latency của môi trường biến đổi.
- **Percentile-based delay:** Dùng p95/p99 của endpoint/cụm để bắt đầu hedge ở các requests bất thường.
- **Adaptive:** Cân nhắc tải hiện tại, loại request, replica health và ngưỡng trần cho extra attempts.

Không dùng một ngưỡng 100 ms chung cho cache GET 2 ms và query analytics 3 giây.

### 24.4. Chọn destination độc lập

Hedge hiệu quả hơn nếu đường thứ hai tránh được nguồn chậm:

~~~text
Attempt A -> Replica ở AZ1
Attempt B -> Replica khác ở AZ2
~~~

Nhưng cross-AZ/Region có chi phí và consistency implications riêng. Không tự route sang Region bị cấm bởi data residency chỉ để nhanh hơn.

### 24.5. Giới hạn số attempts

Một policy minh họa:

~~~text
Operation type: eligible pure read
Hedge threshold: endpoint-specific p95
Maximum hedges: 1
Overall deadline: 500 ms
Extra load budget: <= 5% normal traffic
Disable on overload / unhealthy replica pool
~~~

Các ngưỡng chỉ để minh họa; phải benchmark theo khả năng xử lý của hệ.

### 24.6. Tỷ lệ xác suất không độc lập

Giả sử xác suất một replica bị chậm là \(p\). Chỉ trong mô hình **độc lập lý tưởng**, xác suất hai đường cùng chậm có thể ước lượng \(p^2\).

Trong production, các nguyên nhân chậm thường tương quan: cùng dữ liệu nóng, cùng storage, cùng mạng, cùng sự cố Region. Do đó không thể áp dụng \(p^2\) để cam kết SLO cho hedged requests.

### 24.7. Đừng để hedge hại request khác

Hedging có thể cải thiện p99 của nhóm được hedge nhưng làm QPS tăng và kéo dài p99 của các request khác. Phải đo toàn dịch vụ và các nhóm tenant, không chỉ latency của request thắng.

## 25. Race conditions đặc trưng

### 25.1. Race: first attempt commits, second also commits

~~~text
A: commits INCR K
B: commits INCR K
Client sees B success
~~~

Nếu K là counter không có dedup, tăng hai lần. Chọn B là winner ở client không sửa được.

### 25.2. Race: cancellation đến sau commit

~~~text
A: commits
Client: cancel A
A: receives cancel too late
~~~

Cancellation không quay ngược log đã commit.

### 25.3. Race: idempotency marker trước effect

~~~text
A: claim operationId
A: crashes
B: sees claim, refuses
~~~

Không có duplicate effect, nhưng operation có thể mất tiến triển mãi. Cần recovery và trạng thái PENDING có deadline hoặc workflow idempotent.

### 25.4. Race: effect trước idempotency marker

~~~text
A: charges payment
A: crashes before writing marker
B: marker absent, charges again
~~~

Đây là lỗi nghiêm trọng; marker và effect cần ràng buộc transaction hoặc provider idempotency/outbox/reconciliation phù hợp.

### 25.5. Race: owner lease expired

~~~text
A: processing with old lease
B: acquires new lease
A and B: write to downstream
~~~

Fencing/epoch tại resource đích phải ngăn owner cũ tiếp tục tác động.

### 25.6. Race: read from stale replica wins

~~~text
GET replica B -> version 9 in 3 ms
GET leader A  -> version 10 in 40 ms
Client chooses B
~~~

Nếu minimum version=10, fastest response không hợp lệ.

### 25.7. Race: duplicate event but different IDs

Một lỗi producer phát lại cùng business event nhưng sinh eventId mới:

~~~text
eventId=E1001, order=O101, action=CHARGE
eventId=E1002, order=O101, action=CHARGE
~~~

Dedup theo eventId không thấy duplicate logical operation. Cần thêm một business operation ID có tính ổn định và định nghĩa rõ sự kiện nào được phép lặp.

## 26. Hành vi đúng khi outcomes không rõ

### 26.1. Ba trạng thái cần phân biệt

~~~text
SUCCEEDED:
    Có bằng chứng commit theo contract.

REJECTED:
    Điều kiện nghiệp vụ bị từ chối có thẩm quyền.

UNKNOWN / PENDING:
    Không thể kết luận commit hay chưa từ phản hồi hiện có.
~~~

### 26.2. Không biến UNKNOWN thành FAILED

Nếu UI hiển thị “thanh toán thất bại” khi provider đã charge, người dùng có thể thử lại bằng một phương thức khác và bị tính tiền hai lần.

Một UX an toàn hơn:

~~~text
Thanh toán đang được xác minh.
Không thực hiện thêm yêu cầu thanh toán mới.
Bạn có thể kiểm tra trạng thái bằng mã giao dịch O101.
~~~

### 26.3. Status endpoint phải đọc đủ mới

Nếu POST đã commit nhưng GET /operations trên một search index eventual chưa thấy record, status endpoint không được khẳng định “chưa tồn tại” như một kết luận cuối cùng.

Có thể cần đọc nguồn có thẩm quyền, minimum revision hoặc một transaction status ledger.

### 26.4. Reconciliation

Sau timeout, service có thể đối soát:

1. Lookup operationId.
2. Tra business resource theo khóa có thẩm quyền.
3. Tra trạng thái external provider nếu có.
4. Kiểm tra outbox/inbox và các terminal events.
5. Chỉ khi có bằng chứng phù hợp mới chuyển trạng thái cuối.

### 26.5. Không nên ngủ vô hạn chờ kết quả

Một operation có thể ở PENDING nhiều giờ nếu worker không chạy. Cần retry schedule, dead-letter/exception queue, timeout SLA và người/automation chịu trách nhiệm đối soát.

## 27. Bảo vệ concurrency khi cùng operation được xử lý song song

### 27.1. Một lock không đủ nếu không có trạng thái bền vững

Một process-local mutex:

~~~java
synchronized (this) {
    process(operationId);
}
~~~

chỉ bảo vệ những threads dùng cùng object trong cùng JVM. Nó không khóa Node B ở máy khác.

### 27.2. Distributed claim

Một conditional item trong storage có thể xác định worker đang xử lý một operation. Tuy nhiên cần:

- Owner identity.
- Epoch hoặc version.
- Trạng thái lifecycle.
- Lease/retry deadline nếu dùng lease.
- Atomic transition theo protocol.

### 27.3. Concurrent same-operation attempts

Nếu hai attempts cùng opId:

~~~text
A claims IN_PROGRESS epoch 8
B gets ALREADY_IN_PROGRESS
~~~

B không nhất thiết phải đợi block đồng bộ tới vô hạn; có thể trả PENDING/retry-after hoặc watch trạng thái theo API.

### 27.4. Claim expiry và takeover

Sau khi A mất lease, B có thể takeover với epoch 9. Nhưng A còn sống có thể tiếp tục chạy. Không dựa vào “A hẳn đã chết” để cho B thực thi side effect không có fencing.

### 27.5. Dedupe cache và nguồn quyết định

Cache in-memory để tránh lookup ledger trên mọi attempt là tối ưu hóa. Khi cache bị eviction/restart, **nguồn bền vững** vẫn phải bảo vệ uniqueness và terminal result.

### 27.6. Hot idempotency key

Một opId bị hàng nghìn clients spam retry có thể thành hot item. Có thể dùng backoff, per-operation rate limiting và status polling/coalescing, nhưng không phân tán quyền claim của cùng opId sang 16 random owners.

## 28. Đọc có side effect gián tiếp và giới hạn cancellation

### 28.1. Query có thể chiếm tài nguyên sau khi client trả

Một speculative query thất bại ở client nhưng vẫn được server thực thi:

~~~text
Coordinator scans 1 million rows.
Client uses another replica's result.
Server scan continues for some time.
~~~

Số liệu thành công ở client có thể đẹp trong khi backend bị nhân đôi I/O.

### 28.2. Cancellation có nhiều tầng

- Cancel future ở client.
- Hủy HTTP/gRPC stream.
- Driver báo cancel tới coordinator.
- Coordinator hủy subqueries.
- Storage engine dừng scan.

Các tầng không nhất thiết có cùng semantics hoặc lập tức chấm dứt công việc.

### 28.3. Streaming response

Với query streaming:

~~~text
Attempt A: đã stream 500 items
Attempt B: bắt đầu hedge
~~~

Không thể tùy tiện lấy nửa stream từ A rồi chuyển sang B mà không có snapshot/cursor/version contract. Dữ liệu có thể bị trùng, thiếu hoặc đổi thứ tự.

### 28.4. Race giữa query update và stale read

Một query GET đầu có snapshot cũ; hedge query sau đọc snapshot mới. Chọn fastest response có thể làm UI đôi lúc đi lùi version nếu không có minimum revision/monotonic reads policy.

### 28.5. Read-only ở API không tự đọc thuần ở business layer

Một endpoint /reports/latest có thể tự tạo report nếu chưa có. Đó là **read-or-create** và có mutation ngầm; hedging cần dedup của create path, không chỉ dựa trên HTTP GET.

## 29. SLO/SLI nên đo theo logical operation

### 29.1. Một attempt thành công không đủ

Giả sử một logical reservation gửi ba attempts; hai trả 200 nhưng tạo hai records. **Logical outcome là sai**, không phải hai successes.

### 29.2. Các metric

~~~text
logical_operations_total{kind,outcome}
physical_attempts_total{kind,reason,target}
hedged_attempts_total{kind,target}
retries_total{kind,reason}
duplicate_attempts_detected_total{kind}
duplicate_effects_detected_total{kind}
idempotency_conflicts_total{kind}
unknown_outcomes_total{kind}
reconciliation_pending_operations{kind}
request_duration_seconds_bucket{kind,le}
logical_operation_duration_seconds_bucket{kind,le}
~~~

Tên chỉ là ví dụ, không phải metric chuẩn bắt buộc của một sản phẩm.

### 29.3. Phân biệt 4 thước đo

| Thước đo | Câu hỏi |
|---|---|
| Physical attempt rate | Backend thực sự nhận bao nhiêu yêu cầu? |
| Logical operation success | Bao nhiêu ý định nghiệp vụ có kết quả đúng? |
| End-to-end latency | Người dùng hoàn thành ý định sau bao lâu? |
| Effect cardinality | Một ý định sinh đúng bao nhiêu side effects? |

### 29.4. Ví dụ định lượng

~~~text
10.000 logical GET requests.
500 GETs được hedge, mỗi hedge thêm một attempt.
All logical GETs thành công theo read contract.
~~~

Số physical attempts:

\[
10.000+500=10.500.
\]

Attempt amplification:

\[
10.500/10.000=1,05.
\]

Tức thêm 5% lượng query vật lý trong ví dụ này.

### 29.5. Hiệu quả ròng

Đánh giá:

- p95/p99 logical latency giảm bao nhiêu?
- Tổng CPU/I/O/network tăng bao nhiêu?
- Có tăng throttle/timeout ở tenants khác không?
- Extra attempts có giúp khi replica thật sự chậm không?
- Duplicate side effects có phát sinh không?

Không bật hedging chỉ vì một biểu đồ p99 của client đẹp hơn trong khi cụm đã overload.

## 30. Runbook khi thấy duplicate side effects

### 30.1. Khoanh vùng ảnh hưởng

Thu:

~~~text
operationIds affected
business resources affected
time window
clients/regions/tenants
attempt counts
driver retry/hedge settings
downstream effect IDs
~~~

Không xuất dữ liệu cá nhân, thẻ thanh toán hoặc secrets ra logs tùy tiện.

### 30.2. Ngăn hiệu ứng tiếp tục

Tùy tình huống:

- Tắt/giới hạn speculative writes.
- Chặn retry của endpoint non-idempotent.
- Thêm rate limit cho hot operation.
- Chuyển giao dịch nhạy cảm sang chế độ fail-closed nếu thiếu authority.
- Dừng consumer đang phát event trùng nếu có kế hoạch an toàn.

### 30.3. Phân biệt duplicate attempt và duplicate effect

Hai GET requests không nhất thiết là incident. Hai CHARGE side effects của cùng order là incident nghiêm trọng.

### 30.4. Đối soát từ nguồn có thẩm quyền

Lấy danh sách logical operations rồi ghép:

~~~text
operationId -> attempts -> commits -> external effects
~~~

Không dựa vào một cache/search index eventual để kết luận giao dịch thực chưa xảy ra.

### 30.5. Xử lý bù trừ

Với double charge, một khoản refund có thể được yêu cầu theo chính sách. Nhưng refund là một operation mới cần idempotency, audit và đối soát; không xóa lịch sử giao dịch rồi coi như không có sự cố.

### 30.6. Nguyên nhân gốc

Xác định duplicate đến từ:

- Tầng client.
- Gateway retry POST.
- Service retry sau timeout.
- Driver speculative execution.
- Queue re-delivery.
- Consumer restart.
- Lease expiry.
- Mismatch giữa operation ID và payload.

### 30.7. Khắc phục dài hạn

Thêm atomic dedup, business condition, fencing, transaction hoặc outbox phù hợp. Tạo fault injection test trước khi bật lại chính sách retry/hedging.

## 31. Kiểm thử lỗi phân tán cho speculative execution

### 31.1. Mô hình thử

Giả sử:

~~~text
Client -> Gateway -> Service A/B -> NoSQL cluster
                            |
                            v
                     External provider
~~~

Mọi logical operation được gắn operationId và mỗi attempt có attemptId riêng để trace.

### 31.2. Test matrix

| Kịch bản | Fault injection | Điều cần xác minh |
|---|---|---|
| Replica A chậm | Delay A 500 ms | Hedge đọc B giảm latency, vẫn hợp consistency |
| Cả A và B chậm | Delay cả hai | Extra load không tạo retry storm |
| A commit nhưng response mất | Drop response sau commit | Retry cùng opId không duplicate effect |
| B commit nhanh hơn A | Start concurrent attempts | Chỉ một logical outcome |
| A/B cùng nhận request | Duplicate delivery | CAS/ledger bảo vệ một winner |
| Cancel sau commit | Client abort socket | Không giả định rollback |
| Leader election giữa ghi | Fail leader có chủ đích | Unknown outcome được đối soát |
| Follower stale | Delay replication | Hedged read không trả phiên bản dưới minimum revision |
| Consumer restart | Crash sau effect trước checkpoint | Event replay không tạo effect trùng |
| Lease hết hạn | Pause old worker | Fencing ngăn worker cũ |
| Dedupe record sắp hết TTL | Retry muộn | Retention/policy không tạo giao dịch mới sai |
| Directory route cũ | Chậm cập nhật owner epoch | Stale owner bị từ chối |
| Payment provider timeout | Commit thành công, mất ACK | Reconciliation/provider idempotency xử lý đúng |
| 1000 clients retry cùng lúc | Synchronize retries | Backoff/jitter, rate limit và capacity hoạt động |

### 31.3. Inject lỗi sau commit là quan trọng

Chỉ test “mạng lỗi trước khi server nhận request” là chưa đủ. Cần thử đúng thời điểm:

~~~text
Server commit
     |
     X  drop ACK here
     |
Client retry
~~~

Đây là một trong những nguồn duplicate effects khó phát hiện nhất trong môi trường bình thường.

### 31.4. Các bất biến kiểm thử

Ví dụ:

~~~text
For each operationId:
    terminal business result is stable
    no more than one logical charge

For each (eventId, seatId):
    confirmed owner count <= 1

For each lease-controlled resource:
    old epoch cannot commit after new epoch takes authority
~~~

Phải kiểm chứng trên trạng thái **nguồn có thẩm quyền**, không chỉ số HTTP successes.

### 31.5. Đo hiệu năng và đúng đắn cùng lúc

Chạy workload:

- Không hedge.
- Hedge sau p95 với tối đa một attempt.
- Hedge theo ngưỡng p99.
- Hedge khi đang overload.

Đo p99 latency, logical success, extra attempts, read/write pressure, timeout và duplicate effects. Chính sách nào nhanh hơn nhưng gây sai business outcome phải bị loại.

### 31.6. An toàn thử nghiệm

Fault injection có thể làm gián đoạn hệ và gây side effects thật. Dùng môi trường kiểm thử, dữ liệu giả lập, payment sandbox, quyền hạn/giới hạn phù hợp và kế hoạch rollback. Không cố ý làm hỏng production không có phê duyệt.

## 32. Checklist thiết kế trước khi bật retry hoặc hedge

### 32.1. Xác định operation

- Logical operation là gì?
- Có mutation hoặc external side effect không?
- Có thể chạy đồng thời hai attempts không?
- Phạm vi invariant nằm ở key, partition, shard, Region hay hệ ngoài?

### 32.2. Xác định nguồn quyết định

- Node/leader/quorum nào được commit?
- Có conditional write/transaction đúng phạm vi không?
- Có owner epoch và fencing khi failover không?
- Nếu đa Region nhận ghi, có global ordering/authority phù hợp không?

### 32.3. Xác định duplicate contract

- OperationId ổn định qua mọi attempt?
- Payload canonical/fingerprint có được kiểm tra?
- Dedupe result có bền vững và giữ đủ lâu?
- Marking và effect có atomic hoặc có recovery không?
- External provider có idempotency theo operationId không?

### 32.4. Xác định retry policy

- Những lỗi nào chắc chắn retryable?
- Timeout sau gửi có outcome chưa rõ không?
- Combined attempt budget là bao nhiêu?
- Deadline tổng cho người dùng là gì?
- Có backoff/jitter và rate limiting khi overload không?

### 32.5. Xác định read contract

- GET có thuần đọc không?
- Đọc eventual, bounded staleness hay linearizable?
- “Fastest response” có cần minimum version/quorum validation?
- Replica nào có quyền phục vụ request theo Region và data residency?

### 32.6. Xác định quan sát

- Log/trace nối logical operation với attempts?
- Có metric duplicate effect và unknown outcome?
- Có dashboard latency cả trước và sau khi hedge?
- Có báo động khi reconciliation queue tồn đọng?

## 33. Những hiểu lầm thường gặp

| Hiểu lầm | Điều đúng hơn |
|---|---|
| Timeout chứng minh server chưa thực thi | Server có thể commit rồi mất response |
| Client cancel khiến server rollback | Cancellation thường best effort, không phải transaction rollback |
| Hai replicas cùng lưu bản sao nghĩa hai business operations | Replication khác duplicate execution |
| Hedge luôn chỉ dùng cho read | Có hệ cho speculative attempts rộng hơn, nhưng side effects cần bảo vệ |
| Hedged GET luôn an toàn | GET có thể tạo effect ngầm hoặc đọc stale trái contract |
| Fastest response luôn tốt nhất | Response phải hợp consistency/minimum revision |
| Một PUT giống hệt luôn an toàn | Trigger, audit, timestamps, concurrency có thể đổi semantics |
| Commutative là idempotent | Hai lần cộng không tương đương một lần cộng |
| Retry một INCREMENT luôn được vì DB có quorum | Quorum có thể commit hai commands hợp lệ |
| Consensus tự dedup mọi user action | Hai log entries cùng payload có thể đều được apply |
| Driver retryable write bảo vệ mọi application retry | Hai API calls độc lập có thể là hai logical writes |
| CAS trên seat thay thế opId | CAS bảo vệ seat owner nhưng không tự replay kết quả retry |
| OpId dedup thay thế unique constraint | Hai opIds khác nhau vẫn có thể tranh cùng resource |
| SET NX rồi làm effect tương đương atomic transaction | Worker có thể chết sau claim trước effect |
| Effect trước marker rồi thêm marker sẽ an toàn | Crash giữa hai bước có thể duplicate |
| Redis lock TTL đảm bảo worker cũ dừng | Pause rồi resume tạo stale worker |
| Chỉ cần check epoch trước write | Nếu check và write không nguyên tử vẫn có race |
| Hai regions local conditional writes luôn global unique | Eventual multi-Region có thể có concurrent local winners |
| Nếu một attempt thành công thì những attempt khác đã dừng | Loser có thể đang chạy hoặc đã commit |
| Driver hỗ trợ speculative execution thì mọi CQL đều phù hợp | Phải xem idempotency/consistency/query type |
| Bật hedging p99 giảm chắc chắn tốt | Extra load có thể hại cluster/tenants khác |
| Retry ở mỗi tầng tối đa ba lần thì chỉ có ba attempts | Nested retries có thể nhân số attempts |
| Exactly once message delivery tự tạo exactly once business effect | Cần transactional dedup và external idempotency |
| Dedupe bằng payload là đủ | Hai ý định mới có thể có payload giống nhau |
| Dedupe record TTL ngắn luôn ổn | Retry muộn có thể tạo effect mới |
| Error 409 ở retry chứng minh người khác thắng | Có thể chính attempt trước đã claim thành công |
| Chỉ theo dõi HTTP 200 là đủ | Phải đo logical outcome và effect cardinality |
| Hệ chỉ cần HA, không cần reconciliation | Unknown outcomes và external effects cần đối soát |

## 34. Bài tập 1 — hai nodes cùng xử lý một lệnh

Một client gửi:

~~~text
INCREMENT viewCount for PAGE#P101
~~~

Đường truyền:

~~~text
Attempt A đến Node A ở t=0.
Attempt B đến Node B ở t=100 ms.
Node B trả OK ở t=120 ms.
Node A trả OK ở t=300 ms.
~~~

Hãy trả lời:

1. Nếu không có dedup, counter có thể tăng bao nhiêu lần?
2. Client bỏ phản hồi A có làm A rollback không?
3. Thay operation bằng PUT viewCount=100 có còn cùng rủi ro trạng thái không?
4. Nếu PUT phát sinh audit event, rủi ro gì vẫn còn?
5. Thay đổi nào cần thực hiện để một logical increment chỉ có một effect?

## 35. Bài tập 2 — phân biệt retry, hedge và quorum read

Cho ba tình huống:

~~~text
A. Client chờ A timeout, sau đó gửi B.
B. Client gửi A, đợi 80 ms rồi gửi B khi A chưa trả.
C. Coordinator gửi A+B, chờ đủ kết quả để đạt R=2.
~~~

1. A, B, C thuộc loại nào?
2. Loại nào có thể có attempts đồng thời?
3. Trong C, có thể lấy ngay phản hồi đầu tiên từ A không?
4. Nếu có một replica stale, consistency contract quyết định thế nào?
5. Những tình huống nào tăng resource amplification?

## 36. Bài tập 3 — tính số attempts do nested retries

API đi qua bốn tầng, mỗi tầng được phép tối đa ba attempts (gồm lần đầu), và mỗi tầng có thể gọi tầng kế tiếp nhiều lần.

1. Trong trường hợp xấu nhất của mô hình đơn giản, số leaf attempts bằng bao nhiêu?
2. Vì sao con số này không nhất thiết xảy ra trong một request bình thường?
3. Thiết kế một **shared deadline**.
4. Phân công chỉ một hoặc hai tầng có quyền retry để giảm amplification.
5. Nếu driver cũng hedge hai replicas cho mỗi leaf attempt, upper-bound logic có thể đổi thế nào?

**Gợi ý:** Không cộng bốn lần ba khi mọi retry lồng nhau có thể xảy ra.

## 37. Bài tập 4 — timeout sau khi commit

~~~text
t0: POST reserve S101, opId=RESERVE-101
t1: Database commits reservation R901
t2: Response lost
t3: Client timeout
t4: Client retries with opId=RESERVE-101
~~~

1. Ở t3, trạng thái nào đúng: REJECTED, FAILED hay UNKNOWN?
2. Server cần lưu gì trong operation ledger?
3. Attempt thứ hai nên trả reservationId nào?
4. Nếu chỉ Query một search index eventual không thấy R901, có được tạo reservation mới không?
5. Nếu client tạo opId mới ở t4, rủi ro gì phát sinh?

## 38. Bài tập 5 — một ghế, hai ý định khác nhau

~~~text
Client X -> opId=R101, seat=S101, owner=X.
Client Y -> opId=R102, seat=S101, owner=Y.
~~~

1. Dedupe theo opId có ngăn cả hai thành công không?
2. Cần bảo vệ invariant gì trên business key?
3. Nếu dùng conditional write IF owner absent, kết quả hợp lệ là gì?
4. Nếu winner X timeout rồi retry với R101 và thấy condition failed, làm sao biết mình đã thắng?
5. Tại sao LWW không giải quyết hai email xác nhận đã được gửi?

## 39. Bài tập 6 — thiết kế operation ledger

Hãy định nghĩa schema logic:

~~~text
Operation(
  tenantId,
  operationType,
  operationId,
  payloadHash,
  status,
  result,
  ownerEpoch,
  createdAt,
  updatedAt
)
~~~

1. Chọn khóa định danh duy nhất.
2. Khi cùng opId nhưng payloadHash khác, phải trả gì?
3. Khi hai nodes cùng claim, storage cần atomic primitive nào?
4. IN_PROGRESS bị treo do crash xử lý thế nào?
5. SUCCEEDED phải giữ bao lâu?
6. Nếu business effect ở store khác, vì sao một marker riêng không đủ?

## 40. Bài tập 7 — fencing và lease hết hạn

~~~text
Worker A giữ job J101 epoch=12, lease 30 giây.
A bị pause 40 giây.
Worker B được cấp epoch=13.
A và B đều gửi UPDATE trạng thái job.
~~~

1. Có thể có hai workers cùng chạy code không?
2. Tại sao Redis lock TTL không chặn A?
3. Resource đích cần điều kiện gì để từ chối epoch 12?
4. Kiểm tra epoch và write trên hai calls tách biệt tạo race gì?
5. Nếu A gọi API external không hỗ trợ fencing, cần idempotency và reconciliation ra sao?

## 41. Bài tập 8 — hedged read bị stale

Một client vừa ghi profile version=12 và yêu cầu GET phải read-your-writes:

~~~text
Replica A trả version=12 sau 80 ms.
Replica B trả version=11 sau 5 ms.
~~~

1. Policy “first response wins” có đúng không?
2. Minimum revision cần là bao nhiêu?
3. Nếu B trả sớm nhưng dưới minimum revision, nên làm gì?
4. Quorum read khác fastest-success ra sao?
5. Có nên gửi hedge sang Region vi phạm data residency không?

## 42. Bài tập 9 — Cassandra counter và speculative execution

Một hệ dùng CQL:

~~~sql
UPDATE page_views
SET view_count = view_count + 1
WHERE page_id = 'P101';
~~~

Ứng dụng bật speculative executions ở driver.

1. Thao tác này có idempotent không?
2. Nếu hai coordinators đều thực thi, counter có thể tăng mấy lần?
3. Consistency level QUORUM có tự dedup hai mutations logic không?
4. Đề xuất một mô hình eventId + sharded counter hoặc aggregate có dedup.
5. Những loại CQL operations nào cần đặc biệt cẩn thận với retry?

## 43. Bài tập 10 — MongoDB retryable writes

Một MongoDB driver có retryable writes trong cấu hình được hỗ trợ. Application nhận timeout rồi tự gọi lại một updateOne với $inc như một lệnh mới.

1. Vì sao driver retry và application retry không luôn tương đương?
2. Session/statement identity có vai trò gì trong cơ chế retryable writes?
3. Nếu hai updateOne là hai logical commands mới, counter có thể tăng hai lần không?
4. Nếu transaction callback có gọi payment provider, retry callback có rủi ro nào?
5. Đề xuất một operation ledger ở mức domain.

## 44. Bài tập 11 — DynamoDB conditional write

Một ứng dụng tạo:

~~~text
PK=IDEMPOTENCY#R101
state=IN_PROGRESS
~~~

bằng conditional PutItem.

1. Cách này ngăn hai attempts cùng tạo marker như thế nào?
2. Vì sao marker riêng không tự bảo vệ reservation effect?
3. Thiết kế một TransactWriteItems phù hợp nếu keys nằm trong phạm vi transaction được hỗ trợ.
4. Nếu retry transaction sau thời hạn idempotency của API, cần cơ chế gì?
5. Nếu Global Tables eventual nhận hai conditional writes khác Region đồng thời, có thể tự suy global uniqueness không?

## 45. Bài tập 12 — Redis lock và Lua script

Một hệ:

~~~text
SET lock:payment:O101 "A" NX PX 30000
charge provider
DEL lock:payment:O101
~~~

1. Worker A bị pause hơn 30 giây gây rủi ro gì?
2. Nếu A xóa lock sau khi B đã nhận quyền, lỗi nào có thể xảy ra?
3. Vì sao nên dùng compare-owner token khi release lock?
4. Lua script bảo vệ atomicity trong phạm vi Redis nhưng có bao trùm provider không?
5. Provider idempotency key nên gắn với logical order/payment intent nào?

## 46. Bài tập 13 — queue redelivery

Một worker nhận eventId=EVT101:

~~~text
Read event.
Update database.
Crash before acknowledging message.
Broker redelivers EVT101 to another worker.
~~~

1. Vì sao redelivery có thể là hành vi bình thường của broker?
2. Nếu event tạo một audit record với ID ngẫu nhiên mỗi lần, có nguy cơ gì?
3. Thiết kế inbox dedup keyed theo eventId.
4. Marker dedup và effect cần transaction/reconciliation như thế nào?
5. Nếu cùng business operation bị phát thành EVT101 và EVT102, eventId-only dedup còn đủ không?

## 47. Bài tập 14 — chọn hedge delay

Một endpoint GET có:

~~~text
10.000 logical requests/phút.
95% hoàn tất trước 80 ms.
5% còn đang chờ sau 80 ms.
Mỗi request pending sẽ hedge tối đa 1 lần.
~~~

1. Có khoảng bao nhiêu extra attempts nếu phân bố này giữ ổn định?
2. Attempt amplification xấp xỉ bao nhiêu?
3. Nếu hai replicas cùng gặp shared storage bottleneck, hedge có chắc giảm p99 không?
4. Khi QPS đã gần capacity limit, policy nên thay đổi thế nào?
5. Vì sao cần đo latency những tenants không được hedge?

## 48. Bài tập 15 — kiểm tra end-to-end idempotency

Một ứng dụng có các bước:

~~~text
Create order -> Outbox -> Consumer -> Payment provider -> Email
~~~

Hãy lập test với lỗi:

1. Order commit, response mất.
2. Outbox event giao hai lần.
3. Consumer chết sau khi charge.
4. Payment provider response timeout.
5. Email provider gửi thành công nhưng response mất.
6. Worker cũ và mới cùng chạy sau lease expiry.

Với mỗi lỗi, xác định operationId/idempotency key, nơi lưu marker, trạng thái UNKNOWN và cách đối soát.

## 49. Bài tập 16 — tracing các attempts

Bạn nhìn thấy:

~~~text
operationId=R101
attempt=A status=timeout duration=800ms
attempt=B status=success duration=120ms
attempt=C status=canceled duration=200ms
~~~

1. Có thể kết luận A không commit không?
2. Có thể kết luận C không tạo effect không?
3. Những log/trace/ledger nào cần tra để xác nhận?
4. Tại sao attempt success count không thay thế logical outcome?
5. Đề xuất các metric bảo vệ SLO và theo dõi duplicate effects.

## 50. Bài tập 17 — phân tích sự cố duplicate charge

Một đợt triển khai bật retry POST ở gateway, speculative execution ở DB driver và retry tại worker. Trong 10 phút:

~~~text
Logical payment operations: 25.000
Physical API attempts:      34.000
Provider charge records:    25.170
Duplicate charge candidates: 170
~~~

1. Tính attempt amplification.
2. Vì sao 25.170 provider charges chưa chắc tương đương 25.170 logical payments thành công?
3. Có thể suy ngay tất cả 170 là duplicate thật không?
4. Lập runbook khoanh vùng và đối soát.
5. Đề xuất những tầng retry cần tắt/giới hạn.
6. Thiết kế giải pháp domain idempotency + provider idempotency + outbox.
7. Nêu các fault-injection tests cần chạy trước khi bật lại.

## 51. Tổng kết

**Thực thi dự phòng** như hedged request hoặc speculative execution là kỹ thuật giảm ảnh hưởng của những đường xử lý chậm. Nhưng **nhiều attempts của cùng một logical operation** có thể chạy đồng thời, tiếp tục sau cancellation và thậm chí cùng commit một side effect.

Những nguyên tắc cần nhớ:

1. **Timeout không phải bằng chứng thất bại.** Server có thể đã commit trước khi response mất.
2. **Hedge khác retry tuần tự và khác replication.** Một request dự phòng là thêm một lần thực thi ở tầng client/driver, không tự là bản sao nội bộ của một write.
3. **Client chỉ chọn một response không ngăn attempts khác chạy.** Cancel future/socket không phải rollback.
4. **Đọc dự phòng phải đáp ứng consistency contract.** Fastest stale replica có thể cho kết quả sai nếu endpoint cần read-your-writes, minimum revision hoặc linearizability.
5. **Ghi non-idempotent cần bảo vệ đặc biệt.** Increment, append, create với ID mới, payment và email có thể tạo duplicate effects.
6. **OperationId phải ổn định qua mọi attempts.** attemptId chỉ để tracing; payload fingerprint và tenant scope ngăn dùng nhầm idempotency key.
7. **Dedup cần nguyên tử ở đúng phạm vi.** Read-then-write hoặc marker rồi effect không phải giải pháp hoàn chỉnh khi có crash.
8. **Business invariant khác dedup.** Hai users với hai operation IDs vẫn cần tranh quyền ở một nguồn quyết định duy nhất khi chọn cùng ghế hoặc username.
9. **Lease không ngăn worker cũ sống lại.** Fencing epoch và atomic check-and-act giúp ngăn owner đã hết quyền tiếp tục ghi.
10. **Consensus bảo vệ một quyết định trong group**, không tự dedup commands và không tự bảo vệ side effects ở hệ khác.
11. **Retry nhiều tầng có thể nhân tải.** Cần combined attempt budget, deadline tổng, backoff/jitter và overload control.
12. **Hedging cần đo hiệu quả ròng.** So p99 và logical success với physical attempts, tài nguyên tiêu thụ, sự cố stale read và duplicate effect.
13. **Outbox, inbox, provider idempotency và reconciliation** giúp xử lý giao dịch đi qua nhiều hệ độc lập.
14. **Fault injection sau commit là bài test thiết yếu.** Kỹ thuật chỉ thực sự an toàn khi chứng minh được xử lý đúng trường hợp commit thành công nhưng ACK thất lạc.

Câu hỏi cuối cùng trước khi bật speculative execution không phải chỉ là **“Có giảm p99 không?”**, mà là:

> **“Nếu hai node cùng nhận một ý định, mỗi node có thể thực hiện side effect nào, cơ chế nào bảo vệ một kết quả nghiệp vụ duy nhất, và chúng ta xác minh điều đó ra sao khi timeout, failover, cancellation hoặc retry xảy ra?”**







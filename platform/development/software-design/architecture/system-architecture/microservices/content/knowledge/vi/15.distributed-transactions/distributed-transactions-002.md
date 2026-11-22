# Giao thức hai pha (2PC), điều kiện áp dụng và đánh đổi

## 1. Bối cảnh: tại sao cần giao dịch phân tán?

Trong một cơ sở dữ liệu quan hệ, transaction thường mang lại các bảo đảm ACID trong phạm vi mà database hỗ trợ. Ví dụ, chuyển tiền giữa hai tài khoản **cùng một database** có thể dùng một transaction để trừ tài khoản A và cộng tài khoản B: hoặc cả hai thay đổi commit, hoặc cả hai rollback.

Trong kiến trúc microservices, hai bước có thể nằm ở hai database hoặc hai resource manager khác nhau:

~~~text
                  Transaction Coordinator?
                           |
              +------------+-------------+
              |                          |
        Orders database             Inventory database
              |                          |
        Tạo đơn hàng             Giữ tồn kho tương ứng
~~~

Một lần gọi từ Checkout tới Orders DB thành công không làm cho lần gọi tới Inventory DB tự động thành công. Nếu bước thứ hai lỗi, hệ thống có thể ở trạng thái chỉ một bên đã thay đổi.

**Two-Phase Commit (2PC)** là một giao thức phối hợp commit cho nhiều tài nguyên có khả năng tham gia giao dịch, nhằm đưa ra **một quyết định toàn cục**: COMMIT nếu tất cả participant đã đồng ý và có thể cam kết, ngược lại ABORT/ROLLBACK. Coordinator phải xử lý trạng thái durable, thông điệp có thể mất, participant có thể crash, và các lần khôi phục sau sự cố.

2PC không đồng nghĩa với “thực hiện hai API lần lượt”, không phải lời hứa hoạt động liên tục khi mạng bị phân vùng, và không tự áp dụng được cho dịch vụ thanh toán bên thứ ba chỉ có HTTP API.

### Mục tiêu học tập

- Mô tả vai trò **coordinator** và **participant/resource manager**.
- Trình bày chính xác **prepare/voting phase** và **decision/commit phase**.
- Hiểu vai trò của durable log, prepared state, in-doubt transaction và recovery.
- Nhận diện vấn đề blocking, lock duration, coordinator outage và heuristic outcome.
- Phân biệt 2PC với XA/JTA, local DB transaction, consensus, Saga, TCC và transactional outbox.
- Biết khi nào nên cân nhắc 2PC và khi nào không nên.
- Xây dựng ví dụ, thước đo, checklist và runbook vận hành thích hợp.

**Thông điệp chính:** 2PC ưu tiên tính nguyên tử của quyết định commit xuyên nhiều tài nguyên được phối hợp, nhưng phải trả giá bằng **sự phụ thuộc phối hợp**, chi phí thời gian và khả năng chờ khóa kéo dài trong một số tình huống lỗi.

## 2. Ba cấp giao dịch cần tách bạch

| Phạm vi | Cơ chế thường gặp | Điều được giải quyết | Giới hạn |
|---|---|---|---|
| **Một database** | Local transaction (BEGIN/COMMIT/ROLLBACK) | Atomicity trong cùng resource manager | Không bao phủ DB, broker hay API ngoài transaction |
| **Nhiều tài nguyên có enlistment** | 2PC qua transaction manager/XA hoặc cơ chế tương đương | Một quyết định commit/abort phối hợp | Blocking, khóa dài, hỗ trợ XA, recovery log |
| **Nhiều dịch vụ độc lập** | Saga, orchestration/choreography, outbox, idempotent command | Hoàn thành workflow theo bước và bù trừ khi cần | Thường có trạng thái trung gian, eventual consistency, compensation không phải rollback ACID |

Ví dụ:

- **Trừ và cộng tiền trong cùng một PostgreSQL DB:** local transaction là lựa chọn rõ ràng hơn nếu không cần nhiều resource manager.
- **Cập nhật hai DB độc lập nhưng cả hai hỗ trợ XA, cùng một ứng dụng điều phối:** có thể cân nhắc 2PC nếu giao dịch ngắn và điều kiện vận hành đáp ứng.
- **Đặt hàng qua Checkout, Inventory, Payment Gateway:** thường không thể đơn giản dùng XA 2PC toàn chuỗi vì provider bên ngoài không “prepare” và giữ tài nguyên theo giao thức XA. Cần workflow với trạng thái, idempotency và xử lý kết quả không chắc chắn.

**Cẩn trọng:** hai bảng ở hai schema cùng một database engine có thể vẫn nằm trong một local transaction. Ngược lại, hai kết nối được mở tới hai database/resource manager độc lập thường không mặc nhiên thuộc cùng một transaction chỉ vì nằm trong một method được gắn annotation.

## 3. Các thành phần trong 2PC

### 3.1. Coordinator (transaction coordinator)

Coordinator điều phối toàn bộ giao dịch. Nó:

1. Xác định các participant cần tham gia.
2. Yêu cầu từng participant chuẩn bị commit.
3. Thu thập phiếu **YES/READY** hoặc **NO/ABORT**.
4. Quyết định COMMIT chỉ khi mọi participant cần thiết đã đồng ý.
5. Ghi quyết định toàn cục vào log bền vững trước khi gửi COMMIT theo giao thức phù hợp.
6. Gửi kết quả cho participant, nhận xác nhận và hoàn tất cleanup.
7. Khôi phục giao dịch đang dang dở sau crash, dựa trên durable log.

Coordinator không nhất thiết là một microservice riêng do đội dự án viết tay. Trong môi trường Java enterprise, một **transaction manager** có thể thực hiện vai trò này qua API JTA/XA.

### 3.2. Participant / resource manager

Participant là một tài nguyên hỗ trợ chuẩn bị và cam kết/rollback theo giao thức, ví dụ một XA-capable relational database hoặc hệ thống messaging có XA support phù hợp.

Khi bỏ phiếu YES trong PREPARE, participant phải đạt trạng thái **đã sẵn sàng commit và có thể khôi phục** nếu tiến trình crash. Thông thường điều này đòi hỏi dữ liệu chuẩn bị hoặc log được lưu durable. Participant cũng có thể giữ lock, version hoặc tài nguyên khác để bảo vệ tính hợp lệ của quyết định cuối.

Participant **không được tự tuyên bố COMMIT toàn cục** chỉ vì đã trả YES. Nó phải đợi quyết định chính thức từ coordinator, trừ những cơ chế recovery/heuristic đặc biệt với rủi ro cần ghi nhận.

### 3.3. Transaction identifier

Một giao dịch phân tán có định danh để coordinator và participant phân biệt các lần chạy. Trong XA, định danh giao dịch thường có dạng **Xid** (gồm global transaction ID và branch qualifier). Xid phục vụ recovery và đối chiếu nhánh, không giống orderId hoặc paymentId ở tầng nghiệp vụ.

### 3.4. Durable log

Coordinator cần log bền vững để biết mình đã quyết định COMMIT hay ABORT khi khởi động lại. Participant cần biết mình đã PREPARED những nhánh nào, kể cả sau crash. Thiếu durable recovery state có thể khiến các bên không thể quyết định an toàn sau lỗi.

**Durable ở đây là một tính chất triển khai cần kiểm chứng**, không chỉ gọi một hàm logger ghi text vào stdout.

## 4. Thuật toán 2PC: hai pha rõ ràng

Giả sử có một coordinator C và hai participant A/B.

### 4.1. Pha một – PREPARE / VOTING

~~~text
Coordinator C                   Participant A                Participant B
     |                                |                            |
     |---------- PREPARE ------------>|                            |
     |------------------------------ PREPARE --------------------->|
     |                                |                            |
     |                         kiểm tra, giữ trạng thái       kiểm tra, giữ trạng thái
     |                         sẵn sàng commit               sẵn sàng commit
     |<---------- YES ---------------|                            |
     |<------------------------------ YES ------------------------|
     |                                |                            |
     |                      A, B đang PREPARED và chờ quyết định   |
~~~

Tại mỗi participant:

1. Kiểm tra transaction branch có hợp lệ và còn khả năng commit không.
2. Đồng bộ trạng thái cần thiết theo cơ chế durable của resource manager.
3. Bỏ phiếu YES nếu đã chuẩn bị thành công; hoặc NO nếu không thể.
4. Nếu YES, giữ các điều kiện cần thiết để về sau COMMIT đúng và không tự ý trả quyền điều khiển cho một giao dịch xung đột.
5. Chờ quyết định toàn cục.

Tùy resource manager, participant có thể trả kết quả tối ưu **read-only** nếu nhánh không thay đổi gì; đây là optimization theo giao thức hỗ trợ, không phải một phiếu YES thông thường bắt buộc cần commit.

### 4.2. Pha hai – GLOBAL DECISION

Nếu mọi participant cần thiết bỏ phiếu YES, coordinator có thể quyết định COMMIT.

~~~text
Coordinator C                   Participant A                Participant B
     |                                |                            |
     |==== durable COMMIT decision ===|============================|
     |---------- COMMIT ------------->|                            |
     |------------------------------ COMMIT --------------------->|
     |                                |                            |
     |                     commit local work              commit local work
     |                     release resources              release resources
     |<----------- ACK --------------|                            |
     |<------------------------------ ACK ------------------------|
     |                                |                            |
     |------------ hoàn tất theo log/recovery policy -------------|
~~~

**Điểm thứ tự quan trọng:** khi coordinator đã có quyết định COMMIT bền vững, sự cố mạng không được khiến nó đổi sang ABORT cho giao dịch đó. Nó phải tiếp tục đưa quyết định COMMIT tới các participant trong quá trình recovery.

Nếu bất kỳ participant cần thiết bỏ phiếu NO, hoặc coordinator không thể đạt điều kiện prepare trước khi đưa ra quyết định commit, giao dịch đi theo đường ABORT/ROLLBACK theo protocol và trạng thái hiện có.

~~~text
A vote YES, B vote NO
          |
          v
Coordinator chọn GLOBAL ABORT
          |
          +--> ROLLBACK A (nếu A đã prepare)
          |
          +--> ROLLBACK B / dọn nhánh
          |
          v
Ghi nhận và hoàn tất sau các ACK/recovery
~~~

Một participant chỉ “nhận được PREPARE request” chưa đủ để coi nó đã đồng ý. Phải phân biệt **chưa trả lời**, **bỏ phiếu NO** và **đã bỏ phiếu YES**.

## 5. Ví dụ số dư trên hai database

Giả sử một ứng dụng nội bộ phải chuyển 100 đơn vị tiền từ tài khoản A ở DB-1 sang tài khoản B ở DB-2. Hai database đều có cơ chế prepare/recovery cần thiết.

Nghiệp vụ yêu cầu:

~~~text
Trước:
  A = 500
  B = 200

Sau một giao dịch thành công:
  A = 400
  B = 300

Nếu giao dịch bị abort:
  A = 500
  B = 200
~~~

Hệ thống không được kết thúc ở trạng thái **A = 400, B = 200** hoặc **A = 500, B = 300** nếu giao dịch được khẳng định là atomic trong phạm vi hai resource manager.

Một protocol minh họa:

~~~text
1. Transaction Manager mở global transaction X.

2. Enlist DB-1 và DB-2 vào X.

3. Trong nhánh DB-1:
   UPDATE accounts SET balance = balance - 100
   WHERE id = 'A' AND balance >= 100;

4. Trong nhánh DB-2:
   UPDATE accounts SET balance = balance + 100
   WHERE id = 'B';

5. TM yêu cầu PREPARE DB-1 và DB-2.
   DB-1: YES
   DB-2: YES

6. TM ghi COMMIT decision bền vững.

7. TM gửi COMMIT tới cả hai DB.
   Khi có đủ xác nhận, giao dịch được dọn dẹp.
~~~

Đây là sơ đồ luồng logic, không phải lệnh SQL có thể tự động thực hiện 2PC. Mỗi DB phải có invariant và concurrency control đúng; số dư A không âm là điều kiện local cần bảo vệ.

**Phạm vi ví dụ:** giả định hai resource manager đều hỗ trợ chuẩn bị và commit, transaction manager có durable recovery log, dữ liệu không bị sửa qua đường bypass, và tất cả thay đổi tham gia được enlist hợp lệ. Nếu một dịch vụ khác sửa A ngoài transaction, 2PC không bảo vệ được invariant ngoài ranh giới đã thiết kế.

## 6. Trường hợp thành công và thất bại

### 6.1. Đường thành công

- Cả hai participant trả YES.
- Coordinator ghi durable COMMIT.
- Participant nhận COMMIT, hoàn tất nhánh local và ACK.
- Các lock/tài nguyên được giải phóng theo cơ chế DB.

### 6.2. Một participant từ chối prepare

Ví dụ Inventory DB phát hiện vi phạm constraint hoặc không thể bảo đảm tài nguyên.

- Inventory trả NO hoặc prepare thất bại.
- Coordinator quyết định ABORT nếu chưa có durable COMMIT.
- Mọi participant đã prepare phải rollback theo quyết định.
- Caller nhận failure khi transaction manager xác định được kết quả.

Không nên diễn giải mọi lỗi prepare thành “sẽ tự retry an toàn”. Cần xét lỗi nào tạm thời, idempotency của yêu cầu nghiệp vụ và khả năng có nhánh chưa được xử lý xong.

### 6.3. Coordinator crash sau khi các participant đã YES

Đây là bài toán kinh điển.

~~~text
A: PREPARED ---- lock / resource held ---- ?
B: PREPARED ---- lock / resource held ---- ?
C: coordinator crash hoặc mất liên lạc
~~~

A và B không thể tự xác định liệu coordinator đã chọn COMMIT hay sẽ ABORT, trừ khi có cơ chế truy vấn durable decision/recovery được thiết kế đúng. Chúng có thể nằm trong trạng thái **in-doubt**, giữ tài nguyên và **chặn công việc khác**.

Khi coordinator khôi phục, nó dùng log để tiếp tục quyết định. Nếu đã có durable COMMIT, coordinator phải hoàn tất COMMIT. Nếu chưa có quyết định commit bền vững và protocol cho phép quyết định ABORT khi recovery, nó phải phục hồi theo đúng trạng thái và quy tắc của giao thức.

**2PC là blocking protocol trong mô hình lỗi thông thường.** Chỉ “đặt coordinator ở ba máy” không tự loại bỏ mọi tình huống blocked dưới network partition; phải xem chính xác cơ chế log và consensus/recovery nếu có.

### 6.4. Participant crash sau YES

Participant có thể đã lưu prepared state nhưng chưa nhận COMMIT. Sau restart, resource manager cần **recover in-doubt branches** và nhận quyết định từ transaction manager, không được coi crash là phép rollback tự động an toàn.

Nếu log/transaction state mất hoặc bị sửa thủ công, recovery có thể yêu cầu điều tra và can thiệp theo quy trình được kiểm soát.

### 6.5. Client timeout sau khi coordinator quyết định

~~~text
Client gửi transfer request
      |
TM hoàn thành prepare A/B
      |
TM ghi durable COMMIT
      |
Client timeout, response bị mất
      |
TM vẫn tiếp tục commit A/B
~~~

Client không thể kết luận đã rollback chỉ vì timeout. Lời gọi lại cùng lệnh có thể tạo một **giao dịch nghiệp vụ mới** nếu không có idempotency key hoặc business operation ID.

2PC bảo vệ atomicity giữa các resource đã enlist, **không tự** cho phép client retry HTTP POST tạo giao dịch mà không tạo side effect kép.

## 7. Bảng lỗi và hành vi mong đợi

| Điểm xảy ra lỗi | Trạng thái có thể có | Hành vi phục hồi đúng |
|---|---|---|
| Participant lỗi trước khi bỏ phiếu YES | Chưa chuẩn bị thành công | Coordinator có thể quyết định ABORT nếu chưa quyết định COMMIT |
| Participant trả NO | Global prepare thất bại | ABORT và rollback các nhánh liên quan |
| Participant đã YES, coordinator chưa gửi quyết định | Nhánh PREPARED/in-doubt | Chờ hoặc truy vấn quyết định qua recovery |
| Coordinator crash trước durable COMMIT | Có thể còn các nhánh prepared | Dùng durable protocol state để xác định ABORT/tiếp tục recovery |
| Coordinator crash sau durable COMMIT | Quyết định COMMIT đã cố định | Phát lại COMMIT tới participant chưa ACK |
| Participant crash sau YES | Prepared branch tồn tại trong durable recovery state | Khôi phục và nhận kết quả toàn cục |
| Mất network giữa coordinator và participant | Không chắc participant đã nhận quyết định | Retry control message/recover; không đoán kết quả |
| Client HTTP timeout | Kết quả nghiệp vụ chưa rõ đối với client | Query theo operation ID; retry idempotent có giới hạn |
| Lock giữ quá lâu | Các giao dịch khác có thể chờ | Quan sát prepared age/lock wait, khôi phục TM thay vì tùy tiện force rollback |
| Bên thứ ba xử lý ngoài XA | Tác dụng phụ không thuộc global transaction | Dùng giao thức nghiệp vụ, outbox, reconciliation hoặc compensation |

Trong thực tế, trường hợp lỗi có thể còn phức tạp hơn do vendor timeout, heuristic decision, bug, mất durable log hoặc lỗi hạ tầng. Bảng này mô tả nguyên tắc, không thay thế tài liệu transaction manager/resource manager đang triển khai.

## 8. Tính atomic không đồng nghĩa mọi tính chất khác được bảo đảm

2PC hướng đến **atomic global commit/abort** trong phạm vi các participant đã enlist và giả định recovery phù hợp. Nó không tự mang lại:

- **Isolation level đồng nhất:** database A có thể dùng READ COMMITTED trong khi DB B có cơ chế isolation khác; tính serializable của toàn bộ nghiệp vụ không tự được suy ra từ việc có 2PC.
- **Business invariant đúng:** nếu code không kiểm tra số dư, đơn giá hoặc quyền ghi, global commit vẫn có thể commit trạng thái nghiệp vụ sai.
- **Exactly-once HTTP request:** client timeout và retry hai lệnh mới có thể thực hiện nghiệp vụ hai lần.
- **Giao dịch với mọi API:** không thể prepare/commit một API HTTP tùy ý.
- **High availability trong network partition:** các participant đã PREPARED có thể chờ coordinator.
- **Latency thấp:** prepare/decision bổ sung round-trip, durable log và thời gian giữ resource.
- **Thay đổi database độc lập:** coupling ở tầng transaction manager và resource vẫn tồn tại.
- **Rollback được tác dụng phụ ngoài transaction:** email đã gửi hoặc tiền đã bị đối tác thu không quay về chỉ vì XA resource rollback.

Vì vậy câu “2PC làm tất cả dữ liệu nhất quán” là quá rộng. Đúng hơn: 2PC phối hợp **quyết định commit của các tài nguyên tham gia**; các bảo đảm khác phụ thuộc vào logic nghiệp vụ và cơ chế từng resource.

## 9. Blocking: đánh đổi mang tính cấu trúc

### 9.1. Tại sao participant phải chờ?

Khi A đã trả YES, A đã cam kết với coordinator rằng nó có thể thực hiện COMMIT sau này. Nếu coordinator mất liên lạc, A không được tự quyết định ABORT chỉ vì muốn giải phóng lock, bởi coordinator có thể đã durable COMMIT và gửi COMMIT cho B.

Tương tự, A không được tự COMMIT khi chưa biết B có trả NO hay không.

Đây là trạng thái **không thể tự quyết định an toàn** của 2PC truyền thống. Tùy resource manager, prepared transaction có thể giữ:

- Row/table locks hoặc version constraints.
- Transaction log và các record recovery.
- Dung lượng WAL/redo/undo hoặc replication retention.
- Connection/resource manager structures.
- Các tác vụ khác bị chặn bởi resource đã được bảo lưu.

Những tài nguyên này có thể tồn tại lâu hơn request HTTP ban đầu. Đó là lý do **không nên kéo 2PC xuyên một workflow nhiều phút hoặc đợi người dùng thao tác**.

### 9.2. Blocking không giống downtime toàn hệ thống

Không nhất thiết mọi query trên cùng database sẽ đứng yên. Ảnh hưởng phụ thuộc lock scope, schema, storage engine và tài nguyên bị giữ. Nhưng nếu transaction prepared giữ khóa trên một hàng quan trọng, nhiều giao dịch khác có thể xếp hàng và gây incident.

Cần đo thực tế: prepared transaction count/age, lock wait, blocked sessions, throughput, log retention và recovery duration. Đặt cảnh báo sớm thay vì đợi database “đứng toàn bộ”.

## 10. Chi phí hiệu năng và vận hành

2PC đòi hỏi nhiều hơn một local commit:

1. Coordinator gửi prepare tới các participant.
2. Participant phải kiểm tra, bảo toàn trạng thái và trả vote.
3. Coordinator lưu quyết định bền vững.
4. Coordinator gửi commit/rollback.
5. Participant thực hiện, giải phóng tài nguyên và xác nhận.
6. Coordinator dọn trạng thái sau khi đủ bằng chứng.

Tùy công nghệ, một số bước có thể tối ưu, chạy song song hoặc loại bỏ trong trường hợp read-only/single resource. Tuy nhiên thông thường 2PC tăng:

- **Độ trễ commit:** thêm pha giao tiếp và disk durability.
- **Lock holding time:** tài nguyên có thể bị giữ qua nhiều round-trip.
- **Coupling về availability:** resource chậm hoặc unavailable có thể ngăn global completion.
- **Phức tạp recovery:** phải giữ log, Xid, prepared state và thông tin owner.
- **Chi phí network/connection:** kết nối resource phải đáp ứng thời gian giao dịch.
- **Khó mở rộng thành workflow dài:** nhiều participant làm tăng xác suất một thành phần bất ổn.
- **Độ khó thao tác vận hành:** in-doubt, heuristic recovery, log corruption và deadlocks.

Không có một con số “2PC chậm hơn local transaction bao nhiêu lần” đúng cho mọi hệ thống. Cần benchmark theo **số participant, latency giữa vùng, loại database, kích thước transaction, lock contention và tình huống lỗi**.

### Ví dụ minh họa thời gian (không phải chuẩn)

~~~text
Ứng dụng -> DB-A & DB-B, xử lý logic:    20 ms
PREPARE round-trip và durability:        15 ms
Coordinator decision log + COMMIT:       15 ms
Các chi phí lock/network khác:           10 ms
---------------------------------------------
Tổng trong ví dụ:                         60 ms
~~~

Thực tế có thể nhanh hoặc chậm hơn nhiều. Tail latency p95/p99 và thời gian phục hồi khi participant chết thường quan trọng hơn trung bình khi quyết định có dùng 2PC.

## 11. XA là gì và liên hệ ra sao với 2PC?

**XA** là giao diện giao dịch phân tán liên quan đến X/Open Distributed Transaction Processing. Một hệ thống Java có thể dùng XA để transaction manager phối hợp các resource manager như database hoặc JMS provider phù hợp.

Các khái niệm:

| Khái niệm | Vai trò |
|---|---|
| **Transaction manager (TM)** | Quản lý global transaction, enlist branches, quyết định và recovery |
| **XAResource** | Interface để resource manager tham gia global transaction |
| **Xid** | Định danh global transaction và branch |
| **XADataSource** | DataSource cung cấp XA-capable connections cho database |
| **prepare(Xid)** | RM chuẩn bị và bỏ phiếu ready/read-only hoặc báo lỗi |
| **commit(Xid, ...)** | Hoàn tất commit theo quyết định và cơ chế tối ưu tương ứng |
| **rollback(Xid)** | Rollback nhánh |
| **recover(...)** | Truy xuất các nhánh in-doubt cần reconciliation/recovery |
| **JTA / Jakarta Transactions** | API giao dịch và integration của ứng dụng Java |

**XA không tự xuất hiện khi ứng dụng có hai JDBC DataSource.** Cần cả hai resource được enlist trong một global transaction do **cùng transaction manager** quản lý, và transaction manager phải có recovery log bền vững. Nếu một nguồn dùng local transaction manager, nguồn còn lại dùng XA, kết quả có thể không còn atomic theo cách developer tưởng.

### 11.1. One-phase commit optimization

Nếu giao dịch chỉ có một resource manager cần commit, transaction manager có thể sử dụng **one-phase optimization** tùy chuẩn và triển khai thay vì thực hiện đầy đủ prepare/commit hai pha.

Đây không có nghĩa “2PC có thể bỏ prepare khi có hai DB” một cách tùy ý. Cần hiểu participant enlistment thực tế và quy tắc tối ưu của transaction manager.

### 11.2. Read-only vote

Một participant không có thay đổi cần commit có thể báo **XA_RDONLY** trong prepare, cho phép transaction manager không yêu cầu commit nhánh đó. Điều này có thể giảm chi phí, nhưng phụ thuộc cơ chế resource manager và không thay thế kiểm tra consistency ở tầng nghiệp vụ.

### 11.3. Heuristic outcomes

Một participant đôi khi có thể tự đưa ra quyết định cuối trong tình huống recovery/timeout bất thường, theo cơ chế gọi là **heuristic decision**. Khi các participant ra quyết định khác nhau, có thể xuất hiện **heuristic mixed**: một nơi commit, một nơi rollback.

Đây là sự cố nghiêm trọng, cần điều tra và đối soát nghiệp vụ. Không thể coi 2PC tuyệt đối ngăn mọi trạng thái phân kỳ trong tất cả điều kiện mất dữ liệu, thao tác quản trị hoặc heuristic intervention.

## 12. Ví dụ Java: transaction xuyên hai XA-capable DataSource

Đoạn dưới là **mẫu cấu trúc**, không phải ứng dụng chạy được chỉ bằng cách thêm annotation. Giả định môi trường Jakarta có transaction manager JTA/XA đã được cấu hình đúng, hai repository nối tới **hai XA-capable resources**, và các database đã sẵn sàng cho prepared transactions/recovery.

~~~java
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.transaction.Transactional;
import java.math.BigDecimal;

@ApplicationScoped
public class InternalTransferService {

    @Inject
    AccountLedgerRepository ledgerRepository;   // XA resource A

    @Inject
    ClearingLedgerRepository clearingRepository; // XA resource B

    @Transactional
    public void transfer(
            String operationId,
            String sourceAccount,
            String destinationAccount,
            BigDecimal amount
    ) {
        // Cần kiểm tra quyền, currency, amount, operationId.
        // Idempotency ở tầng nghiệp vụ vẫn là bắt buộc.
        ledgerRepository.debit(
            operationId,
            sourceAccount,
            amount
        );

        clearingRepository.credit(
            operationId,
            destinationAccount,
            amount
        );

        // Container / JTA transaction manager quyết định commit.
        // Annotation tự nó KHÔNG chứng minh hai resources đã enlist XA.
    }
}
~~~

Những điều **phải có ngoài đoạn code**:

1. Transaction manager có **persistent object store/recovery log**, không phải cấu hình tạm trong memory.
2. Cả hai DataSource được cấu hình **XA**, driver/database tương thích, enlist đúng vào một JTA transaction.
3. Các repository không tự mở connection ngoài transaction hoặc tự gọi local COMMIT.
4. Có handling cho constraint violation, rollback, transaction timeout và exception do TM cung cấp.
5. Có business operation ID/idempotency để client không tạo lệnh transfer kép sau timeout.
6. Có isolation/concurrency phù hợp để không trừ số dư vượt khả dụng.
7. Có tài liệu và runbook cho in-doubt XA branches.
8. Có kiểm thử crash ở từng thời điểm prepare/commit và khôi phục sau restart.

**Chú ý:** annotation cùng tên hoặc tương tự trong Spring, Jakarta và các thư viện khác không tự bảo đảm một transaction XA; cần kiểm tra **transaction manager thực sự được dùng**. Không bao giờ coi việc hai repository nằm trong một Java method là bằng chứng về 2PC.

## 13. Pseudocode của một transaction manager

Mã giả dưới minh họa luồng logic và vị trí recovery, **không phải** cách xây coordinator production. Một triển khai chính xác còn cần xử lý retry, crash, log, duplicate message, heuristic status, RM-specific recovery và trạng thái song song.

~~~text
begin global transaction X
enlist participants = [A, B]

try:
    execute business writes under X

    votes = []
    for each participant p:
        votes.add(prepare(p, X))

    if every required participant is READY or READ_ONLY:
        durableLog(COMMIT, X)
        for each prepared writable participant p:
            send COMMIT(X) to p
        await/track acknowledgements via recovery
        report completion when consistent with contract
    else:
        durableLog(ABORT, X) as protocol requires
        for each relevant participant p:
            send ROLLBACK(X) to p
        await/track acknowledgements via recovery

on crash:
    recover coordinator log
    rediscover in-doubt branches
    if durable decision is COMMIT:
        resend COMMIT until resolved
    else:
        resolve according to protocol state and durable evidence
~~~

Câu lệnh **durableLog(COMMIT, X)** là mốc không thể tùy tiện đổi quyết định. Việc chờ ACK hoặc báo kết quả cho caller phải theo đúng contract của transaction manager và mô hình durability; không suy diễn rằng mất ACK tương đương mất COMMIT.

## 14. PostgreSQL prepared transactions: liên hệ và giới hạn

PostgreSQL có khả năng **prepared transactions** ở database engine khi được cấu hình phù hợp. Các lệnh minh họa:

~~~sql
BEGIN;

UPDATE internal_accounts
SET balance = balance - 100
WHERE id = 'A' AND balance >= 100;

-- Transaction được chuẩn bị dưới một định danh duy nhất.
PREPARE TRANSACTION 'transfer-branch-A-unique-id';

-- Ở một session khác, khi đã có global COMMIT decision:
COMMIT PREPARED 'transfer-branch-A-unique-id';

-- Hoặc, nếu global decision là ABORT:
-- ROLLBACK PREPARED 'transfer-branch-A-unique-id';
~~~

Đây là minh họa protocol state tại **một** database. Để có global 2PC xuyên DB-A và DB-B, cần một coordinator đáng tin cậy theo dõi các nhánh, quyết định durable và recovery. Chạy lệnh SQL riêng trên từng database bằng script **không tự tạo một transaction manager an toàn**.

Các điểm vận hành cần biết:

- Cấu hình prepared transactions của PostgreSQL phải cho phép tính năng (ví dụ **max_prepared_transactions** khi phù hợp với môi trường).
- Prepared transactions có thể tiếp tục giữ lock và gây áp lực tài nguyên; không nên để chúng chờ vô hạn.
- Phải có quy trình tìm và đối soát prepared transactions (chẳng hạn quan sát **pg_prepared_xacts**).
- Prepared transaction identifier cần duy nhất, quản lý được, không va chạm với các nhánh khác.
- Không xử lý thủ công COMMIT PREPARED hay ROLLBACK PREPARED chỉ dựa trên trực giác; phải có **bằng chứng quyết định toàn cục**.
- Quy trình backup, failover, pooling và vận hành phải được kiểm tra cùng khả năng prepared transaction/recovery thực tế.

Một prepared transaction cũ không tự chứng minh là “rác có thể xóa”. Nó có thể là một nhánh của giao dịch đã quyết định COMMIT ở coordinator nhưng chưa được thông báo hoàn tất.

## 15. Điều kiện để 2PC đáng cân nhắc

2PC có thể phù hợp hơn khi **nhiều điều kiện đồng thời** được thỏa:

### 15.1. Yêu cầu atomic commit thực sự cứng

Hai hoặc vài tài nguyên phải cùng commit/abort trong một giao dịch ngắn, và mô hình trạng thái trung gian hoặc compensation không được nghiệp vụ chấp nhận.

Cần hỏi: có thật phải cần global atomic commit, hay invariant có thể đưa về một owner/database? Nếu một thay đổi thiết kế domain giúp toàn bộ invariant nằm trong một local transaction, thường nên ưu tiên cách đơn giản đó.

### 15.2. Participant đều hỗ trợ chuẩn bị và recovery

Mỗi resource cần:

- Khả năng prepare/commit/rollback hoặc XA tương đương.
- Durable prepared state và recovery API.
- Driver/integration phù hợp với transaction manager.
- Cơ chế điều tra in-doubt branches.
- Chính sách timeout, isolation và lock hợp lệ.

Nếu một bước là “gọi API bên thứ ba trả 200 OK”, 2PC thông thường **không thể đưa bước đó vào global atomic commit** trừ khi provider hỗ trợ một giao thức enlistment/prepare thực sự và toàn bộ hệ thống được cấu hình đúng.

### 15.3. Giao dịch ngắn, số participant kiểm soát được

Nếu transaction giữ tài nguyên trong vài chục mili giây ở mạng nội bộ ổn định, chi phí có thể chấp nhận. Nếu giữ lock nhiều phút để chờ tác vụ người dùng, message broker hoặc payment provider, nguy cơ blocking là rất lớn.

Không có ngưỡng thời gian hoặc số participant tối ưu phổ quát. Đo p95/p99, lock contention, failure recovery và tải thực tế.

### 15.4. Hạ tầng và tổ chức có năng lực vận hành

Cần có:

- Transaction manager HA/recovery đúng thiết kế.
- Log storage bền vững, backup/recovery và ownership rõ.
- Dashboard, alert và runbook prepared/in-doubt transactions.
- Kiểm thử lỗi network, crash và restart.
- Quyền truy cập hạn chế đối với thao tác heuristic/manual recovery.
- Nhóm trực vận hành có thể xác định trạng thái global commit mà không gây side effect trái ngược.

### 15.5. Mức coupling được chấp nhận

2PC làm các resource tham gia cùng vòng đời giao dịch. Nếu nhóm muốn deploy/database độc lập và có các SLO availability khác nhau, coupling này có thể đi ngược mục tiêu microservices. Cần chấp nhận đánh đổi một cách có chủ đích, không gắn 2PC vào mọi service-to-service call.

## 16. Khi nào không nên dùng 2PC?

### 16.1. Workflow dài hoặc chờ con người

Ví dụ “đặt hàng – đợi khách nhập OTP – nhận xác nhận ngân hàng – giao hàng” kéo dài nhiều phút/giờ. Không nên giữ database transactions prepared và lock xuyên toàn bộ workflow.

**Phù hợp hơn:** state machine/Saga, command/event, timeout nghiệp vụ, bù trừ và đối soát.

### 16.2. Payment provider hoặc email API không tham gia XA

Không thể gửi PREPARE đến một cổng HTTP thông thường rồi kỳ vọng sau này COMMIT hoặc ROLLBACK side effect. Một payment authorization đã được provider thực hiện có thể cần capture/void/refund theo nghiệp vụ; email đã gửi không có rollback.

**Phù hợp hơn:** idempotency key, operation status, reconciliation, outbox và compensation thật sự được provider hỗ trợ.

### 16.3. Kết nối liên vùng dễ partition hoặc yêu cầu availability cao

Khi transaction span nhiều region với latency cao và network partition có thể xảy ra, 2PC có thể giữ lock/in-doubt lâu và tạo coupling vận hành lớn.

**Phù hợp hơn khi nghiệp vụ cho phép:** phân vùng ownership theo region, single writer, event-driven integration và workflow chịu eventual consistency. Nếu vẫn bắt buộc global atomicity, phải thiết kế availability và failure recovery chặt chẽ, chấp nhận trade-off.

### 16.4. Tách service chỉ để mô phỏng một transaction cũ

Nếu các bảng cần cập nhật atomic vẫn thuộc cùng bounded context, tách chúng thành hai database rồi dùng XA để nối lại có thể không tạo giá trị. Cân nhắc giữ chúng trong một local transaction hoặc module chung.

### 16.5. Consumer không cần kết quả đồng bộ tức thì

Ví dụ Search Index, BI hay notification có thể cập nhật sau khi Order commit.

**Phù hợp hơn:** transactional outbox, event streaming, read model và idempotent consumer. Đừng giữ Order transaction mở để chờ mọi downstream projection hoàn thành.

## 17. So sánh 2PC với Saga

**Saga** chia một workflow dài thành các **local transactions**, với các bước tiếp theo hoặc compensation khi lỗi.

~~~text
2PC:
  Global transaction
      |
      +-- PREPARE A
      +-- PREPARE B
      |
      +-- Global COMMIT / ABORT

Saga:
  T1: CreateOrder(PENDING)
      |
  T2: ReserveInventory
      |
  T3: AuthorizePayment
      |
  T4: ConfirmOrder
      |
  Nếu lỗi phù hợp:
      ReleaseInventory / VoidAuthorization / RejectOrder
~~~

| Tiêu chí | 2PC | Saga |
|---|---|---|
| Đơn vị commit | Một global commit/abort với các enlisted resources | Nhiều local transactions |
| Trạng thái trung gian | Có thể ẩn trong global transaction cho tới quyết định | Có, cần mô hình hóa rõ |
| Failure behavior | Participant có thể in-doubt và blocking | Workflow có thể pending/retry/compensating |
| Locks | Có thể giữ lock qua prepare/decision | Local transaction ngắn hơn nếu thiết kế đúng |
| Phụ thuộc kỹ thuật | Resources phải tham gia giao thức phối hợp | Service cung cấp command/event và idempotency |
| Tác vụ dài | Thường không phù hợp | Thường phù hợp hơn |
| Compensation | Global rollback trong phạm vi enlisted resources | Bù trừ nghiệp vụ; không nhất thiết đảo ngược chính xác |
| Consistency cho consumer | Atomic global decision trong scope 2PC | Thường eventual consistency |
| Độ phức tạp | TM/XA/recovery và khóa phân tán | State machine, retries, compensation và reconciliation |

Saga **không phải** “2PC không cần khóa” có cùng semantics. Một bước đã commit trong Saga có thể tạo side effect quan sát được trước khi compensation. Đối với tiền hoặc dữ liệu pháp lý, một hành động bù trừ có thể là giao dịch mới chứ không xóa dấu vết giao dịch cũ.

### 17.1. Saga orchestration và choreography

- **Orchestration:** một workflow coordinator nghiệp vụ quyết định bước nào gọi tiếp, retry, bù trừ và trạng thái terminal.
- **Choreography:** các service phản ứng với event của nhau; dễ phân tán trách nhiệm nhưng có thể khó nhìn toàn bộ workflow nếu không có quy ước.

Đừng nhầm **Saga orchestrator** với **2PC transaction coordinator**. Saga orchestrator quản lý tiến trình nghiệp vụ qua các local commits, không yêu cầu mọi database bỏ phiếu PREPARE.

## 18. So sánh 2PC với TCC (Try–Confirm–Cancel)

**TCC** là mô hình phối hợp nghiệp vụ:

1. **Try:** giữ chỗ tài nguyên hoặc tạo trạng thái có thể xác nhận.
2. **Confirm:** chốt nghiệp vụ.
3. **Cancel:** giải phóng phần đã giữ khi không thể hoàn tất.

~~~text
Try inventory reservation
Try payment authorization
      |
   success?
      |
  +---+---+
  |       |
Confirm  Cancel
~~~

TCC có bề ngoài “hai giai đoạn”, nhưng **không phải XA 2PC**:

- Try/Confirm/Cancel là API/ngữ nghĩa nghiệp vụ phải được service tự thiết kế.
- Reservation có expiry, idempotency, recovery và trạng thái riêng.
- Cancel có thể đến sau Confirm hoặc bị gửi trùng; cần state machine rõ.
- Không có bảo đảm một global DB commit ACID chỉ vì gọi Confirm cho nhiều dịch vụ.

TCC hữu ích khi domain hỗ trợ giữ tài nguyên trước khi chốt và cần điều phối giữa các service độc lập. Nhưng nó đòi thiết kế trạng thái nhất quán và xử lý lỗi phức tạp, không thay thế tự động cho mọi nhu cầu 2PC.

## 19. So sánh 2PC với transactional outbox

Outbox là mô hình thường dùng khi cần **đồng bộ thay đổi DB với ý định phát event** mà không phải commit đồng thời database và broker qua XA.

~~~text
Trong một local transaction:
  UPDATE orders
  INSERT outbox_event
  COMMIT
          |
     Outbox relay
          |
       Message broker
          |
     Idempotent consumer
~~~

Nếu DB transaction commit, outbox record cũng có mặt. Relay có thể retry để phát event. Tuy nhiên:

- Event có thể được phát **trùng** nếu relay crash sau publish mà trước khi đánh dấu sent.
- Consumer cần dedup/inbox/business idempotency.
- Downstream có thể cập nhật **sau** Order commit.
- Outbox không làm nhiều database đồng thời commit atomic.
- Eventual-consistency lag và dữ liệu lệch tạm thời phải được công bố, theo dõi và đối soát.

**Phân biệt mục tiêu:** 2PC phối hợp quyết định commit của nhiều tài nguyên XA; outbox kết hợp thay đổi dữ liệu và ý định phát event trong **một local transaction**, rồi chuyển tiếp đáng tin cậy theo thời gian.

### 19.1. Khi nào outbox là lựa chọn tốt hơn?

- Order commit không cần đợi Analytics hoặc Notification.
- Có thể chấp nhận downstream xử lý sau một khoảng thời gian.
- Consumer có thể thiết kế idempotent.
- Mục tiêu là tránh “DB đã commit nhưng event phát thất bại”.
- Không muốn/không thể enlist broker và database vào một global XA transaction.

## 20. 2PC không đồng nghĩa consensus hoặc distributed database replication

Nhiều tài liệu dùng chữ “two phase” cho các giao thức khác nhau. Cần phân biệt.

- **2PC:** coordinator thu phiếu chuẩn bị rồi quyết định commit/abort cho transaction.
- **Consensus (ví dụ Raft/Paxos):** một nhóm node phối hợp thống nhất một chuỗi quyết định hoặc trạng thái dưới giả định lỗi cụ thể.
- **Quorum replication:** yêu cầu đủ replica phản hồi trước khi xem một write đạt mức độ bền vững/nhất quán nào đó.
- **Two-phase read/write hoặc rollout:** là cách tổ chức công việc hai bước, không nhất thiết liên quan transaction commit.
- **Saga/TCC:** điều phối các thao tác nghiệp vụ, khác global 2PC.

Một database phân tán có thể sử dụng cả consensus **và** một protocol commit phân tán giữa các shard. “Database dùng Raft” không đủ để kết luận mọi giao dịch xuyên shard là 2PC, và “có 2PC” không chứng minh consensus đã giải quyết hoàn toàn blocking trong mọi trường hợp.

Nếu công nghệ có coordinator được nhân bản/leader election, phải xem cơ chế phục hồi durable decision và participant state cụ thể. **Không dùng thuật ngữ “2PC = consensus” hoặc “consensus loại bỏ mọi trade-off của 2PC”**.

## 21. 2PC và isolation/concurrency control

Giả sử hai transaction phân tán cùng cố chuyển tiền hoặc sửa cùng tài nguyên. 2PC quyết định **mỗi transaction commit hay abort**, nhưng cách chúng xen kẽ phụ thuộc isolation và concurrency control tại từng participant.

Các vấn đề cần thiết kế:

1. **Lost update:** hai transaction ghi đè trạng thái nếu không có version/lock đúng.
2. **Write skew:** các bất biến đa dòng có thể bị phá ở isolation level chưa đủ mạnh.
3. **Deadlock:** hai transaction giữ khóa ở A/B theo thứ tự ngược nhau.
4. **Lock wait:** prepared transaction có thể giữ khóa lâu sau network failure.
5. **Global consistency model:** các resource khác nhau có thể không cung cấp cùng serializable semantics.
6. **Read-only participant:** đọc không nhất thiết tạo snapshot toàn cục nhất quán nếu không có cơ chế bổ sung.

Để bảo vệ invariant, cần thiết kế isolation, lock ordering, unique/foreign-key constraints trong phạm vi DB, optimistic concurrency và transaction boundaries phù hợp. **2PC không tự chữa một thiết kế concurrency sai.**

## 22. 2PC trong microservices và nguyên tắc autonomy

Microservices thường hướng tới:

- Deployment độc lập.
- Quyền sở hữu dữ liệu rõ.
- Fault isolation.
- Contract ổn định.
- Khả năng scale riêng.
- Nhóm vận hành có trách nhiệm end-to-end.

Một global 2PC kéo dài qua ba service có thể làm ngược một phần các mục tiêu trên:

~~~text
Checkout Service -- XA transaction --> Orders DB
         |
         +------------ XA transaction --> Inventory DB
         |
         +------------ XA transaction --> Billing DB

Một resource ngừng đáp ứng ở prepare:
  cả global transaction có thể chưa hoàn tất.
~~~

Nếu các service khác nhau có các team, release cycle và storage engine riêng, việc cùng enlist vào một global XA transaction có thể làm tăng coupling và làm lộ hạ tầng DB của service này cho service khác. Nó còn gây khó khăn khi một service chuyển database engine hoặc thay deployment topology.

Không phải mọi sử dụng 2PC đều “phá microservices”. Nó có thể phù hợp trong một hệ thống quản lý tập trung, tài nguyên rõ và giao dịch ngắn. Nhưng phải ghi nhận **vì sao lợi ích atomicity vượt chi phí phối hợp**, thay vì chọn 2PC mặc định cho mọi cuộc gọi liên service.

## 23. Trường hợp điển hình nên thận trọng: đặt hàng và thanh toán

Đường đi:

~~~text
Checkout -> Orders DB
         -> Inventory Service
         -> Payment Provider API
         -> Notification Service
~~~

Cách tưởng tượng sai:

~~~text
BEGIN GLOBAL 2PC
   INSERT order
   reserve inventory
   charge customer via HTTP
   send confirmation email
COMMIT ALL
~~~

Vấn đề:

- Payment Provider thường không hỗ trợ PREPARE/COMMIT XA trong global transaction của doanh nghiệp.
- Email đã gửi không có rollback.
- Nếu chờ khách xác thực 3-D Secure hoặc OTP, transaction có thể kéo dài không đoán trước.
- Timeout sau charge không chứng minh charge thất bại.
- Lock trên Orders/Inventory sẽ bị giữ quá lâu trong khi chờ provider.

Một mô hình khác:

~~~text
1. Orders tạo Order(PENDING) trong local transaction.
2. Outbox phát OrderCreated / ReserveInventory command.
3. Inventory xử lý với operationId idempotent.
4. Payment xử lý với provider idempotency key và status lookup.
5. Workflow cập nhật CONFIRMED hoặc REJECTED.
6. Nếu cần, release reservation / void authorization.
7. Notification gửi sau trạng thái đã xác định, có dedup.
~~~

Mô hình này chấp nhận các trạng thái trung gian và cần compensation/reconciliation; nó không có semantics y hệt 2PC, nhưng phù hợp hơn với nhiều workflow dịch vụ độc lập.

## 24. Một ví dụ khác: chuyển đổi hệ thống cũ sử dụng hai DB

Giả sử một ứng dụng enterprise đang trong giai đoạn migration:

- Ledger A lưu dữ liệu giao dịch, sử dụng database XA-capable.
- Ledger B lưu dữ liệu clearing, cũng XA-capable.
- Cả hai do một đội vận hành; traffic trong một vùng mạng nội bộ ổn định.
- Yêu cầu kế toán đã xác định rằng một thao tác ngắn phải cùng commit/abort.
- Có transaction manager, recovery logs và nhóm vận hành prepared transactions.
- Hệ thống có kế hoạch giảm coupling trong dài hạn nhưng cần giai đoạn chuyển tiếp.

Ở đây 2PC **có thể là lựa chọn có cơ sở**, nếu:

1. Hai tài nguyên thực sự enlist cùng global transaction.
2. Transaction ngắn, lock contention thấp và failure drills được thực hiện.
3. Có SLO và phương án xử lý in-doubt.
4. Các business operations có idempotency khi caller retry.
5. Không thêm HTTP side effect ngoài 2PC vào cùng lời hứa atomicity.
6. Lộ trình kiến trúc biết khi nào bỏ XA hoặc giữ lâu dài với ownership rõ.

**Điều kiện áp dụng mới là quyết định quan trọng**, không phải tên ngành “kế toán” hay “ngân hàng”. Nhiều hệ thống tài chính cũng dùng ledger, idempotency và workflow có đối soát thay vì XA xuyên mọi thành phần.

## 25. Thiết kế timeout và deadline cho 2PC

Cần phân biệt:

- **Client request deadline:** người gọi chờ phản hồi tối đa bao lâu.
- **Global transaction timeout:** transaction manager cho phép bao lâu trước khi bắt đầu hoặc hoàn tất theo policy.
- **Database lock/statement timeout:** giới hạn đợi khóa hoặc câu lệnh.
- **Prepare/commit network timeout:** giới hạn RPC điều phối.
- **Recovery timeout/alert threshold:** bao lâu một nhánh có thể in-doubt trước khi cần phản ứng.

Không được hiểu các timeout này như cùng một giá trị. Đặc biệt, **timeout của client không quyết định rollback an toàn** nếu global COMMIT đã được log.

Nếu request hết deadline trước khi 2PC ra quyết định toàn cục, application/TM có thể yêu cầu rollback theo protocol. Nhưng nếu commit decision đã durable, không được đơn giản đổi sang rollback chỉ vì client hết chờ.

Khi latency từ các participant cao, nên giảm phạm vi công việc trong global transaction: validate input và chuẩn bị dữ liệu không cần lock trước khi begin, chỉ giữ phần cần atomic bên trong, không thực hiện lời gọi HTTP chậm trong khi đã prepare.

### 25.1. Deadline propagation tới service không phải participant

Nếu một bước trong workflow gọi service không tham gia XA, deadline propagation giúp giới hạn thời gian chờ nhưng không tạo global atomicity. Nên tránh lẫn lộn hai khái niệm “request cùng deadline” với “resource cùng transaction”.

## 26. Recovery sau sự cố: phải làm gì?

Khi hệ thống gặp in-doubt transaction, thao tác thủ công sai có thể tạo trạng thái commit ở một bên, rollback ở bên còn lại.

### 26.1. Quy trình điều tra an toàn

1. **Khoanh vùng giao dịch:** xác định Xid/global transaction ID, participant branches, timeframe và owner.
2. **Xác định durable decision:** đọc transaction manager log/recovery state qua công cụ được vendor hỗ trợ.
3. **Kiểm tra participant state:** nhánh nào prepared, committed, rolled back, absent hoặc unknown.
4. **Tránh can thiệp vội:** không force ROLLBACK chỉ vì prepared age cao.
5. **Ưu tiên recovery tự động:** khôi phục coordinator, connectivity và recovery service trước.
6. **Nếu cần can thiệp:** có người phê duyệt, evidence về global decision, runbook vendor và audit.
7. **Đối soát:** sau khi các nhánh resolved, kiểm tra invariant và kết quả nghiệp vụ.
8. **Ghi incident:** nguyên nhân, thời gian khóa, hậu quả, biện pháp ngăn tái diễn.

### 26.2. Prepared transaction bị bỏ quên

Một nhánh prepared tồn tại lâu có thể do:

- Coordinator không chạy hoặc không truy cập được log.
- Connection/network partition.
- Cấu hình recovery ID sai sau deploy.
- Participant đã đổi resource name hoặc credential.
- TM object store bị thiếu/không thể đọc.
- Người vận hành đã reset/khôi phục DB không đồng bộ với TM.

Giải pháp không phải luôn “rollback transaction cũ nhất”. Cần biết có durable COMMIT decision hay không, và **ai đang sở hữu quyết định**.

### 26.3. Heuristic mixed: khi atomicity bị phá trong sự cố

Nếu một resource bị force commit trong khi resource khác bị rollback, phải xem đây là sự cố dữ liệu nghiêm trọng. Ứng dụng cần đối soát trạng thái và áp **nghiệp vụ sửa chữa có audit**, không chỉ “chạy lại transfer API” một cách mù quáng.

## 27. Observability cho transaction phân tán

Tập metric và log nên bao phủ cả performance và recovery:

| Chỉ số | Ý nghĩa |
|---|---|
| Global transaction start/commit/abort count | Tỷ lệ hoàn tất hoặc abort |
| Prepare latency p50/p95/p99 | Participant nào làm chậm voting phase |
| Commit completion latency | Thời gian từ quyết định tới xác nhận |
| In-doubt / prepared transaction count | Có nhánh đang chờ quyết định |
| Prepared transaction age | Phát hiện khóa tồn tại bất thường |
| Lock wait / blocked sessions | Tác động lên DB khác |
| XA errors theo mã và resource | Khác biệt lỗi hạ tầng và lỗi giao dịch |
| Heuristic outcome count | Bất nhất nghiêm trọng cần can thiệp |
| Recovery retry count / duration | Hiệu quả phục hồi |
| Coordinator log durability errors | Nguy cơ không khôi phục được quyết định |
| Transaction timeout rate | Giới hạn thời gian có phù hợp không |
| Connection pool saturation | Các nhánh đang chiếm connection/tài nguyên |
| Business reconciliation mismatch | Kiểm tra tính đúng đắn sau lỗi |

Log nên nối được **trace ID**, **business operation ID** và **transaction/Xid** trong phạm vi quyền truy cập phù hợp, nhưng không ghi mật khẩu, token, số tài khoản đầy đủ hoặc payload PII vào metric labels. Dùng labels có cardinality hợp lý như resource name, region, phase, outcome và error class.

### 27.1. Cảnh báo

Một số cảnh báo nên có:

- In-doubt transaction tồn tại quá ngưỡng của operation.
- Prepared count tăng nhanh trong khi commit rate giảm.
- Lock wait hoặc DB log retention tăng sau coordinator restart.
- Recovery liên tục thất bại cùng Xid/resource.
- XA heuristic outcome xuất hiện.
- TM recovery object store không khả dụng.
- Transaction timeout hoặc abort spike theo resource.

Ngưỡng phải dựa trên baseline và mức quan trọng nghiệp vụ, không copy một con số chung.

## 28. Kiểm thử 2PC đúng tình huống lỗi

Happy-path unit test chưa đủ để chứng minh tính bền vững.

| Kịch bản | Thao tác thử | Kỳ vọng |
|---|---|---|
| Hai participant đồng ý | DB-A/DB-B prepare thành công | Cả hai commit; không còn nhánh in-doubt |
| Một participant trả NO | Vi phạm constraint ở DB-B | Global rollback, không có partial business effect |
| Participant crash trước prepare | Dừng DB-B trước khi bỏ phiếu | TM abort/recover theo protocol |
| Participant crash sau YES | Kill DB-B khi đã prepared | Khi restart, nhánh được phát hiện và resolved theo durable decision |
| Coordinator crash trước durable decision | Kill TM ở điểm tương ứng | Recovery không tự đưa ra quyết định trái protocol |
| Coordinator crash sau durable COMMIT | Kill TM trước khi B nhận COMMIT | Sau recovery, tiếp tục COMMIT cả hai |
| Mất network sau prepare | Chặn kết nối TM ↔ DB-A | Prepared branch không tự ý rollback sai |
| Client timeout sau commit | Làm mất response | Query operation status xác minh; retry không double transfer |
| Lock contention cao | Chạy giao dịch cạnh tranh | Có alert, bounded resource use và recovery |
| Heuristic/manual intervention | Mô phỏng trong lab theo vendor tools | Quy trình nhận diện, đối soát và audit |
| DB failover | Thực hiện failover trong lúc prepared | Xác minh resource manager recovery theo topology thực |
| Deploy đổi TM config | Thay recovery identity có kiểm soát | Không orphan các Xid cũ |

**Thử nghiệm nên chạy trên môi trường cô lập**, không kill database production hoặc force commit một nhánh thật để “kiểm chứng”. Với platform có nhiều vùng/replica, phải thử cả chuyển primary và phục hồi coordinator log theo cấu hình dự kiến.

### 28.1. Bài kiểm thử giá trị nhất

Giả sử coordinator đã ghi **durable COMMIT**, A đã commit, B chưa nhận lệnh. Sau restart, hệ thống phải hoàn tất commit B, không chọn rollback B và cũng không tạo một giao dịch nghiệp vụ mới để “thử lại”.

Điều cần xác minh không chỉ là kết quả trả về của một method, mà là:

- A/B cuối cùng cùng phản ánh kết quả nghiệp vụ dự kiến.
- Có evidence của recovery path.
- Không có in-doubt branch bị bỏ lại.
- Client có thể tra cứu operation ID mà không tạo giao dịch kép.

## 29. Chọn giữa 2PC, local transaction, Saga, TCC và Outbox

### 29.1. Cây quyết định khái quát

~~~text
Cần thay đổi dữ liệu atomic?
           |
           +-- Chỉ một resource manager?
           |          |
           |          +--> Ưu tiên local transaction
           |
           +-- Nhiều resource managers?
                      |
                      v
        Có thể đưa invariant về một owner/DB?
                      |
              +-------+-------+
              |               |
             Có              Không
              |               |
        Tái thiết kế      Cần global atomic
        boundary          commit ngay?
                              |
                      +-------+-------+
                      |               |
                     Có              Không
                      |               |
           Mọi resource hỗ trợ    Saga / TCC / Outbox
           XA + recovery?         theo semantics nghiệp vụ
                      |
              +-------+-------+
              |               |
             Có              Không
              |               |
       Đánh giá 2PC và      Không “giả lập XA”;
       chi phí blocking     thiết kế workflow/compensation
~~~

Đây là gợi ý suy nghĩ, không phải thuật toán chọn kiến trúc tự động. Ngay cả khi đủ hỗ trợ XA, cần kiểm tra thời gian giao dịch, RTO/RPO, availability, ownership và khả năng vận hành.

### 29.2. Bảng chọn nhanh

| Tình huống | Thường ưu tiên | Lý do |
|---|---|---|
| Cập nhật nhiều bảng trong một DB | Local ACID transaction | Ít overhead, invariant tập trung |
| Hai XA databases, transaction rất ngắn, cùng đội vận hành, atomic commit bắt buộc | Cân nhắc 2PC | Global atomicity với điều kiện recovery và blocking chấp nhận được |
| Checkout + Payment Provider qua HTTP | Saga/TCC theo domain, idempotency | Provider ngoài không tham gia XA |
| DB commit + phát message | Outbox và idempotent consumer | Loại bỏ khoảng trống giữa DB write và ý định publish |
| Search index sau Order commit | Event/read projection | Không cần chờ tất cả consumer commit |
| Giao dịch xuyên region latency cao | Ưu tiên thiết kế ownership/workflow lại | 2PC dễ tăng latency và in-doubt |
| Workflow có bước chờ người dùng/phê duyệt | Saga/state machine | Không giữ prepared DB transaction hàng giờ |
| Legacy enterprise nhiều XA systems đã kiểm soát | 2PC có thể phù hợp | Có hỗ trợ transaction manager và recovery trưởng thành |

## 30. Mẫu Architecture Decision Record (ADR)

~~~markdown
# ADR: Có nên dùng 2PC cho <business operation>?

## Bối cảnh
- Năng lực nghiệp vụ:
- Vì sao cần atomicity xuyên nhiều resource:
- Số participant và chủ sở hữu:
- Resource manager/driver, XA support:
- Isolation/invariants ở từng resource:
- Network topology/region:
- SLO latency/availability, RTO/RPO:

## Phương án so sánh
1. Gom invariant về một owner/local transaction.
2. XA/2PC.
3. Saga orchestration hoặc choreography.
4. TCC với reservation/confirm/cancel.
5. Transactional outbox + async reconciliation.

## Phân tích 2PC
- Ai là transaction manager/coordinator:
- Durable TM log/recovery object store:
- Enlistment và XADataSource/JMS XA config:
- Prepare/commit timeout:
- Lock behavior/transaction duration:
- In-doubt và recovery runbook:
- Heuristic outcome và người phê duyệt:
- Crash/failover tests:
- Data permissions, ownership/coupling:
- Client idempotency và unknown outcome:

## Quyết định
- Phương án được chọn:
- Vì sao các phương án khác không phù hợp:
- Trade-off chấp nhận được:
- Guardrails và metric:
- Kế hoạch rollout/rollback:
- Chủ sở hữu và ngày xem lại:
~~~

Nên viết ADR trước khi nối thêm nhiều service vào một global transaction. Nếu không thể trả lời ai có trách nhiệm recovery và xác định global decision sau crash, hệ thống chưa sẵn sàng vận hành 2PC cho dữ liệu quan trọng.

## 31. Bài tập thực hành

### Bài 1: phân tích đường lỗi

Coordinator C điều phối A và B. A trả YES, B trả YES. C ghi durable COMMIT rồi gửi COMMIT tới A. A xác nhận, nhưng trước khi gửi cho B thì C crash.

Hỏi:

1. B đang ở trạng thái gì?
2. Có được tự ROLLBACK B vì B chưa nhận COMMIT không?
3. Khi C restart, nó phải dựa trên dữ liệu gì để tiếp tục?
4. Nếu client đã timeout, client nên làm gì thay vì gửi một transfer mới?
5. Metric và alert nào giúp phát hiện nhánh B chờ quá lâu?

**Gợi ý:** global COMMIT decision đã durable; recovery phải tiếp tục quyết định này. Timeout ở client không thay đổi global decision.

### Bài 2: chọn kiến trúc

Cho ba tình huống:

- **Tình huống A:** một PostgreSQL database có bảng accounts, ledger_entries; muốn chuyển tiền giữa hai account.
- **Tình huống B:** hai XA-capable databases trong cùng data center, giao dịch nội bộ kéo dài vài chục mili giây, yêu cầu cùng commit và có TM/recovery chuyên trách.
- **Tình huống C:** khách đặt vé, xác thực OTP, payment provider HTTP, giữ ghế 15 phút và có email xác nhận.

Hãy chọn local transaction, 2PC hoặc Saga/TCC/Outbox cho từng trường hợp. Nêu ít nhất ba tiêu chí quyết định và một failure mode cần kiểm thử cho mỗi lựa chọn.

**Gợi ý:** A không cần distributed transaction nếu dữ liệu cùng resource manager; B có thể cân nhắc XA nếu cost/recovery chấp nhận; C không nên giữ prepared transaction khi chờ OTP và API bên ngoài.

### Bài 3: tìm lỗi trong thiết kế Java

Một lớp Spring có method gắn @Transactional, gọi:

~~~text
accountRepository.save(...) -> DataSource A (local)
balanceRepository.save(...) -> DataSource B (local)
httpClient.post("/payment/charge")
~~~

Developer kết luận “đã có 2PC vì @Transactional bao hết method”.

Hãy chỉ ra:

1. Vì sao hai local DataSources không tự tham gia XA?
2. Cần những thành phần cấu hình nào để hai DB cùng một global transaction?
3. Vì sao HTTP payment charge không được rollback bằng annotation?
4. Khi timeout sau charge, hệ thống phải làm gì?
5. Có thể thay đổi ranh giới nghiệp vụ ra sao để tránh global transaction dài?

### Bài 4: vận hành in-doubt transaction

Dashboard cho thấy một prepared branch giữ khóa trên bảng ledger 20 phút. Một nhân viên đề xuất chạy ROLLBACK PREPARED ngay vì khách hàng đã nhận HTTP 504.

Hãy viết các bước điều tra, xác định durable global decision, vai trò TM, bằng chứng cần có trước manual intervention và cách đối soát sau recovery.

**Gợi ý:** HTTP 504 không chứng minh global ABORT. Cần phân biệt kết quả của caller và trạng thái transaction manager.

## 32. Checklist trước khi đưa 2PC vào production

- [ ] Có yêu cầu global atomic commit thật, không thể giải quyết đơn giản hơn trong một owner/local transaction.
- [ ] Mọi participant có hỗ trợ prepare/commit/rollback và recovery được xác minh thực tế.
- [ ] Transaction manager có durable log, backup, recovery identity và quyền vận hành rõ.
- [ ] Các resource được enlist vào đúng **một global transaction**.
- [ ] Không nhầm @Transactional với automatic XA across databases.
- [ ] Không cho rằng HTTP API bên ngoài tự tham gia 2PC.
- [ ] Transaction ngắn và lock scope được kiểm soát.
- [ ] Isolation, concurrency và invariant nghiệp vụ đã thiết kế độc lập với 2PC.
- [ ] Có mô hình idempotency/operation status cho client retry sau timeout.
- [ ] Có chính sách transaction timeout và request deadline rõ.
- [ ] Biết các loại failure trước/sau prepare và sau durable commit decision.
- [ ] Có runbook in-doubt, heuristic, XA recovery và đối soát nghiệp vụ.
- [ ] Có cảnh báo prepared age, lock waits, abort, heuristic và recovery failures.
- [ ] Đã chạy crash/failover tests ở cả hai pha, không chỉ happy path.
- [ ] SLO latency/availability và chi phí so với local transaction/Saga được đo.
- [ ] Có ADR nêu trade-off về autonomy, coupling và khả năng mở rộng.
- [ ] Có kế hoạch thay thế hoặc quản lý lâu dài 2PC nếu hệ thống tiến hóa.

## 33. Ghi nhớ

**2PC gồm hai pha: PREPARE để tất cả participant xác nhận sẵn sàng, rồi COMMIT/ABORT theo một quyết định toàn cục bền vững.** Khi thành công và các giả định về resource/recovery được giữ, nó giúp phối hợp tính nguyên tử của commit trên nhiều tài nguyên tham gia. Nhưng participant đã chuẩn bị có thể bị **in-doubt**, giữ khóa và chờ khi coordinator không sẵn sàng; triển khai còn cần transaction manager, XA-capable resources, durable logs, giám sát và quy trình recovery.

Dùng 2PC khi có **nhu cầu atomic commit thực sự, transaction ngắn, participant phù hợp và năng lực vận hành đủ mạnh**. Đối với workflow xuyên các microservice độc lập, payment gateway, email, sự kiện hay tác vụ lâu dài, hãy cân nhắc **local transactions, Saga/TCC, transactional outbox, idempotency và reconciliation**. Quyết định tốt là quyết định bảo vệ được bất biến nghiệp vụ với mức phụ thuộc và chi phí vận hành mà hệ thống chấp nhận được.

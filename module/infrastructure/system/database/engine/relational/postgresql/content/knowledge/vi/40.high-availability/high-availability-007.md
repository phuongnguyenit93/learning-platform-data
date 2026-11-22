# Tính nhất quán khi đọc từ standby và yêu cầu đọc sau ghi trong PostgreSQL

## 1. Vì sao đọc từ standby có thể trả về dữ liệu cũ?

Trong kiến trúc PostgreSQL High Availability, standby thường được dùng để phục vụ truy vấn đọc, giảm tải primary và duy trì khả năng failover. Với physical streaming replication, primary gửi WAL tới standby; standby nhận, ghi, flush và replay WAL để cập nhật trạng thái database.

Các bước đó diễn ra bất đồng bộ nếu dùng asynchronous replication. Vì vậy một transaction có thể đã COMMIT thành công trên primary trong khi standby chưa replay WAL chứa transaction đó. Nếu ứng dụng ghi vào primary rồi ngay lập tức đọc từ standby, truy vấn có thể chưa nhìn thấy dữ liệu vừa ghi.

Tình huống này gọi là **read-after-write inconsistency** hoặc stale read. Nó không nhất thiết là replication bị hỏng; có thể chỉ là độ trễ bình thường của asynchronous replication.

```text
Application
    |
    | 1. INSERT / UPDATE
    v
PRIMARY
    |
    | 2. COMMIT acknowledged
    | 3. WAL sent asynchronously
    |
    +------------------------------+
                                   |
                                   v
                              STANDBY
                              WAL received
                                   |
                                   | 4. WAL replayed later
                                   v
                              New row visible

Application reads standby between steps 3 and 4:
the row may not be visible yet.
```

Ứng dụng cần chọn một consistency policy rõ ràng cho từng loại request. Có request chấp nhận dữ liệu trễ vài giây, có request cần thấy ngay transaction vừa commit, và có request cần đọc nhất quán xuyên suốt một phiên làm việc.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao standby có thể chậm hơn primary.
2. Phân biệt replication lag, read freshness và transaction snapshot.
3. Hiểu read-after-write, read-your-writes, monotonic reads và causal consistency.
4. Thiết kế routing đọc/ghi theo yêu cầu nhất quán.
5. Dùng LSN token làm consistency fence giữa primary và standby.
6. Chờ standby replay tới một LSN trước khi đọc.
7. Hiểu giới hạn của synchronous replication và synchronous_commit.
8. Phân biệt remote_write, on và remote_apply.
9. Xử lý transaction snapshot cũ trong READ COMMITTED và REPEATABLE READ.
10. Thiết kế session stickiness, fallback và timeout.
11. Hiểu tác động của delayed standby và recovery conflicts.
12. Kiểm tra read-after-write trong application và connection pool.
13. Xây test cases, metrics và runbook cho stale reads.
14. Xác định khi nào phải đọc từ primary.
15. Tránh dùng sleep cố định hoặc một lag metric làm bảo đảm consistency.

---

## 2. Primary và standby có cùng dữ liệu ở cùng một thời điểm không?

Không nhất thiết. Primary xử lý transaction và tạo WAL. Standby nhận rồi replay WAL sau đó. Khoảng thời gian giữa hai bước có thể ngắn, nhưng vẫn đủ để một request đọc thấy trạng thái cũ.

| Thời điểm | Primary | Standby |
|---|---|---|
| T1 | customer 42 có balance 100 | balance 100 |
| T2 | UPDATE balance = 150 | balance 100 |
| T3 | COMMIT thành công | balance 100 |
| T4 | Ứng dụng đọc standby | vẫn có thể trả 100 |
| T5 | Standby replay transaction | balance 150 |
| T6 | Ứng dụng đọc standby | trả 150 |

### 2.1. Replication lag là trạng thái có thể thay đổi

Lag có thể tăng trong giờ batch, giảm khi workload nhẹ và thay đổi theo network/storage. Không có một độ trễ cố định áp dụng cho mọi query.

### 2.2. Commit trên primary không mặc định chờ standby replay

Với cấu hình asynchronous thông thường và synchronous_commit mặc định là on nhưng không có synchronous standby được cấu hình, commit chờ local WAL flush. Nó không chờ một standby bất kỳ replay transaction.

### 2.3. Standby chỉ replay WAL đã nhận

Nếu WAL chưa tới standby, replay không thể tiến tới transaction đó. Nếu WAL đã nhận và flush nhưng replay chưa chạy tới, dữ liệu vẫn chưa visible trên standby.

### 2.4. “Đã nhận” khác “đã áp dụng”

Các LSN receive/flush và replay mô tả hai giai đoạn khác nhau. Để đọc row vừa thay đổi, cần standby đã replay tới WAL chứa transaction đó.

## 3. Read-after-write và các consistency guarantees

Các thuật ngữ này mô tả điều ứng dụng có thể kỳ vọng sau khi ghi.

| Guarantee | Ý nghĩa |
|---|---|
| Read-your-writes | Một client đọc được những thay đổi mà chính nó đã commit |
| Read-after-write | Sau khi ghi thành công, lần đọc tiếp theo thấy thay đổi đó |
| Monotonic reads | Một client không nhìn thấy trạng thái cũ hơn trạng thái nó đã nhìn thấy trước đó |
| Causal consistency | Nếu thao tác B phụ thuộc thao tác A, client không quan sát B mà thiếu A |
| Eventual consistency | Nếu không có writes mới và replication tiếp tục, các bản sao cuối cùng hội tụ |
| Strong/linearizable read | Read tuân theo thứ tự thời gian thực đã định nghĩa; cần kiến trúc/coordination phù hợp |

### 3.1. Read-your-writes là guarantee theo client/session

Một request ghi có thể thành công trên primary. Nếu request tiếp theo được route tới một standby chưa replay, cùng client vẫn thấy dữ liệu cũ. Vì vậy chỉ giữ session affinity ở tầng HTTP chưa chắc đủ; cần route read tới primary hoặc chờ replica đạt consistency token.

### 3.2. Monotonic reads

Nếu request đầu đọc từ standby A đã replay tới LSN X, request sau không nên bị route tới standby B mới chỉ replay tới LSN thấp hơn X. Nếu không, cùng người dùng có thể thấy dữ liệu “đi lùi”.

### 3.3. Causal consistency

Ví dụ người dùng tạo đơn hàng rồi mở trang chi tiết đơn. Trang chi tiết phải thấy đơn vừa tạo. Việc tạo đơn là nguyên nhân của lần đọc tiếp theo; request đọc phải chờ một replica đã replay thay đổi đó hoặc đọc primary.

### 3.4. Eventual consistency không đủ cho mọi nghiệp vụ

Dashboard analytics có thể chấp nhận trễ. Số dư tài khoản, trạng thái thanh toán, quyền truy cập và kết quả của thao tác vừa commit thường cần consistency mạnh hơn.

## 4. Transaction snapshot ảnh hưởng tới read-after-write

Ngay cả khi standby đã replay transaction, một transaction đọc đang mở có thể không nhìn thấy thay đổi mới.

PostgreSQL mặc định dùng READ COMMITTED. Mỗi statement bắt đầu một snapshot mới. Nếu transaction đang dùng REPEATABLE READ hoặc SERIALIZABLE, snapshot thường được cố định từ đầu transaction.

### 4.1. READ COMMITTED

Một transaction có thể thực hiện nhiều statement và mỗi statement nhận snapshot mới. Nếu standby đã replay trước khi statement đọc bắt đầu, statement có thể thấy thay đổi.

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM accounts
WHERE account_id = 42;

-- Một transaction khác được replay trên standby.

SELECT balance
FROM accounts
WHERE account_id = 42;

COMMIT;
```

Statement thứ hai có snapshot mới và có thể thấy dữ liệu vừa replay.

### 4.2. REPEATABLE READ

Snapshot của transaction được giữ ổn định. Nếu transaction bắt đầu trước khi WAL được replay, những statement sau vẫn có thể không thấy thay đổi mới dù replay đã tiến lên.

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM accounts
WHERE account_id = 42;

-- Standby replay thêm WAL ở bên ngoài transaction này.

SELECT balance
FROM accounts
WHERE account_id = 42;

COMMIT;
```

Cả hai SELECT dùng cùng snapshot transaction.

### 4.3. SERIALIZABLE

SERIALIZABLE cung cấp các bảo đảm serializable cho transaction trên database node mà nó chạy. Nó không tự đồng bộ snapshot giữa primary và standby, cũng không bảo đảm read từ một standby khác đã replay một transaction vừa commit.

### 4.4. Cách xử lý

Sau khi đợi replica đạt LSN fence, hãy bắt đầu transaction đọc mới hoặc dùng READ COMMITTED statement có snapshot mới. Đừng giữ một REPEATABLE READ transaction cũ rồi kỳ vọng nó tự thấy WAL mới.

## 5. Cách đơn giản nhất: đọc từ primary sau khi ghi

Nếu request vừa ghi cần đọc lại ngay, route read tiếp theo tới primary là giải pháp dễ hiểu nhất.

```text
Application
    |
    v
Write to primary
    |
    v
COMMIT acknowledged
    |
    v
Read from the same primary
    |
    v
Fresh statement snapshot
```

### 5.1. Cùng connection hoặc cùng primary

Nếu ghi và đọc trong cùng transaction, transaction nhìn thấy writes của chính nó theo isolation semantics. Nếu commit rồi đọc trong transaction mới trên cùng primary, statement snapshot mới sẽ thấy transaction đã commit, trừ các tình huống failover làm mất commit theo durability model.

### 5.2. Read routing cần biết request vừa ghi

Application có thể gắn metadata vào request/session, ví dụ `read_after_write=true`, rồi route các reads liên quan tới primary trong một khoảng thời gian hoặc cho tới khi có consistency token.

### 5.3. Không cần ép mọi read về primary

Các request không phụ thuộc write vừa thực hiện có thể đọc standby nếu business chấp nhận staleness. Phân loại endpoint giúp giữ read scaling.

### 5.4. Primary read vẫn cần đúng transaction semantics

Một transaction REPEATABLE READ bắt đầu trước commit khác không tự nhìn thấy commit đó. Dùng transaction mới hoặc snapshot phù hợp.

## 6. Session stickiness và giới hạn của nó

Session stickiness có thể giữ các request của cùng người dùng ở cùng một node hoặc cùng một read route. Nó hữu ích cho monotonic reads nhưng không tự bảo đảm read-after-write.

### 6.1. Sticky tới primary

Sau khi write, giữ các reads trên primary trong session là cách đơn giản để đạt read-your-writes trong primary history hiện tại.

### 6.2. Sticky tới một standby

Nếu session được gắn với standby A, nó tránh chuyển sang standby B có lag lớn hơn. Tuy nhiên A vẫn có thể chưa replay transaction vừa commit. Stickiness không thay LSN fence.

### 6.3. Load balancer đổi backend

Connection pool hoặc proxy có thể chọn backend khác cho mỗi transaction. Không giả định hai câu SQL liên tiếp trong ứng dụng sẽ dùng cùng PostgreSQL server nếu connection routing không bảo đảm điều đó.

### 6.4. Failover làm thay đổi lịch sử

Sau promotion, old primary và new primary có thể thuộc các timeline khác nhau. Session affinity không thể thay thế việc xác định primary hiện tại và durability của transaction đã xác nhận.

## 7. LSN token: cách tạo consistency fence

Một cách tổng quát là lấy một LSN token sau khi transaction commit trên primary. Ứng dụng gửi token cùng request đọc. Standby chỉ được dùng khi replay position đã đạt hoặc vượt token.

```text
1. Application writes on primary
2. COMMIT succeeds
3. Application reads a WAL LSN token
4. Token travels with the next read request
5. Application checks standby replay LSN
6. If replay LSN >= token, read from standby
7. Otherwise wait, retry, or read from primary
```

### 7.1. Lấy token sau COMMIT

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 25
WHERE account_id = 42;

COMMIT;

SELECT pg_current_wal_lsn() AS consistency_lsn;
```

Lấy token trên cùng primary sau khi COMMIT thành công. Token có thể tiến xa hơn commit của request do WAL của transaction khác được ghi đồng thời; điều này chỉ làm standby có thể phải chờ thêm một chút, nhưng tạo một fence an toàn nếu vẫn cùng WAL history.

### 7.2. Vì sao lấy sau commit?

Nếu lấy LSN trước khi transaction commit, token có thể chưa bao gồm commit record. Khi đó standby đạt token vẫn chưa chắc đã replay transaction cần đọc.

### 7.3. Token là một upper bound hữu ích

LSN lấy sau commit có thể bao gồm WAL của các transaction concurrent khác. Standby replay tới token sẽ replay cả WAL trước token theo thứ tự, bao gồm transaction vừa commit.

### 7.4. Gắn token với cluster/timeline context

Không chỉ lưu chuỗi LSN. Token nên đi cùng cluster identity/primary generation hoặc metadata đủ để biết nó thuộc WAL history nào. Không so sánh số LSN từ hai cluster/timeline độc lập một cách mù quáng.

## 8. Kiểm tra standby đã replay tới token chưa

Trên standby:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_wal_replay_lsn() >= '0/16B6C50'::pg_lsn AS reached_token;
```

Thay 0/16B6C50 bằng token nhận từ primary.

### 8.1. Đảm bảo query chạy trên đúng standby

Nếu connection pool route nhầm sang primary hoặc một standby khác, phép kiểm tra không còn đại diện node dự kiến. Gắn node identity vào telemetry.

### 8.2. Kiểm tra role

pg_is_in_recovery() trả true trên standby đang ở recovery. Nếu false, node có thể đã được promote. Application cần nhận diện topology mới và xác minh token có thuộc history hiện tại không.

### 8.3. LSN comparison

PostgreSQL hỗ trợ kiểu pg_lsn và so sánh thứ tự trong cùng WAL history. Dùng cast rõ ràng cho token string. Không parse LSN bằng cách so sánh text alphabetically trong application.

### 8.4. NULL và trạng thái không xác định

Nếu replay LSN không có giá trị phù hợp hoặc server vừa đổi role, coi kết quả là “chưa xác minh”, không coi là đã đạt fence.

## 9. Polling tới khi đạt LSN fence

Một cách triển khai portable là polling với timeout và exponential backoff ở application layer.

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    COALESCE(
        pg_last_wal_replay_lsn() >= '0/16B6C50'::pg_lsn,
        false
    ) AS reached_token;
```

Application lặp lại:
1. Kết nối đúng standby.
2. Kiểm tra role và replay LSN.
3. Nếu token đã đạt, thực hiện read trong transaction mới.
4. Nếu chưa đạt, chờ một khoảng ngắn rồi kiểm tra lại.
5. Nếu timeout, fallback sang primary hoặc trả trạng thái retry theo policy.

### 9.1. Timeout phải gắn với latency budget

Không chờ vô hạn. Ví dụ endpoint có budget 300 ms có thể chờ replica một phần budget rồi chuyển sang primary.

### 9.2. Backoff có giới hạn

Dùng backoff tăng dần có cap và jitter để nhiều request không polling đồng loạt khi standby lag.

### 9.3. Không giữ transaction đọc mở trong lúc chờ

Nếu bắt đầu REPEATABLE READ transaction trước khi replay tới token, snapshot có thể đã cũ. Chờ ngoài transaction đọc, sau đó mở transaction mới.

### 9.4. Đọc sau khi fence đạt

Ngay sau khi kiểm tra đạt, chạy SELECT trên cùng standby và trong transaction mới. Nếu connection bị đổi node giữa check và read, phải kiểm tra lại fence trên node mới.

## 10. LSN fence không phải một distributed transaction

Token chỉ chứng minh standby đã replay tới một vị trí WAL trong history phù hợp. Nó không tạo atomic transaction giữa primary và standby, cũng không khóa primary để ngăn các writes mới.

### 10.1. Có thể có writes mới sau token

Standby có thể tiếp tục replay sau token trong lúc request chạy. Đây là điều bình thường. Token chỉ bảo đảm nó đã vượt qua mốc cần thiết.

### 10.2. Không bảo đảm các node khác đã theo kịp

Nếu token được kiểm tra trên standby A, nó không chứng minh standby B hoặc C đã replay cùng mốc.

### 10.3. Không bảo đảm external side effects

Nếu transaction gọi hệ thống ngoài database, WAL replay chỉ phản ánh PostgreSQL changes. Payment gateway, queue hoặc object storage cần consistency protocol riêng.

### 10.4. Không khắc phục lost commit sau failover

Nếu asynchronous failover promote một standby chưa có transaction, token từ old primary có thể không tồn tại trong new primary history. Application cần xử lý commit ambiguity và reconcile.

## 11. Synchronous replication và read-after-write

Synchronous replication cho phép primary chờ một hoặc nhiều standby xác nhận WAL trước khi báo commit thành công, tùy cấu hình.

Các setting quan trọng:
- synchronous_standby_names: chọn standby synchronous hoặc quorum.
- synchronous_commit: mức acknowledgment cần chờ cho từng transaction/session.
- sync_state: trạng thái synchronous thực tế của standby.

### 11.1. synchronous_commit = on

Với synchronous replication, on chờ standby flush WAL bền vững theo semantics PostgreSQL. Khi commit được xác nhận, standby synchronous đã flush transaction, nhưng có thể chưa replay để phục vụ query đọc.

### 11.2. synchronous_commit = remote_apply

remote_apply chờ synchronous standby replay transaction trước khi commit được xác nhận. Điều này hỗ trợ read-after-write từ standby được chọn, với điều kiện lần đọc bắt đầu sau acknowledgment và được route tới standby đã đáp ứng sync policy.

### 11.3. synchronous_commit = remote_write

remote_write chờ standby ghi WAL tới hệ điều hành, nhưng không bảo đảm remote durable flush như on.

### 11.4. synchronous_commit = local

Chờ local flush theo semantics, không chờ remote synchronous standby.

### 11.5. synchronous_commit = off

Có thể trả COMMIT trước local WAL flush. Điều này giảm latency nhưng có thể mất các transaction vừa được xác nhận khi primary crash. Không dùng như một cách đạt strong durability.

## 12. remote_apply có bảo đảm đọc từ mọi standby không?

Không. Nó chỉ chờ theo synchronous standby policy đang cấu hình.

Ví dụ:
- synchronous_standby_names chọn standby A làm synchronous.
- remote_apply chờ A replay.
- Ứng dụng đọc từ A sau commit acknowledgment: có thể đạt read-after-write.
- Ứng dụng đọc từ standby B đang asynchronous: B có thể vẫn stale.

### 12.1. Quorum synchronous

Nếu cấu hình quorum, commit chờ đủ số standby theo policy. Không giả định mọi node trong danh sách đều đã replay. Application phải biết node nào đáp ứng consistency token hoặc dùng read route phù hợp.

### 12.2. Priority-based synchronous

Với cấu hình ưu tiên, node synchronous active có thể thay đổi khi standby disconnect/reconnect. Theo dõi sync_state và topology tại thời điểm commit.

### 12.3. Node identity cần thiết

Nếu application cần đọc từ chính node đã xác nhận remote_apply, cần có cách xác định node/endpoint phù hợp. Không chỉ gửi token tới một endpoint load-balanced không biết backend.

### 12.4. Latency trade-off

Remote apply làm commit latency phụ thuộc cả network, standby flush và replay. Một query dài trên standby hoặc recovery conflict có thể làm replay chậm, từ đó làm commit chậm.

## 13. Khi nào chọn LSN fence, khi nào chọn remote_apply?

| Cách | Phù hợp khi | Chi phí/giới hạn |
|---|---|---|
| Read primary after write | Đơn giản, cần RYW chắc chắn trên primary hiện tại | Tăng tải primary |
| LSN fence + polling | Cần đọc từ replica nhưng chỉ khi replica đã theo kịp request | Thêm round trips, timeout/fallback logic |
| remote_apply | Cần synchronous commit đợi selected standby replay | Tăng commit latency và phụ thuộc standby |
| Session stickiness | Cần monotonic reads trên cùng replica | Không tự bảo đảm replica đã thấy write |
| Eventual read | Analytics/reporting chấp nhận stale data | UI/business phải chấp nhận freshness window |

### 13.1. Kết hợp nhiều cách

Một hệ thống có thể route các thao tác tài chính tới primary, dùng LSN fence cho trang chi tiết sau write và dùng eventual consistency cho dashboard analytics.

### 13.2. Không mặc định bật remote_apply toàn hệ thống

Chỉ các transaction cần guarantee đó mới cần mức đồng bộ cao hơn nếu application có thể đặt synchronous_commit theo transaction/session và policy cho phép.

### 13.3. Đo trước khi quyết định

Đo commit latency, replica lag distribution, request latency và primary load trước/sau khi áp dụng.

## 14. Read routing theo consistency policy

Application có thể gắn consistency requirement vào từng request.

| Request | Read target | Consistency |
|---|---|---|
| Tạo đơn rồi xem chi tiết | Primary hoặc replica đã đạt token | Read-after-write |
| Trang profile sau cập nhật | Primary hoặc LSN fence | Read-your-writes |
| Dashboard tổng hợp | Standby | Eventual |
| Báo cáo lịch sử | Standby/reporting replica | Eventual, snapshot rõ |
| Kiểm tra quyền vừa thay đổi | Primary hoặc fence | Không chấp nhận stale |
| Feed công khai | Standby | Có thể chấp nhận lag nhỏ |

### 14.1. Đừng route chỉ theo HTTP method

Một GET sau POST có thể phụ thuộc transaction vừa commit. Một GET khác có thể không cần strong consistency. Hãy dùng nghiệp vụ/causal token thay vì chỉ phân loại GET/POST.

### 14.2. Consistency token trong request context

Sau write, application có thể giữ token trong server-side session hoặc gửi token cùng request tiếp theo để read router chọn primary/standby phù hợp.

### 14.3. Token cần giới hạn scope

Token phải gắn với cluster/database history và expiry. Không dùng token từ cluster khác hoặc sau một failover chưa được reconcile.

### 14.4. Tránh lộ thông tin nội bộ

Không nhất thiết expose raw LSN tới client công khai. Có thể dùng opaque token ký/encode ở application layer.

## 15. Connection pool và transaction boundaries

Connection pool có thể cấp một connection khác cho request đọc. Vì vậy không giả định connection đã ghi transaction cũng là connection đọc tiếp theo.

### 15.1. Pool có primary và replica endpoints

Cần route rõ endpoint theo consistency policy. Một transaction không nên vô tình chuyển giữa primary và standby.

### 15.2. Transaction pooling

Proxy ở transaction pooling mode có thể cấp backend khác sau mỗi transaction. LSN token hoặc route metadata phải sống ở application layer, không dựa vào session state backend.

### 15.3. Session variables

Không dùng session variable trên một connection để lưu consistency token nếu request sau có thể dùng connection khác. Lưu ở application/session store có kiểm soát.

### 15.4. Reset state khi trả connection

Nếu đặt synchronous_commit, isolation level hoặc read routing state theo session, phải reset trước khi trả connection về pool để tránh ảnh hưởng request tiếp theo.

## 16. Read-your-writes trong cùng transaction

Nếu ứng dụng ghi rồi đọc trong cùng transaction trên primary, PostgreSQL cho transaction thấy writes của chính nó.

```sql
BEGIN;

INSERT INTO public.orders (order_id, status)
VALUES (9001, 'NEW');

SELECT order_id, status
FROM public.orders
WHERE order_id = 9001;

COMMIT;
```

Đọc từ chính transaction này không cần chờ replication. Nhưng nếu ứng dụng commit rồi route SELECT sang standby trước khi replay, phải áp dụng một policy khác.

### 16.1. Uncommitted writes

Transaction khác không nhìn thấy uncommitted writes theo isolation semantics thông thường. Đọc từ standby càng không thể nhìn thấy transaction chưa được commit/replay.

### 16.2. Read-your-writes không phải read-your-concurrent-writes

Nếu một transaction khác cập nhật cùng row sau commit của bạn, kết quả phụ thuộc snapshot/time/order. RYW chỉ bảo đảm thấy writes của mình trong history hợp lệ.

### 16.3. Đọc sau COMMIT trên primary

Mở statement/transaction mới trên primary để thấy committed state theo snapshot mới. Nếu có failover và async loss, phải xét commit ambiguity riêng.

## 17. Monotonic reads khi có nhiều standby

Giả sử:
- Request A đọc standby 1 tại replay LSN 0/500.
- Request B đọc standby 2 tại replay LSN 0/420.

Người dùng có thể thấy một giá trị cũ hơn ở request B. Đây là non-monotonic read.

### 17.1. Sticky replica

Giữ session ở cùng replica giúp tránh chuyển sang node lùi hơn, nhưng replica vẫn có thể tạm dừng replay hoặc failover.

### 17.2. Track last-seen LSN

Application có thể giữ LSN fence lớn nhất mà session đã quan sát. Trước lần đọc sau, chỉ chọn replica có replay LSN >= last-seen token.

### 17.3. Nếu không có replica đạt token

Chờ trong latency budget hoặc route primary. Không trả dữ liệu cũ hơn mà không có policy rõ ràng.

### 17.4. Sau failover

Last-seen LSN thuộc timeline cũ. Cần mapping/history hoặc reset/reconcile session consistency state. Không so sánh số LSN trần qua timeline fork.

## 18. Causal reads qua nhiều request

Ví dụ:
1. User tạo order.
2. Service phát event order-created.
3. Consumer cập nhật read model.
4. User mở trang order status.

Nếu read model là PostgreSQL standby, nó phải replay WAL tới thay đổi liên quan trước khi trả trạng thái cần thiết. Nếu event được xử lý ở database khác, causal token cần đi qua toàn bộ pipeline chứ không chỉ một LSN.

### 18.1. Causal dependency graph

Ghi nhận operation nào phụ thuộc operation nào. Chỉ chờ một PostgreSQL LSN không chứng minh message queue consumer hoặc external index đã xử lý event.

### 18.2. Outbox/inbox

Outbox ghi event trong cùng transaction với business change; consumer xử lý event idempotently. Read model có thể cần watermark riêng để biết event sequence nào đã apply.

### 18.3. Watermark khác LSN

Nếu pipeline chuyển đổi dữ liệu qua queue/ETL, dùng event sequence/offset/watermark của pipeline. LSN PostgreSQL không thay thế offset của Kafka hoặc checkpoint của consumer.

### 18.4. UI trạng thái pending

Nếu eventual read model chưa cập nhật, UI có thể hiển thị “đang cập nhật” hoặc tạm dùng primary result thay vì trả stale value như kết quả cuối cùng.

## 19. Transaction snapshot trên standby

Hot standby phục vụ read-only queries trong khi replay. Snapshot của query/transaction xác định dữ liệu nó nhìn thấy.

### 19.1. Statement snapshot

Trong READ COMMITTED, mỗi statement có snapshot mới. Nếu query bắt đầu sau khi replay đạt token, nó có thể thấy changes đã replay.

### 19.2. Transaction snapshot

Trong REPEATABLE READ/SERIALIZABLE, transaction có snapshot ổn định. Chờ replay giữa hai statement không làm snapshot cũ tự cập nhật.

### 19.3. Long-running queries

Một query dài đã bắt đầu trước khi replay tiến tới LSN mới có thể tiếp tục dùng snapshot cũ tới khi hoàn tất.

### 19.4. Connection pool reuse

Một connection có thể còn transaction mở do ứng dụng quên COMMIT/ROLLBACK. Kiểm tra transaction state trước khi đọc sau khi chờ fence.

## 20. Standby delayed có chủ ý

PostgreSQL hỗ trợ recovery_min_apply_delay để trì hoãn replay trong một khoảng thời gian. Delayed standby có thể giúp phục hồi trước thao tác phá hoại đã được replicate, nhưng không phù hợp cho read-after-write freshness.

### 20.1. Receive có thể nhanh, replay có chủ ý chậm

Standby có thể nhận/flush WAL nhưng chờ apply. LSN receive và replay sẽ cách nhau.

### 20.2. Không route RYW tới delayed standby

Một request vừa ghi có thể phải chờ hết delay policy, làm latency lớn. Route primary hoặc replica không delayed.

### 20.3. Delayed standby có vai trò khác

Nó là lớp bảo vệ trước logical mistakes trong một số kiến trúc. Không nhất thiết là failover target đầu tiên.

### 20.4. Không xóa delay chỉ để đạt freshness

Thay đổi delay có thể làm mất mục đích bảo vệ. Đánh giá riêng yêu cầu HA và yêu cầu delayed recovery.

## 21. Recovery conflicts và read freshness

Standby có thể trì hoãn WAL replay do query conflicts. Các setting như max_standby_streaming_delay và hot_standby_feedback ảnh hưởng cân bằng giữa query continuity và replay freshness.

### 21.1. Query dài có thể giữ replay lại

Nếu replay operation xung đột với snapshot/query, PostgreSQL có thể chờ hoặc cancel query tùy setting.

### 21.2. Replay lag tăng

Read-after-write fence sẽ chờ lâu hơn. Đây là tín hiệu standby không đáp ứng latency budget của request.

### 21.3. hot_standby_feedback

Feedback có thể giảm một số query cancellations nhưng có thể khiến primary giữ dead tuples lâu hơn. Theo dõi bloat và vacuum horizon.

### 21.4. Tách reporting workload

Dùng standby riêng cho analytics query dài nếu chúng làm ảnh hưởng replica phục vụ freshness/failover.

## 22. Synchronous replication: durability và visibility

Cần phân biệt ba khái niệm:
- WAL đã được ghi/flush trên standby.
- WAL đã được replay.
- Query transaction có snapshot nhìn thấy thay đổi đó.

remote_apply đi xa hơn remote flush vì chờ replay. Tuy nhiên transaction đọc vẫn cần snapshot bắt đầu sau khi commit acknowledgment và route tới node phù hợp.

### 22.1. on không đồng nghĩa remote apply

Với synchronous standby, on chờ remote flush; standby có thể chưa replay khi commit trả về.

### 22.2. remote_apply không bỏ qua snapshot rules

Một REPEATABLE READ transaction bắt đầu trước commit vẫn có thể không thấy transaction đó, kể cả standby đã replay.

### 22.3. Không có synchronous standby thì không có remote guarantee

Chỉ đặt synchronous_commit không tự tạo standby hoặc xác định node đồng bộ. Kiểm tra synchronous_standby_names và pg_stat_replication.sync_state.

### 22.4. Failover selection phải phù hợp

Nếu policy yêu cầu không mất acknowledged commits, promotion phải chọn standby có durability evidence phù hợp. Remote apply acknowledgment từ node A không bảo đảm node B chứa transaction.

## 23. Read-after-write qua load balancer

Một load balancer có thể phân phối request tới nhiều standby. Nếu không biết replay position từng backend, một request có thể đi tới replica stale.

### 23.1. Sticky routing

Có thể gắn session vào một replica, nhưng vẫn cần kiểm tra replica đạt token sau write.

### 23.2. Consistency-aware routing

Router có thể:
1. Nhận token.
2. Chọn standby đủ mới.
3. Nếu không có, thử standby khác.
4. Nếu hết budget, dùng primary.
5. Nếu primary không khả dụng, trả trạng thái retry/uncertain theo policy.

### 23.3. Backend identity

Nếu proxy không cung cấp identity, application có thể chạy query trả server address/role/cluster metadata để ghi nhận backend. Không dùng thông tin đó như security identity; nó phục vụ routing/observability.

### 23.4. Pooler transaction mode

Proxy transaction pooling có thể thay backend giữa transaction. Đảm bảo consistency check và actual SELECT chạy trong cùng transaction/backend, hoặc kiểm tra lại token trên backend đã chọn.

## 24. Fallback khi standby chưa đạt token

| Lựa chọn | Hành vi | Phù hợp |
|---|---|---|
| Wait | Chờ replica đạt LSN | Lag ngắn, latency budget đủ |
| Retry another replica | Chọn standby khác đã theo kịp | Nhiều replicas |
| Read primary | Bỏ qua stale replica | RYW quan trọng |
| Return pending/retry | Báo chưa sẵn sàng | Không thể đọc primary |
| Serve stale with label | Trả dữ liệu cũ có ghi rõ | Analytics/feed chấp nhận |

### 24.1. Không fallback im lặng sang stale data

Nếu business yêu cầu read-after-write, trả stale data mà không báo là vi phạm contract.

### 24.2. Timeout và circuit breaker

Nếu replica thường xuyên không đạt freshness SLO, có thể tạm giảm traffic read hoặc mở circuit breaker. Theo dõi primary load khi fallback.

### 24.3. Primary overload

Nếu mọi RYW request fallback sang primary, primary có thể quá tải. Capacity planning cần tính tỷ lệ fallback trong lag incidents.

### 24.4. Không thể dùng primary

Nếu primary unavailable và standby chưa đạt token, không có cách tạo dữ liệu chưa replicate. Application phải xử lý unavailable/uncertain thay vì giả định transaction tồn tại.

## 25. Read-after-write sau failover

Failover là tình huống đặc biệt vì primary history có thể đổi.

### 25.1. Synchronous failover

Nếu acknowledged commit đã được flush/replayed trên standby được promote theo policy, transaction có thể tồn tại trên new primary. Vẫn cần xác minh node và transaction history.

### 25.2. Asynchronous failover

Một commit được xác nhận trên old primary có thể chưa tới standby được promote. Khi đó read-after-write không thể được bảo đảm chỉ bằng token cũ.

### 25.3. Commit ambiguity

Nếu client mất kết nối đúng lúc COMMIT, ứng dụng có thể không biết transaction đã commit hay chưa. Dùng idempotency key/business operation ID để truy vấn/reconcile trên new primary.

### 25.4. Token thuộc timeline cũ

Không so sánh LSN token cũ với replay LSN mới như hai số trong một chuỗi duy nhất. Cần nhận diện timeline/history và xác định transaction có được giữ trong new primary hay không.

## 26. Idempotency cho write retry

Khi commit acknowledgment bị mất do network/failover, client có thể retry. Nếu thao tác không idempotent, có thể tạo duplicate orders/payments.

```sql
CREATE TABLE request_deduplication (
    request_key uuid PRIMARY KEY,
    result_json jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Trong một transaction:
1. Insert request_key.
2. Nếu key đã tồn tại, đọc kết quả đã lưu.
3. Nếu mới, thực hiện business write.
4. Lưu response/result.
5. Commit.

### 26.1. Unique key là hàng rào cuối

Database unique constraint giúp ngăn cùng request key được xử lý thành hai records, nếu mọi retries dùng cùng key.

### 26.2. Idempotency window

Giữ deduplication record đủ lâu theo retry/client behavior và business requirements. Cleanup quá sớm có thể cho phép duplicate retry.

### 26.3. Không dựa vào client timeout để kết luận rollback

Client timeout không nói transaction đã rollback. Kết quả có thể unknown; truy vấn idempotency key trên primary mới.

## 27. Đọc nhất quán trên nhiều bảng

Một request có thể đọc nhiều bảng có quan hệ. Nếu các changes được commit cùng transaction trên primary, WAL replay giữ transaction atomicity khi apply. Tuy nhiên request phải đọc sau khi standby replay tới transaction đó và dùng snapshot phù hợp.

### 27.1. Một transaction đọc

Dùng một transaction READ COMMITTED/REPEATABLE READ theo business need để đọc các bảng trong cùng snapshot. Nếu muốn một snapshot ổn định, bắt đầu transaction sau khi fence đạt.

### 27.2. Nhiều request đọc

Nếu request 1 đọc orders và request 2 đọc payments, cả hai cần cùng consistency token hoặc causal context để không thấy một nửa workflow.

### 27.3. Cross-database reads

PostgreSQL standby replay token chỉ áp dụng cho WAL history của cluster đó. Nếu dữ liệu nằm ở hai cluster, cần coordination token/watermark ở tầng ứng dụng.

### 27.4. Cross-service dependencies

Một transaction database không tự bảo đảm event consumer, cache hay search index đã cập nhật. Mỗi read model cần freshness contract riêng.

## 28. Cache làm phức tạp read-after-write

Ngay cả khi standby đã replay, cache có thể trả dữ liệu cũ.

Các tầng có thể có:
- Application in-memory cache.
- Redis/Memcached.
- CDN.
- ORM identity map.
- Browser cache.
- Search index.

### 28.1. Invalidate sau commit

Chỉ invalidate cache sau khi commit thành công. Invalidate trước commit có thể cho request khác refill dữ liệu cũ.

### 28.2. Versioned cache keys

Có thể gắn entity version/update sequence vào cache key để tránh đọc entry cũ sau write.

### 28.3. Cache bypass cho RYW

Request vừa ghi có thể bypass cache hoặc đọc cache entry được cập nhật từ transaction result.

### 28.4. Replication fence không kiểm soát cache

LSN token chỉ chứng minh standby đã replay. Nó không chứng minh Redis/CDN/search index đã cập nhật.

## 29. Read consistency cho pagination và feed

Pagination trên standby có thể thay đổi giữa các request nếu data mới được replay hoặc thứ tự sort không ổn định.

### 29.1. Keyset pagination

Dùng stable ordering key, ví dụ (created_at, id), thay offset-only pagination khi dữ liệu thay đổi liên tục.

### 29.2. Snapshot consistency

Nếu cần một tập kết quả ổn định xuyên nhiều pages, cần snapshot/export strategy hoặc materialized result; mỗi HTTP request độc lập thường không giữ cùng transaction snapshot.

### 29.3. Monotonic feed

Nếu feed item vừa tạo phải xuất hiện ngay, route read theo token hoặc trả item vừa tạo từ write response trong khi read model catch up.

### 29.4. Analytics freshness

Nếu chấp nhận eventual consistency, hiển thị updated-at hoặc freshness watermark để người dùng hiểu độ mới dữ liệu.

## 30. Read-after-write với sequence và generated IDs

Sau INSERT, ứng dụng thường nhận generated ID qua RETURNING. Đọc ngay row từ primary hoặc standby cần consistency policy tương tự.

```sql
INSERT INTO public.orders (status)
VALUES ('NEW')
RETURNING order_id;
```

Nếu response trả ID rồi request sau đọc standby trước khi replay, row có thể chưa tồn tại ở đó.

### 30.1. Trả representation từ write result

Nếu phù hợp, trả row/result từ transaction ghi để tránh read-after-write round trip.

### 30.2. Sequence state không giống row replication

Sequence values không được logical replication đồng bộ như row data; trong physical standby, WAL/recovery giữ state theo physical history. Khi failover/migration, vẫn cần kiểm tra sequence policy.

### 30.3. Không suy ra row visible chỉ từ ID được cấp

ID có thể được tạo trước commit hoặc transaction có thể rollback. Chỉ coi row committed sau khi transaction thành công.

## 31. Read-after-write cho quyền truy cập và security state

Các thay đổi như revoke role, disable account, update permission hoặc rotate access state thường cần freshness cao.

Nếu authorization service đọc standby stale, user vừa bị khóa có thể vẫn được cấp quyền theo dữ liệu cũ.

### 31.1. Security-sensitive reads

Đọc từ primary hoặc consistency-aware replica cho access-control decisions cần cập nhật ngay.

### 31.2. Cache TTL

TTL dài có thể kéo dài stale window ngay cả khi PostgreSQL đã replay. Invalidation/versioning cần đi cùng replication policy.

### 31.3. Fail closed hay fail open

Khi primary/replica không thể xác minh quyền mới nhất, policy phải do security/business owner quyết định. Không tự mặc định fail-open cho thao tác nhạy cảm.

### 31.4. Audit

Ghi request, decision version/LSN token và source node theo policy để điều tra nếu stale authorization xảy ra.

## 32. Read-after-write cho balance và inventory

Các nghiệp vụ cần không bán vượt tồn kho hoặc không hiển thị balance sai phải có consistency strategy rõ.

### 32.1. Command/query separation

Ghi command vào primary; đọc kết quả ngay từ transaction/write response hoặc primary. Read model trên standby có thể cập nhật sau.

### 32.2. Không dùng stale replica để quyết định invariant

Nếu quyết định giảm inventory dựa trên một replica stale, hai request có thể cùng thấy stock cũ. Invariant phải được kiểm soát bằng transaction/locking/constraints trên authoritative primary.

### 32.3. Hiển thị trạng thái pending

Read model chậm có thể hiển thị trạng thái pending với version/watermark, sau đó cập nhật khi projection catch up.

### 32.4. Read replica không thay transaction isolation

Không dùng replica routing để thay row locks, atomic updates hoặc constraints cần thiết cho correctness.

## 33. Kiểm tra consistency bằng SQL

Trên primary, sau khi transaction commit:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_current_wal_lsn() AS consistency_lsn;
```

Trên standby:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_wal_replay_lsn() >= '0/16B6C50'::pg_lsn AS reached_token;
```

### 33.1. Xem replication positions trên primary

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
```

### 33.2. Xem receiver trên standby

```sql
SELECT
    status,
    received_tli,
    written_lsn,
    flushed_lsn,
    latest_end_lsn,
    last_msg_receipt_time
FROM pg_stat_wal_receiver;
```

### 33.3. Kiểm tra row sau fence

```sql
SELECT
    order_id,
    status,
    updated_at
FROM public.orders
WHERE order_id = 9001;
```

Chạy SELECT trong transaction mới sau khi token đã đạt.

## 34. Đo read-after-write latency

Đo thời gian từ COMMIT acknowledgment tới khi standby đạt token và query đọc thấy dữ liệu.

Một test agent:
1. Ghi một marker unique trên primary.
2. COMMIT.
3. Lấy LSN token sau commit.
4. Bắt đầu timer monotonic.
5. Poll standby replay LSN.
6. Khi đạt token, mở transaction mới và query marker.
7. Xác nhận marker tồn tại.
8. Ghi elapsed time, replica identity và token.
9. Lặp lại ở giờ cao điểm/thấp điểm.

### 34.1. Đo nhiều percentile

Báo cáo median, P95, P99 khi có đủ samples, cùng timeout rate và fallback rate.

### 34.2. Tách wait time và query time

Ghi riêng commit latency, time waiting for replay, standby query latency và application end-to-end latency.

### 34.3. Kiểm tra false success

Không chỉ dừng khi replay LSN >= token; còn phải query row/transaction marker và xác nhận kết quả nghiệp vụ.

### 34.4. Test trên mọi replica class

Standby synchronous, async, cross-region, delayed và reporting có freshness khác nhau. Đo riêng.

## 35. Timeout, retry và fallback design

Consistency wait cần có timeout. Ví dụ policy:
- Chờ standby 100 ms.
- Nếu chưa đạt, thử standby khác.
- Nếu vẫn chưa đạt và primary khỏe, route primary.
- Nếu primary unavailable, trả retryable/unavailable theo business contract.

Đây chỉ là ví dụ; budget thực tế phụ thuộc SLA.

### 35.1. Retry phải idempotent

Read retry an toàn hơn write retry. Nếu retry write sau timeout commit ambiguity, dùng idempotency key.

### 35.2. Jitter

Thêm jitter vào polling/retry để tránh thundering herd.

### 35.3. Circuit breaker

Nếu replica thường xuyên không đạt freshness SLO, tạm ngừng route consistency-sensitive reads tới node đó.

### 35.4. Observability

Ghi reason code: token_not_reached, wrong_timeline, replica_disconnected, timeout, primary_fallback hoặc cache_bypass.

## 36. Cập nhật routing sau promotion

Khi standby được promote:
- pg_is_in_recovery() đổi trạng thái.
- Endpoint role cần được cập nhật.
- Các replicas khác cần follow new primary theo topology.
- LSN/timeline history có thể thay đổi.
- Session tokens từ history cũ cần được xử lý.

### 36.1. Không để application ghi vào old primary

Fencing và routing update phải ngăn split-brain. DNS TTL thấp một mình không thay fencing.

### 36.2. Xác nhận new primary

Dùng orchestration/HA manager có authoritative role state, health checks và fencing. Không chỉ dựa vào một query từ endpoint load balancer.

### 36.3. Token migration

Nếu old commit được xác nhận mất trong async failover, application phải reconcile bằng idempotency key/business record. Không thể làm transaction xuất hiện bằng cách chờ LSN token cũ.

### 36.4. Rebuild session consistency state

Sau failover, có thể cần reset hoặc remap per-session last-seen token theo new timeline và dữ liệu đã xác minh.

## 37. Consistency với cache và read models

Một hệ thống có thể có nhiều bản sao:
- PostgreSQL primary.
- Physical standby.
- Logical subscriber.
- Redis cache.
- Search index.
- Analytics warehouse.

Mỗi bản có pipeline và watermark riêng.

### 37.1. Không dùng PostgreSQL LSN cho mọi hệ thống

LSN chỉ mô tả WAL history của PostgreSQL cluster. Logical consumers, message brokers và search index có checkpoint/offset riêng.

### 37.2. Watermark hợp nhất

Application có thể giữ một causal context gồm PostgreSQL LSN, event ID và consumer watermark nếu request phụ thuộc nhiều systems.

### 37.3. Cache invalidation sau commit

Dùng outbox hoặc versioned cache updates để giảm race giữa commit và cache invalidation.

### 37.4. Read model có thể chậm dù PostgreSQL standby nhanh

Nếu ETL/consumer phía sau bị chậm, read model không theo kịp. Đo pipeline end-to-end.

## 38. Các consistency anti-patterns

- Ghi primary, đọc bất kỳ standby nào ngay lập tức mà không chấp nhận stale reads.
- Dùng sleep cố định 1 giây thay cho kiểm tra replay LSN.
- Coi write_lag hoặc replay_lag là bảo đảm RYW.
- Dùng sticky session nhưng không theo dõi replica freshness.
- Kiểm tra LSN trên standby A rồi query standby B.
- Chờ LSN trong một REPEATABLE READ transaction đã mở trước đó.
- Bật remote_apply nhưng route read tới async replica khác.
- So sánh LSN qua timeline fork mà không kiểm tra history.
- Coi cache đã invalidate khi transaction chưa commit.
- Retry non-idempotent writes sau network timeout.
- Dùng read replica stale để quyết định inventory/balance/authorization.
- Gọi database start là service restored.
- Dùng một metric PostgreSQL để đại diện cho queue/search/cache pipeline.
- Bỏ qua fallback rate và làm primary quá tải khi replica lag.

## 39. Runbook: request vừa ghi nhưng đọc không thấy

1. Ghi request ID, transaction ID/business key và thời điểm COMMIT acknowledgment.
2. Xác định write đã commit thành công hay client gặp commit ambiguity.
3. Ghi primary identity, cluster identity và LSN token sau commit nếu có.
4. Xác định read request đi tới primary hay standby nào.
5. Kiểm tra pg_is_in_recovery() và server identity trên read backend.
6. Nếu là standby, kiểm tra pg_last_wal_replay_lsn().
7. So sánh replay LSN với token trong cùng WAL history.
8. Kiểm tra transaction isolation/snapshot có được mở trước khi replay không.
9. Kiểm tra cache, ORM identity map và application read model.
10. Nếu token chưa đạt, chờ trong budget hoặc route primary.
11. Nếu token đã đạt, mở transaction mới và kiểm tra row/query.
12. Nếu failover xảy ra, xác minh timeline và reconcile commit ambiguity.
13. Ghi lại stale-read duration, fallback và root cause.

### 39.1. Không kết luận replication hỏng ngay

Có thể chỉ là request được route tới standby trước khi replay. Xác định node và LSN trước.

### 39.2. Nếu token đạt nhưng row không có

Kiểm tra transaction đã commit đúng database/schema chưa, row filter/application query có loại row không, transaction có rollback/overwrite không và token có đúng cluster/timeline không.

### 39.3. Nếu primary cũng không thấy

Có thể commit chưa thành công, transaction rollback, application đọc sai tenant/database hoặc commit outcome unknown.

## 40. Runbook: thiết kế consistency cho một endpoint

1. Xác định nghiệp vụ và dữ liệu mà endpoint cần.
2. Xác định có phụ thuộc write vừa commit không.
3. Định nghĩa stale window được chấp nhận.
4. Chọn primary, LSN fence, remote_apply hoặc eventual read.
5. Xác định transaction snapshot/isolation.
6. Xác định routing và replica identity.
7. Đặt timeout/fallback behavior.
8. Xử lý cache/ORM/read models.
9. Định nghĩa idempotency cho writes và retries.
10. Viết integration test cho lag, timeout, failover và stale cache.
11. Đo latency/fallback rate.
12. Ghi consistency contract vào API/runbook.

## 41. Bài tập thực hành có đáp án

### Bài 1. Vì sao đọc từ standby có thể trả dữ liệu cũ?

**Đáp án:** Standby có thể chưa replay WAL chứa transaction vừa commit trên primary.

### Bài 2. WAL đã receive có nghĩa row đã visible?

**Đáp án:** Không. WAL còn phải được replay.

### Bài 3. Read-after-write là gì?

**Đáp án:** Sau khi write thành công, lần đọc tiếp theo của client nhìn thấy thay đổi đó theo consistency contract.

### Bài 4. Read-your-writes khác eventual consistency thế nào?

**Đáp án:** Read-your-writes bảo đảm client thấy writes của mình; eventual consistency chỉ yêu cầu replicas hội tụ sau khi không còn updates.

### Bài 5. Monotonic reads có nghĩa gì?

**Đáp án:** Client không nhìn thấy trạng thái cũ hơn trạng thái mà nó đã quan sát trước đó.

### Bài 6. Session stickiness tới standby có bảo đảm RYW?

**Đáp án:** Không. Standby đó vẫn có thể chưa replay transaction vừa commit.

### Bài 7. Cách đơn giản nhất để đọc ngay sau ghi?

**Đáp án:** Route read tới primary hoặc đọc kết quả ngay trong transaction ghi.

### Bài 8. LSN token là gì?

**Đáp án:** Một WAL position được lấy sau commit để làm consistency fence cho standby.

### Bài 9. Vì sao lấy token sau COMMIT?

**Đáp án:** Để token bao gồm commit record; token lấy trước commit có thể chưa bao gồm transaction cần đọc.

### Bài 10. Function nào lấy current WAL write position trên primary?

**Đáp án:** pg_current_wal_lsn().

### Bài 11. Function nào lấy replay position trên standby?

**Đáp án:** pg_last_wal_replay_lsn().

### Bài 12. Điều kiện fence cơ bản?

**Đáp án:** Standby replay LSN phải bằng hoặc vượt token trong cùng WAL history.

### Bài 13. Có nên so LSN bằng text comparison trong application?

**Đáp án:** Không. Dùng kiểu pg_lsn/operator hoặc parser chính xác, đồng thời xét cluster/timeline.

### Bài 14. Vì sao token có thể cao hơn commit của request?

**Đáp án:** WAL của transaction concurrent khác có thể được ghi trước khi token được đọc; token vẫn là upper bound an toàn trong cùng history.

### Bài 15. LSN fence có phải distributed transaction?

**Đáp án:** Không. Nó chỉ kiểm tra replay progress của một standby.

### Bài 16. Sau khi token đạt, có cần transaction đọc mới?

**Đáp án:** Có, để lấy snapshot bắt đầu sau khi replay đạt token, đặc biệt nếu trước đó có transaction snapshot cũ.

### Bài 17. READ COMMITTED lấy snapshot khi nào?

**Đáp án:** Mỗi statement thường lấy snapshot mới.

### Bài 18. REPEATABLE READ có tự thấy WAL mới giữa transaction không?

**Đáp án:** Không. Transaction giữ snapshot ổn định.

### Bài 19. SERIALIZABLE trên standby có đồng bộ snapshot với primary?

**Đáp án:** Không. Nó chỉ cung cấp isolation semantics trên node/transaction đó.

### Bài 20. synchronous_commit = on có chờ standby replay?

**Đáp án:** Không. Với synchronous replication, on chờ remote WAL flush.

### Bài 21. remote_apply chờ điều gì?

**Đáp án:** Chờ synchronous standby replay WAL transaction trước khi commit acknowledgment được trả về.

### Bài 22. remote_apply có bảo đảm mọi standby đã replay?

**Đáp án:** Không. Nó tuân theo synchronous standby policy; async replicas khác có thể còn lag.

### Bài 23. remote_write có tương đương remote durable flush?

**Đáp án:** Không. Nó chờ standby ghi WAL tới OS, không phải durable flush.

### Bài 24. Chỉ đặt synchronous_commit = remote_apply có đủ không?

**Đáp án:** Không. Cần cấu hình synchronous_standby_names và standby thực sự hoạt động.

### Bài 25. remote_apply có thể tăng commit latency vì sao?

**Đáp án:** Commit phải chờ network, standby flush và replay.

### Bài 26. Vì sao query dài trên standby ảnh hưởng remote_apply?

**Đáp án:** Recovery conflicts có thể trì hoãn replay, khiến commit chờ lâu hơn.

### Bài 27. Delayed standby có phù hợp RYW không?

**Đáp án:** Thường không; replay bị trì hoãn có chủ ý.

### Bài 28. Vì sao không dùng sleep cố định để chờ replica?

**Đáp án:** Lag thay đổi theo workload; sleep có thể quá ngắn hoặc gây latency không cần thiết.

### Bài 29. Polling LSN cần timeout không?

**Đáp án:** Có. Request cần latency budget và fallback policy.

### Bài 30. Nếu standby chưa đạt token thì có những lựa chọn nào?

**Đáp án:** Chờ, thử replica khác, đọc primary, trả retry/unavailable hoặc serve stale nếu contract cho phép.

### Bài 31. Vì sao phải kiểm tra cùng standby giữa fence và SELECT?

**Đáp án:** Nếu query được route sang node khác, node đó có thể chưa replay tới token.

### Bài 32. LSN token có thể so sánh mù qua failover timeline không?

**Đáp án:** Không. Timeline có thể fork; cần xác định history và transaction survival.

### Bài 33. Async failover có thể làm mất commit đã được client xác nhận?

**Đáp án:** Có, nếu standby được promote chưa nhận transaction đó.

### Bài 34. Commit ambiguity là gì?

**Đáp án:** Client mất kết nối quanh thời điểm COMMIT và không biết transaction đã commit hay rollback.

### Bài 35. Idempotency key giúp gì?

**Đáp án:** Cho phép retry một business operation mà không tạo duplicate effects khi commit outcome không rõ.

### Bài 36. Cache có thể làm stale read dù standby đã replay?

**Đáp án:** Có. Cache/ORM/search index có freshness pipeline riêng.

### Bài 37. Cache invalidation nên diễn ra khi nào?

**Đáp án:** Sau khi transaction commit thành công, theo policy nhất quán của ứng dụng.

### Bài 38. LSN fence có chứng minh Redis đã cập nhật?

**Đáp án:** Không. LSN chỉ mô tả PostgreSQL WAL replay.

### Bài 39. Causal consistency qua message queue cần gì?

**Đáp án:** Event ID/offset/watermark và cơ chế theo dõi consumer progress; PostgreSQL LSN một mình chưa đủ.

### Bài 40. Một GET request có thể cần read-after-write không?

**Đáp án:** Có. HTTP method không quyết định consistency; nghiệp vụ và causal dependency mới quyết định.

### Bài 41. Balance/inventory có nên dựa vào stale standby để quyết định ghi?

**Đáp án:** Không. Invariant cần được bảo vệ trên authoritative primary bằng transaction/constraints/locking phù hợp.

### Bài 42. Read replica có thay row lock không?

**Đáp án:** Không. Read replica phục vụ reads; nó không thay transaction coordination trên primary.

### Bài 43. Vì sao phải route security-sensitive reads cẩn thận?

**Đáp án:** Stale permissions/account state có thể cho phép truy cập đã bị revoke.

### Bài 44. Sau khi fence đạt, REPEATABLE READ transaction cũ có thấy dữ liệu mới không?

**Đáp án:** Không. Cần transaction snapshot mới.

### Bài 45. Làm sao đo read-after-write latency?

**Đáp án:** Đo từ COMMIT acknowledgment tới lúc standby replay đạt token và query xác nhận marker.

### Bài 46. P95 read-after-write wait giúp gì?

**Đáp án:** Cho biết tail latency của replica freshness và giúp đặt timeout/fallback budget.

### Bài 47. Vì sao cần kiểm tra pg_is_in_recovery()?

**Đáp án:** Để biết endpoint đang là standby hay đã được promote; role ảnh hưởng cách diễn giải replay LSN.

### Bài 48. Nếu primary unavailable và standby chưa đạt token thì sao?

**Đáp án:** Không thể tạo ra transaction chưa replicate; phải xử lý unavailable/uncertain và reconcile theo business policy.

### Bài 49. Read-after-write guarantee có tự áp dụng tới search index không?

**Đáp án:** Không. Search index cần consumer watermark hoặc consistency mechanism riêng.

### Bài 50. Một endpoint có consistency contract tốt cần định nghĩa gì?

**Đáp án:** Source of truth, stale window, read route, snapshot behavior, token/fence, timeout/fallback, cache behavior và validation tests.

## 42. Checklist thiết kế read consistency

| Giai đoạn | Câu hỏi |
|---|---|
| Business | Request có phụ thuộc write vừa commit không? |
| Business | Stale window tối đa chấp nhận được là bao lâu? |
| Source | Primary nào là authoritative? |
| Routing | Read đi tới primary hay standby nào? |
| Replication | Standby async, sync, quorum hay delayed? |
| Token | Có cần LSN fence sau commit? |
| Fence | Token có được lấy sau COMMIT? |
| Identity | Check và SELECT có chạy cùng standby? |
| Snapshot | Transaction đọc bắt đầu sau fence chưa? |
| Isolation | READ COMMITTED hay snapshot cố định? |
| Timeout | Wait budget có giới hạn? |
| Fallback | Chuyển primary, retry hay trả pending? |
| Failover | Token có thuộc timeline hiện tại? |
| Cache | Cache/ORM/search index có stale không? |
| Retry | Write có idempotency key? |
| Security | Permission-sensitive reads có freshness phù hợp? |
| Metrics | Commit latency, wait time, fallback rate được đo? |
| Testing | Có test lag, failover, timeout và cache race? |
| Documentation | Endpoint consistency contract được ghi rõ? |

## 43. Tài liệu PostgreSQL chính thức

- [Hot Standby](https://www.postgresql.org/docs/current/hot-standby.html) — đọc trên standby, snapshot và recovery conflicts.
- [Warm Standby / Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html) — WAL streaming và standby.
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION) — synchronous standby và commit acknowledgment.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — synchronous_commit và WAL settings.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — READ COMMITTED, REPEATABLE READ và SERIALIZABLE.
- [System Administration Functions](https://www.postgresql.org/docs/current/functions-admin.html) — current/replay LSN và recovery functions.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — replication positions và lag.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — synchronous_standby_names và replication settings.
- [Recovery Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html#RUNTIME-CONFIG-WAL-RECOVERY-TARGET) — recovery delay settings.

Các replication views, synchronous behavior và function availability có thể thay đổi theo PostgreSQL major version. Trước khi triển khai consistency fence hoặc remote_apply, kiểm tra server_version, pg_settings, topology và tài liệu đúng phiên bản.

## 44. Tổng kết: chọn read path theo consistency contract

```text
Write transaction
      |
      v
COMMIT acknowledged on primary
      |
      +--> Read from primary
      |        |
      |        +--> Fresh primary snapshot
      |
      +--> Read from standby
               |
               v
          Obtain LSN token
               |
               v
          Check replay_lsn >= token
               |
          +----+----+
          |         |
         Yes        No
          |         |
          v         v
      New read    Wait / retry
      transaction     |
          |            +--> Another replica
          v            +--> Primary fallback
      Read-your-writes +--> Pending/unavailable
```

Những nguyên tắc cần nhớ:

1. **Standby có thể stale dù replication đang hoạt động bình thường.** WAL phải được replay trước khi thay đổi visible.
2. **Read-after-write là contract của application.** Không tự có chỉ vì write đã COMMIT trên primary.
3. **Đọc primary là cách đơn giản nhất cho RYW.** Dùng standby khi có freshness policy rõ ràng.
4. **LSN token tạo consistency fence.** Lấy sau COMMIT và chỉ so sánh trong cùng cluster/WAL history.
5. **Fence phải được kiểm tra trên đúng standby sẽ phục vụ SELECT.** Không check một node rồi đọc node khác.
6. **Mở transaction đọc sau khi fence đạt.** Snapshot REPEATABLE READ cũ không tự cập nhật.
7. **remote_apply chờ synchronous standby replay.** Nó không bảo đảm mọi async standby đã theo kịp.
8. **Session stickiness không thay LSN fence.** Cùng một standby vẫn có thể lag.
9. **Cache và read models có consistency riêng.** PostgreSQL LSN không chứng minh external consumers đã cập nhật.
10. **Failover có thể đổi timeline và làm commit ambiguity xuất hiện.** Dùng idempotency keys và reconciliation.
11. **Timeout/fallback phải nằm trong latency budget.** Không chờ vô hạn hoặc trả stale data im lặng.
12. **Chọn consistency theo nghiệp vụ.** Balance, inventory và authorization cần policy chặt hơn analytics.

**Một câu để nhớ:** *Sau khi ghi, chỉ đọc từ standby khi biết standby đã replay tới transaction cần thấy; nếu không chứng minh được điều đó trong latency budget, hãy đọc primary hoặc trả trạng thái chờ theo consistency contract.*


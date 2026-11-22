# Kiểm soát việc nhân bản tác vụ, consumer và thành phần giữ vai trò duy nhất

Checkpoint CRaC lưu trạng thái của một tiến trình JVM tại một thời điểm. Khi cùng một ảnh được restore thành nhiều instance, mỗi instance tiếp tục từ một bản sao của heap và trạng thái static đã được checkpoint. Các bản sao có thể mang theo cùng bộ đếm, cờ trạng thái, lịch chạy, consumer metadata, UUID đã tạo trước checkpoint hoặc thông tin “tôi đang là leader”.

Điều này tạo ra rủi ro vận hành: nhiều tiến trình có thể cùng thực hiện một tác vụ mà trước checkpoint chỉ có một tiến trình thực hiện. Ví dụ, hai replica cùng chạy báo cáo đêm, nhiều consumer cùng xử lý một message, hai instance cùng refresh cache dùng chung, hoặc nhiều process cùng tin rằng mình đang giữ vai trò leader.

CRaC không tự cung cấp cơ chế điều phối singleton trên toàn cluster. Một `static` field, singleton bean, `synchronized` block hay `AtomicBoolean` chỉ điều phối các thread trong một JVM. Khi ảnh được restore nhiều lần, mỗi JVM có bản sao độc lập của những trạng thái đó. Quyền sở hữu tác vụ dùng chung phải được quyết định bởi một hệ thống phối hợp bên ngoài tiến trình, chẳng hạn database, distributed coordination service, broker hoặc scheduler có cơ chế claim/lease.

Mục tiêu của bài học là thiết kế vòng đời để mỗi instance sau restore:

- Nhận diện được incarnation mới của chính nó.
- Tạm dừng và giải phóng quyền sở hữu trước checkpoint.
- Tham gia lại nhóm consumer hoặc cuộc bầu chọn leader sau restore.
- Chỉ chạy tác vụ singleton khi có quyền sở hữu hiện hành.
- Xử lý message/job theo cách an toàn khi retry hoặc thực thi trùng.
- Không mở readiness trước khi trạng thái điều phối đã được xác minh.

## 1. Vì sao restore nhiều lần có thể nhân bản hành vi?

Hãy hình dung ứng dụng có một singleton trong heap:

~~~java
public final class BackgroundCoordinator {
    private static boolean leader = true;
    private static long nextJobNumber = 1200;
}
~~~

Trước checkpoint, chỉ một JVM đang chạy và `leader` là `true`. Nếu ảnh được restore trên ba worker, mỗi worker có bản sao riêng của field này:

| Instance | `leader` trong heap | `nextJobNumber` trong heap |
|---|---:|---:|
| Restore A | true | 1200 |
| Restore B | true | 1200 |
| Restore C | true | 1200 |

Ba process không chia sẻ cùng một `static` field. Mỗi process tin rằng nó đang là leader và có thể cấp cùng số job tiếp theo. Một `synchronized` method cũng chỉ khóa trong một JVM, không khóa được hai JVM khác nhau.

Tương tự, một object scheduler hoặc consumer được khôi phục không tự động biết rằng bản sao khác cũng vừa được restore. Nếu mỗi bản sao tiếp tục phát message hoặc chạy lịch, hành vi sẽ được nhân lên.

### Bản sao heap và quyền sở hữu bên ngoài

| Trạng thái | Khi restore nhiều instance |
|---|---|
| Object Java và static field | Mỗi JVM có bản sao riêng |
| Bộ đếm trong bộ nhớ | Có thể bắt đầu từ cùng một giá trị |
| UUID đã tạo trước checkpoint | Có thể bị dùng lại ở nhiều instance |
| Cờ `isLeader` hoặc `isActive` | Mỗi bản sao có thể giữ cùng giá trị |
| Scheduler và task definition | Mỗi instance có thể tiếp tục đăng ký task |
| Consumer client và metadata cũ | Có thể không còn hợp lệ; phải rejoin theo API |
| Database lock hoặc lease bên ngoài | Có thể đã hết hạn hoặc được cấp cho instance khác |
| File/port/socket bên ngoài | Có thể bị instance khác chiếm hoặc không còn hợp lệ |

Điểm cần nhớ: snapshot có thể nhân bản **ý định và dữ liệu trong bộ nhớ**, nhưng không nhân bản hợp lệ quyền sở hữu trong hệ thống bên ngoài. Quyền sở hữu phải được xác minh lại.

## 2. Phân biệt singleton trong JVM và singleton trong cluster

Từ “singleton” thường được dùng cho hai ý nghĩa khác nhau:

**Singleton trong JVM** bảo đảm một instance object trong một class loader hoặc một phạm vi ứng dụng. Nó hữu ích để chia sẻ cấu hình, cache cục bộ hoặc coordinator giữa các thread của cùng process.

**Singleton trong cluster** bảo đảm chỉ một instance trong nhiều process được phép thực hiện một vai trò tại một thời điểm. Nó cần cơ chế phối hợp bên ngoài như lease, leader election hoặc transaction/claim trong database.

Một singleton bean của framework không tự trở thành singleton trong cluster. Nếu có năm replica, thường có năm singleton bean.

### Phân loại công việc trước khi thiết kế

Không phải mọi background task đều cần một leader duy nhất. Hãy phân loại theo yêu cầu:

| Loại công việc | Mô hình phù hợp | Ví dụ |
|---|---|---|
| Mỗi instance phải làm riêng | Per-instance | Flush metric cục bộ, dọn cache local |
| Chỉ một instance toàn cluster | Cluster singleton | Chạy migration, phát báo cáo toàn hệ thống |
| Chia theo partition/key | Partition ownership | Kafka consumer, shard worker |
| Nhiều instance cùng xử lý nhưng không trùng tác động | Competing consumers + idempotency | Gửi email theo outbox, xử lý đơn hàng |
| Có thể chạy lại nếu bỏ lỡ | Durable scheduled job | Reconciliation, retry queue |
| Vai trò thay đổi theo thời gian | Leader/lease | Điều phối failover, refresh tài nguyên dùng chung |

Phân loại sai sẽ dẫn đến giải pháp quá yếu hoặc quá phức tạp. Ví dụ, không cần bầu leader cho tác vụ flush metric riêng của từng process; ngược lại, không thể dùng `AtomicBoolean` để bảo đảm chỉ một process trong cluster chạy database migration.

### Ownership matrix

Trước khi tích hợp CRaC, lập bảng ghi rõ:

| Thành phần | Phạm vi quyền sở hữu | Nguồn sự thật | Hành vi trước checkpoint | Hành vi sau restore |
|---|---|---|---|---|
| Scheduler singleton | Toàn cluster | Lease/database | Pause, drain, release lease | Reacquire lease rồi mới schedule |
| Consumer group | Partition trong group | Broker coordinator | Stop poll, xử lý/commit hoặc bỏ dở có kiểm soát | Tạo consumer mới và rejoin |
| Job worker | Job ID | Durable job store | Ngừng claim job mới, hoàn tất hoặc nhả claim | Claim lại bằng lease/attempt mới |
| Leader controller | Một role | Coordination service | Nhả quyền hoặc để lease hết hạn có kiểm soát | Bầu/chọn leader mới |
| Cache refresh | Key hoặc cache partition | Lease/key ownership | Dừng refresh và nhả lease | Chỉ refresh key đã claim |
| Outbox dispatcher | Record/partition | Database claim | Dừng lấy record mới | Claim lại record chưa hoàn tất |

Mỗi thành phần cần một owner chịu trách nhiệm lifecycle và một nguồn sự thật để kiểm tra quyền sở hữu.

## 3. Tạo incarnation ID mới sau restore

Một process có thể giữ cùng service name, replica configuration hoặc checkpoint ID, nhưng mỗi lần restore là một incarnation thực thi mới. Incarnation ID giúp phân biệt log, metric, lease và hành động của các bản sao.

Không tạo incarnation ID duy nhất một lần trước checkpoint rồi giữ trong heap. Nếu ảnh được restore nhiều lần, tất cả bản sao có thể nhận cùng giá trị đó.

Nên tạo ID mới sau restore bằng nguồn entropy hoặc bộ cấp ID độc lập với heap đã checkpoint. Với hệ thống cần đảm bảo uniqueness tuyệt đối trong phạm vi nghiệp vụ, dùng ID được cấp từ database/coordination service hoặc kết hợp checkpoint ID với một restore-attempt nonce duy nhất do orchestrator cấp.

Ví dụ về thông tin nhận diện:

| ID | Ý nghĩa | Có thể giữ qua checkpoint? |
|---|---|---|
| Service ID | Định danh logic của ứng dụng | Có |
| Replica/slot ID | Vị trí replica theo orchestrator | Có thể thay đổi theo deployment |
| Checkpoint ID | Ảnh nguồn được restore | Có |
| Incarnation ID | Một lần chạy cụ thể của process | Phải tạo mới sau restore |
| Job ID | Một công việc logic bền vững | Giữ ổn định |
| Job attempt ID | Một lần thử thực thi job | Tạo mới cho mỗi attempt |
| Lease/fencing token | Quyền sở hữu có thứ tự | Cấp lại từ authority bên ngoài |

### Ví dụ tạo incarnation ID

~~~java
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

public final class ProcessIdentity {

    private final AtomicReference<UUID> incarnation =
            new AtomicReference<>();

    public UUID startFresh() {
        UUID id = UUID.randomUUID();
        incarnation.set(id);
        return id;
    }

    public UUID afterRestore() {
        UUID id = UUID.randomUUID();
        incarnation.set(id);
        return id;
    }

    public UUID current() {
        UUID id = incarnation.get();
        if (id == null) {
            throw new IllegalStateException("Process identity is not initialized");
        }
        return id;
    }
}
~~~

Ví dụ dùng `UUID.randomUUID()` sau restore để minh họa việc tạo giá trị mới thay vì giữ UUID trong snapshot. Nếu threat model hoặc nền tảng có yêu cầu đặc biệt về entropy, dùng identity/nonce do runtime hoặc hệ thống điều phối cấp. Không dùng PID làm incarnation ID duy nhất: PID có thể được tái sử dụng và có thể khác trong PID namespace.

Gắn incarnation ID vào log, trace, metric label có kiểm soát, lease owner và job attempt. Không dùng nó thay cho ID nghiệp vụ ổn định như order ID hoặc message ID.

## 4. Tạm dừng scheduler và job worker trước checkpoint

Scheduler là một trong những nơi dễ phát sinh tác vụ trùng nhất. Một scheduler chạy trong JVM có thể lưu task definition, trigger state, executor và thời điểm chạy kế tiếp trong heap. Khi restore nhiều bản sao, mỗi bản sao có thể tiếp tục đăng ký cùng một lịch.

### Vì sao task có thể chạy trùng?

Các nguyên nhân thường gặp:

- Mỗi instance khởi động scheduler và đăng ký cùng cron expression.
- Một task đã được schedule trước checkpoint; sau restore, task được đăng ký thêm lần nữa.
- Một job đang chạy bị checkpoint giữa chừng, rồi nhiều bản sao tiếp tục cùng job.
- Lịch fixed-rate cố chạy bù các lần đã trễ trong thời gian process tạm dừng.
- Lease của scheduler cũ đã hết hạn nhưng cờ `isLeader` trong heap vẫn là true.
- Hai instance cùng claim một job do thao tác claim không nguyên tử.

Không nên coi trạng thái scheduler trong heap là nguồn sự thật về quyền chạy job. Lịch có thể được lưu trong database hoặc scheduler service; mỗi lần thực thi cần có claim/lease độc lập.

### Trình tự trước checkpoint

Với scheduler có tác động dùng chung, quy trình nên:

1. Đóng admission cho job mới.
2. Dừng trigger phát sinh thêm lần chạy.
3. Chờ job đang chạy hoàn tất trong deadline đã chọn, hoặc dừng/cancel theo chính sách.
4. Ghi trạng thái tiến độ bền vững nếu job có thể tiếp tục.
5. Commit kết quả hoặc nhả claim/lease.
6. Đóng executor/client cần tái tạo.
7. Chỉ cho phép checkpoint khi trạng thái đã quiescent.

Không checkpoint khi một job đang giữ transaction, lock hoặc side effect chưa có trạng thái bền vững nếu ứng dụng chưa có cơ chế recovery rõ ràng.

### Trình tự sau restore

- Tạo incarnation ID mới.
- Đăng ký instance với scheduler/coordination service.
- Chỉ reacquire quyền sở hữu nếu role yêu cầu singleton.
- Nạp lịch từ nguồn bền vững hoặc đăng ký lịch bằng khóa duy nhất.
- Không chạy bù hàng loạt một cách mù quáng.
- Chỉ mở job trigger sau khi claim/lease và dependency đã sẵn sàng.

### Chính sách cho lịch bị bỏ lỡ

Khi một process tạm dừng, thời điểm chạy của cron hoặc timer có thể trôi qua. Cần quyết định rõ:

| Chính sách | Hành vi | Phù hợp khi |
|---|---|---|
| Skip | Bỏ lần chạy đã lỡ, chờ lịch kế tiếp | Công việc chỉ cần chạy định kỳ và dữ liệu mới sẽ được xử lý sau |
| Coalesce | Gộp nhiều lần lỡ thành một lần | Tác vụ refresh/reconciliation không cần chạy từng tick |
| Backfill | Chạy lại từng khoảng bị bỏ lỡ | Mỗi kỳ là một đơn vị nghiệp vụ cần được xử lý |
| Resume | Tiếp tục job từ checkpoint nghiệp vụ | Job có tiến độ bền vững và hỗ trợ resume |

Chính sách này phải nằm trong scheduler/job store hoặc logic nghiệp vụ, không phụ thuộc vào timer object đã được khôi phục.

### Fixed-rate và fixed-delay

`scheduleAtFixedRate` cố duy trì nhịp theo thời điểm dự kiến; nếu tác vụ chậm, các lần thực thi có thể đến gần nhau hoặc được xử lý bù tùy scheduler. `scheduleWithFixedDelay` tính khoảng chờ sau khi lần trước hoàn tất. Sau restore, cả hai đều cần kiểm tra cách thư viện xử lý clock, missed execution và task đang chạy.

Với tác vụ nghiệp vụ quan trọng, ưu tiên durable schedule với job ID và trạng thái thực thi trong kho bền vững. Timer trong JVM chỉ nên là cơ chế đánh thức worker, không phải nơi duy nhất lưu lịch.

## 5. Claim job bằng kho trạng thái bền vững

Một worker nên claim job bằng thao tác nguyên tử. Ví dụ database có bảng job với trạng thái `READY`, `RUNNING`, `DONE`, lease expiration và attempt number.

Một claim cần kiểm tra trong cùng transaction:

- Job đang ở trạng thái cho phép nhận.
- Lease cũ đã hết hạn hoặc chưa có owner.
- Attempt/generation được tăng nguyên tử.
- Owner được ghi bằng incarnation ID.
- Thời hạn lease được đặt.

Pseudo SQL minh họa:

~~~sql
UPDATE scheduled_job
SET owner_id = :incarnation_id,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '30 seconds',
    attempt = attempt + 1,
    status = 'RUNNING'
WHERE job_id = :job_id
  AND status IN ('READY', 'RUNNING')
  AND (lease_until IS NULL OR lease_until < CURRENT_TIMESTAMP)
RETURNING job_id, attempt, lease_until;
~~~

Cú pháp interval và `RETURNING` tùy database. Điều quan trọng là claim phải nguyên tử, có điều kiện lease hết hạn và trả về đúng attempt đã được cấp. Không thực hiện `SELECT` rồi `UPDATE` tách rời mà không khóa hoặc kiểm soát concurrency; hai worker có thể cùng đọc thấy job sẵn sàng.

Khi xử lý xong, worker chỉ được đánh dấu hoàn tất nếu vẫn sở hữu attempt/generation hiện hành. Nếu lease đã hết hạn và job được cấp cho worker khác, worker cũ không được phép ghi đè kết quả mới.

### Lease và heartbeat

Lease có thời hạn giúp hệ thống thu hồi quyền nếu process chết hoặc mất kết nối. Worker phải gia hạn lease trước khi hết hạn. Nếu không gia hạn được, worker phải ngừng bắt đầu side effect mới và xử lý trạng thái đang chạy theo chính sách.

Không dùng đồng hồ local của JVM làm nguồn duy nhất cho lease expiration nếu database/coordination service có clock riêng. Dùng thời gian và thao tác nguyên tử từ authority sở hữu lease.

### Fencing token chống owner cũ

Lease đơn thuần chưa đủ nếu một worker cũ bị pause lâu, lease hết hạn, worker mới nhận lease, rồi worker cũ tiếp tục chạy khi được resume. Cả hai có thể cùng nghĩ mình có quyền.

Fencing token là số thế hệ tăng đơn điệu do authority bên ngoài cấp mỗi lần cấp quyền. Mọi thao tác ghi vào tài nguyên dùng chung phải mang token; tài nguyên đích từ chối token thấp hơn token đã chấp nhận gần nhất.

Ví dụ:

| Owner | Lease generation | Kết quả |
|---|---:|---|
| Instance A | 41 | Được cấp quyền ban đầu |
| Instance A bị pause | 41 | Lease hết hạn |
| Instance B | 42 | Được cấp quyền mới |
| Instance A tiếp tục | 41 | Tác vụ ghi bị từ chối vì token cũ |

Fencing chỉ hiệu quả nếu tài nguyên nhận thao tác có kiểm tra token. Một counter trong JVM không thể thay thế fencing token do authority bên ngoài cấp.

## 6. Consumer phải tham gia lại group sau restore

Message consumer thường có trạng thái network, heartbeat, assignment, offset và buffer xử lý. Những trạng thái này có thể không còn hợp lệ sau thời gian checkpoint. Không nên giả định consumer object trong heap có thể tiếp tục poll an toàn.

Với consumer group như Kafka, broker coordinator quản lý membership và partition assignment. Sau restore, consumer cần được tạo lại hoặc phục hồi theo lifecycle được client hỗ trợ, sau đó join group và nhận assignment mới. Các member khác có thể đã tiếp tục xử lý trong lúc instance này tạm dừng.

### Trước checkpoint

Một quy trình phổ biến:

1. Ngừng nhận record mới bằng cách pause hoặc dừng poll theo API client.
2. Chờ xử lý các record đang in-flight trong deadline.
3. Commit offset sau khi side effect đã được hoàn tất theo semantics của ứng dụng.
4. Nếu không thể hoàn tất, để record được xử lý lại và bảo đảm handler idempotent.
5. Đóng consumer client theo API của thư viện.
6. Giải phóng thread/event loop và connection mà client sở hữu.

Không commit offset chỉ vì muốn checkpoint nhanh. Commit trước khi side effect bền vững có thể làm mất xử lý nếu process bị dừng. Ngược lại, side effect đã thành công nhưng offset chưa commit có thể dẫn đến xử lý lại; handler cần idempotency hoặc transaction phù hợp.

### Sau restore

- Tạo consumer client mới theo API hỗ trợ.
- Dùng group ID và client configuration hiện hành.
- Xác thực lại workload identity/credential.
- Join group và chờ partition assignment.
- Kiểm tra offset và trạng thái in-flight theo chính sách.
- Chỉ mở xử lý khi consumer đã có assignment và dependency sẵn sàng.

Không tự khôi phục partition assignment từ một field đã checkpoint. Broker coordinator là nguồn sự thật cho assignment hiện tại.

### Rebalance và thời gian tạm dừng

Trong thời gian process tạm dừng, heartbeat có thể ngừng và broker có thể loại member khỏi group. Consumer khác sẽ nhận partition. Khi restore, instance cũ quay lại như một member mới hoặc member cần rejoin tùy client/protocol.

Điều này có thể gây rebalance và tăng latency tạm thời. Nếu nhiều instance restore đồng thời, chúng có thể tạo một đợt join/rebalance lớn. Cần giới hạn tốc độ rollout, dùng backoff/jitter và theo dõi rebalance count, assignment duration và consumer lag.

### Offset và side effect

Không có một thứ tự commit duy nhất phù hợp mọi ứng dụng. Ví dụ:

| Thứ tự | Rủi ro |
|---|---|
| Commit offset trước side effect | Process chết sau commit có thể khiến record bị bỏ qua |
| Side effect trước commit offset | Process chết trước commit có thể khiến record được xử lý lại |
| Commit cùng transaction hỗ trợ bởi broker/database | Có thể cung cấp semantics mạnh hơn trong phạm vi được hỗ trợ |

Ngay cả khi dùng transaction hoặc exactly-once feature của broker, side effect tới hệ thống ngoài transaction đó vẫn cần idempotency hoặc cơ chế phối hợp riêng. Không quảng bá “exactly once” chỉ dựa trên việc bật một flag consumer.

## 7. Làm cho handler idempotent

Khi restore, rebalance hoặc retry, cùng một message/job có thể được giao lại. Handler idempotent bảo đảm thực hiện nhiều lần không tạo ra nhiều tác động nghiệp vụ ngoài ý muốn.

Một cách phổ biến là dùng message ID hoặc business key làm idempotency key và lưu kết quả xử lý trong cùng transaction với cập nhật nghiệp vụ.

Ví dụ pseudo-code:

~~~java
public void handle(OrderCreated event) {
    transactionTemplate.executeWithoutResult(tx -> {
        boolean firstDelivery =
                processedMessageRepository.insertIfAbsent(event.messageId());

        if (!firstDelivery) {
            return;
        }

        orderService.applyCreatedEvent(event);
    });
}
~~~

`insertIfAbsent` cần được triển khai bằng unique constraint hoặc thao tác nguyên tử trong cùng database transaction. Nếu chỉ kiểm tra `exists` rồi mới insert, hai consumer có thể cùng vượt qua kiểm tra.

### Idempotency key phải ổn định

Không tạo message ID mới mỗi lần handler nhận lại record. ID cần được tạo ở nguồn phát message và giữ ổn định qua retry. Attempt ID có thể thay đổi, nhưng business/message ID phải giữ nguyên.

### Outbox pattern

Nếu consumer cần cập nhật database và phát message tiếp theo, outbox giúp lưu thay đổi nghiệp vụ và event cần phát trong cùng transaction database. Dispatcher có thể claim từng outbox record; nếu gửi trùng, consumer nhận cần idempotent.

CRaC không thay thế transaction, outbox hoặc deduplication. Nó chỉ thay đổi cách process tiếp tục sau checkpoint.

## 8. Điều phối thành phần giữ vai trò duy nhất

Các thành phần thường được thiết kế như “chỉ một instance”:

- Leader controller hoặc cluster coordinator.
- Scheduler chạy migration hoặc báo cáo toàn hệ thống.
- Cache warmer/refresh job dùng chung.
- Outbox dispatcher hoặc cleanup worker.
- Service discovery publisher giữ một lease.
- Worker quản lý tài nguyên bên ngoài hoặc một thiết bị độc quyền.
- Component quản lý một port, file lock hoặc socket path dùng chung.

Với mỗi thành phần, cần trả lời:

1. Phạm vi duy nhất là một JVM, một host, một namespace hay toàn cluster?
2. Ai cấp quyền sở hữu?
3. Quyền có lease/expiration không?
4. Owner phải gia hạn bằng cách nào?
5. Tài nguyên đích có thể từ chối owner cũ bằng fencing token không?
6. Điều gì xảy ra khi owner chết, pause hoặc mất network?
7. Sau restore, component có phải bầu lại hoặc đăng ký lại không?

### Leader election

Leader election phải dựa trên coordination service hoặc database có semantics nhất quán phù hợp. Một biến `leader=true` trong heap chỉ là snapshot của quyết định cũ.

Sau restore:

- Xóa trạng thái leader cũ khỏi quyết định runtime.
- Tham gia lại election hoặc yêu cầu lease mới.
- Nhận fencing token/generation mới.
- Chỉ thực hiện hành động leader khi lease còn hiệu lực.
- Ngừng hành động ngay khi lease mất hoặc không gia hạn được.

### Distributed lock

Lock có TTL giúp phục hồi khi owner biến mất, nhưng process bị pause có thể tiếp tục sau khi lock hết hạn. Vì vậy, thao tác ghi phải có fencing token hoặc điều kiện version ở tài nguyên đích.

Không giữ trong heap một object lock và giả định lock bên ngoài vẫn thuộc về instance sau restore. Phải xác minh owner và thời hạn với lock service.

### File lock và port

File lock và port binding là tài nguyên của hệ điều hành. Khi restore nhiều bản sao trên cùng host/namespace, nhiều process có thể tranh cùng một path hoặc port. Khi restore trên host khác, tài nguyên tương ứng có thể tồn tại hoặc không.

Trước checkpoint, đóng và nhả tài nguyên theo API. Sau restore, bind/acquire lại và xử lý lỗi conflict. Không dùng boolean đã checkpoint để kết luận port/file lock vẫn thuộc process.

## 9. Điều phối lifecycle bằng một coordinator

Khi nhiều thành phần phụ thuộc nhau, nên có một coordinator rõ ràng điều khiển thứ tự. Ví dụ, scheduler không được chạy trước khi lease được cấp; consumer không được xử lý trước khi credential và group assignment sẵn sàng; readiness không được mở trước khi các thành phần bắt buộc đã hoạt động.

Một state machine đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE
    ACTIVE --> QUIESCING: beforeCheckpoint
    QUIESCING --> CHECKPOINT_READY: tasks drained, leases released
    CHECKPOINT_READY --> RESTORING: image restored
    RESTORING --> REJOINING: new incarnation
    REJOINING --> ACTIVE: consumers and roles verified
    REJOINING --> NOT_READY: recovery failed
    NOT_READY --> REJOINING: bounded retry
~~~

Các trạng thái trong sơ đồ là trạng thái ứng dụng tự quản lý, không phải enum bắt buộc của CRaC. Dùng state machine để ngăn method khởi tạo bị gọi trùng và để log được tiến trình rõ ràng.

### Một Resource điều phối các thành phần

Ví dụ sau minh họa một coordinator duy nhất. Các interface đại diện cho adapter của scheduler, consumer group, lease service và readiness gate.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.util.UUID;

public final class RuntimeCoordinationResource implements Resource {

    public interface Identity {
        UUID createNewIncarnation() throws Exception;
    }

    public interface Scheduler {
        void pauseTriggersAndDrain() throws Exception;
        void startIfLeader(long fencingToken) throws Exception;
    }

    public interface Consumers {
        void stopPollingDrainAndClose() throws Exception;
        void createJoinAndVerify() throws Exception;
    }

    public interface Leadership {
        void release() throws Exception;
        LeadershipGrant acquireIfAvailable(UUID incarnation) throws Exception;
    }

    public interface Readiness {
        void close();
        void open();
    }

    public record LeadershipGrant(boolean leader, long fencingToken) {
    }

    private final Identity identity;
    private final Scheduler scheduler;
    private final Consumers consumers;
    private final Leadership leadership;
    private final Readiness readiness;

    private UUID incarnation;
    private boolean active;

    public RuntimeCoordinationResource(
            Identity identity,
            Scheduler scheduler,
            Consumers consumers,
            Leadership leadership,
            Readiness readiness) {
        this.identity = identity;
        this.scheduler = scheduler;
        this.consumers = consumers;
        this.leadership = leadership;
        this.readiness = readiness;
        Core.getGlobalContext().register(this);
    }

    public synchronized void initializeForFreshStart() throws Exception {
        readiness.close();
        activateNewIncarnation();
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        readiness.close();
        active = false;
        scheduler.pauseTriggersAndDrain();
        consumers.stopPollingDrainAndClose();
        leadership.release();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        readiness.close();
        active = false;
        activateNewIncarnation();
    }

    private void activateNewIncarnation() throws Exception {
        incarnation = identity.createNewIncarnation();

        // Rejoin the consumer group; the broker assigns current partitions.
        consumers.createJoinAndVerify();

        // A cluster-wide role is granted by an external authority.
        LeadershipGrant grant = leadership.acquireIfAvailable(incarnation);
        if (grant.leader()) {
            scheduler.startIfLeader(grant.fencingToken());
        }

        active = true;
        readiness.open();
    }
}
~~~

Đây là cấu trúc minh họa, không phải adapter dùng trực tiếp cho mọi framework. Trong ứng dụng thật:

- `pauseTriggersAndDrain()` phải chặn task mới và chờ task đang chạy theo deadline.
- `stopPollingDrainAndClose()` phải xử lý in-flight record và offset theo semantics của consumer.
- `release()` phải giải phóng lease/lock bên ngoài và xử lý fencing token.
- `createJoinAndVerify()` phải chờ consumer nhận assignment cần thiết, không chỉ tạo object.
- `acquireIfAvailable()` phải dùng thao tác nguyên tử của coordination service.
- `startIfLeader()` phải truyền fencing token vào mọi thao tác ghi liên quan.
- Nếu một bước thất bại, readiness vẫn đóng và lỗi phải được báo ra để runtime/orchestrator xử lý.

Trong ví dụ, consumer group được tham gia bởi mọi instance, còn scheduler chỉ chạy khi instance nhận được leadership grant. Nếu consumer cũng là cluster singleton, đặt điều kiện acquire role trước khi join hoặc trước khi bắt đầu poll.

### Vì sao gom vào một coordinator?

Nếu nhiều Resource độc lập cùng đóng/mở các thành phần có quan hệ phụ thuộc, thứ tự callback có thể trở thành một giả định ngầm. Dùng một coordinator làm rõ thứ tự: đóng readiness, drain công việc, đóng consumer, nhả lease; sau restore tạo incarnation, join consumer, reacquire role, bật scheduler và cuối cùng mở readiness.

Nếu vẫn dùng nhiều Resource, hãy dùng cơ chế ordering được tài liệu runtime/framework hỗ trợ và kiểm thử thứ tự thực tế. Không dựa vào thứ tự đăng ký tình cờ nếu nó không được bảo đảm.

### Xử lý lỗi giữa chừng

Nếu consumer đã đóng nhưng reacquire leadership thất bại, không mở readiness cho chức năng cần leader. Nếu secret refresh thất bại trước khi consumer tạo lại, không để consumer bắt đầu xử lý. Mỗi bước cần timeout, cleanup và trạng thái lỗi xác định.

Không bắt exception rồi vẫn mở readiness. Nếu hệ thống hỗ trợ phục hồi nền, readiness vẫn phải đóng cho đến khi thành phần bắt buộc hoàn tất. Retry phải có backoff, jitter và deadline; tránh tạo vòng lặp reconnect gây quá tải dependency.

## 10. Tránh đăng ký scheduler và listener trùng

Một nguyên nhân khác là khởi tạo component nhiều lần. Khi object được khôi phục, framework không nhất thiết gọi lại constructor hoặc startup hook như một JVM mới. Nhưng callback restore có thể gọi logic đăng ký task lần nữa nếu code không phân biệt trạng thái.

### Những lỗi dễ gặp

- Gọi `schedule()` trong cả constructor và `afterRestore`.
- Khởi tạo executor mới mà không dừng executor cũ.
- Đăng ký listener/event handler lần nữa sau restore.
- Mở hai polling loop trên cùng consumer wrapper.
- Thêm shutdown hook hoặc timer lặp lại.
- Khởi tạo cùng một job definition vào scheduler store nhiều lần.

### Dùng registration key ổn định

Với scheduler bền vững, dùng một khóa logic ổn định cho job definition, ví dụ `(service, jobName, scheduleVersion)`. Đăng ký bằng thao tác upsert/unique constraint thay vì insert mỗi lần process khởi động.

Không dùng incarnation ID làm khóa job definition nếu mục tiêu là chỉ có một lịch toàn cluster. Incarnation ID xác định process; job key xác định lịch logic. Tách hai khái niệm để mỗi restore không tạo thêm một lịch mới.

### Guard trong JVM chỉ là lớp bảo vệ cục bộ

Có thể dùng `AtomicBoolean` hoặc state machine để ngăn một JVM đăng ký cùng listener hai lần:

~~~java
if (started.compareAndSet(false, true)) {
    scheduler.start();
}
~~~

Đây là bảo vệ hữu ích cho thread cạnh tranh trong cùng process. Nó không bảo đảm một JVM khác không thực hiện cùng công việc. Quyền sở hữu cluster vẫn phải được xác nhận bên ngoài.

## 11. Xử lý job đang chạy tại thời điểm checkpoint

Checkpoint giữa một side effect có thể tạo ra trạng thái không rõ ràng. Ví dụ, process đã gửi lệnh thanh toán đến hệ thống ngoài nhưng chưa ghi nhận kết quả; sau restore, job có thể gửi lại lệnh.

### Xác định điểm commit nghiệp vụ

Với mỗi job, xác định:

- Job bắt đầu ở đâu và trạng thái nào được lưu bền vững?
- Side effect nào có thể xảy ra ngoài transaction?
- Có idempotency key không?
- Kết quả được commit trước hay sau acknowledgment?
- Nếu process bị dừng giữa hai bước, job sẽ retry, resume hay cần reconciliation?

Không dùng việc heap được checkpoint làm bằng chứng tiến độ nghiệp vụ đã được commit. Heap chỉ lưu trạng thái process; transaction/database/broker mới là nguồn sự thật bền vững.

### Chọn cách xử lý

| Trạng thái lúc chuẩn bị checkpoint | Cách xử lý |
|---|---|
| Job chưa bắt đầu | Không claim job mới sau khi admission đóng |
| Job đang chạy, có thể hoàn tất nhanh | Drain trong deadline rồi commit kết quả |
| Job đang chạy lâu, có checkpoint nghiệp vụ | Lưu progress bền vững rồi dừng an toàn |
| Job đã gửi side effect nhưng chưa ghi kết quả | Dùng idempotency key hoặc reconciliation |
| Không thể xác định side effect đã xảy ra chưa | Đưa vào trạng thái cần đối soát, không tự chạy lại mù quáng |

### Không giữ lock nghiệp vụ qua checkpoint

Nếu job giữ database transaction hoặc distributed lock trong lúc checkpoint, thời gian tạm dừng có thể làm transaction timeout hoặc lease hết hạn. Trước checkpoint, hoàn tất/rollback transaction và nhả lock theo giao thức. Sau restore, bắt đầu transaction mới và claim quyền mới.

## 12. Nhiều instance restore cùng một ảnh

Kịch bản quan trọng nhất là cùng một checkpoint image được restore đồng thời trên nhiều host hoặc pod.

Ví dụ:

~~~text
                 checkpoint image
                  /      |      \
                 /       |       \
             restore A restore B restore C
                |         |         |
             JVM A     JVM B     JVM C
                |         |         |
                +---- external coordination ----+
                          |
                  lease / group / job store
~~~

Các instance có thể bắt đầu với cùng:

- Static counter và cache state.
- Scheduler registration state.
- Consumer group ID và client metadata.
- Leader flag và lease metadata đã lưu trong heap.
- UUID hoặc random generator state được khởi tạo trước checkpoint.
- Queue nội bộ và danh sách task đang chờ.

Vì vậy, kiểm thử một lần restore trên một máy chưa đủ. Cần restore cùng ảnh thành ít nhất hai instance và xác minh hệ thống bên ngoài chỉ cấp quyền theo chính sách.

### Rollout có kiểm soát

Khi nhiều replica restore:

- Giới hạn số instance được restore đồng thời.
- Tránh để tất cả consumer join group cùng lúc nếu broker không chịu được rebalance lớn.
- Dùng backoff/jitter khi lấy lease hoặc secret.
- Theo dõi số leader, consumer assignment và job claim.
- Giữ readiness đóng cho đến khi instance hoàn tất rejoin.
- Đảm bảo scale down cũng nhả lease và dừng consumer an toàn.

Không giả định tất cả instance phải trở thành leader. Thông thường, chỉ một instance nhận lease cho một role; các instance còn lại ở trạng thái follower hoặc standby.

## 13. Theo dõi quyền sở hữu và tác vụ sau restore

Nếu chỉ theo dõi số process đang chạy, rất khó phát hiện hai instance cùng thực hiện một vai trò. Cần metric và log thể hiện quyền sở hữu thực tế.

### Metric nên có

| Metric | Ý nghĩa |
|---|---|
| `process_incarnation_info` | Nhận diện incarnation đang chạy |
| `cluster_role_leader` | Instance hiện tại có đang giữ role leader không |
| `leadership_lease_valid` | Lease còn hiệu lực và đã được xác minh |
| `leadership_fencing_token` | Generation hiện hành được authority cấp |
| `scheduler_active` | Scheduler đang nhận trigger hay đang pause |
| `scheduler_inflight_jobs` | Số job đang chạy |
| `job_claim_conflicts_total` | Số lần claim thất bại do worker khác đã nhận |
| `job_duplicate_suppressed_total` | Số lần idempotency chặn xử lý trùng |
| `consumer_group_rebalance_total` | Số lần consumer group rebalance |
| `consumer_assigned_partitions` | Số partition được giao cho instance |
| `consumer_lag` | Độ trễ xử lý message |
| `consumer_inflight_records` | Số record đang xử lý |
| `restore_rejoin_duration_seconds` | Thời gian tham gia lại group/role sau restore |
| `readiness_state` | Instance đã sẵn sàng nhận traffic hay chưa |

Tên metric là gợi ý. Tránh đưa incarnation ID, job ID hoặc message ID có cardinality rất cao vào label của metric. Dùng log/trace cho ID chi tiết và metric cho trạng thái tổng hợp.

### Log có cấu trúc

Mỗi sự kiện điều phối nên ghi:

- `checkpoint_id`
- `restore_attempt_id`
- `incarnation_id`
- `service_id`
- `role_name`
- `lease_generation` hoặc `fencing_token`
- `consumer_group_id`
- `assigned_partitions`
- `job_id` và `attempt_id` khi cần
- `event` và `result`

Không ghi token, password hoặc secret trong các field này. Ghi ID của credential version nếu cần điều tra rotation.

### Cảnh báo quan trọng

- Có nhiều hơn một leader cho cùng role.
- Hai incarnation cùng giữ lease generation không hợp lệ.
- Lease hết hạn nhưng worker vẫn tiếp tục phát side effect.
- Scheduler singleton chạy khi chưa có leadership grant.
- Consumer xử lý record trước khi có partition assignment.
- Consumer lag hoặc rebalance tăng đột biến sau restore.
- Job attempt mới bắt đầu khi attempt cũ chưa được xác định kết quả.
- Readiness mở trong khi coordinator còn ở trạng thái `REJOINING`.

Nếu hệ thống có nhiều role singleton, đếm leader theo từng `role_name`, không chỉ tổng số leader toàn cluster.

## 14. Kiểm thử việc restore nhiều bản sao

Kiểm thử phải tạo tình huống mà một checkpoint image được restore thành nhiều process độc lập. Chạy một instance duy nhất không thể phát hiện các static flag, counter hoặc scheduler bị nhân bản.

### Kịch bản kiểm thử cơ bản

1. Khởi động ứng dụng và để scheduler, consumer, leader role hoạt động.
2. Ghi lại incarnation ID, leader/lease generation, consumer assignment và job state.
3. Đóng admission, drain job, pause scheduler, dừng consumer và nhả lease.
4. Tạo checkpoint.
5. Restore cùng ảnh thành ít nhất hai instance độc lập.
6. Xác nhận mỗi instance tạo incarnation ID khác nhau.
7. Xác nhận broker coordinator phân phối partition theo group hiện tại.
8. Xác nhận chỉ một instance có lease cho role singleton.
9. Xác nhận scheduler chỉ chạy trên owner được cấp quyền.
10. Phát message/job có ID cố định và xác minh side effect chỉ xảy ra một lần về mặt nghiệp vụ.
11. Dừng owner hiện tại và xác minh lease/failover hoạt động.
12. Cho instance cũ tiếp tục sau khi lease đã được cấp cho owner mới; xác minh fencing token chặn thao tác stale.

### Ma trận tình huống

| Tình huống | Điều cần xác minh |
|---|---|
| Restore một instance | Consumer rejoin, lease được cấp và scheduler hoạt động đúng |
| Restore hai instance cùng ảnh | Incarnation khác nhau; singleton chỉ có một owner |
| Restore nhiều instance đồng thời | Coordination service và broker chịu được join/claim burst |
| Lease hết hạn khi process bị pause | Instance cũ không thể ghi bằng fencing token cũ |
| Consumer bị loại khỏi group | Restore join lại và nhận assignment hiện hành |
| Message xử lý xong nhưng offset chưa commit | Redelivery không tạo side effect trùng |
| Offset commit trước side effect | Test chứng minh không bỏ mất nghiệp vụ |
| Job bị dừng giữa side effect | Retry/reconciliation dùng idempotency key |
| Scheduler bị đăng ký hai lần | Registration key/unique constraint chặn lịch trùng |
| Restore sau thời điểm cron đã qua | Skip/coalesce/backfill theo policy đã định |
| Checkpoint khi job đang chạy | Admission/drain ngăn snapshot trạng thái nghiệp vụ mơ hồ |
| Leadership service không sẵn sàng | Readiness đóng; không tự giả định mình là leader |
| Scale down instance | Consumer đóng, lease nhả và job claim được xử lý |
| Restore trên host khác | Không phụ thuộc PID, hostname hoặc local lock cũ |

### Kiểm tra side effect, không chỉ kiểm tra log

Một log “job started” trên một instance và “job started” trên instance khác đã cho thấy có hai lần bắt đầu, nhưng chưa chứng minh có hai side effect. Ngược lại, một log duy nhất cũng không chứng minh nghiệp vụ chỉ xảy ra một lần.

Kiểm tra kết quả ở hệ thống đích:

- Một record nghiệp vụ duy nhất cho một idempotency key.
- Một job state chuyển sang DONE đúng một lần.
- Một lease owner hợp lệ tại một thời điểm.
- Fencing token tăng theo thứ tự.
- Partition assignment không bị hai consumer cùng xử lý theo cách trái với protocol.
- Outbox/event được phát theo semantics đã thiết kế.

## 15. Các anti-pattern khi dùng CRaC với background work

| Anti-pattern | Vì sao nguy hiểm | Hướng xử lý |
|---|---|---|
| Giữ `isLeader=true` trong static field | Mọi bản restore có thể cùng tin là leader | Re-elect hoặc reacquire lease |
| Dùng `synchronized` làm distributed lock | Lock chỉ có hiệu lực trong một JVM | Coordination service/database |
| Dùng counter trong heap để cấp job ID | Các bản sao có thể cấp cùng giá trị | Sequence/ID generator bên ngoài |
| Giữ consumer object và tiếp tục poll | Network session và assignment có thể stale | Đóng và tạo/join consumer mới |
| Commit offset trước side effect | Có thể mất xử lý khi process dừng | Transaction/idempotency phù hợp |
| Side effect rồi commit offset mà không idempotency | Redelivery có thể tạo tác động trùng | Deduplication/outbox/transaction |
| Giữ lease qua checkpoint | Lease có thể hết hạn trong thời gian pause | Nhả và reacquire; dùng fencing |
| Chỉ dùng TTL lock | Owner cũ có thể tiếp tục sau pause | Fencing token được resource đích kiểm tra |
| Đăng ký cron trong mọi callback | Mỗi lần restore có thể tạo thêm lịch | Durable schedule và registration key |
| Chạy bù mọi tick đã lỡ | Tạo burst job sau restore | Skip/coalesce/backfill có policy |
| Mở readiness ngay khi JVM tiếp tục | Consumer/lease/client có thể chưa sẵn sàng | Mở sau khi coordinator xác minh |
| Dùng PID làm ID instance bền vững | PID có thể tái sử dụng và khác namespace | Incarnation ID mới |

## 16. Checklist vận hành

### Trước checkpoint

- [ ] Đã phân loại từng task là per-instance, cluster singleton, partitioned hay competing consumer.
- [ ] Đã xác định nguồn sự thật về ownership cho từng role.
- [ ] Đóng admission và ngừng claim công việc mới.
- [ ] Pause scheduler trigger và drain task đang chạy.
- [ ] Xử lý in-flight message/job theo transaction và idempotency policy.
- [ ] Commit hoặc nhả claim/lease theo đúng semantics.
- [ ] Dừng consumer và giải phóng client/thread cần tái tạo.
- [ ] Nhả leadership/lease và ghi nhận fencing generation.
- [ ] Không checkpoint với lock/transaction nghiệp vụ chưa có recovery path.

### Sau restore

- [ ] Tạo incarnation ID mới.
- [ ] Làm mới workload identity/credential nếu client cần.
- [ ] Tham gia lại consumer group và chờ assignment hiện hành.
- [ ] Reacquire lease/leadership từ authority bên ngoài.
- [ ] Nhận fencing token mới và truyền token vào thao tác ghi.
- [ ] Khởi động scheduler chỉ khi role được cấp.
- [ ] Đăng ký lịch bằng khóa logic ổn định để tránh duplicate.
- [ ] Xác định cách xử lý lịch bị lỡ.
- [ ] Mở readiness sau khi mọi thành phần bắt buộc đã được xác minh.

### Kiểm thử và quan sát

- [ ] Đã restore cùng một image thành nhiều instance.
- [ ] Incarnation ID của các bản sao khác nhau.
- [ ] Chỉ một owner giữ cluster singleton role.
- [ ] Consumer group rejoin và rebalance theo dự kiến.
- [ ] Handler/job có idempotency cho redelivery/retry.
- [ ] Fencing chặn owner cũ sau khi lease hết hạn.
- [ ] Metric/log ghi rõ role, incarnation, lease generation và job attempt.
- [ ] Có cảnh báo cho duplicate leader, duplicate job và readiness mở sớm.
- [ ] Đã thử scale down, restart, network partition và restore đồng thời.

## 17. Nguyên tắc thiết kế cần giữ

CRaC giúp tạo nhiều instance từ một trạng thái JVM đã chuẩn bị, nhưng nó không biến trạng thái trong heap thành quyền sở hữu phân tán. Mọi thứ mang tính cục bộ như static field, counter, scheduler object hoặc consumer metadata có thể được nhân bản cùng ảnh. Những thành phần có vai trò duy nhất phải lấy quyền từ một authority bên ngoài sau mỗi restore.

Hãy dùng incarnation ID để nhận diện từng process, lease/leader election để cấp quyền, fencing token để ngăn owner cũ, consumer group để phân phối partition, idempotency để bảo vệ side effect và durable job state để xử lý retry/resume. Trước checkpoint, đóng admission, drain công việc và nhả quyền. Sau restore, tạo identity mới, rejoin, reacquire và chỉ mở readiness khi trạng thái hiện hành đã được xác minh.

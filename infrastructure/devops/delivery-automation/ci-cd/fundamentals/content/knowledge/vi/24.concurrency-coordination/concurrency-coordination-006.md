# Thiết kế khóa và thời gian chờ với khả năng giải phóng khi lỗi

Một pipeline có thể khởi chạy hai lần triển khai cùng lúc, hai migration cùng sửa một schema hoặc nhiều worker cùng xử lý một partition dữ liệu. Nếu các tiến trình không phối hợp, chúng có thể ghi đè trạng thái, tạo tài nguyên trùng, giữ database lock quá lâu hoặc làm release mới bị thao tác cũ ghi đè.

Khóa (lock) giúp giới hạn quyền thực hiện một thao tác trên tài nguyên dùng chung. Nhưng thiết kế khóa không chỉ là "lấy được khóa rồi chạy". Một giao thức đáng tin cậy phải xác định cách lấy khóa nguyên tử, thời gian được phép chờ, thời hạn sở hữu, cách gia hạn, cách giải phóng khi thành công và khi lỗi, cũng như cách ngăn tiến trình cũ tiếp tục ghi sau khi mất quyền.

Trong CI/CD, lỗi có thể xảy ra ở bất kỳ thời điểm nào: job bị hủy, runner mất kết nối, process bị kill, database restart, network partition hoặc pipeline timeout. Vì vậy, khóa cần được thiết kế theo hướng **bounded waiting, ownership rõ ràng, release an toàn và recovery có thể kiểm chứng**.

Bài viết tập trung vào vòng đời khóa và thời gian chờ trong các tác vụ triển khai, migration và data job. Nội dung bao gồm lock scope, acquire/release, timeout, lease, heartbeat, fencing token, xử lý lỗi, ví dụ database và CI, cùng các cách kiểm thử khi tiến trình bị gián đoạn.

## 1. Vì sao cần khóa trong CI/CD?

Một pipeline có thể chạy theo nhiều trigger: push, pull request, schedule, tag release hoặc thao tác thủ công. Hai lần chạy có thể cùng nhắm đến một tài nguyên:

- Hai workflow cùng deploy một service vào production.
- Migration mới bắt đầu khi migration trước chưa hoàn tất.
- Hai job cùng cập nhật một file cấu hình hoặc trạng thái release.
- Nhiều worker cùng xử lý một partition trong bảng dữ liệu.
- Một pipeline cũ tiếp tục chạy sau khi pipeline mới đã được khởi chạy.
- Job rollback và job deploy mới cùng sửa trạng thái của một environment.

Không phải mọi công việc chạy đồng thời đều nguy hiểm. Build và unit test trên các workspace riêng thường có thể chạy song song. Xung đột xuất hiện khi nhiều tiến trình cùng sửa một tài nguyên hoặc cùng thực hiện một thao tác mà thứ tự có ý nghĩa.

Khóa giúp bảo vệ invariant như:

- Chỉ một migration coordinator thay đổi schema tại một thời điểm.
- Chỉ một deployment operation đang điều khiển service/environment.
- Một partition chỉ có một worker được phép commit tại một thời điểm.
- Một release cũ không thể ghi đè release mới hơn.
- Chỉ owner hiện tại mới có quyền giải phóng khóa.

Khóa là cơ chế điều phối. Nó không thay thế transaction, idempotency, authorization hay kiểm tra trạng thái thực tế.

## 2. Xác định tài nguyên và phạm vi khóa

Trước khi chọn công nghệ, cần xác định chính xác tài nguyên nào cần được bảo vệ và những thao tác nào có thể xung đột.

### Khóa toàn hệ thống

Chỉ một tác vụ trong toàn hệ thống được phép chạy. Phù hợp với thao tác hiếm, ảnh hưởng rộng hoặc không thể chia nhỏ, ví dụ thay đổi cấu trúc hạ tầng dùng chung.

Nhược điểm là giảm concurrency. Một tác vụ chậm có thể chặn tất cả tác vụ khác dù chúng không xung đột.

### Khóa theo job

Chỉ ngăn hai instance cùng loại job chạy đồng thời. Ví dụ chỉ một lần chạy nightly-index-rebuild trong một environment.

Phạm vi này đơn giản, nhưng hai job khác tên vẫn có thể sửa cùng một tài nguyên. Vì vậy cần xác định quan hệ giữa job name và resource thực tế.

### Khóa theo resource hoặc environment

Khóa theo service/environment, database/schema, registry namespace hoặc một resource cụ thể. Ví dụ:

~~~text
deploy:order-api:production
migration:orders-db:public-schema
backfill:customer:partition-03
~~~

Hai job có cùng resource key sẽ cạnh tranh khóa; các resource độc lập vẫn có thể chạy song song.

### Khóa theo partition hoặc tenant

Với dữ liệu lớn, có thể chia phạm vi theo tenant, shard, ngày hoặc dải khóa chính. Điều kiện là các partition thực sự độc lập về dữ liệu và tác dụng phụ.

Không chọn lock key chỉ dựa vào tên job nếu hai job khác nhau vẫn cập nhật cùng một bảng hoặc cùng một business entity.

### Quy tắc chọn scope

Chọn phạm vi nhỏ nhất vẫn bảo vệ được invariant. Nếu khóa quá rộng, throughput giảm và hàng đợi dài. Nếu khóa quá hẹp, hai thao tác có thể cùng thay đổi một trạng thái không nhất quán.

Một khóa cần có namespace rõ ràng, ví dụ gồm project, service, environment và resource. Cách đặt tên phải ổn định qua các lần chạy và không chứa secret.

## 3. Những thuộc tính của một giao thức khóa an toàn

Một giao thức khóa nên trả lời được các câu hỏi sau:

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| Mutual exclusion | Hai owner có thể cùng được cấp khóa hay không? |
| Ownership | Ai đang giữ khóa và bằng chứng ownership là gì? |
| Atomic acquire | Việc kiểm tra và chiếm khóa có phải một thao tác nguyên tử? |
| Bounded wait | Worker chờ tối đa bao lâu? |
| Lease/expiry | Khi owner mất tích, quyền có được thu hồi không? |
| Renewal | Owner gia hạn khóa bằng cách nào? |
| Safe release | Owner cũ có thể xóa khóa của owner mới không? |
| Fencing | Tiến trình cũ có thể ghi sau khi mất khóa không? |
| Recovery | Sau crash, worker mới xác định trạng thái công việc ra sao? |
| Observability | Có thể biết ai đang giữ khóa, chờ bao lâu và vì sao không? |

Mutual exclusion chỉ là một phần. Với hệ thống phân tán, lease có thể hết hạn trong khi tiến trình cũ vẫn sống. Nếu nơi ghi dữ liệu không kiểm tra quyền hiện tại, hai tiến trình vẫn có thể tác động đồng thời dù lock service đã cấp khóa cho owner mới.

## 4. Phân biệt lock, lease, transaction và semaphore

Các cơ chế này thường được dùng cùng nhau nhưng không giống nhau.

- **Lock:** quyền độc quyền hoặc quyền truy cập được điều phối trên một tài nguyên.
- **Lease:** lock có thời hạn; quyền sở hữu hết hạn nếu không được gia hạn.
- **Transaction:** nhóm thay đổi dữ liệu được commit hoặc rollback trong một ranh giới database.
- **Semaphore:** giới hạn số lượng tiến trình được phép sử dụng một tài nguyên cùng lúc.
- **Mutex:** dạng khóa độc quyền, thường chỉ cho một owner tại một thời điểm.
- **Queue:** xếp thứ tự công việc thay vì để nhiều worker cùng tranh khóa.

Ví dụ, một deployment có thể dùng semaphore giới hạn tối đa một lần triển khai trên production, còn một migration schema dùng mutex độc quyền. Một data job có thể dùng lease để worker chết không giữ khóa mãi.

Không dùng transaction dài để thay thế lease cho tác vụ kéo dài hàng giờ. Transaction nên ngắn để giảm lock contention và áp lực database.

## 5. Acquire khóa phải nguyên tử

Một lỗi phổ biến là thực hiện hai bước riêng:

1. Kiểm tra xem khóa đã tồn tại chưa.
2. Nếu chưa, tạo khóa.

Hai worker có thể cùng kiểm tra và cùng thấy "chưa tồn tại", sau đó cùng tạo khóa. Đây là race condition.

Acquire phải được thực hiện bằng primitive nguyên tử do hệ thống điều phối cung cấp, ví dụ:

- Unique constraint hoặc conditional update trong database.
- Row lock trong transaction.
- SET-if-not-exists có expiry trong Redis.
- Compare-and-set trong coordination store.
- Resource group hoặc concurrency control của scheduler.

### Ví dụ claim một lock record trong database

Giả sử bảng lock có một dòng cho mỗi resource key và unique constraint trên lock_key. Worker có thể dùng conditional update:

~~~sql
UPDATE job_locks
SET owner_id = :owner_id,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '60 seconds',
    fencing_token = fencing_token + 1
WHERE lock_key = :lock_key
  AND lease_until < CURRENT_TIMESTAMP
RETURNING owner_id, lease_until, fencing_token;
~~~

Nếu không có dòng nào được trả về, khóa chưa hết hạn hoặc đang được owner khác giữ. Cần xử lý trường hợp tạo lock record lần đầu bằng insert có unique constraint và xử lý conflict. Toàn bộ claim phải chạy trong transaction phù hợp.

Không được đọc lease_until rồi cập nhật bằng hai request độc lập mà không có compare-and-set hoặc khóa, vì một worker khác có thể chiếm quyền giữa hai bước.

## 6. Thời gian chờ khi acquire

Worker không nên chờ khóa vô hạn. Một yêu cầu acquire nên có timeout hoặc deadline rõ ràng.

Ví dụ chính sách:

- Chờ tối đa 30 giây để lấy khóa deploy.
- Mỗi lần kiểm tra cách nhau 1-3 giây với jitter.
- Khi hết deadline, trả kết quả LOCK_BUSY hoặc ACQUIRE_TIMEOUT.
- Ghi nhận owner hiện tại và thời gian chờ nếu có thể.
- Không bắt đầu thao tác khi chưa xác nhận acquire thành công.

### Chờ cố định hay backoff?

Polling mỗi 100 ms có thể tạo tải lớn lên lock service khi nhiều worker cùng chờ. Chờ cố định quá lâu làm tăng độ trễ phản hồi.

Có thể dùng backoff tăng dần và jitter:

~~~text
delay = min(max_delay, base_delay * 2^attempt)
wait = random(0, delay)
~~~

Ví dụ bắt đầu 250 ms, tăng dần tới 3 giây, tổng thời gian chờ không quá 30 giây. Giá trị thực tế phụ thuộc latency, số worker và SLA.

Nếu hệ thống hỗ trợ notification hoặc blocking acquire có timeout, có thể ưu tiên cơ chế đó thay vì polling liên tục.

### Chọn hành vi khi khóa đang bận

Tùy loại job, khi khóa bận có thể:

- Chờ trong deadline rồi thử lại.
- Đưa công việc vào queue.
- Bỏ qua trigger trùng nếu một run tương đương đang hoạt động.
- Thất bại sớm để scheduler lên lịch lại.
- Hiển thị trạng thái đang chờ để người vận hành theo dõi.

Không phải lúc nào chờ cũng tốt. Một release mới có thể cần thay thế release cũ đang chờ, nhưng việc hủy phải tuân theo chính sách và trạng thái của operation cũ.

## 7. Phân biệt các loại timeout

Không có một timeout duy nhất cho toàn bộ vòng đời khóa.

| Timeout | Ý nghĩa | Ví dụ |
|---|---|---|
| Acquire timeout | Thời gian tối đa chờ lấy khóa | 30 giây |
| Lease duration | Thời hạn owner giữ quyền trước khi phải gia hạn | 60 giây |
| Heartbeat interval | Khoảng cách giữa hai lần gia hạn/báo sống | 20 giây |
| Operation timeout | Thời gian tối đa cho một thao tác được bảo vệ | 20 phút |
| Query timeout | Thời gian tối đa cho một truy vấn database | 30 giây |
| Job deadline | Tổng thời gian job được phép chạy | 45 phút |
| Shutdown grace period | Thời gian dừng mềm để hoàn tất batch hiện tại | 30 giây |
| Cleanup timeout | Thời gian dành cho release/cleanup | 5 giây |

Các con số chỉ minh họa. Cần đặt sao cho lease đủ dài hơn heartbeat interval và có dư địa cho jitter/network delay. Đồng thời job deadline phải giới hạn tổng thời gian, tránh retry vô hạn.

### Acquire timeout khác lease duration

Acquire timeout chỉ giới hạn thời gian chờ trước khi có khóa. Lease duration giới hạn thời gian sở hữu sau khi acquire thành công.

Một worker có thể chờ 20 giây, nhận lease 60 giây, xử lý 10 phút bằng cách gia hạn định kỳ. Không nên dùng acquire timeout để suy ra thời gian job được phép chạy.

### Job deadline khác query timeout

Job deadline giới hạn toàn bộ tiến trình. Query timeout giới hạn một câu SQL. Nếu query timeout dài hơn thời gian còn lại của job, query có thể vẫn chạy sau khi caller đã từ bỏ nếu cancellation không được truyền đúng.

Nên truyền deadline còn lại cho từng bước và không bắt đầu thao tác mới khi không còn đủ thời gian hoàn tất hoặc dừng an toàn.

## 8. Lease và heartbeat

Lease giúp thu hồi quyền khi owner chết hoặc không thể liên lạc. Một worker nhận lease có thời hạn và phải gia hạn trước khi hết hạn.

Ví dụ:

~~~text
Lease duration: 60 seconds
Heartbeat interval: 20 seconds

t=00  Worker A acquires lease
t=20  A renews lease
t=40  A renews lease
t=60  A renews lease
...
~~~

Gia hạn phải kiểm tra owner ID hoặc token. Một worker không được gia hạn khóa đã thuộc về worker khác.

Nếu renew thất bại:

1. Dừng claim công việc mới.
2. Không bắt đầu transaction ghi mới.
3. Nếu đang trong transaction, kết thúc hoặc rollback theo ranh giới an toàn.
4. Đánh dấu operation cần reconcile.
5. Không tiếp tục ghi với giả định lease vẫn còn hiệu lực.

Heartbeat chỉ cho biết worker còn gửi được tín hiệu. Nó không chứng minh công việc đang tiến triển. Nên ghi thêm progress marker, batch đã commit và thời điểm commit gần nhất để phát hiện worker bị treo.

## 9. Fencing token ngăn owner cũ ghi dữ liệu

Lease hết hạn không tự động dừng process cũ. Worker có thể bị pause, mất mạng rồi hoạt động trở lại sau khi worker khác đã nhận khóa.

Ví dụ:

1. Worker A nhận lease với token 101.
2. A bị treo lâu hơn lease duration.
3. Lease hết hạn; worker B nhận khóa với token 102.
4. A sống lại và gửi lệnh ghi với token 101.
5. Hệ thống đích từ chối token 101 vì token mới nhất là 102.

Fencing token là số thứ tự tăng đơn điệu, được cấp khi có owner mới. Nơi ghi dữ liệu phải kiểm tra token; nếu chỉ ghi token vào log thì không bảo vệ được tài nguyên.

### Ví dụ kiểm tra fencing token

~~~sql
UPDATE deployment_state
SET version = :new_version,
    last_fencing_token = :token
WHERE service_name = :service
  AND environment = :environment
  AND COALESCE(last_fencing_token, 0) < :token;
~~~

Nếu số dòng cập nhật là 0, token đã cũ hoặc resource không tồn tại. Caller phải đọc trạng thái và không tiếp tục ghi như owner hợp lệ.

Cần thiết kế sao cho token mới được cấp từ nguồn có tính tăng đơn điệu. Không dùng timestamp do worker tự tạo làm fencing token vì đồng hồ giữa các máy có thể lệch.

## 10. Release khóa an toàn

Khi công việc hoàn tất, owner cần giải phóng khóa. Release phải kiểm tra ownership để tránh worker cũ xóa khóa của worker mới.

### Không xóa khóa chỉ bằng resource key

Giả sử A giữ khóa, lease của A hết hạn, B nhận khóa mới. Nếu A thức dậy và chạy lệnh xóa theo lock_key, A có thể xóa nhầm khóa của B.

Mọi thao tác release cần so sánh owner token:

~~~sql
DELETE FROM job_locks
WHERE lock_key = :lock_key
  AND owner_id = :owner_id
  AND fencing_token = :fencing_token;
~~~

Nếu không có dòng nào bị xóa, owner không còn giữ khóa. Đây không nhất thiết là lỗi; có thể lease đã hết hạn hoặc một worker khác đã nhận quyền.

### Redis lock

Với Redis, mẫu thường gặp là SET key token NX PX ttl để tạo khóa có thời hạn và token owner ngẫu nhiên. Khi release, dùng Lua script kiểm tra token hiện tại trước khi DEL:

~~~lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
else
  return 0
end
~~~

Không dùng DEL trực tiếp chỉ theo key. Token owner giúp tránh xóa nhầm khóa của tiến trình khác.

Mẫu Redis lock cần được đánh giá cùng cấu hình persistence, replication và failover. Trong môi trường có yêu cầu nhất quán cao, lock ở Redis không tự bảo đảm fencing cho database hoặc cloud API. Nơi ghi vẫn cần kiểm tra version/token hoặc dùng một cơ chế điều phối có bảo đảm phù hợp.

## 11. Giải phóng khóa khi lỗi: finally và cleanup

Với process còn sống, release nên nằm trong khối cleanup luôn được thực hiện dù thao tác thành công hay ném exception.

Ví dụ Java dùng AutoCloseable:

~~~java
try (LockHandle lock = lockProvider.acquire(
        "deploy:order-api:production",
        Duration.ofSeconds(30),
        Duration.ofSeconds(60))) {

    deploymentService.applyDesiredVersion(
        "order-api",
        "production",
        "sha256:abc123"
    );

    deploymentService.verifyRollout("order-api", "production");
}
~~~

LockHandle.close() phải release theo owner token và xử lý trường hợp lease đã mất. Không nên để close() xóa khóa của owner khác.

Nếu API acquire trả về không có khóa, không được chạy phần thân. Có thể dùng exception hoặc kết quả Optional/Result để phân biệt acquired và timeout.

### Cleanup không được che mất lỗi gốc

Nếu deploy thất bại và release khóa cũng thất bại, log cần giữ cả hai lỗi. Không để exception trong cleanup thay thế hoàn toàn exception gốc mà không ghi nhận nguyên nhân đầu tiên.

Mẫu xử lý:

~~~java
LockHandle lock = lockProvider.acquire(...);
try {
    runProtectedOperation();
} finally {
    try {
        lock.release();
    } catch (Exception releaseError) {
        logger.error("Could not release lock", releaseError);
    }
}
~~~

Đây là ví dụ khái niệm; trong code thực tế cần bảo đảm acquire thành công trước khi vào try/finally và ghi nhận trạng thái cleanup để có thể đối soát.

### finally không xử lý được mọi kiểu crash

finally chạy khi runtime có cơ hội unwind stack. Nó không bảo đảm chạy khi:

- Process bị kill -9 hoặc bị terminate cứng.
- Máy mất điện.
- Container runtime hoặc host crash.
- JVM bị dừng bất thường.
- Network partition khiến process không thể gọi lock service.
- Hệ điều hành dừng process mà không có grace period.

Vì vậy, cleanup chủ động phải kết hợp với lease expiry, connection cleanup và recovery process.

## 12. Giải phóng khóa khi database connection bị ngắt

Với transaction-scoped lock, database tự giải phóng khi transaction commit/rollback hoặc session kết thúc. Với session-scoped advisory lock, khóa tồn tại tới khi release hoặc session đóng.

Điều này đặc biệt quan trọng khi dùng connection pool:

- Không trả connection về pool khi còn session lock.
- Luôn release session lock trong cleanup.
- Nếu release thất bại, reset hoặc loại bỏ connection thay vì tái sử dụng tùy tiện.
- Không giả định connection timeout ở client đồng nghĩa server đã đóng session.
- Theo dõi session và lock holder khi job bị treo.

Nếu một network partition làm client mất kết nối nhưng database vẫn giữ session, session lock có thể tiếp tục tồn tại cho tới khi server phát hiện connection chết hoặc TCP timeout xảy ra. Cần đặt keepalive và timeout ở tầng phù hợp, nhưng không nên dựa vào việc timeout network để bảo đảm phục hồi tức thời.

Với tác vụ dài, lock record có lease và heartbeat thường dễ quan sát hơn việc giữ một database transaction mở nhiều giờ.

## 13. Khóa trong PostgreSQL

PostgreSQL cung cấp row-level lock, table-level lock và advisory lock.

### Transaction-scoped advisory lock

Ví dụ:

~~~sql
BEGIN;

SELECT pg_try_advisory_xact_lock(202611, 6) AS acquired;

-- Chỉ thực hiện phần thay đổi được bảo vệ nếu acquired = true.

COMMIT;
~~~

Khóa được giải phóng khi transaction kết thúc. Phù hợp với thao tác ngắn nằm trong một transaction. Không giữ transaction mở suốt một job backfill dài chỉ để giữ advisory lock.

### Session-scoped advisory lock

Session lock có thể tồn tại qua nhiều transaction:

~~~sql
SELECT pg_try_advisory_lock(202611, 6);
-- Protected work
SELECT pg_advisory_unlock(202611, 6);
~~~

Phải bảo đảm unlock trên đúng session. Với connection pool, session có thể được tái sử dụng nên cần cleanup chắc chắn và tránh để connection có lock quay lại pool.

### Row lock cho job control

Có thể khóa dòng job record bằng SELECT FOR UPDATE trong transaction ngắn để chuyển trạng thái READY sang RUNNING. Sau khi ghi owner/lease, commit transaction rồi xử lý batch bên ngoài. Mỗi batch mở transaction riêng để ghi dữ liệu và checkpoint.

Không nên giữ row lock trong lúc gọi dịch vụ ngoài hoặc chờ người phê duyệt.

## 14. Khóa phân tán và giới hạn của TTL

Distributed lock hữu ích khi worker chạy trên nhiều máy. Một lock service có thể lưu owner và thời hạn lease. Tuy nhiên, TTL chỉ là cơ chế thu hồi sau một khoảng thời gian; nó không dừng tiến trình cũ.

Các rủi ro cần xem xét:

- Worker bị pause lâu hơn TTL.
- Network partition giữa worker và lock service.
- Clock drift nếu expiry dựa vào thời gian client.
- Lock service failover và mất cập nhật mới nhất.
- Worker cũ tiếp tục gửi request tới hệ thống đích.
- Release bị gửi trễ sau khi owner mới đã nhận khóa.

Để tăng độ an toàn:

- Dùng primitive atomic từ lock service.
- Dùng owner token duy nhất cho mỗi lần acquire.
- Gia hạn có điều kiện theo owner.
- Release có điều kiện theo owner.
- Dùng fencing token tại hệ thống đích khi có thể.
- Giữ thao tác được bảo vệ trong thời gian hữu hạn.
- Đối soát resource state sau khi mất lease.

Không khẳng định một Redis lock hay một TTL đơn lẻ bảo đảm mutual exclusion tuyệt đối trong mọi failure mode. Mức đảm bảo phụ thuộc vào kiến trúc lock service và việc hệ thống đích có kiểm tra quyền ghi hay không.

## 15. Tránh deadlock bằng thứ tự lấy khóa

Deadlock có thể xảy ra khi hai transaction giữ các khóa khác nhau rồi chờ khóa của nhau.

Ví dụ:

~~~text
Transaction A              Transaction B
-------------              -------------
Lock resource 1            Lock resource 2
Wait for resource 2        Wait for resource 1
       |                          |
       +---------- DEADLOCK ------+
~~~

Cách giảm deadlock:

- Lấy nhiều khóa theo cùng một thứ tự toàn hệ thống.
- Giữ transaction ngắn.
- Không chờ user approval hoặc gọi API bên ngoài khi đang giữ row lock.
- Chỉ khóa đúng các resource cần thiết.
- Dùng timeout để phát hiện chờ quá lâu.
- Retry transaction bị database hủy do deadlock nếu toàn bộ thao tác có thể chạy lại an toàn.

Nếu job cần khóa service và database, định nghĩa thứ tự cố định, ví dụ acquire deployment lock trước rồi mới mở transaction DB ngắn. Tất cả job phải tuân thủ cùng thứ tự để tránh vòng chờ.

## 16. Cancellation và graceful shutdown

Khi pipeline bị cancel, runner thường gửi tín hiệu dừng trước rồi mới terminate process sau một khoảng grace period.

Job nên xử lý dừng mềm:

1. Ngừng nhận công việc mới.
2. Không bắt đầu batch mới.
3. Hoàn tất hoặc rollback transaction hiện tại.
4. Ghi checkpoint sau khi dữ liệu đã commit.
5. Ghi trạng thái PAUSED/INTERRUPTED.
6. Release khóa nếu vẫn là owner hợp lệ.
7. Đóng connection và tài nguyên.
8. Thoát trước khi grace period hết.

Nếu không đủ thời gian, để lease hết hạn và dùng recovery worker tiếp nhận. Không cố giữ khóa vô thời hạn chỉ vì cleanup chưa hoàn tất.

### Cancel job không đồng nghĩa thao tác đã dừng

Một CI job có thể bị cancel trong khi server phía sau vẫn đang xử lý request. Ví dụ lệnh deploy đã gửi tới Kubernetes API hoặc deployment service. Sau khi cancel, cần tra cứu trạng thái operation và observed state trước khi chạy lại.

Không chỉ dựa vào trạng thái job của CI để kết luận lock hoặc side effect đã được giải phóng.

## 17. Khóa trong GitHub Actions và GitLab CI

CI platform cung cấp một số cơ chế concurrency ở cấp workflow hoặc resource. Chúng hữu ích để điều phối các job đi qua cùng nền tảng, nhưng không thay thế lock ở database/service nếu có nhiều hệ thống cùng truy cập tài nguyên.

### GitHub Actions concurrency group

Ví dụ:

~~~yaml
name: deploy

on:
  push:
    branches: [main]

concurrency:
  group: deploy-order-api-production
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-24.04
    steps:
      - name: Deploy
        run: ./scripts/deploy.sh
~~~

Concurrency group giúp giới hạn các workflow cùng group. Với deploy production, cancel-in-progress false thường phù hợp hơn nếu hủy workflow đang chạy có thể để lại trạng thái không rõ. Hành vi xếp hàng và thay thế run pending phụ thuộc chính sách nền tảng; không nên coi group là distributed lock giữa các repository hoặc hệ thống ngoài GitHub.

Nếu cần tuần tự tuyệt đối và kiểm tra trạng thái resource, deployment service hoặc database vẫn nên có lock/operation state riêng.

### GitLab resource_group

Ví dụ:

~~~yaml
deploy_production:
  stage: deploy
  resource_group: order-api-production
  script:
    - ./scripts/deploy.sh
~~~

Resource group giúp serialize các job dùng cùng resource group trong phạm vi GitLab project. Cần cấu hình process mode và kiểm tra thứ tự chạy phù hợp. Nếu có job từ project khác hoặc thao tác ngoài GitLab, resource group không bảo vệ các nguồn đó.

## 18. Khi khóa hết hạn hoặc không thể release

Không nên xóa lock record thủ công chỉ vì thấy job cũ không còn chạy trên dashboard. Cần xác minh:

- Owner ID và run ID hiện tại.
- Lease expiry và heartbeat gần nhất.
- Process/runner còn hoạt động không.
- Có transaction hoặc request phía server đang chạy không.
- Fencing token mới nhất.
- Resource state đã thay đổi đến đâu.
- Có thể resume hoặc reconcile operation cũ không.

Nếu đã xác minh owner chết và lease hết hạn, recovery worker có thể claim khóa mới bằng thao tác atomic và token mới. Sau đó kiểm tra checkpoint/operation state trước khi tiếp tục.

Nếu lock không có lease, có thể cần thao tác quản trị để thu hồi. Việc force unlock phải có audit, lý do và xác minh resource trước/sau; nếu không, worker cũ có thể tiếp tục chạy và tạo split-brain.

## 19. Observability cho lock và thời gian chờ

Khóa khó vận hành nếu chỉ biết job đang "pending". Cần ghi metadata đủ để tìm owner và nguyên nhân chờ.

Mỗi lần acquire nên ghi:

- Lock key hoặc resource scope.
- Owner ID, run ID và attempt.
- Thời điểm request/acquire/release.
- Acquire wait duration.
- Lease expiry và heartbeat time.
- Fencing token.
- Kết quả renew/release.
- Operation ID được bảo vệ.
- Lý do release hoặc lease loss.
- Job deadline và thời gian còn lại.

Metrics hữu ích:

| Metric | Ý nghĩa |
|---|---|
| lock_acquire_wait_seconds | Thời gian chờ acquire |
| lock_acquire_failures_total | Số lần acquire thất bại |
| active_locks | Số khóa đang được giữ |
| lock_lease_renew_failures_total | Số lần renew thất bại |
| lock_expired_total | Số lease hết hạn |
| lock_release_failures_total | Số lần release lỗi |
| lock_contention_total | Số lần tranh chấp khóa |
| lock_holder_duration_seconds | Thời gian owner giữ khóa |
| stale_owner_write_rejections_total | Số lần fencing từ chối owner cũ |
| job_deadline_exceeded_total | Số job vượt deadline |

Không ghi secret hoặc token xác thực vào log. Owner token có thể được ghi dưới dạng ID/fingerprint không nhạy cảm để điều tra.

## 20. Kiểm thử failure path của giao thức khóa

Một lock protocol cần được kiểm thử trong các tình huống lỗi, không chỉ happy path.

### Kiểm thử acquire

- Hai worker acquire cùng key đồng thời: chỉ một worker thành công.
- Hai worker acquire key khác nhau: không chặn nhau.
- Lock đang bận: acquire timeout đúng deadline.
- Lock record chưa tồn tại: insert cạnh tranh không tạo hai owner.
- Worker mất kết nối trong lúc acquire: tra cứu trạng thái trước khi gửi lại nếu kết quả chưa rõ.

### Kiểm thử lease và fencing

- Worker renew trước hạn: lease được gia hạn.
- Worker renew sau khi owner đã thay đổi: bị từ chối.
- Lease hết hạn và worker mới nhận token cao hơn.
- Worker cũ sống lại: hệ thống đích từ chối token cũ.
- Owner cũ release: không xóa khóa của owner mới.

### Kiểm thử release và crash

- Operation thành công: release được thực hiện.
- Operation ném exception: cleanup vẫn được gọi.
- Release service tạm lỗi: lỗi được ghi nhận và recovery hoạt động.
- Process bị kill cứng: lease hết hạn và worker mới có thể tiếp nhận.
- Database connection đóng: transaction lock được giải phóng theo semantics của DB.
- Session lock với connection pool: connection không quay lại pool khi còn lock.

### Kiểm thử thời lượng

- Lock wait vượt timeout.
- Query vượt statement timeout.
- Job deadline đến giữa batch.
- Heartbeat bị trễ.
- Network partition dài hơn lease.
- Graceful shutdown không đủ thời gian.
- Nhiều job cùng retry acquire gây contention.

Kết quả cần xác nhận là chỉ một owner hợp lệ có thể ghi, khóa không bị xóa nhầm, job không chờ vô hạn và resource cuối cùng ở trạng thái có thể đối soát.

## 21. Anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách xử lý |
|---|---|---|
| Check-then-set thành hai thao tác riêng | Hai worker cùng nhận khóa | Dùng atomic acquire/compare-and-set |
| Chờ khóa vô hạn | Job bị kẹt và giữ runner | Đặt acquire timeout/deadline |
| TTL quá ngắn | Lease hết hạn khi owner vẫn xử lý | Đo batch duration và renew phù hợp |
| TTL quá dài | Phục hồi chậm sau crash | Chọn lease hợp lý và có heartbeat |
| Release chỉ theo lock key | Owner cũ xóa khóa của owner mới | So sánh owner token/fencing token |
| Dựa vào finally để xử lý mọi crash | Process kill cứng không release | Kết hợp lease expiry và recovery |
| Giữ DB transaction nhiều giờ | Blocking, deadlock và rollback lớn | Transaction ngắn, checkpoint và lease |
| Không có fencing | Worker cũ ghi sau khi mất lease | Kiểm tra token tại nơi ghi |
| Dùng CI concurrency làm khóa duy nhất | Job ngoài CI vẫn có thể xung đột | Bảo vệ ở service/database |
| Force delete lock record khi chưa xác minh | Split-brain và ghi đè dữ liệu | Xác minh owner, operation và resource |
| Cleanup che mất lỗi gốc | Khó tìm nguyên nhân thực | Ghi nhận riêng operation failure và release failure |
| Heartbeat được coi là progress | Worker treo vẫn giữ khóa | Theo dõi batch/commit progress |
| Retry acquire quá nhanh | Lock service quá tải | Backoff, jitter và queue |

## 22. Checklist thiết kế khóa an toàn

### Phạm vi và ownership

- [ ] Xác định tài nguyên và invariant cần bảo vệ.
- [ ] Chọn lock scope theo job/resource/environment/partition.
- [ ] Lock key có namespace ổn định.
- [ ] Acquire là thao tác atomic.
- [ ] Ownership có owner ID và token rõ ràng.
- [ ] Không có đường ghi nào bỏ qua giao thức khóa nếu invariant yêu cầu độc quyền.

### Thời gian chờ và lease

- [ ] Có acquire timeout và chính sách khi khóa bận.
- [ ] Có lease duration cho worker phân tán.
- [ ] Heartbeat interval phù hợp lease và network delay.
- [ ] Có job deadline, query timeout và shutdown grace period.
- [ ] Không chờ vô hạn hoặc retry không giới hạn.
- [ ] Renew chỉ thành công với owner hiện tại.
- [ ] Có fencing token/version check tại nơi ghi.

### Release và phục hồi

- [ ] Release kiểm tra owner token.
- [ ] Cleanup chạy khi thành công và exception.
- [ ] Release failure không che mất lỗi gốc.
- [ ] Có lease expiry hoặc cơ chế thu hồi khi process chết.
- [ ] Connection pool không tái sử dụng session còn lock.
- [ ] Có quy trình reconcile trước khi force unlock.
- [ ] Worker mới đọc operation/checkpoint trước khi tiếp tục.

### Vận hành và kiểm thử

- [ ] Log lock key, owner, run ID, wait duration và fencing token.
- [ ] Có metric acquire wait, lease expiry, renew/release failure.
- [ ] Test hai worker acquire đồng thời.
- [ ] Test owner cũ sống lại sau khi lease hết hạn.
- [ ] Test process kill và database/network failure.
- [ ] Test deadlock, timeout và graceful shutdown.
- [ ] Có audit cho thao tác force unlock.

## Kết luận

Một khóa chỉ hữu ích khi ownership và vòng đời của nó được xác định rõ. Hãy chọn lock scope theo tài nguyên cần bảo vệ, acquire bằng thao tác nguyên tử, giới hạn thời gian chờ, dùng lease và heartbeat cho worker phân tán, đồng thời kiểm tra fencing token tại nơi ghi để ngăn owner cũ tiếp tục tác động. Release phải so sánh owner token và được gọi trong cleanup khi có thể; lease expiry và recovery xử lý các trường hợp process chết hoặc mất kết nối. Khi kết hợp timeout, transaction ngắn, graceful shutdown, quan sát và kiểm thử failure path, pipeline có thể phục hồi sau lỗi mà không giữ khóa vô hạn hoặc xóa nhầm khóa của tiến trình khác.


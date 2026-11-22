# Backfill dữ liệu lớn mà không làm quá tải dịch vụ chính

Trong **SPRING_BOOT_INTEGRATION**, Spring Boot thường kết nối HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter Spring Integration thành một luồng dữ liệu liên tục. Khi cần **backfill** hàng triệu bản ghi đã bị thiếu hoặc xây dựng lại một bảng phục vụ truy vấn, luồng phục hồi phải chạy trong lúc người dùng vẫn gọi API và các consumer vẫn xử lý dữ liệu mới. Nếu không kiểm soát, một công việc có vẻ đơn giản như quét bảng và ghi lại từng bản ghi có thể làm cạn connection pool, tạo backlog broker, tăng độ trễ p99, gây replication lag và khiến dịch vụ chính mất khả năng đáp ứng.

Bài học tập trung vào **vận hành backfill khối lượng lớn có kiểm soát**: xác định phạm vi chính xác, phân bổ ngân sách tài nguyên, chia nhỏ công việc, giới hạn tốc độ, checkpoint, chống trùng, phối hợp với live traffic, quan sát và tự động dừng khi hệ thống chịu tải. Ví dụ dùng **Spring Boot + PostgreSQL** làm nền, với cách mở rộng sang HTTP client, cache, RabbitMQ/Kafka và Spring Batch.

## 1. Bối cảnh: xây dựng lại bảng tra cứu đơn hàng

Giả sử hệ thống có bảng **orders** chứa 30 triệu đơn hàng. API dùng bảng **order_projection** để trả nhanh trạng thái đơn. Một lỗi triển khai đã bỏ sót cập nhật projection trong ba ngày. Để sửa, đội vận hành cần quét lại khoảng **8 triệu đơn** và khôi phục projection.

Trong lúc đó:

- API đang phục vụ người dùng thực, có SLA độ trễ và tỷ lệ lỗi.
- Luồng **live** vẫn nhận OrderCreated, OrderPaid, OrderShipped từ broker.
- PostgreSQL primary đang phục vụ các transaction tạo/cập nhật đơn.
- Read replica, broker, Redis và đối tác HTTP đều có giới hạn riêng.
- Dữ liệu đang thay đổi; backfill có thể đọc bản cũ sau khi live đã ghi bản mới.

Một câu lệnh **SELECT toàn bộ rồi UPDATE từng hàng nhanh nhất có thể** có thể hoàn thành backfill sớm nhưng làm hệ thống mất ổn định. Mục tiêu đúng là **hoàn thành phục hồi trong một ngân sách tải cho phép**, với khả năng pause, resume, retry và đối soát kết quả.

~~~mermaid
flowchart LR
    SOURCE[("Nguồn đơn hàng / read replica")] --> READER["Backfill reader theo page nhỏ"]
    READER --> LIMIT["Rate limit + concurrency limit"]
    LIMIT --> APPLY["Idempotent projection writer"]
    LIVE["Live events"] --> APPLY
    APPLY --> TARGET[("Order projection DB")]
    CTRL[("Backfill run + task + checkpoint")] <--> READER
    METRICS["DB p95, pool wait, replica lag, API errors"] --> ADAPT["Controller: tăng / giảm / pause"]
    ADAPT --> LIMIT
    TARGET --> API["Production API"]
~~~

**Điểm mấu chốt:** backfill thường là **khối lượng công việc có thể hoãn**, còn giao dịch của người dùng và xử lý sự kiện live thường có độ ưu tiên cao hơn. Cơ chế điều tiết phải bảo vệ **tài nguyên thực sự dùng chung** giữa hai luồng.

## 2. Backfill khác replay và xử lý dữ liệu live ở đâu?

| Luồng | Dữ liệu được đọc | Mục đích | Đặc điểm vận hành |
| --- | --- | --- | --- |
| **Live ingestion** | Sự kiện, request mới | Duy trì trạng thái gần thời gian thực | Ưu tiên latency và ổn định |
| **Retry/redelivery** | Một thao tác hoặc message chưa xác nhận | Hoàn tất kết quả không chắc chắn | Giữ identity/idempotency key |
| **Replay** | Sự kiện lịch sử đã lưu trong log/archive | Chạy lại logic hoặc tái tạo projection | Cần retention, offset và tránh side effect lặp |
| **Backfill** | Dữ liệu thiếu hoặc một phạm vi lịch sử từ DB/API/file | Lấp khoảng thiếu hay tạo lại dữ liệu | Khối lượng lớn, cần giới hạn tải và đối soát |
| **Reconciliation** | Hai trạng thái được coi là nguồn và đích | Phát hiện/sửa chênh lệch | Quyết định đã hoàn tất phục hồi hay chưa |

Backfill có thể **dùng kỹ thuật replay** nếu nguồn là event archive, nhưng không phải broker nào cũng lưu đủ lịch sử. RabbitMQ queue thông thường không cho đọc lại những message đã ack/xóa; Kafka cho đọc lại trong phạm vi log còn được retention giữ; RabbitMQ Streams có cơ chế offset/retention riêng. Không giả định có thể backfill từ mọi queue khi không có nguồn lịch sử phù hợp.

Một bản ghi bị thiếu trong projection không tự trở thành đơn hàng mới khi được backfill. **eventTime/sourceVersion** phản ánh thời điểm và thứ tự ở hệ thống nguồn; **ingestedAt/backfillRunId** phản ánh thời điểm vận hành phục hồi. Cần tách chúng để tránh đếm doanh thu hoặc gửi thông báo sai kỳ.

## 3. Đầu tiên xác định ranh giới dữ liệu và cách chứng minh đầy đủ

Trước khi tính throughput, phải biết chính xác **đọc cái gì**. Một backfill không có phạm vi ổn định dễ rơi vào vòng lặp quét mãi hoặc bỏ sót dữ liệu ở biên.

### 3.1. Xác định nguồn chân lý

Với bảng projection, nguồn chân lý có thể là:

1. **Bảng đơn hàng hiện tại**: phù hợp nếu chỉ cần trạng thái cuối và bảng nguồn chứa đầy đủ các trường cần dựng lại.
2. **Event archive/CDC log**: cần khi projection được tính từ mọi thay đổi lịch sử, ví dụ ledger hoặc tổng doanh thu theo sự kiện.
3. **API đối tác có snapshot/cursor**: dùng khi không sở hữu database nguồn.
4. **Tệp snapshot bất biến**: hữu ích với backfill ngoại tuyến hoặc tải lại theo phiên bản.

Nếu nghiệp vụ cần lịch sử cộng dồn, **snapshot trạng thái cuối** thường không khôi phục được tất cả các giao dịch trung gian. Không áp cùng một quy tắc cập nhật latest-state cho ledger tính tiền, điểm thưởng hoặc lệnh thanh toán.

### 3.2. Khóa phạm vi và cutoff

Với bảng chỉ **thêm bản ghi** có khóa số tăng ổn định, có thể chụp một **high-watermark theo ID**, ví dụ **id <= H**, rồi đọc bằng keyset pagination. Các bản ghi mới có ID lớn hơn H thuộc luồng live hoặc một run sau. Tuy nhiên, **H chỉ khóa phạm vi hàng được chèn**, không đóng băng các update/delete lên hàng cũ.

Với bảng **có cập nhật**, cần một trong các cơ chế:

- Snapshot nhất quán tại mốc W rồi nạp các thay đổi từ CDC/log **sau W**.
- API nguồn hỗ trợ **snapshot token/cursor** bảo đảm cùng một phiên bản dữ liệu trong suốt phiên đọc.
- Dữ liệu có **sourceVersion/revision**, handler cập nhật có điều kiện, thêm kiểm tra reconciliation và tombstone.
- Nếu không có các bảo đảm trên, phải ghi rõ giới hạn, lấy cửa sổ overlap và kiểm tra chênh lệch sau khi nạp.

Chỉ dùng **updatedAt <= now()** hoặc offset page trên bảng thay đổi liên tục không tạo snapshot nhất quán. Một bản ghi được cập nhật trong lúc quét có thể xuất hiện ở trang khác, bị bỏ qua hoặc được đọc hai lần.

### 3.3. Thiết kế điều kiện hoàn tất ngay từ đầu

Không dùng chỉ số “worker đã đọc xong mọi page” làm định nghĩa hoàn thành. Ví dụ một backfill đạt yêu cầu khi:

- Tập khóa nguồn trong phạm vi cutoff có đủ đại diện ở đích.
- Các bản ghi đích có version/trạng thái tương thích với nguồn ở watermark đã chọn.
- Không còn gap không giải thích được, xung đột dữ liệu hoặc bản ghi bị quarantine vượt ngưỡng cho phép.
- Backfill không gây mất SLA production, tác động lặp hoặc lỗi giới hạn tài nguyên.
- Kết quả đối soát, thời gian và cấu hình run được ghi lại để audit.

## 4. Lập ngân sách tài nguyên trước khi bật công việc

Một backfill lớn có thể sử dụng đồng thời CPU, RAM, network, disk I/O, DB connections, HTTP connections, broker partitions, Redis operations và khóa dữ liệu. Chỉ giới hạn **số thread worker** là chưa đủ nếu mỗi thread gửi batch SQL cực lớn.

### 4.1. Ưu tiên ngân sách của luồng live

Đo baseline trong giờ cao điểm và khi tải thấp:

| Tài nguyên | Baseline cần quan sát | Dấu hiệu backfill gây hại |
| --- | --- | --- |
| API/service | RPS, error rate, p95/p99 latency, request queue | p95/p99 tăng, timeout, 429/503 |
| PostgreSQL primary | CPU, IOPS, WAL, lock wait, active sessions, replication lag | Transaction live chậm, checkpoint/WAL bùng tăng |
| Read replica | CPU/I/O, replica lag, query duration | Replica trả dữ liệu quá cũ hoặc đuổi theo primary không kịp |
| Connection pool | active, idle, pending acquire, timeout | Thread chờ lấy connection, request live bị từ chối |
| Broker | queue depth, oldest message age, lag, redelivery | Consumer live bị giành mất tài nguyên |
| HTTP đối tác | quota, 429/5xx, p95 latency | Rate limit, circuit breaker mở |
| Redis/cache | latency, CPU, evictions, throughput | Cache nóng bị trục xuất, API phải fallback DB |

Nên xác định **ngưỡng dừng** dựa trên SLO production. Ví dụ minh họa: chỉ chạy khi p95 API dưới 250 ms, DB CPU dưới 70%, connection pool pending gần 0 và replica lag dưới 5 giây. Đây **không phải** ngưỡng mặc định cho mọi hệ thống; thông số thật cần đo tải và mục tiêu phục vụ.

### 4.2. Quy đổi quota đầu ra thành tốc độ backfill

Ví dụ một API đối tác có quota **120 HTTP request/giây**, live traffic cao điểm cần 85 request/giây, hệ thống để dành 15 request/giây cho burst. Ngân sách tối đa có thể dành cho backfill:

\[
Q_{\mathrm{backfill}} \le 120 - 85 - 15 = 20\ \text{request/giây}
\]

Nên **khởi chạy thấp hơn ngưỡng tính toán**, chẳng hạn 5 request/giây, rồi tăng từ từ theo số đo. Quota API chỉ là **một** giới hạn. Nếu DB chỉ chịu thêm 10 bản ghi/giây do áp lực I/O thì **10 bản ghi/giây** (quy đổi đúng đơn vị công việc) mới là giới hạn chi phối.

Không quy đổi cố định “1 item = 1 SQL statement”. Một item có thể cần 1 đọc + nhiều update + cache invalidation + outbox write. Nên đo **tài nguyên trên mỗi nghìn item** tại các mức throughput khác nhau và tính lại khi schema/index thay đổi.

### 4.3. Ước lượng thời gian không biến thành lời hứa

Với **8 triệu bản ghi** và tốc độ **40 bản ghi/giây** được duy trì, thời gian xử lý thuần là:

\[
\frac{8\,000\,000}{40} = 200\,000\ \text{giây} \approx 55{,}6\ \text{giờ}
\]

Đây chỉ là **kịch bản giả định** trước khi tính pause, retry, đối soát và thay đổi tải live. Nếu tốc độ cần thiết để kịp deadline vượt headroom an toàn, phải đổi kiến trúc: đọc từ snapshot/object storage, tăng hiệu quả SQL, xây bảng mới theo batch, hoặc thương lượng cửa sổ bảo trì. Không nên tăng vô hạn concurrency để ép tiến độ.

## 5. Cô lập tài nguyên để backfill không tranh suất của production

### 5.1. Tách worker khỏi API

Ưu tiên một tiến trình/deployment riêng cho backfill, ví dụ Spring Boot worker có profile riêng, thay vì chạy một vòng lặp quét 8 triệu hàng trong thread xử lý HTTP request. Deployment riêng cho phép:

- Đặt **CPU/memory requests và limits** rõ ràng.
- Dùng **connection pool riêng** cho read replica và target DB.
- Giới hạn **số worker replicas**, không autoscale dựa trên backlog mà bỏ qua sức chịu tải database.
- Tách thread pool, queue và retry policy.
- Pause/stop toàn bộ backfill mà không restart API.

Dù tách tiến trình, **database primary, network và broker vẫn là tài nguyên chung**. Cô lập deployment chỉ có ích khi đi kèm quota, pool và giới hạn throughput.

### 5.2. Đọc từ replica hoặc snapshot khi phù hợp

Với workload đọc lớn, **read replica** hoặc bản snapshot được tạo ở môi trường phân tích giúp giảm quét trên primary. Nhưng cần nhớ:

- Replica vẫn chia sẻ tài nguyên storage/network ở một số kiến trúc và có thể gây thêm tải I/O.
- Replica có **lag**, nên nguồn đọc có thể cũ hơn event live đã xử lý.
- Truy vấn dài trên replica có thể xung đột với replay WAL/vacuum tùy cấu hình database.
- Dữ liệu dùng cho backfill phải phù hợp watermark/snapshot đã chọn.
- Ghi projection có thể vẫn phải đi vào primary; chuyển đọc ra replica **không giải quyết** tải ghi.

Với phục hồi dữ liệu cực lớn, xuất snapshot ra object storage theo partition hoặc dựng projection trên một database/cluster riêng rồi **cutover có kiểm soát** thường có hiệu quả hơn hàng triệu upsert vào bảng production.

### 5.3. Cơ chế ưu tiên và ngừng khẩn cấp

Một job cần có **pause flag/kill switch** được quan sát định kỳ, cấu hình **max concurrency**, **max rows/request per second**, thời gian timeout và ngưỡng lỗi. Khi guardrail kích hoạt, job ngừng **nhận task mới**, hoàn thành hoặc rollback chunk đang chạy theo chính sách và ghi checkpoint. Không nên kill process giữa một giao dịch lớn nếu có thể tránh.

## 6. Đọc dữ liệu lớn bằng keyset và chia lô nhỏ

### 6.1. Tránh OFFSET ngày càng lớn

Truy vấn như sau thường kém hiệu quả khi offset tăng cao:

~~~sql
SELECT id, state, source_version
FROM orders
ORDER BY id
LIMIT 500 OFFSET 7000000;
~~~

Database phải đi qua nhiều hàng trước khi tới trang cần lấy; nếu dữ liệu nguồn được thêm/xóa, các trang offset còn dễ bị trượt và gây thiếu/trùng.

Nếu khóa **id** là số nguyên tăng và có index, dùng **keyset pagination**:

~~~sql
-- :lastId bắt đầu trước khóa đầu tiên của phạm vi.
-- :rangeEnd là giới hạn trên CỐ ĐỊNH của task.
SELECT id, state, source_version, updated_at
FROM orders
WHERE id > :lastId
  AND id <= :rangeEnd
ORDER BY id
LIMIT :pageSize;
~~~

Sau khi các item trong page đã được xử lý bền vững, cập nhật **lastId = id của hàng cuối cùng**. Chỉ số này là **cursor đọc**, không phải bằng chứng mọi side effect đã thành công nếu target và checkpoint lưu ở hai transaction manager khác nhau.

**Giới hạn của keyset:** một cột id có index giải quyết chi phí phân trang, không tự tạo snapshot nhất quán. Nếu nguồn cho phép update/delete vào hàng có id nhỏ hơn cursor, những thay đổi đó cần sourceVersion/CDC/reconciliation riêng. Với khóa tổng hợp, thiết kế sort key đầy đủ và bất biến.

### 6.2. Chia task theo phạm vi nhỏ

Thay vì giao cho một worker quét toàn bộ bảng, chia phạm vi thành các **task**:

~~~text
Run R-20261121 / high-watermark H = 30,000,000
  Task 001: id 1         ..  100,000
  Task 002: id 100,001   ..  200,000
  ...
  Task 300: id 29,900,001 .. 30,000,000

Mỗi task dùng pageSize=300, commit theo page/chunk,
giữ lastId và có lease để resume khi worker chết.
~~~

Giá trị 100.000 ID/task và 300 item/page chỉ là ví dụ; nếu dữ liệu rất thưa, nhiều ID có thể không tồn tại. Chia theo **ID range** không đồng nghĩa mỗi task chứa số bản ghi bằng nhau. Khi có phân vùng hoặc tenant lớn, có thể chia theo **partition/date/tenant** và lấy histogram để cân bằng tải. Luôn chặn phạm vi đọc bằng high-watermark của run.

### 6.3. Index và query plan quan trọng hơn số lượng worker

Tạo/chọn index phù hợp cho điều kiện lọc, sắp xếp và phân vùng. Ví dụ:

~~~sql
-- Nếu backfill chỉ chọn các hàng theo source_system và id:
CREATE INDEX CONCURRENTLY IF NOT EXISTS orders_source_id_idx
    ON orders (source_system, id);

-- Query minh họa dùng index này:
SELECT id, state, source_version, updated_at
FROM orders
WHERE source_system = :source
  AND id > :lastId
  AND id <= :rangeEnd
ORDER BY id
LIMIT :pageSize;
~~~

**CREATE INDEX CONCURRENTLY** là câu lệnh PostgreSQL cần xem xét kế hoạch triển khai, dung lượng và I/O; không nên mặc định tạo index mới trên primary chỉ để chạy một job. Với bảng đang phục vụ production, đánh giá index hiện có và chạy thử query plan trên dữ liệu đại diện. **EXPLAIN ANALYZE** thực thi truy vấn nên phải dùng cẩn trọng khi truy vấn lớn.

## 7. Lưu run, task, lease và checkpoint để pause/resume

Một dịch vụ backfill vận hành tốt cần lưu **trạng thái điều phối bền vững** thay vì dựa vào biến đếm trong RAM.

### 7.1. Bảng điều phối minh họa trên PostgreSQL

~~~sql
CREATE TABLE backfill_run (
    id                  uuid PRIMARY KEY,
    kind                varchar(80) NOT NULL,
    source_system       varchar(80) NOT NULL,
    scope_description   text NOT NULL,
    high_watermark      bigint,
    state               varchar(16) NOT NULL,
    page_size           integer NOT NULL,
    requested_rate      integer NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    started_at          timestamptz,
    finished_at         timestamptz,
    CHECK (state IN ('PLANNED', 'RUNNING', 'PAUSED', 'FAILED', 'COMPLETED')),
    CHECK (page_size > 0 AND requested_rate > 0)
);

CREATE TABLE backfill_task (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id          uuid NOT NULL REFERENCES backfill_run(id),
    range_start     bigint NOT NULL,
    range_end       bigint NOT NULL,
    last_id         bigint NOT NULL,  -- lúc tạo = range_start - 1
    state           varchar(16) NOT NULL DEFAULT 'PENDING',
    lease_token     uuid,
    lease_until     timestamptz,
    attempts        integer NOT NULL DEFAULT 0,
    available_at    timestamptz NOT NULL DEFAULT now(),
    last_error_code varchar(80),
    CHECK (range_start > 0 AND range_end >= range_start),
    CHECK (last_id >= range_start - 1 AND last_id <= range_end),
    CHECK (state IN ('PENDING', 'RUNNING', 'DONE', 'FAILED'))
);

CREATE INDEX backfill_task_ready_idx
    ON backfill_task (available_at, id)
    WHERE state = 'PENDING';
~~~

Không nên dùng **backfill_run** làm source of truth cho trạng thái hóa đơn; nó chỉ ghi hoạt động vận hành. Các bảng tác vụ có thể ở schema/DB điều phối riêng, nhưng nếu checkpoint muốn commit **nguyên tử cùng projection write** thì cần transaction thực sự bao được cả hai. Nếu không thể, phải chấp nhận at-least-once và thiết kế writer idempotent.

### 7.2. Claim một task bằng lease

Khi có nhiều worker replica, dùng giao dịch ngắn với **FOR UPDATE SKIP LOCKED** để tránh hai worker claim cùng task cùng lúc:

~~~sql
-- Chạy trong một transaction NGẮN trên DB điều phối.
-- :leaseToken là UUID mới cho mỗi lần claim.
WITH picked AS (
    SELECT t.id
    FROM backfill_task AS t
    JOIN backfill_run AS r ON r.id = t.run_id
    WHERE r.state = 'RUNNING'
      AND (
        (t.state = 'PENDING' AND t.available_at <= now())
        OR (t.state = 'RUNNING' AND t.lease_until < now())
      )
    ORDER BY t.id
    FOR UPDATE OF t SKIP LOCKED
    LIMIT 1
)
UPDATE backfill_task AS t
SET state = 'RUNNING',
    lease_token = :leaseToken,
    lease_until = now() + interval '60 seconds',
    attempts = attempts + 1
FROM picked
WHERE t.id = picked.id
RETURNING t.id, t.run_id, t.range_start, t.range_end,
          t.last_id, t.lease_token;
~~~

Sau khi claim, **commit transaction claim** rồi mới đọc nguồn/call HTTP. Không giữ khóa DB chờ hàng trăm HTTP response hoặc hàng triệu dòng. Lease phải đủ dài hoặc được **gia hạn có điều kiện theo lease_token**; nếu worker chết, task RUNNING hết lease sẽ được worker khác nhận lại.

**Lease chỉ giảm xử lý cạnh tranh, không bảo đảm exactly-once.** Worker cũ có thể vẫn đang thực thi lúc worker mới claim sau khi hết lease. Mọi cập nhật checkpoint/phần ghi đích phải kiểm tra **lease_token** và writer phải idempotent. Nếu source và target không hỗ trợ transaction chung, retry có thể xử lý lại một page sau crash.

## 8. Writer idempotent và checkpoint ở ranh giới commit

### 8.1. Projection có version guard

Giả sử mỗi đơn ở nguồn có **source_version tăng đơn điệu** theo orderId, và projection cần giữ **trạng thái mới nhất**:

~~~sql
CREATE TABLE order_projection (
    source_system         varchar(80) NOT NULL,
    order_id              bigint NOT NULL,
    source_version        bigint NOT NULL,
    state                 varchar(40) NOT NULL,
    state_updated_at      timestamptz NOT NULL,
    rebuilt_at            timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_system, order_id)
);

-- Cùng đơn hàng, chỉ ghi khi phiên bản nguồn CAO HƠN.
INSERT INTO order_projection AS p (
    source_system, order_id, source_version, state, state_updated_at
)
VALUES (:source, :orderId, :version, :state, :stateUpdatedAt)
ON CONFLICT (source_system, order_id)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    state = EXCLUDED.state,
    state_updated_at = EXCLUDED.state_updated_at,
    rebuilt_at = now()
WHERE p.source_version < EXCLUDED.source_version;
~~~

Vì có điều kiện version, backfill version=11 không ghi lùi projection đã được live cập nhật lên version=13. Nếu cùng version mà payload khác nhau, cần **conflict detection/quarantine** theo hợp đồng nguồn; chỉ số version không tự phát hiện mọi mâu thuẫn. Với dữ liệu cộng dồn như sổ cái, phải dùng **ledger theo eventId/transactionId**, không thay bằng latest-state upsert.

### 8.2. Minh họa ghi một chunk bằng Spring Boot

Ví dụ dưới đây giả định **backfill_task** và **order_projection** ở **cùng PostgreSQL DataSource/transaction manager**. Việc đọc page từ nguồn đã hoàn tất bên ngoài transaction của phương thức này; dữ liệu đã validate và sắp xếp theo orderId tăng.

~~~java
public record SourceOrder(
        long id, long sourceVersion,
        String state, Instant stateUpdatedAt) {}

@Service
public class BackfillChunkWriter {
    private final JdbcTemplate jdbc;

    public BackfillChunkWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void writePage(
            long taskId, UUID leaseToken,
            String sourceSystem, List<SourceOrder> rows) {

        if (rows.isEmpty()) {
            return; // Worker đánh dấu DONE bằng thao tác có kiểm tra lease.
        }

        for (SourceOrder order : rows) {
            jdbc.update("""
                    INSERT INTO order_projection AS p
                        (source_system, order_id, source_version,
                         state, state_updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (source_system, order_id)
                    DO UPDATE SET
                        source_version = EXCLUDED.source_version,
                        state = EXCLUDED.state,
                        state_updated_at = EXCLUDED.state_updated_at,
                        rebuilt_at = now()
                    WHERE p.source_version < EXCLUDED.source_version
                    """,
                    sourceSystem, order.id(), order.sourceVersion(),
                    order.state(), Timestamp.from(order.stateUpdatedAt()));
        }

        long lastId = rows.get(rows.size() - 1).id();
        int checkpointUpdated = jdbc.update("""
                UPDATE backfill_task
                SET last_id = ?, lease_until = now() + interval '60 seconds'
                WHERE id = ?
                  AND lease_token = ?
                  AND state = 'RUNNING'
                  AND lease_until > now()
                  AND last_id < ?
                """, lastId, taskId, leaseToken, lastId);

        if (checkpointUpdated != 1) {
            // Rollback toàn bộ page, kể cả các upsert projection.
            throw new IllegalStateException("Lease or cursor is stale");
        }
    }
}
~~~

**Vì sao cập nhật checkpoint cuối giao dịch?** Nếu DB commit cả projection và **last_id**, lần restart biết đoạn nào đã xử lý bền vững. Nếu cập nhật checkpoint trước rồi write lỗi, có thể **bỏ sót** dữ liệu. Nếu write thành công nhưng checkpoint không được commit trong cùng transaction, đoạn đó có thể bị chạy lại và writer phải idempotent.

Trong ví dụ này, phương thức **@Transactional** phải được gọi qua Spring proxy, không tự gọi trong cùng bean. Lease 60 giây chỉ là giá trị minh họa: chunk phải hoàn thành trong khoảng thuê hoặc worker gia hạn lease đúng cách. **Không chuyển một giao dịch 60 giây thành cơ chế chờ HTTP dài**; nên giữ mỗi chunk ngắn. Khi lease hết hạn, code ném exception để rollback; không tự tiếp tục ghi với token cũ.

### 8.3. Khi điều phối và target nằm ở các database khác nhau

Khi không thể dùng một DB transaction chung:

1. Đọc page từ nguồn và ghi target theo **idempotent upsert/unique key**.
2. Chỉ khi target đã commit thành công mới lưu cursor/checkpoint ở DB điều phối.
3. Nếu crash giữa hai bước, **đọc lại một page** khi resume, chấp nhận at-least-once.
4. Đối soát target với source để phát hiện thiếu dữ liệu; không suy từ cursor rằng mọi side effect đã đúng.

Đây là mô hình **at-least-once processing** có chống trùng. Không coi @Transactional trên một datasource là transaction phân tán với datasource còn lại, HTTP API, cache hoặc RabbitMQ.

## 9. Điều tiết tốc độ: concurrency, throughput và phản hồi theo tải

Backfill nên có ít nhất **hai loại giới hạn độc lập**:

- **Concurrency limit:** tối đa bao nhiêu request, chunk hoặc transaction đang xử lý đồng thời.
- **Rate limit:** tối đa bao nhiêu đơn vị công việc mỗi giây, ví dụ HTTP call/giây, row/giây hoặc byte/giây.

Concurrency thấp nhưng mỗi task gửi SQL batch khổng lồ vẫn có thể gây quá tải. Rate thấp mà mỗi request chờ rất lâu vẫn có thể tích nhiều công việc in-flight. Do đó phải giới hạn **cả hai** và giới hạn kích thước page/chunk.

### 9.1. Cấu hình minh họa của worker

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 4
      connection-timeout: 2000

# Nhóm khóa CUSTOM của ứng dụng; Spring Boot không tự thực thi chúng.
backfill:
  enabled: false
  page-size: 300
  max-in-flight-pages: 2
  max-rows-per-second: 40
  worker-poll-interval: 1000ms
  pause-on-primary-cpu-percent: 75
  pause-on-live-api-p95-ms: 350
  pause-on-replica-lag: 5s
~~~

Các khóa **backfill.*** phải được ứng dụng đọc và thực thi thông qua cấu hình riêng, limiter và controller; chỉ viết YAML **không tự tạo throttling**. Pool size 4 phù hợp minh họa cho một worker nhỏ, không phải con số chuẩn. Nếu có nhiều worker instance, **tổng pool và tổng rate** phải được giới hạn ở cấp cụm, không chỉ mỗi instance.

### 9.2. Token bucket, semaphore và giới hạn cụm

**Semaphore** giới hạn số công việc đồng thời; **token bucket/rate limiter** phân phối số lượt cho phép trong một cửa sổ thời gian. Khi dùng nhiều replica, limiter in-memory trên từng replica cho phép tổng tốc độ vượt quota; cần phân bổ rate budget cho từng replica hoặc dùng limiter phân tán đáng tin cậy.

Ví dụ policy:

~~~text
Global quota:        40 rows/s
Worker replicas:     2
Budget mỗi replica:  20 rows/s
Max in-flight page:  1 mỗi replica
Page size:           300

Page 300 rows phải tiêu thụ ngân sách ~15 giây/replica
hoặc chia thành chunk nhỏ; không được gửi 300 update tức thì
rồi đợi 15 giây nếu burst đó gây nghẽn primary.
~~~

Để tránh burst, nên giới hạn **kích thước chunk** và cấp permit theo **row/chunk có chi phí đã đo**, thay vì chỉ dùng trung bình trong một phút. Nếu DB chịu tốt transaction 50 hàng, có thể bắt đầu với chunk 50 và phân bố nhịp các chunk. Khi quota liên quan API đối tác, dùng request/giây và giới hạn số trang song song riêng.

### 9.3. Adaptive throttling theo sức khỏe production

Rate cố định không phản ánh lưu lượng live thay đổi theo giờ. Một controller đơn giản có thể áp dụng **additive increase, multiplicative decrease (AIMD)**:

~~~text
Nếu các guardrail ổn định trong nhiều cửa sổ:
    targetRate = min(maxRate, targetRate + 2 rows/s)

Nếu API p95 vượt ngưỡng hoặc DB pool wait tăng:
    targetRate = max(minRate, floor(targetRate * 0.5))

Nếu live error rate, replica lag hoặc DB lock wait vượt mức nghiêm trọng:
    PAUSE nhận task mới

Chỉ RESUME sau khi điều kiện hồi phục ổn định
và operator/automation cho phép theo chính sách.
~~~

Đây là **thuật toán minh họa**, không phải API có sẵn của Spring Batch. Cần áp dụng smoothing, hysteresis và cửa sổ đo hợp lý để tránh rate nhảy lên xuống liên tục. Tín hiệu phải được đo đủ gần với tài nguyên đích; ví dụ p95 API có thể tăng do nguyên nhân khác, vì thế cần phân tích và vẫn ưu tiên an toàn production.

### 9.4. Retry không được phá quota

HTTP 429, 503, DB deadlock, broker unavailable có thể là lỗi tạm thời. Retry phải:

- Có **giới hạn số lần**, **exponential backoff** và **jitter**.
- Tính luôn lưu lượng retry vào quota, không được retry “ngoài limiter”.
- Tôn trọng **Retry-After** khi đối tác cung cấp và contract cho phép.
- Chuyển lỗi vĩnh viễn như schema sai hoặc record không hợp lệ sang quarantine, không retry vô tận.
- Không để một task thất bại liên tục chiếm toàn bộ worker slots.

Một backfill đang lỗi mà tăng thread/replica để “đuổi tiến độ” thường khuếch đại sự cố.

## 10. Bảo vệ database, HTTP client, broker và cache

### 10.1. PostgreSQL: transaction ngắn và truy vấn có index

Nên:

- Giữ chunk nhỏ, transaction ngắn; tránh giữ row lock trong lúc gọi HTTP.
- Dùng **bulk insert/upsert** khi phù hợp, nhưng điều chỉnh batch size theo latency/WAL/lock wait thực tế.
- Đảm bảo index phục vụ keyset query và khóa unique dùng cho idempotency.
- Chọn **statement_timeout** và **lock_timeout** cho kết nối worker để một truy vấn kéo dài không giữ tài nguyên vô hạn.
- Theo dõi **autovacuum, WAL generation, replication lag, disk space, connection count** và ảnh hưởng lên query chính.
- Cân nhắc partition hoặc dựng bảng mới rồi cutover nếu ghi lại phần lớn bảng production.

Không dùng một transaction duy nhất cho hàng triệu bản ghi. Việc giữ snapshot/transaction rất dài có thể cản trở vacuum, gia tăng bloat và khiến khôi phục lỗi khó khăn.

### 10.2. HTTP: cân đối quota đối tác và connection pool

Khi nguồn backfill là HTTP API:

- Dùng cursor/keyset/snapshot token của đối tác; lưu cursor **sau khi page đã xử lý bền vững**.
- Đặt connect, read/response timeout, connection pool và max concurrency riêng cho worker.
- Giới hạn request rate toàn cụm; tránh để retry làm bùng tải.
- Kiểm tra pagination consistency, snapshot expiry, dữ liệu bị xóa/sửa và schema version.
- Nếu đối tác hỗ trợ bulk export, cân nhắc tải archive một lần về object storage rồi đọc từ đó thay vì gọi hàng triệu API nhỏ.

Nếu dịch vụ chính và backfill dùng cùng API quota, phải **dành quota cho live**. Ngay cả worker chạy ở deployment riêng vẫn có thể làm đối tác trả 429 cho request khách hàng.

### 10.3. RabbitMQ/Kafka: đừng lấn hàng đợi live

Nếu backfill tạo message:

- Xem xét **queue/topic riêng** và consumer pool riêng, tránh flood vào hàng đợi ưu tiên cao.
- Hạn chế publisher rate và **số message đang chờ confirm**, theo dõi queue depth, oldest message age, consumer lag.
- RabbitMQ cần cân nhắc publisher confirms, returns/mandatory, delivery mode và cấu hình queue phù hợp; timeout confirm không chứng minh publish thất bại, do đó cần idempotency.
- Kafka cần tính partition/consumer lag, backpressure, throughput producer, retention và điều kiện giữ thứ tự theo key.
- Giữ **eventId nguồn** khi replay/backfill; không dùng deliveryTag hoặc offset mới làm business identity.

Khi producer ghi DB rồi phát message, dùng **Transactional Outbox** nếu cần bảo đảm ý định phát event cùng commit nghiệp vụ. Với consumer, dùng **inbox/idempotent processing và ack sau DB commit**. Backfill không tạo atomicity xuyên database và broker chỉ bằng một @Transactional.

### 10.4. Redis/cache: tránh stampede khi làm mới hàng loạt

Không invalidate hàng triệu cache key cùng một thời điểm nếu mọi request sau đó đều quay về DB. Có thể:

- Rebuild nền và cập nhật cache theo nhịp có giới hạn.
- Dùng version namespace/cache key theo dataset để cutover khi dữ liệu mới sẵn sàng.
- Invalidate theo phân vùng, thêm jitter vào TTL và kiểm tra hit rate/eviction.
- Không dùng Redis dedup cache làm bằng chứng duy nhất “đã xử lý” nếu mất cache có thể tạo side effect lặp.

Một cache refresh có vẻ nhẹ cũng có thể tạo tải cao khi số lượng key và tỷ lệ miss tăng cùng lúc.

## 11. Spring Batch và Spring Integration đóng vai trò nào?

Không có yêu cầu phải tự viết mọi thành phần điều phối. **Spring Batch** phù hợp để tổ chức backfill theo **Job/Step**, **chunk**, **JobParameters**, **ExecutionContext**, restart và tiến độ. **Spring Integration** phù hợp để nối nhiều adapter và xử lý message/HTTP/broker. Hai thư viện có thể dùng cùng nhau, nhưng việc hạn chế tải vẫn là trách nhiệm cấu hình và vận hành cụ thể.

### 11.1. Spring Batch: chunk không đồng nghĩa tự rate limit

Ví dụ cấu hình Step cơ bản kiểu Spring Batch 5+:

~~~java
@Bean
Step rebuildProjectionStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRecord> sourceReader,
        ItemProcessor<OrderRecord, ProjectionRecord> processor,
        ItemWriter<ProjectionRecord> targetWriter) {

    return new StepBuilder("rebuildProjectionStep", jobRepository)
            .<OrderRecord, ProjectionRecord>chunk(100, transactionManager)
            .reader(sourceReader)
            .processor(processor)
            .writer(targetWriter)
            .build();
}
~~~

**chunk(100)** xác định ranh giới commit theo số item trong một chunk; nó **không bảo đảm** chỉ ghi 100 item/giây. Job có thể chạy hàng chục chunk mỗi giây nếu nguồn và đích phản hồi nhanh. Cần bổ sung throttling riêng qua giới hạn executor, rate limiter tại reader/writer, scheduler hoặc cơ chế điều phối phân tán đã thiết kế.

**JobRepository/ExecutionContext** lưu metadata tiến độ kỹ thuật, nhưng không thay thế **bảng business data, khóa unique/idempotency và trạng thái đối soát**. Nếu Step đọc nguồn ở DB khác và ghi đích ở một DB riêng, checkpoint với write không tự nguyên tử. Khi restart, phải chấp nhận có thể đọc lại một số item và xử lý an toàn.

### 11.2. Spring Integration: tách luồng và điều tiết channel

Spring Integration có thể kết nối **HTTP inbound/outbound gateway, AMQP inbound/outbound adapter, JDBC polling, transformer, router, filter, aggregator**. Với backfill:

- Nên tách channel/flow cho **recovery traffic** và **live traffic** nếu hai loại có chính sách tải khác nhau.
- **ExecutorChannel** giúp tách thread của nhánh nhưng phải gắn **bounded executor/queue**.
- **QueueChannel** tạo đệm, nhưng hàng đợi không giới hạn sẽ che giấu quá tải và làm tăng latency; phải có capacity và overflow policy.
- Poller cần **fixed delay/rate, maxMessagesPerPoll, task executor** và khả năng pause theo health signal.
- Khi đi qua broker, kiểm soát ack, retry, DLQ và idempotency của consumer.

Tạo nhiều executor hoặc tăng **maxMessagesPerPoll** không giải quyết nghẽn database; chỉ thay vị trí tích backlog. Cần đo **độ sâu hàng đợi và độ trễ của từng đoạn** để tìm nút cổ chai thật.

## 12. Cách đối xử với dữ liệu cũ khi live vẫn ghi

Một backfill lớn thường chạy nhiều giờ hoặc nhiều ngày. Trong thời gian đó, sự kiện live tiếp tục thay đổi projection. Có ba chiến lược phổ biến:

| Chiến lược | Thích hợp | Lưu ý |
| --- | --- | --- |
| **Live + backfill cùng writer có version guard** | Latest-state projection với sourceVersion đáng tin | Không ghi lùi; không phù hợp mọi ledger hoặc workflow theo thứ tự |
| **Snapshot + CDC catch-up + cutover** | Rebuild phần lớn bảng, yêu cầu ảnh chụp nhất quán | Cần mốc source log và khả năng theo kịp live |
| **Tạm đệm live theo key rồi replay tuần tự** | Nghiệp vụ phải xử lý mọi transition, ví dụ saga | Cần trạng thái pending/gap và giới hạn backlog |

Đặc biệt:

- **eventTime** là thời gian sự kiện diễn ra; **ingestedAt** là khi job đọc lại. Không chuyển hóa đơn năm trước thành doanh thu hôm nay vì backfill.
- **sourceVersion/sequence** là cơ sở sắp thứ tự nếu upstream bảo đảm; không lấy **thời điểm tới** làm “bản mới hơn”.
- **Delete/tombstone** cần version phù hợp, tránh snapshot cũ “hồi sinh” dữ liệu đã bị xóa.
- **Same version, different payload** cần được ghi nhận conflict và đối soát, không âm thầm bỏ qua.
- Với business action như thanh toán/gửi email, không phát lại mù quáng; kiểm tra idempotency key và trạng thái side effect ở hệ thống đích.

Một **HTTP 200 khi backfill gọi endpoint** không chứng minh dữ liệu đã commit đúng trên mọi hệ thống sau nó. Các tác động ngoài DB cần retry, idempotency, xác nhận và audit riêng.

## 13. Tiến độ, quan sát và guardrail vận hành

### 13.1. Phân biệt tiến độ đọc với dữ liệu thực sự khôi phục

Nên có các counter:

| Chỉ số | Ý nghĩa |
| --- | --- |
| **scanned** | Số hàng ứng viên đã được reader nhìn thấy |
| **validated** | Số hàng vượt kiểm tra hợp đồng |
| **applied** | Số thay đổi thực sự được áp dụng vào đích |
| **duplicate/stale** | Bản ghi đã có hoặc sourceVersion không mới hơn |
| **conflict/rejected** | Dữ liệu mâu thuẫn hoặc không hợp lệ, cần đối soát |
| **retried** | Số lượt xử lý lại sau lỗi |
| **pending/running/done tasks** | Tiến độ điều phối |
| **oldest incomplete task age** | Task bị kẹt hoặc thiếu worker |
| **watermark gap** | Khoảng cách giữa dữ liệu nguồn và đích đã xác minh |

**scanned = 8 triệu** không có nghĩa **applied = 8 triệu** và càng không chứng minh mọi đơn đã đúng. Nếu run chỉ phục hồi một phần bảng hoặc có bản ghi stale/duplicate hợp lệ, applied thấp hơn scanned là bình thường; cần đối soát bằng trạng thái và identity nguồn.

### 13.2. Bộ chỉ số bảo vệ live

Theo dõi cùng thời gian:

- API **RPS, p50/p95/p99**, error rate, saturation/queue wait.
- DB primary CPU, active connections, pool pending, lock waits, deadlocks, WAL, replication lag.
- Read replica lag, query latency, CPU/I/O; xác minh watermark dữ liệu.
- Broker **queue depth/consumer lag**, oldest message age, nack/timeout/DLQ.
- Backfill **rows/sec, pages/sec, retries/sec**, số worker, lease expiry, pause duration.
- Cache latency, hit rate, evictions; số request fallback xuống DB.

Trong log/tracing, gắn **backfillRunId, taskId, sourceSystem, source range, cursor, attempt** và đối chiếu với span HTTP/DB. Không dùng runId, rowId hoặc eventId làm nhãn Prometheus tùy ý gây cardinality cực cao; các ID cụ thể nằm trong log/trace/audit.

### 13.3. Một bảng điều khiển vận hành cần trả lời được

1. Backfill **đang đọc đúng phạm vi** và chưa vượt cutoff chưa?
2. **Tốc độ hiện tại** là bao nhiêu, do người vận hành đặt hay controller đang giảm vì quá tải?
3. Tác động tới **live latency, lỗi và DB lock wait** ra sao?
4. Những task nào đang chờ, retry, hết lease hoặc bị quarantine?
5. Đã đối soát được bao nhiêu và còn gap nào?
6. Có thể **pause/resume an toàn** ở điểm nào mà không làm trùng dữ liệu?

## 14. Quy trình triển khai từ dry-run đến đóng run

### Giai đoạn 1: lập kế hoạch và dry-run

Ghi **runId, source, khoảng ID/thời gian, high-watermark/snapshot token, schemaVersion, pageSize, rate budget, max concurrency, điều kiện pause**. Đo query plan và chi phí trên dữ liệu đại diện. Dry-run có thể đếm/quét mẫu và ước lượng số rows cần cập nhật, nhưng **không ghi business effect** hoặc gắn marker đã xử lý nhầm với kết quả thật.

### Giai đoạn 2: canary có giới hạn

Chạy một phạm vi/tenant nhỏ, ví dụ **0,1% tập ứng viên**, tốc độ 5 rows/giây và một worker. Theo dõi trực tiếp p95/p99 API, connection pool, WAL, replica lag và kết quả projection. Kiểm tra khả năng **pause, restart cùng run và chống trùng** trước khi mở rộng.

### Giai đoạn 3: ramp-up có kiểm soát

Tăng dần rate hoặc số worker **một yếu tố mỗi lần**, theo ngưỡng đã quan sát. Cấu hình limiter toàn cụm, không chỉ mỗi replica. Nếu live performance vượt ngưỡng, tự giảm/đóng nhận task mới; ghi lại thời điểm và lý do throttle.

### Giai đoạn 4: phục hồi và đối soát liên tục

Chạy task từng trang, cập nhật checkpoint sau commit, retry có backoff và audit bản ghi lỗi. So sánh high-watermark đích với nguồn, phát hiện gap, stale, conflict và bản ghi xóa. Nếu có CDC catch-up, chỉ cutover khi dữ liệu bắt kịp mức yêu cầu và kiểm thử trạng thái live.

### Giai đoạn 5: kết thúc, không vội dọn state

Đánh dấu **COMPLETED** khi đối soát đạt tiêu chí, không chỉ khi mọi task DONE. Giữ lịch sử run/task, log lỗi, báo cáo tiến độ và checksum/đếm theo partition trong thời gian cần audit. Có chính sách cleanup tránh phình bảng điều phối nhưng không làm mất khả năng giải thích một lần phục hồi đã xảy ra.

## 15. Ma trận lỗi và cách phục hồi

| Tình huống | Rủi ro nếu làm đơn giản | Cách xử lý |
| --- | --- | --- |
| Worker chết sau write nhưng trước checkpoint | Trang được chạy lại | Writer idempotent, checkpoint sau commit; nếu cùng DB thì commit chung |
| Worker mất lease khi đang ghi | Hai worker ghi cùng task | Lease token guard; rollback khi mất quyền, idempotent upsert |
| Source API 429/503 | Retry storm, ảnh hưởng live | Backoff + jitter, limiter toàn cụm, ưu tiên live |
| Replica lag tăng | Backfill đọc bản quá cũ | Pause/chọn watermark phù hợp; version guard và reconciliation |
| SQL query full-scan | DB CPU/I/O tăng, live latency cao | Keyset/index/query plan; giảm chunk và rate |
| WAL/disk đầy | Primary lỗi, nguy cơ downtime | Cảnh báo và pause theo WAL/disk, tính trước dung lượng |
| Connection pool hết slot | Live API chờ kết nối | Worker pool riêng/nhỏ, max concurrency, guardrail pool wait |
| Backfill v11 đến sau live v13 | Ghi lùi trạng thái | Upsert có điều kiện sourceVersion |
| Bản ghi bị xóa ở nguồn | Snapshot cũ tạo lại dữ liệu đã xóa | Tombstone/version/catch-up |
| Dữ liệu lịch sử kích hoạt gửi email hoặc payment | Side effect lặp | Domain idempotency + policy side effect và audit |
| Một task sai schema liên tục | Worker retry vô hạn | Quarantine, số lần thử tối đa, mã lỗi, can thiệp |
| Broker backlog tăng do publish phục hồi | Consumer live lag | Queue/pool/rate tách riêng, áp backpressure |
| Run đã scan hết nhưng projection còn gap | Báo cáo thành công sai | Reconciliation độc lập trước COMPLETED |

## 16. Kiểm thử với tải và lỗi có chủ đích

Một bộ kiểm thử phù hợp cần kết hợp **tính đúng dữ liệu** và **bảo vệ production-like traffic**:

1. **Keyset/cursor:** với ID thưa và nguồn lớn, mỗi ID trong phạm vi được đọc đủ; không quét lặp do OFFSET.
2. **Crash sau commit:** giả lập worker chết giữa write và checkpoint; resume không tạo tác động nghiệp vụ trùng.
3. **Lease expiry:** worker A hết lease, worker B claim; A không được commit checkpoint với token cũ.
4. **Live race:** projection v13 được cập nhật trong khi backfill v11/v12 chạy; kết quả giữ v13.
5. **Nguồn thay đổi:** update/delete trong lúc backfill; snapshot/CDC/reconciliation nhận diện đúng phạm vi.
6. **Tải database:** chạy cùng traffic HTTP gần giờ cao điểm, giám sát p95/p99, connection pool, lock wait, WAL và replica lag.
7. **HTTP 429/503:** retry có backoff, tính vào quota, không gây storm.
8. **Broker backlog:** backfill phát lượng lớn message mà live consumer vẫn đạt giới hạn lag đã đặt.
9. **Pause/resume:** dừng giữa lô, khởi động lại worker và xác minh checkpoint/state không mất.
10. **Cạnh tranh nhiều worker:** cùng claim task từ DB; mỗi task có lease hợp lệ, dữ liệu cuối nhất quán.
11. **Dữ liệu lỗi:** quarantine các bản ghi sai schema/cùng version khác payload, không che giấu bằng tổng count.
12. **Đối soát:** cố tình bỏ một partition; hệ thống không được đánh dấu COMPLETED cho đến khi xử lý gap.

Trong Spring Boot, có thể kiểm thử database bằng **Testcontainers PostgreSQL**, HTTP partner bằng **WireMock/MockWebServer**, broker bằng container tương ứng và kịch bản tải bằng công cụ load test chuyên dụng. Kiểm thử tốc độ chỉ có giá trị khi dùng dữ liệu, index, băng thông và giới hạn connection gần với môi trường mục tiêu; unit test riêng cho vòng lặp reader không chứng minh không gây nghẽn production.

### Ví dụ tiêu chí chấp nhận

Giả sử mục tiêu là backfill 8 triệu đơn trong khi hệ thống vẫn nhận live events:

- Worker có thể **pause trong lúc đang chạy** và resume từ checkpoint bền vững, không bỏ qua dữ liệu đã commit.
- API production không vượt ngưỡng lỗi/latency đã thỏa thuận; nếu vượt, controller giảm rate hoặc pause task mới.
- Chạy đồng thời nhiều worker không vượt tổng **rate budget** và tổng connection pool đã cấp.
- Một đơn có sourceVersion mới hơn không bị backfill ghi lùi; các message trùng không tạo side effect lần hai.
- Khi run kết thúc, reconciliation theo source watermark/partition xác nhận độ đầy đủ; các gap và conflict còn lại được báo rõ.

## 17. Checklist vận hành backfill lớn

- [ ] Xác định **source of truth, scope, cutoff/watermark** và giới hạn retention.
- [ ] Có **baseline production SLO**, rate budget, ngưỡng giảm tốc/pause và kill switch.
- [ ] Tách worker/pool/queue với live khi phù hợp; giới hạn **cả concurrency và throughput**.
- [ ] Dùng **keyset/partition/snapshot** thay vì OFFSET lớn hoặc transaction quá dài.
- [ ] Có index phù hợp, chunk/page nhỏ, timeout và chính sách WAL/replica lag.
- [ ] Lưu **run/task/lease/cursor** bền vững; checkpoint sau commit và writer idempotent.
- [ ] Đối xử đúng với **event identity, sourceVersion, tombstone, dữ liệu cũ và side effect**.
- [ ] Có **retry backoff, jitter, quarantine, DLQ** phù hợp và không cho retry phá quota.
- [ ] Theo dõi **live p95/p99, DB pool wait, broker lag, replica lag, rows/sec** và khả năng pause/resume.
- [ ] Triển khai **dry-run → canary → ramp-up → reconciliation → hoàn tất**, có hồ sơ audit và cơ chế xử lý chênh lệch.

**Nguyên tắc cần nhớ:** Backfill dữ liệu lớn là một **công việc vận hành được điều tiết bằng sức chịu tải còn lại của hệ thống**, đồng thời là một bài toán **nhất quán dữ liệu**. Sự an toàn đến từ **nguồn dữ liệu và watermark rõ ràng, đọc theo page có kiểm soát, idempotent write, checkpoint bền vững, rate limit thích ứng và reconciliation**. Một job chạy nhanh hoặc báo COMPLETED chưa đủ; kết quả phải đúng và các dịch vụ chính vẫn đáp ứng được người dùng trong suốt quá trình phục hồi.

# Thiết kế xử lý lặp an toàn bằng khóa nghiệp vụ

## 1. Vì sao Spring Cloud Task cần idempotency?

Spring Cloud Task giúp xây dựng ứng dụng Spring Boot **chạy hữu hạn** và ghi nhận vòng đời mỗi lần thực thi qua `TaskExecution` trong `TaskRepository`. Một tác vụ nhập file, đóng sổ, đối soát hoặc xuất báo cáo có thể được kích hoạt từ CronJob, API, CLI hay bộ điều phối. Khi có sự cố, các hệ thống đó thường **chạy lại cùng nghiệp vụ**.

Các tình huống phổ biến:

- Tác vụ đã commit dữ liệu nhưng JVM bị kill trước khi TaskRepository ghi thời gian kết thúc.
- Bộ điều phối không nhận được phản hồi nên khởi chạy lại, dù lần trước có thể đã hoàn tất.
- Người vận hành yêu cầu chạy bù một ngày đã bị nghi ngờ thất bại.
- Hai instance cùng nhận yêu cầu xử lý một file hoặc kỳ đối soát.
- Message broker giao lại một thông điệp sau timeout xác nhận.
- API client retry khi kết nối mạng bị ngắt.

Ví dụ tác vụ chốt doanh thu cho `tenant-A` ngày `2026-11-23` đã tạo số liệu thành công. Nếu chạy lại mà cộng thêm doanh thu lần nữa, hệ thống có thể ghi nhận **hai lần cho một ý định nghiệp vụ**.

**Idempotency** nghĩa là việc áp dụng lại cùng ý định nghiệp vụ không làm thay đổi kết quả có hiệu lực sau khi ý định đó đã được áp dụng thành công:

\[
apply(apply(S, K), K) = apply(S, K)
\]

Trong đó `S` là trạng thái dữ liệu và `K` là khóa nghiệp vụ. Đây là tính chất của **hiệu ứng nghiệp vụ**, không yêu cầu hai lần chạy có cùng mã TaskExecution hay cùng log. Một lần retry hoàn toàn có thể tạo TaskExecution mới, nhưng phải không tạo thêm kết quả nghiệp vụ ngoài ý muốn.

## 2. Phân biệt TaskExecutionId và khóa nghiệp vụ

Điểm dễ nhầm: **TaskExecutionId chỉ định danh một lần chạy ứng dụng**, không định danh một công việc nghiệp vụ duy nhất. Chạy lại sẽ có lần thực thi mới.

| Giá trị | Ví dụ | Mục đích | Ổn định giữa các retry? |
|---|---|---|---|
| `TaskExecutionId` | `8191`, `8192` | Tra cứu lịch sử mỗi lần chạy trong TaskRepository | Không |
| ID của Pod hoặc Job | `close-day-kx7kq` | Quan sát lần thực thi của scheduler | Thường không |
| UUID tạo mới lúc runner chạy | `a3bf...` | Tracing kỹ thuật | Không |
| **Khóa nghiệp vụ** | `tenant-A / CLOSE_DAY / 2026-11-23 / revision-1` | Định danh ý định cần có hiệu lực duy nhất | **Có** |
| `eventId` từ hệ thống nguồn | `evt-1051` | Dedupe một event cụ thể | Có, nếu upstream tái sử dụng event ID khi redelivery |

Với chốt doanh thu theo ngày, khóa có thể là bộ:

~~~text
(tenant_id, operation_type, business_date, revision)
= (tenant-A, CLOSE_DAY, 2026-11-23, 1)
~~~

Với nhập hóa đơn, khóa có thể là `tenantId + sourceSystem + externalInvoiceId`. Với đồng bộ thay đổi dữ liệu, khóa có thể là `source + entityId + sourceVersion`.

**Khóa phải mô tả chính xác “khi nào hai yêu cầu được xem là cùng một ý định”.** Thường cần thêm tenant, nguồn, loại tác vụ hoặc phiên bản xử lý để tránh xung đột giả. Tuy nhiên, thêm `runAt`, thời điểm hiện tại, UUID ngẫu nhiên hoặc TaskExecutionId sẽ khiến retry thành **khóa mới**, làm mất tác dụng chống lặp.

### Ba tình huống phải phân biệt

| Tình huống | Khóa nên dùng |
|---|---|
| Retry do timeout/lỗi tạm thời | **Giữ nguyên khóa** của lần đầu |
| Chạy bù một kỳ chưa xử lý xong | Dùng khóa của **kỳ cần chạy bù**, không dùng ngày hiện tại |
| Tính lại vì dữ liệu hoặc quy tắc đã sửa | Dùng **revision mới có chủ đích** nếu chính sách cho phép |

Không tăng revision chỉ để “né” lỗi unique key. Revision thể hiện một nghiệp vụ mới theo quy tắc rõ ràng, ví dụ thay thế hoặc điều chỉnh báo cáo đã phát hành.

## 3. Đặc điểm của một khóa nghiệp vụ tốt

Một khóa idempotency hữu ích cần đáp ứng các điều kiện:

1. **Ổn định:** cùng một yêu cầu nghiệp vụ tạo ra cùng khóa ở mọi lần chạy, kể cả qua nhiều JVM.
2. **Đúng phạm vi:** hai tenant khác nhau không chặn nhầm nhau; hai loại tác vụ khác nhau không chia sẻ khóa nếu có thể xử lý độc lập.
3. **Đủ phân biệt:** hai ý định thực sự khác nhau không bị gom làm một.
4. **Không phụ thuộc runtime:** không dùng ID Pod, thread, TaskExecutionId hoặc timestamp mới phát sinh.
5. **Có nơi lưu bền vững:** quy tắc duy nhất được cưỡng chế trong database hoặc một dịch vụ lưu idempotency tương đương.
6. **Có chính sách giữ dữ liệu:** không xóa trạng thái dedupe quá sớm khi vẫn có khả năng message/request được gửi lại.
7. **Không lộ bí mật:** có thể ghi log mã correlation hoặc bản hash đã được chọn lọc, tránh ghi dữ liệu nhận dạng nhạy cảm không cần thiết.

Cũng cần xác định **thời gian hiệu lực** của khóa. Khóa dedupe cho event đã phát hành có thể cần tồn tại lâu hơn TTL của hệ điều phối; khóa API của bên thứ ba có thể có hạn lưu ngắn hơn. Nếu TTL hết mà yêu cầu cũ vẫn được retry, hiệu ứng trùng có thể xảy ra.

## 4. Không thể chỉ SELECT rồi INSERT

Mẫu dễ mắc lỗi:

~~~java
if (!repository.existsByBusinessKey(key)) {
    repository.createResult(result);
}
~~~

Hai phiên chạy đồng thời đều có thể quan sát “chưa tồn tại” trước khi một phiên kịp ghi.

~~~mermaid
sequenceDiagram
    participant A as TaskExecution 101
    participant B as TaskExecution 102
    participant DB as Business Database
    A->>DB: SELECT key -> không có
    B->>DB: SELECT key -> không có
    A->>DB: INSERT key
    B->>DB: INSERT key
    Note over A,DB: Không có UNIQUE thì có thể ghi trùng
~~~

**Cần bảo vệ ở ranh giới commit bằng `PRIMARY KEY` hoặc `UNIQUE`**, thay vì chỉ kiểm tra trước trên ứng dụng.

Ví dụ PostgreSQL cho một lần đóng sổ doanh thu:

~~~sql
CREATE SCHEMA IF NOT EXISTS finance;

CREATE TABLE finance.daily_revenue_close (
    tenant_id            VARCHAR(64) NOT NULL,
    business_date        DATE NOT NULL,
    revision             INTEGER NOT NULL CHECK (revision > 0),
    request_fingerprint  CHAR(64) NOT NULL,
    total_amount         NUMERIC(19, 2) NOT NULL,
    completed_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_daily_revenue_close
        PRIMARY KEY (tenant_id, business_date, revision)
);
~~~

Khóa chính có nghĩa: **mỗi tenant, mỗi ngày, mỗi revision chỉ có một kết quả có hiệu lực**. Nếu yêu cầu sinh nhiều bản ghi chi tiết, hãy áp dụng unique key tương ứng và thiết kế transaction nhất quán cho cả bảng tổng lẫn bảng chi tiết.

Constraint không cản việc tạo nhiều TaskExecution; nó bảo vệ **bảng kết quả nghiệp vụ**. Các TaskExecution vẫn cần được lưu độc lập để biết có bao nhiêu attempt đã diễn ra.

## 5. Thêm fingerprint để không “bỏ qua nhầm” dữ liệu khác

Một số hệ thống nhận **cùng business key nhưng nội dung đã thay đổi**. Nếu chỉ nhìn khóa và trả “đã xử lý”, dữ liệu bị sửa có thể bị che giấu.

| Yêu cầu | Business key | Fingerprint | Hành vi đúng |
|---|---|---|---|
| Chạy lần đầu | `tenant-A/date-23/rev-1` | `abc...` | Ghi kết quả |
| Retry cùng dữ liệu | `tenant-A/date-23/rev-1` | `abc...` | Tái sử dụng kết quả cũ |
| Cùng key nhưng nguồn đã sửa | `tenant-A/date-23/rev-1` | `def...` | Báo **conflict** |
| Tính lại hợp lệ | `tenant-A/date-23/rev-2` | `def...` | Xử lý theo chính sách revision mới |

**Fingerprint** có thể là SHA-256 của một biểu diễn chuẩn hóa của request/snapshot đầu vào. Cần cố định thứ tự field, chuẩn thời gian, cách làm tròn số tiền, cách sắp xếp tập bản ghi và phiên bản quy tắc tính toán.

Không thêm timestamp lần chạy hoặc trace ID vào fingerprint, vì chúng thay đổi mỗi lần retry. Cũng không xem hash là giải pháp thay thế cho unique constraint hay cho kiểm tra quyền tenant.

Nếu dữ liệu nguồn thay đổi liên tục, phải xác định **snapshot/cutoff** rõ ràng. Không thể hứa kết quả tính lại “giống hệt” nếu attempt đầu và attempt sau đọc hai thời điểm dữ liệu khác nhau mà không có chính sách revision.

## 6. Chiến lược atomic insert-or-reuse

Với tác vụ ghi kết quả trong **cùng một CSDL**, có thể dùng một transaction để chèn kết quả hoặc đọc lại kết quả đã có:

~~~mermaid
flowchart TD
    A["Runner nhận business key"] --> B["Chuẩn hóa input, tính fingerprint"]
    B --> C["INSERT ... ON CONFLICT DO NOTHING"]
    C --> D{"Có chèn được một bản ghi?"}
    D -- Có --> E["Commit kết quả mới"]
    D -- Không --> F["SELECT kết quả đã tồn tại"]
    F --> G{"Fingerprint có khớp?"}
    G -- Có --> H["REUSED / ALREADY_APPLIED"]
    G -- Không --> I["CONFLICT: dừng và điều tra"]
~~~

PostgreSQL cho phép:

~~~sql
INSERT INTO finance.daily_revenue_close (
    tenant_id, business_date, revision,
    request_fingerprint, total_amount
)
VALUES (
    :tenant_id, :business_date, :revision,
    :request_fingerprint, :total_amount
)
ON CONFLICT (tenant_id, business_date, revision)
DO NOTHING;
~~~

`ON CONFLICT DO NOTHING` khiến lần ghi trùng không thêm kết quả, **nhưng không tự đối chiếu fingerprint**. Nếu logic còn phải ghi bảng chi tiết, hãy thực hiện nó **trong cùng transaction** hoặc dùng mô hình checkpoint nhất quán.

Ở PostgreSQL `READ COMMITTED`, một lệnh insert concurrent có thể chờ transaction đang giữ unique key; sau khi conflict được xác định, một `SELECT` tiếp theo có thể nhìn thấy bản ghi đã commit. Ở các mức cách ly hoặc dialect khác, phải xét lỗi serialization/deadlock và retry transaction phù hợp.

## 7. Ví dụ Spring Boot: service lưu kết quả đúng một lần

Ví dụ Java 17 và Spring JDBC sau đây minh họa tính idempotent của **một kết quả chốt doanh thu trong PostgreSQL**. Hệ thống thực tế cần cài đặt cách tính tổng và fingerprint từ snapshot đầu vào.

### Model và kết quả

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;

public record CloseDayCommand(
        String tenantId,
        LocalDate businessDate,
        int revision,
        String fingerprint,
        BigDecimal totalAmount) {
}

public record CloseDayResult(
        boolean newlyApplied,
        BigDecimal totalAmount) {
}

public class IdempotencyConflictException extends RuntimeException {
    public IdempotencyConflictException(String message) {
        super(message);
    }
}
~~~

### Persistence service

~~~java
import java.sql.Date;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CloseDayPersistenceService {

    private final JdbcTemplate jdbc;

    public CloseDayPersistenceService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public CloseDayResult saveOnce(CloseDayCommand command) {
        int inserted = jdbc.update("""
            INSERT INTO finance.daily_revenue_close (
                tenant_id, business_date, revision,
                request_fingerprint, total_amount
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (tenant_id, business_date, revision)
            DO NOTHING
            """,
            command.tenantId(),
            Date.valueOf(command.businessDate()),
            command.revision(),
            command.fingerprint(),
            command.totalAmount()
        );

        if (inserted == 1) {
            return new CloseDayResult(true, command.totalAmount());
        }

        return jdbc.queryForObject("""
            SELECT request_fingerprint, total_amount
            FROM finance.daily_revenue_close
            WHERE tenant_id = ?
              AND business_date = ?
              AND revision = ?
            """,
            (rs, rowNum) -> {
                String savedHash =
                    rs.getString("request_fingerprint").trim();

                if (!Objects.equals(
                        savedHash, command.fingerprint())) {
                    throw new IdempotencyConflictException(
                        "Same business key with different input");
                }

                return new CloseDayResult(
                    false, rs.getBigDecimal("total_amount"));
            },
            command.tenantId(),
            Date.valueOf(command.businessDate()),
            command.revision()
        );
    }
}
~~~

**Ý nghĩa:**

- `PRIMARY KEY` bảo đảm hai transaction không commit hai kết quả có cùng business key.
- Attempt đầu tạo được bản ghi sẽ nhận `newlyApplied=true`; lần chạy lại cùng fingerprint trả dữ liệu đã lưu.
- Nếu cùng key nhưng fingerprint khác, service ném exception rõ ràng thay vì âm thầm coi là hoàn tất.
- `@Transactional` cần transaction manager của **đúng DataSource**. Đừng gọi method qua `this.saveOnce(...)` trong chính bean nếu đang phụ thuộc Spring proxy.
- Ví dụ chỉ bảo vệ **bản ghi đã được insert**. Bất kỳ lời gọi HTTP, ghi file hoặc publish message thực hiện sau đó cần biện pháp riêng.

Giả định `fingerprint` đã được validate thành chuỗi 64 ký tự hex, dữ liệu kết quả thuộc một snapshot nguồn được xác định và transaction sử dụng mức cách ly phù hợp. Với MySQL/SQL Server/Oracle, cú pháp upsert cần thay theo dialect.

### Runner của Spring Cloud Task

~~~java
import java.time.LocalDate;
import java.util.List;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CloseDayRunnerConfig {

    @Bean
    ApplicationRunner closeDayRunner(CloseDayJobService jobService) {
        return args -> {
            List<String> dates = args.getOptionValues("date");

            if (dates == null || dates.size() != 1) {
                throw new IllegalArgumentException(
                    "Can truyen --date=yyyy-MM-dd");
            }

            LocalDate date = LocalDate.parse(dates.get(0));

            // Service tạo fingerprint ổn định và gọi saveOnce.
            jobService.run("tenant-A", date, 1);
        };
    }
}
~~~

`CloseDayJobService` là service nghiệp vụ cần có trong ứng dụng; nó chuẩn bị dữ liệu, fingerprint và gọi `CloseDayPersistenceService`. Khi triển khai thật, tenant cần được đọc từ nguồn tin cậy và kiểm tra quyền; code chỉ minh họa điểm vào nghiệp vụ.

~~~bash
java -jar close-day-task.jar --date=2026-11-23
~~~

Lệnh chạy lại cùng input không tạo thêm kết quả. Nếu lần đầu commit thành công rồi JVM chết trước khi TaskRepository cập nhật `END_TIME`, lần chạy thứ hai vẫn có thể nhận ra business key đã hoàn tất.

## 8. Race condition giữa hai JVM và vai trò transaction

Giả sử hai CronJob cùng chạy ngày `2026-11-23`:

~~~mermaid
sequenceDiagram
    participant A as Task A / JVM 1
    participant B as Task B / JVM 2
    participant DB as Business Database
    A->>DB: INSERT business key
    B->>DB: INSERT cùng key
    DB-->>A: inserted=1
    DB-->>B: inserted=0 sau xử lý conflict
    B->>DB: SELECT fingerprint và kết quả
    DB-->>B: Kết quả đã commit
    Note over A,B: Cả hai TaskExecution vẫn được theo dõi riêng
~~~

Kết quả thực tế phụ thuộc lịch commit: nếu A rollback, B có thể trở thành bên insert thành công. Unique constraint mới là ranh giới bảo vệ dữ liệu. `synchronized` hoặc `ReentrantLock` trong JVM **không bảo vệ** được hai container riêng biệt.

Không được coi mọi lỗi SQL là “duplicate đã thành công”. Timeout, connection loss, serialization failure và deadlock có cơ chế xử lý khác nhau. Khi trạng thái ghi chưa chắc chắn, đọc lại bằng khóa nghiệp vụ trước khi quyết định retry.

## 9. Công việc nhiều bước: claim, lease và fencing

Nếu một task xử lý hàng trăm nghìn bản ghi hoặc kéo dài hàng giờ, giữ transaction duy nhất toàn bộ thời gian là thiết kế không phù hợp. Có thể lưu tiến độ theo **đơn vị commit** và dùng bảng công việc có khóa nghiệp vụ:

~~~sql
CREATE SCHEMA IF NOT EXISTS workflow;

CREATE TABLE workflow.task_claim (
    tenant_id           VARCHAR(64) NOT NULL,
    business_key        VARCHAR(200) NOT NULL,
    request_fingerprint CHAR(64) NOT NULL,
    status              VARCHAR(20) NOT NULL,
    owner_token         UUID,
    lease_until         TIMESTAMPTZ,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (tenant_id, business_key),
    CONSTRAINT ck_claim_status CHECK (
        status IN ('PENDING', 'PROCESSING', 'SUCCEEDED', 'FAILED')
    )
);
~~~

Luồng xử lý:

1. Tạo claim bằng `INSERT ... ON CONFLICT` với business key; nếu đã tồn tại, kiểm tra fingerprint.
2. Worker **claim atomically** từ `PENDING`/`FAILED` hoặc từ claim `PROCESSING` đã hết lease.
3. Worker xử lý từng phân vùng và lưu checkpoint sau commit.
4. Worker gia hạn lease khi còn sống; trước khi hoàn tất cần kiểm tra quyền sở hữu.
5. Khi crash, coordinator chỉ cho worker mới tiếp quản theo chính sách timeout và đối chiếu trạng thái.

Ví dụ claim bản ghi đã có (PostgreSQL):

~~~sql
UPDATE workflow.task_claim
SET status = 'PROCESSING',
    owner_token = :new_owner_token,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    attempt_count = attempt_count + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = :tenant_id
  AND business_key = :business_key
  AND status <> 'SUCCEEDED'
  AND (
       status IN ('PENDING', 'FAILED')
       OR (
           status = 'PROCESSING'
           AND lease_until < CURRENT_TIMESTAMP
       )
  )
RETURNING owner_token, attempt_count;
~~~

Không có dòng trả về nghĩa là worker **chưa nhận quyền**. Không được xử lý nghiệp vụ như thể claim thành công. Với `PROCESSING` còn lease, nên quan sát/chờ; với `SUCCEEDED` và fingerprint trùng, trả kết quả cũ.

Lệnh hoàn tất cũng cần kiểm tra owner token và lease:

~~~sql
UPDATE workflow.task_claim
SET status = 'SUCCEEDED',
    owner_token = NULL,
    lease_until = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = :tenant_id
  AND business_key = :business_key
  AND status = 'PROCESSING'
  AND owner_token = :owner_token
  AND lease_until > CURRENT_TIMESTAMP;
~~~

Kiểm tra số dòng thay đổi. Nếu bằng 0, worker không còn quyền hoàn tất.

**Lease không tự ngăn tác động trùng:** worker A có thể bị pause, lease hết hạn, B tiếp quản; sau đó A chạy tiếp. Trong hệ thống yêu cầu mạnh, sử dụng **fencing token tăng đơn điệu** hoặc `ownership_version` được kiểm tra trong các thao tác ghi. Đối với API bên ngoài, bên nhận cũng phải hỗ trợ idempotency/fencing hoặc có cơ chế đối soát.

## 10. Side effect bên ngoài: outbox và idempotency key

Một JDBC transaction không bao trùm lời gọi HTTP, ghi object storage, email hay publish message.

Ví dụ hệ thống đã commit đơn hàng vào CSDL và gửi yêu cầu tạo hóa đơn qua API. Nếu API nhận yêu cầu nhưng JVM chết trước khi ghi phản hồi, retry có thể phát hành thêm hóa đơn.

Giải pháp phổ biến là **transactional outbox**:

~~~mermaid
flowchart LR
    A["Spring Cloud Task"] --> T["Transaction nội bộ"]
    T --> B["Ghi dữ liệu nghiệp vụ"]
    T --> O["Ghi outbox event"]
    B --> C["COMMIT"]
    O --> C
    C --> R["Outbox relay"]
    R --> M["Broker / external API"]
    M --> D["Bên nhận dedupe theo eventId hoặc business key"]
~~~

Trong cùng transaction, lưu kết quả nghiệp vụ và outbox event. Relay có thể phát lại sau crash, vì vậy bên nhận **phải idempotent**. Có thể thiết kế outbox:

~~~sql
CREATE TABLE workflow.outbox_event (
    event_id      UUID PRIMARY KEY,
    tenant_id     VARCHAR(64) NOT NULL,
    business_key  VARCHAR(200) NOT NULL,
    event_type    VARCHAR(64) NOT NULL,
    payload       JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at  TIMESTAMPTZ
);
~~~

Nếu hai attempt cùng nghiệp vụ tạo hai `event_id` khác nhau, cần thêm một unique key tương ứng với ý định logic (chẳng hạn `tenant_id, business_key, event_type`) hoặc tạo event ID xác định. `eventId` của message và idempotency key bên thứ ba phải được tái sử dụng khi retry theo hợp đồng API.

**Không có bảo đảm exactly-once toàn bộ hệ thống** chỉ nhờ outbox. Broker có thể giao ít nhất một lần, relay có thể publish lại, API có TTL cho idempotency key. Phải xác định ranh giới nào có dedupe và thời gian hiệu lực bao lâu.

## 11. Spring Cloud Task, Spring Batch và dữ liệu nghiệp vụ

| Thành phần | Theo dõi | Có tự chống ghi trùng nghiệp vụ? |
|---|---|---|
| `TaskRepository` của Spring Cloud Task | `TaskExecutionId`, start/end, exit code của **mỗi lần chạy ứng dụng** | Không |
| `JobRepository` của Spring Batch | `JobInstance`, `JobExecution`, `StepExecution`, checkpoint | Không tự bảo vệ mọi side effect ngoài transaction |
| Bảng nghiệp vụ có unique key | Kết quả cuối theo business key | Có, trong phạm vi constraint và transaction |
| Bảng claim/checkpoint | Tiến độ, quyền sở hữu và phần việc đã commit | Có khi thiết kế đúng |
| Outbox/consumer idempotent | Event và tác động tới hệ thống ngoài | Trong phạm vi ranh giới đã triển khai |

Với Spring Batch, các **identifying JobParameters** cùng tên job giúp xác định JobInstance và phục vụ restart theo cơ chế Batch. Nhưng nếu mỗi lần chạy thêm `run.id` mới làm identifying parameter, job instance cũng thay đổi. Vì vậy business key vẫn phải được đưa vào thiết kế dữ liệu, kể cả khi Batch có checkpoint.

Ví dụ hai lần chạy:

~~~text
TaskExecution 8191 -> CLOSE_DAY tenant-A, date=2026-11-23, rev=1
TaskExecution 8192 -> CLOSE_DAY tenant-A, date=2026-11-23, rev=1

Business database:
  (tenant-A, 2026-11-23, revision=1) -> một kết quả có hiệu lực
~~~

Khi JVM chết sau commit nhưng trước lúc `TaskRepository` cập nhật trạng thái, TaskExecution đầu có thể chưa có `END_TIME`. Retry phải kiểm tra **business state** trước khi ghi lại; không dùng riêng trạng thái TaskRepository để quyết định nghiệp vụ đã thực hiện hay chưa.

## 12. Phân loại lỗi và quy tắc retry

Idempotency làm retry an toàn hơn, nhưng không biến mọi lỗi thành lỗi nên thử lại.

| Tình huống | Phản ứng phù hợp |
|---|---|
| Timeout kết nối, lỗi DB tạm thời | Retry có giới hạn với backoff/jitter, giữ nguyên key |
| Unique key trùng, fingerprint giống | Trả `ALREADY_APPLIED` và kết quả cũ |
| Unique key trùng, fingerprint khác | Báo `CONFLICT`; không ghi đè |
| Input sai hoặc không có quyền | Fail-fast; không retry y hệt vô hạn |
| Claim đang xử lý, lease chưa hết | Chờ/quan sát, không giành việc |
| Lease hết hạn | Kiểm tra và takeover có fencing/checkpoint |
| Không rõ API bên ngoài đã xử lý chưa | Query trạng thái bằng idempotency key, đối soát hoặc outbox |
| TaskExecution chưa có END_TIME | Đối chiếu process, log, dữ liệu nghiệp vụ rồi quyết định |
| Không còn khả năng retry | Ghi nhận trạng thái thất bại, cảnh báo và bảo toàn dấu vết |

Retry cần **số lần tối đa**, backoff, jitter, timeout và thông tin điều tra. Không đổi business key hoặc revision chỉ vì muốn một lần retry chạy được.

~~~text
Transient failure -> backoff -> retry SAME business key
Permanent failure -> stop, alert, preserve evidence
Duplicate + same fingerprint -> return old result
Duplicate + different fingerprint -> explicit conflict
Unknown external outcome -> reconcile before replay
~~~

## 13. Kiểm thử cả hai tiến trình và tình huống crash

Kiểm thử một task chạy hai lần tuần tự chỉ xác minh được một phần yêu cầu. Cần thử:

| Kịch bản | Kết quả kỳ vọng |
|---|---|
| Lần chạy đầu | Có đúng một kết quả được commit |
| Retry với cùng key/fingerprint | Không ghi thêm; trả kết quả cũ |
| Cùng key nhưng fingerprint khác | Báo conflict |
| Hai JVM cùng xử lý key | Unique constraint chỉ cho một dòng có hiệu lực |
| Crash trước commit | Transaction rollback; retry có thể tiếp tục |
| Crash sau commit, trước TaskRepository end | Retry nhận biết kết quả đã tồn tại |
| Worker A hết lease, B tiếp quản | A mất quyền sở hữu; không commit kết quả trùng |
| Publish event rồi không nhận ACK | Consumer xử lý duplicate bằng eventId/business key |
| Hai tenant cùng ngày | Không chặn nhầm giữa hai tenant |
| Reprocess theo revision mới | Có bản revision mới hợp lệ theo chính sách |

Ví dụ truy vấn kiểm tra:

~~~sql
SELECT tenant_id, business_date, revision, COUNT(*) AS row_count
FROM finance.daily_revenue_close
GROUP BY tenant_id, business_date, revision
HAVING COUNT(*) > 1;
~~~

Với primary key đã triển khai đúng, truy vấn phải trả **không dòng nào**. Nhưng điều đó chưa chứng minh side effect bên ngoài không bị lặp; cần đối chiếu hệ thống nhận, outbox và kết quả nghiệp vụ.

Một bài thực hành:

1. Tạo schema/bảng bằng migration và ràng buộc unique theo business key.
2. Cấu hình Spring Cloud Task với `ApplicationRunner` nhận ngày xử lý; dùng `TaskRepository` bền vững.
3. Gọi service `saveOnce` và log business key, `TaskExecutionId`, trạng thái `APPLIED/REUSED`.
4. Chạy đồng thời hai tiến trình cho cùng ngày, rồi truy vấn bảng kết quả.
5. Diễn tập kill sau commit; chạy lại cùng tham số.
6. Thay đổi input nhưng giữ revision và xác nhận hệ thống báo conflict.
7. Thử quy trình xuất event và tiêu chí xử lý trùng ở consumer.

Không cần thêm bộ kiểm thử khổng lồ nếu chưa có yêu cầu triển khai thực tế, nhưng các kịch bản trên nên được kiểm chứng trước khi cho phép retry tự động trong production.

## 14. Lỗi thiết kế thường gặp

### “TaskExecutionId là khóa idempotency”

**Sai.** Nó thay đổi ở mỗi lần khởi chạy. Nó thích hợp cho audit attempt và correlation, không để định nghĩa một ý định nghiệp vụ.

### “SELECT EXISTS rồi INSERT là đủ”

**Sai khi concurrent.** Hai transaction có thể cùng thấy chưa có dữ liệu. Dùng unique constraint, upsert và transaction.

### “ON CONFLICT DO NOTHING giải quyết mọi thứ”

**Chưa đủ.** Phải phân biệt cùng key/cùng dữ liệu với cùng key/khác dữ liệu. Lời gọi API, file và event bên ngoài cần bảo vệ riêng.

### “Có PROCESSING thì sẽ không bao giờ chạy trùng”

**Không đúng.** Worker có thể chết mà để lại claim, hoặc sống lại sau khi lease hết hạn. Cần timeout, quyền sở hữu, fencing và checkpoint.

### “Spring Batch restart bảo đảm exactly-once”

**Không tự động.** Batch hỗ trợ trạng thái job/step và checkpoint, nhưng các side effect ngoài transaction và quy tắc nghiệp vụ vẫn cần idempotency.

### “Đổi revision để tránh unique conflict”

**Sai.** Revision là thay đổi nghiệp vụ có chủ đích; tự tăng khi retry tạo ra nhiều kết quả không được yêu cầu.

## 15. Checklist thiết kế trước khi vận hành

| Câu hỏi | Điều kiện đạt |
|---|---|
| Đã định nghĩa “cùng ý định” rõ ràng? | Business key ổn định và có phạm vi tenant/loại/kỳ/version phù hợp |
| Có ràng buộc khóa ở nơi commit? | `PRIMARY KEY` hoặc `UNIQUE` |
| Có phân biệt cùng key nhưng dữ liệu khác? | Fingerprint/snapshot và conflict policy |
| Các bảng nghiệp vụ có nhất quán? | Transaction/constraint cho cả dữ liệu tổng, chi tiết và checkpoint |
| Chạy đồng thời nhiều JVM có an toàn? | Test race và retry DB phù hợp |
| Có tác động tới hệ thống ngoài? | Idempotency key, outbox, consumer dedupe hoặc đối soát |
| Có tác vụ dài? | Claim/lease, fencing, heartbeat, checkpoint |
| Retry có kiểm soát? | Backoff/jitter, timeout, số attempt tối đa và phân loại lỗi |
| Có nhầm TaskRepository với business state? | Tách metadata attempt và kết quả nghiệp vụ, liên kết bằng correlation ID |
| Có xử lý crash sau commit? | Retry đọc business key trước khi tạo tác động mới |
| Có quy tắc reprocess dữ liệu đã sửa? | Revision rõ ràng và quyết định bản nào có hiệu lực |

**Kết luận:** Một Spring Cloud Task có thể được chạy lại nhiều lần vì lỗi, timeout hoặc yêu cầu vận hành. Muốn kết quả nghiệp vụ không bị nhân đôi, cần **khóa nghiệp vụ ổn định**, **ràng buộc duy nhất tại ranh giới commit**, **fingerprint để phát hiện dữ liệu thay đổi**, và **quy tắc retry/concurrency minh bạch**. `TaskRepository` lưu từng lần thực thi; bảng nghiệp vụ, checkpoint và outbox bảo vệ hiệu ứng thực tế. Khi phối hợp hai lớp này, ứng dụng có thể chạy theo lịch hoặc theo yêu cầu và phục hồi an toàn sau sự cố.

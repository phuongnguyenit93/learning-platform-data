# Giới hạn lịch cục bộ khi ứng dụng có nhiều bản sao

## 1. Vấn đề: một lịch, nhiều JVM cùng thực hiện

Trong một dịch vụ **Spring Boot Integration**, tác vụ định kỳ có thể gọi HTTP API đối tác để đối soát, quét bản ghi outbox để phát Kafka, làm mới cache hoặc đồng bộ dữ liệu từ cơ sở dữ liệu. Với một ứng dụng chạy trên máy cá nhân, lập lịch bằng `@Scheduled` thường đủ đơn giản. Nhưng khi triển khai ba bản sao (replica) sau load balancer, mỗi JVM tự có **bộ lập lịch cục bộ** và không biết replica khác đã thực hiện tác vụ hay chưa.

Ví dụ, cùng một bản build được chạy trên ba pod, mỗi pod có bean sau:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ReconciliationTimer {
    @Scheduled(cron = "0 0 2 * * *", zone = "UTC")
    public void reconcile() {
        // Đồng bộ đối soát đơn hàng với hệ thống bên ngoài.
    }
}
~~~

Lúc 02:00 UTC, **cả ba pod đều có thể gọi `reconcile()`**. Spring không mặc định bầu ra một pod làm leader hay cấp khóa phân tán cho annotation `@Scheduled`. Nếu công việc cập nhật số dư, phát thông điệp hoặc gọi một đối tác có giới hạn API, chạy ba lần có thể tạo dữ liệu trùng, tăng chi phí và làm hỏng trạng thái nghiệp vụ.

~~~mermaid
flowchart TB
    Cron["02:00 UTC: cùng một lịch"] --> A["Replica A: @Scheduled"]
    Cron --> B["Replica B: @Scheduled"]
    Cron --> C["Replica C: @Scheduled"]
    A --> API["Đối tác HTTP / DB / Kafka"]
    B --> API
    C --> API
    DB[("Kho trạng thái chia sẻ")] -. "Chưa có cơ chế điều phối" .-> Cron
~~~

**Mục tiêu bài học:** hiểu phạm vi của lịch cục bộ, các tình huống chạy trùng và bỏ lỡ khi scale hoặc restart, rồi chọn cơ chế phối hợp ở mức cluster. Trọng tâm không chỉ là **một lần kích hoạt**, mà còn là tính nhất quán của dữ liệu, retry, idempotency, kiểm thử lỗi và khả năng quan sát luồng tích hợp.

## 2. `@Scheduled` thực sự bảo đảm điều gì?

Spring xử lý `@Scheduled` trên các bean được quản lý và kích hoạt callback theo cấu hình **trong cùng application context/JVM**. Một ứng dụng thường bật cơ chế này bằng `@EnableScheduling`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class SchedulingConfiguration {
}
~~~

Một số cách định lịch thông dụng:

| Cơ chế | Nguyên tắc | Rủi ro khi có nhiều replica |
|---|---|---|
| `@Scheduled(fixedRate = ...)` | Mỗi chu kỳ tính tương đối theo mốc bắt đầu lần chạy trước, tùy scheduler và khả năng thực thi | Mỗi replica có chu kỳ riêng; tổng số lần có thể tăng theo replica |
| `@Scheduled(fixedDelay = ...)` | Đợi một khoảng sau khi lần thực thi trước trên scheduler đó kết thúc | Chỉ kiểm soát các lần gọi trong phạm vi cục bộ |
| `@Scheduled(cron = "...")` | Kích hoạt tại các thời điểm khớp biểu thức cron | Tất cả replica đều có thể cùng khớp một thời điểm |
| `initialDelay` | Trì hoãn lần chạy đầu sau khi khởi tạo | Không tạo cơ chế bầu leader hay lưu trạng thái lịch toàn cluster |

Một số chi tiết cần nắm:

- **Lịch được cấu hình cho mỗi instance.** Scale từ một lên năm replica có thể tạo năm lần thực thi cùng lịch.
- **Pool của scheduler là cục bộ.** Tăng `spring.task.scheduling.pool.size` giúp xử lý các tác vụ trong một JVM, nhưng không giải quyết chạy trùng giữa các JVM. Với callback có thể overlap hoặc nhiều annotation/lịch trên cùng tác vụ, cần kiểm soát cả cạnh tranh nội bộ.
- **`@Async` không thay thế scheduler phân tán.** `@Async` chuyển công việc sang executor của JVM, không làm lịch chỉ chạy trên một replica và cũng không bảo đảm tác vụ sống sót khi tiến trình bị dừng.
- **Không có kho lịch sử bền vững mặc định.** Nếu ứng dụng không chạy đúng thời điểm cron, một lần kích hoạt có thể bị bỏ qua; chỉ thêm replica không tạo khả năng replay lịch đã mất.
- **Cron có múi giờ.** Khai báo `zone` tường minh để tránh khác nhau do cấu hình hệ điều hành; khi lịch theo múi giờ địa phương, phải xét giờ mùa hè (DST) tại những khu vực áp dụng.

Vì vậy, `@Scheduled` là **cơ chế tạo tín hiệu thời gian tại mỗi instance**, chưa phải cơ chế bảo đảm một công việc nghiệp vụ chỉ được nhận hoặc hoàn thành đúng một lần trên toàn cluster.

## 3. Những lỗi dễ xuất hiện khi triển khai nhiều bản sao

### 3.1. Chạy trùng theo lịch

Giả sử scheduler gửi yêu cầu `POST /partner/settlements` lúc 02:00. Nếu cả ba replica thực hiện và API đối tác không hỗ trợ idempotency key, có thể phát sinh ba phiên đối soát. Dùng `synchronized`, `ReentrantLock` hoặc biến `AtomicBoolean` chỉ khóa trong một JVM; các replica khác vẫn thực hiện độc lập.

### 3.2. Bỏ lỡ lần chạy khi không có instance nào sống

Đúng giờ cron, hệ thống đang nâng cấp và toàn bộ replica tạm ngừng. Khi pod mới khởi động lúc 02:05, `@Scheduled` thông thường **không tự chạy bù** slot 02:00 vừa qua. Nếu đối soát theo ngày, cần lưu lịch/slot công việc vào cơ sở dữ liệu, bổ sung catch-up logic hoặc dùng scheduler có khả năng lưu lịch sử và chính sách misfire.

### 3.3. Hai bản sao cũ và mới cùng tồn tại khi rolling deployment

Replica chạy phiên bản A còn sống trong lúc replica phiên bản B được khởi tạo. Cả hai có thể bắt cùng thời điểm cron, thậm chí xử lý dữ liệu theo hai hợp đồng khác nhau. Hạ tầng rolling update không tạo ra ranh giới giao dịch cho một tác vụ nghiệp vụ.

### 3.4. Tác vụ chạy lâu hơn khoảng lặp

Một tác vụ quét dữ liệu cần 20 phút nhưng lịch đặt 5 phút. Nếu đồng thời có nhiều replica, lượng công việc chồng lấn có thể tăng rất nhanh. Ngay cả khi scheduler cục bộ tuần tự hóa callback, mỗi JVM vẫn có một tác vụ của riêng mình. Cần phân biệt **không overlap** với **không chạy trùng mục đích nghiệp vụ**.

### 3.5. Tiến trình chết giữa xử lý và xác nhận thành công

Nếu replica A gọi Kafka hoặc HTTP thành công rồi chết trước khi đánh dấu công việc hoàn tất trong database, replica B có thể thực hiện lại. Khóa phân tán giúp điều phối người thực thi, nhưng **không tự khiến tác dụng phụ bên ngoài database trở thành đúng một lần**.

| Thời điểm lỗi | Hậu quả có thể xảy ra | Cơ chế cần thiết |
|---|---|---|
| Mọi replica tắt lúc cron kích hoạt | Bỏ lỡ slot | Lưu lịch/slot, cơ chế chạy bù |
| Nhiều replica bật đúng lúc | Chạy trùng | Claim/lock chung, một scheduler trung tâm |
| Công việc lâu, khóa hết hạn | Worker mới nhận lại khi worker cũ còn chạy | Lease renewal, token thế hệ (*fencing*), idempotency |
| API bên ngoài nhận request rồi trả timeout | Không biết tác dụng phụ đã xảy ra chưa | Idempotency key, đối soát kết quả, retry có kiểm soát |
| DB commit nhưng Kafka chưa gửi | Thiếu sự kiện downstream | Transactional outbox và relay |
| Kafka đã nhận, worker chưa đánh dấu xong | Phát lại event | `eventId` ổn định, idempotent consumer |

## 4. Xác định đúng yêu cầu trước khi chọn giải pháp

Ba mục tiêu sau thường bị nhầm lẫn:

1. **Chỉ một instance bắt đầu một slot lịch** (*single trigger*): điều phối xem instance nào được phép bắt đầu.
2. **Công việc cuối cùng được hoàn tất dù gặp lỗi** (*at-least-once execution*): cần lưu trạng thái, phát hiện timeout, retry và chạy bù.
3. **Tác dụng phụ nghiệp vụ chỉ được áp dụng một lần** (*effectively-once business effect*): cần idempotency, khóa unique/điều kiện cập nhật và cơ chế xử lý lỗi ở hệ thống đích.

Khóa phân tán thường chỉ giải quyết mục tiêu thứ nhất trong điều kiện thông thường. Nếu worker cũ bị chậm, mất kết nối với kho khóa, rồi tiếp tục gọi API sau khi khóa đã hết hạn, worker mới cũng có thể thực hiện. Để bảo vệ nghiệp vụ, phải thiết kế thêm hai mục tiêu còn lại.

Chọn độ hạt của công việc cho phù hợp:

- **Theo slot thời gian:** `reconcile:2026-11-21`, dùng để đối soát đúng một ngày.
- **Theo đối tượng:** `customer:42:report:2026-11`, dùng để lập báo cáo từng khách hàng.
- **Theo sự kiện:** `eventId` hoặc `orderId + eventType + version`, dùng để chống xử lý trùng một message.

Khóa quá rộng (chẳng hạn `all-jobs`) khiến các tác vụ độc lập bị nghẽn; khóa quá hẹp (ID ngẫu nhiên cho mỗi lần retry) không ngăn thực hiện cùng ý định nghiệp vụ.

## 5. Các phương án điều phối ở mức cluster

| Phương án | Cách vận hành | Phù hợp khi | Hạn chế quan trọng |
|---|---|---|---|
| Chỉ dùng `@Scheduled` ở mọi replica | Mỗi JVM tự kích hoạt | Công việc đọc/refresh cho từng instance, không ảnh hưởng khi chạy trùng | Không có điều phối, không tự chạy bù |
| Chỉ bật lịch trên một instance riêng | Một process có vai trò scheduler; worker khác không đặt lịch | Công việc ít, vận hành đơn giản và chấp nhận kế hoạch failover rõ ràng | Instance scheduler chết sẽ ngừng kích hoạt nếu không có failover |
| Distributed lock/claim bằng DB hoặc Redis | Các replica cùng thức dậy; chỉ instance giành được quyền mới xử lý | Muốn giữ `@Scheduled` nhưng bảo vệ một slot hoặc batch dùng chung | Phải xử lý TTL/lease, crash, mất kết nối, retry, idempotency |
| Hàng đợi công việc bền vững trong DB | Scheduler ghi việc cần chạy, worker claim từng job | Muốn backfill, retry và chạy nhiều job song song | Cần thiết kế state machine, lease, giám sát backlog |
| Quartz với JDBC JobStore clustered | Scheduler lưu lịch/trạng thái trong cùng kho JDBC; các node Quartz phối hợp | Nhiều trigger, lịch động, misfire và lịch sử cần được quản lý | Tăng cấu hình, schema Quartz và yêu cầu vận hành |
| Kubernetes CronJob / scheduler hạ tầng | Hạ tầng tạo Job theo lịch, workload là worker chạy rồi kết thúc | Tách tác vụ khỏi service phục vụ HTTP | Job vẫn có thể bị tạo/chạy lại hoặc bỏ lỡ; cần idempotency và kiểm soát lịch |
| Broker/task queue | Một producer tạo công việc, các consumer trong nhóm xử lý/phân phối | Công việc tốn thời gian, cần retry và mở rộng worker | Broker không tự giải quyết nguồn tạo lịch, dedup và hiệu ứng ngoài broker |

**Lựa chọn thực tế:** không có một công cụ phù hợp tất cả. Nếu chỉ cần chống hai replica chạy đồng thời, DB claim có thể đủ. Nếu cần biết mọi slot đã hoàn tất chưa, hãy lưu **công việc hoặc lịch sử slot bền vững**. Nếu công việc dài, cần retry và mở rộng nhiều worker, kiến trúc scheduler tạo job + queue/worker thường dễ vận hành hơn việc để callback cron thực hiện toàn bộ công việc.

## 6. Ví dụ mức cơ bản: dùng khóa unique của PostgreSQL để claim từng ngày

Giả sử hệ thống tích hợp cần đối soát đơn hàng lúc 02:00 UTC mỗi ngày, và mỗi ngày chỉ được **một replica nhận quyền bắt đầu**.

### 6.1. Bảng ghi nhận slot

~~~sql
CREATE TABLE scheduled_run (
    job_name VARCHAR(120) NOT NULL,
    slot_key VARCHAR(32) NOT NULL,
    state VARCHAR(16) NOT NULL
        CHECK (state IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    PRIMARY KEY (job_name, slot_key)
);
~~~

Khóa chính `(job_name, slot_key)` là cơ chế đồng bộ do PostgreSQL thực thi, áp dụng cho **mọi replica dùng cùng database/schema**, không lệ thuộc JVM nào chạy trước.

### 6.2. Triển khai Spring Boot

Ví dụ dưới dùng Spring JDBC để minh họa một thao tác claim nguyên tử:

~~~java
import java.time.LocalDate;
import java.time.ZoneOffset;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DailyReconciliationScheduler {

    private final JdbcTemplate jdbc;
    private final ReconciliationJob reconciliationJob;

    public DailyReconciliationScheduler(
            JdbcTemplate jdbc,
            ReconciliationJob reconciliationJob) {
        this.jdbc = jdbc;
        this.reconciliationJob = reconciliationJob;
    }

    @Scheduled(cron = "0 0 2 * * *", zone = "UTC")
    public void runDaily() {
        LocalDate todayUtc = LocalDate.now(ZoneOffset.UTC);
        String slot = todayUtc.toString();

        int claimed = jdbc.update("""
                INSERT INTO scheduled_run(job_name, slot_key, state)
                VALUES (?, ?, 'RUNNING')
                ON CONFLICT (job_name, slot_key) DO NOTHING
                """, "reconcile-orders", slot);

        if (claimed == 0) {
            return; // Replica khác đã claim slot này.
        }

        try {
            reconciliationJob.runForDate(todayUtc.minusDays(1));
            jdbc.update("""
                    UPDATE scheduled_run
                       SET state = 'SUCCEEDED', finished_at = CURRENT_TIMESTAMP
                     WHERE job_name = ? AND slot_key = ?
                    """, "reconcile-orders", slot);
        } catch (RuntimeException ex) {
            jdbc.update("""
                    UPDATE scheduled_run
                       SET state = 'FAILED', finished_at = CURRENT_TIMESTAMP
                     WHERE job_name = ? AND slot_key = ?
                    """, "reconcile-orders", slot);
            throw ex;
        }
    }
}
~~~

`ReconciliationJob` là service của ứng dụng, cung cấp `void runForDate(LocalDate date)` và chứa logic đối soát. Mã sử dụng `JdbcTemplate` trên **scheduler thread**, không gọi blocking JDBC từ event loop reactive. Nếu ứng dụng truy cập database bằng R2DBC, có thể dùng một repository R2DBC với cùng thao tác insert nguyên tử; cần subscribe/await kết quả theo cách phù hợp với lifecycle của công việc, không bỏ mặc một publisher chưa được thực thi.

**Điều kiện của ví dụ:** câu `INSERT` phải được commit **trước** khi `runForDate` tạo tác dụng phụ. Ví dụ không đặt `@Transactional` bao quanh cả callback; với JDBC mặc định, mỗi `jdbc.update` tự commit nếu không có transaction Spring đang hoạt động. Nếu gom claim và lời gọi HTTP/Kafka trong cùng transaction database dài, replica khác có thể chờ khóa, giảm throughput và làm tình huống lỗi khó xử lý.

### 6.3. Bảo đảm và giới hạn của ví dụ

Ví dụ này bảo đảm **tối đa một claim được tạo cho cùng slot** khi tất cả replica dùng cùng PostgreSQL và không có thao tác xóa bản ghi claim. Nó **không** bảo đảm công việc chắc chắn hoàn thành:

- Pod chết sau insert: dòng ở trạng thái `RUNNING` mãi; lần cron sau không claim lại slot cũ.
- Job ném lỗi: dòng thành `FAILED`; chính sách retry chưa được xây dựng và lần chạy tiếp theo không tự động thực hiện lại.
- Toàn bộ pod tắt lúc 02:00: không có ai insert slot; nếu chỉ dựa vào `@Scheduled`, slot sẽ bị bỏ qua.
- API đối tác thành công rồi pod chết trước khi cập nhật `SUCCEEDED`: không thể biết có nên retry nếu API không nhận idempotency key hoặc không có API tra cứu.
- PostgreSQL hoặc network bị lỗi: câu lệnh claim có thể không thành công, cần log/metric/alert; không được “fallback” chạy job mà chưa claim vì sẽ làm mất điều kiện loại trừ trùng.

Do đó đây là **mẫu giải thích cơ chế single claim**, không phải một hệ quản lý job đầy đủ. Trong production cần chính sách hồi phục trạng thái `RUNNING`/`FAILED`, deadline, retry/backoff và idempotency của từng tác dụng phụ.

## 7. Từ claim đơn giản đến hàng đợi công việc có lease

Với tác vụ cần retry hoặc mất nhiều phút, thiết kế nên tách thành hai phần:

1. **Scheduler** tính các slot còn thiếu và ghi công việc vào bảng hoặc queue có khóa unique theo business key.
2. **Worker** nhận một batch công việc đến hạn, thực hiện, ghi thành công/thất bại và lên lịch retry.

Tất cả instance có thể vừa chạy scheduler vừa chạy worker nếu các thao tác tạo job và claim đều nguyên tử. Một phương án khác là chỉ đặt lịch tập trung và scale worker độc lập.

### 7.1. Claim batch bằng `FOR UPDATE SKIP LOCKED`

Với PostgreSQL, có thể dùng `FOR UPDATE SKIP LOCKED` để nhiều worker claim **các dòng khác nhau** trong một bảng job:

~~~sql
CREATE TABLE scheduled_work (
    id BIGSERIAL PRIMARY KEY,
    business_key VARCHAR(200) NOT NULL UNIQUE,
    execute_after TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    state VARCHAR(16) NOT NULL DEFAULT 'READY'
        CHECK (state IN ('READY', 'RUNNING', 'SUCCEEDED', 'FAILED')),
    lease_owner VARCHAR(120),
    lease_until TIMESTAMPTZ,
    claim_version BIGINT NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_scheduled_work_claim
    ON scheduled_work (execute_after, id)
    WHERE state IN ('READY', 'RUNNING');
~~~

Ví dụ claim tối đa 20 dòng bằng `NamedParameterJdbcTemplate` (cú pháp `:workerId` là placeholder được Spring bind trước khi gửi SQL):

~~~sql
WITH candidates AS (
    SELECT id
      FROM scheduled_work
     WHERE execute_after <= CURRENT_TIMESTAMP
       AND (
            state = 'READY'
            OR (state = 'RUNNING' AND lease_until < CURRENT_TIMESTAMP)
       )
     ORDER BY execute_after, id
     FOR UPDATE SKIP LOCKED
     LIMIT 20
)
UPDATE scheduled_work AS w
   SET state = 'RUNNING',
       lease_owner = :workerId,
       lease_until = CURRENT_TIMESTAMP + INTERVAL '90 seconds',
       claim_version = w.claim_version + 1,
       attempts = w.attempts + 1
  FROM candidates AS c
 WHERE w.id = c.id
RETURNING w.id, w.business_key, w.payload, w.claim_version;
~~~

Lệnh claim phải được thực thi trong giao dịch ngắn và **commit trước khi gọi hệ thống ngoài**. `SKIP LOCKED` giúp giảm việc các worker cùng chờ một row đang bị khóa; nó không thay thế giới hạn tổng số job hoặc chính sách ưu tiên. Vì câu `UPDATE ... RETURNING` thực hiện nguyên tử với row lock của PostgreSQL, các worker không cùng claim một row trong cùng thời điểm. Khi `lease_until` hết hạn, job `RUNNING` có thể được claim lại.

Sau khi xử lý, worker chỉ được đánh dấu thành công nếu vẫn còn quyền sở hữu claim:

~~~sql
UPDATE scheduled_work
   SET state = 'SUCCEEDED',
       lease_owner = NULL,
       lease_until = NULL
 WHERE id = :id
   AND state = 'RUNNING'
   AND lease_owner = :workerId
   AND claim_version = :claimVersion
   AND lease_until > CURRENT_TIMESTAMP;
~~~

Nếu số dòng cập nhật bằng **0**, có thể lease đã hết hạn hoặc một worker khác đã nhận thế hệ mới; worker cũ không được ghi đè trạng thái job. `claim_version` là **fencing token trong database** cho việc hoàn tất job. Nó chỉ chặn thao tác ghi SQL cũ: nếu worker cũ đã gọi một HTTP endpoint không biết token hoặc idempotency key, DB không thể tự thu hồi tác dụng phụ đó.

### 7.2. Lease, heartbeat và retry

- Đặt `lease_until` theo **đồng hồ của database**, tránh để các pod tự quyết định hết hạn bằng đồng hồ không đồng bộ.
- Với job dài, gia hạn lease định kỳ bằng `UPDATE ... WHERE id/owner/version` và phát hiện gia hạn thất bại. Không cho worker đã mất quyền tiếp tục ghi kết quả chung.
- Khi lỗi, cập nhật `attempts`, `last_error` (nếu schema có) và `execute_after` để retry có backoff. Sau ngưỡng cho phép, chuyển `FAILED` để vận hành xử lý.
- Cần một quá trình **reconciliation/catch-up** tạo lại slot bị bỏ lỡ, ví dụ “các ngày chưa có job báo cáo”, thay vì chờ cron kế tiếp rồi bỏ qua lịch cũ.
- Định nghĩa trạng thái job rõ ràng: `READY → RUNNING → SUCCEEDED`, hoặc `RUNNING → READY` khi retry, `RUNNING → FAILED` khi vượt ngưỡng; mọi chuyển trạng thái cần điều kiện bảo vệ.

Trong hệ thống thực, xây thêm index/tách bảng lịch sử, giữ số bản ghi phù hợp và đánh giá lock contention. Nếu yêu cầu là rất nhiều job hoặc lịch phức tạp, có thể dùng nền tảng scheduler/queue chuyên dụng thay vì tự xây toàn bộ state machine.

## 8. Distributed lock giúp gì và không giúp gì?

Với thư viện như ShedLock hoặc một cơ chế khóa chung dựa trên database/Redis, nhiều replica vẫn có callback `@Scheduled`, nhưng chỉ replica giữ khóa mới chạy phần công việc được bảo vệ.

~~~mermaid
sequenceDiagram
    participant A as Replica A
    participant B as Replica B
    participant L as Shared lock store
    participant E as External API
    A->>L: Try acquire job:reconcile
    B->>L: Try acquire job:reconcile
    L-->>A: Acquired
    L-->>B: Rejected
    A->>E: Run reconciliation
    A->>L: Release lock
~~~

Những vấn đề cần quyết định khi dùng lock:

- **Kho khóa:** database/Redis phải dùng chung giữa tất cả instance. Khóa in-memory không có tác dụng xuyên pod.
- **TTL/lease:** nếu quá ngắn, công việc đang chạy có thể mất khóa và bị worker khác thực hiện; nếu quá dài, crash khiến lần retry bị trì hoãn.
- **Ownership:** khi giải phóng/đổi hạn khóa phải xác nhận token/owner hiện tại; không cho worker cũ xóa khóa mới của worker khác. Với Redis, việc kiểm tra token và xóa cần nguyên tử.
- **Run missed:** lock chỉ quyết định ai được chạy ở thời điểm thức dậy; nó không tự tạo lại một slot hoàn toàn không có instance nào kích hoạt.
- **Không đồng nghĩa exactly-once:** dù chỉ một worker giữ khóa tại một thời điểm, HTTP/Kafka có thể đã hoàn thành nhưng worker chưa ghi nhận; retry vẫn cần idempotency.

Nếu nhiệm vụ có tính chất cập nhật một lần theo slot, mẫu **khóa unique theo business key + trạng thái thực thi bền vững** thường dễ audit hơn một khóa tạm thời không lưu lịch sử. Nếu tác vụ thuần refresh cache cục bộ từng replica, có thể không cần distributed lock: mỗi replica có quyền làm mới cache của chính nó.

## 9. Khi nào chuyển sang Quartz, Kubernetes CronJob hoặc queue?

### Quartz với JDBC JobStore clustering

Quartz phù hợp khi lịch động cần được lưu, có nhiều trigger, cần theo dõi misfire hoặc điều phối execution giữa các node Quartz. Các scheduler instance dùng **cùng bộ bảng Quartz JDBC JobStore**, cấu hình clustered tương thích và instance ID riêng. Nếu mỗi instance dùng bộ bảng riêng thì chúng **không** phối hợp như một cluster.

Trong một hệ thống Quartz clustered, vẫn phải quan tâm đến độ sẵn sàng của database, thời gian kiểm tra cluster, chính sách misfire và tính idempotent của job. Cơ chế `@DisallowConcurrentExecution` dành cho một `JobDetail` của Quartz giúp tránh các lần thực thi chồng lấn của job đó theo quy tắc Quartz; nó không làm một thao tác HTTP có tác dụng phụ trở thành distributed transaction.

### Kubernetes CronJob

Một CronJob định kỳ tạo **Kubernetes Job**, mỗi Job có thể tạo pod thực thi rồi kết thúc. Chẳng hạn, để một job đối soát độc lập với replica HTTP API:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-order-reconciliation
spec:
  schedule: "0 2 * * *"
  timeZone: "Etc/UTC"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 300
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: reconciliation
              image: registry.example.com/integration-worker:1.0.0
              args: ["--job", "reconcile-orders"]
~~~

`concurrencyPolicy: Forbid` giúp tránh chạy chồng **giữa các Job thuộc cùng CronJob**, nhưng không khóa các CronJob độc lập, không ngăn mọi hình thức khởi chạy lặp và không bảo đảm mỗi lịch luôn được thực thi đúng một lần. `startingDeadlineSeconds` điều khiển việc xem một lần chạy đã trễ còn được bắt đầu hay không; cấu hình cần dựa trên yêu cầu chạy bù và chính sách bỏ qua lịch.

Cấu hình `timeZone` yêu cầu phiên bản Kubernetes hỗ trợ trường đó. Ngoài ra cần giới hạn tài nguyên, job history, active deadline, timeout và theo dõi Job thất bại. Hãy truyền business slot vào worker theo cách ổn định hoặc để worker tự xác định các slot còn thiếu từ kho trạng thái.

### Queue / broker cho tác vụ bất đồng bộ

Một scheduler có thể **ghi công việc** vào database và phát signal đến Kafka/RabbitMQ, còn nhiều consumer cùng xử lý. Đây là lựa chọn hữu ích nếu mỗi chu kỳ sinh hàng nghìn tác vụ nhỏ. Producer chỉ nên tạo đúng **business key** cho từng việc; consumer dùng idempotency key để chịu được phát lặp, retry sau crash và rebalance.

Khi vừa ghi trạng thái job trong database vừa phát message tới broker, lại xuất hiện **ranh giới hai commit**. Có thể dùng transactional outbox hoặc cơ chế đối soát: lưu job/outbox trong cùng DB transaction, rồi relay đưa lên broker. Kafka transaction giúp gom thao tác **bên trong Kafka**; nó không tự bao phủ commit của PostgreSQL, HTTP đối tác hoặc cache.

## 10. Xử lý trùng lặp và thiết kế dữ liệu tích hợp

Khóa lịch là tuyến phòng thủ đầu. Ở tuyến nghiệp vụ, cần thiết kế thao tác có thể thực hiện lại an toàn:

| Tác vụ | Idempotency phù hợp | Điều cần lưu ý |
|---|---|---|
| Tạo báo cáo ngày | Unique `(report_type, report_date)`, upsert có điều kiện | Không tạo file/email báo cáo mới mỗi retry nếu không mong muốn |
| Đồng bộ dữ liệu HTTP | `requestId` ổn định hoặc version/ETag của đối tác | Timeout không chứng minh đối tác chưa xử lý |
| Thanh toán/đối soát | Idempotency key theo giao dịch và API tra cứu trạng thái | Tránh tạo khóa mới cho mỗi retry cùng ý định |
| Cập nhật cache chung | Ghi version/timestamp có điều kiện, TTL phù hợp | Có thể chấp nhận refresh nhiều lần nếu thao tác thuần và nhẹ |
| Xuất sự kiện Kafka | `eventId` ổn định, outbox + consumer dedup | Đánh dấu đã gửi sau broker ack vẫn có cửa sổ phát lặp |
| Cập nhật DB từ message | Bảng `processed_events` với unique key, cùng DB transaction | Commit offset sau khi trạng thái nghiệp vụ đã commit |

Ví dụ cập nhật dữ liệu bằng upsert PostgreSQL:

~~~sql
INSERT INTO daily_reconciliation(day_key, outcome, updated_at)
VALUES (:dayKey, :outcome, CURRENT_TIMESTAMP)
ON CONFLICT (day_key) DO UPDATE
   SET outcome = EXCLUDED.outcome,
       updated_at = EXCLUDED.updated_at;
~~~

Upsert có thể làm thao tác **không tạo dòng trùng**, nhưng vẫn cần quan tâm **thứ tự và phiên bản dữ liệu**: lần retry cũ không được ghi đè kết quả mới. Với thông tin biến đổi theo thời gian, dùng điều kiện version tăng dần hoặc kiểm tra `updated_at` của nguồn thay vì upsert vô điều kiện.

Một `requestId` hoặc `jobId` phải giữ nguyên qua tất cả lần retry của **cùng một công việc nghiệp vụ**. Sinh UUID mới mỗi lần retry không tạo idempotency thực chất.

## 11. Tác vụ cục bộ nào có thể chạy trên mọi replica?

Không phải lịch cục bộ nào cũng là lỗi thiết kế:

- Làm mới **cache cục bộ** hoặc tải cấu hình read-only riêng cho từng instance.
- Làm sạch bộ nhớ đệm, thống kê nội bộ hoặc đối tượng có vòng đời gắn với JVM.
- Đo health/snapshot cục bộ theo chu kỳ, khi việc chạy trên từng replica là chủ đích.

Ngược lại, gửi email hàng loạt, trừ tồn kho, tạo hóa đơn, phát outbox, tổng hợp báo cáo chung và cập nhật dữ liệu dùng chung thường cần điều phối cluster, idempotency và chính sách khôi phục.

Câu hỏi thực tế là: **“Nếu 10 replica cùng gọi callback này, điều gì bị thay đổi 10 lần?”** Nếu câu trả lời là một trạng thái nghiệp vụ chung hoặc hệ thống đối tác, nên thiết kế lại ranh giới thực thi.

## 12. Quan sát và vận hành lịch trong production

Với tác vụ tích hợp, log “Scheduler started” chưa đủ cho biết kết quả. Cần theo dõi cả **slot dự kiến**, **slot đã claim** và **tác dụng phụ đã hoàn thành**.

Các tín hiệu quan trọng:

- **Kích hoạt:** `job_name`, `slot_key`, thời điểm dự kiến, thời điểm thực thi, `instance_id`, `correlation_id`.
- **Điều phối:** số lần claim thành công/thất bại, thời gian chờ lock, lease còn hiệu lực, job bị claim lại, lỗi owner/fencing.
- **Thực thi:** duration, lỗi nghiệp vụ, số lần retry, timeout HTTP, số bản ghi đã xử lý, số sự kiện Kafka đã phát và xác nhận.
- **Tồn đọng:** số job `READY`, `RUNNING` quá hạn, `FAILED`, tuổi job lâu nhất, slot chưa tạo do downtime.
- **Phụ thuộc:** kết nối database, tỷ lệ HTTP 429/5xx của đối tác, độ trễ broker, consumer lag hoặc backlog outbox.

Ví dụ đặt cảnh báo nếu **slot đối soát ngày hôm trước chưa có `SUCCEEDED` sau 03:00 UTC**, thay vì chỉ báo khi JVM bị lỗi. Nếu metric cho biết nhiều job đang `RUNNING` nhưng đã hết lease, cần có quy trình xác minh worker bị chết hay đang chậm trước khi retry hàng loạt.

Khi triển khai rolling update, cần graceful shutdown: ngừng nhận việc mới, cho tác vụ đang làm hoàn tất trong thời gian cho phép hoặc trả về trạng thái có thể retry. Kubernetes termination grace period và timeout ứng dụng nên phù hợp với các thao tác có thể kết thúc an toàn; không giả định mọi request HTTP/Kafka có thể hủy tức thì mà không có tác dụng phụ.

## 13. Kiểm thử hành vi nhiều replica

Nên chạy **ít nhất hai application context/process** hoặc hai worker thực trên cùng PostgreSQL (ví dụ Testcontainers), thay vì chỉ gọi một phương thức scheduler trong unit test. Cần dùng clock/slot được kiểm soát để test không phụ thuộc thời gian thực.

| Kiểm thử | Cách tạo tình huống | Kỳ vọng |
|---|---|---|
| Hai replica cùng slot | Cùng gọi claim `(job_name, slot_key)` đồng thời | Chỉ một `INSERT` thành công; không phát hai lần từ nhánh claim |
| Nhiều business key | Gửi hai slot/ngày khác nhau | Hai công việc hợp lệ không khóa nhầm nhau |
| Crash sau claim | Kill worker trước khi cập nhật kết quả | Có bản ghi `RUNNING`/lease hết hạn; recovery được kích hoạt theo policy |
| Crash sau side effect | Đối tác nhận request, worker chết trước khi ack | Retry dùng lại cùng idempotency key và không nhân đôi nghiệp vụ |
| Mất lịch lúc downtime | Dừng tất cả instance qua giờ cron | Cơ chế catch-up tạo lại đúng slot chưa chạy |
| Lease hết hạn khi worker A chậm | Worker B claim cùng job ở thế hệ mới | A không được ghi đè trạng thái B; downstream xử lý trùng an toàn |
| Rolling deployment | Chạy đồng thời phiên bản A và B | Không tạo hai kết quả mâu thuẫn cho cùng slot, tương thích hợp đồng |
| Lỗi phụ thuộc HTTP/Kafka | Gây timeout/429/5xx và phục hồi | Retry/backoff hữu hạn, log/metric chính xác, không mất công việc |
| Nhiều hàng đợi/partition | Nhiều worker nhận job | Không xử lý trùng vượt quy tắc idempotency; throughput đạt mục tiêu |
| Lịch theo múi giờ | Kiểm tra chuyển ngày và DST nếu có | Slot business key nhất quán theo múi giờ đã chọn |

Đối với mẫu PostgreSQL ở phần 6, test phải kiểm tra cả **tình huống `RUNNING` bị kẹt**, vì chỉ test “hai replica, một lần insert” có thể tạo cảm giác hệ thống đã bảo đảm hoàn tất đúng một lần. Với phương án lease ở phần 7, phải thử trường hợp worker cũ hoàn thành sau khi đã mất quyền.

## 14. Checklist thiết kế

Trước khi đưa một tác vụ `@Scheduled` vào ứng dụng Spring Boot chạy nhiều bản sao, hãy xác định:

1. Công việc cần chạy **trên từng replica** hay chỉ cần một kết quả chung?
2. Business key của một slot là gì; được tính theo múi giờ nào và có thay đổi khi retry không?
3. Nếu toàn bộ instance không chạy đúng giờ, ai tạo lại slot bị bỏ lỡ?
4. Nếu hai replica cùng kích hoạt, cơ chế claim nào quyết định quyền thực thi?
5. Nếu worker chết sau side effect, hệ thống đích có idempotency key hoặc cách đối soát trạng thái không?
6. TTL/lease, heartbeat, fencing và retry/backoff được thiết kế thế nào?
7. Với DB + Kafka/HTTP, cơ chế nào tránh mất ý định gửi và xử lý được message trùng?
8. Có metric/alert theo **slot thực sự hoàn tất**, không chỉ theo số lần scheduler thức dậy, hay chưa?
9. Có test multi-instance, crash, rolling deployment, downtime và timeout thật hay chưa?

**Kết luận:** `@Scheduled` cung cấp đồng hồ cho **mỗi JVM**, không tự tạo lịch phân tán. Khi Spring Boot Integration mở rộng nhiều replica, phải gắn lịch với trạng thái công việc bền vững, điều phối quyền thực thi và đảm bảo idempotency ở ranh giới database, HTTP, cache hoặc broker. Một claim nguyên tử có thể ngăn khởi chạy trùng trong trường hợp đơn giản; muốn xử lý sự cố và hoàn tất công việc đáng tin cậy còn cần retry, catch-up, lease/fencing hoặc một scheduler/queue chuyên dụng.

### Tài liệu tham khảo

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Scheduled`, `@Async`, scheduler và executor.
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html): cấu hình task scheduling và thread pool.
- [Quartz Scheduler — Configuration Reference](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/configuration/): JobStore JDBC và cluster.
- [Kubernetes — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/): lịch, time zone, `concurrencyPolicy`, deadline và các giới hạn khi lập lịch.
- [PostgreSQL — SELECT / Locking Clause](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE SKIP LOCKED` và hành vi khóa hàng.

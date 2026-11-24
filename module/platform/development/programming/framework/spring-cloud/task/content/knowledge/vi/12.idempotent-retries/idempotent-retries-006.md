# Xử lý hoàn tất một phần và lưu điểm tiếp tục ở tầng nghiệp vụ

## 1. Tình huống: một task đã làm xong một phần rồi bị ngắt

Trong **Spring Cloud Task**, ứng dụng Spring Boot nhận tham số, xử lý một công việc có điểm kết thúc rõ ràng, ghi nhận trạng thái lần thực thi vào **TaskRepository** và thoát. Ví dụ một tác vụ đối soát xử lý 10.000 giao dịch theo ngày, được chạy lúc 2 giờ sáng.

Đến giao dịch thứ 6.001, JVM bị dừng vì hết bộ nhớ. Dữ liệu của 6.000 giao dịch trước đã được ghi xuống database. Người vận hành cần khởi chạy lại, nhưng **không muốn xử lý lại giao dịch đã hoàn tất** và **không được bỏ sót giao dịch chưa ghi thành công**.

Đây là bài toán **hoàn tất một phần (partial completion)** và **tiếp tục sau lỗi (resume)** ở chương **Chạy lại an toàn**.

Cần trả lời bốn câu hỏi riêng:

- **Phạm vi công việc:** đầu vào cụ thể nào phải được xử lý? Phạm vi đó có thay đổi giữa hai lần chạy không?
- **Trạng thái đã commit:** đơn vị xử lý nào đã hoàn tất bền vững, đơn vị nào chỉ mới được thực hiện trong bộ nhớ?
- **Điểm tiếp tục:** lần chạy mới nên bắt đầu đọc từ đâu?
- **Tác động bên ngoài:** có thao tác nào như gửi email, gọi API hoặc ghi file đã xảy ra mà transaction nội bộ không thể rollback không?

**TaskRepository không lưu tiến độ nghiệp vụ đến từng bản ghi.** Nó theo dõi một `TaskExecution` với thời gian bắt đầu, kết thúc, mã thoát và lỗi. Việc lưu con trỏ, checkpoint và kết quả từng phần phải do **tầng nghiệp vụ** thiết kế hoặc do cơ chế chuyên biệt như **Spring Batch** quản lý.

### Kết quả học tập

Sau bài, bạn có thể phân biệt trạng thái lần thực thi và trạng thái công việc, thiết kế **work key** bền vững, lưu kết quả và checkpoint trong cùng transaction, tiếp tục bằng cursor ổn định, áp dụng idempotency/outbox cho side effect ngoài database và kiểm thử các cửa sổ lỗi trước khi chạy production.

## 2. TaskExecution và checkpoint là hai cấp độ khác nhau

Mỗi lần khởi động một ứng dụng Spring Cloud Task có thể tạo một bản ghi thực thi mới:

| Lần chạy | TASK_EXECUTION_ID | Work key | Kết quả |
| --- | --- | --- | --- |
| Lần đầu | 501 | `tenant-A:2026-11-23:v1` | Lỗi sau chunk 60 |
| Chạy lại | 502 | `tenant-A:2026-11-23:v1` | Tiếp tục từ checkpoint và hoàn tất |

**Task execution ID** xác định **một lần chạy vật lý**. **Work key** xác định **công việc nghiệp vụ cần hoàn tất**, và phải ổn định giữa những lần retry cùng phạm vi nguồn.

| Nơi lưu | Nội dung | Có thể dùng để tiếp tục? |
| --- | --- | --- |
| `TaskRepository` / `TASK_EXECUTION` | Tên task, ID lần chạy, thời điểm, exit code, error message | Chỉ đủ để biết vòng đời, **không** biết đã commit bản ghi nào |
| Bảng `work_progress` nghiệp vụ | Work key, phiên bản nguồn, checkpoint, trạng thái | **Có**, nếu checkpoint phản ánh dữ liệu đã commit |
| Bảng kết quả nghiệp vụ | Dữ liệu đã xử lý, khóa kết quả duy nhất | Kiểm chứng phần thực sự hoàn tất |
| Outbox hoặc hệ thống ngoài | Sự kiện và trạng thái giao nhận theo event ID | Kiểm chứng tác động ngoài transaction |

Hai lần chạy `501` và `502` cần **cùng work key** để dùng chung checkpoint. Nếu đặt tên bản ghi tiến độ bằng `TASK_EXECUTION_ID` thì lần retry có ID mới sẽ không tìm thấy điểm tiếp tục cũ.

Trong log, nên ghi cả **execution ID** và **work key**; tránh đưa mật khẩu, token hoặc dữ liệu cá nhân vào tham số được lưu hoặc log.

## 3. Bất biến của checkpoint

**Checkpoint** là một ranh giới đã hoàn tất bền vững. Ví dụ:

~~~text
work_key          = tenant-A:2026-11-23:v1
upper_source_id   = 10000
last_committed_id = 6000
state             = IN_PROGRESS
~~~

Nghĩa đúng của `last_committed_id=6000` là **mọi đơn vị bắt buộc trong phạm vi nguồn đã chốt, có khóa nhỏ hơn hoặc bằng 6000, đều đã được hoàn tất và commit hoặc có quyết định skip được ghi nhận**.

Đây là bất biến quan trọng:

> Chỉ tăng checkpoint đến `C` sau khi **tất cả kết quả của những đơn vị công việc trước hoặc tại `C` đã được lưu bền vững**.

Nếu cập nhật cursor lên 7000 **trước** khi ghi kết quả cho 6001–7000, một lần crash sẽ khiến lần sau bỏ qua các bản ghi chưa xử lý. Nếu ghi kết quả trước nhưng cập nhật checkpoint trong một **transaction khác**, crash có thể khiến lần sau làm lại phần đã hoàn tất.

Khi kết quả và checkpoint cùng nằm trong **một database hỗ trợ transaction**, hãy ghi chúng trong **một transaction**. Khi đó một chunk chỉ có hai trạng thái bền vững: **cả kết quả lẫn checkpoint được commit**, hoặc **cả hai bị rollback**.

~~~mermaid
flowchart LR
    A["Đọc checkpoint theo work key"] --> B["Lấy chunk nguồn sau cursor"]
    B --> C["BEGIN transaction"]
    C --> D["Ghi kết quả nghiệp vụ"]
    D --> E["Tăng checkpoint"]
    E --> F{"COMMIT thành công?"}
    F -->|Có| G["Tiếp tục chunk sau"]
    F -->|Không| H["ROLLBACK cả kết quả và checkpoint"]
    H --> A
    G --> B
~~~

### Chọn kích thước đơn vị commit

| Đơn vị commit | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Từng bản ghi | Tiếp tục rất chính xác, ít việc phải chạy lại | Nhiều transaction, tăng overhead |
| Chunk 100–1.000 bản ghi | Cân bằng hiệu năng, rollback có giới hạn | Cả chunk được thử lại nếu lỗi trước commit |
| Toàn bộ 10.000 bản ghi | Logic đơn giản nếu công việc rất nhỏ | Transaction lớn, lock dài, rollback tốn kém |
| Từng bước workflow | Dễ quan sát bước đã xong | Cần trạng thái/bù trừ riêng cho bước có side effect |

**Không có kích thước chunk tối ưu cho mọi ứng dụng.** Hãy dựa trên thời gian thực thi, giới hạn timeout, tài nguyên database, khả năng retry và tính nguyên tử cần có.

## 4. Bảo đảm tập nguồn không đổi khi khôi phục

Cursor chỉ an toàn nếu tập nguồn và thứ tự xử lý **ổn định**.

Giả sử đã xử lý tới `source_id=6000` rồi khởi chạy lại:

~~~sql
SELECT source_id, amount
FROM payment_source
WHERE work_key = :workKey
  AND source_id > :lastCommittedId
  AND source_id <= :upperSourceId
ORDER BY source_id
LIMIT :chunkSize;
~~~

Đây là **keyset pagination**: đọc **sau** checkpoint và sắp theo khóa ổn định. Điều kiện `>` loại trừ bản ghi ranh giới đã commit.

Không nên lưu `OFFSET=6000` trên bảng đang bị chèn/xóa, vì vị trí hàng có thể dịch chuyển. Cũng không đủ chỉ lưu `upper_source_id=10000` nếu có transaction chậm commit sau này làm xuất hiện bản ghi mang ID nhỏ hơn 10000.

Một trong các cách **chốt tập nguồn** là:

- Sử dụng partition nguồn bất biến sau khi đóng sổ kỳ.
- Tạo bảng manifest liệt kê chính xác những `source_id` cần xử lý.
- Dùng `snapshot_id` hoặc phiên bản tệp cùng checksum.
- Lưu phiên bản nghiệp vụ trong work key, ví dụ `tenant-A:2026-11-23:v1`.

**Nếu nguồn có thể thay đổi trong lúc chạy, ví dụ tiếp theo chỉ an toàn khi bổ sung cơ chế snapshot/manifest thực tế.** Một con số “ID cao nhất” không tự biến nguồn đang ghi thành bất biến.

## 5. Ví dụ PostgreSQL: tự lưu điểm tiếp tục

Ví dụ dành cho ứng dụng Spring Cloud Task chạy hữu hạn với database nghiệp vụ PostgreSQL. Đây là **schema của nghiệp vụ**, không phải DDL của `TaskRepository`. Giả định `payment_source` đã được chốt theo từng work key.

### 5.1. Tạo ba bảng

~~~sql
-- Đầu vào đã đóng băng theo work_key.
CREATE TABLE payment_source (
    work_key    VARCHAR(160) NOT NULL,
    source_id   BIGINT NOT NULL,
    amount      NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (work_key, source_id)
);

-- Kết quả cần có khóa duy nhất để chống ghi trùng.
CREATE TABLE payment_projection (
    work_key     VARCHAR(160) NOT NULL,
    source_id    BIGINT NOT NULL,
    amount       NUMERIC(18, 2) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (work_key, source_id)
);

-- Checkpoint bền vững, độc lập với TaskExecution.
CREATE TABLE reconciliation_progress (
    work_key          VARCHAR(160) PRIMARY KEY,
    upper_source_id   BIGINT NOT NULL,
    last_committed_id BIGINT NOT NULL DEFAULT 0,
    state             VARCHAR(20) NOT NULL DEFAULT 'READY',
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT valid_progress
      CHECK (last_committed_id >= 0
         AND upper_source_id >= 0
         AND last_committed_id <= upper_source_id),
    CONSTRAINT valid_state
      CHECK (state IN ('READY', 'IN_PROGRESS',
                      'COMPLETED', 'FAILED'))
);
~~~

Các cột chính:

| Cột | Ý nghĩa |
| --- | --- |
| `work_key` | Khóa cùng công việc qua nhiều lần retry |
| `upper_source_id` | Giới hạn trên của tập nguồn **đã chốt** |
| `last_committed_id` | Khóa của đơn vị nguồn cuối đã commit trong thứ tự xử lý |
| `state` | Trạng thái công việc ở tầng nghiệp vụ |
| `updated_at` | Hỗ trợ quan sát thay đổi, không tự là lease/lock |

Để khởi tạo lần đầu, **sau khi nguồn đã đóng băng**:

~~~sql
INSERT INTO reconciliation_progress (work_key, upper_source_id)
SELECT 'tenant-A:2026-11-23:v1',
       COALESCE(MAX(source_id), 0)
FROM payment_source
WHERE work_key = 'tenant-A:2026-11-23:v1'
ON CONFLICT (work_key) DO NOTHING;
~~~

`ON CONFLICT DO NOTHING` giúp lệnh khởi tạo gọi lại mà **không reset** checkpoint đang có. Nếu người dùng muốn xử lý phiên bản nguồn mới, hãy tạo work key/version mới hoặc một quy trình reprocess rõ ràng.

### 5.2. Mỗi chunk là một transaction

Ví dụ Java 17+, Spring JDBC và một transaction manager quản lý **cả kết quả lẫn checkpoint**. Phương thức được gọi qua Spring proxy từ một bean khác:

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReconciliationChunkService {

    private final JdbcTemplate jdbc;

    public ReconciliationChunkService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean processNextChunk(String workKey, int chunkSize) {
        if (chunkSize < 1 || chunkSize > 1000) {
            throw new IllegalArgumentException("Invalid chunk size");
        }

        Cursor cursor = jdbc.queryForObject("""
            SELECT last_committed_id, upper_source_id, state
            FROM reconciliation_progress
            WHERE work_key = ?
            FOR UPDATE
            """,
            (rs, n) -> new Cursor(
                rs.getLong("last_committed_id"),
                rs.getLong("upper_source_id"),
                rs.getString("state")),
            workKey
        );

        if ("COMPLETED".equals(cursor.state())) {
            return false;
        }

        List<Payment> batch = jdbc.query("""
            SELECT source_id, amount
            FROM payment_source
            WHERE work_key = ?
              AND source_id > ?
              AND source_id <= ?
            ORDER BY source_id
            LIMIT ?
            """,
            (rs, n) -> new Payment(
                rs.getLong("source_id"),
                rs.getBigDecimal("amount")),
            workKey, cursor.lastId(), cursor.upperId(), chunkSize
        );

        if (batch.isEmpty()) {
            if (cursor.lastId() < cursor.upperId()) {
                throw new IllegalStateException(
                    "Frozen source has unexpectedly changed");
            }
            jdbc.update("""
                UPDATE reconciliation_progress
                SET state = 'COMPLETED', updated_at = now()
                WHERE work_key = ?
                """, workKey);
            return false;
        }

        for (Payment p : batch) {
            jdbc.update("""
                INSERT INTO payment_projection
                    (work_key, source_id, amount)
                VALUES (?, ?, ?)
                ON CONFLICT (work_key, source_id) DO NOTHING
                """, workKey, p.id(), p.amount());
        }

        long lastId = batch.get(batch.size() - 1).id();
        jdbc.update("""
            UPDATE reconciliation_progress
            SET last_committed_id = ?,
                state = CASE
                    WHEN ? = upper_source_id THEN 'COMPLETED'
                    ELSE 'IN_PROGRESS'
                END,
                updated_at = now()
            WHERE work_key = ?
            """, lastId, lastId, workKey);

        return true;
    }

    private record Cursor(long lastId, long upperId, String state) {}
    private record Payment(long id, BigDecimal amount) {}
}
~~~

**Điểm bảo vệ trong ví dụ:**

1. `SELECT ... FOR UPDATE` khóa **hàng checkpoint của work key** trong transaction đang xử lý. Hai process không thể đọc cùng checkpoint cũ rồi đồng thời commit lên cùng hàng nếu transaction/DB được cấu hình đúng.
2. `ORDER BY source_id` và `source_id > last_committed_id` tạo cursor tăng dần, không dùng offset.
3. `ON CONFLICT` ngăn tạo hai kết quả trùng khóa. Nó cũng có thể **che lỗi khi dữ liệu nguồn bị sửa**, vì vậy điều kiện nguồn bất biến là bắt buộc; nếu nguồn có version mới, cần thiết kế xử lý khác.
4. Cập nhật `last_committed_id` **cùng transaction** với ghi `payment_projection`. Nếu một lệnh trong chunk ném exception trước commit, toàn bộ chunk rollback.
5. `@Transactional` được kích hoạt khi gọi **qua Spring bean proxy**. Nếu tự gọi nội bộ `this.processNextChunk(...)` trong cùng class, Spring AOP transaction có thể không áp dụng.
6. Ví dụ giả định checkpoint đã được khởi tạo. Không có row tương ứng, `queryForObject` sẽ ném lỗi; cần phát hiện và khởi tạo work key trước khi chạy.

**Giới hạn:** row lock chỉ đồng bộ **mỗi chunk**; hai tiến trình có thể thay nhau xử lý các chunk của một work key sau từng lần commit. Nếu chỉ cho một process chạy toàn kỳ, dùng thêm khóa/scheduler policy theo work key.

### 5.3. Runner cho Spring Cloud Task

~~~java
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ReconciliationRunnerConfig {

    @Bean
    ApplicationRunner reconciliationRunner(
            ReconciliationChunkService service) {
        return args -> {
            List<String> values = args.getOptionValues("workKey");
            if (values == null || values.size() != 1) {
                throw new IllegalArgumentException(
                    "Required: --workKey=<stable-business-key>");
            }

            String workKey = values.get(0);
            while (service.processNextChunk(workKey, 100)) {
                // Mỗi lời gọi có transaction riêng.
            }
        };
    }
}
~~~

Ví dụ chạy bằng một dòng lệnh:

~~~bash
java -jar reconciliation-task.jar --workKey=tenant-A:2026-11-23:v1
~~~

Nếu runner ném lỗi, Spring Cloud Task có thể ghi lần chạy thất bại trong `TaskRepository`. Lần chạy kế tiếp nhận **cùng work key** sẽ đọc checkpoint đã commit; `TaskExecution` của lần chạy mới có **execution ID khác**.

### 5.4. Kiểm tra dữ liệu đã commit

~~~sql
SELECT work_key, upper_source_id,
       last_committed_id, state, updated_at
FROM reconciliation_progress
WHERE work_key = 'tenant-A:2026-11-23:v1';
~~~

~~~sql
SELECT COUNT(*) AS committed_results
FROM payment_projection
WHERE work_key = 'tenant-A:2026-11-23:v1';
~~~

**Lưu ý:** `last_committed_id` là **khóa định vị**, không nhất thiết là tổng số hàng đã xử lý. Nếu ID có khoảng trống, `last_committed_id=6000` không có nghĩa là đã xử lý đúng 6.000 hàng.

## 6. Cửa sổ lỗi và cách chạy lại

| Lỗi xảy ra lúc nào? | Checkpoint và kết quả | Quy tắc phục hồi |
| --- | --- | --- |
| Trước chunk | Chưa có thay đổi chunk mới | Đọc lại checkpoint hiện tại |
| Giữa chunk trước commit | Cả kết quả và checkpoint rollback | Thực hiện lại chunk từ ranh giới cũ |
| Sau lệnh UPDATE checkpoint nhưng trước COMMIT | Cả hai vẫn chưa bền vững | Rollback và chạy lại từ checkpoint cũ |
| Sau COMMIT nhưng trước log “xong” | Kết quả và checkpoint **đã lưu** | Tiếp tục sau cursor đã commit |
| Sau khi gửi HTTP/email nhưng trước lưu trạng thái | Tác động ngoài DB có thể đã xảy ra | Idempotency/outbox/đối soát hệ thống ngoài |
| JVM bị kill trước khi TaskRepository ghi END_TIME | Metadata TaskExecution có thể chưa kết thúc | Kiểm tra process và checkpoint nghiệp vụ |

**Không cập nhật checkpoint trước rồi mới ghi dữ liệu.** Ví dụ nguy hiểm:

~~~text
UPDATE progress SET last_committed_id = 7000;
COMMIT;
... chưa kịp xử lý bản ghi 6001-7000 ...
CRASH
~~~

Lần chạy mới tin vào cursor 7000 sẽ **bỏ qua** công việc thực tế chưa hoàn tất.

Thiết kế đúng khi cùng database:

~~~text
BEGIN TRANSACTION;
  GHI kết quả cho phần 6001-7000;
  UPDATE checkpoint = 7000;
COMMIT;
~~~

Nếu một thao tác thất bại, transaction rollback. Nếu commit đã thành công mà log cuối bị mất, database vẫn là nguồn xác thực tiến độ.

## 7. Khi công việc có tác động ngoài database

Transaction JDBC không thể rollback email, object storage upload hoặc API đã xử lý thành công. Ví dụ:

1. Task gọi API hoàn tiền với `refundId=R-123`.
2. API thực hiện hoàn tiền, nhưng kết nối mất trước khi gửi response.
3. Task nhận timeout, chưa lưu checkpoint.
4. Lần retry gửi lại cùng yêu cầu.

Nếu không có bảo vệ ở phía nhận, cùng một giao dịch có thể bị hoàn tiền **hai lần**.

### 7.1. Idempotency key ổn định

Tạo khóa từ **đơn vị nghiệp vụ**, chẳng hạn `refund:order-123:v1`; truyền cùng khóa trong mọi retry. Nếu API đích hỗ trợ idempotency đúng cách, yêu cầu lặp lại có thể trả lại kết quả trước mà không tạo tác động mới.

**Không dùng `TASK_EXECUTION_ID` làm idempotency key** vì mỗi lần chạy lại có ID khác. Đối với API không hỗ trợ idempotency, cần truy vấn trạng thái theo business key hoặc xây quy trình đối soát/bù trừ.

### 7.2. Transactional outbox

Nếu cần phát sự kiện sau khi xử lý dữ liệu, hãy ghi **kết quả, bản ghi outbox và checkpoint trong cùng transaction DB**. Một publisher độc lập gửi outbox tới hệ thống ngoài:

~~~mermaid
flowchart LR
    A["Transaction chunk"] --> B["Kết quả DB"]
    A --> C["Outbox event_id duy nhất"]
    A --> D["Checkpoint"]
    C --> E["Publisher retry"]
    E --> F["Hệ thống nhận kiểm tra event_id"]
~~~

DDL tối giản:

~~~sql
CREATE TABLE outbox_event (
    event_id    VARCHAR(180) PRIMARY KEY,
    work_key    VARCHAR(160) NOT NULL,
    event_type  VARCHAR(80) NOT NULL,
    payload     JSONB NOT NULL,
    sent_at     TIMESTAMPTZ
);
~~~

Bản ghi sự kiện có ID ổn định và ràng buộc duy nhất:

~~~sql
INSERT INTO outbox_event (event_id, work_key, event_type, payload)
VALUES (
    'tenant-A:2026-11-23:v1:payment-601',
    'tenant-A:2026-11-23:v1',
    'PAYMENT_RECONCILED',
    '{"sourceId":601}'
)
ON CONFLICT (event_id) DO NOTHING;
~~~

Publisher vẫn có thể gửi **hơn một lần** nếu bị ngắt sau khi phía nhận đã xử lý nhưng trước khi đánh dấu `sent_at`. Consumer/API đích phải xử lý lặp theo `event_id`. Outbox cung cấp cơ chế giao nhận đáng tin cậy kiểu **at-least-once** khi được triển khai đúng; không mặc nhiên bảo đảm exactly-once trên nhiều hệ thống.

Nếu workflow có nhiều thao tác không rollback được, có thể cần **trạng thái từng bước** và **compensation** (thao tác bù trừ). Một cursor duy nhất không mô tả được trạng thái “đã thanh toán nhưng chưa gửi thông báo”.

## 8. Khi xử lý song song hoặc có lỗi riêng từng item

### 8.1. Hai process cùng work key

Với hai process cùng đọc `last_committed_id=6000`, nếu không có khóa, cả hai có thể cùng xử lý 6001–6100. `SELECT ... FOR UPDATE` trong ví dụ tạo đồng bộ ở mức chunk, nhưng **không** giới hạn số process hoạt động xuyên suốt toàn bộ công việc.

Có thể bổ sung:

- Điều phối ở scheduler để không khởi chạy chồng lấn.
- Single-instance locking của Spring Cloud Task theo **tên task**, khi phù hợp và cùng kho khóa.
- Distributed lease theo **work key** nếu nhiều tên task hoặc nhiều worker khác nhau có thể thao tác cùng kỳ.
- Unique constraint/idempotency tại bảng kết quả như lớp bảo vệ cuối.

Một lease hết hạn khi process cũ vẫn còn chạy có thể tạo **split-brain**. Với tác động quan trọng, cần xét đến **fencing token** được hệ thống đích kiểm tra trước khi ghi.

### 8.2. Có item thất bại nhưng item sau đã hoàn tất

Cursor tăng dần chỉ thích hợp khi **mọi item trước ranh giới đều được giải quyết**. Nếu xử lý song song khiến `source_id=602` còn lỗi nhưng `603` đã thành công, **không được** tăng checkpoint lên 603 rồi bỏ quên 602.

Khi các item có trạng thái độc lập, dùng **bảng trạng thái từng item**:

| work_key | source_id | state | attempt_count |
| --- | --- | --- | --- |
| tenant-A:2026-11-23:v1 | 601 | COMPLETED | 1 |
| tenant-A:2026-11-23:v1 | 602 | RETRYABLE | 2 |
| tenant-A:2026-11-23:v1 | 603 | COMPLETED | 1 |

Công việc tổng chỉ được đánh dấu `COMPLETED` khi mọi item bắt buộc đã hoàn tất, hoặc có quyết định **skip** được ghi nhận theo quy tắc nghiệp vụ.

## 9. Khi nào nên chọn Spring Batch?

**Spring Batch** được thiết kế cho xử lý dữ liệu theo lô với **job/step**, checkpoint, restart, retry và skip. Các khái niệm:

- `JobRepository` quản lý `JobExecution` và `StepExecution`.
- `ExecutionContext` giữ trạng thái khôi phục; **Step ExecutionContext** được lưu ở các commit point của step xử lý chunk.
- Reader/writer được thiết kế restartable có thể dùng `ExecutionContext` để nhớ vị trí.
- `JobParameters` cùng tên job giúp xác định `JobInstance` và điều kiện restart.

Trong khi đó, **Spring Cloud Task TaskRepository chỉ lưu vòng đời ứng dụng task**. Nếu ứng dụng chạy Spring Batch bên trong Spring Cloud Task, cần phân biệt TaskExecution với JobExecution và đọc đúng repository.

| Spring Cloud Task | Spring Batch |
| --- | --- |
| Theo dõi **một lần chạy process** | Theo dõi **job và các step/chunk** |
| Mỗi lần khởi chạy có TaskExecution riêng | Restart của JobInstance có quy tắc riêng |
| Không tự cung cấp checkpoint từng item | ExecutionContext phục vụ restart theo điểm commit |
| Có thể chạy theo lịch/yêu cầu | Phù hợp khối lượng dữ liệu lớn, retry/skip và restart chi tiết |

Nếu bài toán đã là job đọc và ghi hàng triệu bản ghi với lỗi rải rác, **ưu tiên dùng cơ chế checkpoint của Spring Batch** thay vì tự xây cả framework. Với xử lý nghiệp vụ nhỏ, có business key và kết quả cùng một database, bảng progress riêng có thể đủ.

**Lưu ý:** nếu Spring Cloud Task chỉ khởi động Batch job **bất đồng bộ** rồi runner trả về, TaskExecution có thể kết thúc trước khi job thực sự xong. Phải chờ kết quả job nếu thành công của task được định nghĩa là thành công của Batch job.

## 10. Thực hành tiêm lỗi và kiểm chứng

Tạo nguồn bất biến 250 bản ghi, cho chunk size = 100 và dùng cùng work key.

### Kịch bản A: lỗi trong chunk thứ hai

1. Commit chunk 1 gồm bản ghi 1–100.
2. Trong chunk 2, cố ý ném `IllegalStateException` sau khi ghi thử một số hàng, **trước commit**.
3. Đọc `reconciliation_progress`: `last_committed_id` phải vẫn là `100`.
4. Đếm `payment_projection`: chỉ có 100 hàng đã commit.
5. Chạy lại cùng work key và xác nhận kết quả cuối đúng 250 hàng, không trùng khóa.

### Kịch bản B: crash sau commit nhưng trước log cuối

1. Commit chunk 1.
2. Giả lập mất process ngay sau transaction commit.
3. TaskRepository có thể chưa kịp ghi kết thúc; log “chunk done” có thể vắng.
4. Khởi động lại theo cùng work key. Điểm bắt đầu phải là **cursor đã commit** (`100`), không phải vị trí dự đoán từ log.

### Kịch bản C: API ngoài đã thành công nhưng trả timeout

1. Gửi cùng `event_id` cho lần yêu cầu đầu.
2. Phía nhận xử lý nhưng client nhận timeout.
3. Retry với **cùng idempotency key**.
4. Phía nhận trả lại hoặc xác nhận kết quả trước mà không tạo tác động trùng.

### Kịch bản D: hai process cùng work key

Khởi chạy đồng thời hai task kết nối cùng database. Quan sát row lock, thứ tự transaction và ràng buộc duy nhất. Trong thiết kế ví dụ, có thể có **hai process thay phiên xử lý các chunk**; kết quả cuối cần vẫn đúng. Nếu yêu cầu một process duy nhất, thêm lease/scheduler lock và kiểm thử chính sách từ chối/thử lại.

### Checklist kiểm chứng

- [ ] Work key ổn định qua retry, gắn với phạm vi/phiên bản nguồn.
- [ ] Nguồn đã chốt hoặc có manifest/snapshot đáng tin cậy.
- [ ] Có checkpoint chỉ phản ánh phần **đã commit**.
- [ ] Ghi kết quả và tăng checkpoint trong cùng transaction khi dùng cùng database.
- [ ] Lỗi trước commit không làm cursor tăng, lỗi sau commit không làm cursor lùi.
- [ ] Kết quả có khóa duy nhất hoặc cơ chế idempotency phù hợp.
- [ ] Xử lý item lỗi/skip không làm mất item chưa giải quyết.
- [ ] Có quy tắc retry giới hạn số lần, backoff, timeout và cảnh báo.
- [ ] Side effect ngoài database có idempotency key, outbox hoặc đối soát.
- [ ] TaskExecution ID được ghi log, nhưng phục hồi dựa trên work key/checkpoint.
- [ ] Có phương án cho process chết, metadata `END_TIME` trống và khóa stale.

## 11. Runbook khi một task hoàn tất một phần

Khi task báo lỗi hoặc chưa ghi nhận thời điểm kết thúc:

1. **Kiểm tra process thật:** log, pod, job, PID, timeout. `END_TIME IS NULL` trong TaskRepository không chứng minh JVM vẫn sống.
2. **Xác định work key và version nguồn:** lấy từ tham số không nhạy cảm và lịch sử yêu cầu.
3. **Đọc checkpoint đã commit:** `upper_source_id`, `last_committed_id`, `state`, `updated_at`.
4. **Đối chiếu kết quả thật:** bảng nghiệp vụ, outbox, file, API đích; xác định có side effect chưa được xác nhận không.
5. **Kiểm tra cạnh tranh:** process khác có đang xử lý cùng work key không? Lease/lock còn hợp lệ không?
6. **Chọn chính sách phục hồi:** tiếp tục từ checkpoint, retry các item lỗi, bù trừ hoặc điều tra khi metadata và kết quả mâu thuẫn.
7. **Chạy lại có kiểm soát:** dùng work key của cùng phiên bản nguồn, tạo TaskExecution mới và giám sát kết quả.
8. **Xác nhận hoàn tất:** đủ bản ghi, không trùng khóa, không còn outbox pending ngoài SLA, kết quả nghiệp vụ đúng.

Không tự đặt `last_committed_id=upper_source_id` để “xóa lỗi” hoặc reset cursor về 0 rồi chạy lại mà không kiểm tra tính idempotent.

## 12. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng taskExecutionId để định danh checkpoint | Mỗi lần chạy lại ID mới, không nối tiếp được | Dùng work key nghiệp vụ ổn định |
| Checkpoint tăng trước khi ghi kết quả | Bỏ sót dữ liệu sau crash | Commit kết quả và checkpoint cùng transaction |
| Ghi kết quả và checkpoint ở hai transaction | Phần đã ghi có thể bị xử lý lặp | Bổ sung atomicity và idempotency |
| Dùng `OFFSET` trên nguồn thay đổi | Phân trang bị lệch, đọc lại hoặc bỏ sót | Snapshot và cursor ổn định |
| Vượt cursor qua item chưa xử lý | Mất item lỗi | Per-item state, skip có ghi nhận |
| Gọi API ngoài và tin rằng rollback DB sẽ hoàn tác | Gây tác động trùng hoặc trạng thái lệch | Idempotency key, outbox hoặc đối soát |
| Chỉ kiểm tra `EXIT_CODE=0` | Runner có thể bỏ qua lỗi hoặc kết thúc trước công việc async | Định nghĩa thành công theo kết quả nghiệp vụ |
| Chỉ dùng single-instance lock để bảo đảm exactly-once | Hai lần chạy tuần tự vẫn có thể tạo trùng | Unique key/idempotency ở hệ thống đích |
| Retry vô hạn ngay lập tức | Bão tải và tăng lỗi dây chuyền | Retry có backoff, giới hạn, timeout và cảnh báo |

## 13. Ghi nhớ

**TaskRepository trả lời “lần chạy Spring Cloud Task diễn ra thế nào?”; checkpoint nghiệp vụ trả lời “công việc đã hoàn tất bền vững đến đâu và lần chạy tiếp theo bắt đầu từ vị trí nào?”.** Hai loại trạng thái liên kết qua work key và execution ID nhưng có nhiệm vụ khác nhau.

Để xử lý **hoàn tất một phần** an toàn: **chốt nguồn**, **chọn đơn vị commit**, **lưu kết quả cùng checkpoint một cách nguyên tử** và **bảo vệ các side effect không nằm trong transaction bằng idempotency/outbox/đối soát**. Khi cần chunk, skip và restart ở quy mô lớn, hãy xem xét **Spring Batch ExecutionContext** thay vì xây lại cơ chế có sẵn.

### Tài liệu tham khảo

- [Spring Cloud Task Reference Guide — vòng đời và TaskRepository](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/)
- [Spring Batch — Configuring a Job: Restartability](https://docs.spring.io/spring-batch/reference/job/configuring-job.html)
- [Spring Batch — ExecutionContext và restart](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring.html)

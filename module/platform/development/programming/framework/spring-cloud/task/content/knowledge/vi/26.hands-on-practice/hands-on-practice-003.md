# Tạo báo cáo theo ngày với xử lý lặp an toàn

Một tác vụ tạo báo cáo mỗi ngày trông có vẻ đơn giản: đọc hóa đơn đã thanh toán trong ngày, đếm số hóa đơn, tính tổng tiền, lưu một dòng báo cáo, rồi kết thúc. Nhưng trên thực tế, **cùng một ngày có thể được chạy nhiều lần** do người vận hành bấm lại, Kubernetes Job retry, lịch chạy bù, hai Pod khởi động đồng thời hoặc tiến trình chết sau khi ghi dữ liệu. Nếu mỗi lần chạy đều `INSERT` thêm một báo cáo hoặc cộng thêm tổng tiền, hệ thống sẽ xuất hiện bản ghi trùng và số liệu sai.

Bài thực hành thuộc chương **Thực hành** của **Spring Cloud Task**. Ta xây dựng một ứng dụng **Spring Boot + Spring Cloud Task + PostgreSQL** chạy hữu hạn, tạo **báo cáo hóa đơn theo ngày và tenant**, lưu kết quả bền vững, ghi lịch sử vào `TaskRepository`, rồi chứng minh bằng các phép thử rằng chạy lặp, chạy đồng thời và lỗi trước khi commit **không tạo hai báo cáo cho cùng một khóa nghiệp vụ**.

Giải pháp chính sử dụng:

- **Business key:** `(tenant_id, business_date, report_version)`.
- **Ranh giới ngày rõ ràng:** `Asia/Ho_Chi_Minh`, chuyển sang hai mốc UTC khi truy vấn `timestamptz`.
- **Một câu lệnh tổng hợp và ghi kết quả nguyên tử:** `INSERT ... SELECT ... ON CONFLICT DO NOTHING`, thực thi trong giao dịch.
- **Không cộng dồn khi retry:** nếu báo cáo đã tồn tại, trả kết quả `ALREADY_EXISTS` thay vì ghi thêm.
- **Tách trạng thái:** `TaskExecution` là lịch sử *mỗi lần chạy kỹ thuật*, còn bảng báo cáo là kết quả *mỗi kỳ nghiệp vụ*.

> **Giới hạn quan trọng:** Bài lab giả định hóa đơn nguồn của ngày đã được **chốt/đóng băng** trước khi tạo báo cáo và kết quả báo cáo được lưu **trong cùng một PostgreSQL database**. Nếu nguồn vẫn thay đổi sau thời điểm chốt, kết quả cũ không tự cập nhật; cần cơ chế phiên bản báo cáo hoặc snapshot nguồn. Nếu còn gửi email, ghi object storage hay gọi API ngoài DB, phải thiết kế outbox/idempotency riêng. Không nên hiểu một transaction SQL là bảo đảm exactly-once cho mọi hệ thống bên ngoài.

## 1. Mục tiêu và tiêu chí hoàn thành

Hoàn thành bài này, bạn sẽ có thể:

1. Chạy một file JAR Spring Cloud Task nhận `--tenant-id`, `--business-date` và `--report-version`.
2. Lấy các hóa đơn `PAID` thuộc đúng ngày địa phương, loại dữ liệu sát ranh giới nửa đêm ra đúng cách.
3. Lưu đúng **một dòng báo cáo cho mỗi `(tenant, date, version)`** bằng unique constraint trong PostgreSQL.
4. Chạy lại cùng tham số và thấy `ALREADY_EXISTS`, không tăng `invoice_count` hoặc `total_amount`.
5. Khởi chạy hai tiến trình cùng lúc và xác nhận **chỉ một kết quả nghiệp vụ được tạo**.
6. Giả lập exception sau câu lệnh ghi nhưng **trước commit**, thấy rollback; chạy lại thành công.
7. Phân biệt `TaskExecution ID` ở mỗi lần thử với business key của báo cáo.
8. Nêu được giới hạn của mẫu khi nguồn thay đổi, ghi nhiều hệ thống hoặc Task bị kill.

### Dữ liệu thử nghiệm kỳ vọng

Ta dùng ngày **23/11/2026** theo múi giờ **Việt Nam (UTC+07:00)**, tenant `acme`. Trong tập dữ liệu mẫu, chỉ có **3 hóa đơn PAID**, tổng **250,00** thuộc đúng ngày đó.

| businessDate | tenantId | reportVersion | invoiceCount | totalAmount |
| --- | --- | ---: | ---: | ---: |
| `2026-11-23` | `acme` | `1` | **3** | **250.00** |

Chạy lần đầu trả `CREATED`; lần hai với cùng ba tham số trả `ALREADY_EXISTS`; bảng báo cáo vẫn chỉ có **một** dòng. Đây là kết quả có thể kiểm chứng bằng SQL, không chỉ dựa vào log.

## 2. Kiến trúc: TaskExecution không phải báo cáo nghiệp vụ

~~~mermaid
flowchart TD
    S["CronJob / API / terminal"] --> T["Spring Boot + @EnableTask"]
    T --> TR[("TaskRepository<br/>TASK_EXECUTION")]
    T --> A["ApplicationRunner: validate args"]
    A --> B["DailyReportService @Transactional"]
    B --> Q["INSERT ... SELECT ... ON CONFLICT DO NOTHING"]
    Q --> I[("invoice: dữ liệu nguồn đã chốt")]
    Q --> R[("daily_invoice_report<br/>PRIMARY KEY tenant + date + version")]
    B --> O["CREATED / ALREADY_EXISTS"]
    O --> T
~~~

**Hai loại danh tính khác nhau:**

| Định danh | Ví dụ | Công dụng |
| --- | --- | --- |
| `TaskExecution ID` | `4101` rồi `4102` | Phân biệt hai tiến trình Spring Cloud Task |
| Business key | `acme / 2026-11-23 / v1` | Phân biệt **một báo cáo logic** |
| Kubernetes Job/Pod UID | Do cluster tạo | Điều tra một lần chạy kỹ thuật |
| Spring Batch `JobInstance` (nếu mở rộng) | Job name + identifying JobParameters | Quản lý restart/checkpoint Batch |

Một Task có thể kết thúc **thành công về kỹ thuật nhưng không ghi dòng mới**, vì bảng đã có báo cáo: đó là `ALREADY_EXISTS`, một kết quả idempotent hợp lệ. Ngược lại, một Task có thể thất bại sau khi dữ liệu nghiệp vụ đã commit trong kiến trúc phức tạp hơn; vì vậy **không dùng TaskExecution làm cơ chế chống trùng báo cáo**.

## 3. Chuẩn bị môi trường và phụ thuộc

Bạn cần:

- JDK tương thích với phiên bản Spring Boot/Spring Cloud Task của dự án; với hướng tiếp cận **Spring Boot 3.x** thường dùng **JDK 17+**.
- Maven hoặc Gradle, một ứng dụng Spring Boot có `spring-cloud-starter-task`.
- PostgreSQL cho **cả TaskRepository và các bảng lab**; tập thực hành sử dụng **một DataSource** để đơn giản hóa giao dịch.
- Quyền tạo bảng cho tài khoản migration và quyền đọc/ghi cho tài khoản Task.
- Khả năng chạy cùng JAR nhiều lần, hoặc tùy chọn Kubernetes Job khi thực hành phần nâng cao.

### 3.1. Dependency Maven

Trong `pom.xml` của dự án Spring Boot đã cấu hình **Spring Cloud BOM tương thích**, các dependency chính là:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là đoạn dependency, **không phải `pom.xml` hoàn chỉnh**. Hãy khai báo `spring-boot-starter-parent`/plugin và Spring Cloud release train theo BOM **đúng phiên bản** bạn đã chọn. Không tự trộn các version Spring Boot và Spring Cloud Task chỉ vì dependency resolve được.

Trong bài dùng **JDBC đơn giản** thay cho Spring Batch. Spring Cloud Task vẫn cung cấp quản lý vòng đời và metadata; nếu sau này khối lượng lớn cần chunk/checkpoint, có thể thay lõi tổng hợp bằng Spring Batch nhưng giữ nguyên business key và yêu cầu idempotency.

### 3.2. Cấu hình ứng dụng

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: daily-invoice-report-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
    hikari:
      maximum-pool-size: 3
  cloud:
    task:
      initialize-enabled: false
      closecontext-enabled: true
~~~

**Tại sao chọn như vậy?** `web-application-type: none` tránh giữ server HTTP sống sau khi runner xong. `closecontext-enabled: true` giúp đóng context sau vòng đời Task. Pool 3 connection chỉ là điểm khởi đầu cho Task nhỏ, cần đo lại khi tăng concurrency.

`initialize-enabled: false` chỉ đúng khi **schema TaskRepository đã được migration trước đó** bằng DDL tương thích phiên bản Spring Cloud Task. Bài sẽ tạo riêng hai bảng nghiệp vụ, **không tự viết DDL `TASK_EXECUTION`**. Nếu thiếu bảng metadata, Task có thể lỗi ngay khi startup; hãy chạy migration schema Task do phiên bản thư viện cung cấp, không tạo bảng thủ công bằng cách đoán cấu trúc.

Không đặt mật khẩu thật trong YAML/CLI. Cung cấp `TASK_DB_URL`, `TASK_DB_USER`, `TASK_DB_PASSWORD` qua biến môi trường/Secret. **Spring Cloud Task có thể lưu arguments vào `TASK_EXECUTION_PARAMS`**, do đó tuyệt đối không truyền `--spring.datasource.password=...` khi chạy Task.

## 4. Tạo schema nghiệp vụ

Các đoạn sau chạy trên **PostgreSQL của môi trường lab**, không dùng trực tiếp trên production.

### 4.1. Bảng hóa đơn nguồn

~~~sql
CREATE TABLE invoice (
    id          bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id   varchar(64) NOT NULL,
    paid_at     timestamptz NOT NULL,
    status      varchar(16) NOT NULL,
    amount      numeric(18, 2) NOT NULL CHECK (amount >= 0)
);

CREATE INDEX idx_invoice_paid_tenant_time
    ON invoice (tenant_id, paid_at)
    WHERE status = 'PAID';
~~~

`paid_at` được lưu dạng `timestamptz`, biểu diễn **một thời điểm tuyệt đối**. Khi báo cáo theo ngày tại Việt Nam, không so sánh chuỗi `YYYY-MM-DD` trực tiếp với timestamp mà bỏ qua timezone.

Bảng mẫu đơn giản hóa hành vi: `status` của hóa đơn đã được xác nhận trước thời điểm phát hành và không đổi trong kỳ báo cáo đã chốt. Trong hệ thống thật, cần phân tích dữ liệu trả muộn, hoàn tiền, huỷ đơn và yêu cầu phát hành lại.

### 4.2. Bảng báo cáo có khóa chống trùng

~~~sql
CREATE TABLE daily_invoice_report (
    tenant_id       varchar(64) NOT NULL,
    business_date   date NOT NULL,
    report_version  integer NOT NULL CHECK (report_version >= 1),
    invoice_count   bigint NOT NULL CHECK (invoice_count >= 0),
    total_amount    numeric(20, 2) NOT NULL,
    generated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, business_date, report_version)
);
~~~

**PRIMARY KEY ba cột là hàng rào chống trùng quyết định.** Hai tiến trình đồng thời có thể đều vượt qua kiểm tra “chưa tồn tại” ở tầng Java, nhưng DB chỉ cho phép **một dòng** với cùng `(tenant_id, business_date, report_version)`.

Vì vậy, **không dùng kiểm tra trước kiểu này làm bảo vệ duy nhất**:

~~~text
if (!reportExists(tenant, date)) {
    insertReport(tenant, date);
}
~~~

Đó là lỗi *check-then-act*: hai Pod có thể cùng thấy chưa tồn tại rồi cùng chèn. Cần **unique constraint + câu lệnh nguyên tử**, hoặc cơ chế khóa có tính nhất quán tương đương.

### 4.3. Seed dữ liệu có ranh giới ngày

Chỉ trong database lab vừa tạo bảng; **không chạy `TRUNCATE` trên dữ liệu thật**:

~~~sql
TRUNCATE TABLE daily_invoice_report, invoice RESTART IDENTITY;

INSERT INTO invoice (tenant_id, paid_at, status, amount)
VALUES
  ('acme', '2026-11-22T16:59:59+00:00', 'PAID', 100.00),
  ('acme', '2026-11-22T17:00:00+00:00', 'PAID', 120.00),
  ('acme', '2026-11-23T05:30:00+00:00', 'PAID',  80.00),
  ('acme', '2026-11-23T16:59:59+00:00', 'PAID',  50.00),
  ('acme', '2026-11-23T17:00:00+00:00', 'PAID', 300.00),
  ('acme', '2026-11-23T06:00:00+00:00', 'CANCELLED', 70.00),
  ('beta', '2026-11-23T07:00:00+00:00', 'PAID', 999.00);
~~~

Ngày **2026-11-23** ở `Asia/Ho_Chi_Minh` tương đương:

~~~text
startInclusive = 2026-11-22T17:00:00Z
endExclusive   = 2026-11-23T17:00:00Z

Điều kiện: startInclusive <= paid_at < endExclusive
~~~

| Dữ liệu | Kết quả |
| --- | --- |
| `acme`, 22/11 16:59:59Z, 100 | Loại: trước đầu ngày |
| `acme`, 22/11 17:00:00Z, 120 | **Lấy** |
| `acme`, 23/11 05:30:00Z, 80 | **Lấy** |
| `acme`, 23/11 16:59:59Z, 50 | **Lấy** |
| `acme`, 23/11 17:00:00Z, 300 | Loại: sang ngày kế tiếp |
| `acme`, `CANCELLED`, 70 | Loại: chưa PAID |
| `beta`, 23/11 07:00Z, 999 | Loại: tenant khác |

**Kỳ vọng chính xác:** `invoice_count=3`, `total_amount=250.00`. Tập seed này kiểm tra được cả timezone, tenant, trạng thái và ranh giới nửa mở.

## 5. Java: nhận tham số và kết thúc đúng vòng đời

Tạo `DailyInvoiceReportTaskApplication.java`:

~~~java
package example.reporting;

import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class DailyInvoiceReportTaskApplication {

    public static void main(String[] args) {
        SpringApplication.run(DailyInvoiceReportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner reportRunner(DailyReportService service) {
        return args -> {
            String tenant = required(args, "tenant-id");
            LocalDate date = parseDate(required(args, "business-date"));
            int version = parseVersion(required(args, "report-version"));

            // Chỉ dùng trong lab để kiểm tra transaction rollback.
            // Loại bỏ công tắc này trước khi đưa production.
            boolean failBeforeCommit =
                    args.containsOption("lab-fail-before-commit");

            boolean created = service.generate(
                    tenant, date, version, failBeforeCommit);

            System.out.printf(
                    "report tenant=%s date=%s version=%d outcome=%s%n",
                    tenant,
                    date,
                    version,
                    created ? "CREATED" : "ALREADY_EXISTS");
        };
    }

    private static String required(ApplicationArguments args, String key) {
        List<String> values = args.getOptionValues(key);
        if (values == null || values.size() != 1
                || values.get(0) == null || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Missing or invalid option: " + key);
        }
        return values.get(0);
    }

    private static LocalDate parseDate(String value) {
        try {
            return LocalDate.parse(value); // yyyy-MM-dd
        } catch (DateTimeParseException ex) {
            throw new IllegalArgumentException(
                    "Invalid --business-date; expected yyyy-MM-dd");
        }
    }

    private static int parseVersion(String value) {
        try {
            int version = Integer.parseInt(value);
            if (version < 1) {
                throw new NumberFormatException();
            }
            return version;
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "Invalid --report-version; expected positive integer");
        }
    }
}
~~~

**Giải thích:**

- `@EnableTask` bật cơ chế lifecycle Spring Cloud Task; các runner được gọi trong lần khởi động.
- `ApplicationArguments` đọc option như `--tenant-id=acme`; chuỗi phải có **`--`** khi code đọc qua `getOptionValues`.
- Không in toàn bộ `args.getSourceArgs()` vì có thể làm lộ dữ liệu nhạy cảm hoặc thông tin cá nhân. Ví dụ chỉ log ba giá trị đã được phân loại cho phép.
- Nếu validation hoặc service ném exception, runner **không được nuốt lỗi**; cần kiểm tra mã thoát ứng dụng để scheduler thấy Task thất bại.
- `ALREADY_EXISTS` không phải lỗi: đó là hành vi **no-op có chủ đích** khi một kỳ báo cáo đã phát hành.
- Công tắc `--lab-fail-before-commit` chỉ là công cụ tạo lỗi trong lab, **không giữ trong bản production**.

Ứng dụng không chạy HTTP server và runner xử lý **đồng bộ**, nên khi hoàn tất, Spring Cloud Task có thể ghi kết quả và đóng context. Nếu sau này service gọi `CompletableFuture`, phải chờ Future thực sự kết thúc trước khi runner trả về.

## 6. Java: tổng hợp và ghi báo cáo nguyên tử

Tạo `DailyReportService.java` trong cùng package:

~~~java
package example.reporting;

import java.sql.Date;
import java.sql.Types;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DailyReportService {

    private static final ZoneId BUSINESS_ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    private static final String INSERT_REPORT = """
        INSERT INTO daily_invoice_report (
            tenant_id,
            business_date,
            report_version,
            invoice_count,
            total_amount,
            generated_at
        )
        SELECT :tenantId,
               :businessDate,
               :reportVersion,
               COUNT(i.id),
               COALESCE(SUM(i.amount), 0),
               CURRENT_TIMESTAMP
        FROM invoice i
        WHERE i.tenant_id = :tenantId
          AND i.status = 'PAID'
          AND i.paid_at >= :fromUtc
          AND i.paid_at < :toUtc
        ON CONFLICT (tenant_id, business_date, report_version)
        DO NOTHING
        """;

    private final NamedParameterJdbcTemplate jdbc;

    public DailyReportService(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean generate(
            String tenantId,
            LocalDate businessDate,
            int reportVersion,
            boolean labFailBeforeCommit) {

        if (tenantId == null ||
                !tenantId.matches("[a-z0-9][a-z0-9_-]{0,63}")) {
            throw new IllegalArgumentException(
                    "Invalid tenant-id format");
        }
        if (businessDate == null || reportVersion < 1) {
            throw new IllegalArgumentException(
                    "Invalid report date or version");
        }

        Instant from = businessDate
                .atStartOfDay(BUSINESS_ZONE)
                .toInstant();
        Instant to = businessDate.plusDays(1)
                .atStartOfDay(BUSINESS_ZONE)
                .toInstant();

        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("tenantId", tenantId)
                .addValue("businessDate",
                          Date.valueOf(businessDate), Types.DATE)
                .addValue("reportVersion", reportVersion)
                .addValue("fromUtc",
                          OffsetDateTime.ofInstant(from, ZoneOffset.UTC),
                          Types.TIMESTAMP_WITH_TIMEZONE)
                .addValue("toUtc",
                          OffsetDateTime.ofInstant(to, ZoneOffset.UTC),
                          Types.TIMESTAMP_WITH_TIMEZONE);

        int insertedRows = jdbc.update(INSERT_REPORT, params);

        // Chỉ dành cho lab: chứng minh exception rollback dòng vừa ghi.
        if (labFailBeforeCommit) {
            throw new IllegalStateException(
                    "LAB_SIMULATED_FAILURE_BEFORE_COMMIT");
        }

        if (insertedRows != 0 && insertedRows != 1) {
            throw new IllegalStateException(
                    "Unexpected number of report rows");
        }
        return insertedRows == 1;
    }
}
~~~

### 6.1. Vì sao dùng INSERT ... SELECT ... ON CONFLICT?

Đây là **một câu lệnh SQL** thực hiện cả việc tổng hợp và chèn một bản ghi. Nó tránh vòng “SELECT kiểm tra → tính toán bên ngoài → INSERT” dễ bị race giữa hai tiến trình. PostgreSQL thực thi mỗi statement nguyên tử; `@Transactional` còn cho phép kiểm chứng rollback trước commit và là nơi mở rộng nếu sau này cần ghi thêm outbox trong cùng transaction.

Khi hai giao dịch cùng cố ghi **cùng primary key**:

- Giao dịch đầu thành công và commit: nó tạo **một báo cáo**.
- Giao dịch còn lại gặp conflict: với `ON CONFLICT DO NOTHING`, số hàng chèn là **0**; ứng dụng trả `ALREADY_EXISTS`.
- Nếu giao dịch đầu lỗi **trước commit** và rollback: giao dịch sau có thể tiếp tục chèn; không có dòng báo cáo dở dang đã commit.

Ở mức isolation mặc định `READ COMMITTED` của PostgreSQL, tình huống tranh chấp có thể phải **chờ giao dịch còn lại** xác định commit hay rollback. Không suy luận rằng hai Pod không bao giờ chờ nhau; điều được giữ vững là **không chèn trùng business key** khi ràng buộc DB còn hiệu lực.

### 6.2. Vì sao không dùng phép cộng dồn?

Sai với một báo cáo theo ngày đã chốt:

~~~sql
-- PHẢN VÍ DỤ: retry có thể cộng thêm lần nữa.
UPDATE daily_invoice_report
SET total_amount = total_amount + :new_amount
WHERE tenant_id = :tenant_id
  AND business_date = :business_date;
~~~

Nếu ứng dụng chạy lại sau khi giao dịch này đã commit, tổng tiền bị cộng đôi. Bài lab **tính tổng tuyệt đối** từ nguồn và chỉ **INSERT một lần**. `ON CONFLICT DO NOTHING` giữ nguyên bản phát hành cũ.

Một lựa chọn khác trong bài toán có thể tính lại là `ON CONFLICT DO UPDATE SET total_amount = EXCLUDED.total_amount` (gán giá trị tuyệt đối). Nhưng nếu nguồn đã thay đổi, chạy lại sẽ **thay báo cáo đã phát hành**; đó là một chính sách khác, không phải hành vi mong muốn của bài lab.

### 6.3. Vì sao cần chốt dữ liệu nguồn?

Câu lệnh `SELECT` đọc một snapshot giao dịch tại thời điểm thực thi. Nếu hóa đơn trễ đến **sau lần chạy đầu**, retry cùng `reportVersion=1` sẽ thấy conflict và **không thay kết quả**. Đây là tính **bất biến của bản báo cáo đã phát hành**, không phải đảm bảo hóa đơn trễ tự động được bổ sung.

Trong production, cần một quy trình trước khi launch báo cáo:

1. Đợi các nguồn dữ liệu cho `businessDate` hoàn tất/được chốt.
2. Ghi trạng thái nguồn **READY/FINALIZED** hoặc snapshot/version bất biến.
3. Chỉ launch báo cáo khi nguồn đã sẵn sàng, cùng timezone và tập dữ liệu nhất quán.
4. Nếu cần sửa dữ liệu sau khi đã phát hành, chạy **`reportVersion=2`** theo chính sách phát hành lại, giữ lịch sử v1 để đối soát.

Mẫu code hiện tại **giả định bước chốt nguồn được thực hiện bên ngoài**, không tự kiểm tra trạng thái READY. Để production hóa, hãy đưa điều kiện READY/snapshot vào **cùng ranh giới giao dịch hoặc quy trình điều phối đáng tin cậy**, tránh báo cáo rỗng do nguồn chưa đến.

## 7. Chạy lần đầu: báo cáo được tạo

Trước tiên cấu hình môi trường cho JDBC; ví dụ:

~~~text
TASK_DB_URL=jdbc:postgresql://db.example.internal:5432/task_lab
TASK_DB_USER=task_runtime
TASK_DB_PASSWORD=<lấy từ secret store; không truyền qua CLI>
~~~

Các giá trị chỉ mô tả biến cấu hình, không yêu cầu nhập mật khẩu thật vào câu lệnh shell hay log. Cần đảm bảo TaskRepository schema đã được migration và hai bảng nghiệp vụ đã tạo trước đó.

Build dự án bằng quy trình Maven thông thường, ví dụ:

~~~bash
mvn -DskipTests package
~~~

Bài viết không thực thi lệnh này; khi triển khai thật, thay tên JAR trong các lệnh dưới đây theo artifact được tạo. Chạy lần đầu:

~~~bash
java -jar target/daily-invoice-report-task.jar \
  --tenant-id=acme \
  --business-date=2026-11-23 \
  --report-version=1
~~~

Log ứng dụng do runner in (minh họa):

~~~text
report tenant=acme date=2026-11-23 version=1 outcome=CREATED
~~~

Truy vấn kết quả trong PostgreSQL:

~~~sql
SELECT tenant_id,
       business_date,
       report_version,
       invoice_count,
       total_amount,
       generated_at
FROM daily_invoice_report
ORDER BY tenant_id, business_date, report_version;
~~~

Kỳ vọng **một dòng**: `acme` / `2026-11-23` / v1 / `3` / `250.00`. `generated_at` là thời điểm database ghi báo cáo; nó **không phải** businessDate.

### 7.1. Xác nhận tổng trực tiếp từ nguồn

~~~sql
SELECT COUNT(*) AS invoice_count,
       COALESCE(SUM(amount), 0) AS total_amount
FROM invoice
WHERE tenant_id = 'acme'
  AND status = 'PAID'
  AND paid_at >= TIMESTAMPTZ '2026-11-22T17:00:00+00:00'
  AND paid_at <  TIMESTAMPTZ '2026-11-23T17:00:00+00:00';
~~~

Kết quả phải là `3` và `250.00`. Nếu khác, kiểm tra dữ liệu seed, timezone, filter trạng thái và điều kiện `< endExclusive`.

## 8. Chạy lại cùng tham số: không tạo bản ghi trùng

Thực hiện lại đúng lệnh:

~~~bash
java -jar target/daily-invoice-report-task.jar \
  --tenant-id=acme \
  --business-date=2026-11-23 \
  --report-version=1
~~~

Lần này runner dự kiến in:

~~~text
report tenant=acme date=2026-11-23 version=1 outcome=ALREADY_EXISTS
~~~

Kiểm chứng trực tiếp:

~~~sql
SELECT COUNT(*) AS reports,
       MIN(invoice_count) AS invoice_count,
       MIN(total_amount) AS total_amount
FROM daily_invoice_report
WHERE tenant_id = 'acme'
  AND business_date = DATE '2026-11-23'
  AND report_version = 1;
~~~

**Kết quả kỳ vọng:** `reports=1`, `invoice_count=3`, `total_amount=250.00`. Nếu chạy 10 lần nữa, kết quả vẫn như vậy.

**Hai lần chạy Java không dùng chung một TaskExecution.** Nếu cả hai tiến trình hoàn tất và ghi metadata bình thường, TaskRepository sẽ có **hai lần thực thi kỹ thuật**, nhưng bảng nghiệp vụ chỉ có **một báo cáo logic**. Đây là tính chất quan trọng nhất của bài.

### 8.1. Đối chiếu TaskRepository

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-invoice-report-task'
ORDER BY START_TIME DESC;
~~~

Thông thường mỗi lần chạy có `TASK_EXECUTION_ID` khác nhau. `EXIT_CODE=0` chỉ xác nhận tiến trình đã hoàn tất về kỹ thuật; **không có nghĩa lần nào cũng chèn dòng mới**. Hành vi `ALREADY_EXISTS` là no-op hợp lệ khi đã có bản báo cáo v1.

Lưu ý: TaskRepository và bảng nghiệp vụ **có thể** không đồng thời ghi thành công nếu chúng nằm trong các giao dịch khác nhau hoặc Task bị kill. Vì thế, luôn dựa vào **business key** khi xác định có nên chạy lại nghiệp vụ, không chỉ dựa vào exit code của Task.

## 9. Kiểm tra lỗi trước commit và chạy lại an toàn

Đây là bước chứng minh rollback. Sử dụng một business key **chưa tồn tại**, ví dụ v2, sau khi dữ liệu nguồn đã chốt. Lần chạy đầu cố ý ném exception **sau `jdbc.update` nhưng trước khi method `@Transactional` kết thúc**:

~~~bash
java -jar target/daily-invoice-report-task.jar \
  --tenant-id=acme \
  --business-date=2026-11-23 \
  --report-version=2 \
  --lab-fail-before-commit
~~~

Kỳ vọng Task **thất bại** và giao dịch **rollback**. Kiểm chứng:

~~~sql
SELECT COUNT(*) AS reports_v2
FROM daily_invoice_report
WHERE tenant_id = 'acme'
  AND business_date = DATE '2026-11-23'
  AND report_version = 2;
~~~

Kết quả phải là `reports_v2=0`. Nếu vẫn có v2, cần điều tra `@Transactional` có chạy qua Spring proxy không, `NamedParameterJdbcTemplate` có dùng đúng transaction manager/DataSource không, và lỗi có bị catch rồi nuốt bên trong service không.

Chạy lại, **bỏ cờ thử lỗi**:

~~~bash
java -jar target/daily-invoice-report-task.jar \
  --tenant-id=acme \
  --business-date=2026-11-23 \
  --report-version=2
~~~

Bây giờ dự kiến `CREATED` và có **một** báo cáo v2. Bản v1 vẫn ở nguyên; hai version là **hai business key khác nhau**, không phải hai dòng trùng. Trong production, việc tạo v2 phải là **quyết định phát hành lại có kiểm soát**, không phải thủ thuật tự tăng phiên bản khi retry.

### 9.1. Nếu tiến trình chết sau commit nhưng trước khi ghi END?

~~~text
1. Database đã commit daily_invoice_report(v1).
2. Pod/JVM chết trước khi TaskRepository ghi trạng thái cuối.
3. Người vận hành thấy TaskExecution chưa có END_TIME.
4. Retry cùng business key v1.
5. INSERT ... ON CONFLICT DO NOTHING => ALREADY_EXISTS.
~~~

Đây là lý do thiết kế **idempotency ở database nghiệp vụ** cần độc lập với metadata Task. Ngược lại, nếu Pod chết **trước commit**, transaction chưa commit bị PostgreSQL rollback khi connection bị hủy; lần chạy sau có thể tạo báo cáo.

Một Task bị `SIGKILL` có thể không chạy `finally`, TaskExecution listener hoặc context shutdown. Không coi `END_TIME IS NULL` là bằng chứng báo cáo chưa được lưu; kiểm tra **bảng `daily_invoice_report` và tình trạng Pod**.

## 10. Kiểm tra hai tiến trình chạy đồng thời

Trong môi trường lab, chọn **một business key mới** (ví dụ `reportVersion=3`), rồi khởi chạy **hai JVM cùng lúc**. Trên một shell hỗ trợ Bash:

~~~bash
java -jar target/daily-invoice-report-task.jar \
  --tenant-id=acme --business-date=2026-11-23 --report-version=3 &

java -jar target/daily-invoice-report-task.jar \
  --tenant-id=acme --business-date=2026-11-23 --report-version=3 &

wait
~~~

Hai tiến trình đều có thể đọc hóa đơn, nhưng cùng cố INSERT một unique key. Kết quả dự kiến:

~~~text
Một tiến trình: outcome=CREATED
Tiến trình còn lại: outcome=ALREADY_EXISTS
~~~

**Thứ tự log không cố định** và một tiến trình có thể chờ khóa index/transaction của tiến trình còn lại. Sau khi cả hai kết thúc, truy vấn:

~~~sql
SELECT COUNT(*) AS reports_v3,
       SUM(total_amount) AS sum_of_report_rows
FROM daily_invoice_report
WHERE tenant_id = 'acme'
  AND business_date = DATE '2026-11-23'
  AND report_version = 3;
~~~

Kỳ vọng `reports_v3=1` và `sum_of_report_rows=250.00`. Nếu test tạo hai dòng, khả năng cao schema không có primary key đúng, hai tiến trình ghi **khác database/schema**, hoặc khóa đang dùng không chứa đủ ba thành phần.

### 10.1. Vì sao không chỉ dùng synchronized hoặc CronJob Forbid?

- `synchronized` trong Java chỉ khóa trong **một JVM**, không bảo vệ hai Pod.
- `concurrencyPolicy: Forbid` chỉ giới hạn Job sinh từ **cùng một Kubernetes CronJob**, không chặn Job do người vận hành chạy thủ công hoặc một CronJob khác.
- `spring.cloud.task.single-instance-enabled` (nếu dùng cơ chế khóa JDBC tương thích) bảo vệ theo **tên Task** ở phạm vi kho khóa chung, không nhất thiết theo tenant/ngày/version.
- **Unique constraint ở DB** vẫn là hàng rào cuối cho business key của báo cáo.

Trong ví dụ này, hai Pod chạy đồng thời **không làm sai kết quả**, dù có thể tiêu tốn CPU/SQL thừa do cùng tổng hợp đầu vào. Nếu truy vấn nặng hàng giờ, cần thiết kế cơ chế **claim + lease + fencing** theo business key để tránh hai Pod cùng tốn tài nguyên; không đưa khóa đơn giản thiếu TTL vào production.

## 11. Ngày nghiệp vụ, timezone và lịch chạy

Giả sử báo cáo “ngày hôm qua” chạy lúc 02:00 Việt Nam:

~~~text
Mốc lịch:     2026-11-24 02:00 Asia/Ho_Chi_Minh
businessDate: 2026-11-23
~~~

**Nên truyền ngày cụ thể** từ bộ điều phối:

~~~text
--tenant-id=acme
--business-date=2026-11-23
--report-version=1
~~~

Không truyền giá trị trừu tượng `--business-date=yesterday` trong hệ thống cần backfill/retry chính xác. Nếu một Pod chạy trễ đến 26/11 và tự tính “hôm qua” dựa vào đồng hồ hiện tại, nó sẽ xử lý nhầm **25/11** thay vì kỳ 23/11.

Kubernetes CronJob `jobTemplate.args` là **mẫu cố định**; Kubernetes không tự thay ngày trong `--business-date=...` ở mỗi lượt. Với nhu cầu ngày biến đổi, có thể dùng một **launcher** đọc mốc lịch rồi tạo Job mang tham số ngày bất biến hoặc một workflow/scheduler bên ngoài.

### 11.1. Job manifest minh họa cho một kỳ cụ thể

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: invoice-report-acme-20261123-v1
  namespace: batch-jobs
spec:
  backoffLimit: 2
  activeDeadlineSeconds: 900
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: report-task
          image: registry.example.com/batch/daily-invoice-report-task:1.0.0
          args:
            - "--tenant-id=acme"
            - "--business-date=2026-11-23"
            - "--report-version=1"
          envFrom:
            - secretRef:
                name: task-db-runtime
~~~

Đây là **ví dụ Job tĩnh**, không phải CronJob sinh ngày tự động. Secret `task-db-runtime` phải cấp các biến `TASK_DB_URL`, `TASK_DB_USER` và `TASK_DB_PASSWORD`; namespace, image, ServiceAccount, resources và policy phải được điều chỉnh cho môi trường thật.

Retry của **cùng Kubernetes Job** giữ cùng `args` trong Pod template; không dùng Pod UID hoặc TaskExecution ID như một tham số đổi bản báo cáo. Nếu cần chạy lại một Job đã hoàn tất, dùng tên Job mới hoặc launcher đúng quy trình nhưng **giữ nguyên business key**; phía PostgreSQL sẽ bảo vệ idempotency.

### 11.2. Ranh giới ngày trong các múi giờ có DST

Bài dùng Việt Nam, nơi không áp dụng DST trong lịch hiện tại. Nhưng cách tính bằng:

~~~java
Instant from = businessDate.atStartOfDay(zone).toInstant();
Instant to = businessDate.plusDays(1).atStartOfDay(zone).toInstant();
~~~

vẫn phù hợp với những timezone có ngày địa phương dài 23 hoặc 25 giờ. Tránh dùng `from.plus(Duration.ofHours(24))` nếu nghiệp vụ là **ngày theo lịch địa phương**. Truy vấn với điều kiện `>= from` và `< to` cũng ngăn double-count ở mốc cuối ngày khi hai kỳ liền kề chạy.

## 12. Đầu vào thay đổi và chính sách tái phát hành

Có hai kiểu yêu cầu khác nhau:

| Yêu cầu | Hành vi nên chọn |
| --- | --- |
| **Retry cùng kỳ đã công bố** | Giữ version, `ON CONFLICT DO NOTHING`, kết quả `ALREADY_EXISTS` |
| **Lỗi trước commit** | Giữ version, transaction rollback, retry có thể tạo bản báo cáo |
| **Hóa đơn nguồn đến trễ** | Cần quy trình phát hành lại, thường tăng `reportVersion` có kiểm soát |
| **Cần sửa sai số liệu đã công bố** | Tạo version mới hoặc bản sửa có audit trail; không âm thầm cộng/ghi đè |
| **Yêu cầu kết quả theo snapshot nguồn** | Chốt input revision/high-water mark và dùng cùng snapshot cho mọi lần thử |
| **Hai phiên bản báo cáo chạy song song** | Cần chính sách cho phép/từ chối version cũ, và báo cáo “latest” đúng quy tắc |

### 12.1. Thực hành dữ liệu đến trễ

Sau khi đã có v1, thêm một hóa đơn `acme` đã thanh toán trong ngày 23/11:

~~~sql
INSERT INTO invoice (tenant_id, paid_at, status, amount)
VALUES ('acme', '2026-11-23T10:00:00+00:00', 'PAID', 200.00);
~~~

Trong **lab giả lập sửa nguồn sau khi đã chốt**, chạy lại **v1**:

~~~bash
java -jar target/daily-invoice-report-task.jar \
  --tenant-id=acme --business-date=2026-11-23 --report-version=1
~~~

Kết quả vẫn `ALREADY_EXISTS` và báo cáo v1 giữ **3 hóa đơn, 250.00**. Nếu **được phê duyệt** phát hành v4 trên tập dữ liệu mới (giả sử các version trước đó là v1/v2/v3), chạy:

~~~bash
java -jar target/daily-invoice-report-task.jar \
  --tenant-id=acme --business-date=2026-11-23 --report-version=4
~~~

Kỳ vọng v4 có **4 hóa đơn, 450.00**, trong khi v1 không đổi. Đây là **versioning có chủ đích**, không phải “retry thì tự tăng version”. Trong production, phải lưu thêm lý do sửa, người yêu cầu, input revision và quy tắc chọn version hiện hành.

**Giới hạn của mẫu:** báo cáo v4 đọc dữ liệu tại thời điểm thực thi. Nếu hóa đơn vẫn thay đổi liên tục trong khi tạo, cần snapshot hoặc điều kiện READY xác định nguồn đã ổn định; chỉ thêm version không tự tạo snapshot.

## 13. Nếu báo cáo còn phải phát email hoặc file bên ngoài?

Ghi một dòng vào PostgreSQL trong transaction **không bảo đảm** email chỉ được gửi một lần. Kịch bản nguy hiểm:

~~~text
COMMIT báo cáo v1
   → gọi API gửi email
   → tiến trình chết trước khi nhận phản hồi
   → retry thấy báo cáo đã có và bỏ qua
   → không biết email đã gửi hay chưa
~~~

Hoặc gửi email **trước commit**: gửi thành công nhưng transaction rollback, khiến lần retry gửi lại. Không có thứ tự gọi đơn giản nào giải quyết đồng thời cả hai vấn đề.

Giải pháp thường dùng là **transactional outbox**:

1. Trong **cùng transaction** tạo `daily_invoice_report`, ghi thêm một bản ghi outbox có event key duy nhất, ví dụ `report:acme:2026-11-23:v1`.
2. Một publisher riêng đọc outbox sau commit và gửi message/email/upload với retry.
3. Consumer/đích phải hỗ trợ **idempotency key**, hoặc publisher phải có trạng thái giao hàng và cơ chế đối soát.
4. Khi Task bị kill giữa đường, outbox vẫn còn để publisher phục hồi.

~~~mermaid
flowchart LR
    T["Task @Transactional"] --> R[("daily_invoice_report")]
    T --> O[("report_outbox")]
    O --> P["Publisher độc lập + retry"]
    P --> X["Email / object storage / API"]
    X --> K["Idempotency key / deduplication"]
~~~

Một bảng outbox tối giản có thể là:

~~~sql
CREATE TABLE report_outbox (
    event_key   varchar(200) PRIMARY KEY,
    tenant_id   varchar(64) NOT NULL,
    business_date date NOT NULL,
    report_version integer NOT NULL,
    status      varchar(20) NOT NULL DEFAULT 'PENDING',
    created_at  timestamptz NOT NULL DEFAULT now()
);
~~~

Bảng này là **hướng mở rộng** chứ code `DailyReportService` hiện tại **chưa ghi outbox**. Để triển khai, thêm `INSERT INTO report_outbox...ON CONFLICT DO NOTHING` vào **cùng method `@Transactional`**, chỉ khi tạo bản báo cáo mới, sau đó xây publisher/retry/dead-letter và idempotency ở đích. Không đánh dấu `SENT` ngay khi mới gửi request mà chưa có xác nhận phù hợp.

## 14. Bảng kiểm thử bắt buộc

| ID | Cách thử | Kết quả đúng |
| --- | --- | --- |
| **T1** | Chạy v1 lần đầu | `CREATED`; một dòng `3 / 250.00` |
| **T2** | Chạy lại v1 lần hai | `ALREADY_EXISTS`; kết quả không đổi |
| **T3** | Chạy 10 lần cùng v1 | Vẫn chỉ một dòng |
| **T4** | Hai JVM cùng chạy v3 | Một `CREATED`, một `ALREADY_EXISTS`; một dòng |
| **T5** | v2 có `--lab-fail-before-commit` | Task lỗi; không tồn tại dòng v2 |
| **T6** | Bỏ cờ lỗi, chạy lại v2 | `CREATED`; một dòng v2 |
| **T7** | Tenant khác cùng ngày/version | Được tạo riêng; không ảnh hưởng `acme` |
| **T8** | Ngày kế tiếp cùng tenant/version | Được tạo riêng; không chồng khoảng thời gian |
| **T9** | Seed sát 17:00Z và `CANCELLED` | Chỉ nhận 3 hóa đơn `acme` phù hợp |
| **T10** | Dữ liệu đến trễ sau v1 | v1 không đổi; version mới tính theo nguồn mới |
| **T11** | Process bị kill trước/sau commit | Đối soát DB để quyết định retry, không tin mỗi `END_TIME` |
| **T12** | Thiếu `--business-date` hoặc version không hợp lệ | Runner fail fast; không ghi báo cáo |
| **T13** | DB ngừng hoạt động | Task báo lỗi; không coi là báo cáo hoàn tất |
| **T14** | Nhiều Pod CronJob đồng thời | DB vẫn chặn duplicate theo business key |

**Bằng chứng cần lưu khi làm bài:** log `CREATED/ALREADY_EXISTS`, hai execution ID khác nhau, kết quả SQL ở các version, câu lệnh test song song và dấu vết rollback. Với lỗi cố ý, phải xác nhận **không có dữ liệu dở dang** thay vì chỉ kiểm tra Java in exception.

## 15. Các sai lầm phổ biến và cách khắc phục

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| Dùng `TaskExecution ID` làm business key | Retry có TaskExecution ID mới | Dùng tenant/date/version |
| Chỉ `if (!exists) insert()` | Race condition giữa Pod | Unique constraint + atomic INSERT |
| `total = total + newTotal` khi retry | Dễ cộng đôi | Tổng tuyệt đối và insert-once/versioning |
| Không đặt businessDate tường minh | Retry/chạy trễ có thể đổi ngày | Chốt ngày tại launcher |
| So sánh `DATE(paid_at)` theo timezone DB | Có thể lệch ngày, khó dùng index | Chuyển mốc theo business zone rồi query `[from,to)` |
| Dùng `<= end` | Dòng đúng nửa đêm bị tính hai ngày | Dùng `< endExclusive` |
| Bỏ `@Transactional` rồi thêm nhiều câu SQL liên quan | Có thể commit một phần khi bước sau lỗi | Transaction cho toàn bộ thay đổi cần atomic |
| Gọi method transaction bằng `this.generate()` | Spring proxy có thể không kích hoạt advice | Gọi qua Spring-managed service bean |
| Có unique key nhưng DB khác nhau | Hai process không chia sẻ ràng buộc | Đảm bảo cùng DB/schema authoritative |
| Nuốt exception và trả exit 0 | Scheduler tưởng công việc thành công | Propagate lỗi và kiểm tra exit code |
| Hóa đơn đến trễ mà chỉ retry cùng version | `DO NOTHING` giữ dữ liệu cũ | Chốt input, phát version mới có kiểm soát |
| Gửi email trong transaction DB | DB không rollback được email | Transactional outbox + idempotent consumer |
| Task có `END_TIME=NULL` nên chắc chưa tạo báo cáo | Pod có thể chết sau commit | Đối soát bảng báo cáo |
| Đưa password vào command-line | TaskRepository có thể lưu arguments | Kubernetes Secret/env/mounted file |
| Giữ transaction hàng giờ để tính report khổng lồ | Khóa và connection tồn tại lâu | Snapshot, staged aggregation, claim/lease/fencing |

### 15.1. Khi lượng dữ liệu lớn hơn khả năng một statement

Mẫu `INSERT ... SELECT` phù hợp với một phép tổng hợp có thể hoàn tất trong **một giao dịch tương đối ngắn**. Khi phải xử lý hàng trăm triệu hóa đơn, nhiều nguồn hoặc báo cáo nhiều tệp, nên xem xét **Spring Batch** với chunk/checkpoint, hoặc staging tables theo `runId` và business key. Khi đó vẫn phải định nghĩa rõ:

- Các phân đoạn xử lý có cùng **source snapshot** không?
- Kết quả trung gian có thể retry/idempotent theo partition hay không?
- Ai có quyền **publish** một báo cáo sau khi mọi partition hoàn tất?
- Khi worker chết, ai tiếp quản và làm sao chặn worker cũ tiếp tục ghi (**fencing**)?
- Một lần retry có thay đổi `reportVersion` không? Thông thường là **không**.

Không tự động chuyển mọi báo cáo ngày sang remote partitioning hoặc bật `single-instance-enabled` như cách thay thế unique constraint nghiệp vụ.

## 16. Đối soát vận hành sau mỗi lần chạy

Một quy trình giám sát tốt kết hợp **scheduler, TaskRepository và kết quả nghiệp vụ**:

~~~text
Kubernetes Job / Scheduled launch
   │   điều phối theo kỳ, Pod retry
   ▼
TaskExecution
   │   ID, start/end, exit code
   ▼
DailyInvoiceReport
       business key, count, sum, generatedAt
~~~

Thử truy vấn:

~~~sql
SELECT tenant_id,
       business_date,
       report_version,
       invoice_count,
       total_amount,
       generated_at
FROM daily_invoice_report
WHERE tenant_id = 'acme'
  AND business_date = DATE '2026-11-23'
ORDER BY report_version;
~~~

Trong lab sau các bước T1–T6, trước khi thêm dữ liệu đến trễ, sẽ có các version `1`, `2` và `3`, mỗi version có **3 hóa đơn, 250.00**. Nếu sau đó tạo v4 từ nguồn mới, v4 có **4 hóa đơn, 450.00**. Một lần Task thất bại và rollback **không tạo thêm version** ngoài những lần đã commit thành công.

### 16.1. Alert và điều tra

- **Không có TaskExecution trong ngày:** kiểm tra CronJob/launcher, image pull, DB startup; Task có thể chưa từng khởi động.
- **Task FAILED:** xem log an toàn, `TaskRepository`, PostgreSQL lỗi/lock/transaction.
- **Task exit 0 nhưng không có dòng mới:** nếu `ALREADY_EXISTS`, đây có thể là retry an toàn; kiểm tra business key, không báo động sai.
- **Task exit 0 nhưng báo cáo mới sai:** đối chiếu source snapshot, timezone, `PAID` status và dữ liệu đến trễ.
- **Hai Task cùng thời điểm:** xem `ON CONFLICT` và số dòng báo cáo, không suy đoán lỗi chỉ vì có hai TaskExecution.
- **TaskExecution không có end time nhưng báo cáo đã tồn tại:** có thể process chết sau commit; retry idempotent theo cùng key.

Lưu `taskExecutionId`, `Kubernetes Job UID` và `businessKey` trong structured logs hoặc metadata tra cứu, không đưa ID có cardinality cao vào mọi nhãn metric. Không ghi mật khẩu DB hoặc token qua arguments vì lịch sử Task có thể lưu những giá trị đó.

## 17. Tổng kết

1. **Idempotency là thuộc tính của hành vi nghiệp vụ**, không phải số lần Kubernetes/Spring Cloud Task khởi chạy.
2. Với báo cáo ngày, hãy định danh bằng **`(tenant_id, business_date, report_version)`**, thực thi trong **cùng PostgreSQL DB** có unique constraint.
3. **`INSERT ... SELECT ... ON CONFLICT DO NOTHING`** tránh check-then-insert race và không cộng đôi; `@Transactional` cho phép rollback khi service thất bại trước commit.
4. Chạy lại cùng key sau khi thành công phải trả **`ALREADY_EXISTS`**, không tạo bản ghi mới. TaskExecution mới vẫn là chuyện bình thường.
5. Tính khoảng ngày bằng timezone nghiệp vụ và **`[startInclusive,endExclusive)`** để không lệch hoặc đếm trùng tại nửa đêm.
6. **Nguồn dữ liệu phải được chốt hoặc snapshot** trước khi phát hành. Nếu thay đổi sau khi đã công bố, dùng version mới theo quy trình, không âm thầm overwrite v1.
7. Retry sau lỗi trước commit có thể tạo báo cáo; retry sau commit nên no-op. **Không dùng `END_TIME` hoặc exit code làm bằng chứng duy nhất** rằng báo cáo đã/ chưa được lưu.
8. Với nhiều Pod, `synchronized` hoặc `Forbid` không thay thế primary key trên business table.
9. Nếu có tác dụng phụ ở hệ thống ngoài PostgreSQL, phải dùng **outbox, idempotency key và cơ chế đối soát**; một transaction DB không tạo exactly-once toàn cục.
10. **Đo và kiểm chứng thực tế** bằng SQL, kịch bản rollback, chạy đồng thời, dữ liệu đến trễ và trạng thái TaskRepository trước khi vận hành theo lịch.

### Tài liệu tham khảo

- [Spring Cloud Task — Features và vòng đời Task](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — TaskRepository schema](https://docs.spring.io/spring-cloud-task/reference/appendix-task-repository-schema.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Boot — SQL Databases và JdbcTemplate](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [PostgreSQL — INSERT và ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html)
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html)
- [PostgreSQL — Date/Time Types và Time Zones](https://www.postgresql.org/docs/current/datatype-datetime.html)
- [Kubernetes — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)

# Mất kết nối hoặc JVM bị dừng giữa lúc cập nhật

Trong chương **Chạy lại an toàn** của module **SPRING_CLOUD_TASK**, bài toán quan trọng không phải chỉ là “làm sao chạy lại sau lỗi”, mà là **làm sao xác định việc gì đã xảy ra trước khi lỗi xuất hiện**. Một ứng dụng Spring Cloud Task có thời gian chạy hữu hạn có thể ghi dữ liệu nghiệp vụ vào database, cập nhật metadata trong `TaskRepository` rồi thoát. Nếu mất mạng hoặc JVM bị dừng ngay giữa các bước, kết quả nghiệp vụ và trạng thái thực thi có thể không đồng nhất.

Ví dụ: tác vụ tạo báo cáo ngày 24/11 đã lưu bản báo cáo vào PostgreSQL. Đúng lúc database hoàn tất `COMMIT`, kết nối bị đứt; chương trình không nhận được phản hồi. Scheduler nhìn thấy lần chạy thất bại và kích hoạt lại. Nếu lần chạy thứ hai luôn chèn báo cáo mới hoặc cộng thêm số tiền, hệ thống có thể tạo dữ liệu trùng, dù lỗi ban đầu chỉ nằm ở phản hồi mạng.

Bài học này giải thích **kết quả commit không xác định** (*ambiguous commit outcome*), phân biệt transaction nghiệp vụ với metadata Spring Cloud Task, và xây dựng giải pháp chạy lại dựa trên **khóa idempotency, ràng buộc duy nhất, kiểm tra trạng thái sau khi kết nối lại và chính sách retry có giới hạn**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt lỗi trước `COMMIT`, lỗi khi gửi/nhận phản hồi `COMMIT` và lỗi sau khi database đã ghi thành công.
- Giải thích vì sao một exception hoặc mã thoát khác `0` **không đủ chứng minh** rằng dữ liệu nghiệp vụ đã rollback.
- Phân biệt `TaskExecution` trong Spring Cloud Task với nguồn dữ liệu nghiệp vụ quyết định một công việc đã hoàn tất.
- Thiết kế idempotency key ổn định qua nhiều lần chạy, bao gồm cả khi scheduler khởi chạy đồng thời.
- Dùng transaction và ràng buộc `UNIQUE` hoặc `PRIMARY KEY` trong PostgreSQL để ngăn ghi trùng.
- Áp dụng phương án đối soát sau lỗi kết nối, timeout, JVM crash và lần chạy chưa cập nhật `TaskRepository`.
- Hiểu giới hạn của transaction database khi kết hợp API, email, message broker hoặc file/object storage.
- Đưa ra chính sách retry/backoff, phối hợp với Spring Batch và kiểm thử lỗi ở những thời điểm quan trọng.

## 2. Tình huống cốt lõi: database đã commit nhưng ứng dụng không biết

Giả sử task được gọi bằng:

~~~bash
java -jar daily-report-task.jar --tenant=shop-01 --businessDate=2026-11-24
~~~

Ứng dụng dự định ghi **một** báo cáo cho cặp `(shop-01, 2026-11-24)`. Trong một lần thực thi, các sự kiện có thể diễn ra:

1. Spring Cloud Task ghi thông tin bắt đầu chạy vào `TaskRepository`, nếu hạ tầng sẵn sàng.
2. `ApplicationRunner` gọi service tạo báo cáo.
3. Service thực hiện `BEGIN`, tính toán và ghi hàng dữ liệu nghiệp vụ.
4. Ứng dụng gửi lệnh `COMMIT` đến PostgreSQL.
5. PostgreSQL có thể đã commit, nhưng kết nối mạng bị ngắt trước khi phản hồi đến ứng dụng.
6. Ứng dụng hoặc JVM thất bại; scheduler không nhận được bằng chứng hoàn thành.
7. Scheduler chạy lại cùng yêu cầu.

**Đến bước 5, ứng dụng không thể suy ra chỉ từ lỗi kết nối rằng transaction đã commit hay chưa.** Trạng thái thực có thể là:

- **Đã commit:** dữ liệu có thật trong database.
- **Chưa commit/đã rollback:** thay đổi không được lưu.
- **Chưa xác minh được:** database vẫn không thể truy cập, hoặc quan sát được chưa đủ tin cậy.

Tình trạng “không biết” khác với thất bại đã xác nhận. Một exception kiểu kết nối bị đóng khi commit xảy ra **không tự động có nghĩa PostgreSQL đã rollback**.

~~~mermaid
sequenceDiagram
    participant S as Scheduler
    participant T as Spring Cloud Task
    participant DB as PostgreSQL
    S->>T: Chạy báo cáo với business key K
    T->>DB: BEGIN; ghi báo cáo cho K
    T->>DB: COMMIT
    DB--xT: Phản hồi COMMIT bị mất
    Note over T,DB: Ứng dụng không biết kết quả commit
    T--xS: Task thất bại / bị dừng
    S->>DB: Đọc theo khóa nghiệp vụ K khi có kết nối
    alt Đã có dữ liệu đúng K và đúng fingerprint
        DB-->>S: Hoàn tất từ trước
    else Chưa có dữ liệu xác nhận
        DB-->>S: Không thấy kết quả
        S->>T: Thử lại thao tác idempotent
    end
~~~

Trong thực tế, scheduler có thể giao việc đối soát cho một ứng dụng riêng thay vì trực tiếp truy vấn database. Sơ đồ nhằm nhấn mạnh trình tự **xác minh trạng thái trước khi quyết định lặp tác động nghiệp vụ**.

## 3. Bảng phân tích các cửa sổ lỗi

Không phải mọi lỗi giữa lúc cập nhật đều có cùng ý nghĩa.

| Thời điểm gặp lỗi | Dữ liệu nghiệp vụ có thể ở trạng thái nào? | Điều cần làm khi chạy lại |
| --- | --- | --- |
| Trước khi mở transaction | Chưa có thay đổi của lần thử này | Có thể thử lại nếu đầu vào ổn định |
| Trong transaction, trước `COMMIT` | Thao tác trong cùng transaction thường rollback nếu không commit, nhưng cần chờ DB giải phóng phiên lỗi khi cần | Không đoán theo log; dùng khóa nghiệp vụ và transaction đúng |
| Đang gửi `COMMIT` hoặc mất phản hồi sau `COMMIT` | **Không xác định**: đã commit hoặc chưa | Đọc trạng thái bền vững và chạy lại thao tác idempotent |
| Sau `COMMIT` nghiệp vụ, trước khi cập nhật `TaskRepository` | Dữ liệu nghiệp vụ đã có; `TaskExecution` có thể chưa kết thúc | Xác nhận kết quả nghiệp vụ, đối soát metadata, tránh tạo bản mới |
| Sau khi gọi API bên ngoài, trước khi nhận phản hồi | API có thể đã thực hiện tác động dù client timeout | Dùng idempotency key tại hệ thống đích hoặc tra cứu giao dịch |
| Khi JVM bị kill giữa các bước của quy trình nhiều transaction | Một số bước đã commit, bước khác chưa | Theo dõi tiến độ bằng khóa nghiệp vụ/checkpoint và xử lý bù trừ |
| Khi hai scheduler cùng chạy một yêu cầu | Hai phiên có thể cùng kiểm tra “chưa tồn tại” | Dùng ràng buộc duy nhất/khóa ở database, không chỉ `SELECT` trước `INSERT` |

**Điểm cần nhớ:** transaction của **một database** bảo đảm tính nguyên tử cho các thao tác nằm trong ranh giới transaction đó, theo cấu hình và ngữ nghĩa của database. Nó **không tự biến** việc ghi hai database, gọi API bên ngoài, gửi email và cập nhật metadata Task thành một transaction phân tán duy nhất.

## 4. Ba lớp trạng thái phải được đối chiếu

Một lần chạy thực tế có ít nhất ba lớp trạng thái:

| Lớp | Nguồn thông tin | Ý nghĩa |
| --- | --- | --- |
| **Tiến trình** | Scheduler, Kubernetes Job, container, mã thoát JVM | Tiến trình có được tạo, đang chạy hay đã kết thúc? |
| **Lần thực thi Spring Cloud Task** | `TaskExecution` trong `TaskRepository` | Framework ghi nhận bắt đầu/kết thúc, exit code và lỗi như thế nào? |
| **Nghiệp vụ** | Bảng báo cáo, sổ giao dịch, object storage, bảng idempotency | Kết quả mong muốn đã được ghi đúng, đủ và duy nhất chưa? |

Các lớp có thể lệch nhau. Ví dụ:

- Task có `EXIT_CODE=1`, nhưng báo cáo đã được commit trước lúc network hỏng.
- `TaskExecution.END_TIME IS NULL` vì JVM bị kill, nhưng giao dịch nghiệp vụ đã hoàn thành.
- Task có `EXIT_CODE=0`, nhưng ứng dụng nuốt exception hoặc không kiểm tra đầu ra.
- Không có `TaskExecution` do `ApplicationContext` lỗi rất sớm, nhưng scheduler đã cố khởi chạy process.

Spring Cloud Task theo dõi **vòng đời ứng dụng**, không tự cung cấp tính idempotent cho mọi thao tác của runner. Mỗi lần chạy lại có thể sinh một `TASK_EXECUTION_ID` mới; ID kỹ thuật này **không nên dùng làm khóa chống trùng nghiệp vụ**, bởi nó thay đổi giữa các lần thử của cùng một yêu cầu.

Quy tắc quyết định: **xác minh hoàn tất dựa trên trạng thái nghiệp vụ bền vững; dùng `TaskRepository` và scheduler để giải thích quá trình thực thi**.

## 5. Idempotency là gì và cần chọn khóa thế nào?

Một thao tác có tính **idempotent** nếu thực hiện lại cùng yêu cầu không tạo thêm tác động không mong muốn sau lần thực hiện thành công đầu tiên. Ví dụ:

- Ghi báo cáo cho ngày và tenant với cùng phiên bản dữ liệu: lần đầu tạo, lần sau nhận biết đã tồn tại.
- Đặt trạng thái đơn hàng thành `PAID`: lần thứ hai không trừ tiền thêm.
- Gửi lệnh trừ tiền hai lần **không** idempotent nếu không có mã giao dịch chống trùng tại dịch vụ thanh toán.

### 5.1. Khóa phải gắn với công việc, không gắn với lần chạy

Đối với báo cáo ngày, khóa nghiệp vụ có thể là:

~~~text
tenantId + businessDate + reportVersion
~~~

Ví dụ:

~~~text
shop-01|2026-11-24|v1
~~~

Tất cả các lần thử làm cùng công việc phải mang **cùng khóa**. Không nên lấy timestamp khởi chạy, số lần retry, UUID tạo mới trong runner hoặc `TASK_EXECUTION_ID` làm khóa, vì mỗi lần chạy lại sẽ có khóa mới và cơ chế chống trùng bị vô hiệu hóa.

Khi một yêu cầu mang cùng khóa nhưng **nội dung hoặc phiên bản đầu vào khác nhau**, cần chính sách rõ ràng: báo xung đột, tạo phiên bản công việc mới hoặc cho phép cập nhật có kiểm soát. Không được lặng lẽ coi dữ liệu khác là bản trùng hợp lệ.

### 5.2. Fingerprint của đầu vào

Bên cạnh khóa, có thể lưu `payload_hash` (ví dụ SHA-256 của biểu diễn đầu vào đã chuẩn hóa) để so sánh:

- Cùng khóa, cùng fingerprint → thao tác đã hoàn thành từ trước; có thể trả kết quả cũ.
- Cùng khóa, fingerprint khác → **CONFLICT**; điều tra tại sao hai yêu cầu có cùng định danh nhưng khác dữ liệu.
- Chưa có khóa → chỉ được ghi mới thông qua cơ chế nguyên tử có ràng buộc duy nhất.

Cần xác định cách chuẩn hóa đầu vào, timezone, thứ tự trường, mã hóa và phiên bản thuật toán để fingerprint không thay đổi tùy lần chạy. Nếu dữ liệu nguồn liên tục thay đổi, hãy cố định snapshot/version đầu vào hoặc thiết kế cơ chế tái tính toán có version rõ ràng.

## 6. Vì sao SELECT trước INSERT vẫn chưa đủ?

Một cách triển khai không an toàn:

~~~text
Nếu SELECT không có report cho ngày D
    INSERT report mới
~~~

Hai task chạy đồng thời có thể **cùng thấy chưa có record**, sau đó cùng thực hiện `INSERT`. Kiểm tra bằng `SELECT` trước khi ghi chỉ giúp đọc trạng thái, **không thay thế ràng buộc duy nhất của database**.

Một phương án vững hơn là:

1. Có `PRIMARY KEY`/`UNIQUE` trên khóa nghiệp vụ.
2. Thử ghi một cách nguyên tử dưới transaction.
3. Nếu khóa đã tồn tại, đọc kết quả **đã commit** và xác minh fingerprint.
4. Nếu cùng khóa nhưng dữ liệu khác, báo conflict; không tự overwrite.
5. Nếu database không liên lạc được, giữ trạng thái **UNKNOWN** thay vì đoán kết quả.

Với PostgreSQL, có thể dùng `INSERT ... ON CONFLICT DO NOTHING`; trong database khác cần dùng cú pháp và quy tắc tương đương. Khi dùng transaction isolation cao hơn mặc định, ví dụ `REPEATABLE READ` hoặc `SERIALIZABLE`, có thể phải xử lý thêm lỗi serialization và retry **toàn bộ transaction** theo chính sách phù hợp.

## 7. Thực hành PostgreSQL: bảo vệ một báo cáo khỏi tạo trùng

Ví dụ dưới đây xây dựng một tác vụ Spring Cloud Task tạo một bản báo cáo bất biến. Trạng thái “đã tạo” được định nghĩa bởi **record nghiệp vụ đã commit** trong PostgreSQL, còn metadata `TaskExecution` được ghi riêng theo hạ tầng Spring Cloud Task.

### 7.1. Schema nghiệp vụ

Dùng migration tạo bảng trong database PostgreSQL:

~~~sql
CREATE TABLE daily_report (
    tenant_id       VARCHAR(64)  NOT NULL,
    business_date   DATE         NOT NULL,
    report_version  VARCHAR(32)  NOT NULL,
    payload_sha256  CHAR(64)     NOT NULL,
    report_body     TEXT         NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, business_date, report_version)
);
~~~

Khóa chính ba cột giúp database ngăn hai record cho **cùng tenant, cùng ngày và cùng phiên bản báo cáo**. Ví dụ cố ý coi báo cáo là bất biến: nếu muốn xuất phiên bản mới, cần tăng `report_version` theo quy tắc nghiệp vụ thay vì ghi đè bản cũ.

Bên cạnh bảng này, database metadata Spring Cloud Task cần **schema riêng do phiên bản framework quy định**. Không tự tạo bảng `TASK_EXECUTION` bằng DDL của ví dụ nghiệp vụ.

### 7.2. Dependency và cấu hình Spring Boot

Dự án Maven cần Spring Boot và Spring Cloud Task có **phiên bản tương thích**. Các dependency tiêu biểu:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
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
</dependencies>
~~~

Dùng Spring Boot parent/BOM, import Spring Cloud BOM tương thích và cấu hình `spring-boot-maven-plugin` để tạo JAR thực thi.

Ví dụ `application.yml`:

~~~yaml
spring:
  application:
    name: safe-daily-report
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver
  cloud:
    task:
      name: safe-daily-report
      initialize-enabled: false
~~~

Các biến môi trường phải trỏ đến database đã được migration cả schema Spring Cloud Task và bảng `daily_report`. `initialize-enabled: false` giả định schema metadata đã tồn tại; không dùng tài khoản runtime có quyền sửa schema khi không cần.

Trong ví dụ, dùng chung một `DataSource` để đơn giản hóa. **Ngay cả khi cùng database**, đừng tự coi cập nhật `TaskRepository` và transaction nghiệp vụ dưới đây là một lần commit nguyên tử; chúng được gọi ở các giai đoạn khác nhau trong vòng đời ứng dụng.

### 7.3. ApplicationRunner có đầu vào ổn định

Tạo `src/main/java/com/example/task/SafeDailyReportApplication.java`:

~~~java
package com.example.task;

import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class SafeDailyReportApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(SafeDailyReportApplication.class, args);
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }

    @Bean
    ApplicationRunner reportRunner(DailyReportWriter writer) {
        return args -> {
            String tenant = requiredOption(args, "tenant");
            LocalDate date = LocalDate.parse(
                    requiredOption(args, "businessDate"));
            String version = "v1";

            // Demo: nội dung ổn định cho cùng đầu vào.
            // Thực tế: lấy dữ liệu từ snapshot/version đã cố định.
            String body = "Report for " + tenant + " / " + date;

            String result = writer.saveOnce(
                    tenant, date, version, body);
            System.out.println("Report result: " + result);
        };
    }

    private static String requiredOption(
            ApplicationArguments args, String name) {
        List<String> values = args.getOptionValues(name);
        if (values == null || values.size() != 1
                || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Cần truyền đúng một --" + name + "=...");
        }
        return values.get(0).trim();
    }
}
~~~

Đoạn mã tạo nội dung báo cáo cố định nhằm **minh họa idempotency**. Với báo cáo thật, cần tính nội dung từ một snapshot dữ liệu có version, tránh tính mỗi lần từ “dữ liệu hiện tại” khác nhau rồi vô tình tạo fingerprint không nhất quán.

### 7.4. Service ghi một lần bằng transaction và unique key

Tạo `src/main/java/com/example/task/DailyReportWriter.java`:

~~~java
package com.example.task;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDate;
import java.util.HexFormat;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DailyReportWriter {

    private final JdbcTemplate jdbc;

    public DailyReportWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public String saveOnce(
            String tenantId,
            LocalDate businessDate,
            String reportVersion,
            String body) {

        String hash = sha256(body);

        int inserted = jdbc.update("""
            INSERT INTO daily_report
                (tenant_id, business_date, report_version,
                 payload_sha256, report_body)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (tenant_id, business_date, report_version)
            DO NOTHING
            """,
            tenantId, businessDate, reportVersion, hash, body);

        if (inserted == 1) {
            return "CREATED";
        }

        String previousHash = jdbc.queryForObject("""
            SELECT payload_sha256
            FROM daily_report
            WHERE tenant_id = ?
              AND business_date = ?
              AND report_version = ?
            """,
            String.class, tenantId, businessDate, reportVersion);

        if (!hash.equals(previousHash)) {
            throw new IllegalStateException(
                    "IDEMPOTENCY_CONFLICT: same key, different content");
        }

        return "ALREADY_APPLIED";
    }

    private static String sha256(String value) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(bytes);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

Giải thích cơ chế:

1. `@Transactional` bao toàn bộ quyết định ghi và kiểm tra. Phương thức `saveOnce` được gọi **qua bean Spring** từ runner, để Spring transaction interceptor có hiệu lực; không gọi tự thân từ một phương thức khác cùng class.
2. Lần đầu: PostgreSQL ghi một record. Sau `COMMIT`, báo cáo tồn tại bền vững.
3. Lần thứ hai cùng khóa và cùng nội dung: lệnh `ON CONFLICT DO NOTHING` không ghi thêm record; service đọc hash và trả `ALREADY_APPLIED`.
4. Cùng khóa nhưng nội dung khác: service trả lỗi `IDEMPOTENCY_CONFLICT`. Điều này bảo vệ nguyên tắc “cùng một yêu cầu phải có cùng kết quả”.
5. Nếu hai tiến trình chạy đồng thời, **ràng buộc khóa chính** là điểm bảo vệ cuối cùng. PostgreSQL xử lý cạnh tranh khóa; kiểm tra trước bằng một câu `SELECT` riêng lẻ sẽ không đủ.
6. Khi mất kết nối ngay quanh `COMMIT`, caller có thể nhận exception dù kết quả thật chưa rõ. Scheduler được phép thử lại **cùng thao tác idempotent** sau khi có kết nối, thay vì dùng lỗi kết nối để suy ra rollback.

Ví dụ giả định transaction isolation mặc định **READ COMMITTED** của PostgreSQL và driver JDBC hỗ trợ `LocalDate`. Với mức cô lập khác, các trường hợp cạnh tranh có thể sinh lỗi serialization cần được phân loại và retry có giới hạn.

**Giới hạn của ví dụ:** `CREATED` được trả từ thân phương thức trước khi transaction interceptor commit. Caller chỉ nhận giá trị trả về bình thường sau khi proxy commit thành công; nếu commit ném exception, runner không nên coi dòng `CREATED` chưa được xác nhận là bằng chứng đã commit.

## 8. Chạy lần đầu, lần hai và khi đầu vào xung đột

Giả sử artifact là `target/safe-daily-report-0.0.1-SNAPSHOT.jar`. Dùng JDBC URL và credentials từ môi trường, chạy lần đầu:

~~~bash
java -jar target/safe-daily-report-0.0.1-SNAPSHOT.jar \
  --tenant=shop-01 --businessDate=2026-11-24
~~~

Đầu ra nghiệp vụ dự kiến:

~~~text
Report result: CREATED
~~~

Chạy **lần hai với cùng tham số**:

~~~bash
java -jar target/safe-daily-report-0.0.1-SNAPSHOT.jar \
  --tenant=shop-01 --businessDate=2026-11-24
~~~

Đầu ra dự kiến:

~~~text
Report result: ALREADY_APPLIED
~~~

Các lệnh trên dùng cách nối dòng kiểu POSIX; trong PowerShell nhập trên một dòng hoặc dùng cú pháp xuống dòng phù hợp. Chạy lần thứ ba với một ngày khác sẽ tạo record mới vì **khóa nghiệp vụ khác**.

Đối chiếu database:

~~~sql
SELECT tenant_id,
       business_date,
       report_version,
       payload_sha256,
       created_at
FROM daily_report
WHERE tenant_id = 'shop-01'
ORDER BY business_date, report_version;
~~~

Sau hai lần chạy cùng khóa, kỳ vọng chỉ có **một** hàng cho `(shop-01, 2026-11-24, v1)`:

~~~sql
SELECT COUNT(*) AS report_count
FROM daily_report
WHERE tenant_id = 'shop-01'
  AND business_date = DATE '2026-11-24'
  AND report_version = 'v1';
~~~

`report_count` phải bằng `1`, nếu database/schema được cấu hình đúng và các lần chạy hoàn tất theo thiết kế. Để thử conflict, hãy giữ nguyên khóa nhưng làm nội dung nghiệp vụ khác trong **một môi trường thử nghiệm**; service phải từ chối thay vì ghi đè.

Đồng thời, bảng `TASK_EXECUTION` có thể chứa **nhiều record** vì mỗi lần khởi chạy Spring Cloud Task là một lần thực thi khác nhau:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE
FROM TASK_EXECUTION
ORDER BY TASK_EXECUTION_ID DESC;
~~~

**Nhiều `TaskExecution` nhưng chỉ một kết quả nghiệp vụ là hành vi đúng** đối với một task idempotent được chạy lại.

## 9. Quy trình quyết định sau khi mất kết nối

Đừng dùng quy tắc “mọi exception đều chạy lại ngay”. Một quy trình an toàn hơn:

~~~mermaid
flowchart TD
    A["Lần chạy lỗi / JVM bị dừng"] --> B["Lấy business key và run-id từ bộ điều phối"]
    B --> C{"Có thể kết nối nguồn dữ liệu chính?"}
    C -->|"Không"| D["UNKNOWN: cảnh báo, backoff, thử kiểm tra sau"]
    C -->|"Có"| E["Đọc kết quả đã commit theo business key"]
    E --> F{"Record tồn tại?"}
    F -->|"Có"| G{"Hash và điều kiện nghiệp vụ khớp?"}
    G -->|"Có"| H["Đã hoàn thành: không tạo bản mới"]
    G -->|"Không"| I["CONFLICT: điều tra, không ghi đè tự động"]
    F -->|"Không"| J["Thử lại cùng key bằng thao tác idempotent"]
    J --> K{"Ghi thành công?"}
    K -->|"Có"| L["Xác nhận kết quả"]
    K -->|"Timeout / mất kết nối"| D
~~~

Đọc trạng thái từ nguồn **đủ độ nhất quán** để ra quyết định. Nếu database có replica trễ hoặc cache bất đồng bộ, một kết quả “chưa có record” có thể là dữ liệu cũ. Khi cần, dùng database primary hoặc cách đọc có bảo đảm nhất quán phù hợp với hệ thống.

Một `SELECT` sau lỗi chỉ giúp **phân loại** tình trạng; việc chặn trùng vẫn phải được thực thi bằng `UNIQUE`/`PRIMARY KEY` hoặc cơ chế nguyên tử tương đương. Nếu transaction đầu tiên đang xử lý, lần chạy sau vẫn phải đi qua rào chắn duy nhất này.

Khi database vẫn không truy cập được, kết quả cần giữ là **UNKNOWN/PENDING_RECONCILIATION**. Không thể gọi truy vấn xác minh là thành công, cũng không thể khẳng định giao dịch cũ đã rollback.

### Khi một run bị báo FAILED nhưng nghiệp vụ đã hoàn tất

Scheduler có thể ghi trạng thái riêng như `COMPLETED_AFTER_RECONCILIATION` cho **yêu cầu nghiệp vụ**, kèm liên kết tới `run-id`, bằng chứng record và thời điểm xác minh. Không cần sửa trực tiếp `TASK_EXECUTION.EXIT_CODE` thành `0` để làm đẹp lịch sử: bản ghi thực thi vẫn hữu ích khi phản ánh đúng sự cố đã xảy ra.

## 10. Nếu công việc gồm nhiều bước thì làm gì?

Một transaction đơn có thể bao các thao tác ghi vào **cùng database**, nhưng không nên kéo dài tùy tiện qua nhiều phút hay qua các lời gọi mạng. Nếu task có nhiều bước:

1. Tải dữ liệu nguồn.
2. Tạo các hàng báo cáo theo nhóm.
3. Xuất file lên object storage.
4. Gửi thông báo.
5. Ghi trạng thái hoàn tất.

JVM có thể chết giữa bước 2 và bước 3. Không có một transaction JDBC thông thường nào tự rollback file đã tải lên hoặc email đã gửi. Cần tách **điểm hoàn tất nghiệp vụ** và thiết kế từng bước có thể chạy lại.

Một mô hình trạng thái có thể là:

| Trạng thái nghiệp vụ | Ý nghĩa | Hành động khi chạy lại |
| --- | --- | --- |
| `PENDING` | Chưa bắt đầu hoặc đã đăng ký yêu cầu | Có thể nhận việc theo cơ chế claim an toàn |
| `PROCESSING` | Một worker đang xử lý | Kiểm tra lease/heartbeat trước khi chiếm lại |
| `COMPLETED` | Đã xác minh kết quả chính | Trả lại kết quả cũ, không thực hiện tác động thêm |
| `FAILED_RETRYABLE` | Lỗi tạm thời có thể phục hồi | Retry sau backoff, dùng cùng key |
| `FAILED_FINAL` | Lỗi dữ liệu hoặc vi phạm bất biến | Chuyển điều tra/sửa dữ liệu; không retry tự động |
| `UNKNOWN` | Chưa xác minh được sau sự cố commit/network | Đối soát trước khi ra quyết định |

Các tên trạng thái trên là **mẫu thiết kế nghiệp vụ**, không phải enum mặc định của Spring Cloud Task. Trong hệ thống thực tế phải định nghĩa transition hợp lệ, concurrency và cách cấp quyền thay đổi trạng thái.

### 10.1. Lease và xử lý worker chết

Nếu dùng bảng `task_request` có worker ownership, hãy lưu `lease_until` và một token/phiên bản thế hệ xử lý (*fencing token*). Worker mới chỉ nhận việc khi lease hết hạn qua thao tác cập nhật nguyên tử; worker cũ nếu tỉnh lại sau thời gian treo không được ghi kết quả vượt qua token mới.

Không dùng `PROCESSING` không có hạn như một bằng chứng worker còn sống mãi. Ngược lại, chỉ thấy lease hết hạn cũng không chứng minh hiệu ứng từ phiên cũ chưa xảy ra: vẫn cần khóa idempotency tại nơi ghi dữ liệu.

### 10.2. Checkpoint ứng dụng

Với hàng nghìn nhóm dữ liệu, có thể commit theo chunk và ghi checkpoint cùng transaction của mỗi nhóm. Khi chạy lại, đọc những nhóm đã commit để bỏ qua hoặc xử lý idempotent. Cách này giảm phạm vi làm lại nhưng đòi hỏi khóa duy nhất **từng nhóm/bản ghi**, không chỉ khóa của toàn job.

## 11. Tác động bên ngoài database: API, email, message broker và file

### 11.1. Gọi một API thanh toán

Nếu task gọi `POST /charge` rồi timeout, không thể suy ra giao dịch chưa được tạo. Đối với hệ thống đích hỗ trợ idempotency key, gửi **cùng khóa ổn định** ở mọi lần thử và tra cứu trạng thái giao dịch trước khi phát lệnh mới. Nếu API không hỗ trợ khóa hoặc tra cứu, phải thiết kế đối soát/bù trừ; không thể hứa bảo đảm “đúng một lần” chỉ bằng retry của client.

### 11.2. Transactional outbox cho thông điệp

Nếu cần cập nhật database và gửi sự kiện, có thể ghi **dữ liệu nghiệp vụ và record outbox trong cùng một transaction database**, với `event_id` ổn định, khóa duy nhất:

~~~sql
CREATE TABLE outbox_event (
    event_id         VARCHAR(128) PRIMARY KEY,
    event_type       VARCHAR(80) NOT NULL,
    event_payload    TEXT NOT NULL,
    published_at     TIMESTAMPTZ
);
~~~

Sau khi commit, một dispatcher riêng lấy các sự kiện chưa phát, gửi lên broker và đánh dấu đã phát. Nếu broker đã nhận nhưng dispatcher chết trước lúc đánh dấu, sự kiện **có thể được phát lại**. Do đó consumer vẫn cần **inbox/deduplication** hoặc xử lý idempotent theo `event_id`. Outbox giúp không làm mất ý định gửi khi ứng dụng chết giữa các bước; nó **không tự bảo đảm exactly-once end-to-end**.

### 11.3. Ghi file và object storage

Có thể đặt tên đầu ra dựa trên khóa nghiệp vụ, ví dụ `reports/shop-01/2026-11-24/v1.csv`, tạo file tạm và xác minh checksum trước khi publish. Nếu object storage hỗ trợ conditional write hoặc versioning, dùng chúng để ngăn ghi đè ngoài ý muốn. Nếu DB ghi “COMPLETED” trước khi file thực sự tồn tại, hệ thống có thể báo sai. Nên công bố điều kiện hoàn tất theo **cả record trạng thái và đối tượng đầu ra đã xác minh**.

## 12. Spring Cloud Task và Spring Batch không tự giải quyết tất cả

### 12.1. TaskRepository là lịch sử thực thi

Theo vòng đời Spring Cloud Task, metadata bắt đầu được tạo khi hạ tầng đã khởi tạo đủ và trước runner; metadata kết thúc được cập nhật khi hoàn tất hoặc lỗi trong các điều kiện phù hợp. Nếu JVM bị kill hoặc database không ghi được, record có thể không có `END_TIME`.

Không nên dùng `TASK_EXECUTION_ID` như khóa chống trùng nghiệp vụ; một yêu cầu có thể tạo nhiều lần chạy và nhiều ID. `TaskExecution` giúp **theo dõi**, còn khóa nghiệp vụ và ràng buộc database giúp **ngăn tác động trùng**.

### 12.2. Spring Batch có checkpoint nhưng vẫn cần idempotency

Spring Batch có `JobRepository`, `JobExecution`, `StepExecution` và `ExecutionContext` để quản lý job, step, restart và checkpoint. Khi cấu hình chunk processing phù hợp, việc ghi dữ liệu cùng checkpoint theo transaction có thể giúp khởi động lại từ phần đã xử lý. Tuy nhiên:

- Không phải mọi `ItemWriter` đều ghi vào cùng transaction với metadata Batch.
- Gọi API bên ngoài hoặc xuất file có thể để lại tác động dù transaction JDBC rollback.
- Job parameter xác định `JobInstance` theo cấu hình; lần chạy lại bằng bộ tham số nhận dạng khác có thể tạo job instance mới.
- Nếu mất kết nối quanh `COMMIT`, vẫn phải xác minh dữ liệu đã commit và khả năng restart thực tế của job.

Khi phối hợp Spring Cloud Task với Batch, cần phân biệt **lịch sử chạy ứng dụng** (Task) với **lịch sử xử lý từng job/step** (Batch), và cả hai với **kết quả nghiệp vụ**.

## 13. Chính sách retry có giới hạn

Retry là cách xử lý lỗi tạm thời, không phải công cụ che mọi nguyên nhân thất bại. Một chính sách có thể dựa trên bảng sau:

| Lỗi | Có nên tự retry? | Điều kiện |
| --- | --- | --- |
| Network timeout, connection reset | Có thể | Cùng key; sau khi kết nối lại, đối soát hoặc lặp thao tác idempotent |
| Deadlock/serialization failure | Có thể | Retry **toàn bộ transaction**, giới hạn số lần, backoff |
| HTTP 429/503 từ upstream | Có thể | Tôn trọng `Retry-After` nếu có, idempotency key và giới hạn tổng thời gian |
| Đầu vào sai định dạng | Không | Sửa tham số/dữ liệu |
| Cùng key nhưng fingerprint khác | Không | Conflict cần điều tra hoặc tạo phiên bản nghiệp vụ mới |
| Sai schema hoặc thiếu quyền DB | Thường không | Sửa triển khai/migration/quyền trước |
| Lệnh thanh toán có kết quả không rõ | Không retry mù | Tra cứu giao dịch hoặc dùng khóa chống trùng tại hệ thống đích |
| JVM bị kill giữa tác vụ | Có điều kiện | Xác minh trạng thái nghiệp vụ và chống chạy đồng thời |

Đặt **giới hạn số lần**, exponential backoff có jitter, timeout tổng, và cảnh báo khi vượt giới hạn. Nếu scheduler cũng retry toàn bộ process trong khi client của task retry từng thao tác, cần tính **tổng số lần** để tránh bùng nổ request.

Một chính sách ở mức quy trình:

~~~text
for attempt in 1..MAX_ATTEMPTS:
    try:
        thực hiện thao tác idempotent với cùng businessKey
        xác minh kết quả nghiệp vụ
        return COMPLETED
    catch lỗi không thể retry:
        return FAILED_FINAL
    catch lỗi tạm thời hoặc commit không rõ:
        nếu có thể truy cập nguồn dữ liệu chính:
            đọc kết quả theo businessKey
            nếu kết quả và fingerprint đúng:
                return COMPLETED_AFTER_RECONCILIATION
            nếu fingerprint khác:
                return CONFLICT
        nếu chưa xác minh được:
            backoff có giới hạn rồi thử tiếp hoặc chuyển UNKNOWN
~~~

Đây là **mã giả về chính sách**, không phải đoạn mã Java sử dụng trực tiếp. Thao tác business ở bên trong bắt buộc phải có tính idempotent; nếu không, vòng retry có thể làm sai dữ liệu nhanh hơn.

## 14. Kiểm thử lỗi ở ranh giới commit và JVM

Một bài kiểm tra chỉ chạy thành công hai lần liên tiếp **chưa đủ**. Cần chủ động kiểm thử các cửa sổ lỗi trong môi trường thử nghiệm:

| Kịch bản | Cách tạo điều kiện thử | Bất biến cần xác nhận |
| --- | --- | --- |
| Chạy hai lần cùng đầu vào | Gọi task hai lần liên tiếp | Một record nghiệp vụ cho một business key |
| Hai lần chạy đồng thời | Kích hoạt hai process cùng key | Unique constraint chặn trùng, không ghi đè kết quả |
| Lỗi trước transaction | Ném exception trước khi gọi writer | Không có tác động nghiệp vụ |
| Lỗi trong transaction trước commit | Ném exception khi đang ghi | Các thao tác cùng transaction không commit một phần |
| Mất phản hồi sau khi DB đã commit | Trong integration test, mô phỏng lỗi trả lời **sau khi commit**, rồi kích hoạt retry | Retry cùng key trả kết quả cũ, không tạo record mới |
| JVM dừng sau commit nhưng trước cập nhật metadata Task | Chủ động dừng process ở cửa sổ lỗi trong test | Nghiệp vụ vẫn có đúng một kết quả; TaskExecution có thể dang dở |
| Gọi API rồi client timeout | Dùng fake API hỗ trợ idempotency key | Dịch vụ đích không tạo tác động thứ hai |
| Outbox dispatcher phát lại sự kiện | Mô phỏng crash sau publish trước khi đánh dấu | Consumer nhận dạng `event_id` và không xử lý trùng |
| Database mất kết nối kéo dài | Tắt kết nối trong môi trường kiểm thử | Kết quả chuyển UNKNOWN/cảnh báo, không tự tuyên bố thành công |

**Lưu ý về mô phỏng lỗi:** ném exception sau khi service trả kết quả có thể mô phỏng một caller thất bại **sau commit**, nhưng không chứng minh được hành vi của lỗi mạng thật ngay trong giao thức `COMMIT`. Muốn đánh giá đầy đủ phải kiểm thử với driver, database, transaction manager và cách triển khai production tương đương.

Không gây crash cưỡng bức hoặc ngắt database thật trên hệ thống đang phục vụ người dùng để thử các tình huống này.

### Tiêu chí chấp nhận có thể kiểm tra bằng SQL

Sau nhiều lần thử cùng một khóa:

~~~sql
SELECT tenant_id,
       business_date,
       report_version,
       COUNT(*) AS records
FROM daily_report
GROUP BY tenant_id, business_date, report_version
HAVING COUNT(*) > 1;
~~~

Với khóa chính đúng, truy vấn trên phải không có hàng trùng. Nhưng **không có hàng trùng chưa đủ**: cần kiểm tra fingerprint, nội dung báo cáo, trạng thái đầu ra và việc tác động bên ngoài (nếu có) không bị nhân đôi.

## 15. Vận hành an toàn và khôi phục sau sự cố

Một quy trình vận hành trưởng thành nên có:

1. **Business key có thể truy ngược:** giữ nguyên khóa qua các attempt; lưu thêm `run-id` ở scheduler để liên kết log và từng `TaskExecution`.
2. **Nguồn dữ liệu chính rõ ràng:** nơi xác nhận tác động nghiệp vụ đã hoàn thành; không chỉ dựa vào exit code.
3. **Schema phòng vệ:** `UNIQUE`/`PRIMARY KEY` phù hợp, transaction ngắn và migration được kiểm soát.
4. **Chiến lược dữ liệu đầu vào:** cố định ngày nghiệp vụ, timezone, snapshot/version, tránh cùng key nhưng dữ liệu thay đổi.
5. **Khả năng đối soát:** có truy vấn/trạng thái để phát hiện `UNKNOWN`, `PROCESSING` quá hạn, `TaskExecution.END_TIME IS NULL` và output thiếu.
6. **Retry an toàn:** phân loại lỗi, giới hạn tổng số lần thử, backoff, không retry mù khi API bên ngoài có trạng thái không rõ.
7. **Bảo vệ đồng thời:** unique key, lock/lease hoặc fencing token khi cần, không dùng “kiểm tra rồi chèn” thiếu nguyên tử.
8. **Log và cảnh báo:** có correlation ID; ghi log lỗi commit/network nhưng không rò rỉ mật khẩu, token hoặc payload nhạy cảm.
9. **Quy trình phục hồi:** người vận hành có thể đọc lịch sử các attempt, xác minh đầu ra và quyết định retry, bù trừ hoặc đánh dấu cần can thiệp.
10. **Kiểm tra định kỳ:** thử một số kịch bản crash/timeout trên staging trước khi nâng version Spring Cloud Task, Spring Batch hoặc driver JDBC.

Với hệ thống có yêu cầu kiểm toán, nên giữ nguyên lịch sử các lần chạy kỹ thuật và ghi thêm **kết quả đối soát** ở một bảng hoặc hệ thống điều phối riêng. Không nên xóa dấu vết lỗi ban đầu bằng cách cập nhật trực tiếp metadata thực thi thành “thành công”.

## 16. Bài tập tự kiểm tra

**Câu hỏi 1.** Một task thực hiện `COMMIT`, nhận lỗi “connection reset” và kết thúc với mã `1`. Có thể kết luận transaction đã rollback không? Tại sao?

**Câu hỏi 2.** Vì sao hai lần chạy `TASK_EXECUTION_ID=901` và `902` vẫn có thể đại diện cho **cùng một yêu cầu nghiệp vụ**? Khóa nào nên được dùng để ngăn tạo báo cáo hai lần?

**Câu hỏi 3.** Hai instance cùng `SELECT` không thấy báo cáo rồi cùng `INSERT`. Thêm một câu `SELECT` trước khi ghi có giải quyết triệt để vấn đề không? Cần bảo đảm gì tại database?

**Câu hỏi 4.** Một record báo cáo đã tồn tại cùng business key, nhưng SHA-256 khác với lần thử mới. Nên trả `ALREADY_APPLIED`, ghi đè hay báo conflict? Giải thích tác động của từng lựa chọn.

**Câu hỏi 5.** Một outbox event đã được publish nhưng dispatcher chết trước khi cập nhật `published_at`. Khi dispatcher chạy lại, hệ thống cần thêm cơ chế gì ở consumer?

**Bài tập A — Báo cáo idempotent:** chạy ví dụ PostgreSQL với cùng input ít nhất ba lần, so sánh kết quả `CREATED` và `ALREADY_APPLIED`, số `TaskExecution` và số record `daily_report`.

**Bài tập B — Race condition:** khởi chạy hai process cùng business key. Xác minh đúng một record, không có nội dung ghi đè. Ghi lại các log và cách PostgreSQL xử lý conflict.

**Bài tập C — Commit không rõ:** trong integration test, mô phỏng tình huống dữ liệu đã commit nhưng caller nhận exception. Viết bước đối soát theo key/hash, rồi chứng minh lần chạy lại không tạo dữ liệu thứ hai.

**Bài tập D — Từ database đến API:** thay công việc ghi báo cáo bằng lệnh tạo giao dịch ở API bên ngoài. Thiết kế mã idempotency, API tra cứu trạng thái, điều kiện retry và tình huống cần điều tra thủ công.

## 17. Ghi nhớ

- **Lỗi mạng quanh `COMMIT` hoặc JVM crash không chứng minh transaction đã rollback**. Kết quả có thể chưa xác định và phải được đối soát.
- **`TaskExecution` ghi nhận vòng đời ứng dụng**, còn **khóa nghiệp vụ và dữ liệu đã commit** giúp xác nhận một công việc đã được thực hiện.
- **Idempotency key phải ổn định** qua mọi lần thử cho cùng yêu cầu; `TASK_EXECUTION_ID`, timestamp hoặc số attempt không phải khóa chống trùng thích hợp.
- **Transaction và ràng buộc duy nhất tại database** là tuyến phòng vệ quan trọng trước retry và các lần chạy đồng thời. `SELECT` trước `INSERT` không đủ.
- Với **API, broker hoặc file**, transaction JDBC không bao trùm mọi tác động. Cần idempotency của hệ thống đích, outbox/inbox, đối soát hoặc bù trừ phù hợp.
- Retry cần **phân loại lỗi, giới hạn, backoff và quan sát bên ngoài**. Khi chưa xác minh được, giữ trạng thái **UNKNOWN**, không tự báo thành công.
- Spring Batch có thể hỗ trợ checkpoint/restart theo job/step, nhưng vẫn phải bảo vệ các thao tác có tác động bên ngoài và kiểm thử các thời điểm crash.

## Tài liệu tham khảo

- [Spring Cloud Task Reference — Task lifecycle](https://docs.spring.io/spring-cloud-task/reference/features.html): ghi nhận vòng đời `TaskExecution` và giới hạn khi khởi tạo/ghi metadata.
- [Spring Batch Reference 5.1 — Batch Processing and Transactions](https://docs.spring.io/spring-batch/reference/5.1/transaction-appendix.html): transaction, retry, chunk processing và ranh giới các thao tác có side effect.
- [PostgreSQL — COMMIT](https://www.postgresql.org/docs/current/sql-commit.html): ý nghĩa của một lần commit được database chấp nhận.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): xử lý conflict và ràng buộc duy nhất.

Khi thực hành, cần dùng tài liệu, script schema và phiên bản Spring Boot/Spring Cloud Task/Spring Batch/JDBC driver phù hợp với dự án đang triển khai.

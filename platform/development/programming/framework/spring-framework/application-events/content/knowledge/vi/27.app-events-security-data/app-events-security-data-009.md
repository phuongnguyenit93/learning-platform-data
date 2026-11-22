# Xóa dữ liệu theo chính sách lưu trữ trong hệ thống Spring Application Events

## 1. Bài toán: dữ liệu đã hết hạn nhưng vẫn còn trong event pipeline

Một ứng dụng Spring có thể lưu thông tin khách hàng trong database chính, đồng thời phát `ApplicationEvent` để cập nhật cache, tạo bản ghi audit, đồng bộ search index, đưa event sang Kafka/RabbitMQ, lưu transactional outbox hoặc gửi thông báo. Sau một thời gian, bản ghi gốc không còn cần thiết hoặc chính sách yêu cầu xóa. Nếu chỉ xóa hàng trong database chính, bản sao của dữ liệu có thể vẫn tồn tại ở những nơi khác.

Ví dụ:

```text
CustomerService cập nhật hồ sơ
      |
      +--> relational DB: email, profile
      |
      +--> publishEvent(ProfileChanged)
                  |
                  +--> listener cache: serialized profile
                  +--> listener search: search document
                  +--> listener analytics: event history
                  +--> outbox -> message broker -> consumer DB
                  +--> logs/traces/DLQ/backups

Sau 90 ngày theo chính sách GIẢ ĐỊNH:
      DELETE FROM profile WHERE expired ...
      |
      +--> DB chính đã xóa
      +--> cache, broker log, analytics, backup vẫn có thể giữ bản sao
```

**Xóa dữ liệu theo chính sách lưu trữ (retention-based deletion)** là quy trình xác định dữ liệu nào được giữ, trong bao lâu, vì mục đích gì, khi nào trở thành đủ điều kiện xóa, tại đâu phải xóa và bằng chứng nào chứng minh việc thực thi. Đối với hệ thống event-driven, đây là **bài toán vòng đời dữ liệu xuyên nhiều hệ thống**, không chỉ là một câu lệnh SQL hay một `@EventListener`.

Các nguyên tắc cốt lõi:

1. **Data minimization trước:** đừng đưa dữ liệu nhạy cảm vào event chung khi consumer không thật sự cần.
2. **Retention policy được định nghĩa trước:** không tự chọn số ngày theo cảm tính; thời hạn phụ thuộc loại dữ liệu, mục đích, hợp đồng và quy định áp dụng.
3. **Xóa theo căn cứ và phạm vi:** dữ liệu hết hạn có thể phải giữ lại trong trường hợp có nghĩa vụ pháp lý hoặc legal hold hợp lệ.
4. **Xóa hoặc vô hiệu hóa tất cả bản sao liên quan:** database, cache, chỉ mục tìm kiếm, outbox, queue, dead-letter, log, object storage, analytics và backup.
5. **Có thể kiểm toán nhưng không tái lưu PII:** lưu metadata tối thiểu chứng minh hành động xóa, không ghi lại chính payload nhạy cảm vào audit log.
6. **Có khả năng phục hồi:** xóa nguồn chính và truyền yêu cầu xóa đến consumer phải có cơ chế theo dõi, retry, idempotency và xử lý thiếu đồng bộ.

## 2. Phân biệt retention, erasure request, TTL và domain event

| Thuật ngữ | Ý nghĩa | Bẫy thường gặp |
| --- | --- | --- |
| Retention policy | Quy tắc xác định thời hạn giữ và điều kiện xóa | Dùng cùng một TTL cho mọi loại dữ liệu |
| Retention expiration | Một bản ghi đã qua thời điểm đủ điều kiện xóa | Xóa cả bản ghi có căn cứ giữ hợp lệ |
| Erasure request | Yêu cầu xóa theo quyền hoặc quy trình cụ thể | Coi mọi yêu cầu là xóa tức thì không cần xác minh điều kiện/ngoại lệ |
| TTL trong cache | Thời gian cache entry tồn tại | Tưởng cache TTL thay thế việc xóa trong DB/broker |
| Logical deletion | Đánh dấu `deleted=true` hoặc `deletedAt` | PII vẫn còn trong storage, chỉ ẩn khỏi giao diện |
| Physical deletion | Xóa hoặc vô hiệu hóa bản dữ liệu thực tế | Quên index, replica, log, backup, object storage |
| Crypto-erasure | Vô hiệu hóa key mã hóa để dữ liệu không còn giải mã được theo kiến trúc đã định | Không kiểm tra bản plaintext, key backups hoặc bản sao khác |
| Deletion event | Tín hiệu "record/subject đã bị xóa" cho hệ thống khác | Tưởng publish event là bằng chứng consumer đã xóa thành công |
| Tombstone trong log compacted | Marker mang key với value null theo semantics công nghệ | Tưởng tombstone lập tức xóa mọi bản sao lịch sử |

Một `ProfileErased` hoặc `RetentionExpired` là event về **một thay đổi đã được chấp nhận**; nó không phải lời bảo đảm vật lý rằng mọi byte nhạy cảm đã biến mất trên mọi node và mọi backup. Phải thống nhất tên event theo ngữ nghĩa chính xác:

- `ErasureRequested`: yêu cầu đã được ghi nhận, chưa chắc hoàn thành.
- `PrimaryRecordErased`: bản ghi đã bị xóa trong kho dữ liệu chính.
- `ConsumerCopyErased`: một consumer báo đã xóa bản sao của nó.
- `ErasureCompleted`: hệ thống điều phối đã xác minh các bước bắt buộc theo policy.

Không dùng `ErasureCompleted` cho thời điểm vừa gọi `repository.delete(...)`.

## 3. Xác định chính sách lưu trữ trước khi viết code

Chính sách cần được quản trị bằng tài liệu và dữ liệu cấu hình có phiên bản, không rải các số `30`, `90`, `365` ngày trong nhiều listener.

Bảng quy định mẫu **chỉ để minh họa**:

| Data class | Mục đích | Retention trigger | Điều kiện xóa | Yêu cầu bổ sung |
| --- | --- | --- | --- | --- |
| Hồ sơ người dùng tạm | Cung cấp tính năng | Hết thời gian sử dụng/đóng tài khoản | `expiresAt <= now`, không có hold hợp lệ | Xóa cache và chỉ mục liên quan |
| Event outbox đã xác nhận | Truyền sự kiện | `deliveredAt` | Đã giao + qua khoảng chờ retry/audit theo policy | Không xóa pending event |
| Log ứng dụng | Chẩn đoán | Thời điểm ghi log | Quá hạn log retention | Không log secret/PII ngay từ đầu |
| Dead-letter message | Điều tra lỗi | Thời điểm vào DLQ | Quá thời hạn cho phép hoặc lỗi đã giải quyết | Hạn chế quyền xem payload |
| Session/cache | Phục vụ request | Hết hiệu lực phiên | TTL/explicit invalidation | Không dùng TTL để thay quyền xóa dữ liệu gốc |
| Backup | Khôi phục sau thảm họa | Thời điểm snapshot | Theo vòng đời backup được phê duyệt | Có biện pháp ngăn phục hồi dữ liệu đã xóa |

Từng loại phải có **data owner**, nơi lưu, cơ sở retention, người được duyệt chính sách, policy version, retention start, cách xác định `expiresAt`, exception/hold, storage targets và SLA xóa.

Cần phân biệt ba thời điểm:

1. **`createdAt`**: khi dữ liệu được tạo.
2. **`retentionStartsAt`**: khi bắt đầu đếm thời gian giữ; có thể là khi hợp đồng kết thúc hoặc khi ticket đóng, không nhất thiết bằng createdAt.
3. **`expiresAt`**: thời điểm đủ điều kiện xóa theo chính sách hiện hành đã được tính toán và lưu/kiểm tra.

Nên dùng `Instant`/UTC trong mô hình để tránh rủi ro daylight saving và chuyển đổi múi giờ; nếu chính sách dựa trên ngày lịch của một quốc gia, việc tính `expiresAt` cần định nghĩa `ZoneId` và quy tắc ngày tháng chính xác trước khi đổi sang `Instant`. Không lấy thời gian JVM tùy ý thay cơ sở policy mà không có kiểm thử.

### Pháp lý và ngoại lệ

Nguyên tắc `storage limitation` trong GDPR là một ví dụ quốc tế về giới hạn thời gian giữ dữ liệu cá nhân theo mục đích; quyền xóa có những điều kiện và ngoại lệ, chẳng hạn nghĩa vụ pháp lý hoặc yêu cầu bảo vệ quyền lợi pháp lý. **Không mặc định mọi ứng dụng Spring đều chịu GDPR, không tự suy ra thời hạn 30/90 ngày từ GDPR, và không coi legal hold do bất kỳ nhân viên tự bật là cơ sở giữ dữ liệu vô thời hạn.** Trong thực tế phải xác định luật, hợp đồng và chính sách được phê duyệt cho tổ chức, quốc gia và loại dữ liệu đang xử lý.

Legal hold cần có căn cứ, phạm vi rõ ràng, người phê duyệt, thời điểm xét lại, khả năng thu hồi và nhật ký thao tác an toàn. Trong code, một cờ `legal_hold` chỉ là mô hình tối giản; hệ thống thật cần lưu lý do/căn cứ có kiểm soát và đánh giá liệu có thể xóa các trường không thuộc phạm vi hold.

## 4. Kiểm kê mọi bản sao của dữ liệu phát sinh từ event

Sau khi một event được phát, cần biết ai có thể tiếp nhận và lưu lại bản sao:

```text
Source DB (PII gốc)
  |
  +--> Spring @EventListener trong cùng JVM
  |       +--> local cache
  |       +--> secondary index
  |       +--> file/object storage
  |
  +--> transactional outbox table
  |       +--> relay -> Kafka/RabbitMQ
  |                        +--> consumer database
  |                        +--> retry topic / dead-letter queue
  |                        +--> analytics / data lake
  |
  +--> logging, tracing, APM, exception reports
  |
  +--> replicas, snapshots, backups
```

Đối với mỗi điểm lưu, ghi nhận:

- Dữ liệu được lưu dưới dạng gì: plaintext, encrypted field, tokenized reference, hash, event ID?
- Có chứa PII trực tiếp hoặc dữ liệu liên kết tới cá nhân không?
- Ai quản lý retention và quyền truy cập?
- Có khả năng xóa theo `subjectRef`/`eventId` hay chỉ xóa theo partition/time?
- Nếu xóa bản gốc, consumer có được yêu cầu xóa không? Ai theo dõi acknowledgement?
- Nếu restore backup hoặc replay topic, làm thế nào tránh **tái nhập dữ liệu đã xóa**?
- DLQ/trace/log có giữ lỗi chứa nguyên payload hay không?

Mọi lần nhân bản payload tăng chi phí kiểm soát dữ liệu. Nếu consumer chỉ cần `customerRef` và `changedFields`, tránh gửi nguyên `CustomerEntity` có email, địa chỉ hoặc credentials. ID dạng UUID cũng có thể là dữ liệu cá nhân gián tiếp nếu liên kết lại được, nên cần có retention và phân quyền phù hợp.

## 5. Thiết kế quy trình xóa theo retention bằng application events

Một luồng an toàn có thể tổ chức như sau:

```text
Retention policy service / scheduler
        |
        v
Find eligible records by expires_at <= now
        |
        +-- Không đủ điều kiện? => skip
        +-- Có legal hold hợp lệ? => skip / review
        |
        v
Transactional deletion unit
        |
        +-- Re-check expiry/hold ngay tại DELETE
        +-- Delete hoặc anonymize record
        +-- Ghi outbox erasure notification (nếu cần durable)
        |
        v
COMMIT
        |
        +-- In-process AFTER_COMMIT listener:
        |     invalidate cache / metrics / local update
        |
        +-- Outbox relay:
              send erase command/event to consumers
              await/track acknowledgements
              retry, DLQ, alert if required
        |
        v
Verify required copies erased
        |
        +-- update minimal erasure ledger / evidence
        +-- enforce restore and replay suppression
```

### Re-check khi xóa

Không chỉ `SELECT ref FROM ... WHERE expires_at <= ?` rồi xóa theo ID đơn thuần. Giữa lúc đọc và lúc xóa, một transaction khác có thể gia hạn retention, cập nhật legal hold, hoặc thay policy. Nên đưa điều kiện vào chính câu `DELETE`, chẳng hạn:

```sql
DELETE FROM private_profiles
WHERE ref = ?
  AND expires_at <= ?
  AND legal_hold = FALSE;
```

Số hàng thực sự xóa (affected rows) mới là bằng chứng có thay đổi. Nếu `affectedRows = 0`, có thể record đã được worker khác xóa, được gia hạn hoặc đang hold; đừng phát `ProfileErased` như thể đã xóa được.

Với nhiều worker, cần phương pháp claim/lock/lease phù hợp, giới hạn batch và bảo vệ tính idempotent. Không dùng một `SELECT` lớn rồi mở transaction kéo dài hàng giờ.

### Dọn theo batch

Thay vì một câu delete hàng triệu dòng tạo lock/replication lag lớn, dùng các batch giới hạn, transaction ngắn, backpressure và monitoring. Với SQL có `SKIP LOCKED` hoặc các biến thể claim row, cú pháp và semantics phụ thuộc database. Đừng copy SQL vendor-specific sang H2/PostgreSQL/MySQL mà không kiểm tra tính tương thích và isolation.

Nếu quan hệ foreign key/cascade phức tạp, thiết kế thứ tự xóa và xử lý phụ thuộc rõ ràng. Không vô tình tạo "orphan" lưu PII ở bảng phụ. Nếu dùng JPA, lưu ý một số bulk delete như `JpaRepository.deleteAllInBatch(...)` **không chạy JPA entity lifecycle callbacks** và có thể bỏ qua cascade semantics; không dựa vào `@PreRemove` để thông báo xóa khi dùng bulk delete.

## 6. Spring: @Scheduled, @TransactionalEventListener và ranh giới transaction

### 6.1. @Scheduled chỉ kích hoạt một job, không tự xóa dữ liệu

Spring cung cấp `@Scheduled` kết hợp `@EnableScheduling`. Một phác thảo:

```java
// Trích đoạn minh họa, cần Spring bean, imports và @EnableScheduling.
@Scheduled(cron = "0 15 2 * * *", zone = "UTC")
public void eraseExpired() {
    retentionService.cleanup(Instant.now());
}
```

Cron của Spring có **sáu trường**, ví dụ trên chạy theo lịch 02:15 UTC mỗi ngày. Lịch không đồng nghĩa quy trình xóa hoàn thành: job có thể lỗi, được chạy trùng trên nhiều replica, hoặc bỏ qua giờ chạy khi downtime. Cần theo dõi last successful run, backlog, error count, batch duration và xử lý retry.

Nếu nhiều instance cùng có `@EnableScheduling`, mỗi instance có thể chạy cùng job. Cần leader election, distributed lock, DB claim hoặc chiến lược concurrency an toàn. Không coi annotation tự tạo cluster-wide single scheduler.

### 6.2. Transaction và thời điểm phát event

Nếu xóa bản ghi trong transaction rồi gọi `publishEvent(new ProfileErased(...))`, các `@EventListener` đồng bộ **có thể chạy trước commit**; nếu transaction rollback sau đó, side effect bên ngoài không tự hoàn tác.

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` phù hợp cho phản ứng **sau khi transaction DB liên quan commit thành công**. Khi transaction rollback, callback này không chạy. Tuy nhiên:

- Nó không tạo queue durable.
- Process chết sau commit trước khi callback chạy có thể làm mất tác vụ bên ngoài.
- Sau commit, lỗi callback không rollback được thay đổi đã commit.
- Nếu listener sau commit cần **ghi thêm database**, xem xét một transaction mới (`REQUIRES_NEW` qua service/proxy phù hợp), vì tài nguyên transaction cũ có thể vẫn được bind nhưng không còn commit tiếp theo.

Muốn bảo đảm hệ thống khác cuối cùng cũng biết sự kiện xóa dù process crash, dùng **transactional outbox** được ghi *trong cùng transaction* với xóa nguồn chính. Ví dụ chạy được sau đây minh họa after-commit in-process để dễ hiểu; phần outbox dành cho production được trình bày riêng.

## 7. Ví dụ Maven + Java 17 chạy được: xóa quá hạn nhưng giữ legal hold

Ví dụ sử dụng **Spring Framework 6.2.8**, `spring-jdbc`, H2 2.3.232 và `TransactionTemplate`. Dữ liệu giả gồm ba hồ sơ:

- `profile-expired`: hết hạn và **không** có legal hold → phải xóa.
- `profile-held`: đã hết hạn nhưng **có** legal hold → không xóa.
- `profile-future`: chưa hết hạn → không xóa.

Sau khi delete được thực hiện trong transaction, chương trình publish một event `ProfileErased(opaqueRef, policyCode)`; listener `AFTER_COMMIT` chỉ in một thông báo **không chứa ref/email**. Dùng thời điểm giả lập cố định để đầu ra không phụ thuộc ngày chạy thực tế.

Đây là demo về quyết định xóa, transaction và application event, **không phải** ứng dụng hoàn chỉnh về xác minh pháp lý, phân quyền, secure erasure trên SSD, outbox, backups hoặc audit hệ thống.

### 7.1. Cấu trúc

```text
retention-erasure-demo/
├── pom.xml
└── src/main/java/demo/RetentionErasureDemo.java
```

### 7.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>retention-erasure-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.RetentionErasureDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. src/main/java/demo/RetentionErasureDemo.java

```java
package demo;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class RetentionErasureDemo {

    // Không chứa email hoặc bất kỳ giá trị hồ sơ nhạy cảm nào.
    // opaqueRef vẫn phải được bảo vệ nếu có thể tra cứu danh tính.
    public record ProfileErased(String opaqueRef, String policyCode) {}

    public static final class RetentionService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate transactions;
        private final ApplicationEventPublisher publisher;

        public RetentionService(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.transactions = transactions;
            this.publisher = publisher;
        }

        public int cleanup(Instant now) {
            return transactions.execute(status -> {
                List<String> refs = jdbc.query(
                        "select ref from private_profiles " +
                        "where expires_at <= ? and legal_hold = false " +
                        "order by ref",
                        (rs, n) -> rs.getString("ref"),
                        Timestamp.from(now));

                System.out.println("job: candidates=" + refs.size());

                int deleted = 0;
                for (String ref : refs) {
                    // Re-check expiry/hold ngay tại thao tác DELETE.
                    int affected = jdbc.update(
                            "delete from private_profiles " +
                            "where ref = ? and expires_at <= ? " +
                            "and legal_hold = false",
                            ref, Timestamp.from(now));

                    if (affected == 1) {
                        deleted++;
                        publisher.publishEvent(
                                new ProfileErased(ref, "RETENTION"));
                    }
                }

                System.out.println("job: deleted=" + deleted);
                return deleted;
            });
        }
    }

    public static final class ErasureObserver {
        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void onErased(ProfileErased event) {
            // Không log ref hoặc email trong event/DB.
            System.out.println(
                    "listener: deletion committed policy="
                            + event.policyCode());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:retention_demo;DB_CLOSE_DELAY=-1",
                    "sa", "");
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        ErasureObserver erasureObserver() {
            return new ErasureObserver();
        }

        @Bean
        RetentionService retentionService(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher publisher) {
            return new RetentionService(jdbc, transactions, publisher);
        }
    }

    private static void seed(
            JdbcTemplate jdbc,
            String ref,
            String email,
            String expiry,
            boolean legalHold) {
        jdbc.update(
                "insert into private_profiles " +
                "(ref, email, expires_at, legal_hold) " +
                "values (?, ?, ?, ?)",
                ref, email, Timestamp.from(Instant.parse(expiry)),
                legalHold);
    }

    private static boolean exists(JdbcTemplate jdbc, String ref) {
        Integer count = jdbc.queryForObject(
                "select count(*) from private_profiles where ref = ?",
                Integer.class, ref);
        return count != null && count > 0;
    }

    private static int count(JdbcTemplate jdbc) {
        Integer count = jdbc.queryForObject(
                "select count(*) from private_profiles",
                Integer.class);
        return count == null ? 0 : count;
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                    "create table private_profiles (" +
                    "ref varchar(64) primary key," +
                    "email varchar(255) not null," +
                    "expires_at timestamp not null," +
                    "legal_hold boolean not null)");

            seed(jdbc, "profile-expired",
                    "old@example.invalid",
                    "2025-01-01T00:00:00Z", false);
            seed(jdbc, "profile-held",
                    "held@example.invalid",
                    "2025-02-01T00:00:00Z", true);
            seed(jdbc, "profile-future",
                    "future@example.invalid",
                    "2027-01-01T00:00:00Z", false);

            Instant now = Instant.parse(
                    "2026-11-11T00:00:00Z");

            System.out.println("before: rows=" + count(jdbc));
            int deleted = context.getBean(RetentionService.class)
                    .cleanup(now);
            System.out.println("result: deleted=" + deleted);
            System.out.println("after: rows=" + count(jdbc));
            System.out.println("after: held=" +
                    exists(jdbc, "profile-held") +
                    " future=" + exists(jdbc, "profile-future") +
                    " expired=" + exists(jdbc, "profile-expired"));

            int secondRun = context.getBean(RetentionService.class)
                    .cleanup(now);
            System.out.println("again: deleted=" + secondRun);
        }
    }
}
```

### 7.4. Chạy và kết quả

Chạy từ thư mục chứa `pom.xml`, yêu cầu JDK 17+ và Maven:

```bash
mvn -q clean compile exec:java
```

Đầu ra do chương trình tự in (không tính thông tin phụ Maven):

```text
before: rows=3
job: candidates=1
job: deleted=1
listener: deletion committed policy=RETENTION
result: deleted=1
after: rows=2
after: held=true future=true expired=false
job: candidates=0
job: deleted=0
again: deleted=0
```

Giải thích:

1. `now` được cố định tại ngày 11/11/2026 UTC. `profile-expired` có `expires_at` trước `now` và `legal_hold=false`, nên đủ điều kiện. `profile-held` cũng quá hạn nhưng hold còn hiệu lực; `profile-future` chưa quá hạn.
2. `TransactionTemplate` mở transaction; `SELECT` lấy một ứng viên.
3. `DELETE` dùng lại điều kiện expiry và hold để giảm rủi ro xóa nhầm nếu trạng thái thay đổi sau bước chọn.
4. Chỉ khi `affected == 1` mới publish `ProfileErased`; nếu không xóa được thì không khẳng định đã xóa.
5. `@TransactionalEventListener(AFTER_COMMIT)` đăng ký callback trong transaction. Nó in sau khi transaction commit, **trước khi `cleanup(...)` trả về**.
6. Query ngoài transaction xác nhận còn đúng hai record; data đang hold và data chưa hết hạn vẫn có mặt.
7. Lần cleanup thứ hai không tìm thấy record đủ điều kiện, trả 0: tác vụ có thể chạy lại mà không phát thêm event cho record đã xóa.
8. Email giả dùng miền `example.invalid`; code không in dữ liệu email ra stdout. **Opaque reference vẫn có thể là PII gián tiếp** nếu bị liên kết với người cụ thể.

**Giới hạn của demo:** In-process listener không bền vững qua crash; không có batch limit hoặc parallel worker; một transaction bao toàn bộ ứng viên; không có authorization, policy registry/hold approval, outbox, durable audit, backup deletion hoặc xác minh bản sao. Với production, mở rộng theo các phần tiếp theo.

## 8. Propagation: xóa dữ liệu ở các consumer có lưu bản sao

Một cách thiết kế robust là **erasure workflow có theo dõi trạng thái**:

```text
Primary deletion TX
  ├─ delete profile rows
  ├─ insert erasure_outbox(
  |     erasure_id, subject_ref, policy_version,
  |     request_type, status, created_at)
  └─ COMMIT

Outbox relay
  ├─ gửi erasure command/event với idempotency key
  ├─ retry/backoff khi consumer tạm lỗi
  ├─ không phát lại payload PII đã bị xóa
  └─ giữ deadline/escalation nếu không có ack

Consumers
  ├─ cache -> invalidate
  ├─ search index -> delete by scoped ID
  ├─ analytics -> erase/anonymize theo policy
  ├─ object storage -> delete/version purge theo workflow
  └─ return completion/failure acknowledgement

Erasure coordinator
  ├─ đối chiếu target list và acknowledgements
  ├─ báo chưa hoàn thành nếu consumer còn lỗi
  └─ lưu evidence tối thiểu sau khi mọi điều kiện được xác minh
```

### Outbox không tự giải quyết việc xóa

Transactional outbox bảo đảm **ý định thông báo** được lưu trong cùng transaction với thay đổi DB gốc. Nếu process chết sau commit, relay có thể tiếp tục. Nhưng hệ thống không bảo đảm consumer đã xóa chỉ vì relay đã gọi broker, và không bảo đảm exactly-once: nếu publish thành công nhưng relay chết trước khi đánh dấu delivered, message có thể được gửi lại.

Vì thế consumer erasure handler phải **idempotent**: cùng `erasureId` hoặc `subjectRef + policyVersion` gửi lại nhiều lần vẫn dẫn tới cùng kết quả xóa, không hồi sinh dữ liệu hoặc tăng side effect ngoài ý muốn.

Cũng phải **xóa outbox event theo retention** sau khi đã đủ thời gian lưu phục vụ retry và audit. Tuy nhiên không xóa pending event trước khi giao để tránh mất thông tin về việc cần xóa. Nếu outbox chứa định danh liên kết với người dùng, chính nó cũng có data lifecycle riêng; không lưu vô hạn chỉ để làm bằng chứng.

### Không "fan out" thông tin nhạy cảm mới trong erasure event

Sự kiện yêu cầu xóa nên chỉ mang metadata đủ để định tuyến có kiểm soát: `erasureId`, opaque subject reference, scope, policy version và reason code khi cần. Không đính kèm toàn bộ email, hồ sơ, bản sao event cũ hoặc credentials vào thông báo xóa. Không in ID có thể liên kết vào metric tag low-cardinality.

Một consumer chỉ nên được gửi thông điệp khi nó thực sự có bản sao cần xóa. Đừng phát cho toàn hệ thống nếu erasure event tự tiết lộ thông tin nhạy cảm về chủ thể.

## 9. Broker retention, log compaction, tombstone và DLQ

### Retention của Kafka không giống xóa một cá nhân theo khóa

Trong Kafka, `cleanup.policy=delete` thường xóa **log segments** cũ theo chính sách thời gian/dung lượng. Đây không phải API đảm bảo xóa ngay tất cả message có `customerRef=X` ở bất kỳ vị trí nào trong segment.

`cleanup.policy=compact` giữ giá trị mới nhất theo key sau compaction; một tombstone (record có key và value null) có thể đánh dấu một key cần xóa khỏi log compacted. Tuy vậy:

- Compaction **không xảy ra ngay lập tức** khi ghi tombstone.
- Không bảo đảm xóa dữ liệu trong topic khác, retry topic, DLQ, consumer database, backups, log hệ thống.
- Nếu một event chứa PII nằm ở key khác hoặc trong payload không gắn key cần xóa, tombstone không thể tự suy ra bản sao đó.
- Tombstone có retention và cơ chế dọn riêng, chẳng hạn `delete.retention.ms`; consumer chạy trễ/replay cần được thiết kế theo đặc tính thực tế của log.
- Với `cleanup.policy=delete,compact`, các cơ chế retention/compaction có thể cùng áp dụng theo cấu hình.
- Restore/replay event cũ có thể tái tạo một bản ghi từng bị xóa nếu consumer không kiểm tra erasure ledger/version.

Vì vậy tombstone chỉ là **một thành phần kỹ thuật** của quy trình xóa theo chính sách, không phải bằng chứng tuân thủ hoàn chỉnh.

### RabbitMQ, queue và dead-letter

Đối với queue, cần xem thời hạn message, dead-letter retention, redelivery, consumer retry và các bản sao do hệ thống hỗ trợ tạo ra. Một message "đã ack" có thể đã được lưu vào một consumer DB khác, còn một message đưa vào DLQ có thể giữ cả payload PII lâu hơn mong muốn.

Cần policy cho failed messages: nếu sự kiện nghiệp vụ hết hạn mà retry vô hạn, dữ liệu có thể bị giữ ở retry queue/DLQ quá thời hạn. Nếu xóa DLQ trước khi điều tra xong, có thể mất dấu hiệu lỗi vận hành. Giải pháp phải có căn cứ ưu tiên, retention và quy trình quarantine/triage rõ.

## 10. Logs, traces, analytics, object storage và backup

### 10.1. Logs và observability

Một listener có thể log nguyên event:

```java
// Không nên làm với event chứa PII/secrets.
log.info("received {}", event);
```

Nếu event là Java `record`, `toString()` mặc định in toàn bộ field; JSON logger hoặc APM có thể serialize theo accessor. **Không thu thập PII** là hàng rào tốt hơn việc thu thập rồi cố redaction. Chỉ log schema allowlist, reason code, loại event đã phân loại và mã trạng thái vận hành.

Log/trace thường không hỗ trợ xóa chọn lọc một record dễ dàng. Hãy hạn chế dữ liệu ngay từ đầu và thiết kế retention ở cấp hệ thống lưu log. Sự kiện erasure riêng cũng không nên copy lại dữ liệu muốn xóa vào error message.

### 10.2. Analytics và materialized views

Một event đã ghi sang data warehouse có thể tiếp tục nằm trong bảng history, materialized view, export CSV, snapshot hoặc dashboard. Chính sách phải chỉ rõ raw table, derived table, aggregate metrics có còn khả năng nhận diện hay không, và quy trình xóa/anonymize tương ứng.

Không mặc định "aggregate thống kê" đã ẩn danh: nếu nhóm nhỏ, join với dữ liệu ngoài hoặc giữ identifier ổn định, vẫn có thể nhận diện. Khi thật sự anonymize không thể đảo ngược theo tiêu chuẩn áp dụng, dữ liệu có thể có quy tắc khác; điều đó cần được kiểm chứng, không tự gắn nhãn.

### 10.3. Object storage và versioning

`DELETE object` có thể chỉ xóa phiên bản hiện tại hoặc đặt delete marker trong storage có versioning. Phải xét noncurrent versions, object lock/legal hold, replica, lifecycle policies và inventory. Nếu giữ file vì bằng chứng pháp lý, cần policy rõ chứ không bỏ qua mọi yêu cầu xóa.

### 10.4. Backups: xóa khỏi hệ thống hoạt động chưa xóa khỏi snapshot

Backup có thể bất biến và không hỗ trợ xóa chọn lọc theo chủ thể. Thiết kế thực tế có thể bao gồm:

- Giới hạn retention của backup theo chính sách đã phê duyệt.
- Mã hóa backup, phân quyền truy cập, log việc restore.
- Khi restore, thực thi một **erasure/revocation ledger** hoặc cơ chế replay-filter trước khi phục vụ dữ liệu; không hồi sinh dữ liệu đã được xóa.
- Có quy trình bảo vệ và xóa dữ liệu đã hết hạn trong bản sao phục hồi theo nghĩa vụ áp dụng.
- Đánh giá khả năng crypto-erasure nếu dữ liệu được mã hóa bằng các key có lifecycle độc lập và không còn plaintext/key copies khác.

Không hứa "đã xóa trên mọi backup ngay lập tức" nếu storage không hỗ trợ; cũng không được dùng hạn chế backup để bỏ mặc yêu cầu xóa. Quy trình phải được data owner, privacy/security và pháp lý đánh giá theo chính sách thực tế.

## 11. Xóa logic, xóa vật lý và idempotency

### Soft delete

Một update:

```sql
UPDATE customer_profile
SET deleted_at = CURRENT_TIMESTAMP
WHERE ref = ?;
```

giúp ngừng hiển thị hoặc đánh dấu yêu cầu nhưng **PII vẫn ở database**. Nó không hoàn thành physical erasure nếu chính sách yêu cầu xóa. Cần dọn cột nhạy cảm hoặc xóa row theo workflow đã được chấp thuận.

### Hard delete

Một câu `DELETE` loại record khỏi logical table, nhưng vẫn có thể còn bản sao trong transaction log, replica, snapshot và storage cấp thấp. Không tự kết luận secure physical erasure trên thiết bị lưu trữ chỉ từ SQL DELETE.

### Anonymization và minimization

Một số use case cần giữ số liệu thống kê sau khi xóa liên kết cá nhân. Có thể dùng quá trình anonymization được đánh giá đủ mạnh; đơn giản thay email bằng hash không làm dữ liệu chắc chắn vô danh nếu hash có thể bị brute force hoặc liên kết lại.

### Idempotent erasure

Thiết kế tốt là xóa lại một record đã không còn tồn tại vẫn được coi là "đã đạt trạng thái không còn" khi phù hợp, thay vì báo lỗi và retry vô hạn. Nhưng **ack thành công** phải phân biệt giữa:

- Record nguồn đã không còn.
- Các bản sao bắt buộc của consumer đã không còn.
- Metadata/evidence đã được cập nhật theo policy.

Một API có thể trả `ALREADY_ABSENT` cho deletion request lặp mà không tái tạo dữ liệu hay khởi động lại toàn bộ quy trình; kiểm tra quyền và scope vẫn cần thiết.

## 12. Scheduling và vận hành production

### 12.1. Không xóa quá lớn trong một transaction

Khi cần xóa hàng triệu record, transaction kéo dài có thể giữ lock, tăng WAL/redo/replication lag và gây timeout. Dùng batch nhỏ được cấu hình, đánh dấu checkpoint, transaction ngắn, và ghi metrics theo batch. Nếu cần thực thi theo partition, phải đảm bảo điều kiện lọc đúng và không bỏ sót record nằm ở ranh giới.

### 12.2. Multi-instance và cạnh tranh

Không dựa duy nhất vào `@Scheduled` với nhiều pods mà nghĩ chỉ một pod chạy. Có thể dùng distributed lock/leader, claim rows và `SKIP LOCKED` theo database, hoặc chia sharding rõ. Câu delete có điều kiện vẫn cần để xử lý thay đổi concurrent. Trong một số workflow, claim và delete phải cùng transaction/isolation để không xử lý một record bởi nhiều worker cùng lúc.

### 12.3. Lỗi và retry

Phân biệt lỗi tạm (database timeout, 503) và lỗi cố định (permission denied, policy conflict, missing schema). Retry có exponential backoff với jitter, max attempts, deadline và quan sát lag. Không retry mù toàn bộ batch sau khi đã gửi notifications không idempotent; dùng stable erasure ID và trạng thái theo từng target.

### 12.4. Metrics

Các metric đề xuất (không phải có sẵn tự động từ `@EventListener`):

| Metric | Cách hiểu |
| --- | --- |
| `retention.eligible.count` | Số record đủ điều kiện ở thời điểm đo |
| `retention.deleted.count` | Số record đã bị xóa trong primary DB |
| `retention.held.count` | Số record quá hạn bị hoãn vì hold hợp lệ |
| `retention.job.duration` | Thời gian cleanup batch |
| `retention.job.failure` | Lỗi thực thi |
| `erasure.outbox.pending` | Yêu cầu xóa cần chuyển tiếp |
| `erasure.consumer.pending` | Các consumer chưa ack |
| `erasure.consumer.failed` | Consumer xóa thất bại |
| `erasure.oldest.pending.age` | Độ trễ của yêu cầu lâu nhất |

Metric và log không nên dùng `customerRef`, email hoặc event ID làm **low-cardinality tag**. Dùng loại dữ liệu, policy code, target system và outcome thuộc tập hữu hạn. Trace/log correlation có thể cần ID nhưng phải có quyền truy cập, minimization và retention phù hợp.

### 12.5. Chứng minh hiệu lực, không chỉ log "deleted"

Một dashboard thành công cần theo dõi **coverage of required targets** và bằng chứng kiểm tra. "Job đã chạy" không có nghĩa mọi bản sao được xóa. Khi consumer không phản hồi, dashboard phải hiển thị `PENDING/FAILED` và escalation, không đánh dấu toàn bộ request hoàn thành.

## 13. Kiểm thử chính sách lưu trữ

Nên kiểm thử từ domain tới infrastructure:

1. **Hết hạn:** record có `expires_at < now`, không hold → eligible.
2. **Đúng ranh giới:** record có `expires_at == now` → kết quả đúng theo quy ước `<=`.
3. **Chưa hết hạn:** `expires_at > now` → không xóa.
4. **Legal hold:** record quá hạn có hold hợp lệ → không xóa; kiểm tra audit/approval của hold.
5. **Thay đổi đồng thời:** hold được bật hoặc expiry được gia hạn trước delete → affectedRows = 0; không phát event xóa.
6. **Đếm thực tế:** chỉ publish một `ProfileErased` khi thực sự delete 1 row; không phát khi delete 0 row.
7. **Rollback:** transaction delete rollback → listener `AFTER_COMMIT` không chạy; không có trạng thái "đã xóa" giả.
8. **Idempotency:** chạy cleanup hai lần → lần thứ hai không xóa thêm hoặc phát lại event không có căn cứ.
9. **Restart:** crash sau commit → outbox event vẫn tồn tại để relay tiếp tục; in-memory callback alone không đủ.
10. **Fan-out:** cache, search, warehouse, object storage được xóa theo scope; chỉ đánh dấu complete khi các target bắt buộc đã ack.
11. **Tombstone/replay:** replay Kafka/backup không tái tạo record đã bị xóa; test dữ liệu cũ qua các phiên bản schema.
12. **DLQ/logs:** không lưu toàn bộ PII trong failure report hoặc dead-letter payload vượt quá policy.
13. **Backups:** test quy trình restore và erasure ledger, không phục hồi một người dùng đã bị xóa.
14. **Volume:** dọn hàng triệu records theo batch, giám sát locks/replication lag và tài nguyên.
15. **Quyền truy cập:** không để bên không có quyền gửi erasure request nhằm xóa dữ liệu người khác; audit tối thiểu.
16. **Clock/time zone:** thử UTC, ngày lịch và các trường hợp daylight saving nếu policy dựa theo lịch địa phương.

Một số assertion có ý nghĩa:

```java
// Trích đoạn ý tưởng cho integration test dùng các fixture tương ứng.
assertEquals(1, retentionService.cleanup(fixedInstant));
assertFalse(profileExists("profile-expired"));
assertTrue(profileExists("profile-held"));
assertTrue(profileExists("profile-future"));
assertEquals(0, retentionService.cleanup(fixedInstant));
```

Trích đoạn cần class/test fixture phù hợp, không phải chương trình độc lập. Với kiểm thử multi-service, test end-to-end bằng môi trường có broker/storage và cơ chế quan sát acknowledgement thật.

## 14. Lỗi phổ biến cần tránh

**Sai 1 — Xóa nguồn chính rồi coi như toàn bộ dữ liệu đã biến mất.** Sự kiện có thể đã được sao chép vào cache, log, DLQ, analytics và backup.

**Sai 2 — Dùng soft delete làm bằng chứng hoàn thành physical erasure.** Trường PII vẫn nằm trong bảng gốc.

**Sai 3 — Tin rằng @EventListener tự được gọi khi SQL DELETE.** Spring Application Events không tự phát event cho mọi thao tác xóa dữ liệu. Cần publisher hoặc cơ chế repo/ORM đã cấu hình, và bulk delete có thể bỏ qua lifecycle callbacks.

**Sai 4 — Publish "ErasureCompleted" ngay trước transaction commit.** Rollback sau đó làm sự kiện sai sự thật.

**Sai 5 — Dùng AFTER_COMMIT như queue durable.** Callback có thể mất nếu process chết; dùng outbox khi có yêu cầu khôi phục.

**Sai 6 — Dùng @Scheduled mà không xét multi-instance.** Nhiều replicas có thể quét/xóa cùng lúc; cần claim/lock/idempotency.

**Sai 7 — Bỏ qua legal hold và ngoại lệ giữ dữ liệu.** Dữ liệu quá hạn về mặt thời gian có thể chưa đủ điều kiện xóa theo căn cứ hiện hành.

**Sai 8 — Đưa email/PII gốc vào erasure event hoặc log.** Hành động xóa lại tạo thêm bản sao dữ liệu nhạy cảm.

**Sai 9 — Gửi tombstone Kafka rồi khẳng định xóa tất cả.** Compaction không tức thì, không xóa consumer DB, backups hoặc topic khác.

**Sai 10 — Xóa ngay outbox pending.** Relay không còn dữ liệu để retry; các consumer có thể chưa biết có yêu cầu xóa.

**Sai 11 — Retry không giới hạn.** Hệ thống có thể tạo bão retry/DLQ; cần policy, timeout, backoff và phân loại lỗi.

**Sai 12 — Không thử restore/replay.** Snapshot cũ hoặc event history có thể hồi sinh dữ liệu từng bị xóa.

**Sai 13 — Dùng hash đơn giản để gọi dữ liệu "anonymous".** Hash có thể liên kết hoặc đoán lại; cần đánh giá tính nhận diện thực tế.

**Sai 14 — Xóa hàng triệu record trong một transaction.** Gây lock kéo dài, áp lực storage và replication; nên batch với checkpoint.

**Sai 15 — Giữ audit log chứa toàn bộ giá trị từng xóa.** Bằng chứng kiểm toán nên mô tả operation và outcome tối thiểu, không tái lưu nội dung nhạy cảm.

**Sai 16 — Áp retention mặc định không được phê duyệt.** Thời hạn và ngoại lệ phụ thuộc policy, hợp đồng, luật áp dụng; framework không thể chọn thay tổ chức.

## 15. Checklist thiết kế và triển khai

- [ ] Liệt kê data classes, mục đích xử lý, data owners, hệ thống đích và retention period được phê duyệt.
- [ ] Định nghĩa thời điểm bắt đầu tính hạn, `expiresAt`, múi giờ và policy version.
- [ ] Định nghĩa cơ chế legal hold/review/approval và ngoại lệ theo căn cứ hợp lệ.
- [ ] Giảm PII trong event, logs, traces, metrics, DLQ ngay từ thiết kế.
- [ ] Thiết kế xóa có điều kiện ngay tại statement; ghi nhận số hàng thực sự xóa.
- [ ] Tổ chức cleanup batch ngắn, idempotent, chịu lỗi và an toàn multi-instance.
- [ ] Không nhầm `@Scheduled` với distributed scheduler hoặc job có bảo đảm hoàn tất.
- [ ] Phân biệt `ErasureRequested`, `PrimaryRecordErased` và `ErasureCompleted`.
- [ ] Dùng `AFTER_COMMIT` khi cần thời điểm sau commit, dùng outbox khi cần durable propagation.
- [ ] Theo dõi acknowledgements và retry cho tất cả consumer sở hữu bản sao bắt buộc.
- [ ] Cấu hình retention/tombstone của broker, DLQ, outbox và consumer storage.
- [ ] Xác định xóa/anonymize materialized views, object versions và logs.
- [ ] Có restore/replay suppression để không hồi sinh dữ liệu đã xóa.
- [ ] Có lịch xóa backup hợp lệ và quy trình kiểm soát backup/restore.
- [ ] Lưu bằng chứng tối thiểu, phân quyền truy cập, không lưu lại secret/PII trong audit.
- [ ] Kiểm thử expiry, hold, rollback, retry, crash, duplicate, replay và SLA xóa.
- [ ] Quan sát backlog, oldest-pending-age, deletion failures và completion per target.
- [ ] Review khi thêm consumer hoặc field vào event schema: mọi bản sao mới phải có lifecycle.

## 16. Câu hỏi tự kiểm tra

1. **Tại sao xóa một row DB chưa đủ?** — Vì Spring event có thể làm phát sinh bản sao ở cache, broker, index, logs, consumer DB và backups.
2. **Retention và request xóa khác gì?** — Retention là lịch/chính sách vòng đời; request xóa là yêu cầu cần xác minh căn cứ và điều kiện.
3. **Soft delete có đồng nghĩa xóa PII không?** — Không; dữ liệu có thể vẫn còn nguyên trong storage.
4. **`@Scheduled` có tự bảo đảm chỉ chạy một instance không?** — Không; cần điều phối trong môi trường cluster.
5. **Tại sao cần kiểm tra lại expiry và hold tại DELETE?** — Tránh xóa khi điều kiện đã thay đổi kể từ lúc chọn ứng viên.
6. **Một event được publish trong transaction có nghĩa DB đã commit chưa?** — Chưa.
7. **`@TransactionalEventListener(AFTER_COMMIT)` có đảm bảo không mất event khi crash không?** — Không; dùng outbox nếu cần durability.
8. **Vì sao không gửi email trong erasure event?** — Nó tạo thêm bản sao của chính dữ liệu cần xóa.
9. **Kafka tombstone có xóa ngay tất cả PII không?** — Không; compaction không tức thời và không bao phủ các bản sao khác.
10. **Làm sao ngăn replay khôi phục dữ liệu đã xóa?** — Có cơ chế erasure ledger, filter/version/restore controls và kiểm thử replay.
11. **Xóa lại cùng ID có nhất thiết là lỗi?** — Không; erasure handler nên idempotent khi thiết kế cho retry.
12. **Dữ liệu đang có legal hold có thể xóa theo scheduler không?** — Không tự động bỏ qua hold hợp lệ; cần xét chính sách và phê duyệt.
13. **Làm thế nào chứng minh tất cả target đã xử lý?** — Theo dõi acknowledgement/verification theo từng hệ thống, không chỉ log "published".
14. **Tại sao retention period không thể lấy mặc định từ Spring?** — Thời hạn phụ thuộc loại dữ liệu, mục đích, luật/hợp đồng/chính sách được phê duyệt.

## Tài liệu tham khảo

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Data JPA — JpaRepository bulk delete API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html)
- [Apache Kafka — Topic configs: cleanup.policy, retention, compaction, tombstones](https://kafka.apache.org/documentation/#topicconfigs)
- [GDPR — Regulation (EU) 2016/679, Article 5 and Article 17](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32016R0679)
- [European Data Protection Board — Erasure FAQ](https://www.edpb.europa.eu/sme/find-practical-info/faq_en)

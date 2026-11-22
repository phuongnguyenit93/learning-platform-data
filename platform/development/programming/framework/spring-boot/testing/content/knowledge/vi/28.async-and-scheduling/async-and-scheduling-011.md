# Kiểm thử chạy lại, xử lý trùng và lỗi giữa chừng

## 1. Bài toán: một lần chạy thành công không chứng minh hệ thống phục hồi đúng

Trong ứng dụng Spring Boot, tác vụ bất đồng bộ và công việc định kỳ có thể chạy nhiều lần vì lịch `@Scheduled`, retry sau timeout, người vận hành bấm “Run now”, consumer nhận lại message, một instance bị restart hoặc hai replicas cùng khởi động job. Một job xử lý 100 đơn hàng có thể hoàn thành 40 đơn rồi gặp exception ở đơn 41. Lần sau, hệ thống phải tiếp tục đúng cách: không tạo lại side effect của 40 đơn đã xong, không bỏ quên đơn lỗi, không xử lý trùng khi hai worker cùng nhìn thấy một đơn.

Ví dụ **không đủ**:

~~~java
@Test
void batchRuns() {
    runner.runOnce();
    assertThat(receipts.count()).isEqualTo(3);
}
~~~

Test trên chỉ quan sát một lần chạy. Nó không chứng minh kết quả của lần chạy **thứ hai**, không kiểm hai lời gọi cùng lúc, không thử lỗi giữa các items, và không phân biệt lỗi trước hay sau transaction commit. Một lỗi tưởng nhỏ có thể tạo hai hóa đơn, hai lần gửi email hoặc hai lần thu phí.

Bài học này hướng dẫn cách thiết kế và kiểm thử ba thuộc tính chính:

- **Rerun/resume**: chạy lại sau thành công hoặc thất bại mà không làm mất công việc, không nhân đôi kết quả đã được xác nhận.
- **Duplicate handling / idempotency**: cùng một business operation ID được gửi/nhận nhiều lần hoặc chạy đồng thời nhưng side effect tuân thủ contract đã định.
- **Partial failure / recovery**: lỗi ở những thời điểm cụ thể (trước ghi, sau flush, trước commit, giữa batch, sau commit trước publish/ack) được kiểm một cách chủ động và có phương án khôi phục.

Trọng tâm nằm ở **Bất đồng bộ và lịch chạy** trong Spring Boot, nên ví dụ dùng `@Scheduled`, transaction boundaries, Spring Data JPA, failure injection, concurrency test, retry policy, durable outbox và consumer idempotency. Bài có **dự án Maven Java 17 / Spring Boot 3.5.16 / H2 / JUnit 5 / Mockito** với code đầy đủ và các test xác minh state trong database. Các tình huống crash process và external side effect được tách thành hướng dẫn integration nâng cao vì không thể đồng nhất exception trong một test JVM với một crash thật.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **at-most-once**, **at-least-once**, **idempotent effect**, và tuyên bố “exactly once” trong phạm vi xác định.
2. Lập ma trận lỗi trước/sau flush, trước/sau commit, giữa items và trước/sau acknowledgment.
3. Thiết kế job có **idempotency key** ổn định và business status rõ.
4. Dùng **transaction riêng cho từng item** để lần chạy sau tiếp tục được sau một lỗi ở giữa batch.
5. Dùng `@Lock(PESSIMISTIC_WRITE)` và database unique key để chống hai lượt xử lý đồng thời của cùng item.
6. Kiểm `@Scheduled` bằng **manual trigger**, không phải chờ timer chạy vài giây thật.
7. Dùng `@MockitoBean` cho fault-injection hook, không mock chính repository/transaction khi mục tiêu là kiểm commit/rollback.
8. Kiểm trạng thái dữ liệu **ngoài test-managed transaction**, tránh false positive do rollback mặc định.
9. Biết khi nào lỗi external side effect đòi hỏi **transactional outbox, idempotent consumer, retry/backoff và reconciliation**.
10. Xác định giới hạn của H2 và lập test production-like bằng PostgreSQL/Testcontainers khi cần kiểm locks/isolation.

**Nguyên tắc nền tảng:** Một job có thể được gọi nhiều lần; chỉ side effect kinh doanh cần đáp ứng contract không bị nhân đôi, và công việc dở dang phải được phát hiện/khôi phục.

## 2. Các định nghĩa không thể bỏ qua

### 2.1. “Chạy lại” có nhiều hình thức

- **Rerun sau thành công**: item đã DONE phải được bỏ qua.
- **Retry sau exception trước commit**: transaction rollback, item còn eligible; lần sau được xử lý lại.
- **Restart sau crash giữa batch**: một số items đã commit, số còn lại chưa; run mới phải resume từ dữ liệu bền vững.
- **Duplicate trigger**: scheduler/manual/API/queue cùng gọi xử lý một business ID.
- **Concurrent duplicate**: hai instances xử lý cùng ID tại cùng thời điểm.
- **Replay**: consumer đọc lại event do offset/ack state hoặc operator reset.
- **Reconciliation**: quét lại để phát hiện work chưa DONE hoặc side effect chưa xác nhận.

Mỗi loại tạo failure mode khác nhau. Test happy path đơn thuần không bao quát được.

### 2.2. At-most-once và at-least-once

| Delivery/processing model | Điều tốt | Rủi ro |
| --- | --- | --- |
| At-most-once | Cố tránh làm lại | Lỗi có thể làm mất một operation |
| At-least-once | Tiếp tục/retry cho tới khi xử lý | Cùng operation có thể chạy nhiều lần |
| Idempotent effect | Nhiều attempts cho cùng operation nhưng kết quả business không nhân đôi | Cần key, transactional boundary và test đúng |
| Exactly-once trong phạm vi một DB transaction | Atomic commit/unique constraint có thể tạo một hiệu ứng dữ liệu | Không tự mở rộng sang email/broker/payment |
| Distributed exactly-once end-to-end | Đòi guarantee đặc biệt xuyên systems và failure boundaries | Không được suy từ một annotation hoặc một mock test |

Để có **at-least-once + idempotency**, cần cho phép retry nhưng tránh business side effect lặp. Đó thường là thiết kế thực dụng cho job và message handlers.

### 2.3. Idempotent nghĩa là gì?

Với một operation `process(orderId=42)`, gọi một, hai hoặc mười lần không tạo thêm kết quả kinh doanh ngoài hiệu quả của lần hợp lệ đầu tiên. Idempotent **không nhất thiết** có nghĩa method chỉ chạy một lần hoặc logs chỉ ghi một dòng. Job có thể thử lại nhiều lần, trong khi chỉ có một receipt/order state cuối cùng.

Ví dụ:

~~~text
process("invoice-42") lần 1 -> receipt invoice-42 xuất hiện
process("invoice-42") lần 2 -> bỏ qua; receipt vẫn chỉ có một
process("invoice-42") đồng thời từ 2 threads -> chỉ một transaction được thực thi tới completion
~~~

Khi operation có payload khác cho cùng ID (ví dụ order-42 nhưng amount thay đổi), **không nên âm thầm xem đó là duplicate hợp lệ**. Identity/payload consistency phải là một policy riêng: reject conflict hoặc version operation.

### 2.4. Rerun-safe không đồng nghĩa retry-safe cho side effect ngoài DB

~~~text
DB update + unique receipt nằm trong cùng transaction
    => Có thể atomic trong database

DB commit
  -> gửi email / gọi payment API / publish Kafka
    => Không còn cùng một atomic database transaction
~~~

Nếu process crash sau khi gửi email nhưng trước khi lưu “đã gửi”, lần retry có thể gửi **lại**. Nếu crash sau DB commit nhưng trước khi gửi email, không thể dựa vào callback in-memory để bảo đảm email sẽ được gửi. Phần 13 trình bày outbox và idempotency cho trường hợp đó.

## 3. Ma trận failure points: cần inject lỗi ở đâu?

Giả sử một worker xử lý `item-42` theo trình tự:

~~~text
T0: trigger nhận itemId
T1: đọc row, khóa item theo business ID
T2: kiểm đã DONE?
T3: insert receipt / update trạng thái item
T4: flush SQL tới DB
T5: COMMIT transaction
T6: emit external event hoặc đánh thức outbox relay
T7: bên ngoài ACK / consumer commit offset
~~~

| Fault injection | Trạng thái cần quan sát | Khi rerun |
| --- | --- | --- |
| Trước T1 | Chưa thay đổi dữ liệu | Item vẫn eligible |
| Sau T1, trước write | Lock được giải phóng khi rollback | Lần khác có thể xử lý |
| Sau T3/T4, trước T5 | SQL đã flush nhưng transaction rollback | Receipt không còn; item chưa DONE |
| Sau T5, trước T6 | DB đã commit; external event có thể bị mất | Outbox/reconciliation phải tìm lại |
| Sau T6, trước T7 | Event có thể đã được nhận nhưng caller chưa biết | Retry có thể tạo duplicate; consumer idempotent |
| Giữa item A và item B | A đã commit, B chưa | Chạy lại chỉ xử lý B trở đi |
| Hai workers xử lý cùng ID | Một worker phải wait/skip hoặc conflict có kiểm soát | Không có hai business receipts |
| Side effect fail có tính vĩnh viễn | Item RETRY_WAIT/FAILED/DLQ với thông tin lỗi | Không retry vô hạn |

**Điểm quan trọng:** `saveAndFlush()` không phải `commit`. Một test assert entity có mặt **trong cùng transaction** sau flush chưa chứng minh data durable khi worker crash hoặc rollback.

### 3.1. Inject lỗi có chủ đích

Một `FailureGate` chỉ dùng cho test có thể ném `RuntimeException` sau khi đã flush dữ liệu nhưng trước khi transaction commit. Nếu lỗi truyền ra qua transactional proxy, Spring mặc định rollback transaction cho unchecked exception. Điều này cho phép test chứng minh atomicity trong database.

Không gọi một RuntimeException là “mô phỏng chính xác JVM kill”: một crash process cắt hẳn runtime, kết nối/transaction cleanup do DB thực hiện và side effects có thể đã xảy ra. Crash-recovery test thật cần process/container boundary.

### 3.2. Mục tiêu của một matrix test

Một bài test tốt nên:
1. Tạo **item riêng** với identity rõ.
2. Trigger tại boundary được chọn.
3. Inject failure xác định, không phụ thuộc timing.
4. Read lại database **sau khi transaction kết thúc**.
5. Trigger rerun.
6. Assert trạng thái cuối, số receipt, số attempts quan sát được.
7. Cleanup và xác nhận test không để data ảnh hưởng case khác.

Đừng chỉ verify `mockGateway.send()` một lần rồi kết luận persisted state đúng.

## 4. Hai tầng checkpoint: transaction per item và durable state

### 4.1. Một transaction cho toàn batch

Nếu bọc cả batch 1.000 items trong **một transaction**, exception ở item cuối có thể rollback toàn bộ tiến độ database. Ưu điểm là all-or-nothing, nhưng:
- Transaction dài dễ giữ locks và connection lâu.
- Retry lại từ đầu tốn chi phí.
- Side effects ngoài DB đã thực hiện không tự rollback.
- Một poison item có thể chặn cả batch.

Dùng khi business contract thật sự đòi atomic toàn batch và độ lớn cho phép.

### 4.2. Transaction riêng cho từng item

Một lựa chọn khác:

~~~text
BatchRunner.runOnce()                  không có outer transaction
  |
  +-- ItemProcessor.process("a")       Transaction T1 -> COMMIT
  +-- ItemProcessor.process("b")       Transaction T2 -> FAIL/ROLLBACK
  X-- ItemProcessor.process("c")       chưa chạy
                                        |
Rerun                                   v
  +-- "a": DONE -> không quét lại
  +-- "b": PENDING -> T3 -> COMMIT
  +-- "c": PENDING -> T4 -> COMMIT
~~~

Điểm thiết yếu: Runner **không** đánh dấu `@Transactional` ở mức toàn batch, và nó gọi `ItemProcessor` là **Spring bean khác**. Như vậy `@Transactional` của public method `process` được gọi qua proxy, tạo một transaction riêng mỗi item.

### 4.3. Cẩn thận với self-invocation

Sai:

~~~java
@Service
class BadJob {
    public void runAll() {
        this.processOne("a");
        this.processOne("b");
    }

    @Transactional
    public void processOne(String id) {
        // ...
    }
}
~~~

Với Spring proxy-based transaction AOP, `this.processOne()` không đi qua proxy nên annotation có thể không tạo transaction mới. Đặt processor thành bean riêng, hoặc dùng `TransactionTemplate` nếu muốn điều khiển transaction bằng code tường minh.

### 4.4. DONE và receipt phải được ghi atomically

Nếu `WorkItem.status=DONE` nhưng `CompletionReceipt` chưa có, lần retry có thể skip mà business output bị mất. Nếu receipt đã có nhưng status vẫn PENDING, lần retry dễ gây unique conflict hoặc duplicate side effect.

Khi cả hai là database state, ghi **trong cùng transaction** để hoặc cùng commit, hoặc cùng rollback. Database primary key/unique constraint giúp bảo vệ một receipt theo một business ID.

### 4.5. Transaction duration và batch size

Không quét hàng triệu rows vào một Java list rồi giữ hết trong memory. Production dùng pagination/chunk claim và bounded work duration. Nếu có nhiều workers, không nên để mọi worker query cùng pending list quá lớn rồi chờ khóa; dùng atomic claim/lease hoặc `SKIP LOCKED` khi DB/ORM hỗ trợ và kiến trúc được kiểm thử.

Lab cố ý xử lý ít records để chứng minh semantics. Nó không phải job scheduler phân tán có leasing, heartbeat và long-running external tasks.

## 5. Xử lý trùng dưới concurrency

### 5.1. Check-then-act không atomic

Sai:

~~~java
if (!receiptRepository.existsById(id)) {
    receiptRepository.save(new Receipt(id));
}
~~~

Hai threads có thể đồng thời thấy `exists=false` rồi cùng save. Nếu database có unique key, một transaction thất bại; nếu không có, hai receipts có thể được tạo.

Đối với duplicate-safe processing, cần **atomic constraint/lock/claim**, và test concurrent requests. Một `synchronized` trong JVM không bảo vệ khi có nhiều Spring Boot instances trên nhiều máy.

### 5.2. Pessimistic row lock

Trong lab dùng Spring Data JPA:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select w from WorkItem w where w.id = :id")
Optional<WorkItem> findLockedById(
        @Param("id") String id);
~~~

Method này được gọi **bên trong** một transaction. Nó yêu cầu khóa ghi cho row trước khi kiểm status và tạo receipt, nên concurrent attempts cùng ID được serialize theo database locking semantics. Worker sau có thể phải chờ transaction trước commit, rồi đọc trạng thái DONE và skip.

**Giới hạn:** Pessimistic locking phụ thuộc DB isolation, lock timeout và concurrency behavior. H2 giúp kiểm một đường đi đơn giản; cần PostgreSQL/Testcontainers cho production-like lock, deadlock và failover tests.

### 5.3. Primary key/unique constraint là hàng rào cuối

`CompletionReceipt.workId` dùng primary key bằng đúng business ID. Nếu logic quên khóa hoặc tạo duplicate, database không cho lưu hai receipts cùng ID. Đừng chỉ dựa vào unique constraint để *ẩn* race: test cần xác định caller nhận result gì khi conflict và có retry/resolution policy rõ.

### 5.4. Row lock chưa giải quyết mọi external duplicate

Giữ DB lock rồi gọi payment gateway **bên trong transaction** không tạo atomic commit xuyên payment provider. Nếu gateway đã charge nhưng DB rollback, lần sau sẽ charge lại. Dùng provider idempotency key, outbox/saga và reconciliation; không giữ một DB transaction mở trong lúc chờ network dài nếu có thể tránh.

### 5.5. Duplicate payload phải được định nghĩa

Hai messages cùng eventId có thể mang:
- Payload byte-for-byte giống nhau → có thể coi là replay.
- Payload thay đổi vì event version mới → cần versioning rule.
- Payload khác với cùng idempotency key → thường phải reject conflict và log cảnh báo.

Lưu payload hash/operation parameters cùng idempotency key khi nghiệp vụ nhạy cảm (payment, financial transfer). Chỉ kiểm `existsById` rồi skip tất cả có thể giấu request sửa dữ liệu bất hợp lệ.

## 6. @Scheduled, @Async và việc chủ động kiểm thử

### 6.1. @Scheduled không bảo đảm single execution toàn cluster

~~~java
@Scheduled(fixedDelayString =
        "${lab.job.delay-ms:60000}")
public void tick() {
    runner.runOnce();
}
~~~

Spring scheduling gọi method theo lịch trong **mỗi Spring application instance có scheduling enabled**. Nếu chạy 3 replicas, có thể có 3 triggers tương tự. `fixedDelay` tính từ lúc kết thúc invocation trước đến lúc bắt đầu invocation sau trong một schedule; nó **không phải distributed lock**.

Một phương pháp bền vững là:
- Dùng unique key và DB lock/claim để bảo vệ item.
- Hoặc dùng scheduler leader election/distributed lock/fencing theo kiến trúc.
- Viết test concurrent processing dù production hiện tại chỉ có một instance.

### 6.2. Manual trigger thay cho sleep

Nếu test muốn kiểm business job, tốt nhất:
- Tách `ScheduledTrigger` chỉ làm adapter.
- Runner có public method `runOnce()` có thể gọi trực tiếp.
- Bật `@EnableScheduling` bằng profile ngoài tests.
- Gọi `runner.runOnce()`/`trigger.tick()` chủ động trong JUnit.

Không làm:

~~~java
Thread.sleep(65000);
assertThat(...).isEqualTo(...);
~~~

Chờ lịch chạy thật gây test chậm và dễ race. Nếu yêu cầu kiểm cron parsing/next execution time, dùng test riêng cho `CronExpression`/`Trigger` với thời gian giả định rõ, không ngủ tới phút kế tiếp.

### 6.3. @Async

Nếu job dispatch task sang `@Async`/executor:
- Scheduler thread chỉ enqueue; return không có nghĩa task hoàn tất.
- Cần `CompletableFuture`, `CountDownLatch` hoặc Awaitility bounded để đợi side effects.
- Exceptions trong void async methods có thể không truyền về scheduler caller.
- Transaction ThreadLocal của caller không tự chuyển sang worker thread.
- Phải kiểm failure/cancellation/timeouts và executor rejection.

Lab chính dùng synchronous `runOnce()` để test transaction và restart semantics deterministic; scheduler vẫn có thể trigger nó theo lịch. Các asynchronous variants được hướng dẫn ở phần mở rộng.

### 6.4. Cron, timezone, DST và duplicate fire

Với `@Scheduled(cron="...")`:
- Chọn `zone` tường minh khi business schedule theo khu vực.
- Kiểm kỳ vọng vào ngày daylight saving transition nếu timezone có DST.
- Không suy “mỗi ngày đúng một lần” chỉ từ cron expression; restart, multiple nodes hoặc manual rerun tạo duplicates.
- Dùng job execution key như `businessDate + jobType` để idempotent.
- Với backfill, định nghĩa cửa sổ thời gian và cutoff rõ thay vì phụ thuộc `LocalDateTime.now()`.

## 7. Dự án Spring Boot runnable: một job có thể chạy lại an toàn

### 7.1. Business scenario

Ứng dụng xử lý `WorkItem` có `id`, `payload`, `status`. Khi xử lý thành công:
1. Đọc và khóa row bằng `PESSIMISTIC_WRITE`.
2. Nếu status đã `DONE`, **trở về mà không tạo receipt mới**.
3. Insert `CompletionReceipt` có primary key bằng `workId`.
4. Cập nhật `WorkItem.status=DONE`.
5. Flush database writes.
6. Cho phép test inject RuntimeException ngay trước commit.
7. Transaction commit nếu không có lỗi.

Một `BatchRunner` duyệt các items `PENDING`, gọi `ItemProcessor.process(id)` qua Spring proxy. Nếu lỗi ở item B, runner dừng; item A đã commit, item C chưa chạy. Lần sau query lại `PENDING` nên tự tiếp tục.

Không có network/email thật. Receipt tượng trưng **business side effect nằm trong cùng database**. Phần 13 chỉ ra cách chuyển sang outbox khi side effect ngoài DB.

### 7.2. Cây thư mục

~~~text
job-rerun-recovery-lab/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/jobrecovery/
│   ├── JobRecoveryApplication.java
│   ├── SchedulerConfiguration.java
│   ├── WorkStatus.java
│   ├── WorkItem.java
│   ├── CompletionReceipt.java
│   ├── WorkItemRepository.java
│   ├── CompletionReceiptRepository.java
│   ├── FailureGate.java
│   ├── NoopFailureGate.java
│   ├── ItemProcessor.java
│   ├── BatchRunner.java
│   └── ScheduledTrigger.java
└── src/test/java/com/example/jobrecovery/
    └── JobRecoveryIntegrationTest.java
~~~

Mọi Java class ở package `com.example.jobrecovery`, kiểm thử ở cùng package để dùng được public API. Lab gồm JPA entities/repositories, một transactional item processor, một runner không có outer transaction, một test-only replaceable failure gate, và JUnit integration tests. **Không** tự tạo production migration/schema bằng tay: H2 và Hibernate `create-drop` chỉ dùng cho lab/test.

### 7.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>job-rerun-recovery-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Spring Boot 3.5 parent/BOM quản lý Spring Framework 6.2, Spring Data JPA/Hibernate, HikariCP, Mockito, AssertJ và JUnit Jupiter. Java 17 có `Stream.toList()` và records nếu cần.

### 7.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=job-rerun-recovery-lab

# Lab/Test only: H2 database persists while the JVM context is alive.
spring.datasource.url=jdbc:h2:mem:job_recovery;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=10000
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false

# fixedDelay chỉ được kích hoạt khi profile scheduler bật.
lab.job.delay-ms=60000
~~~

`LOCK_TIMEOUT=10000` giúp ví dụ concurrent test có budget cho một transaction đang giữ row lock. Trong production, chọn lock timeout từ SLA và DB config; không copy H2 URL hoặc `ddl-auto=create-drop` sang production.

### 7.5. JobRecoveryApplication.java

~~~java
package com.example.jobrecovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JobRecoveryApplication {

    public static void main(String[] args) {
        SpringApplication.run(JobRecoveryApplication.class, args);
    }
}
~~~

Để tách scheduler khỏi integration tests, main class **không** có `@EnableScheduling`.

### 7.6. SchedulerConfiguration.java

~~~java
package com.example.jobrecovery;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration(proxyBeanMethods = false)
@Profile("scheduler")
@EnableScheduling
public class SchedulerConfiguration {
}
~~~

Khi profile `scheduler` active, Spring phát hiện `@Scheduled` và đăng ký trigger. Trong JUnit ta dùng profile `test` nên chỉ gọi job thủ công, không có timer chạy nền gây race với test setup/cleanup. Profile này là lựa chọn **thiết kế lab**, không phải property tắt scheduler mặc định chung cho mọi ứng dụng Spring Boot.

### 7.7. WorkStatus.java

~~~java
package com.example.jobrecovery;

public enum WorkStatus {
    PENDING,
    DONE
}
~~~

Lab giữ status nhỏ để tập trung rollback/resume. Phần production mở rộng thành `PENDING/PROCESSING/RETRY_WAIT/DONE/FAILED` và lease/nextAttemptAt khi cần work queue dài hạn.

### 7.8. WorkItem.java

~~~java
package com.example.jobrecovery;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "work_items")
public class WorkItem {

    @Id
    @Column(name = "work_id", length = 80)
    private String id;

    @Column(nullable = false, length = 150)
    private String payload;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private WorkStatus status;

    protected WorkItem() {
        // Required by JPA.
    }

    public WorkItem(String id, String payload) {
        this.id = id;
        this.payload = payload;
        this.status = WorkStatus.PENDING;
    }

    public String getId() {
        return id;
    }

    public String getPayload() {
        return payload;
    }

    public WorkStatus getStatus() {
        return status;
    }

    public void markDone() {
        this.status = WorkStatus.DONE;
    }
}
~~~

Primary key `id` là **stable business operation ID** của công việc. Không dùng random ID mới cho mỗi retry nếu muốn deduplicate cùng operation. Dữ liệu fixture trong test dùng synthetic payload.

### 7.9. CompletionReceipt.java

~~~java
package com.example.jobrecovery;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "completion_receipts")
public class CompletionReceipt {

    @Id
    @Column(name = "work_id", length = 80)
    private String workId;

    @Column(nullable = false, length = 150)
    private String payload;

    protected CompletionReceipt() {
        // Required by JPA.
    }

    public CompletionReceipt(
            String workId, String payload) {
        this.workId = workId;
        this.payload = payload;
    }

    public String getWorkId() {
        return workId;
    }

    public String getPayload() {
        return payload;
    }
}
~~~

`workId` là primary key, nên database không thể giữ hai receipt rows cùng ID. Nó biểu diễn **kết quả nghiệp vụ trong cùng database**, không phải email đã được người nhận mở hoặc payment đã được provider xác nhận.

### 7.10. WorkItemRepository.java

~~~java
package com.example.jobrecovery;

import java.util.List;
import java.util.Optional;

import jakarta.persistence.LockModeType;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface WorkItemRepository
        extends JpaRepository<WorkItem, String> {

    List<WorkItem> findByStatusOrderByIdAsc(
            WorkStatus status);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select w from WorkItem w where w.id = :id")
    Optional<WorkItem> findLockedById(
            @Param("id") String id);
}
~~~

`findByStatusOrderByIdAsc(PENDING)` trả một snapshot các candidates tại thời điểm query. Nó có thể chứa cùng ID mà instance khác đang xử lý; điều này **được chấp nhận** vì quyết định thực sự nằm trong transactional `findLockedById` và kiểm status **sau khi lock**.

Không chỉ query pending một lần rồi tin rằng mọi row vẫn pending khi tới lượt xử lý.

### 7.11. CompletionReceiptRepository.java

~~~java
package com.example.jobrecovery;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CompletionReceiptRepository
        extends JpaRepository<CompletionReceipt, String> {
}
~~~

Repo này hỗ trợ test readback và production-side persistence. Không mock repository trong integration tests của bài vì cần kiểm real transaction, lock và unique constraint.

### 7.12. FailureGate.java

~~~java
package com.example.jobrecovery;

public interface FailureGate {

    void afterDatabaseWrites(String workId);
}
~~~

Hook này **không phải logic business**; nó là một seam để inject exception ngay sau khi SQL đã flush nhưng trước khi `@Transactional` commit. Trong production implementation dưới đây là no-op. Các tests dùng `@MockitoBean` thay bean theo type và thiết lập fault tại item cụ thể.

### 7.13. NoopFailureGate.java

~~~java
package com.example.jobrecovery;

import org.springframework.stereotype.Component;

@Component
public class NoopFailureGate implements FailureGate {

    @Override
    public void afterDatabaseWrites(String workId) {
        // No-op trong môi trường chạy thường.
    }
}
~~~

Không dựa vào một external system thật để tạo lỗi timing bất định. Với advanced integration test, hook có thể được thay bằng failpoint/instrumentation tại producer, database, ack hoặc process boundary.

### 7.14. ItemProcessor.java

~~~java
package com.example.jobrecovery;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ItemProcessor {

    private final WorkItemRepository items;
    private final CompletionReceiptRepository receipts;
    private final FailureGate failureGate;

    public ItemProcessor(
            WorkItemRepository items,
            CompletionReceiptRepository receipts,
            FailureGate failureGate) {
        this.items = items;
        this.receipts = receipts;
        this.failureGate = failureGate;
    }

    @Transactional
    public void process(String workId) {
        WorkItem item = items.findLockedById(workId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unknown work item: " + workId));

        if (item.getStatus() == WorkStatus.DONE) {
            // Operation đã hoàn tất; không tạo receipt mới.
            return;
        }

        // WorkItem row đã bị khóa cho tới khi transaction end.
        receipts.saveAndFlush(new CompletionReceipt(
                item.getId(), item.getPayload()));

        item.markDone();

        // Flush UPDATE status trước failpoint.
        items.flush();

        // Test có thể ném RuntimeException tại đây.
        // Cả receipt INSERT và WorkItem UPDATE rollback.
        failureGate.afterDatabaseWrites(workId);
    }
}
~~~

### 7.15. Đọc kỹ transaction boundary

- `@Transactional` được áp dụng khi `process` đi qua Spring proxy, tạo một transaction theo mỗi lời gọi.
- `findLockedById` phát query có `PESSIMISTIC_WRITE`; lock giữ cho tới commit/rollback.
- `saveAndFlush` đẩy INSERT receipt tới database nhưng **không commit**.
- `item.markDone()` được dirty checking; `items.flush()` gửi UPDATE.
- `FailureGate` có thể throw RuntimeException; Spring transaction interceptor rollback toàn bộ các writes trước đó.
- Nếu method return bình thường, transaction commit; lần gọi sau khóa row và thấy DONE, return mà không insert receipt.
- Với concurrent calls cùng workId, row lock serialize đường check-and-write, primary key receipt phòng ngừa lỗi duplicate còn sót.

Không có external side effect nào trong method. Đây là lựa chọn **có chủ đích** để chứng minh đúng semantics atomic database. Nếu thêm `emailGateway.send` ở cuối method và giữ nguyên lời khẳng định “rollback sẽ xóa email”, đó là lỗi kiến trúc.

### 7.16. BatchRunner.java

~~~java
package com.example.jobrecovery;

import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class BatchRunner {

    private final WorkItemRepository items;
    private final ItemProcessor processor;

    public BatchRunner(
            WorkItemRepository items,
            ItemProcessor processor) {
        this.items = items;
        this.processor = processor;
    }

    // Cố ý KHÔNG @Transactional trên toàn batch.
    public void runOnce() {
        List<String> ids = items
                .findByStatusOrderByIdAsc(WorkStatus.PENDING)
                .stream()
                .map(WorkItem::getId)
                .toList();

        for (String id : ids) {
            processor.process(id);
        }
    }
}
~~~

Nếu `process("b")` throw exception, loop dừng, nhưng `process("a")` đã return sau commit của transaction riêng. Lần `runOnce()` kế tiếp query **PENDING mới**, bỏ qua A. Đây là một recovery contract hợp lệ cho job sequential và nhỏ.

Với production batch lớn, thay `findByStatus...` đọc toàn bộ bằng pages/claim batching. Nếu job phải tiếp tục các items khác sau lỗi B thay vì dừng, có thể catch exception **ngoài item transaction**, log/retry state và tiếp tục theo policy; test phải mô tả rõ expected chứ không nuốt lỗi âm thầm.

### 7.17. ScheduledTrigger.java

~~~java
package com.example.jobrecovery;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ScheduledTrigger {

    private final BatchRunner runner;

    public ScheduledTrigger(BatchRunner runner) {
        this.runner = runner;
    }

    @Scheduled(fixedDelayString =
            "${lab.job.delay-ms:60000}")
    public void tick() {
        runner.runOnce();
    }
}
~~~

Trigger cực mỏng, chỉ ủy nhiệm. Dùng `@EnableScheduling` qua profile `scheduler` để bắt đầu lịch chạy thật. Với profile `test`, adapter vẫn có bean để JUnit gọi `tick()` trực tiếp mà không bị thời gian thật hoặc scheduler tự động tranh dữ liệu.

### 7.18. JobRecoveryIntegrationTest.java

`src/test/java/com/example/jobrecovery/JobRecoveryIntegrationTest.java`:

~~~java
package com.example.jobrecovery;

import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

@SpringBootTest
@ActiveProfiles("test")
class JobRecoveryIntegrationTest {

    @Autowired
    WorkItemRepository items;

    @Autowired
    CompletionReceiptRepository receipts;

    @Autowired
    BatchRunner runner;

    @Autowired
    ItemProcessor processor;

    @Autowired
    ScheduledTrigger trigger;

    @MockitoBean
    FailureGate failureGate;

    @BeforeEach
    void cleanBeforeEachTest() {
        // Không có outer test-managed @Transactional:
        // cleanup qua repository transactions thật.
        receipts.deleteAll();
        items.deleteAll();
        reset(failureGate);
    }

    @Test
    void runningSameBatchAgainDoesNotDuplicateReceipts() {
        items.save(new WorkItem("a", "payload-a"));

        runner.runOnce();
        runner.runOnce();

        assertThat(items.findById("a").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);
        assertThat(receipts.findById("a")).isPresent();
        assertThat(receipts.count()).isEqualTo(1);

        verify(failureGate, times(1))
                .afterDatabaseWrites("a");
    }

    @Test
    void directDuplicateInvocationSkipsAlreadyDoneItem() {
        items.save(new WorkItem("same", "payload"));

        processor.process("same");
        processor.process("same");

        assertThat(receipts.count()).isEqualTo(1);
        assertThat(receipts.findById("same")
                .orElseThrow().getPayload())
                .isEqualTo("payload");

        verify(failureGate, times(1))
                .afterDatabaseWrites("same");
    }

    @Test
    void exceptionAfterFlushRollsBackBothWritesThenRetrySucceeds() {
        items.save(new WorkItem("retry", "payload-r"));

        doThrow(new IllegalStateException(
                "injected after database flush"))
                .doNothing()
                .when(failureGate)
                .afterDatabaseWrites("retry");

        assertThatThrownBy(runner::runOnce)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("injected");

        // Đọc SAU transaction exception/rollback.
        assertThat(items.findById("retry").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.PENDING);
        assertThat(receipts.findById("retry")).isEmpty();

        runner.runOnce();

        assertThat(items.findById("retry").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);
        assertThat(receipts.findById("retry")).isPresent();
        assertThat(receipts.count()).isEqualTo(1);

        verify(failureGate, times(2))
                .afterDatabaseWrites("retry");
    }

    @Test
    void failureInMiddleKeepsEarlierCommitAndResumesRemaining() {
        items.saveAll(List.of(
                new WorkItem("a", "payload-a"),
                new WorkItem("b", "payload-b"),
                new WorkItem("c", "payload-c")));

        doThrow(new IllegalStateException(
                "injected failure on b"))
                .doNothing()
                .when(failureGate)
                .afterDatabaseWrites("b");

        assertThatThrownBy(runner::runOnce)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("on b");

        // a hoàn tất trong transaction riêng.
        assertThat(items.findById("a").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);
        assertThat(receipts.findById("a")).isPresent();

        // b rollback toàn transaction.
        assertThat(items.findById("b").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.PENDING);
        assertThat(receipts.findById("b")).isEmpty();

        // c chưa được gọi vì runner dừng ở b.
        assertThat(items.findById("c").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.PENDING);
        assertThat(receipts.findById("c")).isEmpty();
        assertThat(receipts.count()).isEqualTo(1);

        // Rerun đọc PENDING mới: chỉ b và c.
        runner.runOnce();

        assertThat(receipts.count()).isEqualTo(3);
        assertThat(items.findById("a").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);
        assertThat(items.findById("b").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);
        assertThat(items.findById("c").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);

        verify(failureGate, times(1))
                .afterDatabaseWrites("a");
        verify(failureGate, times(2))
                .afterDatabaseWrites("b");
        verify(failureGate, times(1))
                .afterDatabaseWrites("c");
    }

    @Test
    void rerunOnlyProcessesNewlyArrivedPendingItems() {
        items.save(new WorkItem("old", "payload-old"));
        runner.runOnce();

        items.save(new WorkItem("new", "payload-new"));
        runner.runOnce();

        assertThat(receipts.count()).isEqualTo(2);
        assertThat(items.findById("old").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);
        assertThat(items.findById("new").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);

        verify(failureGate, times(1))
                .afterDatabaseWrites("old");
        verify(failureGate, times(1))
                .afterDatabaseWrites("new");
    }

    @Test
    void manualTriggerExecutesWithoutWaitingForRealSchedule() {
        items.save(new WorkItem("timer", "payload-t"));

        trigger.tick();

        assertThat(receipts.findById("timer")).isPresent();
        assertThat(items.findById("timer").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);

        verify(failureGate, times(1))
                .afterDatabaseWrites("timer");
    }

    @Test
    void twoConcurrentAttemptsForOneItemYieldOneReceipt()
            throws Exception {
        items.save(new WorkItem("parallel", "payload-p"));

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<Void> action = () -> {
            ready.countDown();
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "start gate timed out");
            }
            // @Transactional được áp qua Spring proxy.
            processor.process("parallel");
            return null;
        };

        ExecutorService pool = Executors.newFixedThreadPool(2);
        Future<Void> first = pool.submit(action);
        Future<Void> second = pool.submit(action);

        try {
            assertThat(ready.await(5, TimeUnit.SECONDS))
                    .isTrue();
            start.countDown();

            first.get(20, TimeUnit.SECONDS);
            second.get(20, TimeUnit.SECONDS);
        }
        finally {
            start.countDown();
            pool.shutdownNow();
        }

        assertThat(items.findById("parallel").orElseThrow()
                .getStatus()).isEqualTo(WorkStatus.DONE);
        assertThat(receipts.count()).isEqualTo(1);
        assertThat(receipts.findById("parallel"))
                .isPresent();

        // Chỉ worker thắng lock xử lý qua failpoint.
        verify(failureGate, times(1))
                .afterDatabaseWrites("parallel");
    }

    @Test
    void unknownWorkItemFailsLoudlyAndCreatesNoReceipt() {
        assertThatThrownBy(() ->
                processor.process("does-not-exist"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Unknown work item");

        assertThat(receipts.count()).isZero();
    }
}
~~~

### 7.19. Vì sao từng test có giá trị?

**Test 1 — rerun sau DONE:** cùng một batch được gọi hai lần. Lần sau không tạo receipt mới, và hook bên trong transaction chỉ chạy một lần. Assertion DB count là quan trọng hơn verify method vì nó cho biết side effect đã được lưu chính xác.

**Test 2 — duplicate call trực tiếp:** giả lập hai delivery cùng work ID theo thứ tự. `process` kiểm status sau row lock nên lần hai return; không tạo receipt mới. Test không chỉ dựa vào runner lọc PENDING.

**Test 3 — exception sau flush:** test inject RuntimeException **sau khi INSERT/UPDATE đã flush**. Exception đi qua transactional interceptor, rollback cả receipt và status. Lần sau retry thành công và có đúng một receipt. Điều này chứng minh flush không đồng nghĩa commit.

**Test 4 — lỗi ở giữa batch:** A đã commit riêng; B rollback; C chưa gọi. Rerun không chạy A lần nữa, xử lý B/C. Đây là behavior quan trọng khi job bị gián đoạn sau khi hoàn thành một phần.

**Test 5 — incremental rerun:** sau run đầu, có thêm item mới; run sau chỉ xử lý item mới, không làm lại item cũ.

**Test 6 — manual scheduler trigger:** test business job qua public adapter `tick()` mà không chờ 60 giây. Schedule activation thuộc profile, có thể kiểm bằng một test configuration riêng nếu yêu cầu.

**Test 7 — concurrent attempts:** hai worker threads cùng gọi public bean `ItemProcessor`. Database pessimistic row lock serialize check-and-write; sau cả hai requests chỉ có một receipt và một successful processing hook. Test không kiểm multi-node failover, nhưng kiểm race cơ bản mạnh hơn test sequential duplicate.

**Test 8 — unknown item:** không được âm thầm tạo receipt hoặc nuốt lỗi. Business có thể định nghĩa “missing” là skip thay vì exception; khi đó chỉnh cả production contract và assertions có chủ đích.

### 7.20. Các yếu tố giúp test deterministic

- Job không tự chạy trong profile `test`.
- Không có `Thread.sleep` hoặc đợi cron tới thời điểm thật.
- Failure injection có item ID và số invocation xác định.
- Concurrency dùng `CountDownLatch` và `Future.get(timeout)`; không đoán Thread scheduling bằng sleep.
- Dữ liệu được cleanup ở `@BeforeEach` bằng repository transactions.
- Không có `@Transactional` trên JUnit test method, nên service transactions thực sự commit/rollback và readback nhìn state sau completion.
- Mỗi fixture dùng ID riêng trong test, không dựa vào test order.
- SQLite/H2 không thay production database semantics; test cần verify PostgreSQL locking bằng Testcontainers trong dự án thực.
- Mock chỉ thay `FailureGate`. Repositories, `ItemProcessor` transaction, lock và database đều là thật.

### 7.21. Lệnh chạy

Trong thư mục `job-rerun-recovery-lab`, với JDK 17+ và Maven:

~~~bash
mvn -q clean test

mvn -q -Dtest=JobRecoveryIntegrationTest test
~~~

Expected (nếu build và runtime phù hợp):
- 8 JUnit methods PASS.
- Receipt count phù hợp từng test; failed transaction không để lại row.
- Concurrency test kết thúc trong deadline.
- Maven exit code `0`, báo cáo trong `target/surefire-reports`.

**Không có một stdout cố định** của Hibernate/Spring/Maven trên mọi môi trường. Đọc actual Surefire results và stack trace khi fail. Mã lab được rà soát về API/cấu trúc nhưng **chưa chạy Maven/JUnit trong lúc biên soạn tài liệu**.

### 7.22. Chạy scheduler thật ngoài test

Bật profile:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=scheduler
~~~

Application sẽ nạp `SchedulerConfiguration` và kích hoạt `ScheduledTrigger.tick()` theo `lab.job.delay-ms`. Vì lab không có API seed work items, app khởi động một mình sẽ không có pending work; log có thể chỉ cho thấy application started/scheduled scans. Dùng JUnit để seed và quan sát xử lý.

**Không bật `scheduler` cùng lúc với integration tests**: timer có thể lấy item khi test còn đang tạo fixtures và khiến assertions race. Nếu production có nhiều replicas cùng profile, job-level idempotency/locking phải bảo vệ đúng concurrency.

## 8. Vì sao Spring test có thể cho PASS giả?

### 8.1. @SpringBootTest không tự rollback

`@SpringBootTest` tải application context; **nếu bản thân test method không có `@Transactional`**, các service transactions được mở/commit khi gọi qua proxy. Lab dựa vào behavior này.

Nếu thêm `@Transactional` vào class test, `ItemProcessor.process` với propagation `REQUIRED` có thể tham gia test-managed transaction dài, không commit từng item. Test fail ở B có thể làm rollback A cùng test hoặc khiến state chưa commit vẫn quan sát được trong transaction. Điều đó **không** kiểm đúng production boundary.

### 8.2. @DataJpaTest rollback mặc định

`@DataJpaTest` thường tạo test-managed transaction và rollback cuối test. Nó rất tốt để kiểm entity/repository mapping, nhưng không tự chứng minh resume sau **real commit**. Với bài kiểm transaction per item, chọn full Spring context không có test transaction, hoặc dùng `TestTransaction`/@Commit một cách cẩn thận và cleanup data committed.

### 8.3. Verify mock không thay state assertion

~~~java
verify(jobHandler).handle("x");
~~~

Assertion này chỉ nói method mock được gọi, không xác định:
- DB row commit hay rollback.
- Transaction có bao trùm đúng hai writes.
- Một worker khác cùng lúc tạo duplicate không.
- Outcome qua external gateway có thực sự hoàn tất không.

Do đó, dùng mock để **inject failure/observe calls**, giữ DB thật và query sau khi transaction kết thúc.

### 8.4. catch exception bên trong @Transactional có thể gây commit ngoài ý muốn

~~~java
@Transactional
public void process(String id) {
    try {
        saveReceipt(id);
        callSomethingThatFails();
    }
    catch (Exception ex) {
        log.warn("failed", ex);
    }
}
~~~

Nếu exception bị bắt và method return bình thường, Spring có thể cố commit transaction dù workflow thực chất fail (trừ khi transaction đã bị đánh dấu rollback-only hoặc lỗi resource buộc rollback). Để test đúng, assert state sau call; đừng mặc định “có log lỗi = rollback”.

Nếu muốn lưu failure attempts, hãy tách attempt state sang transaction riêng **sau** rollback hoặc dùng một failure-record transaction có policy rõ, không catch rồi vô tình commit partial business writes.

### 8.5. Checked exceptions và rollback rules

Mặc định Spring `@Transactional` rollback cho unchecked exceptions/Errors; checked exceptions có thể không gây rollback nếu không cấu hình `rollbackFor` hoặc global default rollback policy. Khi job có checked exception, cần test thực:
- Ném checked exception qua boundary.
- Kiểm DB state sau method.
- Quyết định `@Transactional(rollbackFor = Exception.class)` hoặc policy cụ thể.

Lab inject `IllegalStateException` (unchecked) có chủ đích.

## 9. Testing lặp với nhiều instances và nhiều threads

### 9.1. Sequential duplicate không đủ cho race

Một test gọi `process("x")` hai lần tuần tự có thể PASS dù code check-then-insert không lock. Hai calls cùng lúc mới bộc lộ race.

Concurrency test nên:
1. Seed một row bền vững trước.
2. Tạo hai tasks.
3. Dùng gate/latch để cùng bắt đầu.
4. Gọi **Spring proxy** từ mỗi thread.
5. Đợi futures với timeout hữu hạn.
6. Query database sau hai transactions.
7. Assert một receipt và DONE.
8. Cleanup dù test fail.

### 9.2. Lock semantics của database khác nhau

`PESSIMISTIC_WRITE` trong H2, PostgreSQL, MySQL, Oracle có thể khác về wait, deadlock, isolation và “skip locked” support. H2 test kiểm application wiring cơ bản; production-grade concurrency cần Testcontainers với đúng DB/version/schema/migrations.

Thêm cases:
- Hai processes khác JVM cùng xử lý một ID.
- Lock wait timeout.
- Deadlock retryable vs non-retryable.
- Worker crash giữ lock rồi DB release.
- Transaction cancellation và connection pool recovery.
- Read committed vs repeatable read.
- Unique constraint conflict nếu một code path quên lock.

### 9.3. Distributed lock không tự tạo exactly once

ShedLock, Redis lease, ZooKeeper hoặc DB advisory lock có thể làm job không chạy đồng thời, nhưng:
- Lock có thể hết hạn giữa công việc dài.
- Worker cũ có thể tiếp tục sau khi worker mới lấy lock.
- Network split có thể gây hai holders về mặt business.
- Cần **fencing token** hoặc DB compare-and-set/unique constraints khi critical.
- Lock chỉ giải quyết overlap, không bảo đảm recovery sau external side effect.

### 9.4. Một “global lock” có thể làm giảm throughput

Khóa toàn bộ job ngăn nhiều replicas chạy cùng lúc, dễ hiểu nhưng có thể không đáp ứng throughput. Per-item DB lock/claim cho phép xử lý song song những IDs khác nhau. Test nên kiểm vừa **không duplicate cùng ID** vừa **độc lập giữa hai IDs**, và xem lock contention.

### 9.5. Không dựa vào JVM synchronized

~~~java
public synchronized void process(String id) {
    // ...
}
~~~

`synchronized` chỉ khóa trên instance/object của JVM đó. Hai Spring instances chạy trên hai pods có locks khác nhau. Database row-level lock, unique constraint, message partition ordering hoặc durable claim thích hợp hơn cho cross-instance correctness.

## 10. Retry, backoff và phân loại lỗi

### 10.1. Không retry mọi exception

| Lỗi | Retry? | Hướng xử lý |
| --- | --- | --- |
| Network timeout tới provider | Thường có, nhưng phải idempotent | Backoff + idempotency key |
| DB deadlock/lock timeout | Có thể | Rerun transaction mới, bounded attempts |
| Broker temporarily unavailable | Thường có | Outbox pending/retry |
| Validation lỗi input vĩnh viễn | Thường không | FAILED/DLQ, cảnh báo |
| Duplicate đã DONE | Không cần làm lại | Return idempotent result |
| Payload conflict cùng key | Không tự coi duplicate | Reject/alert |
| Missing work item | Theo business contract | Fail/skip rõ ràng |
| Token/credential sai | Không retry vô hạn | Sửa configuration |
| Schema mismatch | Không retry vô hạn | Quarantine poison event |

### 10.2. Backoff có ý nghĩa

Không loop retry ngay trong một transaction đang giữ lock:

~~~java
for (int i = 0; i < 1000; i++) {
    try {
        gateway.call();
    }
    catch (Exception ex) {
        // loop vô hạn hoặc tight loop nguy hiểm
    }
}
~~~

Cần:
- Attempt count.
- Backoff có giới hạn, thường exponential và jitter.
- Max attempts / retry deadline.
- Next-attempt timestamp lưu bền vững.
- Lý do failure và stack trace được redacted.
- Dead-letter/quarantine cho poison items.
- Metrics cho waiting/running/retrying/failed.

### 10.3. @Retryable có ranh giới AOP riêng

Spring Retry có `@Retryable` nhưng không nên mặc định nó đã hoạt động chỉ vì gắn annotation. Cần dependency/configuration phù hợp (ví dụ `spring-retry` và AOP, `@EnableRetry` theo cách setup), lời gọi đi qua proxy, và policy retry/transaction boundary rõ.

Một retry quanh toàn bộ batch có thể lặp cả batch, không chỉ item hỏng. Nếu business muốn per-item retry, đặt retry boundary đúng cấp; nếu retry sau external side effect, dùng idempotency key.

### 10.4. Time deterministic

Một `nextAttemptAt` so với `Instant.now()` khiến test phụ thuộc wall clock. Nên inject `Clock`:

~~~java
Clock clock = Clock.fixed(
        Instant.parse("2026-01-15T10:00:00Z"),
        ZoneOffset.UTC);

Instant now = Instant.now(clock);
Instant next = now.plusSeconds(60);
~~~

Snippet minh họa với `java.time` imports, không nằm trong project lab. Test kiểm:
- At T0: RETRY_WAIT chưa eligible.
- T0+59s: vẫn chưa.
- T0+60s: eligible.
- Khi maxAttempts vượt ngưỡng: FAILED.
- Không dùng `Thread.sleep(60000)` để đợi.

### 10.5. Retry phải chạy trong transaction mới khi cần

Sau rollback của một transaction, đừng cố dùng JPA `EntityManager` đã bị đánh dấu rollback-only để tiếp tục business write trong cùng transaction. Lần retry nên mở transaction mới, tải lại entity state, và re-evaluate eligibility/locks.

## 11. At-least-once message processing và scheduled job có điểm chung

### 11.1. Message redelivery

Kafka consumer có thể xử lý DB thành công rồi crash trước offset commit; RabbitMQ consumer có thể xử lý DB xong rồi crash trước basicAck. Broker sẽ có khả năng giao lại cùng logical event. Consumer nên check idempotency record/unique key trong transaction business.

~~~text
Kafka: receive event-42
  -> DB business write COMMIT
  -> crash trước offset commit
  -> restart đọc lại event-42
  -> DB dedupe -> skip side effect
  -> offset commit
~~~

Đây là **at-least-once plus idempotent handler**, không phải exactly-once xuyên Kafka và database.

### 11.2. Ack trước business commit cũng nguy hiểm

Nếu consumer commit offset/ack message **trước** khi database business transaction commit, process crash giữa hai bước sẽ làm mất operation. Test failure matrix phải xác định thứ tự:
- Receive.
- Validate.
- Business DB transaction.
- Ack/offset commit.
- Retry/DLT khi lỗi.

Không có một thứ tự đơn giản nào tự tạo atomicity giữa hai hệ thống độc lập.

### 11.3. EventId vs businessId

Một business operation có thể phát nhiều event versions:
- `eventId` định danh một message cụ thể để dedupe delivery.
- `businessOperationId` định danh hiệu quả nghiệp vụ cần giữ duy nhất.
- `aggregateId` định danh entity.
- `idempotencyKey` có thể xuất phát từ caller/API.
- `payloadHash` giúp phát hiện cùng key nhưng parameters khác.

Không dùng `UUID.randomUUID()` mới trên mỗi retry làm business idempotency key, vì như vậy retry biến thành operation mới.

### 11.4. Scheduled sweep cũng là một cơ chế redelivery

Một scheduled poll quét lại `PENDING` chính là một dạng delivery “có thể nhiều lần” của công việc còn tồn. Nếu dùng status bền vững, lock và dedupe, nó có thể resume sau process restart. Nếu chỉ lưu danh sách pending trong RAM, process crash có thể làm mất items.

## 12. Failure giữa batch: chọn chính sách rõ ràng

### 12.1. Fail-fast

Runner dừng tại item B. Ưu điểm: không che system-wide failure và dễ debug. Nhược điểm: C/D/E phải đợi lần sau. Lab dùng fail-fast có chủ đích.

### 12.2. Continue-on-error

Nếu mỗi item độc lập, có thể catch exception **ở ngoài** `ItemProcessor.process(...)`:

~~~java
for (String id : pendingIds) {
    try {
        processor.process(id);
    }
    catch (RuntimeException ex) {
        // Ghi failure/attempt ở transaction riêng,
        // tiếp tục item kế tiếp theo policy.
    }
}
~~~

Đây là snippet ý tưởng, không phải class runnable riêng. Đừng catch bên trong transactional processor rồi commit partial writes. Khi continue, phải có metrics/alerts và retry state; không âm thầm bỏ qua lỗi.

### 12.3. Poison item

Một item luôn ném validation exception có thể làm fail-fast job dừng ở cùng ID mỗi lần. Giải pháp:
- Max attempts.
- Xác định permanent vs transient.
- Mark FAILED/quarantine sau khi ghi lý do.
- Cho phép items khác chạy.
- Có manual re-drive an toàn khi dữ liệu được sửa.
- Test rằng poison item không gây infinite retry.

### 12.4. Batch checkpoint có business meaning

Checkpoint “đã xong item A” nên được lưu bằng durable DB state, không phải counter trong memory. Nếu thứ tự items thay đổi, ghi “đã xử lý đến index 42” có thể bỏ sót hoặc lặp items. Dùng ID/status/cursor theo business semantics, hoặc một water mark có ordering guarantee được kiểm thử.

### 12.5. Resume sau crash không được phụ thuộc JVM memory

Không chỉ lưu:

~~~java
private int lastProcessedIndex;
~~~

Nếu app restart, biến reset; nếu list reorder, index không còn nghĩa. Dùng DB status/offset/lease để khôi phục. Test restart thật bằng container/process sẽ chứng minh dữ liệu persist vượt qua JVM boundary.

## 13. Ngoại lệ lớn: side effect ngoài DB và transactional outbox

### 13.1. Thời điểm crash không thể giải quyết chỉ bằng @Transactional

~~~text
DB COMMIT success
       |
       | JVM crash
       v
AFTER_COMMIT event/email publish chưa chạy
~~~

Một callback `@TransactionalEventListener(AFTER_COMMIT)` không đảm bảo sẽ chạy nếu process crash sau database commit nhưng trước callback. Ngược lại:

~~~text
External provider xác nhận thành công
       |
       | JVM crash
       v
DB chưa ghi trạng thái sent/acknowledged
       |
       v
Rerun -> gửi lại cùng operation
~~~

Nếu email/payment/event delivery là yêu cầu không được mất, chỉ một `CompletionReceipt` trong DB chưa đủ để chứng minh external system đã nhận.

### 13.2. Transactional outbox

Trong **cùng transaction T1**, ghi:
1. Business state.
2. Outbox row với stable event ID/payload và status PENDING.

Sau commit:
- Relay đọc outbox pending.
- Gửi ra broker/provider với **idempotency key**.
- Khi được xác nhận, cập nhật outbox delivery state.
- Nếu crash trước publish, row pending vẫn ở DB và lần sau được retry.
- Nếu crash sau publish trước mark SENT, có thể publish lại; consumer/provider phải dedupe.

~~~text
T1 (atomic DB transaction):
  UPDATE work_item -> DONE
  INSERT completion_receipt(work_id)
  INSERT outbox_event(event_id, payload, PENDING)
  COMMIT
        |
        v
T2 relay reads committed PENDING event
        |
        +-- publish(event_id)
        +-- provider ACK
        +-- mark SENT in a separate transaction
        |
        +-- crash? retry PENDING
                  |
                  +-- same event_id -> idempotent receiver
~~~

Không tạo outbox row **chỉ trong AFTER_COMMIT listener** nếu yêu cầu nó tồn tại atomically với business state: như vậy crash gap vẫn tồn tại.

### 13.3. Pseudocode outbox adaptation

~~~java
@Transactional
public void processOne(String id) {
    WorkItem item = items.findLockedById(id)
            .orElseThrow();

    if (item.getStatus() == WorkStatus.DONE) {
        return;
    }

    receipts.save(new CompletionReceipt(
            item.getId(), item.getPayload()));

    outbox.save(new OutboxEvent(
            "processed:" + item.getId(),
            item.getId(),
            item.getPayload(),
            "PENDING"));

    item.markDone();
}
~~~

Đây là **snippet kiến trúc**; project runnable không định nghĩa `OutboxEvent`/repository. Điều cần giữ là business write + outbox write **cùng T1** với unique event ID.

### 13.4. Tests phải kiểm cả hai khoảng crash

| Fault | Expected DB state | Lượt tiếp theo |
| --- | --- | --- |
| Failure trước T1 commit | WorkItem PENDING, không receipt/outbox | Reprocess business |
| T1 commit, relay chưa publish | DONE + receipt + outbox PENDING | Relay retry, không reprocess business |
| Publish thành công, relay crash trước mark SENT | Outbox vẫn PENDING | Re-publish cùng eventId, consumer dedupe |
| Consumer business commit, crash trước ack | Consumer dedupe record đã có | Redelivery skip effect và ACK |
| Provider timeout nhưng đã xử lý | Outcome chưa rõ | Query/reconcile với stable idempotency key |
| Payload conflict cùng key | Không âm thầm overwrite | Reject/alert/reconcile |

### 13.5. Payment và irreversible side effects

Payment capture là ví dụ nguy hiểm: charge hai lần không thể được “rollback” bằng DB transaction. Test nên dùng payment sandbox/fake provider có **idempotency-key contract**:
- Lặp cùng key + cùng parameters → một charge, trả cùng kết quả.
- Lặp cùng key + khác parameters → conflict, không tạo charge mới.
- Timeout sau provider accepted → reconcile bằng provider operation ID.
- Retry/backoff giới hạn và có audit trail.
- Không gọi live payment provider từ CI.

Đừng tuyên bố “exactly once payment” chỉ dựa vào một database row lock.

### 13.6. Reconciliation là một phần của recovery

Nếu outbox/relay/provider state sai lệch, scheduled reconciliation quét những operations đang “unknown” sau một threshold, đối chiếu với external provider hoặc broker, đưa về trạng thái cuối hoặc cần can thiệp. Tests nên mô phỏng cả:
- Provider success nhưng local status pending.
- Provider failure nhưng local state marked sent sai.
- Retry hết budget chuyển dead-letter/manual review.
- Duplicate reconciliation runs không nhân side effects.

## 14. Lease, PROCESSING status và worker chết giữa job dài

### 14.1. Vì sao một row lock dài không đủ?

Trong lab, transaction rất ngắn và chỉ thao tác database, nên pessimistic lock hợp lý. Với task kéo dài 30 phút hoặc gọi external API chậm, giữ DB transaction/connection/lock trong suốt thời gian đó gây contention/pool exhaustion.

Production có thể dùng state machine:

~~~text
PENDING -> PROCESSING(owner, leaseUntil, attempt)
   |           |
   |           +-- success -> DONE
   |           +-- failure -> RETRY_WAIT
   |           +-- lease expired -> PENDING (recover)
   |
   +-- invalid -> FAILED
~~~

### 14.2. Atomic claim

Một worker claim item bằng một câu SQL conditional update (hình thức tùy database):

~~~sql
UPDATE work_items
   SET status = 'PROCESSING',
       claimed_by = :worker_id,
       lease_until = :lease_until,
       attempt_count = attempt_count + 1
 WHERE work_id = :id
   AND status = 'PENDING'
~~~

**Đây là SQL minh họa**, không thuộc schema H2 runnable lab và không được copy trực tiếp vì bảng lab chưa có các cột này. Điều quan trọng là kiểm rowsAffected = 1 để biết chỉ một worker thắng claim. Các databases có thể hỗ trợ `SELECT ... FOR UPDATE SKIP LOCKED`, advisory locks hoặc queue-specific claim APIs.

### 14.3. Lease expiry và fencing

Worker A claim rồi bị stop-the-world GC; lease hết hạn, worker B claim lại. Worker A tỉnh dậy và tiếp tục external write. Nếu không kiểm ownership/fencing token khi commit side effect, hai workers có thể ghi trùng. Cần:
- Lease owner/epoch.
- Fencing token tăng đơn điệu.
- Compare-and-set khi mark DONE.
- Downstream chấp nhận fencing token/idempotency key khi cần.
- Test late worker không overwrite result của worker mới.

### 14.4. Test với fake Clock

Dùng injectable `Clock` để đưa thời gian từ T0 tới T0+leaseExpiry mà không sleep. Test:
- Chưa hết lease: không claim lại.
- Đúng lúc hết lease: được reclaim theo contract.
- Worker A hoàn thành muộn: fencing từ chối.
- Worker B thành công: chỉ một business result.
- Lease renew/heartbeat failure: policy rõ.
- Max attempts/poison item được xử lý.

### 14.5. Do not use only in-memory flags

`AtomicBoolean running` hoặc `ReentrantLock` có thể ngăn overlap trong một JVM, nhưng không bảo vệ khi Kubernetes scale replicas, crash/restart hoặc scheduler nodes khác nhau.

## 15. Kiểm thử asynchronous completion đúng cách

### 15.1. Không assert ngay sau @Async

~~~java
service.processAsync("x");
assertThat(receiptRepository.findById("x"))
        .isPresent();
~~~

Nếu `processAsync` trả ngay và worker chạy sau, assertion race. Test nên trả `CompletableFuture` có completion signal hoặc dùng thread-safe probe/await.

### 15.2. CompletableFuture

~~~java
CompletableFuture<Void> task =
        asyncProcessor.processAsync("x");

task.get(5, TimeUnit.SECONDS);

assertThat(receipts.findById("x")).isPresent();
~~~

Đây là snippet mở rộng, giả định `processAsync` trả `CompletableFuture<Void>`. Không nằm trong runnable lab. `get` với timeout chờ hoàn thành và propagate failure vào test. Nếu async method return void, cần `AsyncUncaughtExceptionHandler`/probe để failures không bị nuốt.

### 15.3. CountDownLatch

~~~java
CountDownLatch completed = new CountDownLatch(1);

// Fake gateway hoặc callback:
completed.countDown();

// JUnit thread:
assertThat(completed.await(
        5, TimeUnit.SECONDS)).isTrue();
~~~

Snippet minh họa, không tự biên dịch nếu tách khỏi test setup. Chỉ count down **sau khi side effect quan sát được**, không phải ngay khi executor nhận task.

### 15.4. Bounded polling

Với eventual consistency, Awaitility hoặc polling có deadline sẽ tốt hơn `Thread.sleep(1000)` rồi một lần assert. Tuy nhiên polling không được che business race: nếu requirement đòi atomic exact state ngay sau method return, test nên assert ngay thay vì đợi cho hệ thống tự sửa sai.

### 15.5. Negative assertion với async

“Không thấy message trong 20ms” **không chứng minh sẽ không có message**. Nếu cần chứng minh no side effect:
- Tắt/kiểm soát executor hoặc dùng fake producer để thấy scheduling attempt.
- Kiểm business state/unique constraint và completion signal.
- Chọn bounded observation window phù hợp với test architecture.
- Với Kafka/Rabbit, kiểm offset/acks/DLQ theo protocol, không dựa vào biến local có race.

## 16. Những lỗi phổ biến và chẩn đoán

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Lần rerun tạo receipt thứ hai | Không dùng stable idempotency key/unique constraint | PK/unique + trạng thái DONE |
| Two workers cùng xử lý ID | Check-then-act không atomic | Row lock/atomic claim + concurrent test |
| Test pass sequential nhưng fail parallel | Chỉ test gọi hai lần tuần tự | Latch + thread/process concurrency |
| Test fail sau flush nhưng row vẫn được thấy | Query trong cùng transaction/first-level cache | Read sau rollback, clear context nếu cần |
| Item A mất khi B fail | Runner có outer transaction | Transaction per item qua bean proxy |
| Item B được ghi DONE dù throw | Exception bị catch trong @Transactional | Propagate/mark rollback-only, test state |
| @Transactional không áp dụng | Self-invocation/private method | Gọi qua Spring bean proxy |
| Checked exception vẫn commit | Default rollback rules | `rollbackFor`/policy rõ |
| @SpringBootTest test không phản ánh commit | Gắn test-level @Transactional | Test không có outer transaction |
| @DataJpaTest luôn rollback | Slice transactional mặc định | Test separate real commit boundary |
| Retry trùng external payment | Side effect ngoài DB không atomic | Provider idempotency + reconcile/outbox |
| Job mất event sau DB commit | In-memory after-commit publish crash gap | Transactional outbox |
| Outbox gửi hai lần | Crash sau publish trước mark SENT | Stable eventId + consumer idempotency |
| Poison item chặn batch mãi | Fail-fast không có terminal state | Max attempts/FAILED/DLQ |
| @Scheduled chạy nhiều lần trên cluster | Mỗi replica có scheduler | Distributed lock/claim + DB constraints |
| Job chạy trong lúc setup test | @EnableScheduling active trong test | Scheduler profile off, manual trigger |
| @Async assertion flaky | Không chờ completion | Future/latch/Awaitility bounded |
| Retry state không tới hạn đúng | Wall clock/timezone | Inject Clock, fake-time tests |
| Test H2 pass, PostgreSQL lock fail | Lock/isolation dialect khác | Testcontainers PostgreSQL |
| Unknown work silently skipped | Exception bị nuốt | Define missing-item contract |
| Duplicate key nhưng payload thay đổi | Chỉ check ID | Payload hash/version conflict policy |
| @DirtiesContext làm tưởng DB sạch | Context caching khác DB state | Explicit cleanup/test DB isolation |
| CI report xanh nhưng side effect còn pending | Assert quá sớm hoặc chỉ verify mock | Query committed outcome + completed signal |

### 16.1. Debug transaction boundary

Ghi lại:
- Test method có `@Transactional` không?
- Runner có outer transaction không?
- `ItemProcessor.process` có đi qua Spring proxy không?
- Chạy trên thread nào?
- JPA flush đã xảy ra chưa?
- Exception là unchecked/checked?
- DB transaction thật đã commit hay rollback?
- Side effect có nằm trong cùng DB transaction không?

Đừng sửa expected “cho xanh” trước khi biết transaction nào thực thi.

### 16.2. Debug concurrency

Ghi:
- Work ID/idempotency key.
- Worker/instance ID và transaction correlation.
- Lock acquisition/timeout.
- Status trước và sau khi lock.
- Unique constraint outcome.
- Attempt count/retry reason.
- Timings đã normalized, không rò rỉ PII/secrets.

Không dùng producer/worker logs như nguồn duy nhất chứng minh đúng business result.

### 16.3. Debug retry

Phân biệt failure transient (timeout, deadlock) và permanent (invalid payload, missing schema). Cần quan sát attempt count, backoff, nextAttemptAt, terminal status, DLQ/outbox state. Retry vô hạn không phải recovery strategy có kiểm soát.

## 17. Bài tập thực hành

1. Chạy `JobRecoveryIntegrationTest`. Giải thích tại sao có tám test thay vì chỉ một happy path.
2. Xóa kiểm `DONE` trong `ItemProcessor` và quan sát duplicate invocation tạo lỗi unique key hoặc duplicate side effect; khôi phục logic.
3. Bỏ `@Lock(PESSIMISTIC_WRITE)` rồi chạy concurrent test nhiều lần; giải thích vì sao kết quả có thể thành race/constraint violation.
4. Xóa unique primary key ở `CompletionReceipt` trong bản biến thể và đánh giá rủi ro duplicate.
5. Thêm error tại trước `saveAndFlush`; kiểm row PENDING và không receipt.
6. Inject RuntimeException sau `saveAndFlush`; kiểm rollback dù SQL đã chạy.
7. Trong batch 3 items, tạo lỗi ở item thứ hai; kiểm A DONE, B/C pending, rồi retry.
8. Đổi `BatchRunner.runOnce()` thành `@Transactional`; giải thích tại sao transaction semantics khác.
9. Chuyển `ItemProcessor.process` thành private helper self-invoked; xem vì sao proxy không áp dụng `@Transactional`.
10. Thêm một checked exception, quan sát rollback policy và dùng `rollbackFor` khi cần.
11. Cho phép continue-on-error, ghi failure attempts trong transaction khác rồi xử lý C dù B lỗi.
12. Thêm `RETRY_WAIT`/`FAILED`, max attempt count và deterministic fake Clock.
13. Xây PostgreSQL Testcontainers test cho `PESSIMISTIC_WRITE` với hai clients/transactions và lock timeout.
14. Thêm `payloadHash`; cùng ID+khác payload phải bị reject, không silent skip.
15. Tạo một outbox row cùng transaction WorkItem/Receipt, kiểm rollback để lại không outbox.
16. Giả lập relay crash sau publish trước mark SENT; dùng same eventId và consumer deduplication.
17. Viết test provider sandbox “timeout but accepted” và reconciliation theo operation ID.
18. Thêm `@Async` worker và bounded future/latch thay `Thread.sleep`.
19. Đổi scheduler từ fixedDelay sang cron và kiểm timezone/DST với fake time/`CronExpression`.
20. Mô phỏng 2 replicas cùng kích hoạt scheduler, kiểm per-item claim/unique result.
21. Tạo lease/workerId/fencing token và test late worker không overwrite newer worker.
22. Giới hạn batch 100 items, dùng pagination/claim thay load toàn bộ pending rows.
23. Thêm metrics: successful items, attempted, duplicates skipped, rolled back, retried, terminal failed.
24. Thiết kế test process crash thật bằng container: kill sau DB commit, restart, assert resume/outbox.
25. Review một test đang dùng `@Transactional` outer và sai suy luận “đã commit”; sửa setup để kiểm real service transaction.

## 18. Checklist trước khi merge

- [ ] Tên job/business operation ID ổn định qua retries/restarts?
- [ ] Duplicate ID với payload khác có policy rõ?
- [ ] Đã xác định idempotent effect nằm trong phạm vi DB hay external?
- [ ] Có rerun test sau DONE?
- [ ] Có retry sau rollback test?
- [ ] Có lỗi sau flush nhưng trước commit?
- [ ] Có lỗi giữa batch và kiểm previous commits còn nguyên?
- [ ] Có test concurrent same-ID attempts?
- [ ] Lock/unique constraint/claim phù hợp production DB?
- [ ] Không dựa vào `synchronized` trong một JVM cho cluster correctness?
- [ ] Runner và per-item processor có transaction boundaries rõ?
- [ ] `@Transactional` đi qua Spring proxy?
- [ ] Không catch lỗi rồi vô tình commit partial writes?
- [ ] Checked exceptions có rollback policy đúng?
- [ ] Test không có outer transaction làm sai commit semantics?
- [ ] Scheduler disabled/deterministic trong unit/integration test?
- [ ] Manual trigger có thể gọi mà không sleep?
- [ ] Async tests đợi completion có deadline?
- [ ] Có explicit retries/backoff/maximum attempts?
- [ ] Poison items có terminal/quarantine path?
- [ ] Có dữ liệu attempt/lease để recover sau restart?
- [ ] DB cleanup không ảnh hưởng các tests khác?
- [ ] Parallel tests có per-test namespace/database isolation?
- [ ] External calls dùng idempotency key/transactional outbox/reconciliation?
- [ ] Test before/after publish/ack crash gaps?
- [ ] Không tuyên bố exactly once xuyên DB + broker/payment chỉ vì DB lock?
- [ ] Không gửi email/payment/message production khi chạy CI?
- [ ] Metrics/logs có trace IDs nhưng không lộ secrets/PII?
- [ ] Có production-like database test cho lock/isolation nếu critical?
- [ ] Maven/JUnit reports xác nhận số tests executed và failure scenarios?

**Kết luận:** Kiểm thử một job bất đồng bộ hoặc theo lịch phải vượt ra khỏi “gọi một lần và thấy kết quả”. Hãy chạy lại sau success, inject lỗi ở **đúng transaction boundary**, kiểm tiến độ giữa batch, và kích hoạt đồng thời để lộ check-then-act race. Với database-only side effects, transaction per item + row lock + unique business key có thể bảo đảm một durable result cho mỗi ID trong phạm vi đã test. Với external side effects, cần thêm outbox, retry, idempotent receiver và reconciliation. Một bài test có tên “retry safe” chỉ đáng tin khi chứng minh cả **state sau failure** và **state sau rerun**, không phải chỉ thấy method được gọi.

## 19. Tài liệu chính thức

- Spring Framework 6.2 — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 — @Scheduled Javadoc (fixedDelay, fixedRate, cron): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html
- Spring Framework 6.2 — @EnableScheduling Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/EnableScheduling.html
- Spring Framework 6.2 — Using @Transactional and self-invocation: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework 6.2 — Transaction rollback rules: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html
- Spring Data JPA 3.5 — Locking with @Lock: https://docs.spring.io/spring-data/jpa/reference/3.5/jpa/locking.html
- Spring Data JPA — Transactionality: https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — DataJpaTest API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html
- Spring Boot 3.5 — Testcontainers: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Kafka — Listener Container and Offset Commit: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html
- Spring AMQP — Consumer Acknowledgements: https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html
- PostgreSQL — Explicit Locking: https://www.postgresql.org/docs/current/explicit-locking.html

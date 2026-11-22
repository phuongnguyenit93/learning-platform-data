# Lưu aggregator state qua restart — dự án thực hành Spring Integration runtime

## 1. Bài toán và kết quả cần đạt

Trong module **SPRING_INTEGRATION_RUNTIME**, chúng ta đã biết một message đi qua channel, consumer, poller và handler. Nhưng một **Aggregator** không thể xử lý toàn bộ công việc chỉ bằng một lần nhận message: nó phải **nhớ những messages đã đến của cùng một nhóm**, chờ điều kiện release, rồi mới phát output.

Bài thực hành **Thực hành tổng hợp → Lưu aggregator state qua restart** xây dựng một ứng dụng Spring Integration có thể chạy **hai lần trên cùng một database**:

- **Lần chạy 1 (seed):** gửi hai parts thuộc batch `BATCH-101`, nhưng batch yêu cầu ba parts. Aggregator chưa release và phải lưu trạng thái pending.
- **Dừng hẳn JVM/ApplicationContext:** các beans, scheduler, memory, queue trong process bị hủy.
- **Lần chạy 2 (resume):** khởi động application mới, chỉ gửi part thứ ba của cùng batch. Aggregator đọc lại hai parts cũ từ **persistent JDBC `MessageGroupStore`**, release một batch hoàn chỉnh rồi phát output.

Nếu kết quả chỉ hoạt động khi cả ba parts được gửi trong một lần chạy, chúng ta **chưa chứng minh được persistence qua restart**.

### Mục tiêu kỹ thuật

Sau bài này, bạn có thể:

1. Phân biệt memory state với durable aggregator state.
2. Chọn `MessageGroupStore` và schema lưu trữ phù hợp.
3. Tạo flow có `CorrelationStrategy`, `ReleaseStrategy`, aggregation handler và channel output.
4. Khởi tạo bảng JDBC **một lần**, chạy lại application mà **không** xóa database.
5. Kiểm chứng group 2/3 trước restart và kết quả 3/3 sau restart.
6. Giải thích thời điểm commit, in-flight messages, transaction, retry và broker ack.
7. Xử lý những lỗ hổng còn lại: duplicate, late arrivals, group timeout/expiry, lock contention và schema migration.
8. Xây integration test, fault injection, metrics và runbook phục hồi.

> **Cảnh báo:** “Group còn trong database sau restart” là một kết quả cụ thể; nó **không tự chứng minh exactly-once processing**, không đảm bảo output đã được commit tới downstream và không giải quyết duplicate khi broker redeliver.

## 2. Chọn đúng nơi lưu state

Một hệ thống Aggregator tối thiểu có ba loại dữ liệu khác nhau:

| Đối tượng | Ví dụ | Có cần sống qua restart? | Nơi lưu |
| --- | --- | --- | --- |
| Message đang chờ xử lý trong channel | Part chưa tới aggregator | Tùy SLA | `QueueChannel` có `MessageStore` hoặc broker |
| **Aggregator group state** | `BATCH-101` đã nhận P1/P2 | **Có**, trong bài này | Persistent `MessageGroupStore` |
| Kết quả đã release nhưng chưa publish thành công | Batch đủ 3 parts, outbound lỗi | Có nếu không được mất output | Outbox/durable outbound queue |
| Marker dedupe | Part P2 đã xử lý | Có nếu nguồn at-least-once | `MetadataStore`/inbox/business DB |
| Business order state | Đơn hàng đã hoàn tất | Có | Database nghiệp vụ |
| Connection/retry state | Socket, backoff, worker task | Tùy semantics | Adapter/worker, không thay group store |

`SimpleMessageStore` là một store in-memory để học cách aggregator hoạt động. Nó không thể giữ hai parts khi process bị tắt. Trong dự án này ta dùng **`JdbcMessageStore`**, implement khả năng lưu `Message<?>` và `MessageGroup` qua JDBC.

~~~mermaid
flowchart LR
    A["Nguồn gửi part"] --> C["inputParts / DirectChannel"]
    C --> T["Stateless transformer"]
    T --> G["Aggregator\ncorrelation=batchId"]
    G <--> S[("JDBC MessageGroupStore\nH2 file DB")]
    G -->|Đủ 3 parts| O["completedBatches / QueueChannel"]
    O --> H["ApplicationRunner nhận output"]
    R["Restart application"] -.->|"khởi động process mới"| G
    S -.->|"dữ liệu vẫn còn trên đĩa"| R
~~~

Điều cần hiểu rõ: `QueueChannel` dùng cho **output trong demo** vẫn là memory queue; ta tiêu thụ output ngay trước khi ứng dụng đóng. Nếu muốn bảo đảm một batch đã release nhưng chưa tiêu thụ output cũng được giữ qua crash, phải bổ sung **durable output boundary/outbox** ở bài nâng cao.

## 3. Vì sao Aggregator là stateful endpoint?

Một transformer thuần như `String::trim` có thể xử lý từng message độc lập. Aggregator phải giữ **một tập messages theo correlation key**.

Ví dụ:

~~~text
BATCH-101:
  P1 payload="  red  "
  P2 payload="  blue  "
  P3 payload="  green  "

Trạng thái sau P1: pending count=1
Trạng thái sau P2: pending count=2
Trạng thái sau P3: ready count=3 -> release
~~~

Mỗi `Message` có payload và headers, còn `MessageGroupStore` giữ các members của group. Group state cần bao gồm identity, members và metadata liên quan để framework quyết định release/expiry. Framework quản lý các thao tác group; bạn không nên tự tạo một singleton `HashMap<batchId,List<Message>>` rồi trông chờ nó an toàn qua restart.

### Correlation Strategy

Một **`CorrelationStrategy`** chọn key để gom các messages. Trong dự án, ta dùng header ứng dụng `batchId`. Tất cả parts của `BATCH-101` phải có cùng key.

### Release Strategy

Một **`ReleaseStrategy`** quyết định khi nào group đủ điều kiện xuất output. Demo dùng:

~~~java
group -> group.size() >= 3
~~~

**Chỉ phù hợp với dữ liệu demo có ba parts độc nhất và không redelivery.** Trong thực tế, group size là số message members, **không tự đồng nghĩa số partIds duy nhất**; P2 bị gửi hai lần có thể tạo release sớm.

### Group expiry

Nếu chỉ có hai parts và P3 không bao giờ đến, không thể giữ group vô hạn. Production cần `groupTimeout`/expiry/recovery policy. Nhưng trong bài học đầu tiên, ta **cố ý chưa đặt timeout tự hủy**, nhằm có thể tắt process rồi resume group còn dở.

## 4. Mô hình thời gian: dừng application chứ không xóa database

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant A1 as Aggregator JVM #1
    participant DB as H2 file database
    participant A2 as Aggregator JVM #2
    participant O as Output channel
    P->>A1: P1 (BATCH-101)
    A1->>DB: Persist P1 / group size 1
    P->>A1: P2 (BATCH-101)
    A1->>DB: Persist P2 / group size 2
    A1--xA1: ApplicationContext close / process exit
    Note over DB: Database file còn nguyên
    Note over A2: SpringApplication mới, cùng JDBC URL
    P->>A2: P3 (BATCH-101)
    A2->>DB: Read existing group P1 + P2
    A2->>DB: Add P3 / release condition true
    A2->>O: Aggregated result
    O-->>P: Batch output available
~~~

Không có “serialize toàn bộ Spring context”; state phải được persist tại **một backend độc lập với process lifetime**. Cũng không có nhu cầu giữ JVM #1 sống. Nếu demo kết quả đúng sau khi JVM #1 đã đóng, đó là bằng chứng pending group được khôi phục.

### Đặt tiêu chí pass/fail trước

| Mốc | Kỳ vọng | Nếu không đạt |
| --- | --- | --- |
| Seed, trước stop | `getMessageGroup(batchId).size()==2` | Messages chưa được store hoặc correlation sai |
| Seed, kiểm tra output | `receive(0)==null` | Release sớm hoặc output từ batch khác |
| Sau khi đóng JVM #1 | File database còn tồn tại | Đang dùng H2 in-memory hoặc xóa nhầm DB |
| Resume, trước gửi P3 | Store đọc được group size 2 | Đổi JDBC URL/region/schema, dữ liệu mất |
| Resume, sau gửi P3 | Nhận một aggregated output | Release không chạy hoặc output wiring lỗi |
| Sau completion | State theo completion policy | Cần quan sát cleanup/late duplicates riêng |

Khi bạn chỉ test **stop/start cùng một endpoint trong cùng JVM**, singleton store in-memory vẫn giữ group; đó **chưa phải test restart process**.

## 5. Stack và cấu trúc dự án

Ví dụ nhắm tới **Java 17+, Spring Boot 3.x và Spring Integration 6.x** có BOM tương thích. Dự án dùng:

- Spring Integration core + Java DSL;
- `spring-integration-jdbc` cho `JdbcMessageStore`;
- Spring JDBC để có `DataSource`;
- H2 ở chế độ **file**, không phải `jdbc:h2:mem`;
- JUnit 5/Spring Test cho test mở rộng;
- Micrometer/Spring Boot Actuator là tùy chọn cho quan sát production.

Cấu trúc dự án minh họa:

~~~text
aggregator-restart-lab/
├── build.gradle.kts
├── src/main/java/demo/integration/
│   └── AggregatorRestartLabApplication.java
└── src/main/resources/
    └── application.yml

agg-restart-db.mv.db      # phát sinh ở working directory sau lần chạy đầu
~~~

Tên database file trên phụ thuộc JDBC URL và H2 version. **Không đưa file dữ liệu local này vào git**, không xóa nó giữa hai lượt của cùng bài thực hành.

### Dependency Gradle Kotlin DSL

Chèn vào dự án Spring Boot đã cấu hình plugin, Java toolchain và dependency management:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    implementation("org.springframework.integration:spring-integration-jdbc")
    runtimeOnly("com.h2database:h2")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Các version được quản lý bởi **Spring Boot BOM** của dự án; không tự lấy Spring Integration 6.x nhưng dùng Spring Framework/Micrometer thuộc major đời khác. Đây chỉ là dependency block, không phải toàn bộ `build.gradle.kts`.

## 6. JDBC H2 file-based: cấu hình để sống qua restart

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  datasource:
    driver-class-name: org.h2.Driver
    url: jdbc:h2:file:./agg-restart-db;DB_CLOSE_ON_EXIT=FALSE
    username: sa
    password:
  sql:
    init:
      mode: never
      schema-locations: classpath:org/springframework/integration/jdbc/schema-h2.sql

logging:
  level:
    org.springframework.integration: INFO
~~~

**Vì sao quan trọng?**

1. `jdbc:h2:file:./agg-restart-db` tạo database file trên đĩa trong **working directory hiện tại**.
2. Dùng cùng working directory và JDBC URL cho cả seed và resume. Thay thư mục chạy làm ứng dụng mở **database khác**.
3. `spring.sql.init.mode=never` là mặc định bài thực hành để **không vô tình chạy lại script `CREATE TABLE`** trên database đã tồn tại.
4. **Lần đầu** ta sẽ override `--spring.sql.init.mode=always` để bootstrap schema JDBC một lần.
5. `schema-h2.sql` đến từ artifact `spring-integration-jdbc` của **version đã chọn**; cần đối chiếu đúng script/version trong BOM khi build.
6. `DB_CLOSE_ON_EXIT=FALSE` không làm state mất đi: dữ liệu nằm trong file; `DataSource`/pool phải được đóng để giải phóng file lock.

**Không dùng** `jdbc:h2:mem:lab`: database memory biến mất khi JVM đóng, nên test restart sẽ không có ý nghĩa.

### Schema initialization đúng theo hai lượt chạy

| Lượt | Cờ khởi tạo | Kết quả |
| --- | --- | --- |
| Lần đầu, database chưa có bảng | `--spring.sql.init.mode=always` | Chạy schema SQL chính thức từ dependency |
| Các lần tiếp theo, database đã có bảng | `--spring.sql.init.mode=never` | Không tạo lại bảng, giữ messages đã persist |
| Production, database đã vận hành | Flyway/Liquibase hoặc migration tool được quản lý | Có versioned migration, rollback/backup, không chạy “create” lặp lại |

Nếu vô tình chạy script lần đầu trên database đã có bảng, có thể gặp lỗi “table already exists”. **Đừng bật `continue-on-error=true` rồi bỏ qua mọi lỗi SQL trong production.** Hãy phân biệt database mới và schema đã tồn tại bằng migration policy rõ.

## 7. Java application hoàn chỉnh: hai chế độ seed/resume

Đặt file `src/main/java/demo/integration/AggregatorRestartLabApplication.java`.

Ứng dụng có:

- `inputParts` (`DirectChannel`) nhận các message parts.
- Stateless transformer chuẩn hóa payload.
- Aggregator có correlation theo header `batchId`, release khi đủ 3 members, **persist group bằng `JdbcMessageStore`**.
- `completedBatches` (`QueueChannel`) nhận output.
- `ApplicationRunner` thực hiện một trong hai chế độ, xác minh group trước/ sau và in kết quả.
- `main` đóng `ApplicationContext` sau khi `ApplicationRunner` hoàn tất, để có ranh giới process thực.

~~~java
package demo.integration;

import java.util.List;
import java.util.Locale;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
import org.springframework.integration.store.MessageGroupStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class AggregatorRestartLabApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(AggregatorRestartLabApplication.class, args);

        // ApplicationRunner đã chạy trong SpringApplication.run().
        // Đóng context để lượt sau là một process mới thực sự.
        context.close();
    }

    @Bean("inputParts")
    MessageChannel inputParts() {
        return new DirectChannel();
    }

    @Bean("completedBatches")
    PollableChannel completedBatches() {
        return new QueueChannel();
    }

    @Bean
    MessageGroupStore batchGroupStore(DataSource dataSource) {
        JdbcMessageStore store = new JdbcMessageStore(dataSource);

        // Một logical namespace; phải giữ không đổi giữa hai lượt.
        store.setRegion("LAB_BATCH_AGGREGATOR");
        return store;
    }

    @Bean
    IntegrationFlow batchFlow(MessageGroupStore batchGroupStore) {
        return IntegrationFlow.from("inputParts")
                .transform(String.class,
                        value -> value.strip().toUpperCase(Locale.ROOT))
                .aggregate(spec -> spec
                        .correlationStrategy(message ->
                                message.getHeaders().get("batchId"))
                        .releaseStrategy(group -> group.size() >= 3)
                        .messageStore(batchGroupStore)
                        .expireGroupsUponCompletion(true))
                .channel("completedBatches")
                .get();
    }

    @Bean
    ApplicationRunner demo(
            Environment env,
            @Qualifier("inputParts") MessageChannel input,
            @Qualifier("completedBatches") PollableChannel output,
            MessageGroupStore groups) {

        return args -> {
            String mode = env.getProperty("lab.mode", "seed");
            String batchId = env.getProperty("lab.batch-id", "BATCH-101");

            if ("seed".equalsIgnoreCase(mode)) {
                int before = groups.getMessageGroup(batchId).size();

                // Để demo deterministic: batch mới phải chưa có state.
                if (before != 0) {
                    throw new IllegalStateException(
                            "Batch already exists. Choose a new lab.batch-id.");
                }

                sendPart(input, batchId, "P1", "  red  ");
                sendPart(input, batchId, "P2", " blue ");

                int stored = groups.getMessageGroup(batchId).size();
                Message<?> premature = output.receive(0);

                if (stored != 2 || premature != null) {
                    throw new IllegalStateException(
                            "Expected pending group of 2 parts, got "
                                    + stored);
                }

                System.out.println("SEED_OK batch=" + batchId
                        + " durablePending=" + stored);
                System.out.println("STOP the process; run resume next.");
            }
            else if ("resume".equalsIgnoreCase(mode)) {
                int recovered = groups.getMessageGroup(batchId).size();

                if (recovered != 2) {
                    throw new IllegalStateException(
                            "Expected two persisted parts, found "
                                    + recovered + ". Check DB URL and region.");
                }

                System.out.println("RECOVERED batch=" + batchId
                        + " pending=" + recovered);

                // Chỉ gửi part còn thiếu trong process mới.
                sendPart(input, batchId, "P3", " green ");

                Message<?> combined = output.receive(5_000);
                if (combined == null) {
                    throw new IllegalStateException(
                            "No released result after third part");
                }

                System.out.println("RESUME_OK batch=" + batchId
                        + " result=" + combined.getPayload());
            }
            else {
                throw new IllegalArgumentException(
                        "Unknown lab.mode=" + mode);
            }
        };
    }

    private static void sendPart(
            MessageChannel channel, String batchId,
            String partId, String payload) {

        Message<String> message = MessageBuilder
                .withPayload(payload)
                .setHeader("batchId", batchId)
                .setHeader("partId", partId)
                .setHeader("eventId", batchId + ":" + partId)
                .build();

        boolean accepted = channel.send(message);
        if (!accepted) {
            throw new IllegalStateException(
                    "Channel rejected partId=" + partId);
        }
    }
}
~~~

### Tại sao không tự đọc từ H2 rồi tạo group bằng tay?

`JdbcMessageStore` là implementation của store contract; Aggregator được cấu hình `.messageStore(batchGroupStore)` và gọi store khi cần. Khi application mới xử lý P3, framework dùng **cùng correlation key** và backend để truy lại P1/P2.

Ta không viết code thủ công `SELECT * ...`, deserialize payload rồi gọi Aggregator mới; như vậy sẽ bỏ qua một phần contract group lifecycle, metadata, locking và release của Spring Integration.

### Tại sao output QueueChannel có thể nhận ngay trong demo?

`inputParts` là `DirectChannel`: hành trình transformer → aggregator và release được gọi đồng bộ trên sender thread trong ví dụ. Khi đủ P3, output được enqueue vào `completedBatches` trước khi `sendPart()` trả về. `receive(5_000)` có timeout hữu hạn để demo tránh chờ vô thời hạn.

Nếu thay input bằng `ExecutorChannel` hoặc một `QueueChannel` có poller, processing có thể diễn ra bất đồng bộ; cần đợi bằng queue/latch hoặc Awaitility. Khi đó `send()` accepted **không đồng nghĩa group đã persist** tại thời điểm return.

### Những giả định an toàn của ví dụ

- Chỉ chạy **một instance tại một thời điểm** trên H2 file database.
- Không có duplicate parts hoặc late arrivals trong happy path.
- Cùng một `lab.batch-id` và `JdbcMessageStore.region` giữa hai lượt.
- H2 file còn nguyên; không đổi schema/serializer version giữa hai lượt.
- Input không bị retry sau khi message đã được lưu trước đó.
- Consumer đọc output ngay, chưa có durable outbox.
- Dữ liệu là String, headers là String, tương thích với serializer đã chọn.

Ví dụ chứng minh **pending group durability**, không phải complete workflow durability trong mọi tình huống.

## 8. Thực hiện hai lần chạy

Làm trong cùng project và **cùng working directory** chứa file database.

### Lượt 1 — tạo schema và seed hai parts

Dùng Gradle Boot Run trong dự án đã cấu hình:

~~~shell
./gradlew bootRun --args="--lab.mode=seed --lab.batch-id=BATCH-101 --spring.sql.init.mode=always"
~~~

Nếu chạy file JAR đã build, tương đương:

~~~shell
java -jar build/libs/aggregator-restart-lab.jar --lab.mode=seed --lab.batch-id=BATCH-101 --spring.sql.init.mode=always
~~~

Tên JAR là **ví dụ**; dùng tên JAR thực tế của project. `--spring.sql.init.mode=always` **chỉ dùng khi database chưa được tạo bảng**. Không chạy lại câu lệnh này trên cùng database sau khi đã seed thành công.

Kết quả mong đợi:

~~~text
SEED_OK batch=BATCH-101 durablePending=2
STOP the process; run resume next.
~~~

Sau khi ứng dụng đóng, kiểm tra trong working directory có file H2 như `agg-restart-db.mv.db`. Đây là **bằng chứng backend file tồn tại**, nhưng tự nó chưa chứng minh group đúng; assertion `getMessageGroup(batchId).size()==2` đã kiểm tra ở runtime lần đầu.

### Lượt 2 — resume với cùng DB và gửi P3

~~~shell
./gradlew bootRun --args="--lab.mode=resume --lab.batch-id=BATCH-101 --spring.sql.init.mode=never"
~~~

Hoặc:

~~~shell
java -jar build/libs/aggregator-restart-lab.jar --lab.mode=resume --lab.batch-id=BATCH-101 --spring.sql.init.mode=never
~~~

Kỳ vọng:

~~~text
RECOVERED batch=BATCH-101 pending=2
RESUME_OK batch=BATCH-101 result=...
~~~

Payload output mặc định phụ thuộc aggregation processor của Spring Integration version đang dùng. Với demo này, thông thường nó biểu diễn ba payload đã chuẩn hóa, chẳng hạn `[RED, BLUE, GREEN]`. **Đừng hardcode output ordering trong test concurrency** nếu bạn chưa cấu hình ordering/resequencing.

### Trường hợp chạy lại bài thực hành

- Nếu muốn thực hành thêm trên cùng DB, chọn một `batch-id` **mới**.
- Nếu muốn khởi tạo một DB khác, đổi JDBC URL sang tên file mới và chạy bootstrap schema một lần.
- Không xóa file database để “sửa” lỗi production; chỉ reset dữ liệu **demo tách biệt** khi bạn chắc chắn không có state cần giữ.
- Không dùng lại batch key đã completed khi chưa có policy closed-group/dedup: `expireGroupsUponCompletion(true)` có thể xóa group và cho phép late message mở một group mới.

## 9. Kiểm chứng state thật sự được lưu ở đâu

Spring Integration JDBC schema có các bảng dành cho message store/message group. Với file schema chính thức của version dự án, thường có các bảng như `INT_MESSAGE` và `INT_MESSAGE_GROUP`.

Một số câu SQL chỉ để **quan sát**, không sửa dữ liệu:

~~~sql
SELECT COUNT(*) AS message_rows FROM INT_MESSAGE;
SELECT COUNT(*) AS group_rows FROM INT_MESSAGE_GROUP;
~~~

Tùy schema/version/region/group metadata, hai counters không nhất thiết bằng group size hiển thị từ `MessageGroupStore`. Để xác nhận **batch cụ thể**, dùng API:

~~~java
int pending = batchGroupStore
        .getMessageGroup("BATCH-101")
        .size();

System.out.println("Pending parts=" + pending);
~~~

Nếu muốn query chi tiết bằng SQL, hãy kiểm tra **DDL thực tế của dependency đang chạy** trước khi dựa vào tên cột/index; không đặt một query hardcode theo phiên bản khác rồi kết luận dữ liệu bị mất.

### Điều gì phải giữ không đổi giữa hai lượt?

| Thành phần | Phải giống? | Vì sao |
| --- | --- | --- |
| JDBC URL | **Có** | Cùng database file |
| Schema/tên bảng | **Có**, hoặc migration tương thích | Store đọc đúng bản ghi |
| `JdbcMessageStore.region` | **Có** | Namespace logical store |
| `batchId` | **Có** | Correlation group key |
| Serializer/headers format | Có khả năng đọc backwards | Messages cũ phải deserialize |
| Java/SI major version | Nên cố định cho lab | Tránh thay representation giữa seed/resume |
| ReleaseStrategy | Phải compatible với state cũ | Không release sai |
| `MessageHeaders.ID` | Không cần giữ giữa process | Không phải logical group ID |
| H2 process lifetime | **Khác** | Đây chính là điều bài test restart kiểm tra |

**H2 file database không phải lựa chọn shared multi-node production.** Nó thích hợp cho một process/lab. Với nhiều pods, chuyển sang PostgreSQL/MySQL và kiểm tra distributed locks, transaction isolation, schema migration cùng connection pool.

## 10. Phân biệt restart process và restart endpoint

| Thử nghiệm | Có chứng minh persistence không? | Lý do |
| --- | --- | --- |
| `aggregatorEndpoint.stop(); start()` trong cùng JVM | **Không đủ** | Store in-memory vẫn còn trong process |
| Restart Spring `ApplicationContext` mới nhưng giữ static map cũ | Không | Test vẫn phụ thuộc process memory |
| `SpringApplication.run(...)` → close context → `run(...)` với DB file | Có thể | Nếu store/JDBC file được tái tạo đúng |
| Chạy **hai JVM độc lập**, giữ cùng JDBC file | **Mạnh nhất cho lab** | Không có heap/shared singleton giữa runs |
| Kill -9 sau khi seed nhưng trước DB commit | Không đảm bảo | Chưa chắc dữ liệu đã commit |
| Khởi động pod mới với local file ở pod cũ | Thường không | Disk volume không chia sẻ/bền vững |
| Hạ tầng có persistent broker và JDBC store | Có thể | Phải xác nhận ack/transaction/serializer |

Để đánh giá thực tế, phải biết **trạng thái đã commit** của group chứ không chỉ điều gì đã được `send()` trả về.

## 11. Phân tích luồng xử lý và ranh giới transaction

Với `DirectChannel`, các bước chính trong cùng call stack:

~~~text
send(P1)
  -> DirectChannel
  -> stateless transformer
  -> Aggregator
       -> resolve correlationId=BATCH-101
       -> lock group
       -> add P1 vào JdbcMessageStore
       -> releaseStrategy(group) == false
  <- return from send(P1)
~~~

Tương tự P2, group size thành 2. Sau restart:

~~~text
send(P3)
  -> Aggregator
       -> lock group
       -> load group trong JdbcMessageStore
       -> add P3
       -> releaseStrategy(group) == true
       -> create output message
       -> cleanup theo completion policy
  -> completedBatches QueueChannel
  <- return from send(P3)
~~~

`JdbcMessageStore` truy cập JDBC database nên persistence cần đảm bảo JDBC operations commit thành công. Với các transaction management/aggregate endpoint khác nhau, **điểm commit không mặc nhiên trùng** với `MessageChannel.send()` ở async scenarios.

### Cửa sổ lỗi quan trọng

| Crash window | Có thể xảy ra | Điều cần thiết kế |
| --- | --- | --- |
| Trước store add commit | Part chưa durable | Source retry/redelivery |
| Sau store commit nhưng trước source ack | Part có rồi, nguồn có thể giao lại | Dedupe theo logical part ID |
| Sau đủ 3 parts nhưng trước output publish | Group có thể marked complete | Recoverable release/outbox |
| Sau output side effect commit nhưng trước ack | Remote có thể nhận hai lần | Idempotent receiver |
| Sau group expiry nhưng có late part | Có thể tạo group mới | Closed-group marker/late policy |
| Trong schema/serializer upgrade | Old bytes còn trong store | Compatibility/migration test |

Dự án này tập trung vào **cửa sổ pending 2/3 → restart → P3**. Các cửa sổ khác là phần mở rộng cần hiểu để không quảng cáo nhầm khả năng đảm bảo delivery.

## 12. Vì sao `group.size() >= 3` chưa an toàn với duplicate?

Giả sử broker giao lại part P2:

~~~text
P1 -> group size=1
P2 -> group size=2
P2 duplicate -> group size=3 -> release SAI
P3 -> late arrival, group cũ đã hoàn tất
~~~

Mỗi delivery có thể được Spring Messaging tạo thành `Message` mới, với `MessageHeaders.ID` mới. Vì vậy **không thể dùng message instance UUID để dedupe logical event**.

Trong code demo, mỗi message có `partId` và `eventId`, ví dụ:

~~~text
BATCH-101:P1
BATCH-101:P2
BATCH-101:P3
~~~

Những IDs này có thể được dùng để:

- Deduplicate part trước khi aggregator nhận;
- Xác định đã xử lý P1/P2/P3 hay chưa;
- Theo dõi retry/replay;
- Chặn late part mở group mới;
- Đối chiếu output với business DB.

**Dedupe phải đồng bộ với store transaction.** Nếu đánh dấu “đã thấy P2” trong metadata trước khi persist P2 rồi process crash, retry P2 có thể bị từ chối trong khi group chưa chứa nó. Production cần atomic inbox/state machine hoặc transaction phối hợp, không chỉ một in-memory `Set`.

## 13. Nếu output queue vẫn in-memory thì còn lỗ hổng gì?

Ví dụ dùng `QueueChannel` in-memory để người học nhận output. Khi P3 đến:

~~~mermaid
flowchart LR
    A["Group đủ 3 parts"] --> B["Aggregator release"]
    B --> C["Group completion cleanup"]
    B --> D["QueueChannel in-memory"]
    D --> E["ApplicationRunner.receive()"]
    E --> F["Print / downstream"]
~~~

Nếu process crash **sau cleanup group** nhưng **trước khi consumer xử lý output**, cả group state và output trong queue có thể đều không còn. Đây là lý do “lưu aggregator state qua restart” **không đồng nghĩa** bảo toàn mọi output cuối cùng.

Phương án production:

- Persist output vào **outbox** trong cùng transaction/resource khi release được quyết định; publisher riêng gửi outbox và retry với stable ID.
- Hoặc gửi output vào **durable broker/queue** có ack/transaction đúng; xác minh crash windows giữa store và broker.
- Khi không có atomic transaction đa tài nguyên, dùng idempotency + reconciliation, không giả định exactly-once.
- Có metric/outbox pending count và recovery job để không mất kết quả cuối.

Bài này chủ ý tách hai yêu cầu: **durable pending group** (đã minh họa) và **durable completion/output** (cần thiết kế thêm).

## 14. Điểm cần kiểm tra khi chuyển từ H2 sang PostgreSQL

H2 file là một bài test **một JVM tại một thời điểm**. PostgreSQL/DB server dùng trong cluster đòi hỏi thêm:

1. Schema PostgreSQL chính thức hoặc migration DDL tương thích với `spring-integration-jdbc` version.
2. Connection pool và transaction manager cấu hình đúng.
3. Region/namespace key và các indexes phù hợp.
4. `LockRegistry` phù hợp khi nhiều app instances cùng sửa cùng group.
5. Duplicate/late message policy và idempotency key.
6. Timeout, expiry, retention và cleanup jobs.
7. SQL lock timeouts và deadlock handling.
8. Message serializer/schema compatibility qua rolling deployments.
9. Monitoring store read/write duration, pending groups/age, queue lag.
10. Backup/restore và disaster recovery test.

**Đừng dùng chung một H2 file DB cho nhiều pods** như một giải pháp production HA. Với JDBC backend, store state nằm ở DB server; locks và transaction vẫn cần đảm bảo các updates tới một group không xung đột.

## 15. Kiểm thử thực sự bằng hai JVM độc lập

Chạy seed và resume trong **hai process** là cách rõ ràng nhất để chứng minh state không chỉ nằm trong memory. Một JUnit integration test có thể khởi chạy JAR đã build với cùng working directory tạm thời, cùng JDBC URL tương đối và hai bộ arguments.

**Điều kiện:** JAR Spring Boot đã được build bằng quy trình CI/Gradle của dự án trước khi chạy test. Worker STEP 4 chỉ viết kiến thức, **không build**. Test dùng `@TempDir` cho H2 database và redirect stdout/stderr vào file để tránh process bị block vì đầy output pipe.

~~~java
package demo.integration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class AggregatorRestartProcessTest {

    @TempDir
    Path workDir;

    @Test
    void pendingGroupSurvivesTwoSeparateJvms() throws Exception {
        // Thay bằng đường dẫn JAR thực tế đã build của project.
        Path jar = Path.of("build", "libs", "aggregator-restart-lab.jar")
                .toAbsolutePath();

        assertTrue(Files.isRegularFile(jar),
                "Build the Spring Boot executable JAR before this test");

        String first = runJar(jar, workDir, "seed", "BATCH-101",
                "always");
        assertTrue(first.contains(
                "SEED_OK batch=BATCH-101 durablePending=2"));

        // Jvm #1 đã kết thúc hoàn toàn; chỉ còn file database.
        String second = runJar(jar, workDir, "resume", "BATCH-101",
                "never");

        assertTrue(second.contains(
                "RECOVERED batch=BATCH-101 pending=2"));
        assertTrue(second.contains("RESUME_OK batch=BATCH-101"));
    }

    private static String runJar(
            Path jar, Path directory, String mode,
            String batchId, String sqlInitMode) throws Exception {

        Path java = javaExecutable();
        Path log = Files.createTempFile(directory, "run-", ".log");

        List<String> command = new ArrayList<>();
        command.add(java.toString());
        command.add("-jar");
        command.add(jar.toString());
        command.add("--lab.mode=" + mode);
        command.add("--lab.batch-id=" + batchId);
        command.add("--spring.sql.init.mode=" + sqlInitMode);

        ProcessBuilder builder = new ProcessBuilder(command);
        builder.directory(directory.toFile());
        builder.redirectErrorStream(true);
        builder.redirectOutput(log.toFile());

        Process child = builder.start();
        boolean ended;
        try {
            ended = child.waitFor(
                    Duration.ofSeconds(40).toMillis(),
                    TimeUnit.MILLISECONDS);
        }
        catch (InterruptedException ex) {
            child.destroyForcibly();
            Thread.currentThread().interrupt();
            throw ex;
        }

        if (!ended) {
            child.destroyForcibly();
            throw new AssertionError("Child JVM timed out: " + mode);
        }

        String text = Files.readString(log, StandardCharsets.UTF_8);
        assertEquals(0, child.exitValue(),
                "Child JVM failed in " + mode + ":\n" + text);
        return text;
    }

    private static Path javaExecutable() throws IOException {
        boolean windows = System.getProperty("os.name")
                .toLowerCase(java.util.Locale.ROOT)
                .contains("win");

        Path executable = Path.of(
                System.getProperty("java.home"), "bin",
                windows ? "java.exe" : "java");

        if (!Files.isRegularFile(executable)) {
            throw new IOException("Java binary missing: " + executable);
        }
        return executable;
    }
}
~~~

### Vì sao test này có giá trị?

- `@TempDir` cấp database riêng cho mỗi lần chạy test, không ảnh hưởng batch có sẵn.
- JVM #1 hoàn toàn thoát trước khi JVM #2 bắt đầu.
- Process thứ hai không có reference tới bean, `Map` hay `SimpleMessageStore` của JVM đầu.
- Chỉ một điểm chung được giữ có chủ đích: **đường dẫn database file** và `batchId`.
- Test đọc chính output của `ApplicationRunner` để kiểm chứng pending count và kết quả release.
- `ProcessBuilder` không yêu cầu shell; args được truyền riêng, không phụ thuộc vào cách shell escape dấu `;` của JDBC URL.
- Có finite timeout và log hỗ trợ debug nếu context không khởi động.

### Giới hạn của phép thử

Chạy hai JVM nối tiếp bằng **graceful close** là kiểm tra restart persistence. Đây chưa phải **hard crash** test: một JVM bị `kill -9` giữa transaction có thể khác vì chưa commit, và sẽ cần fault injection theo thời điểm. H2 file lock không cho hai JVM đồng thời dùng database theo cách server production; test này cố tình **không chạy song song**.

Thời gian khởi động Spring Boot trên máy CI có thể biến động; chọn timeout có kiểm soát phù hợp hạ tầng. `@TempDir` cleanup diễn ra sau test; log nên được lưu lại dưới test artifacts khi failure trong CI nếu cần điều tra.

## 16. Thiết kế hard-crash test: chèn fault ở điểm có kiểm soát

Graceful restart trả lời “state đã ghi đọc lại được?”. Hard-crash test thêm câu hỏi “nếu process chết ở thời điểm không thuận lợi, state có nhất quán không?”.

Một test nâng cao có thể thêm mode `seed-and-hold` vào ứng dụng:

1. Gửi P1 và P2.
2. Đợi store xác nhận group size=2 sau JDBC transaction commit.
3. In marker `SEED_COMMITTED` rồi giữ process chạy bằng một latch.
4. Test parent quan sát marker qua log/file.
5. Kill child process, đợi process **thực sự thoát**.
6. Start JVM #2, dùng mode resume.
7. Xác minh group size=2, sau P3 có output.
8. Lặp với kill **trước commit** để so sánh: dữ liệu chưa commit không được kỳ vọng tồn tại.

### Vị trí kill hợp lệ

~~~mermaid
sequenceDiagram
    participant SRC as Source
    participant APP as Aggregator JVM
    participant DB as JDBC Store
    participant TEST as Test controller
    SRC->>APP: deliver P2
    APP->>DB: BEGIN + persist P2
    Note over APP,DB: Crash tại đây: commit chưa chắc xong
    DB-->>APP: COMMIT confirmed
    APP-->>TEST: marker SEED_COMMITTED
    TEST-xAPP: hard kill
    TEST->>DB: start JVM mới + read group
    DB-->>TEST: P1 và P2 persisted
~~~

**Không dùng `sleep(200)` để đoán thời điểm commit.** Cần marker được ghi sau khi boundary thực sự hoàn tất; nếu chỉ instrument bên trong method trước transaction interceptor commit thì marker có thể quá sớm.

Ngoài crash test, cần thử mất mạng DB, deadlock, connection pool cạn và data source chuyển sang read-only. Có thể dùng fault injection ở store implementation hoặc database proxy trong test, nhưng không thay đổi source code production bằng sleeps/chờ ngẫu nhiên.

## 17. Kiểm chứng transaction và acknowledgement từ nguồn

Trong demo, `ApplicationRunner` gửi trực tiếp vào `DirectChannel`, nên **không có broker source ack**. Production thường nhận message từ Kafka/JMS/AMQP hoặc adapter tương đương, nơi phải xác định quan hệ giữa **store commit** và **source acknowledgement**.

### Hai thời điểm quan trọng

~~~text
A. Source receive(P2)
B. JdbcMessageStore commit(P2)
C. Source ack(P2)
~~~

Nếu xảy ra crash giữa A và B, source phải có khả năng redelivery. Nếu crash giữa B và C, P2 đã được lưu và source **có thể phát lại P2**. Vì vậy:

- Ack không nên xảy ra trước khi state đã được persist nếu yêu cầu không mất part.
- Redelivery sau commit phải được dedupe bằng stable `partId`.
- `MessageGroupStore` lưu group **không làm source broker tự ack**.
- Transaction manager ở handler phải gắn với đúng thread/resource. `ExecutorChannel` hoặc poller có thể tạo transaction boundary mới.
- Khi dùng hai resources không nằm trong cùng atomic transaction (DB + broker), phải thiết kế at-least-once + idempotency/outbox thay vì suy exactly-once.

### Gợi ý thiết kế từng tầng

| Tầng | Invariant cần có | Test |
| --- | --- | --- |
| Source inbound | Không ack phần chưa durable | Crash trước store commit |
| Preprocessing | Không đổi logical `eventId`/`batchId` | Header mapping test |
| Group persistence | Một part hợp lệ không bị mất | Readback/restart |
| Deduplication | Duplicate không làm tăng distinct count | Gửi lại P2 |
| Release/output | Full batch chỉ tạo một logical result | Crash trước/sau release |
| Downstream | Retry không nhân đôi business effect | Duplicate output event |
| Cleanup/expiry | Group không rò rỉ và late part được xử lý rõ | Timeout/late tests |

## 18. Chống duplicate trong phần thực hành nâng cao

Để nâng demo thành sản phẩm thật, cần xử lý **hai loại duplicate**:

- **Duplicate part:** P2 được gửi hai lần; group size không được tăng lần thứ hai.
- **Duplicate result:** một batch đã release/publish bị retry; downstream không được thực hiện cùng business side effect hai lần.

### Dedupe theo logical partId

Một key đầy đủ có dạng:

~~~text
part-key = tenantId + ":" + batchId + ":" + partId
~~~

Nếu dùng một `ConcurrentMetadataStore` có `putIfAbsent`, ta có thể minh họa claim logic:

~~~java
import org.springframework.integration.metadata.ConcurrentMetadataStore;

final class PartClaim {
    private final ConcurrentMetadataStore store;

    PartClaim(ConcurrentMetadataStore store) {
        this.store = store;
    }

    boolean claim(String batchId, String partId) {
        String key = "part:" + batchId + ":" + partId;
        return store.putIfAbsent(key, "claimed") == null;
    }
}
~~~

**Không dùng đoạn trên làm exactly-once solution.** Nếu claim marker đã ghi nhưng ứng dụng crash **trước khi ghi part vào `JdbcMessageStore`**, retry part sẽ bị từ chối và batch không thể hoàn thành. Cần một trong các cách:

1. Dedupe key và group mutation nằm trong một transaction/resource hỗ trợ atomicity.
2. Inbox state machine có trạng thái `CLAIMED`/`COMPLETED`/`FAILED`, lease và recovery.
3. Partition input theo key + kiểm tra unique part IDs khi release.
4. Reconciliation job so sánh inbox markers và group members khi lỗi.

### Dedupe output

Tạo `batchResultId` ổn định, chẳng hạn `tenant:batchId:version`. Outbox/consumer phía sau dùng ID này để chặn duplicate side effect. `MessageHeaders.ID` có thể đổi khi rebuild/retry, nên không dùng làm logical business key.

## 19. Late arrivals sau completion

Trong ví dụ, `expireGroupsUponCompletion(true)` được bật để dọn group đã release. Điều này **không đảm bảo** late P2/P3 sẽ bị từ chối. Nếu cùng `batchId` được gửi sau completion và group đã bị xóa, framework có thể tạo một group mới cho key đó.

~~~text
Run #2: BATCH-101 P3 -> release -> group cleanup
Run #3: P2 duplicate -> new group? -> pending 1/3
~~~

Một ứng dụng production có thể cần **closed-group marker** bền vững:

| Key | Status | Updated |
| --- | --- | --- |
| `BATCH-101` | `COMPLETED` | thời điểm commit output |
| `BATCH-102` | `EXPIRED` | thời điểm timeout |
| `BATCH-103` | `PROCESSING` | last part accepted |

Incoming part kiểm tra status theo atomic/transactional policy. Với batch đã completed, trả duplicate acknowledgement hoặc đưa vào quarantine; không silently tạo group mới.

**Retention:** closed marker phải giữ lâu bằng hoặc hơn cửa sổ redelivery/replay phù hợp. Marker tồn tại 1 giờ sẽ không chống được duplicate có thể đến sau 7 ngày.

## 20. Group timeout và expiry: đừng để 2/3 parts tồn tại mãi

Demo cố tình giữ pending group không expiry để học restart. Khi production, group `BATCH-999` chỉ có hai parts và P3 không đến sẽ nằm trong DB mãi nếu không có cleanup.

Một chính sách vận hành mẫu:

- **T0:** nhận part đầu tiên, lưu `createdAt` của group.
- **Deadline:** sau 15 phút vẫn thiếu part, đưa group vào expired.
- **Recovery:** emit timeout event chứa `batchId` và **các part IDs đã nhận**, không publish partial result như success nếu business không cho phép.
- **Cleanup:** sau khi timeout event được persist thành công, xóa/compact group theo policy.
- **Late parts:** đi vào DLQ/quarantine hoặc một quy trình reopen explicit.
- **Monitoring:** gauge pending groups và oldest group age.

Các API liên quan trong Spring Integration Aggregator gồm `groupTimeout`, group expiry, `sendPartialResultOnExpiry`, `expireGroupsUponCompletion` và message group processor/expiry callback theo version. Khi áp dụng DSL cụ thể, **đối chiếu đúng overload/API của dependency**; không bật một option chỉ vì tên nghe hợp lý.

### So sánh timeout khác nhau

| Timeout | Phạm vi | Không thay thế |
| --- | --- | --- |
| `receive(timeout)` của QueueChannel | Thời gian consumer đợi output | Group lifetime |
| Poller `receiveTimeout` | Poller chờ một message | Group expiry |
| `groupTimeout` | Một correlation group chờ release | Gateway request timeout |
| HTTP/JMS request timeout | Caller/gateway đợi reply | Bảo đảm group cleanup |
| Transaction timeout | Resource transaction dài tối đa | Business deadline |

Dừng một endpoint không nhất thiết làm group expire. Khi restart, timeout management phải được cấu hình sao cho expired groups được xử lý theo chính sách, kể cả nếu timeout đã qua trong lúc JVM không chạy.

## 21. Scale-out và lock: từ single H2 tới nhiều pods

Khi hai workers có thể cùng thêm parts vào `BATCH-101`:

~~~mermaid
sequenceDiagram
    participant A as Pod A
    participant B as Pod B
    participant L as LockRegistry
    participant D as Shared JDBC store
    A->>L: lock(BATCH-101)
    B->>L: lock(BATCH-101) [wait]
    A->>D: add P1 + evaluate release
    A->>L: unlock
    L-->>B: acquired
    B->>D: add P2 + evaluate release
    B->>L: unlock
~~~

Nếu dùng local `DefaultLockRegistry`, mỗi pod có lock **riêng** và không phối hợp phân tán. Khi shared store multi-node, cần đánh giá `JdbcLockRegistry`, lock repository/schema/lease và transaction isolation phù hợp; hoặc partition messages để mỗi group có một owner tại một thời điểm.

**Một shared `JdbcMessageStore` không đủ để chứng minh concurrency correctness.** Các operations add/release/remove và business output cần được kiểm chứng dưới race conditions, failover, lock lease expiry.

### Hai mô hình scale-out

| Mô hình | Cách hoạt động | Đổi lại |
| --- | --- | --- |
| **Partition theo `batchId`** | Các parts cùng group về một consumer owner | Hot group, rebalance, pending state recovery |
| **Shared store + distributed lock** | Nhiều pods cùng đọc/ghi group, khóa theo correlation key | Lock overhead, DB contention, lease/liveness |
| **External workflow coordinator** | State nằm trong process manager/workflow service | Dễ quản lý saga dài, nhiều thành phần hơn |

Không tăng executor threads vô hạn để giải bài toán một hot correlation key: throughput có thể chỉ tăng lock wait và DB connections.

## 22. Schema migration và serialized messages cũ

`JdbcMessageStore` phải deserialize những messages được ghi bởi ứng dụng đời cũ. Nếu seed với version A rồi resume bằng version B, có nhiều đường lỗi:

- Java class payload không còn tương thích serializer.
- Headers mới được thêm hoặc type thay đổi.
- Schema JDBC được upgrade không tương thích.
- `JdbcMessageStore.region` đổi nên app đọc nhầm logical namespace.
- Strategy release thay đổi, khiến các group cũ không bao giờ complete.
- Correlation key đổi format, P3 vào group khác.
- Stored `replyChannel`/`errorChannel` là reference không thể phục hồi qua JVM như dự kiến.

Trong lab ta dùng **String payload** và headers kiểu String để giảm độ phức tạp. Với domain object phức tạp, nên cân nhắc DTO schema versioned và serialization contract có backward compatibility.

### Expand–migrate–contract

1. **Expand:** triển khai reader mới đọc được cả dữ liệu cũ/mới.
2. **Migrate:** chuyển schema/store/serialized payload hoặc để pending groups hoàn tất dưới reader tương thích.
3. **Contract:** chỉ xóa support cũ sau khi không còn messages cũ.
4. **Rollback:** test cả trường hợp phiên bản cũ cần đọc state được ghi bởi phiên bản mới trong thời gian rolling deploy.

Khi pending group lâu ngày, code mới có thể phải xử lý serialized messages được ghi từ nhiều bản deploy trước. Không “dọn sạch database” để tránh lỗi decode mà không có quyết định mất dữ liệu có kiểm soát.

## 23. Quan sát và đo recovery

Bài thực hành nên có các chỉ số quan sát ngoài hai dòng log seed/resume.

| Metric/signal (gợi ý) | Ý nghĩa | Cách đọc |
| --- | --- | --- |
| `aggregator.group.pending` | Số groups chưa hoàn thành | Monitor tăng lâu |
| `aggregator.group.oldest.age` | Tuổi group pending lâu nhất | Alert missing parts |
| `aggregator.part.accepted` | Số logical parts được persist | Phân biệt send vs store |
| `aggregator.part.duplicate` | Phần trùng bị từ chối | Theo dõi redelivery |
| `aggregator.group.released` | Số nhóm đã đủ điều kiện release | Không đồng nghĩa output committed |
| `aggregator.output.confirmed` | Đã xác nhận outbound business outcome | Theo dõi SLO |
| `aggregator.store.read/write.duration` | Độ trễ JDBC | Bottleneck DB/serialization |
| `aggregator.store.error` | Lỗi persistence | Retry/quarantine |
| `aggregator.lock.wait` | Lock contention | Multi-node hot key |
| `aggregator.group.expired` | Group timeout | Missing/late parts |
| `flow.inflight`, `queue.depth` | Pending work | Backpressure |
| `recovery.time.to.first.batch` | Thời gian sau restart tới output đầu tiên | Khả năng phục hồi |

**Đây là tên instrumentation gợi ý**, không phải Spring Integration tự xuất mọi metric nêu trên. Dùng Micrometer Observation/Timer/MeterRegistry phù hợp và tránh log full payload khi không cần.

### Không tạo high-cardinality metrics

Không dùng `batchId`, `partId`, `eventId` hoặc raw `MessageHistory` làm metric labels. Chúng nên nằm trong structured logs/traces có retention và quyền truy cập. Metric tags nên dùng endpoint, region, outcome, store type, exception class với số giá trị nhỏ.

### Message History và tracing

`MessageHistory` có thể giúp biết P3 đã đi qua transformer và aggregator. Nó không thay được `MessageGroupStore` để biết P1/P2 còn pending hay không. Nếu cần trace xuyên restart, giữ stable `batchId`/`eventId`, trace/log correlations và application-level recovery events.

## 24. Bảng lỗi thường gặp khi chạy bài

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Seed không tạo bảng | Chưa bật `spring.sql.init.mode=always` lần đầu, thiếu dependency JDBC | Kiểm tra schema-locations/classpath |
| `Table already exists` khi seed | Chạy bootstrap script lần thứ hai trên DB cũ | Dùng `mode=never` cho DB đã có bảng |
| Resume báo `pending=0` | Sai working directory, JDBC URL, region hoặc batchId | So sánh chính xác config hai lượt |
| Resume báo `pending=1` | Seed/transaction chưa persist đủ hoặc dùng batch khác | Kiểm tra log/DB và source deliveries |
| Resume fail deserialize | Payload/header serializer khác version | Pin BOM, migration/compatibility |
| Group trước restart size=2 nhưng output không có sau P3 | Release strategy, route/output channel sai | Kiểm tra graph và group state |
| Có output khi mới 2 parts | Duplicate/condition release sai | Log distinct part IDs, validate release |
| P3 vào group mới | Correlation key khác case/type | Chuẩn hóa `batchId`, kiểm tra headers |
| Đổi sang ExecutorChannel rồi test flake | Async send trả về trước khi persist | Await store condition, không sleep cố định |
| H2 file bị khóa | JVM cũ chưa đóng hoặc process khác đang dùng | Đảm bảo chỉ một process tại một thời điểm |
| Group completed rồi late part tạo pending mới | `expireGroupsUponCompletion(true)` xóa group | Closed marker và late-event policy |
| In-memory QueueChannel mất output khi crash | Output không durable | Durable outbox/broker |
| Multi-node duplicate output | Local lock không phối hợp pods | Partition owner/distributed locking + dedupe |
| Pending groups tăng không giảm | Missing parts hoặc không có expiry | Timeout policy, alert, quarantine |
| DB connection pool cạn | Slow JDBC, transaction dài, retries | Pool metrics, timeout, storage tuning |
| Handler throws nhưng source vẫn ack | Error bị recover/nuốt sai boundary | Kiểm tra ack và transactional failure path |

## 25. Fault-injection matrix cho bài thực hành

| Scenario | Thao tác | Kết quả đúng |
| --- | --- | --- |
| Happy path | Seed 2/3, close JVM, resume 1/3 | Có một batch result |
| No persistence | Thay `JdbcMessageStore` bằng `SimpleMessageStore` | Lượt resume không thấy 2 parts |
| Wrong DB | Resume với JDBC URL khác | Pending group không tồn tại |
| Wrong region | Resume với `setRegion` khác | Pending group không được truy thấy |
| Wrong group key | P3 có `batchId=BATCH-102` | `BATCH-101` vẫn 2/3 |
| Duplicate part | Seed P1/P2 rồi gửi lại P2 | Demo có thể release sai; production phải dedupe |
| Late part | Sau result, gửi lại P1 | Không được tạo logical result trùng |
| Crash after commit | Kill sau marker store committed | Restart phải đọc được pending group |
| Crash before commit | Kill trước transaction commit | Source phải redeliver part |
| Output lost window | Kill sau group cleanup trước output persisted | Chứng minh cần outbox/durable queue |
| DB unavailable | Chặn JDBC write | Message không được silently ack thành công |
| Serialized old data | Seed code cũ, resume code mới | Reader mới đọc được hoặc migration rõ |
| Concurrent writers | Hai nodes add cùng group | Không mất part/release trùng |
| Expired group | Không gửi P3 tới deadline | Failure/expiry event, cleanup có kiểm soát |
| Retry storm | DB timeout + handler retries liên tục | Backoff, retry budget, không làm cạn pool |

### Các bước đánh giá test

Không nên chỉ dựa vào log `RESUME_OK`. Hãy đối chiếu đồng thời:

1. JDBC group count và group size tại các mốc;
2. Output message/payload và stable batch result ID;
3. Dedupe markers/inbox nếu có;
4. Source acknowledgements hoặc broker redelivery logs;
5. Transaction commit/rollback;
6. Error/recovery message store;
7. Lock wait và pending group age;
8. Khả năng chạy lại sau deploy version mới.

## 26. Runbook khi ứng dụng restart nhưng batch không hoàn tất

**Triệu chứng:** sau deploy, application running và database healthy, nhưng nhiều batch pending không release.

### Trình tự điều tra

1. Xác định `batchId`, `region`, JDBC URL/schema và code version của instance.
2. Đọc pending group size và tuổi group ở **store thật**, không chỉ memory counter.
3. Kiểm tra các parts có cùng correlation header/key/type hay không.
4. Tìm source event IDs bị thiếu, duplicate và records trong DLQ.
5. Xem release strategy và serializer compatibility sau deploy.
6. Đo JDBC connection pool, lock registry, transaction, deadlocks và timeouts.
7. Xem input channel, poller, executor có running/subscriber/throughput không.
8. Xác định có output đã release nhưng chưa commit/ack hay không.
9. Nếu cần replay missing part, dùng **original stable eventId** và dedupe policy.
10. Chỉ xóa group khi đã có quyết định nghiệp vụ và recovery plan rõ; không delete JDBC rows tùy tiện.

### Khi cần rolling restart

~~~mermaid
flowchart TD
    A["Chuẩn bị deploy"] --> B["Inventory pending groups + schema"]
    B --> C["Pause/drain ingress nếu cần"]
    C --> D["Xác nhận persist + transaction"]
    D --> E["Stop một instance"]
    E --> F["Start version mới, same store + region"]
    F --> G["Check pending group readback"]
    G --> H["Send/receive controlled part"]
    H --> I{"Output đúng + không duplicate?"}
    I -->|Có| J["Resume và theo dõi backlog"]
    I -->|Không| K["Quarantine / rollback / reconcile"]
~~~

**Đừng restart toàn bộ pods đồng thời** nếu group state còn phải migrate và distributed locks/connection pool có giới hạn. Trên H2 local demo, chỉ chạy nối tiếp từng process. Trên production, test riêng multi-node/shared DB.

## 27. Nâng cấp dự án: tách stateless và stateful flow

Ví dụ đang gộp transform và aggregate trong một `IntegrationFlow`; chúng có thể tách thành hai beans để scale/observability độc lập.

Mô hình:

~~~text
inputParts
  -> normalizationFlow (stateless)
  -> normalizedParts channel
  -> aggregationFlow (stateful, JDBC MessageGroupStore)
  -> completedBatches
~~~

Các lợi ích:

- Stateless transformer dễ unit test và scale riêng.
- Stateful aggregator có correlation strategy, group timeout, lock registry rõ.
- Có thể đặt durable broker/queue ở boundary để chống mất input khi stateful backend chậm.
- Metrics phân biệt thời gian normalization, queue wait, store add/release.
- Dễ kiểm thử riêng “input normalized đúng” và “group survive restart”.

### Một skeleton Java DSL

~~~java
@Bean
IntegrationFlow normalizationFlow() {
    return IntegrationFlow.from("inputParts")
            .transform(String.class,
                    s -> s.strip().toUpperCase(Locale.ROOT))
            .channel("normalizedParts")
            .get();
}

@Bean
IntegrationFlow aggregationFlow(MessageGroupStore batchStore) {
    return IntegrationFlow.from("normalizedParts")
            .aggregate(spec -> spec
                    .correlationStrategy(message ->
                            message.getHeaders().get("batchId"))
                    .releaseStrategy(group -> group.size() >= 3)
                    .messageStore(batchStore))
            .channel("completedBatches")
            .get();
}
~~~

Snippet cần bean channel `normalizedParts`, không khai báo đồng thời với `batchFlow()` trong demo ở mục 7. **Chọn một cấu hình** cho dự án, không đăng ký hai competing aggregators trên cùng input. Nếu đổi sang async/persistent channel, sửa test chờ, transaction và ack tương ứng.

## 28. Bài tập bắt buộc và nâng cao

### Phần A — xác nhận persistence

1. **Bootstrap:** chạy seed trên H2 file mới, đảm bảo schema được init đúng một lần.
2. **Readback:** xác nhận group size = 2 và không có output.
3. **Restart:** tắt hẳn JVM, chạy resume với cùng URL/region.
4. **Release:** xác nhận sau P3 có output và group completion được cleanup theo policy.
5. **Negative:** cố tình dùng sai DB URL; giải thích vì sao resume không đọc được group.
6. **In-memory baseline:** thay `JdbcMessageStore` bằng `SimpleMessageStore` rồi thử hai JVM.

### Phần B — correctness

7. **Correlation:** gửi P3 với batchId khác, giải thích state của hai groups.
8. **Duplicate:** gửi P1/P2/P2, ghi lại failure của release theo raw group size.
9. **Dedupe:** thêm stable partId marker/inbox và chứng minh duplicate không làm full count tăng.
10. **Late part:** thử gửi P1 sau release và xây closed-group policy.
11. **Incomplete group:** thêm timeout và failure event mà không publish partial success.
12. **Out-of-order:** gửi P3/P1/P2; kết luận khi nào cần resequencer.
13. **Header mapping:** cho một transformer dựng lại message; kiểm tra `batchId`/`eventId` còn.
14. **Version migration:** seed với schema serializer cũ, resume trên version mới.

### Phần C — reliability và vận hành

15. **Hard crash:** kill process sau store commit rồi resume.
16. **Lost-ack:** giả lập source giao lại P2 sau store commit.
17. **Output crash:** dừng ngay sau group complete trước outbound commit, xác minh outbox cần thiết.
18. **Multi-node:** chuyển sang PostgreSQL và kiểm tra locks/partition ownership.
19. **Contention:** gửi nhiều parts cùng batchId concurrent, đo lock wait và duplicate release.
20. **Metrics:** tạo dashboard group pending, oldest age, completed, expired, duplicate và store latency.
21. **Runbook:** viết plan pause/drain/resume và replay không mất state.
22. **Security:** kiểm tra DB credentials/TLS, serializer untrusted payload và audit access.
23. **Cleanup:** chạy expiry/quarantine có retention; không delete thủ công các rows đang active.
24. **Regression:** kiểm tra hai JVM độc lập trong CI và assert output/log, không `Thread.sleep()` cứng.

### Câu hỏi tự kiểm tra

- Tại sao `SimpleMessageStore` không đạt yêu cầu qua restart?
- Vì sao chỉ dừng rồi start lại endpoint trong cùng JVM chưa chứng minh durability?
- `MessageGroupStore` lưu gì khác với `QueueChannel` message store?
- `correlationStrategy` và `releaseStrategy` quyết định hai việc gì khác nhau?
- Vì sao dùng H2 `file:` chứ không dùng `mem:`?
- Tại sao phải giữ nguyên JDBC URL, region và batchId?
- Vì sao schema initialization chỉ chạy ở lần đầu?
- Khi đủ 3 parts, output QueueChannel in-memory còn lỗ hổng gì?
- Group completed và bị xóa có tự ngăn late P1/P2 không?
- Nếu broker redeliver P2, vì sao group size có thể tạo kết quả sai?
- Tại sao cần idempotent receiver/outbox ngay cả khi JDBC group state durable?
- Multi-node shared group store có cần distributed locking hoặc key ownership không?
- Khi transaction fail giữa add và ack, nguồn phải xử lý ra sao?
- Tại sao metric `aggregator.group.released` chưa chứng minh business side effect commit?

## 29. Checklist hoàn thành dự án

| Hạng mục | Pass khi |
| --- | --- |
| Build dependencies | JDBC + Integration + H2 tương thích BOM |
| DB durable | JDBC URL `file:` ổn định, schema hiện diện |
| Seed | Hai parts cùng batch, group size=2 |
| No premature output | Output channel rỗng sau seed |
| Process restart | JVM thứ nhất dừng hoàn toàn |
| Resume | JVM mới thấy group size=2 trước P3 |
| Release | Có output sau part thứ ba |
| Correlation | P3 sai batchId không release nhầm |
| Serialization | Old messages đọc lại được |
| Cleanup | Group completed được xử lý theo policy |
| Duplicate handling | Có thiết kế/test chặn P2 gửi lặp |
| Late arrivals | Có closed-group/replay policy |
| Timeout | Group thiếu parts không treo mãi |
| Crash/replay | Test transaction/ack/outbox |
| Observability | Pending/expired/completed/duplicate metrics |
| Runbook | Rõ quy trình restart, verify, rollback |
| Technical scope | Chỉ STEP 4 authoring, chưa QA STEP 6 |

## 30. Tổng kết

Bài học bắt đầu bằng ba messages nhưng cố tình **chia làm hai lần chạy JVM**: hai parts tạo một message group chưa hoàn thành, database giữ state trong lúc process không tồn tại, part thứ ba kích hoạt release ở application mới.

Từ kết quả đó, ta có một nguyên tắc thiết kế lớn:

> **Stateful runtime cần một state owner tồn tại độc lập với vòng đời của worker, cùng một hợp đồng xác định correlation, transaction, retry, expiry và output commit.**

`JdbcMessageStore` giải quyết phần **lưu message group**. Để sản xuất an toàn còn cần idempotency đối với duplicate/late messages, outbox/ack cho kết quả cuối, transaction/locking phù hợp, serializer migration, observability và kiểm thử fault injection.

## 31. Tài liệu tham khảo chính thức

- [Spring Integration — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation, release, group timeout, expiry và aggregator lifecycle.
- [Spring Integration — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): `MessageStore`, `MessageGroupStore`, persistence contracts.
- [Spring Integration — JDBC Support](https://docs.spring.io/spring-integration/reference/jdbc.html): cấu hình JDBC, schema và database-specific store behavior.
- [Spring Integration — JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html): JDBC-backed messages/groups và serializer.
- [Spring Integration Javadoc — JdbcMessageStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/jdbc/store/JdbcMessageStore.html): constructor, group persistence và region.
- [Spring Integration — Distributed Lock](https://docs.spring.io/spring-integration/reference/distributed-locks.html): `LockRegistry` và shared state concurrency.
- [Spring Integration — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): deduplication và metadata store.
- [Spring Integration — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html): storing simple idempotency markers.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): `IntegrationFlow`, aggregator spec và channel composition.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html): `DirectChannel`, `QueueChannel`, `ExecutorChannel`.
- [Spring Integration — Poller/Transaction](https://docs.spring.io/spring-integration/reference/polling-consumer.html): polling, transaction và retry boundaries.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): ErrorMessage, errorChannel và recovery.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): resource transaction/rollback.
- [Spring Boot — SQL Database Initialization](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html): `spring.sql.init.mode` và schema scripts.
- [H2 Database — Connection Modes](https://h2database.com/html/features.html): embedded file database, connection URLs và lifecycle.

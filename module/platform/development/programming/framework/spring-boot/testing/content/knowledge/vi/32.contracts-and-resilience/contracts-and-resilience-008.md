# Kiểm thử hoạt động khi database, broker hoặc dịch vụ ngoài tạm gián đoạn

> **Module:** Spring Boot – testing  
> **Nhóm:** Hợp đồng và khả năng phục hồi  
> **Đề bài:** Kiểm thử hoạt động khi database, broker hoặc dịch vụ ngoài tạm gián đoạn  
> **Mục tiêu:** Tạo và kiểm tra failure modes có kiểm soát cho JDBC/database, AMQP broker và HTTP downstream; phân biệt lỗi tạm thời, lỗi vĩnh viễn và kết quả chưa chắc chắn; xác nhận timeout, retries, transaction, outbox, broker confirms, idempotency và phục hồi sau gián đoạn. Ví dụ Java 17, Spring Boot 3.5.0, Maven/JUnit 5, Mockito, PostgreSQL và RabbitMQ Testcontainers, cùng máy chủ HTTP stub trên JDK 17.

## 1. “Tạm gián đoạn” không phải một lỗi duy nhất

Một request của ứng dụng có thể sử dụng ba phụ thuộc:

```text
Client
  │
  ▼
CheckoutWorkflow
  ├── HTTP partner: kiểm tra quyết định / thông tin bên ngoài
  │        └── timeout, 429, 503, connection reset, 400
  ├── PostgreSQL: ghi yêu cầu + outbox trong một transaction
  │        └── mất kết nối, lock timeout, deadlock, read-only, schema error
  └── RabbitMQ: gửi message outbox
           └── broker offline, publish timeout, unroutable, publisher NACK

          Kết quả cần rõ:
  • REJECTED                       → từ chối nghiệp vụ
  • UPSTREAM_UNAVAILABLE          → chưa có thay đổi bền vững
  • DATABASE_UNAVAILABLE          → chưa gửi message
  • PENDING_DELIVERY              → đã lưu outbox, sẽ thử gửi lại
  • BROKER_CONFIRMED              → broker ACK publication, chưa phải consumer xử lý
```

**Mục tiêu của resilience test không phải chứng minh “mọi thứ vẫn thành công dù dependency chết”.** Có những khi yêu cầu đúng là *fail fast*, trả trạng thái retryable, giữ công việc bền vững hoặc không tạo side effect sai.

### 1.1. Các hợp đồng cần xác định trước khi viết test

1. **Không mất dữ liệu:** Nếu đã thông báo accepted, dữ liệu nào phải được persist?
2. **Không tạo tác dụng phụ sai:** Nếu HTTP partner không trả lời, có được ghi order hoặc gửi event không?
3. **Không nhân đôi nghiệp vụ:** Nếu HTTP client retry request sau timeout, cùng idempotency key có tạo hai order không?
4. **Bounded latency:** Khi dependency treo, request phải kết thúc trong một thời gian hữu hạn.
5. **Failure isolation:** Broker chết không làm mất bản ghi đã commit; database chết không dẫn tới publish sự kiện giả.
6. **Recovery:** Sau khi dependency khôi phục, một retry/replay có xử lý backlog đúng không?
7. **Observability:** Metrics/log/trace phân biệt 503, timeout, connection refused, retry exhausted, pending outbox.
8. **Safety:** Test không tắt database/broker thật của người khác, không phá dữ liệu CI job khác.

### 1.2. Phân loại lỗi: khác nhau về khả năng retry

| Triệu chứng | Loại điển hình | Chính sách gợi ý | Cảnh báo |
| --- | --- | --- | --- |
| HTTP 200 + nội dung APPROVED | Thành công | Tiếp tục | Cần validate body/schema |
| HTTP 400/401/403 | Thường vĩnh viễn/authorization | Không retry mù | Không chuyển 401 thành 503 |
| HTTP 404 | Có thể dữ liệu không tồn tại | Theo domain contract | Không cache “not found” vô hạn |
| HTTP 408/429 | Thường tạm thời | Bounded retry, tôn trọng Retry-After nếu có | Không retry thành bão |
| HTTP 500/502/503/504 | Thường tạm thời | Timeout + backoff/jitter/circuit breaker nếu phù hợp | Có thể server đã thực thi POST |
| TCP refused/reset | Transport | Retry có giới hạn với operation an toàn | Endpoint sai cũng cho lỗi tương tự |
| HTTP read timeout | Kết quả **không chắc chắn** | Idempotency key + reconciliation | Server có thể đã xử lý |
| JDBC connection unavailable | Hạ tầng | Fail fast hoặc retry transaction an toàn | Không giả định transaction trước đó chưa commit |
| SQL deadlock/serialization | Có thể thử lại transaction | Retry toàn bộ unit of work, bounded | Cần đủ tính idempotent |
| Unique violation/invalid SQL | Thường lỗi logic/input | Không retry transient policy | Đừng catch tất cả DataAccessException |
| RabbitMQ connection refused | Broker unavailable | Giữ outbox PENDING | Không đánh dấu DELIVERED |
| AMQP unroutable key | Topology/contract lỗi | Publisher return, sửa routing | Confirm ACK vẫn có thể xảy ra |
| Broker publisher confirm timeout | Kết quả chưa chắc chắn | Giữ outbox, replay idempotent | Broker có thể đã nhận message |
| Consumer xử lý rồi crash trước ACK | Redelivery | Idempotent consumer | Không có exactly-once mặc định |

**Từ khóa:** “retryable” là quyết định theo *operation*, không phải một nhãn chung cho mọi HTTP 5xx hay mọi SQL exception. Một read-only GET thường retry an toàn hơn lệnh POST tạo giao dịch không có idempotency key.

## 2. Các tầng test và bằng chứng tương ứng

| Tầng | Công cụ | Kiểm tra tốt | Không chứng minh |
| --- | --- | --- | --- |
| Unit/business | JUnit + Mockito gateways | Trạng thái, nhánh lỗi, no side effects | Network/protocol thật |
| HTTP adapter | Local HttpServer/WireMock/MockWebServer | 200/400/503/read timeout/invalid body | DNS/TLS/proxy production |
| Database integration | PostgreSQL Testcontainers | Transaction, constraint, rollback, SQL | HA failover nếu chỉ 1 node |
| Broker integration | RabbitMQ Testcontainers | Exchange/binding, confirms/returns, routing | Consumer commit nếu không có consumer |
| Network fault | Toxiproxy giữa JVM và container | Latency, connection cut, recovery | Cluster election/quorum đầy đủ |
| Full system | Staging topology giống production | Mất node, retry storms, alerting, failover | Mọi tương lai |
| Contract test | Provider/consumer schema & status policies | Thông điệp/status/body hợp lệ | Dependency luôn available |

Một Mockito test có thể xác nhận “nếu publisher throw thì outbox vẫn PENDING” nhưng **không chứng minh broker đã thật sự mất kết nối**. Một RabbitMQ container test có thể xác nhận confirm/return thật nhưng không chứng minh policy khi node bị tách mạng nếu không fault-inject network.

### 2.1. Negative tests không được nhầm với thiếu infrastructure

Nếu CI không có Docker daemon, một test fail lúc setup không phải “database outage handled PASS”. Nếu `@RabbitAvailable` skip vì broker thiếu, mandatory integration suite không được tự báo xanh. Failure injection phải xuất hiện **sau khi môi trường test đã sẵn sàng**, và test cần xác nhận fault thực sự có hiệu lực.

### 2.2. Baseline trước fault

Một resilience test đúng nên có chuỗi:

```text
[1] Khởi động provider test-only → HEALTHY
[2] Chạy baseline và xác nhận success
[3] Inject fault (HTTP 503/TCP cut/latency)
[4] Xác nhận fault thật sự tác động lên đúng client
[5] Gọi cùng workflow và assert failure contract
[6] Remove fault / restore provider
[7] Replay/retry với idempotency và bounded deadline
[8] Xác nhận data/message đúng, không trùng
[9] Dọn resources thuộc test, không chạm hệ thống khác
```

Đừng chỉ stop container rồi nhìn một exception và tuyên bố hệ thống resilient. Phần quan trọng thường là **hậu quả sau failure** và **khả năng phục hồi**.

## 3. Thiết kế nghiệp vụ: transactional outbox trước khi gửi broker

Một flow nguy hiểm:

```text
BEGIN TRANSACTION
INSERT order
rabbitTemplate.convertAndSend(...)
COMMIT DB
```

Nếu database rollback sau khi broker đã nhận event, consumer có thể thấy “order created” nhưng DB không có order. Nếu DB commit rồi broker offline, event có thể mất. DB transaction và RabbitMQ ACK **không phải một atomic distributed transaction** theo mặc định.

**Pattern an toàn hơn trong nhiều workflow:** Trong cùng **một DB transaction**, ghi business record + outbox PENDING. Sau commit, dispatcher gửi event qua broker. Khi có publisher confirm ACK **và không có mandatory return**, đánh dấu outbox sent. Nếu publish fail/timeout, giữ PENDING để replay.

```text
HTTP partner result
       |
       v
DB transaction:
    INSERT placed_order
    INSERT outbox_event (PENDING)
       |
     COMMIT
       |
       v
Outbox publisher
       ├── broker confirmed + routable → mark SENT
       └── fail/timeout/uncertain         → keep PENDING
                                                   |
                                             retry/replay later
```

**Quan trọng:** Outbox giảm nguy cơ mất event nhưng **không tự bảo đảm exactly-once delivery**. Nếu broker nhận event nhưng ứng dụng crash trước khi mark SENT, replay có thể tạo bản sao. Consumer cần idempotency key, inbox/dedup hoặc unique business constraint.

### 3.1. Phân biệt trạng thái “broker confirmed” và “consumer processed”

- `RabbitTemplate.convertAndSend` không throw: Java send API không báo lỗi ngay, **chưa đủ**.
- Publisher confirm ACK: RabbitMQ broker nhận/chấp nhận publication theo confirm protocol.
- Mandatory return: publication không route được tới queue; có thể xảy ra **cùng** với confirm ACK.
- Message trong queue: đã route đến đích test; không đồng nghĩa consumer đã xử lý.
- Consumer ACK: broker ghi nhận delivery được acknowledge; không đồng nghĩa database downstream commit trừ khi thiết kế bảo đảm.
- Business effect: query database/HTTP side effect có bằng chứng riêng.

Spring AMQP hỗ trợ `CorrelationData.getFuture()` và `CorrelationData.getReturned()` khi bật confirms/returns. Bài mẫu dùng cả hai trước khi chuyển outbox sang SENT.

## 4. PostgreSQL/database outage: cần kiểm tra gì?

### 4.1. Tách “không connect” và “SQL sai”

Một `DataAccessResourceFailureException`, `CannotGetJdbcConnectionException` hay một số `TransientDataAccessException` có thể là dấu hiệu hạ tầng tạm thời. `BadSqlGrammarException`, `DuplicateKeyException` hoặc lỗi validation thường **không** nên retry vô hạn.

Test service nên bắt những nhóm ngoại lệ **cụ thể** mà policy cho phép xử lý tạm thời; các lỗi còn lại nên nổi lên để monitoring và developer sửa. Một `catch (DataAccessException ex) { return 503; }` có thể che bug schema/migration đáng lẽ làm CI fail.

### 4.2. Transaction rollback khi ghi nhiều bảng

Nếu ghi `placed_orders` thành công nhưng ghi `outbox_events` fail, toàn bộ unit of work cần rollback. Có thể test bằng PostgreSQL thật: cố ý tạo unique-key conflict ở outbox, gọi `savePending` qua Spring transactional bean, rồi assert `placed_orders` không còn bản ghi của request đó.

**Không phải** chỉ verify repository `save` được gọi hai lần. Cần query database sau lỗi để xác nhận transaction thật.

### 4.3. Mất kết nối trong transaction: kết quả có thể không chắc chắn

Khi TCP bị cắt lúc client chờ COMMIT, server có thể đã commit nhưng client không nhận response. Retry cùng một non-idempotent INSERT có thể tạo duplicate, hoặc gặp unique conflict. Giải pháp là client-generated request ID, unique constraints, idempotent upsert/lookup và reconciliation.

Test nên mô phỏng tình huống “commit outcome unknown” riêng nếu business yêu cầu; không kết luận từ exception rằng transaction chắc chắn rollback.

### 4.4. Connection pool và recovery

HikariCP có acquisition timeout, connection validation, minimum idle và pool health. Khi Postgres offline, new connection acquire phải fail có thời gian hữu hạn; khi DB trở lại, pool phải tạo/revalidate connections mới phù hợp. Trong fault-injection test, cache connection cũ có thể che network cut một vài calls.

Không mock `JdbcTemplate` rồi gọi đó là network failover test; mock chỉ kiểm tra control flow. Không stop một PostgreSQL container shared giữa parallel test classes hoặc ép `stop/start` rồi assume mapped host port không đổi.

## 5. Broker outage: timeout, confirms và outbox

### 5.1. Vì sao không chỉ assert `convertAndSend` không throw?

AMQP publisher gửi asynchronously. Khi queue binding không có, message có thể bị bỏ nếu chưa bật mandatory returns; khi exchange không tồn tại, channel có thể đóng và báo lỗi bất đồng bộ.

Để test chính xác:

```properties
spring.rabbitmq.publisher-confirm-type=correlated
spring.rabbitmq.publisher-returns=true
spring.rabbitmq.template.mandatory=true
```

Rồi gửi cùng `CorrelationData` và chờ bounded publisher confirm; nếu `getReturned() != null` thì **không được mark SENT**, kể cả confirm.isAck() là true.

### 5.2. Timeout khi chờ confirm là “chưa biết”, không chắc “chưa gửi”

Một publisher confirm future quá hạn có thể do broker unreachable, network jitter, callback delay hoặc broker đã nhận nhưng ACK bị mất. Vì vậy giữ outbox PENDING và cho phép replay với cùng event ID. Consumer dùng inbox/unique constraint để tránh nhân đôi side effects.

### 5.3. Broker trở lại

Một test có giá trị nên xác nhận:

1. Đã có PENDING outbox sau fault.
2. Trong lúc broker “offline” (thật hoặc fault seam), không đánh dấu SENT.
3. Sau restore, dispatcher đọc pending và publish.
4. Message tới đúng queue/exchange, confirm được nhận.
5. Outbox thành SENT.
6. Replay lần nữa không gửi pending item đã marked sent.
7. Nếu duplicate delivery vẫn có thể xảy ra vì crash, consumer xử lý idempotent.

Nếu broker real outage cần dùng Toxiproxy; một unit test với `BrokerGateway` throw chỉ bảo vệ nhánh nghiệp vụ (phần 10).

## 6. HTTP downstream outage: 503, timeout, 4xx và fallback

### 6.1. Chính sách thử nghiệm

Với một HTTP GET kiểm tra quyết định:

- `200 APPROVED`: tiếp tục workflow.
- `200 DECLINED`: từ chối nghiệp vụ, không tạo pending order.
- `503`: dependency tạm unavailable, không ghi DB hoặc gửi event.
- `400`: request sai/contract lỗi, **không** trả trạng thái retryable như 503.
- Read timeout: kết quả chưa chắc chắn; với GET read-only có thể retry nếu hợp đồng cho phép, nhưng phải bounded.
- Body khác `APPROVED/DECLINED`: contract error, không âm thầm coi là approved.
- 429/408: có thể retry theo quota/`Retry-After`/policy nhưng cần budget.
- POST tạo side effect: timeout có thể xảy ra **sau** khi server thực hiện, phải có idempotency key và reconciliation.

### 6.2. Phân biệt timeout settings

- **Connect timeout:** thời gian thiết lập kết nối TCP; không bao quát mọi DNS/TLS/proxy edge case.
- **Read/response timeout:** thời gian chờ network response/data; có thể không phải toàn bộ deadline nếu response nhiều chunk.
- **Total deadline:** ngân sách end-to-end gồm connection, backoff, attempts, queueing và business processing.
- **Retry delay/backoff:** thêm latency, phải nằm trong deadline tổng.
- **Bulkhead:** giới hạn số request đồng thời và số thread/blocking connections.
- **Circuit breaker:** ngăn gọi provider liên tục khi nhiều lỗi, cần thresholds/reset policy được test.

Đặt timeout là **quyết định nghiệp vụ**. Không dùng một giá trị quá nhỏ chỉ để test xanh; trong test có thể sử dụng timeout ngắn hơn production nhưng phải xác minh semantics phù hợp.

## 7. Project thực hành Java 17 + Spring Boot 3.5

Project minh họa **ba gateway**: `PartnerGateway` (HTTP), `OrderStore` (JDBC/Postgres), `BrokerGateway` (RabbitMQ). Workflow có kết quả rõ ràng khi từng dependency fail. Ghi DB + outbox bằng transaction, sau đó publish qua RabbitMQ với confirms/returns. Dispatcher replay PENDING khi broker khôi phục.

Có **14 phương thức JUnit `@Test`**:

- 6 unit tests cho workflow và no-side-effect assertions.
- 4 HTTP adapter tests với JDK `HttpServer` trả 200/400/503 và response chậm gây read timeout thật.
- 4 Postgres/RabbitMQ integration tests: happy path, broker-fault seam→real recovery, unroutable return, atomic DB rollback.

**Phạm vi:** Test broker-fault seam kiểm tra policy khi publish throw; test returns dùng RabbitMQ thật. Tình huống cắt TCP tới **Postgres/RabbitMQ thật** được mô tả trong phần Toxiproxy mở rộng, không tuyên bố đã có full physical outage test trong 14 tests.

### 7.1. Cây thư mục

```text
resilience-test-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/resilience/
    │   │   ├── ResilienceApplication.java
    │   │   ├── Ports.java
    │   │   ├── GatewayFailures.java
    │   │   ├── WorkflowService.java
    │   │   ├── JdbcOrderStore.java
    │   │   ├── HttpPartnerGateway.java
    │   │   ├── RabbitTopology.java
    │   │   ├── RabbitConfirmedPublisher.java
    │   │   └── OutboxDispatcher.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/resilience/
        ├── WorkflowServiceUnitTest.java
        ├── HttpPartnerGatewayTest.java
        └── OutageIntegrationTest.java
```

Tất cả Java files dùng package `com.example.resilience`. `Ports.java` và `GatewayFailures.java` chứa những package-private types, không có public top-level type nên được phép đặt chung trong file.

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>resilience-test-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-amqp</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-testcontainers</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>postgresql</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>rabbitmq</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
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
```

Spring Boot 3.5 parent quản lý Spring Framework/Spring AMQP/Testcontainers phiên bản tương thích. Với Testcontainers 1.x do Boot 3.5 quản lý, imports `org.testcontainers.containers.PostgreSQLContainer` và `org.testcontainers.containers.RabbitMQContainer` là phù hợp. **Không trộn imports/artifacts của Testcontainers 2.x khi chưa nâng BOM đồng bộ**.

### 7.3. `application.properties`

```properties
# src/main/resources/application.properties
spring.sql.init.mode=always

spring.rabbitmq.publisher-confirm-type=correlated
spring.rabbitmq.publisher-returns=true
spring.rabbitmq.template.mandatory=true

# Địa chỉ mặc định chỉ là placeholder an toàn của lab.
# App ngoài môi trường test cần cấu hình URL thật và credentials test-only.
app.partner.base-url=http://127.0.0.1:9
```

Spring Boot mặc định chỉ chạy `schema.sql` với embedded databases; `spring.sql.init.mode=always` khiến schema được khởi tạo trên PostgreSQL container. Dự án thật nên dùng Flyway/Liquibase và migration policy, không dùng `schema.sql` auto-create tùy tiện trên production DB. Port 9 chỉ là local placeholder không có downstream thật; HTTP unit tests truyền endpoint dynamic và full integration dùng mock PartnerGateway.

### 7.4. `schema.sql`

```sql
-- src/main/resources/schema.sql
CREATE TABLE placed_orders (
    order_id VARCHAR(64) PRIMARY KEY
);

CREATE TABLE outbox_events (
    event_id VARCHAR(64) PRIMARY KEY,
    payload VARCHAR(255) NOT NULL,
    sent BOOLEAN NOT NULL DEFAULT FALSE
);
```

Hai tables đặt unique key theo order/event ID. Đây là cơ sở **idempotency** nhưng sample chưa triển khai idempotent request replay hoàn chỉnh: gọi `savePending` trùng ID sẽ báo constraint error. Production cần giải quyết duplicate request bằng lookup/compare payload/upsert có validation và xử lý những trạng thái “đã xử lý” an toàn.

### 7.5. `ResilienceApplication.java`

```java
// src/main/java/com/example/resilience/ResilienceApplication.java
package com.example.resilience;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResilienceApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResilienceApplication.class, args);
    }
}
```

### 7.6. `Ports.java` và kết quả workflow

```java
// src/main/java/com/example/resilience/Ports.java
package com.example.resilience;

import java.util.List;

interface PartnerGateway {
    boolean approved(String orderId);
}

interface OrderStore {
    void savePending(String orderId);
    void markSent(String orderId);
    boolean isPending(String orderId);
    List<String> pendingIds();
}

interface BrokerGateway {
    void publishConfirmed(String orderId);
}

enum Outcome {
    BROKER_CONFIRMED,
    PENDING_DELIVERY,
    UPSTREAM_UNAVAILABLE,
    DATABASE_UNAVAILABLE,
    DECLINED
}
```

Interface seams giúp Mockito inject lỗi đúng thời điểm trong unit tests, trong khi production adapters dùng HTTP/JDBC/Rabbit thật. `BROKER_CONFIRMED` cố ý **không đặt tên `DELIVERED` hoặc `CONSUMED`** vì test không có consumer xử lý business event.

### 7.7. `GatewayFailures.java`

```java
// src/main/java/com/example/resilience/GatewayFailures.java
package com.example.resilience;

class PartnerUnavailableException extends RuntimeException {
    PartnerUnavailableException(String message) {
        super(message);
    }

    PartnerUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}

class BrokerUnavailableException extends RuntimeException {
    BrokerUnavailableException(String message) {
        super(message);
    }

    BrokerUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đây là **application exceptions**, không phải Spring built-in exception types. Ý nghĩa của chúng được adapter định nghĩa: lỗi partner tạm thời, publisher broker không chắc đã route thành công. Một backend HTTP 400 sẽ bị phân loại là lỗi client/permanent ở adapter thay vì ném `PartnerUnavailableException`.

### 7.8. `WorkflowService.java`

```java
// src/main/java/com/example/resilience/WorkflowService.java
package com.example.resilience;

import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.stereotype.Service;

@Service
public class WorkflowService {

    private final PartnerGateway partner;
    private final OrderStore store;
    private final BrokerGateway broker;

    public WorkflowService(
            PartnerGateway partner,
            OrderStore store,
            BrokerGateway broker) {
        this.partner = partner;
        this.store = store;
        this.broker = broker;
    }

    public Outcome submit(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }

        final boolean approved;
        try {
            approved = partner.approved(orderId);
        }
        catch (PartnerUnavailableException ex) {
            return Outcome.UPSTREAM_UNAVAILABLE;
        }

        if (!approved) {
            return Outcome.DECLINED;
        }

        try {
            store.savePending(orderId);
        }
        catch (TransientDataAccessException
                | DataAccessResourceFailureException ex) {
            return Outcome.DATABASE_UNAVAILABLE;
        }

        try {
            broker.publishConfirmed(orderId);
        }
        catch (BrokerUnavailableException ex) {
            return Outcome.PENDING_DELIVERY;
        }

        try {
            store.markSent(orderId);
        }
        catch (TransientDataAccessException
                | DataAccessResourceFailureException ex) {
            // ACK từ broker đã có, nhưng DB mark SENT chưa chắc.
            // Replay có thể phát lại: consumer phải idempotent.
            return Outcome.PENDING_DELIVERY;
        }

        return Outcome.BROKER_CONFIRMED;
    }
}
```

Những điều đáng chú ý:

- **HTTP fail trước DB:** Không gọi store/broker, không tạo outbox pending vô nghĩa.
- **Database fail:** Không publish broker, tránh event cho order chưa lưu.
- **Broker fail/confirm uncertain:** DB đã lưu outbox PENDING, có thể replay sau.
- **Mark SENT fail:** Lời gọi publish đã được broker confirm, nhưng metadata DB có thể chưa commit. Return PENDING conservative; replay phải chịu được duplicate.
- **Non-transient SQL errors:** Ví dụ `DuplicateKeyException` không bị catch; chúng phải hiện ra để test/monitor, không được biến mọi bug thành 503.
- **Transaction boundary:** Method này không `@Transactional` toàn bộ workflow. Transaction nằm ở `OrderStore.savePending` riêng, để commit hoàn tất **trước** khi publisher gửi event.

Một quy trình production phức tạp hơn cần error response mapping, idempotency, request budget, cancellation, metrics và có thể durable dispatcher chuyên dụng. Sample cô lập invariant chính, không tuyên bố đây là full payments implementation.

### 7.9. `JdbcOrderStore.java`

```java
// src/main/java/com/example/resilience/JdbcOrderStore.java
package com.example.resilience;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class JdbcOrderStore implements OrderStore {

    private final JdbcTemplate jdbc;

    public JdbcOrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    @Transactional
    public void savePending(String orderId) {
        jdbc.update(
                "INSERT INTO placed_orders(order_id) VALUES (?)",
                orderId);

        jdbc.update(
                "INSERT INTO outbox_events(event_id, payload, sent) "
                        + "VALUES (?, ?, FALSE)",
                orderId,
                "ORDER:" + orderId);
    }

    @Override
    public void markSent(String orderId) {
        int changed = jdbc.update(
                "UPDATE outbox_events SET sent = TRUE "
                        + "WHERE event_id = ?",
                orderId);

        if (changed != 1) {
            throw new IllegalStateException(
                    "Missing outbox for " + orderId);
        }
    }

    @Override
    public boolean isPending(String orderId) {
        Boolean sent = jdbc.queryForObject(
                "SELECT sent FROM outbox_events "
                        + "WHERE event_id = ?",
                Boolean.class,
                orderId);

        return Boolean.FALSE.equals(sent);
    }

    @Override
    public List<String> pendingIds() {
        return jdbc.queryForList(
                "SELECT event_id FROM outbox_events "
                        + "WHERE sent = FALSE ORDER BY event_id",
                String.class);
    }
}
```

`@Transactional` được Spring áp dụng vì workflow gọi `store.savePending` qua một Spring bean/proxy riêng. Nếu tự gọi `this.savePending()` bên trong cùng bean (self-invocation), transaction advice có thể không áp dụng.

Đảm bảo cả hai `INSERT` dùng **cùng DataSource và transaction manager**. Test rollback ở phần 10 kiểm chứng hành vi thật trên PostgreSQL.

### 7.10. `HttpPartnerGateway.java`

```java
// src/main/java/com/example/resilience/HttpPartnerGateway.java
package com.example.resilience;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

@Component
public class HttpPartnerGateway implements PartnerGateway {

    private final RestClient client;

    public HttpPartnerGateway(
            RestClient.Builder builder,
            @Value("${app.partner.base-url}") String baseUrl) {

        SimpleClientHttpRequestFactory requests =
                new SimpleClientHttpRequestFactory();
        requests.setConnectTimeout(Duration.ofMillis(200));
        requests.setReadTimeout(Duration.ofMillis(250));

        this.client = builder
                .baseUrl(baseUrl)
                .requestFactory(requests)
                .build();
    }

    @Override
    public boolean approved(String orderId) {
        try {
            String value = client.get()
                    .uri("/decision/{id}", orderId)
                    .retrieve()
                    .body(String.class);

            if ("APPROVED".equals(value)) {
                return true;
            }
            if ("DECLINED".equals(value)) {
                return false;
            }
            throw new IllegalStateException(
                    "Unexpected partner response");
        }
        catch (HttpServerErrorException ex) {
            throw new PartnerUnavailableException(
                    "Partner 5xx", ex);
        }
        catch (HttpClientErrorException ex) {
            int status = ex.getStatusCode().value();
            if (status == 408 || status == 429) {
                throw new PartnerUnavailableException(
                        "Partner temporarily throttled", ex);
            }
            throw new IllegalArgumentException(
                    "Partner request rejected", ex);
        }
        catch (ResourceAccessException ex) {
            throw new PartnerUnavailableException(
                    "Partner connection/timeout", ex);
        }
    }
}
```

Cấu hình JDK-based `SimpleClientHttpRequestFactory` để giữ dependencies gọn. Từ Spring Framework 6.1+, `setConnectTimeout(Duration)` và `setReadTimeout(Duration)` có API phù hợp với Boot 3.5. Đây là timeout cho adapter, **không** phải một full end-to-end deadline của toàn workflow.

`RestClient.retrieve()` theo mặc định throw subclass của `RestClientException` cho HTTP 4xx/5xx. Adapter phân biệt 5xx/408/429 (tạm), 400/401/403 và những 4xx khác (permanent), TCP/read timeout (tạm). Contract error (body ngoài APPROVED/DECLINED) được nổi lên thay vì âm thầm “approve”.

### 7.11. `RabbitTopology.java`

```java
// src/main/java/com/example/resilience/RabbitTopology.java
package com.example.resilience;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RabbitTopology {

    public static final String EXCHANGE = "lab.events";
    public static final String QUEUE = "lab.orders";
    public static final String ROUTING_KEY = "order.created";

    @Bean
    DirectExchange eventsExchange() {
        return new DirectExchange(EXCHANGE, false, false);
    }

    @Bean
    Queue ordersQueue() {
        return new Queue(QUEUE, false);
    }

    @Bean
    Binding ordersBinding(
            Queue ordersQueue, DirectExchange eventsExchange) {
        return BindingBuilder.bind(ordersQueue)
                .to(eventsExchange).with(ROUTING_KEY);
    }
}
```

Exchange và queue non-durable chỉ dành cho **ephemeral broker test**. Production cần đánh giá durable queues/exchanges, persistent messages, broker quorum/policies và replay contract. `RabbitAdmin` thường declare `Exchange`/`Queue`/`Binding` beans trên broker khi AMQP connection mở; test integration sẽ dùng broker thật, không chỉ test tên bean.

### 7.12. `RabbitConfirmedPublisher.java`

```java
// src/main/java/com/example/resilience/RabbitConfirmedPublisher.java
package com.example.resilience;

import java.util.UUID;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.springframework.amqp.AmqpException;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class RabbitConfirmedPublisher implements BrokerGateway {

    private final RabbitTemplate template;

    public RabbitConfirmedPublisher(RabbitTemplate template) {
        this.template = template;
    }

    @Override
    public void publishConfirmed(String orderId) {
        publishTo(RabbitTopology.ROUTING_KEY, orderId);
    }

    // Public để integration test được trường hợp unroutable.
    public void publishTo(String routingKey, String orderId) {
        CorrelationData correlation =
                new CorrelationData(UUID.randomUUID().toString());

        try {
            template.convertAndSend(
                    RabbitTopology.EXCHANGE,
                    routingKey,
                    "ORDER:" + orderId,
                    correlation);

            CorrelationData.Confirm confirm =
                    correlation.getFuture()
                            .get(4, TimeUnit.SECONDS);

            if (!confirm.isAck()) {
                throw new BrokerUnavailableException(
                        "Publisher NACK");
            }

            if (correlation.getReturned() != null) {
                throw new BrokerUnavailableException(
                        "Message not routed");
            }
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new BrokerUnavailableException(
                    "Interrupted waiting for confirm", ex);
        }
        catch (ExecutionException | TimeoutException
                | AmqpException ex) {
            throw new BrokerUnavailableException(
                    "Broker publish not confirmed", ex);
        }
    }
}
```

Điểm chính:

- `CorrelationData` có unique ID để liên hệ confirms/returns đúng publication.
- `getFuture().get(4, TimeUnit.SECONDS)` đợi bounded broker ACK/NACK.
- `confirm.isAck()` và `correlation.getReturned()==null` đều phải thỏa.
- Một message unroutable vẫn có thể nhận publisher ACK; không đánh dấu outbox SENT chỉ dựa vào ACK.
- Khi timeout, trạng thái cuối chưa chắc chắn; giữ outbox PENDING.
- Khi thread bị interrupt, code phục hồi interrupted flag.
- Không cần `Thread.sleep` để đợi AMQP callback.
- Quá trình này xác nhận **broker publication**, không chứng minh consumer đã xử lý hay commit DB khác.

### 7.13. `OutboxDispatcher.java`

```java
// src/main/java/com/example/resilience/OutboxDispatcher.java
package com.example.resilience;

import org.springframework.stereotype.Service;

@Service
public class OutboxDispatcher {

    private final OrderStore store;
    private final BrokerGateway broker;

    public OutboxDispatcher(
            OrderStore store, BrokerGateway broker) {
        this.store = store;
        this.broker = broker;
    }

    public int replayPending() {
        int sent = 0;

        for (String id : store.pendingIds()) {
            try {
                broker.publishConfirmed(id);
                store.markSent(id);
                sent++;
            }
            catch (BrokerUnavailableException ex) {
                // Để nguyên PENDING, đợi lần replay sau.
                // Thực tế cần log/metrics, retry budget và alert.
            }
        }

        return sent;
    }
}
```

Dispatcher của demo được gọi **có chủ đích**, chưa gắn `@Scheduled`. Nhờ vậy tests không bị background race. Production cần runner/scheduler được quản lý, retry/backoff, claim/lease theo workers, dead-letter/quarantine nếu poison payload và tránh nhiều dispatchers publish trùng.

Nếu `store.pendingIds()` hoặc `store.markSent()` fail vì database offline, exception được propagate để job biết DB đang lỗi, không bị nuốt thành “replayed 0”. Khi publisher lỗi, giữ PENDING và tiếp tục item khác. Dữ liệu outbox cần có event ID ổn định trong payload/headers cho consumer dedup; demo dùng `ORDER:orderId` và unique outbox event ID.

## 8. Unit tests: sáu failure-policy assertions bằng Mockito

Unit tests không chạy Spring, không mở PostgreSQL/RabbitMQ/HTTP server. Chúng mô phỏng exception tại đúng port và xác minh hậu quả.

### 8.1. `WorkflowServiceUnitTest.java`

```java
// src/test/java/com/example/resilience/WorkflowServiceUnitTest.java
package com.example.resilience;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;

class WorkflowServiceUnitTest {

    PartnerGateway partner;
    OrderStore store;
    BrokerGateway broker;
    WorkflowService workflow;

    @BeforeEach
    void setup() {
        partner = mock(PartnerGateway.class);
        store = mock(OrderStore.class);
        broker = mock(BrokerGateway.class);
        workflow = new WorkflowService(partner, store, broker);
    }

    @Test
    void happyPathPersistsPublishesAndMarksSent() {
        when(partner.approved("o1")).thenReturn(true);

        assertThat(workflow.submit("o1"))
                .isEqualTo(Outcome.BROKER_CONFIRMED);

        verify(store).savePending("o1");
        verify(broker).publishConfirmed("o1");
        verify(store).markSent("o1");
    }

    @Test
    void businessDeclineDoesNotWriteOrPublish() {
        when(partner.approved("o2")).thenReturn(false);

        assertThat(workflow.submit("o2"))
                .isEqualTo(Outcome.DECLINED);

        verifyNoInteractions(store, broker);
    }

    @Test
    void upstreamUnavailableDoesNotCreateOrder() {
        when(partner.approved("o3"))
                .thenThrow(new PartnerUnavailableException("503"));

        assertThat(workflow.submit("o3"))
                .isEqualTo(Outcome.UPSTREAM_UNAVAILABLE);

        verifyNoInteractions(store, broker);
    }

    @Test
    void databaseUnavailablePreventsBrokerPublish() {
        when(partner.approved("o4")).thenReturn(true);
        doThrow(new DataAccessResourceFailureException("db down"))
                .when(store).savePending("o4");

        assertThat(workflow.submit("o4"))
                .isEqualTo(Outcome.DATABASE_UNAVAILABLE);

        verify(broker, never()).publishConfirmed("o4");
        verify(store, never()).markSent("o4");
    }

    @Test
    void brokerUnavailableLeavesOutboxPending() {
        when(partner.approved("o5")).thenReturn(true);
        doThrow(new BrokerUnavailableException("broker down"))
                .when(broker).publishConfirmed("o5");

        assertThat(workflow.submit("o5"))
                .isEqualTo(Outcome.PENDING_DELIVERY);

        verify(store).savePending("o5");
        verify(store, never()).markSent("o5");
    }

    @Test
    void invalidRequestNeverCallsDependencies() {
        assertThatThrownBy(() -> workflow.submit(" "))
                .isInstanceOf(IllegalArgumentException.class);

        verifyNoInteractions(partner, store, broker);
    }
}
```

**6 tests** xác nhận logic/no-side-effect đúng contract. Chúng **không** chứng minh connection timeout hay broker disconnection thực vì gateways đều là mocks. Đó là lý do cần HTTP adapter test và Postgres/Rabbit integration tiếp theo.

Lưu ý Mockito `verifyNoInteractions` có giá trị đặc biệt khi test fault: một trạng thái lỗi có thể đúng nhưng service vẫn vô tình gọi side effect không mong muốn trước khi trả lỗi.

## 9. HTTP test với máy chủ thật trên loopback: 200/400/503/timeout

### 9.1. `HttpPartnerGatewayTest.java`

Java 17 cung cấp `com.sun.net.httpserver.HttpServer` trong JDK. Ta dùng server ephemeral port 0, mỗi test tạo một server mới. Không dùng external network, không cần WireMock dependencies, test đúng `RestClient` đi qua HTTP connection.

```java
// src/test/java/com/example/resilience/HttpPartnerGatewayTest.java
package com.example.resilience;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class HttpPartnerGatewayTest {

    private HttpServer server;
    private HttpPartnerGateway gateway;
    private final AtomicInteger statusCode = new AtomicInteger(200);
    private final AtomicInteger delayMs = new AtomicInteger();

    @BeforeEach
    void start() throws IOException {
        statusCode.set(200);
        delayMs.set(0);

        server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/decision", exchange -> {
            try {
                int delay = delayMs.get();
                if (delay > 0) {
                    Thread.sleep(delay);
                }

                int status = statusCode.get();
                String response =
                        status == 200 ? "APPROVED" : "TEMPORARY";
                byte[] body = response.getBytes(
                        StandardCharsets.UTF_8);

                exchange.sendResponseHeaders(status, body.length);
                try (var output = exchange.getResponseBody()) {
                    output.write(body);
                }
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
            catch (IOException ignored) {
                // Client có thể đã timeout và đóng socket.
            }
            finally {
                exchange.close();
            }
        });

        server.start();
        String baseUrl = "http://127.0.0.1:"
                + server.getAddress().getPort();

        gateway = new HttpPartnerGateway(
                RestClient.builder(), baseUrl);
    }

    @AfterEach
    void stop() {
        server.stop(0);
    }

    @Test
    void okResponseIsApproved() {
        assertThat(gateway.approved("o1")).isTrue();
    }

    @Test
    void http503IsClassifiedAsTemporaryFailure() {
        statusCode.set(503);

        assertThatThrownBy(() -> gateway.approved("o2"))
                .isInstanceOf(PartnerUnavailableException.class);
    }

    @Test
    void http400IsNotMisclassifiedAsTransient() {
        statusCode.set(400);

        assertThatThrownBy(() -> gateway.approved("o3"))
                .isInstanceOf(IllegalArgumentException.class)
                .isNotInstanceOf(
                        PartnerUnavailableException.class);
    }

    @Test
    void slowResponseFailsWithinReadTimeoutBudget() {
        delayMs.set(1_000);

        assertThatThrownBy(() -> gateway.approved("o4"))
                .isInstanceOf(PartnerUnavailableException.class);
    }
}
```

**4 HTTP tests.** `HttpServer` chạy trong process test nhưng request vẫn qua TCP loopback, khác Mockito stub trực tiếp. Test 503/400 xác minh HTTP status mapping, và test delay 1000ms so với read timeout 250ms xác minh adapter phát hiện quá hạn.

**Đừng viết assertion thời gian cứng như “chính xác 250ms”.** HTTP connection establishment, scheduler, GC và CI có biến động; nếu cần SLA, đo elapsed với một ngưỡng hợp lý rộng hơn và test isolation. Server dừng trong `@AfterEach`, không sử dụng cổng cố định hoặc endpoint bên ngoài.

**Giới hạn:** Đây là local HTTP fault test, chưa bao quát DNS failure, TLS handshake, proxy buffering, connection pool exhaustion, HTTP/2 multiplex hoặc distributed tracing. Với API phức tạp, có thể dùng WireMock/MockWebServer/Pact; luôn tách transport tests khỏi business policy tests.

## 10. Integration test với PostgreSQL và RabbitMQ thật

### 10.1. `@ServiceConnection` cho hai containers

Spring Boot 3.5 có `JdbcConnectionDetails` cho `PostgreSQLContainer` và `RabbitConnectionDetails` cho `RabbitMQContainer`. Khi annotate typed static containers bằng `@ServiceConnection`, Spring Boot tự nhận mapped host/port/credentials; không hard-code `localhost:5432` hay `localhost:5672`.

Testcontainers JUnit extension dùng `@Container` để start/stop các containers theo test class. Spring TestContext có thể cache context lâu hơn class; demo sử dụng `@DirtiesContext(AFTER_CLASS)` để tránh reuse context trỏ container đã dừng.

### 10.2. `OutageIntegrationTest.java`

```java
// src/test/java/com/example/resilience/OutageIntegrationTest.java
package com.example.resilience;

import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.BDDMockito.given;

@Testcontainers
@SpringBootTest(properties = {
        "spring.sql.init.mode=always",
        "spring.rabbitmq.publisher-confirm-type=correlated",
        "spring.rabbitmq.publisher-returns=true",
        "spring.rabbitmq.template.mandatory=true"
})
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OutageIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:4.1.8-management");

    @MockitoBean
    PartnerGateway partner;

    @Autowired
    WorkflowService workflow;

    @Autowired
    OrderStore store;

    @Autowired
    OutboxDispatcher dispatcher;

    @Autowired
    RabbitConfirmedPublisher publisher;

    @Autowired
    RabbitTemplate rabbitTemplate;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void cleanTestOwnedRows() {
        jdbc.update("DELETE FROM outbox_events");
        jdbc.update("DELETE FROM placed_orders");
    }

    @Test
    void happyPathCommitsDbAndConfirmsBrokerPublish() {
        String id = "i-" + UUID.randomUUID();
        given(partner.approved(id)).willReturn(true);

        assertThat(workflow.submit(id))
                .isEqualTo(Outcome.BROKER_CONFIRMED);
        assertThat(store.isPending(id)).isFalse();

        assertThat(rabbitTemplate.receiveAndConvert(
                RabbitTopology.QUEUE, 5_000))
                .isEqualTo("ORDER:" + id);
    }

    @Test
    void simulatedBrokerFaultKeepsOutboxForRealReplay() {
        String id = "i-" + UUID.randomUUID();
        given(partner.approved(id)).willReturn(true);

        BrokerGateway offline = orderId -> {
            throw new BrokerUnavailableException(
                    "injected broker outage");
        };

        WorkflowService testWorkflow =
                new WorkflowService(partner, store, offline);

        assertThat(testWorkflow.submit(id))
                .isEqualTo(Outcome.PENDING_DELIVERY);
        assertThat(store.isPending(id)).isTrue();

        // Khi fault được gỡ, dispatcher dùng broker thật.
        assertThat(dispatcher.replayPending()).isEqualTo(1);
        assertThat(store.isPending(id)).isFalse();

        assertThat(rabbitTemplate.receiveAndConvert(
                RabbitTopology.QUEUE, 5_000))
                .isEqualTo("ORDER:" + id);

        assertThat(dispatcher.replayPending()).isZero();
    }

    @Test
    void unroutableMessageCannotBeMarkedAsDelivered() {
        String id = "i-" + UUID.randomUUID();

        assertThatThrownBy(() ->
                publisher.publishTo("no.such.route", id))
                .isInstanceOf(BrokerUnavailableException.class)
                .hasMessage("Message not routed");
    }

    @Test
    void secondInsertFailureRollsBackWholeDbUnit() {
        String id = "i-" + UUID.randomUUID();

        jdbc.update(
                "INSERT INTO outbox_events(event_id,payload,sent) "
                        + "VALUES (?, ?, FALSE)",
                id, "preexisting");

        assertThatThrownBy(() -> store.savePending(id))
                .isInstanceOf(
                        DataIntegrityViolationException.class);

        Integer orders = jdbc.queryForObject(
                "SELECT COUNT(*) FROM placed_orders "
                        + "WHERE order_id = ?",
                Integer.class,
                id);
        assertThat(orders).isZero();
        assertThat(store.isPending(id)).isTrue();
    }
}
```

**4 integration tests — đúng phạm vi:**

- `happyPath...`: Postgres thật ghi order/outbox, RabbitMQ thật ACK publication, message route vào queue, outbox chuyển sent.
- `simulatedBrokerFault...`: dùng một gateway fault-injection throw, **không thực sự cắt network của broker**. Kiểm tra DB outbox giữ PENDING và dispatcher sau đó dùng **broker thật** để gửi lại. Đây là policy+recovery integration, không phải physical outage test.
- `unroutable...`: đi qua **RabbitMQ thật** với routing key không có binding. Publisher confirm ACK có thể có nhưng mandatory return khiến code báo lỗi. Nó không chứng minh RabbitMQ đã offline.
- `secondInsertFailure...`: tạo unique constraint collision tại outbox trên **Postgres thật**, xác nhận rollback của order INSERT trước đó. Nó là **DB transaction failure**, không phải TCP connection loss.

Các tests dùng UUID để tránh trùng business IDs và xóa **test-owned database tables**; chúng không thao tác với database production. Không bật parallel test methods trên cùng context/data nếu chưa có key namespace và cleanup riêng. RabbitMQ queue thuộc container test class; từng test nhận message của mình, không dùng shared production queue.

### 10.3. Vì sao không stop/start containers trong test?

Nếu `postgres.stop()` rồi `postgres.start()` giữa các tests, mapped port/connection details hoặc database data lifecycle có thể thay đổi. Spring ApplicationContext và HikariCP có thể giữ DataSource configuration cũ, gây thất bại do test harness thay vì resilience business logic. Với broker, open AMQP channels có thể chưa phát hiện kết nối chết ngay.

**Muốn mô phỏng mất kết nối mà vẫn giữ server/data/port ổn định hơn, dùng TCP proxy như Toxiproxy** ở phần 11. Không stop database/broker shared trong multi-worker CI.

## 11. Toxiproxy: fault injection trên kết nối DB hoặc broker thật

Testcontainers có Toxiproxy module, cho phép chặn/thêm latency/bandwidth constraints giữa JVM và một container chạy trên Docker network. Điều này gần với “dependency temporarily unreachable” hơn Mockito, vì thật sự đi qua JDBC/AMQP client stack.

### 11.1. Sơ đồ

```text
JUnit JVM
   |
   |  JDBC / AMQP client
   v
Toxiproxy (mapped host port ổn định)
   |
   |  Docker network
   v
PostgreSQL container / RabbitMQ container

Healthy: proxy chuyển tiếp traffic
Fault:   latency toxic / upstream-downstream cut
Recover: loại toxic, traffic trở lại
```

Test nên giữ backend container sống suốt fault; chỉ thay trạng thái network proxy. Điều này bảo toàn database, broker queues và địa chỉ proxy để kiểm tra recovery.

### 11.2. Dependency và version

Với Testcontainers **1.x** do Boot 3.5 BOM quản lý, module có artifact `org.testcontainers:toxiproxy`. Các ví dụ của Testcontainers **2.x** có thể dùng coordinates/Java package mới (như `testcontainers-toxiproxy`). Không trộn module 2.x vào dự án 1.x.

```xml
<!-- Bổ sung khi làm bài mở rộng với Testcontainers 1.x -->
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>toxiproxy</artifactId>
    <scope>test</scope>
</dependency>
```

**Quan trọng:** Các code tiếp theo là **quy trình mở rộng**, không phải source file thứ tư chạy ngay trong project mẫu. Cần đặt postgres, rabbitmq và Toxiproxy trong cùng Docker `Network`, mở proxy port, rồi đưa JDBC/AMQP client đi qua proxy thay vì địa chỉ trực tiếp của `@ServiceConnection`.

### 11.3. Tránh một lỗi rất phổ biến: `@ServiceConnection` đi vòng proxy

Nếu vẫn gắn `@ServiceConnection` trực tiếp lên `PostgreSQLContainer`/`RabbitMQContainer`, Boot có thể tạo `JdbcConnectionDetails`/`RabbitConnectionDetails` trỏ **thẳng** container. Khi đó bật toxic ở Toxiproxy nhưng app vẫn connect trực tiếp, test báo xanh giả.

Trong suite fault-injection riêng:

- Dùng manual `@DynamicPropertySource` để cấp JDBC URL/username/password tới **proxy endpoint**.
- Với AMQP, cấp `spring.rabbitmq.host/port` qua proxy endpoint.
- Đừng để một service connection khác có precedence override những properties đó.
- Phân biệt container network alias ở phía proxy upstream với mapped host/port mà JVM dùng.
- Kiểm tra test baseline đã đi qua proxy bằng toxic tạm thời và một query/publish round trip.
- Một fault injection test phải fail nếu proxy không thật sự nằm trên path.

### 11.4. Kịch bản database network cut

1. Start PostgreSQL container và proxy, khởi tạo schema bằng connection đã đi qua proxy.
2. Baseline: `SELECT 1` và `savePending` với một ID test-only thành công.
3. Inject network cut trên Toxiproxy cả hai directions hoặc add latency vượt JDBC/query timeout.
4. Nếu Hikari giữ connections cũ, đảm bảo fault ảnh hưởng cả đường hiện có; có thể cần soft-evict connections/đợi bounded validation, tùy adapter.
5. Gọi một transaction mới và đợi tối đa deadline đã thiết kế.
6. Assert exception thuộc failure category mong đợi, **không** chuyển thành `BROKER_CONFIRMED`.
7. Assert database không có một nửa order/outbox transaction; với commit outcome unknown, tra lại bằng request ID sau recovery.
8. Remove toxic.
9. Đợi bounded tới khi connection pool/query phục hồi.
10. Retry/reconcile an toàn theo idempotency policy.

### 11.5. Kịch bản RabbitMQ network cut

1. Start RabbitMQ container và proxy, declare exchange/queue/binding.
2. Baseline: publish + confirm + receive trên queue test-only.
3. Inject cut theo upstream/downstream (publisher→broker và broker→publisher).
4. Gọi publish với `CorrelationData` và bounded confirm timeout.
5. Khi failure, không mark outbox SENT; kiểm tra PENDING trong Postgres.
6. Remove toxic, đảm bảo channel/connection factory có đường reconnect phù hợp.
7. Dispatcher replay pending; assert broker message và outbox state.
8. Dùng stable event ID/consumer idempotency để phòng duplicate nếu broker đã nhận lần đầu trước khi confirm bị mất.

**Không assert rằng broker chắc chắn “chưa nhận event” khi confirm timeout.** Hãy assert hệ thống không mất công việc và có thể chịu duplicate.

### 11.6. Ví dụ về fault type (minh họa API)

Testcontainers Toxiproxy docs hỗ trợ tạo `ContainerProxy` và toxic latency/bandwidth:

```java
// PSEUDOCODE/SCHEMATIC, không phải một test class độc lập.
var proxy = toxiproxy.getProxy(postgres, 5432);
proxy.toxics()
        .latency("db-latency", ToxicDirection.DOWNSTREAM, 1_500);

// Gọi JDBC với read/query timeout < latency.
// Assert timeout/failure outcome, giữ data invariants.
// Sau test, remove toxic (hoặc drop proxy) trong finally.
proxy.toxics().get("db-latency").remove();
```

Đối với lỗi “mất kết nối”, có thể dùng downstream/upstream bandwidth toxic với giá trị 0 hoặc connection reset toxic theo Toxiproxy version. Tên methods/enum/constructor và container images phụ thuộc Testcontainers/Toxiproxy versions — cần xem API docs của **đúng** dependency đang pin trước khi chuyển snippet thành source runnable.

**Luôn dọn fault trong finally** và không dùng proxy trỏ database/broker production.

## 12. Retry, exponential backoff, jitter và timeout budget

### 12.1. Không retry vô hạn

Một retry policy có thể diễn đạt:

```text
Total request budget: 2.0s
First attempt timeout: 300ms
Backoff between attempts: 100ms, 200ms (with jitter)
Max attempts: 3
Stop when deadline exhausted
Return explicit UPSTREAM_UNAVAILABLE or PENDING_DELIVERY
```

Đây là **ví dụ thiết kế**, không phải auto-config của project mẫu. Nó không tự bảo đảm mọi tổ hợp thực thi nằm trong 2s; phải tính connection queueing, DNS, TLS, scheduler delays và callback timing.

### 12.2. Retry theo exception/HTTP status

- GET/idempotent operation: retry 408/429/502/503/504 có budget và tôn trọng `Retry-After` nếu trả về.
- POST payment/order creation: chỉ retry nếu có idempotency key và server contract hỗ trợ, hoặc reconciliation sau timeout.
- DB transaction: retry deadlock/serialization có kiểm soát, không retry tất cả SQLExceptions.
- Broker publish: retry qua durable outbox, tránh kết luận lần trước chưa được nhận.
- 400/401/403/validation/schema errors: sửa dữ liệu/quyền, không retry bằng exponential backoff.
- Half-open circuit breaker: test probe/concurrency/metrics riêng nếu có Resilience4j/Spring Cloud CircuitBreaker.

### 12.3. Retry storm và thundering herd

Nếu 1000 requests cùng retry 5 lần khi downstream outage, hệ thống có thể tăng tải đúng lúc provider đang yếu. Cần rate limit, concurrency bulkhead, jitter, retry budget và circuit breaker phù hợp. Test cần đo **call count tối đa**, deadline và behavior khi recovery.

### 12.4. Fallback có ý nghĩa nghiệp vụ

Fallback không phải lúc nào cũng “return success với dữ liệu giả”:

- Read-only catalog: có thể trả stale cached value trong thời gian được phép.
- Payment authorization: không được tự approve khi gateway timeout.
- Publish event: lưu pending outbox, trả trạng thái đang xử lý.
- Inventory: nếu không xác định đủ hàng, có thể đặt trạng thái CHECKING chứ không chắc chắn CONFIRMED.
- Security service: fail closed khi không thể xác minh quyền, không cấp access mặc định.

Test fallback phải xác nhận **không vượt business/security contract**.

## 13. Idempotency, duplicate delivery và database uncertainty

### 13.1. Không có exactly-once end-to-end mặc định

Một flow có các ranh giới:

```text
Client -> HTTP partner -> DB commit -> broker confirm
                              |            |
                   commit outcome?    confirm outcome?
                              |            |
                           uncertain    uncertain
```

Sau timeout, retry có thể tạo duplicate ở một trong hai phía. Outbox giúp tăng reliability nhưng publisher có thể phát lại cùng event.

### 13.2. Kế hoạch kiểm thử idempotency cho production

Một business request nên có stable `requestId`/`eventId` do client/gateway cấp. Các tests cần:

1. Submit cùng id hai lần (cùng payload) → một business record, một logical event.
2. Submit cùng id nhưng payload khác → conflict rõ ràng, không overwrite âm thầm.
3. Broker nhận duplicate event → consumer chỉ commit business effect một lần.
4. Mark SENT lỗi sau publish thành công → replay không gây duplicate effect.
5. Hai dispatchers cùng claim một outbox row → locking/lease/unique logic đúng.
6. Client timeout sau commit → retry tra trạng thái bằng request ID thay vì tạo mới.
7. DLQ/retry exhausted → không xóa mất evidence, có operator remediation path.

**Mẫu runnable bên trên mới dùng unique PK làm rào cuối**, chưa triển khai đầy đủ API/idempotency state machine. Không đánh đồng một unique constraint với complete exactly-once guarantee.

### 13.3. “At-least-once” thường là thực tế khi có replay

Khi outbox replay sau confirm uncertainty, chấp nhận at-least-once publication, yêu cầu idempotent consumer. Không promise exactly-once across database+broker khi không có một coordination/transaction protocol cụ thể và đã được chứng minh.

## 14. Những test dễ xanh giả

| Anti-pattern | Vì sao sai | Thay bằng |
| --- | --- | --- |
| Mockito throw rồi gọi “Postgres outage integration” | Không dùng JDBC/socket thật | Phân loại là unit-policy test; thêm proxy fault test |
| Stop container nhưng context lỗi startup | Fault trước baseline, không kiểm tra recovery | Start healthy rồi inject sau khi app ready |
| Broker `convertAndSend` không throw → DELIVERED | Publication asynchronous | Confirm + returns + nhận queue/consumer riêng |
| Confirm ACK → consumer DB committed | ACK là publisher-level | Consumer business side effect/ACK tests |
| `Thread.sleep(5000)` rồi assert | Flaky/chậm | Bounded condition/latch/await |
| `@Transactional` ở test method sẽ rollback listener | Transaction thread-local | Test DB/schema riêng, cleanup |
| Catch tất cả `DataAccessException` → 503 | Che schema/constraint bug | Catch transient exceptions có chính sách |
| Retry mọi 4xx/5xx | Thổi bão hoặc retry permanent failures | Classify status/code/operation |
| Timeout → chắc server chưa làm gì | Response có thể mất sau commit | Idempotency key/reconciliation |
| Tắt RabbitMQ shared broker trên CI | Ảnh hưởng test khác | Dedicated container/Toxiproxy |
| `@ServiceConnection` direct + fault proxy | App đi vòng proxy | Inject connection details trỏ proxy |
| Fake HTTP server cổng cố định | Port conflict CI | Port 0 và dynamic base URL |
| Không remove toxic sau test | Truyền lỗi sang tests khác | `try/finally` cleanup |
| Đọc queue depth 0 → job đã xử lý | Message delivered/unacked/misrouted | Assert business state |
| Không kiểm tra logs/metrics | Không biết hệ thống fail vì đâu | Error categories + retry/pending metrics |
| Chỉ test failure mà không recovery | Không chứng minh khả năng phục hồi | Baseline→fault→restore→replay |
| Chỉ test recovery mà không duplicate | Có thể phát lại hai lần | Idempotent consumer tests |

## 15. Kế hoạch kiểm thử theo failure matrix

### 15.1. Database

| Fault | Injection | Assertion | Recovery |
| --- | --- | --- | --- |
| Pool acquisition fail | Gateway mock + Testcontainers/Toxiproxy | DATABASE_UNAVAILABLE, broker không được gọi | Reconnect và retry |
| Mid-transaction SQL error | PostgreSQL unique collision | Order insert bị rollback | Sửa data/constraint, không retry mù |
| DB restart/network cut | Toxiproxy/postgres isolate | Timeout bounded, state không bị đánh dấu sai | Pool recover và query theo requestId |
| Commit response lost | Proxy cut gần commit (khó đồng bộ) | Trạng thái uncertain, reconcile trước retry | Query stable id |
| Deadlock/serialization failure | Hai transaction có lock contention | Retry bounded toàn transaction | Không tạo duplicate |
| Read-only replica or permissions | User/DB role test-only | Không ghi sai đích | Route tới writer/permission fix |

### 15.2. RabbitMQ

| Fault | Injection | Assertion | Recovery |
| --- | --- | --- | --- |
| Broker unreachable | BrokerGateway mock/Toxiproxy cut | PENDING, không mark SENT | Replay pending |
| Routing key không có binding | Broker thật + mandatory return | Exception và không mark SENT | Sửa binding rồi replay |
| Exchange không tồn tại | Broker thật, channel error | Không coi send success | Sửa topology |
| Confirm timeout | Proxy/drop downstream ACK | Pending, outcome unknown | Replay idempotent |
| Consumer ném exception | Test listener + DLQ policy | Bounded retries/no endless requeue | DLQ/reprocess |
| Consumer crash sau DB commit trước ACK | Test consumer recovery | Không tạo duplicate business effect | Dedup/inbox |

### 15.3. HTTP outside service

| Fault | Injection | Assertion | Recovery |
| --- | --- | --- | --- |
| HTTP 503 | HttpServer/WireMock | UPSTREAM_UNAVAILABLE, không ghi DB | Retry có giới hạn |
| Read timeout | Response delay > client timeout | Timeout exception được phân loại đúng | Idempotency/retry-safe GET |
| HTTP 400 | Server stub | Permanent error, không retry | Fix request |
| HTTP 429 | Server stub + Retry-After | Rate-limit budget | Thử lại đúng nhịp |
| Invalid JSON/schema | Stub malformed body | Contract error | Versioned contract tests |
| TCP reset | Fault injection TCP | Transport failure, bounded | Reconnect |
| Slow partial response | Streaming/HTTP stub | Read timeout/deadline | Không giữ thread vô hạn |
| Auth failure 401/403 | Provider stub | Fail closed, không fallback unsafe | Re-auth/permission fix |

## 16. Logging, tracing, metrics cho resilience

### 16.1. Tối thiểu nên quan sát gì?

- `dependency=postgres|rabbitmq|partner-http`.
- `outcome=success|temporary_failure|permanent_failure|unknown`.
- `retry.attempt`, `retry.exhausted`, `circuit.state`, `bulkhead.rejected`.
- `outbox.pending.count` và age oldest pending event.
- `publisher.confirm.ack` / `nack` / `returned`.
- HTTP status categories, timeout type, latency histograms.
- Pool idle/active/pending metrics; AMQP connections/channels.
- Number of DLQ items, poison/replay attempts.
- Incident correlation ID/event ID trong logs/traces theo data policy.

Đừng đặt raw user ID/order ID thành **low-cardinality metric tag**, có nguy cơ cardinality explosion. Không ghi credentials, tokens hoặc PII vào test logs. Dùng stable structured error codes thay vì chỉ search string “connection refused”.

### 16.2. Bằng chứng recovery

Một observability assertion nên kiểm tra metrics/log event tương ứng với *tình trạng*:

```text
upstream_down → request rejected as retryable
db_down       → outbox not newly created, broker not called
broker_down   → pending_count increases
broker_up     → replay_count increases, pending_count decreases
replay_twice  → no extra pending work; downstream idempotent
```

Nếu metrics collector tắt trong tests, dùng in-memory `MeterRegistry` hoặc fake tracer; không cần gửi tới production monitoring backend. External metrics exporter end-to-end là test suite riêng.

## 17. CI/CD: tách unit, integration và chaos/fault suites

### 17.1. Chạy project mẫu

```bash
java -version
mvn -version

# Sáu unit tests (không Docker):
mvn -B -ntp -Dtest=WorkflowServiceUnitTest test

# Bốn HTTP tests trên loopback:
mvn -B -ntp -Dtest=HttpPartnerGatewayTest test

# Bốn integration tests: cần Docker daemon:
docker version
docker info
mvn -B -ntp -Dtest=OutageIntegrationTest test

# Toàn bộ 14 methods:
mvn -B -ntp test
```

| Class | Số `@Test` | Dependencies thật |
| --- | ---: | --- |
| WorkflowServiceUnitTest | 6 | Mockito gateways |
| HttpPartnerGatewayTest | 4 | Local JDK HttpServer |
| OutageIntegrationTest | 4 | PostgreSQL + RabbitMQ containers |
| **Tổng** | **14** | Docker cần cho full suite |

Lệnh Maven là hướng dẫn để người học tự chạy source. **Không tuyên bố dự án đã được biên dịch/chạy thành công khi soạn nội dung**; stdout, startup time và Docker mapped ports phụ thuộc môi trường.

### 17.2. GitHub Actions minh họa

```yaml
name: Resilience contract tests

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 25

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Docker preflight
        run: |
          docker version
          docker info --format 'Engine={{.ServerVersion}}'
      - name: Maven tests
        run: mvn -B -ntp test
      - name: Publish Surefire reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: resilience-surefire
          path: target/surefire-reports/
          if-no-files-found: ignore
```

CI này cho unit, loopback HTTP và container integration chạy cùng Maven phase. Suite Toxiproxy nâng cao có thể chạy profile/matrix riêng sau khi đã thêm code fault-injection thực tế.

**Điều kiện môi trường:** Docker-compatible daemon, quyền tạo containers, khả năng pull PostgreSQL/RabbitMQ images, mapped host ports reachable, CPU/RAM/disk đủ cho JVM + Erlang VM + PostgreSQL. Không đặt `localhost:5432` hoặc `localhost:5672` trong integration tests.

### 17.3. Về an toàn runner

- Không mount Docker socket của shared privileged runner vào untrusted PR jobs nếu chưa có isolation policy.
- Không dùng `docker system prune`/`FLUSHALL`/`DROP DATABASE` trên tài nguyên shared.
- Không gọi endpoints production để “đánh thử network outage”.
- Image nên pin version/digest được review; tránh `latest`.
- Không dùng `mvn test || true`; mandatory integration tests thiếu Docker phải báo environment failure.
- Lưu logs/container logs có giới hạn, redaction secrets.
- Distinguish `UNIT PASS`, `HTTP ADAPTER PASS`, `DB/BROKER PASS` và `CHAOS PASS`; một suite không chạy không được tính là pass.

## 18. Bài tập vận dụng

**Bài 1 — HTTP fallback đúng nghĩa.** Đổi HTTP 503 thành 429, đọc `Retry-After`, đặt max attempts=2 cho read-only GET. Assert call count và bounded total deadline; không cho retry 400/401.

**Bài 2 — POST timeout uncertain.** Mô phỏng partner ghi side effect rồi trì hoãn response khiến caller timeout. Thiết kế request id và query status/reconciliation. Không retry POST không idempotent bằng một while-loop mù.

**Bài 3 — Database outage.** Thêm Testcontainers Toxiproxy đúng version 1.x; route JDBC traffic qua proxy. Baseline query, inject cut, assert DB_UNAVAILABLE hoặc exception category đúng, remove fault, đợi pool recover rồi retry.

**Bài 4 — Atomic rollback.** Trong `OutageIntegrationTest`, làm second INSERT fail và kiểm tra first INSERT rollback. Bỏ `@Transactional` khỏi `JdbcOrderStore.savePending` trong nhánh học thử, quan sát sự khác biệt, sau đó khôi phục.

**Bài 5 — Broker routing bug.** Đổi routing key ở `RabbitConfirmedPublisher` thành `no.such.route`. Quan sát publisher confirm/mandatory return; sửa binding và chạy lại.

**Bài 6 — Broker network cut.** Đưa AMQP client qua Toxiproxy, inject downstream cut gây confirm timeout. Assert outbox PENDING; recover rồi replay. Không assert message trước đó chắc chắn chưa tồn tại.

**Bài 7 — Crash after confirm before markSent.** Mô phỏng `OrderStore.markSent` throw sau broker ACK. Replay có thể gửi trùng; tạo một consumer idempotent dựa trên event ID/DB unique key và assert effect chỉ một lần.

**Bài 8 — Test multiple dispatchers.** Cho hai workers cùng quét pending IDs. Thiết kế claim/lease/`SKIP LOCKED` hoặc hàng đợi retry để tránh double work không cần thiết.

**Bài 9 — Deadline budget.** Tạo ba HTTP failures với backoff rồi tính budget tổng. Test result trả đúng trước deadline, không block request thread vô hạn khi provider mất kết nối.

**Bài 10 — Chaos suite riêng.** So sánh unit gateway fault, Testcontainers network-cut và staging multi-node failover. Viết rõ ở mỗi tầng điều gì đã và chưa được chứng minh.

## 19. Câu hỏi tự kiểm tra

**1.** Mockito ném `DataAccessResourceFailureException` có chứng minh Postgres TCP outage không?  
**Đáp án:** Không; nó kiểm tra policy branch. Muốn kiểm tra network phải dùng provider/proxy thật.

**2.** HTTP client timeout có nghĩa downstream chắc chắn chưa xử lý không?  
**Đáp án:** Không. Response có thể bị mất sau khi server đã xử lý; cần idempotency/reconciliation.

**3.** Nếu database không lưu được order, có được publish order-created không?  
**Đáp án:** Thường không, theo contract mẫu; không phát event cho state chưa commit.

**4.** Broker `convertAndSend` không throw có chứng minh queue nhận message không?  
**Đáp án:** Không; cần publisher confirm/return hoặc test routing thực.

**5.** Publisher confirm ACK có chắc consumer đã commit DB không?  
**Đáp án:** Không, ACK này thuộc publication/broker, không phải consumer business processing.

**6.** Có thể nhận confirm ACK mà message không route không?  
**Đáp án:** Có. Mandatory return giúp phát hiện unroutable.

**7.** Outbox PENDING sau timeout có nguy cơ tạo duplicate khi replay không?  
**Đáp án:** Có, vì lần gửi đầu có thể đã tới broker. Consumer phải idempotent.

**8.** `@Transactional` trên test method có làm listener/dispatcher thread rollback theo không?  
**Đáp án:** Không tự động; transaction thường bound theo thread.

**9.** Vì sao dùng Toxiproxy thay vì stop/start một shared container?  
**Đáp án:** Để điều khiển network fault mà giữ provider/data/lifecycle, tránh ảnh hưởng tests khác và mapped port surprises.

**10.** Dùng `@ServiceConnection` trực tiếp khi muốn route traffic qua proxy có rủi ro gì?  
**Đáp án:** App có thể bypass proxy, khiến toxic không tác động và test xanh giả.

**11.** Lỗi 400 nên retry exponential backoff như 503 không?  
**Đáp án:** Thường không; đó là permanent client/contract error, cần policy theo operation.

**12.** Điều gì quan trọng hơn một status `PENDING_DELIVERY`?  
**Đáp án:** Có durable outbox thật, replay được, không làm mất công việc và chịu duplicate an toàn.

**13.** Tại sao phải có baseline trước fault?  
**Đáp án:** Để phân biệt test infrastructure lỗi từ đầu với sự cố được inject có chủ đích.

**14.** Sau khi restore dependency, assert gì?  
**Đáp án:** Bounded recovery, status đúng, data/message consistency, không duplicate business effects.

## 20. Checklist QA cho kiểm thử khả năng phục hồi

- [ ] Failure modes được chia theo database, broker, HTTP; có baseline healthy.
- [ ] Từng fault có injection method và phạm vi bằng chứng rõ (mock vs network).
- [ ] Lỗi tạm thời khác lỗi logic/schema/authorization.
- [ ] HTTP connect/read timeout và total deadline được thiết kế hữu hạn.
- [ ] Retry chỉ áp cho operations an toàn/idempotent; có max attempts/backoff/jitter.
- [ ] 429/503/408 được xử lý khác 400/401/403.
- [ ] Sau upstream failure không tạo order/broker event sai.
- [ ] DB failure không publish event cho state chưa commit.
- [ ] Transaction rollback được kiểm tra trên database thật.
- [ ] Commit outcome uncertain có request ID/reconciliation plan.
- [ ] Outbox business+event cùng transaction.
- [ ] Publisher confirms và mandatory returns được bật và kiểm tra riêng.
- [ ] Broker timeout không được coi là chắc chắn chưa nhận.
- [ ] PENDING outbox được replay sau recovery.
- [ ] Consumer idempotency xử lý redelivery/duplicate.
- [ ] Connection pool recovery được kiểm chứng khi làm physical outage.
- [ ] Context cache/container lifecycle không reuse stopped endpoints.
- [ ] Fault toxic được cleanup trong finally.
- [ ] Không stop shared DB/broker hoặc dùng production credentials.
- [ ] Không dùng fixed sleeps hay timeout vô hạn.
- [ ] CI phân biệt test skipped, environment failed và business resilience pass.
- [ ] Logs/metrics/traces thể hiện reason, pending count, retry exhaustion có redaction.
- [ ] Không claim exactly-once nếu chưa có test/evidence đầy đủ.

## 21. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Testcontainers Service Connections](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): typed PostgreSQLContainer/RabbitMQContainer, `@ServiceConnection` và dynamic connection details.
- [Spring Boot — SQL Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): `spring.sql.init.mode=always` và schema scripts.
- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html): auto-configured `RestClient.Builder`.
- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html): `RestClient` status handlers và error mapping.
- [Spring Framework 6.2 — SimpleClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/http/client/SimpleClientHttpRequestFactory.html): `setConnectTimeout(Duration)`, `setReadTimeout(Duration)`.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, proxy, rollback boundaries.
- [Spring Framework — DataAccessException hierarchy](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/dao/DataAccessException.html): transient vs non-transient database errors.
- [Spring AMQP — RabbitTemplate, Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): `CorrelationData` futures, confirms, returns, mandatory routing.
- [Spring AMQP — CorrelationData Javadoc](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/rabbit/connection/CorrelationData.html): `getFuture()`/`getReturned()`.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): broker confirm và consumer ACK là những hợp đồng riêng.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): poison messages/requeue/DLQ.
- [Testcontainers Java — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): Postgres container test.
- [Testcontainers Java — RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/): broker integration test.
- [Testcontainers Java — Toxiproxy Module](https://java.testcontainers.org/modules/toxiproxy/): inject latency, connection cuts, bandwidth faults.
- [Testcontainers Java — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): container lifecycle.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): isolation/retries/commit behavior.
- [Resilience4j — Documentation](https://resilience4j.readme.io/docs): optional circuit breaker, retry, bulkhead; căn version nếu thêm library.

**Kết luận:** Kiểm thử “vẫn hoạt động khi database, broker hoặc HTTP downstream tạm gián đoạn” phải xác định **bất biến nghiệp vụ** thay vì chỉ assert exception. HTTP lỗi thì fail đúng cách, DB lỗi thì không publish sai, broker lỗi thì công việc đã commit được giữ trong outbox để replay. Mockito bảo vệ nhánh điều khiển, HTTP loopback/real Testcontainers bảo vệ giao thức và transaction, Toxiproxy bảo vệ network failure/recovery. Không coi publisher send không throw là delivered, không coi timeout là chắc chắn chưa commit, và không tuyên bố exactly-once khi vẫn có replay/duplicate risk.
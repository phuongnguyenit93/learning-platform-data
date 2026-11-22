# Retry có giới hạn, backoff và tránh thực thi nghiệp vụ hai lần

## 1. Khi timeout không có nghĩa nghiệp vụ chưa hoàn tất

Trong module **Spring Boot - testing**, nhóm **Hợp đồng và khả năng phục hồi**, một hệ thống thường phải gọi dịch vụ thanh toán, đặt hàng, giữ kho, gửi lệnh qua broker hoặc cập nhật trạng thái tại một service khác. Khi nhận HTTP 503, 429, lỗi kết nối hay timeout, ta muốn **retry** để phục hồi. Nhưng nếu upstream **đã commit** giao dịch trước khi client mất phản hồi, gửi lại lệnh có thể **tính tiền hai lần**.

~~~text
Client                     Payment service                 Database
   | POST /payments, key=K     |                             |
   |------------------------->| INSERT inbox K + charge ---->|
   |                          |<------------ COMMIT ---------|
   |  timeout / mất response  |                             |
   X                          |                             |
   | POST /payments, key=K     |                             |
   |------------------------->| thấy marker K đã commit      |
   |                          | không chạy UPDATE lần hai   |
   |<--------- receipt -------|                             |
~~~

**Giải pháp gồm hai trách nhiệm độc lập**: client retry có giới hạn, có backoff/time budget; còn server phải bảo vệ tác động nghiệp vụ bằng **idempotency key ổn định + lưu trạng thái/unique constraint + transaction**. Không có annotation retry nào tự biến một POST tùy ý thành exactly-once. Một API có idempotency mà retry vô hạn cũng vẫn có thể làm cạn CPU, network hoặc thread pool.

Bài này dùng **Java 17, Spring Boot 3.5.16, Spring Retry 2.x, Spring JDBC, H2 và JUnit Jupiter**. Có dự án runnable với hai lớp giao dịch để giải quyết duplicate-key đúng, test 503 giả, response-lost-after-commit, payload conflict, hết attempts, rollback marker, exponential backoff và fake sleeper **không dùng `Thread.sleep`**. Phần mở rộng nói rõ retry HTTP, `Retry-After`, messaging, outbox, timeout tổng và race giữa nhiều workers.

## 2. Retry, backoff, timeout, idempotency là các lớp khác nhau

| Khái niệm | Công dụng | Không bảo đảm |
| --- | --- | --- |
| Timeout per attempt | Không chờ mãi một socket/DB call | Upstream không commit khi client timeout |
| Retry | Thử lại một operation khi lỗi được phân loại là transient | Operation không nhân side effect |
| Backoff | Giãn các lần retry để upstream có thời gian hồi phục | Upstream sẽ hồi phục ở lần sau |
| Jitter | Random hóa delay để tránh cả nghìn clients retry cùng thời điểm | Đúng business state |
| Retry budget | Giới hạn attempts, thời gian, traffic và concurrency | Tất cả lỗi đều phục hồi |
| Circuit breaker | Tạm ngưng gửi tới dependency lỗi liên tục | Lệnh trước đó đã/không commit |
| Idempotency | Cùng một logical action lặp lại không thay đổi effect sau lần đầu | Giải quyết mất kết nối |
| Transactional outbox | Ghi business state và ý định publish cùng DB commit | Relay/downstream không nhận bản tin trùng |
| Reconciliation | Tra cứu và xử lý trạng thái không biết kết quả | Loại bỏ mọi lỗi nhất thời ngay lập tức |

Với **`maxAttempts=3`**, Spring Retry tính **attempt đầu và tối đa hai lần retry**, không phải ba retry cộng attempt đầu. Vì thế nhiều nhất có **hai lần backoff** trong một operation ba attempts. Nếu operation thành công ở attempt đầu thì không backoff; nếu exception không thuộc loại được retry, không có attempt thứ hai.

### Định nghĩa logical action

Hai request mang cùng JSON nhưng là **hai giao dịch hợp lệ** phải có **hai idempotency keys khác nhau**. Ngược lại cùng một logical transaction được gửi lại phải **giữ nguyên key**, kể cả request được phát qua connection khác hoặc sau restart.

Idempotency key không nên là thread ID, Kafka partition-offset, random value sinh trong retry callback hay tracing correlation ID không có contract. Trong multi-tenant, scope có thể là `(tenantId, operationType, key)`. Bản demo dùng key duy nhất toàn DB để đơn giản.

## 3. Chọn lỗi retry được và không được

| Tín hiệu | Retry? | Lưu ý |
| --- | --- | --- |
| HTTP 503 | Thường có | Có thể có `Retry-After`; bounded, có deadline |
| HTTP 429 | Có điều kiện | Tôn trọng quota/`Retry-After` và budget |
| 502, 504 | Có điều kiện | Request có thể đã đến upstream |
| Read timeout/connection reset | Có điều kiện | **Outcome ambiguous**: phải có idempotency |
| HTTP 500 | Theo contract | Không mặc định mọi 500 là transient |
| HTTP 400 malformed/validation | Không | Gửi lại payload y nguyên không sửa lỗi |
| HTTP 401/403 | Không mù quáng | Cần auth/permission handling |
| HTTP 404 | Theo nghiệp vụ | Có thể eventual consistency, cũng có thể vĩnh viễn |
| HTTP 409 idempotency conflict | Không | Same key + different payload cần điều tra |
| DB deadlock/serialization failure | Có thể | Retry **toàn transaction** sau rollback |
| Broken application invariant | Không | Không retry `NullPointerException`, validation vĩnh viễn |
| Interrupted/cancelled | Không nuốt để retry | Tôn trọng hủy, restore interrupt |
| Kafka/Nack redelivery | Broker-level retry | Consumer vẫn cần dedup |

**Không catch mọi `RuntimeException` rồi bọc thành transient exception.** Như vậy một bug code hoặc business conflict sẽ bị gửi nhiều lần, đôi khi nhân thiệt hại. Chọn một nhóm exception retryable nhỏ và có chủ đích.

### HTTP semantics

RFC 9110 coi GET/HEAD là safe, còn GET/HEAD/PUT/DELETE là idempotent về *intended effect* theo chuẩn HTTP. **POST mặc định không được tự coi idempotent**. Một POST có thể retry an toàn **nếu API hợp đồng hóa tính lũy đẳng**, ví dụ `Idempotency-Key` cộng server-side unique marker; đừng giả chỉ thêm header là đủ khi server không thực thi contract.

## 4. Max attempts, backoff và tổng thời gian

Spring Retry 2.x hỗ trợ:

~~~java
RetryTemplate retry = RetryTemplate.builder()
        .maxAttempts(3)
        .retryOn(TemporaryGatewayFailure.class)
        .exponentialBackoff(100, 2.0, 800)
        .build();
~~~

Đây là snippet; class exception được định nghĩa ở phần code hoàn chỉnh phía dưới. Policy này cho phép ba attempts và delays dự kiến 100 ms, 200 ms nếu cả hai lần đầu đều thất bại. Nếu muốn jitter Spring Retry hỗ trợ overload `exponentialBackoff(100, 2.0, 800, true)`; lựa chọn random không thể assert exact milliseconds giống bản deterministic.

Công thức capped exponential backoff:

\[
d_k = \min(d_{\max}, d_0\cdot m^{k-1})
\]

Với `d0=100 ms`, `m=2`, `dmax=250 ms` và 5 attempts:

| Retry thứ | Delay |
| --- | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 250 ms |
| 4 | 250 ms |

Tổng 800 ms **chỉ là thời gian chờ**, chưa tính thời gian network/DB/GC và chính các attempts. Ba attempts mỗi attempt timeout 3 giây, backoff 100 + 200 ms có thể mất khoảng **9,3 giây** hoặc lâu hơn, không phù hợp nếu SLO request chỉ 2 giây. Cần thiết kế **overall deadline** và giảm per-attempt timeout theo remaining budget.

RetryTemplate chạy đồng bộ theo ví dụ: backoff thực có thể giữ calling thread. Hệ thống high QPS cần cân nhắc concurrency limits, circuit breaker, async/non-blocking retry hoặc queue thay vì để nhiều request threads sleep.

## 5. Retry-After không tự được exponentialBackoff hiểu

HTTP `Retry-After` có thể là số giây hoặc HTTP-date (RFC 9110). Ví dụ:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 3
~~~

HTTP 429 từ RFC 6585 cũng có thể kèm `Retry-After`. Lời gọi `.exponentialBackoff(100,2.0,800)` **không đọc header** và không tự chờ 3 giây. Nếu phải tôn trọng header, adapter/policy cần:

1. Parse đúng định dạng, timezone/date và validate.
2. Quyết định delay có thể kết hợp với exponential policy.
3. Không retry trước yêu cầu của upstream khi contract áp dụng.
4. Không sleep vô hạn theo header không tin cậy; giới hạn theo SLO/deadline.
5. Nếu cần chờ lâu hơn deadline, **không gửi retry**, trả trạng thái/đưa vào queue sau.
6. Ghi metric rate limit và retry exhaustion, không log secrets.

Tương tự, chỉ tăng delay từ 100 ms lên 10 giây không sửa một request **không idempotent**. Idempotency quyết định an toàn nghiệp vụ, còn backoff quyết định lịch thử lại.

## 6. Nested retries nhân số attempts

Một Spring service có outer retry 3 attempts, bên trong HTTP SDK tự retry 3 attempts và reverse proxy còn thử 2 lần có thể phát **3 × 3 × 2 = 18** sends tới upstream, tùy cấu hình/điểm lỗi.

~~~text
Outer Spring Retry maxAttempts = 3
   HTTP SDK implicit attempts = 3
      Proxy retry attempts = 2
          -> worst-case 18 physical requests
~~~

Đây là **mức tối đa lý thuyết**, không khẳng định mọi request thực tế bị gửi 18 lần. Kiểm tra các tầng retry của network client, gateway, load balancer, database driver, Kafka producer và queue worker. Retry amplification có thể làm outage thành bão traffic. Metric phải phân biệt **logical operations, client attempts và physical sends**.

## 7. Kiến trúc demo và ranh giới transaction

Mẫu project chia trách nhiệm:

~~~text
PaymentCommand(key=K, accountId=A, amountCents=250)
      |
      v
RetryingPaymentClient
    RetryTemplate(maxAttempts=3, retryOn transient)
      |
      v
ChargeGateway           (HTTP adapter trong production)
      |
      v
PaymentProcessor
      |
      +--> PaymentWriteTransaction.applyOnce()
      |        @Transactional
      |        INSERT payment_inbox (unique key K)
      |        UPDATE account_balances +250
      |        COMMIT
      |
      +--> Nếu duplicate-key exception:
               transaction lỗi đã ROLLBACK
               SELECT committed marker K
               same account/amount? -> trả receipt cũ
               changed payload?    -> conflict, no retry
~~~

Trong **bộ test chạy được**, gateway là Java lambda có thể ném lỗi trước/sau `PaymentProcessor`. Nó mô phỏng mất phản hồi nhưng **không mở HTTP socket**; vì vậy được gọi là test boundary + DB integration, không phải HTTP end-to-end test. Phần cuối nêu cách mở rộng với `RestClient` và WireMock.

**Điểm chủ đạo:** retry ở phía gọi, transaction/idempotency ở service thực sự có quyền thay đổi business state. Client không thể dùng Map in-memory để đảm bảo toàn hệ thống không charge trùng vì app có thể restart hoặc chạy nhiều pods.

## 8. Cấu trúc tệp Java 17 + Spring Boot 3.5

~~~text
settings.gradle
build.gradle
src/main/java/com/example/retrysafety/
  RetrySafetyApplication.java
  PaymentCommand.java
  PaymentReceipt.java
  TemporaryGatewayFailure.java
  IdempotencyConflictException.java
  ChargeGateway.java
  PaymentWriteTransaction.java
  PaymentProcessor.java
  RetryingPaymentClient.java
  RetryConfiguration.java
src/main/resources/
  application.properties
  schema.sql
src/test/java/com/example/retrysafety/
  RetryingPaymentClientTest.java
  BackoffPolicyTest.java
~~~

Các Java classes có package `com.example.retrysafety`. Bài được thiết kế để chạy offline khi dependencies đã tải, không cần Docker/Kafka/API key. H2 giúp test unique key/transaction cơ bản, nhưng không thay PostgreSQL/MySQL Testcontainers cho lock/race semantics production.

**`settings.gradle`:**

~~~groovy
rootProject.name = 'retry-safety-demo'
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.retry:spring-retry'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
}
~~~

Spring Boot 3.5 BOM quản lý versions của Spring Retry và H2. Mẫu sử dụng **`RetryTemplate` programmatically**, nên không cần AOP dependency để kích hoạt `@Retryable`. Khi đổi sang annotation-based retry cần chú ý Spring AOP và `@EnableRetry`.

## 9. Schema: unique marker phải commit cùng business effect

**`src/main/resources/schema.sql`:**

~~~sql
CREATE TABLE IF NOT EXISTS account_balances (
    account_id VARCHAR(80) PRIMARY KEY,
    balance_cents BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS payment_inbox (
    idempotency_key VARCHAR(100) PRIMARY KEY,
    account_id VARCHAR(80) NOT NULL,
    amount_cents BIGINT NOT NULL
);
~~~

**`src/main/resources/application.properties`:**

~~~properties
spring.datasource.url=jdbc:h2:mem:retry_safety;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql
spring.datasource.hikari.maximum-pool-size=6
~~~

Unique key ở DB giúp hai workers không thể commit cùng marker `K`. Nhưng **chỉ unique marker không đủ** nếu `INSERT marker` ở transaction riêng và `UPDATE balance` ở transaction khác: marker có thể commit trước, business update rollback, mọi replay sau đó bị skip sai.

Bản demo lưu account/amount với marker để phân biệt same key + same payload với same key + **changed business payload**. Production nên thêm tenant, currency, operation type, canonical payload digest, response, status, timestamps và retention policy.

## 10. Application, PaymentCommand và PaymentReceipt

**`src/main/java/com/example/retrysafety/RetrySafetyApplication.java`:**

~~~java
package com.example.retrysafety;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RetrySafetyApplication {
    public static void main(String[] args) {
        SpringApplication.run(RetrySafetyApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/retrysafety/PaymentCommand.java`:**

~~~java
package com.example.retrysafety;

public record PaymentCommand(
        String idempotencyKey,
        String accountId,
        long amountCents
) {
}
~~~

**`src/main/java/com/example/retrysafety/PaymentReceipt.java`:**

~~~java
package com.example.retrysafety;

public record PaymentReceipt(
        String idempotencyKey,
        String accountId,
        long amountCents
) {
}
~~~

Một command được tạo **trước** vòng retry, idempotency key là đại diện cho **một ý định thanh toán logic**. Không đặt `UUID.randomUUID()` trong callback của `RetryTemplate`. Với money, `long cents` tránh lỗi floating-point của `double`; production vẫn cần xử lý overflow, currency, amount limits, account ownership và settlement semantics.

## 11. Transient exception và idempotency conflict

**`src/main/java/com/example/retrysafety/TemporaryGatewayFailure.java`:**

~~~java
package com.example.retrysafety;

public final class TemporaryGatewayFailure
        extends RuntimeException {

    public TemporaryGatewayFailure(String message) {
        super(message);
    }

    public TemporaryGatewayFailure(
            String message,
            Throwable cause
    ) {
        super(message, cause);
    }
}
~~~

**`src/main/java/com/example/retrysafety/IdempotencyConflictException.java`:**

~~~java
package com.example.retrysafety;

public final class IdempotencyConflictException
        extends RuntimeException {

    public IdempotencyConflictException(String message) {
        super(message);
    }
}
~~~

`TemporaryGatewayFailure` biểu diễn transient failure mà retry policy cho phép; `IdempotencyConflictException` biểu diễn **same key nhưng nội dung mâu thuẫn**. Hai loại lỗi cố tình không cùng retryable superclass.

Khi HTTP adapter gặp đúng HTTP 429/503, nó có thể map thành `TemporaryGatewayFailure`. Không wrap mọi lỗi 4xx/5xx hay `RuntimeException` thành transient vì lỗi hợp đồng/authorization/validation không được giải quyết bằng gửi lại y nguyên.

## 12. Transaction: INSERT marker trước rồi atomic UPDATE

**`src/main/java/com/example/retrysafety/PaymentWriteTransaction.java`:**

~~~java
package com.example.retrysafety;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentWriteTransaction {

    private final JdbcTemplate jdbc;

    public PaymentWriteTransaction(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public PaymentReceipt applyOnce(PaymentCommand command) {
        if (command == null
                || command.idempotencyKey() == null
                || command.idempotencyKey().isBlank()
                || command.accountId() == null
                || command.accountId().isBlank()
                || command.amountCents() <= 0) {
            throw new IllegalArgumentException(
                    "Invalid payment command"
            );
        }

        jdbc.update(
                """
                INSERT INTO payment_inbox
                  (idempotency_key, account_id, amount_cents)
                VALUES (?, ?, ?)
                """,
                command.idempotencyKey(),
                command.accountId(),
                command.amountCents()
        );

        int updated = jdbc.update(
                """
                UPDATE account_balances
                   SET balance_cents = balance_cents + ?
                 WHERE account_id = ?
                """,
                command.amountCents(),
                command.accountId()
        );

        if (updated != 1) {
            throw new IllegalStateException(
                    "Unknown account: " + command.accountId()
            );
        }

        return new PaymentReceipt(
                command.idempotencyKey(),
                command.accountId(),
                command.amountCents()
        );
    }
}
~~~

**Một database transaction bao trùm cả marker và effect.** Nếu account chưa tồn tại, exception unchecked khiến Spring rollback cả marker; replay sau khi khắc phục được phép áp dụng. Nếu marker đã commit, unique constraint từ chối insert trước khi số dư được cộng lần nữa.

`UPDATE balance_cents = balance_cents + ?` là atomic SQL increment, tránh lost update kiểu read-modify-write trên Java khi hai events **khác key** chạy cùng lúc. H2 không chứng minh đầy đủ khóa và isolation của DB production.

**Sai lầm lớn:** bắt `DuplicateKeyException` **ngay trong** method `@Transactional` rồi tiếp tục query/update. Với PostgreSQL, unique violation làm transaction rơi vào trạng thái aborted. Hãy cho exception đi qua transaction interceptor để rollback trước, rồi phân loại duplicate tại bean bên ngoài.

## 13. PaymentProcessor: duplicate đã rollback và so payload

**`src/main/java/com/example/retrysafety/PaymentProcessor.java`:**

~~~java
package com.example.retrysafety;

import java.util.List;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class PaymentProcessor {

    private final PaymentWriteTransaction transactions;
    private final JdbcTemplate jdbc;

    public PaymentProcessor(
            PaymentWriteTransaction transactions,
            JdbcTemplate jdbc
    ) {
        this.transactions = transactions;
        this.jdbc = jdbc;
    }

    public PaymentReceipt charge(PaymentCommand command) {
        try {
            return transactions.applyOnce(command);
        } catch (DuplicateKeyException duplicate) {
            // Transaction applyOnce đã ROLLBACK.
            List<PaymentReceipt> existing = jdbc.query(
                    """
                    SELECT idempotency_key, account_id, amount_cents
                    FROM payment_inbox
                    WHERE idempotency_key = ?
                    """,
                    (rs, rowNum) -> new PaymentReceipt(
                            rs.getString("idempotency_key"),
                            rs.getString("account_id"),
                            rs.getLong("amount_cents")
                    ),
                    command.idempotencyKey()
            );

            if (existing.size() != 1) {
                throw new IdempotencyConflictException(
                        "Idempotency key not resolvable: "
                                + command.idempotencyKey()
                );
            }

            PaymentReceipt receipt = existing.get(0);
            if (!receipt.accountId().equals(command.accountId())
                    || receipt.amountCents()
                            != command.amountCents()) {
                throw new IdempotencyConflictException(
                        "Conflicting idempotency key: "
                                + command.idempotencyKey()
                );
            }

            return receipt;
        }
    }
}
~~~

Mẫu này bảo đảm:

1. **New key** → transaction ghi marker + cập nhật số dư rồi trả receipt.
2. **Existing key + same payload** → duplicate insert rollback, lookup marker đã commit, trả receipt cũ, **không UPDATE lần nữa**.
3. **Existing key + different payload** → throw `IdempotencyConflictException`, không retry.
4. **Business update fail trước commit** → marker rollback; lần xử lý sau không bị skip sai.

`transactions.applyOnce` là lời gọi từ một Spring bean sang **bean khác**, đi qua `@Transactional` proxy. Nếu viết `this.applyOnce(...)` cùng object, self-invocation có thể làm mất transaction. Nếu marker service dùng `REQUIRES_NEW` mà business update ở transaction khác, atomicity cũng bị phá.

**Giới hạn:** trong sản phẩm thật, cần xử lý duplicate **đang in-flight**, payload canonicalization, per-tenant key, retention, failover và API state reconciliation; demo chỉ bảo vệ một DB effect.

## 14. RetryingPaymentClient giữ nguyên command trong mọi attempt

**`src/main/java/com/example/retrysafety/ChargeGateway.java`:**

~~~java
package com.example.retrysafety;

@FunctionalInterface
public interface ChargeGateway {
    PaymentReceipt charge(PaymentCommand command);
}
~~~

**`src/main/java/com/example/retrysafety/RetryingPaymentClient.java`:**

~~~java
package com.example.retrysafety;

import java.util.Objects;
import org.springframework.retry.support.RetryTemplate;

public class RetryingPaymentClient {

    private final ChargeGateway gateway;
    private final RetryTemplate retries;

    public RetryingPaymentClient(
            ChargeGateway gateway,
            RetryTemplate retries
    ) {
        this.gateway = Objects.requireNonNull(
                gateway, "gateway"
        );
        this.retries = Objects.requireNonNull(
                retries, "retries"
        );
    }

    public PaymentReceipt charge(PaymentCommand command) {
        Objects.requireNonNull(command, "command");

        return retries.execute(context ->
                gateway.charge(command)
        );
    }
}
~~~

`RetryTemplate.execute` có thể gọi lại callback sau lỗi retryable, nhưng callback **nhìn cùng PaymentCommand instance**. Nếu timeout sau commit, retry gửi **cùng key**. Business logic không cộng số dư bên trong callback; tác động nghiệp vụ thuộc server-side processor.

**`src/main/java/com/example/retrysafety/RetryConfiguration.java`:**

~~~java
package com.example.retrysafety;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.support.RetryTemplate;

@Configuration(proxyBeanMethods = false)
public class RetryConfiguration {

    @Bean
    RetryTemplate paymentRetryTemplate() {
        return RetryTemplate.builder()
                .maxAttempts(3)
                .retryOn(TemporaryGatewayFailure.class)
                .exponentialBackoff(100, 2.0, 800)
                .build();
    }

    @Bean
    ChargeGateway localChargeGateway(
            PaymentProcessor processor
    ) {
        // Offline demo adapter; không phát HTTP thật.
        return processor::charge;
    }

    @Bean
    RetryingPaymentClient retryingPaymentClient(
            ChargeGateway gateway,
            RetryTemplate paymentRetryTemplate
    ) {
        return new RetryingPaymentClient(
                gateway, paymentRetryTemplate
        );
    }
}
~~~

Bộ test tạo retry template **noBackoff** để kiểm attempts mà không sleep thật. Một test riêng dùng `ExponentialBackOffPolicy` với fake sleeper kiểm chính xác delay. Với production HTTP adapter, phải **thay** `localChargeGateway` bằng bean HTTP hoặc dùng profiles/qualifiers để tránh hai candidates cùng type.

## 15. Integration tests: tám kịch bản cụ thể

**`src/test/java/com/example/retrysafety/RetryingPaymentClientTest.java`:**

~~~java
package com.example.retrysafety;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.retry.support.RetryTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        classes = RetrySafetyApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class RetryingPaymentClientTest {

    @Autowired PaymentProcessor processor;
    @Autowired JdbcTemplate jdbc;

    private String account;

    @BeforeEach
    void setUpOwnAccount() {
        account = "wallet-" + UUID.randomUUID();
        jdbc.update(
                """
                INSERT INTO account_balances
                  (account_id, balance_cents)
                VALUES (?, ?)
                """,
                account, 1_000L
        );
    }

    @AfterEach
    void cleanOnlyThisTestsRows() {
        jdbc.update(
                """
                DELETE FROM payment_inbox
                WHERE account_id IN (?, ?)
                """,
                account, account + "-missing"
        );
        jdbc.update(
                """
                DELETE FROM account_balances
                WHERE account_id IN (?, ?)
                """,
                account, account + "-missing"
        );
    }

    private RetryingPaymentClient client(ChargeGateway gateway) {
        RetryTemplate testRetries = RetryTemplate.builder()
                .maxAttempts(3)
                .retryOn(TemporaryGatewayFailure.class)
                .noBackoff()
                .build();
        return new RetryingPaymentClient(gateway, testRetries);
    }

    private PaymentCommand command(long cents) {
        return new PaymentCommand(
                UUID.randomUUID().toString(), account, cents
        );
    }

    private long balance(String accountId) {
        Long found = jdbc.queryForObject(
                """
                SELECT balance_cents
                FROM account_balances
                WHERE account_id = ?
                """,
                Long.class, accountId
        );
        return found.longValue();
    }

    private int markerCount(String key) {
        Integer found = jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM payment_inbox
                WHERE idempotency_key = ?
                """,
                Integer.class, key
        );
        return found.intValue();
    }

    @Test
    void successfulFirstAttemptDoesNotRetry() {
        AtomicInteger sends = new AtomicInteger();
        PaymentCommand request = command(250);

        ChargeGateway gateway = cmd -> {
            sends.incrementAndGet();
            return processor.charge(cmd);
        };
        PaymentReceipt receipt =
                client(gateway).charge(request);

        assertThat(receipt.idempotencyKey())
                .isEqualTo(request.idempotencyKey());
        assertThat(sends.get()).isEqualTo(1);
        assertThat(balance(account)).isEqualTo(1_250L);
        assertThat(markerCount(request.idempotencyKey()))
                .isEqualTo(1);
    }

    @Test
    void twoTransientFailuresThenSuccessMeanThreeAttempts() {
        AtomicInteger sends = new AtomicInteger();
        List<String> keysSeen = new ArrayList<>();
        PaymentCommand request = command(150);

        ChargeGateway gateway = cmd -> {
            keysSeen.add(cmd.idempotencyKey());
            if (sends.incrementAndGet() <= 2) {
                throw new TemporaryGatewayFailure("simulated 503");
            }
            return processor.charge(cmd);
        };
        PaymentReceipt receipt =
                client(gateway).charge(request);

        assertThat(receipt.amountCents()).isEqualTo(150L);
        assertThat(sends.get()).isEqualTo(3);
        assertThat(keysSeen).containsExactly(
                request.idempotencyKey(),
                request.idempotencyKey(),
                request.idempotencyKey()
        );
        assertThat(balance(account)).isEqualTo(1_150L);
        assertThat(markerCount(request.idempotencyKey()))
                .isEqualTo(1);
    }

    @Test
    void exhaustedRetriesStopAfterExactlyThreeAttempts() {
        AtomicInteger sends = new AtomicInteger();
        PaymentCommand request = command(200);

        ChargeGateway unavailable = cmd -> {
            sends.incrementAndGet();
            throw new TemporaryGatewayFailure(
                    "partner still down"
            );
        };

        assertThatThrownBy(
                () -> client(unavailable).charge(request)
        ).isInstanceOf(TemporaryGatewayFailure.class)
         .hasMessageContaining("partner still down");

        assertThat(sends.get()).isEqualTo(3);
        assertThat(balance(account)).isEqualTo(1_000L);
        assertThat(markerCount(request.idempotencyKey()))
                .isZero();
    }

    @Test
    void nonRetryableValidationErrorIsSentOnlyOnce() {
        AtomicInteger sends = new AtomicInteger();

        ChargeGateway rejected = cmd -> {
            sends.incrementAndGet();
            throw new IllegalArgumentException(
                    "invalid customer data"
            );
        };

        assertThatThrownBy(
                () -> client(rejected).charge(command(100))
        ).isInstanceOf(IllegalArgumentException.class);

        assertThat(sends.get()).isEqualTo(1);
        assertThat(balance(account)).isEqualTo(1_000L);
    }

    @Test
    void lostResponseAfterDbCommitDoesNotChargeTwice() {
        AtomicInteger sends = new AtomicInteger();
        List<String> keysSeen = new ArrayList<>();
        PaymentCommand request = command(300);

        ChargeGateway responseMayBeLost = cmd -> {
            keysSeen.add(cmd.idempotencyKey());
            int attempt = sends.incrementAndGet();

            // Upstream đã commit, nhưng client có thể chưa thấy.
            PaymentReceipt committed = processor.charge(cmd);
            if (attempt == 1) {
                throw new TemporaryGatewayFailure(
                        "response lost after commit"
                );
            }
            return committed;
        };

        PaymentReceipt receipt =
                client(responseMayBeLost).charge(request);

        assertThat(receipt.amountCents()).isEqualTo(300L);
        assertThat(sends.get()).isEqualTo(2);
        assertThat(keysSeen).containsExactly(
                request.idempotencyKey(),
                request.idempotencyKey()
        );
        assertThat(balance(account)).isEqualTo(1_300L);
        assertThat(markerCount(request.idempotencyKey()))
                .isEqualTo(1);
    }

    @Test
    void sameKeyWithChangedPayloadIsConflictNotRetry() {
        PaymentCommand first = command(200);
        processor.charge(first);

        AtomicInteger sends = new AtomicInteger();
        ChargeGateway gateway = cmd -> {
            sends.incrementAndGet();
            return processor.charge(cmd);
        };
        PaymentCommand changed = new PaymentCommand(
                first.idempotencyKey(), account, 999L
        );

        assertThatThrownBy(
                () -> client(gateway).charge(changed)
        ).isInstanceOf(IdempotencyConflictException.class)
         .hasMessageContaining("Conflicting idempotency key");

        assertThat(sends.get()).isEqualTo(1);
        assertThat(balance(account)).isEqualTo(1_200L);
        assertThat(markerCount(first.idempotencyKey()))
                .isEqualTo(1);
    }

    @Test
    void distinctKeysWithSameAmountAreTwoRealPayments() {
        PaymentCommand first = command(150);
        PaymentCommand second = command(150);

        RetryingPaymentClient payments =
                client(processor::charge);
        payments.charge(first);
        payments.charge(second);

        assertThat(first.idempotencyKey())
                .isNotEqualTo(second.idempotencyKey());
        assertThat(balance(account)).isEqualTo(1_300L);
        assertThat(markerCount(first.idempotencyKey()))
                .isEqualTo(1);
        assertThat(markerCount(second.idempotencyKey()))
                .isEqualTo(1);
    }

    @Test
    void failedDbMutationRollsBackMarkerSoLaterReplayWorks() {
        String missing = account + "-missing";
        PaymentCommand request = new PaymentCommand(
                UUID.randomUUID().toString(), missing, 700L
        );
        RetryingPaymentClient payments =
                client(processor::charge);

        assertThatThrownBy(
                () -> payments.charge(request)
        ).isInstanceOf(IllegalStateException.class)
         .hasMessageContaining("Unknown account");

        assertThat(markerCount(request.idempotencyKey()))
                .isZero();

        // Sửa điều kiện business, replay CÙNG key.
        jdbc.update(
                """
                INSERT INTO account_balances
                  (account_id, balance_cents)
                VALUES (?, ?)
                """,
                missing, 0L
        );

        PaymentReceipt recovered = payments.charge(request);
        assertThat(recovered.amountCents()).isEqualTo(700L);
        assertThat(balance(missing)).isEqualTo(700L);
        assertThat(markerCount(request.idempotencyKey()))
                .isEqualTo(1);
    }
}
~~~

### Ý nghĩa từng nhóm test

- **Success first try**: không tự tăng attempt count vô cớ.
- **Transient 503 giả**: hai failures rồi success -> đúng ba sends; cùng một key; balance chỉ tăng 150.
- **Exhaustion**: ba attempts rồi exception; không có marker/effect.
- **Terminal validation**: không retry; sends bằng 1.
- **Lost response sau DB commit**: sends bằng 2 nhưng marker duy nhất và balance chỉ tăng 300, **không phải 600**.
- **Same key + changed payload**: conflict, không retry; balance từ attempt đầu giữ nguyên.
- **Different keys cùng amount**: hai logical actions, phải áp dụng đủ hai.
- **Business failure rollback**: marker không tồn tại sau lỗi; sau sửa account, replay cùng key thành công.

Không có `@Transactional` trên test class: mỗi lần gọi `PaymentWriteTransaction` cần transaction riêng để commit/rollback đúng, tránh Spring test-managed transaction bên ngoài thay đổi semantics. `@BeforeEach` dùng unique account, `@AfterEach` xóa đúng account/marker của test, không TRUNCATE toàn bảng.

## 16. ExponentialBackOffPolicy và fake sleeper

Spring Retry có `ExponentialBackOffPolicy.setSleeper(Sleeper)` để thay chờ thời gian thật bằng một chiến lược do test cung cấp. Test chính xác delays và attempt count **không phải gọi `Thread.sleep()`**.

**`src/test/java/com/example/retrysafety/BackoffPolicyTest.java`:**

~~~java
package com.example.retrysafety;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.support.RetryTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class BackoffPolicyTest {

    private RetryTemplate template(
            int maxAttempts,
            ExponentialBackOffPolicy backoff
    ) {
        RetryTemplate retries = RetryTemplate.builder()
                .maxAttempts(maxAttempts)
                .retryOn(TemporaryGatewayFailure.class)
                .build();
        retries.setBackOffPolicy(backoff);
        return retries;
    }

    @Test
    void exponentialBackoffUses100200AndCapped250() {
        List<Long> waits = new ArrayList<>();
        ExponentialBackOffPolicy policy =
                new ExponentialBackOffPolicy();

        policy.setInitialInterval(100);
        policy.setMultiplier(2.0);
        policy.setMaxInterval(250);
        policy.setSleeper(millis -> {
            waits.add(millis);
        });

        AtomicInteger attempts = new AtomicInteger();
        assertThatThrownBy(() ->
                template(5, policy).execute(context -> {
                    attempts.incrementAndGet();
                    throw new TemporaryGatewayFailure("offline");
                })
        ).isInstanceOf(TemporaryGatewayFailure.class);

        assertThat(attempts.get()).isEqualTo(5);
        assertThat(waits).containsExactly(
                100L, 200L, 250L, 250L
        );
    }

    @Test
    void threeAttemptsProduceExactlyTwoBackoffIntervals() {
        List<Long> waits = new ArrayList<>();
        ExponentialBackOffPolicy policy =
                new ExponentialBackOffPolicy();

        policy.setInitialInterval(50);
        policy.setMultiplier(2.0);
        policy.setMaxInterval(500);
        policy.setSleeper(millis -> {
            waits.add(millis);
        });

        AtomicInteger attempts = new AtomicInteger();
        assertThatThrownBy(() ->
                template(3, policy).execute(context -> {
                    attempts.incrementAndGet();
                    throw new TemporaryGatewayFailure("transient");
                })
        ).isInstanceOf(TemporaryGatewayFailure.class);

        assertThat(attempts.get()).isEqualTo(3);
        assertThat(waits).containsExactly(50L, 100L);
    }
}
~~~

Hai tests không đo elapsed wall time; chúng xác nhận policy gọi `Sleeper` với đúng delay, không có delay sau attempt cuối. Để test jitter, không assert exact millisecond value ngẫu nhiên: inject deterministic randomness nếu API cho phép hoặc kiểm upper/lower bounds và probabilistic behavior, không tạo flaky test. Với HTTP latency cần một integration test riêng và tolerance phù hợp.

**Tổng cộng 10 JUnit methods** ở hai test classes; tám ca kiểm business effect và retry orchestration, hai ca kiểm exponential backoff. Code mẫu không có stdout cố định.

## 17. HTTP adapter minh họa với RestClient

Trong hệ thống thật, gateway nên gửi key ra phía server bằng header. Đoạn sau là **tệp minh họa thêm** chứ không nằm trong project runnable mặc định; muốn dùng cần `spring-boot-starter-web`, base URL từ config, timeouts phù hợp, và **thay** bean `localChargeGateway` để tránh hai candidates.

~~~java
package com.example.retrysafety;

import org.springframework.http.HttpHeaders;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestClient;

public final class HttpChargeGateway implements ChargeGateway {
    private final RestClient http;

    public HttpChargeGateway(
            RestClient.Builder builder,
            String baseUrl
    ) {
        this.http = builder.baseUrl(baseUrl).build();
    }

    @Override
    public PaymentReceipt charge(PaymentCommand command) {
        try {
            PaymentReceipt receipt = http.post()
                    .uri("/api/payments")
                    .header("Idempotency-Key",
                            command.idempotencyKey())
                    .header(HttpHeaders.ACCEPT, "application/json")
                    .body(command)
                    .retrieve()
                    .body(PaymentReceipt.class);

            if (receipt == null) {
                throw new IllegalStateException(
                        "Empty payment response"
                );
            }
            return receipt;
        } catch (HttpServerErrorException.ServiceUnavailable
                 | HttpClientErrorException.TooManyRequests e) {
            throw new TemporaryGatewayFailure(
                    "Partner temporary failure", e
            );
        }
    }
}
~~~

Code này minh họa **503/429 mapping**; nó chưa map 502/504 hoặc `ResourceAccessException` (read timeout/reset). Thêm những lỗi đó **chỉ nếu** API đối tác có server-side idempotency contract đủ mạnh. HTTP 400/409 từ `retrieve()` vẫn là exception riêng, RetryTemplate chỉ retry loại `TemporaryGatewayFailure`.

HTTP contract test bổ sung bằng WireMock/MockWebServer port động nên verify:

- Attempt đầu 503, attempt sau 200 → đúng hai HTTP requests, **cùng header Idempotency-Key**.
- HTTP 400 và 409 → một request, không retry.
- 429 có Retry-After → policy không vi phạm server limit và SLO.
- Timeout sau **server đã commit** → hai attempts nhưng server ledger chỉ một effect.
- Body/status/header decode đúng; không chỉ Mockito verify method invocation.
- Dynamic baseURL không trỏ production khi chạy test.

Vì ví dụ chính dùng scripted Java gateway, nó **không tuyên bố** đã kiểm TCP/HTTP/SSL thật. Bộ HTTP tests là tầng bổ sung khi vận hành API bên ngoài.

## 18. @Retryable, @Recover và AOP self-invocation

Spring Retry cũng hỗ trợ annotation:

~~~java
@EnableRetry
@Configuration
class RetryAnnotationsConfiguration {
}
~~~

~~~java
@Service
class AnnotatedPartnerService {
    @Retryable(
            retryFor = TemporaryGatewayFailure.class,
            maxAttempts = 3,
            backoff = @Backoff(
                    delay = 100,
                    multiplier = 2.0,
                    maxDelay = 800
            )
    )
    PaymentReceipt charge(PaymentCommand command) {
        return gateway.charge(command);
    }
}
~~~

Hai đoạn chỉ là **skeleton**, chưa có imports/gateway và **không thuộc bộ demo runnable**. Cần Spring Retry và AOP proxy infrastructure (ví dụ `spring-boot-starter-aop`), `@EnableRetry` và bean được quản lý bởi Spring. `@Retryable.maxAttempts` **bao gồm lần thử đầu**; `@Recover` là recovery hook khi policy cạn attempts nếu signature/return type phù hợp.

**Self-invocation:** một method trong bean gọi `this.charge(...)` thường **không qua Spring AOP proxy**, nên `@Retryable` có thể không chạy. Nếu test chỉ assert output, nó có thể vẫn PASS do method chạy một lần. Hãy test attempt count và exception qua Spring bean proxy. Programmatic `RetryTemplate` trong dự án chính không phụ thuộc proxy cho retry.

**Retry transaction boundaries:** Nếu đặt `@Transactional` và `@Retryable` trên cùng method, thứ tự AOP advices và rollback-only state có thể gây hành vi không mong muốn. Cách rõ ràng là orchestration retry **bên ngoài**, mỗi attempt gọi một service `@Transactional` ở **bean khác**, để rollback/commit trước khi có retry kế.

Recovery không được tạo giả `PaymentReceipt` “success” khi không biết upstream đã commit hay chưa. Với outcome ambiguous, return PENDING/UNKNOWN và reconciliation có thể đúng hơn một lời khẳng định thành công giả.

## 19. Đừng retry toàn bộ workflow không lũy đẳng

Phản ví dụ:

~~~java
@Retryable(retryFor = Exception.class, maxAttempts = 3)
public void placeOrder(Order order) {
    reserveInventory(order); // đã commit lần 1
    chargePayment(order);    // mất response
    sendEmail(order);        // có thể gửi nhiều lần
}
~~~

Đây là skeleton/anti-pattern, không phải runnable source. Nếu retry cả `placeOrder`, `reserveInventory` có thể bị lặp ngay cả khi payment service dùng idempotency key đúng.

Thiết kế an toàn hơn:

1. Tách mỗi bước thành **state transition có ID/unique contract**.
2. Retry boundary hẹp, ví dụ `chargePayment(paymentIdempotencyKey=K)`.
3. Inventory reservation có uniqueness theo order/line item/attempt semantics.
4. External payment call truyền stable provider key và có trạng thái reconciliation.
5. Email/event được tạo qua **transactional outbox**, không trực tiếp gửi trong một DB transaction rồi kỳ vọng rollback được email.
6. Dùng saga/workflow state machine cho nhiều dịch vụ, có compensation rõ thay vì chạy lại toàn bộ như từ đầu.

**Không có Java retry annotation nào tạo ACID transaction xuyên database, payment provider, email và Kafka.**

## 20. Transactional outbox và side effects ngoài database

Trong demo, `payment_inbox` và balance update thuộc **một database transaction**. Nhưng gửi email hoặc publish Kafka event **sau** commit có thể bị mất nếu JVM crash trước khi gửi. Gửi **trước** commit có thể trùng nếu DB rollback rồi retry.

Transactional outbox:

~~~text
Cùng DB transaction:
  INSERT payment_inbox K
  UPDATE account_balances
  INSERT outbox(PaymentAccepted event E)
  COMMIT

Relay sau đó:
  READ pending outbox E
  PUBLISH E
  MARK sent (có thể crash sau publish)
~~~

Outbox bảo đảm **ý định publish cùng DB commit**, nhưng relay có thể gửi hai lần nếu crash giữa broker ack và mark sent. Consumer downstream cần **idempotent inbox** riêng. Payment provider có thể cung cấp API idempotency-key; phải đọc contract về response replay, concurrent requests, retention và status query, không tự suy từ header name.

Khi response của external system mất sau commit, không gửi một payment action mới với key mới chỉ vì timeout. Thay vào đó **replay cùng key** nếu hợp đồng cho phép hoặc query/reconcile theo key/transaction ID.

## 21. Messaging, Kafka và RabbitMQ: redelivery là bình thường

| Môi trường | Vì sao retry/redelivery? | Cách phòng side effect trùng |
| --- | --- | --- |
| HTTP client | 429/503/timeouts/proxy retry | Stable idempotency key + server atomic effect |
| Kafka consumer | Offset chưa commit, rebalance, replay, DLT | Inbox key per consumer/tenant/event + DB transaction |
| RabbitMQ consumer | ACK mất, NACK/requeue, channel restart | Message ID business-level + inbox/dedup |
| Scheduled worker | Worker chết sau commit trước update job status | Job ID/operation ID unique và reconciliation |
| Outbox relay | Publish thành công nhưng mark sent chưa ghi | Downstream consumer idempotency |
| Payment provider | Client không thấy response, server charge xong | Provider-side idempotency key/transaction lookup |

Kafka exactly-once semantics trong một topology Kafka phù hợp **không tự bảo vệ** email, external API hay database nằm ngoài Kafka transaction. Spring Kafka blocking retry/non-blocking retry/DLT có các ràng buộc theo version, bao gồm thứ tự records và kết hợp transactions. Không bật retry nhiều tầng rồi nghĩ rằng “tổng số lần vẫn ba”.

Nếu replay DLT, **giữ logical event ID/idempotency key**; thay key mới có thể khiến consumer xem event cũ như hành động mới. Nếu dữ liệu marker bị xóa trước khi hết replay window, một event cũ cũng có thể được apply lần nữa.

## 22. Concurrency và key đang được xử lý

Bảng primary key chặn hai transactions commit cùng marker, nhưng có thể xảy ra tình huống hai requests đồng thời cùng key:

~~~text
A: BEGIN -> INSERT K -> UPDATE account
B: BEGIN -> INSERT K -> chờ unique index/lock
A: COMMIT
B: duplicate key -> ROLLBACK -> read K -> no-op
~~~

Nếu A rollback, B có thể tiếp tục xử lý như attempt đầu. Test cạnh tranh cần backend DB thật, `CountDownLatch`/`CyclicBarrier` để ép interleaving và timeout hữu hạn, không đoán bằng `Thread.sleep`.

**Giới hạn của H2:** nó minh họa atomic unique constraint/rollback nhưng không thay thế PostgreSQL/MySQL Testcontainers cho lock wait, deadlock, isolation và error translation dưới tải. Trong production, nếu duplicate vẫn **IN_PROGRESS** (chưa commit), server cần policy cho pending result, đồng bộ theo key và conflict semantics; chỉ lookup committed marker không bao trùm toàn bộ trường hợp.

`synchronized` hoặc cache Map chỉ hoạt động trong một JVM, mất khi restart và không khóa được ba Kubernetes pods. **DB unique constraint** là một hàng rào bền hơn, nhưng cần đúng scope tenant và transaction semantics.

## 23. Retry deadline, cancellation và unknown outcomes

Một timeout của client không có nghĩa attempt cũ đã dừng. `Future.get(2, TimeUnit.SECONDS)` có thể timeout trong khi worker/network request vẫn chạy; nếu client lập tức gửi attempt mới, **hai requests cùng key có thể đồng thời in-flight**.

Cần:

- Per-attempt connect/read timeout.
- Overall deadline hoặc retry budget.
- Propagate cancellation/interrupt hợp lý.
- Không gửi retry mới nếu không đủ remaining time.
- Không tạo retry storm dưới overload; giới hạn concurrency và kết hợp circuit breaker.
- Nếu outcome chưa biết, lưu `PENDING/UNKNOWN` và đối soát bằng stable transaction ID.
- Tránh giữ DB transaction mở qua backoff/network wait.
- Không nuốt tất cả exceptions rồi trả business success.

Khi HTTP timeout xảy ra **sau commit**, chính server dedup mới làm retry an toàn. Khi provider không có idempotency API hoặc status query, phương án đúng có thể là **không tự retry POST**, thay vào đó tạo reconciliation workflow/manual review.

## 24. Jitter và thundering herd

Với nhiều clients cùng sự cố, một backoff deterministic `100, 200, 400 ms` khiến cả nghìn clients thử lại cùng lúc. Jitter làm lệch nhịp, giảm thundering herd.

Các chiến lược:

- Fixed backoff: đơn giản, nhưng dễ đồng pha.
- Capped exponential: giảm hammer, cần max interval.
- Exponential random: thêm randomness cho nhiều clients.
- Server-directed delay: `Retry-After`, kết hợp deadline.
- Retry token budget: giới hạn tổng traffic retry.
- Delayed queue/topic: dành cho async jobs để không block listener threads.

Spring Retry `exponentialBackoff(..., true)` sử dụng exponential random policy theo API 2.x. **Không mặc định đồng nhất** với mọi thuật toán “full jitter” hay “equal jitter” được mô tả ở các hệ khác; kiểm đúng API/version. Test deterministic exponential bằng fake sleeper, còn jitter thì test bounds/cancellation hoặc nguồn randomness kiểm soát nếu framework cho phép. Không assert mỗi lần delay phải đúng một số cố định với random policy.

## 25. Failure injection cần có trong CI

Bộ mười test của demo tập trung business invariant, nhưng production cần ma trận sâu hơn:

| Failure window | Invariant phải chứng minh |
| --- | --- |
| Trước request tới server | Retry được khi transient, không tạo effect ngoài ý muốn |
| Sau INSERT marker nhưng trước balance UPDATE | Rollback cả marker, replay thành công |
| Sau UPDATE nhưng trước COMMIT | Rollback cả marker/effect |
| **Sau COMMIT nhưng trước HTTP response** | Retry same key, no double effect |
| Hai cùng key trong hai transactions | Tối đa một effect commit |
| Hai khác key cùng account | Cả hai effect commit, không lost update |
| Same key + changed payload | Conflict; không silently skip |
| 503 đầu rồi 200 | Attempts đúng, key/header không đổi |
| 429 + Retry-After | Thời gian retry tuân contract/deadline |
| 400/401/403/409 | Không retry vô nghĩa |
| HTTP SDK có retry bên trong | Tổng physical sends không vượt budget |
| Outbox publish rồi crash trước mark sent | Downstream dedup |
| DLT replay sau nhiều ngày | Key retention bảo vệ đúng replay window |
| Provider timeout ở attempt đang in-flight | Không nhân effect khi attempt sau tới |
| CI multi-worker và nhiều pods | Dữ liệu/tenant scoped, cleanup an toàn |

Một HTTP test chỉ kiểm `Mockito.verify(gateway, times(2))` **chưa đủ**. Phải assert database ledger/business state, số unique markers và receipts, đặc biệt ở case response lost. Fault injection process kill/HTTP network cần Testcontainers/embedded server/chaos harness phù hợp.

## 26. Observability: đếm attempts khác applied effects

Một logical payment được gửi hai lần sau lost response có thể tạo metrics:

~~~text
logical operations         = 1
HTTP attempts              = 2
client retries             = 1
server requests received   = 2
idempotency duplicate noops= 1
business effects applied   = 1
~~~

Đây là ví dụ tính toán theo scenario, không phải stdout thực. Nếu `business effects applied` thành 2, idempotency contract đã bị phá dù client cuối cùng có nhận receipt thành công.

Nên đo retry rate, error categories (503/429/timeout/conflict), exhausted attempts, backoff histogram, p95/p99 latency, active requests, database unique conflicts, idempotency duplicates, outbox pending và reconciliation queue. Log theo correlation ID, stable key (redact/hash nếu nhạy cảm), attempt index và deadline remaining. Không log card data, raw credential hoặc PII trong mỗi retry.

**Đừng coi duplicate count tăng luôn là bug:** sau outage/rebalance nó có thể tăng do redelivery hợp lệ. Nhưng same key **payload conflict** thường cần cảnh báo vì có thể là producer bug hoặc malicious reuse.

## 27. Các lỗi thường gặp khi thiết kế retry

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| `maxAttempts=3` hiểu thành 4 calls | Gửi quá budget | Nhớ attempt đầu nằm trong 3 |
| Retry mọi `Exception` | 400/conflict cũng bị gửi lại | Classify transient hẹp |
| Retry POST có side effect mà không dedup | Double charge/duplicate order | Stable key + server unique/transaction |
| Sinh UUID bên trong retry callback | Mỗi attempt thành action mới | Sinh key một lần trước retry |
| Marker commit trước business mutation | Failure rồi retry bị skip | Cùng transaction |
| Catch unique violation trong PostgreSQL tx | Transaction aborted | Catch ngoài transactional proxy |
| Same key khác payload bị no-op | Mất transaction hợp lệ hoặc che lỗi | So canonical payload, conflict |
| Chỉ check exception/no exception | Không biết DB effect có trùng | Assert ledger/marker |
| No backoff/không jitter ở high QPS | Retry storm | Capped exponential + jitter/budget |
| Backoff sleep trên HTTP thread vô hạn | Exhaust thread pool | Deadline, async/queue/bulkhead |
| Header Retry-After bị bỏ qua | Vượt rate limit | Parse header, respect budget |
| 3 tầng retry nhân nhau | Nhiều sends hơn dự kiến | Audit toàn dependency chain |
| Test dùng `Thread.sleep` | Chậm và flaky | Fake sleeper/noBackoff |
| Test @Transactional bọc processor | Transaction boundaries bị méo | Test commit/rollback thật |
| @Retryable self-invocation | Retry bị bỏ qua | Spring bean proxy hoặc RetryTemplate |
| @Transactional self-invocation | Marker/effect không atomic | Tách beans |
| H2 test thay kết luận về PostgreSQL | Bỏ qua lock/deadlock khác biệt | PostgreSQL Testcontainers |
| External email/Kafka ngoài DB tx | Duplicate/missing event | Outbox + downstream dedup |
| Timeout coi như server chưa commit | Tạo action mới | Reconcile bằng same key |
| DLT replay đổi event ID | Consumer áp dụng lại effect | Giữ logical event ID |
| Idempotency marker TTL quá ngắn | Replay cũ gây effect lần nữa | Retention theo business contract |
| Retry exhausted trả fake success | Che uncertain outcome | Return error/PENDING và reconciliation |
| Dùng `@Primary` để che hai gateway beans | Không rõ adapter thực sự gọi ai | Chỉ một gateway theo profile/qualifier |

## 28. Checklist QA trước khi chốt resilience test

- [ ] Đã xác định chính xác **logical business action** và stable idempotency key?
- [ ] Phân biệt same event/key với two legitimate actions có payload giống?
- [ ] Đã classify transient vs permanent vs ambiguous outcomes?
- [ ] `maxAttempts` hữu hạn; test attempt đầu và retry count đúng?
- [ ] Backoff có initial/multiplier/max; jitter khi nhiều clients?
- [ ] Có per-attempt timeout, overall deadline và retry budget?
- [ ] Kiểm tất cả nested retries trong SDK/proxy/consumer?
- [ ] POST mutate chỉ tự retry khi server/provider bảo đảm idempotency?
- [ ] Server-side uniqueness tồn tại ở **database** đúng scope?
- [ ] Marker và business effect commit/rollback cùng transaction?
- [ ] Same key + changed payload tạo conflict/alert?
- [ ] Existing same key + same payload trả receipt cũ/no-op?
- [ ] Failure trước commit không để lại marker giả?
- [ ] **Commit rồi lost response** được test và balance không tăng hai lần?
- [ ] Two different keys được áp dụng độc lập dù amount bằng nhau?
- [ ] Có test permanent 400/validation/conflict không retry?
- [ ] Có test exhausting attempts, số sends chính xác?
- [ ] Fake sleeper kiểm delays mà không sleep thời gian thực?
- [ ] Nếu server gửi Retry-After, policy tôn trọng khi còn deadline?
- [ ] Nếu retry state không xác định, có reconciliation/status query?
- [ ] @Transactional và @Retryable không bị self-invocation bypass?
- [ ] Business effect ngoài DB dùng outbox/provider key/compensation?
- [ ] Kafka/Rabbit replay giữ logical ID và marker retention đủ lâu?
- [ ] Concurrency trên production DB có separate stress/fault tests?
- [ ] Test không gọi production/staging payment endpoint?
- [ ] Metrics phân biệt logical operations, physical attempts và effects applied?
- [ ] Chưa thực thi build thì báo rõ là expected, không giả test đã PASS?

## 29. Lệnh chạy, kết quả mong đợi và giới hạn

Với JDK 17+, Gradle Wrapper và dependencies:

~~~bash
./gradlew test --tests "com.example.retrysafety.RetryingPaymentClientTest"
./gradlew test --tests "com.example.retrysafety.BackoffPolicyTest"
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.retrysafety.RetryingPaymentClientTest"
.\gradlew.bat test --tests "com.example.retrysafety.BackoffPolicyTest"
.\gradlew.bat test
~~~

**Mười JUnit methods** gồm tám Spring/JDBC integration tests và hai unit tests backoff. Expected outcome:

| Test | Kỳ vọng |
| --- | --- |
| `successfulFirstAttemptDoesNotRetry` | 1 send, balance 1250, marker 1 |
| `twoTransientFailuresThenSuccessMeanThreeAttempts` | 3 sends, cùng key, balance 1150 |
| `exhaustedRetriesStopAfterExactlyThreeAttempts` | 3 sends rồi transient exception, balance 1000 |
| `nonRetryableValidationErrorIsSentOnlyOnce` | 1 send, không business effect |
| `lostResponseAfterDbCommitDoesNotChargeTwice` | 2 sends nhưng balance chỉ 1300, marker 1 |
| `sameKeyWithChangedPayloadIsConflictNotRetry` | Conflict, no retry, balance 1200 |
| `distinctKeysWithSameAmountAreTwoRealPayments` | Hai keys, balance 1300 |
| `failedDbMutationRollsBackMarkerSoLaterReplayWorks` | Lần đầu rollback marker, replay thành công 700 |
| `exponentialBackoffUses100200AndCapped250` | 5 attempts; waits [100,200,250,250] |
| `threeAttemptsProduceExactlyTwoBackoffIntervals` | 3 attempts; waits [50,100] |

**Đây là expected logic từ code, không phải output Gradle/JUnit/H2 đã quan sát.** Bài soạn đã được rà soát API và semantics bằng tài liệu, nhưng chưa compile/run trong môi trường biên soạn. Demo không có `System.out.println` nên không có stdout cố định.

**Kết luận:** Retry phải **bounded, phân loại lỗi rõ, có backoff/jitter và deadline**; nhưng để tránh thực thi nghiệp vụ hai lần, còn cần **stable idempotency key + atomic server-side business transaction**. Tình huống nguy hiểm nhất là **server đã commit, client không nhận response**: lặp request với **cùng key** phải trả receipt cũ mà không nhân effect. Với tác động ngoài một DB, mở rộng bằng outbox/provider idempotency/reconciliation; không tự tuyên bố exactly-once chỉ vì annotation retry.

### Tài liệu chính thức

- [RFC 9110 — HTTP semantics, idempotence và Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 6585 — 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html)
- [Spring Retry 2.x — RetryTemplateBuilder Javadoc](https://docs.spring.io/spring-retry/docs/2.0.x/apidocs/spring.retry/org/springframework/retry/support/RetryTemplateBuilder.html)
- [Spring Retry 2.x — ExponentialBackOffPolicy, Sleeper](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/backoff/ExponentialBackOffPolicy.html)
- [Spring Retry 2.x — @Retryable maxAttempts](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/annotation/Retryable.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework — Transaction Rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
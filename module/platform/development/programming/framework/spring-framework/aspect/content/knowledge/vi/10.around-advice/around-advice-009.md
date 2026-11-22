# Rủi ro lặp thao tác có tác dụng phụ khi triển khai retry bằng aspect trong Spring AOP

## 1. Bản chất của vấn đề

Trong **Spring AOP**, một phương thức advice mang `@Around` có thể gọi `ProceedingJoinPoint.proceed()` nhiều lần. Đây là nền tảng để tạo logic **retry**: khi target ném exception, advice gọi lại continuation của Spring proxy. Tuy nhiên, **mỗi lần proceed có thể chạy lại toàn bộ target method, bao gồm những thao tác đã có tác dụng phụ**.

Ví dụ quy trình thanh toán:

~~~text
Client -> Spring service proxy
          -> RetryAspect @Around
             -> proceed #1
                -> gọi hệ thống thanh toán
                -> hệ thống đã ghi nợ
                -> response/ACK bị mất, ném timeout
             -> catch timeout
             -> proceed #2
                -> hệ thống có thể ghi nợ lần nữa
             -> caller nhận một kết quả thành công
~~~

Người dùng thấy **một request trả thành công** không chứng minh chỉ có **một lần ghi nợ**. Đây là nguy cơ quan trọng nhất khi viết retry bằng `@Aspect`.

Sau bài này, bạn sẽ:

1. Hiểu chính xác `proceed()` làm gì trong Spring AOP, vì sao retry có thể lặp cả target và các interceptor bên trong.
2. Phân biệt lỗi **trước side effect**, **sau side effect**, và **không biết side effect đã commit chưa**.
3. Viết bounded retry chỉ bắt lỗi được phân loại cụ thể, không nuốt lỗi cuối hoặc trả thành công giả.
4. Hiểu sự khác biệt giữa **idempotency**, retry attempt và transaction rollback.
5. Chạy ví dụ Spring Framework thuần Java 17+ so sánh luồng **không chống trùng** và luồng có **idempotency key trong một JVM**.
6. Phân tích thứ tự Spring retry aspect và transaction advice, self-invocation, pointcut, concurrency, timeout và observability.
7. Biết khi nào phải yêu cầu idempotency/reconciliation phía hệ thống đích thay vì retry mù.

**Phạm vi:** Chỉ bàn về `@Around` trong **Spring-managed `@Aspect`/Spring AOP proxy**. Những nguyên tắc idempotency và distributed systems được giải thích ở mức cần thiết để thiết kế aspect đúng, không thay thế tài liệu giao dịch/thanh toán chuyên biệt.

## 2. Một proxy invocation không đồng nghĩa một lần vào target

Spring AOP sử dụng JDK dynamic proxy hoặc class-based CGLIB proxy. Khi client gọi một method qua proxy và pointcut khớp, advice `@Around` có thể kiểm soát continuation:

~~~text
Caller
  |
  +--> Spring AOP Proxy
           |
           +--> RetryAspect
                   |
                   +--> pjp.proceed(): attempt 1
                   |          |
                   |          +--> inner advice (nếu có)
                   |          +--> Target.method()
                   |          +--> side effect có thể đã xảy ra
                   |          +--> ném TemporaryFailureException
                   |
                   +--> catch exception phù hợp
                   |
                   +--> pjp.proceed(): attempt 2
                              |
                              +--> inner advice chạy lại
                              +--> Target.method() chạy lại
                              +--> side effect có thể lặp
~~~

Theo tài liệu Spring Framework, `proceed()` trong `@Around` có thể gọi **không lần nào, một lần hoặc nhiều lần**. Điều đó hợp lệ về kỹ thuật, nhưng Spring **không tự đánh giá target có an toàn để thực thi hai lần không**.

Một đoạn mã minh họa:

~~~java
@Around("execution(* demo.ChargeApi.charge(..))")
public Object retry(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (TemporaryFailureException first) {
        return pjp.proceed();
    }
}
~~~

Đây là **fragment trong class aspect**, cần thêm các imports, khai báo exception, bean service và cấu hình Spring AOP. Nó có thể gọi target tối đa hai lần nhưng chưa có idempotency, chính sách exception đầy đủ, backoff, transaction ordering hay giới hạn tổng thời gian. Không sử dụng trực tiếp cho lệnh ghi nợ hoặc gửi message thật.

Điểm cần phân biệt:

- **Client proxy invocation count:** người gọi có thể chỉ gọi một lần.
- **Retry attempts:** số lần `proceed()` được kích hoạt.
- **Target execution count:** có thể nhiều hơn một nếu continuation đi đến target mỗi lần.
- **Committed side effects:** không nhất thiết bằng số attempts; có thể đã thành công ở lần báo lỗi hoặc bị rollback riêng.
- **Advice execution count:** tùy advisor ordering, advice ngoài retry có thể chạy một lần còn advice trong retry chạy mỗi attempt.

## 3. Exception không chứng minh thao tác trước chưa xảy ra

| Thời điểm xảy ra lỗi | Ví dụ | Kết luận trước khi retry |
| --- | --- | --- |
| Trước side effect | Input validation không hợp lệ, lỗi trước khi gửi request | Có thể chưa có side effect, nhưng lỗi validation thường không nên retry |
| Sau side effect | DB đã commit, lỗi khi gọi bước tiếp theo; payment đã ghi nợ nhưng response mất | Retry có thể **lặp tác động** |
| Trạng thái unknown | Network timeout sau khi gửi request, không biết remote đã xử lý chưa | Không thể an toàn chỉ dựa vào exception |
| Transaction rollback được xác nhận | Lỗi trong một local DB transaction bị rollback đúng luật | Local DB side effect có thể chưa commit, nhưng remote side effect ngoài transaction vẫn có thể tồn tại |

**Timeout không đồng nghĩa thao tác không hoàn thành.** Nếu một API thanh toán trả timeout, client không có bằng chứng “chưa ghi nợ”. Muốn retry an toàn cần API phía nhận có idempotency key hoặc cần tra cứu kết quả theo operation ID trước khi thử lại.

Ví dụ dễ gặp khác:

- Gửi email thành công nhưng exception phát sinh khi ghi log kết quả.
- Publish event lên broker thành công nhưng xác nhận gửi bị mất.
- Ghi database thành công, rồi gọi dịch vụ phụ trợ thất bại.
- Tăng bộ đếm hoặc trừ số dư trước khi ném một runtime exception.
- Gửi yêu cầu tạo tài nguyên có request ID mới ở mỗi attempt.

Một vòng lặp retry không hiểu ranh giới side effect có thể khiến lỗi quan sát được **ít hơn** trong khi duplicate behavior **nhiều hơn**.

## 4. Bounded retry là điều kiện cần, không đủ

Ví dụ về cấu trúc retry có giới hạn:

~~~java
@Around("execution(* demo.ExternalOperation.execute(..))")
public Object retry(ProceedingJoinPoint pjp) throws Throwable {
    final int maxAttempts = 3;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            return pjp.proceed();
        } catch (TemporaryFailureException ex) {
            if (attempt == maxAttempts) {
                throw ex;
            }
        }
    }

    throw new IllegalStateException("Unreachable");
}
~~~

Đây là **fragment**; cần khai báo `TemporaryFailureException`, `ExternalOperation` và một class Spring aspect hợp lệ.

Các quy tắc quan trọng:

- `maxAttempts = 3` nghĩa là tối đa **ba attempts tính cả lần đầu**, không phải ba lần retry thêm.
- `proceed()` phải nằm trong loop; nếu gọi ngoài loop sẽ không thực thi lại target.
- Chỉ catch lỗi **đã được phân loại**; không retry mặc định mọi `RuntimeException` hoặc `Throwable`.
- Khi hết attempts, **ném lại exception cuối**, không báo kết quả thành công giả.
- Nếu thành công, trả chính kết quả `pjp.proceed()`, giữ return contract của method.
- Nếu mỗi attempt có thể tạo side effect, **giới hạn 3 attempts chỉ giới hạn tối đa số lần gây tác động**, không bảo đảm có đúng một side effect.
- Nếu caller đã có deadline, những attempts + backoff không được vượt budget theo thiết kế.

Hãy xác định **operation có idempotent không** trước khi áp dụng retry. Không coi bounded retry là giải pháp chống double charge.

## 5. Idempotency khác gì retry?

**Retry** lặp lại một operation khi gặp lỗi. **Idempotency** bảo đảm việc gửi cùng logical operation nhiều lần không nhân lên hiệu ứng nghiệp vụ mong muốn.

Ví dụ:

~~~text
logicalPayment = charge(order-12, amount=100)
    |
    +-- attempt 1 (key=order-12-charge)
    |
    +-- attempt 2 (key=order-12-charge)
    |
    +-- attempt 3 (key=order-12-charge)
~~~

Cả ba attempts dùng **cùng một idempotency key**. Nếu mỗi attempt tạo một key mới, hệ thống phía nhận có thể coi đó là ba operations độc lập.

Những lưu ý bắt buộc:

1. Key xác định **logical operation** chứ không phải một lần gọi HTTP riêng.
2. Key phải được tái sử dụng khi retry cùng operation, nhưng không được dùng chung cho hai operations thực sự khác nhau.
3. Có thể phải ràng buộc key với tenant/account, loại operation và fingerprint của request body.
4. Khi cùng key nhưng body khác nhau, cần trả conflict rõ ràng, không vô tình trả một kết quả của operation khác.
5. Idempotency cần được áp dụng **ở nơi quyết định side effect** hoặc bởi bên nhận có contract tương ứng.
6. Cần xử lý trạng thái **in progress**, completed, failed, unknown và policy TTL/retention.
7. Nếu nhiều replicas cùng nhận key, cần coordination hoặc durable storage. Một cache trong mỗi JVM không đủ.
8. Nếu ghi key và tác động bên ngoài không atomic, vẫn có cửa sổ lỗi; cần reconciliation hoặc cơ chế hỗ trợ của hệ thống đích.

**Idempotent không đồng nghĩa target không được gọi lại**: target có thể chạy hai lần nhưng lần sau đọc kết quả đã hoàn tất và không thực hiện side effect thứ hai.

## 6. Ví dụ Java 17+ Spring AOP: retry hai lần, so sánh số side effects

Ta tạo ứng dụng **Spring Framework 6.2.12**, **Java 17+**, **Maven 3.9+**, dùng Spring context thông thường. Không có DB hoặc network thật, nhưng tái tạo deterministic tình huống **báo lỗi sau khi đã tác động**.

Hai method trên Spring service:

- `unsafeCharge(requestId)`: mỗi lần target chạy sẽ tăng một bộ đếm side effect, **không có chống trùng**.
- `guardedCharge(requestId)`: cùng request ID tra cứu một kết quả đã lưu trong `ConcurrentHashMap`, side-effect counter chỉ tăng **một lần trong một JVM**.

Một `AfterEffectFailureGate` cố ý ném `TemporaryFailureException` **ở lần đầu sau side effect**. `RetryAspect` thực hiện tối đa hai attempts. Kết quả cho thấy **cả hai method đều được target gọi hai lần nhưng số side effects khác nhau**.

> Cơ chế `ConcurrentHashMap` chỉ là mô phỏng có kiểm soát, **không phải giải pháp đúng cho thanh toán phân tán hoặc lưu trữ bền vững**. Mục tiêu là nhìn được tác hại của retry và vị trí cần idempotency.

### 6.1. Cấu trúc project

~~~text
spring-aop-retry-side-effects/
├── pom.xml
└── src/main/java/demo/
    ├── ChargeApi.java
    ├── ChargeLedger.java
    ├── TemporaryFailureException.java
    ├── AfterEffectFailureGate.java
    ├── ChargeService.java
    ├── RetryAspect.java
    ├── AppConfig.java
    └── App.java
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-retry-side-effects</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp ApplicationContext và các module Spring AOP cần thiết. `aspectjweaver` cung cấp annotation/pointcut parser mà Spring sử dụng cho `@AspectJ` style; ví dụ này **proxy-based**, không dùng AspectJ compile-time/load-time weaving.

### 6.3. ChargeApi.java

~~~java
package demo;

public interface ChargeApi {
    String unsafeCharge(String requestId);
    String guardedCharge(String requestId);
}
~~~

Hai method được công bố qua interface để caller sử dụng **JDK dynamic proxy** khi Spring auto-proxy phù hợp. Cách gọi đi qua proxy quan trọng: nếu chỉ `new ChargeService(...)` rồi gọi, aspect không tự intercept đối tượng đó.

### 6.4. ChargeLedger.java

~~~java
package demo;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class ChargeLedger {

    private final AtomicInteger unsafeEffects = new AtomicInteger();
    private final AtomicInteger guardedEffects = new AtomicInteger();

    private final ConcurrentMap<String, String> processed =
            new ConcurrentHashMap<>();

    public String unsafe(String requestId) {
        int number = unsafeEffects.incrementAndGet();
        System.out.println("LEDGER unsafe side_effect=" + number);
        return "charged:" + requestId;
    }

    public String guarded(String requestId) {
        return processed.computeIfAbsent(requestId, key -> {
            int number = guardedEffects.incrementAndGet();
            System.out.println("LEDGER guarded side_effect=" + number);
            return "charged:" + key;
        });
    }

    public int unsafeCount() {
        return unsafeEffects.get();
    }

    public int guardedCount() {
        return guardedEffects.get();
    }
}
~~~

`unsafe` tăng side-effect counter **mỗi lần được gọi**. `guarded` dùng `computeIfAbsent`: với cùng key và entry còn tồn tại trong map này, nó tái sử dụng kết quả, không thực hiện lại lambda tạo giá trị. Điều này mô phỏng một idempotency ledger **cùng process**, không tương đương commit atomic với remote API.

`AtomicInteger` giúp phép tăng count là atomic, **không làm `unsafe` trở thành idempotent**.

### 6.5. TemporaryFailureException.java

~~~java
package demo;

public class TemporaryFailureException extends RuntimeException {

    public TemporaryFailureException(String message) {
        super(message);
    }
}
~~~

Trong demo, exception này chỉ là tín hiệu lỗi được thiết kế để retry aspect bắt. Trong ứng dụng thật, một tên exception như “Temporary” **không chứng minh operation là an toàn để retry**.

### 6.6. AfterEffectFailureGate.java

~~~java
package demo;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class AfterEffectFailureGate {

    private final Set<String> failedKeys =
            ConcurrentHashMap.newKeySet();

    public void failAfterEffectOnce(String method, String requestId) {
        String key = method + ":" + requestId;

        if (failedKeys.add(key)) {
            System.out.println("GATE lost-ack " + method);
            throw new TemporaryFailureException(
                    "Simulated acknowledgement loss after effect");
        }
    }
}
~~~

Ở lần đầu một cặp `method:requestId` xuất hiện, gate in `GATE lost-ack` rồi ném exception. Lần tiếp theo cùng cặp key không ném nữa. Gate chỉ dùng để tạo lỗi **sau khi ledger đã thực hiện side effect**, không dùng network thật, không có độ trễ ngẫu nhiên.

### 6.7. ChargeService.java

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class ChargeService implements ChargeApi {

    private final ChargeLedger ledger;
    private final AfterEffectFailureGate gate;

    public ChargeService(ChargeLedger ledger,
                         AfterEffectFailureGate gate) {
        this.ledger = ledger;
        this.gate = gate;
    }

    @Override
    public String unsafeCharge(String requestId) {
        System.out.println("TARGET unsafeCharge " + requestId);
        String result = ledger.unsafe(requestId);
        gate.failAfterEffectOnce("unsafeCharge", requestId);
        return result;
    }

    @Override
    public String guardedCharge(String requestId) {
        System.out.println("TARGET guardedCharge " + requestId);
        String result = ledger.guarded(requestId);
        gate.failAfterEffectOnce("guardedCharge", requestId);
        return result;
    }
}
~~~

Mỗi method làm ba bước: in `TARGET`, thực hiện ledger side effect (hoặc dedupe), sau đó gate **có thể ném exception**. Một exception ở bước cuối không xóa side effect ở bước trước. Retry sẽ chạy lại toàn bộ method.

Không có dependency vòng: `RetryAspect` không inject `ChargeService` hoặc ledger; nó chỉ khai báo pointcut. Các Spring beans ledger/gate không phải target của expression `ChargeApi.*(..)`.

### 6.8. RetryAspect.java

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class RetryAspect {

    @Around("execution(* demo.ChargeApi.*(..))")
    public Object retry(ProceedingJoinPoint pjp) throws Throwable {
        String methodName = pjp.getSignature().getName();
        final int maxAttempts = 2;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            System.out.println(
                    "RETRY " + methodName + " attempt=" + attempt);

            try {
                return pjp.proceed();
            } catch (TemporaryFailureException ex) {
                System.out.println(
                        "RETRY caught " + methodName +
                        " attempt=" + attempt);

                if (attempt == maxAttempts) {
                    throw ex;
                }
            }
        }

        throw new IllegalStateException("Unreachable retry state");
    }
}
~~~

Điểm đáng chú ý:

- `@Aspect` mô tả advice, `@Component` làm bean được đăng ký khi scan.
- `@Around` chỉ chọn phương thức thuộc contract `ChargeApi`.
- `pjp.proceed()` **nằm trong vòng lặp** và có thể gọi lại target.
- Không bắt mọi loại exception: chỉ retry `TemporaryFailureException`.
- Không nuốt lỗi ở attempt cuối; exception được chuyển cho caller.
- Không thay đổi arguments giữa các attempts; request ID vẫn giống nhau.
- Giá trị trả từ target được trả lại cho caller khi thành công.
- Không có delay trong demo để output có thứ tự xác định.

Trong production, cần giới hạn thêm tổng duration/backoff và đảm bảo operation thực sự có idempotency. Aspect này **cố ý không an toàn** cho `unsafeCharge` để minh họa rủi ro.

### 6.9. AppConfig.java

~~~java
package demo;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "demo")
@EnableAspectJAutoProxy
public class AppConfig {
}
~~~

`@ComponentScan` đăng ký service, ledger, gate và aspect. `@EnableAspectJAutoProxy` kích hoạt hạ tầng tự tạo Spring AOP proxy. Nếu chỉ có `@Aspect` mà class không phải Spring-managed bean, Spring không tự áp dụng advice.

### 6.10. App.java

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            ChargeApi charges = context.getBean(ChargeApi.class);
            ChargeLedger ledger = context.getBean(ChargeLedger.class);

            System.out.println(
                    "IS_PROXY " + AopUtils.isAopProxy(charges));

            System.out.println("=== UNSAFE ===");
            String unsafe = charges.unsafeCharge("U-1");
            System.out.println("RESULT unsafe=" + unsafe);
            System.out.println("UNSAFE_EFFECTS " + ledger.unsafeCount());

            System.out.println("=== GUARDED ===");
            String guarded = charges.guardedCharge("G-1");
            System.out.println("RESULT guarded=" + guarded);
            System.out.println("GUARDED_EFFECTS " + ledger.guardedCount());
        }
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

### 6.11. Stdout logic kỳ vọng

~~~text
IS_PROXY true
=== UNSAFE ===
RETRY unsafeCharge attempt=1
TARGET unsafeCharge U-1
LEDGER unsafe side_effect=1
GATE lost-ack unsafeCharge
RETRY caught unsafeCharge attempt=1
RETRY unsafeCharge attempt=2
TARGET unsafeCharge U-1
LEDGER unsafe side_effect=2
RESULT unsafe=charged:U-1
UNSAFE_EFFECTS 2
=== GUARDED ===
RETRY guardedCharge attempt=1
TARGET guardedCharge G-1
LEDGER guarded side_effect=1
GATE lost-ack guardedCharge
RETRY caught guardedCharge attempt=1
RETRY guardedCharge attempt=2
TARGET guardedCharge G-1
RESULT guarded=charged:G-1
GUARDED_EFFECTS 1
~~~

Những dòng này là **stdout logic dự kiến từ mã mẫu**, chưa bao gồm log riêng của Maven và Spring. Chương trình chạy hai kịch bản tuần tự, nên không có ordering bất định giữa chúng.

**UNSAFE:** Một lời gọi caller, hai lần `proceed()`, hai lần target, **hai side effects**. Lần đầu đã ghi nhận một side effect trước khi exception thoát ra. Kết quả thành công cuối cùng không xóa lần thực thi đầu.

**GUARDED:** Một lời gọi caller, hai lần `proceed()`, hai lần target, **một side effect được đếm**. Key `G-1` được giữ nguyên; lần hai map trả kết quả cũ. Đây là **idempotency mô phỏng trong cùng một JVM**, không bảo đảm hệ thống thanh toán thực không ghi nợ hai lần.

## 7. Vì sao in-memory guard không đủ cho production?

`ConcurrentHashMap` ở ví dụ chỉ bảo vệ key trong process đang chạy:

- Sau **restart**, dữ liệu key mất.
- Khi chạy **hai replicas**, mỗi process có map riêng.
- Nếu một side effect xảy ra ở remote service rồi JVM crash trước khi lưu kết quả key, app không có bằng chứng đã hoàn tất.
- Nếu request body khác nhau nhưng dùng trùng key, map có thể trả kết quả của operation không tương đương.
- Khi key hết hạn hoặc bị xóa, một retry muộn có thể thực thi lại operation.
- Nếu bên dưới còn gọi nhiều hệ thống không chia sẻ transaction, một key ở app layer không bảo đảm mọi side effect atomic.

Giải pháp cần được đặt ở **execution boundary**:

| Loại side effect | Hướng thiết kế cần xét |
| --- | --- |
| Thao tác DB nội bộ | Unique constraint, transaction và kết quả ghi theo operation ID |
| API thanh toán bên ngoài | Idempotency key **được bên nhận hỗ trợ theo contract** |
| Message/event | Outbox, message key, idempotent consumer và cơ chế dedupe |
| Gửi email/SMS | Tracking message ID, trạng thái gửi/ACK và quy tắc resend |
| Workflow nhiều hệ thống | Reconciliation, state machine và xử lý trạng thái unknown |

Không nên gọi tất cả các giải pháp trên là “exactly-once” tuyệt đối. Cần mô tả **phạm vi side effect**, nơi uniqueness được bảo đảm, và tình huống crash/replay thực tế.

## 8. Transaction advice và thứ tự retry aspect

Đây là vấn đề đặc biệt của **Spring AOP** khi service có `@Transactional`.

### 8.1. Retry bọc ngoài transaction advice

~~~text
RetryAspect (outer)
  |
  +-- proceed attempt 1
  |       |
  |       v
  |    TransactionInterceptor
  |       |
  |       +-- begin transaction #1
  |       +-- target ném lỗi
  |       +-- rollback theo policy
  |
  +-- proceed attempt 2
          |
          v
       TransactionInterceptor
          |
          +-- begin transaction #2
          +-- target chạy lại
          +-- commit nếu hợp lệ
~~~

Spring Framework có ví dụ **retry aspect với precedence cao hơn transaction advice** để mỗi lần thử có transaction mới. Cấu hình thứ tự có thể dùng `@Order` hoặc `Ordered`, nhưng kết quả còn phụ thuộc propagation mode và transaction đang tồn tại từ caller. Không chỉ thêm `@Order` rồi coi mọi attempt chắc chắn mở transaction mới.

### 8.2. Transaction bọc ngoài retry advice

~~~text
TransactionInterceptor (outer)
  |
  +-- một transaction context
           |
           +-- RetryAspect (inner)
                   |
                   +-- attempt 1: lỗi
                   +-- attempt 2: thử lại
~~~

Trong bố trí này, retries có thể ở **cùng một transaction**. Sau lỗi đầu, transaction hoặc database resource có thể đã bị đánh dấu rollback-only hay rơi vào trạng thái không an toàn để tiếp tục. Attempt thứ hai thành công ở mức method **không chắc** khiến toàn transaction commit.

Đồng thời, **DB rollback không thu hồi được một remote charge, email hoặc HTTP request đã hoàn tất**. Vì thế đặt retry ngoài transaction có thể cần thiết nhưng **không đủ** để bảo vệ external side effects.

### 8.3. Mẫu khai báo thứ tự

~~~java
@Aspect
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RetryAspect {
    // ...
}
~~~

Đây là **fragment minh họa cách khai báo thứ tự**, cần import `org.springframework.core.Ordered` và `org.springframework.core.annotation.Order`. Không đồng thời thêm class thứ hai tên RetryAspect vào project mẫu ở mục 6. Thứ tự ưu tiên không phải cơ chế chống duplicate; nó chỉ ảnh hưởng vị trí advice trong chain.

## 9. Logging, metrics và transaction có thể lặp theo số attempt khác nhau

Nếu `MetricsAspect` nằm **ngoài** `RetryAspect`:

~~~text
MetricsAspect
  |
  +-- RetryAspect
         |
         +-- proceed #1 -> target
         +-- proceed #2 -> target
~~~

Metrics có thể đo một logical invocation, trong khi target chạy hai lần.

Nếu `MetricsAspect` nằm **trong** retry:

~~~text
RetryAspect
  |
  +-- proceed #1 -> MetricsAspect -> target
  +-- proceed #2 -> MetricsAspect -> target
~~~

Metrics advice có thể chạy hai lần. Do đó cần đo **request count**, **retry attempt count** và **committed effect count** riêng biệt. Đừng suy ra số side effects chỉ từ số dòng log của một aspect khi chưa hiểu advisor ordering.

Một `@AfterThrowing` hoặc transaction advisor nằm phía trong cũng có thể được thực thi mỗi attempt. Nếu advice ở phía ngoài, nó có thể chỉ thấy kết quả/exception **sau cùng** từ retry aspect. Spring không đảm bảo thứ tự giữa các aspects khác nhau nếu ứng dụng không cấu hình rõ.

## 10. Bắt loại lỗi nào và kết thúc ra sao?

Một anti-pattern:

~~~java
try {
    return pjp.proceed();
} catch (Exception anything) {
    return pjp.proceed();
}
~~~

Đây là fragment **không an toàn**. Nó retry cả validation lỗi, permission denied, duplicate key không nên retry và lỗi do code. Nếu operation có side effect, kiểu catch này còn gây nhân tác động.

Một policy retry cần xác định:

1. **Exception whitelist hoặc predicate** cho lỗi thật sự tạm thời.
2. **Maximum attempts** và deadline tổng, không retry vô hạn.
3. **Backoff/jitter** để tránh các request đồng loạt đánh vào dịch vụ đang quá tải.
4. **Idempotency/reconciliation** cho trạng thái kết quả unknown.
5. **Phản hồi cuối cùng** khi hết attempts: exception hoặc status thất bại minh bạch, không tự trả chuỗi thành công.
6. **Observability**: correlation ID và attempt number.
7. **Cancel/interruption**: không nuốt trạng thái hủy hoặc interrupted thread.
8. **Giới hạn phạm vi pointcut** vào business operations đã được review là retryable.

Không dùng `catch(Throwable)` theo mặc định để retry mọi lỗi nghiêm trọng. Một exception tên “Transient” do thư viện ném ra vẫn cần được xem xét với **tác dụng phụ của method thực tế**.

## 11. Backoff, timeout budget và retry storm

Giả sử 100 lời gọi client gặp lỗi mạng cùng lúc. Nếu mỗi invocation có 3 attempts retry tức thì, số lượt target có thể tăng tới 300 trong một khoảng ngắn, khiến dịch vụ vốn đã quá tải càng chậm.

Hướng xử lý:

- Dùng bounded retry, không retry vô hạn.
- Cân nhắc backoff tăng dần và jitter khi nhiều clients cùng retry.
- Dành tổng **timeout budget** cho cả retries, không cộng từng attempt vô hạn.
- Nếu failure rate cao, cân nhắc circuit breaker/rate limiting phù hợp.
- Không dùng `Thread.sleep` dài trên thread xử lý HTTP một cách tùy tiện trong synchronous `@Around`.
- Xác nhận upstream/downstream có tự retry hay không để tránh **retry amplification nhiều tầng**.

Backoff chủ yếu điều chỉnh **tải và xác suất hồi phục**, không ngăn duplicate side effect; idempotency vẫn phải được thiết kế riêng.

## 12. Proxy boundary và self-invocation

Spring AOP chỉ advice những lời gọi đủ điều kiện **đi qua proxy**. Nếu một method trong target gọi method retryable bằng `this.method()`:

~~~java
public void process(String id) {
    this.unsafeCharge(id);
}
~~~

lời gọi nội bộ này không quay qua Spring AOP proxy, nên `RetryAspect` có thể **không được kích hoạt** cho unsafeCharge. Đó là tình huống khác với around advice đã chạy rồi gọi proceed hai lần.

Những hạn chế cần nhớ:

- **JDK dynamic proxy** expose các public interface methods phù hợp.
- **CGLIB** có thể advice các instance methods có thể override khi gọi qua class proxy, nhưng không override private/final methods.
- Bean tự tạo bằng `new` không được Spring AOP tự proxy.
- Pointcut quá rộng có thể chọn cả helper, recorder và gateway mà advice gọi tới, tạo recursion/retry lồng nhau.
- Nếu cần retry cho lời gọi nội bộ, ưu tiên tách operation sang Spring bean khác rồi inject proxy phù hợp, không tự ý dựa vào `AopContext.currentProxy()`.

Trong ví dụ mục 6, pointcut chỉ chọn các method thuộc `ChargeApi` để tránh tác động vào `ChargeLedger` và `AfterEffectFailureGate`.

## 13. Các bài test cần có

| Kịch bản | Phải kiểm chứng |
| --- | --- |
| Target thành công ngay attempt đầu | Target chạy đúng một lần, không có retry |
| Lỗi trước side effect rồi thành công | Retry đúng exception/attempt budget |
| **Lỗi sau side effect** rồi thành công | Phát hiện số side effects bị nhân lên khi không có idempotency |
| Cùng key được retry với guard | Số committed effects không tăng trong phạm vi bảo đảm |
| Exception không thuộc whitelist | Không retry |
| Hết attempts đều thất bại | Exception cuối thoát ra, không báo thành công giả |
| Cùng key nhưng payload khác | Có rule conflict rõ ràng |
| Hai logical operations khác nhau | Không bị dedupe nhầm |
| Concurrency cùng key | Kiểm tra atomicity thật ở storage/bên nhận |
| Nhiều replicas hoặc restart | Kiểm chứng durability, không dựa vào map một JVM |
| Có transaction advice | Verify advisor order và boundary từng attempt |
| Self-invocation | Không giả định retry sẽ chạy |
| Retry nested ở nhiều layers | Đo amplification và deadline |

Với ví dụ đang chạy, bổ sung trong `App.main` sau cả hai kịch bản:

~~~java
if (ledger.unsafeCount() != 2) {
    throw new AssertionError("Unsafe operation should have run twice");
}
if (ledger.guardedCount() != 1) {
    throw new AssertionError("Guarded effect should be recorded once");
}
~~~

Đây là **test fragment**, không phải file Java độc lập. Hai assertion là kết quả chủ đích của bài học để so sánh, **không phải khuyến nghị chấp nhận double charge ở hệ thống thật**.

## 14. Những lỗi phổ biến khi viết RetryAspect

| Triệu chứng | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| Một lệnh thanh toán bị tính hai lần | Retry sau side effect khi ACK bị mất | Idempotency tại provider hoặc reconciliation |
| Service trả thành công nhưng DB/event bị lặp | Caller thấy kết quả attempt cuối, không thấy side effect attempt đầu | Theo dõi committed effects và operation ID |
| Có maxAttempts=2 nhưng vẫn double action | Bounded retry không tự chống trùng | Bổ sung idempotency |
| Mỗi attempt tạo một UUID idempotency mới | Downstream coi mỗi attempt là operation khác | Giữ key ổn định cho logical operation |
| Guard hoạt động ở local nhưng không ở cluster | In-memory map theo JVM | Durable shared store hoặc idempotency của bên nhận |
| Retry cả lỗi validation | Catch quá rộng | Chỉ retry exception đã phân loại |
| Method thành công nhưng transaction rollback | Retry bên trong transaction đã rollback-only | Kiểm tra transaction advice order/boundary |
| DB rollback nhưng email vẫn gửi | External side effect ngoài transaction | Thiết kế outbox/idempotency và reconciliation |
| Retry không chạy khi gọi nội bộ | Self-invocation bỏ qua proxy | Refactor sang Spring bean khác |
| Retry aspect chạy cả trên recorder | Pointcut quá rộng | Restrict service API/package/annotation |
| Logging aspect đếm một request nhưng target hai lần | Logging nằm ngoài retry | Đếm logical requests và attempts riêng |
| Bị quá tải nặng hơn sau lỗi | Retry storm, không backoff/budget | Backoff/jitter/circuit breaker, giới hạn requests |
| Lỗi đã hết attempts nhưng caller vẫn nhận OK | Advice nuốt exception/trả fallback sai | Propagate error/status rõ ràng |

## 15. Checklist triển khai Spring AOP retry an toàn

- Đã liệt kê mọi side effect: DB, remote API, broker, email, cache, counter?
- Có thể khẳng định exception xảy ra **trước** tác động không? Nếu không, coi trạng thái là unknown.
- Operation có idempotency key ổn định qua các attempts không?
- Idempotency có được bên **thực hiện side effect** tôn trọng và lưu bền vững không?
- Có xử lý khi cùng key nhưng request body khác hoặc operation đang chạy không?
- Có giới hạn attempts, tổng deadline và backoff khi cần không?
- Chỉ bắt những exception được phân loại là retryable?
- Khi hết retries, có chuyển exception/status thật tới caller?
- Advisor ordering với `@Transactional` đã được kiểm chứng chưa?
- Các remote side effects có nằm ngoài local transaction không?
- Lời gọi có thật sự đi qua Spring proxy, không phải self-invocation?
- Pointcut có loại recorder, infrastructure và những method không retryable?
- Có test đặc biệt **lỗi sau side effect** với counter hoặc trạng thái hệ thống?
- Có test concurrency, restart và retries từ nhiều layers?
- Có metrics riêng cho **attempts** và **committed side effects**?

## 16. Câu hỏi tự đánh giá

**1. Vì sao gọi `pjp.proceed()` hai lần có thể nguy hiểm?**

Vì continuation của Spring AOP có thể đưa lời gọi đến target hai lần và các thao tác ghi dữ liệu/gửi yêu cầu trong target có thể bị nhân đôi.

**2. Timeout có nghĩa giao dịch trước chắc chắn chưa thành công không?**

Không. Phản hồi có thể mất sau khi bên nhận đã commit.

**3. maxAttempts=2 bảo đảm điều gì và không bảo đảm điều gì?**

Nó giới hạn số attempts tối đa theo retry aspect đó, nhưng **không bảo đảm mỗi logical operation chỉ có một side effect**.

**4. Có nên thay idempotency key ở attempt thứ hai không?**

Không. Các lần thử của cùng logical operation phải có cùng key theo contract.

**5. Vì sao `ConcurrentHashMap` trong demo không đủ cho production?**

Nó chỉ ở một process, mất khi restart, không đồng bộ giữa replicas và không atomic với remote side effects.

**6. Khi retry nằm ngoài Spring transaction advice thì có thể nhận transaction mới cho mỗi attempt không?**

Có thể, nếu ordering và transaction boundaries phù hợp; phải kiểm chứng với propagation/caller thực tế.

**7. DB rollback có thu hồi một email đã gửi không?**

Thông thường không; đó là side effect ngoài transaction DB.

**8. Retry aspect có hoạt động cho `this.method()` trong cùng target không?**

Không qua self-invocation thông thường, vì lời gọi ấy bỏ qua Spring AOP proxy.

**9. Bằng chứng tốt nhất cho việc guard hoạt động là gì?**

Kiểm tra **committed side effect count hoặc trạng thái hệ thống**, không chỉ response hay số dòng log của advice.

**10. Nếu remote operation không có idempotency và kết quả timeout unknown thì nên làm gì?**

Không retry mù; cần tra cứu/reconcile trạng thái hoặc thiết kế idempotency với bên nhận trước.

## 17. Nguồn tham khảo chính thức

- Spring Framework — **Declaring Advice / Around Advice**, cách `proceed()` có thể gọi nhiều lần: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — **An AOP Example**, retry aspect và thứ tự ưu tiên trước transaction advice: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/example.html
- Spring Framework — **Proxying Mechanisms**, JDK/CGLIB và self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — **Declarative Transaction Management**, transaction advice: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — **@AspectJ Support**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html

**Kết luận:** Với Spring `@Around`, retry bằng cách gọi `ProceedingJoinPoint.proceed()` lần nữa có thể kích hoạt lại target và những advice phía trong. Nếu lần đầu đã tạo side effect rồi mới thất bại, caller chỉ thấy một kết quả thành công nhưng tác động nghiệp vụ có thể xảy ra nhiều lần. Phân loại exception, giới hạn attempts, kiểm soát transaction advisor và backoff là quan trọng; **idempotency/reconciliation ở đúng nơi thực hiện side effect** mới giải quyết nguy cơ duplicate thực sự.

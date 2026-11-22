# Kết hợp kiểm tra đồng bộ và reactive trong ứng dụng WebFlux

## 1. WebFlux không làm mọi thư viện trở thành không chặn

Một ứng dụng WebFlux có thể đồng thời sử dụng một SDK cũ chỉ cung cấp phương thức đồng bộ và một client mới trả về `Mono`. Khi công bố health, ta vẫn cần quan sát cả hai thành phần. Vấn đề không chỉ là ghép hai kết quả vào JSON, mà còn là **thực hiện từng phép kiểm tra trên cơ chế thực thi phù hợp**.

Luồng xử lý sự kiện (event loop) được dùng để xử lý nhiều công việc không chặn. Nếu một phép kiểm tra giữ luồng đó để chờ I/O đồng bộ, những yêu cầu khác có thể bị chậm theo. Đổi kiểu trả về thành `Mono<Health>` không tự di chuyển đoạn mã đang chặn sang luồng khác.

Trong bài này, ứng dụng có:

- `legacyStore`: một phép kiểm tra đồng bộ, đại diện cho thư viện cũ có thể chặn luồng.
- `catalog`: một phép kiểm tra reactive, đại diện cho client cung cấp kết quả bất đồng bộ.

Ta giữ hai hợp đồng đúng bản chất, để Actuator chuyển đổi indicator đồng bộ và tổng hợp chúng trong luồng reactive. Ví dụ độc lập dùng **Java 21, Spring Boot 3.3.0 và Reactor 3.6.6 do phiên bản Boot này quản lý**.

## 2. Hai hợp đồng cùng tồn tại trong cây health

| Hợp đồng | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `HealthIndicator` | `Health` | Phương thức trả kết quả trực tiếp; có thể chứa thao tác đồng bộ. |
| `ReactiveHealthIndicator` | `Mono<Health>` | Kết quả được phát qua publisher; việc lấy kết quả phải tuân theo hợp đồng reactive. |
| `ReactiveHealthContributorRegistry` | Các contributor theo tên | Cây thành phần mà đường công bố health reactive sử dụng. |

Trong ứng dụng reactive, cấu hình Actuator có thể thu nhận cả `HealthContributor` thông thường và `ReactiveHealthContributor`. Contributor đồng bộ được chuyển đổi sang hợp đồng reactive; ứng dụng không cần viết lại mọi indicator đồng bộ chỉ để nó xuất hiện trong WebFlux.

Với Spring Boot 3.3.0, adapter của một `HealthIndicator` sử dụng:

```java
Mono.fromCallable(delegate::health)
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là đoạn trích cơ chế, không phải một tệp Java độc lập. `fromCallable` trì hoãn lời gọi tới khi có đăng ký nhận kết quả; `subscribeOn` bố trí lời gọi đó trên scheduler phù hợp cho công việc có thể chặn. Xem [HealthIndicatorReactiveAdapter của Spring Boot 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthIndicatorReactiveAdapter.java).

Cách chuyển đổi thay đổi **nơi chờ**, không biến client đồng bộ thành client I/O không chặn. Khi SDK cũ chờ dữ liệu, một worker vẫn đang bị chiếm. Vì vậy, thời gian chờ, giới hạn kết nối và lượng công việc đồng thời vẫn cần được kiểm soát.

### Đăng ký bean thông thường và đăng ký động là hai trường hợp

Với bean khởi tạo cùng ứng dụng, thường chỉ cần khai báo một bean `HealthIndicator` và một bean `ReactiveHealthIndicator`; cấu hình Actuator thực hiện việc thu nhận/chuyển đổi. Không tạo thêm một bean wrapper cho cùng phép kiểm tra chỉ để “chắc chắn có reactive”, vì có thể tạo mục trùng hoặc chạy kiểm tra hai lần.

Nếu chủ động đăng ký contributor khi ứng dụng đang chạy, hãy dùng `ReactiveHealthContributorRegistry`; một contributor đồng bộ cần được chuyển đổi bằng `ReactiveHealthContributor.adapt(...)` trước khi đăng ký. Đây là quy tắc của [health reactive trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.reactive-health-indicators).

Không chọn implementation chỉ từ tên sản phẩm như Redis hoặc MongoDB. Một số tích hợp có cả biến thể đồng bộ và reactive; cần đọc contributor thực tế và điều kiện cấu hình của phiên bản đang dùng.

## 3. Bốn nhầm lẫn làm mã chặn lọt vào event loop

Các đoạn sau là minh họa tại một vị trí đã có biến `legacy` kiểu `HealthIndicator`.

### Gọi trước rồi mới bọc bằng Mono

```java
return Mono.just(legacy.health());
```

Đối số của `Mono.just` được Java tính trước. `legacy.health()` đã chạy trên luồng gọi ngay trong lúc tạo publisher. Thêm `publishOn(...)` phía sau không thể chuyển một lời gọi đã hoàn tất hoặc đang chặn trước đó sang luồng khác.

### Trì hoãn nhưng chưa chọn scheduler

```java
return Mono.fromCallable(legacy::health);
```

Đoạn này đã trì hoãn, nhưng không tự chọn worker cho công việc chặn. Nó có thể chạy trên luồng đang đăng ký, bao gồm event loop. Khi thật sự cần tự bọc một lời gọi đồng bộ, dùng mẫu `fromCallable(...).subscribeOn(Schedulers.boundedElastic())` hoặc adapter của Actuator.

### Tưởng Mono.defer tự chuyển luồng

```java
return Mono.defer(() -> Mono.just(legacy.health()));
```

`defer` trì hoãn việc tạo publisher, không phải công tắc đổi scheduler. Supplier của nó vẫn phải không chặn nếu đang chạy trên luồng không chặn.

### Gọi block hoặc subscribe trong indicator reactive

Gọi `.block()` có thể giữ luồng phục vụ request và phá vỡ mục đích của WebFlux. Gọi `.subscribe()` rồi trả một `Health` khác ngay lập tức lại khiến kết quả công bố không còn chờ phép kiểm tra thật. Hãy **trả về chuỗi `Mono<Health>` hoàn chỉnh**, để hạ tầng đăng ký và chờ tín hiệu theo cơ chế reactive.

Không dùng `publishOn` như cách chữa chung cho mọi vị trí. Nó tác động đến phần xử lý tín hiệu phía sau vị trí đặt operator; mẫu được khuyến nghị cho nguồn đồng bộ chặn là đặt `subscribeOn` ngay sau nguồn. Có thể đối chiếu [hướng dẫn bọc lời gọi chặn của Reactor](https://projectreactor.io/docs/core/3.6.6/reference/#faq.wrap-blocking).

## 4. Tạo hai indicator có trách nhiệm riêng

Tạo một dự án Maven độc lập. Chỉ thêm starter WebFlux cho web stack của ví dụ, không thêm `spring-boot-starter-web`.

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>learning</groupId>
    <artifactId>mixed-health-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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

### 4.1. Indicator đồng bộ

Tệp `src/main/java/learning/mixedhealth/LegacyStoreHealthIndicator.java`:

```java
package learning.mixedhealth;

import java.util.Objects;
import java.util.concurrent.Callable;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;

public final class LegacyStoreHealthIndicator implements HealthIndicator {

    private final Callable<Boolean> check;

    public LegacyStoreHealthIndicator(Callable<Boolean> check) {
        this.check = Objects.requireNonNull(check, "check");
    }

    @Override
    public Health health() {
        try {
            return Boolean.TRUE.equals(check.call())
                    ? Health.up().withDetail("reason", "READY").build()
                    : Health.down().withDetail("reason", "NOT_READY").build();
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return Health.down().withDetail("reason", "INTERRUPTED").build();
        }
        catch (Exception ex) {
            return Health.down().withDetail("reason", "CHECK_FAILED").build();
        }
    }
}
```

Đây vẫn là một indicator đồng bộ. Nó không tự tạo thread hoặc tự bọc `Mono`. Khi được lấy qua cây health reactive của Actuator, adapter thực hiện phần chuyển đổi. Nếu một đoạn mã khác gọi trực tiếp `legacy.health()`, lời gọi trực tiếp đó không tự có adapter.

`Callable<Boolean>` là đầu nối để ví dụ đưa vào một phép kiểm tra khác nhau. Trong tích hợp thật, nó có thể gọi SDK cũ đã được cấu hình timeout. Indicator không được dùng phép thử làm thay đổi dữ liệu nghiệp vụ.

### 4.2. Indicator reactive

Tệp `src/main/java/learning/mixedhealth/CatalogReactiveHealthIndicator.java`:

```java
package learning.mixedhealth;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.ReactiveHealthIndicator;

import reactor.core.publisher.Mono;

public final class CatalogReactiveHealthIndicator implements ReactiveHealthIndicator {

    private final Supplier<Mono<Boolean>> check;
    private final Duration timeout;

    public CatalogReactiveHealthIndicator(Supplier<Mono<Boolean>> check, Duration timeout) {
        this.check = Objects.requireNonNull(check, "check");
        this.timeout = Objects.requireNonNull(timeout, "timeout");
        if (timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("timeout must be positive");
        }
    }

    @Override
    public Mono<Health> health() {
        return Mono.defer(check)
                .map(ready -> ready
                        ? Health.up().withDetail("reason", "READY").build()
                        : Health.down().withDetail("reason", "NOT_READY").build())
                .switchIfEmpty(Mono.fromSupplier(() ->
                        Health.down().withDetail("reason", "EMPTY_RESPONSE").build()))
                .timeout(timeout)
                .onErrorResume(TimeoutException.class, ex -> Mono.just(
                        Health.down().withDetail("reason", "TIMEOUT").build()))
                .onErrorResume(Exception.class, ex -> Mono.just(
                        Health.down().withDetail("reason", "CHECK_FAILED").build()));
    }
}
```

Hợp đồng của `check` ở đây là phát đúng một `Boolean` cho kết quả kiểm tra. Supplier chỉ tạo một chuỗi reactive không chặn; nếu nó gọi SDK chặn trước khi trả `Mono`, `defer` cũng không thể cứu thiết kế đó.

Các phần của chuỗi có vai trò riêng:

1. `defer` tạo phép thử mới khi có đăng ký; exception thông thường phát sinh trong lúc gọi supplier cũng đi vào chuỗi lỗi.
2. `map` biến kết quả có giá trị thành một `Health`.
3. `switchIfEmpty` biến việc hoàn tất không có giá trị thành `DOWN/EMPTY_RESPONSE`, theo hợp đồng của ví dụ.
4. `timeout` giới hạn thời gian chờ tín hiệu của chuỗi này.
5. `onErrorResume` chuyển timeout hoặc lỗi thông thường thành một kết quả health an toàn.

Không thêm `subscribeOn(boundedElastic())` vào mọi client reactive chỉ vì có async. Với client vốn không chặn, hãy giữ chuỗi reactive của nó; chỉ tách phần thật sự chặn khi có bằng chứng cần tách.

## 5. Kiểm chứng trì hoãn, scheduler và các kiểu kết quả

Tệp `src/main/java/learning/mixedhealth/MixedHealthDemo.java`:

```java
package learning.mixedhealth;

import java.time.Duration;
import java.util.Objects;
import java.util.HashSet;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.ReactiveHealthContributor;
import org.springframework.boot.actuate.health.ReactiveHealthIndicator;
import org.springframework.boot.actuate.health.SimpleStatusAggregator;
import org.springframework.boot.actuate.health.Status;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public class MixedHealthDemo {

    private static final Duration WAIT = Duration.ofSeconds(5);

    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();
        AtomicReference<Boolean> ranOnNonBlockingThread = new AtomicReference<>();
        var legacy = new LegacyStoreHealthIndicator(() -> {
            calls.incrementAndGet();
            ranOnNonBlockingThread.set(Schedulers.isInNonBlockingThread());
            Thread.sleep(20);
            return true;
        });
        var adapted = (ReactiveHealthIndicator) ReactiveHealthContributor.adapt(legacy);
        Mono<Health> pending = adapted.health();
        if (calls.get() != 0) {
            throw new AssertionError("Legacy check ran before subscription");
        }
        System.out.println("legacyBeforeSubscribe=" + calls.get());

        Scheduler eventLoop = Schedulers.newSingle("health-event-loop-demo");
        try {
            Health legacyResult = Objects.requireNonNull(pending.subscribeOn(eventLoop).block(WAIT));
            if (!Status.UP.equals(legacyResult.getStatus())
                    || !Boolean.FALSE.equals(ranOnNonBlockingThread.get())) {
                throw new AssertionError("Legacy check was not isolated correctly");
            }
            System.out.println("legacy=" + legacyResult.getStatus().getCode());
            System.out.println("legacyRanOnNonBlockingThread=" + ranOnNonBlockingThread.get());

            verify("reactive", () -> Mono.delay(Duration.ofMillis(20)).map(value -> true),
                    Status.UP, "READY");
            verify("reactiveDown", () -> Mono.just(false), Status.DOWN, "NOT_READY");
            verify("reactiveError", () -> Mono.error(new IllegalStateException("test error")),
                    Status.DOWN, "CHECK_FAILED");
            verify("reactiveEmpty", Mono::empty, Status.DOWN, "EMPTY_RESPONSE");
            verify("reactiveTimeout", Mono::never, Status.DOWN, "TIMEOUT");
            verify("factoryError", () -> { throw new IllegalStateException("factory error"); },
                    Status.DOWN, "CHECK_FAILED");

            var failedCatalog = new CatalogReactiveHealthIndicator(() -> Mono.just(false), Duration.ofSeconds(1));
            Status mixed = Objects.requireNonNull(Mono.zip(adapted.health(), failedCatalog.health())
                    .map(pair -> {
                        var statuses = new HashSet<Status>();
                        statuses.add(pair.getT1().getStatus());
                        statuses.add(pair.getT2().getStatus());
                        return new SimpleStatusAggregator().getAggregateStatus(statuses);
                    }).block(WAIT));
            if (!Status.DOWN.equals(mixed)) {
                throw new AssertionError("Unexpected mixed result");
            }
            System.out.println("mixed=" + mixed.getCode());
        }
        finally {
            eventLoop.dispose();
        }
    }

    private static void verify(String name, Supplier<Mono<Boolean>> source, Status expected, String reason) {
        var indicator = new CatalogReactiveHealthIndicator(source, Duration.ofMillis(200));
        Health result = Objects.requireNonNull(indicator.health().block(WAIT));
        if (!expected.equals(result.getStatus()) || !reason.equals(result.getDetails().get("reason"))) {
            throw new AssertionError("Unexpected result for " + name + ": " + result);
        }
        System.out.println(name + "=" + result.getStatus().getCode());
    }
}
```

**Phạm vi của chương trình kiểm tra:** `Thread.sleep(20)` chỉ mô phỏng SDK chặn. `Mono.delay` tạo độ trễ bất đồng bộ, không gọi dịch vụ mạng thật. `Schedulers.newSingle` cung cấp một scheduler mang đặc tính luồng không chặn để thử đường đăng ký; nó không phải Reactor Netty HTTP event loop thật.

Các lệnh `.block(...)` chỉ nằm trong chương trình dòng lệnh, nơi luồng `main` cần chờ kết quả để kiểm chứng. Không sao chép chúng vào indicator, controller WebFlux hoặc xử lý request. Chương trình chỉ hủy scheduler mà nó tự tạo; không hủy các scheduler dùng chung của Reactor.

Trong thư mục dự án, kiểm tra Maven đang dùng JDK 21 rồi chạy:

```shell
mvn -version
mvn compile dependency:build-classpath "-Dmdep.outputFile=target/classpath.txt"
```

Trên PowerShell:

```powershell
$dependencyClasspath = (Get-Content -Raw -LiteralPath 'target/classpath.txt').Trim()
java -cp "target/classes;$dependencyClasspath" learning.mixedhealth.MixedHealthDemo
```

Trên Linux/macOS:

```shell
java -cp "target/classes:$(cat target/classpath.txt)" learning.mixedhealth.MixedHealthDemo
```

Maven đã thực hiện bước biên dịch Java và giải quyết classpath. Không biên dịch riêng một tệp bằng `javac` khi chưa cung cấp các thư viện Spring Boot và Reactor cần thiết.

Stdout của chương trình là:

```text
legacyBeforeSubscribe=0
legacy=UP
legacyRanOnNonBlockingThread=false
reactive=UP
reactiveDown=DOWN
reactiveError=DOWN
reactiveEmpty=DOWN
reactiveTimeout=DOWN
factoryError=DOWN
mixed=DOWN
```

Chương trình không in tên luồng cụ thể vì tên và số thứ tự worker có thể thay đổi giữa các lần chạy. Bằng chứng cần kiểm tra là: chưa đăng ký thì SDK chưa chạy; khi đã đăng ký từ scheduler không chặn, lời gọi SDK được adapter chuyển sang worker phù hợp.

Đoạn `Mono.zip` chỉ minh họa cách ghép hai kết quả trong chương trình kiểm tra. Ứng dụng Actuator bình thường không cần một indicator tổng tự viết chỉ để gom lại các bean đã đăng ký.

## 6. Để Actuator thu nhận hai loại bean trong WebFlux

Tệp `src/main/java/learning/mixedhealth/MixedHealthApplication.java`:

```java
package learning.mixedhealth;

import java.time.Duration;
import java.util.function.Supplier;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class MixedHealthApplication {

    public static void main(String[] args) {
        SpringApplication.run(MixedHealthApplication.class, args);
    }

    @Bean
    LegacyStoreHealthIndicator legacyStoreHealthIndicator(
            @Value("${demo.legacy-up:true}") boolean ready) {
        return new LegacyStoreHealthIndicator(() -> {
            Thread.sleep(80);
            return ready;
        });
    }

    @Bean
    CatalogReactiveHealthIndicator catalogHealthIndicator(
            @Value("${demo.catalog-mode:up}") String mode) {
        Supplier<Mono<Boolean>> probe = switch (mode) {
            case "up" -> () -> Mono.delay(Duration.ofMillis(40)).map(value -> true);
            case "down" -> () -> Mono.just(false);
            case "error" -> () -> Mono.error(new IllegalStateException("simulated error"));
            case "empty" -> Mono::empty;
            case "never" -> Mono::never;
            case "factoryError" -> () -> { throw new IllegalStateException("simulated factory error"); };
            default -> throw new IllegalArgumentException("Unsupported catalog demo mode");
        };
        return new CatalogReactiveHealthIndicator(probe, Duration.ofMillis(500));
    }
}
```

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health
management.endpoint.health.show-components=always
management.endpoint.health.show-details=always
management.endpoint.health.group.dependencies.include=legacyStore,catalog
```

Ví dụ cố ý dùng các nguồn mô phỏng để tập trung vào cách kết hợp và scheduling; `Thread.sleep(80)` không phải cách kiểm tra kho dữ liệu trong sản phẩm. Khi thay bằng client thật, giữ nguyên ranh giới đồng bộ/reactive và cấu hình timeout phù hợp cho client đó.

Hai bean có tên `legacyStoreHealthIndicator` và `catalogHealthIndicator`, nên contributor tương ứng là `legacyStore` và `catalog`. Không khai báo thêm wrapper bean cho legacy: Actuator thực hiện chuyển đổi khi thu nhận vào registry reactive.

Chạy ứng dụng:

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.mixedhealth.MixedHealthApplication"
```

Ở terminal khác:

```shell
curl -i http://127.0.0.1:8080/actuator/health/dependencies
curl -i http://127.0.0.1:8080/actuator/health/legacyStore
curl -i http://127.0.0.1:8080/actuator/health/catalog
```

Trên Windows có thể dùng `mvn.cmd` và `curl.exe`. Với cấu hình mặc định, nhóm `dependencies` có hai thành phần `UP`; phần thân có cấu trúc:

```json
{
  "status": "UP",
  "components": {
    "catalog": { "status": "UP", "details": { "reason": "READY" } },
    "legacyStore": { "status": "UP", "details": { "reason": "READY" } }
  }
}
```

Thứ tự khóa JSON không mang ý nghĩa. Nhóm được chọn chỉ gồm hai contributor của ví dụ, giúp tránh nhầm trạng thái của chúng với các thành phần mặc định khác ở endpoint tổng.

Dừng ứng dụng rồi thử catalog không phát tín hiệu:

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.mixedhealth.MixedHealthApplication" "-Dspring-boot.run.arguments=--demo.catalog-mode=never"
```

Sau hạn chờ của catalog, nhánh `catalog` trả `DOWN` với `reason=TIMEOUT`; nhóm `dependencies` trả `DOWN` và HTTP `503` theo mapping mặc định. Đổi đối số thành `--demo.catalog-mode=empty` để thấy `EMPTY_RESPONSE`, hoặc `--demo.legacy-up=false` để thấy `legacyStore` trả `NOT_READY`.

Chi tiết được hiển thị đầy đủ trên loopback để quan sát. Trong vận hành, cần chọn quyền truy cập và chính sách hiển thị phù hợp; không đưa thông tin xác thực hoặc lỗi nhạy cảm vào custom details.

## 7. Sự khác nhau giữa lỗi, hoàn tất rỗng và timeout

### Publisher phát lỗi

Lỗi có thể xuất hiện khi đã đăng ký, sau khi phương thức `health()` trả về. Một `try/catch` chỉ bao quanh việc tạo publisher không xử lý được mọi tín hiệu `onError` về sau. Cần xử lý trong chuỗi, như `onErrorResume`, hoặc dùng lớp hỗ trợ reactive phù hợp với chính sách của ứng dụng.

`Mono.defer(check)` còn giúp đưa exception thông thường ném ngay trong supplier vào đường lỗi của chuỗi. Nó không bảo vệ một công việc đã bị thực hiện trước khi gọi `defer`, và cũng không làm một supplier chặn trở thành không chặn.

### Publisher hoàn tất rỗng

Với `Mono<Boolean>` của bài, hoàn tất rỗng nghĩa là không có bằng chứng `true/false`; ta chủ động trả `DOWN/EMPTY_RESPONSE`. Nếu bỏ qua việc này, một phép ghép như `zip` có thể hoàn tất mà không tạo ra bộ kết quả như mong đợi.

Tuy nhiên, **không được coi mọi Mono rỗng là lỗi**. Có API dùng `Mono<Void>` để báo thành công bằng việc hoàn tất bình thường mà không có giá trị. Với hợp đồng đó, cần chuyển tín hiệu hoàn tất thành `Health`, chẳng hạn:

```java
return client.verify()
        .timeout(Duration.ofMillis(500))
        .thenReturn(Health.up().build())
        .onErrorResume(Exception.class, ex -> Mono.just(Health.down().build()));
```

Đoạn này là minh họa cho một `client.verify()` có kiểu `Mono<Void>`, không phải một chương trình độc lập. `thenReturn` nằm sau `timeout` để thành công không có giá trị vẫn tạo được một `Health`; lỗi upstream vẫn đi tới nhánh xử lý lỗi. Không dùng `thenReturn(UP)` để biến một kết quả có giá trị `false` thành khỏe.

### Publisher không phát tín hiệu

`Mono.never()` không hoàn tất, không phát giá trị và không phát lỗi. Operator `timeout` của ví dụ chuyển tình huống chờ quá hạn thành một tín hiệu lỗi rồi ánh xạ sang `DOWN/TIMEOUT`.

Timeout ở mức chuỗi là giới hạn chờ của subscriber, không phải bằng chứng rằng mọi thao tác I/O bên dưới đã dừng tức thì. Cần cả timeout của client và cơ chế hủy phù hợp. Nếu client ngắt kết nối hoặc chuỗi bị hủy, không được giả định `onErrorResume` luôn chạy và công bố một status cuối cùng; hủy đăng ký không đồng nhất với một tín hiệu lỗi.

## 8. Khi nào cần tự bọc đồng bộ trong một ReactiveHealthIndicator?

Giữ `HealthIndicator` và để Actuator chuyển đổi là lựa chọn rõ ràng khi đã có indicator đồng bộ hoàn chỉnh. Nhưng nếu đang xây dựng một indicator reactive tổng hợp nhiều bước, có thể có một bước bắt buộc gọi SDK cũ. Khi ấy cần bọc **riêng bước đó**, không chặn toàn bộ chuỗi.

Mẫu tại vị trí đã có `legacy` là:

```java
Mono<Health> legacyResult = Mono.fromCallable(legacy::health)
        .subscribeOn(Schedulers.boundedElastic());
```

Sau đó ghép `legacyResult` với nguồn reactive bằng operator phù hợp, đồng thời chuẩn hóa lỗi/rỗng ở từng nguồn theo hợp đồng. Mẫu không làm cho SDK có backpressure ở tầng mạng và không tự giới hạn timeout của SDK.

`boundedElastic` có giới hạn tài nguyên và hàng đợi; nó không phải kho thread vô hạn. Khi có nhiều yêu cầu health cùng chờ dịch vụ chậm, thời gian xếp hàng cũng có thể tăng. Tránh tạo scheduler hoặc executor mới trong mỗi lần health. Nếu cần pool riêng để cách ly một SDK, phải quản lý vòng đời, giới hạn và việc giải phóng tài nguyên của pool đó.

Với hai bean thông thường của bài, không cần bước tự bọc này. Cũng không dùng một `ReactiveHealthIndicator` để gọi trực tiếp `legacy.health()` rồi cho rằng framework sẽ nhận ra phần chặn bên trong: framework đã nhận một hợp đồng reactive và không tự phân tích thân phương thức để di chuyển mã hộ ứng dụng.

## 9. Kiểm tra ứng dụng thực sự chạy bằng web stack nào

Có `Mono` trên classpath hoặc có `ReactiveHealthIndicator` chưa đủ chứng minh HTTP đang được phục vụ bằng WebFlux. Khi cả Spring MVC và WebFlux cùng hiện diện, lựa chọn web stack mặc định của Boot có thể là Servlet/MVC.

Vì vậy, với dự án thật cần kiểm tra dependency runtime, điều kiện auto-configuration và loại application context đang chạy. Không thêm starter Servlet chỉ để có một dependency tiện dùng rồi mặc định cho rằng event loop WebFlux vẫn là đường phục vụ HTTP.

Ví dụ chỉ khai báo WebFlux và Actuator. Nếu chuyển vào một repository có orchestration tự thêm starter theo loại module, phải kiểm tra cấu hình hiệu lực của module, không chỉ nhìn đoạn `dependencies` vừa viết.

`HealthContributorRegistry` và `ReactiveHealthContributorRegistry` có vai trò khác nhau. Khi kiểm tra đường reactive, cần quan sát registry và web extension của đúng đường đó; một lời gọi trực tiếp tới API đồng bộ không chứng minh cách HTTP WebFlux đang thực thi. Việc truy cập reactive qua một cầu nối đồng bộ có thể phải chờ kết quả, nên không dùng nó trong event loop.

## 10. Kiểm thử điều gì để có bằng chứng thực tế?

| Cần chứng minh | Cách kiểm tra có ý nghĩa |
| --- | --- |
| Chưa đăng ký thì chưa chạy SDK | Dùng bộ đếm trước khi subscribe. |
| SDK chặn không chạy trên luồng không chặn | Ghi nhận `Schedulers.isInNonBlockingThread()` bên trong SDK mô phỏng, khi nguồn được đăng ký từ scheduler không chặn. |
| Native reactive không bị chuyển thành chặn | Kiểm tra chuỗi không có `.block()`, không gọi SDK đồng bộ trong supplier/map chạy trên event loop. |
| Mỗi nguồn có kết quả rõ ràng | Thử `true`, `false`, lỗi bất đồng bộ, lỗi tạo nguồn, hoàn tất rỗng và không có tín hiệu. |
| Tự động chuyển đổi đúng | Khởi tạo context WebFlux, kiểm tra registry có cả `legacyStore` và `catalog` mà không có wrapper trùng. |
| HTTP dùng cùng chính sách | Gọi nhóm health bằng WebTestClient hoặc HTTP thật, kiểm tra `UP/200` và `DOWN/503`. |
| Timeout/hủy có hiệu lực với client thật | Đo hành vi khi mạng chậm hoặc bị hủy; nguồn mô phỏng chưa chứng minh phần này. |

Với kiểm thử Reactor, có thể dùng `StepVerifier` và thời gian ảo cho chuỗi có timer; phải tạo chuỗi bên trong supplier thời gian ảo để operator dùng scheduler kiểm thử. Không dùng một lần `Thread.sleep()` dài rồi coi đó là bằng chứng ổn định của timeout hay khả năng không chặn.

Khi đo hiệu năng, không lấy tên thread hoặc một phép thử ngắn làm bằng chứng rằng hệ thống chịu tải tốt. Cần quan sát thêm thời lượng health, thời gian xếp hàng, số kết nối và giới hạn đồng thời của client. Việc adapter bảo vệ event loop vẫn có thể đi kèm pool bị bão hòa khi dịch vụ phụ thuộc chậm.

Những lỗi nên tìm đầu tiên khi health WebFlux treo hoặc chậm là: lời gọi thực hiện trước `Mono.just`, nguồn đồng bộ không được chuyển scheduler, `.block()` trong chuỗi request, publisher không có tín hiệu nhưng thiếu timeout, và mã chặn được giấu sau một kiểu trả về reactive.

# Xây dựng ReactiveHealthIndicator mà không chặn luồng xử lý reactive

Một endpoint health thường thực hiện lời gọi đến cơ sở dữ liệu, bộ nhớ đệm hoặc dịch vụ khác. Trong ứng dụng reactive, nếu phép kiểm tra giữ một luồng xử lý để chờ I/O, chính endpoint dùng để quan sát sức khỏe có thể làm giảm khả năng phục vụ của ứng dụng.

`ReactiveHealthIndicator` trả về `Mono<Health>`, nhưng kiểu trả về đó chưa bảo đảm phần việc bên trong không chặn. Cần thiết kế cả **nguồn dữ liệu, thời điểm thực thi, scheduler, giới hạn thời gian và đường xử lý lỗi**.

Bài dùng Java 21, Spring Boot 3.3.x và Reactor 3.6.x. Phần chạy độc lập cố định Boot 3.3.0, Reactor 3.6.6 và Spring Framework 6.1.8 để kiểm chứng các ví dụ.

## 1. Hợp đồng reactive của một lần kiểm tra health

`ReactiveHealthIndicator` có phương thức chính:

```java
Mono<Health> health();
```

Đây là chữ ký trong interface, không phải chương trình độc lập. `Mono` biểu diễn một chuỗi có thể phát tối đa một giá trị hoặc hoàn tất không có giá trị, hoặc kết thúc bằng lỗi. [API ReactiveHealthIndicator của Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/ReactiveHealthIndicator.html).

Với một indicator do mình viết, nên định nghĩa rõ kết quả cho những trường hợp thông thường:

| Kết quả quan sát | Chính sách minh họa trong bài |
| --- | --- |
| Phụ thuộc đáp ứng điều kiện kiểm tra | Phát một Health UP |
| Phụ thuộc trả kết quả không đạt | Phát một Health DOWN |
| Publisher hoàn tất nhưng không có dữ liệu | Phát UNKNOWN kèm nguyên nhân EMPTY_REPLY |
| Hết ngân sách thời gian | Phát DOWN kèm nguyên nhân PROBE_TIMEOUT |
| Phép kiểm tra phát lỗi | Phát DOWN với nguyên nhân đã chọn lọc |
| Bên gọi hủy đăng ký | Truyền hủy lên nguồn, dọn tài nguyên theo hợp đồng của nguồn |

Chính sách UNKNOWN cho kết quả rỗng là lựa chọn của ví dụ. Một hệ thống khác có thể coi đó là DOWN. Điều quan trọng là lựa chọn có chủ đích, thay vì vô tình trả `Mono.empty()` rồi không biết vì sao thiếu một kết quả health.

Hạ tầng reactive của Actuator kết hợp các contributor để tạo phản hồi. Indicator nên trả publisher cho hạ tầng đó quản lý việc đăng ký, thay vì tự kích hoạt công việc tách rời. [Reactive health trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.reactive-health-indicators).

## 2. Vì sao chặn một luồng reactive lại có tác động lớn?

Trong cách xử lý theo vòng lặp sự kiện (event loop), một số lượng luồng hạn chế có thể phục vụ nhiều kết nối. Khi chưa có dữ liệu I/O, công việc được tiếp tục khi sự kiện đến, thay vì giữ luồng ở trạng thái chờ.

Nếu một callback trên luồng đó thực hiện lời gọi JDBC đồng bộ, đọc tệp chậm hoặc `Thread.sleep`, luồng bị giữ lại. Các tác vụ khác cần cùng luồng phải chờ dù chúng không liên quan đến phép kiểm tra health.

```text
API reactive thực sự:
gửi yêu cầu → trả quyền điều khiển → nhận tín hiệu → tạo Health

API đồng bộ đặt trực tiếp trên luồng reactive:
gửi yêu cầu → giữ luồng chờ I/O → nhận kết quả → tạo Health
```

Các thao tác thường cần kiểm tra kỹ:

- Lời gọi mạng đồng bộ.
- JDBC hoặc SDK đồng bộ.
- Đọc/ghi tệp có thể chờ.
- `block()`, `Future.get()`, `join()` hoặc chờ khóa.
- Tính toán nặng trong `map` hay trong callback nhận kết quả.
- Ghi log hoặc gọi mã tiện ích có I/O đồng bộ trên đường thực thi.

Không phải cứ dùng `map` là sai. Chuyển một boolean thành `Health` hoặc thêm vài trường chẩn đoán là công việc ngắn, phù hợp để thực hiện ngay trong chuỗi. Cần đánh giá phần việc thực sự được gọi bên trong callback.

## 3. Tạo Mono đúng thời điểm

Có ba thời điểm cần phân biệt:

1. Gọi phương thức `health()` để nhận publisher.
2. Hạ tầng đăng ký vào publisher.
3. Nguồn phát dữ liệu và các callback xử lý dữ liệu chạy.

Trong các đoạn minh họa sau, `syncClient.ping()` là lời gọi I/O đồng bộ hiện có của ứng dụng.

### 3.1. Mono.just không trì hoãn phép gọi đã đặt trong tham số

Đoạn minh họa có vấn đề:

```java
return Mono.just(syncClient.ping());
```

Java phải tính tham số trước khi gọi `Mono.just`. Vì vậy, `ping()` đã chạy và có thể chặn ngay trong lúc tạo Mono.

Việc nối thêm scheduler phía sau cũng không chuyển một phép gọi đã chạy xong sang luồng khác.

### 3.2. defer trì hoãn tạo nguồn, nhưng không tự đổi scheduler

Đoạn sau trì hoãn lời gọi đến khi có đăng ký:

```java
return Mono.defer(() -> Mono.just(syncClient.ping()));
```

Tuy nhiên, `ping()` vẫn chạy đồng bộ trên luồng đang thực thi supplier. `defer` không biến một API chặn thành API không chặn.

### 3.3. fromCallable phù hợp để bọc thao tác đồng bộ

```java
return Mono.fromCallable(syncClient::ping)
        .subscribeOn(Schedulers.boundedElastic());
```

Ở đây, thao tác được trì hoãn và phần thực thi nguồn được lập lịch trên scheduler phù hợp cho công việc chặn. Tác vụ vẫn có tính chất chặn, nhưng được cách ly khỏi luồng xử lý reactive cần bảo vệ.

Các đoạn trên minh họa vị trí lời gọi và scheduler, không phải một indicator hoàn chỉnh. [Mẫu bọc lời gọi chặn của Reactor](https://projectreactor.io/docs/core/3.6.6/reference/#faq.wrap-blocking).

## 4. Ưu tiên API reactive thực sự khi đã có

Nếu client đã trả `Mono` và thực hiện I/O không chặn, hãy kết hợp publisher đó:

```text
Publisher của client
    → đánh giá kết quả
    → chuyển thành Health
    → áp dụng ngân sách thời gian
    → chuyển lỗi thành kết quả theo chính sách
```

Không cần gọi `block()` để lấy kết quả trung gian rồi bọc lại vào `Mono.just`.

Nếu bước chuyển đổi chỉ trả `Health`, dùng `map` là phù hợp. Nếu bước tiếp theo trả một publisher khác, cần kết hợp bằng toán tử phù hợp như `flatMap`; tránh vô tình tạo cấu trúc `Mono<Mono<Health>>`.

Với nguồn kết thúc không có giá trị, `map` không được gọi. Đây là điểm quan trọng khi nguồn là `Mono<Void>`: muốn tạo Health sau khi thao tác hoàn tất thành công, có thể dùng `thenReturn(health)`. Trước đó phải hiểu “hoàn tất thành công” chứng minh điều gì theo hợp đồng của thao tác.

[Ngữ nghĩa các toán tử Mono trong Reactor 3.6.6](https://projectreactor.io/docs/core/3.6.6/api/reactor/core/publisher/Mono.html).

## 5. Một indicator có xử lý kết quả rỗng, lỗi và timeout

Ví dụ chạy ở phần sau có interface `Probe` trả `Mono<Boolean>` và lớp `DependencyIndicator` thực hiện chuỗi:

```text
Mono.defer(probe::check)
    → map kết quả thành Health
    → switchIfEmpty theo chính sách
    → timeout theo ngân sách
    → xử lý TimeoutException
    → xử lý các lỗi còn lại
```

Ý nghĩa của từng quyết định:

- `defer` gọi lại phép tạo publisher cho từng đăng ký và đưa exception phát sinh trong supplier vào đường lỗi của chuỗi.
- `map` chỉ làm công việc ngắn để tạo kết quả.
- `switchIfEmpty` xử lý trường hợp hoàn tất mà không có boolean.
- `timeout` tránh để nguồn không phát tín hiệu giữ yêu cầu chờ vô hạn.
- Nhánh timeout đứng trước nhánh lỗi chung để giữ được nguyên nhân riêng.
- Mỗi kết quả tạo Builder mới và chỉ đưa dữ liệu chẩn đoán đã chọn.

Dùng `defer` không miễn trừ yêu cầu rằng `probe.check()` phải trả quyền điều khiển nhanh. Nếu supplier tự thực hiện I/O chặn trước khi trả Mono, vẫn cần sửa nguồn hoặc cách ly phần chặn bằng scheduler.

Ví dụ không đưa nguyên văn thông điệp exception ra health vì thông điệp có thể chứa URL hoặc dữ liệu nội bộ. Các mã nguyên nhân là quy ước của bài, không phải các trường bắt buộc của Boot.

## 6. WebClient: kiểm tra HTTP bằng chuỗi không chặn

Lớp dưới dùng `WebClient` để gọi `/internal/ping` của dịch vụ inventory. Chính sách của ví dụ là chấp nhận mã HTTP 2xx; những mã khác tạo DOWN.

Phép kiểm tra này chỉ chứng minh điều kiện HTTP đã chọn. Nếu hợp đồng của dịch vụ yêu cầu kiểm tra thêm nội dung phản hồi, cần đọc và đánh giá nội dung tương ứng.

Tệp `InventoryReactiveHealthIndicator.java`:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.ReactiveHealthIndicator;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component("inventory")
public final class InventoryReactiveHealthIndicator
        implements ReactiveHealthIndicator {

    private static final Duration BUDGET = Duration.ofMillis(500);
    private final WebClient client;

    public InventoryReactiveHealthIndicator(
            WebClient.Builder builder,
            @Value("${app.inventory.base-url}") String baseUrl) {
        this.client = builder.clone().baseUrl(baseUrl).build();
    }

    @Override
    public Mono<Health> health() {
        return Mono.defer(() -> client.get()
                        .uri("/internal/ping")
                        .exchangeToMono(response -> {
                            int code = response.statusCode().value();
                            boolean up = response.statusCode().is2xxSuccessful();
                            Health health = (up ? Health.up() : Health.down())
                                    .withDetail("target", "inventory")
                                    .withDetail("reasonCode", up
                                            ? "HTTP_OK" : "HTTP_STATUS_NOT_2XX")
                                    .withDetail("httpStatus", code)
                                    .build();
                            return response.releaseBody().thenReturn(health);
                        }))
                .switchIfEmpty(Mono.fromSupplier(() -> failure("EMPTY_RESPONSE")))
                .timeout(BUDGET)
                .onErrorResume(TimeoutException.class, error ->
                        Mono.just(failure("PROBE_TIMEOUT")))
                .onErrorResume(error ->
                        Mono.just(failure("REQUEST_FAILED")));
    }

    private static Health failure(String reason) {
        return Health.down()
                .withDetail("target", "inventory")
                .withDetail("reasonCode", reason)
                .withDetail("timeoutMillis", BUDGET.toMillis())
                .build();
    }
}
```

### Vì sao chuỗi này giữ đúng cách xử lý reactive?

**Không gọi block hay subscribe bên trong health.** Phương thức trả lại publisher để hạ tầng Actuator đăng ký.

**Nguồn được tạo khi có đăng ký.** `Mono.defer` bao quá trình tạo yêu cầu cho từng lần đăng ký.

**Có chính sách cho từng mã HTTP.** Phản hồi 503 từ phụ thuộc trở thành DOWN với detail `httpStatus=503`; không nhầm việc “có phản hồi HTTP” với “đạt phép kiểm tra”.

**Không giữ body không sử dụng.** Ví dụ chỉ cần mã trạng thái nên giải phóng body, rồi dùng `thenReturn` sau tín hiệu hoàn tất.

**Có giới hạn thời gian và đường xử lý lỗi.** Chuỗi cố gắng tạo một kết quả có nguyên nhân rõ ràng thay vì để lỗi thông thường đi ra ngoài mà không có chủ đích.

`exchangeToMono` hỗ trợ xử lý theo mã trạng thái. Khi không cần nội dung, cần tiêu thụ hoặc giải phóng nó đúng vòng đời để quản lý tài nguyên của client. [ClientResponse của Spring Framework 6.1.8](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/reactive/function/client/ClientResponse.html).

### Điều kiện khi đưa vào ứng dụng Spring Boot

Lớp trên có annotation `@Component("inventory")`. Trong một ứng dụng reactive, cần đặt nó trong package được quét, có WebClient.Builder do cấu hình ứng dụng cung cấp và khai báo địa chỉ đích, ví dụ:

```yaml
app:
  inventory:
    base-url: http://127.0.0.1:9090
```

Địa chỉ là cấu hình cho phụ thuộc thực tế; nó không tự khởi chạy một dịch vụ inventory. Đường dẫn `/internal/ping` nên có chi phí nhỏ và không tạo thay đổi nghiệp vụ.

Ứng dụng phải thực sự chạy theo mô hình reactive phù hợp. Việc thêm interface hoặc thêm một dependency WebFlux không phải cách tự chứng minh mọi cấu hình hiện có đã chuyển sang reactive.

Các detail tạo trong mã còn chịu chính sách hiển thị và quyền truy cập health. Khả năng thấy detail trên HTTP là vấn đề cấu hình riêng với việc chuỗi có chặn hay không.

## 7. Khi chỉ có client đồng bộ: cách ly đúng nguồn

Một adapter đơn giản, đặt bên trong lớp đã có các import Mono và Schedulers, có thể như sau:

```java
static Mono<Boolean> adaptBlocking(
        java.util.concurrent.Callable<Boolean> operation) {
    return Mono.fromCallable(operation)
            .subscribeOn(Schedulers.boundedElastic());
}
```

Phương thức này trả publisher và không tự đăng ký. Khi sử dụng cho indicator, vẫn cần các bước chọn trạng thái, xử lý nguồn rỗng, timeout và lỗi theo hợp đồng.

### subscribeOn và publishOn giải quyết các vị trí khác nhau

`subscribeOn` thường được đặt ngay sau `fromCallable` để đặt việc thực thi nguồn lên scheduler cần dùng. `publishOn` chuyển ngữ cảnh xử lý cho phần ở phía sau nó; không nên dựa vào việc đặt `publishOn` sau một nguồn chặn để bảo vệ phần nguồn đã thực thi trước đó.

`boundedElastic` phục vụ công việc có thể chặn với giới hạn về tài nguyên. `parallel` hoặc `single` hướng đến công việc ngắn không chặn; đẩy I/O chặn vào đó có thể chiếm tài nguyên cần cho tác vụ khác. [Các loại scheduler của Reactor 3.6.6](https://projectreactor.io/docs/core/3.6.6/api/reactor/core/scheduler/Schedulers.html).

### Giới hạn vẫn phải được thiết kế

Cách ly công việc không làm tài nguyên trở nên vô hạn. Nếu nhiều probe đồng thời cùng chờ một phụ thuộc chậm, hàng đợi và worker vẫn có thể bị bão hòa.

Khi cần scheduler riêng cho các phép kiểm tra:

- Tạo và quản lý scheduler theo vòng đời ứng dụng.
- Chọn giới hạn worker và hàng đợi phù hợp với tải.
- Dọn scheduler riêng khi ứng dụng kết thúc.
- Không tạo một scheduler mới cho từng yêu cầu health.
- Không tự dispose scheduler dùng chung của Reactor chỉ vì một indicator hoàn tất.

Boot có cơ chế thích ứng contributor đồng bộ cho môi trường reactive, và `ReactiveHealthContributor.adapt` là API liên quan khi đăng ký động. Cần hiểu cơ chế đang được hạ tầng sử dụng trước khi tự bọc thêm nhiều tầng scheduler.

## 8. Timeout, lỗi và hủy đăng ký có giới hạn khác nhau

### 8.1. Timeout giới hạn việc chờ tín hiệu của chuỗi

Trong ví dụ WebClient, `timeout` đặt sau quá trình lấy phản hồi và giải phóng body. Nó nằm trên đường tạo kết quả Health, thay vì chỉ áp dụng cho một phần rất nhỏ của phép kiểm tra.

Cần phân biệt:

| Giới hạn | Phần được điều khiển |
| --- | --- |
| Timeout của phép kết nối | Thời gian thiết lập kết nối theo client/connector |
| Timeout đọc/phản hồi của client | Hoạt động I/O tương ứng theo cấu hình client |
| Toán tử timeout của Reactor | Thời gian chờ tín hiệu trên đoạn publisher đặt dưới chính sách đó |
| Timeout của bên gọi health | Thời gian hệ thống bên ngoài sẵn sàng đợi endpoint |

Các mức này cần phù hợp với nhau. Một indicator hoàn tất sát ngưỡng của bên gọi có thể thường xuyên bị hủy trước khi kết quả được nhận.

### 8.2. Timeout không bảo đảm dừng cưỡng bức mọi thao tác

Khi toán tử timeout kích hoạt, nguồn được hủy theo giao thức reactive và chuỗi có thể chuyển sang kết quả dự phòng. Tuy nhiên, việc công việc I/O thực tế dừng đến đâu phụ thuộc client, driver và khả năng xử lý hủy của nguồn.

Một lời gọi đồng bộ không đáp ứng interruption có thể tiếp tục chiếm worker dù bên gọi đã nhận kết quả timeout. Vì vậy, vẫn cần timeout ở chính client, giới hạn đồng thời và lựa chọn nguồn phù hợp.

Tương tự, đặt `timeout` quanh một callback đang chặn không biến callback đó thành không chặn. Luồng đang bị giữ vẫn là vấn đề cần giải quyết.

### 8.3. Hủy đăng ký không phải một lỗi nghiệp vụ mới

Nếu người gọi đóng kết nối hoặc chủ động hủy đăng ký, không cần cố gửi thêm một Health DOWN đến người đã hủy.

Tránh tự gọi `subscribe()` tạo công việc nền không còn gắn với subscription ban đầu. Cách đó làm khó truyền hủy, quản lý lỗi và kiểm soát số lần gọi phụ thuộc.

Nếu thêm `retry`, cần tính lại ngân sách tổng và tải sinh thêm khi phụ thuộc đang lỗi. Một phép kiểm tra sức khỏe không nên tạo làn sóng gọi lại không giới hạn.

## 9. Chương trình kiểm chứng độc lập

Phần này chạy với các publisher được kiểm soát và một HTTP client giả. Nó không cần mở cổng, khởi chạy máy chủ hoặc gọi dịch vụ inventory bên ngoài.

Chương trình kiểm tra:

1. Nguồn bất đồng bộ thành công.
2. Phụ thuộc trả kết quả không đạt.
3. Nguồn hoàn tất rỗng.
4. Lỗi được phát qua publisher.
5. Exception khi tạo publisher.
6. Không gọi probe trước đăng ký và gọi lại cho từng đăng ký.
7. Timeout truyền hủy lên nguồn.
8. Bên gọi hủy thì nguồn nhận hủy.
9. Cách ly lời gọi đồng bộ khỏi worker được đánh dấu không chặn.
10. WebClient chuyển phản hồi HTTP 503 thành Health DOWN.

### 9.1. Tệp dự án

Chuẩn bị JDK 21 và Gradle 8.5:

```text
reactive-health-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/
    ├── ReactiveHealthDemo.java
    └── InventoryReactiveHealthIndicator.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'reactive-health-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.projectreactor:reactor-test'
}

application {
    mainClass = 'ReactiveHealthDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Dự án dùng plugin application để chạy bộ minh họa trong main, nên reactor-test được đặt ở implementation. Trong dự án ứng dụng thông thường, kiểm thử nằm ở source set test và dependency này thường thuộc testImplementation.

Tệp InventoryReactiveHealthIndicator.java dùng nguyên mã ở mục 6. Chương trình console không khởi chạy SpringApplication; annotation component không tự làm nó trở thành một máy chủ đang lắng nghe.

### 9.2. Mã kiểm chứng đầy đủ

Tệp `src/main/java/ReactiveHealthDemo.java`:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.ReactiveHealthIndicator;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

public class ReactiveHealthDemo {
    private static final Duration VERIFY_LIMIT = Duration.ofSeconds(3);

    @FunctionalInterface
    interface Probe {
        Mono<Boolean> check();
    }

    static final class DependencyIndicator implements ReactiveHealthIndicator {
        private final Probe probe;
        private final Duration budget;

        DependencyIndicator(Probe probe, Duration budget) {
            if (probe == null || budget == null
                    || budget.isZero() || budget.isNegative()) {
                throw new IllegalArgumentException("Probe and positive budget required");
            }
            this.probe = probe;
            this.budget = budget;
        }

        @Override
        public Mono<Health> health() {
            return Mono.defer(probe::check)
                    .map(ok -> result(ok, ok ? "PROBE_OK" : "NEGATIVE_REPLY"))
                    .switchIfEmpty(Mono.fromSupplier(() ->
                            Health.unknown()
                                    .withDetail("target", "inventory")
                                    .withDetail("reasonCode", "EMPTY_REPLY")
                                    .build()))
                    .timeout(budget)
                    .onErrorResume(TimeoutException.class, error ->
                            Mono.just(Health.down()
                                    .withDetail("target", "inventory")
                                    .withDetail("reasonCode", "PROBE_TIMEOUT")
                                    .withDetail("timeoutMillis", budget.toMillis())
                                    .build()))
                    .onErrorResume(error ->
                            Mono.just(result(false, "PROBE_FAILED")));
        }
    }

    static Health result(boolean up, String reason) {
        return (up ? Health.up() : Health.down())
                .withDetail("target", "inventory")
                .withDetail("reasonCode", reason)
                .build();
    }

    static DependencyIndicator indicator(Probe probe) {
        return new DependencyIndicator(probe, Duration.ofSeconds(1));
    }

    static boolean matches(Health health, String status, String reason) {
        return health.getStatus().getCode().equals(status)
                && reason.equals(health.getDetails().get("reasonCode"));
    }

    static void verify(
            String name,
            ReactiveHealthIndicator indicator,
            String status,
            String reason) {
        StepVerifier.create(indicator.health())
                .expectNextMatches(health -> matches(health, status, reason))
                .expectComplete()
                .verify(VERIFY_LIMIT);
        System.out.println(name + "=PASS");
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        StepVerifier.withVirtualTime(() ->
                        indicator(() -> Mono.delay(Duration.ofMillis(100))
                                .thenReturn(true)).health())
                .expectSubscription()
                .thenAwait(Duration.ofMillis(100))
                .expectNextMatches(health -> matches(health, "UP", "PROBE_OK"))
                .expectComplete()
                .verify(VERIFY_LIMIT);
        System.out.println("async-up=PASS");

        verify("reported-down", indicator(() -> Mono.just(false)),
                "DOWN", "NEGATIVE_REPLY");
        verify("empty-result", indicator(Mono::empty),
                "UNKNOWN", "EMPTY_REPLY");
        verify("reactive-error", indicator(() ->
                        Mono.error(new IllegalStateException("unavailable"))),
                "DOWN", "PROBE_FAILED");
        verify("synchronous-error", indicator(() -> {
            throw new IllegalStateException("cannot create probe");
        }), "DOWN", "PROBE_FAILED");

        AtomicInteger calls = new AtomicInteger();
        Mono<Health> reusable = indicator(() -> {
            calls.incrementAndGet();
            return Mono.just(true);
        }).health();
        require(calls.get() == 0, "Probe ran before subscription");
        for (int i = 0; i < 2; i++) {
            StepVerifier.create(reusable)
                    .expectNextMatches(health -> matches(health, "UP", "PROBE_OK"))
                    .expectComplete()
                    .verify(VERIFY_LIMIT);
        }
        require(calls.get() == 2, "Each subscription must invoke the probe");
        System.out.println("lazy-per-subscription=PASS");

        AtomicBoolean timeoutCancelled = new AtomicBoolean();
        StepVerifier.withVirtualTime(() ->
                        indicator(() -> Mono.<Boolean>never()
                                .doOnCancel(() -> timeoutCancelled.set(true)))
                                .health())
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(2))
                .expectNextMatches(health -> matches(
                        health, "DOWN", "PROBE_TIMEOUT"))
                .expectComplete()
                .verify(VERIFY_LIMIT);
        require(timeoutCancelled.get(), "Timeout did not cancel the source");
        System.out.println("timeout-cancels-upstream=PASS");

        AtomicBoolean callerCancelled = new AtomicBoolean();
        StepVerifier.create(indicator(() -> Mono.<Boolean>never()
                        .doOnCancel(() -> callerCancelled.set(true))).health())
                .expectSubscription()
                .thenCancel()
                .verify(VERIFY_LIMIT);
        require(callerCancelled.get(), "Caller cancellation was not propagated");
        System.out.println("caller-cancellation=PASS");

        Scheduler eventLoop = Schedulers.newSingle("demo-event-loop");
        Scheduler blockingWorker =
                Schedulers.newBoundedElastic(2, 10, "demo-health-worker");
        try {
            ReactiveHealthIndicator isolated = indicator(() ->
                    Mono.fromCallable(() -> {
                        require(!Schedulers.isInNonBlockingThread(),
                                "Legacy call ran on a non-blocking worker");
                        return true;
                    }).subscribeOn(blockingWorker));

            StepVerifier.create(Mono.defer(() -> {
                        require(Schedulers.isInNonBlockingThread(),
                                "Test did not start on a non-blocking worker");
                        return isolated.health();
                    }).subscribeOn(eventLoop))
                    .expectNextMatches(health -> matches(health, "UP", "PROBE_OK"))
                    .expectComplete()
                    .verify(VERIFY_LIMIT);
            System.out.println("legacy-offloaded=PASS");
        }
        finally {
            eventLoop.dispose();
            blockingWorker.dispose();
        }

        WebClient.Builder fakeClient = WebClient.builder()
                .clientConnector((method, uri, callback) ->
                        Mono.error(new IllegalStateException("Real I/O disabled")))
                .exchangeFunction(request -> Mono.just(
                        ClientResponse.create(HttpStatus.SERVICE_UNAVAILABLE)
                                .body("ignored").build()));
        InventoryReactiveHealthIndicator httpIndicator =
                new InventoryReactiveHealthIndicator(
                        fakeClient, "http://unused.invalid");
        StepVerifier.create(httpIndicator.health())
                .expectNextMatches(health ->
                        matches(health, "DOWN", "HTTP_STATUS_NOT_2XX")
                        && Integer.valueOf(503).equals(
                                health.getDetails().get("httpStatus")))
                .expectComplete()
                .verify(VERIFY_LIMIT);
        System.out.println("webclient-status=PASS");
    }
}
```

### 9.3. Chạy và đọc kết quả

Tại thư mục dự án:

```shell
gradle -q run --console=plain
```

Nếu đã có wrapper, trong PowerShell:

```powershell
.\gradlew.bat -q run --console=plain
```

Hoặc trên Linux/macOS:

```shell
./gradlew -q run --console=plain
```

Gradle cung cấp classpath của các thư viện Spring và Reactor. Nếu gọi trực tiếp javac/java, cần cung cấp đủ dependency tương ứng.

Stdout của chương trình, không tính thông báo từ Gradle hoặc quá trình tải dependency:

```text
async-up=PASS
reported-down=PASS
empty-result=PASS
reactive-error=PASS
synchronous-error=PASS
lazy-per-subscription=PASS
timeout-cancels-upstream=PASS
caller-cancellation=PASS
legacy-offloaded=PASS
webclient-status=PASS
```

Mỗi dòng PASS chỉ được in sau khi các kỳ vọng tương ứng đạt. Nếu không đạt, chương trình phát AssertionError hoặc lỗi kiểm chứng và không nên được xem là thành công.

### 9.4. Các bằng chứng quan trọng trong chương trình

**Đồng hồ ảo:** `StepVerifier.withVirtualTime` kiểm tra toán tử thời gian bằng scheduler được điều khiển. Publisher có toán tử thời gian được tạo trong supplier để dùng đồng hồ phù hợp. Điều này kiểm tra hành vi timeout mà không cần ngủ thật để đợi.

**Nguồn lười:** bộ đếm còn bằng 0 sau khi gọi health, rồi tăng theo từng đăng ký. Đây là bằng chứng về thời điểm gọi probe trong ví dụ, không phải bằng chứng mọi client bên ngoài đều có cùng hành vi.

**Hủy:** các nguồn never trong bài có callback doOnCancel để kiểm tra tín hiệu hủy từ timeout hoặc người gọi. Nó chứng minh tín hiệu giao thức được truyền cho nguồn giả; không chứng minh một driver bất kỳ luôn dừng tài nguyên thực tế ngay lập tức.

**Cách ly scheduler:** phép kiểm tra bắt đầu trên worker được Reactor đánh dấu không chặn, còn callable chạy trên scheduler dành cho công việc chặn. Callable mẫu trả nhanh; phép kiểm chứng xác nhận vị trí thực thi của phần việc sẽ được thay bằng lời gọi đồng bộ thật.

**HTTP giả:** exchangeFunction tạo một phản hồi 503 trong bộ nhớ. Client connector giả từ chối I/O thật để bài kiểm chứng không khởi tạo kết nối phụ thuộc. Phần này kiểm tra chính sách chuyển mã HTTP sang Health; nó chưa kiểm tra mạng, TLS, DNS hay pool kết nối.

**Giới hạn chờ kiểm thử:** verify có giới hạn thời gian trên luồng chạy chương trình kiểm chứng. Việc chờ của bộ kiểm thử không phải mẫu để đặt vào health trên luồng phục vụ.

StepVerifier cho phép diễn đạt các tín hiệu mong đợi và kích hoạt kiểm chứng ở bước cuối. [Tài liệu kiểm thử Reactor](https://projectreactor.io/docs/core/3.6.6/reference/#testing).

## 10. Những gì các kiểm chứng này chưa thay thế

Bộ minh họa chứng minh các hành vi cụ thể trong chuỗi và scheduler. Trước khi đưa vào ứng dụng thực tế, cần kiểm chứng thêm những điều phụ thuộc môi trường:

- Client/driver thật có I/O không chặn hay đã được cách ly đúng phần việc chặn.
- Timeout và hủy có giải phóng tài nguyên như kỳ vọng.
- Có đọc/giải phóng body trong mọi nhánh HTTP liên quan.
- Nhiều lời gọi health đồng thời không làm cạn worker, hàng đợi hoặc pool kết nối.
- Endpoint hoàn tất trong ngân sách của hệ thống gọi probe.
- Quyền hiển thị details phù hợp và dữ liệu chẩn đoán không chứa bí mật.
- Quy tắc đưa phụ thuộc vào health group phù hợp mục đích vận hành.

Có thể bổ sung công cụ phát hiện thao tác chặn như [BlockHound](https://github.com/reactor/BlockHound) trong kiểm thử phù hợp với phiên bản và môi trường chạy. Nó là bằng chứng bổ sung; vẫn cần đánh giá đường gọi thực tế và khả năng quản lý tài nguyên của client.

Một health check không cần đọc nhiều dữ liệu hay gọi cả chuỗi nghiệp vụ đắt đỏ để có vẻ đầy đủ. Hãy chọn phép quan sát đủ ý nghĩa cho quyết định vận hành mà nó phục vụ.

## 11. Lỗi phổ biến và cách sửa

| Lỗi | Vì sao có vấn đề? | Hướng sửa |
| --- | --- | --- |
| Trả Mono.just(syncCall()) | Lời gọi đã chạy trước khi tạo Mono | Dùng nguồn reactive hoặc fromCallable với scheduler phù hợp |
| Dùng defer quanh một lời gọi chặn rồi cho rằng đã không chặn | Chỉ thay thời điểm, chưa thay nơi thực thi | Cách ly chính phần việc chặn |
| Gọi block trong health | Giữ luồng chờ kết quả và phá cách kết hợp publisher | Trả chuỗi được kết hợp |
| Tự gọi subscribe trong health | Tạo công việc tách rời khỏi hạ tầng gọi | Để hạ tầng sở hữu subscription |
| Đặt publishOn sau nguồn chặn | Không bảo vệ phần nguồn phía trước | Đặt subscribeOn phù hợp gần nguồn |
| Thực hiện JDBC trong map của WebClient | Callback vẫn có thể chặn worker reactive | Dùng driver reactive hoặc adapter cách ly riêng |
| Bỏ qua Mono.empty | Có thể không phát Health nào | Đặt chính sách switchIfEmpty rõ ràng |
| Chỉ map trên Mono<Void> | Không có giá trị để chạy map | Dùng tín hiệu hoàn tất như thenReturn khi đúng hợp đồng |
| Timeout có nhưng không giới hạn client đồng bộ | Công việc có thể tiếp tục chiếm worker | Cấu hình timeout ở client và kiểm soát tài nguyên |
| Không xử lý body HTTP không dùng | Có thể quản lý tài nguyên không đúng | Tiêu thụ hoặc giải phóng theo API client |
| Tạo scheduler mới cho mỗi lần health | Tăng tài nguyên và khó dọn | Quản lý scheduler theo vòng đời ứng dụng |
| Gọi cache mà không định nghĩa độ mới | Kết quả cũ có thể che lỗi mới | Chọn TTL và nơi chia sẻ publisher có chủ đích |

Nếu dùng cache, cần biết cache thuộc một publisher hay được chia sẻ giữa nhiều lần gọi phương thức. Tạo một publisher có cache mới trong mỗi lần health khác với chia sẻ một kết quả có TTL cho nhiều yêu cầu. Đồng thời phải công bố hoặc hiểu độ cũ chấp nhận được của quan sát.

## 12. Thực hành

1. Đổi nguồn thành `Mono.just(false)` và giải thích vì sao đó là một kết quả quan sát, không phải tín hiệu onError.
2. Đổi nguồn thành `Mono.empty()`. So sánh chính sách UNKNOWN của bài với chính sách DOWN nếu hệ thống yêu cầu phải nhận được câu trả lời.
3. Bỏ switchIfEmpty trong bản thử và dùng StepVerifier để quan sát chuỗi không phát Health.
4. Giữ nguồn never và thay ngân sách thời gian. Kiểm tra mã nguyên nhân cùng tín hiệu hủy.
5. Thay callable trả nhanh bằng client đồng bộ thật trong môi trường kiểm thử. Kiểm chứng worker thực thi và timeout của chính client.
6. Đổi phản hồi HTTP giả từ 503 sang 204. Dự đoán trạng thái và mã nguyên nhân của InventoryReactiveHealthIndicator.
7. Cho exchangeFunction giả phát lỗi, rồi xác nhận nhánh REQUEST_FAILED.
8. Đánh giá việc thêm một retry: tổng thời gian có còn nằm trong ngân sách của bên gọi và số lần gọi phụ thuộc có được giới hạn không?

Đối chiếu:

- Nguồn false tạo DOWN với NEGATIVE_REPLY theo chính sách ví dụ.
- Nguồn empty tạo UNKNOWN với EMPTY_REPLY nếu giữ switchIfEmpty.
- Nguồn never bị giới hạn bằng timeout và tạo DOWN với PROBE_TIMEOUT.
- HTTP 204 thuộc 2xx nên tạo UP với HTTP_OK, dù không có body dữ liệu.
- Lỗi thông thường từ nguồn HTTP được chọn lọc thành REQUEST_FAILED; loại timeout riêng trong ví dụ là TimeoutException của đường xử lý tương ứng.

Khi đánh giá một ReactiveHealthIndicator, hãy đọc từ nguồn I/O đến Health cuối cùng: phần nào có thể chờ, phần đó chạy ở đâu, mỗi kết thúc có ý nghĩa gì và tài nguyên được xử lý thế nào khi người gọi không còn chờ nữa. Cách đọc đó giúp bảo vệ luồng reactive và giữ tín hiệu health đáng tin trong cả lúc phụ thuộc hoạt động bình thường lẫn lúc gặp sự cố.

# Spring Framework Retry: điều kiện Spring Framework 7 và phiên bản tương thích

## Mục tiêu

Spring Framework 7 bổ sung cơ chế retry ngay trong nền tảng Spring: annotation `@Retryable`, API lập trình `RetryTemplate` và chính sách `RetryPolicy`. Các API này nằm trong những module cốt lõi của Framework, có cách dùng và package khác với thư viện Spring Retry trước đây. Khi triển khai Circuit Breaker trong Spring Cloud, cần xác định đúng phiên bản Framework, chọn đúng bộ API retry và hiểu retry phối hợp với Circuit Breaker như thế nào.

Sau bài học, bạn có thể:

- Xác định phiên bản Spring Framework tối thiểu để dùng retry tích hợp trong Framework.
- Phân biệt Spring Framework Retry với artifact `org.springframework.retry:spring-retry`.
- Bật và sử dụng `@Retryable` qua `@EnableResilientMethods`.
- Dùng `RetryTemplate` và `RetryPolicy` cho các khối lệnh cần retry theo chương trình.
- Đọc đúng ý nghĩa `maxRetries`, backoff, jitter và điều kiện exception.
- Chọn phương án phù hợp cho Spring Boot 3.x, Spring Boot 4.x và các ứng dụng Spring Framework độc lập.

## Spring Framework Retry xuất hiện từ phiên bản nào?

Từ **Spring Framework 7.0**, Spring đưa các tính năng resilience cơ bản vào nền tảng. Phần retry mới nằm ở hai module:

| Thành phần | Package | Vai trò |
|---|---|---|
| `@Retryable`, `@EnableResilientMethods` | `org.springframework.resilience.annotation` | Khai báo retry cho phương thức Spring bean và bật xử lý annotation. |
| `RetryTemplate`, `RetryPolicy`, `RetryListener` | `org.springframework.core.retry` | Retry các khối lệnh theo chương trình và tùy chỉnh chính sách. |

Đây là tính năng của Spring Framework, không phải một phiên bản mới của artifact `spring-retry`. Không cần thêm dependency `org.springframework.retry:spring-retry` để dùng API retry tích hợp trong Framework 7; ứng dụng cần các module Spring tương ứng, thường đã có thông qua dependency management của Spring Boot.

`@Retryable` là metadata cho Spring xử lý qua proxy. Chỉ đặt annotation trong mã chưa đủ để kích hoạt retry; ứng dụng phải bật bộ xử lý annotation bằng `@EnableResilientMethods` hoặc đăng ký `RetryAnnotationBeanPostProcessor` tương ứng. `RetryTemplate` là API lập trình nên không cần bật AOP annotation để gọi trực tiếp.

## Ma trận phiên bản tương thích

Điều kiện quan trọng là phiên bản **Spring Framework**, không chỉ tên phiên bản Spring Boot:

| Nền tảng | Phiên bản Framework nền tảng | Có Spring Framework Retry tích hợp? |
|---|---|---|
| Spring Framework 7.0.x | 7.0.x | Có, từ 7.0. |
| Spring Framework 7.1.x | 7.1.x | Có; tính năng được giới thiệu từ 7.0. |
| Spring Boot 4.0.x | Spring Framework 7.0.x | Có. |
| Spring Boot 4.2.x | Spring Framework 7.1.0 trở lên | Có. |
| Spring Boot 3.5.x | Spring Framework 6.2.x | Không có API retry tích hợp mới. |
| Spring Framework 6.x | 6.x | Không có `org.springframework.core.retry` và `org.springframework.resilience.annotation` của Framework 7. |

Theo tài liệu hệ thống hiện hành tại thời điểm biên soạn, Spring Boot 4.0.10 yêu cầu Spring Framework 7.0.11 trở lên; Spring Boot 4.2.0 yêu cầu Spring Framework 7.1.0 trở lên. Spring Boot 3.5.16 yêu cầu Spring Framework 6.2.19 trở lên. Các số phiên bản vá sẽ thay đổi theo bản phát hành; hãy xem system requirements và BOM của đúng dòng Spring Boot trước khi nâng cấp.

Spring Boot 4.x yêu cầu Java 17 trở lên. Khi dùng Spring Boot, nên để BOM quản lý các module Spring Framework đồng bộ. Tránh tự nâng riêng `spring-core` hoặc `spring-context` lên 7.x trong ứng dụng Boot 3.x đang được quản lý trên Framework 6.x; trộn các module khác major version có thể gây lỗi binary compatibility và auto-configuration.

Nếu ứng dụng dùng Spring Framework 6.x hoặc Spring Boot 3.x, có thể tiếp tục dùng Resilience4j hoặc một thư viện retry tương thích với dòng Framework hiện tại. Không thể chỉ đổi import sang `org.springframework.core.retry` khi class đó chưa tồn tại trong Framework 6.x.

## Phân biệt Spring Framework Retry và Spring Retry cũ

Trong nhiều năm, Spring Retry là thư viện độc lập với artifact `org.springframework.retry:spring-retry`. Spring Framework 7 đưa một bộ retry tối giản vào core và context. Hai bộ API có tên lớp gần giống nhau nhưng package, cấu hình và một số ngữ nghĩa khác nhau.

| Nội dung | Spring Retry cũ | Spring Framework Retry từ 7.0 |
|---|---|---|
| Dependency | `org.springframework.retry:spring-retry` | Các module `spring-core` và `spring-context` của Framework 7. |
| Annotation | `org.springframework.retry.annotation.Retryable` | `org.springframework.resilience.annotation.Retryable` |
| Bật annotation | `@EnableRetry` | `@EnableResilientMethods` |
| Template | `org.springframework.retry.support.RetryTemplate` | `org.springframework.core.retry.RetryTemplate` |
| Giới hạn số lần | `maxAttempts` thường tính cả lần gọi đầu tiên. | `maxRetries` là số lần thử lại sau lần gọi đầu tiên. |
| Phục hồi sau khi hết retry | Có cơ chế `@Recover`. | Exception gốc cuối cùng được truyền về caller; không có ánh xạ `@Recover` một-một. |

Tên import rất quan trọng. Nếu cả hai thư viện xuất hiện trên classpath, IDE có thể gợi ý hai annotation `Retryable` hoặc hai lớp `RetryTemplate`. Hãy kiểm tra package đầy đủ trong import và quyết định rõ bộ API mà module đang sử dụng.

Spring Retry cũ đã được chuyển sang tổ chức `spring-attic` và repository được archive vào tháng 7 năm 2026. Bản phát hành cuối cùng là 2.0.13 vào ngày 8 tháng 6 năm 2026. Dự án cũ không còn được duy trì như một dự án mã nguồn mở đang phát triển và README hướng người dùng sang resilience features của Spring Framework 7. Spring Boot 4 cũng đã bỏ dependency management cho Spring Retry cũ; nếu ứng dụng còn giữ artifact đó, phải tự quản lý version rõ ràng. Với phát triển mới trên Framework 7, ưu tiên API retry tích hợp.

## Bật `@Retryable` trong Spring Framework 7

Khai báo `@EnableResilientMethods` trên một lớp cấu hình để Spring đăng ký bộ xử lý annotation:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.resilience.annotation.EnableResilientMethods;

@Configuration
@EnableResilientMethods
public class ResilienceConfiguration {
}
```

Sau đó đặt `@Retryable` trên phương thức cần thử lại:

```java
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.resilience.annotation.Retryable;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    private final NotificationClient notificationClient;

    public NotificationService(NotificationClient notificationClient) {
        this.notificationClient = notificationClient;
    }

    @Retryable(
            includes = MessageDeliveryException.class,
            maxRetries = 4,
            delay = 100,
            jitter = 10,
            multiplier = 2,
            maxDelay = 1_000)
    public void sendNotification(Notification notification) {
        notificationClient.send(notification);
    }
}
```

Các kiểu `Notification`, `NotificationClient` là thành phần của ứng dụng. Ví dụ chỉ retry lỗi giao nhận thông điệp được phân loại là tạm thời. `maxRetries = 4` có nghĩa là một lần gọi đầu tiên và tối đa bốn lần thử lại, tổng cộng tối đa năm lần thực thi. `delay` là khoảng chờ cơ sở tính bằng mili giây theo mặc định; `multiplier` tăng khoảng chờ giữa các lần retry, `jitter` thêm độ ngẫu nhiên và `maxDelay` giới hạn khoảng chờ.

`@Retryable` có thể đặt ở cấp phương thức hoặc cấp lớp. Khi đặt ở cấp lớp, annotation áp dụng cho các phương thức được gọi qua proxy trong class hierarchy. Nên ưu tiên đặt ở phương thức cụ thể để người đọc thấy rõ thao tác nào được retry và tránh retry ngoài ý muốn các thao tác không liên quan.

## Điều kiện retry và hành vi mặc định

Nếu không cấu hình điều kiện, `@Retryable` mặc định có thể retry mọi exception được ném ra từ phương thức. Mặc định là tối đa ba lần retry sau lần gọi đầu tiên, với khoảng chờ một giây giữa các lần thử. Khi chính sách hết retry, exception gốc cuối cùng được truyền về caller.

Trong ứng dụng thực tế, nên giới hạn các exception có thể phục hồi:

```java
@Retryable(
        includes = {
                java.net.ConnectException.class,
                java.net.SocketTimeoutException.class
        },
        excludes = {
                IllegalArgumentException.class,
                SecurityException.class
        },
        maxRetries = 2,
        delay = 150,
        multiplier = 2,
        maxDelay = 600)
public Product loadProduct(String id) {
    return catalogClient.load(id);
}
```

`includes` chọn loại exception cần retry; `excludes` loại những exception không được retry. Việc so khớp được thực hiện với exception từ lần gọi và các cause lồng bên trong. Nếu cần logic phân loại phức tạp hơn, có thể cung cấp `MethodRetryPredicate` qua thuộc tính `predicate`; predicate nhận thông tin phương thức và exception để quyết định có retry hay không.

Không nên retry lỗi validation, lỗi quyền truy cập hoặc dữ liệu đầu vào sai vì thử lại không làm nguyên nhân biến mất. Với HTTP client, chỉ retry các lỗi kết nối, timeout hoặc status được xác định là tạm thời theo hợp đồng API. Với thao tác có side effect như tạo đơn hay thanh toán, cần idempotency key hoặc cơ chế tra cứu kết quả để tránh thực hiện trùng khi server đã xử lý nhưng response bị mất.

## Phân biệt maxRetries và maxAttempts

Đây là khác biệt dễ gây lỗi khi chuyển từ Spring Retry cũ:

| Cấu hình | Ý nghĩa | Tổng số lần thực thi tối đa |
|---|---|---:|
| Spring Framework `maxRetries = 2` | Hai lần gọi lại sau lần đầu. | 3 |
| Spring Framework `maxRetries = 4` | Bốn lần gọi lại sau lần đầu. | 5 |
| Spring Retry cũ `maxAttempts = 3` | Ba lần thực thi tính cả lần đầu. | 3 |

Ví dụ, khi chuyển một phương thức từ Spring Retry cũ có `maxAttempts = 3`, giá trị tương đương trong Spring Framework 7 thường là `maxRetries = 2`, nếu muốn giữ nguyên tổng số lần gọi. Không sao chép nguyên con số giữa hai API mà không kiểm tra ý nghĩa.

## Retry theo chương trình bằng RetryTemplate

`RetryTemplate` phù hợp khi cần retry một khối lệnh tùy ý, không nhất thiết là phương thức Spring bean. Chính sách được tách riêng trong `RetryPolicy`:

```java
import java.time.Duration;

import org.springframework.core.retry.RetryPolicy;
import org.springframework.core.retry.RetryTemplate;
import org.springframework.messaging.MessageDeliveryException;

RetryPolicy policy = RetryPolicy.builder()
        .includes(MessageDeliveryException.class)
        .maxRetries(4)
        .delay(Duration.ofMillis(100))
        .jitter(Duration.ofMillis(10))
        .multiplier(2)
        .maxDelay(Duration.ofSeconds(1))
        .build();

RetryTemplate retryTemplate = new RetryTemplate(policy);

retryTemplate.invoke(() -> notificationClient.send(notification));
```

Builder hỗ trợ `includes`, `excludes`, `maxRetries`, `delay`, `jitter`, `multiplier`, `maxDelay` và predicate tùy chỉnh. Có thể cung cấp `BackOff` riêng qua cấu hình `backOff()` khi lịch chờ cần logic đặc biệt. `RetryTemplate` nhẹ và có thể tạo theo từng chính sách cụ thể; nếu dùng lặp lại, có thể tạo bean dùng chung với policy bất biến.

`invoke` cho phép xử lý callback có hoặc không có giá trị trả về. Khi retry cạn, exception unchecked cuối cùng từ callback được truyền ra caller. Nếu cần xem trạng thái chi tiết của toàn bộ lần thử, có thể dùng `execute`; phương thức này ném `RetryException` có thông tin về các exception đã xảy ra, bao gồm exception cuối cùng.

## Reactive method và Reactor

Spring Framework 7 tự điều chỉnh `@Retryable` khi phương thức trả về kiểu reactive như `Mono` hoặc `Flux`. Spring trang trí pipeline bằng retry support của Reactor:

```java
import org.springframework.resilience.annotation.Retryable;
import reactor.core.publisher.Mono;

@Retryable(maxRetries = 4, delay = 100)
public Mono<Void> sendNotification(Notification notification) {
    return notificationClient.sendReactive(notification);
}
```

Publisher được trả về sẽ nhận retry behavior. Không cần tự gọi `subscribe()` trong phương thức chỉ để kích hoạt retry; hãy trả publisher cho tầng WebFlux hoặc subscriber quản lý lifecycle. Cần kiểm tra dependency Reactor có mặt khi dùng reactive return type.

Retry reactive vẫn phải tuân theo giới hạn deadline và tính idempotent. Mỗi lần retry có thể tạo một subscription hoặc request mới tới dependency. Nếu request trước có thể đã được server xử lý, việc gửi lại phải an toàn theo hợp đồng API.

## Kết hợp với Transaction, Cache và Async

Retry là một advice dựa trên proxy, vì vậy thứ tự interceptor ảnh hưởng tới hành vi:

- **Với `@Transactional`:** retry advice nằm bên ngoài transaction advice. Mỗi attempt bắt đầu một transaction mới; khi phương thức ném lỗi, transaction của attempt đó rollback trước khi retry quyết định thử lại. Đây thường là hành vi mong muốn với lỗi tạm thời như deadlock.
- **Với `@Cacheable`:** retry nằm bên ngoài cache advice. Mỗi attempt đi qua cache interceptor; một giá trị cache được tạo bởi request khác giữa các lần thử có thể được trả về ở attempt sau.
- **Với `@Async`:** mặc định async advice nằm ngoài retry advice. Công việc được gửi vào executor một lần; các lần retry chạy trên async thread và caller nhận `Future`/`CompletableFuture` khi chuỗi kết thúc.

Không thay đổi advice order một cách tùy tiện. Đặc biệt, nếu đảo thứ tự `@Async` và `@Retryable`, retry có thể chỉ nhìn thấy đối tượng `Future` được trả về ngay mà không nhìn thấy exception phát sinh trong quá trình thực thi bất đồng bộ. Khi thay đổi order, cần kiểm thử cả thread thực thi, transaction và số attempt thực tế.

## Phối hợp Spring Framework Retry với Circuit Breaker

Spring Framework Retry chỉ thực hiện thử lại. Nó không cung cấp máy trạng thái `CLOSED`, `OPEN`, `HALF_OPEN`, sliding window, ngưỡng failure rate hoặc cơ chế từ chối request khi dependency không khỏe. Trong module Spring Cloud Circuit Breaker, có thể dùng Spring Framework Retry cho lỗi tạm thời và dùng Spring Cloud CircuitBreaker với Resilience4j để theo dõi sức khỏe dependency.

Hai cơ chế cần có trách nhiệm rõ ràng:

| Cơ chế | Vai trò |
|---|---|
| Spring Framework `@Retryable` hoặc `RetryTemplate` | Thử lại một thao tác khi exception thuộc nhóm được phép retry. |
| Resilience4j Circuit Breaker | Theo dõi kết quả, chuyển trạng thái và chặn lời gọi khi dependency đang lỗi. |
| TimeLimiter/HTTP timeout | Giới hạn thời gian chờ của từng attempt hoặc request. |
| Bulkhead | Giới hạn số thao tác đồng thời để cô lập tài nguyên. |

Nếu Circuit Breaker đang `OPEN`, lời gọi có thể bị từ chối bằng `CallNotPermittedException`. Không nên retry exception từ chối này: mạch đã quyết định tạm thời không cho phép gọi dependency. Hãy cấu hình `excludes` cho loại exception tương ứng hoặc viết predicate chỉ retry lỗi mạng/timeout được xác định là tạm thời. Khi kết hợp annotation của nhiều thư viện trên cùng phương thức, hãy kiểm tra thứ tự advice thực tế; nếu cần thứ tự chính xác, dùng composition lập trình tường minh và kiểm thử số request được gửi xuống upstream.

Fallback không phải là mặc định của Spring Framework `@Retryable`. Khi retry cạn, exception cuối cùng được truyền về caller. Nếu cần trả cache hoặc response suy giảm, hãy xử lý ở tầng ứng dụng hoặc dùng fallback của Circuit Breaker theo đúng hợp đồng API.

## Chọn cách dùng theo phiên bản ứng dụng

| Bối cảnh | Hướng triển khai |
|---|---|
| Ứng dụng mới trên Spring Boot 4.x / Framework 7.x | Ưu tiên `@Retryable` hoặc `RetryTemplate` trong Spring Framework. |
| Ứng dụng Spring Framework độc lập 7.x | Dùng `spring-context` và `spring-core` cùng dòng 7.x; bật `@EnableResilientMethods` nếu dùng annotation. |
| Ứng dụng Spring Boot 3.x / Framework 6.x | Dùng Resilience4j hoặc thư viện retry tương thích với Framework 6; không import API core retry của Framework 7. |
| Ứng dụng đang dùng Spring Retry cũ | Có thể cần giữ API cũ trong giai đoạn chuyển đổi; kiểm tra version tương thích, pin dependency nếu BOM không quản lý và lập kế hoạch chuyển sang API được duy trì. |

Khi nâng từ Boot 3.x lên Boot 4.x, không chỉ đổi phiên bản dependency. Hãy kiểm tra package import, annotation enablement, số lần thử, fallback, listener, cách xử lý exhaustion và thứ tự AOP. Spring Framework Retry được thiết kế gọn hơn Spring Retry cũ, nên không phải mọi tính năng cũ đều có bản thay thế trực tiếp.

## Thực hành kiểm chứng phiên bản và hành vi

Thực hiện trong một ứng dụng thử nghiệm có dependency giả lập lỗi tạm thời:

1. Kiểm tra dependency tree để xác định `spring-core` và `spring-context` đang ở cùng dòng 7.x nếu muốn dùng retry tích hợp.
2. Xác nhận ứng dụng có `@EnableResilientMethods`; gọi một bean khác qua Spring proxy để tránh self-invocation bỏ qua advice.
3. Cấu hình `@Retryable` chỉ nhận exception tạm thời, đặt `maxRetries = 2` và quan sát tổng số lần gọi tối đa là ba.
4. Cho dependency thành công ở lần thử thứ hai; xác nhận caller nhận kết quả và log/`MethodRetryEvent` ghi nhận lỗi ban đầu.
5. Cho mọi attempt thất bại; xác nhận exception cuối cùng được truyền về caller và không có `@Recover` tự động như Spring Retry cũ.
6. Thử một phương thức trả `Mono` hoặc `Flux`; xác nhận pipeline được retry mà service không tự subscribe ngoài lifecycle của caller.
7. Tắt `@EnableResilientMethods` trong profile thử nghiệm; xác nhận annotation không được xử lý, qua đó kiểm tra điều kiện enablement.
8. Nếu kết hợp Resilience4j Circuit Breaker, làm mạch chuyển `OPEN`; xác nhận `CallNotPermittedException` không tạo thêm retry tới dependency.

Trong quá trình kiểm tra, ghi lại phiên bản Framework, Boot, số attempt, loại exception, thời gian backoff và số request thực tế tới dependency. Đừng chỉ dựa vào số lần phương thức được gọi ở tầng controller; interceptor có thể tạo nhiều attempt bên trong một lần gọi logic.

## Lỗi thường gặp

- **Dùng Spring Framework Retry trên Framework 6.x:** package `org.springframework.core.retry` và `org.springframework.resilience.annotation` chưa có trong dòng 6.x.
- **Quên `@EnableResilientMethods`:** annotation `@Retryable` chỉ là metadata nếu không có bộ xử lý.
- **Import nhầm `@Retryable`:** Spring Retry cũ và Spring Framework 7 có cùng tên đơn giản nhưng khác package.
- **Nhầm `maxRetries` với `maxAttempts`:** Framework 7 đếm số lần retry bổ sung sau lần gọi đầu tiên.
- **Giữ nguyên `@Recover` khi chuyển đổi:** Framework Retry không cung cấp cơ chế `@Recover` tương đương một-một.
- **Retry mọi exception:** lỗi nghiệp vụ, quyền truy cập và validation không tự hết khi thử lại.
- **Retry `CallNotPermittedException`:** Circuit Breaker đã từ chối lời gọi; thử lại ngay không giúp dependency phục hồi.
- **Cho rằng Retry là Circuit Breaker:** Retry không có trạng thái `OPEN`, sliding window hay failure threshold.
- **Bỏ qua proxy và self-invocation:** lời gọi nội bộ trong cùng bean có thể không đi qua retry advice.
- **Không kiểm tra thứ tự AOP:** Retry, Transaction, Cache và Async có thể thay đổi transaction hoặc thread của từng attempt.
- **Không kiểm tra BOM:** tự trộn module Framework 6.x và 7.x có thể gây lỗi tương thích.

## Tài liệu tham khảo

- [Spring Framework 7.0 – Resilience Features](https://docs.spring.io/spring-framework/reference/7.0/core/resilience.html)
- [Spring Framework 7.1 – Resilience Features](https://docs.spring.io/spring-framework/reference/7.1/core/resilience.html)
- [Spring Framework `@Retryable` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/resilience/annotation/Retryable.html)
- [Spring Boot 4.0 – System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html)
- [Spring Boot 4.2 – System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot 3.5 – System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 4.0 Migration Guide – Dependency Management for Spring Retry](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Retry archived repository](https://github.com/spring-attic/spring-retry)

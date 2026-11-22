# Context khởi động xong không đồng nghĩa tác vụ chuẩn bị đã hoàn tất

Trong Spring Boot, việc **ApplicationContext được khởi tạo và refresh thành công** không có nghĩa mọi tác vụ chuẩn bị của ứng dụng đã hoàn tất. Spring đã có thể tạo các bean cần thiết, khởi động web server và phát sự kiện liên quan đến context, trong khi ứng dụng vẫn đang chạy `ApplicationRunner`, `CommandLineRunner` hoặc một tác vụ bất đồng bộ như nạp cache, tải dữ liệu tham chiếu, kết nối đến hệ thống ngoài hay làm nóng tài nguyên.

Sự phân biệt này rất quan trọng khi triển khai ứng dụng web, worker hoặc hệ thống có health check. Nếu coi “context đã khởi động” là “đã sẵn sàng phục vụ”, ứng dụng có thể nhận yêu cầu trước khi dữ liệu thiết yếu được nạp, trả lỗi tạm thời hoặc tạo ra trạng thái không nhất quán.

Bài học thuộc chủ đề **Trạng thái và dừng** trong **Spring Boot Fundamentals**. Trọng tâm là tách ba câu hỏi khác nhau:

1. **Container đã được dựng chưa?** — các bean và infrastructure chính đã được chuẩn bị đến đâu?
2. **Quá trình startup của Spring Boot đã hoàn thành chưa?** — các runner và callback liên quan đã chạy xong chưa?
3. **Ứng dụng đã thực sự đáp ứng điều kiện nghiệp vụ để phục vụ traffic chưa?** — dữ liệu, tài nguyên và tác vụ chuẩn bị thiết yếu đã sẵn sàng chưa?

Ba câu hỏi có thể có ba câu trả lời khác nhau ở cùng một thời điểm.

## 1. Context khởi động xong nghĩa là gì?

`ApplicationContext` là vùng quản lý các bean, cấu hình và nhiều dịch vụ nền của Spring. Trong quá trình `refresh()`, Spring thực hiện những bước như xử lý định nghĩa bean, tạo các singleton không lazy, thiết lập các thành phần lifecycle và hoàn thành việc khởi tạo context.

Trong trường hợp ứng dụng Spring Boot điển hình, trình tự có thể hình dung như sau:

~~~text
main()
  |
  v
SpringApplication.run(args)
  |
  +-- Chuẩn bị Environment và cấu hình
  |
  +-- Tạo ApplicationContext
  |
  +-- Refresh ApplicationContext
  |     +-- Tạo các bean eager
  |     +-- Chạy init callbacks / @PostConstruct của các bean đó
  |     +-- Khởi động một số thành phần SmartLifecycle
  |     +-- ContextRefreshedEvent
  |
  +-- ApplicationStartedEvent
  |
  +-- Gọi ApplicationRunner và CommandLineRunner
  |
  +-- ApplicationReadyEvent
  |
  +-- ReadinessState.ACCEPTING_TRAFFIC
  |
  +-- SpringApplication.run(...) hoàn tất
~~~

Sơ đồ mô tả luồng startup thông thường; Spring Boot còn có các callback, sự kiện và cơ chế phụ tùy loại ứng dụng, cấu hình và phiên bản.

**Context refresh thành công** thường là điều kiện cần để ứng dụng hoạt động, nhưng không phải điều kiện đủ để công bố rằng mọi công việc chuẩn bị đã hoàn thành.

Ví dụ: bean dịch vụ đã được tạo, nhưng một runner vẫn đang đồng bộ danh mục sản phẩm từ kho dữ liệu. Hoặc bean đã nộp một tác vụ nạp dữ liệu vào executor rồi trả về ngay, để luồng nền tiếp tục chạy sau đó.

### Context tồn tại cũng chưa chắc đã refresh xong

Ngay từ đầu quá trình startup, `SpringApplication` có thể đã tạo đối tượng context nhưng chưa refresh thành công. Vì vậy:

- **Context được tạo** không đồng nghĩa context đã refresh.
- **Context được refresh** không đồng nghĩa mọi runner đã xong.
- **Runner đã xong** không đồng nghĩa mọi tác vụ nền được runner khởi chạy đã xong.
- **Ứng dụng báo ready** theo vòng đời Spring Boot không tự chứng minh rằng tất cả điều kiện nghiệp vụ bên ngoài Spring đã được thỏa mãn.

Trong hệ thống đơn giản, các mốc này có thể nằm rất sát nhau. Trong hệ thống nhiều bước chuẩn bị, khoảng cách có thể là vài giây, vài phút hoặc kéo dài vô hạn khi tác vụ bị treo.

## 2. Phân biệt các mốc vòng đời

Ba sự kiện Spring Boot quan trọng:

| Sự kiện | Ý nghĩa chính | Điều chưa thể kết luận |
|---|---|---|
| `ContextRefreshedEvent` | Spring context đã hoàn tất một lần refresh | Các Boot runners đã chạy xong, ứng dụng sẵn sàng nghiệp vụ |
| `ApplicationStartedEvent` | Spring Boot đã refresh context, trước khi gọi runners | `ApplicationRunner` và `CommandLineRunner` đã hoàn thành |
| `ApplicationReadyEvent` | Spring Boot đã gọi xong các runners và đi tới giai đoạn ready | Mọi việc bất đồng bộ hoặc hệ thống bên ngoài đã sẵn sàng |

`ContextRefreshedEvent` là sự kiện thuộc Spring Framework. Nó có thể xuất hiện nhiều lần khi ứng dụng sử dụng nhiều context hoặc có thao tác refresh đặc biệt; không nên mặc định chỉ có đúng một lần trong mọi kiến trúc.

`ApplicationStartedEvent` và `ApplicationReadyEvent` là sự kiện vòng đời của Spring Boot. Trong đường khởi động thành công thông thường, `ApplicationReadyEvent` xảy ra sau các runners. Spring Boot sau đó công bố readiness chấp nhận traffic qua cơ chế availability.

### Ví dụ về sự khác biệt thời điểm

Giả sử startup có ba việc:

~~~text
0.0s   Ứng dụng bắt đầu chạy
1.2s   ApplicationContext refresh xong
1.3s   ApplicationStartedEvent
1.3s   ApplicationRunner bắt đầu nạp dữ liệu (đồng bộ)
5.0s   ApplicationRunner hoàn tất
5.0s   ApplicationReadyEvent
5.0s   Spring Boot công bố readiness ACCEPTING_TRAFFIC
~~~

Trong khoảng từ 1,2 giây đến 5 giây, context có thể đã đầy đủ các bean nhưng ứng dụng **chưa hoàn tất bước chuẩn bị đồng bộ**.

Nếu thay công việc đó bằng tác vụ nền:

~~~text
0.0s   Ứng dụng bắt đầu chạy
1.2s   ApplicationContext refresh xong
1.3s   ApplicationRunner gửi yêu cầu nạp cache vào executor
1.3s   ApplicationRunner trả về ngay
1.3s   ApplicationReadyEvent
1.3s   Boot công bố readiness ACCEPTING_TRAFFIC
5.0s   Tác vụ nền mới nạp cache xong
~~~

Trong ví dụ thứ hai, mốc ready theo Spring Boot đến **trước khi cache hoàn thành**. Đây là tình huống rất dễ bị bỏ qua.

Các mốc thời gian chỉ có mục đích minh họa, không phải số liệu mặc định của Spring Boot.

## 3. Tại sao web server có thể chạy trước khi ứng dụng thực sự ready?

Với ứng dụng web dùng embedded server, việc khởi động server gắn với quá trình tạo và refresh web application context. Cổng HTTP có thể đã mở trước khi các runner hoàn tất.

Điều này tạo ra hai khái niệm:

- **Port đang lắng nghe:** một TCP connection có thể được chấp nhận và một HTTP request có thể được xử lý.
- **Ứng dụng được phép nhận lưu lượng phục vụ:** toàn bộ điều kiện khởi động và điều kiện nghiệp vụ quan trọng đã đạt.

Không nên dùng phép thử “gọi được `http://localhost:8080`” để kết luận startup hoàn tất. Một endpoint đơn giản có thể phản hồi 200, trong khi endpoint khác cần cache hoặc dữ liệu tham chiếu vẫn thất bại.

Ví dụ:

~~~text
Load balancer
    |
    |  Nếu bỏ qua readiness:
    v
Spring Boot HTTP server (đã listen)
    |
    +-- GET /ping        -> 200
    |
    +-- GET /products    -> lỗi vì cache chưa nạp xong
~~~

Cách triển khai an toàn hơn là yêu cầu ingress hoặc orchestrator **chỉ điều hướng traffic sau khi readiness probe báo đạt**, đồng thời bảo vệ ở tầng ứng dụng đối với đường gọi có thể đi vòng qua hệ thống điều phối.

Một readiness probe chỉ có ý nghĩa nếu điều kiện nó kiểm tra thực sự bao phủ các tài nguyên cần thiết để xử lý traffic tương ứng.

## 4. ApplicationRunner và CommandLineRunner là bước startup đồng bộ

`ApplicationRunner` và `CommandLineRunner` là các hook chạy sau khi context đã refresh. Spring Boot gọi các runner đã được đăng ký theo thứ tự, và chờ mỗi lần gọi trả về.

Ví dụ:

~~~java
package com.example.bootstrap;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class RequiredPreparationRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Bắt đầu kiểm tra dữ liệu bắt buộc...");

        boolean requiredDataAvailable = checkRequiredData();

        if (!requiredDataAvailable) {
            throw new IllegalStateException(
                    "Dữ liệu bắt buộc chưa sẵn sàng");
        }

        System.out.println("Hoàn tất chuẩn bị bắt buộc.");
    }

    private boolean checkRequiredData() {
        // Mô phỏng kiểm tra; thay bằng kiểm tra thực tế của ứng dụng.
        return true;
    }
}
~~~

Trong ví dụ này, phương thức `run(...)` chỉ trả về khi phần kiểm tra đồng bộ kết thúc. Nếu nó ném exception ra ngoài, Spring Boot coi quá trình startup thất bại thay vì phát mốc ready thành công.

`@Order(10)` có thể dùng để phối hợp thứ tự nhiều runner khi có phụ thuộc giữa những bước chuẩn bị. Cần nhớ rằng **thứ tự không giải quyết được tác vụ chạy ngầm**: một runner được gọi trước nhưng nộp việc vào thread pool và trả về ngay thì không bảo đảm công việc kết thúc trước runner kế tiếp.

### Khi nào thích hợp chạy đồng bộ?

Nên cân nhắc startup đồng bộ khi:

- Thiếu dữ liệu hoặc cấu hình khiến mọi request nghiệp vụ đều sai.
- Công việc có thời gian hoàn thành tương đối ngắn và dự đoán được.
- Lỗi cần làm ứng dụng startup thất bại ngay.
- Tác vụ có thể chạy lặp lại một cách an toàn sau mỗi lần deploy hoặc restart.

Ví dụ hợp lý có thể là kiểm tra schema tối thiểu, xác thực cấu hình bắt buộc hoặc nạp một bảng tra cứu nhỏ không thể thiếu.

### Khi nào không nên chặn startup quá lâu?

Một thao tác tốn hàng chục phút, phụ thuộc dịch vụ không ổn định hoặc cần retry trong thời gian dài có thể làm ứng dụng bị kẹt ở giai đoạn startup. Khi đó có thể chọn mô hình xử lý bất đồng bộ **kết hợp readiness gate**, hoặc chuyển công việc ra một job riêng và để ứng dụng theo dõi kết quả.

Lựa chọn cần xuất phát từ yêu cầu nghiệp vụ và chiến lược vận hành, chứ không chỉ từ việc viết code tiện hơn.

## 5. “Runner chạy xong” khác với “công việc được runner khởi chạy đã xong”

Xét hai đoạn code.

**Cách A — chờ đến khi hoàn thành:**

~~~java
@Override
public void run(ApplicationArguments args) {
    catalogService.loadAllSynchronously();
}
~~~

Giả định `loadAllSynchronously()` chỉ trả về khi nạp xong dữ liệu hoặc ném lỗi. Spring Boot phải đợi nó kết thúc trước khi tiếp tục.

**Cách B — giao việc cho thread nền rồi trả về:**

~~~java
@Override
public void run(ApplicationArguments args) {
    executor.execute(catalogService::loadAllSynchronously);
}
~~~

Với cách B, `executor.execute(...)` thường trả về ngay sau khi tác vụ được chấp nhận. Spring Boot không tự theo dõi thread đó để biết cache đã hoàn thành hay chưa. Nó chỉ biết lời gọi `run(...)` đã kết thúc.

Trong đoạn ví dụ, `catalogService` và `executor` là những dependency giả định do ứng dụng cấu hình.

Một số biến thể có hành vi tương tự:

- Gọi một method `@Async` thông qua Spring proxy.
- Khởi chạy `CompletableFuture.runAsync(...)` nhưng không đợi kết quả.
- Tạo một `Thread` và gọi `start()`.
- Đăng ký công việc cho scheduler hoặc hàng đợi.
- Kích hoạt một nhiệm vụ nạp cache có cơ chế refresh ngầm.

**Điểm cần quản lý không phải là runner hay event đã chạy, mà là sự hoàn thành thực tế của điều kiện chuẩn bị.**

## 6. @PostConstruct và SmartLifecycle cũng không luôn là “mọi thứ đã sẵn sàng”

`@PostConstruct` được gọi trong quá trình khởi tạo bean. Nếu một phương thức `@PostConstruct` làm việc đồng bộ và không ném lỗi, phần công việc đó đã hoàn thành trước khi bean được coi là khởi tạo xong.

Tuy nhiên, nếu nó chỉ khởi chạy một thread hoặc giao việc cho executor rồi trả về thì công việc nền vẫn tiếp diễn:

~~~java
@PostConstruct
public void init() {
    backgroundExecutor.execute(this::rebuildIndex);
}
~~~

Đoạn trên chỉ minh họa hành vi bất đồng bộ. `@PostConstruct` không phải là nơi lý tưởng để tích hợp một quy trình nghiệp vụ kéo dài vì việc khởi tạo bean dễ bị ảnh hưởng bởi thời gian và lỗi của tác vụ.

Tương tự, một bean triển khai `SmartLifecycle` có thể khởi động một consumer hoặc kết nối khi context refresh. `start()` kết thúc có thể chỉ có nghĩa là “đã yêu cầu worker bắt đầu”, không có nghĩa consumer đã nhận được phân vùng, nạp snapshot hoặc đồng bộ trạng thái đầy đủ.

Với `@Scheduled`, lần thực thi đầu tiên phụ thuộc lịch, delay và cấu hình scheduler. Không thể suy ra rằng tác vụ theo lịch đã chạy xong chỉ vì context được refresh.

Bảng so sánh:

| Cơ chế | Điểm mà Spring thường chờ | Rủi ro khi bên trong khởi tạo async |
|---|---|---|
| `@PostConstruct` | Method khởi tạo trả về | Thread được tạo vẫn chạy nền |
| `SmartLifecycle.start()` | Method `start()` hoàn thành | Consumer/service có thể chưa kết nối hoặc đồng bộ xong |
| `ApplicationRunner.run()` | Method `run()` trả về | Future hoặc task được submit chưa hoàn tất |
| `@EventListener(ApplicationReadyEvent.class)` | Listener đồng bộ trả về | Task nền do listener khởi chạy vẫn chưa hoàn thành |
| `@Scheduled` | Không phải startup barrier | Lần chạy đầu có thể xảy ra sau mốc ready |

Các cơ chế này có mục đích khác nhau. Không nên chọn hook dựa trên suy luận rằng Spring sẽ tự chờ mọi công việc được khởi tạo bên trong.

## 7. Readiness, liveness và trạng thái sẵn sàng nghiệp vụ

Spring Boot có cơ chế **Application Availability** để thể hiện những tín hiệu vòng đời quan trọng. Hai trạng thái thường gặp:

- `LivenessState.CORRECT`: tiến trình có thể hoạt động, không nhất thiết đã đủ điều kiện nhận request nghiệp vụ.
- `ReadinessState.ACCEPTING_TRAFFIC`: theo vòng đời Spring Boot, ứng dụng đã đi tới giai đoạn sẵn sàng nhận traffic.
- `ReadinessState.REFUSING_TRAFFIC`: ứng dụng chưa hoặc không còn muốn nhận traffic.

Nên phân biệt:

**Liveness trả lời:** tiến trình này còn ở trạng thái có thể vận hành hay không?

**Readiness trả lời:** tiến trình này có nên được điều hướng các request mới vào lúc này hay không?

Trong hệ thống điều phối như Kubernetes, readiness thường dùng để loại một pod khỏi danh sách endpoint phục vụ traffic mà không nhất thiết phải restart pod. Liveness thường được dùng để quyết định khi nào cần xử lý một tiến trình không còn hoạt động đúng, ví dụ restart.

### Trạng thái Spring Boot và điều kiện nghiệp vụ không tự đồng bộ

Spring Boot có thể công bố `ReadinessState.ACCEPTING_TRAFFIC` sau `ApplicationReadyEvent` mặc dù một tác vụ nạp dữ liệu bất đồng bộ vẫn chạy.

Do đó, nếu readiness của hệ thống thật sự phụ thuộc vào tác vụ ấy, cần **bổ sung điều kiện readiness riêng** thay vì chỉ tin vào một mốc lifecycle.

Chẳng hạn, ta có thể coi ứng dụng chỉ sẵn sàng khi:

~~~text
Spring Boot đã tới trạng thái ready
                  AND
Dữ liệu chuẩn bị nghiệp vụ đã hoàn thành
                  AND
Những phụ thuộc bắt buộc đang ở trạng thái sử dụng được
                  |
                  v
Readiness probe -> UP
~~~

Không nhất thiết mọi dependency ngoài hệ thống đều phải kiểm tra bằng network call ở mỗi lần health probe. Thiết kế health check cần tránh tạo ra tải lớn hoặc biến một sự cố tạm thời, không ảnh hưởng request chính, thành lỗi trên toàn bộ pod.

## 8. Một lỗi thường gặp: đánh dấu ACCEPTING_TRAFFIC quá sớm

Giả sử listener này chạy khi có `ApplicationReadyEvent`:

~~~java
@EventListener(ApplicationReadyEvent.class)
public void onReady() {
    preparationService.startAsync();
}
~~~

Nếu `startAsync()` chỉ submit một tác vụ và trả về, Spring Boot có thể tiếp tục công bố readiness chấp nhận traffic ngay sau listener. Tác vụ chuẩn bị có thể còn chưa bắt đầu thực hiện.

Một lỗi tinh vi khác là phát `ReadinessState.REFUSING_TRAFFIC` quá sớm rồi giả định nó sẽ giữ nguyên. Spring Boot có thể phát trạng thái `ACCEPTING_TRAFFIC` sau đó trong luồng startup bình thường và ghi đè ý định ban đầu.

Vì vậy, một chiến lược rõ ràng cho trường hợp chuẩn bị bất đồng bộ là **bổ sung một HealthIndicator kiểm tra trạng thái chuẩn bị vào readiness health group**. Khi đó readiness tổng hợp vẫn có thể báo không đạt dù trạng thái vòng đời của Boot đã chuyển sang ACCEPTING_TRAFFIC.

## 9. Ví dụ đầy đủ: nạp tài nguyên bất đồng bộ nhưng chưa mở readiness

Ta xây dựng ví dụ Spring Boot 3.x gồm những thành phần:

1. Một `PreparationHealthIndicator` giữ trạng thái `PREPARING`, `READY` hoặc `FAILED`.
2. Một service chạy công việc chuẩn bị bất đồng bộ.
3. Một listener dùng `ApplicationReadyEvent` để bắt đầu công việc.
4. Cấu hình Spring Boot Actuator đưa điều kiện `preparation` vào readiness group.

Ví dụ sử dụng thao tác đợi vài giây để mô phỏng công việc nạp dữ liệu. Đây là **mô phỏng kỹ thuật**, không phải gợi ý dùng `Thread.sleep` trong production.

### 9.1. Khai báo dependency

Nếu dự án đã có web starter, cần thêm Actuator để tạo health endpoint. Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Nếu dùng Gradle (Groovy DSL):

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
~~~

Spring Boot và dependency management của dự án nên quản lý phiên bản các starter thay vì chọn phiên bản tùy ý cho từng starter.

### 9.2. Tạo indicator riêng cho công việc chuẩn bị

File `PreparationHealthIndicator.java`:

~~~java
package com.example.preparation;

import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("preparationHealthIndicator")
public class PreparationHealthIndicator implements HealthIndicator {

    private enum Phase {
        PREPARING, READY, FAILED
    }

    private final AtomicReference<Phase> phase =
            new AtomicReference<>(Phase.PREPARING);

    public void markReady() {
        phase.set(Phase.READY);
    }

    public void markFailed() {
        phase.set(Phase.FAILED);
    }

    @Override
    public Health health() {
        Phase current = phase.get();

        if (current == Phase.READY) {
            return Health.up()
                    .withDetail("phase", current.name())
                    .build();
        }

        return Health.down()
                .withDetail("phase", current.name())
                .build();
    }
}
~~~

Một vài điểm quan trọng:

- Giá trị ban đầu là `PREPARING`, do đó ứng dụng chưa đạt readiness nghiệp vụ ngay khi indicator được tạo.
- `AtomicReference` cho phép thread chạy task và thread thực hiện health check thấy trạng thái cập nhật một cách an toàn.
- `PREPARING` và `FAILED` đều trả về `DOWN` vì chưa được phép phục vụ traffic dựa trên điều kiện này.
- Tên bean `preparationHealthIndicator` được Actuator nhận diện dưới tên health contributor `preparation`. Tên đó sẽ được dùng ở cấu hình readiness group.

Ở hệ thống thực tế, có thể thêm thời điểm chuẩn bị bắt đầu, thời điểm hoàn tất hoặc mã lỗi đã được làm sạch. Không nên đưa secret hoặc exception thô có thông tin nhạy cảm vào public health response.

### 9.3. Khai báo executor do Spring quản lý

File `PreparationAsyncConfiguration.java`:

~~~java
package com.example.preparation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class PreparationAsyncConfiguration {

    @Bean("preparationExecutor")
    public ThreadPoolTaskExecutor preparationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("prepare-");
        executor.initialize();
        return executor;
    }
}
~~~

`@EnableAsync` cho phép xử lý các method được đánh dấu `@Async` thông qua proxy của Spring. Tên executor tường minh giúp tránh dùng chung bừa bãi với thread pool phục vụ nhiệm vụ khác.

Không nên giả định việc gọi một method `@Async` từ chính method khác trong **cùng instance** sẽ chuyển sang thread nền, vì self-invocation có thể bỏ qua proxy. Trong ví dụ tiếp theo, một bean khác sẽ gọi service bất đồng bộ.

### 9.4. Tạo service thực hiện công việc chuẩn bị

File `PreparationService.java`:

~~~java
package com.example.preparation;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class PreparationService {

    private static final Logger log =
            LoggerFactory.getLogger(PreparationService.class);

    private final PreparationHealthIndicator indicator;

    public PreparationService(PreparationHealthIndicator indicator) {
        this.indicator = indicator;
    }

    @Async("preparationExecutor")
    public void prepare() {
        log.info("Bắt đầu chuẩn bị dữ liệu nền");

        try {
            // Mô phỏng nạp cache hoặc khởi tạo tài nguyên.
            // Thay bằng công việc thực tế trong ứng dụng.
            Thread.sleep(3_000);

            indicator.markReady();
            log.info("Chuẩn bị dữ liệu hoàn tất");
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            indicator.markFailed();
            log.warn("Công việc chuẩn bị bị ngắt", exception);
        } catch (Exception exception) {
            indicator.markFailed();
            log.error("Công việc chuẩn bị thất bại", exception);
        }
    }
}
~~~

`@Async("preparationExecutor")` khiến công việc chạy qua executor nếu được gọi thông qua Spring proxy. Method `prepare()` trả về từ phía caller trước khi `Thread.sleep(...)` hoặc công việc thực tế kết thúc.

Nếu có lỗi, indicator giữ `DOWN` và logger ghi nguyên nhân. Mẫu này cố ý không tự retry; khi triển khai thật cần xác định chính sách retry, timeout hoặc fail-fast.

### 9.5. Bắt đầu từ ApplicationReadyEvent

File `PreparationStarter.java`:

~~~java
package com.example.preparation;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class PreparationStarter {

    private final PreparationService preparationService;

    public PreparationStarter(PreparationService preparationService) {
        this.preparationService = preparationService;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady() {
        preparationService.prepare();
    }
}
~~~

`PreparationStarter` gọi method `prepare()` trên **bean khác**, nên lời gọi đi qua proxy `@Async`. Listener có thể trả về ngay sau khi executor nhận tác vụ.

Dùng `ApplicationReadyEvent` ở đây không nhằm chứng minh công việc đã xong; ngược lại, nó chỉ là **thời điểm khởi phát** công việc sau các bước startup đồng bộ của Boot.

### 9.6. Cấu hình readiness group

Trong `src/main/resources/application.properties`:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.readiness.include=readinessState,preparation
~~~

Ý nghĩa:

- `management.endpoint.health.probes.enabled=true` bật các health group phục vụ liveness và readiness ngay cả trong môi trường không tự kích hoạt probe.
- `readinessState` là health contributor phản ánh trạng thái readiness vòng đời Spring Boot.
- `preparation` là health contributor do `PreparationHealthIndicator` cung cấp.

Khi một contributor trong readiness group báo `DOWN`, health group tổng hợp thông thường cũng báo không đạt.

Nếu muốn expose endpoint probe trên cùng cổng web chính trong cấu hình có management port riêng, Spring Boot còn hỗ trợ:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

Tùy cấu hình, các đường dẫn probe bổ sung như `/readyz` và `/livez` sẽ được cung cấp trên main server port. Cần kiểm tra lại topology mạng và cấu hình triển khai thật để bảo đảm probe đi qua đúng cổng cần kiểm tra.

### 9.7. Quan sát kết quả

Với web application có Actuator, gọi:

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
~~~

Ở đầu quá trình, indicator nghiệp vụ vẫn `PREPARING`, nên readiness group có thể trả:

~~~text
HTTP/1.1 503 Service Unavailable
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"DOWN"}
~~~

Sau khi công việc hoàn tất, indicator trả `UP`:

~~~text
HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
~~~

Đây là response minh họa. Nội dung chi tiết có thể bị ẩn bởi cấu hình Actuator và status code có thể được tùy chỉnh.

Trạng thái Boot ở mức `ApplicationAvailability.getReadinessState()` có thể đã là `ACCEPTING_TRAFFIC` trong khi **health group readiness** vẫn là `DOWN` do `preparation`. Đây chính là lý do cần hiểu sự khác biệt giữa trạng thái lifecycle và trạng thái readiness tổng hợp.

## 10. Khi nào cần giữ công việc đồng bộ, khi nào dùng readiness gate?

Hai chiến lược chính:

| Tiêu chí | Chuẩn bị đồng bộ trước ready | Chuẩn bị async và readiness gate |
|---|---|---|
| Cách tổ chức | Runner hoặc callback startup chờ công việc xong | Tác vụ chạy nền; có indicator phản ánh hoàn thành |
| Mốc `ApplicationReadyEvent` | Đến sau khi runner đồng bộ kết thúc | Có thể đến trước khi task nền hoàn thành |
| Tín hiệu trạng thái nghiệp vụ | Có thể dùng thất bại của runner để chặn startup | Cần kiểm soát readiness riêng |
| Lỗi chuẩn bị | Exception có thể làm startup thất bại | Cần chính sách retry, báo DOWN, hoặc chủ động dừng app |
| Ưu điểm | Dễ suy luận tính thứ tự và tính bắt buộc | Không khóa luồng startup vì công việc dài |
| Rủi ro | Startup kéo dài, dễ timeout deploy | Có thể báo ready sớm nếu quên gate |

### Chọn đồng bộ khi điều kiện là bắt buộc và cần fail-fast

Nếu thiếu điều kiện khiến ứng dụng vô dụng và việc chuẩn bị hoàn thành nhanh, runner đồng bộ thường rõ ràng:

~~~java
@Bean
ApplicationRunner warmUpRequiredData(RequiredCatalogLoader loader) {
    return args -> loader.loadAndWait();
}
~~~

`RequiredCatalogLoader` và `loadAndWait()` là lớp/phương thức minh họa do ứng dụng tự xây dựng.

Nếu `loadAndWait()` ném exception, Spring Boot xử lý lỗi startup thay vì tới ready. Nếu nó thành công, ta biết riêng công việc đồng bộ này đã xong trước mốc ready.

### Chọn async + readiness khi cần khởi động hạ tầng trước

Ví dụ một worker cần khởi tạo kết nối, sau đó đồng bộ một snapshot dữ liệu lớn. Việc khởi động application context có thể ngắn, còn thời gian đồng bộ lâu hơn nhiều. Khi đó dùng readiness indicator cho snapshot giúp hệ thống báo rõ “tiến trình còn chạy nhưng chưa phục vụ”.

Tuy nhiên không nên đánh đồng “đã tạo background task” với “đã nạp thành công”. Chỉ chuyển indicator sang ready sau khi hoàn tất các bước kiểm tra thành công.

## 11. Điều gì xảy ra nếu tác vụ chuẩn bị thất bại?

Có ba chính sách thường dùng; cần lựa chọn một cách rõ ràng.

### A. Thất bại đồng nghĩa ứng dụng không thể chạy

Nếu điều kiện bắt buộc không đạt và ứng dụng không có đường phục hồi trong tiến trình hiện tại, runner đồng bộ có thể ném exception để startup thất bại.

Lợi ích: trạng thái thất bại rõ ràng, không giữ một process không phục vụ được.

Nhược điểm: nếu phụ thuộc ngoài không ổn định, có nguy cơ vòng lặp restart liên tục; cần phù hợp với chính sách backoff và retry của hệ thống triển khai.

### B. Ứng dụng có thể tự phục hồi trong nền

Nếu chuẩn bị là tác vụ có thể retry, giữ readiness `DOWN`, ghi log và thử lại có kiểm soát. Khi thành công mới chuyển sang `UP`.

Cần cân nhắc:

- Timeout cho mỗi lần thử.
- Exponential backoff và giới hạn tần suất retry.
- Điều kiện hủy retry khi ứng dụng đang shutdown.
- Phân biệt lỗi cấu hình không thể phục hồi và lỗi mạng tạm thời.
- Metrics về thời gian chuẩn bị, số lần thử và trạng thái cuối.
- Cảnh báo khi readiness giữ `DOWN` quá lâu.

Không nên retry vô hạn với tần suất cao hoặc giữ thread bận mà không có cơ chế hủy.

### C. Ứng dụng phục vụ chế độ suy giảm

Một số chức năng có thể hoạt động ngay cả khi cache phụ chưa xong. Khi đó không nhất thiết đánh dấu toàn bộ pod `DOWN`. Có thể cung cấp endpoint nghiệp vụ có guard theo từng tính năng, hoặc công bố mức khả dụng riêng cho từng module.

Không nên đưa tất cả tác vụ tùy chọn vào readiness group: một bộ đếm analytics không cập nhật được thường không nên làm toàn bộ API bị loại khỏi traffic.

## 12. Các trường hợp “nhìn thấy UP nhưng vẫn chưa sẵn sàng”

Một hệ thống có thể xuất hiện những hiểu lầm như:

**Health endpoint trả 200 nhưng dịch vụ cần database chưa dùng được.** Có thể endpoint chỉ kiểm tra liveness hoặc nhóm health chưa bao gồm điều kiện bắt buộc của dịch vụ.

**HTTP server mở port nhưng chưa nhận được request hữu ích.** Web server có thể bắt đầu nghe từ giai đoạn refresh, trong khi runner còn xử lý dữ liệu.

**`ApplicationReadyEvent` đã phát nhưng cache vẫn đang loading.** Listener hoặc runner đã submit một task async; Spring Boot không tự đợi task đó.

**`ReadinessState.ACCEPTING_TRAFFIC` nhưng readiness group `DOWN`.** Một indicator được bổ sung vào health group vẫn chưa đạt. Hai giá trị thuộc hai lớp diễn giải khác nhau.

**Một bean `SmartLifecycle` báo running nhưng consumer chưa nhận được dữ liệu.** Trạng thái của bean có thể chỉ phản ánh vòng chạy đã được bắt đầu, không phản ánh việc đồng bộ nghiệp vụ đã xong.

**Một dependency bên ngoài vừa trở nên unavailable.** Ready lúc startup không bảo đảm ready mãi mãi; readiness cần phản ánh những điều kiện vận hành quan trọng nếu chính sách ứng dụng yêu cầu.

Trong mọi tình huống, cần xác định **ai là người công bố trạng thái**, **trạng thái mô tả điều gì**, và **điều kiện thực sự cần cho request**.

## 13. Kiểm tra readiness trong Kubernetes và load balancer

Trong Kubernetes, readiness probe thường kiểm tra endpoint như:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Đây là đoạn minh họa cho một container lắng nghe tại cổng 8080, dùng Actuator readiness endpoint.

Readiness probe không nhất thiết ngăn được mọi request trực tiếp. Nó chủ yếu giúp hệ thống điều phối traffic **tránh gửi request qua các tuyến tôn trọng readiness**.

Nếu ứng dụng cần khởi động rất lâu, có thể cân nhắc `startupProbe` để cho phép giai đoạn khởi động có thời gian phù hợp trước khi liveness probe bắt đầu gây restart. `startupProbe` khác với readiness: nó hỗ trợ xử lý ứng dụng khởi động chậm, không phải thay thế điều kiện nghiệp vụ để phục vụ request.

Cũng cần phân biệt:

- **Liveness DOWN:** có thể dẫn tới restart theo cấu hình orchestrator.
- **Readiness DOWN:** thường khiến instance bị loại khỏi tuyến nhận traffic mới.
- **Shutdown:** hệ thống cần ngừng nhận request mới, xử lý các request đang chạy và giải phóng tài nguyên.

Mỗi tín hiệu có tác động vận hành riêng; không nên dùng readiness DOWN như một cách mặc định để yêu cầu orchestrator restart ứng dụng.

## 14. Liên hệ với shutdown: không chỉ mở cổng, còn phải đóng đúng lúc

Mối quan hệ giữa startup và shutdown có tính đối xứng:

~~~text
STARTUP
  Tạo context
      |
      v
  Hoàn tất điều kiện chuẩn bị
      |
      v
  Chấp nhận traffic

SHUTDOWN
  Bắt đầu từ chối traffic mới
      |
      v
  Hoàn thành / hủy việc đang chạy theo chính sách
      |
      v
  Đóng tài nguyên, context và process
~~~

Một số cấu hình liên quan:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Với server hỗ trợ graceful shutdown, Spring Boot cố gắng xử lý việc dừng nhận request mới và dành thời gian cho request đang xử lý trong giới hạn cấu hình. Điều này **không tự bảo đảm** rằng mọi background task, consumer hoặc tác vụ chuẩn bị đang chạy sẽ hoàn tất trước khi JVM thoát.

Nếu ứng dụng có worker nền, cần quản lý lifecycle riêng, chẳng hạn:

- Ghi nhận tín hiệu đang dừng để không khởi động thêm việc mới.
- Cho phép hủy hoặc interrupt công việc có thể dừng an toàn.
- Chờ các tác vụ in-flight quan trọng trong một thời gian giới hạn.
- Dùng `SmartLifecycle.stop(...)`, callback hủy bean hoặc cơ chế đóng executor phù hợp.
- Không báo readiness `UP` khi hệ thống không còn chấp nhận việc mới.

Trong Spring Boot, readiness state thường chuyển sang từ chối traffic khi tiến trình đi vào luồng shutdown có quản lý. Tuy nhiên, cần kiểm tra thực tế trình tự xả kết nối ở môi trường triển khai, nhất là khi có load balancer hoặc proxy mất một khoảng thời gian để cập nhật danh sách instance.

**Context đang đóng** cũng không tự có nghĩa mọi tác vụ nền đã kết thúc sạch sẽ. Quản lý startup và shutdown cần cùng một mô hình ownership của công việc.

## 15. Đo lường và quan sát trạng thái chuẩn bị

Để phân biệt “context sống” với “dữ liệu đã sẵn sàng”, nên thu thập những tín hiệu tối thiểu:

| Tín hiệu | Ý nghĩa |
|---|---|
| Thời điểm bắt đầu startup | Mốc tổng thời gian chuẩn bị |
| Thời điểm context refresh xong | Hạ tầng Spring được dựng xong |
| Thời điểm runners kết thúc | Boot đã đi qua bước startup đồng bộ |
| Thời điểm chuẩn bị nghiệp vụ hoàn tất | Dữ liệu hoặc tài nguyên bắt buộc thật sự usable |
| Thời lượng chuẩn bị | Biết chậm ở startup hay ở worker nền |
| Trạng thái `PREPARING`, `READY`, `FAILED` | Dùng cho readiness và cảnh báo |
| Lý do thất bại đã được chuẩn hóa | Hỗ trợ debug mà không lộ dữ liệu nhạy cảm |

Ví dụ log có thể được thiết kế theo cách đơn giản:

~~~text
INFO  Application context refreshed
INFO  Starting mandatory runners
INFO  Spring Boot ready event observed
INFO  Beginning asynchronous catalog preparation
INFO  Preparation completed: 3270 ms
INFO  Readiness health contributor preparation=UP
~~~

Đây là ví dụ về log ứng dụng tự ghi, không phải các dòng log mặc định bắt buộc của Spring Boot.

Nếu một instance liên tục ở trạng thái `PREPARING`, người vận hành cần biết nó đang chờ gì, đã thử bao nhiêu lần và điều kiện nào sẽ làm nó chuyển sang `READY` hoặc `FAILED`.

## 16. Bài thực hành: quan sát khoảng cách giữa context và business readiness

Có thể thực hiện bài tập ngay trên ứng dụng mẫu ở mục 9.

### Thí nghiệm 1 — Chuẩn bị chậm có kiểm soát

Giữ `Thread.sleep(3_000)` trong `PreparationService`, chạy ứng dụng rồi liên tục gọi:

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
~~~

Quan sát một giai đoạn ban đầu trả `DOWN`, sau đó chuyển sang `UP` khi công việc nền gọi `markReady()`.

Mốc chính cần kiểm tra: `ApplicationReadyEvent` có thể đã xảy ra trước khi `preparation` trả `UP`.

### Thí nghiệm 2 — Công việc thất bại

Thay nội dung mô phỏng trong `prepare()` bằng:

~~~java
throw new IllegalStateException("Dữ liệu giả lập không hợp lệ");
~~~

Đặt lệnh này bên trong khối `try` của ví dụ để nhánh `catch (Exception exception)` ghi lỗi và gọi `markFailed()`.

Kỳ vọng: process có thể vẫn còn chạy, nhưng readiness group tiếp tục `DOWN`. Nếu hệ thống yêu cầu fail-fast, cần thiết kế thêm chính sách chủ động đóng ứng dụng hoặc chuyển tác vụ thành runner đồng bộ.

### Thí nghiệm 3 — So sánh với runner đồng bộ

Di chuyển mô phỏng chuẩn bị sang một `ApplicationRunner` đồng bộ. Khởi động lại và quan sát:

- `ApplicationStartedEvent` đến trước khi runner bắt đầu.
- `ApplicationReadyEvent` đến sau khi runner trả về.
- Nếu runner ném exception ra ngoài, ứng dụng đi vào xử lý startup failure thay vì ready thành công.

### Thí nghiệm 4 — Chỉ dùng readinessState

Tạm thời đổi readiness group sang:

~~~properties
management.endpoint.health.group.readiness.include=readinessState
~~~

Khi đó health group không còn dựa trên `preparation`. Mốc readiness của Boot có thể chuyển `UP` trong lúc mô phỏng chuẩn bị vẫn chạy. Điều này cho thấy **không thể dùng một trạng thái khởi động mặc định thay cho tất cả điều kiện nghiệp vụ**.

Khôi phục cấu hình ban đầu sau khi thử nghiệm.

## 17. Những nhầm lẫn cần tránh

**“Context đã refresh nên hệ thống sẵn sàng.”** Sai. Các runner và tác vụ async có thể chưa hoàn thành.

**“Server đã mở port thì ingress có thể gửi traffic.”** Không nhất thiết. Cần readiness probe phù hợp và tuyến traffic tôn trọng kết quả đó.

**“ApplicationStartedEvent là ready.”** Không. Spring Boot còn chạy các runners sau mốc started.

**“ApplicationReadyEvent bảo đảm mọi việc nền xong.”** Không. Nó phản ánh việc hoàn tất đường startup đồng bộ mà Boot quản lý, không phải mọi tác vụ được submit ra executor.

**“Gọi @Async trong runner sẽ khiến Boot chờ method đó xong.”** Không. Nếu gọi qua proxy, method async trả quyền điều khiển cho runner trước khi tác vụ thực tế hoàn tất.

**“ReadinessState.ACCEPTING_TRAFFIC luôn có nghĩa business readiness đạt.”** Không. Trạng thái của Boot chỉ thể hiện góc nhìn lifecycle; cần thêm điều kiện nghiệp vụ nếu hệ thống yêu cầu.

**“Mọi dependency ngoài hệ thống phải kiểm tra live ở mỗi health request.”** Không. Kiểm tra quá nhiều phụ thuộc có thể khiến endpoint health chậm, tạo tải lớn hoặc làm ứng dụng không phục vụ được do một dependency tùy chọn.

**“Readiness DOWN tức là phải restart process.”** Không. Readiness và liveness có mục đích khác nhau.

**“Graceful shutdown tự xử lý mọi background task.”** Không. Các công việc nền cần cơ chế dừng hoặc hoàn tất có quản lý.

## 18. Nguyên tắc thiết kế nên ghi nhớ

Khi một ứng dụng có bước chuẩn bị riêng, hãy xác định rõ:

1. **Điều kiện nào là bắt buộc để nhận traffic?** Không đưa những tác vụ tùy chọn vào readiness một cách máy móc.
2. **Ai sở hữu tác vụ chuẩn bị?** Runner, service, scheduler, worker nền hay một job riêng?
3. **Ai biết khi nào tác vụ hoàn tất?** Chờ đồng bộ, future được quản lý, một trạng thái atomically published hoặc dữ liệu được kiểm chứng.
4. **Lỗi có thể phục hồi không?** Quyết định fail-fast, retry hay degraded mode.
5. **Readiness được tổng hợp từ những tín hiệu nào?** Xác nhận endpoint thực sự báo đúng khi đang chuẩn bị và khi thất bại.
6. **Shutdown sẽ ngắt hoặc chờ tác vụ thế nào?** Không để luồng nền chạy không chủ sở hữu.
7. **Có quan sát được thời gian và nguyên nhân không?** Log, metric và cảnh báo cần trả lời được “đang chờ gì”.

Đối với một dịch vụ có khả năng phục vụ sớm mà vẫn đang chuẩn bị tài nguyên không bắt buộc, có thể cho phép traffic tới một số chức năng và bảo vệ phần chưa sẵn sàng bằng cơ chế riêng. Đối với hệ thống yêu cầu tính nhất quán nghiêm ngặt, readiness gate nên phản ánh điều kiện mạnh hơn.

## Kết luận

**ApplicationContext refresh thành công là mốc hạ tầng, không phải cam kết mọi công việc chuẩn bị đã kết thúc.** Spring Boot tiếp tục chạy `ApplicationRunner` và `CommandLineRunner` sau mốc context refresh; ngoài ra, những tác vụ khởi chạy bất đồng bộ có thể kéo dài ngay cả sau `ApplicationReadyEvent`.

Khi công việc là bắt buộc và ngắn, có thể để runner thực hiện **đồng bộ**, khiến Spring Boot chỉ đi tới ready sau khi công việc hoàn thành. Khi công việc là **bất đồng bộ**, nên theo dõi riêng trạng thái `PREPARING/READY/FAILED` và đưa điều kiện cần thiết vào readiness health group để không nhận traffic quá sớm.

Trong toàn bộ vòng đời **Trạng thái và dừng**, phải tách rõ **context đã được tạo**, **Boot đã hoàn tất startup**, **ứng dụng thật sự sẵn sàng nghiệp vụ** và **ứng dụng đang dừng**. Phân biệt đúng các mốc này giúp hệ thống triển khai an toàn, giảm lỗi khởi động và xử lý traffic nhất quán.

# Spring Boot starter aspectj

Một service Spring Boot có method xử lý đơn hàng cần đo thời gian thực thi, số lần gọi và kết quả để điều tra latency hoặc lỗi. Bạn có thể tự tạo Observation quanh từng method, nhưng boilerplate lặp lại dễ khiến các nhóm code ghi nhận không nhất quán. Micrometer cung cấp các annotation như @Observed, @Timed, @Counted và @NewSpan; Spring Boot có thể bật AOP để intercept method được annotate và chuyển chúng thành Observation, metrics hoặc tracing spans.

Bài **Spring Boot starter aspectj** thuộc chương **Annotation observability** của module **SPRING_BOOT_OBSERVABILITY**. Module học cách thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; hiểu context propagation, tag/cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

> **Điểm cốt lõi:** Annotation-based observability cần dependency AspectJ weaver phù hợp phiên bản Spring Boot và property management.observations.annotations.enabled=true. Spring Boot 4 đổi tên starter từ spring-boot-starter-aop sang spring-boot-starter-aspectj; Boot 3.x vẫn dùng starter AOP cũ. Starter hỗ trợ Spring AOP proxy/AspectJ annotation style cho aspects; nó không có nghĩa toàn bộ code đã được compile-time hoặc load-time woven bằng AspectJ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích vai trò của AspectJ starter trong annotation-based observability.
2. Chọn đúng dependency theo Spring Boot 3.x hoặc 4.x.
3. Bật annotation scanning bằng management.observations.annotations.enabled.
4. Phân biệt Spring AOP proxy với AspectJ compile-time/load-time weaving.
5. Dùng @Observed, @Timed, @Counted, @MeterTag và @NewSpan đúng mục đích.
6. Hiểu cách annotation interceptor tạo Observation, metrics và tracing spans.
7. Nhận diện self-invocation, method visibility và proxy limitations.
8. Tránh duplicate observations khi method đã được instrument tự động.
9. Kiểm soát low-cardinality tags và tránh dữ liệu nhạy cảm trong metrics.
10. Kiểm thử annotation interception và điều tra khi annotation không hoạt động.

## 2. AspectJ starter giải quyết việc gì?

Micrometer Observation là API thống nhất để instrument operation. ObservationRegistry điều phối handlers; tùy handler được cấu hình, một Observation có thể tạo Micrometer metrics và/hoặc tracing span.

Annotation observability giúp khai báo instrumentation gần method/class:
- @Observed: tạo Observation quanh operation.
- @Timed: ghi thời gian thực thi bằng Timer.
- @Counted: đếm số lần method được gọi.
- @MeterTag: bổ sung tag cho meter dựa trên tham số method, khi annotation support tương ứng được bật.
- @NewSpan: tạo span mới qua Micrometer Tracing.

Các annotation không tự thực thi chỉ vì import được class. Ứng dụng cần aspect/interceptor quét annotation và runtime có đủ dependencies. Spring Boot AspectJ starter đưa AspectJ weaver lên classpath và auto-configuration hỗ trợ proxy infrastructure; annotation scanning của Micrometer cần bật rõ ràng.

~~~mermaid
flowchart TD
    A["Annotated Spring bean method"] --> B["Spring AOP proxy"]
    B --> C["Micrometer annotation aspect"]
    C --> D["Observation / Timer / Span"]
    D --> E["ObservationRegistry"]
    E --> F["MeterObservationHandler"]
    E --> G["TracingObservationHandler"]
    F --> H["MeterRegistry"]
    G --> I["Tracer / exporter"]
~~~

Annotation chỉ khai báo ý định instrument. Proxy/aspect phải intercept invocation; ObservationRegistry và handlers mới quyết định signal nào được tạo và export.

## 3. Chọn đúng starter theo Spring Boot version

Tên starter thay đổi ở major version 4:

| Spring Boot version | Dependency |
|---|---|
| 3.x | org.springframework.boot:spring-boot-starter-aop |
| 4.x | org.springframework.boot:spring-boot-starter-aspectj |

Spring Boot 4 đổi tên AOP starter thành AspectJ starter trong quá trình modularization. Dùng BOM/dependency management của Spring Boot để chọn version tương thích; không tự pin AspectJ weaver version nếu không có lý do cụ thể.

### 3.1 Gradle với Spring Boot 3.x

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
~~~

### 3.2 Gradle với Spring Boot 4.x

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-aspectj'
}
~~~

Nếu dùng Maven, khai báo starter tương ứng trong dependencies. Không thêm cả hai starter cùng lúc chỉ để chắc chắn; chọn đúng artifact theo major version.

### 3.3 Vì sao cần Actuator?

AspectJ starter cung cấp AOP/AspectJ infrastructure. Actuator đưa observability/metrics auto-configuration của Spring Boot vào ứng dụng. Nếu chỉ có aspect support mà không có MeterRegistry/ObservationRegistry và handlers thích hợp, annotation không tự tạo backend telemetry hoàn chỉnh.

## 4. Bật annotation scanning

Cấu hình trong application.yml:

~~~yaml
management:
  observations:
    annotations:
      enabled: true
~~~

Property này bật quét các Micrometer observability annotations như @Observed, @Timed, @Counted, @MeterTag và @NewSpan. Theo tài liệu Spring Boot, annotation support không được bật mặc định; cần bật tường minh.

Để tạo metrics và traces:
- Có ObservationRegistry trong application context.
- Có MeterRegistry và meter observation handler cho metrics.
- Có Micrometer Tracing bridge/handler và exporter nếu muốn spans được gửi đi.
- Có annotation aspect/interceptor trên classpath và proxy có thể intercept method.

Annotation có thể được intercept nhưng không có exporter. Vì vậy kiểm tra riêng annotation scanning, Observation creation, handler, registry/tracer và export pipeline.

## 5. Spring AOP proxy và AspectJ weaving khác nhau

| Cơ chế | Cách hoạt động | Phạm vi |
|---|---|---|
| Spring AOP proxy | Tạo proxy cho Spring bean và intercept method call đi qua proxy | Join points Spring AOP hỗ trợ |
| AspectJ compile-time weaving | Compiler weave aspect vào bytecode khi build | Join points theo AspectJ language |
| AspectJ load-time weaving | Agent/classloader weave bytecode khi class được load | Join points theo AspectJ language |

Spring Boot auto-configuration thường dùng Spring AOP proxy. AspectJ annotation style dùng cú pháp @Aspect/@Around nhưng aspect có thể vẫn chạy trên Spring AOP proxy runtime. Có AspectJ weaver trên classpath không tự chứng minh compile-time hoặc load-time weaving đang hoạt động.

Không cần AspectJ weaving đầy đủ chỉ để dùng Micrometer annotation observability trong Spring Boot. Hãy dùng starter được tài liệu yêu cầu, bật property và để Spring quản lý proxy/aspect.

### 5.1 CGLIB và JDK proxies

Spring AOP có thể dùng CGLIB class-based proxies hoặc JDK interface-based proxies. Spring Boot mặc định thường dùng CGLIB; có thể chọn JDK proxies qua spring.aop.proxy-target-class=false.

Với JDK proxies, invocation phải đi qua interface proxy. Với class-based proxy, class/method phải có thể được proxy theo giới hạn subclass. Final classes/methods không thể được override để intercept theo cơ chế subclass proxy. Kiểm tra loại proxy thực tế khi annotation không chạy.

## 6. Dùng @Observed cho business operation

@Observed phù hợp để instrument operation có ý nghĩa nghiệp vụ, ví dụ reserve inventory hoặc submit order.

~~~java
import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Service;

@Service
class OrderApplicationService {

    @Observed(name = "order.submit", contextualName = "submit-order")
    public OrderResult submit(CreateOrder command) {
        return createOrder(command);
    }

    private OrderResult createOrder(CreateOrder command) {
        // Logic nghiệp vụ được giản lược.
        return new OrderResult();
    }
}
~~~

Khi method được gọi qua Spring proxy, annotation aspect có thể tạo Observation với name và contextual name đã cấu hình. Observation được chuyển thành metrics/traces tùy handlers.

Tên Observation nên ổn định và mô tả operation. Không đưa order ID, customer email, raw URL hoặc dữ liệu request vào tên Observation.

### 6.1 @Observed không tự tạo mọi metric

@Observed tạo Observation; handlers quyết định metrics/spans. Muốn đo duration cần meter observation handler. Muốn span cần tracing handler/bridge. Muốn export cần registry/exporter.

Không suy luận rằng thêm annotation sẽ tự gửi dữ liệu tới Prometheus hoặc OTLP nếu exporter chưa được cấu hình.

## 7. Dùng @Timed và @Counted

@Timed ghi thời gian thực thi method bằng Micrometer Timer. @Counted ghi số lần method được gọi bằng Counter.

~~~java
import io.micrometer.core.annotation.Counted;
import io.micrometer.core.annotation.Timed;
import org.springframework.stereotype.Service;

@Service
class ReportService {

    @Timed(value = "report.generate.duration", description = "Time to generate report")
    @Counted(value = "report.generate.calls", description = "Report generation calls")
    public Report generate(String reportType) {
        return new Report();
    }
}
~~~

Tên meter nên ổn định. Tag bổ sung cần bounded values. Nếu @Observed và @Timed cùng đặt trên method, có thể tạo nhiều instruments/observations; cần có mục đích và kiểm tra duplicate measurements.

Chọn annotation theo ý nghĩa:
- @Observed khi muốn một operation Observation có thể tạo nhiều signal.
- @Timed khi mục tiêu là đo duration.
- @Counted khi mục tiêu là đếm invocation/event.
- Custom Observation khi cần context, low/high cardinality key-values hoặc lifecycle control chi tiết.

Không gắn tất cả annotations lên mọi method. Instrumentation quá dày làm tăng noise, chi phí và duplicate signals.

## 8. @MeterTag và kiểm soát cardinality

@MeterTag cho phép tạo meter tag từ method parameter trong annotation-based metrics support. Giá trị phải được chuẩn hóa và có cardinality hữu hạn.

~~~java
import io.micrometer.core.annotation.MeterTag;
import io.micrometer.core.annotation.Timed;
import org.springframework.stereotype.Service;

@Service
class CatalogService {

    @Timed(value = "catalog.lookup")
    public Item find(@MeterTag(key = "channel") String channel) {
        return lookupItem();
    }

    private Item lookupItem() {
        return new Item();
    }
}
~~~

Ví dụ minh họa annotation usage; cần resolver/configuration phù hợp với Micrometer version để map parameter sang tag value. Chỉ dùng tập channel đã allowlist như web, mobile, partner.

Không tag orderId/customerId/userId, email, phone, account number, token, session cookie, SQL statement, exception message hoặc raw search query. Nếu giá trị không thuộc tập cho phép, map thành other/unknown thay vì phát sinh series mới.

## 9. @NewSpan trong tracing

@NewSpan thuộc Micrometer Tracing và tạo span mới quanh method khi tracing annotation support được cấu hình. Nó khác @Observed: @Observed tạo Observation, còn @NewSpan yêu cầu tracing bridge tạo span theo tracing API.

~~~java
import io.micrometer.tracing.annotation.NewSpan;
import org.springframework.stereotype.Service;

@Service
class PaymentGatewayService {

    @NewSpan("payment.authorize")
    public AuthorizationResult authorize(PaymentCommand command) {
        return new AuthorizationResult();
    }
}
~~~

Span mới thường nối với current trace context theo tracing integration. Nếu method không chạy trong trace context, span có thể là root span hoặc bắt đầu trace mới tùy context hiện hành.

Không ghi card number, CVV, token hoặc raw provider response vào span attributes. Dùng operation name, outcome và error category đã chuẩn hóa.

## 10. Proxy limitation: self-invocation

Spring AOP proxy chỉ intercept invocation đi qua proxy. Nếu một method trong cùng bean gọi trực tiếp method khác của this, lời gọi nội bộ không đi qua proxy.

~~~java
@Service
class BillingService {

    public void checkout() {
        charge(); // self-invocation: thường bypass proxy advice
    }

    @Observed(name = "billing.charge")
    public void charge() {
        // Charge payment.
    }
}
~~~

Trong ví dụ này, checkout gọi charge trên cùng target object; annotation trên charge có thể không được intercept.

Cách khắc phục:
- Tách operation được annotate sang một Spring bean khác và inject bean đó.
- Gọi method qua bean proxy từ caller.
- Nếu cần semantics không phụ thuộc proxy, tạo Observation thủ công quanh operation.

## 11. Method visibility và final methods

Với proxy-based AOP:
- Method private không thể được gọi qua proxy bên ngoài.
- Method final không thể override trong CGLIB subclass proxy.
- Final class không thể được CGLIB subclass.
- JDK dynamic proxy intercept method được expose qua interface.
- Invocation phải đi qua proxy bean do Spring quản lý.

Đặt annotation trên public service methods thường dễ hiểu nhất. Nếu annotation không được áp dụng, kiểm tra class có phải Spring bean, bean có được inject qua proxy và method có được gọi qua proxy hay không.

AspectJ weaving thật có join-point coverage rộng hơn, nhưng phải cấu hình compiler/weaver riêng; starter đơn thuần không bật weaving toàn chương trình.

## 12. Async và reactive boundaries

Annotation method observation đo invocation theo cơ chế interceptor. Với method trả về CompletableFuture, Mono hoặc Flux, cần xác minh observation/span lifecycle có bao phủ asynchronous execution hay chỉ quanh việc tạo publisher/future, tùy annotation aspect và integration version.

Không mặc định thời gian method return là thời gian task hoàn tất. Với asynchronous work:
- Đo thời gian từ submit đến start riêng nếu cần queue wait.
- Đo từ start đến terminal completion/error/cancel cho processing duration.
- Propagate Observation/trace context qua executor/reactive context.
- Dùng integration native của framework khi có thay vì tự tạo aspect chồng lấn.

Reactive subscription thường là lúc execution bắt đầu; publisher có thể được subscribe nhiều lần. Instrumentation phải phản ánh từng subscription/operation theo semantics mong muốn.

## 13. Tránh duplicate observations

Spring Boot và Spring ecosystem đã tự instrument nhiều boundary như Spring MVC, RestTemplate, Spring Data và messaging integrations. Nếu thêm @Observed lên method đã tự động instrument, có thể tạo observations/spans lồng nhau hoặc metrics đếm trùng.

Tài liệu Spring Boot cảnh báo annotate method/class đã được instrument tự động có thể tạo duplicate observations. Có thể:
- Bỏ annotation trên method đã có instrumentation tự động.
- Tắt instrumentation tự động tương ứng bằng property nếu phù hợp.
- Dùng ObservationPredicate để lọc observation theo name/context.
- Chỉ annotate business boundary chưa được instrument.

Ví dụ predicate lọc một observation name:

~~~java
import io.micrometer.observation.ObservationPredicate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ObservationFilterConfiguration {

    @Bean
    ObservationPredicate ignoreDuplicateOperation() {
        return (name, context) -> !name.equals("duplicate.operation");
    }
}
~~~

Ví dụ chỉ minh họa predicate; đừng lọc theo chuỗi rộng làm mất observations hữu ích. Trước khi disable instrumentation, kiểm tra tác động tới metrics/traces và dashboards.

## 14. Kiểm thử annotation observability

Kiểm thử cần xác nhận proxy/aspect đã intercept method và signal được tạo. Không chỉ assert method trả đúng business result.

~~~java
@SpringBootTest
class ObservedServiceTest {

    @Autowired
    OrderApplicationService service;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void recordsObservedOperation() {
        service.submit(validCommand());

        Timer timer = meterRegistry.find("order.submit").timer();
        assertThat(timer).isNotNull();
        assertThat(timer.count()).isGreaterThan(0);
    }
}
~~~

Đây là test skeleton. Metric name và meter presence phụ thuộc convention/handler; test cần cấu hình Observation metrics handler và xác nhận annotation scanning đã bật. Nếu tên meter không như kỳ vọng, kiểm tra observation name và handler mapping.

### 14.1 Test self-invocation và duplicate instrumentation

Tạo test cho hai trường hợp: method được gọi từ bean khác qua proxy và method gọi method annotate bên trong cùng bean. Assert số observations hoặc Timer count để chứng minh khác biệt.

Nếu controller/repository đã có auto-observation, thêm annotation có thể làm count/span tăng gấp đôi. Kiểm tra số observations, span tree, meter count, instrumentation scope/name và ObservationPredicate sau điều chỉnh.

### 14.2 Test cardinality

Gọi method với nhiều customer IDs nhưng tag chỉ dùng channel đã allowlist. Xác nhận meter IDs không tăng theo customer ID và không có PII trong tags.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| @Observed không tạo observation | Chưa bật annotation scanning hoặc thiếu AspectJ weaver starter | Kiểm tra dependency và property |
| Boot 4 không resolve spring-boot-starter-aop | Starter đã đổi tên | Dùng spring-boot-starter-aspectj |
| Annotation compile nhưng không intercept | Bean không được Spring quản lý hoặc call bypass proxy | Inject bean proxy và kiểm tra invocation |
| Self-invocation không có timer | Internal call không qua proxy | Tách bean hoặc tạo Observation thủ công |
| Private/final method không intercept | Proxy limitations | Dùng public non-final method hoặc weaving được cấu hình riêng |
| Có observation nhưng không có metric | Meter handler/registry chưa cấu hình | Kiểm tra Actuator, ObservationRegistry và MeterRegistry |
| Có metric nhưng không có span | Tracing handler/bridge/exporter thiếu | Kiểm tra Micrometer Tracing pipeline |
| Có hai spans/timers cho một operation | Annotation chồng auto-instrumentation | Bỏ annotation hoặc filter một instrumentation path |
| @MeterTag tạo nhiều series | Parameter có cardinality cao | Normalize/allowlist tag values |
| @NewSpan không nối parent | Current trace context không propagate | Kiểm tra tracing bridge và context propagation |
| Async timer quá ngắn | Chỉ đo thời gian tạo Future/Publisher | Instrument terminal completion hoặc native async integration |
| Test không thấy meter | Test context thiếu handler/registry hoặc aspect | Kiểm tra dependency, property và proxy bean |

## 16. Playbook: @Observed không xuất hiện trong metrics

**Tình huống:** Method có @Observed nhưng /actuator/metrics không hiển thị timer.

1. Xác định Spring Boot major version.
2. Kiểm tra dependency: Boot 3.x dùng spring-boot-starter-aop; Boot 4.x dùng spring-boot-starter-aspectj.
3. Kiểm tra aspectjweaver có trong runtime classpath.
4. Xác nhận management.observations.annotations.enabled=true.
5. Xác nhận class là Spring bean và caller nhận bean qua Spring container.
6. Kiểm tra method có self-invocation, private/final hoặc proxy limitation không.
7. Kiểm tra ObservationRegistry và MeterObservationHandler.
8. Kiểm tra tên meter thực tế và convention.
9. Kiểm tra ObservationPredicate hoặc property có loại observation đó không.
10. Kiểm tra method có auto-instrumentation khác gây duplicate/filtering không.
11. Viết integration test gọi qua proxy và assert Observation/Timer được tạo.

Không chỉ thêm dependency liên tục. Xác định thiếu ở scanning, proxy interception, Observation handler hay export registry.

## 17. Bài tập tự kiểm tra

**Bài 1 — Dependency.** Dự án Boot 3.5 cần annotation observability. Starter nào cần dùng? Khi nâng lên Boot 4, dependency đổi ra sao?

**Bài 2 — Property.** Vì sao chỉ thêm AspectJ starter chưa đủ để Micrometer quét @Observed và @Timed?

**Bài 3 — Proxy vs weaving.** Spring AOP proxy khác AspectJ compile-time weaving như thế nào? Có weaver library trên classpath có đồng nghĩa code đã được woven không?

**Bài 4 — Self-invocation.** Một method public có @Observed được gọi từ method khác trong cùng bean. Vì sao observation có thể không xuất hiện? Đưa ra hai cách khắc phục.

**Bài 5 — Duplicate.** Spring Data repository đã tự instrument nhưng developer thêm @Observed lên repository method. Rủi ro là gì?

**Bài 6 — @MeterTag.** Vì sao không nên annotate parameter customerId làm meter tag? Hãy chọn dimension bounded thay thế.

**Bài 7 — Async.** Method trả CompletableFuture ngay sau khi submit task. Vì sao Timer có thể không phản ánh thời gian task thực thi?

**Bài 8 — Signal pipeline.** @Observed đã tạo Observation nhưng không có span. Những thành phần nào cần kiểm tra?

### Gợi ý trả lời

1. Boot 3.5 dùng spring-boot-starter-aop; Boot 4 dùng spring-boot-starter-aspectj.
2. Annotation scanning cần bật management.observations.annotations.enabled=true; runtime còn cần registry/handlers phù hợp.
3. Proxy intercept call qua Spring bean proxy; compile-time weaving sửa bytecode lúc build. Có weaver library không chứng minh đã bật weaving.
4. Call nội bộ không qua proxy. Tách method sang bean khác hoặc tạo Observation thủ công.
5. Có thể tạo duplicate observations/spans/timers và làm count/latency sai.
6. Customer ID tạo series theo từng khách hàng và có thể là dữ liệu cá nhân; dùng channel/region/operation type đã allowlist.
7. Method timer có thể dừng khi Future được trả về, trước khi task hoàn tất. Đo terminal completion hoặc dùng async-aware instrumentation.
8. Kiểm tra tracing observation handler, Micrometer Tracing bridge, tracer và exporter.

## 18. Tài liệu tham khảo chính thức

- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): annotation scanning property, starter AspectJ requirement và duplicate observations.
- [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html): starter AOP và annotation support cho Boot 3.x.
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): AOP auto-configuration và proxy behavior.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): starter-aop đổi tên thành starter-aspectj.
- [Micrometer Observation Annotations](https://docs.micrometer.io/micrometer/reference/observation/annotations.html): @Observed, annotation aspects và Observation behavior.
- [Micrometer Core Annotations](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): @Timed, @Counted và meter annotation support.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): @NewSpan, span lifecycle và context propagation.
- [Spring Framework — AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): self-invocation, proxy types và method limitations.
- [Spring Framework — AspectJ Integration](https://docs.spring.io/spring-framework/reference/core/aop/using-aspectj.html): @AspectJ syntax, Spring AOP và weaving distinctions.

**Ghi nhớ:** Annotation observability cần dependency/aspect support, annotation scanning và ObservationRegistry handlers. Boot 3.x dùng spring-boot-starter-aop; Boot 4 dùng spring-boot-starter-aspectj. Spring AOP proxy chỉ intercept invocation đi qua proxy, nên self-invocation và final/private methods có giới hạn. @Observed tạo Observation; metrics/traces phụ thuộc handlers và exporter. Tránh annotate trùng boundary đã được Spring tự instrument, giữ tags có cardinality thấp và kiểm thử method invocation qua proxy.


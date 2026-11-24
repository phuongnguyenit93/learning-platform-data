# Kiểm thử aspect qua đối tượng được proxy và các trường hợp gọi bị bỏ qua

Các annotation như `@Timed` và `@Observed` giúp thêm instrumentation mà không phải viết mã đo thời gian hoặc tạo Observation trong từng phương thức. Nhưng annotation chỉ có tác dụng khi lời gọi đi qua aspect đã được cấu hình. Trong Spring AOP, điều này thường có nghĩa caller phải gọi bean proxy do Spring tạo, thay vì gọi trực tiếp target object.

Vì vậy, một bài kiểm thử aspect cần xác minh cả hai phía: khi gọi qua proxy, Timer hoặc Observation được tạo đúng; khi một lời gọi bị bỏ qua, cần xác định rõ đó là do chính sách skip, do ObservationPredicate, hay do đường gọi không đi qua proxy. Ba trường hợp này có biểu hiện giống nhau ở dashboard — không thấy metric — nhưng nguyên nhân và cách sửa khác nhau.

## 1. Aspect và proxy tham gia vào lời gọi như thế nào?

Với Spring AOP proxy, luồng gọi thông thường là:

~~~mermaid
sequenceDiagram
    participant Test as Test hoặc caller
    participant Proxy as Spring AOP proxy
    participant Aspect as Micrometer aspect
    participant Target as Service target
    participant Registry as Meter/Observation registry
    Test->>Proxy: gọi phương thức được đánh dấu
    Proxy->>Aspect: áp dụng advice phù hợp
    Aspect->>Target: thực thi phương thức
    Target-->>Aspect: trả kết quả hoặc ném lỗi
    Aspect->>Registry: ghi Timer/Observation
    Aspect-->>Proxy: trả kết quả hoặc ném lỗi
    Proxy-->>Test: kết quả
~~~

Với Spring AOP proxy, aspect chỉ có cơ hội chạy khi lời gọi đi qua proxy. Nếu test gọi `new CheckoutService().confirm()`, không có proxy nào đứng giữa caller và target. Nếu một phương thức trong target gọi `this.confirm()` thì lời gọi nội bộ cũng đi thẳng vào target và bỏ qua proxy. Nếu ứng dụng dùng AspectJ compile-time hoặc load-time weaving, advice được áp dụng theo bytecode và các quy tắc self-invocation của proxy không còn giống như vậy.

Micrometer có các aspect phổ biến:

| Annotation | Aspect | Kết quả quan sát |
| --- | --- | --- |
| `@Timed` | `TimedAspect` | Ghi Timer cho thời gian thực thi phương thức. |
| `@Observed` | `ObservedAspect` | Tạo Observation; handler có thể chuyển nó thành metrics, trace hoặc hành vi khác. |
| `@Counted` | `CountedAspect` | Ghi Counter cho số lần phương thức được gọi. |

Bài này dùng `@Timed` và `@Observed` để minh họa. Nguyên tắc proxy và cách kiểm tra đường gọi cũng áp dụng cho các aspect annotation khác.

## 2. Chuẩn bị dependency kiểm thử

Với Maven, các dependency cần thiết thường gồm Micrometer core, Observation, Spring AOP, AspectJ Weaver và thư viện test Observation:

~~~xml
<dependencies>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-core</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-observation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-aop</artifactId>
    </dependency>
    <dependency>
        <groupId>org.aspectj</groupId>
        <artifactId>aspectjweaver</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-observation-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.assertj</groupId>
        <artifactId>assertj-core</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Hãy để Spring Boot hoặc Micrometer BOM quản lý version tương thích thay vì khai báo từng version rời rạc. Nếu dự án đã dùng `spring-boot-starter-aop` hoặc starter AspectJ tương ứng của phiên bản Spring Boot, dependency AOP có thể đã được kéo vào.

Với Gradle, sau khi đã cấu hình BOM:

~~~kotlin
dependencies {
    implementation("io.micrometer:micrometer-core")
    implementation("io.micrometer:micrometer-observation")
    implementation("org.springframework:spring-aop")
    implementation("org.aspectj:aspectjweaver")

    testImplementation("io.micrometer:micrometer-observation-test")
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.assertj:assertj-core")
}
~~~

Không phải mọi test đều cần Spring Boot context. `AspectJProxyFactory` có thể dựng proxy trực tiếp để kiểm thử aspect trong một test nhỏ; Spring context test sẽ được dùng khi cần xác minh auto-configuration hoặc bean wiring của ứng dụng.

Nếu dùng phần integration test `@SpringBootTest` ở dưới, thêm `spring-boot-starter-test` trong test scope để có Spring Test, JUnit và AssertJ theo bộ version của Spring Boot.

## 3. Kiểm thử `@Timed` bằng `AspectJProxyFactory`

`TimedAspect` nằm trong `micrometer-core`. Khi dùng Spring AOP, đăng ký aspect với `MeterRegistry` và gọi phương thức thông qua proxy.

Service mẫu:

~~~java
import io.micrometer.core.annotation.Timed;

public class CheckoutService {

    @Timed(value = "checkout.confirm")
    public String confirm() {
        return "confirmed";
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.aop.aspectj.annotation.AspectJProxyFactory;

class TimedAspectTest {

    @Test
    void recordsTimerWhenCallingTheProxiedService() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        AspectJProxyFactory proxyFactory =
                new AspectJProxyFactory(new CheckoutService());
        proxyFactory.addAspect(new TimedAspect(registry));

        CheckoutService service = proxyFactory.getProxy();

        assertThat(service.confirm()).isEqualTo("confirmed");

        Timer timer = registry.find("checkout.confirm").timer();
        assertThat(timer).isNotNull();
        assertThat(timer.count()).isEqualTo(1);
    }
}
~~~

Điểm quan trọng của test là biến `service` nhận từ `proxyFactory.getProxy()`. Nếu test gọi target object đã truyền vào `AspectJProxyFactory`, aspect sẽ không được kích hoạt.

`SimpleMeterRegistry` phù hợp cho test đơn vị vì không cần kết nối Prometheus hoặc backend bên ngoài. Test chỉ xác minh meter đã được đăng ký và count tăng đúng.

## 4. Kiểm tra phương thức thực thi dù aspect không tạo Timer

Không nên chỉ kiểm tra meter. Một aspect có thể được cấu hình bỏ qua Timer nhưng vẫn phải gọi phương thức gốc. Dùng `AtomicInteger` hoặc mock để xác minh logic nghiệp vụ vẫn chạy.

~~~java
import io.micrometer.core.annotation.Timed;
import java.util.concurrent.atomic.AtomicInteger;

public class HealthService {

    private final AtomicInteger calls = new AtomicInteger();

    @Timed(value = "health.check")
    public void check() {
        calls.incrementAndGet();
    }

    public int callCount() {
        return calls.get();
    }
}
~~~

Khi kiểm thử, gọi qua proxy rồi xác minh cả số lần chạy và Timer. Điều này giúp phân biệt “aspect bỏ qua việc ghi metric” với “phương thức không được thực thi”.

## 5. Kiểm thử skip predicate của `TimedAspect`

`TimedAspect` có constructor nhận `Predicate<ProceedingJoinPoint>`. Khi predicate trả về `true`, aspect bỏ qua việc tạo Timer và gọi tiếp phương thức gốc bằng `proceed()`.

Ví dụ bỏ qua phương thức health check vì hệ thống khác đã đo nó:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.aop.aspectj.annotation.AspectJProxyFactory;

class TimedAspectSkipTest {

    public static class HealthService {
        private final AtomicInteger calls = new AtomicInteger();

        @io.micrometer.core.annotation.Timed("health.check")
        public void check() {
            calls.incrementAndGet();
        }

        int calls() {
            return calls.get();
        }
    }

    @Test
    void skipPredicateSkipsTimerButStillExecutesMethod() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        HealthService target = new HealthService();

        TimedAspect aspect = new TimedAspect(
                registry,
                joinPoint -> joinPoint.getSignature()
                        .getName()
                        .equals("check"));

        AspectJProxyFactory proxyFactory = new AspectJProxyFactory(target);
        proxyFactory.addAspect(aspect);
        HealthService service = proxyFactory.getProxy();

        service.check();

        assertThat(target.calls()).isEqualTo(1);
        assertThat(registry.find("health.check").timer()).isNull();
    }
}
~~~

Predicate trong ví dụ dựa vào tên phương thức để dễ đọc. Trong ứng dụng thực tế, có thể kiểm tra target class, annotation hoặc signature để quyết định bỏ qua. Không đưa giá trị động từ request vào điều kiện skip nếu điều đó làm hành vi instrumentation khó dự đoán.

Skip predicate chỉ điều khiển `TimedAspect`. Nó không chặn lời gọi, không bỏ qua transaction và không thay đổi kết quả nghiệp vụ.

## 6. Kiểm thử `@Observed` qua proxy

Với `@Observed`, dùng `ObservedAspect` và `TestObservationRegistry`. Registry kiểm thử cho phép xác minh tên, contextual name, key-value, error và trạng thái start/stop.

`@Observed` có thể đặt trên method hoặc class. Khi đặt trên class, các method phù hợp trong class sẽ được quan sát; hãy kiểm tra số lượng Observation nếu class cũng có instrumentation ở cấp method hoặc được instrument tự động bởi framework.

Service:

~~~java
import io.micrometer.observation.annotation.Observed;

public class ObservedCheckoutService {

    @Observed(
            name = "checkout.confirm",
            contextualName = "checkout#confirm")
    public String confirm() {
        return "confirmed";
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.observation.aop.ObservedAspect;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.aop.aspectj.annotation.AspectJProxyFactory;

class ObservedAspectTest {

    @Test
    void createsObservationForProxiedMethodCall() {
        TestObservationRegistry registry = TestObservationRegistry.create();

        AspectJProxyFactory proxyFactory =
                new AspectJProxyFactory(new ObservedCheckoutService());
        proxyFactory.addAspect(new ObservedAspect(registry));

        ObservedCheckoutService service = proxyFactory.getProxy();

        assertThat(service.confirm()).isEqualTo("confirmed");

        assertThat(registry)
                .doesNotHaveAnyRemainingCurrentObservation()
                .hasSingleObservationThat()
                .hasBeenStarted()
                .hasBeenStopped()
                .hasNameEqualTo("checkout.confirm")
                .hasContextualNameEqualTo("checkout#confirm")
                .doesNotHaveError();
    }
}
~~~

`TestObservationRegistry` thuộc artifact `micrometer-observation-test`. Nó tự đăng ký `ObservationValidator`, giúp phát hiện lifecycle không hợp lệ như stop trước start hoặc gọi stop nhiều lần.

Khác với `SimpleMeterRegistry`, `TestObservationRegistry` kiểm tra Observation ở mức lifecycle và context. Nếu muốn xác minh Timer thực tế được tạo, có thể đăng ký `DefaultMeterObservationHandler` với một `SimpleMeterRegistry` trong test riêng.

## 7. Kiểm thử trường hợp `ObservationPredicate` loại Observation

`ObservedAspect` tạo Observation qua `ObservationRegistry`. Registry có thể đăng ký `ObservationPredicate` để biến một Observation thành no-op theo tên hoặc context.

Khi predicate từ chối Observation, phương thức vẫn chạy; các handler không nhận lifecycle của Observation bị loại bỏ.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.aop.ObservedAspect;
import io.micrometer.observation.annotation.Observed;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.aop.aspectj.annotation.AspectJProxyFactory;

class ObservedAspectPredicateTest {

    public static class InternalService {
        private final AtomicInteger calls = new AtomicInteger();

        @Observed(name = "internal.refresh")
        public void refresh() {
            calls.incrementAndGet();
        }
    }

    @Test
    void rejectedObservationIsNoopButMethodStillRuns() {
        ObservationRegistry registry = ObservationRegistry.create();
        AtomicInteger starts = new AtomicInteger();

        registry.observationConfig()
                .observationPredicate((name, context) ->
                        !name.equals("internal.refresh"))
                .observationHandler(new ObservationHandler<Observation.Context>() {
                    @Override
                    public boolean supportsContext(Observation.Context context) {
                        return true;
                    }

                    @Override
                    public void onStart(Observation.Context context) {
                        starts.incrementAndGet();
                    }
                });

        InternalService target = new InternalService();
        AspectJProxyFactory proxyFactory = new AspectJProxyFactory(target);
        proxyFactory.addAspect(new ObservedAspect(registry));
        InternalService service = proxyFactory.getProxy();

        service.refresh();

        assertThat(target.calls.get()).isEqualTo(1);
        assertThat(starts).hasValue(0);
    }
}
~~~

Đây là một kiểu bỏ qua có chủ đích ở tầng Observation. Khác với `TimedAspect` skip predicate, `ObservationPredicate` quyết định Observation có được tạo thành no-op hay không; nó không phải bộ lọc trực tiếp của `ObservedAspect`.

## 8. Phân biệt ba trường hợp không thấy metric

Khi test không thấy Timer hoặc Observation, trước tiên hãy xác định lời gọi có đi qua aspect không:

| Trường hợp | Aspect có được gọi? | Phương thức nghiệp vụ chạy? | Kết quả quan sát |
| --- | --- | --- | --- |
| Gọi qua proxy, không bị skip | Có | Có | Timer/Observation được tạo. |
| `TimedAspect` skip predicate trả true | Có | Có | Không tạo Timer từ aspect đó. |
| `ObservationPredicate` trả false | Aspect tạo yêu cầu Observation | Có | Observation trở thành no-op, handler không nhận lifecycle. |
| Gọi trực tiếp target bằng `new` | Không | Có | Không có Timer/Observation từ aspect. |
| Self-invocation qua `this` | Không cho lời gọi nội bộ | Có | Lời gọi nội bộ không được aspect đo. |
| Method không thể proxy/advice | Không | Có nếu được gọi hợp lệ | Không có instrumentation từ proxy đó. |

Đừng dùng skip predicate để che lỗi proxy. Nếu một phương thức không đi qua proxy, predicate thậm chí không được gọi.

## 9. Kiểm thử self-invocation

Ví dụ một phương thức công khai gọi phương thức được đánh dấu trên cùng object:

~~~java
import io.micrometer.core.annotation.Timed;

public class BillingService {

    public void process() {
        calculateFee();
    }

    @Timed("billing.calculate.fee")
    public int calculateFee() {
        return 100;
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.aop.aspectj.annotation.AspectJProxyFactory;

class SelfInvocationTest {

    @Test
    void internalThisCallDoesNotPassThroughProxy() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        AspectJProxyFactory factory =
                new AspectJProxyFactory(new BillingService());
        factory.addAspect(new TimedAspect(registry));

        BillingService service = factory.getProxy();

        service.process();
        assertThat(registry.find("billing.calculate.fee").timer()).isNull();

        service.calculateFee();
        assertThat(registry.find("billing.calculate.fee").timer().count())
                .isEqualTo(1);
    }
}
~~~

Lời gọi `service.process()` đi qua proxy, nhưng `process()` không được đánh dấu `@Timed`. Khi target gọi `calculateFee()` bằng `this`, lời gọi đó không quay lại proxy. Lời gọi trực tiếp `service.calculateFee()` từ test mới đi qua proxy và tạo Timer.

Cách xử lý thường tốt nhất là chuyển thao tác được instrument sang một bean riêng rồi inject bean đó. Self-injection cũng có thể gọi lại proxy, nhưng làm class phụ thuộc vào cơ chế proxy. `AopContext.currentProxy()` là lựa chọn cuối cùng vì nó gắn mã nghiệp vụ trực tiếp với Spring AOP.

## 10. Kiểm thử target không được proxy

Một test nhỏ giúp nhận diện lỗi thường gặp:

~~~java
@Test
void directTargetCallDoesNotCreateTimer() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    CheckoutService target = new CheckoutService();
    AspectJProxyFactory factory = new AspectJProxyFactory(target);
    factory.addAspect(new TimedAspect(registry));
    CheckoutService proxy = factory.getProxy();

    // Calling the target bypasses the aspect.
    target.confirm();
    assertThat(registry.find("checkout.confirm").timer()).isNull();

    // Calling the proxy invokes the aspect.
    proxy.confirm();
    assertThat(registry.find("checkout.confirm").timer().count()).isEqualTo(1);
}
~~~

Trong test này, `registry` đã được gắn với aspect qua proxy factory, nhưng lời gọi `target.confirm()` đi thẳng vào target nên không đi qua proxy. Lời gọi `proxy.confirm()` mới kích hoạt aspect. So sánh hai lời gọi giúp xác minh annotation không tự tạo meter nếu không có cơ chế proxy hoặc weaving.

Không khởi tạo Spring bean có annotation bằng `new` trong test tích hợp nếu mục tiêu là kiểm tra auto-proxy. Hãy lấy bean từ `ApplicationContext`.

## 11. Các method và class không được proxy theo cách mong đợi

Spring AOP dùng JDK dynamic proxy hoặc CGLIB:

| Kiểu proxy | Đặc điểm | Hạn chế cần test |
| --- | --- | --- |
| JDK dynamic proxy | Proxy các interface mà target triển khai. | Caller phải dùng interface; method không có trên interface không được gọi qua proxy JDK. |
| CGLIB class proxy | Tạo subclass của target class. | Không proxy được final class; không advice được final hoặc private method vì không thể override. |

Để giảm khác biệt giữa test và production, ưu tiên public method trên Spring bean, và xác minh proxy type trong context test nếu cấu hình proxy là một phần của yêu cầu.

Ví dụ không nên kỳ vọng `private` hoặc `final` method được CGLIB proxy advice:

~~~java
public class OrderService {

    @Timed("orders.public")
    public void confirm() {
        // A public method can be advised through the proxy.
    }

    @Timed("orders.private")
    private void validateInternally() {
        // A proxy cannot override this private method.
    }

    @Timed("orders.final")
    public final void finalizeOrder() {
        // A CGLIB subclass cannot override this final method.
    }
}
~~~

Nếu dùng JDK proxy, test thông qua interface và method khai báo trên interface. Nếu dùng CGLIB, class và method cần có khả năng được subclass override. AspectJ compile-time hoặc load-time weaving có semantics khác Spring proxy và không có cùng hạn chế self-invocation; đừng trộn hai cơ chế khi phân tích kết quả test.

## 12. Kiểm thử ngoại lệ vẫn được đo

`TimedAspect` ghi thời gian khi phương thức kết thúc bình thường hoặc ném exception. Test nên xác minh exception vẫn được truyền về caller và Timer vẫn tăng count:

~~~java
import io.micrometer.core.annotation.Timed;

public class FailingService {

    @Timed("checkout.failure")
    public void fail() {
        throw new IllegalStateException("payment unavailable");
    }
}
~~~

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.aop.aspectj.annotation.AspectJProxyFactory;

class TimedAspectExceptionTest {

    @Test
    void recordsTimerAndPropagatesException() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        AspectJProxyFactory factory =
                new AspectJProxyFactory(new FailingService());
        factory.addAspect(new TimedAspect(registry));

        FailingService service = factory.getProxy();

        assertThatThrownBy(service::fail)
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("payment unavailable");

        assertThat(registry.find("checkout.failure").timer().count())
                .isEqualTo(1);
    }
}
~~~

Với `@Observed`, `TestObservationRegistry` có thể xác minh Observation kết thúc với error. Hãy test lỗi kỹ thuật riêng với outcome nghiệp vụ bình thường; một kết quả declined hoặc rejected không nhất thiết phải được biểu diễn như exception.

## 13. Kiểm thử phương thức bất đồng bộ

Micrometer `TimedAspect` hỗ trợ `CompletableFuture`: Timer được dừng khi future hoàn tất, không chỉ khi phương thức trả về future. Vì thế, test cần đợi future hoàn tất trước khi kiểm tra count.

~~~java
import io.micrometer.core.annotation.Timed;
import java.util.concurrent.CompletableFuture;

public class AsyncCheckoutService {

    @Timed("checkout.async")
    public CompletableFuture<String> confirmAsync() {
        return CompletableFuture.supplyAsync(() -> "confirmed");
    }
}
~~~

Test:

~~~java
@Test
void recordsAsyncTimerWhenFutureCompletes() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    AspectJProxyFactory factory =
            new AspectJProxyFactory(new AsyncCheckoutService());
    factory.addAspect(new TimedAspect(registry));
    AsyncCheckoutService service = factory.getProxy();

    assertThat(service.confirmAsync().join()).isEqualTo("confirmed");

    assertThat(registry.find("checkout.async").timer().count())
            .isEqualTo(1);
}
~~~

Trong ứng dụng dùng `@Async`, thứ tự advisor và executor của Spring có thể ảnh hưởng đến thời điểm quan sát. Hãy viết integration test với cấu hình async thực tế nếu thời lượng cần đo bao gồm cả thời gian chờ xử lý nền. Không dùng `Thread.sleep()` để chờ; chờ `CompletableFuture`, latch hoặc điều kiện hoàn tất rõ ràng.

## 14. Kiểm thử aspect được Spring Boot cấu hình

Test bằng `AspectJProxyFactory` xác minh aspect hoạt động độc lập. Nếu cần xác minh ứng dụng thật đã bật annotation scanning, hãy lấy bean từ Spring context.

Với Spring Boot có hỗ trợ annotation observability, cần bật:

~~~yaml
management:
  observations:
    annotations:
      enabled: true
~~~

Và bảo đảm `aspectjweaver` có mặt trên classpath. Tên starter AOP có thể thay đổi theo dòng Spring Boot; hãy dùng dependency management của phiên bản dự án.

Một integration test có thể dùng `@SpringBootTest` để lấy bean:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;

@SpringBootTest(properties =
        "management.observations.annotations.enabled=true")
@Import(CheckoutObservationIntegrationTest.ObservationTestConfig.class)
class CheckoutObservationIntegrationTest {

    @TestConfiguration
    static class ObservationTestConfig {

        @Bean
        @Primary
        TestObservationRegistry testObservationRegistry() {
            return TestObservationRegistry.create();
        }
    }

    @Autowired
    CheckoutFacade checkoutFacade;

    @Autowired
    TestObservationRegistry observationRegistry;

    @Test
    void springManagedBeanIsObserved() {
        assertThat(AopUtils.isAopProxy(checkoutFacade)).isTrue();
        checkoutFacade.confirm();

        assertThat(observationRegistry)
                .hasObservationWithNameEqualTo("checkout.confirm")
                .that()
                .hasBeenStarted()
                .hasBeenStopped();
    }
}
~~~

Ví dụ giả định `CheckoutFacade` là Spring bean có method `@Observed`. Bean `TestObservationRegistry` được khai báo `@Primary` để các thành phần annotation dùng registry kiểm thử. Nếu cấu hình ứng dụng tự tạo `ObservationRegistry` hoặc `ObservedAspect`, hãy bảo đảm chúng cùng nhận registry này. Spring Boot không tự tạo `TestObservationRegistry` trong ứng dụng thông thường.

Nếu chỉ cần kiểm tra auto-proxy, có thể inject `ApplicationContext` và lấy bean từ context, rồi xác minh bean là AOP proxy bằng `AopUtils.isAopProxy(bean)`. Sau đó gọi bean và kiểm tra registry.

## 15. Tránh đo trùng với instrumentation tự động

Spring Boot và các starter có thể đã instrument HTTP server, Spring MVC controller, Spring Data repository hoặc các client. Nếu thêm `@Timed` hoặc `@Observed` vào một method đã được instrument tự động, có thể tạo hai observation cho cùng một thao tác.

Có ba cách xử lý:

- Bỏ annotation thủ công nếu instrumentation tự động đã trả lời đủ câu hỏi.
- Tắt instrumentation tự động ở phạm vi phù hợp và giữ annotation.
- Dùng skip predicate của `TimedAspect` để aspect không tạo Timer cho các join point đã được component khác đo.

Spring Boot cũng hỗ trợ `ObservationPredicate` để loại các Observation theo tên/context. Khi kiểm thử, hãy xác minh đúng số lượng observation hoặc Timer; chỉ xác minh “có ít nhất một” có thể bỏ sót việc đo trùng.

Không dùng skip predicate để loại một controller rồi kỳ vọng Spring MVC instrumentation cũng bị tắt. Predicate của `TimedAspect` chỉ điều khiển aspect đó; component tự động khác có chính sách riêng.

## 16. Kiểm thử `TimedAspect` với skip controller

Một use case thực tế là bỏ qua controller nếu Spring MVC đã ghi nhận request duration:

~~~java
import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RestController;

@Bean
TimedAspect timedAspect(MeterRegistry registry) {
    return new TimedAspect(registry, joinPoint -> {
        Class<?> targetClass = joinPoint.getTarget().getClass();
        return targetClass.isAnnotationPresent(RestController.class)
                || targetClass.isAnnotationPresent(Controller.class);
    });
}
~~~

Trong test, tạo một target có `@RestController` và method `@Timed`, gọi qua proxy rồi xác minh:

1. Method vẫn thực thi.
2. Timer từ `TimedAspect` không được tạo.
3. Nếu test có cấu hình Spring MVC instrumentation, metric HTTP tương ứng vẫn được tạo bởi thành phần đó.

Đây là test cho chính sách phối hợp instrumentation, không chỉ là test aspect đơn lẻ. Không dùng `SimpleMeterRegistry` để kết luận MVC auto-instrumentation đã chạy nếu test không khởi tạo các thành phần web cần thiết.

## 17. `@Timed` không tự nhận mọi meta-annotation

`TimedAspect` không hỗ trợ meta-annotation trên `@Timed`. Nếu tạo annotation riêng rồi gắn `@Timed` lên annotation đó, không giả định aspect sẽ tìm thấy annotation gốc.

~~~java
@Timed("checkout.operation")
public @interface CheckoutTimed {
}
~~~

~~~java
@CheckoutTimed
public void confirm() {
    // Do not assume TimedAspect will intercept this as @Timed.
}
~~~

Nếu muốn dùng annotation composed, cần một aspect riêng hoặc cơ chế instrumentation được thiết kế để nhận diện annotation đó. Hãy viết test xác minh pointcut thực sự khớp trước khi áp dụng rộng.

## 18. Kiểm tra proxy và registry trong test

Khi một test không thấy meter, kiểm tra lần lượt:

1. **Đúng object:** biến đang gọi có phải proxy không?
2. **Đúng registry:** aspect có nhận cùng `MeterRegistry` mà test đang kiểm tra không?
3. **Đúng annotation:** annotation nằm trên method/class mà pointcut hỗ trợ không?
4. **Đúng method:** method có thể được proxy/advice theo loại proxy đang dùng không?
5. **Đúng đường gọi:** lời gọi có đi qua proxy hay là self-invocation?
6. **Có skip không:** skip predicate hoặc ObservationPredicate có loại nó không?
7. **Có đo trùng không:** instrumentation tự động có tạo một meter khác tên không?
8. **Đã hoàn tất chưa:** với future, đã chờ future hoàn tất trước khi assert chưa?

Một kiểm tra nhanh trong test:

~~~java
import org.springframework.aop.support.AopUtils;

assertThat(AopUtils.isAopProxy(service)).isTrue();
~~~

Nếu dùng `AspectJProxyFactory`, biến trả về từ `getProxy()` phải được dùng làm subject của test. Nếu dùng Spring context, lấy bean bằng `getBean()` hoặc inject bean, không tự khởi tạo target bằng `new`.

## 19. Ma trận test tối thiểu

| Trường hợp | Kỳ vọng về lời gọi | Kỳ vọng về instrumentation |
| --- | --- | --- |
| Public method gọi qua proxy | Method chạy một lần. | Một Timer/Observation được tạo. |
| Method ném exception qua proxy | Exception được truyền về caller. | Timer vẫn được ghi; Observation có error. |
| `TimedAspect` skip predicate trả true | Method vẫn chạy. | Không có Timer từ TimedAspect. |
| ObservationPredicate trả false | Method vẫn chạy. | Observation no-op, handler không nhận lifecycle. |
| Gọi target trực tiếp | Method chạy. | Aspect không chạy. |
| Self-invocation | Method nội bộ chạy. | Lời gọi nội bộ bỏ qua proxy. |
| Private/final method với proxy class | Tùy khả năng gọi của Java. | Không được CGLIB advice. |
| Async future | Future hoàn tất. | Timer dừng sau khi future hoàn tất. |
| Có instrumentation tự động khác | Request/repository vẫn chạy. | Xác minh không tạo observation trùng ngoài ý muốn. |
| Meta-annotation chứa `@Timed` | Method chạy. | TimedAspect không hỗ trợ meta-annotation. |

## 20. Những lỗi thường gặp

| Lỗi | Triệu chứng | Cách xử lý |
| --- | --- | --- |
| Gọi target thay vì proxy | Method chạy nhưng không có Timer. | Gọi bean do Spring quản lý hoặc proxy từ `AspectJProxyFactory`. |
| Tự gọi bằng `this` | Lời gọi bên ngoài qua proxy có thể được advice, lời gọi nội bộ thì không. | Tách method sang bean khác hoặc gọi qua self proxy có chủ đích. |
| Không đăng ký aspect | Annotation có mặt nhưng không có meter. | Đăng ký `TimedAspect`/`ObservedAspect` hoặc bật annotation support của framework. |
| Thiếu AspectJ Weaver | Aspect không được proxy/weave theo cấu hình. | Thêm dependency AOP phù hợp. |
| Skip predicate trả true | Không có Timer dù method chạy. | Kiểm tra điều kiện skip và test riêng predicate. |
| ObservationPredicate trả false | Không có Observation handler callback. | Kiểm tra predicate và tên/context Observation. |
| Private/final method | Proxy không advice được method. | Đưa instrumentation lên public method có thể proxy. |
| Đo trùng controller hoặc repository | Count hoặc thời lượng tăng bất thường. | Chọn một cơ chế instrumentation hoặc cấu hình skip. |
| Assert ngay sau khi trả future | Timer chưa được ghi. | Chờ future hoàn tất rồi assert. |
| Test chỉ kiểm tra meter tồn tại | Bỏ sót count sai hoặc gọi target không đúng. | Kiểm tra proxy, count, method invocation và lifecycle. |
| Test dùng registry khác aspect | Registry kiểm tra luôn rỗng. | Inject cùng một registry vào aspect và test. |

## 21. Checklist trước khi hoàn tất test aspect

- [ ] Đã xác minh đối tượng được gọi là proxy.
- [ ] Đã kiểm thử ít nhất một method thành công qua proxy.
- [ ] Đã kiểm tra Timer count hoặc Observation lifecycle.
- [ ] Đã kiểm tra phương thức nghiệp vụ thực thi đúng số lần.
- [ ] Đã kiểm thử exception và kết quả quan sát tương ứng.
- [ ] Đã kiểm thử skip predicate của `TimedAspect` nếu có dùng.
- [ ] Đã kiểm thử `ObservationPredicate` nếu có loại Observation.
- [ ] Đã phân biệt skip có chủ đích với self-invocation hoặc direct target call.
- [ ] Đã xem xét giới hạn JDK/CGLIB proxy đối với method và class.
- [ ] Đã kiểm thử async bằng cách chờ future hoàn tất.
- [ ] Đã kiểm tra instrumentation tự động để tránh đo trùng.
- [ ] Đã dùng `TestObservationRegistry` cho test Observation và `SimpleMeterRegistry` cho test meter.
- [ ] Đã dùng registry đúng với registry được inject vào aspect.

Kiểm thử aspect không chỉ là xác minh annotation có mặt. Test phải gọi đúng đối tượng proxy, xác minh phương thức thực thi, kiểm tra Timer hoặc Observation được ghi nhận, và chủ động bao phủ các trường hợp skip. Khi không có dữ liệu, hãy xác định aspect bị skip theo chính sách hay lời gọi đã đi vòng qua proxy; đó là hai lỗi khác nhau và cần hai kiểu kiểm thử khác nhau.

## Tài liệu tham khảo

- [Micrometer Timers - `@Timed` and `TimedAspect`](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer Observation Components - `@Observed` aspect testing](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Observation Testing - `TestObservationRegistry`](https://docs.micrometer.io/micrometer/reference/observation/testing.html)
- [TimedAspect Javadoc - skip predicate](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/aop/TimedAspect.html)
- [Spring Framework - AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Boot - Observability annotations and duplicate observations](https://docs.spring.io/spring-boot/reference/actuator/observability.html)

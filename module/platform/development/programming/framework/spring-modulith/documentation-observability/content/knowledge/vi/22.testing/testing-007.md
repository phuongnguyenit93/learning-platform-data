# Kiểm thử observation predicate

Trong ứng dụng Spring Boot, một observation có thể tạo ra metrics và traces thông qua Micrometer. Spring Modulith bổ sung module entry observations để ghi nhận tương tác khi một module gọi bean API của module khác hoặc khi một event listener được gọi. Khi hệ thống có nhiều loại operation, ta thường cần loại bỏ một số observation khỏi pipeline: ví dụ health check nội bộ, một nhóm operation quá ồn hoặc một module không cần tracing ở môi trường nhất định.

**ObservationPredicate** là điểm quyết định observation có được tạo thành observation thực hay trở thành **no-op observation**. Vì predicate ảnh hưởng tới những gì metrics và tracing handlers nhận được, cần kiểm thử cả điều kiện cho phép/từ chối lẫn cách predicate được đăng ký vào **ObservationRegistry**.

Bài thuộc chương **Kiểm thử** của mô-đun **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Mô-đun hướng dẫn dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong Spring Boot qua module graph, Actuator, event metrics, tracing và context propagation. Bài này tập trung vào cách kiểm thử ObservationPredicate với Micrometer, Spring Boot và ModulithContext.

> Ví dụ sử dụng Spring Boot 4.2, Spring Modulith 2.2 và Micrometer tương thích do BOM của Spring Boot quản lý. Nếu dự án dùng Spring Boot 3.x, tên một số test annotation và API auto-configuration khác; hãy theo tài liệu đúng phiên bản của dự án.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của `ObservationPredicate` trong vòng đời observation.
2. Phân biệt predicate, filter, convention và handler.
3. Hiểu ý nghĩa của observation thực và no-op observation.
4. Viết unit test cho predicate bằng `TestObservationRegistry`.
5. Xác minh observation bị từ chối không được ghi nhận, trong khi business logic vẫn chạy.
6. Kiểm thử nhiều predicate cùng hoạt động theo nguyên tắc AND.
7. Kiểm thử predicate dựa trên `ModulithContext` và module identifier.
8. Xác minh Spring Boot tự đăng ký bean `ObservationPredicate` vào `ObservationRegistry`.
9. Chọn giữa cấu hình property và predicate tùy theo độ phức tạp của điều kiện.
10. Chẩn đoán các test pass giả do dùng sai registry hoặc chỉ kiểm tra method `test()`.

## 2. ObservationPredicate hoạt động ở đâu?

Micrometer Observation dùng `ObservationRegistry` để tạo và quản lý observation. Khi code tạo một observation, registry đánh giá các predicate đã đăng ký. Nếu tất cả predicate trả về `true`, observation được tạo bình thường. Nếu bất kỳ predicate nào trả về `false`, Micrometer tạo một no-op observation.

~~~mermaid
flowchart TD
    A["Code yêu cầu tạo Observation"] --> B["ObservationRegistry"]
    B --> C{"Chạy các ObservationPredicate"}
    C -->|"Tất cả trả về true"| D["Observation thực"]
    C -->|"Có ít nhất một false"| E["No-op Observation"]
    D --> F["ObservationHandler"]
    F --> G["Metrics / Tracing / Handler khác"]
    E --> H["Không gửi lifecycle tới handlers"]
    D --> I["Business operation tiếp tục"]
    E --> I
~~~

Predicate quyết định **có ghi nhận observation hay không**. Nó không quyết định business operation có được thực thi hay không. Ví dụ, nếu một method được bọc trong `Observation.observe(...)` nhưng predicate từ chối observation, callback của method vẫn chạy; chỉ phần quan sát bị bỏ qua.

### 2.1. Chữ ký của predicate

Interface Micrometer:

~~~java
package io.micrometer.observation;

public interface ObservationPredicate {

    boolean test(String name, Observation.Context context);
}
~~~

Hai đầu vào có ý nghĩa:

- `name`: tên kỹ thuật của observation.
- `context`: context mang metadata của observation; có thể là `Observation.Context` cơ bản hoặc một subtype chuyên biệt.

Predicate nên trả lời một câu hỏi nhỏ, xác định và nhanh: observation này có nên được ghi nhận không?

### 2.2. Nhiều predicate có quan hệ AND

Một registry có thể đăng ký nhiều predicate. Observation chỉ được tạo nếu **tất cả** predicate đều cho phép.

| Predicate A | Predicate B | Kết quả |
| --- | --- | --- |
| `true` | `true` | Observation thực |
| `true` | `false` | No-op |
| `false` | `true` | No-op |
| `false` | `false` | No-op |

Micrometer duyệt danh sách predicate và dừng khi gặp predicate đầu tiên trả về `false`. Vì thế, không nên viết predicate có side effect hoặc phụ thuộc vào việc một predicate khác đã chạy.

## 3. Phân biệt Predicate, Filter, Convention và Handler

Các thành phần này đều tham gia Observation nhưng giải quyết những vấn đề khác nhau.

| Thành phần | Trách nhiệm | Thời điểm / tác động |
| --- | --- | --- |
| `ObservationPredicate` | Cho phép hoặc từ chối observation | Khi tạo observation; `false` tạo no-op |
| `ObservationFilter` | Thay đổi `Observation.Context` | Khi observation dừng, trước các handler `onStop` |
| `ObservationConvention` | Định nghĩa tên và key-values mặc định | Khi xây dựng observation theo convention |
| `ObservationHandler` | Ghi nhận lifecycle để tạo metrics, spans hoặc hành vi khác | Khi observation start/error/event/stop |

Ví dụ:

- Không muốn ghi nhận observation có tên bắt đầu bằng `internal.`: dùng predicate.
- Muốn bổ sung tag `region` vào observation: dùng filter hoặc convention tùy mục tiêu.
- Muốn đổi tên observation và định nghĩa low/high cardinality keys: dùng convention.
- Muốn tạo timer hoặc span: dùng handler.

**Không dùng `ObservationFilter` để thay thế predicate.** Filter thay đổi context của observation đã được tạo; predicate ngăn observation được ghi nhận ngay từ đầu.

## 4. Cấu hình predicate trong Spring Boot

Spring Boot tự động đăng ký các bean thuộc những kiểu sau vào `ObservationRegistry`:

- `ObservationPredicate`
- `GlobalObservationConvention`
- `ObservationFilter`
- `ObservationHandler`

Vì vậy, khi ứng dụng chạy bằng Spring Boot, ta thường khai báo predicate dưới dạng bean.

### 4.1. Predicate loại observation theo tên

Ví dụ không ghi nhận các observation có prefix `internal.`:

~~~java
package com.example.shop.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationPredicate;
import org.springframework.stereotype.Component;

@Component
class IgnoreInternalObservations implements ObservationPredicate {

    @Override
    public boolean test(String name, Observation.Context context) {
        return name == null || !name.startsWith("internal.");
    }
}
~~~

Điều kiện được viết null-safe để tránh lỗi khi tên observation không có giá trị. Với predicate này:

- `internal.health` bị từ chối.
- `internal.cache.lookup` bị từ chối.
- `orders.create` được cho phép.
- `payments.authorize` được cho phép.

### 4.2. Dùng property khi chỉ cần loại theo prefix

Spring Boot có property `management.observations.enable` để ngăn các observation theo prefix:

~~~yaml
management:
  observations:
    enable:
      denied:
        prefix: false
      another:
        denied:
          prefix: false
~~~

Cấu hình trên ngăn các observation có tên bắt đầu bằng `denied.prefix` hoặc `another.denied.prefix`.

Nếu chỉ cần bật/tắt theo prefix, property giúp cấu hình đơn giản. Nếu cần kiểm tra `Observation.Context`, module identifier hoặc điều kiện kết hợp, dùng bean `ObservationPredicate`.

### 4.3. Predicate không phải security policy

Không dùng predicate để thay thế authorization hoặc bảo vệ dữ liệu nhạy cảm. Predicate chỉ quyết định telemetry observation có được ghi nhận hay không. Nó không ngăn người dùng gọi API, không chặn method chạy và không xóa dữ liệu đã được log ở một pipeline khác.

## 5. Chuẩn bị test dependencies

Để kiểm thử observation mà không cần kết nối Prometheus, Zipkin hoặc backend tracing, dùng `TestObservationRegistry` từ `micrometer-observation-test`.

Ví dụ Gradle:

~~~gradle
dependencies {
    implementation 'org.springframework.modulith:spring-modulith-observability-api'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.micrometer:micrometer-observation-test'
}
~~~

Vai trò dependency:

- `spring-modulith-starter-insight`: bật Actuator và observability support của Spring Modulith ở runtime.
- `spring-modulith-observability-api`: cần ở compile scope nếu code predicate truy cập `ModulithContext` hoặc các API observability của Modulith.
- `spring-boot-starter-test`: JUnit Jupiter, AssertJ, Mockito và Spring Test.
- `micrometer-observation-test`: cung cấp `TestObservationRegistry` và các assertion cho observation.

Các version nên được quản lý bởi Spring Boot và Spring Modulith BOM tương thích. Không tự gán version Micrometer khác với version được BOM quản lý nếu chưa xác minh compatibility.

## 6. Unit test bằng TestObservationRegistry

`TestObservationRegistry` là registry dành cho test. Nó lưu các observation đã được tạo và đăng ký một validator để kiểm tra lifecycle, ví dụ không được gọi `stop()` trước `start()` hoặc gọi lifecycle sai thứ tự.

### 6.1. Viết predicate cần kiểm thử

~~~java
package com.example.shop.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationPredicate;

class IgnoreInternalObservations implements ObservationPredicate {

    @Override
    public boolean test(String name, Observation.Context context) {
        return name == null || !name.startsWith("internal.");
    }
}
~~~

### 6.2. Kiểm tra observation bị từ chối trở thành no-op

~~~java
package com.example.shop.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class IgnoreInternalObservationsTests {

    @Test
    void shouldCreateNoopObservationForInternalName() {
        TestObservationRegistry registry = TestObservationRegistry.create();
        registry.observationConfig()
                .observationPredicate(new IgnoreInternalObservations());

        Observation observation = Observation.start("internal.health", registry);

        assertThat(observation.isNoop()).isTrue();
    }
}
~~~

Assertion `isNoop()` xác nhận predicate đã tham gia vào quá trình tạo observation. Chỉ gọi `predicate.test(...)` rồi assert kết quả boolean là chưa đủ để chứng minh registry thực sự sử dụng predicate.

### 6.3. Kiểm tra observation hợp lệ vẫn được ghi nhận

~~~java
@Test
void shouldRecordObservationWhenNameIsAllowed() {
    TestObservationRegistry registry = TestObservationRegistry.create();
    registry.observationConfig()
            .observationPredicate(new IgnoreInternalObservations());

    Observation observation = Observation.start("orders.create", registry);

    assertThat(observation.isNoop()).isFalse();

    observation.stop();

    assertThat(registry)
            .hasObservationWithNameEqualTo("orders.create")
            .that()
            .hasBeenStarted()
            .hasBeenStopped();
}
~~~

Test này xác nhận cả hai phía của rule:

1. Observation được phép không trở thành no-op.
2. Lifecycle start/stop được `TestObservationRegistry` ghi lại.

### 6.4. Kiểm tra business logic vẫn chạy khi observation bị bỏ qua

Đây là test quan trọng để tránh hiểu sai semantics của predicate:

~~~java
@Test
void shouldStillExecuteBusinessCodeWhenObservationIsNoop() {
    TestObservationRegistry registry = TestObservationRegistry.create();
    registry.observationConfig()
            .observationPredicate(new IgnoreInternalObservations());

    AtomicBoolean businessCodeExecuted = new AtomicBoolean(false);

    Observation.createNotStarted("internal.health", registry)
            .observe(() -> businessCodeExecuted.set(true));

    assertThat(businessCodeExecuted).isTrue();
}
~~~

Predicate bỏ telemetry của `internal.health`; callback vẫn được thực thi. Nếu cần chặn một operation nghiệp vụ, hãy dùng validation, authorization hoặc business rule phù hợp.

## 7. Kiểm thử predicate dựa trên Observation.Context

Không phải lúc nào tên observation cũng đủ để quyết định. Một số operation có cùng tên nhưng context khác nhau. Ta có thể viết predicate dựa trên subtype hoặc dữ liệu trong context.

Ví dụ context nghiệp vụ riêng:

~~~java
class PaymentObservationContext extends Observation.Context {

    private final String paymentChannel;

    PaymentObservationContext(String paymentChannel) {
        this.paymentChannel = paymentChannel;
    }

    String getPaymentChannel() {
        return paymentChannel;
    }
}
~~~

Predicate loại observation cho kênh thử nghiệm:

~~~java
class IgnoreTestPaymentObservations implements ObservationPredicate {

    @Override
    public boolean test(String name, Observation.Context context) {
        if (!(context instanceof PaymentObservationContext paymentContext)) {
            return true;
        }

        return !"TEST".equals(paymentContext.getPaymentChannel());
    }
}
~~~

Test theo hai trường hợp:

~~~java
@Test
void shouldIgnoreTestPaymentChannel() {
    TestObservationRegistry registry = TestObservationRegistry.create();
    registry.observationConfig()
            .observationPredicate(new IgnoreTestPaymentObservations());

    PaymentObservationContext testContext =
            new PaymentObservationContext("TEST");

    Observation ignored = Observation.start(
            "payment.authorize", () -> testContext, registry);

    assertThat(ignored.isNoop()).isTrue();
}

@Test
void shouldKeepProductionPaymentChannel() {
    TestObservationRegistry registry = TestObservationRegistry.create();
    registry.observationConfig()
            .observationPredicate(new IgnoreTestPaymentObservations());

    PaymentObservationContext liveContext =
            new PaymentObservationContext("CARD");

    Observation recorded = Observation.start(
            "payment.authorize", () -> liveContext, registry);

    assertThat(recorded.isNoop()).isFalse();
    recorded.stop();
}
~~~

Dùng `Supplier<Observation.Context>` cho phép observation nhận context chuyên biệt khi được tạo. Predicate cần đọc context một cách an toàn và không giả định mọi observation đều có cùng subtype.

## 8. Kiểm thử predicate dành cho Spring Modulith

Spring Modulith sử dụng `ModulithContext`, một subtype của `Observation.Context`, để mang thông tin về module và method invocation. Observation liên quan đến việc đi vào module được định nghĩa bởi `ModulithObservations.MODULE_ENTRY`.

Module entry observation có thể chứa metadata như:

- `module.identifier`: technical identifier của module.
- `module.name`: tên hiển thị của module.
- `module.method`: method được gọi.
- `module.invocation-type`: kiểu invocation, chẳng hạn bean hoặc event listener.

Do đó, predicate có thể quyết định dựa trên module identifier.

### 8.1. Ví dụ predicate bỏ qua module inventory

~~~java
package com.example.shop.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationPredicate;
import org.springframework.modulith.core.ApplicationModuleIdentifier;
import org.springframework.modulith.observability.ModulithContext;

class IgnoreInventoryModuleObservations implements ObservationPredicate {

    private static final ApplicationModuleIdentifier IGNORED_MODULE =
            ApplicationModuleIdentifier.of("inventory");

    @Override
    public boolean test(String name, Observation.Context context) {
        if (!(context instanceof ModulithContext modulithContext)) {
            return true;
        }

        return !IGNORED_MODULE.equals(
                modulithContext.getModule().getIdentifier());
    }
}
~~~

Predicate này chỉ loại observation có `ModulithContext` thuộc module `inventory`. Các observation HTTP, database hoặc custom observation có context khác vẫn được cho phép.

Đây là một ví dụ để hiểu cách lọc theo module. Trước khi dùng trong production, hãy xác nhận lý do nghiệp vụ và tác động tới khả năng điều tra; loại module entry spans có thể làm trace không còn đầy đủ đường đi qua các module.

### 8.2. Test context của module bị loại

Dùng Mockito để tạo context và module giả lập:

~~~java
package com.example.shop.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModuleIdentifier;
import org.springframework.modulith.observability.ModulithContext;
import org.springframework.modulith.observability.ObservedModule;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class IgnoreInventoryModuleObservationsTests {

    @Test
    void shouldIgnoreInventoryModuleEntry() {
        TestObservationRegistry registry = TestObservationRegistry.create();
        registry.observationConfig()
                .observationPredicate(new IgnoreInventoryModuleObservations());

        ObservedModule module = mock(ObservedModule.class);
        when(module.getIdentifier())
                .thenReturn(ApplicationModuleIdentifier.of("inventory"));

        ModulithContext context = mock(ModulithContext.class);
        when(context.getModule()).thenReturn(module);

        Observation observation = Observation.start(
                "module.entry", () -> context, registry);

        assertThat(observation.isNoop()).isTrue();
    }
}
~~~

Test dùng mock để tập trung kiểm tra quyết định của predicate. Nó không kiểm tra Spring Modulith có thực sự tạo `ModulithContext` trong một lần gọi module hay không; việc đó thuộc phạm vi integration test.

### 8.3. Test module khác vẫn được ghi nhận

~~~java
@Test
void shouldKeepOrdersModuleEntry() {
    TestObservationRegistry registry = TestObservationRegistry.create();
    registry.observationConfig()
            .observationPredicate(new IgnoreInventoryModuleObservations());

    ObservedModule module = mock(ObservedModule.class);
    when(module.getIdentifier())
            .thenReturn(ApplicationModuleIdentifier.of("orders"));

    ModulithContext context = mock(ModulithContext.class);
    when(context.getModule()).thenReturn(module);

    Observation observation = Observation.start(
            "module.entry", () -> context, registry);

    assertThat(observation.isNoop()).isFalse();

    observation.stop();

    assertThat(registry)
            .hasObservationWithNameEqualTo("module.entry")
            .that()
            .hasBeenStarted()
            .hasBeenStopped();
}
~~~

Hai test nên kiểm tra cả module bị loại và module được giữ lại. Nếu chỉ test nhánh `false`, predicate có thể vô tình loại tất cả observation mà vẫn pass.

## 9. Kiểm thử Spring Boot tự đăng ký predicate bean

Unit test ở trên đăng ký predicate trực tiếp bằng:

~~~java
registry.observationConfig()
        .observationPredicate(predicate);
~~~

Trong ứng dụng Spring Boot, ta thường đăng ký predicate như bean. Spring Boot tự động tìm bean kiểu `ObservationPredicate` và thêm chúng vào `ObservationRegistry` được auto-configure.

Ví dụ cấu hình:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class ObservationPredicateTestConfiguration {

    @Bean
    ObservationPredicate ignoreInternalObservations() {
        return (name, context) -> name == null || !name.startsWith("internal.");
    }
}
~~~

Test kiểm tra wiring:

~~~java
@SpringBootTest
@Import(ObservationPredicateTestConfiguration.class)
class ObservationPredicateBeanRegistrationTests {

    @Autowired
    ObservationRegistry observationRegistry;

    @Test
    void shouldRegisterPredicateBeanInObservationRegistry() {
        Observation ignored =
                Observation.start("internal.health", observationRegistry);

        assertThat(ignored.isNoop()).isTrue();

        Observation accepted =
                Observation.start("orders.create", observationRegistry);

        assertThat(accepted.isNoop()).isFalse();
        accepted.stop();
    }
}
~~~

Test này kiểm tra nhiều thứ hơn việc gọi trực tiếp `test()`:

1. Spring tạo bean predicate.
2. Spring Boot tìm bean theo type.
3. Predicate được đăng ký vào `ObservationRegistry`.
4. Observation được tạo qua registry thực sự tuân theo predicate.

Nếu ứng dụng dùng nhiều `ObservationRegistry` tự tạo bằng `ObservationRegistry.create()`, bean predicate trong Spring context không tự động được đăng ký vào mọi registry đó. Registry tùy chỉnh phải được cấu hình riêng.

### 9.1. Test slice trong Spring Boot 4.2

Khi dùng test slice, Spring Boot 4.2 cung cấp:

- `@AutoConfigureMetrics` từ `spring-boot-micrometer-metrics-test`.
- `@AutoConfigureTracing` từ `spring-boot-micrometer-tracing-test`.

Các annotation này có thể auto-configure `ObservationRegistry` trong slice test tương ứng. Với test cần xác minh bean predicate của application context, hãy bảo đảm test thực sự load configuration chứa bean đó.

`RestTestClient` và `WebTestClient` được auto-configure cho test không tự được instrument như một client ứng dụng thông thường. Spring Boot ghi nhận observations của application đang được test; request do test harness phát ra không trở thành client metric hoặc root trace của ứng dụng. Nếu muốn kiểm tra xử lý incoming trace context, gửi request với header `traceparent` đã biết.

## 10. Kiểm thử nhiều predicate

Giả sử ứng dụng có hai policy:

- Predicate A loại observation prefix `internal.`.
- Predicate B loại observation có tên `debug.dump`.

Cấu hình:

~~~java
@Test
void shouldRequireAllPredicatesToAllowObservation() {
    TestObservationRegistry registry = TestObservationRegistry.create();

    registry.observationConfig()
            .observationPredicate((name, context) ->
                    name == null || !name.startsWith("internal."))
            .observationPredicate((name, context) ->
                    !"debug.dump".equals(name));

    Observation internal = Observation.start("internal.health", registry);
    Observation debug = Observation.start("debug.dump", registry);
    Observation business = Observation.start("orders.create", registry);

    assertThat(internal.isNoop()).isTrue();
    assertThat(debug.isNoop()).isTrue();
    assertThat(business.isNoop()).isFalse();

    business.stop();
}
~~~

Nếu nhiều predicate được đăng ký bởi các cấu hình khác nhau, hãy test kết quả tổng hợp qua registry. Đừng chỉ test từng class riêng lẻ rồi cho rằng toàn bộ cấu hình đã đúng.

### 10.1. Kiểm tra short-circuit và side effect

Micrometer dừng đánh giá sau predicate đầu tiên trả về `false`. Vì vậy, thứ tự đăng ký có thể ảnh hưởng predicate nào được gọi trong một lần tạo observation.

Không nên viết predicate để:

- Tăng business counter.
- Gọi database hoặc remote API.
- Thay đổi trạng thái domain.
- Phụ thuộc vào một predicate khác đã chạy.
- Ghi log lớn cho mọi observation.

Predicate được gọi trên đường tạo observation; giữ logic rẻ, xác định và không có side effect.

## 11. Những điều nên assert trong test

Một bộ test tốt không chỉ kiểm tra boolean trả về. Hãy chọn assertion theo hành vi cần bảo đảm.

| Điều cần xác minh | Assertion phù hợp |
| --- | --- |
| Predicate từ chối observation | `observation.isNoop()` là `true` |
| Predicate cho phép observation | `observation.isNoop()` là `false` |
| Observation được phép đã chạy hết lifecycle | `hasBeenStarted()` và `hasBeenStopped()` |
| Observation bị loại không xuất hiện trong test registry | Không có recorded observation tương ứng |
| Business callback vẫn chạy | Assert state/result của business operation |
| Context được phân loại đúng | Kiểm tra `ModulithContext`, module identifier hoặc context subtype |
| Bean được Spring Boot đăng ký | Tạo observation qua bean `ObservationRegistry` đã inject |
| Nhiều predicate phối hợp đúng | Kiểm tra trường hợp từng predicate từ chối và trường hợp tất cả cho phép |

### 11.1. Kiểm tra không có observation bị bỏ sót

Nếu test một operation được phép, có thể dùng:

~~~java
assertThat(registry)
        .hasObservationWithNameEqualTo("orders.create")
        .that()
        .hasBeenStarted()
        .hasBeenStopped()
        .doesNotHaveError();
~~~

Nếu operation ném exception, hãy kiểm tra error state theo API assertion của phiên bản Micrometer đang dùng. Không nên chỉ assert observation tồn tại; observation có thể đã start nhưng không stop do code quản lý lifecycle sai.

### 11.2. Test exception không bị predicate che mất

Predicate không nên quyết định business operation thành công hay thất bại. Có thể test rằng callback vẫn ném exception dù observation bị bỏ qua:

~~~java
@Test
void shouldNotHideBusinessExceptionWhenObservationIsNoop() {
    TestObservationRegistry registry = TestObservationRegistry.create();
    registry.observationConfig()
            .observationPredicate(new IgnoreInternalObservations());

    assertThatThrownBy(() ->
            Observation.createNotStarted("internal.job", registry)
                    .observe(() -> {
                        throw new IllegalStateException("job failed");
                    }))
            .isInstanceOf(IllegalStateException.class)
            .hasMessage("job failed");
}
~~~

Test này xác nhận no-op observation không nuốt exception của business code.

## 12. Kiểm thử sai lầm thường gặp

| Sai lầm | Vì sao test vẫn có thể pass | Cách sửa |
| --- | --- | --- |
| Chỉ gọi `predicate.test(...)` | Chưa xác nhận registry có dùng predicate | Tạo observation qua registry và assert `isNoop()` |
| Test predicate trên registry A nhưng code dùng registry B | Predicate không áp dụng lên registry của code thật | Inject cùng registry vào code và test |
| Chỉ test trường hợp bị từ chối | Predicate có thể từ chối mọi observation | Test cả nhánh cho phép |
| Chỉ test nhánh context cơ bản | Có thể bỏ sót context đặc thù của Modulith | Test `ModulithContext` và module identifier |
| Nghĩ no-op đồng nghĩa business logic không chạy | Nhầm telemetry với business execution | Assert callback vẫn thực thi |
| Dùng `ObservationFilter` để loại observation | Filter không có vai trò quyết định tạo no-op | Dùng `ObservationPredicate` |
| Predicate truy vấn database | Test chậm, flaky và làm tăng tải trên đường tạo observation | Chuẩn bị dữ liệu cần thiết trong context hoặc cấu hình tĩnh |
| Predicate sửa context | Khó đoán thứ tự và tác động tới handlers | Dùng `ObservationFilter` hoặc convention |
| Chỉ test class predicate, bỏ qua Spring wiring | Bean có thể không được load hoặc registry tùy chỉnh không nhận bean | Thêm Spring context test |
| Hard-code tên observation mà không xác minh | Tên có thể đổi theo convention hoặc phiên bản | Dùng hằng số/documentation của observation hoặc xác minh output |
| Mock context nhưng không test instrumentation | Predicate đúng với mock nhưng runtime có thể tạo context khác | Bổ sung integration test qua luồng module thực |
| Giả định mọi span bị loại đều mất mọi log | Logging có thể là pipeline riêng | Kiểm tra handlers và logging configuration độc lập |

## 13. Chẩn đoán khi test thất bại

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra |
| --- | --- | --- |
| Observation đáng lẽ bị loại nhưng `isNoop()` là `false` | Predicate chưa được đăng ký hoặc tên/context không khớp | Kiểm tra registry, bean wiring và đầu vào predicate |
| Observation được phép nhưng không có trong TestObservationRegistry | Observation chưa stop, test dùng registry khác hoặc tên khác | Kiểm tra lifecycle và registry truyền vào code |
| Predicate không nhận được `ModulithContext` | Đang test observation custom khác hoặc instrumentation Modulith chưa tạo module entry observation | Kiểm tra starter insight, module API và đường gọi bean |
| Unit test pass nhưng Spring Boot integration test fail | Predicate bean không được load hoặc registry khác được dùng | Kiểm tra `@TestConfiguration`, component scan và bean registry |
| Tất cả observation đều bị loại | Một predicate khác luôn trả false | Kiểm tra tất cả predicate bean và cấu hình property |
| Observation metrics biến mất nhưng business request vẫn thành công | Predicate có thể loại observation hoặc metrics handler không có mặt | Kiểm tra `isNoop()`, meter registry và handler |
| Trace module bị thiếu một đoạn | Predicate loại module entry observation hoặc sampling/exporter bỏ trace | Kiểm tra context predicate, sampled decision và tracing pipeline |
| Test chạy ổn định một mình nhưng fail khi chạy cùng suite | Test dùng global registry hoặc state chia sẻ | Dùng registry riêng cho test, tránh global mutable state |

### 13.1. Quy trình điều tra

1. Xác định observation name và context thật tại nơi tạo observation.
2. Kiểm tra predicate có nhận đúng hai giá trị đó không.
3. Tạo một `TestObservationRegistry` mới cho unit test.
4. Đăng ký predicate vào đúng registry.
5. Assert `isNoop()` ở cả nhánh allow và deny.
6. Kiểm tra business callback vẫn chạy.
7. Nếu unit test pass, xác minh Spring Boot bean wiring.
8. Nếu predicate liên quan Modulith, kiểm tra module entry observation và `ModulithContext` trong integration test.
9. Sau cùng mới kiểm tra metrics/tracing handlers và exporter.

## 14. Checklist cho một bộ test production-ready

- [ ] Predicate có điều kiện đơn giản, dễ giải thích.
- [ ] Predicate xử lý an toàn tên observation hoặc context có thể null nếu API cho phép.
- [ ] Test nhánh cho phép.
- [ ] Test nhánh từ chối.
- [ ] Test xác nhận observation bị từ chối là no-op.
- [ ] Test xác nhận business operation vẫn chạy.
- [ ] Test lifecycle start/stop cho observation được phép.
- [ ] Test các context subtype liên quan, đặc biệt `ModulithContext` nếu lọc module spans.
- [ ] Test module identifier bị loại và module identifier được giữ.
- [ ] Test nhiều predicate phối hợp theo AND.
- [ ] Test Spring Boot tự đăng ký predicate bean.
- [ ] Không dùng global registry chia sẻ state giữa các test.
- [ ] Không thực hiện I/O hoặc business side effect trong predicate.
- [ ] Có lý do vận hành rõ ràng trước khi loại observation khỏi tracing/metrics.

## 15. Bài thực hành

### Bài 1 — Predicate theo tên

Viết `ObservationPredicate` từ chối các observation có prefix `internal.`. Dùng `TestObservationRegistry` để assert `internal.health` là no-op và `orders.create` được ghi nhận.

### Bài 2 — Business logic vẫn chạy

Bọc một callback tăng `AtomicInteger` trong observation bị từ chối. Assert counter vẫn tăng đúng một lần.

### Bài 3 — Predicate theo context

Tạo `PaymentObservationContext` với channel `TEST` và `CARD`. Viết predicate loại `TEST`, giữ `CARD`. Test cả hai trường hợp qua `Observation.start(name, contextSupplier, registry)`.

### Bài 4 — Lọc module entry observation

Viết predicate bỏ qua `ModulithContext` có module identifier `inventory`. Mock `ObservedModule` và `ModulithContext`; xác nhận `inventory` là no-op còn `orders` được ghi nhận.

### Bài 5 — Kiểm tra nhiều predicate

Đăng ký hai predicate độc lập: một predicate lọc prefix và một predicate lọc tên cụ thể. Kiểm tra bốn tổ hợp đầu vào để xác nhận quan hệ AND.

### Bài 6 — Spring Boot bean wiring

Khai báo predicate bằng `@Bean` trong test configuration. Inject `ObservationRegistry` và xác nhận observation theo prefix bị từ chối khi đi qua registry do Spring Boot tạo.

### Bài 7 — So sánh property và predicate

Dùng `management.observations.enable` để tắt một prefix. Sau đó thay bằng predicate đọc `Observation.Context`. So sánh độ đơn giản và khả năng kiểm soát của hai cách.

### Bài 8 — Kiểm tra tác động tới module tracing

Trong một ứng dụng có hai module `orders` và `inventory`, gọi bean API từ `orders` sang `inventory`. Ghi nhận module entry observation trước và sau khi thêm predicate. Xác minh business result không đổi, sau đó đánh giá trace bị thiếu module entry ảnh hưởng thế nào tới việc điều tra.

## 16. Câu hỏi ôn tập

1. `ObservationPredicate` quyết định điều gì khi tạo observation?
2. Nếu một predicate trả về `false`, Micrometer tạo loại observation nào?
3. Business callback có được thực thi khi observation là no-op không?
4. Nhiều predicate trong cùng registry kết hợp theo AND hay OR?
5. Vì sao cần kiểm thử qua `TestObservationRegistry` thay vì chỉ gọi `predicate.test()`?
6. `ObservationFilter` khác `ObservationPredicate` ở thời điểm và tác động nào?
7. Khi nào nên dùng property `management.observations.enable`?
8. Vì sao predicate dựa trên context cần test cả context subtype?
9. `ModulithContext` mang thông tin gì về module?
10. `ModulithObservations.MODULE_ENTRY` đại diện cho loại observation nào?
11. Vì sao cần test cả module bị loại và module được giữ?
12. Làm thế nào xác nhận Spring Boot tự đăng ký predicate bean?
13. Vì sao predicate không nên gọi database hoặc remote service?
14. Vì sao no-op observation không phải là cơ chế bảo mật?
15. Khi module spans biến mất, cần phân biệt predicate filtering với sampling và exporter failure thế nào?

## 17. Ghi nhớ

**`ObservationPredicate` quyết định observation có được ghi nhận hay trở thành no-op; nó không quyết định business operation có được chạy hay không.** Một registry có nhiều predicate và tất cả phải trả về `true` để observation được tạo bình thường.

Dùng `TestObservationRegistry` để kiểm thử hành vi thực tế: observation bị loại phải là no-op, observation được phép phải được ghi nhận và callback nghiệp vụ vẫn phải chạy. Với Spring Boot, thêm integration test để xác nhận bean predicate được đăng ký vào `ObservationRegistry`. Với Spring Modulith, kiểm thử thêm `ModulithContext` và module identifier để bảo đảm policy chỉ ảnh hưởng đúng module entry observations dự kiến.

Giữ predicate nhanh, thuần và có thể dự đoán. Dùng property cho quy tắc prefix đơn giản; dùng predicate cho điều kiện dựa trên context. Trước khi loại module spans, cân nhắc ảnh hưởng tới tính đầy đủ của distributed trace và khả năng điều tra hệ thống.

### Tài liệu tham khảo chính thức

- [Spring Boot 4.2 — Observability: ObservationPredicate và ngăn observation](https://docs.spring.io/spring-boot/reference/actuator/observability.html).
- [Spring Boot 4.2 — Testing Spring Boot Applications: kiểm thử observations, metrics và tracing](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html).
- [Spring Modulith 2.2 — Production-ready Features: Observing Application Modules](https://docs.spring.io/spring-modulith/reference/2.2/production-ready.html).
- [Spring Modulith 2.2 API — ModulithContext](https://docs.spring.io/spring-modulith/docs/2.2.0/api/org/springframework/modulith/observability/ModulithContext.html).
- [Spring Modulith 2.2 API — ModulithObservations](https://docs.spring.io/spring-modulith/docs/2.2.0/api/org/springframework/modulith/observability/ModulithObservations.html).
- [Spring Modulith 2.2 API — ObservedModule](https://docs.spring.io/spring-modulith/docs/2.2.0/api/org/springframework/modulith/observability/ObservedModule.html).
- [Micrometer 1.18 — Observation Components: Predicates, Filters và Handlers](https://docs.micrometer.io/micrometer/reference/observation/components.html).
- [Micrometer 1.18 — Testing Observations với TestObservationRegistry](https://docs.micrometer.io/micrometer/reference/observation/testing.html).
- [Micrometer — TestObservationRegistry API](https://javadoc.io/doc/io.micrometer/micrometer-observation-test/latest/io/micrometer/observation/tck/TestObservationRegistry.html).

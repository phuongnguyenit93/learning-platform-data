# Kiểm thử observation convention

## 1. Vì sao cần kiểm thử observation convention?

Trong ứng dụng Spring Boot dùng **Spring Modulith**, các lời gọi đi vào API của application module có thể được instrument thành Micrometer observations. Những observation này cung cấp dữ liệu để tạo metrics và traces, giúp nhóm phát triển biết module nào đang xử lý, phương thức nào được gọi và thời gian thực thi ra sao.

**Observation convention** quyết định tên observation, contextual name và các key-value đi kèm. Một convention phù hợp giúp dữ liệu nhất quán giữa metrics, traces, logs và dashboard. Một convention sai có thể làm mất module identifier, đưa dữ liệu có cardinality cao vào metrics hoặc thay đổi tên observation khiến dashboard và alert không còn khớp.

Trong module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, việc kiểm thử convention xác minh rằng dữ liệu quan sát phản ánh đúng ranh giới application module. Bài này hướng dẫn:

- Hiểu vai trò của **ModulithContext** và **ModulithObservationConvention**.
- Kiểm tra convention mặc định của Spring Modulith.
- Viết convention tùy chỉnh và đăng ký nó như Spring bean.
- Kiểm thử name, contextual name, low-cardinality và high-cardinality key values bằng **TestObservationRegistry**.
- Viết integration test để xác nhận Spring Modulith thật sự phát observation khi gọi bean qua Spring container.
- Phát hiện lỗi cardinality, convention không được chọn và observation scope không được đóng.

## 2. Observation convention nằm ở đâu trong luồng quan sát?

Micrometer Observation tách việc ghi nhận một hoạt động khỏi cách xuất dữ liệu. Code được instrument tạo một observation; **ObservationRegistry** điều phối convention, predicate, filter và handler. Handler có thể tạo Timer, span hoặc log tùy cấu hình.

Với Spring Modulith, module instrumentation tạo **ModulithContext** khi một lời gọi đi vào Spring component thuộc API của application module. Convention phù hợp với context này là **ModulithObservationConvention**.

~~~mermaid
flowchart TD
    A[Call vào module API] --> B[Module observability interceptor]
    B --> C[ModulithContext]
    C --> D[ModulithObservationConvention]
    D --> E[Observation name và KeyValues]
    E --> F[ObservationRegistry]
    F --> G[Meter handler]
    F --> H[Tracing handler]
    G --> I[Micrometer metrics]
    H --> J[Trace backend]
~~~

Các thành phần có trách nhiệm riêng:

| Thành phần | Trách nhiệm | Điều cần kiểm thử |
| --- | --- | --- |
| ModulithContext | Giữ module, invocation và application environment | Context có module và invocation đúng không? |
| ModulithObservationConvention | Chọn name, contextual name và key-values | Tên và tags có đúng quy ước không? |
| ObservationRegistry | Chọn convention, predicate, filter và handler | Convention tùy chỉnh có được chọn không? |
| ObservationHandler | Xử lý vòng đời observation để tạo metric/trace/log | Observation có start, error và stop đúng thứ tự không? |
| Meter registry | Lưu Timer/Counter | Low-cardinality tags có ổn định không? |
| Tracing bridge/exporter | Tạo và xuất span | High-cardinality values có được giữ trong trace không? |

Một convention không tự tạo metrics hoặc traces. Nó chỉ mô tả tên và metadata. Việc tạo Timer hoặc span phụ thuộc các ObservationHandler được đăng ký trên registry.

## 3. ModulithContext cung cấp dữ liệu gì?

**ModulithContext** là một implementation của **Observation.Context** dành cho ứng dụng modular. Nó được tạo với module được quan sát, method invocation và Spring Environment.

Các phương thức quan trọng:

| Phương thức | Ý nghĩa |
| --- | --- |
| getModule() | Module đang được quan sát |
| getInvocation() | Method invocation đang thực thi |
| getApplicationName() | Tên ứng dụng nếu có |
| getLowCardinalityValues() | Key-values có số lượng giá trị hữu hạn |
| getHighCardinalityValues() | Key-values có thể có nhiều giá trị |
| getContextualName() | Tên dễ đọc gắn với invocation |

Spring Modulith xác định tên convention mặc định bằng **ModulithContext.DEFAULT_CONVENTION_NAME**, có giá trị **module.invocations**.

### 3.1. Các key mặc định

Module entry observation có các key chính:

| Key | Cardinality | Ý nghĩa |
| --- | --- | --- |
| module.identifier | Low | Technical identifier, ví dụ orders |
| module.name | Low | Tên hiển thị của module |
| module.invocation-type | Low | Kiểu invocation như bean hoặc event listener |
| module.method | High | Phương thức được thực thi trên module |

Các key low-cardinality phù hợp làm metric tags vì tập giá trị thường hữu hạn. Key high-cardinality phù hợp với trace attributes để điều tra từng thao tác. Không đưa request ID, user ID, order ID hoặc dữ liệu tùy biến không giới hạn vào low-cardinality values.

### 3.2. Phân biệt observation name và contextual name

- **Observation name** là tên kỹ thuật dùng để định danh loại observation, mặc định là **module.invocations**.
- **Contextual name** là tên dễ đọc hơn cho một lần thực thi, thường mô tả module và method.

Không nên đổi observation name theo từng module hoặc method. Nếu mỗi module tạo một meter name riêng, dashboard và alert sẽ khó tổng hợp, số meter tăng và convention bị phân mảnh. Giữ tên kỹ thuật ổn định; dùng module.identifier để phân nhóm.

## 4. Convention mặc định của Spring Modulith

Spring Modulith cung cấp **DefaultModulithObservationConvention** làm convention mặc định cho **ModulithContext**. Implementation này ủy quyền việc lấy name và key-values cho dữ liệu trong context.

Về mặt hành vi, convention mặc định cần giữ được:

- Tên observation là **module.invocations**.
- Module identifier xuất hiện dưới dạng low-cardinality key.
- Module name và invocation type được giữ trong low-cardinality values.
- Method được giữ trong high-cardinality values.
- Contextual name phản ánh invocation đang được quan sát.

Có thể tham chiếu implementation mặc định qua **DefaultModulithObservationConvention.INSTANCE** ở API hiện hành. Khi kiểm thử, nên xác nhận các thuộc tính quan trọng thay vì phụ thuộc vào thứ tự key-value hoặc cách hiển thị nội bộ của object.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.observability.ModulithContext;
import org.springframework.modulith.observability.ModulithObservationConvention;
import org.springframework.modulith.observability.support.DefaultModulithObservationConvention;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

class DefaultModulithObservationConventionTests {

    @Test
    void exposesTheExpectedConventionNameAndModuleDimensions() {
        ModulithContext context = mock(ModulithContext.class);

        when(context.getLowCardinalityValues()).thenReturn(KeyValues.of(
            KeyValue.of("module.identifier", "orders"),
            KeyValue.of("module.name", "Orders"),
            KeyValue.of("module.invocation-type", "bean")
        ));

        when(context.getHighCardinalityValues()).thenReturn(KeyValues.of(
            KeyValue.of("module.method", "placeOrder")
        ));

        when(context.getContextualName()).thenReturn("orders.place-order");

        ModulithObservationConvention convention =
            DefaultModulithObservationConvention.INSTANCE;

        assertThat(convention.supportsContext(context)).isTrue();
        assertThat(convention.getName())
            .isEqualTo(ModulithContext.DEFAULT_CONVENTION_NAME);
        assertThat(convention.getContextualName(context))
            .isEqualTo("orders.place-order");

        assertThat(convention.getLowCardinalityKeyValues(context))
            .contains(
                KeyValue.of("module.identifier", "orders"),
                KeyValue.of("module.name", "Orders"),
                KeyValue.of("module.invocation-type", "bean")
            );

        assertThat(convention.getHighCardinalityKeyValues(context))
            .contains(KeyValue.of("module.method", "placeOrder"));
    }
}
~~~

Ví dụ dùng Mockito để tạo context có dữ liệu xác định. Khi cần kiểm tra cách ModulithContext thật được tạo từ application module, hãy bổ sung integration test ở phần sau.

## 5. Khi nào cần custom convention?

Custom convention hữu ích khi cần bổ sung metadata dùng chung cho mọi module invocation, ví dụ:

- Environment như development, staging hoặc production.
- Phiên bản ứng dụng.
- Một nhóm triển khai hoặc vùng vận hành có tập giá trị hữu hạn.
- Contextual name theo quy ước nội bộ đã thống nhất.

Không dùng convention để nhét toàn bộ dữ liệu nghiệp vụ vào metrics. Trước khi thêm một key, cần quyết định nó thuộc low-cardinality hay high-cardinality.

| Dữ liệu | Nên đặt ở đâu? | Lý do |
| --- | --- | --- |
| module.identifier | Low cardinality | Số module hữu hạn |
| module.name | Low cardinality | Tập tên module hữu hạn |
| module.invocation-type | Low cardinality | Số loại invocation hữu hạn |
| deployment.environment | Low cardinality | Các môi trường được kiểm soát |
| module.method | High cardinality | Chi tiết method phù hợp trace |
| traceId | Trace/log correlation | Giá trị thay đổi theo trace |
| orderId | Trace/log nếu thực sự cần | Không phù hợp metric label |
| Email hoặc token | Không thêm | Dữ liệu nhạy cảm |

## 6. Viết custom ModulithObservationConvention

Giả sử muốn thêm **deployment.environment** vào low-cardinality values để dashboard có thể lọc theo môi trường. Convention nên giữ nguyên key mặc định và chỉ bổ sung key cần thiết.

~~~java
package com.example.shop.observability;

import org.springframework.modulith.observability.ModulithContext;
import org.springframework.modulith.observability.ModulithObservationConvention;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

final class ShopModulithObservationConvention
        implements ModulithObservationConvention {

    private final String environment;

    ShopModulithObservationConvention(String environment) {
        this.environment = environment;
    }

    @Override
    public String getName() {
        return ModulithContext.DEFAULT_CONVENTION_NAME;
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(ModulithContext context) {
        return ModulithObservationConvention.super
            .getLowCardinalityKeyValues(context)
            .and(KeyValue.of("deployment.environment", environment));
    }

    // Giữ nguyên high-cardinality values mặc định.
}
~~~

Điểm quan trọng là gọi **ModulithObservationConvention.super.getLowCardinalityKeyValues(context)** trước khi thêm key mới. Cách này giữ module identifier, module name và invocation type do Spring Modulith cung cấp.

Nếu trả về một KeyValues mới mà không kết hợp values mặc định, các tag chuẩn có thể biến mất khỏi metrics và traces. Đây là lỗi dễ bỏ sót nếu chỉ kiểm tra key tùy chỉnh.

### 6.1. Đăng ký convention như Spring bean

Spring Modulith cho phép tùy chỉnh convention bằng cách cung cấp một bean **ModulithObservationConvention**.

~~~java
package com.example.shop.observability;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

import org.springframework.modulith.observability.ModulithObservationConvention;

@Configuration(proxyBeanMethods = false)
class ModulithObservabilityConfiguration {

    @Bean
    ModulithObservationConvention modulithObservationConvention(
            Environment environment) {

        String deploymentEnvironment = environment.getProperty(
            "deployment.environment",
            "local"
        );

        return new ShopModulithObservationConvention(deploymentEnvironment);
    }
}
~~~

Cấu hình tương ứng:

~~~yaml
deployment:
  environment: staging
~~~

Giá trị environment phải thuộc một tập hữu hạn được kiểm soát. Không lấy giá trị tùy ý từ request header hoặc user input rồi gắn vào low-cardinality key.

Spring Modulith cần observability support ở runtime. Nếu ứng dụng dùng Insight starter, starter này cung cấp Actuator và module observability support. Khi source code trực tiếp tham chiếu API ModulithObservationConvention, bảo đảm artifact API có trong compile classpath.

## 7. Dependency cần cho kiểm thử

Ví dụ Maven khi ứng dụng đã quản lý version bằng Spring Boot và Spring Modulith BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-observability-api</artifactId>
    </dependency>

    <!-- Chỉ cần nếu test tham chiếu trực tiếp implementation mặc định. -->
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-observability-core</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-observation-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Nếu test dùng Mockito và AssertJ, dùng các dependency test mà Spring Boot starter test đã quản lý hoặc khai báo riêng theo cấu hình dự án. Không khai báo một version Micrometer khác với version được BOM quản lý.

**micrometer-observation-test** cung cấp **TestObservationRegistry**, một registry dành cho unit test. Registry này lưu các observation được tạo và tự đăng ký validator để phát hiện một số lỗi vòng đời như stop trước start hoặc stop nhiều lần.

## 8. Kiểm thử custom convention bằng TestObservationRegistry

Một unit test tốt cần xác nhận đồng thời:

1. Observation name vẫn ổn định.
2. Low-cardinality values mặc định vẫn còn.
3. Key tùy chỉnh được thêm vào low-cardinality values.
4. High-cardinality values mặc định vẫn còn.
5. Observation đã start và stop.
6. Không còn observation scope chưa đóng sau khi test kết thúc.

Ví dụ:

~~~java
package com.example.shop.observability;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.observability.ModulithContext;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;

class ShopModulithObservationConventionTests {

    @Test
    void preservesDefaultKeysAndAddsEnvironment() {
        ModulithContext context = mock(ModulithContext.class);

        when(context.getLowCardinalityValues()).thenReturn(KeyValues.of(
            KeyValue.of("module.identifier", "orders"),
            KeyValue.of("module.name", "Orders"),
            KeyValue.of("module.invocation-type", "bean")
        ));

        when(context.getHighCardinalityValues()).thenReturn(KeyValues.of(
            KeyValue.of("module.method", "placeOrder")
        ));

        when(context.getContextualName()).thenReturn("orders.place-order");

        var convention = new ShopModulithObservationConvention("test");
        var registry = TestObservationRegistry.create();

        Observation.createNotStarted(
            convention,
            () -> context,
            registry
        ).observe(() -> {
            // Thực hiện phần công việc được quan sát trong unit test.
        });

        assertThat(registry)
            .doesNotHaveAnyRemainingCurrentObservation()
            .hasObservationWithNameEqualTo(
                ModulithContext.DEFAULT_CONVENTION_NAME
            )
            .that()
            .hasLowCardinalityKeyValue("module.identifier", "orders")
            .hasLowCardinalityKeyValue("module.name", "Orders")
            .hasLowCardinalityKeyValue("module.invocation-type", "bean")
            .hasLowCardinalityKeyValue("deployment.environment", "test")
            .hasHighCardinalityKeyValue("module.method", "placeOrder")
            .hasBeenStarted()
            .hasBeenStopped();

        assertThat(convention.getContextualName(context))
            .isEqualTo("orders.place-order");
    }
}
~~~

Test này kiểm tra convention được áp dụng khi tạo observation qua Micrometer API. Nó không chứng minh Spring Modulith đã instrument một bean thực tế trong application context; phần đó cần integration test.

### 8.1. Vì sao dùng TestObservationRegistry?

**TestObservationRegistry** lưu các context của observation và cung cấp AssertJ assertions để kiểm tra name, contextual name, low/high-cardinality values, events, start/stop và error.

Ngoài việc xác nhận output, registry còn giúp phát hiện lỗi vòng đời. Ví dụ, nếu code gọi stop hai lần hoặc để observation chưa stop, validator có thể ném **InvalidObservationException** với lịch sử các thao tác.

Không cần khởi tạo tracing backend hoặc Prometheus server cho mọi unit test convention. Chỉ cần registry kiểm thử và context có dữ liệu xác định.

## 9. Kiểm thử cardinality

Một convention có thể hoạt động đúng về mặt tên nhưng vẫn tạo ra metric cardinality nguy hiểm. Vì vậy cần test riêng quy tắc low/high-cardinality.

Giả sử một module invocation có:

- Module ID là orders.
- Invocation type là bean.
- Environment là staging.
- Method là placeOrder.

Kỳ vọng:

| Key | Giá trị | Nhóm |
| --- | --- | --- |
| module.identifier | orders | Low |
| module.invocation-type | bean | Low |
| deployment.environment | staging | Low |
| module.method | placeOrder | High |

Có thể thêm assertion để đảm bảo không đưa dữ liệu định danh từng request vào low-cardinality values:

~~~java
var lowValues = convention.getLowCardinalityKeyValues(context);

assertThat(lowValues)
    .contains(KeyValue.of("module.identifier", "orders"))
    .contains(KeyValue.of("deployment.environment", "staging"));
~~~

Nếu cần kiểm tra một key không xuất hiện, chuyển values thành list hoặc stream rồi kiểm tra từng key. Mục tiêu là bảo đảm không có key động trong tập low-cardinality.

Không nên dùng request ID, customer ID, order ID, session token hoặc URI đầy đủ làm metric tag. Nếu cần điều tra một request cụ thể, hãy dùng trace/log correlation.

## 10. Kiểm thử convention bean trong Spring context

Unit test có thể tạo convention trực tiếp bằng constructor. Tuy nhiên, ứng dụng production sử dụng convention thông qua bean. Cần xác nhận bean được tạo và có thể được Spring Modulith nhận diện.

Có thể kiểm tra bean trong một Spring Boot test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.modulith.observability.ModulithContext;
import org.springframework.modulith.observability.ModulithObservationConvention;

@SpringBootTest
class ModulithObservationConventionBeanTests {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void registersOneModulithObservationConvention() {
        Map<String, ModulithObservationConvention> conventions =
            applicationContext.getBeansOfType(
                ModulithObservationConvention.class
            );

        assertThat(conventions).hasSize(1);
        assertThat(conventions.values().iterator().next().getName())
            .isEqualTo(ModulithContext.DEFAULT_CONVENTION_NAME);
    }
}
~~~

Ví dụ này giả định ứng dụng có đúng một convention bean. Nếu dự án cố ý cung cấp nhiều bean, hãy xác định bean được auto-configuration chọn và tránh để hai convention cùng hỗ trợ một context mà không có quy tắc ưu tiên rõ ràng.

Đăng ký bean thành công chưa có nghĩa instrumentation đã chạy. Cần gọi một component thuộc API module qua Spring container và kiểm tra observation được tạo.

## 11. Integration test cho module instrumentation thực tế

Integration test xác nhận cả ba phần: module instrumentation được bật, convention bean được dùng và observation xuất hiện khi gọi module API.

Một test handler đơn giản có thể thu thập những observation thuộc ModulithContext:

~~~java
package com.example.shop.observability;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import org.springframework.modulith.observability.ModulithContext;

final class RecordingModulithObservationHandler
        implements ObservationHandler<Observation.Context> {

    private final List<Observation.Context> completed =
        new CopyOnWriteArrayList<>();

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof ModulithContext;
    }

    @Override
    public void onStop(Observation.Context context) {
        completed.add(context);
    }

    List<Observation.Context> completed() {
        return List.copyOf(completed);
    }
}
~~~

Trong test Spring Boot:

~~~java
package com.example.shop.observability;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import io.micrometer.common.KeyValue;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.modulith.observability.ModulithContext;

// Import OrderManagement và PlaceOrderCommand từ module API thực tế của ứng dụng.

@SpringBootTest(properties = "deployment.environment=test")
class ModuleEntryObservationIntegrationTests {

    @Autowired
    ObservationRegistry observationRegistry;

    @Autowired
    OrderManagement orderManagement;

    @Test
    void recordsObservationWhenCallingModuleApi() {
        var recorder = new RecordingModulithObservationHandler();

        observationRegistry.observationConfig()
            .observationHandler(recorder);

        // Gọi bean API được Spring quản lý, không tự tạo bằng new.
        orderManagement.placeOrder(new PlaceOrderCommand("order-123"));

        var observed = recorder.completed().stream()
            .filter(ModulithContext.class::isInstance)
            .map(ModulithContext.class::cast)
            .filter(context -> context.getModule()
                .getIdentifier().toString().equals("orders"))
            .findFirst()
            .orElseThrow();

        assertThat(observed.getModule().getIdentifier().toString())
            .isEqualTo("orders");
        assertThat(observed.getLowCardinalityKeyValues())
            .contains(KeyValue.of("deployment.environment", "test"));
    }
}
~~~

**OrderManagement** và **PlaceOrderCommand** là tên minh họa; thay bằng API thực tế của module trong ứng dụng. Đảm bảo bean được gọi thông qua Spring container để module observability interceptor có thể áp dụng.

Để kiểm tra key-values sau khi convention được áp dụng, có thể lưu thêm các giá trị trên Observation.Context trong handler hoặc dùng TestObservationRegistry ở unit test. Integration test nên tập trung xác nhận đường đi thật: bean được instrument, context nhận diện đúng module và convention tùy chỉnh đã được chọn.

### 11.1. Vì sao không gọi method bằng object tự tạo?

Spring Modulith sử dụng cơ chế proxy/interceptor để quan sát các Spring component thuộc module API. Nếu test gọi một object được khởi tạo bằng new, hoặc gọi một method nội bộ qua self-invocation không đi qua proxy, observation có thể không được tạo.

Khi test không thấy observation, hãy kiểm tra:

- Component có nằm trong module API được nhận diện không?
- Bean có được Spring quản lý không?
- Lời gọi có đi qua proxy/interceptor không?
- Spring Modulith observability support có trên runtime classpath không?
- ObservationRegistry có được cấu hình và không phải no-op registry không?
- Test có gọi đúng method được instrument không?

## 12. Kiểm thử convention name và contextual name

Tên observation cần ổn định để metrics và dashboard tiếp tục hoạt động sau khi refactor method. Với module invocation, giữ **ModulithContext.DEFAULT_CONVENTION_NAME** làm observation name.

Contextual name có thể thay đổi theo cách trình bày, nhưng phải ngắn, dễ đọc và không chứa dữ liệu request động.

Ví dụ kiểm tra:

~~~java
@Test
void keepsObservationNameStable() {
    var convention = new ShopModulithObservationConvention("test");

    assertThat(convention.getName())
        .isEqualTo(ModulithContext.DEFAULT_CONVENTION_NAME);
}
~~~

Nếu convention tùy chỉnh override contextual name, test các module đại diện và invocation type khác nhau. Không tạo contextual name từ toàn bộ method arguments, URI có ID hoặc nội dung event payload.

## 13. Phân biệt convention với observation filter và handler

Ba extension point này thường bị nhầm lẫn:

| Extension point | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| ModulithObservationConvention | Chọn name và key-values cho module observation | Thêm deployment.environment |
| ObservationFilter | Thay đổi context trước khi observation dừng | Loại bỏ hoặc chuẩn hóa key-value |
| ObservationHandler | Phản ứng với lifecycle để tạo metric, trace hoặc log | Lưu Timer hoặc span |

Nếu cần thêm một tag vào mọi observation bất kể convention nào được dùng, cân nhắc **ObservationFilter**. Nếu cần tạo Timer hoặc span, dùng handler. Nếu cần tùy chỉnh metadata riêng cho module invocation, dùng **ModulithObservationConvention**.

Không dùng handler để tự đặt lại toàn bộ metadata mà convention đã cung cấp. Cách đó khiến trách nhiệm bị phân tán và khó kiểm thử.

## 14. Kiểm thử lỗi và observation lifecycle

Observation có vòng đời gồm start, scope, error, event và stop. Khi công việc ném exception, instrumentation cần ghi nhận error và vẫn đóng observation.

Ví dụ với một observation độc lập:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import org.springframework.modulith.observability.ModulithContext;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;

@Test
void recordsErrorAndStopsObservation() {
    var registry = TestObservationRegistry.create();
    var context = mock(ModulithContext.class);

    when(context.getLowCardinalityValues()).thenReturn(
        KeyValues.of(KeyValue.of("module.identifier", "payments"))
    );
    when(context.getHighCardinalityValues()).thenReturn(KeyValues.empty());

    var convention = new ShopModulithObservationConvention("test");
    var failure = new IllegalStateException("payment rejected");

    assertThatThrownBy(() ->
        Observation.createNotStarted(convention, () -> context, registry)
            .observe(() -> {
                throw failure;
            })
    ).isSameAs(failure);

    assertThat(registry)
        .doesNotHaveAnyRemainingCurrentObservation()
        .hasObservationWithNameEqualTo(
            ModulithContext.DEFAULT_CONVENTION_NAME
        )
        .that()
        .hasBeenStarted()
        .hasBeenStopped()
        .hasError();
}
~~~

Test này kiểm tra Micrometer Observation lifecycle. Nó không thay thế test nghiệp vụ cho exception của module, nhưng giúp phát hiện instrumentation không đóng scope hoặc không ghi nhận error.

Nếu lỗi phát sinh trong module API, integration test nên xác nhận exception vẫn được truyền theo hợp đồng của method và observation được dừng đúng cách. Không nuốt exception chỉ để làm test observability pass.

## 15. Những lỗi thường gặp khi kiểm thử convention

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không có observation | Module observability chưa được kích hoạt hoặc registry là no-op | Kiểm tra runtime dependency và ObservationRegistry |
| Observation name thay đổi ngoài ý muốn | Custom convention override getName() | Giữ ModulithContext.DEFAULT_CONVENTION_NAME nếu không có lý do đổi tên |
| Mất module.identifier | Custom convention thay thế toàn bộ low-cardinality values | Kết hợp với ModulithObservationConvention.super |
| Mất module.method trong trace | Custom convention thay thế high-cardinality values | Giữ high-cardinality values mặc định |
| Metric cardinality tăng mạnh | Đưa request ID, user ID hoặc method arguments vào low-cardinality values | Chuyển chi tiết động sang high-cardinality hoặc log |
| Convention bean không được chọn | Bean thiếu, không nằm trong context hoặc có convention khác cùng hỗ trợ | Kiểm tra ApplicationContext và convention selection |
| Unit test pass nhưng runtime không có span | Unit test chỉ kiểm tra convention, chưa kiểm tra module instrumentation | Viết integration test gọi bean API qua Spring |
| Test không thấy observation khi gọi method | Gọi object tự tạo hoặc self-invocation bypass proxy | Dùng bean do Spring quản lý và gọi qua API |
| Observation chưa stop | Code tự điều khiển lifecycle nhưng thiếu finally | Dùng observe hoặc bảo đảm stop trong finally |
| Contextual name chứa ID động | Convention ghép request data vào tên | Dùng tên ổn định, đưa ID vào trace/log khi cần |
| Test phụ thuộc thứ tự KeyValues | Assertion so sánh danh sách theo thứ tự | Kiểm tra từng key-value cần thiết |
| Metric và trace có metadata khác nhau | Convention hoặc filter chỉ áp dụng một phần pipeline | Kiểm tra registry, handler và convention thực tế |

## 16. Quy trình kiểm thử đề xuất

Một quy trình gọn nhưng đủ tin cậy gồm:

1. **Kiểm thử default convention:** xác nhận name, module identifier, module name, invocation type và method.
2. **Kiểm thử custom convention:** xác nhận key bổ sung và bảo toàn key mặc định.
3. **Kiểm thử cardinality:** xác nhận key hữu hạn nằm ở low cardinality, dữ liệu động không bị đưa vào metric tags.
4. **Kiểm thử lifecycle:** xác nhận observation start/stop, error và không còn scope đang mở.
5. **Kiểm thử Spring bean:** xác nhận convention được đăng ký trong ApplicationContext.
6. **Kiểm thử module instrumentation:** gọi module API qua Spring container và xác nhận ModulithContext xuất hiện.
7. **Kiểm thử export ở tầng tích hợp:** xác nhận metrics/traces nhận được metadata mong đợi trong môi trường test phù hợp.

Không cần chạy Prometheus, Grafana hoặc tracing backend cho mọi unit test. Chỉ dùng integration environment khi cần xác minh exporter, protocol hoặc backend ingestion.

## 17. Bài thực hành: kiểm thử convention cho module orders

**Bối cảnh:** ứng dụng có module orders, inventory và payments. Nhóm muốn thêm environment vào mọi module observation nhưng giữ nguyên metadata mặc định.

| Bước | Công việc | Tiêu chí hoàn thành |
| --- | --- | --- |
| 1 | Thêm observability API và Insight runtime dependency | Source tham chiếu được convention API, module instrumentation có mặt |
| 2 | Viết ShopModulithObservationConvention | Name giữ module.invocations |
| 3 | Bổ sung deployment.environment | Key nằm trong low-cardinality values |
| 4 | Đăng ký convention bean | Spring context có convention đúng |
| 5 | Viết unit test với TestObservationRegistry | Kiểm tra name, low/high values, start/stop |
| 6 | Kiểm tra cardinality | Không có request ID hoặc user ID trong low-cardinality values |
| 7 | Viết integration test gọi orders API bean | Có module entry observation với identifier orders |
| 8 | Kiểm tra trường hợp exception | Observation được stop và error được ghi nhận |
| 9 | Đối chiếu metric và trace trong môi trường test | Metadata phù hợp với convention và cấu hình handler |

### 17.1. Câu hỏi tự kiểm tra

1. **Observation convention quyết định điều gì?** Observation name, contextual name và key-values.
2. **Convention dành cho module invocation của Spring Modulith là interface nào?** ModulithObservationConvention.
3. **Context mà convention nhận là gì?** ModulithContext.
4. **Tên observation mặc định là gì?** module.invocations.
5. **Vì sao phải giữ low-cardinality values mặc định khi custom?** Để metrics và dashboard vẫn nhận diện được module identifier, module name và invocation type.
6. **module.method thuộc nhóm nào?** High-cardinality key.
7. **TestObservationRegistry giúp kiểm tra điều gì?** Observation name, key-values, events, lifecycle và scope còn mở.
8. **Unit test convention có chứng minh module instrumentation hoạt động không?** Không; cần integration test gọi Spring bean thuộc module API qua container.
9. **Khi nào nên dùng ObservationFilter thay convention?** Khi cần bổ sung hoặc chuẩn hóa metadata áp dụng rộng hơn, không phụ thuộc convention cụ thể.
10. **Có nên đưa order ID vào low-cardinality key không?** Không; đó là giá trị động, không phù hợp metric tags.

## 18. Ghi nhớ

**ModulithObservationConvention** là extension point để kiểm soát metadata của module invocation observation. **ModulithContext** cung cấp module, invocation, application name và các key-values mặc định. Tên observation mặc định là **module.invocations**; module identifier, module name và invocation type là low-cardinality, còn module method là high-cardinality.

Khi viết convention tùy chỉnh, hãy giữ key-values mặc định rồi mới bổ sung metadata có cardinality hữu hạn. Dùng **TestObservationRegistry** để kiểm tra name, contextual name, low/high values và lifecycle. Sau đó dùng Spring Boot integration test để xác nhận convention bean được đăng ký và module API thật sự tạo observation qua Spring container.

Unit test giúp kiểm tra quy tắc metadata; integration test xác minh instrumentation; kiểm thử exporter/backend xác nhận dữ liệu đi hết pipeline. Kết hợp ba lớp này giúp module spans, metrics và traces giữ được định danh nhất quán, hỗ trợ kiểm chứng kiến trúc mô-đun khi hệ thống vận hành.

### Tài liệu tham khảo

- [Spring Modulith 2.2 — Production-ready Features](https://docs.spring.io/spring-modulith/reference/2.2/production-ready.html): module entry spans, module tags và custom ModulithObservationConvention.
- [Spring Modulith 2.2 API — ModulithObservationConvention](https://docs.spring.io/spring-modulith/docs/2.2.0/api/org/springframework/modulith/observability/ModulithObservationConvention.html): convention API cho ModulithContext.
- [Spring Modulith 2.2 API — ModulithContext](https://docs.spring.io/spring-modulith/docs/2.2.0/api/org/springframework/modulith/observability/ModulithContext.html): context, default convention name và các key-values.
- [Spring Modulith 2.2 API — ModulithObservations.LowKeys](https://docs.spring.io/spring-modulith/docs/2.2.0/api/org/springframework/modulith/observability/ModulithObservations.LowKeys.html): low-cardinality keys.
- [Spring Modulith 2.2 API — ModulithObservations.HighKeys](https://docs.spring.io/spring-modulith/docs/2.2.0/api/org/springframework/modulith/observability/ModulithObservations.HighKeys.html): high-cardinality keys.
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): convention, registry, handler, filter và cardinality.
- [Micrometer — Testing Observations](https://docs.micrometer.io/micrometer/reference/observation/testing.html): micrometer-observation-test, TestObservationRegistry và assertions.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): cấu hình observation trong test context.

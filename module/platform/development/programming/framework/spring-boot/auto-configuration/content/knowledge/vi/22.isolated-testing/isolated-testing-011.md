# Giải phóng context sau mỗi lần chạy và giữ các trường hợp độc lập

> **Mục tiêu:** Viết kiểm thử auto-configuration sao cho mỗi trường hợp có một Spring context riêng, context được đóng ngay sau khi kiểm thử xong và tài nguyên do bean quản lý được giải phóng đúng lifecycle. Đồng thời phân biệt được trạng thái thuộc context với trạng thái toàn JVM hoặc hệ thống bên ngoài vẫn có thể rò rỉ giữa các test.

Bài học thuộc nhóm **Kiểm thử độc lập**, sử dụng Spring Boot 3.3.x, Java 17+, JUnit Jupiter và AssertJ. Trọng tâm là `ApplicationContextRunner` và các nguyên tắc cô lập test khi kiểm tra điều kiện, bean mặc định, property, classpath và vòng đời tài nguyên.

## 1. Vì sao cần đóng context sau mỗi lần chạy?

Một `ApplicationContext` giữ nhiều đối tượng và tài nguyên trong suốt thời gian hoạt động:

- Singleton beans và trạng thái mutable của chúng.
- Connection pool, client HTTP, cache, scheduler và executor.
- Listener, callback, lifecycle component và các hook shutdown.
- Các bean được tạo trong quá trình refresh và dependency injection.
- Các tài nguyên do bean đăng ký để giải phóng khi context đóng.

Nếu test tạo nhiều context rồi bỏ quên context cũ, tài nguyên có thể tiếp tục tồn tại sau khi assertion đã hoàn tất. Một connection pool chưa đóng có thể giữ connection; executor chưa dừng có thể giữ thread; listener chưa được gỡ có thể tiếp tục nhận event; file hoặc socket tạm thời có thể vẫn bị giữ.

Spring Boot cung cấp các runner để tạo context nhỏ cho một trường hợp kiểm thử. Với `ApplicationContextRunner`, mỗi lần gọi `run(...)` sẽ tạo và refresh một context mới, chuyển context đó vào callback để assertion, sau đó tự động đóng context khi callback hoàn tất.

Luồng lifecycle:

~~~text
ApplicationContextRunner.run(...)
          |
          v
Tạo ApplicationContext mới
          |
          v
Đăng ký configuration, bean và property
          |
          v
Refresh context
          |
          v
Chạy callback / assertions
          |
          v
Đóng ApplicationContext
          |
          v
Gọi các callback hủy bean
          |
          v
Giải phóng tài nguyên do context quản lý
~~~

Đóng context là một phần của contract của runner. Test không cần tự gọi `context.close()` trong callback thông thường. Hãy để runner quản lý lifecycle để không vô tình đóng context giữa lúc assertion còn đang sử dụng bean.

## 2. ApplicationContextRunner tạo context mới cho từng lần run

`ApplicationContextRunner` là runner cho môi trường non-web tiêu chuẩn. Constructor mặc định sử dụng `AnnotationConfigApplicationContext` làm context nền.

Một runner thường được khai báo thành field của test class để dùng chung cấu hình cơ sở:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(MyServiceAutoConfiguration.class));
~~~

Việc dùng chung runner không có nghĩa các test dùng chung một context. Runner lưu cấu hình cần áp dụng; mỗi lời gọi `run(...)` tạo một context mới theo cấu hình hiện tại.

Ví dụ:

~~~java
contextRunner.run(context -> {
    // Context thứ nhất.
});

contextRunner.run(context -> {
    // Context thứ hai, được tạo mới.
});
~~~

Hai callback nhận hai context khác nhau. Bean singleton trong context thứ nhất không được tái sử dụng làm singleton của context thứ hai. Khi callback thứ nhất kết thúc, context thứ nhất được đóng trước khi lời gọi `run(...)` trả về.

### 2.1. Runner có thể được tái sử dụng

Các method tùy chỉnh như `withPropertyValues`, `withUserConfiguration`, `withBean`, `withClassLoader` và `withInitializer` trả về một instance runner mới với cấu hình được cập nhật.

Ví dụ:

~~~java
contextRunner.withPropertyValues("demo.mode=first").run(context -> {
    // Kiểm thử trường hợp first.
});

contextRunner.withPropertyValues("demo.mode=second").run(context -> {
    // Kiểm thử trường hợp second.
});

contextRunner.run(context -> {
    // Dùng lại cấu hình cơ sở, không có demo.mode do hai lời gọi trên thêm vào.
});
~~~

Mỗi biến thể là một cấu hình runner riêng. Không gán ngược biến thể vào runner cơ sở nếu không muốn tất cả test sau đó nhận cấu hình đã thay đổi:

~~~java
// Tránh cách làm này nếu các test phải độc lập:
contextRunner = contextRunner.withPropertyValues("demo.mode=first");
~~~

Thông thường hãy khai báo runner là `private final`, giữ cấu hình chung tại field và tạo biến thể ngay tại từng test. Cách đó giúp đọc test biết rõ property hoặc configuration nào chỉ thuộc một trường hợp.

## 3. Thời điểm context được đóng

Contract của `AbstractApplicationContextRunner.run(...)` mô tả rằng runner tạo và refresh context, chuyển context cho consumer, rồi đóng context khi consumer hoàn tất.

Điều này có một số hệ quả thực tế:

1. Bean có thể được sử dụng trong callback để kiểm tra state, dependency và behavior.
2. Sau khi callback trả về, context đã được đóng; không tiếp tục dùng bean hoặc lấy bean từ context đó.
3. Callback kết thúc bằng assertion thành công hay ném exception thì test vẫn phải để lifecycle của context được quản lý theo runner.
4. Nếu startup thất bại, runner vẫn gọi callback với một context ở trạng thái failed để test kiểm tra nguyên nhân.
5. Không giữ reference tới context để dùng trong test method khác.

Ví dụ không nên làm:

~~~java
AtomicReference<AssertableApplicationContext> saved =
        new AtomicReference<>();

contextRunner.run(context -> saved.set(context));

// Context đã được đóng sau khi run trả về.
// Không dùng saved.get() để tiếp tục lấy bean hoặc đọc Environment.
~~~

Hãy đặt tất cả assertion cần thiết bên trong callback:

~~~java
contextRunner.run(context -> {
    assertThat(context).hasNotFailed();
    assertThat(context).hasSingleBean(MyService.class);

    MyService service = context.getBean(MyService.class);
    assertThat(service.process("hello")).isEqualTo("HELLO");
});
~~~

### 3.1. prepare(...) khác run(...)

`prepare(...)` cũng tạo context và đóng context sau callback, nhưng không refresh context. Nó phù hợp cho trường hợp cần kiểm tra hoặc tùy chỉnh giai đoạn trước refresh, ví dụ bean definitions hoặc initializer. Với kiểm thử hành vi bean sau khi ứng dụng đã khởi tạo, dùng `run(...)`.

### 3.2. Context khởi động thất bại

Khi refresh thất bại, runner chuyển một failed context vào callback. Các thao tác đòi hỏi context đang chạy sẽ không dùng được; hãy kiểm tra nguyên nhân qua assertion `getFailure()`:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(BrokenConfiguration.class)
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context)
                    .getFailure()
                    .hasCauseInstanceOf(IllegalStateException.class);
        });
~~~

Đừng chỉ để test ném lỗi chung khi context khởi động thất bại. Kiểm tra cause cụ thể giúp phân biệt lỗi do điều kiện, binding, constructor hoặc dependency.

## 4. Spring gọi destroy callback khi context đóng

Khi context đóng, Spring thực hiện lifecycle shutdown cho các singleton bean đã được quản lý. Những cơ chế thường gặp:

- `DisposableBean.destroy()`.
- Method được đánh dấu `@PreDestroy`.
- Destroy method được khai báo qua `@Bean(destroyMethod = "...")`.
- Các lifecycle component như `Lifecycle` hoặc `SmartLifecycle` được dừng theo contract của chúng.
- Listener và resource cleanup do framework quản lý.

Ví dụ bean giữ một tài nguyên cần đóng:

~~~java
package example.testing;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.DisposableBean;

public final class LifecycleProbe implements DisposableBean {

    private final AtomicInteger closeCount;

    public LifecycleProbe(AtomicInteger closeCount) {
        this.closeCount = closeCount;
    }

    @Override
    public void destroy() {
        closeCount.incrementAndGet();
    }
}
~~~

Nếu bean được đăng ký trong context, `destroy()` được gọi khi context đóng. Trong test, một bộ đếm có thể xác nhận callback đã chạy.

Với bean tự tạo executor, khai báo destroy method rõ ràng:

~~~java
@Bean(destroyMethod = "shutdown")
ExecutorService backgroundExecutor() {
    return Executors.newFixedThreadPool(2);
}
~~~

Với resource do thư viện cung cấp, ưu tiên để bean quản lý lifecycle bằng `AutoCloseable`, `DisposableBean`, `@PreDestroy` hoặc destroy method tương ứng. Tránh tự tạo tài nguyên ở static initializer vì static resource không thuộc lifecycle của context.

**Lưu ý:** Spring chỉ giải phóng các resource mà nó biết cách quản lý. Nếu test tự mở socket, tạo temporary directory hoặc khởi động server bên ngoài context, test phải tự đóng chúng bằng `try-with-resources`, `@AfterEach` hoặc API cleanup tương ứng.

## 5. Kiểm thử rằng mỗi lần run có bean riêng và context được đóng

Ví dụ sau là một test class hoàn chỉnh. Nó chứng minh ba điều:

1. Mỗi `run(...)` tạo instance bean mới.
2. Property của từng biến thể không rò sang runner cơ sở.
3. Destroy callback chạy ngay sau callback của từng lần `run(...)`.

**Tệp:** `src/test/java/example/testing/ContextIsolationTests.java`

~~~java
package example.testing;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class ContextIsolationTests {

    private final AtomicInteger destroyedBeans = new AtomicInteger();

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withBean(
                            LifecycleProbe.class,
                            () -> new LifecycleProbe(destroyedBeans));

    @Test
    void eachRunCreatesFreshBeansAndClosesContextAfterCallback() {
        AtomicReference<LifecycleProbe> firstBean = new AtomicReference<>();

        runner.withPropertyValues("demo.case=first").run(context -> {
            assertThat(context).hasNotFailed();

            LifecycleProbe bean = context.getBean(LifecycleProbe.class);
            firstBean.set(bean);

            assertThat(context.getEnvironment().getProperty("demo.case"))
                    .isEqualTo("first");
            assertThat(destroyedBeans).hasValue(0);
        });

        // run() đã trả về: destroy callback của context thứ nhất đã chạy.
        assertThat(destroyedBeans).hasValue(1);

        runner.withPropertyValues("demo.case=second").run(context -> {
            assertThat(context).hasNotFailed();

            LifecycleProbe secondBean =
                    context.getBean(LifecycleProbe.class);

            assertThat(secondBean).isNotSameAs(firstBean.get());
            assertThat(context.getEnvironment().getProperty("demo.case"))
                    .isEqualTo("second");
            assertThat(destroyedBeans).hasValue(1);
        });

        assertThat(destroyedBeans).hasValue(2);

        // Runner gốc không bị thay đổi bởi hai biến thể property ở trên.
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context.getEnvironment().containsProperty("demo.case"))
                    .isFalse();

            LifecycleProbe thirdBean =
                    context.getBean(LifecycleProbe.class);

            assertThat(thirdBean).isNotSameAs(firstBean.get());
            assertThat(destroyedBeans).hasValue(2);
        });

        assertThat(destroyedBeans).hasValue(3);
    }

    @Test
    void systemPropertyIsRestoredWhenRunCompletes() {
        String original =
                System.getProperty("example.runner.lifecycle.marker");

        runner.withSystemProperties(
                "example.runner.lifecycle.marker=inside")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(System.getProperty(
                            "example.runner.lifecycle.marker"))
                            .isEqualTo("inside");
                });

        assertThat(System.getProperty(
                "example.runner.lifecycle.marker"))
                .isEqualTo(original);
    }

    @Test
    void failedStartupCanBeAssertedInsideCallback() {
        new ApplicationContextRunner()
                .withUserConfiguration(BrokenConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context)
                            .getFailure()
                            .hasCauseInstanceOf(IllegalStateException.class);
                });
    }

    static final class LifecycleProbe implements DisposableBean {

        private final AtomicInteger destroyedBeans;

        LifecycleProbe(AtomicInteger destroyedBeans) {
            this.destroyedBeans = destroyedBeans;
        }

        @Override
        public void destroy() {
            destroyedBeans.incrementAndGet();
        }
    }

    @org.springframework.context.annotation.Configuration(
            proxyBeanMethods = false)
    static class BrokenConfiguration {

        @org.springframework.context.annotation.Bean
        String brokenBean() {
            throw new IllegalStateException("Expected startup failure");
        }
    }
}
~~~

Test đầu tiên dùng một `AtomicInteger` được chia sẻ có chủ đích để đếm destroy callback. Đây là bộ quan sát lifecycle, không phải state của ứng dụng. Mỗi lần run vẫn nhận một `LifecycleProbe` khác nhau; bộ đếm tăng sau khi callback kết thúc.

Test thứ hai xác nhận `withSystemProperties` khôi phục giá trị JVM ban đầu khi context đóng. Test thứ ba minh họa cách assertion startup failure nằm trong callback.

### Kết quả mong đợi

Với Spring Boot 3.3.x, JUnit Jupiter và AssertJ được cấu hình trong test classpath:

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là kết quả mong đợi khi chạy test thành công, không phải log được sinh bởi bài viết này.

Dependency thường dùng:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}
~~~

Chạy bằng Maven:

~~~bash
mvn -Dtest=ContextIsolationTests test
~~~

Hoặc Gradle wrapper:

~~~bash
./gradlew test --tests example.testing.ContextIsolationTests
~~~

## 6. Giữ từng trường hợp kiểm thử độc lập

Một test độc lập phải tự mô tả đầy đủ điều kiện của nó. Không nên yêu cầu test trước chạy thành công để chuẩn bị trạng thái cho test sau.

Ví dụ, không thiết kế hai test phụ thuộc thứ tự:

~~~java
@Test
void firstTestCreatesSharedState() {
    SharedState.currentMode = "enabled";
}

@Test
void secondTestRequiresFirstTest() {
    assertThat(SharedState.currentMode).isEqualTo("enabled");
}
~~~

Test thứ hai có thể thất bại khi chạy riêng, khi JUnit đổi thứ tự hoặc khi test được chạy song song. Thay vào đó, mỗi test tạo state của chính nó:

~~~java
@Test
void enabledModeCreatesService() {
    runner.withPropertyValues("demo.enabled=true").run(context -> {
        assertThat(context).hasSingleBean(MyService.class);
    });
}

@Test
void disabledModeSkipsService() {
    runner.withPropertyValues("demo.enabled=false").run(context -> {
        assertThat(context).doesNotHaveBean(MyService.class);
    });
}
~~~

Các nguyên tắc:

- Mỗi test tự khai báo property, configuration và user bean cần thiết.
- Không phụ thuộc thứ tự thực thi giữa các method.
- Không dùng mutable static field để truyền kết quả từ test này sang test khác.
- Không giữ bean hoặc context của một lần run để tái sử dụng trong lần run tiếp theo.
- Dùng dữ liệu riêng cho từng trường hợp và dọn dữ liệu sau khi test.
- Nếu test có shared fixture, fixture phải được khởi tạo độc lập theo lifecycle của test class/method.
- Assertion phải kiểm tra hành vi của chính trường hợp đang chạy, không dựa vào kết quả đã ghi ở log hoặc file từ lần chạy trước.

### 6.1. Runner field dùng chung không làm test dùng chung context

Khai báo một runner field là cách được Spring Boot khuyến nghị để gom cấu hình cơ sở:

~~~java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(MyAutoConfiguration.class));
~~~

Mỗi test gọi `runner.with...(...).run(...)` với các tùy chỉnh riêng. Runner là cấu hình tái sử dụng; context là instance mới theo từng lần run.

Để test dễ đọc, đặt tên theo hành vi và trường hợp:

- `createsDefaultBeanWhenPropertyMissing`
- `backsOffWhenUserBeanExists`
- `skipsConfigurationWhenOptionalClassIsMissing`
- `closesResourceAfterRun`

Tên như `test1`, `test2` hoặc `works` không nói rõ điều kiện và kết quả đang được kiểm tra.

## 7. Context isolation không đồng nghĩa với process isolation

Đóng một `ApplicationContext` giải phóng những bean và tài nguyên thuộc context đó. Nhưng test vẫn chạy trong cùng JVM và có thể truy cập state nằm ngoài context.

Các nguồn rò rỉ thường gặp:

| State | Được reset khi context đóng? | Cách giữ test độc lập |
| --- | --- | --- |
| Singleton bean thuộc context | Có, khi context đóng và destroy lifecycle hoàn tất | Không giữ reference sang lần run khác |
| Bean có `DisposableBean` hoặc `@PreDestroy` | Callback được gọi khi bean được quản lý và context đóng | Kiểm tra callback; tránh tạo resource ngoài bean lifecycle |
| Property thêm bằng `withPropertyValues` | Chỉ thuộc Environment của runner/context tương ứng | Tạo biến thể runner riêng cho mỗi test |
| System property qua `withSystemProperties` | Runner khôi phục giá trị khi context đóng | Dùng key riêng; tránh chạy song song trên cùng key |
| Static field hoặc static cache | Không | Reset rõ ràng hoặc loại bỏ mutable global state |
| Database bên ngoài | Không | Dùng database/schema/table riêng, transaction rollback hoặc cleanup |
| File và thư mục tạm | Không nếu test tự tạo ngoài context | Dùng thư mục duy nhất và xóa sau test |
| HTTP server hoặc socket tự khởi động | Không nếu không do bean lifecycle quản lý | Đóng server/socket trong cleanup |
| Executor/thread do bean quản lý | Chỉ khi destroy callback thực sự dừng nó | Khai báo destroy method và chờ task kết thúc |
| Container hoặc dịch vụ test bên ngoài | Không | Dùng lifecycle container/test fixture và cleanup riêng |

Một test có thể đóng context đúng cách nhưng vẫn làm test khác thất bại vì để lại row trong database, file tạm hoặc system property. Khi điều tra test flakiness, hãy hỏi state nằm ở context, JVM hay hệ thống bên ngoài.

## 8. Property trong Environment và system property là hai phạm vi khác nhau

Ưu tiên `withPropertyValues` cho cấu hình chỉ cần trong context đang kiểm thử:

~~~java
runner.withPropertyValues(
        "acme.feature.enabled=true",
        "acme.feature.timeout=2s")
        .run(context -> {
            assertThat(context.getEnvironment()
                    .getProperty("acme.feature.enabled"))
                    .isEqualTo("true");
        });
~~~

Property được thêm vào Environment của context. Nó không cần thay đổi `System.getProperties()` của cả JVM.

Dùng `withSystemProperties` khi code cần đọc system property thật:

~~~java
runner.withSystemProperties("demo.external.mode=test")
        .run(context -> {
            assertThat(System.getProperty("demo.external.mode"))
                    .isEqualTo("test");
        });
~~~

Runner khôi phục các system property khi context đóng. Tuy nhiên, trong thời gian callback đang chạy, system property vẫn là state toàn JVM. Nếu hai test song song cùng thay đổi một key, chúng có thể quan sát giá trị của nhau. Khi có thể, dùng property trong Environment thay cho system property; nếu buộc phải dùng system property, tránh song song trên cùng key hoặc cô lập test ở cấp process.

Không dùng trực tiếp `System.setProperty` và quên khôi phục giá trị cũ. Nếu code test phải thay đổi system property bằng tay, dùng `try/finally` để trả về đúng trạng thái trước test.

## 9. Tài nguyên bất đồng bộ cần được dừng trước khi test kết thúc

Một tình huống dễ bị bỏ sót:

~~~java
runner.run(context -> {
    context.getBean(MyService.class).startBackgroundWork();
    // Callback trả về ngay.
});
~~~

Khi callback trả về, context đóng. Nếu background work vẫn đang chạy và còn tham chiếu tới bean hoặc resource của context, nó có thể gặp lỗi hoặc tiếp tục giữ thread sau khi test kết thúc.

Cách xử lý:

1. Đăng ký executor/scheduler như bean có lifecycle.
2. Khi context đóng, dừng nhận task mới.
3. Chờ task đang chạy hoàn tất trong giới hạn hợp lý.
4. Đóng client, pool và resource liên quan.
5. Trong test, đợi kết quả bất đồng bộ trước khi callback trả về.

Ví dụ bean executor có destroy method:

~~~java
@Configuration(proxyBeanMethods = false)
class AsyncConfiguration {

    @Bean(destroyMethod = "shutdown")
    ExecutorService testExecutor() {
        return Executors.newSingleThreadExecutor();
    }
}
~~~

Nếu cần xác nhận task đã dừng, test có thể dùng `CountDownLatch`, `Future.get(timeout, unit)` hoặc API tương đương. Đặt timeout để test không treo vô hạn khi task lỗi.

Không khởi chạy thread nền bằng static initializer hoặc trong constructor của class không do Spring quản lý. Những thread đó không tự động được đóng khi context đóng.

## 10. Dùng @DirtiesContext trong SpringBootTest có khác không?

Cần phân biệt `ApplicationContextRunner` với Spring TestContext Framework.

### Với ApplicationContextRunner

Mỗi lời gọi `run(...)` tạo context mới và đóng context khi callback hoàn tất. Vì vậy, không cần gắn `@DirtiesContext` chỉ để yêu cầu runner đóng context. Việc runner tự đóng là contract sẵn có.

### Với @SpringBootTest và TestContext Framework

Spring TestContext Framework thường cache và tái sử dụng context giữa các test có cùng cấu hình. Caching giúp tránh khởi động lại một ứng dụng lớn cho mọi test method.

Điều đó có nghĩa hai test dùng cùng cấu hình có thể nhận cùng một cached context. Nếu một test làm hỏng trạng thái singleton, thay đổi bean definition hoặc làm context không còn dùng được, có thể đánh dấu context là dirty:

~~~java
@SpringBootTest
class ApplicationIntegrationTests {

    @Test
    @DirtiesContext
    void testThatCorruptsContextState() {
        // Test có chủ đích làm thay đổi state của context.
    }
}
~~~

`@DirtiesContext` đánh dấu context để Spring TestContext loại nó khỏi cache và đóng nó; test sau cần cấu hình tương ứng sẽ được tạo context mới.

Không dùng `@DirtiesContext` cho mọi test chỉ để dọn dữ liệu. Nó có thể làm suite chậm do phải khởi tạo context lại. Với dữ liệu database, file hoặc service bên ngoài, hãy cleanup đúng resource; với context cache, chỉ dùng `@DirtiesContext` khi test thực sự làm context không thể tái sử dụng.

## 11. Parent context và custom context factory

`ApplicationContextRunner.withParent(...)` cho phép test một context con kế thừa bean từ context cha. Đây là trường hợp có chủ đích nhưng không còn hoàn toàn độc lập:

- Bean ở child context thuộc lifecycle của child.
- Bean ở parent context là dependency được chia sẻ.
- Đóng child không thay thế trách nhiệm đóng parent do test tạo và sở hữu.
- Nếu parent chứa mutable singleton, các lần chạy child có thể quan sát chung state đó.

Hãy tạo parent fixture rõ ràng và đóng nó trong lifecycle của test sở hữu parent. Không dùng parent context dùng chung nếu mục tiêu của test là chứng minh mọi bean đều mới.

Nếu tạo runner với custom context factory:

~~~java
ApplicationContextRunner runner =
        new ApplicationContextRunner(
                AnnotationConfigApplicationContext::new);
~~~

Supplier phải trả về **một context instance mới ở mỗi lần được gọi**. Không trả cùng một instance đã refresh hoặc đã đóng cho nhiều lần run. Việc tái sử dụng context instance sẽ phá vỡ giả định độc lập của runner và có thể gây lỗi refresh/closed context.

Với test web, chọn runner phù hợp như `WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner`. `ApplicationContextRunner` mặc định là non-web; không khởi động embedded web server chỉ vì test cần một số bean MVC.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Destroy callback không chạy | Bean không được Spring quản lý, bean chưa được tạo hoặc destroy method không được nhận diện | Đăng ký bean đúng cách và khai báo lifecycle callback |
| Test sau nhìn thấy property của test trước | Gán lại runner cơ sở hoặc thay đổi system property trực tiếp | Dùng biến thể runner mới và `withPropertyValues` |
| Test chạy riêng pass nhưng chạy cả suite fail | Shared static state, file/database dùng chung hoặc test phụ thuộc thứ tự | Tạo fixture riêng và cleanup external state |
| Thread còn tồn tại sau test | Executor hoặc scheduler không được dừng | Đăng ký bean lifecycle và chờ shutdown |
| Context bị đóng nhưng test vẫn dùng bean | Reference bean/context được lưu qua callback | Thực hiện assertion trong callback, không sử dụng sau run |
| Test song song lúc pass lúc fail | Cùng system property, port, file hoặc database row | Dùng resource định danh riêng hoặc khóa đồng bộ phù hợp |
| Context startup fail rồi assertion ném lỗi khó hiểu | Test gọi bean trên failed context | Dùng `hasFailed()` và `getFailure()` |
| `@DirtiesContext` làm suite chậm | Đánh dấu context dirty dù chỉ cần cleanup dữ liệu | Chỉ dùng khi context cache thực sự bị làm hỏng |
| Parent bean bị chia sẻ ngoài ý muốn | Runner dùng chung parent context | Tạo parent riêng hoặc kiểm thử rõ shared-state behavior |

### 12.1. Quy trình điều tra test không độc lập

1. Chạy riêng test bị lỗi để xác nhận nó có tự dựng được context không.
2. Chạy cả test class để tìm phụ thuộc giữa các method.
3. Chạy toàn module để phát hiện static state hoặc resource dùng chung giữa class.
4. Xem bean nào có destroy callback và callback có được gọi sau run không.
5. Kiểm tra thread, port, database, file và system property còn tồn tại sau test.
6. Nếu dùng `@SpringBootTest`, kiểm tra context cache và xem test có thật sự cần `@DirtiesContext` không.
7. Chạy lại test nhiều lần hoặc bật parallel execution có kiểm soát để phát hiện resource collision.

Đừng chữa flakiness bằng cách ép thứ tự test trước khi xác định state nào đang bị chia sẻ. Thứ tự chỉ che vấn đề; nó không giải phóng resource.

## 13. Checklist cho mỗi test dùng ApplicationContextRunner

- [ ] Runner cơ sở được khai báo `private final`.
- [ ] Mỗi trường hợp dùng lời gọi `run(...)` riêng.
- [ ] Property và user configuration được thêm bằng runner variant cục bộ.
- [ ] Assertion và việc dùng bean diễn ra trong callback.
- [ ] Không lưu context hoặc bean để sử dụng sau khi callback kết thúc.
- [ ] Bean quản lý resource có destroy callback rõ ràng.
- [ ] Background thread/executor được dừng và task được chờ hoàn tất.
- [ ] System property được khôi phục; tránh nhiều test song song thay cùng key.
- [ ] Database, file, socket và container bên ngoài có cleanup riêng.
- [ ] Test chạy riêng và chạy trong suite đều không phụ thuộc thứ tự.
- [ ] Startup failure được kiểm tra bằng `hasFailed()` và `getFailure()`.
- [ ] Chỉ dùng `@DirtiesContext` khi test làm context cache không thể tái sử dụng.

## 14. Tự kiểm tra kiến thức

1. Mỗi lần gọi `ApplicationContextRunner.run(...)` có dùng lại context trước đó không?  
   **Đáp án:** Không. Runner tạo và refresh một context mới cho callback, rồi đóng context khi callback hoàn tất.

2. Vì sao runner field có thể dùng chung giữa nhiều test?  
   **Đáp án:** Runner lưu cấu hình; các method `with...` trả về runner mới và mỗi `run(...)` tạo context riêng.

3. Khi nào `DisposableBean.destroy()` được gọi?  
   **Đáp án:** Khi bean do Spring quản lý được hủy trong quá trình context đóng.

4. Context đóng có tự xóa static field hoặc database row không?  
   **Đáp án:** Không. Static state và dữ liệu bên ngoài cần cleanup riêng.

5. `withPropertyValues` khác `withSystemProperties` như thế nào?  
   **Đáp án:** Một bên thêm property vào Environment của context; bên kia thay system property toàn JVM trong thời gian run và khôi phục khi context đóng.

6. Có nên gọi `context.close()` bên trong callback thông thường không?  
   **Đáp án:** Không cần. Runner đóng context sau callback; đóng sớm có thể làm assertion tiếp theo không sử dụng được context.

7. `@DirtiesContext` có cần cho mỗi test ApplicationContextRunner không?  
   **Đáp án:** Không. Runner đã đóng context sau mỗi lần run; `@DirtiesContext` dành cho context được Spring TestContext cache khi test làm context đó không thể tái sử dụng.

8. Vì sao test vẫn có thể phụ thuộc thứ tự dù mỗi lần run tạo context mới?  
   **Đáp án:** Vì state có thể nằm ngoài context: static field, system property, file, database, port hoặc background thread.

9. Khi callback trả về nhưng task bất đồng bộ chưa xong, chuyện gì có thể xảy ra?  
   **Đáp án:** Context đóng trong lúc task vẫn dùng bean/resource, dẫn đến lỗi hoặc rò rỉ thread. Test phải đợi task hoàn tất trước khi callback kết thúc.

## Tài liệu chính thức

- [Spring Boot 3.3 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): context non-web và context factory mặc định.
- [Spring Boot 3.3 — AbstractApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/AbstractApplicationContextRunner.html): `run`, `prepare`, `withPropertyValues`, `withSystemProperties`, `withBean` và các runner customization.
- [Spring Boot 3.3 — Testing Your Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): dùng ApplicationContextRunner để kiểm tra từng tổ hợp user configuration, Environment và condition.
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): cách TestContext Framework cache, tái sử dụng và đóng context.
- [Spring Framework — @DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html): khi nào context được đánh dấu dirty, loại khỏi cache và tạo lại.

**Ghi nhớ:** `ApplicationContextRunner` bảo đảm một context mới cho mỗi lần `run(...)` và tự đóng context sau callback. Điều đó giải phóng bean/resource thuộc context, nhưng không tự xóa state toàn JVM hoặc dữ liệu bên ngoài. Để test thực sự độc lập, mỗi trường hợp phải tự cấu hình, tự kiểm tra, quản lý lifecycle resource và cleanup mọi state nằm ngoài context.

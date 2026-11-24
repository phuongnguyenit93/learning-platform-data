# Kiểm thử quan sát lồng nhau, lỗi, sự kiện và đóng Scope

Micrometer Observation thường được lồng theo cấu trúc của một thao tác: HTTP request gọi service, service truy vấn database hoặc gọi dependency, rồi các thao tác con hoàn tất trước thao tác cha. Một test chỉ xác nhận code trả về đúng kết quả chưa đủ để chứng minh telemetry đúng. Cần kiểm tra parent-child relationship, event, lỗi được gắn vào đúng Observation và Scope được đóng để khôi phục context trước đó.

Micrometer cung cấp module `micrometer-observation-test` với `TestObservationRegistry`. Registry này ghi lại Observation để kiểm tra bằng AssertJ và tự đăng ký `ObservationValidator` nhằm phát hiện các trình tự lifecycle không hợp lệ. Có thể kết hợp nó với test handler riêng để kiểm tra quan hệ cha-con và trạng thái current Observation.

## Mục tiêu

Sau bài học, bạn có thể:

- Tạo và kiểm thử Observation cha-con.
- Xác minh Observation con được gắn parent khi được tạo trong Scope của parent.
- Gắn parent tường minh khi không thể tạo child trong Scope hiện tại.
- Kiểm tra lỗi và event được ghi vào đúng Observation.
- Phân biệt lỗi của child với lỗi lan truyền lên parent.
- Kiểm tra current Observation được khôi phục sau khi Scope con đóng.
- Đảm bảo Scope được đóng theo thứ tự LIFO và trên đúng thread.
- Dùng TestObservationRegistry và ObservationValidator.
- Kiểm tra trường hợp exception xảy ra giữa các Scope lồng nhau.
- Kiểm thử ranh giới bất đồng bộ và tránh phụ thuộc ThreadLocal ngầm.

## Vì sao phải kiểm thử Observation lồng nhau?

Một request thường tạo ra nhiều Observation có quan hệ nhân quả:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Payment service]
    B --> C[Database query]
    B --> D[Payment gateway call]
    D --> E[Retry event]
    C --> F[Child hoàn tất]
    E --> G[Child gateway hoàn tất]
    F --> H[Parent tiếp tục]
    G --> H
    H --> I[HTTP request hoàn tất]
~~~

Nếu parent-child relationship sai, trace có thể hiển thị các span ngang hàng dù một thao tác thực sự được gọi bên trong thao tác khác. Nếu Scope con không được đóng, current Observation có thể vẫn trỏ tới child khi code cha tiếp tục chạy. Nếu lỗi chỉ được ghi ở parent hoặc chỉ ở child ngoài ý muốn, người vận hành sẽ khó xác định thao tác nào thực sự thất bại.

Một bộ test nên xác minh ít nhất bốn khía cạnh:

| Khía cạnh | Điều cần xác minh |
|---|---|
| Quan hệ lồng nhau | Child có đúng parent và được tạo trong đúng phạm vi không? |
| Error | Exception được ghi vào Observation phát sinh lỗi; việc lan truyền lên parent đúng với cách xử lý exception |
| Event | Event xuất hiện trong context của Observation tương ứng |
| Scope | Child trở thành current khi mở Scope, parent được khôi phục khi child đóng, cuối cùng không còn current Observation |

## Chuẩn bị TestObservationRegistry

Micrometer cung cấp dependency kiểm thử riêng. Nếu dự án quản lý phiên bản bằng Micrometer BOM hoặc Spring Boot dependency management, không cần chỉ định version riêng:

~~~gradle
dependencies {
    testImplementation("io.micrometer:micrometer-observation-test")
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-observation-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Các ví dụ dùng JUnit 5 và AssertJ. Trong Spring Boot, các thư viện test thường đã cung cấp hai dependency này; nếu dự án Java thuần, hãy khai báo JUnit Jupiter và AssertJ theo dependency management của dự án.

Tạo registry trong từng test:

~~~java
import io.micrometer.observation.tck.TestObservationRegistry;

TestObservationRegistry registry = TestObservationRegistry.create();
~~~

`TestObservationRegistry` ghi lại context của từng Observation. Nó cũng đăng ký `ObservationValidator` tự động để kiểm tra những lỗi như:

- Gọi stop trước start.
- Gọi stop nhiều lần.
- Ghi event hoặc error sau khi Observation đã stop.
- Vi phạm các quy tắc lifecycle mà validator hỗ trợ.

Khi validator phát hiện lỗi, nó ném `InvalidObservationException` kèm thông tin lỗi và lịch sử callback. Điều này giúp test phát hiện instrumentation sai ngay tại vị trí tạo ra lỗi.

TestObservationRegistry không phải MeterRegistry và không tự tạo Timer, Counter hay span của tracing backend. Nó tập trung kiểm thử Observation lifecycle, context, key-values và event. Muốn kiểm tra meter, hãy thêm SimpleMeterRegistry cùng DefaultMeterObservationHandler; muốn kiểm tra span, dùng tracing test exporter hoặc span handler tương ứng.

## Tạo Observation cha và con

Khi tạo Observation trong Scope hiện tại, Micrometer tự gắn Observation hiện tại làm parent nếu context của child chưa có parent. Vì vậy, mẫu phổ biến là tạo child bên trong phần xử lý của parent:

~~~java
Observation parent = Observation.createNotStarted(
    "http.server.requests",
    registry
);

parent.observe(() -> {
    Observation child = Observation.createNotStarted(
        "db.query",
        registry
    );

    child.observe(() -> repository.findById("order-42"));
});
~~~

Khi parent đang chạy trong Scope, `registry.getCurrentObservation()` trả về parent. Child được tạo trong khoảng đó sẽ nhận parent từ current Observation. Tracing handler có thể dùng quan hệ này để tạo span con của span cha.

Nếu có sẵn parent nhưng không thể tạo child trong Scope của parent, có thể gắn parent tường minh:

~~~java
Observation child = Observation.createNotStarted(
    "db.query",
    registry
).parentObservation(parent);
~~~

`parentObservation(parent)` đặt quan hệ cha-con trực tiếp. Cách này hữu ích khi việc tạo Observation con xảy ra ở một điểm khác trong code hoặc sau khi Scope của parent đã đóng. Nó không tự động truyền ThreadLocal hoặc mở Scope của parent trên thread hiện tại.

### Parent-child và Scope là hai khái niệm khác nhau

Parent-child mô tả quan hệ giữa hai Observation. Scope mô tả Observation nào đang current trên thread tại một thời điểm.

| Thao tác | Tác động |
|---|---|
| Tạo child trong Scope parent | Child có thể tự nhận parent từ current Observation |
| Gọi `child.parentObservation(parent)` | Gắn quan hệ cha-con tường minh |
| Mở Scope child | Child trở thành current trên thread hiện tại |
| Đóng Scope child | Current Observation trước đó được khôi phục |
| Stop child | Kết thúc lifecycle của child; không tự stop parent |
| Stop parent | Kết thúc lifecycle của parent; không thay thế việc đóng Scope |

Không nên suy luận rằng child có parent thì Scope parent luôn đang mở. Cũng không nên giữ Scope mở chỉ để biểu diễn quan hệ parent-child nếu API `parentObservation` đã đáp ứng yêu cầu đó.

## Kiểm thử nested Observation, event và lỗi của child

Ví dụ sau tạo một HTTP Observation cha và một database Observation con. Child phát event retry rồi ném exception. Parent bắt exception để tiếp tục xử lý, do đó lỗi thuộc về child và không làm parent chuyển thành lỗi.

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

class NestedObservationTest {

    @Test
    void recordsChildErrorAndEventAndRestoresParent() {
        TestObservationRegistry registry = TestObservationRegistry.create();

        Observation parent = Observation.createNotStarted(
            "http.server.requests",
            registry
        );

        parent.observe(() -> {
            assertThat(registry.getCurrentObservation()).isSameAs(parent);

            Observation child = Observation.createNotStarted(
                "db.query",
                registry
            );

            assertThat(child.getContext().getParentObservation())
                .isSameAs(parent);

            IllegalStateException failure =
                new IllegalStateException("database unavailable");

            assertThrows(IllegalStateException.class, () ->
                child.observe(() -> {
                    child.event(Observation.Event.of("db.retry"));
                    throw failure;
                })
            );

            // Scope của child đã đóng; parent trở lại thành current.
            assertThat(registry.getCurrentObservation()).isSameAs(parent);
        });

        // Scope của parent cũng đã đóng sau khi observe hoàn tất.
        assertThat(registry)
            .doesNotHaveAnyRemainingCurrentObservation()
            .hasAnObservation(context -> {
                context.hasNameEqualTo("http.server.requests")
                    .hasBeenStarted()
                    .hasBeenStopped()
                    .doesNotHaveError();
            })
            .hasAnObservation(context -> {
                context.hasNameEqualTo("db.query")
                    .hasBeenStarted()
                    .hasBeenStopped()
                    .hasError()
                    .hasEvent("db.retry");
            });
    }
}
~~~

Test này xác minh nhiều điều trong cùng một luồng:

1. Parent là current trong khi body của parent chạy.
2. Child được tạo trong Scope parent nên nhận đúng parent.
3. Event retry được phát trên child.
4. Exception được ghi nhận trên child.
5. Child kết thúc và Scope của child đóng.
6. Parent được khôi phục thành current.
7. Parent kết thúc bình thường vì exception của child đã được bắt.
8. Sau khi parent kết thúc, registry không còn current Observation.

Các assertion `hasBeenStarted()` và `hasBeenStopped()` kiểm tra lifecycle. `hasError()` và `doesNotHaveError()` phân biệt lỗi ở child với kết quả của parent. `hasEvent()` xác nhận event nằm trong context của Observation tương ứng.

## Khi exception lan truyền, parent cũng có thể ghi nhận lỗi

Nếu exception của child không được bắt trong body của parent, exception đi ra khỏi body parent. Khi đó cả child và parent đều có thể ghi nhận cùng exception ở cấp Observation của chúng:

~~~java
@Test
void propagatingChildFailureMarksParentAndChildAsFailed() {
    TestObservationRegistry registry = TestObservationRegistry.create();

    Observation parent = Observation.createNotStarted(
        "http.server.requests",
        registry
    );

    assertThrows(IllegalArgumentException.class, () ->
        parent.observe(() -> {
            Observation child = Observation.createNotStarted(
                "payment.gateway",
                registry
            );

            child.observe(() -> {
                throw new IllegalArgumentException("gateway rejected request");
            });
        })
    );

    assertThat(registry)
        .doesNotHaveAnyRemainingCurrentObservation()
        .hasAnObservation(context -> {
            context.hasNameEqualTo("http.server.requests")
                .hasError()
                .hasBeenStopped();
        })
        .hasAnObservation(context -> {
            context.hasNameEqualTo("payment.gateway")
                .hasError()
                .hasBeenStopped();
        });
}
~~~

Đây là hành vi hợp lý khi lỗi của child làm toàn bộ request thất bại. Nếu ứng dụng có fallback và xử lý được lỗi child, hãy bắt exception tại ranh giới phù hợp để parent tiếp tục với kết quả thành công hoặc degraded theo nghiệp vụ.

Không viết test mặc định rằng mọi lỗi child đều phải làm parent lỗi. Kết quả phụ thuộc exception có được xử lý trong body của parent hay không.

## Kiểm tra event được gắn vào đúng Observation

Event biểu diễn một mốc trong lifecycle, chẳng hạn cache miss, retry hoặc message acknowledged. Event được phát trên một Observation cụ thể:

~~~java
Observation child = Observation.createNotStarted("inventory.lookup", registry);

child.observe(() -> {
    child.event(Observation.Event.of("cache.miss"));
    child.event(Observation.Event.of("remote.fetch.started"));
    inventoryClient.fetch("sku-100");
});
~~~

Test nên kiểm tra event thuộc đúng child:

~~~java
assertThat(registry)
    .hasAnObservation(context -> {
        context.hasNameEqualTo("inventory.lookup")
            .hasEvent("cache.miss")
            .hasEvent("remote.fetch.started");
    });
~~~

Nếu parent và child cùng phát event có tên giống nhau, hãy kiểm tra từng Observation riêng. Không chỉ xác minh event tồn tại ở đâu đó trong registry; một event bị gắn nhầm vào parent có thể khiến trace hiển thị sai mốc thời gian.

Tên event nên ổn định và có cardinality thấp. Tránh event name chứa request ID, order ID, URL động hoặc exception message. Chi tiết riêng của một lần gọi nên được lưu ở span attribute hoặc log theo chính sách dữ liệu.

## Kiểm tra đóng Scope theo thứ tự LIFO

Scope được quản lý theo stack trên thread. Nếu mở Scope parent rồi mở Scope child, phải đóng child trước parent:

~~~java
Observation parent = Observation.start("http.server.requests", registry);

try (Observation.Scope parentScope = parent.openScope()) {
    Observation child = Observation.start("db.query", registry);

    try (Observation.Scope childScope = child.openScope()) {
        // Child là current trong đoạn này.
        repository.findById("order-42");
    }
    finally {
        child.stop();
    }

    // Scope child đã đóng; parent lại là current.
}
finally {
    parent.stop();
}
~~~

Dùng try-with-resources để bảo đảm Scope được đóng cả khi code ném exception. Gọi stop trong finally để hoàn tất Observation. Hai thao tác có trách nhiệm riêng: close khôi phục current context, còn stop kết thúc lifecycle.

Micrometer 1.17 trở lên cung cấp các tùy chọn kiểm tra Scope trong TestObservationRegistry builder. Có thể bật xác minh đóng theo thứ tự ngược với thứ tự mở và xác minh Scope được mở/đóng trên cùng thread:

~~~java
TestObservationRegistry registry = TestObservationRegistry.builder()
    .validateScopesClosedInReverseOrderOfOpening(true)
    .validateScopesOpenedAndClosedOnTheSameThread(true)
    .build();
~~~

Hai tùy chọn này giúp phát hiện các lỗi khó nhìn thấy trong test thông thường:

- Đóng Scope parent trong khi Scope child vẫn còn mở.
- Mở Scope trên một thread rồi đóng nó trên thread khác.
- Để current Observation còn sót lại sau khi thao tác kết thúc.

Các tùy chọn builder này có từ Micrometer 1.17. Với phiên bản cũ hơn, vẫn có thể kiểm tra current Observation và tự viết assertion cho stack Scope, nhưng không gọi những builder method chưa có trong dependency của dự án.

## Test Scope restoration khi child ném exception

Một test chuyên biệt có thể xác minh parent được khôi phục ngay cả khi child lỗi:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ObservationScopeTest {

    @Test
    void restoresParentScopeWhenChildFails() {
        TestObservationRegistry registry = TestObservationRegistry.builder()
            .validateScopesClosedInReverseOrderOfOpening(true)
            .validateScopesOpenedAndClosedOnTheSameThread(true)
            .build();

        Observation parent = Observation.start(
            "http.server.requests",
            registry
        );

        try (Observation.Scope parentScope = parent.openScope()) {
            assertThat(registry.getCurrentObservation()).isSameAs(parent);

            Observation child = Observation.start("db.query", registry);
            assertThat(child.getContext().getParentObservation()).isSameAs(parent);

            try (Observation.Scope childScope = child.openScope()) {
                assertThat(registry.getCurrentObservation()).isSameAs(child);
                throw new IllegalStateException("query failed");
            }
            catch (IllegalStateException exception) {
                child.error(exception);
            }
            finally {
                child.stop();
            }

            assertThat(registry.getCurrentObservation()).isSameAs(parent);
        }
        finally {
            parent.stop();
        }

        assertThat(registry.getCurrentObservation()).isNull();
        assertThat(registry)
            .doesNotHaveAnyRemainingCurrentObservation();
    }
}
~~~

Trong test này, exception thoát khỏi Scope child khiến try-with-resources đóng child scope. Khối catch báo lỗi cho child và xử lý lỗi tại ranh giới child; finally stop child. Luồng tiếp tục bên trong parent scope, nơi assertion xác nhận current Observation đã trở lại parent. Khi body parent kết thúc, parent scope đóng và finally stop parent. Parent không nhận error signal vì exception đã được xử lý trong body của nó.

Test này kiểm tra cleanup ở nhiều tầng. Khi thay đổi code, nếu quên đóng child scope hoặc parent scope, validator hoặc assertion current Observation sẽ phát hiện.

## Dùng TestObservationRegistry để phát hiện lifecycle không hợp lệ

`ObservationValidator` được đăng ký tự động trong TestObservationRegistry. Nó kiểm tra trình tự lifecycle như start, error, event và stop. Một số thao tác sau là không hợp lệ:

| Trình tự sai | Lý do |
|---|---|
| stop trước start | Observation chưa bắt đầu nhưng đã kết thúc |
| stop hai lần | Một lifecycle bị kết thúc nhiều lần |
| error sau stop | Đã báo lỗi sau khi Observation kết thúc |
| event sau stop | Event phát ra ngoài lifecycle |
| Scope đóng sai thứ tự khi bật kiểm tra LIFO | Stack current Observation bị phá vỡ |
| Scope mở và đóng ở hai thread khi bật kiểm tra thread | Scope gắn với thread-local context |

Khi validator phát hiện lỗi, InvalidObservationException chứa thông báo và lịch sử thao tác liên quan. Dùng stack trace của exception để tìm instrumentation đang phát lifecycle sai.

Không cần tự viết một validator đầy đủ cho mỗi test. Dùng validator có sẵn để kiểm tra hợp đồng lifecycle; chỉ viết handler riêng khi cần xác minh metadata hoặc hành vi ứng dụng cụ thể.

## Kiểm thử bằng TestObservationRegistry và SimpleMeterRegistry cùng lúc

TestObservationRegistry xác minh Observation; SimpleMeterRegistry xác minh meter. Có thể đăng ký cả hai loại handler trên cùng registry:

~~~java
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ObservationMetricsTest {

    @Test
    void recordsTimerForChildObservation() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        TestObservationRegistry observations = TestObservationRegistry.create();

        observations.observationConfig().observationHandler(
            DefaultMeterObservationHandler.builder(meters).build()
        );

        Observation parent = Observation.createNotStarted(
            "http.server.requests",
            observations
        );

        parent.observe(() -> {
            Observation child = Observation.createNotStarted(
                "db.query",
                observations
            );

            child.observe(() -> repositoryCall());
        });

        Timer childTimer = meters.get("db.query").timer();

        assertThat(childTimer.count()).isEqualTo(1);
        assertThat(observations)
            .doesNotHaveAnyRemainingCurrentObservation()
            .hasAnObservation(context ->
                context.hasNameEqualTo("db.query")
                    .hasBeenStarted()
                    .hasBeenStopped()
            );

        meters.close();
    }

    private void repositoryCall() {
        // Giả lập thao tác database.
    }
}
~~~

Timer của child được tạo với tên Observation tương ứng. Parent cũng có thể tạo Timer riêng nếu DefaultMeterObservationHandler nhận cả hai Observation. Test nên kiểm tra từng meter theo tên và tag dự kiến, tránh chỉ đếm tổng số meter trong registry.

TestObservationRegistry không thay thế kiểm thử exporter. Nếu cần xác minh Prometheus naming, OTLP payload hoặc span export, hãy thêm integration test cho registry/exporter tương ứng.

## Kiểm tra parent-child trong tracing

TestObservationRegistry xác nhận quan hệ parent ở Observation context. Nó không chứng minh tracing backend đã tạo đúng span parent-child. Khi dùng Micrometer Tracing, hãy kiểm tra thêm span bằng test exporter hoặc span handler của bridge đang dùng.

Các assertion nên bao gồm:

- Span của child có parent span ID đúng với span của parent.
- Span child bắt đầu và kết thúc trong khoảng thời gian hợp lý của parent.
- Error status được gắn vào span child khi child thất bại.
- Parent có error status khi exception lan truyền ra khỏi parent.
- Event được ghi thành span event ở đúng span.
- Không tạo span trùng do instrumentation lồng nhau hai lần.

Tên class test exporter phụ thuộc tracing bridge (Brave hoặc OpenTelemetry). Giữ test ở lớp abstraction nếu có thể và chỉ dùng implementation cụ thể trong test tích hợp.

## Kiểm thử qua ranh giới bất đồng bộ

Observation Scope dựa trên current context của thread. Khi code chuyển sang executor hoặc thread khác, current Observation không tự động xuất hiện ở thread mới chỉ vì task được tạo bên trong parent Scope.

Một test nên xác minh hai trường hợp:

1. Không truyền context: thread worker không có current Observation của thread gọi.
2. Có cơ chế truyền context: worker nhận đúng parent hoặc context snapshot, tạo child phù hợp và đóng Scope trên chính worker thread.

Nếu cần gắn parent tường minh, có thể tạo child rồi gọi `parentObservation(parent)`. Nếu cần current context và các ThreadLocal liên quan được khôi phục trong worker, dùng Micrometer Context Propagation với TaskDecorator hoặc ContextSnapshot phù hợp với executor.

Không mở Scope ở thread A rồi đóng ở thread B. Bật kiểm tra same-thread trong TestObservationRegistry để phát hiện lỗi này. Scope phải được đóng trên thread đã mở nó; context propagation cần khôi phục context trong thread đích theo đúng vòng đời của task.

## Ma trận test nên có

| Kịch bản | Assertion quan trọng |
|---|---|
| Parent và child thành công | Cả hai start/stop; child có parent; current trở về parent sau child |
| Child phát event | Event xuất hiện trên child |
| Child lỗi và được parent bắt | Child có error; parent không có error |
| Child lỗi và lan truyền | Child và parent đều có error |
| Exception trong Scope child | Child Scope đóng; parent Scope được khôi phục |
| Exception trong Scope parent | Parent Scope đóng; registry không còn current |
| Nhiều Scope lồng nhau | Đóng theo LIFO |
| Scope qua thread | Mở/đóng cùng thread hoặc dùng context propagation |
| Observation bị predicate từ chối | Không có lifecycle Observation thực, không mong đợi handler được gọi |
| Meter handler được đăng ký | Timer của parent/child có count và tag đúng |
| Tracing handler được đăng ký | Span parent-child và error/event đúng |

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Tạo child ngoài parent Scope nhưng không gắn parent | Trace child trở thành span độc lập | Tạo trong Scope parent hoặc gọi parentObservation |
| Nghĩ parent-child đồng nghĩa với Scope lồng nhau | Test bỏ sót lỗi current context | Kiểm tra parent relationship và current Observation riêng |
| Bắt exception ở sai tầng | Parent bị đánh dấu lỗi dù nghiệp vụ đã fallback, hoặc lỗi child bị mất | Đặt catch tại ranh giới xử lý nghiệp vụ |
| Chỉ kiểm tra exception được ném ra | Không biết Observation nào ghi error | Assert hasError trên từng Observation |
| Chỉ kiểm tra event tồn tại | Event có thể bị gắn nhầm vào parent | Assert event trên Observation cụ thể |
| Quên đóng Scope | Current Observation rò sang thao tác kế tiếp | Dùng try-with-resources |
| Đóng parent trước child | Scope stack sai thứ tự | Đóng theo LIFO |
| Mở Scope trên một thread, đóng ở thread khác | ThreadLocal/context bị sai | Truyền context và mở/đóng Scope trong cùng worker |
| Dùng TestObservationRegistry như MeterRegistry | Không xác minh được Timer hoặc Counter | Kết hợp SimpleMeterRegistry và meter handler |
| Nghĩ TestObservationRegistry xác minh span export | Bỏ sót lỗi bridge/exporter | Thêm test tracing với exporter giả |
| Tạo cùng Observation nhiều lần trong test | Context và thứ tự test khó xác định | Tạo registry riêng cho mỗi test |
| Predicate vô tình từ chối Observation | Không có callback dù handler đã đăng ký | Kiểm tra predicate và tên Observation |
| Reuse Observation đã stop | Lifecycle validator báo lỗi hoặc telemetry sai | Tạo Observation mới cho mỗi lần thao tác |

## Ghi nhớ

- Observation được tạo trong Scope hiện tại tự nhận current Observation làm parent nếu chưa có parent khác.
- Có thể gọi parentObservation để gắn parent tường minh khi không tạo child trong Scope parent.
- Parent-child relationship và Scope current là hai điều cần kiểm tra riêng.
- TestObservationRegistry ghi lại context và cung cấp AssertJ assertions cho name, event, key-values, error, start và stop.
- ObservationValidator được đăng ký tự động để phát hiện lifecycle sai.
- Khi child error được bắt trong parent, child có thể lỗi trong khi parent vẫn thành công.
- Khi exception lan ra ngoài parent, parent cũng có thể ghi nhận cùng lỗi.
- Scope phải được đóng theo LIFO và trên cùng thread đã mở nó.
- Dùng try-with-resources để bảo đảm Scope đóng khi exception xảy ra.
- TestObservationRegistry kiểm tra Observation; dùng SimpleMeterRegistry để kiểm tra meter và tracing test exporter để kiểm tra span.
- Context không tự truyền qua thread boundary; cần Context Propagation hoặc gắn parent và mở Scope phù hợp ở worker.

Một bài kiểm thử Observation tốt xác minh cả dữ liệu lẫn vòng đời: child thuộc đúng parent, lỗi và event xuất hiện đúng nơi, Scope luôn được đóng và current context được khôi phục. Khi các điều kiện này được kiểm tra tự động, trace và metrics có thể phản ánh đúng cấu trúc thực thi của ứng dụng.

## Tài liệu tham khảo

- [Micrometer: Testing Observations](https://docs.micrometer.io/micrometer/reference/observation/testing.html) — TestObservationRegistry, AssertJ assertions và ObservationValidator.
- [Micrometer: Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html) — Observation lifecycle, Scope và ObservationRegistry.
- [Micrometer: Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html) — cách tạo Observation, mở Scope, xử lý error và handler.
- [Observation API](https://javadoc.io/doc/io.micrometer/micrometer-observation/latest/io/micrometer/observation/Observation.html) — parentObservation, observe, event, error và Scope.
- [ObservationRegistry API](https://javadoc.io/doc/io.micrometer/micrometer-observation/latest/io/micrometer/observation/ObservationRegistry.html) — current Observation và current Scope.
- [Micrometer Tracing: Configuring with Micrometer Observation](https://docs.micrometer.io/tracing/reference/configuring.html) — liên kết Observation Scope với span và ThreadLocal.


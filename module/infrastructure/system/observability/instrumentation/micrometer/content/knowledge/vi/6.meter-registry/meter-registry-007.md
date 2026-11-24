# Metrics.globalRegistry và tác động của trạng thái tĩnh dùng chung

Micrometer cung cấp hai cách phổ biến để ứng dụng ghi nhận metrics: nhận `MeterRegistry` qua dependency injection, hoặc gọi các phương thức tĩnh trong lớp `Metrics`. Các phương thức tĩnh này ghi số liệu vào `Metrics.globalRegistry`, một `CompositeMeterRegistry` dùng chung.

Sự tiện lợi của API tĩnh đi kèm một hệ quả kiến trúc: registry có trạng thái dùng chung trong phạm vi class loader. Những thành phần cùng sử dụng lớp `Metrics` có thể cùng ghi vào một registry toàn cục, và mọi registry con được gắn vào đó có thể nhận cùng các meter. Điều này ảnh hưởng đến vòng đời ứng dụng, cấu hình, kiểm thử, nhiều Spring context và khả năng cô lập số liệu.

## 1. Metrics.globalRegistry là gì?

`Metrics.globalRegistry` là một instance tĩnh của `CompositeMeterRegistry`. Lớp `Metrics` cung cấp các phương thức tiện ích như `Metrics.counter(...)`, `Metrics.timer(...)`, `Metrics.summary(...)` và `Metrics.gauge(...)`. Các phương thức này chuyển tiếp việc đăng ký và ghi nhận meter đến global registry.

Có thể hình dung luồng dữ liệu:

```text
Module A ── Metrics.counter(...) ──┐
Module B ── Metrics.timer(...) ────┼──> Metrics.globalRegistry
Module C ── Metrics.gauge(...) ────┘              |
                                                  |
                              ┌───────────────────┼───────────────────┐
                              v                   v                   v
                       Prometheus registry   OTLP registry       Simple registry
                              |                   |                   |
                              v                   v                   v
                         Prometheus          Metrics backend       Test
```

Global registry đóng vai trò điểm điều phối. Nó không tự biến dữ liệu thành một backend cụ thể. Các registry con mới là nơi chuyển meter sang định dạng hoặc hệ thống giám sát tương ứng.

Ví dụ, một ứng dụng có thể gắn registry Prometheus vào global registry:

```java
Metrics.addRegistry(prometheusMeterRegistry);

Metrics.counter("orders.created").increment();
Metrics.timer("orders.payment.duration")
    .record(() -> paymentGateway.charge(order));
```

Các lời gọi tĩnh sau đó được chuyển qua global registry. Nếu có nhiều registry con, composite có thể chuyển cùng meter đến từng registry đã gắn.

## 2. Thêm và gỡ registry con

Micrometer cung cấp các API để quản lý registry con:

- `Metrics.addRegistry(registry)`: thêm một registry vào global registry.
- `Metrics.removeRegistry(registry)`: gỡ registry đã thêm khỏi global registry.
- `Metrics.globalRegistry`: truy cập trực tiếp composite registry dùng chung.

Ví dụ tối giản, giả sử ứng dụng đã tạo và cấu hình registry backend:

```java
Metrics.addRegistry(registry);

Metrics.counter("jobs.started").increment();
```

Trong ứng dụng thật, việc gắn registry nên diễn ra một lần trong giai đoạn khởi tạo. Khi ứng dụng dừng, cần gỡ registry khỏi global registry trước khi registry được đóng, để các lời gọi tĩnh không tiếp tục hướng tới một đích đã ngừng hoạt động.

```java
public final class GlobalMetricsLifecycle {
    private final MeterRegistry registry;

    public GlobalMetricsLifecycle(MeterRegistry registry) {
        this.registry = registry;
    }

    public void start() {
        Metrics.addRegistry(registry);
    }

    public void stop() {
        Metrics.removeRegistry(registry);
    }
}
```

Đây là ví dụ minh họa vòng đời. Trong Spring, hãy để container quản lý việc khởi tạo và đóng registry, đồng thời bảo đảm thao tác detach được thực hiện trước khi registry đóng. Không gọi add/remove trên mỗi request vì việc thay đổi tập registry đích ở đường xử lý nóng gây khó kiểm soát và tạo thêm chi phí vận hành.

### Điều gì xảy ra khi chưa có registry con?

Một `CompositeMeterRegistry` có thể tồn tại trước khi registry backend được gắn vào. Khi chưa có registry con, các meter được ghi qua composite không được xuất đến backend nào; thao tác ghi nhận không phải một hàng đợi lưu trữ để phát lại sau này.

Nếu backend được gắn sau đó, các meter đã đăng ký trong composite có thể được kết nối với registry mới để nhận các lần ghi nhận tiếp theo. Những sự kiện xảy ra trước thời điểm gắn registry không thể được khôi phục từ một bộ đệm lịch sử của global registry.

Vì vậy, hãy hoàn tất cấu hình registry đích trước khi ứng dụng bắt đầu xử lý công việc cần quan sát. Đừng dựa vào giả định rằng global registry sẽ lưu lại mọi lần tăng counter trong lúc chưa có backend.

## 3. Trạng thái tĩnh được chia sẻ trong phạm vi nào?

Từ khóa `static` có nghĩa trạng thái thuộc về lớp, thay vì thuộc về từng object được tạo ra. Với `Metrics.globalRegistry`, các thành phần tham chiếu đến cùng định nghĩa lớp Micrometer trong cùng class loader sẽ sử dụng chung global registry.

Trong một ứng dụng Java thông thường, điều đó có nghĩa:

- Nhiều service có thể ghi vào cùng global registry.
- Nhiều package hoặc module có thể đăng ký meter với cùng tên.
- Các Spring application context trong cùng class loader có thể cùng tác động đến registry.
- Một thư viện gọi `Metrics.counter(...)` có thể tạo số liệu mà không biết registry nào đang nhận dữ liệu.
- Cấu hình hoặc thay đổi vòng đời ở một thành phần có thể ảnh hưởng các thành phần khác.

Phạm vi chia sẻ phụ thuộc class loader. Hai ứng dụng được nạp bởi các class loader tách biệt có thể có hai bản static state khác nhau, ngay cả khi chạy trong cùng một JVM. Tuy nhiên, trong một ứng dụng hoặc nhiều context dùng chung lớp Micrometer, cần xem global registry là trạng thái dùng chung.

### Không phải registry theo request hoặc tenant

Global registry không tự tạo ranh giới riêng cho từng request, người dùng hay tenant. Nếu một request thêm registry, common tag hoặc filter vào global registry, thay đổi đó có thể ảnh hưởng các request khác đang chạy đồng thời.

Không dùng global registry để lưu trạng thái nghiệp vụ hoặc trạng thái của một người dùng. Metrics là dữ liệu quan sát tổng hợp. Nếu cần phân biệt tenant, chỉ dùng tag khi tập tenant có giới hạn phù hợp và cardinality đã được đánh giá; không tạo một registry toàn cục riêng cho từng request hoặc tenant.

## 4. Tác động đến thiết kế module và thư viện

API tĩnh làm giảm số tham số cần truyền, nhưng cũng che khuất dependency. Một class gọi:

```java
Metrics.counter("orders.created").increment();
```

không cho thấy rõ registry đến từ đâu, ai cấu hình nó hoặc ai chịu trách nhiệm đóng nó.

Điều này tạo ra một số hệ quả:

- Khó thay registry bằng một implementation khác trong unit test.
- Khó biết module nào đã thêm meter vào global registry.
- Tên metric và tag có thể xung đột giữa các module.
- Một thư viện có thể vô tình ghi metrics vào backend của ứng dụng chủ.
- Thay đổi global state có thể làm test hoặc context khác bị ảnh hưởng.

Với module ứng dụng, dependency injection thường làm ranh giới rõ ràng hơn:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class OrderMetrics {
    private final Counter created;

    public OrderMetrics(MeterRegistry registry) {
        this.created = Counter.builder("orders.created")
            .description("Số đơn hàng được tạo")
            .register(registry);
    }

    public void recordCreated() {
        created.increment();
    }
}
```

Registry được truyền vào constructor nên dependency có thể được nhìn thấy, thay thế và kiểm thử. Spring Boot có thể cung cấp bean `MeterRegistry` phù hợp với registry backend được cấu hình trong ứng dụng.

Đối với thư viện dùng lại ở nhiều ứng dụng, nên nhận `MeterRegistry` qua constructor hoặc một API cấu hình rõ ràng. Điều này để ứng dụng chủ quyết định registry nào được sử dụng và tránh việc thư viện tự ý thay đổi global state của tiến trình.

### Khi nào API tĩnh vẫn hữu ích?

Global registry có thể phù hợp trong các tình huống:

- Một tiện ích nhỏ cần ghi metric mà không muốn truyền registry qua nhiều tầng.
- Mã tích hợp cũ đã sử dụng API tĩnh và cần duy trì tương thích.
- Ứng dụng có một global registry được cấu hình có chủ đích và vòng đời rõ ràng.
- Một thành phần độc lập được triển khai trong môi trường có quy ước quản lý global registry thống nhất.

Ngay cả khi dùng API tĩnh, nên gom lời gọi vào một facade nhỏ do ứng dụng sở hữu. Cách này giúp kiểm soát tên metric, tag và có điểm thay thế khi cần chuyển sang dependency injection.

## 5. Tích hợp Metrics.globalRegistry với Spring Boot

Spring Boot Actuator cấu hình Micrometer và các registry backend thông qua auto-configuration. Bean `MeterRegistry` được ứng dụng tiêm vào constructor là điểm tích hợp rõ ràng nhất cho instrumentation thông thường.

Cần phân biệt bean registry của Spring với `Metrics.globalRegistry`. Không nên giả định rằng mọi `MeterRegistry` bean đều tự động được thêm vào global registry theo mọi phiên bản hoặc mọi cấu hình. Nếu mã ứng dụng dùng các phương thức tĩnh của `Metrics`, hãy xác minh rõ registry backend đã được gắn vào global registry trong cấu hình đang chạy.

Việc gắn có thể thực hiện bằng `Metrics.addRegistry(meterRegistry)` tại một điểm khởi tạo được quản lý. Cần đảm bảo:

1. Registry backend đã được tạo và cấu hình trước khi gắn.
2. Mỗi registry được quản lý theo một vòng đời xác định.
3. Registry được gỡ khỏi global registry khi ứng dụng dừng hoặc context bị hủy.
4. Không vô tình gắn một registry trung gian hoặc composite theo cách tạo vòng tham chiếu.
5. Không tạo nhiều lần gắn cùng một backend qua nhiều đường cấu hình.

Nếu một ứng dụng có nhiều registry backend, composite có thể gửi meter đến từng registry con. Điều đó có thể là chủ đích, chẳng hạn vừa xuất Prometheus vừa xuất OTLP. Hãy xác định rõ backend nào nhận dữ liệu, tránh cấu hình dư thừa và xác minh kết quả scrape/export ở từng đích.

### Cấu hình common tags

Common tags cần có cùng quy ước trên các registry đích. Khi cấu hình global registry và registry con, hãy kiểm tra tag thực tế ở đầu ra để tránh thiếu tag hoặc thêm cùng một tag hai lần.

Ví dụ một bộ tag ổn định:

```text
application=orders-service
environment=production
region=ap-southeast-1
```

Không dùng common tag cho giá trị thay đổi theo request như request ID hoặc user ID. Các giá trị này làm tăng cardinality và không phù hợp với metadata chung của toàn ứng dụng.

## 6. Rủi ro khi dùng global registry

### Rò rỉ trạng thái giữa các test

Global registry sống lâu hơn một test method. Nếu test thêm registry nhưng không gỡ nó, test sau có thể tiếp tục gửi metrics đến registry cũ. Nếu nhiều test dùng cùng tên và tag, meter có thể được dùng chung hoặc kết quả test phụ thuộc thứ tự chạy.

Các biểu hiện thường gặp:

- Counter có giá trị lớn hơn dự kiến dù test chỉ increment một lần.
- Test chạy riêng thì pass nhưng chạy cả suite thì fail.
- Một test ghi metrics vào registry của test khác.
- Registry đã đóng vẫn còn được tham chiếu trong global registry.
- Test chạy song song ảnh hưởng lẫn nhau.

Cách xử lý là ưu tiên registry riêng được inject cho unit test. Chỉ test hành vi của static API mới cần gắn registry vào global registry, và phải gỡ registry sau khi test kết thúc.

### Rò rỉ registry qua vòng đời Spring context

Trong môi trường có nhiều Spring context, việc gắn registry của context A vào global registry có thể khiến context B cũng gửi số liệu đến registry A. Khi context A bị hủy nhưng registry chưa được gỡ, global registry có thể giữ tham chiếu đến registry cũ.

Điều này dễ xảy ra trong test dùng context cache, ứng dụng plugin, môi trường phát triển có reload hoặc máy chủ nhúng nhiều ứng dụng trong cùng class loader.

Hãy gắn registry theo đúng vòng đời context và detach khi context đóng. Không giả định việc Spring đóng bean sẽ tự động loại nó khỏi mọi cấu trúc static mà ứng dụng đã tự đăng ký.

### Đăng ký trùng hoặc xuất trùng

Nếu nhiều module cùng gọi `Metrics.addRegistry` cho các registry backend mà chúng tự tạo, một meter có thể được chuyển tới nhiều đích ngoài dự kiến. Điều này làm tăng chi phí scrape, lưu trữ và có thể tạo dashboard trùng dữ liệu nếu các backend được tổng hợp lại.

Hãy chọn một thành phần sở hữu việc gắn registry. Các module nghiệp vụ chỉ đăng ký meter, không tự ý thêm hoặc gỡ registry backend.

### Xung đột tên và tag

Global registry là điểm dùng chung, vì vậy hai module có thể vô tình sử dụng cùng tên và cùng tag cho hai ý nghĩa khác nhau. Khi đó registry coi chúng là cùng một meter identity, dù người viết mã nghĩ rằng chúng độc lập.

Đặt quy ước tên theo miền nghiệp vụ hoặc namespace rõ ràng, ví dụ:

- `orders.created`
- `payments.charge.duration`
- `inventory.reservation.failed`

Tag phải có ý nghĩa nhất quán cho cùng metric. Không để một module dùng `status=success` theo nghĩa HTTP, module khác lại dùng cùng tag key theo nghĩa trạng thái đơn hàng trong cùng meter identity.

## 7. Kiểm thử với static API và registry dùng chung

Phần lớn unit test nên dùng một registry độc lập:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderMetricsTest {

    @Test
    void recordsCreatedOrders() {
        MeterRegistry registry = new SimpleMeterRegistry();
        OrderMetrics metrics = new OrderMetrics(registry);

        try {
            metrics.recordCreated();

            assertEquals(
                1.0,
                registry.get("orders.created").counter().count()
            );
        } finally {
            registry.close();
        }
    }
}
```

Cách này kiểm tra hành vi instrumentation mà không cần sửa trạng thái toàn cục.

Nếu cần xác minh static API thực sự ghi vào registry được gắn, hãy viết một test riêng và luôn gỡ registry trong `finally`:

```java
import io.micrometer.core.instrument.Metrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GlobalMetricsTest {

    @Test
    void staticApiPublishesToAttachedRegistry() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        Metrics.addRegistry(registry);

        try {
            Metrics.counter(
                "test.global.registry.invocations",
                "suite", "global-registry"
            ).increment();

            assertEquals(
                1.0,
                registry.get("test.global.registry.invocations")
                    .tag("suite", "global-registry")
                    .counter()
                    .count()
            );
        } finally {
            Metrics.removeRegistry(registry);
            registry.close();
        }
    }
}
```

Trong test thực tế, nên dùng tên metric dành riêng cho test, tránh chạy song song các test cùng thao tác trên global registry và không dùng `Metrics.globalRegistry.clear()` như cách dọn dẹp mặc định. `clear()` có thể xóa meter do các thành phần khác đang sử dụng trong cùng class loader.

Một integration test bổ sung có thể xác minh registry backend nhận được meter từ static API và xuất đúng tên, tag, unit hoặc histogram. Unit test với `SimpleMeterRegistry` không thay thế kiểm thử endpoint của Prometheus hoặc backend thực tế.

## 8. Quan sát và chẩn đoán global registry

Khi static metrics không xuất hiện, hãy kiểm tra theo thứ tự:

1. Lời gọi đang dùng `Metrics.counter`, `Metrics.timer` hay một registry được inject?
2. Nếu dùng API tĩnh, registry backend đã được thêm vào `Metrics.globalRegistry` chưa?
3. Việc gắn registry xảy ra trước hay sau khi luồng nghiệp vụ bắt đầu ghi số liệu?
4. Registry có bị gỡ hoặc đóng trong khi ứng dụng vẫn chạy không?
5. Filter có từ chối meter hoặc biến đổi tên/tag không?
6. Backend có scrape/export đúng endpoint và đúng thời điểm không?

Có thể kiểm tra số registry con của composite trong quá trình chẩn đoán:

```java
int attachedRegistryCount =
    Metrics.globalRegistry.getRegistries().size();
```

Đây là thông tin chẩn đoán, không nên dùng để điều khiển nghiệp vụ. Số lượng registry con không chứng minh rằng mọi meter đã được cấu hình đúng hoặc backend đang nhận dữ liệu thành công.

Nếu một meter có trong global registry nhưng không thấy ở backend, hãy kiểm tra registry con, filter, cấu hình export và quá trình scrape. Nếu không có registry con, static API không có đích xuất dữ liệu.

## 9. Hướng dẫn lựa chọn

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Service Spring cần ghi metrics | Inject `MeterRegistry` |
| Unit test cần cô lập meter | Tạo `SimpleMeterRegistry` riêng |
| Mã cũ đang dùng static API | Dùng global registry với lifecycle được quản lý |
| Thư viện được tái sử dụng trong nhiều ứng dụng | Nhận `MeterRegistry` từ ứng dụng chủ |
| Một ứng dụng xuất tới nhiều backend | Dùng composite có cấu hình registry con rõ ràng |
| Nhiều Spring context trong cùng class loader | Tránh global state hoặc quản lý add/remove theo từng context |

Quy trình thực tế khi quyết định dùng global registry:

1. Xác định module nào sở hữu vòng đời registry backend.
2. Xác định các thành phần nào cần API tĩnh và lý do không dùng dependency injection.
3. Gắn registry trước khi ghi metrics và xác minh static API chuyển dữ liệu đến đúng backend.
4. Quy định namespace tên metric và tập tag dùng chung.
5. Gỡ registry khi ứng dụng hoặc context kết thúc.
6. Viết test xác minh cả đường ghi static lẫn khả năng cô lập test.

## 10. Checklist vận hành

- [ ] Hiểu rằng `Metrics.globalRegistry` là composite registry dùng chung.
- [ ] Biết static API ghi vào global registry, không tự chọn một Spring bean bất kỳ.
- [ ] Registry backend được gắn trước khi ứng dụng cần xuất số liệu.
- [ ] Không giả định số liệu trước thời điểm gắn registry được lưu đệm và phát lại.
- [ ] Có một thành phần sở hữu việc add/remove registry.
- [ ] Registry được detach trước khi đóng hoặc hủy context.
- [ ] Không thêm hoặc gỡ registry trong mỗi request.
- [ ] Tên meter và tag không xung đột giữa các module.
- [ ] Không dùng global registry làm vùng lưu trạng thái tenant hoặc request.
- [ ] Unit test ưu tiên registry riêng; test static API luôn cleanup.
- [ ] Không dùng `clear()` để dọn một test trong khi còn thành phần khác dùng global registry.
- [ ] Đã xác minh số liệu thực tế tại backend nhận metrics.

`Metrics.globalRegistry` hữu ích khi cần một điểm ghi metrics tĩnh dùng chung, nhưng nó đưa trạng thái và vòng đời của registry ra phạm vi toàn cục. Quản lý rõ ai gắn registry, khi nào bắt đầu ghi, cách cô lập test và thời điểm tháo registry sẽ giúp tránh rò rỉ trạng thái, xuất trùng và số liệu khó diễn giải.


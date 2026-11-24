# Tái sử dụng meter trong trường đối tượng và giảm tạo builder lặp lại

Trong Micrometer, một meter nên được đăng ký một lần rồi tái sử dụng trong suốt vòng đời của thành phần cần ghi nhận số liệu. Cách phổ biến trong ứng dụng Spring là inject `MeterRegistry`, tạo meter trong constructor và lưu tham chiếu vào trường `final`. Các phương thức nghiệp vụ chỉ gọi `increment()`, `record()` hoặc `record(value)` trên meter đã có.

Cách làm này giúp tên và tag được khai báo tập trung, tránh tạo builder và tra cứu registry lặp lại trên đường xử lý nóng (hot path), đồng thời làm rõ vòng đời của instrumentation. Registry vẫn nhận diện meter bằng tên và tập tag; nếu nhiều component đăng ký cùng danh tính trong một registry, chúng có thể dùng chung meter đó.

## 1. Builder và meter là hai đối tượng khác nhau

`Counter.builder(...)`, `Timer.builder(...)` và `DistributionSummary.builder(...)` tạo builder để mô tả meter. Khi gọi `register(registry)`, builder đăng ký meter vào registry và trả về đối tượng meter tương ứng.

```java
Counter counter = Counter.builder("shop.orders.created")
        .description("Number of successfully created orders")
        .register(registry);
```

Sau khi đăng ký, ứng dụng nên giữ lại `counter` và cập nhật nó khi sự kiện xảy ra. Không cần tạo builder mới mỗi lần tăng counter:

```java
// Nên: đăng ký một lần, tái sử dụng nhiều lần.
private final Counter ordersCreated;

public OrderMetrics(MeterRegistry registry) {
    this.ordersCreated = Counter.builder("shop.orders.created")
            .register(registry);
}

public void recordCreated() {
    ordersCreated.increment();
}
```

Builder là đối tượng cấu hình tạm thời; meter là đối tượng được registry quản lý và được dùng để ghi nhận số liệu. Lưu meter vào field giúp thể hiện rõ rằng component đang sử dụng một phép đo đã đăng ký.

## 2. Đăng ký meter trong constructor và lưu bằng field final

Ví dụ một component quản lý counter và timer cho quy trình đơn hàng:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;
import org.springframework.stereotype.Component;

@Component
public class OrderMetrics {
    private final Counter ordersCreated;
    private final Timer orderProcessing;

    public OrderMetrics(MeterRegistry registry) {
        this.ordersCreated = Counter.builder("shop.orders.created")
                .description("Number of successfully created orders")
                .register(registry);

        this.orderProcessing = Timer.builder("shop.orders.processing")
                .description("Time spent processing an order")
                .register(registry);
    }

    public void recordCreated() {
        ordersCreated.increment();
    }

    public <T> T recordProcessing(Supplier<T> operation) {
        return orderProcessing.record(operation);
    }

    public void recordExternalDuration(long duration, TimeUnit unit) {
        orderProcessing.record(duration, unit);
    }
}
```

Spring tạo bean `OrderMetrics`, truyền registry vào constructor và component đăng ký hai meter trong lúc khởi tạo. Các lần gọi sau chỉ dùng field đã có.

Việc khai báo field là `final` bảo đảm tham chiếu đến meter không bị gán sang đối tượng khác sau khi constructor hoàn tất. Bản thân meter vẫn có thể thay đổi số liệu thông qua các phương thức cập nhật; `final` chỉ cố định tham chiếu.

Constructor injection cũng làm dependency hiển thị rõ ràng và giúp unit test truyền một `SimpleMeterRegistry` trực tiếp mà không cần khởi tạo Spring context.

## 3. Tránh tạo builder và tra cứu meter trên hot path

Một cách viết có thể hoạt động nhưng không nên dùng thường xuyên là tạo builder trong mỗi lần xử lý:

```java
public void recordCreated(MeterRegistry registry) {
    Counter.builder("shop.orders.created")
            .description("Number of successfully created orders")
            .register(registry)
            .increment();
}
```

Mỗi lần gọi, code lại tạo builder, thiết lập metadata, gọi đăng ký và yêu cầu registry tìm meter theo danh tính. Registry thường tái sử dụng meter đã đăng ký với cùng tên và tag trong cùng registry, vì vậy đoạn code này không nhất thiết tạo ra một chuỗi thời gian mới mỗi lần. Tuy nhiên, nó vẫn lặp lại công việc cấu hình và tra cứu không cần thiết.

Phiên bản nên dùng:

```java
private final Counter ordersCreated;

public OrderMetrics(MeterRegistry registry) {
    this.ordersCreated = registry.counter("shop.orders.created");
}

public void recordCreated() {
    ordersCreated.increment();
}
```

`MeterRegistry.counter(name, tags...)` là API tiện ích để tìm hoặc tạo counter theo danh tính. Dùng API này trong constructor cũng được; điểm quan trọng là giữ kết quả trong field thay vì gọi lại trên mỗi sự kiện.

Không nên xem builder là một chi phí lớn trong mọi trường hợp. Builder thường nhẹ; lợi ích thực tế phụ thuộc tần suất gọi, loại meter và implementation registry. Lợi ích rõ ràng hơn là code có danh tính meter ổn định, ít thao tác lặp và dễ kiểm thử. Nếu tối ưu hiệu năng là mục tiêu chính, hãy đo profiling trước và sau thay đổi.

## 4. Meter trong field không có nghĩa mỗi object có một meter độc lập

Registry nhận diện meter theo tên và tập tag. Nếu hai object cùng đăng ký `shop.orders.created` với cùng tag trong cùng một registry, registry sẽ tìm meter có sẵn thay vì tạo một chuỗi thời gian độc lập cho mỗi object.

```java
OrderMetrics first = new OrderMetrics(registry);
OrderMetrics second = new OrderMetrics(registry);

first.recordCreated();
second.recordCreated();
```

Nếu hai component đăng ký cùng danh tính, cả hai tham chiếu có thể cập nhật cùng một counter trong registry. Kết quả count tăng tổng cộng hai đơn vị.

Điều này phù hợp khi cả hai object đang ghi nhận cùng một đại lượng chung. Nếu cần phân biệt theo một chiều nghiệp vụ, hãy dùng tag có tập giá trị hữu hạn, ví dụ `channel=web` hoặc `channel=mobile`. Đừng thêm tag chỉ để tạo meter riêng cho từng object nếu không có câu hỏi vận hành cần phân tích theo chiều đó.

### 4.1. Tránh tag định danh object

Không dùng object ID, user ID, order ID hoặc request ID làm tag để tách meter. Nếu mỗi object có một giá trị tag riêng, số meter và chuỗi thời gian có thể tăng theo số object được tạo.

Nếu muốn phân biệt theo loại worker, loại client hoặc nhóm nghiệp vụ, hãy chuẩn hóa thành một danh sách giá trị nhỏ. Ví dụ:

```java
enum Channel {
    WEB,
    MOBILE,
    PARTNER,
    OTHER
}
```

Sau đó đăng ký meter cho từng giá trị hợp lệ và tái sử dụng các meter tương ứng.

## 5. Tái sử dụng meter cho tập tag hữu hạn

Khi một component cần ghi nhận cùng metric theo một tập tag đã biết, có thể đăng ký trước meter cho mọi giá trị hợp lệ rồi lưu vào map. Ví dụ sau dùng `EnumMap` cho các kênh bán hàng:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.Collections;
import java.util.EnumMap;
import java.util.Map;
import org.springframework.stereotype.Component;

enum Channel {
    WEB,
    MOBILE,
    PARTNER,
    OTHER
}

@Component
public class ChannelOrderMetrics {
    private final Map<Channel, Counter> ordersByChannel;

    public ChannelOrderMetrics(MeterRegistry registry) {
        EnumMap<Channel, Counter> meters = new EnumMap<>(Channel.class);

        for (Channel channel : Channel.values()) {
            meters.put(channel, Counter.builder("shop.orders.created")
                    .description("Number of successfully created orders")
                    .tag("channel", channel.name().toLowerCase(java.util.Locale.ROOT))
                    .register(registry));
        }

        this.ordersByChannel = Collections.unmodifiableMap(meters);
    }

    public void recordCreated(Channel channel) {
        ordersByChannel.get(channel).increment();
    }
}
```

Các meter được đăng ký khi bean khởi tạo. Phương thức `recordCreated()` chỉ tra cứu map và tăng counter. Vì `Channel` là enum, tập tag value hữu hạn và dễ dự đoán.

### 5.1. Chuẩn hóa đầu vào trước khi chọn meter

Nếu dữ liệu đầu vào đến từ request hoặc hệ thống bên ngoài, không nên dùng trực tiếp chuỗi chưa kiểm soát làm tag. Hãy ánh xạ về enum hoặc tập value cố định:

```java
private Channel normalizeChannel(String raw) {
    if (raw == null) {
        return Channel.OTHER;
    }

    switch (raw.trim().toLowerCase(java.util.Locale.ROOT)) {
        case "web":
            return Channel.WEB;
        case "mobile":
            return Channel.MOBILE;
        case "partner":
            return Channel.PARTNER;
        default:
            return Channel.OTHER;
    }
}
```

Trong ví dụ đầy đủ, `OTHER` là nhóm dự phòng cho đầu vào không xác định. Chọn giá trị dự phòng có ý nghĩa thay vì gộp dữ liệu lạ vào một kênh hợp lệ.

Ở nơi nhận chuỗi từ request hoặc hệ thống bên ngoài, hãy gọi `recordCreated(normalizeChannel(rawChannel))` để chỉ truyền enum đã được chuẩn hóa vào map meter.

## 6. Khi tập tag không thể đăng ký trước

Đôi khi tập tag chỉ biết được lúc chạy nhưng vẫn có giới hạn rõ ràng. Có thể dùng cache meter với `ConcurrentHashMap.computeIfAbsent` để chỉ đăng ký meter ở lần đầu gặp mỗi value:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Component;

@Component
public class PartnerMetrics {
    private final MeterRegistry registry;
    private final ConcurrentMap<String, Counter> counters =
            new ConcurrentHashMap<>();

    public PartnerMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordResponse(String partnerGroup) {
        String boundedGroup = normalizePartnerGroup(partnerGroup);
        Counter counter = counters.computeIfAbsent(boundedGroup, group ->
                Counter.builder("shop.partner.responses")
                        .tag("partner_group", group)
                        .register(registry));
        counter.increment();
    }

    private String normalizePartnerGroup(String raw) {
        if (raw == null) {
            return "other";
        }

        switch (raw) {
            case "tier-a":
            case "tier-b":
            case "tier-c":
                return raw;
            default:
                return "other";
        }
    }
}
```

`ConcurrentHashMap` giúp các luồng cùng yêu cầu một key dùng chung kết quả đã tạo. Việc chuẩn hóa trước `computeIfAbsent` bảo đảm số key tối đa là bốn trong ví dụ. Nếu đầu vào không được giới hạn, map có thể tăng không giới hạn và làm chính ứng dụng tiêu thụ bộ nhớ; registry cũng có thể tạo quá nhiều meter.

Khi danh sách giá trị đã biết từ đầu, đăng ký trước bằng enum hoặc map thường đơn giản hơn. Chỉ dùng cache động khi có lý do rõ ràng và có giới hạn cardinality được kiểm soát.

## 7. Thread safety khi tái sử dụng meter

Các meter tiêu chuẩn của Micrometer được thiết kế để được cập nhật từ nhiều luồng. Có thể giữ một `Counter` hoặc `Timer` trong field `final` của bean singleton rồi gọi `increment()` hoặc `record()` từ nhiều request đồng thời.

```java
@Component
public class MessageMetrics {
    private final Counter processed;

    public MessageMetrics(MeterRegistry registry) {
        this.processed = registry.counter("app.messages.processed");
    }

    public void recordProcessed() {
        processed.increment();
    }
}
```

Field `final` bảo đảm mọi luồng nhìn thấy tham chiếu đã được khởi tạo an toàn khi bean được công bố qua Spring. Việc cập nhật nội bộ của meter tiêu chuẩn cũng hỗ trợ sử dụng đồng thời. Không cần tạo một meter riêng cho mỗi request để tránh tranh chấp.

Nếu meter được bọc trong một class tùy chỉnh hoặc nguồn dữ liệu của `Gauge`/`FunctionCounter` là đối tượng mutable, bạn vẫn phải bảo đảm nguồn dữ liệu đó an toàn khi nhiều luồng đọc và ghi. Thread safety của meter không tự động làm cho mọi object mà meter tham chiếu trở nên thread-safe.

## 8. Tái sử dụng Timer và DistributionSummary

Nguyên tắc giữ meter trong field áp dụng cho mọi loại meter. Ví dụ với `DistributionSummary`:

```java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class PayloadMetrics {
    private final DistributionSummary payloadSize;

    public PayloadMetrics(MeterRegistry registry) {
        this.payloadSize = DistributionSummary.builder("app.payload.size")
                .baseUnit("bytes")
                .description("Payload size in bytes")
                .register(registry);
    }

    public void recordPayloadSize(long bytes) {
        if (bytes < 0) {
            throw new IllegalArgumentException("Payload size cannot be negative");
        }
        payloadSize.record(bytes);
    }
}
```

`DistributionSummary` được đăng ký một lần. Mỗi lần xử lý payload chỉ ghi giá trị vào meter đã có. Cùng cách đó, một `Timer` được giữ trong field và tái sử dụng cho mọi thao tác thuộc cùng metric/tag set.

Không tạo builder mới chỉ để thay đổi giá trị đo. Builder mô tả meter; giá trị được ghi nhận bằng phương thức của meter sau khi đăng ký.

## 9. Vòng đời component và registry

Trong Spring Boot, một bean `@Component` mặc định thường là singleton trong application context. Vì vậy, meter được giữ trong field của component tồn tại trong suốt vòng đời context và có thể được dùng lại qua nhiều request.

Nếu component có scope prototype hoặc được tạo thủ công nhiều lần, mỗi instance có thể chạy constructor và đăng ký meter lại. Registry vẫn tra cứu theo danh tính; cùng tên và tag có thể trả về cùng meter, nhưng builder và thao tác đăng ký vẫn bị lặp. Hãy cân nhắc scope của component và không tạo instrumentation object mới theo từng request nếu không cần.

Không đóng registry được inject vào component. Registry là tài nguyên do application context hoặc cấu hình cấp ứng dụng quản lý. Component chỉ sở hữu tham chiếu đến meter mà nó sử dụng.

Với `Gauge`, cần giữ cả đối tượng trạng thái được đo đủ lâu vì Micrometer thường dùng weak reference đến object nguồn. Lưu meter vào field không thay thế yêu cầu giữ sống đối tượng mà gauge đọc.

## 10. Kiểm thử việc tái sử dụng meter

Có thể dùng `SimpleMeterRegistry` để xác minh component đăng ký meter đúng tên và các lần gọi cập nhật cùng một meter:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class OrderMetricsTest {
    @Test
    void reusesRegisteredCounterAcrossCalls() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            OrderMetrics metrics = new OrderMetrics(registry);

            metrics.recordCreated();
            metrics.recordCreated();
            metrics.recordCreated();

            assertThat(registry.get("shop.orders.created")
                    .counter().count()).isEqualTo(3.0);
            assertThat(registry.getMeters()).hasSize(2);
        }
    }
}
```

Trong ví dụ này, `OrderMetrics` đăng ký một counter và một timer. Ba lần gọi `recordCreated()` chỉ cập nhật counter đã có; số meter trong registry không tăng theo số lần gọi.

Với component có tag, hãy kiểm tra số lượng meter theo số tổ hợp hợp lệ, không theo số request. Nếu dùng map cache, hãy kiểm tra đầu vào không hợp lệ được chuẩn hóa về nhóm dự phòng và số key không vượt giới hạn.

## 11. Những lỗi thường gặp

- **Tạo builder trong mỗi phương thức nghiệp vụ:** lặp lại cấu hình và thao tác đăng ký/tra cứu trên hot path.
- **Không lưu meter trả về từ `register()`:** component phải tìm lại meter khi cần ghi nhận.
- **Nhầm builder với meter:** builder dùng để cấu hình; meter mới là đối tượng dùng để cập nhật số liệu.
- **Cho rằng mỗi object có meter độc lập:** cùng tên và tag trong cùng registry có thể dùng chung một meter.
- **Gắn ID object làm tag:** tạo cardinality cao và làm số meter tăng theo số object.
- **Cache tag không giới hạn:** map và registry cùng tăng theo số value mới.
- **Tạo component instrumentation theo request:** constructor và đăng ký meter bị lặp không cần thiết.
- **Dùng static meter gắn với registry:** có thể làm dependency ẩn và gây rò rỉ trạng thái giữa các application context hoặc test.
- **Cho rằng field final giải quyết mọi thread safety:** nguồn dữ liệu mutable được gauge/function meter đọc vẫn cần cơ chế đồng bộ phù hợp.
- **Tối ưu builder mà không đo:** builder thường nhẹ; hãy tập trung vào tính nhất quán và chỉ tối ưu sâu khi profiling cho thấy cần thiết.

## 12. Checklist tái sử dụng meter

- [ ] Inject `MeterRegistry` qua constructor.
- [ ] Đăng ký meter trong constructor hoặc bước khởi tạo một lần của bean.
- [ ] Lưu meter trả về vào field `final`.
- [ ] Phương thức nghiệp vụ chỉ cập nhật meter đã đăng ký.
- [ ] Dùng cùng tên và tập tag cho cùng một đại lượng.
- [ ] Dùng enum hoặc map cho tập tag hữu hạn; chuẩn hóa trước khi tra cứu.
- [ ] Giới hạn cardinality nếu phải cache meter theo key động.
- [ ] Không tạo component instrumentation mới theo từng request.
- [ ] Không đóng registry dùng chung hoặc giữ static reference không cần thiết.
- [ ] Kiểm thử số meter và giá trị sau nhiều lần cập nhật.
- [ ] Đo profiling trước khi kết luận builder lặp lại là nút thắt hiệu năng.

Tái sử dụng meter trong field giúp instrumentation có vòng đời rõ ràng và tránh lặp lại công việc đăng ký trong mỗi lần xử lý. Hãy để component khởi tạo meter một lần, giữ tham chiếu ổn định, kiểm soát tag và chỉ cập nhật số liệu trên đường nghiệp vụ. Cách làm này vừa dễ duy trì vừa giúp giảm công việc không cần thiết trong hot path.

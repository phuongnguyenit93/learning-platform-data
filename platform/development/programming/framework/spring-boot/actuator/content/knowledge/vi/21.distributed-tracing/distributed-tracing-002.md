# Quan hệ giữa Micrometer Tracing, Observation và thư viện tracer

## 1. Bắt đầu từ một thao tác cần quan sát

Giả sử ứng dụng có thao tác đặt hàng, bên trong gọi bước thanh toán. Bạn muốn trả lời hai loại câu hỏi:

- Thao tác chạy bao nhiêu lần, mất tổng cộng bao lâu và có thường phát sinh lỗi không?
- Một lần đặt hàng cụ thể đã đi qua những bước nào, các bước liên hệ với nhau ra sao?

Metric phù hợp với câu hỏi tổng hợp. Trace phù hợp với việc theo dõi một lần thực thi và các thao tác có liên quan. Cùng một đoạn mã nghiệp vụ có thể cung cấp dữ liệu cho cả hai.

**Micrometer Observation mô tả và quản lý một lần quan sát; các handler quyết định dữ liệu nào được tạo từ vòng đời đó. Micrometer Tracing cung cấp API truy vết thống nhất; bridge nối API này với thư viện tracer cụ thể như Brave hoặc OpenTelemetry.**

Đây là các vai trò phối hợp, không phải những tên gọi thay thế cho cùng một thành phần. Một ứng dụng có thể dùng Observation để ghi metric mà chưa tạo span. Ngược lại, mã dùng trực tiếp API `Tracer` có thể tạo span mà không tạo metric.

## 2. Bản đồ các thành phần

```text
Mã được gắn logic quan sát
        |
        v
Observation + ObservationRegistry
        |
        +--> Handler metric
        |      --> MeterRegistry
        |      --> hệ thống thu thập/lưu metric, tùy cấu hình
        |
        +--> Handler tracing
               --> API Micrometer Tracing
               --> bridge Brave hoặc bridge OpenTelemetry
               --> thư viện tracer/SDK tương ứng
               --> reporter/exporter
               --> collector hoặc hệ thống nhận trace
               --> nơi lưu trữ và truy vấn trace
```

Nhánh metric và nhánh tracing cùng nhận các sự kiện vòng đời observation phù hợp. Không cần viết lại cùng một phép đo nghiệp vụ bằng hai bộ mã bắt đầu–kết thúc riêng chỉ để thu cả hai loại dữ liệu. Đây là mục tiêu của thiết kế dựa trên handler. [Micrometer: các thành phần Observation](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

| Thành phần | Trách nhiệm | Không nên nhầm với |
| --- | --- | --- |
| `Observation` | Một lần quan sát có tên, ngữ cảnh, nhãn, sự kiện và vòng đời | Một span đã chắc chắn được gửi đi |
| `ObservationRegistry` | Giữ cấu hình và điều phối handler cho observation | Nơi lưu trữ trace để truy vấn |
| `MeterRegistry` | Quản lý các meter như timer và counter | Tracer |
| Micrometer Tracing API | Cung cấp các kiểu như `Tracer`, `Span`, `TraceContext` dùng chung | Một hệ thống lưu trữ trace |
| Bridge | Chuyển lời gọi từ Micrometer Tracing sang API của tracer cụ thể | Exporter gửi dữ liệu |
| Brave hoặc OpenTelemetry SDK | Thực thi cơ chế tracer cụ thể: span, ngữ cảnh, lấy mẫu và xử lý liên quan | Giao diện xem trace |
| Reporter/exporter | Đưa dữ liệu span ra khỏi tiến trình theo giao thức/cấu hình đã chọn | Bridge API |
| Collector/hệ thống nhận trace | Nhận, có thể xử lý và chuyển tiếp dữ liệu | Thư viện tracer chạy trong ứng dụng |

Trong OpenTelemetry, API và SDK cũng có vai trò khác nhau: API là hợp đồng gọi, SDK cung cấp cơ chế thực thi và cấu hình. Khi nói “dùng OpenTelemetry làm tracer”, cần hiểu ứng dụng phải có một triển khai và cấu hình hoạt động, không chỉ có các kiểu API.

Collector có thể là một bước trung gian; không bắt buộc mọi cấu hình phải có một collector tách biệt. Ví dụ, reporter có thể gửi trực tiếp đến đầu nhận của một hệ thống lưu trữ trace.

## 3. Observation được chuyển thành span bằng cách nào?

### 3.1. Handler là điểm nối

Micrometer Tracing tích hợp với Observation bằng các `ObservationHandler` dành cho tracing. Với thao tác cục bộ thông thường, `DefaultTracingObservationHandler` là ví dụ quan trọng.

Khi handler này dùng một tracer thật, vòng đời đồng bộ có thể được hiểu như sau:

| Hành động của observation | Tác động tracing tương ứng |
| --- | --- |
| Bắt đầu observation | Tạo/bắt đầu span theo tracer và quan hệ ngữ cảnh hiện có |
| Mở scope | Làm span liên quan trở thành span hiện tại trong phạm vi đó |
| Báo lỗi | Gắn thông tin lỗi vào span theo cơ chế handler/tracer |
| Đóng scope | Khôi phục ngữ cảnh span trước đó |
| Dừng observation | Hoàn tất span để các thành phần xử lý span tiếp nhận |

Handler metric có thể đồng thời bắt đầu mẫu đo thời gian và ghi timer khi observation dừng. Vì thế, một vòng đời nghiệp vụ có thể tạo cả số liệu tổng hợp và dữ liệu truy vết. [Micrometer Tracing 1.3: cấu hình handler với Observation](https://docs.micrometer.io/tracing/reference/1.3/configuring.html).

Điều này không có nghĩa mọi observation trong mọi ứng dụng đều trở thành một span có thể tìm thấy ở hệ thống giám sát. Còn cần xét:

- Observation có bị vô hiệu hóa bởi predicate hoặc cấu hình không?
- Registry có handler tracing phù hợp không?
- Handler có dùng tracer hoạt động hay một triển khai không thực hiện ghi dữ liệu?
- Chính sách lấy mẫu có cho ghi nhận/gửi span không?
- Span đã kết thúc và đường xuất dữ liệu có hoạt động không?

Một observation bị bỏ qua hoàn toàn và một span không được xuất do lấy mẫu là hai tình huống khác nhau. Nếu observation bị chặn ngay ở tầng Observation, cả những handler khác cũng có thể không được gọi. Nếu chỉ tracing không chọn ghi nhận span, nhánh metric vẫn có thể hoạt động bình thường.

### 3.2. Không phải mọi handler tracing đều có cùng nhiệm vụ

Với giao tiếp mạng, cần biết vai trò gửi/nhận, thông tin đích và cách inject/extract ngữ cảnh. Micrometer có các handler chuyên biệt như:

- `PropagatingSenderTracingObservationHandler` cho phía gửi.
- `PropagatingReceiverTracingObservationHandler` cho phía nhận.
- `DefaultTracingObservationHandler` cho trường hợp cục bộ thông thường.

Cấu hình có thể dùng `FirstMatchingCompositeObservationHandler` để chọn handler tracing phù hợp đầu tiên, thay vì tạo nhiều span cạnh tranh cho cùng một observation. Nhánh metric vẫn cần được xử lý riêng phù hợp; không đặt mọi handler vào một nhóm “chỉ lấy phần tử khớp đầu tiên” rồi vô tình làm mất nhánh còn lại.

`TracingAwareMeterObservationHandler` cần được hiểu đúng vị trí: nó bọc một handler metric và giúp nhánh metric phối hợp với ngữ cảnh tracing, chẳng hạn hỗ trợ liên kết mẫu đo với trace khi registry có khả năng tương ứng. Nó không thay thế toàn bộ các handler tracing tạo và quản lý span. Không mặc định rằng chỉ có chữ “Tracing” trong tên handler là đã có tracer và đường xuất span.

Trong ứng dụng Boot, các nhóm handler này thường được auto-configuration phối hợp. Không sao chép cấu hình handler thủ công của một ví dụ độc lập vào Boot mà không kiểm tra các handler đã tồn tại.

## 4. Micrometer Tracing và tracer cụ thể khác nhau ở đâu?

### 4.1. Cùng tên Tracer nhưng khác API

Ba tên kiểu sau thuộc ba hợp đồng khác nhau:

```text
io.micrometer.tracing.Tracer
brave.Tracer
io.opentelemetry.api.trace.Tracer
```

Mã nghiệp vụ muốn dựa vào lớp trừu tượng Micrometer thường inject `io.micrometer.tracing.Tracer`, hoặc dùng `ObservationRegistry` nếu muốn một lần quan sát phục vụ nhiều tín hiệu.

Các bridge cung cấp adapter tương ứng. Chẳng hạn, `BraveTracer` triển khai API Micrometer và chuyển lời gọi sang `brave.Tracer`. Phía OpenTelemetry có bridge tương ứng dùng tracer của OpenTelemetry.

Bridge giúp hạn chế việc mã quan sát nghiệp vụ phụ thuộc trực tiếp vào API riêng của một tracer. Khi đổi triển khai, vẫn cần kiểm tra cấu hình, convention, truyền ngữ cảnh, lấy mẫu và xuất dữ liệu; không giả định chỉ thay dependency là mọi chi tiết đầu ra giống nhau.

### 4.2. Thư viện tracer không phải hệ thống lưu trữ trace

Brave chạy trong tiến trình ứng dụng để thực hiện tracer. OpenTelemetry là một hệ sinh thái rộng hơn, trong đó API/SDK tracing thực hiện vai trò tương ứng. Chúng không tự trở thành một màn hình truy vấn toàn bộ trace của hệ thống chỉ vì đã có dependency.

Một reporter/exporter nhận span đã hoàn tất rồi đưa dữ liệu tới đầu nhận phù hợp. Ví dụ:

- Bridge OpenTelemetry có thể kết hợp với exporter OTLP.
- Bridge OpenTelemetry cũng có thể kết hợp với exporter Zipkin.
- Bridge Brave có thể kết hợp với reporter Zipkin.

Vì vậy, “chọn tracer” và “chọn nơi nhận trace” là hai quyết định liên quan nhưng khác nhau. Giao thức truyền như OTLP cũng khác với API mà mã Java dùng để tạo span. [Micrometer: dùng API Tracing và cấu hình Brave/OpenTelemetry](https://docs.micrometer.io/tracing/reference/api.html).

## 5. Trace, span, quan hệ cha–con và scope

Một trace mô tả các thao tác có liên quan trong một lần xử lý. Span mô tả một thao tác với thời gian bắt đầu/kết thúc và dữ liệu đi kèm. Các span thuộc cùng trace dùng chung trace ID; span ID nhận diện từng span.

Ví dụ trong một tiến trình:

```text
trace T
└── span checkout-flow, id A
    └── span payment-check, id B, parent A
```

Quan hệ này khác hai timer tên `checkout` và `payment`:

- Timer tổng hợp nhiều lần đo theo tên và bộ nhãn.
- Span giữ thông tin của một lần thực thi được ghi nhận.
- Cùng tên timer không có nghĩa là cùng trace.
- Cùng trace ID không có nghĩa là cùng span.

Trong đường gọi đồng bộ của ví dụ phía sau, observation ngoài mở scope; observation con được bắt đầu khi ngữ cảnh ngoài đang hiện tại. Handler tracing dùng ngữ cảnh đó để hình thành quan hệ cha–con.

Scope và vòng đời span là hai việc khác nhau. Đóng scope làm span đó không còn là span hiện tại trong phạm vi đang xét; nó không thay việc kết thúc span. Tương tự, một span đã được ghi nhận hoàn chỉnh vẫn có thể tồn tại ở hệ thống lưu trữ sau khi `tracer.currentSpan()` trên luồng hiện tại đã trả về `null`.

Qua luồng khác hoặc mạng, còn cần cơ chế truyền ngữ cảnh tương ứng. Có một span đang hiện tại trong luồng A không tự khiến luồng B hoặc dịch vụ khác biết về nó. Mã HTTP client/server đã được tích hợp quan sát có thể giúp truyền và tiếp nhận thông tin đó; bridge không tự chặn mọi thư viện mạng trong JVM. [OpenTelemetry giải thích trace và span](https://opentelemetry.io/docs/concepts/signals/traces/).

## 6. Tên và nhãn đi tới metric và span như thế nào?

Với cấu hình handler mặc định thường gặp:

| Dữ liệu Observation | Nhánh metric | Nhánh tracing |
| --- | --- | --- |
| Tên observation | Là cơ sở cho tên meter | Là tên dự phòng hoặc đầu vào của quy ước đặt tên span |
| `contextualName` | Không mặc nhiên đổi tên meter | Có thể được dùng làm tên span dễ đọc hơn |
| Nhãn ít giá trị (`low cardinality`) | Dùng làm nhãn metric | Có thể được thêm vào span |
| Nhãn nhiều giá trị (`high cardinality`) | Không được handler metric mặc định đưa thành nhãn metric | Có thể được thêm vào span |
| Lỗi/sự kiện | Do handler tương ứng quyết định cách thể hiện | Có thể thành thông tin lỗi/sự kiện trên span |

Convention hoặc handler tùy chỉnh có thể làm thay đổi chi tiết đầu ra. Hãy kiểm tra đúng cấu hình đang chạy, không coi bảng này là quy tắc cho mọi handler do người dùng tự viết.

Một mã đơn hàng có nhiều giá trị khác nhau có thể hữu ích để tra một span cụ thể, nhưng không phù hợp làm nhãn metric cho từng đơn hàng. Trace ID cũng không nên được thêm vào mỗi tổ hợp nhãn timer: làm vậy biến phép đo tổng hợp thành quá nhiều chuỗi số liệu.

Nhãn của observation/span cũng khác baggage. Baggage phục vụ mang dữ liệu ngữ cảnh qua các ranh giới được cấu hình; việc thêm một tag vào span không tự khiến tag đó được truyền sang mọi dịch vụ. Chọn dữ liệu thu thập có chủ đích và tránh đưa thông tin nhạy cảm vào dữ liệu quan sát.

## 7. Chọn Observation hay dùng trực tiếp Tracer?

| Nhu cầu | Điểm vào thường phù hợp |
| --- | --- |
| Quan sát một thao tác để có thể tạo cả metric và trace theo cấu hình | `ObservationRegistry` và Observation API |
| Tạo riêng một span, không cần tự tạo metric cho thao tác đó | Micrometer `Tracer` API |
| Làm việc với khả năng riêng của một SDK/tracer mà API chung không biểu diễn | API riêng, với phạm vi phụ thuộc được cân nhắc rõ |
| Xem trace đã nhận và điều tra một lần xử lý | Hệ thống lưu trữ/truy vấn trace |

Khi chỉ tạo span trực tiếp, vòng đời cơ bản là bắt đầu span → mở scope khi cần → xử lý công việc → đóng scope → kết thúc span. Việc mở scope giúp mã chạy bên trong tìm thấy span hiện tại, nhưng vẫn phải kết thúc span để hoàn tất việc ghi nhận.

Không tạo đồng thời một observation và một span thủ công bao quanh đúng cùng một thao tác chỉ vì nghĩ “cả hai đều cần cho tracing”. Nếu handler observation đã tạo span phù hợp, thêm một span nữa có thể khiến cây trace có các lớp thừa.

## 8. Tích hợp trong Spring Boot 3.3.x

### 8.1. Dependency thể hiện từng vai trò

Trong một ứng dụng Boot đã có plugin/BOM, một lựa chọn dùng OpenTelemetry và OTLP là:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'
}
```

Đây là phần dependency trong build hiện có, không phải toàn bộ một dự án Gradle. Boot quản lý các phiên bản tương thích; không tự ghép các phiên bản của ví dụ độc lập phía sau vào ứng dụng Boot.

Một số tổ hợp được Boot 3.3 hỗ trợ:

| Tracer/bridge | Thành phần xuất trace | Nhóm cấu hình đầu nhận |
| --- | --- | --- |
| `micrometer-tracing-bridge-otel` | `opentelemetry-exporter-otlp` | `management.otlp.tracing.*` |
| `micrometer-tracing-bridge-otel` | `opentelemetry-exporter-zipkin` | `management.zipkin.tracing.*` |
| `micrometer-tracing-bridge-brave` | `io.zipkin.reporter2:zipkin-reporter-brave` | `management.zipkin.tracing.*` |

Tất cả các hàng đều giả định có hạ tầng Actuator phù hợp. Bridge nằm trong nhóm `io.micrometer`; các exporter OpenTelemetry nằm trong nhóm `io.opentelemetry`.

Chọn một đường tracing rõ ràng cho ví dụ triển khai. Không thêm cả hai bridge chỉ để “chắc chắn có tracing” rồi bỏ qua việc xác định tracer và auto-configuration nào đang hoạt động. [Spring Boot 3.3: các tổ hợp tracer và exporter](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

### 8.2. Dùng hạ tầng Boot đã cấu hình

Trong mã nghiệp vụ, inject registry/tracer do ứng dụng quản lý. Tự gọi `ObservationRegistry.create()` trong một service sẽ tạo registry khác; registry đó không tự có các handler mà Boot đã đăng ký.

Với một thao tác có sẵn logic quan sát từ framework, hãy kiểm tra dữ liệu hiện tại trước khi bổ sung mã quan sát cùng ranh giới. Cũng không tự đăng ký thêm các handler mặc định vào registry Boot nếu auto-configuration đã cung cấp chúng.

Để thấy đầy đủ các lượt trong môi trường học tập, có thể cấu hình lấy mẫu tracing:

```yaml
management:
  tracing:
    sampling:
      probability: 1.0
```

Đây là lấy mẫu cho tracing, không phải tỷ lệ quyết định timer ghi bao nhiêu lượt. Nó cũng không sửa lỗi đầu nhận, giao thức hoặc kết nối exporter. Một span đã được chọn ghi nhận vẫn cần đường xuất dữ liệu hoạt động để xuất hiện ở nơi truy vấn.

Không cần thêm endpoint nghiệp vụ chỉ để chứng minh các lớp thư viện phối hợp. Thí nghiệm trong bộ nhớ dưới đây đủ để kiểm tra quan hệ Observation → handler → tracer và metric.

## 9. Thực nghiệm: cùng mã Observation, có hoặc không có tracing handler

### 9.1. Mục tiêu và môi trường

Thí nghiệm dùng JDK 21, Micrometer Core/Observation 1.13.0, Micrometer Tracing bridge Brave 1.3.0 và Brave 6.0.3 theo dependency của bridge. Đây là thế hệ thư viện của Boot 3.3.0, được cố định cho một thư mục thí nghiệm độc lập.

Chương trình có hai chế độ:

- `both`: đăng ký cả handler metric và handler tracing.
- `metrics-only`: giữ handler metric, không đăng ký handler tracing.

Trong cả hai chế độ, phần mã tạo observation nghiệp vụ giống nhau. Span hoàn tất được thu trong bộ nhớ bằng một `SpanHandler` của Brave; chương trình không gửi trace qua mạng và không cần hệ thống lưu trữ trace.

### 9.2. Dependency trong pom.xml

Tạo `pom.xml` trong thư mục riêng:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>observation-tracing-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-tracing-bridge-brave</artifactId>
            <version>1.3.0</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-nop</artifactId>
            <version>1.7.36</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
</project>
```

Maven giải quyết các dependency bắc cầu của bridge, bao gồm Micrometer Tracing và Brave. Dependency `slf4j-nop` chỉ phục vụ thí nghiệm không xuất log qua SLF4J; nó không phải thành phần tạo metric/span.

### 9.3. Toàn bộ ObservationTracingDemo.java

Lưu cạnh `pom.xml`, không khai báo package:

```java
import java.util.ArrayList;
import java.util.List;

import brave.Tracing;
import brave.handler.MutableSpan;
import brave.handler.SpanHandler;
import brave.propagation.TraceContext;
import brave.sampler.Sampler;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.brave.bridge.BraveCurrentTraceContext;
import io.micrometer.tracing.brave.bridge.BraveTracer;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;

public class ObservationTracingDemo {
    public static void main(String[] args) {
        String mode = args.length == 0 ? "both" : args[0];
        if (!mode.equals("both") && !mode.equals("metrics-only")) {
            throw new IllegalArgumentException("Use both or metrics-only");
        }
        boolean tracingEnabled = mode.equals("both");
        List<MutableSpan> finished = new ArrayList<>();

        SpanHandler collector = new SpanHandler() {
            @Override
            public boolean end(TraceContext context, MutableSpan span, Cause cause) {
                finished.add(new MutableSpan(span));
                return true;
            }
        };

        var meters = new SimpleMeterRegistry();
        try (Tracing brave = Tracing.newBuilder()
                .localServiceName("observation-demo")
                .sampler(Sampler.ALWAYS_SAMPLE)
                .addSpanHandler(collector)
                .build()) {
            Tracer tracer = new BraveTracer(brave.tracer(),
                    new BraveCurrentTraceContext(brave.currentTraceContext()));
            var observations = ObservationRegistry.create();
            observations.observationConfig()
                    .observationHandler(new DefaultMeterObservationHandler(meters));
            if (tracingEnabled) {
                observations.observationConfig()
                        .observationHandler(new DefaultTracingObservationHandler(tracer));
            }

            System.out.println("mode=" + mode);
            int result = Observation.createNotStarted("checkout", observations)
                    .contextualName("checkout-flow")
                    .lowCardinalityKeyValue("channel", "demo")
                    .highCardinalityKeyValue("order.id", "ORD-42")
                    .observe(() -> {
                        System.out.println("observation.current="
                                + (observations.getCurrentObservation() != null));
                        System.out.println("span.current=" + (tracer.currentSpan() != null));
                        return Observation.createNotStarted("payment", observations)
                                .contextualName("payment-check")
                                .observe(() -> 42);
                    });

            var checkoutTimer = meters.get("checkout").timer();
            System.out.println("result=" + result);
            System.out.println("checkout.timer.count=" + checkoutTimer.count());
            System.out.println("payment.timer.count="
                    + meters.get("payment").timer().count());
            System.out.println("metric.high.tag.absent="
                    + (checkoutTimer.getId().getTag("order.id") == null));
            System.out.println("finished.spans=" + finished.size());
            System.out.println("span.names=" + finished.stream()
                    .map(MutableSpan::name).toList());
            System.out.println("observation.cleared="
                    + (observations.getCurrentObservation() == null));
            System.out.println("span.cleared=" + (tracer.currentSpan() == null));

            if (checkoutTimer.count() != 1
                    || meters.get("payment").timer().count() != 1
                    || finished.size() != (tracingEnabled ? 2 : 0)
                    || observations.getCurrentObservation() != null
                    || tracer.currentSpan() != null) {
                throw new AssertionError("Unexpected observation results");
            }

            if (tracingEnabled) {
                MutableSpan parent = find(finished, "checkout-flow");
                MutableSpan child = find(finished, "payment-check");
                boolean sameTrace = parent.traceId().equals(child.traceId());
                boolean parentMatches = parent.id().equals(child.parentId());
                System.out.println("same.trace=" + sameTrace);
                System.out.println("parent.matches=" + parentMatches);
                System.out.println("span.low.tag=" + parent.tag("channel"));
                System.out.println("span.high.tag=" + parent.tag("order.id"));

                Span direct = tracer.nextSpan().name("span-only").start();
                try (Tracer.SpanInScope scope = tracer.withSpan(direct)) {
                    direct.tag("mode", "direct");
                } finally {
                    direct.end();
                }
                System.out.println("direct.span.finished="
                        + finished.stream().anyMatch(s -> "span-only".equals(s.name())));
                System.out.println("direct.timer.exists="
                        + (meters.find("span-only").timer() != null));
                if (!sameTrace || !parentMatches || finished.size() != 3
                        || meters.find("span-only").timer() != null) {
                    throw new AssertionError("Unexpected tracing relationship");
                }
            }
        } finally {
            meters.close();
        }
    }

    static MutableSpan find(List<MutableSpan> spans, String name) {
        return spans.stream().filter(span -> name.equals(span.name()))
                .findFirst().orElseThrow();
    }
}
```

Một số điểm cần chú ý trong mã:

- Biến `tracer` có kiểu `io.micrometer.tracing.Tracer`; giá trị là `BraveTracer`, còn `brave.tracer()` cung cấp tracer gốc.
- `DefaultTracingObservationHandler` nối registry observation với tracer đó.
- `DefaultMeterObservationHandler` ghi số liệu vào `SimpleMeterRegistry`, độc lập với việc có đăng ký handler tracing hay không.
- `Sampler.ALWAYS_SAMPLE` làm kết quả số span trong thí nghiệm xác định được; không dự đoán một tỷ lệ ngẫu nhiên.
- `SpanHandler` thu bản sao span đã hoàn tất. Đây là API của Brave, khác với `ObservationHandler` của Micrometer.
- Các observation dùng `observe(...)` để quản lý scope và kết thúc. Span tạo trực tiếp dùng `finally` để kết thúc.
- Mã đơn hàng `ORD-42` là dữ liệu giả phục vụ đối chiếu nhãn trong thí nghiệm.

### 9.4. Biên dịch và chạy

Chọn JDK 21 cho cả `javac` và `java`, có Maven, rồi chạy trong PowerShell. Chỉ chuyển sang lệnh tiếp theo khi lệnh trước thành công:

```powershell
mvn org.apache.maven.plugins:maven-dependency-plugin:3.7.0:build-classpath "-Dmdep.outputFile=classpath.txt"
$demoClasspath = (Get-Content -Raw classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp "$demoClasspath" ObservationTracingDemo.java
java -cp ".;$demoClasspath" ObservationTracingDemo both
java -cp ".;$demoClasspath" ObservationTracingDemo metrics-only
```

Lần đầu cần truy cập kho Maven để tải dependency. Dấu `;` là dấu phân cách classpath của Windows; trên Linux/macOS dùng `:`.

Stdout của chế độ `both`, không tính thông báo của Maven:

```text
mode=both
observation.current=true
span.current=true
result=42
checkout.timer.count=1
payment.timer.count=1
metric.high.tag.absent=true
finished.spans=2
span.names=[payment-check, checkout-flow]
observation.cleared=true
span.cleared=true
same.trace=true
parent.matches=true
span.low.tag=demo
span.high.tag=ORD-42
direct.span.finished=true
direct.timer.exists=false
```

Stdout của chế độ `metrics-only`:

```text
mode=metrics-only
observation.current=true
span.current=false
result=42
checkout.timer.count=1
payment.timer.count=1
metric.high.tag.absent=true
finished.spans=0
span.names=[]
observation.cleared=true
span.cleared=true
```

Chương trình không in trace ID/span ID cụ thể vì các giá trị đó được tạo lúc chạy. Thay vào đó, nó kiểm tra các quan hệ bằng boolean. Không gán trước một thời lượng cố định cho timer.

### 9.5. Kết quả chứng minh điều gì?

| Bằng chứng | Kết luận trong phạm vi thí nghiệm |
| --- | --- |
| Cả hai chế độ đều có hai timer, mỗi timer count bằng 1 | Mã observation và handler metric vẫn hoạt động khi không có handler tracing |
| `span.current=true` trong `both` | Scope observation đã làm span do handler tạo trở thành hiện tại |
| `span.current=false` trong `metrics-only` | Có observation hiện tại không đồng nghĩa với có span hiện tại |
| `finished.spans=2` trong `both` | Hai observation đã tạo và hoàn tất hai span qua bridge Brave |
| `same.trace=true`, `parent.matches=true` | Span thanh toán dùng cùng trace và nhận đúng span đặt hàng làm cha |
| `span.names=[payment-check, checkout-flow]` | Span con kết thúc trước span cha; tên lấy từ contextual name trong cấu hình này |
| `metric.high.tag.absent=true` nhưng `span.high.tag=ORD-42` | Nhãn nhiều giá trị không được thêm vào timer nhưng có trên span |
| Hai dòng `cleared=true` | Sau lời gọi, scope đã trả ngữ cảnh hiện tại về trạng thái không có observation/span |
| `direct.span.finished=true`, `direct.timer.exists=false` | Gọi Micrometer Tracer trực tiếp tạo span riêng, không tự tạo timer cùng tên |

Trong `metrics-only`, tracer/bridge vẫn được khởi tạo và có mặt trên classpath, nhưng không được nối với registry bằng handler tracing. Điều này chủ động tách hai câu hỏi: “có thư viện tracer không?” và “observation có được chuyển thành span không?”.

Kết quả `finished.spans=2` được in trước phần tạo span trực tiếp. Sau phần đó, danh sách trong bộ nhớ có ba span; assertion của chương trình kiểm tra đúng thứ tự này.

Thí nghiệm chưa chứng minh khả năng truyền trace qua hai dịch vụ hoặc xuất thành công tới một hệ thống bên ngoài. Hai khả năng ấy cần kiểm tra ranh giới truyền ngữ cảnh và exporter tương ứng.

## 10. Cách khoanh vùng khi metric có nhưng trace không có

Hãy kiểm tra theo đường đi của dữ liệu:

1. **Observation:** mã có thực sự chạy, observation có bị bỏ qua, registry có đúng là registry của ứng dụng không?
2. **Handler:** registry có handler tracing phù hợp, hay chỉ có handler metric?
3. **Tracer/bridge:** ứng dụng đang dùng triển khai nào; có đang dùng tracer không thực hiện ghi dữ liệu không?
4. **Scope và ngữ cảnh:** kiểm tra span hiện tại ở bên trong phạm vi cần xét, không chỉ ở sau khi scope đã đóng.
5. **Lấy mẫu và kết thúc:** span có được chọn ghi nhận và đã kết thúc chưa?
6. **Xuất dữ liệu:** reporter/exporter, đầu nhận và giao thức có khớp nhau; dữ liệu đã được xử lý/chuyển tiếp tới nơi truy vấn chưa?

`tracer.currentSpan() != null` không tự chứng minh span được xuất. Ngược lại, `currentSpan() == null` sau khi scope đóng là kết quả bình thường, không có nghĩa span đã bị mất khỏi nơi lưu trữ.

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| Có Actuator là chắc chắn có trace gửi đi | Còn cần tracer/bridge, handler và đường xuất dữ liệu phù hợp |
| Bridge chính là exporter | Bridge nối API; exporter/reporter vận chuyển dữ liệu |
| Chọn Brave đồng nghĩa phải viết nghiệp vụ bằng brave.Tracer | Có thể dùng API Micrometer qua bridge |
| Dùng OpenTelemetry là bắt buộc bỏ Micrometer Observation | Observation có thể dùng Micrometer Tracing bridge OpenTelemetry |
| Mỗi metric tương ứng đúng một trace | Metric tổng hợp nhiều lượt; trace thể hiện các lượt được ghi nhận |
| Thêm span trực tiếp cũng tự thêm timer | Tracer API riêng không tự đi qua nhánh metric của Observation |
| Tag của span tự thành header gửi sang dịch vụ khác | Truyền ngữ cảnh/baggage cần cơ chế và cấu hình tương ứng |
| Có log chứa trace ID là trace chắc chắn đã tới nơi lưu trữ | Tương quan log và xuất trace là hai bước cần kiểm chứng riêng |

## 11. Bài tập tự kiểm tra

1. Chạy hai chế độ và chỉ ra dòng chứng minh Observation không phụ thuộc bắt buộc vào việc tạo span.
2. Đổi riêng `contextualName` của observation đặt hàng. Kiểm tra tên span thay đổi nhưng tra timer vẫn theo tên `checkout` trong cấu hình hiện tại.
3. Đổi `order.id` từ nhãn nhiều giá trị sang nhãn ít giá trị trong thí nghiệm. Quan sát nhãn timer và giải thích vì sao cách này không phù hợp khi số đơn hàng tăng không giới hạn.
4. Giữ bridge/tracer nhưng không đăng ký handler tracing. Giải thích vì sao đây vẫn chưa phải một chuỗi Observation → span hoàn chỉnh.
5. Chỉ ra thành phần cần thay khi chuyển từ Brave sang OpenTelemetry, và thành phần cần thêm khi muốn đưa span ra khỏi bộ nhớ.
6. Với một đường gọi thật, xác định riêng nơi tạo observation, handler tracing, bridge, tracer và exporter. Kiểm tra một bước tại một thời điểm để biết chính xác dữ liệu dừng ở đâu.

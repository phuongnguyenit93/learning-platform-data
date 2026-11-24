# MeterRegistry giữ meter và cung cấp API tạo phép đo như thế nào

`MeterRegistry` là điểm quản lý trung tâm của Micrometer để đăng ký, tra cứu và quản lý các meter trong một ứng dụng. Khi service cần đếm sự kiện, đo thời lượng hoặc đọc trạng thái hiện tại, service sử dụng API của registry để tạo hay lấy lại meter phù hợp. Registry giữ các meter đã đăng ký, áp dụng cấu hình chung và kết nối chúng với cơ chế xuất dữ liệu của hệ thống giám sát.

Có thể xem registry như một nơi quản lý các phép đo của ứng dụng: mã nghiệp vụ mô tả đại lượng cần đo; registry quản lý định danh và vòng đời meter; registry cụ thể quyết định cách dữ liệu được lưu tạm hoặc xuất đến backend. Nhờ abstraction này, service có thể dùng API Micrometer ổn định trong khi ứng dụng thay đổi backend metrics.

## 1. Vai trò của MeterRegistry

`MeterRegistry` là lớp trừu tượng trung tâm trong Micrometer. Nó đảm nhiệm một số trách nhiệm:

- Cung cấp API tạo và đăng ký Counter, Gauge, Timer, DistributionSummary cùng các loại meter khác.
- Quản lý meter đã đăng ký trong registry theo định danh của chúng.
- Kết hợp tên, tag, loại meter, mô tả và đơn vị thành metadata của meter.
- Áp dụng cấu hình như common tags, naming convention và meter filters.
- Cung cấp các phép đo cho registry/exporter tương ứng để hệ thống nhận thu thập.
- Quản lý tài nguyên của registry, chẳng hạn việc đóng các thành phần có kết nối hoặc luồng nền khi ứng dụng dừng.

Trong ứng dụng Spring Boot, service thường nhận `MeterRegistry` qua dependency injection. Service không cần biết dữ liệu cuối cùng được gửi đến Prometheus, OTLP hay hệ thống khác bằng cách nào. Việc cấu hình backend thuộc tầng ứng dụng.

Một registry có thể được tạo trực tiếp trong chương trình Micrometer độc lập hoặc được Spring Boot cấu hình tự động. Trong cả hai trường hợp, mã đo lường vẫn sử dụng cùng các API chính.

## 2. Meter và Meter.Id

Meter là đối tượng biểu diễn một phép đo. Mỗi meter có một định danh `Meter.Id`, bao gồm các thông tin quan trọng như:

- **Name:** tên logic của phép đo, ví dụ `orders.accepted`.
- **Tags:** các cặp key-value dùng để phân loại chuỗi thời gian.
- **Type:** loại meter, ví dụ Counter, Gauge, Timer hoặc DistributionSummary.
- **Base unit:** đơn vị cơ sở nếu có, ví dụ bytes hoặc seconds.
- **Description:** mô tả ý nghĩa của phép đo.

Tên và tag là phần cốt lõi để phân biệt các meter trong một registry. Ví dụ, `orders.process` với `channel=web` và `orders.process` với `channel=mobile` là hai định danh khác nhau vì bộ tag khác nhau.

~~~java
Counter webOrders = Counter.builder("orders.accepted")
        .tag("channel", "web")
        .description("Number of accepted orders")
        .register(meterRegistry);

Counter mobileOrders = Counter.builder("orders.accepted")
        .tag("channel", "mobile")
        .description("Number of accepted orders")
        .register(meterRegistry);
~~~

Hai Counter trên cùng tên nhưng có hai bộ tag khác nhau. Backend có thể lưu chúng thành hai chuỗi thời gian riêng biệt. Đây là cách biểu diễn các chiều phân loại của cùng một đại lượng.

Khi một meter cùng định danh được đăng ký lại, registry thường trả về meter đã được quản lý thay vì tạo một meter độc lập khác. Vì vậy, nhiều thành phần có thể lấy cùng một meter nếu chúng dùng chung registry, tên và tag. Cần bảo đảm chúng cùng thống nhất về ý nghĩa và loại meter.

Không dùng cùng một định danh cho các phép đo khác bản chất. Ví dụ, không đăng ký Counter và Gauge với cùng tên và bộ tag rồi kỳ vọng registry hiểu đó là hai đại lượng khác nhau. Xung đột loại meter có thể bị từ chối khi đăng ký. Hãy chọn tên riêng cho từng ý nghĩa.

## 3. Đăng ký meter qua API của registry

Micrometer cung cấp hai cách phổ biến để đăng ký meter:

1. Dùng builder khi cần khai báo description, base unit, tag hoặc cấu hình riêng.
2. Dùng phương thức tiện ích của registry khi chỉ cần đăng ký nhanh với tên và tag.

### Counter

Counter biểu diễn số lần một sự kiện xảy ra. Giá trị chỉ tăng:

~~~java
Counter accepted = meterRegistry.counter(
        "orders.accepted",
        "channel", "web"
);

accepted.increment();
accepted.increment(2.0);
~~~

Có thể dùng builder khi cần metadata:

~~~java
Counter failed = Counter.builder("orders.failed")
        .description("Number of orders that failed processing")
        .tag("stage", "validation")
        .register(meterRegistry);
~~~

Nên đăng ký meter ở nơi khởi tạo thành phần hoặc dùng một hàm tiện ích có chủ đích, sau đó tái sử dụng đối tượng Counter. Không cần gọi builder liên tục trong vòng lặp xử lý nếu tên và tag không đổi.

### Gauge

Gauge đọc giá trị hiện tại từ một đối tượng hoặc hàm truy xuất:

~~~java
AtomicInteger queueDepth = new AtomicInteger();

Gauge.builder("orders.queue.depth", queueDepth, AtomicInteger::get)
        .description("Current number of queued orders")
        .register(meterRegistry);
~~~

Registry lấy mẫu giá trị gauge khi thu thập dữ liệu. Gauge phù hợp với độ sâu hàng đợi, số kết nối đang mở hoặc số tác vụ đang hoạt động. Nó không phải bộ đếm sự kiện tích lũy.

Micrometer Gauge thường giữ tham chiếu yếu đến đối tượng được quan sát. Ứng dụng cần giữ tham chiếu mạnh đến đối tượng trong suốt thời gian cần đo. Nếu đối tượng bị garbage collector thu hồi, gauge có thể không còn giá trị hữu ích để đọc.

### Timer

Timer đo thời lượng và số lần ghi nhận:

~~~java
Timer authorization = Timer.builder("payment.authorization")
        .description("Time spent authorizing a payment")
        .register(meterRegistry);

PaymentResult result = authorization.record(
        () -> paymentGateway.authorize(command)
);
~~~

Timer phù hợp với thời gian xử lý request, truy vấn database hoặc lời gọi dịch vụ bên ngoài. Khi cần thống kê số lần và tổng thời lượng của cùng thao tác, Timer đã cung cấp cả hai thông tin đó.

### DistributionSummary

DistributionSummary ghi nhận phân bố của một đại lượng số không phải thời gian:

~~~java
DistributionSummary payloadSize =
        DistributionSummary.builder("http.request.payload.size")
                .description("HTTP request payload size")
                .baseUnit("bytes")
                .register(meterRegistry);

payloadSize.record(payload.length);
~~~

Summary phù hợp với kích thước payload, số phần tử xử lý mỗi batch hoặc dung lượng dữ liệu. Nếu cần histogram hoặc percentile, cấu hình phù hợp trên meter và registry nhận.

## 4. Registry quản lý meter như thế nào?

Khi ứng dụng đăng ký meter, có thể hình dung luồng xử lý khái quát:

~~~mermaid
flowchart TD
    A[Service yêu cầu một meter] --> B[MeterRegistry nhận tên và tag]
    B --> C[Áp dụng cấu hình và MeterFilter]
    C --> D{Định danh đã tồn tại?}
    D -- Có --> E[Lấy meter đã đăng ký]
    D -- Không --> F[Tạo và đăng ký meter]
    E --> G[Service ghi nhận số đo]
    F --> G
    G --> H[Registry cụ thể lưu hoặc xuất dữ liệu]
    H --> I[Backend giám sát thu thập]
~~~

Luồng này giúp tránh việc mỗi lần gọi đều tạo một phép đo tách biệt cho cùng định danh. Registry quản lý tập meter đã đăng ký, còn các thao tác như `increment()`, `record()` hoặc đọc Gauge cập nhật dữ liệu của meter đó.

Với một định danh gồm tên và bộ tag ổn định, ứng dụng nên giữ lại tham chiếu meter và dùng lại trong các lần xử lý. Cách này giúp mã rõ ràng, tránh chi phí tìm kiếm/đăng ký lặp lại và hạn chế việc tạo tag động không kiểm soát.

Không nên tạo tên hoặc tag chứa request ID, order ID hay timestamp. Mỗi tổ hợp tên và tag có thể trở thành một chuỗi thời gian riêng; số lượng định danh tăng không giới hạn sẽ làm registry và backend chịu tải lớn.

## 5. Các loại MeterRegistry phổ biến

Micrometer cung cấp nhiều triển khai registry để phục vụ các mục đích khác nhau. Mã ứng dụng có thể phụ thuộc vào abstraction `MeterRegistry` thay vì phụ thuộc trực tiếp vào một triển khai cụ thể.

| Registry | Mục đích | Đặc điểm |
|---|---|---|
| `SimpleMeterRegistry` | Phát triển và kiểm thử | Giữ số đo trong bộ nhớ, không tự xuất đến backend |
| `PrometheusMeterRegistry` | Tích hợp Prometheus | Cung cấp dữ liệu theo định dạng Prometheus để scrape |
| `CompositeMeterRegistry` | Kết hợp nhiều registry | Chuyển các meter đến các registry con đã thêm |
| Registry cho backend khác | Xuất dữ liệu đến hệ thống tương ứng | Mỗi triển khai áp dụng định dạng, naming convention và cơ chế xuất riêng |

### SimpleMeterRegistry

SimpleMeterRegistry hữu ích khi muốn kiểm tra số đo mà không cần một máy chủ metrics:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

Counter counter = registry.counter("demo.events");
counter.increment();

assertThat(counter.count()).isEqualTo(1.0);
~~~

Registry này lưu số đo trong bộ nhớ của tiến trình. Khi ứng dụng kết thúc, dữ liệu không được gửi tự động đến hệ thống giám sát. Vì vậy, nó phù hợp cho unit test hoặc ví dụ nhỏ, không thay thế registry xuất dữ liệu ở môi trường vận hành.

### Registry dành cho backend

Một registry như PrometheusMeterRegistry biết cách biểu diễn meter theo định dạng mà Prometheus có thể scrape. Các registry khác có thể đẩy dữ liệu theo chu kỳ, gửi qua giao thức hoặc cung cấp endpoint riêng.

Service nên sử dụng API chung để đăng ký meter. Cấu hình registry, dependency exporter, endpoint và thông tin kết nối được quản lý ở tầng ứng dụng hoặc cấu hình Spring Boot.

### CompositeMeterRegistry

CompositeMeterRegistry cho phép kết hợp nhiều registry:

~~~java
CompositeMeterRegistry composite = new CompositeMeterRegistry();
composite.add(prometheusRegistry);
composite.add(otherRegistry);

Counter counter = composite.counter("orders.accepted");
counter.increment();
~~~

Meter được đăng ký qua composite có thể được chuyển đến các registry con. Cách này hữu ích khi một ứng dụng cần xuất cùng phép đo đến nhiều hệ thống. Cần cân nhắc chi phí và mục đích của từng backend, vì mỗi registry bổ sung có thể làm tăng lưu lượng và lượng dữ liệu cần quản lý.

Nếu composite chưa có registry con, không nên giả định dữ liệu đã ghi trước thời điểm thêm registry sẽ được phát lại đầy đủ. Hãy cấu hình các registry con trước khi ứng dụng bắt đầu ghi số đo và xác minh hành vi với phiên bản Micrometer đang dùng.

## 6. Cấu hình chung qua MeterRegistry.Config

Registry cung cấp đối tượng cấu hình để áp dụng quy tắc chung cho các meter. Một số cấu hình thường dùng gồm:

- Common tags: thêm các tag dùng chung cho meter trong registry.
- Meter filters: chấp nhận, từ chối hoặc điều chỉnh meter khi đăng ký.
- Naming convention: chuyển tên meter và tag theo quy tắc của registry.
- Listener hoặc hook: nhận biết sự kiện meter được thêm hoặc bị loại bỏ, tùy API và triển khai.

### Common tags

Common tags giúp bổ sung thông tin chung như tên ứng dụng hoặc môi trường:

~~~java
registry.config().commonTags(
        "application", "order-service",
        "environment", "production"
);
~~~

Sau cấu hình, các meter được đăng ký trong registry sẽ mang các tag chung đó cùng tag riêng của chúng. Common tags hữu ích để lọc và so sánh metrics giữa các service hoặc môi trường.

Hãy cấu hình common tags trước khi đăng ký meter. Không nên kỳ vọng thay đổi common tags sau đó sẽ sửa lại các meter đã được tạo. Các tag chung cũng phải có tập giá trị nhỏ và ổn định; không đưa request ID hay user ID vào common tags.

### MeterFilter

MeterFilter cho phép kiểm soát meter khi chúng được đăng ký. Có thể dùng filter để từ chối meter theo tên, điều chỉnh ID, thêm hoặc sửa cấu hình, hay giới hạn số lượng tag.

Ví dụ giới hạn số giá trị của tag `region` trên meter có tên bắt đầu bằng `orders.`:

~~~java
registry.config().meterFilter(
        MeterFilter.maximumAllowableTags(
                "orders.",
                "region",
                5,
                MeterFilter.deny()
        )
);
~~~

Filter này minh họa cách giới hạn cardinality cho một nhóm meter. Khi vượt ngưỡng, filter áp dụng hành vi từ chối đã cấu hình. Trong ứng dụng thực tế, hãy chọn ngưỡng theo số vùng hợp lệ và cách backend xử lý meter bị từ chối.

MeterFilter cũng có thể từ chối một meter không cần thiết:

~~~java
registry.config().meterFilter(
        MeterFilter.denyNameStartsWith("debug.")
);
~~~

Nên đặt filter trong cấu hình ứng dụng, ghi rõ lý do và kiểm thử kết quả. Nếu filter từ chối meter quan trọng, dashboard hoặc alert có thể thiếu dữ liệu mà không dễ nhận ra.

## 7. MeterBinder: đăng ký một nhóm meter có liên quan

Khi một thành phần cần đăng ký nhiều meter, có thể đóng gói việc đăng ký trong `MeterBinder`. Interface này cung cấp phương thức `bindTo(MeterRegistry)` để thành phần gắn các phép đo của nó vào registry được cung cấp.

Ví dụ:

~~~java
final class QueueMetrics implements MeterBinder {
    private final AtomicInteger queueDepth;

    QueueMetrics(AtomicInteger queueDepth) {
        this.queueDepth = queueDepth;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder("jobs.queue.depth", queueDepth, AtomicInteger::get)
                .description("Current number of queued jobs")
                .register(registry);
    }
}
~~~

MeterBinder giúp tách phần định nghĩa instrumentation khỏi nơi tạo registry. Thành phần có thể được bind vào một registry trong kiểm thử hoặc môi trường khác nhau mà không phải viết lại logic đo lường.

Micrometer và Spring Boot cũng có các binder cho những nguồn thông tin phổ biến như JVM, hệ điều hành, bộ nhớ đệm hoặc executor. Các binder được cấu hình phù hợp có thể tự đăng ký nhóm meter liên quan. Chỉ bật binder cần thiết và kiểm soát tag để tránh thu thập dữ liệu không phục vụ mục tiêu vận hành.

## 8. Sử dụng MeterRegistry trong Spring Boot

Spring Boot Actuator và các registry Micrometer tương ứng có thể tự cấu hình một MeterRegistry dựa trên dependency và application properties. Service thường inject abstraction này qua constructor:

~~~java
@Service
final class OrderService {
    private final Counter acceptedOrders;

    OrderService(MeterRegistry registry) {
        this.acceptedOrders = Counter.builder("orders.accepted")
                .description("Number of accepted orders")
                .register(registry);
    }

    void accept(Order order) {
        // Perform the business operation.
        acceptedOrders.increment();
    }
}
~~~

Trong môi trường có Prometheus registry, ứng dụng có thể bật endpoint scrape qua cấu hình Actuator. Service vẫn dùng `MeterRegistry` và không cần gọi API riêng của Prometheus.

Một số nguyên tắc tích hợp:

1. Ưu tiên dùng registry do Spring quản lý và inject qua constructor.
2. Không tự tạo `new SimpleMeterRegistry()` trong service production nếu mục tiêu là xuất metrics đến backend đã cấu hình.
3. Đăng ký meter một lần và tái sử dụng trong vòng đời bean.
4. Cấu hình common tags và filter ở tầng cấu hình, trước khi meter được đăng ký.
5. Kiểm tra endpoint hoặc luồng export để chắc chắn meter thực sự đến được hệ thống nhận.

Nếu ứng dụng có nhiều MeterRegistry bean, cần xác định rõ registry nào được inject hoặc sử dụng composite theo chủ đích. Tránh để service tự chọn backend bằng cách phụ thuộc trực tiếp vào một lớp registry cụ thể khi không cần thiết.

## 9. Vòng đời và tài nguyên của registry

Registry thường sống cùng vòng đời ứng dụng. Trong Spring Boot, container quản lý các bean và có thể đóng registry khi context dừng. Với ứng dụng tạo registry thủ công, mã khởi tạo cần quản lý việc đóng registry nếu triển khai đó có tài nguyên cần giải phóng.

Ví dụ cho chương trình độc lập:

~~~java
try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
    Counter counter = registry.counter("demo.events");
    counter.increment();
    System.out.println(counter.count());
}
~~~

Không tạo một registry mới cho mỗi request hoặc mỗi lần gọi service. Cách đó làm phân tán meter, tăng chi phí và khiến dữ liệu không còn được tổng hợp trong một nơi quản lý ổn định.

Registry nên được chia sẻ theo phạm vi ứng dụng hoặc phạm vi cấu hình có chủ đích. Nếu cần tách số đo giữa các tenant, vùng hoặc subsystem, trước tiên hãy cân nhắc tag có cardinality kiểm soát và yêu cầu bảo mật dữ liệu; chỉ tạo registry riêng khi có lý do về vòng đời hoặc cấu hình backend.

## 10. Tra cứu và quản lý meter

Registry hỗ trợ tra cứu meter theo tên và tag. API `find` hữu ích trong kiểm thử hoặc công cụ quản trị:

~~~java
Counter counter = registry.find("orders.accepted")
        .tag("channel", "web")
        .counter();

assertThat(counter).isNotNull();
assertThat(counter.count()).isEqualTo(3.0);
~~~

Tra cứu nên dùng cùng định danh đã đăng ký. Nếu thiếu hoặc khác tag, kết quả có thể không tìm thấy meter mong muốn. Không nên dùng thao tác tra cứu trong đường xử lý nóng thay cho việc giữ tham chiếu meter khi đã biết trước tên và tag.

Registry cũng cung cấp API để loại bỏ meter hoặc xóa các meter đã đăng ký trong những trường hợp quản trị cụ thể. Các thao tác này cần được sử dụng cẩn thận: xóa meter có thể làm mất dữ liệu trong bộ nhớ của registry và khiến chuỗi thời gian ngừng được xuất. Không xóa meter chỉ để cố giảm cardinality sau khi đã tạo hàng loạt tag động; cần sửa nguyên nhân ở chỗ thiết kế tên và tag.

## 11. Kiểm thử MeterRegistry

SimpleMeterRegistry là lựa chọn thuận tiện cho unit test vì không yêu cầu backend bên ngoài. Kiểm thử có thể xác minh meter được đăng ký, giá trị thay đổi đúng và tag được gắn đúng:

~~~java
class OrderMetricsTest {
    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();

    @Test
    void recordsAcceptedOrders() {
        Counter counter = Counter.builder("orders.accepted")
                .tag("channel", "web")
                .register(registry);

        counter.increment();
        counter.increment(2.0);

        assertThat(registry.find("orders.accepted")
                .tag("channel", "web")
                .counter()
                .count()).isEqualTo(3.0);
    }
}
~~~

Ngoài giá trị, nên kiểm tra:

- Tên logic và tag có đúng quy ước không.
- Meter có đúng loại với ý nghĩa cần đo không.
- Common tags đã được thêm đúng chưa.
- MeterFilter có từ chối hoặc điều chỉnh meter như dự kiến không.
- Meter cùng định danh có được tái sử dụng không.
- Gauge vẫn tham chiếu đến đối tượng có vòng đời phù hợp không.

Unit test với SimpleMeterRegistry không xác minh được tên cuối cùng, định dạng và khả năng gửi dữ liệu của backend production. Cần có kiểm thử tích hợp với registry/exporter thật hoặc kiểm tra endpoint scrape để xác nhận toàn bộ đường đi.

## 12. Các lỗi thường gặp khi dùng registry

**Tạo registry trong từng service.** Các service có thể ghi vào những registry khác nhau, làm số liệu bị chia nhỏ hoặc không đến backend đang được cấu hình. Dùng registry được quản lý chung trong phạm vi ứng dụng.

**Tạo meter liên tục với tag động.** Mỗi bộ tag mới có thể tạo một meter mới. Hãy giới hạn tập giá trị và đăng ký meter một lần cho mỗi định danh cần thiết.

**Dùng cùng tên cho các loại meter khác nhau.** Một định danh cần có ý nghĩa và loại ổn định. Đặt tên riêng cho đại lượng khác nhau.

**Thay đổi common tags sau khi meter đã đăng ký.** Meter đã tồn tại có thể vẫn giữ định danh cũ. Cấu hình common tags trước khi khởi tạo các meter.

**Dùng SimpleMeterRegistry trong production để chờ dữ liệu tự xuất.** SimpleMeterRegistry chỉ giữ dữ liệu trong bộ nhớ. Chọn registry/exporter phù hợp với hệ thống nhận.

**Bỏ qua MeterFilter.** Filter có thể loại bỏ hoặc điều chỉnh meter. Khi một số đo không xuất hiện, hãy kiểm tra filter và cấu hình registry trước khi kết luận instrumentation không chạy.

**Không đóng registry tự tạo.** Một số registry có tài nguyên nền hoặc kết nối cần giải phóng. Quản lý vòng đời registry theo vòng đời ứng dụng.

## 13. Kết luận

MeterRegistry quản lý các meter theo định danh, cung cấp API để đăng ký và tra cứu phép đo, áp dụng quy tắc chung và kết nối instrumentation với cơ chế xuất dữ liệu. Service chỉ cần mô tả đại lượng bằng tên, tag và loại meter phù hợp, sau đó ghi nhận số đo thông qua đối tượng meter được tái sử dụng.

Trong ứng dụng thực tế, hãy dùng một registry có vòng đời ổn định, cấu hình common tags và MeterFilter trước khi đăng ký meter, kiểm soát cardinality và kiểm thử cả lớp Micrometer lẫn lớp exporter. Cách tổ chức này giúp instrumentation nhất quán và cho phép thay đổi backend mà không phải viết lại logic đo lường trong service.

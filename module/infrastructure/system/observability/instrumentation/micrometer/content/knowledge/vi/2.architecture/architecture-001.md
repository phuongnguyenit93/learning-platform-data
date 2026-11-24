# Luồng dữ liệu từ thao tác ứng dụng đến meter, registry và hệ thống nhận

Micrometer tạo một lớp thống nhất giữa mã ứng dụng và các hệ thống giám sát. Khi một thao tác nghiệp vụ xảy ra, mã instrumentation ghi nhận số lần, thời gian hoặc giá trị đo vào một meter. **MeterRegistry** quản lý các meter đó, sau đó cung cấp dữ liệu theo cách mà registry tương ứng hỗ trợ: cho backend chủ động scrape hoặc gửi dữ liệu theo chu kỳ. Backend nhận các mẫu đo, lưu thành chuỗi thời gian để truy vấn, dựng dashboard và thiết lập cảnh báo.

Điểm cần nắm là ứng dụng thường chỉ cập nhật meter trong bộ nhớ. Mỗi lần xử lý request không cần tự tạo một kết nối mạng đến hệ thống giám sát. Việc thu thập, định dạng và chuyển dữ liệu được thực hiện bởi registry cùng cơ chế export hoặc scrape của nó.

## 1. Bức tranh kiến trúc

~~~mermaid
flowchart LR
    A["Thao tác nghiệp vụ"] --> B["Mã instrumentation"]
    B --> C["Meter API<br/>Counter, Timer, Gauge..."]
    C --> D["MeterRegistry"]
    D --> E["Meter được đăng ký và quản lý"]
    E --> F["Thu thập số đo"]
    F --> G["Registry và cơ chế export"]
    G --> H["Backend giám sát"]
    H --> I["Query, dashboard, alert"]
~~~

Luồng này có thể chia thành ba vùng:

- **Trong ứng dụng:** thao tác nghiệp vụ gọi API của Micrometer để cập nhật meter.
- **Trong registry:** meter được đăng ký, quản lý và cung cấp số đo. Registry áp dụng cấu hình phù hợp với hệ thống nhận.
- **Ở hệ thống giám sát:** backend tiếp nhận dữ liệu, lưu trữ và cung cấp khả năng truy vấn, trực quan hóa hoặc cảnh báo.

Một meter được đăng ký trong registry và được mã ứng dụng giữ lại hoặc tra cứu để ghi nhận các lần đo tiếp theo. Registry không phải là một hàng đợi chứa từng sự kiện nghiệp vụ. Counter, timer và distribution summary thường duy trì các thống kê tổng hợp; gauge cung cấp giá trị được đọc tại thời điểm thu thập.

## 2. Các thành phần trong luồng dữ liệu

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Thao tác ứng dụng | Tạo ra sự kiện hoặc trạng thái cần quan sát | Tạo đơn hàng, xử lý HTTP request, số tác vụ đang chạy |
| Instrumentation | Chọn meter và thời điểm ghi nhận | Tăng counter sau khi tạo đơn thành công, đo thời gian xử lý |
| **Meter** | Đại diện cho một phép đo và cung cấp API ghi nhận hoặc đọc số đo | Counter, Timer, Gauge, DistributionSummary |
| **Meter.Id** | Mô tả danh tính và metadata của meter | Tên, tags, loại meter, đơn vị cơ sở, mô tả |
| **MeterRegistry** | Đăng ký, tra cứu và quản lý meter; kết nối API chung với cơ chế thu thập của backend | SimpleMeterRegistry, PrometheusMeterRegistry, CompositeMeterRegistry |
| Export hoặc scrape | Đưa số đo ra khỏi vùng instrumentation của ứng dụng | Endpoint cho Prometheus scrape hoặc tiến trình push theo chu kỳ |
| Backend | Lưu dữ liệu và xử lý truy vấn vận hành | Prometheus, Datadog hoặc một hệ thống nhận metrics tương thích |

### Meter và MeterRegistry khác nhau thế nào?

**Meter** là đối tượng biểu diễn phép đo. Ví dụ, một Timer ghi nhận số lần thực hiện và thời gian thực hiện; một Counter ghi nhận tổng số lần một sự kiện xảy ra.

**MeterRegistry** là nơi đăng ký và quản lý các meter. Khi gọi registry.counter(...) hoặc Timer.builder(...).register(registry), ứng dụng yêu cầu registry tìm meter phù hợp hoặc đăng ký meter mới. Những lần tra cứu sau với cùng tên và cùng tập tags sẽ dùng lại meter đã đăng ký. Vì vậy, nên dùng chung registry của ứng dụng và tránh tạo registry mới trong từng request.

**Meter.Id** mang metadata để mô tả meter. Tên và tập tags là phần đặc biệt quan trọng vì chúng xác định chiều dữ liệu mà backend có thể phân tích. Đơn vị và mô tả giúp người đọc hiểu ý nghĩa số đo; registry có thể chuyển tên hoặc đơn vị sang quy ước riêng của backend.

## 3. Luồng xử lý từ lúc ứng dụng ghi nhận đến lúc backend nhận dữ liệu

### Bước 1: Khởi tạo registry

Trong ứng dụng Spring Boot, dependency của registry thường quyết định loại registry được tự động cấu hình. Ví dụ, ứng dụng có thể dùng registry dành cho Prometheus hoặc một registry hỗ trợ hệ thống giám sát khác. Ứng dụng nhận MeterRegistry thông qua dependency injection và dùng cùng bean đó ở các thành phần cần instrumentation.

Ở giai đoạn khởi tạo, ứng dụng cũng có thể:

- Thêm tags chung như tên service và môi trường chạy.
- Cấu hình MeterFilter để đổi tên, loại bỏ meter hoặc giới hạn tag values.
- Đăng ký các MeterBinder để thu thập metrics có sẵn của JVM, hệ điều hành hoặc thư viện.
- Đăng ký các meter nghiệp vụ cần dùng trong suốt vòng đời ứng dụng.

### Bước 2: Đăng ký meter

Instrumentation chọn meter phù hợp với loại dữ liệu:

- Dùng Counter cho số sự kiện tích lũy.
- Dùng Timer cho thời gian thực hiện và số lần thực hiện.
- Dùng Gauge để quan sát một giá trị trạng thái tại thời điểm thu thập.
- Dùng DistributionSummary cho phân phối của một đại lượng không nhất thiết là thời gian, chẳng hạn kích thước payload.

Meter có thể được đăng ký khi khởi tạo service hoặc khi ứng dụng cần đến nó lần đầu. Với các meter có tags, mỗi tổ hợp tên và tags khác nhau có thể tạo ra một chuỗi thời gian riêng ở backend. Vì thế, giá trị tag phải được kiểm soát ngay từ thiết kế instrumentation.

### Bước 3: Thao tác nghiệp vụ cập nhật meter

Khi một thao tác xảy ra, mã ứng dụng gọi phương thức tương ứng trên meter. Ví dụ, thao tác tạo đơn hàng thành công làm counter tăng một đơn vị; timer ghi nhận thời gian từ lúc bắt đầu đến lúc kết thúc thao tác.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final MeterRegistry registry;
    private final Timer createOrderTimer;

    public OrderService(MeterRegistry registry) {
        this.registry = registry;
        this.createOrderTimer = Timer.builder("orders.create")
            .description("Thời gian xử lý thao tác tạo đơn hàng")
            .tag("operation", "create")
            .register(registry);
    }

    public Order create(CreateOrderCommand command) {
        return createOrderTimer.record(() -> {
            Order order = persist(command);

            registry.counter(
                "orders.created",
                "channel", normalizeChannel(command.channel()),
                "result", "success"
            ).increment();

            return order;
        });
    }

    // persist và normalizeChannel đại diện cho logic nghiệp vụ của ứng dụng.
}
~~~

Trong ví dụ, Timer ghi nhận thời gian của toàn bộ hàm được truyền vào record. Counter chỉ tăng sau khi persist hoàn tất thành công. Tag channel cần được chuẩn hóa về một tập giá trị hữu hạn, chẳng hạn web, mobile, partner và unknown. Không đưa mã đơn hàng, email hoặc request ID vào tags.

Lệnh registry.counter(...) có thể được gọi ở nhiều lần xử lý. Khi tên và tags giống nhau, registry trả về meter đã đăng ký để tiếp tục cập nhật số đo. Nếu mỗi request tạo ra một tag value mới, ứng dụng có thể tạo ra lượng meter và chuỗi thời gian tăng không kiểm soát.

### Bước 4: Registry cung cấp số đo

Meter giữ hoặc tính toán số đo theo semantics của từng loại. Registry quản lý việc truy cập các meter và chuẩn bị dữ liệu cho cơ chế thu thập. Một meter không nhất thiết tương ứng với đúng một chuỗi thời gian ở backend: timer có thể được biểu diễn bằng count, tổng thời gian, max và các bucket histogram; cấu hình cụ thể quyết định những thống kê nào được xuất.

Registry cũng có thể áp dụng quy ước tên và đơn vị của backend. Vì vậy, tên meter trong mã Java có thể khác hình thức tên metric được nhìn thấy trong giao diện backend.

### Bước 5: Export hoặc scrape dữ liệu

Có hai kiểu trao đổi phổ biến:

**Pull (scrape):** backend chủ động gọi endpoint của ứng dụng theo lịch. Registry cung cấp snapshot metrics tại thời điểm được scrape. Prometheus thường hoạt động theo mô hình này. Ứng dụng cần có registry và endpoint scrape phù hợp, đồng thời cấu hình để endpoint được phép truy cập.

**Push:** registry hoặc exporter gửi dữ liệu đến hệ thống nhận theo chu kỳ cấu hình. Một số registry dùng cửa sổ thời gian (step) để tổng hợp và xuất số đo. Dữ liệu không nhất thiết được gửi ngay tại thời điểm mã ứng dụng gọi increment() hoặc record().

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant Registry as MeterRegistry
    participant Meter as Meter
    participant Backend as Backend

    App->>Registry: counter(...), register(...)
    Registry-->>App: Meter đã đăng ký
    App->>Meter: increment() hoặc record()
    Note over Meter,Registry: Registry quản lý meter và số đo
    alt Pull (scrape)
        Backend->>Registry: Scrape / collect
        Registry-->>Backend: Snapshot metrics
    else Push
        Registry->>Backend: Publish metrics theo chu kỳ
    end
~~~

Hai kiểu này khác nhau ở bên khởi tạo việc truyền dữ liệu. Chúng không làm thay đổi cách mã nghiệp vụ gọi Counter, Timer hay Gauge. Chi tiết về thời điểm xuất, cửa sổ tổng hợp và định dạng dữ liệu phụ thuộc registry được chọn.

### Bước 6: Backend lưu trữ và sử dụng metrics

Backend nhận tên metric, tags, đơn vị và các mẫu đo. Hệ thống lưu dữ liệu thành chuỗi thời gian, sau đó cho phép truy vấn theo tên và chiều tags. Dashboard có thể hiển thị tốc độ tạo đơn hàng theo kênh; cảnh báo có thể phát hiện độ trễ tăng hoặc tỷ lệ lỗi vượt ngưỡng.

Backend thường coi mỗi tổ hợp tên metric và tags là một chuỗi thời gian riêng. Vì vậy, tags ảnh hưởng trực tiếp đến dung lượng lưu trữ, chi phí và khả năng truy vấn.

## 4. Dữ liệu được ghi nhận khác nhau theo từng loại meter

| Loại meter | Cách ghi nhận | Cách diễn giải |
| --- | --- | --- |
| Counter | Tăng một lượng không âm bằng increment() hoặc increment(amount) | Tổng số sự kiện tích lũy; tốc độ tăng có thể được backend tính từ các mẫu |
| Gauge | Đọc giá trị hiện tại từ một đối tượng hoặc hàm | Trạng thái tại thời điểm thu thập, ví dụ số phần tử trong queue |
| Timer | Ghi một khoảng thời gian bằng record(...) hoặc recordCallable(...) | Count và tổng thời gian; có thể có max, histogram hoặc percentile tùy cấu hình |
| DistributionSummary | Ghi một giá trị bằng record(value) | Count, tổng và phân phối của đại lượng như kích thước payload |
| LongTaskTimer | Theo dõi tác vụ còn đang chạy | Số tác vụ đang hoạt động và thời gian hoạt động của chúng |
| FunctionCounter | Đọc một bộ đếm tích lũy từ hàm hoặc đối tượng được cung cấp | Quan sát bộ đếm do thành phần khác quản lý |

Một số điểm cần lưu ý:

- Nếu cần đếm số request và đo độ trễ của chúng, Timer thường đã cung cấp count cùng thời gian; không cần tạo thêm counter trùng mục đích nếu không có lý do nghiệp vụ riêng.
- Gauge quan sát giá trị khi registry thu thập. Đối tượng được gauge tham chiếu cần còn tồn tại trong bộ nhớ; nếu đối tượng bị giải phóng, giá trị gauge có thể không còn được cung cấp như mong đợi.
- Percentile được tính phía ứng dụng và histogram bucket có cách tổng hợp khác nhau. Percentile phía ứng dụng hữu ích để quan sát từng instance nhưng không thể cộng gộp trực tiếp như bucket histogram. Khi cần tổng hợp nhiều instance, hãy chọn cấu hình histogram và khả năng hỗ trợ của backend cho phù hợp.

## 5. Tags, naming và kiểm soát cardinality

Tags tạo chiều phân tích cho metrics. Với metric orders.created, các tags channel=web và result=success cho phép truy vấn số đơn theo kênh hoặc kết quả. Các giá trị nên có tập hữu hạn, ổn định và phản ánh câu hỏi vận hành cần trả lời.

| Nên dùng | Tránh dùng |
| --- | --- |
| method=GET hoặc method=POST | Một giá trị method tùy biến không giới hạn |
| status=2xx, status=4xx, status=5xx | Nội dung lỗi tự do |
| uri=/orders/{id} | URL thô như /orders/849203 |
| channel=web, channel=mobile | customerId, orderId, email hoặc request ID |

Cardinality là số lượng tổ hợp giá trị tags khác nhau. Nếu một tag nhận giá trị mới cho từng request hoặc từng người dùng, số chuỗi thời gian có thể tăng rất nhanh. Điều này làm tăng bộ nhớ, dung lượng lưu trữ, thời gian truy vấn và chi phí của backend.

Có thể kiểm soát cardinality bằng các biện pháp sau:

1. Thiết kế danh sách giá trị hợp lệ cho từng tag ngay trong mã instrumentation.
2. Dùng route template thay cho URL chứa ID thực tế.
3. Thêm tags chung có giá trị ổn định như service và environment.
4. Dùng MeterFilter để loại bỏ meter không cần thiết hoặc giới hạn số giá trị tag.
5. Đưa dữ liệu có cardinality cao như request ID hoặc user ID sang trace hoặc log khi cần điều tra một giao dịch cụ thể.

Ví dụ dưới đây minh họa cách giới hạn số giá trị của tag uri cho nhóm HTTP request. Ngưỡng 100 chỉ là giá trị minh họa; cần chọn ngưỡng phù hợp với số route thực tế của dịch vụ.

~~~java
registry.config().meterFilter(
    MeterFilter.maximumAllowableTags(
        "http.server.requests",
        "uri",
        100,
        MeterFilter.deny()
    )
);
~~~

Nên cấu hình filter trước khi các meter liên quan được đăng ký. Filter kiểm soát quá trình đăng ký meter; nó không làm giảm số chuỗi thời gian đã được backend lưu từ trước.

## 6. Micrometer trong ứng dụng Spring Boot

Spring Boot giúp kết nối instrumentation với registry thông qua auto-configuration và dependency injection:

1. Thêm dependency của registry mà hệ thống giám sát hỗ trợ.
2. Spring Boot cấu hình MeterRegistry phù hợp khi dependency và cấu hình tương ứng có mặt.
3. Các service inject MeterRegistry để đăng ký hoặc tra cứu meter.
4. MeterRegistryCustomizer có thể thêm tags chung hoặc cấu hình registry.
5. MeterBinder có thể đăng ký metrics từ JVM, hệ điều hành và các thành phần tích hợp.
6. Với endpoint Prometheus, cần dependency Prometheus registry và cấu hình exposure cho endpoint tương ứng.

Ví dụ cấu hình exposure trong application.properties:

~~~properties
management.endpoints.web.exposure.include=health,prometheus
~~~

Thuộc tính trên cho phép endpoint prometheus được expose qua web khi registry và endpoint tương ứng đã được cấu hình. Chỉ thêm thuộc tính này mà thiếu dependency Prometheus registry thì chưa đủ để tạo luồng scrape hoàn chỉnh.

Nếu ứng dụng cần xuất metrics đến nhiều hệ thống, có thể dùng CompositeMeterRegistry để chuyển các lần ghi nhận đến nhiều registry thành phần. Cần cân nhắc chi phí và chính sách cấu hình của từng đích nhận, đồng thời tránh đăng ký trùng lặp không chủ ý.

## 7. Kiểm thử và lần theo lỗi trong pipeline

Nên xác minh từng chặng của luồng dữ liệu để biết metrics bị thiếu ở đâu:

| Chặng | Cách kiểm tra | Dấu hiệu lỗi thường gặp |
| --- | --- | --- |
| Instrumentation | Gọi thao tác nghiệp vụ và kiểm tra nhánh code ghi nhận meter | Đặt lệnh ghi nhận ở nhánh không được chạy hoặc sau một điểm return |
| Meter | Kiểm tra count, duration hoặc giá trị gauge trong môi trường test | Chọn sai loại meter, không gọi increment() hoặc record() |
| Registry | Kiểm tra meter đã được đăng ký trong registry đang dùng | Tạo registry khác với registry được exporter sử dụng |
| Export hoặc scrape | Truy cập endpoint hoặc kiểm tra cấu hình lịch push | Endpoint chưa expose, exporter thiếu cấu hình hoặc sai địa chỉ |
| Backend | Kiểm tra target, ingestion, tên metric và tags | Backend không scrape được, dữ liệu bị từ chối hoặc truy vấn sai tên/tag |

Có thể kiểm tra instrumentation đơn giản bằng SimpleMeterRegistry mà không cần kết nối backend:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

Counter counter = registry.counter(
    "orders.created",
    "result", "success"
);

counter.increment();

assertThat(counter.count()).isEqualTo(1.0);
~~~

Kiểm thử này xác nhận meter ghi nhận đúng trong registry tại chỗ. Nó chưa chứng minh endpoint export hoạt động hoặc backend đã nhận dữ liệu. Các chặng đó cần integration test hoặc kiểm tra cấu hình triển khai riêng.

Khi điều tra metric không xuất hiện, hãy lần lượt kiểm tra: mã instrumentation có chạy không; meter có được đăng ký vào đúng registry không; tags có bị filter từ chối không; registry có endpoint hoặc exporter phù hợp không; cuối cùng backend có thu thập và truy vấn đúng tên metric cùng tags không.

## 8. Nguyên tắc thiết kế

- Dùng một MeterRegistry dùng chung trong phạm vi ứng dụng và inject nó vào các thành phần cần đo lường.
- Đăng ký meter với tên, đơn vị, mô tả và tags có ý nghĩa; giữ bộ giá trị tags hữu hạn.
- Chọn meter theo semantics của dữ liệu, không dùng counter để thay thế mọi phép đo.
- Đo thời gian quanh đúng ranh giới thao tác cần quan sát; tránh vô tình bao gồm thời gian chờ ngoài phạm vi mong muốn.
- Cấu hình registry, filter và exporter ở giai đoạn khởi tạo để pipeline có hành vi nhất quán.
- Xác minh cả hai phần: số đo được ghi nhận trong ứng dụng và dữ liệu thực sự đến được backend.

Khi cần một API cấp cao hơn để liên kết metrics với tracing hoặc context của một thao tác, có thể dùng Micrometer Observation. Observation mô tả một hoạt động; các handler được cấu hình có thể chuyển hoạt động đó thành metrics hoặc trace. Dù dùng Meter API trực tiếp hay Observation, registry vẫn là thành phần kết nối dữ liệu metrics với cơ chế export hoặc scrape.

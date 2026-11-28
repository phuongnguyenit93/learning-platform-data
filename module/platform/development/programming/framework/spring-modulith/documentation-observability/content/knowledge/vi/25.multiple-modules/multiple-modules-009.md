# Đối chiếu topology runtime với cấu trúc source

## 1. Mục tiêu: kiến trúc được thiết kế có đúng với hệ thống đang chạy?

Trong ứng dụng Spring Boot gồm nhiều **application module**, sơ đồ trong mã nguồn cho biết *module nào được phép phụ thuộc module nào*. Nhưng sơ đồ đó chưa trả lời hết các câu hỏi vận hành: request thực sự đi qua những module nào, luồng sự kiện được module nào xử lý, có đường gọi vòng ngoài dự kiến hay không, và việc xử lý bất đồng bộ có giữ được thông tin truy vết hay không?

**Spring Modulith Documentation & Observability** kết hợp hai góc nhìn:

- **Cấu trúc source (static topology):** ranh giới module, quan hệ phụ thuộc Java, API được công bố, quy tắc phụ thuộc và tài liệu module graph do Spring Modulith phân tích từ mã nguồn.
- **Topology runtime (observed topology):** các tương tác *đã xảy ra và được quan sát* khi ứng dụng chạy, qua Micrometer Observation, tracing, Actuator, metrics, thông tin sự kiện và log có ngữ cảnh.

Mục đích của bài **Đối chiếu topology runtime với cấu trúc source** là lập được bản đồ đối chiếu theo *cùng một phiên bản ứng dụng và cùng một kịch bản*, giải thích các chênh lệch thay vì kết luận vội rằng hai sơ đồ phải giống hệt nhau.

Sau bài này, bạn có thể:

1. Sinh module graph từ Spring Modulith và kiểm chứng các ranh giới bằng kiểm tra kiến trúc.
2. Thu thập bằng chứng runtime cho lời gọi đồng bộ, sự kiện bất đồng bộ và các tương tác bên ngoài.
3. Quy đổi tên, hướng và loại quan hệ để so sánh hai đồ thị có ý nghĩa.
4. Phân biệt vi phạm kiến trúc với đường đi hợp lệ nhưng chưa được test hoặc chưa được ghi nhận.
5. Phát hiện các điểm mất trace context, module bị gọi ngoài dự kiến và vùng quan sát còn thiếu.

**Phạm vi:** application module là ranh giới logic trong **một ứng dụng** Spring Boot; nhiều module không mặc nhiên tương ứng với nhiều process, container hay microservice. Sơ đồ APM phân tán chỉ thấy một service Spring Boot không có nghĩa ứng dụng chỉ có một application module.

## 2. Hiểu đúng hai loại đồ thị

Một **đồ thị source** có đỉnh là các application module, cạnh có hướng **A → B** nghĩa là mã thuộc A tham chiếu thành phần thuộc B (chẳng hạn import kiểu dữ liệu hoặc inject bean). Một **đồ thị runtime** có đỉnh là các module được gắn danh tính ở thời điểm chạy; cạnh **A → B** nghĩa là bằng chứng quan sát được ghi nhận một tương tác từ A sang B trong khoảng thời gian khảo sát.

Hai loại cạnh có thể biểu đạt những ý nghĩa khác nhau:

| Loại quan hệ | Trong source | Trong runtime | Cách hiểu khi đối chiếu |
| --- | --- | --- | --- |
| Gọi Java đồng bộ | Module A tham chiếu API của B | Một thao tác của A gọi vào B trong một trace | Có thể đối chiếu theo cùng chiều A → B. |
| Phát và tiêu thụ sự kiện | Handler ở B **tham chiếu kiểu sự kiện** do A công bố: thường là B → A ở đồ thị phụ thuộc kiểu | Publisher ở A phát sự kiện để handler ở B xử lý: luồng A → B | Phải phân biệt **phụ thuộc kiểu** với **luồng phát sự kiện**; không so trực tiếp hai mũi tên. |
| Gọi ra database, HTTP, broker | Có thể chỉ thấy dependency tới thư viện hoặc adapter | Thấy span/truy cập tài nguyên ngoài | Phân loại thành *module → external resource*, không tự nhận là module nội bộ mới. |
| Tạo object, reflection, callback | Có thể không hiện thành cạnh theo quy tắc phân tích module | Có thể phát sinh tương tác lúc chạy | Cần kiểm tra vị trí instrumentation và nguồn dữ liệu trước khi kết luận. |

Đồ thị runtime luôn là **một tập con của những gì hệ thống đã chạy và được đo**. Không có cạnh trong trace *không chứng minh* lời gọi đó không tồn tại: nhánh nghiệp vụ có thể chưa chạy, sampling có thể bỏ qua trace, hoặc công cụ chưa instrument đường đi đó.

Ngược lại, một cạnh trong module graph biểu thị *dependency có trong mã*, chưa chứng minh dependency đó được thực thi trong request đang xét.

### Ba tầng topology cần đặt đúng chỗ

~~~mermaid
flowchart TD
    A["Cấu trúc source<br/>ApplicationModules + Documenter"] --> C["Bảng đối chiếu<br/>ranh giới + hướng + loại cạnh"]
    B["Tương tác runtime<br/>Observations + spans + events"] --> C
    D["Hạ tầng<br/>process, HTTP, DB, broker"] --> B
    C --> E["Giải thích chênh lệch<br/>và kiểm chứng lại"]
~~~

**Actuator công bố thông tin module** thường phản ánh cấu trúc ứng dụng đã nạp; riêng việc đọc một endpoint cấu trúc trên Actuator **không tạo ra** đồ thị các lời gọi thực tế. Muốn đối chiếu runtime, vẫn phải có thông tin từ metrics, tracing, event publication hoặc instrumentation cụ thể.

## 3. Ví dụ xuyên suốt: ứng dụng bán hàng bốn module

Giả sử package gốc của ứng dụng là **com.example.store** với các module con trực tiếp:

~~~text
com.example.store
├── StoreApplication.java
├── catalog/
│   ├── CatalogApi.java
│   └── internal/
├── orders/
│   ├── OrderService.java
│   ├── events/
│   │   └── OrderPlaced.java
│   └── internal/
├── billing/
│   └── BillingEventListener.java
└── notifications/
    └── NotificationEventListener.java
~~~

Các module theo quy ước package của Spring Modulith:

- **orders** tiếp nhận lệnh đặt hàng và gọi **catalog** để kiểm tra mặt hàng.
- Sau khi lưu đơn, **orders** phát **OrderPlaced**.
- **billing** và **notifications** đăng ký xử lý **OrderPlaced**. Kiểu sự kiện nằm trong giao diện công khai của module orders hoặc trong **named interface** được khai báo rõ; handler không import trực tiếp class dưới **orders.internal**.
- Mỗi module giữ phần triển khai nội bộ bên trong ranh giới package của mình.

Ví dụ mã minh họa:

~~~java
// Trong module orders
@Service
class OrderService {
    private final CatalogApi catalog;
    private final ApplicationEventPublisher events;

    OrderService(CatalogApi catalog, ApplicationEventPublisher events) {
        this.catalog = catalog;
        this.events = events;
    }

    void placeOrder(String sku, int quantity) {
        catalog.assertAvailable(sku, quantity);
        // Lưu đơn hàng và xác định ID thực tế tại đây.
        events.publishEvent(new OrderPlaced("ORD-1001"));
    }
}
~~~

~~~java
// Trong module billing; OrderPlaced là kiểu sự kiện đã được orders công bố.
@Component
class BillingEventListener {
    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Tạo bản ghi thanh toán cho event.orderId().
    }
}
~~~

Các đoạn trên chỉ minh họa đường tương tác; để xây dựng dự án chạy được cần khai báo/import các class theo cấu trúc thực tế, lớp **CatalogApi**, record **OrderPlaced**, repository và cấu hình giao dịch. **@ApplicationModuleListener** là cơ chế listener hỗ trợ tích hợp sự kiện giữa các module trong Spring Modulith; kiểm tra ngữ nghĩa transaction, async và retry theo phiên bản/configuration của dự án.

Trong mã nguồn, cạnh phụ thuộc kiểu có thể là:

~~~text
orders        ──API──> catalog
billing       ──type──> orders::events
notifications ──type──> orders::events
~~~

Với kịch bản **POST /orders**, luồng nghiệp vụ runtime dự kiến:

~~~mermaid
sequenceDiagram
    actor U as HTTP caller
    participant O as orders
    participant C as catalog
    participant E as Event publisher
    participant B as billing
    participant N as notifications
    U->>O: placeOrder()
    O->>C: assertAvailable()
    C-->>O: OK
    O->>E: publish OrderPlaced
    E-->>B: deliver OrderPlaced
    E-->>N: deliver OrderPlaced
    Note over B,N: Có thể được xử lý bất đồng bộ
~~~

**Điểm dễ nhầm:** trên đồ thị source, **billing → orders::events** do tham chiếu kiểu; trên đồ thị luồng sự kiện, **orders → billing** do publisher gửi tới consumer. Đây là hai cách mô tả khác nhau của cùng một thiết kế hợp lệ, không mặc nhiên là *architecture drift*.

## 4. Chụp topology của source bằng Spring Modulith

Spring Modulith xác định application module theo cấu trúc package và quy tắc công bố API; phần **ApplicationModules** cho phép kiểm tra các module mà framework nhận diện. Trước tiên, bảo đảm các dependency Spring Modulith phù hợp với **Spring Boot BOM** và phiên bản Spring Modulith được quản lý tập trung. Những artifact thường liên quan:

| Thành phần | Mục đích |
| --- | --- |
| **spring-modulith-starter-core** | Thành phần cốt lõi cho thiết kế và nhận diện module. |
| **spring-modulith-starter-test** | Hỗ trợ các phép kiểm thử theo module. |
| **spring-modulith-docs** | Sinh tài liệu/diagram ở thời gian kiểm thử hoặc build. |
| **spring-modulith-actuator** | Công bố metadata module trong môi trường runtime qua Actuator, tùy cấu hình. |
| **spring-modulith-starter-observability** | Bổ sung tích hợp quan sát tương tác module, kết hợp hạ tầng quan sát của ứng dụng. |
| **spring-boot-starter-actuator** | Hệ endpoint quản trị, health và metrics của Spring Boot. |

Tên artifact, BOM và cấu hình tích hợp có thể thay đổi theo phiên bản Spring Modulith. Sử dụng một nhánh phiên bản tương thích với Spring Boot của dự án và khóa phiên bản khi thu thập bằng chứng.

### 4.1. Kiểm tra ranh giới module từ source

Trong **src/test/java**, tạo kiểm thử:

~~~java
package com.example.store;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifyModuleBoundaries() {
        ApplicationModules.of(StoreApplication.class).verify();
    }
}
~~~

**verify()** giúp phát hiện các vấn đề kiến trúc mà Spring Modulith hỗ trợ kiểm tra, như vòng phụ thuộc giữa các module và truy cập tới phần triển khai nội bộ trái ranh giới. Quy tắc **allowedDependencies**, **@NamedInterface** và cách khai báo module cần được dùng khi cần hợp đồng phụ thuộc chặt hơn. Việc kiểm tra này **không** phải test hiệu năng, test tải, cũng không xác nhận một đường gọi thực sự được thực thi.

### 4.2. Sinh sơ đồ để reviewer đọc được

Nếu dự án đã thêm **spring-modulith-docs** vào test classpath, có thể sinh PlantUML từ model source:

~~~java
package com.example.store;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentationTests {

    @Test
    void writeModuleDiagrams() {
        ApplicationModules modules =
                ApplicationModules.of(StoreApplication.class);

        new Documenter(modules)
                .writeModulesAsPlantUml()
                .writeIndividualModulesAsPlantUml();
    }
}
~~~

Các artifact diagram do **Documenter** sinh ra dùng làm **baseline source**. Tùy bản Spring Modulith, có thể dùng thêm khả năng xuất tài liệu/Canvas và cấu hình thư mục output theo API tương ứng. Nên lưu lại trong báo cáo tên ứng dụng, **Git commit**, phiên bản Spring Modulith, quy tắc package/module và thời điểm sinh graph; nếu không biết snapshot này thuộc bản deploy nào thì không thể so sánh đáng tin.

Khi đồ thị bất ngờ thiếu module hoặc hiện quá nhiều module, kiểm tra đầu tiên là package gốc đặt class **@SpringBootApplication**, cách tổ chức các package con và rule xác định module. Đừng vội chỉnh observability để giải quyết lỗi nhận diện ở source.

### 4.3. Định nghĩa ranh giới làm chuẩn

Một quy ước rõ ràng cho ví dụ:

| Module | API/kiểu được phép dùng từ bên ngoài | Nội bộ không nên bị gọi trực tiếp |
| --- | --- | --- |
| catalog | **CatalogApi** | Repository và tính toán tồn kho nội bộ |
| orders | API nhận lệnh, **orders::events** chứa OrderPlaced | OrderRepository, internal services |
| billing | API/consumer thanh toán theo hợp đồng | Triển khai bút toán và adapter |
| notifications | API/consumer thông báo theo hợp đồng | Template renderer và adapter gửi |

Nếu **billing** import **orders.internal.OrderRepository**, cần sửa thiết kế hoặc định nghĩa API được phép gọi. Nếu **billing** chỉ tham chiếu **OrderPlaced** thuộc named interface đã công bố thì đó là dependency có chủ đích.

## 5. Quan sát runtime: Actuator, module observations và tracing

Để nhìn được đường đi ở thời gian chạy, kết hợp nhiều nguồn dữ liệu thay vì trông chờ một endpoint duy nhất.

### 5.1. Actuator cho trạng thái và metadata

Bật Spring Boot Actuator, sau đó chỉ công bố các endpoint cần cho môi trường đang test. Ví dụ trong **application.yml** dành cho môi trường phát triển:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  tracing:
    sampling:
      probability: 1.0
~~~

**sampling.probability: 1.0** chỉ phù hợp cho thực hành hoặc một lần chạy kiểm thử có kiểm soát để không bỏ sót trace do sampling; môi trường production phải cân nhắc lưu lượng, chi phí và quyền riêng tư. Có thể cần thêm bridge/exporter Micrometer Tracing và cấu hình đích OTLP/Zipkin theo hệ quan sát thực tế; bật property sampling thôi **chưa tự tạo** hệ thống xuất trace.

Khi dùng **spring-modulith-actuator**, hãy kiểm tra endpoint module thực tế được bản library cung cấp và cấu hình exposure tương ứng. **/actuator** cho biết các endpoint đã công bố với cấu hình hiện tại; endpoint metadata module giúp xem ứng dụng *nhận diện cấu trúc nào khi khởi động*, không chứng minh đã có lời gọi A → B.

Không mở công khai endpoint quản trị, trace UI hoặc metric nội bộ ra Internet. Ở môi trường production, dùng network restriction và security của Spring Boot Actuator.

### 5.2. Quan sát tương tác nội bộ

**spring-modulith-starter-observability** tích hợp Spring Modulith với cơ chế quan sát của Spring Boot/Micrometer. Với những module và component được instrument, các span/observation có thể thể hiện điểm đi vào module và lời gọi giữa các module. Số lượng, tên và tag của span phụ thuộc phiên bản, kiểu component, cấu hình và đường chạy thực tế.

Cần kiểm tra *thực tế* trace chứa trường nào:

- Module nguồn/đích có thể suy ra đáng tin từ span hoặc từ mapping chính thức giữa package/bean và module hay không?
- Có **parent span** hoặc causal link nối request gốc với nghiệp vụ ở module khác hay không?
- Thời điểm thực thi, instance, build version, transaction và loại gọi (sync/async/event) có ghi nhận không?
- Sampling hoặc batching có tạo vùng trống trong dữ liệu hay không?

Hãy dùng **trace/span thực**, không suy luận topology runtime chỉ từ sơ đồ Actuator. Nếu một loại lời gọi không được starter instrument, bổ sung **Micrometer Observation** tại API module hoặc interceptor phù hợp; đặt tag module ở mức cardinality thấp và luôn giữ tên module nhất quán.

Ví dụ observation nghiệp vụ minh họa cho chỗ có thể instrument thủ công:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

class CheckoutUseCase {
    private final ObservationRegistry registry;
    private final OrderWorkflow workflow;

    CheckoutUseCase(ObservationRegistry registry, OrderWorkflow workflow) {
        this.registry = registry;
        this.workflow = workflow;
    }

    void submit(CheckoutCommand command) {
        Observation.createNotStarted("orders.submit", registry)
                .lowCardinalityKeyValue("application.module", "orders")
                .observe(() -> workflow.submit(command));
    }
}
~~~

Đây là **điểm đo thao tác ở orders**, chưa phải một cạnh sang module khác. Muốn suy ra A → B, cần quan sát ở ranh giới vào B và ngữ cảnh gọi của A, hoặc ghi nhận cặp nguồn/đích bằng một thành phần đo đáng tin. Không tự biến mọi observation thành một cạnh dựa vào tên span.

### 5.3. Metrics và traces bổ sung cho nhau

| Dữ liệu | Trả lời tốt | Không đủ để kết luận |
| --- | --- | --- |
| Health/Actuator | Ứng dụng còn chạy? Cấu trúc module được nạp như thế nào? | Từng request gọi module nào. |
| Module/operation metrics | Số lần chạy, lỗi, độ trễ theo nhãn có kiểm soát | Chuỗi nhân quả đầy đủ nếu chỉ có số tổng hợp. |
| Distributed tracing | Các span liên quan trong một request, độ trễ và parent/child | Những request bị sampling bỏ qua hoặc phần chạy không được instrument. |
| Event publication status | Sự kiện nào phát đi, xử lý thành công/thất bại/chưa hoàn thành nếu có cơ chế lưu publication | Mọi handler đều đã nhận/trả ACK nếu hệ thống không instrument tương ứng. |
| Structured logs | Thông tin chi tiết có trace ID, module, event ID, version | Một đồ thị đầy đủ nếu thiếu correlation hoặc log bị lọc. |

## 6. Sự kiện bất đồng bộ và context propagation

Một đường đi qua module có thể chia làm hai giai đoạn:

1. **orders** nhận request HTTP, xác thực đơn hàng và phát **OrderPlaced**.
2. **billing** xử lý một event ở luồng hoặc transaction riêng; **notifications** có thể xử lý muộn hơn.

Trường hợp này dễ bị APM hiển thị thành những trace rời rạc. Không nên kết luận **billing** là module độc lập với luồng đặt hàng chỉ vì thiếu quan hệ parent/child.

Spring Modulith hỗ trợ publication và listener tích hợp với Spring Application Events. Cấu hình persistence cho event publication giúp theo dõi các publication chưa được hoàn tất và hỗ trợ xử lý lại theo khả năng của từng phiên bản; điều đó **không tự đảm bảo** toàn bộ chuỗi trace sẽ giữ được context qua các boundary thread/process.

### 6.1. Dữ liệu nên mang theo qua event

Trong ứng dụng nhiều module, event cần một định danh ổn định cho nghiệp vụ; correlation metadata phải tách với dữ liệu nhạy cảm.

~~~java
public record OrderPlaced(
        String eventId,
        String orderId,
        java.time.Instant occurredAt
) {}
~~~

Trong trường hợp cần liên kết trace, bên phát có thể ghi **eventId** cùng **traceId** vào log có cấu trúc; bên nhận ghi **eventId** và **traceId hiện tại**. Nếu event được đưa qua broker hoặc lưu bền, cần thiết kế truyền context trong metadata/header theo chuẩn của hạ tầng đó, đồng thời không trộn thông tin trace tạm thời với hợp đồng nghiệp vụ ổn định.

Mỗi consumer nên có **idempotency** cho eventId để một sự kiện xử lý lại không tạo thanh toán hoặc gửi thông báo lặp không chủ đích.

### 6.2. Khi đổi thread phải kiểm tra ngữ cảnh

Trace/MDC thường gắn với context của thread. Với **@Async**, scheduler, executor riêng, callback hoặc message broker, cần xác nhận framework và ứng dụng có cơ chế **context propagation** phù hợp. Spring Framework/Micrometer có các thành phần phục vụ việc này, nhưng không phải executor nào cũng tự động áp dụng chúng.

Ví dụ gắn **ContextPropagatingTaskDecorator** vào một executor tự quản lý trong môi trường có Spring Framework hỗ trợ API này:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class AsyncExecutionConfiguration {

    @Bean(name = "orderEventExecutor")
    ThreadPoolTaskExecutor orderEventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setThreadNamePrefix("order-event-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

**Quan trọng:** chỉ những tác vụ **thực sự chạy trên executor này** mới nhận tác dụng của decorator. Đăng ký một bean mới không tự làm cho mọi **@ApplicationModuleListener** dùng nó. Phải xác định executor nào được Spring async/event multicaster sử dụng và cấu hình theo đúng đường dispatch. Khi event chuyển qua broker hoặc được phát lại sau khởi động, cần propagation theo message headers và liên kết nhân quả thích hợp, thay vì giả định còn sống nguyên thread context ban đầu.

Phép thử hữu ích là chạy cùng một kịch bản đặt hàng và kiểm tra cả hai nhánh listener: **trace liên kết được hoặc có correlation/event ID rõ ràng**, log giữ đúng ngữ cảnh, và kết quả business không phụ thuộc việc có trace.

## 7. Thu thập hai snapshot có thể đối chiếu

Kết quả đối chiếu chỉ có giá trị khi **source snapshot** và **runtime snapshot** thuộc cùng một bản build. Một bảng chứng cứ tối thiểu:

| Trường | Ví dụ | Vì sao cần |
| --- | --- | --- |
| Source revision | Git commit **a1b2c3d** | Biết module graph được tạo từ mã nào. |
| Runtime revision | Cùng commit **a1b2c3d** | Tránh so bản chạy cũ với nhánh source mới. |
| Application | **store-api** | Xác định boundary của một application. |
| Environment | **staging** | Kỳ vọng topology có thể khác production vì cấu hình/feature flag. |
| Thời gian | Cửa sổ 10 phút đã ghi rõ timezone | Bao phủ các trace và event được so sánh. |
| Scenario | **placeOrder / ORD-1001** | Biết nhánh nghiệp vụ nào đã chạy. |
| Sampling | **100% cho kịch bản test** | Đánh giá khả năng thiếu trace. |
| Evidence | Span ID, trace ID, event ID, endpoint/metric/log | Có thể truy nguyên từng nhận định. |

**Lưu ý:** commit trong bảng chỉ là ví dụ định dạng. Khi thực hành, ghi chính xác revision của artifact đang chạy, không sao chép giá trị minh họa.

### Quy trình thu thập đề xuất

1. Build ứng dụng ở revision xác định. Chạy phép kiểm tra **ApplicationModules.verify()** và sinh module graph của đúng revision.
2. Khởi động cùng artifact trong môi trường test có module observability và exporter hoạt động; xác minh nguồn Actuator/trace thực sự cung cấp dữ liệu.
3. Chạy kịch bản **placeOrder** và ít nhất một nhánh lỗi (chẳng hạn mặt hàng không tồn tại) với trace sampling đủ cao.
4. Đợi các handler bất đồng bộ hoàn thành, hoặc ghi rõ khoảng chờ/kết quả publication còn pending. Đừng lấy snapshot khi các event vẫn đang xử lý rồi gọi đó là topology cuối cùng.
5. Lấy span/observation và publication metrics/log từ đúng cửa sổ. Định danh module bằng mapping package/bean → module đã sinh ở bước 1.
6. Tổng hợp thành các cạnh **SYNC_CALL**, **EVENT_PUBLISH/CONSUME** và **EXTERNAL_CALL**, mỗi cạnh có ít nhất một evidence reference.

Không cần ép dữ liệu runtime thành PlantUML ngay lập tức. Một **bảng cạnh có chứng cứ** thường dễ kiểm toán hơn ảnh chụp dashboard.

## 8. Chuẩn hóa cạnh trước khi so sánh

Đặt mỗi cạnh vào cùng mô hình dữ liệu:

~~~text
Edge = {
  sourceModule, targetModule,
  relationType, operationOrEvent,
  sourceRevision, runtimeRevision,
  scenario, timeWindow,
  evidenceIds, observationCoverage
}
~~~

Quy tắc chuẩn hóa:

- Dùng **tên application module** từ Spring Modulith làm khóa, không dùng tên bean dễ trùng hoặc tên service APM vốn chỉ đại diện cả process.
- Xác định **hướng của lời gọi**: caller → callee cho sync; publisher → consumer cho luồng event; consumer → module công bố event cho dependency kiểu trong Java.
- Với một event, lưu cả quan hệ dependency kiểu và quan hệ publisher/consumer; **không đổi ngược mũi tên một cách ngầm định**.
- Bỏ khỏi đồ thị *liên module* các bước chỉ đi bên trong cùng module; nếu cần, giữ chúng trong trace chi tiết để giải thích latency.
- Gắn nhãn **external** cho database, HTTP downstream và broker.
- Không suy ra edge nếu chỉ có sự hiện diện của hai span không có parent/link, event ID hoặc bằng chứng về kết nối nhân quả đáng tin.
- Ghi **observationCoverage** là đủ/chưa đủ/chưa biết; nếu sampling thấp hoặc thiếu instrumentation, không dùng phép trừ tập hợp để kết luận đường đi không tồn tại.

### Bảng so sánh cho ví dụ

| Quan hệ mong đợi | Bằng chứng source | Bằng chứng runtime cần tìm | Kết luận khi quan sát đủ |
| --- | --- | --- | --- |
| **orders → catalog** (sync) | OrderService phụ thuộc CatalogApi | Span vào catalog xảy ra từ luồng orders | Hợp lệ nếu đúng API đã công bố. |
| **orders → billing** (event flow) | billing phụ thuộc API **orders::events** | EventId của OrderPlaced gắn với handler billing | Hợp lệ; chiều source dependency kiểu ngược chiều event flow. |
| **orders → notifications** (event flow) | notifications phụ thuộc API **orders::events** | EventId tương ứng được handler notifications xử lý | Hợp lệ nếu handler hoàn thành, hoặc ghi rõ pending. |
| **billing → catalog.internal** (sync) | Không được thiết kế; nếu có tham chiếu, verify có thể báo | Có dấu vết gọi trực tiếp implementation nội bộ | Cần điều tra vi phạm boundary. |
| **orders → external payment API** | Không có trong luồng đặt hàng giả định | Trace HTTP client đi ra payment provider | Kiểm tra đây là thay đổi thiết kế hay instrumentation gán nhầm module. |

Khi muốn tự động hóa, chỉ trừ các tập cạnh **cùng loại và cùng quy ước hướng**:

~~~text
observedSyncUnexpected = observedSyncEdges - approvedSyncBoundaries
sourceSyncNotObserved  = sourceSyncEdges - observedSyncEdges

eventFlowUnexpected   = observedEventFlows - expectedEventFlows
eventFlowNotObserved  = expectedEventFlows - observedEventFlows
~~~

Hai tập **NotObserved** chỉ có nghĩa là *chưa có bằng chứng trong phạm vi đo*; đó không mặc nhiên là lỗi. Tập **Unexpected** cũng cần xác minh mapping, sampling, proxy/reflection, feature flag và thay đổi hợp đồng trước khi đánh dấu vi phạm.

## 9. Nhận diện architecture drift và điểm mù quan sát

Hãy phân loại chênh lệch theo nguyên nhân; cùng một hình ảnh trên dashboard có thể có nhiều cách giải thích.

### Trường hợp A: runtime xuất hiện đường gọi không được phép

Ví dụ trace cho thấy **billing → catalog.internal.StockRepository**. Nếu lookup đúng với runtime revision và module mapping, đây là dấu hiệu xuyên ranh giới. Cách xử lý: xác định call site, kiểm tra **ApplicationModules.verify()**, định nghĩa lại interface hợp lệ ở catalog hoặc chuyển logic tới đúng module. Không khắc phục bằng cách tắt span đang cho thấy lỗi.

### Trường hợp B: source có dependency nhưng runtime chưa thấy

Ví dụ **notifications → orders::events** hiện trong source, nhưng chưa có event nào tới notifications. Kiểm tra các khả năng: kịch bản chưa phát OrderPlaced, feature flag tắt, listener chưa đăng ký, event đang pending, giao dịch rollback, trace không nối được khi đổi thread, hoặc sampling bỏ qua. Nếu mọi điều kiện quan sát đầy đủ và đường đi phải xảy ra thì mới xem đây là lỗi nghiệp vụ/cấu hình.

### Trường hợp C: event flow bị hiểu nhầm thành dependency ngược

Runtime ghi **orders → billing** qua event, nhưng module graph có **billing → orders::events**. Không sửa code để buộc hai mũi tên giống nhau. Đánh dấu **type dependency** và **event delivery** là hai loại quan hệ, đồng thời kiểm tra event contract và sự tách biệt giữa publisher/consumer.

### Trường hợp D: mất trace context

Request root ở **orders** và một trace khác bắt đầu ở **billing**, nhưng cả hai ghi cùng **eventId**. Đây có thể là mất context qua async/broker hoặc cách mô hình trace không biểu diễn liên kết bất đồng bộ bằng parent-child. Cần kiểm tra executor và propagation, liên kết event ID, timestamp, span links/headers và độ trễ xử lý. Chỉ kết luận lỗi nghiệp vụ nếu có bằng chứng xử lý sai, không phải vì graph APM vẽ thành hai cây.

### Trường hợp E: module graph đổi mà trace chưa đổi

Một API mới được import nhưng chưa được gọi, hoặc đường gọi cũ đã bị refactor nhưng dashboard vẫn đang lưu trace của bản deploy trước. Kiểm tra revision, thời gian, cache tài liệu và khoảng lưu dữ liệu trước khi sửa code.

### Trường hợp F: số liệu tổng hợp khác số event

Một event có thể có nhiều consumer; retries hoặc replay có thể khiến số lần xử lý lớn hơn số event đã phát. So theo **eventId + consumer + attempt/status** thay vì kết luận lỗi từ một phép so tổng số counters. Cần quy ước riêng về at-least-once delivery và idempotency.

## 10. Kiểm chứng bằng test và quan sát lặp lại

Một chiến lược hiệu quả gồm ba lớp, mỗi lớp giải quyết một loại rủi ro:

| Lớp | Công cụ | Bảo đảm chính |
| --- | --- | --- |
| **Source architecture** | ApplicationModules.verify(), Documenter và các quy tắc allowedDependencies | Ranh giới được phát hiện, dependency trực tiếp tuân thủ thiết kế. |
| **Application/module integration** | **@ApplicationModuleTest**, test listener, test nghiệp vụ | Đường đi trong một hoặc nhiều module thực hiện đúng chức năng. |
| **Runtime evidence** | Actuator, Micrometer/trace export, event publication/log, kịch bản HTTP thật | Đường gọi đã xảy ra và có dữ liệu thời gian chạy để đối chiếu. |

Ví dụ kiểm tra đường đi có thể thiết kế theo bảng:

| Kịch bản | Mong đợi | Bằng chứng cần lưu |
| --- | --- | --- |
| Đặt hàng hợp lệ | orders gọi catalog, phát OrderPlaced, billing và notifications xử lý | Một trace hoặc các trace liên kết với eventId; trạng thái publication; kết quả nghiệp vụ. |
| SKU không tồn tại | orders gọi catalog, từ chối đặt hàng; không tạo sự kiện OrderPlaced | Kết quả HTTP/domain error; không có publication mới theo orderId của lần chạy. |
| Billing thất bại một lần | Publication/handler báo trạng thái lỗi hoặc pending, thử lại theo cấu hình | Event ID, attempt, exception đã được xử lý, kết quả cuối và idempotency. |
| Listener bất đồng bộ | Ngữ cảnh được nối qua thread boundary hoặc liên kết bằng correlation ID | Span/link, log, executor, eventId và thời gian hoàn thành. |
| Gọi xuyên API nội bộ | Architecture test phải phát hiện khi dependency thuộc phạm vi kiểm tra | Report test thất bại với module nguồn/đích, call site. |

Trong CI có thể kiểm tra **.verify()** và sinh tài liệu đồ thị mỗi lần thay đổi mã. Với bài test observability, hãy đặt điều kiện và kịch bản lặp lại được, chạy trên môi trường tích hợp; không cần mỗi commit dựng toàn bộ APM sản xuất. Tách **fail về quy tắc source** khỏi **cảnh báo thiếu dữ liệu quan sát**, để tránh làm pipeline thất bại bởi sampling hoặc exporter tạm lỗi.

## 11. Đọc số liệu vận hành cho đúng bối cảnh

Topology cho biết *đường đi*. Metrics/tracing còn giúp trả lời *đường đi có khỏe không*. Với mỗi cạnh quan trọng, có thể theo dõi:

- **Throughput:** số lần gọi hoặc số publication/handler invocation theo đơn vị thời gian.
- **Latency:** độ trễ module hoặc handler; với async phải tách thời gian nằm chờ và thời gian xử lý.
- **Error rate:** exception/Fault, số publication chưa hoàn thành, timeout và retry.
- **Fan-out:** một sự kiện đến bao nhiêu consumer, và consumer nào chậm.
- **Context completeness:** tỷ lệ đường tương tác có thể liên kết tới request/event gốc trong lần kiểm thử có kiểm soát.

Không đưa **orderId**, email, số điện thoại, eventId ngẫu nhiên hoặc traceId vào metric label cardinality thấp: số lượng chuỗi khác nhau sẽ làm nổ series trong hệ metrics. Thông tin định danh dùng trong **trace/log với retention, masking và quyền truy cập thích hợp**; metric chỉ nên gắn nhãn hữu hạn như **module**, **operation**, **result** và **environment**.

Quy tắc vận hành cần giữ: trace có thể chứa tên method, request attributes và dữ liệu tích hợp nhạy cảm. Hạn chế tag đầu vào, che thông tin riêng tư, cấu hình sampling/retention và bảo vệ Actuator/collector. Đồ thị chi tiết có giá trị trong điều tra nhưng cần tránh lộ cấu trúc nội bộ cho người không có quyền.

## 12. Quy trình thực hành từng bước

Thực hiện một lần đối chiếu có thể review độc lập:

1. **Chuẩn bị baseline:** vẽ bốn module **catalog**, **orders**, **billing**, **notifications**; định nghĩa API công khai, event contract và các quan hệ sync/event kỳ vọng.
2. **Xác nhận source:** chạy **ApplicationModules.of(StoreApplication.class).verify()**; xuất module graph bằng **Documenter** và ghi lại build revision.
3. **Bật quan sát:** cấu hình Actuator và Spring Modulith observability; xác minh backend nhận trace/metric từ ứng dụng. Chọn cửa sổ test ngắn có sampling phù hợp.
4. **Chạy kịch bản:** đặt hàng hợp lệ, đặt hàng lỗi và một trường hợp handler retry. Theo dõi publication cho tới khi hoàn thành hoặc ghi rõ trạng thái còn chờ.
5. **Trích bằng chứng:** xuất bảng các tương tác đã quan sát, gắn **trace/span ID**, **eventId**, revision, scenario, thời điểm và mức độ phủ quan sát.
6. **Chuẩn hóa:** nối span và module bằng quy tắc package/bean → module; phân biệt **SYNC_CALL**, **EVENT_FLOW**, **EXTERNAL_CALL**, và dependency kiểu của source.
7. **Đối chiếu:** phân loại cạnh được thiết kế và quan sát, cạnh chưa quan sát, cạnh ngoài dự kiến và cạnh chưa đủ bằng chứng; lưu lý do cho mỗi chênh lệch.
8. **Điều chỉnh và thử lại:** sửa call site vượt boundary hoặc cấu hình instrumentation/context propagation nếu cần. Chạy lại cùng kịch bản, xác nhận bản source/runtime cùng revision.

### Mẫu báo cáo đối chiếu

| Source → Target | Loại cạnh | Mong đợi | Quan sát | Evidence | Kết luận |
| --- | --- | --- | --- | --- | --- |
| orders → catalog | Sync | Có | Có | Trace T1 / span S2 | Đúng thiết kế |
| orders → billing | Event flow | Có | Có | Event E1 / handler B1 | Đúng thiết kế |
| orders → notifications | Event flow | Có | Chưa xác nhận | Event E1 / pending | Cần chờ hoặc kiểm tra listener |
| billing → catalog.internal | Sync | Không | Không | Architecture test / trace window | Chưa thấy vi phạm trong phạm vi đo |

**Các ID T1/S2/E1/B1 là ký hiệu minh họa**, không phải bằng chứng thu được từ một hệ thống đã chạy. Báo cáo thực cần đường dẫn hoặc định danh trỏ tới dữ liệu có thể kiểm chứng. Nếu không đủ dữ liệu thì ghi **chưa xác nhận**, tránh tô trạng thái thành công.

### Câu hỏi tự kiểm tra

1. Vì sao quan hệ **billing → orders::events** ở source vẫn tương thích với luồng **orders → billing** khi event được phát?
2. Vì sao đồ thị module đọc từ Actuator chưa đủ để khẳng định runtime có lời gọi A → B?
3. Khi trace không chứa notifications, những khả năng nào cần kiểm tra trước khi kết luận module này không được gọi?
4. Context propagation qua executor khác gì propagation qua broker có lưu trữ sự kiện?
5. Vì sao nên so sánh snapshot cùng revision, cùng kịch bản và cùng thời gian quan sát?
6. Một edge chỉ có dấu vết ở runtime nhưng không có dependency Java trực tiếp có thể đến từ những cơ chế nào?

**Đầu ra cần nộp:** (1) module graph từ source, (2) bảng edge runtime có chứng cứ, (3) bảng đối chiếu phân biệt sync, event flow và external, (4) danh sách chênh lệch kèm giả thuyết/kiểm chứng, và (5) kết quả architecture test. Đây là cách dùng Spring Modulith, Actuator, event metrics, tracing và context propagation để kiểm chứng kiến trúc mô-đun khi ứng dụng Spring Boot đang vận hành.

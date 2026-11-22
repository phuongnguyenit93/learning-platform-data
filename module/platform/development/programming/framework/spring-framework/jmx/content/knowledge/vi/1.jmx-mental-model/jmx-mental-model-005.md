# Phân biệt MBean, bean Spring, endpoint và chỉ số ứng dụng

## 1. Mục tiêu và bức tranh tổng thể

Khi xây dựng ứng dụng Spring Framework, bốn khái niệm **MBean**, **Spring bean**, **endpoint** và **chỉ số ứng dụng (metric)** thường xuất hiện cùng nhau trong tài liệu vận hành. Chúng có thể biểu diễn thông tin về cùng một thành phần, nhưng không nằm cùng một tầng khái niệm.

Sau bài này, bạn có thể:
- Xác định đúng đối tượng đang nói đến là thành phần nội bộ, giao diện quản trị, điểm truy cập mạng hay phép đo.
- Giải thích quan hệ giữa Spring IoC container, JMX MBeanServer, HTTP endpoint và hệ thống metrics.
- Nhận diện các trường hợp một Spring bean được xuất bản thành MBean hoặc cung cấp dữ liệu cho endpoint/metric.
- Chọn cơ chế thích hợp khi cần cấu hình, chẩn đoán, theo dõi hoặc tự động hóa vận hành.

**Mô hình tư duy:** Spring bean trả lời *“đối tượng nào được ứng dụng quản lý?”*; MBean trả lời *“đối tượng quản trị nào JMX cho phép quan sát hoặc thao tác?”*; endpoint trả lời *“người gọi truy cập chức năng/thông tin bằng địa chỉ và giao thức nào?”*; metric trả lời *“đại lượng nào được đo, với tên, giá trị và nhãn gì?”*

Một thành phần có thể đồng thời tham gia cả bốn vai trò mà không khiến bốn khái niệm trở thành đồng nghĩa.

## 2. Bốn khái niệm và ranh giới

| Khái niệm | Bản chất | Ai quản lý hoặc cung cấp? | Cách truy cập thường gặp | Ví dụ |
|---|---|---|---|---|
| **Spring bean** | Instance của một đối tượng được đăng ký trong Spring IoC container | \`ApplicationContext\`/\`BeanFactory\` | Dependency injection, lấy bean từ context | \`OrderService\`, \`DataSource\` |
| **JMX MBean** | Đối tượng quản trị có thuộc tính, thao tác và có thể có thông báo, được đăng ký bằng \`ObjectName\` | \`MBeanServer\` của nền tảng/JMX | JMX client như JConsole, VisualVM, Java Management API | \`com.example:type=Queue,name=Orders\` |
| **Endpoint** | Điểm truy cập một chức năng hoặc tài nguyên qua giao thức/đường dẫn đã công bố | Web framework, management framework hoặc adapter tương ứng | HTTP \`GET /actuator/health\`, \`GET /orders\`; cũng có endpoint quản trị qua JMX | Health endpoint, REST endpoint |
| **Metric** | Phép đo có tên, loại, giá trị và có thể có tags/labels | Meter registry, instrumentation, monitoring backend | Prometheus scrape, Micrometer API, metrics endpoint, dashboard | \`http.server.requests\`, số tác vụ đang chờ |

**Chú ý về từ “endpoint”:** Trong ngữ cảnh Spring Boot Actuator, một *actuator endpoint* là một chức năng quản trị trừu tượng có thể được phơi bày qua **HTTP hoặc JMX**. Còn trong web API thông thường, endpoint thường nói đến URL/route. Vì vậy, “endpoint” không mặc nhiên có nghĩa là HTTP và “MBean” không đồng nghĩa với một URL.

### 2.1. Spring bean: đối tượng trong container

Spring bean được tạo và quản lý bởi Spring IoC container. Container xử lý dependency injection, phạm vi sống, các callback vòng đời và việc cấu hình đối tượng.

\`\`\`java
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public long countPendingOrders() {
        // Giả sử truy vấn dữ liệu nghiệp vụ ở đây.
        return 42;
    }
}
\`\`\`

\`OrderService\` là Spring bean khi được container phát hiện và đăng ký. Mặc định, nó **không tự động trở thành MBean**, **không tự động có HTTP endpoint** và phương thức trả về một con số **không tự động là metric**.

### 2.2. MBean: đối tượng trong hệ thống quản trị JMX

Java Management Extensions (JMX) cung cấp cách chuẩn hóa thông tin quản trị Java. MBean có thể cung cấp:

- **Attribute:** trạng thái có thể đọc và, nếu thiết kế cho phép, ghi.
- **Operation:** hành động quản trị có thể gọi từ JMX client.
- **Notification:** sự kiện quản trị do MBean phát ra, khi được hỗ trợ.

MBean được đăng ký vào \`MBeanServer\` bằng \`ObjectName\`; tên này phục vụ định danh quản trị, khác với tên bean trong Spring container. JMX có thể hoạt động trong cùng JVM; truy cập từ xa chỉ khả dụng nếu có cấu hình và quyền truy cập phù hợp.

Ví dụ thuộc tính \`PendingCount\` và thao tác \`resetStatistics()\` của MBean giám sát hàng đợi không khiến ứng dụng tự có đường dẫn \`/queue\` qua HTTP.

### 2.3. Endpoint: điểm vào được công bố

Một HTTP endpoint được xác định bởi method, URL và hợp đồng request/response. Ví dụ:

\`\`\`java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class QueueController {
    private final OrderService orderService;

    public QueueController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders/pending-count")
    public long pendingCount() {
        return orderService.countPendingOrders();
    }
}
\`\`\`

Đây là HTTP endpoint dùng một Spring bean; nó không vì thế trở thành MBean. Việc public URL, authentication/authorization và network exposure cần được xét độc lập.

Với Spring Boot Actuator, \`health\`, \`info\`, \`metrics\`, \`prometheus\` là những ví dụ endpoint quản trị khi đã có dependency và cấu hình phù hợp. Một số actuator endpoint có thể được expose qua HTTP, JMX hoặc cả hai. Không nên suy ra mọi endpoint đều được bật mặc định.

### 2.4. Metric: đại lượng được đo

Metric ghi nhận **giá trị theo thời gian** nhằm quan sát xu hướng, tỷ lệ, độ trễ hoặc số lượng.

Các loại thường gặp:

- **Counter:** số đếm tích lũy theo sự kiện, ví dụ tổng số tác vụ đã xử lý.
- **Gauge:** giá trị tại thời điểm lấy mẫu, ví dụ số tác vụ đang chờ.
- **Timer:** phân phối thời lượng và thường cả số lần thực hiện.
- **Distribution summary:** phân phối của các giá trị đo không phải thời lượng.

Trong hệ sinh thái Spring, Micrometer là API instrumentation được Spring Boot Actuator sử dụng phổ biến; meter được đăng ký vào \`MeterRegistry\`. Tên metric trong Micrometer có thể được chuyển đổi theo quy ước của hệ thống xuất dữ liệu (ví dụ Prometheus), do đó không nên giả định tên nội bộ và tên xuất ra luôn giống hệt.

\`\`\`java
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class QueueMetrics {
    private final AtomicInteger pending = new AtomicInteger();

    public QueueMetrics(MeterRegistry registry) {
        registry.gauge("orders.pending", pending);
    }

    public void setPending(int count) {
        pending.set(count);
    }
}
\`\`\`

Ví dụ này minh họa một **gauge** phản ánh trạng thái đã cập nhật. \`QueueMetrics\` là một Spring bean nếu được component scan; \`orders.pending\` là metric; bản thân cả hai không tự tạo JMX MBean hay URL HTTP. Trong hệ thống thực tế, trạng thái gauge nên liên kết với nguồn dữ liệu có giá trị hiện hành đáng tin cậy.

## 3. Bản đồ quan hệ: cùng một hệ thống, nhiều lớp nhìn

\`\`\`text
                +-------------------------------+
                | Spring ApplicationContext     |
                |  OrderService (Spring bean)   |
                +-------------------------------+
                    |          |           |
          gọi logic |          | đọc số liệu| dùng để quản trị
                    v          v           v
        HTTP Controller   MeterRegistry   MBean exporter
        /api/...          orders.pending  ObjectName
             |                 |               |
         HTTP client      monitoring backend  JMX client
                              ^
                              |
                    /actuator/prometheus
                    (nếu bật và expose)
\`\`\`

Đây là sơ đồ các **khả năng tích hợp**, không phải pipeline bắt buộc. Một ứng dụng có thể chỉ có Spring bean, hoặc có metrics mà không có custom MBean. Thông tin của cùng một hàng đợi có thể được dùng để trả HTTP response, cập nhật metric, và cung cấp JMX attribute.

Phân biệt ba loại tên:

1. **Bean name** do Spring container quản lý, ví dụ \`orderService\`.
2. **JMX ObjectName** như \`com.example.monitoring:type=Queue,name=Orders\`.
3. **Metric name** như \`orders.pending\`, cộng labels/tags nếu có.

Một URL \`/actuator/metrics/orders.pending\` (nếu được expose) chứa tên metric để truy vấn, nhưng **URL không phải metric**. Nó chỉ là một phương tiện đọc thông tin liên quan đến metric.

## 4. Ví dụ Spring JMX: biến Spring bean thành MBean khi cần

Spring Framework hỗ trợ tích hợp JMX thông qua annotation và \`MBeanExporter\`. Đoạn ví dụ minh họa nguyên tắc, không yêu cầu web server:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Queue,name=Orders",
    description = "Quan ly hang doi don hang"
)
public class OrderQueueMonitor {
    private volatile int pendingCount;

    @ManagedAttribute(description = "So don hang dang cho")
    public int getPendingCount() {
        return pendingCount;
    }

    @ManagedOperation(description = "Dat lai bo dem mo phong")
    public void reset() {
        pendingCount = 0;
    }

    public void updatePendingCount(int value) {
        pendingCount = value;
    }
}
\`\`\`

Cần cấu hình cơ chế export annotation, chẳng hạn:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfig {
    @Bean
    public MBeanExporter mBeanExporter() {
        AnnotationJmxAttributeSource source = new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler = new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming = new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        return exporter;
    }
}
\`\`\`

Khi exporter hoạt động, Spring bean được đăng ký như MBean trong \`MBeanServer\` thích hợp. JConsole có thể duyệt \`ObjectName\` để đọc \`PendingCount\` và gọi \`reset\`, tùy quyền truy cập. Annotation cung cấp metadata quản trị; **\`@Component\` riêng lẻ không export MBean**.

Một dự án Spring Boot có thể hỗ trợ auto-configuration JMX khác với cấu hình Spring Framework thuần. Trong Boot, việc bật JMX export bean được điều khiển bởi cấu hình như \`spring.jmx.enabled\`; không đồng nhất nó với expose Actuator JMX endpoint. Khi sử dụng cấu hình tự động, tránh đăng ký thêm exporter trùng lặp. Đối với Spring Framework không dùng Boot, ví dụ trên minh họa cách khai báo exporter rõ ràng.

**Lưu ý vận hành:** \`reset()\` là operation có tác dụng thay đổi trạng thái. Nếu trạng thái đang được dùng cho nghiệp vụ thật, cần tính đến đồng bộ truy cập, tính nhất quán, phân quyền và hậu quả của hành động; một thao tác quản trị không mặc nhiên an toàn chỉ vì nó nằm trong JMX.

## 5. Bảng phân biệt theo câu hỏi thực tế

| Câu hỏi | Khái niệm bắt đầu từ đó | Lý do |
|---|---|---|
| “Đối tượng này được inject vào service nào?” | Spring bean | Quan hệ phụ thuộc thuộc IoC container |
| “Tôi muốn xem thuộc tính JVM bằng JConsole?” | MBean | JMX expose các đối tượng quản trị |
| “Lấy kết quả từ \`GET /api/orders\`?” | HTTP endpoint | Một route xử lý request/response |
| “Tỷ lệ lỗi HTTP tăng trong 15 phút qua?” | Metric | Cần chuỗi số liệu theo thời gian và phép tổng hợp |
| “Ứng dụng có còn healthy không?” | Health endpoint | Trả đánh giá trạng thái hoạt động |
| “Cho phép operator kích hoạt làm mới cache?” | MBean operation hoặc endpoint quản trị có bảo vệ | Cần giao diện thao tác rõ ràng, có kiểm soát |
| “Có bao nhiêu connection hiện mở?” | Gauge, đôi khi thêm MBean attribute | Một số đo tức thời; JMX có thể cung cấp cùng thông tin |
| “Metrics endpoint có phải là một metric?” | Không | Endpoint phục vụ truy xuất tập metric hoặc phép đo |

Một giá trị “42 đơn đang chờ” có thể xuất hiện ở cả MBean attribute, HTTP response và metric gauge. **Ngữ nghĩa thông tin trùng nhau không làm đồng nhất giao diện truy cập, vòng đời hoặc cách bảo vệ.**

## 6. Mối liên hệ giữa Spring JMX, Spring Boot Actuator và Micrometer

Không nên ghép ba tên này thành một tính năng duy nhất:

- **Spring JMX integration** hỗ trợ xuất Spring-managed object dưới dạng JMX MBean và ánh xạ attribute/operation/notification.
- **Spring Boot Actuator** cung cấp các endpoint quản trị và cơ chế expose chúng qua công nghệ được hỗ trợ, gồm HTTP và JMX tùy cấu hình.
- **Micrometer** thu thập metric qua meter/registry, tích hợp với hệ thống monitoring. Spring Boot Actuator sử dụng Micrometer cho hệ thống metrics thông dụng.

Có thể hình dung:

\`\`\`text
Spring beans  --->  Spring JMX exporter  ---> JMX MBeanServer
       |
       +------->  Web/Actuator endpoints ---> HTTP hoặc JMX exposure
       |
       +------->  Micrometer registry ----> Prometheus/monitoring
                               ^
                         application metrics
\`\`\`

Một Actuator \`metrics\` endpoint không thay thế Micrometer registry; nó là **cách tra cứu** những metric đã được registry cung cấp. Tương tự, một JMX MBean không mặc định xuất hiện trên Prometheus, dù có thể dùng công cụ cầu nối trong kiến trúc phù hợp.

### Tình huống minh họa

Giả sử ứng dụng xử lý đơn hàng và operator cần ba khả năng:

1. **Xem nhanh trạng thái qua JConsole:** tạo custom MBean có attribute \`PendingCount\`.
2. **Tạo dashboard số đơn đang chờ và cảnh báo:** ghi \`orders.pending\` bằng gauge và cấu hình backend giám sát.
3. **Cho hệ thống khác hỏi số đơn đang chờ:** công bố HTTP endpoint có hợp đồng phản hồi và bảo mật.

Ba khả năng có thể gọi chung một service hoặc một nguồn trạng thái. Chọn cách nào phụ thuộc người dùng, tần suất truy cập và giao thức tích hợp; không phải vì hệ thống có JMX thì mọi client đều phải dùng JMX.

## 7. Các nhầm lẫn thường gặp

**Nhầm 1: “Bean Spring nào cũng là MBean.”**  
Sai. Spring bean thuộc container; để thành MBean, đối tượng phải được export/đăng ký qua cơ chế JMX phù hợp. Bean có annotation JMX nhưng thiếu exporter cũng chưa chắc đã có registration.

**Nhầm 2: “MBean và Spring bean là hai instance chắc chắn khác nhau.”**  
Không nhất thiết. Spring exporter có thể expose đối tượng bean gốc thông qua MBean adapter/metadata. Quan trọng là hai **vai trò quản lý** khác nhau, không phải khẳng định số lượng instance.

**Nhầm 3: “Endpoint luôn là URL HTTP.”**  
Sai trong ngữ cảnh Actuator. Endpoint logic có thể có exposure qua JMX. HTTP endpoint thông thường đúng là route mạng.

**Nhầm 4: “Có \`@RestController\` thì endpoint là metric.”**  
Sai. Response chứa số không mặc nhiên là dữ liệu đo được registry quản lý. Metric còn có loại đo, tags, vòng đời lấy mẫu/tổng hợp và khả năng quan sát lịch sử ở backend.

**Nhầm 5: “Gauge và counter có thể đổi cho nhau.”**  
Sai. Giá trị số tác vụ đang chờ có thể tăng/giảm nên hợp với gauge; tổng số tác vụ hoàn thành thường là counter tăng dần. Chọn loại sai sẽ làm dashboard và truy vấn sai ngữ nghĩa.

**Nhầm 6: “Bật Actuator hoặc JMX nghĩa là nên expose tất cả ra công khai.”**  
Sai. Endpoint và JMX operation có thể làm lộ dữ liệu hoặc cho phép điều khiển ứng dụng. Chỉ expose phần cần thiết, áp dụng xác thực/phân quyền và giới hạn mạng phù hợp.

**Nhầm 7: “Metric luôn lưu lịch sử trong ứng dụng.”**  
Không. Registry/instrumentation cung cấp measurement; khả năng lưu giữ, tổng hợp dài hạn, truy vấn và cảnh báo phụ thuộc backend monitoring được cấu hình.

## 8. Hướng dẫn chọn giải pháp

Khi có một yêu cầu quan sát hoặc điều khiển ứng dụng, hãy hỏi lần lượt:

1. **Cần một đối tượng phục vụ nghiệp vụ nội bộ?** Tổ chức thành Spring bean và inject qua container.
2. **Cần thao tác quản trị từ công cụ JMX/Java?** Cân nhắc MBean với attributes và operations rõ ràng, hạn chế thao tác nguy hiểm.
3. **Cần client gọi từ xa bằng API hoặc health check?** Thiết kế endpoint phù hợp cùng authentication, authorization và quản lý exposure.
4. **Cần biểu đồ, cảnh báo hoặc so sánh theo thời gian?** Instrument metric đúng loại (counter/gauge/timer), với nhãn có cardinality hợp lý và backend theo dõi.
5. **Cần cả ba cách quan sát?** Dùng chung nguồn trạng thái đáng tin cậy; tránh mỗi adapter giữ một bản đếm riêng gây lệch dữ liệu.

### Bảo mật và khả năng vận hành

- MBean operation thay đổi trạng thái phải được xem như chức năng quản trị nhạy cảm; hạn chế đối tượng có quyền gọi.
- Không mở JMX remote mặc định chỉ để tiện debug. Nếu cần, cấu hình mạng, xác thực và bảo vệ kênh theo môi trường triển khai.
- Health/metrics endpoint không nên vô tình lộ bí mật, thông tin nội bộ hoặc lượng nhãn cao bất thường.
- Instrumentation nên tránh tạo tags từ giá trị không giới hạn như user ID, request ID hoặc URL động có cardinality lớn; điều này có thể làm tăng chi phí lưu trữ và gánh nặng monitoring.

## 9. Tự kiểm tra kiến thức

**Câu 1.** \`PaymentService\` có \`@Service\`. Nó đã là MBean chưa?  
**Trả lời:** Chưa thể kết luận; \`@Service\` đăng ký Spring bean, còn JMX cần bước export/registration riêng.

**Câu 2.** \`GET /actuator/metrics\` trả danh sách tên đo. Bản thân URL này có phải một metric?  
**Trả lời:** Không. Đó là endpoint dùng để truy vấn metrics (khi đã được expose).

**Câu 3.** “Số kết nối hiện hoạt” phù hợp với metric loại gì?  
**Trả lời:** Gauge vì đại lượng tăng và giảm theo trạng thái hiện tại.

**Câu 4.** Một custom MBean expose operation \`clearCache()\`. Có thể coi nó là API public không?  
**Trả lời:** Không. Đây là thao tác quản trị cần giới hạn truy cập và đánh giá tác dụng phụ.

**Câu 5.** Ứng dụng muốn so sánh latency p95 của API theo thời gian. Chỉ tạo MBean attribute có đủ không?  
**Trả lời:** Thường không đủ. Cần instrument thời lượng dưới dạng timer/distribution phù hợp, export và tổng hợp trong backend monitoring để truy vấn percentile theo thời gian.

## 10. Ghi nhớ

- **Spring bean** là đối tượng nội bộ được Spring container quản lý.
- **MBean** là đối tượng quản trị được đăng ký với JMX \`MBeanServer\` và định danh bằng \`ObjectName\`.
- **Endpoint** là giao diện truy cập chức năng/thông tin; actuator endpoint có thể được expose bằng HTTP hoặc JMX.
- **Metric** là dữ liệu đo có ngữ nghĩa và loại đo, dùng cho quan sát/tổng hợp; nó có thể được endpoint hoặc MBean trình bày nhưng không đồng nhất với các giao diện đó.
- Cùng một dữ liệu trạng thái có thể phục vụ JMX, API và monitoring. Hãy chọn cơ chế theo mục đích truy cập, ngữ nghĩa đo và ranh giới bảo mật.

### Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Boot Reference — Monitoring and Management over JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Spring Boot Reference — Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot Reference — Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Micrometer — Concepts: https://docs.micrometer.io/micrometer/reference/concepts.html
- Oracle Java Management Extensions (JMX) documentation: https://docs.oracle.com/javase/tutorial/jmx/

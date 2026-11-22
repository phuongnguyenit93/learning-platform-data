# Khi nào JMX phù hợp hơn HTTP endpoint hoặc hệ thống metrics?

## Mục tiêu

Sau bài này, bạn có thể quyết định khi nào nên sử dụng Java Management Extensions (JMX), khi nào nên cung cấp HTTP endpoint và khi nào nên dùng hệ thống metrics. Trọng tâm là **mô hình tư duy lựa chọn kênh quản trị/quan sát** trong ứng dụng Spring Framework: ai là người sử dụng, cần đọc hay điều khiển, phạm vi truy cập, vòng đời dữ liệu và chi phí vận hành.

## 1. Ba công cụ trả lời ba nhóm câu hỏi khác nhau

**JMX** là giao diện quản trị và giám sát các tài nguyên Java ở thời gian chạy. JVM cung cấp một `MBeanServer`; các đối tượng quản trị (*MBeans*) công bố thuộc tính, thao tác và đôi khi phát thông báo. Công cụ như JConsole, VisualVM hoặc trình quản lý JMX có thể xem thuộc tính và gọi thao tác. JMX hợp với kỹ sư vận hành/chẩn đoán có quyền quản trị JVM và với hệ thống cần thao tác trực tiếp trên các thành phần nội bộ.

**HTTP endpoint** cung cấp giao diện qua HTTP cho người gọi cụ thể: trình duyệt, client, công cụ vận hành hoặc một dịch vụ khác. Endpoint có thể trả dữ liệu trạng thái, thực thi hành động hoặc phục vụ nghiệp vụ. Đây thường là lựa chọn thuận tiện hơn khi bên gọi không thuộc hệ sinh thái Java, cần dễ tích hợp với hạ tầng web, hoặc đã có cơ chế xác thực/ủy quyền qua HTTP.

**Hệ thống metrics** (chẳng hạn các instrument được thu thập bằng Micrometer và quan sát qua Prometheus/Grafana) chuyên đo các đại lượng theo thời gian: tần suất, độ trễ, tỷ lệ lỗi, mức tiêu thụ tài nguyên. Metrics giúp tạo dashboard, cảnh báo, so sánh nhiều instance và xem xu hướng lịch sử. Metrics **không phải giao diện thao tác quản trị tùy ý**; chúng thường mô tả trạng thái bằng phép đo đã chuẩn hóa.

Ba lựa chọn không loại trừ nhau. Một ứng dụng có thể dùng metrics để giám sát thường trực, HTTP cho health/readiness và thao tác vận hành chuẩn hóa, JMX cho các thuộc tính hoặc thao tác JVM chuyên sâu khi cần.

## 2. Khi nào nên ưu tiên JMX?

### 2.1. Đối tượng cần quản lý là thành phần sống trong JVM

JMX phù hợp khi bạn cần xem một trạng thái nội bộ của bean, cache, thread pool, scheduler hoặc connector Java và trạng thái đó có ý nghĩa trong một JVM cụ thể. Ví dụ:

- Xem số tác vụ đang đợi trong bộ xử lý, cấu hình hiện hành hoặc trạng thái một bộ đệm.
- Chẩn đoán một instance bị kẹt trong lúc các instance còn lại vẫn bình thường.
- Kiểm tra thông tin quản trị đã sẵn có dưới dạng MBean của JVM, thư viện hoặc máy chủ ứng dụng.

**Lý do:** MBean gắn với đối tượng trong tiến trình; cách truy cập phản ánh trực tiếp những gì đối tượng đó xuất bản, không cần tạo một REST contract mới cho mỗi thuộc tính.

### 2.2. Cần thao tác quản trị có chủ đích, tần suất thấp

Một MBean có thể công bố các operations như làm mới một cấu hình đọc lại được, xóa bộ đệm có kiểm soát hoặc kích hoạt một hoạt động chẩn đoán. Đây là những thao tác mang tính *management plane*: người có quyền vận hành thực hiện, có kiểm soát, không phải luồng yêu cầu nghiệp vụ hàng ngày.

Ví dụ: người vận hành cần thực hiện thao tác `resetStatistics()` của một thành phần quản trị trong môi trường thử nghiệm. Nếu giao diện chỉ dùng bởi người quản trị Java, JMX có thể gọn và sát bài toán hơn một HTTP endpoint mới.

**Cẩn trọng:** Mọi operation có tác dụng phụ cần kiểm soát quyền, ghi nhận thao tác và định nghĩa rõ ảnh hưởng; JMX không tự làm cho thao tác trở nên an toàn.

### 2.3. Công cụ quản lý hiện tại đã nói được JMX

JMX đặc biệt thực dụng trong môi trường Java lâu năm, khi các library hoặc máy chủ đã công bố MBean và công cụ vận hành đã có quy trình truy cập. Tận dụng contract quản trị có sẵn thường ít công triển khai hơn xây dựng lớp API bổ sung.

### 2.4. Dữ liệu cần quan sát chi tiết tại một thời điểm

Một người đang điều tra sự cố có thể cần đọc thuộc tính động hoặc kiểm tra cấu hình tức thời, chưa đủ ổn định để định nghĩa thành metric tiêu chuẩn. JMX hỗ trợ kiểu điều tra tương tác như vậy. Nếu một giá trị về sau trở thành tín hiệu cần alert hàng ngày, nên bổ sung metric được thiết kế rõ ràng.

## 3. Khi nào HTTP endpoint phù hợp hơn?

Chọn HTTP khi người dùng hoặc hệ thống gọi giao diện cần **contract web rõ ràng** và khả năng tích hợp rộng:

- Client được viết bằng nhiều ngôn ngữ, hoặc công cụ bên ngoài chỉ hỗ trợ HTTP/JSON.
- Cần quản lý phiên bản API, schema, mã lỗi, giới hạn tốc độ, xác thực và ủy quyền theo cơ chế API hiện có.
- Muốn công bố health, readiness, diagnostics ở phạm vi đã chọn; ví dụ trong ứng dụng Spring Boot có thể dùng các endpoint Actuator phù hợp.
- Cần một thao tác được tự động hóa qua pipeline hoặc hệ thống quản trị tập trung; API phải quy định đầu vào, kết quả, tính lặp lại và audit.
- Ứng dụng chạy trong container/Kubernetes, nơi việc vận hành thường dựa trên HTTP probes và hệ thống gateway/service networking.

**Phân biệt:** Một HTTP endpoint quản trị không đương nhiên an toàn hơn JMX. Các endpoint nhạy cảm phải được giới hạn mạng, xác thực, phân quyền và kiểm soát nội dung trả về. Đừng phơi bày dữ liệu cấu hình bí mật chỉ vì có URL quen thuộc.

### Ví dụ: hợp đồng trạng thái qua HTTP

```http
GET /internal/health
Accept: application/json
```

```json
{
  "status": "UP",
  "dependencies": {
    "database": "UP"
  }
}
```

Đây là ví dụ minh họa về một endpoint nội bộ do ứng dụng tự định nghĩa, **không phải schema mặc định được bảo đảm của Spring Boot Actuator**. Dữ liệu health thích hợp để một hệ thống ngoài JVM tiêu thụ; trái lại việc xem sâu trạng thái một Java bean riêng lẻ có thể hợp với MBean.

## 4. Khi nào metrics phù hợp hơn?

Ưu tiên metrics khi câu hỏi có dạng **bao nhiêu, nhanh hay chậm, tỷ lệ thay đổi thế nào, có vượt ngưỡng không**:

- Request rate, error rate, latency percentile, thời gian xử lý công việc.
- Bộ nhớ heap đang sử dụng, số thread, mức bão hòa connection pool.
- So sánh nhiều instance theo phút/giờ/ngày, dựng biểu đồ và cảnh báo tự động.
- Xác định thời điểm suy giảm và tương quan với triển khai hoặc lượng tải.

Metrics yêu cầu **mô hình đo có chủ đích**: tên, đơn vị, loại instrument, tag/dimension và tính toán aggregate. Metric tốt thường có tập nhãn có cardinality giới hạn, chứ không xuất nguyên mọi thuộc tính động hoặc ID riêng lẻ của MBean.

Ví dụ (đo thành công/thất bại bằng Spring/Micrometer):

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public final class JobMetrics {
    private final Counter completed;

    public JobMetrics(MeterRegistry registry) {
        this.completed = Counter.builder("jobs.completed")
                .description("Number of completed jobs")
                .register(registry);
    }

    public void recordCompletion() {
        completed.increment();
    }
}
```

Ví dụ này **giả định ứng dụng đã cấu hình Micrometer và MeterRegistry**; metrics backend và exporter là các quyết định cấu hình riêng. Counter giúp theo dõi tiến trình hoặc tốc độ hoàn tất jobs theo thời gian; nó không thay thế thao tác quản trị như `pauseQueue()`.

### Vì sao không biến mọi MBean attribute thành metric?

- Các thuộc tính là text phức tạp hoặc thay đổi liên tục thường không thành phép đo dễ tổng hợp.
- Nhiều tag chứa job ID/user ID có thể làm nổ cardinality, tăng chi phí lưu trữ và truy vấn.
- Một MBean operation là lệnh có tác dụng phụ, không có cách biểu diễn tương đương bằng counter/gauge.
- Dữ liệu quản trị nhạy cảm có thể bị phát tán nếu tự động export sang hệ thống metrics tập trung.

Nếu một thư viện chỉ cung cấp số liệu qua JMX, bạn có thể dùng cầu nối JMX exporter hoặc instrumentation tương ứng, nhưng phải thiết kế danh sách metric và nhãn cụ thể; không xuất tràn lan.

## 5. Bảng quyết định nhanh

| Tiêu chí | JMX | HTTP endpoint | Metrics |
|---|---|---|---|
| Người dùng điển hình | Kỹ sư Java/vận hành có quyền | Client, orchestrator, automation, ops | Monitoring, SRE, dashboard/alert |
| Kiểu dữ liệu chính | Thuộc tính, operation, notification của MBean | Response/request theo API contract | Số đo, chuỗi thời gian, aggregate |
| Phạm vi | JVM/instance cụ thể | API/app hoặc service cụ thể | Nhiều instance, nhiều service |
| Tương tác điều khiển | Có, qua MBean operations | Có, nếu thiết kế endpoint | Không dành cho việc phát lệnh |
| Quan sát lịch sử | Không phải chức năng cốt lõi | Phải tự xây hoặc lưu trữ ngoài | Được thiết kế cho lưu trữ/truy vấn lịch sử |
| Client không dùng Java | Thường phức tạp hơn | Dễ tích hợp | Dễ truy vấn qua backend/visualization |
| Phù hợp cảnh báo | Không phải lựa chọn mặc định | Dùng cho probe hoặc automation riêng | Lựa chọn mặc định cho chỉ số/ngưỡng |
| Lưu ý | Bảo mật kết nối JMX, giới hạn quyền và mạng | Auth, authorization, rate limits, audit | Cardinality, đơn vị, nhãn, retention |

**Câu hỏi quyết định:**

1. Bạn cần **gọi một thao tác quản trị** hay **đo một xu hướng**? Nếu là xu hướng, ưu tiên metrics.
2. Một hệ thống ngoài Java cần contract chuẩn qua mạng? Nếu có, ưu tiên HTTP.
3. Bạn đang chẩn đoán hoặc điều khiển một thành phần Java đã có MBean trong môi trường quản trị tin cậy? JMX thường hợp lý.
4. Phải giám sát và cảnh báo nhiều bản sao ứng dụng liên tục? Dùng metrics, kể cả khi dữ liệu ban đầu được thu thập từ JMX.
5. Giao diện có thể làm gián đoạn vận hành? Dù chọn JMX hay HTTP, phải thiết kế quyền, audit và rào chắn thao tác trước.

## 6. JMX trong Spring Framework: ví dụ cụ thể

Spring Framework hỗ trợ xuất bản bean thành MBean qua `MBeanExporter`, và hỗ trợ annotation `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation` để mô tả giao diện quản trị. Ví dụ thuần Spring dưới đây minh họa một trạng thái quan sát được và một lệnh vận hành có chủ đích:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "example.management:name=JobQueue",
    description = "Management view for the job queue"
)
public class JobQueueManagement {
    private volatile boolean paused;

    @ManagedAttribute(description = "Whether job acceptance is paused")
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation(description = "Pause acceptance of new jobs")
    public void pause() {
        paused = true;
    }

    @ManagedOperation(description = "Resume acceptance of new jobs")
    public void resume() {
        paused = false;
    }
}
```

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.support.RegistrationPolicy;

@Configuration
public class JmxConfiguration {
    @Bean
    JobQueueManagement jobQueueManagement() {
        return new JobQueueManagement();
    }

    @Bean
    MBeanExporter mBeanExporter(JobQueueManagement queue) {
        AnnotationJmxAttributeSource source = new AnnotationJmxAttributeSource();
        MetadataMBeanInfoAssembler assembler = new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setBeans(java.util.Map.of(
                "example.management:name=JobQueue", queue
        ));
        exporter.setRegistrationPolicy(RegistrationPolicy.FAIL_ON_EXISTING);
        return exporter;
    }
}
```

**Cách hiểu ví dụ:** `paused` là thuộc tính của một object đang chạy; `pause()` và `resume()` là thao tác điều khiển. Trong ứng dụng thực tế, các thao tác này cần kết nối với cơ chế xử lý queue thật, bảo đảm đồng bộ thread, kiểm tra trạng thái, phân quyền và audit. Đoạn mã chỉ mô phỏng mục đích lựa chọn giao diện. MBean được đăng ký trong `MBeanServer` có thể được nhìn thấy bởi client JMX đã cấu hình truy cập phù hợp.

**Lưu ý tích hợp:** Trong ứng dụng Spring Boot, cơ chế tự động xuất MBean, endpoint Actuator và Micrometer phụ thuộc phiên bản, starter và cấu hình của ứng dụng. Không mặc định rằng mọi bean đều được xuất thành MBean hoặc mọi endpoint quản trị đều được mở công khai.

## 7. Tình huống thực tế và lựa chọn

### Tình huống A: cache nội bộ có thể cần làm sạch thủ công

Một instance đôi lúc giữ dữ liệu cache sai trong môi trường quản trị kín. Kỹ sư cần xem `entryCount`, `lastRefreshTime` và kích hoạt `clearCache()`.

**Lựa chọn:** JMX phù hợp nếu chỉ công cụ vận hành Java được phép thao tác và chức năng đã tồn tại trong MBean. Đồng thời xuất cache hit/miss và eviction counters sang metrics để theo dõi lâu dài. Nếu automation bên ngoài phải dùng hành động này thường xuyên, cân nhắc HTTP admin API có xác thực và audit.

### Tình huống B: nhiều pod tăng latency sau deploy

Đội vận hành cần dashboard so sánh P95/P99 latency, error rate và số request giữa các pod.

**Lựa chọn:** Metrics, vì dữ liệu cần biểu đồ thời gian, tổng hợp và cảnh báo. Có thể bổ sung HTTP readiness/liveness. JMX chỉ là công cụ điều tra cụ thể từng JVM khi dấu hiệu cho thấy vấn đề nội bộ.

### Tình huống C: kiểm tra readiness trước khi nhận traffic

Load balancer hoặc Kubernetes cần kiểm tra liệu ứng dụng sẵn sàng tiếp nhận yêu cầu hay chưa.

**Lựa chọn:** HTTP health/readiness endpoint với quy ước trạng thái ổn định. Không yêu cầu orchestrator mở phiên JMX để quyết định routing.

### Tình huống D: hệ thống Java legacy đã có nhiều MBean

Một thành phần từ lâu công bố trạng thái connector và thao tác quản trị qua MBean; công cụ vận hành hiện tại đã hỗ trợ nó.

**Lựa chọn:** Tiếp tục dùng JMX cho chẩn đoán và quản trị có phân quyền. Chỉ bổ sung HTTP hoặc metrics khi xuất hiện nhu cầu tích hợp web hoặc giám sát thời gian thực bằng dashboard/cảnh báo.

### Tình huống E: cần một công cụ tự động điều khiển queue

Hệ thống điều phối độc lập cần gửi lệnh pause/resume, cung cấp identity, lý do thao tác, trạng thái xử lý và log audit.

**Lựa chọn:** HTTP admin API thường phù hợp hơn vì giao diện cần contract rõ cho bên gọi ngoài JVM. Bên trong API có thể sử dụng cùng service quản trị mà MBean gọi; tránh viết hai logic nghiệp vụ khác nhau.

## 8. An toàn vận hành và phạm vi mạng

- **JMX remote** phải được thiết kế như một bề mặt quản trị đặc quyền: giới hạn mạng, cấu hình xác thực, mã hóa đường truyền khi cần, tránh mở cổng quản trị trực tiếp ra Internet. Cơ chế kết nối remote có thể liên quan đến RMI và yêu cầu cấu hình cổng/mạng riêng, đặc biệt trong container.
- **JMX local** tiện để chẩn đoán JVM cùng host hoặc trong môi trường đã có quyền truy cập máy. Quyền truy cập tiến trình và chính sách JVM vẫn rất quan trọng.
- **HTTP management** cần phân biệt với public business API; giới hạn endpoint nhạy cảm theo network/role, log các thao tác gây thay đổi trạng thái.
- **Metrics endpoint** cũng có thể tiết lộ tên service, cấu hình, cấu trúc nội bộ, hành vi tải hoặc dữ liệu nhạy cảm trong tag. Chỉ xuất những metric/label thực sự cần thiết và giới hạn quyền truy cập.
- Một thay đổi cấu hình có thể tác động mọi request. Xác nhận quyền truy cập, phạm vi instance, tính idempotent, khả năng rollback và dấu vết vận hành trước khi cho phép thực thi.

## 9. Những ngộ nhận cần tránh

**“JMX là một dạng metrics.”** JMX có thể cung cấp số liệu nhưng còn quản lý thuộc tính và thao tác. Hệ thống metrics bổ sung thu thập, lưu trữ, tổng hợp và cảnh báo theo thời gian.

**“HTTP endpoint thay thế toàn bộ JMX.”** HTTP có thể mô phỏng một phần thao tác, nhưng hệ sinh thái Java có nhiều MBean có sẵn để chẩn đoán tại JVM. Việc tạo endpoint mới chỉ có ích nếu tồn tại nhu cầu client hoặc vận hành rõ ràng.

**“Có JMX thì không cần đo metrics.”** Đọc thủ công từng MBean không thay thế việc phát hiện suy giảm trên nhiều instance theo thời gian.

**“JMX chỉ phù hợp ứng dụng đơn máy.”** JMX vẫn dùng được trong hệ phân tán nếu mô hình truy cập được thiết kế phù hợp, nhưng mỗi kết nối/đối tượng quản trị thường thuộc một JVM; việc tổng hợp xu hướng liên service cần một lớp khác.

**“Đưa MBean operation lên web là đủ.”** Khi mở rộng đối tượng gọi, phải định nghĩa API contract và kiểm soát quyền, input, tác dụng phụ, retry, timeout và audit.

## 10. Checklist lựa chọn cho một yêu cầu mới

Hãy điền ngắn gọn năm thông tin trước khi triển khai:

1. **Người gọi:** kỹ sư vận hành Java, orchestrator, client bên ngoài, hay hệ thống monitoring?
2. **Câu hỏi chính:** chẩn đoán trạng thái hiện tại, thực thi thao tác, kiểm tra health, hay đo xu hướng?
3. **Phạm vi:** một JVM/instance hay hàng chục service/instance?
4. **Tần suất:** thỉnh thoảng, theo mỗi lần deploy, hay thu thập định kỳ liên tục?
5. **Ràng buộc:** xác thực, quyền, mạng/container, độ nhạy dữ liệu, audit và chi phí nhãn/thời gian lưu trữ?

Nếu phần lớn câu trả lời là “công cụ Java, JVM riêng lẻ, xem thuộc tính hoặc gọi operation hiếm khi”, chọn **JMX**. Nếu là “client đa nền tảng, API contract, automation và health”, chọn **HTTP**. Nếu là “thu thập liên tục, biểu đồ, cảnh báo và so sánh nhiều instance”, chọn **metrics**. Khi có đồng thời nhiều nhu cầu, kết hợp các kênh với trách nhiệm và quyền truy cập rõ ràng.

## 11. Bài tập vận dụng

Một dịch vụ Spring có hai yêu cầu:

- Đội SRE muốn báo động khi hàng đợi vượt 5.000 phần tử trong 10 phút và so sánh mức tăng giữa các pod.
- Kỹ sư trực ca đôi khi cần dừng tiếp nhận job mới trên đúng một JVM đang điều tra lỗi.

Hãy chọn kênh cho từng yêu cầu và giải thích. Gợi ý: yêu cầu đầu là số liệu cần lưu theo thời gian → **gauge metrics** với nhãn instance/pod được kiểm soát; yêu cầu sau là điều khiển ở phạm vi JVM → **JMX MBean operation** nếu môi trường quản trị đã hỗ trợ, hoặc **HTTP admin endpoint** nếu công cụ điều khiển ở ngoài hệ sinh thái Java. Cả hai thao tác cần xác thực và audit tương ứng.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java Management Extensions (JMX) Technology: https://docs.oracle.com/javase/8/docs/technotes/guides/jmx/
- Spring Boot Actuator: https://docs.spring.io/spring-boot/reference/actuator/index.html
- Micrometer Concepts: https://docs.micrometer.io/micrometer/reference/concepts.html
- Prometheus — Metric and label naming: https://prometheus.io/docs/practices/naming/

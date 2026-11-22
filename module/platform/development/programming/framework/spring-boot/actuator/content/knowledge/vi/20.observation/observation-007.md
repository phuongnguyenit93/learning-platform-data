# Lọc hoặc bổ sung dữ liệu bằng ObservationPredicate và ObservationFilter

## 1. Hai câu hỏi khác nhau: có quan sát và ghi thêm điều gì?

Một ứng dụng có thể tạo observation cho xử lý báo cáo, gọi HTTP hoặc chạy tác vụ nền. Khi số điểm quan sát tăng lên, cần chính sách dùng chung: bỏ qua một số hoạt động kiểm tra nội bộ, không đưa dữ liệu thử vào thống kê nghiệp vụ, hoặc gắn vùng triển khai và kết quả xử lý vào dữ liệu quan sát.

Micrometer cung cấp hai cơ chế có vai trò khác nhau:

- `ObservationPredicate`: quyết định một lần quan sát có được kích hoạt hay không.
- `ObservationFilter`: điều chỉnh `Observation.Context` trước khi thông báo kết thúc đến các bộ xử lý (`ObservationHandler`).

Tên `Filter` dễ khiến người học nghĩ nó dùng để loại bỏ cả observation. Ở đây, quyết định giữ/bỏ thuộc về predicate; filter ánh xạ hoặc bổ sung dữ liệu của context đã được chấp nhận. [Nguồn: Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html).

`Observation.Context` mang dữ liệu của một lần quan sát để các handler sử dụng; scope là phạm vi thiết lập ngữ cảnh quan sát hiện tại.

Bài này đặt trong Spring Boot 3.3.x, dùng ví dụ chạy được với Spring Boot 3.3.0 và Micrometer 1.13.0. Mục tiêu là hiểu đúng thời điểm thực thi để chính sách lọc không làm sai dữ liệu hoặc vô tình tác động đến logic nghiệp vụ.

## 2. Vị trí của predicate và filter trong vòng đời

Với cách tạo observation được sử dụng trong bài:

```text
Chuẩn bị context có dữ liệu đầu vào
    → gọi createNotStarted(name, contextSupplier, registry)
    → xét các ObservationPredicate
        → có predicate trả false: dùng observation no-op
        → tất cả trả true: có observation hoạt động
    → start và các handler onStart
    → chạy tác vụ trong scope; có thể báo lỗi/sự kiện
    → khi stop: áp dụng các ObservationFilter
    → các handler onStop nhận context đã qua filter
```

Observation không thực hiện ghi nhận (no-op) vẫn cho phép tác vụ bên trong `observe(...)` chạy. Nó không phải một câu lệnh `if` để chặn chức năng. Vì vậy, predicate không thay thế kiểm tra quyền truy cập, xác thực đầu vào hay công tắc bật/tắt nghiệp vụ.

Ở Micrometer 1.13.0, overload `createNotStarted(name, contextSupplier, registry)` lấy context, xét điều kiện cho phép và trả observation no-op nếu điều kiện không đạt. Việc này xảy ra ngay trong lời gọi tạo, trước các lời gọi gắn nhãn được nối phía sau. [Nguồn: Observation.java 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-observation/src/main/java/io/micrometer/observation/Observation.java).

Ở bước kết thúc, `SimpleObservation` áp dụng các filter nối tiếp rồi chuyển context kết quả cho `onStop`. [Nguồn: SimpleObservation.java 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-observation/src/main/java/io/micrometer/observation/SimpleObservation.java).

| Đặc điểm | ObservationPredicate | ObservationFilter |
| --- | --- | --- |
| Dữ liệu nhận | Tên và context tại lúc xét | Context tại lúc kết thúc |
| Kết quả trả về | `boolean` | `Observation.Context` |
| Mục đích | Cho phép hoặc bỏ ghi nhận observation | Bổ sung, chuẩn hóa hoặc loại khóa dữ liệu trong context |
| Biết được lỗi cuối cùng của tác vụ chưa? | Chưa thể biết lỗi còn chưa xảy ra | Có thể đọc lỗi đã được báo vào context |
| Ngăn mã nghiệp vụ chạy? | Không | Không |
| Tự thay thế chính sách xuất metrics/trace? | Không | Không |

## 3. ObservationPredicate: quyết định trước khi bắt đầu

### 3.1. Đọc tên từ tham số và xét đúng loại context

`ObservationPredicate` có dạng kiểm tra `test(String name, Observation.Context context)`. Trong Micrometer 1.13, nó mở rộng `BiPredicate<String, Observation.Context>`, nên có thể viết bằng lambda. [Nguồn: ObservationPredicate 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-observation/src/main/java/io/micrometer/observation/ObservationPredicate.java).

Một quy tắc dựa trên tên có thể bỏ các observation có tiền tố `internal.`. Với chính sách dựa trên dữ liệu nghiệp vụ, nên dùng context có kiểu cụ thể và kiểm tra kiểu trước khi truy cập.

Trong ví dụ, `RenderContext` có cờ `synthetic` cho biết lượt chạy được tạo để kiểm tra hệ thống. Predicate bỏ ghi nhận các lượt synthetic nhưng không cản chúng tạo kết quả. Nếu context thuộc loại khác, predicate này cho qua; nó không có quyền tự suy rằng mọi hoạt động khác đều phải bị loại.

Dùng tham số `name` để kiểm tra tên trong predicate. Đừng mặc định mọi thuộc tính của context đã được điền đầy đủ giống giai đoạn `onStop`.

### 3.2. Dữ liệu phải có trước lúc predicate chạy

Xét chuỗi lời gọi:

```text
createNotStarted(...) → lowCardinalityKeyValue(...) → observe(...)
```

Predicate đã được xét trong bước đầu, nên không thể đọc một nhãn chỉ được thêm ở bước thứ hai để quyết định chính lần tạo đó. Cũng không thể chờ filter bổ sung dữ liệu rồi quay lại quyết định có bắt đầu observation hay không.

Cách thiết kế phù hợp trong bài là chuẩn bị cờ `synthetic` trong `RenderContext` trước khi đưa context vào `createNotStarted`. Các trường đã biết lúc đầu phục vụ quyết định sớm; nhãn tổng hợp có thể được gắn riêng ở thời điểm thích hợp.

Nếu một context của framework đã có sẵn dữ liệu khi tạo, predicate có thể dùng dữ liệu đó. Điểm cần kiểm tra là **thời điểm dữ liệu tồn tại**, không phải một quy tắc rằng predicate tuyệt đối không được đọc nhãn.

Không dùng `context.getError() != null` để chọn “chỉ quan sát các lượt sau này sẽ thất bại”. Lỗi chưa xảy ra tại lúc quyết định sớm. Có thể quan sát rồi phân loại kết quả khi kết thúc; chính sách lấy mẫu trace theo dữ liệu hoàn tất là một vấn đề khác.

### 3.3. Nhiều predicate được kết hợp theo AND

Một observation chỉ được phép khi tất cả predicate đã đăng ký đều trả `true`. Gặp `false` thì việc xét có thể dừng sớm. [Nguồn: ObservationRegistry.ObservationConfig 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-observation/src/main/java/io/micrometer/observation/ObservationRegistry.java).

| Quy tắc tên | Quy tắc synthetic | Observation được ghi nhận? |
| --- | --- | --- |
| Cho qua | Cho qua | Có |
| Chặn | Cho qua | Không |
| Cho qua | Chặn | Không |
| Chặn | Chặn | Không |

Hai bean predicate không tạo thành hai lựa chọn OR. Nếu một chính sách cần điều kiện A **hoặc** B, diễn đạt OR bên trong chính predicate đó; các predicate còn lại vẫn là điều kiện bắt buộc.

Không đặt tác dụng phụ nghiệp vụ vào predicate hoặc phụ thuộc vào việc mọi predicate đều được gọi. Predicate nên nhẹ, rõ ràng và chỉ đọc dữ liệu cần thiết.

## 4. ObservationFilter: bổ sung dữ liệu trước onStop

### 4.1. Sửa context và trả lại context

`ObservationFilter` có phương thức `Observation.Context map(Observation.Context context)`. Hợp đồng của nó là điều chỉnh context và trả về context kết quả. [Nguồn: ObservationFilter 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-observation/src/main/java/io/micrometer/observation/ObservationFilter.java).

Trong ví dụ, filter chỉ xử lý `RenderContext` của hoạt động `report.render`, rồi thêm:

| Khóa | Loại | Giá trị trong bài |
| --- | --- | --- |
| `region` | Low cardinality | `vn-south` |
| `result` | Low cardinality | `completed` hoặc `failed` |
| `request.id` | High cardinality | Mã yêu cầu của từng lần chạy |

Filter có thể đọc `context.getError()` để phân loại lỗi đã được báo vào observation. `completed` trong bài chỉ có nghĩa không có lỗi được báo, không phải lời xác nhận mọi giao dịch hoặc tác vụ bên ngoài đều đã thành công.

Với context ngoài phạm vi, trả lại nguyên context. Với context cần xử lý, thông thường sửa chính đối tượng đang có rồi trả lại nó. Không trả `null` để bỏ observation và không tùy tiện thay bằng `new Observation.Context()`: các handler có thể đã lưu trạng thái như mẫu đo thời gian trong context ban đầu.

Nếu có nhiều filter, kết quả của filter trước được chuyển sang filter tiếp theo. Hai filter cùng thay một khóa có thể làm kết quả phụ thuộc thứ tự đăng ký. Nên tách trách nhiệm rõ, tránh việc một filter phải đoán filter khác đã chạy hay chưa; nếu cần thứ tự, khai báo và kiểm chứng trong cách tích hợp đang dùng.

### 4.2. Filter chạy muộn, không sửa được quá khứ

Một nhãn thêm trước `onStop` có thể xuất hiện trong timer được hoàn tất tại `onStop`. Nó không tự quay lại bổ sung vào dữ liệu mà handler đã tạo ở `onStart`, hoặc vào sự kiện/log đã được xử lý từ trước.

Với `DefaultMeterObservationHandler` 1.13, long-task timer có thể được tạo ngay lúc bắt đầu, còn timer tổng hợp của hoạt động được ghi khi kết thúc. Nhãn có sau thời điểm bắt đầu không được tự thêm ngược vào long-task timer đó. [Nguồn: DefaultMeterObservationHandler 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/observation/DefaultMeterObservationHandler.java).

Vì vậy, nếu `region` cần xuất hiện trên cả phép đo đang hoạt động, đặt nó trước khi bắt đầu hoặc dùng quy ước quan sát phù hợp. Bài tập cố ý thêm `region` bằng filter để nhìn thấy giới hạn thời điểm này.

Tương tự, xóa một khóa trong filter cuối không bảo đảm dữ liệu nhạy cảm chưa từng được một handler khác đọc trước đó. Không đưa dữ liệu không cần thiết vào context từ đầu rồi dựa hoàn toàn vào filter cuối để thu hồi.

### 4.3. Giữ số lượng giá trị nhãn trong giới hạn

Low cardinality có tập giá trị nhỏ, được kiểm soát. `result` chỉ có hai giá trị trong bài; `request.id` thay đổi theo từng yêu cầu nên dùng high cardinality. Theo luồng mặc định, nhãn low cardinality được dùng cho metrics và trace, nhãn high cardinality không làm nhãn metrics. [Nguồn: Spring Boot — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Filter không làm một mã yêu cầu tự trở thành dữ liệu có độ đa dạng thấp. Không đưa ID hoặc thông báo lỗi tùy ý vào nhãn metrics chỉ vì việc bổ sung diễn ra ở một nơi tập trung.

## 5. Đăng ký trong Spring Boot

Trong ứng dụng có Actuator và cấu hình quan sát, khai báo các bean `ObservationPredicate` và `ObservationFilter`. Boot tự đăng ký những bean đó vào `ObservationRegistry` do ứng dụng quản lý. Không cần tự tạo một registry khác trong dịch vụ. [Nguồn: Spring Boot — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Ví dụ đầy đủ bên dưới sử dụng:

- Hai bean predicate: bỏ tên nội bộ và bỏ dữ liệu synthetic.
- Một bean filter: bổ sung dữ liệu mô tả cho báo cáo được quan sát.
- Một handler kiểm chứng: ghi lại dữ liệu thấy lúc bắt đầu và kết thúc.
- Một dịch vụ sử dụng registry được tiêm vào hàm khởi tạo.

Nếu dùng Micrometer thuần ngoài Boot, đăng ký qua `registry.observationConfig().observationPredicate(...)` và `.observationFilter(...)`, đồng thời cấu hình các handler cần thiết. Đừng vừa đăng ký thủ công vừa để Boot đăng ký cùng chính sách mà không kiểm tra tác động lặp.

Với quy tắc đơn giản dựa trên tên, Boot còn có cấu hình như:

```properties
management.observations.enable.internal=false
```

Đối với tên `internal.report.check` trong bài, cấu hình đó có thể diễn đạt việc bỏ ghi nhận mà không cần predicate tên viết bằng Java. Đây là lựa chọn cấu hình thay thế cho chính sách tương ứng, không phải một bước bắt buộc bổ sung vào ví dụ. Một predicate khác trả `true` không mở lại được một observation đã bị chính sách khác chặn.

## 6. Thực hành: bỏ ghi nhận hai lượt nhưng vẫn chạy đủ bốn tác vụ

### 6.1. Kịch bản

Chương trình tạo bản biểu diễn văn bản đơn giản cho báo cáo. Đây là thí nghiệm về chính sách quan sát, không phải bộ xuất PDF hay hệ thống lưu báo cáo hoàn chỉnh.

| Lượt | Tên | Synthetic | Kết quả nghiệp vụ | Có được quan sát? |
| --- | --- | --- | --- | --- |
| R-1 | `report.render` | `false` | Trả văn bản bình thường | Có |
| R-2 | `report.render` | `true` | Vẫn trả văn bản kiểm tra | Không |
| R-3 | `internal.report.check` | `false` | Vẫn trả kết quả kiểm tra nội bộ | Không |
| R-4 | `report.render` | `false` | Nội dung trống, ném lỗi | Có |

Filter chạy cho hai observation được chấp nhận. Nó thêm nhãn kết quả sau khi đã biết nhánh thành công hay lỗi. Bộ kiểm chứng cũng cho thấy `region` chưa có lúc bắt đầu nhưng có lúc kết thúc.

### 6.2. Tệp pom.xml

Cần JDK 17 trở lên và Maven. Tạo thư mục thực hành riêng, đặt `pom.xml` và `ObservationPolicyApplication.java` cạnh nhau. Lần tải dependency đầu cần mạng.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.0</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>observation-policy-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
  </dependencies>
</project>
```

Parent cố định bộ phiên bản tương thích. Không cần thêm thư viện registry bên ngoài cho thí nghiệm giữ metrics trong bộ nhớ.

### 6.3. Tệp ObservationPolicyApplication.java

```java
package example.policy;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.common.KeyValue;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationFilter;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationPredicate;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableAutoConfiguration
public class ObservationPolicyApplication {
    static final String REPORT = "report.render";

    static final class RenderContext extends Observation.Context {
        final String requestId;
        final boolean synthetic;

        RenderContext(String requestId, boolean synthetic) {
            this.requestId = requestId;
            this.synthetic = synthetic;
        }
    }

    static final class ReportService {
        private final ObservationRegistry registry;
        final AtomicInteger businessRuns = new AtomicInteger();

        ReportService(ObservationRegistry registry) {
            this.registry = registry;
        }

        String render(String requestId, boolean synthetic, String body) {
            return execute(REPORT, requestId, synthetic, body);
        }

        String internalCheck(String requestId) {
            return execute("internal.report.check", requestId, false, "check");
        }

        private String execute(String name, String requestId, boolean synthetic, String body) {
            RenderContext context = new RenderContext(requestId, synthetic);
            return Observation.createNotStarted(name, () -> context, registry)
                .lowCardinalityKeyValue("format", "text")
                .observe(() -> {
                    businessRuns.incrementAndGet();
                    if (body.isBlank()) {
                        throw new IllegalArgumentException("Empty report");
                    }
                    return requestId + "|" + body.strip();
                });
        }
    }

    static final class ReportMetadataFilter implements ObservationFilter {
        final AtomicInteger calls = new AtomicInteger();

        @Override
        public Observation.Context map(Observation.Context context) {
            if (!(context instanceof RenderContext render) || !REPORT.equals(context.getName())) {
                return context;
            }
            calls.incrementAndGet();
            context.addLowCardinalityKeyValue(KeyValue.of("region", "vn-south"));
            context.addLowCardinalityKeyValue(KeyValue.of("result",
                context.getError() == null ? "completed" : "failed"));
            context.addHighCardinalityKeyValue(KeyValue.of("request.id", render.requestId));
            return context;
        }
    }

    static final class LifecycleAudit implements ObservationHandler<Observation.Context> {
        final List<String> startRegions = new CopyOnWriteArrayList<>();
        final List<String> stopRegions = new CopyOnWriteArrayList<>();
        final List<String> stopRequestIds = new CopyOnWriteArrayList<>();

        private static String value(KeyValue keyValue) {
            return keyValue == null ? "missing" : keyValue.getValue();
        }

        @Override
        public boolean supportsContext(Observation.Context context) {
            return context instanceof RenderContext && REPORT.equals(context.getName());
        }

        @Override
        public void onStart(Observation.Context context) {
            startRegions.add(value(context.getLowCardinalityKeyValue("region")));
        }

        @Override
        public void onStop(Observation.Context context) {
            stopRegions.add(value(context.getLowCardinalityKeyValue("region")));
            stopRequestIds.add(value(context.getHighCardinalityKeyValue("request.id")));
        }
    }

    @Bean
    ObservationPredicate skipInternalObservations() {
        return (name, context) -> !name.startsWith("internal.");
    }

    @Bean
    ObservationPredicate skipSyntheticReports() {
        return (name, context) ->
            !(context instanceof RenderContext render && render.synthetic);
    }

    @Bean
    ReportMetadataFilter reportMetadataFilter() {
        return new ReportMetadataFilter();
    }

    @Bean
    LifecycleAudit lifecycleAudit() {
        return new LifecycleAudit();
    }

    @Bean
    ReportService reportService(ObservationRegistry registry) {
        return new ReportService(registry);
    }

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(ObservationPolicyApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);
        application.setDefaultProperties(Map.of(
            "logging.level.root", "OFF",
            "management.metrics.use-global-registry", "false",
            "management.observations.long-task-timer.enabled", "true"));

        try (ConfigurableApplicationContext context = application.run(args)) {
            ReportService service = context.getBean(ReportService.class);
            MeterRegistry meters = context.getBean(MeterRegistry.class);
            ObservationRegistry observations = context.getBean(ObservationRegistry.class);
            ReportMetadataFilter filter = context.getBean(ReportMetadataFilter.class);
            LifecycleAudit audit = context.getBean(LifecycleAudit.class);

            System.out.println("normal.result=" + service.render("R-1", false, "Revenue"));
            System.out.println("synthetic.result=" + service.render("R-2", true, "Probe"));
            System.out.println("internal.result=" + service.internalCheck("R-3"));
            try {
                service.render("R-4", false, " ");
            } catch (IllegalArgumentException error) {
                System.out.println("failed=" + error.getClass().getSimpleName());
            }

            System.out.println("business.runs=" + service.businessRuns.get());
            System.out.println("timer.completed="
                + meters.get(REPORT).tag("result", "completed").timer().count());
            System.out.println("timer.failed="
                + meters.get(REPORT).tag("result", "failed").timer().count());
            System.out.println("filter.calls=" + filter.calls.get());
            System.out.println("start.region=" + audit.startRegions);
            System.out.println("stop.region=" + audit.stopRegions);
            System.out.println("stop.requestIds=" + audit.stopRequestIds);
            boolean requestIdIsTag = meters.find(REPORT).timers().stream()
                .anyMatch(timer -> timer.getId().getTag("request.id") != null);
            System.out.println("timer.hasRequestId=" + requestIdIsTag);
            System.out.println("active.hasRegion="
                + (meters.get(REPORT + ".active").longTaskTimer().getId().getTag("region") != null));
            System.out.println("current.cleared=" + (observations.getCurrentObservation() == null));
        }
    }
}
```

### 6.4. Biên dịch và chạy

Trong PowerShell, tại thư mục chứa hai tệp:

```powershell
mvn dependency:copy-dependencies -DincludeScope=runtime
New-Item -ItemType Directory -Force -Path target/classes | Out-Null
javac --release 17 -encoding UTF-8 -cp "target/dependency/*" -d target/classes ObservationPolicyApplication.java
java -cp "target/classes;target/dependency/*" example.policy.ObservationPolicyApplication
```

Trên Linux/macOS, tạo thư mục bằng `mkdir -p target/classes` và thay dấu `;` phân cách các mục classpath của `java` bằng `:`. Package là `example.policy`; khi biên dịch trực tiếp từ tệp, `-d` tạo cây package trong thư mục đích. Trong dự án Maven thông thường, đặt tệp tại `src/main/java/example/policy/`.

Ứng dụng không mở máy chủ web, không gọi hệ thống giám sát bên ngoài. Nó tắt banner/log khởi động để phần stdout dễ đối chiếu; cấu hình này chỉ phục vụ bài tập.

Chạy nguyên trạng sẽ có stdout:

```text
normal.result=R-1|Revenue
synthetic.result=R-2|Probe
internal.result=R-3|check
failed=IllegalArgumentException
business.runs=4
timer.completed=1
timer.failed=1
filter.calls=2
start.region=[missing, missing]
stop.region=[vn-south, vn-south]
stop.requestIds=[R-1, R-4]
timer.hasRequestId=false
active.hasRegion=false
current.cleared=true
```

### 6.5. Đọc các bằng chứng

1. Ba dòng kết quả đầu và dòng `failed` cho thấy logic nghiệp vụ vẫn chạy ở cả bốn lượt, kể cả R-2 và R-3 bị loại khỏi quan sát.
2. `business.runs=4` xác nhận tổng số lần thực thi trong lambda. Predicate không chặn các tác vụ đó.
3. `timer.completed=1` và `timer.failed=1` chỉ thuộc hai observation qua được cả hai predicate.
4. `filter.calls=2` cho thấy filter không chạy cho hai observation no-op đã bị chặn.
5. `start.region=[missing, missing]` và `stop.region=[vn-south, vn-south]` kiểm chứng filter bổ sung dữ liệu ở giai đoạn kết thúc.
6. `stop.requestIds=[R-1, R-4]` cho thấy dữ liệu high cardinality đã có khi handler nhận `onStop` của hai observation hợp lệ.
7. `timer.hasRequestId=false` xác nhận mã yêu cầu không được thêm làm nhãn timer mặc định.
8. `active.hasRegion=false` chứng minh nhãn được thêm muộn không tự xuất hiện trên long-task timer đã tạo trước đó.
9. `current.cleared=true` xác nhận sau các lượt chạy không còn observation hiện tại trong luồng của ví dụ.

Chương trình bật tường minh `management.observations.long-task-timer.enabled=true` để nhìn thấy phép đo `.active`. Điều đó không làm filter chạy sớm hơn. Các bộ đếm và danh sách trong filter/handler là dữ liệu kiểm chứng của bài, không phải yêu cầu giữ lịch sử mọi observation trong bộ nhớ của ứng dụng thật.

Ví dụ không cài tracer nên không khẳng định đã xuất span ra nơi lưu trace. Nó kiểm tra chính sách ở cấp Observation và phép đo metrics được tạo từ đó.

## 7. Những giới hạn cần giữ đúng khi áp dụng

### 7.1. Predicate áp dụng cho từng observation

Chặn một tên hoặc một context không có nghĩa mọi observation con, mọi phép đo trực tiếp bằng `MeterRegistry` hoặc mọi log của tác vụ đều bị chặn. Mỗi điểm quan sát có điều kiện của nó; log hoặc mã đo được gọi độc lập vẫn có đường thực thi riêng.

Khi viết predicate toàn cục, luôn kiểm tra phạm vi tên hoặc loại context. Một nhánh `return false` dành cho mọi context không nhận ra có thể vô tình loại dữ liệu của framework mà bạn không định tác động.

### 7.2. Filter không phải lớp cô lập lỗi

Filter nằm trong đường hoàn tất observation. Ở cách triển khai được dùng trong bài, chuỗi filter được gọi trước khi thông báo `onStop`; không nên giả định việc ném lỗi trong filter sẽ được tự động bỏ qua. Lỗi từ chính sách quan sát có thể làm lời gọi thất bại hoặc che mất lỗi gốc.

Giữ filter nhanh, không gọi dịch vụ mạng chỉ để tra nhãn ở cuối mỗi tác vụ. Với dữ liệu môi trường ổn định, đọc từ cấu hình đã có; với dữ liệu nghiệp vụ, đưa trường cần thiết vào context theo vòng đời phù hợp. Trả context hợp lệ và giữ trạng thái các handler đang sử dụng.

### 7.3. Bổ sung và loại khóa phải có mục tiêu rõ

`Observation.Context` có thể thêm hoặc xóa khóa, chẳng hạn `removeLowCardinalityKeyValue(...)`. Tuy nhiên, sửa ở bước cuối chỉ tác động dữ liệu được đọc sau đó; không thu hồi một meter hoặc sự kiện đã được tạo từ trước.

Cũng không đổi tên observation ở cuối để kỳ vọng toàn bộ handler đã bắt đầu bằng tên cũ tự được sửa đồng nhất. Nếu mục tiêu là quy ước tên/nhãn của một loại thao tác, xem xét `ObservationConvention` và thời điểm dữ liệu cần xuất hiện.

Nếu nhiều chính sách dùng cùng một khóa, hãy xác định rõ ai sở hữu khóa đó và giá trị nào được ưu tiên. Không phụ thuộc vào thứ tự tên lớp hoặc vị trí tệp trong mã nguồn.

## 8. Chọn đúng cơ chế cho từng nhu cầu

| Nhu cầu | Cơ chế nên xem xét |
| --- | --- |
| Không ghi nhận cả điểm quan sát cho một số tên/context | `ObservationPredicate` hoặc cấu hình bật/tắt Observation của Boot |
| Bổ sung dữ liệu mô tả khi hoạt động kết thúc | `ObservationFilter` |
| Đặt tên và nhãn theo một quy ước của loại thao tác | `ObservationConvention` |
| Cần dữ liệu có ngay khi handler bắt đầu | Chuẩn bị context/nhãn trước bắt đầu hoặc dùng convention phù hợp |
| Chỉ lọc một số meter của metrics | Chính sách cấp `MeterRegistry`, chẳng hạn `MeterFilter` |
| Điều chỉnh việc lấy mẫu trace | Cấu hình lấy mẫu của tracing |
| Bật/tắt tính năng nghiệp vụ hoặc kiểm tra quyền | Logic/cơ chế nghiệp vụ tương ứng |

Tên gọi “lọc” không có nghĩa các cơ chế này thay thế nhau. Một ObservationPredicate có thể loại cả dữ liệu metrics và tracing do điểm quan sát đó sinh ra, trong khi MeterFilter chỉ xử lý ở đường metrics.

## 9. Chẩn đoán các nhầm lẫn thường gặp

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Predicate không thấy nhãn vừa nối sau createNotStarted | Nhãn đó được thêm sau lúc predicate đã xét; chuẩn bị dữ liệu cần quyết định trong context từ trước |
| Chỉ muốn giữ lỗi nhưng không thấy observation nào | Đang dùng kết quả chưa xảy ra làm điều kiện sớm, chẳng hạn kiểm tra getError trong predicate |
| Hai predicate tưởng là OR nhưng dữ liệu bị loại | Các predicate được kết hợp theo AND |
| Filter thêm nhãn nhưng onStart vẫn không thấy | Filter chạy trước onStop, không trước onStart |
| Timer có region nhưng phép đo active không có | Hai meter đọc dữ liệu mô tả tại hai thời điểm khác nhau |
| Bean filter có mặt nhưng dịch vụ không bị tác động | Dịch vụ có thể đang dùng registry tự tạo thay vì bean registry của Boot, hoặc observation đã bị predicate chặn |
| Không có dữ liệu sau khi filter trả null/context mới | Filter không phải cách bỏ observation; phải trả context hợp lệ và bảo toàn trạng thái cần thiết |
| Đã loại observation nhưng tác vụ vẫn thực hiện | Đây là hành vi đúng: predicate điều khiển ghi nhận, không điều khiển nghiệp vụ |

Trong kiểm tra thực tế, cần quan sát cả bốn thứ: số lần tác vụ chạy, số observation được chấp nhận, dữ liệu handler thấy lúc bắt đầu và dữ liệu thấy lúc kết thúc. Chỉ nhìn một biểu đồ trống sẽ không phân biệt được lỗi đăng ký registry, predicate chặn hay đường xuất chưa hoạt động.

## 10. Tự kiểm tra

1. Vì sao R-2 vẫn có kết quả dù predicate dành cho synthetic trả false?
2. Nếu một predicate tên cho qua nhưng predicate context chặn, kết quả chung là gì?
3. Nhãn được thêm bằng lowCardinalityKeyValue ngay sau createNotStarted có chắc đã tồn tại khi predicate của chính lời tạo đó chạy không?
4. Vì sao filter có thể phân loại result theo lỗi trong ví dụ, còn predicate không thể dùng lỗi tương lai để chọn observation?
5. Nếu cần region trên cả timer kết thúc và long-task timer, chỉ thêm region bằng filter cuối đã đủ chưa?
6. Vì sao không trả null hoặc một Context trống để “lọc bỏ” dữ liệu?
7. Hai filter ghi cùng một khóa sẽ cần quan tâm điều gì?

Đáp án: (1) No-op bỏ ghi nhận quan sát chứ không bỏ thực thi lambda. (2) Bị chặn vì điều kiện chung là AND. (3) Không; với overload trong bài, predicate chạy trước bước gắn nhãn nối tiếp. (4) Filter chạy khi kết thúc và lỗi đã được báo; predicate quyết định sớm. (5) Chưa; dữ liệu cần có tại thời điểm tạo phép đo đang hoạt động. (6) Có thể làm mất trạng thái handler hoặc gây lỗi; predicate mới là nơi quyết định không ghi nhận. (7) Phạm vi, quyền sở hữu khóa và thứ tự áp dụng phải rõ, có kiểm chứng.

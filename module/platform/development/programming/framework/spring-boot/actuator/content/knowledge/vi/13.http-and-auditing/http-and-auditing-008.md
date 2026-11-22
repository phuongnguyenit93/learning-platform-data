# Phát hành sự kiện kiểm toán đặc thù qua ApplicationEventPublisher

Khi một người xuất báo cáo, người vận hành có thể cần trả lời: ai đã thực hiện, thao tác nào đã hoàn tất, trên báo cáo nào và thuộc yêu cầu nào? Một dòng log tùy ý thường khó truy vấn thống nhất. Sự kiện kiểm toán (audit event) biểu diễn thông tin đó thành bản ghi có cấu trúc.

Bài này dùng Spring Boot Actuator 3.3.x để phát sự kiện nghiệp vụ qua `ApplicationEventPublisher`. Sau bài học, bạn có thể tạo `AuditApplicationEvent`, cung cấp nơi nhận bản ghi, kiểm chứng dữ liệu đã lưu và chọn thời điểm phát phù hợp với ý nghĩa của sự kiện.

## 1. Từ hành động nghiệp vụ đến bản ghi kiểm toán

Giả sử hệ thống có hành động xuất báo cáo. Quy ước của ứng dụng là:

- `REPORT_EXPORT_REQUESTED`: đã tiếp nhận yêu cầu xuất.
- `REPORT_EXPORTED`: việc xuất đã hoàn tất theo tiêu chí của nghiệp vụ.
- `REPORT_EXPORT_DENIED`: yêu cầu xuất bị từ chối.

Đây là các tên do ứng dụng đặt; Actuator không tự suy ra chúng từ tên phương thức hay mã HTTP. Việc một người đăng nhập thành công cũng chưa nói rằng họ đã xuất báo cáo. Vì vậy, sự kiện bảo mật có sẵn và sự kiện kiểm toán nghiệp vụ bổ sung cho nhau.

Spring Boot hỗ trợ kiểm toán nghiệp vụ bằng cách ghi trực tiếp vào `AuditEventRepository` hoặc phát `AuditApplicationEvent` qua cơ chế sự kiện của Spring. Với cách phát sự kiện, lớp nghiệp vụ chỉ cần biết bộ phát; việc lưu được giao cho phía lắng nghe. [Tài liệu kiểm toán Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html).

Luồng chuẩn khi hạ tầng kiểm toán đã được cấu hình:

```text
Thao tác nghiệp vụ đạt mốc cần ghi nhận
    -> ApplicationEventPublisher.publishEvent(AuditApplicationEvent)
    -> cơ chế phân phối sự kiện trong ApplicationContext
    -> AuditListener của Actuator
    -> AuditEventRepository.add(AuditEvent)
```

`ApplicationEventPublisher` phân phối sự kiện. `AuditEventRepository` lưu và tìm bản ghi. Hai trách nhiệm này cần được phân biệt: gọi `publishEvent(...)` chưa tự chứng minh rằng có bản ghi bền vững.

## 2. Ba kiểu dữ liệu cần phân biệt

| Thành phần | Vai trò | Cách sử dụng trong bài |
| --- | --- | --- |
| `ApplicationEventPublisher` | Giao diện phát sự kiện của Spring | Được tiêm qua hàm khởi tạo, gọi `publishEvent(...)` |
| `AuditApplicationEvent` | Sự kiện Spring bao một `AuditEvent` | Đối tượng được phát để listener kiểm toán của Actuator nhận |
| `AuditEvent` | Dữ liệu kiểm toán | Đối tượng được lưu trong repository và đọc lại để kiểm chứng |

Một `AuditEvent` có các trường quan trọng:

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `principal` | Danh tính chủ thể thực hiện | `alice` hoặc danh tính tác vụ hệ thống |
| `type` | Loại sự kiện theo quy ước ổn định | `REPORT_EXPORTED` |
| `timestamp` | Thời điểm của bản ghi, có kiểu `Instant` | Được tạo khi dựng bản ghi nếu không truyền riêng |
| `data` | Thông tin bổ sung, kiểu `Map<String, Object>` | Mã báo cáo, mã yêu cầu, kết quả |

Cách tạo thường dùng:

```java
Map<String, Object> data = Map.of(
        "reportId", "report-42",
        "requestId", "req-001",
        "outcome", "SUCCESS");
publisher.publishEvent(
        new AuditApplicationEvent("alice", "REPORT_EXPORTED", data));
```

Đoạn trên là phần trích trong một bean đã được tiêm `ApplicationEventPublisher`; cần import `java.util.Map` và `org.springframework.boot.actuate.audit.listener.AuditApplicationEvent`.

Bạn cũng có thể dựng `AuditEvent` trước rồi bao bằng `new AuditApplicationEvent(auditEvent)`. Cách này hữu ích khi cần truyền thời điểm nghiệp vụ cụ thể bằng constructor nhận `Instant`. Không truyền thời điểm do máy khách tự khai làm bằng chứng thời gian đáng tin cậy mà chưa xác định rõ nguồn dữ liệu. [API AuditApplicationEvent](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/audit/listener/AuditApplicationEvent.html). Các constructor dùng ở đây có trong Spring Boot 3.3.0.

### Vì sao không phát thẳng AuditEvent?

```java
publisher.publishEvent(new AuditEvent(
        "alice", "REPORT_EXPORTED", Map.of("reportId", "report-42")));
```

Đoạn trích này có thể biên dịch khi có các import tương ứng, nhưng không đi vào đường nhận mặc định của `AuditListener`. `AuditEvent` là dữ liệu; `AuditApplicationEvent` mới là kiểu sự kiện mà listener này đăng ký nhận. Cơ chế sự kiện Spring có thể bao đối tượng thông thường thành sự kiện chứa dữ liệu, nhưng không tự chuyển nó thành `AuditApplicationEvent`. Nếu dùng bộ nhận mặc định, hãy phát đúng lớp bao.

### Quy ước dữ liệu giúp truy vấn nhất quán

- Giữ `type` ổn định; đưa mã đối tượng vào `data`, chẳng hạn `type=REPORT_EXPORTED` và `data.reportId=report-42`. Tránh tạo một loại mới cho từng báo cáo.
- Lấy `principal` từ nguồn danh tính đã được ứng dụng xác minh. Trong ứng dụng có Spring Security, có thể lấy tên từ thông tin xác thực đã kiểm tra; không tin một trường `username` tùy ý trong nội dung yêu cầu.
- Với tác vụ định kỳ, dùng danh tính hệ thống được quy ước rõ, chẳng hạn `system:report-job`.
- Chỉ đưa dữ liệu cần để giải thích hành động vào `data`; chọn chuỗi, số hoặc giá trị đơn giản mà nơi lưu hỗ trợ. Tránh đưa thực thể JPA, đối tượng request hoặc toàn bộ nội dung báo cáo.
- Không đưa mật khẩu, access token, session ID hoặc thông tin bí mật vào bản ghi. Mã yêu cầu dùng để liên hệ các quan sát, không thay thế việc kiểm tra quyền.
- Chụp dữ liệu tại thời điểm phát; không tiếp tục thay đổi cấu trúc lồng nhau rồi kỳ vọng bên nhận thấy đúng trạng thái ban đầu. `Map.of(...)` tạo map không sửa được, nhưng các đối tượng nằm bên trong vẫn có thể thay đổi nếu bạn đưa đối tượng có trạng thái vào.

`Map.of(...)` không chấp nhận khóa hoặc giá trị `null`. Nếu mã yêu cầu có thể thiếu, hãy quyết định bỏ trường đó hoặc từ chối đầu vào theo hợp đồng của ứng dụng; đừng để một lỗi tạo map xảy ra sau thao tác nghiệp vụ mà không dự tính.

## 3. Điều kiện để Actuator tự lưu sự kiện

Trong cấu hình mặc định của Spring Boot 3.3, chỉ thêm starter Actuator chưa đủ để có nơi lưu kiểm toán. Cần cung cấp một bean `AuditEventRepository`.

```java
@Bean
AuditEventRepository auditEventRepository() {
    return new InMemoryAuditEventRepository(100);
}
```

Đây là phương thức cấu hình trích từ ví dụ đầy đủ ở phần sau. Kho bộ nhớ này phù hợp cho thử nghiệm: không cần cơ sở dữ liệu và có thể đọc lại ngay trong cùng tiến trình.

`AuditAutoConfiguration` yêu cầu có bean `AuditEventRepository` và thuộc tính `management.auditevents.enabled` không bị tắt. Bean `AuditListener` mặc định chỉ được tạo khi chưa có bean thuộc kiểu `AbstractAuditListener`. Nếu bạn thay listener này, cần kiểm tra chính bộ nhận thay thế còn thực hiện việc lưu theo mong muốn hay không. [API AuditAutoConfiguration 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/audit/AuditAutoConfiguration.html).

Các trường hợp dễ nhầm:

- Không có repository: đường lưu tự động này không được thiết lập; riêng việc phát sự kiện có thể vẫn hoàn tất nếu không có bộ nhận tương ứng.
- Có repository nhưng đặt `management.auditevents.enabled=false`: tự cấu hình kiểm toán bị tắt, nên không thể kỳ vọng listener mặc định tự gọi `add(...)`.
- Có listener tự viết: kết quả phụ thuộc cách đăng ký và xử lý của listener đó.
- Có repository bộ nhớ: bản ghi chỉ tồn tại trong bộ nhớ của tiến trình và bị giới hạn theo dung lượng cấu hình. Một instance khác không tự nhìn thấy dữ liệu này.

Muốn lưu lâu dài hoặc tổng hợp nhiều instance, cần triển khai `AuditEventRepository` phù hợp với nơi lưu của hệ thống. Khi chọn nơi lưu, xác định cách truy vấn, giữ dữ liệu và xử lý lỗi theo nhu cầu thực tế. Spring Boot khuyến nghị kho bộ nhớ cho môi trường phát triển. [Hướng dẫn chọn repository kiểm toán](https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html).

## 4. Ví dụ độc lập có thể chạy

Ví dụ chỉ kiểm chứng việc phát và nhận sự kiện. Hàm `recordExportCompleted(...)` ghi nhận một việc đã được phía nghiệp vụ xác nhận hoàn tất; nó không tạo tệp báo cáo và không giả lập rằng đã thực hiện đầy đủ nghiệp vụ xuất báo cáo.

Yêu cầu: JDK 17 trở lên và Maven. Mã dùng mức ngôn ngữ Java 17 và có thể chạy bằng JDK 21. Phiên bản Spring Boot được cố định ở 3.3.0 để tái lập ví dụ thuộc dòng 3.3.x.

Ứng dụng chạy dạng dòng lệnh, không khởi động HTTP server. Vì vậy có thể học cơ chế kiểm toán mà chưa cần tạo controller, cấu hình endpoint hoặc đưa Spring Security vào ví dụ.

Cấu trúc dự án thử nghiệm riêng:

```text
audit-publisher-demo/
├── pom.xml
└── src/main/java/example/audit/AuditDemoApplication.java
```

### 4.1. Khai báo phụ thuộc

Nội dung `pom.xml`:

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
    <artifactId>audit-publisher-demo</artifactId>
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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Starter Actuator đưa các thành phần cần cho ví dụ vào classpath. Không tự thêm phiên bản riêng cho từng thư viện Spring, vì parent Spring Boot quản lý tập phiên bản tương ứng.

### 4.2. Cấu hình repository và phát sự kiện

Nội dung `src/main/java/example/audit/AuditDemoApplication.java`:

```java
package example.audit;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;
import org.springframework.boot.actuate.audit.listener.AuditApplicationEvent;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(proxyBeanMethods = false)
public class AuditDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(AuditDemoApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);
        application.setDefaultProperties(
                Map.of("logging.level.root", "OFF"));

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            context.getBean(ReportAuditService.class)
                    .recordExportCompleted("alice", "report-42", "req-001");

            AuditEventRepository repository =
                    context.getBean(AuditEventRepository.class);
            List<AuditEvent> events = repository.find(
                    "alice", Instant.EPOCH, "REPORT_EXPORTED");
            if (events.size() != 1) {
                throw new IllegalStateException(
                        "Expected one audit event, got " + events.size());
            }

            AuditEvent event = events.get(0);
            System.out.println("count=" + events.size());
            System.out.println("principal=" + event.getPrincipal());
            System.out.println("type=" + event.getType());
            System.out.println("reportId=" + event.getData().get("reportId"));
            System.out.println("requestId=" + event.getData().get("requestId"));
            System.out.println("outcome=" + event.getData().get("outcome"));
        }
    }

    @Bean
    AuditEventRepository auditEventRepository() {
        return new InMemoryAuditEventRepository(100);
    }

    @Bean
    ReportAuditService reportAuditService(
            ApplicationEventPublisher publisher) {
        return new ReportAuditService(publisher);
    }

    public static class ReportAuditService {
        private final ApplicationEventPublisher publisher;

        public ReportAuditService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void recordExportCompleted(
                String principal, String reportId, String requestId) {
            requireText(principal, "principal");
            requireText(reportId, "reportId");
            requireText(requestId, "requestId");

            Map<String, Object> data = Map.of(
                    "reportId", reportId,
                    "requestId", requestId,
                    "outcome", "SUCCESS");
            publisher.publishEvent(new AuditApplicationEvent(
                    principal, "REPORT_EXPORTED", data));
        }

        private static void requireText(String value, String name) {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException(name + " is required");
            }
        }
    }
}
```

Các điểm cần theo dõi:

1. `ReportAuditService` nhận `ApplicationEventPublisher` qua hàm khởi tạo. Đối tượng được khai báo bằng `@Bean`, nên Spring cung cấp bộ phát; không cần triển khai `ApplicationEventPublisherAware` chỉ để lấy bộ phát.
2. `requireText(...)` kiểm tra đầu vào trước khi phát. Trong ví dụ, `alice` là dữ liệu cố định để quan sát luồng; khi tích hợp thật, nơi gọi phải truyền danh tính từ nguồn đáng tin.
3. Sự kiện mang `principal=alice`, loại `REPORT_EXPORTED` và ba trường dữ liệu. Không có thao tác gọi trực tiếp `repository.add(...)` trong service.
4. Bean `InMemoryAuditEventRepository(100)` cho phép tự cấu hình của Actuator thiết lập listener lưu kiểm toán. Dung lượng 100 là lựa chọn của ví dụ.
5. Sau khi phát, phần `main` đọc lại repository và kiểm tra có đúng một bản ghi. Đây là kiểm chứng cho cả đường phát lẫn đường lưu, vượt quá việc chỉ nhìn thấy lệnh `publishEvent(...)` đã được gọi.
6. `Instant.EPOCH` được chọn làm mốc trước bản ghi vừa tạo. Bộ lọc gồm danh tính và loại giúp không lấy nhầm sự kiện khác. Ví dụ không in toàn bộ map nên không phụ thuộc thứ tự duyệt của `Map.of(...)`.
7. Khi ra khỏi khối `try`, context được đóng và ứng dụng kết thúc. Kho bộ nhớ không duy trì lịch sử cho lần chạy tiếp theo.

### 4.3. Biên dịch và chạy

Tại thư mục chứa `pom.xml`, chạy:

```shell
mvn -q package
java -jar target/audit-publisher-demo-1.0.0.jar
```

Maven cần tải plugin và phụ thuộc trong lần đầu nếu máy chưa có chúng. Dự án có phụ thuộc Spring nên không thể biên dịch chỉ bằng `javac AuditDemoApplication.java` khi chưa cung cấp classpath.

Phần stdout của chương trình với cấu hình trên:

```text
count=1
principal=alice
type=REPORT_EXPORTED
reportId=report-42
requestId=req-001
outcome=SUCCESS
```

Banner và log khởi động đã được tắt trong mã để phần kết quả dễ quan sát. Timestamp không được in vì được tạo theo thời gian chạy; không nên viết một giá trị thời gian cố định rồi coi đó là kết quả của mọi lần chạy.

### 4.4. Vì sao chưa cần /actuator/auditevents?

Việc lưu bản ghi và việc cho phép truy cập bản ghi qua HTTP là hai việc riêng. Ví dụ đọc `AuditEventRepository` trực tiếp nên không cần mở endpoint. Trong ứng dụng web, cấu hình exposure và quyền truy cập chỉ cần xét khi muốn cung cấp giao diện đọc qua Actuator; không dùng thao tác mở endpoint để thay cho cấu hình repository. Bản ghi kiểm toán có thể chứa dữ liệu nhạy cảm, nên chỉ cho các chủ thể phù hợp quyền đọc khi triển khai giao diện đó.

## 5. Gọi publishEvent có nghĩa gì về thời điểm xử lý?

Với cơ chế phân phối mặc định của Spring, listener thông thường được gọi đồng bộ trên luồng phát. Vì vậy, khi ví dụ vừa phát xong và đọc repository, bản ghi đã được listener bộ nhớ thêm vào. Nếu thay cấu hình bộ phân phối hoặc dùng xử lý bất đồng bộ, thời điểm đó có thể khác. Bản thân giao diện phát không phải cam kết rằng mọi ứng dụng luôn xử lý theo cùng một cách. [Cơ chế sự kiện trong ApplicationContext](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events).

Hệ quả cần tính khi tích hợp:

- Listener ghi chậm có thể làm lời gọi nghiệp vụ chậm theo trong cấu hình đồng bộ.
- Lỗi từ listener đồng bộ có thể truyền ngược về nơi phát nếu không có cơ chế xử lý lỗi khác.
- Thêm xử lý bất đồng bộ cần tính cả thời điểm đọc, lỗi xử lý và ngữ cảnh danh tính. Hãy đưa dữ liệu cần thiết vào sự kiện thay vì mặc định luồng khác vẫn có thông tin của yêu cầu ban đầu.
- Sự kiện nội bộ này không tự trở thành thông điệp gửi sang tiến trình khác. Gửi sang hệ thống bên ngoài cần một cơ chế tích hợp riêng.

Vì `publishEvent(...)` không trả về biên nhận lưu trữ, tiêu chí quan sát nên là bản ghi đã xuất hiện ở đúng nơi lưu, với đúng nội dung và đúng thời điểm mà thiết kế yêu cầu.

## 6. Đặt thời điểm phát theo đúng ý nghĩa nghiệp vụ

Trong ví dụ, người gọi đã xác nhận thao tác hoàn tất rồi mới gọi `recordExportCompleted(...)`. Với dữ liệu có giao dịch, cần xác định rõ từ “hoàn tất” có nghĩa là phương thức đã chạy tới một dòng lệnh hay giao dịch đã commit.

### 6.1. Phát trong giao dịch chưa có nghĩa là đã commit

Tình huống cần tránh:

```text
Bắt đầu giao dịch
    -> cập nhật trạng thái báo cáo
    -> phát REPORT_EXPORTED
    -> listener ghi vào kho bộ nhớ
    -> có lỗi ở bước tiếp theo
Rollback giao dịch
```

Kho bộ nhớ không tự rollback theo cơ sở dữ liệu. Kết quả có thể là bản ghi mang tên đã xuất thành công dù cập nhật nghiệp vụ bị hủy. Đặt lệnh phát sau `save(...)` cũng chưa tự chứng minh commit đã xảy ra.

Quyết định dựa trên ý nghĩa bạn cần:

| Điều cần ghi nhận | Thời điểm phù hợp để cân nhắc |
| --- | --- |
| Đã tiếp nhận một lần thử | Sau khi xác định yêu cầu và chủ thể; dùng tên biểu thị yêu cầu hoặc lần thử |
| Quyết định từ chối đã được đưa ra | Tại nơi quyết định từ chối, với dữ liệu tối thiểu giải thích quyết định |
| Thay đổi trong cơ sở dữ liệu đã commit | Sau commit hoặc thiết kế lưu cùng giao dịch với dữ liệu nghiệp vụ |
| Cần giữ bằng chứng dù giao dịch nghiệp vụ rollback | Đường lưu có chính sách giao dịch độc lập và kiểm chứng riêng |

### 6.2. Khi cần ghi nhận sau commit

Một phương án là phát sự kiện nghiệp vụ trong giao dịch, rồi chuyển thành sự kiện kiểm toán ở bộ nhận sau commit:

```text
Phương thức nghiệp vụ chạy trong giao dịch
    -> phát sự kiện nghiệp vụ ReportExportCompleted
    -> giao dịch commit
    -> bean có @TransactionalEventListener(AFTER_COMMIT) nhận sự kiện nghiệp vụ
    -> phát AuditApplicationEvent
    -> AuditListener lưu bản ghi kiểm toán
```

Đây là sơ đồ tích hợp, không phải phần mã đang chạy trong ví dụ dòng lệnh. Cần có quản lý giao dịch phù hợp và bean bộ nhận được đăng ký.

`@TransactionalEventListener` mặc định xử lý ở `AFTER_COMMIT`; khi không có giao dịch, mặc định không gọi listener, trừ khi bật `fallbackExecution`. Nếu ghi cơ sở dữ liệu sau commit, cần thiết kế giao dịch ghi riêng phù hợp, vì không thể dựa vào giao dịch cũ để commit thêm thay đổi. [API TransactionalEventListener của Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html).

Đừng chỉ thêm một listener sau commit cùng nghe `AuditApplicationEvent` rồi cho rằng listener mặc định sẽ chờ theo. Listener lưu sẵn vẫn có đường xử lý riêng. Phương án ở sơ đồ giữ sự kiện nghiệp vụ và sự kiện kiểm toán tách biệt về thời điểm: chỉ phát `AuditApplicationEvent` khi đã đạt mốc cần ghi.

Sau commit vẫn tồn tại khoảng thời gian tiến trình có thể dừng trước khi việc lưu kiểm toán hoàn tất. Nếu yêu cầu không được mất sự kiện khi tiến trình dừng, cần thiết kế lưu bền vững, chẳng hạn lưu bản ghi cần chuyển trong cùng giao dịch nghiệp vụ rồi xử lý tiếp. `ApplicationEventPublisher` một mình không cung cấp bảo đảm đó.

## 7. Tránh ghi trùng và hiểu chính sách lỗi

### 7.1. Chọn một đường lưu cho mỗi lần ghi nhận

Không vừa làm cả hai việc sau cho cùng một lần ghi nhận khi listener mặc định đang hoạt động:

```java
repository.add(auditEvent);
publisher.publishEvent(new AuditApplicationEvent(auditEvent));
```

Đây là đoạn minh họa lỗi, không phải đoạn cần bổ sung vào ví dụ. Lần gọi đầu đã thêm bản ghi; lần phát sau có thể khiến listener thêm lại. Một listener tự viết chỉ để quan sát cũng không nên gọi `add(...)` thêm lần nữa nếu đường lưu mặc định vẫn chạy.

Tương tự, hai lần gọi `recordExportCompleted(...)` tạo hai lần phát. `requestId` chỉ là dữ liệu đi kèm; Actuator không tự khử trùng chỉ vì hai bản ghi có cùng mã yêu cầu.

Cần phân biệt hai câu hỏi nghiệp vụ:

- Hai lần yêu cầu xuất thực sự khác nhau: có thể cần hai bản ghi, dù cùng một báo cáo.
- Cùng một sự kiện được gửi lại do retry: có thể cần nhận diện để tránh lưu hai lần theo chính sách đã chọn.

Nếu cần khử trùng, hãy xác định mã sự kiện ổn định và thực hiện quy tắc ở nơi lưu phù hợp. Không giả định việc dùng map không sửa được sẽ tạo ra cơ chế chống trùng.

### 7.2. Quyết định hành vi khi không lưu được

Ví dụ kho bộ nhớ giúp thấy luồng thành công, chưa mô tả chính sách lỗi của một nơi lưu từ xa. Trước khi tích hợp nơi lưu thật, xác định:

- Hành động nghiệp vụ có được tiếp tục nếu việc ghi kiểm toán thất bại không?
- Nếu nghiệp vụ đã commit nhưng ghi kiểm toán thất bại, nơi nào giữ thông tin để xử lý lại?
- Làm sao quan sát được lỗi mà không ghi thêm dữ liệu bí mật vào log?
- Khi thử lại, làm sao phân biệt một lần phát lại với một hành động mới?

Không bắt mọi ngoại lệ rồi bỏ qua chỉ để giữ đầu ra đẹp. Cũng không mặc định rằng lỗi xuất hiện ở phía gọi đồng nghĩa nghiệp vụ chưa xảy ra: một listener có thể lỗi sau khi phần nghiệp vụ đã hoàn tất.

## 8. Thực hành kiểm chứng và chẩn đoán

Mỗi thí nghiệm dưới đây bắt đầu từ một lần chạy mới để tránh trộn dữ liệu từ thí nghiệm trước.

| Thay đổi | Điều cần quan sát | Giải thích |
| --- | --- | --- |
| Giữ nguyên ví dụ | Một bản ghi, sáu dòng stdout như trên | Đúng đường phát, đúng listener, đúng nơi lưu |
| Gọi service hai lần với cùng tham số | Repository chứa hai bản ghi | Chưa có cơ chế khử trùng |
| Truyền `principal` là chuỗi trắng | `IllegalArgumentException` trước khi phát | Điều kiện đầu vào do service kiểm tra |
| Phát `AuditEvent` thuần thay cho `AuditApplicationEvent` | Listener mặc định không thêm bản ghi đó | Phát sai kiểu sự kiện cho đường kiểm toán chuẩn |
| Tắt `management.auditevents.enabled` | Repository vẫn có thể tồn tại nhưng không nhận bản ghi qua listener mặc định | Tắt tự cấu hình không đồng nghĩa xóa bean repository bạn khai báo |
| Chạy lại tiến trình | Dữ liệu bộ nhớ từ lần chạy trước không còn | Không có lưu trữ bền vững |

Khi thử hai lần gọi, sửa phần kiểm chứng trong `main` để mong đợi hai bản ghi; nếu giữ kiểm tra `events.size() != 1`, chương trình sẽ chủ động báo lỗi. Khi thử tắt auditing, phần kiểm chứng hiện tại cũng sẽ báo `Expected one audit event, got 0`; đó là kết quả phù hợp với thí nghiệm.

Có thể truyền thuộc tính tắt auditing cho bản JAR sau khi đóng gói:

```shell
java -jar target/audit-publisher-demo-1.0.0.jar --management.auditevents.enabled=false
```

Nếu mong đợi có dữ liệu nhưng truy vấn không thấy, kiểm tra theo đường đi của bản ghi:

1. Bean phát có thực sự do Spring quản lý và phương thức phát có được gọi không?
2. Đối tượng phát có đúng là `AuditApplicationEvent` không?
3. Có bean `AuditEventRepository`, auditing có bị tắt và listener mặc định có bị thay thế không?
4. Bộ lọc `principal`, `type` và thời điểm truy vấn có khớp với bản ghi không?
5. Bạn đang đọc đúng tiến trình/instance đã ghi, và dữ liệu có bị loại do giới hạn dung lượng hoặc mất sau khởi động lại không?
6. Cơ chế xử lý có bị đổi sang bất đồng bộ, hoặc nơi lưu có báo lỗi không?

Để kiểm chứng ở các mức khác nhau, có thể kiểm tra riêng đối tượng sự kiện do service tạo, rồi kiểm tra tích hợp bằng cách khởi động context và đọc repository như ví dụ. Khi thay kho bộ nhớ bằng kho bền vững hoặc thêm giao dịch, bổ sung kiểm chứng cho commit, rollback, lỗi lưu và lần gửi lại theo yêu cầu thực tế.

## 9. Tự kiểm tra cách hiểu

**Vì sao đã gọi `publishEvent(...)` mà chưa thấy dữ liệu?** Bộ phát không tự tạo repository hay tự bảo đảm có listener lưu. Cũng cần kiểm tra kiểu sự kiện, cấu hình auditing, bộ lọc truy vấn và nơi lưu.

**Có bắt buộc dùng `ApplicationEventPublisherAware` không?** Không. Trong ví dụ, Spring cung cấp `ApplicationEventPublisher` qua tham số của phương thức `@Bean`, rồi truyền vào hàm khởi tạo service.

**Có cần Spring Security cho sự kiện nghiệp vụ trong ví dụ không?** Không. Người phát cung cấp danh tính; nếu ứng dụng có cơ chế xác thực, cần nối danh tính đã được xác minh vào dữ liệu kiểm toán.

**Bản ghi tồn tại trong bộ nhớ đã chứng minh đủ điều gì?** Nó chứng minh đường phát và nhận trong tiến trình đang chạy đã hoạt động. Nó chưa chứng minh dữ liệu tồn tại sau khởi động lại, đã được chia sẻ cho instance khác hoặc thao tác nghiệp vụ đã commit.

**Điểm quyết định khi thiết kế sự kiện là gì?** Tên sự kiện phải phản ánh đúng điều đã xảy ra tại thời điểm phát. Sau đó mới chọn dữ liệu, đường lưu và mức bảo đảm cần thiết để giữ được ý nghĩa đó.

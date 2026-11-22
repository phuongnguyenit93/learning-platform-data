# Phát event từ ApplicationContext

Trong Spring Framework, `ApplicationContext` vừa là container quản lý bean, vừa triển khai hợp đồng `ApplicationEventPublisher`. Vì vậy, khi đang có một application context, bạn có thể gọi trực tiếp `context.publishEvent(event)` để phát một sự kiện đến các listener phù hợp đã được đăng ký trong context.

Cách phát này hữu ích ở điểm khởi động ứng dụng, trong mã tích hợp đang quản lý context, hoặc khi cần hiểu luồng phân phối event của Spring. Trong service nghiệp vụ, thông thường nên inject `ApplicationEventPublisher` thay vì phụ thuộc vào toàn bộ `ApplicationContext`, vì service chỉ cần khả năng phát thông báo.

Sau bài học, bạn có thể:

- Giải thích quan hệ giữa `ApplicationContext` và `ApplicationEventPublisher`.
- Phát event trực tiếp bằng `context.publishEvent(...)`.
- Phân biệt event kế thừa `ApplicationEvent` với payload POJO hoặc record.
- Đăng ký listener bằng `@EventListener` và `ApplicationListener`.
- Mô tả vai trò của `ApplicationEventMulticaster` và phạm vi phân phối trong context cha/con.
- Nhận biết hành vi đồng bộ mặc định và giới hạn của application event.
- Viết chương trình Java 17 hoàn chỉnh để phát event từ `AnnotationConfigApplicationContext`.

## 1. ApplicationContext có thể phát event vì sao?

`ApplicationContext` là interface trung tâm của Spring container. Ngoài khả năng truy cập bean, message source, resource và environment, interface này còn mở rộng `ApplicationEventPublisher`. Do đó, mọi implementation của `ApplicationContext` đều cung cấp phương thức phát event.

Một số hợp đồng chính:

| Hợp đồng | Vai trò |
|---|---|
| `BeanFactory` và `ListableBeanFactory` | Truy cập, tra cứu và quản lý bean. |
| `MessageSource` | Phân giải message và hỗ trợ quốc tế hóa. |
| `ResourcePatternResolver` | Tìm và đọc tài nguyên theo cơ chế của Spring. |
| `EnvironmentCapable` | Truy cập profile và property sources. |
| `ApplicationEventPublisher` | Phát event đến listener phù hợp. |

Vì có `ApplicationEventPublisher`, có thể gọi:

~~~java
applicationContext.publishEvent(event);
~~~

`publishEvent` thông báo một sự kiện cho cơ chế event của Spring. Publisher không cần gọi tên từng listener, không cần biết có bao nhiêu listener và cũng không nhận một giá trị trả về tổng hợp từ các listener.

Ví dụ, sau khi báo cáo được tạo, ứng dụng phát `ReportGeneratedEvent`. Một listener có thể ghi audit, listener khác cập nhật metric và listener khác gửi thông báo. Publisher chỉ phát event; mỗi listener chịu trách nhiệm cho tác vụ của mình.

## 2. Phát event trực tiếp từ ApplicationContext

Có thể phát event tại nơi đang có context, ví dụ trong `main` sau khi context được khởi tạo:

~~~java
var context = new AnnotationConfigApplicationContext(AppConfig.class);
context.publishEvent(new ReportGeneratedEvent("RPT-1001"));
context.close();
~~~

Nên quản lý vòng đời context bằng try-with-resources khi có thể:

~~~java
try (var context =
         new AnnotationConfigApplicationContext(AppConfig.class)) {
    context.publishEvent(new ReportGeneratedEvent("RPT-1001"));
}
~~~

Constructor nhận lớp cấu hình của `AnnotationConfigApplicationContext` sẽ đăng ký cấu hình, khởi tạo context và thực hiện refresh. Sau khi context đã refresh, các listener bean được phát hiện trong quá trình khởi tạo có thể nhận event.

Gọi `context.publishEvent(...)` phù hợp khi mã khởi động hoặc mã tích hợp đang quản lý context, một thành phần hạ tầng có sẵn context, hoặc khi viết ví dụ và kiểm thử để minh họa cơ chế event. Không nên truyền `ApplicationContext` qua nhiều lớp nghiệp vụ chỉ để gọi `publishEvent`; dependency này rộng hơn nhu cầu thực tế.

## 3. ApplicationContext và ApplicationEventPublisher

Hai cách gọi sau đều dùng cùng hợp đồng phát event:

~~~java
applicationContext.publishEvent(event);
~~~

~~~java
applicationEventPublisher.publishEvent(event);
~~~

Trong service, hãy ưu tiên inject `ApplicationEventPublisher`:

~~~java
@Service
public class ReportService {

    private final ApplicationEventPublisher publisher;

    public ReportService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void generate(String reportId) {
        // Thực hiện công việc tạo báo cáo.
        publisher.publishEvent(new ReportGeneratedEvent(reportId));
    }
}
~~~

Cách này thể hiện chính xác dependency mà service cần, không cho service phụ thuộc vào toàn bộ API của container và dễ thay thế publisher bằng mock hoặc stub trong unit test.

Chỉ inject `ApplicationContext` khi lớp thật sự cần các khả năng khác như tra cứu bean, truy cập environment hoặc đọc resource. Nếu mục đích duy nhất là phát event, `ApplicationEventPublisher` là dependency phù hợp hơn.

## 4. Các dạng event mà publishEvent hỗ trợ

Spring hỗ trợ event kế thừa `ApplicationEvent` và cả object thông thường. API publisher có thể nhận một `ApplicationEvent` hoặc một object làm payload.

### Event kế thừa ApplicationEvent

Đây là cách truyền thống. Lớp event kế thừa `ApplicationEvent` và truyền source cho constructor:

~~~java
public final class LegacyReportGeneratedEvent extends ApplicationEvent {

    private final String reportId;

    public LegacyReportGeneratedEvent(Object source, String reportId) {
        super(source);
        this.reportId = reportId;
    }

    public String getReportId() {
        return reportId;
    }
}
~~~

Phát event:

~~~java
context.publishEvent(
    new LegacyReportGeneratedEvent(this, "RPT-1001")
);
~~~

`source` là đối tượng khởi phát event theo ý nghĩa của ứng dụng. Nó được lưu trong `ApplicationEvent` và có thể đọc bằng `getSource()`.

Listener có thể nhận event theo kiểu cụ thể:

~~~java
public class LegacyReportListener
        implements ApplicationListener<LegacyReportGeneratedEvent> {

    @Override
    public void onApplicationEvent(LegacyReportGeneratedEvent event) {
        System.out.println("Report: " + event.getReportId());
    }
}
~~~

### Phát POJO hoặc record

Với code mới, không bắt buộc event tùy chỉnh phải kế thừa `ApplicationEvent`. Có thể phát một POJO, class thông thường hoặc record:

~~~java
public record ReportGeneratedEvent(String reportId) {}
~~~

Phát event:

~~~java
context.publishEvent(new ReportGeneratedEvent("RPT-1001"));
~~~

Khi object phát ra không phải `ApplicationEvent`, Spring bọc nó trong `PayloadApplicationEvent` trước khi phân phối. Với `@EventListener`, method có thể khai báo trực tiếp kiểu payload:

~~~java
@EventListener
public void onReportGenerated(ReportGeneratedEvent event) {
    System.out.println(event.reportId());
}
~~~

Record thường gọn và giúp payload bất biến. Event nên chứa dữ liệu nghiệp vụ mà listener cần, chẳng hạn mã báo cáo, mã đơn hàng hoặc trạng thái đã hoàn tất. Không cần tạo một lớp kế thừa chỉ để đáp ứng cơ chế event nếu payload thông thường đã đủ.

| Trường hợp | Cách chọn |
|---|---|
| Code mới, payload đơn giản | POJO hoặc record thường là lựa chọn gọn. |
| Tương thích hệ thống cũ đã dùng event class | Tiếp tục dùng lớp kế thừa `ApplicationEvent`. |
| Cần giữ source của event theo hợp đồng cũ | Dùng `ApplicationEvent` và constructor có source. |
| Listener dùng `@EventListener` | Có thể nhận trực tiếp payload POJO hoặc event class. |
| Listener triển khai `ApplicationListener` | Dùng kiểu event phù hợp với hợp đồng listener. |

## 5. Đăng ký listener để nhận event

Phát event chỉ tạo ra thông báo trong context. Để xử lý thông báo, ứng dụng cần đăng ký listener dưới dạng Spring bean.

### Dùng @EventListener

Đánh dấu method trong một bean được Spring quản lý:

~~~java
@Component
public class ReportListener {

    @EventListener
    public void onReportGenerated(ReportGeneratedEvent event) {
        System.out.println("Report generated: " + event.reportId());
    }
}
~~~

Method có thể nhận payload POJO hoặc event kế thừa `ApplicationEvent`. Bean phải được đăng ký qua component scanning hoặc một phương thức `@Bean`; một object được tạo bằng `new` bên ngoài container sẽ không tự động được Spring phát hiện method listener.

Một bean có thể có nhiều method `@EventListener`. Nhiều bean cũng có thể lắng nghe cùng một kiểu event. Spring chọn các listener phù hợp dựa trên kiểu event và điều kiện đã khai báo.

Có thể dùng điều kiện SpEL khi một listener chỉ xử lý một nhóm payload nhất định:

~~~java
@Component
public class FinancialReportListener {

    @EventListener(condition = "#a0.reportId().startsWith('FIN-')")
    public void onFinancialReport(ReportGeneratedEvent event) {
        System.out.println("Financial report: " + event.reportId());
    }
}
~~~

`#a0` tham chiếu tham số đầu tiên của method. Điều kiện nên ngắn và dễ đọc. Nếu cần truy vấn dữ liệu hoặc logic phức tạp, hãy chuyển phần đó sang service được listener gọi.

### Dùng ApplicationListener

Có thể triển khai interface listener:

~~~java
public class ReportListener
        implements ApplicationListener<LegacyReportGeneratedEvent> {

    @Override
    public void onApplicationEvent(LegacyReportGeneratedEvent event) {
        System.out.println("Report: " + event.getReportId());
    }
}
~~~

Đăng ký implementation này thành bean:

~~~java
@Configuration
class EventConfiguration {

    @Bean
    ReportListener reportListener() {
        return new ReportListener();
    }
}
~~~

`ApplicationListener<E>` phù hợp khi muốn biểu diễn listener như một bean triển khai hợp đồng chuyên biệt. `@EventListener` thường thuận tiện hơn khi một bean có nhiều method xử lý hoặc muốn nhận trực tiếp payload POJO.

## 6. Cơ chế phân phối bên trong ApplicationContext

Khi gọi `context.publishEvent(event)`, application context chuyển event đến `ApplicationEventMulticaster` của context. Multicaster tìm các listener tương thích rồi điều phối việc gọi chúng.

~~~mermaid
flowchart TD
    A["ApplicationContext.publishEvent(event)"] --> B["Chuẩn hóa event"]
    B --> C["ApplicationEventMulticaster"]
    C --> D["Tìm listener tương thích"]
    D --> E["Listener A"]
    D --> F["Listener B"]
    E --> G["Hoàn tất phân phối cục bộ"]
    F --> G
    G --> H["Chuyển tiếp lên parent context nếu có"]
~~~

Các thành phần chính:

- `ApplicationContext`: cung cấp điểm phát event và quản lý bean listener.
- `ApplicationEventMulticaster`: điều phối phân phối event.
- `SimpleApplicationEventMulticaster`: implementation mặc định thường được dùng khi ứng dụng không khai báo multicaster riêng.
- `ApplicationListener` hoặc method `@EventListener`: xử lý event được chọn.

Spring phát hiện các listener bean trong quá trình khởi tạo context. Với method `@EventListener`, hạ tầng annotation của Spring tìm method được đánh dấu và đăng ký adapter tương ứng với multicaster.

Multicaster không phải event log. Nó phân phối event tại thời điểm phát; nó không tự lưu lịch sử để listener đăng ký sau có thể đọc lại các event cũ.

## 7. Phạm vi event trong context cha và context con

Một ứng dụng có thể có nhiều `ApplicationContext` theo cấu trúc phân cấp. Context con có thể tham chiếu một parent context.

Khi event được phát từ context con, event được phân phối trong context con và được chuyển tiếp lên context cha. Do đó, listener ở parent có thể nhận event từ child nếu kiểu event phù hợp.

Chiều ngược lại không tự động xảy ra: event phát ở parent không được phân phối xuống các child context.

~~~text
Parent ApplicationContext
    ├── ParentListener
    └── Child ApplicationContext
          ├── ChildListener
          └── ChildService
~~~

Nếu `ChildService` phát event từ child context, `ChildListener` có thể nhận event tại child và `ParentListener` có thể nhận event được chuyển tiếp lên parent. Listener trong một context độc lập khác không tự động nhận event.

Việc chuyển tiếp lên parent không phải broadcast đến mọi context trong tiến trình. Nếu ứng dụng có nhiều context độc lập, mỗi context có phạm vi listener riêng.

## 8. Event vòng đời do Spring phát

Ngoài event do ứng dụng tự định nghĩa, Spring còn phát một số event phản ánh vòng đời của application context.

| Event | Ý nghĩa |
|---|---|
| `ContextRefreshedEvent` | Context đã hoàn tất quá trình refresh. |
| `ContextStartedEvent` | Context được yêu cầu start thông qua lifecycle API. |
| `ContextStoppedEvent` | Context được yêu cầu stop. |
| `ContextClosedEvent` | Context đang được đóng. |

Có thể lắng nghe event refresh và close:

~~~java
@Component
public class ContextLifecycleListener {

    @EventListener
    public void onRefresh(ContextRefreshedEvent event) {
        System.out.println("Context refreshed");
    }

    @EventListener
    public void onClosed(ContextClosedEvent event) {
        System.out.println("Context is closing");
    }
}
~~~

Các event vòng đời hữu ích khi cần phản ứng với trạng thái container. Tuy nhiên, nếu nhu cầu thực tế là quản lý vòng đời của một bean, hãy cân nhắc callback chuyên biệt như `@PostConstruct`, `SmartLifecycle` hoặc `DisposableBean` thay vì dùng event tổng quát.

## 9. Đồng bộ, bất đồng bộ và thứ tự xử lý

Với `SimpleApplicationEventMulticaster` mặc định và không cấu hình executor, listener chạy đồng bộ trên thread gọi `publishEvent`. Publisher chờ listener hoàn tất trước khi chạy câu lệnh tiếp theo.

Hệ quả:

- Listener chạy lâu làm tăng thời gian xử lý của publisher.
- Exception từ listener đồng bộ có thể truyền về nơi gọi `publishEvent`.
- Các listener được gọi trong cùng lượt phân phối có thể bị ảnh hưởng nếu một listener ném exception và không có `ErrorHandler` xử lý.
- Publisher không nhận một kết quả tổng hợp từ tất cả listener.

Có thể dùng `@Order` để khai báo mức ưu tiên gọi listener khi cần một thứ tự cụ thể. Giá trị order nhỏ hơn được ưu tiên trước. Không nên dựa vào thứ tự đăng ký bean hoặc thứ tự method trong source code nếu chưa khai báo hợp đồng thứ tự.

Có thể dùng `@Async` cùng `@EnableAsync` hoặc cấu hình executor cho multicaster để chuyển việc xử lý sang thread do executor quản lý. Khi đó publisher có thể tiếp tục trước khi listener hoàn tất. Cần cấu hình riêng cho executor, exception, transaction, retry và quan sát completion.

Nếu một listener phải chạy sau khi transaction commit, dùng `@TransactionalEventListener` với phase phù hợp, thường là `TransactionPhase.AFTER_COMMIT`. Application event không tự cung cấp hàng đợi bền vững hay cơ chế retry sau sự cố tiến trình.

## 10. Ví dụ hoàn chỉnh: phát event trực tiếp từ ApplicationContext

Ví dụ dùng Java 17 và Spring Context 6.2.0. Chương trình tạo một `AnnotationConfigApplicationContext`, đăng ký listener bằng `@Bean`, phát record event trực tiếp từ context rồi đóng context.

Cấu trúc thư mục:

~~~text
application-context-event-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationContextEventDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>application-context-event-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ApplicationContextEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/ApplicationContextEventDemo.java

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class ApplicationContextEventDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            context.publishEvent(
                new ReportGeneratedEvent("RPT-1001")
            );

            System.out.println("ApplicationContext.publishEvent returned");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean
        ReportListener reportListener() {
            return new ReportListener();
        }
    }

    record ReportGeneratedEvent(String reportId) {}

    static class ReportListener {

        @EventListener
        public void onReportGenerated(ReportGeneratedEvent event) {
            System.out.println(
                "Listener received report: " + event.reportId()
            );
        }
    }
}
~~~

Chạy tại thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Kết quả stdout với multicaster đồng bộ mặc định:

~~~text
Listener received report: RPT-1001
ApplicationContext.publishEvent returned
~~~

Listener được Spring đăng ký từ bean `ReportListener`. Khi gọi `context.publishEvent`, Spring bọc record trong `PayloadApplicationEvent` rồi phân phối đến method có tham số `ReportGeneratedEvent`. Listener chạy đồng bộ nên dòng thông báo từ listener xuất hiện trước dòng tiếp theo trong `main`.

## 11. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ ApplicationContext không thể phát event | Bỏ qua API có sẵn của context. | Nhớ rằng `ApplicationContext` triển khai `ApplicationEventPublisher`. |
| Truyền ApplicationContext vào mọi service | Service phụ thuộc nhiều chức năng container không cần thiết. | Inject `ApplicationEventPublisher` nếu chỉ phát event. |
| Listener không phải Spring bean | Method `@EventListener` không được đăng ký. | Đăng ký bằng `@Bean` hoặc component scanning. |
| Event payload không khớp tham số listener | Listener không được chọn để nhận event. | Kiểm tra kiểu event và kiểu tham số listener. |
| Cho rằng phát event sẽ lưu lịch sử | Listener đăng ký sau không nhận lại event cũ. | Dùng persistence hoặc message broker nếu cần replay. |
| Cho rằng event lan đến mọi context | Context độc lập hoặc child không nhận event theo cách mong đợi. | Hiểu rõ phạm vi context và chiều chuyển tiếp lên parent. |
| Cho rằng publishEvent luôn chạy async | Listener mặc định có thể chặn thread phát event. | Cấu hình async khi nghiệp vụ cho phép. |
| Cho rằng publishEvent xác nhận mọi listener thành công | Publisher không nhận kết quả nghiệp vụ tổng hợp. | Thiết kế logging, giám sát và xử lý lỗi riêng. |
| Dùng application event để giao tiếp giữa nhiều tiến trình | Event chỉ hoạt động trong cơ chế context của ứng dụng. | Dùng message broker hoặc API liên tiến trình. |
| Không quản lý vòng đời context | Resource hoặc thread liên quan có thể không được đóng đúng cách. | Đóng context bằng lifecycle phù hợp hoặc try-with-resources. |

## 12. Checklist khi phát event từ ApplicationContext

Trước khi triển khai, hãy kiểm tra:

1. Đoạn mã phát event có thật sự cần `ApplicationContext` hay chỉ cần `ApplicationEventPublisher`?
2. Event có payload rõ ràng, ổn định và đủ dữ liệu cho listener không?
3. Listener đã được đăng ký thành bean trong context phù hợp chưa?
4. Kiểu event và tham số listener có tương thích không?
5. Listener cần chạy đồng bộ hay bất đồng bộ?
6. Có yêu cầu thứ tự listener hoặc chính sách xử lý exception không?
7. Event có cần chờ transaction commit không?
8. Có context cha/con và phạm vi phân phối nào cần lưu ý không?
9. Có yêu cầu lưu trữ, retry hoặc phát lại event không?
10. Context có được đóng đúng vòng đời không?

`ApplicationContext` phát event thông qua hợp đồng `ApplicationEventPublisher`. Context nhận event, chuẩn hóa payload khi cần, rồi giao cho `ApplicationEventMulticaster` phân phối đến listener phù hợp. Dùng `context.publishEvent(...)` ở nơi cần thao tác trực tiếp với context; trong service nghiệp vụ, inject `ApplicationEventPublisher` để giữ dependency gọn. Hiểu rõ payload, listener, phạm vi context và execution model giúp event được phát và xử lý đúng với vòng đời ứng dụng.

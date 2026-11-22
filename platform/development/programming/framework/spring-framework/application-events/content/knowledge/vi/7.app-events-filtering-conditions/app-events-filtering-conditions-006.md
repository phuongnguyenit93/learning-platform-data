# Điều kiện động theo environment trong Spring Application Events

## 1. Bài toán và mô hình tư duy

Một ứng dụng phát sự kiện `OrderPlaced` mỗi khi đơn hàng được tạo. Bộ xử lý kiểm toán chỉ cần hoạt động khi cấu hình `events.audit.enabled=true`; có thể còn cần giới hạn theo vùng `VN`. Khi tắt cờ, ứng dụng vẫn phải phát sự kiện và các listener khác vẫn được xử lý bình thường. Điều ta cần là **điều kiện cho một listener**, không phải hủy sự kiện trên toàn hệ thống.

Trong Spring Framework, `Environment` cung cấp hai nhóm thông tin: **profiles** (ví dụ `dev`, `staging`, `prod`) và **properties** (ví dụ `events.audit.enabled`). Từ “động” có hai nghĩa cần tách rõ:

- **Chọn lúc tạo `ApplicationContext`:** Spring xem profile/property để quyết định có đăng ký bean listener hay không. Sau khi context đã khởi tạo, thay đổi cấu hình không tự tạo lại bean.
- **Chọn mỗi lần nhận event:** listener đã được đăng ký; mỗi sự kiện đến sẽ được kiểm tra theo giá trị cấu hình ở thời điểm xử lý. Khi nguồn cấu hình thực sự thay đổi và có thể được đọc lại, sự kiện sau có thể cho kết quả khác mà không cần dựng lại listener.

Luồng xử lý thường là: `publishEvent(event)` → Spring tìm listener tương thích kiểu event → kiểm tra `condition` nếu có → gọi phương thức listener khi điều kiện đúng. Điều kiện trả về `false` chỉ bỏ qua **phương thức listener đó**; các listener khác vẫn có thể chạy.

## 2. Ba cơ chế dễ nhầm lẫn

| Cơ chế | Thời điểm quyết định | Dùng cho trường hợp |
| --- | --- | --- |
| `@Profile("prod")` trên lớp hoặc bean | Lúc đăng ký bean khi context được khởi tạo | Chỉ có listener trong một môi trường triển khai |
| `@ConditionalOnProperty` (Spring Boot) | Lúc xử lý cấu hình/đăng ký bean | Bật hoặc tắt toàn bộ bean theo property khởi động |
| `@EventListener(condition = "...")` | Mỗi lần Spring xét event cho listener đã đăng ký | Lọc event theo payload, cờ tính năng hoặc chính sách đọc được khi chạy |
| `@EventListener` kèm `if` trong thân hàm | Mỗi lần phương thức listener được gọi | Điều kiện phức tạp, cần debug rõ hoặc phụ thuộc nhiều dịch vụ |

`@Profile` thuộc Spring Framework. `@ConditionalOnProperty` thuộc **Spring Boot**, không có sẵn nếu dự án chỉ phụ thuộc `spring-context`. Cả hai thường quyết định việc **có bean hay không** lúc khởi tạo, không làm listener tự xuất hiện hoặc biến mất khi đổi property sau `refresh()`.

Ví dụ cấu hình theo profile:

~~~java
@Component
@Profile("prod")
public class ProductionAuditListener {
    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        // Chỉ có bean listener này khi profile prod phù hợp lúc khởi tạo.
    }
}
~~~

Mã này chỉ minh họa annotation và cần kiểu `OrderPlaced`, các import tương ứng, cấu hình quét component để hoạt động. Nếu listener phải được giữ nguyên trong context nhưng bật/tắt theo từng lần phát sự kiện, hãy dùng cơ chế ở phần tiếp theo.

## 3. Viết điều kiện SpEL cho `@EventListener`

Thuộc tính `condition` nhận biểu thức Spring Expression Language (SpEL). Spring đánh giá biểu thức khi xét một sự kiện; giá trị Boolean `true` làm phương thức được gọi, `false` làm phương thức bị bỏ qua. Có thể lấy dữ liệu qua `#root.args`, `#a0` hoặc `#p0` (tham số đầu tiên), và qua tên tham số nếu thông tin tên có sẵn khi biên dịch.

~~~java
@EventListener(condition = "#a0.region() == 'VN'")
public void handle(OrderPlaced event) {
    // Chỉ xử lý event có region bằng VN.
}
~~~

Với một Java `record OrderPlaced(String id, String region)`, `region()` là phương thức truy cập của record. Dùng `#a0` giúp biểu thức không phụ thuộc tên biến tham số trong bytecode.

Để điều kiện phụ thuộc cấu hình, nên đưa logic đọc cấu hình vào một bean có tên rõ ràng, rồi gọi bean đó từ SpEL:

~~~java
@EventListener(
    condition = "@auditSwitch.enabled() and #a0.region() == 'VN'"
)
public void handle(OrderPlaced event) {
    // Chạy khi cờ hiện tại bật và đơn hàng thuộc vùng VN.
}
~~~

Ký hiệu `@auditSwitch` tham chiếu bean tên `auditSwitch` trong context. Toán tử `and` dùng phép AND logic; nếu cờ tắt, nhánh kiểm tra vùng không cần đánh giá. Dùng bean cho phép kiểm thử và tập trung chính sách đọc property; tránh nhúng chuỗi tên property, chuyển kiểu và quy tắc mặc định khắp các listener.

**Điểm quyết định:** biểu thức được xét mỗi lần có sự kiện phù hợp, nhưng giá trị mà nó thấy chỉ “động” nếu `auditSwitch.enabled()` thực sự đọc một nguồn được cập nhật. Việc sửa một file YAML trên đĩa hoặc đổi biến môi trường của máy chủ không mặc nhiên làm `Environment` đang chạy được tải lại.

## 4. Ví dụ chạy được: đổi cờ giữa các sự kiện

Ví dụ này chỉ dùng Spring Framework, không yêu cầu Spring Boot. Chương trình tạo một `MapPropertySource` có bản đồ cấu hình có thể chỉnh sửa, phát bốn event liên tiếp, rồi kiểm tra listener có chạy theo **giá trị cờ lúc mỗi event được phát** hay không.

Cấu trúc thư mục:

~~~text
demo/
├── pom.xml
└── src/main/java/DynamicEnvironmentEventsDemo.java
~~~

`pom.xml` (Java 17+, Spring Context 6.2.0):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>dynamic-environment-events-demo</artifactId>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>DynamicEnvironmentEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/DynamicEnvironmentEventsDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

public final class DynamicEnvironmentEventsDemo {

    // Một đối tượng dữ liệu thông thường cũng có thể được publish làm event.
    public record OrderPlaced(String id, String region) { }

    public static final class AuditSwitch {
        private final Environment environment;

        public AuditSwitch(Environment environment) {
            this.environment = environment;
        }

        public boolean enabled() {
            // Thiếu hoặc không hợp lệ theo bộ chuyển kiểu => cần xử lý phù hợp;
            // trong ví dụ, property "true"/"false" hợp lệ và mặc định là false.
            return environment.getProperty(
                "events.audit.enabled", Boolean.class, false
            );
        }
    }

    public static final class AuditListener {
        @EventListener(
            condition = "@auditSwitch.enabled() and #a0.region() == 'VN'"
        )
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println("AUDIT " + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean("auditSwitch")
        AuditSwitch auditSwitch(Environment environment) {
            return new AuditSwitch(environment);
        }

        @Bean
        AuditListener auditListener() {
            return new AuditListener();
        }
    }

    private static void publish(
        AnnotationConfigApplicationContext context,
        String id,
        String region
    ) {
        System.out.println("PUBLISH " + id + " " + region);
        context.publishEvent(new OrderPlaced(id, region));
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

            Map<String, Object> flags = new HashMap<>();
            flags.put("events.audit.enabled", "false");

            context.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource("demoFlags", flags)
            );
            context.register(AppConfig.class);
            context.refresh();

            publish(context, "A-001", "VN");   // flag false: không audit

            flags.put("events.audit.enabled", "true");
            publish(context, "A-002", "VN");   // flag true, VN: audit
            publish(context, "A-003", "US");   // flag true, US: bỏ qua

            flags.put("events.audit.enabled", "false");
            publish(context, "A-004", "VN");   // flag false: bỏ qua
        }
    }
}
~~~

Tại thư mục `demo/`, chạy bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java
~~~

Các dòng chương trình tự in ra `stdout`, theo đúng thứ tự:

~~~text
PUBLISH A-001 VN
PUBLISH A-002 VN
AUDIT A-002
PUBLISH A-003 US
PUBLISH A-004 VN
~~~

Giải thích: Khi nhận `A-001`, Spring bỏ qua `AuditListener` vì cờ là `false`. Ta sửa giá trị trong bản đồ nguồn và phát `A-002`; `AuditSwitch` đọc lại `Environment`, trả về `true`, đồng thời `region()` là `VN` nên in `AUDIT A-002`. `A-003` bị lọc theo vùng. `A-004` bị lọc do cờ đã tắt. Không có lần nào phải đăng ký lại listener.

**Vì sao ví dụ có thể thay đổi ngay?** `MapPropertySource` được tạo từ cùng đối tượng `flags`. Ở đây các thay đổi xảy ra tuần tự trên một luồng, và lần đọc property tiếp theo nhìn thấy giá trị mới. Đây là cách minh họa hành vi đánh giá lúc xử lý; trong ứng dụng nhiều luồng, không dùng `HashMap` sửa chung theo cách này làm kho cấu hình động. Chọn nguồn cấu hình có cơ chế cập nhật và an toàn luồng rõ ràng.

## 5. Cách dùng `Environment` trong listener khi điều kiện phức tạp

Có thể không dùng SpEL cho toàn bộ chính sách. Listener được gọi rồi tự quyết định có tiếp tục hay không:

~~~java
@Component
public class BillingEventListener {
    private final Environment environment;

    public BillingEventListener(Environment environment) {
        this.environment = environment;
    }

    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        boolean enabled = environment.getProperty(
            "events.billing.enabled", Boolean.class, false
        );
        if (!enabled || !"VN".equals(event.region())) {
            return;
        }
        // Xử lý nghiệp vụ: gửi yêu cầu thanh toán, ghi nhật ký...
    }
}
~~~

Đoạn này minh họa một bean trong dự án có sẵn `OrderPlaced`; cần import `Component`, `EventListener`, `Environment`. Spring vẫn gọi `onOrderPlaced` cho mỗi `OrderPlaced`, còn câu lệnh `return` bỏ qua phần nghiệp vụ. Cách này hợp khi chính sách có nhiều nhánh, cần ghi log lý do bỏ qua, hoặc muốn dùng service thay vì viết biểu thức dài.

Nếu muốn gọn hơn mà vẫn lọc trước lời gọi phương thức, tạo một service chính sách với phương thức `allows(OrderPlaced)` và tham chiếu từ SpEL:

~~~java
@EventListener(condition = "@orderEventPolicy.allows(#a0)")
public void onOrderPlaced(OrderPlaced event) {
    // Logic nghiệp vụ
}
~~~

`orderEventPolicy` phải là bean thực sự có tên này và phương thức `allows` truy cập được. Như vậy biểu thức chỉ điều phối; service giữ việc đọc property, kiểm tra vùng, tenant hoặc quy tắc cấu hình.

## 6. Profile, property và thay đổi lúc runtime

### Profile dành cho cấu hình triển khai

Đặt `@Profile("prod")` lên lớp listener khi **môi trường nào cần có bean** là một quyết định trong giai đoạn khởi tạo. Có thể bật profile bằng cấu hình của ứng dụng trước khi context khởi động. Thay `spring.profiles.active` sau khi context đã `refresh()` không khiến Spring tự quét, tạo hoặc hủy các listener theo profile mới.

### Property dành cho công tắc tính năng

Trong Spring Boot, `@ConditionalOnProperty(prefix = "events.audit", name = "enabled", havingValue = "true")` có thể quyết định tạo bean ở giai đoạn cấu hình. Điều này khác với điều kiện `@EventListener`: điều kiện Boot đó **không tự kích hoạt lại** khi property đổi trong lúc chạy. Với việc cần bật/tắt theo event, giữ listener trong context và đọc cờ ở đường xử lý event.

### Nguồn cấu hình thực sự thay đổi như thế nào?

`Environment` tìm giá trị qua các `PropertySource` theo thứ tự ưu tiên. Với một file cấu hình hoặc biến môi trường đã được đọc vào context, Spring Framework không mặc định theo dõi thay đổi rồi phát thông báo làm mới. Tùy nhu cầu, dùng một nguồn giá trị có cập nhật được, một dịch vụ feature flag, cơ chế refresh được thiết kế riêng hoặc tải lại context có kiểm soát. Kiểm tra cả **độ mới của giá trị**, **thứ tự ưu tiên nguồn** và **an toàn luồng**.

Không nên gọi `System.getenv()` trong listener rồi cho rằng thay đổi biến môi trường bên ngoài sẽ tức thì hiện vào tiến trình Java đang chạy. Biến môi trường tiến trình và hệ thống cấu hình động là hai khái niệm khác nhau.

## 7. Quy tắc thiết kế và những lỗi hay gặp

1. **Phân biệt điều kiện đăng ký với điều kiện xử lý:** `@Profile`/`@ConditionalOnProperty` dùng cho việc tạo bean; `@EventListener(condition = ...)` dùng cho từng event. Nếu listener không được đăng ký, mọi biểu thức lọc của nó đều không được xét.
2. **Chọn giá trị mặc định an toàn:** với chức năng tùy chọn như audit bổ sung, có thể dùng `false` khi thiếu property. Với tác vụ nghiệp vụ bắt buộc, không được âm thầm bỏ xử lý chỉ vì cấu hình thiếu; cần báo lỗi cấu hình hoặc thiết kế cơ chế bền vững.
3. **Dùng kiểu Boolean khi đọc cấu hình:** `getProperty(key, Boolean.class, false)` làm ý định rõ hơn việc tự so sánh một loạt chuỗi. Property có giá trị không thể chuyển kiểu có thể phát sinh lỗi chuyển đổi; hãy kiểm tra cấu hình đầu vào.
4. **Tránh SpEL quá phức tạp:** biểu thức dài, gọi dịch vụ mạng hoặc truy cập cơ sở dữ liệu trong `condition` làm khó quan sát và có thể gây lỗi, chậm đường phát sự kiện. Đưa chính sách vào bean/service, thêm cache phù hợp và kiểm thử riêng.
5. **Biết sự kiện đang chạy đồng bộ hay bất đồng bộ:** với multicaster mặc định không gắn executor riêng, listener thông thường chạy đồng bộ trong luồng phát. Nếu dùng `@Async` hoặc executor cho multicaster, thời điểm thật sự đánh giá cờ có thể muộn hơn thời điểm gọi `publishEvent`; tránh kỳ vọng một ảnh chụp cấu hình “đúng lúc phát” nếu không truyền snapshot vào event.
6. **Đừng dùng điều kiện làm ranh giới bảo mật:** sự kiện vẫn được publish cho context và listener khác. Lọc `@EventListener` không thay cho kiểm tra quyền, kiểm tra tenant, hoặc đảm bảo chỉ một bên thấy dữ liệu.
7. **Không nhầm event nội bộ với hàng đợi bền vững:** `ApplicationEventPublisher` của Spring Framework không tự lưu lại event bị bỏ qua và không tự chuyển event giữa các tiến trình. Nếu cần retry, delivery guarantee hoặc replay, phải thiết kế lưu trữ/nhắn tin riêng.
8. **Thử cả chuyển trạng thái bật → tắt → bật:** đừng chỉ kiểm tra một cấu hình ban đầu; hãy phát event sau mỗi lần nguồn cấu hình được cập nhật, gồm cả trường hợp payload không khớp và thiếu property.

Bảng chọn nhanh:

| Nhu cầu | Giải pháp nên bắt đầu |
| --- | --- |
| Listener chỉ tồn tại trong `prod` | `@Profile("prod")` |
| Bean chỉ được tạo khi cờ lúc startup bật, có dùng Spring Boot | `@ConditionalOnProperty` |
| Listener tồn tại nhưng bật/tắt theo cờ cập nhật tại runtime | `@EventListener(condition = "@namedPolicy.allowed(#a0)")` |
| Cần ghi log chi tiết lý do bỏ qua và xử lý nhiều nhánh | Inject `Environment`/policy service rồi `if (...) return` trong listener |
| Cần chốt chính sách tại thời điểm phát dù xử lý bất đồng bộ | Đưa snapshot quyết định hoặc dữ liệu cấu hình cần thiết vào event |

## 8. Bài tập tự kiểm tra

1. Giữ `events.audit.enabled=false` và phát ba `OrderPlaced` khác nhau. Vì sao listener audit không in gì dù `publishEvent` vẫn chạy?
2. Đổi flag từ `false` sang `true` trong `MapPropertySource` đang được đọc, rồi phát lại event `VN`. Đâu là điều kiện làm thay đổi kết quả: đánh giá lại SpEL hay tự đăng ký lại bean?
3. Chuyển `@EventListener(condition = ...)` thành `@Profile("prod")` và thử đổi active profile sau `refresh()`. Vì sao đây không phải thay thế tương đương?
4. Nếu sự kiện được xử lý bất đồng bộ, làm thế nào để quy tắc “dùng cờ tại thời điểm phát” vẫn xác định được? Gợi ý: quyết định hoặc chụp giá trị cấu hình tại thời điểm phát và đưa thông tin đó vào payload.

**Tự đối chiếu:** (1) cờ chặn riêng lời gọi listener; (2) SpEL đánh giá lại và policy đọc giá trị mới; (3) profile tác động tới đăng ký bean trong quá trình dựng context; (4) truyền quyết định/snapshot bất biến theo event thay vì đọc một cờ có thể đổi muộn hơn.

## Tài liệu tham khảo

- Spring Framework Reference, *Application Events / Annotation-based Event Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference, *Environment Abstraction / Profiles / PropertySource*: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- Spring Framework API, *EventListener.condition*: https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListener.html

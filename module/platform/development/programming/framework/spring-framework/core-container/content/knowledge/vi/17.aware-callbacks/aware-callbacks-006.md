# Đánh đổi giữa tiện ích container và mức độ phụ thuộc vào Spring

## 1. Câu hỏi thiết kế: tiện lợi đến đâu là hợp lý?

Spring Core Container cho phép bean khai thác nhiều tiện ích ngoài việc nhận collaborator thông thường: biết tên bean qua `BeanNameAware`, truy cập bean registry qua `BeanFactoryAware`, nhận `ApplicationContext` qua `ApplicationContextAware`, lấy dependency theo nhu cầu, phát event, đọc resource hay truy cập thông tin scope. Khả năng đó rất hữu ích khi xây dựng **hạ tầng/framework adapter**.

Đánh đổi nằm ở chỗ **đối tượng nghiệp vụ càng hiểu nhiều về container, nó càng phụ thuộc vào Spring và cấu hình Spring**. Một lớp tự gọi `applicationContext.getBean(PaymentGateway.class)` có thể thực hiện công việc thành công hôm nay, nhưng dependency `PaymentGateway` không còn hiện rõ trong constructor; unit test thuần Java phải dựng/mô phỏng context hoặc giả lập thao tác lookup; khi scope hoặc cấu hình thay đổi, lỗi có thể xuất hiện vào lúc chạy.

Nguyên tắc thực hành:

> Hãy để Spring *kết nối* các thành phần; để các thành phần nghiệp vụ diễn đạt rõ chúng *cần* gì. Chỉ để một bean biết về container khi chính vai trò của nó thực sự cần thông tin hoặc hành vi container.

Không phải tất cả Spring coupling đều xấu. Một `BeanPostProcessor`, một framework integration adapter hay một component cần đăng ký handler theo tên bean có thể hợp lý khi implement `Aware`. Nhưng một `OrderCalculator` chỉ cộng tiền, áp dụng chính sách giảm giá và gọi `TaxService` thì thông thường nên nhận các collaborator qua constructor.

### Ba lớp phụ thuộc cần phân biệt

1. **Phụ thuộc nghiệp vụ**: `CheckoutService` cần `PaymentGateway`. Đó là quan hệ nghiệp vụ phải tồn tại dù dùng Spring hay framework khác.
2. **Phụ thuộc vào abstraction/framework type**: class dùng `ApplicationEventPublisher`, `ResourceLoader` hoặc `ObjectProvider`. Spring API hiện diện, nhưng bề mặt phụ thuộc có thể hẹp.
3. **Phụ thuộc vào toàn bộ container**: class implement `ApplicationContextAware` và lưu `ApplicationContext` để lookup tùy ý nhiều bean. Đây là mức quyền truy cập rộng nhất, cần lý do cụ thể.

Không nên đánh giá bằng số lượng annotation đơn thuần: một lớp sử dụng `@Component` chỉ ở lớp adapter cấu hình vẫn có thể có nghiệp vụ thuần Java; ngược lại, một lớp không gắn annotation nhưng tự lưu `ApplicationContext` đã phụ thuộc sâu vào Spring API.

## 2. IoC/DI và cách phụ thuộc dịch chuyển

**Inversion of Control (IoC)** nghĩa là container chịu trách nhiệm tạo và kết nối đối tượng, thay vì mỗi đối tượng tự điều khiển toàn bộ quá trình tạo collaborator. **Dependency Injection (DI)** là một cách thực hiện IoC: dependency được đưa vào qua constructor, setter hoặc injection point khác.

So sánh hai thiết kế:

~~~text
A. Service chủ động tìm dependency

CheckoutService ── getBean() ──► ApplicationContext
                                    │
                                    ▼
                               PaymentGateway

B. Dependency được cung cấp cho service

Composition root (Spring @Configuration)
     │
     ├── tạo PaymentGateway
     │
     └── tạo CheckoutService(PaymentGateway)
                │
                ▼
           PaymentGateway
~~~

Trong mô hình A, việc Spring cấp `ApplicationContext` vào service vẫn là một dạng injection, nhưng **service tự tìm collaborator thực tế** nên phụ thuộc nghiệp vụ bị che giấu: constructor chỉ nói cần container. Trong mô hình B, hợp đồng của `CheckoutService` nói rõ cần `PaymentGateway`.

Mô hình B thường dễ:

- Đọc code: ai cũng thấy collaborator trong constructor.
- Test: `new CheckoutService(fakeGateway)` hoạt động ngoài Spring.
- Thay triển khai: ứng dụng chỉ thay binding của `PaymentGateway` tại composition root.
- Kiểm soát vòng đời: scope của gateway được giải quyết khi Spring tạo hoặc cung cấp dependency.
- Phát hiện lỗi sớm: thiếu dependency bắt buộc thường lộ ngay khi container tạo service thay vì khi một nhánh business method lần đầu chạy.

Mô hình A có điểm mạnh thật sự: **lookup động khi runtime**, chọn bean dựa trên metadata/container state, hỗ trợ một adapter kết nối với plugin architecture hoặc bean definition. Nhưng nếu dùng để thay mọi constructor injection, code sẽ trở thành một dạng **Service Locator**: dependency lan qua các chuỗi lookup và khó quản lý.

## 3. Tiện ích của ba Aware interface và chi phí đi kèm

### 3.1. `BeanNameAware` — biết danh tính trong container

Spring gọi `setBeanName(String beanName)` khi một bean implement `BeanNameAware`. Bean có thể dùng tên đăng ký thực tế để phục vụ logging, metadata hoặc registry hạ tầng.

~~~java
public final class NamedListener
        implements org.springframework.beans.factory.BeanNameAware {

    private String beanName;

    @Override
    public void setBeanName(String beanName) {
        this.beanName = beanName;
    }

    public String diagnosticName() {
        return beanName;
    }
}
~~~

**Tiện ích:** tự động lấy tên thực tế, kể cả khi được đăng ký qua `@Bean(name = "...")` hoặc bean name generator riêng.

**Chi phí:** lớp biết trực tiếp API Spring; phải được Spring quản lý và đi qua callback mới có field hợp lệ. Tên bean là **metadata triển khai**, không nhất thiết là mã nghiệp vụ ổn định. Refactor tên bean có thể thay đầu ra hoặc behavior nếu code dùng name làm khóa.

Nếu một service chỉ cần “kênh xử lý đơn hàng” hay “mã tenant”, thường truyền chúng thành dữ liệu constructor rõ ràng:

~~~java
public final class ChannelProcessor {
    private final String channel;

    public ChannelProcessor(String channel) {
        this.channel = channel;
    }

    public String channel() {
        return channel;
    }
}
~~~

Mẫu thứ hai không phụ thuộc Spring. Còn nếu hạ tầng thật sự cần bean name để quản lý registry, `BeanNameAware` là hợp lý.

### 3.2. `BeanFactoryAware` — giữ quyền truy cập bean lookup

Bean implement `BeanFactoryAware` nhận `BeanFactory` hiện quản lý nó qua `setBeanFactory(BeanFactory)`.

~~~java
public class DynamicConverterAdapter
        implements org.springframework.beans.factory.BeanFactoryAware {

    private org.springframework.beans.factory.BeanFactory beanFactory;

    @Override
    public void setBeanFactory(
            org.springframework.beans.factory.BeanFactory beanFactory) {
        this.beanFactory = beanFactory;
    }

    public Converter converter() {
        return beanFactory.getBean(Converter.class);
    }
}
~~~

Đây là class minh họa, giả định có interface `Converter` và bean tương ứng.

**Tiện ích:** biết container đang sở hữu bean, có thể tra cứu bean theo type/name khi thao tác phát sinh, tuân theo scope thực tế (singleton, prototype, v.v.).

**Chi phí:** bất cứ method nào cũng có thể tạo ra dependency ẩn qua `getBean`; test cần fake/mock factory; lỗi `NoSuchBeanDefinitionException`, `NoUniqueBeanDefinitionException` hay scope-not-active có thể xuất hiện muộn; người đọc code không biết service cần loại bean nào nếu chỉ nhìn constructor.

Nếu chỉ cần **một type** nhưng phải lấy theo nhu cầu, Spring có `ObjectProvider<Converter>` được inject vào constructor. Nó vẫn là Spring-specific abstraction, nhưng **giới hạn bề mặt lookup vào Converter** thay vì trao cả factory cho bean.

### 3.3. `ApplicationContextAware` — tiện ích rộng nhất

Bean implement `ApplicationContextAware` nhận `ApplicationContext` thông qua `setApplicationContext(ApplicationContext)`.

~~~java
public class ContextBridge
        implements org.springframework.context.ApplicationContextAware {

    private org.springframework.context.ApplicationContext context;

    @Override
    public void setApplicationContext(
            org.springframework.context.ApplicationContext context) {
        this.context = context;
    }

    public boolean hasBean(String name) {
        return context.containsBean(name);
    }
}
~~~

Ngoài bean lookup, `ApplicationContext` cung cấp khả năng phát event, đọc resource, giải quyết message/i18n và metadata về context. Đây là công cụ thuận tiện để kết nối một adapter/framework extension.

**Chi phí:** lớp phụ thuộc vào Spring cấp cao; được trao API rộng hơn nhu cầu của đa số business services, có thể gọi `getBean` tùy ý, khó thay bằng Java thuần. Nhiều `ApplicationContext` cha/con hoặc integration-test contexts khiến giả định “chỉ có một context toàn JVM” sai.

Một lưu ý quan trọng: **inject `ApplicationContext` qua constructor hoặc `@Autowired` thay vì implement `ApplicationContextAware` chỉ đổi cách nhận context, chứ không làm lớp hết coupling với Spring**. Phải thay dependency bằng collaborator/abstraction hẹp hơn mới thực sự giảm coupling.

## 4. Bảng so sánh công cụ

| Cách nhận dependency/capability | Điều class biết về Spring | Tính tường minh | Khả năng test thuần Java | Khi nào hợp lý |
| --- | --- | --- | --- | --- |
| Constructor DI với interface nghiệp vụ `PaymentGateway` | Không cần biết Spring | Rõ ràng nhất | Cao, truyền fake trực tiếp | Business service mặc định |
| Setter injection với interface nghiệp vụ | Có thể không phụ thuộc Spring API nếu wiring qua config | Rõ qua setter, phụ thuộc có thể bị thay | Khá tốt | Optional/reconfigurable dependency |
| `@Autowired` field | Biết annotation Spring | Ít tường minh ở constructor | Khó hơn khi tạo object thuần | Một số lớp tích hợp, không nên lạm dụng |
| `ObjectProvider<Gateway>` | Biết một API Spring | Rõ loại dependency, lookup deferred | Cần fake provider hoặc bọc abstraction | Prototype/lazy/optional runtime lookup |
| `BeanNameAware` | Biết callback Spring | Rõ metadata cần | Có thể gọi setter thủ công nhưng cần test integration | Infrastructure cần tên bean |
| `BeanFactoryAware` | Biết Spring BeanFactory | Dependency thực có thể bị ẩn | Cần fake factory | Container extension/registry dynamic |
| `ApplicationContextAware` | Biết Spring ApplicationContext | Quyền rộng, dependency dễ bị ẩn | Cần fake/mock context | Hạ tầng cần nhiều context capabilities |
| Adapter Spring implement interface do ứng dụng định nghĩa | Chỉ adapter biết Spring | Business contract rõ | Core dễ test độc lập | Kiến trúc nhiều module/hexagonal |

Không có một giải pháp tối ưu tuyệt đối: **dependency tĩnh** nên được inject tường minh; **dependency động** cần factory/provider; **container metadata** có thể hợp lý với Aware.

## 5. Thay việc lấy bean trực tiếp bằng constructor DI

### Trước: Service Locator nằm trong business service

~~~java
public class ShippingService
        implements org.springframework.context.ApplicationContextAware {
    private org.springframework.context.ApplicationContext context;

    @Override
    public void setApplicationContext(
            org.springframework.context.ApplicationContext context) {
        this.context = context;
    }

    public void ship(Order order) {
        ShippingGateway gateway = context.getBean(ShippingGateway.class);
        gateway.send(order);
    }
}
~~~

Đây là đoạn minh họa; `Order` và `ShippingGateway` cần được định nghĩa. Service nói với constructor rằng nó **không cần gì**, nhưng method `ship` lại yêu cầu một gateway cụ thể. Nếu không có context hoặc gateway, lỗi chỉ lộ khi method được gọi.

### Sau: dependency tường minh, lớp nghiệp vụ độc lập

~~~java
public final class ShippingService {
    private final ShippingGateway gateway;

    public ShippingService(ShippingGateway gateway) {
        this.gateway = java.util.Objects.requireNonNull(gateway);
    }

    public void ship(Order order) {
        gateway.send(order);
    }
}
~~~

Wiring bằng Java configuration:

~~~java
@Configuration
class ShippingConfig {
    @Bean
    ShippingService shippingService(ShippingGateway gateway) {
        return new ShippingService(gateway);
    }
}
~~~

Đây là các snippet minh họa, không phải tệp Java độc lập. `ShippingService` không cần import Spring; annotation chỉ xuất hiện ở composition root. Unit test có thể truyền một fake `ShippingGateway` và kiểm tra số lần gửi.

**Đánh đổi:** cách sau cần constructor và khai báo bean wiring; cách trước thuận tay trong đoạn code ngắn nhưng khiến service khó kiểm thử và đổi framework về sau. Khi số lượng service tăng, chi phí maintainability của Service Locator thường lớn hơn vài dòng constructor.

## 6. Khi cần lookup động: `ObjectProvider` và factory riêng

Một số dependency phải được chọn hoặc tạo **ở thời điểm hành động**, chẳng hạn prototype cần state riêng mỗi job hoặc dependency optional. Constructor injection của một target singleton duy nhất không luôn đáp ứng nhu cầu.

### 6.1. Bỏ BeanFactory rộng, dùng provider theo type

~~~java
@Service
class ExportCoordinator {
    private final ObjectProvider<ExportTask> taskProvider;

    ExportCoordinator(ObjectProvider<ExportTask> taskProvider) {
        this.taskProvider = taskProvider;
    }

    void export(RequestData input) {
        ExportTask task = taskProvider.getObject();
        task.run(input);
    }
}
~~~

Đây là đoạn minh họa, giả định `ExportTask` được đăng ký với `@Scope("prototype")` nếu cần instance mới mỗi lần; `RequestData` là type nghiệp vụ và có import phù hợp.

`ObjectProvider<T>.getObject()` sẽ resolve bean theo scope. Với prototype, một lookup thông thường cung cấp instance mới; với singleton, nó cung cấp lại singleton; nếu bean bị bọc thành scoped proxy, provider có thể trả proxy thay vì raw target nên cần hiểu cấu hình scope/proxy. **Provider không tự đổi một singleton thành prototype.**

Provider giúp chỉ rõ dependency type trong constructor, nhưng **code vẫn phụ thuộc Spring API**. Để business core độc lập hoàn toàn, định nghĩa **factory interface riêng** ở tầng ứng dụng.

### 6.2. Bọc Spring trong adapter

Tầng nghiệp vụ:

~~~java
public interface ExportTaskFactory {
    ExportTask create();
}

public final class ExportCoordinator {
    private final ExportTaskFactory factory;

    public ExportCoordinator(ExportTaskFactory factory) {
        this.factory = factory;
    }

    public void export(RequestData input) {
        ExportTask task = factory.create();
        task.run(input);
    }
}
~~~

Adapter hạ tầng:

~~~java
public final class SpringExportTaskFactory implements ExportTaskFactory {
    private final ObjectProvider<ExportTask> provider;

    public SpringExportTaskFactory(ObjectProvider<ExportTask> provider) {
        this.provider = provider;
    }

    @Override
    public ExportTask create() {
        return provider.getObject();
    }
}
~~~

Những đoạn này là mẫu kiến trúc cần định nghĩa `ExportTask`/`RequestData` và các import thích hợp. Trong test Java thuần, factory có thể là lambda `() -> new FakeExportTask()` nếu `ExportTaskFactory` là functional interface và type phù hợp.

**Lợi ích thật:** tầng nghiệp vụ phụ thuộc `ExportTaskFactory` do chính nó sở hữu; adapter hạ tầng là vị trí duy nhất biết `ObjectProvider`. Nếu sau này thay Spring bằng factory thủ công, sửa adapter/composition root mà không viết lại core service.

**Chi phí:** thêm một interface và adapter để bảo trì. Đừng tạo factory abstraction chỉ cho một simple singleton dùng trực tiếp; chi phí abstraction chỉ đáng trả khi có yêu cầu deferred creation hoặc tách module rõ ràng.

## 7. Chọn đúng mức API thay vì nhận toàn bộ ApplicationContext

`ApplicationContext` bao gồm nhiều capability. Nếu class chỉ cần một phần, interface hẹp giúp hạn chế quyền truy cập vô ý:

| Chức năng thật sự cần | Spring interface hẹp hoặc lựa chọn khác | Ghi chú |
| --- | --- | --- |
| Phát domain/application event | `ApplicationEventPublisher` | Vẫn là Spring API, nhưng chỉ quyền publish |
| Đọc file/resource | `ResourceLoader` hoặc `Resource` | Domain core có thể nhận dữ liệu đã parse thay vì tự tải |
| Tra message quốc tế hóa | `MessageSource` | Trong core độc lập có thể dùng interface `Localizer` riêng |
| Chọn/tạo bean cùng type theo nhu cầu | `ObjectProvider<T>` / `ObjectFactory<T>` | Lookup có phạm vi type rõ |
| Thực thi logic khi tất cả eager singleton sẵn sàng | `SmartInitializingSingleton` hoặc lifecycle event | Dành cho infrastructure/startup orchestration |
| Biết bean name thật | `BeanNameAware` | Metadata container, không phải business ID |
| Đọc thông tin cấu hình ứng dụng | `Environment` hoặc typed configuration object | Domain có thể nhận một record/value object |
| Truy cập arbitrary bean registry/metadata | `BeanFactory` hoặc interface mở rộng phù hợp | Thường chỉ hợp lý trong container extension |

Một class inject `ApplicationEventPublisher` vẫn **gắn với Spring** vì type ở package Spring. Nhưng mức coupling hẹp hơn nhiều so với giữ `ApplicationContext` để truy cập mọi capability. Nếu yêu cầu test đơn thuần quan trọng, bọc cả publisher trong interface ứng dụng như `DomainEvents`.

## 8. Ví dụ Java 17 hoàn chỉnh: so sánh Aware, constructor DI và ObjectProvider

Ví dụ dùng **Java 17**, **Spring Framework 6.2.19**, Maven. Nó minh họa trực tiếp lợi ích và trade-off của ba cách lấy collaborator. Một `AwareReceiptService` giữ BeanFactory/ApplicationContext để lookup một formatter; một `PureReceiptService` chỉ nhận formatter qua constructor, nên có thể tạo bằng `new` ngoài Spring; một `ProviderReceiptService` nhận provider có type hẹp.

Cấu trúc thư mục:

~~~text
coupling-tradeoffs/
├── pom.xml
└── src/main/java/example/CouplingDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>coupling-tradeoffs</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/example/CouplingDemo.java`:

~~~java
package example;

import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.BeanFactoryAware;
import org.springframework.beans.factory.BeanNameAware;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class CouplingDemo {

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            AwareReceiptService aware =
                    context.getBean(AwareReceiptService.class);
            PureReceiptService pure =
                    context.getBean(PureReceiptService.class);
            ProviderReceiptService provider =
                    context.getBean(ProviderReceiptService.class);

            System.out.println("Aware: " + aware.render(7));
            System.out.println("BeanFactory/context same bean: "
                    + aware.sameFormatter());
            System.out.println("Constructor DI: " + pure.render(7));
            System.out.println("Provider: " + provider.render(8));
        }

        // Đoạn sau vẫn hoạt động khi KHÔNG có Spring container:
        PureReceiptService plain =
                new PureReceiptService(new BasicReceiptFormatter());
        System.out.println("Plain Java: " + plain.render(9));
    }

    public interface ReceiptFormatter {
        String render(int invoiceId);
    }

    public static final class BasicReceiptFormatter
            implements ReceiptFormatter {
        @Override
        public String render(int invoiceId) {
            return "INV-" + invoiceId;
        }
    }

    // Spring-coupled: cả container API và lookup đều nằm trong service.
    public static final class AwareReceiptService
            implements BeanNameAware,
                       BeanFactoryAware,
                       ApplicationContextAware {
        private String beanName;
        private BeanFactory factory;
        private ApplicationContext context;

        @Override
        public void setBeanName(String name) {
            beanName = name;
        }

        @Override
        public void setBeanFactory(BeanFactory beanFactory) {
            factory = beanFactory;
        }

        @Override
        public void setApplicationContext(ApplicationContext applicationContext) {
            context = applicationContext;
        }

        public String render(int invoiceId) {
            return beanName + ": "
                    + context.getBean(ReceiptFormatter.class).render(invoiceId);
        }

        public boolean sameFormatter() {
            return factory.getBean(ReceiptFormatter.class)
                    == context.getBean(ReceiptFormatter.class);
        }
    }

    // Business component không import một Spring API nào.
    public static final class PureReceiptService {
        private final ReceiptFormatter formatter;

        public PureReceiptService(ReceiptFormatter formatter) {
            this.formatter = formatter;
        }

        public String render(int invoiceId) {
            return formatter.render(invoiceId);
        }
    }

    // Vẫn Spring-specific nhưng bề mặt lookup được giới hạn theo type.
    public static final class ProviderReceiptService {
        private final ObjectProvider<ReceiptFormatter> formatters;

        public ProviderReceiptService(
                ObjectProvider<ReceiptFormatter> formatters) {
            this.formatters = formatters;
        }

        public String render(int invoiceId) {
            return formatters.getObject().render(invoiceId);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public ReceiptFormatter receiptFormatter() {
            return new BasicReceiptFormatter();
        }

        @Bean("awareReceiptService")
        public AwareReceiptService awareReceiptService() {
            return new AwareReceiptService();
        }

        @Bean
        public PureReceiptService pureReceiptService(
                ReceiptFormatter formatter) {
            return new PureReceiptService(formatter);
        }

        @Bean
        public ProviderReceiptService providerReceiptService(
                ObjectProvider<ReceiptFormatter> formatterProvider) {
            return new ProviderReceiptService(formatterProvider);
        }
    }
}
~~~

Chạy từ thư mục `coupling-tradeoffs`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.CouplingDemo
~~~

Stdout **do chính chương trình in** (bỏ qua log Maven hoặc logger của môi trường):

~~~text
Aware: awareReceiptService: INV-7
BeanFactory/context same bean: true
Constructor DI: INV-7
Provider: INV-8
Plain Java: INV-9
~~~

Giải thích:

1. `AwareReceiptService` được Spring quản lý. `BeanNameAware` cung cấp `awareReceiptService`; `BeanFactoryAware` cung cấp factory; `ApplicationContextAware` cung cấp context. Khi `render(7)` chạy sau refresh, context resolve bean `ReceiptFormatter` và tạo chuỗi.
2. `sameFormatter()` so sánh hai lookup: trong cấu hình này `ReceiptFormatter` có scope singleton mặc định nên factory và context trả **cùng instance**. Nếu khai báo prototype hoặc proxy khác, kết quả identity có thể khác, nên không tổng quát hóa test này cho mọi scope.
3. `PureReceiptService` chỉ cần `ReceiptFormatter`, và Spring cung cấp thông qua `@Bean` factory argument. Mã service không biết container.
4. `ProviderReceiptService` giữ `ObjectProvider<ReceiptFormatter>`, lookup khi method chạy. Provider tuân thủ scope thật; ở ví dụ này formatter là singleton.
5. Sau khi context đóng, code vẫn có thể `new PureReceiptService(new BasicReceiptFormatter())` và chạy thuần Java. Đó là bằng chứng trực tiếp về **khả năng test/tái sử dụng không cần Spring** của phần business contract.

Ví dụ dùng các nested classes bên trong một file `CouplingDemo.java` đúng quy tắc Java 17. `Config` là nested `static` class, các phương thức `@Bean` được container gọi, không có lời gọi trực tiếp đến methods trên config. Không cần annotation `@ComponentScan` vì mọi bean trong demo được đăng ký qua `@Bean`.

**Điều ví dụ không chứng minh:** rằng Aware luôn kém hiệu năng hơn DI, hoặc mọi ứng dụng cần loại bỏ toàn bộ Aware. Nó chỉ minh họa **bề mặt dependency và cách sử dụng**. Để đo hiệu năng thực tế phải benchmark phù hợp; lựa chọn kiến trúc nên đặt tính đúng, khả năng bảo trì và nhu cầu runtime lookup trước chi phí gọi hàm nhỏ.

## 9. Kiểm thử: chênh lệch chi phí hiện rõ

### 9.1. Business service dùng constructor DI

`PureReceiptService` có thể được tạo trong unit test đơn giản, không cần test runner của Spring:

~~~java
ReceiptFormatter fake = id -> "TEST-" + id;
PureReceiptService service = new PureReceiptService(fake);
String actual = service.render(123);

if (!"TEST-123".equals(actual)) {
    throw new AssertionError("Wrong receipt: " + actual);
}
~~~

Đây là đoạn minh họa trong ngữ cảnh có import hai nested types tương ứng từ `CouplingDemo` hoặc đặt trong cùng class/file phù hợp. Lambda dùng được vì `ReceiptFormatter` là functional interface chỉ có một abstract method.

Đặc điểm: mỗi test có thể tạo instance độc lập, thay stub dễ dàng, không cần startup context hoặc mock BeanFactory.

### 9.2. Service dùng `ApplicationContextAware`

Để unit test riêng `AwareReceiptService` mà không dùng Spring context, test phải tạo hoặc mock `ApplicationContext`, bảo đảm `getBean(ReceiptFormatter.class)` trả fake, gọi `setBeanName`/`setBeanFactory`/`setApplicationContext` đúng, hoặc chuẩn bị test context thật. Nếu quên một callback, test có thể nhận `NullPointerException` vốn không xuất hiện khi container quản lý bean đầy đủ.

Một integration test với `AnnotationConfigApplicationContext` vẫn hữu ích để xác nhận **Spring thực thi đúng callback**, nhưng không nên bắt hàng trăm unit tests nghiệp vụ khởi động context chỉ vì một service dùng Service Locator.

### 9.3. Provider và factory do ứng dụng sở hữu

`ObjectProvider` có thể được fake hoặc stub, nhưng vẫn bắt test business hiểu Spring API. Khi business core nhận `ReceiptFormatterFactory` do chính module định nghĩa, test chỉ cần truyền lambda hoặc factory thuần Java. Điều này đặc biệt hữu ích nếu core có yêu cầu build không thêm `spring-context` vào dependencies.

## 10. Ảnh hưởng đến kiến trúc module

Một kiến trúc phân lớp có thể đặt Spring ở rìa:

~~~text
application-core/
    ReceiptFormatter
    PureReceiptService
    ReceiptFormatterFactory (nếu thật sự cần dynamic creation)

spring-adapter/
    @Configuration
    @Bean definitions
    ObjectProvider adapters
    EventPublisher adapters
    Aware infrastructure components
~~~

Chiều dependency:

~~~text
Spring adapter → Interface do application core định nghĩa
Business core ── không cần ──► org.springframework.*
~~~

**Ý nghĩa:** Core phụ thuộc vào contracts ổn định của chính nó. Spring adapter phụ thuộc vào core để wire collaborators và cung cấp hạ tầng. Nếu sau này đổi cách khởi động hoặc môi trường test, phần core giữ nguyên.

Tuy nhiên, đừng biến yêu cầu “tránh coupling” thành việc bọc mọi API bằng interface mới vô nghĩa. Trong một ứng dụng Spring thuần không có ý định đổi framework, việc trực tiếp dùng `ApplicationEventPublisher` trong một adapter/service tích hợp có thể hoàn toàn hợp lý. **Mục tiêu là giới hạn coupling vào nơi có lợi ích thật**, không đạt chỉ tiêu “0 import Spring” bằng mọi giá.

## 11. Những tình huống Aware hợp lý

Một số trường hợp cần truy cập container thật sự:

1. **Extension/registry infrastructure:** một adapter phải tự đăng ký dựa trên actual bean name, chẳng hạn hệ thống plugin đã tích hợp với Spring bean registry.
2. **Container introspection:** framework component kiểm tra type/scope/metadata để cung cấp chức năng điều phối hoặc diagnostic.
3. **Framework bridge:** tích hợp library không theo DI thông thường, cần đưa Spring-managed bean vào một container hoặc API của bên thứ ba.
4. **Dynamic bean name lookup thực sự do cấu hình quyết định:** tên bean được chọn trong adapter ở runtime, có thể dùng BeanFactory ở boundary thay vì để mọi business service tự lấy.
5. **Generic tooling:** một infrastructure bean dùng ApplicationContext để cung cấp màn hình diagnostic, event dispatch hay quản lý tài nguyên theo context.

Những trường hợp này có chung đặc điểm: **nhiệm vụ của class chính là làm việc với container hoặc bridge hạ tầng**, nên biết Spring là một phần của hợp đồng kỹ thuật.

Nếu class xử lý nghiệp vụ cụ thể như tính thuế, chuyển tiền, validate đơn hàng hoặc định giá, thường không cần ba Aware interfaces. Càng ít quyền truy cập container thì code càng dễ đọc, test và thay thế.

## 12. Rủi ro runtime lookup và lifecycle

### 12.1. Dependency bị giấu

Một constructor `ReportService(ApplicationContext context)` không nói rõ business service cần `InvoiceRepository`, `CurrencyService` và `AuditPublisher`. Những dependency ẩn lộ ra khi đọc các method chứa `getBean`, đôi khi chỉ trong error branch. Static analysis và code review khó phát hiện đầy đủ bean graph.

Đưa dependency thực vào constructor làm hợp đồng rõ hơn. Nếu chỉ cần một bean lookup deferred, inject `ObjectProvider<SpecificType>` để chỉ rõ type.

### 12.2. Runtime lookup có thể ném lỗi muộn

`getBean(Type.class)` có thể thất bại do thiếu bean, nhiều bean cùng type, qualifier không đủ hoặc scope không active. Nếu chỉ chạy ở một nhánh nghiệp vụ ít gặp, lỗi xuất hiện muộn hơn so với tạo bean thông qua constructor injection của dependency bắt buộc. Không đảm bảo mọi constructor DI luôn phát hiện lỗi ngay lúc app start: bean lazy vẫn có thể khởi tạo muộn, nhưng dependency graph vẫn được biểu diễn rõ.

### 12.3. Lookup không đồng nghĩa “new object”

Với singleton, nhiều `getBean()` trả về cùng instance. Với prototype, mỗi lookup trực tiếp target thường tạo instance mới. Với request/session scope, kết quả phụ thuộc scope context; không thể dùng request-scoped bean tùy tiện từ background thread không có active request. Với scoped proxy, có thể nhận cùng proxy nhưng target được chọn theo mỗi invocation.

Lựa chọn Aware/BeanFactory không thay đổi semantics của bean scope. Cần hiểu bean mình lấy là raw target, proxy hay factory product.

### 12.4. Spring-managed object và object Java tự tạo

Aware callbacks chỉ được Spring gọi khi object được container tạo/quản lý và đi qua xử lý thích hợp. `new AwareReceiptService()` thuần Java không tự được gọi `setApplicationContext`. Không dùng static “ApplicationContextHolder” để cố biến mọi object thành service locator toàn cục; nó mang nguy cơ shared mutable state, stale context sau shutdown và phụ thuộc hidden.

### 12.5. Container đang trong quá trình khởi tạo

`setBeanFactory` và `setApplicationContext` thuộc lifecycle **trước khi bean hoàn toàn initialized**. Gọi thêm bean khác hoặc tác vụ nặng ngay trong callback có thể kéo khởi tạo sớm, vòng phụ thuộc, initialization deadlock hoặc thấy raw object trước AOP. Callback nên nhận/lưu tham chiếu hạ tầng, hoàn tất nhanh; nghiệp vụ phụ thuộc toàn context dùng hook khác phù hợp.

### 12.6. AOP, `@Transactional` và self-invocation

Nếu service gọi `this.transactionalMethod()` ngay trong Aware setter hoặc `@PostConstruct`, nó không đi qua Spring AOP proxy thông thường; `@Transactional` có thể không được áp dụng. Truy cập container chỉ để “lấy chính proxy của tôi” trong callback là dấu hiệu thiết kế khó hiểu, có thể kéo bean chưa hoàn tất. Cần tách nghiệp vụ có transaction sang collaborator được gọi từ vị trí phù hợp sau initialization.

### 12.7. Đóng context và giữ tham chiếu quá lâu

Nếu một background thread giữ `ApplicationContext` và cố `getBean()` sau `context.close()`, nó đang dùng hạ tầng đã hết vòng đời. Với parent-child context, context con có thể đóng trong khi parent vẫn còn. Tránh để business class có quyền giữ context tham chiếu toàn JVM; owner/lifecycle phải rõ ở adapter.

## 13. Cách đánh giá độ coupling trong code review

Đừng chỉ hỏi “file này import Spring không?”. Hãy trả lời cụ thể:

- Class có thể tạo bằng `new` với những dependency do test truyền vào không?
- Nếu dependency bắt buộc bị thiếu, constructor/bean definition thể hiện rõ điều đó hay lỗi bị trì hoãn tới `getBean()` trong business method?
- Class có cần tên bean, metadata hoặc event context thật hay chỉ cần một collaborator?
- Unit test có phải fake nguyên `ApplicationContext` chỉ để trả một bean đơn giản không?
- Runtime lookup có chủ đích theo scope/dynamic selection, hay chỉ để tránh thêm constructor parameter?
- Việc lookup có thể tạo bean lúc container đang init hoặc khi web scope chưa active không?
- Nếu đổi từ `ApplicationContextAware` sang injection `ApplicationContext` vào constructor, coupling thực chất đã giảm chưa? **Chưa**, nếu class vẫn thao tác trên context.
- Có thể đặt bean lookup ở composition root/adapter, truyền interface nghiệp vụ cho core không?
- Nếu tạo thêm abstraction, nó có biểu đạt đúng khái niệm domain hay chỉ sao chép một API framework không cần thiết?

Nếu core đã có nhiều `ApplicationContextHolder.getBean` hoặc service thường xuyên yêu cầu arbitrary bean names, có thể xem đó là **dấu hiệu Service Locator lan vào nghiệp vụ**. Tập trung refactor các luồng có thay đổi thường xuyên, khó test hoặc hay lỗi runtime trước.

## 14. Quy trình refactor thực tế

### Bước 1 — Liệt kê dependency ẩn

Tìm các vị trí gọi `getBean`, `getBeansOfType`, static context holder, hoặc implement `BeanFactoryAware`/`ApplicationContextAware`. Với mỗi nơi ghi lại **type/name được lookup**, lý do cần lookup động và scope thực tế.

### Bước 2 — Chuyển lookup tĩnh thành constructor argument

Nếu một service luôn cần `PaymentGateway` và không có điều kiện chọn implementation ở runtime, constructor `Service(PaymentGateway gateway)` là cách đơn giản nhất. Để Spring chọn implementation qua `@Primary`/`@Qualifier` trong cấu hình khi cần.

### Bước 3 — Lookup deferred vẫn giữ type rõ

Nếu cần prototype theo từng job, inject `ObjectProvider<Task>` hoặc factory do ứng dụng định nghĩa. Chọn một instance cho mỗi job và giữ trong biến cục bộ nếu cần state qua nhiều method. Đừng cấu hình proxy prototype rồi vô thức gọi nhiều method và kỳ vọng chúng dùng cùng target.

### Bước 4 — Tách hạ tầng cần context rộng vào adapter

Nếu cần đọc resources, publish events hoặc truy vấn bean metadata, gom nó vào adapter Spring. Để business core nhận interface chuyên biệt như `TemplateContentProvider` hoặc `DomainEvents`. Điều này giúp test với fake không cần context.

### Bước 5 — Xóa dependency Spring không còn dùng

Khi core đã nhận các abstraction/POJO, xóa Aware interfaces và fields/lookup dư thừa khỏi chính lớp đó. Trong build nhiều module, xem xét cấu hình dependency để module core không cần `spring-context` khi compile.

### Bước 6 — Kiểm chứng behavior và lifecycle

Tạo unit test thuần Java cho core; integration test bằng `ApplicationContext` cho adapter/wiring. Test cả nhánh thiếu bean, nhiều implementations, prototype tạo theo mỗi job, request scope không active, context close và error handling. Đừng đổi scope khi refactor nếu không có yêu cầu nghiệp vụ.

## 15. Những quyết định thường gặp

| Tình huống | Quyết định ưu tiên | Khi nào cần cân nhắc khác? |
| --- | --- | --- |
| `InvoiceService` cần `InvoiceRepository` cố định | Constructor DI | Có routing repository thực sự động |
| `OrderService` cần biết bean name để ghi log | Tên component/label cấu hình rõ | Framework registry yêu cầu actual bean name → `BeanNameAware` |
| Consumer muốn phát event | Inject `ApplicationEventPublisher` hoặc domain event adapter | Hạ tầng cần đồng thời nhiều context capabilities |
| Singleton muốn prototype mỗi job | `ObjectProvider<Task>` hoặc factory adapter | Cần lựa chọn bean bằng tên động |
| Code đọc template từ classpath | Inject `Resource`/`ResourceLoader` hoặc content provider | Framework adapter cần context resource semantics rộng |
| Code cần i18n | `MessageSource` hoặc `Localizer` domain | Thành phần framework tích hợp toàn context |
| Generic Spring diagnostic console | `ApplicationContextAware` có thể hợp lý | Nên giới hạn quyền thao tác và lifecycle |
| Plugin registry chọn bean theo name runtime | BeanFactory trong adapter | Có thể inject `Map<String, Plugin>` khi tập plugin hữu hạn |
| Test một phép tính thuần | Không cần Spring test context | Chỉ dùng integration test cho wiring |
| Dùng legacy static context holder khắp nơi | Di chuyển lookup về boundary | Không cố refactor toàn dự án ngay nếu quá rủi ro |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Đổi `ApplicationContextAware` sang constructor `MyService(ApplicationContext context)` có loại bỏ Spring coupling?

**Trả lời:** Không. Chỉ thay cơ chế truyền context; code vẫn tham chiếu Spring type và có khả năng lookup tùy ý.

**Câu 2.** Tại sao constructor `CheckoutService(PaymentGateway gateway)` dễ test hơn `CheckoutService(ApplicationContext context)`?

**Trả lời:** Dependency nghiệp vụ hiện rõ; test có thể truyền gateway fake trực tiếp, không cần tạo/mô phỏng container API để trả lại gateway.

**Câu 3.** `ObjectProvider<ReportTask>` có luôn trả instance mới?

**Trả lời:** Không. Phụ thuộc scope bean được resolve: singleton được tái sử dụng; prototype tạo mới theo mỗi lookup; scoped proxy có semantics riêng.

**Câu 4.** Một adapter đăng ký plugin theo tên bean thực tế có nên cấm dùng `BeanNameAware`?

**Trả lời:** Không. Với infrastructure cần đúng bean metadata, `BeanNameAware` là công cụ hợp lý. Chỉ tránh kéo nó vào code business không cần Spring bean name.

**Câu 5.** Inject `ApplicationEventPublisher` thay cho `ApplicationContext` có xóa hoàn toàn Spring coupling?

**Trả lời:** Không. Cả hai đều thuộc Spring API, nhưng publisher có bề mặt hẹp hơn; muốn core thuần Java, có thể dùng một interface `DomainEvents` do ứng dụng định nghĩa và implement ở Spring adapter.

**Câu 6.** Vì sao không nên gọi `context.getBean(...)` để start hàng loạt worker trong `setApplicationContext`?

**Trả lời:** Callback xảy ra giữa quá trình tạo bean; việc làm đó có thể kéo dependency tạo sớm, vòng phụ thuộc, AOP/proxy chưa hoàn tất và chặn startup. Nên dùng lifecycle hook riêng như `SmartLifecycle` nếu có start/stop.

**Câu 7.** Một service dùng constructor DI nhưng được đánh dấu `@Service`. Nó có còn phụ thuộc Spring không?

**Trả lời:** Class còn phụ thuộc annotation Spring ở mã nguồn, nhưng những phương thức nghiệp vụ và các collaborator vẫn có thể được test bằng `new` nếu constructor nhận interface Java thường. Muốn bỏ dependency compile-time, chuyển annotation/bean registration sang composition root.

**Câu 8.** BeanFactoryAware có tiện ích nào mà constructor DI trực tiếp không có sẵn?

**Trả lời:** Cho phép component hạ tầng truy cập factory quản lý bean và lookup dựa trên metadata/name tại runtime. Đó là năng lực hữu ích cho adapter/framework extension, nhưng cũng mở rộng coupling và che giấu dependency.

## 17. Checklist áp dụng

- Đã phân biệt **dependency nghiệp vụ**, **capability Spring hẹp** và **container-wide API**?
- Những collaborator bắt buộc đã xuất hiện rõ trong constructor?
- Code có chỉ dùng `Aware` khi thực sự cần metadata hoặc hạ tầng của Spring?
- Nơi cần deferred lookup đã dùng provider/factory phù hợp với scope?
- Business core có thể test bằng POJO/fake mà không khởi động `ApplicationContext`?
- Có tránh static ApplicationContext holder và bean lookup lan khắp logic nghiệp vụ?
- Có phân biệt coupling do **cách inject context** với coupling do **kiểu API được sử dụng**?
- Với bean proxy, có hiểu thời điểm lookup và semantics target theo scope?
- Có tránh gọi bean động hoặc việc nặng khi Aware callback đang chạy?
- Các adapter có lifecycle/ownership rõ khi context đóng?
- Mọi interface trừu tượng bổ sung có mang ý nghĩa nghiệp vụ thực, thay vì chỉ thêm boilerplate?

## 18. Tài liệu chính thức

- [Spring Framework Reference — ApplicationContextAware and BeanNameAware](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html#beans-factory-aware)
- [Spring Framework Reference — BeanFactory API](https://docs.spring.io/spring-framework/reference/core/beans/beanfactory.html)
- [Spring Framework Reference — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework Reference — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [Spring Framework Reference — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework Reference — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework Javadoc — ApplicationContextAware](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationContextAware.html)
- [Spring Framework Javadoc — BeanFactoryAware](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/BeanFactoryAware.html)

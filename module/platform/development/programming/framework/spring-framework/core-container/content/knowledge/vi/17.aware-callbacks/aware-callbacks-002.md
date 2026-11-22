# BeanNameAware, BeanFactoryAware và ApplicationContextAware trong Spring Framework

## 1. Bài toán: bean cần biết thông tin từ container

Dependency Injection (DI) là nguyên tắc trung tâm của Spring Core Container: một bean thông thường nên **nhận các dependency nghiệp vụ cần dùng qua constructor, setter hoặc cơ chế injection khác**, thay vì tự tìm mọi thứ trong container. Tuy nhiên, một số bean hạ tầng cần biết **chính nó được container đăng ký dưới tên nào**, **BeanFactory nào đang quản lý nó** hoặc **ApplicationContext nào đang chứa nó**.

Spring cung cấp các interface dạng `Aware` cho nhu cầu đó. Khi bean do Spring quản lý implement một trong các interface tương ứng, container sẽ gọi callback và chuyển thông tin hạ tầng thích hợp vào instance.

Ba interface trọng tâm:

- `BeanNameAware` — nhận **tên đăng ký thực tế của bean** qua `setBeanName(String name)`.
- `BeanFactoryAware` — nhận **BeanFactory sở hữu bean** qua `setBeanFactory(BeanFactory beanFactory)`.
- `ApplicationContextAware` — nhận **ApplicationContext bao quanh bean** qua `setApplicationContext(ApplicationContext applicationContext)`.

Các callback này diễn ra **sau khi điền các property thông thường** và **trước các init callback như `InitializingBean.afterPropertiesSet()` và custom init method**. Chúng là cơ chế container thông báo hạ tầng cho bean, không phải tín hiệu “toàn ứng dụng đã startup xong”.

### Mô hình trực quan

~~~text
ApplicationContext (cung cấp API cấp cao)
    │
    ├── BeanFactory (quản lý bean definitions và bean instances)
    │       │
    │       └── tạo bean "auditAdapter"
    │                │
    │                ├── constructor / factory method
    │                ├── tiêm dependency/thuộc tính thông thường
    │                ├── BeanNameAware.setBeanName("auditAdapter")
    │                ├── BeanFactoryAware.setBeanFactory(beanFactory)
    │                ├── ApplicationContextAware.setApplicationContext(context)
    │                ├── @PostConstruct và các init callbacks
    │                └── bean hoàn thành post-processing
    │
    └── chương trình có thể lấy bean đã được khởi tạo
~~~

Đây là trình tự **phổ biến trong ApplicationContext thông thường**; `ApplicationContextAware` thực tế được xử lý thông qua một `BeanPostProcessor` của context, trong khi `BeanNameAware` và `BeanFactoryAware` được gọi trực tiếp bởi BeanFactory trong quy trình khởi tạo. Sơ đồ không phải hợp đồng về vị trí của **mọi** custom `BeanPostProcessor`, và không thay thế lifecycle đầy đủ của một số bean đặc biệt.

## 2. Interface `Aware` có ý nghĩa gì?

`org.springframework.beans.factory.Aware` là interface đánh dấu (marker interface): bản thân nó không khai báo phương thức cần implement. Các interface cụ thể kế thừa `Aware` rồi khai báo callback chứa thông tin phù hợp.

~~~java
// Minh họa chữ ký API; không phải file Java standalone.
public interface BeanNameAware extends Aware {
    void setBeanName(String name);
}

public interface BeanFactoryAware extends Aware {
    void setBeanFactory(BeanFactory beanFactory) throws BeansException;
}

public interface ApplicationContextAware extends Aware {
    void setApplicationContext(ApplicationContext applicationContext)
            throws BeansException;
}
~~~

Các định nghĩa trên là dạng lược bớt import/documentation để học chữ ký; namespace thực tế lần lượt là `org.springframework.beans.factory.BeanNameAware`, `org.springframework.beans.factory.BeanFactoryAware` và `org.springframework.context.ApplicationContextAware`.

**Điểm mấu chốt:** chỉ implement `Aware` trống **không** khiến Spring tự inject mọi thứ. Bean phải implement **interface cụ thể** mà container hoặc bộ xử lý hỗ trợ. Việc Spring gọi callback phụ thuộc bean **được quản lý bởi container phù hợp**. Tự `new MyAwareBean()` bên ngoài Spring không tự phát sinh các callback này.

### Bảng so sánh nhanh

| Interface | Callback | Giá trị nhận được | Thường dùng cho |
| --- | --- | --- | --- |
| `BeanNameAware` | `setBeanName(String)` | Tên bean thực tế trong BeanFactory | Adapter, hạ tầng cần gắn metadata/log với bean name |
| `BeanFactoryAware` | `setBeanFactory(BeanFactory)` | BeanFactory đang sở hữu bean | Hạ tầng cần dependency lookup, metadata/lifecycle của factory |
| `ApplicationContextAware` | `setApplicationContext(ApplicationContext)` | ApplicationContext của bean | Hạ tầng cần event, resource, message hoặc context-level API |
| Constructor DI thông thường | Constructor do Spring gọi | Những dependency đã khai báo | Service, repository, controller, phần lớn code nghiệp vụ |

Cả ba Aware callback đều làm object phụ thuộc trực tiếp vào Spring API. Chỉ dùng khi **thật sự cần thông tin container**; khi chỉ cần `PaymentGateway`, hãy inject `PaymentGateway`.

## 3. `BeanNameAware` — bean biết tên đăng ký của mình

### 3.1. Cách hoạt động

Một class implement:

~~~java
import org.springframework.beans.factory.BeanNameAware;

public class NamedProcessor implements BeanNameAware {
    private String beanName;

    @Override
    public void setBeanName(String name) {
        this.beanName = name;
    }

    public String beanName() {
        return beanName;
    }
}
~~~

Nếu đăng ký nó với tên `namedProcessor`, Spring gọi `setBeanName("namedProcessor")` trong giai đoạn khởi tạo bean.

~~~java
@Bean(name = "namedProcessor")
NamedProcessor namedProcessor() {
    return new NamedProcessor();
}
~~~

Hai snippet có thể đặt vào các tệp/class cấu hình thích hợp; phần trên minh họa một bean và phương thức `@Bean`, **không phải chương trình Java đầy đủ**.

### 3.2. Bean name có phải tên class hoặc tên Java field không?

Không. Tên bean là **định danh trong container**, phụ thuộc cách đăng ký:

- `@Bean` thường lấy tên method khi không chỉ định tên khác.
- `@Bean("shippingWorker")` chỉ định tên bean là `shippingWorker`.
- Component scanning thường tạo tên dựa trên tên class theo `BeanNameGenerator`, nhưng có thể thay quy tắc.
- XML `<bean id="...">` chỉ định id hoặc các alias.
- Bean nội bộ (inner bean) hoặc bean được đăng ký bằng API có thể mang tên sinh tự động.

`BeanNameAware` nhận **actual bean name** do factory quản lý. Đối với một số inner beans, Spring có thể điều chỉnh tên cho duy nhất; vì thế tên nhận được không nhất thiết trùng 100% với một chuỗi trong cấu hình ban đầu.

Ví dụ có alias:

~~~java
@Bean(name = {"fastEncoder", "primaryEncoderAlias"})
Encoder encoder() {
    return new Encoder();
}
~~~

`BeanNameAware` được gọi bằng tên bean chính mà container gắn cho định nghĩa, **không gọi một lần cho mỗi alias**. Không dựa vào alias do người dùng sử dụng khi lookup để suy ra giá trị callback. Tên bean có thể thay đổi khi refactor config; tránh xây dựng business logic bằng cách so sánh các string name cố định.

### 3.3. Khi nào có ích?

- Logging infrastructure cần gắn bean name vào thông báo chẩn đoán.
- Một adapter hạ tầng phải tự đăng ký tài nguyên theo đúng tên bean.
- Một generic component dùng chung class nhưng được đăng ký thành nhiều bean definitions cần biết tên của **định nghĩa cụ thể**.

Tránh dùng tên bean làm **khóa định danh người dùng, mã đơn hàng hoặc security policy**; đó là metadata container, không phải dữ liệu nghiệp vụ bất biến.

## 4. `BeanFactoryAware` — truy cập nhà máy quản lý bean

### 4.1. Callback và khả năng

`BeanFactoryAware` cho bean nhận tham chiếu tới `org.springframework.beans.factory.BeanFactory` thực sự sở hữu bean:

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.BeanFactoryAware;

public class LookupAdapter implements BeanFactoryAware {
    private BeanFactory factory;

    @Override
    public void setBeanFactory(BeanFactory beanFactory) throws BeansException {
        this.factory = beanFactory;
    }

    public Encoder newEncoder() {
        return factory.getBean(Encoder.class);
    }
}
~~~

Đây là snippet minh họa; type `Encoder` cần có bean definition đúng và import/class phù hợp. Nếu bean `Encoder` là prototype, mỗi lần `getBean(Encoder.class)` container thực hiện một lookup theo prototype scope. Nếu `Encoder` là singleton, những lần lookup thường nhận lại cùng instance.

Giao diện cơ bản `BeanFactory` cung cấp các thao tác như `getBean(...)`, `containsBean(...)`, `isSingleton(...)`, `isPrototype(...)`, `getType(...)`. Nó **không đồng nghĩa** bạn đang giữ một `ConfigurableListableBeanFactory`: đừng gọi API quản trị definition chỉ thuộc interface mở rộng khi chỉ khai báo biến kiểu `BeanFactory`.

### 4.2. Khác gì với DI thông thường?

Inject trực tiếp:

~~~java
public ReportService(Encoder encoder) {
    this.encoder = encoder;
}
~~~

Ưu điểm: dependency hiển thị rõ trong constructor, dễ dùng fake/mock ở unit test, bean không phụ thuộc vào container lookup.

Tự `factory.getBean(Encoder.class)`:

~~~java
public Encoder lookupEncoderWhenNeeded() {
    return factory.getBean(Encoder.class);
}
~~~

Ưu điểm đặc biệt khi **đúng là cần lấy bean theo nhu cầu và scope**. Nhược điểm: dependency ẩn trong method; lỗi thiếu/nhiều bean có thể xuất hiện lúc runtime; code buộc phải biết Spring và BeanFactory. Với lookup theo nhu cầu, Spring thường khuyến nghị cách có chủ đích hơn như `ObjectProvider<Encoder>` injected vào constructor.

Ví dụ:

~~~java
public ReportService(ObjectProvider<Encoder> encoders) {
    this.encoders = encoders;
}

public void execute() {
    Encoder instance = encoders.getObject();
    // Dùng instance theo đơn vị thao tác cần thiết.
}
~~~

Các đoạn trên là mẫu method/constructor minh họa, không phải class hoàn chỉnh. `ObjectProvider` nằm trong package `org.springframework.beans.factory`. Việc có provider **không tự đảm bảo một instance mới**; kết quả phụ thuộc scope bean được provider resolve.

### 4.3. Vì sao không nên gọi `getBean()` tùy tiện ngay trong `setBeanFactory()`?

`setBeanFactory()` được gọi khi **chính bean này còn đang khởi tạo**. Gọi một bean khác ở đó có thể buộc Spring tạo thêm bean, sinh vòng phụ thuộc hoặc kéo theo initialization side effects. Nếu cần một dependency bắt buộc, constructor injection thường dễ hiểu hơn. Không dùng Aware callback như cơ chế startup orchestration.

Dù javadoc cho phép sử dụng BeanFactory ngay trong callback, điều đó không cam kết mọi bean khác đã hoàn tất khởi tạo hoặc toàn application đã ready.

## 5. `ApplicationContextAware` — nhận Spring context

### 5.1. Callback

`ApplicationContextAware` cho bean nhận `org.springframework.context.ApplicationContext` hiện hành:

~~~java
import org.springframework.beans.BeansException;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;

public class ContextInspector implements ApplicationContextAware {
    private ApplicationContext context;

    @Override
    public void setApplicationContext(ApplicationContext applicationContext)
            throws BeansException {
        this.context = applicationContext;
    }

    public boolean hasBean(String name) {
        return context.containsBean(name);
    }
}
~~~

Đây là class minh họa. Với một `ApplicationContext` như `AnnotationConfigApplicationContext` hoặc web-aware context, Spring đăng ký `ApplicationContextAwareProcessor` để cung cấp context trước init callbacks.

### 5.2. `ApplicationContext` có gì ngoài `BeanFactory`?

`ApplicationContext` là interface cấp cao, cung cấp nhiều chức năng bổ sung:

- Kế thừa các khả năng bean lookup từ `ListableBeanFactory` và `HierarchicalBeanFactory`.
- `getResource(...)` để truy cập tài nguyên dưới dạng `Resource`.
- `getMessage(...)` thông qua `MessageSource`, hỗ trợ i18n và resource bundles.
- `publishEvent(...)` thông qua `ApplicationEventPublisher`.
- `getId()`, `getDisplayName()`, `getParent()` để đọc metadata và quan hệ context.
- Trong những biến thể có quyền quản lý như `ConfigurableApplicationContext`, có thêm refresh/close/environment/lifecycle capabilities.

Không hiểu `ApplicationContextAware` là “được quyền sửa tất cả bean tùy lúc”. Reference được cung cấp là interface `ApplicationContext`, thường nên dùng theo nhu cầu hẹp. Casting tùy tiện sang implementation class cụ thể khiến code khó tái sử dụng và dễ lỗi giữa các context.

### 5.3. Ưu tiên interface hẹp khi chỉ cần một khả năng

Nếu chỉ cần publish event, cách phụ thuộc hẹp hơn:

~~~java
public AuditService(ApplicationEventPublisher events) {
    this.events = events;
}
~~~

Nếu chỉ cần đọc resource:

~~~java
public TemplateReader(ResourceLoader loader) {
    this.loader = loader;
}
~~~

Nếu chỉ cần i18n:

~~~java
public GreetingService(MessageSource messages) {
    this.messages = messages;
}
~~~

Đây là các constructor snippet minh họa, giả định các field được khai báo và import phù hợp.

Có thể inject `ApplicationEventPublisher`, `ResourceLoader`, `MessageSource` hoặc implement các Aware interfaces chuyên biệt (`ApplicationEventPublisherAware`, `ResourceLoaderAware`, `MessageSourceAware`) nếu đang viết một hạ tầng cần callback. Khi chỉ cần một collaborator đã biết, inject chính collaborator đó.

### 5.4. Một bean có thể thuộc nhiều ApplicationContext không?

Một object được tạo bởi một context thường nhận **context sở hữu hoặc tạo nó** qua callback. Ứng dụng có thể có parent context và child context; chúng có các bean registries và event semantics riêng. Không dùng static field toàn cục để giữ `ApplicationContext` rồi giả định chỉ có một context cho toàn JVM.

Nếu hai context cùng đăng ký một class thành **hai bean instances**, mỗi instance có thể nhận context khác nhau. Nếu cố tái sử dụng **cùng một raw object instance** dưới nhiều bean definitions/contexts, các callback có thể bị gọi lại và ghi đè tham chiếu; đây là thiết kế bất thường nên tránh khi cần ownership rõ ràng.

## 6. Thứ tự gọi ba Aware callback

Trong `AnnotationConfigApplicationContext` thông thường, callback của ba interface trọng tâm chạy theo thứ tự:

1. `BeanNameAware.setBeanName(...)`, do BeanFactory gọi trực tiếp.
2. `BeanFactoryAware.setBeanFactory(...)`, sau `BeanClassLoaderAware` nếu có.
3. `ApplicationContextAware.setApplicationContext(...)`, do `ApplicationContextAwareProcessor` thực hiện trong pha `BeanPostProcessor.before`.

Các bước này diễn ra **sau constructor/property population**, trước `@PostConstruct` trong cấu hình chuẩn và trước `InitializingBean.afterPropertiesSet()` / custom init. `ApplicationContextAware` không tự hoạt động trong `DefaultListableBeanFactory` thuần nếu không có context processor. Aware fields chưa được gán trong constructor; không dùng callback để kích hoạt hàng loạt bean khác trước khi context refresh xong. Bài 185 dành riêng cho thứ tự của **tất cả** nhóm Aware, các BeanPostProcessor, init/destroy và ví dụ ghi log đầy đủ.

## 7. Ví dụ Java 17 chạy được: ba callback và lifecycle

Đây là ví dụ độc lập dùng Java 17, Maven và Spring Framework `6.2.12`. Chương trình đăng ký một bean duy nhất có đầy đủ ba Aware interfaces, sau đó cho thấy callback thứ tự với `@PostConstruct`, `InitializingBean` và custom `initMethod`. Không cần web server hay Spring Boot.

Cấu trúc:

~~~text
spring-aware-demo/
├── pom.xml
└── src/main/java/example/AwareDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aware-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>jakarta.annotation</groupId>
            <artifactId>jakarta.annotation-api</artifactId>
            <version>2.1.1</version>
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

Tệp `src/main/java/example/AwareDemo.java`:

~~~java
package example;

import jakarta.annotation.PostConstruct;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.BeanFactoryAware;
import org.springframework.beans.factory.BeanNameAware;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class AwareDemo {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {
            AwareProbe probe = context.getBean(AwareProbe.class);
            System.out.println("8. Bean da san sang: " + probe.ready());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean(name = "awareProbe", initMethod = "customInit")
        public AwareProbe awareProbe() {
            return new AwareProbe();
        }
    }

    public static class AwareProbe
            implements BeanNameAware,
                       BeanFactoryAware,
                       ApplicationContextAware,
                       InitializingBean {

        private String beanName;
        private BeanFactory beanFactory;
        private ApplicationContext applicationContext;
        private boolean initialized;

        public AwareProbe() {
            System.out.println("1. Constructor");
        }

        @Override
        public void setBeanName(String beanName) {
            this.beanName = beanName;
            System.out.println("2. BeanNameAware: " + beanName);
        }

        @Override
        public void setBeanFactory(BeanFactory beanFactory)
                throws BeansException {
            this.beanFactory = beanFactory;
            System.out.println("3. BeanFactoryAware: "
                    + beanFactory.containsBean("awareProbe"));
        }

        @Override
        public void setApplicationContext(ApplicationContext applicationContext)
                throws BeansException {
            this.applicationContext = applicationContext;
            System.out.println("4. ApplicationContextAware: "
                    + (applicationContext != null));
        }

        @PostConstruct
        public void afterInjection() {
            boolean ok = "awareProbe".equals(beanName)
                    && beanFactory != null
                    && applicationContext != null;
            System.out.println("5. @PostConstruct: " + ok);
        }

        @Override
        public void afterPropertiesSet() {
            initialized = true;
            System.out.println("6. InitializingBean");
        }

        public void customInit() {
            System.out.println("7. Custom initMethod");
        }

        public boolean ready() {
            return initialized
                    && "awareProbe".equals(beanName)
                    && beanFactory.containsBean(beanName)
                    && applicationContext.containsBean(beanName);
        }
    }
}
~~~

Chạy từ thư mục `spring-aware-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.AwareDemo
~~~

Stdout dự kiến do chương trình in (không bao gồm output riêng của Maven/SLF4J trong môi trường cụ thể):

~~~text
1. Constructor
2. BeanNameAware: awareProbe
3. BeanFactoryAware: true
4. ApplicationContextAware: true
5. @PostConstruct: true
6. InitializingBean
7. Custom initMethod
8. Bean da san sang: true
~~~

**Giải thích:**

- Constructor tạo `AwareProbe` nhưng chưa có giá trị của các Aware fields.
- `setBeanName` nhận **tên đã đăng ký** `awareProbe`, không lấy từ tên class `AwareProbe`.
- `setBeanFactory` nhận factory đang chứa definition. `containsBean("awareProbe")` trả true vì bean đã được đăng ký ngay cả khi chính bean còn đang khởi tạo; đoạn này không gọi `getBean()` và không tạo bean mới.
- `setApplicationContext` nhận context bao quanh bean. Việc chỉ kiểm tra non-null không kích hoạt lookup hoặc công việc khác.
- Khi đến `@PostConstruct`, cả ba callback đã đi qua trong cấu hình thông thường của ví dụ. Đoạn kiểm tra thuần xác nhận field đã được set.
- `afterPropertiesSet()` và `customInit()` chạy sau Aware callbacks. `ready()` được gọi ở `main` sau khi `AnnotationConfigApplicationContext(Config.class)` refresh xong.

Tại sao ví dụ không gọi `applicationContext.getBean(...)` ngay trong `setApplicationContext`? Vì callback đang xảy ra giữa quá trình tạo bean; gọi bean khác lúc này có thể làm khởi tạo thêm dependency, gây circular lookup hoặc khó dự đoán thứ tự startup. Trong ví dụ chỉ lưu reference và kiểm tra thông tin đơn giản.

## 8. BeanFactory và ApplicationContext có phải cùng object?

Không cần. `ApplicationContext` thường dùng hoặc bao bọc một bean factory bên trong. Trong `AnnotationConfigApplicationContext`, `setBeanFactory` nhận BeanFactory được context sử dụng, còn `setApplicationContext` nhận đối tượng context. Hai reference thuộc **hai interface với vai trò khác nhau**, không được giả định `beanFactory == applicationContext`.

~~~text
ApplicationContext
   │ expose context-level API, events, messages, resources
   │
   └── sở hữu / sử dụng BeanFactory
          └── quản lý bean definitions, scope và lifecycle

BeanFactoryAware         → factory quản lý bean
ApplicationContextAware  → context bao quanh bean
BeanNameAware            → tên đăng ký của bean đó
~~~

`ApplicationContext` kế thừa những giao diện cho phép bean lookup, nhưng không vì vậy mà trở thành object factory cấp thấp theo identity Java. Đừng dùng ép kiểu implementation để sửa bean definition ở bất cứ thời điểm nào.

## 9. Sự khác biệt với `@Autowired`, `@Value` và constructor injection

Constructor injection cấp collaborator **ngay khi tạo object**; `@Autowired` và `@Value` hỗ trợ inject/resolve dependency hoặc value ở vị trí hợp lệ qua Spring infrastructure. Aware cấp metadata/capability **sau** khi instance đã được tạo. Đây là các mục đích khác nhau, và bean không phải implement Aware chỉ để nhận một dependency từ container.

Ví dụ một component chỉ cần phát event có thể nhận constructor `ApplicationEventPublisher` rồi giữ field `final`; không cần lấy cả context. `BeanNameAware` cung cấp tên đăng ký của chính bean, không thay `@Qualifier` (cơ chế chọn dependency). Với prototype theo nhu cầu, inject `ObjectProvider<T>`; nó tuân thủ scope target, không mặc định tạo instance mới. Nếu cần khai thác cả BeanFactory hoặc context metadata trong adapter/framework bridge, Aware có thể có ý nghĩa riêng.

## 10. Các rủi ro về lifecycle và AOP

Aware callback được gọi trong quá trình bean còn initialize. Constructor không thể dùng field do `setBeanName`/`setApplicationContext` thiết lập; trong các setter cũng tránh gọi `getBean` hàng loạt vì dễ early initialization, vòng dependency hoặc kéo singleton/proxy vào trạng thái chưa hoàn chỉnh.

Nếu bean được Spring AOP bọc proxy **sau initialization**, Aware setters thông thường chạy trên target. Self-invocation như `this.someTransactionalMethod()` từ setter/init có thể không đi qua AOP proxy, nên đừng coi callback là nơi chạy nghiệp vụ transactional. Một context được cung cấp trong callback cũng chưa bảo đảm `ContextRefreshedEvent` đã phát hoặc mọi listener đã sẵn sàng.

Với parent-child contexts, hãy xác định context thật sở hữu bean; không giữ reference trong static global. Bean singleton thường nhận callback một lần khi được tạo, prototype nhận mỗi lần tạo target mới, và context đã đóng không còn là nguồn lookup hoạt động bình thường.

## 11. Khi nào dùng ba Aware interface?

| Nhu cầu thực tế | Hướng phù hợp |
| --- | --- |
| Hạ tầng cần tên bean để logging/registry | `BeanNameAware` |
| Adapter cần bean lookup/metadata động của factory | `BeanFactoryAware` |
| Tooling cần context hierarchy hoặc nhiều dịch vụ cấp context | `ApplicationContextAware` |
| Service chỉ cần repository/gateway/mapper | Constructor injection trực tiếp |
| Singleton cần lấy prototype theo job | Inject `ObjectProvider<T>` hoặc application factory |
| Chỉ cần events, resources hay i18n | Inject `ApplicationEventPublisher`, `ResourceLoader`/`Resource`, `MessageSource` |
| Cần chạy logic sau startup | Lifecycle/event hook, không đặt vào Aware setter |

Sự lựa chọn dựa vào **API nhỏ nhất diễn đạt dependency thật**. BeanNameAware là metadata của bean, còn BeanFactory/ApplicationContext là quyền truy cập container; chỉ dùng chúng khi chính nhiệm vụ class là làm việc với hạ tầng Spring. Bài 186 phân tích chi tiết những đánh đổi, cách tách adapter và test.

## 12. Các lỗi phổ biến

### Lỗi 1 — Tự tạo object bằng `new`

~~~java
AwareProbe probe = new AwareProbe();
probe.ready(); // Aware fields chưa được container điền.
~~~

Spring không quản lý object vừa tạo bằng `new`. Muốn Aware callback phải đăng ký bean và để container tạo/khởi tạo instance, hoặc tự gọi lifecycle qua API đặc biệt với hợp đồng rõ (đây không phải trường hợp phổ biến của ứng dụng).

### Lỗi 2 — Tin bean name luôn là simple class name

Class `AuditSink` có thể được đăng ký bằng `@Bean("logSink")` hoặc một alias. `setBeanName` nhận bean name thực tế, không có quy tắc bảo đảm bằng `"auditSink"`. Nếu name có vai trò business, đặt dữ liệu business thành dependency rõ ràng.

### Lỗi 3 — Gọi `getBean()` để “tự inject” mọi dependency

Dùng `BeanFactoryAware` và gọi `factory.getBean(Repository.class)` khắp nơi làm dependency ẩn. Ưu tiên constructor DI và chỉ dùng dynamic lookup khi có nhu cầu rõ. Nếu có nhiều candidate cùng type, lookup còn có thể ném `NoUniqueBeanDefinitionException`; nếu thiếu bean có thể ném `NoSuchBeanDefinitionException`.

### Lỗi 4 — Coi `ApplicationContextAware` luôn hoạt động trên BeanFactory thuần

`DefaultListableBeanFactory` không tự tạo `ApplicationContext` và không tự cấp callback này như một `ApplicationContext`. Với `AnnotationConfigApplicationContext`, infrastructure processors được thiết lập thích hợp nên callback hoạt động.

### Lỗi 5 — Truy cập bean khác quá sớm

Gọi `getBean()` để kích hoạt một transaction, consumer hoặc job dài trong `setApplicationContext` có thể kéo quá trình tạo bean khác vào một thời điểm không mong muốn. Aware callback nên lưu hạ tầng cần thiết và hoàn tất nhanh.

### Lỗi 6 — Nhầm BeanFactory reference với chính ApplicationContext

Hai tham số `BeanFactory` và `ApplicationContext` khác vai trò và có thể là hai Java objects khác nhau. Dùng API phù hợp thay vì ép kiểu không được bảo đảm.

### Lỗi 7 — Aware interface là DI business tốt hơn constructor injection

Phần lớn application services chỉ cần collaborator nghiệp vụ, vì vậy constructor injection dễ đọc và dễ test hơn. Aware interfaces phù hợp nhất với các bean **infrastructure** cần biết môi trường Spring.

### Lỗi 8 — Callback sẽ được gọi lặp mỗi lần `getBean`

Đối với singleton, các Aware callbacks thường chạy **một lần khi bean instance được tạo**, không chạy mỗi lần lookup singleton. Đối với prototype, mỗi instance được tạo lại đi qua quy trình wiring/lifecycle nên callback có thể chạy nhiều lần. Với AOP/scoped proxy, chú ý phân biệt target instance và proxy bean.

## 13. Kiểm thử những hành vi Aware một cách có ý nghĩa

### 13.1. Unit test thuần Java

Nếu phần business logic không cần bean name hay context, tách business service để constructor nhận các collaborator bình thường. Test không cần Spring. Với một bean infrastructure có Aware, unit test có thể gọi các setter callback thủ công trên stub hoặc mock `BeanFactory`/`ApplicationContext`, nhưng test đó chỉ xác thực code của bạn, **không chứng minh Spring thực sự gọi callback ở đúng lifecycle**.

### 13.2. Integration test với context thật

Dùng một `AnnotationConfigApplicationContext` chứa bean như ví dụ mục 7, xác nhận:

- `beanName` trong callback khớp bean name khai báo, không phụ thuộc alias lookup.
- Factory cung cấp trong callback có bean definition của chính bean.
- Context cung cấp trong callback khớp context khởi tạo bean.
- Ba callback đã chạy trước `@PostConstruct` và `afterPropertiesSet`.
- Khi gọi `getBean()` nhiều lần với singleton, callbacks không chạy lại.
- Khi tạo prototype nhiều lần, mỗi target instance nhận callbacks riêng.

Đừng dùng `assertSame(context, beanFactory)`: không có bảo đảm đây là cùng object.

### 13.3. Test ranh giới startup

Không tạo task cần `ApplicationContext.getBean` rồi chờ nó ngay trong Aware setter. Dùng integration test với lifecycle hooks riêng nếu cần khẳng định ứng dụng có thể start/stop worker. Nếu có parent-child context, xác thực bean nhận đúng context sở hữu nó.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Class implement `BeanNameAware` và được đăng ký qua `@Bean("billingEngine")`. Callback nhận gì?

**Đáp án:** `"billingEngine"` là bean name thực tế trong trường hợp này; không nhất thiết là tên class hoặc tên method Java.

**Câu 2.** Một bean implement `BeanFactoryAware`. Có phải `setBeanFactory` chỉ được gọi sau `@PostConstruct`?

**Đáp án:** Không. Callback này thuộc giai đoạn trước initialization; trong flow thông thường, nó chạy sau property population và trước `@PostConstruct`, `afterPropertiesSet` và custom init.

**Câu 3.** Bean implement `ApplicationContextAware` nhưng chỉ dùng riêng `DefaultListableBeanFactory`. Có chắc nhận `ApplicationContext` không?

**Đáp án:** Không. BeanFactory thuần không có ApplicationContext để cung cấp nếu không thêm infrastructure tương ứng.

**Câu 4.** Constructor muốn sử dụng `beanName` đã được `BeanNameAware` inject. Có đúng thứ tự không?

**Đáp án:** Không. Constructor tạo instance trước khi có callback. Truyền dữ liệu bắt buộc qua constructor hoặc đợi Aware callback xong trước khi sử dụng giá trị.

**Câu 5.** Business service chỉ cần `CurrencyConverter`. Nên inject `ApplicationContext` rồi `getBean(CurrencyConverter.class)`?

**Đáp án:** Thường không. Constructor injection của `CurrencyConverter` trực tiếp diễn đạt dependency rõ và dễ unit test.

**Câu 6.** Một singleton `ApplicationContextAware` có nhận lại context mỗi lần ai đó gọi `getBean()`?

**Đáp án:** Không. Callback gắn với quá trình tạo/khởi tạo **instance**, còn các lần lookup singleton thường chỉ nhận lại bean đã có.

**Câu 7.** `ApplicationContextAware` có thể thay thế `ApplicationEventPublisherAware` không?

**Đáp án:** `ApplicationContext` có API publish event nên về khả năng kỹ thuật là có, nhưng nếu **chỉ cần event publisher**, injection `ApplicationEventPublisher` hoặc `ApplicationEventPublisherAware` thường tạo phụ thuộc hẹp và rõ ràng hơn.

## 15. Checklist áp dụng

- Bean có do Spring thực sự tạo và quản lý không?
- Cần **tên bean**, **BeanFactory**, **ApplicationContext**, hay chỉ cần dependency nghiệp vụ?
- Nếu cần tên bean, có phụ thuộc vào alias, generated name hay giả định tên class không?
- Nếu cần BeanFactory, có tránh gọi bean động và gây vòng phụ thuộc trong callback không?
- Nếu cần ApplicationContext, có thực sự cần các capability của context hay có interface nhỏ hơn?
- Code có đợi Aware callback thay vì truy cập field trong constructor không?
- Nếu có AOP, code có tránh self-invocation và publish raw target quá sớm không?
- Có phân biệt một bean singleton với nhiều prototype instances và nhiều application contexts không?
- Có test lifecycle thật ít nhất một lần để kiểm chứng callback order?
- Có đưa startup job và resource ownership sang lifecycle hook thích hợp thay vì callback Aware không?

## 16. Tài liệu chính thức

- [Spring Framework Reference — Customizing the Nature of a Bean (ApplicationContextAware and BeanNameAware)](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework Reference — The BeanFactory API](https://docs.spring.io/spring-framework/reference/core/beans/beanfactory.html)
- [Spring Framework Reference — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Javadoc — BeanNameAware](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/BeanNameAware.html)
- [Spring Javadoc — BeanFactoryAware](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/BeanFactoryAware.html)
- [Spring Javadoc — ApplicationContextAware](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationContextAware.html)

# Phân biệt thay đổi BeanDefinition với xử lý thể hiện bean trong Spring Framework

## 1. Mục tiêu và vấn đề cần giải quyết

Một ứng dụng Spring có thể mở rộng cách container đăng ký, cấu hình và khởi tạo bean. Hai loại extension point đặc biệt dễ nhầm lẫn là **`BeanFactoryPostProcessor`** và **`BeanPostProcessor`**. Tên gọi chỉ khác một chữ `Factory`, nhưng chúng tác động lên hai đối tượng hoàn toàn khác nhau:

- **`BeanFactoryPostProcessor` (BFPP)** đọc/chỉnh **`BeanDefinition`**, tức metadata mà BeanFactory sử dụng để tạo object.
- **`BeanPostProcessor` (BPP)** nhận **bean instance** trong quá trình initialization và có thể quan sát, tùy biến hoặc thay thế tham chiếu trả về, thường bằng proxy.
- **`BeanDefinitionRegistryPostProcessor` (BDRPP)** mở rộng BFPP để đăng ký thêm bean definitions trong giai đoạn registry sớm.

Bài thuộc **Mở rộng định nghĩa** của Spring Framework Core Container. Sau khi học, bạn sẽ phân biệt đúng *definition-time* và *instance-time*, biết method và lifecycle của từng SPI, tự chạy ví dụ Java 17/Spring Framework 6.x kiểm chứng thứ tự, và tránh những lỗi do khởi tạo bean quá sớm.

## 2. BeanDefinition không phải là bean object

### 2.1. BeanDefinition là công thức

Spring lưu metadata tạo bean trong `org.springframework.beans.factory.config.BeanDefinition`. Tùy cách đăng ký (XML, `@Configuration`, `@Component`, `@Bean` hoặc code), definition có thể mang:

- Bean name, class hoặc factory method.
- Scope như `singleton`, `prototype`, `request`.
- Constructor arguments, `MutablePropertyValues` và metadata autowire.
- `lazyInit`, `dependsOn`, `primary`, qualifiers.
- Tên initialization/destruction methods.
- Attributes phục vụ những framework extension khác.

Ví dụ minh họa metadata, không phải file cấu hình hợp lệ:

~~~text
BeanDefinition name="clientService"
    beanClass="demo.ClientService"
    scope="singleton"
    propertyValues:
       endpoint="https://api.example.invalid"
    initMethod="initialize"
~~~

Chỉnh `endpoint` ở định nghĩa **trước khi instantiate** có thể khiến Spring dùng giá trị mới khi inject bean. Nhưng chỉnh metadata **sau khi singleton đã tạo** không có nghĩa object đó được tự động xây dựng lại hay property đang nằm trong object lập tức thay đổi.

### 2.2. Bean instance là object thật

~~~text
BeanDefinition (metadata)
      |
      | constructor/factory method, dependency resolution
      v
Java bean instance (target)
      |
      | BeanPostProcessor + initialization callbacks
      v
Reference Spring cung cấp cho consumer
      |
      +-- có thể chính instance gốc
      +-- hoặc proxy/wrapper do BPP tạo
~~~

BeanDefinition có thể dùng để tạo nhiều instances theo scope. BPP có thể xử lý từng instance; BFPP thay công thức chứ không phải từng object tạo ra sau đó.

### 2.3. So sánh nhanh

| Tiêu chí | `BeanFactoryPostProcessor` | `BeanPostProcessor` |
| --- | --- | --- |
| Đối tượng chính | BeanFactory và `BeanDefinition` | Bean instance |
| Thời điểm | Sau đăng ký metadata, trước khởi tạo các bean thường | Trong vòng đời khởi tạo mỗi bean |
| Method chính | `postProcessBeanFactory(...)` | `postProcessBeforeInitialization(...)` và `postProcessAfterInitialization(...)` |
| Có thể đổi property metadata? | Có | Không phải nhiệm vụ của nó |
| Có thể đổi reference trả ra? | Không nên đụng đến instance | Có, ví dụ trả proxy |
| Có được tự gọi `getBean()` không? | **Tránh:** có thể instantiate quá sớm | Có sẵn instance được truyền vào; vẫn cần tránh vòng phụ thuộc |
| Được chạy cho mỗi prototype instance? | Không; xử lý factory ở bootstrap | Có, khi prototype được tạo và đi qua processor |
| Ví dụ framework | `PropertySourcesPlaceholderConfigurer` | AOP auto-proxying, xử lý annotation/lifecycle |
| Phạm vi ảnh hưởng | BeanFactory/context tương ứng | Beans trong container tương ứng |

**Quy tắc chọn:** muốn thay đổi **công thức tạo bean**, dùng BFPP/BDRPP. Muốn thay đổi **object trong quá trình khởi tạo**, dùng BPP.

## 3. Trình tự mở rộng trong ApplicationContext.refresh()

Một mô hình giản lược:

~~~text
ApplicationContext.refresh()
    |
    +-- Chuẩn bị BeanFactory
    +-- Nạp / đăng ký BeanDefinitions
    |
    +-- BeanDefinitionRegistryPostProcessor
    |      postProcessBeanDefinitionRegistry(registry)
    |      -> thêm/chỉnh definitions ở registry phase
    |
    +-- BeanFactoryPostProcessor
    |      postProcessBeanFactory(beanFactory)
    |      -> thay metadata trước khi tạo beans thông thường
    |
    +-- Tạo và đăng ký BeanPostProcessors
    |
    +-- Tạo eager singleton beans
            |
            +-- Instantiate
            +-- Inject dependencies / populate properties
            +-- BPP before-initialization callbacks
            +-- Initialization callbacks
            +-- BPP after-initialization callbacks
            +-- Bean/proxy được sử dụng
    |
    +-- Kết thúc refresh()
~~~

Sơ đồ trên chỉ mô tả các mốc có ý nghĩa cho bài. Spring còn xử lý environment, factory method, merged definitions, BeanFactory aware callbacks và lifecycle infrastructure.

**Nuance quan trọng:** `@PostConstruct` được thực thi bởi một infrastructure BPP trong giai đoạn before-initialization. Không thể khẳng định callback `postProcessBeforeInitialization` của **mọi BPP tùy biến** đều chạy trước `@PostConstruct`, vì thứ tự giữa BPPs khác nhau được quyết định bởi ordering. `InitializingBean.afterPropertiesSet()` và custom `initMethod` được gọi trong logic initialization giữa nhóm before/after của BPP.

Ngoài interface BPP cơ bản còn có `InstantiationAwareBeanPostProcessor` và `SmartInstantiationAwareBeanPostProcessor` với các hook trước/sau instantiate và property population. Vì vậy câu “BPP chỉ có thể can thiệp sau khi constructor đã hoàn tất” là không đúng khi xét **cả họ SPI**. Hai method cốt lõi trình bày ở đây thực sự làm việc với instance đã được tạo.

## 4. BeanFactoryPostProcessor: xử lý configuration metadata

Interface `org.springframework.beans.factory.config.BeanFactoryPostProcessor` có phương thức:

~~~java
void postProcessBeanFactory(
    ConfigurableListableBeanFactory beanFactory);
~~~

Đây là chữ ký rút gọn, không phải chương trình Java độc lập.

### 4.1. Sửa BeanDefinition đúng cách

~~~java
@Override
public void postProcessBeanFactory(
        ConfigurableListableBeanFactory beanFactory) {

    BeanDefinition definition =
            beanFactory.getBeanDefinition("clientService");

    definition.getPropertyValues()
              .add("endpoint", "https://new.example.invalid");
}
~~~

Đây là **snippet class BFPP**: yêu cầu bean name `clientService` đã đăng ký và bean target có setter/property `endpoint` hợp lệ. Code không truy cập instance; chỉ thêm `PropertyValue` vào metadata. Khi bean chưa được tạo, container sử dụng giá trị đó ở bước property population.

Những thay đổi metadata có thể bao gồm constructor args, scope, lazy-init, property values và thuộc tính khác. Tuy nhiên phải tuân thủ semantics của BeanDefinition, tránh chỉnh class/factory method sang một loại không tương thích.

### 4.2. Anti-pattern: tạo bean ngay trong BFPP

~~~java
@Override
public void postProcessBeanFactory(
        ConfigurableListableBeanFactory factory) {

    ClientService service = factory.getBean(ClientService.class);
    service.setEndpoint("https://new.example.invalid");
}
~~~

Đây là **phản ví dụ**. `getBean()` có thể instantiate một singleton khi các BPPs chưa được đăng ký đầy đủ, dẫn đến:

1. Bean không được auto-proxying như những bean khác.
2. Dependency graph bị khởi tạo dây chuyền quá sớm.
3. Một số callback injection/initialization chưa được xử lý đúng.
4. Circular dependency hoặc trạng thái context chưa sẵn sàng.
5. Hành vi khác nhau tùy startup order.

Spring Reference trực tiếp khuyến cáo: BFPP nên làm việc với **bean configuration metadata**, không làm việc với bean instances. Nếu mục đích là thay object sau khi tạo, hãy viết BPP.

### 4.3. BFPP chạy lúc nào và bao nhiêu lần?

Trong một lần chuẩn bị BeanFactory của context, Spring gọi các BFPP thích hợp **trước khi tạo các non-processor beans bình thường**. Một BFPP không phải interceptor chạy trên mọi bean/mọi method call. Một definition prototype có thể được dùng để tạo hàng chục objects nhưng BFPP không chạy lại hàng chục lần vì nó không xử lý từng object.

Với nhiều `ApplicationContext` (parent/child), processors được áp dụng trong phạm vi BeanFactory mà chúng được đăng ký. Không giả định BFPP đặt ở parent tự sửa definitions của child.

### 4.4. BFPP sẵn có trong Spring

`PropertySourcesPlaceholderConfigurer` thường tham gia xử lý placeholders trong cấu hình bean. `CustomScopeConfigurer` đăng ký custom scopes trong giai đoạn BeanFactory post-processing. Các ví dụ này minh họa “mở rộng container trước khi bean business được tạo”, chứ không trực tiếp can thiệp từng instance sau startup.

## 5. BeanPostProcessor: xử lý bean instance

Interface `org.springframework.beans.factory.config.BeanPostProcessor` cung cấp:

~~~java
Object postProcessBeforeInitialization(
    Object bean, String beanName);

Object postProcessAfterInitialization(
    Object bean, String beanName);
~~~

Ở Spring Framework hiện đại, hai phương thức có default implementation trả lại `bean` không đổi. Code ví dụ có thể override một hoặc cả hai.

### 5.1. Before/after có nghĩa gì?

Với một bean điển hình:

~~~text
Constructor / factory method
       ↓
Dependency injection / property population
       ↓
BeanPostProcessor.beforeInitialization(bean, name)
       ↓
Spring initialization callbacks
       ↓
BeanPostProcessor.afterInitialization(bean, name)
       ↓
Reference được trả cho client
~~~

`BPP.postProcessBeforeInitialization` có thể kiểm tra trạng thái đã inject. `BPP.postProcessAfterInitialization` có thể kiểm tra trạng thái đã init hoặc trả proxy. Lưu ý `@PostConstruct` được một BPP xử lý nên vị trí tuyệt đối của annotation callback so với BPP tùy biến phụ thuộc thứ tự processors.

### 5.2. Giữ hay thay reference?

~~~java
@Override
public Object postProcessAfterInitialization(
        Object bean, String beanName) {
    if ("clientService".equals(beanName)) {
        // Kiểm tra, log hoặc wrap bean.
    }
    return bean; // Giữ nguyên tham chiếu.
}
~~~

Nếu muốn wrap, BPP có thể trả **proxy** đáp ứng hợp đồng injection. Đừng trả một object không tương thích với kiểu bean mà consumer yêu cầu. Spring AOP sử dụng các post-processors/autoproxy creators để chọn và tạo proxies trong quá trình xây dựng bean.

### 5.3. Không nhầm BPP với method interception

BPP callback chạy **khi tạo bean**, không phải mỗi lần code gọi business method. Nếu cần ghi log quanh mỗi `service.execute()`, phải có proxy/interceptor/AOP hoặc cơ chế tương đương; một BPP chỉ in log ở after-initialization không tự làm được điều đó.

Với bean prototype, mỗi object được tạo có thể được BPP xử lý. Với singleton, lần khởi tạo bình thường diễn ra một lần trong context; không phải mọi `getBean()` sau đó đều gọi lại BPP.

### 5.4. Loại và tên bean trong callback

BPP nhận `Object bean` cùng `String beanName`. Nên lọc:

~~~java
@Override
public Object postProcessAfterInitialization(
        Object bean, String name) {
    if ("clientService".equals(name)
            && bean instanceof ClientService service) {
        service.verifyConfiguration();
    }
    return bean;
}
~~~

Đây là snippet minh họa, giả định method `verifyConfiguration()` được định nghĩa. Đối với proxy hoặc objects của framework, kiểm tra bằng interface đôi khi ổn định hơn ép implementation class.

## 6. BeanDefinitionRegistryPostProcessor: thêm định nghĩa trước BFPP

`BeanDefinitionRegistryPostProcessor` (BDRPP) extends `BeanFactoryPostProcessor` và thêm:

~~~java
void postProcessBeanDefinitionRegistry(
    BeanDefinitionRegistry registry);
~~~

Nó dùng khi cần đăng ký/chỉnh nhiều definitions **ở giai đoạn registry** thay vì chỉ sửa metadata của những definitions đã tồn tại.

Ví dụ:

~~~java
public class ClientRegistrar
        implements BeanDefinitionRegistryPostProcessor {

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) {
        if (!registry.containsBeanDefinition("dynamicClient")) {
            registry.registerBeanDefinition(
                    "dynamicClient",
                    new RootBeanDefinition(DynamicClient.class));
        }
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
        // Không thay metadata thêm trong ví dụ này.
    }
}
~~~

Đây là **snippet mở rộng**, yêu cầu class `DynamicClient` và import các interface Spring tương ứng. Nó chưa phải file chạy độc lập.

### BDRPP vs BFPP

- **BDRPP** nhận một registry và có thể thêm definitions mới trước khi Spring tiếp tục xử lý các BFPPs.
- **BFPP** chủ yếu sửa metadata đang được BeanFactory quản lý.
- **BPP** chỉ nhìn thấy bean instance khi nó được tạo theo definition.

`ConfigurationClassPostProcessor` là ví dụ quan trọng của Spring về registry post-processor xử lý `@Configuration`, `@ComponentScan`, `@Import`, `@Bean`. Nếu tự làm dynamic registration, cân nhắc thứ tự so với processor này.

## 7. Ví dụ chạy độc lập: một BeanDefinition được chỉnh, một instance được xử lý

Ví dụ này không cần Spring Boot hoặc web server. Nó dùng **Java 17, Spring 6.2.9 và GenericApplicationContext**, đăng ký ba bean definitions:

1. `DefinitionEditor implements BeanFactoryPostProcessor`.
2. `InstanceTracer implements BeanPostProcessor`.
3. `MessageService implements InitializingBean`.

Processor thứ nhất chỉnh property `text` của `MessageService` **trước khi instance tồn tại**. Processor thứ hai in thông tin instance trước/sau initialization. Chương trình in ra trình tự đủ để tự kiểm chứng khác biệt.

### 7.1. Cây thư mục

~~~text
bean-extension-demo/
├── pom.xml
└── src/main/java/demo/
    └── DefinitionVsInstanceDemo.java
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-extension-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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

### 7.3. src/main/java/demo/DefinitionVsInstanceDemo.java

~~~java
package demo;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.support.GenericApplicationContext;

public class DefinitionVsInstanceDemo {

    public static void main(String[] args) {
        try (GenericApplicationContext context =
                     new GenericApplicationContext()) {

            context.registerBean("messageService", MessageService.class);
            context.registerBean("definitionEditor", DefinitionEditor.class);
            context.registerBean("instanceTracer", InstanceTracer.class);

            context.refresh();

            MessageService service =
                    context.getBean("messageService", MessageService.class);
            System.out.println("result: " + service.getText());
        }
    }

    public static class MessageService implements InitializingBean {
        private String text;

        public MessageService() {
            System.out.println("construct: MessageService");
        }

        public void setText(String text) {
            this.text = text;
            System.out.println("setter: " + text);
        }

        public String getText() {
            return text;
        }

        @Override
        public void afterPropertiesSet() {
            System.out.println("init: " + text);
        }
    }

    public static class DefinitionEditor
            implements BeanFactoryPostProcessor {

        @Override
        public void postProcessBeanFactory(
                ConfigurableListableBeanFactory beanFactory) {

            BeanDefinition definition =
                    beanFactory.getBeanDefinition("messageService");

            definition.getPropertyValues()
                    .add("text", "from-definition");

            System.out.println("BFPP: definition changed");
        }
    }

    public static class InstanceTracer implements BeanPostProcessor {

        @Override
        public Object postProcessBeforeInitialization(
                Object bean, String beanName) {

            if ("messageService".equals(beanName)) {
                MessageService service = (MessageService) bean;
                System.out.println("BPP before: " + service.getText());
            }
            return bean;
        }

        @Override
        public Object postProcessAfterInitialization(
                Object bean, String beanName) {

            if ("messageService".equals(beanName)) {
                MessageService service = (MessageService) bean;
                System.out.println("BPP after: " + service.getText());
            }
            return bean;
        }
    }
}
~~~

Tất cả Java classes là nested `public static` trong một file đúng tên. `GenericApplicationContext.registerBean(...)` đăng ký bean definitions. Khi `refresh()`, Spring tự phát hiện hai processor beans, tạo/chạy chúng ở giai đoạn hạ tầng rồi mới pre-instantiate `MessageService`.

### 7.4. Biên dịch và chạy

Từ thư mục `bean-extension-demo`:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=demo.DefinitionVsInstanceDemo
~~~

**Stdout của chương trình** (không tính log Maven/SLF4J tùy môi trường):

~~~text
BFPP: definition changed
construct: MessageService
setter: from-definition
BPP before: from-definition
init: from-definition
BPP after: from-definition
result: from-definition
~~~

### 7.5. Vì sao đúng thứ tự này?

1. `DefinitionEditor.postProcessBeanFactory(...)` được gọi lúc metadata đã được đăng ký, trước constructor của `MessageService`. In `BFPP: definition changed`.
2. Spring tạo instance của `MessageService`, in `construct: MessageService`.
3. Spring populate property từ BeanDefinition sau khi BFPP sửa, setter in `setter: from-definition`.
4. `InstanceTracer.postProcessBeforeInitialization(...)` thấy object và field đã có giá trị, in `BPP before: from-definition`.
5. Spring gọi `InitializingBean.afterPropertiesSet()`, in `init: from-definition`.
6. `InstanceTracer.postProcessAfterInitialization(...)` nhận object sau init, in `BPP after: from-definition`.
7. `context.getBean(...)` nhận instance đã khởi tạo, in `result: from-definition`.

BPP trong ví dụ chỉ quan sát bean và trả cùng reference; để thay reference bằng proxy cần hạ tầng proxy phù hợp (JDK dynamic proxy/CGLIB). Đó là một ví dụ instance processing khác, không thuộc việc BFPP chỉnh BeanDefinition.

### 7.6. Tự thử thay đổi

**Thử A — bỏ BFPP:** bỏ registration `definitionEditor`. `MessageService` vẫn được tạo; `text` không có giá trị được inject, kết quả getter là `null`. BPP vẫn quan sát trước/sau init.

**Thử B — bỏ BPP:** bỏ registration `instanceTracer`. BFPP vẫn chỉnh metadata; constructor/setter/`afterPropertiesSet()` vẫn hoạt động nhưng không có hai dòng BPP.

**Thử C — sửa metadata:** đổi `"from-definition"` thành `"configured-v2"`. Giá trị mới xuất hiện trong setter, initialization, BPP và result mà không cần BFPP gọi `getBean()`.

**Thử D — prototype:** đăng ký `messageService` với scope `prototype` trước refresh. BFPP vẫn sửa **một definition**, còn mỗi lần `getBean()` tạo target prototype mới sẽ được BPP xử lý.

**Thử E — proxy:** thay after-init BPP trả một object implement interface mà client inject. Không trả một JDK proxy chỉ implement interface vào injection point yêu cầu concrete class vì type mismatch.

## 8. Đăng ký processors bằng @Configuration và @Bean

### 8.1. BFPP dưới dạng static @Bean

~~~java
@Configuration
class ExtensionConfig {

    @Bean
    static BeanFactoryPostProcessor definitionEditor() {
        return factory -> {
            BeanDefinition def =
                    factory.getBeanDefinition("messageService");
            def.getPropertyValues().add("text", "configured");
        };
    }
}
~~~

Đây là **cấu hình minh họa**, đòi import `@Configuration`, `@Bean`, `BeanFactoryPostProcessor`, `BeanDefinition`, và BeanDefinition `messageService` có property `text`. `BeanFactoryPostProcessor` là functional interface nên lambda hợp lệ.

Spring Reference khuyến nghị khai báo `@Bean` trả BFPP là **`static`**. BFPP cần được khởi tạo từ rất sớm; nếu factory method là instance method trên `@Configuration`, Spring có thể phải tạo configuration class trước khi annotation processing hoàn tất, dẫn đến các trường `@Autowired`, `@Value` hoặc `@PostConstruct` trong class đó bị xử lý không như kỳ vọng.

### 8.2. BPP dưới dạng static @Bean

~~~java
@Configuration
class ExtensionConfig {

    @Bean
    static InstanceTracer instanceTracer() {
        return new InstanceTracer();
    }
}
~~~

Đây là snippet sử dụng `InstanceTracer` của chương trình mục 7. Với BPP, Spring cũng khuyên `static @Bean` và **return type phải đủ cụ thể** (implementation hoặc ít nhất `BeanPostProcessor`) để phát hiện sớm bằng type. Trả `Object` từ factory method khiến container khó nhận diện trước lúc tạo và có thể dẫn đến BPP đăng ký quá muộn.

**Không phải mọi `@Bean` đều phải static**. Khuyến nghị trên tập trung vào các bean hạ tầng đặc biệt được khởi tạo trước các business beans.

### 8.3. Early-instantiation và cảnh báo “not eligible”

Một `BeanPostProcessor` hoặc bean nó inject trực tiếp thường phải được tạo sớm trong quá trình Spring đăng ký processors. Bean business bị kéo vào quá sớm có thể chưa đủ điều kiện nhận **toàn bộ BPP**, đặc biệt AOP auto-proxying.

Log điển hình:

~~~text
Bean 'someBean' of type [...] is not eligible for getting
processed by all BeanPostProcessors
(for example: not eligible for auto-proxying)
~~~

Hướng giải quyết không phải tắt log, mà xem xét **phụ thuộc của processor**, tránh inject business beans vào BPP quá sớm, và dùng static factory method không cần dependency khi khả thi.

### 8.4. Đăng ký programmatic

BFPP trước refresh:

~~~java
context.addBeanFactoryPostProcessor(
        beanFactory -> {
            BeanDefinition definition =
                    beanFactory.getBeanDefinition("messageService");
            definition.getPropertyValues()
                      .add("text", "configured");
        });
~~~

Đây là snippet trong method có `context` phù hợp, không phải class độc lập.

BPP cũng có thể đăng ký:

~~~java
beanFactory.addBeanPostProcessor(new InstanceTracer());
~~~

**Điểm khác:** BPP được thêm bằng `addBeanPostProcessor(...)` theo **registration order**, không được sắp xếp lại tự động bởi `Ordered`; các BPP programmatically registered được chạy trước BPP tự động phát hiện. Do đó nếu cần xử lý thứ tự chính xác, phải biết con đường registration, không chỉ thêm annotation `@Order`.

## 9. Ordering: PriorityOrdered, Ordered và tương tác processors

### 9.1. BFPP/BDRPP

Spring dùng `PriorityOrdered`, `Ordered` và thứ tự phase đặc biệt để sắp xếp những processors phát hiện được từ definitions. `BeanDefinitionRegistryPostProcessor` registry callbacks được xử lý sớm, rồi các BFPP callbacks. Spring có thể tiếp tục phát hiện BDRPP mới được đăng ký bởi BDRPP khác.

Nếu hai processors cùng viết lên property `text`, kết quả phụ thuộc thứ tự. Production code nên tránh xung đột vô tình, hoặc xác định precedence minh bạch.

### 9.2. BPP

Với auto-detected `BeanPostProcessor` beans, có thể dùng `Ordered`/`PriorityOrdered` để tham gia sắp xếp. BPP sau trong chain nhận reference do BPP trước trả về; nếu trước đó đã có JDK proxy, ép kiểu implementation ở BPP sau có thể không hợp lệ.

Đừng giả định BPP before-init của mình sẽ luôn chạy trước `@PostConstruct`: `@PostConstruct` nằm trong hệ thống callback của một infrastructure BPP. Thứ tự chi tiết có thể phụ thuộc version/processor priorities.

### 9.3. Con đường registration ảnh hưởng thứ tự

Khi auto-detect BPP beans, Spring có bước sorting. Khi `ConfigurableBeanFactory.addBeanPostProcessor` trực tiếp, thứ tự gọi chi phối và các BPP đó có độ ưu tiên trước auto-detected BPPs. Lời giải “chỉ cần thêm `@Order(1)`” có thể không có tác dụng như mong đợi với programmatic registration.

## 10. Khi BeanDefinitionRegistryPostProcessor bổ sung definitions

Một plugin framework có thể cần scan nhiều implementation classes rồi đăng ký definitions theo cấu hình. Khi đó:

~~~text
BDRPP → registerBeanDefinition("connectorA")
      ↓
BFPP → chỉnh property/metadata của "connectorA"
      ↓
BeanFactory → tạo instance "connectorA"
      ↓
BPP → kiểm tra/wrap instance
      ↓
Client sử dụng
~~~

Ba extension points **bổ trợ** nhau. Một design hợp lý đưa phần đăng ký/cấu hình vào BDRPP/BFPP và phần quan sát/wrapping runtime vào BPP.

Nếu chỉ cần khai báo một service đơn giản, hãy dùng `@Bean`/`@Component` thay vì xây dựng BDRPP riêng. Mở rộng registry nên là giải pháp cho **hạ tầng đăng ký động hoặc framework integration** thật sự.

## 11. Quan hệ với BeanFactory, FactoryBean và AOP

Các tên gần nhau nhưng vai trò khác nhau:

| Interface | Vai trò |
| --- | --- |
| `BeanFactory` | Container truy xuất/quản lý beans |
| `FactoryBean<T>` | Bean đặc biệt cung cấp **sản phẩm object** qua `getObject()` |
| `BeanFactoryPostProcessor` | Can thiệp metadata BeanDefinition của BeanFactory |
| `BeanDefinitionRegistryPostProcessor` | Thêm/chỉnh bean definitions sớm trong registry |
| `BeanPostProcessor` | Can thiệp vào bean instance trong lifecycle |
| Spring AOP auto-proxy creator | Hạ tầng thường thuộc họ BPP, quyết định và trả proxy |

**Không nhầm `FactoryBean` với BFPP:** một FactoryBean dùng để tạo product; BFPP sửa cấu hình. Một FactoryBean cũng có BeanDefinition và bản thân product của nó có lifecycle, nhưng không phải vì tên “Factory” mà hai SPI tương đương.

Một AOP proxy có thể được tạo sau khi instance được initialize; metadata như annotations và pointcut giúp quyết định đối tượng nào nên được proxy. Đây là minh họa tốt cho sự hợp tác giữa **definition/metadata** và **instance processing**.

## 12. Những tình huống nên chọn extension nào?

### Tình huống A: thay endpoint cho nhiều beans khi startup

Chọn **BFPP** nếu dữ liệu cần thay nằm trong BeanDefinition và phải được chỉnh trước instantiation. Tránh gọi `getBean()` trong BFPP để sửa setter trên instance.

Nếu yêu cầu chỉ là binding properties thông thường, `@ConfigurationProperties`, `@Value` hoặc cấu hình `@Bean` trực tiếp có thể đơn giản hơn và dễ bảo trì hơn một BFPP tùy biến.

### Tình huống B: tạo bean definitions từ plugin descriptors

Chọn **BDRPP**, vì số lượng/names/types bean chưa biết khi viết cấu hình gốc và phải đăng ký vào registry.

### Tình huống C: kiểm tra hoặc decorate bean sau khi khởi tạo

Chọn **BPP**. Ví dụ kiểm tra một marker interface sau injection, thêm custom proxy, logging hoặc instrumentation trong lifecycle.

### Tình huống D: thay property của một singleton đang phục vụ

**Không** kỳ vọng BFPP runtime tự làm mới instance. Khi singleton đã tồn tại, BeanDefinition là metadata tạo bean ban đầu. Thiết kế một API reconfigure có đồng bộ, refresh scope có contract cụ thể hoặc replaceable delegate phù hợp.

### Tình huống E: mỗi lần gọi business method phải có logging

**Không** chỉ dùng BPP callback logging ở startup. Dùng Spring AOP proxy/interceptor hoặc code nghiệp vụ phù hợp. BPP có thể đóng vai trò **tạo proxy**, nhưng bản thân callback không được chạy mỗi lần method invocation.

### Tình huống F: một @Bean trả BPP bị khai báo Object

Spring có thể không phát hiện sớm BPP bằng type từ factory method. Trả đúng type BPP/implementation và cân nhắc `static @Bean`.

## 13. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| BFPP đã chỉnh metadata nhưng singleton không đổi | Bean đã được tạo/cached | Thực hiện mutation trước instance creation |
| AOP annotation không có tác dụng | Gọi `getBean()` quá sớm trong BFPP hoặc BPP dependency kéo bean vào startup | Tránh eager instantiation, kiểm tra processor ordering |
| Log “not eligible for getting processed by all BeanPostProcessors” | Bean được instantiate trong lúc đăng ký BPPs | Giảm dependencies của BPP; ưu tiên static @Bean |
| Non-static `@Bean` trả BFPP gây lifecycle conflict | Configuration class bị tạo quá sớm | Dùng static factory method |
| BeanPostProcessor không chạy | BPP không được Spring đăng ký/phát hiện bằng return type | Register đúng bean, return type rõ |
| BPP đã chạy nhưng không thấy proxy | Implementation trả lại target, không tạo proxy; hoặc bean được tạo sớm | Kiểm tra after-init return value và auto-proxy infra |
| `@PostConstruct` diễn ra trước BPP tùy biến | Thứ tự các BPP, bởi `@PostConstruct` do BPP xử lý | Đừng áp một ordering giả định cho mọi BPP |
| BFPP tìm BeanDefinition báo không có | Sai bean name/context hoặc definition chưa được register | Dùng `containsBeanDefinition` và đúng registry phase |
| BDRPP tạo name trùng | Không kiểm tra registry hoặc cố override | Kiểm tra `containsBeanDefinition` và naming strategy |
| Hai BFPP sửa một property ra giá trị khó hiểu | Thứ tự processor không xác định theo ý đồ | Dùng ordering rõ và tránh xung đột |
| BPP trả wrapper không cùng injection type | Proxy không implement API mà consumer cần | Dùng interface/class proxy tương thích |
| `@Order` không đổi thứ tự BPP thủ công | `addBeanPostProcessor` dùng registration order | Sửa trình tự đăng ký |
| Processor ở parent không xử lý child beans | Extension points per-container | Đăng ký vào đúng child context |
| Truyền property name sai vào BeanDefinition | Không có setter/writable property phù hợp | Kiểm tra property metadata, constructor args và type conversion |
| Mỗi `getBean()` kỳ vọng BPP chạy lại | Bean singleton đã cache | Phân biệt per-instance initialization và per-method interception |

### Cách chẩn đoán có hệ thống

1. Việc cần thực hiện ảnh hưởng **metadata** hay **instance**?
2. Với metadata: BeanDefinition đã được register tại đúng context và tên chưa?
3. Có cần bổ sung definition mới (BDRPP) hay chỉ sửa definition hiện có (BFPP)?
4. Có bean nào bị tạo sớm hơn lúc BPP được đăng ký không?
5. Nếu BPP trả proxy, reference và type mà consumer nhận có còn tương thích không?
6. Có nhiều processors với ordering khác nhau không?
7. Context có parent/child hoặc prototype scope ảnh hưởng số lần callback không?

## 14. Kiểm thử chuẩn cho cả hai SPI

### 14.1. Unit test metadata

Dùng `DefaultListableBeanFactory` và một `RootBeanDefinition`:

~~~java
DefaultListableBeanFactory factory =
        new DefaultListableBeanFactory();

factory.registerBeanDefinition(
        "messageService",
        new RootBeanDefinition(MessageService.class));

new DefinitionEditor().postProcessBeanFactory(factory);

Object text = factory.getBeanDefinition("messageService")
        .getPropertyValues()
        .getPropertyValue("text")
        .getValue();

if (!"from-definition".equals(text)) {
    throw new AssertionError("Definition was not updated");
}
~~~

Đây là **snippet unit test**, cần imports và các nested types của mục 7, không phải file chạy độc lập. Nó chứng minh BFPP cập nhật BeanDefinition nhưng chưa chứng minh BPP được Spring gọi.

### 14.2. Unit test instance callback

Tạo `MessageService`, set state rồi gọi `InstanceTracer.postProcessBeforeInitialization`/`postProcessAfterInitialization` thủ công, kiểm tra reference được trả về. Logic processor được kiểm tra nhưng test này chưa chứng minh Spring tự động đăng ký BPP.

### 14.3. Integration test

Chạy `GenericApplicationContext` như ví dụ chính:

- BFPP chạy trước khi target constructor được gọi.
- BeanDefinition property được áp dụng bởi setter.
- BPP before và after bao quanh `InitializingBean.afterPropertiesSet()`.
- Chỉ bean name được chọn mới in log.
- Chuyển sang prototype thì từng instance được xử lý.
- Thay BPP trả proxy thì kiểu injection phải còn tương thích.
- Đăng ký BFPP/BPP ở đúng context, không gây early-instantiation.
- Nếu dùng BDRPP, definitions mới phải xuất hiện ở BFPP stage và có thể được instantiate bình thường.

Dùng `try-with-resources` để đóng context test nhằm giải phóng singleton resources.

## 15. Checklist dùng trong dự án thật

- [ ] Chỉnh **BeanDefinition** → `BeanFactoryPostProcessor`.
- [ ] Đăng ký **definitions mới** → `BeanDefinitionRegistryPostProcessor`.
- [ ] Xử lý **bean instance** → `BeanPostProcessor`.
- [ ] Không gọi `getBean()` trong BFPP để sửa object.
- [ ] Processor beans được phát hiện/đăng ký trước khi business beans được instantiate.
- [ ] Dùng `static @Bean` cho BFPP/BPP theo hướng dẫn Spring khi cần đăng ký hạ tầng sớm.
- [ ] Cấu hình rõ ordering (`PriorityOrdered`/`Ordered`) khi nhiều processors tương tác.
- [ ] Không giả định mọi BPP before-init luôn chạy trước `@PostConstruct`.
- [ ] Không chỉnh metadata muộn rồi kỳ vọng singleton đang sống tự thay đổi.
- [ ] Không lạm dụng BFPP/BDRPP cho nhu cầu cấu hình đơn giản.
- [ ] Unit test metadata và instance riêng; integration test xác nhận lifecycle đầy đủ.

## 16. Tự kiểm tra

**Câu 1.** Bạn cần đổi default property của 50 beans trước khi chúng được tạo. Chọn SPI nào?  
**Đáp:** BeanFactoryPostProcessor, vì cần đổi BeanDefinition metadata.

**Câu 2.** Bạn cần wrap một bean bằng proxy sau initialization. Chọn SPI nào?  
**Đáp:** BeanPostProcessor (hoặc hạ tầng AOP dựa trên BPP).

**Câu 3.** Vì sao BFPP không nên gọi `getBean()`?  
**Đáp:** Nó có thể khởi tạo bean khi BPP chưa đăng ký đủ, gây thiếu proxying/lifecycle và phát sinh dependency cycles.

**Câu 4.** BeanDefinitionRegistryPostProcessor khác BFPP thế nào?  
**Đáp:** Nó có registry callback chạy sớm để thêm/chỉnh bean definitions, đồng thời vẫn là BFPP.

**Câu 5.** Mỗi lần lấy singleton qua `getBean()`, BPP có chạy lại không?  
**Đáp:** Không. BPP xử lý instance khi tạo/khởi tạo. Một singleton thông thường chỉ được khởi tạo một lần trong context.

**Câu 6.** @PostConstruct luôn xảy ra sau tất cả BPP before-initialization callbacks đúng không?  
**Đáp:** Không. @PostConstruct được một infrastructure BPP xử lý, nên thứ tự tương đối với BPP khác còn tùy ordering.

**Câu 7.** Vì sao khi khai báo @Bean trả BFPP nên đặt method static?  
**Đáp:** Vì BFPP được tạo rất sớm; static method tránh khởi tạo @Configuration instance khi annotation processors chưa sẵn sàng.

**Câu 8.** Một BPP đăng ký thủ công bằng addBeanPostProcessor có dùng @Order giống BPP auto-detected không?  
**Đáp:** Không theo cách đó; registration order chi phối BPP programmatic.

**Câu 9.** Khi đổi scope của BeanDefinition sau khi singleton đã được tạo, object cũ có biến thành prototype không?  
**Đáp:** Không. Metadata thay đổi muộn không tự thay thế singleton instance đã cache.

**Câu 10.** BFPP và BPP tự động ảnh hưởng tất cả beans của parent và child ApplicationContexts chứ?  
**Đáp:** Không. Extension processors hoạt động trong phạm vi container tương ứng.

## Tài liệu chính thức

- [Spring Framework Reference — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): BFPP/BPP/ordering/early-instantiation.
- [Spring Framework Reference — Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): BeanDefinition là recipe.
- [Spring Framework Reference — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html).
- [Spring Framework Javadoc — BeanFactoryPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/config/BeanFactoryPostProcessor.html).
- [Spring Framework Javadoc — BeanPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/config/BeanPostProcessor.html).
- [Spring Framework Javadoc — BeanDefinitionRegistryPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionRegistryPostProcessor.html).

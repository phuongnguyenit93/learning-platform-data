# BeanFactoryPostProcessor và thay đổi metadata trước khi tạo bean

Trong Spring, container không tạo bean ngay khi đọc thấy một class Java. Trước khi khởi tạo các singleton thông thường, Spring thu thập thông tin mô tả cách tạo bean, dependency, scope, thuộc tính và các tùy chọn khác. Thông tin đó được lưu trong **BeanDefinition**. Nhờ vậy, framework có thể điều chỉnh cách một bean sẽ được tạo trước khi object thật sự xuất hiện.

**BeanFactoryPostProcessor (BFPP)** là extension point cho phép ứng dụng hoặc framework đọc và thay đổi metadata của bean trong giai đoạn này. Ví dụ, một post-processor có thể đổi một bean thành lazy-init, thêm property value vào định nghĩa bean hoặc tùy chỉnh một số thiết lập của BeanFactory.

Điểm cốt lõi của bài học là phân biệt:

- **BeanDefinition:** bản mô tả bean, chưa phải object bean.
- **BeanFactoryPostProcessor:** xử lý metadata trong BeanFactory trước khi các bean thông thường được tạo.
- **BeanPostProcessor:** can thiệp vào object bean trong quá trình khởi tạo, trước hoặc sau initialization callbacks.

Hiểu ba khái niệm này giúp bạn biết khi nào cần thay đổi cách Spring sẽ tạo bean và khi nào cần xử lý chính object sau khi nó đã được tạo.

## 1. Từ class Java tới bean instance

Giả sử có service:

~~~java
@Service
public class ReportService {

    public void generate() {
        // Tạo báo cáo.
    }
}
~~~

Spring không chỉ nhìn class này rồi lập tức gọi constructor. Trong quá trình đọc cấu hình, component scanning và phân tích annotation, container tạo một **BeanDefinition** mô tả cách đăng ký bean tương ứng.

BeanDefinition có thể chứa những thông tin như:

- Tên bean và class được dùng để tạo bean (nếu biết trực tiếp).
- Factory bean hoặc factory method nếu object được tạo qua phương thức **@Bean**.
- Scope: singleton, prototype, request hoặc scope tùy chỉnh.
- Lazy initialization.
- Constructor arguments và property values.
- Các dependency hoặc quan hệ **depends-on**.
- Cờ **primary**, **autowire candidate** và những metadata khác.
- Một số thuộc tính liên quan đến role, description và nguồn định nghĩa.

Luồng khái quát:

~~~text
Class Java / @Bean / XML / auto-configuration
                    │
                    ▼
             BeanDefinition
             (metadata)
                    │
                    ▼
        BeanFactoryPostProcessor
        có thể thay đổi metadata
                    │
                    ▼
          BeanFactory tạo object
                    │
                    ▼
             Bean instance
                    │
                    ▼
       Dependency injection và lifecycle
~~~

**BeanDefinition là bản mô tả; bean instance là object thật trong bộ nhớ.** BFPP làm việc chủ yếu với bản mô tả để thay đổi cách object sẽ được tạo hoặc cấu hình.

## 2. BeanFactoryPostProcessor là gì?

**BeanFactoryPostProcessor** là interface của Spring với một phương thức:

~~~java
void postProcessBeanFactory(
        ConfigurableListableBeanFactory beanFactory);
~~~

Phương thức nhận **ConfigurableListableBeanFactory**, cho phép post-processor truy cập những bean definition đã được đăng ký và tùy chỉnh metadata trước khi các bean thông thường được khởi tạo.

Một triển khai tối giản:

~~~java
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;

public class ApplicationMetadataProcessor
        implements BeanFactoryPostProcessor {

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
        // Đọc hoặc thay đổi bean definitions tại đây.
    }
}
~~~

Spring phát hiện bean BFPP và gọi phương thức này trong quá trình refresh ApplicationContext. Mục tiêu là xử lý cấu hình BeanFactory **trước khi các bean ứng dụng thông thường được tạo**.

Có một chi tiết cần nhớ: bản thân các post-processor phải được tạo đủ sớm để thực hiện công việc của chúng. Vì thế BFPP là một nhóm bean hạ tầng đặc biệt trong quá trình startup. Không nên xem nó như một service bình thường có thể phụ thuộc tùy ý vào mọi bean khác.

### BFPP làm được gì?

- Lấy bean definition theo tên và đọc metadata.
- Thay đổi scope, lazy-init, primary hoặc các thuộc tính phù hợp khác.
- Thêm/sửa property values sẽ được áp dụng khi bean được tạo.
- Thay đổi một số cấu hình của BeanFactory.
- Hỗ trợ các cơ chế xử lý placeholder và metadata mà framework cần.

### BFPP không phải công cụ để sửa object đã được tạo

Nếu một singleton đã được khởi tạo, thay đổi **BeanDefinition** sau đó không tự sửa field trong object hiện tại. BFPP được thiết kế để chạy ở giai đoạn sớm, trước khi phần lớn bean thông thường được tạo.

Nếu muốn xử lý object instance sau khi tạo, hãy xem **BeanPostProcessor**. Nếu muốn thay đổi một giá trị cấu hình khi ứng dụng đang chạy, hãy dùng cơ chế quản lý cấu hình động riêng phù hợp; sửa BeanDefinition không phải cách reload trạng thái runtime.

## 3. Thời điểm BFPP chạy trong quá trình khởi động

Trong một ApplicationContext thông thường, các bước lớn có thể hình dung:

~~~text
1. Tạo ApplicationContext và chuẩn bị Environment
                  │
                  ▼
2. Đọc cấu hình và đăng ký BeanDefinitions
   - @Configuration
   - @ComponentScan
   - @Bean
   - auto-configuration
                  │
                  ▼
3. BeanDefinitionRegistryPostProcessor
   - có thể đăng ký thêm BeanDefinitions
   - xử lý registry trước BFPP thông thường
                  │
                  ▼
4. BeanFactoryPostProcessor
   - điều chỉnh BeanFactory / BeanDefinition metadata
                  │
                  ▼
5. Đăng ký BeanPostProcessor
                  │
                  ▼
6. Khởi tạo các singleton eager còn lại
   - constructor
   - dependency injection
   - initialization callbacks
                  │
                  ▼
7. ApplicationContext hoàn tất refresh
~~~

Đây là sơ đồ khái quát để hiểu vị trí của BFPP. Một số thành phần hạ tầng như **ConfigurationClassPostProcessor**, các post-processor và bean phục vụ quá trình khởi tạo được tạo ở giai đoạn sớm theo quy trình riêng của container.

**BFPP chạy sau khi những bean definition liên quan đã được nạp và trước khi các singleton ứng dụng thông thường được khởi tạo.** Nhờ vậy, nó có thể sửa metadata mà BeanFactory sẽ dùng về sau.

### Vì sao phải xử lý trước khi tạo bean?

Giả sử muốn đặt **ReportService** thành lazy-init. Nếu service đã được tạo, thay cờ lazy-init trong metadata không làm object biến mất khỏi bộ nhớ hay khiến Spring trì hoãn việc tạo lại. Vì vậy, thay đổi cần xảy ra khi BeanFactory còn đang chuẩn bị việc khởi tạo bean.

Tương tự, nếu cần thêm property value vào BeanDefinition, giá trị phải có mặt trước khi container thực hiện property population cho object tương ứng.

## 4. Ví dụ 1: đổi bean thành lazy-init

Một bean có thể được đánh dấu lazy bằng annotation:

~~~java
@Service
@Lazy
public class ReportService {
}
~~~

Hoặc cấu hình metadata qua BFPP. Giả sử component được đăng ký với bean name **reportService**:

~~~java
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetadataConfiguration {

    @Bean
    static BeanFactoryPostProcessor makeReportServiceLazy() {
        return beanFactory -> {
            String beanName = "reportService";

            if (beanFactory.containsBeanDefinition(beanName)) {
                BeanDefinition definition =
                        beanFactory.getBeanDefinition(beanName);
                definition.setLazyInit(true);
            }
        };
    }
}
~~~

Trong ví dụ:

1. Component scan đăng ký BeanDefinition cho **ReportService**.
2. Spring gọi BFPP trước khi tạo các singleton eager thông thường.
3. BFPP lấy metadata bằng **getBeanDefinition("reportService")**.
4. **setLazyInit(true)** yêu cầu BeanFactory trì hoãn tạo singleton đó cho tới khi được yêu cầu.

**Lazy-init không có nghĩa bean sẽ không bao giờ được tạo.** Nếu một singleton eager khác cần **ReportService** qua constructor, Spring vẫn phải tạo dependency đó khi khởi tạo bean phụ thuộc. Lazy-init trì hoãn việc tạo bean cho tới khi nó được yêu cầu, nhưng dependency bắt buộc của một bean eager có thể khiến nó được tạo sớm.

Tên bean trong ví dụ cần khớp với tên đã đăng ký. Với component có tên mặc định, Spring thường chuyển tên class sang dạng bean name bắt đầu bằng chữ thường; có thể khai báo tên rõ ràng bằng **@Service("reportService")** để tránh phụ thuộc vào quy tắc đặt tên.

## 5. Ví dụ 2: thay đổi property values trong BeanDefinition

BFPP cũng có thể bổ sung property value sẽ được áp dụng khi object được tạo.

Bean ứng dụng:

~~~java
import org.springframework.stereotype.Component;

@Component("batchProcessor")
public class BatchProcessor {

    private int batchSize = 50;

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }

    public int getBatchSize() {
        return batchSize;
    }
}
~~~

Post-processor:

~~~java
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BatchMetadataConfiguration {

    @Bean
    static BeanFactoryPostProcessor configureBatchSize() {
        return beanFactory -> {
            String beanName = "batchProcessor";

            if (beanFactory.containsBeanDefinition(beanName)) {
                BeanDefinition definition =
                        beanFactory.getBeanDefinition(beanName);

                definition.getPropertyValues()
                        .add("batchSize", 200);
            }
        };
    }
}
~~~

Khi **BatchProcessor** được tạo, Spring áp dụng property value **batchSize = 200** thông qua setter. Giá trị mặc định **50** trong class được thay bằng giá trị từ metadata.

Điều kiện để ví dụ hoạt động:

- Bean definition phải tồn tại với tên **batchProcessor** trước khi BFPP chạy.
- Class phải có writable property tương ứng, ở đây là **setBatchSize(int)**.
- Kiểu giá trị phải chuyển đổi được sang kiểu property.
- BFPP phải chạy trước khi bean được tạo.

Ví dụ này minh họa việc thay đổi **metadata**, không phải gọi **setBatchSize(200)** trực tiếp trên một bean instance. Tại thời điểm BFPP chạy, ta đang thay đổi danh sách property values mà BeanFactory sẽ áp dụng trong quá trình tạo object.

### Khi nào nên dùng property value trong BFPP?

Đây là kỹ thuật cấp hạ tầng. Trong code ứng dụng thông thường, **@ConfigurationProperties**, **@Value**, constructor injection hoặc một factory method rõ ràng thường dễ đọc hơn. BFPP phù hợp khi cần biến đổi metadata một cách có hệ thống, chẳng hạn framework nội bộ hoặc thư viện tích hợp cần điều chỉnh bean definition của nhiều component.

## 6. BeanDefinition chứa những metadata nào?

BeanDefinition là abstraction mô tả cách container tạo và cấu hình bean. Những thuộc tính thường gặp:

| Metadata | Ý nghĩa |
|---|---|
| **beanClassName / bean class** | Class được dùng để tạo bean nếu xác định trực tiếp |
| **scope** | Phạm vi instance, ví dụ singleton hoặc prototype |
| **lazyInit** | Có trì hoãn khởi tạo bean hay không |
| **primary** | Bean có được ưu tiên khi resolve dependency đơn hay không |
| **autowireCandidate** | Bean có đủ điều kiện làm ứng viên autowiring hay không |
| **dependsOn** | Những bean cần được khởi tạo trước |
| **propertyValues** | Các giá trị sẽ được gán vào bean properties |
| **constructorArgumentValues** | Giá trị/tham số dùng khi tạo bean qua constructor |
| **factoryBeanName / factoryMethodName** | Factory bean hoặc factory method tạo object |
| **initMethodName / destroyMethodName** | Phương thức lifecycle tùy chỉnh |
| **role / description** | Thông tin mô tả vai trò và nguồn định nghĩa |

Không phải mọi BeanDefinition đều chứa đầy đủ tất cả thông tin này. Ví dụ, bean được tạo qua factory method có thể không khai báo trực tiếp class của object theo cùng cách với bean định nghĩa bằng class name.

### BFPP có thể thay đổi nhiều loại metadata

Ví dụ, thay đổi scope:

~~~java
definition.setScope(BeanDefinition.SCOPE_PROTOTYPE);
~~~

Hoặc đánh dấu bean primary:

~~~java
definition.setPrimary(true);
~~~

Hoặc không cho bean làm autowire candidate:

~~~java
definition.setAutowireCandidate(false);
~~~

Những dòng trên chỉ minh họa các API metadata. Không nên tùy tiện thay scope hoặc autowire candidate của bean ứng dụng chỉ vì có thể làm được. Scope ảnh hưởng trực tiếp tới số lượng instance, state và lifecycle; thay đổi metadata có thể làm hành vi của cả hệ thống khác đi.

## 7. BeanFactoryPostProcessor khác BeanPostProcessor thế nào?

Hai tên rất giống nhau nhưng làm việc ở hai giai đoạn khác nhau.

| Tiêu chí | BeanFactoryPostProcessor | BeanPostProcessor |
|---|---|---|
| Đối tượng xử lý chính | BeanFactory và BeanDefinition metadata | Bean instance |
| Thời điểm | Sau khi bean definitions được nạp, trước khi các bean ứng dụng thông thường được tạo | Trong quá trình khởi tạo từng bean |
| Mục tiêu | Thay đổi cách bean sẽ được tạo/cấu hình | Xử lý object trước/sau initialization |
| API chính | **postProcessBeanFactory(...)** | **postProcessBeforeInitialization(...)**, **postProcessAfterInitialization(...)** |
| Ví dụ | Property placeholder configurer, sửa lazy-init | Annotation processing, proxy creation |

Sơ đồ:

~~~text
BeanDefinition được nạp
        │
        ▼
BeanFactoryPostProcessor
        │
        │ thay đổi metadata
        ▼
BeanFactory bắt đầu tạo bean
        │
        ▼
Dependency injection
        │
        ▼
BeanPostProcessor before initialization
        │
        ▼
@PostConstruct / afterPropertiesSet / init-method
        │
        ▼
BeanPostProcessor after initialization
        │
        ▼
Bean instance sẵn sàng
~~~

### Ví dụ về BeanPostProcessor

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.stereotype.Component;

@Component
public class LoggingBeanPostProcessor implements BeanPostProcessor {

    @Override
    public Object postProcessBeforeInitialization(
            Object bean, String beanName) throws BeansException {
        // Có thể kiểm tra hoặc xử lý instance trước init callbacks.
        return bean;
    }

    @Override
    public Object postProcessAfterInitialization(
            Object bean, String beanName) throws BeansException {
        // Có thể trả về object khác, ví dụ một proxy.
        return bean;
    }
}
~~~

BeanPostProcessor nhận **object thật** và có thể trả lại object đã được bọc hoặc xử lý. Ví dụ, các cơ chế AOP có thể sử dụng post-processing để tạo proxy cho bean.

Ngược lại, BFPP không nhận tham số bean instance. Nó nhận **ConfigurableListableBeanFactory** để thao tác với metadata và cấu hình BeanFactory.

### Không dùng BFPP thay cho BeanPostProcessor

Nếu yêu cầu là:

- “Đổi lazy-init trước khi bean được tạo” → BFPP.
- “Thêm property value vào bean definition” → BFPP.
- “Ghi log khi một bean instance được tạo xong” → BeanPostProcessor hoặc lifecycle callback phù hợp.
- “Bọc một service bằng proxy” → BeanPostProcessor/AOP.
- “Kiểm tra trạng thái object sau khi inject” → @PostConstruct hoặc post-processor phù hợp.

Chọn đúng extension point giúp tránh tạo object quá sớm hoặc sửa sai tầng.

## 8. BeanDefinitionRegistryPostProcessor: đăng ký definition mới

**BeanDefinitionRegistryPostProcessor (BDRPP)** mở rộng **BeanFactoryPostProcessor** và cung cấp thêm phương thức:

~~~java
void postProcessBeanDefinitionRegistry(
        BeanDefinitionRegistry registry);
~~~

Khác biệt quan trọng:

- **BDRPP** có thể thêm, sửa hoặc xóa bean definitions trong registry trước giai đoạn BFPP thông thường.
- **BFPP** làm việc với BeanFactory và những bean definitions đã có; nó chủ yếu sửa metadata/cấu hình.

Nếu cần **đăng ký một bean definition mới**, BDRPP thường là extension point phù hợp hơn.

### Ví dụ đăng ký bean definition

~~~java
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DynamicRegistrationConfiguration {

    @Bean
    static BeanDefinitionRegistryPostProcessor registerAuditService() {
        return new BeanDefinitionRegistryPostProcessor() {

            @Override
            public void postProcessBeanDefinitionRegistry(
                    BeanDefinitionRegistry registry) {
                if (!registry.containsBeanDefinition("auditService")) {
                    registry.registerBeanDefinition(
                            "auditService",
                            BeanDefinitionBuilder
                                    .genericBeanDefinition(AuditService.class)
                                    .getBeanDefinition());
                }
            }

            @Override
            public void postProcessBeanFactory(
                    ConfigurableListableBeanFactory beanFactory) {
                // Có thể xử lý thêm metadata sau bước registry.
            }
        };
    }
}
~~~

Trong ví dụ, **AuditService** là class Java cần được định nghĩa trong ứng dụng. BDRPP kiểm tra tên bean trước khi đăng ký để tránh đăng ký trùng. Khi quá trình startup tiếp tục, BeanFactory sẽ dùng definition mới để tạo object theo yêu cầu.

### Vì sao BDRPP chạy trước BFPP?

BDRPP cần có cơ hội bổ sung bean definitions để các post-processor tiếp theo nhìn thấy chúng. Do đó, Spring xử lý các **BeanDefinitionRegistryPostProcessor** trước các **BeanFactoryPostProcessor** thông thường.

Một phần quan trọng của Spring, **ConfigurationClassPostProcessor**, cũng là một BDRPP. Nó xử lý các class cấu hình, component scanning, @Bean methods và nhiều metadata cấu hình trước khi các bean ứng dụng được tạo.

Nếu nhu cầu chỉ là thay đổi lazy-init hoặc property value của bean đã có, không cần dùng BDRPP chỉ vì nó có tên “post processor” rộng hơn. Hãy chọn BFPP đơn giản hơn.

## 9. Vì sao phương thức @Bean tạo BFPP nên là static?

Khi khai báo BFPP bằng Java configuration, thường nên viết:

~~~java
@Configuration
public class MetadataConfiguration {

    @Bean
    public static BeanFactoryPostProcessor metadataProcessor() {
        return beanFactory -> {
            // Chỉnh metadata.
        };
    }
}
~~~

Lý do: Spring phải tạo BFPP rất sớm để thực hiện xử lý metadata. Nếu factory method **@Bean** là instance method, Spring có thể phải khởi tạo object **@Configuration** chứa nó trước thời điểm thông thường.

Việc tạo configuration class quá sớm có thể khiến những dependency hoặc annotation processing liên quan tới class đó chưa sẵn sàng như bạn kỳ vọng. Spring vì thế khuyến nghị các **@Bean methods trả về BeanFactoryPostProcessor/BeanDefinitionRegistryPostProcessor nên là static** khi có thể.

### Không inject application service vào BFPP

Một BFPP được tạo ở giai đoạn rất sớm. Nếu nó phụ thuộc vào service nghiệp vụ:

~~~java
@Bean
BeanFactoryPostProcessor metadataProcessor(
        ReportService reportService) {
    return beanFactory -> {
        // ...
    };
}
~~~

Spring có thể phải tạo **ReportService** ngay để cung cấp tham số cho factory method, trước khi quá trình xử lý metadata hoàn tất. Bean đó có thể được tạo quá sớm, chưa nhận đầy đủ các post-processor thông thường hoặc gây cảnh báo về bean không được xử lý đầy đủ.

**Không nên lấy application bean trong BFPP** bằng constructor injection, field injection hoặc gọi **beanFactory.getBean(...)**. BFPP nên làm việc với BeanDefinition và cấu hình hạ tầng, không chạy nghiệp vụ hay dùng service của ứng dụng.

Nếu cần dữ liệu cấu hình, hãy cân nhắc nguồn metadata phù hợp như Environment hoặc một cấu hình primitive đã có sẵn, đồng thời tránh ép container tạo những bean ứng dụng thông thường trong giai đoạn sớm này.

## 10. Các BeanFactoryPostProcessor có thứ tự chạy như thế nào?

Một ứng dụng có thể có nhiều post-processor. Thứ tự xử lý có thể quan trọng nếu processor thứ hai phụ thuộc vào metadata do processor thứ nhất thay đổi.

Spring hỗ trợ sắp xếp những BFPP được phát hiện trong context qua các interface:

- **PriorityOrdered:** nhóm ưu tiên cao hơn.
- **Ordered:** nhóm được sắp xếp tiếp theo theo giá trị order.
- Các BFPP không triển khai hai interface này được xử lý sau các nhóm có thứ tự.

Ví dụ:

~~~java
import org.springframework.beans.factory.PriorityOrdered;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;

public class EarlyMetadataProcessor
        implements BeanFactoryPostProcessor, PriorityOrdered {

    @Override
    public int getOrder() {
        return 0;
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
        // Xử lý metadata ở nhóm PriorityOrdered.
    }
}
~~~

Một processor khác có thể implement **Ordered** và trả về giá trị order phù hợp. Giá trị order nhỏ hơn thường được xử lý trước trong cùng nhóm so sánh.

### Lưu ý về đăng ký programmatic

Nếu BFPP được thêm trực tiếp qua **ConfigurableApplicationContext.addBeanFactoryPostProcessor(...)**, Spring xử lý những processor đăng ký programmatically trước các processor được phát hiện từ bean definitions; thứ tự đăng ký trực tiếp được dùng và semantics sắp xếp qua PriorityOrdered/Ordered không áp dụng giống nhóm tự phát hiện.

Vì vậy, khi cần thứ tự có chủ đích, hãy hiểu BFPP được đăng ký theo cách nào. Không nên dựa vào thứ tự tình cờ của class hoặc file cấu hình.

### @Order có thay thế được Ordered không?

Đối với BFPP, cách rõ ràng và được tài liệu Spring sử dụng là triển khai **PriorityOrdered** hoặc **Ordered**. Không nên mặc định rằng thêm **@Order** lên mọi class BFPP sẽ giải quyết thứ tự trong tất cả cách đăng ký.

## 11. PropertySourcesPlaceholderConfigurer là ví dụ BFPP có sẵn

Một ứng dụng thường dùng placeholder:

~~~java
@Value("\${app.report-timeout:5000}")
private int timeout;
~~~

Hoặc giá trị trong bean definition:

~~~xml
<property name="timeout" value="\${app.report-timeout}"/>
~~~

Spring cung cấp **PropertySourcesPlaceholderConfigurer**, một BeanFactoryPostProcessor, để xử lý placeholder từ các property sources và thay thế chúng bằng giá trị phù hợp.

Trong Spring Boot, cơ chế cấu hình Environment và placeholder thường đã được tự động cấu hình. Bạn thường không cần tự khai báo configurer này trong một ứng dụng Boot thông thường. Nhưng đây là ví dụ hữu ích để hiểu BFPP được dùng thế nào trong hạ tầng Spring.

Trong một ứng dụng Spring Framework thuần hoặc cấu hình đặc biệt, có thể khai báo:

~~~java
@Configuration
public class PlaceholderConfiguration {

    @Bean
    public static PropertySourcesPlaceholderConfigurer propertySourcesPlaceholderConfigurer() {
        return new PropertySourcesPlaceholderConfigurer();
    }
}
~~~

Phương thức là **static** vì bean trả về một BFPP. Cấu hình này cho phép placeholder configurer tham gia vào giai đoạn xử lý BeanFactory trước khi bean thông thường được tạo.

## 12. Những gì BFPP không nên làm

### Không gọi getBean() để dùng service nghiệp vụ

~~~java
@Override
public void postProcessBeanFactory(
        ConfigurableListableBeanFactory beanFactory) {
    ReportService service = beanFactory.getBean(ReportService.class);
    service.generate();
}
~~~

Đây là cách sử dụng không phù hợp. **getBean()** có thể buộc Spring khởi tạo bean quá sớm, trước khi các post-processor thông thường được đăng ký đầy đủ. Ngoài ra, gọi **generate()** là chạy nghiệp vụ trong giai đoạn sửa metadata, làm lẫn hai trách nhiệm.

BFPP nên thao tác **getBeanDefinition(...)**, không phải lấy instance ứng dụng để gọi hành vi.

### Không dùng BFPP để sửa field của object

BFPP không nhận object bean. Nếu cần xử lý instance, hãy dùng BeanPostProcessor, @PostConstruct hoặc một cơ chế khác đúng thời điểm.

### Không đăng ký bean definition mới qua BFPP thông thường

BFPP nhận **ConfigurableListableBeanFactory**, không phải API registry chuyên dùng để đăng ký definition. Nếu cần thêm bean definition, hãy dùng **BeanDefinitionRegistryPostProcessor** hoặc một cơ chế đăng ký phù hợp.

### Không dùng BFPP cho mỗi cấu hình nhỏ

Nếu mục tiêu chỉ là gán timeout, URL hoặc batch size, hãy ưu tiên **@ConfigurationProperties**, **@Value**, constructor parameter của **@Bean** hoặc cấu hình rõ ràng khác. BFPP mạnh nhưng phức tạp và chạy rất sớm.

### Không phụ thuộc vào bean được tạo quá sớm

Việc lấy application service hoặc datasource từ BFPP có thể gây early initialization và ảnh hưởng tới quá trình post-processing. Hãy giữ BFPP độc lập với bean ứng dụng.

## 13. So sánh các extension point liên quan

| Cơ chế | Làm việc với | Mục đích |
|---|---|---|
| **BeanDefinitionRegistryPostProcessor** | Registry của BeanDefinition | Đăng ký thêm hoặc thay đổi bean definitions ở giai đoạn registry |
| **BeanFactoryPostProcessor** | BeanFactory và BeanDefinition metadata | Điều chỉnh metadata/cấu hình trước khi bean thông thường được tạo |
| **BeanPostProcessor** | Bean instance | Xử lý object trước/sau initialization |
| **InitializingBean** | Một bean instance | Callback init sau khi properties được thiết lập |
| **@PostConstruct** | Một bean instance | Callback init theo annotation |
| **SmartInitializingSingleton** | Các eager singleton sau khi tạo | Callback khi các singleton eager thông thường đã được khởi tạo |
| **ApplicationRunner** | Ứng dụng sau khi context refresh | Chạy công việc startup ở cấp Spring Boot |

Sơ đồ quyết định:

~~~text
Cần thêm một BeanDefinition?
        │
        ├── Có → BeanDefinitionRegistryPostProcessor
        │
        └── Không
             │
             ▼
       Cần sửa metadata trước khi tạo bean?
             │
             ├── Có → BeanFactoryPostProcessor
             │
             └── Không
                  │
                  ▼
          Cần xử lý bean instance?
                  │
                  ├── Trước/sau init → BeanPostProcessor
                  ├── Init callback → @PostConstruct / InitializingBean
                  └── Sau toàn bộ eager singleton → SmartInitializingSingleton
~~~

## 14. Ví dụ kiểm tra metadata mà không khởi tạo bean sớm

Một cách kiểm tra BFPP đã sửa metadata là đọc **BeanDefinition** trong một context test, thay vì gọi **getBean()** ngay trong processor.

Ví dụ kiểm tra lazy-init:

~~~java
try (var context =
        new AnnotationConfigApplicationContext(
                MetadataConfiguration.class,
                ReportService.class)) {

    var beanFactory = context.getDefaultListableBeanFactory();
    var definition = beanFactory.getBeanDefinition("reportService");

    assertTrue(definition.isLazyInit());
}
~~~

Đoạn trên là phần thân minh họa; test hoàn chỉnh cần import JUnit assertion và cấu hình component/bean name tương ứng. Nó đọc metadata bằng **getBeanDefinition**, không yêu cầu tạo instance **ReportService**.

Nếu muốn kiểm tra property value đã được bổ sung:

~~~java
var definition = beanFactory.getBeanDefinition("batchProcessor");
Object configuredValue = definition.getPropertyValues()
        .get("batchSize");

assertEquals(200, configuredValue);
~~~

Điều này kiểm tra **metadata**. Nếu muốn kiểm tra giá trị cuối cùng trên bean instance, phải yêu cầu container tạo bean rồi đọc property:

~~~java
BatchProcessor processor = context.getBean(BatchProcessor.class);
assertEquals(200, processor.getBatchSize());
~~~

Hai kiểm tra trả lời hai câu hỏi khác nhau:

- Metadata có được BFPP thay đổi đúng không?
- Khi bean được tạo, BeanFactory có áp dụng metadata đó vào object không?

## 15. Những lỗi thường gặp khi triển khai BFPP

**Dùng non-static @Bean method để khai báo BFPP.** Configuration class có thể bị khởi tạo quá sớm. Hãy ưu tiên static factory method cho BFPP/BDRPP.

**Inject service nghiệp vụ vào BFPP.** Dependency có thể bị tạo trước khi quá trình post-processing hoàn tất. BFPP nên làm việc với metadata, không gọi nghiệp vụ.

**Gọi getBean() bên trong postProcessBeanFactory().** Việc này có thể tạo object quá sớm và làm mất cơ hội áp dụng đầy đủ các post-processor thông thường.

**Nhầm BFPP với BeanPostProcessor.** BFPP sửa BeanDefinition; BeanPostProcessor xử lý object instance.

**Dùng BFPP để thêm bean definition mới.** Dùng BeanDefinitionRegistryPostProcessor nếu cần đăng ký definition.

**Quên tên bean có thể khác tên class.** Kiểm tra tên được đăng ký hoặc khai báo tên rõ ràng qua stereotype/@Bean.

**Thay scope mà không hiểu tác động.** Chuyển singleton thành prototype có thể làm thay đổi state, lifecycle, số lượng instance và hành vi dependency injection.

**Đặt lazy-init rồi kỳ vọng dependency eager không tạo bean.** Một bean lazy vẫn có thể được tạo sớm khi bean eager khác cần nó.

**Dựa vào thứ tự không được bảo đảm.** Nếu nhiều post-processor phụ thuộc nhau, dùng PriorityOrdered/Ordered hoặc thứ tự đăng ký programmatic theo đúng cơ chế.

**Chạy tác vụ nghiệp vụ trong BFPP.** BFPP chạy ở giai đoạn startup sớm; không dùng nó để gửi email, nhập dữ liệu hay xử lý đơn hàng.

## 16. Khi nào nên dùng BeanFactoryPostProcessor?

BFPP phù hợp nhất khi bạn đang xây dựng **hạ tầng, framework nội bộ, thư viện tích hợp hoặc một cơ chế cấu hình tổng quát** cần điều chỉnh bean definitions trước khi instance được tạo.

Ví dụ có thể cân nhắc:

- Một thư viện đánh dấu một nhóm bean là lazy dựa trên metadata.
- Một nền tảng nội bộ thêm property value mặc định vào định nghĩa bean theo quy ước.
- Một integration thay đổi autowire candidate hoặc primary cho bean definitions được chọn.
- Một framework cần điều chỉnh metadata của bean được component scan/auto-configuration đăng ký.
- Một configurer xử lý placeholder trong bean definitions.

Với code nghiệp vụ thường ngày, các lựa chọn đơn giản hơn thường thích hợp:

| Nhu cầu | Cơ chế dễ hiểu hơn |
|---|---|
| Gán dependency bắt buộc | Constructor injection |
| Gán cấu hình vào class | @ConfigurationProperties hoặc @Value |
| Tạo bean với constructor/factory logic | @Bean |
| Xử lý object sau khi tạo | @PostConstruct hoặc BeanPostProcessor |
| Chọn implementation theo môi trường | @Profile / conditional configuration |
| Đăng ký một bean bổ sung cụ thể | @Bean hoặc @Import |

Không nên dùng BFPP chỉ vì nó có thể thay đổi rất nhiều metadata. Hãy dùng khi yêu cầu thực sự nằm ở **giai đoạn xử lý BeanDefinition**.

## 17. Thực hành: quan sát thứ tự và hiệu quả của BFPP

Tạo một Spring Boot project nhỏ có class **BatchProcessor** và **ReportService**. Đăng ký một BFPP bằng static @Bean method. Trong callback, chỉ thao tác trên bean definitions:

1. Đọc definition **batchProcessor**.
2. Thêm property value **batchSize = 200**.
3. Đọc definition **reportService**.
4. Đặt **lazyInit = true**.
5. Không gọi **getBean()** trong callback.

Sau khi context refresh:

- Đọc metadata để xác nhận **batchProcessor** có property value mới.
- Đọc metadata để xác nhận **reportService** được đánh dấu lazy.
- Khi thật sự gọi **getBean(ReportService.class)**, quan sát bean mới được tạo.
- Thử để một singleton eager phụ thuộc vào ReportService và quan sát lazy dependency vẫn được tạo để thỏa mãn dependency.

Tiếp theo, tạo một **BeanPostProcessor** chỉ ghi log trước/sau initialization để thấy nó hoạt động trên instance sau khi BeanFactory đã xử lý metadata. Sau đó thử một **BeanDefinitionRegistryPostProcessor** đăng ký thêm definition và quan sát thứ tự của registry phase.

Mục tiêu là nhận ra ba tầng:

~~~text
Registry post-processor
    → thay đổi danh sách BeanDefinitions

BeanFactory post-processor
    → thay đổi metadata của BeanDefinitions

Bean post-processor
    → xử lý object bean khi khởi tạo
~~~

## Kết luận

**BeanFactoryPostProcessor** là extension point của Spring dùng để thay đổi **BeanFactory và BeanDefinition metadata trước khi các bean ứng dụng thông thường được tạo**. Nó có thể điều chỉnh lazy-init, scope, property values, primary hoặc các thiết lập metadata phù hợp.

Hãy phân biệt rõ:

- **BeanDefinitionRegistryPostProcessor** dùng khi cần thêm hoặc thay đổi registry của bean definitions ở giai đoạn sớm hơn.
- **BeanFactoryPostProcessor** dùng khi cần điều chỉnh metadata/cấu hình của BeanFactory.
- **BeanPostProcessor** dùng khi cần xử lý bean instance trước hoặc sau initialization.

Khi khai báo BFPP bằng **@Bean**, ưu tiên factory method **static** và tránh lấy application bean trong callback để không kích hoạt việc khởi tạo quá sớm. Với ứng dụng Spring Boot thông thường, hãy ưu tiên dependency injection, **@ConfigurationProperties**, **@Bean** và các annotation cấu hình trực tiếp; dành BFPP cho những trường hợp thực sự cần can thiệp ở tầng metadata.

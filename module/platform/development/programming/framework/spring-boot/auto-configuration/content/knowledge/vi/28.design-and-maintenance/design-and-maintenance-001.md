# Mỗi cấu hình có mục đích, đầu vào và bean đầu ra rõ ràng

## 1. Auto-configuration là một contract

Một class auto-configuration nên trả lời được ba câu hỏi trước khi người khác đọc code:

1. **Mục đích:** capability nào của thư viện sẽ được tích hợp?
2. **Đầu vào:** condition, dependency, property và bean nào phải có để cấu hình được áp dụng?
3. **Đầu ra:** bean nào được tạo, kiểu gì, phục vụ ai và người dùng thay thế nó bằng cách nào?

Ví dụ, thay vì mô tả chung chung “cấu hình Acme”, hãy mô tả cụ thể:

> **AcmeAuditAutoConfiguration** cung cấp một **AuditClient** mặc định khi SDK transport có trên classpath, **acme.audit.enabled=true** và ứng dụng chưa tự cung cấp AuditClient. Đầu ra là một **DefaultAuditClient**, có endpoint và timeout được bind từ **AuditProperties**.

Mô tả này cho người maintain biết phải kiểm tra điều gì khi bean không xuất hiện, biết bean nào là public extension point và biết thay đổi nào có thể phá contract.

Một auto-configuration có thể tạo nhiều bean nếu chúng cùng phục vụ một capability và có quan hệ rõ ràng. Mục tiêu không phải tạo một class cho mỗi bean, mà là giữ mỗi configuration class có một trách nhiệm đủ hẹp để hiểu, test và thay đổi độc lập.

Bài này dùng Spring Boot 3.3.13, Java 17+ và ví dụ thư viện Acme Audit. Nội dung đi qua contract, đầu vào, bean đầu ra, properties, conditions, optional dependencies, back-off, ordering, module boundaries và kiểm thử bằng ApplicationContextRunner.

## 2. Viết contract trước khi viết bean

Với mỗi configuration class, hãy ghi lại mục đích, điều kiện đầu vào, bean đầu ra và điểm mở rộng. Bảng dưới đây là bản thiết kế cho ví dụ:

| Thành phần | Contract của AcmeAuditAutoConfiguration |
| --- | --- |
| Mục đích | Cung cấp client audit mặc định cho ứng dụng |
| Classpath input | Có AuditTransport từ SDK transport |
| Property input | acme.audit.enabled=true |
| Configuration input | AuditProperties cung cấp endpoint và timeout |
| Bean input | Chưa có bean nào implement AuditClient |
| Bean output | Một DefaultAuditClient, expose qua AuditClient |
| Customization | Ứng dụng có thể tự khai báo AuditClient; bean mặc định back off |
| Side effects | Không gửi request hoặc mở kết nối chỉ vì ApplicationContext được tạo |

Contract này giúp trả lời những câu hỏi vận hành:

- Nếu SDK không có, ứng dụng có khởi động được không? Có; configuration nhánh SDK không được áp dụng.
- Nếu feature bị tắt, bean client có xuất hiện không? Không.
- Nếu người dùng tự tạo AuditClient, ai thắng? Bean của người dùng.
- Nếu endpoint thay đổi, có cần sửa code không? Không; nó là property được bind.
- Nếu muốn thêm web endpoint, có nên thêm bean đó vào cùng class không? Chỉ khi nó thuộc cùng capability và có cùng điều kiện; nếu có web-specific inputs, nên tách configuration riêng.

### 2.1. Mẫu contract ngắn cho mỗi configuration

| Trường | Nội dung cần ghi |
| --- | --- |
| Purpose | Một câu mô tả capability và lý do class tồn tại |
| Applies when | Classpath, property, resource, web type hoặc bean conditions |
| Requires | Dependency/bean/property bắt buộc để tạo output |
| Provides | Bean type, bean name nếu có ý nghĩa, default implementation |
| Backs off when | User bean hoặc điều kiện nào khiến default không được tạo |
| Ordering | Auto-configuration nào phải chạy trước/sau và vì sao |
| Tests | Các trường hợp ON/OFF, missing dependency và override phải được kiểm chứng |

Không cần biến bảng này thành boilerplate dài cho mọi class. Một vài dòng rõ ràng trong Javadoc, cùng test thể hiện contract, thường là đủ.

## 3. Phân loại đầu vào của auto-configuration

Đầu vào không chỉ là property. Spring Boot cung cấp nhiều loại condition; hãy chọn đúng loại cho điều mà configuration thực sự cần.

### 3.1. Classpath input

Dùng **@ConditionalOnClass** khi capability cần một thư viện hoặc API cụ thể:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.sdk.AuditTransport")
public class AcmeAuditAutoConfiguration {
    // ...
}
```

Dùng thuộc tính name khi muốn tránh tham chiếu trực tiếp tới class có thể vắng mặt. Nếu dùng value = AuditTransport.class, Spring Boot có thể đọc annotation metadata bằng ASM mà không cần load class đó ngay.

Nếu bean method có chữ ký hoặc implementation tham chiếu một class tùy chọn, hãy cô lập nó trong nested **@Configuration** có **@ConditionalOnClass**. JVM có thể phải load kiểu của method trước khi method-level condition được đánh giá. Cấu hình lồng có điều kiện ngăn type tùy chọn bị xử lý quá sớm.

Ví dụ:

```java
@AutoConfiguration
public class AcmeAuditAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(AuditTransport.class)
    static class TransportConfiguration {

        @Bean
        @ConditionalOnMissingBean(AuditClient.class)
        DefaultAuditClient auditClient(AuditProperties properties) {
            return new DefaultAuditClient(
                    new AuditTransport(),
                    properties.getEndpoint(),
                    properties.getTimeout());
        }
    }
}
```

Trong thư viện thực tế, AuditTransport thường đến từ một dependency SDK tùy chọn. Class này và mọi kiểu chỉ có trong SDK nên được giữ bên trong nhánh configuration có điều kiện. Không đưa kiểu SDK đó vào public method signature của configuration ngoài nếu class có thể không tồn tại.

### 3.2. Property input

Dùng **@ConditionalOnProperty** khi property quyết định một capability có được tạo hay không:

```java
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
```

Với havingValue để trống, @ConditionalOnProperty mặc định match khi property tồn tại và không bằng chuỗi false. Nếu contract yêu cầu chính xác boolean true, hãy ghi havingValue = "true" để tránh những giá trị chuỗi không mong muốn.

matchIfMissing phải phản ánh lựa chọn sản phẩm:

- false: feature mặc định tắt nếu người dùng không khai báo.
- true: feature mặc định bật nếu property vắng mặt.

Đừng dùng property condition chỉ vì property có tên gần giống capability. Property nên thực sự quyết định configuration có được áp dụng hay không.

### 3.3. Bean input

**@ConditionalOnBean** và **@ConditionalOnMissingBean** kiểm tra bean definitions hiện có.

Ví dụ, chỉ tạo adapter nếu ứng dụng đã cung cấp một ConnectionFactory:

```java
@AutoConfiguration
@ConditionalOnBean(ConnectionFactory.class)
public class AcmeReactiveAutoConfiguration {
    // Các bean phụ thuộc ConnectionFactory.
}
```

Ví dụ, cung cấp default nếu chưa có implementation do ứng dụng khai báo:

```java
@Bean
@ConditionalOnMissingBean(AuditClient.class)
DefaultAuditClient auditClient(AuditProperties properties) {
    return new DefaultAuditClient(properties);
}
```

Bean conditions phụ thuộc vào các bean definitions đã được xử lý tại thời điểm condition được đánh giá. Vì vậy, Spring Boot khuyến nghị dùng @ConditionalOnBean và @ConditionalOnMissingBean ở cấp auto-configuration: auto-configuration được xử lý sau các bean definitions do người dùng khai báo.

Khi đặt @ConditionalOnMissingBean trên một bean method, target type mặc định được suy ra từ kiểu trả về. Nếu public extension point là interface AuditClient, khai báo rõ @ConditionalOnMissingBean(AuditClient.class) và trả về implementation cụ thể như DefaultAuditClient.

### 3.4. Resource và application type

Các loại đầu vào khác:

| Condition | Đầu vào được kiểm tra | Ví dụ sử dụng |
| --- | --- | --- |
| @ConditionalOnResource | Resource có tồn tại | Chỉ bật integration khi file schema/resource có mặt |
| @ConditionalOnWebApplication | Servlet hoặc reactive web context | Đăng ký web adapter phù hợp |
| @ConditionalOnNotWebApplication | Context không phải web | Cấu hình cho batch/CLI |
| @ConditionalOnWarDeployment | WAR triển khai vào Servlet container truyền thống | Khác biệt giữa external container và embedded server |
| @ConditionalOnExpression | Kết quả SpEL | Trường hợp thật sự cần biểu thức phức hợp |

Hạn chế @ConditionalOnExpression nếu các condition chuyên biệt đã đủ. Tham chiếu bean trong SpEL có thể khiến bean khởi tạo rất sớm trong quá trình refresh, trước khi hoàn tất post-processing như configuration properties binding. Khi đó state của bean có thể chưa đầy đủ.

### 3.5. Phân biệt condition với dependency injection

Condition trả lời câu hỏi **có đăng ký bean/configuration hay không**. Dependency injection trả lời câu hỏi **bean đã đăng ký cần bean nào để hoạt động**.

Ví dụ:

```java
@Bean
DefaultAuditClient auditClient(
        AuditTransport transport,
        AuditProperties properties) {
    return new DefaultAuditClient(
            transport,
            properties.getEndpoint(),
            properties.getTimeout());
}
```

Ở đây transport là dependency của bean. Không cần thêm @ConditionalOnBean(AuditTransport.class) nếu configuration đã được bảo vệ bởi @ConditionalOnClass và transport được đăng ký trong cùng nhánh. Hãy tránh lặp điều kiện không cần thiết; mỗi condition thêm vào đều làm contract khó hiểu hơn.

## 4. Định nghĩa bean đầu ra rõ ràng

Một bean method là nơi công bố output của configuration. Kiểu trả về nên thể hiện rõ bean nào được tạo.

### 4.1. Ưu tiên kiểu trả về cụ thể

Spring Boot khuyến nghị cung cấp nhiều type information nhất có thể trong method signature, đặc biệt khi bean conditions dựa vào kiểu trả về.

Ví dụ tốt:

```java
@Bean
@ConditionalOnMissingBean(AuditClient.class)
DefaultAuditClient auditClient(AuditProperties properties) {
    return new DefaultAuditClient(properties);
}
```

Ở phía ứng dụng, code vẫn có thể inject qua abstraction:

```java
@Service
class AuditJob {

    private final AuditClient auditClient;

    AuditJob(AuditClient auditClient) {
        this.auditClient = auditClient;
    }
}
```

Method trả về DefaultAuditClient để metadata và condition có type cụ thể; ứng dụng phụ thuộc AuditClient để giữ coupling thấp.

Nếu method trả về Object hoặc một interface quá tổng quát, bean conditions có thể không nhìn thấy type cần thiết từ method signature. Chỉ dùng kiểu trả về tổng quát khi đó thực sự là contract output.

### 4.2. Một output nên có một trách nhiệm

Tránh một configuration tạo nhiều bean không liên quan chỉ vì chúng cùng dùng một dependency:

```java
@AutoConfiguration
public class AcmeAutoConfiguration {

    @Bean
    AuditClient auditClient() { ... }

    @Bean
    MetricsExporter metricsExporter() { ... }

    @Bean
    AdminController adminController() { ... }

    @Bean
    ReactiveAdapter reactiveAdapter() { ... }
}
```

Nếu các bean có điều kiện đầu vào khác nhau, hãy chia theo capability. Ví dụ:

- AcmeAuditClientAutoConfiguration: client và các object cần để client hoạt động.
- AcmeAuditMetricsAutoConfiguration: metrics integration, chỉ khi Actuator/Micrometer có mặt.
- AcmeAuditWebAutoConfiguration: controller hoặc web adapter, chỉ trong đúng loại web application.
- AcmeAuditReactiveAutoConfiguration: reactive adapter và dependency riêng.

Một configuration có thể tạo nhiều bean liên quan, chẳng hạn client và customizer của chính client đó. Không nên chia nhỏ đến mức mỗi bean có một class configuration riêng mà không đem lại ranh giới rõ hơn.

### 4.3. Công bố rõ bean name và kiểu

Khi có nhiều bean cùng type, contract cần nêu:

- Bean nào là default?
- Bean nào là primary nếu có lý do chọn mặc định?
- Bean nào có qualifier?
- Ứng dụng có thể thay toàn bộ abstraction hay chỉ thay một collaborator?
- Khi user bean xuất hiện, auto-configuration back-off ở một bean hay cả nhóm?

Không dùng @Primary để che một thiết kế có hai default bean cùng type mà không rõ vai trò. Nếu có hai client khác mục đích, hãy dùng interface riêng, qualifier có tên hoặc cấu hình hai capability độc lập.

## 5. Tổ chức configuration class theo capability

Tên class nên giúp người đọc suy ra chức năng mà không cần mở nội dung.

Ví dụ một thư viện audit:

```text
com.acme.audit.autoconfigure/
├── AcmeAuditClientAutoConfiguration.java
├── AcmeAuditWebAutoConfiguration.java
├── AcmeAuditMetricsAutoConfiguration.java
├── AcmeAuditProperties.java
└── package-info.java
```

Mỗi class có thể có contract riêng:

| Configuration | Purpose | Inputs | Outputs |
| --- | --- | --- | --- |
| AcmeAuditClientAutoConfiguration | Cung cấp client audit | SDK client class, acme.audit.enabled, AuditProperties, chưa có AuditClient | AuditClient mặc định |
| AcmeAuditWebAutoConfiguration | Cung cấp HTTP endpoint/adapter | Servlet web application, client có sẵn | Web adapter/controller |
| AcmeAuditMetricsAutoConfiguration | Cung cấp metrics cho audit | Micrometer/Actuator classpath, client/registry | MeterBinder hoặc metrics contributor |

Đừng đặt @ConditionalOnWebApplication lên client core nếu client có thể được dùng trong batch hoặc CLI. Web condition chỉ nên bao quanh web-specific beans.

### 5.1. Chia optional integration

Nếu SDK Kafka, AWS, Redis hoặc WebFlux là tùy chọn, tạo nested configuration hoặc module riêng cho từng integration. Việc một condition không match chỉ ngăn bean được đăng ký; nó không xóa dependency khỏi classpath. Tách module/starter giúp ứng dụng chỉ kéo integration thực sự cần.

### 5.2. Giữ package riêng và tránh component scanning

Auto-configuration phải được tìm thấy qua resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Ví dụ:

```text
com.acme.audit.autoconfigure.AcmeAuditClientAutoConfiguration
com.acme.audit.autoconfigure.AcmeAuditWebAutoConfiguration
com.acme.audit.autoconfigure.AcmeAuditMetricsAutoConfiguration
```

Auto-configuration nên nằm trong package riêng và chỉ được nạp bằng imports file. Không để package đó là target của component scanning. Cũng không thêm @ComponentScan vào auto-configuration để tìm component phụ. Dùng @Import cụ thể cho configuration/helper class cần thiết.

Nếu class auto-configuration không phải top-level, tên trong imports resource dùng dấu $ để phân tách nested class. Tuy nhiên, top-level class thường dễ refactor và review hơn.

## 6. Properties là đầu vào có cấu trúc

Property contract cần có namespace riêng, kiểu dữ liệu rõ, default hợp lý và mô tả có ích. Đừng để từng bean method tự đọc nhiều key bằng @Value nếu các key thuộc cùng một nhóm cấu hình.

### 6.1. Dùng @ConfigurationProperties

Ví dụ:

```java
package com.acme.audit.autoconfigure;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.audit")
public class AuditProperties {

    private URI endpoint = URI.create("https://audit.example.test");

    private Duration timeout = Duration.ofSeconds(3);

    public URI getEndpoint() {
        return this.endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return this.timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

Properties có một namespace rõ ràng:

```yaml
acme:
  audit:
    enabled: true
    endpoint: https://audit.internal.example
    timeout: 5s
```

enabled là input cho condition. endpoint và timeout là dữ liệu cấu hình cho bean đã được chọn. Tách vai trò này giúp người đọc biết property nào quyết định bean presence và property nào chỉ cấu hình output.

Ưu tiên Duration thay vì long để người dùng có thể ghi 5s, 250ms hoặc đơn vị phù hợp. Dùng URI, enum, collection và kiểu miền phù hợp thay vì để mọi giá trị ở dạng String.

### 6.2. Đăng ký properties có chủ đích

Trong auto-configuration, dùng @EnableConfigurationProperties:

```java
@AutoConfiguration
@EnableConfigurationProperties(AuditProperties.class)
public class AcmeAuditClientAutoConfiguration {
    // ...
}
```

Nếu properties chỉ có ý nghĩa khi một integration có mặt và được bật, có thể đặt annotation bên trong nested configuration có condition tương ứng. Như vậy properties bean không xuất hiện khi capability không được kích hoạt.

Không cần dựa vào @ConfigurationPropertiesScan của ứng dụng consumer để tìm properties type trong thư viện. Auto-configuration nên tự đăng ký những properties mà nó sở hữu.

### 6.3. Đặt tên và mô tả property

Dùng prefix thuộc tổ chức/sản phẩm, chẳng hạn acme.audit. Tránh đặt key của thư viện vào namespace do Spring Boot sở hữu như spring, server hoặc management.

Tài liệu field Javadoc nên giải thích ý nghĩa, không lặp lại default value:

```java
/**
 * Endpoint used by the audit client.
 */
private URI endpoint = URI.create("https://audit.example.test");

/**
 * Timeout for one audit request.
 */
private Duration timeout = Duration.ofSeconds(3);
```

Bật spring-boot-configuration-processor để IDE có metadata cho các key. Nếu dùng record cho @ConfigurationProperties, mô tả component bằng Javadoc @param ở cấp class.

Nếu cần validation, thêm validation dependency phù hợp và dùng constraint như @NotNull, @Min hoặc custom validator. Metadata/IDE hint không thay thế validation runtime.

## 7. Thiết kế condition theo đúng ý nghĩa

Condition càng rõ, behavior càng dễ dự đoán. Mỗi condition nên bảo vệ một yêu cầu thật sự của bean.

### 7.1. Kết hợp class, property và bean condition

Ví dụ cấu hình client:

```java
@AutoConfiguration
public class AcmeAuditAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(AuditTransport.class)
    @ConditionalOnProperty(
            prefix = "acme.audit",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    @EnableConfigurationProperties(AuditProperties.class)
    static class ClientConfiguration {

        @Bean
        @ConditionalOnMissingBean(AuditClient.class)
        DefaultAuditClient auditClient(AuditProperties properties) {
            return new DefaultAuditClient(
                    new AuditTransport(),
                    properties.getEndpoint(),
                    properties.getTimeout());
        }
    }
}
```

Đầu vào của ClientConfiguration được thể hiện ngay trên class và bean method:

- AuditTransport phải có trên classpath.
- acme.audit.enabled phải là true.
- AuditProperties được bind.
- Chưa có bean AuditClient do người dùng cung cấp.

Đầu ra là một DefaultAuditClient, có thể inject bằng AuditClient.

### 7.2. Đặt condition ở cấp class hay bean method?

| Vị trí | Khi nào phù hợp? | Kết quả khi không match |
| --- | --- | --- |
| Trên auto-configuration class | Toàn bộ capability không áp dụng | Configuration class không được đăng ký |
| Trên nested @Configuration | Một nhánh tùy chọn cần classpath/property riêng | Chỉ nhánh đó không được áp dụng |
| Trên bean method | Một bean cụ thể là optional, các bean khác vẫn cần | Chỉ bean method đó bị bỏ qua |

Nếu condition bảo vệ một nhóm bean cùng phụ thuộc SDK, nested configuration thường làm contract dễ đọc hơn. Nếu chỉ một bean phụ là optional, method-level condition có thể đủ.

### 7.3. Đừng tạo condition thừa hoặc mâu thuẫn

Ví dụ một configuration đã có @ConditionalOnClass(AuditTransport.class) và bean method bắt buộc inject AuditTransport. Nếu transport được đăng ký trong cùng nhánh, không cần thêm @ConditionalOnBean(AuditTransport.class) chỉ để lặp lại điều kiện classpath.

Ngược lại, class có trên classpath không chứng minh rằng một bean instance đã được đăng ký. Class condition và bean condition là hai loại đầu vào khác nhau.

Viết condition theo đúng câu hỏi:

- Cần API có mặt? @ConditionalOnClass.
- Cần property bật? @ConditionalOnProperty.
- Cần bean đã đăng ký? @ConditionalOnBean.
- Cần nhường bean cho người dùng? @ConditionalOnMissingBean.
- Cần resource tồn tại? @ConditionalOnResource.
- Cần đúng web type? @ConditionalOnWebApplication.

## 8. Back-off là một phần của contract customization

Auto-configuration cung cấp default. Ứng dụng phải có quyền thay default bằng bean riêng khi extension point được thiết kế cho việc đó.

```java
@Bean
@ConditionalOnMissingBean(AuditClient.class)
DefaultAuditClient auditClient(AuditProperties properties) {
    return new DefaultAuditClient(properties);
}
```

Nếu ứng dụng khai báo:

```java
@Configuration(proxyBeanMethods = false)
class CustomAuditConfiguration {

    @Bean
    AuditClient customAuditClient() {
        return payload -> "custom";
    }
}
```

auto-configuration không tạo DefaultAuditClient. Ứng dụng có đúng một AuditClient theo contract.

### 8.1. Chọn đúng type cho missing-bean condition

Nếu output công bố là AuditClient, condition nên kiểm tra AuditClient.class. Nếu kiểm tra DefaultAuditClient.class, bean do người dùng cung cấp bằng implementation khác sẽ không ngăn default được tạo; ứng dụng có thể nhận hai bean cùng interface.

### 8.2. Không back-off quá rộng

Không đặt @ConditionalOnMissingBean trên cả configuration class nếu người dùng chỉ cần thay một bean nhưng vẫn muốn các bean phụ trợ khác. Khi đó đặt condition ở bean method tương ứng.

Ngược lại, nếu tất cả bean trong một capability chỉ có ý nghĩa khi user chưa cung cấp một abstraction cấp cao hơn, class-level condition có thể hợp lý. Hãy ghi rõ phạm vi back-off trong contract và test nó.

### 8.3. Callback và customizer

Khi cần customization nhỏ hơn việc thay toàn bộ client, có thể công bố callback/customizer:

```java
@FunctionalInterface
public interface AuditClientCustomizer {

    void customize(AuditClientBuilder builder);
}
```

Auto-configuration có thể nhận danh sách customizer và áp dụng chúng khi tạo client. Đây là extension point phù hợp khi người dùng chỉ cần thay timeout policy, header, retry policy hoặc interceptor.

Chỉ thêm customizer khi có nhu cầu thực tế. Mỗi callback là một API công khai cần duy trì compatibility và thứ tự áp dụng rõ ràng.

## 9. Ordering giữa các auto-configuration

Không dùng thứ tự để bù cho một contract đầu vào/đầu ra chưa rõ.

Nếu auto-configuration phải được áp dụng sau configuration khác, có thể khai báo:

```java
@AutoConfiguration(after = WebMvcAutoConfiguration.class)
public class AcmeAuditWebAutoConfiguration {
    // Web-specific beans
}
```

Hoặc dùng before, after, beforeName, afterName, @AutoConfigureBefore, @AutoConfigureAfter và @AutoConfigureOrder.

Một số nguyên tắc:

- Chỉ khai báo ordering khi configuration thực sự phụ thuộc vào bean definitions/configuration khác.
- Dùng afterName khi không muốn phụ thuộc trực tiếp vào class của optional module.
- Ordering của auto-configuration quyết định thứ tự bean definitions được đăng ký.
- Nó không quyết định thứ tự khởi tạo bean instance; dependency graph và @DependsOn mới liên quan đến quan hệ khởi tạo.
- @Order trên bean thường điều khiển thứ tự trong collection/injection, không thay thế @AutoConfigureAfter.

Với @ConditionalOnBean và @ConditionalOnMissingBean, hãy nhớ chúng nhìn vào các bean definitions đã được xử lý đến thời điểm đó. Vì vậy, đặt bean conditions ở auto-configuration và khai báo ordering rõ khi có phụ thuộc thật.

## 10. Tránh side effect trong quá trình đăng ký cấu hình

Một auto-configuration nên mô tả cách tạo bean, không thực hiện nghiệp vụ khi class được load.

Tránh:

- Gửi HTTP request trong static initializer.
- Kết nối database hoặc Kafka chỉ để kiểm tra credentials khi parse configuration.
- Đọc file lớn hoặc gọi remote discovery service trong bean factory method.
- Đăng ký listener toàn cục không có lifecycle rõ.
- Dùng ApplicationContext.getBean() để tự tra dependency thay cho constructor/method injection.
- Dùng SpEL tham chiếu bean để quyết định condition khi bean có thể khởi tạo quá sớm.

Bean factory method nên tạo object và cấu hình dependency. Việc mở kết nối hoặc thực hiện request nên nằm trong lifecycle/operation được thiết kế rõ, có timeout, cleanup và error handling.

Một context test phải có thể khởi động mà không gọi hệ thống bên ngoài. Điều này làm auto-configuration dễ kiểm thử và giúp ứng dụng không gặp side effect bất ngờ chỉ vì thêm starter.

## 11. Ví dụ hoàn chỉnh: một AuditClient có contract rõ ràng

Phần này ghép các nguyên tắc thành một project tối thiểu chạy được trên Java 17 và Spring Boot 3.3.13. AuditTransport là stand-in nhỏ cho SDK bên ngoài; trong thư viện thật, class này đến từ dependency transport tùy chọn.

### 11.1. Cấu trúc thư mục

```text
acme-audit-autoconfigure/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/audit/
    │   │   ├── AuditClient.java
    │   │   ├── AuditProperties.java
    │   │   ├── AuditTransport.java
    │   │   ├── DefaultAuditClient.java
    │   │   └── autoconfigure/AcmeAuditAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/acme/audit/autoconfigure/
        └── AcmeAuditAutoConfigurationTest.java
```

### 11.2. Maven POM

File pom.xml:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>acme-audit-autoconfigure</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Trong thư viện thực tế, SDK transport có thể được khai báo optional ở module autoconfigure và được starter thêm lại như dependency mặc định. Ví dụ lab đặt AuditTransport trong source để test tự chạy mà không cần vendor SDK.

### 11.3. Output abstraction

File AuditClient.java:

```java
package com.acme.audit;

public interface AuditClient {

    String target();
}
```

Interface này là contract mà ứng dụng consumer sử dụng. Consumer không cần phụ thuộc vào implementation cụ thể.

### 11.4. Input properties

File AuditProperties.java:

```java
package com.acme.audit;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.audit")
public class AuditProperties {

    private URI endpoint = URI.create("https://audit.example.test");

    private Duration timeout = Duration.ofSeconds(3);

    public URI getEndpoint() {
        return this.endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return this.timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

### 11.5. Transport dependency

File AuditTransport.java:

```java
package com.acme.audit;

import java.net.URI;
import java.time.Duration;

public final class AuditTransport {

    public String describe(URI endpoint, Duration timeout) {
        return endpoint + " (timeout=" + timeout + ")";
    }
}
```

Class này đại diện cho API của transport SDK. Method describe chỉ tạo chuỗi để minh họa wiring; nó không thực hiện network I/O.

### 11.6. Default implementation

File DefaultAuditClient.java:

```java
package com.acme.audit;

import java.net.URI;
import java.time.Duration;

public final class DefaultAuditClient implements AuditClient {

    private final AuditTransport transport;

    private final URI endpoint;

    private final Duration timeout;

    public DefaultAuditClient(
            AuditTransport transport,
            URI endpoint,
            Duration timeout) {
        this.transport = transport;
        this.endpoint = endpoint;
        this.timeout = timeout;
    }

    @Override
    public String target() {
        return this.transport.describe(this.endpoint, this.timeout);
    }

    public URI getEndpoint() {
        return this.endpoint;
    }

    public Duration getTimeout() {
        return this.timeout;
    }
}
```

Implementation nhận dependency qua constructor. Không có lookup ngầm từ ApplicationContext và không có kết nối bên ngoài trong constructor.

### 11.7. Auto-configuration class

File AcmeAuditAutoConfiguration.java:

```java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditClient;
import com.acme.audit.AuditProperties;
import com.acme.audit.AuditTransport;
import com.acme.audit.DefaultAuditClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class AcmeAuditAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(AuditTransport.class)
    @ConditionalOnProperty(
            prefix = "acme.audit",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    @EnableConfigurationProperties(AuditProperties.class)
    static class ClientConfiguration {

        @Bean
        @ConditionalOnMissingBean(AuditClient.class)
        DefaultAuditClient auditClient(AuditProperties properties) {
            return new DefaultAuditClient(
                    new AuditTransport(),
                    properties.getEndpoint(),
                    properties.getTimeout());
        }
    }
}
```

Đọc contract của class này:

- **Purpose:** tạo default audit client.
- **Classpath input:** AuditTransport phải có mặt.
- **Property input:** acme.audit.enabled=true.
- **Configuration input:** AuditProperties.
- **Bean input:** chưa có AuditClient do người dùng cung cấp.
- **Output:** một DefaultAuditClient, được inject bằng AuditClient.
- **Back-off:** user AuditClient thắng; default không được tạo.

@ConditionalOnClass nằm trên nested configuration để cô lập type transport tùy chọn. @ConditionalOnMissingBean nằm trên method tạo default, cho phép thay đúng extension point.

### 11.8. Đăng ký auto-configuration

File src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports:

```text
com.acme.audit.autoconfigure.AcmeAuditAutoConfiguration
```

Auto-configuration được Spring Boot phát hiện qua resource này. Không thêm @ComponentScan vào class configuration.

### 11.9. Test bốn contract quan trọng

File AcmeAuditAutoConfigurationTest.java:

```java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditClient;
import com.acme.audit.AuditProperties;
import com.acme.audit.AuditTransport;
import com.acme.audit.DefaultAuditClient;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeAuditAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AcmeAuditAutoConfiguration.class));

    @Test
    void disabledByDefaultCreatesNoAuditClient() {
        this.contextRunner.run(context -> {
            assertThat(context).doesNotHaveBean(AuditClient.class);
            assertThat(context).doesNotHaveBean(AuditProperties.class);
        });
    }

    @Test
    void enabledCreatesDefaultClientAndBindsProperties() {
        this.contextRunner
                .withPropertyValues(
                        "acme.audit.enabled=true",
                        "acme.audit.endpoint=https://audit.internal.example",
                        "acme.audit.timeout=5s")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditClient.class);
                    assertThat(context).hasSingleBean(DefaultAuditClient.class);

                    DefaultAuditClient client =
                            context.getBean(DefaultAuditClient.class);

                    assertThat(client.getEndpoint().toString())
                            .isEqualTo("https://audit.internal.example");
                    assertThat(client.getTimeout())
                            .isEqualTo(java.time.Duration.ofSeconds(5));
                });
    }

    @Test
    void userClientReplacesDefaultClient() {
        this.contextRunner
                .withUserConfiguration(UserAuditConfiguration.class)
                .withPropertyValues("acme.audit.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditClient.class);
                    assertThat(context).doesNotHaveBean(DefaultAuditClient.class);
                    assertThat(context.getBean(AuditClient.class).target())
                            .isEqualTo("custom");
                });
    }

    @Test
    void missingTransportClassDisablesOnlyThisIntegration() {
        this.contextRunner
                .withClassLoader(new FilteredClassLoader(AuditTransport.class))
                .withPropertyValues("acme.audit.enabled=true")
                .run(context -> {
                    assertThat(context.getStartupFailure()).isNull();
                    assertThat(context).doesNotHaveBean(AuditClient.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserAuditConfiguration {

        @Bean
        AuditClient customAuditClient() {
            return () -> "custom";
        }
    }
}
```

Bốn test xác minh:

1. Feature mặc định tắt: không có client và không đăng ký properties bean của nhánh client.
2. Feature bật: default client xuất hiện và endpoint/timeout được bind đúng.
3. User cung cấp client: default implementation back-off.
4. SDK class vắng mặt: context vẫn khởi động, nhánh integration không tạo bean.

FilteredClassLoader mô phỏng classpath thiếu dependency. Đây là cách kiểm tra hữu ích cho auto-configuration có optional SDK.

### 11.10. Chạy test

Từ thư mục project:

```bash
mvn clean test
```

Kết quả mong đợi:

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Summary chi tiết có thể khác theo Maven Surefire version, nhưng cả bốn test phải pass.

### 11.11. Kiểm tra artifact đã đóng gói

Sau khi package:

```bash
mvn clean package
jar tf target/acme-audit-autoconfigure-1.0.0.jar
```

JAR phải chứa:

```text
com/acme/audit/autoconfigure/AcmeAuditAutoConfiguration.class
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Để xác minh end-to-end, nên có một consumer project độc lập chỉ phụ thuộc starter/JAR đã cài hoặc publish. Consumer dùng @EnableAutoConfiguration và kiểm tra bean xuất hiện mà không import class auto-configuration trực tiếp. ApplicationContextRunner ở trên tập trung kiểm tra contract bên trong configuration; consumer smoke test kiểm tra thêm imports resource và packaging.

## 12. Kiểm thử theo ma trận đầu vào/đầu ra

Một test suite tốt thể hiện các kết hợp có ý nghĩa của contract, thay vì chỉ kiểm tra một happy path.

| Classpath | Property | User bean | Kết quả mong đợi |
| --- | --- | --- | --- |
| Có SDK | Missing/false | Không | Không có default client |
| Có SDK | true | Không | Có đúng một default client |
| Có SDK | true | Có AuditClient | User client được giữ, default back-off |
| Không có SDK | true | Không | Context khởi động; không có client của integration |
| Có SDK | true, endpoint override | Không | Client dùng endpoint đã bind |
| Có SDK | true, timeout override | Không | Client dùng timeout đã bind |

Ngoài ma trận chính, hãy kiểm tra:

- Properties validation khi input sai.
- Servlet và reactive contexts nếu có web-specific configuration.
- Hai integration cùng có mặt trên classpath.
- Bean cùng type nhưng khác qualifier nếu thư viện có nhiều client.
- Condition evaluation report khi một test không tạo ra bean mong đợi.

Dùng ConditionEvaluationReportLoggingListener ở mức INFO/DEBUG khi cần xem condition nào match/no-match. Đừng đoán từ việc bean vắng mặt; report sẽ chỉ ra property, classpath hoặc bean condition nào không thỏa.

## 13. Những lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Một class auto-configuration có nhiều bean không liên quan | Nhiều capability bị gom vào một configuration | Chia theo client, web, metrics, integration |
| Không rõ vì sao bean được tạo | Condition nằm rải rác hoặc property name mơ hồ | Viết contract và gom condition theo capability |
| User bean có mặt nhưng default vẫn tạo | @ConditionalOnMissingBean kiểm tra sai type | Condition theo public extension point |
| Auto-configuration lỗi khi SDK vắng mặt | Optional type xuất hiện ở method signature/config ngoài nhánh guarded | Dùng nested configuration có @ConditionalOnClass |
| Bean condition lúc đúng lúc sai | Dựa vào bean definition được xử lý trước đó | Đặt bean condition trong auto-configuration và khai báo ordering khi cần |
| Test pass nhưng starter consumer không chạy | Test import class trực tiếp, bỏ qua discovery | Thêm consumer smoke test qua imports resource |
| Condition nhìn thấy interface nhưng không thấy implementation | Bean method return type quá tổng quát | Trả về concrete implementation type |
| App không thể thay một collaborator nhỏ | Chỉ có cách thay toàn bộ bean | Cân nhắc callback/customizer có contract rõ |
| Bean kết nối hệ thống ngoài ngay khi startup | Constructor/configuration có side effect | Tách object creation khỏi hoạt động I/O |
| Property namespace xung đột | Dùng key thuộc namespace Spring Boot | Dùng prefix riêng của thư viện |
| Condition expression khởi tạo bean quá sớm | SpEL tham chiếu bean trong condition | Dùng property/class/bean condition chuyên biệt |
| Auto-configuration bị quét như component | Package nằm trong component scan | Dùng imports resource và package riêng |

## 14. Quy trình maintain một auto-configuration

Khi thay đổi configuration class, review theo thứ tự:

1. **Mục đích có còn đúng không?** Nếu capability đã tách ra, chuyển bean sang configuration mới.
2. **Đầu vào có thay đổi không?** Classpath, property, bean prerequisite, resource hoặc web type.
3. **Đầu ra có thay đổi không?** Bean type, bean name, default implementation, scope hoặc lifecycle.
4. **Back-off có đúng không?** User bean cũ/mới có còn thay thế default được không?
5. **Ordering có thật sự cần không?** Không dùng order để giải quyết một dependency injection thiếu rõ ràng.
6. **Optional dependency có được cô lập không?** Kiểm tra classloader thiếu SDK.
7. **Tests có thể hiện contract mới không?** Thêm test cho cả nhánh match và no-match.
8. **Metadata/documentation có được cập nhật không?** Mô tả property, default, output bean và migration behavior.

Khi đổi tên auto-configuration class hoặc package, cập nhật imports resource. Nếu class được tham chiếu trong before/after hoặc excludes, xem xét resource replacements của Spring Boot để hỗ trợ chuyển đổi class name. Không để class cũ và class mới cùng đăng ký một nhóm bean mà không có kế hoạch tương thích.

## 15. Checklist review trước khi merge

**Mục đích và ranh giới**

- [ ] Mỗi configuration class mô tả một capability cụ thể.
- [ ] Class không gom bean thuộc các integration có điều kiện đầu vào khác nhau.
- [ ] Package auto-configuration riêng và không phải target của component scanning.
- [ ] Không bật component scanning bên trong auto-configuration.

**Đầu vào**

- [ ] Classpath conditions phản ánh dependency thật sự cần thiết.
- [ ] Optional class được cô lập trong nested configuration.
- [ ] Property conditions dùng prefix riêng và semantics rõ.
- [ ] matchIfMissing phản ánh default ON/OFF đã công bố.
- [ ] Bean conditions kiểm tra đúng public extension point.
- [ ] @ConfigurationProperties có type/default/validation/documentation phù hợp.
- [ ] Resource/web conditions chỉ dùng khi capability cần chúng.

**Đầu ra**

- [ ] Mỗi bean output có type và trách nhiệm rõ ràng.
- [ ] Bean method cung cấp concrete return type khi phù hợp.
- [ ] User bean có thể override default theo contract.
- [ ] Bean name/qualifier/primary có ý nghĩa rõ nếu có nhiều bean cùng type.
- [ ] Bean factory không thực hiện side effect bên ngoài không cần thiết.

**Ordering và maintainability**

- [ ] @AutoConfigureBefore/@AutoConfigureAfter chỉ dùng khi có phụ thuộc thực.
- [ ] Không nhầm auto-configuration order với bean instantiation order.
- [ ] Optional integration được tách theo capability khi dependency graph cần.
- [ ] Imports resource chứa đúng FQCN và nằm trong JAR.

**Testing**

- [ ] Có test feature disabled/default behavior.
- [ ] Có test feature enabled và property binding.
- [ ] Có test user bean back-off.
- [ ] Có test optional dependency missing bằng FilteredClassLoader.
- [ ] Có test web context nếu configuration phụ thuộc web type.
- [ ] Có test consumer artifact/discovery qua imports resource.
- [ ] Có thể đọc Condition Evaluation Report khi test thất bại.

**Ghi nhớ:** Một auto-configuration dễ bảo trì khi người đọc nhìn vào class là hiểu ngay nó cung cấp capability nào, cần class/property/bean nào và tạo ra bean gì. Viết contract trước, gom condition theo capability, dùng properties có kiểu, trả về bean type cụ thể và để user bean thay thế default đúng extension point. Tách optional integrations, kiểm soát ordering có lý do và dùng ApplicationContextRunner để kiểm tra từng tổ hợp đầu vào. Khi mục đích, đầu vào và đầu ra rõ ràng, configuration sẽ dễ mở rộng mà không biến thành một khối bean khó dự đoán.

## Tài liệu chính thức

- Spring Boot 3.3.13 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3.13 — Externalized Configuration and ConfigurationProperties: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3.13 API — AutoConfiguration: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.3.13 API — ConditionalOnMissingBean: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot 3.3.13 API — ConditionalOnClass: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.3.13 API — ConditionalOnProperty: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html

# BeanFactoryPostProcessor, BeanDefinitionRegistryPostProcessor và điểm cần kiểm tra

Spring cung cấp hai extension point quan trọng để can thiệp vào cấu hình của container trước khi phần lớn bean nghiệp vụ được tạo: **BeanFactoryPostProcessor (BFPP)** và **BeanDefinitionRegistryPostProcessor (BDRPP)**. Chúng có liên hệ với nhau nhưng phục vụ hai nhiệm vụ khác nhau: BFPP xử lý cấu hình của BeanFactory sau khi các bean definitions đã được đăng ký; BDRPP được gọi sớm hơn để có thể bổ sung hoặc điều chỉnh chính tập bean definitions.

Khi biên dịch Spring Boot thành GraalVM Native Image, khác biệt này trở nên đặc biệt quan trọng. Spring AOT cần phân tích được cấu trúc bean tại build time để sinh mã khởi tạo. Một processor đăng ký bean theo dữ liệu chỉ xuất hiện khi ứng dụng chạy có thể làm cho tập bean ở build time và runtime khác nhau, khiến generated context không còn phản ánh đúng ứng dụng mong muốn.

Bài này giải thích vai trò, thứ tự gọi, cách đăng ký, ví dụ thực tế và các điểm phải kiểm tra khi dùng BFPP/BDRPP trong ứng dụng Spring Boot AOT/native.

## 1. Hai processor can thiệp vào tầng nào?

Trước tiên cần nhớ ba loại đối tượng:

- **BeanDefinition:** metadata mô tả bean, như class, constructor/factory method, scope, lazy flag, dependency và các giá trị cấu hình.
- **Bean instance:** object Java thực tế được tạo từ definition và được container quản lý.
- **BeanFactory:** thành phần lưu definitions, tạo instance, phân giải dependency và quản lý vòng đời bean.

BFPP và BDRPP chủ yếu làm việc với **metadata và cấu trúc factory**. Chúng không phải công cụ thông thường để sửa trạng thái nghiệp vụ trên object đã được tạo.

### BeanFactoryPostProcessor

BFPP nhận ConfigurableListableBeanFactory và có thể kiểm tra hoặc sửa các bean definitions đã đăng ký, ví dụ:

- Thay đổi property values hoặc metadata của một definition.
- Điều chỉnh scope, lazy initialization hoặc một số cờ của bean.
- Đăng ký các dependency có thể phân giải ở cấp factory khi phù hợp.
- Thực hiện thao tác cấu hình container trước khi các singleton thông thường được khởi tạo.

BFPP được chạy sau giai đoạn đăng ký bean definitions. Nó phù hợp khi cần **chỉnh metadata đã tồn tại** hoặc cấu hình BeanFactory.

### BeanDefinitionRegistryPostProcessor

BDRPP là một loại BFPP chuyên biệt, mở rộng BFPP và bổ sung callback:

~~~java
void postProcessBeanDefinitionRegistry(BeanDefinitionRegistry registry);
~~~

Callback này được gọi khi registry còn có thể nhận thêm definitions. BDRPP có thể:

- Đăng ký một bean definition mới.
- Kiểm tra definition đã tồn tại trước khi thêm.
- Điều chỉnh hoặc thay thế metadata theo quy tắc rõ ràng.
- Phát hiện cấu hình đã đăng ký và bổ sung các bean liên quan.

Sau callback registry, BDRPP còn có callback postProcessBeanFactory kế thừa từ BFPP. Vì vậy, BDRPP có thể tham gia cả giai đoạn xử lý registry lẫn giai đoạn xử lý BeanFactory.

| Tiêu chí | BFPP | BDRPP |
| --- | --- | --- |
| Mục đích chính | Điều chỉnh BeanFactory và definitions đã có | Điều chỉnh registry, đặc biệt là đăng ký thêm definitions |
| Callback đặc trưng | postProcessBeanFactory | postProcessBeanDefinitionRegistry, sau đó là postProcessBeanFactory |
| Thời điểm | Sau các BDRPP registry callbacks | Sớm hơn các BFPP thông thường |
| Có thể thêm bean definitions ở callback chuyên biệt? | Không có registry callback chuyên biệt; nên dùng BDRPP cho nhiệm vụ này | Có |
| Có nên tạo bean nghiệp vụ ở đây? | Không | Không |
| Ảnh hưởng đến AOT | Có thể làm thay đổi metadata mà AOT phân tích | Có thể làm thay đổi tập bean definitions được AOT ghi nhận |

**Quy tắc chọn nhanh:** cần thêm bean definition thì cân nhắc BDRPP; cần điều chỉnh metadata của những definition đã đăng ký thì cân nhắc BFPP. Nếu chỉ cần khai báo bean thông thường, ưu tiên @Component, @Bean, auto-configuration hoặc @Import thay vì tự viết post-processor.

## 2. Phân biệt với BeanPostProcessor

Tên hai loại processor khá giống nhau, nhưng chúng xử lý hai tầng khác nhau.

| Processor | Đối tượng tác động | Thời điểm chính | Ví dụ nhiệm vụ |
| --- | --- | --- | --- |
| BeanDefinitionRegistryPostProcessor | Registry chứa bean definitions | Trước BFPP thông thường | Đăng ký definition cho một implementation |
| BeanFactoryPostProcessor | BeanFactory và metadata definitions | Trước khi phần lớn singleton thông thường được tạo | Đặt lazy flag hoặc sửa property metadata |
| BeanPostProcessor | Bean instance | Trong quá trình tạo và khởi tạo từng bean | Bọc proxy, xử lý annotation, can thiệp trước/sau initialization |

Ví dụ, một BeanPostProcessor có thể bọc bean bằng proxy sau khi object được khởi tạo để áp dụng hành vi bổ sung. BFPP không phải nơi để làm việc đó: khi BFPP chạy, instance nghiệp vụ thường chưa được tạo. Ngược lại, nếu cần thêm definition để Spring biết một bean tồn tại, BeanPostProcessor đã quá muộn.

## 3. Thứ tự xử lý trong quá trình khởi tạo ApplicationContext

Trong một Spring ApplicationContext thông thường, trình tự khái quát như sau:

~~~mermaid
flowchart TD
    A["Đọc cấu hình và đăng ký bean definitions"] --> B["Tìm BeanDefinitionRegistryPostProcessor"]
    B --> C["Gọi postProcessBeanDefinitionRegistry"]
    C --> D["Gọi postProcessBeanFactory của các BDRPP"]
    D --> E["Gọi BeanFactoryPostProcessor thông thường"]
    E --> F["Đăng ký BeanPostProcessor"]
    F --> G["Tạo các singleton eager thông thường"]
    G --> H["Dependency injection và initialization callbacks"]
    H --> I["Context sẵn sàng"]
~~~

Đây là sơ đồ khái quát cho quá trình refresh. Các processor hạ tầng có thể được khởi tạo sớm để phục vụ các bước trước đó; không nên hiểu mọi object trong ứng dụng đều đợi tới bước G mới được tạo.

### Thứ tự theo PriorityOrdered và Ordered

Spring hỗ trợ sắp xếp processor theo các interface:

1. Processor triển khai PriorityOrdered được xử lý trước nhóm Ordered.
2. Trong mỗi nhóm có hỗ trợ sắp xếp, giá trị getOrder() nhỏ hơn thường có độ ưu tiên cao hơn.
3. Processor không triển khai các interface ordering được xử lý sau các nhóm có thứ tự.

Đối với BDRPP, Spring xử lý registry callbacks trước BFPP thông thường. Spring còn có thể phát hiện BDRPP mới được đăng ký trong quá trình xử lý và tiếp tục xử lý registry trước khi chuyển sang các BFPP thông thường.

Không nên dựa vào một con số order nội bộ của framework nếu ứng dụng không có yêu cầu rõ ràng. Nếu hai processor phụ thuộc nhau, hãy làm cho quan hệ đó tường minh, tránh giả định thứ tự tình cờ do thứ tự khai báo bean hoặc tên class.

### Một BDRPP có hai callback

BDRPP vừa có callback registry vừa có callback BeanFactory. Về mặt khái niệm:

~~~java
public final class ExampleRegistryProcessor
        implements BeanDefinitionRegistryPostProcessor {

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) {
        // Thêm hoặc điều chỉnh bean definitions.
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
        // Xử lý BeanFactory sau giai đoạn registry.
    }
}
~~~

Callback registry dành cho thao tác trên definitions. Callback BeanFactory là nơi thực hiện phần việc tương ứng với BFPP. Nếu không có việc gì cần làm ở callback thứ hai, có thể để thân phương thức rỗng.

## 4. Ví dụ BDRPP: đăng ký một bean definition theo quy tắc cố định

Giả sử ứng dụng có một dịch vụ tính phí tùy chọn. Khi cấu hình ứng dụng yêu cầu đưa dịch vụ này vào context, ta muốn đăng ký definition bằng BDRPP. Ví dụ dưới đây dùng một điều kiện cố định trong mã để tập trung vào thao tác registry; trong dự án thực tế, hãy chọn cơ chế cấu hình phù hợp và bảo đảm điều kiện có thể xác định ở pha AOT.

**FeatureService.java**

~~~java
package com.example.nativeimage;

public final class FeatureService {
    public String status() {
        return "feature-enabled";
    }
}
~~~

**FeatureServiceRegistry.java**

~~~java
package com.example.nativeimage;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor;
import org.springframework.beans.factory.support.RootBeanDefinition;

public final class FeatureServiceRegistry
        implements BeanDefinitionRegistryPostProcessor {

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) throws BeansException {

        String beanName = "featureService";

        if (!registry.containsBeanDefinition(beanName)) {
            RootBeanDefinition definition =
                    new RootBeanDefinition(FeatureService.class);
            registry.registerBeanDefinition(beanName, definition);
        }
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) throws BeansException {
        // Không cần chỉnh BeanFactory trong ví dụ này.
    }
}
~~~

**FeatureRegistryConfiguration.java**

~~~java
package com.example.nativeimage;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeatureRegistryConfiguration {

    @Bean
    public static FeatureServiceRegistry featureServiceRegistry() {
        return new FeatureServiceRegistry();
    }
}
~~~

Ở đây:

- FeatureServiceRegistry đăng ký definition tên featureService nếu registry chưa có definition cùng tên.
- RootBeanDefinition mô tả class mà container sẽ tạo khi cần instance.
- Phương thức @Bean khai báo processor là static để tránh phải khởi tạo sớm configuration class chỉ nhằm lấy BFPP/BDRPP.
- Definition được đăng ký không có nghĩa FeatureService instance đã được tạo ngay tại callback.

Với ứng dụng thực tế, cần bảo đảm FeatureService nằm trong classpath khi build native, và những reflection/resource/proxy mà dịch vụ cần đã được Spring hoặc thư viện khai báo hints thích hợp.

### Vì sao phải kiểm tra tên bean trước khi đăng ký?

Gọi registerBeanDefinition với tên đã tồn tại có thể dẫn đến ghi đè hoặc lỗi tùy chính sách registry/container. Kiểm tra containsBeanDefinition giúp quy tắc đăng ký rõ ràng hơn. Tuy nhiên, nếu tên đã tồn tại mà đó là definition không tương thích, im lặng bỏ qua có thể che giấu lỗi cấu hình. Trong ứng dụng production, hãy quyết định rõ nên giữ definition cũ, thay thế có chủ đích hay báo lỗi.

## 5. Ví dụ BFPP: điều chỉnh metadata của definition đã có

Giả sử ReportService được đăng ký bằng một phương thức @Bean. Ta muốn đặt lazy initialization cho definition này bằng BFPP:

~~~java
package com.example.nativeimage;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;

public final class ReportLazyPostProcessor
        implements BeanFactoryPostProcessor {

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory)
            throws BeansException {

        String beanName = "reportService";

        if (beanFactory.containsBeanDefinition(beanName)) {
            BeanDefinition definition =
                    beanFactory.getBeanDefinition(beanName);
            definition.setLazyInit(true);
        }
    }
}
~~~

Đăng ký processor bằng một phương thức static:

~~~java
@Configuration(proxyBeanMethods = false)
class ReportConfiguration {

    @Bean
    static ReportLazyPostProcessor reportLazyPostProcessor() {
        return new ReportLazyPostProcessor();
    }

    @Bean
    ReportService reportService() {
        return new ReportService();
    }
}
~~~

Kết quả mong đợi là definition của reportService được đánh dấu lazy trước khi Spring tạo các singleton eager thông thường. Khi có bean eager khác phụ thuộc vào ReportService, dependency đó vẫn có thể khiến service được tạo sớm. Lazy flag không phải cam kết rằng object sẽ chỉ được tạo khi có HTTP request đầu tiên trong mọi tình huống.

Ví dụ này cũng cho thấy BFPP làm việc với **BeanDefinition**, không cần gọi getBean("reportService") để lấy instance rồi thay đổi object.

## 6. Đăng ký processor đúng cách và tránh khởi tạo sớm

BFPP/BDRPP là thành phần hạ tầng đặc biệt. Spring cần phát hiện và gọi chúng **trước khi tạo phần lớn bean thông thường**. Cách khai báo ảnh hưởng đến việc framework có nhận diện processor đúng lúc hay không.

### Khuyến nghị dùng static @Bean

Khi đăng ký processor trong @Configuration, nên khai báo factory method static:

~~~java
@Configuration(proxyBeanMethods = false)
class InfrastructureConfiguration {

    @Bean
    static FeatureServiceRegistry featureServiceRegistry() {
        return new FeatureServiceRegistry();
    }
}
~~~

Lý do: để gọi một factory method không static, Spring có thể phải khởi tạo configuration class chứa method đó sớm. Việc này có thể làm configuration class và các dependency liên quan được tạo trước khi toàn bộ BeanPostProcessor được đăng ký. Spring thường cảnh báo khi một bean được tạo quá sớm và không được xử lý qua tất cả post-processors.

### Khai báo kiểu trả về cụ thể

Nên khai báo return type là class processor cụ thể hoặc interface processor mà Spring có thể nhận diện:

~~~java
@Bean
static BeanFactoryPostProcessor timeoutPostProcessor() {
    return new TimeoutPostProcessor();
}
~~~

Không nên khai báo quá chung như Object nếu Spring không thể dự đoán kiểu processor mà không phải khởi tạo bean. Kiểu trả về rõ ràng giúp container phát hiện processor trong giai đoạn tìm kiếm sớm.

### Giữ processor nhẹ và ít dependency

Không nên inject một graph bean nghiệp vụ lớn vào constructor của BFPP/BDRPP. Processor được tạo sớm; việc inject các dependency khác có thể kéo chúng lên trước thời điểm dự kiến và làm một số bean bỏ lỡ quá trình xử lý đầy đủ của BeanPostProcessor.

Ưu tiên:

- Dùng các tham số cấu hình đơn giản, ổn định.
- Làm việc trực tiếp với registry/BeanFactory metadata.
- Tránh gọi beanFactory.getBean(...) để lấy bean nghiệp vụ.
- Tránh truy cập database, HTTP API, message broker hoặc hệ thống ngoài.
- Không dùng processor để chạy nghiệp vụ, ghi dữ liệu hay tạo side effect production.

Nếu cần đọc cấu hình, hãy dùng nguồn cấu hình thích hợp và xác định rõ giá trị đó thuộc build time hay runtime. Đặc biệt với AOT, không giả định biến môi trường của máy build giống môi trường container production.

## 7. Processor quan trọng có sẵn trong Spring

Một ví dụ điển hình của BDRPP là ConfigurationClassPostProcessor. Đây là processor hạ tầng của Spring, chịu trách nhiệm xử lý các cấu hình Java dựa trên @Configuration và các annotation liên quan.

Nó giúp phát hiện và xử lý các cấu trúc như:

- @Bean để đăng ký bean definitions từ factory methods.
- @ComponentScan để tìm component.
- @Import để nhập thêm cấu hình hoặc registrar.
- @ImportResource để nạp cấu hình resource được hỗ trợ.
- Các điều kiện và metadata cấu hình liên quan.

Có thể hình dung quá trình:

~~~mermaid
flowchart TD
    A["Configuration class và annotation"] --> B["ConfigurationClassPostProcessor"]
    B --> C["Phân tích @Bean, @ComponentScan, @Import"]
    C --> D["Đăng ký thêm BeanDefinition"]
    D --> E["Các BFPP xử lý BeanFactory"]
    E --> F["Spring tạo bean instances theo lifecycle"]
~~~

Điều này giải thích vì sao BDRPP chạy trước BFPP thông thường: Spring cần hoàn tất việc phát hiện cấu hình và đăng ký definitions trước khi các processor khác chỉnh sửa BeanFactory dựa trên tập definitions đó.

Nếu một yêu cầu chỉ là thêm cấu hình qua @Import, ImportBeanDefinitionRegistrar có thể là extension point phù hợp hơn việc viết BDRPP toàn cục. Nếu chỉ cần khai báo một bean cố định, @Bean hoặc component scanning thường đơn giản và dễ phân tích AOT hơn.

## 8. Spring AOT xử lý các processor như thế nào?

Spring AOT phân tích ApplicationContext trước khi native compilation. Trong quá trình này, Spring dựng và xử lý mô hình container để biết bean definitions, quan hệ dependency và các metadata cần thiết. Các BDRPP/BFPP có thể tham gia vào quá trình hình thành BeanFactory này.

Kết quả AOT có thể gồm:

- Mã đăng ký các bean definitions mà Spring đã nhận diện.
- Mã hỗ trợ khởi tạo application context.
- Các đóng góp AOT từ framework hoặc thư viện.
- Runtime hints cho những thao tác reflection, resource, proxy hoặc JNI cần thiết.

~~~mermaid
flowchart TD
    S["Source + cấu hình + dependencies"] --> A["Spring AOT phân tích ApplicationContext"]
    A --> R["BDRPP đăng ký definitions"]
    R --> F["BFPP xử lý BeanFactory metadata"]
    F --> G["AOT contributions và generated registrations"]
    G --> H["GraalVM Native Image compilation"]
    H --> N["Native executable"]
    N --> X["Runtime: tạo bean instances và phục vụ request"]
~~~

Điểm cần hiểu:

1. **Processor có thể chạy trong pha AOT:** khi Spring phân tích context để tạo mô hình và generated code, các post-processors liên quan được dùng để xử lý registry/factory.
2. **Definitions được hình thành ở build time:** nếu processor đăng ký bean dựa trên điều kiện cố định và class có sẵn, AOT có thể ghi nhận cấu trúc đó trong mã sinh ra.
3. **Bean instance vẫn thuộc vòng đời runtime:** generated code mô tả cách khởi tạo context/bean; nó không có nghĩa object nghiệp vụ được tạo ở build rồi mang sang production.
4. **Không dựa vào side effect “chạy đúng một lần”:** tùy loại processor, integration và cách đăng ký, logic liên quan có thể được thực thi trong quá trình phân tích AOT và/hoặc trong quá trình khởi tạo context. Hãy dùng contract AOT chính thức của phiên bản Spring đang dùng thay vì dựa vào thứ tự tình cờ.

Nếu processor có logic đặc thù cần đóng góp mã AOT, Spring cung cấp các extension SPI chuyên cho AOT, chẳng hạn BeanFactoryInitializationAotProcessor và BeanRegistrationAotProcessor. Nếu cần mô tả khả năng truy cập động cho Native Image, hãy dùng runtime hints phù hợp, ví dụ RuntimeHintsRegistrar. Không nên biến một BFPP thông thường thành nơi chứa mọi logic code generation và reflection registration.

## 9. Vì sao đăng ký bean động có thể gây vấn đề với Native Image?

Native Image sử dụng giả định closed-world: mã, kiểu và các thao tác truy cập động cần thiết phải được xác định hoặc khai báo trong lúc build. Vì vậy, tập bean definitions mà Spring AOT phân tích cần phản ánh được các cấu trúc ứng dụng mà binary phải hỗ trợ.

### Tình huống dễ lỗi

Giả sử BDRPP đọc database khi ứng dụng chạy và đăng ký một bean cho từng plugin:

~~~java
// Ý tưởng không phù hợp nếu danh sách plugin chỉ tồn tại ở runtime.
for (PluginRecord plugin : pluginRepository.loadPlugins()) {
    registry.registerBeanDefinition(
            plugin.beanName(),
            createDefinition(plugin.className())
    );
}
~~~

Đoạn ý tưởng trên có nhiều vấn đề trong AOT/native:

- Database có thể chưa sẵn sàng hoặc không tồn tại ở build time.
- Danh sách plugin ở máy build có thể khác production.
- Tên class đến từ dữ liệu runtime không chứng minh class đó có trong native binary.
- Reflection constructor/method và resource mà plugin cần có thể chưa được đăng ký.
- Tập definitions được generated code ghi nhận có thể không tương ứng với plugin production.

Ngay cả khi BDRPP có thể chạy trên JVM, điều đó không đảm bảo kiến trúc động như vậy tương thích với AOT.

### Thiết kế thân thiện với AOT hơn

Nếu danh sách implementation là hữu hạn và biết trước, hãy đưa các implementation vào classpath/build và đăng ký chúng theo một cấu hình có thể phân tích:

~~~java
@Configuration(proxyBeanMethods = false)
class PluginConfiguration {

    @Bean
    UppercasePlugin uppercasePlugin() {
        return new UppercasePlugin();
    }

    @Bean
    LowercasePlugin lowercasePlugin() {
        return new LowercasePlugin();
    }
}
~~~

Khi chạy, ứng dụng có thể chọn một implementation theo cấu hình hoặc request thông qua một factory/strategy đã được đăng ký. Nếu cần nạp code Java mới hoàn toàn sau khi build, hãy xem xét ranh giới process/plugin service riêng; native executable không phải class loader mở để thêm tùy ý JAR mới.

### Phân biệt điều kiện build time và dữ liệu runtime

| Loại quyết định | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Quyết định bean definition có tồn tại trong context không | @ConditionalOnProperty, profile, custom registry processor | Xác định điều kiện trong pha AOT; build artifact cho tập cấu hình cần hỗ trợ |
| Chọn implementation đã có sẵn | Chọn một strategy trong các bean đã đăng ký | Có thể quyết định lúc runtime bằng factory/strategy |
| Giá trị cấu hình của instance | URL, timeout, token, credentials | Đọc qua cấu hình runtime phù hợp, không đóng băng bí mật vào binary |
| Plugin class mới từ JAR ngoài | Tải class chưa có trong build input | Không thể mặc nhiên hỗ trợ bằng native executable đã build; cần kiến trúc khác hoặc rebuild |

**Nguyên tắc:** có thể chọn dữ liệu runtime giữa những bean và class đã được chuẩn bị cho binary; không nên mong runtime tự mở rộng tùy ý tập class/definition mà AOT không biết.

## 10. Các điểm cần kiểm tra trong code review

Khi review một BFPP/BDRPP trong dự án Spring Boot Native Image, hãy xem các câu hỏi sau:

| Điểm kiểm tra | Dấu hiệu tốt | Dấu hiệu cần xem lại |
| --- | --- | --- |
| Mục đích | Chỉ xử lý metadata/registry phù hợp | Dùng processor để chạy nghiệp vụ hoặc tạo object tùy tiện |
| Đăng ký processor | @Bean static, kiểu trả về rõ ràng | Factory method non-static hoặc return type quá chung |
| Dependency | Nhẹ, không kéo theo graph bean lớn | Constructor inject repository/service/client |
| Tác động registry | Tên rõ ràng, kiểm tra tồn tại, quy tắc idempotent | Đăng ký trùng, ghi đè không chủ ý |
| Điều kiện | Dựa trên cấu hình có thể xác định khi AOT | Dựa trên database/network/request chỉ có lúc runtime |
| Ordering | Chỉ định khi có dependency thật sự và có test | Dựa vào order nội bộ hoặc thứ tự khai báo |
| AOT | Kết quả registration có thể tái lập, có test AOT/native | Dựa vào side effect không ổn định |
| Reflection/resource | Có hints khi cần, đúng member/resource | Chỉ vì definition tồn tại mà cho rằng mọi truy cập động đã được hỗ trợ |
| Phiên bản | Dùng API phù hợp Spring Framework/Boot đã pin | Dựa vào internal API hoặc cấu trúc generated code của version khác |

### Một số dấu hiệu cần tránh

- Gọi getBean bên trong postProcessBeanFactory chỉ để thay đổi một bean nghiệp vụ.
- Khởi tạo kết nối database hoặc gọi HTTP trong registry callback.
- Đọc danh sách plugin từ file ngoài mà file đó có thể khác giữa build và runtime.
- Đăng ký definition với tên cố định mà không kiểm tra registry.
- Dùng một post-processor để thay thế cơ chế auto-configuration hoặc configuration class đơn giản.
- Giả định generated source có một tên package/file cố định qua mọi phiên bản Spring.
- Sửa trực tiếp mã sinh ra trong thư mục build thay vì sửa processor/configuration gốc.

## 11. Cách kiểm tra khi ứng dụng không chạy như mong đợi

Chẩn đoán theo từng tầng sẽ tiết kiệm thời gian hơn việc thêm reflection hints ngay khi thấy lỗi native.

### Bước 1: Xác định definition có tồn tại không

Dùng BeanFactory để kiểm tra definition:

~~~java
ConfigurableListableBeanFactory beanFactory =
        context.getBeanFactory();

boolean definitionExists =
        beanFactory.containsBeanDefinition("featureService");

System.out.println("definitionExists=" + definitionExists);
~~~

Nếu false, kiểm tra component scanning, @Import, profile/condition và BDRPP có được đăng ký/chạy không. Nếu bean được đăng ký bằng alias hoặc factory khác, cần kiểm tra đúng tên/loại bean.

### Bước 2: Phân biệt definition với singleton instance

~~~java
boolean singletonCreated =
        beanFactory.containsSingleton("featureService");

System.out.println("singletonCreated=" + singletonCreated);
~~~

Một definition tồn tại nhưng singleton chưa được tạo là điều bình thường nếu bean lazy, prototype hoặc chưa được yêu cầu. Không kết luận registry processor thất bại chỉ vì containsSingleton trả false.

### Bước 3: Xem log processor và thời điểm khởi tạo

Ghi log ở đầu mỗi callback để biết processor có được gọi hay không. Tránh ghi dữ liệu nhạy cảm hoặc gọi side effect trong log. Quan sát cả build-time AOT logs và log của native executable khi chạy.

### Bước 4: Xác minh AOT generated output

Chạy AOT processing theo cấu hình Maven/Gradle của project. Ví dụ với một project Maven đã bind goal vào profile native:

~~~bash
./mvnw -Pnative clean process-classes
~~~

Với Gradle Native Build Tools đã được cấu hình:

~~~bash
./gradlew processAot
~~~

Các task/goal và vị trí output phụ thuộc phiên bản plugin. Hãy xem log và thư mục generated source của chính project. Không sửa generated code; sửa processor hoặc configuration nguồn rồi chạy lại AOT.

### Bước 5: Kiểm thử bản native

Build native executable theo toolchain của project và chạy các đường nghiệp vụ có dùng bean được đăng ký. Nếu definition đã tồn tại nhưng lỗi chỉ xuất hiện khi gọi method, kiểm tra dependency, initialization callback, reflection/resource/proxy và metadata Native Image.

## 12. Lỗi phổ biến và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| BDRPP không được gọi | Processor chưa được đăng ký hoặc kiểu trả về không được nhận diện sớm | Kiểm tra bean definition của processor, static @Bean, return type và log |
| Bean definition không xuất hiện | Registry callback không chạy hoặc điều kiện đăng ký false | Kiểm tra profile/condition, thứ tự processor, classpath và tên bean |
| Definition có nhưng bean không tạo được | Constructor/factory method/dependency lỗi | Kiểm tra exception gốc, dependency graph và cấu hình instance |
| Configuration class được tạo quá sớm | Processor đăng ký qua factory method non-static hoặc kéo dependency sớm | Dùng static @Bean, giảm dependency của processor |
| Bean được tạo trước khi có đủ proxy/post-processing | Processor hoặc dependency bị khởi tạo quá sớm | Không gọi getBean trong BFPP/BDRPP; kiểm tra warning về bean chưa được xử lý đầy đủ |
| Duplicate bean definition | Nhiều processor cùng đăng ký hoặc không kiểm tra tên | Xác định ownership, đặt quy tắc idempotent và xử lý xung đột rõ ràng |
| JVM chạy nhưng native thiếu reflection | Type/member được truy cập động chưa có hints | Đăng ký đúng reflection metadata hoặc dùng API/framework có AOT support |
| Native thiếu resource | File không được đóng gói hoặc pattern không khớp | Kiểm tra resource input và resource hints |
| Bean khác nhau giữa build và runtime | Processor dựa vào dữ liệu môi trường hoặc hệ thống ngoài | Chuyển quyết định cấu trúc về build time hoặc đăng ký tập implementation cố định |
| Processor chạy lặp gây side effect | Giả định callback chỉ chạy một lần hoặc build/runtime không được tách rõ | Làm processor deterministic, tránh side effect và dùng AOT SPI đúng mục đích |

## 13. Bài thực hành: kiểm tra một BDRPP trong Spring AOT

Tạo một ứng dụng Spring Boot nhỏ với hai class:

- FeatureService có method status() trả về chuỗi cố định.
- FeatureServiceRegistry triển khai BeanDefinitionRegistryPostProcessor và đăng ký definition tên featureService nếu chưa có.

Đăng ký processor bằng một @Bean static trong configuration class. Sau đó thực hiện:

1. Chạy ứng dụng trên JVM và kiểm tra containsBeanDefinition("featureService").
2. Kiểm tra containsSingleton("featureService") trước và sau khi gọi getBean để thấy khác biệt giữa definition và instance.
3. Chạy Spring AOT processing và xem processor có được thực thi trong pha phân tích không.
4. Build native executable và kiểm tra cùng bean trên bản native.
5. Thêm một điều kiện đăng ký dựa trên property, sau đó thay đổi property giữa build và runtime để quan sát điều kiện nào được quyết định trong AOT.
6. Thêm một lời gọi reflection trong FeatureService (nếu muốn mở rộng) và kiểm tra riêng runtime hints cần thiết.

### Câu hỏi tự kiểm tra

1. Vì sao BDRPP được xử lý trước BFPP thông thường?
2. BFPP có thể sửa lazy flag của definition đã đăng ký như thế nào?
3. Vì sao phương thức @Bean khai báo BFPP/BDRPP nên là static?
4. Tại sao gọi getBean bên trong BFPP có thể gây khởi tạo bean quá sớm?
5. Một BDRPP đăng ký bean dựa trên danh sách plugin lấy từ database production có phù hợp với Spring AOT không? Vì sao?
6. Definition đã xuất hiện trong generated AOT code có bảo đảm mọi reflection bên trong bean hoạt động trong native không?
7. Khi cần custom AOT code generation, vì sao nên xem các AOT SPI thay vì chỉ dựa vào side effect của BFPP?

**Tiêu chí đạt:** phân biệt đúng BFPP, BDRPP và BeanPostProcessor; mô tả được thứ tự registry/factory callbacks; viết được processor an toàn và đăng ký đúng cách; giải thích được tác động của processor tới Spring AOT; đồng thời chẩn đoán riêng lỗi thiếu definition, lỗi tạo instance và lỗi reachability metadata trong GraalVM Native Image.

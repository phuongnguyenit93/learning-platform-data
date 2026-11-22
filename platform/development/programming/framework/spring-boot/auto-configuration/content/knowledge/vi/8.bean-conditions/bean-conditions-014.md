# Ảnh hưởng của thông tin kiểu không đầy đủ, `FactoryBean` và bean đăng ký gián tiếp

## Mục tiêu

Khi thiết kế auto-configuration, ta dễ gặp nghịch lý: trong ứng dụng **có** một bean nhưng `@ConditionalOnBean` báo không tìm thấy, hoặc `@ConditionalOnMissingBean` vẫn đăng ký bean dự phòng, gây trùng lặp. Ba nguyên nhân thường bị bỏ sót là **thông tin kiểu (type metadata) chưa đủ**, **bean do `FactoryBean` tạo ra**, và **bean được đăng ký gián tiếp hoặc quá muộn**.

Sau bài này, bạn có thể phân biệt bean definition với đối tượng thực tế, dự đoán kết quả điều kiện theo kiểu đã khai báo, nhận diện chính xác sản phẩm của `FactoryBean`, kiểm tra thời điểm đăng ký bean và viết bài kiểm thử cô lập cho các trường hợp này. Ví dụ hướng đến Spring Boot 3.3.x, Spring Framework 6.1 và Java 17+.

## 1. Điều kiện bean thực sự “nhìn thấy” điều gì?

`@ConditionalOnBean`, `@ConditionalOnMissingBean` và `@ConditionalOnSingleCandidate` thuộc nhóm điều kiện trên **những bean definition đã được xử lý tại thời điểm đánh giá**. Điều kiện tra cứu thông tin mà `BeanFactory` hiện có; nó không chờ tất cả singleton được khởi tạo rồi mới xem kiểu thực tế.

- `@ConditionalOnBean(T.class)`: chỉ khớp khi đã có ứng viên thỏa yêu cầu `T`. Nếu chỉ rõ nhiều kiểu/tên/annotation, mọi yêu cầu phải được thỏa, nhưng không nhất thiết trên cùng một bean.
- `@ConditionalOnMissingBean(T.class)`: khớp khi **chưa có** ứng viên thỏa yêu cầu tương ứng. Nếu đã tồn tại bean thực tế nhưng hệ thống chưa thể nhận diện nó như `T`, điều kiện có thể cho kết quả “missing”.
- `@ConditionalOnSingleCandidate(T.class)`: cần một ứng viên có thể xác định duy nhất; có thể khớp khi có nhiều bean kiểu `T` nhưng một bean được chọn làm `@Primary`. Nó cũng phụ thuộc vào thông tin kiểu và thời điểm.
- Trên phương thức `@Bean`, khi không chỉ định `value`, `type` hoặc `name`, kiểu mặc định để kiểm tra là **kiểu trả về đã khai báo của phương thức**, không phải kiểu runtime của đối tượng được trả về.
- Tham số `search` kiểm soát có tra cứu parent context hay không (mặc định `SearchStrategy.ALL`); `name` kiểm tra theo tên, `annotation` kiểm tra annotation, `parameterizedContainer` cho phép nhận diện kiểu được chứa trong generic container được chỉ định. Đây là các tiêu chí khác nhau; tra theo tên có thể hữu ích khi kiểu sản phẩm chưa suy luận được, nhưng phải chắc chắn tên là hợp đồng ổn định.

Mô hình cần giữ trong đầu:

```text
Bean được định nghĩa / phát hiện
          |
          v
BeanDefinition đăng ký vào BeanFactory ở thời điểm t?
          | không -> điều kiện chưa thể thấy ứng viên
          v có
Container biết ứng viên mang kiểu/thuộc tính nào?
          | metadata quá chung hoặc không xác định
          v
OnBeanCondition so khớp type / name / annotation + search
          |
          +--> match / no match -> quyết định đăng ký definition có điều kiện
          |
          v
Sau đó: khởi tạo đối tượng, inject dependency, dùng bean
```

**“Không nhìn thấy kiểu `T`” không đồng nghĩa “không có bean nào”,** và **“có class `T` trên classpath” không đồng nghĩa “đã có bean `T`”**. `@ConditionalOnClass` giải quyết câu hỏi thứ hai về classpath, còn điều kiện bean giải quyết trạng thái của `BeanFactory`.

## 2. Thông tin kiểu không đầy đủ: method trả về interface, `Object` hoặc generic thô

Xét ví dụ:

```java
interface PaymentGateway {
    String pay();
}
final class CardGateway implements PaymentGateway {
    @Override public String pay() { return "card"; }
}

@Configuration(proxyBeanMethods = false)
class UserConfig {
    @Bean
    PaymentGateway gateway() {
        return new CardGateway();
    }
}
```

Tại lúc Spring xử lý bean definition cho `gateway`, kiểu trả về khai báo là `PaymentGateway`. Điều kiện `@ConditionalOnBean(PaymentGateway.class)` có cơ sở để khớp, còn `@ConditionalOnBean(CardGateway.class)` **không được bảo đảm** khớp chỉ vì sau này phương thức trả về `new CardGateway()`. Đổi chữ ký thành `CardGateway gateway()` giúp hệ thống nhận diện cả `CardGateway` lẫn interface `PaymentGateway`.

Tệ hơn, nếu khai báo `@Bean Object gateway() { return new CardGateway(); }`, phần lớn tín hiệu kiểu hữu ích biến mất ở giai đoạn dự đoán. Điều kiện kiểm tra `CardGateway` hoặc `PaymentGateway` có thể không khớp, khiến một `@ConditionalOnMissingBean(PaymentGateway.class)` đăng ký bean mặc định dù người dùng đã cung cấp gateway.

Điều này cũng xảy ra với một số định nghĩa tạo bằng factory method, `Supplier<?>`, factory trả về interface quá rộng, raw generic, proxy hoặc kiểu chỉ được biết sau khởi tạo. Không phải mọi proxy đều “vô hình”: điều quan trọng là **kiểu mà container có thể suy luận được tại thời điểm đánh giá**, cùng khả năng gán được (`assignable`) từ kiểu đó sang kiểu được yêu cầu.

| Khai báo / metadata đã có | Kiểm tra `PaymentGateway` | Kiểm tra `CardGateway` |
| --- | --- | --- |
| `@Bean CardGateway gateway()` | Có cơ sở khớp | Có cơ sở khớp |
| `@Bean PaymentGateway gateway()` | Có cơ sở khớp | Không bảo đảm |
| `@Bean Object gateway()` | Không bảo đảm | Không bảo đảm |
| BeanDefinition khai báo class `CardGateway` | Có cơ sở khớp | Có cơ sở khớp |
| Definition không mô tả được kiểu trước khởi tạo | Không bảo đảm | Không bảo đảm |

Bảng mô tả **khả năng nhận diện sớm**, không kết luận tuyệt đối cho mọi pha và mọi cơ chế suy luận của container. Singleton đã được tạo, generic `ResolvableType` hoặc metadata bổ sung có thể làm kết quả tra cứu về sau khác đi; điều kiện đã đánh giá trước đó **không tự chạy lại** chỉ vì kiểu trở nên rõ hơn.

**Cách xử lý:** khai báo `@Bean` với kiểu trả về cụ thể nhất mà các consumer/điều kiện cần. Nếu thiết kế API cố ý chỉ công khai interface, hãy kiểm tra điều kiện theo interface thay vì trông đợi kiểu triển khai. Bảo toàn generic type nếu điều kiện hoặc injection phụ thuộc vào `ResolvableType`; tránh dùng `Object` hoặc raw type chỉ vì thuận tay.

## 3. `FactoryBean<T>`: bean “nhà máy” khác sản phẩm của nhà máy

`FactoryBean<T>` là giao diện Spring dùng để **cung cấp một object** thông qua container; nó khác annotation `@Bean` và cũng khác một service class chỉ được đặt tên “factory”.

Khi đăng ký factory dưới tên `gateway`:

- `context.getBean("gateway")` lấy **sản phẩm** mà `FactoryBean#getObject()` tạo ra.
- `context.getBean("&gateway")` lấy **bản thân đối tượng FactoryBean**.
- Đối với điều kiện theo kiểu sản phẩm, thứ cần biết là kiểu mà factory **công bố**. `getObjectType()` có vai trò thiết yếu; nó có thể được gọi rất sớm, trước khi factory khởi tạo xong.
- `getObjectType()` nên trả về kiểu ổn định, đủ cụ thể, có thể xác định **mà không phải tạo sản phẩm**. Nếu trả về `null` thì Spring có thể phải dựa vào generic hoặc metadata khác; khi vẫn không suy luận được, kiểm tra theo kiểu có thể xem sản phẩm là chưa xác định. `getObjectType()` trả về kiểu rộng (`PaymentGateway.class`) cũng không hứa rằng sản phẩm là `CardGateway`, dù `getObject()` thật sự trả về đối tượng đó.

Ví dụ factory báo kiểu công khai là `PaymentGateway`:

```java
final class GatewayFactory implements FactoryBean<PaymentGateway> {
    @Override
    public PaymentGateway getObject() {
        return new CardGateway();
    }

    @Override
    public Class<?> getObjectType() {
        return PaymentGateway.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }
}

@Configuration(proxyBeanMethods = false)
class FactoryConfig {
    @Bean
    GatewayFactory gateway() {
        return new GatewayFactory();
    }
}
```

`@ConditionalOnBean(PaymentGateway.class)` có thể phát hiện sản phẩm do factory công bố; `@ConditionalOnBean(CardGateway.class)` **không thể mặc nhiên dựa vào** `getObject()` để biết implementation. Đừng “chữa” bằng cách ép khởi tạo sản phẩm sớm chỉ để thỏa một điều kiện; việc ấy có thể làm tăng phụ thuộc vòng, chạm các bean chưa sẵn sàng hoặc gây side effect lúc bootstrap.

### 3.1. Metadata sản phẩm cho đăng ký chương trình

Trong trường hợp một thư viện đăng ký bean definition của `FactoryBean` bằng API thay vì `@Bean`, có thể công bố kiểu sản phẩm qua thuộc tính `FactoryBean.OBJECT_TYPE_ATTRIBUTE` trên `BeanDefinition` khi cần. Ví dụ minh họa **đoạn code nằm trong registrar**, với biến `registry` có sẵn:

```java
RootBeanDefinition definition = new RootBeanDefinition(GatewayFactory.class);
definition.setAttribute(FactoryBean.OBJECT_TYPE_ATTRIBUTE, PaymentGateway.class);
registry.registerBeanDefinition("gateway", definition);
```

Trong Spring Framework 6.1, giá trị attribute này cần là `Class<?>` hoặc `ResolvableType` phù hợp; **không đặt chuỗi tên lớp như `"com.example.PaymentGateway"`** vào attribute. Hãy coi metadata là lời cam kết đúng về sản phẩm; khai báo sai sẽ làm condition và autowiring sai theo. Nếu đã có generic chính xác hoặc `getObjectType()` tốt, thường không cần thêm attribute thủ công.

Không đồng nhất ba câu hỏi: “có definition tên `gateway`?”, “`gateway` là sản phẩm kiểu nào?” và “`&gateway` là factory kiểu nào?”. Một condition theo tên và một condition theo kiểu có thể cho kết quả khác nhau mà không mâu thuẫn.

## 4. Bean đăng ký gián tiếp: nguồn đăng ký và **thời điểm** quan trọng hơn cú pháp

Bean có thể đến từ `@ComponentScan`, `@Import`, `ImportBeanDefinitionRegistrar`, `BeanDefinitionRegistryPostProcessor`, bean definition được thư viện tạo qua API, hoặc `registerSingleton(...)`. Đây đều là cơ chế hợp lệ, nhưng **không tự bảo đảm** rằng một condition sẽ thấy bean.

| Cơ chế | Điều cần kiểm tra |
| --- | --- |
| `@Component` + component scan | Scanner đã chạy trước condition chưa? Definition có công bố đúng class/kiểu không? Đừng phụ thuộc thứ tự scan tình cờ. |
| `@Bean` trong configuration được `@Import` | Configuration đã được xử lý/đăng ký chưa? Chữ ký `@Bean` có cho biết kiểu cần kiểm tra không? |
| `ImportBeanDefinitionRegistrar` | Registrar được kích hoạt vào giai đoạn nào? Definition thêm vào registry mang `beanClass`, factory method hoặc `targetType` nào? |
| `BeanDefinitionRegistryPostProcessor` | Callback đăng ký có chạy **trước** condition cần dùng nó không? Một post-processor chạy muộn có thể thêm bean sau khi condition đã quyết định. |
| `registerSingleton` hoặc đăng ký runtime | Instance được thêm vào khi nào? Nếu sau lần đánh giá, condition không tự tái đánh giá. |

Ví dụ dùng `ImportBeanDefinitionRegistrar` với type rõ ràng:

```java
public final class GatewayRegistrar implements ImportBeanDefinitionRegistrar {
    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata metadata, BeanDefinitionRegistry registry) {
        registry.registerBeanDefinition(
                "gateway", new RootBeanDefinition(CardGateway.class));
    }
}

@Configuration(proxyBeanMethods = false)
@Import(GatewayRegistrar.class)
class UserImportedConfig {
}
```

Các import tương ứng (để đoạn này nằm trong một chương trình Spring):

```java
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.ImportBeanDefinitionRegistrar;
import org.springframework.core.type.AnnotationMetadata;
```

`RootBeanDefinition(CardGateway.class)` mang type có thể dự đoán. **Nếu** registrar được xử lý trước điều kiện, một check `@ConditionalOnBean(CardGateway.class)` có thể nhìn thấy bean; nếu registrar/processor chỉ bổ sung definition sau khi điều kiện chạy thì vẫn không thấy. Đừng chỉ nhìn vào trạng thái cuối cùng “bean có tồn tại” để suy ra nó đã tồn tại lúc condition chạy.

### 4.1. Phân biệt thứ tự đăng ký và thứ tự khởi tạo

Trong Spring Boot, bean do người dùng định nghĩa thường được xử lý trước auto-configuration; vì vậy tài liệu chính thức khuyên dùng `@ConditionalOnBean`/`@ConditionalOnMissingBean` chủ yếu **trên auto-configuration**. Nếu auto-config B phụ thuộc bean do auto-config A cung cấp, khai báo quan hệ đăng ký như:

```java
@AutoConfiguration(after = GatewayAutoConfiguration.class)
class GatewayMetricsAutoConfiguration {

    @Bean
    @ConditionalOnBean(PaymentGateway.class)
    GatewayMetrics gatewayMetrics() {
        return new GatewayMetrics();
    }
}
```

Đây là **đoạn minh họa**, giả sử `GatewayAutoConfiguration` và `GatewayMetrics` đã tồn tại. Có thể dùng `afterName` để tránh liên kết class trực tiếp. Các lựa chọn `@AutoConfigureAfter`/`@AutoConfigureBefore` cũng diễn đạt quan hệ tương tự.

`after` điều chỉnh **thứ tự xử lý definition giữa các auto-configuration**, **không** bắt buộc bean được khởi tạo trước, và không phải thuốc chữa cho metadata kiểu sai. `@DependsOn` điều khiển phụ thuộc lúc khởi tạo, không làm bean definition được biết sớm hơn khi condition chạy. `@Order` thông thường cũng không thay thế quan hệ thứ tự auto-config này. Nếu dùng conditional trên các `@Bean` nằm trong cùng một configuration hoặc các class được scan theo thứ tự không rõ, kết quả có thể phụ thuộc thời điểm phân tích; nên tách phần tạo bean nguồn với auto-config phụ thuộc và nêu rõ quan hệ sau/trước.

## 5. Thực hành kiểm chứng có thể chạy: năm kịch bản

Bài thử dưới đây dùng Spring Boot 3.3.13, JUnit 5 và `ApplicationContextRunner`. Nó không cần khởi động web server hay kết nối database; mỗi test tạo một context riêng. Đây là **ví dụ test hoàn chỉnh**, độc lập với các đoạn code minh họa ở trên.

Tạo dự án Gradle Java 17+ với cấu trúc:

```text
bean-condition-lab/
  settings.gradle
  build.gradle
  src/test/java/demo/BeanConditionVisibilityTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'bean-condition-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}

test {
    useJUnitPlatform()
}
```

`src/test/java/demo/BeanConditionVisibilityTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.FactoryBean;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.ImportBeanDefinitionRegistrar;
import org.springframework.core.type.AnnotationMetadata;

import static org.assertj.core.api.Assertions.assertThat;

class BeanConditionVisibilityTest {

    interface Gateway {
        String id();
    }

    public static final class FastGateway implements Gateway {
        public FastGateway() {}
        @Override public String id() { return "fast"; }
    }

    @AutoConfiguration
    static class ProbeAutoConfiguration {

        @Bean
        @ConditionalOnBean(Gateway.class)
        String interfaceDetected() {
            return "interface visible";
        }

        @Bean
        @ConditionalOnBean(FastGateway.class)
        FastMarker concreteDetected() {
            return new FastMarker();
        }

        @Bean
        @ConditionalOnMissingBean(Gateway.class)
        Gateway fallbackGateway() {
            return () -> "fallback";
        }
    }

    static final class FastMarker {}

    @Configuration(proxyBeanMethods = false)
    static class BroadReturnConfig {
        @Bean
        Gateway gateway() {
            return new FastGateway();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ConcreteReturnConfig {
        @Bean
        FastGateway gateway() {
            return new FastGateway();
        }
    }

    static final class GatewayFactory implements FactoryBean<Gateway> {
        @Override public Gateway getObject() {
            return new FastGateway();
        }
        @Override public Class<?> getObjectType() {
            return Gateway.class;
        }
        @Override public boolean isSingleton() {
            return true;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class FactoryConfig {
        @Bean
        GatewayFactory gateway() {
            return new GatewayFactory();
        }
    }

    public static final class GatewayRegistrar
            implements ImportBeanDefinitionRegistrar {
        @Override
        public void registerBeanDefinitions(
                AnnotationMetadata metadata,
                BeanDefinitionRegistry registry) {
            registry.registerBeanDefinition(
                    "gateway", new RootBeanDefinition(FastGateway.class));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(GatewayRegistrar.class)
    static class ImportedConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(ProbeAutoConfiguration.class));

    @Test
    void noGatewayRegistersFallback() {
        runner.run(ctx -> {
            assertThat(ctx).hasBean("fallbackGateway");
            assertThat(ctx).doesNotHaveBean("interfaceDetected");
            assertThat(ctx).doesNotHaveBean("concreteDetected");
        });
    }

    @Test
    void interfaceReturnHidesConcreteImplementation() {
        runner.withUserConfiguration(BroadReturnConfig.class).run(ctx -> {
            assertThat(ctx).hasBean("interfaceDetected");
            assertThat(ctx).doesNotHaveBean("concreteDetected");
            assertThat(ctx).doesNotHaveBean("fallbackGateway");
        });
    }

    @Test
    void concreteReturnExposesBothTypes() {
        runner.withUserConfiguration(ConcreteReturnConfig.class).run(ctx -> {
            assertThat(ctx).hasBean("interfaceDetected");
            assertThat(ctx).hasBean("concreteDetected");
            assertThat(ctx).doesNotHaveBean("fallbackGateway");
        });
    }

    @Test
    void factoryBeanExposesItsDeclaredProductType() {
        runner.withUserConfiguration(FactoryConfig.class).run(ctx -> {
            assertThat(ctx).hasBean("interfaceDetected");
            assertThat(ctx).doesNotHaveBean("concreteDetected");
            assertThat(ctx).doesNotHaveBean("fallbackGateway");
            assertThat(ctx.getBean("gateway")).isInstanceOf(FastGateway.class);
            assertThat(ctx.getBean("&gateway"))
                    .isInstanceOf(GatewayFactory.class);
        });
    }

    @Test
    void importedRegistrarMakesConcreteTypeVisible() {
        runner.withUserConfiguration(ImportedConfig.class).run(ctx -> {
            assertThat(ctx).hasBean("interfaceDetected");
            assertThat(ctx).hasBean("concreteDetected");
            assertThat(ctx).doesNotHaveBean("fallbackGateway");
        });
    }
}
```

Chạy trong thư mục dự án bằng Gradle đã cài:

```bash
gradle test --tests demo.BeanConditionVisibilityTest
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew test --tests demo.BeanConditionVisibilityTest` trên macOS/Linux hoặc `.\gradlew.bat test --tests demo.BeanConditionVisibilityTest` trên Windows. Cần JDK 17+ và có quyền tải dependency lần đầu. **Kết quả mong đợi** là task `test` thành công với 5 test vượt qua; log thực tế có thể khác nhau theo cấu hình Gradle, vì vậy không giả định một stdout cố định.

Năm test minh họa đồng thời các điểm quan trọng: không có bean thì fallback được đăng ký; kiểu trả về interface không hứa nhận diện implementation; kiểu trả về cụ thể giúp điều kiện nhìn thấy; `FactoryBean` công bố kiểu sản phẩm khác với factory; và một `ImportBeanDefinitionRegistrar` đăng ký type rõ ràng đủ sớm để auto-configuration nhận diện. Nếu đổi `getObjectType()` thành `null` để thử nghiệm, nhớ rằng generic `FactoryBean<Gateway>` vẫn có thể cung cấp metadata suy luận: **không lấy một trường hợp đó làm bằng chứng rằng Spring hoàn toàn không biết type**.

## 6. Chẩn đoán tình huống thực tế theo thứ tự

Khi condition trả kết quả bất ngờ, hãy hỏi theo thứ tự sau:

1. **Đúng điều kiện chưa?** `@ConditionalOnClass` cần class trên classpath; `@ConditionalOnBean` cần ứng viên trong `BeanFactory`. Điều kiện đang so `name`, `type`, `annotation` hay generic container? Có cấu hình `search = SearchStrategy.CURRENT` khiến bean ở parent context bị bỏ qua không?
2. **Lúc đánh giá bean đã đăng ký chưa?** Ai tạo bean definition? Cấu hình người dùng, một auto-config khác, `@Import`, registrar hay post-processor? Xác minh quan hệ `@AutoConfiguration(after = ...)` nếu có phụ thuộc giữa auto-configs. Đừng sửa bằng `@DependsOn` khi lỗi xảy ra trước giai đoạn instantiate.
3. **Container dự đoán được type nào?** Kiểm tra kiểu trả về của `@Bean`, `beanClass`, `ResolvableType`, generic bị xóa, type được factory method công bố, `FactoryBean#getObjectType()` và `FactoryBean.OBJECT_TYPE_ATTRIBUTE`. So sánh type yêu cầu với **type thấy trước khởi tạo**, không chỉ với `instance.getClass()` ở cuối startup.
4. **Đó là sản phẩm hay factory?** Thử phân biệt `"gateway"` và `"&gateway"` trong ngữ cảnh `FactoryBean`. Đừng nhầm `getObjectType()` với `getClass()` của factory.
5. **Ứng viên có được tính không?** Điều kiện có thể lọc ứng viên không phù hợp (chẳng hạn bean không đủ điều kiện autowire), bỏ qua một số type nhờ `ignored`/`ignoredType` của `@ConditionalOnMissingBean`, hoặc bị ảnh hưởng bởi context hierarchy.
6. **Lấy chứng cứ từ condition report.** Với ứng dụng Spring Boot, bật debug bằng tham số `--debug` hoặc cấu hình `debug=true`; xem **Conditions Evaluation Report** trong log. Nếu dùng Actuator và endpoint được bật/expose có chủ đích, `/actuator/conditions` cung cấp positive/negative matches và lý do. Tìm đúng configuration và thông điệp `OnBeanCondition` về “found/did not find” tại thời điểm đánh giá.
7. **Tái hiện bằng test nhỏ.** Dùng `ApplicationContextRunner` với `withUserConfiguration(...)` và `AutoConfigurations.of(...)` để thay đổi lần lượt loại bean definition, kiểu trả về, factory và thứ tự auto-config. Assert cả trường hợp user bean thắng fallback và trường hợp fallback phải xuất hiện.

Để quan sát type **mà không cố ý khởi tạo factory/product**, có thể khảo sát bean factory trong một phép chẩn đoán có kiểm soát:

```java
String[] names = beanFactory.getBeanNamesForType(
        PaymentGateway.class, true, false);
System.out.println(java.util.Arrays.toString(names));
```

Đây là **đoạn minh họa** bên trong một hàm có biến `beanFactory` kiểu `ListableBeanFactory`. Tham số `allowEagerInit=false` giúp hạn chế khởi tạo sớm để suy luận kiểu. Kết quả tại một thời điểm **không tương đương** với danh sách mọi đối tượng mà context có thể tạo ra sau này; hãy ghi lại pha gọi và so với condition report. Không gọi `getBean(...)` hàng loạt trong quá trình debug chỉ để ép các condition “thấy” được type.

## 7. Lỗi phổ biến và cách sửa tương ứng

| Dấu hiệu | Nguyên nhân thường gặp | Cách sửa đúng tầng |
| --- | --- | --- |
| `@ConditionalOnMissingBean(FastGateway.class)` vẫn tạo mặc định dù đã có `@Bean Gateway gateway()` | Kiểu khai báo chỉ là interface | So theo `Gateway` nếu đó là hợp đồng; hoặc trả về `FastGateway` nếu cần điều kiện theo implementation |
| Có `FactoryBean` nhưng `@ConditionalOnBean(Product.class)` không khớp | `getObjectType()` quá rộng/`null`, generic hoặc metadata không đủ | Công bố kiểu sản phẩm đúng, ổn định và khả dụng sớm; khi đăng ký programmatic, dùng metadata phù hợp |
| Nhầm bean factory với sản phẩm | Tra tên `gateway` như thể đó là class `GatewayFactory` | Phân biệt `gateway` (product) và `&gateway` (factory); kiểm tra điều kiện theo kiểu phù hợp |
| Bean có ở context sau startup nhưng condition trước đó “missing” | Definition được đăng ký sau thời điểm condition | Di chuyển bước đăng ký sớm hơn, khai báo quan hệ auto-config, hoặc tái cấu trúc phạm vi điều kiện |
| `@AutoConfiguration(after=...)` đã thêm nhưng không hết lỗi | Kiểu không dự đoán được hoặc nguồn không thật sự là auto-config được sắp thứ tự | Kiểm tra metadata và nguồn đăng ký; `after` chỉ giúp điều kiện thấy definition đã xử lý |
| Tự gọi `getBean()` để làm condition khớp | Dùng khởi tạo sớm như một workaround | Bỏ workaround, sửa type metadata và thứ tự đăng ký; kiểm chứng bằng context runner |

## 8. Checklist thiết kế auto-configuration bền vững

- Chỉ kiểm tra loại bean mà API của thư viện thực sự cần; ưu tiên interface ổn định khi đó là hợp đồng với người dùng, và dùng implementation khi lý do điều kiện đòi hỏi chính implementation.
- Trong `@Bean`, trả về kiểu đủ cụ thể cho injection và điều kiện; tránh chữ ký `Object` hoặc generic thô nếu việc dự đoán kiểu là quan trọng.
- Với `FactoryBean`, hiện thực `getObjectType()` có ý nghĩa từ sớm, không có side effect nặng; giữ nhất quán với sản phẩm `getObject()`.
- Với bean tạo qua API/registrar, cung cấp bean class/`ResolvableType` hoặc factory product type đủ rõ; tránh attribute kiểu sản phẩm sai định dạng.
- Đặt điều kiện presence/missing chủ yếu trong auto-config; sắp xếp các auto-config phụ thuộc bằng `after`/`before` và xác minh test, không dựa vào thứ tự tình cờ của component scan.
- Kiểm thử ít nhất ba trường hợp: không có user bean, user bean có type công bố rõ, user bean có type rộng hoặc được tạo qua factory/registrar.
- Khi thấy điều kiện sai, đọc **lý do match** và kiểm tra **type/timing**, trước khi thay đổi logic nghiệp vụ.

**Điểm cốt lõi:** kết quả của bean condition phản ánh **những definition đã được xử lý và kiểu có thể nhận diện ở thời điểm đánh giá**. `FactoryBean` thêm lớp phân biệt giữa factory và sản phẩm; đăng ký gián tiếp thêm biến số về thứ tự. Viết metadata rõ ràng và kiểm thử theo từng thời điểm sẽ làm fallback và tích hợp auto-configuration dự đoán được.

## Tài liệu chính thức

- Spring Boot 3.3 — Creating Your Own Auto-configuration (bean conditions, return type, thứ tự, `ApplicationContextRunner`): https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — `@ConditionalOnBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html
- Spring Boot 3.3 — `@ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Framework 6.1 — `FactoryBean`: https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/beans/factory/FactoryBean.html
- Spring Framework — Using the `@Bean` Annotation (giới hạn kiểu trả về rộng): https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html

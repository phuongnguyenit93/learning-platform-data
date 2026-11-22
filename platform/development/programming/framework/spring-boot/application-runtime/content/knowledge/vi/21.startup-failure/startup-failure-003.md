# Phân biệt thiếu bean, xung đột bean, phụ thuộc vòng và lỗi khởi tạo trong Spring Boot

## 1. Mục tiêu: phân loại đúng trước khi sửa

Một ứng dụng Spring Boot có thể dừng ngay trong giai đoạn khởi động dù mã Java đã biên dịch thành công. Log thường có các cụm **Error creating bean with name**, **Unsatisfied dependency**, hoặc **APPLICATION FAILED TO START**. Nhưng ba cụm này có thể xuất hiện ở nhiều nguyên nhân hoàn toàn khác nhau. Sửa theo một dòng log bề mặt mà không xác định **loại lỗi gốc** rất dễ dẫn đến đặt thêm annotation, tắt bảo vệ của Spring hoặc tạo ra lỗi mới.

Bài này tập trung vào bốn nhóm chính thuộc **lỗi khởi động**:

1. **Thiếu bean:** Spring cần một dependency nhưng **không có ứng viên phù hợp**.
2. **Xung đột bean:** Có **nhiều ứng viên cùng kiểu** cho một injection point, hoặc **hai định nghĩa dùng cùng tên bean**. Hai trường hợp này cần phân biệt.
3. **Phụ thuộc vòng:** Bean A cần B, B lại cần A, trực tiếp hoặc gián tiếp; container không thể tạo đồ thị theo yêu cầu.
4. **Lỗi khởi tạo:** Spring đã tìm được định nghĩa bean và đang xây dựng nó, nhưng constructor, @Bean factory method, @PostConstruct, init method hoặc cấu hình liên quan **ném lỗi**.

Mỗi loại có thông điệp, exception và cách khắc phục khác nhau. Tài liệu dùng Spring Boot **3.3.x**, Spring Framework **6.1.x**, Java **17+** để thống nhất phiên bản.

## 2. Bean đi qua những giai đoạn nào?

Một bean không chỉ có hai trạng thái “đã tồn tại” và “chưa tồn tại”. Hãy hình dung một quy trình:

~~~text
Doc configuration / component scan / auto-configuration
                       |
            Dang ky BeanDefinition
                       |
          Giai quyet dependency
                       |
       Goi constructor / factory method
                       |
       Dependency injection / binding
                       |
      BeanPostProcessor / @PostConstruct
                       |
             Init method thanh cong
                       |
        Bean san sang cho context
                       |
  Context refresh hoan tat -> Started -> Runners -> Ready
~~~

Thứ tự trên được **đơn giản hóa**; tùy bean, post-processors, proxy, factory, scope và auto-configuration mà các bước cụ thể có khác biệt.

Các lỗi thường tương ứng với những giai đoạn:

| Giai đoạn | Ví dụ vấn đề | Nhóm chẩn đoán |
| --- | --- | --- |
| Đăng ký definition | Hai bean cùng tên, overriding bị cấm | Xung đột định nghĩa bean |
| Resolve dependency | Không có bean loại NotificationGateway | Thiếu bean |
| Resolve dependency | Có hai NotificationGateway đều phù hợp | Mơ hồ do nhiều bean cùng kiểu |
| Resolve dependency / instantiate | A cần B, B cần A | Phụ thuộc vòng |
| Constructor / @Bean method | Ném IllegalArgumentException | Lỗi tạo instance |
| @PostConstruct / init method | Ném IllegalStateException | Lỗi khởi tạo |
| Configuration binding | Sai kiểu dữ liệu/validation | Lỗi cấu hình và khởi tạo |
| Runner sau refresh | ApplicationRunner ném lỗi | Startup failure, không nhất thiết do bean |

**ApplicationStartedEvent** chỉ phát sau khi context refresh thành công. **ApplicationReadyEvent** đến sau runner. Khi một bean cần thiết không tạo được trong refresh, ứng dụng **không đi tới Ready theo đường thành công**; Spring Boot có thể phát **ApplicationFailedEvent**. Tuy nhiên lỗi runner có thể xảy ra **sau khi các bean đã tạo xong**, nên không xếp mọi startup failure vào nhóm lỗi bean.

## 3. Ma trận nhận diện nhanh bằng exception và log

| Tình huống | Dấu hiệu thường gặp | Vấn đề thật sự | Hướng sửa chính |
| --- | --- | --- | --- |
| Không có bean phù hợp | NoSuchBeanDefinitionException; UnsatisfiedDependencyException | 0 candidate | Đăng ký bean, sửa scan/profile/condition/type |
| Nhiều bean cùng kiểu | NoUniqueBeanDefinitionException; expected single matching bean but found 2 | Nhiều candidate không chọn được một | @Qualifier, @Primary, collection hoặc thiết kế tách interface |
| Hai bean cùng tên | BeanDefinitionOverrideException; bean name already defined | Trùng bean name trong registry | Đổi tên, loại duplicate config; không bật override bừa |
| Bean A cần B cần A | BeanCurrentlyInCreationException; requested bean currently in creation; dependency cycle | Cycle trong graph | Thiết kế lại dependency, tách trách nhiệm hoặc thêm mediator |
| Constructor / factory lỗi | BeanCreationException, BeanInstantiationException, root cause cụ thể | Code xây bean ném exception | Sửa constructor/factory, input và resource |
| @PostConstruct/init lỗi | BeanCreationException, invocation of init method failed | Init callback ném exception | Sửa dữ liệu, timeout, validation, cleanup |
| Bind config lỗi | ConfigurationPropertiesBindException, bind/validation cause | Property sai hoặc thiếu | Sửa cấu hình, kiểu dữ liệu và ràng buộc |

**Lưu ý:** BeanCreationException và UnsatisfiedDependencyException thường là **wrapper**. Chúng mô tả việc tạo một bean thất bại, chưa chắc cho biết chính xác nguyên nhân cuối. Cần xem toàn bộ chuỗi **Caused by** và bean/dependency gốc. **NoUniqueBeanDefinitionException** là trường hợp không chọn được một bean trong những bean đã có, không đồng nghĩa “không có bean”.

## 4. Nhóm 1 — Thiếu bean (missing dependency)

### 4.1. Dấu hiệu

Một constructor hoặc @Bean factory yêu cầu:

~~~java
@Service
class AlertService {
    AlertService(NotificationGateway gateway) {
        // ...
    }
}
~~~

Đây là **đoạn minh họa**, cần khai báo NotificationGateway và import @Service. Nếu không có bean nào phù hợp với NotificationGateway, Spring không thể tạo AlertService.

Log thường có dạng diễn giải:

~~~text
Parameter 0 of constructor in ...AlertService
required a bean of type ...NotificationGateway
that could not be found.
~~~

Tùy vị trí injection và phiên bản, chuỗi exception có thể chứa **UnsatisfiedDependencyException** bọc **NoSuchBeanDefinitionException**. Đừng đoán rằng cứ thấy UnsatisfiedDependencyException là phải thêm @Component vào class đang báo lỗi; dependency bị thiếu có thể nằm nhiều tầng sâu hơn.

### 4.2. Tại sao Java có class mà Spring vẫn báo thiếu bean?

**Class tồn tại trong classpath không có nghĩa một bean đã được đăng ký.** Các nguyên nhân thường gặp:

1. Class thiếu @Component/@Service/@Repository, hoặc chưa được khai báo bằng @Bean.
2. Class ở **ngoài phạm vi component scan**. @SpringBootApplication mặc định scan package của class chính và các subpackage; class ở package anh em có thể không được quét.
3. @Profile khác profile đang active. Ví dụ bean chỉ tồn tại với profile prod nhưng local chạy dev.
4. @ConditionalOnProperty, @ConditionalOnClass hoặc điều kiện auto-configuration không thỏa.
5. Thiếu starter/module khiến auto-configuration không tạo bean mong đợi.
6. Cần interface T nhưng @Bean khai báo type khác, qualifier không trùng, hoặc bean được tạo trong ApplicationContext khác.
7. Annotation đặt lên object tạo bằng new thủ công, không phải instance container quản lý.
8. Bean scope/proxy hoặc generic type không khớp injection point.
9. Tên @Qualifier sai, làm **không còn candidate trong tập đã lọc**, dù có bean cùng interface.

### 4.3. Các cách sửa đúng

Khi dependency bắt buộc, đăng ký nó bằng một trong các cơ chế thích hợp:

~~~java
@Service
class SmtpNotificationGateway implements NotificationGateway {
    // ... implement contract ...
}
~~~

Hoặc:

~~~java
@Configuration
class GatewayConfiguration {
    @Bean
    NotificationGateway gateway() {
        return new SmtpNotificationGateway();
    }
}
~~~

Hai đoạn minh họa trên **không phải project độc lập**: cần interface, implementation và import tương ứng. Chọn **một** cơ chế đăng ký phù hợp, tránh vô tình tạo hai bean cho cùng chức năng khi không cần.

Nếu dependency **thực sự tùy chọn**, có thể dùng Optional<NotificationGateway>, ObjectProvider<NotificationGateway> hoặc điều kiện cấu hình để chọn một nhánh rõ ràng. Nhưng **đừng đổi dependency bắt buộc thành Optional chỉ để che startup failure**; service có thể ready nhưng hỏng khi xử lý request thật.

### 4.4. Checklist khi thấy NoSuchBeanDefinitionException

- Kiểm tra **type chính xác**, generic type, qualifier và vị trí injection.
- Kiểm tra class chính @SpringBootApplication đặt ở package gốc đúng.
- Kiểm tra bean có được tạo bởi @Component, @Bean hay auto-configuration.
- Kiểm tra profile đang chạy: spring.profiles.active.
- Kiểm tra điều kiện @ConditionalOnProperty, @ConditionalOnBean, @ConditionalOnMissingBean.
- Kiểm tra module/starter đúng nằm trên runtime classpath.
- Kiểm tra config không bị exclude từ @Import/@ComponentScan hoặc auto-config.
- Nếu cần hai context, xác định bean ở context nào và quan hệ parent-child.

## 5. Nhóm 2 — Xung đột bean có hai dạng khác nhau

### 5.1. Nhiều bean cùng kiểu, injection mơ hồ

Giả sử có:

~~~java
@Bean
NotificationGateway emailGateway() {
    return new EmailGateway();
}

@Bean
NotificationGateway smsGateway() {
    return new SmsGateway();
}
~~~

Đây là mã minh họa, cần class EmailGateway/SmsGateway. Khi một constructor chỉ yêu cầu:

~~~java
AlertService(NotificationGateway gateway) {
    // ...
}
~~~

Spring có **hai candidate cùng kiểu**, nhưng không có tín hiệu lựa chọn. Lỗi thường có **NoUniqueBeanDefinitionException**, hoặc FailureAnalyzer in:

~~~text
required a single bean, but 2 were found:
  - emailGateway
  - smsGateway
~~~

**Đây không phải lỗi trùng tên bean.** Hai bean có tên riêng biệt, tồn tại hợp lệ; vấn đề chỉ là **injection point yêu cầu đúng một instance**.

Các cách sửa:

**@Primary**: khai báo một implementation là mặc định:

~~~java
@Bean
@Primary
NotificationGateway emailGateway() {
    return new EmailGateway();
}
~~~

Khi một injection point yêu cầu một NotificationGateway không có qualifier, Spring thường chọn bean primary duy nhất nếu không có điều kiện ưu tiên khác.

**@Qualifier**: chỉ định bean mong muốn tại nơi sử dụng:

~~~java
AlertService(@Qualifier("smsGateway") NotificationGateway gateway) {
    // ...
}
~~~

**Collection injection**: nếu cố ý cần mọi implementation, dùng List<NotificationGateway> hoặc Map<String, NotificationGateway> thay vì chọn một.

**Interface thiết kế rõ hơn**: nếu email và SMS là hai vai trò nghiệp vụ khác nhau, có thể tách contract hoặc inject một router chọn theo channel, tránh lạm dụng @Primary.

**Không dựa vào tên tham số constructor** làm cách sửa chính: Spring có thể match theo tên bean khi metadata tên tham số được giữ; với Spring Framework 6.1 cần compiler **-parameters** cho cơ chế dựa trên tên tham số. @Qualifier là hợp đồng rõ hơn và bền với việc đổi tên biến.

### 5.2. Hai định nghĩa bean cùng tên (bean name collision)

Một lỗi hoàn toàn khác:

~~~java
@Configuration
class ConfigA {
    @Bean("sharedGateway")
    NotificationGateway first() {
        return new EmailGateway();
    }
}

@Configuration
class ConfigB {
    @Bean("sharedGateway")
    NotificationGateway second() {
        return new SmsGateway();
    }
}
~~~

Đây là đoạn minh họa với các type chưa được định nghĩa. Hai method đặt cùng bean name **sharedGateway** trong registry. Mặc định Spring Boot 3.3 **không cho bean definition overriding**. Do đó khi cố đăng ký definition thứ hai, có thể gặp **BeanDefinitionOverrideException**.

Một thông điệp lỗi thường có ý:

~~~text
The bean 'sharedGateway' could not be registered.
A bean with that name has already been defined
and overriding is disabled.
~~~

Cách sửa đúng: đổi tên bean, loại bỏ duplicate @Configuration, loại một config bằng @Profile/@Conditional, hoặc sửa module import/component scan để mỗi definition có chủ sở hữu rõ.

Có property:

~~~properties
spring.main.allow-bean-definition-overriding=true
~~~

**Không xem property này là cách sửa mặc định.** Khi bật, một bean definition có thể thay thế definition khác tùy thứ tự đăng ký, che mất cấu hình đáng lẽ phải rõ. Đặc biệt nguy hiểm khi nâng cấp module hoặc thay classpath.

Một số xung đột từ component scan có thể biểu hiện bằng **ConflictingBeanDefinitionException** thay vì BeanDefinitionOverrideException, tùy đường đăng ký. Hãy dùng thông điệp gốc để phân biệt.

### 5.3. So sánh cực ngắn

| Đặc tính | NoUniqueBeanDefinitionException | BeanDefinitionOverrideException |
| --- | --- | --- |
| Số tên bean | Hai hoặc nhiều tên riêng biệt | Cùng một tên bị định nghĩa hơn một lần |
| Lỗi xuất hiện khi | Resolve injection yêu cầu một bean | Đăng ký BeanDefinition |
| @Qualifier giúp trực tiếp? | Có, khi chọn đúng candidate | Không sửa trùng tên definition |
| @Primary giúp trực tiếp? | Có, nếu chỉ một primary phù hợp | Không sửa trùng tên definition |
| Đổi tên/loại config trùng | Có thể giảm ambiguity | Cách sửa chính |
| Bật overriding | Không phải giải pháp | Chỉ dùng khi thực sự chủ động thiết kế overriding |

## 6. Nhóm 3 — Phụ thuộc vòng (circular dependency)

Giả sử A phụ thuộc B qua constructor, trong khi B phụ thuộc A:

~~~text
OrderService -> PaymentService
       ^               |
       +---------------+
~~~

Đồ thị không có điểm bắt đầu để tạo một trong hai instance thông thường. Spring có thể ném **BeanCurrentlyInCreationException**, đôi khi được bọc trong **UnsatisfiedDependencyException** hoặc BeanCreationException.

Ví dụ cấu trúc:

~~~java
class OrderService {
    OrderService(PaymentService payment) {
        // ...
    }
}

class PaymentService {
    PaymentService(OrderService order) {
        // ...
    }
}
~~~

Đây là đoạn Java minh họa, chưa có annotation tạo bean. Với constructor injection thuần, cả hai cần instance kia **trước khi constructor của mình chạy xong**.

### Mặc định của Spring Boot 3.3

~~~properties
spring.main.allow-circular-references=false
~~~

Spring Boot 3.3 mặc định **false**. Property true có thể cho Spring cố xử lý **một số** loại cycle dựa trên property/setter injection, nhưng **không giải quyết được cycle constructor injection thuần**. Spring Boot khuyến nghị sửa cấu trúc dependency, thay vì bật true.

### Cách sửa kiến trúc

**Tách logic dùng chung ra bean thứ ba:**

~~~text
Truoc:
OrderService -> PaymentService -> OrderService

Sau:
OrderService -> PaymentService
OrderService -> OrderPolicy
PaymentService -> OrderPolicy
~~~

**Đảo hướng dependency** qua interface hoặc event: một service phát sự kiện nghiệp vụ, service khác lắng nghe tại ranh giới đã thiết kế, tránh cả hai giữ tham chiếu constructor tới nhau.

**Chuyển orchestration** sang một coordinator: thay vì OrderService gọi PaymentService và PaymentService gọi ngược OrderService, tạo CheckoutCoordinator phụ thuộc cả hai, còn hai service độc lập.

**@Lazy** ở một cạnh dependency có thể trì hoãn việc resolve một proxy, đôi khi tháo vòng khởi tạo. Nhưng nó **không xóa cycle logic**, có thể chuyển lỗi sang runtime hoặc gây hành vi khó dự đoán. Hãy xem đây là biện pháp có điều kiện, không phải refactor chính.

**Không nhầm với @DependsOn**: @DependsOn biểu thị quan hệ khởi tạo trước-sau, không biến một đồ thị phụ thuộc vòng thành không vòng. @Order chỉ sắp thứ tự trong những ngữ cảnh khác, không chữa được constructor cycle.

## 7. Nhóm 4 — Lỗi trong quá trình tạo và khởi tạo bean

Spring có thể đã biết definition và tìm được mọi dependency nhưng bản thân bean **ném exception khi tạo**.

Các nguồn lỗi:

1. **Constructor** ném IllegalArgumentException, IllegalStateException, NullPointerException.
2. **@Bean factory method** gọi resource bên ngoài hoặc kiểm tra config rồi ném exception.
3. **@PostConstruct** ném exception trong lúc init.
4. **@Bean(initMethod="...")** ném exception.
5. **InitializingBean.afterPropertiesSet()** ném exception.
6. **@ConfigurationProperties binding** thất bại do kiểu dữ liệu không hợp lệ hoặc validation.
7. **BeanPostProcessor / proxy creation** không thành công.
8. **Resource** như file, key, chứng chỉ, socket hoặc database không truy cập được trong init.

Thông thường gặp **BeanCreationException**, có thể bọc **BeanInstantiationException** hoặc exception nghiệp vụ gốc. Câu “Error creating bean with name 'fragileClient'” chưa đủ để biết phải thêm @Component hay chỉnh @Qualifier: cần xem **Caused by**.

### Ví dụ @PostConstruct

~~~java
@Component
class ConfigurationVerifier {
    @PostConstruct
    void initialize() {
        if (System.getenv("API_TOKEN") == null) {
            throw new IllegalStateException("API_TOKEN is missing");
        }
    }
}
~~~

Đây là **đoạn minh họa**, cần import Component và **jakarta.annotation.PostConstruct** với Spring Boot 3.x. Nếu thiếu environment variable, bean definition đã tồn tại; lỗi không phải NoSuchBeanDefinitionException mà là **exception từ init callback**.

### Lỗi kết nối trong init có nên làm startup fail?

Cần dựa vào hợp đồng nghiệp vụ:

- Nếu không thể phục vụ bất kỳ request hữu ích khi dependency thiếu, **fail fast** hoặc giữ readiness ở refusing theo chính sách rõ.
- Nếu có degraded mode an toàn, có thể không cần kết nối remote trong constructor/@PostConstruct; thay vào đó khởi tạo nhanh, đặt timeout/health riêng.
- Không gọi network operation vô thời hạn trong bean init, vì context refresh có thể bị treo.
- Nếu init method đã mở socket/file rồi ném exception, cần cleanup phần đã tạo dở; không thể tin @PreDestroy luôn chạy cho một bean chưa khởi tạo hoàn chỉnh.

### Nhầm lẫn với lỗi cấu hình

~~~properties
client.connect-timeout=abc
~~~

Nếu bind vào thuộc tính Duration/Integer yêu cầu cú pháp hợp lệ, lỗi **binding/conversion** có thể xuất hiện trước khi service hoạt động. Đây là lỗi configuration, không tự động là thiếu bean. Kiểm tra binding path, property source precedence, active profile và validation message.

## 8. Một project runnable tái hiện cả bốn nhóm lỗi

Ví dụ dùng **Spring Boot 3.3.13 + Java 17+ + Gradle**, kiểu ứng dụng non-web để dễ quan sát startup. Mỗi lỗi nằm trong **một Spring profile độc lập**; chạy một profile mỗi lần để không trộn exception.

Các profile:

- **healthy**: không lỗi; dùng @Primary và @Qualifier đúng.
- **missing**: cần NotificationGateway nhưng không có candidate.
- **ambiguous**: có hai NotificationGateway, không chọn được một.
- **collision**: hai @Bean cùng tên sharedGateway.
- **cycle**: constructor dependency cycle giữa Alpha và Beta.
- **initfail**: method khởi tạo của FragileClient chủ động ném IllegalStateException.

### 8.1. Cấu trúc project

~~~text
startup-failure-lab/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          StartupFailureLab.java
          ScenarioConfigs.java
      resources/
        application.properties
~~~

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'startup-failure-lab'
~~~

Tệp **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Tệp **src/main/resources/application.properties**:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
~~~

Không bật bean overriding hoặc circular references; để Spring Boot giữ hai mặc định an toàn.

### 8.2. Lớp chính và các type chung

Tệp **src/main/java/demo/StartupFailureLab.java**:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class StartupFailureLab {

    public static void main(String[] args) {
        SpringApplication.run(StartupFailureLab.class, args);
    }

    @Bean
    ApplicationListener<ApplicationReadyEvent> readyObserver() {
        return event -> System.out.println("APPLICATION_READY");
    }
}

interface NotificationGateway {
    String channel();
}

record DemoGateway(String channel) implements NotificationGateway { }

record Alpha(Beta beta) { }

record Beta(Alpha alpha) { }

class FragileClient {
    public void initialize() {
        throw new IllegalStateException("Simulated init failure");
    }
}
~~~

**Java syntax:** đây là một file có một public class đúng tên tệp; các interface, record và class còn lại package-private trong cùng package demo. Record được hỗ trợ trên Java 17.

### 8.3. Các cấu hình profile riêng

Tệp **src/main/java/demo/ScenarioConfigs.java**:

~~~java
package demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("healthy")
class HealthyConfig {

    @Bean("emailGateway")
    @Primary
    NotificationGateway emailGateway() {
        return new DemoGateway("email");
    }

    @Bean("smsGateway")
    NotificationGateway smsGateway() {
        return new DemoGateway("sms");
    }

    @Bean
    ApplicationRunner healthyRunner(
            NotificationGateway defaultGateway,
            @Qualifier("smsGateway") NotificationGateway selectedGateway) {
        return args -> {
            System.out.println("HEALTHY_PRIMARY=" + defaultGateway.channel());
            System.out.println("HEALTHY_QUALIFIED=" + selectedGateway.channel());
        };
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("missing")
class MissingConfig {
    @Bean
    ApplicationRunner missingRunner(NotificationGateway gateway) {
        return args -> System.out.println(gateway.channel());
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("ambiguous")
class AmbiguousConfig {

    @Bean
    NotificationGateway emailGateway() {
        return new DemoGateway("email");
    }

    @Bean
    NotificationGateway smsGateway() {
        return new DemoGateway("sms");
    }

    @Bean
    ApplicationRunner ambiguousRunner(NotificationGateway gateway) {
        return args -> System.out.println(gateway.channel());
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("collision")
class CollisionConfigA {
    @Bean("sharedGateway")
    NotificationGateway firstDefinition() {
        return new DemoGateway("first");
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("collision")
class CollisionConfigB {
    @Bean("sharedGateway")
    NotificationGateway secondDefinition() {
        return new DemoGateway("second");
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("cycle")
class CircularConfig {

    @Bean
    Alpha alpha(Beta beta) {
        return new Alpha(beta);
    }

    @Bean
    Beta beta(Alpha alpha) {
        return new Beta(alpha);
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("initfail")
class InitFailureConfig {

    @Bean(initMethod = "initialize")
    FragileClient fragileClient() {
        return new FragileClient();
    }
}
~~~

**Vì sao ví dụ không kích hoạt tất cả lỗi cùng lúc:**

- Mọi class @Configuration của tình huống đều được component scan từ package demo.
- Mỗi tình huống được bảo vệ bởi @Profile; chỉ chạy **một profile trong mỗi lần thử**.
- Các @Bean method của lỗi thiếu/mơ hồ nhận dependency qua tham số; Spring phải resolve chúng trong context refresh.
- Hai cấu hình collision cố ý đăng ký **cùng tên** sharedGateway để tạo lỗi bean-definition overriding.
- Constructor cycle qua các @Bean parameter tạo đồ thị Alpha cần Beta và Beta cần Alpha.
- FragileClient có init method public cố ý ném exception để tái hiện lỗi khởi tạo, dù không có dependency bị thiếu.
- Profile healthy có cả @Primary và @Qualifier để cho thấy hai cách chọn bean khác nhau.

**Vì sao đoạn mã profile healthy đáng tin:** parameter defaultGateway không trùng tên các bean emailGateway hoặc smsGateway, nhưng emailGateway được đánh dấu @Primary; parameter selectedGateway có @Qualifier("smsGateway") nên chọn sms.

## 9. Chạy từng profile và đọc kết quả

Nếu có Gradle wrapper:

~~~bash
./gradlew bootRun --args="--spring.profiles.active=healthy"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=healthy"
~~~

Nếu chưa tạo wrapper nhưng đã có Gradle tương thích:

~~~bash
gradle bootRun --args="--spring.profiles.active=healthy"
~~~

Với **healthy**, các dòng do code tự in theo thứ tự:

~~~text
HEALTHY_PRIMARY=email
HEALTHY_QUALIFIED=sms
APPLICATION_READY
~~~

Log riêng Spring Boot/Gradle có thể xen giữa. Dù non-web app kết thúc tự nhiên sau startup khi không còn non-daemon threads, ApplicationReadyEvent đã xuất hiện trong nhánh thành công.

### 9.1. Thiếu bean

~~~bash
./gradlew bootRun --args="--spring.profiles.active=missing"
~~~

Kỳ vọng: một FailureAnalyzer hoặc stack trace cho thấy **parameter NotificationGateway của missingRunner không có bean phù hợp**. Trong chuỗi nguyên nhân có thể có **NoSuchBeanDefinitionException/UnsatisfiedDependencyException**. Không có dòng APPLICATION_READY từ readyObserver, vì context không hoàn tất startup.

### 9.2. Mơ hồ vì nhiều bean cùng kiểu

~~~bash
./gradlew bootRun --args="--spring.profiles.active=ambiguous"
~~~

Kỳ vọng: **có hai candidate emailGateway và smsGateway** cho tham số NotificationGateway của ambiguousRunner. Vì không có @Primary/@Qualifier phù hợp, xuất hiện **NoUniqueBeanDefinitionException** hoặc thông báo tương đương. APPLICATION_READY không xuất hiện theo đường thành công.

### 9.3. Trùng tên định nghĩa bean

~~~bash
./gradlew bootRun --args="--spring.profiles.active=collision"
~~~

Kỳ vọng: lỗi **BeanDefinitionOverrideException** vì hai @Bean trong CollisionConfigA/CollisionConfigB cùng dùng tên **sharedGateway** và overriding bị tắt theo mặc định. Lỗi xảy ra khi đăng ký definition, không phải vì tham số constructor thiếu candidate.

### 9.4. Phụ thuộc vòng

~~~bash
./gradlew bootRun --args="--spring.profiles.active=cycle"
~~~

Kỳ vọng: thông điệp hoặc graph cho thấy **alpha → beta → alpha** với **BeanCurrentlyInCreationException** hoặc chuỗi BeanCreationException/UnsatisfiedDependencyException. Không bật allow-circular-references để giải quyết vì constructor cycle thuần không có instance hoàn chỉnh để tái sử dụng.

### 9.5. Lỗi init method

~~~bash
./gradlew bootRun --args="--spring.profiles.active=initfail"
~~~

Kỳ vọng: **BeanCreationException** liên quan fragileClient, và root cause **IllegalStateException: Simulated init failure**. Đây là lỗi khởi tạo thật; không phải thiếu bean và không phải hai bean cùng tên.

**Đừng assert toàn bộ nguyên văn stack trace**: số dòng, class proxy, FailureAnalyzer và wording khác theo bản Spring Boot/Framework/Gradle. Khi kiểm thử, xác minh **kiểu nguyên nhân, bean liên quan, tên candidate và việc Ready không phát** thay vì so sánh cả log.

## 10. Sửa từng tình huống trong project

### Thiếu bean: đăng ký implementation đúng profile

Có thể thêm vào MissingConfig một @Bean trả về NotificationGateway:

~~~java
@Bean
NotificationGateway gateway() {
    return new DemoGateway("email");
}
~~~

Đây là method **thay thế/bổ sung bên trong MissingConfig**, không phải class Java riêng. Khi đã có một NotificationGateway, missingRunner có thể resolve dependency.

### Mơ hồ: chọn bằng @Qualifier hoặc @Primary

Thay ambiguousRunner:

~~~java
@Bean
ApplicationRunner ambiguousRunner(
        @Qualifier("emailGateway") NotificationGateway gateway) {
    return args -> System.out.println(gateway.channel());
}
~~~

Method này thay đúng method cũ trong AmbiguousConfig, không đăng ký đồng thời hai method cùng tên. Hoặc thêm @Primary vào **một** implementation, không phải cả hai.

### Trùng tên: đặt tên riêng hoặc loại cấu hình thừa

Đổi secondDefinition thành:

~~~java
@Bean("alternateGateway")
NotificationGateway secondDefinition() {
    return new DemoGateway("second");
}
~~~

Khi hai bean có tên khác, BeanDefinitionOverrideException được loại bỏ. Nếu sau đó một injection point yêu cầu một NotificationGateway không qualifier thì có thể phát sinh lỗi **NoUniqueBeanDefinitionException** mới; phải giải quyết đúng tình huống tiếp theo, không cho rằng đổi tên là xong mọi vấn đề.

### Phụ thuộc vòng: sửa đồ thị

Thay vì Alpha cần Beta và Beta cần Alpha, hãy chuyển trách nhiệm chung sang một thành phần thứ ba, hoặc để coordinator phụ thuộc vào cả hai nhưng hai service không phụ thuộc ngược. Ví dụ mô hình:

~~~text
Truoc: A -> B -> A

Sau:  Coordinator -> A
                  -> B
       A -> SharedPolicy
       B -> SharedPolicy
~~~

Đây là mô hình kiến trúc, không phải source Java.

### Lỗi init: sửa điều kiện khởi tạo

Nếu init cần biến môi trường, kiểm tra property và cung cấp thông điệp chỉ rõ key bị thiếu; nếu cần remote API, dùng timeout/retry hữu hạn và cleanup resource mở dở. Trong demo, method initialize() cố ý luôn ném exception, nên thay nó bằng code khởi tạo hợp lệ là cách sửa thực tế; thêm @Qualifier hoàn toàn không có tác dụng.

## 11. Quy trình debug lỗi startup từng bước

### Bước 1: Xác định lỗi bắt đầu ở giai đoạn nào

- **Definition registration**: BeanDefinitionOverrideException hoặc ConflictingBeanDefinitionException.
- **Dependency resolution**: NoSuchBeanDefinitionException, NoUniqueBeanDefinitionException.
- **Bean construction/init**: BeanCreationException với root cause constructor/@PostConstruct/binding.
- **Lifecycle/runner**: SmartLifecycle.start hoặc ApplicationRunner; không phải lúc nào cũng lỗi bean.
- **Web startup**: port đã được dùng, certificate lỗi, datasource cấu hình sai; xem root cause riêng.

### Bước 2: Tìm bean hoặc injection point cụ thể

Đọc log để xác định:

- Bean name nào đang được tạo?
- Class hoặc factory method nào yêu cầu dependency?
- Required type/generic/qualifier cụ thể là gì?
- Có bao nhiêu candidate và tên chúng?
- Đồ thị cycle gồm những bean nào?
- Init method nào thực sự ném exception?

Một dòng “Error creating bean with name 'orderService'” có thể chỉ là **bean đầu tiên bị ảnh hưởng**. Phần cause tiếp theo mới chỉ ra lỗi ở paymentGateway hay remoteClient.

### Bước 3: Đọc toàn bộ chuỗi Caused by

Ví dụ:

~~~text
UnsatisfiedDependencyException: Error creating orderService
Caused by: BeanCreationException: Error creating pricingClient
Caused by: IllegalArgumentException: Invalid region code
~~~

Không sửa orderService bằng annotation ngẫu nhiên nếu root cause là **region code** không hợp lệ khi tạo pricingClient.

### Bước 4: Dùng FailureAnalyzer và conditions report

Spring Boot có nhiều **FailureAnalyzer** để in **Description** và **Action** cụ thể. Nếu chưa rõ vì sao một auto-configured bean có hoặc không có, thử:

~~~bash
./gradlew bootRun --args="--spring.profiles.active=missing --debug"
~~~

Hoặc với executable JAR:

~~~bash
java -jar build/libs/startup-failure-lab-1.0.0.jar --spring.profiles.active=missing --debug
~~~

Flag **--debug** cho Spring Boot có thể bật conditions evaluation report và log chẩn đoán hữu ích; không đồng nghĩa bật JVM debugger. Dùng log đủ để xem điều kiện nào **matched** hay **did not match**, nhất là @ConditionalOnClass, @ConditionalOnProperty, @ConditionalOnMissingBean. Không gửi toàn bộ secrets trong log lên hệ thống không tin cậy.

### Bước 5: Sửa một nguyên nhân gốc mỗi lần

Ví dụ sửa missing bean bằng cách đăng ký hai implementation có thể chuyển sang lỗi NoUniqueBeanDefinitionException; điều đó không có nghĩa giải pháp trước “sai hoàn toàn”, mà cấu hình vẫn chưa định nghĩa được injection chính xác. Hãy lặp lại chẩn đoán trên **lỗi hiện tại**, không bật hàng loạt flag.

### Bước 6: Xác minh startup và hành vi thật

Không chỉ xem log đã hết stack trace. Xác minh:

- ApplicationReadyEvent có được phát sau khi runners hoàn tất?
- Bean đúng implementation nào được inject?
- Profile/configuration có đúng môi trường?
- Endpoint hoặc job dùng dependency có vận hành thật không?
- Có thay đổi thứ tự beans hoặc định nghĩa nào ngoài dự định không?
- Nếu sửa lỗi bằng @Lazy hay optional injection, liệu lỗi chỉ bị trì hoãn tới request đầu tiên?

## 12. Các trường hợp dễ bị phân loại sai

### 12.1. Không thấy bean do @Profile

~~~java
@Profile("prod")
@Service
class RealGateway implements NotificationGateway {
    // ...
}
~~~

Khi chạy profile dev, type tồn tại trên classpath nhưng **bean không được đăng ký**. Đây vẫn là missing bean, không phải lỗi constructor của RealGateway.

### 12.2. Nhiều bean do tự khai báo trùng auto-configuration

Bạn khai báo custom bean kiểu T, trong khi auto-config cũng cung cấp bean T. Có thể xảy ra:

- Auto-config dùng @ConditionalOnMissingBean và **lùi lại**, không lỗi.
- Auto-config không lùi lại nhưng hai bean có **tên khác**, injection T trở nên mơ hồ.
- Hai bean dùng **cùng tên**, phát sinh lỗi definition overriding.

Vì vậy phải xem type, name, condition và thứ tự đăng ký thực tế; không mặc định “có hai bean” luôn là BeanDefinitionOverrideException.

### 12.3. Sai @Qualifier có thể trông giống thiếu bean

Có EmailGateway và SmsGateway, nhưng injection dùng @Qualifier("pushGateway"). Spring không có candidate phù hợp trong tập đã lọc và có thể báo thiếu bean thỏa qualifier. Đừng thêm một implementation ngẫu nhiên; sửa semantic qualifier.

### 12.4. Constructor có null và @PostConstruct thất bại

Nếu constructor nhận được dependency rồi ném NullPointerException do code bên trong, đó là lỗi **bean instantiation**, không phải thiếu bean. Nếu @PostConstruct gọi remote API rồi timeout, đó là lỗi init/remote dependency, không phải cycle.

### 12.5. Constructor cycle so với runtime call cycle

A phụ thuộc constructor vào B, B phụ thuộc constructor vào A là **bean creation cycle**. Nhưng A.method gọi B.method rồi B.method gọi lại A.method vô hạn là **runtime recursion**, có thể dẫn đến StackOverflowError sau khi context đã ready, dù việc tạo bean không có vòng.

### 12.6. @Lazy có thể giấu lỗi tới runtime

Bật:

~~~properties
spring.main.lazy-initialization=true
~~~

có thể làm nhiều bean chỉ được tạo khi cần. Startup thành công không chứng minh các dependency lazy hợp lệ. Cần test endpoint/job thật và có chính sách fail-fast cho thành phần critical. Không dùng lazy-initialization làm cách tránh sửa wiring.

### 12.7. Khác class loader hoặc nhiều ApplicationContext

Một bean được đăng ký ở child context không tự được tra cứu từ parent theo mọi hướng; class T ở classloader khác có thể không được xem là cùng type dù tên fully-qualified giống. Đây là tình huống nâng cao; không sửa bằng component scan toàn bộ thế giới hoặc cho phép override bừa.

## 13. Phương án sửa nào nên được ưu tiên?

| Lỗi gốc | Ưu tiên 1 | Không nên làm ngay |
| --- | --- | --- |
| Không có bean | Xác minh scan/profile/condition, đăng ký đúng một implementation | Thêm @Autowired(required=false) để che lỗi |
| Nhiều bean cùng kiểu | @Qualifier hoặc @Primary có nghĩa nghiệp vụ rõ | Bật bean overriding |
| Hai bean cùng tên | Đổi tên hoặc bỏ config trùng, thiết kế ownership | allow-bean-definition-overriding=true để bỏ cảnh báo |
| Phụ thuộc vòng | Refactor hướng dependency, mediator/service chung | allow-circular-references=true như giải pháp lâu dài |
| Constructor/init ném exception | Sửa root cause, input, config, timeout và cleanup | Thêm @Primary/@Qualifier hoặc đổi bean name ngẫu nhiên |
| Config binding fail | Sửa key/type/validation và profile | Nuốt BindException |
| Runner fail | Sửa điều kiện startup task và propagate lỗi đúng | Bỏ hết startup validation |

**Khi cần nhiều implementation có chủ đích**, hãy định nghĩa cách chọn minh bạch. **Khi cần plugin architecture**, inject collection hoặc Map theo tên và chọn ở lớp router. **Khi hai service phụ thuộc vòng**, thường phản ánh trách nhiệm chưa tách rõ; chữa graph tốt hơn thay annotation.

## 14. Chiến lược kiểm thử và QA

1. **Missing:** bật profile missing; log chỉ rõ NotificationGateway không có bean. Sau khi bổ sung implementation, chạy thành công.
2. **Ambiguous:** bật profile ambiguous; có đúng hai candidate. Thêm @Qualifier hoặc một @Primary và xác minh implementation đúng.
3. **Collision:** bật profile collision; cùng tên sharedGateway bị chặn. Đổi tên hoặc bỏ definition trùng. Sau đó vẫn kiểm tra khả năng injection theo type.
4. **Cycle:** bật profile cycle; kiểm tra graph alpha/beta và không thử “chữa” constructor cycle bằng allow-circular-references.
5. **Init failure:** bật profile initfail; root cause IllegalStateException với thông điệp Simulated init failure; kiểm tra resource cleanup nếu có side effect.
6. **Healthy:** bật profile healthy; nhận đúng hai dòng PRIMARY/QUALIFIED và APPLICATION_READY.
7. **Runtime/test:** với code production, thêm ApplicationContextRunner hoặc @SpringBootTest để test cấu hình theo profile. Với negative test, dùng AssertJ để kiểm tra context thất bại và root cause chứ không assert nguyên văn toàn bộ log.
8. **Build/package:** chạy cùng Java và profile với deployment; review dependencies trong runtime classpath, không chỉ compile classpath.
9. **Config drift:** kiểm tra application.properties, environment variables, command-line args và Kubernetes config map, kể cả secret injection.
10. **Failure handling:** xác minh ứng dụng không phát Ready sai hoặc mở listener nhận việc khi dependency critical chưa sẵn sàng.

### Ý tưởng kiểm thử lỗi bằng ApplicationContextRunner

Spring Boot test module hỗ trợ **ApplicationContextRunner** tạo context nhỏ từ tập cấu hình/auto-config xác định. Nó phù hợp để kiểm tra điều kiện có hoặc không có bean mà không phải khởi động web server đầy đủ.

Ví dụ minh họa:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(MissingConfig.class)
        .run(context -> {
            // Kiem tra context.getStartupFailure()
            // va root cause/bean type theo ky vong.
        });
~~~

Đây là **đoạn trích minh họa, không phải test runnable độc lập**; cần spring-boot-test, AssertJ, import, cấu hình runner và assertion cụ thể. Test nên xác nhận hành vi có chủ đích chứ không chỉ mong “có exception bất kỳ”.

## 15. Những lỗi khắc phục sai thường gặp

**“Thấy UnsatisfiedDependencyException thì thêm @Component vào mọi class.”** Sai. Có thể dependency thực sự thiếu hoặc bị profile/conditional/qualifier loại; thêm bừa có thể tạo duplicate.

**“Hai bean cùng type là trùng bean name.”** Sai. Trùng type gây mơ hồ khi resolve injection; trùng name gây lỗi definition registration.

**“@Primary chữa BeanDefinitionOverrideException.”** Sai. @Primary chỉ giúp chọn ứng viên khi autowire by type; nó không làm hai definition cùng tên được đăng ký hợp lệ.

**“@Qualifier chữa missing dependency bất kỳ.”** Sai. Nếu không có bean nào thuộc type, qualifier không tự tạo bean.

**“spring.main.allow-bean-definition-overriding=true là cách sửa mọi xung đột.”** Sai. Nó có thể che một definition và làm cấu hình phụ thuộc thứ tự.

**“spring.main.allow-circular-references=true luôn chữa được cycle.”** Sai. Constructor cycle thường không giải quyết được và đây không phải thiết kế khuyến nghị.

**“@DependsOn giúp phá vòng constructor.”** Sai. Nó chỉ thêm dependency/order, không tháo vòng.

**“@Order quyết định cách Spring inject mọi bean.”** Sai. @Order không tương đương @Qualifier hay @Primary.

**“Spring Boot sẽ tự tạo bean cho mọi interface trên classpath.”** Sai. Phải có component/configuration/auto-configuration thỏa điều kiện.

**“Nếu class có @Service ở package bất kỳ thì chắc chắn được scan.”** Sai. Phạm vi scan mặc định dựa trên vị trí class @SpringBootApplication.

**“BeanCreationException luôn là nguyên nhân gốc.”** Sai. Thường là wrapper cho exception cụ thể ở factory/init/binding.

**“Sửa để application start là đủ.”** Chưa đủ nếu lỗi bị che bằng lazy/optional, hoặc bean được inject không đúng implementation.

## 16. Câu hỏi tự kiểm tra

**Câu 1:** Constructor cần PaymentGateway nhưng không có bean nào thuộc type này. Lỗi nhóm nào?  
**Đáp án:** Thiếu bean, thường NoSuchBeanDefinitionException/UnsatisfiedDependencyException.

**Câu 2:** Có hai PaymentGateway tên cardGateway và bankGateway, không @Primary, injection yêu cầu một PaymentGateway. Lỗi?  
**Đáp án:** Nhiều candidate cùng type; NoUniqueBeanDefinitionException.

**Câu 3:** Có hai @Bean cùng tên paymentGateway. Lỗi mặc định của Boot 3.3?  
**Đáp án:** Có thể BeanDefinitionOverrideException vì overriding mặc định false.

**Câu 4:** @Primary có chữa hai @Bean cùng tên không?  
**Đáp án:** Không. Phải sửa name/config ownership.

**Câu 5:** A constructor cần B, B constructor cần A. Lỗi?  
**Đáp án:** Constructor cycle; có thể BeanCurrentlyInCreationException.

**Câu 6:** Bật allow-circular-references=true có đảm bảo phá constructor cycle không?  
**Đáp án:** Không.

**Câu 7:** Bean có @PostConstruct ném IllegalStateException. Đây là missing bean?  
**Đáp án:** Không; bean được tìm thấy nhưng thất bại khi init.

**Câu 8:** @Profile("prod") nhưng chỉ active dev. Class @Service có được đăng ký không?  
**Đáp án:** Không theo profile đó; có thể dẫn tới missing bean.

**Câu 9:** Vì sao nên đọc Caused by thay vì chỉ dòng Error creating bean?  
**Đáp án:** Bean báo lỗi có thể chỉ là nạn nhân; root cause nằm ở dependency sâu hoặc init method.

**Câu 10:** Đổi tên hai bean trùng nhau có luôn loại NoUniqueBeanDefinitionException không?  
**Đáp án:** Không; sau khi có hai tên khác nhau nhưng cùng type, injection có thể lại mơ hồ.

**Câu 11:** @Lazy có chữa dependency wiring sai không?  
**Đáp án:** Không; nó có thể trì hoãn exception tới lần sử dụng đầu tiên.

**Câu 12:** ApplicationReadyEvent có được phát khi một bean cần thiết lỗi trong context refresh không?  
**Đáp án:** Không trên nhánh startup thành công.

**Câu 13:** Thay @Qualifier("emailGateway") thành @Qualifier("pushGateway") khi không có pushGateway sẽ gây gì?  
**Đáp án:** Không còn candidate phù hợp với qualifier, có thể báo thiếu bean phù hợp.

**Câu 14:** Chọn phương án nào khi hai service gọi qua lại vì chứa quá nhiều trách nhiệm?  
**Đáp án:** Refactor, dùng coordinator/mediator, tách dịch vụ hoặc interface và dữ liệu chia sẻ phù hợp.

## 17. Checklist trước khi kết luận đã sửa xong

- Xác định đúng **stage**: definition, dependency resolution, instantiate, initialize, runner hay runtime.
- Xác định đúng **bean name, required type, qualifier, generic và profile**.
- Phân biệt **0 candidate**, **nhiều candidate khác tên**, **trùng tên definition**.
- Nếu có cycle, vẽ đầy đủ đồ thị dependency và tìm cách **tháo một cạnh** bằng refactor.
- Nếu có init failure, tìm exception gốc và loại bỏ nguyên nhân thay vì che lỗi.
- Xác minh default Boot 3.3: **bean overriding=false**, **circular references=false**.
- Với auto-configuration, đọc conditions report và active properties.
- Không để fix tạo bean trùng hoặc thay implementation không được kiểm tra.
- Chạy test dưới runtime/profile tương ứng production.
- Sau khi startup được, xác minh runner/Ready và chức năng thật.
- Với failure và retry, resource đã mở dở được cleanup, không tạo side effects lặp không kiểm soát.

**Kết luận:** “Không tạo được bean” là biểu hiện chung của nhiều nguyên nhân. **Thiếu bean** nghĩa là không có candidate; **xung đột kiểu** là có nhiều candidate không chọn được; **xung đột tên** là hai definition muốn cùng tên; **phụ thuộc vòng** là đồ thị creation tự quay về chính nó; **lỗi khởi tạo** là code factory/constructor/init thất bại. Cách sửa bền vững phải nhắm vào **nguyên nhân gốc, giai đoạn lỗi và hợp đồng dependency**, không chỉ dập dòng cảnh báo startup.

### Tài liệu tham khảo

- [Spring Boot 3.3.13 — SpringApplication API: Allow Bean Definition Overriding và Circular References](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot — SpringApplication: Startup Failure, Events và Conditions Report](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Framework — Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework — @Primary](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [Spring Framework — Circular Dependencies](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework — Lifecycle and Bean Initialization](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)

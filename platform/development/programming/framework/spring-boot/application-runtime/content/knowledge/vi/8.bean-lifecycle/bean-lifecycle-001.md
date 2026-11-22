# Từ định nghĩa bean đến đối tượng đã sẵn sàng sử dụng

Khi nhìn thấy `@Component`, `@Service`, `@Repository` hoặc `@Bean` trong một dự án Spring Boot, ta thường nói “Spring quản lý đối tượng này”. Tuy nhiên, giữa **việc Spring biết có một bean** và **việc một đối tượng đã được tạo, nhận đủ phụ thuộc, hoàn tất khởi tạo rồi có thể được sử dụng** là một chuỗi bước riêng biệt.

Bài học này giải thích hành trình **`BeanDefinition` → tạo instance → giải quyết phụ thuộc → khởi tạo → hậu xử lý → cung cấp bean cho nơi sử dụng** trong Spring Framework 6.1/Spring Boot 3.3 (Java 17+). Nó giúp đọc log khởi động, chẩn đoán `BeanCreationException`, chọn thời điểm thực hiện công việc khởi tạo và tránh nhầm lẫn giữa “bean sẵn sàng” với “toàn ứng dụng đã sẵn sàng nhận lưu lượng”.

## 1. Ba khái niệm cần phân biệt

Hãy hình dung một ứng dụng bán hàng có `OrderService` phụ thuộc vào `OrderRepository`.

- **`BeanDefinition`** là bản mô tả mà container dùng để biết **cách quản lý một bean**. Nó có thể chứa tên, lớp hoặc phương thức tạo, scope, lazy-init, thông tin phụ thuộc, thuộc tính cấu hình và callback vòng đời.
- **Bean instance** là **đối tượng Java thật** được tạo bằng constructor hoặc phương thức factory. Khi constructor vừa trả về, nó chưa chắc đã được Spring thực hiện toàn bộ xử lý sau khi tạo.
- **Bean đã khởi tạo xong** là đối tượng đã đi qua những bước tạo, inject thuộc tính và callback khởi tạo thích hợp, cùng những `BeanPostProcessor` cần áp dụng; đối tượng mà nơi sử dụng nhận được **có thể là proxy** thay vì chính instance gốc.

| Câu hỏi | `BeanDefinition` | Bean instance |
| --- | --- | --- |
| “Đây là loại bean gì, tạo thế nào?” | Mô tả câu trả lời | Là sản phẩm được tạo theo mô tả |
| “Có phải một đối tượng Java đang tồn tại?” | Không | Có |
| “Có thể đọc các thuộc tính cấu hình như scope, lazy?” | Có trong metadata | Có thể suy ra theo cách bean được tạo, nhưng không thay thế metadata |
| “Có thể gọi phương thức nghiệp vụ?” | Không | Có khi đối tượng đã ở trạng thái thích hợp |
| “`@Autowired`/`@PostConstruct` đã diễn ra?” | Chưa thể kết luận chỉ từ định nghĩa | Phụ thuộc giai đoạn tạo và khởi tạo |

Ví dụ một bean có thể được mô tả bởi:

~~~java
@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
~~~

Đoạn trên là **ví dụ về một lớp trong dự án Spring đã có `OrderRepository`**, không phải chương trình độc lập. Khi quét component, Spring có thể đăng ký định nghĩa cho `OrderService`. Để tạo instance, container phải chọn constructor và giải quyết được `OrderRepository` tương ứng. Nếu chưa tạo instance, sự có mặt của định nghĩa **không chứng minh constructor đã chạy**.

Một cách hình dung đơn giản:

~~~text
Mã nguồn / cấu hình
   |
   | @ComponentScan, @Bean, @Import, auto-configuration ...
   v
BeanDefinition (metadata để tạo và quản lý bean)
   |
   | BeanFactory quyết định khi nào cần bean
   v
Tạo instance (constructor hoặc factory method)
   |
   v
Inject phụ thuộc, cung cấp thông tin Aware
   |
   v
Khởi tạo: callback + BeanPostProcessor
   |
   v
Bean sẵn sàng được cung cấp cho các thành phần khác
   |
   v
Người dùng của bean nhận reference (có thể là proxy)
~~~

Sơ đồ là **luồng thông thường**, không phải cam kết mọi bean đều đi qua đúng cùng một tập callback hay cùng một thứ tự nội bộ trong các trường hợp đặc biệt như factory, proxy tạo sớm và circular dependency.

## 2. Bean definition xuất hiện từ đâu?

Trong Spring Boot, những nguồn định nghĩa bean thường gặp gồm:

| Nguồn | Cách khai báo | Ý nghĩa |
| --- | --- | --- |
| Component scanning | `@Component` và các biến thể `@Service`, `@Repository`, `@Controller` | Spring phát hiện lớp trong phạm vi quét thích hợp và đăng ký bean definition |
| Java configuration | `@Configuration` cùng phương thức `@Bean` | Container biết cách gọi phương thức factory để lấy bean |
| Import/configuration | `@Import`, các lớp cấu hình được đưa vào | Đăng ký thêm các bean definition do cấu hình cung cấp |
| Spring Boot auto-configuration | Các cấu hình tự động thỏa điều kiện | Bổ sung bean definition phù hợp với classpath, thuộc tính và bean đã có |
| Đăng ký bằng mã | Các API đăng ký `BeanDefinition`/`BeanDefinitionRegistry` | Cấu hình động khi thực sự cần |

Ví dụ định nghĩa qua `@Bean`:

~~~java
@Configuration
public class ServiceConfiguration {
    @Bean
    OrderService orderService(OrderRepository repository) {
        return new OrderService(repository);
    }
}
~~~

Mã trên là **một phương án thay thế** cho việc gắn `@Service` trực tiếp lên `OrderService`. Khi container cần tạo bean `orderService`, nó giải quyết tham số `OrderRepository` và gọi phương thức `orderService(...)` để lấy instance.

**Không nhầm việc xử lý bean definition với việc chạy constructor.** Quá trình quét, phân tích cấu hình và đăng ký metadata diễn ra trước khi container quyết định tạo những singleton thông thường. `BeanDefinitionRegistryPostProcessor` và `BeanFactoryPostProcessor` có thể can thiệp vào metadata ở giai đoạn xây dựng container. Chúng không giống `BeanPostProcessor`, vốn xử lý **instance của bean**.

Một định nghĩa có thể tồn tại nhưng instance **chưa được tạo**, chẳng hạn bean singleton `@Lazy` chưa được yêu cầu hoặc bean scope `prototype` chưa được lấy lần nào.

## 3. Bean được tạo lúc nào?

### Singleton mặc định

Mặc định, bean được Spring quản lý có scope **`singleton`**. Trong một `ApplicationContext` thông thường, những singleton **không lazy** sẽ được tạo và khởi tạo trong quá trình `refresh()` (giai đoạn hoàn thiện `BeanFactory`), trước khi ứng dụng đi qua các bước sẵn sàng cuối cùng của Spring Boot.

“Singleton” ở đây là **một bean instance chung cho mỗi định nghĩa trong container**, không có nghĩa toàn JVM chỉ được phép tồn tại một đối tượng Java thuộc lớp đó. Hai `ApplicationContext` hoặc hai định nghĩa khác nhau có thể tạo những instance riêng.

~~~java
@Service
class PricingService {
}
~~~

Nếu không có tùy chỉnh scope/lazy và lớp nằm trong phạm vi quét, bean này thường được tạo sớm trong quá trình refresh.

### Lazy singleton

~~~java
@Bean
@Lazy
HeavyClient heavyClient() {
    return new HeavyClient();
}
~~~

Định nghĩa có thể được đăng ký khi xây dựng context, nhưng instance `HeavyClient` chỉ được tạo khi bean được yêu cầu. Tuy nhiên, nếu một singleton **không lazy** cần inject trực tiếp `HeavyClient` trong lúc khởi động, Spring vẫn có thể tạo `HeavyClient` sớm để đáp ứng phụ thuộc. `@Lazy` trên định nghĩa không luôn đồng nghĩa “chắc chắn không khởi tạo trong startup”.

### Prototype và các scope khác

~~~java
@Bean
@Scope("prototype")
DraftDocument draftDocument() {
    return new DraftDocument();
}
~~~

Với `prototype`, mỗi lần container xử lý yêu cầu lấy bean sẽ có một instance mới theo ngữ nghĩa scope. Vì vậy, không thể coi mọi bean đã được tạo xong ở cuối `refresh()`. Scope request/session chỉ có ý nghĩa trong ngữ cảnh tương ứng, và các bean đó được khởi tạo khi scope có hiệu lực và cần chúng.

**Một lưu ý khi inject prototype vào singleton:** việc inject trực tiếp thường được giải quyết khi singleton được tạo; các lần gọi phương thức sau đó trên singleton **không tự tạo prototype mới**. Nếu cần tạo mới theo từng tác vụ, xem xét `ObjectProvider<T>`, `Provider<T>` hoặc giải pháp lookup phù hợp.

## 4. Chuỗi khởi tạo một bean thông thường

Với một singleton bình thường không lazy, đường đi có thể đọc như sau:

~~~text
BeanDefinition đã có
      |
      v
[1] Container quyết định cần bean
      |
      v
[2] Chọn constructor / factory method
    Giải quyết các phụ thuộc cần thiết
      |
      v
[3] Tạo instance Java
      |
      v
[4] Điền thuộc tính / inject field, setter, @Value ... nếu có
      |
      v
[5] Các callback Aware phù hợp
      |
      v
[6] BeanPostProcessor trước init
    Bao gồm cơ chế xử lý @PostConstruct
      |
      v
[7] InitializingBean.afterPropertiesSet() nếu có
      |
      v
[8] Phương thức initMethod cấu hình nếu có
      |
      v
[9] BeanPostProcessor sau init
    Có thể trả về proxy/wrapper
      |
      v
Instance/reference được container quản lý và cung cấp
~~~

Đây là **bản đồ học tập**, cần đọc cùng các ngoại lệ sau:

- Không phải bean nào cũng có field injection, `Aware`, `@PostConstruct`, `InitializingBean` hoặc `initMethod`.
- `BeanPostProcessor` là **một chuỗi nhiều processor**. `@PostConstruct` được thực hiện bởi cơ chế post-processor trước initialization. Vì vậy, không thể khẳng định **mọi** `postProcessBeforeInitialization` tùy biến đều chạy **trước** `@PostConstruct`. Thứ tự các processor còn phụ thuộc cơ chế sắp xếp của Spring.
- Những cơ chế như `InstantiationAwareBeanPostProcessor`, `SmartInstantiationAwareBeanPostProcessor` hoặc factory/proxy đặc biệt có thể tác động ở giai đoạn sớm hơn. Sơ đồ không mô tả mọi nhánh kỹ thuật này.
- Constructor injection được giải quyết **trước khi constructor của bean đích chạy**. Field/setter injection xảy ra **sau khi đã có instance**, trước các callback khởi tạo.
- Container có thể quản lý bean được tạo từ một phương thức `@Bean`, một `FactoryBean` hoặc factory khác, nên không nên luôn tìm constructor của “lớp bean” bằng cách lần ngược một câu lệnh `new` trực tiếp.

Chính sự phân biệt **định nghĩa → tạo → inject → initialize → post-process** giúp định vị lỗi chính xác thay vì gom mọi lỗi startup thành “Spring không tạo được bean”.

## 5. Từ phụ thuộc đến đối tượng: constructor injection

Xét hai thành phần:

~~~java
public final class MailClient {
    public String send() {
        return "sent";
    }
}

public final class RegistrationService {
    private final MailClient mailClient;

    public RegistrationService(MailClient mailClient) {
        this.mailClient = mailClient;
    }

    public String register() {
        return mailClient.send();
    }
}
~~~

Đây là **hai lớp Java có thể biên dịch**, nhưng để thành bean Spring cần khai báo thêm bằng `@Component` hoặc `@Bean`. Trong trường hợp container quản lý cả hai:

1. Spring cần một `RegistrationService`.
2. Nó tìm constructor của `RegistrationService` và thấy cần `MailClient`.
3. Nó phân giải bean `MailClient`; nếu cần, bean phụ thuộc cũng trải qua chu kỳ tạo và khởi tạo.
4. Nó gọi `new RegistrationService(mailClient)` hoặc cơ chế tạo tương ứng.
5. Nó tiếp tục xử lý vòng đời của instance `RegistrationService`.

Từ đó suy ra: trong **constructor injection**, đối tượng phụ thuộc đã được cung cấp khi constructor của bean đích thực thi. Với **field injection** hay **setter injection**, khi constructor của bean đích bắt đầu chạy thì các trường được Spring inject sau đó có thể vẫn chưa có giá trị.

### Vì sao không nên sử dụng field được inject trong constructor?

~~~java
@Component
class IncorrectService {
    @Autowired
    private MailClient mailClient;

    IncorrectService() {
        // mailClient có thể đang null ở thời điểm constructor.
        // KHÔNG gọi mailClient.send() ở đây.
    }
}
~~~

Đoạn trên là **mã minh họa cấu trúc**, chưa bao gồm phần định nghĩa bean `MailClient`. Nếu constructor truy cập `mailClient.send()` trong cách inject field này, có nguy cơ `NullPointerException` vì việc điền field diễn ra sau khởi tạo object.

Constructor injection giúp thể hiện các phụ thuộc bắt buộc rõ ràng hơn:

~~~java
@Component
class BetterService {
    private final MailClient mailClient;

    BetterService(MailClient mailClient) {
        this.mailClient = mailClient;
        // Phụ thuộc bắt buộc đã được cung cấp.
    }
}
~~~

Với một constructor duy nhất trong Spring Framework hiện đại, không cần thêm `@Autowired` lên constructor để nó được chọn tự động trong trường hợp thông thường.

## 6. Các callback `Aware`: bean nhận thông tin từ container

Một bean đôi khi cần biết tên đăng ký hoặc tương tác với container. Spring có những giao diện callback như:

| Giao diện | Tác dụng |
| --- | --- |
| `BeanNameAware` | Nhận tên mà container dùng để đăng ký bean |
| `BeanFactoryAware` | Nhận `BeanFactory` đang quản lý bean |
| `ApplicationContextAware` | Nhận `ApplicationContext` tương ứng |

Ví dụ:

~~~java
public final class NamedService implements BeanNameAware {
    private String beanName;

    @Override
    public void setBeanName(String name) {
        this.beanName = name;
    }
}
~~~

Đoạn này cần import `org.springframework.beans.factory.BeanNameAware` trong dự án Spring; nó không phải chương trình JDK độc lập. `setBeanName(...)` được gọi trong quá trình initialize bean, trước khi bean được cung cấp như đối tượng đã hoàn tất.

**Đừng mặc định mọi callback Aware đều do cùng một bước nội bộ thực hiện.** Một số giao diện Aware được `AbstractAutowireCapableBeanFactory` xử lý trực tiếp, một số khác được xử lý qua `BeanPostProcessor` của context. Đối với mã nghiệp vụ, nên ưu tiên inject phụ thuộc cụ thể và chỉ dùng Aware khi thật sự cần tương tác với container.

## 7. Ba cách khởi tạo thường gặp: `@PostConstruct`, `InitializingBean`, `initMethod`

Spring hỗ trợ các callback khởi tạo sau khi phụ thuộc cần thiết đã được thiết lập:

### `@PostConstruct`

~~~java
@PostConstruct
public void prepare() {
    // Kiểm tra cấu hình hoặc chuẩn bị trạng thái cục bộ của bean.
}
~~~

Đối với Spring Boot 3.x, import `jakarta.annotation.PostConstruct`. Callback này thường phù hợp để xác thực cấu hình và chuẩn bị dữ liệu của chính bean.

### `InitializingBean.afterPropertiesSet()`

~~~java
public class CacheConfig implements InitializingBean {
    @Override
    public void afterPropertiesSet() {
        // Chạy sau khi Spring đặt các thuộc tính cần thiết.
    }
}
~~~

Đây là API trực tiếp của Spring, có import `org.springframework.beans.factory.InitializingBean`. Nó làm lớp phụ thuộc vào Spring, vì vậy nhiều ứng dụng ưu tiên `@PostConstruct` hoặc phương thức init thông thường.

### `@Bean(initMethod = "...")`

~~~java
@Bean(initMethod = "initialize")
ReportFormatter reportFormatter() {
    return new ReportFormatter();
}
~~~

Spring gọi `initialize()` trên object do phương thức factory trả về theo cấu hình khởi tạo. Đây là cách phù hợp khi lớp là mã của bên thứ ba và không thể sửa để gắn annotation.

**Khi ba cơ chế khởi tạo được khai báo trên cùng một bean, với ba phương thức khác nhau**, thứ tự theo hợp đồng Spring là:

1. `@PostConstruct`.
2. `InitializingBean.afterPropertiesSet()`.
3. Phương thức init được khai báo, ví dụ `@Bean(initMethod = "initialize")`.

Nếu một phương thức được cấu hình trùng nhau qua nhiều cơ chế, Spring tránh gọi cùng một phương thức hai lần theo quy tắc vòng đời. Không nên thiết kế phụ thuộc vào việc gọi lặp một callback.

Phần lớn bean **không cần cả ba**. Chúng được trình bày cùng nhau để học thứ tự; trong mã nghiệp vụ thực tế, một cơ chế rõ ràng thường dễ bảo trì hơn.

## 8. Ví dụ thực hành chạy được với Spring Boot 3.3

Ví dụ xây dựng một ứng dụng console nhỏ, không cần web server. Nó minh họa đúng **constructor → BeanNameAware → @PostConstruct → afterPropertiesSet → initMethod → ApplicationRunner → lấy bean từ context → close**.

### Cấu trúc thư mục

~~~text
bean-journey-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/beanjourney/BeanJourneyApplication.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'bean-journey-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
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
    // Gradle native BOM: cung cấp version cho các module Spring Boot.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'jakarta.annotation:jakarta.annotation-api'
}
~~~

**Vì sao cần BOM?** Khi dùng plugin Spring Boot cùng Gradle native dependency management, việc áp dụng `org.springframework.boot` **không tự cấp phiên bản cho mọi dependency khai báo không có version**. BOM ở trên cung cấp những phiên bản tương thích cho starter và Jakarta annotations. Dự án cũng có thể dùng plugin `io.spring.dependency-management` theo tài liệu Spring Boot; chỉ cần chọn một cơ chế quản lý phiên bản nhất quán.

Tệp `src/main/java/com/example/beanjourney/BeanJourneyApplication.java`:

~~~java
package com.example.beanjourney;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.BeanNameAware;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BeanJourneyApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BeanJourneyApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            GreetingService service =
                    context.getBean(GreetingService.class);
            System.out.println("MAIN ready=" + service.isReady());
        }
        System.out.println("MAIN closed");
    }

    @Bean
    GreetingRepository greetingRepository() {
        return new GreetingRepository();
    }

    @Bean(initMethod = "customInit", destroyMethod = "customDestroy")
    GreetingService greetingService(GreetingRepository repository) {
        return new GreetingService(repository);
    }

    @Bean
    ApplicationRunner verifyService(GreetingService service) {
        return args -> System.out.println(
                "RUNNER message=" + service.greet("Spring"));
    }

    static final class GreetingRepository {
        String prefix() {
            return "Xin chào";
        }
    }

    static final class GreetingService
            implements BeanNameAware, InitializingBean {

        private final GreetingRepository repository;
        private boolean ready;

        GreetingService(GreetingRepository repository) {
            this.repository = repository;
            System.out.println(
                    "BEAN constructor repository=" + (repository != null));
        }

        @Override
        public void setBeanName(String beanName) {
            System.out.println("BEAN name=" + beanName);
        }

        @PostConstruct
        public void postConstruct() {
            System.out.println("BEAN @PostConstruct");
        }

        @Override
        public void afterPropertiesSet() {
            System.out.println("BEAN afterPropertiesSet");
        }

        public void customInit() {
            ready = true;
            System.out.println("BEAN customInit");
        }

        public boolean isReady() {
            return ready;
        }

        public String greet(String name) {
            return repository.prefix() + " " + name;
        }

        @PreDestroy
        public void preDestroy() {
            System.out.println("BEAN @PreDestroy");
        }

        public void customDestroy() {
            System.out.println("BEAN customDestroy");
        }
    }
}
~~~

Mã ở trên là **một tệp Java hoàn chỉnh trong dự án Gradle có dependency Spring Boot**, không phải ví dụ chỉ dùng JDK. `GreetingService` được tạo qua phương thức `@Bean` nên tên bean theo mặc định là `greetingService`. `GreetingRepository` được Spring giải quyết và truyền vào phương thức factory trước khi constructor `GreetingService` chạy. Cờ `ready` chỉ được bật ở callback init cuối của ví dụ để dễ quan sát.

### Chạy và quan sát

Nếu dự án có Gradle Wrapper tương thích:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu chưa tạo wrapper nhưng đã cài Gradle tương thích với Spring Boot 3.3, chạy:

~~~bash
gradle bootRun
~~~

Các dòng **do `System.out.println` trong mã trên tạo ra**, theo thứ tự trên đường khởi động/đóng thành công, là:

~~~text
BEAN constructor repository=true
BEAN name=greetingService
BEAN @PostConstruct
BEAN afterPropertiesSet
BEAN customInit
RUNNER message=Xin chào Spring
MAIN ready=true
BEAN @PreDestroy
BEAN customDestroy
MAIN closed
~~~

Có thể còn các thông báo khác từ Gradle hoặc hệ thống logging; danh sách trên chỉ mô tả những dòng do chính ví dụ in.

Đọc từng mốc:

1. **Constructor** được gọi với `GreetingRepository` đã phân giải, vì đây là constructor nhận repository.
2. **`BeanNameAware`** nhận tên `greetingService` trong giai đoạn hoàn thiện bean.
3. **`@PostConstruct`** chạy trước `afterPropertiesSet`.
4. **`afterPropertiesSet`** chạy trước `customInit` của `@Bean`.
5. **`ApplicationRunner`** nhận bean đã được khởi tạo; nó gọi `greet(...)` sau khi context refresh.
6. **`SpringApplication.run` trả về**; mã `main` lấy bean từ context và thấy `ready=true`.
7. **`close()`** bắt đầu hủy bean; `@PreDestroy` và `customDestroy` của bean được gọi trước khi dòng `MAIN closed` được in.

Ví dụ cố ý tắt banner, log startup và web server để giảm nhiễu; nó **không thay đổi** logic tạo bean. Không có `BeanPostProcessor` tự viết trong ví dụ, để thứ tự callback được dự đoán dễ dàng.

### Bài thử lỗi khởi tạo

Trong `customInit()`, thử thay thân phương thức bằng:

~~~java
public void customInit() {
    throw new IllegalStateException("invalid configuration");
}
~~~

Đây là **biến thể thử nghiệm**, không phải mã mặc định của ví dụ. Khi khởi động lại, Spring không thể hoàn tất khởi tạo `greetingService`. Lời gọi `application.run(args)` thất bại; mã sau lời gọi không chạy như đường thành công. Thông báo lỗi thường có chuỗi nguyên nhân chứa `BeanCreationException` hoặc một ngoại lệ tạo bean liên quan, với nguyên nhân gốc `IllegalStateException: invalid configuration`.

Sau khi quan sát, khôi phục `customInit()` ban đầu. Không dùng lỗi cố ý này trong cấu hình vận hành.

## 9. `BeanPostProcessor` và vì sao đối tượng được inject có thể là proxy

`BeanPostProcessor` là điểm mở rộng xử lý **instance** của bean quanh giai đoạn initialization:

~~~java
public interface BeanPostProcessor {
    Object postProcessBeforeInitialization(
            Object bean, String beanName);

    Object postProcessAfterInitialization(
            Object bean, String beanName);
}
~~~

Đây là **chữ ký minh họa của hai phương thức trong Spring API**, không phải toàn bộ mã nguồn của giao diện ở một phiên bản cụ thể.

Một bộ xử lý có thể kiểm tra metadata, áp dụng xử lý annotation hoặc trả về **đối tượng bọc**. Cơ chế AOP thường dùng proxy để bổ sung behavior như giao dịch, bảo mật hoặc đo lường khi phương thức được gọi qua reference được Spring quản lý.

~~~text
Bean gốc được tạo
    |
    +-- Inject + callback init
    |
    +-- BeanPostProcessor sau init
             |
             +-- Trả về chính bean gốc
             |
             +-- Hoặc trả về proxy bao quanh bean gốc
                         |
                         v
            Nơi dùng bean nhận reference phù hợp
~~~

Ví dụ:

~~~java
@Service
class PaymentService {
    @Transactional
    public void pay() {
        // Công việc thanh toán thực tế.
    }
}
~~~

Đây là đoạn **minh họa trong dự án đã bật transaction management phù hợp**; muốn biên dịch cần import `@Service`, `@Transactional` và có các dependency Spring cần thiết. Nó không tự đảm bảo transaction hoạt động nếu chưa có cấu hình quản lý giao dịch.

Hai kết luận quan trọng:

- Một bean đã chạy `@PostConstruct` **chưa chắc đã được bọc bằng proxy sau init**. Đừng mặc định lời gọi phương thức `@Transactional` trong chính `@PostConstruct` sẽ đi qua cơ chế giao dịch mong muốn.
- **Self-invocation** (một phương thức của bean gọi trực tiếp phương thức khác trên `this`) thường không đi qua Spring AOP proxy, kể cả sau khi bean đã sẵn sàng. Đừng suy luận “bean đã được tạo” là mọi annotation liên quan đến proxy tự hoạt động cho mọi kiểu gọi.

Để nhận biết bean được inject có thể không cùng lớp runtime với target, có thể quan sát `getClass()` hoặc API như `AopUtils.isAopProxy(...)` trong môi trường có Spring AOP. Tuy nhiên, logic nghiệp vụ nên phụ thuộc vào giao diện/hợp đồng và tránh giả định lớp runtime chính xác của proxy.

**Đừng viết `BeanPostProcessor` chỉ để log mọi bean ở môi trường production** nếu không thật sự cần: post-processor chạy trên rất nhiều bean, bản thân nó được tạo và đăng ký sớm, việc truy cập bean khác không đúng lúc có thể gây tạo bean quá sớm hoặc thay đổi thứ tự khởi tạo.

## 10. “Bean đã sẵn sàng” là sẵn sàng ở cấp nào?

Cụm “đã sẵn sàng sử dụng” thường có **ba lớp nghĩa**, nên tách rõ:

| Mốc | Đã có gì? | Chưa nhất thiết có gì? |
| --- | --- | --- |
| Bean vừa khởi tạo xong | Đối tượng đã đi qua các callback và BPP cần thiết, Spring có reference để cung cấp | Các singleton khác hoặc công việc toàn hệ thống có thể chưa hoàn tất |
| `ApplicationContext` hoàn tất refresh | Các singleton non-lazy thông thường đã được tạo, container làm mới thành công và phát sự kiện liên quan | `ApplicationRunner`/`CommandLineRunner` có thể chưa chạy |
| Spring Boot phát `ApplicationReadyEvent` | Các runner đồng bộ đã hoàn tất; vòng đời startup của Spring Boot đạt mốc ready | Dịch vụ bên ngoài, cơ sở dữ liệu hoặc công việc nền chưa chắc đều khỏe nếu không kiểm tra riêng |

Với các singleton cần phối hợp sau khi toàn bộ singleton non-lazy thông thường được tạo, Spring có điểm mở rộng **`SmartInitializingSingleton.afterSingletonsInstantiated()`**. Nó được gọi ở cuối giai đoạn khởi tạo trước các singleton thông thường, sau các callback init của từng bean. Tuy nhiên, bean lazy được tạo về sau **không nhận callback này qua đường khởi động ban đầu**.

Trong context đầy đủ, một listener của `ContextRefreshedEvent` là một lựa chọn khác để phản ứng sau khi refresh. Nếu cần **bắt đầu/dừng** consumer hoặc thành phần chạy nền theo thứ tự, cơ chế `SmartLifecycle` và `LifecycleProcessor` thích hợp hơn việc khởi động công việc bất đồng bộ lâu dài ngay trong `@PostConstruct`.

Lý do: `@PostConstruct` thuộc **giai đoạn tạo riêng một bean**, thường nằm trong việc khởi tạo singleton có khóa quản lý. Làm I/O chặn lâu, chờ một bean khác chưa sẵn sàng hoặc tự khởi động việc nền phức tạp tại đây có thể khiến startup chậm, deadlock hoặc khó quản lý shutdown.

### Ví dụ tình huống

`EmailSender` đã tạo xong lúc 08:00:00 và phương thức `send` có thể được gọi. Nhưng `ApplicationRunner` đang tải cấu hình hoạt động dài 10 giây, nên `ApplicationReadyEvent` chưa phát. Nếu hệ thống yêu cầu đồng bộ dữ liệu trước khi nhận HTTP traffic, “`EmailSender` đã được khởi tạo” **không chứng minh** “ứng dụng đã đủ điều kiện nhận request”.

Tương tự, một bean `@Lazy` có thể được tạo **sau** khi `ApplicationReadyEvent` phát, khi request đầu tiên yêu cầu bean. Tính “ready của ứng dụng” không có nghĩa tất cả lazy/prototype bean đã từng được khởi tạo.

## 11. Quan hệ với scope, proxy và việc hủy bean

Vòng đời bean không kết thúc ngay sau initialization. Khi container đóng, Spring còn xử lý dừng hoạt động và callback dọn dẹp với những bean thuộc phạm vi mà nó quản lý.

~~~text
Đăng ký định nghĩa
    |
    v
Tạo / inject / initialize
    |
    v
Bean được sử dụng trong thời gian context tồn tại
    |
    +-- Có thể tham gia start/stop nhờ Lifecycle/SmartLifecycle
    |
    v
Context đóng bình thường
    |
    +-- Dừng Lifecycle bean đang chạy (nếu có)
    |
    +-- Gọi callback destroy với singleton do container quản lý
    |
    v
Giải phóng tài nguyên
~~~

Với singleton, Spring thường gọi `@PreDestroy`, `DisposableBean.destroy()` hoặc destroy method đã khai báo theo cơ chế tương ứng. Với **prototype**, container hỗ trợ tạo/inject/khởi tạo nhưng thông thường **không tự theo dõi để gọi callback hủy** cho từng instance prototype. Bên sử dụng phải chịu trách nhiệm giải phóng tài nguyên cần thiết.

Với bean thuộc request/session scope, vòng đời và thời điểm hủy còn phụ thuộc scope đang hoạt động. Vì thế, không nên mô tả mọi bean bằng công thức “được tạo khi khởi động, được hủy khi JVM thoát”.

Thứ tự callback thường gặp khi một bean có nhiều callback hủy khác nhau là:

1. `@PreDestroy`.
2. `DisposableBean.destroy()` nếu được triển khai.
3. Phương thức destroy cấu hình cho bean.

Ví dụ `BeanJourneyApplication` bên trên chỉ dùng `@PreDestroy` và `customDestroy`, nên nhận hai dòng tương ứng.

**Phân biệt với `LifecycleProcessor`:** `Lifecycle`/`SmartLifecycle` quản lý **start/stop** của một thành phần đang hoạt động; callback destroy quản lý **hủy bean**. Khi `ApplicationContext.close()` chạy theo đường bình thường, stop có thể diễn ra trước giai đoạn destroy. Không nên thay thế `SmartLifecycle.stop(Runnable)` bằng một `@PreDestroy` dài vô hạn nếu cần điều phối thứ tự ngừng nhận việc.

## 12. Khoanh vùng lỗi theo giai đoạn

| Triệu chứng | Giai đoạn cần kiểm tra | Ví dụ nguyên nhân |
| --- | --- | --- |
| Không có bean để inject | Đăng ký definition / phân giải phụ thuộc | Ngoài phạm vi component scan, điều kiện auto-config không đạt, không có `@Bean` phù hợp |
| Có nhiều bean cùng kiểu và không chọn được | Phân giải dependency | Thiếu `@Qualifier`/`@Primary` hoặc cấu hình lựa chọn |
| Không tạo được instance | Chọn constructor / factory method | Constructor ném exception, thiếu tham số, phụ thuộc không tồn tại |
| `@Autowired` field là `null` trong constructor | Tạo instance trước field injection | Đọc field quá sớm; chuyển sang constructor injection |
| `@Value`/`@ConfigurationProperties` sai | Liên kết thuộc tính / giải quyết cấu hình | Sai tên thuộc tính, profile, biến môi trường, kiểu dữ liệu |
| Exception trong `@PostConstruct` | Giai đoạn initialize | Cấu hình thiếu, gọi I/O hoặc truy cập bean khác quá sớm |
| Exception trong `afterPropertiesSet`/`initMethod` | Callback initialization | Kiểm tra điều kiện sai hoặc tài nguyên chưa hợp lệ |
| `@Transactional` không có hiệu lực từ lời gọi nội bộ | Proxy / đường gọi AOP | Gọi bằng `this` hoặc gọi trước khi proxy hoàn tất |
| Bean `@Lazy` chỉ lỗi ở request đầu | Tạo muộn theo yêu cầu | Lỗi đã tồn tại nhưng chỉ bộc lộ lúc bean được khởi tạo |
| Bean có init log nhưng app vẫn fail | Giai đoạn khác của container/runner | Một bean khác thất bại hoặc runner ném exception |
| `@PreDestroy` không được gọi trên prototype | Scope và quản lý destroy | Container không tự theo dõi chu kỳ hủy prototype |

Khi đọc stack trace, hãy tìm **`Caused by` sâu nhất có ý nghĩa**, tên bean liên quan và đoạn giai đoạn tạo lỗi. `BeanCreationException` thường là vỏ bọc mô tả bean nào không hoàn tất được vòng đời; lỗi gốc có thể nằm trong constructor, factory method hoặc callback.

### Trường hợp phụ thuộc vòng tròn

~~~text
ServiceA constructor cần ServiceB
ServiceB constructor cần ServiceA
~~~

Khi cả hai dùng constructor injection trực tiếp, container không thể tạo A trước B đồng thời tạo B trước A. Điều này thường dẫn đến lỗi phụ thuộc vòng tròn. Đừng coi một lỗi như vậy là `@PostConstruct` “chạy sai thứ tự”; thiết kế phụ thuộc cần được xem xét lại. Một số kỹ thuật trì hoãn/proxy có thể giải quyết trường hợp đặc biệt, nhưng che phụ thuộc vòng tròn không phải giải pháp mặc định.

### Thứ tự bean khác thứ tự danh sách

`@Order` có vai trò khi Spring sắp xếp một tập bean được inject theo thứ tự hoặc xử lý một số extension point. Nó **không phải lời cam kết tạo mọi singleton theo thứ tự `@Order`**. Muốn biểu đạt dependency lúc xây dựng bean, hãy dùng constructor injection hoặc quan hệ `@DependsOn` khi có lý do cụ thể; muốn start/stop thành phần hoạt động, dùng phase của `SmartLifecycle`.

## 13. Nên đặt hành động nào vào giai đoạn nào?

| Việc cần làm | Điểm đặt thường phù hợp | Giải thích |
| --- | --- | --- |
| Kiểm tra giá trị cấu hình bắt buộc của một bean | Constructor hoặc `@PostConstruct` | Kiểm tra sớm, phạm vi của chính bean |
| Chuẩn bị cấu trúc dữ liệu cục bộ nhỏ | `@PostConstruct` hoặc init method | Không kéo dài startup và không cần bean khác chạy trước |
| Dùng dependency bắt buộc | Constructor injection | Cho phép khai báo và kiểm tra ngay trong quá trình tạo |
| Điều chỉnh definition trước khi tạo instance | `BeanFactoryPostProcessor`/`BeanDefinitionRegistryPostProcessor` | Tác động metadata, không phải instance |
| Bọc bean hoặc tạo proxy để áp dụng cơ chế hạ tầng | `BeanPostProcessor`/Spring AOP | Cơ chế mở rộng cấp container |
| Thực hiện một việc sau khi singleton thông thường đã khởi tạo | `SmartInitializingSingleton` hoặc `ContextRefreshedEvent` | Không cố làm việc toàn hệ thống giữa quá trình tạo một bean |
| Chạy kiểm tra một lần sau khi context refresh | `ApplicationRunner`/`CommandLineRunner` | Có thể sử dụng các bean đã được container chuẩn bị |
| Bắt đầu/dừng consumer, scheduler, worker theo phase | `SmartLifecycle` | Có cơ chế start/stop điều phối |
| Dọn dẹp socket, connection hoặc tài nguyên cuối vòng đời | `@PreDestroy` hoặc destroy method | Khi container đóng bean theo đường bình thường |

Một quy tắc thực tế: nếu logic cần **một bean đã hoàn thành init**, hãy đặt nó sau giai đoạn tạo bean. Nếu logic cần **toàn context hoặc toàn ứng dụng đạt một mốc**, dùng event/runner/availability thích hợp. Đừng dùng `@PostConstruct` của một bean như sự kiện toàn ứng dụng sẵn sàng.

## 14. Bài tập tự kiểm tra

1. **`BeanDefinition` có phải đối tượng `OrderService` đang chạy không?** Không. Nó là metadata để Spring biết cách tạo/quản lý bean.
2. **Vì sao `@Lazy` có thể vẫn bị tạo sớm?** Vì một singleton non-lazy có thể cần inject trực tiếp bean lazy trong lúc khởi động.
3. **Constructor injection và field injection khác nhau ở thời điểm nào?** Dependency của constructor đã được cung cấp trước khi constructor đích chạy; field injection diễn ra sau khi đã tạo instance.
4. **Một bean vừa thoát constructor đã “fully initialized” chưa?** Chưa chắc; còn inject field/setter, callback Aware, init và hậu xử lý.
5. **Thứ tự `@PostConstruct`, `afterPropertiesSet()` và init method khi ba phương thức khác nhau là gì?** Theo đúng thứ tự vừa liệt kê.
6. **Có thể bảo đảm mọi custom `BeanPostProcessor.postProcessBeforeInitialization` đều chạy trước `@PostConstruct` không?** Không. `@PostConstruct` cũng được hạ tầng xử lý qua post-processor; thứ tự các processor quan trọng.
7. **Đã gọi `@PostConstruct` nghĩa là AOP proxy chắc chắn đã sẵn sàng chưa?** Không; proxy có thể hình thành trong bước hậu xử lý.
8. **Tại sao `@Transactional` có thể không hoạt động khi một phương thức gọi phương thức khác qua `this`?** Vì cuộc gọi có thể không đi qua proxy Spring AOP.
9. **Prototype bean được container tự destroy sau khi không còn ai dùng không?** Thông thường không; bên dùng phải quản lý tài nguyên cần dọn dẹp.
10. **Một bean singleton đã init xong có chứng minh toàn ứng dụng đã phát `ApplicationReadyEvent` không?** Không; context còn có thể đang hoàn thiện và runner chưa chạy.
11. **Nếu `customInit` ném exception, Spring vẫn cấp bean bình thường không?** Không; initialization thất bại thường làm việc tạo bean thất bại và có thể khiến startup thất bại.
12. **Khi cần bắt đầu và dừng một consumer chạy nền theo phase, chọn `@PostConstruct` hay `SmartLifecycle`?** `SmartLifecycle` thường phù hợp hơn, vì có hợp đồng điều phối start/stop và shutdown.

Khi đọc source Spring hoặc chẩn đoán startup, hãy lần theo **định nghĩa bean được đăng ký → container yêu cầu bean → tạo object → inject dependency → chạy init callbacks → áp dụng post-processors → cấp reference**. Chỉ sau đó mới đánh giá xem **context/ứng dụng** đã hoàn thành các mốc chạy tiếp theo hay chưa.

### Tài liệu tham khảo

- Spring Framework — Bean Definition (`BeanDefinition` API): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/config/BeanDefinition.html
- Spring Framework — Customizing the Nature of a Bean (init/destroy callbacks và Aware): https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-nature.html
- Spring Framework — Container Extension Points (`BeanFactoryPostProcessor`, `BeanPostProcessor`): https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-extension.html
- Spring Framework — Lazy-initialized Beans: https://docs.spring.io/spring-framework/reference/6.1/core/beans/dependencies/factory-lazy-init.html
- Spring Framework — Bean Scopes: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-scopes.html
- Spring Framework 6.1 — `SmartInitializingSingleton`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html
- Spring Boot 3.3 — SpringApplication Events/Listeners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot Gradle Plugin 3.3 — Managing Dependencies: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html

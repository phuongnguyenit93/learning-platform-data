# Bean, định nghĩa bean và thể hiện đối tượng trong Spring Core Container

## 1. Ba khái niệm cần tách bạch

Trong Spring Framework, **bean** là đối tượng do Spring IoC container quản lý. Để làm được việc đó, container cần biết **bean được đăng ký theo cấu hình nào** và **khi nào phải tạo hoặc cung cấp một đối tượng thực tế**. Ba thuật ngữ liên quan nhưng không đồng nghĩa:

| Khái niệm | Bản chất | Câu hỏi nó trả lời |
| --- | --- | --- |
| **Bean definition** (`BeanDefinition`) | Metadata/công thức khai báo một bean cho container | Tên gì, tạo bằng cách nào, kiểu gì, scope nào, phụ thuộc gì, lazy hay không? |
| **Bean instance** | Một đối tượng Java thực đã được tạo/cấu hình, nằm trong hoặc được cung cấp qua vòng đời quản lý của Spring | Đối tượng cụ thể nào đã được tạo? Có phải cùng reference với lần lấy trước không? |
| **Bean** | Đối tượng được Spring container quản lý trong ngữ cảnh một bean definition/registration | Spring có thể cung cấp và quản lý đối tượng này theo quy tắc nào? |

Cần nhớ:

- `class UserService` là **kiểu Java**, không tự động là bean.
- `new UserService(...)` tạo một **Java object**; nếu không được đưa qua cơ chế đăng ký/quản lý phù hợp, nó không tự trở thành Spring-managed bean.
- Một phương thức `@Bean UserService userService() {...}` là **nguồn khai báo** để container đăng ký bean definition. Khi container thực thi factory method đó theo scope, đối tượng trả về được quản lý như một bean.
- Một **bean definition** có thể chưa có instance tại thời điểm quan sát, có một instance được chia sẻ, hoặc tạo nhiều instance tùy **scope** và cơ chế khởi tạo.
- Tên bean, tên class và đối tượng là **ba lớp nhận diện khác nhau**. Không nên nói “một class Java = một bean = một instance”.

**Ví dụ tư duy:** bản thiết kế/nguyên liệu (definition) hướng dẫn tạo sản phẩm; sản phẩm cụ thể (instance) là kết quả thực tế. Đây chỉ là phép ví von: container còn có thể xử lý dependency, post-processor, proxy và lifecycle trước khi cung cấp instance.

## 2. Bean definition chứa thông tin gì?

Spring biểu diễn metadata bean bằng các API như `org.springframework.beans.factory.config.BeanDefinition`. Thông tin điển hình:

| Nhóm thông tin | Mục đích | Ví dụ |
| --- | --- | --- |
| Danh tính bean | Tra cứu theo tên và alias, xác định đăng ký nào | `userService`, `mainService` |
| Kiểu/cách tạo | Class, constructor/factory method, đối tượng factory, supplier | `UserService.class`, method `@Bean` |
| Phụ thuộc | Bean khác mà đối tượng cần để được tạo/cấu hình | `UserRepository` truyền qua constructor |
| Scope | Điều chỉnh số lượng/tần suất cung cấp instance | `singleton`, `prototype` |
| Lazy/eager | Khi nào bean có thể được instantiate | `@Lazy` hoặc khởi tạo singleton lúc refresh |
| Giá trị/cấu hình | Property, constructor argument, autowiring metadata | URL, timeout, dependency reference |
| Lifecycle | Các callback khởi tạo/kết thúc được cấu hình phù hợp | `initMethod`, `destroyMethod` |
| Thông tin phụ | Nguồn cấu hình, vai trò, primary/candidate... | Hỗ trợ resolve và quản trị bean |

**Không phải mọi definition đều lưu đủ mọi trường giống nhau.** Tùy loại registration, một phần metadata nằm trong bean definition, một phần được suy ra từ annotation hoặc factory method trong các giai đoạn xử lý container. Đây cũng không phải một object DTO nghiệp vụ thông thường.

### Tên, alias và kiểu khác nhau ra sao?

- Với `@Bean`, tên mặc định **thông thường** là tên phương thức factory, ví dụ method `userService()` tạo bean có tên `userService` (có thể cấu hình bean-name generator hoặc chỉ định `name`).
- `@Bean(name = {"userService", "mainService"})` đăng ký một bean dưới tên chính và một alias. **Alias không tự tạo definition hay instance thứ hai.**
- Hai **definition khác nhau** có thể tạo hai bean cùng class. Vì vậy Spring singleton là **một instance trên mỗi bean definition trong một container** theo quy tắc scope, không phải một object duy nhất của class đó trên toàn JVM.
- Khi lấy bean theo type, nếu có nhiều candidate tương thích và không có quy tắc chọn phù hợp, quá trình resolve có thể báo ambiguity. `@Primary` hoặc `@Qualifier` xử lý bài toán chọn dependency, không phải tạo object thứ hai.

Một `BeanDefinition` được đăng ký có thể được quan sát qua `ConfigurableListableBeanFactory.getBeanDefinition(name)` trong context thích hợp; đó là **metadata**, không phải lời gọi lấy đối tượng như `getBean(name)`.

## 3. Từ định nghĩa đến instance: quá trình diễn ra thế nào?

Sơ đồ khái niệm (các triển khai/extension points cụ thể có thể có thêm bước):

~~~text
Nguồn cấu hình
@Configuration / @Bean / @Component scan / XML / registration bằng code
                 |
                 v
  Phân tích và đăng ký BeanDefinition
                 |
                 v
  BeanFactoryPostProcessor có thể xử lý metadata
                 |
                 v
  Xác định scope, lazy, dependency và điều kiện tạo
                 |
                 v
  Factory/constructor tạo đối tượng Java thực
                 |
                 v
  Inject/cấu hình, BeanPostProcessor, init callbacks
                 |
                 v
  Container cung cấp bean reference cho nơi sử dụng
                 |
                 v
  Đóng context hoặc kết thúc scope: callback phù hợp
~~~

Một số điểm chính:

1. Container **đọc cấu hình** và đăng ký các bean definitions; definition là công thức tạo, **không đồng nhất** với đối tượng đã được tạo.
2. Spring **resolve dependency** trước hoặc trong quá trình tạo và cấu hình bean. Constructor injection, tham số của `@Bean` factory method và property injection là những cơ chế thường gặp.
3. Container gọi constructor hoặc factory method, có thể áp dụng `BeanPostProcessor`, tạo proxy khi cấu hình yêu cầu, rồi chạy initialization callbacks thích hợp trước khi ứng dụng dùng bean.
4. Khi gọi `getBean`, thứ được trả về là **bean object/reference** do container cung cấp. Trong trường hợp có proxy, object được cung cấp có thể là **proxy**, không cùng runtime class với target; không nên xem `getClass()` luôn bằng class gốc.
5. Việc có definition **không bảo đảm** quá trình tạo bean thành công: dependency thiếu, ambiguity, constructor ném exception hoặc vòng phụ thuộc không giải được đều có thể làm bootstrap/lookup thất bại.

### Hai loại extension point dễ nhầm

- `BeanFactoryPostProcessor` chủ yếu tác động vào **bean-definition metadata** trước khi bean thông thường được instantiate.
- `BeanPostProcessor` xử lý **bean instance** trong các giai đoạn khởi tạo. Nó có thể trả về một object thay thế hoặc proxy theo hợp đồng thích hợp.

Không nên gọi `getBean()` bừa bãi bên trong post-processor metadata: hành động đó có thể ép tạo instance quá sớm và khiến một số bước hậu xử lý không diễn ra như mong đợi.

## 4. Một definition có thể tương ứng bao nhiêu instance?

**Scope** quyết định phần rất quan trọng của mối quan hệ giữa bean definition và các instance.

| Scope | Quy tắc điển hình | Gọi `getBean()` hai lần |
| --- | --- | --- |
| `singleton` (mặc định) | Một instance được chia sẻ theo bean definition trong một IoC container | Nhận cùng bean reference (khi không có cơ chế lookup đặc biệt) |
| `prototype` | Container tạo/cấu hình một instance mới mỗi lần yêu cầu bean | Thường nhận hai instance khác nhau |
| `request` | Một bean instance trong phạm vi một HTTP request | Phụ thuộc request hiện hành; cần web-aware context |
| `session` | Gắn theo một HTTP session | Phụ thuộc session hiện hành; cần web-aware context |
| Custom scope | Theo quy tắc do ứng dụng khai báo | Không thể suy ra nếu chưa biết custom scope |

Một **bean definition prototype** là *một công thức có thể tạo nhiều đối tượng*, không có nghĩa có nhiều definition được tự động tạo ra.

**Singleton của Spring khác GoF Singleton:** cùng một class có thể có nhiều singleton beans nếu đăng ký nhiều definition hoặc nhiều contexts. Đặc biệt, Spring không tự bảo đảm đối tượng được tạo bằng `new` ở bên ngoài container dùng chung với singleton bean nào đó.

**Lifecycle:** container thường quản lý việc hủy các singleton phù hợp khi đóng context; đối với prototype, Spring thông thường **không tự gọi đầy đủ destruction callbacks** sau khi đã giao instance cho caller. Với prototype chứa tài nguyên cần đóng, bên dùng phải có chiến lược cleanup phù hợp.

### Lazy không đồng nghĩa với prototype

- Các singleton **không lazy** trong `ApplicationContext` thường được pre-instantiate khi context refresh.
- Bean singleton gắn `@Lazy` thường được tạo khi lần đầu thực sự cần; **definition có thể tồn tại trước instance**.
- Nếu một singleton `@Lazy` là dependency cần thiết của một singleton eager, nó vẫn có thể được tạo trong quá trình khởi động để đáp ứng dependency.
- `@Lazy` không tự đổi scope sang prototype. Lazy quyết định **thời điểm**; scope quyết định **cách chia sẻ/số instance**.

## 5. Đăng ký definition từ đâu?

Spring có một số cách khai báo bean. Ví dụ ngắn trong mục này minh họa **cú pháp**, không phải tệp Java chạy độc lập.

### Cách A — Java configuration với `@Bean`

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    PaymentService paymentService(PaymentRepository repository) {
        return new PaymentService(repository);
    }
}
~~~

Đoạn trên giả định đã có class `PaymentService`, interface `PaymentRepository`, bean `PaymentRepository` và các import Spring phù hợp. Khi context đọc `AppConfig`, nó đăng ký definition cho `paymentService`; lúc tạo instance, Spring resolve `repository` theo quy tắc injection.

`@Configuration(proxyBeanMethods=false)` phù hợp khi **không gọi trực tiếp các phương thức `@Bean` để lấy bean qua interception**; trong chế độ này lời gọi Java thông thường tới method factory có thể tạo object mới bên ngoài việc lookup singleton của container. Dùng tham số `@Bean` hoặc constructor để biểu diễn dependency rõ ràng.

### Cách B — Component scanning

~~~java
@Component
class EmailSender {
    void send(String message) {
        System.out.println(message);
    }
}
~~~

Class chỉ trở thành bean nếu context đã **đăng ký/quét package** chứa class đó qua `@ComponentScan`, `context.scan(...)` hoặc cơ chế cấu hình tương ứng. Annotation không tự khiến toàn JVM biết đến bean.

### Cách C — XML hoặc programmatic registration

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">
    <bean id="emailSender" class="demo.EmailSender" scope="singleton"/>
</beans>
~~~

Đây là ví dụ **XML cấu hình độc lập về cú pháp**, không dùng để chạy chương trình Java ở mục 6. Programmatic registration còn có thể dùng `GenericApplicationContext` / `BeanDefinitionRegistry` và API định nghĩa bean thích hợp. Các cách khác nhau đều cung cấp **metadata/registration cho container**; không cần biến mọi object thành component scan.

## 6. Ví dụ chạy độc lập: quan sát definition, singleton, prototype và alias

Đây là chương trình **Spring Framework thuần**, không cần Spring Boot, database hay máy chủ HTTP. Nó quan sát rõ: metadata tồn tại **trước lần truy vấn instance lazy**, alias không tạo definition thứ hai, singleton được tái sử dụng và prototype tạo instance mới.

### 6.1. Yêu cầu và cấu trúc dự án

Cần **JDK 17+**, **Maven 3.9+** và internet ở lần tải dependencies đầu. Spring Framework **7.0.9** giữ baseline Java 17; ví dụ khóa phiên bản để giảm sự khác biệt khi chạy lại.

~~~text
bean-definition-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanDefinitionDemo.java
~~~

### 6.2. Tệp `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-definition-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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
                <configuration>
                    <mainClass>demo.BeanDefinitionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` kéo theo các module Spring cần thiết qua Maven dependency graph; không cần tự tải từng JAR `spring-beans`. Maven Compiler Plugin gọi compiler Java với release mục tiêu 17, còn Exec Plugin chạy class `main` với dependency classpath.

### 6.3. Tệp `src/main/java/demo/BeanDefinitionDemo.java`

~~~java
package demo;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Scope;

public final class BeanDefinitionDemo {
    private BeanDefinitionDemo() {
    }

    public static final class CatalogRepository {
        static int created;
        private final int id;

        CatalogRepository() {
            id = ++created;
        }

        int id() {
            return id;
        }
    }

    public static final class ReportJob {
        static int created;
        private final int id;
        private final CatalogRepository repository;

        ReportJob(CatalogRepository repository) {
            this.repository = repository;
            id = ++created;
        }

        int id() {
            return id;
        }

        CatalogRepository repository() {
            return repository;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean(name = {"catalogRepository", "catalogAlias"})
        @Lazy
        public CatalogRepository catalogRepository() {
            return new CatalogRepository();
        }

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public ReportJob reportJob(CatalogRepository repository) {
            return new ReportJob(repository);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            BeanDefinition definition =
                    context.getBeanFactory()
                            .getBeanDefinition("catalogRepository");

            System.out.println("definitionExists="
                    + context.containsBeanDefinition("catalogRepository"));
            System.out.println("aliasIsBean="
                    + context.containsBean("catalogAlias"));
            System.out.println("aliasIsDefinition="
                    + context.containsBeanDefinition("catalogAlias"));
            System.out.println("definitionLazy="
                    + definition.isLazyInit());
            System.out.println("repositoryCountBeforeGet="
                    + CatalogRepository.created);

            CatalogRepository first =
                    context.getBean(CatalogRepository.class);
            CatalogRepository second =
                    context.getBean("catalogAlias", CatalogRepository.class);

            System.out.println("repositoryCountAfterGet="
                    + CatalogRepository.created);
            System.out.println("sameSingleton=" + (first == second));

            BeanDefinition reportDefinition =
                    context.getBeanFactory().getBeanDefinition("reportJob");
            System.out.println("reportScope="
                    + reportDefinition.getScope());

            ReportJob reportA = context.getBean(ReportJob.class);
            ReportJob reportB = context.getBean(ReportJob.class);

            System.out.println("samePrototype=" + (reportA == reportB));
            System.out.println("reportIds="
                    + reportA.id() + "," + reportB.id());
            System.out.println("bothUseSameRepository="
                    + (reportA.repository() == first
                    && reportB.repository() == first));
        }
    }
}
~~~

**Chạy trong thư mục `bean-definition-demo` chứa `pom.xml`:**

~~~bash
java -version
mvn -version
mvn -q compile exec:java
~~~

Lệnh `mvn -q compile exec:java` chạy compiler theo cấu hình Maven rồi chạy chương trình. Không dùng `java demo.BeanDefinitionDemo` trực tiếp từ thư mục dự án khi chưa cấu hình đầy đủ classpath thư viện.

**Stdout chính xác của 11 câu `System.out.println` trong ứng dụng** (không tính output của `java -version`, `mvn -version` và log/diagnostic có thể xuất hiện từ Maven hoặc logging backend):

~~~text
definitionExists=true
aliasIsBean=true
aliasIsDefinition=false
definitionLazy=true
repositoryCountBeforeGet=0
repositoryCountAfterGet=1
sameSingleton=true
reportScope=prototype
samePrototype=false
reportIds=1,2
bothUseSameRepository=true
~~~

Mỗi lần chạy chương trình trong một JVM mới, các biến `static created` khởi đầu bằng 0. Bộ đếm là công cụ của ví dụ, không phải property mặc định của Spring.

### 6.4. Giải thích từng kết quả

1. `containsBeanDefinition("catalogRepository")` cho `true`: context đã đăng ký metadata của bean.
2. `containsBean("catalogAlias")` là `true` vì alias trỏ đến registration được biết đến; `containsBeanDefinition("catalogAlias")` là `false` vì alias **không phải một definition khác**.
3. `definition.isLazyInit()` là `true`: annotation `@Lazy` mô tả việc trì hoãn tạo singleton. Trước khi lookup, `CatalogRepository.created=0` vì chưa có bean eager nào cần instance này.
4. Hai lần lookup theo kiểu và theo alias dẫn tới **cùng object** cho singleton; constructor chỉ chạy một lần, nên bộ đếm bằng 1.
5. Bean `reportJob` có scope `prototype`; hai lần `getBean(ReportJob.class)` tạo hai `ReportJob` có id 1 và 2, nên `==` trả `false`.
6. Cả hai prototype được inject **cùng singleton `CatalogRepository`** qua tham số của factory method `reportJob`. Vì thế `bothUseSameRepository=true`.

Một vài chi tiết để đọc kết quả đúng: `getBeanDefinition(...)` trả **metadata**, còn `getBean(...)` trả **đối tượng**; `getScope()` trên bean không khai báo `scope` tường minh có thể trả chuỗi rỗng (nghĩa là mặc định singleton), không nhất thiết chuỗi `singleton`. Do đó ví dụ chủ động in scope của bean prototype vốn có giá trị rõ ràng.

## 7. Bean instance khác các object được tạo thủ công thế nào?

Xét ba trường hợp:

| Cách tạo/nhận đối tượng | Có bean definition tương ứng trong context? | Ai quản lý lifecycle? |
| --- | --- | --- |
| `context.getBean(CatalogRepository.class)` | Có, trong context của ví dụ | Spring quản lý bean theo scope/callback |
| `new CatalogRepository()` ở code ứng dụng bên ngoài Spring | Không vì hành động `new` đơn lẻ | Code tự tạo/chịu trách nhiệm |
| `new CatalogRepository()` trong `@Bean` factory method | Definition do `@Bean` cung cấp; object trả về được quản lý | Spring tiếp nhận **object trả về** như bean |

Không phải mọi object được tạo bên trong factory method đều thành bean. Nếu factory tạo một object tạm `helper` nhưng chỉ trả về một object khác, `helper` không tự là bean nếu không được đăng ký.

**Object reference và bean name cũng không đồng nhất:**

- Cùng bean có thể có **nhiều alias** nhưng chỉ một instance singleton được cung cấp cho tên đó.
- Cùng class có thể có **nhiều bean definitions**, mỗi definition singleton có instance riêng.
- Cùng bean definition prototype có thể sản sinh **nhiều instance**.
- Proxy/AOP có thể khiến reference Spring trả về trỏ đến proxy; đừng dùng `getClass()` hoặc `new` làm phép thử duy nhất cho câu hỏi một đối tượng có được Spring quản lý hay không.

**Không có chuyện Spring thay đổi quy tắc `new` của Java.** Spring chỉ định nghĩa cách đăng ký, tạo/cấu hình và quản lý object thuộc phạm vi container.

## 8. Thời điểm tạo, lifecycle và những giới hạn cần nhớ

Ở mức nhập môn, vòng đời bean thường được học theo mô hình:

~~~text
BeanDefinition có hiệu lực
          |
          v
  Resolve dependencies
          |
          v
  Constructor/factory method
          |
          v
  Inject/cấu hình + hậu xử lý phù hợp
          |
          v
    Init callbacks
          |
          v
  Bean được đưa vào sử dụng
          |
          v
  End of scope / context close
          |
          v
  Destroy callbacks nếu scope hỗ trợ
~~~

Có thể dùng `@Bean(initMethod = "start", destroyMethod = "stop")` khi class có các method thích hợp để container gọi theo lifecycle; với annotation-based component, các callback như `@PostConstruct`/`@PreDestroy` thuộc namespace **`jakarta.annotation`** ở các thế hệ Spring hiện đại.

**Điểm đặc biệt dễ sai:**

- `ApplicationContext` thông thường tạo các singleton **không lazy** khi refresh; đừng mặc định rằng gọi `getBean` luôn là lần constructor chạy đầu.
- `@Lazy` có thể không trì hoãn được bean nếu một singleton eager cần dependency đó ngay khi bootstrap.
- Prototype bean được tạo mỗi lần yêu cầu; Spring không tự chạy đầy đủ destruction callback sau khi giao prototype cho caller. Nếu bean giữ connection/file/socket, cần cơ chế cleanup của caller.
- Inject một prototype vào **constructor của singleton** không tự làm dependency mới mỗi lần singleton gọi method; injection thường xảy ra một lần khi singleton được tạo. Nếu muốn tạo prototype theo từng lần dùng, cần cơ chế lookup/provider thích hợp.
- `context.close()` không đồng nghĩa với Java garbage collection tức thì. Nó kích hoạt lifecycle/shutdown phù hợp; reference còn tồn tại thì object Java vẫn có thể tiếp tục tồn tại.
- Bean đăng ký thất bại khi metadata/dependency thiếu hoặc sai, ambiguity, constructor ném lỗi, chu trình constructor không giải được... Không nên lấy `BeanDefinition` làm chứng cứ rằng instance đã được tạo thành công.

### Khi nào quan sát definition và khi nào lấy instance?

- Xem `BeanDefinition`, scope, lazy và source metadata khi **debug cấu hình container** hoặc xây công cụ mở rộng. Thông thường làm việc qua `ConfigurableListableBeanFactory`/registry trong đúng giai đoạn.
- Dùng dependency injection và nhận object thực qua constructor/`@Bean` parameter khi **viết nghiệp vụ**. Tránh rải `context.getBean` trong mọi service, biến service thành service locator và làm khó kiểm thử.
- Dùng `getBean` có chủ đích ở bootstrap, công cụ thử nghiệm, plugin lookup hoặc nhu cầu dynamic lookup; cần biết scope và chi phí tạo đối tượng.
- Không sửa bean definitions tùy tiện **sau khi context đã tạo các singleton**: metadata thay đổi lúc này không tự tái tạo mọi bean đang tồn tại hoặc tự cập nhật các tham chiếu đã inject.

## 9. Lỗi thường gặp khi nhầm definition với instance

| Nhận định sai | Diễn giải đúng |
| --- | --- |
| “Một `@Bean` method tương đương một object được tạo ngay” | Đó là một nguồn bean definition; thời điểm instantiate tùy scope/lazy/dependency/refresh |
| “`BeanDefinition` là chính bean object” | Definition là metadata, instance là object thực |
| “Một class Java luôn chỉ có một Spring bean” | Có thể đăng ký nhiều definitions của cùng class, hoặc không có definition nào |
| “Hai bean names luôn là hai objects” | Có thể là alias cùng bean, không tạo object mới |
| “Prototype nghĩa là nhiều definitions tự động” | Một definition có thể tạo nhiều instances |
| “Singleton nghĩa là một object cho mọi Spring context/JVM” | Scope mặc định theo **container + bean definition** |
| “Thêm `@Component` là Spring luôn thấy class đó” | Cần scan/registration đúng context |
| “`@Bean` method bị gọi trực tiếp luôn trả bean singleton” | Với `proxyBeanMethods=false`, lời gọi Java trực tiếp vẫn là lời gọi method thông thường |
| “Có `BeanDefinition` thì bean chắc chắn instantiate được” | Tạo bean có thể thất bại vì dependency/config/constructor |
| “Close context phá hủy hết Java objects” | Spring chỉ gọi lifecycle phù hợp; object/reference và GC theo Java |

**Tình huống kiểm tra lỗi hay gặp:** có hai definitions `EmailSender` khác nhau nhưng inject một `EmailSender` mà không quy định candidate. Khi đó việc xác định bean phù hợp có thể mơ hồ và fail lúc tạo bean dùng dependency. Đừng giải quyết bằng cách đổi tên Java class ngẫu nhiên; kiểm tra bean names, types, `@Qualifier`, `@Primary`, factory methods và cấu hình scan.

## 10. Bài tập tự kiểm tra

Thực hiện từng thay đổi **trên một bản sao** và khôi phục code gốc giữa các bài để so sánh stdout chính xác.

1. **Bỏ `@Lazy`** trên `catalogRepository()`: dự đoán `repositoryCountBeforeGet` và lý do. Với default eager singleton trong context hiện tại, nó thường thành `1` ngay sau khi context tạo xong.
2. **Đổi scope `reportJob` về singleton** bằng cách bỏ `@Scope`: dự đoán `samePrototype` (sẽ là `true`) và `reportIds` (thường là `1,1`). Vì tên `samePrototype` lúc này không phù hợp, hãy đổi tên nhãn theo ý nghĩa.
3. **Bỏ alias `catalogAlias`** khỏi `@Bean(name=...)`: dự đoán `containsBean("catalogAlias")` và lời gọi `getBean("catalogAlias", ...)` sẽ ra sao. Có thể kiểm thử qua `NoSuchBeanDefinitionException`.
4. **Thêm một `@Bean` khác cùng kiểu `CatalogRepository` nhưng khác tên**: quan sát vì sao lookup `getBean(CatalogRepository.class)` có thể mơ hồ. Thử `@Qualifier` hoặc lấy theo bean name.
5. **Tạo trực tiếp `new CatalogRepository()` bên ngoài context**: bộ đếm static có tăng không? Spring definition/alias có đổi không? Tại sao object đó không tự thuộc container?
6. **Đặt thử một instance stateful và mutable trong singleton**: mô tả rủi ro khi nhiều luồng dùng chung, và tại sao scope **không** tự bảo đảm thread safety.
7. **Đóng context và giữ một reference**: phân biệt lifecycle callbacks với object GC, tránh khẳng định object bị xóa ngay khi `close()`.

### Tự đánh giá

Bạn đã nắm bài nếu tự giải thích, không cần đoán:

- [ ] Bean definition là gì; nó khác class, bean name và bean instance như thế nào?
- [ ] `containsBeanDefinition`, `getBeanDefinition`, `containsBean` và `getBean` trả lời các câu hỏi gì khác nhau?
- [ ] Một definition singleton so với prototype tạo/cấp bao nhiêu instance?
- [ ] Vì sao alias không tạo thêm bean instance?
- [ ] Vì sao `@Lazy` và scope trả lời **hai câu hỏi khác nhau**?
- [ ] Bằng chứng thực tế nào trong stdout chứng minh definition có trước singleton instance?
- [ ] Thay đổi `@Bean` factory method có thể ảnh hưởng dependency graph/lifecycle ra sao?

## 11. Tóm tắt và tài liệu chính thức

**Ghi nhớ cốt lõi:**

- **Bean definition = metadata/công thức.**
- **Bean instance = object thực được tạo và cung cấp theo scope.**
- **Spring bean = object được IoC container quản lý** trong một registration/context phù hợp.
- Definition có thể tồn tại trước instance; singleton thường chia sẻ một instance, prototype cung cấp instance mới mỗi lần yêu cầu.
- Bean name và alias là tên tra cứu, không phải số lượng object.
- `BeanFactory`/registry quản lý metadata, còn `ApplicationContext` giúp bootstrap và sử dụng ứng dụng; nên ưu tiên DI hơn việc tra `getBean` ở mọi nơi.

Tài liệu chính thức để kiểm tra thêm:

- [Spring – Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
- [Spring – Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring – Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html)
- [Spring – Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring – Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)

**Kết luận:** Đừng nhầm “Spring **biết cách tạo** bean” với “Spring **đã tạo** một object”, cũng đừng nhầm tên bean với instance. Phân biệt chính xác `BeanDefinition` và bean instance là nền để hiểu dependency injection, scope, lazy loading, proxy, lifecycle và việc debug Core Container.
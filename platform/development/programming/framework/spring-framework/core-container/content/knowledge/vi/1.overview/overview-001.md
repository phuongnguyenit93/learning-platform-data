# Core Container là gì và nằm ở đâu trong Spring Framework?

## 1. Câu trả lời ngắn: lớp nền tảng quản lý đối tượng của Spring

**Spring Core Container** là nhóm module và cơ chế nền tảng giúp một ứng dụng Java **khai báo, tạo, kết nối, cấu hình và quản lý vòng đời các đối tượng mà Spring phụ trách**. Những đối tượng được container quản lý gọi là **Spring beans**. Thành phần nổi bật nhất là **IoC container** (*Inversion of Control container*), thông thường được truy cập qua giao diện `ApplicationContext`.

Thay vì mỗi đối tượng tự đi tìm hoặc tự tạo tất cả đối tượng cộng tác, ứng dụng mô tả chúng phụ thuộc vào những gì; container đọc cấu hình và **cung cấp các phụ thuộc (Dependency Injection – DI)** khi tạo bean. Nhờ đó mã nghiệp vụ bớt gắn chặt với cách khởi tạo và dễ thay thế thành phần khi kiểm thử.

Một cách phân biệt đơn giản:

- **Core Container**: phần nền trong Spring Framework, gồm nhiều module và API; không phải tên của một class Java duy nhất.
- **IoC container**: cơ chế cụ thể đọc metadata, quản lý bean và lắp ráp quan hệ phụ thuộc.
- **Bean**: một đối tượng được container quản lý; không phải cứ dùng từ khóa `new` trong Java thì đối tượng tự trở thành Spring bean.
- **DI**: một cách hiện thực IoC, trong đó dependency được đưa vào đối tượng thay vì đối tượng tự tìm/tạo dependency.

Ví dụ, `OrderService` cần `OrderRepository`. Nếu tự tạo `new JdbcOrderRepository(...)` trong `OrderService`, lớp dịch vụ trực tiếp biết về việc khởi tạo implementation. Với DI, `OrderService` nhận một `OrderRepository` qua constructor; container chọn và cấp một bean phù hợp theo cấu hình.

**Không đồng nhất container với một web server.** Có thể tạo `ApplicationContext` trong chương trình Java chạy console, một ứng dụng batch hay một tiến trình không dùng HTTP.

## 2. Core Container nằm ở vị trí nào trong Spring Framework?

Spring Framework là tập hợp nhiều **module (artifact/JAR)** với các chức năng khác nhau. Core Container nằm **ở trung tâm/nền của mô hình ứng dụng**, cung cấp khả năng quản lý đối tượng để các phần khác sử dụng:

~~~text
                     ỨNG DỤNG JAVA
                (console, batch, web, ...)
                            |
     +----------------------+----------------------+
     |                      |                      |
   Spring MVC/           Data Access/          Spring AOP/
   Spring WebFlux         Transaction           Messaging/...
     |                      |                      |
     +----------------------+----------------------+
                            |
                CORE CONTAINER (IoC/DI)
                   BeanFactory / Context
                            |
           spring-core, spring-beans,
           spring-context, spring-expression
                            |
                           JVM
~~~

Sơ đồ này là **sơ đồ khái niệm về vai trò**, không phải sơ đồ dependency Maven tuyệt đối: mỗi module có các dependency kỹ thuật riêng, và không phải mọi ứng dụng đều cần tất cả phần phía trên. Ví dụ, `spring-webmvc` xử lý yêu cầu HTTP nhưng vẫn có thể dựa vào `ApplicationContext` để nhận controller, service và các bean khác. AOP/transaction thường **được tích hợp qua cơ chế bean/proxy** chứ không phải chính IoC container tự động bật tất cả hành vi đó.

**Spring Framework khác Spring Boot:**

- **Spring Framework** cung cấp nền tảng DI/IoC cùng các module web, dữ liệu, transaction, AOP... mà ứng dụng lựa chọn.
- **Spring Boot** xây **trên Spring Framework**, giúp cấu hình, khởi động, quản lý phụ thuộc và auto-configuration thuận tiện hơn. Boot **sử dụng Core Container**, không thay thế nó bằng một cơ chế IoC độc lập.
- `@SpringBootApplication` là tiện ích của Boot, **không bắt buộc** để dùng `ApplicationContext` của Spring Framework thuần.
- Có Core Container không có nghĩa là sẵn HTTP server, REST endpoint, database, transaction hoặc Spring Security. Chúng cần module, cấu hình và điều kiện phù hợp.

Ví dụ bài này dùng **Spring Framework trực tiếp**, không cần Boot và không cần máy chủ web.

## 3. Các module ở phần nền và nhiệm vụ chính

| Artifact/module | Vai trò dễ nhớ | Ví dụ API/chức năng |
| --- | --- | --- |
| `spring-core` | Tiện ích cốt lõi và hạ tầng cho Framework | `Resource`, chuyển đổi kiểu, tiện ích nền |
| `spring-beans` | Mô hình bean, metadata và nền của IoC | `BeanFactory`, `BeanDefinition`, wiring các phụ thuộc |
| `spring-context` | Container ở mức ứng dụng và các tính năng đi kèm | `ApplicationContext`, cấu hình bằng annotation, sự kiện, i18n |
| `spring-expression` | Ngôn ngữ biểu thức Spring (SpEL) | Biểu thức `#{...}` trong ngữ cảnh hỗ trợ |
| `spring-context-support` | Tích hợp hỗ trợ bổ sung quanh context | Các adapter/tích hợp chuyên biệt, **không** phải bước bắt buộc cho ví dụ DI đơn giản |

Nhóm module có thể được diễn giải khác nhau tùy sơ đồ tài liệu và phiên bản Spring; bốn artifact đầu là những phần rất thường được nhắc đến khi học IoC. `spring-context-support` là **module hỗ trợ tùy nhu cầu**, không cần thêm chỉ để viết `@Bean`.

Tên artifact Maven dạng `spring-context`, còn các package Java như `org.springframework.context` là **namespace mã nguồn**; đừng nhầm package Java với JAR Maven hay với **JPMS module** (`spring.context`). Khi thêm dependency `spring-context` qua Maven/Gradle, các module cần thiết khác thường được kéo theo **theo dependency transitive**, nên không nhất thiết phải khai báo thủ công từng JAR.

Spring còn có các module khác (`spring-web`, `spring-webmvc`, `spring-jdbc`, `spring-tx`, `spring-aop`, `spring-test`, ...). Chúng cung cấp khả năng chuyên ngành, **không đồng nghĩa** với `spring-core` hay toàn bộ Core Container.

## 4. Cơ chế IoC/DI: Spring quản lý những gì?

Một vòng đời rút gọn của ứng dụng dùng context:

~~~text
Cấu hình (annotation / @Bean / XML / đăng ký bằng code)
                         |
                         v
            Container đọc bean metadata
                         |
                         v
         Xác định cách tạo và nối dependency
                         |
                         v
       Tạo bean, tiêm dependency, khởi tạo
                         |
                         v
      Ứng dụng lấy hoặc được cấp bean để dùng
                         |
                         v
        Đóng context, hủy bean phù hợp
~~~

**Bean definition** là **mô tả/cấu hình** của bean: kiểu, tên, scope, dependency, cách tạo, các callback... Bean instance là **đối tượng thực** sau khi được tạo. Không phải một bean definition luôn bằng một đối tượng ngay lập tức: scope và chính sách khởi tạo ảnh hưởng thời điểm/số lần tạo.

Ba cách cung cấp cấu hình phổ biến:

1. **Java configuration**: `@Configuration` và các factory method `@Bean` khai báo bean; rất dễ thấy dependency qua tham số của factory method.
2. **Component scanning**: `@Component`, `@Service`, `@Repository`, `@Controller` và `@ComponentScan` khi phù hợp để Spring dò thành phần rồi đăng ký bean.
3. **XML hoặc đăng ký programmatic**: vẫn có ứng dụng dùng `ClassPathXmlApplicationContext`, `GenericApplicationContext` hoặc các API đăng ký bean trực tiếp.

**Không phải cứ thêm `@Component` vào class là bean tự xuất hiện**: class đó phải được đưa vào nguồn cấu hình/scan thích hợp. Tương tự, nếu một đối tượng được tự tạo bằng `new` bên ngoài context, annotation DI trên nó không tự được Spring xử lý.

DI phổ biến nhất cho dependency bắt buộc là **constructor injection**:

~~~java
// Đoạn minh họa Java thuần, đặt trong các type thích hợp.
interface EmailSender {
    void send(String message);
}

class NotificationService {
    private final EmailSender sender;

    NotificationService(EmailSender sender) {
        this.sender = sender; // Dependency do caller/container cung cấp.
    }

    void notifyUser() {
        sender.send("Ready");
    }
}
~~~

Vì `NotificationService` nhận interface, khi kiểm thử có thể truyền một implementation giả (*fake*) mà không sửa logic của service. Constructor injection không phải chỉ xuất hiện trong Spring: đó cũng là một kỹ thuật thiết kế Java thuần; **Spring tự động hóa việc tạo/cấp đối tượng** dựa trên cấu hình.

## 5. `BeanFactory` và `ApplicationContext`: hiểu đúng vai trò

| Tiêu chí | `BeanFactory` | `ApplicationContext` |
| --- | --- | --- |
| Vai trò | Giao diện nền cho truy cập/quản lý bean | Giao diện container hướng ứng dụng, **mở rộng** `BeanFactory` |
| API dễ thấy | `getBean(...)`, kiểm tra thông tin bean | Bao gồm API `BeanFactory`; thêm sự kiện, tài nguyên, message/i18n và các tiện ích khác |
| Dùng cho ứng dụng mới | Thường không cần thao tác trực tiếp | **Lựa chọn thông dụng** cho bootstrap Spring |
| Thời điểm khởi tạo singleton | Phụ thuộc implementation/việc cấu hình bootstrap | Thông thường khởi tạo các singleton **không lazy** khi refresh context |
| Ví dụ implementation | `DefaultListableBeanFactory` | `AnnotationConfigApplicationContext`, `ClassPathXmlApplicationContext` |

`ApplicationContext` là **một loại `BeanFactory`**, không phải hai container phải tạo độc lập. Những phần như `BeanPostProcessor`, xử lý annotation và lifecycle được kích hoạt qua quá trình bootstrap phù hợp; chỉ tạo một `DefaultListableBeanFactory` thuần rồi mong mọi annotation tự chạy có thể không đạt kết quả mong đợi.

Không nên suy ra “`BeanFactory` luôn lazy còn `ApplicationContext` luôn eager” như quy tắc tuyệt đối. Scope, lazy-init và cách dùng implementation quyết định chi tiết; cách nói an toàn là `ApplicationContext` thông thường **pre-instantiate các singleton không lazy** khi refresh.

## 6. Thực hành Spring Core Container thuần với Java 17+

Ví dụ hoàn chỉnh này minh họa **container tạo bean và tiêm một dependency bằng tham số `@Bean`**, không dùng Spring Boot, HTTP hay database. Cần **JDK 17+ và Maven 3.9+** (Maven sẽ tải thư viện từ repository ở lần đầu chạy).

Trong thư mục `core-container-demo`, tạo cấu trúc:

~~~text
core-container-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── CoreContainerDemo.java
~~~

### 6.1. `pom.xml` – khai báo Spring Framework

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>core-container-demo</artifactId>
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
                    <mainClass>demo.CoreContainerDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Version **Spring Framework 7.0.9** được cố định trong ví dụ để mọi người chạy cùng một phiên bản; đây là một bản thuộc dòng 7.0 hỗ trợ **Java 17 làm baseline**, mặc dù dòng Spring 7 khuyến nghị JDK LTS mới hơn cho các dự án phù hợp. Khi dùng trong dự án thật, hãy theo chính sách quản lý dependency/BOM và cập nhật bản vá có hỗ trợ, thay vì tự giữ mãi version học tập này.

### 6.2. `src/main/java/demo/CoreContainerDemo.java`

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class CoreContainerDemo {
    private CoreContainerDemo() {
    }

    interface MessageRepository {
        String prefix();
    }

    static final class FixedMessageRepository implements MessageRepository {
        @Override
        public String prefix() {
            return "Xin chao";
        }
    }

    static final class WelcomeService {
        private final MessageRepository repository;

        WelcomeService(MessageRepository repository) {
            this.repository = repository;
        }

        String greet(String name) {
            return repository.prefix() + ", " + name + "!";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean
        MessageRepository messageRepository() {
            return new FixedMessageRepository();
        }

        @Bean
        WelcomeService welcomeService(MessageRepository repository) {
            return new WelcomeService(repository);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            WelcomeService service = context.getBean(WelcomeService.class);

            System.out.println("message=" + service.greet("Lan"));
            System.out.println("hasBean="
                    + context.containsBean("welcomeService"));
            System.out.println("sameSingleton="
                    + (service == context.getBean(WelcomeService.class)));
            System.out.println("contextType="
                    + context.getClass().getSimpleName());
        }
    }
}
~~~

**Chạy tại thư mục chứa `pom.xml`:**

~~~bash
java -version
mvn -version
mvn -q compile exec:java
~~~

Maven Compiler Plugin biên dịch code với `--release 17` theo property đã khai báo. Maven phụ trách **classpath gồm Spring và dependency transitive**, do đó dùng `javac`/`java` thủ công mà không thiết lập classpath cho JAR Spring sẽ báo thiếu package/class. Lệnh `mvn -q compile exec:java` vừa biên dịch bằng `javac` thông qua plugin, vừa khởi chạy main class.

**Stdout từ bốn câu `System.out.println` của ứng dụng** (không tính thông tin phiên bản ở hai lệnh kiểm tra môi trường, và không tính log/diagnostic do Maven hay logging backend phát sinh ngoài ứng dụng):

~~~text
message=Xin chao, Lan!
hasBean=true
sameSingleton=true
contextType=AnnotationConfigApplicationContext
~~~

Đây là stdout xác định của logic ví dụ: bean tên `welcomeService` được factory method cùng tên đăng ký; mặc định bean có **singleton scope** trong context nên hai lần lấy cùng kiểu cho cùng một instance. Nếu IDE/logging in thêm thông tin vào console, hãy phân biệt nó với bốn dòng do chính chương trình in.

### 6.3. Đối chiếu từng bước trong ví dụ

1. `new AnnotationConfigApplicationContext(AppConfig.class)` tạo context, đăng ký class cấu hình và thực hiện bootstrap/refresh trong cách dùng constructor này.
2. `@Configuration` đánh dấu class `AppConfig` làm nguồn bean definitions; `proxyBeanMethods=false` chọn cách xử lý phù hợp khi **không dựa vào việc gọi trực tiếp `@Bean` method này từ method khác**.
3. `@Bean messageRepository()` tạo bean `MessageRepository` bằng `FixedMessageRepository`.
4. `@Bean welcomeService(MessageRepository repository)` yêu cầu Spring **resolve tham số** từ bean type phù hợp, rồi truyền vào constructor `WelcomeService`. Phương thức `welcomeService` **không tự gọi** `messageRepository()` và không hard-code phụ thuộc trong service.
5. `getBean(WelcomeService.class)` tra cứu bean đã được quản lý; việc gọi `greet("Lan")` sau đó là phương thức Java bình thường trên instance nhận được.
6. `containsBean("welcomeService")` xác minh bean name tồn tại trong context hiện tại.
7. `try-with-resources` đóng context khi rời khối. Một số bean có lifecycle callback được container gọi khi context đóng; **đối tượng Java nói chung không tự biến mất hoặc được GC ngay khi close**.

**Đặt chú ý vào chủ đề chính:** code dịch vụ không import Spring; chỉ class cấu hình và phần bootstrap biết `ApplicationContext`. Đây là một cách giữ business logic dễ kiểm thử ngay cả khi đổi cách cấu hình container.

## 7. Không phải mọi object đều là bean; scope và lifecycle có giới hạn

**Scope `singleton`** là scope mặc định của Spring: một bean definition thường tương ứng với **một instance được chia sẻ trong mỗi container**. Đó **không phải** cam kết chỉ có một object trên toàn JVM hay trên nhiều application contexts.

**Scope `prototype`** thông thường tạo một instance mới mỗi khi container được yêu cầu cấp bean đó. Spring tạo/cấu hình và gọi initialization callbacks phù hợp, nhưng **không tự quản lý toàn bộ destruction callbacks của prototype sau khi đã giao cho caller**. Với scope `request`, `session`... còn phải có context web phù hợp; không dùng được một cách mặc định trong console context ở ví dụ.

**Lifecycle theo ngữ cảnh**: Bean có thể tham gia các bước tạo → inject → khởi tạo → được dùng → kết thúc. `ApplicationContext.close()` xử lý lifecycle cho những bean thuộc phạm vi quản lý phù hợp (đặc biệt singleton), chứ không phải lệnh đóng mọi đối tượng do code từng tạo ra.

**Không nhầm ba khái niệm:**

| Tình huống | Ai tạo/quản lý? | Hệ quả |
| --- | --- | --- |
| `context.getBean(WelcomeService.class)` | Spring Core Container | Truy cập bean đã đăng ký theo type |
| `new WelcomeService(repository)` trong code thường | Chính đoạn code đó | Object Java bình thường; không tự có DI/lifecycle của Spring |
| `new FixedMessageRepository()` bên trong method `@Bean` | Method tạo đối tượng, Spring đăng ký/ quản lý object **trả về** | Object trả về trở thành bean; không phải mọi object trung gian trong method đều thành bean |

Một bean có thể phụ thuộc vào bean khác và tạo thành **đồ thị phụ thuộc (dependency graph)**. Nếu thiếu bean phù hợp, có nhiều bean cùng type mà không có cách phân giải rõ, hoặc có vòng phụ thuộc constructor không giải được, bootstrap có thể thất bại thay vì tạo một graph sai.

## 8. Dùng Core Container khi nào, và khi nào cần module khác?

**Nên dùng Core Container khi:**

- Cần quản lý nhiều service/repository/client với các dependency rõ ràng.
- Muốn thay implementation trong test và tránh tạo dependency bằng `new` rải rác trong business code.
- Cần cấu hình đối tượng theo môi trường và có lifecycle/extension points ở mức ứng dụng.
- Xây dựng console/batch/service/web app có kiến trúc nhiều lớp.

**Chưa nhất thiết cần container** nếu chỉ viết một chương trình Java nhỏ, một vài hàm thuần và không có graph phụ thuộc đáng kể; việc tự tạo đối tượng có thể đơn giản và phù hợp hơn.

**Khi mục tiêu mở rộng:**

| Muốn làm gì? | Phần liên quan | Lưu ý |
| --- | --- | --- |
| Điều phối bean, DI, cấu hình | Core Container | Phạm vi chính của bài này |
| Xây dựng REST/MVC web | Spring Web/Spring MVC hoặc WebFlux | Phải thêm module/cấu hình tương ứng |
| SQL, giao dịch | Spring JDBC/`spring-tx`, tích hợp dữ liệu | DI cung cấp dependency, không tự thực hiện transaction |
| Proxy và cross-cutting advice | Spring AOP và cấu hình tương ứng | Spring không tự áp mọi method call thành advice |
| Auto-configuration, executable app | Spring Boot | Boot khai thác Core Container của Spring Framework |
| Kiểm thử integration bean graph | Spring Test | Có thể dựng context trong test, nhưng phải kiểm soát phạm vi và chi phí khởi tạo |

Spring Core Container là **nền móng cho nhiều chức năng**, không phải toàn bộ tính năng enterprise được bật mặc định.

## 9. Hiểu sai thường gặp và cách tự kiểm tra

1. **“IoC = DI hoàn toàn.”** DI là một cách áp dụng nguyên tắc IoC. Ở mức học Spring, thường thấy IoC được thực hiện qua DI và quản lý đối tượng của container.
2. **“Thêm `spring-core` là đã có đầy đủ `ApplicationContext`.”** Không. Container ở mức ứng dụng nằm trong `spring-context`; Maven sẽ quản lý dependency liên quan khi khai báo artifact đúng.
3. **“`@Component` trên một lớp là Spring tự quản lý nó ở mọi nơi.”** Chỉ khi lớp nằm trong nguồn quét/đăng ký của context thích hợp.
4. **“`@Bean` là annotation đặt lên class.”** Thông dụng nhất là `@Bean` trên **factory method** trong một cấu hình; `@Component` mới dùng trên class để scan.
5. **“DI bắt buộc dùng `@Autowired` ở field.”** Constructor injection hoặc factory-method parameter injection thường rõ ràng và dễ kiểm thử hơn; với đúng một constructor trên component được quản lý, Spring có thể tiêm mà không cần ghi `@Autowired`.
6. **“Singleton của Spring nghĩa là một instance cho mọi context.”** Mặc định là **một instance cho mỗi bean definition trong mỗi context**; tạo thêm context khác có thể có object khác.
7. **“Có `ApplicationContext` thì web server tự chạy.”** Sai. Ví dụ console ở trên không mở cổng HTTP.
8. **“Container tự tạo bean ngay cả khi cấu hình sai.”** Thiếu dependency, mơ hồ giữa nhiều candidate hoặc graph không giải được có thể khiến startup thất bại.
9. **“Gọi `close()` sẽ phá hủy tất cả mọi object Java.”** Sai. Context gọi các callback lifecycle phù hợp; Java GC và lifetime của reference có cơ chế riêng.
10. **“Spring Boot và Spring Framework là một.”** Boot dùng Framework, cung cấp thêm bootstrap, auto-configuration và tiện ích phát triển; nắm Core Container giúp hiểu Boot rõ hơn.

### Bài tập kiểm chứng

- **Bài A – đổi implementation:** thêm `AnotherMessageRepository` và đổi return trong factory method `messageRepository()`. Dự đoán lại duy nhất dòng `message=...` trước khi chạy.
- **Bài B – scope:** dùng `@Scope("prototype")` cho bean `welcomeService`, lấy bean hai lần rồi kiểm tra `==`. Dự đoán vì sao `sameSingleton` trở thành `false` (nên đổi nhãn in thành `sameInstance` cho đúng nghĩa).
- **Bài C – thiếu dependency:** tạm bỏ factory method `messageRepository()` rồi chạy lại. Kiểm tra kiểu exception khi context không resolve được tham số `MessageRepository`. Không chép nguyên một thông điệp exception, vì nó có thể thay đổi theo phiên bản.
- **Bài D – tách cấu hình:** chuyển `AppConfig` thành file riêng, giữ `WelcomeService` thuần Java và xác minh output không đổi.
- **Bài E – compare:** tạo `WelcomeService` thủ công bằng `new` và đặt cạnh phiên bản dùng context. Chỉ ra chỗ dependency được chọn, ai sở hữu lifecycle và khi nào nên dùng mỗi cách.

Mỗi bài tập là **một thay đổi độc lập**, cần khôi phục mã gốc để chạy lại stdout chuẩn ở mục 6.

## 10. Tóm tắt ghi nhớ và tài liệu chính thức

- Core Container là **tầng nền của Spring Framework**, không phải tên đồng nghĩa với Spring Boot hoặc Spring MVC.
- Vai trò trung tâm: **quản lý bean và các dependency** theo cấu hình, cung cấp IoC/DI và lifecycle thích hợp.
- `BeanFactory` là API nền, `ApplicationContext` mở rộng để phục vụ ứng dụng; thực tế thường bắt đầu với `ApplicationContext`.
- Các module quan trọng: `spring-core`, `spring-beans`, `spring-context`, `spring-expression`; `spring-context-support` bổ sung tích hợp khi cần.
- Một chương trình **không dùng HTTP** vẫn có thể tạo context. Điều quan trọng là graph đối tượng được lắp ráp/đưa vào sử dụng đúng theo hợp đồng.

Tài liệu để đối chiếu các API và hành vi theo phiên bản:

- [Spring Framework Overview](https://docs.spring.io/spring-framework/reference/overview.html)
- [Spring IoC Container and Beans](https://docs.spring.io/spring-framework/reference/core/beans/introduction.html)
- [Container Overview](https://docs.spring.io/spring-framework/reference/core/beans/basics.html)
- [Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)

**Kết luận:** Core Container là nơi Spring **tổ chức và nối các đối tượng ứng dụng lại với nhau**. Hiểu vị trí, trách nhiệm và giới hạn của container sẽ giúp học tiếp cấu hình bean, component scanning, injection, scope/lifecycle, AOP, giao dịch và Spring Boot mà không nhầm lẫn giữa các tầng.
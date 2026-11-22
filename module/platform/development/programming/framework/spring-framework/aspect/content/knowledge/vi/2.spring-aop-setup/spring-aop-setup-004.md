# Vai trò @Configuration, component scan và đăng ký bean khi thiết lập Spring AOP

## 1. Mục tiêu bài học

Trong Spring Framework, viết một lớp có **@Aspect** mới chỉ khai báo logic can thiệp. Để advice thực sự chạy khi ứng dụng gọi phương thức của một service, **ApplicationContext** phải biết cả **service bean**, **aspect bean** và phải có **hạ tầng tạo Spring AOP proxy**. Bài này tập trung vào ba thao tác cấu hình liên kết các phần đó:

1. Dùng **@Configuration** để cung cấp cấu hình Java cho container và đặt **@EnableAspectJAutoProxy**.
2. Dùng **@ComponentScan** để tự phát hiện các lớp Spring component như **@Service**, **@Component**.
3. Dùng **@Bean** để đăng ký tường minh service, aspect và client khi không muốn dùng component scanning.

Kết quả cần đạt: giải thích được **vì sao một aspect đã viết đúng vẫn không chạy nếu chưa đăng ký bean**, phân biệt việc **đưa bean vào context** với việc **bean có được bọc proxy hay không**, và biết kiểm tra bean thực tế mà client nhận từ Spring.

**Phạm vi:** Ví dụ dùng **Spring AOP dạng proxy trong ApplicationContext**; không đi sâu vào lý thuyết AOP tổng quát, AspectJ compile-time/load-time weaving hay các framework AOP khác. Tên gọi **@AspectJ** trong tài liệu Spring chỉ kiểu khai báo aspect qua annotation; Spring vẫn tạo proxy theo cơ chế của Spring AOP.

## 2. Bức tranh cấu hình: ba điều kiện cần

Hãy tưởng tượng ứng dụng có **PaymentService** và muốn ghi dấu vết trước khi xử lý thanh toán. Ba điều kiện không thể thay thế lẫn nhau:

| Thành phần | Nhiệm vụ trong Spring | Nếu thiếu |
| --- | --- | --- |
| **Cấu hình ApplicationContext** | Nạp lớp cấu hình, kích hoạt hỗ trợ **@AspectJ** bằng **@EnableAspectJAutoProxy** | Aspect có thể là bean nhưng không có hạ tầng tự tạo proxy cho advice của nó |
| **Đăng ký PaymentService** | Tạo bean target mà client có thể lấy/inject từ container | Không có Spring-managed service để Spring đưa qua auto-proxying |
| **Đăng ký AuditAspect** | Cho Spring biết bean chứa **@Aspect** và advice | Hạ tầng AOP không tìm thấy aspect để xây dựng advisor tương ứng |

Một service đã được đăng ký **không mặc nhiên luôn là proxy**. Spring xét các advisor có thể áp dụng cho bean và có thể trả về proxy nếu bean đủ điều kiện. Với lời gọi tới phương thức phù hợp, luồng chạy là:

~~~text
ApplicationContext
  |
  +-- PaymentServiceImpl (@Service) --------------------+
  |                                                    |
  +-- AuditAspect (@Aspect + @Component) -- advice -----+-- Spring auto-proxy creator
  |                                                            |
  +-- PaymentClient (@Component)                                |
          |                                                     |
          +-- inject PaymentService <--- proxy <----------------+
                                             |
PaymentClient.checkout() --> proxy --> advice --> PaymentServiceImpl.pay()
~~~

Các annotation **@Service** và **@Component** phục vụ phát hiện/đăng ký bean; **@Aspect** phục vụ khai báo aspect; **@EnableAspectJAutoProxy** kích hoạt cơ chế Spring đọc khai báo đó và xây dựng proxy. Đây là các trách nhiệm khác nhau.

## 3. Dự án thực hành Spring Framework thuần

Ta dùng **Java 17+**, **Maven 3.9+**, **Spring Framework 6.2.12**. Không cần Spring Boot, HTTP server hay cơ sở dữ liệu. Ví dụ được tổ chức sao cho từng class có thể biên dịch cùng nhau.

~~~text
spring-aop-config-demo/
├── pom.xml
└── src/main/java/example/
    ├── App.java
    ├── AppConfig.java
    ├── PaymentService.java
    ├── PaymentServiceImpl.java
    ├── AuditAspect.java
    └── PaymentClient.java
~~~

**pom.xml**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aop-config-demo</artifactId>
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
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
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
                    <mainClass>example.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**spring-context** cung cấp container cấu hình annotation và kéo theo những module Spring cần thiết, bao gồm **spring-aop**. **aspectjweaver** cần có trong classpath để Spring xử lý các annotation và biểu thức pointcut kiểu **@AspectJ**. Điều này **không có nghĩa** ví dụ đang dùng AspectJ weaving: các lời gọi vẫn được Spring AOP chặn qua proxy.

### 3.1. Định nghĩa hợp đồng service

**src/main/java/example/PaymentService.java**

~~~java
package example;

public interface PaymentService {
    String pay(String orderId);
}
~~~

### 3.2. Khai báo service bằng @Service

**src/main/java/example/PaymentServiceImpl.java**

~~~java
package example;

import org.springframework.stereotype.Service;

@Service
public class PaymentServiceImpl implements PaymentService {

    @Override
    public String pay(String orderId) {
        System.out.println("SERVICE pay " + orderId);
        return "ok:" + orderId;
    }
}
~~~

**@Service** là một stereotype annotation của Spring và là một dạng chuyên biệt của **@Component**. Khi package chứa lớp được quét, container sẽ đăng ký một **bean definition** cho **PaymentServiceImpl**. Với quy tắc đặt tên mặc định, bean có tên **paymentServiceImpl**.

Lưu ý: JVM không tự tạo Spring bean chỉ vì lớp mang **@Service**. Phải có một cơ chế đăng ký nó vào container: component scan, phương thức **@Bean**, hoặc đăng ký bằng API của context.

### 3.3. Khai báo aspect thành một Spring bean

**src/main/java/example/AuditAspect.java**

~~~java
package example;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {

    @Before("execution(* example.PaymentServiceImpl.pay(..))")
    public void beforePay(JoinPoint joinPoint) {
        Object orderId = joinPoint.getArgs()[0];
        System.out.println("ASPECT before " + orderId);
    }
}
~~~

Hai annotation có nhiệm vụ độc lập:

- **@Aspect**: Spring nhận ra lớp là nơi định nghĩa advice và biểu thức chọn phương thức; ở đây **@Before** áp dụng cho **PaymentServiceImpl.pay(...)**.
- **@Component**: đưa **AuditAspect** vào danh sách ứng viên cho component scanning, từ đó tạo bean **auditAspect** trong context.

Nếu chỉ còn **@Aspect** mà bỏ **@Component**, component scanner thông thường không tự coi lớp đó là component. Khi ấy **@EnableAspectJAutoProxy** vẫn có thể đã bật, nhưng aspect này không được đăng ký nên không tham gia can thiệp.

Aspect phải được **đăng ký như một Spring bean**: có thể dùng **@Component** hoặc một phương thức **@Bean**. Không cần thêm **@Service** lên lớp aspect. Ngoài ra, bản thân bean mang **@Aspect** không phải đối tượng mà Spring AOP dùng để advice bởi các aspect khác.

### 3.4. Tạo client nhận service từ container

**src/main/java/example/PaymentClient.java**

~~~java
package example;

import org.springframework.stereotype.Component;

@Component
public class PaymentClient {

    private final PaymentService paymentService;

    public PaymentClient(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public void checkout(String orderId) {
        String result = paymentService.pay(orderId);
        System.out.println("CLIENT result " + result);
    }
}
~~~

Vì class có một constructor, Spring có thể thực hiện constructor injection mà không cần ghi **@Autowired**. Spring tìm **PaymentService** theo kiểu dữ liệu trong context; với ví dụ này chỉ có một bean phù hợp.

Từ góc nhìn **PaymentClient**, dependency là **PaymentService**. Nếu bean đủ điều kiện được Spring tạo AOP proxy, chính proxy ấy được inject vào client. Tự viết **new PaymentServiceImpl()** trong constructor của client sẽ bỏ qua quá trình đăng ký và proxy của Spring.

### 3.5. Vai trò của @Configuration, @ComponentScan và @EnableAspectJAutoProxy

**src/main/java/example/AppConfig.java**

~~~java
package example;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "example")
@EnableAspectJAutoProxy
public class AppConfig {
}
~~~

Đọc từng dòng:

**@Configuration** đánh dấu lớp là nguồn cấu hình Java của Spring. Trong ví dụ, **AppConfig** được truyền trực tiếp cho **AnnotationConfigApplicationContext**. Lớp cấu hình có thể chứa các phương thức **@Bean**, nhập cấu hình qua **@Import** hoặc khai báo cách scan và bật tính năng container. Chỉ có **@Configuration** không tự làm mọi lớp cùng package trở thành bean.

**@ComponentScan(basePackages = "example")** yêu cầu Spring tìm các component phù hợp dưới package **example** và các subpackage. Nhờ đó, Spring phát hiện **PaymentServiceImpl** nhờ **@Service**, **AuditAspect** và **PaymentClient** nhờ **@Component**. Nếu component nằm ở package ngoài phạm vi scan mà không được đăng ký theo cách khác, nó không nằm trong context.

**@EnableAspectJAutoProxy** đăng ký hạ tầng Spring AOP tự động xét các bean và các advisor khai báo qua **@AspectJ**, tạo proxy khi cần. Annotation này **không thay thế component scan** và **không tự tạo AuditAspect bean từ class chưa được đăng ký**.

Đây là **Spring Framework thuần** nên bật AOP một cách tường minh bằng annotation trên. Trong dự án Spring Boot có starter và auto-configuration phù hợp, phần bật proxy có thể được cung cấp tự động; cần kiểm tra cấu hình Boot thay vì mặc định rằng ví dụ thuần Spring và Boot hoàn toàn giống nhau.

### 3.6. Tạo ApplicationContext, kiểm tra bean và gọi service

**src/main/java/example/App.java**

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            System.out.println(
                    "HAS_SERVICE " + context.containsBean("paymentServiceImpl"));
            System.out.println(
                    "HAS_ASPECT " + context.containsBean("auditAspect"));

            PaymentService service = context.getBean(PaymentService.class);
            System.out.println("IS_PROXY " + AopUtils.isAopProxy(service));

            PaymentClient client = context.getBean(PaymentClient.class);
            client.checkout("ORD-7");
        }
    }
}
~~~

Chạy từ thư mục có **pom.xml**:

~~~bash
mvn -q clean compile exec:java
~~~

Đầu ra logic kỳ vọng, bỏ qua thông điệp của Maven và môi trường chạy:

~~~text
HAS_SERVICE true
HAS_ASPECT true
IS_PROXY true
ASPECT before ORD-7
SERVICE pay ORD-7
CLIENT result ok:ORD-7
~~~

Ý nghĩa của ba dòng đầu:

- **HAS_SERVICE true**: component scanning đã đăng ký service theo tên mặc định.
- **HAS_ASPECT true**: aspect cũng đã được đăng ký là bean; chỉ có **@Aspect** sẽ không bảo đảm điều này.
- **IS_PROXY true**: đối tượng **PaymentService** mà context trả về đã được Spring AOP bọc proxy. Việc có bean không tương đương việc có proxy; ví dụ đủ điều kiện vì có advice khớp **pay(...)**.

Ba dòng còn lại cho thấy client gọi qua proxy, advice **@Before** chạy trước phương thức đích, rồi service trả kết quả như bình thường.

## 4. Tại sao component scanning và @Configuration không tự động bật AOP?

Ba trường hợp rất dễ bị lẫn:

| Cấu hình thực tế | Service là bean? | Aspect là bean? | Có advice của AuditAspect chạy? |
| --- | --- | --- | --- |
| **@ComponentScan** nhưng không bật **@EnableAspectJAutoProxy** | Có | Có | Không, trong ví dụ Spring Framework thuần này |
| **@EnableAspectJAutoProxy** nhưng không scan và không khai báo bean nào | Không | Không | Không |
| **@Configuration + @ComponentScan + @EnableAspectJAutoProxy** như ví dụ | Có | Có | Có, với lời gọi khớp pointcut đi qua proxy |
| **@Configuration + @Bean** khai báo cả service và aspect, đồng thời bật AOP | Có | Có | Có, nếu advisor phù hợp |

**@Configuration** chỉ nói với Spring rằng lớp là một nguồn định nghĩa bean và cấu hình. **@ComponentScan** chỉ đăng ký những component phù hợp với vùng quét và bộ lọc. **@EnableAspectJAutoProxy** mới là phần nối hạ tầng advice/proxy vào Spring container. Không annotation nào trong ba annotation này có thể thay thế toàn bộ công việc của hai annotation còn lại.

Một chi tiết khác: **@Configuration** được xem là một component khi scanner quét tới nó, nhưng trong ví dụ chính ta nạp **AppConfig.class** trực tiếp vào context. Vì vậy việc nạp lớp cấu hình chính không phụ thuộc vào việc scanner tình cờ phát hiện lớp ấy.

## 5. Cách thay thế: đăng ký tất cả bean bằng @Bean

Component scan thuận tiện khi các lớp do dự án sở hữu có stereotype annotation. Với các class không thể sửa, muốn đặt tên bean chủ động hoặc cần xây dựng bean qua constructor/factory, có thể dùng **@Bean**.

**Thí nghiệm độc lập:** thay **toàn bộ nội dung** của **src/main/java/example/AppConfig.java** bằng phiên bản sau, thay vì thêm một lớp **@Configuration** mới vào package đang được scan. Nhờ vậy không vô tình đăng ký trùng service và aspect.

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy
public class AppConfig {

    @Bean
    public PaymentService paymentService() {
        return new PaymentServiceImpl();
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }

    @Bean
    public PaymentClient paymentClient(PaymentService paymentService) {
        return new PaymentClient(paymentService);
    }
}
~~~

Không còn **@ComponentScan**. **PaymentServiceImpl**, **AuditAspect** và **PaymentClient** vẫn có các annotation cũ trong file Java nhưng chỉ được container đăng ký vì các phương thức **@Bean**.

Những điểm cần nhận ra:

1. **@Bean public PaymentService paymentService()** đăng ký bean với tên mặc định **paymentService**, không phải **paymentServiceImpl**. Spring quản lý đối tượng được factory method trả về và vẫn có thể bọc nó bằng AOP proxy.
2. **@Bean public AuditAspect auditAspect()** đăng ký instance chứa khai báo **@Aspect**. Không bắt buộc class **AuditAspect** phải có **@Component** trong đường đăng ký bằng **@Bean**.
3. **paymentClient(PaymentService paymentService)** để Spring resolve tham số qua dependency injection. Client nhận bean **PaymentService** đã được container xử lý, không cần tự gọi factory method.
4. **@EnableAspectJAutoProxy** vẫn phải tồn tại trong cấu hình Spring Framework thuần. **@Bean** chỉ đăng ký đối tượng; nó không tự bật AOP.
5. Việc method **paymentService()** dùng **new PaymentServiceImpl()** là hợp lệ vì **new** xảy ra **bên trong phương thức factory @Bean** và đối tượng trả về được container quản lý. Ngược lại, **new PaymentServiceImpl()** ở mã client rồi dùng trực tiếp sẽ không tự được Spring proxy.

Để chạy lại **App.java**, đổi dòng kiểm tra tên bean từ:

~~~java
context.containsBean("paymentServiceImpl")
~~~

thành:

~~~java
context.containsBean("paymentService")
~~~

Chạy lại lệnh Maven ở mục 3.6; các dòng logic vẫn như cũ, bao gồm **IS_PROXY true**, **ASPECT before ORD-7**, **SERVICE pay ORD-7**. Nếu để nguyên câu kiểm tra tên cũ, **HAS_SERVICE** sẽ là **false** dù service thực sự đã được đăng ký dưới tên **paymentService**. Vì vậy phải phân biệt **kiểm tra đúng tên bean** với **kết luận có hay không có bean theo kiểu**.

Khôi phục **AppConfig.java** của mục 3.5 khi muốn quay lại phiên bản component scan ban đầu. Không nên đồng thời giữ cả hai con đường khai báo cùng một service/aspect nếu chưa có chủ đích quản lý nhiều bean.

## 6. Spring tạo proxy ở giai đoạn nào?

Trong ví dụ, luồng cấu hình có thể tách thành các bước để chẩn đoán:

~~~text
new AnnotationConfigApplicationContext(AppConfig.class)
          |
          v
Đọc AppConfig và các annotation cấu hình
          |
          +-- @ComponentScan -> bean definitions:
          |      paymentServiceImpl, auditAspect, paymentClient
          |
          +-- @EnableAspectJAutoProxy
          |      -> đăng ký hạ tầng auto-proxy creator
          |
          v
Tạo và khởi tạo các bean cần thiết
          |
          +-- tìm aspect bean, đọc @Before và pointcut
          +-- xác định advisor áp dụng cho PaymentServiceImpl
          +-- xử lý bean bằng AOP BeanPostProcessor
          |
          v
Expose PaymentService qua proxy cho các dependency/client
          |
          v
PaymentClient.checkout() -> PaymentService proxy
          -> AuditAspect.beforePay() -> PaymentServiceImpl.pay()
~~~

Sơ đồ mô tả quan hệ trách nhiệm, không biểu diễn đầy đủ mọi callback hoặc một thứ tự khởi tạo cố định cho tất cả bean. Nền tảng của auto-proxying là các thành phần **BeanPostProcessor** của Spring; chúng có thể thay đối tượng bean được expose bằng proxy sau khi bean trải qua quá trình khởi tạo thích hợp.

Có hai kết luận thực hành:

- **Bean definition** có nghĩa Spring biết cách tạo/quản lý bean. Nó chưa đủ để suy ra client nhận proxy.
- **AOP proxy** là lớp trung gian mà Spring có thể cung cấp cho client nếu có advisor phù hợp và hạ tầng AOP hoạt động. Advisor quyết định liệu lời gọi tới một method có đi qua advice hay không.

Trong ví dụ này, vì **PaymentServiceImpl** triển khai **PaymentService**, cấu hình Spring Framework thuần mặc định có thể dùng **JDK dynamic proxy** theo interface. Client nên inject theo **PaymentService**, như đoạn mã trên. Muốn ép proxy dựa trên class có thể dùng **@EnableAspectJAutoProxy(proxyTargetClass = true)**; điều đó thay đổi kiểu proxy, không thay thế việc đăng ký bean. Các cấu hình proxy khác trong cùng context hoặc cấu hình Spring Boot cũng có thể ảnh hưởng loại proxy thực tế.

## 7. Phân biệt @Configuration enhancement với Spring AOP proxy

Một nguồn gây hiểu nhầm là **@Configuration** cũng có hành vi liên quan đến proxy/subclass. Trong cấu hình đầy đủ mặc định **@Configuration(proxyBeanMethods = true)**, Spring có thể tăng cường lớp cấu hình bằng CGLIB để các lời gọi giữa phương thức **@Bean** tuân theo ngữ nghĩa singleton của container. Đây là **cơ chế hỗ trợ cấu hình bean**, khác với AOP proxy dùng để chặn **PaymentService.pay(...)**.

Ví dụ hai phương thức factory:

~~~java
@Configuration
public class ExtraConfig {
    @Bean
    public SharedStore sharedStore() {
        return new SharedStore();
    }

    @Bean
    public ReportService reportService() {
        return new ReportService(sharedStore());
    }
}
~~~

Đây là **mã minh họa**, giả sử đã có hai lớp **SharedStore** và **ReportService** tương ứng; không phải file bắt buộc của dự án chạy ở trên. Với **@Configuration** mặc định, Spring bảo đảm việc tham chiếu bean theo phương thức cấu hình nhất quán với bean được quản lý. Nếu chuyển thành **@Configuration(proxyBeanMethods = false)**, việc trực tiếp gọi **sharedStore()** từ phương thức khác có thể tạo instance Java mới ngoài ngữ nghĩa gọi bean qua container. Khi đó nên dùng tham số dependency injection:

~~~java
@Bean
public ReportService reportService(SharedStore sharedStore) {
    return new ReportService(sharedStore);
}
~~~

Hai đoạn code này nhằm làm rõ **@Configuration và @Bean**; chúng không làm thay đổi pointcut hoặc behavior AOP của **PaymentService** ở ví dụ chính. Không suy luận rằng vì **AppConfig** đã có CGLIB enhancement thì service chắc chắn được tạo Spring AOP proxy.

## 8. Chẩn đoán bằng những thí nghiệm nhỏ

### 8.1. Aspect có @Aspect nhưng không được đăng ký

Trong phiên bản **component scan** ở mục 3.5, bỏ **@Component** khỏi **AuditAspect** và giữ **@Aspect**. Sau đó tạo mới ApplicationContext bằng cách chạy lại ứng dụng. Kỳ vọng:

~~~text
HAS_SERVICE true
HAS_ASPECT false
IS_PROXY false
SERVICE pay ORD-7
CLIENT result ok:ORD-7
~~~

Kết quả này áp dụng cho ví dụ chưa có advisor khác. Nếu ứng dụng thật có thêm advisor khác, bean có thể vẫn là proxy dù **AuditAspect** hiện tại không được đăng ký.

Cách sửa: khôi phục **@Component**, hoặc đăng ký bean aspect qua **@Bean** như mục 5; đồng thời xác minh package scan.

### 8.2. Aspect đã được scan nhưng AOP chưa bật

Ở phiên bản component scan, bỏ **@EnableAspectJAutoProxy** khỏi **AppConfig**, giữ **@ComponentScan** và **@Component** trên aspect. Khi chạy lại:

~~~text
HAS_SERVICE true
HAS_ASPECT true
IS_PROXY false
SERVICE pay ORD-7
CLIENT result ok:ORD-7
~~~

Trong Spring Framework thuần ở đây, thiếu hạ tầng AOP làm advice không được cài vào proxy; **@Aspect** tự nó không khiến advice chạy.

### 8.3. Service nằm ngoài vùng scan

Nếu chuyển **PaymentServiceImpl** sang package khác nhưng giữ **@ComponentScan(basePackages = "example")** và không đăng ký nó bằng cách khác, bean **PaymentService** không được phát hiện. Khi Spring tạo **PaymentClient**, dependency **PaymentService** không thể được giải quyết; context thường lỗi khi khởi tạo thay vì chạy tới dòng **HAS_SERVICE**. Cần mở rộng vùng scan đúng phạm vi hoặc khai báo service bằng **@Bean**.

Đừng mở scan tùy tiện sang toàn bộ ứng dụng lớn chỉ để sửa một lớp bị thiếu; kiểm tra package thực và cấu trúc module trước.

### 8.4. Tự tạo service ngoài ApplicationContext

Thay cho lời gọi đến Spring bean, mã bên ngoài tự tạo:

~~~java
PaymentService direct = new PaymentServiceImpl();
System.out.println("DIRECT " + direct.pay("ORD-8"));
~~~

Đầu ra của phần bổ sung này:

~~~text
SERVICE pay ORD-8
DIRECT ok:ORD-8
~~~

Không có log **ASPECT before** vì instance **direct** không phải bean được Spring xử lý. So sánh với cách gọi **context.getBean(PaymentService.class)** hoặc injection vào **PaymentClient**.

### 8.5. Client lấy service đúng nhưng gọi nội bộ không qua proxy

Nếu trong **PaymentServiceImpl** có một phương thức tự gọi **this.pay(...)**, lời gọi nội bộ đó không quay lại proxy của Spring. Đây là giới hạn của Spring AOP dựa trên proxy, không phải lỗi component scanning hay mất đăng ký bean.

Nếu cần advice cho thao tác nội bộ, một thiết kế dễ kiểm soát là tách phần thao tác sang Spring bean khác rồi inject/gọi qua dependency của container.

## 9. Lỗi cấu hình phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| Aspect không chạy dù lớp có **@Aspect** | Chưa tạo aspect bean hoặc thiếu **@EnableAspectJAutoProxy** | Kiểm tra **containsBean**, cấu hình context và dependency AspectJ |
| Không inject được service | Package chưa scan, thiếu **@Service**, hoặc chưa có **@Bean** | Kiểm tra package, bean names và bean definitions |
| **NoUniqueBeanDefinitionException** | Nhiều bean cùng thỏa mãn kiểu cần inject | Xác định bean đúng, dùng **@Qualifier** hoặc **@Primary** khi phù hợp |
| Lấy bean bằng implementation class thất bại | JDK proxy chỉ triển khai service interface | Inject/lấy bean theo **PaymentService** |
| Aspect có bean nhưng phương thức không được chặn | Pointcut không khớp hoặc lời gọi bỏ qua proxy | So khớp tên package/class/method; quan sát đường đi lời gọi |
| Có proxy nhưng không có log của aspect mong muốn | Proxy có thể do advisor khác tạo ra | Kiểm tra đúng aspect bean và pointcut, không chỉ **AopUtils.isAopProxy** |
| Chạy code từ **new** mà không có advice | Instance không được tạo và expose qua Spring container | Lấy/inject bean từ context |
| Bị đăng ký trùng service hoặc aspect | Đồng thời khai báo cả scan và **@Bean** cho cùng logic | Chọn một đường đăng ký hoặc quản lý rõ nhiều bean |
| Dùng nhiều ApplicationContext, advice chỉ chạy ở một nơi | AOP configuration gắn với context chứa bean liên quan | Xác định config và service nằm ở context nào |
| Lỗi lúc phân tích **@Aspect**/pointcut | Thiếu **aspectjweaver** hoặc dependency không tương thích | Kiểm tra Maven dependency tree và phiên bản Spring đang chạy |

Với các ứng dụng dùng nhiều advice, cần chú ý độ ưu tiên và thứ tự áp dụng; **@Order** có thể dùng khi thứ tự là yêu cầu cụ thể. Điều đó là cấu hình advice sau khi đã giải quyết đúng việc đăng ký bean và tạo proxy.

## 10. Các câu hỏi tự kiểm tra

**Câu 1. Có @Configuration và @ComponentScan, tại sao @Before không chạy?**

Vì hai annotation này cho phép Spring nạp cấu hình và đăng ký component, nhưng trong ví dụ Spring Framework thuần cần thêm **@EnableAspectJAutoProxy** để xử lý **@Aspect** và tạo proxy theo advisor.

**Câu 2. AuditAspect chỉ có @Aspect, có được component scan tự phát hiện như một bean không?**

Không. Phải đồng thời có **@Component** (hoặc stereotype Spring đủ điều kiện scan) hoặc dùng cách đăng ký tường minh như **@Bean**.

**Câu 3. Có bắt buộc mọi Spring AOP aspect phải đăng ký bằng component scan không?**

Không. Một **@Bean** method trả về **AuditAspect** cũng cho container một aspect bean để hạ tầng AOP sử dụng.

**Câu 4. Tại sao trong @Bean được phép new PaymentServiceImpl() nhưng new ở client lại bỏ qua AOP?**

**@Bean** trả instance cho container quản lý, container có thể đưa instance đó qua bước auto-proxy rồi expose bean cho client. Instance new trực tiếp ở client không qua pipeline đó.

**Câu 5. Sự khác biệt giữa bean và proxy là gì trong ví dụ?**

Bean là đối tượng mà Spring quản lý; proxy là đối tượng trung gian có thể được Spring expose cho client để áp dụng advice. Bean được đăng ký không tự bảo đảm rằng mỗi method của nó đều bị advice.

**Câu 6. Tại sao có tên paymentService ở cấu hình @Bean, còn ở component scan là paymentServiceImpl?**

Mặc định bean từ **@Bean** lấy tên theo phương thức factory; bean từ component scan thường lấy tên lớp theo quy tắc naming của Spring. Tên khác không nhất thiết có nghĩa là loại service khác.

**Câu 7. Bằng chứng nào đủ tốt cho việc setup thành công?**

Cần quan sát ít nhất: bean service có trong context, aspect bean có trong context, service do context trả về là AOP proxy khi phù hợp, và **@Before** thực sự chạy trong lời gọi service qua dependency của Spring.

## 11. Checklist áp dụng cho một module Spring AOP

1. Xác định service cần can thiệp là bean trong **ApplicationContext** nào.
2. Chọn một đường đăng ký phù hợp: **@Service + @ComponentScan** hoặc **@Bean**.
3. Bảo đảm class **@Aspect** cũng được đăng ký thành bean, không chỉ gắn annotation.
4. Bật hỗ trợ auto-proxy trong context tương ứng (**@EnableAspectJAutoProxy** với ví dụ Framework thuần).
5. Kiểm tra biểu thức pointcut khớp method của target.
6. Inject service từ container theo interface khi dùng JDK proxy.
7. Kiểm tra hành vi qua lời gọi thực tế; xác nhận các giới hạn như self-invocation.

## 12. Tài liệu Spring đối chiếu

- Spring Framework Reference — Java-based Container Configuration: https://docs.spring.io/spring-framework/reference/core/beans/java.html
- Spring Framework Reference — @Bean: https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html
- Spring Framework Reference — @Configuration: https://docs.spring.io/spring-framework/reference/core/beans/java/configuration-annotation.html
- Spring Framework Reference — @AspectJ support và enabling auto-proxy: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Kết luận kỹ thuật:** trong Spring AOP, **@Configuration** nạp cấu hình, **@ComponentScan/@Bean** làm cho service và aspect trở thành Spring-managed beans, còn **@EnableAspectJAutoProxy** cho phép Spring tạo proxy và áp dụng advice theo pointcut. Ba trách nhiệm kết hợp mới làm ví dụ can thiệp lời gọi service hoạt động.

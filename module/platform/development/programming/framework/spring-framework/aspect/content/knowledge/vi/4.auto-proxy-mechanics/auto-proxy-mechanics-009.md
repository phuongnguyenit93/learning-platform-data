# Phụ thuộc vòng và nguy cơ tham chiếu sớm chưa được tăng cường trong Spring AOP

## 1. Vấn đề cần hiểu

Spring AOP thường tạo một **proxy** để client gọi method của Spring bean qua advice trước hoặc sau khi vào đối tượng đích (**target**). Khi các bean có **phụ thuộc vòng** (circular dependency), Spring có thể bị yêu cầu đưa một bean cho đối tượng khác **trước khi bean ấy hoàn tất vòng đời khởi tạo**. Đối với một bean có thể được Spring AOP bọc proxy, đây là thời điểm nhạy cảm: client có thể cần **proxy** nhưng container mới tạo xong **target thô (raw target)**.

Ba câu hỏi trung tâm:

1. Trong chu trình Spring tạo bean, **tham chiếu sớm (early reference)** xuất hiện khi nào?
2. Spring AOP phối hợp với cơ chế đó ra sao để tránh việc một nơi giữ raw target còn nơi khác giữ proxy?
3. Tại sao cách sửa đáng tin cậy nhất là **loại bỏ phụ thuộc vòng**, thay vì cố cho phép tiêm một bean chưa hoàn tất khởi tạo?

**Phạm vi:** Bài chỉ phân tích các trường hợp liên quan **Spring Framework, Spring bean lifecycle và Spring AOP auto-proxy**; không mở rộng sang lý thuyết AOP độc lập, compile-time weaving hoặc các framework IoC khác.

## 2. Hai vấn đề dễ bị trộn lẫn

Có ít nhất hai loại sự cố khác nhau.

### 2.1. Vòng phụ thuộc khiến Spring không tạo nổi bean

Ví dụ:

~~~text
PaymentService
    |
    | constructor cần AuditService
    v
AuditService
    |
    | constructor cần PaymentService
    +---------------------------> PaymentService
~~~

Nếu cả hai constructor yêu cầu instance đã tồn tại, Spring không thể hoàn thành đối tượng nào trước. Với vòng phụ thuộc constructor như trên, container có thể ném **BeanCurrentlyInCreationException** (thường nằm trong chuỗi nguyên nhân của BeanCreationException hoặc UnsatisfiedDependencyException).

Spring AOP không phải công cụ phá vòng constructor. Việc cấu hình **@EnableAspectJAutoProxy** không làm cho loại vòng này tự biến mất.

### 2.2. Vòng phụ thuộc có tham chiếu sớm nhưng tham chiếu khác proxy cuối cùng

Một vòng phụ thuộc dựa trên property/setter injection giữa **singleton beans** đôi khi có thể được Spring giải quyết bằng cách đưa ra một **early singleton reference** sau khi đối tượng được cấp phát, trước khi toàn bộ dependency, initialization callback và BeanPostProcessor hoàn tất.

Nhưng nếu Bean A sau cùng phải được bọc thành Spring AOP proxy:

~~~text
A raw target --------------------------> A final proxy
      |                                        ^
      | tham chiếu sớm                          |
      v                                        |
B giữ tham chiếu tới A raw          Client khác nhận A proxy
~~~

Khi B gọi trực tiếp A raw, đường gọi có thể **bỏ qua advice**. Chúng ta có hai tham chiếu không tương đương về hành vi. Đây là nguy cơ **raw bean injected despite wrapping**.

Quan trọng: **không phải mọi circular dependency đều gây tiêm raw target**. Hạ tầng Spring AOP chuẩn có hook để cung cấp **early proxy** nếu có thể. Nguy cơ xuất hiện khi không thể bảo đảm tham chiếu sớm chính là wrapper sẽ được expose cuối cùng, hoặc bean bị tạo quá sớm nên không được áp dụng đủ BeanPostProcessor.

## 3. Ôn đúng những bước cần thiết của Spring bean lifecycle

Đối với một singleton bean điển hình, có thể hình dung:

~~~text
Đăng ký BeanDefinition
        |
        v
Tạo instance / gọi constructor
        |
        v
Populate properties / tiêm dependency
        |
        v
Initialization (@PostConstruct, InitializingBean, init method...)
        |
        v
BeanPostProcessor, gồm hạ tầng Spring AOP auto-proxy
        |
        v
Expose bean cuối cùng (có thể là proxy)
~~~

Thứ tự chi tiết có nhiều hook, nên sơ đồ cố ý giản lược. Việc tạo proxy của Spring AOP được thực hiện qua **BeanPostProcessor**; với auto-proxy creator tiêu biểu, bean có thể được bọc ở bước xử lý sau initialization. Trong một vòng singleton phù hợp, Spring có thêm con đường cung cấp **early singleton reference** giữa giai đoạn tạo instance và hoàn tất khởi tạo.

Vì vậy:

- **Raw bean:** instance target được tạo bằng constructor; chưa thể mặc định coi là object đã qua AOP.
- **Early reference:** tham chiếu được container xuất ra khi một singleton đang được tạo và bean khác cần nó; giá trị có thể là raw object hoặc wrapper/proxy do post-processor cấp.
- **Final exposed bean:** tham chiếu người dùng bình thường nhận từ `ApplicationContext.getBean(...)` sau khi khởi tạo thành công.
- **AOP proxy:** wrapper có thể thực thi interceptor/advice cho các method phù hợp khi client gọi qua nó.

Một bean đã được cấp phát không có nghĩa bean đó đã có đầy đủ dependency, đã chạy initialization hoặc đã có AOP proxy. Tránh gọi logic nghiệp vụ trên một early reference chỉ vì biến tham chiếu đã khác `null`.

## 4. Vì sao Spring từng có thể giải quyết vòng qua setter?

Xét hai singleton:

~~~java
class Alpha {
    private Beta beta;

    void setBeta(Beta beta) {
        this.beta = beta;
    }
}

class Beta {
    private Alpha alpha;

    void setAlpha(Alpha alpha) {
        this.alpha = alpha;
    }
}
~~~

Đây là **fragment mô tả graph**, chưa có annotation đăng ký bean. Khi container được phép thử giải quyết vòng singleton, một chuỗi thực thi có thể là:

1. Bắt đầu tạo **Alpha**: constructor không cần Beta nên có instance raw.
2. Container ghi nhận Alpha đang được tạo và có thể cung cấp **singleton factory** cho yêu cầu tham chiếu sớm.
3. Trong lúc tiêm `beta`, Spring cần tạo **Beta**.
4. Khi tiêm `alpha` cho Beta, Spring phát hiện Alpha đang được tạo; nếu thỏa điều kiện, nó lấy **early reference của Alpha**.
5. Hoàn thành Beta và gán Beta cho Alpha.
6. Chạy initialization, BeanPostProcessor và quyết định tham chiếu Alpha cuối cùng.

Cơ chế này **không áp dụng được khi constructor Alpha cần Beta và constructor Beta cần Alpha**, vì ở điểm vòng quay lại chưa có instance nào được tạo hoàn chỉnh đến mức có thể đưa vào early singleton cache.

Một hệ quả: khả năng giải quyết vòng phụ thuộc phụ thuộc vào **loại dependency, bean scope, container settings và post-processors**; không nên đọc “Spring hỗ trợ circular references” thành bảo đảm mọi vòng đều tạo được bean.

## 5. Cơ chế ba tầng tham chiếu singleton, ở mức cần cho AOP

Trong triển khai Spring, quá trình giải quyết tham chiếu singleton có thể được hiểu bằng ba nhóm nơi lưu:

| Tầng / tên thường gặp trong triển khai | Chứa gì | Vai trò |
| --- | --- | --- |
| `singletonObjects` | Singleton đã được expose hoàn chỉnh | Đường lấy bean thông thường |
| `earlySingletonObjects` | Tham chiếu sớm đã được tạo | Tái sử dụng cùng early reference nếu có yêu cầu sau |
| `singletonFactories` | Factory có thể cung cấp early reference | Cho phép BeanPostProcessor tạo wrapper sớm khi cần |

Khi bean vẫn đang khởi tạo, Spring có thể đăng ký một factory. Nếu bean khác cần nó, factory được dùng để lấy early reference. Đối tượng nhận được từ factory **không bắt buộc là raw target**. Hạ tầng Spring AOP có thể tham gia để trả về proxy.

~~~text
                  Bean A đang khởi tạo
                           |
                    tạo raw target
                           |
                  singleton factory A
                           |
                  B cần dependency A
                           |
                           v
                 getEarlyBeanReference
                           |
             +-------------+-------------+
             |                           |
       early proxy                  raw target
     (nếu tạo được)             (nếu không được bọc)
             |                           |
             v                           v
        B giữ proxy                 B giữ raw target
             |                           |
             v                           v
   có thể nhất quán với            nguy cơ khác hành vi
   final exposed bean              so với final proxy
~~~

Đây là sơ đồ mô tả **khả năng**, không phải một lời hứa rằng mọi aspect đều được Spring xác định kịp thời để tạo early proxy. Vòng phụ thuộc có thể bị từ chối trước khi có early reference, hoặc phát sinh lỗi khi final proxy khác tham chiếu đã tiêm.

## 6. Hook quan trọng: getEarlyBeanReference(...)

Hạ tầng Spring định nghĩa callback của **SmartInstantiationAwareBeanPostProcessor**:

~~~java
Object getEarlyBeanReference(Object bean, String beanName)
~~~

Đây là **chữ ký API minh họa**, không phải một chương trình Java độc lập. Callback cho post-processor cơ hội cung cấp một wrapper trước khi target hoàn toàn initialized.

**AbstractAutoProxyCreator** của Spring AOP triển khai đường đi này. Về mặt ý tưởng:

~~~text
getEarlyBeanReference(rawA, "a")
      |
      +-- xác định bean cần proxy hay không
      |
      +-- nếu cần, có thể trả AOP proxy của rawA
      |
      +-- lưu trạng thái để tránh tạo một proxy khác
          không nhất quán ở cuối initialization
~~~

Sau đó, post-processor xử lý phần còn lại của lifecycle với thông tin rằng bean có thể đã được cấp early proxy. Mục tiêu là **early reference và final exposed reference tương thích**, không để B giữ target thô trong khi client khác nhận proxy khác hành vi.

Cần diễn đạt chính xác hai giới hạn:

- Callback này là cơ chế hỗ trợ **có điều kiện**. Nó **không** làm cho vòng constructor injection được giải quyết.
- `SmartInstantiationAwareBeanPostProcessor` có triển khai mặc định trả bean gốc; một custom post-processor hoặc một tình huống khởi tạo không phù hợp vẫn có thể để lại **raw reference**.

Không dựa vào việc “Spring tự bọc tất cả tham chiếu sớm” để thiết kế graph phụ thuộc vòng.

## 7. Khi raw target được tiêm nhưng final bean trở thành proxy

Giả sử A là service phải được Spring AOP proxy, còn B tham chiếu sớm tới A:

~~~text
B.a ----------------------------------> A raw target

context.getBean(AService.class) ------> A final proxy
                                           |
                                           v
                                        A raw target
~~~

Nếu B gọi `a.process()` qua raw target, advice của Spring AOP có thể không chạy. Các caller khác gọi qua `A final proxy` thì advice chạy. Hai đường gọi có khả năng sinh kết quả phụ trợ khác nhau (ví dụ thiếu audit hoặc tracing), ngay cả khi cùng đi tới nghiệp vụ của một target.

Để tránh trạng thái này, Spring theo mặc định **không cho phép raw injection bất chấp bean về sau bị wrapper**. Trong trường hợp phát hiện sự không nhất quán và có các dependent beans thực sự nhận raw instance, Spring có thể ném **BeanCurrentlyInCreationException** với mô tả theo ý nghĩa:

~~~text
Bean ... has been injected into other beans [...] in its raw version
as part of a circular reference, but has eventually been wrapped.
~~~

Thông báo trên là **trích đoạn dạng mẫu**, không phải expected stdout của một chương trình cụ thể. Chữ của thông báo thực tế phụ thuộc phiên bản Spring và đường tạo bean.

Trong API của `AbstractAutowireCapableBeanFactory` có hai lựa chọn khác nhau:

- **`setAllowCircularReferences(boolean)`**: container có thử xử lý một số vòng dependency hay không.
- **`setAllowRawInjectionDespiteWrapping(boolean)`**: cho phép chấp nhận raw instance đã được inject dù final bean về sau là wrapper hay không; mặc định **false**.

Bật raw injection despite wrapping để che lỗi là rủi ro vì khiến mã gọi có thể vượt qua AOP proxy. Đây không phải biện pháp sửa thiết kế đáng dùng cho service cần advice.

## 8. Chương trình chạy được: thiết kế không vòng, proxy nhất quán

Ta xây một ví dụ **Spring Framework 6.2.12, Java 17+, Maven 3.9+**. Client dùng `PaymentService`. Aspect ghi log qua một bean `AuditRecorder` độc lập; aspect **không inject ngược PaymentService**.

~~~text
spring-aop-early-reference/
├── pom.xml
└── src/main/java/demo/
    ├── PaymentService.java
    ├── PaymentServiceImpl.java
    ├── AuditRecorder.java
    ├── LoggingAspect.java
    ├── CheckoutClient.java
    ├── AppConfig.java
    ├── CycleProbe.java
    └── App.java
~~~

### 8.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-early-reference</artifactId>
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
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp ApplicationContext và mang theo Spring AOP cần dùng; `aspectjweaver` cung cấp các kiểu pointcut/advice theo cú pháp `@AspectJ`. Cách thực hiện ở đây **vẫn là Spring AOP proxy**, không phải weaving class bằng AspectJ agent.

### 8.2. Service interface và implementation

**src/main/java/demo/PaymentService.java**

~~~java
package demo;

public interface PaymentService {
    String pay(String orderId);
}
~~~

**src/main/java/demo/PaymentServiceImpl.java**

~~~java
package demo;

public class PaymentServiceImpl implements PaymentService {

    @Override
    public String pay(String orderId) {
        System.out.println("SERVICE " + orderId);
        return "paid:" + orderId;
    }
}
~~~

Implementation không phụ thuộc vào aspect hoặc recorder. Vì service có interface, client lấy bean theo `PaymentService`; điều này phù hợp với JDK dynamic proxy mặc định của cấu hình Spring Framework thuần trong ví dụ.

### 8.3. Collaborator của aspect

**src/main/java/demo/AuditRecorder.java**

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

public class AuditRecorder {

    private final AtomicInteger count = new AtomicInteger();

    public void record(String orderId) {
        count.incrementAndGet();
        System.out.println("AUDIT " + orderId);
    }

    public int count() {
        return count.get();
    }
}
~~~

`AuditRecorder` độc lập, không inject `PaymentService`. Trường AtomicInteger giúp ví dụ không mắc lỗi tăng `int` không an toàn trong môi trường đồng thời. Đây chỉ là bộ đếm trong bộ nhớ; hệ thống thật cần giải pháp audit phù hợp và chính sách lỗi rõ ràng.

### 8.4. Aspect chỉ phụ thuộc một chiều vào recorder

**src/main/java/demo/LoggingAspect.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class LoggingAspect {

    private final AuditRecorder recorder;

    public LoggingAspect(AuditRecorder recorder) {
        this.recorder = recorder;
    }

    @Before("execution(* demo.PaymentServiceImpl.pay(..))")
    public void beforePay(JoinPoint joinPoint) {
        String orderId = (String) joinPoint.getArgs()[0];
        recorder.record(orderId);
    }
}
~~~

Lớp có **@Aspect** để Spring AOP đọc advice. Instance `LoggingAspect` sẽ được đăng ký bằng `@Bean`, nên không cần `@Component`. Aspect nhận `AuditRecorder` bằng constructor, **không** nhận service đang bị advice và không sinh graph phụ thuộc vòng.

### 8.5. Client chỉ nhận service từ Spring

**src/main/java/demo/CheckoutClient.java**

~~~java
package demo;

public class CheckoutClient {

    private final PaymentService paymentService;

    public CheckoutClient(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public void checkout(String orderId) {
        String result = paymentService.pay(orderId);
        System.out.println("CLIENT " + result);
    }
}
~~~

Client không dùng `new PaymentServiceImpl()`. Spring resolve `PaymentService` từ container và có thể inject **proxy** vào client.

### 8.6. Cấu hình bean rõ ràng, không vòng

**src/main/java/demo/AppConfig.java**

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy
public class AppConfig {

    @Bean
    public AuditRecorder auditRecorder() {
        return new AuditRecorder();
    }

    @Bean
    public LoggingAspect loggingAspect(AuditRecorder recorder) {
        return new LoggingAspect(recorder);
    }

    @Bean
    public PaymentService paymentService() {
        return new PaymentServiceImpl();
    }

    @Bean
    public CheckoutClient checkoutClient(PaymentService paymentService) {
        return new CheckoutClient(paymentService);
    }
}
~~~

Các phụ thuộc tạo thành một graph một chiều:

~~~text
CheckoutClient ---> PaymentService (proxy) ---> PaymentServiceImpl
LoggingAspect ----> AuditRecorder
                       ^
                       |
              advice gọi khi pay(...)
~~~

Về dependency injection, **LoggingAspect không phụ thuộc PaymentService**; điều kiện pointcut để can thiệp method service **không tương đương với dependency Java của aspect trên service**.

`@EnableAspectJAutoProxy` bật hạ tầng tự tạo proxy và xử lý aspect. `@Bean` đăng ký những instance vào Spring. `proxyBeanMethods = false` ở `@Configuration` chỉ kiểm soát interception của lời gọi giữa các `@Bean` factory methods; **không vô hiệu hóa Spring AOP proxy của PaymentService**.

### 8.7. Thí nghiệm vòng constructor bị từ chối

Ta tạo thêm một context **độc lập** chỉ để chứng minh constructor cycle không thể được cứu bởi early singleton reference. Nó không chứa `AppConfig` hoặc service/bean của kịch bản thành công, để tránh lẫn nguyên nhân lỗi.

**src/main/java/demo/CycleProbe.java**

~~~java
package demo;

import org.springframework.beans.BeansException;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class CycleProbe {

    private CycleProbe() {
    }

    static class A {
        A(B b) {
        }
    }

    static class B {
        B(A a) {
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CycleConfig {
        @Bean
        A a(B b) {
            return new A(b);
        }

        @Bean
        B b(A a) {
            return new B(a);
        }
    }

    public static void demonstrate() {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.setAllowCircularReferences(false);
            context.register(CycleConfig.class);

            try {
                context.refresh();
                System.out.println("CYCLE unexpectedly created");
            } catch (BeansException exception) {
                System.out.println("CYCLE rejected");
            }
        }
    }
}
~~~

`context.setAllowCircularReferences(false)` được gọi trước `refresh()` để phép thử nhất quán và loại bỏ mọi kỳ vọng rằng container sẽ thử resolve vòng. Ngay cả khi cho phép vòng, **constructor A(B) ↔ B(A)** không thể được hoàn thành bằng early reference thông thường.

Ta chỉ in câu cố định **CYCLE rejected** trong catch để tránh gắn bài học với thông điệp stack trace dài, có thể thay đổi giữa các bản Spring. Việc catch ở đây chỉ dùng cho **chương trình minh họa lỗi**, không phải cách ứng dụng production nên nuốt lỗi startup.

### 8.8. Chạy cả trường hợp bình thường và vòng lỗi

**src/main/java/demo/App.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            PaymentService service =
                    context.getBean(PaymentService.class);
            CheckoutClient client =
                    context.getBean(CheckoutClient.class);
            AuditRecorder recorder =
                    context.getBean(AuditRecorder.class);

            System.out.println(
                    "IS_PROXY " + AopUtils.isAopProxy(service));
            client.checkout("ORD-59");
            System.out.println("AUDIT_COUNT " + recorder.count());
        }

        CycleProbe.demonstrate();
    }
}
~~~

Trong thư mục chứa `pom.xml`, chạy:

~~~bash
mvn -q clean compile exec:java
~~~

**Các dòng logic do chính ví dụ in ra:**

~~~text
IS_PROXY true
AUDIT ORD-59
SERVICE ORD-59
CLIENT paid:ORD-59
AUDIT_COUNT 1
CYCLE rejected
~~~

Spring hoặc Maven có thể in cảnh báo/lỗi startup của context thử nghiệm lên stderr; những dòng đó không thuộc stdout logic liệt kê phía trên.

Ý nghĩa:

- **IS_PROXY true**: bean service thông thường từ context đã được Spring AOP expose dưới dạng proxy.
- **AUDIT** đứng trước **SERVICE**: advice `@Before` thực sự được gọi trước target.
- **AUDIT_COUNT 1**: recorder được Spring quản lý ghi chính xác một sự kiện.
- **CYCLE rejected**: context thứ hai gặp vòng phụ thuộc constructor và fail khi `refresh()`; lỗi được bắt có chủ đích để chương trình tiếp tục kết thúc bình thường.

Ví dụ không cố ép một vòng setter “thành công bằng mọi giá”. Mục đích là chỉ ra giải pháp có thể chứng minh **cùng một proxy đi qua advice** và **graph dependency không vòng**.

## 9. Một lỗi thiết kế AOP thường xuất hiện: aspect phụ thuộc vào chính service được advise

Xét cấu hình nguy hiểm sau, **chỉ là ví dụ phản diện**, không thêm trực tiếp vào project chạy ở mục 8:

~~~java
@Aspect
@Component
class TraceAspect {
    private final OrderService orderService;

    TraceAspect(OrderService orderService) {
        this.orderService = orderService;
    }

    @Before("execution(* example.OrderService.submit(..))")
    public void beforeSubmit() {
        // advice
    }
}

@Service
class OrderServiceImpl implements OrderService {
    private final TraceAspect traceAspect;

    OrderServiceImpl(TraceAspect traceAspect) {
        this.traceAspect = traceAspect;
    }

    public void submit() {
        // business logic
    }
}
~~~

Để biên dịch fragment trên cần thêm interface `OrderService`, import Spring/AspectJ và package tương ứng; đây **không phải ví dụ độc lập có thể chạy ngay**. Graph là:

~~~text
OrderServiceImpl -> TraceAspect -> OrderServiceImpl
~~~

Cả hai bên đều đòi dependency constructor. Khi Spring cố tạo proxy cho service, nó còn phải xét các advisor từ aspect, khiến thứ tự khởi tạo có thể trở nên khó chẩn đoán hơn. Nhưng nguyên nhân thiết kế cơ bản vẫn là **vòng phụ thuộc giữa các bean**.

**Không có quy tắc cấm tuyệt đối aspect inject service mà nó advise** trong mọi trường hợp. Tuy nhiên, cách đó dễ dẫn đến graph vòng hoặc tái nhập advice nếu aspect lại gọi method thuộc pointcut. Một cách rõ ràng hơn là để aspect phụ thuộc vào **AuditRecorder**, **EventPublisher** hoặc collaborator độc lập; service chỉ mang nghiệp vụ, không inject aspect.

## 10. Tham chiếu sớm đã là proxy thì còn nguy cơ gì?

Ngay cả khi một `AbstractAutoProxyCreator` có thể trả **early proxy**, vẫn phải hiểu những giới hạn sau:

1. **Target chưa hoàn tất initialization**. Proxy có thể trỏ tới object mà field/property hoặc init callback chưa hoàn thành. Nếu caller gọi method quá sớm, method có thể đọc trạng thái chưa sẵn sàng.
2. **Lựa chọn advisor có thể bị ảnh hưởng bởi bean đang được tạo**. Aspect hoặc dependency của auto-proxy creator cũng có vòng phụ thuộc, khiến việc xác định wrapper khó bảo đảm.
3. **Thứ tự BeanPostProcessor rất quan trọng**. Những custom BeanPostProcessor không biết xử lý early reference, hoặc tạo wrapper khác nhau ở đầu/cuối, có thể làm final object khác early object.
4. **Một số bean khởi tạo quá sớm để được auto-proxying đầy đủ**. Đặc biệt, các BeanPostProcessor và bean chúng trực tiếp phụ thuộc có thể được tạo trong giai đoạn container đang đăng ký post-processor. Log kiểu *not eligible for getting processed by all BeanPostProcessors* là dấu hiệu cần kiểm tra.
5. **Proxy vẫn chỉ intercept những method invocation đủ điều kiện**. Self-invocation trên target không qua proxy, bất kể proxy được tạo sớm hay muộn.

Vì vậy, câu “Spring xử lý được vòng setter” không đồng nghĩa “mọi advice của Spring AOP vẫn an toàn và toàn bộ dependency đã initialized”.

## 11. Cách sửa: phá vòng phụ thuộc tại thiết kế

### 11.1. Tách bean dùng chung độc lập

Graph lỗi:

~~~text
OrderService -> AuditService -> OrderService
~~~

Refactor thành:

~~~text
OrderService --> PaymentRepository
TraceAspect  --> AuditRecorder
OrderService <-- Spring AOP proxy/advice matching (không phải DI arrow)
~~~

Đây là giải pháp khuyến nghị. Đưa chức năng ghi audit vào `AuditRecorder` hay một event publisher độc lập, **không inject ngược OrderService** chỉ để biết mã đơn hoặc kết quả. Advice có thể lấy argument, signature và return value từ `JoinPoint`/các kiểu advice tương ứng mà không tạo dependency ngược vào service.

Khi cần tham khảo dữ liệu của một lần gọi, truyền chính dữ liệu đó từ tham số method/advice; không cần service bean tự tham chiếu lại vào aspect.

### 11.2. Dùng ObjectProvider khi thực sự cần lookup muộn

Spring có thể tiêm `ObjectProvider<T>` để **trì hoãn việc lấy bean**:

~~~java
class DeferredCaller {
    private final org.springframework.beans.factory.ObjectProvider<OrderService>
            serviceProvider;

    DeferredCaller(
            org.springframework.beans.factory.ObjectProvider<OrderService>
                    serviceProvider) {
        this.serviceProvider = serviceProvider;
    }

    void callLater() {
        OrderService service = serviceProvider.getObject();
        service.submit();
    }
}
~~~

Đây là fragment minh họa, cần định nghĩa đúng `OrderService.submit()` và đăng ký bean trong context. `ObjectProvider` làm dependency được resolve **lúc `getObject()`**, không phải lúc constructor nhận provider.

Đây **không phải thuốc chữa phụ thuộc vòng tự động**. Nếu gọi `getObject()` ngay trong constructor hoặc `@PostConstruct` khi graph chưa ổn định, lỗi vẫn có thể xảy ra. Nếu thật sự cần lookup muộn, phải có ranh giới lifecycle rõ ràng và lý do kiến trúc hợp lệ.

### 11.3. @Lazy có thể dời thời điểm, không thay được thiết kế

Khai báo minh họa:

~~~java
SomeClient(@Lazy OrderService orderService) {
    this.orderService = orderService;
}
~~~

Import `org.springframework.context.annotation.Lazy` khi dùng. Với dependency injection, `@Lazy` có thể tạo **lazy-resolution proxy** cho điểm tiêm và chỉ resolve target bean khi phương thức được sử dụng. Proxy trì hoãn resolve dependency này **không nhất thiết là Spring AOP proxy** thực thi advice.

Nếu phương thức được gọi quá sớm trong lúc vòng bean vẫn tồn tại, vấn đề quay lại. Dùng `@Lazy` chỉ sau khi hiểu rõ dependency cần được dùng ở giai đoạn nào; với graph AOP quan trọng, refactor loại vòng vẫn là hướng ưu tiên.

### 11.4. Không dùng cấu hình cho phép vòng làm giải pháp mặc định

Trong **Spring Framework thuần**, bean factory có thể được cấu hình để thử giải quyết circular references và mặc định của `AbstractAutowireCapableBeanFactory` cho `allowCircularReferences` là **true**. Trong **Spring Boot** các bản hiện đại, property `spring.main.allow-circular-references` mặc định **false**.

Việc cố bật property dưới đây trong Boot:

~~~properties
spring.main.allow-circular-references=true
~~~

không giải quyết được vòng constructor bất khả thi và không bảo đảm Spring AOP proxy nhất quán cho mọi trường hợp. Đây là cấu hình hỗ trợ tạm thời khi di chuyển hệ thống cũ, cần đánh giá, thử nghiệm và có kế hoạch loại bỏ vòng. Không chọn nó làm sửa lỗi đầu tiên.

Cũng không khuyến nghị bật `setAllowRawInjectionDespiteWrapping(true)` để buộc container chấp nhận tham chiếu raw; điều đó có thể khiến dependency ở một bean không chạy các advice mong đợi.

## 12. Cách điều tra khi ứng dụng khởi tạo lỗi

### Bước 1: Vẽ graph dependency từ chuỗi exception

Ví dụ log có thể xuất hiện nhiều tầng:

~~~text
UnsatisfiedDependencyException
  caused by BeanCurrentlyInCreationException
    "Requested bean is currently in creation ..."
~~~

Đọc **bean names** trong exception và tìm đường vòng: service → collaborator → aspect → service; hoặc service A → service B → service A. Đừng chỉ đọc class cuối cùng trong stack trace.

### Bước 2: Xác định vòng constructor hay vòng có khả năng tham chiếu sớm

- **Constructor ↔ constructor**: refactor, thường không thể resolve bằng cơ chế early reference.
- **Setter/property vòng singleton**: có thể tồn tại tham chiếu sớm, nhưng phải phân tích điều kiện container và auto-proxy creator.
- **Prototype hoặc scope đặc biệt**: không suy ra có khả năng resolve như singleton.
- **Aspect ↔ advised service**: kiểm tra graph DI và khả năng aspect gọi ngược vào service.

### Bước 3: Kiểm tra bean nào đáng lẽ được proxy

Khi context có thể khởi tạo, xác minh bean lấy qua context:

~~~java
Object service = context.getBean("paymentService");

boolean isProxy =
        org.springframework.aop.support.AopUtils.isAopProxy(service);
System.out.println("IS_PROXY " + isProxy);
~~~

Đây là fragment debug, chỉ chạy khi đã có biến `context` và bean tên `paymentService`. Không suy ra **mọi method** đều được chặn chỉ từ `isProxy == true`; phải thử invocation đúng pointcut.

### Bước 4: Tìm dấu hiệu raw injection hoặc khởi tạo quá sớm

Những chuỗi cần chú ý:

~~~text
Bean ... injected ... in its raw version
... but has eventually been wrapped

Bean ... is not eligible for getting processed
by all BeanPostProcessors
~~~

Đây là **mẫu thông điệp**, không phải dữ liệu log từ hệ thống đang chạy. Thông điệp raw injection gợi ý final wrapper khác tham chiếu đã cấp cho dependent bean. Thông điệp về BeanPostProcessor gợi ý có bean được tạo quá sớm nên không đi qua toàn bộ post-processing.

Đừng cố sửa bằng cách bỏ exception guard. Hãy xác định bean nào kéo theo việc khởi tạo sớm và thay đổi dependency graph hoặc cấu hình phase tạo bean.

### Bước 5: Kiểm tra lời gọi thực tế có đi qua proxy

Nếu context khởi tạo thành công nhưng advice không chạy:

- Kiểm tra method và signature có khớp pointcut hay không.
- Kiểm tra caller dùng Spring-managed proxy hay trực tiếp `new` target.
- Kiểm tra có self-invocation bằng `this.method()` trong target hay không.
- Nếu có custom wrapper/BeanPostProcessor, kiểm tra client đã giữ **final proxy** hay giữ raw/early object.
- Với JDK proxy, inject theo interface nếu triển khai interface; đừng ép kiểu proxy về class implementation tùy tiện.

## 13. Những lỗi thường gặp và tác động

| Triệu chứng | Nguyên nhân khả dĩ | Hành động |
| --- | --- | --- |
| Startup báo `BeanCurrentlyInCreationException` | Constructor cycle hoặc bean raw đã được inject trước khi bị bọc | Đọc nguyên nhân gốc, dựng dependency graph, phá vòng |
| Vòng setter từng chạy ở Framework thuần nhưng lỗi sau chuyển Spring Boot | Boot mặc định từ chối circular references | Refactor graph, không mặc định bật property cho phép vòng |
| Client A được advice nhưng client B không | B đang giữ raw target hoặc đi đường trực tiếp không qua proxy | Xác minh identity proxy/target và điểm inject, loại bỏ vòng |
| Aspect giữ tham chiếu tới service mà chính nó advise | Dependency graph khó khởi tạo hoặc advice gọi ngược service | Tách collaborator độc lập, dùng dữ liệu của JoinPoint |
| Bean báo “not eligible for auto-proxying” | Khởi tạo sớm trong giai đoạn BeanPostProcessor | Kiểm tra custom BPP và dependency bị khởi tạo quá sớm |
| `@Lazy` hết lỗi lúc startup nhưng lỗi lúc gọi | Lookup muộn vẫn tạo vòng trong runtime | Thiết kế lại quan hệ phụ thuộc, xem thời điểm `getObject()` |
| Cho phép raw injection rồi mất advice | Dependent bean giữ raw target thay vì final proxy | Không dùng đường raw; refactor và kiểm thử proxy behavior |
| `AopUtils.isAopProxy` trả true nhưng advice mong đợi không chạy | Proxy do advisor khác hoặc pointcut không khớp | Kiểm tra aspect bean, advisor và invocation thực |
| Tham chiếu đến bean trước khi init xong làm lỗi trạng thái | Early reference được gọi quá sớm | Đừng gọi nghiệp vụ ở constructor/init callback của graph vòng |

## 14. Những phân biệt cần nhớ

**Phụ thuộc vòng** là một vấn đề **dependency graph**. **Raw bean được inject nhưng cuối cùng được bọc proxy** là một vấn đề **tham chiếu không nhất quán theo lifecycle**. Hai vấn đề có liên quan nhưng không đồng nghĩa: có vòng không nhất thiết có raw mismatch, và việc có early proxy không làm vòng constructor biến mất.

**AOP proxy** có thể giúp lời gọi đi qua advice, nhưng chỉ khi caller thật sự giữ và sử dụng proxy phù hợp. Tham chiếu sớm có thể là proxy nếu hạ tầng Spring AOP cấp được; không phải cứ gọi early reference là chắc chắn bypass AOP.

**Bật circular references** chỉ cho phép container thử một số đường khởi tạo. Nó không làm cho mọi dependency graph hợp lệ, cũng không phải chính sách bảo đảm bean đã hoàn tất initialization khi được gọi.

**Đọc exception sớm** thường đáng tin cậy hơn việc tìm cách tắt exception: nếu container báo một bean đã được inject raw rồi wrap, mục tiêu của cảnh báo là tránh hành vi AOP không đồng nhất giữa các caller.

## 15. Câu hỏi tự đánh giá

**1. Vì sao vòng A(B) và B(A) qua constructor không thể dùng early singleton reference để giải quyết?**

Vì cả hai constructor cần instance của phía kia trước khi một instance có thể được tạo để đăng ký làm early reference.

**2. Early reference có luôn là raw target không?**

Không. Spring AOP auto-proxy creator có thể cung cấp wrapper sớm qua `getEarlyBeanReference`. Điều đó tùy tình huống và post-processors, không phải bảo đảm chung.

**3. Nếu một dependent bean giữ raw target còn `context.getBean(...)` trả proxy, nguy cơ gì?**

Những lời gọi qua raw target có thể bypass advice trong khi lời gọi qua proxy chạy advice, dẫn tới hành vi phụ trợ không nhất quán.

**4. `setAllowCircularReferences(true)` có tương đương `setAllowRawInjectionDespiteWrapping(true)` không?**

Không. Cái thứ nhất cho phép thử xử lý circular references; cái thứ hai cho phép raw bean được inject dù final bean bị bọc, một tình huống Spring mặc định tránh.

**5. Tại sao aspect inject ngược service nó advise có thể tạo vấn đề?**

Vì aspect và auto-proxy creator cần tham gia xác định việc advice cho service, trong khi graph dependency có thể yêu cầu service được tạo xong trước khi aspect tạo được. Nếu chiều ngược lại hiện diện, dễ thành vòng hoặc khởi tạo sớm.

**6. Sử dụng `ObjectProvider` hay `@Lazy` có sửa tận gốc vòng không?**

Không. Chúng dời thời điểm resolve dependency. Nếu logic gọi quá sớm hoặc graph vẫn có vòng không thể giải quyết, lỗi vẫn xuất hiện.

**7. Sau khi refactor, phải kiểm tra gì để chứng minh AOP hoạt động?**

Bean được khởi tạo thành công, service được lấy từ context là proxy phù hợp, advice được gọi trước/sau method mong muốn, và dependency không còn giữ raw target đi ngoài proxy.

## 16. Tài liệu Spring Framework chính thức

- **Spring Framework — Dependency Injection (Circular dependencies)**: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html
- **Spring Framework — BeanPostProcessor và auto-proxying**: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- **Spring Framework API — AbstractAutoProxyCreator#getEarlyBeanReference**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aop/framework/autoproxy/AbstractAutoProxyCreator.html
- **Spring Framework API — AbstractAutowireCapableBeanFactory#setAllowCircularReferences / setAllowRawInjectionDespiteWrapping**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/support/AbstractAutowireCapableBeanFactory.html
- **Spring Framework — Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- **Spring Boot — Common Application Properties (allow-circular-references)**: https://docs.spring.io/spring-boot/appendix/application-properties/index.html

**Kết luận của bài:** Phụ thuộc vòng có thể buộc Spring cấp tham chiếu sớm khi bean chưa hoàn tất vòng đời. Hạ tầng Spring AOP có thể cấp **early proxy** để giữ nhất quán với proxy cuối cùng, nhưng không phải mọi vòng hay mọi custom post-processor đều an toàn. Thiết kế bean dependency một chiều, đăng ký aspect rõ ràng và kiểm tra lời gọi qua Spring proxy là cách đáng tin cậy để tránh việc tham chiếu raw âm thầm bỏ qua advice.

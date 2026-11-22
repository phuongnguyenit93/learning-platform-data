# Bean khởi tạo quá sớm và tình trạng không đủ điều kiện auto-proxy trong Spring AOP

## 1. Vì sao Spring báo bean “not eligible for auto-proxying”?

Khi ứng dụng dùng Spring AOP, một số Spring bean phải được **tạo sau khi hệ thống BeanPostProcessor (BPP) đã sẵn sàng** để auto-proxy creator có thể xem xét và bọc bean bằng proxy. Nếu một bean bị khởi tạo **quá sớm**, trong lúc Spring còn đang tìm, khởi tạo hoặc đăng ký các BPP, bean ấy có thể chỉ đi qua một phần chuỗi BPP. Kết quả là bean đã tạo có thể **không được bọc bằng Spring AOP proxy**, dù kiểu hoặc phương thức của nó có vẻ khớp một `@Aspect` advice.

Thông báo thường gặp:

~~~text
Bean 'someBean' of type [example.SomeBean] is not eligible for getting processed
by all BeanPostProcessors (for example: not eligible for auto-proxying)
~~~

Thông điệp trên là **dạng minh họa**, không phải bản ghi được cam kết chính xác từng chữ ở mọi phiên bản Spring: bean name, class name và thông tin bổ sung có thể khác. Nó nói rằng bean đã được tạo khi toàn bộ các post-processor dự kiến chưa được đăng ký. **Không tự động đồng nghĩa bean có lỗi, hoặc chắc chắn thiếu mọi loại proxy**; cần kiểm tra proxy thực tế và chuỗi khởi tạo. Tuy nhiên, với Spring AOP, đây là dấu hiệu rất đáng chú ý khi advice không chạy.

Phạm vi bài tập trung vào **auto-proxying của Spring Framework**, thứ tự đăng ký BeanPostProcessor, quan hệ phụ thuộc khiến bean được tạo sớm, bằng chứng quan sát và cách xử lý. Không cần mở rộng sang kiến thức AspectJ weaving độc lập.

## 2. Cơ chế gây ra tình trạng này

### 2.1. Auto-proxy creator cũng là BeanPostProcessor

Đối với Spring AOP kiểu `@AspectJ`, `@EnableAspectJAutoProxy` đăng ký hạ tầng auto-proxy creator của Spring (tiêu biểu `AnnotationAwareAspectJAutoProxyCreator`, kế thừa `AbstractAutoProxyCreator`). Hạ tầng này là một **BeanPostProcessor** chuyên trách: khi một Spring bean được tạo, nó tìm các advisor phù hợp rồi có thể trả về proxy thay cho target.

Luồng chuẩn, rút gọn:

~~~text
Đăng ký BeanDefinition
       |
       v
Spring tìm và khởi tạo các BeanPostProcessor
       |
       v
Spring đăng ký đầy đủ BPP, gồm auto-proxy creator
       |
       v
Tạo các application bean thông thường
       |
       v
postProcessBeforeInitialization(...)
       |
       v
@PostConstruct / InitializingBean / custom init method
       |
       v
postProcessAfterInitialization(...)
       |
       +--> advisor không áp dụng: bean gốc
       |
       +--> advisor áp dụng: Spring AOP proxy
                                    |
                                    v
                         Bean nhận bởi caller
                                    |
                                    v
                        proxy -> advice -> target
~~~

Đây là luồng thường gặp cho singleton bean thông thường. Spring còn có các extension point hỗ trợ tham chiếu sớm, ví dụ `SmartInstantiationAwareBeanPostProcessor`, và các tình huống dependency đặc biệt; sơ đồ không được hiểu là thứ tự gọi tuyệt đối cho mọi loại bean.

Auto-proxy creator đánh giá bean trong **quá trình tạo bean**, không chạy lại mỗi lần có method invocation. Sau khi có proxy, một lời gọi đi qua proxy mới vào chuỗi advice. Khi bean được khởi tạo trước lúc auto-proxy creator tham gia đầy đủ, việc gọi method về sau **không tự làm Spring bọc lại instance đó**.

### 2.2. Giai đoạn đặc biệt để tạo và đăng ký BPP

`ApplicationContext` cần chuẩn bị BPP trước khi tạo hàng loạt application beans. Để làm được vậy, Spring chủ động tìm những bean có kiểu `BeanPostProcessor`, khởi tạo chúng **sớm** và đăng ký vào container. Những BPP đã khởi tạo, cùng bean được kéo vào làm dependency của chúng, có thể tồn tại **trước lúc mọi BPP khác, bao gồm auto-proxy creator, được đăng ký đầy đủ**.

Một chuỗi dễ gây lỗi:

~~~text
ApplicationContext.refresh()
          |
          v
Bắt đầu đăng ký BeanPostProcessor
          |
          v
Khởi tạo customAuditPostProcessor
          |
          +--> constructor/ @Bean parameter yêu cầu paymentService
                              |
                              v
                     paymentService bị tạo ngay
                              |
                              v
                     Chưa có đủ BPP để xét auto-proxy
                              |
                              v
                     Bean có thể ở dạng target gốc
          |
          v
Các BPP còn lại (bao gồm auto-proxy creator) được đăng ký
          |
          v
ApplicationContext tiếp tục tạo các bean khác
          |
          v
paymentService đã tồn tại từ trước; không được tự tạo lại
~~~

Trong một số tình huống, dependency của BPP có thể bị tạo sớm do tìm kiếm theo kiểu, `@Autowired`, `@Resource`, lời gọi thủ công tới `getBean()`, hoặc method `@Bean` tạo BPP cần một service. Không nhất thiết phải có một explicit call `new Service()` trong cấu hình để vấn đề xuất hiện.

Điểm cốt lõi: **Spring AOP cũng phụ thuộc vào BeanPostProcessor**. Bean sinh ra trong chính giai đoạn bootstrap các BPP có thể không có cơ hội được xử lý bởi toàn bộ auto-proxy pipeline.

### 2.3. BeanPostProcessor và các dependency của nó

Theo tài liệu Spring, chính các instance `BeanPostProcessor` và bean chúng trực tiếp tham chiếu thường **không đủ điều kiện auto-proxy như những application bean được tạo bình thường sau đó**. Một ví dụ thường thấy là BPP nghiệp vụ được inject một service vốn lại cần `@Before`/`@Around` hoặc `@Transactional` dạng proxy.

Tuy nhiên, cần đọc cảnh báo theo logic thay vì kết luận quá mức:

- Nó chủ yếu phát hiện **thời điểm và phạm vi post-processing**: bean đã được tạo khi số lượng BPP đăng ký thấp hơn mục tiêu dự kiến.
- Nó **không** khẳng định một pointcut cụ thể sẽ khớp hay không; còn phải kiểm tra aspect và advisor.
- Không phải mọi BPP đều thiết kế để trở thành đối tượng được advice; một số bean hạ tầng Spring được cố ý loại khỏi auto-proxy.
- Nếu ứng dụng còn cơ chế proxy khác hoặc tạo proxy trực tiếp, tình trạng cụ thể cần xác nhận bằng loại bean thực nhận và advisor của nó.
- Đừng cố “sửa” bằng cách bật AspectJ weaver vì vấn đề đang nằm ở **Spring container lifecycle và Spring AOP proxy**.

## 3. Các nguyên nhân thực tế trong cấu hình Spring

| Nguyên nhân | Tại sao gây khởi tạo sớm? | Dấu hiệu |
| --- | --- | --- |
| Constructor của custom BPP nhận application service | Container phải dựng service để dựng BPP | Service bị khởi tạo trong giai đoạn BPP registration |
| Static `@Bean` tạo BPP có tham số service | Static tránh khởi tạo config class nhưng **không tránh dependency service được inject sớm** | Cảnh báo cho service được truyền vào |
| Non-static `@Bean` trả `BeanPostProcessor` | Muốn gọi factory method, Spring phải tạo cả configuration object sớm | Configuration class và các dependency liên quan có thể không đủ post-processing |
| BPP tự `getBean("orderService")` lúc construction | Kéo business bean ra trước thời điểm sẵn sàng của auto-proxy creator | BPP startup làm service xuất hiện bất thường |
| `@Resource`/autowire trong BPP khiến Spring dò bean theo kiểu | Một số kiểu dependency lookup có thể kéo thêm bean ngoài dự định | Bean không liên quan trực tiếp theo tên nhưng vẫn bị tạo sớm |
| Custom `BeanFactoryPostProcessor` gọi `getBean(...)` | Force instance creation trong pha xử lý definition, trước giai đoạn BPP thường lệ | Bean không đi qua đầy đủ các post-processors |
| BPP đăng ký muộn trong runtime | Các bean đã sinh ra không tự động được áp dụng processor mới | Một số bean có proxy, một số cùng loại lại không |

Một nuance quan trọng: **`static @Bean` là khuyến nghị cho BPP, nhưng không phải thuốc chữa mọi eager dependency**. Khi method vẫn khai báo tham số là một business service, việc inject tham số đó có thể kéo service vào quá trình tạo BPP quá sớm.

## 4. Ví dụ Spring Framework tái lập lỗi và đối chứng

Ví dụ dưới đây cố ý tạo **hai bean cùng kiểu**: `earlyService` được inject vào một `PriorityOrdered BeanPostProcessor` trong giai đoạn bootstrap; `normalService` được tạo sau và có cơ hội nhận AOP proxy. Một aspect `@Before` khớp method của cả hai. Kết quả làm rõ vì sao một bean không nhận advice mặc dù cùng class và pointcut.

Yêu cầu: **Java 17+**, Maven, Spring Framework **6.2.0**. Đây là bài chạy độc lập, không dùng Spring Boot, không dùng AspectJ weaving.

Cấu trúc project:

~~~text
spring-early-bpp/
├── pom.xml
└── src/main/java/demo/
    ├── App.java
    ├── TrackedService.java
    ├── TraceAspect.java
    └── EarlyReferenceBpp.java
~~~

### 4.1. Maven dependencies

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-early-bpp</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22</version>
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

`spring-context` lo container và BPP registration; `spring-aop` hỗ trợ AOP proxy; `aspectjweaver` cung cấp kiểu annotation/pointcut để Spring hiểu `@AspectJ`. **Thêm dependency này không kích hoạt bytecode weaving**.

### 4.2. Service dùng chung cho cả hai bean

Tạo `src/main/java/demo/TrackedService.java`:

~~~java
package demo;

public class TrackedService {
    private final String name;

    public TrackedService(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    public void execute() {
        System.out.println("TARGET: " + name);
    }
}
~~~

Class `TrackedService` và method `execute` đều không `final`, cho phép Spring tạo subclass proxy khi `proxyTargetClass = true`. Các bean `earlyService` và `normalService` chỉ khác nhãn tên, giúp đối chứng cùng một advisor.

### 4.3. Aspect chung cho cả hai service

Tạo `src/main/java/demo/TraceAspect.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Before("execution(* demo.TrackedService.execute(..))")
    public void beforeExecute(JoinPoint joinPoint) {
        TrackedService target = (TrackedService) joinPoint.getTarget();
        calls.incrementAndGet();
        System.out.println("ADVICE: " + target.getName());
    }

    public int count() {
        return calls.get();
    }
}
~~~

Advice chỉ chọn method execution `TrackedService.execute()`. Nếu cả hai bean đều được proxy, mỗi lần gọi `execute()` qua bean reference sẽ khớp. Khi chỉ `normalService` được proxy, chỉ lời gọi tới bean đó kích hoạt advice và tăng `calls`.

### 4.4. BeanPostProcessor cố tình kéo một service vào bootstrap

Tạo `src/main/java/demo/EarlyReferenceBpp.java`:

~~~java
package demo;

import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.PriorityOrdered;

public class EarlyReferenceBpp implements BeanPostProcessor, PriorityOrdered {
    private final TrackedService capturedService;

    public EarlyReferenceBpp(TrackedService capturedService) {
        this.capturedService = capturedService;
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }
}
~~~

Ở Spring 6.2, hai callback `BeanPostProcessor` có default implementation, nên ví dụ không cần override `postProcessBeforeInitialization` hoặc `postProcessAfterInitialization` chỉ để giữ nguyên bean. BPP này **không tạo proxy, không gọi aspect, không sửa business logic**. Nó cố ý giữ reference tới một application service trong constructor để minh họa **dependency bị kéo vào quá sớm**.

`PriorityOrdered` làm processor tùy biến thuộc nhóm được Spring chuẩn bị ưu tiên trước nhóm BPP chỉ triển khai `Ordered`. Auto-proxy creator Spring 6.2 kế thừa `AbstractAutoProxyCreator` triển khai `Ordered`. Trong project này, việc resolve dependency của `EarlyReferenceBpp` diễn ra khi các BPP còn đang được đăng ký, trước khi auto-proxy creator xử lý `earlyService` theo luồng thông thường.

Không nên dùng thứ tự `PriorityOrdered` để thiết kế một BPP nghiệp vụ phụ thuộc vào service. Nó được dùng ở đây **chỉ để tái lập rõ tình huống lỗi**.

### 4.5. Cấu hình và mã chạy

Tạo `src/main/java/demo/App.java`:

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class App {
    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    static class Config {
        @Bean
        public TrackedService earlyService() {
            return new TrackedService("early");
        }

        @Bean
        public TrackedService normalService() {
            return new TrackedService("normal");
        }

        @Bean
        public TraceAspect traceAspect() {
            return new TraceAspect();
        }

        @Bean
        public static EarlyReferenceBpp earlyReferenceBpp(
                @Qualifier("earlyService") TrackedService earlyService) {
            return new EarlyReferenceBpp(earlyService);
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            TrackedService early =
                    (TrackedService) context.getBean("earlyService");
            TrackedService normal =
                    (TrackedService) context.getBean("normalService");
            TraceAspect aspect = context.getBean(TraceAspect.class);

            boolean earlyProxy = AopUtils.isAopProxy(early);
            boolean normalProxy = AopUtils.isAopProxy(normal);

            System.out.println("EARLY_PROXY: " + earlyProxy);
            System.out.println("NORMAL_PROXY: " + normalProxy);

            early.execute();
            normal.execute();

            System.out.println("ADVICE_COUNT: " + aspect.count());

            if (earlyProxy || !normalProxy || aspect.count() != 1) {
                throw new IllegalStateException(
                        "Unexpected Spring AOP auto-proxy behavior");
            }
            System.out.println("CHECK: PASS");
        }
    }
}
~~~

Giải thích chi tiết các quyết định:

- `@EnableAspectJAutoProxy(proxyTargetClass = true)` kích hoạt Spring AOP, yêu cầu class-based proxy. Không phụ thuộc việc hai service implement interface hay không.
- `@Bean earlyService()` và `@Bean normalService()` cùng trả `TrackedService`. `@Bean traceAspect()` tạo Spring bean chứa advisor từ `@Before`.
- `@Bean public static EarlyReferenceBpp earlyReferenceBpp(...)` cho phép Spring tìm/khởi tạo BPP mà không phải khởi tạo `Config` chỉ vì factory method. **Tuy nhiên**, tham số `@Qualifier("earlyService")` buộc Spring tạo `earlyService` để đưa vào constructor BPP, ngay trong pha đăng ký processor. Việc khai báo `static` không chặn được eager dependency này.
- Kiểu trả về **cụ thể** `EarlyReferenceBpp` cho Spring biết factory method tạo BPP thuộc nhóm `PriorityOrdered` ngay từ lúc kiểm tra kiểu; việc trả một kiểu quá chung có thể làm phát hiện và thứ tự xử lý thiếu chính xác.
- `normalService` không phải dependency của BPP, nên được tạo theo quá trình singleton initialization thông thường, sau khi Spring đã đăng ký auto-proxy creator.
- Chương trình lấy bean **qua Spring context**, kiểm tra trực tiếp bằng `AopUtils.isAopProxy` rồi gọi cùng method `execute()` ở hai bean. Biến đếm của aspect giúp xác minh có chính xác một advice chạy.

### 4.6. Chạy và quan sát kết quả

Trong thư mục `spring-early-bpp`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng **do chương trình Java tự in ra** trong project Spring 6.2.0 được cấu hình ở trên:

~~~text
EARLY_PROXY: false
NORMAL_PROXY: true
TARGET: early
ADVICE: normal
TARGET: normal
ADVICE_COUNT: 1
CHECK: PASS
~~~

Có thể có WARN từ logger Spring báo `earlyService` chưa được tất cả BPP xử lý. **Cảnh báo không nằm trong bảy dòng do chương trình in**; tên logger, nội dung và thứ tự log phụ thuộc cấu hình logging. Mục tiêu ở đây là quan sát `AopUtils` và `TraceAspect.count()`.

Đọc kết quả theo hai nhánh:

- **Nhánh early:** `earlyService` được tạo để khởi tạo `EarlyReferenceBpp` khi auto-proxy creator chưa có cơ hội xử lý đầy đủ bean đó. Khi gọi `early.execute()`, chỉ có `TARGET: early`, không có `ADVICE: early`.
- **Nhánh normal:** `normalService` được tạo sau giai đoạn đăng ký BPP, auto-proxy creator tìm thấy advisor `TraceAspect` phù hợp, tạo proxy; `normal.execute()` đi qua proxy nên in `ADVICE: normal` trước `TARGET: normal`.
- Cả hai cùng class và dùng cùng pointcut. Điều khác biệt là **thời điểm Spring tạo bean so với quá trình đăng ký các processor**.
- Nếu stdout/proxy status khác kỳ vọng, chương trình ném exception thay vì báo thành công. Khi chạy với phiên bản Spring hoặc cấu hình khác, hãy kiểm tra log bootstrap và các BPP được đăng ký thay vì ép dữ liệu thành giống bản mẫu.

## 5. Cách khắc phục: đừng yêu cầu service trong lúc tạo BeanPostProcessor

Cách khắc phục tốt nhất là bỏ quan hệ BPP → business service ở thời điểm khởi tạo. Nếu BPP chỉ cần quan sát thông tin bean, viết callback nhận `Object bean, String beanName`; nếu cần logic nghiệp vụ, đẩy nó sang service hoặc advice chạy **sau khi context hoàn thành khởi tạo**.

Trong project trên, một bản sửa tối thiểu để tự đối chứng là thay `EarlyReferenceBpp` bằng processor không giữ `TrackedService`:

~~~java
package demo;

import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.PriorityOrdered;

public class EarlyReferenceBpp implements BeanPostProcessor, PriorityOrdered {
    public EarlyReferenceBpp() {
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }
}
~~~

Đồng thời thay factory method BPP trong `App.Config` bằng:

~~~java
@Bean
public static EarlyReferenceBpp earlyReferenceBpp() {
    return new EarlyReferenceBpp();
}
~~~

Hai code fence này là **những đoạn thay thế cho hai phần tương ứng trong project đã có**, không phải các tệp Java độc lập. Bây giờ `earlyService` không còn bị tạo bởi dependency của BPP. Nếu không có nguyên nhân khởi tạo sớm khác, cả hai service đều đi qua auto-proxy creator:

~~~text
EARLY_PROXY: true
NORMAL_PROXY: true
ADVICE: early
TARGET: early
ADVICE: normal
TARGET: normal
ADVICE_COUNT: 2
~~~

Cần sửa cả kiểm tra trong `App.main()` cho kịch bản mới:

~~~java
if (!earlyProxy || !normalProxy || aspect.count() != 2) {
    throw new IllegalStateException(
            "Expected both service beans to be proxied");
}
~~~

Sau khi thay cả ba đoạn trên, chương trình tiếp tục in `CHECK: PASS`. Nếu chỉ thay BPP nhưng giữ điều kiện cũ `earlyProxy || ... count != 1`, kết quả `CHECK` sẽ lỗi **đúng theo phép kiểm tra cũ**, không phải vì Spring AOP hỏng.

### 5.1. Khi BPP thực sự cần một dependency

Phân biệt ba nhu cầu:

1. **Cần cấu hình đơn giản:** truyền literal, cấu hình thuần hoặc bean definition metadata vào BPP, tránh inject service có advice/transaction.
2. **Cần tra cứu bean khi xử lý mỗi callback:** cân nhắc thiết kế lại để không biến BPP thành thành phần điều phối nghiệp vụ; nếu phải dùng lookup, chỉ tra cứu ở thời điểm an toàn và quản lý dependency/recursion cẩn thận. Dùng `ObjectProvider`/`Provider` có thể **trì hoãn** việc resolve dependency, nhưng **không tự bảo đảm an toàn** nếu gọi `getObject()` ngay trong constructor hoặc trong bootstrap callback.
3. **Cần xử lý nghiệp vụ bình thường:** không dùng BPP làm nơi gọi service. Dùng `@Aspect` advice, một service khác hoặc listener chạy sau context refresh tùy nhiệm vụ. Với Spring AOP, đây thường là lựa chọn đơn giản nhất.

### 5.2. Khai báo `@Bean` cho BPP đúng cách

Một khai báo nên ưu tiên:

~~~java
@Bean
public static CustomBeanPostProcessor customBeanPostProcessor() {
    return new CustomBeanPostProcessor();
}
~~~

`CustomBeanPostProcessor` là tên class **minh họa**, không phải class đã định nghĩa trong project thực hành. Hai điểm chính:

- **`static`:** container có thể gọi factory method mà không phải tạo sớm configuration instance.
- **Không có dependency mạnh đến business service:** tránh khởi tạo service trong giai đoạn BPP registration.

Không nên khai báo:

~~~java
@Bean
public BeanPostProcessor myProcessor(PaymentService paymentService) {
    return new MyProcessor(paymentService);
}
~~~

Đây là **ví dụ về cấu hình cần xem lại**, không phải snippet biên dịch độc lập. `PaymentService` và `MyProcessor` chỉ là tên minh họa. Factory method non-static có thể kích hoạt config class sớm, còn tham số service kéo dependency business bean vào bootstrap.

Hơn nữa, factory method tạo BPP cần return type thể hiện rõ kiểu BPP; nếu khai báo return type quá rộng như `Object`, Spring có thể không phát hiện chính xác BPP đủ sớm trong quá trình lấy danh sách post-processor.

## 6. Những tình huống gần giống nhưng nguyên nhân khác

### 6.1. Proxy có tồn tại nhưng advice vẫn không chạy

`AopUtils.isAopProxy(bean) == true` là bằng chứng proxy tồn tại, không phải bằng chứng advisor cụ thể sẽ chạy. Nếu proxy đã có, cần xem:

- Pointcut `execution(...)` có thực sự khớp method không?
- Caller có gọi qua Spring bean proxy hay gọi `this.method()` trong target?
- Method có khả năng proxy được không (JDK interface, CGLIB class/method `final`, visibility)?
- Có nhiều advisor/proxy khác chỉ bao một số method hay không?

Ngược lại, nếu bean không nhận proxy và xuất hiện WARN “not eligible for auto-proxying”, hãy ưu tiên điều tra **lịch khởi tạo và dependency của BPP** trước khi thay đổi biểu thức pointcut.

### 6.2. @PostConstruct gọi method có advice

Trong Spring AOP proxy-based, method được gọi ngay trong constructor hoặc `@PostConstruct` của target thường không đi qua proxy cuối cùng, kể cả bean sau đó sẽ trở thành proxy. Điều này **không nhất thiết** là “bean không đủ điều kiện auto-proxying”. Phải phân biệt:

| Tình huống | Proxy sau khi context khởi tạo? | Advice trên lời gọi đang quan sát? |
| --- | --- | --- |
| Bean được tạo đúng pha, gọi method qua proxy | Có, nếu advisor khớp | Có khi match |
| Bean được tạo đúng pha, gọi method nội bộ trong `@PostConstruct` | Về sau có thể có | Lời gọi ở init thường không qua proxy |
| Bean bị khởi tạo quá sớm vì BPP dependency | Có thể không có | Lời gọi vào target không được AOP intercept |
| Gọi object tự tạo bằng `new` ngoài Spring | Không phải Spring proxy | Không, trừ cơ chế độc lập khác |

Việc chuyển logic khỏi `@PostConstruct` hoặc tách service có thể giải quyết vấn đề gọi method lúc init, nhưng nguyên nhân của cảnh báo *not eligible* cần xét riêng.

### 6.3. Circular dependency và early reference

Auto-proxy creator có cơ chế như `getEarlyBeanReference(...)` để hỗ trợ một số trường hợp dependency vòng, nhằm tránh trao target raw cho một số bean rồi sau đó dùng proxy ở nơi khác. Tuy nhiên, khả năng này **không phải bảo đảm mọi bean khởi tạo quá sớm sẽ được proxy**, đặc biệt khi toàn bộ BPP chưa đăng ký. Đừng dùng circular reference làm phương án chữa thông báo early initialization. Refactor dependencies để phá vòng là cách đáng tin hơn.

### 6.4. Context cha/con và proxy configuration

Các BeanPostProcessor đăng ký với một `ApplicationContext` có phạm vi theo container đó. BPP trong parent không tự xử lý mọi bean sinh trong child. Trong ứng dụng nhiều context, cần kiểm tra nơi aspect, auto-proxy creator và service được tạo; đừng quy tất cả việc thiếu advice cho early initialization.

### 6.5. Spring Boot auto-configuration

Spring Boot có thể tự bật AOP khi có dependency starter tương ứng, nhưng cơ chế proxy Spring vẫn dựa vào post-processing của container. Nếu một service bị tạo quá sớm vì chính BPP tự khai báo hoặc dependency của nó, chỉ thêm `spring-boot-starter-aop` hay `@EnableAspectJAutoProxy` thường **không giải quyết thời điểm khởi tạo**. Kiểm tra logs, bean graph và vị trí processor trước.

## 7. Quy trình chẩn đoán thực tế

Khi thấy cảnh báo trong log hoặc advice bỗng không chạy, thực hiện có thứ tự:

1. **Ghi lại chính xác tên và kiểu bean** được nêu trong WARN; không đoán theo symptom. Nếu log chỉ báo “not eligible ...”, tra nguyên nhân bootstrap của chính bean đó.
2. **Xác nhận proxy sau khi context sẵn sàng**: gọi `AopUtils.isAopProxy(context.getBean("beanName"))`. Với Spring bean có proxy, cân nhắc kiểm tra tiếp `isCglibProxy`/`isJdkDynamicProxy`.
3. **Kiểm tra BPP registration:** xem các class triển khai `BeanPostProcessor`, đặc biệt custom BPP, `BeanPostProcessor` trả về qua `@Bean`, và auto-proxy creator do `@EnableAspectJAutoProxy` đăng ký.
4. **Tìm quan hệ phụ thuộc:** constructor tham số service, `@Autowired`/`@Resource` trong BPP, factory method BPP non-static, `getBean()` gọi sớm hoặc `BeanFactoryPostProcessor` làm instantiate object.
5. **Đọc thứ tự startup** bằng logger framework/trace debug phù hợp môi trường. Đối chiếu việc bean được tạo trước hay sau khi auto-proxy creator đã được đăng ký và hạ tầng aspect sẵn sàng.
6. **Tách eager dependency khỏi BPP:** static `@Bean`, giảm dependency hoặc trì hoãn giải quyết dependency đến thời điểm phù hợp, nhưng không giải quyết bean business ngay trong bootstrap callback.
7. **Chạy lại và kiểm tra hành vi thật:** log WARN có còn không, AOP proxy có xuất hiện không, advice có chạy qua external caller hay không. Đo proxy và advice độc lập, không chỉ dựa vào hết cảnh báo.
8. **Kiểm tra nguyên nhân thứ hai nếu vẫn lỗi:** pointcut, self-invocation, object ngoài container, final method, nhiều context hoặc advisor khác.

### Dùng AopUtils để đo mà không suy luận từ tên lớp proxy

Đoạn minh họa sau đặt **bên trong mã đã có biến `context`**, không phải tệp Java độc lập:

~~~java
Object bean = context.getBean("normalService");

System.out.println("AOP=" + org.springframework.aop.support.AopUtils.isAopProxy(bean));
System.out.println("JDK=" + org.springframework.aop.support.AopUtils.isJdkDynamicProxy(bean));
System.out.println("CGLIB=" + org.springframework.aop.support.AopUtils.isCglibProxy(bean));
~~~

Ở ví dụ nguyên bản, `normalService` là class-based proxy, nên ba dòng tương ứng là `AOP=true`, `JDK=false`, `CGLIB=true`. Nếu một application bean không có proxy, hãy quay lại kiểm tra cả lifecycle lẫn advisor/pointcut; không thể kết luận chỉ từ tên class chứa `$$SpringCGLIB$$` hoặc mỗi một WARN.

## 8. Những điều không nên làm để “chữa” cảnh báo

- **Không tự xóa log hoặc đổi logging level để coi là đã khắc phục.** Cảnh báo là dấu hiệu cho thấy một đường tạo bean bất thường; cần hiểu bean nào và BPP nào liên quan.
- **Không dùng `@DependsOn` một cách máy móc để ép thứ tự.** Nếu tạo bean trước khi processor sẵn sàng, `@DependsOn` có thể làm lỗi nặng hơn, không bảo đảm Spring AOP proxy xuất hiện.
- **Không cố gọi `getBean()` thêm một lần với hy vọng container tự tạo lại proxy.** Singleton đã sinh có thể được giữ lại; lookup lại thường lấy đúng instance đó.
- **Không tự bọc proxy thứ hai trong một custom BPP nếu chỉ cần advice chuẩn.** Dễ gây double-proxy, thay đổi thứ tự advisor và xung đột transaction/cache.
- **Không nhầm `static @Bean` với loại bỏ dependency.** Static giúp tránh khởi tạo configuration object sớm; tham số factory method vẫn được Spring resolve khi dựng processor.
- **Không mặc định phải chuyển sang AspectJ weaving.** Hãy sửa chuỗi khởi tạo bean và giữ Spring AOP nếu phạm vi method trên managed Spring bean vẫn phù hợp.

## 9. Bài tập tự kiểm tra

1. Tại sao một `BeanPostProcessor` lại làm service nhận thiếu Spring AOP advice?  
   **Vì việc khởi tạo BPP kéo service vào container trước khi toàn bộ auto-proxy creator/BPP sẵn sàng; service không đi qua đủ post-processing để thành proxy.**

2. Vì sao khai báo `@Bean static EarlyReferenceBpp earlyReferenceBpp(TrackedService earlyService)` vẫn có thể lỗi?  
   **Vì `static` không ngăn Spring phải khởi tạo service dùng làm tham số.**

3. Vì sao hai bean cùng class, cùng pointcut nhưng chỉ một bean có proxy?  
   **Vì thời điểm tạo bean khác nhau so với giai đoạn đăng ký BPP, không phải vì cú pháp aspect khác nhau.**

4. Thông báo “not eligible for auto-proxying” có khẳng định chắc chắn bean sẽ không bao giờ có proxy không?  
   **Không. Nó cho biết thiếu một phần quá trình post-processing; phải đo trạng thái bean và cấu hình thực tế.**

5. Làm cách nào xác nhận lỗi đã được giải quyết?  
   **Sau khi loại bỏ dependency gây khởi tạo sớm, kiểm tra bean lấy từ context bằng `AopUtils.isAopProxy(...)` và xác minh advice thực sự chạy trên lời gọi qua proxy.**

## 10. Tài liệu Spring Framework

- [Container Extension Points — BeanPostProcessor, early initialization](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-extension.html): chuỗi xử lý BPP, bean bị khởi tạo sớm, WARN và khuyến nghị `static @Bean`.
- [Spring @Bean Javadoc — BeanPostProcessor-returning methods](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Bean.html): return type cụ thể, `static` và tránh dependency lúc bootstrap.
- [Spring @AspectJ support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): Spring diễn giải cú pháp `@AspectJ` bằng hạ tầng proxy.
- [Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): cách kích hoạt cơ chế tự tạo proxy cho Spring bean.
- [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): loại proxy và giới hạn method invocation trong Spring AOP.

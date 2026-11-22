# Giới hạn đảm bảo thứ tự giữa nhiều advice cùng loại trong Spring AOP

## 1. Bài học giải quyết vấn đề gì?

Khi nhiều Spring AOP advice cùng khớp một method execution của Spring bean, người học thường nhìn vào thứ tự các method được viết trong một class rồi cho rằng Spring sẽ gọi chúng từ trên xuống dưới. **Đó không phải một bảo đảm của Spring AOP.**

Đặc biệt, **hai hoặc nhiều advice cùng loại** – ví dụ hai `@Before`, hai `@After`, hai `@AfterReturning`, hai `@AfterThrowing` hoặc hai `@Around` – **được khai báo trong cùng một class `@Aspect` và cùng áp dụng cho một join point** thì **thứ tự giữa chúng không được định nghĩa** theo tài liệu Spring Framework. Java reflection không cung cấp một hợp đồng đáng tin cậy để truy hồi thứ tự khai báo trong source của các methods mà `javac` biên dịch.

Một ví dụ dễ mắc lỗi:

~~~java
@Aspect
@Component
public class OrderChecksAspect {

    @Before("execution(* demo.JobApi.run(..))")
    public void validate() {
        System.out.println("VALIDATE");
    }

    @Before("execution(* demo.JobApi.run(..))")
    public void audit() {
        System.out.println("AUDIT");
    }
}
~~~

Đây là **fragment minh họa**: cần các imports, `JobApi` và Spring context phù hợp. **Không được kết luận chắc rằng VALIDATE sẽ luôn xuất hiện trước AUDIT** chỉ vì `validate()` được viết phía trên `audit()`.

Nếu `audit()` giả định `validate()` đã kiểm tra quyền/đầu vào, kết quả có thể không như mong đợi khi thay phiên bản compiler, Spring hoặc môi trường triển khai.

Mục tiêu của README này:

1. Nêu đúng **bảo đảm thứ tự** mà Spring AOP cung cấp, và phần **không được bảo đảm**.
2. Phân biệt advice **cùng loại trong một aspect** và advice **ở các aspect khác nhau**.
3. Hiểu `@Order` / `Ordered` **điều khiển precedence cấp aspect** thay vì “đánh số thứ tự source methods” trong cùng aspect.
4. Nắm quy tắc **trên đường vào** và **trên đường ra** khi advice bọc nhau; tránh đọc sai `@After`.
5. Tổ chức lại thành **một advice có các bước tuần tự**, hoặc thành **nhiều aspect có order khác nhau**.
6. Chạy ví dụ **Java 17+ / Spring Framework 6.2.x / Maven** cho hai `@Before` nằm ở **hai aspect được sắp thứ tự**, có stdout có thể kiểm chứng.
7. Biết cách viết test: khẳng định hợp đồng được bảo đảm và **không viết test phụ thuộc vào hành vi tình cờ**.

**Special Note/phạm vi:** Chỉ tập trung vào **Spring Framework proxy-based AOP** và `@AspectJ` style mà Spring hỗ trợ. Các khái niệm chung của AspectJ chỉ được nhắc khi cần diễn giải quy tắc Spring; không chuyển sang bytecode weaving độc lập.

## 2. Hai trục cần phân biệt: loại advice và nơi khai báo

Có hai câu hỏi khác nhau:

- **Các advice thuộc cùng loại hay khác loại?** Ví dụ hai `@Before` là **cùng loại**; `@Before` và `@AfterReturning` là **khác loại**.
- **Chúng nằm trong cùng class `@Aspect` hay trong hai `@Aspect` class khác nhau?**

Bảng phân loại:

| Trường hợp | Spring bảo đảm điều gì? | Cách xử lý khi thứ tự là yêu cầu nghiệp vụ |
| --- | --- | --- |
| Hai `@Before` cùng class `@Aspect`, cùng match | **Không xác định thứ tự giữa hai method advice** | Gộp thành một `@Before` và gọi các bước tuần tự, hoặc tách aspect |
| Hai `@AfterReturning` cùng class `@Aspect`, cùng match | **Không xác định thứ tự giữa hai advice cùng loại** | Gộp hoặc tách aspect có `@Order` |
| Hai `@Around` cùng class `@Aspect`, cùng match | **Không xác định thứ tự giữa hai advice cùng loại** | Gộp logic vào một `@Around` hoặc tách aspect |
| Hai advice cùng loại ở **hai aspect khác nhau**, không order | **Thứ tự không xác định**, trừ khi có cấu hình precedence khác | Cấp precedence tường minh |
| Hai advice ở hai aspects, `@Order(10)` và `@Order(20)` | Aspect có **giá trị nhỏ hơn ưu tiên cao hơn** | Dùng khi cần ranh giới concern rõ và thứ tự được kiểm soát |
| Các advice **khác loại** trong cùng `@Aspect` | Spring xác định precedence theo loại advice; thời điểm thực thi phụ thuộc ngữ nghĩa trước/sau | Hiểu `@After` dạng finally và đường vào/ra |

**Không nên đồng nhất “thứ tự không xác định” với “Spring sẽ chọn ngẫu nhiên ở mỗi request”.** Một JVM có thể cho ra thứ tự trông ổn định trong hàng nghìn lần gọi, nhưng điều đó **không tạo hợp đồng** để phụ thuộc khi nâng cấp hoặc tái cấu trúc.

## 3. Chính xác Spring nói gì về advice cùng loại?

Tài liệu Spring Framework phần **Declaring Advice → Advice Ordering** chỉ rõ:

- Khi hai advice cùng loại trong **cùng một class `@Aspect`** đều cần chạy tại cùng join point, **thứ tự không được định nghĩa**.
- Lý do: thứ tự khai báo methods trong source Java không thể truy xuất một cách tin cậy qua reflection đối với classes do `javac` biên dịch.
- Spring khuyến nghị **gộp những advice liên quan vào một method** ở mỗi aspect/join point, hoặc **tách chúng thành các `@Aspect` classes riêng** rồi dùng `Ordered` hoặc `@Order` ở cấp aspect.

Chú ý điều kiện **“cùng áp dụng cho một join point”**. Nếu hai `@Before` có pointcut **loại trừ lẫn nhau**, chúng không tranh nhau thứ tự trên cùng lời gọi.

Ví dụ:

~~~java
@Before("execution(* demo.JobApi.run(..))")
public void beforeRun() {
    // Chỉ khi run(...) match.
}

@Before("execution(* demo.JobApi.cancel(..))")
public void beforeCancel() {
    // Chỉ khi cancel(...) match.
}
~~~

Nếu `run` và `cancel` là hai phương thức khác nhau, cùng một invocation sẽ không kích hoạt cả hai advice trong trường hợp điển hình; không có tranh chấp về thứ tự cần giải quyết.

Ngược lại, khi hai pointcuts giao nhau:

~~~java
@Before("execution(* demo.JobApi.*(..))")
public void beforeAnyMethod() {
    // Match mọi method trên JobApi.
}

@Before("execution(* demo.JobApi.run(..))")
public void beforeRunOnly() {
    // Match cả run(...), nên giao với beforeAnyMethod().
}
~~~

Lời gọi `run(...)` có thể kích hoạt **cả hai `@Before`**. Nếu chúng ở cùng class `@Aspect`, không được dựa vào thứ tự khai báo của hai method advice.

## 4. @Order không đánh số thứ tự từng method advice trong cùng @Aspect

Trong Spring, cách phổ biến đặt precedence giữa **hai aspects** là:

~~~java
@Aspect
@Component
@Order(10)
public class FirstAspect {
    @Before("execution(* demo.JobApi.run(..))")
    public void before() {
        System.out.println("FIRST");
    }
}
~~~

và một aspect khác:

~~~java
@Aspect
@Component
@Order(20)
public class SecondAspect {
    @Before("execution(* demo.JobApi.run(..))")
    public void before() {
        System.out.println("SECOND");
    }
}
~~~

**Đây là các fragments cần đặt ở hai file tương ứng**, không phải mã hoàn chỉnh của chương trình. Với hai aspect có precedence khác nhau:

- `@Order(10)` có **precedence cao hơn** `@Order(20)` vì số nhỏ hơn.
- Hai `@Before` match cùng invocation và **không ném ngoại lệ** sẽ được gọi trên đường vào theo thứ tự precedence: **FIRST rồi SECOND**, sau đó tới target.
- Khi chạy code thật, Spring còn phải tạo bean/aspect/advisor và caller phải gọi qua **Spring AOP proxy**.

**Đặt `@Order` trên từng method advice trong một `@Aspect` không phải giải pháp được Spring tài liệu hóa để bảo đảm thứ tự giữa các advice cùng loại trong chính class đó.** Cách an toàn là **sắp thứ tự ở cấp aspect** hoặc **gom các bước cần thứ tự vào một advice**.

Cũng không dùng:

- Tên method `aFirst`/`zLast` để ép thứ tự.
- Vị trí method trong source.
- Thứ tự import hoặc thứ tự class files.
- Thứ tự xuất hiện trong log của một lần chạy.
- Annotation tự tạo không được Spring advisor chain đọc làm precedence.

Nếu `@Order` có giá trị **bằng nhau**, đừng coi thứ tự hai aspects là một hợp đồng ổn định. Muốn thứ tự cụ thể, cho chúng **hai mức precedence khác nhau**.

## 5. Thứ tự trên đường vào và đường ra

Spring AOP làm việc theo chuỗi interceptor quanh một method execution:

~~~text
Client
   |
   v
Aspect order=10 (ưu tiên cao)
   |
   v
Aspect order=20 (ưu tiên thấp hơn)
   |
   v
TARGET METHOD
   |
   v
Aspect order=20 (hoàn tất phía trong)
   |
   v
Aspect order=10 (hoàn tất phía ngoài)
   |
   v
Caller
~~~

Hệ quả:

- **Trên đường vào:** advice có precedence cao thường chạy **trước**.
- **Trên đường ra:** advice có precedence cao thường chạy **sau**, vì nó bao quanh phần phía trong.
- Đây là quy tắc trực giác của **lồng interceptor**, không nên suy ra rằng mọi advice đều chạy ở cả hai chiều. `@Before` chỉ xử lý trước; `@AfterReturning` chỉ chạy trên nhánh trả bình thường, v.v.

Với hai `@Around` nằm ở hai aspects:

~~~text
ORDER 10: around ENTER
  ORDER 20: around ENTER
    TARGET
  ORDER 20: around EXIT
ORDER 10: around EXIT
~~~

Nếu cả hai gọi `proceed()` đúng một lần và target trả về bình thường, thứ tự này được giải thích bằng cấu trúc lồng. Nếu aspect bên ngoài **không gọi `proceed()`**, advisor phía trong và target **không được đi tới**.

**Lưu ý:** Không dùng `@Order` để “buộc một `@AfterReturning` chạy như `@Before`”. `@Order` quyết định precedence giữa aspects; **loại advice** quyết định khi nào code chạy.

## 6. Precedence trong cùng @Aspect khi các loại advice khác nhau

Spring Framework 6.2 công bố precedence giữa **các loại advice khác nhau** trong một `@Aspect` (cao đến thấp):

1. `@Around`.
2. `@Before`.
3. `@After`.
4. `@AfterReturning`.
5. `@AfterThrowing`.

**Nhưng phải hiểu ngữ nghĩa thực thi, không đọc dãy trên như thứ tự in log tuyến tính.** Theo Spring, `@After` mang ngữ nghĩa kiểu **finally** và **thực tế được gọi sau `@AfterReturning` hoặc `@AfterThrowing`** trong cùng aspect.

Ví dụ minh họa một aspect có nhiều loại advice:

~~~java
@Aspect
@Component
public class TraceAspect {

    @Around("execution(* demo.JobApi.run(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("AROUND enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("AROUND exit");
        }
    }

    @Before("execution(* demo.JobApi.run(..))")
    public void before() {
        System.out.println("BEFORE");
    }

    @AfterReturning("execution(* demo.JobApi.run(..))")
    public void afterSuccess() {
        System.out.println("AFTER RETURNING");
    }

    @After("execution(* demo.JobApi.run(..))")
    public void afterFinally() {
        System.out.println("AFTER FINALLY");
    }
}
~~~

Đoạn này là **fragment class minh họa**, cần imports và service/app context. Với **target trả về bình thường, không có advice khác làm thay đổi flow**, có thể hiểu logic bao quanh như:

~~~text
AROUND enter
BEFORE
TARGET
AFTER RETURNING
AFTER FINALLY
AROUND exit
~~~

Nếu target ném exception, `@AfterReturning` không chạy, còn `@After` theo finally semantics vẫn chạy khi invocation đi tới phạm vi của nó. `@Around` có thể catch/transform exceptions nên phải xét cả mã của advice.

Điểm trọng tâm của bài không phải học thuộc một danh sách advice type chung, mà là **phân biệt thứ tự được Spring định nghĩa giữa các loại khác nhau với thứ tự *không được định nghĩa* giữa nhiều advice cùng loại trong một class**.

## 7. Ví dụ Maven chạy được: hai @Before ở hai aspects có thứ tự rõ ràng

Để có stdout **có thứ tự được bảo đảm**, ví dụ chính dùng:

- Một Spring service bean triển khai `JobApi`.
- `FirstBeforeAspect` là một `@Aspect` có `@Order(10)`.
- `SecondBeforeAspect` là một `@Aspect` khác có `@Order(20)`.
- Cả hai cùng có **một `@Before`**, match phương thức `JobApi.run(..)`.
- Client gọi qua proxy từ `AnnotationConfigApplicationContext`.

**Môi trường:** Java 17+, Maven 3.9+, Spring Framework 6.2.12 và AspectJ Weaver 1.9.24.

### 7.1. Cấu trúc dự án

~~~text
spring-aop-advice-order/
├── pom.xml
└── src/main/java/demo/
    ├── JobApi.java
    ├── JobService.java
    ├── FirstBeforeAspect.java
    ├── SecondBeforeAspect.java
    ├── AppConfig.java
    └── App.java
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-advice-order</artifactId>
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

`spring-context` cung cấp ApplicationContext và kéo theo các module Spring AOP cần thiết. `aspectjweaver` cho Spring đọc `@AspectJ` annotations/pointcut expressions. Không có AspectJ compiler hoặc weaving trong ví dụ.

### 7.3. JobApi.java

~~~java
package demo;

public interface JobApi {
    String run(String jobId);
}
~~~

Đây là contract công khai. Spring có thể tạo JDK dynamic proxy khi implementation có interface và không ép CGLIB.

### 7.4. JobService.java

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class JobService implements JobApi {

    @Override
    public String run(String jobId) {
        System.out.println("TARGET run " + jobId);
        return "done:" + jobId;
    }
}
~~~

`@Service` được component scan đăng ký trong Spring context. Code target chỉ in một dòng và trả String; không cần database/network để thấy thứ tự.

### 7.5. FirstBeforeAspect.java

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(10)
public class FirstBeforeAspect {

    @Before("execution(* demo.JobApi.run(..))")
    public void before() {
        System.out.println("BEFORE priority10");
    }
}
~~~

`@Order(10)` đặt ở **class aspect**. Advice này có precedence cao hơn aspect `@Order(20)`. Đừng hiểu `10` là “chạy mười lần”, “chờ mười mili giây” hoặc “thứ tự dòng 10”.

### 7.6. SecondBeforeAspect.java

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(20)
public class SecondBeforeAspect {

    @Before("execution(* demo.JobApi.run(..))")
    public void before() {
        System.out.println("BEFORE priority20");
    }
}
~~~

Cả hai `@Before` cùng match `JobApi.run(..)`, nhưng nằm ở **hai class `@Aspect` khác nhau**. Vì precedence tường minh nên có thể dự đoán thứ tự.

### 7.7. AppConfig.java

~~~java
package demo;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "demo")
@EnableAspectJAutoProxy
public class AppConfig {
}
~~~

`@ComponentScan` đăng ký service và hai aspects. `@EnableAspectJAutoProxy` tạo AOP advisor/proxy thích hợp. Nếu chỉ đặt `@Aspect` mà không đăng ký bean qua `@Component` hoặc `@Bean` thì Spring không tự đưa advice vào context.

### 7.8. App.java

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            JobApi jobs = context.getBean(JobApi.class);

            System.out.println(
                    "IS_PROXY " + AopUtils.isAopProxy(jobs));

            String result = jobs.run("J-17");
            System.out.println("RESULT " + result);
        }
    }
}
~~~

Caller lấy Spring-managed bean theo interface `JobApi`, không dùng `new JobService()` và không cast JDK proxy về concrete implementation class.

Chạy tại thư mục có `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

### 7.9. Stdout logic kỳ vọng

~~~text
IS_PROXY true
BEFORE priority10
BEFORE priority20
TARGET run J-17
RESULT done:J-17
~~~

Kết quả trên là **stdout logic kỳ vọng của ví dụ**, bỏ qua Maven/Spring logging. Hai dòng `BEFORE` có thứ tự dựa trên **`@Order` cấp aspect**, không phải thứ tự source methods.

Giải thích:

1. `IS_PROXY true`: Spring trả một AOP proxy vì advisor phù hợp với service.
2. `BEFORE priority10` chạy trước nhờ precedence cao hơn.
3. `BEFORE priority20` chạy tiếp.
4. `TARGET run J-17` chỉ xuất hiện sau hai before advices trả về bình thường.
5. `RESULT done:J-17` là giá trị do target trả về và proxy chuyển tiếp.

Nếu advice priority10 **ném exception**, priority20 và target có thể không được đi tới ở đường gọi này. Precedence là **trình tự khi control flow tiếp tục**, không phải cam kết mọi advice sẽ luôn chạy bất kể exception.

## 8. Phản ví dụ: hai @Before trong cùng một aspect

Giả sử bạn **thay thế** hai aspect `FirstBeforeAspect` và `SecondBeforeAspect` bằng một aspect:

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AmbiguousBeforeAspect {

    @Before("execution(* demo.JobApi.run(..))")
    public void alpha() {
        System.out.println("ALPHA");
    }

    @Before("execution(* demo.JobApi.run(..))")
    public void beta() {
        System.out.println("BETA");
    }
}
~~~

Đây là **file riêng có thể dùng khi bạn đổi cấu trúc demo**. Để test, **loại hai original aspect beans khỏi context** hoặc tắt registration của chúng rồi mới đăng ký `AmbiguousBeforeAspect`. Nếu đồng thời giữ cả ba, có thêm advice và stdout sẽ khác.

Bạn có thể quan sát một trong hai cách sắp xếp:

~~~text
ALPHA
BETA
TARGET run J-17
~~~

hoặc:

~~~text
BETA
ALPHA
TARGET run J-17
~~~

**Hai đoạn trên chỉ là các khả năng minh họa, không phải “expected output” độc nhất.** Tài liệu Spring không cam kết chọn phương án nào. Nếu vài lần chạy luôn cho ra `ALPHA` rồi `BETA`, đó vẫn **không phải hợp đồng** để production dựa vào.

Việc thêm `@Order(1)` cho **class `AmbiguousBeforeAspect`** chỉ ảnh hưởng precedence của aspect đó **so với aspects khác**, không biến `alpha()` và `beta()` thành một trình tự xác định trong cùng class.

## 9. Phương án 1: gộp thành một advice và gọi helper tuần tự

Nếu hai bước **thuộc cùng một concern** và có dependency rõ ràng “phải kiểm tra trước khi audit”, giải pháp đơn giản nhất là một advice:

~~~java
@Aspect
@Component
public class CombinedChecksAspect {

    @Before("execution(* demo.JobApi.run(..))")
    public void validateThenAudit() {
        validate();
        audit();
    }

    private void validate() {
        System.out.println("VALIDATE");
    }

    private void audit() {
        System.out.println("AUDIT");
    }
}
~~~

Đây là **fragment class** cần imports `@Aspect`, `@Component` và `@Before`. Nó không tạo hai advice cùng loại nữa; có **một `@Before`** và hai Java helper calls theo thứ tự **được Java language semantics bảo đảm**:

~~~text
VALIDATE
AUDIT
TARGET run ...
~~~

Nếu `validate()` ném exception, `audit()` không chạy và target có thể bị ngăn, phù hợp với chính sách “không audit một tác vụ bị chặn”, nếu đó thật sự là yêu cầu.

Nhưng nếu audit **phải ghi cả những lần validation thất bại**, bạn cần thiết kế `try/catch/finally` theo ý định nghiệp vụ; **không** chỉ dựa vào thứ tự hay loại advice để tự có behavior mong muốn.

**Ưu điểm gộp:** ít cấu hình order, logic nội bộ dễ đọc, dễ unit test với helper/dependency injection.

**Đánh đổi:** hai trách nhiệm nếu thuộc hai module độc lập có thể trở nên gắn chặt trong một aspect; khi đó tách thành aspects khác nhau có thể hợp lý hơn.

## 10. Phương án 2: tách aspects để có thứ tự concern rõ ràng

Khi validation và audit là hai concerns độc lập:

~~~text
ValidationAspect @Order(10)
           |
           v
AuditAspect @Order(20)
           |
           v
Business service
~~~

Đây chính là mô hình project ở mục 7. Mỗi aspect có mục tiêu, test và owner riêng; Spring sử dụng precedence giữa aspects.

Mẫu khai báo:

~~~java
@Aspect
@Component
@Order(10)
class ValidationAspect {
    @Before("execution(* demo.JobApi.run(..))")
    public void check() {
        // validation
    }
}

@Aspect
@Component
@Order(20)
class AuditAspect {
    @Before("execution(* demo.JobApi.run(..))")
    public void record() {
        // audit
    }
}
~~~

Đây là **fragment minh họa gồm hai class package-private**, cần imports và khai báo trong các file phù hợp. Không nên chép thêm vào project mục 7 khi chưa loại original aspects, vì nó tạo thêm advisors.

Dùng **giá trị order khác nhau** để thể hiện ranh giới. Nếu công việc yêu cầu security phải chạy trước một action có side effect, hãy kiểm tra cả **advisor ordering với Spring Security/transaction/cache aspects**, không chỉ so hai aspects tự viết.

**Lưu ý lớn:** `@Order` có precedence trên Spring aspects nhưng không định nghĩa trọn vẹn thứ tự của mọi BeanPostProcessor, servlet filter, method security interceptor hoặc transactional resource lifecycle. Mỗi infrastructure layer có cách tích hợp riêng; cần integration test trên context thật.

## 11. Phương án 3: một @Around thực hiện nhiều bước có chủ đích

Khi yêu cầu vừa kiểm soát thứ tự “trước” và “sau”, một `@Around` có thể chứa trình tự rõ ràng:

~~~java
@Around("execution(* demo.JobApi.run(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("STEP-1 validate");
    System.out.println("STEP-2 start timer");

    try {
        Object result = pjp.proceed();
        System.out.println("STEP-3 success audit");
        return result;
    } finally {
        System.out.println("STEP-4 finish");
    }
}
~~~

Đây là **fragment method trong `@Aspect`**, cần imports. Khi target trả bình thường, thứ tự logic do **Java statements** bảo đảm:

~~~text
STEP-1 validate
STEP-2 start timer
TARGET ...
STEP-3 success audit
STEP-4 finish
~~~

Nếu `pjp.proceed()` ném exception, `STEP-3 success audit` không chạy nhưng `finally` vẫn thực thi.

Cần cẩn trọng:

- `@Around` có thể short-circuit nếu không gọi proceed, khiến target và advisor phía trong bị bỏ qua.
- `proceed()` có thể được gọi nhiều lần, làm target/side effects lặp lại.
- Advice trả `Object` phải chuyển tiếp đúng return contract.
- Không dùng `@Around` chỉ để ép thứ tự khi một `@Before` duy nhất đã đủ.

Gộp nhiều bước vào một method là một cách diễn đạt yêu cầu **trình tự cứng**, nhưng làm logic AOP phức tạp hơn khi nó vừa ghi log, vừa cache, vừa retry, vừa quản lý transaction.

## 12. @After, @AfterReturning, @AfterThrowing và thứ tự cần hiểu

Nếu hai advice **cùng loại** trong cùng `@Aspect`, ví dụ:

~~~java
@AfterReturning("execution(* demo.JobApi.run(..))")
public void recordSuccess() {
    System.out.println("SUCCESS");
}

@AfterReturning("execution(* demo.JobApi.run(..))")
public void updateMetric() {
    System.out.println("METRIC");
}
~~~

thì **SUCCESS trước METRIC** không phải bảo đảm. Nếu metric phải được ghi sau audit thành công, gộp thành một `@AfterReturning` hoặc tách thành aspects có `@Order`.

Với hai `@AfterThrowing` cùng match một join point, nguyên tắc tương tự: **thứ tự giữa chúng trong cùng aspect không xác định**. Không dùng thứ tự source method để giả định handler nào “xử lý exception trước”.

Với hai `@After` trong cùng aspect, cũng **không xác định thứ tự** giữa hai method advice `@After` ấy.

**Khác loại** có semantics riêng:

- `@AfterReturning`: chạy khi method execution hoàn tất **bình thường**.
- `@AfterThrowing`: chạy khi invocation ném exception phù hợp; không nhất thiết chạy nếu exception bị `@Around` phía trong bắt và chuyển thành giá trị bình thường.
- `@After`: kiểu finally, chạy sau execution khi invocation đã được advice đi tới, **bất kể hoàn tất bình thường hay ngoại lệ**, ngoại trừ các đường gọi bị advice ngoài short-circuit trước khi nó tham gia.
- `@Around`: tự quyết định có gọi `proceed()` và có xử lý/biến đổi kết quả/exception hay không.

**Không nên viết một bài test assert một danh sách log toàn cục cố định** nếu context có nhiều aspects cùng loại không đặt order. Thứ tự khác loại có quy tắc nhưng thứ tự các concerns và exception flow phải được xét theo advisor chain thực.

## 13. Tại sao @After thường in sau @AfterReturning?

Tài liệu Spring Framework 6.2 phân biệt **precedence assignment** với **thời điểm callback**. `@After` có **after finally semantics**, do đó trong cùng aspect nó **thực tế chạy sau** `@AfterReturning` hoặc `@AfterThrowing` của invocation tương ứng.

Nếu đọc thứ tự precedence từ cao đến thấp:

~~~text
@Around > @Before > @After > @AfterReturning > @AfterThrowing
~~~

rồi vẽ ra:

~~~text
TARGET
@After
@AfterReturning
~~~

thì đó là cách diễn giải **không đúng** thứ tự callback trong Spring cho trường hợp cùng aspect. Precedence quy định interceptor lồng nhau; `@After` chạy ở nhánh finally khi continuation trong phạm vi của nó kết thúc.

Với câu hỏi của bài này, cần nhớ hai kết luận riêng:

1. **Các loại advice khác nhau:** Spring có quy tắc precedence/semantics.
2. **Nhiều advice cùng loại trong cùng aspect:** **không có bảo đảm thứ tự**.

Không dùng quy tắc loại advice để giải quyết hai `@Before` hoặc hai `@After` có cùng type.

## 14. Trường hợp hai aspects không khai báo @Order

Ví dụ hai aspects đều không khai báo order:

~~~java
@Aspect
@Component
class LoggingAspect {
    @Before("execution(* demo.JobApi.run(..))")
    public void before() {
        System.out.println("LOGGING");
    }
}

@Aspect
@Component
class TrackingAspect {
    @Before("execution(* demo.JobApi.run(..))")
    public void before() {
        System.out.println("TRACKING");
    }
}
~~~

Đây là fragment gồm **hai top-level class riêng**; cần imports và Spring config. Hai aspects khác nhau vẫn có thể **không có thứ tự được bảo đảm** nếu không gán precedence.

Không đủ để nói “Spring scan `LoggingAspect` trước nên LOGGING chắc chạy trước”. Component scanning hay alphabet của class names **không phải một hợp đồng ordering giữa các aspects**.

Thay bằng:

~~~java
@Aspect
@Component
@Order(10)
class LoggingAspect {
    // ...
}

@Aspect
@Component
@Order(20)
class TrackingAspect {
    // ...
}
~~~

Đây là **mẫu khai báo**, cần thêm advice bodies từ đoạn trước nếu áp dụng. `@Order(10)` được ưu tiên cao hơn `@Order(20)` trên đường vào.

## 15. Nếu hai aspects có cùng giá trị @Order

Một cấu hình dễ gây hiểu nhầm:

~~~java
@Aspect
@Component
@Order(100)
class AspectA {
    // ...
}

@Aspect
@Component
@Order(100)
class AspectB {
    // ...
}
~~~

Hai aspects được đặt **cùng priority 100**. Đừng đọc con số ấy như một số thứ tự duy nhất. Khi có tie, không dựa vào thứ tự kết quả tình cờ để đưa ra yêu cầu business “A trước B”.

Muốn một contract rõ ràng:

~~~java
@Aspect
@Component
@Order(100)
class AspectA {
    // ...
}

@Aspect
@Component
@Order(200)
class AspectB {
    // ...
}
~~~

Class AspectA có precedence cao hơn AspectB. Các con số có thể chọn theo convention của module; không nhất thiết phải là 1 và 2, miễn quan hệ so sánh rõ ràng.

Trong hệ thống lớn, tránh dùng số order rải rác ở nhiều modules mà không có một tài liệu quy ước. Có thể tạo constants như `SECURITY_ORDER` và `AUDIT_ORDER` nếu muốn thống nhất, nhưng phải hiểu advisors từ Spring framework/starter khác cũng có thứ tự riêng.

## 16. Khi advice trước có ngoại lệ hoặc around short-circuit

Thứ tự được bảo đảm **không đồng nghĩa tất cả advice nhất định phải chạy**.

### 16.1. @Before ưu tiên cao ném exception

~~~text
@Order(10) @Before: kiểm tra quyền -> throw AccessDenied
@Order(20) @Before: ghi dấu sự kiện
TARGET: xử lý nghiệp vụ
~~~

Nếu advice ưu tiên cao ném exception, chain có thể dừng trước advice ưu tiên thấp và target. Không viết test bắt buộc `@Order(20)` chạy ở tình huống exception chặn sớm.

### 16.2. @Around ưu tiên cao bỏ qua proceed

~~~java
@Around("execution(* demo.JobApi.run(..))")
public Object gate(ProceedingJoinPoint pjp) throws Throwable {
    if (maintenanceMode) {
        return "maintenance";
    }
    return pjp.proceed();
}
~~~

Đây là **fragment** cần `maintenanceMode` và imports thích hợp. Nếu `@Around` ở phía ngoài trả về trước mà **không gọi `proceed()`**, các advice nằm phía trong cùng target có thể **không được kích hoạt**.

### 16.3. Hai @Around cùng loại trong một @Aspect

Nếu cùng một class có hai `@Around` match cùng operation mà một method đôi khi return sớm, thứ tự chưa được bảo đảm có thể ảnh hưởng cực lớn: method nào được bọc ngoài quyết định code nào có cơ hội chạy.

Trường hợp này **đặc biệt nên** gộp thành một around advice hoặc tách thành aspects có order rõ ràng và integration tests. Không coi hai `@Around` là “hai handlers độc lập chắc chắn đều sẽ được gọi”.

## 17. Sự khác biệt giữa @Order và @Priority/Ordered

Trong Spring AOP advice ordering:

- `@Order(value)`: cách phổ biến gán thứ tự cho **class aspect** như demo.
- `Ordered`: aspect có thể implement `org.springframework.core.Ordered` và cung cấp `getOrder()`.
- **Giá trị số càng nhỏ → precedence càng cao**.
- Khi advice nằm trong **cùng class aspect và cùng loại**, thứ tự giữa chúng vẫn **không xác định**.
- Một bean có thể chịu nhiều loại ordering trong Spring context (BeanPostProcessor, event listener, transaction interceptor…). Không suy luận tất cả cùng một loại contract.

Ví dụ skeleton:

~~~java
@Aspect
@Component
public class OrderedAspect implements Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Before("execution(* demo.JobApi.run(..))")
    public void before() {
        System.out.println("ORDERED ASPECT");
    }
}
~~~

Đây là **fragment class**, cần import `org.springframework.core.Ordered` và các annotations. `Ordered` là cách thay thế `@Order` trên aspect trong ví dụ; không nên đồng thời sao chép thêm vào project runnable nếu muốn giữ expected stdout.

Nếu yêu cầu order dựa vào runtime config, implement `Ordered` có thể hữu dụng. Nhưng dynamic ordering phức tạp dễ khó debug; dùng constants hoặc `@Order` tường minh thường đủ.

## 18. XML schema AOP có quy tắc riêng

Bài này tập trung vào `@Aspect` annotation style, nhưng cần tránh nhầm với Spring **schema-based AOP**:

~~~xml
<aop:aspect id="example" ref="exampleBean">
    <aop:before pointcut-ref="serviceOp" method="one"/>
    <aop:before pointcut-ref="serviceOp" method="two"/>
</aop:aspect>
~~~

Đây chỉ là **XML fragment**, chưa phải file Spring XML hợp lệ đầy đủ. Tài liệu Spring ghi nhận rằng **trong cùng một `<aop:aspect>` của schema-based AOP**, precedence được xác định theo **thứ tự các phần tử advice được khai báo**. Quy tắc này **khác** annotation-style `@Aspect` dùng Java reflection.

**Không lấy thứ tự XML elements để chứng minh thứ tự hai annotated Java methods.** Nếu đang dùng `@Aspect` trên Spring bean, hãy áp dụng quy tắc ở các phần trước. Nếu đang dùng schema-based AOP, xem đúng phần tài liệu dành cho XML configuration.

## 19. Kiểm thử Spring AOP ordering đúng cách

Một bộ test đáng tin nên phân biệt:

- **Trường hợp có order được định nghĩa:** test output order cụ thể.
- **Trường hợp order không được định nghĩa:** không hardcode một thứ tự tình cờ; test rằng cả hai advices **đã chạy** khi được phép chạy, nhưng đừng kiểm tra vị trí tương đối giữa chúng.
- **Trường hợp không có proceed/exception:** test rằng chỉ các advice trong đường điều khiển được thực thi.
- **Trường hợp nhiều advisors:** kiểm tra cả application context thực tế, không chỉ một aspect unit test isolated.

### 19.1. Test project mục 7

Giả sử lấy biến `jobs` từ `ApplicationContext`:

~~~java
String result = jobs.run("T-1");

if (!"done:T-1".equals(result)) {
    throw new AssertionError("Wrong result");
}
~~~

Đoạn này là **fragment kiểm tra kết quả**, không phải một class độc lập. Để assert thứ tự `BEFORE priority10` và `BEFORE priority20`, tốt hơn là inject một `TraceRecorder` vào hai aspects, lưu events và so thứ tự trong integration test, thay vì dựa vào console log dễ chịu ảnh hưởng logging từ hệ thống khác.

### 19.2. TraceRecorder cho integration test

Một recorder tối giản:

~~~java
@Component
public class TraceRecorder {
    private final List<String> events = new CopyOnWriteArrayList<>();

    public void record(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
~~~

Đây là **fragment class**, cần imports `java.util.List`, `java.util.concurrent.CopyOnWriteArrayList` và `org.springframework.stereotype.Component`. Nó có thể được hai aspects inject qua constructor và ghi events.

Sau một lời gọi hợp lệ, một test có thể assert:

~~~java
List<String> expected = List.of(
        "priority10",
        "priority20",
        "target"
);

if (!expected.equals(recorder.snapshot())) {
    throw new AssertionError("Incorrect advice order");
}
~~~

Lưu ý: để đoạn này có ý nghĩa, target cũng phải được sửa để record event `target`. Nếu project thực có những advisors khác chặn exception hoặc ghi thêm events, kỳ vọng phải được điều chỉnh theo **chain thực**. Những fragments này minh họa kỹ thuật kiểm thử chứ **không phải bản source chạy độc lập** đã được tạo ở mục 7.

### 19.3. Không nên test undefined order bằng một giá trị cố định

Nếu chỉ có `AmbiguousBeforeAspect` với hai advices `alpha` và `beta` cùng loại, một test như sau là sai về giả định:

~~~java
assertEquals(
    List.of("ALPHA", "BETA"),
    recorder.snapshot()
);
~~~

Đây là **fragment JUnit**, cần JUnit dependency và recorder trong test. Nó có thể pass trên máy hiện tại nhưng fail ở môi trường khác dù Spring AOP vẫn đúng contract. Nếu chưa có order, chỉ test sự **hiện diện** của cả hai events (nếu chúng thực thi bình thường), không yêu cầu thứ tự.

## 20. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng giải quyết |
| --- | --- | --- |
| Hai `@Before` đổi thứ tự sau build khác | Cùng loại trong cùng `@Aspect` không có thứ tự bảo đảm | Gộp advice hoặc tách aspects có `@Order` |
| `@Order` trên class nhưng hai method cùng loại vẫn đảo | `@Order` không xếp thứ tự nội bộ cùng loại | Một advice với helper calls tuần tự |
| Hai aspects chạy “theo alphabet” trên dev nhưng khác ở CI | Chưa gán precedence giữa aspects | `@Order` khác nhau |
| Hai aspects đều `@Order(5)` | Tie precedence, không thể giả định thứ tự | Dùng giá trị khác nhau |
| `@After` được mong chạy trước `@AfterReturning` | Hiểu sai precedence thành callback order | Nhớ `@After` có finally semantics |
| Aspect order thấp hơn lại chạy trước ở đường ra | Precedence cao bọc ngoài nên thoát sau | Vẽ interceptor nesting |
| Advice ưu tiên thấp không chạy | Advice ngoài ném exception hoặc không proceed | Kiểm tra exception/continuation |
| Target không chạy dù @Before matched | `@Around` ở ngoài đã short-circuit | Kiểm tra code around và order |
| Method private/final không được advice | Giới hạn Spring proxy | Thiết kế method interceptable |
| Advice không chạy trong `this.method()` | Self-invocation bypass proxy | Gọi qua Spring-managed dependency |
| Có `@Aspect` nhưng không có advice | Aspect chưa là Spring bean hoặc AOP chưa bật | `@Component`/`@Bean` và `@EnableAspectJAutoProxy` |
| Cùng một business operation in nhiều log | Nhiều advisors cùng pointcut hoặc method thực sự gọi nhiều lần | Quan sát advisor/pointcut và call path |
| Unit test ordering pass còn integration test fail | Context thật có additional advisors và ordering | Test với Spring context đúng production |
| Copy thứ tự XML vào annotation style | Schema-based AOP có quy tắc khác | Áp dụng tài liệu đúng cấu hình |
| Hai `@Around` trong một aspect làm side effect khó hiểu | Nested order không bảo đảm và proceed có thể bỏ qua/lặp | Gộp thành một around hoặc split + @Order |
| Không biết security hay transaction chạy trước | Các infrastructure advisors có order riêng | Kiểm chứng precedence và integration behavior |
| Thay JDK proxy sang CGLIB để “sửa thứ tự” | Loại proxy không tạo source-declaration order | Sửa thiết kế aspect/advice, không đổi proxy chỉ vì ordering |

## 21. Quy trình quyết định khi nhiều advice cùng match

**Bước 1 — Xác định join point.** Các pointcuts có thật sự cùng chọn **một Spring-managed method execution** không? Nếu không, không có vấn đề ordering tại cùng invocation.

**Bước 2 — Xác định loại advice.** Hai `@Before` hay `@AfterReturning` là cùng loại; `@Before` và `@Around` là khác loại.

**Bước 3 — Xác định nơi khai báo.** Cùng class `@Aspect`, hay các class aspects khác nhau?

**Bước 4 — Xem yêu cầu business.** Nếu thứ tự chỉ mang tính thẩm mỹ logging và không có dependency, có thể không cần ép order. Nếu audit/security/validation/retry/cache phụ thuộc kết quả của nhau, thứ tự phải tường minh.

**Bước 5 — Chọn cách sửa.**

- Hai thao tác phụ thuộc nhau trong **một concern** → **một advice** với các bước Java theo thứ tự.
- Hai concerns độc lập → **tách aspects** và cấp precedence qua `@Order` hoặc `Ordered`.
- Có nhiều advice types → hiểu Spring precedence và actual callback semantics, nhất là `@After`.
- Có third-party advisors → xem configuration/order của chúng; đừng chỉ đặt order trên aspects riêng mà bỏ qua framework infrastructure.

**Bước 6 — Dùng integration test.** Assert những thứ tự **được bảo đảm**, và test nhánh exception, retry, short-circuit.

**Bước 7 — Tài liệu hóa convention.** Giữ một thứ tự ưu tiên chung cho security, validation, audit, transaction, tracing nếu business yêu cầu; tránh các values trùng không có chủ đích.

## 22. Checklist trước khi đưa vào production

1. Có nhiều advice cùng type và cùng match một join point không?
2. Chúng có nằm trong cùng `@Aspect` class không?
3. Nếu có, đã tránh dựa vào thứ tự Java source/reflection chưa?
4. Nếu logic cần thứ tự, đã gộp trong một advice hoặc tách aspects chưa?
5. Nếu tách aspects, mỗi aspect có `@Order`/`Ordered` riêng, không tie không?
6. Đã hiểu **giá trị order nhỏ hơn là precedence cao hơn**?
7. Có kiểm tra thứ tự trên đường vào và đường ra thay vì chỉ một chiều không?
8. Với `@After` và `@AfterReturning`, đã phân biệt finally semantics chưa?
9. Nếu `@Around` bỏ proceed hoặc throw, những advice phía trong có bị bỏ qua không?
10. Có tự gọi `this.method()` bỏ qua Spring proxy không?
11. Có advisor khác của Spring Security, transaction hoặc cache tham gia context không?
12. Có test bằng Spring ApplicationContext đầy đủ và actual proxy type không?
13. Có test nhánh thành công và ngoại lệ, không chỉ một happy path?
14. Có bị nhầm schema-based XML AOP ordering với annotation-based `@Aspect` không?
15. README/test có tránh khẳng định một stdout cố định cho các advice cùng loại **không được sắp thứ tự** không?

## 23. Câu hỏi tự đánh giá

**1. Hai `@Before` trong cùng class `@Aspect` có chắc chạy theo vị trí khai báo không?**

Không. Nếu cả hai cùng match một join point, Spring Framework không định nghĩa thứ tự giữa chúng.

**2. Một class `@Aspect` có `@Order(1)` thì hai `@Before` trong class ấy được sắp thứ tự nội bộ không?**

Không. `@Order` đặt precedence cấp aspect so với những aspects khác; nó không biến thứ tự hai methods cùng loại thành một contract.

**3. Cách đơn giản nhất khi phải validate rồi audit theo thứ tự cứng là gì?**

Gộp thành một advice và gọi `validate()` rồi `audit()` theo thứ tự Java, nếu đó thực sự là một concern phù hợp.

**4. Khi nên tách aspects và dùng @Order?**

Khi hai concerns tương đối độc lập nhưng có precedence rõ ràng giữa chúng.

**5. Giữa `@Order(10)` và `@Order(20)`, aspect nào ưu tiên cao hơn?**

`@Order(10)`, vì trong Spring giá trị order nhỏ hơn có precedence cao hơn.

**6. Trên đường ra của hai `@Around` nested, aspect ưu tiên cao hoàn tất trước hay sau?**

Thường hoàn tất **sau** aspect ưu tiên thấp hơn, vì nó bọc ngoài, miễn cả hai gọi proceed và không thay đổi flow theo cách khác.

**7. `@After` trong cùng aspect có chạy trước `@AfterReturning` chỉ vì precedence list viết @After trước không?**

Không. `@After` có finally semantics và thực tế được gọi sau `@AfterReturning`/`@AfterThrowing` khi những advice đó áp dụng.

**8. Nếu hai aspects không có `@Order`, Spring cam kết thứ tự nào?**

Không có thứ tự được bảo đảm, trừ khi precedence được cấu hình qua cơ chế khác.

**9. Hai aspects cùng `@Order(100)` có bảo đảm theo tên class không?**

Không. Nếu thứ tự có ý nghĩa, phải dùng precedence riêng hoặc gộp logic phù hợp.

**10. Nếu around advice ưu tiên cao không gọi `proceed()`, before advice ở phía trong có được chạy không?**

Không được continuation đi tới, vì around đã short-circuit trước khi gọi vào chain phía trong.

**11. Vì sao chạy chương trình 1.000 lần thấy cùng order vẫn không đủ?**

Vì behavior có thể ổn định một cách tình cờ nhưng không được Spring API/tài liệu bảo đảm, nên không thể coi là contract qua môi trường khác.

**12. Schema-based AOP có cùng quy tắc thứ tự advice method annotation style không?**

Không hoàn toàn. Với `<aop:aspect>` XML, thứ tự khai báo các advice elements có vai trò trong precedence; quy tắc này không áp dụng nguyên xi cho Java `@Aspect`.

## 24. Tài liệu Spring chính thức

- **Spring Framework 6.2 — Declaring Advice / Advice Ordering:** https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html
- **Spring Framework — Declaring an Aspect:** https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html
- **Spring Framework — @AspectJ-style AOP Support:** https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- **Spring Framework — Proxying Mechanisms:** https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- **Spring Framework 6.2 — Schema-based AOP / Advice Ordering:** https://docs.spring.io/spring-framework/reference/6.2/core/aop/schema.html
- **Spring Framework — Order annotation:** https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/annotation/Order.html
- **Spring Framework — Ordered interface:** https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/Ordered.html

**Kết luận:** Trong Spring `@AspectJ`-style AOP, **nhiều advice cùng loại trong một `@Aspect` áp dụng cho cùng method execution không có thứ tự được bảo đảm**. Để tạo trình tự nghiệp vụ đáng tin cậy, **gộp các bước vào một advice**, hoặc **tách thành nhiều aspects và chỉ định precedence bằng `@Order`/`Ordered`**. Khi nhiều loại advice cùng tham gia, hãy xét **đường vào/đường ra, finally semantics và `proceed()`**, thay vì coi thứ tự source code là quy tắc của Spring.

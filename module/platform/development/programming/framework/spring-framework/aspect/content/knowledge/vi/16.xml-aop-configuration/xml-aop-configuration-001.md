# Namespace `aop` và đăng ký bean phụ thuộc trong Spring AOP bằng XML

## Mục tiêu

Trong một ứng dụng Spring dùng cấu hình XML, viết một lớp chứa phương thức advice vẫn chưa đủ để lời gọi nghiệp vụ được Spring AOP chặn. Cần phối hợp đúng **XML namespace `aop`**, cơ chế tạo proxy và các bean liên quan: bean nghiệp vụ (target), bean chứa advice, các bean mà aspect phụ thuộc, và bean advice riêng khi dùng `<aop:advisor>`.

Bài này tập trung vào Spring AOP trong Spring Framework: đọc một cấu hình XML, xác định bean nào cần đăng ký, hiểu Spring nối pointcut với advice ra sao, và kiểm tra hành vi của proxy. Đây là cấu hình **Spring AOP dựa trên proxy**, không phải cấu hình AspectJ bytecode weaving.

Sau bài học, bạn có thể:

- Khai báo `xmlns:aop` và `spring-aop.xsd` hợp lệ trong `<beans>`.
- Dùng `<aop:config>`, `<aop:pointcut>`, `<aop:aspect>`, `<aop:around>` với một Java class advice thông thường.
- Đăng ký target, aspect và bean dependency bằng `<bean>` / `ref` / `constructor-arg`, không nhầm `ref` của aspect với `pointcut-ref` hay `advice-ref`.
- Phân biệt cấu hình aspect kiểu XML schema và cấu hình lớp `@Aspect` qua `<aop:aspectj-autoproxy/>`.
- Chẩn đoán bean chưa được quản lý, advice không chạy, tham chiếu sai, self-invocation và lựa chọn kiểu proxy.

## 1. Khai báo namespace `aop` trong Spring XML

Một file cấu hình XML sử dụng `aop:` cần khai báo namespace và địa chỉ schema:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <!-- Định nghĩa bean Spring và cấu hình AOP tại đây. -->

</beans>
~~~

Ở đây:

1. `xmlns` mặc định trỏ đến beans namespace để dùng `<bean>`, `<constructor-arg>`, `<property>`.
2. `xmlns:aop` khai báo prefix `aop` gắn với Spring AOP namespace.
3. `xsi:schemaLocation` ghép từng namespace URI với URL XSD tương ứng. Thiếu cặp schema của `aop` có thể làm XML không được parser/schema validator hiểu như mong đợi.
4. Namespace `aop` **cung cấp cú pháp cấu hình**; nó không tự tạo aspect hay target bean chỉ vì có `xmlns:aop`.

Trong dự án dùng Maven, tối thiểu cho ví dụ ở phần sau có `spring-context`, `spring-aop` và `aspectjweaver` tương thích. Với Spring AOP kiểu `@AspectJ` và pointcut AspectJ expression, thư viện AspectJ phục vụ parsing/matching, trong khi runtime interception vẫn là Spring proxy; ví dụ không cần AspectJ compiler hoặc load-time weaving.

## 2. Hai con đường khai báo Spring AOP bằng XML

Spring XML hỗ trợ hai cơ chế khai báo AOP. Với **schema-based AOP**, `<aop:config>` chứa pointcut và các phần tử advice; bean Java chứa method advice có thể là POJO, không cần `@Aspect`. Với **@AspectJ style bật bằng XML**, `<aop:aspectj-autoproxy/>` nhận diện các bean đã đăng ký có `@Aspect` và annotation `@Before`, `@Around`... trong Java.

| Cấu hình | Nơi khai báo quy tắc | Điều bắt buộc |
| --- | --- | --- |
| `<aop:config>` / `<aop:aspect ref="auditBean">` | Pointcut, loại advice và method mapping nằm ở XML | Bean target và bean chứa Java advice method |
| `<aop:aspectj-autoproxy/>` | Pointcut và advice annotation nằm trong `@Aspect` Java | Target bean, aspect bean, hạ tầng @AspectJ được bật |

Trong cả hai trường hợp, caller phải đi qua **Spring AOP proxy**. Không đăng ký cùng một hành vi hai lần qua hai cơ chế. Bài **“aop:aspectj-autoproxy cho aspect dùng annotation”** kiểm chứng riêng cách bật @Aspect và đăng ký aspect bean.

## 3. Mối quan hệ giữa các bean và thẻ AOP

Một sơ đồ điển hình:

~~~text
Spring ApplicationContext
    |
    +-- <bean id="orderService" class="...DefaultOrderService"/>
    |       |
    |       +--> target được Spring AOP proxy nếu pointcut match
    |
    +-- <bean id="auditFormatter" class="...AuditFormatter"/>
    |       |
    |       +--> bean phụ thuộc được inject cho auditAspectBean
    |
    +-- <bean id="auditAspectBean" class="...AuditAspect">
    |       +-- constructor-arg ref="auditFormatter"
    |
    +-- <aop:config>
            +-- <aop:pointcut id="serviceCalls" .../>
            +-- <aop:aspect ref="auditAspectBean">
                    +-- <aop:around pointcut-ref="serviceCalls"
                                    method="around"/>
~~~

Phân biệt các thuộc tính:

| Thành phần | Tham chiếu đến | Tác dụng |
| --- | --- | --- |
| `<aop:aspect ref="auditAspectBean">` | **Spring bean ID** chứa method advice | Chỉ định đối tượng triển khai aspect |
| `<aop:around method="around">` | **Tên method** trên bean aspect | Chọn implementation của around advice |
| `<aop:around pointcut-ref="serviceCalls">` | **Pointcut ID**, không phải bean ID | Chọn join point sẽ áp dụng advice |
| `<constructor-arg ref="auditFormatter">` | **Spring bean ID** hỗ trợ aspect | Inject dependency vào aspect |
| `<aop:advisor advice-ref="interceptorBean">` | **Spring bean ID** implement advice interface | Cấu hình advisor kiểu Spring AOP API |

Nói cách khác, ID được dùng trong cùng một chuỗi ký tự không có nghĩa đó là cùng loại đối tượng. Spring quản lý lifecycle và dependency injection cho các bean, còn `<aop:config>` nối pointcut với advice để áp dụng proxy.

## 4. Ví dụ chạy được: `<aop:config>` với bean phụ thuộc

Ví dụ sử dụng Java 17, Spring Framework 6.1.15, Maven, và **không dùng `@Aspect`**. Aspect nhận một bean `AuditFormatter` qua constructor để minh họa chính xác quan hệ phụ thuộc.

Cấu trúc:

~~~text
spring-xml-aop-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── Application.java
        │       ├── OrderService.java
        │       ├── DefaultOrderService.java
        │       ├── AuditFormatter.java
        │       └── AuditAspect.java
        └── resources/
            └── applicationContext.xml
~~~

### 4.1. Maven dependencies

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-xml-aop-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.15</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.1.15</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Application</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. Interface và target bean

**src/main/java/demo/OrderService.java**

~~~java
package demo;

public interface OrderService {
    String place(String orderId);
    String reject(String orderId);
}
~~~

**src/main/java/demo/DefaultOrderService.java**

~~~java
package demo;

public class DefaultOrderService implements OrderService {
    @Override
    public String place(String orderId) {
        System.out.println("service: place " + orderId);
        return "accepted " + orderId;
    }

    @Override
    public String reject(String orderId) {
        throw new IllegalArgumentException("rejected " + orderId);
    }
}
~~~

Lớp `DefaultOrderService` không cần `@Service` vì sẽ được đăng ký bằng `<bean>` trong XML. `OrderService` giúp ví dụ dùng JDK interface-based proxy.

### 4.3. Bean phụ thuộc và Java class triển khai advice

**src/main/java/demo/AuditFormatter.java**

~~~java
package demo;

public class AuditFormatter {
    public String label(String method) {
        return "audit: " + method;
    }
}
~~~

**src/main/java/demo/AuditAspect.java**

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;

public class AuditAspect {
    private final AuditFormatter formatter;

    public AuditAspect(AuditFormatter formatter) {
        this.formatter = formatter;
    }

    // Được aop:around trong XML gọi; không cần @Around/@Aspect.
    public Object around(ProceedingJoinPoint joinPoint) throws Throwable {
        String operation = joinPoint.getSignature().getName();
        System.out.println(formatter.label("before " + operation));

        try {
            Object result = joinPoint.proceed();
            System.out.println(formatter.label("after " + operation));
            return result;
        } catch (Throwable ex) {
            System.out.println(formatter.label("error " + operation
                    + " " + ex.getClass().getSimpleName()));
            throw ex;
        }
    }
}
~~~

`AuditAspect` là Spring bean chứa callback được XML trỏ đến. Dependency `AuditFormatter` được constructor-inject, không tạo thủ công bằng `new` trong aspect. Giữ `formatter` là `final` giúp quan hệ phụ thuộc rõ ràng; không lưu trạng thái của từng lời gọi vào mutable field dùng chung giữa các request.

### 4.4. Đăng ký bean và `aop:config`

**src/main/resources/applicationContext.xml**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
          http://www.springframework.org/schema/beans
          https://www.springframework.org/schema/beans/spring-beans.xsd
          http://www.springframework.org/schema/aop
          https://www.springframework.org/schema/aop/spring-aop.xsd">

    <!-- 1) Target: bean thực hiện nghiệp vụ. -->
    <bean id="orderService" class="demo.DefaultOrderService"/>

    <!-- 2) Dependency mà aspect sử dụng. -->
    <bean id="auditFormatter" class="demo.AuditFormatter"/>

    <!-- 3) Bean Java triển khai phương thức advice. -->
    <bean id="auditAspectBean" class="demo.AuditAspect">
        <constructor-arg ref="auditFormatter"/>
    </bean>

    <!-- 4) Cấu hình AOP qua XML schema. -->
    <aop:config proxy-target-class="false">
        <aop:pointcut
            id="serviceCalls"
            expression="execution(* demo.DefaultOrderService.*(..))"/>

        <aop:aspect id="orderAuditAspect" ref="auditAspectBean">
            <aop:around pointcut-ref="serviceCalls" method="around"/>
        </aop:aspect>
    </aop:config>

</beans>
~~~

Điểm quan trọng trong XML:

- `<bean id="orderService">` đặt target dưới quyền quản lý của Spring. Nếu nơi gọi viết `new DefaultOrderService()`, đối tượng đó không được Spring AOP proxy.
- `<bean id="auditFormatter">` là dependency độc lập.
- `<bean id="auditAspectBean">` cần tồn tại để `<aop:aspect ref="auditAspectBean">` trỏ tới. `constructor-arg ref="auditFormatter"` là dependency injection của Spring.
- `<aop:pointcut id="serviceCalls">` xác định phương thức của target class sẽ được match. `<aop:around pointcut-ref="serviceCalls">` dùng pointcut ID đã khai báo.
- `method="around"` phải trùng tên phương thức advice hiện hữu trong `AuditAspect`; đây **không phải** tên annotation.
- `proxy-target-class="false"` yêu cầu Spring ưu tiên interface-based proxy nếu target có interface phù hợp. Trong ví dụ `OrderService` là giao diện để caller lấy bean và gọi.
- `aop:config` đăng ký hạ tầng advisor/auto-proxy theo XML. Cấu hình này tự đủ cho aspect schema-based, không cần thêm `<aop:aspectj-autoproxy/>` chỉ để chạy `AuditAspect`.

Bên trong một `<aop:config>`, thứ tự khai báo các phần tử theo Spring schema là **pointcut, advisor rồi aspect**; nếu sử dụng nhiều loại, giữ thứ tự để XML hợp lệ. Các thẻ advice cụ thể được khai báo trong `<aop:aspect>`.

### 4.5. Lấy bean từ Spring context và chạy

**src/main/java/demo/Application.java**

~~~java
package demo;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public class Application {
    public static void main(String[] args) {
        try (var context =
                     new ClassPathXmlApplicationContext("applicationContext.xml")) {
            OrderService service = context.getBean(OrderService.class);

            System.out.println("result: " + service.place("O-7"));

            try {
                service.reject("O-9");
            } catch (IllegalArgumentException ex) {
                System.out.println("caught: " + ex.getMessage());
            }
        }
    }
}
~~~

Từ thư mục dự án chạy:

~~~bash
mvn -q compile exec:java
~~~

Các dòng `System.out` của chương trình theo thứ tự:

~~~text
audit: before place
service: place O-7
audit: after place
result: accepted O-7
audit: before reject
audit: error reject IllegalArgumentException
caught: rejected O-9
~~~

Maven/ứng dụng có thể sinh log hạ tầng khác theo cấu hình môi trường, nhưng các dòng trên thể hiện thứ tự nghiệp vụ quan trọng.

**Diễn giải đường đi**: `context.getBean(OrderService.class)` trả bean service đã được Spring AOP áp dụng proxy khi pointcut khớp. Caller gọi `place()` qua proxy; interceptor gọi `AuditAspect.around()`; aspect dùng bean `AuditFormatter`, sau đó `proceed()` đi vào `DefaultOrderService.place()`. Nếu target ném lỗi, advice ghi nhãn lỗi rồi ném lại; caller vẫn nhận `IllegalArgumentException`.

**Khi lỗi cấu hình**: xóa `<bean id="auditFormatter"...>` hoặc đổi `ref="auditFormatter"` thành ID không tồn tại sẽ khiến Spring không khởi tạo đầy đủ `AuditAspect`. Xóa `<bean id="auditAspectBean"...>` nhưng giữ `<aop:aspect ref="auditAspectBean">` khiến tham chiếu aspect không hợp lệ. Đó là lỗi bean wiring, không phải lỗi biểu thức `execution(...)`.

## 5. `aop:config` còn hỗ trợ những phần tử gì?

Ngoài `<aop:aspect>`, `<aop:config>` hỗ trợ **named pointcut** ở cấp cấu hình, **advisor** dùng advice interface, và các loại advice `before`, `after-returning`, `after-throwing`, `after`, `around`. Ví dụ:

~~~xml
<aop:config>
    <aop:pointcut id="serviceCalls"
                  expression="execution(* demo..*Service.*(..))"/>
    <aop:aspect ref="auditBean">
        <aop:before pointcut-ref="serviceCalls" method="before"/>
    </aop:aspect>
</aop:config>
~~~

Đây là fragment: bean `auditBean` cần method `before()` tương thích. Một `<aop:advisor advice-ref="interceptorBean" .../>` thay thế bằng **bean implement Advice/MethodInterceptor** chứ không tự gọi Java method tùy ý. Nếu có đầy đủ ba nhóm ở cấp `aop:config`, XSD yêu cầu **pointcut → advisor → aspect**. Các bài **“aop:config và khai báo aop:aspect”**, **“Pointcut có tên và pointcut-ref”** và **“aop:before...around”** lần lượt giải thích cấu trúc, chia sẻ scope và semantics từng advice.

## 6. Đăng ký đúng các bean mà AOP cần

### 6.1. Bean nghiệp vụ (target)

Target phải là **Spring-managed bean**, bằng `<bean>`, component scanning hoặc cấu hình bean tương đương. Khi dùng XML thuần, `<bean id="orderService" class="..."/>` trực tiếp là cách dễ xác minh nhất. Chỉ khai báo pointcut không tạo ra bean matching.

Một bean được proxy khi Spring có advisor khớp với method/target phù hợp. Không phải mọi bean trong context đều được bọc proxy, và tên bean được lấy từ context có thể trỏ tới proxy chứ không phải instance target nguyên bản.

### 6.2. Bean chứa aspect và dependency của nó

Với schema-based:

~~~xml
<bean id="auditFormatter" class="demo.AuditFormatter"/>

<bean id="auditAspectBean" class="demo.AuditAspect">
    <constructor-arg ref="auditFormatter"/>
</bean>

<aop:config>
    <aop:aspect ref="auditAspectBean">
        <aop:before
            pointcut="execution(* demo..*Service.place(..))"
            method="before"/>
    </aop:aspect>
</aop:config>
~~~

Đây chỉ là mẫu wiring; Java `AuditAspect` phải có method `before` nếu sử dụng thay cho phiên bản `around` ở mục 4. Các bean phụ thuộc của aspect dùng cú pháp Spring beans namespace thông thường (`constructor-arg`, `property`, `autowire` nếu được cấu hình). `<aop:aspect ref>` phải trỏ đến bean backing aspect; nó không phải cơ chế inject dependency.

Nếu aspect phụ thuộc một repository/client/service khác, khai báo bean phù hợp và inject vào aspect. Lưu ý tránh pointcut quá rộng vô tình intercept các method của chính aspect hoặc bean hỗ trợ, gây hành vi vòng lặp hoặc log ngoài dự kiến.

### 6.3. Phạm vi, khởi tạo và thứ tự bean

- Với schema-defined aspect, Spring hỗ trợ mô hình **singleton** cho aspect instance, nên không đặt request state vào field mutable của aspect. Với dữ liệu lời gọi, dùng biến cục bộ trong advice hoặc cơ chế context phù hợp.
- Constructor injection theo `ref` giúp Spring biết phụ thuộc cần được khởi tạo/resolve. Với singleton bean thông thường, container sẽ tạo dependency phù hợp khi khởi tạo aspect; **thứ tự các dòng `<bean>` trong cùng XML không phải công cụ sắp xếp logic advice**.
- Thứ tự chạy nhiều advisors/aspects là vấn đề AOP ordering (`order`, `Ordered`, `@Order` tùy cách khai báo); không suy diễn từ thứ tự đặt `<bean>` hay thời điểm dependency được inject.
- `depends-on` là cơ chế kiểm soát khởi tạo khi có quan hệ cần thứ tự nhưng không có dependency injection trực tiếp; nếu đã có `constructor-arg ref`, thông thường không cần `depends-on` chỉ để bean formatter sẵn sàng. `depends-on` không thay `ref` và không quyết định thứ tự advice.

## 7. Biến thể XML: bật các lớp `@Aspect` bằng `aop:aspectj-autoproxy`

Khi advice được viết trong class `@Aspect`, XML có thể kích hoạt bằng `<aop:aspectj-autoproxy/>` và đăng ký aspect bằng `<bean>`:

~~~xml
<bean id="orderService" class="demo.DefaultOrderService"/>
<bean id="annotatedAuditAspect" class="demo.AnnotatedAuditAspect"/>
<aop:aspectj-autoproxy/>
~~~

`demo.AnnotatedAuditAspect` phải thực sự có `@Aspect` và annotation advice. Nếu nó cần `AuditFormatter`, đăng ký bean formatter rồi inject qua `constructor-arg ref="auditFormatter"` như bean thường. `@Aspect` một mình không tạo bean, và `<aop:aspectj-autoproxy>` không tự bật component scanning. Trong kiểu này không cần thêm `<aop:aspect ref="annotatedAuditAspect">` để định nghĩa lại chính advice ấy.

## 8. Tác động của cấu hình proxy đến bean wiring

`proxy-target-class="false"` cho phép Spring ưu tiên **JDK interface proxy** với bean có interface phù hợp; caller nên lấy bean qua interface, như `OrderService.class`. `proxy-target-class="true"` yêu cầu **class-based proxy** và có giới hạn đối với final class, final/private methods. Spring có thể hợp nhất thiết lập auto-proxy trong cùng context nên một cấu hình khác yêu cầu CGLIB có thể ảnh hưởng kết quả.

Dù loại proxy nào, `this.otherMethod()` trong target và `new Target()` ngoài container không tự đi qua proxy. Muốn tìm hiểu `expose-proxy`, `AopContext.currentProxy()`, thread-local boundary và cách tự kiểm tra proxy thật, xem bài **“proxy-target-class và expose-proxy trong cấu hình XML”**.

## 9. Lỗi thường gặp khi cấu hình namespace và bean phụ thuộc

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| XML parser không nhận `aop:config` | Thiếu `xmlns:aop`, cặp `schemaLocation`, hoặc XSD không phù hợp | Đối chiếu URI và `spring-aop.xsd` chính thức |
| Context báo không tìm thấy bean được tham chiếu | `ref="auditAspectBean"`, `constructor-arg ref` hoặc `advice-ref` trỏ ID không tồn tại | Kiểm tra đúng tên bean ID và context chứa bean |
| Spring không tạo được aspect bean | Constructor dependency chưa đăng ký hoặc signature/constructor-arg không khớp | Kiểm tra `<bean>` hỗ trợ và constructor của aspect |
| Advice không chạy | Pointcut không match class/method, target không do Spring quản lý, caller dùng `new` | Kiểm tra bean thực tế từ ApplicationContext và pointcut |
| Advice không chạy khi gọi từ cùng bean | Self-invocation `this.method()` bypass proxy | Gọi qua ranh giới Spring bean proxy thích hợp |
| Khai báo `<aop:aspect ref="...">` nhưng advice method không có | `method="..."` sai tên hoặc signature sai | Khớp đúng method trên backing aspect bean |
| Dùng `<aop:aspectj-autoproxy/>` nhưng `@Aspect` không chạy | Chưa đăng ký bean `@Aspect` hoặc thiếu aspectjweaver | Đăng ký bằng `<bean>`/component scan và kiểm tra classpath |
| Log bị lặp | Định nghĩa cùng advice ở cả schema-based và `@Aspect`, hoặc nhiều advisors match | Loại cấu hình trùng, xem proxy/advisor chain |
| `getBean(DefaultOrderService.class)` không hoạt động như mong muốn | Bean đang là JDK interface proxy | Lấy bằng `OrderService`, hoặc cân nhắc class proxy |
| XML có `&&` trong expression | Ký tự ampersand chưa escape | Dùng `and` hoặc `&amp;&amp;` |
| `<aop:advisor advice-ref>` tham chiếu bean thường | Advice bean chưa implement đúng Spring AOP Advice/MethodInterceptor contract | Đăng ký class advice tương ứng API |
| Thứ tự advice ngoài mong đợi | Hiểu nhầm thứ tự khai báo bean là thứ tự interception | Cấu hình và kiểm thử advisor order rõ ràng |

## 10. Kiểm thử cấu hình XML trong Spring

Kiểm thử nên khởi tạo context bằng **cùng XML** mà ứng dụng dùng; không `new` target để kiểm thử advice. Các kiểm tra có giá trị:

1. Context khởi tạo thành công: schema được parse, bean ID và dependency được resolve.
2. Lấy bean qua interface; xác minh lời gọi `place` đi qua before → service → after, còn `reject` đi qua before → error và exception gốc vẫn đến caller.
3. Nếu bỏ cấu hình `<aop:config>` trong môi trường test riêng, quan sát direct target output không có log advice: giúp nhận diện điểm activation.
4. Đổi pointcut trong môi trường test để cố tình loại `place` khỏi vùng match; xác minh advice không chạy để biết expression đang hoạt động.
5. Cấu hình advisor/aspect khác: đo đúng số lần interception và thứ tự order thay vì suy đoán.
6. Xác minh bean `AuditAspect` được inject đúng `AuditFormatter`; không chia sẻ mutable per-request state trên singleton aspect.
7. Nếu thay JDK/class proxy, kiểm tra cách lấy bean và method đủ điều kiện được advice.

Có thể kiểm tra cơ chế proxy trong Java test:

~~~java
import org.springframework.aop.support.AopUtils;
import org.springframework.context.support.ClassPathXmlApplicationContext;

try (var context =
         new ClassPathXmlApplicationContext("applicationContext.xml")) {
    Object service = context.getBean("orderService");
    System.out.println(AopUtils.isAopProxy(service)); // true nếu được proxy
}
~~~

Đây là đoạn test **minh họa nhúng trong một method/runner Java**, không phải file độc lập có main. `isAopProxy` cho biết instance trả về là Spring AOP proxy; nó không chứng minh mọi method đều được pointcut match. Khi debug cần xét cả tên method, kiểu proxy, advisors và cách caller gọi bean.

## 11. Phân biệt ba lỗi về vòng đời và trách nhiệm

**Bean definition failure**: Spring chưa tạo được dependency như `auditFormatter`; context có thể fail trước khi business method được gọi. Cần sửa `<bean>`, `ref`, constructor injection hoặc phạm vi ApplicationContext.

**Advisor/pointcut mismatch**: context khởi động được và target chạy nhưng method không nằm trong expression, advice có thể không được áp dụng. Cần xét `execution(...)`, class thật và proxy boundary.

**Business exception**: target method thực sự được gọi và ném lỗi; `@AfterThrowing` hoặc `aop:around` có thể ghi nhận lỗi trước khi caller thấy exception. Cần giữ nguyên exception và bảo đảm advice không vô tình nuốt lỗi, trừ khi yêu cầu nghiệp vụ chỉ định chính sách khác.

Chúng là ba tình huống khác nhau, và Spring XML cung cấp dấu hiệu kiểm tra ở những chỗ khác nhau.

## Tổng kết

Trong cấu hình XML của Spring AOP, `xmlns:aop` và `spring-aop.xsd` cung cấp cú pháp, **`<aop:config>`** khai báo pointcut và advice, còn **`<bean>`** tạo đối tượng target/aspect cùng các dependency cần injection. `<aop:aspect ref>` liên kết đến bean triển khai advice; `pointcut-ref` liên kết đến pointcut; `method` liên kết đến tên method. Nếu chọn kiểu Java `@Aspect`, bật `<aop:aspectj-autoproxy/>` và vẫn phải đăng ký aspect bean. Mọi invocation cần đi qua Spring proxy thì mới được advice áp dụng.

### Tài liệu Spring chính thức

- [Spring Framework — Schema-based AOP Support](https://docs.spring.io/spring-framework/reference/core/aop/schema.html)
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — XML Schema-based Configuration](https://docs.spring.io/spring-framework/reference/core/appendix/xsd-schemas.html)

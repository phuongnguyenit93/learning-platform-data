# Ví dụ xuyên suốt: can thiệp lời gọi service bean trong ApplicationContext bằng Spring AOP

## 1. Mục tiêu và giới hạn

Bài này xây dựng một ứng dụng **Spring Framework thuần** để quan sát cách Spring AOP can thiệp khi mã ứng dụng gọi phương thức của **service bean lấy từ ApplicationContext**. Sau khi thực hành, bạn có thể:

- Đăng ký một service và một Spring aspect trong cùng ApplicationContext.
- Bật cơ chế tự tạo proxy bằng **@EnableAspectJAutoProxy**.
- Xác định đường đi của một lời gọi: client → Spring proxy → advice → service đích → client.
- Kiểm tra bean được trả về có phải AOP proxy hay không.
- Giải thích vì sao gọi từ bean khác đi qua proxy, còn gọi nội bộ bằng **this** thường bỏ qua advice.
- Nhận diện các lỗi cấu hình khiến một phương thức service không được chặn.

Trọng tâm là **cơ chế Spring gắn advice vào lời gọi của bean do container quản lý**. Những khái niệm AOP tổng quát chỉ được nhắc đến ở mức cần thiết để đọc và chạy ví dụ; bài không triển khai AspectJ weaving, bytecode instrumentation hay một hệ thống AOP độc lập với Spring.

## 2. Kịch bản thực tế

Giả sử một ứng dụng có **OrderService** nhận mã đơn hàng. Ta muốn in dấu vết trước và sau khi xử lý mà không thêm lệnh ghi log vào phương thức nghiệp vụ. Chúng ta tạo:

1. **OrderService**: hợp đồng mà mã gọi service sử dụng.
2. **OrderServiceImpl**: bean thực thi nghiệp vụ và được Spring quản lý bằng **@Service**.
3. **TraceAspect**: bean aspect được Spring tìm thấy qua **@Aspect** và **@Component**; advice chỉ áp dụng cho phương thức **place(...)**.
4. **AppConfig**: cấu hình component scanning và kích hoạt Spring AOP.
5. **App**: tạo ApplicationContext, lấy service từ container, gọi các phương thức và kiểm tra kết quả.

Sơ đồ đường đi được kỳ vọng:

~~~text
App
 │
 ├─ context.getBean(OrderService.class)
 │                 │
 │          Spring AOP proxy
 │                 │
 └─ service.place("A-01")
                   │
            TraceAspect: before
                   │
          OrderServiceImpl.place
                   │
            TraceAspect: after
                   │
             Giá trị trả về
~~~

Một điểm cốt lõi: biến **service** ở mã client trỏ tới đối tượng proxy do Spring đưa ra. Advice không tự chèn vào mọi lời gọi Java ở mọi nơi; nó chạy khi lời gọi đi qua proxy phù hợp.

## 3. Chuẩn bị dự án

Ví dụ dùng **Java 17+**, **Maven 3.9+**, **Spring Framework 6.2.12** và **AspectJ Weaver 1.9.24**. Dự án **không yêu cầu Spring Boot** hoặc máy chủ HTTP.

Cấu trúc:

~~~text
spring-aop-service-demo/
├── pom.xml
└── src/main/java/demo/
    ├── App.java
    ├── AppConfig.java
    ├── OrderService.java
    ├── OrderServiceImpl.java
    └── TraceAspect.java
~~~

**pom.xml**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-service-demo</artifactId>
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

**spring-context** mang theo các thành phần container và module Spring AOP cần dùng trong ví dụ; **aspectjweaver** cung cấp kiểu annotation, kiểu JoinPoint và công cụ phân tích biểu thức pointcut dạng AspectJ. Với cách chạy ở đây, Spring vẫn thực hiện **proxy-based AOP**: không bật trình biên dịch AspectJ và không gắn Java agent để weave class.

## 4. Viết mã Java

### 4.1. Định nghĩa hợp đồng service

**src/main/java/demo/OrderService.java**

~~~java
package demo;

public interface OrderService {
    String place(String code);

    String placeTwice(String code);
}
~~~

Client sẽ lấy và sử dụng bean theo **OrderService**, là interface mà proxy JDK có thể triển khai. Phương thức thứ hai chỉ dùng để minh họa trường hợp service tự gọi phương thức khác trên chính đối tượng đó.

### 4.2. Cài đặt bean nghiệp vụ

**src/main/java/demo/OrderServiceImpl.java**

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class OrderServiceImpl implements OrderService {

    @Override
    public String place(String code) {
        System.out.println("SERVICE place(" + code + ")");
        return "saved:" + code;
    }

    @Override
    public String placeTwice(String code) {
        String first = this.place(code + "-1");
        String second = this.place(code + "-2");
        return first + "|" + second;
    }
}
~~~

**@Service** làm cho lớp trở thành ứng viên được component scanning đăng ký vào ApplicationContext. **place(...)** chứa nghiệp vụ đơn giản; không cần biết về aspect. Trong **placeTwice(...)**, cả hai lệnh **this.place(...)** đều đi trực tiếp tới phương thức của target. Đây là chủ đích của ví dụ: khi client gọi **placeTwice(...)** qua proxy, phần gọi nội bộ không tự quay lại proxy.

### 4.3. Tạo Spring aspect chặn đúng phương thức

**src/main/java/demo/TraceAspect.java**

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TraceAspect {

    @Around("execution(* demo.OrderService.place(..))")
    public Object trace(ProceedingJoinPoint joinPoint) throws Throwable {
        System.out.println("AOP before place");
        try {
            Object result = joinPoint.proceed();
            System.out.println("AOP after place");
            return result;
        } catch (Throwable error) {
            System.out.println("AOP error place: "
                    + error.getClass().getSimpleName());
            throw error;
        }
    }
}
~~~

Các phần cần hiểu trong ngữ cảnh Spring:

- **@Aspect** đánh dấu đây là lớp khai báo advice và pointcut để Spring AOP xử lý. Nó **không tự làm lớp trở thành Spring bean**; ở đây **@Component** thực hiện việc đó.
- **@Around(...)** yêu cầu Spring đặt logic bao quanh lời gọi khớp biểu thức.
- **execution(* demo.OrderService.place(..))** chỉ chọn việc thực thi phương thức **place** của hợp đồng **OrderService**, với bất kỳ kiểu trả về và số tham số phù hợp. Vì bean triển khai interface này, Spring có thể áp dụng advisor cho lời gọi qua proxy.
- **joinPoint.proceed()** chuyển tiếp lời gọi cho bước kế tiếp trong chuỗi interceptor và cuối cùng đến target. Nếu bỏ nó, nghiệp vụ **place(...)** sẽ không chạy; nếu gọi nhiều lần, nghiệp vụ có thể chạy nhiều lần.
- Khi target thành công, advice trả về chính giá trị nhận từ **proceed()**. Khi target ném lỗi, ví dụ log tên kiểu lỗi rồi **ném lại nguyên lỗi** để giữ hành vi của service.
- Biểu thức hiện tại **không** chọn phương thức **placeTwice(...)**.

Trong ứng dụng thực, ghi log bằng framework logging, có chính sách che dữ liệu nhạy cảm, và tránh ghi quá nhiều dữ liệu tại advice. **System.out.println** chỉ giúp ví dụ có đầu ra dễ kiểm tra.

### 4.4. Bật AOP và đăng ký bean

**src/main/java/demo/AppConfig.java**

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

- **@Configuration** khai báo cấu hình cho container.
- **@ComponentScan(basePackages = "demo")** phát hiện **OrderServiceImpl** và **TraceAspect**.
- **@EnableAspectJAutoProxy** đăng ký hạ tầng auto-proxy dùng để xét các Spring bean với những advisor tương ứng. Với ví dụ có interface, cấu hình mặc định của Spring Framework thuần sử dụng JDK dynamic proxy.
- AOP infrastructure được bật trong **ApplicationContext** đang dùng. Nếu tạo một context khác mà không cấu hình tương ứng, không thể mặc nhiên kỳ vọng proxy giống context này.

### 4.5. Chạy và quan sát từ ApplicationContext

**src/main/java/demo/App.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderService service = context.getBean(OrderService.class);
            System.out.println("IS_PROXY " + AopUtils.isAopProxy(service));

            System.out.println("RESULT " + service.place("A-01"));
            System.out.println(
                    "INTERNAL_RESULT " + service.placeTwice("B-02"));
        }
    }
}
~~~

Điểm quan trọng là **context.getBean(OrderService.class)**. Nếu thay bằng **new OrderServiceImpl()**, client đang giữ target do chính mình tạo, không được Spring bọc proxy nên Spring AOP không chặn lời gọi đó.

## 5. Chạy chương trình và đọc đầu ra

Trong thư mục chứa **pom.xml**, chạy:

~~~bash
mvn -q clean compile exec:java
~~~

Đầu ra logic chuẩn (không tính thông báo riêng của Maven hoặc môi trường):

~~~text
IS_PROXY true
AOP before place
SERVICE place(A-01)
AOP after place
RESULT saved:A-01
SERVICE place(B-02-1)
SERVICE place(B-02-2)
INTERNAL_RESULT saved:B-02-1|saved:B-02-2
~~~

Giải thích lần lượt:

1. **IS_PROXY true**: Spring trả về một đối tượng AOP proxy, thay vì client trực tiếp giữ target thuần.
2. **service.place("A-01")**: đây là lời gọi từ client đi vào proxy; advice in **AOP before place**.
3. **proceed()**: target thực hiện nghiệp vụ, in **SERVICE place(A-01)** và trả về **saved:A-01**.
4. Sau khi target thành công, advice in **AOP after place** rồi trả kết quả về client; client in **RESULT saved:A-01**.
5. **service.placeTwice("B-02")**: lời gọi bên ngoài vẫn được chuyển qua proxy tới target, nhưng biểu thức pointcut không chọn chính phương thức **placeTwice(...)**.
6. Từ bên trong target, **this.place(...)** được gọi hai lần; các lời gọi này **không qua proxy**, nên chỉ xuất hiện hai dòng **SERVICE place(...)**, không có dòng **AOP before/after**.

Vì vậy, việc một phương thức có annotation **@Service** không có nghĩa mọi lần gọi phương thức đó đều tự động bị can thiệp. Điều kiện quyết định trong ví dụ là: **lời gọi đi qua Spring AOP proxy** và **phương thức khớp advisor/pointcut**.

## 6. Phân tích vòng đời proxy trong Spring

### 6.1. Lúc dựng ApplicationContext

Khi thực thi **new AnnotationConfigApplicationContext(AppConfig.class)**, Spring đọc cấu hình, tìm component, tạo các bean liên quan và áp dụng hạ tầng auto-proxy. **TraceAspect** là một Spring bean mang khai báo **@Aspect**; Spring đọc các khai báo advice và xác định bean/phương thức nào có thể phù hợp. **OrderServiceImpl** đủ điều kiện nên bean được đưa đến client qua proxy.

Diễn giải đơn giản:

~~~text
AppConfig
  ├─ @ComponentScan ──> OrderServiceImpl (@Service)
  ├─ @ComponentScan ──> TraceAspect (@Aspect, @Component)
  └─ @EnableAspectJAutoProxy
           │
           └─ Auto-proxy infrastructure
                      │
             OrderService bean exposed as proxy
~~~

Đối tượng đích vẫn chứa nghiệp vụ **place(...)**. Proxy chịu trách nhiệm chuyển lời gọi qua chuỗi interceptor được Spring xây dựng. Đối với ví dụ này, chuỗi chứa advice **trace(...)**.

### 6.2. Lúc client gọi phương thức

Điều kiện áp dụng advice có thể xem qua ba câu hỏi:

| Câu hỏi | Trong ví dụ | Hệ quả |
| --- | --- | --- |
| Đối tượng đến từ ApplicationContext đã bật AOP? | Có, gọi **context.getBean(...)** | Có thể nhận proxy |
| Có advisor phù hợp phương thức gọi? | Có, đối với **place(...)** | Advice được lựa chọn |
| Lời gọi có đi qua proxy? | Có với lời gọi từ **App**; không với **this.place(...)** | Chỉ lời gọi bên ngoài vào **place(...)** được chặn |

Ở đây Spring AOP dùng pointcut theo **lời gọi thực thi phương thức bean**. Không suy rộng rằng proxy tự chặn constructor, truy cập field hoặc toàn bộ mã Java nằm trong phương thức.

### 6.3. JDK proxy và CGLIB trong ví dụ này

**OrderServiceImpl** triển khai **OrderService**, vì vậy với cấu hình Spring Framework thuần như trên, Spring có thể tạo **JDK dynamic proxy** triển khai interface đó. Vì thế hãy lấy bean bằng **OrderService.class**. Không nên mặc định lấy bằng **OrderServiceImpl.class** trong chế độ JDK proxy: kiểu proxy không phải một instance của lớp triển khai.

Nếu service không triển khai interface, Spring AOP có thể tạo proxy dựa trên lớp bằng **CGLIB**. Bạn cũng có thể yêu cầu class-based proxy bằng **@EnableAspectJAutoProxy(proxyTargetClass = true)**. Lúc đó các ràng buộc kế thừa phải được lưu ý: lớp **final** không thể được subclass và phương thức **final/private** không thể được advice theo cách subclass proxy thông thường. Với ứng dụng Spring Boot, loại proxy mặc định có thể bị cấu hình Boot tác động, nên không áp dụng máy móc giả định mặc định của ví dụ Framework thuần.

## 7. Ba thí nghiệm để tự kiểm chứng

### Thí nghiệm A: gọi đối tượng tự tạo

Trong **App.java**, ngay sau phần gọi bean từ context, thêm:

~~~java
OrderService direct = new OrderServiceImpl();
System.out.println("DIRECT_RESULT " + direct.place("C-03"));
~~~

Đầu ra riêng của lần gọi này:

~~~text
SERVICE place(C-03)
DIRECT_RESULT saved:C-03
~~~

Không có **AOP before/after** vì **direct** không đi qua một Spring proxy. Việc lớp **OrderServiceImpl** có **@Service** không biến mọi instance tạo bằng **new** thành Spring bean.

### Thí nghiệm B: để proxy chặn cả lời gọi placeTwice

Trong **TraceAspect.java**, đổi duy nhất biểu thức pointcut:

~~~java
@Around("execution(* demo.OrderService.*(..))")
~~~

Khi gọi **service.placeTwice("B-02")**, advice bây giờ chạy **một lần cho lời gọi bên ngoài vào placeTwice(...)**. Hai lời gọi **this.place(...)** bên trong target vẫn không có vòng advice riêng. Các chuỗi log trong ví dụ cố ý đặt tên **place**, nên nếu chạy thí nghiệm này hãy đổi thông điệp log thành tên phương thức động (chẳng hạn **joinPoint.getSignature().getName()**) để tránh hiểu lầm.

### Thí nghiệm C: tắt Spring AOP trong context

Bỏ **@EnableAspectJAutoProxy** khỏi **AppConfig** trong ứng dụng Spring Framework thuần này. Chạy lại: **AopUtils.isAopProxy(service)** trở thành **false** và không có log của **TraceAspect**. Giữ nguyên annotation **@Aspect** trên lớp là chưa đủ: cần có hạ tầng xử lý aspect và đăng ký aspect bean trong context.

Các thí nghiệm này nên được chạy **từng thí nghiệm một**, rồi hoàn nguyên thay đổi trước khi thử tình huống tiếp theo.

## 8. Những lỗi hay gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân có thể có trong Spring | Cách kiểm tra hoặc sửa |
| --- | --- | --- |
| Không thấy advice chạy | Chưa bật **@EnableAspectJAutoProxy** trong context hiện tại | Kiểm tra **AppConfig** thực sự được nạp |
| Aspect không được phát hiện | Chỉ có **@Aspect** mà không đăng ký bean | Thêm **@Component** hoặc đăng ký bằng **@Bean** |
| Không tìm thấy service | Component scan không bao phủ package **demo** | Xác minh **@ComponentScan** và **@Service** |
| Lấy bean theo lớp triển khai thất bại | Bean được expose bằng JDK proxy triển khai interface | Inject/lấy theo **OrderService** |
| Advice chạy với lời gọi bên ngoài nhưng thiếu ở lời gọi nội bộ | **this.place(...)** bỏ qua proxy | Chuyển luồng cần advice sang một Spring bean khác và gọi qua bean được inject |
| Advice chạy sai hoặc không chạy ở một method | Biểu thức **execution(...)** quá rộng hoặc quá hẹp | Kiểm tra kiểu, tên method, package và đối tượng được proxy |
| Có log trước nhưng không có log sau | Target ném exception hoặc **proceed()** không hoàn thành | Giữ nguyên exception; dùng **finally** nếu muốn ghi log kết thúc dù lỗi |
| Startup báo lỗi liên quan AspectJ annotation/pointcut | Classpath thiếu dependency AspectJ cần cho kiểu annotation/parsing | Kiểm tra **aspectjweaver** cùng dependency Spring |

Khi có nhiều aspect, thứ tự các advice có thể thay đổi chuỗi log. Spring cung cấp **@Order** để quy định mức ưu tiên; không nên suy ra thứ tự chỉ từ vị trí class trong dự án.

## 9. Áp dụng thiết kế vào service thật

Ví dụ logging ở đây rất nhỏ, nhưng nguyên tắc triển khai quan trọng hơn lượng code:

- Đặt nghiệp vụ trong Spring bean và lấy dependency qua injection từ container. Đối tượng tự tạo bằng **new** không tự tham gia cơ chế Spring AOP.
- Viết pointcut đủ hẹp, chẳng hạn chỉ một gói service hoặc một annotation nghiệp vụ, để không vô tình can thiệp các phương thức ngoài ý muốn.
- Khi dùng **@Around**, gọi **proceed()** có chủ đích; giữ nguyên kết quả trả về và ngoại lệ nếu chỉ muốn quan sát. Advice can thiệp kết quả chỉ khi đó thực sự là yêu cầu thiết kế.
- Hạn chế dựa vào **self-injection** hay **AopContext.currentProxy()**. Nếu cần chặn một thao tác được gọi bên trong, giải pháp dễ bảo trì là tách thao tác đó sang bean khác rồi gọi qua dependency do Spring inject.
- Trong các hệ thống dùng **@Transactional**, **@Async** hoặc advice của nhiều thư viện, quy tắc đi qua proxy và self-invocation cũng là điều cần kiểm tra; mỗi cơ chế còn có điều kiện riêng nên phải đối chiếu cấu hình thực tế.
- Kiểm tra bằng cả **AopUtils.isAopProxy(...)** lẫn dấu vết hành vi. Việc có proxy không bảo đảm mọi method đều khớp pointcut.

## 10. Câu hỏi tự đánh giá

**1. Tại sao gọi service bằng context.getBean(...) lại có log advice, còn new OrderServiceImpl() thì không?**

Vì Spring tạo và expose proxy trong ApplicationContext có bật AOP. Instance do ứng dụng tự tạo không đi qua quá trình đó.

**2. Tại sao placeTwice(...) gọi this.place(...) mà không có log advice?**

Vì lời gọi từ chính target tới phương thức của nó là lời gọi Java trực tiếp, không đi qua proxy của Spring.

**3. Có phải @Aspect đã đủ để Spring quét và kích hoạt aspect?**

Không. **@Aspect** khai báo vai trò AOP; lớp vẫn phải được đăng ký là Spring bean (ở đây là **@Component**), đồng thời context cần bật khả năng xử lý @AspectJ.

**4. Nếu đổi pointcut thành execution(* demo.OrderService.*(..)), điều gì thay đổi?**

Các lời gọi bên ngoài qua proxy vào cả **place(...)** và **placeTwice(...)** sẽ khớp. Các lời gọi **this.place(...)** từ bên trong **placeTwice(...)** vẫn bỏ qua proxy.

**5. Trong ví dụ interface-based proxy, tại sao nên lấy bean theo OrderService.class?**

Vì JDK dynamic proxy thực thi interface **OrderService**; nó không nhất thiết có kiểu runtime **OrderServiceImpl**.

## 11. Tài liệu đối chiếu

- Spring Framework Reference — Spring AOP: https://docs.spring.io/spring-framework/reference/core/aop.html
- Spring Framework Reference — @AspectJ support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework Reference — Proxying mechanisms và self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

Kết quả cần nhớ từ thí nghiệm: **Spring AOP can thiệp lời gọi service bean qua proxy do ApplicationContext quản lý, với advisor phù hợp; lời gọi trực tiếp trên target hoặc gọi nội bộ bằng this không tự chạy cùng advice.**

# Phân biệt @AspectJ trong Spring AOP và cơ chế dệt của AspectJ

## 1. Hai cơ chế có thể dùng cùng cú pháp nhưng hoạt động khác nhau

Trong Spring Framework, `@AspectJ` là **kiểu khai báo aspect bằng annotation của AspectJ**, chẳng hạn `@Aspect`, `@Before`, `@Around` và biểu thức `execution(...)`. **Spring AOP đọc các khai báo đó để tạo proxy cho Spring bean**. Việc dùng các annotation này không có nghĩa AspectJ đang dệt (weave) bytecode của ứng dụng.

Cần tách ba khái niệm khi đọc cấu hình hoặc chẩn đoán:

- **Khai báo:** lớp Java gắn `@Aspect` và advice bằng annotation `org.aspectj.lang.annotation.*`. Đây là cú pháp dùng chung.
- **Bộ máy áp dụng trong Spring AOP:** Spring chọn bean/method phù hợp, tạo JDK dynamic proxy hoặc proxy lớp con CGLIB; lời gọi **đi qua proxy** mới được đưa qua chuỗi advice rồi tới đối tượng đích.
- **Dệt thực sự bằng AspectJ:** AspectJ compiler/weaver sửa bytecode của lớp chịu tác động tại thời điểm biên dịch, sau biên dịch hoặc khi nạp lớp. Advice không phụ thuộc việc lời gọi có đi qua Spring proxy.

Vì vậy, `@Aspect`, `@EnableAspectJAutoProxy`, `spring-boot-starter-aop` hoặc dependency `aspectjweaver` **tự thân không chứng minh bytecode đang được dệt**. Spring dùng thư viện AspectJ để phân tích/khớp pointcut, trong khi cơ chế thực thi của Spring AOP vẫn là proxy.

> Phạm vi bài: cách Spring AOP tích hợp cú pháp @AspectJ, sự khác biệt với AspectJ weaving trong ứng dụng Spring và hệ quả kỹ thuật khi lựa chọn cơ chế. Các lý thuyết AspectJ độc lập ngoài Spring không được mở rộng ở đây.

## 2. Bảng so sánh sát thực tế Spring

| Tiêu chí | Spring AOP sử dụng `@AspectJ` | AspectJ weaving trong ứng dụng Spring |
| --- | --- | --- |
| Công cụ áp dụng advice | Hạ tầng auto-proxy của Spring | AspectJ compiler/weaver |
| Cái được thay đổi | Bean được bọc bởi proxy; mã lớp đích về cơ bản giữ nguyên | Bytecode lớp chịu dệt được biến đổi |
| Điểm can thiệp chính | Join point thực tế của Spring AOP là **method execution** trên Spring bean qua proxy | Có thể dùng method execution và các join point khác như field access, constructor, method call khi weaving hỗ trợ |
| Phạm vi đối tượng | Đối tượng do Spring quản lý và đã được proxy | Lớp/đối tượng được weave theo phạm vi cấu hình, kể cả đối tượng không phải Spring bean |
| Gọi `this.otherMethod()` trong bean | Đi thẳng từ target sang target, thường bỏ qua advice trên `otherMethod()` | Có thể được advice vì bytecode của join point đích đã được dệt |
| `private`, `final`, constructor | Không thể xử lý chỉ bằng proxy theo cách tương đương weaving; CGLIB không override được `final`/`private` | Có thể can thiệp vào nhiều join point đó nếu aspect/pointcut và kiểu weaving phù hợp |
| Khởi động và vận hành | Không cần `ajc`, file `aop.xml` hay Java agent để dùng Spring AOP | Cần cấu hình quy trình dệt: `ajc` hoặc AspectJ LTW (weaver/agent, `META-INF/aop.xml`, classloader phù hợp) |
| Mức độ tích hợp Spring | Đi theo vòng đời bean, proxy, advisor, `ApplicationContext` | Có thể kết hợp Spring để cấu hình weaving/aspect, nhưng weaving thực hiện trên lớp |
| Chi phí và rủi ro cấu hình | Ít khâu vận hành; chịu các giới hạn proxy | Kiểm soát sâu hơn nhưng cần quản lý phạm vi weave, agent/build, class loading và thử nghiệm tương thích |

Mệnh đề chính xác là: **Spring AOP có thể dùng cú pháp @AspectJ; AspectJ weaving cũng có thể dùng aspect viết bằng kiểu @AspectJ; cùng mã annotation không làm hai cách thực thi giống nhau.**

## 3. Spring triển khai `@AspectJ` thành proxy như thế nào?

Một luồng điển hình:

~~~text
@Configuration / @Component + @Aspect được đăng ký thành Spring bean
       |
@EnableAspectJAutoProxy (hoặc Spring Boot AOP auto-configuration)
       |
Spring phát hiện aspect, phân tích pointcut, tạo advisor
       |
Bean phù hợp được trao ra qua proxy
       |
Caller -> proxy -> advice chain -> target.method()
                               -> giá trị trả về / exception
~~~

Để bật bằng Java config thuần Spring:

~~~java
@Configuration
@EnableAspectJAutoProxy
class AopConfiguration {
}
~~~

Một aspect cần là **bean thực sự** trong `ApplicationContext`. Có thể khai báo bằng `@Bean`, hoặc dùng đồng thời `@Aspect` và `@Component` nếu component scanning đã được bật. **Chỉ có `@Aspect` không tự đăng ký thành Spring bean.** Khi dùng Spring Boot, dependency `spring-boot-starter-aop` thường cho sẵn cấu hình auto-proxy; vẫn phải đăng ký aspect.

Spring Framework có hai kiểu proxy thường gặp:

1. **JDK dynamic proxy:** bọc các interface của bean; phía gọi tương tác qua interface.
2. **CGLIB class proxy:** tạo lớp con để intercept method có thể override. Spring có thể chọn CGLIB khi bean không có interface hoặc khi cấu hình ép dùng class proxy như `@EnableAspectJAutoProxy(proxyTargetClass = true)`. Kiểu proxy mặc định cần xem theo cấu hình Spring/Spring Boot thực tế, không đoán chỉ từ việc lớp có interface.

Dù dùng JDK proxy hay CGLIB, **lời gọi nội bộ trên `this` vẫn không quay lại proxy**. Ép `proxyTargetClass = true` không khắc phục self-invocation.

### Giới hạn pointcut trong Spring

Spring AOP hỗ trợ một tập biểu thức AspectJ xoay quanh *method execution* như `execution`, `within`, `args`, `@annotation`, `target`/`@target`, `this` và `bean` (mở rộng riêng của Spring). Spring không biến `call(...)`, `get(...)`, `set(...)` hoặc `cflow(...)` thành join point mới. Các designator đòi cơ chế weaving có thể báo lỗi khi đưa vào Spring AOP.

`bean(orderService)` hữu ích để lọc **tên Spring bean** trong Spring AOP; đây là mở rộng của Spring và không phải pointcut tương đương có thể chuyển nguyên xi sang AspectJ weaving thuần. Trong proxy AOP, `this` tham chiếu proxy còn `target` tham chiếu đối tượng phía sau proxy; khác biệt rõ nhất với JDK dynamic proxy.

## 4. Ví dụ Java 17+ chạy được: cùng bean, hai đường gọi

Ví dụ dùng **Spring Framework 6.2.0 + AspectJ Weaver 1.9.22** để minh họa Spring AOP bằng proxy, không bật weaving. Thư mục:

~~~text
spring-aop-demo/
├── pom.xml
└── src/main/java/demo/Demo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-aop-demo</artifactId>
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
          <mainClass>demo.Demo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

`src/main/java/demo/Demo.java`:

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class Demo {
    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    static class Config {
        @Bean
        PaymentService paymentService() {
            return new PaymentService();
        }

        @Bean
        AuditAspect auditAspect() {
            return new AuditAspect();
        }
    }

    public static class PaymentService {
        public void pay() {
            System.out.println("PAY");
        }

        public void batch() {
            System.out.println("BATCH");
            this.pay();
        }
    }

    @Aspect
    public static class AuditAspect {
        @Before("execution(* demo..*.pay(..))")
        public void beforePay() {
            System.out.println("ADVICE");
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            PaymentService bean = context.getBean(PaymentService.class);
            bean.pay();   // Caller -> Spring proxy -> advice -> target
            bean.batch(); // Proxy -> target.batch() -> this.pay(), không qua proxy lần hai
        }
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do ứng dụng in ra (nếu Maven báo thêm thông tin môi trường thì bỏ qua phần đó):

~~~text
ADVICE
PAY
BATCH
PAY
~~~

Tại sao chỉ có **một** dòng `ADVICE`?

- `bean.pay()` được gọi **qua Spring proxy** nên `@Before` chạy trước `PaymentService.pay()`.
- `bean.batch()` đi qua proxy nhưng không khớp pointcut `pay`; bên trong target, `this.pay()` gọi trực tiếp method cùng đối tượng nên không đi qua proxy. `@Before` không chạy thêm lần nữa.
- Đổi `proxyTargetClass` thành `true`, thêm dependency `aspectjweaver` hoặc đổi vị trí annotation không làm lời gọi nội bộ đó thành lời gọi đi qua proxy.

Đây là ví dụ chạy độc lập với Maven và Java 17 trở lên. Nó minh họa cơ chế Spring AOP; **không minh họa một quy trình AspectJ weaving được kích hoạt**.

### Cách sửa nhu cầu interception ngay trong Spring AOP

Nếu muốn xử lý mỗi lần `pay()` được gọi theo boundary, giải pháp Spring thường rõ nhất là chuyển `pay()` vào **bean riêng**, rồi để `batch()` gọi bean được Spring inject. Lúc đó lời gọi đi qua proxy. Tự inject proxy hoặc gọi `AopContext.currentProxy()` có thể làm được trong một số thiết lập, nhưng tăng phụ thuộc vào Spring AOP và cần cấu hình/kiểm soát vòng đời cẩn thận. Không dùng weaving chỉ để né mọi self-invocation khi có thể tách trách nhiệm giữa các bean hợp lý.

## 5. Khi nào cơ chế weaving của AspectJ xuất hiện trong một ứng dụng Spring?

Spring có tài liệu tích hợp với **AspectJ compile-time weaving (CTW)**, **post-compile weaving** và đặc biệt **load-time weaving (LTW)**. Điểm cốt lõi: AspectJ biến đổi bytecode đã xác định, thay vì bọc riêng một bean bằng proxy. Với LTW, phép biến đổi diễn ra khi lớp được nạp vào JVM (trước khi class được dùng). Với CTW/post-compile, build tạo ra bytecode đã weave.

Đối với LTW, một cấu hình minh họa thường có ba phần phối hợp:

1. **Aspect phù hợp** được biên dịch và có trong classpath, khai báo bằng cú pháp AspectJ hoặc kiểu `@AspectJ`.
2. **Bộ weaver và phạm vi weave**: AspectJ weaver (ví dụ qua `-javaagent:/path/to/aspectjweaver.jar`) cùng khai báo `META-INF/aop.xml`; chỉ rõ các package cần weave.
3. **Phần tích hợp Spring khi cần**: `@EnableLoadTimeWeaving`/`<context:load-time-weaver/>` giúp Spring bố trí `LoadTimeWeaver` theo classloader và môi trường; một số môi trường dùng `spring-instrument` agent. Chỉ thêm annotation này mà không có cơ sở hạ tầng, cấu hình và classloader phù hợp thì không bảo đảm có weaving.

Ví dụ **phác họa riêng của LTW**, không phải một bản thay thế thẳng cho project proxy ở phần 4:

`src/main/resources/META-INF/aop.xml`:

~~~xml
<!DOCTYPE aspectj PUBLIC "-//AspectJ//DTD//EN"
  "https://www.eclipse.org/aspectj/dtd/aspectj.dtd">
<aspectj>
  <aspects>
    <aspect name="demo.TraceAspect"/>
  </aspects>
  <weaver>
    <include within="demo..*"/>
  </weaver>
</aspectj>
~~~

Trong mô hình dùng AspectJ Java agent, ứng dụng cần được khởi chạy với tham số JVM tương tự:

~~~text
-javaagent:/absolute/path/to/aspectjweaver.jar
~~~

`TraceAspect` phải là class aspect thực sự có trên classpath; ví dụ này chỉ cho thấy **vị trí cấu hình weaving**, không tự nhận là project LTW có thể chạy ngay nếu chưa định nghĩa aspect, đóng gói và thiết lập lệnh chạy. Nên giới hạn `include` vào lớp của ứng dụng; weave tràn toàn bộ classpath làm tăng rủi ro và khó chẩn đoán.

Một bẫy quan trọng: ứng dụng dùng Spring Framework **không bắt buộc** aspect nào cũng do Spring tạo/tiêm dependency theo cách áp dụng cho proxy aspect. Việc khởi tạo, cấu hình và inject vào aspect được AspectJ weave cần được thiết kế riêng, đặc biệt khi dùng aspect ngoài `ApplicationContext`. Không suy ra rằng `@Component` + `@Aspect` + `@EnableAspectJAutoProxy` đã kích hoạt AspectJ weaver.

## 6. Chọn cơ chế nào cho từng yêu cầu trong Spring?

| Yêu cầu | Ưu tiên và lý do |
| --- | --- |
| Log, đo thời gian, audit hoặc kiểm tra tại public method của Spring service khi được bean khác gọi | **Spring AOP @AspectJ**, ít cấu hình, khớp với cấu trúc service bean |
| Cross-cutting ở controller/service/repository do Spring quản lý, pointcut là method execution | **Spring AOP** thường đủ; kiểm tra tình huống async, proxy chain và thứ tự advisor |
| Cần advice trên cuộc gọi `this.method()` hoặc thực thi nội bộ cùng object | Có thể **tách bean để giữ Spring AOP**; nếu cần bao phủ mọi đường gọi bên trong class mới cân nhắc weaving |
| Cần tác động constructor, field access, method call site hoặc object tạo bằng `new` ngoài IoC | **AspectJ weaving** phù hợp về cơ chế; proxy của Spring không bao phủ được |
| Một lớp `final` hoặc method `final` cần interception thực sự | **Weaving hoặc đổi thiết kế**; CGLIB subclass proxy không override được `final` |
| Chỉ có dependency `aspectjweaver` và aspect có `@Aspect` | Chưa đủ chứng minh weaving; đọc thiết lập auto-proxy/`ajc`/agent/`aop.xml` trước khi kết luận |

Ví dụ dễ nhầm: `@Transactional` của Spring trong cấu hình proxy mặc định cũng chịu vấn đề self-invocation; cùng bản chất proxy đó có thể gặp ở logging, security hoặc caching thông qua advisor. Tuy nhiên đây là minh họa hệ quả của proxy Spring; không đồng nhất tất cả annotation với một loại aspect `@Aspect`.

## 7. Những nhầm lẫn và cách chẩn đoán

**Nhầm 1: “Có `@Aspect` nên chắc chắn là AspectJ weaving.”** Sai. Kiểm tra có `@EnableAspectJAutoProxy`/auto-configuration, aspect được đăng ký làm bean và Spring đang cấp proxy hay không. Ngược lại, để xác nhận AspectJ weaving, tìm cấu hình `ajc` của build, startup `-javaagent`, `META-INF/aop.xml` hoặc bằng chứng bytecode/class-load weaving.

**Nhầm 2: “Thêm `aspectjweaver.jar` thì self-invocation sẽ được advice.”** Sai. Dependency thường cần cho việc phân tích expression của Spring @AspectJ; muốn weave phải **chủ động kích hoạt và cấu hình** compiler/weaver.

**Nhầm 3: “Bật CGLIB sẽ bắt được private/final/self-call.”** Sai. Proxy CGLIB là lớp con; method `private`/`final` không thể override để advice, còn `this` gọi vào target không qua proxy. Proxy JDK lại phụ thuộc interface được expose; cần hiểu kiểu proxy thực tế.

**Nhầm 4: “Viết mọi pointcut AspectJ rồi Spring AOP sẽ hiểu.”** Sai. Spring AOP hỗ trợ một tập designator giới hạn và có mở rộng `bean(...)` riêng. Với `call`, `get`, `set`, constructor join point..., phải đánh giá weaving thay vì cố dùng Spring proxy.

**Nhầm 5: “Tạo object bằng `new` bên trong service vẫn được auto-proxy.”** Sai trong ngữ cảnh bean thông thường: đối tượng tự tạo không đi qua cơ chế đăng ký và proxy bean của container. Muốn advice với Spring AOP thì quản lý đối tượng bằng Spring và gọi qua bean proxy; nếu bắt buộc advice đối tượng ngoài container thì xét weaving.

**Nhầm 6: “Spring LTW chỉ cần `@EnableLoadTimeWeaving` là xong.”** Sai. Cần xác minh classloader/instrumentation, khai báo aspect và phạm vi weave, cách nạp lớp, agent khi cần. Nếu lớp đã nạp trước khi transformer có hiệu lực, cấu hình LTW có thể không xử lý lớp như mong muốn.

Quy trình chẩn đoán lỗi advice không chạy:

1. Xác nhận đối tượng thật sự là Spring bean được lấy từ `ApplicationContext`, aspect cũng được đăng ký; tránh vô tình khởi tạo service bằng `new`.
2. Xác nhận auto-proxy đã bật và pointcut khớp đúng method execution/các annotation/signature được gọi.
3. Xác định hướng gọi: **caller có đi qua Spring proxy không?** Kiểm tra self-invocation, method không thể advice, JDK interface và CGLIB class proxy.
4. Nếu yêu cầu nằm ngoài khả năng proxy, xem cấu hình weaving riêng: build/agent/`META-INF/aop.xml`, classpath, classloader và package include.
5. Với lời gọi có nhiều advisor, kiểm tra thứ tự bằng `@Order`, vấn đề exception và trạng thái transaction; không suy đoán thứ tự từ tên lớp.

## 8. Câu hỏi tự kiểm tra

1. Một class có `@Aspect` và `@Before`, trong classpath có `aspectjweaver`. Có đủ căn cứ nói nó dùng weaving chưa? **Chưa**: đây có thể chỉ là cấu hình Spring AOP proxy.
2. Vì sao một bean Spring gọi `this.save()` lại bỏ qua advice trên `save()` trong proxy AOP? **Vì lời gọi nội bộ không đi qua proxy**.
3. Đổi JDK dynamic proxy sang CGLIB có làm `this.save()` đi qua proxy không? **Không**.
4. Muốn chặn truy cập field của đối tượng không do Spring tạo thì `@EnableAspectJAutoProxy` có đủ không? **Không**; phải đánh giá AspectJ weaving và phạm vi loại join point tương ứng.
5. Khi một Spring service gọi bean khác có method khớp `execution(...)`, Spring AOP `@AspectJ` có cần compiler `ajc` không? **Không**.

## Tài liệu chính thức để đối chiếu

- Spring Framework, *@AspectJ support*: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework, *Enabling @AspectJ Support*: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework, *Proxying Mechanisms*: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework, *Declaring a Pointcut*: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Spring Framework, *Using AspectJ with Spring Applications*: https://docs.spring.io/spring-framework/reference/core/aop/using-aspectj.html

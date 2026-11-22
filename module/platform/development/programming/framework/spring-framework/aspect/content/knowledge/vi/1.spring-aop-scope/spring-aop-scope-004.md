# Phạm vi áp dụng Spring AOP trên đối tượng được Spring quản lý

## 1. Phạm vi của bài học

Trong **Spring AOP dựa trên proxy**, đối tượng được Spring quản lý (Spring bean) là phạm vi mà cơ chế tự động tạo proxy và áp dụng advice hoạt động. Một lớp Java có phương thức khớp pointcut chưa đủ để mọi instance của lớp đó đều được can thiệp.

Sau bài này, bạn cần phân biệt được:

- **Spring bean**: instance được đăng ký, khởi tạo hoặc cung cấp cho Spring IoC container theo bean definition; container quản lý việc cung cấp tham chiếu bean và các bước xử lý liên quan.
- **Target object**: instance chứa hành vi nghiệp vụ thật.
- **AOP proxy**: đối tượng trung gian do Spring tạo cho target đủ điều kiện, giúp chạy advice trước/sau/xung quanh lời gọi phương thức.
- **Đối tượng tự tạo**: instance do mã ứng dụng tự khởi tạo, không đăng ký làm bean; cơ chế Spring AOP tự động không bao bọc instance này.

Trọng tâm là **Spring AOP trong ApplicationContext**, không bàn về lý thuyết Aspect chung hoặc cơ chế weaving độc lập của AspectJ.

## 2. Quy tắc cốt lõi: Bean + proxy + lời gọi đi qua proxy

Một lời gọi phương thức có cơ hội nhận Spring AOP advice khi đồng thời thỏa các điều kiện:

1. **Đối tượng đích thuộc phạm vi Spring quản lý**: chẳng hạn bean từ `@Component`, `@Service`, `@Repository`, `@Bean` hoặc khai báo bean tương đương.
2. **Spring AOP đã được cấu hình và có advisor phù hợp**: aspect được đăng ký là bean, hỗ trợ `@AspectJ` được bật, và pointcut khớp phương thức/bean. Không phải mọi bean đều sinh ra proxy.
3. **Lời gọi đi qua tham chiếu proxy và phương thức có thể được proxy can thiệp**: nếu gọi trực tiếp target hoặc gọi nội bộ qua `this`, advice của proxy không được thực thi cho lời gọi đó.

```text
Lời gọi bên ngoài -> tham chiếu Spring bean (proxy, nếu có)
                  -> advice phù hợp -> target.method()
                  -> kết quả trả về người gọi

Lời gọi trực tiếp -> new Target().method()
                  -> target.method()       (không qua Spring AOP proxy)
```

**Phân biệt quan trọng:** Bean được Spring quản lý là điều kiện để cơ chế auto-proxy của Spring AOP hoạt động, nhưng **không đảm bảo** bean nào cũng có proxy. Việc proxy có mặt còn phụ thuộc cấu hình AOP, pointcut, khả năng proxy hóa kiểu/phương thức và các điều kiện tạo bean.

### Spring có thể quản lý đối tượng theo những cách nào?

| Cách có được đối tượng | Spring có quản lý instance đó không? | Hệ quả đối với Spring AOP |
| --- | --- | --- |
| `@Component`/`@Service` được component scan phát hiện | Có | Có thể được tạo proxy nếu advisor khớp |
| Phương thức `@Bean` trả về `new OrderService()` | Có, **đối với instance được trả về và đăng ký làm bean** | Có thể được proxy; từ khóa `new` trong factory method không loại trừ AOP |
| Bean khai báo bằng Java configuration, XML hoặc đăng ký bean definition | Có | Có thể được auto-proxy |
| `context.getBean(OrderService.class)` | Lấy bean mà container cung cấp | Thường nhận proxy nếu bean đã được AOP proxy |
| Instance `new OrderService()` bên ngoài container | Không | Không tự nhận advice của Spring AOP |
| `new OrderService()` bên trong một phương thức nghiệp vụ, không đăng ký bean | Không | Không tự nhận advice |
| Bean scope `prototype` được lấy qua container | Có; mỗi lần lấy có thể tạo một instance mới | Instance nhận được có thể được proxy tùy điều kiện |
| Đối tượng được tạo ở thư viện khác hoặc bởi một factory ngoài container | Không mặc nhiên | Cần tích hợp rõ ràng với Spring; chỉ cùng kiểu với bean là chưa đủ |

`@Autowired` hoặc constructor injection thường cung cấp tham chiếu bean từ container; nếu Spring đã bọc bean bằng proxy thì dependency nhận được chính là tham chiếu có thể đi qua advice. Ngược lại, giữ một tham chiếu riêng tới target do chính bạn tạo ra sẽ bỏ qua proxy.

## 3. Ví dụ chạy được: cùng một lớp, hai đường tạo instance

Ví dụ sử dụng **Spring Framework 6.2.x và Java 17+**, không cần Spring Boot. `MessageService` là một lớp thông thường. `AppConfig` đăng ký một instance làm Spring bean; `Main` đồng thời tự tạo một instance khác để đối chiếu.

Cấu trúc Maven:

```text
spring-aop-scope/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── MessageService.java
    ├── AuditAspect.java
    └── Main.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aop-scope</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>${spring.version}</version>
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
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`MessageService.java`**

```java
package example;

public class MessageService {
    public void send(String message) {
        System.out.println("send: " + message);
    }
}
```

**`AuditAspect.java`**

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    @Before("execution(* example.MessageService.send(..))")
    public void beforeSend() {
        System.out.println("[aspect] before send");
    }
}
```

**`AppConfig.java`**

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy
public class AppConfig {
    @Bean
    public MessageService messageService() {
        return new MessageService();
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }
}
```

**`Main.java`**

```java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            MessageService managed = context.getBean(MessageService.class);
            System.out.println("managed proxy: " + AopUtils.isAopProxy(managed));
            managed.send("bean");

            MessageService manual = new MessageService();
            System.out.println("manual proxy: " + AopUtils.isAopProxy(manual));
            manual.send("new");
        }
    }
}
```

Tại thư mục chứa `pom.xml`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

Các dòng do chương trình in ra:

```text
managed proxy: true
[aspect] before send
send: bean
manual proxy: false
send: new
```

**Giải thích từng bước:**

1. `@EnableAspectJAutoProxy` kích hoạt cơ chế Spring AOP proxy trong context ví dụ; `@Bean auditAspect()` đăng ký aspect để Spring tìm thấy advice.
2. `@Bean messageService()` đăng ký **giá trị trả về** làm bean. Mặc dù thân phương thức dùng `new`, instance này được đưa vào vòng quản lý của container.
3. Pointcut khớp phương thức `MessageService.send(..)` của bean. `context.getBean(...)` cung cấp proxy; lời gọi `managed.send("bean")` đi qua advice.
4. `manual` là instance cùng lớp nhưng được tạo riêng ở `Main`. Không có bước đăng ký/proxy, nên `manual.send("new")` chỉ in dòng nghiệp vụ.

Nếu bỏ `@EnableAspectJAutoProxy` trong ứng dụng Spring Framework thuần ở ví dụ này, hoặc không đăng ký `AuditAspect` làm bean, đừng kỳ vọng advice chạy. Trong Spring Boot, starter AOP và auto-configuration có thể đảm nhiệm bước bật hỗ trợ AOP; cần kiểm tra cấu hình thực tế của ứng dụng.

> **Quy tắc dễ nhớ:** Spring nhìn vào **instance do container cung cấp và đường gọi đi qua proxy**, chứ không tự sửa mọi instance Java có cùng class hay mọi vị trí thỏa chuỗi pointcut.

## 4. Các ngoại lệ cần phân biệt về phạm vi quản lý

Không phải mọi object cùng class với Spring bean đều là bean. `@Bean MessageService messageService() { return new MessageService(); }` đưa **instance trả về** vào container; `new MessageService()` gọi trong một utility khác thì không. Đối với prototype bean, từng lần tra cứu từ container có thể nhận một instance mới và mỗi instance vẫn có thể được AOP proxy nếu phù hợp.

Một bean được Spring quản lý cũng chưa chắc nhận advice: aspect có thể chưa được đăng ký, pointcut không khớp, method không được proxy chặn, hoặc caller giữ tham chiếu target thô. Gọi `this.inner()` từ một method khác của target không quay lại proxy, nên advice chỉ gắn trên `inner()` không chạy trong bước gọi đó. Hãy tách trách nhiệm sang bean cộng tác khi cần interception rõ ràng.

JDK proxy chỉ công bố các method trên interface được proxy; CGLIB không thể override `final`/`private` hoặc subclass một `final class`. Constructor, static method và field access không phải join point của Spring AOP proxy. Những lời gọi trong giai đoạn initialization như `@PostConstruct` cũng không nên được thiết kế dựa trên giả định proxy đã có hiệu lực.

Vì vậy cần xác minh hai sự thật khác nhau: **object đã được Spring đăng ký** và **lời gọi đang đi qua proxy có advisor phù hợp**. Bài này tập trung ở ranh giới instance do container quản lý; chi tiết tự gọi và trình tự advice thuộc phần cơ chế proxy.

## 5. Kiểm tra phạm vi trong ứng dụng thật

Khi dự kiến advice phải chạy nhưng thực tế không chạy, kiểm tra theo thứ tự:

1. **Bean có thật trong context đúng không?** Kiểm tra khai báo `@ComponentScan`, `@Bean`, profile/condition và context chứa bean. `context.containsBean("beanName")` kiểm tra **tên bean**, không chứng minh một object bất kỳ là bean.
2. **Tham chiếu đang gọi có phải proxy không?** Sử dụng `AopUtils.isAopProxy(reference)`, có thể kết hợp `AopUtils.isJdkDynamicProxy(...)` hoặc `AopUtils.isCglibProxy(...)`. `false` nghĩa là tham chiếu đang kiểm tra không phải Spring AOP proxy; không tự động kết luận mọi cấu hình AOP sai.
3. **Caller lấy tham chiếu từ đâu?** Đối chiếu `context.getBean(...)` hoặc dependency injection với một instance tự `new`. Nếu có JDK proxy, inject/gọi qua kiểu interface phù hợp thay vì ép kiểu về implementation.
4. **Đường gọi có tự quay về `this` không?** Nếu có, advice của phương thức được gọi nội bộ không nhận được lượt đi qua proxy.
5. **Pointcut và khả năng can thiệp có đúng không?** Xem package, modifier, kiểu proxy, method signature, annotation, overload và bean thực tế. Một biểu thức khớp tên lớp chưa đủ nếu chính lời gọi không đi qua proxy.
6. **Có nhiều ApplicationContext hoặc bean cùng kiểu không?** Xác minh đúng context và đúng bean reference đang sử dụng; aspect trong context này không mặc nhiên áp dụng lên mọi instance do context khác hoặc thư viện khác tạo ra.

Đoạn chẩn đoán nhỏ khi đã có `context`:

```java
// Giả định có AnnotationConfigApplicationContext context
// và một bean MessageService đã đăng ký trong context.
Object bean = context.getBean("messageService");
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.getTargetClass(bean).getName());
```

Lệnh đầu quan sát **tham chiếu proxy thực tế**; lệnh sau giúp xem lớp target phía sau proxy. Đừng chỉ kiểm tra `bean.getClass()` rồi đánh đồng lớp proxy sinh động với lớp nghiệp vụ.

## 6. Các tình huống cần phân biệt

| Tình huống | Advice Spring AOP có chạy không? | Lý do |
| --- | --- | --- |
| Controller/bean A gọi một public method trên service B được inject, B đã có proxy khớp pointcut | Có | Lời gọi đi qua proxy B |
| `@Bean` trả về `new Service()`, sau đó caller lấy bean qua context và gọi method khớp | Có, nếu proxy hợp lệ được tạo | Instance đã đăng ký là bean |
| Một utility tạo `new Service()` rồi gọi cùng method | Không | Instance ngoài container, không qua proxy |
| Service được proxy, nhưng `this.work()` gọi trong chính Service | Không đối với advice riêng của `work()` | Self-invocation bỏ qua proxy |
| Một bean Spring không khớp advisor nào | Không | Không có advice phù hợp |
| Cố advice phương thức `private` | Không | Phương thức không được proxy chặn |
| Chỉ thêm `@Aspect` lên lớp mà không đăng ký nó làm bean | Không tự động | Spring không phát hiện aspect để cấu hình AOP |

Các dòng ghi “Có” luôn giả định **cấu hình Spring AOP hoạt động, pointcut đúng và phương thức có thể chặn**. Không nên suy ra việc tất cả bean đều bị can thiệp.

## 7. Giới hạn rõ ràng của chủ đề

Spring AOP được thiết kế cho **method execution trên Spring bean thông qua proxy**. Nếu bài toán bắt buộc áp dụng advice cho đối tượng không do Spring quản lý, constructor, field access hoặc lời gọi nội bộ bất kể proxy, đó là yêu cầu vượt phạm vi proxy-based Spring AOP. Spring có tích hợp với AspectJ weaving cho các tình huống khác, nhưng đây là **cơ chế riêng**, cần cấu hình riêng; không nên nhầm `@EnableAspectJAutoProxy` với việc kích hoạt bytecode weaving.

**Tự kiểm tra:** Cho lớp `PaymentService` có một instance được đăng ký bằng `@Bean` và một instance tạo bằng `new`. Cả hai có phương thức `pay()` khớp pointcut. Lần lượt gọi qua `context.getBean(...).pay()`, `new PaymentService().pay()` và gọi `this.pay()` từ một method trong bean. Hãy dự đoán đường gọi nào đi qua Spring proxy và giải thích vì sao. Đáp án: chỉ lời gọi qua tham chiếu bean proxy (nếu được tạo và khớp) mới chạy advice của `pay()`; hai cách còn lại bỏ qua proxy.

**Tài liệu Spring Framework:**
- [Spring AOP — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html)
- [Spring AOP — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring AOP — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html)

# Spring AOP can thiệp lời thực thi phương thức qua proxy

## 1. Mục tiêu và phạm vi

Sau bài này, bạn có thể giải thích vì sao một lời gọi phương thức trên Spring bean có thể chạy thêm logic trước/sau phương thức thật; phân biệt proxy với đối tượng đích; xác định lời gọi nào đi qua Spring AOP, lời gọi nào đi thẳng vào đối tượng; và chẩn đoán các trường hợp advice không chạy.

**Trọng tâm:** Spring AOP sử dụng **proxy** do Spring container quản lý để chặn *method execution* trên Spring bean. Kiến thức Aspect nói chung không phải chủ đề ở đây. Những tên như aspect, pointcut, advice được dùng để mô tả cách Spring cấu hình chuỗi xử lý cho phương thức.

## 2. Luồng gọi thật sự trong Spring AOP

Giả sử một thành phần khác được tiêm `OrderService` và gọi `orderService.submit("A01")`. Nếu có advice áp dụng cho phương thức này, tham chiếu bean mà thành phần đó nhận có thể là một **proxy** thay vì chính đối tượng triển khai.

```text
Controller / Client bean
          |
          |  gọi orderService.submit("A01")
          v
     Spring AOP proxy
          |
          |  (1) so khớp phương thức với các advisor/pointcut
          |  (2) chạy chuỗi interceptor / advice phù hợp
          |  (3) tiếp tục tới target khi advice cho phép
          v
   OrderServiceImpl.submit(...)
          |
          |  trả kết quả hoặc ném exception
          v
     advice xử lý kết quả/lỗi
          |
          v
     trả về Controller / Client
```

- **Target:** đối tượng chứa phần triển khai nghiệp vụ thật, ví dụ `OrderServiceImpl`.
- **Proxy:** đối tượng trung gian Spring trả về khi bean đủ điều kiện áp dụng advisor; nó tiếp nhận lời gọi từ bên ngoài rồi điều phối advice và target.
- **Advisor / interceptor chain:** Spring chọn các advice phù hợp với phương thức đang gọi và thực thi chúng theo thứ tự đã cấu hình. Proxy không nhất thiết có advice cho *mọi* phương thức của bean.
- **Join point trong Spring AOP:** chỉ là **lúc thực thi phương thức**. Spring AOP theo cơ chế proxy không trực tiếp chặn việc đọc trường, gọi constructor hay mọi điểm thực thi tùy ý.
- **Điểm quyết định:** đường đi quan trọng là `client → proxy → target`. Nếu client nắm trực tiếp target và gọi nó, chuỗi advice của proxy không tham gia.

Ở thời điểm tạo bean, bộ xử lý auto-proxy của Spring phát hiện các advisor/aspect phù hợp và có thể tạo proxy bao quanh bean. Ứng dụng thường lấy proxy từ `ApplicationContext` hoặc qua dependency injection; không cần tự gọi một “hàm AOP” trong business method.

## 3. Hai dạng proxy và hệ quả thực tế

| Cơ chế | Cách tạo | Những phương thức có thể được gọi từ bên ngoài |
| --- | --- | --- |
| **JDK dynamic proxy** | Proxy triển khai interface của bean | Gọi qua các interface mà proxy công bố |
| **Class-based proxy (CGLIB)** | Proxy là lớp con được sinh từ target class | Gọi qua kiểu lớp của proxy đối với phương thức có thể override |

Trong cấu hình Spring Framework thông thường, target có interface thì JDK dynamic proxy là lựa chọn mặc định; nếu không có interface thì Spring dùng class-based proxy. Cấu hình từ Spring Boot hoặc `proxyTargetClass=true` có thể đổi kiểu proxy mặc định. Vì vậy **đừng suy kiểu proxy chỉ từ việc class có interface** khi chưa xem cấu hình thực tế.

Với JDK proxy, mã tiêm bean theo interface thường an toàn hơn việc ép kiểu sang implementation. Class-based proxy **không thể** tạo bằng cách kế thừa một `final class`; `final method` và `private method` không thể được advice theo cơ chế override. Những phương thức không nhìn thấy từ lớp con, chẳng hạn package-private ở lớp cha thuộc package khác, cũng gặp giới hạn. Các phương thức `static` và lời gọi trực tiếp trên đối tượng ngoài Spring container không phải các lời gọi proxy cần trông đợi Spring AOP chặn.

Đừng nhầm kiểu proxy với phạm vi can thiệp: **dù là JDK hay CGLIB, Spring AOP vẫn hoạt động qua lời gọi được chuyển đến proxy**. Chọn CGLIB không tự sửa được lỗi self-invocation.

## 4. Ví dụ có thể chạy: gọi qua proxy và quan sát advice

Ví dụ độc lập dùng **Java 17+, Maven, Spring Framework 6.2.6**. Đặt đúng hai tệp dưới đây. `spring-context` cung cấp container, `spring-aop` chứa cơ chế proxy; `aspectjweaver` được Spring dùng để diễn giải biểu thức pointcut `@AspectJ`. Ví dụ chỉ dùng Spring AOP, không thiết lập compile-time hoặc load-time weaving.

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-proxy-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.6</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/Main.java`:

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class Main {
    public interface OrderService {
        String submit(String orderId);
    }

    static class OrderServiceImpl implements OrderService {
        @Override
        public String submit(String orderId) {
            System.out.println("TARGET submit " + orderId);
            return "OK:" + orderId;
        }
    }

    @Aspect
    static class AuditAspect {
        @Around("execution(* demo..*.submit(..))")
        public Object trace(ProceedingJoinPoint pjp) throws Throwable {
            System.out.println("BEFORE " + pjp.getSignature().getName());
            try {
                Object value = pjp.proceed();
                System.out.println("AFTER " + value);
                return value;
            } catch (Throwable error) {
                System.out.println("ERROR " + error.getClass().getSimpleName());
                throw error;
            }
        }
    }

    @Configuration
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    static class AppConfig {
        @Bean
        OrderService orderService() {
            return new OrderServiceImpl();
        }

        @Bean
        AuditAspect auditAspect() {
            return new AuditAspect();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);
            System.out.println("IS_AOP_PROXY=" + AopUtils.isAopProxy(service));
            System.out.println("RESULT=" + service.submit("A01"));
        }
    }
}
```

Chạy tại thư mục có `pom.xml`:

```bash
mvn -q compile exec:java
```

Phần stdout do chương trình in, theo đúng thứ tự:

```text
IS_AOP_PROXY=true
BEFORE submit
TARGET submit A01
AFTER OK:A01
RESULT=OK:A01
```

Giải thích luồng:

1. `AnnotationConfigApplicationContext` tạo bean `orderService` và `auditAspect`. `@EnableAspectJAutoProxy` bật việc phát hiện `@Aspect` bean và tạo proxy khi phù hợp.
2. `@Bean AuditAspect` đăng ký aspect với container; chỉ đặt `@Aspect` lên một lớp **chưa** tự biến lớp đó thành Spring bean.
3. `@Around("execution(* demo..*.submit(..))")` áp dụng cho các lần **thực thi** phương thức `submit` phù hợp trong package `demo`. Khi client lấy bean từ context, lời gọi đến proxy được chặn.
4. Advice in `BEFORE`, gọi `pjp.proceed()` để tiếp tục tới lời gọi trong chuỗi và cuối cùng tới target; target in `TARGET` rồi trả `OK:A01`.
5. Advice in `AFTER` và trả lại **chính giá trị** từ `proceed()`; client cuối cùng in `RESULT`. Với target ném lỗi, nhánh `catch` in lỗi rồi ném lại, không nuốt exception.

Trong `@Around`, quên gọi `proceed()` có nghĩa target có thể **không được chạy**; gọi `proceed()` nhiều lần có thể khiến target được thực hiện nhiều lần. Đây là quyền điều khiển mạnh của around advice, nên cần chủ đích. Nếu chỉ cần ghi sự kiện trước lời gọi, dùng `@Before` dễ đọc hơn; nếu chỉ cần quan sát kết quả thành công, cân nhắc `@AfterReturning`.

**Giới hạn của output:** dòng trên là các dòng do ví dụ tự in. Thông báo từ Maven, thư viện logging hoặc môi trường chạy có thể xuất hiện thêm tùy thiết lập; chúng không thay đổi thứ tự dòng quan sát được trong ví dụ.

## 5. Khi nào advice được chọn?

Spring cần đồng thời thỏa các điều kiện: bean đi qua cơ chế auto-proxy; lời gọi tới đối tượng proxy; phương thức có thể được proxy chặn; và pointcut khớp lần thực thi đó. Các cách viết pointcut Spring AOP thường gặp:

| Biểu thức | Ý nghĩa trong Spring AOP |
| --- | --- |
| `execution(* demo..service.*.*(..))` | Method execution của kiểu thuộc package `demo..service`, mọi tên phương thức và tham số |
| `execution(public * demo..*Service.*(..))` | Các method execution public ở kiểu có tên kết thúc bằng `Service` thuộc `demo` và package con |
| `@annotation(demo.TraceCall)` | Method execution có annotation `@TraceCall` phù hợp |
| `within(demo..service..*)` | Thu hẹp nơi khai báo kiểu nằm trong `demo..service` |
| `bean(orderService)` | Giới hạn theo tên Spring bean; đây là phần mở rộng riêng của Spring AOP |

`execution` là lựa chọn trung tâm khi nói đến **lời thực thi phương thức**. `bean(...)` phân biệt được nhiều bean cùng kiểu. `@annotation` hữu ích khi chỉ muốn chặn một tập phương thức được gắn nhãn; cần chú ý annotation đặt trên interface hay implementation và cơ chế proxy có thể ảnh hưởng cách nhận diện, nên kiểm tra bằng test thực tế.

Ví dụ tổ hợp:

```java
@Around("execution(public * demo..service..*Service.*(..)) && bean(*Service)")
public Object monitorService(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
```

Đây chỉ là **phương thức advice minh họa**, phải nằm trong một `@Aspect` bean và cần import phù hợp. Không nên dùng pointcut quá rộng như `execution(* *(..))` cho tất cả bean khi mục tiêu chỉ là một nhóm service.

Spring AOP không hỗ trợ các AspectJ designator như `call`, `get`, `set` để chặn phương thức được gọi tại một vị trí mã nguồn hay thao tác field. Thêm chúng vào Spring AOP pointcut có thể gây lỗi phân tích biểu thức. Cũng vì cơ chế proxy, Spring AOP không thay bytecode của mọi đối tượng `new` trong chương trình.

## 6. Self-invocation: trường hợp hay gây hiểu nhầm nhất

Hãy xem một bean:

```java
class BillingService {
    public void checkout() {
        this.charge();          // gọi trực tiếp trên target
    }

    public void charge() {
        System.out.println("charge");
    }
}
```

Nếu một client gọi `billingService.checkout()` **qua proxy**, advice khớp `checkout()` có thể chạy. Nhưng sau khi target đã vào `checkout()`, lời gọi `this.charge()` đi **thẳng trên đối tượng target**, không quay lại proxy; do đó advice chỉ khớp `charge()` sẽ **không** được kích hoạt trong đường đi này.

```text
Từ client:
client -> proxy.checkout() -> advice(checkout) -> target.checkout()
                                                    |
                                                    | this.charge()
                                                    v
                                                target.charge()
                                           (không qua proxy lần hai)

Một lời gọi độc lập:
client -> proxy.charge() -> advice(charge) -> target.charge()
```

Ngay cả khi đặt `proxyTargetClass=true`, nguyên tắc self-invocation vẫn giữ nguyên. Cách giải quyết thường rõ ràng nhất là **tách thao tác cần chặn sang một Spring bean khác**, rồi inject bean đó để lời gọi đi qua proxy. Nếu buộc phải gọi lại chính proxy, có các kỹ thuật như self-injection qua interface hoặc `AopContext.currentProxy()` với `exposeProxy=true`, nhưng chúng tạo sự phụ thuộc vào AOP và dễ gây rối khi quản lý bean; chỉ dùng sau khi cân nhắc cấu trúc thiết kế.

Một biến thể cùng bản chất: tạo trực tiếp `new OrderServiceImpl()`, truyền target thô thay cho bean do Spring cấp, hoặc gọi phương thức trong constructor trước khi proxy hoàn tất. Các lời gọi đó không có đường đi `client → Spring proxy` để advice chặn.

## 7. Phân biệt proxy, target và dữ liệu lời gọi khi gỡ lỗi

Trong advice, Spring cung cấp các thông tin hữu ích:

- `pjp.getSignature().getName()`: tên phương thức được chặn.
- `pjp.getArgs()`: tham số lời gọi; cân nhắc che thông tin nhạy cảm trước khi log.
- `pjp.getThis()`: proxy tiếp nhận lời gọi.
- `pjp.getTarget()`: đối tượng target đứng sau proxy.
- `pjp.proceed()`: chuyển tiếp qua phần còn lại của chuỗi advice tới target, nếu có.

Ở một bean thực tế, `pjp.getThis() == pjp.getTarget()` thường là `false`. Spring hỗ trợ `this(Type)` để ràng buộc kiểu **proxy** và `target(Type)` để ràng buộc kiểu **target** trong pointcut; điều này đặc biệt đáng lưu ý khi JDK proxy chỉ triển khai interface.

Có thể kiểm tra bean ở Java:

```java
Object bean = context.getBean("orderService");
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

Đây là **đoạn bổ sung** cho ví dụ trước; cần `import org.springframework.aop.support.AopUtils;` (đã có trong ví dụ). Các hàm kiểm tra loại proxy giúp chẩn đoán, nhưng **một bean là proxy không bảo đảm mọi method đều có advice**. Còn phải kiểm tra pointcut và đường đi lời gọi.

## 8. Các tình huống Spring thực tế

**Transaction:** `@Transactional` ở chế độ proxy thường khởi động/kết thúc transaction qua interceptor khi lời gọi vào proxy. Đặt `@Transactional` trên một method rồi gọi nó bằng `this.method()` từ cùng bean không tạo lời gọi proxy mới. Vì vậy việc “annotation đã có nhưng transaction mới không bắt đầu” có thể xuất phát từ self-invocation, chứ không phải lỗi annotation.

**Caching:** Với cơ chế proxy của `@Cacheable`, lời gọi bên ngoài qua bean proxy có thể được tra cache trước khi target thực thi. Một lần gọi nội bộ `this.load()` thường đi thẳng tới implementation và bỏ qua interceptor cache trên method đó. Đặt annotation không đồng nghĩa mọi đường gọi tới method đều được cache.

**Asynchronous execution:** `@Async` cũng thường dựa vào proxy. Gọi nội bộ qua `this` có thể không chuyển tác vụ sang executor như kỳ vọng. Để kiểm tra, quan sát thread tại nơi gọi và bên trong method được advice, với lưu ý thứ tự các interceptor và thiết lập Spring thực tế.

Ba ví dụ trên cùng nhấn mạnh một quy luật Spring: hành vi xuyên suốt được kích hoạt tại **ranh giới gọi qua proxy**. Các annotation cụ thể có cơ chế và điều kiện riêng; không suy rằng mọi advice hoặc mọi annotation đều chạy giống nhau.

## 9. Thứ tự interceptor nhìn từ đường đi proxy

Khi hai `@Around` advice cùng chọn một method, hãy xem chúng như **hai lớp bao quanh** lời gọi. Giả sử aspect A được ưu tiên cao hơn aspect B (chẳng hạn `@Order(1)` và `@Order(2)`), cả hai đều `proceed()` đúng một lần và không có interceptor khác thay đổi luồng, trace thường là:

```text
A before → B before → target → B after → A after
```

Giá trị `@Order` nhỏ hơn có độ ưu tiên cao hơn, nên A đi vào trước và đi ra sau. Nếu target ném ngoại lệ, phần `after` đặt trong `finally` vẫn chạy theo chiều thoát ngược; đoạn chỉ chạy sau `proceed()` thành công sẽ không chạy khi lỗi truyền lên. Đây là lý do cần nhìn **chuỗi interceptor và các nhánh thành công/thất bại**, thay vì suy thứ tự từ vị trí phương thức advice trong source.

Spring có thể ghép transaction, cache hay các advisor khác vào cùng proxy. Khi cần audit *sau commit* hoặc đo chính xác vùng transaction, phải kiểm tra thứ tự advisor thực tế; một dòng log sau `proceed()` không mặc nhiên chứng minh commit thành công.

## 10. Checklist chẩn đoán khi “Spring AOP không chạy”

1. **Bean có do Spring quản lý?** Kiểm tra client lấy bean từ injection/context, không tự `new` đối tượng rồi kỳ vọng proxy.
2. **Aspect có được đăng ký?** Có `@Aspect` và là một Spring bean (ví dụ `@Component` được component-scan hoặc `@Bean`). Cấu hình đã bật hỗ trợ `@AspectJ` và dependency `aspectjweaver` chưa?
3. **Lấy được proxy chưa?** Dùng `AopUtils.isAopProxy(bean)`. Nếu `false`, kiểm tra context/configuration và việc advisor có áp dụng cho bean.
4. **Đang gọi qua proxy hay `this`?** Đặt điểm dừng/trace tại caller, target và advice để xác định đường đi.
5. **Pointcut có thật sự khớp method không?** Rà package, kiểu, tên, modifiers, tham số, annotation và tên bean. `execution` mô tả *execution*, không phải vị trí *call*.
6. **Method có thể bị proxy chặn?** Kiểm tra interface khi dùng JDK proxy; với class-based proxy kiểm tra `final`, `private`, visibility và các giới hạn override.
7. **Advice có gọi `proceed()`?** Với `@Around`, không tiếp tục thì target có thể không chạy; nếu catch exception rồi không ném lại thì caller sẽ nhận hành vi khác.
8. **Có nhiều interceptor cùng khớp?** Kiểm tra `@Order`, transaction/cache/async và các aspect khác để hiểu thứ tự trước/sau.

Cách kiểm thử đáng tin cậy là lấy bean từ chính Spring context trong test, gọi qua tham chiếu do context cấp, quan sát một hành vi ngoài target và đối chiếu với đường gọi trực tiếp vào target. Việc test đơn thuần `new ServiceImpl()` không kiểm tra Spring AOP.

## 11. Tự kiểm tra

**Tình huống A.** Client inject `OrderService`, gọi `submit()`; method được một `@Around` pointcut phù hợp chặn. Dấu vết kỳ vọng? — Trước target có logic advice; advice gọi `proceed()`; target chạy; sau đó advice xử lý kết quả trước khi trả caller.

**Tình huống B.** `checkout()` gọi `this.charge()` trong cùng target, trong khi advice chỉ khớp `charge()`. Advice chạy không? — Không cho lời gọi `this.charge()` này, vì không đi qua proxy. Gọi `charge()` từ một bean khác qua proxy thì có thể chạy.

**Tình huống C.** Đổi từ JDK proxy sang CGLIB thì `this.charge()` tự được chặn? — Không. Đổi loại proxy không thay đổi đường đi self-invocation.

**Tình huống D.** `@Aspect` được đặt lên class nhưng không đưa class ấy vào Spring context. Advice có tự chạy? — Không. Aspect phải được Spring đăng ký và hỗ trợ auto-proxy được bật phù hợp.

**Tình huống E.** Aspect dùng `@Around` chỉ in “before” rồi return `null` mà không gọi `proceed()`. Điều gì xảy ra? — Target có thể không được thực thi; caller nhận `null` (hoặc không tương thích với return type), vì around advice quyết định có tiếp tục hay không.

## Tài liệu Spring tham khảo

- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB và self-invocation.
- [Spring Framework — @AspectJ support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html): bật proxy, đăng ký aspect và advice.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): method-execution pointcuts được Spring hỗ trợ.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): `proceed()`, kết quả, exception và thứ tự.

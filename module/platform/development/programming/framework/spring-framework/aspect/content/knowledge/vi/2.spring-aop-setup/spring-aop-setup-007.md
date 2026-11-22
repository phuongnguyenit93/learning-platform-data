# Phân biệt mặc định proxy của Spring Framework và cấu hình từ Spring Boot

## 1. Bài toán: cùng một Spring bean, vì sao có hai kiểu proxy?

Khi dùng Spring AOP, một bean thỏa điều kiện advice có thể được thay bằng **AOP proxy**. Điều dễ nhầm là cấu hình mặc định của **Spring Framework thuần** và **Spring Boot auto-configuration** khác nhau:

- Trong **Spring Framework**, cơ chế proxy mặc định chọn **JDK dynamic proxy** nếu target triển khai interface; nếu target không có interface phù hợp, Spring dùng **class-based proxy (CGLIB)**.
- Trong **Spring Boot**, auto-configuration AOP mặc định đặt `spring.aop.proxy-target-class=true`, tức ưu tiên **class-based proxy (CGLIB)**, kể cả target có interface.
- Với ứng dụng Boot, đặt `spring.aop.proxy-target-class=false` cho phép Spring dùng **JDK dynamic proxy khi target có interface**; nếu target không có interface, class-based proxy vẫn cần thiết.

Đây là khác biệt của **cấu hình Spring AOP**, không phải hai hệ thống AOP khác nhau. Boot xây dựng trên Spring Framework và bật một lựa chọn proxy khác trong phần auto-configuration.

**Phạm vi bài:** cách bật AOP, cơ chế chọn JDK/CGLIB, cấu hình Boot/Framework, kiểm tra thực tế và các hệ quả với bean Spring. Các khái niệm Aspect tổng quát không được mở rộng ở đây.

## 2. Bảng so sánh mặc định

Giả sử Spring AOP thực sự cần tạo proxy cho bean (có advisor áp dụng; bean do Spring quản lý):

| Target bean | Spring Framework thuần, cấu hình mặc định | Spring Boot có AOP auto-configuration mặc định | Boot với `spring.aop.proxy-target-class=false` |
| --- | --- | --- | --- |
| `PaymentServiceImpl implements PaymentService` | JDK dynamic proxy | CGLIB class-based proxy | JDK dynamic proxy |
| `ReportService` không implements interface | CGLIB class-based proxy | CGLIB class-based proxy | CGLIB class-based proxy |
| `final class` cần class-based proxy | Không thể tạo proxy subclass bình thường | Không thể tạo proxy subclass bình thường | Nếu không có interface để proxy, vẫn không thể tạo proxy subclass |
| Bean không có advisor nào áp dụng | Thường không có AOP proxy | Thường không có AOP proxy | Thường không có AOP proxy |

**Điều kiện quan trọng:** bảng nói về proxy tạo bởi cơ chế Spring AOP được cấu hình như mô tả. Một ứng dụng có thể có các loại proxy khác (ví dụ scoped proxies, proxy tùy biến hoặc hạ tầng khác), và một cấu hình mạnh hơn có thể làm thay đổi lựa chọn cuối cùng. Không suy loại proxy chỉ từ việc project có hoặc không có Spring Boot.

```text
                     Có cần Spring AOP proxy không?
                                  |
                           Có advisor khớp
                                  |
                             +----v----+
                             | Target  |
                             +----+----+
                                  |
                +-----------------+--------------------+
                |                                      |
       class-based được yêu cầu?                     Không
        (Boot thường true)                             |
                |                                      v
                v                           Target có interface?
             CGLIB                              /          \
                                             Có              Không
                                             |                 |
                                             v                 v
                                      JDK dynamic proxy       CGLIB
```

Sơ đồ mô tả quy tắc chung khi chưa có cấu hình đặc biệt hoặc override khác. `proxy-target-class=false` **không** có nghĩa “cấm CGLIB”; nó có nghĩa “không ép mọi bean dùng target-class proxy”.

## 3. Mặc định của Spring Framework thuần

Khi cấu hình `@EnableAspectJAutoProxy` trong ứng dụng Spring Framework dùng `AnnotationConfigApplicationContext`, thuộc tính `proxyTargetClass` mặc định là `false`:

```java
@Configuration
@EnableAspectJAutoProxy // proxyTargetClass mặc định false
class AopConfig {
}
```

Dạng ghi rõ ý định:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
class AopConfig {
}
```

Với cấu hình này:

1. Bean triển khai một hoặc nhiều interface: proxy thường là đối tượng JDK dynamic proxy, chỉ triển khai các interface được proxy công bố.
2. Bean không có interface có thể proxy qua JDK: Spring dùng proxy dựa trên lớp để có thể áp dụng advice lên method phù hợp.
3. Nếu chủ động đặt `@EnableAspectJAutoProxy(proxyTargetClass = true)`: Spring chọn class-based proxy, cả khi bean triển khai interface.

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
class ClassProxyConfig {
}
```

**Bật auto-proxy không đồng nghĩa mọi bean đều bị proxy.** `@EnableAspectJAutoProxy` bật xử lý advisor/aspect; Spring còn phải tìm thấy advice phù hợp với bean. Một lớp chỉ có `@Aspect` mà không được đăng ký thành Spring bean sẽ không tự kích hoạt advice.

Với XML, thuộc tính tương ứng là `<aop:aspectj-autoproxy proxy-target-class="true"/>`. Điều này cũng chỉ ảnh hưởng cơ chế tạo proxy; nó không mở rộng Spring AOP thành chặn constructor hoặc truy cập field.

### Vì sao Spring Framework ưu tiên JDK khi có interface?

JDK proxy triển khai interface mà caller sử dụng; caller gọi qua interface và Spring chèn advice trước khi chuyển đến target. Điều này phù hợp với code inject theo abstraction:

```java
public interface PaymentService {
    String pay(String id);
}

// Dùng interface trong client:
private final PaymentService paymentService;
```

Một JDK proxy **không phải instance của implementation class**. Vì vậy inject/ép kiểu theo `PaymentServiceImpl` có thể thất bại ngay cả khi inject `PaymentService` hoàn toàn ổn.

## 4. Mặc định Spring Boot và điều kiện auto-configuration

Spring Boot có cấu hình AOP tự động. Trong các phiên bản Spring Boot 3.x và 4.x được tài liệu chính thức mô tả, các giá trị thông dụng là:

```properties
spring.aop.auto=true
spring.aop.proxy-target-class=true
```

Hai property giải quyết **hai câu hỏi khác nhau**:

- `spring.aop.auto`: Boot có tự động bật hỗ trợ `@AspectJ` auto-proxy khi điều kiện classpath phù hợp hay không. Mặc định `true`.
- `spring.aop.proxy-target-class`: khi Boot thiết lập AOP auto-proxy, có **ưu tiên proxy bằng subclass của target class** hay không. Mặc định `true`.

Thường chỉ cần thêm dependency `spring-boot-starter-aop` vào dự án Spring Boot; starter đưa hỗ trợ Spring AOP cùng các thư viện AspectJ cần cho kiểu pointcut `@AspectJ` lên classpath. Boot có thể tự bật auto-proxy khi AspectJ hiện diện, nên **không cần tự khai báo `@EnableAspectJAutoProxy` trong trường hợp tiêu chuẩn**.

Ví dụ Maven sử dụng Spring Boot 3.3.x:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

Đây là **đoạn dependency** dành cho một project đã quản lý version qua Boot parent hoặc BOM. Không tự thêm version vào dependency này nếu Boot dependency management đã quản lý nó.

Cách đổi về lựa chọn JDK proxy cho target có interface trong `src/main/resources/application.properties`:

```properties
spring.aop.proxy-target-class=false
```

Hoặc `application.yml`:

```yaml
spring:
  aop:
    proxy-target-class: false
```

Với `false`, cần nhớ rằng target không có interface vẫn phải sử dụng class-based proxy nếu muốn Spring AOP chặn method của nó.

### Vậy có nên thêm `@EnableAspectJAutoProxy` vào ứng dụng Boot?

Thông thường **không cần** nếu auto-configuration AOP của Boot đã hoạt động. Có thể khai báo tường minh khi ứng dụng cần kiểm soát riêng, nhưng kết quả phải đánh giá trên **toàn bộ cấu hình auto-proxy của application context**.

Một lỗi dễ mắc:

```java
// Trong ứng dụng Boot vẫn để mặc định
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
class ExplicitAopConfig {
}
```

Nhiều người kỳ vọng đoạn trên ép mọi bean quay về JDK. Tuy nhiên Spring có cơ chế **hợp nhất / nâng cấp auto-proxy creator**; cấu hình `proxyTargetClass=true` từ một nơi khác có thể thắng cấu hình `false`. Để chọn JDK trong Boot tiêu chuẩn, cấu hình trực tiếp `spring.aop.proxy-target-class=false` và tránh nơi khác ép target-class proxy; xác minh loại proxy sau khi context khởi động.

Ngược lại, đặt `spring.aop.auto=false` chỉ **tắt việc Boot tự động bật @AspectJ auto-proxy**. Nó không phải nút “cấm toàn bộ proxy” cho ứng dụng: cấu hình `@EnableAspectJAutoProxy` tường minh, `@EnableTransactionManagement`, proxy tùy biến hoặc cơ chế hạ tầng khác vẫn có thể tạo proxy theo điều kiện riêng.

## 5. Thí nghiệm chạy được: cùng bean trong Spring Framework và Boot

Thí nghiệm sử dụng **Java 17+, Maven, Spring Boot 3.3.13** (bao gồm Spring Framework 6.x theo dependency management của Boot). Có **một service triển khai interface** và **một aspect**. Hai context được khởi chạy riêng biệt trong cùng chương trình:

- `CORE`: `AnnotationConfigApplicationContext` + `@EnableAspectJAutoProxy(proxyTargetClass=false)`; không bật Boot auto-configuration.
- `BOOT`: `SpringApplicationBuilder` + Boot `@EnableAutoConfiguration`; nhận giá trị `spring.aop.proxy-target-class` từ property/environment.
- Cùng một service và aspect được khai báo trong `SharedBeans`, để khác biệt đến từ cấu hình context chứ không phải khác biệt code nghiệp vụ.

Cấu trúc:

```text
spring-proxy-defaults/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── aop/
                    └── ProxyDefaultsDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-proxy-defaults</artifactId>
    <version>1.0-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/example/aop/ProxyDefaultsDemo.java`:

```java
package example.aop;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.aop.support.AopUtils;
import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

public class ProxyDefaultsDemo {

    public interface PaymentService {
        String pay(String orderId);
    }

    public static class PaymentServiceImpl implements PaymentService {
        @Override
        public String pay(String orderId) {
            System.out.println("TARGET " + orderId);
            return "PAID:" + orderId;
        }
    }

    @Aspect
    public static class AuditAspect {
        @Before("execution(* example.aop..*.pay(..))")
        public void beforePay(JoinPoint joinPoint) {
            System.out.println("ADVICE " + joinPoint.getSignature().getName());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SharedBeans {
        @Bean
        PaymentService paymentService() {
            return new PaymentServiceImpl();
        }

        @Bean
        AuditAspect auditAspect() {
            return new AuditAspect();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    @Import(SharedBeans.class)
    public static class CoreConfig {
    }

    @SpringBootConfiguration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    @Import(SharedBeans.class)
    public static class BootConfig {
    }

    private static void inspect(String mode, Object bean) {
        System.out.println(mode
                + " aop=" + AopUtils.isAopProxy(bean)
                + ", jdk=" + AopUtils.isJdkDynamicProxy(bean)
                + ", cglib=" + AopUtils.isCglibProxy(bean));
    }

    public static void main(String[] args) {
        try (var core = new AnnotationConfigApplicationContext(CoreConfig.class)) {
            PaymentService bean = core.getBean(PaymentService.class);
            inspect("CORE", bean);
            System.out.println("CORE_RESULT " + bean.pay("A01"));
        }

        try (var boot = new SpringApplicationBuilder(BootConfig.class)
                .bannerMode(Banner.Mode.OFF)
                .web(WebApplicationType.NONE)
                .logStartupInfo(false)
                .run(args)) {
            PaymentService bean = boot.getBean(PaymentService.class);
            inspect("BOOT", bean);
            System.out.println("BOOT_RESULT " + bean.pay("B02"));
        }
    }
}
```

**Lần 1 — Boot với mặc định:**

```bash
mvn -q compile exec:java -Dexec.mainClass=example.aop.ProxyDefaultsDemo
```

Các dòng quan sát trọng tâm từ chương trình:

```text
CORE aop=true, jdk=true, cglib=false
ADVICE pay
TARGET A01
CORE_RESULT PAID:A01
BOOT aop=true, jdk=false, cglib=true
ADVICE pay
TARGET B02
BOOT_RESULT PAID:B02
```

**Lần 2 — yêu cầu Boot chọn JDK proxy khi có interface:**

```bash
mvn -q compile exec:java -Dexec.mainClass=example.aop.ProxyDefaultsDemo -Dexec.args=--spring.aop.proxy-target-class=false
```

Các dòng quan sát trọng tâm:

```text
CORE aop=true, jdk=true, cglib=false
ADVICE pay
TARGET A01
CORE_RESULT PAID:A01
BOOT aop=true, jdk=true, cglib=false
ADVICE pay
TARGET B02
BOOT_RESULT PAID:B02
```

Các đoạn trên liệt kê dòng do chương trình tự in; Boot hoặc Maven có thể có thêm logging tùy môi trường. `--spring.aop.proxy-target-class=false` được truyền tới `SpringApplicationBuilder.run(args)` của context Boot; context `CORE` không sử dụng cơ chế cấu hình property của Boot.

**Vì sao thử nghiệm chứng minh được khác biệt?** Hai context có cùng target type `PaymentServiceImpl implements PaymentService`, cùng `@Aspect`, cùng pointcut. Chỉ cơ chế đăng ký AOP khác: Spring Framework thuần dùng mặc định interface proxy, còn Boot áp giá trị property mặc định của mình. `AopUtils` đo loại proxy trên **bean lấy từ container**, không kiểm tra class `PaymentServiceImpl` tạo bằng `new`.

## 6. Khi đổi kiểu proxy, điều gì thực sự thay đổi?

### 6.1. Khả năng inject và ép kiểu

Với **JDK dynamic proxy**:

```java
PaymentService service = context.getBean(PaymentService.class);
// OK: proxy triển khai interface PaymentService.

// Không giả định mã sau hợp lệ:
PaymentServiceImpl impl = (PaymentServiceImpl) service;
```

Cast sang implementation ở dòng thứ hai thường ném `ClassCastException` nếu `service` là JDK proxy. Với **CGLIB class-based proxy**, proxy là subclass của implementation (nếu class có thể subclass), nên tham chiếu kiểu implementation có thể hoạt động.

Vì vậy, khi thay `spring.aop.proxy-target-class=true` thành `false` trong Boot, cần kiểm tra các nơi inject trực tiếp implementation hoặc dùng `getBean(Implementation.class)`. Việc cấu hình AOP có thể ảnh hưởng khả năng resolve bean theo kiểu mà application sử dụng.

### 6.2. Phương thức có thể được advice

- JDK proxy **công bố interface**; caller thông thường gọi qua interface đã được proxy.
- CGLIB proxy dựa trên subclass, có thể xử lý lời gọi tới phương thức của target class phù hợp với giới hạn proxying, kể cả phương thức public không khai báo trên business interface.
- `final class` không thể tạo CGLIB subclass; `final method` không thể được advice qua override; `private method` và phương thức không nhìn thấy từ subclass cũng không thể advice bằng cách đó.
- **Đổi sang CGLIB không giải quyết self-invocation**: `this.someMethod()` bên trong target vẫn không đi qua Spring proxy một lần nữa.

Với phương thức package-private/protected, những điều kiện về visibility, kiểu proxy và phiên bản Spring có thể quyết định kết quả; đừng diễn dịch “CGLIB chặn mọi method” như một lời hứa tuyệt đối.

### 6.3. Hiệu năng và tương thích

Không nên chọn JDK hay CGLIB chỉ bằng giả định rằng kiểu nào nhanh hơn. Chi phí advice, reflection/dispatch, JVM tối ưu hóa và workload thực tế đều có thể lớn hơn chênh lệch proxy. Hãy dùng mặc định phù hợp, ưu tiên API ổn định, và benchmark trên ứng dụng cụ thể khi thật sự có yêu cầu hiệu năng.

Class-based proxy còn có thể bị ảnh hưởng bởi module-path và Java module access vì cần sinh subclass. Những kiểu nằm trong module/package không mở để truy cập cần kiểm tra giới hạn JVM tương ứng. Kết quả lỗi thường liên quan khả năng subclass/access, không phải biểu thức pointcut.

## 7. Auto-configuration chồng nhau: vì sao đặt `false` đôi khi vẫn là CGLIB?

Trong ứng dụng Spring có thể tồn tại nhiều nguồn cấu hình auto-proxy như `@EnableAspectJAutoProxy`, hạ tầng transaction, các thành phần XML và cấu hình khác. Spring thường thống nhất chúng về một auto-proxy creator, với các thiết lập mạnh hơn như `proxyTargetClass=true` có thể chi phối toàn cục. Vì vậy:

```java
// Ví dụ một nơi ép class-based proxy:
@EnableAspectJAutoProxy(proxyTargetClass = true)
class ForceClassProxy {
}
```

Nếu bean cấu hình này được nạp, việc ứng dụng Boot đặt `spring.aop.proxy-target-class=false` không có nghĩa chắc chắn mọi proxy lập tức thành JDK. Cần tìm mọi nơi ép target-class proxy trong **application context cụ thể**, không chỉ xem một dòng property.

Lưu ý theo phiên bản: Spring Framework **7.0 trở lên** còn có `@Proxyable` để chọn proxy type cho từng bean trong những trường hợp được hỗ trợ; quy tắc này là khả năng mới và **không áp dụng mặc nhiên cho Spring Framework 6.x / Spring Boot 3.x** của ví dụ. Nếu dùng phiên bản đó, phải xem tài liệu đúng release để xác định độ ưu tiên cấu hình.

### Property được nạp từ đâu?

Trong Boot, property có thể được khai báo qua `application.properties`, `application.yml`, profile-specific configuration, biến môi trường, tham số command line và các nguồn `Environment` khác. Giá trị thực tế sau áp dụng thứ tự ưu tiên có thể khác file bạn đang mở.

Ví dụ biến môi trường chuẩn theo tên property:

```bash
SPRING_AOP_PROXY_TARGET_CLASS=false
```

Với ví dụ chạy dòng lệnh ở phần 5, giá trị `--spring.aop.proxy-target-class=false` chỉ tác động đến context Boot nhận `args`. Nếu đang chẩn đoán ứng dụng triển khai thật, kiểm tra giá trị của `Environment.getProperty("spring.aop.proxy-target-class")` và kết hợp kiểm tra bean proxy; đừng dựa duy nhất vào file cấu hình.

### Kiểm tra trạng thái hỗ trợ AOP

- `spring.aop.auto=true` và có AspectJ trên classpath: Boot có thể tự bật xử lý `@AspectJ`.
- `spring.aop.auto=false`: dừng phần Boot tự động thêm xử lý `@AspectJ`; các nguồn cấu hình AOP tường minh/hạ tầng khác vẫn có thể tạo proxy.
- Thiếu `spring-boot-starter-aop` không đủ để kết luận AOP bất khả thi; thư viện liên quan có thể vào classpath từ dependency khác. Kiểm tra dependency tree và cấu hình hiệu lực.
- Một bean không có AOP proxy vẫn có thể hoạt động nghiệp vụ bình thường, chỉ không đi qua chuỗi advice AOP tương ứng.

## 8. Quy trình điều tra một ứng dụng thực tế

Khi một project Boot mặc định ra CGLIB nhưng bạn kỳ vọng JDK, hoặc ngược lại:

1. **Xác định môi trường:** Spring Framework thuần hay Spring Boot? Phiên bản cụ thể? `@EnableAutoConfiguration` thực sự được chạy ở context nào?
2. **Kiểm tra classpath:** có starter AOP/AspectJ và advisor hoặc aspect bean phù hợp không?
3. **Kiểm tra cấu hình có hiệu lực:** `spring.aop.auto`, `spring.aop.proxy-target-class` và nơi khai báo `@EnableAspectJAutoProxy(proxyTargetClass=...)` / `@EnableTransactionManagement`.
4. **Xác định target có interface nào:** nếu không có, cấu hình `false` vẫn có thể cho CGLIB.
5. **Lấy đúng bean từ context:** dùng `AopUtils.isAopProxy(bean)`, `AopUtils.isJdkDynamicProxy(bean)` và `AopUtils.isCglibProxy(bean)`.
6. **Kiểm tra cách inject:** ứng dụng đang yêu cầu bean bằng interface hay implementation? Sau khi đổi loại proxy, cast và injection có tương thích không?
7. **Xem đường đi lời gọi:** self-invocation hay tạo object bằng `new` không đi qua proxy, dù proxy JDK hay CGLIB.
8. **Kiểm tra với test context thật:** thử cả property `true`/`false` và assert loại proxy cùng hành vi advice. Đừng test bằng cách gọi đối tượng thô ngoài Spring.

Ví dụ assert trong integration test, với bean đã xác nhận thực sự được áp dụng Spring AOP:

```java
Object bean = applicationContext.getBean(PaymentService.class);
assertTrue(AopUtils.isAopProxy(bean));
assertTrue(AopUtils.isJdkDynamicProxy(bean)); // Khi kỳ vọng JDK
assertFalse(AopUtils.isCglibProxy(bean));
```

Đây là **đoạn mã kiểm thử minh họa**, cần context/test imports và assertion library, không phải chương trình độc lập. Đổi kỳ vọng sang `isCglibProxy` khi test cấu hình Boot mặc định.

## 9. Lỗi nhận định thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Spring Boot cũng phải dùng JDK proxy nếu class implements interface vì Spring Framework mặc định vậy.” | Boot có thể thay lựa chọn mặc định qua AOP auto-configuration; mặc định phổ biến là CGLIB. |
| “Đặt `spring.aop.proxy-target-class=false` là toàn bộ AOP dùng JDK.” | Chỉ chọn JDK khi có interface và không có cấu hình khác ép class-based proxy. |
| “`@EnableAspectJAutoProxy(proxyTargetClass=false)` chắc chắn ghi đè mặc định Boot true.” | Nhiều thiết lập auto-proxy có thể hợp nhất; `true` từ nơi khác có thể chi phối. |
| “Spring Boot bắt buộc khai báo `@EnableAspectJAutoProxy`.” | Với starter/classpath phù hợp, Boot đã tự bật @AspectJ auto-proxy. |
| “Đổi sang CGLIB thì gọi `this.foo()` sẽ được advice.” | Self-invocation vẫn bỏ qua lời gọi qua proxy. |
| “`spring.aop.auto=false` tắt mọi cơ chế tạo proxy trong ứng dụng.” | Nó chỉ chi phối auto-configuration AOP của Boot; cấu hình và hạ tầng khác có thể tạo proxy. |
| “Bean implements interface thì nhất định là JDK proxy.” | Còn phụ thuộc cấu hình `proxyTargetClass`, auto-proxy creator và phiên bản framework. |
| “Có `@Aspect` tức là mọi bean chắc chắn có proxy.” | Aspect phải được đăng ký và pointcut/advisor phải áp dụng cho bean. |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** `UserServiceImpl implements UserService`, ứng dụng Spring Framework thuần có `@EnableAspectJAutoProxy` mặc định và pointcut phù hợp. Loại proxy dự kiến?  
**Đáp án:** JDK dynamic proxy.

**Câu 2.** Cùng bean đó trong ứng dụng Boot có `spring-boot-starter-aop`, AOP auto-configuration và không ghi đè cấu hình. Loại proxy dự kiến?  
**Đáp án:** CGLIB class-based proxy theo mặc định của Boot.

**Câu 3.** Đặt `spring.aop.proxy-target-class=false` trong Boot; bean `ReportService` không implements interface. Kết quả?  
**Đáp án:** Spring vẫn cần class-based proxy nếu advisor áp dụng; `false` không “ép JDK” khi không có interface.

**Câu 4.** Đã để Boot `spring.aop.proxy-target-class=false` nhưng bean vẫn là CGLIB. Nên kiểm tra gì?  
**Đáp án:** Target có interface không; property có hiệu lực không; có cấu hình khác ép `proxyTargetClass=true` không; bean có phải AOP proxy đúng context không; có loại proxy khác không.

**Câu 5.** Đổi từ Boot CGLIB sang JDK, một controller inject trực tiếp `UserServiceImpl` bị lỗi nhưng inject `UserService` thì ổn. Vì sao?  
**Đáp án:** JDK proxy chỉ triển khai interface, không phải subtype của implementation class.

**Câu 6.** `spring.aop.auto=false` có bảo đảm không còn proxy cho transaction hoặc các cấu hình AOP khác?  
**Đáp án:** Không. Đây là cờ cho phần tự động cấu hình @AspectJ AOP của Boot; cấu hình và hạ tầng khác có thể tạo proxy.

## 11. Tài liệu chính thức

- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): quy tắc JDK/CGLIB, giới hạn `final` và hành vi cấu hình auto-proxy.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html): `@EnableAspectJAutoProxy` và đăng ký aspect bean.
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): Boot mặc định CGLIB và cách chuyển sang JDK bằng `spring.aop.proxy-target-class=false`.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): giá trị mặc định `spring.aop.auto` và `spring.aop.proxy-target-class`.

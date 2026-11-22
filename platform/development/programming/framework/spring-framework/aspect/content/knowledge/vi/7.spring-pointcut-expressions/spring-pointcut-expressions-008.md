# `bean(...)` — chọn pointcut theo tên Spring bean

## 1. Khi nào cần `bean(...)` trong Spring AOP?

Spring AOP thường dùng biểu thức `execution(...)`, `within(...)`, `target(...)` hoặc `@annotation(...)` để chọn những *method execution* sẽ được advice. Nhưng có một nhu cầu rất đặc trưng của Spring: **hai Spring bean có cùng một lớp triển khai, cùng chữ ký method, nhưng chỉ muốn advice một bean có tên cụ thể**.

Spring cung cấp pointcut designator (PCD) **`bean`** để giải quyết trường hợp này:

```java
@Before("execution(* demo..*.process(..)) && bean(primaryJobService)")
public void audit() {
    System.out.println("AUDIT");
}
```

Đây là **đoạn advice minh họa**; method cần nằm trong một class mang `@Aspect`, class đó phải được đăng ký thành Spring bean và hỗ trợ Spring AOP phải được bật.

Trong biểu thức trên:

- `execution(* demo..*.process(..))`: chỉ chọn **method execution** có tên `process` và nằm trong phạm vi pattern.
- `bean(primaryJobService)`: chỉ chọn **Spring bean có tên `primaryJobService`**.
- `&&`: cả hai điều kiện đều phải thỏa mới áp dụng advice.

**Điểm chính:** `bean(...)` lọc theo **tên bean trong Spring container**, không lọc trực tiếp theo tên class, tên interface, tên method, tên biến Java hay giá trị `@Qualifier` bất kỳ.

Bài này chỉ bàn về **Spring AOP / Spring Framework**, không đi sâu vào các khái niệm Aspect tổng quát. `bean(...)` là một **Spring-specific extension**, không thuộc danh sách PCD tiêu chuẩn mà native AspectJ weaving có thể dùng tương đương.

## 2. Cú pháp và ý nghĩa

Cú pháp Spring AOP:

```text
bean(idOrNameOfBean)
```

Trong đó `idOrNameOfBean` là tên bean được Spring quản lý, có thể chứa ký tự đại diện `*`:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `bean(primaryJobService)` | Chọn bean mang tên `primaryJobService` |
| `bean(*Service)` | Chọn các bean có tên kết thúc bằng `Service` |
| `bean(order*)` | Chọn các bean có tên bắt đầu bằng `order` |
| `bean(*Audit*)` | Chọn các bean có tên chứa `Audit` |
| `!bean(backupJobService)` | Loại trừ bean có tên `backupJobService` |
| `bean(primaryJobService) || bean(backupJobService)` | Chọn một trong hai tên |
| `bean(*Service) && !bean(backupJobService)` | Chọn các bean hậu tố `Service`, trừ bean dự phòng |
| `bean(*Service) && execution(public * *(..))` | Chọn method public phù hợp trên các bean có hậu tố tên `Service` |

Spring hỗ trợ **wildcard đơn giản bằng `*`**, kết hợp logic với `&&`, `||`, `!`. Đây không phải biểu thức regex. Không thay `*` bằng cú pháp regex như `.*`, và không coi pattern này như đường dẫn package của `execution` hoặc `within`.

Điều kiện `bean` áp dụng ở **bean-instance/named-bean level**. Nó có thể phân biệt **hai instance bean cùng class** nếu hai bean có tên khác nhau. Đây là lý do Spring AOP hỗ trợ `bean`: Spring BeanFactory biết danh tính bean theo tên.

### Khi chỉ có `bean(...)` thì sao?

Spring AOP vẫn chỉ chạy advice trên những **method execution mà proxy có thể intercept**. Một expression như `bean(primaryJobService)` không thể khiến Spring advice constructor, field access hoặc lời gọi trên object do `new` tạo ngoài container. Nó cũng không bảo đảm mọi method của bean đều intercept được (ví dụ CGLIB không override được `final/private` method).

Trong code thực tế, nên kết hợp với `execution(...)` để chỉ rõ ranh giới method và giữ pointcut dễ đọc:

```java
@Pointcut("bean(*Service) && execution(public * demo..service..*.*(..))")
public void serviceMethodsOnNamedBeans() {
}
```

Đây là **named-pointcut minh họa**, chưa phải class độc lập. Trong Java string literal, có thể viết toán tử `&&` trực tiếp; khi cấu hình XML, phải escape thành `&amp;&amp;` hoặc dùng các toán tử từ `and/or/not` theo cú pháp hỗ trợ.

## 3. Spring bean name đến từ đâu?

Spring xác định bean name khi đăng ký bean definition. Một số cách phổ biến:

### 3.1. `@Bean` với tên tường minh

```java
@Configuration
class JobConfig {
    @Bean("primaryJobService")
    JobService primary() {
        return new JobServiceImpl("PRIMARY");
    }

    @Bean("backupJobService")
    JobService backup() {
        return new JobServiceImpl("BACKUP");
    }
}
```

Trong đoạn này, **tên bean là `primaryJobService` và `backupJobService`**. Không phải `primary`/`backup` chỉ vì đó là tên hai Java methods.

Các type `JobService` và `JobServiceImpl` sẽ được định nghĩa đầy đủ trong chương trình ở phần 5. Đoạn trên chỉ minh họa cách đặt tên qua `@Bean`.

### 3.2. `@Bean` không có tên tường minh

```java
@Configuration
class JobConfig {
    @Bean
    JobService primaryJobService() {
        return new JobServiceImpl("PRIMARY");
    }
}
```

Trong cách dùng thông thường, bean mang tên mặc định là **`primaryJobService`**, trùng với tên method khai báo `@Bean`.

### 3.3. Component scanning

```java
@Service("inventoryService")
public class InventoryService {
    public void check() {
        System.out.println("CHECK");
    }
}
```

Đây là class minh họa. Nếu Spring component-scan phát hiện class, tên tường minh là `inventoryService`. Khi không cung cấp tên tường minh, Spring thường sinh tên theo quy tắc đặt tên bean (chẳng hạn `InventoryService` thành `inventoryService`); có những trường hợp tên viết hoa đặc biệt, custom `BeanNameGenerator` hoặc cấu hình khác. Với pointcut dựa vào tên, **nên xác minh tên thực tế** thay vì đoán từ class.

### 3.4. Bean alias và đặt tên lại

Spring có thể hỗ trợ **nhiều tên/alias trỏ tới cùng một bean definition**. Nếu ứng dụng có alias hoặc dùng registry tùy biến, cần kiểm tra tên và alias mà Spring AOP matcher thực tế nhận diện, cũng như ảnh hưởng của việc đổi tên bean. Một alias **không phải** một target instance mới.

Không nên dựa vào chi tiết alias không được kiểm thử như một bảo đảm nghiệp vụ; hãy chọn một tên bean ổn định, đặt tường minh và test pointcut trong context thật. Đổi `@Bean("primaryJobService")` thành tên khác **có thể làm advice ngừng khớp** dù class và method không đổi.

## 4. Vì sao `bean(...)` khác `execution(...)`, `within(...)` và `target(...)`?

Giả sử hai bean khác nhau nhưng cùng target class:

```text
Spring ApplicationContext
   |
   +-- bean name = primaryJobService
   |      class = JobServiceImpl
   |      method = process(String)
   |
   +-- bean name = backupJobService
          class = JobServiceImpl
          method = process(String)
```

Nếu dùng:

```java
@Before("execution(* demo..*.process(..))")
```

cả hai bean có thể được advice, vì Spring chọn theo **method execution** và target type/signature phù hợp.

Nếu dùng:

```java
@Before("execution(* demo..*.process(..)) && bean(primaryJobService)")
```

chỉ bean có tên `primaryJobService` được chọn.

| Điều kiện | Đang chọn theo | Có thể tách hai bean cùng class khác tên? |
| --- | --- | --- |
| `execution(* demo..*.process(..))` | Method signature / execution | Không, nếu các method tương ứng giống nhau |
| `within(demo..*)` | Kiểu/phạm vi khai báo method | Không, nếu cùng implementation |
| `target(demo.JobServiceImpl)` | Kiểu của target object | Không, nếu cả hai là instance cùng class |
| `this(demo.JobService)` | Kiểu của Spring AOP proxy | Không, nếu cả hai proxy cùng expose interface đó |
| `@annotation(demo.Audited)` | Annotation trên method execution | Không, nếu cùng một method được gắn annotation |
| **`bean(primaryJobService)`** | **Tên của Spring bean** | **Có** |

Không nên viết `bean(JobServiceImpl)` nếu ý định là “chọn mọi bean có class `JobServiceImpl`”. Biểu thức đó sẽ tìm bean **tên `JobServiceImpl`**, không phải tự kiểm tra class. Nếu muốn chọn theo type, sử dụng `target(...)`, `this(...)` hoặc `execution(...)` theo mục đích.

### Đặc điểm Spring-specific

Spring Framework xác nhận `bean(...)` là **extension dành cho Spring AOP**, bởi framework gắn chặt với BeanFactory và có thể biết bean name. Native AspectJ weaving tập trung vào join point/type-level semantics và **không có PCD `bean` tương đương**. Aspect được khai báo bằng `@Aspect` **và do Spring AOP xử lý** vẫn có thể dùng extension này; điều không tương thích là chuyển nguyên pointcut sang AspectJ compiler/weaver để weaving ngoài Spring AOP.

## 5. Demo chạy được: hai bean cùng implementation nhưng advice khác nhau

Ví dụ sử dụng **Java 17+, Maven, Spring Framework 6.2.19**. Nó tạo **hai Spring application context độc lập** để cho thấy hai biểu thức:

1. **Exact:** `bean(primaryJobService)` chỉ áp dụng cho một bean.
2. **Wildcard:** `bean(*JobService)` áp dụng cho cả hai bean có hậu tố tên `JobService`.

Cả hai context đăng ký **cùng hai target classes/implementations**, chỉ đổi `@Aspect` bean. Code sử dụng `@Bean` có tên tường minh để không phụ thuộc bean-name generator. Target `JobServiceImpl` implement interface `JobService` nên ví dụ chạy được với JDK dynamic proxy mặc định của cấu hình Spring Framework.

### 5.1. Cấu trúc dự án

```text
spring-aop-bean-pointcut/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanPointcutDemo.java
```

### 5.2. Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-bean-pointcut</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.19</version>
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
                    <mainClass>demo.BeanPointcutDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. Tệp `src/main/java/demo/BeanPointcutDemo.java`

```java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

public class BeanPointcutDemo {

    public interface JobService {
        String process(String id);
    }

    public static class JobServiceImpl implements JobService {
        private final String label;

        public JobServiceImpl(String label) {
            this.label = label;
        }

        @Override
        public String process(String id) {
            System.out.println("TARGET " + label + " " + id);
            return label + ":" + id;
        }
    }

    @Aspect
    public static class ExactAspect {
        @Before(
            "execution(* demo..*.process(..)) " +
            "&& bean(primaryJobService)"
        )
        public void trace(JoinPoint jp) {
            System.out.println("ADVICE exact " + jp.getSignature().getName());
        }
    }

    @Aspect
    public static class WildcardAspect {
        @Before(
            "execution(* demo..*.process(..)) " +
            "&& bean(*JobService)"
        )
        public void trace(JoinPoint jp) {
            System.out.println("ADVICE wildcard " + jp.getSignature().getName());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SharedBeans {
        @Bean("primaryJobService")
        public JobService primaryJobService() {
            return new JobServiceImpl("PRIMARY");
        }

        @Bean("backupJobService")
        public JobService backupJobService() {
            return new JobServiceImpl("BACKUP");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    @Import(SharedBeans.class)
    public static class ExactConfig {
        @Bean
        public ExactAspect exactAspect() {
            return new ExactAspect();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    @Import(SharedBeans.class)
    public static class WildcardConfig {
        @Bean
        public WildcardAspect wildcardAspect() {
            return new WildcardAspect();
        }
    }

    static void run(String title, Class<?> config) {
        try (var ctx = new AnnotationConfigApplicationContext(config)) {
            JobService primary =
                    ctx.getBean("primaryJobService", JobService.class);
            JobService backup =
                    ctx.getBean("backupJobService", JobService.class);

            System.out.println("=== " + title + " ===");
            System.out.println("PRIMARY_PROXY=" + AopUtils.isAopProxy(primary));
            System.out.println("BACKUP_PROXY=" + AopUtils.isAopProxy(backup));

            System.out.println("RESULT " + primary.process("A"));
            System.out.println("RESULT " + backup.process("B"));
        }
    }

    public static void main(String[] args) {
        run("EXACT", ExactConfig.class);
        run("WILDCARD", WildcardConfig.class);
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

**Các dòng do chương trình in, theo thứ tự kỳ vọng** (bỏ qua log bổ sung từ Maven/Spring nếu có):

```text
=== EXACT ===
PRIMARY_PROXY=true
BACKUP_PROXY=false
ADVICE exact process
TARGET PRIMARY A
RESULT PRIMARY:A
TARGET BACKUP B
RESULT BACKUP:B
=== WILDCARD ===
PRIMARY_PROXY=true
BACKUP_PROXY=true
ADVICE wildcard process
TARGET PRIMARY A
RESULT PRIMARY:A
ADVICE wildcard process
TARGET BACKUP B
RESULT BACKUP:B
```

Vì sao kết quả khác nhau?

- Hai bean trong mỗi context **đều dùng `JobServiceImpl`**, đều expose `JobService.process(String)`, và đều do Spring quản lý.
- Trong `ExactConfig`, Spring chỉ tạo AOP proxy cho `primaryJobService` vì chỉ bean name đó match pointcut. `backupJobService` không nhận proxy Spring AOP từ advice này.
- Trong `WildcardConfig`, cả hai bean name kết thúc bằng `JobService`, nên advisor áp cho cả hai target và chúng đều có Spring AOP proxy.
- Advice `@Before` chạy trước target method nếu lời gọi qua proxy và pointcut match.
- Hai context độc lập giúp tránh tình trạng nhiều advice chạy trên cùng join point với thứ tự tương đối không được khai báo.

**Ranh giới quan trọng:** output mô tả demo với chỉ một advisor liên quan trong mỗi context. Nếu ứng dụng có transaction/caching hoặc aspect khác, một bean không match `bean(...)` vẫn có thể nhận proxy bởi **advisor khác**. Do đó `AopUtils.isAopProxy(backup)==false` ở nhánh EXACT chỉ đúng trong setup được nêu, không phải quy luật tổng quát.

## 6. Cách giới hạn nhiều bean theo pattern và điều kiện phủ định

Sau khi nắm demo, có thể viết các pointcut phức hợp rõ chủ đích.

### 6.1. Chọn một nhóm bean đặt tên theo convention

```java
@Pointcut("bean(*Service)")
public void namedServices() {
}

@Pointcut("execution(public * demo..*.process(..))")
public void publicProcessingMethods() {
}

@Before("namedServices() && publicProcessingMethods()")
public void auditServices() {
    System.out.println("AUDIT");
}
```

Đây là các method mẫu **nằm trong cùng một Spring `@Aspect` bean**; chưa phải chương trình độc lập. Biểu thức có thể tái sử dụng tên pointcut thay vì lặp pattern dài.

### 6.2. Loại trừ một bean cụ thể

```java
@Before(
    "bean(*JobService) && !bean(backupJobService) " +
    "&& execution(* demo..*.process(..))"
)
public void auditNonBackup() {
    System.out.println("AUDIT-NON-BACKUP");
}
```

Trên hai bean của demo, chỉ `primaryJobService` còn match. Điều kiện `!bean(backupJobService)` là **phủ định match theo tên**, không phải phủ định class hay việc bean có được Spring quản lý hay không.

### 6.3. Chọn một tập tên rõ ràng

```java
@Before(
    "(bean(primaryJobService) || bean(backupJobService)) " +
    "&& execution(* demo..*.process(..))"
)
public void auditSelected() {
    System.out.println("AUDIT-SELECTED");
}
```

Biểu thức `(...)` nhóm điều kiện trước khi kết hợp với `execution`; mục đích là chỉ chọn method `process(..)` của hai bean được đặt tên cụ thể.

### 6.4. Phạm vi tên không phải phạm vi class/package

```text
bean(*Service)                 -> kiểm tra tên Spring bean
execution(* demo.service..*.*(..))
                               -> kiểm tra method execution theo package/type
within(demo.service..*)        -> kiểm tra phạm vi kiểu khai báo method
target(demo.service.JobService)-> kiểm tra target object type
```

Các dòng trên là **minh họa ý nghĩa biểu thức**. Một `@Bean("primaryJobService")` có thể trả instance của class nằm ngoài package `demo.service`, và `bean(primaryJobService)` vẫn có thể match theo tên. Ngược lại, class trong package `demo.service` không được chọn bởi `bean(*Service)` nếu tên Spring bean của nó không khớp pattern.

## 7. `bean(...)` không đồng nghĩa với `@Qualifier` hoặc tên biến

`@Qualifier` chủ yếu hỗ trợ Spring dependency injection: nó thu hẹp **ứng viên dependency theo type**. Còn `bean(...)` trong Spring AOP quyết định **advisor áp dụng cho bean mang tên nào**.

Ví dụ:

```java
public JobRunner(
        @Qualifier("primaryJobService") JobService jobService) {
    this.jobService = jobService;
}
```

Đây là **constructor mẫu** cần field, class và import. `@Qualifier("primaryJobService")` có thể giúp chọn bean phù hợp khi inject, nhưng không phải nó “tạo một tên bean mới” hoặc làm `bean(primaryJobService)` bỗng khớp. Tên bean đã tồn tại trong registry.

Nếu có một custom qualifier `@Qualifier("critical")` gắn cho bean tên `mainProcessor`, biểu thức `bean(critical)` **không tự match** tên custom qualifier đó. Muốn chọn theo annotation/type, cần dùng cơ chế pointcut tương ứng hoặc đặt tên Spring bean theo convention phù hợp.

Tương tự, tên field Java `private JobService jobService;` hoặc tên local variable không quyết định bean name. Khi cần kiểm tra thực tế, có thể gọi `context.containsBean("primaryJobService")` hoặc lấy bean bằng tên từ `ApplicationContext`.

## 8. Spring Boot và các quy tắc tạo proxy liên quan

Trong Spring Framework thuần, `@EnableAspectJAutoProxy` kích hoạt auto-proxy cho `@AspectJ` style khi có các dependency phù hợp. Trong Spring Boot với `spring-boot-starter-aop` và điều kiện classpath, AOP thường được tự cấu hình; không nhất thiết phải thêm annotation đó thủ công.

Một khác biệt cấu hình thường gặp:

- Spring Framework thuần: target có interface thường được JDK dynamic proxy khi `proxyTargetClass=false`.
- Spring Boot auto-configuration AOP mặc định thường ưu tiên **class-based proxy**; có thể dùng `spring.aop.proxy-target-class=false` để cho phép JDK proxy khi có interface.

**Dù chọn JDK hay CGLIB, `bean(...)` vẫn xét tên Spring bean**, nhưng còn cần method có thể được proxy intercept. Nếu chuyển sang JDK proxy, method chỉ có trên implementation và không expose qua interface sẽ không tự trở thành callable qua JDK proxy. Nếu CGLIB, `final/private` method không được override để advice.

Không mặc định rằng thiết lập `spring.aop.auto=false` tắt mọi nguồn tạo proxy của ứng dụng; các hạ tầng transaction, custom advisors hoặc cấu hình khác vẫn có thể tạo proxy. Khi debug `bean(...)`, phải tách rõ **bean name matching** và **có proxy/advisor thực sự áp dụng hay không**.

## 9. Giới hạn quan trọng của Spring AOP `bean(...)`

### 9.1. Chỉ dành cho Spring AOP proxy-based pointcuts

`bean(...)` là phần mở rộng gắn với Spring BeanFactory, không phải PCD chuẩn dùng chung cho native AspectJ weaving. Nếu code chuyển từ Spring AOP sang compile-time/load-time AspectJ weaving, cần thiết kế lại pointcut theo các type/annotation/logic khả dụng ở môi trường weaving.

### 9.2. Lời gọi phải đi qua Spring proxy

Nếu một service gọi `this.process()` bên trong chính target của nó, lời gọi đó **không quay lại proxy**. Dù `bean(primaryJobService)` khớp tên bean, advice không được thực thi thêm lần nữa ở lời gọi nội bộ này. Tương tự, object tạo bằng `new JobServiceImpl(...)` ngoài Spring không được advisor lựa chọn chỉ vì có class tương ứng.

### 9.3. Không phải phân vùng dữ liệu bảo mật

`bean(...)` giúp chọn advisor theo bean name, nhưng **không phải một cơ chế phân quyền hoặc sandbox**. Một tên bị đổi, bean được alias, hoặc logic bị gọi theo đường không qua proxy có thể làm kỳ vọng advice thay đổi. Với nhu cầu bảo mật, cần kiểm tra authorization tại ranh giới thích hợp và có kiểm thử; không chỉ trông chờ tên bean hay việc log/audit advice đã chạy.

### 9.4. Kết quả có thể khác khi bean được tạo bởi factory/proxy khác

Các đối tượng như `FactoryBean`, scoped proxy, proxy lồng nhau, target source động và bean definitions đặc biệt làm việc tra tên hoặc đối tượng runtime phức tạp hơn. Trong những tình huống đó, nên đo tên bean thực tế, loại proxy và các advisors đang gắn vào bean. Không tự khẳng định `bean(pattern)` luôn phản ánh alias hay factory product theo đúng một cách cho mọi dạng factory/proxy.

### 9.5. Tên bean không nhất thiết ổn định khi refactor

Chuyển từ `@Bean("primaryJobService")` sang `@Component` sinh tên tự động, đổi tên `@Bean` method hoặc dùng custom naming strategy có thể làm pointcut không còn khớp. Vì vậy, khi `bean(...)` mang ý nghĩa nghiệp vụ cần lâu dài, ưu tiên tên tường minh và thêm integration test kiểm tra advice.

## 10. Quy trình chẩn đoán pointcut `bean(...)` không chạy

1. **Tên thực tế:** xác minh trong context đang chạy có `primaryJobService` không; không đoán từ tên class, field hoặc `@Qualifier`.
2. **Có nhiều instance cùng class:** kiểm tra bean được gọi từ client là **bean nào**, không chỉ kiểm `getClass()`.
3. **Đã bật @AspectJ auto-proxy:** aspect class có `@Aspect` và được đăng ký thành Spring bean chưa?
4. **Pointcut có đúng chữ hoa/thường và wildcard:** kiểm tra `bean(*Service)` có khớp hậu tố tên thực tế không; phân biệt `*` với regex.
5. **Điều kiện kết hợp:** `execution(...)` có match method đang gọi? Nếu `bean(...)` đúng nhưng `execution(...)` sai, tổng `&&` vẫn không match.
6. **Bean có Spring AOP proxy không:** dùng `AopUtils.isAopProxy(bean)`. Không có proxy thường là dấu hiệu không có advisor nào áp vào bean trong context đó.
7. **Các advisor khác:** có thể bean nhận proxy vì transaction/cache/advice khác dù `bean(...)` bạn viết không khớp. Vì vậy proxy tồn tại không đủ chứng minh chính advice của bạn đã chạy.
8. **Phương thức được gọi qua proxy:** tránh `new` object hoặc self-invocation `this.method()` trên target.
9. **Khả năng chặn method:** JDK proxy chỉ expose interface methods; CGLIB bị giới hạn bởi `final/private` và khả năng kế thừa.
10. **Nhiều context/proxy layer:** bảo đảm đang nhìn đúng Spring `ApplicationContext` và đúng bean reference; context test và context production có thể đăng ký tên khác nhau.

Có thể in các bean names theo type trong **ứng dụng của bạn** (đây là đoạn code bổ sung, không phải chương trình standalone):

```java
String[] names = context.getBeanNamesForType(JobService.class);
for (String name : names) {
    Object bean = context.getBean(name);
    System.out.println(name + " -> aop=" + AopUtils.isAopProxy(bean));
}
```

Nếu cùng type có nhiều bean, đoạn trên hữu ích để kiểm tra tên thực tế, nhưng một advisor chỉ áp trên một bean không làm các bean khác cùng class tự được advice.

## 11. Những nhận định sai thường gặp

| Nhận định | Sự thật |
| --- | --- |
| “`bean(JobServiceImpl)` là match mọi bean thuộc class `JobServiceImpl`.” | `bean(...)` match theo **tên Spring bean**, không phải tên class. |
| “Hai bean cùng class luôn nhận cùng advice.” | `bean(name)` có thể chỉ chọn một instance bean theo tên. |
| “`bean(*Service)` là regex.” | Đây là wildcard đơn giản `*` trong pattern tên bean. |
| “Dùng `@Qualifier("critical")` thì `bean(critical)` sẽ match.” | Qualifier metadata không tự trở thành tên bean. |
| “Chỉ cần `@Aspect` class có pointcut `bean(...)` là hoạt động.” | Aspect còn phải được đăng ký thành Spring bean; AOP support cần được bật phù hợp. |
| “`bean(...)` advice mọi method trên bean kể cả private/constructor.” | Spring AOP chỉ intercept method execution qua proxy, còn chịu giới hạn proxy strategy. |
| “`bean(...)` dùng được như nhau trong AspectJ weaving native.” | Đây là Spring-specific pointcut designator cho Spring AOP. |
| “Một bean không match `bean(...)` chắc chắn không có proxy.” | Advisor khác có thể tạo AOP proxy cho bean đó. |
| “Đổi bean name không tác động pointcut.” | Refactor tên có thể làm biểu thức ngừng khớp. |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Hai Spring bean `primaryJobService` và `backupJobService` có cùng class `JobServiceImpl`. `bean(primaryJobService)` chọn mấy bean?  
**Đáp án:** Chọn bean có đúng tên `primaryJobService` (một trong hai, giả định không có alias/đăng ký đặc biệt và có method match).

**Câu 2.** `bean(*JobService)` chọn bean nào nếu cả hai tên đều kết thúc bằng `JobService`?  
**Đáp án:** Cả hai bean, trong phạm vi những method execution được proxy và điều kiện pointcut còn lại.

**Câu 3.** `bean(JobServiceImpl)` có tự hiểu đó là tên Java class không?  
**Đáp án:** Không. Spring xét bean name `JobServiceImpl` theo pattern.

**Câu 4.** Một method nằm ngoài package được `execution(...)` chọn, nhưng bean name phù hợp `bean(primaryJobService)`. Biểu thức ghép `execution(...) && bean(...)` có match không?  
**Đáp án:** Không, vì toán tử AND đòi hỏi cả hai điều kiện.

**Câu 5.** Dùng custom `@Qualifier("fast")` cho bean `primaryJobService`. `bean(fast)` chắc chắn match không?  
**Đáp án:** Không. Custom qualifier không tự tạo bean name `fast`.

**Câu 6.** Nếu Spring AOP proxy `primaryJobService` có advice cho `process()`, target gọi nội bộ `this.process()` sẽ chạy lại advice không?  
**Đáp án:** Không có lời gọi vào proxy mới; self-invocation bỏ qua Spring AOP interception.

**Câu 7.** Nếu bean `backupJobService` không match exact pointcut nhưng có `@Transactional`, nó có thể vẫn là proxy không?  
**Đáp án:** Có, vì cơ chế/advisor khác có thể tạo proxy.

**Câu 8.** Có thể chuyển nguyên biểu thức `bean(*Service)` sang native AspectJ weaving không?  
**Đáp án:** Không. `bean` là extension dành riêng cho Spring AOP tích hợp BeanFactory.

## 13. Tài liệu Spring Framework chính thức

- [Spring Framework 6.2 — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): `bean(name)`, wildcard `*`, toán tử `&&`/`||`/`!`, Spring-specific instance-level matching.
- [Spring Framework — Bean Overview](https://docs.spring.io/spring-framework/reference/6.2/core/beans/definition.html): bean name, id, alias và naming conventions.
- [Spring Framework — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): đặt tên bean qua `@Bean`.
- [Spring Framework — Spring AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): hạn chế proxy, method execution và self-invocation.
- [Spring Framework — Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html): phân biệt semantic qualifier và bean name.

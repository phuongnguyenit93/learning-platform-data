# Kiểm tra cấu hình Java và XML không gây thiết lập chồng chéo trong Spring AOP

## 1. Vì sao phải kiểm tra khi ứng dụng Spring dùng cả Java config và XML?

Một ứng dụng Spring lâu năm có thể đồng thời chứa:

- Cấu hình Java bằng `@Configuration`, `@EnableAspectJAutoProxy`, `@Bean` hoặc `@ComponentScan`.
- Cấu hình XML với `<aop:aspectj-autoproxy/>`, `<aop:config>`, `<aop:advisor>`, `<bean>` và `<context:component-scan/>`.
- Cấu hình tự động của Spring Boot hoặc những tính năng Spring khác cũng sử dụng proxy, chẳng hạn transaction interception.

Việc tồn tại song song **không mặc nhiên sai**: Spring cho phép kết hợp nhiều cách định nghĩa bean, aspect và advisor. Tuy nhiên, khi chuyển dần từ XML sang Java config, rất dễ giữ lại khai báo cũ khiến khó xác định ai chịu trách nhiệm bật proxy, một aspect được đăng ký mấy lần, hoặc một phương thức có hai advice thực hiện cùng chức năng.

Mục tiêu của bước kiểm tra là trả lời **ba câu hỏi riêng biệt**:

1. **Auto-proxy:** cùng một Spring `ApplicationContext` có bao nhiêu cơ chế tạo proxy đang tham gia, và cấu hình proxy thực tế là gì?
2. **Aspect bean:** mỗi aspect dự định sử dụng có được đăng ký đúng một lần theo tên/loại bean hay không?
3. **Advice/advisor:** với một method nghiệp vụ, có bao nhiêu advice thực sự khớp, theo thứ tự nào, và hành vi có bị lặp không?

**Không được suy ra “advice chạy hai lần” chỉ từ việc thấy cả `@EnableAspectJAutoProxy` và `<aop:aspectj-autoproxy/>`.** Spring hợp nhất các khai báo auto-proxy chuẩn vào một hạ tầng thống nhất trong cùng context; sự lặp cần được chứng minh ở mức aspect/advisor và kết quả chạy.

Bài này tập trung vào **cấu hình Spring AOP trên Spring-managed beans**. Các cơ chế AspectJ weaving thuần túy và lý thuyết AOP tổng quát nằm ngoài phạm vi.

## 2. Các khai báo Java/XML có thể gặp và ý nghĩa của chúng

| Khai báo | Nơi xuất hiện | Chức năng trong Spring AOP |
| --- | --- | --- |
| `@EnableAspectJAutoProxy` | Class `@Configuration` | Bật nhận diện các aspect bean kiểu `@Aspect` và tự tạo proxy cho bean phù hợp trong application context liên quan. |
| `<aop:aspectj-autoproxy/>` | XML namespace `aop` | Bật cùng kiểu hỗ trợ `@AspectJ` bằng XML. |
| `<aop:config>` | XML namespace `aop` | Khai báo pointcut, aspect và advisor trực tiếp trong XML; cũng tham gia hệ thống auto-proxy. |
| `@Bean` trả về class `@Aspect` | Java config | Đăng ký **một bean aspect** cho Spring phát hiện. |
| `@Aspect` + `@Component` | Class aspect được component scan | Một cách khác đăng ký bean aspect; `@Aspect` đơn lẻ không phải annotation phát hiện component. |
| `<bean class="...MyAspect"/>` | XML | Đăng ký một instance aspect dưới một bean id, nếu class mang `@Aspect`. |
| `<aop:aspect ref="...">` | XML | Dùng một bean hiện có làm nơi chứa các phương thức advice được khai báo qua schema XML. |
| `@ImportResource("classpath:...xml")` | Java config | Đưa bean definitions từ XML vào context Java; đây là **đường nạp** XML, không tự bật Spring AOP. |
| `<context:component-scan ... />` | XML | Quét component bean; có thể trùng phạm vi với `@ComponentScan` bên Java. |

Phân biệt rõ: **khai báo bật AOP**, **khai báo bean aspect**, và **định nghĩa advice** là ba việc khác nhau. Một cách bật AOP có thể dùng chung cho nhiều aspect; một aspect bean khác tên nhưng cùng class có thể tạo ra thêm một tập advice; hai định nghĩa advice khác nhau có thể cùng khớp một phương thức.

## 3. Spring hợp nhất auto-proxy creator: hiểu đúng trước khi dọn cấu hình

Spring Framework ghi rõ các `<aop:config/>`, `<aop:aspectj-autoproxy/>` và `<tx:annotation-driven/>` trong cùng context được điều phối qua **một auto-proxy creator hợp nhất**, với mức thiết lập proxy mạnh nhất trong những yêu cầu cùng tham gia. Các annotation cấu hình tương ứng như `@EnableAspectJAutoProxy` và `@EnableTransactionManagement` cũng tham gia cơ chế hợp nhất này.

Ví dụ tại **cùng một context**:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AopJavaConfig {
}
```

```xml
<aop:aspectj-autoproxy proxy-target-class="true"/>
```

Với cách kết hợp trên, yêu cầu XML dùng class-based proxy (`true`) có thể **nâng mức lựa chọn chung lên class-based proxy**. Vì vậy chỉ nhìn annotation Java và thấy `false` không đủ kết luận rằng Spring sẽ dùng JDK dynamic proxy. Ngược lại, không nên đếm số dòng bật AOP rồi kết luận từng dòng tạo thêm một lớp proxy độc lập.

Một số lưu ý khi đọc kết quả:

- **“Hợp nhất auto-proxy creator” không có nghĩa mọi aspect hoặc advisor đều bị loại trùng.** Hai aspect bean hoặc hai advice hợp lệ cùng khớp có thể khiến hành vi được thực hiện nhiều lần.
- **`proxyTargetClass = true` không làm Spring chặn được mọi phương thức.** Class/method `final`, phương thức `private`, và self-invocation vẫn có giới hạn của proxy AOP.
- **Phạm vi context quan trọng.** Một parent context và một child context là hai miền bean/proxy khác nhau; cấu hình ở parent không đương nhiên áp dụng như nhau với bean chỉ thuộc child context.
- **Spring Boot có thể bật Spring AOP qua auto-configuration** khi các dependency và điều kiện phù hợp. Khai báo `@EnableAspectJAutoProxy` thêm vào một ứng dụng Boot đang tự cấu hình AOP có thể dư thừa và còn thay đổi thuộc tính proxy dự kiến.

**Mục tiêu bảo trì** là xác định được một nơi sở hữu cấu hình proxy cho mỗi context, dù Spring có cơ chế tự hợp nhất để bảo vệ các khai báo trùng.

## 4. Ví dụ Spring Framework 6: trộn Java và XML đúng cách

Ví dụ dưới đây dùng **Java 17+**, Spring Framework **6.1.14**, AspectJ `aspectjweaver` **1.9.22.1** và Maven. Đây là phiên bản mẫu cố định để minh họa, không phải phát biểu về bản Spring mới nhất.

Ta chọn một quy ước rõ ràng:

- **Java config bật `@EnableAspectJAutoProxy` và đăng ký aspect**.
- **XML chỉ định nghĩa service bean** kế thừa từ hệ thống cũ.
- Chỉ có **một** `TraceAspect` bean; lời gọi đến `OrderService` đi qua Spring proxy.

Cấu trúc thư mục:

```text
spring-aop-java-xml-check/
├── pom.xml
└── src/main/
    ├── java/com/example/demo/
    │   ├── DemoApp.java
    │   ├── AppConfig.java
    │   ├── OrderService.java
    │   └── TraceAspect.java
    └── resources/legacy-beans.xml
```

### 4.1. Khai báo Maven

**`pom.xml`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-java-xml-check</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.1.14</version>
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

`spring-context` quản lý bean và cấu hình; `spring-aop` triển khai cơ chế proxy; `aspectjweaver` cung cấp hỗ trợ cho biểu thức pointcut `@AspectJ`. Trong ứng dụng đã có Spring Boot starter AOP tương ứng, thông thường không cần liệt kê thủ công cả ba artifact.

### 4.2. XML giữ lại bean nghiệp vụ

**`src/main/resources/legacy-beans.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="orderService" class="com.example.demo.OrderService"/>
</beans>
```

XML trên không khai báo `<aop:aspectj-autoproxy/>`, `<aop:config>` hoặc aspect bean. Mục đích của nó chỉ là đăng ký bean cũ có tên `orderService`.

### 4.3. Java config chịu trách nhiệm bật AOP

**`src/main/java/com/example/demo/AppConfig.java`**:

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.ImportResource;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
@ImportResource("classpath:legacy-beans.xml")
public class AppConfig {
    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

`@ImportResource` chỉ yêu cầu Spring nạp file XML để có `orderService`. Bean `traceAspect` được khai báo **đúng một lần bằng Java**. Annotation `@EnableAspectJAutoProxy(proxyTargetClass = true)` kích hoạt proxy theo class nên ví dụ lấy được bean dưới kiểu `OrderService` dù class không triển khai interface.

### 4.4. Service và aspect

**`src/main/java/com/example/demo/OrderService.java`**:

```java
package com.example.demo;

public class OrderService {
    public void place(String id) {
        System.out.println("[SERVICE] order " + id);
    }
}
```

**`src/main/java/com/example/demo/TraceAspect.java`**:

```java
package com.example.demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Before("execution(public * com.example.demo.OrderService.place(..))")
    public void beforePlace() {
        calls.incrementAndGet();
        System.out.println("[ASPECT] before place");
    }

    public int count() {
        return calls.get();
    }
}
```

`@Aspect` đánh dấu class là aspect, còn `@Bean` ở `AppConfig` đưa đối tượng vào Spring container. Không cần gắn thêm `@Component` cho `TraceAspect` trong ví dụ này.

### 4.5. Kiểm tra proxy, số aspect bean và số lần advice

**`src/main/java/com/example/demo/DemoApp.java`**:

```java
package com.example.demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderService service = context.getBean(OrderService.class);
            TraceAspect aspect = context.getBean(TraceAspect.class);

            System.out.println("[CHECK] isProxy=" + AopUtils.isAopProxy(service));
            System.out.println("[CHECK] aspectBeans="
                    + context.getBeansOfType(TraceAspect.class).size());

            service.place("ORD-1");

            System.out.println("[CHECK] adviceCalls=" + aspect.count());
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.demo.DemoApp
```

Các dòng chương trình tự in ra theo đúng thứ tự:

```text
[CHECK] isProxy=true
[CHECK] aspectBeans=1
[ASPECT] before place
[SERVICE] order ORD-1
[CHECK] adviceCalls=1
```

**Diễn giải từng phép kiểm tra:**

- `isProxy=true`: `OrderService` mà caller lấy ra thực sự là Spring AOP proxy, không phải object tự `new`.
- `aspectBeans=1`: có đúng một bean kiểu `TraceAspect` trong context; đếm bean quan trọng hơn đếm số file cấu hình.
- `adviceCalls=1`: đúng một lần gọi advice sau một lần gọi phương thức qua proxy. Đây là kiểm tra **quan sát được** giúp phát hiện điều kiện chồng chéo.
- Dòng nghiệp vụ vẫn chạy sau advice: Spring AOP đã áp dụng hành vi chung mà không cần sửa `OrderService`.

`AopUtils.isAopProxy` là công cụ quan sát proxy; trong hệ thống thực tế cần bổ sung kiểm thử số lần advice và kết quả nghiệp vụ, vì chỉ có proxy chưa chứng minh cấu hình không trùng logic.

## 5. Hai tình huống chồng chéo: một trường hợp thừa, một trường hợp thực sự lặp hành vi

### 5.1. Bật auto-proxy lần nữa trong XML: dư thừa, chưa chứng minh advice lặp

Giả sử `AppConfig` ở trên đã chứa `@EnableAspectJAutoProxy(proxyTargetClass = true)`, nhưng file XML cũ còn có:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd
         http://www.springframework.org/schema/aop
         https://www.springframework.org/schema/aop/spring-aop.xsd">

    <aop:aspectj-autoproxy proxy-target-class="true"/>

    <bean id="orderService" class="com.example.demo.OrderService"/>
</beans>
```

Việc thêm `<aop:aspectj-autoproxy/>` như trên là **khai báo bật AOP thứ hai**. Trong cùng context, Spring hợp nhất hỗ trợ auto-proxy thông thường; riêng tình huống này **không tự tạo ra hai aspect bean** và không phải căn cứ đủ để nói lời gọi sẽ chạy `beforePlace()` hai lần.

Tuy nhiên, cách cấu hình này gây khó bảo trì và có thể che khuất việc chọn `proxy-target-class`. Khi Java config đã là nơi bật AOP chính thức, **xóa dòng XML dư thừa** sau khi kiểm tra mọi context phụ thuộc, giữ XML chỉ cho bean definitions. Nếu thực tế XML mới là nơi được chọn để sở hữu AOP, làm ngược lại: chỉ giữ XML activation và loại annotation Java dư thừa trong context đó.

Không chỉnh đồng thời hai nơi theo một quy tắc “mỗi nơi một chút” vì người đọc rất khó xác định chính sách proxy cuối cùng.

### 5.2. Đăng ký cùng class aspect thành hai bean: advice có thể chạy hai lần

Giữ nguyên `@Bean traceAspect()` bên Java, rồi **thêm** vào `legacy-beans.xml`:

```xml
<bean id="traceAspectXml" class="com.example.demo.TraceAspect"/>
```

Khi đó tồn tại hai bean riêng biệt:

```text
Java:  @Bean traceAspect()               --> traceAspect
XML:   <bean id="traceAspectXml" .../>    --> traceAspectXml
```

Cả hai đều là bean thuộc class có `@Aspect` và cùng chứa `@Before` khớp `OrderService.place()`. Dù Spring chỉ dùng một cơ chế auto-proxy thống nhất, nó có thể tạo **hai advisor tương ứng với hai aspect instances**. Mỗi lần gọi `place()` qua proxy sẽ có hai dòng `[ASPECT] before place`; vì là hai instance độc lập, `aspect.count()` của một instance riêng lẻ **không phải tổng số lần advice trên cả hai instance**.

Thay phép kiểm `aspect.count()` bằng một bộ đếm được chia sẻ hoặc thu thập event để chứng minh số lần thực thi khi đánh giá nhiều instances. Nếu chạy nguyên `DemoApp` mà không đổi, phần `context.getBean(TraceAspect.class)` còn có thể ném `NoUniqueBeanDefinitionException`, do có hai bean cùng kiểu; đây là một dấu hiệu khác cho thấy cấu hình đã lặp đăng ký.

**Cách sửa:** xác định nơi sở hữu bean aspect, xóa đăng ký còn lại. Nếu class đã có `@Component` và được cả Java `@ComponentScan` lẫn XML `<context:component-scan/>` quét, hãy kiểm tra bean name thực tế. Cùng một bean name có thể bị xử lý như một định nghĩa trùng hoặc gây lỗi override; **khác bean name** có thể tạo hai instances. Không nên khẳng định mọi lần quét lặp tự sinh ra hai bean: kết quả phụ thuộc naming, metadata và chính sách ghi đè bean definitions.

### 5.3. Hai định nghĩa advice cùng mục đích

Một biến thể khác là:

- Java aspect có `@Before` ghi một audit event;
- XML `<aop:config>` lại có `<aop:advisor>` hoặc `<aop:aspect>` chọn đúng method và ghi cùng audit event.

Dù chỉ có một bean aspect Java, hệ thống vẫn có **hai advice chức năng tương tự**. Spring hỗ trợ phối hợp cả annotation-based aspect lẫn schema-defined advisor; việc chúng cùng tồn tại hợp lệ về mặt Spring, nhưng phải kiểm tra xem đó là hai chính sách khác nhau được chủ đích hay là mã chuyển đổi chưa dọn xong.

**Không sửa bằng cách tắt toàn bộ AOP.** Hãy tìm đúng khai báo advice bị trùng chức năng và thống nhất một nguồn sở hữu cho chính sách đó.

## 6. Danh sách điểm cần tìm khi kiểm kê Spring AOP configuration

Khi codebase dùng cả Java và XML, lần lượt tìm các nhóm ký hiệu sau trong **các file cấu hình thực sự được nạp bởi application context**.

| Nhóm | Trong Java | Trong XML | Điều cần xác nhận |
| --- | --- | --- | --- |
| Bật proxy | `@EnableAspectJAutoProxy` | `<aop:aspectj-autoproxy>`, `<aop:config>` | Ai sở hữu chính sách proxy trong context? Có thiết lập `proxyTargetClass` xung đột? |
| Nạp cấu hình | `@Import`, `@ImportResource`, `@ComponentScan` | `<import>`, `<context:component-scan>` | Một file hoặc bean có bị nạp/đăng ký theo nhiều con đường? |
| Đăng ký aspect | `@Bean`, `@Component` + `@Aspect` | `<bean class="...">` | Có bao nhiêu bean name/instance cho mỗi aspect? |
| Gắn advice | `@Before`, `@After`, `@Around`... | `<aop:aspect>`, `<aop:advisor>` | Có nhiều advice khớp cùng method và cùng chức năng? |
| Tính năng dùng chung proxy | `@EnableTransactionManagement` | `<tx:annotation-driven>` | Thiết lập class-based proxy có ảnh hưởng đến các interceptor khác? |
| Auto-configuration | Spring Boot starter, properties và cấu hình Java | XML legacy được import | Boot đã tự kích hoạt AOP trước khi thêm annotation/XML thủ công chưa? |

**Cách tìm trong repository** (ví dụ khi có `rg`):

```bash
rg -n 'EnableAspectJAutoProxy|ImportResource|ComponentScan|@Aspect|@Bean' src/main/java
rg -n 'aspectj-autoproxy|aop:config|aop:advisor|aop:aspect|context:component-scan|<import' src/main/resources
```

Tìm được một đoạn text chưa đủ kết luận nó có hiệu lực: profile có thể chưa bật, file XML có thể không được import, package có thể nằm ngoài component scan, hoặc cấu hình thuộc một context khác. Bước kiểm kê phải truy ngược **điểm khởi tạo context**, danh sách config được nạp, profile và điều kiện kích hoạt.

Với Spring Boot, đối chiếu `spring.aop.auto`, `spring.aop.proxy-target-class` và auto-configuration phù hợp với phiên bản Boot đang chạy. Khi muốn ngừng AOP, không nên chỉ đặt một property rồi bỏ qua các cấu hình `@EnableAspectJAutoProxy` do code tự bật.

## 7. Kiểm tra trực tiếp Spring container khi nghi có trùng

### 7.1. Đếm bean aspect theo type và name

Trong môi trường kiểm thử, ví dụ:

```java
String[] names = context.getBeanNamesForType(TraceAspect.class);
System.out.println(java.util.Arrays.toString(names));
```

Kết quả dự kiến với bài mẫu:

```text
[traceAspect]
```

Nếu có `traceAspectXml` cùng tồn tại, có thể thấy hai tên. **Không dựa vào thứ tự in tên khi kiểm thử nhiều bean**; hãy so theo tập tên hoặc số lượng.

Lưu ý: `getBeansOfType` có thể khởi tạo các singleton tương ứng, còn việc lấy định nghĩa bean name chỉ phản ánh context được hỏi. Khi hệ thống có context cha/con, phải kiểm kê đúng cả hai.

### 7.2. Quan sát proxy và các advisor đang áp dụng

Nếu bean là Spring AOP proxy hỗ trợ giao diện `Advised`, có thể liệt kê các advisor:

```java
Object bean = context.getBean("orderService");
System.out.println(org.springframework.aop.support.AopUtils.isAopProxy(bean));

if (bean instanceof org.springframework.aop.framework.Advised advised) {
    for (org.springframework.aop.Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName()
                + " -> " + advisor.getAdvice().getClass().getName());
    }
}
```

Đây là **đoạn mã chẩn đoán** dùng trong test hoặc môi trường kiểm tra, không phải bản mở rộng của `DemoApp` cần stdout chính xác. Advisor nội bộ có thể bao gồm nhiều loại hỗ trợ, và thứ tự/class tên phụ thuộc version. Đếm số advisor **không tương đương** với đếm số advice chạy trên một method: phải xét pointcut và lần gọi cụ thể.

### 7.3. Kiểm thử một lần gọi với số lần advice kỳ vọng

Một kiểm thử hữu ích nên có:

1. Một bean đích chắc chắn khớp pointcut.
2. Một bean/phương thức không khớp để kiểm tra advice không chạy ngoài phạm vi.
3. Bộ đếm hoặc event collector cho **tổng** lần chạy của chính sách audit/tracing.
4. Kiểm tra giá trị trả về/ngoại lệ của nghiệp vụ và thứ tự khi có nhiều advice khác loại.
5. Lặp lại với các Spring profiles/configuration combinations được triển khai thực tế.

Kỳ vọng ví dụ đơn giản: **một lần `service.place("ORD-1")` → một audit event → một lần chạy nghiệp vụ**. Trường hợp khác như hai chính sách khác nhau cùng advice một method có thể hợp lệ; kiểm thử phải nêu rõ số lần dự kiến cho **từng trách nhiệm**, thay vì mặc định mọi method chỉ được một advice.

## 8. Phân biệt các triệu chứng dễ nhầm

| Triệu chứng | Giải thích có thể xảy ra | Cách xác minh |
| --- | --- | --- |
| Có `@EnableAspectJAutoProxy` và `<aop:aspectj-autoproxy/>` | Khai báo bật proxy dư; Spring thường hợp nhất thành một creator | Kiểm tra context và config thực tế; đừng kết luận log lặp nếu chưa đo. |
| Advice chạy hai lần | Hai aspect beans, hai advisors, hoặc hai interception layers thực sự | Đếm bean, liệt kê advisor, ghi số lần advice bằng counter chung. |
| Inject aspect bằng type báo không duy nhất | Cùng class aspect được đăng ký dưới nhiều bean names | `getBeanNamesForType(MyAspect.class)`, kiểm tra `@Bean`, `@Component` và XML `<bean>`. |
| Không có advice dù có XML | XML chưa được import, aspect không là bean, pointcut không khớp, hoặc caller đi vòng qua proxy | Kiểm tra đường nạp XML, bean registry, `AopUtils.isAopProxy` và đường gọi. |
| Proxy là CGLIB dù annotation Java đặt `proxyTargetClass=false` | XML hoặc cấu hình khác có thể yêu cầu `proxy-target-class=true` | Kiểm kê mọi proxy setting trong cùng context, kể cả transaction AOP. |
| Tưởng AOP chạy hai lần vì có nhiều dòng log giống nhau | Một request có thể gọi method hai lần hoặc log ở nhiều tầng | Gắn request/correlation id và đo counter tại advice thay vì so mỗi chuỗi log. |
| Boot báo lỗi trùng tên bean | Hai định nghĩa sử dụng cùng name; chính sách override của Boot có thể từ chối | Đọc exception gốc và vị trí đăng ký; đặt một nguồn sở hữu duy nhất. |
| Advice ở web context chạy nhưng bean khác không chạy | Khác application context hoặc lời gọi không qua bean proxy | Kiểm tra parent/child context, vị trí đăng ký aspect và proxy bean đích. |

Đặc biệt, khi thấy hai tầng proxy hay nhiều interceptors khác nhau, không nên tự động xóa một tầng nếu chưa hiểu transaction, security hoặc async đang thực thi nhiệm vụ gì. Mục tiêu là loại bỏ cấu hình **trùng trách nhiệm**.

## 9. Chiến lược dọn Java/XML từng bước mà vẫn giữ hành vi

Một cách chuyển đổi cấu hình an toàn:

1. **Xác định chính xác các context đang chạy.** Phân biệt root, servlet context hoặc module context nếu ứng dụng có nhiều tầng.
2. **Chọn chủ sở hữu cấu hình Spring AOP cho từng context.** Ví dụ Java config bật `@EnableAspectJAutoProxy`, XML chỉ giữ beans chưa chuyển đổi.
3. **Liệt kê aspect beans theo tên/type**, loại những đăng ký trùng chức năng. `@ComponentScan`, `@Bean` và XML `<bean>` cần được kiểm tra như ba nguồn khác nhau.
4. **Đối chiếu pointcut/advice ở Java và XML.** Với hai advice cùng mục đích, chọn một định nghĩa phù hợp với hướng duy trì của dự án; không thay đổi chính sách nghiệp vụ ngoài phạm vi.
5. **So sánh lựa chọn proxy trước/sau.** Kiểm tra `proxyTargetClass`, interface injection, `final` methods và việc sử dụng `@Transactional` nếu có, vì thay đổi chế độ proxy có thể ảnh hưởng đến khả năng intercept.
6. **Chạy kiểm thử có quan sát.** Đảm bảo mỗi hành vi dùng chung chạy đúng số lần, nghiệp vụ cho kết quả cũ và các trường hợp ngoại lệ vẫn đúng.
7. **Chỉ khi đã xác nhận tương đương, xóa khai báo thừa** khỏi vị trí không còn sở hữu cấu hình. Giữ test để việc bổ sung XML/Java trong tương lai không tái tạo trùng lặp.

Đối với một project Spring Boot đang dùng starter Spring AOP, thường nên dựa vào auto-configuration được quản lý theo dòng Boot, tránh bật lại thủ công trừ khi ứng dụng có lý do riêng và đã kiểm thử tác động. Với Spring Framework thuần, chọn một trong hai cơ chế bật auto-proxy Java/XML cho cùng context và ghi rõ nơi được duy trì.

## 10. Tự kiểm tra cuối bài

- Nếu Java và XML đều bật Spring AOP, **liệu advice chắc chắn chạy hai lần?** Không. Phải kiểm tra beans và advisors; Spring có cơ chế hợp nhất auto-proxy creator.
- Nếu chỉ có một auto-proxy creator, **liệu aspect không thể bị trùng?** Không. Hai aspect beans hoặc hai advisors cùng pointcut có thể cùng chạy.
- Nếu có `@Aspect`, **đã đủ cho Spring nhận diện?** Không. Class phải được đăng ký thành Spring bean và có hỗ trợ auto-proxy phù hợp.
- Nếu `proxy-target-class=true` trong XML và `false` trong Java, **có thể chỉ đọc Java rồi tin là JDK proxy?** Không. Các lựa chọn proxy có thể được hợp nhất theo thiết lập mạnh hơn.
- Nếu tests thấy `isAopProxy=true`, **đã chứng minh advice chạy một lần?** Chưa. Cần đếm sự kiện advice khớp trên một lần gọi cụ thể.

### Tài liệu tham khảo Spring Framework

- Spring AOP: Proxying mechanisms — https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Enabling @AspectJ support — https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Declaring an aspect — https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html
- Schema-based AOP support — https://docs.spring.io/spring-framework/reference/core/aop/schema.html
- Mixing aspect types — https://docs.spring.io/spring-framework/reference/core/aop/mixing-styles.html

Trong Spring AOP, cấu hình Java/XML được xem là nhất quán khi **đường nạp context xác định, nơi bật proxy rõ ràng, mỗi aspect chỉ được đăng ký đúng số instance theo thiết kế và mỗi chính sách advice chạy đúng số lần trên bean đích**. Kiểm tra cùng lúc cả cấu hình và hành vi chạy sẽ phân biệt được một khai báo dư vô hại với một lỗi nhân đôi thực sự.

# equals, hashCode, toString và hành vi cần kiểm chứng trên proxy Spring AOP

## 1. Vì sao ba phương thức Object cần được kiểm tra khi dùng Spring AOP?

Một Spring bean nghiệp vụ có thể được `ApplicationContext` trao cho caller dưới dạng **AOP proxy**, thường là **JDK dynamic proxy** hoặc **class-based proxy (CGLIB)**. Vì vậy, lời gọi `equals(Object)`, `hashCode()` và `toString()` trên biến được inject không nhất thiết có cùng đường đi hoặc cùng kết quả với lời gọi trực tiếp trên **raw target**.

Đây là vấn đề của **Spring AOP và Spring-managed beans**, không phải một bài tổng quan về hợp đồng `Object` của Java. Điều cần biết khi cấu hình hoặc debug aspect là:

- Hai tham chiếu lấy từ context đang trỏ tới cùng **Spring proxy** hay tới các proxy khác?
- `equals()` có đang so sánh cấu hình proxy hoặc sử dụng quy tắc đặc biệt của Spring thay vì so sánh dữ liệu nghiệp vụ bên trong target?
- `hashCode()` có ổn định cho một proxy hay không; có an toàn nếu dùng proxy làm key trong `HashMap`/`HashSet`?
- `toString()` được dispatch thế nào; in log một proxy có kích hoạt advice hoặc truy cập dữ liệu nhạy cảm hay không?
- Kết quả có khác khi đổi từ JDK proxy sang CGLIB, hoặc khi target override ba phương thức này?
- Có thể dùng những phép kiểm tra nào **mà không suy luận sai từ tên class proxy hoặc một vài kết quả tình cờ**?

Kết luận định hướng: **Spring AOP proxy có danh tính và lớp hành vi riêng**. Không đồng nhất `proxy.equals(other)` với `target.equals(other)`, không đồng nhất `proxy.hashCode()` với `target.hashCode()`, và không coi chuỗi `proxy.toString()` là bằng chứng đầy đủ về cấu trúc proxy.

## 2. Nhắc lại ranh giới giữa proxy và target

```text
  Bean gọi từ ApplicationContext
             |
             v
       Spring AOP proxy
        /           \
JDK interface      CGLIB subclass
       \             /
        \           /
         v         v
  Spring interceptor/advisor handling
             |
             v
       Target bean method
```

Với Spring Framework thuần, target có business interface thường dẫn tới JDK proxy; nếu không có interface phù hợp thì class-based proxy. Thiết lập `proxyTargetClass = true` yêu cầu CGLIB; Spring Boot có thể chọn mặc định khác theo cấu hình auto-proxy.

Điều quan trọng cho ba phương thức `Object` là **caller gọi trên đối tượng proxy**, và Spring quyết định có xử lý riêng hay chuyển tiếp xuống target. Đường đi chính xác còn phụ thuộc phiên bản Spring, loại proxy, interfaces được proxy, `Advisor`, `TargetSource`, method override và các tối ưu hạ tầng.

Không nên dùng công thức “mọi lời gọi trên proxy đều đi qua target rồi mới có kết quả” hoặc “mọi method trên proxy đều kích hoạt advice”. Cả hai đều bỏ qua cơ chế dispatch thực sự của Spring AOP.

## 3. `equals(Object)` trên Spring AOP proxy

### 3.1. Trường hợp JDK dynamic proxy

Trong triển khai `JdkDynamicAopProxy` của Spring, `equals` có **nhánh xử lý riêng** khi không có một interface được proxy khai báo method `equals(Object)` tương ứng. Khi đó `equals` được xử lý bởi phần proxy, thay vì mặc định gọi thẳng `equals` của target.

Ý nghĩa thực tế:

- `proxy.equals(proxy)` phải trả `true` (tính phản xạ).
- Việc hai proxies cùng bao một target object **không tự bảo đảm** `proxy1 == proxy2` hoặc `proxy1.equals(proxy2)`.
- Spring có thể so sánh các đặc tính cấu hình proxy như **các interface, advisor chain và `TargetSource`** khi xác định hai AOP proxies có tương đương theo cơ chế Spring hay không.
- `proxy.equals(rawTarget)` không có nghĩa giống `rawTarget.equals(rawTarget)`.
- Khi interface được proxy **có khai báo lại `equals(Object)`**, nhánh dispatch của JDK proxy có thể khác; cần kiểm tra đúng phiên bản và cấu hình thay vì mặc định áp dụng một quy tắc cho mọi interface.

Không phải lúc nào Spring cũng dùng quy tắc **identity của Java object** cho `equals` trên proxy. Nhưng cũng không có bảo đảm rằng nó sẽ áp dụng **domain equality của entity** theo logic do target tự định nghĩa. Đây là lý do nên viết test cho trường hợp thực tế thay vì đoán.

### 3.2. Trường hợp CGLIB class proxy

Spring CGLIB AOP có **EqualsInterceptor** dành cho `equals(Object)` khi method có thể được override và interceptor được cài đặt phù hợp. Nó có thể xử lý so sánh theo danh tính proxy và cấu hình proxy/advisor/target source, không nhất thiết gọi `target.equals(...)`.

Ví dụ hai Spring proxies có cùng class runtime hoặc cùng loại target **chưa đủ** để kết luận chúng `equals` nhau. Số bean, scope, target source và advisor configuration đều là thông tin có liên quan.

Một **cảnh báo kỹ thuật**: class-based proxy không override được method `final` (bao gồm `final equals`), và không thể subclass class `final`. Nếu bean có các ràng buộc đó, không thiết kế test dựa trên giả định mọi lời gọi Object methods sẽ được Spring CGLIB intercept bình thường.

### 3.3. Không lấy domain equality của target làm hợp đồng proxy

Giả sử target chứa `id = "INV-10"` và override `equals` để so sánh theo id. Điều này **không chứng minh** hai references tới AOP proxies sẽ so sánh bằng nhau chỉ vì hai raw targets có cùng id.

```java
// Fragment minh họa; các biến lấy từ cấu hình Spring thực tế:
boolean sameReference = proxyA == proxyB;
boolean sameByProxyEquals = proxyA.equals(proxyB);
boolean sameBusinessId = idA.equals(idB);
```

Ba biểu thức kiểm tra **ba quan hệ khác nhau**:

1. `==`: cùng một Java object reference.
2. `equals` trên AOP proxy: semantics thực tế của Spring proxy trong cấu hình cụ thể.
3. So sánh **business key**: domain identity mà nghiệp vụ chủ động lựa chọn.

Nếu chương trình cần gom các giao dịch theo business id, hãy lấy **id bất biến** để làm key, hoặc dùng một value object chuyên biệt; đừng lấy sự bằng nhau của các AOP proxies làm tiêu chuẩn nghiệp vụ mặc định.

## 4. `hashCode()` trên Spring AOP proxy

`hashCode()` có quan hệ trực tiếp với `equals()`: nếu hai đối tượng được coi là bằng nhau, hash code cần bằng nhau. Một AOP proxy cũng phải tôn trọng hợp đồng này trong phạm vi semantics mà Spring áp dụng.

### 4.1. JDK proxy

Trong `JdkDynamicAopProxy` của Spring, nếu không có proxied interface nào khai báo `hashCode()` thì Spring có **nhánh xử lý `hashCode` của proxy**. Triển khai Spring có thể tính giá trị dựa trên loại handler/đặc điểm `TargetSource`, không phải lấy nguyên `hashCode()` của target.

**Không assert một số nguyên hash cố định.** Hash code phụ thuộc đối tượng, identity/cấu hình/implementation và có thể khác giữa lần chạy JVM. Phép kiểm hợp lý là tính ổn định trong lúc proxy và các dữ liệu liên quan không thay đổi.

### 4.2. CGLIB proxy

Trong cơ chế Spring CGLIB thông thường, `HashCodeInterceptor` chuyên trách xử lý `hashCode()` trên proxy. Điều này đi cùng xử lý đặc biệt của `EqualsInterceptor`.

Khi target implement `hashCode` dựa trên business id, `proxy.hashCode()` **không được giả định** là giá trị hash do target tính. Không assert `proxy.hashCode() == rawTarget.hashCode()` trừ khi đó là hợp đồng cụ thể đã được xác minh trên nền tảng đang triển khai và thực sự cần.

### 4.3. Dùng proxy làm key cho `HashMap` hoặc `HashSet`

Một proxy được tạo và sử dụng ổn định có thể làm key theo semantics của nó, nhưng cần cân nhắc:

- **Scope:** singleton bean thường trả cùng Spring reference trong một context; prototype beans tạo các instances khác nhau; scoped proxy có thể là một reference ổn định trong khi target phía dưới thay đổi theo request.
- **Thay đổi proxy configuration:** hai proxies khác advisors, interfaces hoặc target sources có thể không có equality tương đương.
- **Mutability:** tránh thay đổi trạng thái/cấu hình tham gia `equals`/`hashCode` trong thời gian object nằm trong một hash collection.
- **Mục đích key:** nếu business key là `orderId`, lưu `orderId`, không lưu `OrderService` proxy và suy ra business identity từ nó.
- **Cross-context:** singleton theo Spring context không có nghĩa cùng reference hoặc cùng proxy equality ở context khác.

Mẫu phù hợp cho bộ nhớ cache nghiệp vụ:

```java
Map<String, String> resultsByOrderId = new HashMap<>();
resultsByOrderId.put("ORD-7", "processed");
```

Đây là fragment cần import `java.util.Map` và `java.util.HashMap`. Giá trị key `"ORD-7"` có ý nghĩa nghiệp vụ rõ hơn nhiều so với `OrderService` proxy.

## 5. `toString()` trên Spring AOP proxy

Khác với việc Spring AOP có nhánh riêng dành cho `equals/hashCode`, **`toString()` thường được xử lý theo đường dispatch method của proxy**. Khi target override `toString()`, Spring proxy có thể chuyển lời gọi đến target hoặc đi qua interceptor chain theo cấu hình.

Không nên gộp ba method vào một quy tắc “Spring luôn override mọi Object method theo cùng cách”.

Các điểm quan trọng:

- `proxy.toString()` có thể cho chuỗi mà target khai báo, nhưng **không phải API bảo đảm trả kiểu class runtime của proxy**.
- Một `toString()` mặc định hoặc được override có thể hiển thị giá trị khác nhau tùy class target, proxy style và advice hiện có.
- Nếu pointcut/advisor được thiết kế **có thể khớp `toString()`**, lời gọi có khả năng bị can thiệp; một pointcut **chỉ** chọn `OrderService.process(..)` thì không tự chuyển mọi lời gọi `toString()` thành `process` advice.
- `toString()` không phải cơ chế quản lý lifecycle và không phải công cụ chuẩn để liệt kê advisor chain.
- In một proxy bằng `logger.info("bean={}", bean)` hoặc nối chuỗi có thể dẫn tới lời gọi `toString()`; nếu target `toString()` truy cập lazy data, remote service hoặc thông tin nhạy cảm, logging có thể tốn chi phí và rò rỉ dữ liệu.

Ưu tiên logging **metadata được chọn rõ** (bean name, class target từ API Spring chẩn đoán, request id đã được kiểm soát) thay vì log toàn bộ `toString()` của một bean có trạng thái.

### 5.1. `getClass().getName()` khác `toString()`

```java
String runtimeClass = proxy.getClass().getName();
String printable = proxy.toString();
```

- `runtimeClass`: tên class thực sự của object đang giữ; có thể là lớp `jdk.proxy...` hoặc lớp sinh bằng Spring CGLIB.
- `printable`: chuỗi do dispatch `toString()` quyết định; có thể từ target hoặc advice tùy cấu hình.

Hai giá trị không cần trùng nhau. Tên generated proxy class có thể thay đổi theo JDK/Spring version nên không nên assert chính xác toàn bộ tên class. Dùng `AopUtils.isJdkDynamicProxy`, `AopUtils.isCglibProxy` và `AopUtils.getTargetClass` để kiểm tra đúng mục đích.

## 6. Bảng so sánh khi kiểm tra hành vi Object methods

| Phép kiểm | JDK Spring AOP proxy | CGLIB Spring AOP proxy | Cách kiểm tra an toàn |
| --- | --- | --- | --- |
| `proxy == proxy` | `true` | `true` | Phép kiểm identity Java. |
| `proxy.equals(proxy)` | Kỳ vọng `true` | Kỳ vọng `true` | Assert phản xạ trên bean thật từ context. |
| `proxy.hashCode()` gọi hai lần | Kỳ vọng ổn định khi state/config không đổi | Kỳ vọng ổn định khi state/config không đổi | So sánh hai giá trị trong cùng test; không hardcode số. |
| `proxy.equals(rawTarget)` | Không mặc định bằng `true` | Không mặc định bằng `true` | Đo trong context cụ thể; tránh dựa vào raw-target identity. |
| `proxy1.equals(proxy2)` | Phụ thuộc semantics/cấu hình | Phụ thuộc semantics/cấu hình | Kiểm tra rõ các proxies/target sources, không phỏng đoán. |
| `proxy.toString()` | Có thể dispatch tới target | Có thể dispatch tới target | Đặt mục đích `toString` rõ ràng, kiểm tra output và advice. |
| `proxy.getClass()` | JDK generated proxy class | CGLIB generated subclass | Dùng `AopUtils` thay vì dựa vào tên generated class. |
| `proxy instanceof ConcreteService` | Thường `false` nếu dùng interface-based proxy | Thường `true` nếu class proxy hợp lệ | Test injection/cast theo hợp đồng interface hoặc class. |

Bảng mô tả **Spring AOP theo proxy thông thường**. Mỗi assert về kết quả business cần chạy trên **Spring version, bean scope, advice chain và proxy settings** của dự án. Không coi một giá trị quan sát ở project demo là hợp đồng tương thích vĩnh viễn của Spring internals.

## 7. Ví dụ Java 17+ chạy được: đo ba phương thức trên JDK và CGLIB

Ví dụ xây dựng **hai `ApplicationContext` độc lập** trên cùng business interface và aspect:

- Context `JDK` dùng `@EnableAspectJAutoProxy(proxyTargetClass=false)`.
- Context `CGLIB` dùng `@EnableAspectJAutoProxy(proxyTargetClass=true)`.
- `ReportOperations` là business interface; `ReportService` implement interface đó.
- Aspect chỉ advice `runReport()`, **không chọn `equals`, `hashCode`, `toString`**.
- `ReportService.toString()` trả chuỗi cố định nhằm quan sát dispatch mà không phụ thuộc giá trị hash hay tên class được sinh.

Để tránh khẳng định những equality internals không được hứa hẹn, chương trình chỉ in các đặc tính ổn định/có thể giải thích: type proxy, phản xạ `equals`, hash ổn định qua hai lần gọi, `toString`, và số lần advice.

### 7.1. Cấu trúc project

```text
spring-proxy-object-methods/
├── pom.xml
└── src/main/java/com/example/proxycheck/
    ├── ReportOperations.java
    ├── ReportService.java
    ├── TraceAspect.java
    └── DemoApp.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-proxy-object-methods</artifactId>
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

`spring-context` quản lý bean và kéo theo Spring AOP trong dependency graph của bản mẫu, còn `aspectjweaver` cung cấp phần thư viện cần thiết để Spring hiểu khai báo `@Aspect`/pointcut. Mã này dùng **Spring proxy AOP**, không cấu hình AspectJ weaving agent.

### 7.3. `src/main/java/com/example/proxycheck/ReportOperations.java`

```java
package com.example.proxycheck;

public interface ReportOperations {
    String runReport(String reportId);
}
```

Interface **không tự khai báo** `equals(Object)` hoặc `hashCode()`: đây là trường hợp phổ biến để quan sát xử lý riêng của Spring JDK proxy.

### 7.4. `src/main/java/com/example/proxycheck/ReportService.java`

```java
package com.example.proxycheck;

public class ReportService implements ReportOperations {

    @Override
    public String runReport(String reportId) {
        System.out.println("[TARGET] run " + reportId);
        return "report:" + reportId;
    }

    @Override
    public String toString() {
        return "ReportService(target)";
    }
}
```

Target chỉ override `toString`. `equals` và `hashCode` giữ cách triển khai từ `Object`, giúp bài demo tập trung vào khác biệt **proxy handling** mà không trộn thêm domain equality.

### 7.5. `src/main/java/com/example/proxycheck/TraceAspect.java`

```java
package com.example.proxycheck;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    private final AtomicInteger count = new AtomicInteger();

    @Before("execution(public * com.example.proxycheck.ReportService.runReport(..))")
    public void beforeRun() {
        count.incrementAndGet();
        System.out.println("[ADVICE] before runReport");
    }

    public int count() {
        return count.get();
    }
}
```

Pointcut chọn rõ một method nghiệp vụ. Việc gọi `equals`, `hashCode` và `toString` **không nhằm kích hoạt advice này**. `AtomicInteger` giúp kiểm tra chính xác số lời gọi trong ví dụ.

### 7.6. `src/main/java/com/example/proxycheck/DemoApp.java`

```java
package com.example.proxycheck;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

public class DemoApp {

    @Configuration
    static class SharedBeans {
        @Bean
        ReportOperations reportOperations() {
            return new ReportService();
        }

        @Bean
        TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    @Configuration
    @Import(SharedBeans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    static class JdkConfig {
    }

    @Configuration
    @Import(SharedBeans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    static class CglibConfig {
    }

    private static void inspect(String label, Class<?> configClass) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(configClass)) {

            ReportOperations proxy = context.getBean(ReportOperations.class);
            TraceAspect aspect = context.getBean(TraceAspect.class);

            System.out.println("[" + label + "] isJdk="
                    + AopUtils.isJdkDynamicProxy(proxy));
            System.out.println("[" + label + "] isCglib="
                    + AopUtils.isCglibProxy(proxy));
            System.out.println("[" + label + "] equalsSelf="
                    + proxy.equals(proxy));

            int firstHash = proxy.hashCode();
            int secondHash = proxy.hashCode();
            System.out.println("[" + label + "] hashStable="
                    + (firstHash == secondHash));

            System.out.println("[" + label + "] toString="
                    + proxy.toString());
            System.out.println("[" + label + "] adviceBeforeBusiness="
                    + aspect.count());

            String result = proxy.runReport(label);
            System.out.println("[" + label + "] result=" + result);
            System.out.println("[" + label + "] adviceAfterBusiness="
                    + aspect.count());
        }
    }

    public static void main(String[] args) {
        inspect("JDK", JdkConfig.class);
        inspect("CGLIB", CglibConfig.class);
    }
}
```

**Vì sao hai context?** `@EnableAspectJAutoProxy(proxyTargetClass=false)` và `@EnableAspectJAutoProxy(proxyTargetClass=true)` cùng hiệu lực trong một context có thể hợp nhất theo thiết lập mạnh hơn; tách context giúp so sánh đúng hai lựa chọn proxy. Cả hai context đều có một `TraceAspect` riêng và cùng định nghĩa target nghiệp vụ.

### 7.7. Chạy và dự kiến stdout

Với Maven và JDK 17+ tại thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.proxycheck.DemoApp
```

Các dòng do chương trình tự in ra theo thứ tự (bỏ qua log Maven hoặc Spring nếu môi trường có):

```text
[JDK] isJdk=true
[JDK] isCglib=false
[JDK] equalsSelf=true
[JDK] hashStable=true
[JDK] toString=ReportService(target)
[JDK] adviceBeforeBusiness=0
[ADVICE] before runReport
[TARGET] run JDK
[JDK] result=report:JDK
[JDK] adviceAfterBusiness=1
[CGLIB] isJdk=false
[CGLIB] isCglib=true
[CGLIB] equalsSelf=true
[CGLIB] hashStable=true
[CGLIB] toString=ReportService(target)
[CGLIB] adviceBeforeBusiness=0
[ADVICE] before runReport
[TARGET] run CGLIB
[CGLIB] result=report:CGLIB
[CGLIB] adviceAfterBusiness=1
```

Ý nghĩa:

1. **Hai proxy type khác nhau** dù dùng chung source class và aspect. `AopUtils` cung cấp bằng chứng trực tiếp hơn so với so sánh tiền tố tên class.
2. `equalsSelf=true` chứng minh phản xạ ngay trên object Spring trả về, **không chứng minh** `proxy.equals(rawTarget)` hay `proxyA.equals(proxyB)`.
3. `hashStable=true` chứng minh hai lời gọi liên tiếp trong cấu hình ví dụ cho cùng hash; chương trình **không in hash number** vì đó không phải hợp đồng portable.
4. `toString` hiển thị output có chủ đích của target. Nó không trả về tên generated proxy class, và không nên được dùng để phát hiện proxy type.
5. `adviceBeforeBusiness=0` cho biết các lời gọi Object methods ở trên **không kích hoạt `@Before` vốn chỉ chọn `runReport`**.
6. Sau một lời gọi business qua Spring bean proxy, `adviceAfterBusiness=1`, method target chạy một lần và return value giữ nguyên.

Ví dụ không khẳng định rằng `toString()` **không thể** bị advice. Nó chỉ cho thấy **pointcut của ứng dụng đã cố ý chọn riêng business method**.

## 8. Kiểm chứng thêm equality thực tế giữa hai Spring proxies

Một ứng dụng cần so sánh các proxies nên kiểm thử công khai những trường hợp nó sẽ thật sự thực hiện:

```java
// Đoạn minh họa đặt trong test có ApplicationContext context.
Object first = context.getBean("reportOperations");
Object second = context.getBean("reportOperations");

System.out.println("sameReference=" + (first == second));
System.out.println("equalByEquals=" + first.equals(second));
System.out.println("hashEqualIfEquals="
        + (!first.equals(second) || first.hashCode() == second.hashCode()));
```

Với bean singleton như ví dụ, hai lần lookup cùng bean name trong một context bình thường sẽ trả cùng reference; khi đó hai dòng đầu thường là `true`. Nhưng đó là kết quả của **singleton bean lookup** và **proxy identity**, không phải chứng cứ hai *khác nhau* proxies có semantics bằng nhau.

Khi cần đánh giá **hai proxies khác nhau**, thiết lập hai bean definitions riêng hoặc hai Spring contexts; kiểm thử:

```java
boolean leftEqualsRight = left.equals(right);
boolean rightEqualsLeft = right.equals(left);
boolean hashesAgreeWhenEqual =
        !leftEqualsRight || left.hashCode() == right.hashCode();
```

Đây là fragment đòi hỏi biến `left` và `right` trong test. Ngoài `equals`/hash, nên xem xét **symmetry** giữa hai chiều và **transitivity** khi có ba đối tượng. Không hardcode rằng hai proxy khác nhau cùng bọc một loại target bắt buộc bằng nhau.

Nếu target tự override `equals/hashCode`, hãy chạy lại chính test đó dưới JDK proxy và CGLIB; việc target override không có nghĩa cả hai proxy styles sẽ chuyển tiếp method theo cách giống nhau.

### 8.1. Test đúng scope và đường lấy bean

Các trường hợp có giá trị thực tế:

| Tình huống | Điều phải quan sát |
| --- | --- |
| Lấy singleton bean cùng name hai lần | `==`, `equals`, `hashCode`; expected stable reference trong cùng context. |
| Lấy prototype bean hai lần | Hai bean/proxy references và semantics equality; không mặc định chúng bằng nhau. |
| Hai bean names trỏ tới hai target instances | Equality của hai proxies và hash contract nếu bằng nhau. |
| Request/session scoped proxy | Tách reference proxy sống lâu khỏi target thay đổi theo scope. |
| Hai ApplicationContexts độc lập | So sánh sau khi xác định có đúng cùng cấu hình và không dựa vào singleton toàn JVM. |
| Target override Object methods | Kiểm tra symmetry/consistency của proxy, target và các domain value objects liên quan. |

Hãy đánh giá semantics mà ứng dụng thật sự cần. Không cần can thiệp vào internals nếu một business identifier độc lập đủ làm key.

## 9. Những điều dễ sai khi debug ba phương thức trên Spring proxy

### 9.1. “Target override `equals`, vậy proxy cũng dùng y hệt”

**Sai khi coi là quy tắc mặc định.** Spring AOP có thể xử lý `equals` ở hạ tầng proxy, đặc biệt khi interface không khai báo method đó, hoặc khi dùng CGLIB interceptor chuyên dụng. Hãy tách test raw target và test proxy được lấy từ Spring.

### 9.2. “Hai proxy của cùng target class phải bằng nhau”

**Không đủ căn cứ.** Class target chỉ là một yếu tố; interface set, advisors và `TargetSource` có thể tham gia. `proxy1 == proxy2` lại là phép đo identity riêng.

### 9.3. “Hash code bằng nhau chứng minh hai Spring beans là một”

**Không.** Hash collision luôn có thể xảy ra. Dùng `==` để kiểm tra cùng reference, bean name/type để kiểm tra cấu hình, business key để so sánh nghiệp vụ và `equals` theo hợp đồng thực tế. Hash chỉ giúp cấu trúc dữ liệu phân phối bucket, không chứng minh identity.

### 9.4. “In `toString` là đủ biết bean có bị proxy”

**Không.** Target có thể override `toString` và trả một chuỗi cố định như demo. Dùng:

```java
boolean aop = org.springframework.aop.support.AopUtils.isAopProxy(bean);
boolean jdk = org.springframework.aop.support.AopUtils.isJdkDynamicProxy(bean);
boolean cglib = org.springframework.aop.support.AopUtils.isCglibProxy(bean);
```

Đây là fragment cần một biến `bean` đã lấy từ container. Có AOP proxy vẫn **không đảm bảo** một method cụ thể được advice; cần kiểm tra pointcut và lần gọi.

### 9.5. “`toString` vô hại, có thể log mọi Spring bean”

**Không luôn đúng.** `toString` của target có thể chứa object graph lớn, property bí mật, lazy-loaded association hoặc logic tính toán. Một số advice còn có thể khớp method đó khi pointcut quá rộng. Trong production, logging chọn thông tin đã lọc là lựa chọn an toàn và dễ kiểm soát hơn.

### 9.6. “CGLIB luôn chặn mọi Object method”

**Không.** Class proxy chịu giới hạn của inheritance và khả năng override; `final` methods, `private` methods hoặc class `final` có hạn chế. Riêng `equals/hashCode` còn có nhánh triển khai đặc biệt. Không chuyển từ JDK sang CGLIB chỉ vì muốn “đảm bảo” domain equality, vì đó không phải trách nhiệm của việc chọn proxy type.

### 9.7. “Không có dòng `@Before` nghĩa là Object methods không đi qua proxy”

**Sai về cách suy luận.** Advice có thể chỉ chọn business method. Một Object method vẫn có thể được xử lý bởi proxy mà không khớp advisor đó. Khi cần xác định luồng dispatch, xem các advisors/pointcuts và kiểm thử riêng từng method.

## 10. Checklist khi refactor AOP hoặc nâng phiên bản Spring

1. **Xác định đúng proxy type** từ bean đã inject, bằng `AopUtils.isJdkDynamicProxy`/`isCglibProxy`.
2. **Xác định bean scope và reference semantics:** singleton, prototype, scoped proxy; phân biệt proxy và target.
3. **Kiểm tra `equals` phản xạ và đối xứng** trên đúng các tổ hợp object ứng dụng có ý định so sánh.
4. **Kiểm tra `hashCode` ổn định** và hợp đồng `equals => same hash`; không assert hash number cụ thể.
5. **Kiểm tra `toString` có output hợp lệ**, không phát sinh side effects không mong muốn, không làm lộ thông tin nhạy cảm.
6. **Đo số lần advice** trước/sau khi gọi `equals/hashCode/toString`, nhất là khi dùng pointcut rộng hoặc advisor đặc biệt.
7. **Đối chiếu JDK vs CGLIB** nếu thay `proxyTargetClass`, thay interface, bật Spring Boot auto-config hoặc nâng phiên bản framework.
8. **Không lấy proxy equality làm business identity** nếu yêu cầu chính là so theo id của domain object.
9. **Kiểm tra usage trong collections/caches**: nếu đang dùng proxy làm key, xác định lifecycle của key và tính ổn định theo cấu hình thật.
10. **Đưa các quan sát vào automated tests** chạy trên Spring context giống production; phân biệt sự bảo đảm từ Java object contract với chi tiết hiện thực nội bộ của một phiên bản Spring.

### Tài liệu đối chiếu

- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — AOP Proxies: https://docs.spring.io/spring-framework/reference/core/aop/introduction-proxies.html
- Spring Framework — Spring AOP APIs: https://docs.spring.io/spring-framework/reference/core/aop-api.html
- Spring Framework — JdkDynamicAopProxy source: https://github.com/spring-projects/spring-framework/blob/main/spring-aop/src/main/java/org/springframework/aop/framework/JdkDynamicAopProxy.java
- Spring Framework — CglibAopProxy source: https://github.com/spring-projects/spring-framework/blob/main/spring-aop/src/main/java/org/springframework/aop/framework/CglibAopProxy.java

**Khi làm việc với Spring AOP, hãy coi ba phương thức `equals`, `hashCode`, `toString` là những lời gọi có ngữ nghĩa cần kiểm chứng ngay trên proxy thực tế.** Điều này ngăn những giả định sai về identity, tránh cache bugs và giúp phân biệt rõ chính sách advice với cơ chế object dispatch của Spring.

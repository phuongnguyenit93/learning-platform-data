# `<aop:aspectj-autoproxy>`: kích hoạt `@Aspect` từ cấu hình XML trong Spring

Trong ứng dụng Spring Framework sử dụng XML để khai báo bean, phần tử **`<aop:aspectj-autoproxy/>`** kích hoạt cơ chế Spring AOP tự tạo proxy cho các Spring bean phù hợp với pointcut của aspect viết bằng annotation **`@Aspect`, `@Before`, `@AfterReturning`, `@Around`...**. Đây là cách sử dụng cú pháp annotation của AspectJ để định nghĩa *advice/pointcut* trong một application context được cấu hình bằng XML.

Điểm cần phân biệt: XML **bật cơ chế xử lý aspect**, còn các class Java mang `@Aspect` **vẫn phải được đăng ký thành Spring bean** (trực tiếp bằng `<bean>` hoặc bằng component scanning). Spring AOP thực hiện advice thông qua **Spring proxy**, không tự động weave bytecode mọi đối tượng Java trong JVM.

Bài này tập trung vào cấu hình và vận hành **Spring Aspect/AOP**. Không đi sâu các mô hình AOP độc lập với Spring.

## 1. `<aop:aspectj-autoproxy/>` làm gì?

Ví dụ khai báo cơ bản:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <aop:aspectj-autoproxy/>

    <!-- Cả target và aspect đều cần là Spring bean. -->
    <bean id="orderService" class="com.example.xmlaop.OrderServiceImpl"/>
    <bean id="loggingAspect" class="com.example.xmlaop.LoggingAspect"/>
</beans>
```

Khi Spring xây dựng `ApplicationContext`:

1. XML namespace `aop` cung cấp phần tử `<aop:aspectj-autoproxy/>`. Spring đăng ký bộ xử lý tự tạo AOP proxy (`AnnotationAwareAspectJAutoProxyCreator`, một dạng bean post-processor).
2. Spring tạo các bean được khai báo, trong đó có bean `loggingAspect`. Trên bean aspect, Spring nhận diện annotation `@Aspect` và các advice dùng annotation.
3. Khi bean `orderService` có method khớp pointcut, Spring cung cấp một **proxy** thay cho việc đưa trực tiếp target object cho caller lấy từ context.
4. Lời gọi từ client **qua proxy** kích hoạt advice; advice chạy trước/sau/vòng quanh target tùy annotation. Việc gọi method trên target vẫn là logic do target cung cấp.

`<aop:aspectj-autoproxy/>` **không** tự component-scan, **không** tự tạo bean cho mọi class có `@Aspect` và **không** làm cho lời gọi trực tiếp bằng `new` trở thành lời gọi qua proxy. Nó kích hoạt cách Spring áp dụng các aspect bean đã có trong context.

## 2. Ví dụ chạy được với Spring Framework 6 và Java 17

Ví dụ tạo một Spring application context bằng XML (không cần Spring Boot), có một service xử lý đơn hàng và một aspect ghi log trước lời gọi service.

### 2.1. Cấu trúc dự án

```text
spring-xml-aop/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/xmlaop/
        │   ├── Demo.java
        │   ├── OrderService.java
        │   ├── OrderServiceImpl.java
        │   └── LoggingAspect.java
        └── resources/
            └── applicationContext.xml
```

**`pom.xml`** (các phiên bản cụ thể phục vụ ví dụ độc lập; dự án thực tế có thể quản lý phiên bản bằng BOM):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-xml-aop</artifactId>
    <version>1.0.0</version>

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
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` cung cấp application context và quản lý bean; `spring-aop` cung cấp cơ chế AOP; `aspectjweaver` cung cấp các type và hỗ trợ phân tích biểu thức pointcut kiểu AspectJ được Spring AOP sử dụng. Ví dụ chỉ dùng **Spring proxy AOP**: không cài Java agent hay dùng AspectJ compile-time/load-time weaving.

### 2.2. Interface và target bean

**`src/main/java/com/example/xmlaop/OrderService.java`**

```java
package com.example.xmlaop;

public interface OrderService {
    void placeOrder(String orderId);
}
```

**`src/main/java/com/example/xmlaop/OrderServiceImpl.java`**

```java
package com.example.xmlaop;

public class OrderServiceImpl implements OrderService {
    @Override
    public void placeOrder(String orderId) {
        System.out.println("SERVICE placeOrder " + orderId);
    }
}
```

Ta dùng interface để thấy hành vi của **JDK dynamic proxy** khi để chế độ mặc định `proxy-target-class="false"`.

### 2.3. Aspect khai báo bằng annotation

**`src/main/java/com/example/xmlaop/LoggingAspect.java`**

```java
package com.example.xmlaop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class LoggingAspect {
    @Before("execution(* com.example.xmlaop.OrderServiceImpl.placeOrder(..))")
    public void beforePlaceOrder() {
        System.out.println("ASPECT before placeOrder");
    }
}
```

- `@Aspect` cho Spring biết bean này chứa định nghĩa aspect.
- `@Before` khai báo advice chạy trước khi method được pointcut chọn thực thi.
- Biểu thức `execution(* com.example.xmlaop.OrderServiceImpl.placeOrder(..))` chọn method `placeOrder` của implementation trong ví dụ. Spring dùng pointcut đó để xác định phương thức nào cần áp dụng advice khi gọi qua proxy.
- Class aspect **không cần `@Component`** khi đã khai báo thành Spring bean bằng XML.

Đừng tự gọi `new LoggingAspect()` rồi mong Spring tự áp dụng. Phải để instance đó thuộc Spring context.

### 2.4. Kích hoạt proxy trong XML

**`src/main/resources/applicationContext.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <!-- Bật @Aspect-based Spring AOP proxying. -->
    <aop:aspectj-autoproxy proxy-target-class="false"/>

    <bean id="orderService" class="com.example.xmlaop.OrderServiceImpl"/>

    <!-- Đăng ký aspect làm Spring bean: bước cần thiết. -->
    <bean id="loggingAspect" class="com.example.xmlaop.LoggingAspect"/>
</beans>
```

Trong cấu hình này:

- `xmlns:aop` và cặp schema `spring-aop.xsd` cho phép XML nhận phần tử thuộc Spring AOP namespace.
- `<aop:aspectj-autoproxy/>` kích hoạt trình tự tạo proxy cho các target bean phù hợp.
- Hai `<bean>` đưa **target** và **aspect** vào cùng application context.
- `proxy-target-class="false"` yêu cầu ưu tiên JDK proxy khi bean có interface thích hợp. Nếu target không có interface, Spring có thể dùng proxy dựa trên class. Đây là lựa chọn proxy, không liên quan việc có dùng annotation trên aspect hay không.

Không cần đặt `@EnableAspectJAutoProxy` trong code Java để bật thêm lần nữa; đó là dạng kích hoạt tương ứng khi dùng cấu hình bằng annotation/Java. Ví dụ này cố ý dùng XML làm nguồn cấu hình.

### 2.5. Client chạy qua Spring context

**`src/main/java/com/example/xmlaop/Demo.java`**

```java
package com.example.xmlaop;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public class Demo {
    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                 new ClassPathXmlApplicationContext("applicationContext.xml")) {

            OrderService service =
                context.getBean("orderService", OrderService.class);

            System.out.println("PROXY " + AopUtils.isAopProxy(service));
            System.out.println("JDK_PROXY " + AopUtils.isJdkDynamicProxy(service));

            service.placeOrder("A001");
        }
    }
}
```

Chạy ở thư mục dự án có Maven và JDK 17 trở lên:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.xmlaop.Demo
```

Các dòng do code của ví dụ in ra, theo đúng thứ tự (không tính thông báo riêng từ môi trường Maven):

```text
PROXY true
JDK_PROXY true
ASPECT before placeOrder
SERVICE placeOrder A001
```

Lý do: `getBean(...)` trả Spring proxy cho service; lời gọi `service.placeOrder("A001")` đi qua proxy và chạy `@Before` trước thân method. Nếu bỏ `<aop:aspectj-autoproxy/>` khỏi XML nhưng giữ hai bean, với cấu hình ví dụ này `getBean` sẽ nhận target thường: `PROXY false`, `JDK_PROXY false`, và không có dòng log `ASPECT`. Đây là cách đối chiếu hữu ích để nhận diện tác dụng của phần tử cấu hình.

## 3. Đăng ký aspect bằng component scanning trong XML

Ngoài khai báo từng `<bean>`, ứng dụng có thể để Spring quét annotation để tìm bean. Khi đó `@Aspect` **chỉ định nghĩa aspect**, còn `@Component` biến class đó thành ứng viên được component-scan đăng ký:

```java
package com.example.xmlaop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class LoggingAspect {
    @Before("execution(* com.example.xmlaop.OrderServiceImpl.placeOrder(..))")
    public void beforePlaceOrder() {
        System.out.println("ASPECT before placeOrder");
    }
}
```

Nếu muốn component-scan cả service, thêm `@Service` vào `OrderServiceImpl`. XML tương ứng có thể viết:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan base-package="com.example.xmlaop"/>
    <aop:aspectj-autoproxy/>
</beans>
```

**Đây là biến thể cấu hình**, không phải phần XML thay thế vào ví dụ hoàn chỉnh ở mục 2 nếu chưa thêm `@Component`/`@Service` vào các class. Nếu đã chuyển sang scan, hãy bỏ những khai báo `<bean>` trùng để tránh hai instance không chủ định.

Nhớ hai trách nhiệm độc lập:

| Khai báo | Tác dụng |
| --- | --- |
| `<context:component-scan .../>` | Đăng ký các class đủ điều kiện thành Spring bean, gồm aspect có `@Component` |
| `<aop:aspectj-autoproxy/>` | Kích hoạt Spring AOP proxy và áp dụng advice từ các bean mang `@Aspect` |

## 4. Tùy chọn quan trọng: `proxy-target-class` và `expose-proxy`

Hai thuộc tính của `<aop:aspectj-autoproxy>` điều khiển hạ tầng proxy, không thay đổi annotation trong `@Aspect`:

~~~xml
<aop:aspectj-autoproxy proxy-target-class="false" expose-proxy="false"/>
~~~

- `proxy-target-class="false"`: với bean có interface phù hợp, Spring thường chọn JDK dynamic proxy; không có interface có thể dùng class proxy. `true` yêu cầu class-based proxy, chịu giới hạn final/private và module visibility.
- `expose-proxy="true"`: cho phép `AopContext.currentProxy()` trong lời gọi đã đi qua proxy, hữu ích cho trường hợp rất cụ thể nhưng tạo coupling và phụ thuộc thread. Nó **không tự chuyển** `this.method()` thành proxy call.
- Trong context có nhiều cấu hình AOP/transaction, các auto-proxy settings có thể được hợp nhất; hãy kiểm tra loại proxy thực tế bằng `AopUtils`, đừng dựa vào một dòng XML.

Bài **“proxy-target-class và expose-proxy trong cấu hình XML”** có ví dụ thay từng thuộc tính, đối chiếu JDK/CGLIB và self-invocation.

## 5. Vì sao annotation tồn tại nhưng advice không chạy?

Khi advice annotation không chạy, phân loại nguyên nhân theo đường thực thi thay vì chỉ tìm lỗi pointcut:

| Dấu hiệu | Kiểm tra đầu tiên |
| --- | --- |
| `@Aspect` tồn tại nhưng chưa được Spring đăng ký | `<bean>` hoặc `@Component` kết hợp `<context:component-scan>` |
| Aspect bean tồn tại nhưng không có advisor | `<aop:aspectj-autoproxy/>`, namespace/schema, classpath `aspectjweaver` |
| Bean có proxy nhưng một method không có advice | `execution(...)` có match method/annotation thật không |
| Chỉ mất advice khi gọi nội bộ | `this.method()` bỏ qua Spring proxy |
| Target tạo thủ công không có advice | Đưa target vào context và inject reference proxy |
| Log xuất hiện hai lần | Có nhiều aspect beans/advisors cùng triển khai một concern không |

`<aop:aspectj-autoproxy/>` không tương đương với `<aop:aspect>` trong `<aop:config>`. Chỉ phối hợp khi thật sự dùng hai kiểu khai báo riêng với trách nhiệm không chồng lấn; bài **“Kết hợp XML với Java configuration mà không tạo hành vi trùng lặp”** phân tích cụ thể các nguồn duplicate.

## 6. Khi nào dùng, khi nào chuyển sang cấu hình Java?

Nếu dự án hiện có `applicationContext.xml` quản lý Spring bean, `<aop:aspectj-autoproxy/>` cho phép tiếp tục cấu hình ứng dụng bằng XML trong khi viết advice gọn bằng annotation Java.

Ở ứng dụng dùng Java configuration, cơ chế tương ứng là `@EnableAspectJAutoProxy` (trong ứng dụng Spring Boot, auto-configuration liên quan có thể đã kích hoạt Spring AOP tùy dependencies/config). Việc chọn XML hay Java config thay đổi **cách đăng ký hạ tầng proxy**; nguyên tắc Spring bean, pointcut matching và gọi qua proxy vẫn cần được tuân thủ.

**Kiểm tra nhanh trước khi bàn giao cấu hình:**

1. XML khai báo `xmlns:aop` và `spring-aop.xsd` đúng.
2. Có `<aop:aspectj-autoproxy/>` trong application context phù hợp.
3. Class aspect có `@Aspect` và các advice annotation hợp lệ; aspect thực sự được đăng ký Spring bean.
4. Target cũng là Spring bean, pointcut khớp method muốn intercept.
5. Mã sử dụng bean từ context và gọi **qua proxy**; kiểu injection phù hợp loại proxy.
6. Dependency Spring AOP/AspectJ đầy đủ; phép thử `AopUtils.isAopProxy(...)` cùng output advice xác nhận cơ chế hoạt động.

**Ghi nhớ:** `<aop:aspectj-autoproxy/>` là công tắc **Spring XML để kích hoạt AOP proxy cho `@Aspect` beans**. Nó không thay thế việc đăng ký bean và không biến mọi lời gọi Java thành join point được intercept; cả XML, bean và đường đi của lời gọi phải đúng thì advice mới chạy.
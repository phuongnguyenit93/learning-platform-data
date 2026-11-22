# Lọc ở cấp lớp và ở cấp phương thức bằng Spring Pointcut API

## 1. Mục tiêu của bài học

Trong Spring AOP, không phải mọi lời gọi trên một bean đều cần chạy advice. Ví dụ: chỉ ghi nhận thao tác `charge(String)` của nhóm service thanh toán, không ghi nhận `status()` trên cùng service và cũng không ghi nhận một method tên `charge` thuộc service vận chuyển.

**Spring Pointcut API** giải quyết yêu cầu đó bằng hai bộ lọc độc lập:

1. `ClassFilter`: xác định **lớp target nào** thuộc phạm vi pointcut.
2. `MethodMatcher`: xác định **phương thức nào trên lớp target đó** thuộc phạm vi pointcut.

Hai bộ lọc hợp thành một `org.springframework.aop.Pointcut`. Advice được áp dụng cho method execution qua Spring proxy khi **điều kiện cấp lớp và điều kiện cấp phương thức cùng thỏa**; nếu matcher động, còn phải kiểm tra giá trị argument tại mỗi lần gọi.

Sau bài này, bạn có thể đọc các interface Java của Spring Pointcut API, triển khai pointcut tĩnh cho cả lớp và phương thức, kết nối pointcut với advice thông qua advisor, phân biệt matcher tĩnh/động và kiểm tra những trường hợp tưởng đã khớp nhưng advice không chạy.

Phạm vi tập trung vào **Spring AOP proxy và Pointcut API**. Không đi sâu vào lý thuyết aspect nói chung hoặc AspectJ weaving.

## 2. Ghép hai cấp lọc để mô tả đúng nghiệp vụ

Một `org.springframework.aop.Pointcut` gồm `getClassFilter()` (chọn lớp đích) và `getMethodMatcher()` (chọn phương thức trên lớp ấy). Hai giao diện tương ứng có các phép kiểm tra `ClassFilter.matches(Class<?>)` và `MethodMatcher.matches(Method, Class<?>)`. Chỉ khi bộ lọc tĩnh khớp, và matcher báo `isRuntime() == true`, Spring mới cần kiểm tra thêm `matches(Method, Class<?>, Object... args)` cho lần gọi thực tế. Đây là cấu trúc matching của Spring Pointcut API, không phải lời gọi trực tiếp tới target.

Áp dụng vào ví dụ thanh toán của bài:

| Target class | Method | ClassFilter chỉ chọn BillingService | MethodMatcher chọn charge(String) | Advice? |
| --- | --- | --- | --- | --- |
| `BillingService` | `charge(String)` | Có | Có | Có, khi caller qua proxy |
| `BillingService` | `status()` | Có | Không | Không |
| `ShippingService` | `charge(String)` | Không | Có về chữ ký | Không, bị loại từ lớp |

Công thức kiểm tra là `classMatch && staticMethodMatch && (!isRuntime || runtimeArgsMatch)`. Kết quả tĩnh có thể được Spring lưu lại; kết quả động chỉ phụ thuộc một lần invocation. Nếu một advisor không khớp, method nghiệp vụ vẫn tiếp tục như bình thường trừ khi một interceptor khác thay đổi luồng. Các phần tiếp theo cài đặt từng cấp lọc và kiểm chứng đúng ba dòng của bảng trên bằng `ProxyFactory`.

## 3. Lọc ở cấp lớp: `ClassFilter`

Phương thức `matches(Class<?> clazz)` nhận **kiểu target** mà Spring đang xem xét. Nó trả về `true` nếu target class thuộc tập lớp cần advice.

Ví dụ chỉ nhận `BillingService` và các subclass của nó:

~~~java
ClassFilter billingOnly =
        clazz -> BillingService.class.isAssignableFrom(clazz);
~~~

Đoạn này giả định class `BillingService` đã được khai báo. Ý nghĩa của `isAssignableFrom` là target có thể dùng như `BillingService`, do đó chấp nhận chính lớp và lớp con. So sánh `clazz == BillingService.class` chỉ khớp đúng một class; cân nhắc rõ chính sách của ứng dụng.

Ví dụ khác, chọn qua marker interface:

~~~java
ClassFilter auditedServices =
        clazz -> AuditedOperations.class.isAssignableFrom(clazz);
~~~

Giả định interface `AuditedOperations` do ứng dụng định nghĩa. Đây thường là lựa chọn tốt khi các implementation khác nhau cùng thuộc một nghiệp vụ, vì không cần buộc tất cả kế thừa một superclass.

**Lưu ý quan trọng:** Class filter không dùng để kiểm tra tên method, giá trị tham số hoặc giá trị return. Một khi lớp thỏa `ClassFilter`, `MethodMatcher` sẽ xử lý việc chọn method cụ thể. Đừng dùng package-name string một cách vô ý: package chứa class do Spring tạo proxy, các subclass và lớp triển khai có thể dẫn tới giả định sai. Hãy xem xét **target class**, thay vì tự suy từ tên lớp proxy quan sát được ở caller.

### ClassFilter mặc định

Một số pointcut tiện ích cho phép đặt `ClassFilter` riêng; khi không giới hạn, filter mặc định có thể là `ClassFilter.TRUE` (khớp mọi target class). Điều đó không đồng nghĩa mọi method đều khớp, vì `MethodMatcher` vẫn có quyền từ chối.

## 4. Lọc ở cấp phương thức: `MethodMatcher`

### 4.1. Lọc tĩnh bằng chữ ký method

`matches(Method method, Class<?> targetClass)` có đủ thông tin để xét:

- Tên method: `method.getName()`.
- Kiểu và số parameter: `method.getParameterTypes()`, `method.getParameterCount()`.
- Kiểu trả về: `method.getReturnType()`.
- Modifier: `Modifier.isPublic(method.getModifiers())`, v.v.
- Annotation/metadata mà implementation chủ động tra cứu trên method và target class.

Ví dụ yêu cầu method đúng tên `charge`, có một argument `String`:

~~~java
@Override
public boolean matches(Method method, Class<?> targetClass) {
    return method.getName().equals("charge")
            && method.getParameterCount() == 1
            && method.getParameterTypes()[0] == String.class;
}
~~~

Đây là phần thân khi override `StaticMethodMatcherPointcut.matches`, chưa phải tệp độc lập. Kiểu `Method` trong method matching không luôn đồng nhất với cách caller nhìn phương thức qua interface; nếu cần annotation implementation hoặc xử lý bridge/generic, có thể tra most-specific method qua `AopUtils.getMostSpecificMethod(...)`.

### 4.2. Tĩnh nghĩa là không phụ thuộc giá trị arguments

Method `charge("NORMAL-1")` và `charge("VIP-1")` có **cùng tên và chữ ký**, nên matcher tĩnh ở trên không phân biệt chúng. Lợi thế là Spring có thể cache kết quả matching thay vì tính lại ở từng lần gọi.

Với `StaticMethodMatcherPointcut`, `isRuntime()` là `false`. Spring sẽ không yêu cầu `matches(method, targetClass, args)` cho mỗi invocation. Đây là lựa chọn mặc định khi tiêu chí lọc chỉ dựa vào class và metadata method.

### 4.3. Động nghĩa là phải xem arguments tại thời điểm gọi

Nếu chỉ muốn advice cho `charge` khi mã bắt đầu bằng `VIP-`, phải thêm bước kiểm tra `args` tại runtime. Spring cung cấp `DynamicMethodMatcherPointcut`; với nó, `isRuntime()` là `true`.

~~~java
// Ví dụ một lớp pointcut riêng; cần import các kiểu Spring/Java tương ứng.
class VipChargePointcut extends DynamicMethodMatcherPointcut {

    @Override
    public ClassFilter getClassFilter() {
        return clazz -> BillingService.class.isAssignableFrom(clazz);
    }

    @Override
    public boolean matches(Method method, Class<?> targetClass) {
        return method.getName().equals("charge")
                && method.getParameterCount() == 1
                && method.getParameterTypes()[0] == String.class;
    }

    @Override
    public boolean matches(Method method, Class<?> targetClass, Object... args) {
        return args.length == 1
                && args[0] instanceof String id
                && id.startsWith("VIP-");
    }
}
~~~

Lớp trên là **biến thể minh họa** đặt cạnh ví dụ đầy đủ ở mục 5. Khi dùng phải import `org.springframework.aop.ClassFilter`, `org.springframework.aop.support.DynamicMethodMatcherPointcut` và `java.lang.reflect.Method`, đồng thời có `BillingService`.

Điểm quan trọng: Spring chỉ gọi dynamic matcher sau khi kết quả matching ở cấp class và chữ ký method cho phép. Runtime matcher có overhead trên mỗi lời gọi phù hợp với điều kiện tĩnh. Chỉ dùng khi giá trị đối số thực sự là một phần chính sách chọn advice.

## 5. Ví dụ chạy được: kết hợp hai cấp lọc bằng `ProxyFactory`

Ví dụ dùng **Java 17** và **Spring Framework 6.1.x** (qua Spring Boot 3.3.0 dependency management) để chạy Spring AOP theo dạng chương trình thuần Java. Nó không cần server HTTP, không cần annotation `@Aspect` và không cần Spring Boot startup. Chúng ta tạo proxy trực tiếp qua `ProxyFactory` để thấy rõ quan hệ giữa Pointcut, Advisor và Advice.

### 5.1. Cấu trúc

~~~text
pom.xml
src/main/java/com/example/pointcut/Demo.java
~~~

### 5.2. Maven dependencies

Tệp `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>spring-pointcut-filters</artifactId>
    <version>1.0.0</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot parent ở đây dùng để quản lý phiên bản dependency; không có `@SpringBootApplication`. `spring-boot-starter-aop` đưa Spring AOP và các thư viện liên quan vào classpath. Cơ chế proxy do `ProxyFactory` tạo trực tiếp.

### 5.3. Mã Java hoàn chỉnh

Tệp `src/main/java/com/example/pointcut/Demo.java`:

~~~java
package com.example.pointcut;

import java.lang.reflect.Method;

import org.springframework.aop.MethodBeforeAdvice;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.DefaultPointcutAdvisor;
import org.springframework.aop.support.StaticMethodMatcherPointcut;

public class Demo {

    public static class BillingService {
        public String charge(String code) {
            System.out.println("target:billing-charge:" + code);
            return "charged:" + code;
        }

        public String status() {
            System.out.println("target:billing-status");
            return "ready";
        }
    }

    public static class ShippingService {
        public String charge(String code) {
            System.out.println("target:shipping-charge:" + code);
            return "shipped:" + code;
        }
    }

    // Pointcut có cả ClassFilter và MethodMatcher.
    public static class BillingChargePointcut
            extends StaticMethodMatcherPointcut {

        public BillingChargePointcut() {
            setClassFilter(clazz ->
                    BillingService.class.isAssignableFrom(clazz));
        }

        @Override
        public boolean matches(Method method, Class<?> targetClass) {
            return method.getName().equals("charge")
                    && method.getParameterCount() == 1
                    && method.getParameterTypes()[0] == String.class;
        }
    }

    public static void main(String[] args) {
        var pointcut = new BillingChargePointcut();

        MethodBeforeAdvice advice = (method, arguments, target) -> {
            System.out.println(
                    "advice:" + target.getClass().getSimpleName()
                    + "." + method.getName()
                    + "(" + arguments[0] + ")");
        };

        var advisor = new DefaultPointcutAdvisor(pointcut, advice);

        ProxyFactory billingFactory = new ProxyFactory(new BillingService());
        billingFactory.setProxyTargetClass(true);
        billingFactory.addAdvisor(advisor);
        BillingService billing =
                (BillingService) billingFactory.getProxy();

        ProxyFactory shippingFactory = new ProxyFactory(new ShippingService());
        shippingFactory.setProxyTargetClass(true);
        shippingFactory.addAdvisor(advisor);
        ShippingService shipping =
                (ShippingService) shippingFactory.getProxy();

        System.out.println("== Billing charge ==");
        System.out.println("result=" + billing.charge("B-1"));

        System.out.println("== Billing status ==");
        System.out.println("result=" + billing.status());

        System.out.println("== Shipping charge ==");
        System.out.println("result=" + shipping.charge("S-1"));
    }
}
~~~

Trong mã này:

1. `BillingChargePointcut` kế thừa `StaticMethodMatcherPointcut`. Đây là tiện ích Spring vừa đóng vai `Pointcut`, vừa thực hiện phần `MethodMatcher`, nên ta chỉ override phương thức `matches(Method, Class)`.
2. Constructor gọi `setClassFilter` để chọn target thuộc `BillingService`. `ShippingService` bị loại từ bước lọc lớp, dù có method `charge(String)` trùng chữ ký.
3. `matches` chỉ chọn `charge(String)`. Method `status()` của `BillingService` vượt qua bộ lọc class nhưng bị loại ở bộ lọc method.
4. `DefaultPointcutAdvisor(pointcut, advice)` ghép **điều kiện chọn** với **hành vi thực thi**. Đây là sự nối kết cốt lõi của low-level Spring AOP API.
5. `MethodBeforeAdvice` dùng để in log trước khi target method chạy. Nó không tự chọn method; advisor mới xác định nơi áp dụng.
6. Mỗi `ProxyFactory` nhận một target thực, thêm cùng advisor rồi tạo class-based proxy. `setProxyTargetClass(true)` giúp nhận proxy về bằng đúng concrete service type trong demo.

Các method của service là `public`, không `final`, và class có thể được subclass. Đây là điều kiện thuận tiện cho class-based proxy.

### 5.4. Chạy

Từ thư mục có `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.pointcut.Demo
~~~

Không tính log của Maven hoặc môi trường, output do chương trình phát ra là:

~~~text
== Billing charge ==
advice:BillingService.charge(B-1)
target:billing-charge:B-1
result=charged:B-1
== Billing status ==
target:billing-status
result=ready
== Shipping charge ==
target:shipping-charge:S-1
result=shipped:S-1
~~~

**Vì sao chỉ có một dòng `advice:`?**

| Lời gọi | ClassFilter | MethodMatcher | Advice? |
| --- | --- | --- | --- |
| `billing.charge("B-1")` | PASS: `BillingService` | PASS: `charge(String)` | Có |
| `billing.status()` | PASS: `BillingService` | FAIL: tên `status` | Không |
| `shipping.charge("S-1")` | FAIL: `ShippingService` | Cấp method không cần được chọn | Không |

Cả ba lời gọi vẫn chạy phần nghiệp vụ. Pointcut quyết định **advice áp dụng ở đâu**, không phải là bộ chặn quyền truy cập method. Nếu cần cấm thực thi trong trường hợp nào đó thì phải có advice và chính sách bảo vệ được thiết kế rõ ràng.

## 6. Tự kiểm tra từng bộ lọc trước khi tạo proxy

Một ưu điểm của Pointcut API là bạn có thể kiểm tra kết quả matching bằng Java mà không cần chạy toàn bộ hệ thống. Với `pointcut` đã tạo ở mục 5:

~~~java
boolean billingClass =
        pointcut.getClassFilter().matches(BillingService.class);

boolean shippingClass =
        pointcut.getClassFilter().matches(ShippingService.class);

Method charge =
        BillingService.class.getMethod("charge", String.class);
Method status =
        BillingService.class.getMethod("status");

boolean chargeMethod =
        pointcut.getMethodMatcher().matches(charge, BillingService.class);
boolean statusMethod =
        pointcut.getMethodMatcher().matches(status, BillingService.class);

System.out.println(billingClass);
System.out.println(shippingClass);
System.out.println(chargeMethod);
System.out.println(statusMethod);
~~~

Đây là **đoạn kiểm tra bổ sung** để đặt trong `main`; giả định có biến `pointcut` cùng các nested service classes đã định nghĩa, và `main` cần khai báo `throws NoSuchMethodException` hoặc xử lý ngoại lệ từ `getMethod`. Khi chèn đúng vào ví dụ, bốn dòng tương ứng là:

~~~text
true
false
true
false
~~~

Chú ý: gọi trực tiếp `MethodMatcher.matches` trên một method của class không khớp `ClassFilter` có thể vẫn trả `true`, vì method matcher riêng không nhất thiết kiểm tra class filter. Để dự đoán advisor có áp dụng, phải kiểm tra **cả hai điều kiện**, không chỉ hỏi riêng method matcher.

### Vì sao không dùng `getClass()` của proxy?

Trong ví dụ, `billing.getClass()` là một subclass proxy do Spring tạo, không phải `BillingService.class` thuần. API `ClassFilter` được thiết kế cho **target class** mà Spring đánh giá; trong kiểm thử trực tiếp, dùng class target đã biết. Với một bean có sẵn trong Spring context, có thể dùng `AopUtils.getTargetClass(bean)` để tra target class theo cơ chế của Spring. Không nên viết class filter dựa vào tên lớp proxy sinh động như `BillingService$$SpringCGLIB$$...`.

## 7. Cách chọn kiểu triển khai Pointcut API

Spring có những lớp hỗ trợ để tránh phải tự triển khai cả `Pointcut` và `MethodMatcher`:

| Nhu cầu | Kiểu Spring phù hợp | Đặc điểm |
| --- | --- | --- |
| Chọn theo class + metadata method | `StaticMethodMatcherPointcut` | `setClassFilter` và override `matches(Method, Class)`; `isRuntime=false` |
| Chọn method theo tên hoặc pattern tên đơn giản | `NameMatchMethodPointcut` | Matcher tĩnh theo tên method; có thể bổ sung class filter |
| Chọn method theo regular expression | `JdkRegexpMethodPointcut` | Matcher tĩnh theo biểu thức chính quy; hạn chế bằng target class khi cần |
| Chọn theo AspectJ expression | `AspectJExpressionPointcut` | Dùng expression trong Spring AOP proxy, ví dụ `execution(...)`, `within(...)` |
| Cần xem argument của mỗi lần gọi | `DynamicMethodMatcherPointcut` | Thêm `matches(method, targetClass, args)` ở runtime |
| Kết hợp nhiều pointcut | `ComposablePointcut` hoặc `Pointcuts` | Hợp/ giao các điều kiện đã có |

Một ví dụ ngắn khi chỉ muốn chọn method tên `charge`:

~~~java
var nameMatch = new NameMatchMethodPointcut();
nameMatch.setMappedName("charge");
nameMatch.setClassFilter(clazz ->
        BillingService.class.isAssignableFrom(clazz));
~~~

Đoạn trên cần import `org.springframework.aop.support.NameMatchMethodPointcut`. `NameMatchMethodPointcut` cung cấp matcher theo tên, có thể cấu hình tên/pattern đơn giản, nên không cần viết `MethodMatcher` thủ công cho trường hợp này. Nhưng nếu cần phân biệt overload `charge(String)` và `charge(BigDecimal)`, matcher theo tên đơn thuần không đủ; phải bổ sung điều kiện chữ ký.

### Cách ghép điều kiện AND/OR

Giả sử có hai pointcut `P1` và `P2`:

- **Intersection**: cả `P1` và `P2` phải match.
- **Union**: ít nhất một trong `P1` hoặc `P2` match.

Các tiện ích `org.springframework.aop.support.Pointcuts` và `ComposablePointcut` hỗ trợ kết hợp. Tránh nhầm **intersection của hai pointcut** với việc chỉ viết thêm điều kiện method vào một pointcut mà bỏ mất class filter. Khi kết hợp các advisor khác nhau, nhiều advice có thể cùng chạy nếu mỗi advisor đều match.

Trong đa số Spring application, có thể diễn đạt phạm vi bằng `AspectJExpressionPointcut` hoặc `@Pointcut` rõ ràng hơn. Pointcut API hữu ích khi **điều kiện lọc được xây dựng bằng Java, cần tái sử dụng hoặc cần tích hợp advisor tùy chỉnh**.

## 8. Lớp và method matching trong Spring application có DI

Ví dụ `ProxyFactory` tạo proxy trực tiếp để làm rõ cơ chế. Trong ứng dụng Spring Boot/Spring Framework thực tế, bean có thể được proxy tự động nhờ advisor và auto-proxy creator. Khi dùng Spring DI:

- Pointcut/advisor phải được đăng ký và gắn vào quá trình tạo proxy theo cấu hình Spring AOP của ứng dụng.
- Caller phải lấy **Spring-managed proxy**, không tự `new` target rồi chờ advice chạy.
- Với JDK dynamic proxy, caller thường truy cập public method từ interface được proxy. Với class-based proxy, lớp/method `final` và method `private` không được intercept tương tự ví dụ public method.
- Self-invocation `this.charge(...)` bên trong target không đi qua proxy, nên class/method có thỏa bộ lọc vẫn không làm lời gọi nội bộ kích hoạt advice.

**Đủ điều kiện matching không có nghĩa chắc chắn được chặn:** kết quả `ClassFilter=true` và `MethodMatcher=true` mới chứng minh method thuộc phạm vi pointcut; còn phải có advisor trên proxy và lời gọi thực sự đi qua proxy đó.

### Cấu hình theo annotation và biểu thức có liên quan ra sao?

Trong Spring AOP, expression `execution(* com.example.billing..*(..))` có thể làm nhiệm vụ gần giống lọc class/package + lọc method bằng chữ ký; `within(com.example.billing..*)` thiên về kiểu khai báo. Nhưng pointcut expression cần được Spring dịch sang matcher, và không phải mọi AspectJ join point đều được Spring proxy AOP hỗ trợ. Bài này nhấn mạnh **API Java lõi** `Pointcut`, `ClassFilter`, `MethodMatcher` thay vì thay thế cơ chế XML hoặc `@Aspect` bằng cách diễn giải tùy tiện.

## 9. Lỗi phổ biến

### 9.1. Class filter dùng so sánh chính xác trong khi có subclass

~~~java
clazz -> clazz == BillingService.class
~~~

Điều kiện này không khớp một subclass của `BillingService` khi chính subclass ấy là target class. Nếu muốn chấp nhận subclass, dùng `BillingService.class.isAssignableFrom(clazz)`. Nếu chính sách bảo mật hoặc nghiệp vụ chỉ cho đúng một loại, so sánh chính xác vẫn có thể hợp lệ; quyết định dựa vào phạm vi muốn chọn.

### 9.2. Method filter chỉ so tên, vô tình chọn nhiều overload

~~~java
method.getName().equals("charge")
~~~

Nó có thể match `charge(String)`, `charge(int)`, `charge(BigDecimal)` nếu tất cả được proxy intercept. Khi cần đúng signature, so `getParameterTypes()`, `getReturnType()` hoặc các thuộc tính phù hợp.

### 9.3. Nhầm method matcher với phép kiểm tra mọi lời gọi

Một matcher tĩnh không xem được `args[0] == "VIP-1"` ở từng invocation. `isRuntime=false` có nghĩa Spring không gọi biến thể `matches(..., args)`. Để chọn theo argument value, dùng dynamic matcher hoặc advice điều kiện, đồng thời tính tới overhead.

### 9.4. Kiểm tra annotation sai method

Method có thể được nhìn từ interface khi dùng JDK proxy. Annotation đặt trên implementation method không nhất thiết được tìm thấy khi chỉ gọi `method.getAnnotation(...)` trên method của interface. Nếu bài toán cần annotation ở implementation, dùng `AopUtils.getMostSpecificMethod(method, targetClass)` và xác định chính sách metadata. Không giả định Java kế thừa annotation method từ interface.

### 9.5. Proxy, self-invocation và final method

Nếu method không có advice dù đã thấy matcher trả `true`, hãy kiểm tra caller có giữ proxy hay target gốc, class/method có bị `final`, và lời gọi có đi từ bean khác qua proxy không. Không cố giải quyết vấn đề self-invocation bằng việc nới `ClassFilter`, vì bộ lọc không tạo thêm một lượt đi qua proxy.

### 9.6. Làm matcher chậm hoặc có tác dụng phụ

Matcher tĩnh nên dựa vào metadata ổn định. Không truy vấn database, gọi HTTP hoặc sửa state ở `matches`. Spring có thể gọi matcher trong quá trình dựng proxy và caching, nên điều kiện phụ thuộc state thay đổi theo từng lời gọi sẽ không an toàn khi đặt ở matcher tĩnh. Matcher động cần gọn nhẹ vì chạy nhiều lần; nếu cần quan sát dữ liệu nghiệp vụ phức tạp, cân nhắc thiết kế khác.

### 9.7. Quá rộng ở class level, quá hẹp ở method level

Ví dụ `ClassFilter.TRUE` kết hợp `MethodMatcher` chỉ chọn tên `charge` có thể áp dụng advice trên mọi bean có tên method đó, bao gồm service không liên quan. Ngược lại, giới hạn đúng một class khi ứng dụng dùng nhiều implementation của interface có thể làm mất các bean cần advice. Hãy coi class filter là ranh giới nghiệp vụ/kiến trúc và method matcher là lựa chọn operation.

## 10. Checklist kiểm thử

Đối với một custom pointcut trong Spring:

1. **Class scope:** test class cần chọn và class cần loại; nếu có inheritance, test cả subclass hoặc interface implementation.
2. **Method scope:** test method cần chọn, method khác tên, overload khác chữ ký và method không thể proxy intercept.
3. **Static/dynamic:** xác nhận `isRuntime()` đúng với mục đích; nếu dynamic, thử nhiều argument values; tránh dùng matcher tĩnh cho yêu cầu thay đổi theo lần gọi.
4. **Proxy:** gọi qua Spring proxy và xác nhận advice chạy đúng số lần; kiểm tra cả trường hợp self-invocation bị bỏ qua.
5. **Advisor:** bảo đảm pointcut được ghép với advice trên proxy thực tế; một class/method match đơn lẻ chưa đủ.
6. **Behavior:** method bị loại khỏi advice vẫn thực thi đúng nghiệp vụ; method được chọn vẫn trả kết quả/ném exception theo contract của advice tương ứng.
7. **Chi phí:** giữ filter rẻ, ổn định và giới hạn phạm vi hợp lý khi ứng dụng có nhiều bean hoặc tần suất gọi cao.

## 11. Ghi nhớ

**Spring `Pointcut` tách quyết định áp dụng advice thành `ClassFilter` và `MethodMatcher`.** Class filter xác định đối tượng target nào có thể được chặn; method matcher xác định operation nào phù hợp. Với static matcher, quyết định dựa vào class/method metadata và có thể được cache. Với dynamic matcher, Spring còn xét argument values khi gọi. Dù hai bộ lọc đều khớp, advice chỉ chạy nếu advisor được lắp vào Spring proxy và caller đi qua proxy.

Tài liệu chính thức:

- [Spring Framework Reference — Pointcut API in Spring](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html)
- [Spring Framework Reference — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework API — Pointcut](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/aop/Pointcut.html)
- [Spring Framework API — MethodMatcher](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/aop/MethodMatcher.html)

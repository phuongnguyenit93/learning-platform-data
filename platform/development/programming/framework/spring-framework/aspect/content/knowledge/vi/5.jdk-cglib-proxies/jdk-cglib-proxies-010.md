# Hạn chế của Spring AOP với Java Module System và quyền truy cập lớp (JDK Proxy & CGLIB)

## 1. Bối cảnh: vì sao cùng một aspect chạy trên classpath nhưng lỗi trên module path?

Spring AOP chặn lời gọi phương thức thông qua **proxy**. Một Spring bean có thể được bao bởi:

- **JDK dynamic proxy**: một đối tượng triển khai các interface của target. Client gọi phương thức thông qua interface.
- **Class-based proxy (CGLIB)**: Spring tạo một subclass ở runtime để override những phương thức có thể chặn được.

Khi đưa ứng dụng Java 9+ lên **Java Platform Module System (JPMS)** bằng `module-info.java` và `--module-path`, Java kiểm soát thêm **module nào đọc module nào**, **package nào được truy cập công khai**, **package nào được truy cập sâu qua reflection** và **runtime có quyền định nghĩa lớp proxy ở đâu**. Vì vậy, lỗi AOP có thể chỉ xuất hiện khi triển khai theo named module, dù cùng source chạy được trên classpath.

Trong Spring, câu hỏi đúng là:

1. Spring đang dùng JDK proxy hay CGLIB?
2. Bean, interface, lớp cấu hình và aspect thuộc package/module nào?
3. Target class/method có thể truy cập hoặc override không?
4. Các package cần thiết đã `exports` hoặc `opens` đúng **module tiêu thụ** chưa?
5. Runtime đã cấp phép tạo class động ở classloader/module phù hợp chưa?
6. Lời gọi có đi qua Spring AOP proxy không?

**Phạm vi bài:** Spring Framework `@AspectJ` theo proxy, hệ quả JPMS và quyền truy cập của target/advice. Đây không phải bài giới thiệu JPMS tổng quát hoặc AspectJ bytecode weaving độc lập.

## 2. Phân biệt bốn loại rào cản

| Loại rào cản | Ví dụ | Liên hệ Spring AOP |
| --- | --- | --- |
| **Java language / class visibility** | Class không `public`; method `private`; method `final`; package-private method không được subclass ở package khác nhìn thấy | Dù module đã `opens`, CGLIB vẫn không override `final` hoặc `private`; JDK proxy chỉ cung cấp method qua interface của proxy. |
| **JPMS readability / exports** | Module A không `requires` module B; package chứa public API chưa được `exports` | Code ở module khác có thể không compile hoặc không truy cập trực tiếp interface/public class; JDK proxy không tự xóa các giới hạn ở API phía client. |
| **JPMS deep reflection / opens** | Spring cần phản chiếu gọi constructor hoặc method không public trong package đóng | Có thể gặp `InaccessibleObjectException` hoặc lỗi truy cập liên quan; cần mở đúng package cho module thực sự dùng reflection. |
| **Runtime-generated class / ClassLoader** | CGLIB cần định nghĩa một subclass động trong môi trường module chặt | Có thể không tạo được proxy, dù method là public; `--add-opens` không chữa được mọi giới hạn classloader hoặc module membership. |

Một điểm thường bị bỏ qua: **`exports` và `opens` giải quyết hai quyền khác nhau**. Cả hai cũng **không biến** method `private`, `final` thành method mà CGLIB có thể override.

## 3. Spring quyết định JDK hay CGLIB như thế nào?

Trong cấu hình Spring AOP thông thường, nếu target triển khai interface phù hợp thì Spring có thể dùng JDK dynamic proxy; nếu không có interface hoặc cấu hình buộc proxy theo lớp, Spring dùng CGLIB.

### 3.1. Cấu hình trên Spring Framework

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
class JdkProxyConfiguration {
    // Ưu tiên JDK proxy khi target có interface phù hợp.
}
```

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
class ClassProxyConfiguration {
    // Buộc proxy theo lớp khi bean cần Spring AOP proxy.
}
```

Đây là **hai đoạn minh họa độc lập**; không đăng ký cả hai vào một context chỉ để thử hai chế độ. Khi nhiều cấu hình Spring trong cùng context yêu cầu proxy, một `proxyTargetClass=true` ở cơ chế khác như transaction hoặc caching có thể chi phối lựa chọn thực tế.

### 3.2. Spring Boot có thể khác cấu hình Spring Framework thuần

Với Spring Boot 3.3 có AOP auto-configuration phù hợp (thường qua `spring-boot-starter-aop`), class-based proxy thường là mặc định. Có thể đổi định hướng bằng:

```properties
spring.aop.proxy-target-class=false
```

Thuộc tính này không phủ quyết mọi cấu hình tường minh khác trong context. Cần kiểm tra **runtime proxy thực tế**, không đoán chỉ từ một property.

### 3.3. Kiểm tra bằng API của Spring

```java
Object bean = context.getBean("gateway");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

Đoạn trên là **snippet chẩn đoán**: giả sử biến `context` tồn tại và bean tên `gateway` đã đăng ký. `AopUtils` thuộc `org.springframework.aop.support`. Nếu không có advisor khớp hoặc bean không qua Spring, có thể không tạo AOP proxy dù `@EnableAspectJAutoProxy` đã bật.

## 4. JDK dynamic proxy dưới JPMS: điều gì được phép, điều gì không?

### 4.1. JDK proxy dựa vào interface, không cần subclass target

Giả sử:

```java
package demo.orders.api;

public interface OrderGateway {
    String submit(String id);
}
```

```java
package demo.orders.internal;

public final class DefaultOrderGateway
        implements demo.orders.api.OrderGateway {

    @Override
    public String submit(String id) {
        return "stored:" + id;
    }
}
```

Nếu client được tiêm **`OrderGateway`**, một JDK proxy có thể triển khai interface đó dù target class là `final`. CGLIB sẽ không thể tạo subclass của `DefaultOrderGateway` do lớp này `final`.

Tuy nhiên, JDK proxy chỉ trình bày những interface mà proxy triển khai:
- Client không thể cast một JDK proxy thành `DefaultOrderGateway`.
- Phương thức chỉ có trên class và **không được khai báo trên interface proxy** không thể gọi thông qua interface đó.
- Các method được advice vẫn phải được gọi qua proxy; self-invocation từ target không được chặn.
- Interface và chữ ký method vẫn phải có khả năng truy cập hợp lệ trong bối cảnh module của client.

### 4.2. JPMS kiểm soát khả năng nhìn thấy interface từ module khác

Ví dụ mô hình module:

```java
// module-info.java của module cung cấp API
module demo.orders {
    exports demo.orders.api;

    // Những requires/opens khác phụ thuộc cấu trúc Spring thực tế.
}
```

`exports demo.orders.api` cho phép module khác có quan hệ đọc hợp lệ tham chiếu public type trong package API. Nó **không tự mở quyền deep reflection cho mọi lớp trong package internal**.

Nếu `OrderGateway` không được export cho module client, code client ở module khác có thể không dùng được interface như một API biên dịch thông thường. Do đó, đừng dựa vào “JDK proxy sẽ xuất hiện” để bỏ qua thiết kế module boundary.

### 4.3. Không đơn giản hóa quá mức quy tắc JDK proxy

Theo JDK 17, lớp proxy tạo bởi `java.lang.reflect.Proxy` có quy tắc chọn package/module tùy khả năng truy cập của các proxy interfaces. Đặc biệt:
- Public interface trong package được export/open có cách đặt proxy class phù hợp với khả năng truy cập đã công bố.
- Public interface trong package không export có thể dẫn đến proxy class thuộc **dynamic module với package không export**.
- Các interface không public có hạn chế nghiêm ngặt về package/module chung nếu cùng được proxy.
- Có proxy class **không đồng nghĩa** client có thể phản chiếu constructor hoặc truy cập mọi type chứa trong method signature.

Bởi vậy, khuyến nghị thực tế với Spring là **public business interface ở package được export cho module cần sử dụng**, inject theo interface và để Spring quản lý proxy. Không tự suy đoán tên module hoặc tên class proxy tạo ra ở runtime.

## 5. CGLIB và JPMS: subclass động cần những quyền gì?

### 5.1. CGLIB bị ràng buộc bởi khả năng kế thừa và override

Proxy theo lớp thường dựa trên subclass động của target class.

| Target hoặc method | JDK interface proxy | CGLIB class proxy |
| --- | --- | --- |
| Target class `final` nhưng có public interface | Có thể proxy qua interface | Không subclass được class `final` |
| Method `final` trong target | Interface method có thể được JDK proxy chặn | Không override được method `final` |
| Method `private` | Không nằm trên interface proxy để gọi | Không override được |
| Method package-private của superclass ở package khác | Không trực tiếp là interface API | Không nhìn thấy để override như method thường |
| Public non-final method | Nếu method được expose qua interface | Có thể override nếu class/proxy generation hợp lệ |
| Method chỉ được gọi bằng `this.otherMethod()` trong target | Bỏ qua proxy | Bỏ qua proxy |

Hai trường hợp cuối không liên quan JPMS: đó là giới hạn cơ bản của Spring AOP proxy. Việc thêm `opens` hoặc `--add-opens` **không khắc phục self-invocation hoặc non-overridable methods**.

### 5.2. Module path có thể cản định nghĩa subclass

Trong Java 9+, class được định nghĩa ở runtime phải tuân theo hệ thống module và classloader. Spring CGLIB có đường tạo subclass thường liên quan tới `MethodHandles.Lookup#defineClass` hoặc đường phản chiếu dự phòng, tùy môi trường. `Lookup#defineClass` chỉ được dùng trong những điều kiện package/loader thích hợp. Khi module hoặc classloader không cho phép định nghĩa lớp proxy ở vị trí cần thiết, proxy generation có thể thất bại.

Ví dụ được tài liệu Spring nêu rõ là **cố tạo CGLIB proxy cho lớp trong `java.lang` khi triển khai trên module path**. Đây không phải tình huống một service thông thường của ứng dụng; nó cho thấy có giới hạn thật của module system với subclass động.

Tài liệu Spring nói trường hợp fallback trên classpath có thể cần JVM option:

```text
--add-opens=java.base/java.lang=ALL-UNNAMED
```

**Không dùng option đó như công thức chữa mọi lỗi module path:**
- `ALL-UNNAMED` chỉ mở cho các **unnamed modules**, không mở cho mọi named module.
- Với module được đặt tên, tên đích mở quyền cần được xét cụ thể; ngay cả khi mở package đúng, giới hạn tạo class ở classloader/module không phù hợp vẫn có thể còn.
- Mở `java.base/java.lang` rộng chỉ để ép proxy một lớp JDK cốt lõi thường là dấu hiệu nên đổi thiết kế proxy. Đừng áp dụng `--add-opens=java.base/java.lang=ALL-UNNAMED` cho toàn ứng dụng nếu lỗi thực sự thuộc package của chính ứng dụng.

### 5.3. Lỗi có thể xuất hiện lúc khởi tạo Spring context

Nếu Spring đã thấy aspect advisor và cần class proxy cho bean nhưng không thể generate subclass, context có thể khởi tạo thất bại với lỗi liên quan `AopConfigException`, `CodeGenerationException`, `IllegalAccessException` hoặc `InaccessibleObjectException`; tên exception phụ thuộc call stack và phiên bản.

Không đọc **chỉ** dòng lỗi ngoài cùng. Hãy xem nested `Caused by` để xác định:
- Module nào chứa lớp bị từ chối truy cập?
- Package nào không được `opens` hoặc `exports`?
- Thành phần nào đang thử reflective access hoặc define class?
- Bean nào cần CGLIB proxy, vì sao Spring chọn class proxy?
- Có thể chuyển bean sang JDK proxy hay không?

## 6. `exports`, `opens`, `--add-exports`, `--add-opens`: chọn đúng công cụ

| Cú pháp | Quyền cấp | Ví dụ dùng trong bối cảnh Spring |
| --- | --- | --- |
| `exports p;` | Cho mọi module **đọc được** truy cập public type/public member thuộc package `p` bằng truy cập bình thường | Export business API interface cho module client |
| `exports p to m;` | Cho module `m` truy cập public API của package | Giới hạn API dành riêng cho một module |
| `opens p;` | Cho các module khác deep reflection tại runtime vào package `p` | Framework cần phản chiếu constructor/field/method trong app |
| `opens p to m;` | Cấp deep reflection có chọn lọc cho module `m` | Mở package cho module Spring thực sự cần truy cập |
| `--add-exports=A/p=B` | Thêm export cho run/compile phù hợp với cấu hình | Biện pháp tương thích khi không sửa được descriptor của module `A` |
| `--add-opens=A/p=B` | Thêm quyền deep reflection ở runtime | Khắc phục lỗi truy cập cụ thể khi quyền mở package còn thiếu |

**Nguyên tắc:** `exports` không đồng nghĩa `opens`. Quyền truy cập public API không tự cho Spring phép `setAccessible(true)` đối với non-public members. Ngược lại, `opens` mở quyền phản chiếu ở runtime nhưng không có vai trò thay thế API export cho việc biên dịch module client.

### 6.1. Ví dụ mô hình `module-info.java` cho ứng dụng có Spring AOP

Đoạn sau **minh họa thiết kế module**, không phải một project JPMS độc lập có thể dán nguyên vào ví dụ Gradle classpath ở phần 8. Tên package/module Spring và danh sách `requires` phải được điều chỉnh theo module thực tế, dependency và tính năng đang dùng.

```java
module demo.orders {
    requires spring.context;
    requires spring.beans;
    requires spring.aop;

    // Business interface được client module nhìn thấy.
    exports demo.orders.api;

    // Spring được phép phản chiếu vào vùng triển khai.
    // Chọn danh sách module đích bằng evidence từ stack trace
    // và phụ thuộc Spring thực tế.
    opens demo.orders.internal
        to spring.core, spring.beans, spring.context, spring.aop;
}
```

Ở đây:
- `exports demo.orders.api` đặt interface ở API boundary.
- `demo.orders.internal` không trở thành public API chỉ vì Spring có thể reflect vào nó.
- `opens ... to ...` là một **qualified opens**: chỉ liệt kê các module cần thiết thay vì mở cho toàn bộ thế giới.
- Cấu hình Spring có thể còn cần mở package chứa `@Configuration`, aspect hoặc những class được tạo/khởi tạo bằng reflection. Phải kiểm tra package thật, không mặc định chỉ cần mở `internal`.
- Phần khai báo module không thể đảm bảo proxy CGLIB được tạo thành công trong mọi classloader hoặc cho mọi target class; kiểm tra đặc điểm class và runtime.

### 6.2. Ví dụ JVM option khi một module đóng package của ứng dụng

Với ứng dụng named module `demo.orders`, nếu runtime báo Spring module `spring.core` thiếu quyền deep reflection vào `demo.orders.internal`, một lựa chọn tương đương với việc sửa module descriptor (khi đang kiểm tra) là:

```bash
java --add-opens=demo.orders/demo.orders.internal=spring.core \
     --module-path "<module-path-thuc-te>" \
     --module demo.orders/demo.orders.Main
```

Đây là **lệnh minh họa cấu trúc**, không phải lệnh chạy hoàn chỉnh: `<module-path-thuc-te>` phải được thay bằng module path thật và `demo.orders.Main` phải tồn tại trong ứng dụng. Không dùng lệnh này như kết quả đã test cho mọi Spring app. Nếu cần nhiều module Spring khác nhau có reflective access, phải xác minh từng module đích từ exception cụ thể.

Khi có quyền chỉnh source của ứng dụng, `module-info.java` là nơi mô tả quyền ổn định dễ review hơn so với thêm nhiều JVM flags không rõ mục đích.

## 7. Ví dụ Spring AOP chạy được để so sánh JDK proxy và CGLIB

Để kiểm tra **proxy type** trước khi đưa JPMS vào, ví dụ sau chạy theo **classpath**, dùng Java 17 và Spring Framework 6.1.14. Nó cố tình dùng hai context **tách biệt**: một context chỉ cho phép JDK proxy khi có interface và một context ép CGLIB. Không có `module-info.java` trong project này.

### 7.1. Cấu trúc file

```text
spring-aop-proxy-access/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/jpms/
    ├── Gateway.java
    ├── GatewayImpl.java
    ├── TraceAspect.java
    └── Demo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-proxy-access'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-aop:6.1.14'
    implementation 'org.aspectj:aspectjweaver:1.9.22.1'
}

application {
    mainClass = 'demo.jpms.Demo'
}
```

### 7.2. Interface cho JDK proxy

`src/main/java/demo/jpms/Gateway.java`:

```java
package demo.jpms;

public interface Gateway {
    String transfer(String id);
}
```

### 7.3. Target triển khai phương thức

`src/main/java/demo/jpms/GatewayImpl.java`:

```java
package demo.jpms;

public class GatewayImpl implements Gateway {

    @Override
    public String transfer(String id) {
        System.out.println("target:" + id);
        return "ok:" + id;
    }
}
```

Target không `final` và `transfer` là public non-final, nên có thể được proxy theo lớp hoặc interface. Điều này tách biệt được vấn đề **kiểu proxy** khỏi các lỗi do `final`.

### 7.4. Aspect làm dấu hiệu advice đã chạy qua proxy

`src/main/java/demo/jpms/TraceAspect.java`:

```java
package demo.jpms;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {

    @Before("execution(public * demo.jpms.GatewayImpl.transfer(..))")
    public void beforeTransfer(JoinPoint joinPoint) {
        System.out.println("aspect:" + joinPoint.getSignature().getName());
    }
}
```

`TraceAspect` là Spring `@Aspect`. Bài dùng pointcut khớp method của **target class**; Spring sẽ áp dụng advice cho lời gọi đi qua proxy. Aspect được đăng ký bằng `@Bean` ở `Demo`, không cần `@Component`.

### 7.5. Hai context với lựa chọn proxy khác nhau

`src/main/java/demo/jpms/Demo.java`:

```java
package demo.jpms;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

public class Demo {

    @Configuration(proxyBeanMethods = false)
    public static class CommonBeans {

        @Bean
        public Gateway gateway() {
            return new GatewayImpl();
        }

        @Bean
        public TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(CommonBeans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class JdkConfig {
    }

    @Configuration(proxyBeanMethods = false)
    @Import(CommonBeans.class)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    public static class CglibConfig {
    }

    public static void main(String[] args) {
        show("JDK", JdkConfig.class);
        show("CGLIB", CglibConfig.class);
    }

    private static void show(String label, Class<?> config) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(config)) {

            Gateway bean = context.getBean(Gateway.class);

            System.out.println(label + " jdk=" +
                    AopUtils.isJdkDynamicProxy(bean) +
                    " cglib=" + AopUtils.isCglibProxy(bean) +
                    " implementsClass=" + (bean instanceof GatewayImpl));

            String result = bean.transfer(label.toLowerCase());
            System.out.println(label + " result=" + result);
        }
    }
}
```

Hai `ApplicationContext` được tạo mới rồi đóng riêng, giúp cấu hình `proxyTargetClass=true` của case CGLIB không ảnh hưởng case JDK. `@Import(CommonBeans.class)` đăng ký bean cần thiết trong context đang xét; `@EnableAspectJAutoProxy` tạo hạ tầng AOP của từng context.

### 7.6. Chạy và đối chiếu stdout

Tại thư mục chứa `build.gradle`, dùng Gradle cài đặt sẵn:

```bash
gradle run
```

Nếu project đã có Gradle Wrapper thì dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows.

Các dòng **do Java code in ra**, không tính Gradle/logging của môi trường:

```text
JDK jdk=true cglib=false implementsClass=false
aspect:transfer
target:jdk
JDK result=ok:jdk
CGLIB jdk=false cglib=true implementsClass=true
aspect:transfer
target:cglib
CGLIB result=ok:cglib
```

Ý nghĩa:
- `implementsClass=false` cho JDK proxy: object là implementation của `Gateway`, nhưng **không là instance của `GatewayImpl`**. Trên module path, việc có public exported API interface thuận lợi cho cách sử dụng này.
- `implementsClass=true` cho CGLIB: proxy là subclass của `GatewayImpl`. Khi chuyển sang named modules, việc tạo subclass và quyền truy cập vào target class trở thành vấn đề cần kiểm tra.
- Hai case đều chạy `aspect:transfer`: khác proxy type **không làm mất advice**, miễn pointcut phù hợp và lời gọi đi qua proxy.
- Bài ví dụ classpath trên **chưa chứng minh cấu hình JPMS thật đã đủ `exports`/`opens`**; cần kiểm thử tiếp khi đóng gói vào named module.

## 8. Chuyển sang module path: checklist kiểm tra có hệ thống

Khi ứng dụng chạy ở classpath nhưng lỗi ở module path, tiến hành theo thứ tự để xác định nguyên nhân thực:

### Bước 1 — Xác định module và cách chạy

Kiểm tra có `module-info.java` và thực sự khởi chạy bằng `--module-path` / `--module` hay không. Đừng suy từ việc dùng JDK 17 rằng tất cả application classes đã thuộc named modules. Các ứng dụng chạy bằng classpath thông thường thuộc unnamed module và có ranh giới truy cập khác.

### Bước 2 — Xác định bean cần proxy và proxy type

Từ lỗi nested cause hoặc điểm startup thất bại, tìm bean Spring đang được advice. Nếu context khởi động được thì inspect:

```java
Object bean = context.getBean("gateway");
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

Nếu Spring đang tạo CGLIB proxy cho class mà bạn có thể expose qua interface, cân nhắc thiết kế interface và đặt `proxyTargetClass=false` **trong toàn bộ cấu hình liên quan**. Việc một Spring subsystem khác yêu cầu class-based proxy có thể ghi đè lựa chọn riêng ở `@EnableAspectJAutoProxy`.

### Bước 3 — Kiểm tra method/class trước khi sửa modules

Trước cả `--add-opens`, xem target có `final` class hoặc `final`/`private` method không. Với CGLIB, đây là giới hạn kế thừa Java và không thể đổi bằng JPMS flag. Với JDK proxy, bảo đảm method cần gọi được khai báo trên interface mà proxy triển khai.

### Bước 4 — Kiểm tra tính đọc được và exported API

Nếu lỗi compile-time hoặc `IllegalAccessError` cho public API, xem:
- Client module có `requires <api-module>` phù hợp không?
- Package chứa public interface/class có `exports` cho client không?
- Interface trong một package không export có vô tình được dùng làm API của service module khác không?

Đừng giải quyết nhu cầu public API bằng cách thêm `opens` rồi kỳ vọng Java compiler xem package đó như đã export.

### Bước 5 — Kiểm tra deep reflection

Nếu `InaccessibleObjectException` thông báo một module `does not "opens ..."`, đọc đủ tên **module nguồn, package, module đích**. Xem nơi Spring đang reflect:
- `@Configuration` và bean factory method;
- non-public constructor/field/method của Spring-managed bean;
- method/annotation mà Spring AOP hoặc cơ chế Spring khác phải introspect.

Thêm `opens package to moduleA, moduleB` vào module descriptor **khi có quyền chỉnh source** và phù hợp nhu cầu. Với môi trường không sửa được descriptor, dùng `--add-opens` có phạm vi hẹp để xác nhận giả thuyết trước.

### Bước 6 — Nếu vẫn không tạo được CGLIB class, xét ClassLoader

Khi lỗi liên quan `defineClass`, `MethodHandles.Lookup` hoặc package JDK core, kiểm tra target được nạp bởi classloader nào và lớp proxy cần được định nghĩa ở đâu. Trong JPMS chặt, **mở package chưa bảo đảm có quyền tạo lớp trong classloader không liên quan**. Spring Framework từng ghi nhận giới hạn này đối với một số kiểu JDK core; giải pháp thiết kế thường là tránh subclass chúng, chuyển proxy sang interface hoặc thay đổi boundary của Spring bean.

### Bước 7 — Kiểm tra lời gọi có thực sự đi qua proxy không

Sau khi startup thành công, nếu advice vẫn không chạy:
- Bean đã được Spring quản lý và `@Aspect` đã đăng ký thành bean?
- AOP auto-proxy được bật trong **đúng `ApplicationContext`**?
- Pointcut có khớp method của target?
- Client gọi từ ngoài qua proxy hay gọi `this.method()` trong target?
- Method có thực sự được JDK interface proxy expose hoặc CGLIB override?

**JPMS chỉ là một lớp rào cản.** Một lỗi Spring AOP xảy ra trên module path vẫn có thể do cấu hình pointcut hoặc self-invocation bình thường.

## 9. So sánh hướng xử lý theo từng tình huống

| Tình huống | Giải pháp nên xem trước | Điều không nên làm |
| --- | --- | --- |
| Chỉ cần advice trên các method công khai trong interface | Giữ interface public, export package API và thử JDK proxy | Ép CGLIB cho một `final` implementation không thể kế thừa |
| Bean không có interface và cần CGLIB | Bảo đảm class không `final`, method override được, và quyền module/runtime cho phép tạo subclass | Dùng `--add-opens` như cách mở khóa `final` |
| Spring báo không reflect được non-public constructor/method | Mở đúng package cho module Spring cần thiết bằng `opens`/`--add-opens` | Export mọi package nội bộ hoặc mở rộng `ALL-UNNAMED` tùy tiện |
| Compile module client không tham chiếu được interface | Thiết kế `exports` API và `requires` đúng | Chỉ `opens` mà không export API |
| JDK proxy không cast được sang implementation class | Inject/lookup theo interface; xem cơ chế nào đang quyết định proxy type | Cast ép hoặc phụ thuộc tên class proxy ngẫu nhiên |
| Spring cố subclass một JDK core class dưới named module | Đánh giá lại target/proxy design, dùng interface/adapter do ứng dụng sở hữu | Mở toàn bộ `java.base` với kỳ vọng sửa mọi hạn chế |
| Lời gọi nội bộ không được aspect advice | Đưa boundary sang bean cộng tác và gọi qua Spring proxy | Sửa `module-info.java` khi vấn đề là self-invocation |
| Spring Boot dùng CGLIB dù đã đặt AOP `false` | Xem property, transaction/caching settings và proxy thực tế trong context | Suy luận theo một annotation mà bỏ qua cấu hình khác |

## 10. Thiết kế Spring AOP thân thiện JPMS

Một kiến trúc rõ ràng thường có:

```text
module demo.orders
│
├── demo.orders.api
│   └── OrderGateway          [public interface, exported khi cần]
│
├── demo.orders.internal
│   └── DefaultOrderGateway   [class triển khai, giữ riêng]
│
├── demo.orders.aop
│   └── AuditAspect           [Spring bean @Aspect]
│
└── demo.orders.config
    └── SpringConfiguration   [@Configuration, register bean]

module-info.java:
  requires những module thật sự dùng;
  exports các package API cần cho client;
  opens các package Spring cần reflect tới module cụ thể;
  không mở phần nội bộ nếu không có nhu cầu.
```

Khi Spring có thể dùng JDK proxy qua interface API, bạn thường giảm được áp lực phải subclass implementation class. Tuy nhiên, điều đó **không loại bỏ** nhu cầu reflection của Spring IoC (nếu cấu hình/constructor/member của bean cần được inspect) hoặc việc client module phải đọc module cung cấp API.

Ngược lại, nếu thật sự cần advice method không nằm trên interface, bạn phải đánh giá class-based proxy theo cả hai trục: *khả năng Java override* và *khả năng module/runtime tạo subclass*. Đừng đánh đổi JPMS encapsulation chỉ để thuận tiện cast bean về class triển khai mà không có yêu cầu kỹ thuật chính đáng.

## 11. Những điều cần ghi nhớ

- **Spring AOP là proxy-based**: JDK proxy đứng ở interface; CGLIB đứng ở subclass. Method phải được gọi qua proxy thì advice mới chạy.
- **`module-info.java` tăng tính đóng gói**: `requires`, `exports` và `opens` có vai trò khác nhau; chỉ mở đúng package/module mà Spring cần.
- **CGLIB chịu hai loại hạn chế**: Java không cho override `private`/`final` và JPMS có thể ngăn định nghĩa subclass động.
- **JDK proxy không phải “bỏ qua JPMS”**: public API interface và quyền truy cập giữa các module vẫn phải hợp lệ; JDK tự có quy tắc package/module cho proxy class.
- **`--add-opens=java.base/java.lang=ALL-UNNAMED` không phải thuốc chữa chung**: nó nhắm vào unnamed modules và không giải quyết mọi trường hợp named module hoặc classloader.
- **Luôn kiểm tra runtime thực**: proxy type, nested exception, context sở hữu bean, advisor match và đường gọi; từ đó chỉnh module descriptor hoặc thiết kế proxy một cách có căn cứ.

### Tài liệu tham khảo

- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB, `final`/`private`, giới hạn Java Module System, self-invocation.
- [Spring Framework — Component Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): quyền `exports`/`opens` khi dùng Spring trên module path.
- [JDK 17 — java.lang.reflect.Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): quy tắc package/module của JDK dynamic proxy class.
- [Dev.java — Opening for Reflection](https://dev.java/learn/organizing/modules/opening-for-reflection/): khác biệt `exports`/`opens` và quyền truy cập phản chiếu.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): khai báo `@Aspect` và bật Spring AOP.

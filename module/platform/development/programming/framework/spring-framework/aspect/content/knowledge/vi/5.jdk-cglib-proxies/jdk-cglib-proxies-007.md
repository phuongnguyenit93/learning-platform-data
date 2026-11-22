# Phạm vi public, protected và package-visible theo cơ chế proxy trong Spring AOP

## 1. Mục tiêu

Spring AOP can thiệp vào lời gọi phương thức **đi qua Spring proxy**. Tuy nhiên, việc một phương thức có thể được advise hay không còn phụ thuộc vào **loại proxy**, **visibility của phương thức**, **kiểu dữ liệu mà client có thể gọi** và **cách lời gọi đi vào bean**.

Bài này giải quyết trực tiếp câu hỏi: với cùng một service bean trong Spring, lời gọi tới phương thức **public**, **protected** và **package-visible (package-private)** khác nhau thế nào khi Spring dùng **JDK dynamic proxy** hoặc **CGLIB proxy**?

Sau bài học, bạn có thể:

- Phân biệt chính xác vùng phương thức Spring AOP có thể chặn theo từng loại proxy.
- Giải thích vì sao phương thức public có trên implementation nhưng **không khai báo trong interface** không có trên JDK proxy.
- Giải thích điều kiện để class-based CGLIB proxy chặn được protected và package-visible.
- Nhận diện private, final, static, package-visible không thể override trong cây kế thừa và lời gọi nội bộ bỏ qua proxy.
- Viết, chạy và đối chiếu một ví dụ Spring Framework thuần có cả JDK proxy và CGLIB proxy.
- Tránh nhầm quy tắc của **Spring AOP @AspectJ advice** với một số quy tắc riêng của **@Transactional**.

**Phạm vi:** Chỉ xét **proxy-based Spring AOP**, Spring-managed service bean và advice khai báo bằng **@Aspect**. Những kiến thức AOP tổng quát hoặc AspectJ weaving không phải nội dung chính.

## 2. Hai kiểu Spring AOP proxy

Spring AOP lựa chọn một trong hai cơ chế tạo proxy cho target được quản lý:

1. **JDK dynamic proxy**: proxy triển khai interface, chặn những lời gọi **public interface methods** đã được công bố qua proxy. Với cấu hình Spring Framework thuần mặc định, đây là kiểu thường dùng khi target triển khai ít nhất một interface thích hợp.
2. **CGLIB proxy**: proxy là một subclass tạo động của target class. Cơ chế này có thể chặn các method mà subclass **có quyền override** và caller **thật sự gọi thông qua proxy**. Có thể chọn kiểu này khi không có interface hoặc chủ động bật **proxyTargetClass = true**.

Ví dụ:

~~~text
                        Spring ApplicationContext
                                   |
                       target: InventoryService
                                   |
                  +----------------+----------------+
                  |                                 |
              JDK proxy                         CGLIB proxy
        implements InventoryApi          extends InventoryService
                  |                                 |
         public interface API             public, protected,
                                         package-visible hợp lệ
                  |                                 |
                  +----------- client --------------+
                                  |
                        advice -> target
~~~

Sơ đồ thể hiện **điểm có thể intercept**, không có nghĩa CGLIB tự chặn mọi Java call trong target. **Self-invocation** vẫn đi thẳng tới target.

## 3. Bảng quy tắc visibility

| Loại phương thức | JDK dynamic proxy | CGLIB class-based proxy |
| --- | --- | --- |
| **public** và được khai báo trong interface mà proxy triển khai | Có thể chặn qua interface proxy | Có thể chặn qua class proxy |
| **public** chỉ có trên implementation, không nằm trong interface proxy | Không được expose qua JDK interface proxy | Có thể chặn nếu không final và được gọi qua proxy |
| **protected** | Không có trên JDK interface proxy | Có thể chặn nếu overridable và caller truy cập hợp lệ qua proxy |
| **package-visible** khai báo trong chính target class, proxy subclass ở cùng package | Không có trên JDK interface proxy | Có thể chặn khi Java visibility cho phép override |
| **package-visible** kế thừa từ superclass thuộc **package khác** | Không có trên JDK interface proxy | Không thể advise theo cách subclass thông thường vì phương thức **không visible để override** |
| **private** | Không thể expose qua interface như một instance business method | Không thể override, nên không advise được |
| **final instance method** | Nếu public và có trên interface, JDK proxy vẫn có thể chặn **lời gọi qua interface proxy** | Không override được, nên không advise được bằng CGLIB |
| **static method** | Không phải lời gọi instance đi qua JDK proxy | Không phải method instance override của proxy; Spring AOP không chặn lời gọi static |
| **constructor** | Không phải method-execution call trên proxy | Spring AOP proxy không áp dụng advice lên constructor execution |

**“Có thể chặn” không có nghĩa chắc chắn được chặn.** Spring còn cần có advisor khớp với method, bean phải thực sự được expose qua proxy và caller phải gọi trên proxy. Các method bị loại theo visibility/finality không trở thành interceptable chỉ nhờ biểu thức pointcut trông có vẻ khớp.

Một điểm tinh tế: **final** ở implementation không nhất thiết ngăn **JDK dynamic proxy** chặn lời gọi **public interface method**. JDK proxy xử lý lời gọi ở interface phía ngoài target, không subclass/override phương thức final của implementation. CGLIB thì cần override trên subclass nên chịu ràng buộc final.

## 4. Public qua interface: phạm vi chuẩn của JDK proxy

Xét:

~~~java
package demo;

public interface InventoryApi {
    void check();
}
~~~

Và implementation:

~~~java
package demo;

public class InventoryService implements InventoryApi {

    @Override
    public void check() {
        System.out.println("TARGET check");
    }

    public void reindex() {
        System.out.println("TARGET reindex");
    }
}
~~~

Nếu Spring tạo JDK proxy, mã client thường nhận:

~~~java
InventoryApi service = context.getBean(InventoryApi.class);
service.check();
~~~

Lời gọi **check()** có thể đi qua advice; nhưng **service.reindex()** không biên dịch vì kiểu **InventoryApi** không có method này. Ngay cả khi target thật có public **reindex()**, một JDK proxy chỉ triển khai interface được proxy không tự xuất toàn bộ method của implementation.

Không sửa bằng cách ép kiểu:

~~~java
InventoryService concrete = (InventoryService) service;
~~~

Với một JDK dynamic proxy điển hình, phép cast đó dẫn đến **ClassCastException** vì proxy **không phải subclass InventoryService**. Nếu cần gọi **reindex()** qua interface proxy, hãy thiết kế một interface phù hợp; nếu chủ đích cần proxy các method chỉ có trên class, cân nhắc class-based proxy và những giới hạn tương ứng.

**Một public method có trong interface vẫn cần lời gọi đi qua proxy.** Nếu từ bên trong InventoryService có **this.check()**, Spring AOP thông thường không advice lời gọi nội bộ ấy như một invocation riêng.

## 5. CGLIB và khả năng override phương thức

Class-based proxy dùng một subclass runtime của target để intercept. Vì thế nó chịu các quy tắc override của Java:

- **public**: thường có thể override khi không final, và gọi ngoài proxy thuận tiện.
- **protected**: có thể override; từ code ở cùng package hoặc subclass phù hợp, có thể gọi qua proxy và được chặn.
- **package-visible**: có thể override nếu method thật sự visible từ subclass. Trường hợp target và proxy được định nghĩa trong cùng package cho phép; nếu method ở superclass package khác, nó có thể **effectively private** đối với subclass ở package target.
- **private**: không được thừa kế như method overridable; CGLIB không thể override.
- **final**: không cho subclass override; class **final** không thể tạo CGLIB subclass.
- **static**: là lời gọi liên kết với class, không được override như instance method.

Lưu ý thêm: muốn gọi một **protected** hay **package-visible** method của bean từ một class bên ngoài, code gọi vẫn phải thỏa **quy tắc Java access control**. Việc Spring dùng CGLIB không khiến protected hoặc package-visible trở thành public. Do đó ví dụ runnable bên dưới để class **App** và service **cùng package demo**.

Một câu giải thích dễ nhớ: **JDK proxy giới hạn theo interface được expose; CGLIB giới hạn theo khả năng subclass và override.** Cả hai còn bị ràng buộc bởi đường đi lời gọi.

## 6. Ví dụ Maven chạy được: cùng service, hai kiểu proxy

Ta tạo hai **ApplicationContext độc lập**. Context thứ nhất bật JDK proxy, context thứ hai bật CGLIB. Cả hai đều dùng cùng class **VisibilityService**, cùng pointcut, cùng cấu trúc service. Vì tạo hai context độc lập, không phải thay đổi annotation giữa chừng hoặc trộn hai chế độ proxy trong một container.

Yêu cầu: **Java 17+**, **Maven 3.9+**, **Spring Framework 6.2.12**. Đây là ứng dụng console Spring thuần, không cần Spring Boot.

~~~text
spring-aop-method-visibility/
├── pom.xml
└── src/main/java/demo/
    ├── ServiceApi.java
    ├── VisibilityService.java
    ├── VisibilityAspect.java
    └── App.java
~~~

### 6.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-method-visibility</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
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
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**spring-context** mang theo các module core container và Spring AOP cần thiết. **aspectjweaver** cung cấp các kiểu AspectJ annotation và pointcut expression mà Spring AOP sử dụng; ví dụ này vẫn **proxy-based**, không dùng compile-time hay load-time weaving.

### 6.2. Interface chỉ công bố public methods

**src/main/java/demo/ServiceApi.java**

~~~java
package demo;

public interface ServiceApi {
    void publicWork();
    void internalFlow();
}
~~~

Interface Java **public** chỉ công bố **publicWork()** và **internalFlow()** cho client JDK proxy. Interface không chứa protected hoặc package-visible abstract instance methods theo nghĩa hợp đồng API. Ngoài ra, không có **protectedWork()** hay **packageWork()** trên interface.

### 6.3. Service chứa đủ các mức visibility

**src/main/java/demo/VisibilityService.java**

~~~java
package demo;

public class VisibilityService implements ServiceApi {

    @Override
    public void publicWork() {
        System.out.println("TARGET publicWork");
    }

    public void implementationOnly() {
        System.out.println("TARGET implementationOnly");
    }

    protected void protectedWork() {
        System.out.println("TARGET protectedWork");
    }

    void packageWork() {
        System.out.println("TARGET packageWork");
    }

    private void privateWork() {
        System.out.println("TARGET privateWork");
    }

    @Override
    public void internalFlow() {
        System.out.println("TARGET internalFlow");
        this.protectedWork();
        this.packageWork();
        this.privateWork();
    }
}
~~~

Ở đây:

- **publicWork()**: public và nằm trong **ServiceApi**.
- **implementationOnly()**: public nhưng không nằm trong interface.
- **protectedWork()**: protected, callable từ **App** trong cùng package demo.
- **packageWork()**: package-visible do không có từ khóa access modifier, callable từ **App** trong cùng package.
- **privateWork()**: private, chỉ gọi trong class; không thể gọi trực tiếp trên Spring proxy từ App.
- **internalFlow()**: public và nằm trong interface, nhưng gọi protected, package-visible và private method bằng **this**. Cả ba lời gọi nội bộ này không tự đi qua proxy.

### 6.4. Aspect ghi nhận tên method trước khi vào target

**src/main/java/demo/VisibilityAspect.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class VisibilityAspect {

    @Before("execution(* demo.VisibilityService.*(..))")
    public void before(JoinPoint joinPoint) {
        System.out.println(
                "ADVICE " + joinPoint.getSignature().getName());
    }
}
~~~

**@Before** được Spring AOP gọi khi một **method execution** khớp pointcut và invocation đi qua proxy. Mẫu **execution(* demo.VisibilityService.*(..))** cố ý không ghi từ khóa public, vì bài muốn kiểm tra cả protected và package-visible.

Biểu thức pointcut có thể biểu diễn tên một method nhưng **không mở rộng khả năng kỹ thuật của proxy**. Nếu CGLIB không override được một method, hoặc method được gọi trực tiếp qua **this**, advice sẽ không chạy cho lời gọi đó.

Aspect được đăng ký bằng phương thức **@Bean** trong cấu hình nên không cần **@Component**; chỉ gắn **@Aspect** mà không đăng ký như Spring bean sẽ không đủ.

### 6.5. Chạy hai ApplicationContext độc lập

**src/main/java/demo/App.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class App {

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy
    static class JdkConfig {

        @Bean
        public ServiceApi service() {
            return new VisibilityService();
        }

        @Bean
        public VisibilityAspect visibilityAspect() {
            return new VisibilityAspect();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    static class CglibConfig {

        @Bean
        public VisibilityService service() {
            return new VisibilityService();
        }

        @Bean
        public VisibilityAspect visibilityAspect() {
            return new VisibilityAspect();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(JdkConfig.class)) {

            ServiceApi service = context.getBean(ServiceApi.class);

            System.out.println("=== JDK ===");
            System.out.println(
                    "JDK_PROXY " + AopUtils.isJdkDynamicProxy(service));

            service.publicWork();
            service.internalFlow();
        }

        try (var context =
                     new AnnotationConfigApplicationContext(CglibConfig.class)) {

            VisibilityService service =
                    context.getBean(VisibilityService.class);

            System.out.println("=== CGLIB ===");
            System.out.println(
                    "CGLIB_PROXY " + AopUtils.isCglibProxy(service));

            service.publicWork();
            service.implementationOnly();
            service.protectedWork();
            service.packageWork();
            service.internalFlow();
        }
    }
}
~~~

Giải thích cấu hình:

1. **JdkConfig**: trả bean dưới hợp đồng **ServiceApi**, đồng thời **@EnableAspectJAutoProxy** mặc định ưu tiên JDK dynamic proxy khi target có interface. Client lấy service bằng interface.
2. **CglibConfig**: bật **@EnableAspectJAutoProxy(proxyTargetClass = true)**, chủ động chọn class-based proxy. Client lấy bằng **VisibilityService.class** nên truy cập được protected/package-visible trong cùng package.
3. Hai context cùng đăng ký **VisibilityAspect** nhưng **mỗi context có instance riêng**, không phải hai aspect bean trong một context.
4. **@Bean** tạo **VisibilityService** làm Spring-managed bean. Lời gọi qua bean do container trả về mới có đường đi Spring AOP proxy.
5. **@Configuration(proxyBeanMethods = false)** chỉ xử lý việc interceptor các phương thức **@Bean** trong class cấu hình; nó **không hủy chế độ AOP** cho service, vì **@EnableAspectJAutoProxy** vẫn được bật.
6. **@Before** là advice đơn giản, có đầu ra in theo tên method để thấy chính xác method nào được chặn.

Trong project **Spring Boot**, cấu hình chọn loại proxy có thể bị Boot AOP auto-configuration tác động; ví dụ này là **Spring Framework thuần** để so sánh chính xác hai chế độ.

## 7. Chạy và đọc stdout

Trong thư mục dự án chứa pom.xml, chạy:

~~~bash
mvn -q clean compile exec:java
~~~

Đầu ra logic kỳ vọng, bỏ qua thông điệp Maven và logging của framework:

~~~text
=== JDK ===
JDK_PROXY true
ADVICE publicWork
TARGET publicWork
ADVICE internalFlow
TARGET internalFlow
TARGET protectedWork
TARGET packageWork
TARGET privateWork
=== CGLIB ===
CGLIB_PROXY true
ADVICE publicWork
TARGET publicWork
ADVICE implementationOnly
TARGET implementationOnly
ADVICE protectedWork
TARGET protectedWork
ADVICE packageWork
TARGET packageWork
ADVICE internalFlow
TARGET internalFlow
TARGET protectedWork
TARGET packageWork
TARGET privateWork
~~~

### 7.1. Quan sát JDK

- **JDK_PROXY true** cho thấy Spring trả về JDK dynamic proxy.
- **publicWork()** được khai báo trên interface, vì vậy client gọi qua proxy và advice xuất hiện trước target.
- **internalFlow()** cũng là public interface method nên lời gọi bên ngoài được advice.
- Bên trong **internalFlow()**, các method protected/package-visible/private được gọi trên **this** của target; không có các dòng **ADVICE protectedWork**, **ADVICE packageWork** hoặc **ADVICE privateWork**.
- **implementationOnly()** không thể gọi từ biến **ServiceApi**. Điểm này là giới hạn API của JDK proxy, không phải lỗi pointcut.

### 7.2. Quan sát CGLIB

- **CGLIB_PROXY true** cho thấy Spring trả về class-based proxy của VisibilityService.
- **publicWork()** được chặn tương tự JDK.
- **implementationOnly()** được chặn khi gọi từ App qua class proxy, dù method không có trên interface.
- **protectedWork()** và **packageWork()** được chặn vì có thể override trong proxy subclass và App ở cùng package **demo** gọi trực tiếp trên proxy.
- **internalFlow()** được chặn ở lời gọi bên ngoài. Tuy nhiên, ba lời gọi **this.protectedWork()**, **this.packageWork()**, **this.privateWork()** bên trong target vẫn không qua proxy, nên chỉ có dòng **TARGET**.

**Điểm mấu chốt:** “CGLIB có thể advise protected và package-visible” là phát biểu về **khả năng intercept lời gọi qua proxy**, không có nghĩa mọi lần thực thi các method đó trên target đều tạo một lần advice.

## 8. Vì sao gọi internalFlow() không làm ba advice bên trong chạy?

Spring AOP sử dụng proxy để chặn lời gọi từ bên ngoài:

~~~text
App
 |
 v
CGLIB proxy
 |
 +-- advice: internalFlow
 |
 v
VisibilityService.internalFlow()        <- target
 |
 +-- this.protectedWork() ------------- trực tiếp vào target
 +-- this.packageWork() --------------- trực tiếp vào target
 +-- this.privateWork() --------------- trực tiếp vào target
~~~

Từ khóa **this** trong thân **VisibilityService** tham chiếu object target đang chạy; các lời gọi nội bộ không quay trở lại proxy.

Cả hai câu dưới đây đều có thể đúng đồng thời:

- **App gọi service.protectedWork() qua class-based proxy** → advice chạy.
- **internalFlow() gọi this.protectedWork() bên trong target** → advice cho protectedWork không chạy.

Muốn kiểm tra chính xác đường đi, phải biết **đối tượng nào được caller giữ**. Đừng chỉ nhìn visibility hoặc annotation trên method.

Cách thiết kế dễ kiểm soát khi một thao tác cần advice là **đặt thao tác đó ở một Spring bean khác** và gọi qua dependency được inject. Không nên tìm cách vá self-invocation bằng cast hoặc tự tạo instance target.

## 9. Package-visible: trường hợp cùng package và khác package

Phương thức package-visible không có từ khóa **public/protected/private**:

~~~java
package demo;

public class LocalService {
    void refreshCache() {
        System.out.println("refresh");
    }
}
~~~

Trong cùng package demo, một Spring CGLIB subclass có thể override **refreshCache()** nếu không final; khi một caller hợp lệ ở cùng package gọi **qua proxy**, Spring AOP có thể chạy advice.

Nhưng xét inheritance qua hai package:

~~~text
src/main/java/
├── base/
│   └── BaseService.java     // package base
└── demo/
    └── DerivedService.java  // package demo, extends BaseService
~~~

**base/BaseService.java**

~~~java
package base;

public class BaseService {
    void hiddenOperation() {
        System.out.println("BASE hiddenOperation");
    }
}
~~~

**demo/DerivedService.java**

~~~java
package demo;

import base.BaseService;

public class DerivedService extends BaseService {
    public void run() {
        System.out.println("DERIVED run");
    }
}
~~~

**hiddenOperation()** là package-visible của **base**, không visible cho subclass ở package **demo**. Nó không thể được subclass CGLIB ở package demo override theo cách thông thường; đối với tình huống này, nó **effectively private** từ góc nhìn subclass. Vì vậy không được kết luận “mọi package-private method đều được CGLIB chặn”.

Hai file ở mục này là **ví dụ minh họa Java visibility**, chưa gắn với class App hoặc cấu hình Spring ở mục 6, và không thể gọi hiddenOperation trực tiếp từ DerivedService ở package demo.

Nếu nghiệp vụ thực sự cần lời gọi từ bên ngoài đi qua advice, nên dùng public method là điểm vào rõ ràng. Protected/package-visible có giá trị ở phạm vi hẹp nhưng đòi hỏi cả Java access control lẫn khả năng proxy override.

## 10. Những giới hạn không phải do mức visibility

Khi so sánh public/protected/package-visible, cần kiểm tra thêm **khả năng override** và **đường gọi**:

- CGLIB không thể tạo subclass của `final class`, không thể override `final`/`private` instance methods; các method này không được advice qua class-based proxy. Một method `public` vẫn có thể không được advice nếu nó `final`.
- JDK proxy lại có thể chặn một public interface method dù phần implementation được khai báo `final`, vì việc chặn diễn ra ở interface boundary chứ không cần override target method.
- `static` methods không dispatch qua instance proxy; constructor cũng không phải method-execution join point của Spring AOP.
- Ngay cả method public có thể override vẫn bỏ qua advice khi target tự gọi `this.method()` thay vì client gọi qua proxy.

Những điều kiện trên độc lập với việc caller có quyền truy cập protected/package-visible hay không. Muốn xác nhận một lời gọi được advice, hãy kiểm tra đầy đủ loại proxy, khả năng override, pointcut và đường đi của invocation.

## 11. Pointcut có thể giới hạn public, nhưng không ép protected thành public

Trong aspect ở mục 6:

~~~java
@Before("execution(* demo.VisibilityService.*(..))")
public void before(JoinPoint joinPoint) {
    // ...
}
~~~

Biểu thức **execution** không chỉ định modifier, vì thế về mặt pointcut nó có thể mô tả nhiều mức visibility. **Proxy vẫn là giới hạn thực thi**.

Nếu muốn chỉ bắt các public method:

~~~java
@Before("execution(public * demo.VisibilityService.*(..))")
public void beforePublic(JoinPoint joinPoint) {
    // ...
}
~~~

Đây là **biến thể pointcut minh họa**; khi thử, thay annotation/method trong aspect hiện tại hoặc tạo context thử riêng, tránh vừa giữ advice cũ vừa thêm advice mới rồi nhầm số log.

Khi chạy với CGLIB:

- publicWork, implementationOnly và internalFlow có thể khớp **public**.
- protectedWork và packageWork **không** khớp biểu thức có modifier **public**.
- privateWork vẫn không thể được Spring AOP proxy advise dù bạn viết một pointcut có tên của nó.

Trong AspectJ pointcut syntax, **visibility của phương thức @Pointcut được dùng để tái sử dụng biểu thức** và **visibility của target method trong execution()** là hai việc khác nhau. Việc đặt method khai báo **@Pointcut** là private không tự thu hẹp những join point mà biểu thức của pointcut có thể match.

## 12. Phân biệt quy tắc kỹ thuật của AOP với @Transactional

Spring thường dùng các proxy tương tự cho **@Transactional**, **@Async** và một số tính năng khác. Tuy vậy, mỗi tính năng còn có **quy tắc chọn method và metadata riêng**. Không được suy ra chỉ từ cơ chế CGLIB rằng một annotation trên mọi method không-public sẽ luôn có hiệu lực.

Ví dụ với **Spring Framework 6+**, hỗ trợ transaction annotation có thể xử lý **protected** và **package-visible** trên **class-based proxy** theo mặc định; với **interface-based proxy**, method transaction phải **public và công bố trên interface**. Cấu hình transaction còn phụ thuộc **@EnableTransactionManagement**, transaction manager và các quy tắc nhận diện transaction metadata.

Đối với **Spring AOP @AspectJ @Before** trong bài này, điểm cốt lõi là Spring đánh giá **execution pointcut** trên method invocation có thể intercept. **@Transactional** là một ví dụ khác sử dụng proxy nhưng có thêm lớp quy tắc riêng. Khi kiểm thử một tính năng cụ thể, cần đọc tài liệu của tính năng đó và không đồng nhất “có proxy” với “đã áp dụng transaction/advice”.

## 13. CGLIB không tự mở rộng quyền truy cập của caller

Giả sử **App** chuyển sang package khác (ví dụ **client**) và không kế thừa VisibilityService, Java không cho biên dịch lời gọi:

~~~java
service.protectedWork();
service.packageWork();
~~~

Kể cả nếu **service** là class-based proxy, source code bên ngoài package vẫn phải tuân thủ quy tắc truy cập Java. Việc Spring bọc bean không biến protected/package-visible thành API công khai.

Do đó, trong thiết kế ứng dụng lớn:

- Public service method thường là contract dễ dùng và dễ test nhất.
- Protected thường dành cho subclass extension hooks; gọi qua proxy cần đúng ngữ cảnh Java.
- Package-visible hợp lý cho nội bộ package; không phải API công bố giữa module/package.
- Nếu muốn phương thức được áp dụng advice từ module khác, cân nhắc tạo một public entry point trên Spring-managed bean, với pointcut và dependency rõ ràng.

## 14. Trường hợp method không nằm trong interface JDK proxy

Trong **VisibilityService** có public **implementationOnly()**, nhưng **ServiceApi** không khai báo method này. Dưới JDK proxy:

~~~java
ServiceApi proxy = context.getBean(ServiceApi.class);
proxy.publicWork();       // Hợp lệ
// proxy.implementationOnly(); // Không biên dịch
~~~

Hai hướng thiết kế:

1. **Bổ sung method vào một interface phù hợp** nếu nó thực sự thuộc hợp đồng nghiệp vụ cần expose. Khi đó JDK proxy có thể công bố method.
2. **Chọn CGLIB** nếu cần expose các public method của implementation mà không qua interface, đồng thời chấp nhận ràng buộc inheritance và final/private.

Không dùng **ProxyTargetClass** chỉ để sửa một phép cast mà không cân nhắc thiết kế API. Nếu cùng một bean được người dùng khác inject theo interface, thay đổi từ JDK sang CGLIB có thể ảnh hưởng đến các phép kiểm tra kiểu, pointcut và behavior phụ thuộc class.

## 15. Những hiểu lầm thường gặp trong Spring AOP

| Nhận định | Đánh giá đúng |
| --- | --- |
| “Spring AOP chỉ chặn public method trong mọi trường hợp.” | Sai về mặt tổng quát: **CGLIB** có thể chặn protected/package-visible nếu phương thức overridable, caller hợp lệ và đi qua proxy |
| “Dùng @Aspect có thể chặn mọi private method.” | Sai: Spring AOP proxy không override private method |
| “CGLIB chặn protected bất kể ai gọi.” | Sai: lời gọi phải đi qua proxy; Java visibility vẫn áp dụng |
| “Package-private được chặn dù method khai báo ở superclass package khác.” | Sai: nếu không visible để override từ proxy subclass, method effectively private |
| “Phương thức final luôn không thể được advice ở mọi loại proxy.” | Sai: final chặn **CGLIB override**; JDK interface proxy vẫn có thể advice public interface call |
| “Method là public trong implementation nên JDK proxy đều thấy.” | Sai: JDK proxy expose những interface methods của proxy, không phải toàn bộ implementation |
| “CGLIB chặn cả lệnh this.protectedWork().” | Sai: self-invocation trên target không qua proxy |
| “@EnableAspectJAutoProxy làm service tự được đăng ký bean.” | Sai: vẫn cần component scan, @Bean hoặc cơ chế đăng ký bean khác |
| “AopUtils.isAopProxy(bean) = true chứng tỏ method này được advice.” | Chưa đủ: cần xác minh pointcut và lời gọi thực tế |
| “Protected method có thể gọi từ class ở package bất kỳ nếu đã bật proxyTargetClass.” | Sai: Java access control không đổi |
| “Thêm public vào execution pointcut sẽ chặn protected.” | Sai: modifier public làm pointcut hẹp lại |
| “Chọn CGLIB sẽ khắc phục mọi lỗi thiếu transaction hoặc advice.” | Sai: có thể do đăng ký bean, pointcut, metadata hay self-invocation |

## 16. Quy trình điều tra khi thiếu advice

Thực hiện theo thứ tự dưới đây để tránh suy đoán:

### Bước 1 — Xác nhận bean lấy từ ApplicationContext

~~~java
Object service = context.getBean("service");
System.out.println(
        org.springframework.aop.support.AopUtils.isAopProxy(service));
~~~

Nếu tự **new VisibilityService()** rồi gọi trực tiếp, Spring AOP không tự chặn instance đó. Đoạn mã là fragment debug cần có biến **context** hợp lệ.

### Bước 2 — Xác định loại proxy

~~~java
System.out.println(
        org.springframework.aop.support.AopUtils.isJdkDynamicProxy(service));
System.out.println(
        org.springframework.aop.support.AopUtils.isCglibProxy(service));
~~~

Nếu JDK proxy, xác minh phương thức muốn gọi **có trên interface được expose**. Nếu CGLIB proxy, xác minh method có thể override và caller truy cập hợp lệ.

### Bước 3 — Kiểm tra pointcut

Ví dụ wildcard **execution(* demo.VisibilityService.*(..))** có thể match public/protected/package-visible phù hợp. Nếu pointcut ghi **execution(public ...)**, protected/package-visible bị loại theo biểu thức.

Ngoài ra, package/class trong pointcut phải khớp service thật. Đừng đoán rằng advice chạy khi chỉ thay visibility.

### Bước 4 — Kiểm tra đường gọi

Đặt log tại **@Before**, rồi so với log trong target. Nếu log advice chỉ xuất hiện khi gọi từ App nhưng thiếu khi target gọi **this.method()**, đó là self-invocation, không phải lỗi Spring không nhìn thấy method.

### Bước 5 — Xem xét final, private và cây kế thừa

- Class final không tạo CGLIB subclass.
- Method final hoặc private không override được.
- Package-visible method ở superclass thuộc package khác có thể không visible đối với proxy subclass.
- Nếu method được gọi theo kiểu static, nó không qua instance proxy.

### Bước 6 — Xác minh cấu hình

Có thể dùng:

~~~java
@EnableAspectJAutoProxy(proxyTargetClass = true)
~~~

để yêu cầu class-based proxy trong context tương ứng. Đồng thời phải đăng ký **@Aspect** như Spring bean qua **@Component** hoặc **@Bean**. Annotation trên class không đủ nếu bean không nằm trong ApplicationContext.

## 17. Một số bài tập kiểm chứng

**Bài tập A — Chỉ public qua CGLIB.** Thay pointcut bằng **execution(public * demo.VisibilityService.*(..))** và chạy lại context CGLIB. Quan sát advice chỉ xuất hiện trước những public methods được gọi qua proxy; protected/package-visible vẫn in dòng target nhưng không có advice của pointcut public-only.

**Bài tập B — Thêm public implementation-only vào interface.** Thêm **void implementationOnly()** vào ServiceApi, rồi gọi nó ở phần JDK. Quan sát JDK proxy bây giờ công bố method qua interface và có thể chạy advice cho lời gọi đó.

**Bài tập C — Biến protectedWork thành final.** Không thể khai báo đồng thời một method final trong base và override nó ở subclass; CGLIB không advice cho protectedWork bằng cách override. So sánh việc chặn **publicWork()** vẫn hoạt động. Đây là bài tập thay đổi source rồi chạy lại, không phải thay đổi nên áp dụng vào service production.

**Bài tập D — Dời App sang package khác.** Thử gọi protectedWork/packageWork trong App ở package khác để thấy lỗi biên dịch do Java visibility. CGLIB không thay thế quy tắc access control.

**Bài tập E — Gọi lại từ internalFlow().** Đếm số dòng advice trước protectedWork hoặc packageWork khi gọi trực tiếp qua proxy, rồi so với gọi nội bộ. Giải thích sự khác biệt theo đường đi của invocation.

## 18. Các câu hỏi tự đánh giá

**1. JDK dynamic proxy có thể advise một public method nằm trong implementation nhưng không thuộc interface được proxy không?**

Không theo đường gọi qua JDK interface proxy đó: proxy không expose method implementation-only. Nếu muốn gọi qua proxy, cần thay API interface hoặc chọn class-based proxy.

**2. CGLIB có thể advise một protected method không?**

Có, khi method có thể override, nằm trong vùng visible của proxy subclass, pointcut phù hợp và caller thật sự gọi qua proxy trong ngữ cảnh Java hợp lệ.

**3. Package-visible nào không thể được CGLIB advise dù cùng tên method?**

Một ví dụ là package-visible method khai báo trong superclass ở **package khác**, khiến proxy subclass không thể override vì method effectively private từ góc nhìn subclass.

**4. Tại sao @Before xuất hiện khi App gọi protectedWork qua proxy nhưng không xuất hiện khi internalFlow gọi this.protectedWork?**

Vì App gọi qua proxy; lời gọi **this** trong target là lời gọi nội bộ trực tiếp, không quay lại proxy.

**5. Một final public method triển khai interface có luôn nằm ngoài Spring AOP không?**

Không. JDK interface proxy có thể advice public interface call dù implementation method final. Giới hạn final trực tiếp ngăn cơ chế override của CGLIB.

**6. Đặt pointcut rộng trên cả class có làm private method trở thành join point được proxy chặn không?**

Không. Việc biểu thức có thể ghi tên method không vượt qua hạn chế override hoặc cấu trúc lời gọi proxy của Spring AOP.

**7. Nếu service bị proxy nhưng không có advice ở package-visible method, cần kiểm tra điều gì?**

Xác định proxy là JDK hay CGLIB, method có visible và overridable không, caller gọi qua proxy hay **this**, và pointcut có match hay không.

**8. Để xây API Spring service ổn định giữa JDK và CGLIB nên làm gì?**

Ưu tiên các **public service methods** có hợp đồng rõ ràng; nếu theo interface, khai báo method cần chặn trong interface. Chỉ dựa vào protected/package-visible interception khi thực sự cần và đã có kiểm thử cho kiểu proxy đang sử dụng.

## 19. Tài liệu Spring chính thức

- Spring Framework 6.2 — **Proxying Mechanisms** (JDK proxy, CGLIB, final/private/effectively-private và self-invocation): https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring Framework — **Declaring a Pointcut** (public interface methods, public/protected/package-visible trên CGLIB và execution modifier): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Spring Framework — **AOP Proxies**: https://docs.spring.io/spring-framework/reference/core/aop/introduction-proxies.html
- Spring Framework — **@AspectJ Support**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework — **Using @Transactional** (quy tắc visibility riêng của transaction annotation trong proxy mode): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html

**Kết luận kỹ thuật:** Phạm vi Spring AOP được quyết định bởi **loại proxy + khả năng expose/override method + pointcut + đường đi lời gọi**. Với **JDK proxy**, client dùng các public interface methods. Với **CGLIB**, lời gọi qua proxy có thể được advice trên public, protected và package-visible methods khi Java cho phép override và truy cập; private/final/static hoặc self-invocation không thể được xử lý theo cùng cách proxy đó.

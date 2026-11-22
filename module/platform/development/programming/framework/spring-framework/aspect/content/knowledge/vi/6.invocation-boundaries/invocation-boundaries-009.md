# Proxy lồng nhau và việc lần theo chuỗi đối tượng trong Spring AOP

## 1. Mục tiêu bài học

Trong Spring AOP, caller đôi khi không gọi trực tiếp đối tượng nghiệp vụ, mà gọi qua nhiều tầng wrapper. Một tình huống quan trọng là **target của một Spring AOP proxy lại là một Spring AOP proxy khác**. Khi đó cần biết lời gọi đi qua tầng nào, interceptor nào chạy ở đâu, và tại sao có thể mất hoặc chạy lặp advice.

Sơ đồ:

~~~text
Caller
  -> Outer Spring AOP proxy
       -> Outer interceptor/advisor
       -> Inner Spring AOP proxy
            -> Inner interceptor/advisor từ @Aspect
            -> TargetService.method()
~~~

Bài học này chỉ nói về **Spring Aspect/Spring AOP dựa trên proxy**, đặc biệt là:

1. Phân biệt **một proxy với nhiều advisors** và **nhiều proxy lồng nhau**.
2. Lần theo từng tầng bằng Spring AOP APIs: AopUtils, Advised, TargetSource và AopProxyUtils.
3. Hiểu thứ tự gọi, proceed, return, exception và các điểm cắt ngắn chuỗi.
4. Tránh truy xuất target động hoặc tự bóc proxy trong code nghiệp vụ.
5. Quan sát qua một ứng dụng Maven/Java 17+ chạy được với @Aspect thật và ProxyFactory.
6. Chẩn đoán khi transaction, cache, scoped proxy hoặc adapter khác cùng tồn tại.

Việc có nhiều lớp @Aspect hoặc nhiều annotation Spring AOP trên một bean **không tự động có nghĩa** Spring đã tạo nhiều proxy lồng nhau. Spring auto-proxy thông thường có thể đưa nhiều advisors vào **một proxy duy nhất**.

## 2. Ba cấu trúc rất khác nhau

### 2.1. Một proxy, nhiều advisors

~~~text
Client
 -> AOP Proxy [Advisor A, Advisor B, Advisor C]
     -> Target
~~~

Proxy có một TargetSource và một danh sách advisors. Nếu bean được áp dụng custom @Aspect và transaction advice, trong một cấu hình thông thường, chúng có thể cùng xuất hiện trên một Spring AOP proxy. Số lượng advisors có thể lớn hơn một nhưng số tầng proxy vẫn chỉ là một.

### 2.2. Hai proxy thật sự lồng nhau

~~~text
Client
 -> Outer Proxy [Advisor A]
     -> Inner Proxy [Advisor B]
         -> Target
~~~

Ở đây target của Outer Proxy là object Inner Proxy. Mỗi proxy có cấu hình riêng; việc gọi phương thức trên Outer Proxy có thể đi qua cả hai chuỗi interceptor.

Nếu kiểm tra:

~~~java
Advised outerAdvised = (Advised) outer;
Advisor[] advisors = outerAdvised.getAdvisors();
~~~

thì mảng đó mô tả advisors **trực tiếp của outer**, không nhất thiết hiển thị advisor trên inner.

### 2.3. Một proxy Spring AOP nằm bên trong wrapper khác

~~~text
Client
 -> Custom JDK proxy hoặc framework adapter
     -> Spring AOP proxy
         -> Target
~~~

Một proxy JDK tự tạo từ java.lang.reflect.Proxy không mặc nhiên là Spring AOP proxy. Một class có tên chứa CGLIB cũng chưa chắc là AOP proxy: Spring còn dùng class enhancement cho @Configuration và nhiều chức năng khác.

**Nguyên tắc:** Phải xác định **thực tế object nào đang được client giữ**, chứ không kết luận từ tên class hay từ việc có nhiều dòng log.

## 3. Những công cụ Spring nên biết

| API | Dùng để quan sát | Giới hạn cần nhớ |
| --- | --- | --- |
| AopUtils.isAopProxy(obj) | Object có là Spring AOP proxy không | Không chứng minh có advice của @Aspect cụ thể |
| AopUtils.isJdkDynamicProxy(obj) | Proxy AOP theo interface/JDK | Không dùng kết quả này để đếm các tầng |
| AopUtils.isCglibProxy(obj) | Proxy AOP class-based | Class được CGLIB tăng cường ngoài AOP là tình huống khác |
| obj instanceof Advised | Object có expose cấu hình advised không | Proxy được cấu hình opaque có thể không cho cast sang Advised |
| Advised.getAdvisors() | Danh sách advisors ở **tầng hiện tại** | Không gộp advisor của inner |
| Advised.getTargetSource() | Abstraction tìm target ở **tầng hiện tại** | Target có thể là singleton, scope, pool hoặc lazy |
| TargetSource.getTargetClass() | Loại target được công bố | Không cần khởi tạo hay truy xuất target thực tế |
| TargetSource.isStatic() | Có trả lại cùng một target cho các lần gọi không | Không bảo đảm đó là một plain object |
| AopProxyUtils.getSingletonTarget(obj) | Đối tượng target ngay bên dưới khi dùng SingletonTargetSource | Trả null khi không thỏa, không tự truy qua dynamic sources |
| AopProxyUtils.ultimateTargetClass(obj) | Loại target sâu nhất theo chuỗi singleton có thể truy an toàn | Không phải công cụ bóc mọi wrapper do thư viện khác tạo |

Các imports quan trọng:

~~~java
import org.springframework.aop.Advisor;
import org.springframework.aop.TargetSource;
import org.springframework.aop.framework.Advised;
import org.springframework.aop.framework.AopProxyUtils;
import org.springframework.aop.support.AopUtils;
~~~

**Phân biệt:** Đọc được target class không có nghĩa object proxy là instance của class đó. Với JDK proxy, kiểu runtime thường là proxy triển khai interface, không phải subclass của implementation.

## 4. Cách Spring xử lý đường gọi qua nested proxies

Giả sử outer và inner đều có around-style interceptor:

~~~text
1. Client gọi outer.method()
2. Outer interceptor bắt đầu và ghi log before
3. Outer invocation.proceed()
4. Inner proxy nhận method call
5. Inner advice chạy nếu pointcut khớp
6. Inner chuyển sang target.method()
7. Target trả kết quả
8. Inner trả kết quả cho outer
9. Outer interceptor ghi log after và trả kết quả cho client
~~~

Một interceptor đặt log trước và sau proceed thể hiện dạng:

~~~java
Object invoke(MethodInvocation invocation) throws Throwable {
    before();
    Object result = invocation.proceed();
    after();
    return result;
}
~~~

Đây là **mẫu minh họa**: before/after là tên pseudocode, không phải chương trình hoàn chỉnh. Nếu proceed ném exception, after nằm sau proceed sẽ không chạy, trừ khi bạn đặt cleanup trong finally. Nếu inner advice short-circuit và không gọi proceed (ví dụ cache hit), target có thể không được gọi.

**@Order không tự thay đổi ranh giới vật lý outer/inner.** @Order chủ yếu tham gia quy tắc sắp xếp advisors khi được framework quản lý trong một chuỗi. Với hai proxy do code đã cấu hình độc lập, outer vẫn là outer; muốn đổi thứ tự tầng phải đổi cấu trúc wrapping.

## 5. Ví dụ Java 17+ chạy được: @Aspect inner + ProxyFactory outer

Chương trình minh họa dùng:

- Spring Framework **6.2.19**, AspectJ Weaver **1.9.25.1**.
- Một Spring bean chứa logic nghiệp vụ.
- Một aspect bean với @Before, được Spring AOP áp dụng lên bean nghiệp vụ.
- Một Spring AOP ProxyFactory tạo **proxy ngoài**, bọc chính proxy trong do context trả ra.
- API quan sát cho biết có hai tầng khác nhau.

Ví dụ này **không dùng AspectJ bytecode weaving**; toàn bộ hành vi được thực hiện qua Spring AOP proxies.

### 5.1. Thư mục

~~~text
spring-nested-aop/
├── pom.xml
└── src/main/java/example/
    ├── GreetingPort.java
    ├── GreetingService.java
    ├── TraceAspect.java
    ├── AppConfig.java
    └── Main.java
~~~

### 5.2. Maven

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-nested-aop</artifactId>
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
            <version>1.9.25.1</version>
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
~~~

Trong dự án thực tế, nên dùng Spring Framework BOM hoặc Spring Boot BOM để các module spring-* thống nhất phiên bản. Ở đây ghi trực tiếp phiên bản để ví dụ độc lập, không nên sao chép các số version này vào một Spring Boot app đang quản lý phiên bản khác.

### 5.3. Interface và target

**GreetingPort.java**

~~~java
package example;

public interface GreetingPort {
    String greet(String name);
}
~~~

**GreetingService.java**

~~~java
package example;

public class GreetingService implements GreetingPort {

    @Override
    public String greet(String name) {
        System.out.println("target: greet " + name);
        return "hello " + name;
    }
}
~~~

### 5.4. Aspect của Spring

**TraceAspect.java**

~~~java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {

    @Before("execution(* example.GreetingService.greet(..))")
    public void beforeGreet() {
        System.out.println("inner aspect: before");
    }
}
~~~

Aspect khai báo advice trên method target. Class @Aspect này cần được đăng ký thành bean để Spring AOP sử dụng.

### 5.5. Cấu hình tạo inner proxy

**AppConfig.java**

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {

    @Bean
    public GreetingPort greetingService() {
        return new GreetingService();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
~~~

Spring AOP nhận diện TraceAspect và advisor khớp GreetingService.greet. Với interface GreetingPort và cấu hình không ép class proxy, Spring dùng **JDK dynamic proxy** cho bean greetingService. Đừng nhầm annotation @Aspect với annotation tự đăng ký bean: chính method @Bean đã đăng ký TraceAspect.

### 5.6. Tạo proxy ngoài và kiểm tra object chain

**Main.java**

~~~java
package example;

import org.aopalliance.intercept.MethodInterceptor;
import org.springframework.aop.framework.Advised;
import org.springframework.aop.framework.AopProxyUtils;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            GreetingPort inner =
                context.getBean("greetingService", GreetingPort.class);

            ProxyFactory factory = new ProxyFactory();
            factory.setInterfaces(GreetingPort.class);
            factory.setTarget(inner);
            factory.addAdvice((MethodInterceptor) invocation -> {
                System.out.println("outer: before");
                Object result = invocation.proceed();
                System.out.println("outer: after");
                return result;
            });

            GreetingPort outer = (GreetingPort) factory.getProxy();

            System.out.println("inner is AOP proxy: "
                + AopUtils.isAopProxy(inner));
            System.out.println("outer is AOP proxy: "
                + AopUtils.isAopProxy(outer));
            System.out.println("both JDK proxies: "
                + (AopUtils.isJdkDynamicProxy(inner)
                   && AopUtils.isJdkDynamicProxy(outer)));

            Object immediate = AopProxyUtils.getSingletonTarget(outer);
            Object deepest = AopProxyUtils.getSingletonTarget(inner);

            System.out.println("outer wraps inner: "
                + (immediate == inner));
            System.out.println("inner wraps plain target: "
                + (deepest instanceof GreetingService
                   && !AopUtils.isAopProxy(deepest)));
            System.out.println("ultimate target type: "
                + AopProxyUtils.ultimateTargetClass(outer).getSimpleName());

            if (outer instanceof Advised advised) {
                System.out.println("outer advisors: "
                    + advised.getAdvisors().length);
            }

            System.out.println("result: " + outer.greet("Lan"));
        }
    }
}
~~~

Cấu trúc có chủ đích: inner lấy từ Spring container nên nó đã có advice của @Aspect. ProxyFactory được gọi **sau khi** context hoàn tất, và proxy ngoài không đăng ký lại thành Spring bean. Vì thế ví dụ không phụ thuộc vào việc container có auto-proxy thêm lớp proxy ngoài hay không.

### 5.7. Chạy chương trình

Trong thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

**Các dòng do chương trình in ra, đúng thứ tự:**

~~~text
inner is AOP proxy: true
outer is AOP proxy: true
both JDK proxies: true
outer wraps inner: true
inner wraps plain target: true
ultimate target type: GreetingService
outer advisors: 1
outer: before
inner aspect: before
target: greet Lan
outer: after
result: hello Lan
~~~

Log do Maven/framework phát ra (nếu có) không nằm trong phần stdout cố định của các System.out.println này.

### 5.8. Vì sao output như vậy?

1. **Inner proxy:** Spring tạo advisor từ TraceAspect và bọc GreetingService; AopUtils trả true.
2. **Outer proxy:** ProxyFactory tạo thêm một AOP proxy, có đúng một MethodInterceptor do ví dụ đăng ký.
3. **Hai proxy theo interface:** Cả inner và outer sử dụng JDK dynamic proxies, nhưng chiến lược JDK/CGLIB không quyết định số tầng.
4. **Outer wraps inner:** TargetSource của outer là SingletonTargetSource giữ chính instance inner.
5. **Inner wraps plain target:** TargetSource của inner là SingletonTargetSource giữ GreetingService gốc.
6. **Ultimate target:** AopProxyUtils lần qua singleton layers và xác định lớp đích GreetingService.
7. **Outer advisors: 1:** Chỉ đếm advisor gắn ở tầng outer. Lớp inner vẫn có advisor từ @Aspect.
8. **Đường gọi:** Outer nhận greet trước, in “outer: before”; proceed gọi inner, @Before trên inner in “inner aspect: before”; target in kết quả; inner trả về, outer in “outer: after”; cuối cùng Main in “result”.

Nếu trực tiếp gọi inner.greet("Lan"), outer interceptor không được kích hoạt. Nếu gọi thẳng GreetingService gốc mà không qua proxy thì cả outer và inner advice đều bị bỏ qua.

## 6. Xem advisors của từng tầng

Trong ví dụ, thay vì suy từ log, có thể in advisors/target sources riêng của outer và inner:

~~~java
// Snippet để bổ sung vào Main, không phải file độc lập.
if (outer instanceof Advised advisedOuter) {
    System.out.println("outer advisor count: "
        + advisedOuter.getAdvisors().length);
    System.out.println("outer source: "
        + advisedOuter.getTargetSource().getClass().getSimpleName());
}

if (inner instanceof Advised advisedInner) {
    System.out.println("inner advisor count: "
        + advisedInner.getAdvisors().length);
    System.out.println("inner source: "
        + advisedInner.getTargetSource().getClass().getSimpleName());
}
~~~

Con số advisor và tên class infrastructure của inner có thể khác theo Spring release hoặc các advisor bổ sung, vì vậy không hard-code chúng trong test nghiệp vụ.

**Một proxy có nhiều advisors**: outer.getAdvisors() có thể hiển thị nhiều phần tử, nhưng getSingletonTarget(outer) có thể là đối tượng nghiệp vụ thường.

**Nhiều proxy lồng nhau**: getSingletonTarget(outer) có thể là một AOP proxy khác; khi đó getAdvisors() của outer và inner cần được xem riêng.

Advised là interface của Spring AOP configuration, nhưng không phải mọi proxy đều expose interface này; proxy opaque có thể ẩn nó. Hãy dùng instanceof trước khi cast.

## 7. Lần theo singleton proxy chain an toàn

Spring cung cấp:

~~~java
Object next = AopProxyUtils.getSingletonTarget(proxy);
Class<?> deepType = AopProxyUtils.ultimateTargetClass(proxy);
~~~

getSingletonTarget chỉ trả immediate target khi proxy giữ một SingletonTargetSource. Nếu trả null, điều này **không chứng minh proxy không có target**: target source có thể thuộc loại dynamic hoặc object không phải AOP proxy dạng này.

Đoạn chẩn đoán an toàn hơn so với gọi getTarget() bừa bãi:

~~~java
// Các import cần thêm vào Main.java nếu dùng snippet này:
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;
import org.springframework.aop.framework.AopProxyUtils;
import org.springframework.aop.support.AopUtils;

static void traceSingletonChain(Object object) {
    Set<Object> seen =
        Collections.newSetFromMap(new IdentityHashMap<>());
    Object current = object;
    int depth = 0;

    while (current != null && seen.add(current)) {
        System.out.println("depth=" + depth
            + ", aopProxy=" + AopUtils.isAopProxy(current)
            + ", runtimeType=" + current.getClass().getName());

        Object next = AopProxyUtils.getSingletonTarget(current);
        if (next == null) {
            break;
        }
        current = next;
        depth++;
    }
}
~~~

Đây là **method snippet** để đặt trong một class với các import đã ghi, không phải một chương trình độc lập. Nó có thể nhận diện chuỗi singleton Spring AOP proxies mà không kích hoạt dynamic TargetSource.getTarget().

Dùng **identity-based** Set thay vì HashSet thông thường để tránh phụ thuộc vào equals/hashCode của proxy. Khi trace dừng tại một wrapper không phải Spring AOP hoặc một dynamic target source, hãy báo giới hạn thay vì kết luận “đây chắc chắn là target cuối cùng”.

## 8. TargetSource không phải lúc nào cũng là singleton

Spring AOP proxy có thể dùng những loại target source khác nhau:

| TargetSource | Đặc trưng | Rủi ro khi debug |
| --- | --- | --- |
| SingletonTargetSource | Giữ một đối tượng target | Có thể quan sát một lớp singleton bằng getSingletonTarget |
| PrototypeTargetSource | Có thể tạo/lấy target mới | Gọi getTarget() có thể tạo thêm instance không mong muốn |
| Scoped target source | Lấy target theo request/session/scope | Có thể không có scope hiện hành hoặc trả target khác nhau |
| Pooling target source | Mượn object từ pool | Có thể phải releaseTarget sau khi sử dụng |
| Lazy/hot-swappable target source | Target được tạo muộn hoặc thay thế | Trạng thái có thể thay đổi trong quá trình thực thi |

Vì vậy, **đừng** dùng đoạn sau như cách quan sát mặc định:

~~~java
Object target = ((Advised) proxy).getTargetSource().getTarget();
((GreetingPort) target).greet("Lan");
~~~

Nó có thể bỏ qua outer advice, tạo target mới, đòi scope đang active hoặc gây ảnh hưởng đến vòng đời target. Đặc biệt với resource/pool, việc không gọi releaseTarget theo hợp đồng có thể làm cạn resource. Business code nên tiếp tục sử dụng bean proxy do Spring cung cấp.

Để biết thông tin sơ bộ mà chưa lấy target:

~~~java
TargetSource source = ((Advised) proxy).getTargetSource();
Class<?> declaredTargetType = source.getTargetClass();
boolean constantTarget = source.isStatic();
~~~

Hai lời gọi này giúp nhận diện metadata; chúng không thay thế kiểm tra cấu hình bean thực tế.

## 9. Thứ tự advice, exception và kết thúc sớm

Cấu trúc outer/inner quyết định thứ tự đi **vào** các tầng. Với around-style interceptor:

~~~java
factory.addAdvice((MethodInterceptor) invocation -> {
    System.out.println("outer: begin");
    try {
        return invocation.proceed();
    } finally {
        System.out.println("outer: end");
    }
});
~~~

Đây là **phiên bản thay thế** interceptor trong Main.java, không dùng đồng thời với phiên bản đã viết nếu muốn so output cố định.

- Outer “begin” xuất hiện trước inner vì outer nhận lời gọi trước.
- Nếu inner trả về bình thường, outer thực thi finally rồi trả kết quả.
- Nếu inner/target ném exception, finally của outer vẫn thực thi.
- Nếu một outer around advice trả về giá trị mà **không** gọi proceed, inner/target có thể không chạy.
- Nếu inner có một cache advisor trả kết quả ngay tại tầng đó, target có thể không được gọi, nhưng outer vẫn có thể chạy before/after hoặc finally.

Phân biệt với @Order: sắp xếp advisors trong một proxy và thứ tự **các lớp proxy lồng nhau** không phải cùng một phép sắp xếp.

## 10. Những đường gọi bỏ qua một hoặc nhiều tầng

Giả sử ba tham chiếu tồn tại:

~~~java
GreetingPort outer = ...; // Outer AOP proxy
GreetingPort inner = ...; // Inner AOP proxy
GreetingPort plain = ...; // Target nghiệp vụ (ví dụ minh họa)
~~~

Kết quả:

| Caller gọi | Tầng được đi qua | Tác động |
| --- | --- | --- |
| outer.greet(...) | Outer → Inner → Target | Outer advice và inner @Aspect advice có cơ hội chạy |
| inner.greet(...) | Inner → Target | Không đi qua outer interceptor |
| plain.greet(...) | Target trực tiếp | Bỏ qua cả hai proxy |
| Target dùng this.someMethod() | Lời gọi trực tiếp trong target | Không tự quay lại inner/outer proxy |
| Outer around advice không proceed | Chỉ outer (hoặc các interceptor outer trước đó) | Inner/target không được gọi |

**Self-invocation** vẫn là một giới hạn của Spring AOP, cho dù proxy ngoài hoặc proxy trong là JDK hay CGLIB. Nested proxies không tự tạo ranh giới advice mới cho this.method() nằm bên trong target.

Đừng “unwrap” proxy rồi giữ plain target trong một field để tối ưu hiệu năng khi business behavior phụ thuộc vào transaction, cache, security hay tracing; hành động đó có thể làm mất các lời advice thiết yếu.

## 11. Các nguyên nhân hay dẫn tới nhiều wrapper trong ứng dụng Spring

Một vài trường hợp đáng điều tra:

1. Lập trình viên tạo ProxyFactory để bọc một Spring AOP bean đã có proxy.
2. Bean factory trả object vốn đã là proxy, sau đó một BeanPostProcessor khác bọc thêm.
3. Một framework tích hợp như Spring Data cung cấp repository proxy, đồng thời có thêm AOP advisor hoặc một proxy tùy biến.
4. Scoped proxy đi cùng transaction/cache/custom @Aspect và target source đặc biệt.
5. Một adapter/client wrapper ngoài Spring AOP nhận Spring AOP proxy làm target.
6. AOP infrastructure có nhiều advisor, khiến log **trông giống** nested nhưng thực tế chỉ một proxy.

Các tình huống 2–5 **không phải lúc nào cũng tạo hai tầng proxy riêng**. Spring có thể hợp nhất advisor/cấu hình hoặc sử dụng hạ tầng chung. Bởi vậy chỉ xác nhận nested khi bạn tìm thấy một proxy object có target source chứa **proxy khác**, không dựa vào số annotation hay số log.

## 12. Quy trình chẩn đoán Spring Aspect

### Bước 1: Bắt đầu từ object caller đang giữ

Đừng bắt đầu bằng class nguồn rồi giả định đó cũng là runtime class. Lấy reference từ dependency injection hoặc context, xác minh isAopProxy, isJdkDynamicProxy/isCglibProxy.

### Bước 2: Xem proxy ngoài

Nếu instanceof Advised, đọc getAdvisors, getTargetSource, getTargetClass và isStatic. Không sửa advisor runtime trên production chỉ để xem kết quả.

### Bước 3: Lần theo singleton targets, nếu có

Dùng AopProxyUtils.getSingletonTarget ở từng tầng; dừng khi trả null hoặc khi object không phải Spring AOP proxy tương thích. Có thể dùng ultimateTargetClass để lấy target type sâu nhất trong phạm vi hỗ trợ.

### Bước 4: Vẽ chuỗi object

Ghi rõ:

~~~text
caller -> outerProxy/advisor A -> innerProxy/advisor B -> realTarget
~~~

Hoặc:

~~~text
caller -> oneProxy/advisors A,B -> realTarget
~~~

Đây là hai sơ đồ khác nhau, kéo theo các chẩn đoán khác nhau.

### Bước 5: Theo dõi proceed/return

Log ở những điểm đầu/cuối interceptor. Xác định advice nào gọi proceed, advice nào có thể cache hit/short-circuit, exception được catch hay propagate.

### Bước 6: So với pointcut của @Aspect

Một proxy có tồn tại không có nghĩa mọi method đều khớp. Kiểm tra Spring-managed aspect bean, advisor đúng target/method, kiểu proxy, visibility và đường gọi qua proxy.

### Bước 7: Kiểm tra ranh giới bên ngoài và nội bộ

Có caller nào lấy inner thay outer, lấy plain target, tự new một object hoặc gọi this.method() bên trong target? Các cách gọi đó có thể tạo trace khác nhau dù method nghiệp vụ giống nhau.

### Bước 8: Kiểm thử với context thực tế

Integration test nên gọi từ tham chiếu Spring cấp cho caller, quan sát cả kết quả nghiệp vụ và advice; không chỉ dựa vào số dòng log của target.

## 13. Lỗi thường gặp

| Dấu hiệu | Kết luận vội | Kiểm tra đúng |
| --- | --- | --- |
| Có hai dòng before | Chắc chắn hai proxy | Có thể một proxy với hai advisors |
| Outer chỉ có một advisor | Không có advice ở trong | Phải kiểm tra inner riêng |
| isAopProxy trả true | Chắc chắn từ @Aspect của mình | Có thể proxy do transaction/cache/scope |
| getSingletonTarget trả null | Không có target | Có thể dynamic TargetSource hoặc proxy không phù hợp |
| ultimateTargetClass trả GreetingService | Proxy cast được về GreetingService | JDK proxy vẫn có thể chỉ triển khai GreetingPort |
| @Order không đảo outer và inner | Spring lỗi ordering | Các tầng vật lý khác với advisor order trong một proxy |
| Gọi trực tiếp target mất tracing | Aspect không tồn tại | Đường gọi đã bỏ qua proxy |
| Scoped proxy getTarget thất bại | Bean mất | Có thể scope đang không active |
| Hai lần log một advice | Chắc chắn do nested proxies | Có thể đăng ký aspect bean trùng, nhiều advisor hoặc gọi method hai lần |
| Target không được gọi | Proxy lỗi | Có thể một around advice trả sớm hoặc cache hit |

## 14. Câu hỏi vận dụng

**Câu 1.** Một AOP proxy có ba advisors. Có chắc chắn ba tầng proxy?

**Trả lời:** Không. Có thể cả ba advisors nằm trên đúng một proxy.

**Câu 2.** Outer có một advisor, immediate singleton target của outer là một Spring AOP proxy khác. Có thể kết luận gì?

**Trả lời:** Có ít nhất hai tầng AOP proxy trong chuỗi singleton này. Cần xem advisors/target source của inner để hiểu tiếp.

**Câu 3.** Vì sao outer.getAdvisors() không thấy advice do @Aspect của inner tạo ra?

**Trả lời:** Nó chỉ liệt kê advisors thuộc cấu hình outer, không tự gộp inner advisors.

**Câu 4.** Nếu caller đổi từ outer.greet() sang inner.greet() thì outer advice có chạy không?

**Trả lời:** Không, vì lời gọi bỏ qua outer proxy. Inner advice có thể vẫn chạy.

**Câu 5.** Có nên gọi getTarget() nhiều lần để bóc scoped proxy trong môi trường production?

**Trả lời:** Không. Target source có thể động, phụ thuộc scope và có hợp đồng release/lifecycle. Hãy quan sát metadata hoặc dùng helper singleton khi an toàn.

**Câu 6.** Outer around interceptor không gọi proceed. Có bắt buộc inner và target nhận lời gọi không?

**Trả lời:** Không. Interceptor ngoài có thể short-circuit toàn bộ đường gọi.

## 15. Tài liệu nguồn chính thức

- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB proxies, proxy boundary và self-invocation.
- [Spring Framework — Creating AOP Proxies Programmatically](https://docs.spring.io/spring-framework/reference/core/aop-api/prog.html): ProxyFactory, addAdvice, addAdvisor, getProxy.
- [Spring Framework — Manipulating Advised Objects](https://docs.spring.io/spring-framework/reference/core/aop-api/advised.html): quan sát advisors và cấu hình proxy.
- [Spring Framework — TargetSource Implementations](https://docs.spring.io/spring-framework/reference/core/aop-api/targetsource.html): singleton/dynamic target sources.
- [Spring Javadoc — AopProxyUtils](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/aop/framework/AopProxyUtils.html): getSingletonTarget và ultimateTargetClass.
- [Spring Javadoc — Advised](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/aop/framework/Advised.html): getAdvisors và getTargetSource.
- [Spring Javadoc — AopUtils](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/aop/support/AopUtils.html): cách nhận diện AOP proxy và target class.

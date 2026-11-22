# Vai trò của BeanPostProcessor trong việc bọc Spring bean bằng AOP proxy

## 1. Câu hỏi trung tâm

Khi khai báo một aspect bằng `@Aspect`, bật `@EnableAspectJAutoProxy` và lấy service qua `ApplicationContext`, tại sao service nhận được có thể là một **proxy** thay vì đối tượng gốc? Cơ chế nối Spring IoC với Spring AOP chính là **BeanPostProcessor**.

Trong Spring, `BeanPostProcessor` (BPP) là điểm mở rộng cho phép container xử lý **instance của bean** trong quá trình tạo bean. Một BPP có thể trả lại đối tượng đã nhận hoặc trả về một đối tượng khác — chẳng hạn proxy — để container sử dụng làm bean được cung cấp cho các caller khác. Hạ tầng **auto-proxy creator** của Spring AOP triển khai cơ chế đó: nó tìm advisor/advice phù hợp và thay instance được xuất ra ngoài bằng AOP proxy khi cần.

Phạm vi ở đây là cách Spring thực hiện auto-proxying và ý nghĩa của `BeanPostProcessor` trong Spring AOP. Nội dung tập trung vào Spring bean, advisor, proxy và thời điểm xử lý; không trình bày lại lý thuyết AspectJ weaving độc lập.

## 2. BeanPostProcessor can thiệp ở thời điểm nào?

Giao diện tối thiểu:

~~~java
package org.springframework.beans.factory.config;

public interface BeanPostProcessor {
    default Object postProcessBeforeInitialization(Object bean, String beanName)
            throws org.springframework.beans.BeansException {
        return bean;
    }

    default Object postProcessAfterInitialization(Object bean, String beanName)
            throws org.springframework.beans.BeansException {
        return bean;
    }
}
~~~

Đoạn trên là **minh họa hai callback quan trọng**, không phải mã nguồn sao chép nguyên bản của Spring và không phải tệp cần đưa vào project. Spring cung cấp sẵn giao diện này. Từng callback có thể trả cùng instance hoặc một instance thay thế; không phải mọi BPP đều tạo proxy.

Ở luồng tạo bean thông thường, Spring thực hiện gần như sau:

~~~text
BeanDefinition đã được đăng ký trong BeanFactory
        |
        v
Tạo instance target (constructor / factory method)
        |
        v
Populate dependencies / properties
        |
        v
BeanPostProcessor.postProcessBeforeInitialization(...)
        |
        v
Khởi tạo bean: @PostConstruct, InitializingBean, init method
        |
        v
BeanPostProcessor.postProcessAfterInitialization(...)
        |
        |-- không cần advice --> trả bean ban đầu
        |
        +-- có advisor phù hợp --> trả AOP proxy bọc target
                                      |
                                      v
                     Container lưu / cung cấp bean reference
                                      |
                                      v
                        Caller -> proxy -> advice -> target
~~~

Đây là **mô hình chuẩn đã đơn giản hóa**, không phải khẳng định mọi bean luôn trải qua mọi nhánh theo cùng cách. Spring có các kiểu `InstantiationAwareBeanPostProcessor` và `SmartInstantiationAwareBeanPostProcessor` hỗ trợ hook sớm; `FactoryBean`, lazy bean và dependency cycle có thể khiến đường đi thực tế khác sơ đồ. Với bài cơ bản, hãy nhớ rằng **Spring AOP thường tạo proxy khi xử lý bean lúc kết thúc giai đoạn khởi tạo**, trước khi caller bình thường nhận reference đó.

Các điểm dễ nhầm:

- `BeanPostProcessor` xử lý **đối tượng bean đã được tạo**. `BeanFactoryPostProcessor`/`BeanDefinitionRegistryPostProcessor` xử lý cấu hình/định nghĩa bean trước giai đoạn tạo instance. Hệ thống auto-proxy có bước đăng ký định nghĩa hạ tầng, nhưng thao tác **bọc instance bằng proxy** xảy ra ở BPP.
- Callback `postProcessBeforeInitialization` thường phù hợp để xử lý trước init. Auto-proxy creator của Spring AOP chủ yếu dùng `postProcessAfterInitialization` để trả về proxy khi xác định bean cần advice.
- Khi một BPP trả về proxy, bean trong container được tiêu thụ bằng **reference proxy**; target thường vẫn là đối tượng khác mà proxy ủy quyền đến. Do đó `service.getClass()` có thể là lớp proxy, và `service == target` không phải giả định an toàn.
- Trả `null` từ một callback BPP không có nghĩa “bỏ qua bean”; trong quy trình xử lý BPP của Spring, việc này có thể làm dừng chuỗi processor tại giai đoạn ấy. Trong BPP tùy biến, thông thường **trả lại `bean`** nếu không cần thay đổi.

## 3. Auto-proxy creator: BeanPostProcessor chuyên dụng của Spring AOP

Với cấu hình `@EnableAspectJAutoProxy`, Spring đăng ký hạ tầng auto-proxy creator. Một triển khai quan trọng là `org.springframework.aop.aspectj.annotation.AnnotationAwareAspectJAutoProxyCreator`, kế thừa nhánh `AbstractAutoProxyCreator` và triển khai giao diện `SmartInstantiationAwareBeanPostProcessor` (bản mở rộng của `BeanPostProcessor`).

Trong Spring AOP sử dụng kiểu khai báo `@AspectJ`, auto-proxy creator thực hiện các nhiệm vụ:

1. **Nhận diện aspect/advisor:** lấy các Spring `Advisor` và chuyển các advice khai báo bằng `@Aspect`, `@Before`, `@Around`… từ aspect bean thành advisor mà Spring AOP có thể sử dụng.
2. **Xác định bean cần proxy:** xét từng bean đủ điều kiện, so khớp candidate advisor/pointcut với kiểu bean và các method join point Spring AOP hỗ trợ. Một bean không có advisor áp dụng thì thường được giữ nguyên.
3. **Bỏ qua lớp hạ tầng:** tránh proxy hóa các thành phần AOP nội bộ, advisor/advice/aspect không phù hợp hoặc bean bị loại theo quy tắc xử lý. Không phải cứ có `@EnableAspectJAutoProxy` là **mọi** bean đều được bọc.
4. **Tạo proxy với advisor thích hợp:** sử dụng cơ chế proxy của Spring (JDK dynamic proxy hoặc CGLIB class proxy, tùy cấu hình và kiểu đích). Proxy chứa cách điều phối advice cho lời gọi method.
5. **Trả về proxy thay target** qua đường đi của BeanPostProcessor (thường là `postProcessAfterInitialization`). Spring container và dependency injection sẽ cung cấp reference đã qua xử lý cho các bean khác.

### Chuỗi lớp có ích khi đọc mã nguồn Spring

~~~text
BeanPostProcessor
        ^
SmartInstantiationAwareBeanPostProcessor
        ^
AbstractAutoProxyCreator
        ^
AbstractAdvisorAutoProxyCreator
        ^
AspectJAwareAdvisorAutoProxyCreator
        ^
AnnotationAwareAspectJAutoProxyCreator
~~~

Mũi tên thể hiện quan hệ mở rộng/triển khai phục vụ giải thích kiến trúc; `AnnotationAwareAspectJAutoProxyCreator` là lớp Spring hỗ trợ kiểu aspect `@AspectJ`. Từ góc nhìn method nội bộ, hãy chú ý:

- `AbstractAutoProxyCreator.postProcessAfterInitialization(...)`: điểm xử lý hậu khởi tạo, có thể bọc một bean bằng proxy.
- `wrapIfNecessary(...)`: xem xét bean có cần tạo proxy hay không.
- `getAdvicesAndAdvisorsForBean(...)` và các phương thức tìm advisor trong nhánh `AbstractAdvisorAutoProxyCreator`: chọn advice/advisor có thể áp dụng.
- `createProxy(...)`: tạo AOP proxy với cấu hình và advisor đã chọn.
- `getEarlyBeanReference(...)`: đường xử lý tham chiếu sớm cho một số tình huống vòng phụ thuộc; xem phần lưu ý bên dưới.

Tên các method này phục vụ **đọc hiểu/debug framework**, không phải API mà ứng dụng bình thường cần gọi hoặc override. Không nên tự kế thừa `AbstractAutoProxyCreator` chỉ để bật một `@Before` advice đơn giản.

## 4. Từ @EnableAspectJAutoProxy đến lời gọi runtime

Đăng ký cấu hình:

~~~java
@Configuration
@EnableAspectJAutoProxy
class AopConfig {
}
~~~

Trong Java configuration, `@EnableAspectJAutoProxy` dùng cơ chế import/registrar của Spring để đăng ký auto-proxy creator. Khi container chuẩn bị BeanPostProcessor, auto-proxy creator được quản lý như một processor chuyên dụng. Aspect cũng phải có trong `ApplicationContext` dưới dạng bean, ví dụ `@Component` (với component scanning) hoặc `@Bean`. **Chỉ thêm `@Aspect` vào một class thường không tự đăng ký bean.**

Sau đó:

~~~text
@EnableAspectJAutoProxy
   |
   +--> đăng ký auto-proxy creator trong Spring context
                      |
       bean checkoutService được khởi tạo
                      |
                      v
          BeanPostProcessor chain
                      |
                      v
          Xét các Advisor phù hợp
                      |
                  +---+---+
                  |       |
                Có       Không
                  |       |
               Proxy     Target gốc
                  |
               Container trao proxy cho caller
                  |
             caller.checkout()
                  |
              interceptor chain
                  |
              @Before advice
                  |
              target.checkout()
~~~

Cần tách hai **thời điểm**:

- **Lúc tạo bean:** BPP quyết định tạo wrapper nào để Spring cung cấp cho caller.
- **Lúc gọi method qua proxy:** interceptor/advice trong wrapper được thực thi ở các join point khớp. BPP **không cần chạy lại mỗi lần method được gọi**. Nếu một singleton service được gọi 1.000 lần, không suy ra BPP cũng bọc service lại 1.000 lần.

Proxy từ Spring AOP không biến bytecode service thành code advice theo AspectJ weaving; method invocation đi qua đối tượng proxy. Điều này giải thích vì sao `this.otherMethod()` gọi trực tiếp trên target có thể bỏ qua advice trên method nội bộ.

## 5. Project Java 17+ quan sát BeanPostProcessor và proxy

Ví dụ chạy độc lập bằng **Spring Framework 6.2.0, AspectJ Weaver 1.9.22, Maven và Java 17+**. Dự án chỉ khởi tạo một `ApplicationContext`, không dùng Spring Boot và không bật weaving.

Cấu trúc:

~~~text
spring-auto-proxy-bpp/
├── pom.xml
└── src/main/java/example/
    ├── App.java
    ├── CheckoutService.java
    └── AuditAspect.java
~~~

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-auto-proxy-bpp</artifactId>
    <version>1.0-SNAPSHOT</version>
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
                <configuration>
                    <mainClass>example.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` chứa lifecycle/container, `spring-aop` chứa hạ tầng AOP/proxy và `AopUtils`. `aspectjweaver` cung cấp các kiểu AspectJ dùng để phân tích pointcut `@AspectJ` trong Spring AOP. **Dependency này không tự kích hoạt AspectJ bytecode weaving.**

### 5.1. CheckoutService có bước init rõ ràng

Tạo `src/main/java/example/CheckoutService.java`:

~~~java
package example;

import org.springframework.beans.factory.InitializingBean;

public class CheckoutService implements InitializingBean {
    @Override
    public void afterPropertiesSet() {
        System.out.println("INIT: checkoutService");
    }

    public void checkout() {
        System.out.println("TARGET: checkout");
    }
}
~~~

`afterPropertiesSet()` là lifecycle callback sau khi dependency/properties đã được gắn vào bean. Dòng `INIT` giúp nhìn thấy ranh giới giữa các giai đoạn BeanPostProcessor. `checkout()` là business method sẽ được advice, không phải method init.

### 5.2. Aspect sẽ chạy khi gọi checkout qua proxy

Tạo `src/main/java/example/AuditAspect.java`:

~~~java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    @Before("execution(* example.CheckoutService.checkout(..))")
    public void beforeCheckout() {
        System.out.println("ADVICE: before checkout");
    }
}
~~~

Spring dùng `@Aspect`/`@Before` để tạo advisor. `execution(* example.CheckoutService.checkout(..))` khớp **method execution** của `checkout`. Aspect chỉ chạy khi method qua Spring AOP proxy khớp advisor đó; không phải vì BeanPostProcessor quan sát tự gọi advice.

### 5.3. Cấu hình hai loại BeanPostProcessor khác nhau

Tạo `src/main/java/example/App.java`:

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class App {
    @Bean
    public CheckoutService checkoutService() {
        return new CheckoutService();
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }

    @Bean
    public static BeanPostProcessor lifecycleObserver() {
        return new BeanPostProcessor() {
            @Override
            public Object postProcessBeforeInitialization(
                    Object bean, String beanName) {
                if ("checkoutService".equals(beanName)) {
                    System.out.println("BPP_BEFORE: checkoutService");
                }
                return bean;
            }

            @Override
            public Object postProcessAfterInitialization(
                    Object bean, String beanName) {
                if ("checkoutService".equals(beanName)) {
                    System.out.println("BPP_AFTER: checkoutService");
                }
                return bean;
            }
        };
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            CheckoutService service = context.getBean(CheckoutService.class);
            System.out.println("PROXY: " + AopUtils.isAopProxy(service));
            service.checkout();
        }
    }
}
~~~

Trong cùng một `ApplicationContext` có hai loại processor với vai trò **khác nhau**:

1. `lifecycleObserver()` trả về **BPP do ta viết** để in dấu mốc lifecycle. Nó trả nguyên `bean` ở cả hai callback, **không tự tạo proxy**. Vì Spring `ApplicationContext` phát hiện bean `BeanPostProcessor` và gọi nó trong quá trình tạo những bean phù hợp, observer nhìn thấy quá trình khởi tạo `checkoutService`.
2. `@EnableAspectJAutoProxy` đăng ký **auto-proxy creator nội bộ của Spring**, cũng là BeanPostProcessor. Processor này tìm advisor sinh từ `AuditAspect` và bọc `CheckoutService` bằng AOP proxy khi có method phù hợp.

Đặt `@Bean` của BPP tùy biến ở dạng **`public static`, không có dependency** để Spring phát hiện/đăng ký sớm mà không phải tạo instance configuration class trước hạn. Đây là thực hành quan trọng: các BPP cần hoạt động đủ sớm để xử lý các bean được tạo sau chúng. Khai báo BPP bằng `@Bean` có return type `BeanPostProcessor` (hoặc lớp triển khai) giúp container nhận diện đúng.

Trong ví dụ, `proxyTargetClass = true` chọn **class-based proxy** (CGLIB), nên `context.getBean(CheckoutService.class)` trả kiểu có thể gán cho `CheckoutService`. Thuộc tính `proxyBeanMethods = false` trên `@Configuration` chỉ quyết định cách xử lý các phương thức `@Bean` của configuration class; nó **không vô hiệu hóa auto-proxy AOP**.

### 5.4. Chạy và giải thích stdout

Trong thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng mà chương trình tạo ra:

~~~text
BPP_BEFORE: checkoutService
INIT: checkoutService
BPP_AFTER: checkoutService
PROXY: true
ADVICE: before checkout
TARGET: checkout
~~~

Các thông điệp Maven/logger khác, nếu có, không thuộc sáu dòng từ mã ví dụ. Thứ tự trên phản ánh lifecycle của `CheckoutService` ở project đã cho:

- `BPP_BEFORE`: callback `postProcessBeforeInitialization` của observer chạy trước `afterPropertiesSet()`.
- `INIT`: Spring thực hiện initialization callback của service.
- `BPP_AFTER`: callback `postProcessAfterInitialization` của observer chạy sau initialization callback. **Dòng này không tự chứng minh bean đã được bọc**: observer chỉ in tên bean và trả về đối tượng được nhận.
- `PROXY: true`: reference Spring đưa cho caller là Spring AOP proxy, được tạo bởi auto-proxy creator nội bộ nếu phù hợp advisor.
- `ADVICE` trước `TARGET`: lời gọi đi qua proxy, kích hoạt `@Before` rồi chuyển tiếp tới `checkout()` của service.

Chú ý: **không kết luận kiểu của đối tượng trong từng BPP callback chỉ từ tên log**. Các BeanPostProcessor có thứ tự xử lý khác nhau; một BPP tùy biến có thể quan sát target hoặc wrapper tùy thời điểm và thứ tự thực thi. `AopUtils.isAopProxy(context.getBean(...))` trong `main` đo trực tiếp **reference cuối cùng** Spring cung cấp cho caller.

## 6. Vì sao việc “bọc bằng proxy” làm thay đổi hành vi của caller?

Khi auto-proxy creator thấy advisor áp dụng được, về ý tưởng nó trả một wrapper:

~~~text
Trước auto-proxying:
caller --> CheckoutService.checkout()

Sau auto-proxying:
caller --> CheckoutServiceProxy.checkout()
                 |
                 +--> AuditAspect.beforeCheckout()
                 |
                 +--> CheckoutService.checkout()
~~~

Không cần sửa class `CheckoutService` để chèn lệnh gọi `AuditAspect.beforeCheckout()`. Các bean khác trong Spring được inject service thông thường sẽ nhận reference mà container công bố, tức proxy nếu đã được tạo.

Các hệ quả quan trọng:

- **Không phải mọi bean đều là proxy:** nếu pointcut không khớp hoặc không có advisor áp dụng, auto-proxy creator có thể trả target. `@EnableAspectJAutoProxy` chỉ bật cơ chế xét/proxy.
- **Không phải mọi lời gọi đều qua proxy:** `this.checkout()` bên trong target là self-invocation; lời gọi nội bộ có thể bỏ qua advice. Tách responsibility sang bean khác để gọi qua Spring reference là cách xử lý thường dễ hiểu.
- **Không phải mọi method đều intercept được:** class-based proxy không override được `final`/`private` method hoặc `final` class. Với JDK proxy, caller tương tác qua interface proxy; lựa chọn kiểu proxy có ảnh hưởng trực tiếp đến method nào được expose.
- **Initialization không phải invocation business qua proxy:** các callback init thường chạy trên target trong quá trình tạo bean trước khi bean proxy cuối cùng được công bố; đừng xem việc `@Before` không chạy cho method gọi ở init là bằng chứng Spring AOP không hoạt động.
- **Không phải AOP weaving:** Spring tạo đối tượng proxy; AspectJ compile/load-time weaving sửa bytecode theo công cụ riêng. Cú pháp `@Aspect`/`@Before` không biến Spring auto-proxy thành weaving.

## 7. Những trường hợp BPP không áp dụng như mong đợi

### 7.1. BPP được đăng ký quá muộn hoặc tạo phụ thuộc sớm

`ApplicationContext` chủ động tìm và khởi tạo BPP trong giai đoạn đặc biệt trước khi nhiều bean thông thường được tạo. Bản thân các BPP, cùng các bean được chúng kéo vào khởi tạo quá sớm, **không thể mặc định hưởng toàn bộ chuỗi BPP** và có thể không đủ điều kiện auto-proxying. Spring có cảnh báo dạng:

~~~text
Bean '...' is not eligible for getting processed by all BeanPostProcessors
(for example: not eligible for auto-proxying)
~~~

Nếu gặp cảnh báo này:

1. Kiểm tra BPP do ứng dụng tự khai báo có được tạo **sớm** qua static `@Bean` và return type nhận diện được là BPP hay không.
2. Tránh inject dịch vụ nghiệp vụ nặng hoặc tạo graph phụ thuộc lớn trong chính constructor/factory method của BPP; các dependency đó có thể bị khởi tạo trước khi auto-proxy creator sẵn sàng.
3. Không tự gọi `getBean()` để khởi tạo hàng loạt service trong lúc đăng ký BPP. Hãy để container hoàn thành đúng pha khởi tạo.

Không cố advice chính một `BeanPostProcessor` và kết luận Spring AOP hỏng khi nó không nhận proxy như business bean bình thường.

### 7.2. Proxy xuất hiện sớm để hỗ trợ circular references

`AbstractAutoProxyCreator` là `SmartInstantiationAwareBeanPostProcessor` và có `getEarlyBeanReference(...)` để Spring có thể cấp **reference đã bọc** sớm ở một số đường xử lý phụ thuộc vòng. Điều này giúp tránh chuyện một bean nhận target thô trong khi caller khác sau đó nhận proxy.

Tuy vậy, **không dựa vào circular dependencies như một pattern thiết kế**. Constructor cycle thường không giải được theo cách này; trong Spring Boot nhiều cấu hình còn từ chối circular references theo mặc định. Refactor vòng phụ thuộc là giải pháp bền vững. Đừng hiểu rằng BPP luôn được gọi đúng một lần trên mọi bean hoặc việc gọi callback sớm luôn thành công.

### 7.3. Nhiều context và nhiều auto-proxy setting

BPP có phạm vi theo **container**. BPP đăng ký trong một `ApplicationContext` không tự trở thành post-processor cho mọi bean thuộc một context khác, đặc biệt trong mô hình parent/child. Khi advice không chạy ở bean được tạo bởi context con, kiểm tra auto-proxy creator và aspect có được đăng ký trong đúng context chứa bean hay không.

Các khai báo auto-proxy AOP/transaction có thể được Spring hợp nhất về một auto-proxy creator và áp dụng thiết lập proxy mạnh hơn khi cấu hình chồng nhau. Không suy diễn rằng hai annotation đồng nghĩa chắc chắn có hai lớp proxy độc lập. Kiểm tra proxy thực tế qua `AopUtils.isAopProxy(...)` và các advisor nếu cần.

### 7.4. Tự viết BPP để tạo proxy cho mọi bean

Đừng thay `AnnotationAwareAspectJAutoProxyCreator` bằng một BPP tùy biến chỉ để làm logging hoặc method advice thông thường. Việc tự tạo proxy trùng lặp dễ gây double wrapping, thay đổi thứ tự advice, rối lifecycle và làm sai hành vi của transaction/cache. Khi mục tiêu là Spring AOP, hãy khai báo `@Aspect`/advisor và để hạ tầng Spring đảm nhiệm proxy creation.

## 8. Phân biệt nhanh các thành phần liên quan

| Thành phần | Nó xử lý gì? | Vai trò trong Spring AOP |
| --- | --- | --- |
| `BeanDefinitionRegistryPostProcessor` | Registry/định nghĩa bean | Có thể tham gia đăng ký thêm bean definition trước khởi tạo |
| `BeanFactoryPostProcessor` | Cấu hình/metadata của BeanFactory | Chỉnh định nghĩa; không phải bước bọc từng instance bằng proxy |
| `BeanPostProcessor` | Instance của bean quanh các callback init | Điểm mở rộng cho phép trả wrapper/proxy thay bean |
| `SmartInstantiationAwareBeanPostProcessor` | Thêm hook sớm vào quá trình tạo instance | Cho auto-proxy creator khả năng cung cấp proxy reference sớm trong một số trường hợp |
| `AnnotationAwareAspectJAutoProxyCreator` | Bean phù hợp với Advisor/`@AspectJ` | BPP cụ thể tìm advisor, chọn bean và tạo AOP proxy |
| `Advisor` / `Pointcut` / `Advice` | Điều kiện chọn join point và thao tác thực thi | Được auto-proxy creator đưa vào interceptor chain của proxy |
| JDK dynamic proxy / CGLIB | Wrapper runtime | Cơ chế thực thi lời gọi phương thức qua proxy |
| `@EnableAspectJAutoProxy` | Cấu hình bật hỗ trợ AOP kiểu `@AspectJ` | Đăng ký hạ tầng auto-proxy cho context đang cấu hình |

## 9. Chẩn đoán khi service không nhận AOP proxy

Một thứ tự kiểm tra thực tế:

1. **Có đúng bean Spring không?** `new CheckoutService()` không tự đi qua `BeanPostProcessor` của container. Lấy bean từ context đang sở hữu service.
2. **Auto-proxy creator có bật chưa?** Xác nhận `@EnableAspectJAutoProxy` nằm trong configuration đã nạp hoặc Boot AOP auto-configuration đang hoạt động.
3. **Aspect có là bean không?** `@Aspect` không đủ nếu Spring không đăng ký class aspect dưới dạng bean.
4. **Advisor có khớp method không?** Pointcut `execution(...)` phải khớp kiểu và chữ ký của method thực tế. Không khớp thì service có thể được giữ nguyên, không nhất thiết có proxy.
5. **BPP có bị khởi tạo quá muộn không?** Tìm log “not eligible for auto-proxying”, BPP khai báo qua non-static `@Bean` hoặc BPP inject quá nhiều service sớm.
6. **Lời gọi có đi qua proxy không?** Proxy tồn tại nhưng self-invocation hoặc object ngoài container sẽ không kích hoạt advice như lời gọi xuyên bean.
7. **Loại proxy có phù hợp không?** Xem interface/JDK proxy, CGLIB class proxy, `final` class/method, visibility và kiểu bean cần inject.
8. **Có chồng nhiều BPP/proxy/contexts không?** Kiểm tra nơi định nghĩa aspect, advisor và thứ tự BPP. BPP tùy biến cần trả đúng object nhận vào hoặc wrapper hợp lệ.

Để kiểm tra nhanh trong một ứng dụng đã có Spring container:

~~~java
Object bean = context.getBean("checkoutService");
System.out.println(org.springframework.aop.support.AopUtils.isAopProxy(bean));
System.out.println(org.springframework.aop.support.AopUtils.isJdkDynamicProxy(bean));
System.out.println(org.springframework.aop.support.AopUtils.isCglibProxy(bean));
~~~

Đây là **đoạn chèn vào chương trình đang có biến `context`**, không phải file Java độc lập; với ví dụ phần 5, nó trả `true`, `false`, `true` theo thứ tự nếu class-based proxy được cấu hình như đã nêu. Nếu `isAopProxy` là `false`, hãy kiểm tra cả điều kiện proxy/advisor trước khi quy lỗi do BPP.

## 10. Tự kiểm tra hiểu bài

1. **BeanPostProcessor thay đổi cái gì?** — Nó xử lý instance bean; có thể trả wrapper thay instance gốc sau khởi tạo.
2. **Spring AOP dựa vào BPP nào để tự động tạo proxy cho `@AspectJ`?** — Nhóm auto-proxy creator, tiêu biểu `AnnotationAwareAspectJAutoProxyCreator`.
3. **`@EnableAspectJAutoProxy` làm mọi bean thành proxy?** — Không. Bean cần phù hợp với advisor và cơ chế proxy.
4. **Vì sao `BPP_AFTER` không tương đương `ADVICE`?** — BPP chạy trong vòng đời tạo bean, còn advice chạy khi một method qua proxy khớp pointcut.
5. **Vì sao `@Bean static BeanPostProcessor` quan trọng?** — Giúp Spring phát hiện, khởi tạo BPP đủ sớm mà hạn chế tạo sớm configuration/dependencies.
6. **Đã có proxy sao `this.checkout()` có thể không chạy advice?** — Lời gọi nội bộ bỏ qua wrapper Spring AOP.
7. **Khi nào nên tránh sửa lõi auto-proxy creator?** — Khi yêu cầu chỉ là logging/audit/transaction thông thường, hãy dùng aspect/advisor chuẩn và để Spring quản lý proxy.

## Tài liệu Spring Framework để tra cứu

- [Container Extension Points — BeanPostProcessor](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-extension.html): lifecycle BPP và các lưu ý auto-proxy eligibility.
- [Using the auto-proxy facility](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/autoproxy.html): các auto-proxy creator trong Spring AOP.
- [Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): cách bật auto-proxy cho aspect.
- [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK proxy, CGLIB và giới hạn self-invocation.
- [AnnotationAwareAspectJAutoProxyCreator API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aop/aspectj/annotation/AnnotationAwareAspectJAutoProxyCreator.html) và [AbstractAutoProxyCreator API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aop/framework/autoproxy/AbstractAutoProxyCreator.html): lớp/callback hạ tầng.

# Phân biệt proxy AOP với proxy do cơ chế khác trong Spring tạo ra

## 1. Vì sao không nên kết luận “có proxy là có `@Aspect`”?

Spring Framework sử dụng cơ chế **ủy quyền và tăng cường hành vi** ở nhiều nơi. Khi debug một Spring bean, bạn có thể thấy class sinh động chứa `$$SpringCGLIB$$`, một JDK dynamic proxy hoặc một instance trả về `true` khi gọi `AopUtils.isAopProxy(...)`. Các quan sát ấy **không tự chứng minh** rằng bean đang chạy advice từ `@Aspect` do ứng dụng viết.

Trong chủ đề **Cơ chế Auto-proxy**, bài này trả lời bốn câu hỏi cụ thể:

1. Proxy của **Spring AOP** dùng advisor/advice để chặn phương thức khác gì proxy hỗ trợ **scope** và proxy do các tiện ích khác tạo ra?
2. Vì sao `@Transactional`, `@Cacheable` và `@Async` cũng có thể dùng hạ tầng AOP dù ứng dụng không viết một lớp `@Aspect` nào?
3. Vì sao class `@Configuration` được Spring **CGLIB-enhance** không đồng nghĩa với việc nó là Spring AOP proxy?
4. Dựa trên API nào để xác minh **loại proxy, advisor, target và hành vi thực tế** thay vì chỉ đoán từ tên class?

Phạm vi tập trung vào **Spring Framework/Spring Boot và Spring AOP proxy-based**; không trình bày lại lý thuyết Aspect tổng quát.

## 2. Tách ba trục để nhận diện đúng proxy

Một proxy nên được phân loại theo **ai tạo**, **mục đích** và **hạ tầng kỹ thuật**. Ba điều này có quan hệ nhưng không đồng nhất.

| Trục | Câu hỏi cần hỏi | Ví dụ |
| --- | --- | --- |
| Nguồn gốc | BeanPostProcessor/FactoryBean/cơ chế nào tạo hoặc tăng cường instance? | Spring AOP auto-proxy creator, `ScopedProxyFactoryBean`, `ConfigurationClassEnhancer`, Spring Data repository factory |
| Mục đích | Proxy giải quyết chức năng gì? | Gọi `@Before`, mở transaction, cache kết quả, tìm target đúng scope, giữ ngữ nghĩa gọi `@Bean` |
| Công nghệ | Wrapper được tạo bằng cách nào? | JDK dynamic proxy, CGLIB subclass, bytecode enhancement, interface adapter |
 
Cả Spring AOP lẫn scoped proxy có thể sử dụng cùng **hạ tầng `spring-aop`** và cùng công nghệ JDK/CGLIB. Ngược lại, `@Configuration` cũng dùng CGLIB nhưng phục vụ một cơ chế riêng. Vì vậy không thể phân loại chỉ bằng chữ `CGLIB` hoặc `Proxy` trong tên class.

### 2.1. Hiểu đúng cụm từ “proxy AOP”

Cụm từ này có hai mức độ:

- **Spring AOP proxy về kỹ thuật:** object tạo bởi hạ tầng Spring AOP, có marker `SpringProxy`; có thể phát hiện bằng `AopUtils.isAopProxy(object)`. Nó có thể phục vụ advisor nghiệp vụ, transaction/cache, **hoặc scoped delegation**.
- **Proxy có advice từ `@Aspect` cụ thể:** hẹp hơn. Cần chứng minh advisor của aspect đó được gắn vào proxy và lời gọi phương thức **khớp pointcut** nên advice thực sự chạy.

Do đó **`isAopProxy == true` không đồng nghĩa “advice của tôi đang chạy”**, và **`isAopProxy == false` không đồng nghĩa object không được tăng cường bằng cách khác**.

## 3. So sánh các cơ chế phổ biến trong Spring

| Trường hợp | Ai tạo/cấu hình hành vi | Thường dùng Spring AOP proxy? | Có cần `@Aspect` tự viết? | Ý nghĩa quan trọng |
| --- | --- | --- | --- | --- |
| `@Aspect` + `@EnableAspectJAutoProxy` | Spring AOP auto-proxy creator chọn advisors từ aspect bean | **Có** | Có, nếu chính bạn định nghĩa advice dạng `@AspectJ` | Phương thức trên target bean nhận advice khi gọi qua proxy và pointcut khớp |
| `@Transactional` với `@EnableTransactionManagement(mode = PROXY)` | Transaction advisor + `TransactionInterceptor` | **Có** | **Không** | Proxy điều phối transaction quanh method khớp metadata |
| `@Cacheable` với `@EnableCaching(mode = PROXY)` | Cache advisor + interceptor của cache abstraction | **Có** | **Không** | Proxy kiểm tra/lưu cache, có thể bỏ qua việc chạy target ở cache hit |
| `@Async` với `@EnableAsync` | Async annotation processing/advisor | Thường **có** ở chế độ proxy; chi tiết tích hợp có thể tùy phiên bản | **Không** | Chuyển lời gọi phù hợp sang executor, chịu giới hạn proxy |
| `@Scope(proxyMode = TARGET_CLASS)` hoặc `<aop:scoped-proxy/>` | Scoped proxy factory/target source | **Có thể nhận diện bằng `AopUtils`** vì dùng hạ tầng Spring AOP | **Không** | Tra cứu target đúng scope vào thời điểm gọi |
| `@Configuration(proxyBeanMethods = true)` | Spring `ConfigurationClassEnhancer` | **Không mặc nhiên** | **Không** | CGLIB subclass giúp lời gọi `@Bean` được điều phối qua container |
| `@Lookup` method injection | Spring bean method override/subclass enhancement | **Không mặc nhiên** | **Không** | Thay thế lời gọi method lookup bằng truy xuất bean |
| JDK proxy được trả về từ một `@Bean` tùy biến | Mã dùng `java.lang.reflect.Proxy` | **Không mặc nhiên** | **Không** | Bean có thể là JDK proxy nhưng không mang marker Spring AOP |
| Spring Data repository | Repository factory tạo implementation/proxy và interceptors | Thường dùng cơ sở `ProxyFactory`/AOP trong Spring Data | **Không** | Repository API được dispatch đến query/implementation; không suy ra có advice `@Aspect` |

**Lưu ý về `@Transactional`, `@Cacheable`, `@Async`:** Chúng không phải ví dụ “không dùng Spring AOP” khi ở **proxy mode**; chúng là minh chứng hạ tầng **AOP còn phục vụ các tính năng Spring khác**, không cần một lớp `@Aspect` của người dùng. Một bean có thể đồng thời nhận nhiều advisor từ nhiều nguồn. Với chế độ AspectJ weaving nếu được cấu hình riêng, những cơ chế này có thể hoạt động khác; bảng tập trung vào proxy mode.

**Lưu ý về scoped proxy:** Đây là trường hợp dễ gây bất ngờ. Proxy scope có thể trả về `true` với `AopUtils.isAopProxy(...)` nhưng mục đích là **chọn target từ scope**, không phải tự động gọi một `@Before` của ứng dụng. Sự khác biệt là **advisor/target source và hành vi**, chứ không chỉ loại hạ tầng proxy.

## 4. Spring AOP auto-proxy tạo proxy khi nào?

Trong Spring AOP dựa trên `@AspectJ`, cần các điều kiện điển hình:

1. Aspect đã thành **Spring bean** (`@Aspect @Component` trong vùng scan hoặc một `@Bean` trả về instance `@Aspect`).
2. Hỗ trợ Spring AOP hoạt động (ví dụ `@EnableAspectJAutoProxy`; với Spring Boot có thể do auto-configuration của starter AOP/AspectJ).
3. Advisor/pointcut phù hợp với target bean.
4. Bean đủ điều kiện proxy và client gọi phương thức **qua proxy**.

Đường gọi minh họa:

```text
Client -> Spring bean reference (AOP proxy)
            -> interceptor/advice matching method
            -> target.method()
            -> trả kết quả
```

Spring AOP có hai chiến lược tạo wrapper cơ bản:

- **JDK dynamic proxy** khi proxy theo interface: đối tượng triển khai các interface được expose, không phải instance trực tiếp của implementation class.
- **CGLIB class-based proxy** khi proxy theo lớp: đối tượng là subclass sinh động của target class, chịu các giới hạn `final`, `private` và khả năng override method.

Chính **nguồn advisor và đường gọi** mới giải thích tại sao advice chạy. Tên class được sinh từ JDK hoặc CGLIB chỉ mô tả kỹ thuật tạo proxy.

## 5. Proxy transaction/cache/async: AOP nhưng không nhất thiết có `@Aspect`

### 5.1. `@Transactional`

Với annotation-driven transaction management ở **proxy mode**, Spring thường tạo một advisor sử dụng `TransactionInterceptor` và `TransactionAttributeSource`, kết hợp với `TransactionManager`. Client gọi method cần transaction qua bean proxy; interceptor bắt đầu/tham gia transaction, gọi method và commit/rollback theo cấu hình.

```java
// Snippet để chèn vào ứng dụng có cấu hình transaction manager phù hợp.
// Không phải chương trình độc lập.
@Service
public class PaymentService {
    @Transactional
    public void pay() {
        // Thực thi nghiệp vụ trong transaction.
    }
}
```

Bạn không cần viết `@Aspect` để có transaction advice. Ngược lại, chỉ thêm `@Transactional` mà thiếu transaction infrastructure/manager và cấu hình cần thiết không đảm bảo transaction hoạt động.

`@Transactional` ở **proxy mode** cũng chịu giới hạn self-invocation: `this.pay()` bên trong target có thể bỏ qua interceptor transaction. Điều này xảy ra vì cơ chế dựa trên Spring AOP proxy.

### 5.2. `@Cacheable`

Với `@EnableCaching` ở proxy mode, Spring tạo cache-related advisor/interceptor cho bean phù hợp:

```java
// Snippet minh họa, cần CacheManager và caching đã được bật.
@Cacheable("products")
public Product findProduct(String id) {
    return repository.findById(id).orElseThrow();
}
```

Cache hit có thể trả kết quả ngay, **không gọi method target**. Một lần không thấy log bên trong target không đồng nghĩa proxy/pointcut không hoạt động. Cần kiểm tra `CacheManager`, cache name, key và cache advice. Một proxy tạo cho caching có thể cho `AopUtils.isAopProxy(bean) == true` mà ứng dụng hoàn toàn không khai báo một `@Aspect` tự viết.

### 5.3. `@Async`

Trong cấu hình proxy, `@Async` dùng Spring infrastructure để xử lý invocation và chuyển việc thực thi phù hợp sang executor. Nó không yêu cầu `@Aspect` của người dùng. Với Spring Framework, việc bật `@EnableAsync`, cung cấp executor và xử lý return type nằm trong cấu hình chức năng async; ở đây chỉ quan tâm rằng **proxy có thể sinh ra để phục vụ mục đích khác nhau**.

**Không đồng nhất ba tính năng:** Có proxy transaction không có nghĩa cache advice đã được bật; có proxy async không có nghĩa mọi method đều chạy ngoài thread hiện tại. Muốn kết luận phải xem advisor và metadata annotation thực tế.

## 6. Scoped proxy: dùng hạ tầng AOP để tìm target theo scope

Ví dụ: một singleton cần gọi một bean có scope ngắn hơn (request/session) hoặc một `prototype`. Thay vì giữ cố định một target không đúng scope, Spring có thể inject **scoped proxy**. Proxy này tìm instance target phù hợp từ container khi method được gọi.

```java
@Bean
@Scope(value = ConfigurableBeanFactory.SCOPE_PROTOTYPE,
       proxyMode = ScopedProxyMode.TARGET_CLASS)
public ScopedWorker scopedWorker() {
    return new ScopedWorker();
}
```

Đây là **đoạn minh họa trong class `@Configuration`**, cần import `@Bean`, `@Scope`, `ConfigurableBeanFactory` và `ScopedProxyMode`. Nó không phải chương trình độc lập; chương 8 sẽ có project chạy được.

Đối với `prototype` scoped proxy:

```text
Singleton caller -> cùng một scoped proxy
                      |
            mỗi lần gọi method
                      |
                  BeanFactory
                      |
               prototype target mới
                      |
                 target.method()
```

Với `request` hoặc `session` scope, Spring tra target tương ứng với request/session hiện tại; nếu gọi khi scope không hoạt động, có thể nhận exception liên quan scope. Không dùng một `request` scoped bean trực tiếp trong ứng dụng console không có request context.

**Điểm then chốt:** scoped proxy có thể là một **Spring AOP proxy thật** xét về marker/hạ tầng (`ScopedProxyFactoryBean` dùng Spring AOP proxy machinery), nhưng **không đồng nghĩa** nó có `@Aspect` advice. Nếu có advisor phù hợp khác, nhiều chức năng proxy có thể cùng xuất hiện hoặc được phối hợp.

## 7. `@Configuration` CGLIB enhancement khác AOP proxy

Một class `@Configuration(proxyBeanMethods = true)` (mặc định trong chế độ full configuration) được Spring tăng cường bằng một subclass CGLIB để lời gọi giữa các method `@Bean` tuân theo container và scope của bean:

```java
@Configuration(proxyBeanMethods = true)
public class SampleConfig {
    @Bean
    public Repository repository() {
        return new Repository();
    }

    @Bean
    public Service service() {
        return new Service(repository());
    }
}
```

Đây là **đoạn minh họa**, giả định các class `Repository`, `Service` tồn tại. Với singleton beans, lời gọi `repository()` từ `service()` được subclass tăng cường can thiệp để lấy bean từ context phù hợp, thay vì luôn tạo một instance mới độc lập.

So sánh:

| CGLIB-enhanced `@Configuration` | Class-based Spring AOP proxy |
| --- | --- |
| Tạo bởi hạ tầng `ConfigurationClassEnhancer` | Tạo bởi hạ tầng Spring AOP proxy |
| Mục tiêu là bảo toàn ngữ nghĩa method `@Bean` và inter-bean references | Mục tiêu là định tuyến lời gọi qua interceptor/advisor |
| Không tự động có marker `SpringProxy` chỉ vì CGLIB | Spring AOP proxy có marker `SpringProxy` |
| `AopUtils.isAopProxy(configBean)` thường là `false` | `AopUtils.isAopProxy(aopProxy)` là `true` |
| `configBean.getClass() != SampleConfig.class` có thể `true` | Target class cũng có thể khác runtime class vì proxy |

Khi dùng `@Configuration(proxyBeanMethods = false)`, Spring **không dùng kiểu tăng cường gọi chéo `@Bean` này**. Nhưng đặt `false` **không phải cách tắt Spring AOP** cho các service beans; đó là hai cơ chế riêng.

Cũng cần phân biệt `@Lookup` method injection: Spring có thể dùng subclass để override method lookup lấy bean, nhưng mục đích là **bean lookup**, không phải tự động thực thi `@Aspect` advice.

## 8. Ví dụ Java 17+ chạy được: so sánh ba cơ chế Spring và một JDK proxy

Chương trình sau sử dụng Spring Framework 6.2.19, Java 17+, Maven và không cần Spring Boot, HTTP server, database hoặc transaction manager. Nó chứng minh:

- `BillingService` được proxy bởi advisor từ một `@Aspect`.
- `ScopedCounter` được proxy để cung cấp target `prototype` phù hợp dù **không có advice `@Aspect` nhắm tới nó**.
- `AppConfig` là CGLIB-enhanced configuration class nhưng **không phải Spring AOP proxy** trong cấu hình này.
- Một `Runnable` dùng `java.lang.reflect.Proxy` được trả về từ `@Bean` là **Spring-managed bean có JDK proxy**, nhưng không phải Spring AOP proxy.

### 8.1. Cấu trúc thư mục

```text
proxy-origin-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── BillingService.java
    ├── BillingAspect.java
    ├── ScopedCounter.java
    └── Main.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>proxy-origin-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>${spring.version}</version>
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
```

### 8.3. `BillingService.java`

```java
package example;

public class BillingService {
    public void charge() {
        System.out.println("billing: charge");
    }
}
```

### 8.4. `BillingAspect.java`

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class BillingAspect {
    @Before("execution(* example.BillingService.charge(..))")
    public void beforeCharge() {
        System.out.println("aspect: before charge");
    }
}
```

### 8.5. `ScopedCounter.java`

```java
package example;

import java.util.concurrent.atomic.AtomicInteger;

public class ScopedCounter {
    private static final AtomicInteger NEXT_ID = new AtomicInteger();
    private final int id = NEXT_ID.incrementAndGet();

    public int id() {
        return id;
    }
}
```

Mỗi instance `ScopedCounter` giữ một `id` riêng. Nếu hai lần gọi `id()` được ủy quyền đến hai prototype targets mới, kết quả sẽ khác nhau.

### 8.6. `AppConfig.java`

```java
package example;

import java.lang.reflect.Proxy;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Scope;
import org.springframework.context.annotation.ScopedProxyMode;

@Configuration(proxyBeanMethods = true)
@EnableAspectJAutoProxy
public class AppConfig {
    @Bean
    public BillingService billingService() {
        return new BillingService();
    }

    @Bean
    public BillingAspect billingAspect() {
        return new BillingAspect();
    }

    @Bean
    @Scope(value = ConfigurableBeanFactory.SCOPE_PROTOTYPE,
           proxyMode = ScopedProxyMode.TARGET_CLASS)
    public ScopedCounter scopedCounter() {
        return new ScopedCounter();
    }

    @Bean
    public Runnable plainJdkProxy() {
        Runnable delegate = () -> System.out.println("jdk: delegated");
        return (Runnable) Proxy.newProxyInstance(
            AppConfig.class.getClassLoader(),
            new Class<?>[] { Runnable.class },
            (proxy, method, args) -> method.invoke(delegate, args)
        );
    }
}
```

Tại sao có `new` trong các method `@Bean` vẫn hợp lệ? Vì **giá trị trả về** được Spring đăng ký làm bean và có thể được các cơ chế post-processing/proxy xử lý. `new` bên ngoài container cho một instance riêng thì không tự nhận cơ chế đó.

### 8.7. `Main.java`

```java
package example;

import java.lang.reflect.Proxy;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            BillingService billing = context.getBean(BillingService.class);
            ScopedCounter counter = context.getBean(ScopedCounter.class);
            AppConfig config = context.getBean(AppConfig.class);
            Runnable jdk = context.getBean("plainJdkProxy", Runnable.class);

            System.out.println("billing Spring AOP proxy: "
                + AopUtils.isAopProxy(billing));
            System.out.println("scope Spring AOP proxy: "
                + AopUtils.isAopProxy(counter));
            System.out.println("scope targets differ: "
                + (counter.id() != counter.id()));
            System.out.println("config subclassed: "
                + (config.getClass() != AppConfig.class));
            System.out.println("config Spring AOP proxy: "
                + AopUtils.isAopProxy(config));
            System.out.println("plain JDK dynamic proxy: "
                + Proxy.isProxyClass(jdk.getClass()));
            System.out.println("plain Spring AOP proxy: "
                + AopUtils.isAopProxy(jdk));

            billing.charge();
            jdk.run();
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml` (yêu cầu Maven/JDK phù hợp):

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

Các dòng **do chương trình** in ra, theo thứ tự:

```text
billing Spring AOP proxy: true
scope Spring AOP proxy: true
scope targets differ: true
config subclassed: true
config Spring AOP proxy: false
plain JDK dynamic proxy: true
plain Spring AOP proxy: false
aspect: before charge
billing: charge
jdk: delegated
```

### 8.8. Vì sao các kết quả khác nhau?

**`billing Spring AOP proxy: true`**: `BillingAspect` đã là bean qua `@Bean`, `@EnableAspectJAutoProxy` đã bật; advisor từ `@Before` khớp `BillingService.charge()`. Spring trả về AOP proxy cho bean `billingService`, và khi `billing.charge()` chạy qua proxy, advice in trước dòng nghiệp vụ.

**`scope Spring AOP proxy: true`**: `scopedCounter` được khai báo `prototype` với scoped proxy. Hạ tầng Spring AOP tạo wrapper để tra target đúng scope. `BillingAspect` chỉ nhắm `BillingService.charge()`, vì vậy **không có `@Before` nào của ví dụ áp dụng cho `ScopedCounter.id()`**. Hai lần gọi `counter.id()` lấy hai prototype targets khác nhau nên so sánh trả `true`. Một lời gọi method **khác** trên scoped proxy cũng có thể tra target mới; đừng lưu trạng thái dài hạn trong prototype target với kỳ vọng nó được dùng cho mọi lần gọi qua scoped proxy.

**`config subclassed: true` nhưng `config Spring AOP proxy: false`**: `@Configuration(proxyBeanMethods = true)` khiến class cấu hình được CGLIB-enhance để Spring điều phối method `@Bean`. Không có advisor AOP nào match configuration class trong ví dụ, và CGLIB enhancement bản thân không phải Spring AOP proxy.

**`plain JDK dynamic proxy: true` nhưng `plain Spring AOP proxy: false`**: `@Bean` `plainJdkProxy()` tạo một dynamic proxy bằng Java reflection và trả về cho Spring quản lý. JDK proxy **không tự có marker Spring AOP**, không có Spring advisors trong cấu hình này. Nếu một advisor khác về sau bọc tiếp bean ấy, quan sát của *tham chiếu mới* có thể thay đổi.

Đây là bốn nhóm khác nhau về **mục đích và nguồn tạo**, dù có thể cùng sử dụng proxy class hoặc cùng được Spring container trả về.

## 9. Bộ công cụ chẩn đoán phù hợp

### 9.1. `AopUtils`: phát hiện Spring AOP proxy

Các API phổ biến của `org.springframework.aop.support.AopUtils`:

```java
// Snippet đặt trong mã có các tham chiếu bean đã khởi tạo.
boolean springAop = AopUtils.isAopProxy(bean);
boolean jdkSpringAop = AopUtils.isJdkDynamicProxy(bean);
boolean cglibSpringAop = AopUtils.isCglibProxy(bean);
Class<?> targetClass = AopUtils.getTargetClass(bean);
```

- `isAopProxy` nhận diện **Spring AOP proxy**; kiểm tra thêm marker `SpringProxy`, không chỉ dựa vào class name.
- `isJdkDynamicProxy` và `isCglibProxy` phân biệt **hai chiến lược Spring AOP**.
- `getTargetClass` giúp tìm target type nếu thông tin có sẵn; không mặc định cho rằng nó tháo được mọi lớp proxy tùy biến hoặc chuỗi proxy lồng nhau.

**Không dùng `Proxy.isProxyClass(...)` một mình để chứng minh Spring AOP**: đó là phép kiểm tra **JDK dynamic proxy nói chung**, không cần có Spring. Tương tự, chuỗi `$$` hoặc `$$SpringCGLIB$$` trong class name có thể thuộc một dạng CGLIB enhancement khác.

### 9.2. `Advised`: nhìn advisor và target source (khi khả dụng)

Một Spring AOP proxy điển hình có thể triển khai `org.springframework.aop.framework.Advised`. Trong ví dụ mục 8, có thể thêm đoạn sau vào cuối `main` trước khi đóng context để quan sát:

```java
// Snippet, không phải chương trình độc lập:
if (billing instanceof org.springframework.aop.framework.Advised advised) {
    System.out.println("billing advisors: " + advised.getAdvisors().length);
    System.out.println("billing target source: "
        + advised.getTargetSource().getClass().getSimpleName());
}
if (counter instanceof org.springframework.aop.framework.Advised advised) {
    System.out.println("scope advisors: " + advised.getAdvisors().length);
    System.out.println("scope target source: "
        + advised.getTargetSource().getClass().getSimpleName());
}
```

Kết quả số lượng advisor hoặc tên class target source phụ thuộc phiên bản/cấu hình, vì vậy **không nên cố định stdout** của snippet chẩn đoán này. Nội dung quan trọng là:

- **Advisor** mô tả chuỗi advice/interceptor gắn với proxy được quan sát.
- **TargetSource** cung cấp target mà proxy sẽ gọi. Với scoped proxy, target source dùng để lấy bean từ scope; không đồng nhất với target source tĩnh thông thường.
- Nếu proxy được cấu hình `opaque`, không phải lúc nào cũng có thể cast `Advised`; hãy dùng `instanceof`.
- `Advised.getAdvisors()` cho biết các advisor lắp trên **lớp proxy quan sát được**, nhưng chưa tự chứng minh một advice đã chạy cho lời gọi cụ thể. Cần kiểm tra method match và hành vi.

Không gọi `advised.getTargetSource().getTarget()` tùy tiện khi debug scope/request/prototype: thao tác này có thể tạo/lấy target hoặc cần scope đang active, dẫn tới tác động không cần thiết. Ưu tiên quan sát type target source và thực thi method trong ngữ cảnh đã kiểm soát.

### 9.3. Xác nhận advice đến từ đâu

Một bean được `AopUtils.isAopProxy(...)` xác nhận có thể chứa:

- Advisor khai báo từ `@Aspect` do ứng dụng đăng ký.
- Infrastructure advisor tạo bởi Spring transaction, caching, async hoặc các feature khác.
- Interceptor phục vụ việc định tuyến tới target theo scope.
- Advisor/đường ủy quyền từ các framework extension.

Vì thế, khi hỏi “Advice của **aspect X** có được dùng không?”, phải kiểm tra **`@Aspect` bean tồn tại, advisor của aspect có áp dụng cho target, method có khớp và lời gọi có đi qua proxy hay không**. Không chỉ in một cờ boolean.

### 9.4. Proxy lồng nhau hoặc kết hợp

Trong dự án phức tạp, bean có thể đi qua nhiều lớp post-processing hoặc được bọc qua nhiều proxy. Ví dụ một object vốn do factory trả về dưới dạng proxy rồi tiếp tục được Spring AOP bọc. Khi đó:

```text
Client
  -> outer proxy / interceptor A
      -> inner proxy / interceptor B
          -> target
```

Không suy ra **chính xác** thứ tự các interceptor hoặc lớp proxy chỉ từ tên class; hãy quan sát cấu hình `Advised`, target source và trace invocation của phiên bản đang chạy. Spring cũng có cơ chế hợp nhất/điều phối auto-proxy settings nên hai annotation cấu hình không mặc nhiên tạo hai proxy tách biệt.

## 10. Cây quyết định khi gặp một bean “trông giống proxy”

```text
Object được lấy từ Spring ApplicationContext?
|
+-- Không: cần xác định ai tạo object (new, JDK Proxy, mock, factory ngoài Spring)
|
+-- Có: AopUtils.isAopProxy(bean)?
    |
    +-- false:
    |   +-- Proxy.isProxyClass(bean.getClass())?
    |   |      -> Có thể là JDK proxy không phải Spring AOP
    |   +-- getClass() khác class gốc / CGLIB enhancement?
    |          -> Kiểm tra @Configuration, @Lookup hoặc cơ chế tăng cường khác
    |
    +-- true:
        +-- isJdkDynamicProxy / isCglibProxy để biết hình thức
        +-- instanceof Advised? Kiểm tra advisor + target source nếu có
        +-- Có advisor @Aspect bạn cần không?
        |      -> Có: tiếp tục kiểm tra pointcut/method/invocation
        |      -> Không: xem transaction/cache/async/scope/feature khác
        +-- Gọi method qua bean proxy, xác minh hành vi thực tế
```

**Một proxy “do Spring tạo” không nhất thiết là “do Spring AOP auto-proxy từ `@Aspect` tạo”.** Đồng thời, scoped proxy là ví dụ phản chứng cho cách phân loại giản lược “proxy AOP = advice do developer viết”: scoped proxy có thể dùng đúng hạ tầng Spring AOP, nhưng mục đích là scope.

## 11. Lỗi chẩn đoán thường gặp

| Dấu hiệu | Kết luận vội dễ sai | Cách kiểm tra đáng tin |
| --- | --- | --- |
| `bean.getClass().getName()` chứa `$$SpringCGLIB$$` | Chắc chắn có `@Aspect` advice | Xác định `AopUtils.isAopProxy`, class `@Configuration`, advisor và hành vi |
| `Proxy.isProxyClass(bean.getClass()) == true` | Đây là Spring AOP proxy | Kiểm tra `AopUtils.isAopProxy`; JDK proxy thuần có thể không phải Spring AOP |
| `AopUtils.isAopProxy(bean) == true` | Mọi method chạy advice của tôi | Kiểm tra eligible advisor, pointcut, method runtime và proxy call |
| Bean có `@Transactional`, `@Cacheable` hoặc `@Async` | Bắt buộc phải có `@Aspect` class | Kiểm tra Spring annotation infrastructure và configuration/manager tương ứng |
| Scoped proxy cho `prototype` có AOP marker | Nó phải chạy aspect advice | Kiểm tra target source, scope và advisor; mục đích chính là chọn target |
| `@Configuration(proxyBeanMethods = true)` tạo subclass | Cấu hình class đang bị aspect chặn | Xác định enhancement `@Bean` so với advisor AOP |
| Bean có AOP proxy nhưng self-invocation không có log | Pointcut chắc chắn sai | Kiểm tra `this.method()`; lời gọi nội bộ đi thẳng trên target |
| Không thấy log của target trong lần gọi `@Cacheable` | Không có proxy | Có thể cache hit; kiểm tra cache metrics/interceptor |
| Cần đọc target của `request` scope khi không có request | Có thể gọi bất kỳ lúc nào để kiểm tra | Chỉ debug trong scope phù hợp; tránh ép lấy scoped target sớm |
| Class `final` với CGLIB proxy | Annotation AOP chắc chắn được áp dụng | CGLIB không subclass được `final` class; xem kiểu proxy và thông báo lỗi |

## 12. Bài tập vận dụng

**Tình huống A.** `@Configuration(proxyBeanMethods = true)` khiến bean cấu hình có class runtime khác class mã nguồn. `AopUtils.isAopProxy(config)` bằng `false`. Có mâu thuẫn không?

**Đáp án:** Không. CGLIB subclass enhancement cho ngữ nghĩa `@Bean` khác Spring AOP proxy. Đừng suy từ việc subclassed sang việc advisor `@Aspect` có mặt.

**Tình huống B.** Singleton inject một scoped proxy cho prototype bean. `AopUtils.isAopProxy(scoped)` là `true`, nhưng dự án không có `@Aspect` nào. Có hợp lệ không?

**Đáp án:** Có. Scoped proxy có thể dùng Spring AOP machinery để chuyển mỗi lần gọi tới target đúng scope; không cần advice `@Aspect` do người dùng khai báo.

**Tình huống C.** Service có `@Transactional`, không có custom `@Aspect`, nhưng `AopUtils.isAopProxy(service) == true`. Tại sao?

**Đáp án:** Transaction management ở proxy mode tự đăng ký infrastructure advisor/interceptor để điều phối transaction. Spring AOP không giới hạn ở `@Aspect` do người dùng viết.

**Tình huống D.** Một bean được `@Bean` trả về từ `java.lang.reflect.Proxy.newProxyInstance(...)`. `Proxy.isProxyClass(...)` trả `true` nhưng `AopUtils.isAopProxy(...)` trả `false`. Có phải Spring AOP bị lỗi?

**Đáp án:** Không. Đây là JDK dynamic proxy thông thường, không có marker Spring AOP; Spring quản lý bean không đồng nghĩa Spring tạo hoặc bổ sung AOP proxy cho bean ấy.

**Tình huống E.** AOP proxy của `PaymentService` có transaction advisor và `@Aspect` advisor. Gọi `pay()` từ ngoài chạy cả hai; `this.refund()` trong target không kích hoạt advice riêng của `refund()`. Giải thích?

**Đáp án:** Hai advisor có thể cùng gắn lên proxy, nhưng self-invocation qua `this` không quay lại proxy. Đây là giới hạn **proxy-based interception**, độc lập với việc advisor đến từ `@Transactional` hay `@Aspect`.

## 13. Nguồn Spring chính thức

- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB AOP proxy và giới hạn self-invocation.
- [Spring Framework — Bean Scopes / Scoped Proxies](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): scoped proxy, proxy target theo request/session/prototype.
- [Spring Framework — Using the @Configuration Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/configuration-annotation.html): CGLIB enhancement và `proxyBeanMethods`.
- [Spring Framework — Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction interceptor sử dụng Spring AOP.
- [Spring Framework — Cache Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): cache annotation proxy mode.
- [Spring Framework — AopUtils API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html): `isAopProxy`, `isJdkDynamicProxy`, `isCglibProxy`, `getTargetClass`.
- [Spring Framework — Advised API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/framework/Advised.html): các advisors/target source có thể quan sát trên Spring AOP proxy.

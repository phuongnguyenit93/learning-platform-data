# Scope của Spring bean khác mô hình khởi tạo aspect như thế nào?

## 1. Hai câu hỏi tưởng giống nhưng Spring trả lời bằng hai cơ chế khác nhau

Trong Spring AOP, khi thấy một lớp có cả `@Aspect` và `@Component`, rất dễ nghĩ rằng `@Scope` trên lớp đó và tham số của `@Aspect(...)` là hai cách viết của cùng một quy tắc. Thực tế, chúng giải quyết **hai cấp độ khác nhau**.

- **Spring bean scope** trả lời: *BeanFactory/ApplicationContext cung cấp và quản lý đối tượng của một bean definition theo vòng đời nào?* Những scope phổ biến là `singleton`, `prototype`, `request`, `session`. Cơ chế này áp dụng cho bean nói chung, kể cả service bean và bean dùng để khai báo aspect.
- **Aspect instantiation model** trả lời: *Spring AOP tạo hoặc liên kết instance aspect với những join point/proxy/target nào khi thực thi advice?* Mặc định một aspect là mô hình **singleton**; với cú pháp `@AspectJ` được Spring hỗ trợ còn có các mô hình như `perthis` và `pertarget`.

Do đó, cùng một ứng dụng có thể có **hàng trăm target bean prototype** nhưng chỉ **một aspect instance singleton** quan sát các lần gọi qua proxy. Ngược lại, một aspect dạng `pertarget` có thể sở hữu các instance trạng thái riêng cho từng target được khớp, ngay cả khi bạn không thay đổi cách tạo target bằng `@Scope`.

Bài này tập trung vào **Spring Framework và Spring AOP theo proxy**: cách hai cơ chế phối hợp, cấu hình đúng và các ngộ nhận gây lỗi. Nó không mở rộng sang mô hình weaving độc lập ngoài Spring.

### Mục tiêu học tập

Sau bài này, bạn có thể:
1. Phân biệt *bean definition / bean scope / Spring AOP proxy / target object / aspect instance*.
2. Giải thích vì sao `@Scope("prototype")` trên service không tự tạo một aspect cho mỗi service, và tại sao `@Scope("prototype")` trên aspect cũng chưa đủ để biểu đạt `perthis` hoặc `pertarget`.
3. Chọn `@Aspect` mặc định hay `@Aspect("perthis(...)")` / `@Aspect("pertarget(...)")` theo nhu cầu trạng thái.
4. Chạy ví dụ Java 17 với Spring để kiểm tra số instance của target và aspect.
5. Nhận diện tương tác khó giữa Spring scoped proxy, vòng đời web bean và lời gọi qua AOP proxy.

## 2. Bảng đối chiếu: Spring bean scope và aspect instantiation

| Tiêu chí | Spring bean scope | Mô hình khởi tạo aspect trong Spring AOP |
| --- | --- | --- |
| Cấu hình chính | `@Scope`, `@RequestScope`, `@SessionScope`, hoặc scope của `@Bean` | `@Aspect` và giá trị per-clause trong `@Aspect("...")` |
| Đối tượng quản lý | Bean definition do Spring IoC quản lý, gồm service, repository, aspect bean | Những instance **của một aspect** được advice framework sử dụng |
| Quy tắc mặc định | `singleton`: một bean instance trên mỗi bean definition trong container | `@Aspect` không tham số: singleton instantiation model, thường một aspect instance trong context |
| Nhân bản instance | `prototype`: mỗi lần container cung cấp bean mới thường có instance mới | `perthis`: theo đối tượng `this` tại join point khớp; `pertarget`: theo target object tại join point khớp |
| Đơn vị gắn vòng đời | Context/bean lookup; hoặc request, session, scope tùy chỉnh | Proxy/target liên quan đến lời gọi và **điều kiện pointcut tạo aspect** |
| Điều kiện áp dụng | Có bean definition và scope đã đăng ký hợp lệ | AOP được bật; aspect được đăng ký làm Spring bean; advisor/pointcut có lời gọi phù hợp **qua proxy** |
| Thời điểm tạo | Theo việc khởi tạo bean: singleton thường eager, prototype được tạo theo yêu cầu, web scope theo request/session | Singleton aspect theo vòng đời bean; `perthis`/`pertarget` khởi tạo khi có join point phù hợp đầu tiên |
| Thứ gì được chia sẻ? | Phụ thuộc scope của từng bean, không phụ thuộc trực tiếp annotation AOP trên target | Phụ thuộc per-clause, không mặc định bằng scope của target |
| Mối quan hệ với proxy | Scoped proxy có thể giúp inject bean sống ngắn hơn vào bean sống dài hơn | AOP proxy chặn method execution và gọi advice trước/sau target |

**Hai chữ “singleton” không đồng nhất mọi đối tượng:**
- Spring bean singleton nghĩa là **một instance cho mỗi bean definition trong một container**, không phải một instance Java duy nhất trong toàn JVM.
- Singleton aspect mặc định là quy tắc Spring AOP sử dụng một aspect instance chung trong context để thực thi các advice của aspect đó. Nó có thể advise nhiều bean, nhiều phương thức, nhiều lời gọi và nhiều thread.
- Nếu có nhiều `ApplicationContext` hoặc nhiều bean definition khác nhau, không suy ra chỉ có một instance aspect trong toàn ứng dụng.

### Bốn đối tượng cần nhìn tách biệt

```text
ApplicationContext
│
├── Bean definition: auditAspect
│     └── aspect instance (thường singleton)
│                  │
│                  └── advice / advisor của Spring AOP
│
├── Bean definition: orderService [scope=prototype]
│     ├── target instance #1 ──> Spring AOP proxy #1
│     └── target instance #2 ──> Spring AOP proxy #2
│
└── Client:
      service1.call() ──> proxy #1 ──> advice trên aspect ──> target #1
      service2.call() ──> proxy #2 ──> advice trên aspect ──> target #2
```

Ở đây, các proxy và target là hai đối tượng khác nhau. Cả hai lời gọi có thể đi qua **cùng instance của singleton aspect**, mặc dù hai target là hai instance prototype. Không nên đếm số proxy rồi kết luận số instance aspect.

## 3. Bean scope tác động thế nào khi bean được Spring AOP advise?

### 3.1. `singleton` target

Ví dụ định nghĩa service:

```java
@Bean
public OrderService orderService() {
    return new OrderService();
}
```

Bean có scope mặc định `singleton`. Với một context và một bean definition:
- Các lần `context.getBean("orderService")` thường nhận cùng tham chiếu Spring-managed bean. Nếu Spring AOP cần proxy, tham chiếu đó có thể là **cùng một proxy singleton**.
- Tất cả lần gọi `public` khớp pointcut và đi qua proxy đều có thể dùng cùng instance aspect singleton.
- Mỗi lời gọi không tạo lại service hoặc aspect theo mặc định.

Lưu ý: Spring proxy không phải bằng chứng rằng toàn bộ logic trong đối tượng đã trở thành immutable hoặc thread-safe. Cả target singleton và aspect singleton đều có thể được nhiều thread truy cập.

### 3.2. `prototype` target

Nếu khai báo:

```java
@Bean
@Scope("prototype")
public OrderService orderService() {
    return new OrderService();
}
```

mỗi lần **BeanFactory được yêu cầu cấp bean** sẽ tạo một target instance mới. Nếu có advice khớp, Spring xử lý và trả một proxy ứng với bean được tạo đó. Tuy nhiên:
- **Aspect singleton vẫn có thể là cùng một instance** dùng chung cho mọi target prototype.
- Nếu inject prototype vào constructor một singleton, việc inject bình thường chỉ xảy ra khi singleton được tạo; singleton giữ tham chiếu đó cho các lần gọi tiếp theo. Muốn lấy prototype mới lúc runtime, cân nhắc `ObjectProvider<OrderService>` hoặc method injection.
- Gọi nhiều lần qua *một* tham chiếu prototype đã được lấy ra không khiến Spring tự cấp target mới cho mỗi method invocation. Đừng nhầm với `@Scope(proxyMode = ...)` hoặc một provider lấy bean mỗi lần.

### 3.3. `request`, `session` và scoped proxy

Bean `request` hoặc `session` thuộc phạm vi web-aware `ApplicationContext`. Ví dụ:

```java
@RequestScope
@Component
public class RequestMetadata {
    // Một target bean theo HTTP request trong Spring web context.
}
```

Khi cần đưa bean sống theo request vào một singleton, Spring thường dùng **scoped proxy** để tra cứu target ứng với request hiện tại. Scoped proxy giải bài toán *tham chiếu và vòng đời bean*, còn AOP proxy giải bài toán *áp dụng advice cho lời gọi method*. Hai loại proxy có thể cùng xuất hiện trong một đường gọi nhưng phục vụ mục đích khác nhau.

**Không tự suy ra** rằng cứ một HTTP request là Spring tạo một aspect mới. Nếu aspect đang ở mô hình singleton, nó vẫn có thể quan sát nhiều request bằng một instance. Nếu ứng dụng cần dữ liệu riêng theo request, hãy lấy từ method arguments, các dependency request-scoped phù hợp hoặc context của lời gọi, thay vì đưa dữ liệu của từng request vào field mutable dùng chung của singleton aspect.

## 4. Cách Spring AOP tạo aspect instance

### 4.1. Mặc định: `@Aspect` có singleton instantiation model

```java
@Aspect
@Component
public class AuditAspect {
    @Before("execution(* com.example.service..*.*(..))")
    public void audit() {
        // Được chạy cho các bean/method khớp pointcut,
        // nhưng không vì mỗi bean khớp mà có aspect instance mới.
    }
}
```

`@Component` là cách đăng ký lớp thành Spring bean. `@Aspect` mô tả các advice/pointcut để Spring phân tích khi AOP đã được kích hoạt (ví dụ qua `@EnableAspectJAutoProxy` hoặc Spring Boot AOP auto-configuration). Một mình `@Aspect` **không tự đăng ký bean**.

Nếu aspect bean dùng scope mặc định `singleton`, một aspect instance sẽ được framework dùng để xử lý những lời gọi khớp trên nhiều target/proxy. Điều này phù hợp nhất với aspect **stateless** hoặc có trạng thái dùng chung được thiết kế thread-safe (ví dụ bộ đếm `AtomicLong`).

**Cạm bẫy:** field `int currentUserCalls` trong singleton aspect có thể bị cập nhật đồng thời bởi nhiều thread và trộn dữ liệu của nhiều người dùng. Khi advice chỉ cần đo thời gian từng lời gọi, biến cục bộ trong `@Around` thường phù hợp hơn field của aspect.

### 4.2. `perthis`: một aspect instance theo đối tượng `this` được khớp

Với Spring AOP, cú pháp:

```java
@Aspect("perthis(execution(* com.example.service..*.*(..)))")
@Component
@Scope("prototype")
public class PerProxyAuditAspect {
    @Before("execution(* com.example.service..*.*(..))")
    public void audit() {
        // Trạng thái của instance aspect được gắn với this phù hợp.
    }
}
```

Ý nghĩa:
1. Phần `perthis(...)` là **instantiation pointcut** xác định lần đầu một đối tượng `this` tham gia lời gọi phù hợp.
2. Khi phát sinh lời gọi khớp đầu tiên, Spring có thể tạo một aspect instance liên kết với đối tượng `this` đó; các advice của instance này tiếp tục áp dụng cho những join point tương ứng.
3. Trong Spring AOP dựa trên proxy, `this` trong pointcut nói đến **proxy object**. Vì vậy có thể hiểu trực quan `perthis` là theo *proxy identity* thích hợp.
4. Spring cần có khả năng tạo nhiều instance aspect; vì vậy aspect bean phải có scope không phải singleton (mẫu thông dụng là `@Scope("prototype")`).

Đây là **đoạn minh họa cú pháp**, giả sử package `com.example.service` và các bean liên quan đã tồn tại, Spring AOP được bật. Không ghép thẳng đoạn này vào ví dụ chạy ở phần 6 vì hai ví dụ minh họa **hai chế độ khởi tạo khác nhau**.

### 4.3. `pertarget`: một aspect instance theo target object được khớp

```java
@Aspect("pertarget(execution(* com.example.service..*.*(..)))")
@Component
@Scope("prototype")
public class PerTargetAuditAspect {
    @Before("execution(* com.example.service..*.*(..))")
    public void audit() {
        // Trạng thái riêng cho target object đã khớp.
    }
}
```

`pertarget` cũng dựa vào lần đầu join point phù hợp xuất hiện, nhưng khóa liên kết instance aspect là **target object** thay cho `this`. Trong một AOP proxy đơn giản bao quanh một target cố định, `perthis` và `pertarget` thường cho kết quả số lượng instance giống nhau. Chúng khác nhau về ý nghĩa khi proxy và target không có quan hệ một-một (ví dụ cấu hình target source động hoặc có scoped proxy), nên **không được coi là hai tên khác nhau cho cùng một bean scope**.

Cẩn thận với cụm “mỗi target”: đây là từng **đối tượng target thực tế khớp** trong cơ chế AOP, không phải mỗi lần gọi method, mỗi tên bean, mỗi thread hoặc mỗi HTTP request theo mặc định.

### 4.4. Bảng các mô hình và hỗ trợ theo phiên bản Spring

| Cú pháp | Đơn vị instance aspect | Lưu ý trong Spring AOP |
| --- | --- | --- |
| `@Aspect` | Mặc định singleton trong context | Thích hợp cho cross-cutting logic stateless và phổ biến nhất. |
| `@Aspect("perthis(<pointcut>)")` | Theo `this` của matched join point (Spring proxy) | Cần aspect bean có scope có thể cấp instance mới, ví dụ `prototype`. |
| `@Aspect("pertarget(<pointcut>)")` | Theo target object của matched join point | Cần aspect bean non-singleton như `prototype`. |
| `@Aspect("pertypewithin(<type-pattern>)")` | Theo type phù hợp | **Phụ thuộc phiên bản:** tài liệu Spring Framework mới có ghi hỗ trợ, nhưng tài liệu của những phiên bản cũ không hỗ trợ. Phải kiểm tra đúng phiên bản Spring đang dùng trước khi áp dụng. |
| `percflow(...)` / `percflowbelow(...)` | Theo luồng điều khiển trong AspectJ | Không được hỗ trợ trong Spring AOP dựa trên proxy; cần cân nhắc cơ chế khác nếu thật sự cần. |

Ví dụ chạy trong bài dùng **Spring Framework 6.1.14** và chỉ minh họa mô hình aspect singleton, tương thích chắc chắn với phiên bản này. `perthis` và `pertarget` là các mô hình được tài liệu Spring 6.1 mô tả; `pertypewithin` đã thay đổi tình trạng hỗ trợ giữa các thế hệ tài liệu, nên không xây bài thực hành dựa vào nó.

### Vì sao `@Scope("prototype")` trên aspect không tương đương `perthis`?

Đây là một điểm đặc biệt quan trọng:

- `@Scope("prototype")` nói với **Spring BeanFactory** rằng khi được yêu cầu cấp bean theo definition này, nó có thể cấp instance mới.
- `@Aspect("perthis(...)")` hoặc `@Aspect("pertarget(...)")` nói với **Spring AOP** khi nào cần liên kết một instance aspect mới với đối tượng nào.
- Với aspect per-instance, hai cấu hình phối hợp: AOP xác định quy tắc liên kết, BeanFactory cung cấp instance mỗi khi cần.

Chỉ sửa:

```java
@Aspect
@Component
@Scope("prototype")
public class SomeAspect {
    // Không khai báo perthis/pertarget.
}
```

**không có nghĩa** Spring sẽ tự suy ra “mỗi target một aspect” hay “mỗi lời gọi một aspect”. Đây vẫn là **singleton instantiation model** vì `@Aspect` không có per-clause. Khi cần định lượng số instance thật sự, phải hiểu cách Spring sử dụng aspect instance factory theo phiên bản và kiểm tra runtime, không suy đoán từ tên scope.

Ở chiều ngược lại, khai báo `@Aspect("pertarget(...)")` nhưng để aspect bean singleton mặc định cũng là **cấu hình không phù hợp**: Spring cần khả năng tạo instance aspect độc lập và có thể báo lỗi khi phát hiện bean singleton với non-singleton instantiation model. Mẫu an toàn là phối hợp per-clause với `@Scope("prototype")`.

## 5. Ma trận tình huống: target scope không quyết định mô hình aspect

Giả sử mọi bean được Spring tạo, Spring AOP được bật, pointcut khớp các lời gọi công khai qua proxy và không có proxy/target source bất thường:

| Target bean | Aspect bean / instantiation | Số instance target nhìn thấy | Số instance aspect dùng cho các target |
| --- | --- | --- | --- |
| Singleton | `@Aspect` + aspect bean singleton | Một target trên mỗi bean definition | Một instance aspect singleton chung cho các lời gọi khớp |
| Prototype | `@Aspect` + aspect bean singleton | Nhiều target qua nhiều lần `getBean` | **Vẫn** một instance aspect dùng chung trong context |
| Hai singleton bean definition khác nhau | `@Aspect` + aspect bean singleton | Mỗi definition có target riêng | Một aspect instance có thể advise cả hai nếu pointcut khớp |
| Prototype | `@Aspect("perthis(...)")` + aspect bean prototype | Nhiều target/proxy riêng | Một aspect instance theo từng proxy phù hợp, không bắt buộc theo lần gọi |
| Prototype | `@Aspect("pertarget(...)")` + aspect bean prototype | Nhiều target riêng | Một aspect instance theo từng target phù hợp |
| Request/session với scoped proxy | `@Aspect` + aspect bean singleton | Target thay theo scope runtime | Aspect vẫn có thể dùng chung giữa các request/session |
| Request/session với scoped proxy | `perthis` hoặc `pertarget` | Proxy và target có thể khác vòng đời | Phải khảo sát proxy identity, target source và pointcut; không được suy đoán từ HTTP scope |

Số instance trong cột cuối mang tính **mô hình**: một aspect không khớp method nào sẽ không nhất thiết có cùng hành vi khởi tạo như khi có join point khớp; kết quả thực tế cũng phụ thuộc vào cấu hình scope, proxy và lifecycle.

## 6. Ví dụ chạy được: hai prototype target và một singleton aspect

Để nhìn rõ hai cơ chế độc lập, ta xây một ứng dụng **Spring Framework thuần**, không cần web server. Ví dụ dùng:
- Java 17+;
- Spring Framework `6.1.14`;
- `spring-context` và `spring-aop`;
- AspectJ Weaver trên classpath để Spring xử lý biểu thức trong `@Before`.

### 6.1. Cấu trúc project và Gradle

```text
spring-aop-scope/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/aop/
    ├── ScopeDemo.java
    ├── JobService.java
    └── AuditAspect.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-scope'
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
    mainClass = 'demo.aop.ScopeDemo'
}
```

### 6.2. Target service có ID riêng theo mỗi instance

`src/main/java/demo/aop/JobService.java`:

```java
package demo.aop;

import java.util.concurrent.atomic.AtomicInteger;

public class JobService {
    private static final AtomicInteger NEXT_ID = new AtomicInteger();
    private final int id = NEXT_ID.incrementAndGet();

    public void run(String name) {
        System.out.println("target#" + id + ":" + name);
    }
}
```

Biến `NEXT_ID` là công cụ quan sát **số instance `JobService`**, không phải biến của aspect. Với hai lần gọi `getBean(JobService.class)` trên definition `prototype`, hai target được tạo riêng và nhận `id` lần lượt là `1`, `2` trong chương trình này.

### 6.3. Aspect singleton với bộ đếm lời gọi chung

`src/main/java/demo/aop/AuditAspect.java`:

```java
package demo.aop;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Before("execution(public void demo.aop.JobService.run(String))")
    public void beforeRun() {
        int value = calls.incrementAndGet();
        System.out.println("advice#" + value);
    }

    public int count() {
        return calls.get();
    }
}
```

Spring thấy `@Aspect` để tạo advisor. `AuditAspect` sẽ được đăng ký thành singleton bean trong config, nên **cùng đối tượng aspect** tăng bộ đếm khi hai prototype service chạy. `AtomicInteger` làm phép tăng thread-safe; ví dụ vẫn chạy tuần tự để stdout xác định. `count()` giúp kiểm tra aspect giữ trạng thái tích lũy.

### 6.4. Khởi tạo Spring context và so sánh các instance

`src/main/java/demo/aop/ScopeDemo.java`:

```java
package demo.aop;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Scope;

public class ScopeDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    public static class Config {

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public JobService jobService() {
            return new JobService();
        }

        @Bean
        public AuditAspect auditAspect() {
            return new AuditAspect();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            JobService first = context.getBean(JobService.class);
            JobService second = context.getBean(JobService.class);

            AuditAspect one = context.getBean(AuditAspect.class);
            AuditAspect two = context.getBean(AuditAspect.class);

            System.out.println("differentTargets=" + (first != second));
            System.out.println("sameAspect=" + (one == two));
            System.out.println("firstProxied=" + AopUtils.isAopProxy(first));
            System.out.println("secondProxied=" + AopUtils.isAopProxy(second));

            first.run("alpha");
            second.run("beta");

            System.out.println("adviceCount=" + one.count());
        }
    }
}
```

**Giải thích cấu hình:**
1. `@EnableAspectJAutoProxy(proxyTargetClass = true)` bật cơ chế Spring AOP và ưu tiên class-based proxy, nên có thể lấy proxy bằng kiểu `JobService`.
2. `@Bean @Scope(PROTOTYPE)` làm mỗi lần `context.getBean(JobService.class)` tạo service khác nhau.
3. `@Bean AuditAspect` không có `@Scope` nên mặc định là singleton bean. `@Aspect` trên lớp chỉ định mô hình khởi tạo aspect singleton.
4. `@Before` áp dụng cho `JobService.run(String)` khi lời gọi đi qua proxy. Cả hai proxy dùng cùng aspect bean.
5. `AopUtils.isAopProxy` phân biệt bean được Spring trả về với target gốc. Test `first != second` đo tham chiếu bean được trả về; ID trong `run` cho thấy target thực sự khác nhau.

### 6.5. Lệnh chạy và kết quả mong đợi

Trong thư mục dự án, dùng một Gradle installation có thể chạy project:

```bash
gradle run
```

Nếu đã tạo Gradle Wrapper trong dự án, có thể dùng `./gradlew run` (Linux/macOS) hoặc `gradlew.bat run` (Windows).

Những dòng do **chương trình Java** in ra (bỏ qua banner/log của Gradle hoặc môi trường):

```text
differentTargets=true
sameAspect=true
firstProxied=true
secondProxied=true
advice#1
target#1:alpha
advice#2
target#2:beta
adviceCount=2
```

Nhận xét:
- `differentTargets=true`: hai yêu cầu bean prototype tạo hai Spring-managed instances riêng.
- `sameAspect=true`: hai lần xin aspect singleton đều được cấp cùng tham chiếu.
- Hai kết quả `firstProxied=true` và `secondProxied=true`: target prototype cũng có thể được Spring AOP proxy.
- Bộ đếm advice tăng `1 → 2` **trên cùng instance aspect**, không reset về `1` khi chuyển sang target thứ hai.
- Advice chạy *trước* target vì là `@Before`. Nếu dùng `@Around` với `proceed()`, thứ tự log tùy logic bao quanh được viết.

Đây là minh chứng cụ thể cho kết luận **“target prototype” không có nghĩa “aspect pertarget”**.

## 7. Cấu hình aspect gắn với target: hai cơ chế phối hợp

Nếu nghiệp vụ thực sự cần **state riêng theo từng target**, Spring AOP hỗ trợ `@Aspect("pertarget(...)")`. Bean definition của aspect phải cho phép Spring cấp nhiều instance, thường bằng `prototype`; chỉ đổi scope hoặc chỉ thêm per-clause riêng lẻ không đủ để có mô hình đúng.

```java
@Aspect("pertarget(execution(public void demo.aop.JobService.run(String)))")
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class PerTargetAuditAspect {
    @Before("execution(public void demo.aop.JobService.run(String))")
    public void beforeRun() {
        // Advice thuộc aspect instance liên kết với target tương ứng.
    }
}
```

Đoạn trên **minh họa cấu hình**, cần thêm imports và component scan phù hợp; không ghép vào demo singleton ở mục 6. Nếu đăng ký aspect bằng phương thức `@Bean` thay cho `@Component`, đặt `@Scope(PROTOTYPE)` trên bean definition tương ứng. Với `perthis(...)`, Spring AOP liên kết instance theo **proxy** thay vì target. Bài kế tiếp thực hành riêng cả ba mô hình `singleton`, `perthis`, `pertarget` và cách quan sát identity của các đối tượng.

Per-clause theo proxy/target **không phải** scope request hay thread-local: nhiều lời gọi đồng thời trên cùng target vẫn có thể dùng cùng aspect instance. Khi chỉ cần dữ liệu theo request, ưu tiên tham số advice hoặc collaborator có scope phù hợp.

## 8. Những phép suy luận sai hay gặp trong Spring

| Câu nói sai | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Service `prototype` nên mỗi service có aspect riêng.” | Target bean scope và aspect instantiation là hai trục. | Aspect `@Aspect` mặc định có thể được chia sẻ giữa nhiều prototype target. |
| “`@Aspect` là bean dù không đăng ký gì.” | `@Aspect` không phải annotation đăng ký component. | Đăng ký aspect qua `@Component`, `@Bean` hoặc cách tương đương. |
| “`@Scope("prototype")` trên aspect có nghĩa một aspect trên mỗi method call.” | Scope chỉ quy định cách BeanFactory cấp bean theo request tạo bean; không diễn đạt quy tắc AOP per-method. | Dùng đúng per-clause nếu muốn instance gắn với proxy/target. |
| “`@Aspect("pertarget(...)")` một mình là đủ.” | Instance model per-target cần aspect bean non-singleton. | Kết hợp với scope cho phép tạo nhiều aspect instances, thường `prototype`. |
| “Có hai bean definition singleton cùng lớp thì chỉ một object.” | Spring singleton thuộc **mỗi bean definition**, không phải class trong JVM. | Hai definition có thể có hai instance độc lập. |
| “Hai HTTP request luôn có hai aspect.” | HTTP request scope của **target** không quyết định aspect instance. | Xem mô hình của aspect và cấu hình scoped proxy. |
| “Một aspect singleton có field đếm tự an toàn khi concurrent.” | Nhiều thread có thể đồng thời dùng chung một aspect. | Giữ aspect stateless hoặc dùng dữ liệu đồng bộ/thread-safe đúng nhu cầu. |
| “`@Lazy` biến singleton thành prototype.” | `@Lazy` đổi thời điểm tạo, không đổi scope. | Scope vẫn là singleton trừ khi được cấu hình khác. |
| “AOP proxy và scoped proxy luôn là một.” | Một proxy dùng để chặn advice; proxy còn lại đại diện bean theo scope và chọn target. | Xác định cả hai lớp proxy khi debug. |
| “Gọi `this.run()` bên trong target vẫn đi qua advice.” | Self-invocation thường bỏ qua Spring AOP proxy. | Gọi qua Spring proxy từ bên ngoài hoặc thiết kế lại boundary. |
| “`perthis` cũng là mỗi thread.” | `this` của Spring AOP là proxy tại join point, không phải thread. | Chọn instance model theo đối tượng, không theo suy đoán concurrency. |

### Vì sao scoped proxy khiến `perthis` và `pertarget` phức tạp hơn?

Lấy một bean `request` được inject vào singleton qua **một scoped proxy**. Singleton thường giữ nguyên **proxy reference**, còn scoped proxy có thể chọn **target khác nhau tùy request**.

Trong cấu hình đó:
- Nếu pointcut `perthis` nhìn thấy cùng proxy identity, không thể suy ra có một aspect instance mới cho từng request chỉ vì target request thay đổi.
- `pertarget` được định nghĩa theo target object của join point, nhưng tương tác cụ thể với chuỗi nhiều proxy và target source cần kiểm tra đúng runtime/version.
- `@RequestScope` hoặc `@Scope(proxyMode = ...)` giải quyết vòng đời và lookup; chúng **không phải cú pháp thay thế** cho `@Aspect("perthis(...)")` hoặc `@Aspect("pertarget(...)")`.

Vì vậy, khi logic cần xử lý dữ liệu request, giải pháp bền vững thường là **dịch chuyển trạng thái request vào bean request-scoped rõ ràng** hoặc truyền thông tin vào advice bằng `JoinPoint`/parameters, thay vì dựa vào việc “aspect chắc sẽ có số lượng instance đúng bằng số request”.

## 9. Checklist chẩn đoán số lượng instance ở runtime

Khi quan sát aspect/service không như dự đoán:

1. **Xác định bean definition**: service được đăng ký bằng `@Component` hay `@Bean`? Có nhiều definition trùng class không? Có context cha–con không?
2. **Kiểm tra bean scope**: `singleton`, `prototype`, `request`, `session`? Nếu inject prototype vào singleton, prototype được cấp lúc nào?
3. **Kiểm tra aspect bean**: nó đã được Spring đăng ký chưa, scope là gì và được hạ tầng AOP phát hiện chưa?
4. **Kiểm tra per-clause**: `@Aspect` mặc định, `perthis`, `pertarget` hay một cú pháp không được phiên bản hiện tại hỗ trợ?
5. **Kiểm tra proxy và target**: `AopUtils.isAopProxy(bean)`, `AopUtils.isJdkDynamicProxy(bean)`, `AopUtils.isCglibProxy(bean)`; xem có thêm scoped proxy hay `TargetSource` động không.
6. **Kiểm tra lời gọi**: client có lấy bean từ context và gọi qua proxy? Điểm cắt có khớp method execution thực tế? Có self-invocation không?
7. **Kiểm tra concurrent state**: advice có dùng field mutable dùng chung không? Bộ đếm có cần `AtomicInteger`/`AtomicLong` hoặc tránh trạng thái không?
8. **Đọc lỗi khởi tạo**: nếu per-clause cần nhiều aspect instance nhưng bean bị cấu hình singleton, xử lý nguyên nhân scope/model; đừng tắt AOP chỉ để bỏ lỗi.

Ví dụ đoạn kiểm tra proxy (giả sử `service` là một biến Spring bean có sẵn, không phải chương trình chạy độc lập):

```java
System.out.println(AopUtils.isAopProxy(service));
System.out.println(AopUtils.isJdkDynamicProxy(service));
System.out.println(AopUtils.isCglibProxy(service));
```

Ba giá trị trên nói về **đối tượng proxy**, chưa đủ kết luận số lượng aspect instance. Muốn kiểm tra aspect, đối chiếu thêm các bean definition/aspect scope và theo dõi instance identity khi cần.

## 10. Kết luận và nguyên tắc thiết kế

Trong Spring, có hai bước cần tách bạch:

```text
Spring IoC:
  Bean definition + @Scope
        -> tạo, cấp, quản lý target bean / aspect bean theo scope

Spring AOP:
  @Aspect + per-clause + pointcut + advice
        -> chọn proxy/target phù hợp, gắn aspect instance,
           thực thi advice khi method được gọi qua Spring proxy
```

**Quy tắc thực hành:** Chọn bean scope theo vòng đời dependency/target; chọn aspect instantiation model theo *vòng đời trạng thái của advice*. Với phần lớn Spring AOP như logging, metrics và kiểm tra boundary, dùng aspect singleton không giữ trạng thái của từng lời gọi. Chỉ dùng `perthis`/`pertarget` khi thật sự cần trạng thái theo proxy/target và đã kiểm chứng trong bối cảnh Spring proxy thực tế.

### Tài liệu đối chiếu

- [Spring Framework — Aspect Instantiation Models](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/instantiation-models.html): mô hình singleton, `perthis`, `pertarget` và khả năng hỗ trợ phụ thuộc phiên bản.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): `singleton`, `prototype`, web scope, dependency và scoped proxy.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): kích hoạt Spring AOP, đăng ký aspect và yêu cầu dependency.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxy, `this`/target và self-invocation.
- [Spring Framework 6.1 — BeanFactoryAspectJAdvisorsBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/aop/aspectj/annotation/BeanFactoryAspectJAdvisorsBuilder.html): cách Spring tìm các `@Aspect` bean và xây dựng advisor.

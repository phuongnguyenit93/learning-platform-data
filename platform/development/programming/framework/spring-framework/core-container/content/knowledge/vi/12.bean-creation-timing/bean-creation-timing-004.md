# Proxy tại điểm tiêm `@Lazy` và thời điểm lỗi xuất hiện trong Spring Framework

## 1. Bài toán: bean được tạo lúc nào, và lỗi bị trì hoãn đến khi nào?

Spring IoC Container quản lý việc đăng ký bean definitions, giải quyết dependency và khởi tạo bean. Theo mặc định, nhiều singleton trong một `ApplicationContext` được tạo ngay khi context khởi động. Điều này có ích vì ứng dụng sớm phát hiện lỗi cấu hình, dependency và initialization.

Tuy nhiên, đôi khi một collaborator chỉ thực sự cần trong một nhánh hiếm gặp, mất thời gian khởi tạo hoặc có chi phí kết nối đến hệ thống bên ngoài. Spring cung cấp `@Lazy` để kiểm soát thời điểm tạo bean và **lazy-resolution proxy** để trì hoãn việc giải quyết dependency ở **điểm tiêm (injection point)**.

Hai đoạn code trông gần giống nhưng có ý nghĩa khác nhau:

```java
// 1. @Lazy trên bean definition.
@Bean
@Lazy
PaymentClient paymentClient() {
    return new RemotePaymentClient();
}
```

```java
// 2. @Lazy trên injection point.
@Bean
CheckoutService checkoutService(@Lazy PaymentClient client) {
    return new CheckoutService(client);
}
```

Các đoạn là **trích đoạn minh họa**, cần khai báo đầy đủ imports và domain classes mới compile. Trường hợp (1) điều khiển **có pre-instantiate bean `paymentClient` hay không**. Trường hợp (2) yêu cầu Spring cung cấp **một proxy** tại tham số `client`, để giải quyết bean thực khi proxy được sử dụng.

Đây không phải hai từ đồng nghĩa:

- Bean definition có `@Lazy` nhưng được **tiêm trực tiếp** vào eager singleton thì Spring vẫn có thể phải tạo bean ngay khi context khởi động.
- Injection point có `@Lazy` nhưng target bean là **eager singleton thông thường** thì target vẫn có thể đã được tạo trước lần gọi proxy đầu tiên.
- Khi cả target definition **và** injection point đều lazy, trong bối cảnh không có đường dependency/eager lookup khác kéo target vào, target có thể được tạo khi proxy thực sự được gọi.
- Nếu target bean **không tồn tại**, lazy proxy ở injection point vẫn có thể được tiêm; lỗi chỉ lộ ra khi proxy được gọi.
- Nếu target bean được chọn nhưng tạo thất bại, lỗi bean creation có thể xuất hiện trong lời gọi proxy đầu tiên — thay vì lúc tạo consumer.

Mục tiêu bài học:

1. Phân biệt `@Lazy` ở `@Bean`/`@Component`/`@Configuration` với `@Lazy` ở field, constructor parameter và method parameter injection.
2. Hiểu một lazy-resolution proxy làm gì và không làm gì.
3. Biết cách suy luận các thời điểm `register`, `refresh`, constructor, init callback, proxy invocation và destroy.
4. Nhận diện các lỗi startup, injection, first invocation và later invocation.
5. Hiểu quy tắc singleton target được cache sau khi resolve và non-singleton có thể được resolve lại mỗi lần truy cập.
6. Phân biệt lazy dependency với dependency tùy chọn; sử dụng `ObjectProvider` đúng khi không có bean.
7. Chạy ví dụ Java 17+ / Spring Framework 6.2 có nhiều context kiểm chứng các biến thể.
8. Có phương pháp kiểm thử, debug và áp dụng an toàn cho production.

## 2. Chọn đúng vị trí `@Lazy` để kiểm soát thời điểm lỗi

`@Lazy` trên **bean definition** (`@Bean`, component, configuration) quyết định liệu singleton target có bị eager pre-instantiation thông thường không. `@Lazy` trên **injection point** (tham số constructor/`@Bean`, field hoặc setter được Spring xử lý) yêu cầu một lazy-resolution **proxy** để consumer có thể tạo trước lúc cần target.

| Target bean | Cạnh injection vào eager consumer | Kết quả quan sát |
| --- | --- | --- |
| Singleton eager | `@Lazy Gateway` proxy | Proxy được tiêm, nhưng target vẫn có thể tạo ngay trong refresh |
| Singleton `@Lazy` | `Gateway` trực tiếp | Target bị tạo sớm để hoàn tất consumer |
| Singleton `@Lazy` | `@Lazy Gateway` proxy | Target có thể chờ đến lần gọi proxy đầu tiên |
| Không có target hợp lệ | `@Lazy Gateway` proxy | Proxy vẫn có thể được tiêm; lỗi thiếu dependency chuyển sang lúc invoke |
| Prototype | Lazy proxy | Target có thể được resolve lại cho từng method invocation; tránh dùng cho nhiều calls cần chung mutable state |

Ví dụ `@Bean @Lazy Gateway gateway()` kết hợp `consumer(@Lazy Gateway gateway)` chỉ thật sự hoãn target khi **không có đường eager khác** lấy bean trước. Cần dùng interface hoặc type có thể proxy; final class/method và những giới hạn của proxy có thể gây lỗi **ngay tại injection**, không chờ first use.

Bài này phân tích kỹ **vị trí và loại lỗi**: proxy creation error, bean lookup error, bean creation error và business invocation error là những tình huống khác nhau. Kiểm tra mốc refresh so với lần gọi đầu bằng marker hoặc `containsSingleton` trước khi dereference proxy.

## 3. Cơ chế lazy-resolution proxy tại điểm tiêm

Spring tạo một object đứng giữa consumer và target. Consumer giữ reference đến proxy; proxy giữ cơ chế tìm target thông qua bean factory/dependency descriptor.

```text
                     ApplicationContext.refresh()
                                |
                                v
                    EagerConsumer được tạo
                                |
                                v
            @Lazy dependency ở injection point
                                |
                                v
            Spring tạo lazy-resolution proxy
                                |
                                v
              Consumer giữ proxy reference
                                |
                    [chưa cần target]
                                |
               User gọi consumer.execute()
                                |
                                v
                  Proxy intercept lời gọi
                                |
                                v
          BeanFactory resolve target dependency
                 /             |             \
          tồn tại         không tồn tại      tạo lỗi
             |                 |               |
             v                 v               v
       Tạo/lấy target   thiếu bean error   BeanCreationException
             |
             v
       Gọi method của target
             |
             v
        Trả kết quả cho consumer
```

### 3.1. Proxy là một object thật được tiêm

`@Lazy` trên injection point không đưa vào Java `null` rồi tự đổi thành bean về sau. Nó đưa vào **một object proxy** mà consumer có thể giữ trong field, trả về qua getter hoặc truyền tiếp.

```java
class ClientConsumer {
    private final Client client;

    ClientConsumer(@Lazy Client client) {
        this.client = client;
    }

    Client getClient() {
        return client;
    }
}
```

Đây là snippet minh họa; cần imports, bean registration và interface `Client`. Khi container hỗ trợ proxy, `getClient() != null` không chứng minh có target bean. Nó chỉ chứng minh field giữ proxy reference.

### 3.2. Proxy không phải bản sao của target

Một lazy-resolution proxy không phải một object domain `new ExpensiveClient()` thứ hai. Nó là **cầu nối** tới container để lấy target. Khi target là singleton, proxy có thể cache singleton target sau lần resolution đầu tiên; những lần gọi sau sử dụng target ấy. Khi target không phải singleton, proxy có thể resolve target lại trên mỗi access, theo Javadoc của `@Lazy`.

Cần phân biệt:
- **Proxy identity:** consumer giữ cùng một proxy reference.
- **Target identity:** object đằng sau proxy có thể singleton, prototype hoặc scoped proxy target.
- **Bean definition name:** tên được container dùng để đăng ký target, không nhất thiết là Java class name.

### 3.3. Interface proxy và class-based proxy

Với injection type là interface, Spring có thể tạo JDK dynamic proxy implement interface ấy. Với concrete class injection, Spring có thể cần cơ chế class-based proxy; các class final, method final, visibility và cấu hình AOP có thể đặt ra giới hạn cho việc tạo/intercept proxy.

Đối với bài demo, chúng ta cố ý inject **interface `Gateway`** để JDK proxy semantics đơn giản và dễ xác minh. Đừng mặc định mọi `@Lazy` proxy sẽ có tên class cố định hoặc luôn dùng CGLIB.

### 3.4. Vì sao `getClass()` và `instanceof` không phải bằng chứng target đã tạo?

`proxy.getClass()` lấy Java runtime class của **proxy**, không tạo thành chứng cứ target bên trong đã được khởi tạo. `proxy instanceof Gateway` chỉ cho biết proxy implements interface/type `Gateway`. Cách kiểm tra target creation đáng tin hơn là:
- bộ đếm trong factory method/constructor;
- `beanFactory.containsSingleton("gateway")` khi target singleton;
- side effects được ghi log có chủ đích;
- assertion behavior sau lời gọi.

Đừng gọi `proxy.toString()`, `equals()` hoặc một business method chỉ để “kiểm tra là proxy” nếu bạn không muốn vô tình làm Spring resolve target. Tùy proxy implementation, những lời gọi đó có thể đi qua interceptor/target source.

## 4. Ba thời điểm khác nhau: inject proxy, resolve target, khởi tạo bean

Một ứng dụng có thể trải qua:

1. **Bean definition registration:** Spring biết metadata `gateway` và `consumer`, chưa chắc có instance.
2. **Consumer bean instantiation:** Spring tạo consumer và cung cấp proxy vào parameter `@Lazy Gateway`.
3. **Target dependency resolution:** proxy được gọi, Spring xác định bean target theo kiểu/qualifier/name và candidate rules.
4. **Target bean instantiation/initialization:** nếu target chưa tồn tại, BeanFactory tạo object, inject dependency, chạy lifecycle callbacks/post-processors.
5. **Target method invocation:** business method chạy trên target/proxy chain.
6. **Context closing:** container gọi destroy callbacks của managed singletons theo semantics scope/lifecycle.

Giai đoạn 3 và 4 có thể xảy ra đồng thời vào lời gọi đầu tiên, nhưng không bắt buộc. Nếu target eager singleton được tạo sẵn bởi context, proxy chỉ lấy bean đã tồn tại. Nếu target là prototype, nhiều lần gọi có thể dẫn đến nhiều target instances.

### 4.1. Phân biệt ẩn delay của resolve và delay của instantiate

`@Lazy` ở injection point trì hoãn **việc resolve target cho consumer đó**. Nó không phải công tắc đảm bảo target bean **không bao giờ** được tạo trước. Một bean khác có thể inject trực tiếp target, `@DependsOn` có thể kéo startup hoặc application code có thể gọi `context.getBean(Target.class)` từ sớm.

Bởi vậy, khi cần đo “lazy thực sự”, phải kiểm tra **mọi đường tạo target** trong context và target bean definition lazy policy.

### 4.2. Đừng tự nhận lazy là async

Lazy proxy xử lý lookup khi có lời gọi; mặc định business method vẫn chạy **đồng bộ trong luồng đang gọi**, trừ khi có một cơ chế async độc lập như `@Async` hoặc reactive pipeline.

Nếu target constructor block trên network, lời gọi proxy đầu tiên cũng có thể block trên network. Lazy chỉ dời latency tới thời điểm khác; nó không biến latency thành miễn phí.

### 4.3. Lazy không phải hot swap

Một singleton target sau khi được tạo không tự bị thay thế bằng một implementation khác khi property thay đổi. `@Lazy` không thay `@RefreshScope`, routing layer hay cơ chế runtime reconfiguration. Với prototype/scoped beans, behavior resolution theo scope có thể khác, nhưng không suy ra rằng thay config file sau `refresh()` sẽ tự đổi bean definitions.

## 5. Ma trận thời điểm khởi tạo

Giả sử có một singleton `Consumer` được tạo eagerly và một `Gateway`:

| Target definition | Injection point của Consumer | Đường tạo Gateway khác? | Kết quả điển hình lúc startup |
| --- | --- | --- | --- |
| Eager singleton | Inject trực tiếp | Không | Gateway được tạo khi startup |
| `@Lazy` singleton | Inject trực tiếp | Không | Gateway vẫn được tạo vì consumer cần target |
| Eager singleton | `@Lazy` proxy | Không | Gateway được pre-instantiate do chính definition eager |
| `@Lazy` singleton | `@Lazy` proxy | Không | Consumer tạo được, Gateway chưa cần khởi tạo |
| `@Lazy` singleton | `@Lazy` proxy | Có eager bean khác cần target | Gateway có thể vẫn được tạo khi startup |
| Prototype | Inject trực tiếp vào singleton | Không | Một prototype được cấp khi consumer tạo |
| Prototype | `@Lazy` proxy | Không | Target có thể được resolve mới cho mỗi method invocation |
| Không có bean | Inject trực tiếp required | Không | Thường lỗi trong startup/injection |
| Không có bean | `@Lazy` proxy | Không | Consumer có thể tạo được, lỗi khi gọi proxy |

Bảng giả định Spring injection-point proxy infrastructure đang hoạt động và những dependency types có thể proxy. Đây không phải cam kết cho mọi lifecycle/FactoryBean/custom BeanPostProcessor ngoài ví dụ.

### 5.1. `@Lazy` trên target **chưa đủ** nếu consumer eager

```java
@Bean
@Lazy
Gateway gateway() {
    return new RealGateway();
}

@Bean
Consumer consumer(Gateway gateway) {
    return new Consumer(gateway);
}
```

Spring cần Gateway để tạo Consumer; target bị kéo vào dù được đánh dấu lazy. Đây là nguyên tắc quan trọng của Spring reference.

### 5.2. `@Lazy` trên injection point **chưa đủ** nếu target eager

```java
@Bean
Gateway gateway() {
    return new RealGateway();
}

@Bean
Consumer consumer(@Lazy Gateway gateway) {
    return new Consumer(gateway);
}
```

Consumer nhận proxy, nhưng nếu `gateway` là non-lazy singleton được context eager pre-instantiate, target có thể đã được tạo trong startup. Đừng nhìn thấy injection proxy rồi khẳng định đã giảm thời gian tạo toàn bộ singleton.

### 5.3. Kết hợp đúng khi thực sự cần trì hoãn

```java
@Bean
@Lazy
Gateway gateway() {
    return new RealGateway();
}

@Bean
Consumer consumer(@Lazy Gateway gateway) {
    return new Consumer(gateway);
}
```

Trong một context không có đường nào khác resolve gateway, consumer có thể khởi động mà không phải khởi tạo gateway. Business method đầu tiên chạm proxy sẽ kích hoạt target resolution.

## 6. Khi nào lỗi xuất hiện?

Điểm quan trọng nhất của bài này là **thời điểm báo lỗi thay đổi theo dependency route**, dù bản chất lỗi giống nhau.

### 6.1. Target bean không tồn tại

Không có `Gateway` trong registry:

```java
@Component
class Consumer {
    private final Gateway gateway;

    Consumer(@Lazy Gateway gateway) {
        this.gateway = gateway;
    }

    String charge() {
        return gateway.pay();
    }
}
```

Đây là minh họa, cần imports/interface và bean registration. Theo Javadoc `@Lazy`, lazy-resolution proxy **vẫn được tiêm**, dù target chưa tồn tại. `ApplicationContext` có thể refresh thành công, nhưng khi `charge()` gọi `gateway.pay()`, proxy resolve dependency và Spring ném exception như `NoSuchBeanDefinitionException` trong một số đường lookup.

Nếu bỏ `@Lazy` tại injection point và vẫn required dependency, Spring thường phát hiện thiếu bean khi tạo Consumer. Đây là ý nghĩa của **fail-fast** so với **fail-late**.

### 6.2. Target bean definition có nhưng factory method/constructor lỗi

```java
@Bean
@Lazy
Gateway gateway() {
    throw new IllegalStateException("Remote configuration invalid");
}
```

Nếu Consumer nhận target qua `@Lazy Gateway` proxy và không ai tạo target lúc startup, context có thể refresh. Lời gọi đầu tiên đi qua proxy sẽ khiến BeanFactory thực thi factory method, dẫn tới `BeanCreationException` (thường bọc `IllegalStateException`).

Đừng nói “`@Lazy` bắt lỗi thay Spring” — lỗi vẫn xảy ra, chỉ được **dời sang mốc sử dụng target**. Trong production, điều này có thể là một request/queue message đầu tiên, khó quan sát hơn lỗi startup nếu không có logs/metrics đúng.

### 6.3. Target là eager singleton nhưng tạo lỗi

Nếu bean target không `@Lazy`:

```java
@Bean
Gateway gateway() {
    throw new IllegalStateException("Configuration invalid");
}
```

dù một consumer có `@Lazy Gateway` injection point, context vẫn có thể eager instantiate target singleton và thất bại **ngay lúc refresh**. Injection proxy không ngăn cơ chế eager initialization của target definition.

### 6.4. Target thành công nhưng business method lỗi

Target được tạo và initialized thành công không có nghĩa business method sẽ không throw. Lỗi nghiệp vụ như validation, network timeout hoặc database conflict có thể xảy ra ở **bất kỳ method call** nào, không riêng lời gọi đầu tiên qua proxy.

Hãy tách:
- **Dependency resolution failure:** không có/không chọn được ứng viên.
- **Bean creation failure:** constructor/factory/init callback lỗi.
- **Business invocation failure:** method chạy nhưng phát sinh lỗi nghiệp vụ.
- **Proxy creation failure:** không thể tạo proxy phù hợp cho injection type (ví dụ ràng buộc proxying của concrete/final class).

### 6.5. Lỗi proxy type có thể xuất hiện sớm

Nếu injection point yêu cầu một concrete final class không thể được subclass/proxy bằng chiến lược hiện có, Spring có thể thất bại **lúc tạo proxy/inject consumer**, trước khi bất kỳ business method nào chạy.

Do đó mệnh đề “mọi lỗi với `@Lazy` đều bị trì hoãn” là sai. Javadoc đảm bảo lazy target resolution semantics trong bối cảnh proxy được tạo thành công; lỗi cấu hình AOP/proxy và một số lỗi metadata vẫn có thể xảy ra khi context khởi động.

## 7. Optional dependency: đừng dùng proxy như phép kiểm tra có bean

Một mẫu dễ nhầm:

```java
@Autowired(required = false)
@Lazy
private OptionalGateway optionalGateway;
```

Ngay cả khi target không tồn tại, lazy-resolution proxy có thể được injected. Vì thế:

```java
if (optionalGateway != null) {
    optionalGateway.execute();
}
```

không chứng minh target có mặt. Chính lời gọi `execute()` có thể mới ném exception. Spring Javadoc cảnh báo injection-point lazy proxy có hành vi khó trực giác cho optional dependencies.

### 7.1. Dùng `ObjectProvider<T>` khi cần optional, lazy và điều khiển thời điểm lookup

```java
@Component
class NotificationService {
    private final ObjectProvider<OptionalGateway> gateways;

    NotificationService(
            ObjectProvider<OptionalGateway> gateways) {
        this.gateways = gateways;
    }

    void notifyIfConfigured() {
        OptionalGateway gateway = gateways.getIfAvailable();
        if (gateway != null) {
            gateway.execute();
        }
    }
}
```

Đây là code minh họa; cần imports và loại `OptionalGateway`. `ObjectProvider` thuộc `org.springframework.beans.factory`. Nó giữ **handle để tra cứu**, không phải dependency target đã resolve.

- `getObject()`: yêu cầu một object phù hợp, có thể throw khi không có hoặc ambiguous.
- `getIfAvailable()`: trả `null` khi không có, nhưng vẫn có thể báo lỗi nếu có nhiều ứng viên không phân giải được hoặc bean creation hỏng.
- `ifAvailable(Consumer<T>)`: chạy callback nếu có object; tránh nhầm “không có” với business method throw.
- `getIfUnique()`: hữu ích khi chỉ chấp nhận một ứng viên duy nhất; cần đọc semantics của qualifier/primary ở phiên bản Spring.

Dùng `ObjectProvider` không bảo đảm tránh exception nếu target **có definition nhưng tạo lỗi**. Nó giúp biểu diễn optional/late lookup rõ hơn injection proxy bị coi nhầm như một nullable field.

### 7.2. `Optional<T>` và `@Nullable` giải quyết vấn đề khác

Spring hỗ trợ optional dependency injection với `Optional<Gateway>` hoặc `@Nullable Gateway` ở những injection points phù hợp. Nhưng nếu consumer cần lookup lại tại **thời điểm sử dụng**, một provider thích hợp hơn: `Optional` được resolve tại injection time, trong khi `ObjectProvider` cho phép chủ động hỏi container khi cần.

Không gộp `@Lazy` và `Optional<T>` rồi giả định chúng luôn có cùng lifecycle semantics. Cần test cấu hình cụ thể.

### 7.3. Đừng dùng `@Lazy` để che config thiếu

Nếu Gateway là required business dependency, việc đẩy lỗi từ startup sang request đầu tiên thường làm hệ thống **kém tin cậy hơn**, không tốt hơn. Có thể dùng lazy để giảm chi phí khởi tạo khi chức năng chưa được gọi, nhưng vẫn cần readiness checks/integration tests đảm bảo những nhánh bắt buộc có đủ resources.

## 8. Singleton và prototype dưới lazy-resolution proxy

Javadoc Spring `@Lazy` nêu cơ chế caching khi target singleton được resolve lần đầu, và **re-resolution ở mỗi lần truy cập** khi target không phải singleton.

### 8.1. Singleton target

```java
@Bean
@Lazy
Gateway gateway() {
    return new DefaultGateway();
}

@Bean
Consumer consumer(@Lazy Gateway gateway) {
    return new Consumer(gateway);
}
```

Lần đầu consumer gọi `gateway.call()`, Spring tìm và khởi tạo singleton. Những lần gọi sau thường dùng cùng target singleton. Proxy không tạo một bean mới mỗi method invocation chỉ vì injection point là `@Lazy`.

### 8.2. Prototype target

```java
@Bean
@Scope("prototype")
RequestToken requestToken() {
    return new DefaultRequestToken();
}

@Bean
TokenService tokenService(@Lazy RequestToken token) {
    return new TokenService(token);
}
```

Một lazy-resolution proxy tới prototype dependency có thể yêu cầu BeanFactory resolve target **mỗi lần method được gọi qua proxy**. Điều này khác injection prototype trực tiếp vào singleton, nơi prototype thường chỉ được tạo một lần lúc singleton được khởi tạo.

Nhưng không đồng nhất proxy-per-invocation với **request scope** hoặc thread-local isolation. Nếu cần một object duy nhất xuyên suốt một HTTP request, dùng đúng web request scope/scoped proxy, không tạo prototype mới theo từng method invocation rồi kỳ vọng cùng state.

### 8.3. Lưu ý về stateful prototype

Giả sử `RequestToken` là mutable:

```java
token.setId("one");
return token.getId();
```

Với lazy prototype proxy re-resolving target cho mỗi method call, `setId(...)` và `getId()` **có thể thao tác trên hai prototype instances khác nhau**. Đây là một bẫy nghiêm trọng.

Nếu cần stateful object trong một use-case:
- dùng `ObjectProvider<RequestToken>.getObject()` **một lần**, lưu target trong local variable rồi thực hiện các methods liên tiếp;
- hoặc sử dụng scoped bean phù hợp với lifecycle use-case;
- không trông chờ proxy prototype bảo toàn state xuyên các lời gọi.

### 8.4. Singleton consumer giữ một proxy reference

`TokenService` là singleton và field `token` chỉ chứa **một proxy object**. Nhưng proxy có thể re-resolve prototype target khi cần. Vì thế field reference identity ổn định không đồng nghĩa target identity cố định.

## 9. Demo Java 17+ đầy đủ: 6 tình huống kiểm chứng

Dự án này dùng **Spring Framework 6.2.19** và Gradle, không cần Spring Boot, database hay network. Nó tạo các `AnnotationConfigApplicationContext` độc lập để chứng minh:

1. Target `@Lazy` + injection-point `@Lazy`: consumer khởi động trước target; lần gọi đầu tạo target singleton.
2. Prototype được inject qua lazy proxy: mỗi method invocation resolve target mới.
3. Thiếu target: proxy vẫn injected và lỗi xuất hiện lúc gọi.
4. `ObjectProvider`: dependency tùy chọn không có target được xử lý rõ ràng.
5. Target `@Lazy` nhưng consumer inject **trực tiếp**: target bị tạo lúc refresh để thỏa dependency.
6. Target eager hoặc factory lỗi: injection proxy không tự biến eager bean thành lazy, và lỗi bean creation có thể xuất hiện ở startup hoặc first invocation tùy cấu hình.

### 9.1. Cấu trúc

```text
lazy-injection-point-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── LazyInjectionDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'lazy-injection-point-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'LazyInjectionDemo'
}
```

Cần JDK 17+ và bản Gradle phù hợp. `spring-context` cung cấp `AnnotationConfigApplicationContext`, `@Bean`, `@Lazy`, bean factory injection và kéo theo những Spring modules cần cho proxy infrastructure.

### 9.2. Toàn bộ Java source

Lưu `src/main/java/LazyInjectionDemo.java`:

```java
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Scope;

public class LazyInjectionDemo {

    static final AtomicInteger lazyCreated = new AtomicInteger();
    static final AtomicInteger prototypeCreated = new AtomicInteger();
    static final AtomicInteger directCreated = new AtomicInteger();
    static final AtomicInteger eagerCreated = new AtomicInteger();

    public interface Gateway {
        String call();
    }

    public record DefaultGateway() implements Gateway {
        @Override
        public String call() {
            return "ok";
        }
    }

    public record GatewayConsumer(Gateway gateway) {
        public String use() {
            return gateway.call();
        }

        public boolean holdsJdkProxy() {
            return Proxy.isProxyClass(gateway.getClass());
        }
    }

    public interface SessionToken {
        String id();
    }

    public record DefaultToken(String value) implements SessionToken {
        @Override
        public String id() {
            return value;
        }
    }

    public record TokenConsumer(SessionToken token) {
        public String id() {
            return token.id();
        }
    }

    public interface MissingPort {
        String ping();
    }

    public record MissingConsumer(MissingPort port) {
        public boolean holdsJdkProxy() {
            return Proxy.isProxyClass(port.getClass());
        }

        public String invoke() {
            return port.ping();
        }
    }

    public record OptionalConsumer(
            ObjectProvider<MissingPort> provider) {
        public boolean exists() {
            return provider.getIfAvailable() != null;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class LazyConfig {

        @Bean
        @Lazy
        Gateway gateway() {
            lazyCreated.incrementAndGet();
            return new DefaultGateway();
        }

        @Bean
        GatewayConsumer gatewayConsumer(@Lazy Gateway gateway) {
            return new GatewayConsumer(gateway);
        }

        @Bean
        @Scope("prototype")
        SessionToken sessionToken() {
            int number = prototypeCreated.incrementAndGet();
            return new DefaultToken("token-" + number);
        }

        @Bean
        TokenConsumer tokenConsumer(@Lazy SessionToken sessionToken) {
            return new TokenConsumer(sessionToken);
        }

        @Bean
        MissingConsumer missingConsumer(@Lazy MissingPort missing) {
            return new MissingConsumer(missing);
        }

        @Bean
        OptionalConsumer optionalConsumer(
                ObjectProvider<MissingPort> provider) {
            return new OptionalConsumer(provider);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DirectConfig {

        @Bean
        @Lazy
        Gateway gateway() {
            directCreated.incrementAndGet();
            return new DefaultGateway();
        }

        @Bean
        GatewayConsumer gatewayConsumer(Gateway gateway) {
            return new GatewayConsumer(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class EagerConfig {

        @Bean
        Gateway gateway() {
            eagerCreated.incrementAndGet();
            return new DefaultGateway();
        }

        @Bean
        GatewayConsumer gatewayConsumer(@Lazy Gateway gateway) {
            return new GatewayConsumer(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DeferredFailureConfig {

        @Bean
        @Lazy
        Gateway gateway() {
            throw new IllegalStateException("late factory failure");
        }

        @Bean
        GatewayConsumer gatewayConsumer(@Lazy Gateway gateway) {
            return new GatewayConsumer(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class EagerFailureConfig {

        @Bean
        Gateway gateway() {
            throw new IllegalStateException("startup factory failure");
        }

        @Bean
        GatewayConsumer gatewayConsumer(@Lazy Gateway gateway) {
            return new GatewayConsumer(gateway);
        }
    }

    private static void check(boolean condition, String reason) {
        if (!condition) {
            throw new AssertionError(reason);
        }
    }

    private static void lazyAndOptionalCases() {
        try (var context = new AnnotationConfigApplicationContext(
                LazyConfig.class)) {

            GatewayConsumer gateway =
                    context.getBean(GatewayConsumer.class);
            TokenConsumer tokens =
                    context.getBean(TokenConsumer.class);
            MissingConsumer missing =
                    context.getBean(MissingConsumer.class);
            OptionalConsumer optional =
                    context.getBean(OptionalConsumer.class);

            boolean before = context.getBeanFactory()
                    .containsSingleton("gateway");
            check(!before, "gateway must not be created yet");

            boolean proxy = gateway.holdsJdkProxy();
            check(proxy, "expected interface lazy proxy");

            System.out.println("lazy.before=" + before);
            System.out.println("lazy.proxy=" + proxy);

            String first = gateway.use();
            boolean after = context.getBeanFactory()
                    .containsSingleton("gateway");
            String second = gateway.use();

            check("ok".equals(first) && "ok".equals(second),
                    "unexpected gateway result");
            check(after && lazyCreated.get() == 1,
                    "singleton target should be created once");

            System.out.println("lazy.call1=" + first);
            System.out.println("lazy.after=" + after);
            System.out.println("lazy.call2=" + second);
            System.out.println("lazy.created=" +
                    lazyCreated.get());

            String tokenOne = tokens.id();
            String tokenTwo = tokens.id();
            check(!tokenOne.equals(tokenTwo),
                    "prototype target should change");
            check(prototypeCreated.get() == 2,
                    "expected two prototype instances");

            System.out.println("prototype.first=" + tokenOne);
            System.out.println("prototype.second=" + tokenTwo);
            System.out.println("prototype.created=" +
                    prototypeCreated.get());

            boolean missingProxy = missing.holdsJdkProxy();
            check(missingProxy, "expected missing-port proxy");
            boolean missingFailure = false;
            try {
                missing.invoke();
            } catch (BeansException expected) {
                missingFailure = true;
            }
            check(missingFailure,
                    "missing target must fail on invocation");

            boolean optionalExists = optional.exists();
            check(!optionalExists, "missing port must be absent");

            System.out.println("missing.proxy=" + missingProxy);
            System.out.println("missing.failsOnCall=" +
                    missingFailure);
            System.out.println("optional.exists=" +
                    optionalExists);
        }
    }

    private static void directCase() {
        try (var context = new AnnotationConfigApplicationContext(
                DirectConfig.class)) {

            GatewayConsumer consumer =
                    context.getBean(GatewayConsumer.class);
            check(directCreated.get() == 1,
                    "direct injection should create lazy target");
            check(!consumer.holdsJdkProxy(),
                    "direct injection should hold target");

            System.out.println("direct.createdAtRefresh=" +
                    directCreated.get());
            System.out.println("direct.proxy=" +
                    consumer.holdsJdkProxy());
        }
    }

    private static void eagerCase() {
        try (var context = new AnnotationConfigApplicationContext(
                EagerConfig.class)) {

            GatewayConsumer consumer =
                    context.getBean(GatewayConsumer.class);
            check(eagerCreated.get() == 1,
                    "eager singleton should exist at refresh");

            System.out.println("eager.createdAtRefresh=" +
                    eagerCreated.get());
            System.out.println("eager.proxy=" +
                    consumer.holdsJdkProxy());
        }
    }

    private static void deferredFailureCase() {
        try (var context = new AnnotationConfigApplicationContext(
                DeferredFailureConfig.class)) {

            GatewayConsumer consumer =
                    context.getBean(GatewayConsumer.class);
            boolean failed = false;
            try {
                consumer.use();
            } catch (BeansException expected) {
                failed = true;
            }
            check(failed, "expected deferred bean creation failure");

            System.out.println("deferred.failureOnCall=" +
                    failed);
        }
    }

    private static void eagerFailureCase() {
        boolean failedAtRefresh = false;
        try (var context = new AnnotationConfigApplicationContext(
                EagerFailureConfig.class)) {
            throw new AssertionError("expected refresh to fail");
        } catch (BeansException expected) {
            failedAtRefresh = true;
        }
        check(failedAtRefresh, "expected startup failure");
        System.out.println("eager.failureAtRefresh=" +
                failedAtRefresh);
    }

    public static void main(String[] args) {
        lazyAndOptionalCases();
        directCase();
        eagerCase();
        deferredFailureCase();
        eagerFailureCase();
    }
}
```

### 9.3. Lệnh chạy

Trong thư mục `lazy-injection-point-demo`:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper trên Linux/macOS:

```bash
./gradlew run --quiet
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat run --quiet
```

Đầu ra từ `System.out.println`:

```text
lazy.before=false
lazy.proxy=true
lazy.call1=ok
lazy.after=true
lazy.call2=ok
lazy.created=1
prototype.first=token-1
prototype.second=token-2
prototype.created=2
missing.proxy=true
missing.failsOnCall=true
optional.exists=false
direct.createdAtRefresh=1
direct.proxy=false
eager.createdAtRefresh=1
eager.proxy=true
deferred.failureOnCall=true
eager.failureAtRefresh=true
```

Các Spring/Gradle logging messages có thể xuất hiện thêm, đặc biệt ở các contexts **cố ý throw** exceptions. Các dòng trên là output nghiệp vụ chủ động in; demo dùng `check(...)` để ném `AssertionError` nếu giả định không đúng.

### 9.4. Vì sao case 1 thật sự trì hoãn target?

`gateway()` được khai báo `@Bean @Lazy` nên singleton definition không bị pre-instantiate tự động. `gatewayConsumer(@Lazy Gateway gateway)` nhận một lazy proxy, không bắt BeanFactory tạo Gateway ngay. Khi gọi `gateway.use()` lần đầu, proxy resolve target và `gateway()` mới chạy. Bộ đếm tăng từ 0 lên 1; lần gọi thứ hai vẫn dùng singleton, bộ đếm giữ 1.

`containsSingleton("gateway")` kiểm tra singleton cache trong BeanFactory; nó không kiểm tra **có hay không bean definition**. Ngay cả khi `containsSingleton` trả false, bean definition vẫn có thể đã tồn tại hợp lệ.

### 9.5. Vì sao prototype tạo hai instances?

`sessionToken()` có `@Scope("prototype")`; lazy proxy được tiêm vào `TokenConsumer`. Khi consumer gọi `tokens.id()` hai lần, target resolution có thể tạo hai `DefaultToken`, từ `token-1` sang `token-2`. Đây là demonstration của Spring `@Lazy` non-singleton re-resolution, không phải một token tự thay đổi value trên cùng instance.

### 9.6. Vì sao missing target không phá startup?

`MissingConsumer` nhận `@Lazy MissingPort missing`. Spring có thể tạo proxy cho interface `MissingPort` mà chưa resolve target. `getClass()` trên proxy không làm bean xuất hiện. Chỉ khi `missing.invoke()` gọi `port.ping()`, BeanFactory mới cố resolve `MissingPort` và báo lỗi. Trong demo catch một `BeansException` để xác định vị trí xảy ra lỗi; production code nên log root cause và phân biệt thiếu bean với lỗi logic khác.

### 9.7. Vì sao `ObjectProvider` trả false?

`OptionalConsumer` nhận `ObjectProvider<MissingPort>`. Khi `exists()` gọi `getIfAvailable()`, không có bean `MissingPort` nên nó trả null; test in `optional.exists=false`. Đây là API hợp lý hơn khi muốn kiểm tra sự tồn tại của một dependency tùy chọn.

### 9.8. Vì sao direct injection kéo target lazy vào startup?

Trong `DirectConfig`, target Gateway được đánh dấu `@Lazy` nhưng `gatewayConsumer(Gateway gateway)` không có `@Lazy` trên parameter. Eager consumer cần target thật để chạy factory method, nên `gateway()` được gọi trong `refresh()`; `direct.createdAtRefresh=1` và `direct.proxy=false`.

### 9.9. Vì sao eager target vẫn được tạo dù consumer có proxy?

`EagerConfig.gateway()` không mang `@Lazy`. `AnnotationConfigApplicationContext` thường pre-instantiate non-lazy singletons, nên sau `refresh()` bộ đếm đã là 1. Consumer có injection-point `@Lazy` nên field vẫn có proxy, nhưng target đã được tạo; vì thế `eager.proxy=true` **không** có nghĩa `eager.createdAtRefresh` bằng 0.

### 9.10. Hai lỗi factory cùng một nguyên nhân nhưng khác thời điểm

`DeferredFailureConfig` đánh dấu target bean `@Lazy`, consumer nhận proxy. `refresh()` hoàn tất; lần gọi đầu mới tạo Gateway và throw `IllegalStateException` được Spring bọc thành bean creation error. Output `deferred.failureOnCall=true`.

`EagerFailureConfig` khai báo target eager, nên BeanFactory thực thi factory method lỗi trong startup, trước khi application kịp lấy consumer. Output `eager.failureAtRefresh=true`.

**Kết luận demo:** lựa chọn lazy/eager ảnh hưởng mốc lỗi xuất hiện, không làm lỗi biến mất.

## 10. Những lỗi dễ mắc khi dùng proxy ở điểm tiêm

| Triệu chứng / quan niệm | Nguyên nhân | Cách giải quyết |
| --- | --- | --- |
| “Đã dùng `@Lazy` nhưng startup vẫn chậm” | Target definition vẫn eager hoặc consumer khác cần target | Đánh dấu target lazy và kiểm tra mọi dependency edges |
| “Consumer tạo được nghĩa là target tồn tại” | Proxy được injected dù target chưa resolve | Kiểm tra target bằng provider/readiness test hoặc gọi use case |
| `@Autowired(required=false) @Lazy` vẫn không null | Lazy proxy luôn được tạo khi hỗ trợ | Dùng `ObjectProvider`/`Optional` phù hợp |
| Mất bean chỉ báo lỗi tại request đầu | Injection-point proxy làm fail-late | Test startup contract, readiness và critical path |
| Constructor target throw nhưng context vẫn refresh | Target lazy và proxy trì hoãn bean creation | Phân biệt startup và first-invocation failures |
| Context fail dù injection point lazy | Target eager hoặc proxy creation/config errors | Kiểm tra target definition/proxyability |
| `proxy.getClass()` không đúng implementation | Đó là class của proxy | Kiểm tra interface/behavior, không dựa exact proxy class |
| `proxy == target` là false | Proxy là object trung gian | Dùng contract method và bean identity thích hợp |
| Prototype method calls không chia sẻ state | Proxy resolve mới từng access | Lấy target một lần bằng provider nếu cần stateful use case |
| Self-invocation không qua proxy | Method call nội bộ trên target bỏ qua wrapper | Tái thiết kế call boundary, không coi lazy là AOP business feature |
| Final class/method proxying lỗi | Proxy strategy không thể subclass/intercept | Ưu tiên interface, kiểm tra proxy constraints |
| Lời gọi đầu có latency spike | Target initialization được chuyển vào request | Warmup/readiness hoặc pre-initialize có chủ đích |
| `@Lazy` nghĩ là chạy async | Nó chỉ dời thời điểm lookup/init | Dùng async infrastructure riêng nếu cần |
| Bean target có lỗi credentials đến khi user gọi mới biết | Missing config được phát hiện muộn | Validate configuration tại startup hoặc health check |
| Quên đóng context | Resource target được khởi tạo nhưng không cleanup | Đóng ApplicationContext khi thích hợp |
| `@Lazy` bị xóa trong refactor | Dependency trở thành eager và đổi mốc lỗi | Viết integration tests cho creation timing |
| Thay property sau refresh không làm target đổi | Lazy không phải hot reload | Dùng chính sách refresh/routing phù hợp |
| Dùng `@Lazy` để khắc phục vòng phụ thuộc | Chỉ trì hoãn một đường resolution | Refactor graph; test cycles/proxies/early references |
| Prototype được inject trực tiếp vào singleton | Target chỉ được giải quyết khi singleton tạo | Dùng provider hoặc lazy proxy nếu muốn mỗi-use lookup |

### 10.1. Đừng chẩn đoán qua thông báo exception ngắn

Một lỗi như `BeanCreationException` có thể bao nhiều root causes:
- một constructor ném `IllegalArgumentException`;
- bean definition thiếu property;
- condition/profile khiến dependency không được đăng ký;
- network client initialization fail;
- circular dependency;
- một proxy không được tạo với target type.

Hãy đọc full exception chain, tên bean, injection point, thread và mốc lỗi (during refresh vs first business call).

### 10.2. Lưu ý về AOP proxy xếp chồng

Target bean có thể đã được proxy bởi Spring AOP (transaction, cache, security). Lazy-resolution proxy là lớp trung gian cho **dependency resolution**, không tự cung cấp transaction/authorization. Khi gọi method, có thể đi qua lazy proxy rồi đến target bean vốn là AOP proxy.

Không unwrap/proxy-cast sang implementation class trong business code. Inject interface hoặc một public contract rõ. Kiểm thử transaction/caching behavior qua managed reference, không gọi object bằng `new`.

### 10.3. Hạn chế dùng lazy cho infrastructure bắt buộc

Transaction manager, security policy, database schema validation hoặc một client luôn được dùng ngay sau startup có thể cần fail-fast. Việc che lỗi cho tới khi traffic đến sẽ làm failure blast radius khó quản lý hơn. Nếu chọn lazy có lý do (startup cost lớn/feature optional), bổ sung readiness contract và test khởi tạo trên đường đi được yêu cầu.

## 11. So sánh lazy proxy với `ObjectProvider`, `Supplier` và explicit factory

| Đặc điểm | Injection-point `@Lazy` | `ObjectProvider<T>` | Inject trực tiếp `T` |
| --- | --- | --- | --- |
| Consumer nhận | Proxy typed as T | Provider handle | Target bean/proxy do container trả |
| Khi resolve target | Khi gọi qua proxy | Khi code gọi `getObject/getIfAvailable` | Trong DI, trước consumer ready |
| Missing target | Có thể fail khi invoke proxy | `getIfAvailable` biểu thị vắng mặt; `getObject` báo lỗi | Required injection thường fail sớm |
| Singleton caching | Theo target scope/proxy semantics | BeanFactory singleton semantics | Cùng reference singleton |
| Prototype mỗi-use | Có thể re-resolve từng proxy invocation | Mỗi `getObject()` có thể lấy prototype mới | Singleton consumer giữ một prototype đã inject |
| Kiểm soát lookup | Ngầm qua lời gọi method | Tường minh tại điểm use | Không có |
| Dễ review dependencies | Vừa, proxy ẩn resolution | Rõ nếu provider được đặt tên đúng | Rõ |
| Nhu cầu | Hoãn gọi target mà vẫn dùng interface trực tiếp | Optional/multi-candidate/runtime lookup | Required DI, fail-fast |

### 11.1. Khi nào chọn `ObjectProvider`?

Dùng provider khi bạn cần:
- kiểm tra một dependency có tồn tại không;
- lấy một prototype mới **một lần cho một unit of work**;
- chủ động xử lý thiếu/multiple candidates;
- chọn thời điểm lookup minh bạch để tính toán cache/retry;
- triển khai fallback service khi feature không được cài.

Ví dụ:

```java
void process(ObjectProvider<SessionToken> provider) {
    SessionToken token = provider.getObject();
    token.assign("order-1");
    token.consume();
}
```

Snippet trên cần `SessionToken` API có hai methods minh họa. Cả hai calls trên cùng **local target instance**. Nếu thay bằng lazy prototype proxy và gọi hai methods trên proxy, target có thể khác nhau giữa hai lời gọi.

### 11.2. Khi nào chọn injection-point `@Lazy`?

Khi dependency bắt buộc **sẽ tồn tại**, nhưng consumer không cần gọi nó lúc tạo; API interface ổn định; bạn muốn tránh lookup boilerplate và chấp nhận rủi ro phát hiện lỗi muộn cùng chi phí proxy.

Ví dụ một module reporting lâu lâu mới chạy, trong khi phần main business không phụ thuộc module reporting trong mỗi request. Dù vậy, vẫn nên validate module quan trọng trước khi nhận traffic cần đến nó.

### 11.3. Khi nào nên tránh cả hai?

Nếu consumer luôn dùng dependency ngay trong constructor/init method, hoặc resource bắt buộc để application hoạt động, direct constructor DI có thể rõ và fail-fast hơn. Nếu cần async/background creation, hãy sử dụng startup scheduling/background initialization features tương ứng; `@Lazy` đơn thuần không lập lịch thread.

## 12. Kiểm thử đúng thời điểm và đúng ranh giới

### 12.1. Test 1 — target singleton chưa được tạo sau refresh

```java
try (var context = new AnnotationConfigApplicationContext(
        LazyInjectionDemo.LazyConfig.class)) {
    boolean created = context.getBeanFactory()
            .containsSingleton("gateway");
    if (created) {
        throw new AssertionError("Gateway created too early");
    }
}
```

Đây là **test fragment** theo demo mục 9, cần imports/tên package phù hợp. Nó kiểm chứng mốc tạo bean mà chỉ nhìn log startup có thể bỏ sót.

### 12.2. Test 2 — target tạo đúng một lần

```java
GatewayConsumer consumer = context.getBean(
        GatewayConsumer.class);
consumer.use();
consumer.use();
if (createdCounter.get() != 1) {
    throw new AssertionError("Expected singleton init once");
}
```

Đây là **pseudo-test fragment**: `createdCounter` là counter do test setup cung cấp. Nó biểu diễn cách xác minh singleton cache/creation thay vì chỉ quan sát output hai calls giống nhau.

### 12.3. Test 3 — dependency không tồn tại thì exception ở invocation

- Tạo context với consumer `@Lazy MissingPort` nhưng không khai bean MissingPort.
- Xác nhận context refresh thành công.
- Xác nhận proxy reference tồn tại.
- Gọi `port.ping()` và kiểm tra exception family/root cause.
- Ghi rõ “first method invocation failed” trong assertion message.

Điều này giúp tránh regression: một refactor bỏ `@Lazy` có thể chuyển lỗi từ invocation sang refresh; test sẽ chỉ ra sự thay đổi.

### 12.4. Test 4 — cùng lỗi nhưng eager bean gây fail-fast

Định nghĩa bean target eager với factory method throw. Đảm bảo `new AnnotationConfigApplicationContext(Config.class)` thất bại. Nếu bạn chỉ catch mọi `Exception` rồi coi test pass, có thể che sai lỗi XML/annotation/constructor khác; nên inspect root cause và bean name.

### 12.5. Test 5 — prototype re-resolution

```java
String first = tokenConsumer.id();
String second = tokenConsumer.id();
if (first.equals(second)) {
    throw new AssertionError("Expected distinct targets");
}
```

Trích đoạn demo giả định target tạo ID khác nhau. Đây là test của scope target, không phải test `proxy != target`.

### 12.6. Test 6 — không tạo target khi chỉ inspect proxy class

Nếu muốn bảo đảm một getter/proxy check không kích hoạt target, so counter trước/sau `Proxy.isProxyClass(proxy.getClass())`. Hạn chế việc vô tình gọi `toString` trong logger hoặc debugger watches khi test “chưa resolve target”.

### 12.7. Test 7 — optional dependency thay bằng provider

Khai `ObjectProvider<MissingPort>` và kiểm tra `getIfAvailable() == null` khi không có provider. Sau đó đăng ký bean phù hợp trong **context khác** để thử branch có provider. Tránh đăng ký runtime vào một context đã refresh khi đang phục vụ ứng dụng, vì bean registry concurrent mutation không phải workflow an toàn mặc định.

## 13. Những câu hỏi thường gặp

### 13.1. `@Lazy` ở constructor có làm constructor chạy muộn không?

Nếu annotation đặt trên **tham số constructor** `Consumer(@Lazy Gateway gateway)`, constructor Consumer **vẫn chạy** khi Consumer bean được tạo. Nó nhận proxy. Annotation đó không làm chính Consumer bean lazy. Muốn Consumer lazy, annotate **definition** của Consumer với `@Lazy` hoặc cấu hình tương ứng.

### 13.2. Có phải bean target luôn được tạo tại business method đầu tiên?

Không. Nếu target eager singleton, nó có thể được tạo lúc refresh; nếu dependency khác cần nó, cũng có thể bị kéo vào sớm; nếu target đã có, proxy chỉ lookup. Câu đúng hơn: injection-point proxy **resolve target khi bị gọi**, còn **target creation** chỉ xảy ra nếu bean chưa tồn tại và scope/lifecycle yêu cầu tạo.

### 13.3. Injection point `@Lazy` có bắt buộc dùng với `@Autowired`?

Javadoc mô tả nó trên injection points được đánh dấu `@Autowired` hoặc `@Inject`, và Spring bean factory method parameters cũng có cơ chế dependency resolution tương ứng. Trong JavaConfig, `@Bean Consumer consumer(@Lazy Gateway gateway)` là ví dụ đã được thiết kế để hoạt động. Nếu bạn tự tạo Consumer bằng `new Consumer(...)` ngoài Spring, annotation trên parameter không được JVM tự diễn giải thành proxy.

### 13.4. Một annotation `@Lazy` trên interface có tự làm mọi implementation lazy không?

Không theo mặc định. Bean definitions và injection points mới là nơi Spring áp dụng metadata phù hợp. Hãy kiểm tra target implementation beans thực tế và injection points; không dựa vào annotation tùy ý trên một interface để suy ra tất cả candidate beans đều lazy.

### 13.5. Vì sao interface injection thường dễ hơn với proxy?

JDK dynamic proxy chỉ cần implement interface. Concrete class proxy có thể phụ thuộc subclassing và gặp ràng buộc final classes/methods. Interface contract giúp giảm coupling giữa consumer và implementation và dễ tạo proxy hơn. Đây là khuyến nghị, không phải yêu cầu rằng mọi dependency trong Spring phải là interface.

### 13.6. Proxy có cache kết quả method không?

Không. Singleton target caching và **method result caching** là hai chuyện khác nhau. Lazy-resolution proxy có thể giữ singleton target reference nhưng không tự ghi nhớ output của `gateway.call()`. Nếu method gọi database hai lần, hai calls vẫn có thể thực hiện nghiệp vụ hai lần, trừ khi có caching khác.

### 13.7. Proxy tạo ra có phải `@Transactional` proxy không?

Không chỉ vì `@Lazy`. Lazy-resolution proxy phục vụ deferred dependency resolution. Một target bean có thể được các post-processors AOP tạo thêm proxy cho transactions/caching/security, nhưng đó là cơ chế độc lập cần configuration phù hợp.

### 13.8. Nếu gọi proxy từ nhiều threads cùng lúc thì sao?

Với singleton bean, BeanFactory thường bảo đảm singleton creation semantics, nhưng thời gian chờ/latency khi nhiều threads cùng chạm lazy target lần đầu cần được đo trong workload thật. Với prototype, nhiều invocations có thể lấy nhiều instances. Tránh dựa vào số lượng factory calls/ordering trong concurrency tests nếu chưa kiểm tra bean scope và application synchronization.

### 13.9. Lazy giúp xử lý circular dependency không?

Nó có thể trì hoãn một edge trong dependency graph và giúp một số trường hợp khởi tạo qua proxy, nhưng không biến graph vòng thành thiết kế tốt; errors có thể chuyển từ startup sang runtime. Hãy tái thiết kế module boundaries, event/callback hoặc factory abstraction để loại vòng khi có thể.

### 13.10. Có nên cho mọi bean đều lazy để startup nhanh?

Không mặc nhiên. Eager singleton creation giúp fail-fast, warm caches và kiểm chứng infrastructure trước khi nhận traffic. Lazy quá rộng dời lỗi, memory/CPU spikes sang critical path đầu tiên; nên tối ưu bằng profiling, startup metrics và feature-specific policies.

## 14. Bài tập có đáp án

### Bài 1 — Annotation đặt ở đâu?

`@Bean @Lazy Gateway gateway()` và `@Bean Consumer consumer(Gateway gateway)`. Khi Consumer eager, Gateway có chắc không được tạo ở startup?

**Đáp án:** Không. Dependency của eager Consumer kéo target lazy vào bean creation.

### Bài 2 — Chỉ injection point lazy

`@Bean Gateway gateway()` (eager) và `consumer(@Lazy Gateway gateway)`. `proxy` xuất hiện có chứng minh target chưa tạo không?

**Đáp án:** Không. Target eager singleton có thể được pre-instantiate khi refresh.

### Bài 3 — Cả definition và injection point lazy

`@Bean @Lazy Gateway gateway()` và consumer nhận `@Lazy Gateway`, không có reference khác tới Gateway. Mốc tạo target dự kiến?

**Đáp án:** Lần gọi phương thức đầu tiên qua lazy proxy (hoặc một lookup/đường sử dụng khác tạo bean trước).

### Bài 4 — Thiếu target

Không có `MissingPort` bean nhưng consumer có `@Lazy MissingPort`. Context có thể refresh thành công không?

**Đáp án:** Có nếu proxy được tạo hợp lệ. Khi gọi method trên proxy, BeanFactory có thể báo missing bean.

### Bài 5 — Nullable field

`@Autowired(required=false) @Lazy Gateway gateway`. `gateway != null` có khẳng định bean Gateway thực sự tồn tại không?

**Đáp án:** Không. Proxy reference có thể không null dù target missing. Dùng `ObjectProvider.getIfAvailable()` hoặc policy optional rõ.

### Bài 6 — Proxy là bean thật?

Một consumer giữ `Gateway` proxy và một lần gọi method kích hoạt target singleton. Có phải hai Gateway domain instances được tạo?

**Đáp án:** Không. Proxy là object trung gian; target singleton là managed domain bean. Proxy identity và target identity khác nhau.

### Bài 7 — Singleton target

Consumer gọi cùng method qua lazy proxy năm lần. Có bắt buộc factory `@Bean Gateway` chạy năm lần không?

**Đáp án:** Không; với target singleton và không có reset, factory thường chạy một lần khi target được tạo.

### Bài 8 — Prototype target

Consumer có `@Lazy Token token`, target Token prototype. Hai lời gọi `token.id()` có thể lấy hai target objects không?

**Đáp án:** Có. Lazy-resolution proxy có thể re-resolve non-singleton mỗi access.

### Bài 9 — Stateful prototype

`token.setValue("A")` và ngay sau đó `token.getValue()` trên một lazy prototype proxy. Có bảo đảm get trả A không?

**Đáp án:** Không. Hai calls có thể resolve hai instances khác nhau. Dùng provider để lấy một prototype target duy nhất cho unit of work.

### Bài 10 — Lỗi lúc nào?

Target `@Bean @Lazy Gateway gateway()` ném exception trong factory method, consumer nhận `@Lazy Gateway`. Không có lookup khác. Lỗi nhiều khả năng lộ ra ở đâu?

**Đáp án:** Khi method đầu tiên qua proxy làm BeanFactory tạo target.

### Bài 11 — Factory eager lỗi

Bỏ `@Lazy` khỏi target definition, giữ `@Lazy` ở consumer injection point. Factory ném exception. Có chắc context vẫn refresh không?

**Đáp án:** Không. Eager singleton creation có thể fail trong refresh.

### Bài 12 — Lazy là async?

Một Gateway constructor mất 5 giây. Sử dụng lazy proxy có làm call đầu không chờ 5 giây không?

**Đáp án:** Không. Call đầu có thể chờ creation đồng bộ. Async cần cơ chế riêng.

### Bài 13 — Missing candidate và provider

`ObjectProvider<Gateway>.getIfAvailable()` khi không có target thường trả gì?

**Đáp án:** `null` theo contract khi không có ứng viên. Nếu candidate tồn tại nhưng khởi tạo lỗi hoặc ambiguity, vẫn có thể có exception.

### Bài 14 — Proxy getClass

`Proxy.isProxyClass(client.getClass())` là true. Có chứng minh lazy target đã được tạo không?

**Đáp án:** Không. Nó nhận diện class proxy, không khẳng định target instantiation.

### Bài 15 — Annotation trên bean definition

`@Lazy` chỉ đặt trên `@Component HeavyJob`, một singleton khác inject `HeavyJob` trực tiếp. Container có thể tạo HeavyJob khi startup?

**Đáp án:** Có, vì phải thỏa dependency eager.

### Bài 16 — Proxy và transaction

Một `@Lazy` proxy giữ target có `@Transactional`. Có thể loại bỏ transaction infrastructure vì đã có proxy lazy không?

**Đáp án:** Không. Lazy resolution không thay transaction interception/advisor/manager.

### Bài 17 — Thời điểm khởi tạo Consumer

Consumer có constructor parameter `@Lazy Gateway` và Consumer bản thân là eager singleton. Consumer constructor chạy khi nào?

**Đáp án:** Khi Spring khởi tạo Consumer trong startup. Chỉ dependency target resolution được trì hoãn theo proxy.

### Bài 18 — Exception delayed

Production chạy bình thường suốt 2 giờ, đến request sử dụng hiếm gặp mới fail tạo một lazy target. Vì sao đây là trade-off?

**Đáp án:** Startup nhanh/fail-late đánh đổi khả năng phát hiện config/dependency errors sớm. Cần readiness/integration test/warmup policy tương ứng với mức độ quan trọng.

## 15. Checklist áp dụng `@Lazy` tại injection point

- Đã phân biệt `@Lazy` trên **target definition** với `@Lazy` trên **injection point** chưa?
- Target thực sự cần lazy hay đang được eager tạo qua một dependency khác?
- Consumer có inject một **proxy** đúng type (thường là interface) không?
- Có concrete final types/methods hoặc class-based proxy constraints không?
- Dependency có thật sự tùy chọn không? Nếu có, `ObjectProvider` có diễn đạt tốt hơn không?
- Có đang dùng `proxy != null` để xác nhận bean tồn tại một cách sai lầm không?
- Lỗi target creation có bị chuyển từ startup sang request đầu, gây downtime không?
- Có test cả no-target, broken-factory, eager-factory và healthy-target cases không?
- Scope target là singleton hay prototype? Mỗi proxy invocation resolve cùng hay khác target?
- Với stateful prototype, code có vô tình gọi nhiều methods qua proxy trên các instances khác nhau không?
- Lazy proxy có làm chậm critical path đầu tiên? Có readiness/warmup strategy không?
- Business method có được gọi qua Spring-managed proxy chain khi cần transactions/caching không?
- Có đang nhầm lazy với async/background execution hoặc runtime refresh không?
- Test dùng creation counters/`containsSingleton` và assert thời điểm thay vì chỉ inspect proxy class chưa?
- Context cleanup và errors/logs/metrics có được xử lý đúng không?

## 16. Tổng kết

Trong Spring Core Container, **`@Lazy` trên bean definition** điều chỉnh việc bean có được eagerly pre-instantiated không; **`@Lazy` tại injection point** tạo một **lazy-resolution proxy** để hoãn việc giải quyết target dependency tới khi proxy được sử dụng. Cần xem cả hai phía và mọi dependency edges để kết luận target thực sự được tạo muộn.

Proxy luôn là object được injected thành công khi proxy creation hợp lệ; **một target thiếu có thể chỉ bị phát hiện khi gọi proxy**. Điều đó làm optional dependencies khó trực giác. `ObjectProvider` biểu đạt việc lookup tùy chọn/chủ động tốt hơn. Với singleton target, lazy proxy có thể cache target sau lần resolve đầu; với non-singleton, nó có thể resolve lại từng access. Vì thế phải cẩn thận với prototype stateful beans.

Hãy lựa chọn lazy vì **lý do startup/chi phí/lifecycle cụ thể**, không coi nó như cách sửa dependency graph thiếu hoặc cách làm biến mất exception. Điều quan trọng không chỉ là “bean được tạo muộn hơn”, mà là **lỗi được phát hiện muộn hơn ở đâu**, consumer nào chịu latency và các đường sử dụng quan trọng có được kiểm chứng trước production traffic hay chưa.

### Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — `@Lazy` Javadoc (definition vs injection-point proxy, missing target và singleton/prototype)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Lazy.html).
- [Spring Framework 6.2 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html).
- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html).
- [Spring Framework 6.2 — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html).
- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html).
- [Spring Framework 6.2 — `ContextAnnotationAutowireCandidateResolver` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/ContextAnnotationAutowireCandidateResolver.html).
- [Spring Framework 6.2 — `ObjectProvider` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/ObjectProvider.html).

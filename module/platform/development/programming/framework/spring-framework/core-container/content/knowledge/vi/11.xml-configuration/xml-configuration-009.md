# Chuyển đổi cấu hình XML sang Java mà giữ nguyên hành vi — Spring Core Container

## 1. Mục tiêu: giữ hợp đồng runtime, không chỉ đổi cú pháp

Spring Framework hỗ trợ XML bean definitions và Java-based configuration (`@Configuration`, `@Bean`, `@Import`). Khi chuyển đổi một ứng dụng từ XML sang Java, việc thay thế `<bean>` bằng `@Bean` chỉ là phần dễ nhìn thấy. Phần khó là **giữ đúng hành vi của container**: beans nào tồn tại, chúng tên gì, được tạo khi nào, scope gì, nhận dependency nào và được khởi tạo/hủy như thế nào.

Ví dụ XML:

```xml
<bean id="repository" class="demo.Repository"/>
<bean id="service" class="demo.Service">
    <constructor-arg ref="repository"/>
    <property name="prefix" value="INV:"/>
</bean>
```

JavaConfig có thể viết:

```java
@Configuration(proxyBeanMethods = false)
class ApplicationConfig {
    @Bean("repository")
    Repository repository() {
        return new Repository();
    }

    @Bean("service")
    Service service(Repository repository) {
        Service service = new Service(repository);
        service.setPrefix("INV:");
        return service;
    }
}
```

Hai ví dụ này là **mã minh họa**, cần định nghĩa domain classes và imports. Chúng có thể tạo ra cùng object graph, nhưng chưa chứng minh mọi hợp đồng đều giống nhau: XML cũ còn có thể có aliases, profiles, `depends-on`, custom init/destroy callbacks, prototype scopes, namespace infrastructure hoặc properties được resolve theo một thứ tự ưu tiên cụ thể.

**Chuyển đổi thành công** là khi cùng bộ đầu vào và môi trường, consumer vẫn quan sát thấy hành vi đúng như trước, trừ những khác biệt đã được đội dự án chủ động phê duyệt.

Bài học tập trung vào:

- Kiểm kê đầy đủ nguồn XML, bean definitions và metadata.
- Bảng ánh xạ XML → JavaConfig cho dependency injection, bean names, aliases, scopes, lazy, profiles, ordering và lifecycle.
- Các trường hợp không có phép chuyển 1:1 như `FactoryBean`, lookup-method injection và custom namespaces.
- Tích hợp XML/Java tạm thời bằng `@ImportResource` và chiến lược tránh đăng ký trùng.
- Ví dụ Java 17+ Spring Framework 6.2 với **hai context độc lập** và assertions so sánh output/identity/lifecycle.
- Test hồi quy, checklist triển khai, lỗi phổ biến và bài tập có lời giải.

## 2. “Parity” là gì và nên đo ở đâu?

Một phép so sánh class names đơn thuần không đủ. Cần phân biệt các hợp đồng:

| Nhóm hợp đồng | Điều cần giữ | Ví dụ lỗi khi migrate |
| --- | --- | --- |
| Bean registration | Những bean names/types có mặt trong đúng context | Bỏ bean cũ hoặc vô tình scan thêm bean |
| Naming/alias | Bean id, alias và lookup theo chuỗi | `getBean("billingGateway")` không còn hoạt động |
| Injection | Consumer nhận chính collaborator trước đây | Chuyển `ref="safeStore"` sang inject by type rồi nhận `fastStore` |
| Scope | Singleton, prototype hoặc web/custom scope | Prototype biến thành singleton |
| Lazy/eager | Thời điểm bean được tạo | Bean lazy bị tạo ngay lúc refresh |
| Lifecycle | Init/destroy method, callbacks, shutdown | Bỏ `stop()` hoặc gọi `start()` hai lần |
| Ordering | `depends-on` và các dependencies gián tiếp | Infrastructure chưa sẵn sàng khi service init |
| Config values | Literals, nulls, collections, property sources | Endpoint thay đổi vì precedence khác |
| Conditions | Active profile/conditional metadata | Production nhận dev bean |
| Candidate rules | Primary/qualifier/autowire-candidate | Hai implementations trở nên ambiguous |
| Framework infrastructure | Transactions/AOP/cache/async/schedulers | Logic vẫn chạy nhưng transaction không rollback |
| Ownership | ApplicationContext cha/con, scope boundary | Bean được chuyển sang context khác |
| External behavior | I/O, database, messaging, side effects | Job/listener chạy hai lần sau migration |

Không nhất thiết giữ nguyên tất cả **chi tiết triển khai**. Chẳng hạn `AnnotationConfigApplicationContext` có thể đăng ký thêm những Spring infrastructure definitions so với `ClassPathXmlApplicationContext`. Thay vì đòi `getBeanDefinitionCount()` bằng nhau tuyệt đối, hãy so sánh **bean contract** và kết quả sử dụng thực tế.

### 2.1. Phân biệt behavioral và structural parity

Hai configurations có thể khác nhau về cấu trúc mà vẫn đúng hành vi:

- XML `<constructor-arg ref=...>` chuyển thành factory-method parameter.
- XML `<property value=...>` chuyển thành lời gọi setter trong `@Bean` method.
- XML `<import resource=...>` chuyển thành `@Import(JavaConfig.class)` sau khi nguồn đó được migrate.
- XML name/alias được giữ trong `@Bean(name={"primary","alias"})`.

Ngược lại, giữ cùng implementation class nhưng thay scope, bỏ alias hoặc mất lifecycle hook là **không tương đương**.

### 2.2. Định nghĩa ranh giới kiểm chứng

Trong một application có cả root và servlet child contexts, cùng một type có thể tồn tại hai instances hợp lệ. Hãy kiểm tra từ **cùng điểm nhìn consumer**: context nào sở hữu bean, tên nào được lookup, proxy nào được truyền cho service. Không so một singleton XML ở child context với singleton JavaConfig ở root rồi tuyên bố tương đương chỉ vì class giống nhau.

## 3. Trước khi viết Java: kiểm kê cấu hình XML thực sự được load

Một dự án có thể chứa:

```text
config/
├── root.xml
├── persistence.xml
├── services.xml
├── integration/
│   ├── messaging.xml
│   └── transactions.xml
└── environments/
    ├── dev.xml
    └── prod.xml
```

Entry point có thể gọi:

```java
new ClassPathXmlApplicationContext(
        "config/root.xml",
        "config/services.xml");
```

hoặc XML chứa `<import resource="..."/>` bắc cầu. Một library JAR cũng có thể mang XML được nhập từ application.

**Nên kiểm kê:**

1. Những XML resources được load ở runtime, không chỉ file có tên “applicationContext”.
2. `<import>` bắc cầu và nhóm `<beans profile=...>`.
3. Bean ids, aliases, types, scopes, `lazy-init`, `depends-on`, init/destroy, primary, qualifiers.
4. Các constructor/property values và explicit `ref` theo tên.
5. Property placeholders, bean factory post-processors và precedence của property sources.
6. Các namespace handler `context`, `tx`, `aop`, `task` hoặc thư viện thứ ba.
7. `FactoryBean`, `factory-bean`, `factory-method`, inner beans, lookup-method, bean definition inheritance.
8. Các test/integrations dùng `getBean("name")` hay SpEL bean references theo chuỗi.
9. Beans được đăng ký qua component scan ngoài XML explicit definitions.
10. Parent-child contexts và những beans có external side effects.

Ví dụ bảng kiểm kê:

| Bean | Tên khác | Scope | Dependencies | Init/Destroy | Đặc điểm |
| --- | --- | --- | --- | --- | --- |
| `catalogRepository` | — | singleton | — | — | Managed repository |
| `catalogService` | `publicCatalog` | singleton | `catalogRepository` | `start/stop` | `depends-on="startupMarker"` |
| `ticket` | — | prototype | — | — | Hai lookups phải khác instances |
| `lazyFormatter` | — | lazy singleton | — | — | Tạo khi lookup |
| `startupMarker` | — | singleton | — | — | Initialization dependency |

Demo ở mục 10 sẽ hiện thực toàn bộ bảng này trên cả XML và JavaConfig, rồi kiểm tra tự động.

## 4. Ánh xạ XML → JavaConfig: bản tra cứu thực hành

| XML | JavaConfig | Kiểm tra |
| --- | --- | --- |
| `<bean id="x" class="pkg.X"/>` | `@Bean("x") X x()` | Bean type và name |
| `<alias name="x" alias="publicX"/>` | `@Bean(name={"x","publicX"})` | Hai names cùng bean |
| `<constructor-arg ref="repo"/>` | Factory method nhận `Repo repo` | Đúng bean instance |
| `<constructor-arg value="5"/>` | `new X(5)` hoặc config value | Conversion/default |
| `<property name="enabled" value="true"/>` | `obj.setEnabled(true)` | Giá trị và timing |
| `<property name="store" ref="store"/>` | Inject Store param rồi `setStore(store)` | Không tự tạo raw dependency |
| `<list>/<map>/<props>` | Java collections/Properties | Content, mutability, order |
| `scope="singleton"` | `@Bean` mặc định | Per-container singleton |
| `scope="prototype"` | `@Scope("prototype")` | Unique lookup behavior |
| `lazy-init="true"` | `@Lazy` | Tránh pre-instantiation khi chưa cần |
| `depends-on="manager"` | `@DependsOn("manager")` | Startup/shutdown relation |
| `init-method="start"` | `@Bean(initMethod="start")` | Callback một lần |
| `destroy-method="stop"` | `@Bean(destroyMethod="stop")` | Callback khi context close |
| `primary="true"` | `@Primary` | Single-candidate selection |
| `autowire-candidate="false"` | `@Bean(autowireCandidate=false)` | Type-based selection |
| `<beans profile="dev">` | `@Profile("dev")` | Bean tập hợp theo profile |
| XML `<import resource="x.xml"/>` | `@Import(XConfig.class)` sau khi migrate | Đúng sources |
| Giữ XML chưa migrate | `@ImportResource("classpath:x.xml")` | Không duplicate beans |
| `<context:component-scan>` | `@ComponentScan` | Packages và filters |
| `<tx:annotation-driven/>` | `@EnableTransactionManagement` khi phù hợp | Transaction manager/proxy behavior |

Các mảnh Java trong bảng là **cú pháp minh họa**. Chúng cần import annotation từ các Spring packages tương ứng và class definitions đúng.

### 4.1. Cẩn thận với những XML default values

XML bean definitions mặc định singleton và thường eager initialize non-lazy singletons trong `ApplicationContext`. `@Bean` cũng mặc định singleton, nhưng destroy inference/bean candidate metadata có thể khác. Không vì cả hai có default singleton mà bỏ qua kiểm tra các defaults khác.

## 5. Bean names và aliases là một phần API

XML:

```xml
<bean id="paymentService" class="demo.PaymentService"/>
<alias name="paymentService" alias="billingGateway"/>
```

JavaConfig gần tương ứng:

```java
@Bean(name = {"paymentService", "billingGateway"})
PaymentService paymentService() {
    return new PaymentService();
}
```

Tên đầu trong mảng là primary bean name; tên sau là aliases. Với singleton, hai lookups theo tên nhận cùng instance. Không cần tạo hai factory methods chỉ vì XML có alias.

### 5.1. Đặt rõ `@Bean("oldName")`

Nếu chuyển:

```xml
<bean id="accountDao" class="demo.AccountDao"/>
```

sang:

```java
@Bean
AccountDao repository() {
    return new AccountDao();
}
```

thì bean mặc định được đặt tên `repository` chứ không phải `accountDao`. Injection theo type có thể vẫn chạy, nhưng `getBean("accountDao")` hoặc XML `ref="accountDao"` ở file chưa migrate sẽ thất bại.

Giữ tên bằng `@Bean("accountDao")` khi legacy contract có tên này. Đừng tự ý đổi naming convention cùng lúc migrate.

### 5.2. Kiểm tra cả lookup theo type lẫn theo tên

Nếu JavaConfig thêm một implementation thứ hai, lookup theo tên có thể vẫn đúng nhưng type-based injection trở nên ambiguous. Kiểm tra tên/alias và số ứng viên cùng interface, nhất là khi có `@Primary`/`@Qualifier`.

## 6. Chuyển dependency injection mà không đổi lựa chọn collaborator

### 6.1. Constructor arguments

XML:

```xml
<bean id="repository" class="demo.SqlRepository"/>
<bean id="service" class="demo.OrderService">
    <constructor-arg ref="repository"/>
</bean>
```

JavaConfig:

```java
@Configuration(proxyBeanMethods = false)
class OrderConfiguration {

    @Bean("repository")
    SqlRepository repository() {
        return new SqlRepository();
    }

    @Bean("service")
    OrderService service(SqlRepository repository) {
        return new OrderService(repository);
    }
}
```

Method-parameter injection nói với BeanFactory resolve repository trước khi chạy service factory. Đây là lựa chọn đơn giản và tránh inter-bean self-invocation khi `proxyBeanMethods=false`.

### 6.2. Một XML `ref` có thể mang ý nghĩa **chọn theo tên**

XML:

```xml
<bean id="service" class="demo.OrderService">
    <constructor-arg ref="safeRepository"/>
</bean>
```

Nếu Java viết:

```java
@Bean("service")
OrderService service(Repository repository) {
    return new OrderService(repository);
}
```

mà container có `fastRepository` và `safeRepository`, Spring có thể chọn ứng viên khác (primary/qualifier/name resolution rules), hoặc fail vì không có ứng viên thắng. Để giữ intent, dùng:

```java
@Bean("service")
OrderService service(
        @Qualifier("safeRepository") Repository repository) {
    return new OrderService(repository);
}
```

`@Qualifier` giúp ràng buộc candidate theo name/metadata. Với kịch bản đặc biệt cần lookup chính xác bằng string, có thể sử dụng BeanFactory named lookup có chủ đích. Không biến business code thành service locator nếu factory-method parameters đủ diễn đạt dependency.

### 6.3. Setter injection giữ thời điểm populate property

XML:

```xml
<bean id="client" class="demo.Client">
    <property name="timeoutMillis" value="5000"/>
    <property name="repository" ref="repository"/>
</bean>
```

JavaConfig:

```java
@Bean("client")
Client client(Repository repository) {
    Client client = new Client();
    client.setTimeoutMillis(5000);
    client.setRepository(repository);
    return client;
}
```

Giữ cả literal và dependency reference. Nếu refactor sang constructor injection trong lúc chuyển, behavior có thể vẫn đúng nhưng initialization sequencing/class API thay đổi; nên làm bước refactor riêng và có tests.

### 6.4. Tránh `new` một collaborator thay cho managed bean

Sai nếu XML cũ inject singleton repository:

```java
@Bean
OrderService orderService() {
    return new OrderService(new SqlRepository());
}
```

`new SqlRepository()` tạo object độc lập, không phải managed bean `repository` do Spring đăng ký, không nhất thiết có AOP proxy/injection/init/destroy đúng.

Đúng hơn:

```java
@Bean
OrderService orderService(SqlRepository repository) {
    return new OrderService(repository);
}
```

**Ngoại lệ cần xét riêng:** XML inner bean cố ý tạo collaborator chỉ cho một consumer. Trong trường hợp đó, Java factory tự tạo object có thể phù hợp về functional effect, nhưng lifecycle/post-processing của inner bean có thể khác — test trước khi kết luận parity.

### 6.5. Full `@Configuration` và lite mode

`@Configuration` mặc định `proxyBeanMethods=true` và có thể được CGLIB tăng cường để các lời gọi giữa instance `@Bean` methods được chuyển về container. Với `proxyBeanMethods=false`, lời gọi Java `someBean()` là direct method call, có thể tạo thêm raw object.

Để migration dễ theo dõi, ưu tiên:

```java
@Bean
Service service(Repository repository) {
    return new Service(repository);
}
```

hơn:

```java
@Bean
Service service() {
    return new Service(repository()); // Direct @Bean method call.
}
```

Phương pháp đầu làm graph rõ trong signature và không phụ thuộc proxy mode.

## 7. Scalar values, nulls, collections và cấu hình bên ngoài

### 7.1. Literal conversion

XML:

```xml
<property name="retries" value="3"/>
<property name="enabled" value="true"/>
<property name="label" value="Invoices"/>
```

Trong Java:

```java
service.setRetries(3);
service.setEnabled(true);
service.setLabel("Invoices");
```

Spring XML dùng type-conversion infrastructure để đổi text theo setter type; Java compiler kiểm tra kiểu arguments. Với custom `PropertyEditor`/`ConversionService`, một literal có thể được biến thành domain value đặc biệt. Hãy giữ **ý nghĩa sau conversion**, không chỉ copy raw XML string.

### 7.2. Empty string khác Java null

XML `<property name="memo" value=""/>` diễn đạt chuỗi rỗng. XML:

```xml
<property name="memo">
    <null/>
</property>
```

diễn đạt null. Khi Java migrate, dùng `setMemo("")` hay `setMemo(null)` đúng theo dữ liệu cũ. Phân biệt hai trường hợp nếu validation/serialization/business logic phụ thuộc chúng.

### 7.3. Collection mutability và order

XML:

```xml
<property name="channels">
    <list>
        <value>email</value>
        <value>sms</value>
    </list>
</property>
```

Java:

```java
service.setChannels(List.of("email", "sms"));
```

Hai collections này có thể tương đương nếu service **chỉ đọc** và chỉ cần đúng nội dung/thứ tự. Nhưng `List.of(...)` là unmodifiable; nếu legacy service gọi `channels.add("push")`, behavior đổi.

Nếu mutation là contract:

```java
service.setChannels(
        new ArrayList<>(List.of("email", "sms")));
```

Với XML `<map>` và Java `Map.of(...)`, chú ý iteration order, null keys/values, duplicate keys và mutability. Khi cần order rõ, cân nhắc `LinkedHashMap`; khi cần mutable object, tạo mutable copy và có tests.

### 7.4. Placeholder và property source precedence

XML có thể khai:

```xml
<context:property-placeholder
    location="classpath:legacy.properties"/>

<bean id="client" class="demo.Client">
    <property name="endpoint"
              value="${client.endpoint}"/>
</bean>
```

JavaConfig có thể dùng:

```java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:legacy.properties")
class ClientConfiguration {

    @Bean
    Client client(@Value("${client.endpoint}") String endpoint) {
        Client client = new Client();
        client.setEndpoint(endpoint);
        return client;
    }
}
```

Đây là các đoạn minh họa; XML cần khai namespace `context`, Java cần imports và domain class. Cú pháp Spring placeholder là `${client.endpoint}` (không có backslash ở source thật). Hệ thống resolve placeholder dựa trên property sources và infrastructure đang dùng.

Chú ý **source/precedence**: property từ system env, system properties, file trong classpath, Spring `Environment`, `PropertySourcesPlaceholderConfigurer` hoặc Boot config system có thể khác nhau. Không đổi tên key, default fallback hoặc nguồn ưu tiên chỉ vì syntax mới ngắn hơn.

### 7.5. SpEL expressions không phải Java expressions tương đương vô điều kiện

XML `value="#{@settings.timeoutMillis}"` có thể resolve SpEL qua container. Một Java call `settings.timeoutMillis()` có thể khác về proxy, lazy/scoped references và lifecycle. Giữ `@Value("#{...}")` khi có lý do rõ hoặc thay bằng DI + test, không tìm–thay thế biểu thức theo text.

## 8. Bean scope, lazy, ordering và lifecycle

### 8.1. Scope

XML:

```xml
<bean id="ticket" class="demo.Ticket"
      scope="prototype"/>
```

Java:

```java
@Bean("ticket")
@Scope("prototype")
Ticket ticket() {
    return new Ticket();
}
```

Hai calls `context.getBean("ticket")` phải trả hai objects khác nhau theo prototype semantics. `@Bean` mặc định singleton nên quên `@Scope` là regression.

Nếu một singleton nhận prototype trong constructor, nó thường giữ một prototype đã inject; để lookup mỗi operation, có thể cần `ObjectProvider<T>`/factory/method injection. Chỉ chuyển scope flag chưa đủ nếu XML cũ dùng `<lookup-method>`.

### 8.2. Lazy

XML:

```xml
<bean id="lazyFormatter"
      class="demo.LazyFormatter"
      lazy-init="true"/>
```

Java:

```java
@Bean("lazyFormatter")
@Lazy
LazyFormatter lazyFormatter() {
    return new LazyFormatter();
}
```

Bean lazy có thể bị tạo tại startup nếu một eager singleton cần nó để giải quyết dependency. Test trên actual graph, không tuyên bố mọi lazy bean “không bao giờ” được tạo lúc refresh.

### 8.3. Depends-on

XML:

```xml
<bean id="service" class="demo.Service"
      depends-on="startupMarker"/>
```

Java:

```java
@Bean("service")
@DependsOn("startupMarker")
Service service(Repository repository) {
    return new Service(repository);
}
```

`@DependsOn` là ordering dependency theo bean names. Nó không tự truyền object `StartupMarker` cho service. Quan hệ này còn có thể ảnh hưởng destruction order của singletons. Đừng xóa nó chỉ vì service constructor không dùng marker.

### 8.4. Init/destroy callbacks

XML:

```xml
<bean id="service" class="demo.Service"
      init-method="start"
      destroy-method="stop"/>
```

Java:

```java
@Bean(name = "service",
      initMethod = "start",
      destroyMethod = "stop")
Service service(Repository repository) {
    return new Service(repository);
}
```

Không gọi `service.start()` trong factory method rồi đồng thời giữ `initMethod="start"`: callback có thể chạy **hai lần**. Phải để container gọi ở đúng lifecycle phase.

### 8.5. Destroy inference của `@Bean` là một bẫy

`@Bean` có thể tự suy luận destroy method dạng public no-arg `close()` hoặc `shutdown()`. Điều đó có thể thêm behavior so với XML cũ không cấu hình callback như vậy.

Nếu muốn ngăn **inference** cho một bean:

```java
@Bean(destroyMethod = "")
LegacyResource sharedResource() {
    return new LegacyResource();
}
```

Giá trị rỗng chỉ vô hiệu cơ chế inference đó; nó không tắt callbacks từ `DisposableBean` hoặc lifecycle khác. Với resource XML đã có `destroy-method="close"`, nên khai `@Bean(destroyMethod="close")` rõ để giữ hành vi.

### 8.6. Prototype destroy không giống singleton destroy

Spring không tự theo dõi đầy đủ mọi prototype đã cấp để thực hiện destroy trên chúng khi context đóng như với singleton. Nếu dự án có prototype resource cần cleanup, application có thể phải thực hiện riêng. Không dùng `@Bean(destroyMethod="...")` để hứa hẹn cleanup mọi prototype.

## 9. Profiles, candidates và infrastructure quan trọng

### 9.1. XML profile sang `@Profile`

XML:

```xml
<beans profile="dev">
    <bean id="store" class="demo.InMemoryStore"/>
</beans>
```

Java:

```java
@Configuration(proxyBeanMethods = false)
@Profile("dev")
class DevConfiguration {
    @Bean("store")
    Store store() {
        return new InMemoryStore();
    }
}
```

Test cả dev/prod/no profile, cộng multi-profile khi ứng dụng thực tế hỗ trợ. Nếu imported configuration mang `@Conditional` hoặc `@Profile`, nó còn chịu điều kiện riêng; import không ép bean tồn tại.

### 9.2. Primary/qualifier

XML `primary="true"` gần với Java `@Primary`. Với consumer cần rõ một bean cụ thể, `@Qualifier("safeStore")` hoặc explicit named lookup có thể cần thiết hơn một default by-type injection.

`autowire-candidate="false"` trong XML chủ yếu loại bean khỏi type-based injection, không xóa bean và không cấm explicit `ref`. Trong Spring 6.2, `@Bean(autowireCandidate=false)` có thể giữ candidate metadata tương ứng.

### 9.3. Infrastructure XML không đổi sang annotation bằng đoán tên

`<tx:annotation-driven/>` có thể tương ứng `@EnableTransactionManagement`, nhưng hãy xác minh mode proxy/AspectJ, transaction manager, advisor ordering, proxyTargetClass và actual commit/rollback.

`<aop:aspectj-autoproxy/>` có cơ chế Java như `@EnableAspectJAutoProxy` khi phù hợp, nhưng không có nghĩa mọi raw object trở thành proxy. Self-invocation trong Spring AOP proxy mode thường bypass proxy.

`<context:component-scan>` có thể chuyển sang `@ComponentScan`, nhưng giữ đúng package roots, include/exclude filters và bean naming. Component scan quá rộng có thể đăng ký thêm cả XML configs/implementations chưa muốn dùng.

Với custom namespace từ Spring Integration, Security, Batch hoặc vendor library, một Java DSL/API tương đương **không được bảo đảm** cho mọi version. Có thể giữ một XML fragment qua `@ImportResource` rồi migrate khi đã có test.

## 10. Demo Java 17+: cùng ứng dụng, hai cách đăng ký bean

Mục tiêu là so sánh **một XML context** và **một JavaConfig context**, không nhập cả hai vào chung một registry. Bản XML và JavaConfig cùng định nghĩa:

- `catalogRepository`: singleton repository.
- `catalogService`: singleton service, alias `publicCatalog`, nhận repository, prefix, retries, channels.
- `startupMarker`: có quan hệ `depends-on` với service.
- `ticket`: prototype.
- `lazyFormatter`: lazy singleton.
- Lifecycle của service: `start` khi initialize, `stop` khi context close.

### 10.1. Cấu trúc file

```text
xml-to-java-parity/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── XmlJavaParityDemo.java
        └── resources/
            └── legacy-context.xml
```

`settings.gradle`:

```groovy
rootProject.name = 'xml-to-java-parity'
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
    mainClass = 'demo.XmlJavaParityDemo'
}
```

Dùng JDK 17+ và Gradle tương thích. `spring-context` bao gồm những Spring module dependencies cần để đọc XML và JavaConfig; không cần Spring Boot.

### 10.2. File XML gốc

`src/main/resources/legacy-context.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="startupMarker"
          class="demo.XmlJavaParityDemo$StartupMarker"/>

    <bean id="catalogRepository"
          class="demo.XmlJavaParityDemo$CatalogRepository"/>

    <bean id="catalogService"
          class="demo.XmlJavaParityDemo$CatalogService"
          depends-on="startupMarker"
          init-method="start"
          destroy-method="stop">
        <constructor-arg ref="catalogRepository"/>
        <property name="prefix" value="INV:"/>
        <property name="retries" value="2"/>
        <property name="channels">
            <list>
                <value>email</value>
                <value>sms</value>
            </list>
        </property>
    </bean>

    <alias name="catalogService" alias="publicCatalog"/>

    <bean id="ticket"
          class="demo.XmlJavaParityDemo$Ticket"
          scope="prototype"/>

    <bean id="lazyFormatter"
          class="demo.XmlJavaParityDemo$LazyFormatter"
          lazy-init="true"/>
</beans>
```

Các `$` trong attribute `class` là **binary names của nested Java classes**. Đây là chính xác trong demo; nếu chuyển domain classes thành top-level classes thì phải đổi XML class names.

### 10.3. Toàn bộ mã Java

`src/main/java/demo/XmlJavaParityDemo.java`:

```java
package demo;

import java.util.Arrays;
import java.util.List;
import java.util.Objects;

import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Scope;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public class XmlJavaParityDemo {

    public static final class StartupMarker {
        public StartupMarker() {
        }
    }

    public static final class CatalogRepository {
        public CatalogRepository() {
        }

        public String find(String id) {
            return "sku-" + id;
        }
    }

    public static final class Ticket {
        public Ticket() {
        }
    }

    public static final class LazyFormatter {
        public LazyFormatter() {
        }
    }

    public static final class CatalogService {
        private final CatalogRepository repository;
        private String prefix = "";
        private int retries;
        private List<String> channels = List.of();
        private boolean started;
        private boolean stopped;

        public CatalogService(CatalogRepository repository) {
            this.repository = Objects.requireNonNull(repository);
        }

        public void setPrefix(String prefix) {
            this.prefix = Objects.requireNonNull(prefix);
        }

        public void setRetries(int retries) {
            this.retries = retries;
        }

        public void setChannels(List<String> channels) {
            this.channels = Objects.requireNonNull(channels);
        }

        public CatalogRepository getRepository() {
            return repository;
        }

        public void start() {
            started = true;
        }

        public void stop() {
            stopped = true;
        }

        public boolean isStarted() {
            return started;
        }

        public boolean isStopped() {
            return stopped;
        }

        public String report(String id) {
            return prefix + repository.find(id)
                    + " retries=" + retries
                    + " channels=" + channels;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class JavaConfig {

        @Bean("startupMarker")
        StartupMarker startupMarker() {
            return new StartupMarker();
        }

        @Bean("catalogRepository")
        CatalogRepository catalogRepository() {
            return new CatalogRepository();
        }

        @Bean(
            name = {"catalogService", "publicCatalog"},
            initMethod = "start",
            destroyMethod = "stop"
        )
        @DependsOn("startupMarker")
        CatalogService catalogService(
                CatalogRepository catalogRepository) {

            CatalogService service =
                    new CatalogService(catalogRepository);
            service.setPrefix("INV:");
            service.setRetries(2);
            service.setChannels(List.of("email", "sms"));
            return service;
        }

        @Bean("ticket")
        @Scope("prototype")
        Ticket ticket() {
            return new Ticket();
        }

        @Bean("lazyFormatter")
        @Lazy
        LazyFormatter lazyFormatter() {
            return new LazyFormatter();
        }
    }

    private static void inspect(
            String label,
            ConfigurableApplicationContext context) {

        CatalogService service;

        try (context) {
            boolean lazyBefore = context.getBeanFactory()
                    .containsSingleton("lazyFormatter");

            service = context.getBean(
                    "catalogService", CatalogService.class);

            CatalogRepository repository =
                    context.getBean(CatalogRepository.class);

            boolean aliasSame =
                    service == context.getBean("publicCatalog");
            boolean repositorySame =
                    service.getRepository() == repository;
            boolean prototypeDistinct =
                    context.getBean("ticket")
                    != context.getBean("ticket");
            boolean dependsOnCorrect = Arrays.equals(
                    context.getBeanFactory()
                            .getBeanDefinition("catalogService")
                            .getDependsOn(),
                    new String[] {"startupMarker"});

            context.getBean("lazyFormatter");
            boolean lazyAfter = context.getBeanFactory()
                    .containsSingleton("lazyFormatter");

            String expected =
                    "INV:sku-42 retries=2 channels=[email, sms]";

            if (!expected.equals(service.report("42"))
                    || !aliasSame || !repositorySame
                    || !prototypeDistinct || !dependsOnCorrect
                    || !service.isStarted()
                    || lazyBefore || !lazyAfter) {
                throw new AssertionError(
                        label + " parity failed");
            }

            System.out.println(label + " report=" +
                    service.report("42"));
            System.out.println(label + " aliasSame=" + aliasSame);
            System.out.println(label + " repositorySame=" +
                    repositorySame);
            System.out.println(label + " prototypeDistinct=" +
                    prototypeDistinct);
            System.out.println(label + " dependsOnCorrect=" +
                    dependsOnCorrect);
            System.out.println(label + " started=" +
                    service.isStarted());
            System.out.println(label + " lazyBefore=" + lazyBefore);
            System.out.println(label + " lazyAfter=" + lazyAfter);
        }

        if (!service.isStopped()) {
            throw new AssertionError(
                    label + " destroy callback not invoked");
        }
        System.out.println(label + " stopped=" +
                service.isStopped());
    }

    public static void main(String[] args) {
        inspect("XML", new ClassPathXmlApplicationContext(
                "legacy-context.xml"));
        inspect("JAVA", new AnnotationConfigApplicationContext(
                JavaConfig.class));
    }
}
```

Đây là một Java file đầy đủ với đúng một top-level public class. Domain types là static nested classes; các factory methods trong `JavaConfig` không tự gọi lẫn nhau. `@Bean` method `catalogService(...)` nhận managed repository từ BeanFactory; không tạo một repository thứ hai.

### 10.4. Cách chạy

Từ root project:

```bash
gradle run --quiet
```

Khi có Gradle Wrapper:

```bash
./gradlew run --quiet
```

Trong Windows PowerShell:

```powershell
.\gradlew.bat run --quiet
```

Stdout của chương trình:

```text
XML report=INV:sku-42 retries=2 channels=[email, sms]
XML aliasSame=true
XML repositorySame=true
XML prototypeDistinct=true
XML dependsOnCorrect=true
XML started=true
XML lazyBefore=false
XML lazyAfter=true
XML stopped=true
JAVA report=INV:sku-42 retries=2 channels=[email, sms]
JAVA aliasSame=true
JAVA repositorySame=true
JAVA prototypeDistinct=true
JAVA dependsOnCorrect=true
JAVA started=true
JAVA lazyBefore=false
JAVA lazyAfter=true
JAVA stopped=true
```

Các build tool/logging messages nằm ngoài những `System.out.println` có thể xuất hiện tùy môi trường. Assertions sẽ ném `AssertionError` nếu parity contract ở ví dụ không thỏa.

### 10.5. Giải thích kết quả

**`report`:** cả hai contexts cung cấp cùng prefix, retries và ordered channels. Repository behavior trả `sku-42`, nên business result bằng nhau.

**`aliasSame=true`:** XML `<alias>` và Java `@Bean(name=...)` cùng giữ alias `publicCatalog` cho `catalogService`.

**`repositorySame=true`:** constructor của `CatalogService` được cấp đúng managed singleton `CatalogRepository`. Không có `new CatalogRepository()` trong service factory method.

**`prototypeDistinct=true`:** hai lookups của `ticket` trong cùng context trả hai objects khác nhau.

**`dependsOnCorrect=true`:** cả hai definitions có metadata phụ thuộc `startupMarker`.

**`started=true`:** Spring gọi init method trên singleton service; code factory không gọi `start()` thủ công.

**`lazyBefore=false`/`lazyAfter=true`:** trước lookup, bean lazy chưa có singleton instance; sau lookup đã được tạo.

**`stopped=true`:** try-with-resources đóng context và thực hiện destroy callback.

### 10.6. Giới hạn của bài demo

Demo xác minh **contract đã khai báo**, không chứng minh hai Spring contexts có mọi bean infrastructure/metadata giống tuyệt đối. Nó không thử transactions, component scan, FactoryBean, profiles hay web scopes. Java `List.of` là unmodifiable; do demo không mutate channels nên parity được chứng minh về nội dung/thứ tự, **không** về mutability. Với hệ thống thật, thêm assertions theo business contract còn thiếu.

## 11. Chạy XML và JavaConfig song song bằng `@ImportResource`

Không nhất thiết xóa mọi XML trong một commit. Trong Java-centric application, có thể:

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy-infrastructure.xml")
class ApplicationConfig {

    @Bean
    NewService newService(LegacyRepository repository) {
        return new NewService(repository);
    }
}
```

Đây là **mã minh họa**, cần class/domain types và imports. `@ImportResource` nạp XML bean definitions; nó khác Java `@Import(AnotherConfig.class)`.

### 11.1. Mỗi bean chỉ có một nguồn registration có chủ đích

Khi chuyển một bean từ XML sang Java:
- Đăng ký bean mới trong JavaConfig.
- Loại chính bean definition tương ứng khỏi XML đang load.
- Rà soát scanner/auto-config có đăng ký thêm type/name đó không.
- Kiểm thử named lookup, injection, scopes, callbacks, side effects.

Đừng để hai bean definitions cùng tên rồi trông chờ bean override order tự chọn đúng. Chính sách bean definition overriding phụ thuộc context/framework settings và không nên là migration strategy.

### 11.2. XML-centric app vẫn có thể nhận JavaConfig

Trong ứng dụng mà `ClassPathXmlApplicationContext` là entry point, Spring có thể xử lý một `@Configuration` class được đăng ký như bean hoặc quét từ package nếu configuration post-processing phù hợp đã bật. Đừng chỉ thêm một class vào XML rồi cho rằng toàn bộ `@Bean` methods chắc chắn sẽ được nhận trong mọi legacy bootstrap setup.

Java-centric `AnnotationConfigApplicationContext` với `@ImportResource` thường là điểm xuất phát gọn khi mục tiêu cuối là JavaConfig. Nhưng migration có thể đi hai chiều tùy ranh giới hiện tại.

### 11.3. Chia module nhỏ

Một lộ trình an toàn:

1. Giữ legacy XML infrastructure hoạt động.
2. Migrate nhóm domain bean nhỏ, ít side effects.
3. Chạy context parity tests.
4. Thay đổi composition root để dùng bean Java mới.
5. Xóa XML definitions của nhóm đó.
6. Tiếp tục với nhóm kế tiếp, để hạ tầng namespace phức tạp sau cùng.

Không kết hợp nâng cấp major Spring version, sửa business logic và đổi property precedence trong cùng một đợt nếu cần chứng minh hành vi được bảo toàn.

## 12. Những trường hợp không có ánh xạ một-một

### 12.1. `FactoryBean` và ký hiệu `&`

XML có thể đăng ký implementation của `FactoryBean<T>`. Khi gọi `getBean("connection")`, Spring trả product; khi gọi `getBean("&connection")`, có thể lấy chính factory bean. Một JavaConfig chuyển nó thành `@Bean Connection connection()` trực tiếp có thể làm mất factory contract.

Nếu consumers cần `&name`, hãy giữ `FactoryBean` semantics hoặc thay consumers có kế hoạch. Đừng đánh đồng `FactoryBean` và Java factory method.

### 12.2. Lookup-method injection

XML `<lookup-method>` có thể giúp singleton lấy prototype mới ở mỗi lần gọi method. Java `@Scope("prototype")` trên bean được tạo chưa tự làm một singleton đổi dependency mỗi lần dùng. Cân nhắc `ObjectProvider<T>`/factory abstraction hoặc `@Lookup` với constraints phù hợp. Kiểm tra behavior qua nhiều lookups.

### 12.3. XML bean inheritance

XML child bean definitions có thể thừa hưởng/ghi đè metadata từ parent `parent="..."`. Java class inheritance không mô phỏng mọi rule của bean definition inheritance, đặc biệt collection merging hoặc abstract parent definitions. Có thể thay bằng helper methods/factory patterns, nhưng phải đối chiếu metadata merged.

### 12.4. Custom XML namespaces

Một số XML namespaces được vendor triển khai bằng `NamespaceHandler` tạo nhiều bean definitions/proxies. Chỉ khi vendor có Java DSL/API tương ứng đúng version mới nên chuyển từng phần. Có thể giữ XML qua `@ImportResource` nếu hiện chưa có cách an toàn; không tự dựng một `@Bean` và giả định thay thế toàn bộ namespace semantics.

### 12.5. Post-processors, proxies và infrastructure

Bean XML có thể được một `BeanPostProcessor` thay bằng proxy; nếu đổi context bootstrapping làm post-processor đó không còn được đăng ký, returned type/transaction behavior sẽ khác dù target class giống. Test qua **managed bean reference**, không chỉ trực tiếp gọi Java factory method.

### 12.6. Metadata ít phổ biến

`role`, `description`, abstract definitions, lookup/replaced methods, custom qualifiers, `primary`, `autowire-candidate` và scope-specific proxies có thể mang hợp đồng đối với libraries/tooling. Không phải trường nào cũng có annotation có tên y hệt; nếu cần, sử dụng API bean definition registration hoặc giữ XML tạm thời.

## 13. Test hồi quy: dùng bằng chứng thay vì tin vào mắt

### 13.1. Golden-master trước migration

Với context XML cũ, thu kết quả:

- `getBean("name")` và alias lookup.
- Type/identity của managed dependency quan trọng.
- Kết quả gọi method nghiệp vụ với input ổn định.
- Singleton/prototype differences.
- Lifecycle init/destroy, lazy/eager và `depends-on`.
- Active profiles và property precedence ở dev/test/prod.
- Transaction rollback/commit, cache, scheduler hoặc messaging side effects khi có.
- Có hay không nhiều candidates cùng interface.

Sau đó chạy cùng kiểm tra trên JavaConfig mới **với cùng phiên bản framework, input và runtime dependencies**.

### 13.2. Differential test ở hai contexts

Trích đoạn từ demo:

```java
try (var legacy = new ClassPathXmlApplicationContext(
        "legacy-context.xml");
     var modern = new AnnotationConfigApplicationContext(
        XmlJavaParityDemo.JavaConfig.class)) {

    String oldValue = legacy.getBean(
            XmlJavaParityDemo.CatalogService.class)
            .report("42");
    String newValue = modern.getBean(
            XmlJavaParityDemo.CatalogService.class)
            .report("42");

    if (!oldValue.equals(newValue)) {
        throw new AssertionError("Business output changed");
    }
}
```

Đây là **test fragment**, cần imports và class scope phù hợp khi đặt ở file riêng. Một business assertion là cần nhưng chưa đủ: mục 10 còn kiểm tra alias, scope, depends-on, lazy và destroy.

### 13.3. Test theo profile/property matrix

| Tình huống | Input environment | Kỳ vọng |
| --- | --- | --- |
| Local | `dev` | Dev provider, không tạo production resource |
| CI | `test` | Deterministic fake/stub |
| Production | `prod` | Real provider và transaction infrastructure |
| Thiếu required property | Không có endpoint | Fail-fast cùng policy như XML |
| Nhiều profiles | `dev,metrics` | Candidate selection nhất quán |

Bảng là mẫu; điều chỉnh theo môi trường thực. Không so sánh cả hai context với những property sources khác nhau rồi quy lỗi cho JavaConfig.

### 13.4. Test cả shutdown

Nhiều regression chỉ xuất hiện khi context đóng: threads còn chạy, connection pool chưa giải phóng hoặc shared resource bị đóng ngoài ý muốn do inferred destroy callback. Chạy test tạo/đóng context nhiều lần và assert cleanup.

### 13.5. Không so số lượng bean definitions một cách máy móc

`@Configuration` processing có infrastructure bean definitions khác XML. Ưu tiên so set các **business bean names/types** và behavior. Nếu có dependency vào infrastructure, kiểm tra infrastructure cụ thể đó.

## 14. Lỗi điển hình khi chuyển XML sang Java

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` theo tên | `@Bean` method đổi bean name | Chỉ định `@Bean("oldName")` và alias |
| Type injection ambiguous | XML explicit ref → Java by-type parameter | Dùng qualifier/named injection |
| Prototype thành singleton | Quên `@Scope("prototype")` | Khôi phục scope và test identities |
| Lazy bean tạo ngay | Quên `@Lazy` hoặc có eager consumer | Xem metadata và graph |
| Setter property thiếu | Factory không gọi setter | Kiểm kê XML `<property>` |
| Endpoint sai | Property source precedence đổi | So source/order/defaults |
| Init chạy hai lần | Manual call + `initMethod` | Để container gọi một lần |
| Destroy không chạy | Quên `destroyMethod` | Dùng explicit callback và close test |
| Destroy chạy ngoài ý muốn | `@Bean` suy luận `close/shutdown` | Xem `destroyMethod=""` |
| Service tạo dependency ngoài Spring | Factory dùng `new Dependency()` | Inject managed bean qua parameter |
| Bean trùng tên | XML vẫn được import cùng Java | Một owner cho mỗi definition |
| Scope đổi vì chuyển context | Bean được đưa từ child lên root | Giữ context boundary hoặc refactor có test |
| Transactions ngừng tác dụng | Mất `tx`/AOP infrastructure | Đăng ký Java equivalent, test rollback |
| Scan đăng ký thêm beans | `@ComponentScan` quá rộng | Kiểm tra package/filter |
| `FactoryBean` contract hỏng | Thay factory bằng product | Giữ factory/product semantics |
| List không mutable | Dùng `List.of` thay mutable XML collection | Dùng mutable collection khi cần |
| Prototype “không đổi” mỗi call | Singleton giữ prototype dependency một lần | Dùng provider/lookup abstraction |
| Profile sai | Đổi XML profile block thành `@Profile` không đúng phạm vi | Test tất cả profile combos |
| Custom namespace mất behavior | Chưa thay namespace handler | Giữ XML hoặc dùng vendor API đúng |

## 15. Lộ trình phát hành thực tế

**Giai đoạn 1 — Chụp baseline.** Ghi phiên bản Spring, cấu trúc contexts, file XML, property sources, profiles, danh sách bean contracts, integration tests và startup/shutdown behavior. Không làm nhiều thay đổi ngoài phạm vi.

**Giai đoạn 2 — Xây JavaConfig song song trong test.** Viết Java definitions nhưng **không đăng ký chung với XML production**. So sánh outputs qua hai test contexts.

**Giai đoạn 3 — Rà metadata.** Check aliases, scopes, lazy, lifecycle, explicit depends-on, candidates và nontrivial namespace infrastructure.

**Giai đoạn 4 — Chuyển một module.** Thay root import để dùng JavaConfig cho nhóm bean đã test; bỏ XML definitions cùng nhóm khỏi active load path.

**Giai đoạn 5 — Quan sát.** Kiểm tra startup, duplicate bean issues, transactions, worker threads, shutdown, memory/cpu, logs và metrics.

**Giai đoạn 6 — Rollback khi cần.** Có khả năng đảo nguồn config mà không bật cả XML và Java cùng lúc. Sau khi ổn định mới dọn XML cũ và cập nhật documentation ownership.

## 16. Bài tập có lời giải

### Bài 1 — Tên bean

XML `id="accountDao"` chuyển thành `@Bean AccountDao repository()`. `getBean("accountDao")` có được bảo đảm chạy?

**Đáp án:** Không. Default name thành `repository`. Giữ `@Bean("accountDao")`.

### Bài 2 — Alias

XML `<alias name="service" alias="publicService"/>`. Cách Java thuận tiện?

**Đáp án:** `@Bean(name={"service","publicService"})` trên một factory method. Đừng tạo hai beans nếu XML chỉ có alias.

### Bài 3 — Candidate sai

XML `ref="safeStore"`. Java đổi thành injection `Store store`, trong context có `fastStore` @Primary. Có giữ collaborator không?

**Đáp án:** Chưa chắc. `@Primary` có thể khiến nhận `fastStore`. Dùng qualifier/named wiring và test.

### Bài 4 — Prototype

XML `scope="prototype"`, Java chỉ `@Bean Ticket ticket()`. Sai ở đâu?

**Đáp án:** Quên `@Scope("prototype")`; Java default singleton.

### Bài 5 — Lazy

XML `lazy-init="true"`, Java có `@Lazy`. Nhưng một eager service inject bean đó. Có chắc bean lazy chưa tạo lúc refresh không?

**Đáp án:** Không; dependency bắt buộc có thể kích hoạt việc tạo sớm.

### Bài 6 — Init

Java factory gọi `start()` và `@Bean(initMethod="start")`. Điều gì xảy ra?

**Đáp án:** Callback có thể chạy hai lần; giữ một nguồn lifecycle invocation.

### Bài 7 — Destroy inference

Một bean có `public void close()`, XML cũ không khai custom destroy, Java chuyển thành `@Bean`. Cần kiểm tra gì?

**Đáp án:** Inferred destroy callback của `@Bean`. Nếu legacy yêu cầu không tự đóng, xem `destroyMethod=""` và các lifecycle interfaces liên quan.

### Bài 8 — Depends-on

XML service không inject marker nhưng có `depends-on="marker"`. Java xóa ordering này vì “không có constructor dependency”. Đúng không?

**Đáp án:** Không; có thể đổi thứ tự init/shutdown. Giữ `@DependsOn("marker")` nếu cần parity.

### Bài 9 — Property null

XML dùng nested `<null/>` cho memo. Java dùng `setMemo("")`. Có tương đương không?

**Đáp án:** Không nếu consumer phân biệt null/empty.

### Bài 10 — Collection mutability

XML list mutable, Java dùng `List.of(...)`, business code thêm phần tử. Hậu quả?

**Đáp án:** Java list không thể sửa; hành vi khác. Chọn collection mutable thích hợp và test.

### Bài 11 — ImportResource

Một repository chưa migrate còn trong `legacy.xml`; JavaConfig đã migrate service. Dùng cơ chế nào?

**Đáp án:** `@ImportResource("classpath:legacy.xml")`, đồng thời không đăng ký trùng service giữa hai nguồn.

### Bài 12 — XML namespace hạ tầng

Legacy dùng `<tx:annotation-driven/>`. JavaConfig chỉ khai `@Bean` cho services. Có bảo đảm transaction còn tác dụng?

**Đáp án:** Không. Cần transaction configuration/proxy/manager tương ứng và integration test commit/rollback.

### Bài 13 — FactoryBean

Một consumer gọi `getBean("&factory")`, Java thay `FactoryBean` bằng raw product factory method. Có parity?

**Đáp án:** Không nếu consumer phụ thuộc vào factory object; cần giữ contract hoặc refactor consumers có kế hoạch.

### Bài 14 — Parent context

Bean cũ nằm ở servlet child context, bean mới ở root; tên và class giống. Có tự tương đương?

**Đáp án:** Không; visibility, identity và lifecycle boundary có thể khác.

### Bài 15 — Tổng số bean definitions

XML context có ít definitions hơn JavaConfig context vì infrastructure. Có thể tự kết luận migration sai?

**Đáp án:** Không. So sánh business contracts và infrastructure quan trọng, không so raw count thiếu ngữ cảnh.

### Bài 16 — Runtime property

Legacy lấy config từ một property file còn Java lấy từ environment variable khác, local defaults trùng nhau. Đã đủ parity?

**Đáp án:** Chưa. Test nguồn/precedence ở các môi trường có giá trị khác defaults.

## 17. Checklist trước khi xóa XML

- Đã tìm đủ XML files thực sự được load trong mọi environments?
- Bean names, aliases và lookup theo string đã được giữ?
- Dependency injection giữ đúng provider, nhất là nơi có multiple candidates?
- Scope, lazy, depends-on và lifecycle init/destroy đúng?
- Property literals, type conversion, null/empty và collections đúng semantics?
- JavaConfig có thêm inferred destroy callbacks ngoài ý muốn?
- XML namespace infrastructure đã được chuyển có kiểm thử hoặc còn giữ qua `@ImportResource`?
- Components auto-scanned có tạo duplicate beans không?
- Không có XML và Java cùng đăng ký một bean name trong một context?
- Test cùng Spring version, profiles, inputs và property precedence?
- Assertions đã bao phủ behavior, identity, prototype và shutdown?
- Đã có rollback plan không bật đồng thời hai nguồn bean definitions?
- Config classes được tổ chức thành module boundaries dễ theo dõi?
- Những chỗ vẫn giữ XML đã được ghi rõ lý do và owner?

## 18. Kết luận

Đổi Spring XML sang JavaConfig là thay đổi **cách mô tả bean graph**. Để giữ hành vi, phải giữ bean names/aliases, injection lựa chọn đúng candidate, scope, lazy, lifecycle, ordering, profile, property precedence và các Spring infrastructure contracts. Nhiều chỗ có ánh xạ trực tiếp sang `@Bean`/`@Scope`/`@Lazy`/`@DependsOn`/`@Profile`, nhưng custom namespaces, FactoryBeans, lookup-method injection và bean inheritance cần thiết kế riêng.

Đừng chỉ xem context startup thành công là đủ. Hãy tạo **hai context riêng**, chạy cùng inputs, so sánh business output và metadata/identity/lifecycle quan trọng. Với migration từng phần, `@ImportResource` cho phép giữ XML cũ nhưng phải kiểm soát trùng definitions. Sau khi parity tests đạt và production vận hành ổn định, mới loại bỏ XML đã thay thế.

### Tài liệu Spring chính thức

- [Spring Framework 6.2 — Composing Java-based Configurations and XML](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html).
- [Spring Framework 6.2 — Using `@Bean`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html).
- [Spring Framework 6.2 — Basic Concepts: `@Bean` and `@Configuration`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html).
- [Spring Framework 6.2 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html).
- [Spring Framework 6.2 — Using `depends-on`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html).
- [Spring Framework 6.2 — Bean Lifecycle](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html).
- [Spring Framework 6.2 — `Bean` Javadoc, names/aliases and destroy inference](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/Bean.html).

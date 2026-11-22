# Singleton theo bean và theo container trong Spring Framework Core Container

## 1. Câu trả lời ngắn: một bean definition, một container, một managed singleton

Trong Spring Framework, `singleton` là scope mặc định. Khi một **bean definition** được đánh dấu singleton, Spring IoC Container quản lý một shared instance của bean đó trong **phạm vi container sở hữu bean**. Những lần yêu cầu cùng bean name (hoặc alias của bean name đó) trong cùng container thường trả cùng managed object reference.

Nói chính xác hơn:

> **Spring singleton = một shared instance cho mỗi singleton bean definition trong mỗi Spring IoC container.**

Định nghĩa này có hai trục độc lập:

- **Per bean:** hai bean definitions khác nhau, dù cùng Java class, vẫn có thể tạo **hai singleton objects khác nhau** trong cùng container.
- **Per container:** hai Spring `ApplicationContext` độc lập, dù load cùng một `@Configuration` class và dùng cùng bean name, thường quản lý **hai singleton instances khác nhau**.

Quy tắc trên khác hẳn mẫu Singleton của Gang of Four (GoF) thường kiểm soát một instance ở phạm vi class/ClassLoader qua static field hoặc private constructor. Spring singleton **không tự biến Java class thành global singleton**.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class RepositoryConfig {

    @Bean("mainRepository")
    Repository mainRepository() {
        return new Repository("main");
    }

    @Bean("archiveRepository")
    Repository archiveRepository() {
        return new Repository("archive");
    }
}
```

Đây là **snippet minh họa**, cần thêm Spring imports và class `Repository`. Mặc dù cả hai `@Bean` methods trả về **cùng class Repository**, chúng khai báo **hai beans có tên khác nhau**, nên mặc định mỗi definition có singleton instance riêng trong một context.

Giả sử `context` nạp `RepositoryConfig`:

```java
Object first = context.getBean("mainRepository");
Object second = context.getBean("mainRepository");
Object archive = context.getBean("archiveRepository");

System.out.println(first == second);    // true
System.out.println(first == archive);   // false
```

Đây là đoạn minh họa khi cả hai factory methods thực sự tạo object mới, không phải một class trả về cùng static object. Toán tử `==` so **reference identity**, chính là phép kiểm tra cần thiết để phân biệt scope singleton và hai beans khác nhau.

Bài học này giúp trả lời:

1. “Singleton” trong Spring thuộc **class**, **bean name** hay **ApplicationContext**?
2. Hai `@Bean` methods cùng return type có làm chung singleton không?
3. Một bean có alias khác có tạo object thứ hai không?
4. Hai `ApplicationContext` load cùng cấu hình có dùng chung instance không?
5. Vì sao nhiều controllers/services cùng inject một bean lại giữ chung reference?
6. `scope="singleton"` khác `prototype`, `request` và `session` thế nào?
7. Singleton cache, lifecycle, lazy initialization, `FactoryBean` và proxies ảnh hưởng identity ra sao?
8. Container đảm bảo gì về thread-safety, và developer còn phải tự bảo vệ state nào?
9. Làm sao kiểm chứng bằng Java 17+ và Spring Framework 6.2 một cách không phụ thuộc console hash code?

## 2. Mô hình trực quan: định danh bằng bean và container

Giả sử cùng class `ReportStore` được khai hai lần trong Context A, và một lần trong Context B:

```text
                   ApplicationContext A
     +-------------------------------------------+
     | BeanDefinition "primaryStore"  [singleton] |
     |               |                           |
     |               v                           |
     |         ReportStore object #A1             |
     |               ^                           |
     |     getBean("primaryStore") nhiều lần      |
     |                                           |
     | BeanDefinition "backupStore"   [singleton] |
     |               |                           |
     |               v                           |
     |         ReportStore object #A2             |
     +-------------------------------------------+

                   ApplicationContext B
     +-------------------------------------------+
     | BeanDefinition "primaryStore"  [singleton] |
     |               |                           |
     |               v                           |
     |         ReportStore object #B1             |
     +-------------------------------------------+
```

Các identity kỳ vọng khi factory mỗi context tạo object mới:

- A: `getBean("primaryStore")` lặp lại → object #A1.
- A: `getBean("backupStore")` → object #A2, khác #A1.
- B: `getBean("primaryStore")` → object #B1, khác #A1.
- Java class của #A1, #A2, #B1 **có thể giống hệt nhau**.

Vì vậy, nói “Spring chỉ tạo một `ReportStore` cho cả ứng dụng” là một phát biểu thiếu điều kiện. Nếu ứng dụng có nhiều bean definitions hoặc nhiều containers, nó có thể có nhiều `ReportStore` instances hợp lệ.

### 2.1. “Một bean” là khái niệm container metadata

Một Spring bean được nhận diện trong registry bằng **bean definition/registration cùng tên** và scope. Java class chỉ là một phần metadata. Những thuộc tính khác có thể gồm:

| Thuộc tính | Ví dụ | Vai trò |
| --- | --- | --- |
| Bean name | `primaryStore` | Lookup/DI theo tên |
| Alias | `storeForBilling` | Tên khác của cùng bean |
| Factory/class | `ReportStore` hoặc `@Bean` method | Cách Spring tạo bean |
| Scope | `singleton` | Chính sách tái sử dụng object |
| Constructor arguments | Repository/URL/config | Thông tin tạo object |
| Dependencies | `ref`/`@Qualifier`/method parameter | Quan hệ giữa managed beans |
| Lazy | `@Lazy` | Thời điểm khởi tạo |
| Lifecycle | init/destroy callbacks | Chu kỳ quản lý object |
| Candidate metadata | `@Primary`/qualifiers | Chọn bean khi inject by type |

Hai beans có cùng class nhưng khác name/config không phải hai aliases của một bean. Ngược lại, một bean có nhiều aliases vẫn là **một managed bean**.

### 2.2. Singleton không có nghĩa bean được tạo trước mọi thứ

Singleton mô tả **số instance được quản lý/tái sử dụng**, không phải thời điểm tạo. Trong `ApplicationContext`, singleton mặc định thường được eagerly pre-instantiated trong quá trình refresh. Nhưng `@Lazy` có thể trì hoãn tạo bean cho tới khi được yêu cầu, miễn là không có eager dependency kéo nó vào sớm.

Một singleton có thể chưa tồn tại dưới dạng instance, trong khi **bean definition đã tồn tại** trong registry. `containsBean("x")` và `containsSingleton("x")` không phải cùng một phép thử.

## 3. Đối chiếu với GoF Singleton pattern

Spring singleton là **per bean registration và container**; GoF Singleton thông dụng quản lý instance qua static holder/constructor giới hạn ở cấp Java class/ClassLoader. Một Spring `@Bean` có public constructor vẫn có thể singleton, còn GoF instance có thể được một factory trả chung cho nhiều containers. Việc dùng static global instance làm test isolation hoặc resource ownership khó hơn. Bài “Phân biệt singleton Spring với mẫu Singleton GoF” phân tích đầy đủ cơ chế, đưa ví dụ holder và output đối chứng.

## 4. Mặc định singleton trong XML và JavaConfig

### 4.1. XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="mainStore" class="demo.Store"/>

    <bean id="backupStore"
          class="demo.Store"
          scope="singleton"/>

</beans>
```

Đoạn là XML cấu hình minh họa; class `demo.Store` phải tồn tại. Hai bean definitions có hai names khác nhau. `scope="singleton"` ở bean thứ hai chỉ viết tường minh chính sách vốn đã là default.

### 4.2. JavaConfig

```java
@Configuration(proxyBeanMethods = false)
class StoreConfig {

    @Bean("mainStore")
    Store mainStore() {
        return new Store("main");
    }

    @Bean("backupStore")
    @Scope("singleton")
    Store backupStore() {
        return new Store("backup");
    }
}
```

Snippet minh họa cần imports và class `Store`. Annotation `@Scope("singleton")` ở bean thứ hai có tính minh họa, vì scope mặc định là singleton.

Đối với một `@Bean` method:
- Default bean name là **method name**, nếu không chỉ định `@Bean("name")`.
- Bean singleton thường được container tạo một lần rồi lưu để các requests sau tái sử dụng.
- Spring có thể chèn BeanPostProcessors, AOP proxies và lifecycle behavior xung quanh việc tạo bean; object trả về từ `getBean` có thể là managed proxy, không nhất thiết raw object được tạo bằng `new` trong method body.
- Direct Java calls tới factory method bên ngoài BeanFactory có semantics riêng, không tự động là bean lookup trong mọi cấu hình.

### 4.3. Component scanning

Một class:

```java
@Component
public class CatalogService {
}
```

thường được scan thành một bean definition (bean name theo naming strategy, ví dụ `catalogService`) với singleton scope mặc định.

Nhưng cùng class có thể được khai báo **thêm một definition khác** qua `@Bean` hoặc registration programmatic với một tên khác. Không có luật “mỗi `@Component` class chỉ có một bean trong toàn hệ thống”; số definitions thực tế do registration sources và collision rules quyết định.

Hãy kiểm soát quét trùng hoặc đăng ký song song. Nếu tên trùng, Spring có thể reject hoặc override tùy registry policy; nếu tên khác, bạn có thể có hai candidates cùng type và gây ambiguity cho by-type injection.

## 5. Hai bean definitions cùng class trong một container

Ví dụ:

```java
@Bean("primaryClient")
HttpClient primaryClient() {
    return new HttpClient("primary");
}

@Bean("auditClient")
HttpClient auditClient() {
    return new HttpClient("audit");
}
```

Đây là snippet không độc lập, class `HttpClient` là một domain type minh họa chứ không phải `java.net.http.HttpClient`. Với cùng context và hai definitions mặc định singleton:

```java
Object p1 = context.getBean("primaryClient");
Object p2 = context.getBean("primaryClient");
Object audit = context.getBean("auditClient");

boolean samePrimary = p1 == p2; // true
boolean differentBeans = p1 != audit; // true
```

### 5.1. Hai beans cùng class không cần có trạng thái giống nhau

`primaryClient` có thể được cấu hình timeout khác `auditClient`; cùng Java class không đồng nghĩa cùng behavior:

```xml
<bean id="primaryClient" class="demo.Client">
    <property name="region" value="north"/>
</bean>

<bean id="auditClient" class="demo.Client">
    <property name="region" value="south"/>
</bean>
```

Mỗi definition có metadata riêng. Singleton của `primaryClient` không thể tự suy ra cũng là singleton của `auditClient`.

### 5.2. By-type injection có thể trở nên ambiguous

Khi có hai beans kiểu `Client`:

```java
@Bean
ReportService reportService(Client client) {
    return new ReportService(client);
}
```

có thể không còn một ứng viên duy nhất. Nếu không có primary/qualifier/selection rule thích hợp, Spring có thể ném `NoUniqueBeanDefinitionException` hoặc bean-creation-related exception.

Giải pháp:
- `@Qualifier("primaryClient") Client client` trong method parameter hoặc constructor.
- `@Primary` trên default bean nếu đúng thiết kế.
- Dùng `List<Client>` khi consumer thực sự cần tất cả candidates.
- Không dùng `@Order` để “tự chọn” một singleton cho single injection; ordering collection và candidate selection là hai vấn đề khác.

### 5.3. Kiểm tra số lượng bằng name, không chỉ class

`context.getBeansOfType(Client.class)` có thể trả mapping của các bean names sang các objects cùng type. Nhưng số entries không phải lúc nào đồng nghĩa số objects vật lý nếu có aliases, FactoryBeans hoặc factories trả cùng reference có chủ đích. Vì vậy kết hợp:
- danh sách tên và definitions;
- `isSingleton("name")`;
- phép so sánh `==` trên references;
- test behavior và proxy semantics.

## 6. Alias: nhiều tên không tạo nhiều singleton

Spring cho phép một definition có nhiều tên.

XML:

```xml
<bean id="primaryStore" class="demo.Store"/>
<alias name="primaryStore" alias="billingStore"/>
<alias name="primaryStore" alias="shippingStore"/>
```

JavaConfig tương ứng:

```java
@Bean(name = {
        "primaryStore", "billingStore", "shippingStore"
})
Store primaryStore() {
    return new Store("primary");
}
```

Các fragments yêu cầu root/imports/classes phù hợp. Ba tên ở đây đều trỏ tới **một bean definition**. Với singleton:

```java
Object primary = context.getBean("primaryStore");
Object billing = context.getBean("billingStore");
Object shipping = context.getBean("shippingStore");

boolean same = primary == billing && billing == shipping;
```

`same` là true nếu các names là aliases đúng của singleton bean. Dùng alias để tương thích legacy naming hoặc chia sẻ tên giữa modules; đừng tạo nhiều `@Bean` methods chỉ để mô phỏng aliases.

### 6.1. Alias không phải bean thứ hai

Một số hệ thống in `getBeanDefinitionNames()` và kết luận alias bị “mất” vì không thấy tên thứ hai trong danh sách definitions. Điều đó là bình thường: alias registry và bean definition registry có semantics riêng.

Để kiểm tra:
- `context.containsBean("billingStore")` có thể trả true.
- `context.getAliases("primaryStore")` trả alias names đã đăng ký.
- `getBean("billingStore") == getBean("primaryStore")` chứng minh reference identity.

### 6.2. Alias không phải `@Primary` hay qualifier tự động

Một alias chỉ là tên khác. Nó không ép Spring chọn bean ấy khi có nhiều beans cùng type. Nếu single dependency ambiguous, dùng qualifier/primary hoặc explicit name lookup có chủ đích.

## 7. Nhiều consumers inject cùng singleton

Một tình huống phổ biến:

```text
       Bean "sharedRepository" (singleton)
                  |
       +----------+----------+
       |                     |
       v                     v
 ServiceA.repository    ServiceB.repository
       |                     |
       +------ same object --+
```

JavaConfig:

```java
@Bean("sharedRepository")
Repository sharedRepository() {
    return new Repository();
}

@Bean("serviceA")
ServiceA serviceA(Repository repository) {
    return new ServiceA(repository);
}

@Bean("serviceB")
ServiceB serviceB(Repository repository) {
    return new ServiceB(repository);
}
```

Đây là đoạn minh họa; để chắc chắn selection đúng nếu nhiều repositories, thêm `@Qualifier("sharedRepository")`.

Spring resolve bean dependency và cung cấp same singleton reference cho các consumers trong **cùng container**. Thực tế, trong một hệ thống có AOP, reference có thể là **same proxy** đại diện managed bean; điều cần giữ là consumers nhận đúng Spring-managed reference chứ không tự `new` một object khác.

### 7.1. Field của consumers không phải hai copies

Nếu `ServiceA` giữ `repository` và `ServiceB` giữ `repository`, đó chỉ là hai Java references trỏ tới cùng object. Gọi phương thức trên một reference có thể thay đổi runtime state được quan sát qua reference kia nếu repository mutable.

Tính chia sẻ này hữu ích cho:
- stateless service beans;
- shared connection pool manager;
- singleton cache;
- configuration registry;
- immutable lookup tables;
- managed cross-cutting infrastructure.

Nhưng cũng tạo rủi ro nếu bean lưu state riêng theo request hoặc user.

### 7.2. Singleton không có nghĩa mỗi method call tạo object

Một controller singleton nhận một service singleton không tạo service mới khi mỗi request đến. Constructor/factory method của singleton thông thường chạy một lần **khi bean được tạo**. Các business method calls trên object đã có có thể chạy rất nhiều lần và có thể chạy đồng thời.

Nếu một singleton method cần object mới mỗi invocation, hãy thiết kế creation riêng: local object `new` không cần container, `ObjectProvider<PrototypeBean>`, factory abstraction hoặc scoped object phù hợp.

## 8. Mỗi `ApplicationContext` thường có cache singleton riêng

Trong một ứng dụng Java, bạn có thể tạo:

```java
var first =
        new AnnotationConfigApplicationContext(MyConfig.class);
var second =
        new AnnotationConfigApplicationContext(MyConfig.class);
```

Đây là snippet minh họa, cần imports/class `MyConfig`. Hai `AnnotationConfigApplicationContext` instances là **hai IoC containers độc lập**. Mỗi context đăng ký bean definitions theo `MyConfig` rồi khởi tạo/cache beans của chính nó.

Với factory method:

```java
@Bean
Widget widget() {
    return new Widget();
}
```

thì thông thường:

```java
Object left = first.getBean("widget");
Object right = second.getBean("widget");

boolean different = left != right; // true
```

**Không được khẳng định “đúng vì cùng classloader sẽ chia sẻ instance”.** Cùng classloader chỉ ảnh hưởng class/static metadata; Spring singleton cache vẫn theo container.

### 8.1. Context test caching là ngoại lệ ở “đếm số contexts”

Spring TestContext Framework có thể **cache/reuse cùng một ApplicationContext** giữa nhiều test cases khi cấu hình context được xem là tương thích. Vì vậy hai test methods dùng `@SpringJUnitConfig` không chắc tự tạo hai containers khác nhau.

Khi cần một context mới cho test isolation, thiết kế test fixtures riêng hoặc sử dụng `@DirtiesContext` trong tình huống đúng; đừng đoán “mỗi test class = context mới”. Đây là khác biệt của test framework reuse, không phải vi phạm singleton scope.

### 8.2. Spring Boot không mặc nhiên là một singleton toàn JVM

Một Spring Boot application run thường có một root application context chính, nhưng có thể có nhiều contexts tùy test setup, parent-child integration, management contexts hay nhiều ứng dụng nhúng trong một JVM. Bean singleton không tự xuyên các context boundaries.

### 8.3. Parent-child context hierarchy

Với context cha/con:
- Child có thể lookup bean ở parent khi không có local bean cùng tên và parent visibility cho phép.
- Nếu child dùng bean parent bằng delegation, reference trả về có thể **chính là singleton thuộc parent**.
- Child có thể đăng ký một local bean cùng tên, che khuất parent bean trong lookup từ child.
- Mỗi context vẫn có singleton cache/ownership của nó; delegation không có nghĩa cache được “hợp nhất” thành một toàn cục.

Do đó phát biểu đúng không phải “mọi hai contexts bắt buộc trả object khác nhau”, mà là **singleton thuộc container sở hữu bean definition**. Nếu child trả parent bean, nó đang trả instance **do parent quản lý**; nếu hai contexts đăng ký definitions độc lập, mỗi cái thường tạo instance riêng.

### 8.4. Một factory trả static instance có thể được hai contexts dùng chung

Ví dụ:

```java
final class GlobalClient {
    static final GlobalClient INSTANCE = new GlobalClient();

    private GlobalClient() {
    }
}

@Configuration(proxyBeanMethods = false)
class SharedConfig {
    @Bean("client")
    GlobalClient client() {
        return GlobalClient.INSTANCE;
    }
}
```

Mã trên minh họa một intentional static instance. Hai contexts cùng dùng `SharedConfig` sẽ nhận **cùng Java object** nếu ClassLoader/class identity cũng dùng chung.

Điều này **không xóa định nghĩa per container**: mỗi context vẫn có một singleton registration/cache entry riêng, nhưng hai factory methods cùng trả reference đã tồn tại. Đó là kết quả của **user factory code**, không phải Spring tự phát minh global singleton.

**Rủi ro:** nếu cùng instance resource được nhiều contexts xem là thuộc sở hữu và cả hai đăng ký destroy callback, object có thể bị đóng nhiều lần. Tránh chia sẻ static resources giữa containers khi lifecycle ownership không rõ.

## 9. Singleton cache và lifecycle

### 9.1. Bean definition khác bean instance

Spring có metadata cho bean name trước khi object được tạo. Singleton instance được lưu trong container sau khi Spring xử lý creation/initialization theo lifecycle. Ở mức conceptual:

```text
BeanDefinition("catalogService", scope=singleton)
                      |
                      v
          BeanFactory cần instance?
                 /          \
               chưa         có
                |           |
          tạo/cấu hình      |
           object           |
                |           |
             cache ----------+
                |
                v
        getBean("catalogService")
          trả managed reference
```

Implementation thực tế của Spring còn có caches/early singleton references/factory handling để hỗ trợ những tình huống phức tạp như circular dependency, AOP và singleton registration. Sơ đồ đơn giản **không** phải một mô tả đầy đủ mọi internal map/lock.

### 9.2. Eager singleton là default trong `ApplicationContext`

Non-lazy singleton thường được tạo khi context refresh hoàn tất. Điều này giúp fail-fast nếu:
- constructor ném exception;
- dependencies không tồn tại;
- init callback lỗi;
- configuration metadata sai.

Dùng `@Lazy` trên bean definition:

```java
@Bean
@Lazy
ExpensiveClient expensiveClient() {
    return new ExpensiveClient();
}
```

có thể trì hoãn tạo bean cho tới khi cần. Nhưng nếu một eager singleton consumer inject dependency này trực tiếp, Spring vẫn phải tạo nó để thỏa dependency. Lazy không thay đổi “mỗi bean definition một singleton” mà chỉ đổi **mốc tạo**.

### 9.3. `containsSingleton` và `isSingleton` không có cùng nghĩa

Spring BeanFactory/registry cung cấp các phép kiểm tra khác nhau:

| API | Ý nghĩa gần đúng |
| --- | --- |
| `containsBean("x")` | Bean với name/alias đó có thể được tìm trong factory/hierarchy phù hợp |
| `containsBeanDefinition("x")` | Có **local bean definition** tên `x` trong registry |
| `containsSingleton("x")` | Có singleton instance đã đăng ký/cache trong singleton registry local |
| `isSingleton("x")` | Bean được xem là singleton khi lookup theo BeanFactory contract |
| `isPrototype("x")` | Bean được xem là prototype theo BeanFactory contract |
| `getBean("x")` | Yêu cầu instance; có thể kích hoạt bean creation |

Đặc biệt, một bean `@Lazy` singleton có thể khiến `containsSingleton("x") == false` trước lookup nhưng `isSingleton("x") == true`. Đừng suy ra “chưa cache” nghĩa là “scope prototype”.

FactoryBeans và scoped proxies có thể khiến câu hỏi `isSingleton(name)` phức tạp hơn; đọc API contract và biết đang hỏi **factory** hay **product**.

### 9.4. Lúc context đóng

Một `ConfigurableApplicationContext` được đóng đúng cách sẽ chạy các destroy callbacks phù hợp cho managed singleton beans. Bean definition không nhất thiết sống mãi trong JVM, và Spring không bảo đảm vẫn sử dụng được managed reference sau khi context đã đóng.

Với JavaConfig:

```java
@Bean(name = "resource", destroyMethod = "close")
ManagedResource resource() {
    return new ManagedResource();
}
```

Container gọi `close` theo lifecycle khi context close bình thường.

Spring còn có **destroy method inference** trên `@Bean` nếu class có public no-argument `close` hoặc `shutdown`; khi không muốn infer callback đó, `@Bean(destroyMethod="")` có thể vô hiệu phần suy luận này, nhưng không tắt mọi lifecycle contract như `DisposableBean`.

### 9.5. Không dùng `System.identityHashCode` làm bằng chứng duy nhất

`System.identityHashCode(obj)` cho một số hữu ích khi debug, nhưng **hai objects khác nhau có thể va chạm cùng identity hash code**. Kiểm tra identity bằng `==`. Nếu cần trình bày stdout ổn định, in boolean từ phép so sánh thay vì dựa vào địa chỉ/hashes biến thiên mỗi run.

## 10. Singleton không tự bảo đảm state thread-safe

Spring công bố singleton đã khởi tạo qua container theo quy tắc lifecycle, nhưng mọi thread gọi business method trên cùng singleton vẫn có thể tranh chấp state mutable. Ví dụ `private int hits;` và `++hits` không atomic, làm mất cập nhật khi gọi đồng thời. Ưu tiên singleton service **stateless**, để dữ liệu từng request trong method parameters/local variables; khi cần shared counter dùng `AtomicInteger` hoặc lock phù hợp.

`final` chỉ giữ reference ổn định; dependency mutable bên trong không tự trở thành thread-safe. `volatile` không biến `count++` thành atomic. Bài “Trạng thái dùng chung và an toàn luồng của singleton” đi sâu Java Memory Model, immutable snapshot, `Atomic*`, concurrent collections và kiểm thử race.

## 11. So sánh singleton với các scopes khác

`singleton` tái sử dụng một managed instance theo bean/container; `prototype` tạo bean mỗi lần container resolve, `request` và `session` ràng theo HTTP request/session trong web context, `application` theo ServletContext, `websocket` theo STOMP session. Web scope cần hạ tầng hỗ trợ; Spring không tự hủy prototype khi context đóng.

Nếu singleton constructor-inject prototype trực tiếp, instance prototype được giữ lại tại thời điểm inject; dùng `ObjectProvider<T>` khi cần tạo mới theo mỗi operation. Nếu inject request bean, dùng scoped proxy hoặc provider trong request đang active. Nhớ rằng proxy reference có thể singleton dù target đổi theo scope.

## 12. Cấu hình Java và trường hợp gọi `@Bean` method trực tiếp

Một trong những lỗi hiểu sai phổ biến: “`@Bean` method chỉ chạy một lần, nên gọi method đó trực tiếp luôn cho singleton”.

Cần phân biệt hai modes.

### 12.1. Full `@Configuration(proxyBeanMethods=true)`

Ở full configuration mode mặc định, Spring có thể tăng cường configuration class bằng CGLIB. Những lời gọi inter-bean method trên managed configuration instance có thể được intercept để trả bean theo scope từ container.

```java
@Configuration
class FullConfig {

    @Bean
    Repository repository() {
        return new Repository();
    }

    @Bean
    Service service() {
        return new Service(repository());
    }
}
```

Đây là snippet minh họa. Trong full mode, lời gọi `repository()` từ `service()` có thể đi qua Spring inter-bean interception và nhận singleton managed object.

### 12.2. `@Configuration(proxyBeanMethods=false)`

Ở lite/non-intercepted mode:

```java
@Configuration(proxyBeanMethods = false)
class LiteConfig {

    @Bean
    Repository repository() {
        return new Repository();
    }

    @Bean
    Service service() {
        return new Service(repository());
    }
}
```

Lời gọi `repository()` trong `service()` là **Java method call thông thường**, có thể tạo raw Repository thứ hai, không phải managed singleton `repository` mà BeanFactory đăng ký.

Cấu hình tốt hơn:

```java
@Bean
Service service(Repository repository) {
    return new Service(repository);
}
```

Factory-method parameter injection bảo đảm BeanFactory cung cấp managed dependency và không phụ thuộc vào inter-bean CGLIB interception.

### 12.3. Gọi method trên một config object do `new` tạo

```java
LiteConfig config = new LiteConfig();
Repository raw = config.repository();
```

Đây không phải `context.getBean("repository")`. Annotation `@Bean` chỉ có semantics Spring khi definition được đăng ký/xử lý trong context; trực tiếp gọi method trên object tự tạo là Java code bình thường.

Hãy kiểm tra identity qua managed API thay vì quan sát method name có `@Bean` rồi suy ra các lời gọi thủ công đều được singleton-cache.

## 13. FactoryBean, alias, và singleton semantics nâng cao

`FactoryBean<T>` khác với `@Bean` factory method:

- Bean definition có thể đăng ký một **factory object** implement `FactoryBean<T>`.
- `getBean("name")` thường yêu cầu **product** do factory cung cấp.
- `getBean("&name")` yêu cầu **factory bean instance**.
- `FactoryBean#isSingleton()` quyết định semantics product object và cache theo contract factory; nó không tự cùng nghĩa với scope của bean definition chứa factory.

Ví dụ conceptual:

```java
FactoryBean<?> factory =
        (FactoryBean<?>) context.getBean("&clientFactory");

Object product = context.getBean("clientFactory");
```

Cần một bean tên `clientFactory` thật sự implement `FactoryBean`. Hai references thường thuộc **hai lớp đối tượng khác nhau**: factory và product.

Một factory singleton có thể tạo product non-singleton, tùy `isSingleton()`. Ngược lại, các singleton products được cache theo product contract. Vì vậy **đừng dùng `isSingleton("name")` một cách mù quáng** rồi cho rằng đã kiểm tra cùng một layer; tìm hiểu API semantics của FactoryBean khi có product/factory indirection.

### 13.1. Một bean name có thể trả AOP proxy

Bean singleton được AOP post-processors bao bọc có thể khiến `getBean("service")` trả proxy. So sánh `==` nhiều lần trên same name vẫn cho thấy managed singleton reference được tái sử dụng, nhưng raw target và proxy không phải cùng Java object.

Điều này không biến singleton thành prototype. Container quản lý một **exposed singleton reference** cho bean đó, có thể là proxy. Nếu thử identity, hãy so **consumer-visible references**, không tự dựng target raw object rồi đòi `==` với proxy.

### 13.2. Bean definitions có thể được thay thế/override

Trong các container/bootstraps cho phép override bean definition, cùng bean name có thể được đăng ký lại có kiểm soát. Đây không phải hành vi nên dựa vào để chia sẻ singleton across modules. Đặc biệt khi test dùng `@MockitoBean` hoặc `@TestBean`, instance quan sát được có thể bị thay/wrap bởi test infrastructure.

Luôn xác định **runtime context và bean definition thực tế** đang được test, không chỉ đọc một file `@Configuration`.

## 14. Ví dụ Java 17+ chạy được: bean identity và context ownership

Demo chứng minh trực tiếp:
- Trong một context, hai lần `getBean("primaryRepo")` trả cùng object.
- `repoAlias` trỏ cùng bean as `primaryRepo`.
- Hai `@Bean` definitions trả cùng class `NamedRepository` nhưng giữ hai objects riêng.
- Hai consumers cùng inject managed primary repository thì giữ chung instance.
- Hai contexts load cùng `DemoConfig` có riêng primary repository khi mỗi factory call tạo object bằng `new`.
- Prototype bean trả instance mới theo mỗi lookup.
- Tự `new NamedRepository` không phải lookup container-managed bean.
- Resource singleton có lifecycle độc lập theo từng context: đóng context thứ nhất không đóng resource thuộc context thứ hai.

**Dự án:** Spring Context 6.2.19, Java 17+, Gradle, không dùng Spring Boot hay database.

### 14.1. Cấu trúc thư mục

```text
spring-singleton-boundaries/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── SingletonBoundariesDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-singleton-boundaries'
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
    mainClass = 'demo.SingletonBoundariesDemo'
}
```

Spring `spring-context` kéo theo những Spring Beans/Core modules cần thiết; code không sử dụng web scopes. Dùng một Gradle version tương thích với JDK 17+ của bạn.

### 14.2. Java source hoàn chỉnh

Lưu `src/main/java/demo/SingletonBoundariesDemo.java`:

```java
package demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public final class SingletonBoundariesDemo {

    public static final class NamedRepository {
        private final String name;

        public NamedRepository(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }
    }

    public static final class CatalogService {
        private final NamedRepository repository;

        public CatalogService(NamedRepository repository) {
            this.repository = repository;
        }

        public NamedRepository repository() {
            return repository;
        }
    }

    public static final class Ticket {
        public Ticket() {
        }
    }

    public static final class ManagedResource {
        private boolean closed;

        public void close() {
            closed = true;
        }

        public boolean isClosed() {
            return closed;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DemoConfig {

        @Bean(name = {"primaryRepo", "repoAlias"})
        public NamedRepository primaryRepo() {
            return new NamedRepository("primary");
        }

        @Bean("archiveRepo")
        public NamedRepository archiveRepo() {
            return new NamedRepository("archive");
        }

        @Bean("catalogService")
        public CatalogService catalogService(
                @Qualifier("primaryRepo")
                NamedRepository repository) {
            return new CatalogService(repository);
        }

        @Bean("auditService")
        public CatalogService auditService(
                @Qualifier("primaryRepo")
                NamedRepository repository) {
            return new CatalogService(repository);
        }

        @Bean("ticket")
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public Ticket ticket() {
            return new Ticket();
        }

        @Bean(name = "managedResource",
              destroyMethod = "close")
        public ManagedResource managedResource() {
            return new ManagedResource();
        }
    }

    private static void verify(boolean condition,
                               String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        ManagedResource firstResource;
        ManagedResource secondResource;

        try (var second = new AnnotationConfigApplicationContext(
                DemoConfig.class)) {

            secondResource = second.getBean(
                    "managedResource", ManagedResource.class);

            try (var first =
                    new AnnotationConfigApplicationContext(
                            DemoConfig.class)) {

                NamedRepository primary1 = first.getBean(
                        "primaryRepo", NamedRepository.class);
                NamedRepository again = first.getBean(
                        "primaryRepo", NamedRepository.class);
                NamedRepository byAlias = first.getBean(
                        "repoAlias", NamedRepository.class);
                NamedRepository archive = first.getBean(
                        "archiveRepo", NamedRepository.class);
                NamedRepository primary2 = second.getBean(
                        "primaryRepo", NamedRepository.class);

                CatalogService catalog = first.getBean(
                        "catalogService", CatalogService.class);
                CatalogService audit = first.getBean(
                        "auditService", CatalogService.class);

                Object ticket1 = first.getBean("ticket");
                Object ticket2 = first.getBean("ticket");
                NamedRepository outside =
                        new NamedRepository("manual");

                firstResource = first.getBean(
                        "managedResource", ManagedResource.class);

                boolean repeatedSame = primary1 == again;
                boolean aliasSame = primary1 == byAlias;
                boolean definitionsDistinct = primary1 != archive;
                boolean sameClass =
                        primary1.getClass() == archive.getClass();
                boolean consumersShare =
                        catalog.repository() == audit.repository()
                        && catalog.repository() == primary1;
                boolean separateContexts = primary1 != primary2;
                boolean prototypeDistinct = ticket1 != ticket2;
                boolean manualOutside = outside != primary1;
                boolean metadataMatches =
                        first.isSingleton("primaryRepo")
                        && first.isSingleton("archiveRepo")
                        && first.isPrototype("ticket");

                verify(repeatedSame, "Same bean lookup differs");
                verify(aliasSame, "Alias is not same bean");
                verify(definitionsDistinct,
                        "Different definitions unexpectedly shared");
                verify(sameClass, "Repositories not same class");
                verify(consumersShare,
                        "Consumers did not share primary bean");
                verify(separateContexts,
                        "Contexts did not own separate objects");
                verify(prototypeDistinct,
                        "Prototype lookups returned same object");
                verify(manualOutside,
                        "Manual new must not be managed lookup");
                verify(metadataMatches,
                        "Unexpected Spring scope metadata");
                verify(!firstResource.isClosed(),
                        "First resource closed too early");
                verify(!secondResource.isClosed(),
                        "Second resource closed too early");

                System.out.println("sameLookup=" + repeatedSame);
                System.out.println("aliasSame=" + aliasSame);
                System.out.println("sameClass=" + sameClass);
                System.out.println("differentBeanDefinitions=" +
                        definitionsDistinct);
                System.out.println("consumersShare=" + consumersShare);
                System.out.println("differentContexts=" +
                        separateContexts);
                System.out.println("prototypeDifferent=" +
                        prototypeDistinct);
                System.out.println("manualNewDifferent=" +
                        manualOutside);
                System.out.println("scopeMetadataCorrect=" +
                        metadataMatches);
            }

            verify(firstResource.isClosed(),
                    "First context must close its resource");
            verify(!secondResource.isClosed(),
                    "Second context must remain active");

            System.out.println("firstResourceClosed=" +
                    firstResource.isClosed());
            System.out.println("secondResourceStillOpen=" +
                    !secondResource.isClosed());
        }

        verify(secondResource.isClosed(),
                "Second context must close its resource");
        System.out.println("secondResourceClosed=" +
                secondResource.isClosed());
    }
}
```

Code có một top-level public class, domain classes lồng static để tiết kiệm files. `@Configuration(proxyBeanMethods=false)` được dùng vì **mọi `@Bean` method đều nhận managed dependencies qua parameters** chứ không tự gọi factory method khác trực tiếp.

Hai methods `catalogService`/`auditService` cùng return type `CatalogService` nhưng là hai singleton definitions riêng, trong khi cả hai consumers đều giữ **cùng instance** `NamedRepository` dưới bean name `primaryRepo`.

### 14.3. Lệnh chạy và stdout dự kiến

Tại thư mục `spring-singleton-boundaries`:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper:

```bash
./gradlew run --quiet
```

Windows PowerShell:

```powershell
.\gradlew.bat run --quiet
```

Các dòng do `System.out.println` tạo:

```text
sameLookup=true
aliasSame=true
sameClass=true
differentBeanDefinitions=true
consumersShare=true
differentContexts=true
prototypeDifferent=true
manualNewDifferent=true
scopeMetadataCorrect=true
firstResourceClosed=true
secondResourceStillOpen=true
secondResourceClosed=true
```

Tùy Gradle/logging backend, terminal có thể in thêm dòng ngoài stdout nghiệp vụ. Chương trình dừng bằng `AssertionError` nếu một contract không đạt, không chỉ “in giá trị để người học tự đoán”.

### 14.4. Vì sao từng kết quả đúng?

**`sameLookup=true`:** `getBean("primaryRepo")` hai lần trong cùng container trả managed singleton. Spring không gọi lại `primaryRepo()` mỗi lookup.

**`aliasSame=true`:** `repoAlias` là alias của `primaryRepo`, nên cả hai tên trỏ cùng bean.

**`sameClass=true` và `differentBeanDefinitions=true`:** `primaryRepo` và `archiveRepo` đều là `NamedRepository` nhưng được tạo bởi hai `@Bean` definitions khác nhau. Mỗi factory method dùng `new` một object riêng.

**`consumersShare=true`:** hai factory methods `catalogService` và `auditService` đều yêu cầu `@Qualifier("primaryRepo") NamedRepository`, vì vậy Spring truyền cùng managed primary repository cho hai consumers.

**`differentContexts=true`:** hai `AnnotationConfigApplicationContext` được tạo độc lập; mỗi context gọi factory method của mình để tạo primary repository. Chúng không dùng shared static object.

**`prototypeDifferent=true`:** `Ticket` có `@Scope(PROTOTYPE)`, nên hai lookups trong cùng container tạo hai objects.

**`manualNewDifferent=true`:** `new NamedRepository("manual")` là object độc lập ngoài registration `primaryRepo`. Spring không đồng nhất raw object mới với cached bean chỉ vì Java class giống.

**`scopeMetadataCorrect=true`:** registry cho biết hai repository beans singleton và `ticket` prototype. Metadata test bổ trợ cho identity test, không thay thế identity test.

**Ba dòng Resource:** context `first` đóng trước context `second`. `ManagedResource` thuộc `first` nhận `close()` trong khi resource thuộc `second` vẫn mở. Khi `second` đóng, resource đó mới được đóng. Đây là lifecycle ownership theo **container**, không theo Java class.

### 14.5. Các giới hạn của demo

Ví dụ không chứng minh mọi bean từ hai contexts luôn khác identity: một factory method trả static shared object hoặc context con delegation có thể làm hai lookup trả cùng object. Demo dùng `new` trong từng factory method và hai containers độc lập để cô lập quy tắc thông thường.

Nó cũng không bao phủ AOP proxies, `FactoryBean`, web session/request scope hoặc mutating singleton under concurrent load. Những chủ đề này có semantics riêng cần test bổ sung.

## 15. Debug: khi nào “singleton” trông như tạo nhiều lần?

### 15.1. Có nhiều contexts mà không nhận ra

Một test suite, web app hoặc child-context setup có thể tạo nhiều `ApplicationContext` instances. Nếu log constructor xuất hiện nhiều lần, kiểm tra **bao nhiêu containers đang tồn tại**, không vội kết luận Spring vi phạm singleton scope.

### 15.2. Đăng ký cùng class dưới nhiều bean names

Hai `@Bean` methods hoặc XML `<bean>` definitions dùng cùng class có thể tạo hai objects. Dùng `getBeanDefinitionNames()`/`getBeansOfType(...)` để kiểm tra.

### 15.3. Object được tạo bằng `new` bên ngoài BeanFactory

Mã như:

```java
var rawService = new CatalogService(new Repository());
```

không nhận shared singleton của Spring dù domain classes giống. Nếu cùng lúc Spring có `@Bean CatalogService`, sẽ tồn tại ít nhất một raw instance và một managed instance. Đừng gắn scope semantics lên mọi object của class có annotation.

### 15.4. Direct call tới `@Bean` method trong lite mode

Với `proxyBeanMethods=false`, inter-bean call `repository()` là Java method invocation và có thể tạo object ngoài managed definition. Dùng parameters thay vì direct method calls.

### 15.5. Bean thực ra có `@Scope("prototype")`

Một override annotation, meta-annotation, XML definition hoặc custom scope có thể làm bean không singleton. Kiểm tra `isSingleton(name)`/`isPrototype(name)` trong chính context đang dùng và hiểu proxy/factory semantics.

### 15.6. Proxy và target không trùng object

Một AOP proxy có thể khác raw target object. Gọi `proxy == target` có thể false, nhưng managed bean exposed qua `getBean(name)` vẫn singleton. So sánh reference ở **cùng layer**, đừng trộn raw object và proxy.

### 15.7. FactoryBean trả product với scope khác

`FactoryBean#isSingleton()` điều khiển product caching riêng; factory bean itself có definition scope khác. Cần phân biệt `&beanName` và `beanName` khi điều tra số lượng instances.

### 15.8. Test context được rebuild

`@DirtiesContext` hoặc test configuration changes có thể làm Spring TestContext đóng/recreate context, dẫn tới bean singleton được tạo mới hợp lệ. Thay đổi profile/mock beans/property sources có thể khiến cache key khác nhau.

### 15.9. Lazy singleton chưa tạo ở startup

Bean definition singleton tồn tại nhưng constructor chưa chạy vì `@Lazy`. Lần đầu `getBean` kích hoạt tạo; đây không phải prototype. Kiểm tra `isSingleton` và `containsSingleton` thay vì chỉ đếm log.

### 15.10. Bean được tạo hai lần do lifecycle/circular reference issues

Trong cấu hình phức tạp, BeanPostProcessor/proxy/circular dependency failures hoặc retry ở application level có thể dẫn tới nhiều constructor logs mà chỉ một instance cuối cùng được publish dưới bean name. Đừng dựa vào số dòng constructor log làm **chứng cứ độc lập** về singleton cache; kiểm tra bean definitions, proxying và exception chain.

## 16. Cách kiểm thử scope và ownership có chủ đích

### 16.1. Identity test trong cùng context

```java
Object a = context.getBean("primaryRepo");
Object b = context.getBean("primaryRepo");
assert a == b;
```

Dùng Java assertions cần bật `-ea` khi chạy, hoặc dùng JUnit `assertSame(a,b)` để không phụ thuộc JVM flag. Demo mục 14 dùng helper `verify(...)` ném `AssertionError` trực tiếp.

### 16.2. Multiple definitions test

```java
Object a = context.getBean("primaryRepo");
Object b = context.getBean("archiveRepo");
assert a != b;
```

Đây là expected result nếu hai factory definitions tạo objects riêng. Nếu factory methods intentionally trả một shared static instance, test cần biết contract khác ấy.

### 16.3. Context isolation test

```java
Object left = first.getBean("primaryRepo");
Object right = second.getBean("primaryRepo");
assert left != right;
```

Chỉ diễn đạt khi first và second là **hai containers sở hữu definitions riêng** và không dùng static shared instance/factory delegation. Nó không áp dụng mù quáng cho child context lookup bean của parent.

### 16.4. Alias test

```java
Object primary = context.getBean("primaryRepo");
Object alias = context.getBean("repoAlias");
assert primary == alias;
```

Nếu không bằng nhau, kiểm tra alias có được đăng ký đúng không và đang lookup trên cùng context không.

### 16.5. Consumer reference test

```java
CatalogService a = context.getBean(
        "catalogService", CatalogService.class);
CatalogService b = context.getBean(
        "auditService", CatalogService.class);

assert a != b;
assert a.repository() == b.repository();
```

Đây là điểm hay: **hai service singleton objects khác nhau**, nhưng vẫn **chia sẻ cùng singleton repository**. Học viên thường nhầm “inject cùng type” với “chỉ có một service instance toàn context”.

### 16.6. Lifecycle isolation test

Đóng một context trong khi context khác vẫn hoạt động; kiểm tra resource singleton do context đóng được cleanup, resource context đang mở vẫn active. Không dùng global static counters nếu chúng làm nhiễu boundary giữa contexts; dùng instance state như demo.

### 16.7. Concurrency test

Với singleton counter, chạy nhiều threads gọi `incrementAndGet` và assert tổng chính xác khi dùng atomic/lock. Test này kiểm tra **thread safety business state**, không phải tự kiểm tra singleton scope. Luôn tách hai assertions.

## 17. Những ngộ nhận phổ biến

| Ngộ nhận | Điều đúng |
| --- | --- |
| “Singleton = một instance mỗi Java class” | Spring singleton là per bean definition trong một container |
| “Một JVM chỉ có một Spring singleton của class X” | JVM có thể có nhiều contexts và nhiều definitions |
| “Hai `@Bean` methods cùng return class nên dùng chung object” | Mỗi bean definition độc lập trừ khi factory trả chung reference |
| “Bean alias tạo singleton mới” | Alias là tên khác của cùng bean definition |
| “`@Component` tự đảm bảo không có definition thứ hai” | Nhiều registration sources có thể tạo definitions khác nhau |
| “Hai services inject Repository thì Spring copy Repository” | Managed singleton dependency được dùng chung trong cùng context |
| “Singleton = luôn tạo lúc JVM startup” | Scope khác creation timing; có `@Lazy` và dependency-driven creation |
| “Singleton = thread-safe toàn bộ state” | Container safe-publication, business state vẫn cần synchronization |
| “`@Bean` method luôn singleton dù gọi trực tiếp” | Direct Java calls trong lite mode không phải BeanFactory lookup |
| “Prototype = instance mới sau mỗi service method call” | Prototype tạo theo lookup; singleton injection chỉ resolve một lần |
| “Một resource singleton được hai contexts tự động cùng share” | Thường mỗi container có instance riêng; có ngoại lệ factory trả static |
| “`getBeanDefinitionCount()` bằng số objects” | Definitions, aliases, proxies, FactoryBeans, scopes làm khác biệt |
| “`getClass()` cho biết mọi details bean target” | AOP/scoped proxy có runtime class khác target |
| “Context đóng thì mọi prototype auto cleanup” | Prototype cleanup thường do consumer/owner đảm nhận |
| “Singleton cache của child và parent luôn tách biệt mọi lookup” | Child có thể delegate lookup đến parent-owned singleton |
| “FactoryBean singleton luôn trả singleton product” | Factory scope và `FactoryBean#isSingleton()` là hai tầng |
| “Static singleton chắc chắn an toàn khi được nhiều contexts đóng” | Shared resource có thể bị destroy nhiều lần |
| “Cứ thêm `@Primary` là chỉ còn một bean” | `@Primary` chọn default candidate, không xóa bean khác |
| “Gọi `new Repository()` là nhận bean Spring vì class có annotation” | Raw object không trở thành managed bean chỉ do class annotation |
| “Constructor log nhiều dòng chứng minh Spring tạo nhiều singleton final instances” | Cần kiểm tra container, proxies, failed creations và identity |

## 18. Bài tập có đáp án

### Bài 1 — Một class, hai definitions

Trong một context:

```java
@Bean("left") Store left() { return new Store("left"); }
@Bean("right") Store right() { return new Store("right"); }
```

Hai bean names có thể cùng singleton scope không? Và có cùng instance không?

**Đáp án:** Có, mỗi definition là một singleton. Với factory methods `new` như trên, chúng tạo hai instances riêng.

### Bài 2 — Một definition, hai lookup

`getBean("left")` hai lần trong một context trả gì?

**Đáp án:** Cùng managed singleton reference nếu bean `left` là singleton.

### Bài 3 — Hai contexts

Hai `AnnotationConfigApplicationContext` độc lập cùng register một `@Bean Store store(){return new Store();}`. Có bảo đảm cùng instance không?

**Đáp án:** Không. Mỗi context thường tạo/cache Store riêng; static shared return là một ngoại lệ do factory code.

### Bài 4 — Aliases

`@Bean(name={"store","sharedStore"})` có tạo hai bean definitions không?

**Đáp án:** Không. `sharedStore` là alias của `store`, khi scope singleton hai lookups cùng reference.

### Bài 5 — Hai consumers

Service A và B cùng inject `@Qualifier("store") Store`. Nếu Store singleton, A và B giữ bao nhiêu Store objects?

**Đáp án:** Một shared Store reference từ bean definition đó trong cùng context.

### Bài 6 — Java `new`

`new Store()` trong một unit test có trả object từ `context.getBean(Store.class)` không?

**Đáp án:** Không, trừ khi bạn chủ động đăng ký/trả lại chính object đó; thông thường `new` độc lập với Spring registry.

### Bài 7 — Lazy singleton

`@Bean @Lazy Store store()`, sau refresh `containsSingleton("store")` có thể false. Điều đó chứng minh prototype không?

**Đáp án:** Không. Bean definition vẫn singleton; chỉ chưa instantiated.

### Bài 8 — Primary

Có hai `DataSource` beans, một `@Primary`. Có phải bean kia không còn singleton?

**Đáp án:** Không. Cả hai definitions có thể singleton, `@Primary` chỉ hỗ trợ chọn single dependency.

### Bài 9 — Prototype vào singleton

`ReportService` singleton inject `Ticket` prototype qua constructor một lần. Mỗi `report()` call có một Ticket mới không?

**Đáp án:** Không; singleton giữ prototype object đã inject. Nếu cần mới mỗi operation, dùng provider/factory lookup.

### Bài 10 — Prototype trực tiếp

Hai `context.getBean("ticket")` với prototype scope và factory luôn `new Ticket()` có cùng object không?

**Đáp án:** Không, mỗi lookup nhận một instance mới.

### Bài 11 — Safe publication

Singleton có cấu hình immutable được set trước initialization hoàn tất. Các threads khác lookup từ container có visibility phù hợp không?

**Đáp án:** Container bảo đảm safe publication cho initialized singleton. Nhưng các updates **sau startup** vẫn cần concurrency controls theo Java Memory Model.

### Bài 12 — Mutable counter

Controller singleton có field `int hits` và method `hits++` được gọi đồng thời. Spring tự đảm bảo kết quả đúng không?

**Đáp án:** Không. Cần `AtomicInteger`, synchronization hoặc tránh shared mutable state.

### Bài 13 — Scoped proxy

Một singleton service giữ cùng proxy reference tới request bean. Có phải mọi requests dùng một target object?

**Đáp án:** Không. Proxy reference có thể là singleton, nhưng request target thay đổi theo request scope.

### Bài 14 — Child/parent

Child không có local bean `repo` và lookup parent bean. Có thể trả cùng reference như parent không?

**Đáp án:** Có; child delegate lookup đến parent-owned singleton, không tạo local copy.

### Bài 15 — Child override name

Parent có `repo` singleton, child đăng ký một `repo` definition mới. Lookup từ child có bắt buộc trả parent object?

**Đáp án:** Không; local name có thể che parent. Kiểm tra thực tế parent-child lookup/overriding policies.

### Bài 16 — FactoryBean

`FactoryBean` definition là singleton nhưng `FactoryBean#isSingleton()` cho product false. Product lookup có chắc trả một instance duy nhất không?

**Đáp án:** Không. Factory object scope và product caching là hai semantics khác nhau.

### Bài 17 — Gọi `@Bean` method trực tiếp

Trong `@Configuration(proxyBeanMethods=false)`, method `service()` gọi `repository()` thủ công. Có đảm bảo nhận repository từ bean cache không?

**Đáp án:** Không. Lời gọi là Java bình thường; dùng factory method parameter injection.

### Bài 18 — Destroy callbacks

Hai contexts mỗi cái có `ManagedResource` riêng. Đóng context A có tự đóng resource thuộc B không?

**Đáp án:** Không theo normal ownership; chỉ resource do A quản lý được A cleanup. Nếu cả hai factories intentional return shared static object, cần thận trọng lifecycle double-close.

### Bài 19 — Test context caching

Hai test methods dùng cùng Spring TestContext configuration. Có chắc tạo hai `ApplicationContext` khác nhau?

**Đáp án:** Không. Spring TestContext có caching/reuse policy; cần xác nhận actual context identity.

### Bài 20 — Bean names và types

`@Bean("alpha") Client alpha()` và `@Bean("beta") Client beta()`, cả hai singleton. `getBean(Client.class)` có chắc chọn một không?

**Đáp án:** Không. Khi có nhiều candidates mà không có một ứng viên thắng, type lookup/injection có thể ambiguous; dùng qualifier/primary/named lookup.

## 19. Checklist thực hành

- Đã xác định rõ **bean name/definition** nào đang được nói tới chưa?
- Có đang nhầm Java class identity với Spring bean registration identity không?
- Có bao nhiêu `ApplicationContext`/`BeanFactory` đang chạy?
- Nếu context cha/con, bean được sở hữu bởi container nào?
- Có aliases hay nhiều definitions cùng class không?
- `@Bean` factory methods có tự trả một static shared object không?
- Scope là singleton, prototype hay web/custom scope? Có proxy không?
- Injection tới shared bean có dùng đúng `@Qualifier`/named reference khi có nhiều candidates?
- `@Configuration(proxyBeanMethods=false)` có inter-bean direct calls nguy hiểm không?
- Có code tự `new` một dependency đáng lẽ phải lấy từ container không?
- `@Lazy` có làm bean chưa được instantiate lúc refresh? Có eager consumer kích hoạt nó không?
- Có phân biệt `containsSingleton`, `isSingleton` và `containsBean` không?
- Đã kiểm tra reference identity bằng `==`/`assertSame` thay vì hash code/log text?
- Singleton có giữ mutable request/user data gây race/leak không?
- State mutable sau init có dùng lock, atomic hoặc concurrent structure phù hợp?
- Managed singleton resources có destroy callbacks và được đóng đúng context không?
- Prototype resource có cleanup owner riêng không?
- Tests có dùng context caching làm sai giả định isolation không?
- FactoryBean product và factory instance có bị nhầm khi gọi `&name` không?
- Nếu cần “một instance toàn JVM”, đó có thực sự là requirement hay chỉ là lạm dụng global state?

## 20. Kết luận

**Spring singleton là chính sách container scope, không phải một Java class Singleton pattern.** Một bean definition singleton trong một Spring container được container quản lý như một shared instance; nhiều lookups và consumers tới cùng bean nhận same managed reference. Hai beans cùng class nhưng khác definitions vẫn có thể giữ instances riêng. Hai containers độc lập thường cũng có caches/instances riêng. Alias là nhiều tên cho cùng bean, không phải thêm definition.

Hiểu chính xác ranh giới giúp bạn giải thích vì sao một ứng dụng có hai đối tượng `Repository` dù cả hai đều singleton, vì sao một object bị tạo lại khi integration test dựng context mới, và vì sao constructor của một bean singleton có thể chạy khi context refresh hoặc muộn hơn với `@Lazy`.

Cuối cùng, **singleton không đồng nghĩa thread-safe mutable state**, cũng không đồng nghĩa global resource ownership. Spring bảo đảm container-side safe publication, nhưng business code vẫn phải thiết kế concurrency và cleanup đúng. Hãy kiểm chứng bằng bean name, context identity, scopes, object reference `==` và lifecycle tests.

### Tài liệu Spring Framework chính thức

- [Spring Framework 6.2 — Bean Scopes / Singleton Scope](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html).
- [Spring Framework 6.2 — Using the `@Bean` Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html).
- [Spring Framework 6.2 — Basic Concepts: `@Bean` and `@Configuration`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html).
- [Spring Framework 6.2 — Using `@Configuration` and inter-bean method calls](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html).
- [Spring Framework 6.2 — Bean Factory API](https://docs.spring.io/spring-framework/reference/6.2/core/beans/beanfactory.html).
- [Spring Framework 6.2 — Bean Lifecycle and Thread Safety/Visibility](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html).
- [Spring Framework 6.2 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html).
- [Spring Framework 6.2 — Singleton beans with prototype dependencies](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html#beans-factory-scopes-prototype).

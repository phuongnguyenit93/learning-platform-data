# Bean lazy vẫn có thể được tạo bởi phụ thuộc không lazy trong Spring Core Container

## 1. Bài học giải quyết vấn đề gì?

Một bean được đánh dấu `@Lazy` không nhất thiết “sống sót” qua quá trình khởi động mà chưa có instance. Trong Spring Framework, **singleton không lazy (*eager singleton*) có thể kéo một bean lazy được khai báo là dependency vào quá trình khởi tạo sớm**. Đây là một quy tắc trọng tâm của chủ đề **Thời điểm tạo bean** trong Spring Core Container.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class ApplicationConfig {
    @Bean
    @Lazy
    PricingRules pricingRules() {
        return new PricingRules();
    }

    @Bean
    CheckoutService checkoutService(PricingRules pricingRules) {
        return new CheckoutService(pricingRules);
    }
}
```

Đây là **mẫu minh họa**, giả định `PricingRules` và `CheckoutService` có constructor hợp lệ. Có hai bean definitions:

- `pricingRules`: singleton lazy vì phương thức `@Bean` có `@Lazy`.
- `checkoutService`: singleton **không lazy** vì không có `@Lazy`.

Khi `ApplicationContext.refresh()` thực hiện pre-instantiation, Spring phải tạo `checkoutService`. Nhưng để gọi factory method `checkoutService(PricingRules pricingRules)`, container **phải cung cấp một object `PricingRules`**. Vì vậy `pricingRules` được tạo ngay trong startup, bất chấp chính bean definition mang dấu `@Lazy`.

Đó không phải bug của Spring. Nó phản ánh **hợp đồng dependency**: lazy initialization có tính ưu tiên thấp hơn nhu cầu tạo thành công một bean eager đang phụ thuộc vào nó.

### Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Giải thích đúng `singleton`, `eager`, `lazy` và `dependency-driven instantiation`.
2. Phân biệt **lazy trên bean definition** với **lazy trên injection point**.
3. Biết tại sao constructor/factory method parameter của eager bean khiến lazy dependency được tạo.
4. Nhìn được chuỗi A→B→C khi A eager kéo nhiều lazy beans.
5. Dự đoán thời điểm constructor, init callbacks và post-processors chạy.
6. Hiểu `@Lazy` trên `@Bean`, `@Component`, `@Configuration` và XML `lazy-init`.
7. Dùng `@Lazy` tại injection point để nhận một lazy-resolution proxy **khi phù hợp**.
8. Dùng `ObjectProvider<T>` để lookup tại thời điểm cần thật sự.
9. Tránh hiểu sai `@DependsOn`, `prototype` và `FactoryBean`.
10. Quan sát `BeanFactory.containsSingleton(...)` để kiểm tra trạng thái mà không vô tình tạo bean.
11. Chạy ví dụ Java 17/Spring Framework độc lập, có output deterministic, chứng minh đủ các nhánh.
12. Áp dụng cách thiết kế startup, latency, reliability và testing hợp lý trong dự án.

**Quy tắc cần thuộc:** Đánh dấu một bean `@Lazy` chỉ nói rằng Spring **không chủ động pre-instantiate nó như một singleton eager thông thường**. Nếu một bean eager **cần instance thật của bean đó**, Spring sẽ tạo nó để hoàn thành dependency.

## 2. Đọc đúng scope, lazy flag và cạnh phụ thuộc

Ba thuộc tính cần được xem **cùng lúc** khi dự đoán bean được tạo ở thời điểm nào:

| Trục | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Scope | Container dùng lại hay tạo instance mới? | `singleton` thường tái sử dụng cùng bean instance trong một container; `prototype` tạo theo từng lookup |
| Lazy flag của definition | Bean có bị chủ động pre-instantiate không? | `@Lazy` bỏ qua lượt chủ động tạo singleton non-lazy |
| Cạnh dependency | Bean nào buộc phải lấy instance của bean khác? | A eager nhận B lazy trực tiếp thì vẫn phải resolve B khi tạo A |

```text
A (singleton, eager)
    └── constructor cần B (singleton, @Lazy)
                              └── B được tạo khi A khởi tạo
```

Với `AnnotationConfigApplicationContext`, một singleton bình thường không lazy thường được tạo khi `refresh()` hoàn tất. Nhưng **B có lazy flag không có nghĩa mọi caller phải chờ tới sau startup**; nó vẫn được tạo nếu một eager consumer đòi target thật. Ngược lại, A nhận proxy bằng `@Lazy` tại injection point hoặc giữ `ObjectProvider<B>` mà chưa lookup thì riêng cạnh đó không cần B ngay.

Đừng nhầm `BeanDefinition` đã đăng ký với instance đã tạo. Muốn quan sát lazy singleton trước first use, đọc `containsSingleton("beanName")` thay cho `getBean()`, vì `getBean()` chính là thao tác có thể khiến B được tạo. Các khái niệm scope và pre-instantiation đã được giải thích ở bài mở đầu; bài này theo dấu **cạnh phụ thuộc gây ra việc tạo sớm**.

## 3. Spring pre-instantiate singleton khi nào?

Trong Spring Framework, `ApplicationContext.refresh()` bao gồm giai đoạn tạo các non-lazy singleton beans, thông qua BeanFactory và cơ chế `preInstantiateSingletons()` tương ứng.

Mô hình rút gọn:

```text
Đọc @Configuration / XML / component scan
                  |
                  v
       Đăng ký BeanDefinitions
                  |
                  v
  BeanFactoryPostProcessor, BeanPostProcessor
                  |
                  v
   preInstantiateSingletons() khi refresh
                  |
        Duyệt non-lazy singletons
                  |
           Tạo eager bean A
                  |
           Resolve dependencies
                  |
          B lazy được yêu cầu?
             /          \
           Có           Không
            |             |
       Tạo B sớm       B vẫn deferred
            |
       Hoàn tất A
                  |
                  v
          Refresh hoàn tất
```

Một số infrastructure beans có lifecycle đặc biệt và được tạo trước giai đoạn này; sơ đồ chỉ minh họa logic **regular beans**.

### “Bean lazy” có nghĩa bỏ qua lượt pre-instantiation, không phải từ chối mọi yêu cầu tạo

Spring không bảo trì một lệnh cấm “không được tạo B trước request đầu tiên” cho bean `@Lazy`. Container chỉ có **lazy-init flag** tác động đến đường đi khởi tạo chủ động. Những yêu cầu thật từ `getBean`, dependency injection, lookup của một bean khác và một số extension points vẫn có thể khiến bean ấy được tạo.

### Pre-instantiation không đồng nghĩa tạo tất cả bean trên classpath

Chỉ class có bean definition phù hợp mới được container quản lý. Prototype và các scope khác không được pre-instantiate hàng loạt như regular singleton non-lazy. Nhưng chúng **có thể bị tạo theo nhu cầu khi làm dependency của eager singleton**.

### Vì sao Spring làm như vậy?

Nếu Spring bỏ qua một dependency bắt buộc chỉ vì bean được đánh lazy, bean A sẽ thiếu parameter của constructor, tạo object không hợp lệ hoặc không thể được tạo. Spring ưu tiên đảm bảo một eager bean được hoàn tất đúng dependency contract.

## 4. Ví dụ A eager, B lazy: kết quả thật sự

Cho hai POJO:

```java
public final class ExchangeRateTable {
    public ExchangeRateTable() {
        System.out.println("ExchangeRateTable constructed");
    }
}

public final class InvoiceService {
    private final ExchangeRateTable rates;

    public InvoiceService(ExchangeRateTable rates) {
        this.rates = rates;
        System.out.println("InvoiceService constructed");
    }
}
```

Đây là ví dụ **minh họa**, hai public top-level classes cần đặt trong hai file .java riêng nếu copy, không phải chương trình độc lập hoàn chỉnh.

Cấu hình:

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    @Lazy
    ExchangeRateTable exchangeRateTable() {
        return new ExchangeRateTable();
    }

    @Bean
    InvoiceService invoiceService(ExchangeRateTable table) {
        return new InvoiceService(table);
    }
}
```

Khi context được tạo và refresh:

```java
try (var context = new AnnotationConfigApplicationContext(Config.class)) {
    System.out.println("Context ready");
}
```

Các dòng từ **hai bean constructors** có thể xuất hiện trước `Context ready`; thứ tự logic cần thiết là **ExchangeRateTable phải được tạo trước khi InvoiceService constructor nhận nó**. Các bean độc lập khác hoặc logging có thể xen vào, do vậy ví dụ runnable ở mục 10 sẽ không dựa vào thứ tự log toàn cục.

Điểm rút ra: Thêm `@Lazy` vào `exchangeRateTable` mà không đổi cách `invoiceService` phụ thuộc nó **không trì hoãn được chi phí construction của rate table**.

## 5. Chuỗi phụ thuộc: eager bean có thể kéo nhiều lazy beans

Không chỉ A→B. Một eager bean có thể kéo theo cả một graph:

```text
WebFacade            eager
    |
    v
CheckoutService      lazy
    |
    v
PriceCalculator      lazy
    |
    +---> TaxTable    lazy
    |
    +---> ExchangeRates lazy
```

Nếu `WebFacade` constructor cần `CheckoutService`, service constructor cần calculator, calculator cần tax table và rates, Spring phải phân giải cả chuỗi để xây facade. Không quan trọng ở file Java nào hoặc module cấu hình nào các `@Bean` nằm.

Từ đây có hai hệ quả:

- **Đánh dấu mọi bean ở tầng dưới là `@Lazy` không đảm bảo startup nhanh hơn** nếu một root eager bean vẫn cần toàn bộ graph.
- Để thực sự trì hoãn, phải thay đổi **cạnh dependency**, ví dụ một injection point là proxy lazy hoặc bean consumer giữ provider để lấy collaborator ở thời điểm sử dụng.

### Đồ thị này khác import graph

`@Import(ServiceConfig.class)` chỉ đưa cấu hình khác vào cùng context. Nó không đồng nghĩa BeanFactory phải tạo ngay mọi singleton lazy khai báo ở config được import. Ngược lại, chỉ cần một eager bean trong toàn context cần một lazy bean thuộc module đó, nó vẫn có thể bị khởi tạo.

### Đừng dựa vào thứ tự các @Bean methods

Khi `@Bean a()` xuất hiện trước `@Bean b()` trong source code, điều đó không phải cách xác định “a được tạo trước b” theo business semantics. Spring resolve dependencies và lifecycle. Để dự đoán lazy bean bị tạo hay chưa, hãy nhìn vào **dependency graph**, không phải thứ tự methods.

## 6. @Lazy trên bean definition và @Lazy tại injection point khác nhau

Đây là khác biệt quan trọng nhất sau quy tắc ở đầu bài.

### 6.1. @Lazy trên bean definition

```java
@Bean
@Lazy
RulesEngine rulesEngine() {
    return new RulesEngine();
}
```

Nghĩa là bean `rulesEngine` không bị chọn cho eager pre-instantiation mặc định. Nhưng nếu một eager service cần `RulesEngine` như constructor parameter bình thường, Spring vẫn tạo instance và inject.

### 6.2. @Lazy trên injection point

```java
@Bean
BillingService billingService(@Lazy RulesEngine rulesEngine) {
    return new BillingService(rulesEngine);
}
```

Spring hỗ trợ `@Lazy` trên injection point: với điều kiện dependency/proxying phù hợp, nó có thể truyền **lazy-resolution proxy** thay vì tạo target `RulesEngine` ngay. Khi code thực sự gọi method trên proxy, Spring mới resolve target bean.

Điều này khác với `@Lazy` trên chính bean factory method. Hai annotation điều chỉnh hai khía cạnh:

| Nơi đánh dấu | Điều chỉnh | Kết quả điển hình |
| --- | --- | --- |
| `@Lazy` trên `@Bean rulesEngine()` | Definition `rulesEngine` là lazy | Bỏ lượt chủ động pre-instantiate, nhưng vẫn tạo nếu eager consumer cần trực tiếp |
| `@Lazy` trên tham số `billingService(@Lazy RulesEngine r)` | Cách resolve dependency tại injection point | Consumer có thể nhận proxy, target được resolve khi proxy sử dụng |
| Cả hai | Definition lazy + injection point lazy | Target có cơ hội không bị tạo khi consumer eager được xây |
| Chỉ `@Lazy` trên consumer `@Bean billingService()` | Bản thân consumer được trì hoãn | Consumer không bị pre-instantiate trực tiếp nếu không có eager dependency khác |

### 6.3. Proxy là object thật, nhưng chưa chắc target đã có

Khi Spring inject proxy, constructor consumer **đã nhận được một Java reference**. Nhưng reference đó có thể là proxy làm nhiệm vụ **resolve target khi được gọi**, không phải target instance đã khởi tạo. Do đó cần phân biệt:

- **Proxy được tạo** để inject vào eager bean.
- **Target bean được tạo** khi proxy bị dereference/invoked.
- **Eager consumer bean được tạo** trong refresh.

Nếu code gọi method trên proxy ngay trong constructor hoặc `@PostConstruct` của consumer, Spring vẫn có thể phải khởi tạo target trong startup. Annotation không có “phép màu” khiến target luôn bị trì hoãn bất kể consumer làm gì.

### 6.4. Proxy không áp dụng tùy tiện với mọi type

Một interface là target dependency thuận lợi cho JDK dynamic proxy. Với concrete class, Spring có thể cần class-based proxy với điều kiện bytecode/type phù hợp. Những kiểu `final` hoặc method `final` và các trường hợp không proxy được có giới hạn đáng kể. Mẫu runnable sẽ dùng **interface `RemoteGateway`** cho deferred proxy.

### 6.5. @Lazy injection point không biến dependency bắt buộc thành optional

Một lazy-resolution proxy có thể được inject mà không cần target ngay. Nếu target bean không tồn tại hoặc resolution thất bại, lỗi có thể chỉ xuất hiện lúc proxy được sử dụng. Vì vậy **không dùng `@Lazy` để che dependency thiếu**. Nếu collaborator là tùy chọn thật, xem `ObjectProvider`/`Optional` theo hợp đồng rõ.

## 7. ObjectProvider<T>: trì hoãn lookup bằng code tường minh

Spring `ObjectProvider<T>` cho phép consumer giữ một handle, rồi yêu cầu target khi cần:

```java
import org.springframework.beans.factory.ObjectProvider;

final class InvoiceExporter {
    private final ObjectProvider<RemoteGateway> gateways;

    InvoiceExporter(ObjectProvider<RemoteGateway> gateways) {
        this.gateways = gateways;
    }

    String export(String payload) {
        return gateways.getObject().send(payload);
    }
}
```

Mã là đoạn minh họa, cần interface `RemoteGateway` và bean definition tương ứng. Với provider, constructor không buộc phải lấy target instance; provider làm việc khi `getObject()` được gọi.

### Ưu điểm so với proxy ẩn

- Code nói rõ **khi nào** lookup xảy ra.
- Có thể sử dụng `getIfAvailable()`/`getIfUnique()` khi dependency thực sự optional.
- Dễ điều khiển phạm vi mỗi lần lookup với prototype/scope.
- Không phải giả định consumer nhận “đúng target reference ngay tại construction”.

### Giới hạn

- Nếu gọi `getObject()` trong constructor hoặc init callback của eager bean, target vẫn được tạo sớm.
- Dùng provider ở mọi chỗ có thể che dependency graph, tạo service locator style khó test.
- `getIfAvailable()` không phải cách hợp lý để im lặng bỏ qua một collaborator bắt buộc.
- Nếu có nhiều beans cùng type, `getObject()` vẫn có thể bị ambiguity; cần qualifier hoặc cấu hình resolution tương ứng.
- Provider chỉ hoãn lookup; nếu object target tạo chậm, first-use latency vẫn tồn tại.

### Khi nào chọn @Lazy injection point, khi nào provider?

| Nhu cầu | Nên cân nhắc |
| --- | --- |
| Muốn interface collaborator “trông như một bean bình thường”, resolution khi gọi method | `@Lazy` injection point |
| Cần gọi lookup một cách tường minh ở một method cụ thể | `ObjectProvider<T>` |
| Cần prototype mới cho mỗi job | `ObjectProvider<T>` thường rõ hơn |
| Constructor cần target để thiết lập invariant ngay | Trực tiếp inject bean, chấp nhận tạo sớm |
| Dependency optional thật | Provider/Optional và rõ default behavior |
| Muốn né vòng constructor mà không đổi thiết kế | Không ưu tiên cả hai; refactor graph trước |

## 8. @Lazy trên @Component và @Configuration

### @Lazy trên component class

```java
@Component
@Lazy
public class OptionalAdapter {
    // ...
}
```

Nếu component scanning đăng ký bean này và không eager bean nào yêu cầu nó, Spring thường không tạo ngay lúc refresh. Nhưng một singleton eager constructor-inject `OptionalAdapter` sẽ làm adapter bị khởi tạo như trường hợp `@Bean`.

### @Lazy trên class @Configuration

```java
@Configuration
@Lazy
class FeatureConfig {
    @Bean
    FeatureCatalog featureCatalog() {
        return new FeatureCatalog();
    }
}
```

`@Lazy` đặt ở configuration class có thể đặt default lazy-init cho các `@Bean` definitions của configuration đó theo contract annotation. Tuy vậy:

- Bean khác vẫn có thể yêu cầu `featureCatalog` và khiến nó khởi tạo sớm.
- Infrastructure/processing của `@Configuration` có quy tắc riêng; đừng mặc định configuration instance và mọi helper đều tuyệt đối lazy.
- Nếu `@Bean` đã có `@Lazy(false)` tường minh, có thể override default laziness.
- Cần test trong context thực theo version/phạm vi ứng dụng.

### Đừng nhầm với @Primary hoặc @DependsOn

`@Primary` giải quyết ưu tiên ứng viên injection. `@DependsOn` thêm ràng buộc thứ tự bean creation. Không annotation nào trong hai loại đó tự tạo lazy-resolution proxy cho injection point.

## 9. XML: lazy-init="true" cũng chịu cùng quy tắc

Spring XML:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="priceRules"
          class="example.PriceRules"
          lazy-init="true"/>

    <bean id="checkoutService"
          class="example.CheckoutService">
        <constructor-arg ref="priceRules"/>
    </bean>
</beans>
```

Nếu class `CheckoutService` có constructor cần `PriceRules`, eager singleton `checkoutService` khiến `priceRules` được tạo lúc startup dù XML của `priceRules` có `lazy-init="true"`.

### XML default-lazy-init

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       default-lazy-init="true">
    <bean id="a" class="example.A"/>
    <bean id="b" class="example.B"/>
</beans>
```

Đây là snippet cú pháp rút gọn, cần schema đầy đủ trong file thật. `default-lazy-init="true"` có thể thay default cho definitions trong phạm vi tương ứng; vẫn có thể khai báo `lazy-init="false"` tường minh cho một bean. Nếu bean eager khác yêu cầu A, A vẫn được tạo.

### @ImportResource không thay ngữ nghĩa lazy

Dù XML được đọc từ `ClassPathXmlApplicationContext` hay được nhập qua Java:

```java
@Configuration
@ImportResource("classpath:legacy.xml")
class RootConfig {
}
```

bean definitions sau khi đăng ký vẫn dùng chung BeanFactory, scope và dependency rules. XML resource nằm trong module riêng không giúp lazy bean tránh bị eager consumer trong Java `@Bean` inject.

## 10. Dự án runnable Java 17: ba cách quan sát khác nhau

Ví dụ đầy đủ dưới đây chứng minh trong cùng một `ApplicationContext`:

- **`requiredIndex` được đánh `@Lazy` nhưng bị `eagerCatalogService` kéo vào startup.**
- **`idleReport` lazy và không được eager bean nào yêu cầu, nên vẫn chưa tạo sau refresh.**
- **`remoteGateway` lazy nhưng `deferredConsumer` eager nhận `@Lazy RemoteGateway` tại injection point**, nên consumer có thể được tạo mà target gateway chưa được tạo; khi gọi method qua proxy mới khởi tạo.
- `containsSingleton(name)` quan sát singleton cache, không làm bean lazy bị tạo.
- Lazy singleton sau khi tạo vẫn giữ identity.
- Output xác định, không phụ thuộc thứ tự các constructors của các singleton độc lập.

### 10.1. Cấu trúc dự án

```text
lazy-dependency-demo/
├── pom.xml
└── src/main/java/demo/
    └── LazyDependencyDemo.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>lazy-dependency-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.3. File LazyDependencyDemo.java hoàn chỉnh

```java
package demo;

import java.util.HashSet;
import java.util.Set;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;

public class LazyDependencyDemo {

    public static final class Tracker {
        private final Set<String> created = new HashSet<>();

        public void mark(String name) {
            created.add(name);
        }

        public boolean has(String name) {
            return created.contains(name);
        }
    }

    public static final class RequiredIndex {
        public RequiredIndex(Tracker tracker) {
            tracker.mark("requiredIndex");
        }

        public String lookup(String key) {
            return "INDEX:" + key;
        }
    }

    public static final class EagerCatalogService {
        private final RequiredIndex index;

        public EagerCatalogService(RequiredIndex index, Tracker tracker) {
            this.index = index;
            tracker.mark("eagerCatalogService");
        }

        public String catalog(String key) {
            return index.lookup(key);
        }
    }

    public static final class IdleReport {
        public IdleReport(Tracker tracker) {
            tracker.mark("idleReport");
        }
    }

    public interface RemoteGateway {
        String send(String request);
    }

    public static final class RemoteGatewayImpl implements RemoteGateway {
        public RemoteGatewayImpl(Tracker tracker) {
            tracker.mark("remoteGateway");
        }

        @Override
        public String send(String request) {
            return "REMOTE:" + request;
        }
    }

    public static final class DeferredConsumer {
        private final RemoteGateway gateway;

        public DeferredConsumer(RemoteGateway gateway, Tracker tracker) {
            this.gateway = gateway;
            tracker.mark("deferredConsumer");
        }

        public String useGateway(String request) {
            return gateway.send(request);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public Tracker tracker() {
            return new Tracker();
        }

        @Bean
        @Lazy
        public RequiredIndex requiredIndex(Tracker tracker) {
            return new RequiredIndex(tracker);
        }

        @Bean
        public EagerCatalogService eagerCatalogService(
                RequiredIndex requiredIndex, Tracker tracker) {
            return new EagerCatalogService(requiredIndex, tracker);
        }

        @Bean
        @Lazy
        public IdleReport idleReport(Tracker tracker) {
            return new IdleReport(tracker);
        }

        @Bean
        @Lazy
        public RemoteGateway remoteGateway(Tracker tracker) {
            return new RemoteGatewayImpl(tracker);
        }

        @Bean
        public DeferredConsumer deferredConsumer(
                @Lazy RemoteGateway remoteGateway, Tracker tracker) {
            return new DeferredConsumer(remoteGateway, tracker);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            Tracker tracker = context.getBean(Tracker.class);

            System.out.println("required.createdAtRefresh=" +
                    tracker.has("requiredIndex"));
            System.out.println("eager.createdAtRefresh=" +
                    tracker.has("eagerCatalogService"));
            System.out.println("idle.createdAtRefresh=" +
                    tracker.has("idleReport"));
            System.out.println("gateway.createdAtRefresh=" +
                    tracker.has("remoteGateway"));
            System.out.println("consumer.createdAtRefresh=" +
                    tracker.has("deferredConsumer"));

            System.out.println("gateway.hasSingletonBefore=" +
                    context.getBeanFactory().containsSingleton("remoteGateway"));

            EagerCatalogService eager =
                    context.getBean(EagerCatalogService.class);
            System.out.println("catalog=" + eager.catalog("B-17"));

            DeferredConsumer consumer =
                    context.getBean(DeferredConsumer.class);
            System.out.println("deferredCall=" +
                    consumer.useGateway("ping"));

            System.out.println("gateway.createdAfterCall=" +
                    tracker.has("remoteGateway"));

            IdleReport first = context.getBean(IdleReport.class);
            IdleReport second = context.getBean(IdleReport.class);

            System.out.println("idle.createdAfterLookup=" +
                    tracker.has("idleReport"));
            System.out.println("idle.sameSingleton=" +
                    (first == second));
        }
    }
}
```

### 10.4. Lệnh chạy

Cần JDK 17+, Maven và tải được dependency Spring từ repository phù hợp nếu máy chưa cache:

```bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.LazyDependencyDemo
```

### 10.5. Output do chương trình in ra

Không tính các log Maven/Spring có thể xuất hiện ngoài các dòng do `System.out.println` tạo:

```text
required.createdAtRefresh=true
eager.createdAtRefresh=true
idle.createdAtRefresh=false
gateway.createdAtRefresh=false
consumer.createdAtRefresh=true
gateway.hasSingletonBefore=false
catalog=INDEX:B-17
deferredCall=REMOTE:ping
gateway.createdAfterCall=true
idle.createdAfterLookup=true
idle.sameSingleton=true
```

### 10.6. Phân tích chính xác từng nhóm dòng

**`required.createdAtRefresh=true`:** Dù `requiredIndex` mang `@Lazy`, Spring phải tạo nó khi pre-instantiate `eagerCatalogService`. Đây là trọng tâm bài học.

**`eager.createdAtRefresh=true`:** `eagerCatalogService` là singleton không lazy nên được tạo trong refresh. Constructor đánh dấu `Tracker`.

**`idle.createdAtRefresh=false`:** `idleReport` có `@Lazy` và không có eager consumer yêu cầu. Vì vậy constructor chưa chạy trước khi code `main` lấy nó.

**`gateway.createdAtRefresh=false`:** `remoteGateway` là singleton lazy. `deferredConsumer` eager không đòi target ngay vì tham số factory method là `@Lazy RemoteGateway`; Spring có thể inject lazy-resolution proxy. Constructor của `RemoteGatewayImpl` chưa chạy.

**`consumer.createdAtRefresh=true`:** `deferredConsumer` là eager singleton và có thể được tạo với proxy reference, trong khi remote gateway target vẫn deferred.

**`gateway.hasSingletonBefore=false`:** `containsSingleton("remoteGateway")` kiểm tra singleton cache, không gây tạo target. Proxy được inject vào `deferredConsumer` không làm singleton target `remoteGateway` xuất hiện trong registry.

**`catalog=INDEX:B-17`:** Eager service đã có instance `RequiredIndex` thật, dùng nó để trả chuỗi. Không phải gọi `getBean(RequiredIndex.class)` tại đây.

**`deferredCall=REMOTE:ping`:** Khi `DeferredConsumer.useGateway("ping")` gọi method `send` trên proxy, Spring resolve target `remoteGateway` và tạo `RemoteGatewayImpl` nếu target chưa tồn tại. Sau đó method trả chuỗi.

**`gateway.createdAfterCall=true`:** Constructor implementation đã ghi marker trong lần sử dụng đầu tiên của proxy.

**`idle.createdAfterLookup=true`:** Hai lời gọi `context.getBean(IdleReport.class)` đầu tiên và thứ hai khiến lazy bean được tạo và trả về từ singleton cache.

**`idle.sameSingleton=true`:** Lazy không làm đổi scope. Hai lượt tra cứu trong cùng context trả về cùng `IdleReport` instance.

### 10.7. Vì sao ví dụ tránh flakiness?

- `Tracker` được tạo trong cùng context; markers chỉ được đọc sau refresh.
- Không in constructor logs để suy luận thứ tự giữa các eager beans không có dependency.
- `Set` được dùng để hỏi membership, không duyệt và không phụ thuộc iteration order.
- Không có network calls, DB, clocks hoặc threads nền.
- `RemoteGateway` là **interface**, nên lazy-resolution proxy có thể hoạt động mà không gặp hạn chế của final concrete class.
- `@Configuration(proxyBeanMethods=false)` hợp lệ vì tất cả dependencies đi qua tham số `@Bean`, không direct-call các `@Bean` methods.
- Các bean là `public static` nested classes; không cần instance outer `LazyDependencyDemo`.
- Không đọc `remoteGateway` qua `getBean` trước khi kiểm tra trạng thái cache.
- Chỉ kiểm tra singleton identity sau khi bean lazy đã thực sự được tra cứu.
- `try-with-resources` đóng context và kích hoạt lifecycle cleanup phù hợp.

## 11. Thay đổi nhỏ để thấy bản chất

### Thử 1 — Xóa @Lazy ở requiredIndex

```java
@Bean
RequiredIndex requiredIndex(Tracker tracker) {
    return new RequiredIndex(tracker);
}
```

Output `required.createdAtRefresh` vẫn là `true`, nhưng **lý do** khác: bản thân bean giờ eager; không cần consumer để kéo nó lên. Bài học: chỉ nhìn output “created=true” không đủ để biết nguyên nhân; phải đọc bean definition và graph.

### Thử 2 — Đặt @Lazy trên eagerCatalogService

```java
@Bean
@Lazy
EagerCatalogService eagerCatalogService(
        RequiredIndex index, Tracker tracker) {
    return new EagerCatalogService(index, tracker);
}
```

Nếu không có eager bean khác cần service và không có lookup nào trước bước kiểm tra, cả service và required index có thể vẫn chưa tạo lúc refresh. Nhưng trong `main` của dự án này, gọi `getBean(EagerCatalogService.class)` sau đó sẽ tạo cả chuỗi.

### Thử 3 — Bỏ @Lazy tại injection point của deferredConsumer

Từ:

```java
DeferredConsumer deferredConsumer(
        @Lazy RemoteGateway gateway, Tracker tracker)
```

thành:

```java
DeferredConsumer deferredConsumer(
        RemoteGateway gateway, Tracker tracker)
```

Lúc đó eager `deferredConsumer` cần target thật, nên `remoteGateway` dù có `@Lazy` trên definition vẫn bị tạo trong refresh. `gateway.createdAtRefresh` sẽ là `true`. Đây là phép thử cho khác biệt **definition lazy** và **injection point lazy**.

### Thử 4 — Gọi proxy trong constructor

Nếu `DeferredConsumer` constructor thực thi `gateway.send("health")` ngay, nó sẽ dereference proxy khi eager consumer được tạo. `remoteGateway` lại bị tạo sớm. Proxy hoãn lúc tạo target **cho tới khi sử dụng**, không bảo đảm hoãn qua mốc startup nếu chính constructor dùng target.

### Thử 5 — Đổi IdleReport sang prototype

```java
@Bean
@Scope("prototype")
IdleReport idleReport(Tracker tracker) {
    return new IdleReport(tracker);
}
```

Mỗi lần `getBean(IdleReport.class)` có thể cho instance mới, nên `idle.sameSingleton` đổi thành `false`. Đó là thay đổi **scope**, không phải do lazy annotation. Nhớ import `org.springframework.context.annotation.Scope` nếu thử.

### Thử 6 — Làm gateway có dependency từ eager bean khác

Nếu thêm một eager bean mới constructor-inject `RemoteGateway` **không có lazy proxy**, target vẫn bị tạo trong refresh, bất kể `deferredConsumer` có injection point `@Lazy`. Lazy strategy ở **một consumer** không thể kiểm soát những consumers khác.

## 12. @Lazy trên consumer và lazy trên dependency: ma trận trường hợp

Giả sử B là collaborator, A là consumer. Không có bên thứ ba yêu cầu B.

| A consumer | B definition | Injection A→B | B thường được tạo lúc refresh? |
| --- | --- | --- | --- |
| Eager singleton | Eager singleton | Trực tiếp | Có |
| Eager singleton | Lazy singleton | Trực tiếp | **Có**, vì A cần B |
| Eager singleton | Lazy singleton | `@Lazy` injection point phù hợp | Thường **không**, target hoãn tới khi proxy sử dụng |
| Eager singleton | Lazy singleton | `ObjectProvider<B>` | Thường **không**, tới khi `getObject()` |
| Lazy singleton | Lazy singleton | Trực tiếp | Không nếu A/B chưa bị bean khác yêu cầu |
| Lazy singleton | Eager singleton | Trực tiếp | Có, B tự eager |
| Prototype A được eager singleton khác yêu cầu | Lazy singleton | Trực tiếp | Có thể có, vì prototype A bị tạo để inject rồi cần B |
| Eager A có `@DependsOn("b")` | Lazy B | Không có constructor reference | B có thể vẫn được tạo trước A do explicit ordering |

Không coi bảng là hợp đồng tuyệt đối cho mọi plugin/`FactoryBean`/custom scope/proxy configuration; nó mô tả các trường hợp regular bean thông dụng. Những custom post-processors hoặc explicit lookups trong startup có thể thay đổi thời điểm.

## 13. @DependsOn có thể buộc tạo lazy bean sớm

`@DependsOn` có mục đích **ràng buộc thứ tự khởi tạo**. Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    @Lazy
    CacheWarmup cacheWarmup() {
        return new CacheWarmup();
    }

    @Bean
    @DependsOn("cacheWarmup")
    BusinessService businessService() {
        return new BusinessService();
    }
}
```

Đây là ví dụ minh họa cần các classes `CacheWarmup` và `BusinessService`. Nếu `businessService` là eager singleton, BeanFactory cần đảm bảo `cacheWarmup` được khởi tạo trước theo metadata `dependsOn`. Một bean lazy có thể được tạo sớm dù không được truyền làm constructor parameter.

**Điểm quan trọng:** Đừng coi `@DependsOn` là một cách giảm eager creation. Ngược lại, nó có thể **thêm một cạnh bắt buộc khởi tạo**.

### @DependsOn không thay thế dependency injection

Nếu service thực sự cần đối tượng rules trong constructor, khai báo `BusinessService(Rules rules)` hoặc `@Bean businessService(Rules rules)`. `@DependsOn("rules")` chỉ làm rules được tạo trước, **không truyền reference** vào constructor.

### Không dùng @DependsOn làm workflow scheduler

Nếu `CacheWarmup` constructor gọi hàng loạt external APIs, tạo nó qua `@DependsOn` có thể kéo business side effect vào startup. Đó là vấn đề lifecycle/job orchestration chứ không phải riêng lazy flag.

## 14. Một singleton eager có thể kéo prototype bean lên sớm

`prototype` và `lazy` khác nhau. Giả sử:

```java
@Bean
@Scope("prototype")
WorkBuffer workBuffer() {
    return new WorkBuffer();
}

@Bean
BatchScheduler batchScheduler(WorkBuffer buffer) {
    return new BatchScheduler(buffer);
}
```

Nếu `batchScheduler` eager, Spring phải tạo một `WorkBuffer` prototype **để inject vào scheduler** trong startup. Không phải Spring pre-instantiated mọi prototype: chỉ tạo dependency được yêu cầu.

### Prototype không tự làm consumer nhận buffer mới mỗi lần

Một singleton scheduler constructor nhận buffer một lần và thường giữ cùng reference. Nếu mỗi job cần buffer mới, inject `ObjectProvider<WorkBuffer>` và gọi `getObject()` cho từng job, hoặc dùng factory có hợp đồng rõ.

### Lazy flag trên prototype

`@Lazy` chủ yếu hữu ích để điều khiển pre-instantiation của singleton definitions; prototype vốn thường chỉ tạo khi được yêu cầu. Đánh `@Lazy` lên prototype không biến nó thành singleton hay đổi prototype semantics. Một prototype đang là dependency của eager singleton vẫn có thể được tạo.

## 15. @Autowired field và setter injection có khác không?

Không phải cứ không dùng constructor là lazy bean thoát khỏi startup.

Ví dụ field injection:

```java
@Component
public class OrderFacade {

    @Autowired
    private TaxRules taxRules;
}
```

Nếu `OrderFacade` là eager singleton, Spring phải xử lý `@Autowired TaxRules` trong giai đoạn population. Nếu `TaxRules` bean là lazy, container vẫn có thể tạo nó để inject vào eager facade.

Setter injection:

```java
@Component
public class OrderFacade {
    private TaxRules taxRules;

    @Autowired
    void setTaxRules(TaxRules taxRules) {
        this.taxRules = taxRules;
    }
}
```

Tương tự: Spring cần có collaborator object phù hợp để gọi setter. Các class trên là **hai phiên bản minh họa**, không đặt cùng tên trong một file.

### Khi @Lazy nằm trên injection point

```java
@Autowired
@Lazy
private TaxRules taxRules;
```

hoặc:

```java
OrderFacade(@Lazy TaxRules rules) {
    this.taxRules = rules;
}
```

Spring có thể truyền lazy-resolution proxy cho injection point khi type hỗ trợ. Tuy nhiên, **constructor injection** vẫn thường dễ test, thể hiện dependency bắt buộc rõ hơn field injection. Dùng provider hoặc injection point lazy có chủ đích thay vì chuyển dependency từ constructor sang field chỉ để che graph.

## 16. Một dependency lazy có thể bị gọi sớm qua BeanPostProcessor

Spring Framework có nhiều extension points trong quá trình bootstrap:

- `BeanDefinitionRegistryPostProcessor` / `BeanFactoryPostProcessor`.
- `BeanPostProcessor`.
- `FactoryBean` và type lookup.
- Init callbacks như `@PostConstruct`.
- `SmartInitializingSingleton`.
- ApplicationContext event listeners/lifecycle processors.

Một post-processor hoặc startup callback có thể gọi `getBean("lazyBean")` hoặc một method trên proxy/provider, khiến lazy target được tạo **trước khi request bên ngoài xuất hiện**.

### Không gọi getBean bừa trong BeanFactoryPostProcessor

Các BeanFactory post-processors chạy rất sớm, trước khi toàn bộ regular BeanPostProcessors được đăng ký. Ép business bean tạo từ giai đoạn này có thể khiến bean không nhận AOP/proxy/lifecycle behavior như mong đợi.

Một startup issue có thể do việc đọc metadata bị nhầm với việc tạo instance. Nếu chỉ cần kiểm tra bean definition, dùng API definition registry; đừng gọi `getBean()`.

### SmartInitializingSingleton không bảo đảm mọi lazy bean còn vắng

Một callback `afterSingletonsInstantiated()` chạy sau lượt pre-instantiation các regular non-lazy singletons. Nhưng các lazy dependencies của eager beans đã có thể được tạo trong lượt đó. Vì vậy callback không thể khẳng định “tất cả lazy beans vẫn chưa tạo”.

Ngược lại, một `SmartInitializingSingleton` bản thân lazy và chỉ được tạo về sau thường **không** được gọi callback cuối pre-instantiation tại thời điểm tạo muộn. Không dùng nó như per-bean constructor event.

### FactoryBean và type introspection

Với `FactoryBean<T>`, container phân biệt factory object và product. Một số type-lookups cần initialize factory để xác định type, tùy flags/contract như `allowEagerInit`. Do vậy “chỉ query danh sách bean names theo type” không phải luôn 100% side-effect-free trong mọi cấu hình.

Đối với việc quan sát một singleton lazy thông thường mà không muốn tạo nó, `containsSingleton("beanName")` phù hợp hơn `getBean()`.

## 17. Tác động đến hiệu năng: startup nhanh hay request đầu tiên nhanh?

Giả sử bean `RemotePricingClient` mở kết nối, xây thread pool hoặc tải metadata khi constructor chạy. Khi bị eager service yêu cầu, chi phí vẫn nằm ở **startup** dù bean có `@Lazy`.

Nếu bạn đổi injection point sang proxy hoặc provider, chi phí chuyển sang **first use**, có thể rơi đúng vào request đầu tiên của người dùng.

| Chiến lược | Startup | First use | Khả năng phát hiện lỗi |
| --- | --- | --- | --- |
| Eager bean với dependency trực tiếp | Tạo các dependencies ngay | Có thể nhanh hơn sau startup | Fail-fast |
| Lazy definition nhưng bị eager consumer kéo lên | **Vẫn tốn chi phí lúc startup** | Thường không phải tạo lại singleton | Fail-fast cho dependency đó |
| Lazy injection-point proxy | Consumer khởi tạo mà target có thể chưa tạo | Target resolution + creation cost tại lần gọi đầu | Lỗi có thể tới muộn |
| ObjectProvider lookup tại runtime | Provider thường nhẹ | `getObject()` chịu latency và lỗi | Lỗi có thể tới muộn |
| Refactor tác vụ nặng ra khỏi constructor | Construction nhẹ hơn | Tùy lifecycle/use case design | Có thể chủ động startup validation |

**Không có lựa chọn tối ưu tuyệt đối.** Với một dependency bắt buộc cho endpoint cốt lõi, fail-fast và sẵn sàng ngay có thể quan trọng hơn tối ưu thời gian tạo context. Với feature tùy chọn ít dùng, lazy giúp giảm startup cost hợp lý.

### Nếu cần readiness chính xác

Một Java object được tạo thành công không chứng minh tất cả dịch vụ mạng/DB bên ngoài đang healthy. Hãy có timeout, health checks, readiness gating và kết nối theo hợp đồng phù hợp. Đừng lẫn singleton creation với distributed system readiness.

### Tránh đưa công việc kinh doanh vào bean constructor

Một bean eager chạy `sendWelcomeEmailToAllUsers()` trong constructor có thể gây side effects trên mỗi instance/context/restart. Nếu sau đó bạn thêm lazy proxy, tác vụ chỉ chuyển sang request đầu tiên, không thành giải pháp an toàn.

Tách business workflow sang service method/startup coordinator với policy idempotency, retry và transaction phù hợp.

## 18. Quan sát thời điểm tạo mà không làm thay đổi thí nghiệm

### containsBeanDefinition

```java
boolean definitionExists =
        context.getBeanFactory().containsBeanDefinition("remoteGateway");
```

Có bean definition không đồng nghĩa singleton instance đã được tạo.

### containsSingleton

```java
boolean instantiated =
        context.getBeanFactory().containsSingleton("remoteGateway");
```

Kiểm tra singleton cache không yêu cầu BeanFactory instantiate bean mới. Trong ví dụ chính, trước khi gọi deferred proxy, kết quả là `false`; sau khi gọi `send`, là `true` với singleton target.

### getBean

```java
RemoteGateway gateway =
        context.getBean(RemoteGateway.class);
```

Đây là **hành động yêu cầu instance**. Nếu target lazy chưa tạo, chính lời gọi này có thể khiến nó tạo ra. Dùng `getBean` rồi mới kiểm tra `containsSingleton` sẽ không chứng minh target “đã tạo sẵn trước lookup”.

### Logs và constructor counters

Logging trong constructor là phương tiện dễ nhìn nhưng có thể làm thứ tự output phụ thuộc nội bộ container. Nếu muốn assert chính xác, dùng marker/atomic counter, kiểm tra ở các mốc **trước refresh**, **sau refresh**, **sau first use** và **sau close**.

Mẫu chương trình dùng `Tracker` thay vì suy ra thứ tự từ logs. Với môi trường đa luồng thực tế, lựa chọn `ConcurrentHashMap.newKeySet()`/`AtomicInteger` tùy yêu cầu; `HashSet` của demo đủ vì không có worker threads truy cập đồng thời.

### Có thể có Spring proxy trong singleton cache không?

Có. BeanFactory có thể expose proxy thay vì raw target trong những tính năng như AOP; “bean reference” mà consumer nhận có thể là proxy. Tuy nhiên, lazy injection-point proxy là cơ chế đặc thù: nó không nhất thiết được lưu dưới **tên target bean** trong singleton cache trước khi target được yêu cầu. Tránh kết luận dựa trên Java class của reference một mình.

## 19. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Đánh `@Lazy` nhưng constructor vẫn chạy lúc startup | Bean là dependency của eager singleton | Xác định consumer eager và đường injection |
| `@Lazy` trên một bean mà initMethod vẫn chạy | Bean bị dependency khác tạo sớm | Xem graph và callback |
| Eager bean bị tạo sớm ngoài ý định | Không có `@Lazy` ở consumer | Chọn consumer laziness nếu tính năng thật sự optional |
| `@Lazy` tại injection point nhưng target vẫn tạo lúc refresh | Constructor/init của consumer dùng proxy; consumer khác yêu cầu target trực tiếp | Kiểm tra tất cả đường gọi và lookups |
| @Lazy proxy không hoạt động với concrete type | Proxying limitation như final class/method | Ưu tiên interface hoặc provider; review proxy restrictions |
| `containsBean` true làm tưởng instance đã tạo | API kiểm tra resolvability, không phải cache | Dùng `containsSingleton` |
| `getBean` làm kết quả quan sát thay đổi | Lookup kích hoạt bean creation | Kiểm tra markers/cache trước lookup |
| Bean bị tạo ở nhiều contexts | Singleton scope per-container | Kiểm tra test/application contexts |
| Prototype được tạo lúc startup | Eager singleton cần một prototype dependency | Dùng provider/factory nếu cần instance từng lượt |
| Thay tất cả bằng `@Lazy` nhưng startup không nhanh | Dependency graph vẫn kéo các bean vào startup | Phân tích graph và điểm tạo chi phí cao |
| Request đầu tiên chậm sau refactor lazy | Deferred target construction/resolution | Đánh giá trade-off và warmup/readiness policy |
| Lazy target thiếu bean, lỗi xuất hiện ở request đầu | Proxy/provider hoãn resolution | Test feature path; fail-fast nếu dependency bắt buộc |
| NoUniqueBeanDefinitionException khi provider lookup | Nhiều target beans cùng type | Qualifier/Primary/naming policy |
| BeanCurrentlyInCreationException | Circular dependency/early resolution | Sửa graph, không dùng lazy để che vòng |
| @DependsOn làm lazy bean tạo sớm | Ordering metadata buộc pre-create target | Kiểm tra dependsOn declarations |
| BeanPostProcessor cảnh báo bean không eligible | Có bean được tạo quá sớm ở infrastructure phase | Tránh early getBean trong post-processors |
| FactoryBean product tạo sớm ngoài dự đoán | Eager product/FactoryBean hoặc dependency/type lookup | Xem isSingleton/isEagerInit/allowEagerInit |
| Startup coordinator dùng SmartInitializingSingleton nhưng vẫn gặp remote target lỗi | Callback gọi proxy/provider; target bắt đầu tạo | Quản lý startup validation riêng, timeout rõ |
| Test pass local nhưng fail production | Khác profile, beans, component scanning, auto-config | Test đúng root/profile/conditions |

### Quy trình debug tuần tự

1. Lấy **bean name** của target và các constructors/`@Bean` methods tạo nó.
2. Kiểm tra scope: `singleton` hay `prototype`?
3. Kiểm tra lazy flag của target definition: `@Lazy`, XML `lazy-init` hoặc global config.
4. Tìm mọi **eager singleton consumers** yêu cầu target qua constructor, setter, field, `@Bean` parameter hoặc `@DependsOn`.
5. Xác định target được inject trực tiếp, qua `@Lazy` proxy hay `ObjectProvider`.
6. Kiểm tra constructors/init callbacks có gọi proxy/provider sớm không.
7. Kiểm tra lookups từ post-processors, application events, listeners và `FactoryBean`.
8. Quan sát bằng `containsSingleton`/markers **trước** khi dùng `getBean`.
9. Xem nguyên nhân gốc exception; đừng tự kết luận có vòng khi chỉ thấy `UnsatisfiedDependencyException`.
10. Refactor dependency/use-case boundary hoặc điều chỉnh eager/lazy có chủ đích; test cả startup và first-use.

## 20. Test khi nào bean lazy được tạo

Có thể thêm assertions sau vào `main` ở ví dụ mục 10 khi `tracker` và `context` còn tồn tại, **trước khi gọi deferred consumer hoặc lookup idle report**:

```java
if (!tracker.has("requiredIndex")) {
    throw new AssertionError("Eager dependency should create requiredIndex");
}
if (tracker.has("idleReport")) {
    throw new AssertionError("Idle lazy bean created too soon");
}
if (tracker.has("remoteGateway")) {
    throw new AssertionError("Lazy proxy target resolved too soon");
}
if (context.getBeanFactory().containsSingleton("remoteGateway")) {
    throw new AssertionError("Gateway target already in singleton cache");
}
```

Sau khi gọi `consumer.useGateway("ping")`:

```java
if (!tracker.has("remoteGateway")) {
    throw new AssertionError("Gateway target not created on first use");
}
if (!context.getBeanFactory().containsSingleton("remoteGateway")) {
    throw new AssertionError("Gateway target missing from cache");
}
```

Đây là **hai đoạn bổ sung**, không phải chương trình Java độc lập. Chúng mô tả ranh giới thời điểm rất rõ: target không có trước first use, có sau khi sử dụng proxy. Tránh thêm lệnh `getBean(RemoteGateway.class)` vào giữa để không phá giả định của bài test.

### Test với nhiều profiles

Khi profile dev/prod đăng ký consumers khác nhau, lazy target có thể bị kéo lên chỉ trong một profile:

```text
dev:
  AdminTool (lazy) --> ReportEngine (lazy)
  => ReportEngine có thể còn deferred.

prod:
  StartupReportService (eager) --> ReportEngine (lazy)
  => ReportEngine bị tạo khi startup.
```

Test từ root configuration của mỗi profile, không chỉ test bean definition riêng lẻ. Kiểm tra cả giá trị của `@Conditional`/`@Profile` trong đúng môi trường.

### Unit test business logic không cần mở Spring

Nếu `EagerCatalogService` chỉ dùng `RequiredIndex` POJO, unit test có thể tự tạo collaborators và gọi method. Phần “Spring tạo instance khi nào” cần **integration test bằng context thật**, vì annotation/proxy/lifecycle thuộc container.

### Tránh assertions dựa vào số bean names

`getBeanNamesForType(RemoteGateway.class)` có thể cho biết một bean **được khai báo theo type** mà target chưa được tạo. Danh sách names không chứng minh bean instance đã tồn tại. Nếu test thời điểm khởi tạo, đọc cache/constructor markers.

## 21. Circular dependency: lazy có giải quyết được không?

Cho:

```java
class ServiceA {
    ServiceA(ServiceB b) {
    }
}
class ServiceB {
    ServiceB(ServiceA a) {
    }
}
```

Với constructor cycle A→B→A, BeanFactory thường không thể tạo đủ hai instances. `@Lazy` trên **bean definition** của B không sửa vòng nếu A eager vẫn phải tạo B. Bạn có thể dùng `@Lazy` ở injection point để trì hoãn một cạnh qua proxy trong một số trường hợp, nhưng:

- Vòng logic vẫn tồn tại.
- Proxy có thể bị dereference trong constructor/init và tái tạo vòng.
- Type/proxy limitations có thể khiến solution không hoạt động.
- Lifecycle/invariants khó reasoning hơn.

Ưu tiên trích interface chung hoặc đưa orchestration lên một coordinator:

```text
Trước:
ServiceA <----> ServiceB

Sau:
Orchestrator ---> ServiceA
             \-> ServiceB
```

`spring.main.allow-circular-references` là option của Spring Boot, không phải cách chuẩn sửa vòng của Spring Framework thuần; kể cả khi hỗ trợ early references cho một số setter cycles, constructor cycles thường vẫn bất khả giải.

## 22. FactoryBean, AOP và các trường hợp cần cẩn trọng

### FactoryBean không giống @Bean factory method

`FactoryBean<T>` có hai khái niệm khác nhau: factory object và product. BeanFactory có thể tạo/check factory object sớm để biết metadata/type, trong khi product có eager/lazy semantics phụ thuộc `FactoryBean`/`SmartFactoryBean` và consumers.

Đừng kết luận “nếu BeanDefinition là lazy thì không object liên quan nào được tạo khi startup” trong mọi combination của `FactoryBean`, type introspection và dependency resolution.

### AOP proxy và @Lazy injection-point proxy không đồng nhất

Một bean có `@Transactional`/AOP có thể được Spring expose thông qua proxy. Một `@Lazy` injection point cũng có thể dùng proxy, nhưng vì **lý do khác**: defer target resolution. Một bean có thể chịu cả hai cơ chế. Cần quan sát target instantiation ở đúng layer, không suy đoán chỉ bằng class name của reference.

### Factory method có thể chạy code ngoài ý định

Nếu Java `@Bean` method vừa tạo bean vừa gọi external API tốn thời gian, việc target bị eager consumer yêu cầu sẽ kích hoạt toàn bộ factory method ấy trong startup. Dời sang lazy proxy chuyển tác vụ tới lần đầu dùng, không thay thế timeout/retry/idempotency.

### Static @Bean và infrastructure

Những `BeanFactoryPostProcessor`/`BeanPostProcessor` có thời điểm tạo sớm, và static `@Bean` có thể phù hợp cho factory methods cung cấp một số post-processors để tránh instantiate configuration object quá sớm. Đây là mảng lifecycle hạ tầng riêng, không nên xem static là cách sửa lazy dependency thông thường.

## 23. Spring Boot global lazy và hệ quả

Spring Boot có cấu hình:

```properties
spring.main.lazy-initialization=true
```

Khi bật, Boot cố đặt nhiều bean definitions thành lazy để cải thiện thời gian startup. Tuy nhiên:

- Đây là **tùy chọn của Boot**, không phải generic setting mà plain `AnnotationConfigApplicationContext` tự đọc.
- Nếu một bean vẫn eager và phụ thuộc vào bean lazy, dependency vẫn có thể bị tạo.
- Một số infrastructure beans có ngoại lệ hoặc cần hoạt động sớm.
- Lỗi cấu hình có thể bị đẩy tới request đầu tiên.
- Bean được dùng qua proxy/provider có thể chịu extra first-use latency.

**Đừng dùng global lazy như giải pháp duy nhất** cho startup chậm do business initialization trong constructor. Hãy đo đúng cost, thiết kế startup readiness và giữ fail-fast cho các dependencies bắt buộc.

## 24. Bài tập có đáp án

### Bài 1 — Phân biệt definition và instance

Một `@Bean @Lazy Repository repository()` đã được Spring đăng ký. `containsBeanDefinition("repository")` là true. Điều này có đủ chứng minh constructor Repository đã chạy không?

**Đáp án:** Không. Definition tồn tại chỉ chứng minh container biết cách tạo. Cần quan sát instance/cache hoặc một marker; đừng tự kích hoạt `getBean()` khi muốn đo trạng thái ban đầu.

### Bài 2 — Eager A cần lazy B

Bean A là singleton eager, constructor cần B; B singleton lazy. Khi ApplicationContext refresh, B có bị tạo không?

**Đáp án:** Thông thường có. Để gọi A constructor, Spring phải resolve B instance theo dependency bắt buộc.

### Bài 3 — A là lazy

A và B đều lazy; A cần B, nhưng không bean eager nào cần A hay B. Sau refresh, có chắc chúng đã tạo chưa?

**Đáp án:** Không. Chúng có thể vẫn deferred. Khi caller yêu cầu A, Spring tạo B để hoàn thành dependency rồi tạo A.

### Bài 4 — Lazy trên parameter

Eager A nhận `@Lazy B b` (injection point) và B lazy singleton; interface B có thể proxy. Khi nào target B được tạo?

**Đáp án:** Thường tới lần đầu proxy được sử dụng; constructor A có thể chỉ nhận proxy. Nhưng nếu constructor/init A gọi method trên proxy hoặc consumer khác cần B trực tiếp, B có thể vẫn tạo trong startup.

### Bài 5 — Một consumer khác

`CheckoutService` dùng lazy proxy tới RemoteGateway, nhưng `MonitoringService` eager inject gateway trực tiếp. Gateway có còn deferred sau refresh không?

**Đáp án:** Thường không. Eager MonitoringService buộc tạo target. Lazy injection ở CheckoutService chỉ ảnh hưởng cạnh dependency riêng của CheckoutService.

### Bài 6 — @DependsOn

A eager có `@DependsOn("b")`; B lazy singleton. Có thể B vẫn được tạo lúc startup không?

**Đáp án:** Có. Depends-on yêu cầu B được khởi tạo trước A theo ordering metadata.

### Bài 7 — ObjectProvider

Consumer eager giữ `ObjectProvider<B>` nhưng không gọi `getObject()` cho tới method `serve()`. B lazy có nhất thiết tạo lúc startup không?

**Đáp án:** Không vì riêng cạnh provider đó. Khi `serve()` gọi `getObject()`, target mới được resolve, trừ khi một consumer khác tạo nó sớm.

### Bài 8 — Observability

Bạn muốn biết lazy bean `remoteGateway` đã được tạo chưa mà không làm nó tạo. Nên gọi `containsSingleton` hay `getBean`?

**Đáp án:** `containsSingleton("remoteGateway")`. `getBean` có thể tạo object, phá điều kiện quan sát.

### Bài 9 — XML

`<bean id="b" class="..." lazy-init="true"/>` và `<bean id="a" ...><constructor-arg ref="b"/></bean>` với A eager. Đảo thứ tự hai thẻ `<bean>` giúp B tránh tạo sớm không?

**Đáp án:** Không. Spring dựa vào dependency graph, không phải vị trí khai báo XML, để resolve B cho A.

### Bài 10 — Scope

B prototype, A singleton eager nhận B qua constructor. B có thể được tạo lúc refresh không? A nhận B mới mỗi lần gọi business method?

**Đáp án:** B có thể được tạo để inject khi A khởi tạo. A thường giữ instance prototype đó; không tự đổi mỗi method call. Nếu cần B mới mỗi lượt, dùng provider/factory phù hợp.

### Bài 11 — Bean missing

Một consumer eager nhận `@Lazy PaymentGateway gateway` nhưng không có PaymentGateway target bean. Context startup có thể vẫn qua trong một số lazy-proxy scenarios. Có nên chấp nhận?

**Đáp án:** Không nếu gateway là dependency bắt buộc. Target resolution failure bị dời muộn. Nên test path dùng gateway hoặc fail-fast chủ động theo reliability contract.

### Bài 12 — Vòng A↔B

A eager constructor cần B lazy, B constructor cần A. Chỉ thêm `@Lazy` trên B definition có giải quyết vòng không?

**Đáp án:** Không. A vẫn cần B ngay, B lại cần A đang xây. Sửa dependency graph hoặc trích coordinator/abstraction phù hợp.

### Bài 13 — Singleton sau lần đầu dùng

Một lazy singleton được tạo bởi `getBean` ở request đầu. Request sau lấy cùng bean từ context. Có phải mỗi lần trả instance mới không?

**Đáp án:** Không. Lazy không đổi singleton identity; các lần lookup trong cùng container dùng cùng managed singleton.

### Bài 14 — Giá phải trả

Một bean tạo chậm 800 ms. Dùng proxy để defer target. Thời gian 800 ms biến mất không?

**Đáp án:** Không. Nó có thể chuyển sang first-use latency. Cần đo và quản lý đường đi người dùng/thời gian timeout, không chỉ tối ưu metric startup.

### Bài 15 — Callback sau singleton pre-instantiation

`SmartInitializingSingleton.afterSingletonsInstantiated()` có đảm bảo chưa có lazy bean nào được tạo không?

**Đáp án:** Không. Lazy beans bị eager dependencies kéo lên đã có thể được tạo trong pre-instantiation phase.

### Bài 16 — Dự đoán output

Trong ví dụ mục 10, tại sao `required.createdAtRefresh=true` nhưng `idle.createdAtRefresh=false`?

**Đáp án:** `requiredIndex` là dependency bắt buộc của eager `eagerCatalogService`; `idleReport` không có eager consumer yêu cầu.

### Bài 17 — Quan sát proxy

Tại sao `gateway.hasSingletonBefore=false` dù `deferredConsumer` đã được tạo thành công?

**Đáp án:** Consumer giữ lazy-resolution proxy cho RemoteGateway; target singleton `remoteGateway` chưa phải instantiate tại thời điểm đó.

### Bài 18 — Refactor

Ứng dụng có eager controller cần 5 clients lazy nhưng chỉ một client được dùng thường xuyên. Nêu một thiết kế để giảm startup cost mà không che dependency bắt buộc.

**Đáp án định hướng:** Chỉ giữ eager initialization cho client cốt lõi cần fail-fast; với các integrations ít dùng, inject interface qua `@Lazy` injection point hoặc provider tại use-case boundary. Constructor không dereference lazy proxy. Viết tests cho feature path, timeout/health/readiness cho external services, theo dõi latency first-use và không dùng global lazy để che thiếu configuration.

## 25. Checklist kiểm tra trong dự án

- [ ] Đã phân biệt scope `singleton` với thời điểm `eager`/`lazy`.
- [ ] Biết `ApplicationContext.refresh()` chủ động tạo regular non-lazy singletons.
- [ ] Không hiểu `@Lazy` bean definition như lệnh cấm khởi tạo trong startup.
- [ ] Đã kiểm tra **mọi eager consumers** của target lazy.
- [ ] Kiểm tra cả constructor, `@Bean` method parameter, setter và field injection.
- [ ] Không nhầm `@Lazy` tại injection point với `@Lazy` trên bean definition.
- [ ] Khi dùng lazy proxy, type có thể proxy được và constructor/init không dereference sớm.
- [ ] Nếu dùng provider, chỉ lookup đúng thời điểm cần và xử lý lỗi minh bạch.
- [ ] Không dùng provider/optional lookup để âm thầm bỏ qua mandatory dependency.
- [ ] Không dùng `@DependsOn` như cách giữ một bean lazy.
- [ ] Không mong prototype không bao giờ xuất hiện khi startup.
- [ ] Với `FactoryBean`, phân biệt factory instance, product và eager type lookup.
- [ ] Không ép business beans khởi tạo sớm từ BeanFactory post-processors.
- [ ] Đo lazy state qua `containsSingleton` hoặc markers trước first-use.
- [ ] Không gọi `getBean` khi chỉ muốn hỏi target lazy đã tạo hay chưa.
- [ ] Integration tests bao gồm startup, first-use, extra eager consumer và failure paths.
- [ ] Kiểm soát lỗi cấu hình bị trì hoãn bởi lazy proxy/provider.
- [ ] Có kế hoạch đối với first-use latency và startup readiness.
- [ ] Không phụ thuộc vào constructor log ordering giữa beans độc lập.
- [ ] Giữ constructor và init callbacks nhẹ, không đặt workflow không idempotent.
- [ ] Không dùng lazy đơn thuần để che circular dependency.
- [ ] Đã đánh giá ngoại lệ của Boot global lazy nếu chạy trên Boot.

## Kết luận

**Một bean có `@Lazy` vẫn có thể được tạo bởi phụ thuộc không lazy** vì Spring phải hoàn thành dependency của eager consumer trong khi `ApplicationContext.refresh()` tạo các singleton không lazy.

Ba tình huống cần phân biệt:

1. **Lazy bean definition + eager consumer inject trực tiếp:** Spring vẫn tạo target trong startup.
2. **Lazy injection-point proxy:** eager consumer có thể được tạo với proxy, còn target hoãn tới khi proxy được sử dụng — trừ khi một đường khác tạo nó sớm.
3. **`ObjectProvider<T>`:** consumer giữ provider và yêu cầu target khi cần, phù hợp nếu dynamic lookup là chủ đích.

`@Lazy` không đổi singleton scope, không làm dependency bắt buộc thành optional, không xóa construction cost và không tự sửa circular dependencies. Hãy đọc toàn bộ bean graph, kiểm thử bằng context thật và đo cả **startup** lẫn **first use** trước khi quyết định mức laziness.

## Tài liệu Spring chính thức

- [Spring Framework 6.2 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html): cơ chế lazy và trường hợp eager singleton buộc lazy dependency khởi tạo.
- [Spring Framework 6.2 — @Lazy Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/Lazy.html): lazy bean definitions, lazy-resolution proxy cho injection points và các giới hạn.
- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html): constructor/property dependency resolution.
- [Spring Framework 6.2 — ObjectProvider API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/ObjectProvider.html): lazy/dynamic lookup.
- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): singleton/prototype semantics.
- [Spring Framework 6.2 — Bean Dependencies: depends-on](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html): ordering metadata.

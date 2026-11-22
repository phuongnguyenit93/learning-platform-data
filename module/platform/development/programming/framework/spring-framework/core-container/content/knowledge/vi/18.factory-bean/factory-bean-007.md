# Lựa chọn giữa FactoryBean, @Bean và phương thức nhà máy trong Spring Core Container

## 1. Mục tiêu và câu hỏi thiết kế

Khi một hệ thống Java cần tạo HTTP client, đối tượng mã hóa, dynamic proxy, SDK client hoặc một service được lắp ráp từ nhiều dependency, có ít nhất ba cách viết code trông đều giống “factory”:

1. **Phương thức nhà máy Java thông thường (factory method)**: một hàm `static` hoặc instance method trả đối tượng, hoàn toàn có thể tồn tại mà không cần Spring.
2. **Phương thức cấu hình `@Bean`**: Spring đọc một method có `@Bean` thành **bean definition**, gọi method khi cần tạo bean và quản lý **đối tượng trả về** theo scope/lifecycle.
3. **`FactoryBean<T>`**: một **bean đặc biệt** implement contract của Spring. Khi tra cứu tên bean đó, container thường expose **sản phẩm T** do `getObject()` cung cấp, còn chính instance factory được truy cập bằng prefix `&`.

Chọn sai thường dẫn đến code rườm rà, bean được tạo ngoài container, tạo instance trùng, product không được đóng, hoặc autowiring không phát hiện đúng kiểu. Chọn đúng không phải chọn giải pháp “mạnh nhất”, mà chọn giải pháp **đơn giản nhất đủ diễn đạt ownership, thời điểm tạo, identity và integration với container**.

Bài này phân tích các tiêu chí đó, đưa ví dụ Java 17/Spring Framework 6.2 và giải thích khi nào mỗi phương án là hợp lý.

> Tên **“factory method”** chỉ một kỹ thuật tạo object, không tự chứng minh object được Spring quản lý. Còn **`FactoryBean`** (viết hoa đúng tên interface) có semantics đặc biệt mà Spring nhận biết. Trong XML Spring, thuộc tính `factory-bean` mang nghĩa **tên bean chứa instance factory method**, không bắt buộc phải là `FactoryBean<T>`.

## 2. Bảng quyết định nhanh

| Câu hỏi | Factory method Java | `@Bean` method | `FactoryBean<T>` |
| --- | --- | --- | --- |
| Có phải phụ thuộc Spring không? | Không | Có, tại lớp cấu hình | Có, class triển khai interface Spring |
| Có tự đăng ký object vào container? | **Không** | **Có**, khi configuration được xử lý | **Có**, nếu chính FactoryBean được đăng ký làm bean |
| Code tạo object được gọi bởi ai? | Caller Java | Spring gọi theo bean definition | Spring yêu cầu `getObject()` khi cần product |
| DI của Spring áp dụng cho product? | Không tự động khi caller tự gọi | Có, như bean thông thường | Có mức độ integration của FactoryBean product; **không đồng nhất toàn bộ init/destroy lifecycle** của bean thông thường |
| Singleton/prototype product | Tự code quyết định | Dùng `@Scope` trên bean definition | `FactoryBean.isSingleton()` + scope của factory; cần xét **hai lớp** |
| Lấy factory object và product riêng? | Caller giữ factory reference | Tùy những bean bạn đăng ký | `getBean("&name")` lấy factory, `getBean("name")` lấy product |
| Khả năng Spring biết kiểu trước khi tạo | Nếu không đăng ký thì Spring không biết | Có thông tin từ return type `@Bean` | `getObjectType()` và metadata liên quan |
| Đóng tài nguyên | Caller/owner tự chịu trách nhiệm | Spring có destroy callbacks của bean được quản lý | Container quản lý FactoryBean; factory/caller cần xác định cleanup cho product |
| Độ phức tạp thiết kế | Thấp | Thấp–vừa | Cao hơn, dùng cho extension point thực sự cần thiết |
| Lựa chọn mặc định khi tích hợp SDK thông thường | Được gọi **trong `@Bean`** | **Thường nên chọn** | Chỉ khi product creation semantics cần được Spring hiểu đặc biệt |

**Quy tắc ưu tiên:** bắt đầu với **constructor injection + `@Bean`** (hoặc `@Component` cho class tự phát triển). Nếu thư viện chỉ có `ExternalSdk.createClient(config)`, cứ gọi static factory đó **bên trong `@Bean`**. Chỉ tự triển khai `FactoryBean<T>` khi bạn thực sự cần một bean factory được container nhận biết qua `getObject()/getObjectType()/isSingleton()` và cú pháp product-vs-factory.

## 3. Phương thức nhà máy Java thuần: tạo đối tượng là trách nhiệm của caller

Factory method là cách đóng gói logic `new` hoặc lựa chọn implementation:

```java
public final class FormatterFactory {
    private FormatterFactory() {}

    public static Formatter forLocale(String locale) {
        return new Formatter(locale);
    }
}
```

Đây là **mảnh minh họa**, giả định đã định nghĩa class `Formatter` có constructor nhận `String`. `forLocale` là static factory method thuần Java. Có thể gọi ở bất kỳ chương trình nào:

```java
Formatter formatter = FormatterFactory.forLocale("vi-VN");
```

Đây là mảnh sử dụng, không cần Spring. Ưu điểm: không phụ thuộc container, dễ tái sử dụng như thư viện, logic tạo object nằm ở một nơi, có thể kiểm thử hoàn toàn độc lập.

Nhưng nếu gọi factory method **trực tiếp trong business code**:

```java
class ReportService {
    void generate() {
        Formatter formatter =
                FormatterFactory.forLocale("vi-VN");
        // Sử dụng formatter...
    }
}
```

thì `ReportService` quyết định **khi nào và cách nào** tạo formatter. Spring không tự theo dõi những object đó, không tự inject field, không tự gọi `@PostConstruct`, `@PreDestroy` hoặc apply AOP chỉ vì ứng dụng đang dùng Spring.

### Static factory method và instance factory method

Static:

```java
Client client = ClientSdk.create("https://api.example");
```

Instance:

```java
ClientBuilder builder = new ClientBuilder(credentials);
Client client = builder.build("https://api.example");
```

Đây là các đoạn minh họa, yêu cầu `ClientSdk`/`Client`/`ClientBuilder`/`credentials` theo SDK cụ thể. Method có thể tự cache, tạo mới, trả object đã tồn tại hay implement pool. **Java không tự gắn scope singleton/prototype cho factory method**.

Một Java factory class được Spring inject **cũng không làm mọi product nó tạo tự động thành Spring bean**. `@Component ClientBuilder` khiến **builder** là bean, không khiến mỗi lần gọi `builder.build()` tự đăng ký product vào BeanFactory.

## 4. @Bean: bọc factory logic thành bean definition

`@Bean` là annotation đánh dấu một method để Spring đăng ký **bean definition**. Spring gọi method như factory method khi cần object, rồi áp dụng scope/lifecycle của bean returned.

```java
@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    ApiClient apiClient(ApiCredentials credentials) {
        return VendorSdk.createClient(credentials);
    }
}
```

Đây là mảnh minh họa; `ApiClient`, `ApiCredentials` và `VendorSdk` là những class giả định trong hệ thống thực. Không cần triển khai `FactoryBean<ApiClient>` nếu yêu cầu chỉ là tạo một client qua SDK. Spring có thể resolve `ApiCredentials` từ container để truyền vào method; tên bean mặc định lấy từ method `apiClient`, và scope mặc định là singleton.

**Hai tầng trách nhiệm rõ ràng:**

- **`VendorSdk.createClient(...)`** quyết định cách dựng đối tượng.
- **Spring `@Bean`** quyết định lúc tạo, wiring dependency, scope và lifecycle của kết quả.

Đó là một tổ hợp rất thường gặp và là đáp án cho nhiều trường hợp “SDK bắt buộc dùng static factory” hoặc “constructor bị private”.

### @Bean không buộc code domain dùng Spring

Class `ApiClient`, `VendorSdk` hay business service có thể hoàn toàn không import Spring. Spring chỉ xuất hiện trong class cấu hình:

```java
@Bean
ConnectionSettings connectionSettings(
        Environment environment) {
    return new ConnectionSettings(
            environment.getRequiredProperty("client.url"));
}
```

Đây là mảnh minh họa cần `ConnectionSettings` có constructor tương ứng và import `Environment`. Code domain không cần biết dependency đến từ Spring.

### @Bean hỗ trợ scope

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
RequestEncoder requestEncoder() {
    return new RequestEncoder();
}
```

Đây là mảnh minh họa có import `Scope`/`ConfigurableBeanFactory`, giả định class `RequestEncoder` tồn tại. Mỗi lần BeanFactory trực tiếp resolve prototype này sẽ tạo đối tượng mới. Nhưng nếu inject prototype vào một singleton bằng constructor **một lần**, singleton vẫn giữ instance đã nhận; không tự thay prototype ở mỗi lần gọi method.

### @Bean hỗ trợ init/destroy callbacks

```java
@Bean(initMethod = "connect", destroyMethod = "close")
RemoteChannel remoteChannel(Config config) {
    return RemoteChannel.open(config);
}
```

Đây là mảnh minh họa, giả định `RemoteChannel` có methods phù hợp. Bean returned nhận lifecycle callbacks như một bean được container quản lý, bao gồm những gì Spring hỗ trợ theo configuration.

Đặc biệt `@Bean` có mặc định `destroyMethod = "(inferred)"` trong Spring 6.2, có thể suy luận `close()`/`shutdown()` khi đủ điều kiện. Đối với resource mượn từ JNDI hoặc hệ thống bên ngoài có owner riêng, cân nhắc `@Bean(destroyMethod = "")` để tắt inferred cleanup; không nhầm rằng cấu hình này tự tắt mọi `@PreDestroy`/`DisposableBean` khác.

## 5. FactoryBean<T>: mở rộng cơ chế instantiation của BeanFactory

`org.springframework.beans.factory.FactoryBean<T>` là contract của **một bean đóng vai factory**. Spring hiểu đặc biệt ba method:

```java
public interface FactoryBean<T> {
    T getObject() throws Exception;
    Class<?> getObjectType();
    default boolean isSingleton() {
        return true;
    }
}
```

Đây là chữ ký **rút gọn để giải thích API** của Spring 6.2; chi tiết annotations/Javadoc đã lược bỏ.

- `getObject()`: sản xuất hoặc cung cấp product.
- `getObjectType()`: cho container biết type của product, hữu ích cho autowiring/type lookup **mà không cần tạo product**.
- `isSingleton()`: cho biết product có là shared singleton hay không; mặc định `true`.

Đăng ký một `FactoryBean` tên `remoteClient` nghĩa là:

```java
Object client  = context.getBean("remoteClient");
Object factory = context.getBean("&remoteClient");
```

Đây là mảnh minh họa, giả định bean `remoteClient` implements `FactoryBean`.

- `"remoteClient"` → **product** do `FactoryBean.getObject()` cung cấp.
- `"&remoteClient"` → **bản thân FactoryBean instance**.
- Prefix là `BeanFactory.FACTORY_BEAN_PREFIX`; không phải ký pháp Java đặc biệt hay một bean definition tên `&remoteClient`.

Chính semantics này khiến `FactoryBean` khác hẳn một class tự đặt tên `RemoteClientFactory` nhưng không implement interface.

### getObjectType() là một quyết định kiến trúc

Spring có thể cần suy ra type khi chọn candidate cho constructor injection:

```java
@Override
public Class<?> getObjectType() {
    return ApiClient.class;
}
```

Đây là mảnh method minh họa. Nên trả type ổn định (thường interface hoặc class sản phẩm) **không gây side effect**. Trả `null` nếu thực sự chưa xác định được type có thể khiến autowiring theo type bỏ qua FactoryBean đó.

Không viết:

```java
@Override
public Class<?> getObjectType() {
    return getObject().getClass(); // Anti-pattern.
}
```

vì truy vấn metadata có thể vô tình kết nối mạng, tạo thread hoặc làm product được dựng quá sớm, thậm chí khi factory chưa init xong.

### FactoryBean không phải BeanFactory

`BeanFactory` là container-level API, còn `FactoryBean` chỉ là một **extension point đang được container quản lý**. `FactoryBean` không thay thế BeanFactory, không chứa mọi bean definitions và không cung cấp `getBean(...)` cho toàn ứng dụng.

Tên gần giống nhau không có nghĩa hai interface liên quan theo inheritance.

## 6. Một chương trình Java 17+ để so sánh cả ba lựa chọn

Ví dụ này có mục tiêu kiểm chứng **quyết định kiến trúc**, không chỉ đọc định nghĩa. Một kiểu `Endpoint` được tạo theo bốn đường:

1. `@Bean` gọi **static factory method** của thư viện giả định.
2. `@Bean` gọi **instance factory method** của một collaborator.
3. Một `@Bean` đăng ký **`FactoryBean<Endpoint>`**; container expose product khi lookup.
4. `@Bean` prototype dùng instance factory method để tạo một instance khác ở mỗi lookup.

Chương trình dùng Spring Framework 6.2.18, Java 17, Gradle. Không cần Spring Boot.

Cấu trúc:

```text
factory-choice-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/FactoryChoiceDemo.java
```

### settings.gradle

```groovy
rootProject.name = 'factory-choice-demo'
```

### build.gradle

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'FactoryChoiceDemo'
}
```

### src/main/java/FactoryChoiceDemo.java

```java
import org.springframework.beans.factory.FactoryBean;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public class FactoryChoiceDemo {

    // Kiểu sản phẩm. Record Java 17 không biết gì về Spring.
    public record Endpoint(String origin) {
    }

    public record Prefix(String value) {
    }

    // Static factory method thuần Java.
    public static final class ExternalSdk {
        private ExternalSdk() {
        }

        public static Endpoint create(String prefix) {
            return new Endpoint("static:" + prefix);
        }
    }

    // Instance factory method thuần Java.
    public static class EndpointMaker {
        public Endpoint create(String prefix) {
            return new Endpoint("instance:" + prefix);
        }
    }

    // Một bean đặc biệt: Spring expose Endpoint là product.
    public static class EndpointFactory
            implements FactoryBean<Endpoint> {

        private final Prefix prefix;
        private Endpoint shared;
        private int calls;

        public EndpointFactory(Prefix prefix) {
            this.prefix = prefix;
        }

        @Override
        public synchronized Endpoint getObject() {
            calls++;
            if (shared == null) {
                shared = new Endpoint("factoryBean:" + prefix.value());
            }
            return shared;
        }

        @Override
        public Class<?> getObjectType() {
            return Endpoint.class;
        }

        @Override
        public boolean isSingleton() {
            return true;
        }

        public synchronized int calls() {
            return calls;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public Prefix prefix() {
            return new Prefix("blue");
        }

        @Bean
        public EndpointMaker endpointMaker() {
            return new EndpointMaker();
        }

        // @Bean lấy sản phẩm của static factory method.
        @Bean("staticEndpoint")
        public Endpoint staticEndpoint(Prefix prefix) {
            return ExternalSdk.create(prefix.value());
        }

        // @Bean lấy sản phẩm của instance factory method.
        @Bean("instanceEndpoint")
        public Endpoint instanceEndpoint(
                EndpointMaker maker, Prefix prefix) {
            return maker.create(prefix.value());
        }

        // @Bean này trả về FactoryBean, không trả Endpoint.
        @Bean("factoryEndpoint")
        public EndpointFactory factoryEndpoint(Prefix prefix) {
            return new EndpointFactory(prefix);
        }

        // Cùng instance factory Java nhưng bean product là prototype.
        @Bean("prototypeEndpoint")
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public Endpoint prototypeEndpoint(
                EndpointMaker maker, Prefix prefix) {
            return maker.create("prototype-" + prefix.value());
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            Endpoint fromStatic =
                    context.getBean("staticEndpoint", Endpoint.class);

            Endpoint fromInstance =
                    context.getBean("instanceEndpoint", Endpoint.class);

            Endpoint fromFactory =
                    context.getBean("factoryEndpoint", Endpoint.class);

            Endpoint factoryAgain =
                    context.getBean("factoryEndpoint", Endpoint.class);

            EndpointFactory realFactory =
                    context.getBean("&factoryEndpoint",
                                    EndpointFactory.class);

            EndpointFactory sameFactory =
                    context.getBean("&factoryEndpoint",
                                    EndpointFactory.class);

            Endpoint firstPrototype =
                    context.getBean("prototypeEndpoint", Endpoint.class);

            Endpoint secondPrototype =
                    context.getBean("prototypeEndpoint", Endpoint.class);

            // Gọi factory method bằng Java thông thường:
            Endpoint manual = context.getBean(EndpointMaker.class)
                    .create("manual");

            System.out.println("static=" + fromStatic.origin());
            System.out.println("instance=" + fromInstance.origin());
            System.out.println("factoryBean=" + fromFactory.origin());
            System.out.println("staticSingleton=" +
                    (fromStatic == context.getBean("staticEndpoint")));
            System.out.println("factoryProductSingleton=" +
                    (fromFactory == factoryAgain));
            System.out.println("sameFactoryInstance=" +
                    (realFactory == sameFactory));
            System.out.println("productVsFactoryDifferentTypes=" +
                    (!((Object) fromFactory instanceof FactoryBean<?>)));
            System.out.println("factoryGetObjectCalls=" +
                    realFactory.calls());
            System.out.println("prototypeDifferent=" +
                    (firstPrototype != secondPrototype));
            System.out.println("prototypeOrigin=" +
                    firstPrototype.origin());
            System.out.println("manualOrigin=" + manual.origin());
        }
    }
}
```

**Lưu ý về Java:** `Endpoint` là một `record` không implement `FactoryBean`. Biểu thức `fromFactory instanceof FactoryBean<?>` trực tiếp không biên dịch do hai kiểu không tương thích. Mã đầy đủ ở trên **đã cast sang `Object` trước khi dùng `instanceof`**, nên có thể copy-paste chạy mà không cần thay dòng nào.

### Chạy

```bash
gradle run --quiet
# Nếu dự án đã có Gradle Wrapper:
# ./gradlew run --quiet
```

Kết quả do `System.out` của chương trình in ra:

```text
static=static:blue
instance=instance:blue
factoryBean=factoryBean:blue
staticSingleton=true
factoryProductSingleton=true
sameFactoryInstance=true
productVsFactoryDifferentTypes=true
factoryGetObjectCalls=1
prototypeDifferent=true
prototypeOrigin=instance:prototype-blue
manualOrigin=instance:manual
```

Trong thực tế có thể có log runtime/framework, không thuộc danh sách các dòng `System.out` ở trên.

### Giải thích

- `staticEndpoint`: Spring gọi method `@Bean`, method đó gọi static Java factory `ExternalSdk.create`. Product `Endpoint` là bean singleton, dù `ExternalSdk` hoàn toàn không phải Spring bean.
- `instanceEndpoint`: Spring resolve collaborator `EndpointMaker` từ container, rồi gọi instance method `maker.create(...)` trong `@Bean`. Product cũng là bean singleton.
- `factoryEndpoint`: bean definition chứa **`EndpointFactory`**, vốn implements `FactoryBean<Endpoint>`. `getBean("factoryEndpoint")` trả product `Endpoint`; `getBean("&factoryEndpoint")` trả `EndpointFactory`. Vì `isSingleton()==true`, product được cache; `getObject()` chỉ cần gọi một lần cho các lookup được quan sát.
- `prototypeEndpoint`: vẫn chỉ là một `@Bean` method gọi Java factory bình thường, nhưng có `@Scope("prototype")`. Hai lookup tạo hai instance độc lập.
- `manual`: gọi `EndpointMaker.create` trực tiếp là một lời gọi Java; product tạo ra không tự đăng ký thêm bean definition trong context. `EndpointMaker` vẫn là bean singleton, nhưng `manual` **không** là một bean mới được Spring quản lý.

Đây là minh họa cả ba lựa chọn **trong cùng container**. Sự khác nhau nằm ở việc ai quản lý product và contract mà Spring nhận diện, không phải cú pháp tạo object `new`, static hay instance.

## 7. Đối chiếu kiểu product và factory trong ví dụ

Dòng `!((Object) fromFactory instanceof FactoryBean<?>)` ở mục 6 dùng cast sang `Object` để kiểm tra kiểu runtime hợp lệ trong Java 17. Kết quả `true` xác nhận product `Endpoint` không phải `FactoryBean`. Đây chỉ là phép kiểm chứng minh họa, không phải cách ứng dụng nên tự dò factory bằng `instanceof`.

Khi code cần chính factory, cách rõ hơn là tra `getBean("&factoryEndpoint", EndpointFactory.class)`; khi cần product, tra `getBean("factoryEndpoint", Endpoint.class)`. Hai lookup này cho thấy sự khác nhau về hợp đồng của `FactoryBean` mà không cần ép kiểu hoặc đoán từ tên Java class.

## 8. Khi nào chọn @Bean gọi static factory method?

Chọn khi thư viện chỉ cung cấp:

```java
ThirdPartyClient client =
        ThirdPartyClient.create(apiKey, timeout);
```

Đây là mảnh minh họa với API giả định. Bạn có thể đăng ký nó gọn bằng:

```java
@Configuration(proxyBeanMethods = false)
class ThirdPartyConfig {

    @Bean(destroyMethod = "close")
    ThirdPartyClient thirdPartyClient(
            ClientSettings settings) {
        return ThirdPartyClient.create(
                settings.apiKey(), settings.timeout());
    }
}
```

Đây là mảnh cấu hình minh họa, cần `ThirdPartyClient`/`ClientSettings` tương ứng. Lợi ích:

- Spring resolve `ClientSettings`;
- product `ThirdPartyClient` có tên và scope;
- client có lifecycle nếu bean definition được cấu hình đúng;
- client được constructor-inject vào các service;
- code SDK thuần Java, không bị ép implement Spring API.

**Không nên bọc thêm một custom FactoryBean** chỉ để gọi đúng một static factory method. Điều đó thêm boilerplate, tăng số khái niệm và lifecycle cần quản lý mà không cải thiện hành vi.

### Factory có constructor private

Java library thường khóa constructor vì phải kiểm soát invariant:

```java
public final class TokenCodec {
    private TokenCodec(String secret) { /* ... */ }

    public static TokenCodec fromSecret(String secret) {
        // ... validate ...
        return new TokenCodec(secret);
    }
}
```

Đây là class minh họa. `@Bean TokenCodec tokenCodec(...)` gọi `TokenCodec.fromSecret(...)` là giải pháp tự nhiên. Spring **không yêu cầu** product có public constructor nếu bạn đã cung cấp object qua factory method.

## 9. Khi nào chọn @Bean gọi instance factory method?

Chọn khi quá trình tạo cần một factory collaborator có state/dependencies:

```java
@Configuration(proxyBeanMethods = false)
class CryptoConfig {

    @Bean
    KeyProvider keyProvider(Environment env) {
        return new KeyProvider(
                env.getRequiredProperty("security.key-path"));
    }

    @Bean
    TokenSigner tokenSigner(KeyProvider provider) {
        return provider.createSigner();
    }
}
```

Đây là mảnh minh họa. `KeyProvider`, `TokenSigner` là các type do ứng dụng định nghĩa. Phương thức `createSigner()` là **instance factory method Java**; factory collaborator `KeyProvider` cũng là một bean; product `TokenSigner` được **đăng ký riêng** nhờ `@Bean` thứ hai.

Ưu điểm:

- Reuse factory state/dependencies của `KeyProvider`.
- Vẫn khai báo rõ mỗi product cần container quản lý.
- Scope của `tokenSigner` độc lập scope của `keyProvider`.
- Code consumer chỉ inject `TokenSigner`, không biết factory implementation.

Nếu một factory có nhiều method (create signer, verifier, decoder), có thể khai báo nhiều `@Bean` methods để đăng ký từng product riêng, không cần bắt tất cả các sản phẩm đi qua một `FactoryBean`.

### XML: static và instance factory methods

Spring XML có cú pháp factory method rõ ràng:

```xml
<bean id="staticProduct"
      class="example.LegacyFactory"
      factory-method="createStatic"/>

<bean id="legacyFactory"
      class="example.LegacyFactory"/>

<bean id="instanceProduct"
      factory-bean="legacyFactory"
      factory-method="createInstance"/>
```

Đây là **XML minh họa**, giả định `example.LegacyFactory` có static method `createStatic()`, no-arg constructor và instance method `createInstance()`. Tên thuộc tính `factory-bean="legacyFactory"` chỉ **bean làm đối tượng giữ instance factory method**; **không yêu cầu** class đó implements `org.springframework.beans.factory.FactoryBean`.

Đây là nguồn gốc của một nhầm lẫn nổi tiếng trong Spring docs: chữ *factory bean* viết thường có thể mang nghĩa “bean chứa method tạo object”, còn `FactoryBean` viết hoa là interface có ba method và semantics product dereference.

## 10. Khi nào FactoryBean<T> thực sự mang lại lợi ích?

Chọn `FactoryBean<T>` nếu bạn đang viết **container integration** thay vì chỉ đăng ký một product tĩnh. Các đặc điểm thường xuất hiện:

1. **Product là dynamic proxy** được tạo dựa vào metadata, interface hoặc descriptor.
2. **Một bean name cần expose product** trong khi bản thân factory có state/lifecycle riêng và cũng cần tra cứu `&name`.
3. Container hoặc framework cần **dự đoán product type** qua `getObjectType()`, trước khi sản phẩm được tạo.
4. Product có **singleton-vs-non-singleton** contract cần thể hiện trên factory, không chỉ một `@Scope` đơn giản.
5. Việc tạo product có thể được trì hoãn để tích hợp framework hạ tầng.
6. Bạn đang xây reusable library/infrastructure được đăng ký bằng bean definitions từ XML, Java config hoặc registry API.

Ví dụ ý tưởng:

```java
public final class RemoteProxyFactory
        implements FactoryBean<RemoteService> {

    private final RemoteProxyBuilder builder;

    public RemoteProxyFactory(RemoteProxyBuilder builder) {
        this.builder = builder;
    }

    @Override
    public RemoteService getObject() throws Exception {
        return builder.createProxy(RemoteService.class);
    }

    @Override
    public Class<?> getObjectType() {
        return RemoteService.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }
}
```

Đây là **class minh họa**, giả định `RemoteService` và `RemoteProxyBuilder` tồn tại; cần import `FactoryBean`. Factory `getObject()` trả proxy; một bean name có thể được inject theo interface `RemoteService` thay vì buộc consumer phụ thuộc type proxy cụ thể.

**Nhưng có một điều cần sửa cho production:** method `getObject()` ở trên **tạo một proxy mới khi được gọi trực tiếp** dù đã khai báo `isSingleton()==true`. Container có thể cache product, nhưng contract tốt của FactoryBean yêu cầu product singleton có identity ổn định. Hãy cache proxy ở factory hoặc đảm bảo `builder.createProxy(...)` trả shared product. Mảnh này chỉ biểu diễn ý tưởng integration, không phải implementation singleton hoàn thiện.

### getObjectType() và predictability

FactoryBean cần công bố type đủ ổn định cho Spring autowiring. Tránh gọi `getObject()` từ `getObjectType()`. Điều đó có thể thực thi external I/O hoặc tạo proxy chưa sẵn sàng ở lúc container đang hỏi metadata.

Nếu type không biết trước, `getObjectType()` có thể trả `null`, nhưng type-based lookup/autowiring sẽ bị hạn chế. Một interface công khai ổn định là lựa chọn tốt hơn nếu product runtime có class động.

## 11. Scope và identity: đừng nhầm factory với product

### Factory method thuần Java

Phương thức Java có thể trả:

```java
public Endpoint create() {
    return new Endpoint("new-every-time");
}
```

Nếu caller gọi hai lần, có hai instance, trừ khi factory tự cache. Không có `@Scope` implicit nào được gắn.

### @Bean

`@Bean Endpoint endpoint()` mặc định tạo singleton bean trong container. Dù method luôn `return new Endpoint(...)`, Spring không tự gọi lại method ở mỗi lookup singleton. Với `@Scope("prototype")`, mỗi lần BeanFactory trực tiếp tạo bean prototype sẽ gọi lại factory method.

### FactoryBean

`FactoryBean.isSingleton()` điều khiển product caching contract. Bản thân FactoryBean có bean definition với scope riêng. Ví dụ một singleton FactoryBean có thể cấp:

- singleton product nếu `isSingleton()==true`;
- product không cache nếu `isSingleton()==false`.

Không suy ra “FactoryBean singleton thì product luôn singleton” hoặc “`isSingleton=false` chắc chắn prototype”. Một `SmartFactoryBean` có `isPrototype()` để bổ sung semantics của product độc lập.

### Trường hợp singleton inject prototype

`@Bean` method trả prototype đúng scope, nhưng khi prototype được inject vào singleton qua constructor, Spring resolve **một lần trong lúc dựng singleton**. Nếu mỗi nghiệp vụ cần object mới, dùng `ObjectProvider<Endpoint>`, lookup method injection hoặc một Java factory collaborator với lifetime được thiết kế rõ.

`FactoryBean` không phải công cụ mặc định để giải quyết mọi bài toán “singleton cần prototype”. Nếu nhiệm vụ chỉ là yêu cầu prototype mới mỗi lần, `ObjectProvider` thường trực tiếp hơn.

## 12. Vòng đời và quyền sở hữu tài nguyên

Đây là tiêu chí quan trọng hơn số dòng code. Nếu product mở socket/file/threads, ai chịu trách nhiệm đóng?

| Cách tạo | Quyền sở hữu mặc định cần nghĩ tới | Hướng cleanup |
| --- | --- | --- |
| Factory method Java gọi trực tiếp ngoài Spring | Caller hoặc factory theo hợp đồng Java | `try-with-resources`/`finally`/explicit close |
| `@Bean` trả singleton resource | Spring nếu cấu hình giao ownership cho context | `@PreDestroy`, `DisposableBean`, `destroyMethod` hoặc inferred `close`/`shutdown` |
| `@Bean` trả prototype | Caller sau khi nhận prototype | Tự đóng từng instance |
| `FactoryBean` bản thân là singleton | Spring quản lý **factory bean instance** | Factory destroy callback khi context đóng |
| Product do `FactoryBean.getObject()` tạo | Không tự có toàn bộ destruction lifecycle của bean thường | Factory theo dõi/đóng product, hoặc caller quản lý theo contract |
| Resource được mượn từ shared registry/JNDI | External owner | Không tự close; tắt inferred destroy trên bean borrowed khi phù hợp |

Theo `FactoryBean` Javadoc, container quản lý lifecycle của **FactoryBean instance**, nhưng **không quản lý tự động toàn bộ lifecycle destruction của product** theo cùng cách. Vì vậy nếu proxy hoặc client product giữ resource, factory phải phối hợp cleanup hoặc giao ownership cho caller.

### Product singleton có resource

```java
final class ClientFactory
        implements FactoryBean<ManagedClient>, DisposableBean {

    private ManagedClient singleton;

    @Override
    public synchronized ManagedClient getObject() {
        if (singleton == null) {
            singleton = new ManagedClient();
        }
        return singleton;
    }

    @Override
    public Class<?> getObjectType() {
        return ManagedClient.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }

    @Override
    public synchronized void destroy() throws Exception {
        if (singleton != null) {
            singleton.close();
        }
    }
}
```

Đây là mảnh minh họa; cần imports của Spring `FactoryBean`/`DisposableBean` và class `ManagedClient implements AutoCloseable`. Trong code thật, hãy làm `destroy()` idempotent, xử lý partial initialization và không để một product đã được đóng bị cấp lại.

Nếu factory tạo product non-singleton, cần thiết kế cách theo dõi hoặc yêu cầu caller close từng product, không thể chỉ đóng một field `singleton`.

### FactoryBean tạo product trong getObject và gặp lỗi

`getObject()` có thể `throws Exception`. Nếu đã mở socket rồi bước sau throw, bean factory chưa chắc đã nhận được một product hợp lệ để destroy. Cleanup resource trung gian ngay trong `getObject()` bằng `try/finally`. Đây là cùng nguyên tắc với `@Bean` factory method ném lỗi trước `return`.

## 13. @Configuration(proxyBeanMethods) và gọi chéo @Bean methods

Phân biệt quan trọng khi chọn `@Bean`:

```java
@Configuration(proxyBeanMethods = false)
class LiteConfig {

    @Bean
    Dependency dependency() {
        return new Dependency();
    }

    @Bean
    Consumer consumer() {
        // Đây là lời gọi Java thuần, KHÔNG được Spring chặn.
        return new Consumer(dependency());
    }
}
```

Đây là mảnh minh họa với `Dependency`/`Consumer` giả định. Khi `proxyBeanMethods = false`, method `consumer()` gọi trực tiếp `dependency()` có thể tạo **một Dependency khác**, không phải singleton container đã đăng ký.

Cách nên làm:

```java
@Configuration(proxyBeanMethods = false)
class SafeConfig {

    @Bean
    Dependency dependency() {
        return new Dependency();
    }

    @Bean
    Consumer consumer(Dependency dependency) {
        return new Consumer(dependency);
    }
}
```

Spring resolve dependency qua container, tránh bypass lifecycle/scope của `dependency`. Đây là mảnh minh họa không phải chương trình độc lập.

Với `@Configuration` full mode và `proxyBeanMethods = true` mặc định, Spring có thể tạo CGLIB-enhanced subclass để **intercept lời gọi chéo giữa `@Bean` methods**, trả scoped bean tương ứng. Nhưng điều đó có giới hạn với final class/method và không nên bị lạm dụng làm giải pháp cho mọi trường hợp. Parameter injection rõ nghĩa hơn khi không cần interception.

**Không nhầm** hành vi intercept `@Bean` methods của `@Configuration` với `FactoryBean<T>`: hai cơ chế khác nhau hoàn toàn.

## 14. XML static/instance factory method so với FactoryBean

Xét cấu hình XML:

```xml
<bean id="encoder"
      class="example.EncodingSdk"
      factory-method="staticEncoder"/>

<bean id="codecBuilder"
      class="example.CodecBuilder"/>

<bean id="decoder"
      factory-bean="codecBuilder"
      factory-method="createDecoder"/>
```

Đây là XML minh họa, giả định có class và methods phù hợp. `encoder` và `decoder` là **bean products thông thường**, được Spring xây bằng static/instance factory methods.

Nếu thay `codecBuilder` thành class implements `FactoryBean<Decoder>` và lookup `getBean("codecBuilder")`, Spring áp dụng semantics product của `FactoryBean`. Nhưng XML `factory-bean="codecBuilder"` không đồng nghĩa cùng thứ đó: nó chỉ nói Spring phải gọi instance method trên bean tên `codecBuilder` để tạo bean `decoder`.

Những khái niệm này có thể kết hợp nhưng không phải một:
- Factory method Java tạo object.
- XML/`@Bean` đăng ký product thành bean.
- `FactoryBean<T>` tạo abstraction riêng có product-dereference semantics.

Việc document cũ dùng cụm “factory bean” viết thường khiến developer dễ nhầm với interface viết hoa. Khi đọc code, hãy kiểm tra **kiểu thật của object được đăng ký** chứ không đoán từ tên.

## 15. Tính minh bạch khi autowiring và testing

### Constructor injection cho product

Nếu chỉ có một bean ứng viên kiểu `PricingClient`:

```java
@Service
class PriceService {
    private final PricingClient client;

    PriceService(PricingClient client) {
        this.client = client;
    }
}
```

Đây là mảnh minh họa, cần imports/definitions tương ứng. `PriceService` không quan tâm `PricingClient` đến từ constructor, static factory qua `@Bean` hay `FactoryBean`. Đó là mục tiêu của DI: giữ code nghiệp vụ độc lập với việc tạo object.

Nếu có nhiều ứng viên cùng type, dùng `@Qualifier` hoặc injection theo tên rõ ràng. Ví dụ mục 6 có nhiều bean `Endpoint`, nên truy xuất theo bean name; cố `getBean(Endpoint.class)` không có qualifier có thể dẫn đến `NoUniqueBeanDefinitionException`.

### Unit test factory thuần

`EndpointMaker.create("test")` có thể kiểm tra không cần Spring. Điều tương tự đúng với `ExternalSdk.create(...)` nếu code đó thuần Java và không cần external I/O.

### Integration test @Bean

Dựng `AnnotationConfigApplicationContext(Config.class)` để xác minh:
- Product được đăng ký.
- `@Scope` đúng.
- Dependencies đi qua container.
- Init/destroy callbacks xảy ra ở mốc dự kiến.
- Bean names/qualifiers không conflict.

### Integration test FactoryBean

Ngoài behavior `getObject()` khi gọi trực tiếp, cần kiểm tra:
- `context.getBean("x")` trả product.
- `context.getBean("&x")` trả factory.
- `getObjectType()` giúp type lookup.
- `isSingleton()` phù hợp identity product.
- Product có cleanup đúng với ownership.
- Các lỗi `getObject()` được propagate hợp lý.

Một `FactoryBean` unit test đạt yêu cầu **không chứng minh** container dereference và cache đúng nếu chưa có integration test.

## 16. Bảng tình huống thực tế

| Nhu cầu | Chọn ưu tiên | Vì sao |
| --- | --- | --- |
| Đăng ký SDK client từ static `create(config)` | `@Bean` gọi static factory | Gọn, type-safe, scope/lifecycle đầy đủ |
| Client builder có constructor dependencies, tạo một product | `@Bean` nhận builder rồi gọi instance method | Giữ rõ dependency của factory và product |
| Business method cần tạo object ngắn hạn không phải bean | Java factory method thuần | Tránh đưa object nghiệp vụ tạm thời vào container không cần thiết |
| Singleton muốn lấy prototype mới nhiều lần | `@Bean @Scope("prototype")` + `ObjectProvider<T>` | Product là bean đúng scope, lookup tường minh |
| Tạo client từ config có một lần init/cleanup | `@Bean(initMethod/destroyMethod)` | Một bean thông thường đủ |
| Product là dynamic proxy cần công bố interface/type trước khi tạo | `FactoryBean<T>` | Spring hiểu product type và product dereference |
| Viết framework integration reusable có nhiều product definitions | `FactoryBean<T>` hoặc bean definition registration | Extension point được container hiểu rõ |
| Product phải là singleton nhưng factory có nhiều config riêng | `FactoryBean<T>` với `isSingleton=true` hoặc các `@Bean` methods | Xem tính cần thiết của factory/product abstraction |
| External JNDI resource do app server sở hữu | `@Bean(destroyMethod = "")` | Không vô tình close borrowed resource |
| Cần một object không phụ thuộc Spring trong library portable | Static/instance Java factory | Không kéo framework vào library API |
| Nhiều product từ cùng một factory object | Nhiều `@Bean` methods gọi cùng factory hoặc Java factory trực tiếp | Rõ từng product và scope; không ép một `FactoryBean<T>` giải quyết đa loại |
| Product type không biết trước và framework chuyên biệt cần delegate | `FactoryBean` với interface product ổn định nếu có | Tận dụng `getObjectType()`, nhưng cần tránh null/type ambiguity |

## 17. Các anti-pattern và cách sửa

### Anti-pattern A: tự viết FactoryBean chỉ để bọc constructor

```java
public final class UserServiceFactoryBean
        implements FactoryBean<UserService> {
    @Override
    public UserService getObject() {
        return new UserService();
    }

    @Override
    public Class<?> getObjectType() {
        return UserService.class;
    }
}
```

Đây là class minh họa (cần imports và `UserService`). Nếu `getObject()` luôn tạo mới nhưng `isSingleton()` dùng default true, factory còn có **nguy cơ vi phạm kỳ vọng identity** khi bị gọi trực tiếp. Thay bằng:

```java
@Bean
UserService userService() {
    return new UserService();
}
```

đủ cho hầu hết trường hợp.

### Anti-pattern B: mọi method Java factory đều coi là bean

```java
Endpoint e = context.getBean(EndpointMaker.class)
                    .create("test");
```

Instance `e` là kết quả của lời gọi Java; nó **không** thành Spring bean mới chỉ vì `EndpointMaker` là Spring bean. Nếu cần Spring quản lý riêng product, khai báo `@Bean`/scope tương ứng.

### Anti-pattern C: dùng context.getBean ở mọi nơi

```java
class BusinessUseCase {
    private final BeanFactory beanFactory;

    BusinessUseCase(BeanFactory beanFactory) {
        this.beanFactory = beanFactory;
    }

    void run() {
        Endpoint e = beanFactory.getBean("staticEndpoint", Endpoint.class);
    }
}
```

Đây là mảnh minh họa. Nó làm business code phụ thuộc container và bean names dạng chuỗi. Với dependency cố định, dùng constructor injection kiểu `Endpoint` kèm qualifier khi cần; với dependency tạo mới theo scope, cân nhắc `ObjectProvider<Endpoint>`.

### Anti-pattern D: FactoryBean.getObjectType() kích hoạt network

`getObjectType()` phục vụ metadata; tránh mở kết nối, gọi API remote, hay dựng product chỉ để biết class. Cho Spring một kiểu ổn định qua interface/class nếu có thể.

### Anti-pattern E: FactoryBean.isSingleton() khác behavior

`isSingleton=true` trong khi `getObject()` luôn tạo object mới có thể không lộ ra khi lấy qua BeanFactory vì container cache, nhưng những ai gọi factory trực tiếp sẽ thấy behavior khác. Thiết kế shared singleton identity thực sự hoặc trả `false` nếu product đúng là non-singleton.

### Anti-pattern F: quên cleanup của FactoryBean product

Spring quản lý lifetime của factory bean instance; đừng cho rằng sản phẩm `AutoCloseable` sẽ luôn có `@PreDestroy`/`destroyMethod` được áp dụng tự động như object đăng ký thông thường. Factory hoặc caller phải có ownership rõ.

### Anti-pattern G: gọi chéo @Bean methods khi proxyBeanMethods=false

`consumer(dependency())` là lời gọi Java trực tiếp, có thể tạo instance ngoài singleton cache. Truyền `Dependency` làm argument cho `@Bean consumer(Dependency dependency)`.

### Anti-pattern H: tách mỗi construct step thành nhiều abstraction

Nếu chỉ có ba dòng dựng object trong `@Bean`, việc thêm `AbstractFactory` + `FactoryBean` + `Builder` + `ServiceLocator` có thể làm kiến trúc khó test và tăng coupling. Chỉ thêm abstraction nếu có **biến thể thực tế** hoặc integration contract rõ ràng.

## 18. Checklist thiết kế trước khi quyết định

1. Product có cần Spring quản lý như một bean không? Nếu không, Java factory method thuần có thể đủ.
2. Product chỉ cần tạo một lần từ constructor/static/instance factory? Nếu có, `@Bean` thường là lựa chọn đơn giản.
3. Product có request/prototype scope hay sẽ được chia sẻ singleton? Scope của bean và caching trong factory có phù hợp không?
4. Product có external resource cần close? Ai là owner: Spring, caller, factory hay external registry?
5. Class product có thể nhận DI trong `@Bean` method arguments mà không cần Spring-specific interface không?
6. Bạn có thật sự cần Spring biết type product qua `getObjectType()` **khi chỉ có FactoryBean definition** không?
7. Có cần expose **factory instance** và **product** dưới cùng bean name với `&name` không?
8. `FactoryBean.getObject()` có thread-safe, predictable và đúng singleton-status không?
9. Có thể dùng `ObjectProvider` để lấy prototype mới thay vì tự triển khai FactoryBean không?
10. Trong `@Configuration(proxyBeanMethods=false)`, đã thay direct cross-method calls bằng parameter injection chưa?
11. Nếu có nhiều product cùng type, đã đặt bean name/`@Qualifier` đúng chưa?
12. Có test chứng minh behavior và lifecycle thật qua Spring container chưa?

## 19. Quy tắc ngắn gọn để ghi nhớ

Một cách phân biệt theo ngôn ngữ tự nhiên:

- **“Tôi chỉ muốn đóng gói cách tạo object”** → **Java factory method**.
- **“Tôi muốn Spring quản lý object mà method đó tạo”** → **`@Bean` gọi factory method**.
- **“Tôi đang xây một factory bean mà Spring phải hiểu sản phẩm và cách expose của nó như một extension point”** → **`FactoryBean<T>`**.

Trong code thực tế, **`@Bean` và factory method Java không đối lập**: phương án phổ biến nhất chính là **dùng cả hai cùng lúc**. `FactoryBean` là lựa chọn riêng khi bạn cần semantics product/factory và metadata kiểu/caching đặc biệt.

**Không quyết định chỉ từ tên class `XxxFactory`.** Hãy kiểm tra nó có implement `FactoryBean` hay chỉ là một factory class Java, rồi xác định bean nào thực sự được Spring đăng ký, ai sở hữu product và nó tồn tại trong scope nào.

## 20. Nguồn chính thức để đọc và kiểm chứng

- [Spring Framework Reference — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): cấu hình bean definition từ method, dependency arguments, scope và lifecycle.
- [Spring Framework Reference — Customizing Instantiation Logic with a FactoryBean](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-extension.html): hợp đồng FactoryBean và cách `getBean("x")`/`getBean("&x")` hoạt động.
- [Spring Framework Reference — Bean Overview / Static and Instance Factory Methods](https://docs.spring.io/spring-framework/reference/6.2/core/beans/definition.html): constructor, static `factory-method`, XML instance `factory-bean` và sự phân biệt với `FactoryBean`.
- [Spring Framework Reference — Using the @Configuration annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html): inter-bean references và ảnh hưởng `proxyBeanMethods`.
- [Spring Framework 6.2.18 API — FactoryBean](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/FactoryBean.html): `getObject()`, `getObjectType()`, `isSingleton()` và lifecycle semantics của factory/product.
- [Spring Framework 6.2.18 API — @Bean](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/Bean.html): metadata bean definition, init/destroy method và annotation behavior.

**Kết luận:** Không cần triển khai `FactoryBean<T>` chỉ để gọi một factory method. Hãy đưa factory method Java vào `@Bean` nếu muốn product là Spring-managed bean. Khi cần container-level extension với product-vs-factory lookup, product type prediction và factory-specific caching semantics, `FactoryBean<T>` mới là công cụ đúng.

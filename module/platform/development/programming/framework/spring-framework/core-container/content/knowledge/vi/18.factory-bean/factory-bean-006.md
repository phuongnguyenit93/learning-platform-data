# Vòng đời của FactoryBean và trách nhiệm quản lý sản phẩm trong Spring Core Container

## 1. Bài toán và thông điệp chính

`FactoryBean<T>` là cơ chế mở rộng của Spring IoC Container để một **bean đóng vai trò factory** tạo hoặc cung cấp một object khác. Khi tên bean được đăng ký cho một `FactoryBean`, lời gọi thông thường `context.getBean("name")` trả về **sản phẩm** từ `getObject()`; muốn lấy **bản thân factory**, dùng tiền tố `&`: `context.getBean("&name")`.

Điều dễ nhầm nhất không nằm ở cú pháp `getObject()` mà ở **hai vòng đời khác nhau**:

1. **Vòng đời của FactoryBean instance:** chính factory là một Spring-managed bean. Spring tạo, inject dependency, gọi các callback khởi tạo, áp dụng bean post-processing và gọi destroy callbacks thích hợp khi scope của factory kết thúc.
2. **Vòng đời của object do FactoryBean sản xuất:** container có thể lấy sản phẩm, cache theo `isSingleton()` và áp dụng một số bước post-processing, nhưng **không tự động quản lý toàn bộ vòng đời khởi tạo/hủy của sản phẩm như một bean definition độc lập**. Đặc biệt, destroy callback, `Closeable.close()` hoặc `AutoCloseable.close()` của sản phẩm **không được container tự động gọi chỉ vì sản phẩm được FactoryBean trả về**.

Theo hợp đồng chính thức của `FactoryBean`, **FactoryBean chịu trách nhiệm quản lý tài nguyên của object do nó tạo** khi factory thực sự sở hữu object đó. Một factory quản lý sản phẩm dùng chung lâu dài có thể implement `DisposableBean` và chuyển tiếp `destroy()` tới `product.close()`. Nếu factory tạo nhiều sản phẩm không shared, code sử dụng sản phẩm hoặc một owner chuyên trách cần có cơ chế dọn dẹp từng instance.

~~~text
Bean definition: "connectionClient" → ConnectionClientFactoryBean
                             │
Spring tạo và quản lý        ▼
              FactoryBean instance
              - constructor
              - dependency injection
              - @PostConstruct / InitializingBean
              - destroy callback theo scope của factory
                             │
                       getObject()
                             ▼
                      Product object
              - có thể dùng chung/cached
              - có thể tạo mới mỗi lookup
              - KHÔNG mặc định được Spring gọi
                @PreDestroy/DisposableBean/close như bean thường
                             │
                        Ai đóng?
              FactoryBean hoặc owner của từng product
~~~

**Cảnh báo kiến thức:** `FactoryBean` khác hoàn toàn khái niệm *một method factory* được đánh dấu `@Bean` và khác **BeanFactory**. Chúng có thể được kết hợp nhưng không phải cùng một API.

## 2. Hợp đồng `FactoryBean<T>`

Interface nằm ở package `org.springframework.beans.factory`. Dạng giản lược:

~~~java
public interface FactoryBean<T> {
    T getObject() throws Exception;
    Class<?> getObjectType();
    default boolean isSingleton() {
        return true;
    }
}
~~~

Trong mã thực, `getObject()` và `getObjectType()` có thể trả `null` theo hợp đồng API (với điều kiện và hệ quả tương ứng); Spring có xử lý riêng cho các trường hợp đó.

### 2.1. `getObject()`

Trả về sản phẩm. Sản phẩm có thể:

- Được dựng mới bằng constructor/SDK builder.
- Được lấy từ một thư viện hoặc resource manager.
- Là một proxy hạ tầng.
- Là object được factory cache nội bộ để tái sử dụng.
- Có thể là resource giữ socket, file handle, thread hoặc connection pool, do đó cần ownership/cleanup rõ ràng.

Không nên giả định `getObject()` luôn chạy mỗi lần gọi `context.getBean(...)`, bởi Spring có thể cache sản phẩm singleton. Không nên gọi trực tiếp `factory.getObject()` rồi suy ra hành vi cache của `BeanFactory`: gọi trực tiếp bypass đường xử lý sản phẩm của container, trừ khi factory tự cache.

### 2.2. `getObjectType()`

Trả về kiểu của sản phẩm, giúp container thực hiện lookup/autowiring theo type mà không nhất thiết phải tạo sản phẩm. Ví dụ factory trả `Client.class` nếu `getObject()` trả `Client`.

Hợp đồng quan trọng:

- Nên trả kiểu có ý nghĩa **sớm và nhất quán**, kể cả trước khi factory hoàn toàn initialized.
- Không tạo resource nặng, không mở network và không dựa vào trạng thái chỉ có sau khi `@PostConstruct` chạy.
- Có thể trả `null` nếu type chưa xác định, nhưng như vậy by-type autowiring có thể **bỏ qua** factory, tạo lỗi khó hiểu.
- `getObjectType()` có thể được gọi nhiều lần vào các thời điểm bootstrap khác nhau; không dùng như init method.

### 2.3. `isSingleton()`

Quy định **semantics của sản phẩm**, không phải scope của chính FactoryBean.

- `true`: factory cam kết sản phẩm là một reference có thể dùng chung, container có thể cache sản phẩm của một singleton FactoryBean. Đây là **mặc định** trên interface hiện đại.
- `false`: sản phẩm không được xem là shared singleton theo contract của factory; BeanFactory thường gọi factory để có sản phẩm cho lần lookup tiếp theo. Điều này **không bắt buộc đảm bảo từng sản phẩm có identity khác nhau**; factory có thể tự tái sử dụng object vì lý do riêng.

Chỉ trả `true` khi có thể bảo đảm reference sản phẩm ổn định. Nếu `getObject()` luôn `new` một object khác nhưng `isSingleton()` báo `true`, Spring có thể cache sản phẩm đầu tiên, khiến semantics sai lệch giữa việc gọi qua container và gọi trực tiếp factory.

### 2.4. `SmartFactoryBean<T>`

`SmartFactoryBean` bổ sung những thông tin như `isPrototype()` (định nghĩa sản phẩm độc lập theo nghĩa prototype) và `isEagerInit()` (yêu cầu khởi tạo sản phẩm trong giai đoạn eager singleton initialization khi thích hợp). Đây là hợp đồng **nâng cao**, không cần dùng cho mọi custom FactoryBean.

`FactoryBean.isSingleton() == false` và `SmartFactoryBean.isPrototype() == true` không hoàn toàn là cùng khái niệm. `isSingleton=false` chỉ nói sản phẩm không phải shared singleton; còn `isPrototype=true` xác nhận factory thực sự tạo independent instances theo hợp đồng nâng cao.

## 3. Phân biệt ba khái niệm dễ nhầm

| Khái niệm | Vai trò | Ai cung cấp object | Thường dùng khi nào |
| --- | --- | --- | --- |
| `BeanFactory` | Container API tạo và quản lý bean | Chính Spring BeanFactory | DI container, metadata, bean lookup |
| `FactoryBean<T>` | Spring bean đặc biệt sản xuất một object khác | Code `getObject()` trong custom factory | Complex object setup, proxy/SDK integration |
| `@Bean` method | Bean definition dựa trên factory method | Method trong `@Configuration`/component | Đăng ký bean Java config thông thường |
| Java factory thuần | Class/method tự tạo object theo Java | Java application code | Khi không cần Spring-specific FactoryBean semantics |

Hai đoạn sau không tương đương về lifecycle:

~~~java
// Bean thông thường: sản phẩm là bean được Spring quản lý trực tiếp.
@Bean(destroyMethod = "close")
RemoteClient remoteClient() {
    return new RemoteClient();
}
~~~

~~~java
// FactoryBean: bean definition trả về factory đặc biệt.
// Lookup thông thường của tên bean trả về sản phẩm từ getObject().
@Bean
FactoryBean<RemoteClient> remoteClient() {
    return new RemoteClientFactoryBean();
}
~~~

Hai đoạn là mẫu minh họa, giả định có các class `RemoteClient`/`RemoteClientFactoryBean` và import cần thiết. Ở đoạn đầu, `RemoteClient` là bean trực tiếp: `destroyMethod="close"` gắn với chính bean definition ấy. Ở đoạn sau, lifecycle của bean definition chủ yếu áp dụng cho **FactoryBean instance**; sản phẩm `RemoteClient` không tự nhận cùng destroy callback.

Nếu sản phẩm cần một chuỗi đầy đủ của lifecycle callback trong Spring, hãy cân nhắc đăng ký nó thành **bean thường** thay vì chỉ cho FactoryBean tạo rồi trả ra.

## 4. FactoryBean được tạo và khởi tạo thế nào?

Khi container cần một FactoryBean instance, Spring thực hiện quy trình của Spring-managed bean thông thường:

1. Đọc bean definition, xác định class hoặc `@Bean` factory method tạo FactoryBean.
2. Resolve constructor/factory method arguments và tạo instance của FactoryBean.
3. Inject dependency qua constructor, setter, `@Autowired` hoặc những cơ chế được hỗ trợ.
4. Gọi Aware callbacks nếu factory implement (như `BeanNameAware`, `BeanFactoryAware`, `ApplicationContextAware` khi context phù hợp).
5. Chạy `BeanPostProcessor` và initialization callbacks của **FactoryBean**: `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, custom `initMethod` theo cấu hình.
6. Bean factory instance được quản lý trong scope mà bean definition của factory quy định.
7. Nếu cần sản phẩm, container gọi `FactoryBean.getObject()` (hoặc dùng cache sản phẩm). Khi cần đóng chính factory, Spring chạy destroy callback phù hợp với scope của factory.

FactoryBean ở scope `singleton` là cấu hình phổ biến. Một số custom factory có thể lazy init, một số triển khai `SmartFactoryBean` có chính sách eager khởi tạo sản phẩm; do đó **không được đoán** `getObject()` lúc nào cũng chạy ngay sau `afterPropertiesSet()` hoặc chỉ chạy khi application code gọi `getBean()`. Phải hiểu bean graph và chính sách eager/lazy.

### Khác biệt giữa factory và product trong một dòng thời gian

~~~text
t0 Spring đăng ký bean definition "managedClient"
t1 Tạo và inject ManagedClientFactoryBean
t2 FactoryBean.@PostConstruct / afterPropertiesSet()
t3 FactoryBean hoàn tất Spring post-processing
t4 Client product được cần → FactoryBean.getObject()
t5 BeanFactory có thể post-process/cache product
t6 Application code nhận product và sử dụng
t7 Context shutdown → FactoryBean destroy callback
t8 FactoryBean chuyển tiếp close tới product nếu factory sở hữu product
~~~

Đây là **timeline minh họa**; `getObjectType()` có thể được gọi trước t2 và nhiều lần. Nếu factory thuộc prototype scope hoặc nếu cơ chế lookup khác, việc tạo factory/product lặp lại có thể thay đổi. Không tự viết logic phụ thuộc vào con số lần gọi `getObjectType()` hoặc thời điểm chính xác của lần cache đầu tiên.

## 5. Lấy factory hay lấy sản phẩm: `name` và `&name`

Giả sử cấu hình có bean name `managedClient`, bean definition trỏ tới `ManagedClientFactoryBean implements FactoryBean<Client>`.

~~~java
// Client là sản phẩm.
Client client = context.getBean("managedClient", Client.class);

// FactoryBean là đối tượng tạo sản phẩm:
ManagedClientFactoryBean factory =
        context.getBean("&managedClient", ManagedClientFactoryBean.class);
~~~

Đây là snippet, giả sử có `context` và các type tương ứng.

Quy tắc:

- `getBean("managedClient")` → object từ `getObject()`, có thể là sản phẩm đã cache.
- `getBean("&managedClient")` → FactoryBean instance.
- `getBean(Client.class)` → có thể resolve sản phẩm của FactoryBean nếu `getObjectType()` khai báo kiểu phù hợp, không mơ hồ với bean khác.
- `getBean(ManagedClientFactoryBean.class)` → phụ thuộc type lookup và bean definitions, nhưng khi cần factory một cách không mơ hồ, `&beanName` là cú pháp rõ ràng.

Ký tự `&` ở đây là **factory dereference prefix** của Spring, không phải dấu AND hay syntax đặc biệt của Java. Tên bean có alias vẫn phải được resolve theo cơ chế naming của container.

Lỗi phổ biến: ép `context.getBean("managedClient")` thành `ManagedClientFactoryBean` sẽ nhận sản phẩm và thường ném `ClassCastException`. Dùng `&managedClient` nếu mục tiêu là cấu hình/debug factory.

## 6. Hai phạm vi độc lập: scope của FactoryBean và kiểu chia sẻ sản phẩm

Cần phân biệt:

- **Scope của FactoryBean instance** do bean definition quản lý, ví dụ singleton hoặc prototype.
- **Semantics chia sẻ sản phẩm** do `FactoryBean.isSingleton()` và (nếu có) `SmartFactoryBean.isPrototype()` mô tả.

| FactoryBean scope | `isSingleton()` cho sản phẩm | Hành vi thường gặp | Hệ quả lifecycle |
| --- | --- | --- | --- |
| Singleton | `true` | Một factory instance, sản phẩm dùng chung/cache | Factory singleton có thể dọn sản phẩm khi destroy |
| Singleton | `false` | Một factory instance, nhiều lần `getObject()` theo nhu cầu | Factory phải theo dõi products nếu nhận ownership; hoặc caller tự close |
| Prototype | `true` | Mỗi lần lấy factory có thể là factory instance riêng; cam kết singleton áp dụng trong ngữ cảnh một factory | Không kỳ vọng cache toàn context của một factory singleton cố định |
| Prototype | `false` | Factory có thể được tạo lại, sản phẩm cũng có thể mới | Spring không tự destroy từng prototype factory đã cấp |
| Singleton + `SmartFactoryBean` | Tùy cấu hình | Có thêm thông tin sản phẩm independent/eager | Cần kiểm tra contract nâng cao |

Bảng diễn tả các mô hình thông dụng, không phải mọi tổ hợp API/proxy/custom scope. **Tuyệt đối không diễn giải `isSingleton()` là `@Scope("singleton")` của FactoryBean.**

### Nếu sản phẩm cần trạng thái mỗi lần dùng

Khi factory trả independent sản phẩm, mỗi caller phải xác định lúc nào một sản phẩm được tạo, dùng qua bao nhiêu method call, và ai sở hữu việc đóng. Ví dụ sản phẩm là một mutable processing session:

~~~java
ProcessingSession session = context.getBean(
        "processingSession", ProcessingSession.class);
try {
    session.process(batch);
    session.commit();
} finally {
    session.close();
}
~~~

Đoạn này là ý tưởng ownership minh họa. `ProcessingSession` cần có `close()` đúng hợp đồng, và factory phải được cấu hình để trả independent sản phẩm nếu nghiệp vụ đòi hỏi. Không cho một sản phẩm không thread-safe dùng chung chỉ vì vô tình để `isSingleton()` ở mặc định `true`.

## 7. Container có xử lý gì cho sản phẩm không?

Có, nhưng cần diễn đạt chính xác.

### 7.1. Sản phẩm không có lifecycle đầy đủ như bean thường

Spring quản lý FactoryBean instance. `getObject()` của factory tạo sản phẩm; Spring có thể áp dụng `BeanPostProcessor.postProcessAfterInitialization(...)` lên sản phẩm, ví dụ để tạo proxy. Tuy vậy, **không có quy trình hoàn chỉnh** constructor injection, property population, các Aware callbacks, `@PostConstruct`, `InitializingBean` và destroy callbacks cho sản phẩm chỉ vì nó được FactoryBean trả về.

Vì vậy câu “product hoàn toàn vô hình với Spring” **không chính xác** (vì BeanFactory biết nó, có thể cache và post-process), nhưng câu “product được Spring quản lý hệt bean thường” **cũng sai**.

### 7.2. Nếu cần dependency của sản phẩm thì làm gì?

Factory có thể được constructor-inject dependency và **truyền chúng** cho sản phẩm:

~~~java
public final class ClientFactoryBean implements FactoryBean<Client> {
    private final HttpTransport transport;

    public ClientFactoryBean(HttpTransport transport) {
        this.transport = transport;
    }

    @Override
    public Client getObject() {
        return new Client(transport);
    }

    @Override
    public Class<?> getObjectType() {
        return Client.class;
    }
}
~~~

Đây là snippet minh họa, cần định nghĩa `HttpTransport` và `Client`. Spring DI áp dụng cho **factory**, không tự động tìm field `@Autowired` trong Client vừa được tạo bằng `new`.

Nếu cần Spring wiring cho một object tự tạo, BeanFactory có một số API autowiring/initialization chuyên dụng; nhưng gọi chúng phải hiểu lifecycle và cleanup, không tự cho rằng chúng biến object thành managed bean đầy đủ với automatic destruction. Phần lớn code ứng dụng nên **ưu tiên `@Bean` trả sản phẩm trực tiếp** nếu không có lý do phải có FactoryBean.

### 7.3. BeanPostProcessor không đồng nghĩa destroy callback

Một custom BeanPostProcessor hoặc auto-proxy creator có thể tác động đến sản phẩm; đây là **post-processing sau khi factory đã cấp object**, không có nghĩa Spring sẽ tự gọi `@PreDestroy` hoặc `DisposableBean.destroy()` của sản phẩm khi context close. Hai cơ chế này tách biệt.

## 8. Ai sở hữu sản phẩm và ai phải giải phóng tài nguyên?

Ownership là quyết định thiết kế, không chỉ là một flag của `FactoryBean`.

### Trường hợp A — Factory sở hữu một sản phẩm dùng chung

Ví dụ FactoryBean quản lý một SDK client có connection pool, có một instance dùng suốt vòng đời singleton factory. Factory có thể implement `DisposableBean`:

~~~java
public final class SdkClientFactoryBean
        implements FactoryBean<SdkClient>, DisposableBean {

    private SdkClient client;

    @Override
    public synchronized SdkClient getObject() {
        if (client == null) {
            client = new SdkClient();
        }
        return client;
    }

    @Override
    public Class<?> getObjectType() {
        return SdkClient.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }

    @Override
    public synchronized void destroy() {
        if (client != null) {
            client.close();
        }
    }
}
~~~

Đây là **mẫu minh họa**, cần `SdkClient` thực thi `close()`, import `FactoryBean` và `DisposableBean`. Khi factory là singleton Spring-managed bean, Spring gọi `destroy()` của factory lúc context đóng hợp lệ. Factory kiểm tra client đã được tạo chưa để tránh mở client chỉ để đóng.

### Trường hợp B — Nhiều sản phẩm độc lập

Nếu `getObject()` luôn tạo một object mới và `isSingleton()` trả `false`, factory phải **chọn chính sách sở hữu rõ ràng**:

- **Caller sở hữu:** caller lấy sản phẩm và close bằng `try-with-resources`/`finally` sau thao tác. Factory không cố đóng những object đã trao đi nếu ownership được chuyển.
- **Factory sở hữu:** factory lưu registry có kiểm soát những sản phẩm còn sống, đóng lúc factory shutdown hoặc theo lease/reference-count. Cần thiết kế concurrency, memory và lỗi một close ảnh hưởng close còn lại.
- **Một resource manager bên ngoài sở hữu:** sản phẩm có thể chỉ là handle/borrowed view; chỉ resource manager được phép close. Factory phải diễn đạt ownership bằng API/documentation.

Không có một “finalizer mặc định” của Spring sẽ tự theo dõi và đóng mọi object `getObject()` từng trả về. Đặc biệt, sản phẩm không singleton có thể được sử dụng sau khi factory không còn biết ai giữ reference; vì vậy chuyển quyền đóng cho caller thường là cách dễ hiểu.

### Trường hợp C — Factory là prototype

Ngay cả khi factory implement `DisposableBean`, Spring **không mặc định tự hủy mọi prototype instance** sau khi trao cho caller. Do đó `DisposableBean.destroy()` của factory prototype không được tự động đảm bảo khi context close; thiết kế ownership riêng vẫn cần thiết.

### Trường hợp D — Sản phẩm không giữ tài nguyên

Một value object không có `close`, thread hay unmanaged resource có thể không cần cơ chế dọn dẹp riêng. Không nên thêm `DisposableBean` chỉ cho “đầy đủ ba bước” nếu thực sự không có thứ gì cần release.

## 9. Ví dụ Java 17 hoàn chỉnh: factory quản lý client shared, caller quản lý client không shared

Ví dụ này chạy với **Java 17**, **Maven** và **Spring Framework 6.2.12**, không cần Spring Boot hay HTTP server. Chương trình chứng minh:

1. Spring gọi `InitializingBean.afterPropertiesSet()` của FactoryBean.
2. Dấu `&` lấy chính FactoryBean.
3. Sản phẩm `isSingleton()==true` được tái sử dụng.
4. `isSingleton()==false` cấp hai sản phẩm độc lập trong ví dụ.
5. Caller tự đóng hai sản phẩm non-shared.
6. Khi đóng context, Spring gọi `DisposableBean.destroy()` trên factory singleton; factory chuyển tiếp `close()` tới sản phẩm shared.

Cấu trúc tệp:

~~~text
factorybean-lifecycle/
├── pom.xml
└── src/main/java/example/FactoryBeanLifecycleDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>factorybean-lifecycle</artifactId>
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
~~~

`src/main/java/example/FactoryBeanLifecycleDemo.java`:

~~~java
package example;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.FactoryBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class FactoryBeanLifecycleDemo {

    public static void main(String[] args) {
        Client shared;
        OwnedClientFactoryBean owner;

        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            owner = context.getBean("&ownedClient",
                    OwnedClientFactoryBean.class);
            System.out.println("Factory initialized: " + owner.initialized());

            shared = context.getBean("ownedClient", Client.class);
            Client sharedAgain = context.getBean("ownedClient", Client.class);
            System.out.println("Shared product reused: "
                    + (shared == sharedAgain));

            Client first = context.getBean("freshClient", Client.class);
            Client second = context.getBean("freshClient", Client.class);
            System.out.println("Non-shared products different: "
                    + (first != second));

            System.out.println("Non-shared before close: "
                    + (first.isClosed() || second.isClosed()));

            first.close();
            second.close();
            System.out.println("Non-shared manually closed: "
                    + (first.isClosed() && second.isClosed()));

            System.out.println("Shared before shutdown: "
                    + shared.isClosed());
        }

        System.out.println("Factory destroyed: " + owner.destroyed());
        System.out.println("Shared after shutdown: " + shared.isClosed());
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean("ownedClient")
        public OwnedClientFactoryBean ownedClientFactory() {
            return new OwnedClientFactoryBean();
        }

        @Bean("freshClient")
        public FreshClientFactoryBean freshClientFactory() {
            return new FreshClientFactoryBean();
        }
    }

    public static final class Client implements AutoCloseable {
        private boolean closed;

        public boolean isClosed() {
            return closed;
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    public static final class OwnedClientFactoryBean
            implements FactoryBean<Client>,
                       InitializingBean, DisposableBean {

        private Client client;
        private boolean initialized;
        private boolean destroyed;

        @Override
        public void afterPropertiesSet() {
            initialized = true;
        }

        @Override
        public synchronized Client getObject() {
            if (!initialized) {
                throw new IllegalStateException("Factory not initialized");
            }
            if (client == null) {
                client = new Client();
            }
            return client;
        }

        @Override
        public Class<?> getObjectType() {
            return Client.class;
        }

        @Override
        public boolean isSingleton() {
            return true;
        }

        public boolean initialized() {
            return initialized;
        }

        public boolean destroyed() {
            return destroyed;
        }

        @Override
        public synchronized void destroy() {
            destroyed = true;
            if (client != null) {
                client.close();
            }
        }
    }

    public static final class FreshClientFactoryBean
            implements FactoryBean<Client> {

        @Override
        public Client getObject() {
            return new Client();
        }

        @Override
        public Class<?> getObjectType() {
            return Client.class;
        }

        @Override
        public boolean isSingleton() {
            return false;
        }
    }
}
~~~

Chạy ở thư mục `factorybean-lifecycle`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.FactoryBeanLifecycleDemo
~~~

Stdout từ các câu lệnh `System.out.println` trong chương trình (không tính log Maven hoặc logging riêng của môi trường):

~~~text
Factory initialized: true
Shared product reused: true
Non-shared products different: true
Non-shared before close: false
Non-shared manually closed: true
Shared before shutdown: false
Factory destroyed: true
Shared after shutdown: true
~~~

**Vì sao stdout xác định?**

- Hai FactoryBeans do `@Bean` đăng ký đều là singleton và được container khởi tạo trong giai đoạn refresh. `OwnedClientFactoryBean.afterPropertiesSet()` đặt `initialized=true`; chương trình lấy factory bằng `&ownedClient` sau khi refresh.
- Lần gọi `getBean("ownedClient")` đưa sản phẩm qua cơ chế FactoryBean. `OwnedClientFactoryBean` cache `Client` trong field, đồng thời báo `isSingleton()==true`, nên hai lần lookup trong ví dụ nhận cùng reference.
- `FreshClientFactoryBean.isSingleton()==false` và `getObject()` trả `new Client()` ở mỗi lần gọi. Hai lookup `freshClient` do đó nhận hai object khác nhau. Điều này là tính chất của **implementation cụ thể**, không phải định nghĩa tuyệt đối của mọi FactoryBean trả false.
- Không có code nào tự đóng hai client fresh nếu caller không gọi `close()`. Hai lệnh `first.close()` và `second.close()` minh họa **caller ownership**.
- Khi kết thúc `try-with-resources`, `context.close()` được gọi. Spring destroy chính `OwnedClientFactoryBean`; trong `destroy()`, factory gọi `client.close()`. Sản phẩm shared được đóng **gián tiếp do owner**, không phải vì container tìm một bean definition riêng của `Client` để gọi destroy callback.
- Phép kiểm tra `shared.isClosed()` ngoài context vẫn đọc state của Java object còn được tham chiếu trong method `main`; không dùng client để kết nối nữa sau khi đã đóng.

Đây là chương trình mô phỏng resource lifecycle bằng một cờ `closed`, không tạo socket/network thật. Với client thực, `close()` có thể ném exception, cần quyết định log, propagation, timeout và cleanup của các resource khác khi có nhiều clients.

## 10. Nếu cần `@PreDestroy` của sản phẩm thì làm gì?

Một lỗi suy luận phổ biến:

~~~java
public final class ExternalClient {
    @PreDestroy
    public void cleanup() {
        closeNetworkResources();
    }
}
~~~

Nếu `ExternalClient` chỉ được `FactoryBean.getObject()` tạo bằng `new` và trả về, annotation đó **không tự đảm bảo Spring sẽ gọi cleanup** lúc context shutdown.

Các cách xử lý:

1. **Factory sở hữu:** FactoryBean là singleton, implement `DisposableBean` hoặc khai báo destroy callback của factory, gọi `product.close()`.
2. **Caller sở hữu:** với sản phẩm ngắn hạn, caller dùng `try-with-resources`/`finally` để close đúng lúc.
3. **Đăng ký sản phẩm thành bean thường:** nếu cần đầy đủ Spring DI/init/destroy semantics và không thực sự cần `FactoryBean`, dùng `@Bean(initMethod = "...", destroyMethod = "close")` trả sản phẩm trực tiếp.
4. **Resource manager sở hữu:** product là view/lease; chỉ manager đóng underlying resource theo lifecycle của manager.

Không nên vừa yêu cầu factory tự đóng sản phẩm, vừa yêu cầu caller tùy ý đóng sản phẩm dùng chung khi đang có người sử dụng khác. Việc **double close**, đóng quá sớm và use-after-close là lỗi resource ownership thực tế.

### Khi factory chưa hề tạo product

Factory singleton có thể được Spring khởi tạo và hủy mà `getObject()` chưa từng được gọi. `destroy()` cần xử lý an toàn `product==null`, không tạo một client mới chỉ để gọi `close()`.

### Khi product không singleton

Factory có thể không còn biết tất cả products đã cấp. Để factory quản lý tất cả phải có tracking registry và chính sách eviction/cleanup, tránh giữ references mãi gây memory leak. Nếu không cần tracking, chuyển ownership rõ ràng cho caller.

## 11. FactoryBean và BeanPostProcessor: không đơn giản là “không xử lý”

Spring có thể áp dụng `postProcessAfterInitialization` của các BeanPostProcessors lên product do `getObject()` trả về, ví dụ để wrapping/proxying. Nhưng quá trình đó **không phải toàn bộ vòng đời** của một bean thông thường.

Bảng phân biệt:

| Hoạt động | FactoryBean instance | Product do `getObject()` trả về |
| --- | --- | --- |
| Spring tạo instance từ bean definition | Có | Thông thường do FactoryBean tạo |
| Constructor/factory method DI của chính object | Có theo bean definition | Do logic FactoryBean tự làm |
| Setter/field autowiring tự động | Có, nếu cấu hình phù hợp | Không mặc định chỉ vì được trả về |
| Aware callbacks | Có, nếu factory implement | Không mặc định |
| `@PostConstruct`/`InitializingBean` của object | Có | Không mặc định |
| `BeanPostProcessor` sau initialization | Có | Có thể có, tùy BeanFactory/cơ chế |
| Spring cache sản phẩm shared | Factory instance theo bean scope | Có thể cache theo `isSingleton()` |
| `@PreDestroy`/`DisposableBean` trên object | Theo scope factory | Không tự động |
| Dọn resource bên dưới | Factory phải tự cleanup tài nguyên mình sở hữu | Factory/caller/resource manager theo ownership |

Không nên viết `@Autowired` fields trong product rồi mong Spring tự inject bởi product là “bean nhìn thấy qua getBean”. Nếu cần một dependency `Transport` trong product, inject `Transport` vào **FactoryBean** và truyền vào constructor của product; hoặc thay kiến trúc để product thực sự là bean được Spring quản lý trực tiếp.

### Type prediction có thể xảy ra rất sớm

`getObjectType()` có thể bị gọi **trước khi factory hoàn toàn initialized**, kể cả trong giai đoạn autowiring/by-type lookup. Vì vậy không mở connection hay tạo product chỉ để xác định type. Đối với một type luôn biết trước:

~~~java
@Override
public Class<?> getObjectType() {
    return ExternalClient.class;
}
~~~

Đây là method snippet. Nếu không biết type, `null` là được phép nhưng Spring có thể không nhận diện sản phẩm trong by-type autowiring. Không “khắc phục” bằng cách ép mọi `getObjectType()` tạo sản phẩm.

## 12. Thread safety và cache ownership

FactoryBean thường được nhiều thread truy cập gián tiếp qua BeanFactory. Nếu factory tự cache singleton product, logic lazy creation cần thread safety.

Ví dụ:

~~~java
private Client client;

@Override
public synchronized Client getObject() {
    if (client == null) {
        client = new Client();
    }
    return client;
}
~~~

Đây là snippet. `synchronized` đảm bảo factory không tự tạo hai object khi hai thread gọi trực tiếp `getObject()`. Trong đường truy cập thông thường Spring cũng có cơ chế đồng bộ hóa singleton creation/cache; tuy nhiên **không nên dựa hoàn toàn vào cache Spring để bảo vệ mutable state riêng của factory khi có code gọi trực tiếp factory**.

Nếu client thật có phương thức không thread-safe, việc factory trả cùng singleton **không làm client trở nên thread-safe**. Đặt cache ở factory chỉ khi product phù hợp để chia sẻ hoặc được bảo vệ qua pooling/synchronization đúng.

Với nhiều sản phẩm cần release, registry theo dõi phải xử lý race giữa `getObject()` và `destroy()`, exception khi đóng, và không giữ mãi reference của product không shared đã được caller đóng. Trách nhiệm cuối cùng phải nằm ở một owner duy nhất hoặc có hợp đồng chia sẻ rõ.

## 13. Đặt FactoryBean ở scope prototype có giải quyết cleanup không?

Không. Prototype scope của **factory** khiến Spring có thể tạo FactoryBean instance mới theo lookup, nhưng Spring không tự chủ động thu hồi và gọi destroy callback cho mọi prototype factory sau khi cấp chúng. Điều đó có thể làm resource leak nghiêm trọng hơn nếu mỗi prototype factory sở hữu một client.

Hai vấn đề tách biệt:

- **Cần product mới mỗi job:** một singleton FactoryBean với `isSingleton=false` và caller ownership có thể đủ.
- **Cần factory instance mới mỗi job:** mới cần nghĩ đến prototype factory, và phải tự quản lý cả factory instance lẫn sản phẩm.

Với use case “đối tượng thay đổi mỗi lần yêu cầu”, trước khi viết FactoryBean hãy cân nhắc bean `@Scope("prototype")` thông thường hoặc `ObjectProvider<T>`. FactoryBean hợp lý khi có logic tạo SDK/proxy object phức tạp, type prediction, đặc thù integration hoặc cần cung cấp product qua một bean definition.

## 14. Lỗi phổ biến và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `getBean("x")` trả product thay vì factory | FactoryBean mặc định được dereference thành sản phẩm | Dùng `getBean("&x")` nếu cần factory |
| Không thấy `@PreDestroy` trên product chạy | Spring chỉ quản lý destroy của FactoryBean | Factory `DisposableBean.destroy` gọi product.close hoặc đổi sang bean thường |
| Context close rồi resource vẫn mở | Không xác định product owner | Thiết kế factory/caller cleanup tường minh |
| Factory singleton trả product không đồng nhất nhưng `isSingleton=true` | Container có thể cache product đầu tiên | Sửa `isSingleton=false` hoặc tự cache cùng reference |
| Product non-singleton bị leak | Caller quên close; factory không track | `try-with-resources`/`finally` hoặc registry ownership |
| `getObjectType()==null` gây lỗi autowiring | Spring không dự đoán product type | Trả class đúng, không tạo product nặng |
| `getObjectType()` chạy khi field init còn null | Type prediction có thể xảy ra rất sớm | Dựa trên type metadata ổn định |
| Sản phẩm có field `@Autowired` nhưng null | Product không được wiring theo full bean lifecycle | Factory inject rồi truyền dependency |
| Product state khác kỳ vọng | Nhầm scope của factory với isSingleton product | Kiểm tra hai trục cấu hình |
| Factory scope prototype nhưng destroy không chạy | Spring không tự destroy prototype | Caller hoặc owner phải release |
| Sản phẩm chung bị đóng giữa request | Caller tự đóng shared product | Factory/resource manager giữ ownership shared |
| Double-close hoặc race khi shutdown | Nhiều owner, thiếu synchronization | Một ownership contract và stop flow rõ |
| Tưởng `@Bean` method giống FactoryBean | Hai cơ chế có semantics khác | Nếu muốn full bean lifecycle, đăng ký product trực tiếp |
| Autowiring chọn sai bean cùng type | Nhiều product cùng type hoặc metadata type không đúng | Dùng tên/qualifier/`@Primary` và `getObjectType` chính xác |
| Client mở connection trong `getObjectType()` | Type lookup có side effect | Return class thuần, mở resource trong `getObject` |

## 15. Cách kiểm chứng bằng test

### 15.1. FactoryBean contract test

Một unit test thuần Java cho factory có thể kiểm chứng:

- `getObjectType()` trả class mong đợi, không tạo connection/client.
- `isSingleton()==true` đi kèm `getObject()` trả reference ổn định khi factory tự cache.
- `isSingleton()==false` và thiết kế prototype-like tạo independent objects khi cần.
- `destroy()` chỉ close resource factory sở hữu, không cố close nhầm caller-owned resource.
- `destroy()` an toàn nếu product chưa từng được tạo.
- Hai luồng gọi `getObject()` không vi phạm cache/thread safety nếu factory support concurrent use.

### 15.2. Spring integration test

Dùng `AnnotationConfigApplicationContext` rồi xác nhận:

~~~java
Object product = context.getBean("managedClient");
Object factory = context.getBean("&managedClient");

if (!(factory instanceof FactoryBean<?>)) {
    throw new AssertionError("Expected FactoryBean");
}
if (product == factory) {
    throw new AssertionError("Expected distinct product and factory");
}
~~~

Đây là snippet, cần `context` đã tạo, import `FactoryBean` và một bean definition `managedClient` thực tế.

Tiếp theo đóng context và kiểm tra owner cleanup đã được gọi. Không phải chỉ assert `context.close()` không ném lỗi: tài nguyên bên dưới cũng phải về trạng thái closed.

### 15.3. Test product lifecycle không được tự suy diễn

Nếu sản phẩm có `@PostConstruct`/`@PreDestroy`, cần test thực tế xem bạn có tự xử lý những annotation đó hoặc đã đăng ký sản phẩm thành bean thường hay không. Chỉ vì `context.getBean("managedClient")` trả Client không có nghĩa mọi annotation lifecycle trên Client sẽ chạy như một bean definition độc lập.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `context.getBean("client")` và `context.getBean("&client")` khác nhau thế nào khi bean là FactoryBean?

**Đáp án:** Lời gọi thứ nhất lấy sản phẩm do FactoryBean cung cấp; lời gọi thứ hai lấy chính FactoryBean instance.

**Câu 2.** Một FactoryBean singleton implement `DisposableBean`. Sản phẩm của nó implement `AutoCloseable`. Khi đóng context, Spring tự gọi `product.close()`?

**Đáp án:** Không chỉ vì product implement AutoCloseable. Container destroy factory; factory phải chuyển tiếp việc đóng sản phẩm nếu nó là owner, hoặc có owner khác xử lý.

**Câu 3.** `FactoryBean.isSingleton() == true` có nghĩa FactoryBean bean definition chắc chắn singleton?

**Đáp án:** Không. `isSingleton()` nói về sản phẩm; scope của FactoryBean do bean definition/container quản lý riêng.

**Câu 4.** `isSingleton() == false` có bảo đảm hai lần `getBean("client")` trả hai Java objects khác identity?

**Đáp án:** Không tuyệt đối. Contract không-shared không đồng nghĩa bảo đảm independent product references với mọi factory implementation. Factory có thể tự quản lý cache; `SmartFactoryBean.isPrototype()` cho biết thêm semantics nếu dùng.

**Câu 5.** `getObjectType()` có thể gọi trước initialization của FactoryBean không?

**Đáp án:** Có. Vì vậy nên trả type dự đoán từ metadata ổn định, tránh phụ thuộc state init hay mở resource tại đây.

**Câu 6.** Product từ FactoryBean có bao giờ được BeanPostProcessor xử lý không?

**Đáp án:** Có thể được xử lý sau initialization để wrapping/proxying theo BeanFactory. Nhưng không nên nhầm bước này với full autowiring/init/destroy lifecycle như bean thông thường.

**Câu 7.** Một FactoryBean singleton trả một client mới mỗi lần `getObject()` và quên override `isSingleton()`. Có vấn đề gì?

**Đáp án:** Mặc định `isSingleton()` là true. Spring có thể cache client đầu, khiến lookup qua container không tương đương direct getObject(). Phải chọn contract nhất quán.

**Câu 8.** Factory tạo nhiều clients không shared. Ai phải close?

**Đáp án:** Theo ownership contract: thường caller sau khi dùng; hoặc factory/resource manager nếu nó chủ động theo dõi và chịu trách nhiệm cleanup. Không thể dựa vào container tự gọi destroy từng product.

**Câu 9.** Có nên dùng FactoryBean cho mọi object phức tạp?

**Đáp án:** Không. Nếu method `@Bean` trả trực tiếp product đủ rõ và bạn muốn Spring quản lý full lifecycle, `@Bean` thường đơn giản và ít cạm bẫy hơn.

## 17. Checklist thiết kế production

1. Xác định FactoryBean có thực sự cần thiết thay vì `@Bean` hoặc factory Java thường.
2. Phân biệt factory bean name và product lookup; tài liệu hóa `&beanName` khi cần debug.
3. `getObjectType()` trả class đúng, nhẹ, không phụ thuộc việc init đã hoàn thành.
4. Chọn `isSingleton()` nhất quán với identity/lifetime của sản phẩm.
5. Đọc scope của **factory bean definition**, không chỉ flag về sản phẩm.
6. Có mục đích rõ cho việc cache sản phẩm hay tạo product mới ở mỗi lookup.
7. Nếu product là resource, khai báo **owner duy nhất** và thời điểm `close()`.
8. Với singleton product, factory singleton có `DisposableBean`/destroy callback chuyển tiếp cleanup nếu factory sở hữu.
9. Với non-shared product, caller sử dụng `try-with-resources` hoặc factory có tracking phù hợp.
10. Nếu FactoryBean là prototype, không dựa vào automatic destroy callback của Spring cho từng instance.
11. Không giả định `@Autowired`, `@PostConstruct` hay `@PreDestroy` của product tự vận hành như regular bean.
12. Kiểm tra product có thể được post-processed/proxied; không nhầm proxy identity với raw target.
13. Đảm bảo thread safety nếu factory cache product hoặc trực tiếp nhận concurrent calls.
14. Test cả trường hợp product chưa tạo, tạo nhiều lần, factory destroy khi context close, double-close và exception từ cleanup.
15. Đừng giữ product đã close để phục vụ request khác; định nghĩa lifecycle và readiness rõ ràng.

## 18. Tài liệu tham khảo chính thức

- [Spring Framework — Customizing Instantiation Logic with a FactoryBean](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html#beans-factory-extension-factorybean)
- [Spring Framework — BeanFactory API](https://docs.spring.io/spring-framework/reference/core/beans/beanfactory.html)
- [Spring Framework — Customizing the Nature of a Bean: Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework Javadoc — FactoryBean](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/FactoryBean.html)
- [Spring Framework Javadoc — SmartFactoryBean](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/SmartFactoryBean.html)
- [Spring Framework Javadoc — DisposableBean](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/DisposableBean.html)

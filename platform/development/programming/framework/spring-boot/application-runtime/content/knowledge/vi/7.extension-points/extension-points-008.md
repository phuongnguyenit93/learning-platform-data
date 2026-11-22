# BootstrapRegistry và ConfigurableBootstrapContext trước khi có bean

## 1. Vì sao Spring Boot cần một bootstrap context?

Trong một ứng dụng Spring Boot, có những công việc phải thực hiện **trước khi `ApplicationContext` được tạo và các bean thông thường được khởi tạo**. Ví dụ: nạp cấu hình từ một dịch vụ bên ngoài, xây dựng client truy cập kho bí mật để đọc thuộc tính cấu hình, hoặc dùng chung một đối tượng tốn kém trong giai đoạn chuẩn bị `Environment`.

Ở thời điểm rất sớm này, mã nguồn **không thể dựa vào `@Autowired`, `@Bean`, `ApplicationContext.getBean()` hoặc `BeanFactory` đã refresh** để lấy đối tượng. Spring Boot cung cấp một cơ chế riêng:

- **`BootstrapRegistry`**: nơi *đăng ký* đối tượng hoặc nhà cung cấp đối tượng theo khóa `Class<T>`.
- **`BootstrapContext`**: nơi *lấy* đối tượng đã đăng ký khi cần, thông thường tạo lười (lazy) theo `InstanceSupplier<T>`.
- **`ConfigurableBootstrapContext`**: một interface kết hợp cả hai vai trò trên (`extends BootstrapRegistry, BootstrapContext`), cho phép đọc và đăng ký trong giai đoạn bootstrap.
- **`BootstrapRegistryInitializer`**: callback dùng để khai báo registration từ rất sớm, trước khi bootstrap registry được dùng.
- **`DefaultBootstrapContext`**: triển khai mặc định của `ConfigurableBootstrapContext` trong Spring Boot.

Mục tiêu chính là **chia sẻ dependency khởi động có kiểm soát khi chưa có bean Spring thông thường**. Registry này không thay thế container IoC, không thực hiện component scan, không quản lý `@Autowired` và không tự biến một đối tượng thành bean khi context chính xuất hiện.

### Tình huống thực tế

Giả sử một hệ thống muốn đọc cấu hình runtime từ dịch vụ cấu hình riêng. Quá trình cần một `ConfigurationClient` trước khi có `ApplicationContext`. Nếu nhiều thành phần giai đoạn bootstrap cần dùng cùng client, cách tạo `new ConfigurationClient(...)` lặp lại có thể khiến tài nguyên bị mở nhiều lần và trạng thái bị phân tán. Bootstrap registry cho phép đăng ký supplier theo type rồi chia sẻ instance khi có người gọi `get()`.

Điểm cần nhớ: **bootstrap context tồn tại trong giai đoạn chuẩn bị ứng dụng, còn ApplicationContext quản lý vòng đời bean của ứng dụng**. Hai cơ chế có thời điểm và phạm vi khác nhau.

## 2. Vị trí trong chuỗi khởi động SpringApplication

Trình tự khái quát của `SpringApplication.run(...)` khi chạy Spring Boot 3.3:

~~~text
main()
  |
  v
Tạo SpringApplication và cấu hình bootstrap registry initializers
  |
  v
Tạo ConfigurableBootstrapContext (thường DefaultBootstrapContext)
  |
  +-- Gọi BootstrapRegistryInitializer.initialize(registry)
  |     +-- register / registerIfAbsent các InstanceSupplier
  |
  +-- Phát các sự kiện khởi động sớm
  +-- Chuẩn bị Environment và áp dụng Config Data
  |     +-- Thành phần được phép truy cập bootstrap context
  |     +-- get(Type.class) có thể gọi supplier lần đầu
  |
  +-- Tạo ApplicationContext và chuẩn bị Environment
  +-- Áp dụng ApplicationContextInitializer
  +-- Đóng bootstrap context, thông báo BootstrapContextClosedEvent
  |     +-- Có thể chuyển một đối tượng cần thiết sang BeanFactory
  |
  +-- Nạp cấu hình/bean definitions, refresh ApplicationContext
  |     +-- Xử lý BeanFactoryPostProcessor / BeanPostProcessor
  |     +-- Khởi tạo bean thông thường và các dependency
  |
  +-- ApplicationStartedEvent, chạy các runner
  +-- ApplicationReadyEvent
  v
Ứng dụng sẵn sàng nếu khởi động thành công
~~~

Đây là **sơ đồ logic rút gọn**; trình tự chi tiết giữa một số callback sự kiện, `EnvironmentPostProcessor`, `ConfigData` và việc nạp định nghĩa có thể có các bước bổ sung. Mốc quan trọng nhất là bootstrap registry được tạo **trước khi `ApplicationContext` được chuẩn bị và refresh**. Sự kiện đóng bootstrap context xuất hiện khi `ApplicationContext` đã được chuẩn bị, nhưng **chưa có nghĩa context đã refresh hay ứng dụng đã sẵn sàng**.

Theo API Spring Boot, `ApplicationEnvironmentPreparedEvent` cho phép truy cập `ConfigurableBootstrapContext` qua `getBootstrapContext()` trong lúc chuẩn bị môi trường. Các thành phần config-data tích hợp cũng dùng cơ chế này cho dependency khởi động.

Không nhầm với những mốc sau:

| Mốc | Đã có gì? | Không nên giả định |
| --- | --- | --- |
| `BootstrapRegistryInitializer.initialize()` | Registry để đăng ký type và supplier | Đã có bean nghiệp vụ hoặc một `ApplicationContext` đang chạy |
| Chuẩn bị `Environment` / `ApplicationEnvironmentPreparedEvent` | `Environment` và bootstrap context | `@Bean` đã tạo, `@Autowired` dùng được |
| `BootstrapContextClosedEvent` | `ApplicationContext` đã được *chuẩn bị* | `ApplicationContext` đã refresh, runner đã chạy |
| `ApplicationStartedEvent` | Context đã refresh | Các runner hoàn thành |
| `ApplicationReadyEvent` | Runner đã được thực thi thành công theo lifecycle Boot | Mọi tác vụ nghiệp vụ bất đồng bộ đã xong |

Bước đăng ký BPP trong `ApplicationContext.refresh()` diễn ra muộn hơn giai đoạn bootstrap registry. Vì vậy, không nên trộn lẫn **bootstrap registry** với **BeanFactory registry** hay `BeanPostProcessor`.

## 3. Quan hệ giữa các interface

Các interface liên quan có thể hình dung như sau:

~~~text
       BootstrapRegistry          BootstrapContext
       -----------------          ----------------
       register(...)              get(...)
       registerIfAbsent(...)      getOrElse(...)
       isRegistered(...)          getOrElseSupply(...)
       addCloseListener(...)      getOrElseThrow(...)
                   \              /
                    \            /
               ConfigurableBootstrapContext
                         ^
                         |
                 DefaultBootstrapContext
~~~

Ở đây:

- `BootstrapRegistry` là API dành cho **bên đăng ký**.
- `BootstrapContext` là API dành cho **bên sử dụng** những gì đã được đăng ký.
- `ConfigurableBootstrapContext` có cả hai tập phương thức. Không nhất thiết phải truyền interface tổng hợp vào mọi thành phần; chọn kiểu tham số hẹp nhất phản ánh đúng trách nhiệm.

### 3.1. Đăng ký theo type, không phải tên bean

Ví dụ:

~~~java
registry.registerIfAbsent(
    EarlyClient.class,
    context -> new EarlyClient("dev")
);
~~~

Đây là **đoạn minh họa nằm bên trong một `BootstrapRegistryInitializer`**, chưa phải chương trình độc lập. `EarlyClient` đại diện cho một class do ứng dụng tự viết.

Registry dùng **`Class<T>` làm khóa**. Với cùng khóa `EarlyClient.class`, một registry chỉ giữ **một registration tại một thời điểm**. Khác với Spring BeanFactory, nó không cung cấp cơ chế phân biệt nhiều bean cùng loại bằng các tên và `@Qualifier` theo kiểu IoC.

Nếu cần hai client cùng Java type nhưng cấu hình khác nhau, hãy dùng hai loại wrapper/marker type có ý nghĩa riêng hoặc thiết kế một đối tượng quản lý tập client; đừng xem registry là một map theo tên bean.

### 3.2. register và registerIfAbsent

- `register(type, supplier)`: đăng ký hoặc thay thế supplier nếu registration hiện có còn cho phép thay thế. Với singleton đã được truy cập/khởi tạo, việc thay registration có giới hạn theo contract; đừng coi `register` là phép ghi đè đối tượng tùy ý.
- `registerIfAbsent(type, supplier)`: chỉ đăng ký nếu type chưa có registration. Đây là lựa chọn phù hợp khi thư viện muốn cung cấp **mặc định có thể được ứng dụng hoặc tích hợp khác thay thế trước đó**.
- `isRegistered(type)`: kiểm tra type đã đăng ký chưa; **không chứng minh supplier đã được gọi hoặc instance khác null**.
- `getRegisteredInstanceSupplier(type)`: xem supplier đã đăng ký, có thể trả về null nếu chưa có; thường chỉ cần cho tích hợp muốn điều chỉnh registration.

Lưu ý phân biệt registration và instance:

~~~text
register(EarlyClient.class, supplier) -> lưu công thức tạo
get(EarlyClient.class)               -> lấy (có thể kích hoạt tạo lần đầu)
get(EarlyClient.class) lần nữa        -> dùng lại nếu là SINGLETON
~~~

### 3.3. Lazy creation và scope

`BootstrapRegistry.InstanceSupplier<T>` là functional interface. Phương thức `T get(BootstrapContext context)` nhận context bootstrap, nên supplier có thể đọc các đối tượng bootstrap khác nếu đã đăng ký và không tạo vòng phụ thuộc.

Hai scope được định nghĩa:

| Scope | Ý nghĩa |
| --- | --- |
| `BootstrapRegistry.Scope.SINGLETON` | Supplier được gọi tối đa một lần cho instance, các lần `get` dùng lại cùng instance |
| `BootstrapRegistry.Scope.PROTOTYPE` | Supplier được gọi mỗi lần cần instance mới |

API `InstanceSupplier.withScope(...)` cho phép chỉ định scope, ví dụ:

~~~java
registry.register(
    EarlyClient.class,
    (BootstrapRegistry.InstanceSupplier<EarlyClient>)
        context -> new EarlyClient("demo")
);
~~~

Đây là một registration minh họa về generic lambda, **không cần cast khi compiler đã suy luận type từ tham số `register`**. Trong code thông thường có thể viết trực tiếp `context -> new EarlyClient("demo")`. Khi thực sự cần thay scope, dùng một supplier có kiểu phù hợp và gọi `.withScope(BootstrapRegistry.Scope.PROTOTYPE)`.

Không lấy `PROTOTYPE` chỉ để “đỡ phải quản lý lifecycle”: mỗi lần tạo có thể phát sinh resource mới, và việc đóng chúng vẫn là trách nhiệm của code tương ứng.

## 4. Đọc dữ liệu từ bootstrap context

Bên sử dụng có thể gọi:

~~~java
BootstrapContext bootstrap = event.getBootstrapContext();
EarlyClient client = bootstrap.get(EarlyClient.class);
~~~

Ví dụ trên là **đoạn minh họa trong một `ApplicationEnvironmentPreparedEvent` listener**, không phải tệp Java độc lập. Với Spring Boot 3.3, `getBootstrapContext()` trả `ConfigurableBootstrapContext`, là subtype của `BootstrapContext`.

Các phương thức phổ biến:

| Phương thức | Khi dùng |
| --- | --- |
| `get(Foo.class)` | Type bắt buộc đã đăng ký; có thể kích hoạt tạo instance |
| `getOrElse(Foo.class, fallback)` | Nếu type không được đăng ký, dùng giá trị dự phòng đã có |
| `getOrElseSupply(Foo.class, supplier)` | Nếu không được đăng ký, gọi supplier dự phòng |
| `getOrElseThrow(Foo.class, exceptionSupplier)` | Nếu không được đăng ký, ném lỗi theo chính sách của ứng dụng |
| `isRegistered(Foo.class)` | Kiểm tra có registration trước khi truy cập |

Theo Javadoc, `get` có thể ném `IllegalStateException` nếu type chưa đăng ký. **Một registration hợp lệ vẫn có thể cung cấp null**, vì vậy đừng mặc định `isRegistered` đồng nghĩa “có đối tượng khác null, đang kết nối được và sẵn sàng”.

`getOrElse(...)` không biến giá trị fallback thành một registration chính thức trừ khi bạn chủ động đăng ký; hãy phân biệt truy cập và cấu hình registry.

## 5. Ví dụ đầy đủ Java 17+ (Spring Boot 3.3.x)

Ví dụ này trực tiếp chứng minh bốn cơ chế:

1. `BootstrapRegistryInitializer` đăng ký một supplier trước khi Spring tạo bean.
2. `ApplicationEnvironmentPreparedEvent` truy cập `ConfigurableBootstrapContext` và khiến supplier được gọi lần đầu.
3. `BootstrapContextClosedEvent` cung cấp thời điểm bàn giao instance sang BeanFactory đã chuẩn bị.
4. `ApplicationRunner` nhận instance được bàn giao qua constructor/method dependency injection, sau khi context refresh.

Để các mốc dễ quan sát, ví dụ dùng `WebApplicationType.NONE`, không mở HTTP server và không cần cơ sở dữ liệu.

### 5.1. Cấu trúc dự án

Dùng Maven và Java 17+. Tạo đúng hai tệp:

~~~text
bootstrap-registry-demo/
├─ pom.xml
└─ src/
   └─ main/
      └─ java/
         └─ com/example/bootstrapdemo/
            └─ BootstrapDemoApplication.java
~~~

**Tệp `pom.xml`:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>bootstrap-registry-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ví dụ cố định Spring Boot **3.3.13** để các import nhất quán; cần Maven và JDK 17+ được cấu hình đúng. Nếu dùng bản patch khác trong cùng nhánh 3.5, kiểm tra dependency tương ứng trước khi đổi số phiên bản.

### 5.2. Chương trình Java hoàn chỉnh

**Tệp `src/main/java/com/example/bootstrapdemo/BootstrapDemoApplication.java`:**

~~~java
package com.example.bootstrapdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BootstrapDemoApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                BootstrapDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        // (1) Đăng ký trước khi ApplicationContext/bean được khởi tạo.
        app.addBootstrapRegistryInitializer(registry -> {
            System.out.println("01_REGISTER_SUPPLIER");

            registry.registerIfAbsent(
                    EarlyToken.class,
                    bootstrapContext -> {
                        System.out.println("03_CREATE_EARLY_TOKEN");
                        return new EarlyToken("demo-key");
                    }
            );

            // (3) Khi bootstrap context đóng, context chính đã
            // được chuẩn bị; bàn giao instance cho BeanFactory.
            registry.addCloseListener(event -> {
                EarlyToken token = event.getBootstrapContext()
                        .get(EarlyToken.class);

                event.getApplicationContext()
                        .getBeanFactory()
                        .registerSingleton("earlyToken", token);

                System.out.println("05_BRIDGED_TO_BEAN_FACTORY");
            });
        });

        // (2) Listener được khai báo trước run, vì sự kiện này
        // xảy ra trước khi các bean thông thường tồn tại.
        app.addListeners(
                (ApplicationListener<ApplicationEnvironmentPreparedEvent>)
                        event -> {
                            System.out.println("02_ENVIRONMENT_READY");

                            EarlyToken token = event
                                    .getBootstrapContext()
                                    .get(EarlyToken.class);

                            System.out.println(
                                    "04_BOOTSTRAP_READ=" + token.value());
                        }
        );

        app.run(args);
    }

    // (4) Chỉ tới giai đoạn context/runner thông thường,
    // Spring mới inject instance đã được đăng ký vào BeanFactory.
    @Bean
    ApplicationRunner printResult(EarlyToken token) {
        return args -> System.out.println(
                "06_RUNNER_BEAN=" + token.value());
    }

    public record EarlyToken(String value) {
    }
}
~~~

Những import trên thuộc Spring Boot 3.3: `SpringApplication`, `WebApplicationType`, `ApplicationRunner` ở `org.springframework.boot`; event ở `org.springframework.boot.context.event`; listener và `@Bean` ở Spring Framework.

**Điểm chính của chương trình:**

- `registerIfAbsent(EarlyToken.class, ...)` chỉ lưu supplier, nên không in `03_CREATE_EARLY_TOKEN` ngay khi đăng ký.
- `ApplicationEnvironmentPreparedEvent` xuất hiện trong giai đoạn `Environment` đã có, `ApplicationContext` chưa tạo. Listener lấy `ConfigurableBootstrapContext`, sau đó `get(EarlyToken.class)` kích hoạt supplier.
- Khi close listener gọi `get(EarlyToken.class)` lần nữa, instance singleton đã tạo được dùng lại. Không có dòng `03_CREATE_EARLY_TOKEN` thứ hai.
- `registerSingleton("earlyToken", token)` đưa instance vào singleton registry của BeanFactory chính. Sau khi refresh, method `@Bean printResult(EarlyToken token)` có thể nhận instance đó qua dependency injection.
- Vì đặt `WebApplicationType.NONE`, chương trình có thể kết thúc sau khi runner chạy, không có HTTP server cần giữ tiến trình sống.

### 5.3. Chạy chương trình

Từ thư mục chứa `pom.xml`:

~~~bash
# Yêu cầu Maven đã được cài đặt và Java 17+ trên PATH
mvn spring-boot:run
~~~

Hoặc tạo JAR rồi chạy:

~~~bash
mvn package
java -jar target/bootstrap-registry-demo-0.0.1-SNAPSHOT.jar
~~~

Trong output, **sáu dòng được in bởi code ví dụ** có thứ tự sau (log Spring Boot/Maven có thể xen kẽ, phụ thuộc môi trường):

~~~text
01_REGISTER_SUPPLIER
02_ENVIRONMENT_READY
03_CREATE_EARLY_TOKEN
04_BOOTSTRAP_READ=demo-key
05_BRIDGED_TO_BEAN_FACTORY
06_RUNNER_BEAN=demo-key
~~~

Nếu dùng công cụ phát triển tạo project bằng Spring Initializr, Maven Wrapper có thể được cung cấp; khi đó dùng `./mvnw spring-boot:run` (Linux/macOS) hoặc `.\mvnw.cmd spring-boot:run` (PowerShell).

### 5.4. Vì sao output chứng minh ranh giới bootstrap?

`01_REGISTER_SUPPLIER` và `02_ENVIRONMENT_READY` diễn ra trước khi bean `printResult` được tạo. Supplier chỉ sinh instance ở `03_CREATE_EARLY_TOKEN`, và listener nhận instance ở `04_BOOTSTRAP_READ`. Khi bootstrap context được đóng, callback `05_BRIDGED_TO_BEAN_FACTORY` chạy lúc context ứng dụng đã được chuẩn bị. Cuối cùng, `06_RUNNER_BEAN` cho thấy **bean/runner thông thường đã dùng được cùng instance**.

Đây là một ví dụ minh họa **bàn giao tường minh**. Không có hành vi “tự chuyển tất cả registration thành bean”: nếu xóa `registerSingleton(...)` mà vẫn đòi inject `EarlyToken`, context có thể không tạo được runner do không có bean thích hợp.

### 5.5. Lưu ý về registerSingleton và lifecycle

`registerSingleton(...)` đăng ký **một instance đã có**, không đi qua toàn bộ quá trình tạo bean thông thường như việc đăng ký `BeanDefinition` rồi để Spring dựng đối tượng. Vì vậy **đừng mặc định rằng instance được chuyển sang bằng cách này sẽ tự nhận đủ constructor injection, `@PostConstruct`, bean post-processing hoặc destroy callback như bean do factory tạo**.

Trong ví dụ, `EarlyToken` chỉ là một record bất biến, không phụ thuộc các lifecycle hook, nên cách bàn giao đơn giản là phù hợp. Với resource thực như HTTP client, connection pool hoặc đối tượng cần đóng, phải thiết kế quyền sở hữu và lifecycle dọn dẹp rõ ràng. Nếu đối tượng cần đầy đủ chuỗi xử lý của bean Spring, cân nhắc đăng ký bean definition/factory qua đúng extension point của ApplicationContext thay vì đưa singleton tạo sẵn vào một cách tùy tiện.

## 6. Những cách đăng ký BootstrapRegistryInitializer

### 6.1. Đăng ký bằng SpringApplication

Đây là cách rõ nhất cho một ứng dụng tự kiểm soát `main()`:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addBootstrapRegistryInitializer(registry -> {
    registry.registerIfAbsent(
            MyEarlyDependency.class,
            context -> new MyEarlyDependency()
    );
});
app.run(args);
~~~

Đoạn trên **chỉ minh họa ý tưởng**, chưa độc lập: `MyApplication`, `MyEarlyDependency` là các class giả định và cần import `SpringApplication`. `SpringApplicationBuilder` cũng có phương thức `addBootstrapRegistryInitializer(...)` để làm việc tương tự với cú pháp builder.

### 6.2. Tích hợp đóng gói thư viện

Thư viện hỗ trợ sớm có thể cung cấp một class thực thi:

~~~java
public final class MyBootstrapInitializer
        implements BootstrapRegistryInitializer {

    @Override
    public void initialize(BootstrapRegistry registry) {
        registry.registerIfAbsent(
                MyEarlyDependency.class,
                context -> new MyEarlyDependency()
        );
    }
}
~~~

Đây là **mã minh họa chưa độc lập**, thiếu import và định nghĩa `MyEarlyDependency`. Với Spring Boot 3.3, `BootstrapRegistryInitializer` và `BootstrapRegistry` thuộc `org.springframework.boot`.

Nếu muốn được phát hiện thông qua cơ chế `SpringFactoriesLoader`, thư viện có thể khai báo class triển khai trong `META-INF/spring.factories` theo khóa tương ứng của Spring Boot 3:

~~~properties
org.springframework.boot.BootstrapRegistryInitializer=com.example.bootstrap.MyBootstrapInitializer
~~~

Đường dẫn và tên class phải khớp đúng với package thực tế; class cần constructor phù hợp để được nạp. Trong ứng dụng đã trực tiếp thêm initializer qua `SpringApplication`, không cần thêm một registration trùng trong `spring.factories`. Trong môi trường nhiều auto-configuration, tránh phụ thuộc vào một thứ tự ngầm định giữa các initializer không được quy định rõ.

**Không nhầm** `spring.factories` cho một SPI đặc thù với danh sách `AutoConfiguration.imports` của cơ chế auto-configuration thông thường: chúng tham gia **những giai đoạn khác nhau** của startup.

## 7. Khi nào ConfigurableBootstrapContext hữu ích?

Vì `ConfigurableBootstrapContext` vừa là registry vừa là context, nó phù hợp khi mã giai đoạn bootstrap phải quyết định đăng ký bổ sung dựa trên môi trường.

Ví dụ một listener của `ApplicationEnvironmentPreparedEvent` có thể kiểm tra thuộc tính:

~~~java
app.addListeners(
    (ApplicationListener<ApplicationEnvironmentPreparedEvent>) event -> {
        ConfigurableBootstrapContext bootstrap =
                event.getBootstrapContext();

        if (!bootstrap.isRegistered(MyEarlyDependency.class)) {
            bootstrap.register(
                    MyEarlyDependency.class,
                    context -> new MyEarlyDependency());
        }

        MyEarlyDependency value = bootstrap.get(
                MyEarlyDependency.class);
        // Sử dụng value cho công việc chuẩn bị Environment
    }
);
~~~

Đây là **đoạn minh họa**, chưa phải chương trình độc lập; các class `MyEarlyDependency`, `app` và import được giả định đã có. Với Spring Boot 3.3, `ConfigurableBootstrapContext` nằm trong `org.springframework.boot`.

Trong phần lớn trường hợp, **đăng ký trước bằng `BootstrapRegistryInitializer` vẫn dễ hiểu hơn** vì xác định rõ nhà cung cấp dependency trước khi khởi chạy xử lý `Environment`. Chỉ thêm registration trong listener khi thật sự cần một quyết định phụ thuộc thông tin đã có ở giai đoạn đó.

### Đọc hoặc thay đổi Environment

`ConfigurableBootstrapContext` tự nó **không phải nơi chứa các `PropertySource`**. Muốn đọc/sửa properties, sử dụng `ConfigurableEnvironment` của event hoặc API `EnvironmentPostProcessor` thích hợp. Bootstrap context chỉ giữ các đối tượng bổ trợ cần thiết cho quá trình đó.

Ví dụ: bootstrap registry chứa `SecretsClient`, còn kết quả truy vấn được dùng để tạo `PropertySource` và đưa vào `Environment`. Không nên nhét mọi thuộc tính cấu hình thành registration theo type, vì registry không có hợp đồng về độ ưu tiên property như `PropertySources`.

## 8. Bàn giao đối tượng sang ApplicationContext như thế nào?

Không có quy tắc “mọi bootstrap object sẽ trở thành Spring bean”. Tích hợp phải chọn cách bàn giao rõ ràng theo nhu cầu:

1. **Chỉ dùng trong bootstrap:** không đăng ký vào BeanFactory; đối tượng phục vụ nạp cấu hình và được xử lý vòng đời phù hợp trước/sau khi bootstrap kết thúc.
2. **Tái sử dụng như bean:** `BootstrapContextClosedEvent` cho phép truy cập context chính đã chuẩn bị; có thể đăng ký một singleton đã tạo như ví dụ với `registerSingleton`, nếu điều đó phù hợp với lifecycle của object.
3. **Tạo lại ở runtime:** nếu bootstrap client chứa quyền truy cập nhạy cảm hoặc logic tạm thời, runtime có thể tạo bean riêng theo cấu hình đã nạp, thay vì dùng lại instance bootstrap.
4. **Thực sự cần init/destroy hooks của Spring:** thiết kế cơ chế đăng ký bean definition hoặc factory trong phase thích hợp, bảo đảm tên, phạm vi và lifecycle được xử lý như mong đợi.

**Rủi ro thường gặp** là giữ một instance không rõ chủ sở hữu và để cả bootstrap lẫn ApplicationContext cùng cố gắng đóng nó, hoặc cả hai cùng nghĩ bên kia sẽ đóng. Chọn một nơi sở hữu việc close; tránh đóng object khi một bean khác còn sử dụng nó.

### BootstrapContextClosedEvent không phải ApplicationReadyEvent

`BootstrapContextClosedEvent` cho biết giai đoạn bootstrap context kết thúc khi context chính được chuẩn bị. Đây **không phải dấu hiệu ứng dụng đã start thành công**, cũng không tương đương `ContextClosedEvent` của Spring khi ứng dụng tắt. Nếu bạn cần biết runtime đã refresh hoặc sẵn sàng nhận request, dùng các event như `ApplicationStartedEvent`/`ApplicationReadyEvent` theo đúng mục đích.

## 9. Phân biệt bootstrap registry với những khái niệm dễ nhầm

| Khái niệm | Có khi nào? | Chứa gì? | Dùng để làm gì? |
| --- | --- | --- | --- |
| `BootstrapRegistry` | Rất sớm, trước context chính | Type → supplier | Khai báo dependency khởi động |
| `BootstrapContext` | Rất sớm, khi chuẩn bị Environment | Lazy instance theo type | Đọc dependency đã đăng ký |
| `ConfigurableBootstrapContext` | Giai đoạn bootstrap | Cả đăng ký và đọc | Tích hợp cần vừa đọc vừa cấu hình |
| `ApplicationContext` | Khi Spring đã tạo và về sau refresh | Bean definitions, instance, dependency graph | Quản lý toàn bộ bean của ứng dụng |
| `BeanFactoryPostProcessor` | Trong refresh, trước phần lớn bean | Metadata bean definition | Thay đổi bean metadata/factory |
| `BeanPostProcessor` | Trong quá trình tạo bean | Bean instance trước/sau init | Xử lý bean/proxy/lifecycle |
| `ApplicationContextInitializer` | Context đã tạo, chưa refresh | ConfigurableApplicationContext | Tùy chỉnh context trước refresh |
| Spring Cloud bootstrap context | Phụ thuộc module Spring Cloud và cách tích hợp | Có thể là ApplicationContext riêng | Cơ chế bootstrap cấu hình của Spring Cloud |

Đặc biệt, **`BootstrapRegistry` của Spring Boot không đồng nghĩa với bootstrap ApplicationContext của Spring Cloud**. Spring Cloud có thêm cơ chế cấu hình và lịch sử riêng; cùng từ “bootstrap” không có nghĩa cùng type, lifecycle hay mục đích.

`BootstrapRegistry` cũng **không phải JNDI registry, service registry (Eureka/Consul) hoặc bean registry toàn cục**. Nó chỉ là một cơ chế nội bộ dành cho giai đoạn khởi động ứng dụng.

## 10. Sai lầm thường gặp và cách xử lý

| Hiện tượng / sai lầm | Nguyên nhân thường thấy | Hướng xử lý |
| --- | --- | --- |
| `get(Foo.class)` ném `IllegalStateException` | Type chưa đăng ký | Đăng ký trong initializer đủ sớm, hoặc dùng `getOrElse...` theo hợp đồng |
| `get` trả null dù `isRegistered` true | Supplier có thể cung cấp null | Kiểm tra supplier và điều kiện dữ liệu, không dùng `isRegistered` như health check |
| Tạo client ngay trong initializer | Nhầm registration với eager creation | Đưa logic vào `InstanceSupplier` để lazy khởi tạo |
| Inject `@Autowired Foo` trong bootstrap initializer | Spring chưa tạo bean IoC thông thường | Dùng tham số registry/context và dependency không dựa vào bean |
| Đăng ký nhiều instance cùng một type | Registry dùng `Class<T>` làm khóa | Tách loại wrapper hoặc thiết kế object giữ các biến thể |
| Đổi `register()` sau khi singleton đã được tạo | Replacement bị giới hạn, trạng thái đã chia sẻ | Chốt registration trước khi tiêu thụ; dùng `registerIfAbsent` cho default |
| Code muốn dùng object như bean nhưng inject thất bại | Không có bước bàn giao sang ApplicationContext | Đăng ký bean một cách tường minh trước refresh hoặc tạo bean runtime riêng |
| Đối tượng được `registerSingleton` thiếu init callback | Instance đã được tạo ngoài vòng đời đầy đủ của Spring | Chọn cơ chế bean definition/factory nếu cần đầy đủ init/destroy |
| Đóng client bootstrap quá sớm | Client đang được runtime dùng tiếp | Xác định ownership và thời điểm release resource |
| Dùng API Boot 4 với import Boot 3 | Package API bootstrap thay đổi | Kiểm tra version thực tế, sửa import theo bảng tương thích |
| Gọi bean lookup trong `ApplicationEnvironmentPreparedEvent` | Context chưa được tạo | Dùng `event.getBootstrapContext()`; chưa dựa vào `getBean()` |
| Đồng nhất `BootstrapContextClosedEvent` với app shutdown | Hai sự kiện mang ý nghĩa khác nhau | Theo dõi đúng loại event của phase tương ứng |

### Một số giới hạn thiết kế cần hiểu

**Không mở quá nhiều resource trong bootstrap.** Đây là đoạn đường quan trọng của startup; network timeout dài hoặc phụ thuộc bị treo có thể kéo dài thời gian khởi chạy. Cấu hình retry, timeout, fallback và failure policy có chủ đích nếu tích hợp với hệ thống bên ngoài.

**Tránh dependency vòng giữa các bootstrap supplier.** Nếu `Supplier<A>` gọi `context.get(B.class)`, còn `Supplier<B>` lại gọi `context.get(A.class)`, quá trình khởi tạo có nguy cơ lặp vô hạn hoặc lỗi trạng thái. Thiết kế dependency theo hướng một chiều và giữ cấu trúc đơn giản.

**Không phỏng đoán thread-safety.** Nếu nhiều thành phần truy cập resource cùng lúc, chính resource và tích hợp phải đáp ứng yêu cầu đồng thời. Một singleton không tự động thread-safe.

**Chú ý an toàn thông tin.** Bootstrap thường liên quan đến token, credential hoặc endpoint nội bộ. Không in khóa bí mật trong log, không chuyển dữ liệu nhạy cảm sang bean công khai một cách tùy tiện, và tránh để exception tiết lộ secret. Chuỗi `demo-key` trong ví dụ chỉ là dữ liệu giả.

**Không nhầm cache do bootstrap context quản lý với bean singleton.** Singleton trong registry theo type và singleton trong BeanFactory theo bean name/type là hai hệ thống riêng. Chúng chỉ chia sẻ instance khi tích hợp có thao tác bàn giao cụ thể.

**Đừng tùy tiện dùng registry làm service locator cho code nghiệp vụ.** Sau khi `ApplicationContext` hoạt động, nên ưu tiên dependency injection thông thường để hệ thống dễ kiểm thử, quan sát và quản lý vòng đời.

## 11. Tương thích Spring Boot 2.4 → 3.5 → 4.x

Các API bootstrap registry xuất hiện từ dòng Spring Boot 2.4; `SpringApplication.addBootstrapRegistryInitializer(...)` có từ 2.4.5. Tuy nhiên **đường dẫn package thay đổi ở Spring Boot 4.x**.

| API | Spring Boot 3.3 | Spring Boot 4.x |
| --- | --- | --- |
| `BootstrapRegistry` | `org.springframework.boot.BootstrapRegistry` | `org.springframework.boot.bootstrap.BootstrapRegistry` |
| `BootstrapContext` | `org.springframework.boot.BootstrapContext` | `org.springframework.boot.bootstrap.BootstrapContext` |
| `ConfigurableBootstrapContext` | `org.springframework.boot.ConfigurableBootstrapContext` | `org.springframework.boot.bootstrap.ConfigurableBootstrapContext` |
| `BootstrapRegistryInitializer` | `org.springframework.boot.BootstrapRegistryInitializer` | `org.springframework.boot.bootstrap.BootstrapRegistryInitializer` |
| `BootstrapContextClosedEvent` | `org.springframework.boot.BootstrapContextClosedEvent` | `org.springframework.boot.bootstrap.BootstrapContextClosedEvent` |

`SpringApplication` vẫn là điểm khởi chạy trong `org.springframework.boot` trong các phiên bản đang nói đến. Khi đổi Boot major version, thay import và **cập nhật cả tên key SPI trong `spring.factories` nếu có dùng**; không chỉ sửa các class Java.

Đừng sao chép một ví dụ của Boot 4 vào một dự án dùng Boot 3 rồi kết luận “bootstrap registry đã bị xóa” chỉ vì Java compiler không tìm được package. Luôn kiểm tra Javadoc tương ứng với version phụ thuộc của dự án.

## 12. Bài tập thực hành và cách tự kiểm tra

**Bài tập 1 — Chứng minh lazy supplier.** Chạy ví dụ mục 5, rồi tạm bỏ dòng gọi `get(EarlyToken.class)` ở listener `ApplicationEnvironmentPreparedEvent` nhưng vẫn giữ close listener. Theo dõi thời điểm `03_CREATE_EARLY_TOKEN` chuyển sang giai đoạn đóng bootstrap context. Giải thích vì sao registry vẫn có registration trước đó nhưng chưa tạo instance.

**Bài tập 2 — Bỏ bàn giao bean.** Tạm xóa `registerSingleton("earlyToken", token)` nhưng giữ `@Bean ApplicationRunner printResult(EarlyToken token)`. Dự đoán lỗi inject và giải thích tại sao type trong bootstrap registry không tự trở thành bean. Đây là thay đổi để thử nghiệm, sau đó khôi phục mã.

**Bài tập 3 — Thay đổi chính sách registration.** Viết hai initializer cùng cung cấp `EarlyToken.class` và dùng `registerIfAbsent`. Quan sát initializer nào tạo registration trước khi `get`. Tại sao không nên thiết kế logic nghiệp vụ phụ thuộc vào thứ tự không được chỉ định rõ? Đề xuất một cấu hình minh bạch khi cần override.

**Bài tập 4 — Đánh giá lifecycle.** Thay record đơn giản bằng một đối tượng `AutoCloseable` giả lập kết nối; xác định ai sẽ sở hữu việc đóng sau khi bootstrap kết thúc, đặc biệt khi cùng instance được bàn giao làm bean. Không đóng hai lần hoặc bỏ quên resource.

**Câu hỏi 1:** Vì sao không thể giải quyết mọi dependency bootstrap bằng `@Autowired`?

**Trả lời:** `@Autowired` cần cơ chế bean/container của Spring; ở giai đoạn chuẩn bị `Environment`, context chính chưa tạo/refresh. Bootstrap registry có thể cung cấp đối tượng sớm độc lập với bean lifecycle thông thường.

**Câu hỏi 2:** `BootstrapRegistry` và `ConfigurableBootstrapContext` khác nhau thế nào?

**Trả lời:** `BootstrapRegistry` chỉ định nghĩa thao tác đăng ký/close listener; `ConfigurableBootstrapContext` kế thừa cả `BootstrapRegistry` và `BootstrapContext`, nên vừa đăng ký vừa lấy đối tượng.

**Câu hỏi 3:** Đăng ký supplier có đồng nghĩa lập tức tạo đối tượng không?

**Trả lời:** Không. Cơ chế được thiết kế để hỗ trợ lazy lookup; gọi `get` mới kích hoạt supplier khi chưa có instance tương ứng.

**Câu hỏi 4:** `BootstrapContextClosedEvent` có nghĩa ứng dụng đã ready và mọi bean đã tồn tại?

**Trả lời:** Không. Nó xảy ra lúc ApplicationContext đã chuẩn bị. Việc refresh, tạo bean và chạy runner thuộc các bước tiếp theo.

**Câu hỏi 5:** Có thể đăng ký hai client cùng type nhưng khác cấu hình bằng hai tên string trong registry này không?

**Trả lời:** Không có tên bean trong khóa registration; registry chỉ dùng `Class<T>`. Cần tổ chức type khác hoặc một lớp wrapper quản lý tập client.

**Câu hỏi 6:** Sau khi `registerSingleton` một instance bootstrap vào BeanFactory, có thể yên tâm rằng Spring đã chạy lại mọi init callback cho nó không?

**Trả lời:** Không. Đó là đối tượng đã được tạo sẵn, cần xem lại vòng đời và cleanup của chính tích hợp.

## 13. Tài liệu chính thức và ghi nhớ

Nguồn tra cứu theo đúng dòng Spring Boot đang dùng:

- [Spring Boot 3.3 — BootstrapRegistry API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapRegistry.html).
- [Spring Boot 3.3 — ConfigurableBootstrapContext](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ConfigurableBootstrapContext.html).
- [Spring Boot 3.3 — BootstrapContext và lookup](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapContext.html).
- [Spring Boot 3.3 — BootstrapRegistry.InstanceSupplier](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapRegistry.InstanceSupplier.html).
- [Spring Boot 3.3 — BootstrapContextClosedEvent](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/BootstrapContextClosedEvent.html).
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html).
- [Spring Boot 4.x — BootstrapRegistry (package mới)](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/bootstrap/BootstrapRegistry.html).

**Những điểm không được nhầm:**

1. Bootstrap registry giải quyết **dependency trước khi có bean**, không thay thế Spring IoC.
2. `BootstrapRegistry` đăng ký supplier; `BootstrapContext` lấy object; `ConfigurableBootstrapContext` kết hợp cả hai.
3. Đăng ký theo **`Class<T>`**, không theo tên bean; có thể tạo lazy singleton hoặc prototype theo scope.
4. `BootstrapRegistryInitializer` được gọi sớm, trước các bước cần dùng bootstrap context.
5. `ApplicationEnvironmentPreparedEvent` cung cấp bootstrap context trong giai đoạn sớm.
6. `BootstrapContextClosedEvent` là ranh giới chuẩn bị context; nếu cần đưa resource vào bean runtime phải **bàn giao tường minh**.
7. Chuyển một instance sẵn có bằng `registerSingleton` không tự đảm bảo toàn bộ lifecycle hook như bean được tạo bình thường.
8. Kiểm tra version trước khi copy import: **Spring Boot 3.3 dùng `org.springframework.boot`; Spring Boot 4.x dùng `org.springframework.boot.bootstrap`** cho các bootstrap API.

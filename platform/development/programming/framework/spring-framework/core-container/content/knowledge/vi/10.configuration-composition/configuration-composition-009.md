# Tránh phụ thuộc vòng giữa các lớp cấu hình trong Spring Core Container

## Mục tiêu bài học

Khi ứng dụng Spring mở rộng, việc chia Java configuration thành nhiều class `@Configuration` giúp tổ chức các bean theo module: cơ sở dữ liệu, repositories, services, integrations và entry points. Tuy nhiên, nếu các class cấu hình **import lẫn nhau**, **constructor-inject lẫn nhau** hoặc **truy cập quá sớm những bean do chính chúng định nghĩa**, bạn có thể tạo ra một *circular dependency* (phụ thuộc vòng).

Một lỗi thường gặp là:

```text
ServiceConfig  --->  RepositoryConfig
     ^                    |
     |                    |
     +--------------------+
```

Mũi tên đó có thể là `@Import`, constructor injection giữa hai configuration class, hoặc một dependency giữa các đối tượng được khai báo bằng `@Bean`. **Ba trường hợp này không đồng nghĩa**, và cách chẩn đoán/sửa đúng phải dựa trên loại cạnh nào đang tạo vòng.

Bài này tập trung vào chủ đề **“Tránh phụ thuộc vòng giữa các lớp cấu hình”**, thuộc phần *Ghép cấu hình* của Spring Framework Core Container. Sau bài học, bạn sẽ:

1. Phân biệt **vòng import configuration classes**, **vòng tạo configuration bean** và **vòng dependency giữa application beans**.
2. Dùng `@Import` theo cấu trúc một chiều thay vì để các module config biết và nhập lẫn nhau.
3. Dùng **tham số phương thức `@Bean`** để biểu diễn dependency giữa bean definitions ở các configuration classes khác nhau.
4. Hiểu vì sao constructor injection vào chính `@Configuration` đôi lúc gây **early initialization/self-reference cycle**.
5. Tránh gọi `@Bean` methods trong `@PostConstruct` của class cấu hình.
6. Hiểu sự khác nhau giữa full `@Configuration` và `@Configuration(proxyBeanMethods=false)`; biết khi nào direct method call tạo unmanaged object.
7. Đọc nguyên nhân thực của `BeanCurrentlyInCreationException`, `UnsatisfiedDependencyException` và vòng `@Import`.
8. Đánh giá giới hạn của `@Lazy`, `ObjectProvider`, `@DependsOn` và tùy chọn cho phép circular references.
9. Có mẫu thiết kế hoàn chỉnh Java 17 + Spring Framework dùng root composition và wiring theo kiểu, không có vòng.
10. Viết integration test để phát hiện vòng sớm và tránh regression.

**Nguyên tắc xuyên suốt:** Class `@Configuration` nên **khai báo cách tạo bean**, không nên trở thành service cần phụ thuộc trực tiếp vào configuration class khác. Hãy để **bean nghiệp vụ phụ thuộc vào các abstraction thích hợp**, còn một **root configuration** tổng hợp module theo một chiều.

## 1. Ba loại vòng thường bị đánh đồng

Không phải mọi vòng trong Spring đều thuộc cùng một tầng. Trước khi sửa code, hãy vẽ được đồ thị và xác định **node** là cái gì.

### 1.1. Vòng import: class cấu hình A import B, B import A

```java
// PHẢN VÍ DỤ: Hai class cấu hình nhập lẫn nhau.
@Configuration
@Import(ConfigB.class)
class ConfigA {
}

@Configuration
@Import(ConfigA.class)
class ConfigB {
}
```

Đồ thị:

```text
ConfigA --@Import--> ConfigB
ConfigB --@Import--> ConfigA
```

`@Import` nói với Spring “hãy xử lý thêm class cấu hình này”, **không phải** “hãy tạo một đối tượng làm dependency cho class kia”. Khi import graph có vòng, Spring configuration parser có thể phát hiện và từ chối, ví dụ thông báo liên quan `A circular @Import has been detected` hoặc lỗi phân tích configuration.

Cách sửa thông thường là **đưa quyền phối hợp lên một root**:

```java
@Configuration(proxyBeanMethods = false)
@Import({ConfigA.class, ConfigB.class})
class RootConfig {
}

// ConfigA và ConfigB không còn @Import lẫn nhau.
```

Về mặt tổ chức, root biết những module cần lắp vào một ứng dụng; những module không nhất thiết phải biết cấu hình của nhau.

### 1.2. Vòng constructor giữa chính các @Configuration beans

```java
// PHẢN VÍ DỤ: Cả hai class cấu hình cần instance của nhau.
@Configuration
class BillingConfig {
    BillingConfig(ShippingConfig shippingConfig) {
    }
}

@Configuration
class ShippingConfig {
    ShippingConfig(BillingConfig billingConfig) {
    }
}
```

Đồ thị:

```text
BillingConfig instance --> ShippingConfig instance
ShippingConfig instance --> BillingConfig instance
```

Spring xử lý `@Configuration` như những beans trong container. Nếu phải tạo `BillingConfig` trước mới tạo được `ShippingConfig`, nhưng cũng phải tạo `ShippingConfig` trước mới tạo được `BillingConfig`, constructor injection không thể hoàn thành.

Điểm quan trọng: vòng này xảy ra **giữa bản thân configuration instances**, chứ chưa chắc giữa `InvoiceService` và `ShippingService`. Cách tốt nhất thường là **không inject configuration class vào configuration class**; thay bằng dependency theo kiểu của **bean cần dùng** ngay tại `@Bean` method.

### 1.3. Vòng constructor giữa beans do @Bean tạo

```java
// PHẢN VÍ DỤ: Hai business types phải có nhau ngay trong constructor.
@Configuration(proxyBeanMethods = false)
class BadBusinessConfig {

    @Bean
    ServiceA serviceA(ServiceB b) {
        return new ServiceA(b);
    }

    @Bean
    ServiceB serviceB(ServiceA a) {
        return new ServiceB(a);
    }
}
```

Ở đây `ServiceA` và `ServiceB` là kiểu minh họa có constructors nhận nhau. Đồ thị thực:

```text
bean "serviceA" --> bean "serviceB"
bean "serviceB" --> bean "serviceA"
```

Khi Spring tạo bean A cần B, tạo B lại cần A đang được tạo. Vòng constructor bất khả giải thường dẫn đến `BeanCurrentlyInCreationException`, có thể nằm trong exception chain gồm `UnsatisfiedDependencyException` hoặc `BeanCreationException`.

**Khác biệt thiết yếu:** Việc chuyển hai `@Bean` methods sang hai `@Configuration` classes **không tự làm vòng bean biến mất**. Bạn cần sửa **hướng dependency giữa application beans**, không chỉ sửa vị trí khai báo chúng.

## 2. Vì sao nhiều class cấu hình vẫn có thể phụ thuộc bean của nhau?

Spring **không yêu cầu** mỗi configuration class chỉ tạo các bean mà nó hoàn toàn tự sở hữu. Một bean ở module service hoàn toàn có thể phụ thuộc bean repository do module khác khai báo.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class RepositoryConfig {

    @Bean
    AccountRepository accountRepository() {
        return new InMemoryAccountRepository();
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
class ServiceConfig {

    @Bean
    AccountService accountService(AccountRepository accountRepository) {
        return new AccountService(accountRepository);
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
@Import({RepositoryConfig.class, ServiceConfig.class})
class ApplicationConfig {
}
```

Đây là **mẫu minh họa**, cần các kiểu `AccountRepository`, `InMemoryAccountRepository` và `AccountService` có constructor phù hợp.

Đồ thị import:

```text
             ApplicationConfig
                /       \
           @Import      @Import
              /           \
RepositoryConfig         ServiceConfig
```

Đồ thị dependency **giữa beans**:

```text
accountService --> accountRepository
```

Không có vòng. `ServiceConfig` **không cần import `RepositoryConfig`** chỉ vì method `accountService(AccountRepository)` yêu cầu bean repository. Khi root đã đưa cả hai config vào cùng context, BeanFactory nhìn thấy definitions và resolve tham số theo kiểu.

Đây là điểm quan trọng trong thiết kế module: **class cấu hình có thể độc lập về source-level reference, trong khi các bean của chúng vẫn được wiring qua IoC container**.

### Vai trò của @Import

`@Import` thuộc:

```java
import org.springframework.context.annotation.Import;
```

Nó giúp root configuration gom các cấu hình hoặc components phù hợp để Spring xử lý. Các tham số là **class references**, không phải bean instance. `@Import` không tự inject một configuration instance vào một configuration khác.

### Vai trò của tham số @Bean

```java
@Bean
AccountService accountService(AccountRepository repository) {
    return new AccountService(repository);
}
```

Tham số `AccountRepository` là **dependency request** đối với BeanFactory, giúp Spring phân giải bean theo type, qualifier, primary, generic và scope thích hợp. Không có lý do phải gọi `new RepositoryConfig().accountRepository()` hay giữ một field `RepositoryConfig` trong `ServiceConfig` để lấy bean.

## 3. Thiết kế một chiều: root composition và các module tự chủ

Đối với ứng dụng có cấu trúc theo tầng, một kiến trúc dễ bảo trì là:

```text
                     RootConfig
                   /     |      \
                  v      v       v
              Infra    Repo    Service
              Config   Config  Config

Bean dependencies:
CatalogService  ---> CatalogRepository
       |
       +-----------> Clock
       |
       v
CatalogFacade
```

Các **configuration classes** được import từ root. Các **application beans** được nối qua injection. Không cần có cạnh `ServiceConfig -> RepositoryConfig` nếu chỉ muốn service dùng một repository bean.

### Đặt ranh giới module

- `InfrastructureConfig` chịu trách nhiệm đăng ký clock, data source, HTTP client, codec hoặc hạ tầng chung.
- `RepositoryConfig` chịu trách nhiệm repository implementations.
- `ServiceConfig` chịu trách nhiệm service beans.
- `RootConfig` quyết định ứng dụng cần những module nào.
- Không module nào cần giữ instance configuration class của module khác.

Tổ chức này làm rõ **dependency direction**. Có thể dùng cấu trúc package theo feature thay vì theo layer; nguyên tắc vẫn là chọn root composition rõ và không tạo vòng.

### Nếu một module thực sự cần dùng module khác?

Phân biệt hai câu hỏi:

1. “Ứng dụng có cần nhập cả hai cấu hình không?” — root `@Import` xử lý.
2. “Bean A có cần dùng bean B không?” — constructor hoặc factory method parameter injection xử lý.

Đừng trả lời cả hai bằng “cấu hình A import cấu hình B và nhận luôn BConfig trong constructor”. Điều đó tăng coupling và dễ dẫn đến vòng khi module B cần import A sau này.

## 4. Anti-pattern: inject class cấu hình khác để gọi factory method

Ví dụ khó bảo trì:

```java
@Configuration
class RepositoryConfig {

    @Bean
    CatalogRepository catalogRepository() {
        return new JdbcCatalogRepository();
    }
}

@Configuration
class ServiceConfig {

    private final RepositoryConfig repositoryConfig;

    ServiceConfig(RepositoryConfig repositoryConfig) {
        this.repositoryConfig = repositoryConfig;
    }

    @Bean
    CatalogService catalogService() {
        return new CatalogService(
                repositoryConfig.catalogRepository());
    }
}
```

Đây là **đoạn phản ví dụ** với những class ứng dụng giả định. Có thể có tình huống lời gọi được full configuration proxy intercept, nhưng nó khiến `ServiceConfig` phụ thuộc vào **implementation/configuration class** của module repository thay vì dependency contract `CatalogRepository`.

Rủi ro:

- Khi refactor cách đăng ký repository, service config phải đổi theo.
- Khi repo config có dependency tới service module, vòng giữa config instances dễ xuất hiện.
- Dễ nhầm giữa gọi method Java và lấy Spring-managed singleton, đặc biệt nếu chuyển sang `proxyBeanMethods=false`.
- Unit test của factory method không cần thiết phải dựng configuration instance khác.
- Khó chuyển bean sang XML, registrar hoặc component scan mà không sửa code wiring.

### Sửa bằng tham số factory method

```java
@Configuration(proxyBeanMethods = false)
class ServiceConfig {

    @Bean
    CatalogService catalogService(CatalogRepository repository) {
        return new CatalogService(repository);
    }
}
```

Trong root:

```java
@Configuration(proxyBeanMethods = false)
@Import({RepositoryConfig.class, ServiceConfig.class})
class RootConfig {
}
```

Như vậy `ServiceConfig` không cần biết `RepositoryConfig` là class nào. BeanFactory đáp ứng dependency theo contract.

## 5. Anti-pattern: configuration class inject bean do chính nó khai báo

Vòng có thể tinh vi hơn khi class cấu hình tự yêu cầu **kết quả từ instance method của chính nó**.

```java
// PHẢN VÍ DỤ: StorageConfig cần Storage để được tạo,
// nhưng Storage lại được tạo từ instance method trên StorageConfig.
@Configuration
class StorageConfig {

    private final Storage storage;

    StorageConfig(Storage storage) {
        this.storage = storage;
    }

    @Bean
    Storage storage() {
        return new Storage();
    }
}
```

Đồ thị:

```text
configuration bean "storageConfig"
           |
           | constructor requires Storage
           v
bean "storage"
           |
           | instance @Bean factory requires storageConfig instance
           v
configuration bean "storageConfig"
```

Spring phải khởi tạo configuration instance trước khi gọi non-static factory method `storage()` trên instance đó, trong khi constructor config lại đòi bean do method ấy sản xuất. Đây là một **self-reference cycle** ở giai đoạn tạo bean.

### Cách sửa 1: không đưa Storage vào constructor configuration

```java
@Configuration(proxyBeanMethods = false)
class StorageConfig {

    @Bean
    Storage storage() {
        return new Storage();
    }

    @Bean
    StorageConsumer storageConsumer(Storage storage) {
        return new StorageConsumer(storage);
    }
}
```

Trong ví dụ, `StorageConsumer` có constructor nhận `Storage`. Cấu hình không giữ `Storage` trong field; Spring inject nó trực tiếp vào factory method cần dùng.

### Cách sửa 2: dùng một cấu hình hạ tầng độc lập

```java
@Configuration(proxyBeanMethods = false)
class InfrastructureConfig {

    @Bean
    Storage storage() {
        return new Storage();
    }
}

@Configuration(proxyBeanMethods = false)
class ConsumerConfig {

    @Bean
    StorageConsumer storageConsumer(Storage storage) {
        return new StorageConsumer(storage);
    }
}
```

Một root import cả hai. Không config nào phải inject bean do chính instance factory method của nó tạo.

### Cách sửa 3: static @Bean khi thuộc loại hạ tầng phù hợp

Một số bean post-processors được khai báo bằng `static @Bean`, cho phép BeanFactory tạo chúng mà **không phải tạo instance configuration class quá sớm**. Nhưng đây là trường hợp hạ tầng có yêu cầu lifecycle riêng, không phải giải pháp chung để biến mọi bean thành static.

Ví dụ:

```java
// Đoạn mô tả, không phải lời khuyên áp dụng cho mọi @Bean.
@Configuration(proxyBeanMethods = false)
class InfrastructureConfig {
    @Bean
    static SomeBeanFactoryPostProcessor somePostProcessor() {
        return new SomeBeanFactoryPostProcessor();
    }
}
```

`SomeBeanFactoryPostProcessor` cần là một implementation phù hợp. Điểm quan trọng: dùng static khi bean thực sự thuộc post-processor bootstrap, và hiểu sự khác biệt với instance factory methods.

## 6. Đừng gọi bean của cấu hình trong @PostConstruct trên chính @Configuration

Đây là cảnh báo rõ trong tài liệu Spring về composing Java configurations.

```java
// PHẢN VÍ DỤ: Không lấy bean do chính config định nghĩa
// trong @PostConstruct của class config này.
@Configuration
class RiskyConfig {

    @Bean
    DataClient dataClient() {
        return new DataClient();
    }

    @PostConstruct
    void init() {
        dataClient().connect();
    }
}
```

Đoạn này dùng `@PostConstruct` của Jakarta Annotations và giả định `DataClient` có method `connect()`. Nó chỉ nhằm mô tả rủi ro, không phải một ứng dụng an toàn.

Vì `@Configuration` cũng là một bean và instance method `@Bean` cần instance config đã sẵn sàng, việc cố lấy một locally declared bean **ngay khi config instance còn ở giai đoạn init** có thể tạo self-reference/circular creation. Khi circular references bị cấm, bạn có thể nhận `BeanCurrentlyInCreationException`.

Ngoài ra:

- `@PostConstruct` chạy trong **lifecycle của bean cấu hình**, không có nghĩa toàn bộ application đã khởi động xong.
- Nếu gọi một factory method trực tiếp ở lite mode, Java có thể tạo object riêng **không được BeanFactory quản lý**.
- Mở network connection hoặc chạy nghiệp vụ trong initialization callback còn có thể làm startup chậm, gây deadlock hoặc leak tài nguyên.
- Việc thêm `@Lazy` vào một bean không đảm bảo self-invocation trong init sẽ an toàn.

### Cách sửa: bean-local initialization của bean được quản lý

Nếu `DataClient` có method `connect()` phù hợp cho lifecycle của **chính nó**:

```java
@Configuration(proxyBeanMethods = false)
class ClientConfig {

    @Bean(initMethod = "connect", destroyMethod = "close")
    DataClient dataClient() {
        return new DataClient();
    }
}
```

Spring gọi `connect` trên **managed DataClient bean**, rồi `close` theo lifecycle singleton khi context đóng. Không cần gọi `dataClient()` từ `@PostConstruct` của `ClientConfig`.

Nếu thao tác là bootstrap nghiệp vụ phối hợp nhiều beans, dùng coordinator/startup lifecycle riêng phù hợp; đừng đẩy nó vào config initialization.

## 7. Full và lite @Configuration không làm biến mất vòng thật

Với full configuration:

```java
@Configuration
class FullConfig {
    @Bean
    X x() {
        return new X(y());
    }

    @Bean
    Y y() {
        return new Y();
    }
}
```

Khi lời gọi `y()` diễn ra trên enhanced configuration instance do Spring quản lý, Spring có thể intercept để lấy bean `y` theo scope. Điều này giúp dùng đúng bean identity trong một đồ thị dependency **không có vòng**.

Với lite configuration:

```java
@Configuration(proxyBeanMethods = false)
class LiteConfig {
    @Bean
    X x() {
        return new X(y());
    }

    @Bean
    Y y() {
        return new Y();
    }
}
```

Lời gọi `y()` trong `x()` chỉ là Java call thông thường; nó có thể tạo object `Y` riêng, không phải managed bean `y`. Đây là **lỗi identity/lifecycle**, không nhất thiết báo circular dependency; do vậy lite mode **không phải “thuốc sửa vòng”** mà còn có thể che rủi ro khác.

### Mẫu chung cho cả full và lite

```java
@Configuration(proxyBeanMethods = false)
class SafeConfig {
    @Bean
    X x(Y y) {
        return new X(y);
    }

    @Bean
    Y y() {
        return new Y();
    }
}
```

Spring resolve tham số factory method nên identity đúng. Nếu `Y` lại phụ thuộc vào `X` qua constructor, bạn vẫn có **vòng bean thật** và phải refactor dependency direction.

**Nhớ:** Đổi `proxyBeanMethods=true` sang `false` không xóa vòng import hoặc vòng constructor. Nó chỉ thay đổi cách những lời gọi Java tới bean methods được xử lý. Luôn kiểm tra **đồ thị dependency giữa các beans**, không chỉ cờ configuration enhancement.

## 8. Ví dụ Java 17 + Spring Framework: ghép cấu hình không có vòng

Ví dụ runnable dưới đây minh họa một ứng dụng nhỏ có:

- `InfrastructureConfig` tạo `Clock` cố định để output deterministic.
- `RepositoryConfig` tạo `CatalogRepository`.
- `ServiceConfig` tạo `CatalogService` bằng **tham số `@Bean`** nhận hai dependencies.
- `RootConfig` nhập ba cấu hình đó bằng **một chiều `@Import`** và tạo `CatalogFacade`.
- Không config nào inject một configuration class khác.
- Bean dependencies có hướng một chiều và Spring quản lý singleton identity.

Dự án chỉ cần Java 17+, Maven và `spring-context`, không yêu cầu Spring Boot, web server, database hay mạng bên ngoài.

### 8.1. Cấu trúc dự án

```text
config-cycle-free/
├── pom.xml
└── src/main/java/
    └── demo/
        └── CycleFreeConfigDemo.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
             http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>config-cycle-free</artifactId>
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

### 8.3. Mã Java đầy đủ

Tạo `src/main/java/demo/CycleFreeConfigDemo.java`:

```java
package demo;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Arrays;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

public class CycleFreeConfigDemo {

    public interface CatalogRepository {
        String labelFor(String sku);
    }

    public static final class InMemoryCatalogRepository
            implements CatalogRepository {

        @Override
        public String labelFor(String sku) {
            return switch (sku) {
                case "BK-7" -> "Java book";
                case "MUG-2" -> "Coffee mug";
                default -> "Unknown";
            };
        }
    }

    public static final class CatalogService {
        private final CatalogRepository repository;
        private final Clock clock;

        public CatalogService(CatalogRepository repository, Clock clock) {
            this.repository = repository;
            this.clock = clock;
        }

        public String describe(String sku) {
            return repository.labelFor(sku) + "@" +
                    LocalDate.now(clock);
        }

        public CatalogRepository repository() {
            return repository;
        }
    }

    public static final class CatalogFacade {
        private final CatalogService service;

        public CatalogFacade(CatalogService service) {
            this.service = service;
        }

        public String show(String sku) {
            return "facade:" + service.describe(sku);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class InfrastructureConfig {

        @Bean
        public Clock fixedClock() {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class RepositoryConfig {

        @Bean
        public CatalogRepository catalogRepository() {
            return new InMemoryCatalogRepository();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ServiceConfig {

        @Bean
        public CatalogService catalogService(
                CatalogRepository repository, Clock clock) {
            return new CatalogService(repository, clock);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import({
        InfrastructureConfig.class,
        RepositoryConfig.class,
        ServiceConfig.class
    })
    public static class RootConfig {

        @Bean
        public CatalogFacade catalogFacade(CatalogService service) {
            return new CatalogFacade(service);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(RootConfig.class)) {

            CatalogRepository repository =
                    context.getBean(CatalogRepository.class);
            CatalogService service =
                    context.getBean(CatalogService.class);
            CatalogFacade facade =
                    context.getBean(CatalogFacade.class);

            System.out.println("repo=" + repository.labelFor("BK-7"));
            System.out.println("service=" + service.describe("BK-7"));
            System.out.println("facade=" + facade.show("MUG-2"));
            System.out.println("sameRepository=" +
                    (service.repository() == repository));

            String[] repositoryNames =
                    context.getBeanNamesForType(CatalogRepository.class);
            Arrays.sort(repositoryNames);
            System.out.println("repositoryBeans=" +
                    Arrays.toString(repositoryNames));
        }
    }
}
```

### 8.4. Lệnh chạy

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.CycleFreeConfigDemo
```

Các dòng **do chương trình in ra**, không tính log Maven hoặc các logging bindings trong môi trường:

```text
repo=Java book
service=Java book@2024-01-01
facade=facade:Coffee mug@2024-01-01
sameRepository=true
repositoryBeans=[catalogRepository]
```

### 8.5. Vì sao output chính xác?

**`repo=Java book`:** Bean `catalogRepository` do `RepositoryConfig` khai báo, tạo `InMemoryCatalogRepository`. Method `labelFor("BK-7")` trả chuỗi cố định `Java book`.

**`service=Java book@2024-01-01`:** `CatalogService` được Spring tạo qua factory method `catalogService(CatalogRepository, Clock)`. Nó nhận repository singleton và `Clock.fixed(...)` từ `InfrastructureConfig`. `LocalDate.now(clock)` là ngày `2024-01-01`, không phụ thuộc ngày/giờ máy chạy.

**`facade=facade:Coffee mug@2024-01-01`:** Root tạo `CatalogFacade` bằng tham số `CatalogService` do Spring inject. Facade gọi service với `MUG-2`, repository trả `Coffee mug`, facade thêm tiền tố `facade:`.

**`sameRepository=true`:** `CatalogService` nhận **managed repository singleton** do Spring resolve theo type. `getBean(CatalogRepository.class)` trả cùng reference trong cùng context.

**`repositoryBeans=[catalogRepository]`:** Chỉ có một definition kiểu `CatalogRepository`, tên mặc định của `@Bean` factory method là `catalogRepository`. Mọi module cùng dùng một BeanFactory, không có repository phụ được tạo bằng `new RepositoryConfig().catalogRepository()`.

### 8.6. Đồ thị trong ví dụ

```text
RootConfig
  |--@Import--> InfrastructureConfig  --@Bean--> Clock
  |--@Import--> RepositoryConfig      --@Bean--> CatalogRepository
  |--@Import--> ServiceConfig         --@Bean--> CatalogService
  |
  +-------------- @Bean ---------------------> CatalogFacade

Bean dependencies (cạnh ngược chiều nhu cầu):
CatalogFacade ---> CatalogService ---> CatalogRepository
                         |
                         +-----------> Clock
```

Không có đường nào từ repository về service hoặc từ infrastructure về facade. Import graph và bean dependency graph đều **không có vòng**.

### 8.7. Tại sao RootConfig chỉ import, không instantiate config?

`@Import(RepositoryConfig.class)` nói với Spring xử lý class cấu hình đó. Việc viết:

```java
// PHẢN VÍ DỤ: không tạo configuration instances thủ công.
RepositoryConfig repoConfig = new RepositoryConfig();
CatalogRepository repo = repoConfig.catalogRepository();
```

sẽ tự tạo object repository bên ngoài managed bean definition, không có lý do để BeanFactory quản lý nó. Trong lite configuration, direct call còn có thể tạo instance khác singleton. Cách đúng là để `@Import` đưa bean definitions vào container rồi dùng `@Bean` parameter injection.

### 8.8. Nếu thêm module khác?

Giả sử có `NotificationConfig` đăng ký một `NotificationService` phụ thuộc `CatalogService`. Bạn có thể:

1. Tạo `NotificationConfig` với `@Bean NotificationService notificationService(CatalogService service)`.
2. Thêm `NotificationConfig.class` vào mảng import của **RootConfig**.
3. Không để `ServiceConfig` import `NotificationConfig` chỉ vì một service khác dùng catalogue.
4. Giữ dependency nghiệp vụ một chiều; nếu notification lại buộc catalog service phụ thuộc ngược notification, đó là dấu hiệu cần trích abstraction hoặc event.

Root có thể biết toàn bộ các module được ghép để chạy ứng dụng, nhưng các module không cần nắm toàn bộ bản đồ.

## 9. Đọc vòng trong stack trace và bean graph

Khi context không khởi tạo, lỗi cấp cao có thể là:

```text
BeanCreationException
  -> UnsatisfiedDependencyException
     -> BeanCurrentlyInCreationException
```

Không phải mọi lần đều có đúng chuỗi wrapper này; exception type và mức bọc phụ thuộc giai đoạn lỗi và cách bean được tạo. Điều quan trọng là đọc **root cause** và những đoạn cho biết “A phụ thuộc B, B phụ thuộc A”.

Ví dụ mô tả:

```text
serviceA
   |
   v
serviceB
   |
   v
serviceA  (currently in creation)
```

Nếu node vòng là **beans**, cần tìm constructors/factory-method parameters/field injection đang gây yêu cầu hai chiều. Nếu node vòng là **configuration classes** import lẫn nhau, lỗi có thể phát sinh trong configuration parser **trước khi có bean instances**. Nếu node là **configuration instance và locally defined bean**, xem constructor/`@PostConstruct` hoặc early injection vào config.

### Bảng nhận diện nhanh

| Dấu hiệu | Vòng có thể nằm ở đâu? | Hướng kiểm tra |
| --- | --- | --- |
| Thông báo `A circular @Import has been detected` | Import graph | Các `@Import` trực tiếp/meta-present, import chain |
| `BeanCurrentlyInCreationException` cho tên hai service | Constructor/factory dependency graph | Constructor của service, tham số `@Bean`, hidden service locator |
| Exception nêu configuration bean và locally defined bean | Early creation/self-reference của config | Constructor config, `@Autowired` field, `@PostConstruct` |
| Lỗi sau khi đổi `proxyBeanMethods=false`, object duplicate | Direct `@Bean` calls trong lite mode | Thay bằng factory method parameters |
| `BeanCreationException` khi @Bean static post-processor | Infrastructure bootstrap/lifecycle | Declaration static/non-static, constructor side effects |
| Lỗi khi chỉ enable một profile | Conditional bean graph | `@Profile`, bean availability trong profile đó |
| Chỉ lỗi khi test dùng subset cấu hình | Missing definitions hoặc vòng bị cấu hình test phơi lộ | Root imports, test slices, mock bean replacements |

**Không sửa theo tên exception đơn thuần.** `UnsatisfiedDependencyException` còn có thể do bean thiếu, nhiều ứng viên, sai qualifier hoặc lỗi constructor; nó không chứng minh có vòng nếu thiếu dấu hiệu cụ thể về currently-in-creation.

## 10. @Import và @ComponentScan: ranh giới cần hiểu

Một configuration class có thể được đưa vào context bằng:

- `AnnotationConfigApplicationContext(RootConfig.class)`.
- `@Import(SomeConfig.class)` từ config khác.
- Component scanning khi class có `@Configuration` (meta-annotated bằng `@Component`) nằm trong root scan.
- Cơ chế bootstrap/import selector của framework phù hợp.

Nhiều **đường dẫn đăng ký** đến cùng configuration class không nhất thiết tạo nhiều bản bean nếu Spring nhận diện cùng definition; tuy nhiên, đừng dựa vào sự trùng lặp import để tạo thứ tự hoặc “giải vòng” kỳ diệu.

### Tránh quét quá rộng trong một hệ module phức tạp

```java
@ComponentScan(basePackages = "com.company")
```

có thể đưa vào nhiều configuration classes mà ứng dụng không dự định dùng cùng nhau. Điều này đôi khi kích hoạt bean definitions mới, nhập nhằng về type hoặc các cấu hình phụ thuộc ngược mà một root import rõ ràng sẽ không chọn.

Nếu cần module boundaries chặt, hãy dùng import có chủ đích hoặc component scan giới hạn theo feature. Nhưng không nên hiểu “component scan gây vòng” trong mọi trường hợp: vòng thực sự đến từ **dependency graph** sau khi các beans/configs được chọn.

### @Import vòng không đồng nghĩa bean vòng

Một import graph không có vòng không bảo đảm bean graph không có vòng. Ngược lại, hai service beans không phụ thuộc nhau vẫn có thể nằm trong hai config classes bị import lẫn nhau.

Đó là lý do QA cần kiểm tra cả **composition** và **dependency wiring**, không chỉ cách tổ chức các tệp `@Configuration`.

## 11. Vòng service nghiệp vụ cần được phá ở tầng thiết kế

Nếu:

```text
OrderService ---> PaymentService
PaymentService ---> OrderService
```

thì việc thay `@Import`, chuyển `@Bean` sang một file khác, hay đổi `proxyBeanMethods` sẽ không tự loại bỏ nhu cầu hai chiều. Thường cần một trong các hướng:

### 11.1. Tách trách nhiệm chung thành một bean thứ ba

Trước:

```text
OrderService <----> PaymentService
```

Sau:

```text
OrderService ----> PaymentPolicy <---- PaymentService
```

Mỗi service phụ thuộc một abstraction chung `PaymentPolicy`, không cần inject service còn lại.

### 11.2. Trích coordinator/use case ở tầng cao

```text
          CheckoutCoordinator
             /        \
            v          v
       OrderService  PaymentService
```

Coordinator gọi hai services theo trình tự use case, thay vì mỗi service yêu cầu service kia được tạo trước. Cách này đặc biệt phù hợp khi vòng đến từ **orchestration** chứ không phải dependency logic thật sự.

### 11.3. Dùng event để thông báo, không gọi ngược trực tiếp

Một service thực hiện hành động rồi phát domain/application event; component khác phản ứng theo lifecycle, transaction và idempotency đã được thiết kế. Điều này có thể giảm coupling, nhưng event không miễn trừ việc thiết kế thứ tự, lỗi, tính nhất quán dữ liệu và transaction boundary.

### 11.4. Làm rõ interface hướng vào

Nếu repository cần gọi service nghiệp vụ để quyết định logic, có thể tầng dữ liệu đang phụ thuộc ngược vào tầng ứng dụng. Hãy đưa policy/rule xuống abstraction thích hợp hoặc cung cấp tham số cho repository method, không buộc repository inject toàn bộ service.

**Quan trọng:** “Phá vòng” đúng nghĩa là làm đồ thị dependency **không còn cạnh quay lại node đã có trên đường đi**, không chỉ làm Spring trì hoãn phát hiện lỗi.

## 12. @Lazy có giúp không?

`@Lazy` có thể trì hoãn việc phân giải một dependency injection point qua proxy trong một số trường hợp.

Ví dụ minh họa:

```java
class ServiceA {
    ServiceA(@Lazy ServiceB serviceB) {
        this.serviceB = serviceB;
    }
}

class ServiceB {
    ServiceB(ServiceA serviceA) {
        this.serviceA = serviceA;
    }
}
```

Nếu Spring inject proxy cho `ServiceB` thay vì tạo bean B ngay, có thể tránh yêu cầu khởi tạo B tức thời khi tạo A. Nhưng:

- Đây vẫn là **dependency logic hai chiều**.
- Khi proxy bị dereference quá sớm hoặc trong init/constructor, vòng có thể xuất hiện trở lại.
- Có các giới hạn type/proxying (ví dụ final types hoặc semantics của proxy).
- Việc trì hoãn không giải quyết coupling, ownership của state hay trách nhiệm nghiệp vụ.
- Nó không giải quyết vòng `@Import` giữa configuration classes.

**Khuyến nghị:** `@Lazy` là công cụ chọn thời điểm resolution khi dependency thật sự nên lazy, **không phải cách mặc định để che mọi circular reference**.

## 13. ObjectProvider và Provider: trì hoãn lookup có điều kiện

Nếu một service chỉ cần cộng tác viên tại **thời điểm thực thi một thao tác**, có thể tiêm:

```java
import org.springframework.beans.factory.ObjectProvider;

class DeferredClient {
    private final ObjectProvider<RemoteGateway> gatewayProvider;

    DeferredClient(ObjectProvider<RemoteGateway> gatewayProvider) {
        this.gatewayProvider = gatewayProvider;
    }

    String sendLater(String message) {
        RemoteGateway gateway = gatewayProvider.getObject();
        return gateway.send(message);
    }
}
```

Đây là minh họa cần `RemoteGateway` interface. `ObjectProvider` cho phép lấy bean khi method `sendLater` được gọi, thay vì buộc resolve trong constructor.

Nhưng:

- Nếu `getObject()` được gọi trong constructor hoặc `@PostConstruct`, bạn vẫn có thể tái tạo early creation cycle.
- Nếu vòng chỉ được tránh vì các method chưa được gọi cùng lúc, cấu trúc kiến trúc có thể vẫn bất ổn.
- `getIfAvailable()` và `getIfUnique()` phù hợp cho **dependency tùy chọn thật**, không nên dùng để âm thầm bỏ qua dependency bắt buộc nhằm làm context start thành công.
- Nó không thay thế root composition cho import graph.
- Nếu bean đang là prototype/scoped, việc lookup theo thời điểm có tác động tới lifecycle/identity cần thiết kế riêng.

**Chỉ dùng provider** khi dynamic/lazy lookup là một yêu cầu thật của nghiệp vụ/hạ tầng, không phải để xóa thông báo lỗi vòng mà không thay đổi thiết kế.

## 14. @DependsOn không phải công cụ phá vòng

`@DependsOn` bổ sung **ràng buộc thứ tự khởi tạo bean**. Ví dụ:

```java
@Bean
@DependsOn("schemaValidator")
ReportService reportService() {
    return new ReportService();
}
```

Ý nghĩa: Bean `schemaValidator` phải được khởi tạo trước khi Spring khởi tạo `reportService`, bên cạnh các dependency trực tiếp của report service. Nó không cung cấp instance thay thế cho một constructor cần dependency, và không làm vòng A→B→A trở thành có thể khởi tạo.

Nếu:

```text
A --dependsOn--> B
B --dependsOn--> A
```

thì bạn đã tạo **vòng thứ tự**. Spring không thể vừa khởi tạo A trước B vừa khởi tạo B trước A. Việc đổi sang `@DependsOn` thay vì constructor injection không phải giải pháp khi hai bean thật sự cần reference tới nhau.

Dùng `@DependsOn` cho yêu cầu ordering có nghĩa thực sự, ví dụ một component hạ tầng cần bước validation đã hoàn thành; đừng dùng nó như orchestration nghiệp vụ hay dependency inversion.

## 15. Có nên bật cho phép circular references?

Spring Boot có thuộc tính:

```properties
spring.main.allow-circular-references=true
```

Từ các phiên bản Spring Boot hiện đại, mặc định tùy chọn này thường là `false`. Tuy nhiên, bài này phân biệt rõ **Spring Framework Core** và **Spring Boot**:

- `spring.main.allow-circular-references` là **cấu hình Spring Boot**, không phải cú pháp cấu hình trực tiếp của `AnnotationConfigApplicationContext` trong Spring Framework thuần.
- Một số circular dependencies thông qua setter/field injection có thể được Spring BeanFactory giải quyết bằng early references khi cơ chế hỗ trợ cho phép.
- **Constructor-to-constructor cycles** như A(B)→B(A) vẫn thường bất khả giải, kể cả khi đã bật cho phép circular references.
- Circular `@Import` của configuration parser không phải điều có thể sửa chỉ bằng bean factory flag.
- Early references có thể tương tác khó với AOP proxies, init callbacks và incomplete state.

**Kết luận:** Đừng bật cờ này như “fix” mặc định. Nó là biện pháp tương thích tạm thời trong một số migration, cần test và kế hoạch refactor. Về lâu dài, sửa **hướng dependency** vẫn tốt hơn.

### Nếu dùng plain Spring Framework

Một `DefaultListableBeanFactory`/`AbstractAutowireCapableBeanFactory` có các tùy chọn circular reference handling ở tầng bean factory. Đây là API cấu hình hạ tầng, không nên là bước đầu tiên trong khắc phục thiết kế dependency vòng.

Với ví dụ runnable mục 8, không cần bật bất kỳ cơ chế cho phép vòng nào; bean graph đã không có chu trình.

## 16. Một số bẫy chuyên biệt của @Configuration

### 16.1. Constructor injection của config kéo theo bean do chính nó định nghĩa

```java
@Configuration
class FeatureConfig {

    FeatureConfig(FeatureRegistry registry) {
        // ...
    }

    @Bean
    FeatureRegistry registry() {
        return new FeatureRegistry();
    }
}
```

Nếu không có bean `FeatureRegistry` khác hợp lệ, constructor config đòi bean mà nó phải được tạo xong mới có thể xây. Đây là dấu hiệu self-reference cycle. Đừng chuyển injection xuống field `@Autowired` rồi xem là đã chắc chắn giải quyết: field injection có thể gây early initialization và incomplete state.

### 16.2. @PostConstruct của configuration class gọi @Bean

Như đã nêu ở mục 6, Spring docs lưu ý rõ việc truy cập locally defined beans trong `@PostConstruct` của cùng configuration class có thể khiến circular reference. Đưa việc chuẩn bị trạng thái vào lifecycle bean đích hoặc một startup coordinator riêng.

### 16.3. BeanFactoryPostProcessor và BeanPostProcessor

Những post-processors này tham gia **rất sớm** vào container bootstrap. Nếu chúng được định nghĩa bằng **non-static `@Bean`**, việc tạo chúng có thể buộc Spring instantiate configuration class sớm, khiến `@Autowired`/`@Value` trên chính configuration class chưa được xử lý như mong đợi.

Một số post-processor beans thường nên dùng **static `@Bean`** để không cần tạo instance config sớm. Nhưng chỉ làm vậy khi bạn đang định nghĩa loại bean infrastructure đó, không phải trên mọi service.

### 16.4. @Configuration(proxyBeanMethods=false) không giải quyết vòng import

Cờ này tắt CGLIB interception của `@Bean` methods; nó không sửa việc ConfigA import ConfigB rồi ConfigB import ConfigA. Cần sửa **composition graph** riêng.

### 16.5. @ImportResource cũng không làm vòng tự biến mất

Nếu XML bean definitions tạo bean A phụ thuộc B, bean B lại phụ thuộc A qua constructors, thì nhập XML bằng `@ImportResource` vào Java context vẫn tạo **vòng dependency beans**. Thay vị trí metadata từ XML sang Java hoặc ngược lại không tự thay đổi đồ thị nhu cầu giữa các instances.

## 17. Cách debug vòng từ một ứng dụng lớn

Khi nhìn thấy thông báo circular dependency, nên làm theo một quy trình hữu hạn:

1. **Xác định thời điểm lỗi:** configuration parsing hay bean instantiation?
2. **Ghi lại tên node:** config class names, bean names, factory methods được liệt kê trong exception.
3. **Vẽ cạnh phụ thuộc:** `@Import`; config constructor; `@Bean` method parameter; service constructor; `@DependsOn`; lookup trong init.
4. **Phân loại vòng:** import graph, config instance graph hay application bean graph.
5. **Tìm nguyên nhân cấu trúc:** module biết lẫn nhau, trách nhiệm chung chưa được trích, bean tự phụ thuộc vào factory config của nó, hoặc code gọi sớm.
6. **Chọn refactor nhỏ nhất có ý nghĩa:** root composition, phương thức `@Bean` nhận tham số, trích interface/coordinator, chuyển startup work khỏi config init.
7. **Chạy context test:** tạo `AnnotationConfigApplicationContext` với đúng root, không dựa vào unit test chỉ dùng `new`.
8. **Kiểm tra identity:** instance được consumer giữ phải giống managed singleton nếu scope yêu cầu.
9. **Test cấu hình theo profile:** một graph có thể chỉ có vòng trong một profile cụ thể.
10. **Chỉ cân nhắc workaround lazy/provider** nếu dependency có ngữ nghĩa lazy thật và đã hiểu rủi ro.

### Đừng chỉ xóa một cạnh để context khởi động

Ví dụ bỏ dependency trong constructor nhưng chuyển sang `ApplicationContext.getBean` ở một method init có thể chỉ dời lỗi sang thời điểm khác. Code trở nên khó test hơn và vòng logic vẫn tồn tại.

Một refactor đúng nên khiến người đọc có thể nhìn vào constructors/factory methods và thấy **đồ thị có hướng không quay về chính nó**, hoặc có một abstraction/coordinator rõ ràng giải thích vì sao không cần hai chiều.

## 18. Kiểm thử chống regression

Một integration test nhỏ có thể khởi tạo root configuration rồi lấy bean:

```java
// Đoạn minh họa, không phải file test standalone.
try (var context =
        new AnnotationConfigApplicationContext(RootConfig.class)) {
    CatalogRepository repository =
            context.getBean(CatalogRepository.class);
    CatalogService service =
            context.getBean(CatalogService.class);

    if (service.repository() != repository) {
        throw new AssertionError(
                "Service must use the managed repository singleton");
    }
}
```

Trong project ví dụ, các class là nested classes của `CycleFreeConfigDemo`, vì thế khi viết ở file test độc lập cần import `demo.CycleFreeConfigDemo.RootConfig` và các nested types phù hợp.

### Kiểm tra chỉ đúng các modules mong muốn đã được nạp

Với ứng dụng thật, tạo context từ **root cấu hình duy nhất** và kiểm tra số bean names cho các interfaces chính. Nếu một class config vô tình được import thêm module phụ, test sẽ phát hiện số ứng viên thay đổi hoặc bean graph thất bại.

### Kiểm tra các profiles khác nhau

Nếu module có `@Profile("dev")` hoặc `@Profile("prod")`, mỗi profile có thể dẫn tới tập beans khác nhau. Hãy tạo context test riêng cho những cấu hình có rủi ro, đảm bảo đủ dependency, không có vòng và không import duplicate application modules.

### Cố ý tái hiện lỗi ở môi trường test

Không đưa các phản ví dụ vòng vào root production. Có thể tạo configuration classes riêng trong test để assert rằng context **fail fast** với constructor cycle hoặc circular import. Khi kiểm tra lỗi, đừng phụ thuộc quá chặt vào toàn bộ chuỗi stack trace, vì wrapper messages có thể thay đổi theo phiên bản Spring.

### Kiểm tra init callbacks

Nếu từng có self-reference trong `@PostConstruct` của config, regression test nên chứng minh init đã được chuyển sang managed bean hoặc coordinator và không ép context tạo bean quá sớm.

### Kiểm tra fail-fast của dependency bắt buộc

Một repository thiếu trong cấu hình test nên khiến tạo service bean thất bại rõ. Đừng biến dependency bắt buộc thành `Optional`/`ObjectProvider.getIfAvailable()` rồi im lặng bỏ qua chỉ để context “xanh”.

## 19. Câu hỏi thường gặp

### Có bắt buộc mọi module chỉ có một configuration class?

Không. Một module có thể có vài configurations theo trách nhiệm khác nhau. Điều quan trọng là **định hướng import/ownership rõ**, không phải số class tuyệt đối.

### Có phải hai config import nhau luôn tạo vòng bean constructor?

Không. Import graph là cấu trúc xử lý metadata, bean dependency graph là cấu trúc tạo instances. Circular import có thể lỗi ở configuration parser, dù bean constructors không phụ thuộc nhau.

### Nếu root import nhiều configs thì tạo nhiều BeanFactory?

Không. Khi một `AnnotationConfigApplicationContext` xử lý `RootConfig` và các `@Import` của nó, những bean definitions ở trong **cùng container** trừ khi chính code tạo những contexts riêng một cách có chủ đích.

### Nếu ServiceConfig dùng Repository bean thì có phải import RepositoryConfig trực tiếp không?

Không, nếu một root đã import cả hai. Tham số `@Bean service(Repository repository)` cho phép Spring inject bean cùng context theo type.

### Dùng full @Configuration gọi bean method khác có sai không?

Không mặc định sai. Full configuration cho phép inter-bean references thông qua CGLIB enhancement khi gọi trên managed config instance. Tuy nhiên, **method parameter injection** vẫn dễ đọc, ít coupling hơn và an toàn nếu sau này chuyển sang lite mode.

### Có cần @DependsOn để ép repo tạo trước service?

Nếu service factory method nhận `Repository` bắt buộc, Spring đã biết dependency và tạo/resolve nó khi cần. Không cần thêm `@DependsOn` chỉ để lặp lại quan hệ dependency có sẵn.

### Bật allow-circular-references có giúp constructor A(B), B(A) không?

Không nên trông chờ. Constructor cycles cần cả hai instances trước khi một instance có thể hoàn tất; đây là tình huống bất khả giải thông thường ngay cả khi một số vòng setter/field có thể được cơ chế early references xử lý.

### Có nên inject ApplicationContext vào config để tự lấy bean?

Thường không. Nó che dependency trong code và khiến test khó hơn. Tại factory method, hãy yêu cầu bean bằng tham số. Nếu cần dynamic lookup thật, dùng `ObjectProvider<T>` ở bean có trách nhiệm runtime tương ứng, không ở config init.

### Nếu một config bị @Import từ hai nhánh?

Spring có cơ chế xử lý configuration classes và imported definitions, nhưng không nên dùng đường import trùng để điều khiển thứ tự hoặc duplicate instances. Hãy thử với root context thật và làm rõ ownership. Một root import danh sách module trực tiếp thường dễ kiểm tra hơn.

### Một vòng chỉ xuất hiện ở production vì sao?

Khác biệt profiles, conditional beans, component scan root, auto-configuration, config properties, hoặc một implementation phụ thuộc ngược khác có thể tạo dependency graph mới. Integration tests cần đại diện các biến thể cấu hình quan trọng.

## 20. Bài tập có đáp án

### Bài 1 — Nhận diện vòng import

Hai class:

```java
@Configuration
@Import(BConfig.class)
class AConfig {}

@Configuration
@Import(AConfig.class)
class BConfig {}
```

Đây là loại vòng gì? Sửa thế nào để hai module đều được nạp?

**Đáp án:** Vòng **import graph**. Bỏ imports hai chiều, tạo `RootConfig` với `@Import({AConfig.class, BConfig.class})`, hoặc chọn một direction hợp lý nếu thật sự có hierarchy. Không cần inject instance config.

### Bài 2 — Nhận diện vòng constructor giữa config

```java
@Configuration
class AConfig {
    AConfig(BConfig b) {}
}

@Configuration
class BConfig {
    BConfig(AConfig a) {}
}
```

Vì sao Spring không khởi tạo được hai config instances?

**Đáp án:** Mỗi constructor yêu cầu instance của class kia đã tồn tại; BeanFactory không có điểm bắt đầu để hoàn tất construction. Refactor để configs không inject nhau, sử dụng bean method parameters cho dependency nghiệp vụ.

### Bài 3 — Module service dùng repository bean

Bạn có `RepositoryConfig` tạo `AccountRepository` và `ServiceConfig` tạo `AccountService`. Làm sao tránh `ServiceConfig` phải giữ `RepositoryConfig` field?

**Đáp án:**

```java
@Configuration(proxyBeanMethods = false)
class ServiceConfig {
    @Bean
    AccountService accountService(AccountRepository repository) {
        return new AccountService(repository);
    }
}
```

Root import cả hai config classes. Spring inject repository bean qua tham số factory method.

### Bài 4 — @PostConstruct của config

Một `@Configuration` tự gọi `dataSource()` trong `@PostConstruct`, trong khi `dataSource()` cũng là non-static `@Bean` method của nó. Vì sao rủi ro?

**Đáp án:** Config instance còn trong giai đoạn initialization; bean do method nó sản xuất có thể cần chính config instance đã được tạo/hoàn tất, dẫn tới self-reference/early initialization và `BeanCurrentlyInCreationException`. Nên dùng bean-local `initMethod`/`@PostConstruct` của bean đích hoặc một startup coordinator.

### Bài 5 — Dùng @Lazy để “sửa vòng”

Một service A cần B trong constructor, B cần A trong constructor. Đánh `@Lazy` vào injection point B có phải đã sửa dependency design?

**Đáp án:** Không. Nó có thể trì hoãn phân giải thông qua proxy ở một số trường hợp, nhưng quan hệ hai chiều vẫn tồn tại và có thể lỗi khi dereference sớm. Tốt hơn là trích abstraction hoặc coordinator.

### Bài 6 — @DependsOn

`A` có `@DependsOn("b")` và `B` có `@DependsOn("a")`. Điều gì xảy ra về logic ordering?

**Đáp án:** Không có thứ tự khởi tạo thỏa cả hai yêu cầu. Đây là vòng ordering; bỏ cạnh sai hoặc mô hình hóa quan hệ dependency theo hướng thực tế.

### Bài 7 — Lite config

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    Repo repo() { return new Repo(); }

    @Bean
    Service service() { return new Service(repo()); }
}
```

Rủi ro gì và sửa thế nào?

**Đáp án:** `repo()` gọi trực tiếp là Java factory call, có thể tạo repo ngoài managed bean identity. Sửa thành `Service service(Repo repo) { return new Service(repo); }`. Việc sửa này bảo toàn DI semantics nhưng nếu `Repo` phụ thuộc ngược `Service` thì vẫn cần phá vòng bean thật.

### Bài 8 — Đọc sơ đồ

```text
RootConfig -> InfraConfig
RootConfig -> RepositoryConfig
RootConfig -> ServiceConfig

Bean graph:
Facade -> Service -> Repository
                  -> Clock
```

Có vòng không?

**Đáp án:** Không trong các cạnh đã mô tả. Root import một chiều, bean graph không quay lại node cũ.

### Bài 9 — Spring Boot

Ứng dụng Spring Boot đặt `spring.main.allow-circular-references=true` để giải lỗi giữa hai services constructor-inject lẫn nhau. Có nên coi đây là cách sửa bền vững?

**Đáp án:** Không. Một số vòng constructor vẫn bất khả giải; cờ chỉ liên quan cơ chế xử lý một số circular bean references, không sửa import graph hay kiến trúc. Phải refactor dependencies.

### Bài 10 — Thiết kế đúng cho import composition

Hệ thống có `DbConfig`, `MessagingConfig`, `OrdersConfig`; `OrdersService` cần `DataSource` và `MessagePublisher`. Hãy đề xuất tổ chức.

**Đáp án định hướng:**

```java
@Configuration(proxyBeanMethods = false)
@Import({
    DbConfig.class,
    MessagingConfig.class,
    OrdersConfig.class
})
class RootConfig {
}

@Configuration(proxyBeanMethods = false)
class OrdersConfig {
    @Bean
    OrdersService ordersService(
            DataSource dataSource,
            MessagePublisher publisher) {
        return new OrdersService(dataSource, publisher);
    }
}
```

Đây là mẫu cần các kiểu được định nghĩa riêng. `OrdersConfig` không import ngược Db/Messaging config chỉ để lấy instance. Dependency được giải quyết từ BeanFactory chung theo parameters. Nếu `DbConfig` hoặc `MessagingConfig` phụ thuộc ngược `OrdersService`, đó là tín hiệu cần điều chỉnh trách nhiệm/abstraction.

### Bài 11 — Thứ tự bean creation

Nếu `@Bean Service service(Repository repo)` được Spring gọi, có cần khai báo `@DependsOn("repo")` để repo có trước không?

**Đáp án:** Không khi `Repository` được tiêm như tham số bắt buộc; BeanFactory giải quyết repository trước khi có thể gọi factory method tạo Service.

### Bài 12 — Test đồ thị

Bạn được giao refactor ba configs để loại vòng. Test tối thiểu cần kiểm tra gì?

**Đáp án:** Tạo context từ root mới; lấy các core bean types; assert dependency identity nếu singleton; kiểm tra tổng số bean names và hành vi service; thử profile/conditional variants liên quan; xác nhận không cần bật allow-circular-references hoặc dùng providers để che thiếu dependency.

## 21. Checklist review trước khi ghép cấu hình

- [ ] Có một hoặc một số **entry-point/root configs** rõ ràng, không tạo import ngược vô tình.
- [ ] Mỗi module config chủ yếu khai báo bean definitions thuộc trách nhiệm riêng.
- [ ] Không inject `RepositoryConfig` vào `ServiceConfig` chỉ để gọi phương thức `@Bean`.
- [ ] Khi bean service cần repository, dùng constructor hoặc **factory-method parameter injection**.
- [ ] Không inject một bean vào constructor config nếu chính config này phải sản xuất bean đó.
- [ ] Không gọi locally defined bean từ `@PostConstruct` của config class.
- [ ] Những `BeanFactoryPostProcessor`/`BeanPostProcessor` tạo quá sớm đã được cân nhắc `static @Bean` khi phù hợp.
- [ ] Full/lite configuration semantics được hiểu; không direct-call `@Bean` trong lite để lấy managed object.
- [ ] Không dùng `@DependsOn` để che vòng dependency thực.
- [ ] `@Lazy`/`ObjectProvider` chỉ xuất hiện khi có lazy/dynamic lookup requirement thật, không che vấn đề kiến trúc.
- [ ] Không dựa vào `spring.main.allow-circular-references` làm cách sửa mặc định.
- [ ] Context startup test xác nhận không có `BeanCurrentlyInCreationException`.
- [ ] Đồ thị dependencies theo từng profile/conditional config quan trọng đã được kiểm tra.
- [ ] Không tạo ApplicationContext phụ hoặc configuration instances bằng `new` trong `@Bean`.
- [ ] Mỗi resource có lifecycle rõ, không khởi tạo hai lần do direct method calls.
- [ ] Bean definitions không bị trùng tên/kiểu do import hoặc scan ngoài ý muốn.
- [ ] Có integration test cho bean identity và đường use case chính sau refactor.

## Kết luận

**Tránh phụ thuộc vòng giữa các lớp cấu hình** không có nghĩa phải dồn toàn bộ cấu hình vào một class. Điều cần làm là **tách cấu trúc ghép cấu hình khỏi cấu trúc dependency của bean**:

- `@Import` giúp **root composition** đưa nhiều cấu hình vào cùng context theo một hướng rõ ràng.
- `@Bean` method parameters cho phép bean ở một module nhận bean từ module khác **mà configuration classes không cần inject nhau**.
- Constructor/`@PostConstruct` trên `@Configuration` phải tránh tham chiếu quá sớm tới những bean do chính instance config đó sản xuất.
- Vòng constructor giữa application beans phải được sửa ở **tầng thiết kế service/abstraction/coordinator**, không chỉ đổi file config.
- `@Lazy`, `ObjectProvider`, `@DependsOn` và circular-reference flags có phạm vi riêng; chúng không thay thế cho đồ thị dependency đúng.

**Mẫu đáng nhớ:** root import các module; mỗi module khai báo factory methods; dependency giữa beans được Spring phân giải bằng tham số; không một module config nào phải gọi ngược sang config instance khác chỉ để lấy object.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html): `@Import`, dependency giữa imported configurations, cảnh báo early config initialization và `@PostConstruct`.
- [Spring Framework 6.2 — Dependency Injection and Circular Dependencies](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html): constructor cycle, bean creation và ý nghĩa của early references.
- [Spring Framework 6.2 — Basic Concepts: @Bean and @Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html): full/lite configuration modes.
- [Spring Framework 6.2 — Using the @Configuration Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html): inter-bean method references và CGLIB enhancement.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): factory method parameters, type metadata và lifecycle.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): `spring.main.allow-circular-references` thuộc Boot, không thuộc Spring Core configuration annotation.

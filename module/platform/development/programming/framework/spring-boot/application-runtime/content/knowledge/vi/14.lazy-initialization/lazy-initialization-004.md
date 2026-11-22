# Phân biệt khởi tạo lười toàn ứng dụng với @Lazy ở một phụ thuộc trong Spring Boot

## 1. Kết luận cốt lõi

Spring Boot có **ít nhất ba vị trí khác nhau** mà người học thường gọi chung là “lazy”, nhưng chúng không có cùng phạm vi hoặc cơ chế:

1. **Khởi tạo lười toàn ứng dụng**: cấu hình `spring.main.lazy-initialization=true` yêu cầu Spring Boot áp dụng lazy initialization rộng rãi cho những bean đủ điều kiện, thay vì tạo trước hầu hết singleton thông thường trong lúc startup.
2. **`@Lazy` trên định nghĩa bean**: đặt `@Lazy` trên `@Component`, trên phương thức `@Bean` hoặc trên một lớp `@Configuration` để thay đổi **thời điểm một bean được tạo**. Cơ chế này tác động đến bean definition được đánh dấu, không mặc nhiên thay đổi toàn ứng dụng.
3. **`@Lazy` tại điểm tiêm dependency (injection point)**: đặt `@Lazy` trên tham số constructor, field `@Autowired` hoặc phương thức injection được hỗ trợ. Spring tiêm **lazy-resolution proxy** vào đối tượng nhận dependency; proxy trì hoãn việc tìm/khởi tạo **target** đến khi target được sử dụng qua proxy.

Cả ba đều có thể khiến một số đối tượng được tạo muộn hơn, nhưng câu hỏi chúng giải quyết **khác nhau**:

- Global lazy: *Nhiều bean trong application context có cần được khởi tạo ngay khi refresh không?*
- Bean-definition `@Lazy`: *Bean cụ thể này có cần được pre-instantiate nếu chưa ai yêu cầu không?*
- Injection-point `@Lazy`: *Khi tạo bean A, có cần phân giải và tạo ngay bean B là dependency không?*

**Điểm quan trọng nhất:** `@Lazy` trên một dependency **không tự biến tất cả bean thành lazy**; `spring.main.lazy-initialization=true` **không tự bảo đảm mọi dependency đều chưa được tạo**; và `@Lazy` trên **bean definition** có thể không trì hoãn được bean nếu một singleton eager khác cần nó trực tiếp.

## 2. Nền tảng: singleton eager, singleton lazy và nhu cầu tạo bean

Theo mặc định, nhiều triển khai `ApplicationContext` trong Spring tạo trước các singleton không lazy trong quá trình `refresh()`. Điều này gọi là **pre-instantiation**: Spring có thể phát hiện sớm các lỗi constructor, injection, configuration hoặc lifecycle callback.

Giả sử có hai bean:

```text
OrderController  ----depends-on---->  PricingService
```

Với singleton không lazy ở cả hai phía, Spring có thể tạo cả hai trong giai đoạn refresh. Nếu `OrderController` cần `PricingService` qua constructor thì dependency thường phải được phân giải để controller có thể được tạo.

Một bean singleton được đánh dấu lazy không bị buộc phải pre-instantiate **chỉ vì nó tồn tại trong container**. Nhưng khi có consumer non-lazy bắt buộc cần target để hoàn thành constructor injection, Spring có thể **vẫn tạo bean lazy tại startup** để thỏa dependency.

```text
Bean A (eager) --constructor requires--> Bean B (@Lazy on definition)

refresh()
  -> tạo A
      -> A cần B ngay
          -> tạo B
      -> tạo xong A
```

Do đó **`@Lazy` không có nghĩa “bất kể ai yêu cầu cũng không tạo”**. Nó chủ yếu thay đổi **chính sách tạo sẵn**; yêu cầu thực tế từ dependency hoặc `getBean` vẫn có thể kích hoạt việc tạo target.

Ngược lại, nếu tham số constructor của A mang `@Lazy`, Spring có thể cung cấp một proxy thay vì buộc phải lấy B ngay:

```text
Bean A (eager) --injection-point @Lazy--> Proxy của B
                                              |
                                              +-- dùng lần đầu --> phân giải B
```

Hai sơ đồ trên giải thích vì sao **vị trí đặt annotation** quan trọng ngang với việc có annotation hay không.

## 3. Bảng so sánh ngắn

| Khía cạnh | Global lazy của Spring Boot | `@Lazy` trên bean definition | `@Lazy` trên injection point |
| --- | --- | --- | --- |
| Cách dùng | `spring.main.lazy-initialization=true` | `@Lazy` trên `@Component` / `@Bean` | `@Lazy` trên constructor parameter, field hoặc injection method |
| Phạm vi | Rộng trên các bean đủ điều kiện trong context | Một bean hoặc nhóm bean cấu hình | Một **đường phụ thuộc** của consumer |
| Tác động chính | Đánh dấu nhiều bean để hoãn pre-instantiation | Hoãn pre-instantiation của bean đã đánh dấu | Tiêm proxy hoãn phân giải target |
| Bean consumer có thể eager không? | Có, nếu bị yêu cầu hoặc loại trừ | Có | Có; consumer được tạo nhưng target có thể chưa |
| Phụ thuộc trực tiếp có thể ép tạo target? | Có | Có | Proxy có thể hoãn đến lần gọi target |
| Có tạo proxy mới tại injection? | Không phải bản chất của cờ global | Không phải bản chất của `@Lazy` trên definition | Có, lazy-resolution proxy |
| Một target singleton được gọi nhiều lần | Thường một singleton sau khi tạo | Tương tự | Proxy thường phân giải target singleton, không biến nó thành prototype |
| Cách opt out | `@Lazy(false)` cho bean thích hợp | Bỏ `@Lazy` hoặc dùng cấu hình eager | Bỏ `@Lazy` tại điểm tiêm và cân nhắc direct injection |
| Rủi ro chính | Lỗi bị phát hiện muộn trên phạm vi rộng | Lỗi của bean này có thể đến muộn | Thiếu target có thể chỉ lộ khi gọi proxy |

Cần đọc bảng theo ngữ cảnh Spring Boot 3.3.x / Spring Framework 6.1.x. Framework còn có những bean hạ tầng và callback buộc phải xử lý lúc startup; vì vậy **“lazy toàn ứng dụng” không có nghĩa 100% object sẽ chờ tới request đầu tiên**.

## 4. Global lazy: spring.main.lazy-initialization=true

Spring Boot hỗ trợ:

```properties
spring.main.lazy-initialization=true
```

Hoặc trong `application.yml`:

```yaml
spring:
  main:
    lazy-initialization: true
```

Cấu hình được áp dụng trong quá trình Spring Boot chuẩn bị và refresh application context. Mục tiêu là **giảm số bean cần tạo ngay lúc khởi động**, từ đó có thể giảm thời gian startup quan sát được.

Có thể bật bằng API:

```java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setLazyInitialization(true);
app.run(args);
```

Đoạn này là minh họa bên trong entry point, yêu cầu import `SpringApplication` và class `DemoApplication` đã được định nghĩa. Nếu sử dụng `SpringApplicationBuilder`, có thể dùng API `lazyInitialization(true)` tương ứng.

### 4.1. Những gì có thể thay đổi

Khi bật global lazy:

- Một số singleton ứng dụng không cần thiết ngay có thể **không được tạo tại startup**.
- Constructor, `@PostConstruct`, `InitializingBean.afterPropertiesSet()` và custom init method của bean bị hoãn sẽ chạy **khi bean thực sự được tạo**, không phải tại lúc refresh.
- Một web application có thể trì hoãn tạo các bean liên quan route/controller/service cho đến khi có request phù hợp.
- Một lỗi cấu hình hay dependency của bean lazy có thể chỉ xuất hiện trong một request đầu tiên hoặc một bước xử lý muộn.

### 4.2. Những gì không được bảo đảm

Cờ global **không** bảo đảm:

- Không có bean nào được tạo lúc startup. Bean hạ tầng, bean bắt buộc và dependency của các bean eager vẫn có thể được tạo.
- Mọi bean chỉ được tạo **sau HTTP request đầu tiên**. Runner, listener, scheduler, health probe, công việc startup hoặc bean khác có thể cần chúng trước.
- Mọi singleton lúc đầu là proxy. Global lazy chủ yếu là chính sách pre-instantiation; proxy tại injection point là cơ chế riêng.
- Giảm tổng thời gian làm việc của hệ thống. Công việc khởi tạo có thể chỉ **chuyển từ startup sang đường xử lý đầu tiên**.
- Tăng hiệu năng request. Request đầu gọi một bean lazy đắt đỏ có thể chậm hơn bình thường.
- Tất cả lỗi configuration đều bị hoãn. Spring vẫn xử lý metadata/định nghĩa bean trong refresh và một số lỗi vẫn xuất hiện sớm.

Spring Boot **không bật lazy initialization toàn ứng dụng theo mặc định**. Tài liệu chính thức lưu ý việc bật lazy có thể làm phát hiện lỗi muộn hơn và cần xem lại dung lượng heap khi các bean lần lượt được tạo trong lúc ứng dụng đang vận hành.

### 4.3. Thời điểm có hiệu lực

`spring.main.lazy-initialization` là một **chính sách khi xây dựng context**. Đổi giá trị property sau khi context đã refresh **không tự đổi những singleton đã được tạo thành lazy**, không hủy bean và không tự tạo một context mới.

Nếu muốn so sánh bật/tắt, hãy thực hiện **hai lần khởi động mới** với cấu hình khác nhau. Việc sửa file property trong khi ứng dụng đang chạy không phải một phép thử đúng.

## 5. @Lazy trên định nghĩa bean: hoãn khởi tạo một thành phần

### 5.1. Đặt trên @Component

```java
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Component;

@Component
@Lazy
public class ExpensiveClient {

    public ExpensiveClient() {
        System.out.println("ExpensiveClient constructed");
    }

    public String ping() {
        return "ok";
    }
}
```

Giả sử class nằm trong phạm vi component scanning. Khi **không có consumer eager yêu cầu nó**, context có thể bỏ qua việc tạo `ExpensiveClient` trong giai đoạn pre-instantiation.

Nếu sau đó có lời gọi:

```java
ExpensiveClient client = context.getBean(ExpensiveClient.class);
System.out.println(client.ping());
```

thì yêu cầu `getBean` sẽ **kích hoạt khởi tạo** nếu singleton chưa tồn tại. `@Lazy` không cấm việc tạo bean; nó chỉ hoãn cho đến khi có nhu cầu.

Đoạn trên cần biến `context` kiểu `ApplicationContext` hoặc tương thích; đây là snippet minh họa, không phải một chương trình đầy đủ.

### 5.2. Đặt trên @Bean

Có thể đặt annotation vào phương thức factory:

```java
@Configuration
public class ClientsConfig {

    @Bean
    @Lazy
    ExpensiveClient expensiveClient() {
        return new ExpensiveClient();
    }
}
```

Đây là một cách **thay thế** cho `@Component` trong ví dụ trước. Nếu vừa để `@Component` vừa khai báo cùng kiểu qua `@Bean` và cố inject theo kiểu đơn, cần xử lý khả năng có nhiều candidate; không nên sao chép cả hai vào một ứng dụng rồi kỳ vọng không ảnh hưởng.

Với lớp được tạo bởi một thư viện mà bạn không sửa được source, khai báo `@Bean @Lazy` thường là cách đơn giản để điều khiển bean definition.

### 5.3. Đặt trên @Configuration

```java
@Configuration
@Lazy
public class OptionalFeaturesConfig {

    @Bean
    FeatureCatalog featureCatalog() {
        return new FeatureCatalog();
    }

    @Bean
    @Lazy(false)
    RequiredFeatureMetadata requiredFeatureMetadata() {
        return new RequiredFeatureMetadata();
    }
}
```

Đây là **minh họa về annotation**, yêu cầu hai kiểu `FeatureCatalog` và `RequiredFeatureMetadata` tồn tại, cùng import `Configuration`, `Bean` và `Lazy`. Khi `@Lazy` đặt trên configuration class, các `@Bean` method trong class có thể mặc định lazy; `@Lazy(false)` trên method chỉ định ngoại lệ eager theo semantics của annotation.

**Không hiểu nhầm:** `@Lazy` trên configuration class không phải cờ lazy toàn bộ Spring Boot application. Nó tác động tới phạm vi cấu hình liên quan; property `spring.main.lazy-initialization` mới là lựa chọn ở cấp SpringApplication.

## 6. @Lazy ở injection point: chèn proxy hoãn phân giải target

Đây là trọng tâm của đề bài. Hãy xem constructor injection:

```java
@Component
public class ReportController {

    private final ReportGateway gateway;

    public ReportController(@Lazy ReportGateway gateway) {
        this.gateway = gateway;
    }

    public String report() {
        return gateway.loadReport();
    }
}
```

Đoạn này yêu cầu interface `ReportGateway` có phương thức `loadReport()`, cùng import `Component` và `org.springframework.context.annotation.Lazy`. Đây là snippet minh họa, không phải file hoàn chỉnh nếu chưa định nghĩa `ReportGateway`.

Dấu `@Lazy` **đặt trên tham số** `gateway`. Trong cơ chế autowiring được hỗ trợ, Spring cung cấp một **lazy-resolution proxy** cho dependency này. Điều đó cho phép `ReportController` được tạo **mà chưa cần tạo hoặc lấy target `ReportGateway` thật**, cho đến khi gọi method qua proxy.

```text
ReportController (có thể eager)
       |
       | constructor injection
       v
Proxy implements ReportGateway
       |
       | chưa gọi loadReport() -> chưa cần phân giải target qua đường này
       |
       +-- loadReport()
               |
               v
        Resolve ReportGateway bean
               |
               +-- Nếu singleton chưa tồn tại: tạo singleton
               +-- Gọi method trên target thật
```

**Đây không phải cùng tác động với `@Lazy` trên class `ReportGateway`.** Annotation ở parameter điều khiển **đường phân giải dependency của consumer**. Nếu target là một singleton thông thường *không lazy* và không có cờ global, container vẫn có thể tự tạo target lúc refresh do chính chính sách pre-instantiation của target.

### 6.1. Ví dụ chỉ đặt @Lazy ở dependency

Giả sử:

```java
@Component
class PaymentService {

    PaymentService() {
        System.out.println("PaymentService created");
    }

    void pay() { }
}

@Component
class CheckoutService {

    private final PaymentService payment;

    CheckoutService(@Lazy PaymentService payment) {
        this.payment = payment;
        System.out.println("CheckoutService created");
    }
}
```

Đây là snippet minh họa với import `Component` và `Lazy`. Khi global lazy **tắt** và cả hai bean definition mặc định là singleton eager, `PaymentService` **vẫn có thể được tạo trong refresh** bất chấp constructor của `CheckoutService` nhận proxy. `@Lazy` trên tham số **không sửa thuộc tính lazy của bean definition `PaymentService`**.

Vì vậy câu “đặt `@Lazy` ở injection point thì target sẽ không bao giờ được tạo ở startup” là **sai** khi target vẫn là eager singleton và được pre-instantiate độc lập.

### 6.2. Kết hợp bean-definition lazy với injection-point lazy

Khi muốn consumer vẫn eager nhưng dependency chỉ tạo lần đầu thực sự sử dụng, kết hợp:

```java
@Component
@Lazy
class SlowGateway {

    SlowGateway() {
        System.out.println("SlowGateway constructed");
    }

    String fetch() {
        return "ready";
    }
}

@Component
class NormalConsumer {

    private final SlowGateway gateway;

    NormalConsumer(@Lazy SlowGateway gateway) {
        this.gateway = gateway;
    }

    String run() {
        return gateway.fetch();
    }
}
```

Đây là snippet hợp lệ khi cả hai class nằm trong một package có component scanning và đã import `Component` / `Lazy`. Cần tránh class/method `final` nếu kiểu dependency phải được Spring proxy theo class.

Vai trò từng annotation:

- `@Lazy` **trên `SlowGateway`**: đề nghị container **không pre-instantiate** gateway nếu chưa cần.
- `@Lazy` **trên constructor parameter của `NormalConsumer`**: consumer có thể nhận proxy mà **không buộc phân giải gateway ngay trong constructor**.
- Khi `normalConsumer.run()` gọi `gateway.fetch()` lần đầu, gateway singleton được phân giải và tạo nếu còn thiếu.

Nếu **chỉ có `@Lazy` trên class gateway** mà consumer eager nhận gateway trực tiếp, Spring cần tạo gateway để xây consumer và lazy có thể mất tác dụng trì hoãn. Nếu **chỉ có `@Lazy` ở parameter** mà gateway vẫn eager, Spring vẫn có thể tạo gateway trong refresh độc lập.

## 7. Ví dụ runnable Spring Boot 3.3 / Java 17+: chạy hai chế độ global lazy

Để nhìn rõ khác biệt, ví dụ dùng:

- `RemoteReportGateway`: singleton bình thường, **không `@Lazy` trên bean definition**.
- `ReportWorker`: singleton bình thường, nhận `@Lazy ReportGateway` ở constructor parameter.
- `main`: quan sát đã có **singleton instance** trước/sau khi lấy worker và trước/sau khi gọi method.

Cùng một source được chạy **hai lần trong hai tiến trình**: lần 1 tắt global lazy, lần 2 bật global lazy. Điều này tránh hiểu nhầm thời điểm tạo object.

### 7.1. Cấu trúc file

```text
lazy-comparison/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          lazy/
            LazyComparisonApplication.java
      resources/
        application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'lazy-comparison'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Đây là cấu hình cho một phiên bản Spring Boot 3.3 cụ thể; môi trường thực tế cần chọn phiên bản đang được bảo trì theo chính sách tổ chức. Dự án phải có Gradle wrapper/Gradle tương thích; việc tạo `build.gradle` không tự sinh `gradlew`.

`src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
spring.main.lazy-initialization=false
```

Chúng ta dùng app `NONE` để không cần web server và để tránh request hoặc bean web kích hoạt phụ thuộc trước lúc quan sát.

### 7.2. Java source hoàn chỉnh

File `src/main/java/demo/lazy/LazyComparisonApplication.java`:

```java
package demo.lazy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class LazyComparisonApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(LazyComparisonApplication.class, args)) {

            ConfigurableListableBeanFactory factory =
                    context.getBeanFactory();

            System.out.println("afterRun.gateway="
                    + factory.containsSingleton("remoteReportGateway"));
            System.out.println("afterRun.worker="
                    + factory.containsSingleton("reportWorker"));

            ReportWorker worker = context.getBean(ReportWorker.class);

            System.out.println("afterGetWorker.gateway="
                    + factory.containsSingleton("remoteReportGateway"));

            worker.execute();

            System.out.println("afterExecute.gateway="
                    + factory.containsSingleton("remoteReportGateway"));
        }
    }
}

interface ReportGateway {
    String fetch();
}

@Component
class RemoteReportGateway implements ReportGateway {

    RemoteReportGateway() {
        System.out.println("gateway.constructed");
    }

    @Override
    public String fetch() {
        System.out.println("gateway.fetch");
        return "ok";
    }
}

@Component
class ReportWorker {

    private final ReportGateway gateway;

    ReportWorker(@Lazy ReportGateway gateway) {
        this.gateway = gateway;
        System.out.println("worker.constructed");
    }

    void execute() {
        System.out.println("worker.result=" + gateway.fetch());
    }
}
```

Mã trên hợp lệ trong **một file Java**: chỉ `LazyComparisonApplication` là public top-level class; ba type còn lại package-private. Tất cả nằm cùng package `demo.lazy` để component scanning của `@SpringBootApplication` tìm thấy hai `@Component`.

**Vì sao dùng interface `ReportGateway`?** Điểm injection có kiểu interface, nên Spring có thể tạo proxy theo interface, tránh những vấn đề riêng khi phải proxy một class `final` hoặc method không thể override. `RemoteReportGateway` là implementation bean thật, được đặt tên mặc định `remoteReportGateway`; consumer có tên `reportWorker`.

**Vì sao dùng `containsSingleton`?** `ConfigurableListableBeanFactory.containsSingleton(String)` quan sát xem bean factory **đã chứa singleton instance được tạo** dưới tên đó chưa. Việc kiểm tra này không tương đương với `containsBean` (có bean definition hay không), và **không kích hoạt tạo bean** chỉ để trả lời.

Mã gọi `context.getBean(ReportWorker.class)` sau khi Spring Boot `run` hoàn thành. Đây là **lệnh tạo/lấy bean thật** và có thể khởi tạo consumer đang lazy. Trong demo, consumer chỉ giữ proxy và không gọi `fetch` trong constructor, nên nó không yêu cầu target qua proxy ở thời điểm này.

### 7.3. Lần 1: global lazy tắt

Chạy trong dự án có Gradle wrapper:

```bash
./gradlew bootRun
```

Do `spring.main.lazy-initialization=false`, `ReportWorker` và `RemoteReportGateway` đều là singleton thông thường. Các dòng do chương trình demo in ra gồm:

```text
gateway.constructed
worker.constructed
afterRun.gateway=true
afterRun.worker=true
afterGetWorker.gateway=true
gateway.fetch
worker.result=ok
afterExecute.gateway=true
```

**Lưu ý về output:** thứ tự **giữa hai dòng constructor** `gateway.constructed` và `worker.constructed` không phải hợp đồng cần dựa vào. Chúng có thể đảo vị trí tùy thứ tự xử lý bean definitions. Các dòng `afterRun...` chỉ xuất hiện sau khi cả hai singleton đã được tạo. Từ đó, thứ tự các dòng do `main` và `execute()` in ra đúng như ví dụ.

Giải thích:

- `RemoteReportGateway` **không mang `@Lazy` trên bean definition**.
- `@Lazy` trong constructor `ReportWorker` giúp consumer nhận proxy, nhưng **không yêu cầu container bỏ qua pre-instantiation riêng của gateway**.
- Kết quả `afterRun.gateway=true` chứng minh gateway đã là singleton trước khi code gọi `worker.execute()`.
- `afterGetWorker.gateway=true` không có nghĩa hành vi injection proxy vô hiệu; chỉ có nghĩa target đã tồn tại từ bước eager initialization.

Đây là minh chứng quan trọng nhất rằng **annotation ở một injection point và chính sách eager/lazy của bean definition là hai lớp khác nhau**.

### 7.4. Lần 2: global lazy bật

Để giữ nguyên source và đổi runtime config, chạy một tiến trình mới với override:

```bash
./gradlew bootRun --args='--spring.main.lazy-initialization=true'
```

Với Gradle và shell có quy tắc trích dẫn khác, sửa phần dấu nháy tương ứng. Có thể thay trực tiếp property trong `application.properties` thành `true` rồi khởi động tiến trình mới.

Phần các dòng do code demo in ra trong lượt chạy này:

```text
afterRun.gateway=false
afterRun.worker=false
worker.constructed
afterGetWorker.gateway=false
gateway.constructed
gateway.fetch
worker.result=ok
afterExecute.gateway=true
```

Giải thích từng điểm:

1. Sau `SpringApplication.run`, hai singleton ứng dụng chưa được yêu cầu nên `containsSingleton` trả `false`.
2. Lời gọi `context.getBean(ReportWorker.class)` tạo consumer, in `worker.constructed`.
3. Constructor nhận một **lazy-resolution proxy**, vì thế `RemoteReportGateway` vẫn chưa có singleton instance thật: `afterGetWorker.gateway=false`.
4. Khi `worker.execute()` gọi `gateway.fetch()` lần đầu, proxy phân giải bean `RemoteReportGateway`, constructor target chạy và in `gateway.constructed`.
5. Sau đó method target `fetch()` chạy, rồi consumer in `worker.result=ok`.
6. Cuối cùng `afterExecute.gateway=true` xác nhận singleton target đã tồn tại.

**Không suy rộng kết quả này thành mọi Spring Boot application**: demo chủ động loại bỏ runner, request, scheduled job và các bean khác có thể sử dụng gateway. Nếu có consumer khác gọi gateway từ startup, target vẫn có thể được tạo trước vị trí chúng ta quan sát.

### 7.5. So sánh trực tiếp hai lượt chạy

| Quan sát | Global lazy tắt | Global lazy bật |
| --- | --- | --- |
| `ReportWorker` đã có instance sau `run`? | Có | Chưa, vì không ai yêu cầu |
| `RemoteReportGateway` đã có instance sau `run`? | Có | Chưa |
| Lấy `ReportWorker` bằng `getBean` có tạo consumer? | Đã tồn tại, chỉ lấy lại | Có |
| Lấy consumer có buộc tạo gateway qua `@Lazy` injection? | Không cần phân giải ở bước đó; gateway đã eager | Không; target vẫn chưa tạo |
| Gọi `worker.execute()` có dùng target? | Có, target đã tồn tại | Có, proxy tạo target trước lần gọi |
| `@Lazy` trên constructor parameter có tác dụng gì? | Proxy vẫn được tiêm, nhưng target có thể đã eager | Proxy giúp trì hoãn target sau khi consumer được tạo |

Một điểm về đo đạc: log và `containsSingleton` chỉ cho biết trạng thái **trong demo**. Dùng nó để học cơ chế, không mặc định dùng introspection sâu trong service nghiệp vụ production.

## 8. Thí nghiệm then chốt: @Lazy trên bean definition có đủ không?

Giả sử global lazy **tắt**. Đánh dấu gateway:

```java
@Component
@Lazy
class RemoteReportGateway implements ReportGateway {
    // Constructor và fetch() như ví dụ chính.
}
```

Nếu `ReportWorker` được tạo eager nhưng **không có `@Lazy` tại tham số constructor**:

```java
@Component
class ReportWorker {

    private final ReportGateway gateway;

    ReportWorker(ReportGateway gateway) {
        this.gateway = gateway;
    }
}
```

thì Spring cần một `ReportGateway` thật để hoàn thành constructor injection, nên **gateway được tạo sớm dù bean definition mang `@Lazy`**.

Đây là tình huống rất quan trọng trong tài liệu Spring Framework về lazy singleton: **một bean lazy là dependency trực tiếp của một singleton không lazy vẫn có thể bị khởi tạo lúc startup**.

Nếu **giữ `@Lazy` trên gateway** và **đặt lại `@Lazy` trên tham số** của worker như demo chính, consumer có thể được tạo eager trong khi target được hoãn đến khi proxy bị sử dụng.

**Đừng dùng kết quả demo global lazy để khẳng định chỉ `@Lazy` trên bean definition là đủ**: với global lazy, cả consumer cũng thường lazy; tình huống dependency eager có thể không xuất hiện. Muốn kiểm thử ảnh hưởng bean-definition `@Lazy`, hãy chạy global lazy tắt và thay đổi riêng annotation của bean/constructor.

## 9. Bảng ma trận: hai nút điều khiển khác nhau

Giả định tất cả là singleton, consumer được yêu cầu tạo tại một thời điểm, không có consumer thứ hai, và target không bị một hạ tầng khác yêu cầu trước đó.

| Target bean definition | Injection point vào consumer | Khi consumer được tạo, target có bị buộc tạo qua dependency đó không? |
| --- | --- | --- |
| Eager, không `@Lazy` | Trực tiếp | Có, nếu chưa được tạo sẵn |
| Eager, không `@Lazy` | `@Lazy` trên tham số | **Không cần qua đường injection này**, nhưng target vẫn có thể được pre-instantiate độc lập |
| `@Lazy` trên target | Trực tiếp | Có, nếu consumer cần target thật để tạo |
| `@Lazy` trên target | `@Lazy` trên tham số | Thường có thể hoãn cho đến lần sử dụng proxy |

Khi toàn ứng dụng bật lazy, nhiều bean definitions đi vào trường hợp lazy tương tự hàng 3 hoặc 4, **nhưng các ngoại lệ eager và bean hạ tầng vẫn tồn tại**. Vì vậy hãy đọc bảng như một mô hình giải thích **chính sách tạo bean vs cơ chế dependency proxy**, không phải một cam kết tất cả instance luôn xuất hiện vào cùng một timestamp.

Một cách ghi nhớ cực ngắn:

```text
@Lazy trên BEAN
    -> "Đừng tự tạo tôi khi chưa cần."

@Lazy trên DEPENDENCY
    -> "Khi tạo consumer, hãy đưa proxy trước; tìm target sau."

spring.main.lazy-initialization=true
    -> "Áp dụng chính sách lazy rộng cho các bean đủ điều kiện."
```

## 10. @Lazy(false): muốn một số bean vẫn eager khi bật global lazy

Spring Boot cho phép **chỉ định ngoại lệ**:

```java
@Component
@Lazy(false)
public class CriticalStartupVerifier {

    public CriticalStartupVerifier() {
        System.out.println("Verifier initialized");
    }
}
```

Đoạn này cần import `Component` và `Lazy` và file `CriticalStartupVerifier.java` thuộc package được quét. Khi global lazy được bật, một bean definition được đánh dấu rõ `@Lazy(false)` có thể vẫn được khởi tạo eager theo quy tắc Spring Boot.

Tình huống phù hợp:

- Một bean rất quan trọng cần phát hiện lỗi khởi tạo trước khi tuyên bố startup thành công.
- Thành phần hạ tầng cần chuẩn bị ngay để không tạo độ trễ bất ngờ trên request đầu.
- Một kiểm tra bắt buộc liên quan readiness hay điều kiện thực thi.

**Không dùng `@Lazy(false)` tràn lan** nếu mục tiêu vẫn là trì hoãn nhiều bean. Việc đánh dấu quá nhiều bean eager làm mất lợi ích của global lazy, và sự eager của chúng có thể kéo theo nhiều dependency.

### Một bẫy khi kết hợp @Lazy(false) và @Lazy tại injection

Giả sử `CriticalStartupVerifier` được đánh dấu `@Lazy(false)`, nhưng consumer của nó có:

```java
CriticalConsumer(@Lazy CriticalStartupVerifier verifier) {
    this.verifier = verifier;
}
```

Injection point có thể nhận proxy; tuy nhiên **verifier là một bean eager theo bean definition của chính nó** và vẫn có thể được tạo trong refresh. `@Lazy` trên dependency **không đảo ngược** quyết định eager của bean definition.

Tương tự, nếu một bean được tạo trước vì hạ tầng Spring cần nó, proxy trong một consumer khác không “làm nó chưa được tạo” nữa.

## 11. Lazy singleton không đồng nghĩa prototype hay scoped proxy

Ba khái niệm dễ bị trộn:

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| Lazy initialization | **Khi nào** instance đầu tiên được tạo? | `@Lazy`, global lazy |
| Bean scope | **Bao nhiêu** instance và được dùng chung tới đâu? | `singleton`, `prototype`, `request` |
| Proxy | **Consumer nhận đối tượng gì** và lời gọi được chuyển tiếp thế nào? | Lazy-resolution proxy, AOP proxy, scoped proxy |

Một **singleton lazy** vẫn là singleton. Khi target singleton được tạo, các lần lấy target tiếp theo trong cùng container thường dùng lại singleton đó. `@Lazy` không biến nó thành prototype và không bắt nó tạo instance mới ở mỗi method call.

Ở injection point, lazy-resolution proxy có thể hoạt động khác tùy scope của target. Với singleton, Spring thường cache target đã được phân giải; với dependency không singleton, việc phân giải có thể được thực hiện lại theo vòng đời phù hợp. Khi làm việc với request/session/prototype scope, cần hiểu cả scope lẫn proxy được lựa chọn.

**Không đánh đồng lazy-resolution proxy với `@Scope(proxyMode = ScopedProxyMode.TARGET_CLASS)`**. Scoped proxy phục vụ việc inject một bean có vòng đời scope khác vào consumer sống lâu hơn. Lazy-resolution proxy phục vụ việc hoãn phân giải dependency. Chúng có thể cùng xuất hiện trong một thiết kế, nhưng là cơ chế khác nhau.

## 12. ObjectProvider là lựa chọn khi cần kiểm soát lúc truy xuất

Ngoài `@Lazy` ở injection point, Spring có `ObjectProvider<T>`:

```java
@Component
class ExportService {

    private final ObjectProvider<ReportGateway> gatewayProvider;

    ExportService(ObjectProvider<ReportGateway> gatewayProvider) {
        this.gatewayProvider = gatewayProvider;
    }

    String export() {
        ReportGateway gateway = gatewayProvider.getObject();
        return gateway.fetch();
    }
}
```

Đoạn này cần import `org.springframework.beans.factory.ObjectProvider`, `Component`, và interface `ReportGateway`. Đó là snippet để minh họa **truy xuất target có chủ đích**.

Với `ObjectProvider`, consumer biết rõ mình đang giữ một **provider**, không phải một đối tượng gateway giả dạng proxy. Khi gọi `getObject()`, Spring tìm hoặc tạo bean tương ứng theo cấu hình.

Các phương thức hữu ích:

- `getObject()`: yêu cầu bean; nếu không có target phù hợp có thể báo lỗi.
- `getIfAvailable()`: nhận target nếu có, hoặc `null` khi không có bean phù hợp, theo ngữ nghĩa method/phiên bản.
- `ifAvailable(Consumer)`: xử lý nếu bean khả dụng.
- `getIfUnique()`: hữu ích khi chỉ muốn lấy target nếu có ứng viên duy nhất.

**Cẩn thận:** việc gọi `getIfAvailable()` không có nghĩa “chỉ lấy singleton đã được tạo trước”. Nếu bean definition tồn tại và target lazy, nó vẫn có thể được tạo để đáp ứng truy vấn. Provider trì hoãn **đến lúc yêu cầu**, không phải API thuần túy để kiểm tra cache.

### Vì sao ObjectProvider khác @Lazy injection?

`@Lazy` ở injection point trả về **đối tượng có cùng kiểu dependency** nên consumer có thể gọi trực tiếp `gateway.fetch()`. `ObjectProvider` trả về **một đối tượng provider**, và consumer tự chọn thời điểm `getObject()`.

Khi dependency **có thể vắng mặt**, `ObjectProvider` thường rõ và an toàn hơn:

```java
@Component
class OptionalNotifier {

    private final ObjectProvider<NotificationGateway> provider;

    OptionalNotifier(ObjectProvider<NotificationGateway> provider) {
        this.provider = provider;
    }

    void notifyIfConfigured() {
        NotificationGateway gateway = provider.getIfAvailable();
        if (gateway != null) {
            gateway.send();
        }
    }
}
```

Đây là minh họa cần có interface `NotificationGateway` phù hợp. Với `@Lazy` injection proxy, ngay cả khi target thực tế không tồn tại, **proxy vẫn có thể được tiêm thành công**, và lỗi thiếu target chỉ lộ khi method được gọi. Điều này dễ gây bất ngờ cho optional dependency.

## 13. Lỗi bị phát hiện muộn: mặt trái của lazy

Một lợi ích của eager singleton là Spring phát hiện lỗi ngay khi startup: thiếu bean, sai constructor, invalid configuration, lỗi kết nối hoặc code trong lifecycle callback có vấn đề.

Khi một bean lazy không được tạo trong refresh, lỗi thuộc quá trình **khởi tạo instance đó** có thể chỉ lộ khi:

- Một endpoint HTTP đầu tiên gọi service.
- Một scheduled job chạy lần đầu.
- Một `ApplicationRunner` hoặc bean khác yêu cầu nó.
- Một listener xử lý event đầu tiên.
- Người dùng truy cập chức năng hiếm dùng.

Ví dụ:

```java
@Component
@Lazy
class BrokenClient {

    BrokenClient() {
        throw new IllegalStateException("Client configuration invalid");
    }
}
```

Nếu không ai yêu cầu `BrokenClient` lúc khởi động, app có thể hoàn thành refresh. Sau đó `context.getBean(BrokenClient.class)` mới làm lộ lỗi. Đây chỉ là minh họa trong ứng dụng thử nghiệm; đừng cố tình cho bean production ném lỗi như ví dụ.

Với `@Lazy` tại injection point, một proxy có thể che thời điểm nhận ra target bị thiếu:

```java
@Component
class GatewayConsumer {

    private final MissingGateway gateway;

    GatewayConsumer(@Lazy MissingGateway gateway) {
        this.gateway = gateway;
    }

    void doWork() {
        gateway.execute(); // Có thể lỗi ở thời điểm dùng proxy.
    }
}
```

Đoạn này minh họa một class cần định nghĩa interface `MissingGateway` nhưng **không đăng ký implementation bean**. Nó không phải chương trình độc lập; mục tiêu là cho thấy việc inject proxy có thể thành công trong khi thực thi method thất bại. Nếu bạn cần kiểm tra dependency có thật tại startup, đừng coi proxy là một cơ chế validation.

### Đừng dùng global lazy để “chữa” lỗi bean

Nếu ứng dụng trước đây fail startup vì dependency bắt buộc bị thiếu, bật lazy có thể làm lỗi xuất hiện muộn hơn. Điều đó không sửa cấu hình hay logic và đôi khi nguy hiểm hơn vì service đã được nhận traffic.

Một chính sách tốt:

1. Xác định bean nào có thể lazy an toàn.
2. Những dependency quan trọng cho tính đúng đắn nên được xác nhận trước khi ứng dụng được đánh dấu ready.
3. Đừng để request người dùng đầu tiên trở thành integration test.
4. Dùng readiness/health checks phù hợp với môi trường triển khai, không dựa vào thời gian startup thấp như dấu hiệu ứng dụng khỏe.
5. Trong QA, chạy smoke test qua các đường đi quan trọng để kích hoạt những bean lazy có rủi ro.

## 14. Hiệu năng: giảm thời gian startup có thể làm tăng độ trễ request đầu

Giả sử `ExpensiveSearchClient` cần 400 ms để tạo singleton, và chỉ 5% request cần client đó.

- **Eager**: trả chi phí 400 ms trong startup; request đầu tới chức năng tìm kiếm không phải trả chi phí tạo singleton.
- **Lazy**: có thể tiết kiệm phần chi phí này trong startup; request đầu gọi chức năng tìm kiếm có thể trả thêm ~400 ms.

Các số là **tình huống giả định**, không phải số benchmark của Spring Boot. Thời gian thật phụ thuộc classpath, reflection/proxy, JIT, I/O, dependency và tình trạng hệ thống.

Cần đo nhiều chỉ số:

- Thời gian tới `ApplicationStartedEvent` và `ApplicationReadyEvent`.
- Thời gian tới readiness thật sự của hạ tầng.
- P50/P95/P99 latency của request đầu và các request tiếp theo.
- Bộ nhớ heap tại startup và sau khi các tính năng chính được sử dụng.
- Số bean thực sự được khởi tạo.
- Tỷ lệ lỗi lần đầu sử dụng và mức tăng lỗi sau deploy.

**Trade-off:** lazy thường tối ưu **thời điểm trả chi phí** hơn là xóa chi phí. Có thể rất hữu ích cho CLI ngắn, module hiếm dùng hoặc ứng dụng có nhiều feature tùy chọn; cũng có thể không phù hợp với dịch vụ latency nghiêm ngặt cần sẵn sàng ngay từ request đầu.

### Web application và cold request

Trong Spring MVC hoặc WebFlux, global lazy có thể làm một số controller/service chưa được tạo lúc server bắt đầu nghe. Request đầu tới route thích hợp có thể làm việc khởi tạo bean, mapping hoặc dependency phát sinh muộn tùy cơ chế framework và hạ tầng.

**Không khẳng định mọi controller đều được lazy** chỉ vì có cờ global. Có những bean web hạ tầng cần xuất hiện trong refresh để đăng ký mapping và chạy server. Quy tắc chính xác phụ thuộc phiên bản Spring Boot, starter và cấu hình.

Nếu dùng readiness probe, lưu ý readiness thường đánh giá trạng thái dịch vụ, không nhất thiết chạm mọi đường đi của ứng dụng để khởi tạo tất cả bean lazy.

## 15. Vì sao một bean lazy vẫn được tạo khi startup?

Đây là câu hỏi debugging phổ biến. Các nguyên nhân điển hình:

1. **Eager consumer** constructor-inject target trực tiếp. Target bị yêu cầu ngay để xây consumer.
2. **`ApplicationRunner` hoặc `CommandLineRunner`** truy cập target trong quá trình run, trước `ApplicationReadyEvent`.
3. **`@PostConstruct`** của một bean được tạo sớm gọi target qua proxy.
4. **Listener sự kiện startup** hoặc một lifecycle bean yêu cầu target.
5. **`@Lazy(false)`** trên bean hoặc metadata cấu hình cho biết nó phải eager.
6. **Hạ tầng framework** cần một số bean để xử lý refresh, post-processing hoặc định tuyến.
7. **Code tự gọi `context.getBean(Target.class)`** tại startup.
8. **Bean có dependency graph phức tạp** khiến nó là điều kiện khởi tạo một bean khác.
9. **Test fixture** có `@Autowired` trong test class hoặc `@BeforeEach` làm bean được lấy ngay, dù trong ứng dụng thật không xảy ra cùng thời điểm.
10. **Proxy bị sử dụng trong constructor** hoặc callback sớm, khiến target được phân giải ngay.

Bài toán cần phân biệt “đã có **bean definition**” với “đã có **singleton instance**”. `containsBean` thường trả true khi container biết về bean, còn `containsSingleton` cho biết instance singleton đã được đăng ký trong cache hay chưa.

### Một cách kiểm tra không kích hoạt bean

Khi đang chẩn đoán trong một context đang active:

```java
ConfigurableListableBeanFactory factory = context.getBeanFactory();

System.out.println(
        factory.containsSingleton("remoteReportGateway"));
```

Đoạn này cần biến `context` kiểu `ConfigurableApplicationContext` và import `ConfigurableListableBeanFactory`. `containsSingleton` là công cụ quan sát trạng thái singleton nội bộ; với prototype/request scope hoặc bean có tên khác, nó không thay thế toàn bộ khả năng introspection.

Tránh dùng:

```java
System.out.println(context.getBean(RemoteReportGateway.class));
```

để kiểm tra **bean đã được tạo trước hay chưa**, vì chính `getBean` có thể làm tạo bean đang lazy và thay đổi trạng thái cần quan sát.

## 16. Lỗi thiết kế với @Lazy ở constructor, field và setter

### Constructor parameter được khuyến nghị hơn field injection

Một ví dụ constructor rõ ràng:

```java
@Component
class ReceiptService {

    private final ReportGateway gateway;

    ReceiptService(@Lazy ReportGateway gateway) {
        this.gateway = gateway;
    }
}
```

Class snippet này cần `ReportGateway` và import `Component`/`Lazy`. Với Spring hiện đại, nếu class chỉ có một constructor, thông thường không cần `@Autowired` trên constructor.

Khi lựa chọn, cần trả lời hai câu hỏi riêng:

- Có thật sự cần trì hoãn target không?
- Có thật sự cần **giữ proxy trong bean** không, hay nên inject một `ObjectProvider` để thể hiện truy cập tùy chọn?

Nếu câu trả lời cho cả hai đều không, hãy dùng **constructor injection trực tiếp** không có `@Lazy`, dễ đọc và fail-fast hơn.

### Field injection có thể dùng nhưng khó kiểm thử hơn

```java
@Component
class OldStyleReceiptService {

    @Autowired
    @Lazy
    private ReportGateway gateway;
}
```

Cần import `Autowired`, `Lazy`, `Component`. Đoạn này hợp lệ trong một Spring bean nhưng giấu dependency ở field, gây khó khăn khi tạo object thuần trong unit test và không cho field là `final`. Constructor injection thường được ưu tiên.

### Setter/injection method

Spring cũng hỗ trợ lazy ở những injection point phù hợp trong method được xử lý bởi injection framework. Ví dụ:

```java
@Component
class MutableReceiptService {

    private ReportGateway gateway;

    @Autowired
    void setGateway(@Lazy ReportGateway gateway) {
        this.gateway = gateway;
    }
}
```

Đoạn này cần các import tương ứng. Hãy đặt annotation tại **tham số thực sự cần lazy**, tránh gắn `@Lazy` tùy tiện trên cả class consumer khi mục tiêu chỉ là trì hoãn một dependency.

## 17. Tương tác với AOP proxy, @Transactional và circular dependencies

### Lazy-resolution proxy không đồng nghĩa AOP proxy

Một bean có `@Transactional` có thể được Spring bọc bằng AOP proxy để thực thi transaction interceptor. Một dependency có `@Lazy` cũng có thể được tiêm qua lazy-resolution proxy. Đây là **hai lý do tạo proxy khác nhau**.

```text
Consumer
   |
   v
Lazy-resolution proxy
   |
   | resolve target
   v
Bean reference (có thể là AOP proxy)
   |
   v
Actual bean instance
```

Sơ đồ này mô tả khả năng có nhiều lớp trung gian, không cam kết mọi bean luôn có đúng hai proxy. Khi debug class bằng `getClass()`, đừng suy ra kiểu runtime phải đúng bằng class bạn tự viết; proxy có thể có kiểu khác.

### @Lazy không phải cách chữa mọi circular dependency

Giả sử:

```text
ServiceA --constructor--> ServiceB
ServiceB --constructor--> ServiceA
```

Chu trình constructor injection có thể khiến ứng dụng không khởi tạo được hai bean. `@Lazy` tại **một điểm tiêm** đôi khi giúp trì hoãn một cạnh dependency và phá chu trình tạo object tức thời, vì Spring có thể tiêm proxy thay cho target thật.

Tuy nhiên:

- Đây không phải bảo đảm mọi circular dependency đều được giải quyết.
- Một trong hai bean gọi qua proxy ngay trong constructor hoặc `@PostConstruct` có thể làm vòng lặp tái xuất hiện.
- Global lazy **không tự sửa cấu trúc vòng phụ thuộc** khi các bean cuối cùng vẫn yêu cầu nhau.
- Trong Spring Boot, chính sách xử lý circular references còn phụ thuộc cấu hình; không nên bật hỗ trợ circular dependencies chỉ để lách thiết kế.
- Tốt hơn là trích xuất responsibility chung, đảo chiều dependency qua interface hoặc tổ chức event/callback phù hợp.

Sử dụng `@Lazy` để trì hoãn **một dependency thực sự ít dùng** là hợp lý; sử dụng nó để che một kiến trúc phụ thuộc vòng mà không hiểu hệ quả là rủi ro.

## 18. @Lazy và các callback vòng đời bean

Khi một singleton lazy chưa được tạo, các callback thuộc **instance bean** chưa chạy:

- Constructor.
- Injection vào bean.
- `@PostConstruct`.
- `InitializingBean.afterPropertiesSet()`.
- Custom `initMethod`.
- Một số xử lý `BeanPostProcessor` gắn với lần tạo bean.

Khi bean được tạo ở lần cần đầu tiên, các bước phù hợp sẽ diễn ra lúc đó, trước khi bean được dùng thành công.

**Phân biệt với `@PreDestroy`:** nếu singleton lazy đã được tạo và container quản lý nó, destructor tương ứng vẫn có thể được gọi khi context đóng bình thường. Nếu bean **chưa bao giờ được tạo**, không có instance để gọi callback hủy. Với prototype, Spring không tự quản lý hủy từng instance như singleton, bất kể bean có lazy hay không.

Ví dụ:

```java
@Component
@Lazy
class LazyCache {

    LazyCache() {
        System.out.println("cache constructed");
    }

    @PostConstruct
    void initialize() {
        System.out.println("cache init");
    }

    @PreDestroy
    void close() {
        System.out.println("cache destroy");
    }
}
```

Đoạn này cần `Component`, `Lazy`, `jakarta.annotation.PostConstruct` và `jakarta.annotation.PreDestroy`; phải được đăng ký trong context Spring. Nếu `LazyCache` không được yêu cầu, sẽ không thấy các dòng constructor/init/destroy cho instance đó. Nếu lần đầu gọi `getBean(LazyCache.class)`, constructor/init chạy lúc đó, và destructor sẽ chạy khi context hủy singleton đã được tạo.

**Không dựa vào `@PostConstruct` của một lazy bean để thực thi nhiệm vụ startup bắt buộc**. Bean đó có thể không được khởi tạo trước khi ứng dụng đạt ready.

## 19. Tương tác với ApplicationRunner và kiểm tra readiness

Global lazy có thể hoãn nhiều bean cho đến khi chúng cần thiết. Tuy nhiên Spring Boot chủ động tìm và gọi `ApplicationRunner` / `CommandLineRunner` trong giai đoạn startup **sau refresh, trước `ApplicationReadyEvent`**.

Nếu runner inject một service trực tiếp:

```java
@Component
class SeedDataRunner implements ApplicationRunner {

    private final SeedDataService seedService;

    SeedDataRunner(SeedDataService seedService) {
        this.seedService = seedService;
    }

    @Override
    public void run(ApplicationArguments args) {
        seedService.seed();
    }
}
```

Đây là snippet minh họa cần import `Component`, `ApplicationRunner` / `ApplicationArguments` và định nghĩa bean `SeedDataService` với method `seed()`.

Ngay cả khi global lazy bật, Boot vẫn phải yêu cầu runner để gọi nó, và constructor injection trực tiếp có thể kéo service vào ngay trước ready. Đây là hành vi đúng: **lazy không thắng một yêu cầu thực tế cần dùng bean**.

Nếu constructor nhận `@Lazy SeedDataService` nhưng `run()` vẫn gọi `seed()` ngay, proxy chỉ trì hoãn đến **dòng gọi trong runner**, vốn vẫn thuộc startup. Vì vậy lợi ích về thời gian tới ready có thể **không thay đổi đáng kể**.

Một hệ thống cần khởi tạo dữ liệu bắt buộc trước nhận traffic nên **cố tình** làm nó trước ready. Không nên cố bật lazy để bỏ qua điều kiện an toàn và báo ready sớm.

## 20. Testing: kiểm chứng chính sách lazy bằng hành vi

Để test khác biệt, điều quan trọng là **thứ tự thao tác**.

### Test A: global lazy tắt

1. Đảm bảo `spring.main.lazy-initialization=false`.
2. Khởi chạy một context mới với demo mục 7.
3. Trước mọi lời gọi `getBean` từ code quan sát, kiểm tra `containsSingleton("remoteReportGateway")`.
4. Kết quả mong đợi trong demo là `true`, vì target non-lazy singleton.

### Test B: global lazy bật

1. Đặt `spring.main.lazy-initialization=true` cho lần chạy mới.
2. Sau `SpringApplication.run`, trước `getBean`, gateway được kỳ vọng **chưa có singleton instance** trong demo.
3. Lấy `ReportWorker`; nhờ injection proxy, gateway vẫn chưa cần tạo.
4. Gọi `worker.execute()`; gateway được khởi tạo và method chạy.
5. Kiểm tra `containsSingleton` đổi từ `false` sang `true`.

### Test C: annotation trên bean definition vs injection point

Khi global lazy tắt:

1. Đặt `@Lazy` trên target gateway.
2. Bỏ `@Lazy` ở constructor của eager consumer.
3. Quan sát target bị tạo để thỏa constructor dependency.
4. Đặt lại `@Lazy` tại constructor parameter.
5. So sánh khi consumer được tạo và khi gọi method đầu tiên.

### Test D: thiếu dependency

1. Tạo consumer nhận `@Lazy MissingGateway`, nhưng không khai báo target bean.
2. Chỉ tạo consumer rồi kiểm tra hoạt động khởi tạo.
3. Gọi method trên proxy, quan sát lỗi target bị thiếu.
4. Thay `@Lazy` bằng `ObjectProvider<MissingGateway>` và dùng `getIfAvailable()` để xử lý trường hợp optional bằng nhánh rõ ràng.

Các thí nghiệm nên thực hiện trong **dự án demo độc lập**, không tắt/bật global lazy ngay trên service production và kết luận dựa trên kết quả một lần chạy.

### Unit test và integration test

Với unit test của `ReportWorker`, dễ nhất là tự cung cấp một fake `ReportGateway` qua constructor và kiểm tra method call. Không cần dựng Spring context chỉ để kiểm thử logic consumer.

Với integration test kiểm tra chính sách global lazy, phải khởi tạo context đúng theo cấu hình Spring Boot. Các annotation của test, bean test fixture hoặc lời gọi của test framework có thể tự tạo target sớm. Khi viết assertion, đo **trước khi test tự inject hoặc getBean target**, nếu không kết quả đã bị thay đổi bởi hành động quan sát.

`ApplicationContextRunner` có thể hữu ích để thử bean definitions/configuration trong một context nhỏ, nhưng nó không tự mô phỏng toàn bộ các bước `SpringApplication.run` và cờ global của Spring Boot như một integration test full startup nếu không cấu hình các phần tương ứng. Cần lựa chọn đúng phạm vi test.

## 21. Chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra / hướng xử lý |
| --- | --- | --- |
| Bật global lazy nhưng bean vẫn tạo lúc startup | Bean eager được loại trừ, dependency thật sự cần, runner/lifecycle gọi | Xác định ai yêu cầu bean, xem dependency graph và callback |
| Đặt `@Lazy` trên target nhưng vẫn thấy constructor chạy sớm | Consumer eager constructor-inject target trực tiếp | Chuyển đúng cạnh phụ thuộc sang `@Lazy` injection point nếu phù hợp |
| Đặt `@Lazy` trên constructor parameter nhưng target vẫn tạo sớm | Target bean definition vẫn eager và được pre-instantiated độc lập | Đánh dấu target lazy hoặc bật global lazy có chọn lọc |
| @Lazy injection xong mới báo thiếu bean lúc request đầu | Proxy hoãn phân giải target | Kiểm tra target khi startup nếu bắt buộc; dùng `ObjectProvider` nếu optional |
| Sau khi bật global lazy, request đầu chậm đột biến | Bean đắt đỏ được tạo trong đường request | Đo cold path, chọn eager/prewarm các bean quan trọng |
| Sửa property lazy mà không thấy tác dụng | Context đã refresh; không restart | Khởi động context mới với cấu hình mới |
| Thêm `@Lazy` nhưng circular dependency vẫn lỗi | Proxy không phá được chu trình sử dụng thực tế | Thiết kế lại dependency graph, tránh gọi trong constructor |
| `getBean` khiến lazy bean “bất ngờ” đã tạo | `getBean` chính là lệnh yêu cầu bean | Quan sát bằng `containsSingleton` trước khi yêu cầu |
| Lazy singleton có nhiều constructor logs | Có nhiều context, scope khác, hoặc nhiều bean definitions | Xác định bean name, context identity và scope |
| Bean lazy không chạy `@PostConstruct` lúc startup | Bean chưa được tạo | Đưa logic bắt buộc sang cơ chế startup phù hợp |
| Bean lazy không chạy `@PreDestroy` khi đóng | Bean chưa từng được tạo hoặc scope không quản lý hủy | Kiểm tra instance/scope và đường đóng context |
| `@Lazy(false)` không giúp giảm mọi lỗi muộn | Chỉ kiểm tra eager bean được đánh dấu, các bean khác vẫn lazy | Xác định tập bean cần fail-fast và kiểm tra readiness |
| Proxy gặp vấn đề với class final/method final | Class-based proxy cần khả năng proxy thích hợp | Ưu tiên interface hoặc đánh giá giới hạn proxy framework |
| Startup ngắn hơn nhưng tổng tài nguyên cao hơn | Khởi tạo bị dồn sang runtime, heap chưa được dự trù | Đo memory/latency và tối ưu dựa trên workload thật |

Quy trình debug thực tế:

1. **Chỉ ra bean cụ thể** và tên bean trong context; đừng nói chung “lazy không hoạt động”.
2. Xác định global lazy đang bật hay tắt trong **lần chạy hiện tại**.
3. Kiểm tra annotation trên **bean definition** và trên **điểm tiêm**; chúng là hai vị trí khác nhau.
4. Tìm mọi consumer có thể yêu cầu target, đặc biệt bean eager, runner, listener và lifecycle callback.
5. Dùng phép kiểm tra không tạo bean như `containsSingleton` để quan sát instance trước khi gọi `getBean`.
6. Khi có lỗi, phân biệt lỗi **trong refresh** với lỗi **khi gọi lần đầu** trên proxy.
7. Đo độ trễ request đầu và trạng thái readiness; không lấy thời gian startup ngắn làm mục tiêu duy nhất.
8. Tránh sửa kiến trúc bằng cách gắn `@Lazy` khắp nơi nếu dependency graph thực tế đang có vấn đề.

## 22. Những ngộ nhận cần loại bỏ

**Ngộ nhận 1:** “Bật `spring.main.lazy-initialization=true` nghĩa là không bean nào tạo lúc startup.”

Sai. Bean hạ tầng, bean bắt buộc và những bean được truy cập trong startup vẫn có thể được tạo. Global lazy là **chính sách áp dụng rộng**, không phải lệnh cấm tạo bean trước request.

**Ngộ nhận 2:** “`@Lazy` ở constructor parameter giống `@Lazy` trên class target.”

Sai. Trên parameter, Spring tạo một **lazy-resolution proxy cho dependency**. Trên class target, annotation chủ yếu đánh dấu **bean definition để hoãn pre-instantiation**.

**Ngộ nhận 3:** “Gắn `@Lazy` lên bean target thì mọi consumer eager đều không tạo được target trước request.”

Sai. Consumer eager có direct constructor injection vẫn có thể ép target tạo ngay. Muốn giữ consumer eager và tránh tạo target ngay, xét việc đặt `@Lazy` tại **cạnh injection**.

**Ngộ nhận 4:** “Gắn `@Lazy` tại injection point sẽ ngăn một target singleton vốn eager được tạo ở startup.”

Sai. Target có thể được Spring pre-instantiate độc lập; proxy chỉ không bắt buộc phân giải target **qua đường injection đó**.

**Ngộ nhận 5:** “Proxy tức mỗi lần gọi đều tạo bean mới.”

Sai. Scope vẫn quyết định lifecycle; singleton vẫn là singleton. Lazy-resolution proxy không tự biến target thành prototype.

**Ngộ nhận 6:** “Nếu thiếu bean, Spring sẽ luôn báo ở lúc inject `@Lazy`.”

Không nhất thiết. Proxy có thể được cung cấp trước, và việc target vắng mặt chỉ gây lỗi khi proxy cố phân giải target.

**Ngộ nhận 7:** “Lazy làm cho ứng dụng nhanh hơn trong mọi trường hợp.”

Không được bảo đảm. Chi phí khởi tạo có thể bị chuyển sang request đầu hoặc job đầu; cần đo latency, memory, error detection và readiness.

## 23. Hướng chọn giải pháp cho tình huống thực tế

### Tình huống A: một SDK tích hợp hiếm khi dùng

Ví dụ ứng dụng đa tính năng có một SDK kết nối dịch vụ phân tích chỉ được gọi khi người dùng chọn một chức năng ít dùng.

**Hướng phù hợp:** đánh dấu bean SDK `@Lazy`. Nếu có consumer eager inject trực tiếp, cân nhắc `@Lazy` tại constructor parameter hoặc inject `ObjectProvider<AnalyticsClient>`. Đảm bảo request đầu có timeout và thông báo lỗi an toàn; kiểm thử lazy target khi dependency ngoài không khả dụng.

### Tình huống B: ứng dụng có hàng trăm bean, startup rất chậm

**Hướng cân nhắc:** thử `spring.main.lazy-initialization=true` trên môi trường staging với workload đại diện. Đo cold request và tài nguyên, đánh dấu `@Lazy(false)` cho những bean buộc phải sẵn sàng. Không bật chỉ vì thấy thời gian startup thấp trong log.

### Tình huống C: repository bắt buộc cho mọi request chính

**Hướng phù hợp:** đừng trì hoãn một cách vô thức nếu việc chưa cấu hình repository sẽ khiến chức năng cốt lõi thất bại sau khi app được xem là ready. Cân nhắc eager initialization hoặc kiểm tra readiness chủ động. Giữ fail-fast cho dependency quan trọng có thể đáng giá hơn tối ưu startup vài trăm mili giây.

### Tình huống D: dependency tùy chọn có thể hoàn toàn vắng mặt

**Hướng phù hợp:** `ObjectProvider<T>` hoặc thiết kế interface/strategy/conditional configuration rõ hơn `@Lazy` proxy. Một proxy luôn được tiêm không phải tín hiệu rằng target chắc chắn hiện diện.

### Tình huống E: vòng phụ thuộc giữa hai service

**Hướng phù hợp:** thiết kế lại trách nhiệm và dependency direction. `@Lazy` ở một cạnh có thể là biện pháp tạm thời có hiểu biết, nhưng không giải quyết được rủi ro gọi vòng khi runtime.

## 24. Bài tập thực hành

### Bài 1: phân loại vị trí annotation

Với mỗi ví dụ, nói rõ annotation tác động lên **bean definition** hay **injection point**:

```java
@Component
@Lazy
class Alpha { }

@Bean
@Lazy
Beta beta() { return new Beta(); }

class Gamma {
    Gamma(@Lazy Alpha alpha) { }
}
```

Đây là đoạn code rút gọn để phân tích, cần bổ sung các kiểu và import khi chạy thật.

Đáp án: `Alpha` lazy ở bean definition; method tạo `Beta` lazy ở bean definition; tham số `alpha` của `Gamma` là lazy-resolution injection proxy.

### Bài 2: dự đoán lần tạo đầu tiên

Với bean `SlowGateway @Lazy` và bean `Consumer` eager direct-inject gateway, gateway có được tạo ở refresh không? Vì sao?

Đáp án: **có thể có**; nếu consumer buộc cần gateway thật để hoàn thành constructor injection, container phải tạo gateway.

### Bài 3: sửa đúng một cạnh dependency

Giữ `SlowGateway @Lazy`, thay constructor consumer thành `Consumer(@Lazy SlowGateway gateway)`, không gọi gateway trong constructor và `@PostConstruct`. Dự đoán khi nào gateway được tạo.

Đáp án: consumer có thể được tạo với proxy, còn gateway được phân giải khi method trên proxy được gọi lần đầu, nếu không có consumer/hạ tầng khác yêu cầu gateway trước.

### Bài 4: bật global lazy rồi quan sát

Chạy demo mục 7 theo hai cấu hình. Ghi lại giá trị:

```text
afterRun.gateway
afterRun.worker
afterGetWorker.gateway
afterExecute.gateway
```

Giải thích vì sao chỉ đổi `spring.main.lazy-initialization` mà kết quả của `afterRun` đã khác; trong khi annotation tại constructor của `ReportWorker` không đổi.

### Bài 5: dependency vắng mặt

Thay gateway trong consumer bằng một interface không có implementation bean, vẫn dùng `@Lazy` trên injection point. Quan sát khi tạo consumer và khi gọi method. Sau đó thay bằng `ObjectProvider` và mô tả cách xử lý optional.

### Bài 6: độ trễ request đầu

Tạo một bean giả lập thao tác khởi tạo tốn thời gian trong môi trường test, đo tổng startup và thời gian lời gọi đầu/tiếp theo với global lazy bật/tắt. Không thực hiện `Thread.sleep(...)` trong một service production để mô phỏng “tối ưu”. Cần phân biệt độ trễ do khởi tạo bean với độ trễ từ network/DB.

### Bài 7: lifecycle của bean chưa từng dùng

Tạo bean `@Lazy` có `@PostConstruct` và `@PreDestroy` in marker. Chạy hai lần: một lần không yêu cầu bean, một lần `getBean` rồi đóng context. Giải thích vì sao chỉ lần thứ hai có callback instance tương ứng.

## 25. Checklist trước khi áp dụng vào dự án

- [ ] Đã phân biệt rõ **global lazy**, **`@Lazy` bean definition**, và **`@Lazy` injection point**.
- [ ] Có lý do thực tế để trì hoãn tạo bean, thay vì thêm annotation theo thói quen.
- [ ] Đã kiểm tra consumer eager có ép target lazy tạo sớm không.
- [ ] Không nhầm proxy dependency với target singleton thật trong logging/introspection.
- [ ] Không dùng `@Lazy` để làm missing required dependency trông như hợp lệ.
- [ ] Nếu dependency optional, đã cân nhắc `ObjectProvider` hoặc điều kiện cấu hình rõ ràng.
- [ ] Không giả định global lazy áp dụng cho mọi bean hạ tầng.
- [ ] Nếu dùng `@Lazy(false)`, đã xác định rõ bean nào bắt buộc phải eager.
- [ ] Có phép đo startup, first-request latency, throughput và memory phù hợp.
- [ ] Đã kiểm thử đường lỗi khi target lần đầu được tạo.
- [ ] Những tác vụ startup bắt buộc không vô tình nằm trong `@PostConstruct` của một bean có thể không được tạo.
- [ ] Có chiến lược readiness/health cho các dependency cốt lõi.
- [ ] Đã kiểm thử với context mới; không kết luận từ việc sửa property sau refresh.
- [ ] Không phụ thuộc vào thứ tự log constructor của các singleton độc lập nếu framework không đưa ra hợp đồng thứ tự.
- [ ] Đã rà soát ứng dụng test: test injection, mocks và setup có thể tạo bean sớm.

## 26. Tổng kết

- **Global lazy `spring.main.lazy-initialization=true`** là chính sách rộng của Spring Boot: nhiều bean có thể được tạo **khi cần** thay vì trong refresh. Nó không bảo đảm không có bean nào khởi tạo ở startup.
- **`@Lazy` trên `@Component` hoặc `@Bean`** chủ yếu thay đổi **thuộc tính lazy của bean definition**. Bean đó vẫn được tạo nếu một singleton eager cần nó trực tiếp.
- **`@Lazy` trên constructor parameter/điểm tiêm** khiến consumer nhận một **lazy-resolution proxy**, nên có thể trì hoãn **phân giải target qua cạnh dependency đó**. Nó không tự thay đổi chính sách eager của target.
- Nếu muốn một **consumer eager** được tạo mà **target** chưa khởi tạo, phải xét **cả chính sách lazy của target và proxy tại injection point**.
- `@Lazy(false)` cho phép những bean quan trọng được tạo eager khi bật global lazy; `ObjectProvider` phù hợp khi muốn tự quyết định thời điểm truy xuất hoặc xử lý dependency tùy chọn.
- Mục tiêu không phải “mọi thứ đều lazy”, mà là **tối ưu chi phí startup có kiểm soát** mà không đẩy lỗi cấu hình quan trọng và độ trễ bất ngờ sang người dùng.

### Tài liệu tham khảo

- [Spring Boot 3.3 — SpringApplication / Lazy Initialization](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): cách bật `spring.main.lazy-initialization`, lợi ích/đánh đổi và `@Lazy(false)`.
- [Spring Framework 6.1 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.1/core/beans/dependencies/factory-lazy-init.html): singleton pre-instantiation và việc bean lazy bị consumer eager yêu cầu.
- [Spring Framework 6.1 — @Lazy API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/context/annotation/Lazy.html): sự khác nhau giữa annotation trên bean definition và trên injection point, lazy-resolution proxy.
- [Spring Framework 6.1 — ObjectProvider API](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/beans/factory/ObjectProvider.html): truy xuất bean theo nhu cầu, hỗ trợ optional/unique target.
- [Spring Framework — The IoC Container](https://docs.spring.io/spring-framework/reference/core/beans.html): bean definitions, scope, lifecycle và dependency injection.

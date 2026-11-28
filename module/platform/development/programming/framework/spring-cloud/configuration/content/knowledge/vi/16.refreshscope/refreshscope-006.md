# Giới hạn với constructor binding, record và bean không thể làm mới

Spring Cloud hỗ trợ cập nhật một phần cấu hình khi ứng dụng đang chạy. Tuy nhiên, việc `Environment` nhận giá trị mới không có nghĩa mọi object trong application context tự thay đổi theo. Cơ chế rebinding của `@ConfigurationProperties` cần một bean có thể cập nhật trạng thái; còn `@RefreshScope` cần tạo lại target bean thông qua proxy. Những lựa chọn thiết kế như constructor binding, Java record, singleton giữ giá trị lúc khởi tạo hoặc bean hạ tầng không hỗ trợ tái tạo có thể khiến refresh không có tác dụng như mong đợi.

Bài này tập trung vào ranh giới giữa ba việc: nạp giá trị mới vào `Environment`, bind lại một bean cấu hình, và tạo lại một bean phụ thuộc cấu hình. Hiểu rõ từng việc giúp chọn đúng mô hình cho cấu hình bất biến, bean cần giữ trạng thái và thành phần chỉ có thể thay đổi bằng restart.

## 1. Refresh không đồng nghĩa với thay mọi object trong ứng dụng

Khi Config Client lấy cấu hình mới và phát sinh refresh, Spring Cloud có thể cập nhật `Environment`, phát `EnvironmentChangeEvent`, rebind các bean `@ConfigurationProperties` đủ điều kiện và làm mới target của các bean trong `@RefreshScope`.

Các bước này có phạm vi khác nhau:

| Cơ chế | Điều được cập nhật | Giới hạn chính |
|---|---|---|
| Cập nhật `Environment` | Giá trị trong các `PropertySource` | Bean đã giữ giá trị cũ trong field không tự đọc lại |
| Rebind `@ConfigurationProperties` | Các field của bean cấu hình có thể bind lại | Constructor-bound object và record không được rebinder refresh; việc thay đổi field tại chỗ có thể để lộ trạng thái trung gian |
| `@RefreshScope` | Target bean trong scope bị loại khỏi cache và được tạo lại khi dùng lần tiếp theo | Chỉ bean thực sự nằm trong scope và có thể proxy/tạo lại mới được làm mới |
| Restart ứng dụng | Toàn bộ application context và các thành phần được khởi tạo lại | Tốn thời gian, cần quy trình triển khai và readiness phù hợp |

Ví dụ, một bean đọc URL lúc khởi tạo:

```java
import java.net.URI;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class PaymentGatewayClient {

    private final String baseUrl;

    public PaymentGatewayClient(Environment environment) {
        this.baseUrl = environment.getProperty(
                "payment.gateway.base-url",
                "https://sandbox.example.test");
    }

    public URI endpoint(String path) {
        return URI.create(baseUrl + path);
    }
}
```

Bean này là singleton thông thường. Sau khi constructor chạy, `baseUrl` đã được gán. Thay đổi `payment.gateway.base-url` trong `Environment` không chạy lại constructor và không tự thay field. Muốn cập nhật, cần dùng một mô hình rebinding phù hợp, đặt bean vào `@RefreshScope`, hoặc restart ứng dụng.

## 2. Vì sao constructor binding không được rebinding trực tiếp?

Constructor binding tạo object bằng cách truyền các giá trị cấu hình vào constructor. Sau khi object được tạo, các trường thường là `final` và không có setter để thay đổi. Cơ chế rebinding thông thường của Spring Cloud cập nhật bean `@ConfigurationProperties` hiện có; nó không thể thay thế các đối số đã truyền vào constructor của một object đang tồn tại.

Ví dụ một lớp cấu hình bất biến:

```java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payment.gateway")
public class PaymentGatewayProperties {

    private final URI baseUrl;
    private final Duration timeout;

    public PaymentGatewayProperties(URI baseUrl, Duration timeout) {
        this.baseUrl = baseUrl;
        this.timeout = timeout;
    }

    public URI getBaseUrl() {
        return baseUrl;
    }

    public Duration getTimeout() {
        return timeout;
    }
}
```

Với constructor binding, Binder tạo một instance từ giá trị hiện tại. Khi `Environment` đổi, không có setter để rebinder gán giá trị mới vào instance đó. Tạo một instance khác cũng không tự thay thế mọi tham chiếu mà các bean khác đang giữ đến instance cũ.

Spring Cloud Commons ghi rõ: object dùng constructor binding, bao gồm Java record được đánh dấu `@ConfigurationProperties`, không thể được refresh bằng cơ chế rebinding này. Đây là giới hạn có chủ đích của cách bind bất biến, không phải lỗi cú pháp YAML hoặc lỗi Config Server.

## 3. Java record và `@ConfigurationProperties`

Java record là lựa chọn tốt để biểu diễn dữ liệu cấu hình bất biến. Spring Boot hỗ trợ constructor binding cho record; nếu record chỉ có canonical constructor thì thường không cần đặt `@ConstructorBinding` tường minh.

Ví dụ:

```java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payment.gateway")
public record PaymentGatewayProperties(
        URI baseUrl,
        Duration timeout,
        int maxAttempts) {
}
```

Đăng ký record bằng configuration properties scanning hoặc `@EnableConfigurationProperties`:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderServiceApplication.class, args);
    }
}
```

Record trên có thể được bind lúc khởi động và dùng an toàn như một snapshot bất biến. Nhưng nếu nó được đăng ký trực tiếp như constructor-bound `@ConfigurationProperties`, Spring Cloud không thể rebind instance đó khi refresh. Chỉ thêm endpoint `/actuator/refresh` không thay đổi giới hạn này.

Một điểm cần phân biệt: record có thể được tạo lại bởi một factory hoặc provider nằm trong `@RefreshScope`. Khi đó, Spring Cloud refresh provider proxy; provider tạo một record mới từ `Environment` hiện tại. Record là value object bên trong target mới, không phải constructor-bound configuration bean được rebinder trực tiếp.

## 4. Cách một JavaBean có thể nhận giá trị mới qua rebinding

Nếu cấu hình cần cập nhật bằng cơ chế rebinding chuẩn, có thể dùng JavaBean mutable với constructor không tham số, getter và setter. Spring Cloud có thể bind lại các field của bean khi nhận `EnvironmentChangeEvent`.

Ví dụ:

```java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payment.gateway")
public class PaymentGatewayProperties {

    private URI baseUrl = URI.create("https://sandbox.example.test");
    private Duration timeout = Duration.ofSeconds(2);
    private int maxAttempts = 3;

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }
}
```

Đăng ký bằng `@ConfigurationPropertiesScan` hoặc:

```java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(PaymentGatewayProperties.class)
public class PaymentConfiguration {
}
```

Khi refresh phát ra `EnvironmentChangeEvent`, Spring Cloud có thể bind lại các thuộc tính của bean. Mô hình này phù hợp với tham số như timeout, retry count hoặc endpoint mà ứng dụng có thể tiếp nhận khi đang chạy.

Tuy nhiên, rebinding cập nhật field trên cùng một instance. Nó không tự động thay thế các dependency đã được tạo từ giá trị cũ. Nếu `PaymentGatewayClient` đã tạo một HTTP client hoặc connection pool từ `baseUrl`, việc field `baseUrl` thay đổi không có nghĩa HTTP client bên trong tự đổi theo. Cần thiết kế dependency đó để đọc cấu hình hiện tại, được refresh riêng, hoặc được tái tạo qua một proxy.

Ngoài ra, rebinding không bảo đảm mọi reader nhìn thấy toàn bộ thuộc tính ở cùng một thời điểm. Trong lúc bind, một luồng khác có thể quan sát hỗn hợp giá trị cũ và mới. Spring Cloud có ghi nhận một giới hạn với `Collection`: danh sách hoặc tập hợp đang được cập nhật có thể tạm thời rỗng trong quá trình binder xóa rồi thêm lại phần tử. Nếu cần một snapshot nhất quán cho một thao tác, cân nhắc `@RefreshScope` hoặc mô hình thay thế nguyên object theo cách có kiểm soát.

Việc reset giá trị về mặc định khi một khóa bị xóa cũng có điều kiện. Spring Cloud chỉ reset về giá trị mặc định ở cấp lớp khi bean có constructor không tham số là constructor duy nhất. Nếu lớp có cả constructor không tham số và constructor tham số, rebinder bỏ qua bước reset vì việc gọi constructor không tham số có thể không tái tạo đúng các default ban đầu. Trong trường hợp đó, chỉ những giá trị hiện có trong `Environment` được bind lại trên trạng thái bean đang giữ.

## 5. Dùng `@RefreshScope` cho bean cần được tạo lại

`@RefreshScope` không sửa trực tiếp instance đang tồn tại. Nó đặt bean sau một scoped proxy. Target được tạo lười khi proxy được gọi lần đầu và được giữ trong cache của scope. Khi refresh, cache target bị xóa; lần gọi tiếp theo qua proxy sẽ tạo target mới từ `Environment` hiện tại.

Ví dụ:

```java
import java.net.URI;
import java.time.Duration;

import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class PaymentGatewayClient {

    private final URI baseUrl;
    private final Duration timeout;

    public PaymentGatewayClient(Environment environment) {
        this.baseUrl = environment.getRequiredProperty(
                "payment.gateway.base-url", URI.class);
        this.timeout = environment.getProperty(
                "payment.gateway.timeout", Duration.class,
                Duration.ofSeconds(2));
    }

    public URI endpoint(String path) {
        return baseUrl.resolve(path);
    }

    public Duration timeout() {
        return timeout;
    }
}
```

Bean này được tạo lại khi proxy được gọi sau một lần refresh. Consumer nên giữ tham chiếu đến proxy do Spring inject, thay vì tự lấy target rồi lưu vào một field khác hoặc cache object đích.

### Vì sao proxy quan trọng?

Giả sử `CheckoutService` được inject `PaymentGatewayClient`. Nếu Spring inject scoped proxy, `CheckoutService` có thể giữ proxy trong suốt vòng đời singleton. Mỗi lần gọi phương thức, proxy định tuyến đến target hiện tại. Sau refresh, target cũ bị loại và target mới được tạo khi có lần gọi tiếp theo.

Nếu một consumer tự lấy giá trị cấu hình hoặc giữ một snapshot đã trả về từ target, snapshot đó không tự biến thành snapshot mới. Hãy xác định rõ thành phần nào giữ proxy và thành phần nào giữ dữ liệu bất biến được lấy từ proxy.

Một giới hạn khác là xóa hẳn một khóa khỏi nguồn cấu hình rồi refresh không nhất thiết làm thay đổi sự hiện diện của thuộc tính trong mọi bean. Nếu logic phụ thuộc vào việc khóa biến mất, hãy thiết kế một giá trị tường minh như `enabled: false`, một sentinel hoặc một default được xác định rõ; đừng chỉ dựa vào thao tác xóa dòng YAML để biểu diễn trạng thái runtime.

## 6. Dùng record bất biến bên trong một refresh-scoped provider

Khi muốn giữ record bất biến nhưng vẫn cập nhật được cấu hình lúc chạy, có thể tạo record mới bên trong một provider `@RefreshScope`. Provider là bean có thể proxy; record chỉ là dữ liệu nội bộ được tạo lại mỗi khi target provider được khởi tạo lại.

Định nghĩa record:

```java
public record PaymentSettings(
        URI baseUrl,
        Duration timeout,
        int maxAttempts) {
}
```

Định nghĩa provider có thể refresh:

```java
public interface PaymentSettingsProvider {
    PaymentSettings current();
}
```

```java
@Component
@RefreshScope
public class EnvironmentPaymentSettingsProvider
        implements PaymentSettingsProvider {

    private final PaymentSettings settings;

    public EnvironmentPaymentSettingsProvider(Environment environment) {
        Binder binder = Binder.get(environment);
        this.settings = binder
                .bind("payment", Bindable.of(PaymentSettings.class))
                .orElseThrow(() -> new IllegalStateException(
                        "Missing payment configuration"));
    }

    @Override
    public PaymentSettings current() {
        return settings;
    }
}
```

Consumer inject provider và lấy snapshot tại thời điểm cần dùng:

```java
import java.net.URI;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final PaymentSettingsProvider settingsProvider;

    public CheckoutService(PaymentSettingsProvider settingsProvider) {
        this.settingsProvider = settingsProvider;
    }

    public URI paymentEndpoint() {
        PaymentSettings settings = settingsProvider.current();
        return settings.baseUrl();
    }
}
```

Các import chính cho provider:

```java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;
```

Trong ví dụ này, `EnvironmentPaymentSettingsProvider` là bean Spring được refresh. Sau khi target cũ bị loại, lần gọi `current()` tiếp theo đi qua proxy sẽ tạo provider mới, bind `Environment` hiện tại và tạo một `PaymentSettings` record mới. `CheckoutService` vẫn giữ provider proxy; nó không giữ trực tiếp record cũ trong field.

Lưu ý: không đăng ký `PaymentSettings` record như một constructor-bound `@ConfigurationProperties` bean rồi mong rebinder cập nhật nó. Mẫu trên dùng Binder để tạo một value object mới bên trong target có vòng đời refresh được kiểm soát.

## 7. Những bean không thể hoặc không nên refresh

Không phải bean nào cũng an toàn khi hủy target và tạo lại. Một số bean bị loại khỏi refresh scope theo mặc định; một số bean khác có thể tạo lại về mặt kỹ thuật nhưng các tài nguyên bên ngoài hoặc consumer vẫn giữ trạng thái cũ.

| Loại bean | Hạn chế | Hướng xử lý |
|---|---|---|
| Constructor-bound `@ConfigurationProperties` | Không được rebind; record cũng thuộc nhóm này | Dùng JavaBean mutable hoặc refresh-scoped provider tạo snapshot mới |
| Singleton thông thường có field lấy từ `Environment`/`@Value` | Giá trị chỉ được inject khi khởi tạo | Chuyển thành `@RefreshScope`, dùng provider đọc giá trị hiện tại hoặc restart |
| `HikariDataSource` | Mặc định nằm trong `spring.cloud.refresh.never-refreshable` | Dùng quy trình thay pool/restart có kiểm soát; không giả định refresh sẽ thay JDBC URL |
| Bean giữ socket, thread, executor hoặc connection lâu dài | Tạo target mới không tự đóng hoặc chuyển giao mọi tài nguyên cũ đúng cách | Thiết kế lifecycle/close rõ ràng, drain request và thay thế an toàn |
| Bean được tạo từ `@Configuration` không refresh-scoped | Refresh configuration class không tự đặt mọi bean bên trong vào refresh scope | Đánh dấu từng bean cần refresh hoặc làm mới consumer phụ thuộc |
| Bean dùng trong AOT/native image | Context refresh không được hỗ trợ trong các trường hợp này | Tắt refresh và dùng restart/deployment để áp dụng cấu hình |

### HikariDataSource là trường hợp đặc biệt

Spring Cloud mặc định liệt kê `com.zaxxer.hikari.HikariDataSource` trong `spring.cloud.refresh.never-refreshable`. Do đó, thay đổi `spring.datasource.url` rồi gọi refresh không có nghĩa pool Hikari đang dùng sẽ được thay bằng một pool mới. Đây là hành vi được quy định để tránh tái tạo một thành phần quản lý connection có vòng đời phức tạp theo cách không an toàn.

Nếu JDBC URL, credential hoặc cấu hình pool cần thay đổi, hãy chọn một quy trình rõ ràng: restart instance theo rolling deployment, hoặc tự thiết kế cơ chế thay DataSource có khả năng drain connection, đóng pool cũ và chuyển sang pool mới. Không nên chỉ xóa Hikari khỏi danh sách `never-refreshable` để ép refresh nếu chưa chứng minh được việc đóng/mở connection và chuyển giao transaction là an toàn.

### `@RefreshScope` trên lớp `@Configuration`

Gắn `@RefreshScope` lên một lớp `@Configuration` không có nghĩa mọi bean được khai báo bằng `@Bean` trong lớp đó đều tự động refresh. Một bean singleton khác có thể đã giữ tham chiếu tới object được tạo từ cấu hình cũ. Nếu một dependency cần được tái tạo, hãy đặt scope lên chính bean đó hoặc lên thành phần phụ thuộc cần được khởi tạo lại.

## 8. `extra-refreshable` và `never-refreshable`

Spring Cloud cung cấp hai thuộc tính để điều chỉnh những loại bean được refresh scope xử lý:

```yaml
spring:
  cloud:
    refresh:
      extra-refreshable:
        - com.example.config.LegacyClient
      never-refreshable:
        - com.zaxxer.hikari.HikariDataSource
```

- `spring.cloud.refresh.extra-refreshable` bổ sung class name của các loại bean cần được xem là refreshable trong trường hợp chúng cần được đưa vào refresh scope.
- `spring.cloud.refresh.never-refreshable` liệt kê loại bean không được refresh. HikariDataSource là loại bị loại trừ mặc định.

Đây không phải cách chuyển constructor-bound `@ConfigurationProperties` thành bean có thể rebinding. Các thuộc tính này điều chỉnh khả năng xử lý bean của refresh scope; chúng không làm cho field `final` có setter hoặc thay thế instance mà mọi consumer đang giữ. Với record cấu hình, hãy dùng provider/factory có thể refresh như ví dụ trước hoặc restart ứng dụng.

## 9. Kiểm tra bean có thật sự được refresh không

Đừng chỉ kiểm tra HTTP response của endpoint refresh. Hãy xác nhận target bean đã được tạo lại và consumer đang gọi qua proxy.

Với Spring AOT transformations và native images, Context Refresh không được hỗ trợ. Trong các ứng dụng này, cấu hình refresh nên được tắt rõ ràng:

```yaml
spring:
  cloud:
    refresh:
      enabled: false
```

Các thay đổi cần được áp dụng qua build/deploy hoặc cơ chế restart mà nền tảng hỗ trợ.

Một cách kiểm tra đơn giản trong môi trường thử nghiệm:

1. Khởi động ứng dụng với `payment.gateway.base-url` là endpoint sandbox.
2. Gọi một phương thức trên bean `@RefreshScope` để target được khởi tạo.
3. Thay đổi giá trị trong nguồn cấu hình và cập nhật `Environment` theo quy trình của ứng dụng.
4. Gọi endpoint refresh được bảo vệ.
5. Gọi lại phương thức qua proxy và xác nhận target mới đọc giá trị mới.
6. Kiểm tra consumer có giữ snapshot cũ hoặc cache kết quả ngoài proxy hay không.

Với `@ConfigurationProperties`, có thể kiểm tra giá trị đã bind bằng Actuator `/actuator/configprops`. Với `Environment`, endpoint `/actuator/env` giúp xem property source và giá trị hiện tại. Hai endpoint này cần được bảo vệ và sanitization để không làm lộ secret.

Ví dụ expose các endpoint quản trị cần thiết trong môi trường kiểm thử:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,env,configprops,refresh
```

Trong production, chỉ expose endpoint thực sự cần thiết. `/actuator/refresh` thường nhận `POST`; cần xác thực, phân quyền theo vai trò vận hành, giới hạn mạng truy cập và ghi audit log. Không mở endpoint refresh công khai vì một người không có quyền có thể gây thay đổi hành vi của ứng dụng hoặc kích hoạt khởi tạo lại nhiều bean.

Ví dụ gọi endpoint trong môi trường thử nghiệm sau khi đã cập nhật nguồn cấu hình và xác thực request theo chính sách của ứng dụng:

```bash
curl -i -X POST http://localhost:8080/actuator/refresh
```

Response có thể liệt kê các khóa được nhận diện là đã thay đổi. Response thành công chỉ xác nhận refresh flow đã chạy; vẫn cần gọi qua proxy hoặc kiểm tra `/actuator/env` và `/actuator/configprops` để xác nhận bean/giá trị thực tế đã được cập nhật.

Nếu refresh target thất bại khi khởi tạo lại, theo dõi log và health indicator của refresh scope. Spring Cloud có `RefreshScopeHealthIndicator` để phản ánh trạng thái khi bean không thể re-initialize hoặc rebind sau refresh.

## 10. Khi nào cần restart thay vì refresh?

Refresh phù hợp với những giá trị và bean được thiết kế để nhận thay đổi lúc chạy. Restart phù hợp khi thay đổi đụng đến thành phần có vòng đời gắn với quá trình khởi tạo ứng dụng, hoặc không thể tái tạo an toàn bằng proxy.

| Thay đổi | Cách áp dụng thường phù hợp |
|---|---|
| Log level | Spring Cloud có thể cập nhật logger level khi nhận `EnvironmentChangeEvent` |
| Tham số retry/timeout được bean cấu hình hỗ trợ | Rebind hoặc refresh-scoped provider, sau khi kiểm tra consumer |
| Endpoint HTTP được đọc mỗi lần gọi qua provider | Refresh provider để tạo snapshot mới |
| JDBC URL của Hikari pool | Rolling restart hoặc cơ chế thay DataSource có drain/close rõ ràng |
| Thread pool/executor đã khởi tạo | Refresh chỉ khi có quy trình shutdown và tạo mới an toàn; nếu không, restart |
| Port server, cấu trúc listener hoặc cấu hình JVM | Thường cần restart |
| Cấu hình trong AOT/native image | Không dùng Context Refresh; cấu hình lại lúc build/deploy hoặc restart theo khả năng nền tảng |

Một quy trình triển khai có thể đánh dấu từng property là `runtime-refreshable` hoặc `restart-required`. Khi thay đổi chứa cả hai nhóm, pipeline cần tách đợt áp dụng hoặc thực hiện rolling restart sau khi cập nhật nguồn cấu hình.

## 11. Các lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `/actuator/refresh` trả thành công nhưng record vẫn có giá trị cũ | Record là constructor-bound `@ConfigurationProperties` và không được rebinder refresh | Dùng mutable JavaBean hoặc refresh-scoped provider tạo record mới |
| `Environment` có giá trị mới nhưng bean vẫn cũ | Bean singleton đã giữ field lúc constructor chạy | Dùng proxy `@RefreshScope`, rebind bean phù hợp hoặc restart |
| Bean `@RefreshScope` không được tạo lại | Consumer không đi qua scoped proxy, bean không thuộc scope hoặc target chưa được gọi lại | Kiểm tra bean definition, proxy và nơi inject |
| Refresh configuration class nhưng `@Bean` bên trong không đổi | Scope trên `@Configuration` không tự lan sang mọi bean được khai báo | Đặt scope lên từng bean cần refresh |
| JDBC URL mới nhưng connection vẫn đi endpoint cũ | HikariDataSource nằm trong danh sách never-refreshable hoặc pool đã được tạo trước đó | Rolling restart hoặc thay pool có kiểm soát |
| Consumer tiếp tục dùng cấu hình cũ | Consumer lưu record/snapshot hoặc cache kết quả ngoài proxy | Lấy snapshot mới qua provider ở thời điểm cần dùng; làm mới cache riêng |
| Refresh thành công nhưng bean mới lỗi khi được gọi | Giá trị mới không hợp lệ hoặc constructor không khởi tạo được | Validation trước khi phát hành, log/health check và rollback cấu hình |
| Một số request thấy giá trị trộn cũ/mới | Rebinding mutable bean diễn ra tại chỗ | Dùng `@RefreshScope` cho snapshot nhất quán hoặc restart |

## 12. Kiểm thử giới hạn constructor binding và refresh scope

Nên có kiểm thử cho cả trường hợp được hỗ trợ và trường hợp không được hỗ trợ:

- Bind một record `@ConfigurationProperties` lúc khởi động và xác nhận giá trị ban đầu đúng.
- Cập nhật `EnvironmentChangeEvent` rồi xác nhận record constructor-bound không được rebinder thay đổi.
- Dùng mutable JavaBean và xác nhận field được rebind khi có refresh event.
- Dùng provider `@RefreshScope` tạo record nội bộ, refresh scope và xác nhận lần gọi sau trả snapshot mới.
- Xác nhận consumer giữ proxy, không giữ trực tiếp target hoặc snapshot cũ.
- Kiểm tra bean chứa tài nguyên có được đóng đúng cách khi target cũ bị loại bỏ.
- Kiểm tra hành vi khi cấu hình mới không hợp lệ và cách hệ thống rollback.

Ví dụ kiểm thử khái niệm cho provider có thể refresh:

```java
// Arrange: Environment ban đầu có payment.max-attempts=2
PaymentSettings first = provider.current();
assertThat(first.maxAttempts()).isEqualTo(2);

// Act: cập nhật Environment, phát refresh event và làm mới scope
// Lần gọi tiếp theo đi qua provider proxy sẽ tạo target mới.

PaymentSettings second = provider.current();
assertThat(second.maxAttempts()).isEqualTo(5);
assertThat(second).isNotSameAs(first);
```

Đây là mô tả hành vi cần kiểm tra; phần cập nhật `Environment` và gọi refresh cần dùng test fixture tương ứng với phiên bản Spring Cloud của dự án. Không dùng một test chỉ thay đổi field của record để kết luận framework hỗ trợ refresh constructor-bound bean.

## 13. Nguyên tắc lựa chọn mô hình

| Nhu cầu | Mô hình nên cân nhắc |
|---|---|
| Cấu hình đơn giản, không cần đổi lúc chạy | Constructor-bound class hoặc record |
| Cấu hình cần rebinding trực tiếp | Mutable `@ConfigurationProperties` JavaBean |
| Cần object bất biến nhưng cập nhật lúc chạy | Record/value object được tạo bên trong refresh-scoped provider |
| Bean cần khởi tạo lại từ cấu hình mới | `@RefreshScope` trên chính bean hoặc provider sở hữu vòng đời đó |
| Thành phần có resource/lifecycle phức tạp | Restart/rolling deployment hoặc cơ chế swap được thiết kế riêng |
| AOT/native image | Không dùng Context Refresh; áp dụng cấu hình qua build/deploy/restart |

Không nên chọn constructor binding chỉ vì nó bất biến rồi kỳ vọng refresh hoạt động giống JavaBean. Ngược lại, cũng không nên biến mọi lớp cấu hình thành mutable chỉ để hỗ trợ refresh nếu các giá trị chỉ cần cố định trong suốt vòng đời instance. Chọn mô hình theo yêu cầu vòng đời thực tế của bean.

## 14. Nguyên tắc cần ghi nhớ

- Thay đổi `Environment` không tự cập nhật field đã được inject vào singleton thông thường.
- Rebinding `@ConfigurationProperties` cập nhật bean hiện có; constructor-bound object và Java record không được refresh bằng cơ chế này.
- Mutable JavaBean có constructor không tham số và setter phù hợp cho rebinding, nhưng việc cập nhật field tại chỗ không bảo đảm snapshot nhất quán cho mọi reader.
- `@RefreshScope` dùng scoped proxy; target bị xóa khỏi cache khi refresh và được tạo lại ở lần gọi tiếp theo.
- Giữ proxy trong consumer; không giữ trực tiếp target hoặc record snapshot cũ nếu cần nhận giá trị mới.
- Muốn dùng record bất biến có thể refresh, tạo record mới bên trong một provider bean có vòng đời `@RefreshScope`.
- HikariDataSource mặc định không refreshable; thay JDBC URL thường cần restart hoặc quy trình thay pool được thiết kế rõ.
- `@RefreshScope` trên lớp `@Configuration` không tự đặt mọi bean được khai báo trong lớp đó vào scope.
- Context Refresh không được hỗ trợ cho Spring AOT transformations và native images.
- Bảo vệ endpoint quản trị, kiểm tra health sau khi tạo lại bean và chuẩn bị rollback khi cấu hình mới không hợp lệ.

Constructor binding và record giúp mô hình cấu hình bất biến, còn refresh đòi hỏi framework có cách cập nhật hoặc tạo lại object. Khi một constructor-bound `@ConfigurationProperties` không thể rebinding, hãy chọn JavaBean mutable nếu cần cập nhật field, hoặc đặt việc tạo record bên trong một provider `@RefreshScope` nếu cần giữ tính bất biến. Với bean hạ tầng không thể tái tạo an toàn, dùng restart hoặc rolling deployment có kiểm soát.

## Tài liệu tham khảo

- [Spring Cloud Commons — Application Context Services và Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Boot — Constructor Binding và Java Records](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.constructor-binding)
- [Spring Boot Actuator — `env` và `configprops`](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)

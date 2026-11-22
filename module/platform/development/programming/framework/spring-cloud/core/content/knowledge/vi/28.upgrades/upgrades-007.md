# Kiểm tra thay đổi rebind, xóa thuộc tính và giới hạn Refresh Scope

Trong ứng dụng Spring Cloud, cấu hình có thể thay đổi sau khi ứng dụng đã khởi động. Một số thay đổi chỉ cần bind lại vào bean mang @ConfigurationProperties; một số khác cần tạo lại bean vì giá trị được đọc tại thời điểm khởi tạo; và một số thay đổi không thể áp dụng an toàn khi chỉ xóa key khỏi nguồn cấu hình.

Ba cơ chế thường bị nhầm lẫn là cập nhật Environment, rebind @ConfigurationProperties và refresh bean thuộc @RefreshScope. Chúng có lifecycle khác nhau:

- EnvironmentChangeEvent thông báo rằng một hoặc nhiều key trong Environment đã thay đổi. Spring Cloud có thể bind lại các bean @ConfigurationProperties và cập nhật logger level.
- ConfigurationPropertiesRebinder cập nhật trạng thái của bean cấu hình. Với bean JavaBean có constructor không tham số duy nhất, các thuộc tính được reset về mặc định của class trước khi bind lại để giá trị đã xóa không bị giữ lại.
- RefreshScope quản lý target bean qua proxy và cache. Khi refresh, target hiện tại bị hủy; lần gọi tiếp theo tạo một target mới từ bean definition và Environment hiện tại.

Những khác biệt này đặc biệt quan trọng khi nâng cấp Spring Cloud. Một bean dùng constructor binding, một property bị xóa khỏi Config Server, hoặc một DataSource nằm trong danh sách không refreshable có thể khiến kết quả sau refresh khác với điều mà code cũ đang kỳ vọng.

Bài học thuộc chương **Nâng cấp** của module **SPRING_CLOUD_CORE**. Người học sẽ kiểm tra thay đổi cấu hình, xác minh semantics khi xóa property, lựa chọn giữa rebind và Refresh Scope, nhận diện giới hạn của từng cơ chế và xây dựng test hồi quy trước khi nâng cấp release train.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt thay đổi Environment, rebind @ConfigurationProperties và refresh target của @RefreshScope.
2. Giải thích vai trò của EnvironmentChangeEvent và ConfigurationPropertiesRebinder.
3. Kiểm thử property được thay đổi và được bind lại vào một bean mutable.
4. Giải thích khi nào property bị xóa được reset về class-level default.
5. Nhận diện trường hợp constructor binding hoặc nhiều constructor khiến reset về mặc định bị bỏ qua.
6. Phân biệt xóa key khỏi một PropertySource với xóa key khỏi effective Environment.
7. Giải thích giới hạn khi xóa property dùng bởi bean @RefreshScope.
8. Kiểm thử việc hủy và tạo lại target bean trong Refresh Scope.
9. Nhận diện các bean không refreshable như HikariDataSource.
10. Sử dụng extra-refreshable và never-reset-nested-types đúng mục đích.
11. Bảo đảm ứng dụng nhiều replica nhận được thay đổi cấu hình.
12. Thiết kế test hồi quy và quy trình nâng cấp an toàn theo phiên bản Spring Cloud.

## 2. Ba cơ chế cần phân biệt

### 2.1. Environment thay đổi

Environment là tập hợp các PropertySource mà Spring dùng để resolve cấu hình. Một property có thể đến từ application.yml, biến môi trường, system properties, Config Server, Vault hoặc nguồn do ứng dụng tự thêm.

Khi một nguồn thay đổi, giá trị được resolve có thể đổi:

~~~text
Trước:
checkout.endpoint = https://checkout-v1.internal

Sau:
checkout.endpoint = https://checkout-v2.internal
~~~

Thay đổi một Map hoặc cập nhật Config Server chưa tự động bảo đảm mọi bean đã đọc giá trị cũ đều nhận giá trị mới. Environment là nơi resolve giá trị; bean là object đang giữ hoặc đọc giá trị đó.

### 2.2. Rebind @ConfigurationProperties

Một bean @ConfigurationProperties thường giữ nhiều property đã được bind vào field hoặc setter. Spring Cloud có thể nghe EnvironmentChangeEvent và yêu cầu ConfigurationPropertiesRebinder bind lại các bean cấu hình.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    private String endpoint = "https://checkout-default.internal";
    private boolean enabled = false;
    private int timeoutMillis = 1500;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getTimeoutMillis() {
        return timeoutMillis;
    }

    public void setTimeoutMillis(int timeoutMillis) {
        this.timeoutMillis = timeoutMillis;
    }
}
~~~

Nếu Environment cung cấp checkout.endpoint mới và một EnvironmentChangeEvent được phát, bean có thể nhận giá trị mới mà không cần tạo lại toàn bộ ApplicationContext.

### 2.3. Refresh Scope

@RefreshScope là scope đặc biệt dùng proxy và target cache. Khi refresh, Spring hủy target hiện tại. Proxy vẫn là object mà các thành phần khác đang tham chiếu; lần gọi tiếp theo đi qua proxy sẽ khởi tạo target mới.

~~~mermaid
flowchart TD
    A[Caller] --> B[RefreshScope proxy]
    B --> C{Target trong cache?}
    C -->|Có| D[Target hiện tại]
    C -->|Không| E[Tạo target mới]
    E --> F[Đọc Environment hiện tại]
    F --> G[Cache target mới]
    G --> D
    H[Refresh request] --> I[Hủy target trong cache]
    I --> C
~~~

Cơ chế này phù hợp với bean đọc cấu hình khi khởi tạo, chẳng hạn client giữ endpoint hoặc một component có state cần được tạo lại. Nó không làm mới mọi singleton trong ứng dụng.

## 3. EnvironmentChangeEvent và luồng cập nhật

### 3.1. Event mang danh sách key thay đổi

EnvironmentChangeEvent chứa tập hợp key đại diện cho khác biệt giữa Environment trước và sau cập nhật.

Ví dụ:

~~~java
Set<String> changedKeys = Set.of(
        "checkout.endpoint",
        "checkout.timeout-millis"
);

applicationContext.publishEvent(
        new EnvironmentChangeEvent(applicationContext, changedKeys)
);
~~~

Spring Cloud có listener cho event này. Các hành vi mặc định gồm:

- Rebind các bean @ConfigurationProperties trong context.
- Cập nhật log level đối với property có prefix logging.level.

Event không tự tải cấu hình từ Config Server. Một thành phần khác phải cập nhật Environment hoặc gọi quy trình refresh để lấy nguồn cấu hình mới trước khi event được phát.

### 3.2. Config Client không tự polling mặc định

Spring Cloud Config Client không mặc định polling Config Server liên tục để tìm thay đổi. Ứng dụng cần một cơ chế kích hoạt việc cập nhật, ví dụ:

- Gọi endpoint refresh được bảo vệ.
- Dùng Spring Cloud Bus để broadcast refresh event tới các instance.
- Tích hợp một hệ thống điều phối hoặc event nội bộ.
- Gọi API ContextRefresher từ một thành phần được quản lý.

Với ứng dụng có nhiều replica, việc chỉ cập nhật một instance sẽ tạo ra trạng thái không đồng nhất. Spring Cloud Bus có thể phát thông báo để các instance nhận cùng thay đổi.

### 3.3. Rebind thường xử lý toàn bộ bean cấu hình

ConfigurationPropertiesRebinder nhận EnvironmentChangeEvent và thực hiện rebind các bean thuộc phạm vi quản lý của nó. Không nên giả định event có một key thì chỉ bean chứa đúng key đó mới bị đụng tới.

Vì vậy, một bean cấu hình không liên quan trực tiếp tới key thay đổi vẫn có thể đi qua lifecycle rebind. Constructor, setter, nested object và callback của bean cần an toàn khi được khởi tạo hoặc bind lại.

### 3.4. Phân biệt hai endpoint Actuator

| Endpoint | Tác động chính |
| --- | --- |
| POST /actuator/env | Cập nhật Environment, rebind @ConfigurationProperties và log levels |
| POST /actuator/refresh | Nạp lại cấu hình bootstrap/context theo cơ chế tương ứng và refresh các bean @RefreshScope |

Hai endpoint không thay thế nhau. Nếu chỉ cần cập nhật một bean cấu hình mutable, rebind có thể đủ. Nếu cần tạo lại target bean, Refresh Scope mới là cơ chế liên quan.

Endpoint POST /actuator/env cần được bật rõ ràng bằng management.endpoint.env.post.enabled và giới hạn key được phép cập nhật bằng management.endpoint.env.post.valid-keys-regex. Các endpoint này phải được bảo vệ bằng xác thực, phân quyền và network policy phù hợp.

## 4. Rebind bean mutable hoạt động thế nào?

### 4.1. Reset trước, bind sau

Trong Spring Cloud Commons hiện hành, khi một bean @ConfigurationProperties được rebind, Spring Cloud trước tiên reset các property về class-level defaults, sau đó bind lại dữ liệu hiện có trong Environment.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    private String endpoint = "https://checkout-default.internal";

    private int timeoutMillis = 1500;

    // getters and setters
}
~~~

Giả sử lần đầu Environment có:

~~~properties
checkout.endpoint=https://checkout-v1.internal
checkout.timeout-millis=2500
~~~

Sau rebind, bean có:

~~~text
endpoint       = https://checkout-v1.internal
timeoutMillis  = 2500
~~~

Nếu lần cập nhật tiếp theo cung cấp:

~~~properties
checkout.endpoint=https://checkout-v2.internal
~~~

và không còn cung cấp timeout-millis trong effective Environment, bean được reset rồi bind lại thành:

~~~text
endpoint       = https://checkout-v2.internal
timeoutMillis  = 1500
~~~

Giá trị 1500 là mặc định khai báo trong class. Nó không phải giá trị mặc định chung của Spring.

### 4.2. Reset giúp tránh giữ giá trị cũ

Nếu không reset trước, field đã nhận giá trị từ lần bind trước có thể giữ lại khi property bị xóa. Khi đó, người vận hành xóa key trong Config Server nhưng ứng dụng vẫn sử dụng giá trị cũ.

Reset trước giúp đưa bean về trạng thái mặc định có thể xác định, rồi mới áp dụng những property còn tồn tại.

### 4.3. Điều kiện constructor không tham số duy nhất

Cơ chế reset về class-level defaults chỉ thực hiện khi class khai báo constructor không tham số là constructor duy nhất.

Ví dụ phù hợp:

~~~java
@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    private String endpoint = "https://checkout-default.internal";

    public CheckoutProperties() {
    }

    // getters and setters
}
~~~

Nếu class có constructor khác nhận tham số, kể cả vẫn giữ thêm no-arg constructor cho framework, reset sẽ bị bỏ qua.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    private String endpoint;

    public CheckoutProperties() {
        this.endpoint = "https://fallback.internal";
    }

    public CheckoutProperties(HostResolver resolver) {
        this.endpoint = resolver.defaultEndpoint();
    }

    // getters and setters
}
~~~

Trong trường hợp có nhiều constructor, việc tạo một instance mới bằng no-arg constructor có thể không tái tạo được default thực tế của bean ban đầu. Spring Cloud bỏ bước reset để tránh xóa dữ liệu mà không có property source nào từng cung cấp.

Hệ quả là property bị xóa khỏi Environment có thể giữ giá trị cũ trên bean nếu reset bị bỏ qua. Cần viết test riêng cho class có nhiều constructor.

### 4.4. Nested configuration properties

Reset có thể đi sâu vào các nested @ConfigurationProperties object, kể cả nested object không có setter ở parent.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    private Retry retry = new Retry();

    public Retry getRetry() {
        return retry;
    }

    public static class Retry {

        private int maxAttempts = 3;
        private long backoffMillis = 200;

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }

        public long getBackoffMillis() {
            return backoffMillis;
        }

        public void setBackoffMillis(long backoffMillis) {
            this.backoffMillis = backoffMillis;
        }
    }
}
~~~

Nếu nested object chứa trạng thái nội bộ, vòng tham chiếu hoặc object graph của thư viện không nên bị thay đổi, việc reset đệ quy có thể không an toàn.

### 4.5. Loại trừ nested type khỏi reset

Có thể cấu hình spring.cloud.refresh.never-reset-nested-types để loại trừ class hoặc package prefix khỏi việc reset đệ quy.

~~~yaml
spring:
  cloud:
    refresh:
      never-reset-nested-types:
        - com.example.sdk.ClientState
        - com.example.crypto.
~~~

Tên type được so sánh theo prefix của fully qualified class name. Chỉ dùng cấu hình này khi đã hiểu object graph và có lý do giữ nguyên nested state. Nó không làm nested type tự động refresh theo cách khác.

## 5. Xóa property: ba tình huống khác nhau

### 5.1. Key bị xóa khỏi PropertySource ưu tiên cao

Giả sử có hai nguồn:

~~~text
runtime override:
  checkout.timeout-millis = 1000

application.yml:
  checkout.timeout-millis = 2500
~~~

Nếu xóa key khỏi runtime override, Environment vẫn tìm thấy giá trị trong application.yml. Giá trị hiệu lực trở lại 2500.

Đây không phải property bị xóa khỏi Environment. Đây là trường hợp một nguồn ưu tiên cao không còn cung cấp key và resolver quay về nguồn thấp hơn.

### 5.2. Key không còn trong bất kỳ nguồn hiệu lực nào

Nếu key bị xóa khỏi toàn bộ nguồn cấu hình hiệu lực, Environment không còn resolve được property đó. Với bean mutable đủ điều kiện reset, rebind có thể đưa field về class-level default.

Điều này chỉ đúng khi:

- Event refresh được phát với key liên quan.
- Environment đã được cập nhật trước khi event được phát.
- Bean thuộc nhóm được rebinder quản lý.
- Class có no-arg constructor là constructor duy nhất.
- Reset property và nested object không bị loại trừ hoặc thất bại.
- Không có nguồn ưu tiên thấp hơn tiếp tục cung cấp key.

### 5.3. Key bị xóa nhưng class không đủ điều kiện reset

Nếu class có nhiều constructor hoặc reset không thể tạo default instance đáng tin cậy, Spring Cloud bỏ reset. Rebind vẫn áp dụng những property còn được Environment cung cấp, nhưng property đã xóa có thể giữ giá trị trước đó.

Không suy luận rằng mọi bean @ConfigurationProperties đều tự trở về null hoặc default khi xóa key. Hãy kiểm tra constructor và kiểu bean thực tế.

### 5.4. Ví dụ so sánh

| Tình huống | Giá trị sau rebind |
| --- | --- |
| Key mới được thêm hoặc đổi | Bind giá trị mới |
| Key bị xóa ở nguồn ưu tiên cao, còn ở nguồn thấp | Bind giá trị của nguồn thấp |
| Key không còn trong Environment, bean đủ điều kiện reset | Trở về class-level default |
| Key không còn trong Environment, bean không đủ điều kiện reset | Có thể giữ giá trị đã bind trước đó |
| Nested type được khai báo never-reset | Nested state được giữ lại theo giới hạn reset |
| Property có constructor binding/record | Không được refresh theo cơ chế rebind này |

## 6. Constructor binding và Java record

### 6.1. Constructor-bound object là immutable

Spring Boot hỗ trợ constructor binding cho các class immutable và Java record. Ví dụ:

~~~java
@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(
        String endpoint,
        int timeoutMillis
) {
}
~~~

Kiểu dữ liệu này được tạo thông qua constructor với các giá trị đã bind. Nó không có setter để thay đổi field như JavaBean mutable.

### 6.2. Constructor-bound properties không được refresh

Spring Cloud Commons nêu rõ các object dùng constructor binding, bao gồm Java record được đánh dấu @ConfigurationProperties, không thể được refresh bằng cơ chế rebind thông thường.

Không thiết kế record với kỳ vọng EnvironmentChangeEvent sẽ tạo một instance mới rồi thay mọi reference đang dùng bean cũ. Nếu cần thay đổi cấu hình khi runtime:

- Dùng một mutable JavaBean được thiết kế để rebind.
- Đặt bean phụ thuộc vào cấu hình trong @RefreshScope nếu phù hợp.
- Dùng một provider giữ snapshot cấu hình và thay snapshot một cách tường minh.
- Hoặc restart/rollout ApplicationContext khi thay đổi.

### 6.3. Chọn immutable hay mutable theo lifecycle

| Nhu cầu | Thiết kế phù hợp |
| --- | --- |
| Cấu hình chỉ đọc sau startup | Constructor binding hoặc record |
| Cấu hình cần rebind tại runtime | Mutable @ConfigurationProperties |
| Bean stateful cần tạo lại | @RefreshScope |
| Cần snapshot mới được thay nguyên tử | Provider giữ immutable snapshot |
| Thay đổi bean graph hoặc dependency | Restart/deploy lại ứng dụng |

Không hy sinh thiết kế immutable chỉ để bật refresh. Nếu cấu hình hiếm khi thay đổi, restart có kiểm soát thường dễ hiểu hơn.

## 7. Rebind không phải thay instance bean

### 7.1. Bean bị mutate tại chỗ

Khi rebind, ConfigurationPropertiesRebinder reset và bind lại các field trên cùng một instance. Nó không đơn giản tạo instance mới rồi thay thế mọi reference đang giữ bean cũ.

~~~mermaid
sequenceDiagram
    participant Env as Environment
    participant Event as EnvironmentChangeEvent
    participant Rebind as ConfigurationPropertiesRebinder
    participant Bean as CheckoutProperties
    Env->>Event: Publish changed keys
    Event->>Rebind: Notify listener
    Rebind->>Bean: Destroy callbacks
    Rebind->>Bean: Reset fields to defaults
    Rebind->>Bean: Bind current Environment
    Rebind->>Bean: Initialize callbacks
    Note over Bean: Same bean instance, fields changed in place
~~~

Điều này quan trọng với các thread đang đọc bean trong lúc rebind.

### 7.2. Rebind đồng thời được serialize, nhưng reader không được khóa

Spring Cloud serialize các thao tác rebind đồng thời trên cùng bean để hai lần rebind không xen kẽ bước destroy/reset/initialize.

Tuy nhiên, reader ở thread khác không được khóa theo cùng cơ chế. Một thread có thể đọc bean trong lúc các field đang được cập nhật và nhìn thấy trạng thái trung gian.

Ví dụ:

~~~text
Trước rebind:
  endpoint = v1
  timeout  = 1000

Trong lúc rebind:
  endpoint = default
  timeout  = 1000

Sau bind:
  endpoint = v2
  timeout  = 2000
~~~

Một request đọc giữa quá trình có thể kết hợp endpoint và timeout thuộc hai trạng thái khác nhau.

### 7.3. Khi nào cần RefreshScope?

Nếu một bean cần có trạng thái nhất quán khi cấu hình thay đổi, @RefreshScope cung cấp proxy và lock đọc/refresh theo bean. Điều này giúp caller không đọc target trong khi target đang được refresh.

Đây là bảo đảm theo bean. Không nên xem nhiều bean trong toàn ApplicationContext như một transaction cấu hình nguyên tử nếu ứng dụng có nhiều dependency thay đổi cùng lúc.

### 7.4. Không đặt side effect nguy hiểm trong setter

Setter của @ConfigurationProperties có thể được gọi nhiều lần trong lifecycle rebind. Không nên để setter:

- Mở connection mới mà không đóng connection cũ.
- Gửi request tới hệ thống bên ngoài.
- Ghi dữ liệu nghiệp vụ.
- Cập nhật trạng thái toàn cục không thể rollback.
- Tạo thread hoặc scheduler mới mỗi lần bind.

Setter nên cập nhật dữ liệu cấu hình. Việc tạo hoặc thay resource cần lifecycle rõ ràng.

## 8. Giới hạn của Refresh Scope

### 8.1. Proxy và target cache

Bean @RefreshScope được truy cập qua scoped proxy. Scope hoạt động như cache các target đã khởi tạo. Khi cache entry bị invalidate, target hiện tại được hủy và target mới được tạo ở lần gọi tiếp theo.

Các lifecycle callback destroy và initialize được gọi theo bean definition. Những placeholder hoặc expression được đánh giá lại khi target mới được tạo.

### 8.2. Refresh một bean hoặc toàn scope

RefreshScope cung cấp:

~~~java
refreshScope.refresh("checkoutClient");
~~~

để refresh bean cụ thể, và:

~~~java
refreshScope.refreshAll();
~~~

để invalidate toàn bộ target trong scope.

Tên bean cần được kiểm tra theo tên đăng ký thực tế trong ApplicationContext. Sau khi invalidate, proxy vẫn tồn tại; target mới chỉ được tạo khi có lời gọi tiếp theo.

### 8.3. @RefreshScope trên @Configuration không bao phủ mọi @Bean

Đánh dấu một lớp @Configuration bằng @RefreshScope không có nghĩa tất cả các bean được khai báo bằng @Bean trong lớp đó tự động thuộc refresh scope.

Nếu bean khác phụ thuộc vào các bean đó, dependency có thể vẫn giữ instance cũ. Nếu muốn dependency được tái tạo cùng lúc, cần thiết kế scope cho bean phù hợp hoặc đưa lifecycle vào một factory riêng.

### 8.4. HikariDataSource mặc định không refreshable

HikariDataSource nằm trong danh sách mặc định của spring.cloud.refresh.never-refreshable. Do đó, không giả định thay JDBC URL hoặc credential rồi gọi refresh sẽ tạo lại Hikari pool.

Nếu cần thay database connection pool, hãy thiết kế cách thay resource có kiểm soát hoặc restart instance. Chỉ đổi danh sách never-refreshable khi đã hiểu rõ lifecycle và tương thích của DataSource implementation.

### 8.5. extra-refreshable

spring.cloud.refresh.extra-refreshable cho phép bổ sung tên bean hoặc class cần được post-process vào refresh scope, đặc biệt hữu ích khi không thể gắn @RefreshScope trực tiếp lên bean do thư viện cung cấp.

~~~yaml
spring:
  cloud:
    refresh:
      extra-refreshable:
        - com.example.partner.LegacyClient
~~~

Đây không phải giải pháp phổ quát cho mọi object immutable. Bean phải có thể được khởi tạo lại an toàn từ bean definition và dependency hiện tại.

### 8.6. never-refreshable

spring.cloud.refresh.never-refreshable chỉ định các bean name hoặc class không được refresh/rebind.

~~~yaml
spring:
  cloud:
    refresh:
      never-refreshable:
        - com.zaxxer.hikari.HikariDataSource
        - com.example.crypto.HardwareKeyStore
~~~

Dùng danh sách này để bảo vệ resource hoặc object có internal state không phù hợp với lifecycle refresh. Kiểm tra đúng tên bean hoặc class trong phiên bản đang dùng.

### 8.7. Property bị xóa trong Refresh Scope

Spring Cloud Commons mô tả một giới hạn riêng: xóa một configuration value rồi thực hiện refresh không cập nhật sự hiện diện của property như một giá trị mới. Property cần còn hiện diện để giá trị của nó được cập nhật qua refresh.

Vì vậy, không dùng thao tác xóa key làm tín hiệu duy nhất để bean @RefreshScope chuyển sang trạng thái tắt hoặc bỏ cấu hình.

Thay vào đó, giữ property và dùng một giá trị tường minh:

~~~yaml
checkout:
  mode: disabled
  endpoint: https://checkout.internal
~~~

Hoặc:

~~~yaml
checkout:
  enabled: false
~~~

Bean mới có thể đọc trạng thái disabled và ngừng sử dụng endpoint. Cách này giúp sự thay đổi được biểu diễn thành một giá trị cụ thể mà ứng dụng có thể kiểm tra.

### 8.8. AOT và native image

Spring Cloud Context Refresh không được hỗ trợ cho Spring AOT transformations và native images. Với hai mô hình này, cần đặt:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

Không dùng Refresh Scope như một cách cập nhật bean trong native image. Hãy dùng startup configuration, runtime data provider được thiết kế riêng hoặc rolling restart.

## 9. @Value, Environment và ConfigurationProperties

### 9.1. @Value trong singleton thông thường

Một bean singleton đọc property vào field lúc khởi tạo:

~~~java
@Component
public class CheckoutClient {

    @Value("${checkout.endpoint}")
    private String endpoint;

    public String endpoint() {
        return endpoint;
    }
}
~~~

Field này không tự được cập nhật chỉ vì EnvironmentChangeEvent được phát. Nó đã nhận giá trị khi bean được khởi tạo.

### 9.2. @Value với RefreshScope

Nếu bean dùng @RefreshScope, target mới được tạo lại và placeholder được resolve lại:

~~~java
@Component
@RefreshScope
public class CheckoutClient {

    @Value("${checkout.endpoint}")
    private String endpoint;

    public String endpoint() {
        return endpoint;
    }
}
~~~

Khi target bị invalidate và tạo lại, giá trị được inject từ Environment tại thời điểm target mới khởi tạo.

### 9.3. Đọc Environment mỗi lần gọi

Một component có thể đọc Environment tại thời điểm sử dụng:

~~~java
@Component
public class CheckoutEndpointProvider {

    private final Environment environment;

    public CheckoutEndpointProvider(Environment environment) {
        this.environment = environment;
    }

    public String currentEndpoint() {
        return environment.getRequiredProperty("checkout.endpoint");
    }
}
~~~

Cách này đọc giá trị hiện tại mỗi lần gọi, miễn là Environment đã được cập nhật. Tuy nhiên, nó không tự tạo lại HTTP client, connection pool hoặc resource đã được tạo từ endpoint cũ.

### 9.4. Chọn đúng abstraction

| Cách đọc cấu hình | Cập nhật khi Environment đổi? | Ghi chú |
| --- | --- | --- |
| @Value trong singleton | Không tự cập nhật field | Cần refresh target hoặc tạo lại bean |
| Environment.getProperty mỗi lần gọi | Đọc giá trị hiện tại | Resource đã tạo không tự thay đổi |
| Mutable @ConfigurationProperties | Có thể rebind | Cần chú ý reset và concurrency |
| Constructor-bound record | Không hỗ trợ rebind | Dùng startup/restart |
| Bean @RefreshScope | Target được tạo lại sau invalidate | Chỉ áp dụng cho bean thuộc scope |

## 10. Kiểm thử rebind khi property thay đổi

### 10.1. Chuẩn bị bean cấu hình mutable

Dùng một class có constructor không tham số duy nhất và default được khai báo ở field:

~~~java
@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    private String endpoint = "https://checkout-default.internal";

    private int timeoutMillis = 1500;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public int getTimeoutMillis() {
        return timeoutMillis;
    }

    public void setTimeoutMillis(int timeoutMillis) {
        this.timeoutMillis = timeoutMillis;
    }
}
~~~

Đăng ký class bằng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties.

### 10.2. Test EnvironmentChangeEvent

Ví dụ integration test:

~~~java
@SpringBootTest
class CheckoutPropertiesRefreshTest {

    @Autowired
    ConfigurableEnvironment environment;

    @Autowired
    ApplicationEventPublisher events;

    @Autowired
    CheckoutProperties properties;

    @Autowired
    ApplicationContext context;

    @Test
    void rebindsPropertiesAfterEnvironmentChange() {
        Map<String, Object> values = new ConcurrentHashMap<>();

        MapPropertySource runtimeSource =
                new MapPropertySource("runtime-test", values);

        environment.getPropertySources().addFirst(runtimeSource);

        values.put(
                "checkout.endpoint",
                "https://checkout-v2.internal"
        );

        values.put("checkout.timeout-millis", 2500);

        events.publishEvent(
                new EnvironmentChangeEvent(
                        context,
                        Set.of(
                                "checkout.endpoint",
                                "checkout.timeout-millis"
                        )
                )
        );

        assertThat(properties.getEndpoint())
                .isEqualTo("https://checkout-v2.internal");

        assertThat(properties.getTimeoutMillis())
                .isEqualTo(2500);
    }
}
~~~

Test cần chạy trong context có Spring Cloud Context và ConfigurationPropertiesRebinder được auto-configure. MapPropertySource dùng map mutable để test có thể thay đổi giá trị trong cùng PropertySource.

### 10.3. Test property bị xóa và reset về default

Có thể mở rộng test:

~~~java
@Test
void removedPropertyReturnsToClassDefaultWhenBeanCanBeReset() {
    Map<String, Object> values = new ConcurrentHashMap<>();

    MapPropertySource runtimeSource =
            new MapPropertySource("runtime-test", values);

    environment.getPropertySources().addFirst(runtimeSource);

    values.put(
            "checkout.endpoint",
            "https://temporary.internal"
    );

    events.publishEvent(
            new EnvironmentChangeEvent(
                    context,
                    Set.of("checkout.endpoint")
            )
    );

    assertThat(properties.getEndpoint())
            .isEqualTo("https://temporary.internal");

    values.remove("checkout.endpoint");

    events.publishEvent(
            new EnvironmentChangeEvent(
                    context,
                    Set.of("checkout.endpoint")
            )
    );

    assertThat(environment.getProperty("checkout.endpoint"))
            .isNull();

    assertThat(properties.getEndpoint())
            .isEqualTo("https://checkout-default.internal");
}
~~~

Test này mô phỏng rebind listener khi key đã thực sự biến mất khỏi effective Environment. Nếu một PropertySource thấp hơn vẫn có checkout.endpoint, assertion Environment null sẽ không đúng và bean sẽ nhận giá trị từ nguồn đó.

### 10.4. Test class có nhiều constructor

Tạo một bean cấu hình có no-arg constructor và một constructor khác nhận dependency. Kiểm tra rằng việc xóa key không tự động đưa field về default của no-arg constructor.

Đừng viết test giả định rằng mọi class có một no-arg constructor đều được reset. Điều kiện của Spring Cloud là no-arg constructor phải là constructor duy nhất được khai báo.

### 10.5. Test nested properties

Tạo nested object có default riêng. Cập nhật rồi xóa một nested property, sau đó xác nhận giá trị reset đúng. Nếu nested type được khai báo trong never-reset-nested-types, xác nhận state của nó được giữ nguyên theo chính sách.

## 11. Kiểm thử RefreshScope

### 11.1. Bean đọc cấu hình khi tạo target

~~~java
@Component
@RefreshScope
public class CheckoutEndpoint {

    private final String endpoint;
    private final String mode;

    public CheckoutEndpoint(Environment environment) {
        this.endpoint = environment.getProperty(
                "checkout.endpoint",
                "https://checkout-default.internal"
        );

        this.mode = environment.getProperty(
                "checkout.mode",
                "enabled"
        );
    }

    public String endpoint() {
        return endpoint;
    }

    public String mode() {
        return mode;
    }
}
~~~

Bean lưu giá trị trong constructor. Vì vậy, khi target mới được tạo, nó đọc cấu hình mới từ Environment.

### 11.2. Test target được tạo lại

~~~java
@SpringBootTest
class CheckoutEndpointRefreshTest {

    @Autowired
    ConfigurableEnvironment environment;

    @Autowired
    RefreshScope refreshScope;

    @Autowired
    CheckoutEndpoint checkoutEndpoint;

    @Test
    void refreshCreatesTargetWithNewValues() {
        Map<String, Object> values = new ConcurrentHashMap<>();

        MapPropertySource source =
                new MapPropertySource("runtime-test", values);

        environment.getPropertySources().addFirst(source);

        values.put(
                "checkout.endpoint",
                "https://checkout-v2.internal"
        );

        values.put("checkout.mode", "enabled");

        refreshScope.refresh("checkoutEndpoint");

        assertThat(checkoutEndpoint.endpoint())
                .isEqualTo("https://checkout-v2.internal");

        values.put(
                "checkout.endpoint",
                "https://checkout-v3.internal"
        );

        refreshScope.refresh("checkoutEndpoint");

        assertThat(checkoutEndpoint.endpoint())
                .isEqualTo("https://checkout-v3.internal");
    }
}
~~~

Test này xác nhận proxy vẫn được inject và target được tạo lại sau khi cache entry bị invalidate. Tên bean checkoutEndpoint cần khớp tên đăng ký trong context.

### 11.3. Test trạng thái disabled bằng sentinel

Với Refresh Scope, dùng một property còn hiện diện để biểu diễn trạng thái tắt:

~~~java
values.put("checkout.mode", "disabled");
refreshScope.refresh("checkoutEndpoint");

assertThat(checkoutEndpoint.mode()).isEqualTo("disabled");
~~~

Đây là test hồi quy phù hợp hơn việc chỉ xóa checkout.mode rồi kỳ vọng bean tự suy ra rằng tính năng đã tắt.

### 11.4. Test resource lifecycle

Nếu target quản lý HTTP client, connection hoặc thread pool, kiểm tra:

- Destroy callback được gọi khi target bị refresh.
- Target mới được khởi tạo ở lần truy cập tiếp theo.
- Client cũ được đóng.
- Request đang chạy có thể hoàn tất theo chính sách.
- Không tạo nhiều connection pool cùng lúc ngoài dự kiến.
- Lỗi khi tạo target mới được ghi nhận và health phản ánh trạng thái phù hợp.

Không chỉ kiểm tra rằng getter trả giá trị mới. Một bean có thể giữ giá trị mới nhưng resource bên dưới vẫn dùng cấu hình cũ.

## 12. Kiểm tra các bean không refreshable

### 12.1. HikariDataSource

HikariDataSource là loại DataSource mặc định trong danh sách never-refreshable của Spring Cloud. Khi nâng cấp, kiểm tra xem code có kỳ vọng JDBC URL, username hoặc password thay đổi ngay sau refresh hay không.

Nếu có, lựa chọn phù hợp thường là:

- Rolling restart các instance.
- Tạo factory thay pool có lifecycle và drain rõ ràng.
- Dùng một DataSource implementation khác nếu đã xác minh nó hỗ trợ lifecycle mong muốn.

Không xóa Hikari khỏi never-refreshable chỉ để endpoint refresh trả kết quả khác. Pool đang có connection và thread nội bộ; thay đổi không an toàn có thể gây lỗi kết nối hoặc rò rỉ resource.

### 12.2. Bean immutable từ thư viện

Một số bean do thư viện bên thứ ba tạo ra không thể gắn @RefreshScope trực tiếp. Có thể dùng extra-refreshable nếu việc tạo lại bean từ bean definition là an toàn.

Trước khi thêm class vào extra-refreshable, kiểm tra:

- Constructor có thể chạy lại không?
- Dependency có được inject lại không?
- Có resource cần đóng không?
- Có side effect khi khởi tạo không?
- Có thread hoặc scheduler được tạo trong constructor không?
- Bean có được các component khác giữ reference trực tiếp không?

### 12.3. Bean không nên refresh

Đặt bean vào never-refreshable khi nó giữ trạng thái nội bộ không phù hợp để tạo lại hoặc rebind. Tài liệu hiện hành cho phép khai báo tên bean hoặc class name trong danh sách này.

### 12.4. Không refresh bean chỉ vì nó có property

Một bean có property không đồng nghĩa bean đó cần Refresh Scope. Nếu giá trị chỉ cần đọc khi startup, dùng cấu hình bình thường và restart khi thay đổi. Refresh Scope chỉ nên áp dụng cho bean có lifecycle và hành vi khi tái tạo đã được kiểm thử.

## 13. Actuator, bảo mật và quan sát

### 13.1. /actuator/env

POST /actuator/env có thể cập nhật Environment và kích hoạt rebind @ConfigurationProperties cùng log levels. Để bật POST, cấu hình:

~~~yaml
management:
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: "^(checkout\\.|logging\\.level\\.).*"
~~~

Regex ở ví dụ chỉ cho phép cập nhật key thuộc checkout và logging.level. Điều chỉnh theo ứng dụng thực tế.

### 13.2. /actuator/refresh

Endpoint refresh kích hoạt việc nạp lại cấu hình theo ContextRefresher và refresh các bean @RefreshScope. Nếu ứng dụng không dùng refresh scope, không nên expose endpoint chỉ vì một ứng dụng khác đang dùng nó.

### 13.3. /actuator/configprops

Endpoint configprops hữu ích để xác minh giá trị đã bind vào bean @ConfigurationProperties. Dùng endpoint trong môi trường quản trị được bảo vệ và bảo đảm các field nhạy cảm được che.

### 13.4. RefreshScopeHealthIndicator

Spring Cloud có RefreshScopeHealthIndicator để theo dõi lỗi khi bean không thể re-initialize hoặc rebind sau context refresh. Nếu refresh thất bại, health indicator có thể chuyển trạng thái DOWN và cung cấp thông tin exception liên quan.

Theo dõi health cùng log, metrics và trạng thái rollout. Một refresh request trả HTTP thành công không nhất thiết có nghĩa mọi resource bên dưới đã sẵn sàng phục vụ với cấu hình mới.

### 13.5. Bảo vệ endpoint

Các endpoint thay đổi Environment có thể cho phép thay endpoint, log level hoặc cấu hình nhạy cảm. Cần:

- Xác thực caller.
- Phân quyền theo role.
- Giới hạn network access.
- Giới hạn key được phép cập nhật.
- Ghi audit người gọi, thời điểm và key thay đổi.
- Không ghi plaintext secret vào log.
- Không expose endpoint quản trị ra public internet.

## 14. Ảnh hưởng khi nâng cấp Spring Cloud

### 14.1. Kiểm tra đúng release train

Spring Cloud Commons có nhiều release train và semantics có thể được bổ sung theo phiên bản. Trước khi nâng cấp:

1. Xác định Spring Boot version.
2. Chọn Spring Cloud release train tương thích.
3. Dùng Spring Cloud BOM để khóa dependency.
4. Đọc tài liệu của đúng phiên bản, không chỉ trang current.
5. Kiểm tra configuration metadata và default values.
6. Chạy lại test rebind, deletion và Refresh Scope.

Không ép một phiên bản Spring Cloud mới vào Spring Boot cũ chỉ vì dependency compile được.

### 14.2. Kiểm tra các thuộc tính refresh mới hoặc thay đổi

Các thuộc tính cần rà soát trong cấu hình:

| Property | Vai trò |
| --- | --- |
| spring.cloud.refresh.enabled | Bật/tắt refresh auto-configuration |
| spring.cloud.refresh.extra-refreshable | Bổ sung bean/class được xử lý như refreshable |
| spring.cloud.refresh.never-refreshable | Bean/class không được refresh hoặc rebind |
| spring.cloud.refresh.never-reset-nested-types | Nested type không được reset đệ quy |
| spring.cloud.refresh.on-restart.enabled | Refresh context khi JVM restart sau checkpoint/restore |
| management.health.refresh.enabled | Bật/tắt RefreshScopeHealthIndicator |

Kiểm tra default của từng property trong configprops của release train thực tế.

### 14.3. Kiểm tra constructor của ConfigurationProperties

Một thay đổi trong class cấu hình có thể làm reset behavior thay đổi mà không cần sửa file YAML.

Ví dụ, thêm constructor nhận dependency vào một JavaBean vốn chỉ có no-arg constructor có thể khiến reset về class defaults bị bỏ qua. Khi nâng cấp code hoặc thư viện, kiểm tra constructor và cách bean được tạo.

### 14.4. Kiểm tra bean do auto-configuration tạo

Thay đổi dependency có thể đổi loại bean hoặc class implementation. Ví dụ DataSource có thể vẫn là HikariDataSource sau khi nâng cấp dù code không khai báo trực tiếp.

Dùng ApplicationContext hoặc configprops để xác minh type thực tế, rồi so sánh với never-refreshable.

### 14.5. Kiểm tra AOT và native image

Context Refresh không được hỗ trợ cho Spring AOT transformations và native images. Với hai mô hình này, đặt spring.cloud.refresh.enabled=false và không phụ thuộc vào endpoint refresh.

Khi nâng cấp, kiểm tra profile build-time, bean graph và cấu hình runtime theo đúng mô hình AOT/native. Dùng rolling restart hoặc runtime data provider cho những thay đổi cần áp dụng khi process đang chạy.

## 15. Ma trận quyết định rebind hay RefreshScope

| Tình huống | Rebind @ConfigurationProperties | @RefreshScope |
| --- | --- | --- |
| Thay giá trị timeout đơn giản | Thường phù hợp | Có thể dùng nếu bean cần target mới |
| Thay endpoint được lưu trong field | Rebind nếu bean mutable | Tạo target mới nếu bean stateful |
| Xóa property và về default | Có thể nếu class đủ điều kiện reset | Không dựa vào việc xóa key |
| Bean dùng constructor binding | Không hỗ trợ | Không giải quyết việc rebind immutable config object trực tiếp |
| Cần giữ cùng bean instance | Có | Proxy giữ ổn định, target thay đổi |
| Cần đọc trạng thái nhất quán khi refresh | Có rủi ro reader thấy state trung gian | Read/refresh được serialize theo bean |
| HikariDataSource | Không refreshable mặc định | Không refreshable mặc định |
| Thay bean graph hoặc classpath | Không phù hợp | Không phù hợp |
| Native image/AOT | Context Refresh không được hỗ trợ | Context Refresh không được hỗ trợ |

## 16. Quy trình nâng cấp và kiểm thử hồi quy

### Bước 1 — Kiểm kê property động

Liệt kê các property có thể thay đổi sau startup:

- Endpoint downstream.
- Timeout và retry.
- Feature flags.
- Log levels.
- Pool sizing.
- Database credentials.
- TLS material.
- Danh sách routing hoặc tenant.

Ghi nhận bean nào đang giữ property và cách bean nhận giá trị.

### Bước 2 — Phân loại bean

Chia thành:

- Mutable @ConfigurationProperties cần rebind.
- Constructor-bound properties chỉ đọc lúc startup.
- Bean @RefreshScope cần tạo lại target.
- Bean/resource không refreshable.
- Runtime data nên nằm trong provider hoặc store riêng.

### Bước 3 — Kiểm tra semantics khi xóa key

Với mỗi property có thể bị xóa:

1. Xác định property source ưu tiên cao.
2. Kiểm tra còn nguồn thấp hơn cung cấp key không.
3. Kiểm tra class có no-arg constructor duy nhất không.
4. Kiểm tra nested type có được reset không.
5. Xác nhận class-level default.
6. Kiểm tra behavior của bean sau rebind.
7. Nếu dùng RefreshScope, thay deletion bằng sentinel hoặc explicit state.

### Bước 4 — Viết test trước khi đổi dependency

Tạo test cho:

- Thay property từ giá trị cũ sang mới.
- Xóa property khỏi effective Environment.
- Xóa property khỏi nguồn ưu tiên cao nhưng còn ở nguồn thấp.
- Bean có nhiều constructor.
- Constructor-bound record.
- Nested configuration properties.
- RefreshScope target recreation.
- HikariDataSource và never-refreshable.
- Nhiều replica nhận cùng event.

### Bước 5 — Nâng cấp BOM và chạy test

Nâng Spring Boot/Spring Cloud theo release train tương thích. Chạy test hồi quy trên dependency mới và kiểm tra startup warnings, bean type, Actuator configprops và health.

### Bước 6 — Kiểm thử staging

Thử cập nhật Config Server hoặc nguồn cấu hình test. Xác nhận tất cả instance nhận cùng revision, các bean đúng trạng thái và resource cũ được đóng an toàn.

### Bước 7 — Theo dõi và rollback

Ghi nhận:

- Artifact version.
- Spring Boot version.
- Spring Cloud release train.
- Config revision.
- Active profiles.
- Số lần refresh.
- Lỗi rebind.
- RefreshScopeHealthIndicator.
- Connection pool và downstream errors.

Nếu refresh thất bại, rollback cấu hình hoặc rollout artifact đã kiểm thử. Không lặp lại refresh liên tục khi nguyên nhân là bean không thể rebind hoặc resource không refreshable.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Bean vẫn giữ property cũ sau khi xóa key | Bean không đủ điều kiện reset hoặc key vẫn còn ở nguồn thấp | Kiểm tra constructor và toàn bộ PropertySource |
| Giá trị quay về null thay vì default mong muốn | Class không khai báo default ở field hoặc constructor | Định nghĩa default rõ ràng và kiểm tra reset eligibility |
| Record không cập nhật sau event | Constructor binding không được refresh | Dùng startup/restart hoặc mutable configuration model |
| Một request thấy endpoint mới nhưng timeout cũ | Reader quan sát bean trong lúc rebind tại chỗ | Dùng RefreshScope hoặc immutable snapshot |
| @Value singleton vẫn giữ giá trị cũ | Field chỉ được inject khi bean khởi tạo | Dùng Environment động hoặc RefreshScope |
| Xóa key không tắt tính năng | RefreshScope không áp dụng việc xóa key như trạng thái mới | Dùng enabled=false hoặc mode=disabled |
| Hikari pool không thay URL | HikariDataSource mặc định never-refreshable | Dùng restart hoặc pool replacement có lifecycle |
| Bean trong @Configuration không được refresh | @RefreshScope trên config class không scope mọi @Bean | Annotate bean cần thiết hoặc thiết kế factory |
| Bean mới không khởi tạo sau refresh | Constructor hoặc dependency thất bại | Kiểm tra RefreshScopeHealthIndicator và logs |
| Một replica nhận cấu hình, replica khác không | Event chỉ được phát cục bộ hoặc Bus không hoạt động | Kiểm tra Spring Cloud Bus và broadcast |
| POST /actuator/env trả lỗi | POST chưa bật hoặc key bị regex chặn | Kiểm tra endpoint config và valid-keys-regex |
| Rebind gây side effect lặp | Setter hoặc init callback tạo resource mỗi lần bind | Tách cấu hình khỏi lifecycle resource |
| Nâng cấp xong refresh behavior đổi | Release train hoặc bean constructor/type đổi | Đọc docs đúng version và chạy regression tests |
| Native image không hỗ trợ refresh | Context Refresh không tương thích AOT/native | Đặt spring.cloud.refresh.enabled=false và rollout |

## 18. Checklist trước khi phát hành

### Environment và event

- [ ] Environment được cập nhật trước khi EnvironmentChangeEvent phát.
- [ ] Changed keys được xác định chính xác.
- [ ] Các replica nhận event hoặc refresh signal.
- [ ] Không dựa vào Config Client polling mặc định.
- [ ] Logging level changes được kiểm tra riêng.

### Rebind

- [ ] Bean mutable có default rõ ràng.
- [ ] Constructor không tham số là constructor duy nhất nếu cần reset về default.
- [ ] Constructor-bound record không được kỳ vọng rebind.
- [ ] Nested properties được kiểm tra.
- [ ] Nested library types không bị reset ngoài ý muốn.
- [ ] Setter và initialization callback không tạo side effect nguy hiểm.
- [ ] Test có trường hợp key được thêm, đổi và xóa.

### Refresh Scope

- [ ] Bean thực sự cần tạo lại mới dùng @RefreshScope.
- [ ] Không giả định @RefreshScope trên @Configuration áp dụng cho mọi @Bean.
- [ ] HikariDataSource và các bean never-refreshable được nhận diện.
- [ ] extra-refreshable chỉ dùng với bean có thể khởi tạo lại an toàn.
- [ ] Không dùng deletion làm tín hiệu disable.
- [ ] Target destroy/recreate và resource cleanup được kiểm thử.

### Vận hành và bảo mật

- [ ] Actuator endpoint được bảo vệ.
- [ ] POST /actuator/env giới hạn valid keys.
- [ ] configprops và env được expose có kiểm soát.
- [ ] RefreshScopeHealthIndicator được theo dõi.
- [ ] Có log/audit cho thay đổi cấu hình.
- [ ] Native image/AOT tắt Context Refresh.
- [ ] Có rolling restart hoặc rollback plan.

## 19. Bài tập vận dụng

**Bài tập 1 — Rebind một property.** Tạo CheckoutProperties mutable, thêm MapPropertySource runtime, phát EnvironmentChangeEvent và xác nhận endpoint thay đổi.

**Bài tập 2 — Xóa key.** Xóa checkout.timeout-millis khỏi PropertySource duy nhất chứa key. Phát event và xác nhận bean trở về class-level default.

**Bài tập 3 — PropertySource precedence.** Đặt cùng key ở runtime override và application.yml. Xóa key ở runtime override rồi chứng minh giá trị từ application.yml thắng.

**Bài tập 4 — Nhiều constructor.** Thêm constructor nhận dependency vào CheckoutProperties. Xóa một property và quan sát vì sao reset về class-level defaults bị bỏ qua.

**Bài tập 5 — Nested properties.** Tạo nested RetryProperties và kiểm tra reset đệ quy. Thêm type vào never-reset-nested-types rồi so sánh.

**Bài tập 6 — Record.** Tạo record @ConfigurationProperties và xác nhận thiết kế không dựa vào runtime rebind; kiểm thử restart context để nhận giá trị mới.

**Bài tập 7 — RefreshScope.** Tạo CheckoutEndpoint có @RefreshScope, thay endpoint trong Environment, refresh target và xác nhận target mới được khởi tạo.

**Bài tập 8 — Sentinel thay deletion.** Dùng checkout.mode=disabled thay cho xóa checkout.mode. Xác nhận bean chuyển sang trạng thái tắt sau refresh.

**Bài tập 9 — HikariDataSource.** Kiểm tra DataSource type và never-refreshable. Thiết kế một quy trình restart hoặc pool replacement thay cho refresh trực tiếp.

**Bài tập 10 — Nhiều replica.** Chạy hai instance và broadcast thay đổi bằng Spring Cloud Bus. Xác nhận cả hai instance cùng revision và giá trị cấu hình.

**Bài tập 11 — Actuator security.** Bật POST /actuator/env với valid-keys-regex giới hạn. Kiểm tra caller không đủ quyền không thể thay property.

**Bài tập 12 — Upgrade regression.** Nâng Spring Cloud BOM, chạy lại toàn bộ test rebind/deletion/refresh và so sánh hành vi với release train trước.

## 20. Ghi nhớ và nguồn tra cứu

- EnvironmentChangeEvent thông báo key thay đổi; nó không tự tải cấu hình từ Config Server.
- Spring Cloud Config Client không mặc định polling; ứng dụng nhiều replica nên dùng cơ chế broadcast như Spring Cloud Bus.
- Rebind @ConfigurationProperties cập nhật bean cấu hình mutable và logger levels.
- Rebind mutate cùng instance tại chỗ; concurrent readers có thể thấy trạng thái trung gian.
- Rebind reset về class-level defaults chỉ khi class có constructor không tham số là constructor duy nhất.
- Nếu key bị xóa khỏi một nguồn nhưng còn trong nguồn ưu tiên thấp, Environment vẫn có giá trị và bean sẽ bind giá trị đó.
- Constructor binding và Java record không được refresh bằng cơ chế rebind thông thường.
- @RefreshScope dùng proxy và target cache; refresh hủy target hiện tại và tạo target mới ở lần gọi tiếp theo.
- Xóa key không phải tín hiệu đáng tin cậy để thay đổi sự hiện diện của property trong Refresh Scope; dùng explicit sentinel như enabled=false hoặc mode=disabled.
- HikariDataSource mặc định thuộc never-refreshable.
- @RefreshScope trên @Configuration không tự làm mọi @Bean bên trong refresh scoped.
- Kiểm tra đúng Spring Cloud release train vì reset behavior và configuration properties có thể thay đổi theo phiên bản.
- Context Refresh không được hỗ trợ trong Spring AOT transformations và native images; đặt spring.cloud.refresh.enabled=false trong các mô hình này.

Nguồn chính thức để đối chiếu theo phiên bản Spring Boot/Spring Cloud của dự án:

1. [Spring Cloud Commons 5.0.4 – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
2. [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
3. [Spring Cloud Commons – EnvironmentChangeEvent source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/environment/EnvironmentChangeEvent.java)
4. [Spring Cloud Commons – ConfigurationPropertiesRebinder source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/properties/ConfigurationPropertiesRebinder.java)
5. [Spring Cloud Commons – ContextRefresher source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/refresh/ContextRefresher.java)
6. [Spring Cloud Commons – RefreshScope source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/scope/refresh/RefreshScope.java)
7. [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
8. [Spring Boot – Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
9. [Spring Cloud Bus – Broadcasting configuration changes](https://docs.spring.io/spring-cloud-bus/reference/)
10. [Spring Cloud – Release train và tương thích Spring Boot](https://spring.io/projects/spring-cloud/)

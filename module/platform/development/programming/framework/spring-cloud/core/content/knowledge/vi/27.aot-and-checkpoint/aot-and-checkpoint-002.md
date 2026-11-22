# Giới hạn Context Refresh trong AOT và native image

Spring Cloud Context cung cấp cơ chế cập nhật cấu hình và làm mới bean khi ứng dụng đang chạy. Trong ứng dụng JVM thông thường, annotation @RefreshScope có thể tạo proxy cho bean, xóa target đã cache và khởi tạo lại target khi bean được gọi lần tiếp theo. Endpoint /actuator/refresh có thể kích hoạt quy trình này sau khi Environment được cập nhật.

Cơ chế đó không tương thích với mô hình Spring AOT và GraalVM native image. AOT phân tích ứng dụng ở build time, tạo mã khởi tạo và các hint cần thiết dựa trên classpath, Environment và bean definitions tại thời điểm build. Spring Cloud Context không hỗ trợ Context Refresh trong AOT transformations và native images. Vì vậy, ứng dụng chạy theo hai mô hình này phải đặt:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

Giới hạn này không có nghĩa Spring Cloud Config Client không thể chạy trong native image. Config Client hỗ trợ AOT/native image từ Spring Cloud Config 4.0.0, với các điều kiện riêng về Config Data và nguồn cấu hình ở build time. Ứng dụng vẫn có thể lấy cấu hình khi khởi động; điều không được hỗ trợ là dựa vào Spring Cloud Context để refresh context và các bean refresh scope trong lúc process đang chạy.

Bài học thuộc chương **AOT và checkpoint** của module **SPRING_CLOUD_CORE**. Người học sẽ phân biệt AOT processing với runtime refresh, hiểu vì sao bean graph phải ổn định, cấu hình đúng spring.cloud.refresh.enabled, thiết kế cách áp dụng thay đổi cấu hình khi không có Context Refresh và phân biệt native image với JVM checkpoint/restore bằng Project CRaC.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt AOT processing, native image, Spring ApplicationContext refresh và Spring Cloud Context Refresh.
2. Giải thích cách AOT tạo mã khởi tạo từ classpath, Environment và bean definitions tại build time.
3. Mô tả vai trò của @RefreshScope, proxy và target cache trong ứng dụng JVM thông thường.
4. Giải thích vì sao Spring Cloud Context Refresh không được hỗ trợ trong AOT transformations và native images.
5. Cấu hình spring.cloud.refresh.enabled=false đúng thời điểm build và runtime.
6. Nhận diện các hạn chế liên quan tới @Profile, @Conditional và property ảnh hưởng bean creation.
7. Phân biệt khả năng AOT/native image của Config Client với khả năng refresh runtime.
8. Xây dựng chiến lược cập nhật cấu hình bằng rolling restart hoặc cơ chế dữ liệu động riêng.
9. Phân biệt native image với JVM checkpoint/restore của Project CRaC.
10. Kiểm thử startup, cấu hình, endpoint và hành vi sau restore trong từng mô hình triển khai.

## 2. Làm rõ các khái niệm

### 2.1. Spring ApplicationContext

ApplicationContext là container quản lý bean, dependency injection, event, resource và lifecycle của ứng dụng Spring. Trong startup thông thường, Spring đọc cấu hình, tạo bean definitions, khởi tạo bean và hoàn tất quá trình refresh context trước khi ứng dụng sẵn sàng phục vụ request.

Từ “refresh” trong ApplicationContext.refresh() chỉ quá trình khởi tạo hoặc làm mới container theo lifecycle của Spring. Nó không đồng nghĩa với việc một ứng dụng Spring Cloud đang chạy nhận cấu hình mới qua /actuator/refresh.

### 2.2. Spring Cloud Context Refresh

Spring Cloud Context bổ sung cơ chế thay đổi Environment và làm mới một số bean mà không cần khởi động lại toàn bộ process.

Các thành phần liên quan gồm:

- ContextRefresher: phối hợp việc nạp lại property sources và phát hiện thay đổi cấu hình.
- EnvironmentChangeEvent: thông báo các key đã thay đổi.
- Rebinding: bind lại một số bean ConfigurationProperties.
- RefreshScope: scope quản lý target bean có thể được khởi tạo lại.
- @RefreshScope: đánh dấu bean sử dụng refresh scope.
- /actuator/refresh: endpoint có thể kích hoạt refresh khi được cấu hình và expose.

Trong mô hình JVM thông thường, đây là cơ chế runtime. Nó không phải một phần của quá trình build AOT.

### 2.3. Spring AOT

AOT là viết tắt của Ahead-of-Time. Spring phân tích ứng dụng ở build time để tạo ra các thành phần hỗ trợ khởi tạo runtime hiệu quả hơn, chẳng hạn:

- Java source code được sinh ra.
- Bytecode, ví dụ cho một số proxy.
- RuntimeHints cho reflection, resource loading, serialization và JDK proxy.
- Mã khôi phục các bean definitions đã được phân tích.

AOT giúp Spring giảm công việc khám phá và xử lý động lúc startup. Các quyết định liên quan đến cấu trúc bean được đưa ra sớm dựa trên classpath và Environment của lần build.

### 2.4. GraalVM native image

Native image là executable được biên dịch từ ứng dụng và các thành phần runtime cần thiết. Native image của Spring Boot sử dụng kết quả AOT làm đầu vào bắt buộc.

Khi chạy native image, ứng dụng không hoạt động như một JVM thông thường với khả năng tùy ý tải class và tạo cấu trúc bean động. Nhiều quyết định về classpath, bean definitions, reflection và điều kiện cấu hình đã được xác định trong quá trình build.

### 2.5. Project CRaC checkpoint/restore

CRaC (Coordinated Restore at Checkpoint) tạo checkpoint từ một JVM đang chạy rồi khôi phục process từ ảnh đã lưu. Sau restore, JVM tiếp tục từ ảnh checkpoint với trạng thái đã được warm-up.

CRaC vẫn là mô hình JVM. Nó khác với native image:

| Khái niệm | Thời điểm quyết định chính | Runtime |
| --- | --- | --- |
| JVM thông thường | Chủ yếu khi startup | JVM khởi tạo bean và có thể dùng Spring Cloud refresh |
| Spring AOT trên JVM | Một phần cấu trúc bean ở build time | JVM chạy mã AOT đã sinh |
| GraalVM native image | Classpath, bean graph và native compilation ở build time | Native executable |
| JVM CRaC | Trạng thái process được chụp tại checkpoint | Khôi phục JVM từ checkpoint |

CRaC có lifecycle callback trước checkpoint và sau restore. Spring Cloud có RefreshScopeLifecycle để làm mới cấu hình và bean sau restore trong trường hợp phù hợp. Đây là tính năng gắn với JVM checkpoint/restore, không phải cách bật Context Refresh trong native image.

## 3. Cơ chế RefreshScope trong ứng dụng JVM thông thường

### 3.1. RefreshScope dùng proxy và target cache

Bean có @RefreshScope thường được truy cập qua một proxy. Proxy giữ vai trò định tuyến lời gọi tới target bean hiện tại. Target được khởi tạo khi cần dùng và được lưu trong cache của scope.

Khi refresh scope bị invalidate, target hiện tại bị loại khỏi cache. Lần gọi tiếp theo qua proxy sẽ tạo target mới từ Environment và dependency hiện tại.

~~~mermaid
flowchart TD
    A[Caller] --> B[RefreshScope proxy]
    B --> C{Target đã có trong cache?}
    C -->|Có| D[Target hiện tại]
    C -->|Không| E[Tạo target mới]
    E --> F[Đọc cấu hình hiện tại]
    F --> G[Lưu target vào cache]
    G --> D
    H[Refresh event] --> I[Invalidate target cache]
    I --> C
~~~

Cơ chế này có ích với client hoặc component có thể khởi tạo lại an toàn khi cấu hình thay đổi. Nó không tự bảo đảm mọi object phụ thuộc vào bean đó đều được thay mới.

### 3.2. Ví dụ bean có refresh scope

~~~java
@Component
@RefreshScope
public class PartnerClientSettings {

    private final String baseUrl;

    public PartnerClientSettings(Environment environment) {
        this.baseUrl = environment.getProperty("partner.api.base-url");
    }

    public String baseUrl() {
        return baseUrl;
    }
}
~~~

Trong ứng dụng JVM thông thường, sau khi Environment được cập nhật và refresh scope được làm mới, target bean có thể được tạo lại và đọc giá trị mới.

Ví dụ này chỉ minh họa cơ chế. HTTP client hoặc connection pool đã được tạo từ cấu hình cũ có thể cần lifecycle riêng để đóng và tạo lại an toàn.

### 3.3. RefreshScope không thay thế restart process

Refresh scope làm mới một số target bean trong context. Nó không:

- Thay đổi classpath đang chạy.
- Nạp dependency JAR mới.
- Thay đổi JVM arguments.
- Thay đổi heap size hoặc GC.
- Tự cập nhật mọi singleton.
- Tự khởi tạo lại mọi connection pool.
- Thay thế một deployment mới.

Các thay đổi liên quan cấu trúc ứng dụng hoặc runtime process vẫn cần build/deploy/restart phù hợp.

### 3.4. Những giới hạn khác của refresh scope

Ngay cả trong JVM thông thường, refresh scope cũng có giới hạn:

- @RefreshScope trên một lớp @Configuration không có nghĩa mọi bean được khai báo trong lớp đó tự động thuộc refresh scope.
- Bean phụ thuộc vào một bean refreshable không tự động được tạo lại, trừ khi dependency đó cũng được thiết kế phù hợp.
- Xóa hẳn một property khỏi cấu hình rồi refresh không nhất thiết làm thay đổi sự hiện diện của property như mong muốn.
- Một số loại bean, ví dụ HikariDataSource, mặc định nằm trong nhóm không refreshable.
- @ConfigurationProperties dùng constructor binding, bao gồm Java record, không thể được refresh theo cách rebinding thông thường.

Khi thiết kế ứng dụng JVM, cần kiểm tra lifecycle của từng dependency thay vì mặc định mọi bean đều thay đổi cùng lúc.

## 4. AOT tạo ra bean graph ổn định như thế nào?

### 4.1. AOT phân tích ApplicationContext ở build time

Spring AOT tạo một context phục vụ việc phân tích. Quá trình này xử lý configuration class, component scan, import selector và các điều kiện để xác định bean definitions.

Trong AOT processing, Spring không thực hiện toàn bộ quá trình khởi tạo bean như một lần startup thông thường. Nó chủ yếu tạo và phân tích bean definitions, sau đó sinh mã cần thiết để khôi phục trạng thái bean factory ở runtime.

~~~mermaid
flowchart TD
    A[Application classes and dependencies] --> B[Build-time Environment]
    B --> C[AOT ApplicationContext processing]
    C --> D[Evaluate configuration and conditions]
    D --> E[Collect bean definitions]
    E --> F[Generate code and RuntimeHints]
    F --> G[Compile application]
    G --> H[JVM AOT runtime or native image]
~~~

Các bean definitions phù hợp với điều kiện tại build time được đưa vào kết quả AOT. Những bean không phù hợp bị loại khỏi cấu trúc được sinh ra.

### 4.2. Classpath được cố định

AOT giả định classpath đã được xác định đầy đủ tại build time. Ứng dụng không thể tùy ý thêm một thư viện mới vào runtime rồi mong Spring quét lại classpath và tự tạo bean như một ứng dụng JVM thông thường.

Ví dụ, nếu một provider chỉ có trên classpath ở production nhưng không có khi AOT processing, bean auto-configuration của provider đó có thể không xuất hiện trong kết quả được sinh ra.

### 4.3. @Profile và profile-specific configuration

Profile ảnh hưởng bean definitions. Trong AOT, profile cần được chọn tại build time. Profile được dùng khi AOT processing sẽ được đưa vào cấu hình runtime AOT tương ứng.

Ví dụ:

~~~java
@Configuration
@Profile("production")
class ProductionConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new ProductionPaymentGateway();
    }
}
~~~

Nếu AOT processing được thực hiện với profile test, cấu hình production có thể không được đưa vào bean graph đã sinh. Chỉ đặt SPRING_PROFILES_ACTIVE=production sau khi native image đã được build không thể bổ sung bean definitions đã bị loại trong build.

Với nhiều môi trường, cần chọn một trong các chiến lược:

- Build artifact AOT riêng cho từng profile có bean graph khác nhau.
- Giữ bean graph ổn định và thay đổi các giá trị dữ liệu runtime.
- Dùng factory/strategy đã được đăng ký từ build time để chọn hành vi trong phạm vi được thiết kế.

Không dùng profile runtime để cố thay đổi cấu trúc bean đã được cố định bởi AOT.

### 4.4. @Conditional và các thuộc tính .enabled

Các điều kiện như @ConditionalOnProperty quyết định bean có được tạo hay không. AOT đánh giá các điều kiện ảnh hưởng tới bean presence tại build time.

Ví dụ:

~~~java
@Configuration
@ConditionalOnProperty(
        prefix = "feature.payment",
        name = "enabled",
        havingValue = "true"
)
class PaymentConfiguration {

    @Bean
    PaymentProcessor paymentProcessor() {
        return new PaymentProcessor();
    }
}
~~~

Nếu feature.payment.enabled=false trong lúc AOT processing, bean PaymentProcessor không được đưa vào kết quả AOT. Đổi property thành true lúc runtime không tự tạo lại bean definition bị thiếu.

Điều này đặc biệt quan trọng khi một hệ thống định dùng Config Server để bật/tắt các integration bằng .enabled sau khi native image đã chạy.

### 4.5. RuntimeHints không làm bean graph trở nên động

RuntimeHints cung cấp thông tin cho native runtime về reflection, resource, serialization và proxy cần thiết. Hints giúp native image truy cập những thành phần đã được dự kiến, nhưng không biến một bean definition bị loại ở build time thành bean có thể tự xuất hiện ở runtime.

Không nhầm việc bổ sung reflection hint với việc hỗ trợ tạo bean động hoặc refresh toàn bộ ApplicationContext.

## 5. Vì sao Spring Cloud Context Refresh không được hỗ trợ?

### 5.1. Runtime refresh cần thay đổi trạng thái bean

Spring Cloud Context Refresh có thể cập nhật Environment, rebind một số configuration properties và invalidate target cache của RefreshScope. Khi target được gọi lần tiếp theo, nó được tạo lại theo cấu hình mới.

Đây là một hành vi runtime có tính động. Một số thành phần được khởi tạo lại và dependency của chúng có thể được resolve lại từ container.

### 5.2. AOT dựa trên quyết định đã được tạo ở build time

AOT đã xác định cấu trúc bean dựa trên classpath và Environment tại build time. Các điều kiện quyết định bean presence cũng đã được đánh giá.

Một cơ chế runtime cố làm mới cấu trúc context hoặc tạo lại các thành phần theo quyết định mới có thể vượt khỏi những gì AOT đã phân tích và sinh mã hỗ trợ.

Tài liệu Spring Cloud Commons xác định rõ **Context Refresh không được hỗ trợ cho Spring AOT transformations và native images**. Đây là giới hạn hỗ trợ của tính năng, không phải chỉ là một cảnh báo hiệu năng.

### 5.3. Tắt refresh autoconfiguration

Đối với ứng dụng AOT hoặc native image, đặt:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

Thuộc tính spring.cloud.refresh.enabled điều khiển auto-configuration của refresh scope và các tính năng liên quan. Giá trị mặc định trong ứng dụng Spring Cloud thông thường là true; với AOT/native image, phải đặt false.

### 5.4. Phải đặt property khi AOT processing diễn ra

Đây là điểm quan trọng: không đợi tới khi native executable đã chạy rồi mới truyền:

~~~bash
SPRING_CLOUD_REFRESH_ENABLED=false
~~~

Nếu AOT processing đã đánh giá điều kiện với giá trị khác, mã sinh ra có thể phản ánh cấu trúc bean không phù hợp. Hãy bảo đảm property có giá trị false trong Environment được dùng khi build AOT và giữ cùng quyết định đó khi chạy.

Ví dụ cấu hình dùng chung cho biến thể AOT/native:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

Nếu dùng profile riêng cho biến thể AOT, profile đó phải được active trong cả quá trình AOT processing và runtime. Cần kiểm tra cấu hình build thực tế của Maven/Gradle plugin để chắc chắn property được nạp ở đúng giai đoạn.

### 5.5. Không bật lại refresh bằng runtime override

Sau khi build với refresh disabled, không nên cố bật lại bằng:

~~~bash
SPRING_CLOUD_REFRESH_ENABLED=true
~~~

Việc đổi property runtime không thể làm cho tính năng vốn không được hỗ trợ trở nên an toàn. Cũng không nên expose /actuator/refresh với kỳ vọng endpoint này sẽ hoạt động trong native image.

### 5.6. Rà soát bean còn mang @RefreshScope

Khi tắt refresh auto-configuration, cần rà soát những class vẫn được annotate @RefreshScope.

Không giả định annotation sẽ biến thành singleton bình thường khi scope đã bị tắt. Nếu bean vẫn khai báo scope refresh nhưng scope đó không được đăng ký, context có thể không khởi động được.

Với biến thể AOT/native:

1. Xác định bean nào đang dùng @RefreshScope.
2. Loại bỏ annotation nếu bean không cần refresh.
3. Nếu có cấu hình riêng theo biến thể, dùng cấu hình/bean definitions phù hợp ngay từ build time.
4. Kiểm tra không còn dependency yêu cầu refresh scope.
5. Chạy AOT processing và startup test để phát hiện lỗi scope sớm.

Không chỉ đặt spring.cloud.refresh.enabled=false rồi bỏ qua các bean đã dùng refresh scope.

## 6. Cấu hình theo từng kiểu triển khai

### 6.1. JVM thông thường

Ứng dụng JVM không AOT có thể dùng refresh scope nếu có nhu cầu:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: true
~~~

Có thể expose /actuator/refresh nếu ứng dụng thật sự cần và đã bảo vệ endpoint.

### 6.2. JVM chạy mã AOT

Spring Boot cho phép chạy AOT-generated initialization code trên JVM bằng spring.aot.enabled=true, nếu artifact đã chứa mã AOT.

~~~bash
java -Dspring.aot.enabled=true -jar orders-service.jar
~~~

Đây vẫn là JVM, nhưng các giới hạn về cấu trúc bean và điều kiện được quyết định tại build time vẫn áp dụng. Vì vậy, không dùng Spring Cloud Context Refresh như một cơ chế thay đổi bean graph trong trường hợp này.

### 6.3. GraalVM native image

Native image bắt buộc dùng AOT. Cấu hình cần có:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

Ứng dụng có thể nạp cấu hình ban đầu khi startup, nhưng không dùng Spring Cloud Context để refresh scope trong lúc chạy.

### 6.4. Bảng quyết định

| Mô hình | spring.cloud.refresh.enabled | Context Refresh |
| --- | --- | --- |
| JVM thông thường, không AOT | Có thể true | Được hỗ trợ theo cấu hình |
| JVM chạy AOT-generated code | false | Không được hỗ trợ |
| GraalVM native image | false | Không được hỗ trợ |
| JVM có CRaC checkpoint/restore | Tùy thiết kế và compatibility | Có thể dùng refresh-on-restart theo lifecycle |
| Native image và CRaC | Không coi là cùng mô hình | Không dùng CRaC lifecycle như thay thế native refresh |

## 7. Config Client trong AOT và native image

### 7.1. Config Client vẫn có thể lấy cấu hình

Spring Cloud Config Client hỗ trợ Spring AOT transformations và GraalVM native images từ phiên bản 4.0.0. Vì vậy, việc tắt refresh scope không có nghĩa phải bỏ Spring Cloud Config.

Một ứng dụng có thể sử dụng:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: configserver:https://config.internal
  cloud:
    refresh:
      enabled: false
~~~

Khi startup, Config Client có thể lấy cấu hình từ Config Server và đưa vào Environment trước khi các bean được khởi tạo.

### 7.2. Config Data source phải sẵn sàng trong build

Khi build ứng dụng có Config Client và AOT processing, tài liệu Spring Cloud Config yêu cầu nguồn Config Data mà client kết nối phải có thể truy cập trong quá trình build.

Ví dụ, nếu client lấy cấu hình từ Config Server, server cần chạy và truy cập được theo URL đã cấu hình khi AOT processing diễn ra.

Nguồn có thể là:

- Spring Cloud Config Server.
- Consul.
- ZooKeeper.
- Vault.
- Một nguồn Config Data khác được hỗ trợ.

Đây là điều kiện build-time cho AOT. Không nên chạy build trên máy không có kết nối tới nguồn cấu hình rồi giả định kết quả sẽ tương đương môi trường build có Config Server.

### 7.3. Giá trị ảnh hưởng bean creation cần nhất quán

Các property ảnh hưởng tới việc tạo bean, chẳng hạn:

- @Profile.
- @ConditionalOnProperty.
- Provider enablement.
- Loại integration được auto-configure.
- Bootstrap/configuration flags.

cần có giá trị phù hợp ở build time và runtime. Nếu chúng khác nhau, bean graph đã sinh có thể không tương ứng với cấu hình runtime.

Ví dụ, nếu AOT build với feature.payment.enabled=false, nhưng runtime Config Server trả true, không thể kỳ vọng bean payment tự xuất hiện.

### 7.4. Legacy config-first bootstrap

Tài liệu Spring Cloud Config nêu rõ AOT/native image support không có cho config-first bootstrap legacy khi đặt:

~~~properties
spring.config.use-legacy-processing=true
~~~

Với ứng dụng cần AOT/native, ưu tiên Config Data import:

~~~yaml
spring:
  config:
    import: configserver:
~~~

Kiểm tra đúng phiên bản Spring Cloud Config và cách bootstrap của dự án. Không trộn legacy bootstrap với Config Data mode trong cùng một giả định về lifecycle.

### 7.5. Native startup vẫn cần kết nối nguồn cấu hình

Native executable có thể khởi động nhanh, nhưng nếu Config Client phải gọi Config Server hoặc Vault lúc startup, thời gian mạng vẫn được tính vào startup time.

AOT không loại bỏ chi phí truy cập nguồn cấu hình từ xa. Cần đặt timeout, retry và chính sách fail-fast phù hợp với yêu cầu của ứng dụng.

### 7.6. Không nhầm Config Server với Config Client

Khả năng AOT/native của Config Client và Config Server được tài liệu mô tả riêng:

- Config Client hỗ trợ AOT/native từ 4.0.0, với các điều kiện đã nêu.
- Config Server hỗ trợ AOT transformations từ 4.0.0 và native image từ 4.1.0 với GraalVM 21 trở lên, đồng thời cần một số workaround theo tài liệu phiên bản.

Việc Config Server có thể chạy native không làm thay đổi giới hạn của Spring Cloud Context Refresh ở client hoặc server có refresh scope.

## 8. Thay thế Context Refresh trong native image

Khi không thể refresh ApplicationContext, cần chọn chiến lược cập nhật cấu hình phù hợp với loại thay đổi.

### 8.1. Rolling restart khi cấu hình thay đổi

Đây là phương án dễ vận hành và dễ kiểm chứng nhất khi thay đổi ảnh hưởng bean creation hoặc resource lifecycle.

Quy trình:

1. Cập nhật cấu hình ở nguồn có version.
2. Kiểm tra cấu hình trước khi deploy.
3. Tạo deployment revision mới hoặc kích hoạt rollout.
4. Khởi động instance mới với cấu hình hiện tại.
5. Chờ readiness và health đạt yêu cầu.
6. Chuyển traffic sang instance mới.
7. Drain và dừng instance cũ.
8. Theo dõi lỗi sau rollout.
9. Rollback về revision đã kiểm thử nếu cần.

~~~mermaid
flowchart TD
    A[Config revision changes] --> B[Validate configuration]
    B --> C[Start new instance]
    C --> D[Load config at startup]
    D --> E[Readiness checks]
    E --> F{Healthy?}
    F -->|No| G[Stop new instance and rollback]
    F -->|Yes| H[Shift traffic]
    H --> I[Drain old instance]
    I --> J[Stop old instance]
~~~

Rolling restart tạo instance mới với bean graph và cấu hình được khởi tạo nhất quán. Cách này phù hợp với native image vì không cần thay đổi bean definitions bên trong process hiện tại.

### 8.2. Dùng version hoặc revision của cấu hình

Mỗi lần deploy nên ghi nhận:

- Native image digest.
- Config label hoặc commit.
- Profile.
- Version secret hoặc credential reference.
- Thời điểm khởi động.
- Kết quả readiness.

Khi rollback, khôi phục bộ phiên bản tương thích đã được kiểm thử. Không chỉ thay một file cấu hình trong khi giữ một binary đã được AOT với điều kiện khác.

### 8.3. Đưa dữ liệu thay đổi thường xuyên ra khỏi bean graph

Một số giá trị không cần làm thay đổi cấu trúc bean. Có thể mô hình hóa chúng như dữ liệu runtime:

- Feature flag.
- Danh sách tenant.
- Bảng routing.
- Ngưỡng nghiệp vụ.
- Danh sách đối tác được bật.
- Quy tắc hiển thị.

Một service có thể đọc dữ liệu này từ database, remote API hoặc một dynamic configuration client. Nếu cần cập nhật tức thời, thiết kế một thành phần chuyên trách đọc dữ liệu và publish snapshot mới.

### 8.4. Dùng snapshot bất biến và atomic swap

Ví dụ một service tự quản lý policy snapshot:

~~~java
@Component
public class RuntimePolicyProvider {

    private final AtomicReference<RuntimePolicy> current =
            new AtomicReference<>(RuntimePolicy.defaults());

    public RuntimePolicy current() {
        return current.get();
    }

    public void replace(RuntimePolicy next) {
        current.set(Objects.requireNonNull(next));
    }
}
~~~

Một thành phần khác có thể lấy policy mới từ nguồn dữ liệu, validate và gọi replace(...). Request đang xử lý đọc snapshot cũ hoặc mới một cách nhất quán.

Đây là thiết kế dữ liệu runtime của ứng dụng, không phải Spring Cloud Context Refresh. Nó không tạo bean mới, không thay đổi @Conditional và không sửa cấu trúc ApplicationContext.

### 8.5. Cập nhật client hoặc resource một cách tường minh

Nếu một thay đổi cần tạo lại HTTP client hoặc connection pool, có thể thiết kế factory quản lý phiên bản resource:

1. Đọc cấu hình mới.
2. Validate URL, credential và timeout.
3. Tạo client/pool mới.
4. Kiểm tra kết nối.
5. Thay reference đang dùng bằng client mới.
6. Drain request đang sử dụng client cũ.
7. Đóng client cũ.

Cách này cần quản lý concurrency, resource disposal, timeout và lỗi khởi tạo. Không phải mọi thư viện đều hỗ trợ thay resource an toàn.

### 8.6. Feature flag service

Nếu cần bật/tắt tính năng nhanh, dùng feature flag service hoặc một runtime policy component. Feature flag nên điều khiển hành vi nghiệp vụ trong bean graph đã tồn tại.

Không dùng một property runtime để bật một auto-configuration bean đã bị loại trong AOT. Tất cả implementation cần thiết phải có trong cấu trúc được build sẵn.

## 9. CRaC checkpoint/restore và RefreshScopeLifecycle

### 9.1. CRaC là checkpoint của JVM đang chạy

CRaC cho phép chụp trạng thái JVM tại một thời điểm, lưu ảnh checkpoint và khôi phục process từ ảnh đó. Nó có thể giảm thời gian startup và giữ lại trạng thái đã warm-up.

Checkpoint/restore không phải native image. Process được khôi phục vẫn là JVM với class, heap và trạng thái runtime đã được chụp.

### 9.2. Spring Cloud làm mới cấu hình sau restore

Spring Cloud Context cung cấp RefreshScopeLifecycle để kích hoạt Context Refresh khi ứng dụng được restart sau JVM checkpoint/restore.

Hành vi này có thể:

- Rebind các bean ConfigurationProperties.
- Refresh các bean @RefreshScope.
- Làm mới target cache để target mới được khởi tạo từ cấu hình hiện tại.

Thuộc tính điều khiển:

~~~properties
spring.cloud.refresh.on-restart.enabled=true
~~~

Theo configuration properties hiện hành, giá trị mặc định là true. Có thể tắt:

~~~properties
spring.cloud.refresh.on-restart.enabled=false
~~~

### 9.3. Đây không phải ngoại lệ cho native image

Không suy luận rằng vì CRaC có thể kích hoạt Context Refresh sau restore nên native image cũng có thể refresh. Hai mô hình có runtime khác nhau.

- CRaC: JVM được khôi phục và Spring lifecycle xử lý callback sau restore.
- Native image: executable được tạo từ AOT/native compilation; Spring Cloud Context Refresh không được hỗ trợ.

Không dùng spring.cloud.refresh.on-restart.enabled=true để thay thế yêu cầu spring.cloud.refresh.enabled=false trong native image.

### 9.4. Refresh-on-restart không phải tự động lấy mọi cấu hình mới

Sau restore, Spring Cloud có thể kích hoạt refresh lifecycle, nhưng điều đó không có nghĩa mọi nguồn cấu hình từ xa luôn được tải lại theo cách giống nhau trong mọi kiến trúc.

Cần xác minh:

- Nguồn cấu hình có thể truy cập sau restore không?
- Environment có được cập nhật theo cơ chế triển khai không?
- Property source nào được giữ lại?
- Credential hoặc token có còn hợp lệ không?
- Bean có thể khởi tạo lại an toàn không?
- Kết nối mạng, socket và file handle đã được xử lý đúng trước checkpoint chưa?

CRaC yêu cầu phối hợp lifecycle của resource. Một checkpoint chứa connection cũ hoặc credential hết hạn có thể gây lỗi sau restore nếu ứng dụng không xử lý đúng.

### 9.5. Bảo vệ checkpoint image

Ảnh CRaC chứa trạng thái bộ nhớ JVM. Những giá trị mà JVM đã đọc, bao gồm property hoặc secret, có thể xuất hiện trong checkpoint files.

Do đó:

- Bảo vệ quyền đọc checkpoint files.
- Không lưu checkpoint ở artifact repository công khai.
- Áp dụng encryption at rest nếu phù hợp.
- Kiểm soát backup và retention.
- Rotate credential nếu checkpoint cũ không còn được phép sử dụng.
- Không đưa checkpoint image lên môi trường có quyền truy cập rộng hơn môi trường đã tạo nó.

## 10. Cấu hình mẫu cho ứng dụng AOT/native

### 10.1. Cấu hình refresh disabled

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    refresh:
      enabled: false
~~~

Cấu hình này cần được nạp trong AOT processing. Không chỉ truyền một biến môi trường ở thời điểm runtime sau khi image đã được tạo.

### 10.2. Tách profile build cho native variant

Nếu ứng dụng có cả JVM mode thông thường và native variant, có thể dùng profile cấu hình riêng:

application-native.yml:

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

Profile native phải được chọn trong AOT processing và runtime của native executable. Nếu profile làm thay đổi bean graph, cần kiểm tra chính xác các bean được đưa vào kết quả AOT.

Không dùng cùng một native image cho các profile có bean graph khác nhau rồi kỳ vọng runtime profile tự thêm bean đã bị loại.

### 10.3. Kiểm tra property đã được nạp

Trong môi trường build hoặc test, có thể xác nhận:

~~~java
assertThat(environment.getProperty("spring.cloud.refresh.enabled"))
        .isEqualTo("false");
~~~

Đây chỉ là kiểm tra giá trị Environment. Cần thêm kiểm thử startup AOT/native để xác nhận không còn bean hoặc dependency yêu cầu refresh scope.

### 10.4. Kiểm tra annotation còn sót

Tìm các class có:

~~~java
@RefreshScope
~~~

Đánh giá từng bean:

- Có thể bỏ refresh scope và khởi tạo một lần lúc startup không?
- Có thể chuyển cấu hình thành dữ liệu runtime không?
- Có cần thay đổi resource bằng factory riêng không?
- Có thể dùng rolling restart không?

Nếu bean thực sự cần refresh scope, native image hiện không phải deployment mode phù hợp với yêu cầu đó.

## 11. Kiểm thử theo ma trận triển khai

### 11.1. Ma trận cần xác nhận

| Mô hình test | Refresh setting | Kết quả cần xác nhận |
| --- | --- | --- |
| JVM thường | true | Refresh scope hoạt động theo cấu hình |
| JVM AOT | false | AOT startup thành công, không dựa vào Context Refresh |
| Native image | false | Native executable startup thành công |
| Native image | true | Không phải cấu hình được hỗ trợ; không dùng làm deployment |
| JVM CRaC | Theo thiết kế | Kiểm tra lifecycle sau restore và refresh-on-restart |
| Config Client AOT/native | false | Config source khả dụng khi build; client lấy config lúc startup |

### 11.2. Test startup với refresh disabled

Tạo một integration test khởi động context với:

~~~properties
spring.cloud.refresh.enabled=false
~~~

Xác nhận:

- ApplicationContext khởi động.
- Không có lỗi do scope refresh chưa đăng ký.
- Bean cần thiết được tạo theo cấu hình AOT.
- Không có code path gọi /actuator/refresh.
- ConfigurationProperties nhận giá trị startup dự kiến.

### 11.3. Test AOT trên JVM

Spring Boot có thể chạy JAR chứa AOT-generated initialization code:

~~~bash
java -Dspring.aot.enabled=true -jar orders-service.jar
~~~

Chạy smoke test cho các bean, profile và điều kiện quan trọng. Không chỉ test JVM thường rồi kết luận native image cũng hoạt động.

### 11.4. Test native image

Kiểm tra:

1. Native compilation hoàn tất.
2. Image chạy được trong runtime target.
3. Config Data cần thiết được đọc.
4. Bean graph đúng với profile build.
5. Không có dependency yêu cầu refresh scope.
6. Health/readiness đạt.
7. Các resource bên ngoài kết nối được.
8. Log không có lỗi reflection/resource hint.
9. Endpoint refresh không được coi là chức năng vận hành.
10. Thay cấu hình yêu cầu restart/rollout hoặc dynamic data path đã thiết kế.

### 11.5. Test Config Client

Với Config Client:

- Đảm bảo Config Server hoặc nguồn cấu hình test khả dụng khi AOT processing chạy.
- Dùng application name, profile và label cố định.
- Xác nhận Config Data import được xử lý.
- Xác nhận các property ảnh hưởng bean creation có giá trị nhất quán giữa build và runtime.
- Kiểm tra startup khi nguồn cấu hình không truy cập được theo chính sách optional/fail-fast.
- Xác nhận runtime native client vẫn lấy cấu hình theo cách dự kiến.

Không dùng Config Server production làm nguồn fixture cho build tự động nếu pipeline không được phép truy cập hoặc không nên phụ thuộc dữ liệu production.

### 11.6. Test CRaC riêng biệt

Với JVM có CRaC:

1. Khởi động ứng dụng trên JDK hỗ trợ CRaC.
2. Warm-up các code path cần thiết.
3. Kiểm tra resource trước checkpoint.
4. Tạo checkpoint.
5. Restore process.
6. Quan sát Spring-managed lifecycle restart.
7. Xác nhận RefreshScopeLifecycle nếu được bật.
8. Kiểm tra config, credential và kết nối sau restore.
9. Xác nhận ứng dụng phục vụ request.
10. Kiểm tra checkpoint files được bảo vệ.

Đây là test JVM checkpoint/restore, không thay thế test native image.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Native image lỗi do refresh scope | spring.cloud.refresh.enabled chưa được đặt false khi AOT processing | Đưa property vào build-time Environment |
| Runtime đặt refresh false nhưng native vẫn lỗi | AOT đã xử lý điều kiện với giá trị khác | Build lại với cấu hình đúng |
| Bean báo không có scope refresh | Bean vẫn mang @RefreshScope nhưng refresh auto-configuration đã tắt | Bỏ annotation hoặc thiết kế bean cho native variant |
| Config Server trả cấu hình mới nhưng bean không đổi | Không có Context Refresh trong native | Dùng restart/rollout hoặc dynamic data component |
| Native image thiếu một bean | @Profile hoặc @Conditional không khớp tại build time | Kiểm tra AOT profile và build-time properties |
| Đổi profile runtime không tạo bean mới | Bean graph đã được cố định ở build time | Build variant tương ứng hoặc giữ bean graph ổn định |
| Config Client AOT build không truy cập được server | Config Data source không sẵn sàng trong build | Cung cấp test/build config source khả dụng |
| Runtime config khác build config gây hành vi lạ | Property ảnh hưởng bean creation không nhất quán | Đồng bộ giá trị build/runtime |
| Dùng legacy bootstrap với AOT | spring.config.use-legacy-processing=true | Chuyển sang Config Data import theo hướng dẫn |
| /actuator/refresh không có hoặc không hoạt động | Refresh auto-configuration bị tắt hoặc endpoint không hỗ trợ | Không phụ thuộc endpoint trong AOT/native |
| CRaC restore dùng kết nối cũ | Resource chưa được phối hợp lifecycle đúng | Xử lý before-checkpoint và after-restore |
| Refresh-on-restart không chạy | spring.cloud.refresh.on-restart.enabled=false hoặc refresh lifecycle không được tạo | Kiểm tra property và Spring Cloud Context |
| Checkpoint image chứa secret | JVM đã đọc secret trước checkpoint | Bảo vệ image, hạn chế phân phối và kiểm soát retention |
| AOT build dùng nhầm profile | Profile build không trùng với dự định runtime | Xác định profile trước AOT processing và xác minh output |

## 13. Quy trình chuyển ứng dụng đang dùng RefreshScope sang native image

Giả sử orders-service đang dùng Config Server và nhiều bean @RefreshScope. Nhóm phát triển muốn chuyển ứng dụng sang native image.

### Bước 1 — Kiểm kê refresh use cases

Liệt kê:

- Các class có @RefreshScope.
- Các endpoint /actuator/refresh.
- Các event listener cho EnvironmentChangeEvent.
- Các bean ConfigurationProperties được rebind.
- Các resource được tạo từ cấu hình.
- Các integration bật/tắt bằng @ConditionalOnProperty.

Phân loại từng trường hợp thành startup-only, dynamic-data hoặc resource-recreation.

### Bước 2 — Chọn chính sách cho từng loại thay đổi

| Thay đổi | Chiến lược cho native image |
| --- | --- |
| Endpoint của service | Nạp khi startup; thay đổi bằng restart/rollout |
| Credential database | Nạp lúc startup; rollout hoặc resource replacement được thiết kế riêng |
| Feature flag | Dynamic feature service hoặc runtime policy snapshot |
| Bean provider .enabled | Quyết định tại build time |
| Log level | Dùng cơ chế logging runtime được hỗ trợ, kiểm tra riêng |
| Classpath integration | Build image mới |
| Danh sách routing | Dữ liệu runtime trong component chuyên trách |

### Bước 3 — Tắt refresh auto-configuration

~~~yaml
spring:
  cloud:
    refresh:
      enabled: false
~~~

Đảm bảo property có mặt trong AOT processing.

### Bước 4 — Loại bỏ refresh-scope dependency

Bỏ @RefreshScope ở bean không còn cần thiết. Với bean cần thay đổi dữ liệu, chuyển sang một runtime data model. Với bean cần tạo lại resource, thiết kế factory và lifecycle tường minh.

### Bước 5 — Kiểm tra Config Client

Nếu dùng Config Server, chuyển sang Config Data import nếu còn dùng legacy bootstrap. Đảm bảo Config Server hoặc nguồn cấu hình có thể truy cập trong build AOT và các property ảnh hưởng bean creation nhất quán.

### Bước 6 — Build AOT/native và kiểm thử

Chạy AOT processing, native compilation và smoke test. Xác nhận bean graph, config và resource đúng với profile dự kiến.

### Bước 7 — Đổi quy trình vận hành

Thay thao tác “refresh tất cả instance” bằng rollout có kiểm soát. Ghi nhận artifact digest, config label và secret version. Theo dõi readiness và giữ khả năng rollback.

## 14. Checklist trước khi phát hành AOT/native

### Build-time Environment

- [ ] Classpath đã cố định và đầy đủ.
- [ ] Profile được chọn trước AOT processing.
- [ ] Các thuộc tính ảnh hưởng bean presence đã có giá trị đúng.
- [ ] spring.cloud.refresh.enabled=false.
- [ ] Config Data source cần thiết truy cập được khi build.
- [ ] Config Client không dùng legacy config-first bootstrap.
- [ ] Build/runtime thống nhất các property ảnh hưởng bean creation.

### Bean graph

- [ ] Không còn bean yêu cầu @RefreshScope.
- [ ] Không còn code phụ thuộc /actuator/refresh.
- [ ] @ConditionalOnProperty được kiểm tra ở build-time config.
- [ ] Bean cần thiết đã có trong AOT output.
- [ ] RuntimeHints cho reflection/resource/proxy đã đủ.
- [ ] Resource factory có lifecycle rõ ràng.

### Runtime và vận hành

- [ ] Native executable khởi động được trong môi trường target.
- [ ] Config Client lấy cấu hình đúng lúc startup.
- [ ] Readiness kiểm tra dependency thiết yếu.
- [ ] Thay đổi cấu hình có quy trình restart/rollout.
- [ ] Artifact digest và config revision được ghi nhận.
- [ ] Rollback đã được kiểm thử.
- [ ] Log và Actuator không giả định refresh scope đang hoạt động.

### CRaC nếu có sử dụng

- [ ] Phân biệt JVM checkpoint/restore với native image.
- [ ] Kiểm tra RefreshScopeLifecycle và spring.cloud.refresh.on-restart.enabled.
- [ ] Resource được xử lý trước checkpoint và sau restore.
- [ ] Checkpoint files được bảo vệ như dữ liệu có thể chứa secret.
- [ ] Kiểm thử restore trên JDK và hệ điều hành được hỗ trợ.

## 15. Bài tập vận dụng

**Bài tập 1 — Phân biệt các loại refresh.** Mô tả sự khác nhau giữa ApplicationContext.refresh(), AOT refreshForAotProcessing và Spring Cloud /actuator/refresh. Nêu thời điểm thực hiện và mục đích của từng loại.

**Bài tập 2 — Quan sát AOT condition.** Tạo một bean có @ConditionalOnProperty. Chạy AOT processing với property true rồi false. Quan sát bean definition nào được đưa vào kết quả.

**Bài tập 3 — Tắt RefreshScope.** Tạo một ứng dụng có bean @RefreshScope. Đặt spring.cloud.refresh.enabled=false, sau đó xác định lỗi hoặc dependency còn sót khi context khởi động. Loại bỏ annotation và kiểm thử lại.

**Bài tập 4 — Config Client AOT.** Tạo Config Server test và Config Client. Chạy AOT processing khi server khả dụng. Thử thay đổi property ảnh hưởng bean creation giữa build và runtime và ghi nhận kết quả.

**Bài tập 5 — Native image startup.** Build native executable với refresh disabled. Xác nhận ứng dụng lấy được cấu hình lúc startup và không phụ thuộc /actuator/refresh.

**Bài tập 6 — Rolling restart.** Thay đổi endpoint downstream trong Config Server. Thực hiện rollout native image, xác nhận instance mới dùng cấu hình mới rồi drain instance cũ.

**Bài tập 7 — Runtime policy snapshot.** Viết một RuntimePolicyProvider dùng AtomicReference. Tạo test thay snapshot trong khi nhiều request đọc dữ liệu và xác nhận không có trạng thái cập nhật dở dang.

**Bài tập 8 — CRaC restore.** Trên JVM có CRaC, tạo checkpoint rồi restore. Quan sát lifecycle callback và RefreshScopeLifecycle. So sánh với native image và giải thích vì sao hai cơ chế không tương đương.

**Bài tập 9 — Profile build-time.** Tạo hai profile có bean definitions khác nhau. Chạy AOT với từng profile và xác nhận profile không thể tùy ý thay đổi bean graph sau khi build.

**Bài tập 10 — Kiểm tra bảo mật checkpoint.** Chạy ứng dụng có secret test, tạo checkpoint và kiểm tra quy trình lưu trữ, quyền đọc, backup và retention của checkpoint files.

## 16. Ghi nhớ và nguồn tra cứu

- Spring AOT phân tích ApplicationContext ở build time và tạo mã/hints để khôi phục bean factory.
- AOT cố định classpath và các quyết định về bean presence; @Profile và @Conditional được đánh giá theo build-time Environment.
- Spring Cloud Context Refresh không được hỗ trợ cho Spring AOT transformations và native images.
- AOT/native image cần spring.cloud.refresh.enabled=false ngay trong quá trình AOT processing.
- Không thể bật lại Context Refresh bằng runtime property sau khi đã build native image.
- Rà soát các bean còn @RefreshScope; tắt auto-configuration có thể khiến scope không được đăng ký.
- Spring Cloud Config Client hỗ trợ AOT/native từ 4.0.0, nhưng Config Data source cần khả dụng trong build và các property ảnh hưởng bean creation cần nhất quán giữa build/runtime.
- Config-first bootstrap legacy với spring.config.use-legacy-processing=true không được hỗ trợ trong AOT/native.
- Config Client vẫn có thể lấy cấu hình lúc startup; điều đó không có nghĩa có thể refresh bean graph trong lúc chạy.
- Thay đổi ảnh hưởng bean hoặc resource trong native image thường cần restart/rolling deployment.
- Dữ liệu nghiệp vụ thay đổi thường xuyên có thể được mô hình hóa thành runtime snapshot hoặc feature policy độc lập với bean graph.
- CRaC là checkpoint/restore của JVM. RefreshScopeLifecycle có thể kích hoạt refresh sau restore; đây không phải giải pháp cho native image.
- Checkpoint files có thể chứa dữ liệu nhạy cảm mà JVM đã đọc, nên phải được bảo vệ.

Nguồn chính thức để đối chiếu theo phiên bản Spring Boot/Spring Cloud của dự án:

1. [Spring Cloud Commons – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
2. [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
3. [Spring Framework – Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)
4. [Spring Boot – Ahead-of-Time Processing With the JVM](https://docs.spring.io/spring-boot/reference/packaging/aot.html)
5. [Spring Cloud Config – Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
6. [Spring Cloud Config – AOT and Native Image Support](https://docs.spring.io/spring-cloud-config/reference/server/aot-and-native-image-support.html)
7. [Spring Boot – Checkpoint and Restore With the JVM](https://docs.spring.io/spring-boot/reference/packaging/checkpoint-restore.html)
8. [Spring Framework – JVM Checkpoint Restore](https://docs.spring.io/spring-framework/reference/integration/checkpoint-restore.html)
9. [Project CRaC – Checkpoint and Restore](https://crac.org/use/checkpoint-and-restore/)
10. [Spring Cloud – Release train và tương thích Spring Boot](https://spring.io/projects/spring-cloud/)

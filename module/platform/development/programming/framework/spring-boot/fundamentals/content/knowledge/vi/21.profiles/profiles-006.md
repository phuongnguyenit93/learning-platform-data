# Biểu thức profile với AND, OR, NOT

Spring Boot sử dụng **profile** để chọn cấu hình và bean theo môi trường hoặc vai trò chạy: phát triển, kiểm thử, staging, production, local, cloud, worker, v.v. Một bean đôi khi chỉ được tạo khi nhiều profile cùng active; trường hợp khác, chỉ cần một trong số chúng active hoặc cần bảo đảm một profile không xuất hiện.

Spring Framework hỗ trợ **profile expression** với ba toán tử:

- **AND: `&`** — tất cả điều kiện thành phần phải đúng.
- **OR: `|`** — ít nhất một điều kiện thành phần phải đúng.
- **NOT: `!`** — phủ định tên profile hoặc một nhóm điều kiện.

Dấu ngoặc tròn `(...)` giúp nhóm điều kiện và đặc biệt quan trọng khi kết hợp AND với OR.

Ví dụ các biểu thức độc lập:

```java
@Profile("dev & cloud")
@Profile("dev | test")
@Profile("!prod")
@Profile("(dev | staging) & cloud")
```

Bốn dòng trên là ví dụ cú pháp, **không phải bốn annotation cần đặt cùng nhau trên một class**. Bài học sẽ phân tích ý nghĩa từng toán tử, cách xử lý nhiều active profiles, `@Profile` ở class/method, các tài liệu YAML theo profile và cách kiểm thử.

## 1. Profile là gì?

Profile là một tên logic mà Spring `Environment` biết có đang active hay không. Ví dụ:

```text
dev
test
staging
prod
local
cloud
metrics
worker
```

Ứng dụng có thể kích hoạt nhiều tên đồng thời. Cấu hình:

```properties
spring.profiles.active=dev,cloud
```

nghĩa là cả `dev` và `cloud` đều active.

Có thể thiết lập từ dòng lệnh:

```bash
java -jar app.jar --spring.profiles.active=dev,cloud
```

Hoặc biến môi trường:

```text
SPRING_PROFILES_ACTIVE=dev,cloud
```

Trong phần cấu hình cơ sở của `application.yml`:

```yaml
spring:
  profiles:
    active: dev,cloud
```

**Phân biệt hai thao tác:** `spring.profiles.active` chọn **tập tên profile**; `@Profile("dev & cloud")` đánh giá **biểu thức logic** dựa trên tập đó. Dấu phẩy của danh sách active profile không tương đương toán tử OR trong annotation.

Nên khai báo active profiles ở nguồn cấu hình khởi động hợp lệ. Spring Boot không cho phép một số property như `spring.profiles.active` trong tài liệu cấu hình đã được điều kiện hóa bằng `spring.config.activate.on-profile` hoặc trong file profile-specific để tự kích hoạt thêm profile theo cách đó.

## 2. @Profile quyết định đăng ký bean

`@Profile` thuộc Spring Framework:

```java
import org.springframework.context.annotation.Profile;
```

Spring chỉ đăng ký bean definition tương ứng khi điều kiện profile đạt. Annotation được dùng trên class component/configuration hoặc method `@Bean`.

Ví dụ trên component:

```java
@Component
@Profile("dev")
public class DevelopmentAuditService implements AuditService {

    @Override
    public void record(String message) {
        System.out.println("DEV AUDIT: " + message);
    }
}
```

Khi `dev` không active, component này không được đăng ký qua component scan.

Ví dụ trên configuration:

```java
@Configuration(proxyBeanMethods = false)
@Profile("prod")
public class ProductionConfiguration {

    @Bean
    public AuditClient auditClient() {
        return new RemoteAuditClient();
    }
}
```

Nếu `prod` không active, cấu hình trên không cung cấp bean `auditClient`.

Ví dụ trên method:

```java
@Configuration(proxyBeanMethods = false)
public class AuditConfiguration {

    @Bean
    @Profile("dev")
    public AuditClient devAuditClient() {
        return new InMemoryAuditClient();
    }

    @Bean
    @Profile("prod")
    public AuditClient prodAuditClient() {
        return new RemoteAuditClient();
    }
}
```

Mỗi method có điều kiện riêng. Cần nhớ cả `dev` và `prod` có thể cùng được kích hoạt; khi đó hai bean cùng type có thể đồng thời tồn tại và gây ambiguity nếu một injection point yêu cầu đúng một `AuditClient`.

**@Profile không chạy lại theo từng HTTP request.** Nó được đánh giá trong quá trình xây dựng application context.

## 3. Cú pháp profile expression khác SpEL và Java

Profile expression có grammar riêng, không phải SpEL hoặc biểu thức Java.

Dùng:

```java
@Profile("dev & cloud")
@Profile("dev | test")
@Profile("!prod")
```

Không dùng cú pháp Java:

```java
@Profile("dev && cloud")
@Profile("dev || test")
```

Cũng không dùng SpEL:

```java
@Profile("#{dev && cloud}")
```

Các cách trên không diễn đạt đúng cú pháp profile expression. Dạng `#{...}` dành cho SpEL trong ngữ cảnh hỗ trợ evaluation như `@Value`, không phải cách khai báo `@Profile`.

Bảng tham chiếu:

| Ý định | Expression |
|---|---|
| Chỉ dev | `dev` |
| Cả dev và cloud | `dev & cloud` |
| Dev hoặc test | `dev | test` |
| Không phải prod | `!prod` |
| Dev hoặc staging, nhưng phải là cloud | `(dev | staging) & cloud` |
| Không phải prod và không phải staging | `!prod & !staging` |
| Không thuộc nhóm prod/staging | `!(prod | staging)` |

## 4. AND: toán tử &

AND đúng khi **mọi điều kiện thành phần đều đúng**.

```java
@Component
@Profile("dev & cloud")
public class CloudDevelopmentInspector {
}
```

Bảng kết quả:

| Active profiles | dev active? | cloud active? | `dev & cloud` |
|---|---:|---:|---:|
| Không chỉ định | Không | Không | Sai |
| `dev` | Có | Không | Sai |
| `cloud` | Không | Có | Sai |
| `dev,cloud` | Có | Có | Đúng |
| `dev,cloud,test` | Có | Có | Đúng |
| `prod,cloud` | Không | Có | Sai |

AND không yêu cầu **chỉ có** hai tên trong context. Nếu `dev` và `cloud` cùng active với `test`, biểu thức `dev & cloud` vẫn đúng.

Ví dụ một cấu hình metrics chỉ áp dụng cho production trên hạ tầng cloud:

```java
@Configuration(proxyBeanMethods = false)
@Profile("prod & cloud")
public class ProductionCloudMetricsConfiguration {

    @Bean
    public MetricsExporter metricsExporter() {
        return new CloudMetricsExporter();
    }
}
```

Trước khi thêm AND, cần chắc rằng các profile biểu diễn những điều kiện thực sự độc lập; chẳng hạn `prod` mô tả môi trường và `cloud` mô tả nền tảng chạy.

## 5. OR: toán tử |

OR đúng khi **ít nhất một điều kiện thành phần đúng**.

```java
@Component
@Profile("dev | test")
public class FakePaymentGateway implements PaymentGateway {
    // Implementation dùng cho môi trường phát triển và kiểm thử.
}
```

| Active profiles | `dev | test` |
|---|---:|
| Không chỉ định | Sai |
| `dev` | Đúng |
| `test` | Đúng |
| `dev,test` | Đúng |
| `prod` | Sai |
| `prod,test` | Đúng |

Hàng cuối quan trọng: khi `prod` và `test` cùng active, OR vẫn đúng do `test` active. Spring không mặc định coi `prod` và `test` loại trừ lẫn nhau.

Nếu ý định là “dev hoặc test nhưng tuyệt đối không khi prod active”, cần viết:

```java
@Profile("(dev | test) & !prod")
```

Điều kiện này có cả một nhóm OR và điều kiện NOT rõ ràng.

## 6. NOT: toán tử !

NOT đảo kết quả đánh giá một tên profile hoặc cả nhóm.

```java
@Component
@Profile("!prod")
public class NonProductionBanner {
}
```

| Active profiles | `!prod` |
|---|---:|
| Không chỉ định | Đúng |
| `dev` | Đúng |
| `test` | Đúng |
| `staging` | Đúng |
| `prod` | Sai |
| `prod,cloud` | Sai |
| `prod,dev` | Sai |

**NOT không có nghĩa dev.** `!prod` đúng trong mọi tập active profiles không chứa `prod`, kể cả khi ứng dụng không chỉ định active profile.

So sánh:

```java
@Profile("dev")
```

chỉ match khi dev active. Còn:

```java
@Profile("!prod")
```

có phạm vi rộng hơn rất nhiều.

### 6.1. Phủ định nhóm

```java
@Profile("!(prod | staging)")
```

Đúng khi cả prod và staging đều không active. Theo luật De Morgan:

```text
!(prod | staging)  <=>  !prod & !staging

!(dev & cloud)     <=>  !dev | !cloud
```

Chọn dạng dễ đọc nhất. Để loại một số môi trường nhất định, phủ định nhóm thường rõ hơn chuỗi phủ định rải rác.

## 7. Dấu ngoặc và phép kết hợp AND/OR

Không được trộn `&` và `|` **ở cùng một biểu thức mà thiếu dấu ngoặc phân nhóm**.

Ví dụ sai:

```java
@Profile("dev & cloud | test")
```

Biểu thức trên có thể được hiểu theo hai ý định khác nhau:

```java
@Profile("(dev & cloud) | test")
```

hoặc:

```java
@Profile("dev & (cloud | test)")
```

Cả hai cách đều hợp lệ, nhưng kết quả khác nhau.

| Active profiles | `(dev & cloud) | test` | `dev & (cloud | test)` |
|---|---:|---:|
| `dev` | Sai | Sai |
| `test` | Đúng | Sai |
| `dev,test` | Đúng | Đúng |
| `dev,cloud` | Đúng | Đúng |
| `cloud,test` | Đúng | Sai |
| `prod` | Sai | Sai |

Với biểu thức đầu, chỉ cần test là đủ. Với biểu thức thứ hai, dev luôn là điều kiện bắt buộc.

Vì vậy, **khi có cả AND và OR, luôn dùng dấu ngoặc để thể hiện ý định**, thay vì giả định quy tắc ưu tiên như trong Java.

## 8. Biểu thức nhiều tầng

Có thể viết:

```java
@Profile("(dev | staging) & cloud & !maintenance")
```

Ý nghĩa:

1. `dev` **hoặc** `staging` đang active.
2. `cloud` đang active.
3. `maintenance` **không** active.

Ví dụ khác:

```java
@Profile("prod & !(maintenance | readonly)")
```

Bean chỉ áp dụng khi prod active và không có maintenance/readonly.

Nếu active profiles là `prod,maintenance`, expression thứ hai sai. Nếu active là `prod,cloud`, expression đúng.

Có thể tạo một điều kiện mâu thuẫn:

```java
@Profile("prod & !prod")
```

Không có tập active profiles nào làm điều kiện này đúng. Spring không tự ưu tiên một phần điều kiện so với phần còn lại; biểu thức logic toàn bộ quyết định kết quả.

## 9. @Profile nhận mảng: các phần tử được OR

Một đặc điểm rất quan trọng: `@Profile` có thể nhận nhiều chuỗi expression.

```java
@Profile({"dev", "test"})
```

Ý nghĩa là **dev hoặc test** active, không phải cả hai.

So sánh:

| Cú pháp | Ý nghĩa |
|---|---|
| `@Profile("dev & test")` | Cả hai active |
| `@Profile("dev | test")` | Ít nhất một active |
| `@Profile({"dev", "test"})` | Ít nhất một active |
| `@Profile({"dev & cloud", "test"})` | (dev và cloud) hoặc test |

Với nhiều expression:

```java
@Profile({
    "prod & cloud",
    "staging & cloud"
})
```

tương đương ý định:

```java
@Profile("(prod | staging) & cloud")
```

Dạng mảng phù hợp nếu muốn tách các nhánh điều kiện thành những chuỗi dễ đọc. Dạng một expression phù hợp khi các nhánh chia sẻ điều kiện chung.

### 9.1. Đừng nhầm hai dấu phân cách

`spring.profiles.active=dev,cloud` kích hoạt **cả** dev và cloud.

`@Profile({"dev", "cloud"})` lại là điều kiện **dev hoặc cloud**.

Một bên thiết lập tập active, một bên kiểm tra biểu thức. Đây là nguồn gốc nhiều lỗi sử dụng profile.

## 10. Bảng đánh giá tổng hợp

Xét các biểu thức:

- E1 = `dev & cloud`.
- E2 = `dev | staging`.
- E3 = `!prod`.
- E4 = `(dev | staging) & cloud`.
- E5 = `prod & !cloud`.

| Active profiles | E1 | E2 | E3 | E4 | E5 |
|---|---:|---:|---:|---:|---:|
| Không chỉ định | Sai | Sai | Đúng | Sai | Sai |
| `dev` | Sai | Đúng | Đúng | Sai | Sai |
| `dev,cloud` | Đúng | Đúng | Đúng | Đúng | Sai |
| `prod` | Sai | Sai | Sai | Sai | Đúng |
| `prod,cloud` | Sai | Sai | Sai | Sai | Sai |
| `staging,cloud` | Sai | Đúng | Đúng | Đúng | Sai |

Cách đánh giá:

1. Xác định tập active profiles hiệu lực.
2. Xác định mỗi tên profile trong expression là đúng hay sai.
3. Áp dụng NOT cho toán hạng tương ứng.
4. Đánh giá các nhóm trong ngoặc.
5. Áp dụng AND/OR theo cấu trúc đã khai báo.
6. Đăng ký bean nếu condition đúng **và** các điều kiện khác của bean/configuration cũng thỏa.

Bảng chỉ xác định condition profile, không khẳng định bean chắc chắn tồn tại. Component vẫn cần nằm trong phạm vi scan/import và mọi dependency phải hợp lệ.

## 11. Ví dụ đầy đủ: chọn đúng một implementation

Giả sử ứng dụng muốn dùng một gateway “remote” khi chạy production trên cloud, còn các trường hợp khác dùng gateway “local”.

Interface:

```java
package com.example.notification;

public interface NotificationGateway {
    String channel();
}
```

Configuration:

```java
package com.example.notification;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class NotificationGatewayConfiguration {

    @Bean
    @Profile("prod & cloud")
    public NotificationGateway remoteGateway() {
        return () -> "remote";
    }

    @Bean
    @Profile("!(prod & cloud)")
    public NotificationGateway localGateway() {
        return () -> "local";
    }
}
```

`NotificationGateway` là functional interface nên có thể dùng lambda như ví dụ.

Service sử dụng:

```java
package com.example.notification;

import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final NotificationGateway gateway;

    public NotificationService(NotificationGateway gateway) {
        this.gateway = gateway;
    }

    public String selectedChannel() {
        return gateway.channel();
    }
}
```

Kết quả:

| Active profiles | Bean được tạo từ configuration | Giá trị channel |
|---|---|---|
| `dev` | `localGateway` | `local` |
| `test` | `localGateway` | `local` |
| `prod` | `localGateway` | `local` |
| `cloud` | `localGateway` | `local` |
| `prod,cloud` | `remoteGateway` | `remote` |
| `prod,cloud,metrics` | `remoteGateway` | `remote` |

Hai expression `prod & cloud` và `!(prod & cloud)` là phủ định nhau. Vì vậy, đối với cặp `@Bean` này, đúng một method được áp dụng theo điều kiện profile trong mỗi lần tạo context.

Ví dụ mô phỏng chọn implementation; lambda không thực hiện gửi tin nhắn thực tế. Với gateway thật, các URL, credentials và timeout vẫn cần cấu hình/validation độc lập.

### Vì sao không nên viết hai điều kiện chồng lấp?

Ví dụ:

```java
@Bean
@Profile("prod")
NotificationGateway prodGateway() { /* ... */ }

@Bean
@Profile("cloud")
NotificationGateway cloudGateway() { /* ... */ }
```

Khi `prod,cloud` cùng active, cả hai method có thể cung cấp bean cùng type. Nếu service inject một `NotificationGateway` mà không có `@Qualifier` hoặc `@Primary` phù hợp, có thể xuất hiện `NoUniqueBeanDefinitionException`.

Để chọn một implementation, nên thiết kế condition loại trừ nhau, hoặc dùng quy tắc DI có chủ đích.

## 12. @Profile trên class và trên phương thức @Bean

Khi đặt trên configuration class:

```java
@Configuration(proxyBeanMethods = false)
@Profile("prod & cloud")
public class ProductionCloudConfiguration {

    @Bean
    public ExportClient exportClient() {
        return new CloudExportClient();
    }

    @Bean
    public ExportMonitor exportMonitor() {
        return new ExportMonitor();
    }
}
```

điều kiện áp dụng cho toàn bộ configuration. Nếu không thỏa, các bean trên không được đăng ký từ class này.

Khi đặt trên `@Bean` method:

```java
@Configuration(proxyBeanMethods = false)
public class ExportConfiguration {

    @Bean
    @Profile("prod & cloud")
    public ExportClient remoteExportClient() {
        return new CloudExportClient();
    }

    @Bean
    @Profile("dev | test")
    public ExportClient fakeExportClient() {
        return new FakeExportClient();
    }
}
```

mỗi method có condition riêng.

Nếu class và method bên trong đều có `@Profile`, thì cả hai điều kiện phải đúng:

```java
@Configuration(proxyBeanMethods = false)
@Profile("cloud")
public class CloudConfiguration {

    @Bean
    @Profile("prod")
    public CloudClient productionClient() {
        return new CloudClient();
    }
}
```

Bean `productionClient` chỉ có thể được đăng ký khi cả `cloud` và `prod` active.

Không nên tạo nhiều `@Bean` overloaded method cùng tên với các `@Profile` khác nhau để phân nhánh: việc chọn overload có các giới hạn riêng. Đặt tên factory method/bean rõ ràng sẽ dễ bảo trì hơn.

## 13. Default profile và NOT

Khi không có active profile được khai báo, Spring dùng **default profiles** để đánh giá condition. Tên mặc định thường là `default`.

Ví dụ:

```java
@Bean
@Profile("default")
public Clock defaultClock() {
    return Clock.systemUTC();
}
```

Nếu không có profile active và default profile hiệu lực là `default`, bean này có thể được đăng ký.

Khi profile `dev` được active tường minh, Spring không tự đồng thời giữ `default` như một active profile chỉ vì nó mang tên mặc định.

### Phân biệt hai điều kiện

```java
@Profile("default")
```

kiểm tra tên profile `default`.

```java
@Profile("!prod")
```

kiểm tra rằng `prod` không active.

Khi `dev` active, biểu thức `!prod` vẫn đúng, còn `default` thông thường không còn được dùng như profile fallback. Đây là hai điều kiện khác nhau.

Có thể thay default profile:

```properties
spring.profiles.default=local
```

Khi không có active profile tường minh, tên `local` có thể được dùng làm default profile hiệu lực. Khi thiết kế, hãy phân biệt “default profile” với một điều kiện phủ định rộng.

## 14. Profile expression trong application.yml

Spring Boot cũng hỗ trợ điều kiện kích hoạt một tài liệu cấu hình bằng `spring.config.activate.on-profile`.

Ví dụ hai tài liệu YAML được phân tách bằng `---`:

```yaml
app:
  report:
    storage: local
    timeout: 5s

---
spring:
  config:
    activate:
      on-profile: "prod & cloud"

app:
  report:
    storage: remote
    timeout: 30s
```

Ý nghĩa:

- Tài liệu đầu cung cấp giá trị cơ sở.
- Tài liệu sau chỉ được kích hoạt khi cả `prod` và `cloud` active.
- Các property trong tài liệu sau có thể override giá trị cơ sở theo quy tắc thứ tự config data.

Ví dụ OR:

```yaml
---
spring:
  config:
    activate:
      on-profile: "staging | prod"

app:
  diagnostics:
    include-build-info: true
```

Ví dụ kết hợp:

```yaml
---
spring:
  config:
    activate:
      on-profile: "(dev | staging) & cloud & !maintenance"

app:
  sample-data:
    enabled: true
```

Các cơ chế khác nhau:

| Cơ chế | Vai trò |
|---|---|
| `spring.profiles.active` | Chỉ định tập active profiles |
| `spring.config.activate.on-profile` | Quyết định có nạp tài liệu cấu hình hay không |
| `@Profile(...)` | Quyết định đăng ký bean/configuration |

Một config document được nạp không đồng nghĩa bean chắc chắn được tạo. Bean còn phụ thuộc component scanning, auto-configuration và các condition khác.

Trong các dòng Boot cũ, YAML từng có cách khai báo profile-specific khác. Với các dự án Spring Boot hiện đại, `spring.config.activate.on-profile` là lựa chọn phù hợp để điều kiện hóa một config document.

## 15. Kết hợp @Profile với @ConditionalOnProperty

Profile expression nói về **tập profile**, còn property condition nói về **giá trị thuộc tính cấu hình**.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@Profile("(dev | staging) & cloud")
@ConditionalOnProperty(
    prefix = "feature.report",
    name = "enabled",
    havingValue = "true"
)
public class ReportConfiguration {

    @Bean
    public ReportClient reportClient() {
        return new ReportClient();
    }
}
```

Configuration chỉ được áp dụng nếu:

1. Có dev hoặc staging.
2. Có cloud.
3. `feature.report.enabled` là true theo property condition.

Có thể hình dung:

```text
(dev | staging) & cloud
           │
           ▼
     Profile condition
           │
          AND
           │
           ▼
feature.report.enabled=true
           │
           ▼
    ReportConfiguration
```

Nếu chỉ muốn bật một tính năng độc lập với môi trường, `@ConditionalOnProperty` thường phù hợp hơn tạo thêm một profile chỉ để làm feature flag.

## 16. Khi nào nên dùng profile, khi nào nên dùng property?

| Nhu cầu | Cơ chế hợp lý |
|---|---|
| Chọn implementation theo dev/test/prod | Profile |
| Chỉ tạo bean khi prod và cloud đều active | Profile expression AND |
| Dùng fake integration trong dev hoặc test | Profile expression OR |
| Không tạo bean khi prod active | Profile expression NOT |
| Bật/tắt feature theo một flag cấu hình | `@ConditionalOnProperty` |
| Chọn provider theo giá trị `payment.provider=stripe` | Property condition hoặc typed configuration |
| Thay đổi lựa chọn ngay lúc runtime | Dynamic configuration mechanism |
| Kiểm soát quyền truy cập tài nguyên | Authentication và authorization thực sự |

**Không dùng profile như ranh giới bảo mật.** Ví dụ `@Profile("!prod")` có thể cho phép bean xuất hiện trong một deployment production bị quên tên profile `prod`. Các endpoint nguy hiểm vẫn cần bảo vệ bằng chính sách authorization độc lập với profile.

## 17. Kiểm tra biểu thức trong code bằng Environment

Nếu cần đánh giá profile expression trong code, Spring Framework cung cấp API `Profiles.of(...)` và `Environment.acceptsProfiles(...)`.

```java
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.stereotype.Component;

@Component
public class DeploymentInspector {

    private final Environment environment;

    public DeploymentInspector(Environment environment) {
        this.environment = environment;
    }

    public boolean enableCloudDiagnostics() {
        return environment.acceptsProfiles(
                Profiles.of("(dev | staging) & cloud")
        );
    }
}
```

Có thể dùng:

```java
Profiles condition = Profiles.of("dev & !prod");
boolean matches = environment.acceptsProfiles(condition);
```

Ngoài ra:

- `environment.getActiveProfiles()` trả mảng tên profile được khai báo active.
- `environment.getDefaultProfiles()` trả default profile names.
- Nếu active profile array rỗng, việc đánh giá `Profiles` vẫn có thể dựa trên default profiles hiệu lực.

Tuy nhiên, đừng lạm dụng kiểm tra profile thủ công trong nhiều method. Nếu mục tiêu là chọn một implementation cho interface, dùng `@Profile` kết hợp dependency injection thường rõ hơn.

## 18. Test biểu thức bằng @ActiveProfiles

Spring Test cung cấp `@ActiveProfiles` để kích hoạt những profile cụ thể trong test application context.

Ví dụ test gateway từ phần 11:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles({"prod", "cloud"})
class RemoteGatewayTest {

    @Autowired
    NotificationGateway gateway;

    @Test
    void selectsRemoteGateway() {
        assertEquals("remote", gateway.channel());
    }
}
```

Khi cả prod lẫn cloud active, configuration chọn `remoteGateway`.

Test khác:

```java
@SpringBootTest
@ActiveProfiles("dev")
class LocalGatewayTest {

    @Autowired
    NotificationGateway gateway;

    @Test
    void selectsLocalGateway() {
        assertEquals("local", gateway.channel());
    }
}
```

Cần đặt hai test ở các file/class riêng và bảo đảm cấu hình ứng dụng thực sự scan/import `NotificationGatewayConfiguration`.

**Khác biệt cú pháp:** `@ActiveProfiles({"prod", "cloud"})` là hai tên active. `@Profile("prod & cloud")` là expression kiểm tra cả hai. Không được coi chuỗi `"prod & cloud"` là một tên active profile.

### 18.1. Unit test logic trực tiếp với MockEnvironment

Khi chỉ muốn kiểm tra expression, không cần khởi động ứng dụng:

```java
import org.junit.jupiter.api.Test;
import org.springframework.core.env.Profiles;
import org.springframework.mock.env.MockEnvironment;

import static org.junit.jupiter.api.Assertions.*;

class ProfileExpressionTest {

    @Test
    void matchesOnlyWhenBothAreActive() {
        MockEnvironment env = new MockEnvironment();
        env.setActiveProfiles("prod", "cloud");

        assertTrue(env.acceptsProfiles(
                Profiles.of("prod & cloud")
        ));

        assertFalse(env.acceptsProfiles(
                Profiles.of("dev & cloud")
        ));
    }
}
```

Ví dụ này sử dụng Spring Test và JUnit. Test expression độc lập như vậy thuận tiện để viết ma trận các active profiles.

### 18.2. Test trường hợp nhiều profile xung đột

Nếu code có `@Profile("dev | test")`, test với `@ActiveProfiles({"prod", "test"})` vẫn có thể khiến bean match. Đây là behavior logic đúng, nhưng có thể không đúng ý định nghiệp vụ.

Hãy test cả trường hợp có nhiều profile cùng active, thay vì chỉ test từng tên đơn lẻ.

## 19. Debug khi bean không xuất hiện

Nếu bạn nghĩ một bean phải có mặt nhưng context không đăng ký nó, kiểm tra theo thứ tự:

1. **Class được scan/import chưa?** Profile đúng không giúp tạo bean nếu class không phải bean candidate.
2. **Active profile names là gì?** Xem log startup và Environment.
3. **Default profile có đang được dùng không?** Trường hợp không có active profiles dễ gây nhầm.
4. **Có nhiều profile cùng active không?** Một NOT có thể trở thành sai khi thêm tên.
5. **Expression có dấu ngoặc đúng không?** AND/OR phải được nhóm rõ.
6. **@Profile đặt trên class hay method?** Có thể đang chịu điều kiện ở nhiều cấp.
7. **Có condition khác không?** Property/classpath/bean condition cũng ảnh hưởng.
8. **Có nhiều bean cùng type không?** Có thể lỗi DI do hai nhánh OR cùng match.
9. **Config document có được kích hoạt không?** Thiếu property vì tài liệu YAML không match profile cũng có thể gây lỗi.
10. **Test profile khác deployment profile không?** Kết quả trên test không bảo đảm giống production.

### 19.1. In tên profile hiệu lực để chẩn đoán

```java
import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class ProfileDiagnosticsConfiguration {

    @Bean
    ApplicationRunner logProfiles(Environment environment) {
        return args -> {
            System.out.println(
                "Active profiles: "
                    + Arrays.toString(environment.getActiveProfiles())
            );
            System.out.println(
                "Default profiles: "
                    + Arrays.toString(environment.getDefaultProfiles())
            );
        };
    }
}
```

Đây là ví dụ dùng khi học/debug. Không in toàn bộ environment vào production logs vì có thể chứa secrets.

Có thể chạy:

```bash
java -jar app.jar --debug
```

để nhận condition evaluation report hữu ích với auto-configuration. Các điều kiện profile của application component có thể không được trình bày đầy đủ theo cùng cấu trúc auto-configuration report; khi đó dùng test và kiểm tra bean definitions trực tiếp.

Nếu sử dụng Spring Boot Actuator, `/actuator/beans` và `/actuator/conditions` cũng có thể hữu ích khi được bật và bảo vệ phù hợp.

## 20. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| `dev & cloud` không match khi chỉ bật dev | AND cần cả hai tên. | Bật cloud hoặc sửa ý định expression. |
| `@Profile({"dev","cloud"})` match khi chỉ bật dev | Mảng dùng OR. | Dùng `@Profile("dev & cloud")` cho AND. |
| `dev & cloud | test` báo lỗi | AND/OR trộn không có dấu ngoặc. | Dùng `(dev & cloud) | test` hoặc `dev & (cloud | test)`. |
| `!prod` match khi không có active profile | Prod không active nên NOT đúng. | Dùng positive expression như `dev` nếu chỉ muốn dev. |
| `dev | test` match trong prod | `test` cũng đang active. | Dùng `(dev | test) & !prod` nếu cần loại prod. |
| `@Profile("default")` không match khi bật dev | Default profile không cùng active theo cơ chế fallback mặc định. | Hiểu default profiles và chọn điều kiện đúng. |
| Bean vẫn vắng dù expression đúng | Class chưa được scan hoặc condition khác sai. | Kiểm tra registration và conditions. |
| Nhiều bean cùng type xuất hiện | Các expression chồng lấp khi nhiều profile active. | Thiết kế điều kiện loại trừ nhau, hoặc dùng `@Qualifier`/`@Primary`. |
| Thay profile lúc runtime mà bean không đổi | Profile condition được đánh giá khi xây context. | Restart context hoặc cơ chế runtime khác. |
| Dùng `&&`, `||`, `#{...}` | Nhầm profile expression với Java/SpEL. | Dùng `&`, `|`, `!`, `(...)`. |
| Kích hoạt profile từ một YAML document đã được profile hóa | Đặt `spring.profiles.active` sai ngữ cảnh config data. | Cấu hình active profiles ở nguồn startup hợp lệ. |

## 21. Thiết kế profile dễ bảo trì

### 21.1. Tách tên theo ý nghĩa

Ví dụ:

- Môi trường: `dev`, `test`, `staging`, `prod`.
- Hạ tầng: `local`, `cloud`.
- Vai trò: `worker`, `web`.
- Khả năng bổ sung: `metrics`, `tracing`.

Các nhóm tên trên chỉ là convention. Spring không tự ngăn `dev` và `prod` active cùng lúc. Nếu đó là trạng thái không hợp lệ với hệ thống, cần có validation hoặc quy định deployment.

### 21.2. Ưu tiên điều kiện dương khi có thể

`@Profile("dev | test")` thường rõ ràng và giới hạn hơn `@Profile("!prod")` nếu tính năng chỉ dành cho dev/test. Điều kiện phủ định có thể vô tình bật ở profile mới như demo/training.

### 21.3. Tránh expression dài khó đọc

Expression như:

```java
@Profile("(dev | staging) & cloud & !maintenance")
```

còn tương đối rõ. Khi có quá nhiều nhóm OR/AND lồng nhau, cân nhắc:

- Tách configuration thành class nhỏ hơn.
- Dùng property mô tả feature hoặc provider rõ ràng.
- Dùng các condition Spring Boot phù hợp.
- Viết test theo ma trận profile.
- Ghi lại chính sách deployment và bean ownership.

### 21.4. Không coi profile là biện pháp security

Đừng chỉ dựa vào `!prod` để bảo vệ endpoint quản trị, fake client có thể làm hỏng dữ liệu hoặc thao tác nguy hiểm. Profile có thể cấu hình sai; authorization, network policy và credential boundaries phải được áp dụng độc lập khi cần.

## 22. Bài tập thực hành

### Bài tập A — Kiểm tra AND

Tạo component:

```java
@Component
@Profile("dev & cloud")
public class CloudDevOnlyComponent {}
```

Chạy với các active profiles `dev`, `cloud`, `dev,cloud` và `dev,cloud,test`. Quan sát lúc nào bean xuất hiện.

### Bài tập B — OR và mảng

So sánh `@Profile("dev | test")` với `@Profile({"dev", "test"})`. Thử các tập active `dev`, `test`, `dev,test` và `prod`. Giải thích vì sao hai cách có cùng kết quả.

### Bài tập C — NOT và default

Tạo hai bean riêng, một với `@Profile("!prod")`, một với `@Profile("default")`. Thử không khai báo active profile, `dev` và `prod`. So sánh kết quả.

### Bài tập D — Dấu ngoặc

Tính kết quả của hai expression:

```text
(dev & cloud) | test
dev & (cloud | test)
```

với active profiles `dev`, `test`, `dev,test`, `cloud,test` và `dev,cloud`.

### Bài tập E — Chọn đúng một bean

Dùng interface `PaymentGateway` và hai implementations. Đặt `prod & cloud` cho remote gateway, `!(prod & cloud)` cho local gateway. Test các tập active để đảm bảo không có hai bean cùng type được tạo từ cặp cấu hình đó.

### Bài tập F — YAML theo profile

Tạo tài liệu YAML có `spring.config.activate.on-profile: "staging | prod"`. Thiết lập property `app.diagnostics.mode` khác tài liệu cơ sở. Quan sát giá trị với dev, staging và prod.

### Bài tập G — Unit test biểu thức

Dùng `MockEnvironment` với `Profiles.of("(dev | staging) & cloud")`. Test `dev,cloud`, `staging,cloud`, `prod,cloud` và `dev`.

### Bài tập H — Sửa điều kiện nhập nhằng

Một dự án có:

```java
@Profile("dev & cloud | staging")
```

Hãy giải thích vì sao phải sửa và viết hai cách phân nhóm có ý nghĩa khác nhau. Tập active chỉ có staging có làm bean được đăng ký trong từng cách hay không?

### Bài tập I — Phân tích rủi ro

Một bean nhạy cảm được đánh dấu `@Profile("!prod")`. Phân tích chuyện gì xảy ra nếu deployment production không khai báo profile `prod` và đề xuất lớp bảo vệ độc lập với profile.

## 23. Ghi nhớ

1. **AND dùng `&`**: tất cả điều kiện phải đúng.
2. **OR dùng `|`**: chỉ cần một điều kiện đúng.
3. **NOT dùng `!`**: phủ định profile hoặc một nhóm.
4. **Dấu ngoặc `(...)`** giúp nhóm expression; khi có AND và OR, cần phân nhóm rõ để tránh cú pháp không hợp lệ hoặc hiểu sai.
5. **`@Profile({"dev", "test"})` là OR**, không phải AND.
6. Có thể bật nhiều profile đồng thời; tên như dev/test/prod không tự loại trừ nhau.
7. `!prod` không đồng nghĩa `dev`, vì NOT có phạm vi rộng.
8. `default` là tên profile fallback, không phải biểu thức phủ định.
9. `@Profile` kiểm soát bean registration; `spring.config.activate.on-profile` kiểm soát việc kích hoạt config document.
10. `spring.profiles.active` xác định tập active profiles, không phải vị trí viết biểu thức chọn bean.
11. Khi cần đánh giá expression bằng code, dùng `Environment.acceptsProfiles(Profiles.of(...))`.
12. Trong test, `@ActiveProfiles({"prod", "cloud"})` kích hoạt hai profile; nhớ test cả trường hợp nhiều profile chồng lấp.
13. Profile được đánh giá lúc xây dựng context; không phải runtime feature toggle hoặc cơ chế bảo mật.
14. Với nhiều bean cùng type, nên thiết kế expression loại trừ nhau hoặc cơ chế DI tường minh.
15. Khi expression trở nên dài, hãy cân nhắc tách cấu hình hoặc dùng property condition có ý nghĩa nghiệp vụ rõ hơn.

**Tư duy cốt lõi:** trước hết xác định tập profile đang active, sau đó đánh giá `@Profile` như một biểu thức logic dựa trên tập đó. AND, OR, NOT và dấu ngoặc rõ ràng giúp Spring Boot đăng ký đúng bean cho mỗi môi trường và vai trò chạy.

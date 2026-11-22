# beans, conditions, env, configprops khi cần chẩn đoán

Khi một ứng dụng Spring Boot khởi động nhưng có hành vi không như mong đợi, bạn thường phải trả lời bốn câu hỏi: **Bean cần thiết có được tạo không? Vì sao một auto-configuration được hoặc không được kích hoạt? Giá trị cấu hình hiệu lực đến từ nguồn nào? Spring đã bind các giá trị đó thành object như thế nào?**

Spring Boot Actuator cung cấp bốn endpoint rất hữu ích cho chuỗi điều tra này:

- **`/actuator/beans`**: quan sát các Spring beans được quản lý trong application context.
- **`/actuator/conditions`**: xem kết quả đánh giá các điều kiện cấu hình, đặc biệt là auto-configuration.
- **`/actuator/env`**: xem các property sources và thông tin giá trị cấu hình trong Spring `Environment`.
- **`/actuator/configprops`**: quan sát các bean được bind bằng `@ConfigurationProperties`.

Chúng không giống nhau. Một property xuất hiện trong `env` không có nghĩa object đích đã bind đúng; một class xuất hiện trong `conditions` không có nghĩa nó đã tạo bean cụ thể; và một bean xuất hiện trong `beans` không tự giải thích vì sao nó được tạo.

Bài học này hướng dẫn cách sử dụng bốn endpoint như **một bộ công cụ chẩn đoán có thứ tự**, từ tình huống đơn giản ở máy phát triển đến sự cố trong deployment, đồng thời giải thích giới hạn và rủi ro bảo mật khi quan sát thông tin nội bộ.

## 1. Quan sát ứng dụng khác với chỉ đọc log

Startup log thường cho biết ứng dụng đã chạy, port nào được mở hoặc exception nào xảy ra. Nhưng có nhiều câu hỏi mà log mặc định không trả lời đầy đủ:

- Một service không được inject vì chưa được scan hay vì condition không match?
- Vì sao Boot không tạo `DataSource` hoặc tạo một implementation khác dự kiến?
- Profile `staging` có đang active không?
- Giá trị `app.client.timeout` trong runtime đến từ YAML hay environment variable?
- Object `ClientProperties` đã được bind thành `Duration` và boolean đúng chưa?
- Vì sao hai môi trường cùng artifact nhưng behavior khác nhau?

Một mô hình chẩn đoán hữu ích:

```text
                         Triệu chứng
                             │
                             ▼
                  Bean có tồn tại không?
                             │
                    /actuator/beans
                             │
                ┌────────────┴────────────┐
                │                         │
                ▼                         ▼
             Không có                  Có bean
                │                         │
                ▼                         ▼
     Vì sao điều kiện không      Bean/configuration có
     tạo bean tương ứng?         đúng dữ liệu runtime?
                │                         │
                ▼                         ▼
     /actuator/conditions    /actuator/env
                │                         │
                └────────────┬────────────┘
                             ▼
                /actuator/configprops
                Giá trị đã bind vào bean?
                             │
                             ▼
                 Suy luận nguyên nhân
                 cùng log và code
```

Không phải sự cố nào cũng cần xem cả bốn endpoint. Hãy chọn endpoint theo câu hỏi, rồi đối chiếu kết quả với cấu hình và code của phiên bản đang chạy.

## 2. Spring Boot Actuator là gì?

**Spring Boot Actuator** là bộ tính năng cung cấp thông tin vận hành và các endpoint quản trị, ví dụ sức khỏe ứng dụng, metrics, logging, beans, conditions và configuration.

Trong dự án Gradle, dependency thường gặp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Trong Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Dùng starter phù hợp với Spring Boot BOM/plugin và phiên bản của project.

**Có Actuator trên classpath không có nghĩa mọi endpoint tự được xuất bản qua HTTP.** Việc endpoint có tồn tại, được enabled, có exposure ra web và có quyền truy cập là những quyết định khác nhau.

Nếu ứng dụng không có web server, các endpoint có thể vẫn hỗ trợ những cách quản trị khác khi được cấu hình phù hợp, nhưng sẽ không tự có URL HTTP `/actuator/...` nếu không có hạ tầng HTTP server.

## 3. Bốn lớp điều kiện để truy cập endpoint

Để sử dụng một endpoint qua HTTP, cần hiểu các yếu tố sau:

1. **Dependency:** Actuator và các dependency cần thiết có mặt.
2. **Endpoint enabled:** endpoint có được kích hoạt trong cấu hình ứng dụng không.
3. **Web exposure:** endpoint có được đưa ra HTTP hay không.
4. **Security và network:** caller có được phép truy cập đến endpoint không.

Ví dụ: nếu `/actuator/beans` trả 404, có thể do endpoint không được expose, không được enable hoặc base path/port khác. Nếu trả 401/403, endpoint có thể tồn tại nhưng người gọi thiếu xác thực/quyền.

Nếu kết nối bị từ chối, thường nên kiểm tra server/management port, network binding hoặc ứng dụng đã khởi động hay chưa.

Không nên đồng nhất **404**, **401**, **403** và **connection refused** thành một lỗi “Actuator không hoạt động”.

## 4. Bật đúng endpoint để chẩn đoán

Trong các phiên bản Spring Boot phổ biến, chỉ một tập endpoint rất hạn chế, thường gồm `health`, được expose qua web mặc định.

Để dùng bốn endpoint trong môi trường chẩn đoán đã được bảo vệ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,beans,conditions,env,configprops
```

Hoặc `application.properties`:

```properties
management.endpoints.web.exposure.include=health,info,beans,conditions,env,configprops
```

Danh sách trên chỉ định các endpoint được xuất bản qua HTTP. Nó **không phải cấu hình bảo mật**.

Ví dụ URL khi ứng dụng chạy tại `localhost:8080`, sử dụng base path mặc định:

```text
http://localhost:8080/actuator/beans
http://localhost:8080/actuator/conditions
http://localhost:8080/actuator/env
http://localhost:8080/actuator/configprops
```

Nếu cấu hình `management.server.port` hoặc `management.endpoints.web.base-path` khác mặc định, URL cũng thay đổi.

**Cảnh báo vận hành:** không bật cả bốn endpoint công khai trên Internet chỉ để debug. Chúng có thể tiết lộ tên bean, class, cấu trúc package, property keys, nguồn cấu hình và những thông tin nội bộ khác dù các value nhạy cảm được mask. Chỉ expose tạm thời, giới hạn mạng và áp dụng authentication/authorization phù hợp.

## 5. Kiểm tra endpoint discovery

Khi HTTP Actuator discovery được bật và expose phù hợp, truy cập:

```bash
curl http://localhost:8080/actuator
```

có thể nhận về một tài liệu chứa các links đến endpoint đang được expose.

Ví dụ rút gọn mang tính minh họa:

```json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/actuator",
      "templated": false
    },
    "health": {
      "href": "http://localhost:8080/actuator/health",
      "templated": false
    },
    "beans": {
      "href": "http://localhost:8080/actuator/beans",
      "templated": false
    }
  }
}
```

Tài liệu discovery thực tế tùy version, enabled endpoints, web exposure, security và cấu hình discovery page.

Lệnh `curl` ở đây giả định môi trường local cho phép truy cập. Trong môi trường đã bảo vệ, việc nhận `401 Unauthorized` hoặc `403 Forbidden` khi chưa xác thực là behavior cần thiết chứ không phải lỗi.

Đừng dùng ví dụ local không có authentication làm mẫu triển khai production.

## 6. /actuator/beans trả lời câu hỏi gì?

Endpoint **`beans`** cung cấp thông tin về các Spring beans trong application context: tên bean, type, scope, aliases, resource và một số quan hệ dependency khi được endpoint/backend cung cấp.

Những câu hỏi phù hợp:

- `notificationService` có thực sự được đăng ký không?
- Bean thuộc implementation class nào?
- Một bean được khai báo từ cấu hình nào?
- Có nhiều beans cùng type không?
- Bean hiện diện trong context nào?
- Scope của bean là singleton, prototype hay scope khác?
- Một bean có khai báo dependency nào trong metadata được báo cáo?

Ví dụ gọi:

```bash
curl http://localhost:8080/actuator/beans
```

Một phần response **minh họa, không phải schema bắt buộc cho mọi phiên bản**:

```json
{
  "contexts": {
    "application": {
      "beans": {
        "orderService": {
          "aliases": [],
          "scope": "singleton",
          "type": "com.example.orders.OrderService",
          "resource": "class path resource [com/example/orders/OrderService.class]",
          "dependencies": ["orderRepository"]
        }
      }
    }
  }
}
```

Giá trị cụ thể như context ID, resource, type hoặc dependency list phụ thuộc ứng dụng và Spring Boot version.

**Điều endpoint chứng minh:** Spring container đã đăng ký những bean definitions/beans được report trong context tương ứng.

**Điều endpoint không tự chứng minh:** bean hoạt động đúng nghiệp vụ, transaction có hoạt động, một request chắc chắn đi qua proxy hay mọi quan hệ injection đều được thể hiện đầy đủ như đồ thị code.

## 7. Một ví dụ bean đơn giản

Giả sử có:

```java
package com.example.orders;

import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;

@Repository
public class InMemoryOrderRepository {

    public String find(String id) {
        return "order-" + id;
    }
}

@Service
public class OrderService {

    private final InMemoryOrderRepository repository;

    public OrderService(InMemoryOrderRepository repository) {
        this.repository = repository;
    }

    public String findOrder(String id) {
        return repository.find(id);
    }
}
```

Nếu hai class nằm trong phạm vi component scan, `beans` có thể chứa các tên như:

```text
inMemoryOrderRepository
orderService
```

Từ đó có thể kiểm tra type và context của từng bean.

Nếu không thấy `orderService`, các nguyên nhân thường gặp:

- Class nằm ngoài package được `@SpringBootApplication` scan.
- Không có `@Service`, `@Component`, `@Bean` hoặc cơ chế đăng ký khác.
- Bean bị loại bởi `@Profile` hoặc `@Conditional...`.
- Một configuration class chứa `@Bean` không được import/scan.
- Bạn đang đọc nhầm instance/application context.

**Lưu ý:** thông thường một dependency constructor bị thiếu làm ứng dụng khởi động thất bại. Khi ứng dụng đã startup thành công nhưng bean không thấy trong `beans`, hãy đặc biệt kiểm tra bean có thực sự được kỳ vọng đăng ký trong context đó không, thay vì mặc định rằng bean được tạo lỗi rồi âm thầm biến mất.

## 8. Beans và nhiều ApplicationContext

Một Spring Boot application có thể có nhiều context, chẳng hạn application context chính và một management context khi sử dụng management server port khác.

Vì vậy `beans` có thể tổ chức response dưới khóa:

```text
contexts
  ├── application
  │     └── beans
  └── management
        └── beans
```

Đây chỉ là sơ đồ minh họa, không phải danh sách context bắt buộc.

Nếu bean không nằm ở context bạn đang xem, hãy xác nhận:

1. URL thuộc process/instance nào.
2. Port thuộc application server hay management server.
3. Có context cha/con hoặc management child context không.
4. Bean được đăng ký ở context nào.
5. Endpoint đang báo cáo những context nào.

Nếu có hai ứng dụng khác nhau cùng tên service trong một môi trường nhiều replicas, đừng chỉ dựa vào tên bean; kiểm tra instance identity, deployment version và context ID.

## 9. Beans có giúp phát hiện proxy không?

Một bean có thể được Spring AOP proxy hóa vì `@Transactional`, `@Async`, caching hoặc custom aspect.

Trong `beans`, field `type` có thể phản ánh thông tin type theo cách endpoint/reporting backend xác định. Nó **không phải công cụ đầy đủ để chứng minh interceptor chain của bean**.

Muốn xác định một bean được inject có phải AOP proxy, có thể dùng API trong code hoặc test:

```java
import org.springframework.aop.support.AopUtils;

boolean proxy = AopUtils.isAopProxy(orderService);
boolean jdkProxy = AopUtils.isJdkDynamicProxy(orderService);
boolean classProxy = AopUtils.isCglibProxy(orderService);
```

Hoặc kiểm tra behavior qua integration test.

Hãy dùng `beans` cho câu hỏi **bean có tồn tại và loại gì**, rồi dùng AOP diagnostics khi câu hỏi là **lời gọi có đi qua proxy hay không**.

## 10. /actuator/conditions trả lời câu hỏi gì?

Endpoint **`conditions`** trình bày kết quả đánh giá điều kiện auto-configuration và các conditional configuration được framework báo cáo.

Đây là nơi rất hữu ích khi hỏi:

- Vì sao Spring Boot tạo hoặc không tạo bean mặc định?
- Tại sao một auto-configuration không match?
- Có thiếu class cần thiết trên classpath không?
- Một property condition có được thỏa không?
- Đã có bean nào làm `@ConditionalOnMissingBean` không còn match?
- Application type là Servlet, Reactive hay non-web có ảnh hưởng đến condition không?

Gọi:

```bash
curl http://localhost:8080/actuator/conditions
```

Response thường được nhóm theo application context và các phần mô tả kết quả đánh giá, chẳng hạn:

- `positiveMatches`.
- `negativeMatches`.
- `unconditionalClasses`.

Các key và cấu trúc có thể khác tùy phiên bản.

## 11. Đọc một condition report minh họa

Một đoạn response giả lập rút gọn:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "ExampleMetricsAutoConfiguration": [
          {
            "condition": "OnClassCondition",
            "message": "Required class was found"
          }
        ]
      },
      "negativeMatches": {
        "ExampleMailAutoConfiguration": {
          "notMatched": [
            {
              "condition": "OnPropertyCondition",
              "message": "Required property condition did not match"
            }
          ],
          "matched": []
        }
      },
      "unconditionalClasses": []
    }
  }
}
```

Tên configuration và message trên là **ví dụ tự đặt**, chỉ dùng để giải thích cách đọc.

Phân biệt:

- **Positive match:** các điều kiện được báo cáo đã thỏa trong ngữ cảnh đánh giá.
- **Negative match:** có ít nhất một điều kiện không thỏa; phần message có thể cho biết nguyên nhân.
- **Unconditional class:** configuration được ghi nhận không cần conditional evaluation theo cách report phân loại.

Đừng đọc positive match như một bảo đảm rằng **mọi** bean mong muốn đã được tạo hoặc hoạt động đúng. Một configuration có thể có các method `@Bean` mang condition riêng; cần đối chiếu cả `beans`.

## 12. Những condition Spring Boot thường gặp

| Annotation/condition | Kiểm tra khái quát | Tình huống chẩn đoán |
|---|---|---|
| `@ConditionalOnClass` | Class có trong classpath | Dependency starter/library thiếu |
| `@ConditionalOnMissingClass` | Class không có trong classpath | Một stack khác đã được đưa vào |
| `@ConditionalOnBean` | Có bean phù hợp | Dependency infrastructure không tồn tại |
| `@ConditionalOnMissingBean` | Không có bean phù hợp | Bean người dùng đã override default |
| `@ConditionalOnProperty` | Property thỏa điều kiện | Flag không bật hoặc giá trị khác |
| `@ConditionalOnWebApplication` | Có web application context phù hợp | Chạy NONE nhưng mong web configuration |
| `@ConditionalOnNotWebApplication` | Không phải web application | Configuration dành cho batch/CLI |
| `@ConditionalOnResource` | Resource phù hợp tồn tại | Resource không đóng vào artifact |
| `@ConditionalOnExpression` | Biểu thức theo contract condition | Expression không thỏa |
| `@Profile` | Profile expression thỏa | Bean dành cho dev/prod bị loại |

`conditions` có thể giúp quan sát nhiều condition, nhưng **không phải mọi điều kiện trên mọi bean đều luôn được hiển thị với độ chi tiết giống nhau**.

Nếu cần biết một component được loại bởi `@Profile` hay do không được scan, phải kiểm tra cả component scanning, profile hiệu lực và cấu hình source. Báo cáo auto-configuration không thay thế hoàn toàn việc đọc code.

## 13. Ví dụ @ConditionalOnProperty không match

Configuration:

```java
package com.example.orders.config;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "app.notification",
        name = "enabled",
        havingValue = "true"
    )
    public NotificationSender notificationSender() {
        return new ConsoleNotificationSender();
    }
}
```

Cấu hình runtime:

```properties
app.notification.enabled=false
```

Condition không thỏa, nên method `notificationSender` không cung cấp bean.

Cách điều tra:

1. Tìm `notificationSender` trong `beans`.
2. Nếu vắng, xác nhận `NotificationConfiguration` được nạp.
3. Xem `conditions` có thông tin về condition này không.
4. Xem `env` để biết `app.notification.enabled` hiện là gì.
5. Kiểm tra giá trị đó đến từ property source nào.
6. Đối chiếu property với yêu cầu nghiệp vụ, không vội đổi thành true.

Nếu configuration class chưa được scan/import, condition có thể thậm chí chưa có cơ hội được đánh giá như bạn kỳ vọng. Khi đó, nguyên nhân không nằm ở giá trị property.

## 14. @ConditionalOnMissingBean: vì sao bean mặc định biến mất?

Một auto-configuration thường cung cấp default bean khi ứng dụng chưa tự cung cấp implementation.

Ví dụ ý tưởng:

```java
@Configuration(proxyBeanMethods = false)
public class DefaultClockConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Nếu ứng dụng đã đăng ký một bean `Clock` khác, điều kiện `@ConditionalOnMissingBean(Clock.class)` có thể không match và bean mặc định không được tạo.

Ví dụ người dùng tự định nghĩa:

```java
@Configuration(proxyBeanMethods = false)
public class BusinessClockConfiguration {

    @Bean
    Clock businessClock() {
        return Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
    }
}
```

Khi khởi tạo context, kết quả còn tùy thứ tự xử lý configuration/bean definitions và các điều kiện khác.

Các bước điều tra:

- Trong `conditions`, tìm message về `OnBeanCondition` hoặc điều kiện missing bean.
- Trong `beans`, xác định bean `Clock` nào có mặt.
- Kiểm tra configuration nào tạo bean đó.
- Kiểm tra scope/type/qualifier khi có nhiều ứng viên.

Thông báo “did not match because bean found” thường không phải lỗi. Nó có thể cho thấy Spring Boot đã **nhường quyền cấu hình** cho bean do ứng dụng tự cung cấp.

## 15. Khi ứng dụng startup thất bại thì xem conditions thế nào?

Nếu ứng dụng không tạo được context, HTTP endpoint `/actuator/conditions` thường **không có sẵn** để truy cập. Đây là điểm hạn chế thiết thực: Actuator HTTP endpoints hữu ích nhất khi ứng dụng đã khởi động đủ để phục vụ management requests.

Trong trường hợp startup failure, có thể dùng cơ chế debug startup:

```bash
java -jar app.jar --debug
```

Hoặc Gradle:

```bash
./gradlew bootRun --args="--debug"
```

Hoặc Maven:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--debug"
```

Spring Boot có thể in **condition evaluation report** bổ sung vào log giúp chẩn đoán auto-configuration.

**Lưu ý:** `--debug` bật một số logging/debug behavior của Spring Boot, không đồng nghĩa bật TRACE cho mọi package. Đừng mặc định mọi exception sẽ có đủ nguyên nhân chỉ từ report; vẫn phải đọc stack trace và error analysis.

Không nên vô tình bật debug lâu dài trong production vì log volume và khả năng tiết lộ chi tiết nội bộ.

## 16. /actuator/env trả lời câu hỏi gì?

Endpoint **`env`** cung cấp thông tin về Spring `Environment` và những `PropertySource` cấu thành cấu hình runtime.

Các câu hỏi phù hợp:

- Profile nào đang active?
- Có bao nhiêu nguồn property đang góp phần cấu hình ứng dụng?
- Property `app.client.timeout` có xuất hiện không?
- Giá trị hiệu lực đang đến từ file, biến môi trường hay command line?
- Vì sao property trong `application.yml` bị override?
- Có property bị thiếu hoặc được đặt sai key không?

Ví dụ:

```bash
curl http://localhost:8080/actuator/env
```

Khi cần một property cụ thể, nhiều phiên bản hỗ trợ endpoint dạng:

```bash
curl http://localhost:8080/actuator/env/app.client.timeout
```

URL chính xác phụ thuộc web base path, phiên bản và security. Với property name chứa ký tự đặc biệt, cần encode path đúng.

**Quan trọng:** endpoint có thể trả các giá trị đã được mask/sanitize nhằm hạn chế lộ thông tin nhạy cảm. Nhìn thấy key không có nghĩa caller được quyền xem plaintext value.

## 17. Environment và PropertySource là gì?

Spring `Environment` là abstraction cung cấp thông tin cấu hình và profiles. Một `Environment` có thể tổng hợp nhiều `PropertySource`.

Ví dụ:

```text
Environment
    │
    ├── commandLineArgs
    │     └── app.client.timeout=2s
    │
    ├── systemEnvironment
    │     └── APP_CLIENT_TIMEOUT=5s
    │
    ├── systemProperties
    │     └── user.timezone=UTC
    │
    └── application.yml
          └── app.client.timeout=10s
```

Nếu các property sources nói trên được sắp xếp theo thứ tự ưu tiên như mô phỏng, giá trị hiệu lực của `app.client.timeout` có thể là `2s`, không phải `10s` từ YAML.

Hãy xem phần minh họa là mô hình suy luận. **Thứ tự ưu tiên thực tế của Spring Boot** có quy tắc riêng và chịu ảnh hưởng của profile, imports, command line, environment, test overrides hoặc custom property sources.

Do đó, khi điều tra cấu hình, câu hỏi đúng không chỉ là “trong file YAML ghi gì?” mà là **“Environment đang resolve property này từ nguồn nào?”**

## 18. Một ví dụ về precedence

Trong `application.yml`:

```yaml
app:
  client:
    timeout: 10s
```

Khi chạy:

```bash
java -jar app.jar --app.client.timeout=2s
```

Trong cấu hình Boot thông thường có command-line properties được bật, `2s` có độ ưu tiên cao hơn giá trị trong file YAML.

Nếu bạn cũng thiết lập environment variable phù hợp:

```text
APP_CLIENT_TIMEOUT=5s
```

thì nguồn thắng vẫn phụ thuộc vào thứ tự ưu tiên property sources; trong thiết lập Boot thông dụng, command-line property `--app.client.timeout=2s` thắng environment variable và file application.

Trường hợp ứng dụng nhận `10s` thay vì `2s` có thể do:

- Command-line properties bị vô hiệu hóa hoặc arguments không được truyền tới `SpringApplication`.
- Bạn đang gọi nhầm instance.
- Property name bị gõ sai.
- Một nguồn cấu hình được thêm vào với precedence khác dự kiến.
- Code không đọc `app.client.timeout` mà đọc key khác.

`env` giúp bạn kiểm tra nguồn và giá trị hiệu lực; đừng suy đoán từ một file đơn lẻ.

## 19. Property origin giúp chẩn đoán gì?

Một số nguồn cấu hình hỗ trợ **origin metadata** cho biết property được định nghĩa tại đâu, chẳng hạn file và dòng trong file hoặc nguồn tương đương.

Một response minh họa cho property:

```json
{
  "property": {
    "source": "Config resource 'class path resource [application.yml]'",
    "value": "******"
  },
  "activeProfiles": ["dev"]
}
```

Ví dụ chỉ minh họa ý tưởng; tên fields và cách origin được biểu diễn không phải schema chính xác bắt buộc của mọi bản Boot. Ở nhiều phiên bản, endpoint còn báo từng `propertySource` và `origin` theo cấu trúc riêng.

Điều cần đọc:

- **Key** đang truy vấn có chính xác không?
- **Source** nào đang cung cấp effective value?
- **Origin** có thể trỏ về resource/location cụ thể không?
- **Value** có được mask không?
- **Active profiles** có đúng với deployment không?

Origin rất hữu ích khi ứng dụng có `application.yml`, `application-prod.yml`, environment variables và config imports cùng tồn tại.

## 20. Đừng nhầm tên biến môi trường với property key

Spring Boot có cơ chế relaxed binding/tên tương đương cho nhiều trường hợp cấu hình.

Ví dụ canonical property:

```properties
app.client.max-retries=4
```

Một tên biến môi trường thường tương ứng là:

```text
APP_CLIENT_MAXRETRIES=4
```

Quy tắc đặt environment variable của Spring Boot cho binding thường gồm: đổi dấu chấm thành dấu gạch dưới, bỏ dấu gạch ngang và viết hoa. Vì vậy không nên tự suy ra rằng `APP_CLIENT_MAX_RETRIES` luôn tương đương cho mọi kiểu tra cứu.

Nếu thấy property trong environment của OS nhưng ứng dụng bind sai:

1. Xác nhận canonical property name.
2. Kiểm tra spelling và prefix.
3. Đối chiếu cách thư viện/property binder diễn giải tên.
4. Xem `env` có property nguồn không.
5. Xem `configprops` để biết object cuối cùng được bind như thế nào.

Với các app property mới, đặt key canonical dạng kebab-case ngay từ đầu thường dễ bảo trì hơn.

## 21. Bảo vệ giá trị cấu hình khi xem env

`env` là endpoint nhạy cảm vì có thể liệt kê tên cấu hình như:

```text
spring.datasource.url
spring.datasource.username
spring.datasource.password
external.api.token
security.oauth2.client-secret
```

Ngay cả khi giá trị bị mask, tên property có thể tiết lộ kiến trúc, các integration hoặc ứng dụng đang dùng hệ thống nào.

Trong nhiều dòng Spring Boot hiện đại, endpoint `env` có chính sách che giá trị mặc định và property:

```properties
management.endpoint.env.show-values=never
```

Có những chế độ hiển thị giá trị khi caller được ủy quyền, nhưng **không nên bật hiển thị plaintext trong môi trường dùng chung chỉ để tiện debug**. Việc endpoint được bảo vệ bằng authentication chưa chắc đủ để chia sẻ secrets cho mọi thành viên có quyền vận hành.

Một policy an toàn:

- Ưu tiên xem key, source và origin ở mức cần thiết.
- Giữ giá trị nhạy cảm được sanitize.
- Chỉ cấp quyền cho nhân sự/công cụ vận hành phù hợp.
- Không paste nguyên response `env` vào ticket/chat công khai.
- Dùng secret manager hoặc công cụ cấu hình chuyên dụng khi cần xác nhận secret, thay vì in plaintext.

## 22. /actuator/configprops trả lời câu hỏi gì?

Endpoint **`configprops`** tập trung vào các beans được bind thông qua **`@ConfigurationProperties`**.

Các câu hỏi phù hợp:

- Class property object có được đăng ký làm bean chưa?
- Prefix nào đang được dùng để bind?
- Object đích nhận giá trị gì sau khi bind?
- Giá trị nào đến từ nguồn cấu hình nào, khi origin/input metadata được hỗ trợ?
- Một giá trị số, boolean hoặc duration có được chuyển sang Java type phù hợp không?
- Vì sao property xuất hiện trong `env` nhưng object lại dùng default?

Gọi:

```bash
curl http://localhost:8080/actuator/configprops
```

Một số phiên bản hỗ trợ truy vấn theo prefix, ví dụ:

```bash
curl http://localhost:8080/actuator/configprops/app.client
```

Không nên giả định mọi bản Boot đều có cùng dạng path lọc; kiểm tra endpoint discovery và documentation của version thực tế.

`configprops` **không phải bản sao của `env`**. Nó cho biết trạng thái binding của các bean `@ConfigurationProperties`, không phải mọi property key có trong environment.

## 23. Ví dụ @ConfigurationProperties

Giả sử ứng dụng có cấu hình:

```yaml
app:
  client:
    base-url: https://example.invalid
    timeout: 5s
    max-retries: 3
    enabled: true
```

Khai báo typed properties object:

```java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI baseUrl,
        Duration timeout,
        int maxRetries,
        boolean enabled
) {
}
```

Đăng ký scanning:

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Service sử dụng:

```java
@Service
public class ClientService {

    private final ClientProperties properties;

    public ClientService(ClientProperties properties) {
        this.properties = properties;
    }

    public Duration timeout() {
        return properties.timeout();
    }
}
```

Trong thiết lập tương thích, Spring Boot bind:

- `base-url` thành `URI`.
- `timeout: 5s` thành `Duration` năm giây.
- `max-retries: 3` thành `int`.
- `enabled: true` thành `boolean`.

Giá trị `https://example.invalid` chỉ là URL dùng trong tài liệu để không vô tình gọi một dịch vụ thật.

## 24. Đọc configprops response

Một response minh họa rút gọn:

```json
{
  "contexts": {
    "application": {
      "beans": {
        "app.client-com.example.orders.config.ClientProperties": {
          "prefix": "app.client",
          "properties": {
            "baseUrl": "******",
            "timeout": "******",
            "maxRetries": "******",
            "enabled": "******"
          },
          "inputs": {
            "timeout": {
              "value": "******",
              "origin": "application.yml"
            }
          }
        }
      }
    }
  }
}
```

**Đây không phải schema/bản in bắt buộc**: bean name, names của nested fields, cách render `Duration`, cấu trúc inputs/origin và cơ chế mask khác nhau theo phiên bản Spring Boot.

Điều cần tập trung:

1. Có bean `ClientProperties` không?
2. Prefix có đúng `app.client` không?
3. Những fields cần thiết có được bind không?
4. Value có bị sanitize không?
5. Nếu có origin, input đến từ nguồn nào?
6. Giá trị runtime thực tế có khớp với typed object mà service sử dụng không?

Đừng cố suy ra giá trị plaintext từ `******`. Dấu mask là chính sách bảo vệ, không phải lỗi binding.

## 25. env và configprops khác nhau ở đâu?

Đây là phép so sánh quan trọng nhất của hai endpoint cấu hình.

| Khía cạnh | `env` | `configprops` |
|---|---|---|
| Đối tượng quan sát | `Environment` và property sources | Beans `@ConfigurationProperties` |
| Tập dữ liệu | Property keys/sources runtime | Các cấu hình đã bind thành typed objects |
| Có thể thấy key không được bean sử dụng? | Có thể | Không nhất thiết |
| Thấy prefix của properties bean? | Không phải mục tiêu chính | Có |
| Thấy binding vào Java fields? | Không trực tiếp | Có thể |
| Dò property override theo source? | Rất phù hợp | Có thể có input/origin metadata |
| Chẩn đoán conversion/default | Cần đối chiếu code/binder | Phù hợp hơn |
| Có thể chứa thông tin nhạy cảm | Có | Có |
| Chỉ áp dụng @ConfigurationProperties? | Không | Chủ yếu có |

**Ví dụ:** `env` cho thấy `app.client.timeout` có giá trị từ environment variable. Nhưng `configprops` có thể giúp xác nhận `ClientProperties.timeout` đã nhận giá trị đó dưới dạng `Duration`.

Nếu code dùng `@Value("${app.client.timeout}")` chứ không dùng `@ConfigurationProperties`, `configprops` không nhất thiết có object tương ứng. Lúc đó cần kiểm tra injection point hoặc một test/service chẩn đoán riêng.

## 26. Trường hợp env có key nhưng configprops không có bean

Giả sử `env` cho thấy:

```text
app.client.timeout=5s
```

nhưng `configprops` không có bean `ClientProperties`.

Nguyên nhân có thể:

1. Class có `@ConfigurationProperties` nhưng chưa được đăng ký qua `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties` hoặc factory method phù hợp.
2. Class nằm ngoài phạm vi scan.
3. Bean bị loại bởi `@Profile` hoặc condition.
4. Prefix sai nên đang tìm một tên không đúng.
5. Bạn đang truy cập context/instance khác.
6. Ứng dụng không dùng `@ConfigurationProperties` cho cấu hình đó.

**Property tồn tại trong Environment không làm Spring tự tạo một properties bean theo tên bất kỳ.** Spring cần biết object nào phải bind.

Nếu properties bean có mặt nhưng fields không đúng, cần kiểm tra tên fields, khả năng bind, constructor/setter, nested structure và conversion.

## 27. Trường hợp configprops có bean nhưng dữ liệu sai

Ví dụ source YAML:

```yaml
app:
  client:
    max-retries: 5
```

nhưng object quan sát trong runtime sử dụng default khác.

Các khả năng cần xem:

- Một property source khác ghi đè giá trị.
- Tên prefix hoặc field không trùng canonical property.
- Có default value trong constructor/field.
- Class dùng binding mechanism khác với kỳ vọng.
- Một custom converter đang xử lý dữ liệu.
- Object đang xem thuộc context/instance khác.
- Runtime application không chạy artifact/config file bạn vừa sửa.

**Nếu dữ liệu không convert được sang một kiểu bắt buộc**, Spring Boot thường báo lỗi binding lúc khởi tạo bean; một ứng dụng đã startup thành công không có nghĩa mọi giá trị đều đúng về nghiệp vụ, nhưng nhiều lỗi conversion nghiêm trọng đã có thể ngăn startup.

Sử dụng `env` để truy nguyên nguồn, sau đó `configprops` để xem kết quả binding. Hai góc nhìn bổ sung cho nhau.

## 28. Bind thành kiểu dữ liệu không có nghĩa giá trị hợp lệ

Ví dụ:

```yaml
app:
  client:
    max-retries: -3
    timeout: 0s
```

Các giá trị này có thể chuyển thành `int` và `Duration` hợp lệ về mặt cú pháp, nhưng không hợp lệ nếu policy nghiệp vụ yêu cầu số lần retry không âm và timeout phải dương.

Có thể thêm Bean Validation cho properties object theo cấu hình version tương thích:

```java
@ConfigurationProperties(prefix = "app.client")
@Validated
public record ClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration timeout,
        @Min(0) int maxRetries,
        boolean enabled
) {
}
```

Đây là đoạn minh họa. Cần các import validation tương ứng, Bean Validation provider/dependency và đặt constraints đúng theo yêu cầu dự án; ví dụ kiểm tra timeout dương cần constraint hoặc validator phù hợp ngoài `@NotNull`.

`configprops` giúp **quan sát** giá trị đã bind; validation giúp **ngăn** trạng thái cấu hình sai ở thời điểm khởi tạo. Hai cơ chế khác nhiệm vụ.

## 29. configprops cũng cần bảo vệ dữ liệu

Một object `@ConfigurationProperties` có thể chứa:

```java
@ConfigurationProperties(prefix = "external.payment")
public record PaymentProperties(
        URI endpoint,
        String username,
        String password,
        String apiToken
) {
}
```

Không nên mặc định rằng chỉ vì field nằm trong Java object nên an toàn để công khai.

Trong các dòng Spring Boot hiện đại, cấu hình quan trọng là:

```properties
management.endpoint.configprops.show-values=never
```

Chế độ mask mặc định và behavior có thể khác theo version; hãy xác minh trong hệ thống đang dùng.

Ngay cả khi value bị mask, response có thể tiết lộ tên integrations, prefixes, cấu trúc config hoặc runtime class names. Vẫn cần authentication, authorization và giới hạn network.

Đừng bật `show-values=always` trong production chỉ để debug. Đây có thể là cách vô tình công bố secrets cho bất kỳ người dùng nào được phép gọi endpoint.

## 30. So sánh beans, conditions, env và configprops

| Câu hỏi | Endpoint ưu tiên | Endpoint đối chiếu |
|---|---|---|
| Bean `orderService` có tồn tại? | `beans` | `conditions` nếu bean phụ thuộc condition |
| Auto-configuration không tạo bean? | `conditions` | `beans`, `env` |
| Có bean khác làm default bean bị loại? | `conditions` | `beans` |
| Profile active nào? | `env` | Startup log |
| Property đến từ file hay environment? | `env` | `configprops` |
| Object config đã bind chưa? | `configprops` | `beans` |
| Typed field nhận giá trị gì? | `configprops` | `env` |
| Property key tồn tại nhưng bean không có? | `env`, `beans` | `conditions` |
| Startup fail trước khi server chạy? | Startup log/`--debug` | Code/configuration; không trông chờ Actuator HTTP |
| Một method `@Transactional` không có hiệu lực? | Không endpoint nào đủ | Proxy diagnostics/integration test |
| Request bị 500? | Logs/traces/metrics | Chỉ xem bốn endpoint nếu nghi cấu hình/bean |

Không có endpoint nào là câu trả lời duy nhất cho mọi lỗi. Tư duy quan trọng là **đặt câu hỏi cụ thể và kết hợp đúng nguồn bằng chứng**.

## 31. Quy trình chẩn đoán 1: bean thiếu

Tình huống: ứng dụng phải có `NotificationSender` nhưng không thấy hoạt động.

**Bước 1 — Xác nhận symptom.** Ứng dụng không startup vì `NoSuchBeanDefinitionException` hay vẫn startup nhưng chức năng thông báo không chạy? Hai trường hợp cần cách chẩn đoán khác nhau.

**Bước 2 — Kiểm tra beans khi ứng dụng còn hoạt động.**

```bash
curl http://localhost:8080/actuator/beans
```

Tìm bean đúng type/name và đúng context.

**Bước 3 — Kiểm tra conditions.** Nếu bean tạo qua `@ConditionalOnProperty` hoặc auto-configuration, tìm match/non-match.

**Bước 4 — Kiểm tra env.** Xác minh property như:

```text
app.notification.enabled
```

đang có giá trị hiệu lực gì và đến từ đâu.

**Bước 5 — Kiểm tra registration.** Nếu không thấy conditional report, kiểm tra component scan, `@Configuration` import, `@Bean` definitions và active profiles.

**Bước 6 — Xác nhận bằng test hoặc restart kiểm soát.** Chỉ khi tìm nguyên nhân mới sửa cấu hình. Không bật bừa mọi property để ép bean xuất hiện.

Nếu startup fail trước khi endpoint sẵn sàng, dùng stack trace và condition report qua startup debug thay vì cố gọi HTTP.

## 32. Quy trình chẩn đoán 2: auto-configuration không match

Tình huống: bạn mong có connection pool auto-configured, nhưng ứng dụng dùng một bean khác hoặc không có datasource như dự kiến.

**Bước 1:** tìm phần liên quan trong `conditions`, chẳng hạn các kết quả của `OnClassCondition`, `OnBeanCondition` hoặc `OnPropertyCondition`.

**Bước 2:** kiểm tra dependency runtime và classpath có library cần thiết.

**Bước 3:** dùng `beans` để tìm những bean tương ứng đang tồn tại.

**Bước 4:** dùng `env` để xác nhận các key có liên quan, ví dụ datasource URL hoặc feature flags, ở mức được phép và không tiết lộ secrets.

**Bước 5:** đọc configuration source/condition semantics. Một negative match có thể là trạng thái hoàn toàn bình thường nếu Boot đã back off vì ứng dụng tự cung cấp bean.

**Bước 6:** thay đổi đúng nguyên nhân: dependency, property, cấu hình custom bean hoặc module, rồi kiểm chứng ở môi trường phù hợp.

**Không coi mọi negative match là lỗi.** Một ứng dụng bình thường thường có rất nhiều auto-configurations không match vì chúng dành cho technology stack khác.

## 33. Quy trình chẩn đoán 3: cấu hình bị override

Tình huống: trong `application.yml` có:

```yaml
app:
  client:
    timeout: 10s
```

nhưng dịch vụ quan sát timeout ngắn hơn.

**Bước 1:** dùng `env` tìm `app.client.timeout` và property source hiệu lực.

**Bước 2:** xem có command-line property `--app.client.timeout=2s` hoặc environment variable cùng ý nghĩa không.

**Bước 3:** kiểm tra active profiles, config imports và file profile-specific.

**Bước 4:** nếu code dùng `@ConfigurationProperties`, xem `configprops` để kiểm tra `Duration` cuối cùng.

**Bước 5:** nếu code dùng `@Value`, kiểm tra annotation key, default và type conversion.

**Bước 6:** so sánh giá trị hiệu lực giữa các replicas. Một pod có environment khác có thể giải thích hành vi không đồng nhất.

Mục tiêu là tìm ra **nguồn override** thay vì sửa ngay một file YAML mà runtime thực tế không sử dụng.

## 34. Quy trình chẩn đoán 4: hai instance có hành vi khác nhau

Tình huống: cùng một phiên bản ứng dụng nhưng instance A có feature còn instance B không có.

Kiểm tra trên **từng instance**, không chỉ gửi request qua load balancer chung:

1. Xác nhận mỗi instance đang chạy artifact version nào.
2. Kiểm tra active profiles trong `env`.
3. So sánh effective property keys và origins ở mức không làm lộ secret.
4. So sánh beans có mặt/không có trong `beans`.
5. So sánh condition matches liên quan trong `conditions`.
6. So sánh `configprops` cho các typed configuration beans.
7. Kiểm tra deployment rollout, config maps, environment variables, restart timing và secret references.

Khi truy cập qua load balancer, hai lần gọi `/actuator/env` có thể tới **hai replicas khác nhau**, khiến kết quả tưởng như thay đổi ngẫu nhiên. Hãy xác nhận instance identity.

Không thu thập toàn bộ cấu hình plaintext của các replicas vào một file chung để so sánh. Ưu tiên so sánh keys, flags không nhạy cảm, version và origin metadata.

## 35. Endpoint enabled khác endpoint exposed

Một endpoint có thể:

- Có mặt trên classpath.
- Được cấu hình enabled.
- Không được expose qua HTTP.
- Chỉ khả dụng qua một giao thức quản lý được hỗ trợ khác.
- Được expose nhưng bảo vệ bởi Spring Security.
- Được expose nhưng chỉ bind trên management interface/port riêng.

Tùy version, có các property điều khiển enabled state và web exposure riêng.

Ví dụ giới hạn web exposure:

```properties
management.endpoints.web.exposure.include=health,info,beans
```

Điều này không bắt buộc nghĩa `conditions` và `env` bị disable ở mọi phương thức truy cập; nó chỉ cho biết chúng không nằm trong danh sách **web exposure** được chỉ định.

Với security:

- **401:** caller chưa xác thực.
- **403:** caller xác thực nhưng không đủ quyền, hoặc access bị từ chối theo security policy.
- **404:** endpoint không nằm ở URL đang gọi, không được expose/enable hoặc path khác.
- **Connection refused:** không kết nối được tới listener, kiểm tra host/port/process.

Cần kiểm tra HTTP response và cấu hình mạng thực tế thay vì suy đoán.

## 36. Bảo vệ Actuator endpoints bằng Spring Security

Nếu ứng dụng có Spring Security, các endpoint nhạy cảm cần được áp dụng authentication và authorization rõ ràng. Khi tự định nghĩa `SecurityFilterChain`, cần nhớ cấu hình bảo mật mặc định do Boot cung cấp có thể rút lui; trách nhiệm bảo vệ cả endpoints và application URLs chuyển sang cấu hình của ứng dụng.

Một mô hình minh họa với hai filter chains:

```java
package com.example.orders.security;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorChain(HttpSecurity http)
            throws Exception {

        http.securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health"))
                .permitAll()
                .anyRequest()
                .hasRole("OPS"))
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .anyRequest()
                .authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

Đây là ví dụ về **phân quyền đường dẫn**, không phải một hệ thống xác thực hoàn chỉnh. Cần cấu hình identity provider hoặc authentication mechanism thực tế và cấp quyền `ROLE_OPS` phù hợp. Không tự tạo tài khoản admin với password tĩnh trong source chỉ để sử dụng Actuator.

Nếu management server chạy trên một port/context riêng, hãy xác nhận cách security filter chains được áp dụng trong setup đó. Với WebFlux, security API khác Servlet; không sao chép nguyên `HttpSecurity` vào reactive application.

Hạn chế network vẫn cần thiết ngay cả khi có application security. Lý tưởng nhất là management endpoints chỉ đi qua kênh quản trị đáng tin cậy.

## 37. Management port và base path

Có thể tách cổng quản trị khỏi cổng phục vụ nghiệp vụ bằng cấu hình phù hợp:

```properties
server.port=8080
management.server.port=8081
management.endpoints.web.base-path=/actuator
```

Khi đó, trong ứng dụng hỗ trợ cấu hình này, endpoint management có thể được truy cập qua cổng 8081:

```text
http://localhost:8081/actuator/beans
```

Nếu muốn giới hạn bind management listener trên loopback trong setup có **management port riêng**:

```properties
management.server.port=8081
management.server.address=127.0.0.1
```

Cấu hình này giúp hạn chế truy cập mạng từ xa trong mô hình phù hợp, nhưng không thay thế kiểm soát quyền truy cập, firewall và cách triển khai thực tế.

Nếu main server và management endpoints cùng một port, không nên giả định `management.server.address` tạo ra network binding độc lập. Việc bind địa chỉ riêng gắn với cơ chế management server context/port của từng version.

Trong container, bind loopback có thể khiến collector hoặc port-forward mechanism không truy cập được nếu thiết kế không tương thích. Cần quyết định dựa trên network topology, không copy cấu hình rập khuôn.

## 38. Thay đổi đường dẫn Actuator

Base path mặc định thường là `/actuator`, nhưng có thể được đổi:

```properties
management.endpoints.web.base-path=/manage
```

Khi đó các URL tương ứng có thể là:

```text
/manage/beans
/manage/conditions
/manage/env
/manage/configprops
```

Với management port khác, base path thường được áp dụng tương đối theo đường quản trị; với một số server/context-path configuration, URL hoàn chỉnh có thể thay đổi.

Nếu thấy 404 nhưng application vẫn chạy, kiểm tra `management.endpoints.web.base-path` trước khi quyết định endpoint chưa được bật.

Không đưa endpoint nhạy cảm vào API gateway công khai nếu không có lý do vận hành và chính sách authorization mạnh.

## 39. Thông tin nào có thể bị lộ?

| Endpoint | Thông tin có thể tiết lộ | Rủi ro |
|---|---|---|
| `beans` | Tên bean, package, class, resource, dependencies | Lộ kiến trúc nội bộ và library |
| `conditions` | Auto-configurations, classpath indicators, property conditions | Lộ công nghệ và feature flags |
| `env` | Property keys, sources, origins; values nếu chính sách cho phép | Lộ config và có nguy cơ lộ secrets |
| `configprops` | Properties classes, prefixes, field structure, bound values nếu cho phép | Lộ typed configuration/secrets |
| `health` | Thành phần health và trạng thái | Có thể lộ downstream systems nếu details quá rộng |

Một quy tắc tốt: **chỉ expose endpoint cần thiết, cho người cần thiết, trong thời gian cần thiết**.

Nếu phải chia sẻ response để điều tra:

- Redact hostnames, usernames, tokens, credentials và đường dẫn nhạy cảm.
- Không xóa những bằng chứng nguyên nhân như property key hoặc condition message, nếu có thể giữ an toàn.
- Không đưa full dump vào issue tracker công khai.
- Thiết lập expiration/retention cho dữ liệu chẩn đoán đã xuất.
- Kiểm tra những bản sao nằm trong log collector, attachment và chat.

## 40. Tại sao giá trị hiển thị là ******?

Các endpoint cấu hình có thể che giá trị theo policy của Spring Boot.

Ví dụ:

```json
{
  "name": "app.client.timeout",
  "value": "******"
}
```

Đừng kết luận:

- Property bằng chuỗi sáu dấu sao.
- Binder bị lỗi.
- App thực sự dùng default.
- Value không tồn tại.

Đây có thể chỉ là **biểu diễn đã được sanitize**.

Nếu cần xác minh giá trị không nhạy cảm, ưu tiên một test hoặc một diagnostic abstraction chỉ xuất ra dữ liệu được whitelist, chẳng hạn:

```java
@Component
public class TimeoutReporter {

    private final ClientProperties properties;

    public TimeoutReporter(ClientProperties properties) {
        this.properties = properties;
    }

    public String report() {
        return "Timeout configured: " + properties.timeout();
    }
}
```

Đoạn này chỉ phù hợp nếu timeout là thông tin được phép hiển thị. Không tạo endpoint trả toàn bộ properties object trong production để vượt qua cơ chế sanitization của Actuator.

## 41. Debug qua Actuator và debug qua log bổ sung cho nhau

Hãy chọn công cụ đúng loại sự cố.

| Công cụ | Phù hợp |
|---|---|
| Startup log | Lỗi tạo context, port, exception, startup lifecycle |
| `--debug` | Condition evaluation report khi startup |
| `beans` | Inventory Spring beans khi app đã chạy |
| `conditions` | Lý do các conditional configuration match hoặc không match |
| `env` | Property sources, active profiles, effective configuration |
| `configprops` | Typed configuration beans và binding information |
| Metrics/tracing | Latency, error rates, request path và performance |
| Heap/thread dump | Memory leak, deadlock, thread state |
| Integration tests | Chứng minh behavior trong context có kiểm soát |

Không dùng `beans` để kết luận thread bị deadlock, cũng không dùng `env` để chứng minh một HTTP request đã vào controller nào.

Nếu triệu chứng là performance hoặc data consistency, bộ công cụ quan sát có thể cần metrics, traces, database diagnostics hoặc thread dump bên cạnh bốn endpoint này.

## 42. Khi endpoint không truy cập được

Checklist chẩn đoán thực tế:

1. Ứng dụng đã startup và listening chưa?
2. Có starter Actuator trong runtime classpath không?
3. Đúng application instance/port chưa?
4. Có management port riêng không?
5. Base path có bị đổi không?
6. Endpoint có enabled và web-exposed không?
7. Có SecurityFilterChain hoặc network rule chặn không?
8. Có API gateway/proxy đang rewrite path không?
9. Có firewall, service mesh hoặc ingress policy ảnh hưởng không?
10. Nếu trả 401/403, có phải do authentication/authorization đúng thiết kế không?

Một số lỗi điển hình:

| Hiện tượng | Nguyên nhân khả dĩ | Cách xác minh |
|---|---|---|
| `/actuator/health` hoạt động, `/actuator/beans` 404 | Beans chưa được expose | Kiểm tra web exposure |
| Tất cả `/actuator` 404 | Chưa có Actuator, base path khác hoặc sai port | Kiểm tra dependency/path/management config |
| 401 khi gọi `env` | Endpoint yêu cầu xác thực | Dùng kênh và credential vận hành hợp lệ |
| 403 sau khi đăng nhập | Thiếu role hoặc authorization policy | Kiểm tra security rules |
| Connection refused ở management port | Không có listener hoặc bind khác | Kiểm tra process/port/address |
| `env` hiển thị ****** | Sanitization policy | Không coi đó là binding error |
| `configprops` không có class dự kiến | Properties bean chưa được đăng ký hoặc không dùng cơ chế binding này | Kiểm tra scan/enable/prefix |
| `conditions` có nhiều negative matches | Stack không cần những auto-configurations đó | Chỉ phân tích mục liên quan symptom |
| Kết quả khác qua load balancer | Request tới các replicas khác nhau | Kiểm tra instance identity |

## 43. Cách sử dụng ít rủi ro trong development

Một workflow tương đối an toàn:

1. Chạy app ở môi trường local hoặc development cô lập.
2. Thêm `spring-boot-starter-actuator` đúng version.
3. Expose tạm đúng `beans`, `conditions`, `env`, `configprops` cần dùng.
4. Giới hạn network và áp dụng security phù hợp.
5. Giữ chính sách che config values.
6. Dùng công cụ HTTP client để quan sát response.
7. Chỉ lưu những phần dữ liệu cần thiết cho sự cố.
8. Đối chiếu với code/configuration và chạy test nếu cần.
9. Gỡ exposure không còn cần trước khi đưa cấu hình lên production.
10. Ghi lại nguyên nhân và cách phòng ngừa thay vì giữ quyền debug quá rộng.

Không nên commit một cấu hình như:

```properties
management.endpoints.web.exposure.include=*
management.endpoint.env.show-values=always
```

vào repository dùng cho deployment chung. Dấu `*` cho web exposure và hiển thị tất cả values có thể tạo vùng lộ thông tin rất lớn; ví dụ này là **cấu hình cần tránh**, không phải bước thực hành.

## 44. Ví dụ điều tra hoàn chỉnh: feature không bật

Giả sử ứng dụng có feature gửi email.

Configuration:

```java
@Configuration(proxyBeanMethods = false)
public class MailFeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "app.mail",
        name = "enabled",
        havingValue = "true"
    )
    MailSender mailSender() {
        return new LocalMailSender();
    }
}
```

Properties:

```yaml
app:
  mail:
    enabled: false
```

Tình huống: đội phát triển tưởng mail đã bật vì trong một file cấu hình khác có `enabled: true`.

**Điều tra theo bốn endpoint:**

**1. beans**

Tìm `mailSender`. Nếu không có, xác nhận symptom: bean chưa được đăng ký. Nếu có, kiểm tra implementation và context.

**2. conditions**

Tìm `MailFeatureConfiguration` hoặc condition liên quan. Nếu report có thông tin, tìm lý do property match/non-match. Đừng mặc định report liệt kê tất cả beans do project tự viết.

**3. env**

Truy vấn `app.mail.enabled`. Kiểm tra key, value hiệu lực (nếu được phép xem) và nguồn property thắng. Có thể một environment variable hoặc command-line argument override file tưởng là đang dùng.

**4. configprops**

Nếu ứng dụng có `@ConfigurationProperties(prefix="app.mail")`, kiểm tra properties bean có được bind và nhận flag như dự kiến không. Nếu chỉ dùng `@ConditionalOnProperty`, không bắt buộc có một properties bean để `configprops` hiển thị.

**5. Kết luận có bằng chứng**

Ví dụ: “Trong instance B, `app.mail.enabled` được thiết lập false từ environment variable, nên condition không match và `mailSender` không được tạo.”

Đây là kết luận có thể kiểm chứng, tốt hơn việc phỏng đoán lỗi của Spring container.

## 45. Ví dụ điều tra hoàn chỉnh: giá trị timeout sai

Class:

```java
@ConfigurationProperties(prefix = "integration.catalog")
public record CatalogProperties(
        Duration timeout,
        int maxAttempts
) {
}
```

Cấu hình:

```yaml
integration:
  catalog:
    timeout: 10s
    max-attempts: 3
```

Một deployment dùng:

```text
INTEGRATION_CATALOG_TIMEOUT=1s
```

Điều tra:

1. `env` giúp xác minh `integration.catalog.timeout` đến từ environment và giá trị ưu tiên nếu caller được phép xem.
2. `configprops` cho biết `CatalogProperties` có được đăng ký và bind không.
3. `beans` xác nhận properties bean và service consumer tồn tại trong context.
4. `conditions` chỉ hữu ích nếu việc tạo catalog client phụ thuộc conditional configuration; không nhất thiết cần với một bean luôn được tạo.
5. Sau khi xác định source override, điều chỉnh deployment configuration theo quy trình thay đổi phù hợp.

Nếu `configprops` trả giá trị mask, không nên tắt sanitization trên public endpoint. Có thể kiểm chứng timeout bằng unit/integration test hoặc một diagnostic view đã được whitelist, trong môi trường được bảo vệ.

## 46. Bài tập thực hành

### Bài tập A — Bật Actuator

Tạo Spring Boot web app có Actuator. Expose tạm `health` và `beans` trong development. Truy cập:

```text
/actuator/health
/actuator/beans
```

So sánh dữ liệu trả về. Giải thích vì sao endpoint có trên classpath chưa chắc được expose mặc định.

### Bài tập B — Tìm bean trong context

Tạo `@Service` tên `OrderService` và `@Repository` tên `OrderRepository`. Dùng `beans` tìm tên/type/scope của chúng.

Sau đó chuyển class service ra ngoài package scan và quan sát thay đổi khi restart. Giải thích tại sao không phải cứ có file Java là có Spring bean.

### Bài tập C — Một condition không match

Tạo một `@Bean` có:

```java
@ConditionalOnProperty(
    prefix = "feature.report",
    name = "enabled",
    havingValue = "true"
)
```

Thử `feature.report.enabled=false` và `true`. So sánh `beans` với thông tin trong `conditions`, nếu condition đó được report theo setup của bạn.

### Bài tập D — Property source precedence

Đặt `app.client.timeout=10s` trong YAML, rồi truyền `--app.client.timeout=3s` từ command line. Dùng `env` truy vấn key và tìm source hiệu lực. Không cần bật lộ mọi value.

### Bài tập E — Bind properties object

Tạo `ClientProperties` có `Duration timeout` và `int maxRetries`. Đăng ký qua `@ConfigurationPropertiesScan`. Dùng `configprops` tìm bean và prefix tương ứng.

### Bài tập F — env có key nhưng không có configprops bean

Định nghĩa property `app.experimental.mode` nhưng không khai báo `@ConfigurationProperties` tương ứng. Quan sát `env` và `configprops`. Giải thích tại sao kết quả khác nhau.

### Bài tập G — Sai active profile

Tạo hai file `application-dev.yml` và `application-prod.yml` có một property không nhạy cảm khác nhau. Chạy app với profile dev/prod, đối chiếu `env`, origin và startup log.

### Bài tập H — Startup failure

Tạo một lỗi cấu hình làm context không khởi động. Thử truy cập `/actuator/conditions` và giải thích vì sao URL có thể không khả dụng. Sau đó chạy với `--debug` và đọc condition evaluation report trong log.

### Bài tập I — 401, 403 và 404

Bật Actuator và security trong môi trường test. Gọi một endpoint không expose, một endpoint expose nhưng chưa đăng nhập, và một endpoint cần role cao hơn. Phân biệt kết quả HTTP và nguyên nhân.

### Bài tập J — Multi-instance

Chạy hai instances cùng ứng dụng nhưng một instance có `feature.report.enabled=true`, instance khác là false. So sánh `beans`, `conditions` và `env` khi gọi trực tiếp từng instance. Giải thích vì sao gọi qua load balancer có thể dẫn đến kết quả thay đổi giữa các lần.

### Bài tập K — Bảo vệ dữ liệu cấu hình

Đặt một fake secret trong configuration test. Quan sát cơ chế sanitization của `env` và `configprops` trong phiên bản của bạn. Giải thích vì sao không được xuất full response ra ticket công khai hoặc bật `show-values=always` ở production.

### Bài tập L — Lập báo cáo chẩn đoán

Viết báo cáo ngắn cho tình huống “mail sender không được tạo”, với cấu trúc:

```text
Symptom:
Instance/version:
Bean presence:
Condition result:
Effective property source:
Configuration binding:
Root cause:
Proposed fix:
Evidence retained safely:
```

Chỉ ghi những dữ liệu cần thiết, không chứa credentials.

## 47. Ghi nhớ

1. **`beans`** dùng để quan sát Spring bean inventory, type, scope, resource và context.
2. **`conditions`** giúp phân tích conditional configuration, đặc biệt lý do auto-configuration match hoặc không match.
3. **`env`** giúp kiểm tra Spring Environment, active profiles, property sources, precedence và origin.
4. **`configprops`** dùng để quan sát beans `@ConfigurationProperties` và kết quả binding.
5. **Có property trong env không có nghĩa đã có properties bean; có properties bean không bảo đảm giá trị đúng yêu cầu nghiệp vụ.**
6. **Positive match** không tự chứng minh mọi bean đều tồn tại; **negative match** cũng không tự là lỗi.
7. Nếu application startup thất bại trước khi HTTP management server sẵn sàng, dùng startup log và `--debug` thay vì trông đợi `/actuator/conditions`.
8. Actuator dependency, endpoint enabled state, web exposure và security là các lớp khác nhau.
9. Web exposure không tự đồng nghĩa endpoint đã được bảo vệ. Phải kiểm soát authentication, authorization và network.
10. `env` và `configprops` có thể sanitize values; dấu `******` không phải bằng chứng property mang giá trị sáu dấu sao.
11. Hạn chế dùng `show-values=always` và tránh expose `beans`/`conditions`/`env`/`configprops` rộng trong production.
12. Khi có nhiều replicas, hãy chắc chắn đang quan sát đúng instance, version và context.
13. Trong tình huống bean thiếu, đi từ `beans` sang `conditions` và `env`; nếu liên quan typed configuration, xem thêm `configprops`.
14. Trong tình huống property sai, đi từ `env` để tìm effective source rồi đối chiếu `configprops`.
15. Property origin và bind result chỉ có ý nghĩa khi bạn hiểu đúng property name, profile và configuration class.
16. `@ConditionalOnMissingBean` có thể cố ý bỏ qua default bean vì ứng dụng đã cung cấp implementation khác.
17. Không phải mọi `@Profile`, custom condition hoặc runtime failure đều được mô tả đầy đủ trong condition report.
18. Không dùng Actuator như cách vượt qua cơ chế che secrets; chỉ giữ bằng chứng chẩn đoán cần thiết.
19. Các endpoints này bổ sung cho startup logs, metrics, traces và integration tests, không thay thế chúng.
20. Luôn chẩn đoán theo câu hỏi cụ thể, ghi lại kết luận có bằng chứng và thu hẹp exposure sau khi điều tra.

**Tư duy cốt lõi:** **`beans` cho biết *cái gì* có trong container, `conditions` giải thích *vì sao* một số cấu hình được hoặc không được chọn, `env` chỉ ra *nguồn cấu hình hiệu lực*, còn `configprops` cho biết cấu hình đã đi vào *typed bean* ra sao.** Ghép bốn góc nhìn này với startup log và code sẽ giúp chẩn đoán Spring Boot chính xác hơn mà không cần đoán mò.

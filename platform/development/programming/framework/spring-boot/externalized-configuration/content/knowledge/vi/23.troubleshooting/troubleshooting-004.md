# Dùng Actuator env để tìm nguồn thắng và configprops để xem kết quả liên kết

## 1. Mục tiêu: tách lỗi nguồn cấu hình khỏi lỗi binding

Khi một ứng dụng Spring Boot đọc cấu hình ngoài, nhiều nguồn có thể cùng khai báo một khóa. Ví dụ một nhóm phát triển chỉnh `application.yml` để đặt `shipping.retry.max-attempts=3`, nhưng tiến trình vẫn áp dụng số lần thử lại là 7. Có thể deployment đang truyền đối số dòng lệnh, một profile riêng, biến môi trường hoặc file Config Data bên ngoài. Cũng có thể `Environment` đã chọn đúng giá trị nhưng đối tượng Java không bind như dự kiến.

Spring Boot Actuator cung cấp hai góc nhìn bổ sung:

- **`env`**: cho biết `Environment` đang có những `PropertySource` nào, thứ tự ưu tiên ra sao, nguồn nào đang được chọn cho một tên thuộc tính và thông tin origin nếu có.
- **`configprops`**: cho biết những bean `@ConfigurationProperties` nào được quản lý, prefix nào được bind, trạng thái `properties` và thông tin `inputs` của quá trình binding.

Hai endpoint giúp trả lời **hai câu hỏi khác nhau**:

```text
1. Thuộc tính có hiệu lực được lấy từ đâu?
   -> GET /actuator/env/{property.name}

2. Bean cấu hình nhận kết quả liên kết ra sao?
   -> GET /actuator/configprops/{prefix}
```

Một quy trình chẩn đoán đầy đủ:

```text
YAML / properties / profile / ENV / CLI / imports
                         |
                         v
                Environment
                         |
                         +-- /actuator/env/{key}
                         |    source thắng / origin / profiles
                         |
                         v
         Binder + type conversion + validation
                         |
                         +-- /actuator/configprops/{prefix}
                         |    bean / properties / inputs
                         |
                         v
                Service dùng bean
                         |
                         v
               Kiểm tra hành vi
```

**Không nên kết luận chỉ từ một endpoint.** `env` chứng minh góc nhìn của property resolver; `configprops` chứng minh góc nhìn của bean đã được liên kết; service có thể còn xử lý giá trị bằng logic riêng.

## 2. Nắm chắc ba lớp dữ liệu

### 2.1. PropertySource là một nguồn độc lập

`PropertySource` thuộc Spring Framework. Một nguồn có tên và cung cấp giá trị cho những tên thuộc tính mà nó quản lý. Ví dụ:

```text
application.yml:
  shipping.retry.max-attempts -> 3
  shipping.retry.backoff      -> 1s

application-prod.yml:
  shipping.retry.max-attempts -> 5

commandLineArgs:
  shipping.retry.max-attempts -> 7
```

Một nguồn không cần chứa đủ tất cả các khóa. Khi hỏi `shipping.retry.backoff`, chỉ nguồn `application.yml` có thể cung cấp giá trị; khi hỏi `shipping.retry.max-attempts`, nhiều nguồn cùng tham gia.

### 2.2. Environment chọn theo thứ tự

`ConfigurableEnvironment` giữ danh sách `PropertySource` có thứ tự. Khi giải quyết một thuộc tính thông thường, nguồn có ưu tiên cao hơn cung cấp giá trị sẽ thắng.

```text
commandLineArgs         max-attempts = 7
application-prod.yml    max-attempts = 5
application.yml         max-attempts = 3
                        ---------------
effective value                      7
```

Đây là mô hình minh họa của một tiến trình cụ thể, **không phải danh sách thứ tự nguồn bắt buộc của mọi bản Boot**. Các nguồn thực tế và thứ tự cuối cùng có thể phụ thuộc Config Data imports, cấu hình bổ sung, môi trường web, custom PropertySource và test context.

### 2.3. Binder tạo một object có kiểu

Ví dụ record:

```java
@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        boolean enabled,
        Retry retry
) {
    public record Retry(
            int maxAttempts,
            Duration backoff
    ) {}
}
```

Binder chuyển `"7"` thành `int 7` và `"1s"` thành `Duration.ofSeconds(1)`, rồi tạo object Java. Giá trị ở file nguồn, giá trị do `Environment` giải quyết và giá trị ở bean có thể **khác dạng biểu diễn** mà vẫn có cùng ý nghĩa.

## 3. Hai endpoint thực hiện nhiệm vụ gì?

| URL | Dữ liệu tập trung | Câu hỏi |
| --- | --- | --- |
| `GET /actuator/env` | `Environment`, profiles, danh sách nguồn | Những nguồn nào đang tồn tại? |
| `GET /actuator/env/{property.name}` | Một khóa, source hiệu lực, các source cạnh tranh | Ai đang thắng cho khóa này? |
| `GET /actuator/configprops` | Các bean `@ConfigurationProperties` | Những bean nào đã được bind? |
| `GET /actuator/configprops/{prefix}` | Các bean dưới prefix phù hợp | Object dưới nhóm này nhận gì? |

Base path `/actuator` có thể thay đổi bằng `management.endpoints.web.base-path`. Cổng management có thể khác cổng ứng dụng nếu triển khai cấu hình riêng. Những URL trong bài mặc định dùng một ứng dụng lab ở `127.0.0.1:8080`.

Điều kiện có response:

1. Project có `spring-boot-starter-actuator`.
2. Ứng dụng có web stack để cung cấp HTTP endpoint.
3. Endpoint được enable/access và expose trong cấu hình tương ứng.
4. Request qua được lớp xác thực/phân quyền và chính sách mạng.
5. Tiến trình đang chạy và context đã khởi động thành công.

Nếu một điều kiện không đạt, không thể kết luận rằng property không tồn tại chỉ vì HTTP trả 404/401/403.

## 4. Chuẩn bị dependency và cấu hình Actuator

Với Maven được quản lý dependency bởi Spring Boot parent/BOM:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Gradle Groovy:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Gradle Kotlin:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Ở môi trường lab chỉ dùng dữ liệu giả:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,env,configprops"
    jmx:
      exposure:
        include: "health"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

**Không dùng danh sách expose này như mặc định production.** Hai endpoint chẩn đoán có thể tiết lộ metadata hạ tầng ngay cả khi raw values được che. Trên production, chỉ expose đúng endpoint cần thiết, có mạng quản trị, authentication/authorization, TLS và kiểm toán theo yêu cầu.

`management.endpoints.web.exposure.include` dùng `endpoints` số nhiều; `management.endpoint.env.show-values` và `management.endpoint.configprops.show-values` dùng `endpoint` số ít. Nhầm số ít/số nhiều là lỗi cấu hình thường gặp.

## 5. Thực hành hoàn chỉnh: chuẩn bị ba nguồn cấu hình

Cấu trúc thư mục:

```text
shipping-config-lab/
  src/main/java/com/example/shipping/
    ShippingApplication.java
    ShippingProperties.java
    ShippingPlanService.java
  src/main/resources/
    application.yml
    application-prod.yml
  src/test/java/com/example/shipping/
    ShippingBindingTest.java
```

File `application.yml`:

```yaml
shipping:
  enabled: true
  endpoint: https://shipping-default.example.invalid/api
  retry:
    max-attempts: 3
    backoff: 1s
```

File `application-prod.yml`:

```yaml
shipping:
  endpoint: https://shipping-prod.example.invalid/api
  retry:
    max-attempts: 5
```

Trong lab, lệnh khởi động JAR:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --shipping.retry.max-attempts=7
```

`app.jar` là tên minh họa. Các URL có hậu tố `.invalid` là dữ liệu giả, không phải dịch vụ thật.

Dự đoán trong trường hợp không có source cao hơn:

| Property | File chung | File prod | Command line | Hiệu lực |
| --- | --- | --- | --- | --- |
| `shipping.enabled` | true | Không khai | Không khai | true |
| `shipping.endpoint` | URL default | URL prod | Không khai | URL prod |
| `shipping.retry.max-attempts` | 3 | 5 | 7 | 7 |
| `shipping.retry.backoff` | 1s | Không khai | Không khai | 1s |

Giờ ta có một ví dụ mà `env` sẽ giúp tìm nguồn thắng, còn `configprops` giúp nhìn object Java nhận những giá trị này.

## 6. Tạo @ConfigurationProperties và đăng ký bean

File `ShippingProperties.java`:

```java
package com.example.shipping;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        boolean enabled,
        URI endpoint,
        Retry retry
) {
    public record Retry(
            int maxAttempts,
            Duration backoff
    ) {}
}
```

File `ShippingApplication.java`:

```java
package com.example.shipping;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ShippingProperties.class)
public class ShippingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShippingApplication.class, args);
    }
}
```

`@EnableConfigurationProperties(ShippingProperties.class)` đăng ký record để Binder tạo bean. Có thể dùng `@ConfigurationPropertiesScan` cho các project lớn, nhưng nên chọn cơ chế đăng ký rõ ràng và kiểm tra package quét.

Các bước liên kết:

```text
shipping.enabled             -> boolean enabled
shipping.endpoint            -> URI endpoint
shipping.retry.max-attempts  -> int Retry.maxAttempts
shipping.retry.backoff       -> Duration Retry.backoff
```

Một lỗi đáng chú ý: `@ConfigurationProperties` trên class **không tự bảo đảm class ấy trở thành bean** nếu project chưa đăng ký. Vì vậy, `env` có thể cho thấy khóa đúng nhưng `configprops` không có bean tương ứng.

## 7. Bean nghiệp vụ dùng cấu hình

Tạo `ShippingPlanService.java`:

```java
package com.example.shipping;

import java.net.URI;
import java.time.Duration;

import org.springframework.stereotype.Service;

@Service
public class ShippingPlanService {

    private final ShippingProperties properties;

    public ShippingPlanService(ShippingProperties properties) {
        this.properties = properties;
    }

    public Plan currentPlan() {
        return new Plan(
            properties.enabled(),
            properties.endpoint(),
            properties.retry().maxAttempts(),
            properties.retry().backoff()
        );
    }

    public record Plan(
        boolean enabled,
        URI endpoint,
        int maxAttempts,
        Duration backoff
    ) {}
}
```

`currentPlan()` chỉ tạo một giá trị mô tả, không gửi HTTP. Với cấu hình lab và dòng lệnh đã nêu, kết quả Java kỳ vọng:

```text
enabled        = true
endpoint       = https://shipping-prod.example.invalid/api
maxAttempts    = 7
backoff        = PT1S
```

Dạng `PT1S` là biểu diễn của Java `Duration` cho một giây. So sánh giá trị typed thay vì bắt chuỗi lúc bind phải giống hệt văn bản trong YAML.

## 8. Đọc /actuator/env: profile và thứ tự các nguồn

Gọi từ máy thử nghiệm:

```bash
curl -i 'http://127.0.0.1:8080/actuator/env'
```

Theo REST API của Spring Boot, response có thể có các trường:

```text
activeProfiles
defaultProfiles
propertySources[]
  name
  properties
```

Một response đã rút gọn để minh họa:

```json
{
  "activeProfiles": ["prod"],
  "defaultProfiles": ["default"],
  "propertySources": [
    {
      "name": "commandLineArgs",
      "properties": {}
    },
    {
      "name": "systemProperties",
      "properties": {}
    },
    {
      "name": "systemEnvironment",
      "properties": {}
    }
  ]
}
```

**Không xem JSON trên như ảnh chụp một Boot instance thật.** Các entry được cắt ngắn; ứng dụng thực tế có thêm nguồn Config Data và nhiều nguồn khác. Tên và thứ tự chính xác phụ thuộc phiên bản và điều kiện triển khai.

Điều cần quan sát:

1. `activeProfiles` có chứa `prod` không?
2. Có `commandLineArgs` khi tiến trình thực sự được cấp CLI arguments không?
3. Những nguồn Config Data nào được nạp?
4. Có source từ file bên ngoài hoặc `spring.config.import` không?
5. Có custom `EnvironmentPostProcessor` bổ sung nguồn không?
6. `propertySources` theo **thứ tự ưu tiên**, không phải thứ tự alphabet.

Khi chỉ quan tâm một key, không cần tải cả Environment. Chuyển sang `/actuator/env/{property.name}`.

## 9. Truy vấn một khóa: /actuator/env/{property.name}

Dùng canonical name:

```bash
curl -i \
  'http://127.0.0.1:8080/actuator/env/shipping.retry.max-attempts'
```

Các trường quan trọng theo tài liệu Actuator REST API:

| Đường dẫn JSON | Ý nghĩa |
| --- | --- |
| `property.source` | Nguồn đang cung cấp property hiệu lực |
| `property.value` | Giá trị hiệu lực nếu được phép hiển thị; có thể đã sanitize |
| `activeProfiles` | Profiles đang hoạt động |
| `defaultProfiles` | Profiles mặc định |
| `propertySources[]` | Các nguồn theo thứ tự precedence |
| `propertySources[].name` | Tên mỗi nguồn |
| `propertySources[].property` | Thông tin property trong nguồn đó, nếu có |
| `propertySources[].property.origin` | Vị trí gốc, nếu nguồn có origin metadata |

Ví dụ mô phỏng, rút gọn và đã che các value:

```json
{
  "activeProfiles": ["prod"],
  "property": {
    "source": "commandLineArgs",
    "value": "******"
  },
  "propertySources": [
    {
      "name": "commandLineArgs",
      "property": {"value": "******"}
    },
    {
      "name": "Config resource 'application-prod.yml'",
      "property": {
        "value": "******",
        "origin": "application-prod.yml - source location"
      }
    },
    {
      "name": "Config resource 'application.yml'",
      "property": {
        "value": "******",
        "origin": "application.yml - source location"
      }
    }
  ]
}
```

Tên resource và origin ở đây được đơn giản hóa, không phải chuỗi framework buộc phải trả.

Cách đọc:

1. `property.source` chỉ `commandLineArgs`: source đó đang thắng.
2. Source từ file prod và file chung vẫn có thể tồn tại ở phía dưới, không tự biến mất.
3. Value hiển thị `******` không chứng minh giá trị thật là sáu dấu sao; đó là dữ liệu bị che.
4. Khi origin có mặt, nó giúp xác định resource và dòng/cột của file nạp.
5. Nếu chỉ muốn hiểu vì sao một source thắng, ta **không cần bỏ sanitization**.

### 9.1. Đừng suy ra nguồn thắng bằng source đầu tiên của toàn bộ response

Source đầu tiên trong danh sách có thể không chứa khóa đang hỏi. Hãy dùng **`property.source`** ở cấp trên của response truy vấn một key; danh sách source phía dưới dùng để xem các nguồn cạnh tranh, origin và precedence.

### 9.2. Một source có tên nhưng không có property

Entry `propertySources[].name` chỉ cho biết nguồn có trong Environment. Nếu entry không có `property`, điều đó không có nghĩa source đã góp giá trị cho key. Khi có nhiều nguồn, đừng đếm nguồn không chứa key như một lần “override”.

## 10. Origin: chứng cứ giá trị đến từ file nào

Đối với Config Data được nạp từ file, Spring Boot có thể lưu origin, ví dụ resource và vị trí dòng/cột:

```text
class path resource [application-prod.yml] - 5:19
```

Hoặc một file ngoài:

```text
file [/etc/myapp/application-prod.yml] - 5:19
```

Đây là **ví dụ về kiểu origin**, không phải kết quả thật của lab.

Origin đặc biệt hữu ích khi:

- Có file ngoài JAR được mount trong container.
- Có nhiều `spring.config.location` hoặc `spring.config.additional-location`.
- Có `spring.config.import`.
- Có nhiều YAML document được kích hoạt theo profile.
- Có các bản build hoặc deployment dùng resource path khác nhau.

Không phải mọi PropertySource cung cấp origin. Với command-line/system environment, metadata có thể ít hơn một file YAML. **Thiếu origin không đồng nghĩa thiếu giá trị**.

Một lỗi chẩn đoán phổ biến là chỉ đọc file `src/main/resources/application.yml` của repository trong khi process chạy bằng file mounted từ deployment. `env` của đúng instance giúp phát hiện nguồn nạp thực tế.

## 11. Dùng configprops để xem kết quả binding

Gọi:

```bash
curl -i 'http://127.0.0.1:8080/actuator/configprops/shipping'
```

REST API mô tả cấu trúc:

```text
contexts
  -> <context-id>
     -> beans
        -> <bean-id>
           -> prefix
           -> properties
           -> inputs
```

Trong đó:

- **`prefix`**: prefix của `@ConfigurationProperties`.
- **`properties`**: các field/value được biểu diễn của bean.
- **`inputs`**: những property đã tham gia binding, có thể chứa origin và giá trị input.
- **`contexts`**: phân biệt các application context nếu có nhiều context.
- **`beans`**: map theo tên bean; không được giả định bean name luôn là tên class viết thường.

Ví dụ JSON **minh họa đã rút gọn**:

```json
{
  "contexts": {
    "application": {
      "beans": {
        "shipping-com.example.shipping.ShippingProperties": {
          "prefix": "shipping",
          "properties": {
            "enabled": "******",
            "endpoint": "******",
            "retry": {
              "maxAttempts": "******",
              "backoff": "******"
            }
          },
          "inputs": {
            "retry": {
              "maxAttempts": {
                "value": "******"
              },
              "backoff": {
                "value": "******"
              }
            }
          }
        }
      }
    }
  }
}
```

**Đây không phải schema chính xác cho mọi phiên bản và mọi object type.** Một response thực tế có thể biểu diễn nested objects, scalar, collection, origin và sanitized values khác. Bài học tập trung vào ý nghĩa các trường chứ không yêu cầu cùng bean name hoặc số ký tự mask.

### 11.1. So sánh properties với inputs

Một bean có thể có giá trị nhưng không có input cùng tên. Nguyên nhân có thể là:

- JavaBean field initializer cung cấp default.
- Constructor binding dùng `@DefaultValue`.
- Một getter tính toán value.
- Thuộc tính không được cấp ở nguồn ngoài.
- Cách serialize hoặc tổng hợp input của endpoint không thể hiện đường dẫn như dự đoán.

`properties` là góc nhìn **đối tượng được bind**; `inputs` là góc nhìn **đầu vào tham gia quá trình bind**. Không đánh đồng chúng.

### 11.2. Prefix filter không nhất thiết khớp duy nhất một bean

`GET /actuator/configprops/shipping` có thể trả tất cả configuration-properties bean dưới prefix stem phù hợp. Trong project có nhiều module, cần kiểm tra từng bean `prefix` và tên class, không lấy entry đầu tiên rồi cho rằng đó là service đang dùng.

## 12. Quy trình chẩn đoán hai endpoint theo từng bước

Khi sự cố báo “giá trị maxAttempts vẫn sai”:

**Bước 1 — Chốt canonical property name.** Từ `@ConfigurationProperties(prefix="shipping")` và field `retry.maxAttempts`, xác định khóa `shipping.retry.max-attempts`. Không đoán theo cách viết Java hoặc gõ sai chính tả.

**Bước 2 — Gọi đúng instance.** Ghi build, pod/container, management host, port, profile và thời điểm. Tránh lấy `env` của replica A trong khi user request chạy trên replica B.

**Bước 3 — Kiểm tra active profile.** `/actuator/env` có cho thấy `prod` đang active không?

**Bước 4 — Truy vấn một key.** Dùng `/actuator/env/shipping.retry.max-attempts`.

**Bước 5 — Ghi nhận source thắng.** Xem `property.source` và nguồn nào khác cũng có key theo `propertySources`.

**Bước 6 — Kiểm tra origin.** Nếu nguồn từ file, xác định file nào đang được nạp. Nếu từ CLI/ENV, đối chiếu cấu hình của process/deployment, không chỉ repository.

**Bước 7 — Xem configprops theo prefix.** Xác minh `ShippingProperties` tồn tại, prefix đúng và có field `retry.maxAttempts`.

**Bước 8 — Phân biệt properties và inputs.** Giá trị có thể đến từ default Java thay vì một source có origin.

**Bước 9 — Kiểm tra typed value an toàn.** Với dữ liệu không nhạy cảm, dùng test/assertion hoặc một kênh nội bộ được bảo vệ thay vì mở raw values của cả endpoint.

**Bước 10 — Kiểm tra service.** Nếu Bean là 7 nhưng service giới hạn thành 4, lỗi nằm ở logic ứng dụng, không phải source precedence.

**Bước 11 — Ghi nguyên nhân.** Kết luận chính xác là “CLI thắng profile”, “field chưa được bind”, “converter không chấp nhận”, “default được dùng”, hay “service tự biến đổi”.

## 13. Thực nghiệm A: CLI thắng file profile

Với ứng dụng lab:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --shipping.retry.max-attempts=7
```

File chung khai 3; file profile khai 5; command line khai 7.

Nếu không có source cao hơn, `env/shipping.retry.max-attempts` cho biết source hiệu lực là `commandLineArgs`. Trong `configprops/shipping`, `retry.maxAttempts` của bean được bind thành 7, miễn là cấu hình và class đúng.

Nếu người vận hành muốn bỏ override, việc sửa lại `application.yml` từ 3 sang 9 có thể không có tác dụng vì CLI tiếp tục thắng. Cần kiểm tra launcher, service manifest, Helm values, container args hoặc pipeline đang cấp `--shipping.retry.max-attempts=7`.

**Chẩn đoán đúng tìm nơi thực sự cung cấp override**, không tăng giảm các số ở mọi file cùng lúc.

## 14. Thực nghiệm B: profile thắng file chung

Chạy:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Không còn CLI override, nên nếu không có source cao hơn:

```text
shipping.retry.max-attempts = 5
shipping.retry.backoff      = 1s
shipping.endpoint           = prod endpoint
```

Truy vấn `env/shipping.retry.max-attempts`: nguồn có thể là Config Data từ `application-prod.yml`.

Chạy:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Nếu không có `application-dev.yml` cung cấp override và không có nguồn khác, `maxAttempts` trở về 3 từ file chung.

Bài học: thấy `activeProfiles=["prod"]` chưa đủ để biết **mọi khóa** đến từ file profile. Với từng key, vẫn phải xem source được resolver chọn.

## 15. Thực nghiệm C: biến môi trường

Một container có thể cấp:

```text
SHIPPING_RETRY_MAXATTEMPTS=9
```

Spring Boot có quy tắc chuyển từ tên canonical sang environment-variable form: ví dụ `shipping.retry.max-attempts` được chuyển thành `SHIPPING_RETRY_MAXATTEMPTS` khi áp dụng quy tắc thay dấu chấm bằng gạch dưới, bỏ dấu gạch ngang và chuyển thành chữ hoa.

Nếu không có CLI hoặc nguồn cao hơn, bean có thể nhận 9.

Nếu người vận hành mở một terminal ngoài container và thấy biến cùng tên, chưa chắc process đang chạy cũng nhận biến đó. Môi trường của một shell không phải môi trường của mọi process. Hãy kiểm tra nguồn `systemEnvironment` trên **đúng ứng dụng** và đối chiếu deployment spec.

Với những key có Map/List hoặc dấu đặc biệt, quy tắc mapping có thêm chi tiết. Đừng suy ra tên ENV bằng cách thay ký tự tùy ý rồi mặc định Binder hiểu đúng; khi cần, viết test trên phiên bản Boot thực tế.

## 16. Khi env đúng nhưng configprops không có bean

Giả sử:

```text
GET /actuator/env/shipping.retry.max-attempts
  -> có property và source hiệu lực

GET /actuator/configprops/shipping
  -> không thấy ShippingProperties
```

Những nguyên nhân có thể:

1. Class chưa được đăng ký bằng `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan`.
2. Package scanning không bao phủ class.
3. Bean được tạo theo condition/profile không đạt.
4. Prefix Java không phải `shipping`.
5. Ứng dụng dùng `@Value` hoặc `Environment` trực tiếp, không có configuration-properties bean.
6. Bạn đang truy vấn nhầm instance hoặc context.
7. Bean đã được tạo thủ công ngoài Spring nên không xuất hiện theo cơ chế Actuator mong đợi.
8. Endpoint không được expose hoặc request bị security chặn, khiến người đọc tưởng response rỗng.

Một key ở Environment **không tự sinh bean Java**. Cần class, cơ chế đăng ký và kiểu đích phù hợp.

## 17. Khi bean có default nhưng env không tìm thấy key

Java:

```java
@ConfigurationProperties(prefix = "reports")
public class ReportProperties {
    private int maxRows = 100;

    public int getMaxRows() { return maxRows; }
    public void setMaxRows(int maxRows) {
        this.maxRows = maxRows;
    }
}
```

Nếu không có nguồn nào khai `reports.max-rows`:

- `env/reports.max-rows` có thể không tìm thấy property.
- Bean `ReportProperties` vẫn có giá trị `maxRows=100` do Java initializer.
- `configprops` có thể thể hiện property 100 nhưng `inputs` không nhất thiết có một origin của file cấu hình.

Tương tự với record:

```java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "reports")
public record ReportProperties(
        @DefaultValue("100") int maxRows
) {}
```

`@DefaultValue` là cơ chế runtime binding default khi constructor binding; nó **không tự tạo thêm một PropertySource** với khóa `reports.max-rows`.

Vì vậy, “bean có giá trị nhưng env không có key” **không nhất thiết là lỗi**. Cần phân biệt default của object với giá trị do một nguồn ngoài cấp.

## 18. Khi env là String nhưng bean có kiểu khác

Ví dụ:

```properties
shipping.retry.backoff=250ms
```

`Environment.getProperty("shipping.retry.backoff")` có thể trả chuỗi `"250ms"`. Record có `Duration backoff` được bind thành một `Duration` tương đương 250 ms.

Dạng hiển thị Java có thể là `PT0.25S`; nó khác văn bản nguồn nhưng cùng ý nghĩa.

Một số ví dụ:

| Chuỗi nguồn | Kiểu Java | Kết quả |
| --- | --- | --- |
| `"7"` | `int` | 7 |
| `"false"` | `boolean` | false |
| `"250ms"` | `Duration` | 250 mili giây |
| `"8MB"` | `DataSize` | Đối tượng DataSize |
| `"https://x.example.invalid"` | `URI` | Đối tượng URI |
| `"FAST"` | enum `Mode` | Enum `FAST` nếu khai báo hợp lệ |

`configprops` là nơi kiểm tra cấu trúc bean, nhưng nếu policy che value, nên assert trực tiếp qua test đối với giá trị an toàn thay vì bật `always` trên production.

### 18.1. Lỗi conversion khiến ứng dụng chưa khởi động

Nếu cấu hình:

```properties
shipping.retry.max-attempts=seven
```

và Java cần `int`, Binder có thể gây startup failure. Khi ứng dụng không khởi động, **không có Actuator HTTP endpoint hoạt động của instance thất bại** để truy vấn. Phải dùng startup logs, stack trace đã được bảo vệ hoặc một test context có cấu hình tối giản.

Đừng lấy `env` của replica khác đang chạy để suy ra trạng thái của instance đã crash.

## 19. Placeholder khiến nhiều source cùng quyết định kết quả

Giả sử file chung chứa:

```yaml
partner:
  host: localhost
  url: "https://${partner.host}/api"
```

Một Java system property hoặc CLI cung cấp:

```properties
partner.host=partner.internal
```

`partner.url` có thể vẫn đến từ `application.yml`, nhưng giá trị sau giải quyết placeholder là:

```text
https://partner.internal/api
```

Vì vậy phải truy vấn cả:

```bash
curl -i 'http://127.0.0.1:8080/actuator/env/partner.url'
curl -i 'http://127.0.0.1:8080/actuator/env/partner.host'
```

Source thắng của `partner.url` không nhất thiết là source đã cung cấp phần `host`. Nếu một property có placeholder, chẩn đoán các **khóa thành phần** chứ không chỉ khóa kết quả.

Một trường hợp nữa:

```yaml
partner:
  url: "https://${partner.host:localhost}/api"
```

Nếu không có `partner.host`, placeholder có fallback `localhost`. Không nhất thiết `env/partner.host` sẽ thấy một giá trị vì fallback này nằm trong biểu thức chứ không phải một property source độc lập.

## 20. Chú ý List và Map khi đối chiếu env với configprops

Với scalar, chọn nguồn cao hơn khá trực quan. Với collection, Binder có quy tắc riêng.

### 20.1. List

`application.yml`:

```yaml
routing:
  servers:
    - first.example.invalid
    - second.example.invalid
```

`application-prod.yml`:

```yaml
routing:
  servers:
    - prod.example.invalid
```

Spring Boot có quy tắc thay List giữa các nguồn thay vì luôn nối từng phần tử. Bean có thể nhận chỉ một server của profile.

Khi chẩn đoán, đừng chỉ nhìn `routing.servers[0]` rồi suy ra toàn List. Xem `configprops` để biết cấu trúc đã bind.

### 20.2. Map

`application.yml`:

```yaml
routing:
  handlers:
    orders: order-handler
    payments: payment-handler
```

File profile:

```yaml
routing:
  handlers:
    payments: prod-payment-handler
```

Map có thể chứa cả `orders` và `payments`, trong đó `payments` mang value từ nguồn ưu tiên cao hơn.

Nếu key Map chứa ký tự `/`, `@` hoặc ký tự đặc biệt, dùng bracket notation để bảo toàn key literal, ví dụ `"[/api/v1]"` trong YAML. Khi key bị chuẩn hóa sai, `env` có thể cho thấy một tên property nhưng Map đã bind có tên key khác; phải xem cả cấu trúc Map cuối trong `configprops`.

## 21. Khi bean đúng nhưng service vẫn dùng giá trị khác

Service có thể áp dụng quy tắc nghiệp vụ:

```java
public int effectiveAttempts() {
    return Math.min(properties.retry().maxAttempts(), 4);
}
```

Khi bean có `maxAttempts=7`, service cố tình giới hạn bằng 4. Không có lỗi ở source hay Binder.

Một biến thể khác:

```java
public final class RetryClient {
    private final int retryLimit;

    public RetryClient(ShippingProperties properties) {
        this.retryLimit = properties.retry().maxAttempts();
    }
}
```

Nếu người vận hành thêm một PropertySource mới **sau khi RetryClient đã được tạo**, lệnh `Environment.getProperty` ở thời điểm sau có thể thấy giá trị mới, trong khi field `retryLimit` đã chụp snapshot cũ.

**MutablePropertySources thay đổi không tự refresh mọi bean.** Khi `env` và `configprops` hoặc service khác nhau về thời điểm, kiểm tra lifecycle, caching, refresh scope và nơi bean được tạo. Đừng coi thay đổi runtime `Environment` là một phép rebinding tự động.

## 22. Relaxed binding, canonical name và lỗi chính tả

Java field:

```java
int maxAttempts;
```

Cấu hình canonical:

```properties
shipping.retry.max-attempts=7
```

Một số biến thể tên có thể được Binder xử lý nhờ relaxed binding, nhưng điều đó không biến mọi lỗi chính tả thành đúng.

Sai:

```properties
shipping.retry.max-attmpts=7
```

Tên này không tương đương `max-attempts` chỉ vì “nhìn gần giống”. Có thể:

- `env/shipping.retry.max-attmpts` thấy khóa sai được nạp.
- `env/shipping.retry.max-attempts` không thấy khóa đúng.
- Bean giữ default hoặc giá trị từ nguồn khác.
- Với `ignoreUnknownFields` mặc định hoặc tùy chỉnh, một thuộc tính không có đích có thể bị bỏ qua hoặc gây lỗi tùy cấu hình.

Quy trình phát hiện:

1. Xác định prefix và field từ Java.
2. Sử dụng canonical lowercase kebab-case để hỏi `env`.
3. Kiểm tra các tên khóa thực tế trong nguồn đã xác định.
4. Đối chiếu `configprops`.
5. Thêm test để ngăn sai chính tả tái diễn.

## 23. Vì sao @Value không xuất hiện như configprops?

Một bean có thể đọc trực tiếp:

```java
@Component
public class PartnerClient {

    public PartnerClient(
        @Value("${partner.timeout:2s}") Duration timeout) {
        // ...
    }
}
```

Hoặc:

```java
String value = environment.getProperty("partner.timeout");
```

Các cách này không tự đăng ký một `@ConfigurationProperties` bean có prefix `partner`. Vì vậy:

- `env/partner.timeout` có thể tìm được property.
- `configprops/partner` không nhất thiết chứa một bean tương ứng.
- Nếu cần xác minh giá trị `@Value` đã được inject, hãy test hoặc chẩn đoán bean đó bằng cơ chế an toàn.

`configprops` không phải danh sách mọi bean hoặc mọi field được inject trong ứng dụng. Nó tập trung vào **configuration properties beans**.

## 24. Test đối chiếu Environment, typed bean và service

Tạo `ShippingBindingTest.java`:

```java
package com.example.shipping;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("prod")
@SpringBootTest(
    classes = ShippingApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "shipping.retry.max-attempts=7",
        "shipping.retry.backoff=250ms"
    }
)
class ShippingBindingTest {

    @Autowired
    Environment environment;

    @Autowired
    ShippingProperties properties;

    @Autowired
    ShippingPlanService service;

    @Test
    void checksResolverBindingAndConsumer() {
        assertThat(environment.getProperty(
            "shipping.retry.max-attempts"
        )).isEqualTo("7");

        assertThat(properties.retry().maxAttempts())
            .isEqualTo(7);

        assertThat(properties.retry().backoff())
            .isEqualTo(Duration.ofMillis(250));

        assertThat(service.currentPlan().maxAttempts())
            .isEqualTo(7);
    }
}
```

Test này chứng minh dữ liệu test override được Resolver, Binder và service sử dụng thống nhất. **Nó không kiểm tra rằng nguồn command line thắng**, vì `@SpringBootTest.properties` là một **test PropertySource**, không phải `commandLineArgs`. Nếu cần chứng minh nguồn thắng trong deploy CLI, phải quan sát đúng tiến trình khởi động bằng CLI hoặc viết test bootstrap tương ứng.

### 24.1. Test không cần mở raw values qua Actuator

Khi `show-values=never`, request HTTP có thể chỉ trả `******`. Ta vẫn có thể dùng test như trên để assert `7` hoặc `Duration.ofMillis(250)` một cách độc lập, với giá trị không nhạy cảm và context cô lập.

Đối với mật khẩu/token, không tạo test in secret; dùng sentinel giả và assertion rằng response diagnostic **không chứa** sentinel.

## 25. Đọc response an toàn bằng curl và jq

Ở môi trường thử nghiệm có dữ liệu giả, có thể lọc những trường liên quan:

```bash
curl -fsS \
  'http://127.0.0.1:8080/actuator/env/shipping.retry.max-attempts' |
jq '{
  activeProfiles,
  winningSource: .property.source,
  sources: [
    .propertySources[] |
    {name, origin: .property.origin}
  ]
}'
```

Truy vấn này hướng tới tên nguồn và origin, không lấy raw values. Với `jq`, trường `origin` có thể không tồn tại hoặc null đối với những nguồn không lưu thông tin gốc.

Xem tên bean configprops:

```bash
curl -fsS \
  'http://127.0.0.1:8080/actuator/configprops/shipping' |
jq '.contexts | to_entries[] | {
  context: .key,
  beans: (.value.beans | keys)
}'
```

Trong một môi trường chẩn đoán được phép, hai lệnh hỗ trợ giảm lượng dữ liệu cần xem. **Filtering không thay thế security.** Endpoint vẫn phải được bảo vệ, và việc chuyển toàn bộ JSON qua proxy/network vẫn cần tuân theo chính sách bảo mật.

Không ghi kết quả raw vào ticket, terminal history hay log tập trung khi không cần.

## 26. Bảo vệ bí mật khi dùng env và configprops

Thông tin cấu hình có thể chứa:

- Database password.
- Token dịch vụ và API keys.
- Signing keys.
- URI có user/password.
- Header Authorization.
- Client secret, chứng chỉ, cấu hình nội bộ.
- Tên hệ thống, topology, đường dẫn file và profile nhạy cảm.

Theo tài liệu Spring Boot Actuator, `env` và `configprops` **sanitize toàn bộ giá trị theo mặc định** ở những phiên bản hiện đại; thường hiển thị `******`. Có ba chế độ:

| `show-values` | Hành vi |
| --- | --- |
| `never` | Luôn che value |
| `when-authorized` | Có thể cho người authorized xem value; custom sanitizer vẫn có thể che |
| `always` | Có thể cho người truy cập endpoint xem value; custom sanitizer vẫn có thể che |

Cấu hình thận trọng:

```properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

Nếu cấu hình `when-authorized`, phải hiểu role và kênh truy cập:

- HTTP: principal đã xác thực và đáp ứng roles theo cấu hình endpoint.
- Nếu không cấu hình roles, mọi người đã xác thực có thể được coi authorized.
- JMX có quy tắc khác: trong bối cảnh `when-authorized`, người dùng JMX được coi authorized theo tài liệu hiện đại.

**Đừng bật `always` để xem một timeout.** Nếu cần giá trị không nhạy cảm, test trực tiếp bean hoặc tạo một chẩn đoán whitelist được phân quyền.

Một response che value vẫn có thể lộ **tên khóa, bean, path, origin, profile**. Vì vậy không coi `env` đã mask là endpoint an toàn để public.

## 27. Khi Actuator không truy cập được

| Triệu chứng | Nguyên nhân có thể | Bước tiếp |
| --- | --- | --- |
| Connection refused | Sai host/port, app chưa chạy | Kiểm tra process và management port |
| `404` | Endpoint không expose/không tồn tại, path khác | Kiểm tra enablement/access, exposure, base path |
| `401` | Cần authentication | Dùng đường truy cập được cấp quyền |
| `403` | Thiếu authorization | Kiểm tra role/security chain |
| `200` nhưng value là `******` | Sanitization đang bật | Dùng source/origin hoặc test typed bean |
| `200` nhưng không thấy bean | Bean không đăng ký/prefix khác | Kiểm tra `@ConfigurationProperties` |
| App crash lúc khởi động | Bind/validation/conversion lỗi | Đọc startup failure, không dựa vào Actuator |
| Output khác giữa lần gọi | Khác instance/time/context | Cố định target instance và ghi timestamp |

Nếu project tự khai báo `SecurityFilterChain`, phải kiểm tra nó có bảo vệ management endpoint thật sự không. Đừng dựa vào giả định “có Spring Security trên classpath thì mọi Actuator endpoint được khóa đúng” khi app đã tự tùy chỉnh security.

## 28. Chẩn đoán khi ứng dụng không khởi động

Ví dụ:

```properties
shipping.retry.max-attempts=seven
```

Nếu record cần `int`, Binder có thể thất bại trước khi HTTP server sẵn sàng. Không thể hỏi `/actuator/configprops` của instance đã fail.

Thứ tự xử lý:

1. Đọc thông báo `Failed to bind properties` và nguyên nhân chuyển kiểu.
2. Xác định chính xác property và kiểu Java.
3. Tìm nguồn nạp được chỉ ra bởi lỗi/origin nếu có.
4. Kiểm tra file/ENV/CLI của **đúng process**.
5. Tạo một test context nhỏ với `ApplicationContextRunner` nếu muốn xác nhận expected startup failure.
6. Không bật debug output tiết lộ secret thật.
7. Không lấy response từ replica khác làm bằng chứng cho instance lỗi.

`env` và `configprops` là công cụ quan sát **ứng dụng đang chạy**, không thay thế startup logs trong mọi tình huống.

## 29. Chẩn đoán khi có nhiều instance

Trong một deployment rolling update:

```text
pod-A:
  image v1
  maxAttempts = 5

pod-B:
  image v2
  maxAttempts = 7
```

Load balancer có thể đưa `GET /actuator/env/...` tới pod-A nhưng request nghiệp vụ tới pod-B. Nếu không biết instance nào đã trả lời, kết luận “env=5 mà service dùng 7” có thể là so sánh hai hệ thống khác nhau.

Cần ghi:

- Instance ID/pod name.
- Version artifact.
- Active profiles.
- Thời điểm.
- Property source và origin.
- Bean/configprops tương ứng.
- Cấu hình deployment của instance đó.

Nên dùng đường quản trị nội bộ cho **mỗi instance** khi điều tra, không dựa trên việc gateway ngẫu nhiên chọn một replica.

## 30. Bài tập 1: nguồn nào thắng?

Cho:

```text
application.yml:
  feature.limit = 10

application-prod.yml:
  feature.limit = 20

commandLineArgs:
  feature.limit = 30
```

Profile prod hoạt động. Hãy dự đoán:

- Giá trị Environment là 30.
- `property.source` từ `env/feature.limit` là `commandLineArgs` nếu không có source cao hơn.
- Hai source Config Data vẫn có thể nằm trong `propertySources`.
- Nếu `show-values=never`, origin/tên nguồn vẫn giúp phát hiện override mà không cần xem raw value.

Sau đó bỏ command-line argument, gọi lại endpoint trên một instance mới và dự đoán giá trị hiệu lực là 20.

## 31. Bài tập 2: env có property nhưng configprops không bind

Java:

```java
@ConfigurationProperties(prefix = "feature")
public record FeatureProperties(int maxItems) {}
```

Config:

```properties
feature.max-itmes=30
```

Hãy giải thích:

1. `env/feature.max-itmes` có thể thấy khóa này.
2. `feature.max-items` mới là canonical key tương ứng Java.
3. Relaxed binding không sửa lỗi đánh máy `itmes`.
4. `maxItems` có thể giữ default hoặc giá trị từ nguồn khác.
5. Cần test typed bean và kiểm tra chính tả/unknown property policy.

## 32. Bài tập 3: so sánh giá trị typed

Input:

```properties
client.timeout=750ms
```

Java:

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(Duration timeout) {}
```

Hỏi:

- `env/client.timeout` có thể thể hiện nguồn và text value nào nếu được phép xem?
- `configprops/client` cho biết bean có field timeout không?
- Assertion Java đúng là gì?

Đáp án:

```java
assertThat(properties.timeout())
    .isEqualTo(Duration.ofMillis(750));
```

Không yêu cầu object `Duration` phải in nguyên văn `750ms`.

## 33. Bài tập 4: default không có origin

Record:

```java
@ConfigurationProperties(prefix = "reports")
public record ReportProperties(
    @DefaultValue("100") int maxRows
) {}
```

Không có source nào khai `reports.max-rows`. Hãy giải thích vì sao `env` có thể không thấy key, nhưng bean vẫn nhận 100 do constructor binding. `configprops.properties` và `configprops.inputs` có cùng ý nghĩa không?

## 34. Bài tập 5: URL với placeholder

YAML:

```yaml
service:
  host: localhost
  url: "http://${service.host}:8080"
```

Nguồn ưu tiên cao cung cấp `service.host=service.internal`. Hãy hỏi riêng `env/service.host` và `env/service.url`, đối chiếu nguồn thắng của từng khóa rồi suy ra URL đã được giải quyết. Tại sao source của URL không nhất thiết là source của host?

## 35. Bài tập 6: List và Map

File chung khai hai server trong List và hai handler trong Map. File prod khai một server và override một handler. Dùng `configprops` để quan sát List sau quy tắc replacement và Map sau quy tắc merge/override. Giải thích vì sao chỉ nhìn từng key qua `env` không đủ dự đoán mọi cấu trúc đã bind.

## 36. Bài tập 7: khắc phục rủi ro bảo mật

Một deployment có:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
  endpoint:
    env:
      show-values: always
    configprops:
      show-values: always
```

Hãy đề xuất cách giảm rủi ro:

1. Whitelist endpoint.
2. Đặt `show-values=never` khi không cần raw value.
3. Dùng authentication/authorization và mạng quản trị.
4. Kiểm tra JMX exposure.
5. Không in response chứa secret.
6. Dùng test với token giả để xác nhận masking.

## 37. Bài tập 8: service khác bean

`ShippingProperties.retry.maxAttempts=7` nhưng service dùng:

```java
int effective = Math.min(properties.retry().maxAttempts(), 4);
```

Hãy xác định kết quả của:

- `env/{key}`.
- `configprops`.
- Service thực sự.
- Root cause.

Gợi ý: không có mâu thuẫn của nguồn hay Binder; giới hạn 4 đến từ logic service.

## 38. Bài tập 9: xử lý startup failure

Config khai:

```properties
shipping.retry.max-attempts=seven
```

Ứng dụng không khởi động vì chuyển `String` sang `int` thất bại. Vì sao không thể chờ `/actuator/env` trả lời ở chính instance đó? Hãy đề xuất quy trình đọc startup failure và tạo test binding nhỏ để kiểm chứng.

## 39. Checklist thao tác thực tế

- [ ] Đúng instance, đúng version và thời điểm.
- [ ] Canonical property name đã xác định từ Java.
- [ ] Đã xem `activeProfiles`.
- [ ] Đã hỏi `env/{property.name}`.
- [ ] Đã ghi `property.source`.
- [ ] Đã xem các source cạnh tranh theo thứ tự.
- [ ] Đã đọc origin nếu có.
- [ ] Đã xác nhận bean `@ConfigurationProperties` được đăng ký.
- [ ] Đã hỏi `configprops/{prefix}`.
- [ ] Đã phân biệt `properties` và `inputs`.
- [ ] Đã cân nhắc default, placeholder, type conversion.
- [ ] Đã cân nhắc List/Map/relaxed binding.
- [ ] Đã xác minh consumer service.
- [ ] Đã giữ sanitization và bảo vệ endpoint.
- [ ] Đã xác định nguyên nhân theo đúng tầng.

## 40. Tổng kết

Khi Spring Boot dùng Externalized Configuration, một giá trị có thể bị thay đổi trước khi vào bean vì **nguồn ưu tiên cao**, hoặc khác dạng biểu diễn sau khi vào bean vì **Binder, default, conversion và cấu trúc object**. Hai endpoint Actuator cung cấp một chuỗi kiểm tra mạnh:

```text
/actuator/env/{key}
  -> property.source
  -> propertySources theo precedence
  -> origin, profiles nếu có
             |
             v
   @ConfigurationProperties Binder
             |
             v
/actuator/configprops/{prefix}
  -> bean name / prefix
  -> properties / inputs
             |
             v
    Service nhận object typed
```

Nhớ:

1. **`env` xác định nguồn thắng**, không tự chứng minh service đang dùng đúng object.
2. **`configprops` cho thấy kết quả liên kết**, không thay thế việc xem nguồn Config Data và precedence.
3. **`properties` khác `inputs`**: default có thể khiến bean có value nhưng không có source origin tương ứng.
4. **Giữ đúng canonical name**; relaxed binding không sửa mọi lỗi chính tả.
5. **List, Map, placeholder và converter** khiến một scalar lookup không thể mô tả toàn bộ cấu trúc đích.
6. **Đối chiếu trên cùng một instance, cùng thời điểm**, nhất là khi rolling deployment.
7. **Không bật raw values vì tiện debug**: Actuator mask values theo mặc định và endpoints vẫn cần security.
8. **Khi app không khởi động**, đọc startup errors và dùng test context thay vì cố gọi Actuator.
9. **Kết luận ở đúng lớp**: source, profile, precedence, binding, validation, lifecycle hoặc service logic.

### Tài liệu chính thức

- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Environment (env) REST API](https://docs.spring.io/spring-boot/api/rest/actuator/env.html)
- [Spring Boot — Configuration Properties (configprops) REST API](https://docs.spring.io/spring-boot/api/rest/actuator/configprops.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Framework — ConfigurableEnvironment API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html)

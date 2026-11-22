# `spring.config.activate.on-profile` và tài liệu cấu hình nhiều phần

Trong Spring Boot, cấu hình thường thay đổi theo môi trường: local dùng cổng 8081 và log DEBUG, staging bật một số tích hợp thử nghiệm, còn production dùng endpoint thật và log INFO. Bạn có thể tách những giá trị này vào các file `application-dev.yml`, `application-prod.yml`, hoặc đặt chúng thành **nhiều tài liệu cấu hình (multi-document configuration)** ngay trong một file.

Với cách thứ hai, `spring.config.activate.on-profile` cho biết **một tài liệu cấu hình chỉ được áp dụng khi biểu thức profile của nó khớp với môi trường đang chạy**.

Ví dụ:

```yaml
spring:
  application:
    name: order-service

server:
  port: 8080

---
spring:
  config:
    activate:
      on-profile: dev

server:
  port: 8081

logging:
  level:
    com.example.orders: DEBUG
```

Tài liệu đầu tiên là cấu hình chung. Tài liệu sau dấu `---` chỉ được kích hoạt khi profile `dev` khớp. Hai tài liệu này nằm trong **một file** `application.yml` nhưng được Spring Boot coi như **hai nhóm cấu hình có điều kiện riêng**.

Bài học giải thích cú pháp của YAML và `.properties`, cách profile được chọn, biểu thức profile, thứ tự ưu tiên, quy tắc ghi đè, các giới hạn của Config Data và cách kiểm chứng cấu hình thực sự có hiệu lực.

## 1. Ba khái niệm cần phân biệt

Trước khi sử dụng `spring.config.activate.on-profile`, hãy tách rõ:

1. **Active profile**: tên những môi trường/tính năng đang được kích hoạt trong `Environment`, ví dụ `dev`, `prod` hoặc `cloud`.
2. **Profile-specific file**: file được chọn theo tên profile, ví dụ `application-dev.yml`.
3. **Profile-activated document**: một phần nội dung của file được kích hoạt bởi `spring.config.activate.on-profile`.

Cả ba liên quan đến profile nhưng không đồng nhất.

### 1.1. Active profile là trạng thái của `Environment`

Bạn có thể kích hoạt profile khi chạy:

```bash
java -jar order-service.jar --spring.profiles.active=dev
```

Hoặc cung cấp biến môi trường:

```text
SPRING_PROFILES_ACTIVE=dev
```

Lúc này Spring Boot có thể nạp file profile-specific và đánh giá các tài liệu có biểu thức `on-profile` phù hợp với `dev`.

### 1.2. Profile-specific file được nhận biết qua tên

```text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
```

Khi `dev` được kích hoạt, `application-dev.yml` có thể được nạp theo quy tắc tìm Config Data; khi `prod` được kích hoạt, `application-prod.yml` được xét thay vào đó.

Trong trường hợp đơn giản, bạn không cần khai báo `spring.config.activate.on-profile` bên trong từng file đã có hậu tố profile. Tên file đã diễn đạt điều kiện chọn theo profile.

### 1.3. Profile-activated document nằm trong một file

```yaml
app:
  mode: standard

---
spring:
  config:
    activate:
      on-profile: prod

app:
  mode: strict
```

Cả hai phần cùng ở `application.yml`. Spring Boot chỉ áp dụng phần sau khi biểu thức `prod` khớp.

### 1.4. `@Profile` là điều kiện đăng ký bean

```java
@Configuration
@Profile("prod")
public class ProductionPaymentConfiguration {
    // Các bean chỉ dành cho production
}
```

`@Profile` điều kiện hóa **bean hoặc configuration class**. Ngược lại, `spring.config.activate.on-profile` điều kiện hóa **một tài liệu property**. Chúng cùng xem active profiles nhưng không thay thế nhau.

| Cơ chế | Đối tượng chịu điều kiện |
| --- | --- |
| `spring.profiles.active` | Thiết lập tập profile đang hoạt động |
| `application-prod.yml` | Chọn file cấu hình tương ứng profile |
| `spring.config.activate.on-profile` | Chọn một document trong nguồn Config Data |
| `@Profile("prod")` | Điều kiện hóa bean hoặc configuration class |
| `@ConditionalOnProperty` | Điều kiện hóa cấu hình/bean dựa trên giá trị property |

## 2. Tài liệu cấu hình nhiều phần là gì?

Một file có thể chứa **nhiều document** được ngăn cách bằng một marker. Mỗi document khai báo những property riêng. Spring Boot nạp các document có hiệu lực và kết hợp chúng theo quy tắc của hệ thống Config Data.

Ví dụ ba phần:

```text
application.yml
    |
    +-- Document 1: giá trị chung
    |
    +-- Document 2: chỉ dùng với profile dev
    |
    +-- Document 3: chỉ dùng với profile prod
```

Trong YAML, marker phân cách là dòng `---`. Trong `.properties`, Spring Boot hỗ trợ cú pháp phân cách document riêng, ví dụ `#---`.

### 2.1. File cấu hình không phải một Java bean

Các tài liệu YAML hoặc properties được đọc thành những property sources. Spring sau đó có thể sử dụng chúng để bind `@ConfigurationProperties`, giải quyết placeholder `@Value` hoặc cấu hình bean của framework.

```text
application.yml
     |
     v
Chia thành các document
     |
     v
Đánh giá điều kiện activation
     |
     v
Kết hợp các document có hiệu lực
     |
     v
Spring Environment
     |
     v
@ConfigurationProperties / @Value / auto-configuration
```

Điều kiện của một document quyết định **property nào hiện diện trong Environment**, không trực tiếp tạo hoặc hủy một bean instance.

## 3. YAML multi-document: ký hiệu `---`

Ví dụ một `application.yml` có cấu hình chung, dev và prod:

```yaml
spring:
  application:
    name: catalog-service

server:
  port: 8080

app:
  catalog:
    refresh-interval: 30m
    audit-enabled: false

---
spring:
  config:
    activate:
      on-profile: dev

server:
  port: 8081

logging:
  level:
    com.example.catalog: DEBUG

app:
  catalog:
    refresh-interval: 30s

---
spring:
  config:
    activate:
      on-profile: prod

logging:
  level:
    root: INFO

app:
  catalog:
    audit-enabled: true
```

Document đầu **không mang điều kiện profile**, nên được áp dụng khi file được nạp. Document dev chỉ có hiệu lực khi `dev` khớp, còn document prod chỉ có hiệu lực khi `prod` khớp.

### 3.1. Khi không có profile dev hoặc prod

Giả sử ứng dụng chạy mà không kích hoạt `dev` hoặc `prod`:

| Property | Giá trị từ ví dụ |
| --- | --- |
| `spring.application.name` | `catalog-service` |
| `server.port` | `8080` |
| `app.catalog.refresh-interval` | `30m` |
| `app.catalog.audit-enabled` | `false` |
| `logging.level.com.example.catalog` | Không được khai báo bởi ba document |

Không nên đồng nhất “không có active profile do người dùng đặt” với “không có profile nào được xét”: Spring có khái niệm **default profile**. Ở ví dụ này, không có document nào yêu cầu profile `default`, nên kết luận trên không thay đổi.

### 3.2. Khi profile `dev` active

Giả sử chỉ kích hoạt `dev` và không có nguồn property ưu tiên cao hơn:

| Property | Giá trị cuối cùng |
| --- | --- |
| `spring.application.name` | `catalog-service` |
| `server.port` | `8081` |
| `app.catalog.refresh-interval` | `30s` |
| `app.catalog.audit-enabled` | `false` |
| `logging.level.com.example.catalog` | `DEBUG` |

Document dev **bổ sung** property mới và **ghi đè** các key trùng của document chung.

### 3.3. Khi profile `prod` active

Giả sử chỉ kích hoạt `prod`:

| Property | Giá trị cuối cùng |
| --- | --- |
| `server.port` | `8080` |
| `app.catalog.refresh-interval` | `30m` |
| `app.catalog.audit-enabled` | `true` |
| `logging.level.root` | `INFO` |

Document dev không áp dụng. Document prod chỉ ghi đè những key nó định nghĩa; những key khác vẫn có thể lấy từ document chung.

### 3.4. Đừng đặt dấu `---` sai cấp

Marker YAML cần xuất hiện ở cấp document, trên một dòng phân cách thích hợp:

```yaml
app:
  feature: default

---
spring:
  config:
    activate:
      on-profile: test
```

Không nên thụt `---` như một phần tử con của `app`. Marker phân cách document không phải một key thuộc mapping YAML.

## 4. Multi-document trong `application.properties`

Spring Boot cũng hỗ trợ nhiều document trong một file `.properties`, bằng một marker trên dòng riêng:

```properties
spring.application.name=catalog-service
server.port=8080
app.catalog.audit-enabled=false

#---
spring.config.activate.on-profile=dev
server.port=8081
logging.level.com.example.catalog=DEBUG

#---
spring.config.activate.on-profile=prod
app.catalog.audit-enabled=true
logging.level.root=INFO
```

`#---` là marker phân tách của Spring Boot Config Data trong file `.properties`. Dấu `!` cũng có thể được dùng theo dạng `!---`.

### 4.1. Phân biệt marker `.properties` với YAML

| File | Marker thường dùng |
| --- | --- |
| `application.yml` | `---` |
| `application.properties` | `#---` hoặc `!---` |

Trong `.properties`, marker phải theo cú pháp mà Spring Boot nhận biết: đứng riêng trên dòng, không có nội dung tùy ý sau marker và không được thụt theo cách làm nó mất hiệu lực. Không tự dùng marker YAML `---` như một dòng property thông thường rồi giả định Spring Boot sẽ tách document.

Đặc biệt, các dòng comment sát marker có thể khiến cách nhận dạng separator không như mong đợi. Khi cần ghi comment giải thích, nên đặt ở đầu phần cấu hình hoặc tổ chức file rõ ràng, và giữ marker theo quy ước của Spring Boot.

### 4.2. Vì sao `spring.config.activate.on-profile` dùng dạng phẳng?

Trong `.properties`, không có indentation để diễn đạt cấu trúc:

```properties
spring.config.activate.on-profile=dev
```

Trong YAML, cấu hình tương đương:

```yaml
spring:
  config:
    activate:
      on-profile: dev
```

Cả hai đều tạo ra key có tên `spring.config.activate.on-profile`.

### 4.3. Khi nào dùng multi-document properties?

Đây là lựa chọn hợp lệ nếu nhóm đã dùng `.properties` và chỉ cần thêm một vài biến thể profile trong cùng file. Tuy nhiên, khi tài liệu dài hoặc có nhiều profile, các file riêng như `application-dev.properties` thường dễ đọc và kiểm soát hơn.

## 5. Ý nghĩa chính xác của `spring.config.activate.on-profile`

`spring.config.activate.on-profile` là một **điều kiện để document đang được đọc có được kích hoạt hay không**.

Nó không phải lời ra lệnh “bật profile này”.

Ví dụ:

```yaml
spring:
  config:
    activate:
      on-profile: staging

app:
  api:
    sandbox: true
```

Document này có nghĩa:

> Chỉ đưa `app.api.sandbox=true` vào cấu hình có hiệu lực khi biểu thức profile `staging` khớp.

Nó **không** tự kích hoạt `staging`.

### 5.1. Thứ tự tư duy đúng

```text
1. Active profiles được xác định
          |
          v
2. Spring Boot đọc các nguồn Config Data phù hợp
          |
          v
3. Mỗi document có on-profile được đánh giá
          |
          +--> Match: đưa property vào nguồn cấu hình có hiệu lực
          |
          +--> Không match: bỏ qua document đó
          |
          v
4. Hệ thống kết hợp và resolve các property
```

Đây là mô hình khái niệm: Config Data còn phải xử lý thứ tự nguồn, import, profile activation và các bước nội bộ khác. Điều quan trọng là `on-profile` **kiểm tra** profile, không **tạo** profile.

### 5.2. Đúng và sai về ý nghĩa

Sai ý định:

```yaml
spring:
  config:
    activate:
      on-profile: prod

# Không có nghĩa đoạn trên tự bật prod
```

Đúng nếu muốn chủ động bật profile qua dòng lệnh:

```bash
java -jar catalog-service.jar --spring.profiles.active=prod
```

Sau khi active profile được xác định, document `on-profile: prod` mới được xét theo điều kiện đó.

## 6. Biểu thức profile: một profile, OR, AND và NOT

`on-profile` hỗ trợ **profile expression**, không chỉ một tên profile đơn.

Ví dụ:

```yaml
spring:
  config:
    activate:
      on-profile: dev
```

Document được kích hoạt khi `dev` khớp.

### 6.1. OR: một trong nhiều profile

```yaml
spring:
  config:
    activate:
      on-profile: "dev | staging"

app:
  diagnostics:
    verbose: true
```

Document có thể áp dụng nếu `dev` **hoặc** `staging` active.

Đây là lựa chọn khi muốn dùng cùng cấu hình cho nhiều môi trường phi production.

### 6.2. AND: cần đồng thời nhiều profile

```yaml
spring:
  config:
    activate:
      on-profile: "prod & cloud"

app:
  integration:
    use-managed-identity: true
```

Document chỉ khớp khi **cả `prod` và `cloud`** cùng active.

Ví dụ `prod` biểu thị môi trường sản xuất, còn `cloud` biểu thị một lớp cấu hình hạ tầng bổ sung.

### 6.3. NOT: loại trừ một profile

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"

app:
  demo:
    enabled: true
```

Biểu thức trên khớp khi `prod` không active theo cách Spring đánh giá profile expression.

**Quan trọng trong YAML:** biểu thức bắt đầu bằng `!` phải được quote, vì `!` có ý nghĩa cú pháp riêng trong YAML.

### 6.4. Kết hợp điều kiện với ngoặc

```yaml
spring:
  config:
    activate:
      on-profile: "(dev | staging) & cloud"

app:
  observability:
    verbose: true
```

Document này khớp khi `cloud` active đồng thời với `dev` hoặc `staging`.

Để tránh nhầm lẫn về mức ưu tiên toán tử, nên đặt ngoặc rõ ràng khi biểu thức kết hợp nhiều toán tử.

### 6.5. Bảng đánh giá ví dụ

Với biểu thức `(dev | staging) & cloud`:

| Active profiles | Kết quả |
| --- | --- |
| `dev` | Không |
| `cloud` | Không |
| `dev,cloud` | Có |
| `staging,cloud` | Có |
| `prod,cloud` | Không |
| `dev,staging,cloud` | Có |

### 6.6. Cú pháp `.properties` cho biểu thức

```properties
#---
spring.config.activate.on-profile=(dev | staging) & cloud
app.observability.verbose=true
```

Trong `.properties`, toàn bộ phần bên phải dấu `=` là giá trị biểu thức. Với YAML, dùng chuỗi được quote để tránh parser hiểu nhầm ký hiệu đặc biệt.

### 6.7. Đừng trộn profile expression với điều kiện property

`on-profile` chỉ kiểm tra profile. Nếu muốn document chỉ áp dụng khi property `feature.x.enabled=true`, bạn không thể tự coi giá trị đó là một profile.

Hãy dùng `@ConditionalOnProperty` để điều kiện hóa bean, hoặc xây dựng cấu hình profile/property phù hợp. Nếu nhu cầu là điều khiển Config Data theo môi trường được Spring Boot nhận diện, xem cơ chế activation được hỗ trợ như `on-cloud-platform`.

## 7. Một ứng dụng có nhiều active profiles

Spring hỗ trợ nhiều profile active cùng lúc:

```bash
java -jar catalog-service.jar --spring.profiles.active=prod,cloud
```

Bạn có thể tổ chức cấu hình theo hai chiều:

- `prod` hoặc `dev` mô tả vòng đời triển khai.
- `cloud` hoặc `on-premise` mô tả hạ tầng.

Ví dụ:

```yaml
app:
  telemetry:
    enabled: false

---
spring:
  config:
    activate:
      on-profile: prod

app:
  telemetry:
    enabled: true

---
spring:
  config:
    activate:
      on-profile: cloud

app:
  telemetry:
    export-endpoint: "https://telemetry.example.com"

---
spring:
  config:
    activate:
      on-profile: "prod & cloud"

app:
  telemetry:
    batch-size: 1000
```

Nếu `prod,cloud` cùng active, các document phù hợp có thể đóng góp cấu hình cho cùng prefix `app.telemetry`.

| Property | Giá trị mong đợi khi `prod,cloud` |
| --- | --- |
| `app.telemetry.enabled` | `true` |
| `app.telemetry.export-endpoint` | `https://telemetry.example.com` |
| `app.telemetry.batch-size` | `1000` |

Ví dụ giả định không có nguồn cấu hình khác ghi đè. Nếu hai document cùng khai báo **cùng một key**, thứ tự và mức ưu tiên của document sẽ quyết định giá trị cuối.

### 7.1. Không nên dùng nhiều profile mơ hồ

Một tổ hợp như `dev,prod` đồng thời có thể làm nhiều document môi trường cùng khớp. Khi những document đó đều khai báo `server.port` hoặc endpoint, kết quả có thể khác ý định.

Nếu các môi trường được thiết kế loại trừ nhau, hệ thống triển khai cần đảm bảo chỉ chọn một profile môi trường chính, hoặc kiểm tra rõ ràng tính hợp lệ của tổ hợp profile.

### 7.2. Profile không phải hệ thống quyền hạn

Profile giúp chọn cấu hình và bean trong Spring; nó không thay thế authentication, authorization, phân tách secret hoặc policy triển khai. Việc `prod` active không tự khiến ứng dụng an toàn hơn.

## 8. Document sau có thể ghi đè document trước

Khi nhiều document trong **cùng một file** cùng có hiệu lực, Spring Boot xử lý chúng theo thứ tự từ trên xuống và **document xuất hiện sau có độ ưu tiên cao hơn** document trước đối với các key trùng, trong phạm vi các document đó.

Ví dụ:

```yaml
app:
  mode: base
  retries: 2

---
spring:
  config:
    activate:
      on-profile: dev

app:
  mode: debug

---
spring:
  config:
    activate:
      on-profile: dev

app:
  mode: local-override
  retries: 5
```

Khi `dev` active, cả ba document đều phù hợp và không có nguồn cao hơn:

```text
app.mode    = local-override
app.retries = 5
```

Vì document cuối cùng ghi đè các key tương ứng.

### 8.1. Có nên dựa vào nhiều document cùng profile?

Có thể, nhưng nếu một profile xuất hiện nhiều lần với các key trùng nhau, người đọc phải tìm toàn file để xác định giá trị cuối cùng.

Trong dự án thực tế, nên ưu tiên:

- Một document chung.
- Một document cho từng profile hoặc nhóm điều kiện dễ nhận biết.
- Những lớp override bổ sung có mục đích rõ.
- Hạn chế khai báo một key ở nhiều document không cần thiết.

### 8.2. Thứ tự document không thay thế thứ tự PropertySource toàn hệ thống

Document sau thắng document trước **trong cùng nguồn cấu hình** không có nghĩa nó thắng mọi nguồn khác. Biến môi trường, command-line arguments, test properties, external Config Data và các nguồn khác vẫn tham gia thứ tự ưu tiên chung của Spring Boot.

Ví dụ nếu YAML xác định `server.port=8081` nhưng command line truyền `--server.port=9000`, giá trị command line thường có độ ưu tiên cao hơn theo cấu hình Spring Boot mặc định.

## 9. Những thuộc tính không được khai báo trong document có profile activation

Đây là giới hạn quan trọng của Spring Boot Config Data hiện đại.

Các property điều khiển **chính tập profile được kích hoạt** phải được xác định trong tài liệu **không phụ thuộc một profile cụ thể**. Những property như:

- `spring.profiles.active`
- `spring.profiles.default`
- `spring.profiles.include`
- `spring.profiles.group.*`

không nên đặt trong profile-specific files hoặc các document đã có `spring.config.activate.on-profile`.

### 9.1. Ví dụ sai: tự kích hoạt profile trong một document có điều kiện

```yaml
spring:
  config:
    activate:
      on-profile: dev
  profiles:
    active: prod

app:
  mode: debug
```

Đây là cấu hình không hợp lệ theo quy tắc Config Data của các dòng Spring Boot hiện đại. Spring Boot có thể báo lỗi liên quan tới việc property kích hoạt profile bị dùng trong tài liệu profile-specific.

Về mặt ý nghĩa, cấu hình này cũng có vòng lặp khó hiểu: document chỉ được áp dụng nếu `dev` đã active, nhưng lại muốn thay đổi tập active profiles từ bên trong document đó.

### 9.2. Ví dụ đúng: active profile ở document chung

```yaml
spring:
  profiles:
    active: dev

app:
  mode: default

---
spring:
  config:
    activate:
      on-profile: dev

app:
  mode: debug
```

Ví dụ này hợp lệ về vị trí cấu hình profile. Tuy nhiên, trong một artifact triển khai nhiều môi trường, thường **không hard-code** `dev` vào file chung. Hãy truyền `SPRING_PROFILES_ACTIVE` hoặc `--spring.profiles.active` từ môi trường triển khai.

### 9.3. Ví dụ sai với `spring.profiles.include`

Không nên viết:

```yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    include: cloud
```

`spring.profiles.include` phải được khai báo ở nguồn phù hợp không phải profile-specific document.

### 9.4. Profile group cũng cần được định nghĩa đúng chỗ

Ví dụ một cấu hình chung:

```yaml
spring:
  profiles:
    group:
      production:
        - prod
        - cloud
        - metrics
```

Khi kích hoạt profile nhóm `production`, Spring Boot có thể mở rộng tập active profiles theo định nghĩa nhóm.

Không đặt khai báo nhóm này bên trong document đã có `on-profile: prod`; nhóm dùng để **xác định tập profile**, không phải một property chỉ nên xuất hiện sau khi điều kiện profile đã khớp.

## 10. Default profile và biểu thức `!prod`

Khi không khai báo active profile, Spring Framework có khái niệm **default profiles**; theo thiết lập thông thường, profile mặc định mang tên `default`.

Điều này ảnh hưởng đến document:

```yaml
spring:
  config:
    activate:
      on-profile: default

app:
  mode: local-default
```

Document này có thể được áp dụng khi ứng dụng không có active profile và profile `default` là profile mặc định.

### 10.1. Đừng nhầm `default` với document không có condition

```yaml
app:
  mode: base
```

Document trên **không cần** profile `default`; nó là document chung của file được nạp và áp dụng cả khi `dev`, `prod` hoặc profile khác active.

Ngược lại:

```yaml
spring:
  config:
    activate:
      on-profile: default
```

đặt một điều kiện profile cụ thể lên document đó.

### 10.2. `!prod` nghĩa là không có `prod` trong active/default profile evaluation

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"
```

Document có thể áp dụng cho local/dev/staging hoặc khi không có profile `prod` phù hợp.

Tuy nhiên, không nên đặt secret hoặc cài đặt nguy hiểm vào document `!prod` với giả định mọi môi trường phi production đều an toàn. Môi trường thực tế vẫn có thể mang nhiều profile, và tài liệu có điều kiện có thể hoạt động ngoài dự tính nếu tên profile bị đặt sai.

## 11. `application-{profile}.yml` so với document có `on-profile`

Hai chiến lược sau thường giải quyết cùng một bài toán.

### 11.1. Chiến lược nhiều file

```text
application.yml
application-dev.yml
application-prod.yml
```

**`application.yml`:**

```yaml
app:
  cache:
    ttl: 10m
```

**`application-dev.yml`:**

```yaml
app:
  cache:
    ttl: 10s
```

**`application-prod.yml`:**

```yaml
app:
  cache:
    ttl: 30m
```

### 11.2. Chiến lược một file multi-document

```yaml
app:
  cache:
    ttl: 10m

---
spring:
  config:
    activate:
      on-profile: dev

app:
  cache:
    ttl: 10s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  cache:
    ttl: 30m
```

### 11.3. Tiêu chí chọn

| Tiêu chí | File riêng theo profile | Multi-document cùng file |
| --- | --- | --- |
| Ít property thay đổi | Có thể hơi nhiều file | Gọn, dễ so sánh |
| Profile có nhiều cấu hình riêng | Dễ tổ chức | File dễ dài |
| Review thay đổi cho một môi trường | Tập trung vào đúng file | Phải tìm đúng document |
| Chia sẻ cấu hình chung | File cơ bản dùng chung | Document đầu dùng chung |
| Điều kiện profile phức hợp | Có thể cần tổ chức thêm | `on-profile` biểu đạt trực tiếp |
| Dễ kiểm tra trên editor | Rõ qua tên file | Cần nhận biết các separator |
| Nguy cơ trùng key | Giữa các file | Giữa các document |

Không có chiến lược nào luôn tốt hơn. Với một vài biến thể đơn giản, multi-document rất tiện. Khi mỗi môi trường có nhiều cấu hình riêng biệt hoặc cần quản lý trách nhiệm theo nhóm, file profile riêng có thể dễ bảo trì hơn.

### 11.4. Có thể kết hợp cả hai không?

Có. Một dự án có thể dùng `application.yml` chứa document chung và một số document điều kiện, đồng thời có thêm `application-prod.yml`.

Tuy nhiên, khi nhiều nguồn cùng ghi một key, cần hiểu **thứ tự ưu tiên tổng thể của Config Data**. Tránh kết hợp chỉ vì muốn “đảm bảo override” mà không có quy ước, bởi nó dễ khiến giá trị thực tế khó tìm.

## 12. List, map và hành vi ghi đè

Không phải mọi kiểu dữ liệu đều được kết hợp giống nhau khi có nhiều document.

### 12.1. Scalar property

```yaml
app:
  timeout: 10s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  timeout: 3s
```

Khi `prod` active và không có nguồn cao hơn, `app.timeout=3s`.

### 12.2. Map có thể được bind từ nhiều nguồn

```yaml
app:
  headers:
    x-client: order-service
    x-region: default

---
spring:
  config:
    activate:
      on-profile: prod

app:
  headers:
    x-region: ap-southeast
```

Khi bind vào một `Map<String, String>` theo cơ chế configuration properties, Spring Boot có thể kết hợp các entry từ nhiều property sources và dùng giá trị ưu tiên cao hơn cho key trùng.

Với ví dụ này, map có thể chứa `x-client=order-service` và `x-region=ap-southeast`.

### 12.3. List thường được thay thế, không nối thêm

```yaml
app:
  regions:
    - HCM
    - HN

---
spring:
  config:
    activate:
      on-profile: prod

app:
  regions:
    - HCM
    - DN
```

Khi `prod` active và bind `app.regions` vào `List<String>`, list từ nguồn ưu tiên cao thường **thay thế** list từ nguồn thấp hơn, thay vì hợp nhất thành bốn phần tử.

Đây là khác biệt thực tế quan trọng: nếu mong muốn vừa giữ các phần tử chung vừa bổ sung phần tử riêng, hãy thiết kế cấu hình khác hoặc kết hợp dữ liệu bằng logic rõ ràng.

### 12.4. Không dựa vào cấu trúc YAML để suy đoán merge

YAML nhìn giống cây cấu hình, nhưng Spring Boot cuối cùng xử lý các property sources và binder. Việc một node YAML được lồng dưới node khác không có nghĩa các collection luôn merge giống cấu trúc object trong JavaScript.

## 13. `spring.config.activate.on-cloud-platform` và cấu hình điều kiện khác

Spring Boot Config Data còn hỗ trợ activation dựa trên môi trường cloud platform phù hợp, ví dụ:

```yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes

app:
  discovery:
    enabled: true
```

Document chỉ được áp dụng khi điều kiện cloud platform được Spring Boot nhận diện và match. Đây là một chiều activation khác với profile.

### 13.1. Kết hợp với `on-profile`

Ví dụ:

```yaml
spring:
  config:
    activate:
      on-profile: prod
      on-cloud-platform: kubernetes

app:
  observability:
    mode: cluster
```

Trong trường hợp này, document cần thỏa **cả điều kiện profile và điều kiện cloud platform** theo cơ chế activation tương ứng.

Không nên dùng tên `kubernetes` trong `on-profile` và cho rằng Spring Boot tự động bật profile đó chỉ vì ứng dụng đang chạy trên Kubernetes. Profile và cloud-platform detection là hai cơ chế khác nhau.

### 13.2. Khi nào nên dùng?

Nếu cấu hình chỉ khác theo môi trường triển khai hạ tầng, `on-cloud-platform` có thể phù hợp. Nếu sự khác biệt do quy ước `dev`, `staging`, `prod`, `on-profile` thường trực tiếp và dễ hiểu hơn.

## 14. Cách nạp profile từ biến môi trường và command line

Ứng dụng production thường được triển khai bằng một artifact duy nhất, còn profile do hệ thống vận hành cung cấp.

### 14.1. Command-line argument

```bash
java -jar catalog-service.jar --spring.profiles.active=prod
```

Với nhiều profile:

```bash
java -jar catalog-service.jar --spring.profiles.active=prod,cloud
```

### 14.2. Biến môi trường

Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar catalog-service.jar
```

PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar catalog-service.jar
```

### 14.3. Trong Gradle hoặc IDE

Khi dùng Gradle Boot plugin phù hợp:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

Trong IDE, đưa `--spring.profiles.active=dev` vào **Program arguments** hoặc cấu hình biến môi trường phù hợp.

Không cần chép dòng lệnh trên vào mã Java. Trong production, hệ thống triển khai thường là nơi quyết định active profiles.

### 14.4. Lưu ý về độ ưu tiên

Nếu file chung ghi:

```properties
spring.profiles.active=dev
```

nhưng command line truyền:

```text
--spring.profiles.active=prod
```

thì command-line property thường có độ ưu tiên cao hơn theo cấu hình Spring Boot mặc định. Đó là một lý do nên xác định profile của môi trường triển khai bên ngoài artifact.

## 15. `spring.profiles.include` và profile groups

Hai cơ chế này giúp tổ chức nhiều profile liên quan mà không phải ghi tất cả trong mỗi lệnh khởi động.

### 15.1. `spring.profiles.include`

Ví dụ trong một document không profile-specific:

```yaml
spring:
  profiles:
    include:
      - common-metrics
```

Profile `common-metrics` được bổ sung vào tập active profiles theo quy tắc Spring Boot. Lưu ý không đặt `include` trong document được kích hoạt bằng `on-profile`.

### 15.2. Profile group

```yaml
spring:
  profiles:
    group:
      production:
        - prod
        - cloud
        - observability
```

Sau đó chạy:

```bash
java -jar catalog-service.jar --spring.profiles.active=production
```

Spring Boot có thể mở rộng `production` thành các thành viên của group để những document phù hợp được kích hoạt.

Nhóm giúp một profile “cấp cao” mang theo nhiều profile chức năng. Tuy nhiên, nhóm cần được định nghĩa **trong non-profile-specific document** để tránh điều kiện phụ thuộc vòng quanh quá trình xác định active profiles.

### 15.3. Khi nào nên dùng group, khi nào dùng expression?

- **Group:** muốn một tên profile đại diện cho nhiều profile cần được kích hoạt cùng nhau.
- **Expression:** muốn một document được áp dụng khi một tổ hợp profile đã active.

Ví dụ `production` group kích hoạt `prod,cloud`, còn document `on-profile: "prod & cloud"` chỉ **kiểm tra** rằng hai profile đó cùng có hiệu lực.

## 16. Binding vào Java: profile quyết định property, không đổi code

Xét một ứng dụng gọi API đối tác.

### 16.1. Configuration properties

```java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        URI baseUrl,
        Duration timeout,
        boolean sandbox
) {
}
```

Spring Boot 3.x có thể bind record qua constructor. Với các thế hệ cũ hơn, cách dùng immutable properties có thể yêu cầu annotation hoặc cấu hình đăng ký khác.

### 16.2. Khai báo multi-document

```yaml
app:
  partner:
    base-url: "https://sandbox.example.com"
    timeout: 5s
    sandbox: true

---
spring:
  config:
    activate:
      on-profile: prod

app:
  partner:
    base-url: "https://api.example.com"
    timeout: 2s
    sandbox: false
```

Khi `prod` không active, record nhận các giá trị sandbox từ document chung. Khi `prod` active và không có nguồn ghi đè cao hơn, record nhận endpoint production và `sandbox=false`.

### 16.3. Đăng ký bean

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

Đặt `PartnerProperties` trong package con của `com.example.orders` hoặc khai báo scan package tường minh để class được đăng ký.

### 16.4. Service không cần biết file nào đã được chọn

```java
package com.example.orders.service;

import com.example.orders.config.PartnerProperties;
import org.springframework.stereotype.Service;

@Service
public class PartnerGateway {

    private final PartnerProperties properties;

    public PartnerGateway(PartnerProperties properties) {
        this.properties = properties;
    }

    public boolean useSandbox() {
        return properties.sandbox();
    }

    public URI target() {
        return properties.baseUrl();
    }
}
```

Service chỉ phụ thuộc `PartnerProperties`. Cơ chế Config Data và binder đã xác định giá trị phù hợp trước khi service sử dụng chúng.

### 16.5. Validation cấu hình

Với dependency Jakarta Validation tương ứng:

```java
import jakarta.validation.constraints.NotNull;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        @NotNull URI baseUrl,
        @NotNull Duration timeout,
        boolean sandbox
) {
}
```

Validation giúp phát hiện cấu hình thiếu hoặc sai kiểu ở startup. Ví dụ `app.partner.timeout=abc` không thể bind hợp lệ vào `Duration`.

Đừng đặt secret trực tiếp vào record rồi log toàn bộ record, vì `toString()` của record có thể in các field nhạy cảm.

## 17. Điều kiện bean bằng `@Profile` có liên quan thế nào?

Giả sử ứng dụng cần implementation khác nhau theo môi trường:

```java
public interface NotificationSender {
    void send(String message);
}
```

```java
@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    @Profile("dev")
    public NotificationSender devNotificationSender() {
        return message -> System.out.println("DEV: " + message);
    }

    @Bean
    @Profile("prod")
    public NotificationSender prodNotificationSender() {
        return new SmtpNotificationSender();
    }
}
```

`@Profile` quyết định bean method nào được dùng để đăng ký bean. Trong khi đó, `on-profile` chọn property document tương ứng. Có thể dùng cả hai khi ứng dụng thực sự cần thay cả implementation lẫn cấu hình.

### 17.1. Không nên lạm dụng profile để chọn mọi giá trị

Nếu chỉ thay timeout và URL, thường không cần hai implementation:

```yaml
app:
  partner:
    timeout: 5s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  partner:
    timeout: 2s
```

Một `PartnerGateway` dùng `PartnerProperties` là đủ.

### 17.2. Nếu không có profile phù hợp?

Với hai bean chỉ có `@Profile("dev")` và `@Profile("prod")`, khi không có profile nào tương ứng active, có thể **không có bean `NotificationSender`**. Nếu service khác inject bắt buộc một `NotificationSender`, startup có thể thất bại.

Giải pháp có thể là cung cấp fallback hợp lệ, kiểm tra profile bắt buộc hoặc thiết kế điều kiện đúng với các môi trường mà ứng dụng hỗ trợ.

## 18. `spring.config.import` và cấu hình nhiều phần

Trong hệ thống có nhiều module hoặc nguồn cấu hình, Spring Boot có thể nhập thêm Config Data:

```yaml
spring:
  config:
    import: "optional:classpath:partner-settings.yml"
```

`optional:` cho phép nguồn có thể không tồn tại. Nếu bỏ `optional:` và không tìm thấy file bắt buộc, startup có thể thất bại.

Một nguồn được import có thể chứa nhiều document và activation condition riêng theo quy tắc Config Data.

### 18.1. Không nhầm nhập file với kích hoạt profile

`spring.config.import` yêu cầu Spring Boot xét thêm một nguồn Config Data. `spring.config.activate.on-profile` quyết định một document có hiệu lực khi profile khớp. Import một file không đồng nghĩa tự active profile được nhắc tới trong file đó.

### 18.2. Thứ tự Config Data có thể phức tạp hơn thứ tự document

Khi một file import thêm Config Data, nguồn được nhập có quy tắc về thứ tự và độ ưu tiên so với nguồn khai báo import. Nếu nhiều import và nhiều profile cùng hoạt động, việc đọc các document từ trên xuống trong một file **không đủ** để biết giá trị cuối cùng.

Hãy kiểm tra property source thực tế hoặc chạy thử với profile tương ứng, thay vì đoán bằng thứ tự tên file.

### 18.3. Các thuộc tính location phải được cung cấp đủ sớm

Những thuộc tính như:

```text
spring.config.name
spring.config.location
spring.config.additional-location
```

được dùng khi Spring Boot quyết định nơi tìm Config Data. Chúng thường cần được cung cấp từ environment variable, Java system property hoặc command-line argument ở giai đoạn khởi động sớm.

Không nên đặt chúng vào một file mà Spring Boot chưa biết cách tìm để kỳ vọng file đó tự thay đổi vị trí tìm kiếm của chính nó.

## 19. Cách kiểm chứng document nào đã được kích hoạt

Khi cấu hình sai, triệu chứng thường là:

- Một property dùng giá trị chung thay vì giá trị của profile.
- Log level không thay đổi dù đã kích hoạt `dev`.
- Endpoint hoặc port không giống môi trường mong muốn.
- Một bean với `@Profile` không xuất hiện.
- Startup thất bại vì một property điều khiển profile đặt sai tài liệu.

Hãy kiểm tra từ bên ngoài vào.

### 19.1. Xác nhận active profiles

Một `ApplicationRunner` có thể in danh sách profile:

```java
package com.example.catalog;

import java.util.Arrays;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ProfileReporter implements ApplicationRunner {

    private final Environment environment;

    public ProfileReporter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Active profiles: " +
                Arrays.toString(environment.getActiveProfiles())
        );

        System.out.println(
                "Catalog refresh interval: " +
                environment.getProperty(
                        "app.catalog.refresh-interval"
                )
        );
    }
}
```

Kết quả ví dụ khi `dev` active:

```text
Active profiles: [dev]
Catalog refresh interval: 30s
```

Đây là đầu ra minh họa khi những file cấu hình trước đó có hiệu lực và không có nguồn ưu tiên cao hơn.

### 19.2. `getActiveProfiles()` khác `getDefaultProfiles()`

Bạn có thể xem cả default profiles:

```java
System.out.println(
        Arrays.toString(environment.getDefaultProfiles())
);
```

Nếu không đặt active profile tường minh, mảng active profiles có thể rỗng trong khi `getDefaultProfiles()` chứa `default`.

Điểm này rất hữu ích khi document mang `on-profile: default` được áp dụng dù bạn không truyền `spring.profiles.active`.

### 19.3. Kiểm tra property cuối cùng

```java
String mode = environment.getProperty(
        "app.mode",
        "unknown"
);
```

Nếu mode không như mong muốn, hãy kiểm tra:

1. Active profiles thực tế.
2. File nào được Spring Boot tìm thấy.
3. Có thiếu dấu phân cách `---` hoặc `#---` không.
4. `on-profile` có đúng cú pháp và đúng điều kiện không.
5. Một document sau hoặc nguồn ưu tiên cao hơn có ghi đè key không.

### 19.4. Xem thông tin Config Data loading

Khi cần phân tích sâu, có thể tăng log cho phần tải cấu hình trong môi trường phát triển:

```properties
logging.level.org.springframework.boot.context.config=TRACE
```

Log TRACE có thể giúp quan sát những bước tìm kiếm và nạp Config Data. Hãy chỉ bật ở môi trường được kiểm soát và không ghi log nhạy cảm ra nơi không bảo vệ.

### 19.5. Actuator `/env` và `/configprops`

Nếu thêm Spring Boot Actuator và expose endpoint phù hợp:

- `/actuator/env` cung cấp thông tin về environment và property sources.
- `/actuator/configprops` cung cấp dữ liệu binding của configuration properties beans.

Các endpoint này có thể chứa tên property hoặc dữ liệu nhạy cảm. Spring Boot có cơ chế sanitization tùy phiên bản, nhưng **không nên expose công khai chỉ để debug**.

### 19.6. Khi condition là trên bean

Nếu tài liệu `on-profile` cung cấp property được dùng bởi `@ConditionalOnProperty`, bạn có thể bật `--debug` để xem **Conditions Evaluation Report** của Spring Boot.

Lưu ý: báo cáo này chủ yếu giúp giải thích quyết định condition/auto-configuration, không phải danh sách đầy đủ mọi document cấu hình đã được chọn. Để truy vết giá trị cuối, vẫn cần kiểm tra Environment và property source.

## 20. Ví dụ kiểm thử tự động theo profile

Viết test giúp giữ nguyên hành vi khi có nhiều document và profile.

### 20.1. Test với profile dev

Giả sử cấu hình trong `application.yml`:

```yaml
app:
  mode: standard
  request-timeout: 10s

---
spring:
  config:
    activate:
      on-profile: dev

app:
  mode: development
  request-timeout: 30s
```

Test bằng Spring Boot Test:

```java
package com.example.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("dev")
class DevConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void loadsDevDocument() {
        assertThat(environment.getProperty("app.mode"))
                .isEqualTo("development");
        assertThat(environment.getProperty("app.request-timeout"))
                .isEqualTo("30s");
    }
}
```

`@ActiveProfiles("dev")` thiết lập profile cho test context. Test giả định không có test property source hoặc biến môi trường ưu tiên cao hơn ghi đè những key được kiểm tra.

### 20.2. Test với profile khác

```java
@SpringBootTest
@ActiveProfiles("prod")
class ProdConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void keepsBaseValueWithoutProdOverride() {
        assertThat(environment.getProperty("app.mode"))
                .isEqualTo("standard");
    }
}
```

Ở ví dụ này chỉ có document `on-profile: dev`, nên `prod` không làm `app.mode` đổi. Nếu sau đó thêm document prod khai báo `app.mode` khác, cần cập nhật kỳ vọng test theo hợp đồng mới.

### 20.3. Kiểm tra binding theo kiểu

Bạn cũng có thể tạo record:

```java
@ConfigurationProperties(prefix = "app")
public record AppSettings(
        String mode,
        Duration requestTimeout
) {
}
```

Sau khi đăng ký configuration properties bean, test có thể assert:

```java
assertThat(settings.mode()).isEqualTo("development");
assertThat(settings.requestTimeout())
        .isEqualTo(Duration.ofSeconds(30));
```

Điều này kiểm chứng thêm bước chuyển đổi text từ Config Data thành kiểu Java, thay vì chỉ đọc chuỗi từ `Environment`.

## 21. Các lỗi thường gặp

### 21.1. Nhầm `on-profile` là lệnh active profile

```yaml
spring:
  config:
    activate:
      on-profile: prod
```

Nó **không bật** `prod`. Nếu không truyền profile hoặc không có cơ chế khác kích hoạt, document có thể bị bỏ qua.

**Cách sửa:** cung cấp `spring.profiles.active=prod` từ một nguồn hợp lệ, thường là từ môi trường triển khai.

### 21.2. Đặt `spring.profiles.active` trong document `on-profile`

Ví dụ:

```yaml
spring:
  config:
    activate:
      on-profile: dev
  profiles:
    active: prod
```

Cấu hình này vi phạm giới hạn của Spring Boot Config Data hiện đại.

**Cách sửa:** chuyển property xác định active profiles về non-profile-specific document hoặc external startup configuration.

### 21.3. Quên dấu `---`

```yaml
app:
  mode: standard

spring:
  config:
    activate:
      on-profile: dev
```

Nếu không có separator, mọi key nằm trong **cùng document**, bao gồm `app.mode=standard`. Khi document đó bị điều kiện hóa theo `dev`, cấu hình “chung” có thể bị bỏ qua ngoài dev.

**Cách sửa:** dùng `---` để tách document chung khỏi document chỉ dành cho dev.

### 21.4. Sai indentation YAML

Sai:

```yaml
spring:
  config:
  activate:
    on-profile: dev
```

`activate` không nằm dưới `config` như mong muốn.

Đúng:

```yaml
spring:
  config:
    activate:
      on-profile: dev
```

### 21.5. Không quote biểu thức bắt đầu bằng `!`

Không nên viết:

```yaml
spring:
  config:
    activate:
      on-profile: !prod
```

Dấu `!` được YAML dùng cho tag, có thể dẫn đến lỗi parser hoặc ngữ nghĩa khác.

Đúng:

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"
```

### 21.6. Dùng dấu phân cách sai trong `.properties`

Không nên copy marker YAML nguyên dạng:

```properties
server.port=8080
---
spring.config.activate.on-profile=dev
server.port=8081
```

Thay bằng:

```properties
server.port=8080

#---
spring.config.activate.on-profile=dev
server.port=8081
```

### 21.7. Hai document có cùng điều kiện và key trùng

Nếu cả hai document `on-profile: dev` đều khai báo `app.mode`, document được xử lý sau có thể thắng document trước. Lỗi không nhất thiết xuất hiện; cấu hình chỉ âm thầm dùng giá trị khác với nơi bạn đang nhìn.

**Cách sửa:** gom các key liên quan vào một nơi hoặc ghi rõ lớp override có chủ đích.

### 21.8. Cấu hình list bị mất phần tử

Document chung có ba servers, document prod chỉ khai báo một server. Sau binding list, kết quả có thể chỉ còn server trong document prod do list replacement.

**Cách sửa:** nếu toàn bộ danh sách có ý nghĩa ở prod, khai báo đầy đủ danh sách prod hoặc thiết kế một cấu trúc có quy tắc hợp nhất riêng.

### 21.9. Profile và property source bị lẫn

Bạn sửa `application.yml` nhưng process vẫn có biến môi trường hoặc command-line argument ghi đè key đó.

**Cách sửa:** kiểm tra `Environment`, Actuator và các property sources. Đừng suy luận giá trị chỉ từ một file.

### 21.10. Ghi secret thật vào document production

```yaml
spring:
  config:
    activate:
      on-profile: prod

spring:
  datasource:
    password: "real-production-secret"
```

Đoạn trên còn mắc lỗi trùng key `spring` trong cùng mapping. Dù sửa cú pháp, **không nên** commit mật khẩu thật trong file cấu hình.

Nên dùng:

```yaml
spring:
  config:
    activate:
      on-profile: prod
  datasource:
    password: "${DB_PASSWORD}"
```

Secret được cung cấp bởi môi trường triển khai hoặc secret manager. Việc dùng profile không phải cơ chế bảo vệ bí mật.

## 22. Lựa chọn cách tổ chức cho một dự án thực tế

Giả sử nhóm phát triển một REST API có các yêu cầu:

- Cấu hình chung: application name, timeout mặc định, feature flags.
- Local: dùng endpoint giả, log DEBUG, cổng 8081.
- Staging: dùng database và API thử nghiệm, log INFO.
- Production: bật auditing, log INFO và sử dụng secret từ môi trường.
- Cloud: bật một số metadata hoặc tích hợp hạ tầng bổ sung.

Có thể chọn cấu trúc:

```text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-staging.yml
└── application-prod.yml
```

và dùng một document có `on-profile: cloud` trong file chung nếu chỉ cần vài property riêng cho cloud.

Hoặc một file `application.yml` gồm:

```text
Document chung
  -> on-profile: dev
  -> on-profile: staging
  -> on-profile: prod
  -> on-profile: cloud
  -> on-profile: "prod & cloud"
```

### 22.1. Nguyên tắc để tránh cấu hình rối

1. **Đặt cấu hình chung ở document không có điều kiện.** Tránh sao chép cùng giá trị sang mọi profile.
2. **Mỗi override phải có lý do.** Đừng dùng nhiều document trùng key nếu không cần.
3. **Không dùng profile để lưu secret.** Profile chỉ lựa chọn cấu hình.
4. **Đặt tên profile có ý nghĩa ổn định.** Ví dụ `dev`, `staging`, `prod` cho môi trường và `cloud` cho tính năng triển khai.
5. **Kiểm tra tổ hợp nhiều profile.** Đặc biệt khi dùng OR, AND, NOT.
6. **Có test cho cấu hình quan trọng.** Kiểm tra endpoint, timeout và cờ nghiệp vụ của môi trường.
7. **Giữ cùng artifact giữa các môi trường.** Truyền profile, secret và cấu hình triển khai từ bên ngoài.

### 22.2. Khi nào nên tách file?

Tách thành `application-prod.yml` nếu production có hàng chục property riêng, hoặc khi nhóm vận hành cần review thay đổi production độc lập.

Giữ multi-document nếu chỉ có vài giá trị khác nhau, và việc so sánh trong một file giúp giảm thao tác.

## 23. Ví dụ tổng hợp có cấu hình nhiều phần

Tạo một ứng dụng đặt hàng sử dụng:

```text
src/main/resources/application.yml
```

Nội dung:

```yaml
spring:
  application:
    name: order-api

server:
  port: 8080

app:
  order:
    mode: normal
    max-items: 20
    timeout: 10s
    regions:
      - HCM
      - HN

---
spring:
  config:
    activate:
      on-profile: dev

server:
  port: 8081

logging:
  level:
    com.example.orders: DEBUG

app:
  order:
    mode: demo
    timeout: 30s

---
spring:
  config:
    activate:
      on-profile: staging

server:
  port: 8082

app:
  order:
    mode: preproduction
    timeout: 5s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  order:
    mode: live
    max-items: 50
    timeout: 3s

---
spring:
  config:
    activate:
      on-profile: "prod & cloud"

app:
  order:
    regions:
      - HCM
      - DN
```

### 23.1. Trường hợp `dev`

Chạy:

```bash
java -jar order-api.jar --spring.profiles.active=dev
```

Nếu không bị nguồn khác ghi đè:

```text
server.port=8081
app.order.mode=demo
app.order.max-items=20
app.order.timeout=30s
app.order.regions=[HCM, HN]
```

### 23.2. Trường hợp `prod`

Chạy:

```bash
java -jar order-api.jar --spring.profiles.active=prod
```

Giá trị:

```text
server.port=8080
app.order.mode=live
app.order.max-items=50
app.order.timeout=3s
app.order.regions=[HCM, HN]
```

### 23.3. Trường hợp `prod,cloud`

Chạy:

```bash
java -jar order-api.jar --spring.profiles.active=prod,cloud
```

Document cuối khớp và thay danh sách regions:

```text
server.port=8080
app.order.mode=live
app.order.max-items=50
app.order.timeout=3s
app.order.regions=[HCM, DN]
```

### 23.4. Java model

```java
package com.example.orders.config;

import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.order")
public record OrderProperties(
        String mode,
        int maxItems,
        Duration timeout,
        List<String> regions
) {
}
```

Bean này có thể được đăng ký qua `@ConfigurationPropertiesScan` trong ứng dụng Spring Boot. Bất kể document nào khớp, Java code chỉ nhận một model có kiểu.

### 23.5. Endpoint minh họa giá trị hiệu lực

```java
package com.example.orders.web;

import com.example.orders.config.OrderProperties;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ConfigDemoController {

    private final OrderProperties properties;

    public ConfigDemoController(OrderProperties properties) {
        this.properties = properties;
    }

    @GetMapping("/demo/config")
    public Map<String, Object> configuration() {
        return Map.of(
                "mode", properties.mode(),
                "maxItems", properties.maxItems(),
                "timeout", properties.timeout().toString(),
                "regions", properties.regions()
        );
    }
}
```

Endpoint này chỉ nên dùng cho bài thực hành, với dữ liệu không nhạy cảm. Không xây dựng endpoint public trả toàn bộ configuration object nếu object chứa password, API key hoặc thông tin hạ tầng nội bộ.

## 24. Bài tập thực hành

### Bài 1 — Tách document dev và prod

Cho cấu hình:

```yaml
server:
  port: 8080
app:
  feature:
    enabled: false
```

Hãy thêm document `dev` ghi đè cổng thành 8081 và bật feature; thêm document `prod` giữ cổng 8080 nhưng bật feature. Dùng `spring.config.activate.on-profile` ở đúng vị trí.

### Bài 2 — Viết lại bằng `.properties`

Chuyển Bài 1 sang `application.properties` với marker `#---`. Kiểm tra mỗi phần có những key cần thiết và giải thích vì sao `---` đứng riêng không phải cú pháp separator của `.properties`.

### Bài 3 — Đánh giá profile expression

Cho:

```yaml
spring:
  config:
    activate:
      on-profile: "(dev | staging) & cloud"
```

Hãy tính kết quả với:

- `dev`
- `staging,cloud`
- `prod,cloud`
- `dev,cloud`
- `dev,prod,cloud`

Sau đó viết biểu thức “mọi môi trường không có prod” và giải thích vì sao giá trị `!prod` phải được quote trong YAML.

### Bài 4 — Phân tích thứ tự document

Một file có ba document:

```yaml
app:
  mode: base

---
spring:
  config:
    activate:
      on-profile: dev
app:
  mode: debug

---
spring:
  config:
    activate:
      on-profile: dev
app:
  mode: local
```

Dự đoán `app.mode` khi `dev` active và không có nguồn ghi đè khác. Vì sao? Đổi thứ tự hai document dev rồi dự đoán lại.

### Bài 5 — Phát hiện khai báo không hợp lệ

Kiểm tra:

```yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    include: audit
```

Giải thích vì sao không nên đặt `spring.profiles.include` trong document có điều kiện profile. Sửa bằng cách đưa include hoặc group vào một non-profile-specific document thích hợp.

### Bài 6 — Multi-profile configuration

Tạo:

- Một document chung có `app.metrics.enabled=false`.
- Một document `prod` bật metrics.
- Một document `cloud` định nghĩa metrics endpoint.
- Một document `"prod & cloud"` định nghĩa batch size.

Chạy với `prod`, `cloud` và `prod,cloud`. Ghi lại các property xuất hiện ở mỗi trường hợp.

### Bài 7 — List không nối thêm

Document chung có:

```yaml
app:
  nodes:
    - node-a
    - node-b
```

Document prod có:

```yaml
app:
  nodes:
    - node-prod
```

Bind vào `List<String>` và kiểm tra kết quả với profile prod. Vì sao không nên kỳ vọng danh sách gồm cả ba node?

### Bài 8 — Default profile

Tạo một document:

```yaml
spring:
  config:
    activate:
      on-profile: default
```

và thêm property `app.mode=local-default`. Khởi động không truyền active profile, rồi chạy với `--spring.profiles.active=dev`.

So sánh kết quả và phân biệt document `default` với document không có activation.

### Bài 9 — Kiểm tra bằng test

Viết hai test:

```java
@SpringBootTest
@ActiveProfiles("dev")
class DevConfigTest {
}
```

```java
@SpringBootTest
@ActiveProfiles("prod")
class ProdConfigTest {
}
```

Inject `Environment` hoặc configuration properties bean để xác nhận timeout và mode phù hợp. Khi test thất bại, kiểm tra profile, document separator và các nguồn cấu hình ưu tiên cao.

### Bài 10 — Chọn cách tổ chức file

Một ứng dụng có ba profile và mỗi profile chỉ khác năm property. Một ứng dụng khác có sáu môi trường, nhiều secrets, hơn một trăm property riêng. Hãy đề xuất dùng multi-document hay tách file, nêu lý do về review, độ phức tạp và cách bảo vệ secret.

## 25. Tổng kết

`spring.config.activate.on-profile` **không kích hoạt profile**; nó **điều kiện hóa việc nạp một document cấu hình** dựa trên profile đã được xác định. Spring Boot hỗ trợ multi-document YAML với `---` và multi-document `.properties` với marker như `#---`.

Trong một file, document có hiệu lực xuất hiện sau có thể ghi đè key ở document trước. Tuy nhiên, còn có thứ tự ưu tiên rộng hơn của Config Data, biến môi trường, command-line arguments và các nguồn khác. Với list được bind từ nhiều nguồn, hãy nhớ rằng nguồn có ưu tiên cao thường thay thế cả danh sách thay vì nối các phần tử.

Các property quyết định chính tập active profiles — như `spring.profiles.active`, `spring.profiles.include` và profile groups — cần được đặt trong **non-profile-specific document**, không phải trong document đã có `on-profile` hoặc file profile-specific.

Khi thiết kế cấu hình theo môi trường, hãy dùng một document chung cho giá trị mặc định, chỉ ghi đè những key cần thay đổi, đặt biểu thức profile rõ ràng, không đưa secret thật vào file và xác nhận cấu hình cuối cùng qua `Environment`, configuration properties và test. Hiểu đúng mối liên hệ giữa **active profile**, **profile-specific file** và **profile-activated document** giúp ứng dụng Spring Boot dễ triển khai, dễ chẩn đoán và ít sai lệch giữa các môi trường.

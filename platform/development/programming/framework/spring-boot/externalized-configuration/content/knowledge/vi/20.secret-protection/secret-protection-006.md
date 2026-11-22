# Ẩn giá trị khi chẩn đoán bằng Actuator env và configprops

## 1. Bài toán: cần quan sát cấu hình nhưng không được làm lộ bí mật

Khi ứng dụng Spring Boot hoạt động ở môi trường thật, người vận hành thường cần biết:

- Profile nào đang được kích hoạt?
- Vì sao một bean nhận endpoint khác với `application.yml`?
- Một cấu hình đến từ biến môi trường, tham số dòng lệnh hay file Config Data?
- Đối tượng `@ConfigurationProperties` đã bind những trường nào?
- Một giá trị bị ghi đè bởi nguồn có ưu tiên cao hơn hay chưa?

Spring Boot Actuator cung cấp những endpoint hỗ trợ chẩn đoán. Hai endpoint liên quan trực tiếp đến cấu hình ngoài là:

- **`/actuator/env`**: thông tin thuộc `ConfigurableEnvironment` và các `PropertySource`.
- **`/actuator/configprops`**: các bean có cấu hình được liên kết bằng `@ConfigurationProperties`.

Nhưng cấu hình ứng dụng không chỉ gồm host, cổng và timeout. Nó có thể mang những dữ liệu rất nhạy cảm: password, token, khóa API, URI có thông tin xác thực, mật khẩu database, khóa ký, chuỗi kết nối hoặc các giá trị riêng của hạ tầng.

Giả sử ứng dụng được cấp cấu hình:

```yaml
inventory:
  endpoint: https://inventory.example.invalid/api
  connect-timeout: 2s
  api-token: "DO_NOT_USE_REAL_SECRET_IN_EXAMPLES"

spring:
  datasource:
    username: app_user
    password: "DO_NOT_USE_REAL_PASSWORD_IN_EXAMPLES"
```

Người vận hành có thể cần xác nhận `inventory.connect-timeout` đã được nạp, nhưng **không có lý do để một trang chẩn đoán công khai trả lại `inventory.api-token` hoặc `spring.datasource.password`**.

Trong các thế hệ Spring Boot hiện đại, Actuator **ẩn giá trị (sanitize/redact)** ở `env` và `configprops` theo mặc định. Giá trị được thay bằng chuỗi đại diện như `******`. Tên thuộc tính, thông tin nguồn hoặc cấu trúc bean vẫn có thể xuất hiện tùy endpoint và phiên bản.

Bài học này giải thích cách hiểu việc che giá trị, cách điều khiển `show-values`, cách giới hạn người có quyền xem, cách kiểm tra kết quả và những giới hạn của cơ chế che giá trị. Mục tiêu không phải “làm sao mở hết thông tin”, mà là **chẩn đoán được vấn đề cần thiết với quyền truy cập tối thiểu**.

## 2. Ba lớp bảo vệ phải tách biệt

Một sai lầm phổ biến là nghĩ rằng chỉ cần `show-values: never` là endpoint an toàn tuyệt đối, hoặc chỉ cần đặt endpoint sau màn hình đăng nhập là không còn nguy cơ lộ bí mật.

Thực tế có **ba quyết định độc lập**:

1. **Endpoint có tồn tại và được expose không?** Tùy access/enablement và `management.endpoints.web.exposure.*` hoặc JMX.
2. **Ai được gọi endpoint?** Tùy Spring Security, reverse proxy, mTLS, IAM, mạng quản trị và quy tắc phân quyền.
3. **Giá trị nào được hiển thị khi endpoint trả lời?** Tùy `management.endpoint.env.show-values`, `management.endpoint.configprops.show-values` và các `SanitizingFunction` nếu được cấu hình.

Sơ đồ:

```text
Client / operator
       |
       v
Có thể kết nối tới management interface?
       |
       v
Endpoint có được enable/access và expose?
       |
       v
Security cho phép request?
       |
       v
Actuator thu thập thông tin cấu hình
       |
       v
Áp dụng show-values + sanitization
       |
       v
HTTP/JMX response tới client
```

Không nên đánh đồng:

- **`404 Not Found`**: endpoint có thể không được expose, không được đăng ký hoặc đường dẫn không đúng.
- **`401 Unauthorized`**: request cần xác thực.
- **`403 Forbidden`**: đã xác thực nhưng không được phép truy cập.
- **`200 OK` với giá trị `******`**: endpoint truy cập được, nhưng giá trị đã bị che.
- **`200 OK` với giá trị thực**: có thể là chủ đích cho tài khoản được phép, cũng có thể là lỗi bảo mật nghiêm trọng.

Một response đã được che không có nghĩa danh sách tên khóa, tên property source, tên bean, đường dẫn file hoặc cấu trúc môi trường đều vô hại. Chính **metadata** đôi khi cũng tiết lộ chi tiết kiến trúc và cách triển khai.

## 3. Định nghĩa env endpoint

`env` là Actuator endpoint cung cấp góc nhìn vào `ConfigurableEnvironment`. Trong Spring Boot, cấu hình từ nhiều nguồn được sắp xếp thành một danh sách `PropertySource` có thứ tự ưu tiên.

Một response dạng khái quát có thể chứa:

```json
{
  "activeProfiles": ["prod"],
  "propertySources": [
    {
      "name": "systemEnvironment",
      "properties": {
        "INVENTORY_API_TOKEN": {
          "value": "******"
        }
      }
    }
  ]
}
```

Đây chỉ là cấu trúc minh họa; tên và định dạng chi tiết của response có thể khác theo phiên bản, property source và hình thức truy vấn. Giá trị `******` là biểu diễn đã được sanitize, không phải token thật.

`env` hữu ích để quan sát:

- Profile đang hoạt động và profile mặc định.
- Danh sách những nguồn thuộc tính đang tham gia.
- Giá trị hoặc thông tin về một khóa đã được cung cấp.
- Nguồn cung cấp giá trị và, ở một số trường hợp, nguồn gốc (*origin*) của property.
- Cách nhiều nguồn cùng khai báo một khóa và thứ tự chúng được xét.

Ví dụ endpoint truy vấn một property cụ thể:

```text
GET /actuator/env/inventory.connect-timeout
```

Đây là **đường dẫn đọc cấu hình**, không phải API cập nhật giá trị. Truy vấn một khóa cụ thể làm kết quả dễ tập trung hơn nhưng **không tự bỏ qua quy tắc bảo mật và sanitization**.

### 3.1. env không giống việc đọc nguyên file YAML

Actuator `env` không đơn giản là trả toàn bộ nội dung `application.yml`. Nó nhìn vào hệ thống `Environment` sau khi các nguồn cấu hình đã được tổ chức, có thể có biến môi trường, command-line args, system properties và nguồn do thư viện thêm vào.

Vì vậy:

```text
Giá trị trong application.yml          = localhost
Giá trị biến môi trường                 = inventory.internal
Giá trị thực tế được resolver lựa chọn = inventory.internal
```

Nếu hai nguồn cùng khai khóa, cần xem thứ tự và giá trị có hiệu lực. Nhưng khi `show-values=never`, endpoint có thể không trả các giá trị gốc. **Chẩn đoán bằng nguồn và metadata không yêu cầu phải mở toàn bộ bí mật**.

## 4. Định nghĩa configprops endpoint

`configprops` trình bày những bean được Spring Boot quản lý và liên kết qua `@ConfigurationProperties`.

Ví dụ:

```java
package com.example.inventory;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "inventory")
public record InventoryProperties(
        URI endpoint,
        Duration connectTimeout,
        String apiToken
) {}
```

Và đăng ký:

```java
@SpringBootApplication
@EnableConfigurationProperties(InventoryProperties.class)
public class InventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
```

Khi context khởi động, Binder có thể nhận:

```yaml
inventory:
  endpoint: https://inventory.example.invalid/api
  connect-timeout: 2s
  api-token: "DO_NOT_USE_REAL_SECRET_IN_EXAMPLES"
```

`configprops` cung cấp góc nhìn vào **object cấu hình và thông tin binding**, chứ không chỉ từng entry thô của `PropertySource`. Một response có thể có các nhánh như `contexts`, `beans`, `prefix`, `properties` và `inputs`. Trong cách cấu hình mặc định hiện đại, những giá trị nhạy cảm được trình bày đã qua sanitization.

**Điểm khác biệt:**

| Khía cạnh | `env` | `configprops` |
| --- | --- | --- |
| Tập trung vào | Nguồn thuộc tính thuộc `Environment` | Bean `@ConfigurationProperties` |
| Câu hỏi thường gặp | “Khóa này đến từ nguồn nào?” | “Object cấu hình đã bind ra sao?” |
| Có thể thể hiện | PropertySource, profile, origin | Prefix, bean, trường và input binding |
| Cơ chế ẩn giá trị | `management.endpoint.env.show-values` | `management.endpoint.configprops.show-values` |
| Rủi ro | Lộ token, password, nguồn hạ tầng | Lộ dữ liệu trong object đã bind và cấu trúc ứng dụng |

Cả hai đều phục vụ chẩn đoán, không được coi là nơi công khai inventory các bí mật của hệ thống.

## 5. Thêm Spring Boot Actuator vào ứng dụng

Với Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Với Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Với Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
```

Những đoạn trên giả định phiên bản dependency được Spring Boot parent, BOM hoặc plugin quản lý theo dự án. Không cần thêm phiên bản riêng tùy tiện cho Actuator nếu đã quản lý dependency nhất quán.

Sau khi có Actuator, các endpoint có thể được auto-configure nhưng **không có nghĩa tất cả endpoint lập tức truy cập được qua HTTP**.

Trong cấu hình mặc định của nhiều phiên bản Spring Boot hiện đại, **chỉ health được expose qua HTTP và JMX**; `env` và `configprops` cần được expose có chủ đích nếu muốn gọi từ bên ngoài. Cấu hình access/enablement có thể ảnh hưởng thêm tới sự hiện diện của endpoint.

## 6. Baseline bảo mật: mặc định không expose env và configprops

Với production, một cấu hình khởi đầu bảo thủ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
    jmx:
      exposure:
        include: "health"

  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Các điểm đáng chú ý:

- Chỉ yêu cầu expose `health` và `info` qua HTTP trong ví dụ.
- Không có `env` hay `configprops` trong danh sách web exposure.
- Chỉ expose health qua JMX trong ví dụ.
- `show-values: never` được khai tường minh như một chính sách phòng vệ để tránh hiện giá trị khi ai đó thay exposure sau này.
- Đây **không phải** lý do để cho phép bất kỳ ai truy cập các endpoint còn lại; health/info cũng cần cân nhắc mức chi tiết và môi trường truy cập.

Nếu không cần `info` trong production, có thể giữ danh sách chỉ `health`.

### 6.1. show-values: never không tự tắt endpoint

Giả sử thay:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,env,configprops"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Lúc này, `env` và `configprops` được đề nghị expose qua HTTP trong điều kiện chúng được cho phép và có hạ tầng web phù hợp. Việc đặt `show-values: never` **không biến endpoint thành 404**; nó chỉ điều khiển cách trình bày giá trị.

Ngay cả khi giá trị là `******`, một response có thể vẫn bộc lộ tên property, cấu trúc bean, profile hoặc tên nguồn cấu hình. Vì vậy phải bảo vệ endpoint như một tài nguyên quản trị.

### 6.2. Exposure khác access

Các phiên bản Spring Boot mới hỗ trợ thêm cấu hình access chi tiết cho endpoint, chẳng hạn giới hạn quyền đọc hoặc đặt `none`. Những cơ chế như `management.endpoint.<id>.access` và giới hạn toàn cục có thể khác theo phiên bản.

Khi bảo vệ một ứng dụng đang triển khai, cần đối chiếu documentation đúng phiên bản:

- **Endpoint có được phép tồn tại không?**
- **Nó được expose qua kênh nào?**
- **Người nào được phép gọi?**
- **Khi trả lời thì dữ liệu được che đến đâu?**

Không dùng một thiết lập duy nhất như giải pháp thay thế cho tất cả các câu hỏi trên.

## 7. show-values: ba chế độ quyết định cách hiện dữ liệu

Hai cấu hình trung tâm:

```properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

Có ba giá trị thường được Spring Boot hỗ trợ:

| Giá trị | Ý nghĩa khi endpoint trả dữ liệu | Mức độ thận trọng |
| --- | --- | --- |
| `never` | Luôn sanitize giá trị, thường thành `******` | Lựa chọn mặc định/bảo thủ |
| `when-authorized` | Hiển thị giá trị gốc cho người được coi là authorized, trừ những giá trị còn bị custom sanitizer che | Chỉ dùng khi thật sự cần và có phân quyền chặt |
| `always` | Cho phép hiện giá trị gốc đối với mọi người gọi được endpoint, trừ trường hợp bị custom sanitizer che | Rủi ro cao, tránh dùng trên hệ thống thật |

Dạng YAML:

```yaml
management:
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Trong các bản Spring Boot 3.x/4.x hiện đại, mặc định là `never`. Các ví dụ dùng chữ thường/kebab-case cho giá trị để dễ đọc. Tài liệu các bản cũ có thể trình bày dạng enum viết hoa như `NEVER`, `WHEN_AUTHORIZED`, `ALWAYS`; cần xem đúng phiên bản ứng dụng khi đối chiếu.

**Quan trọng:** cả `env` lẫn `configprops` đều có thiết lập riêng. Đổi `env.show-values` không nhất thiết đổi chính sách của `configprops`.

### 7.1. never: mặc định che toàn bộ value

Với:

```yaml
management:
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Giá trị được sanitize dù người gọi đã đăng nhập, miễn là endpoint được triển khai theo hành vi chuẩn của phiên bản Spring Boot tương ứng.

Ví dụ response minh họa:

```json
{
  "name": "systemEnvironment",
  "properties": {
    "WAREHOUSE_API_TOKEN": {
      "value": "******"
    },
    "WAREHOUSE_CONNECT_TIMEOUT": {
      "value": "******"
    }
  }
}
```

Thậm chí các giá trị không nhạy cảm như timeout cũng có thể bị che. Đây là đánh đổi có chủ đích: **bảo vệ dữ liệu ưu tiên hơn việc trả tất cả thông tin để tiện gỡ lỗi**.

Cơ chế này không xóa secret khỏi `Environment`, không ngăn bean sử dụng secret và không mã hóa dữ liệu gốc; nó chỉ ảnh hưởng tới representation của những endpoint được sanitize.

### 7.2. when-authorized: có điều kiện theo người gọi

Ví dụ:

```properties
management.endpoint.env.show-values=when-authorized
management.endpoint.env.roles=ACTUATOR_ADMIN
management.endpoint.configprops.show-values=when-authorized
management.endpoint.configprops.roles=ACTUATOR_ADMIN
```

Khi Spring Boot xác định người gọi HTTP đã xác thực và có role phù hợp, giá trị **có thể** được hiện nguyên bản. Nếu không, giá trị vẫn được sanitize, miễn là request được phép đi đến endpoint.

Đây là lựa chọn cho một quy trình vận hành thực sự cần xem giá trị, nhưng không tự cung cấp toàn bộ cơ chế security. Phải cấu hình xác thực, phân quyền, network và kiểm soát logging riêng.

### 7.3. always: vì sao cần tránh

```properties
management.endpoint.env.show-values=always
management.endpoint.configprops.show-values=always
```

Nếu một người gọi đi tới được endpoint, các giá trị có thể xuất hiện nguyên bản, kể cả các khóa không được custom sanitizer che.

Nguy cơ:

- Một lỗi cấu hình reverse proxy có thể expose endpoint ra Internet.
- Một tài khoản chỉ có quyền quan sát có thể đọc credential của dịch vụ khác.
- Công cụ theo dõi có thể lưu nguyên JSON vào hệ thống log hoặc ticket.
- Sao chép response để báo lỗi có thể chuyển secret sang kênh không phù hợp.
- Những giá trị đặt dưới tên khóa không có chữ `password` hay `token` vẫn có thể là secret.

Vì thế, **không dùng `always` làm “cách gỡ lỗi nhanh” trên production**. Với demo cục bộ, nếu thật sự cần minh họa chế độ này, chỉ sử dụng giá trị giả, một tiến trình cô lập và không có dữ liệu nhạy cảm thực.

## 8. when-authorized: roles là gì?

Theo cơ chế Actuator được tài liệu Spring Boot mô tả:

- Với **HTTP endpoint**, “authorized” liên quan đến trạng thái đã xác thực và vai trò được cấu hình cho endpoint.
- Nếu chưa khai báo `roles`, theo cấu hình phù hợp, **bất kỳ người dùng đã xác thực** có thể được coi là authorized để xem giá trị.
- Nếu khai báo `roles`, chỉ người đáp ứng role tương ứng mới được coi là authorized.
- Với **JMX endpoint**, tài liệu Actuator mô tả người dùng luôn được xem là authorized khi xét `show-values=when-authorized`. Vì vậy không thể dùng riêng tùy chọn `roles` để giả định JMX che giá trị như HTTP.

Ví dụ:

```yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles: "ACTUATOR_ADMIN"

    configprops:
      show-values: when-authorized
      roles: "ACTUATOR_ADMIN"
```

Ý định: role `ACTUATOR_ADMIN` là nhóm người vận hành được phép xem dữ liệu cấu hình trong quy trình được quản lý.

**Lưu ý cách diễn giải role:** trong Spring Security, `hasRole("ACTUATOR_ADMIN")` thường tương ứng authority `ROLE_ACTUATOR_ADMIN` theo quy ước tiền tố `ROLE_`. Tuy nhiên, cơ chế cấp authorities thực tế phụ thuộc cấu hình security. Hãy test bằng một principal thật của ứng dụng và kiểm chứng cùng giá trị `roles` có tác dụng đúng.

### 8.1. Không đặt roles nghĩa là không có phân quyền?

Không hẳn. Vẫn có một lớp security kiểm soát **truy cập endpoint**. Nhưng với `when-authorized`, nếu không quy định role cụ thể, việc “đã đăng nhập” có thể đủ để **xem giá trị gốc** trong HTTP response.

Đó là lý do không nên cấu hình:

```properties
management.endpoint.env.show-values=when-authorized
```

rồi cho rằng chỉ tài khoản admin mới xem được. Cần kiểm tra định nghĩa authorized và áp dụng cả role tại endpoint lẫn policy truy cập HTTP phù hợp.

### 8.2. Bị từ chối request khác với nhận dữ liệu che

Giả sử một security chain quy định **chỉ ACTUATOR_ADMIN** mới truy cập `/actuator/env`. Người dùng thường sẽ nhận 401/403, không nhất thiết nhận response 200 với mọi value đã che.

Trong cấu hình khác cho phép cả operator đọc endpoint, nhưng `show-values=when-authorized` chỉ coi admin là authorized để xem value, operator có thể nhận response đã sanitize.

Hai trường hợp đều có thể phù hợp với mục tiêu bảo vệ bí mật. Điều cần làm là thiết kế và kiểm thử **cả mã trạng thái HTTP lẫn nội dung response**.

## 9. Vấn đề quan trọng: JMX không giống HTTP

Một quan niệm sai dễ gây rủi ro:

> “Đã đặt `show-values=when-authorized` và `roles=ACTUATOR_ADMIN`, nên mọi đường truy cập actuator đều bảo vệ dữ liệu giống HTTP.”

Trong các tài liệu Actuator hiện đại, đối với **JMX**, người dùng được coi là authorized khi xét tùy chọn `when-authorized`. Do đó, cách cấu hình role được thiết kế cho HTTP **không phải bảo đảm tương đương trên JMX**.

Nếu không cần chẩn đoán qua JMX, không expose `env` và `configprops` qua JMX:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: "health"
```

Nếu môi trường thực sự cần JMX, phải bảo vệ giao diện quản lý JMX/RMI bằng cấu hình xác thực, mạng tin cậy, firewall/TLS và quyền truy cập phù hợp. Không xem `management.endpoint.env.roles` là cơ chế bảo vệ JMX từ đầu đến cuối.

Khuyến nghị an toàn cho nhiều ứng dụng:

- Expose càng ít endpoint qua JMX càng tốt.
- Giữ `show-values: never` nếu không cần xem raw value.
- Chỉ sử dụng `when-authorized` khi đã kiểm soát mọi kênh truy cập liên quan, không riêng HTTP.
- Trong audit bảo mật, kiểm tra cả web và JMX exposure, không chỉ một danh sách.

## 10. Cấu hình profile riêng cho chẩn đoán cục bộ

Thay vì expose `env` và `configprops` ở production thường trực, có thể bật chúng trong một profile chẩn đoán cô lập.

File chung `application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
    jmx:
      exposure:
        include: "health"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

File `application-local-observability.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,env,configprops"

  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Khởi động cho mục đích demo, ví dụ:

```bash
java -jar app.jar --spring.profiles.active=local-observability
```

Kỳ vọng:

- `/actuator/env` và `/actuator/configprops` chỉ được expose trong điều kiện profile cùng những nguồn khác không ghi đè policy.
- Các giá trị vẫn bị che bởi `show-values: never`.
- Không cần đưa token thật vào cấu hình.
- Người học có thể quan sát tên khóa và cấu trúc binding mà không vô tình in giá trị gốc.

**Đừng coi từ `local` trong tên profile là một biện pháp bảo mật.** Người vận hành vẫn có thể bật nhầm profile ở môi trường khác qua `spring.profiles.active`. Chính sách mạng, security và deployment mới xác định endpoint có truy cập từ đâu.

Nếu production tuyệt đối không được expose hai endpoint, nên có guardrail ở cấu hình triển khai, policy hoặc test kiểm tra exposure, chứ không chỉ dựa vào quy ước đặt tên profile.

## 11. Bảo vệ endpoint bằng Spring Security

Đối với web application có Spring Security, phải cấu hình quyền truy cập Actuator rõ ràng nếu muốn expose các endpoint chẩn đoán.

Một ví dụ Spring Boot 3.x, Spring Security 6.x cho ứng dụng Servlet:

```java
package com.example.security;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ActuatorSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorChain(HttpSecurity http)
            throws Exception {

        http.securityMatcher(EndpointRequest.toAnyEndpoint());

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("ACTUATOR_ADMIN"));

        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());

        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Ý nghĩa:

- Security chain đầu áp dụng cho Actuator endpoint qua `EndpointRequest`.
- Chỉ principal có role `ACTUATOR_ADMIN` được phép truy cập những endpoint đó.
- Security chain thứ hai xử lý phần ứng dụng còn lại và yêu cầu xác thực trong ví dụ.
- Đây là cấu hình minh họa, không phải chính sách production hoàn chỉnh cho tất cả API. Tùy ứng dụng, cần OAuth2 resource server, session, CSRF, quản lý identity, CORS và cơ chế ủy quyền phù hợp.
- Cần có cơ chế cấp user/role an toàn. **Không thêm tài khoản admin với mật khẩu hard-code vào source code** chỉ để làm ví dụ.

**Cẩn trọng phiên bản:** package của `EndpointRequest` trong Spring Boot 4 có thể khác Spring Boot 3. Ví dụ các bản Boot 4.x chuyển API này sang namespace liên quan đến `org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest`. Hãy dùng import tương ứng với phiên bản dependency đang build, không copy một import cũ nếu IDE báo không tồn tại.

### 11.1. Khi có SecurityFilterChain tự định nghĩa

Spring Boot thường tự cung cấp security cho Actuator khi Spring Security có trên classpath và ứng dụng **không** tự cung cấp `SecurityFilterChain`. Nếu dự án đã có một hoặc nhiều chain tự định nghĩa, phần auto-configuration bảo mật Actuator có thể nhường quyền điều khiển cho dự án.

Điều này tạo nguy cơ: sau khi thêm `management.endpoints.web.exposure.include=env,configprops`, một chain cũ với quy tắc `permitAll()` quá rộng có thể khiến endpoint bị truy cập ngoài ý định.

Vì vậy phải đọc policy security của ứng dụng thực tế và viết test từ phía HTTP client. **Đừng kết luận “có Spring Security trên classpath là env đã an toàn”** khi dự án đã custom security.

### 11.2. Tách cổng quản trị

Một lựa chọn tăng cô lập:

```properties
management.server.port=9091
management.server.address=127.0.0.1
```

Đây là ví dụ về việc bind management interface trên loopback để chỉ các tiến trình cùng máy truy cập được theo mô hình mạng đơn giản. Với container/Kubernetes, `127.0.0.1` có phạm vi trong network namespace của container và có thể làm hỏng cách scrape của hệ thống giám sát nếu thiết kế không phù hợp.

Vì vậy phải điều chỉnh theo môi trường và kiểm tra route mạng thật:

- Chỉ expose endpoint cần thiết.
- Bảo vệ cổng management bằng network policy/firewall hoặc dịch vụ proxy nội bộ.
- Dùng TLS khi truyền dữ liệu nhạy cảm qua kết nối mạng.
- Xác thực và phân quyền đối với endpoint có nguy cơ.
- Không công khai cổng management chỉ vì app chính đang cung cấp API công khai.

**Tách port không thay thế authentication.** Nếu port quản trị bị forward hoặc publish nhầm, thông tin vẫn có thể bị truy cập.

## 12. Thiết lập policy thận trọng cho env và configprops

Một baseline minh họa khi **buộc phải** expose hai endpoint qua web nội bộ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,env,configprops"
    jmx:
      exposure:
        include: "health"

  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Kèm yêu cầu vận hành:

1. Chỉ cho phép nguồn truy cập từ mạng quản trị.
2. Bảo vệ qua Spring Security hoặc lớp xác thực tương đương.
3. Giữ `never` kể cả với admin nếu nhu cầu chỉ là xác định tên khóa/nguồn.
4. Không tự ghi response ra log hoặc kho giám sát không có phân quyền.
5. Không lưu secret dưới dạng hard-code trong repository để “dễ chẩn đoán”.

Nếu cần xem một giá trị **không nhạy cảm** như timeout, thường có cách tốt hơn là tạo thông tin chẩn đoán có kiểm soát, chẳng hạn health detail hoặc metric chỉ biểu diễn thông số an toàn, thay vì mở toàn bộ `env` bằng `always`.

## 13. Cho phép admin xem giá trị trong tình huống giới hạn

Khi một sự cố thật sự đòi hỏi biết giá trị của một số thuộc tính, có thể cân nhắc:

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
      show-values: when-authorized
      roles: "ACTUATOR_ADMIN"
    configprops:
      show-values: when-authorized
      roles: "ACTUATOR_ADMIN"
```

Nhưng cần hiểu hệ quả: **admin được phép có thể nhìn thấy cả secret**, trừ những giá trị còn bị `SanitizingFunction` tùy chỉnh che. Chỉ nên áp dụng nếu mức truy cập này thật sự được phê duyệt.

Trong thực tế, việc có tài khoản “admin ứng dụng” không tự đồng nghĩa người đó cần đọc password DB hoặc signing key. Đôi khi một principal vận hành chỉ cần quan sát tình trạng và tên nguồn; quyền đọc raw secret nên nằm ở một quy trình bí mật được kiểm soát riêng.

Các bảo vệ đi kèm:

- Mạng quản trị hoặc đường hầm được kiểm soát.
- Xác thực mạnh và role riêng cho endpoint.
- Giới hạn thời gian/phạm vi quyền truy cập.
- Audit truy cập theo quy định của tổ chức.
- Tránh ghi response chứa secret vào terminal history, ticket, log hoặc chat.
- Thu hồi quyền/tắt exposure sau đợt chẩn đoán nếu chỉ bật tạm thời.

Không “tạm bật” `always` chỉ vì `when-authorized` chưa hoạt động. Khi role check không đúng, cần sửa security configuration và test thay vì bỏ lớp bảo vệ.

## 14. Vì sao custom SanitizingFunction vẫn quan trọng?

Ở các phiên bản Spring Boot hiện đại, tài liệu Actuator mô tả một extension point tên **`SanitizingFunction`**.

Ý nghĩa: dù `show-values` cho phép hiển thị dữ liệu với người được phép, một `SanitizingFunction` tùy chỉnh vẫn có thể **che những giá trị cụ thể** theo tên khóa, nguồn hoặc tiêu chí phù hợp.

Ví dụ, ứng dụng muốn tuyệt đối không hiển thị các giá trị liên quan đến:

```text
internal-signing-material
client-private-credential
integration-authorization
partner-api-key
```

kể cả khi admin đang dùng `when-authorized`. Một sanitizer riêng có thể đảm nhiệm quy tắc đó.

Lưu ý: `SanitizingFunction` là **extension của quá trình serialize endpoint**, không phải giải pháp mã hóa dữ liệu lưu trữ, che secret khỏi heap memory, hay bảo vệ khỏi mọi hình thức log.

### 14.1. Ví dụ SanitizingFunction bean

Với các bản Spring Boot có API phù hợp:

```java
package com.example.security;

import java.util.Locale;

import org.springframework.boot.actuate.endpoint.SanitizingFunction;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ActuatorSanitizationConfiguration {

    @Bean
    SanitizingFunction applicationSecretSanitizer() {
        return data -> {
            String key = data.getKey().toLowerCase(Locale.ROOT);

            if (key.contains("authorization")
                    || key.contains("api-key")
                    || key.contains("private-credential")
                    || key.contains("signing-material")) {
                return data.withSanitizedValue();
            }

            return data;
        };
    }
}
```

Giải thích:

- Hàm nhận `SanitizableData`.
- `getKey()` cho biết tên khóa đang được xử lý.
- Nếu khớp quy tắc do ứng dụng quyết định, `withSanitizedValue()` trả về dữ liệu với giá trị đã bị che.
- Nếu không khớp, trả dữ liệu ban đầu để tiếp tục xử lý theo cơ chế sanitizer.
- Không log `data.getValue()` vì nó có thể chứa bí mật.

Các ví dụ API và điểm tích hợp phụ thuộc phiên bản Spring Boot; hãy kiểm tra Javadoc của phiên bản dự án trước khi sao chép nguyên đoạn code. Đây chỉ là minh họa về **cách mở rộng sanitization có chủ đích**.

### 14.2. Dùng API convenience ở các phiên bản hỗ trợ

Ở một số phiên bản mới hơn, có thể dùng helper như:

```java
@Bean
SanitizingFunction customKeyMasking() {
    return SanitizingFunction.sanitizeValue()
            .ifKeyContains("authorization", "private-credential");
}
```

Ví dụ này làm rõ **tên khóa nào cần che** mà không phải viết toàn bộ lambda. Các convenience method có thể được bổ sung qua nhiều phiên bản; dùng API có trong dependency thực tế, đừng copy một method chưa tồn tại ở Spring Boot cũ hơn.

### 14.3. Đừng dựa vào tên khóa đơn giản để tìm mọi secret

Một token có thể được đặt dưới tên:

```text
external.service.auth
integration.header-value
cloud.client.configuration
third-party.connection
```

Không phải khóa nào cũng chứa từ `password` hoặc `token`. Vì vậy:

- Trước tiên, **không show raw values** nếu chưa cần.
- Nếu cần show, viết quy tắc sanitizer phù hợp với hợp đồng cấu hình của ứng dụng.
- Kiểm tra những đường dẫn lồng nhau, list, Map, URI và trường có cấu trúc.
- Giữ danh sách khóa nhạy cảm cập nhật khi thêm tích hợp mới.
- Viết test xác nhận các giá trị giả nhạy cảm vẫn được che.

Sanitizer là **defense in depth**, không nên được coi là lớp bảo vệ duy nhất.

## 15. Cẩn thận với hướng dẫn Spring Boot 2 cũ

Một số tài liệu và blog cũ dùng:

```properties
management.endpoint.env.keys-to-sanitize=...
management.endpoint.configprops.keys-to-sanitize=...
```

Những tên này xuất hiện trong tài liệu của một số phiên bản Spring Boot 2.x. Với các phiên bản Boot 3.x/4.x hiện đại, quy trình sanitization và extension point đã thay đổi; những property cũ không nên được coi là cách cấu hình chắc chắn còn có hiệu lực.

Nếu sao chép cấu hình cũ sang hệ thống mới, có thể xảy ra tình huống:

1. File chứa một property được phiên bản mới không sử dụng.
2. Người vận hành tưởng key nhạy cảm đã được che theo pattern cũ.
3. `show-values` lại được bật rộng.
4. Endpoint có nguy cơ trả raw value ngoài ý định.

Vì vậy:

- Ưu tiên `show-values: never` cho cả hai endpoint.
- Khi có nhu cầu custom masking, xem tài liệu `SanitizingFunction` của đúng phiên bản.
- Không dựa vào việc “property có mặt trong YAML” để khẳng định cơ chế đã được áp dụng.
- Viết test HTTP thực tế kiểm tra response, đặc biệt sau nâng cấp Spring Boot.

**Kiểm tra behavior của endpoint**, không chỉ kiểm tra tên khóa cấu hình.

## 16. Một bài thực hành an toàn với dữ liệu giả

Ta tạo một ứng dụng nhỏ để quan sát cả `env` và `configprops`. Không cần token thật hay kết nối dịch vụ thực tế.

### 16.1. Cấu hình mẫu

`src/main/resources/application.yml`:

```yaml
demo:
  endpoint: https://demo.example.invalid/api
  timeout: 1500ms
  api-token: "EXAMPLE_NOT_A_REAL_TOKEN"

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

### 16.2. Lớp configuration properties

```java
package com.example.actuatorlab;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        URI endpoint,
        Duration timeout,
        String apiToken
) {}
```

### 16.3. Đăng ký record

```java
package com.example.actuatorlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(DemoProperties.class)
public class ActuatorLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ActuatorLabApplication.class, args);
    }
}
```

Project sử dụng `spring-boot-starter-actuator` và một web starter phù hợp để có HTTP endpoints, chẳng hạn `spring-boot-starter-web` trong ứng dụng Spring MVC. Nếu cần security, bổ sung `spring-boot-starter-security` và policy thực sự phù hợp; đừng chỉ dựa vào sample thiếu bảo vệ cho production.

### 16.4. Khởi động trong môi trường cô lập

Lệnh minh họa:

```bash
java -jar app.jar
```

Trong một demo không dùng Spring Security và có HTTP server, cấu hình exposure có thể khiến `/actuator/env` cùng `/actuator/configprops` truy cập được. **Chỉ chạy demo như vậy trên máy/mạng thử nghiệm cô lập, với mọi giá trị đều là dữ liệu giả.**

Truy vấn:

```bash
curl -i http://127.0.0.1:8080/actuator/env
```

Hoặc:

```bash
curl -i http://127.0.0.1:8080/actuator/configprops
```

Kết quả quan trọng để quan sát:

- Response cho biết endpoint có thể được truy cập trong điều kiện demo.
- Giá trị cấu hình được sanitize theo `show-values: never`.
- Không thấy chuỗi `EXAMPLE_NOT_A_REAL_TOKEN` trong response của các endpoint.
- Những tên property hoặc cấu trúc bean có thể vẫn xuất hiện.

**Không có yêu cầu phải tắt sanitization** để chứng minh endpoint đã hoạt động. Thay vì tìm token trong response, hãy chủ động assert token giả **không xuất hiện**.

## 17. Dự đoán kết quả khi đổi show-values

Với cùng dữ liệu giả, có thể lập bảng về ý nghĩa policy trước khi chạy:

| `env.show-values` | Người gọi HTTP | Giá trị thô |
| --- | --- | --- |
| `never` | Người gọi được phép vào endpoint | Bị sanitize |
| `when-authorized` | Không đáp ứng role | Bị sanitize, nếu request vẫn được phép |
| `when-authorized` | Đã xác thực và đáp ứng role | Có thể hiển thị, trừ khi custom sanitizer che |
| `always` | Bất kỳ người gọi nào tới được endpoint | Có thể hiển thị, trừ khi custom sanitizer che |

Tương tự cho `configprops.show-values`, nhưng hai property có thể được cấu hình khác nhau.

Đối với JMX, không được áp dụng nguyên bảng HTTP này mà không xét quy tắc JMX; với `when-authorized`, người gọi JMX được coi là authorized theo tài liệu Actuator hiện đại.

Thực hành an toàn nên ưu tiên:

1. Giữ `never`.
2. Thêm test chứng minh masked response.
3. Nếu thực sự phải kiểm tra `when-authorized`, chỉ dùng token **giả**, có principal admin và principal thường, chạy trong môi trường test.
4. Không thực hành `always` với bất kỳ credential nào của môi trường thật.

## 18. Kiểm thử HTTP theo ba lớp: exposure, authentication, masking

Muốn chắc chắn secret không rò rỉ, không đủ nếu chỉ assert `status=200`. Kiểm thử phải kiểm tra ba mặt:

- Endpoint được expose theo ý định hay không.
- User đúng role được phép, user sai role bị chặn thế nào.
- Trong response thành công, giá trị nhạy cảm có bị che hay không.

Ví dụ chiến lược kiểm thử:

```text
Scenario A: production baseline
  GET /actuator/env -> không được expose / bị từ chối
  GET /actuator/configprops -> không được expose / bị từ chối

Scenario B: diagnostic profile, never
  GET /actuator/env -> được phép nếu security cho phép
  Body không có token giả
  GET /actuator/configprops -> được phép nếu security cho phép
  Body không có token giả

Scenario C: when-authorized, admin role
  Operator role khác: không xem được giá trị gốc
  Admin: được xác định authorized
  Custom sanitizer vẫn che những khóa cần bảo vệ
```

Đây là các tình huống **thiết kế test**, không có cam kết mọi dự án đều dùng cùng một HTTP status khi endpoint chưa expose hoặc principal chưa có quyền.

### 18.1. Ví dụ integration test với MockMvc

Trong dự án Servlet dùng Spring Boot Test + Spring Security, có thể viết test minh họa:

```java
package com.example.actuatorlab;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest(properties = {
    "demo.api-token=EXAMPLE_NOT_A_REAL_TOKEN",
    "management.endpoints.web.exposure.include=health,env,configprops",
    "management.endpoint.env.show-values=never",
    "management.endpoint.configprops.show-values=never"
})
@AutoConfigureMockMvc(addFilters = false)
class ActuatorMaskingTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void envDoesNotEchoToken() throws Exception {
        MvcResult result = mockMvc.perform(
                get("/actuator/env"))
            .andReturn();

        String body = result.getResponse().getContentAsString();

        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        assertThat(body).doesNotContain("EXAMPLE_NOT_A_REAL_TOKEN");
    }

    @Test
    void configpropsDoesNotEchoToken() throws Exception {
        MvcResult result = mockMvc.perform(
                get("/actuator/configprops"))
            .andReturn();

        String body = result.getResponse().getContentAsString();

        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        assertThat(body).doesNotContain("EXAMPLE_NOT_A_REAL_TOKEN");
    }
}
```

**Điều kiện quan trọng của ví dụ:** `addFilters = false` chỉ được dùng để **cô lập phép thử sanitization** và tránh phụ thuộc cơ chế login của dự án; tuyệt đối không hiểu nó là cấu hình security production hoặc bằng chứng rằng endpoint được phân quyền đúng.

Trong bộ test thực tế cần thêm **một test khác có security filters bật**, dùng tài khoản/role giả được cấp đúng quyền, để kiểm tra HTTP 401/403/200 theo policy. Khi project đã có nhiều context path hoặc management port riêng, phải điều chỉnh cách tạo test client tương ứng.

Tùy phiên bản Spring Boot, package `@AutoConfigureMockMvc` có thể được tổ chức khác; hãy dùng import tương ứng với dependency test thực tế. Mục tiêu là kiểm tra behavior, không ràng buộc bài học vào một minor version.

### 18.2. Không assert toàn bộ JSON cố định

Cấu trúc response có thể đổi theo phiên bản Spring Boot, nguồn thuộc tính và những bean được auto-configure. Một test so sánh nguyên một JSON snapshot dài dễ bị vỡ dù chính sách che giá trị vẫn đúng.

Nên tập trung assert:

- Endpoint đúng là truy cập được trong context test.
- Chuỗi secret giả **không xuất hiện**.
- Giá trị đại diện đã sanitize xuất hiện tại trường kỳ vọng nếu JSON có trường tương ứng.
- Thông tin cấu hình không nhạy cảm vẫn có thể chẩn đoán được theo thiết kế.

Có thể kiểm tra đường dẫn JSON cụ thể trong một test tích hợp phiên bản đã biết; không cần kỳ vọng cùng một shape ở mọi Spring Boot release.

## 19. Kiểm thử when-authorized không nên dùng secret thật

Một cách tiếp cận an toàn là tạo **một credential giả** dành riêng cho test:

```text
demo.api-token=DEMO_FAKE_TOKEN_DO_NOT_USE
```

Sau đó dùng hai principal test:

- `ROLE_ACTUATOR_VIEWER`: có thể được cho phép đọc endpoint nhưng không được xem giá trị gốc.
- `ROLE_ACTUATOR_ADMIN`: là principal được policy xác định đủ điều kiện xem raw values trong môi trường kiểm thử.

Kiểm tra hai điều kiện:

1. HTTP request có được SecurityFilterChain cho phép đi tới endpoint hay không?
2. Nếu request được trả 200, `show-values` quyết định value là masked hay raw?

Không nên suy đoán nếu viewer nhận 403 thì đó là kết quả sanitization. 403 là kết quả phân quyền request; sanitization chỉ có ý nghĩa đối với **nội dung response được tạo**.

Một số test nên giữ `show-values=never` ngay cả với admin. Nếu buộc phải kiểm thử `when-authorized` với raw value, dùng fake token không nhạy cảm và đảm bảo test log không được gửi ra nơi thiếu quyền truy cập.

## 20. Thay đổi cấu hình phải dùng đúng tên endpoint

Một lỗi phổ biến là viết:

```properties
management.endpoints.env.show-values=never
```

Đường dẫn này sai vì `endpoints` (số nhiều) được dùng cho các thiết lập liên quan đến **tập endpoint và exposure**; `endpoint` (số ít) được dùng cho cấu hình **một endpoint cụ thể**.

Đúng:

```properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

Và:

```properties
management.endpoints.web.exposure.include=health,env,configprops
```

Phân biệt:

```text
management.endpoints.web.exposure.include
         ^
     endpoints (số nhiều)

management.endpoint.env.show-values
         ^
     endpoint (số ít)
```

YAML tương ứng:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,env,configprops"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Khi một property cấu hình bị viết sai, Spring Boot có thể không áp dụng nó cho Actuator theo ý định. Vì vậy cần **quan sát behavior thực tế**, không chỉ đọc file và thấy dòng cấu hình tồn tại.

## 21. Ẩn giá trị không có nghĩa ẩn metadata

Ngay cả khi `show-values=never`, endpoint có thể trả:

- Tên `PropertySource` hoặc vị trí file nguồn.
- Tên các nhóm property.
- Profile đang hoạt động.
- Tên bean và kiểu bean chứa `@ConfigurationProperties`.
- Đường dẫn cấu hình từ `origin`, tùy response.
- Cấu trúc của các object hoặc danh sách những khóa được khai báo.

Thông tin này có thể tiết lộ:

```text
spring.datasource.url          // có sử dụng database
cloud.partner.endpoint         // có tích hợp đối tác
internal.auth.issuer           // tên một hệ thống xác thực
payment.signing-key            // sự tồn tại của vật liệu ký
prod-eu-west                   // vùng hoặc profile vận hành
```

Không nhất thiết có giá trị secret, nhưng vẫn là **thông tin nội bộ**. Do đó, response đã mask không được tự động coi là dữ liệu an toàn để chia sẻ công khai.

Đối với ticket hỗ trợ hoặc tài liệu sự cố:

- Chỉ trích xuất những khóa thực sự cần thiết.
- Loại bỏ tên nguồn hạ tầng/đường dẫn nội bộ nếu không cần cho người nhận.
- Không đính kèm nguyên response `/actuator/env` hoặc `/actuator/configprops` khi không có đánh giá dữ liệu.
- Tránh lưu snapshot cấu hình vào kho log có vòng đời dài không kiểm soát.

Bảo vệ bí mật bao gồm cả **giảm lượng thông tin nội bộ không cần phát tán**.

## 22. Ẩn giá trị không thay cho quản lý secret

Giả sử Actuator trả:

```json
{
  "value": "******"
}
```

Điều này **không** có nghĩa:

- Biến môi trường gốc đã bị xóa.
- Password đã được mã hóa trong file cấu hình.
- Secret không tồn tại trong bộ nhớ Java.
- Mọi log khởi động đều đã được sanitize.
- Stack trace và exception message không thể chứa bí mật.
- Một endpoint do ứng dụng tự viết cũng tự áp dụng sanitization.
- Người có quyền truy cập host/container không đọc được giá trị từ những nguồn khác.

Sanitization của Actuator **chỉ là một lớp kiểm soát đầu ra**. Cần kết hợp với:

1. Secret manager hoặc phương pháp cấp bí mật phù hợp.
2. Nguyên tắc quyền tối thiểu.
3. Không đưa secret thật vào source repository.
4. Không in `@ConfigurationProperties.toString()` nếu object chứa credential.
5. Không log tất cả biến môi trường hoặc đối số khởi động có secret.
6. Không lưu response diagnostic trong CI/CD artifact không bảo vệ.
7. Rotation/thu hồi credential khi đã có dấu hiệu lộ lọt.
8. TLS, kiểm soát mạng và audit hành vi đọc dữ liệu.

Một lỗi thường thấy là che password trong `env` nhưng lại có:

```java
log.info("Inventory configuration: {}", inventoryProperties);
```

Với record, `toString()` thường bao gồm các thành phần, nên token có thể xuất hiện trong log. **Actuator sanitizer không tự can thiệp vào lệnh log này.**

Cách tốt hơn là log những thông số an toàn đã chọn lọc:

```java
log.info(
    "Inventory integration configured, timeout={}",
    inventoryProperties.timeout()
);
```

Ngay cả vậy, cần cân nhắc liệu timeout, endpoint host hoặc các giá trị còn lại có phù hợp với mức phân quyền của hệ thống log không.

## 23. Secret nằm trong URI hoặc Map vẫn là secret

Không phải credential nào cũng mang tên `password`.

Ví dụ một chuỗi kết nối có username và password nằm trong URI:

```text
jdbc:.../database?user=demo&password=FAKE_ONLY
https://demo-user:FAKE_ONLY@service.example.invalid
```

Hoặc:

```yaml
integration:
  headers:
    Authorization: "Bearer FAKE_TEST_VALUE"
```

Hoặc Map cấu hình:

```yaml
partner:
  clients:
    alpha:
      authentication: "FAKE_TEST_VALUE"
```

Khi `show-values=always` hoặc người gọi được `when-authorized` cho xem raw values, **có thể xuất hiện những chuỗi rất nhạy cảm**, kể cả nếu tên property không khớp một số từ khóa sanitizer tự định nghĩa.

Vì thế:

- Thiết kế sanitizer theo cả **field và cấu trúc dữ liệu**.
- Xét tên header như `Authorization`, `Cookie`, `Set-Cookie`, `X-Api-Key` nếu xuất hiện trong cấu hình.
- Không giả định một chuỗi URI đã được `URI`-convert sẽ tự được ẩn.
- Viết test bao gồm Map, nested objects và các tên khóa đặc thù của dự án.
- Khi không cần xem raw value, giữ `never` thay vì cố xây một danh sách từ khóa bảo vệ hoàn hảo.

## 24. Một số bẫy khi dùng reverse proxy hoặc API Gateway

Một số deployment cho management endpoint đi qua:

```text
Operator -> Load Balancer -> API Gateway -> Reverse Proxy -> Spring Boot
```

Ở mỗi tầng, cần hỏi:

1. Proxy có publish `/actuator/**` ra Internet không?
2. Gateway có làm mất header xác thực hoặc forward request đã được xác thực sai không?
3. TLS có được bảo đảm trên từng chặng cần thiết không?
4. WAF/logging layer có lưu body response của endpoint không?
5. Có cache chung cho response chứa dữ liệu quản trị không?
6. Path rewrite có khiến `/internal/env` thực chất trỏ tới `/actuator/env` không?
7. Một URL định danh chỉ được bảo vệ bởi “khó đoán đường dẫn” hay bởi xác thực thật?

Việc Spring Boot đặt `show-values=never` giúp che giá trị, nhưng không giải quyết tất cả các lỗi route, identity và metadata exposure bên ngoài ứng dụng.

Không cấu hình proxy “cho phép tất cả nội bộ” chỉ vì IP thuộc một mạng tư nhân. Mạng nội bộ vẫn có nguy cơ lateral movement, tài khoản bị xâm nhập hoặc rule định tuyến sai.

## 25. Bảng quyết định theo môi trường

| Môi trường | Expose `env/configprops`? | `show-values` đề xuất | Lưu ý |
| --- | --- | --- | --- |
| Production bình thường | Không, trừ nhu cầu rõ | `never` | Ưu tiên không expose |
| Production có chẩn đoán được phê duyệt | Chỉ nội bộ, có phân quyền | `never` trước | Chỉ mở raw khi có lý do và quy trình |
| Staging chứa dữ liệu nhạy cảm | Giới hạn như production | `never` | Không coi staging là vô hại |
| Dev máy cá nhân với dữ liệu giả | Có thể expose cho bài thực hành | `never` | Dùng token giả, loopback |
| Test bảo mật | Expose trong test context riêng | Thử `never`/`when-authorized` | Assert cả HTTP access và body |
| JMX quản trị | Hạn chế tối đa | `never` nếu có expose | `when-authorized` trên JMX có quy tắc riêng |

Không có một “profile dev an toàn” nếu nó dùng credential thật, có port công khai hoặc log toàn bộ response. Phân loại rủi ro phải dựa trên **dữ liệu và khả năng truy cập**, không chỉ tên môi trường.

## 26. Khi nào có thể cần thấy một giá trị không nhạy cảm?

Có những tình huống thông số runtime thật sự hữu ích:

- Timeout cấu hình đang là `250ms` hay `2s`?
- Số lần retry đã được ghi đè từ `3` thành `5` chưa?
- Chế độ tích hợp đang là `SAFE` hay `FAST`?
- Một feature flag đang bật hay tắt?
- Mức giới hạn batch là bao nhiêu?

Nếu muốn công khai những giá trị **đã được xem xét an toàn** cho operator, có các hướng thiết kế:

1. Tạo một endpoint chẩn đoán riêng **chỉ trả whitelist thông tin đã được duyệt**, kèm authentication/authorization.
2. Cung cấp metric hoặc health detail phù hợp, tránh trả nguyên object properties.
3. Dùng cấu hình vận hành hoặc công cụ xem trạng thái deployment có phân quyền riêng.
4. Giữ `env` và `configprops` mặc định mask toàn bộ.
5. Khi cần xem raw tạm thời, dùng quy trình kiểm soát quyền và không ghi response ra hệ thống ngoài.

Đây thường là lựa chọn an toàn hơn so với `show-values=always` trên endpoint tổng quát chứa nhiều nguồn bí mật.

### 26.1. Một endpoint whitelist cần kiểm tra điều gì?

Nếu tự viết:

```java
@GetMapping("/internal/config-summary")
Map<String, Object> summary() {
    return Map.of(
        "mode", settings.mode(),
        "batchSize", settings.batchSize()
    );
}
```

ví dụ này chỉ minh họa việc **lựa chọn hai trường không nhạy cảm**. Endpoint tự viết vẫn phải có Spring Security, network policy và kiểm tra người gọi; không có cơ chế nào tự bảo vệ nó chỉ vì đường dẫn bắt đầu bằng `/internal`.

Không được vô tình trả nguyên `settings` trong Map sau một đợt refactor, vì object có thể được thêm token vào tương lai.

## 27. Checklist kiểm tra sự cố: env trả giá trị bất ngờ

Khi ai đó nói “`/actuator/env` đang lộ giá trị”, hãy phân tích theo thứ tự:

1. **Xác nhận đường đi**: endpoint nào, qua HTTP hay JMX, đang dùng version Spring Boot nào?
2. **Kiểm tra exposure**: endpoint có được expose ngoài ý định không?
3. **Kiểm tra security**: security filter chain nào áp dụng, role nào thực sự có hiệu lực?
4. **Kiểm tra `show-values`**: có `always` hoặc `when-authorized` từ một nguồn ưu tiên cao hơn không?
5. **Kiểm tra role**: `management.endpoint.env.roles` được cấp đúng không, hay mọi user đăng nhập đều được coi authorized?
6. **Kiểm tra custom sanitizer**: bean có được tạo, key có khớp điều kiện, test có được chạy không?
7. **Kiểm tra nguồn khác**: ứng dụng có log secret, trace request/response hoặc custom endpoint khác không?
8. **Kiểm tra người đã truy cập**: review access logs/audit theo quy định mà không tạo thêm bản sao bí mật.
9. **Giảm bề mặt ngay**: ngừng expose, đặt `never`, thu hẹp mạng và quyền khi có dấu hiệu sai.
10. **Xử lý secret đã lộ**: đánh giá phạm vi, rotate/revoke credential nếu cần và cập nhật playbook.

Khi sự cố liên quan dữ liệu thực, **không tái hiện bằng cách in thêm secret thật ra terminal hoặc chat**. Dùng giá trị giả trong test để xác nhận cấu hình mới đã che đúng.

## 28. Checklist khi configprops vẫn thiếu giá trị hoặc không thấy bean

Không phải mọi thiếu dữ liệu ở `/actuator/configprops` đều là vấn đề sanitization.

Có thể do:

- Lớp `@ConfigurationProperties` chưa được đăng ký.
- Bean không tồn tại vì điều kiện auto-configuration không đạt.
- Prefix trong Java và file cấu hình không khớp.
- Giá trị được nạp ở nguồn khác với giá trị người dùng kỳ vọng.
- Một bean cấu hình chỉ được tạo trong profile hoặc điều kiện nhất định.
- Response bị sanitize nên thấy `******`, không phải “mất value”.
- Chế độ security từ chối request.
- Endpoint chưa được expose qua HTTP.
- Phiên bản Spring Boot khác có response structure khác.

Quy trình:

1. Xác minh bean được tạo và được Spring quản lý.
2. Kiểm tra `@ConfigurationProperties(prefix=...)`.
3. Xem tên các nguồn thuộc tính, có thể dùng `env` đã được bảo vệ.
4. Xem profile hoạt động.
5. Xác nhận converter/binder có xử lý kiểu Java đúng không.
6. Xem `show-values` có che nội dung hay không.
7. Không bật `always` chỉ để nhìn một trường khi còn những cách kiểm tra an toàn khác.

Một value `******` không phải bằng chứng ứng dụng đang dùng mật khẩu literal `******`. Nó thường là **biểu diễn đã được sanitize** của endpoint.

## 29. Kiểm tra bằng curl: cách đọc mã trạng thái

Giả sử ứng dụng chạy tại `127.0.0.1:8080` trong môi trường thử nghiệm có dữ liệu giả.

```bash
curl -i http://127.0.0.1:8080/actuator/health
```

Thử:

```bash
curl -i http://127.0.0.1:8080/actuator/env
```

Khi không expose, có thể thấy 404; khi security chặn, có thể thấy 401 hoặc 403. Khi được phép, có thể thấy 200 với body đã mask.

Trong môi trường dùng HTTP Basic, công cụ có thể hỏi mật khẩu. Không nên đưa password thật trực tiếp vào câu lệnh được lưu ở shell history hoặc gửi trong tài liệu hỗ trợ.

Một cách gọi với username nhưng không gắn password vào tham số:

```bash
curl -i -u admin \
  https://management.example.invalid/actuator/env
```

`curl` có thể nhắc nhập password; đó chỉ là ví dụ truy cập một endpoint giả định và không thay thế quy tắc bảo mật của dự án. Khi dùng OAuth2, mTLS hoặc gateway chuyên dụng, cách gọi khác tương ứng.

**Không gửi response JSON thô chứa khả năng có secret vào ticket/chat**. Nếu cần đối chiếu, hãy dùng script/test kiểm tra tính chất “không chứa token giả” và chỉ báo kết quả.

## 30. Phân biệt Actuator sanitization với che log

Có ba nơi dữ liệu cấu hình có thể lộ:

```text
A. Actuator response
   /actuator/env, /actuator/configprops

B. Application logs
   log.info("{}", properties), exception messages

C. External diagnostics
   CI logs, support bundles, monitoring exports
```

Cơ chế `show-values` của Actuator tác động tới **A**. Nó không tự kiểm soát **B** hoặc **C**.

Ví dụ:

```java
record AuthProperties(String clientId, String clientSecret) {}
```

Khi log:

```java
log.debug("auth = {}", authProperties);
```

`record.toString()` có thể in cả `clientSecret`. Đặt `management.endpoint.configprops.show-values=never` không làm thay đổi log này.

Nếu một chuỗi secret đã xuất hiện trong log tập trung, sửa `show-values` không xóa được bản ghi đã lưu. Cần thực hiện quy trình bảo vệ, retention và rotation riêng.

Những kênh rò rỉ thường bị bỏ qua:

- Java startup arguments chứa `--app.token=...`.
- Exception chứa URI có embedded credential.
- Dump của thread hoặc process environment.
- HTTP exchange logging nếu có body/header nhạy cảm.
- Snapshot actuator được exporter thu thập và lưu.
- Đoạn config debug được gửi qua email hoặc hệ thống quản lý công việc.

Một chính sách tốt phải bảo vệ **cả nguồn, đường truyền, nơi lưu và đầu ra chẩn đoán**.

## 31. Lỗi phổ biến và cách sửa

### 31.1. Bật include="*" để dễ xem rồi quên tắt

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
```

Cách này đề nghị expose mọi endpoint có thể expose; nó làm tăng bề mặt tấn công và có thể đưa các endpoint không cần thiết ra ngoài. Hãy chọn whitelist tối thiểu như `health` hoặc `health,info`.

### 31.2. Giữ show-values=always trên production

Kể cả khi có firewall, một thay đổi route hoặc quyền có thể làm giá trị bị lộ. Dùng `never` theo mặc định và chỉ mở xem raw theo quy trình được phê duyệt.

### 31.3. Khi dùng when-authorized mà không khai roles

Theo hành vi tài liệu Actuator, trên HTTP, mọi user đã xác thực có thể được coi authorized khi không khai roles. Nếu cần giới hạn, khai role phù hợp và test.

### 31.4. Nghĩ role trên HTTP bảo vệ được JMX

JMX có quy tắc riêng. Giới hạn JMX exposure và security của giao diện JMX; không giả định role setting của HTTP được áp dụng tương đương.

### 31.5. Nghĩ Spring Security tự bảo vệ mọi endpoint khi đã custom chain

Khi ứng dụng khai báo `SecurityFilterChain`, Spring Boot có thể nhường kiểm soát cấu hình bảo mật. Kiểm tra matcher thật và không để `permitAll` bao phủ nhầm actuator.

### 31.6. Dùng property keys-to-sanitize từ tài liệu cũ

Không dựa vào property của Spring Boot 2 như một bảo đảm trong Boot 3/4. Kiểm tra tài liệu phiên bản, dùng `SanitizingFunction` nếu cần mở rộng và xác nhận response bằng test.

### 31.7. Chỉ che key có chữ password

Credential có thể nằm trong `authorization`, `header-value`, URI, Map hoặc tên khác. Cách đơn giản và an toàn hơn là `show-values=never` nếu không có nhu cầu raw.

### 31.8. Thấy ****** rồi tưởng ứng dụng mất dữ liệu

Dữ liệu gốc vẫn có thể được binder sử dụng. Giá trị được thay thế ở response Actuator, không nhất thiết trong object runtime.

### 31.9. Trả raw JSON cho bộ phận hỗ trợ bên ngoài

Response dù masked có thể chứa tên property và topology nội bộ; nếu raw, nguy cơ càng nghiêm trọng. Chỉ chia sẻ phần tối thiểu đã được rà soát.

### 31.10. Dùng management port riêng mà không có policy mạng

Port riêng chỉ thay đổi điểm lắng nghe. Nếu publish ra mạng rộng hoặc proxy forward nhầm, endpoint vẫn có thể bị truy cập.

### 31.11. Dùng dữ liệu production để test masking

Có thể sử dụng token giả có sentinel rõ ràng. Không cần password thật để chứng minh một endpoint có che chuỗi đúng hay không.

### 31.12. Kiểm tra status nhưng không kiểm tra response body

HTTP 200 không có nghĩa response đã được sanitize. Test cần xác nhận secret giả không xuất hiện.

### 31.13. Kiểm tra response nhưng quên security filters

Nếu test tắt filters để cô lập sanitizer, nó chưa xác nhận IAM, role hoặc network access. Bổ sung test có filters bật.

### 31.14. Quên rằng một endpoint khác có thể tự trả secret

Actuator `env` và `configprops` có cơ chế sanitization riêng. Một custom endpoint, controller, logger hoặc exporter do ứng dụng viết không tự thừa hưởng toàn bộ bảo vệ này.

### 31.15. Thay đổi file YAML rồi tin rằng cấu hình đã đổi trong tiến trình

Cấu hình Spring Boot thường được nạp lúc khởi động. Với bean được tạo và bind một lần, sửa YAML lúc ứng dụng đang chạy không bảo đảm mọi bean hay endpoint policy tự refresh. Để kiểm tra một cấu hình Actuator mới, nên khởi động lại hoặc dùng cơ chế refresh được triển khai và kiểm thử đúng.

## 32. Bài tập 1: phân biệt exposure và masking

Cho:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health"
  endpoint:
    env:
      show-values: never
```

Hỏi:

1. `/actuator/env` có được expose qua HTTP theo danh sách này không?
2. `show-values: never` có phải nguyên nhân duy nhất khiến endpoint không truy cập được không?
3. Nếu thêm `env` vào include, value gốc sẽ được hiện hay che?
4. Nếu Spring Security chặn mọi request tới `env`, có nên kỳ vọng response 200 với `******` không?

Hướng giải:

- Danh sách include chưa có `env`.
- `show-values` quản lý cách hiện value, không phải chính sách expose.
- Nếu endpoint được expose và request được phép, `never` vẫn che value.
- Request bị security chặn có thể nhận 401/403 thay vì body cấu hình.

## 33. Bài tập 2: chọn chính sách theo vai trò

Yêu cầu:

- Operator thường có quyền gọi một số endpoint chẩn đoán.
- Chỉ nhóm quản trị được phê duyệt mới có thể xem raw value khi thật sự cần.
- Các khóa chứa `private-credential` luôn bị che.
- JMX không dùng để xem env/configprops.

Hãy đề xuất:

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
      show-values: when-authorized
      roles: "ACTUATOR_ADMIN"
    configprops:
      show-values: when-authorized
      roles: "ACTUATOR_ADMIN"
```

Sau đó:

1. Cấu hình HTTP security cho phép đúng nhóm operator/admin tương ứng.
2. Viết custom `SanitizingFunction` che `private-credential` kể cả khi admin truy cập.
3. Test principal không có role và principal admin.
4. Test response không chứa secret giả tương ứng với khóa private.
5. Không dùng dữ liệu production thật trong bất kỳ test nào.

Nếu không có nhu cầu raw value, đơn giản hơn và bảo thủ hơn là để `never`.

## 34. Bài tập 3: tìm các lỗi trong cấu hình

Cho:

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
      show-values: when-authorized
```

Các vấn đề cần nhận diện:

- Expose quá nhiều endpoint.
- `env` có thể trả raw value cho mọi người tới được endpoint.
- `configprops` đặt `when-authorized` nhưng chưa giới hạn role cụ thể; người đã xác thực có thể được xem là authorized.
- Chưa biết có Spring Security, firewall, TLS hay chính sách JMX không.
- Nếu một người dùng đã tạo custom `SecurityFilterChain` thiếu matcher cho Actuator, quyền truy cập có thể quá rộng.

Đề xuất sửa theo nguyên tắc quyền tối thiểu: chỉ expose endpoint thực sự cần, đặt `show-values: never` theo mặc định, bảo vệ mạng và HTTP, giới hạn JMX và kiểm chứng bằng integration test.

## 35. Bài tập 4: đọc kết quả test đúng cách

Một kiểm thử gọi `/actuator/env` và thấy:

```text
status = 200
body contains "demo.api-token"
body contains "******"
body does not contain "FAKE_DEMO_TOKEN"
```

Câu hỏi: có thể kết luận gì?

- Endpoint đã phản hồi.
- Tên property có thể được trả về.
- Giá trị token giả không xuất hiện trong response.
- Một số dữ liệu đã được trình bày dưới dạng sanitized.

Không thể kết luận từ test này rằng:

- Endpoint đã được phân quyền đúng cho mọi principal.
- Mọi key nhạy cảm đều được che.
- Không có leak trong log hoặc custom endpoint.
- Production đã chạy chính xác cùng cấu hình.
- JMX không thể trả raw value.

Đây là lý do cần nhiều lớp test và kiểm tra triển khai.

## 36. Bài tập 5: phân biệt env và configprops

Giả sử ứng dụng có:

```java
@ConfigurationProperties(prefix = "notifications")
public record NotificationProperties(
        String token,
        Duration timeout
) {}
```

Và nguồn YAML + biến môi trường có thể cùng khai báo hai khóa.

Hãy trình bày:

1. Khi muốn biết thứ tự và nguồn khai báo `notifications.timeout`, nên xem `env`.
2. Khi muốn biết một bean `NotificationProperties` tồn tại và được bind thế nào, nên xem `configprops`.
3. Khi hai endpoint đều `show-values=never`, không nên kỳ vọng chúng trả raw token.
4. Nếu một source override timeout, bean có thể lấy giá trị đã được chọn ở thời điểm binding.
5. Đừng bật `always` để chỉ kiểm tra một lỗi về thứ tự nguồn; hãy ưu tiên thông tin metadata và test có kiểm soát.

## 37. Bài tập 6: phản ứng khi secret đã lộ qua endpoint

Tình huống: bộ phận vận hành phát hiện `/actuator/env` trên môi trường thật từng trả raw token do `show-values=always`.

Các việc cần cân nhắc:

1. Hạn chế/tắt exposure ngay theo quy trình vận hành.
2. Đổi chính sách sang `never`.
3. Kiểm tra security matcher, role, reverse proxy và firewall.
4. Xác định khoảng thời gian endpoint có thể truy cập và những tài khoản/địa chỉ đã gọi.
5. Không phát tán lại JSON trong quá trình điều tra.
6. Đánh giá việc rotate/revoke token có nguy cơ bị lộ.
7. Tìm và xử lý những bản sao đã lưu trong logs, monitoring hoặc tickets.
8. Bổ sung integration test chặn raw token giả.
9. Kiểm tra các endpoint liên quan như `configprops` và kênh JMX.
10. Ghi nhận thay đổi cấu hình, tài liệu và playbook vận hành.

Việc chỉ che từ thời điểm hiện tại **không tự làm những bản sao secret đã lộ trước đó biến mất**.

## 38. Tổng kết: nguyên tắc chẩn đoán an toàn

`env` và `configprops` rất hữu ích khi tìm lỗi Spring Boot Externalized Configuration:

```text
/env
    -> Environment / PropertySources / nguồn và profile

/configprops
    -> Các bean @ConfigurationProperties đã được binding
```

Nhưng mọi lợi ích chẩn đoán cần đặt trong mô hình bảo vệ nhiều lớp:

```text
Chỉ expose khi cần
        |
        v
Giới hạn mạng và kênh JMX
        |
        v
Xác thực + phân quyền HTTP
        |
        v
show-values = never (mặc định an toàn)
        |
        v
Custom SanitizingFunction nếu thật sự cần
        |
        v
Kiểm thử response không lộ secret giả
        |
        v
Kiểm soát log, ticket và quy trình hỗ trợ
```

Các nguyên tắc phải ghi nhớ:

1. **`management.endpoint.env.show-values` và `management.endpoint.configprops.show-values` là hai thiết lập riêng.**
2. **`never`** che các giá trị ở response Actuator; mặc định hiện đại phù hợp để bắt đầu.
3. **`when-authorized`** chỉ cho người được coi là authorized xem raw values; nếu không khai roles, trên HTTP việc đã đăng nhập có thể đủ.
4. **`always`** rất rủi ro vì có thể hiển thị raw values cho mọi người tới được endpoint.
5. **Expose endpoint không đồng nghĩa cho phép hiện raw values**, và masking không thay thế security.
6. **JMX có hành vi authorization riêng**; không giả định role HTTP bảo vệ JMX.
7. **`SanitizingFunction`** giúp che bổ sung những khóa ứng dụng coi là nhạy cảm, kể cả khi policy cho xem raw.
8. **Không dùng hướng dẫn keys-to-sanitize cũ mà chưa kiểm tra phiên bản Spring Boot.**
9. **Ẩn value không xóa secret khỏi Environment** và không bảo vệ tất cả các kênh log/custom endpoint.
10. **Kiểm thử bằng giá trị giả**, xác nhận cả access và body; không dùng credential thật để trình diễn lỗi.

Cách lựa chọn có độ an toàn cao nhất cho đa số triển khai: **không expose `env`/`configprops` trên kênh công khai, giữ `show-values: never`, bảo vệ management interface và chỉ cung cấp những thông tin chẩn đoán thật sự cần thiết**.

### Nguồn đọc thêm

- [Spring Boot — Actuator Endpoints, Exposing Endpoints và Sanitize Sensitive Values](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Environment (env) REST API](https://docs.spring.io/spring-boot/api/rest/actuator/env.html)
- [Spring Boot — Configuration Properties (configprops) REST API](https://docs.spring.io/spring-boot/api/rest/actuator/configprops.html)
- [Spring Boot — SanitizingFunction Javadoc](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/endpoint/SanitizingFunction.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)

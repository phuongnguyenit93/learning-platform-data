# Tùy chỉnh chi tiết, vai trò, thứ tự trạng thái và HTTP status theo nhóm

## 1. Một nhóm health cần trả lời điều gì?

Nhóm sức khỏe (health group) là một tập các bộ kiểm tra sức khỏe được chọn cho một mục đích. Chẳng hạn, nhóm `traffic` cung cấp tín hiệu cho thành phần điều phối lưu lượng, còn nhóm `ops` phục vụ người vận hành chẩn đoán. Hai nhóm có thể dùng cùng một `HealthIndicator` nhưng áp dụng chính sách phản hồi khác nhau.

Cần tách bốn câu hỏi:

| Câu hỏi | Cấu hình hoặc thành phần quyết định |
| --- | --- |
| Ai được gửi yêu cầu tới URL? | Spring Security, qua `SecurityFilterChain` |
| Người gọi được thấy tên thành phần và dữ liệu chẩn đoán tới mức nào? | `show-components`, `show-details`, `roles` của nhóm |
| Nhiều trạng thái thành phần được gộp thành trạng thái nào? | `status.order` hoặc `StatusAggregator` của nhóm |
| Trạng thái đã gộp trở thành mã HTTP nào? | `status.http-mapping` hoặc `HttpCodeStatusMapper` của nhóm |

Ví dụ, người gọi chưa đăng nhập có thể được phép nhận HTTP 503 và `{"status":"DOWN"}`, trong khi người có vai trò vận hành nhận thêm thành phần gây lỗi. Thông tin sức khỏe cơ bản và thông tin chẩn đoán phục vụ hai nhu cầu khác nhau.

Bài này dùng Spring Boot **3.3.13**, Java **21** và Spring MVC để minh họa. Các chính sách nhóm thuộc Actuator; cấu hình `HttpSecurity` trong ví dụ dành cho Servlet. Ứng dụng WebFlux cần cấu hình bảo mật tương ứng của WebFlux.

Một nhóm có hợp đồng riêng gồm tư cách thành viên, bộ tổng hợp trạng thái, bộ ánh xạ HTTP và chính sách hiển thị. Các thành phần này được thể hiện trong API [HealthEndpointGroup của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthEndpointGroup.html).

## 2. Luồng xử lý: trạng thái, HTTP và nội dung là ba kết quả khác nhau

Với yêu cầu được phép tới health endpoint, có thể hình dung:

```text
GET /actuator/health/ops
    -> Chọn nhóm ops
    -> Chọn các contributor thuộc nhóm
    -> Thu thập Health của từng contributor
    -> StatusAggregator chọn trạng thái chung
    -> HttpCodeStatusMapper chọn mã HTTP
    -> Chính sách hiển thị quyết định components/details cho người gọi
    -> Trả phản hồi
```

Đây là mô hình về trách nhiệm, không phải cam kết thứ tự gọi nội bộ hay số lần thực thi bộ kiểm tra.

Các hệ quả cần nhớ:

- Ẩn chi tiết không làm bộ kiểm tra mất tư cách thành viên và không biến `DOWN` thành `UP`.
- Đổi mã HTTP không đổi trường `status` trong JSON.
- Thêm một ánh xạ cho `DEGRADED` không giúp bộ tổng hợp tự hiểu độ ưu tiên của trạng thái đó.
- Đưa contributor vào nhóm không loại contributor ấy khỏi health tổng thể.
- Không có hợp đồng rằng hai yêu cầu tới hai nhóm dùng chung một ảnh chụp kết quả. Bộ kiểm tra thực tế có thể quan sát trạng thái khác nhau giữa các lần gọi.

Vì vậy, khi kiểm thử phải kiểm tra đồng thời **mã HTTP, trạng thái JSON và mức dữ liệu được hiển thị**.

## 3. Xác định đúng phạm vi cấu hình và quy tắc kế thừa

Tiền tố chung là:

```properties
management.endpoint.health
```

Tiền tố riêng của nhóm tên `ops` là:

```properties
management.endpoint.health.group.ops
```

Đường dẫn mặc định để đọc nhóm:

```text
/actuator/health/ops
```

Nhóm được khai báo dưới health endpoint; không cần thêm `ops` vào danh sách endpoint được công bố. Với đường dẫn mặc định, công bố endpoint `health` là đủ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
```

Việc công bố này vẫn chịu cấu hình bật/tắt endpoint và bảo mật của ứng dụng.

Trong cơ chế tự cấu hình của Boot 3.3, nhóm không khai báo chính sách riêng sẽ dùng chính sách chung tương ứng. Có ba điểm dễ hiểu sai:

1. Danh sách `status.order` riêng, khi có phần tử, tạo bộ tổng hợp riêng; không tự bổ sung phần đuôi từ danh sách chung.
2. Bảng `status.http-mapping` riêng, khi có phần tử, tạo bộ ánh xạ riêng; không tự trộn từng khóa với bảng chung.
3. Tập `roles` riêng có phần tử thay thế tập vai trò chung. Trong phiên bản này, tập riêng rỗng vẫn rơi về tập chung; không nên dùng `roles: []` để cố xóa hạn chế vai trò đã cấu hình ở cấp chung.

Ngoài ra, bean `StatusAggregator` hoặc `HttpCodeStatusMapper` có qualifier đúng tên nhóm được ưu tiên hơn cấu hình thuộc tính cho thành phần đó. Đây là hành vi trong [mã tự cấu hình nhóm của Boot 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/AutoConfiguredHealthEndpointGroups.java).

## 4. Tùy chỉnh mức hiển thị

### 4.1. Phân biệt components với details

Một phản hồi có cấu trúc minh họa như sau:

```json
{
  "status": "DEGRADED",
  "components": {
    "catalog": {
      "status": "DEGRADED",
      "details": {
        "mode": "simulated"
      }
    },
    "ping": {
      "status": "UP"
    }
  }
}
```

- `status` ở ngoài cùng: kết quả tổng hợp của nhóm.
- `components`: các thành phần được hiển thị cùng trạng thái tương ứng.
- `details`: dữ liệu chẩn đoán bổ sung do một bộ kiểm tra cung cấp.

`show-components` điều khiển việc hiển thị cây thành phần. `show-details` điều khiển dữ liệu chi tiết. Tên thành phần cũng có thể làm lộ kiến trúc, kể cả khi `details` đã bị ẩn.

Cả hai dùng các giá trị:

| Giá trị | Ý nghĩa đối với thông tin tương ứng |
| --- | --- |
| `never` | Không hiển thị |
| `when-authorized` | Hiển thị khi người gọi đáp ứng điều kiện được phép xem |
| `always` | Hiển thị cho mọi người gọi đã đi qua lớp kiểm soát truy cập |

Mặc định `show-details` là `never`. Nếu `show-components` không được chỉ định sau khi giải quyết cấu hình kế thừa, chính sách hiển thị thành phần dựa trên `show-details`. Để tránh ảnh hưởng khó nhận ra từ cấu hình chung, các ví dụ dưới đây ghi rõ cả hai.

### 4.2. Hai chính sách thường dùng

Nhóm dành cho máy chỉ cần trạng thái:

```yaml
management:
  endpoint:
    health:
      group:
        traffic:
          include: [catalog, ping]
          show-components: never
          show-details: never
```

Nhóm dành cho người vận hành có quyền:

```yaml
management:
  endpoint:
    health:
      group:
        ops:
          include: [catalog, ping]
          show-components: when-authorized
          show-details: when-authorized
          roles: [OPS]
```

Các đoạn YAML trong phần giải thích là những cấu hình thay thế hoặc bổ sung theo đúng vị trí; không dán nhiều khóa `management` trùng nhau trong cùng một tài liệu YAML. Phần thực hành cung cấp một tệp hoàn chỉnh.

Nếu cần công khai trạng thái từng thành phần nhưng ẩn dữ liệu chẩn đoán, có thể chọn `show-components: always` và `show-details: never`. Cần chủ động chấp nhận việc công khai tên thành phần.

## 5. Vai trò được xem chi tiết khác quyền truy cập URL

Với `when-authorized`, Actuator xác định người gọi có được xem thông tin dựa trên ngữ cảnh bảo mật. Khi không có vai trò hiệu lực được cấu hình, người đã xác thực được xem; khi có danh sách vai trò, khớp ít nhất một vai trò là đủ. Hợp đồng ngữ cảnh bảo mật gồm principal hiện tại và phép kiểm tra vai trò, được mô tả trong [SecurityContext của Actuator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/SecurityContext.html).

Chẳng hạn:

```properties
management.endpoint.health.group.ops.roles=OPS,SUPPORT
```

Nghĩa là người gọi có vai trò `OPS` **hoặc** `SUPPORT` đủ điều kiện, với các chế độ hiển thị đang đặt là `when-authorized`.

Các thuộc tính này không:

- Tạo người dùng hay mật khẩu.
- Xác thực một yêu cầu HTTP.
- Tự sinh quy tắc `hasRole(...)` để chặn URL.
- Đảm bảo người thiếu vai trò nhận HTTP 403.

Nếu bộ lọc bảo mật cho phép người ẩn danh tới nhóm, họ vẫn có thể nhận JSON chỉ có trạng thái. Mã phản hồi khi đó do trạng thái sức khỏe và bộ ánh xạ quyết định.

Trong cấu hình Servlet thông thường, `User.withUsername(...).roles("OPS")` tạo quyền `ROLE_OPS`; ví dụ trong bài dùng `roles: [OPS]` tương ứng. Hệ thống dùng JWT hoặc quyền tự định nghĩa cần ánh xạ quyền thành vai trò phù hợp với cách kiểm tra của ứng dụng, thay vì đoán từ tên claim.

Nếu muốn **chặn cả URL ops**, quy tắc đường dẫn phải đứng trước quy tắc cho phép health tổng quát:

```java
// Đoạn thay thế phần authorizeHttpRequests trong SecurityFilterChain;
// đây không phải một lớp Java chạy độc lập.
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/actuator/health/ops", "/actuator/health/ops/**")
        .hasRole("OPS")
    .requestMatchers("/actuator/health", "/actuator/health/**")
        .permitAll()
    .anyRequest().denyAll());
```

Cách này thay đổi hợp đồng truy cập: yêu cầu không đủ quyền có thể bị chặn trước khi nhận kết quả health. Phải kiểm thử theo cơ chế xác thực thực tế. Thứ tự matcher và việc chỉ áp dụng quy tắc khớp đầu tiên được giải thích trong [tài liệu phân quyền yêu cầu của Spring Security](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).

## 6. Thứ tự trạng thái là chính sách tổng hợp

### 6.1. Phần tử đứng trước có ưu tiên cao hơn

Mặc định của `SimpleStatusAggregator` trong Boot 3.3.13 là:

```text
DOWN -> OUT_OF_SERVICE -> UP -> UNKNOWN
```

Đây là thứ tự chọn kết quả khi có nhiều trạng thái, không phải thứ tự chạy bộ kiểm tra hay thứ tự sắp xếp khóa JSON.

Ví dụ, với tập `{UP, DOWN}`, kết quả là `DOWN`; với `{UP, UNKNOWN}`, mặc định kết quả là `UP`.

Một danh sách riêng có thể đặt `UNKNOWN` trước `UP` để tín hiệu thiếu thông tin thắng tín hiệu khỏe. Khi chọn chính sách đó, nhóm có thể báo chưa sẵn sàng chỉ vì một thành phần chưa xác định được trạng thái.

### 6.2. Trạng thái tùy chỉnh phải có vị trí trong danh sách

Ví dụ:

```yaml
management:
  endpoint:
    health:
      group:
        ops:
          status:
            order:
              - DOWN
              - OUT_OF_SERVICE
              - DEGRADED
              - UNKNOWN
              - UP
```

Trong chính sách này, `DEGRADED` biểu thị hoạt động suy giảm nhưng chưa phải ngừng phục vụ hoàn toàn.

Danh sách được dùng trọn vẹn. Cấu hình chỉ `[DEGRADED, UP]` có thể khiến `DOWN` bị loại khỏi các trạng thái được bộ tổng hợp xem xét. Đây là lỗi nghiêm trọng dù YAML hợp lệ.

`SimpleStatusAggregator` chỉ chọn giữa các trạng thái có trong thứ tự đã biết. Nếu không có trạng thái đầu vào nào được biết, kết quả là `UNKNOWN`. Vì vậy, bộ kiểm tra trả `DEGRADED` nhưng danh sách chỉ biết các trạng thái mặc định có thể bị bỏ qua khi một thành phần khác trả `UP`. Cần đồng bộ tập trạng thái của bộ kiểm tra với chính sách của mọi nhóm sử dụng nó, kể cả health tổng thể. Hành vi mặc định và cách lọc này được thể hiện trong [SimpleStatusAggregator 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java).

### 6.3. Hai nhóm có thể ưu tiên khác nhau

Giả sử một nhóm ưu tiên trạng thái chưa xác định trước suy giảm, nhóm kia ưu tiên suy giảm trước chưa xác định:

| Nhóm | Thứ tự liên quan | Đầu vào giả định | Kết quả |
| --- | --- | --- | --- |
| `traffic` | `DOWN, OUT_OF_SERVICE, UNKNOWN, DEGRADED, UP` | `DEGRADED`, `UNKNOWN` | `UNKNOWN` |
| `ops` | `DOWN, OUT_OF_SERVICE, DEGRADED, UNKNOWN, UP` | `DEGRADED`, `UNKNOWN` | `DEGRADED` |

Đây là lựa chọn chính sách, cần có lý do vận hành. Giữ `DOWN` và `OUT_OF_SERVICE` ở đầu nếu chúng phải luôn thắng các trạng thái còn lại. Không đảo thứ tự chỉ để làm màn hình giám sát chuyển xanh.

## 7. Ánh xạ trạng thái sang HTTP

### 7.1. Ánh xạ chỉ dùng trạng thái đã tổng hợp

Sau khi có trạng thái nhóm, bộ ánh xạ chuyển mã trạng thái sức khỏe thành mã HTTP. API mặc định cung cấp một bộ ánh xạ dựa trên bảng tên trạng thái và mã số: [SimpleHttpCodeStatusMapper](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html).

Trong cấu hình mặc định:

| Trạng thái | HTTP |
| --- | --- |
| `DOWN` | 503 |
| `OUT_OF_SERVICE` | 503 |
| `UP` | 200 |
| `UNKNOWN` | 200 |
| Trạng thái chưa được ánh xạ | 200 |

Đừng suy luận `UNKNOWN` mặc định tương đương 503. Nếu bên tiêu thụ yêu cầu “không biết thì không nhận lưu lượng”, cần cấu hình rõ.

### 7.2. Khai báo lại đầy đủ các trường hợp cần giữ

Ví dụ nhóm chẩn đoán coi `DEGRADED` là một phản hồi đọc được thành công:

```yaml
management:
  endpoint:
    health:
      group:
        ops:
          status:
            http-mapping:
              down: 503
              out-of-service: 503
              degraded: 200
              unknown: 503
              up: 200
```

Khi tự cung cấp bảng, phải giữ rõ các ánh xạ như `down` và `out-of-service` nếu vẫn muốn chúng trả 503. Chỉ thêm `degraded: 200` không bảo toàn các ánh xạ mặc định.

Không dùng HTTP 401/403 làm tín hiệu bộ kiểm tra bị lỗi. Các mã đó nói về xác thực/phân quyền; nhóm không sẵn sàng phục vụ thường dùng 503. Dù có thể gán số tùy ý, hợp đồng HTTP cần có nghĩa với thành phần tiêu thụ.

### 7.3. Cùng trạng thái, khác HTTP

Hai nhóm cùng tổng hợp ra `DEGRADED` có thể trả:

| Nhóm | JSON | HTTP | Ý nghĩa của ví dụ |
| --- | --- | --- | --- |
| `ops` | `{"status":"DEGRADED"}` | 200 | Công cụ chẩn đoán phải đọc trường trạng thái để cảnh báo |
| `traffic` | `{"status":"DEGRADED"}` | 503 | Thành phần điều phối lưu lượng không coi nhóm là sẵn sàng |

Mã 200 của nhóm `ops` là quyết định phục vụ ví dụ, không phải quy tắc chung cho trạng thái suy giảm. Nếu công cụ chỉ coi HTTP 2xx là “khỏe”, nó sẽ bỏ sót tình trạng này. Hãy thống nhất trước công cụ sẽ đọc mã HTTP, trường JSON hay cả hai.

## 8. Thực hành hoàn chỉnh: hai nhóm và hai mức quyền

### 8.1. Chuẩn bị dự án độc lập

Ví dụ không cần cơ sở dữ liệu hay dịch vụ ngoài. Bộ kiểm tra `catalog` trả trạng thái mô phỏng từ tham số khởi động, giúp quan sát chính sách mà không phải tạo sự cố thật.

Dùng JDK 21 và Maven 3.6.3 trở lên. Tạo thư mục dự án riêng với cấu trúc:

```text
health-group-demo/
  pom.xml
  src/main/java/example/HealthGroupApplication.java
  src/main/resources/application.yml
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>health-group-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>21</java.version>
  </properties>
  <dependencies>
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
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

### 8.2. Ứng dụng và người dùng thử nghiệm

Tệp `src/main/java/example/HealthGroupApplication.java`:

```java
package example;

import java.util.Locale;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
public class HealthGroupApplication {

    public static void main(String[] args) {
        SpringApplication.run(HealthGroupApplication.class, args);
    }

    @Bean
    HealthIndicator catalogHealthIndicator(
            @Value("${demo.catalog-status:DEGRADED}") String configuredStatus) {
        String code = configuredStatus.trim().toUpperCase(Locale.ROOT);
        return () -> Health.status(code)
                .withDetail("mode", "simulated")
                .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("operator")
                        .password("{noop}operator-pass")
                        .roles("OPS")
                        .build(),
                User.withUsername("viewer")
                        .password("{noop}viewer-pass")
                        .roles("VIEWER")
                        .build());
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health", "/actuator/health/**")
                    .permitAll()
                .anyRequest().denyAll());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

Bean `catalogHealthIndicator` có ID health là `catalog`; hậu tố `HealthIndicator` được loại khi xác định ID. Bộ kiểm tra dựng một `Health` gồm trạng thái và dữ liệu minh họa; API xây dựng kết quả được mô tả trong [Health 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Health.html).

Các tài khoản và mật khẩu trên chỉ phục vụ chạy cục bộ. `{noop}` giúp giảm phần thiết lập của thí nghiệm; hệ thống thật cần cơ chế lưu mật khẩu và truyền thông phù hợp. Dữ liệu `mode` là dữ liệu giả, không chứa thông tin kết nối hay bí mật.

Quy tắc bảo mật cho phép đọc mọi đường dẫn health, để ta quan sát việc thiếu vai trò chỉ làm ẩn thông tin. HTTP Basic vẫn xử lý thông tin xác thực được gửi lên, nhờ đó người có vai trò `OPS` được nhận diện.

### 8.3. Cấu hình hoàn chỉnh

Tệp `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-components: never
      show-details: never
      status:
        order: [DOWN, OUT_OF_SERVICE, UNKNOWN, DEGRADED, UP]
        http-mapping:
          down: 503
          out-of-service: 503
          unknown: 503
          degraded: 503
          up: 200
      group:
        traffic:
          include: [catalog, ping]
          show-components: never
          show-details: never
        ops:
          include: [catalog, ping]
          show-components: when-authorized
          show-details: when-authorized
          roles: [OPS]
          status:
            order: [DOWN, OUT_OF_SERVICE, DEGRADED, UNKNOWN, UP]
            http-mapping:
              down: 503
              out-of-service: 503
              unknown: 503
              degraded: 200
              up: 200
```

Ở đây:

- `traffic` kế thừa thứ tự và bảng HTTP chung.
- `ops` có thứ tự và bảng HTTP riêng.
- Cả hai dùng `catalog` và bộ kiểm tra `ping` được Boot tự cấu hình.
- Health tổng thể cũng biết `DEGRADED`, tránh bỏ sót trạng thái tùy chỉnh khi gộp với `UP`.
- Các thành phần khác được tự cấu hình có thể xuất hiện trong health tổng thể, nhưng không thuộc hai nhóm vì danh sách `include` đã giới hạn rõ.

Bật/tắt endpoint, chọn thành viên và công bố qua HTTP là các quyết định khác nhau. Cú pháp nhóm, điều kiện hiển thị và các ánh xạ mặc định được trình bày trong [tài liệu health endpoint của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

### 8.4. Biên dịch và chạy

Từ thư mục chứa `pom.xml`:

```shell
mvn package
java -jar target/health-group-demo-1.0.0.jar
```

Maven tải các phụ thuộc nếu chưa có trong bộ nhớ đệm. Ví dụ này có phụ thuộc Spring nên biên dịch và đóng gói bằng Maven; không dùng riêng `javac HealthGroupApplication.java` khi chưa thiết lập classpath.

Chờ ứng dụng khởi động xong trước khi kiểm tra. Các lệnh sau dùng `curl` trong Bash; với PowerShell, gọi `curl.exe` để tránh nhầm alias. Phản hồi JSON dưới đây được trình bày lại với khoảng trắng cho dễ đọc; thứ tự khóa không phải hợp đồng.

Đọc nhóm `ops` không xác thực:

```shell
curl -s -i http://localhost:8080/actuator/health/ops
```

Mã HTTP là **200**, nội dung JSON:

```json
{"status":"DEGRADED"}
```

Đọc cùng nhóm bằng người dùng không có vai trò vận hành:

```shell
curl -s -i -u viewer:viewer-pass http://localhost:8080/actuator/health/ops
```

Mã HTTP vẫn là **200**, nội dung JSON vẫn chỉ có:

```json
{"status":"DEGRADED"}
```

Đọc bằng người dùng có vai trò `OPS`:

```shell
curl -s -i -u operator:operator-pass http://localhost:8080/actuator/health/ops
```

Mã HTTP là **200**; JSON có thành phần và dữ liệu chẩn đoán:

```json
{
  "status": "DEGRADED",
  "components": {
    "catalog": {
      "status": "DEGRADED",
      "details": {
        "mode": "simulated"
      }
    },
    "ping": {
      "status": "UP"
    }
  }
}
```

Cuối cùng, đọc nhóm `traffic`:

```shell
curl -s -i http://localhost:8080/actuator/health/traffic
```

Mã HTTP là **503**, JSON:

```json
{"status":"DEGRADED"}
```

Ngay cả khi gửi tài khoản `operator` tới `traffic`, nhóm đó vẫn ẩn thành phần và chi tiết vì hai chính sách đều là `never`.

Để chỉ in mã HTTP trong Bash:

```shell
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/actuator/health/ops
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/actuator/health/traffic
```

Stdout chính xác của hai lệnh, khi ứng dụng đang chạy với cấu hình trên:

```text
200
503
```

Trong PowerShell trên Windows, dùng `curl.exe` và thay `/dev/null` bằng `NUL` cho các lệnh chỉ in mã HTTP.

### 8.5. Kiểm tra trường hợp lỗi thật sự và trường hợp chưa biết

Dừng tiến trình bằng Ctrl+C, rồi chạy lại với:

```shell
java -jar target/health-group-demo-1.0.0.jar --demo.catalog-status=DOWN
```

Sau khi khởi động xong, cả `ops` lẫn `traffic` phải có trạng thái `DOWN` và HTTP **503**. Điều này kiểm chứng bảng riêng của `ops` vẫn giữ ánh xạ cho lỗi nghiêm trọng.

Dừng và chạy lại:

```shell
java -jar target/health-group-demo-1.0.0.jar --demo.catalog-status=UNKNOWN
```

Cả hai nhóm phải có trạng thái `UNKNOWN` và HTTP **503**, vì cả hai thứ tự hiệu lực đều đặt `UNKNOWN` trước `UP`. Đó là chính sách của ví dụ, khác mặc định `UP` đứng trước `UNKNOWN`.

Ma trận kiểm chứng:

| Trạng thái catalog | Nhóm | Người gọi | Trạng thái nhóm | HTTP | components/details |
| --- | --- | --- | --- | --- | --- |
| `DEGRADED` | `ops` | Ẩn danh | `DEGRADED` | 200 | Không |
| `DEGRADED` | `ops` | `viewer` | `DEGRADED` | 200 | Không |
| `DEGRADED` | `ops` | `operator` | `DEGRADED` | 200 | Có |
| `DEGRADED` | `traffic` | `operator` hoặc ẩn danh | `DEGRADED` | 503 | Không |
| `DOWN` | Cả hai | Bất kỳ người gọi được phép | `DOWN` | 503 | Theo chính sách và vai trò |
| `OUT_OF_SERVICE` | Cả hai | Bất kỳ người gọi được phép | `OUT_OF_SERVICE` | 503 | Theo chính sách và vai trò |
| `UNKNOWN` | Cả hai | Bất kỳ người gọi được phép | `UNKNOWN` | 503 | Theo chính sách và vai trò |
| `UP` | Cả hai | Bất kỳ người gọi được phép | `UP` | 200 | Theo chính sách và vai trò |

Chỉ dùng các trạng thái đã quy định cho thí nghiệm. Một chuỗi lạ như `CUSTOM_X` chưa có trong danh sách có thể bị bộ tổng hợp bỏ qua khi đi cùng `ping=UP`; HTTP mapping cho `CUSTOM_X` khi ấy cũng không được dùng vì trạng thái nhóm không phải `CUSTOM_X`.

## 9. Khi nào cần bean riêng cho nhóm?

Thuộc tính phù hợp khi chính sách là danh sách ưu tiên và bảng ánh xạ cố định. Nếu cần thuật toán khác, có thể đăng ký bean có qualifier đúng tên nhóm.

Ví dụ dưới đây là **cấu hình thay thế** cho phần chính sách trạng thái của nhóm `ops`, không phải bước bắt buộc của thí nghiệm. Nếu áp dụng, đặt lớp này trong cùng package `example`; không đồng thời kỳ vọng các thuộc tính `ops.status` còn là nguồn quyết định cho hai thành phần đã thay bằng bean.

```java
package example;

import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.actuate.health.HttpCodeStatusMapper;
import org.springframework.boot.actuate.health.SimpleHttpCodeStatusMapper;
import org.springframework.boot.actuate.health.SimpleStatusAggregator;
import org.springframework.boot.actuate.health.StatusAggregator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OpsHealthPolicy {

    @Bean
    @Qualifier("ops")
    StatusAggregator opsStatusAggregator() {
        return new SimpleStatusAggregator(
                "DOWN", "OUT_OF_SERVICE", "DEGRADED", "UNKNOWN", "UP");
    }

    @Bean
    @Qualifier("ops")
    HttpCodeStatusMapper opsHttpCodeStatusMapper() {
        return new SimpleHttpCodeStatusMapper(Map.of(
                "DOWN", 503,
                "OUT_OF_SERVICE", 503,
                "DEGRADED", 200,
                "UNKNOWN", 503,
                "UP", 200));
    }
}
```

Hai bean trên cố ý dùng thuật toán có sẵn để chỉ ra cách định vị chính sách theo nhóm. Constructor và phương thức tổng hợp được mô tả trong [API SimpleStatusAggregator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.html).

Tên qualifier phải khớp `ops`. Tránh vô tình đăng ký một bean không có phạm vi nhóm rồi làm thay đổi chính sách chung. Nếu tự viết thuật toán, cần quy định và kiểm thử cả tập rỗng, trạng thái lạ và trường hợp nhiều lỗi đồng thời.

## 10. Áp dụng cho liveness và readiness

Liveness và readiness cũng là health group nên có thể nhận các chính sách hiển thị, thứ tự và ánh xạ riêng. Tuy nhiên, cần giữ ý nghĩa vận hành:

- Liveness phản ánh khả năng tiếp tục sống của tiến trình; một dịch vụ ngoài bị lỗi không tự động có nghĩa cần khởi động lại ứng dụng.
- Readiness phản ánh khả năng nhận lưu lượng theo hợp đồng ứng dụng.
- `OUT_OF_SERVICE` của readiness phải được bộ tổng hợp nhận biết và ánh xạ thành mã HTTP thất bại phù hợp; tránh làm nó rơi về 200 khi thay bảng ánh xạ.
- Tên nhóm `traffic` trong ví dụ không tự cấu hình probe của Kubernetes. Thành phần điều phối phải được trỏ rõ tới URL định dùng.

Ví dụ phần bổ sung vào cấu hình hiện có, khi muốn dùng probe dựng sẵn ở môi trường cục bộ:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: [readinessState]
          show-components: never
          show-details: never
          status:
            order: [DOWN, OUT_OF_SERVICE, UNKNOWN, UP]
            http-mapping:
              down: 503
              out-of-service: 503
              unknown: 503
              up: 200
```

Đây là chính sách riêng cho nhóm `readiness`, không thay trạng thái của `ApplicationAvailability`. Nếu quyết định thêm phụ thuộc vào readiness, cần xác định phụ thuộc đó có thiết yếu với việc phục vụ yêu cầu hay không và hệ thống sẽ xử lý sự cố diện rộng ra sao.

## 11. Lỗi thường gặp và cách khoanh vùng

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Người ẩn danh đọc được trạng thái dù đã đặt `roles` | `roles` chỉ tham gia quyền xem thông tin, URL đang được cho phép | Nếu cần chặn URL, bổ sung quy tắc Spring Security |
| Người có vai trò vẫn không thấy thành phần | `show-components` hiệu lực là `never`, sai vai trò hoặc chưa xác thực thành công | Kiểm tra cả hai chế độ hiển thị và quyền thực tế |
| JSON không có `details` dù được phép xem | Bộ kiểm tra không thêm dữ liệu, hoặc chính sách đang ẩn | Kiểm tra kết quả `Health` và `show-details` |
| `DOWN` lại trả 200 | Bảng HTTP riêng thiếu `down`, hoặc trạng thái tổng hợp không còn là `DOWN` | Kiểm tra JSON trước, rồi bảng ánh xạ hiệu lực |
| Một thành phần `DOWN` nhưng nhóm lại `UP` | Danh sách riêng đã bỏ `DOWN`, hoặc thành phần không thuộc nhóm | Kiểm tra tư cách thành viên và toàn bộ `status.order` |
| Thêm ánh xạ `DEGRADED` nhưng không thấy tác dụng | Trạng thái đó chưa tham gia hoặc không thắng bước tổng hợp | Khai báo thứ tự và thử với tập trạng thái cụ thể |
| Đổi thứ tự nhưng HTTP không đổi | Cả hai trạng thái cùng ánh xạ tới một mã | So sánh thêm trường `status` trong JSON |
| YAML thay đổi nhưng hành vi không đổi | Sai profile, nguồn cấu hình ưu tiên cao hơn, hoặc bean riêng thay chính sách | Kiểm tra cấu hình hiệu lực và qualifier |
| Nhận 401/403 thay vì phản hồi health | Yêu cầu bị cơ chế bảo mật chặn | Kiểm tra xác thực và matcher trước khi điều tra bộ tổng hợp |
| Khởi động lỗi khi khai báo `include` | Sai ID contributor hoặc contributor không tồn tại | Sửa đúng ID; không tắt kiểm tra tư cách thành viên chỉ để che lỗi |

## 12. Tự kiểm tra hiểu bài

1. Vì sao `show-details: never` không bảo đảm tên các thành phần cũng bị ẩn?
2. Nhóm dùng `roles: [OPS]` và URL `permitAll()` sẽ phản hồi thế nào cho người có vai trò `VIEWER`?
3. Điều gì xảy ra nếu danh sách ưu tiên chỉ gồm `[DEGRADED, UP]` trong khi một thành phần trả `DOWN` và thành phần khác trả `UP`?
4. Vì sao bảng chỉ có `degraded: 200` có thể làm mất HTTP 503 mong muốn cho `DOWN`?
5. Nếu nhóm `ops` trả HTTP 200 với JSON `DEGRADED`, công cụ cảnh báo phải đọc gì?
6. Vì sao phải kiểm thử lại `OUT_OF_SERVICE` sau khi tùy chỉnh chính sách readiness?

Gợi ý đối chiếu:

1. `show-components` có thể được cấu hình độc lập và đang cho phép hiển thị.
2. Yêu cầu được vào nhóm nhưng không đủ quyền xem thông tin; mã HTTP vẫn theo trạng thái nhóm.
3. Với `SimpleStatusAggregator`, `DOWN` không được nhận biết trong danh sách đó; `UP` có thể được chọn.
4. Bảng tùy chỉnh thay bảng mặc định; trạng thái không có ánh xạ rơi về 200.
5. Phải đọc trạng thái JSON theo hợp đồng đã thống nhất, thay vì chỉ nhìn HTTP 2xx.
6. Để bảo đảm trạng thái không nhận lưu lượng vẫn thắng bước tổng hợp và trở thành mã HTTP mà probe nhận là thất bại.

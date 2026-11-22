# Giới hạn thông tin cấu trúc và cấu hình được công bố trong production

Actuator giúp người vận hành quan sát ứng dụng đang chạy. Chính những dữ liệu hữu ích cho chẩn đoán cũng có thể tiết lộ cách hệ thống được tổ chức: tên bean, đường dẫn API, nguồn cấu hình, lớp triển khai, thông tin bản dựng hoặc địa chỉ dịch vụ nội bộ.

Trong production, cần xác định **ai cần biết thông tin nào, qua kênh nào và trong khoảng thời gian nào**. Một bộ cân bằng tải thường chỉ cần biết ứng dụng có sẵn sàng nhận yêu cầu hay không; nó không cần danh sách bean hoặc toàn bộ cấu hình.

Bài này sử dụng thuộc tính của **Spring Boot 3.3.x**. Ví dụ Java dành cho **Java 21, Spring MVC/Servlet và Spring Security 6.x**; đó là lớp cấu hình tích hợp vào một ứng dụng sẵn có, không phải chương trình Java độc lập. Các quy tắc quyền truy cập trong ví dụ cần đi cùng cơ chế xác thực của ứng dụng.

## 1. Dữ liệu cần giới hạn rộng hơn mật khẩu

Có hai nhóm cần phân biệt:

- **Giá trị cấu hình nhạy cảm**: mật khẩu, token, chuỗi kết nối có thông tin đăng nhập hoặc khóa riêng.
- **Thông tin cấu trúc và ngữ cảnh vận hành**: tên khóa, tên nguồn cấu hình, profile, tên lớp, đường dẫn, dịch vụ phụ thuộc, thông tin hệ điều hành và bản dựng.

Nhóm thứ hai có thể vẫn xuất hiện sau khi các giá trị được thay bằng `******`. Ví dụ, tên `partner.payment.internal-url` đã tiết lộ một phụ thuộc tích hợp; một nguồn mang đường dẫn tệp có thể tiết lộ cách triển khai.

| Endpoint hoặc loại dữ liệu | Thông tin có thể công bố | Cách xử lý thường phù hợp |
| --- | --- | --- |
| `env` | Thuộc tính môi trường, nguồn, profile và nguồn gốc khai báo | Đóng trong chế độ production thông thường; chỉ mở có kiểm soát khi cần chẩn đoán |
| `configprops` | Nhóm cấu hình đã liên kết, thuộc tính bean và đầu vào | Giới hạn cho người vận hành có nhiệm vụ cụ thể |
| `beans`, `mappings`, `conditions` | Bean, lớp, đường dẫn API và kết quả điều kiện tự cấu hình | Giữ nội bộ; không công bố chỉ để tiện tra cứu |
| `health` | Trạng thái, tên thành phần và chi tiết kiểm tra | Chỉ trả phần tối thiểu cho đối tượng gọi công khai |
| `info` | Thông tin do các contributor cung cấp, có thể gồm Git và bản dựng | Xét duyệt từng trường trước khi mở |
| `threaddump`, `heapdump`, `logfile` | Luồng thực thi, bộ nhớ hoặc log | Xử lý như dữ liệu điều tra nội bộ; có thể chứa dữ liệu nhạy cảm |
| `httpexchanges` | Thông tin trao đổi HTTP đã được thu thập | Xét cả cấu hình thu thập lẫn quyền đọc |
| `metrics`, `prometheus` | Tên chỉ số, nhãn và đặc điểm vận hành | Chỉ mở cho hệ thống giám sát cần dùng; rà soát nhãn |

Một số endpoint chỉ tồn tại khi có phụ thuộc, bean hoặc cấu hình tương ứng. Không thấy endpoint trong một lần chạy không chứng minh rằng lần triển khai tiếp theo vẫn sẽ không có nó.

Ngoài đọc thông tin, một số endpoint còn có thao tác thay đổi trạng thái, chẳng hạn `loggers`. Khi xét quyền, cần xem cả thao tác được phép thực hiện, không chỉ tên endpoint.

## 2. Năm lớp kiểm soát có chức năng riêng

| Lớp | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Kích hoạt endpoint | Có cần endpoint này trong ứng dụng không? | `management.endpoint.env.enabled` |
| Công bố theo kênh | Endpoint có được ánh xạ ra HTTP hoặc JMX không? | `management.endpoints.web.exposure.include` |
| Khả năng tiếp cận qua mạng | Những máy hoặc tiến trình nào kết nối được? | Cổng quản trị riêng, địa chỉ lắng nghe, quy tắc mạng |
| Xác thực và phân quyền | Người gọi là ai và được đọc endpoint nào? | `SecurityFilterChain`, vai trò `OPS` |
| Nội dung phản hồi | Người gọi được nhận những trường và giá trị nào? | `show-values`, `show-details`, `show-components` |

Một người có quyền xem giá trị cũng cần có quyền truy cập endpoint. Một endpoint đã được ánh xạ HTTP vẫn có thể bị lớp bảo mật chặn. Một cổng nằm trong mạng nội bộ vẫn cần được giới hạn quyền theo đúng đối tượng sử dụng.

Trong Spring Boot 3.3, endpoint bị vô hiệu hóa được loại khỏi application context theo cơ chế Actuator. Nếu chỉ muốn thay đổi kênh công bố, dùng cấu hình exposure. Thứ tự `exclude` thắng `include`; vì vậy cần kiểm tra cả hai khi một endpoint không xuất hiện như dự kiến.

Cơ chế kích hoạt và công bố được mô tả tại [Actuator Endpoints — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

## 3. Thiết lập production theo danh sách cho phép

Một chính sách khởi đầu có thể là:

- Chỉ kích hoạt và công bố `health`.
- `health` trả trạng thái tổng quát, không có cây thành phần hoặc chi tiết.
- Không công bố endpoint qua JMX trong phương án triển khai này.
- Không mở trang liệt kê liên kết Actuator.
- Giữ giá trị của `env` và `configprops` bị che nếu sau này chúng được bật có chủ đích.
- Không tự xuất các thông tin Git, bản dựng hoặc môi trường qua các contributor có sẵn của `info`.

Đặt nội dung sau trong `src/main/resources/application-prod.yml`:

```yaml
spring:
  jmx:
    enabled: false

management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include:
          - health
      discovery:
        enabled: false
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      enabled: true
      show-details: never
      show-components: never
    env:
      show-values: never
    configprops:
      show-values: never
  info:
    defaults:
      enabled: false
    env:
      enabled: false
    git:
      enabled: false
    build:
      enabled: false
    java:
      enabled: false
    os:
      enabled: false
    process:
      enabled: false
```

Phải kích hoạt profile `prod` trong tiến trình triển khai, chẳng hạn thông qua biến `SPRING_PROFILES_ACTIVE=prod`. Chỉ tạo tệp `application-prod.yml` chưa làm profile tự hoạt động.

### Cách đọc cấu hình này

`enabled-by-default: false` chuyển việc kích hoạt endpoint sang lựa chọn tường minh. `health.enabled: true` mở lại endpoint cần dùng; danh sách HTTP chỉ chứa `health`.

`show-details: never` giảm chi tiết của kết quả kiểm tra; `show-components: never` giảm việc công bố cây thành phần. Một hệ thống hoạt động bình thường, không có cấu hình bổ sung làm thay đổi phản hồi, có thể trả:

```json
{"status":"UP"}
```

Trạng thái có thể khác `UP`, kèm mã HTTP tương ứng. Việc giảm dữ liệu phản hồi không được biến tình trạng lỗi thành kết quả thành công giả.

`env.show-values: never` và `configprops.show-values: never` chỉ thiết lập chính sách giá trị; hai dòng này không tự kích hoạt các endpoint đang bị tắt.

`discovery.enabled: false` tắt trang liên kết ở đường dẫn gốc Actuator. Các đường dẫn endpoint được công bố vẫn cần chính sách truy cập riêng. Đổi base path từ `/actuator` sang tên khác cũng chỉ là đổi vị trí truy cập.

### Tác dụng và giới hạn của phần `info`

Trong Spring Boot 3.3, contributor Git hoặc bản dựng có thể hoạt động khi tài nguyên tương ứng tồn tại. Cấu hình trên tắt những contributor có sẵn được liệt kê, thay vì trông chờ dữ liệu bản dựng luôn giống môi trường phát triển.

`management.info.defaults.enabled: false` tắt các contributor vốn được bật mặc định; không nên diễn giải nó thành lệnh xóa mọi thông tin ứng dụng có thể tự công bố. Một `InfoContributor` do ứng dụng viết cần được xét riêng.

Nếu sau này mở `info`, kiểm tra phản hồi thực tế và chỉ giữ các trường phục vụ nhu cầu đã xác định. Không đưa mật khẩu vào `info.*` rồi kỳ vọng chính sách che của `env` tự bảo vệ endpoint này.

## 4. Che giá trị vẫn cần đi cùng giảm công bố

Trong Spring Boot 3.3, `env` và `configprops` mặc định che giá trị. Có ba chính sách cần biết:

| Giá trị `show-values` | Ý nghĩa |
| --- | --- |
| `never` | Giữ giá trị bị che |
| `when-authorized` | Cho người được xác định đủ quyền xem giá trị chưa che |
| `always` | Hiển thị giá trị cho mọi người đã truy cập được endpoint, trừ phần bị hàm che tùy chỉnh xử lý |

Cần tách **quyền truy cập endpoint** và **quyền xem giá trị**. Thiết lập `show-values` không thay thế cho kiểm soát truy cập HTTP.

Khi dùng `when-authorized`, cấu hình `roles` của endpoint xác định vai trò được xem giá trị. Nếu không cấu hình vai trò, mặc định mọi người dùng đã xác thực đều được coi là đủ quyền xem giá trị. Cần ghi rõ vai trò vận hành thay vì dựa vào ý nghĩa chung “đã đăng nhập”.

Phản hồi đã che vẫn có thể có:

- Tên thuộc tính hoặc nhóm cấu hình.
- Tên nguồn, profile, đường dẫn tệp và vị trí khai báo.
- Cấu trúc đối tượng giúp suy ra các khả năng đang được sử dụng.

Vì vậy, một yêu cầu vận hành chỉ cần biết ứng dụng còn sống không đủ lý do để công bố toàn bộ `env`, kể cả khi `show-values=never`.

Nếu dùng `SanitizingFunction` tùy chỉnh, nó có thể tiếp tục che giá trị ngay khi chính sách cho phép hiển thị. Cần kiểm chứng kết quả thực tế bằng dữ liệu mẫu không nhạy cảm. Phạm vi che của các endpoint được hỗ trợ không tự mở rộng sang log, endpoint tùy chỉnh, phản hồi lỗi hoặc mọi nội dung trong bộ nhớ.

## 5. Phân quyền HTTP cho ứng dụng Servlet

Giả sử một ứng dụng có các phụ thuộc:

```text
org.springframework.boot:spring-boot-starter-web
org.springframework.boot:spring-boot-starter-actuator
org.springframework.boot:spring-boot-starter-security
```

Lớp dưới đây minh họa hai chuỗi bảo mật:

1. Yêu cầu tới endpoint Actuator được công bố: health có thể gọi không cần đăng nhập; các endpoint còn lại yêu cầu vai trò `OPS`.
2. Yêu cầu còn lại: bị từ chối trong phạm vi ví dụ.

```java
package learning.operations;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class ActuatorSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class))
                    .permitAll()
                .anyRequest().hasRole("OPS"));
        http.httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .anyRequest().denyAll());
        http.httpBasic(withDefaults());
        return http.build();
    }
}
```

Đặt lớp này trong phạm vi quét cấu hình của ứng dụng. Nó chưa bao gồm `main`, cơ chế tạo người dùng hay nhà cung cấp danh tính.

### Những điều phải hiểu trước khi tích hợp

- `EndpointRequest` định vị endpoint theo cơ chế Actuator. Matcher theo `HealthEndpoint.class` bao gồm các đường dẫn thuộc endpoint health, nên cần rà soát cả health group và đường dẫn thành phần.
- `@Order(1)` đặt chuỗi Actuator trước chuỗi tổng quát. Spring Security sử dụng chuỗi phù hợp đầu tiên.
- `hasRole("OPS")` kiểm tra authority `ROLE_OPS` theo quy ước vai trò mặc định của Spring Security.
- Chuỗi thứ hai cố ý từ chối toàn bộ phần còn lại để minh họa một ranh giới đầy đủ. Khi tích hợp vào dịch vụ có API nghiệp vụ, thay nó bằng chính sách nghiệp vụ đã được thiết kế và kiểm thử; sao chép nguyên lớp sẽ làm các API ấy bị từ chối.
- HTTP Basic là cơ chế xác thực mẫu. Với kết nối production, bảo vệ thông tin xác thực bằng HTTPS hoặc cơ chế truyền tin bảo mật đã được thiết kế. Dùng hệ thống danh tính của ứng dụng thay vì thêm tài khoản dùng chung cố định trong mã.
- Ví dụ giữ nguyên bảo vệ CSRF mặc định. Các phép thử ở đây chỉ dùng `GET`.

Khi khai báo một `SecurityFilterChain` tùy chỉnh, cấu hình bảo mật Actuator tự động của Spring Boot nhường quyền kiểm soát cho ứng dụng. Phải bao phủ cả yêu cầu Actuator lẫn các yêu cầu còn lại; không giả định rằng một chuỗi chỉ khớp Actuator sẽ tự bảo vệ luôn API nghiệp vụ.

Với thiết lập production ở phần trước, endpoint ngoài health vẫn bị tắt. Vai trò `OPS` không làm một endpoint đã tắt tự xuất hiện. Chuỗi bảo mật cũng phục vụ trường hợp một endpoint được bật có chủ đích ở chế độ chẩn đoán.

Tham chiếu matcher: [EndpointRequest API — Spring Boot 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html).

## 6. Chẩn đoán có kiểm soát thay vì mở rộng thường trực

Một sự cố cấu hình có thể đòi hỏi đọc `env` hoặc `configprops`. Khi có nhu cầu đó, xác định trước:

- Thuộc tính hoặc nhóm cấu hình cần kiểm tra.
- Người hoặc tài khoản vận hành được phép đọc.
- Bản sao ứng dụng và kênh mạng dùng để chẩn đoán.
- Thời điểm kết thúc, nơi lưu bằng chứng và người chịu trách nhiệm đóng lại quyền.

Có thể chuẩn bị `application-ops.yml` như một cấu hình bổ sung có chủ đích:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - env
          - configprops
  endpoint:
    env:
      enabled: true
      show-values: never
    configprops:
      enabled: true
      show-values: never
```

Phương án này giả định các profile hoạt động theo thứ tự `prod,ops`, với cấu hình production ở phần trước vẫn được nạp. Danh sách HTTP của profile sau được đặt rõ là `health,env,configprops`. Những endpoint khác tiếp tục bị tắt theo chính sách mặc định.

Một tệp profile bổ sung không tự trở thành cơ chế hết hạn. Hệ thống triển khai và quy trình vận hành cần chịu trách nhiệm bật đúng lúc, đóng lại sau khi dùng và kiểm tra cấu hình cuối cùng.

Với lớp bảo mật ở phần 5:

| Người gọi | Health tối thiểu | `env` và `configprops` trong chế độ `prod,ops` |
| --- | --- | --- |
| Chưa xác thực | Có thể đọc | Bị từ chối |
| Đã xác thực, không có vai trò `OPS` | Có thể đọc | Bị từ chối |
| Có vai trò `OPS` | Có thể đọc | Được đọc, nhưng giá trị vẫn bị che bởi `show-values: never` |

Nếu thông tin nguồn và cấu trúc đã đủ để chẩn đoán, giữ nguyên chính sách che. Ưu tiên truy vấn cụ thể như `/actuator/env/demo.region` hoặc `/actuator/configprops/demo` khi cần đọc; tuy nhiên, lựa chọn URL hẹp trong công cụ của người vận hành không tự giới hạn quyền gọi các URL khác của cùng endpoint.

### Khi thật sự cần xem giá trị

Nếu nhiệm vụ yêu cầu xem giá trị rõ, có thể thay chính sách hiển thị trong cấu hình chẩn đoán đã được kiểm soát bằng bốn thuộc tính:

```properties
management.endpoint.env.show-values=when-authorized
management.endpoint.env.roles=OPS
management.endpoint.configprops.show-values=when-authorized
management.endpoint.configprops.roles=OPS
```

Đây là phần thay thế chính sách hiển thị tương ứng, không phải một khối YAML `management` thứ hai được dán vào cùng tài liệu YAML.

Trong chính sách HTTP đang minh họa, người không có vai trò `OPS` bị từ chối trước khi nhận phản hồi. Người có vai trò này có thể xem giá trị chưa che, trừ phần tiếp tục bị hàm che tùy chỉnh xử lý.

Nếu một chính sách HTTP khác cho phép người dùng thông thường truy cập endpoint, `roles=OPS` ở phần hiển thị chỉ giữ giá trị bị che với họ; thông tin cấu trúc vẫn có thể được trả về. Phải xét cả hai lớp quyền.

Kết thúc chẩn đoán, trả tiến trình về profile production thông thường và xác minh lại endpoint từ chính đường truy cập đã dùng. Không chỉ sửa một tệp trong mã nguồn rồi coi việc đóng endpoint đã hoàn tất.

## 7. Tách đường quản trị khi phù hợp với cách triển khai

Nếu sản phẩm có đường quản trị riêng, một cấu hình bổ sung có thể là:

```yaml
server:
  port: 8080

management:
  server:
    port: 9091
    address: 127.0.0.1
```

Khi đó ứng dụng chính dùng cổng `8080`, còn Actuator lắng nghe loopback tại cổng `9091`. Trong Spring Boot 3.3, địa chỉ quản trị riêng chỉ được cấu hình như trên khi cổng quản trị khác cổng chính.

Chọn địa chỉ theo mô hình triển khai thực tế. Loopback thuộc không gian mạng của tiến trình hoặc container; một công cụ giám sát ở máy khác không tự kết nối được vào đó. Nếu cần công cụ ở ngoài kết nối, thiết kế địa chỉ nội bộ, chính sách mạng và xác thực phù hợp.

Các điểm cần kiểm tra:

- Load balancer hoặc reverse proxy có chuyển tiếp cả cổng quản trị ra Internet không?
- Máy không có nhiệm vụ vận hành có kết nối trực tiếp được vào cổng đó không?
- Cổng hoặc đường quản trị riêng có được bảo vệ bằng chính sách quyền dự kiến không?
- Các probe cần gọi cổng nào, và có còn kiểm tra đúng khả năng phục vụ của ứng dụng chính không?

Một cổng quản trị vẫn hoạt động không bảo đảm cổng nghiệp vụ đang hoạt động bình thường. Khi dùng health group hoặc đường bổ sung như `/livez`, `/readyz`, phải xét cả định tuyến và bảo mật của những đường này.

Tham chiếu cách đặt cổng và địa chỉ: [Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### Kiểm tra cả JMX và các kênh khác

Giới hạn HTTP không tự giới hạn JMX. Cấu hình production ở phần 3 loại các endpoint Actuator khỏi công bố JMX và tắt tính năng JMX do Spring quản lý trong phương án này.

Những thiết lập đó không phải công tắc tắt mọi MBean của JVM, thư viện khác hoặc mọi cấu hình JMX remote do tiến trình khởi động. Khi nền tảng có bật JMX remote, cần xét riêng quyền kết nối và xác thực của kênh đó.

Đặc biệt, không chuyển nguyên suy luận về vai trò xem giá trị HTTP sang JMX: với chính sách `when-authorized` của các endpoint được hỗ trợ, JMX coi người truy cập là được phép xem. Do đó, bảo vệ kênh JMX và lựa chọn endpoint công bố trên kênh ấy vẫn là việc bắt buộc của thiết kế.

Tham chiếu: [Monitoring and Management over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

## 8. Kiểm chứng trên tiến trình thực tế

### 8.1. Xác định đúng cấu hình đang được áp dụng

Trước khi kiểm tra HTTP, xác nhận đúng bản dựng, profile, nguồn ghi đè và địa chỉ đang gọi. Đối số dòng lệnh, biến môi trường hoặc cấu hình ngoài có thể làm giá trị thực tế khác tệp production trong JAR.

Không mở `env` công khai chỉ để chứng minh `env` đã đóng. Có thể dùng manifest triển khai, cấu hình tiến trình, kiểm thử tích hợp và quan sát phản hồi qua kênh quản trị đã được cho phép.

Khi có nhiều bản sao ứng dụng, kiểm tra đủ các bản sao hoặc bảo đảm tuyến kiểm tra đến đúng bản sao. Một bản sao chưa được cập nhật có thể tiếp tục công bố dữ liệu dù bản sao đang quan sát đã đóng.

### 8.2. Kiểm tra phản hồi health

Giả sử ví dụ chạy trên máy kiểm chứng tại `127.0.0.1:8080`, cùng cổng cho HTTP nghiệp vụ và quản trị:

```shell
curl -i "http://127.0.0.1:8080/actuator/health"
```

Trên Windows PowerShell, dùng `curl.exe` nếu `curl` đang là bí danh của PowerShell.

Với ứng dụng kiểm chứng khỏe mạnh, body mong đợi là:

```json
{"status":"UP"}
```

Không có `components`, `details`, tên cơ sở dữ liệu, đường dẫn ổ đĩa hay thông tin kết nối trong phản hồi này. Nếu có health group tùy chỉnh, kiểm tra từng group: một cấu hình group riêng có thể làm mức hiển thị khác thiết lập chung.

Thực hiện thêm:

```shell
curl -i "http://127.0.0.1:8080/actuator/health?show-details=always"
```

Tham số tùy ý trên URL không thay thế thuộc tính cấu hình phía máy chủ. Với ví dụ, phản hồi vẫn không có cây thành phần hoặc chi tiết.

### 8.3. Kiểm tra các endpoint không được công bố

Trong chế độ chỉ `prod`, thực hiện các yêu cầu:

```shell
curl -i "http://127.0.0.1:8080/actuator/env"
curl -i "http://127.0.0.1:8080/actuator/configprops"
curl -i "http://127.0.0.1:8080/actuator/beans"
curl -i "http://127.0.0.1:8080/actuator/mappings"
curl -i "http://127.0.0.1:8080/actuator/conditions"
curl -i "http://127.0.0.1:8080/actuator/info"
curl -i "http://127.0.0.1:8080/actuator"
```

Không yêu cầu mọi URL đều trả cùng một mã:

| Mã phản hồi | Ý nghĩa cần kiểm tra |
| --- | --- |
| `401` | Yêu cầu bị chặn vì chưa có thông tin xác thực được chấp nhận |
| `403` | Chính sách từ chối quyền truy cập |
| `404` | Không có tài nguyên phù hợp tại đường dẫn đang xét |
| `200` | Cần đọc body để xác định dữ liệu nào thực sự được trả |

Một `401` cho người gọi ẩn danh chỉ chứng minh lần gọi ấy bị chặn. Nó chưa chứng minh endpoint đã bị tắt hoặc người có quyền cao hơn cũng không đọc được.

Lặp lại bằng tài khoản vận hành đã được cấp trong môi trường kiểm chứng. Với chính sách production chỉ health, ngay cả người có vai trò `OPS` cũng không nhận dữ liệu cấu hình hoặc cấu trúc từ các endpoint đã tắt.

Với HTTP Basic trên máy kiểm chứng, có thể dùng:

```shell
curl -i --user ops "http://127.0.0.1:8080/actuator/env"
```

Lệnh để `curl` hỏi mật khẩu thay vì đặt mật khẩu trực tiếp trong dòng lệnh. Tài khoản `ops` cần được cung cấp bởi cơ chế danh tính của ứng dụng; tên tài khoản tự nó không tạo ra vai trò `OPS`.

Nếu hệ thống dùng cổng quản trị riêng, base path khác hoặc HTTPS, dùng đúng địa chỉ triển khai thực tế thay cho địa chỉ của ví dụ.

### 8.4. Kiểm tra chế độ chẩn đoán và đường bên ngoài

Trong chế độ `prod,ops`:

1. Người chưa xác thực và người sai vai trò không đọc được `env`, `configprops`.
2. Người có vai trò `OPS` đọc được phản hồi nhưng giá trị vẫn bị che với chính sách `never`.
3. Khi đổi có chủ đích sang `when-authorized`, dùng một giá trị mẫu không nhạy cảm để xác minh người đủ quyền nhìn thấy nó.
4. Những endpoint không có trong danh sách chẩn đoán vẫn không công bố dữ liệu.
5. Sau khi đóng chế độ chẩn đoán, lặp lại phép thử bằng tài khoản vận hành.

Kiểm tra cả qua đường công khai và đường nội bộ. Một proxy chặn `/actuator` có thể đang bảo vệ đường công khai, trong khi cổng dịch vụ trực tiếp vẫn công bố dữ liệu cho phạm vi mạng rộng hơn dự kiến.

Bằng chứng kiểm chứng nên ghi địa chỉ hoặc loại tuyến, thời điểm, bản dựng, loại người gọi, mã phản hồi và những trường được phép xuất hiện. Tránh lưu toàn bộ cấu hình thực vào ảnh chụp hoặc log kiểm thử khi chỉ cần chứng minh một thuộc tính.

## 9. Giữ được khả năng giám sát mà không công bố quá mức

Danh sách health duy nhất là phương án khởi đầu của ví dụ. Nếu production cần Prometheus, phải bổ sung endpoint tương ứng có chủ đích: phụ thuộc cần thiết, kích hoạt, exposure, quyền dành cho hệ thống thu thập và đường mạng phù hợp.

Không cần cấp cho tài khoản chỉ thu thập chỉ số cùng quyền xem cấu hình rõ của người điều tra sự cố. Trong ứng dụng thật, có thể phân quyền theo từng endpoint và nhiệm vụ.

Các nhãn của chỉ số cũng cần được xét duyệt. Nhãn chứa địa chỉ nội bộ, thông tin khách hàng hoặc giá trị do người dùng nhập có thể công bố dữ liệu không cần thiết và làm tăng số chuỗi thời gian.

Việc tắt một endpoint quan sát không đồng nghĩa đã dừng toàn bộ quá trình thu thập dữ liệu hoặc exporter khác của ứng dụng. Cần xác định rõ đang giảm kênh đọc nào và hệ thống giám sát nào vẫn hoạt động.

Tương tự, hạn chế Actuator cần đi cùng việc rà soát các đường công bố ngoài Actuator:

- Phản hồi lỗi và trang lỗi tùy chỉnh có đưa stack trace hoặc cấu hình vào body không?
- Endpoint nghiệp vụ hoặc endpoint tùy chỉnh có trả đối tượng cấu hình trực tiếp không?
- Log có in toàn bộ `Environment`, header xác thực hay đối tượng chứa bí mật không?
- Contributor tùy chỉnh của `info` và phần mở rộng health có đưa thêm dữ liệu ngoài dự kiến không?

Những đường này có chủ sở hữu và cơ chế kiểm soát riêng; chính sách che của `env` không tự xử lý chúng.

## 10. Những lỗi triển khai thường gặp

| Cách làm | Vì sao chưa đạt yêu cầu | Cách sửa đúng trọng tâm |
| --- | --- | --- |
| Công bố `"*"`, rồi loại vài endpoint đã biết | Có thể mở thêm endpoint khi bổ sung phụ thuộc hoặc tính năng | Dùng danh sách endpoint cần công bố |
| Chỉ che mật khẩu, vẫn mở toàn bộ `env` | Tên khóa và nguồn cấu hình vẫn có thể được đọc | Giảm endpoint, giới hạn người đọc và payload |
| Dùng `when-authorized` mà không chỉ định vai trò | Mọi người đã xác thực có thể được coi đủ quyền xem giá trị | Chỉ định vai trò theo nhiệm vụ và kiểm thử |
| Dựa vào tên base path khó đoán | Người biết URL vẫn có thể gọi trực tiếp | Áp dụng kiểm soát mạng và quyền truy cập |
| Thêm chuỗi bảo mật riêng cho Actuator, bỏ sót phần còn lại | Yêu cầu ngoài matcher có thể không được bảo vệ như dự kiến | Thiết kế các chuỗi bao phủ toàn bộ ứng dụng |
| Chỉ thử bằng người chưa đăng nhập | Chưa biết người dùng thông thường hoặc tài khoản vận hành đọc được gì | Kiểm tra từng nhóm quyền |
| Bật health details chung rồi chỉ kiểm tra đường health gốc | Group, đường bổ sung hoặc đường thành phần có thể khác | Rà soát tất cả đường health đã cho phép |
| Đóng HTTP nhưng giữ JMX hoặc đường quản trị trực tiếp quá rộng | Dữ liệu còn được tiếp cận qua kênh khác | Kiểm kê và kiểm chứng từng kênh |
| Bật chế độ chẩn đoán rồi không đóng lại | Phạm vi công bố tạm thời trở thành thường trực | Gắn thời hạn vận hành và xác minh sau khi thu hồi |

## 11. Bài tập áp dụng

Một dịch vụ có ba nhu cầu:

1. Bộ cân bằng tải cần biết ứng dụng có thể phục vụ.
2. Hệ thống thu thập chỉ số cần đọc dữ liệu giám sát.
3. Nhóm vận hành thỉnh thoảng cần điều tra vì sao một cấu hình được ghi đè.

Hãy lập bảng gồm: đối tượng gọi, endpoint cần dùng, kênh mạng, quyền đọc và dữ liệu được phép nhận.

Hướng giải quyết cần thể hiện:

- Probe chỉ nhận trạng thái cần thiết; nếu dùng readiness thì kiểm tra đúng health group và đường đã thiết kế.
- Tài khoản thu thập chỉ số có quyền theo nhiệm vụ, không tự nhận quyền đọc giá trị cấu hình.
- Chẩn đoán `env` hoặc `configprops` chỉ diễn ra qua kênh kiểm soát, với người đủ quyền và kế hoạch đóng lại.
- Các endpoint như `beans`, `mappings`, `conditions` không được mở thêm chỉ vì một nhiệm vụ khác cần cấu hình.
- Có phép thử đối với người ẩn danh, người sai vai trò, người đúng vai trò và cấu hình sau khi thu hồi.

Dùng [danh mục thuộc tính Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html) để đối chiếu tên cấu hình với đúng phiên bản đang triển khai. Kết quả cần chứng minh được cả **những dữ liệu phục vụ vận hành vẫn đọc được** và **những dữ liệu ngoài nhu cầu đã bị giới hạn**.

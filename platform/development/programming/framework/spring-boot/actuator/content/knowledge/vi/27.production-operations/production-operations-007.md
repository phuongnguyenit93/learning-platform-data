# Quản lý dữ liệu cá nhân, thời hạn lưu và quyền đọc log, trace hoặc dump

> Phạm vi: vận hành ứng dụng Spring Boot Actuator 3.3.x. Các đoạn cấu hình là ví dụ kỹ thuật; các thời hạn lưu trong bài thuộc một chính sách giả định, cần được xác định lại theo mục đích sử dụng và yêu cầu áp dụng cho hệ thống thực tế.

## 1. Dữ liệu chẩn đoán cũng cần được quản lý như dữ liệu của hệ thống

Log giúp giải thích sự kiện, trace giúp nối các thao tác qua nhiều dịch vụ, còn dump giúp phân tích trạng thái tiến trình. Chúng được tạo để hỗ trợ vận hành nhưng có thể chứa dữ liệu từ yêu cầu, đối tượng nghiệp vụ, phiên đăng nhập hoặc cấu hình.

Một sự cố điển hình: ứng dụng không lưu email vào bảng log nghiệp vụ, nhưng một exception đưa nguyên đối tượng khách hàng vào thông báo. Log được sao chép sang hệ thống tập trung; người điều tra tải thêm heap dump về máy cá nhân. Chính sách dữ liệu của ứng dụng chính chưa kiểm soát được những bản sao này.

Bài toán gồm ba quyết định liên quan:

| Quyết định | Câu hỏi cần trả lời |
| --- | --- |
| Thu thập và giảm dữ liệu | Thật sự cần giữ trường nào để điều tra? Có thể tránh thu thập phần nhạy cảm không? |
| Thời hạn lưu | Dữ liệu còn cần thiết đến khi nào, bắt đầu tính từ mốc nào và được xóa ở những nơi nào? |
| Quyền đọc | Ai được xem loại dữ liệu nào, trong phạm vi dịch vụ/tenant/sự cố nào và đến khi nào? |

Giới hạn quyền đọc không sửa được việc đã thu thập thừa. Mã hóa không tự làm dữ liệu hết hạn. Che một giá trị ở giao diện cũng không chứng minh bản gốc đã được loại bỏ.

## 2. Phân loại từng loại dữ liệu trước khi cấp quyền

| Loại | Nội dung có thể xuất hiện | Điểm cần kiểm soát |
| --- | --- | --- |
| Log ứng dụng | Thông báo lỗi, thuộc tính nghiệp vụ, thông tin từ request hoặc exception | Nội dung được ghi, quyền truy vấn và tải cả tệp |
| Trace | Thuộc tính span, tên thao tác, URL, mã tương quan và lỗi | Thuộc tính, sự kiện lỗi, nơi xuất dữ liệu và phạm vi liên kết |
| Thread dump | Ngăn xếp, tên lớp/phương thức, tên luồng, thông tin khóa | Tên luồng hoặc chi tiết tùy biến cũng có thể chứa dữ liệu nội bộ |
| Heap dump | Các đối tượng và chuỗi đang có trong bộ nhớ heap | Có thể chứa dữ liệu cá nhân, token hoặc bí mật chưa hề được ghi ra log |

Thread dump không phải bản sao toàn bộ heap; heap dump cũng không chỉ chứa các dòng log. Vì vậy, không áp dụng mặc định cùng một mức quyền và một thời hạn lưu cho mọi loại.

Actuator cung cấp heapdump qua một endpoint riêng. Phía JVM còn có các công cụ chẩn đoán độc lập, như jcmd hoặc JMX; tắt đường HTTP không tự loại bỏ các đường đó. [API HeapDumpWebEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/management/HeapDumpWebEndpoint.html), [Công cụ chẩn đoán JDK 21](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html).

Dữ liệu cá nhân không chỉ là họ tên hay email. Một mã khách hàng, địa chỉ IP, URL chứa định danh hoặc mã tương quan có thể liên kết đến một người khi kết hợp với dữ liệu khác. Thay tên bằng một ID không tự chứng minh dữ liệu đã vô danh.

## 3. Giảm dữ liệu trước khi dữ liệu đi vào kho lưu

### Chọn trường được phép ghi

Ưu tiên một sự kiện có cấu trúc và chỉ đưa vào các trường đã chọn. Ví dụ minh họa bằng dữ liệu tổng hợp:

```json
{
  "event": "order_lookup_failed",
  "service": "orders-api",
  "environment": "production",
  "route": "/api/orders/{id}",
  "outcome": "dependency_timeout",
  "durationMs": 143,
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Route được ghi theo mẫu thay vì chép mã đơn hàng vào đường dẫn. Mã lỗi được phân loại thay vì đưa nguyên phản hồi của hệ thống khác vào thông báo. traceId giúp tra cứu tương quan nhưng vẫn cần được bảo vệ theo khả năng liên kết dữ liệu của hệ thống.

Những nội dung thường cần loại bỏ khỏi log gồm mật khẩu, token truy cập, khóa bí mật, cookie phiên và các dữ liệu cá nhân không phục vụ mục đích ghi nhận. Cũng cần mã hóa đầu ra đúng định dạng và xử lý ký tự điều khiển để dữ liệu đầu vào không tạo dòng log giả. [Hướng dẫn ghi log của OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

### Đừng chỉ tìm vài tên khóa để che

Các đường làm lộ dữ liệu có thể nằm ngoài bộ lọc quen thuộc:

- Exception chứa nguyên request, câu SQL đã gắn giá trị hoặc phản hồi của bên thứ ba.
- Phương thức toString của đối tượng nghiệp vụ chứa thông tin khách hàng.
- Query string, tên span hoặc tên luồng được ghép từ dữ liệu đầu vào.
- Tệp hàng đợi của bộ gửi log đã lưu bản thô trước khi bộ thu xử lý.
- Dữ liệu được đưa vào thuộc tính chung rồi lan sang nhiều sự kiện.

Danh sách trường được phép thường dễ kiểm tra hơn việc mong một biểu thức chính quy tìm được mọi dạng dữ liệu nhạy cảm. Lọc ở ứng dụng trước khi ghi giúp giảm số bản sao thô; bộ thu có thể bổ sung một lớp lọc nữa. Hãy kiểm tra đầu ra thực tế của cả hai lớp. [Xử lý dữ liệu nhạy cảm trong OpenTelemetry](https://opentelemetry.io/docs/security/handling-sensitive-data/).

Nếu dùng băm để liên kết các sự kiện theo người dùng, phải đánh giá khả năng đoán lại và liên kết chéo. Băm một tập dữ liệu dễ đoán không đồng nghĩa với vô danh; chính các giá trị băm vẫn cần chính sách truy cập và lưu trữ phù hợp.

### Trace và baggage

Kiểm tra cả tên span, attributes, events và thông báo exception. Giảm tỷ lệ lấy mẫu trace chỉ giảm lượng dữ liệu; nó không loại bỏ phần nhạy cảm trong những trace vẫn được chọn.

Baggage có thể được truyền qua HTTP tới các dịch vụ khác, kể cả đường gọi đi ra ngoài hệ thống. Không dùng nó làm túi chứa tùy ý email, token hoặc thông tin cá nhân. Baggage cũng không tự có kiểm tra tính toàn vẹn để được tin như một nguồn quyền truy cập. [Lưu ý bảo mật của OpenTelemetry Baggage](https://opentelemetry.io/docs/concepts/signals/baggage/#baggage-security-considerations).

## 4. Hiểu đúng giới hạn bảo vệ của Actuator

Ba lớp cần phân biệt là: endpoint có được bật, có được đưa ra qua HTTP/JMX và người gọi có được phép đọc hay không. Trong Spring Boot 3.3, bật/tắt endpoint dùng thuộc tính enabled; expose một endpoint chưa thay cho kiểm tra quyền. [Cấu hình endpoint của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Một cấu hình tham khảo chỉ bật health và prometheus:

```yaml
management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health,prometheus
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      enabled: true
      show-details: never
    prometheus:
      enabled: true
    env:
      show-values: never
    configprops:
      show-values: never
    quartz:
      show-values: never
```

Đây là đoạn ghép vào ứng dụng đã có các dependency cần thiết, bao gồm registry Prometheus nếu dùng endpoint đó. Các endpoint còn lại không được bật bởi cấu hình mặc định đã chọn. Việc loại khỏi JMX ở đây chỉ áp dụng các endpoint Actuator, không phải toàn bộ mọi MBean tự khai báo.

Trong Spring Boot 3.3, env/configprops/quartz hỗ trợ cơ chế che giá trị qua show-values. Cơ chế này dành cho phản hồi các endpoint đó; nó không quét lại log, span hoặc các đối tượng trong heap.

Đặc biệt, when-authorized phải được xét cùng cấu hình roles và cơ chế xác thực. Không được suy ra rằng mọi người đã đăng nhập đều nên đọc cấu hình gốc chỉ vì họ có thể truy cập ứng dụng.

logfile đọc nội dung tệp log; loggers có thể thay đổi mức ghi log. Đây là hai quyền khác nhau. Cho phép đổi một logger sang DEBUG có thể tăng lượng dữ liệu được thu thập, nên quyền thay đổi cấu hình quan sát cần được quản lý riêng với quyền xem số liệu.

Endpoint không xuất hiện qua HTTP cũng không chứng minh dump sẽ không được tạo: cấu hình JVM tạo dump khi lỗi bộ nhớ, công cụ hệ điều hành hoặc thao tác chẩn đoán vẫn phải được kiểm soát ở lớp nền tảng.

## 5. Cấp quyền đọc theo tài nguyên, phạm vi và thời hạn

Xác thực trả lời người gọi là ai; phân quyền quyết định họ được làm gì với tài nguyên nào. Mặc định từ chối và kiểm tra trên mỗi yêu cầu giúp tránh việc một liên kết hoặc một ID trở thành đường đọc toàn bộ kho. [Hướng dẫn phân quyền của OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

Một ma trận quyền tham khảo:

| Chủ thể | Quyền thường trực có thể cấp | Quyền cần cấp riêng |
| --- | --- | --- |
| Bộ thu metrics | Đọc endpoint metrics đã được chọn của dịch vụ | Không kế thừa quyền đọc log, trace hoặc dump |
| Người phát triển | Truy vấn log đã giảm dữ liệu của dịch vụ/phạm vi được giao | Dữ liệu production chi tiết hoặc xuất dữ liệu số lượng lớn |
| Người trực xử lý sự cố | Đọc log/trace trong phạm vi sự cố và khoảng thời gian cần thiết | Heap dump hoặc bản gốc có độ nhạy cảm cao |
| Người quản trị kho | Quản lý cấu hình và vòng đời theo nhiệm vụ | Không mặc định đồng nghĩa với được đọc mọi nội dung |

Ma trận là ví dụ thiết kế, không phải danh sách vai trò bắt buộc. Cần tách ít nhất các hành động: truy vấn, xem một bản ghi, tải tệp, xuất hàng loạt, tạo dump, đổi mức log và xóa dữ liệu.

Với hệ thống nhiều tenant, kiểm tra tenant ở phía máy chủ trên từng tài nguyên và từng truy vấn. Không tin một bộ lọc tenant do trình duyệt gửi lên như bằng chứng người dùng có quyền. Cũng không dùng quyền đọc một trace để mặc định mở mọi log hoặc dump có cùng mã sự cố.

### Ví dụ bảo vệ đường HTTP của Actuator

Đoạn Java sau dành cho ứng dụng Servlet sử dụng Spring Security và OAuth2 Resource Server JWT. Nó yêu cầu JwtDecoder được cấu hình hợp lệ từ cơ chế xác thực của dự án, chẳng hạn qua issuer-uri đã xác minh.

Trong ví dụ, health chỉ công bố trạng thái; prometheus đòi scope metrics.read. Các endpoint Actuator khác và toàn bộ đường còn lại bị từ chối. Đây là một cấu hình minh họa có chủ đích, không chứa chính sách truy cập API nghiệp vụ của một ứng dụng hoàn chỉnh.

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class OperationalReadSecurity {
    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(EndpointRequest.to("health")).permitAll()
            .requestMatchers(EndpointRequest.to("prometheus"))
                .hasAuthority("SCOPE_metrics.read")
            .anyRequest().denyAll());
        http.oauth2ResourceServer(oauth -> oauth.jwt(withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain remainingRequests(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth.anyRequest().denyAll());
        return http.build();
    }
}
```

EndpointRequest chọn endpoint theo vị trí Actuator thay vì chỉ dựa vào một đường dẫn viết cứng. Khi tự cung cấp SecurityFilterChain, cần bao phủ cả các request ngoài Actuator; vì vậy ví dụ có chuỗi thứ hai. [API EndpointRequest](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html), [Bảo vệ HTTP endpoint trong Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

Với ánh xạ scope JWT mặc định, metrics.read tương ứng authority SCOPE_metrics.read. Đừng giả định scope này có sẵn trong mọi token hoặc mọi bộ chuyển đổi đã tùy biến. [Ánh xạ scope của Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html#oauth2resourceserver-jwt-authorization).

Cấu hình này bảo vệ cửa vào ứng dụng; quyền đọc kho log/trace, tệp trong container, object storage và đường quản trị máy chủ vẫn phải được thực thi tại chính những nơi đó.

## 6. Xây thời hạn lưu theo toàn bộ vòng đời

Thời hạn lưu (retention) cần đi cùng mục đích, mốc bắt đầu tính, nơi áp dụng, cách xóa và người chịu trách nhiệm. Các bản sao trong hàng đợi, bản xuất và bản sao lưu cũng nằm trong vòng đời dữ liệu chẩn đoán. [Quản lý vòng đời log theo NIST SP 800-92](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-92.pdf).

Chính sách giả định để thảo luận:

| Nhóm dữ liệu | Thời hạn minh họa | Nơi thực thi chính |
| --- | --- | --- |
| Log vận hành đã giảm dữ liệu | 7 ngày | Kho log tập trung và mọi bản sao theo chính sách |
| Trace đã lọc thuộc tính | 3 ngày | Kho trace và hàng đợi/bản xuất liên quan |
| Heap dump phục vụ một sự cố | 24 giờ từ lúc tạo | Kho chẩn đoán có quyền đọc riêng |
| Dấu vết kiểm toán truy cập | Một chính sách riêng theo mục đích kiểm toán | Kho kiểm toán tách quyền sửa/xóa |

Các con số trên không phải mặc định của Spring Boot và không xác định một thời hạn chung cho mọi hệ thống.

### Phải định nghĩa mốc bắt đầu

Có thể chọn thời điểm sự kiện hoặc thời điểm hệ thống tiếp nhận, nhưng phải công bố lựa chọn và xử lý dữ liệu đến muộn. Với dump, thời điểm tạo và expiresAt có thể được lưu trong metadata của tài nguyên.

Khi sao chép hoặc xuất lại, giữ được hạn hết hiệu lực ban đầu của dữ liệu; không vô tình bắt đầu thêm một kỳ lưu mới chỉ vì bản sao vừa được nhập vào hệ thống khác. Nếu dùng dấu thời gian từ nguồn chưa tin cậy, phải kiểm tra thay vì để nguồn tự kéo dài hạn lưu.

### Xác minh từng nơi dữ liệu có thể còn tồn tại

1. Tệp đang ghi và tệp đã xoay trên máy/container.
2. Bộ đệm hoặc hàng đợi bền vững của agent/collector.
3. Chỉ mục, kho gốc và vùng lưu trữ lạnh của hệ thống tập trung.
4. Object storage, phiên bản cũ của đối tượng và bản sao dự phòng.
5. Tệp xuất, máy phân tích, công cụ điều tra và tệp tạm.

Mã hóa dữ liệu khi lưu và khi truyền giúp bảo vệ nội dung nhưng không thay TTL, quyền đọc hoặc quy trình xóa. Xóa một chỉ mục tìm kiếm cũng chưa chứng minh bản gốc trong object storage đã biến mất.

Nếu có ngoại lệ cần giữ phục vụ điều tra, phải có phạm vi, căn cứ, người chịu trách nhiệm và thời điểm rà soát riêng; không biến ngoại lệ thành lưu vô hạn. Với kho bất biến hoặc bản sao lưu không xóa chọn lọc được, phải xác định cách kiểm soát truy cập, thời hạn hết hiệu lực và xử lý khi khôi phục dữ liệu.

## 7. Xoay vòng log cục bộ không phải chính sách lưu toàn hệ thống

Ví dụ sau dành cho ứng dụng dùng cấu hình Logback do Spring Boot quản lý, triển khai với đường dẫn tệp kiểu Linux:

```yaml
logging:
  file:
    name: /var/log/orders-api/application.log
  logback:
    rollingpolicy:
      file-name-pattern: /var/log/orders-api/archive/application.%d{yyyy-MM-dd,UTC}.%i.log.gz
      max-file-size: 10MB
      max-history: 7
      total-size-cap: 1GB
      clean-history-on-start: true
```

Spring Boot cung cấp các thuộc tính rollingpolicy để cấu hình lưu trữ tệp log. Nếu dự án có logback-spring.xml riêng, cần kiểm tra appender thực tế có sử dụng các giá trị này hay không. [Cấu hình logging của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html#features.logging.file-rotation).

Với mẫu ngày ở trên, max-history được hiểu theo các kỳ lưu trữ của rolling policy; không phải bảo đảm mọi bản ghi tồn tại chính xác 7 lần 24 giờ. %i cho phép nhiều tệp trong cùng kỳ khi chạm giới hạn kích thước.

Logback thực hiện dọn archive theo cơ chế rolling và xử lý bất đồng bộ; tệp đang hoạt động, thời điểm có sự kiện mới và giới hạn tổng dung lượng đều cần được xét. total-size-cap có thể làm archive cũ bị xóa sớm hơn giới hạn tuổi. [Cơ chế rolling và maxHistory của Logback](https://logback.qos.ch/manual/appenders-rolling.html).

Do đó, cần kiểm tra cả hai phía: không giữ quá lâu so với chính sách, và không mất dữ liệu trước thời gian tối thiểu cần giữ. Dung lượng thiếu không nên được che bằng cách âm thầm thay đổi mục đích lưu.

Những cấu hình này không đặt thời hạn cho trace, heap dump, stdout do nền tảng thu thập, kho log tập trung hoặc các bản sao dự phòng.

## 8. Quản lý dump theo từng vụ việc

Heap dump có thể bao gồm dữ liệu chưa đi qua bất kỳ bộ lọc log nào. Không dựa vào việc log đã che password để kết luận dump không chứa bí mật. Cũng không dùng vài phép thay chuỗi như một bảo đảm làm sạch toàn bộ tệp dump nhị phân.

Một luồng xử lý tham khảo:

1. Xác định câu hỏi điều tra và xem dữ liệu ít nhạy cảm hơn đã đủ chưa.
2. Nếu cần dump, ghi nhận đúng dịch vụ/instance, vụ việc, người chịu trách nhiệm và đánh giá tác động khi tạo.
3. Lưu vào nơi có mã hóa, quyền đọc riêng, metadata phân loại và hạn hết hiệu lực.
4. Cấp quyền có hạn cho đúng người và tài nguyên; phân tích trong môi trường được kiểm soát.
5. Ghi lại việc đọc/tải/xuất và kiểm tra xóa các bản sao khi hết mục đích hoặc hết thời hạn.

Quyền tạo dump khác với quyền đọc một dump đã có. Quyền đọc metadata cũng không nhất thiết bao gồm quyền tải toàn bộ nội dung.

Không chuyển dump production sang một hệ thống phân tích khác chỉ vì công cụ đó có thể mở tệp. Trước tiên phải xác minh nơi xử lý đó được phép tiếp nhận loại dữ liệu này và giữ được các ràng buộc truy cập, lưu trữ, sao chép.

## 9. Minh họa Java: hạn đọc và hạn lưu là hai điều kiện độc lập

Chương trình sau dùng metadata giả định. Artifact là tài nguyên chẩn đoán; ReadGrant mô tả quyền đọc có phạm vi. Khoảng hợp lệ gồm thời điểm bắt đầu và không gồm thời điểm kết thúc.

Metadata tài nguyên phải được lấy từ kho tin cậy; grant phải gắn với người đã xác thực và được dịch vụ phân quyền cấp. Người gọi không được tự gửi một ReadGrant để tự tạo quyền. Ví dụ chỉ kiểm chứng logic điều kiện, không thay một hệ thống xác thực, kiểm toán hoặc xóa tệp.

Tệp DiagnosticAccessDemo.java:

```java
import java.time.Instant;
import java.util.Set;

public class DiagnosticAccessDemo {
    record Artifact(String id, String tenant, Instant createdAt,
                    Instant expiresAt) {
        Artifact {
            if (!createdAt.isBefore(expiresAt)) {
                throw new IllegalArgumentException("Invalid retention window");
            }
        }
    }

    record ReadGrant(String tenant, Set<String> readableIds,
                     Instant validFrom, Instant validUntil) {
        ReadGrant {
            readableIds = Set.copyOf(readableIds);
            if (!validFrom.isBefore(validUntil)) {
                throw new IllegalArgumentException("Invalid grant window");
            }
        }
    }

    static boolean mayRead(Artifact artifact, ReadGrant grant, Instant now) {
        return artifact.tenant().equals(grant.tenant())
            && grant.readableIds().contains(artifact.id())
            && !now.isBefore(artifact.createdAt())
            && now.isBefore(artifact.expiresAt())
            && !now.isBefore(grant.validFrom())
            && now.isBefore(grant.validUntil());
    }

    public static void main(String[] args) {
        Instant created = Instant.parse("2026-11-06T09:00:00Z");
        Instant expires = Instant.parse("2026-11-07T09:00:00Z");
        Artifact dump = new Artifact("dump-42", "tenant-a", created, expires);
        Artifact otherId = new Artifact("dump-43", "tenant-a", created, expires);
        Artifact otherTenant = new Artifact(
            "dump-42", "tenant-b", created, expires
        );

        ReadGrant shortGrant = new ReadGrant(
            "tenant-a", Set.of("dump-42"),
            Instant.parse("2026-11-06T09:30:00Z"),
            Instant.parse("2026-11-06T11:00:00Z")
        );
        Instant now = Instant.parse("2026-11-06T10:00:00Z");

        System.out.println("authorizedNow=" + mayRead(dump, shortGrant, now));
        System.out.println("otherArtifact=" + mayRead(otherId, shortGrant, now));
        System.out.println("otherTenant=" + mayRead(otherTenant, shortGrant, now));
        System.out.println("atGrantDeadline="
            + mayRead(dump, shortGrant, shortGrant.validUntil()));

        ReadGrant laterGrant = new ReadGrant(
            "tenant-a", Set.of("dump-42"),
            Instant.parse("2026-11-07T08:00:00Z"),
            Instant.parse("2026-11-07T10:00:00Z")
        );
        System.out.println("atRetentionDeadline="
            + mayRead(dump, laterGrant, dump.expiresAt()));
    }
}
```

Biên dịch và chạy với JDK 21 trở lên:

```powershell
javac --release 21 -encoding UTF-8 DiagnosticAccessDemo.java
java DiagnosticAccessDemo
```

Stdout:

```text
authorizedNow=true
otherArtifact=false
otherTenant=false
atGrantDeadline=false
atRetentionDeadline=false
```

Ví dụ chứng minh:

- Quyền hợp lệ hiện tại chỉ mở tài nguyên đã cấp trong đúng tenant.
- Đúng thời điểm validUntil, quyền tạm thời không còn cho phép đọc.
- Một quyền được cấp vào ngày sau không tự kéo dài expiresAt của dữ liệu.

Hàm trả false tại expiresAt là chặn đọc theo chính sách của ví dụ. Nó không chứng minh dữ liệu vật lý đã bị xóa. Công việc dọn dữ liệu phải được thực thi và kiểm chứng riêng. Đồng hồ đánh giá và metadata thời gian cũng cần nhất quán.

## 10. Kiểm toán và đường xuất dữ liệu

Một lần đọc nên để lại dấu vết đủ để biết ai, hành động gì, với dịch vụ/tenant/tài nguyên nào, lúc nào, theo quyền hoặc vụ việc nào và kết quả ra sao. Hạn chế chép nội dung nhạy cảm vào chính bản ghi kiểm toán.

Quản lý cả quyền xuất hàng loạt và chia sẻ đường tải. Với đường dẫn ký sẵn, thời gian dùng đường dẫn không nên vượt hạn quyền hoặc hạn tài nguyên; không giả định việc đóng giao diện đã thu hồi đường dẫn được cấp.

Cần kiểm tra khả năng thu hồi tại kho/gateway thực tế, chính sách cache và thời gian cấp đường dẫn. Một bản đã được tải xuống không tự biến mất khi quyền trên máy chủ hết hạn; bản sao đó vẫn cần được quản lý trong vòng đời dữ liệu.

Tách quyền ghi dữ liệu, đọc dữ liệu và xóa dấu vết kiểm toán khi có thể. Rà soát quyền thường trực và quyền tạm thời sau sự cố, thay vì chỉ kiểm tra lúc người dùng lần đầu tham gia hệ thống.

Nếu phát hiện token hoặc dữ liệu không nên được ghi, xử lý tại nguồn phát, xác định nơi đã sao chép và hạn chế phạm vi truy cập. Nếu là bí mật xác thực bị lộ, cần xử lý vòng đời của bí mật đó; xóa một dòng log không tự làm token mất hiệu lực.

## 11. Kiểm tra bằng dữ liệu tổng hợp trước khi đưa vào vận hành

| Trường hợp kiểm tra | Kết quả cần chứng minh |
| --- | --- |
| Request có trường bí mật giả và exception chứa đối tượng nghiệp vụ | Nội dung đó không xuất hiện trong log, span và đầu ra collector ngoài chính sách |
| Người chỉ có quyền metrics | Không đọc được log, trace hoặc dump qua các đường khác |
| Người đúng vai trò nhưng sai tenant hoặc sai ID | Bị từ chối tại máy chủ |
| Hết quyền tạm thời | Yêu cầu đọc mới không được chấp nhận; đánh giá cả đường tải đã cấp |
| Hết hạn dữ liệu | Không đọc được qua chỉ mục, kho gốc hoặc bản xuất ngoài chính sách; có bằng chứng dọn dữ liệu |
| Giới hạn dung lượng log bị chạm | Có đánh giá việc xóa sớm, không nhầm với bảo đảm giữ đủ kỳ |
| Khôi phục bản sao dự phòng | Dữ liệu đã hết hạn không vô tình được mở lại như dữ liệu mới |
| Thay đổi mức log sang DEBUG | Có kiểm soát quyền và kiểm tra phần dữ liệu tăng thêm |

Đối với Actuator, cần kiểm tra theo cấu hình bật/expose và bộ lọc bảo mật thực tế. Một mã phản hồi 401, 403 hoặc 404 riêng lẻ không đủ chứng minh mọi đường đọc khác đã bị khóa. Đối với retention, chỉ thấy tệp biến mất khỏi một giao diện cũng chưa đủ.

## 12. Tự thực hành

1. Vẽ đường đi của một log từ ứng dụng đến nơi người điều tra tải bản xuất. Ghi người chịu trách nhiệm về quyền đọc và hết hạn tại từng điểm.
2. Nếu env.show-values=never nhưng logfile vẫn trả một token đã bị ghi vào log, giải thích vì sao hai hành vi không mâu thuẫn.
3. Thêm một kiểm tra vào chương trình Java cho thời điểm trước validFrom. Giải thích vì sao kiểm tra đó khác với hết hạn lưu.
4. Một dump hết hạn sau 24 giờ nhưng URL tải được cấp 48 giờ. Xác định những lớp phải kiểm tra và vì sao chỉ thay TTL hiển thị trên giao diện chưa đủ.
5. Với max-history=7 và total-size-cap=1GB, giải thích vì sao chưa thể cam kết mọi log luôn được giữ đúng 7 ngày.

Một thiết kế hoàn chỉnh phải cho biết dữ liệu nào được tạo, nó có thể đi tới đâu, ai được đọc và cách chứng minh mọi bản sao được xử lý đúng khi quyền hoặc thời hạn lưu kết thúc.

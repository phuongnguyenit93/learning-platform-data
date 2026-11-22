# Tìm nguyên nhân endpoint không xuất hiện dù đã cấu hình include

## 1. Hiểu đúng việc “đưa endpoint vào include”

Giả sử bạn đã cấu hình:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
```

Nhưng `GET /actuator/prometheus` vẫn trả 404. Điều này không nhất thiết có nghĩa Spring Boot bỏ qua YAML. **Danh sách include chọn các endpoint được công bố qua một kênh; nó không tự tạo endpoint, thêm thư viện, bật lại mọi tính năng hoặc cấp quyền truy cập.**

Để một yêu cầu HTTP đến đúng operation của Actuator, nhiều điều kiện phải cùng đúng:

```text
Có mã và dependency cần thiết
        ↓
Các điều kiện tạo endpoint được thỏa mãn
        ↓
Endpoint được bật theo cấu hình tương ứng
        ↓
Endpoint được chọn cho HTTP và không bị loại trừ
        ↓
Có hạ tầng web cùng ánh xạ operation phù hợp
        ↓
Yêu cầu đi đúng giao thức, địa chỉ, cổng, đường dẫn và phương thức
        ↓
Lớp bảo mật/proxy cho phép yêu cầu tới operation
```

Đây là mô hình chẩn đoán, không phải khẳng định mọi endpoint được tạo theo đúng một trình tự nội bộ. Các điều kiện tự cấu hình có thể kiểm tra nhiều yếu tố cùng lúc.

Trong Spring Boot 3.3, cần phân biệt **bật endpoint** (enablement) với **công bố endpoint** (exposure). `exclude` được ưu tiên hơn `include` trong cùng kênh công bố. Xem [Actuator Endpoints của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Bài học dùng cơ chế cấu hình của Spring Boot 3.3.x. Khi tra cứu, chọn đúng phiên bản tài liệu; không ghép property từ phiên bản mới hơn vào ứng dụng 3.3 rồi mặc định chúng có cùng tác dụng.

## 2. Xác định chính xác “không xuất hiện” nghĩa là gì

Những hiện tượng sau cần các hướng kiểm tra khác nhau:

| Hiện tượng | Điều cần kiểm tra đầu tiên |
| --- | --- |
| Không kết nối được, connection refused hoặc timeout | Tiến trình, listener, cổng, địa chỉ bind, mạng và proxy |
| Trả 404 | URL thực tế, nguồn trả lỗi, mapping, exposure và điều kiện tạo endpoint |
| Trả 401 | Cơ chế xác thực và thông tin đăng nhập |
| Trả 403 | Quyền truy cập, chính sách bảo mật, CSRF nếu là thao tác thay đổi |
| Trả 405 | Phương thức HTTP có khớp operation hay không |
| Trả 200 với `{}` | Endpoint có thể đã tồn tại nhưng chưa có dữ liệu để trình bày |
| Không có liên kết trong `/actuator` | Cấu hình discovery và các endpoint được công bố tại địa chỉ đó |
| Gọi bằng curl được nhưng giao diện web báo lỗi | CORS, mixed content, thông tin xác thực và chính yêu cầu trình duyệt gửi |
| Không thấy trong Swagger/OpenAPI | Cách công cụ tạo tài liệu phát hiện mapping, không chỉ cấu hình Actuator |

Mã trạng thái là manh mối, không phải bằng chứng độc lập về nguyên nhân. Proxy hoặc bộ lọc bảo mật tùy chỉnh có thể trả 404 trước khi yêu cầu tới mapping của Actuator. Ngược lại, một URL không có mapping vẫn có thể bị lớp bảo mật chặn trước bằng 401.

Một phản hồi `200 {}` từ `/actuator/info` không đồng nghĩa endpoint bị thiếu. Nó khác hẳn 404: operation đã được gọi và trả về đối tượng rỗng. Muốn có thông tin build, Git hoặc nguồn dữ liệu khác, cần cấu hình thành phần cung cấp dữ liệu tương ứng.

Trước khi sửa cấu hình, ghi lại bốn thông tin: URL đầy đủ, phương thức, mã trạng thái và nơi thực sự trả phản hồi. Nếu gọi qua gateway, đối chiếu với lần gọi trực tiếp tới instance bằng tuyến truy cập quản trị được cho phép.

## 3. Bắt đầu bằng một quy trình kiểm tra ngắn

Không đổi đồng thời dependency, security và mọi property. Đi theo các câu hỏi có thể xác minh:

1. **Có đang chạy đúng ứng dụng, phiên bản và instance không?** Kiểm tra tiến trình hoặc thông tin triển khai; tránh sửa file của bản mới nhưng gọi bản cũ.
2. **HTTP quản trị đang ở đâu?** Xác định giao thức, cổng, context path, base path và path mapping.
3. **Phản hồi đang là gì?** Tách lỗi kết nối, 404, 401/403, 405 và 200 rỗng.
4. **Cấu hình hiệu lực có đúng không?** Kiểm tra profile, nguồn ghi đè, include, exclude và enablement.
5. **Endpoint có đủ điều kiện được tạo không?** Kiểm tra dependency, bean bắt buộc và báo cáo điều kiện tự cấu hình.
6. **Mapping có tồn tại trong đúng kênh không?** Phân biệt HTTP với JMX, danh sách discovery với endpoint thực tế.
7. **Có lớp trung gian chặn hoặc đổi đường dẫn không?** Đối chiếu security, proxy, ingress và phiên bản từng instance.
8. **Sau thay đổi đã khởi động lại và kiểm tra đúng bản chưa?** Không suy ra trạng thái ứng dụng từ nội dung file trên đĩa.

Mỗi bước nên tạo ra một quan sát cụ thể, chẳng hạn “info bị loại bởi exclude trong profile production”, thay vì “có vẻ Actuator lỗi”.

## 4. Kiểm tra cấu hình hiệu lực, không chỉ file vừa sửa

### 4.1. Đúng tên property và cấu trúc YAML

Ba nhóm property sau không thay thế cho nhau:

```properties
management.endpoints.web.exposure.include=health,info
management.endpoints.web.exposure.exclude=info
management.endpoint.info.enabled=true
```

- `endpoints.web.exposure` dùng số nhiều vì cấu hình tập endpoint công bố qua web.
- `endpoint.info.enabled` dùng số ít vì cấu hình riêng endpoint `info`.
- `include` nhận ID như `info`, không phải URL `/actuator/info`.

Với ví dụ trên, `info` vẫn bị loại khỏi HTTP vì có trong `exclude`. Bật `enabled=true` không vô hiệu hóa danh sách loại trừ.

Dạng YAML tương ứng:

```yaml
management:
  endpoint:
    info:
      enabled: true
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
        exclude:
          - info
```

Đừng sửa lỗi thụt lề bằng cách tạo nhiều khóa `management:` trùng nhau trong cùng một tài liệu YAML. Hãy gom chúng vào một cây hợp lệ. Nếu dùng ký tự đại diện trong YAML, phải viết `"*"`; tuy nhiên công bố tất cả endpoint không phải cách chẩn đoán mặc định.

### 4.2. Profile, biến môi trường và tham số chạy có thể ghi đè

Một file chứa `include: health,info` không chứng minh tiến trình đang dùng danh sách đó. Kiểm tra các khả năng:

- File profile bạn sửa không thuộc profile đang hoạt động.
- File cấu hình ngoài JAR ghi đè file đóng gói trong JAR.
- Biến môi trường hoặc tham số dòng lệnh đặt lại danh sách.
- `spring.config.name` hoặc `spring.config.location` khiến ứng dụng đọc nguồn khác.
- Container đang dùng cấu hình hoặc image cũ.
- Bạn đã sửa cấu hình nhưng tiến trình chưa được khởi động lại.

Ví dụ tham số:

```bash
java -jar endpoint-lab-1.0.0.jar --management.endpoints.web.exposure.include=health
```

Trong cách chạy thông thường của Spring Boot, tham số này có độ ưu tiên cao hơn giá trị trong file. Không mặc định `info` vẫn được cộng thêm từ danh sách ở nguồn có ưu tiên thấp hơn. Xem [Externalized Configuration của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Chỉ thu thập những khóa cần chẩn đoán. Việc in toàn bộ biến môi trường hoặc cấu hình có thể đưa thông tin đăng nhập vào log/hồ sơ sự cố. Nếu dùng `env` hoặc `configprops`, cần đường truy cập đã được bảo vệ; không mở công khai các endpoint đó chỉ để kiểm tra một giá trị.

### 4.3. Bật riêng và bật mặc định là hai lớp khác nhau

Ví dụ chọn cách bật có chủ đích:

```yaml
management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      enabled: true
```

Ở đây, `health` được bật riêng; `info` chưa được bật. Chỉ đưa `info` vào include chưa đủ. Nếu thực sự cần công bố nó, bổ sung:

```yaml
management:
  endpoint:
    info:
      enabled: true
```

Đây là phần cấu hình bổ sung vào cây đang có, không phải hướng dẫn tạo khóa `management` thứ hai trong cùng tài liệu.

Với endpoint được cung cấp bằng tự cấu hình, điều kiện khả dụng có thể xét cả enablement và exposure. API [ConditionalOnAvailableEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/ConditionalOnAvailableEndpoint.html) mô tả cách kiểm tra này. Vì vậy, khi bean không được tạo, cần đọc lý do điều kiện không thỏa thay vì chỉ tìm một lớp Java trong classpath.

## 5. Endpoint có đủ dependency và bean hỗ trợ chưa?

`include` là cấu hình, không phải trình cài thư viện. Một ID nằm trong danh sách không bảo đảm có endpoint tương ứng.

| Endpoint/tình huống | Điều kiện đáng kiểm tra |
| --- | --- |
| Không có endpoint Actuator nào | Có `spring-boot-starter-actuator` trên runtime classpath của chính ứng dụng đang chạy không? |
| `prometheus` không xuất hiện | Có registry Prometheus phù hợp và tự cấu hình xuất metrics có được kích hoạt không? |
| `httpexchanges` không xuất hiện | Có bean `HttpExchangeRepository` không? |
| `logfile` không xuất hiện | Ứng dụng có cấu hình đầu ra log ra file phù hợp không? Chỉ log ra console chưa đủ |
| `startup` không xuất hiện | Có sử dụng `BufferingApplicationStartup` để cung cấp dữ liệu startup không? |
| Endpoint tự viết không xuất hiện | Lớp endpoint có thực sự trở thành Spring bean trong context được phát hiện không? |

### Ví dụ với Prometheus

Nếu ứng dụng chỉ có starter Actuator, cấu hình:

```properties
management.endpoints.web.exposure.include=health,prometheus
```

không tự thêm `io.micrometer:micrometer-registry-prometheus`. Khi cần xuất Prometheus, kiểm tra dependency đó trong đồ thị runtime, phiên bản được quản lý bởi Spring Boot và các property điều khiển bộ xuất. Không chỉ kiểm tra mục dependency trong một module khác hoặc trong phạm vi test.

Tự cấu hình Prometheus của Spring Boot 3.3 có các điều kiện về lớp registry, bean và trạng thái bộ xuất; xem [PrometheusMetricsExportAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/metrics/export/prometheus/PrometheusMetricsExportAutoConfiguration.html).

Sự có mặt của `/actuator/metrics` không chứng minh `/actuator/prometheus` phải có mặt. Hai endpoint phục vụ mục đích khác nhau và có điều kiện hỗ trợ khác nhau.

Với `httpexchanges`, việc thiếu repository khác với “repository tồn tại nhưng chưa ghi nhận exchange nào”. Trường hợp thứ nhất liên quan điều kiện tạo endpoint; trường hợp thứ hai liên quan dữ liệu.

Không thêm thư viện hoặc bean một cách máy móc nếu ứng dụng không cần khả năng đó. Kết quả chẩn đoán hợp lệ có thể là “ID này đang được include dù ứng dụng không cung cấp endpoint tương ứng”; khi ấy cần sửa kỳ vọng hoặc cấu hình thừa.

## 6. HTTP và JMX là hai kênh công bố riêng

Cấu hình sau chỉ chọn endpoint cho JMX:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: health,info
```

Nó không tương đương:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Ngay cả khi JMX đã được bật và endpoint truy cập được qua JMX, chưa thể suy ra `GET /actuator/info` có mapping HTTP. Ngược lại, HTTP hoạt động không chứng minh MBean tương ứng được công bố.

Nếu ứng dụng chạy với `WebApplicationType.NONE` hoặc không có hạ tầng web phù hợp, thêm `web.exposure.include` không tự biến nó thành web server. Trước tiên xác định ứng dụng có được thiết kế để phục vụ HTTP hay không. Không đổi kiểu ứng dụng chỉ để làm xuất hiện một URL quản trị vốn không thuộc nhu cầu của nó.

Với endpoint tự viết, `@JmxEndpoint` chỉ dành cho JMX; `@WebEndpoint` dành cho web. Đừng dùng danh sách include của kênh này để giải thích sự vắng mặt ở kênh khác.

## 7. Tính lại URL thực tế

### 7.1. Khi dùng chung cổng với ứng dụng Servlet

Giả sử cấu hình:

```yaml
server:
  port: 18080
  servlet:
    context-path: /shop

management:
  endpoints:
    web:
      base-path: /manage
      path-mapping:
        info: about
      exposure:
        include: health,info
```

Các URL tương ứng là:

```text
Health: http://localhost:18080/shop/manage/health
Info:   http://localhost:18080/shop/manage/about
```

Gọi `http://localhost:18080/actuator/info` là kiểm tra một đường dẫn khác. Endpoint vẫn có thể hoạt động đúng ở URL mới.

### 7.2. Khi dùng cổng quản trị riêng

Ví dụ Servlet:

```yaml
server:
  port: 18080
  servlet:
    context-path: /shop

management:
  server:
    port: 19090
    address: 127.0.0.1
    base-path: /ops
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info
```

Endpoint info nằm ở:

```text
http://127.0.0.1:19090/ops/manage/info
```

Không tự thêm `/shop` của cổng nghiệp vụ vào URL quản trị riêng. Khi dùng chung cổng, web base path tương đối với Servlet context path hoặc WebFlux base path; khi dùng cổng quản trị riêng, nó tương đối với `management.server.base-path`. Xem [Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

Cũng phải kiểm tra HTTP hay HTTPS, địa chỉ bind và việc cổng đó có được container/proxy chuyển tiếp không. `127.0.0.1` giới hạn truy cập theo không gian mạng của tiến trình; trong container, nó không mặc nhiên là loopback của máy đang chạy curl.

### 7.3. HTTP quản trị có thể bị tắt hoặc dùng cổng ngẫu nhiên

- `management.server.port=-1`: tắt phục vụ endpoint quản trị qua HTTP.
- `management.server.port=0`: chọn cổng ngẫu nhiên theo cơ chế quản trị tương ứng; đọc cổng thực tế từ tiến trình/log thay vì gọi một số cổng cố định.
- Không cấu hình cổng quản trị riêng: thông thường dùng cổng của ứng dụng.

Ý nghĩa của cổng quản trị được mô tả trong [ManagementServerProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/web/server/ManagementServerProperties.html). Dùng cổng riêng cũng có thể tạo context quản trị riêng; xem [ManagementContextAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/web/server/ManagementContextAutoConfiguration.html).

Trong một hệ thống nhiều instance, tránh chỉ đọc log của instance A rồi gọi URL được cân bằng tải tới instance B. Một bản sao chưa cập nhật có thể khiến kết quả lúc 200, lúc 404.

## 8. Phân biệt mapping với quyền truy cập và phương thức HTTP

Một endpoint được công bố không đồng nghĩa mọi người được phép gọi nó. Trong ứng dụng Servlet có Spring Security, quy tắc mặc định và các `SecurityFilterChain` tự viết có thể tạo hành vi khác nhau.

Nếu không tự định nghĩa chuỗi bảo mật, tự cấu hình bảo mật Actuator cho phép truy cập health mà không cần xác thực và bảo vệ các endpoint khác theo điều kiện áp dụng. Khi có chuỗi bảo mật do ứng dụng định nghĩa, cần kiểm tra chính các quy tắc đó; không tiếp tục dựa vào giả định mặc định. Xem [ManagementWebSecurityAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/ManagementWebSecurityAutoConfiguration.html).

Trình tự kiểm tra hợp lý:

1. Ghi nhận 401/403 và các header liên quan, không chỉ đọc body lỗi.
2. Xác định chuỗi bảo mật nào xử lý URL quản trị thực tế.
3. Kiểm tra thông tin xác thực, vai trò/quyền và thứ tự các chuỗi.
4. Nếu URL đã đổi cổng hoặc base path, đối chiếu lại matcher.
5. Nếu qua proxy, kiểm tra proxy có chặn, xác thực riêng hay đổi đường dẫn không.

Không dùng `permitAll` cho toàn bộ Actuator hoặc tắt Spring Security để biến một lỗi truy cập thành “đã sửa endpoint”.

Phương thức cũng phải đúng với operation. Với endpoint dùng các annotation operation thông thường:

| Operation | Phương thức HTTP |
| --- | --- |
| `@ReadOperation` | GET |
| `@WriteOperation` | POST |
| `@DeleteOperation` | DELETE |

Một endpoint chỉ có operation ghi không tự có operation đọc để bạn kiểm tra bằng cách mở URL trên trình duyệt. Nếu đã đi tới đúng mapping nhưng dùng sai phương thức, có thể nhận 405; các lớp lọc phía trước vẫn có thể làm kết quả khác.

Đối với thao tác thay đổi, 403 có thể liên quan CSRF chứ không phải endpoint bị thiếu. Cần xử lý theo mô hình bảo mật của ứng dụng, không tắt CSRF toàn hệ thống chỉ để thử một yêu cầu quản trị. Khi chẩn đoán sự tồn tại, ưu tiên operation đọc và tránh gọi thử thao tác có tác dụng phụ như shutdown.

Nếu curl gọi trực tiếp được nhưng mã JavaScript trên một website khác không đọc được phản hồi, kiểm tra CORS và yêu cầu preflight. Exposure, authorization và CORS là các vấn đề khác nhau; thay đổi include không tự giải quyết cả ba.

## 9. Không dùng discovery hoặc giao diện tài liệu làm bằng chứng duy nhất

`/actuator` thường là trang chứa các liên kết khám phá endpoint HTTP. Tuy nhiên:

```properties
management.endpoints.web.discovery.enabled=false
```

có thể tắt trang khám phá trong khi một URL như `/actuator/info` vẫn hoạt động. Khi đặt web base path là `/`, trang discovery cũng có cơ chế tránh xung đột với mapping ở gốc.

Vì vậy:

- Không mở được `/actuator` chưa đủ để kết luận mọi endpoint đã biến mất.
- Danh sách liên kết của HTTP không phải danh sách mọi khả năng JMX.
- Không thấy endpoint trong Swagger/OpenAPI chưa đủ để kết luận HTTP mapping không tồn tại.
- Dữ liệu của endpoint bị rỗng hoặc chi tiết bị ẩn cũng khác với endpoint không có mapping.

Hãy gọi trực tiếp URL operation đã tính đúng với quyền phù hợp. Dùng discovery và công cụ tài liệu làm chứng cứ hỗ trợ, không thay thế kiểm tra operation thực tế.

## 10. Đọc chứng cứ tự cấu hình và kiểm tra endpoint tự viết

### 10.1. Khi endpoint do Spring Boot cung cấp không được tạo

Trong môi trường được phép chẩn đoán, có thể khởi động với debug để xem báo cáo điều kiện tự cấu hình:

```bash
java -jar endpoint-lab-1.0.0.jar --debug
```

Tìm nhóm cấu hình liên quan endpoint hoặc bộ xuất đang nghi ngờ, rồi đọc lý do điều kiện không thỏa. Ví dụ cần phân biệt thiếu lớp registry với property vô hiệu hóa bộ xuất hoặc endpoint bị tắt.

Không xem tên auto-configuration có trong JAR là bằng chứng bean đã tồn tại. Một lớp tự cấu hình có thể được tìm thấy nhưng không được áp dụng do điều kiện không thỏa. Đồng thời, một dòng báo “exposing N endpoints” chỉ là chỉ báo tổng hợp; nó chưa giải thích endpoint cụ thể nào thiếu hoặc một URL qua proxy đang bị chặn ở đâu.

Nếu `conditions`, `beans`, `mappings` hay công cụ kiểm tra context đã được cung cấp qua đường quản trị bảo vệ, có thể dùng chúng để đối chiếu. Không tạo vòng phụ thuộc “phải mở được conditions endpoint mới chẩn đoán được Actuator”: log khởi động và báo cáo điều kiện cũng có giá trị.

Khi chia sẻ chứng cứ, trích phần liên quan, che dữ liệu nhạy cảm và giữ các thông tin đủ để tái hiện: phiên bản Boot, profile, URL, phương thức, property hiệu lực và điều kiện không thỏa.

### 10.2. Khi endpoint do ứng dụng tự viết không được phát hiện

Kiểm tra từ đăng ký bean đến operation:

1. Lớp endpoint đã được đăng ký bằng component scanning hoặc `@Bean` chưa?
2. Package đó có thuộc phạm vi quét của ứng dụng đang chạy không?
3. Có `@Profile` hoặc điều kiện nào khiến bean không được tạo không?
4. Annotation endpoint và ID có đúng với kênh đang cần sử dụng không?
5. Có operation thích hợp như `@ReadOperation` để tạo yêu cầu GET không?
6. Có `@Selector` làm operation cần thêm đoạn đường dẫn không?
7. Có `EndpointFilter` hoặc phần mở rộng tùy chỉnh tác động đến việc công bố không?

Một lớp được gắn `@Endpoint` nhưng không trở thành bean không được “hồi sinh” chỉ bằng cách thêm ID vào include. Ngược lại, `@RestController` với `@GetMapping` thông thường thuộc cơ chế ánh xạ controller; không mặc định nó là một Actuator endpoint được điều khiển bằng danh sách này.

Với endpoint tự viết, cũng phải đọc cách bean và các điều kiện khả dụng được khai báo. Không áp dụng máy móc mọi giả định về tự cấu hình endpoint có sẵn cho một bean được đăng ký theo cơ chế riêng.

## 11. Phòng thử nghiệm: cùng include nhưng kết quả khác nhau

Phòng thử nghiệm sau là **ứng dụng độc lập**, dùng Java 17 trở lên, Maven và Spring Boot 3.3.0 để cố định ví dụ. Nó chỉ lắng nghe loopback, không thêm Spring Security hoặc registry Prometheus. Chạy trong thư mục mới, không dùng profile hay nguồn cấu hình ngoài làm thay đổi các property đang thử.

### 11.1. Tạo chương trình tối thiểu

Cấu trúc:

```text
endpoint-lab/
├── pom.xml
└── src/main/
    ├── java/lab/EndpointLabApplication.java
    └── resources/application.properties
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>endpoint-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
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

Nội dung `src/main/java/lab/EndpointLabApplication.java`:

```java
package lab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EndpointLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointLabApplication.class, args);
    }
}
```

Nội dung `src/main/resources/application.properties`:

```properties
spring.application.name=endpoint-lab
server.address=127.0.0.1
server.port=18080
management.endpoints.web.exposure.include=health,info
```

Đóng gói và chạy từ thư mục chứa POM:

```bash
mvn -q package
java -jar target/endpoint-lab-1.0.0.jar
```

Maven cần truy cập kho dependency trong lần tải đầu. Nếu cổng 18080 đã được sử dụng, chọn cổng khác và đổi cả URL thử tương ứng. Log khởi động chứa thời gian, PID và thông tin môi trường nên không có stdout khởi động cố định.

Ở terminal thứ hai, dùng Bash và curl:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/actuator/info
```

Khi ứng dụng khởi động thành công với đúng cấu hình trên, stdout kỳ vọng là:

```text
200
```

Đọc body:

```bash
curl -s http://127.0.0.1:18080/actuator/info
```

Body kỳ vọng là `{}` vì ví dụ chưa cung cấp dữ liệu info bổ sung. Lệnh này không bảo đảm tự in ký tự xuống dòng cuối. Trên PowerShell, dùng `curl.exe` để tránh nhầm alias; khi chỉ lấy mã trạng thái, có thể thay `/dev/null` bằng `NUL`.

### 11.2. Tái hiện từng nguyên nhân, mỗi lần một thay đổi

Trước mỗi lần thử, dừng tiến trình trước bằng Ctrl+C, giữ nguyên file cấu hình gốc, rồi chạy đúng lệnh của trường hợp đó. Không cộng dồn các tham số từ những lần thử trước.

**Trường hợp A — endpoint bị tắt dù có trong include:**

```bash
java -jar target/endpoint-lab-1.0.0.jar --management.endpoint.info.enabled=false
```

Lệnh curl lấy mã trạng thái của `/actuator/info` ở trên kỳ vọng in `404`. Nguyên nhân là endpoint info bị tắt, không phải cần viết thêm include lần nữa.

**Trường hợp B — exclude loại endpoint:**

```bash
java -jar target/endpoint-lab-1.0.0.jar --management.endpoints.web.exposure.exclude=info
```

Kỳ vọng `/actuator/info` trả 404. Tham số exclude không bị danh sách include trong file vô hiệu hóa.

**Trường hợp C — khai báo ID nhưng thiếu registry hỗ trợ:**

```bash
java -jar target/endpoint-lab-1.0.0.jar --management.endpoints.web.exposure.include=health,info,prometheus
```

Kiểm tra:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/actuator/info
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/actuator/prometheus
```

Với đúng dependency của phòng thử nghiệm, stdout kỳ vọng theo thứ tự là:

```text
200
404
```

Kết quả này minh họa rằng Actuator đang hoạt động trong cùng tiến trình, nhưng include không tự cung cấp registry Prometheus.

**Trường hợp D — endpoint hoạt động ở URL đã đổi:**

```bash
java -jar target/endpoint-lab-1.0.0.jar --server.servlet.context-path=/shop --management.endpoints.web.base-path=/manage --management.endpoints.web.path-mapping.info=about
```

Kiểm tra đường dẫn cũ rồi đường dẫn mới:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/actuator/info
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/shop/manage/about
```

Stdout kỳ vọng:

```text
404
200
```

Endpoint không biến mất; URL dùng để kiểm tra đã sai.

**Trường hợp E — tắt discovery nhưng giữ operation:**

```bash
java -jar target/endpoint-lab-1.0.0.jar --management.endpoints.web.discovery.enabled=false
```

Kiểm tra:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/actuator
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/actuator/info
```

Stdout kỳ vọng:

```text
404
200
```

Các kết quả này áp dụng cho ứng dụng tối thiểu đã mô tả. Nếu thêm security, proxy, controller trùng đường dẫn hoặc cấu hình ngoài, cần phân tích các lớp mới thay vì dùng bảng kết quả như quy luật cho mọi hệ thống.

## 12. Sửa đúng lớp đã xác định và kiểm tra lại

| Chứng cứ tìm được | Hướng xử lý phù hợp |
| --- | --- |
| Dependency cần thiết không có trong runtime | Bổ sung đúng dependency nếu khả năng đó thuộc yêu cầu ứng dụng; đóng gói lại |
| Endpoint bị tắt riêng hoặc theo mặc định | Điều chỉnh enablement có chủ đích cho endpoint cần dùng |
| Endpoint bị exclude ở HTTP | Điều chỉnh đúng nguồn exclude theo chính sách công bố |
| Chỉ cấu hình JMX include | Cấu hình HTTP exposure nếu ứng dụng thực sự cần phục vụ HTTP |
| Property bị nguồn ưu tiên cao ghi đè | Sửa nguồn có hiệu lực hoặc loại cấu hình ghi đè sai |
| Base path/cổng/path mapping đã đổi | Cập nhật URL của người gọi, công cụ giám sát hoặc tuyến proxy |
| Endpoint trả 401/403 | Sửa thông tin xác thực, quyền hoặc matcher theo yêu cầu bảo mật |
| Chỉ discovery bị tắt | Dùng URL operation trực tiếp; chỉ bật discovery nếu cần |
| Endpoint tự viết không thành bean | Sửa đăng ký bean, phạm vi quét hoặc điều kiện tạo bean |
| Chỉ một số instance có endpoint | Đối chiếu phiên bản và cấu hình từng instance, hoàn tất triển khai đúng |

Sau thay đổi, kiểm tra lại cùng một URL và phương thức, trên đúng instance/phiên bản. Ghi cả kết quả mong đợi và kết quả thực tế. Nếu đã đổi đường dẫn, kiểm tra URL mới và xác nhận các công cụ sử dụng endpoint đã được cập nhật.

Khi cần tái hiện, giữ một thay đổi cho mỗi lần thử. Mở toàn bộ endpoint, tắt security rồi thêm nhiều thư viện cùng lúc có thể làm URL trả 200 nhưng khiến bạn không biết điều kiện nào ban đầu bị thiếu.

## 13. Bài tập chẩn đoán

### Tình huống 1: include có info nhưng production trả 404

Cấu hình dùng chung:

```properties
management.endpoints.web.exposure.include=health,info
```

Cấu hình production có hiệu lực:

```properties
management.endpoints.web.exposure.exclude=info
```

Hãy xác định lớp gây vắng mặt và thay đổi tối thiểu nếu chính sách production cho phép công bố info.

**Đối chiếu:** info bị loại ở HTTP exposure. Thêm lại `info` vào include hoặc đặt `management.endpoint.info.enabled=true` không giải quyết xung đột exclude. Cần điều chỉnh đúng nguồn exclude, giữ nguyên việc bảo vệ endpoint theo chính sách và kiểm tra sau triển khai.

### Tình huống 2: không mở được /actuator nhưng gọi info được

Ứng dụng có:

```properties
management.endpoints.web.exposure.include=health,info
management.endpoints.web.discovery.enabled=false
```

Hãy giải thích vì sao chưa thể nói Actuator không chạy.

**Đối chiếu:** cấu hình tắt trang discovery, không tắt operation info. Việc gọi trực tiếp info thành công chứng minh operation đó đang được phục vụ; không cần bật tất cả endpoint để khôi phục một danh sách liên kết không thuộc nhu cầu.

### Tình huống 3: đúng include, sai cổng

Ứng dụng Servlet có cổng chính 18080, context path `/shop`, cổng quản trị riêng 19090, management server base path `/ops` và web base path `/manage`. Không có path mapping riêng cho info.

**Đối chiếu:** URL quản trị cần kiểm tra là `http://127.0.0.1:19090/ops/manage/info` nếu dùng HTTP và địa chỉ đó truy cập được. Không ghép `/shop` vào URL quản trị riêng. Sau khi xác định đúng URL, vẫn phải kiểm tra enablement, exposure, điều kiện tạo endpoint và quyền truy cập.

Một kết luận chẩn đoán đủ tốt phải chỉ ra **điều kiện cụ thể đang thiếu**, chứng cứ xác nhận và phép kiểm tra lại. Việc “đã có include trong YAML” mới chứng minh bạn đã viết một giá trị cấu hình, chưa chứng minh toàn bộ đường đi tới endpoint hoạt động.

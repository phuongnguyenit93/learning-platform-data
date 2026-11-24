# Include và exclude endpoint trong Spring Boot Actuator

Trong chương **Actuator và management** của module **SPRING_BOOT_OBSERVABILITY**, include và exclude endpoint là hai cơ chế kiểm soát endpoint nào được expose qua management interface. Spring Boot Actuator cung cấp endpoint phục vụ health check, metrics, thông tin ứng dụng và thao tác quản trị. Việc một endpoint tồn tại trong ứng dụng không có nghĩa endpoint đó tự động được công khai qua HTTP hoặc JMX.

Mặc định, Actuator chỉ expose một tập endpoint web giới hạn. Quản trị viên có thể cấu hình include để cho phép một tập endpoint và exclude để loại endpoint khỏi exposure. Đây là một lớp kiểm soát bề mặt truy cập, cần phối hợp với Spring Security, network policy, authentication/authorization và cấu hình riêng cho từng môi trường.

Trong module **SPRING_BOOT_OBSERVABILITY**, Actuator là cửa sổ kiểm tra health, metrics và trạng thái vận hành của Spring Boot. Cấu hình exposure sai có thể làm lộ thông tin môi trường, cấu hình, bean graph hoặc tạo endpoint có khả năng thay đổi trạng thái ứng dụng. Bài này giải thích semantics include/exclude, HTTP/JMX exposure, ví dụ cấu hình, endpoint nhạy cảm và cách xác minh những gì thực sự truy cập được.

## 1. Endpoint tồn tại khác với endpoint được expose

Actuator endpoint có thể được xem qua ba lớp:

1. **Endpoint availability:** endpoint có được cung cấp bởi dependency/auto-configuration và điều kiện runtime hay không.
2. **Exposure:** endpoint có được expose qua web hoặc JMX hay không.
3. **Access/security:** caller có được phép truy cập endpoint đó theo access policy và security rules hay không.

```text
Actuator endpoint implementation
          |
          v
   Endpoint available?
          |
          v
   Exposure configuration
      |             |
      v             v
    HTTP           JMX
      |             |
      v             v
 Security / access controls
          |
          v
      Authorized caller
```

Ví dụ, metrics endpoint có thể có trong classpath nhưng không được expose qua HTTP. Nếu gọi /actuator/metrics và nhận 404, chưa thể kết luận metrics registry không hoạt động; có thể endpoint chưa được include hoặc management base path khác.

Ngược lại, include endpoint chỉ quyết định exposure. Nó không tự xác thực caller, không tự mã hóa dữ liệu và không thay thế authorization. Không expose endpoint nhạy cảm ra Internet chỉ vì đã có Spring Security dependency.

## 2. Include và exclude có nghĩa gì?

Các property web exposure phổ biến:

- management.endpoints.web.exposure.include: danh sách endpoint được expose qua HTTP.
- management.endpoints.web.exposure.exclude: danh sách endpoint bị loại khỏi HTTP exposure.

Ví dụ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
        exclude: env,configprops
```

Ví dụ này yêu cầu expose health, info, metrics và prometheus qua web, đồng thời loại env và configprops khỏi web exposure. Danh sách endpoint thực tế phụ thuộc dependency và điều kiện runtime. Exclude được ưu tiên khi endpoint xuất hiện trong cả include và exclude; vì vậy dùng exclude như một lớp deny rõ ràng.

Nếu include không được cấu hình, Spring Boot dùng tập mặc định cho web exposure của phiên bản tương ứng (thường chỉ có health). Khi đặt include rõ ràng, hãy xem nó như allowlist cho endpoint mong muốn. Đừng giả định mọi endpoint mới được thêm bởi dependency sẽ tự động được expose.

Wildcard * có thể dùng để chỉ tất cả endpoint, nhưng expose toàn bộ endpoint web thường không phù hợp production. Nếu dùng wildcard, cần exclude endpoint không muốn công khai và kiểm soát security/network nghiêm ngặt; allowlist tường minh thường dễ review hơn.

## 3. Cấu hình include cho HTTP

Một cấu hình production có phạm vi hẹp:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
```

Nếu ứng dụng cần truy vấn metrics qua Actuator metrics endpoint để chẩn đoán nội bộ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

Chỉ include metrics khi có nhu cầu truy vấn endpoint này. Trong nhiều hệ thống, Prometheus scrape endpoint là giao diện thu thập metrics chính, còn /actuator/metrics/{metricName} dành cho kiểm tra trực tiếp.

Có thể thay management base path:

```yaml
management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info,prometheus
```

Khi đó đường dẫn có thể là /manage/health, /manage/info và /manage/prometheus thay vì /actuator/.... Base path không phải cơ chế bảo mật; đổi path không ngăn được caller dò tìm endpoint.

## 4. Exclude endpoint rõ ràng

Ví dụ loại một endpoint khỏi web exposure:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: env,configprops,heapdump,threaddump,loggers
```

Đây là ví dụ minh họa semantics, không phải cấu hình production khuyến nghị. Include wildcard làm bề mặt web rộng; exclude một vài endpoint không đảm bảo danh sách còn lại an toàn. Một dependency mới có thể bổ sung endpoint mà wildcard tự động expose.

Đặc biệt, không dùng include wildcard để giải quyết nhanh lỗi endpoint 404 ở production. Hãy xác định endpoint cần thiết và include tường minh. Nếu có endpoint không được phép truy cập, exclude rõ ràng và kiểm tra security policy độc lập.

## 5. Web exposure và JMX exposure là hai cấu hình riêng

Actuator có thể expose endpoint qua HTTP hoặc JMX. Cấu hình web exposure không tự quyết định JMX exposure.

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
    jmx:
      exposure:
        include: health,info,metrics
```

Trong ví dụ, HTTP chỉ expose health/info/prometheus, còn JMX expose health/info/metrics. Nếu ứng dụng không sử dụng JMX, cân nhắc tắt JMX exposure hoặc cấu hình allowlist phù hợp với nền tảng quản trị.

Không giả định endpoint đã exclude khỏi web cũng bị loại khỏi JMX. Kiểm tra cả hai transport nếu runtime có bật JMX. Tương tự, kiểm tra các management port/interface riêng nếu ứng dụng tách management traffic khỏi application traffic.

## 6. Endpoint nào thường được dùng?

| Endpoint | Mục đích | Cân nhắc khi expose |
| --- | --- | --- |
| health | Trạng thái health tổng thể | Có thể công khai mức thông tin tối thiểu; chi tiết cần bảo vệ |
| info | Thông tin ứng dụng do cấu hình cung cấp | Chỉ công bố fields đã duyệt |
| metrics | Truy vấn metric trong registry | Có thể tiết lộ tên/tag và trạng thái nội bộ |
| prometheus | Expose metrics cho Prometheus scrape | Chỉ cho scraper đáng tin cậy truy cập |
| env | Environment properties | Có thể tiết lộ cấu hình và secret nếu không được lọc |
| configprops | Configuration properties | Có thể tiết lộ cấu trúc/cấu hình ứng dụng |
| beans | Bean definitions | Thông tin nội bộ về cấu trúc ứng dụng |
| conditions | Auto-configuration conditions | Hữu ích debug, nhưng tiết lộ chi tiết runtime |
| mappings | Request mappings | Có thể lộ routes nội bộ |
| loggers | Xem/đổi log levels | Có thể thay đổi verbosity và làm tăng log volume |
| heapdump | Tạo heap dump | Có thể chứa dữ liệu nhạy cảm, tốn tài nguyên |
| threaddump | Thread dump | Có thể lộ thread names, stack và thông tin runtime |
| shutdown | Dừng ứng dụng nếu được bật | Endpoint thao tác nguy hiểm; không expose tùy tiện |

Endpoint có thể không tồn tại nếu dependency hoặc điều kiện tương ứng không có. Danh sách và semantics phụ thuộc Spring Boot version. Kiểm tra reference của đúng version trước khi dùng trong cấu hình.

## 7. Include không thay thế authentication và authorization

Ngay cả endpoint health hoặc prometheus cũng có thể tiết lộ thông tin hữu ích cho attacker, ví dụ service đang phụ thuộc database nào, có broker nào hoặc ứng dụng đang dùng version nào. Cần quyết định endpoint nào có thể truy cập anonymous và endpoint nào chỉ dành cho monitoring network.

Một nguyên tắc:

- Expose tường minh endpoint cần thiết.
- Chỉ mở management port/interface trong network tin cậy.
- Dùng authentication cho management endpoints không công khai.
- Áp dụng authorization theo role/service identity.
- Giới hạn health details và thông tin nhạy cảm.
- Theo dõi access logs/audit cho thao tác quản trị.

Nếu Spring Security có mặt, ứng dụng cần security rules cho management endpoints. Cấu hình include không tự tạo các rules đó. Ví dụ security matcher và DSL phụ thuộc Spring Security version, management port và cấu trúc filter chain; hãy cấu hình theo đúng app thay vì copy một rule chung cho mọi deployment.

Không cho phép tất cả request tới /actuator/** chỉ vì Prometheus cần scrape /actuator/prometheus. Có thể tạo rule riêng cho scraper identity và rule khác cho health probe, còn các endpoint quản trị yêu cầu role mạnh hơn.

## 8. Health endpoint và health details

Health endpoint thường được dùng bởi load balancer, orchestrator và monitoring system. Có thể expose health công khai với response tối giản, trong khi chỉ caller đã xác thực mới xem component details.

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
```

Giá trị hợp lệ và authorization behavior phụ thuộc Spring Boot version/configuration. Không bật always cho production nếu response có tên database, broker, disk path hoặc dependency nội bộ. Lưu ý health groups/readiness/liveness là cấu hình riêng về nội dung và nhóm health; exposure quyết định endpoint group nào được truy cập qua transport.

Health details không giống endpoint include/exclude. Một endpoint health có thể được expose nhưng chỉ trả trạng thái tổng thể cho caller không có quyền; caller được authorize mới nhận details theo policy.

## 9. Cấu hình theo profile môi trường

Một cách phổ biến là giữ cấu hình chung an toàn và mở rộng có kiểm soát ở profile nội bộ:

```yaml
# application.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info
```

```yaml
# application-prod.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
```

```yaml
# application-dev.yml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: shutdown
```

Không để profile dev vô tình được active ở production. Kiểm tra profile activation, environment variables, command-line overrides và config server; property có thể bị override bởi nguồn cấu hình có precedence cao hơn file YAML.

## 10. Endpoint exposure và access policy theo phiên bản

Các phiên bản Spring Boot mới hơn có thể cung cấp thêm cấu hình access cho endpoint, chẳng hạn chọn endpoint được phép truy cập theo access policy và giới hạn dữ liệu endpoint trả về. Các property này khác với exposure:

- **Exposure** quyết định endpoint có được publish qua web/JMX hay không.
- **Access policy** quyết định endpoint có được phép truy cập theo cơ chế Actuator hay không.
- **Security authorization** quyết định caller nào được phép truy cập.

Không nhầm ba lớp này. Một endpoint bị disable theo access policy không trở nên an toàn chỉ vì đường dẫn của nó không được đoán ra; và endpoint được expose vẫn cần network/security controls. Property names và default access policy thay đổi theo Spring Boot release; dùng metadata của version đang triển khai.

## 11. Kiểm tra endpoint thực sự được expose

Sau khi cấu hình, xác minh từ runtime thay vì chỉ đọc YAML:

1. Khởi động ứng dụng với profile và environment variables giống deployment.
2. Gọi management base path hoặc endpoint discovery link nếu được bật.
3. Kiểm tra endpoint được include trả response như mong đợi.
4. Kiểm tra endpoint bị exclude không truy cập được qua HTTP.
5. Nếu JMX được bật, kiểm tra JMX exposure riêng.
6. Kiểm tra security rules bằng caller anonymous và caller có role.
7. Xác nhận response health không lộ component details cho caller không được authorize.
8. Kiểm tra endpoint có được expose trên management port/interface nào.

Ví dụ kiểm tra:

```bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/prometheus
curl -i http://localhost:8080/actuator/env
```

Kỳ vọng phụ thuộc cấu hình: health/prometheus có thể được phép theo policy; env cần không được expose hoặc phải bị bảo vệ. Status code một mình không đủ phân biệt endpoint không tồn tại, không expose, access bị từ chối hay security filter chặn. Đọc response, application logs và security configuration trong môi trường test.

### Ma trận xác minh

| Endpoint | Include? | Exclude? | Kết quả cần xác nhận |
| --- | --- | --- | --- |
| health | Có | Không | Probe truy cập được, details đúng policy |
| info | Có | Không | Chỉ hiển thị thông tin đã duyệt |
| prometheus | Có | Không | Scraper identity truy cập được |
| env | Không | Có hoặc không nằm allowlist | Caller không thể đọc environment |
| shutdown | Không | Có | Không có thao tác dừng từ web |

Đây là ma trận minh họa; điều chỉnh theo endpoint availability và policy của ứng dụng.

## 12. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng include wildcard ở production | Dependency mới có thể làm lộ endpoint mới | Allowlist tường minh |
| Nghĩ include là authentication | Caller không được xác thực vẫn có thể truy cập nếu security không chặn | Cấu hình Security/network riêng |
| Chỉ exclude khỏi web, quên JMX | Endpoint vẫn có thể lộ qua JMX | Kiểm tra từng transport |
| Public env/configprops | Lộ cấu hình hoặc metadata nội bộ | Không expose hoặc bảo vệ chặt |
| Public heapdump | Rủi ro lộ dữ liệu và tải tài nguyên lớn | Giới hạn quyền truy cập và quy trình |
| Dùng health details always | Lộ dependency/component names | when-authorized hoặc policy phù hợp |
| Đổi base path để “bảo mật” | Endpoint vẫn có thể bị dò | Authentication, authorization và network controls |
| Kiểm tra chỉ ở local profile | Production có overrides khác | Test profile/config giống deployment |

## 13. Bài tập tình huống

Một ứng dụng Spring Boot đang dùng cấu hình:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: shutdown
```

Team vận hành chỉ cần health probe và Prometheus scrape. Ứng dụng còn có env, configprops, beans, mappings, loggers và heapdump endpoints sẵn có.

**Câu hỏi:**

1. Cấu hình hiện tại expose những endpoint nào theo nguyên tắc?
2. Vì sao chỉ exclude shutdown chưa đủ?
3. Nên viết allowlist production như thế nào?
4. Include health có nghĩa mọi caller được xem health details không?
5. Cần kiểm tra HTTP và JMX exposure ra sao?

**Gợi ý phân tích:**

- Wildcard cho phép tất cả endpoint đủ điều kiện được expose qua web; exclude shutdown chỉ loại endpoint đó.
- Các endpoint như env, configprops, beans, mappings, loggers hoặc heapdump có thể tiết lộ thông tin hay cho phép thao tác.
- Nếu nhu cầu chỉ là health và Prometheus, allowlist tường minh health,prometheus (thêm info/metrics nếu có mục đích rõ ràng).
- Exposure không quyết định authentication/authorization hay health detail visibility. Cấu hình health details theo caller được authorize.
- Xem web exposure và JMX exposure riêng; áp dụng security/network policy cho scraper và management callers.

### Checklist hoàn thành

| Nội dung | Có thể giải thích/kiểm tra |
| --- | --- |
| Endpoint availability | Phân biệt endpoint có sẵn và được expose |
| Include | Tạo allowlist endpoint cần thiết |
| Exclude | Loại endpoint khỏi exposure và hiểu precedence |
| Wildcard | Nhận biết rủi ro include tất cả |
| HTTP/JMX | Cấu hình và kiểm tra riêng từng transport |
| Security | Không nhầm exposure với authentication/authorization |
| Health details | Giới hạn component information theo quyền |
| Profiles | Kiểm soát khác biệt dev/prod và property overrides |
| Access policy | Phân biệt exposure, Actuator access và Spring Security |
| Verification | Test endpoint được phép, bị loại và caller khác quyền |

**Ghi nhớ:** Include và exclude kiểm soát endpoint Actuator nào được expose qua một transport; chúng không tự xác thực caller. Dùng allowlist tường minh cho production, kiểm tra HTTP và JMX riêng, giới hạn health details và bảo vệ endpoint quản trị bằng security/network policy. Các endpoint như env, configprops, beans, mappings, loggers và heapdump có thể tiết lộ thông tin hoặc thay đổi trạng thái, vì vậy chỉ mở khi có nhu cầu rõ ràng. Xác minh cấu hình ở đúng profile/runtime và kiểm tra cả endpoint được phép lẫn endpoint phải bị chặn.

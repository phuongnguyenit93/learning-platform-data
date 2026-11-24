# Log level theo environment trong Spring Boot

**Log level theo environment** là cách cấu hình mức độ chi tiết của logging theo môi trường chạy ứng dụng, chẳng hạn local, dev, test, staging và prod. Cùng một phiên bản Spring Boot có thể cần log chi tiết khi phát triển, log vừa đủ khi kiểm thử tích hợp và log gọn trong production để hỗ trợ vận hành mà không tạo quá nhiều dữ liệu hoặc làm lộ thông tin nhạy cảm.

Trong module **SPRING_BOOT_OBSERVABILITY**, logging là một trong ba tín hiệu quan sát cùng metrics và distributed tracing. Log level quyết định sự kiện nào được ghi; correlation fields giúp liên kết logs với Trace ID/Span ID; Resource và deployment metadata giúp xác định service/version/environment phát sinh sự kiện. Bài thuộc chương **Logging**, tập trung vào profiles, application-{profile}.yml, biến môi trường, logger hierarchy, logging groups, Actuator và các nguyên tắc vận hành an toàn.

## 1. Log level là gì?

Log level là mức độ nghiêm trọng hoặc mức chi tiết của sự kiện logging. Các mức phổ biến trong SLF4J/Logback và Spring Boot:

| Level | Ý nghĩa | Tình huống thường dùng |
| --- | --- | --- |
| TRACE | Chi tiết rất nhỏ, phục vụ phân tích sâu | Theo dõi từng bước nội bộ trong thời gian ngắn |
| DEBUG | Thông tin chẩn đoán dành cho developer | Nhánh xử lý, trạng thái nội bộ, dữ liệu đã làm sạch |
| INFO | Sự kiện vận hành bình thường đáng quan tâm | Service started, request hoàn tất, job chạy |
| WARN | Bất thường nhưng ứng dụng vẫn tiếp tục | Retry, fallback, cấu hình gần chạm ngưỡng |
| ERROR | Lỗi khiến thao tác thất bại hoặc cần can thiệp | Exception không xử lý được, dependency call thất bại |

Một logger thường chỉ ghi sự kiện có level bằng hoặc quan trọng hơn ngưỡng được cấu hình. Ví dụ logger ở INFO cho phép INFO, WARN, ERROR, nhưng bỏ qua DEBUG và TRACE.

\[
TRACE \rightarrow DEBUG \rightarrow INFO \rightarrow WARN \rightarrow ERROR
\]

OFF có thể được dùng để tắt một logger; ALL thường cho phép mọi mức. Không đặt root logger thành TRACE/DEBUG trên production một cách rộng rãi.

## 2. Vì sao log level cần khác nhau theo environment?

- **Local/development:** developer cần thấy nhiều chi tiết để hiểu code path và phát hiện lỗi.
- **Test/CI:** log cần đủ rõ để xác định test failure, nhưng không nên tạo output quá lớn.
- **Staging:** gần production để xác nhận hành vi vận hành, tích hợp và tracing.
- **Production:** ưu tiên tín hiệu có giá trị vận hành, ổn định, tìm kiếm được và có chi phí kiểm soát.

| Environment | Level minh họa | Mục đích |
| --- | --- | --- |
| local | DEBUG | Quan sát luồng nghiệp vụ |
| test | INFO | Output gọn, thấy sự kiện chính |
| staging | INFO hoặc DEBUG có chọn lọc | Điều tra tích hợp trước release |
| production | INFO | Log vận hành bình thường |
| production incident | DEBUG tạm thời cho logger cụ thể | Điều tra có thời hạn, sau đó hoàn nguyên |

Không có bảng mức log phù hợp cho mọi hệ thống. Mức cần thiết phụ thuộc traffic, độ nhạy dữ liệu, logging backend, filtering, retention và cách điều tra sự cố.

## 3. Logger hierarchy: root, package và class

Log level thường được cấu hình theo tên logger. Trong Java, logger hay được đặt theo tên class, ví dụ com.example.order.OrderService. Logback hỗ trợ hierarchy theo package/name. Logger con có thể kế thừa level từ logger cha nếu không có cấu hình riêng.

Ví dụ:
- Root logger: INFO.
- Package com.example: INFO.
- Package com.example.order: DEBUG.
- Class com.example.order.PaymentClient: TRACE.

### 3.1. Ví dụ cấu hình nhiều cấp

```yaml
logging:
  level:
    root: INFO
    com.example: INFO
    com.example.order: DEBUG
    com.example.order.PaymentClient: TRACE
    org.springframework.web: WARN
```

Level của logger con có thể ghi đè level kế thừa từ package cha. Tránh bật TRACE cho package lớn vì lượng log có thể tăng rất nhanh.

### 3.2. Root logger và logger riêng

root là ngưỡng mặc định cho logger không có mức riêng. Root WARN có thể làm mất INFO quan trọng; root DEBUG có thể tạo lượng log rất lớn từ framework, HTTP client và thư viện bên thứ ba.

Cấu hình thực tế thường đặt root ở mức vừa phải, package ứng dụng ở INFO hoặc DEBUG theo môi trường, thư viện ồn ở WARN và một class/package cụ thể ở DEBUG khi điều tra.

## 4. Cấu hình cơ bản trong application.yml

Spring Boot hỗ trợ cấu hình mức log qua logging.level.

```yaml
logging:
  level:
    root: INFO
    com.example: INFO
    org.springframework.web: WARN
    org.hibernate.SQL: WARN
```

application.yml chứa cấu hình mặc định. Khi không có profile-specific override, ứng dụng dùng các giá trị này. Nên bắt đầu bằng baseline đơn giản gồm root logger, package ứng dụng và một số logger framework cần điều chỉnh. Xác định logger name từ output thay vì tùy tiện thêm mọi package.

## 5. Dùng Spring Profiles để tách log level

Spring Profiles cho phép cấu hình khác nhau theo môi trường. Một cách phổ biến là dùng application.yml, application-local.yml, application-test.yml, application-staging.yml và application-prod.yml.

application.yml:

```yaml
spring:
  application:
    name: order-service

logging:
  level:
    root: INFO
    com.example: INFO
    org.springframework: WARN
```

application-local.yml:

```yaml
logging:
  level:
    root: INFO
    com.example: DEBUG
    org.springframework.web: INFO
    org.hibernate.SQL: DEBUG
```

application-test.yml:

```yaml
logging:
  level:
    root: INFO
    com.example: INFO
    com.example.order: DEBUG
```

application-prod.yml:

```yaml
logging:
  level:
    root: INFO
    com.example: INFO
    org.springframework: WARN
    org.hibernate: WARN
    org.hibernate.SQL: WARN
```

Khi prod active, Spring Boot nạp cấu hình profile tương ứng và kết hợp với cấu hình mặc định theo externalized configuration. Kiểm tra effective configuration khi có nhiều nguồn override.

### 5.1. Kích hoạt profile

```bash
SPRING_PROFILES_ACTIVE=prod
```

Hoặc:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Khi chạy trong container/orchestrator, environment variable hoặc deployment config thường thuận tiện. Không hardcode prod vào artifact dùng chung cho mọi môi trường.

### 5.2. Profile config không phải file bí mật

Các file application-prod.yml thường được đóng gói cùng ứng dụng. Không lưu password, token hoặc private keys trong đó. Secrets phải đến từ secret management phù hợp.

## 6. YAML multi-document với on-profile

Có thể chia nhiều YAML documents trong cùng file bằng dấu phân cách document và điều kiện profile.

```yaml
spring:
  application:
    name: order-service

logging:
  level:
    root: INFO
    com.example: INFO

---
spring:
  config:
    activate:
      on-profile: local

logging:
  level:
    com.example: DEBUG
    org.springframework.web: INFO
    org.hibernate.SQL: DEBUG

---
spring:
  config:
    activate:
      on-profile: prod

logging:
  level:
    root: INFO
    com.example: INFO
    org.springframework: WARN
    org.hibernate: WARN
```

Document có on-profile chỉ áp dụng khi profile tương ứng active. Nếu nhiều profiles/documents cùng match, thứ tự và precedence cần được xem xét. Giữ cấu hình rõ ràng để tránh hai document đặt cùng logger ở mức khác nhau ngoài ý muốn.

## 7. Cấu hình qua biến môi trường

Các property Spring Boot có thể externalize qua environment variables.

```bash
LOGGING_LEVEL_ROOT=INFO
LOGGING_LEVEL_COM_EXAMPLE=DEBUG
SPRING_PROFILES_ACTIVE=local
```

Với property đơn giản, relaxed binding chuyển tên property sang uppercase có dấu gạch dưới. Tuy nhiên, **logger names có thể chứa dấu gạch dưới hoặc ký tự đặc biệt**, nên ánh xạ tên logger phức tạp sang environment variable có thể mơ hồ hoặc không biểu diễn chính xác. Tên class có chữ hoa hoặc dấu $ của nested class cũng cần kiểm tra.

Đối với tên logger phức tạp, profile-specific YAML, ConfigMap/configuration source hoặc Actuator loggers endpoint thường rõ ràng hơn.

### 7.1. Placeholder cho root level

Có thể dùng biến do deployment quy ước:

```yaml
logging:
  level:
    root: ${APP_LOG_LEVEL:INFO}
```

Biến APP_LOG_LEVEL sẽ dùng INFO nếu không có giá trị. Có thể externalize một package ổn định tương tự, nhưng không nên tạo quá nhiều biến lẻ cho từng class.

### 7.2. Không lấy profile từ request

spring.profiles.active phải được chọn từ cấu hình triển khai đáng tin cậy. Không để HTTP request, header hoặc dữ liệu client kích hoạt profile dev/debug trong production.

## 8. Externalized configuration và precedence

Spring Boot lấy cấu hình từ nhiều nguồn: file cấu hình, profile-specific files, environment variables, system properties, command-line arguments, config tree và các nguồn khác tùy ứng dụng. Nguồn có độ ưu tiên cao hơn sẽ quyết định giá trị effective.

| Nguồn | logging.level.com.example |
| --- | --- |
| application.yml | INFO |
| application-prod.yml | INFO |
| Environment variable được map | DEBUG |
| Command-line argument có độ ưu tiên cao | WARN |

Bảng minh họa nhiều nguồn cùng đặt property; thứ tự hiệu lực chính xác cần đối chiếu property source và cấu hình Spring Boot đang dùng.

### Cách tìm nguồn gây override

1. Kiểm tra profile thực sự active.
2. Kiểm tra environment variables của process/container.
3. Kiểm tra Java system properties và command-line arguments.
4. Kiểm tra config server, mounted config tree hoặc deployment overlays.
5. Kiểm tra Actuator logger level hiện tại.
6. Kiểm tra logging configuration native như logback-spring.xml.

Không chỉnh nhiều nguồn cùng lúc trước khi tìm được nguồn override. Ghi lại giá trị hiệu lực và nguồn đã thay đổi trong deployment record.

## 9. Logging groups

Spring Boot hỗ trợ logging groups để đặt level cho một tập logger liên quan bằng tên nhóm. Một số nhóm dựng sẵn phụ thuộc version; ứng dụng cũng có thể định nghĩa nhóm riêng.

```yaml
logging:
  group:
    order-flow:
      - com.example.order
      - com.example.inventory
      - com.example.payment
  level:
    root: INFO
    order-flow: DEBUG
```

Khi đặt order-flow ở DEBUG, các logger trong nhóm được điều chỉnh theo level nhóm. Đây là cách tiện khi cần bật log cho subsystem có nhiều package.

Nhóm dựng sẵn như web hoặc sql phụ thuộc Spring Boot version. Kiểm tra reference documentation hoặc trạng thái logger trên runtime.

## 10. Log level cho thư viện và framework

```yaml
logging:
  level:
    root: INFO
    com.example: INFO
    org.springframework.web: WARN
    org.springframework.security: INFO
    org.hibernate.SQL: WARN
    org.apache.kafka: WARN
    com.zaxxer.hikari: INFO
```

Tên logger và hành vi có thể khác theo version thư viện. Không hạ level framework xuống ERROR chỉ để làm log sạch nếu điều đó che mất warning hoặc thông tin quan trọng.

### 10.1. Hibernate SQL và bind parameters

SQL logging hữu ích khi debug query, nhưng SQL text và bind values có thể chứa thông tin nhạy cảm. Mỗi request cũng có thể tạo nhiều dòng log. Không bật bind parameter logging trong production nếu chưa đánh giá PII, credentials, dữ liệu thanh toán và retention.

### 10.2. HTTP client/server logs

Log raw request/response headers hoặc bodies có thể làm lộ cookies, authorization tokens và dữ liệu cá nhân. Log level DEBUG không phải biện pháp bảo mật; logging code vẫn phải redact dữ liệu nhạy cảm trước khi ghi.

## 11. Kết hợp log level với Logback

Spring Boot hỗ trợ Logback khi dependency phù hợp có mặt. Nếu cần layout, appender, rolling policy hoặc filter riêng, ứng dụng có thể dùng logback-spring.xml.

Ví dụ fragment root logger:

```xml
<configuration>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Đây chỉ là fragment minh họa; appender CONSOLE cần được định nghĩa. Khi có native logging configuration, cần hiểu cách Spring Boot kết hợp nó với logging.level và profile-specific sections.

logback-spring.xml hỗ trợ một số extension của Spring Boot như tham chiếu profile/property trong quá trình cấu hình. Không phải mọi extension đều hoạt động trong logback.xml thuần vì file có thể được logging system nạp quá sớm.

Tránh cấu hình cùng logger ở hai nơi. Trước khi thêm Logback tùy biến, xác định nhu cầu thật: JSON layout, appender remote, rolling, async logging hay redaction. Nếu chỉ cần đổi level, logging.level thường đơn giản hơn.

## 12. Thay đổi log level runtime qua Actuator

Spring Boot Actuator cung cấp endpoint loggers để đọc và thay đổi mức log tại runtime khi endpoint được expose và bảo vệ đúng cách.

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - loggers
```

Đọc logger:

```http
GET /actuator/loggers/com.example.order
```

Thay đổi level:

```http
POST /actuator/loggers/com.example.order
Content-Type: application/json

{
  "configuredLevel": "DEBUG"
}
```

URL có thể khác nếu management base path/port được cấu hình khác. Payload configuredLevel có thể nhận DEBUG, INFO, WARN, ERROR hoặc null để xóa override runtime và quay về mức kế thừa/configuration hiện có theo implementation.

### 12.1. Runtime override có thể không bền vững

Override qua Actuator thường có hiệu lực trong bộ nhớ process. Nó có thể mất khi service restart, pod được thay thế hoặc cấu hình được nạp lại.

Sau điều tra:
- Hoàn nguyên logger về mức phù hợp.
- Ghi lại ai thay đổi, lúc nào, lý do và thời hạn.
- Nếu mức log mới phải duy trì, cập nhật nguồn cấu hình được quản lý.
- Kiểm tra mọi replicas; thay đổi một pod chưa chắc thay đổi toàn service.

### 12.2. Bảo vệ Actuator loggers endpoint

Endpoint này có thể làm thay đổi lượng telemetry và expose chi tiết nội bộ. Không mở công khai Internet. Giới hạn bằng authentication/authorization, network policy, management port riêng và audit phù hợp. Chỉ người có quyền vận hành mới được điều chỉnh log level production.

## 13. Log level, metrics, logs và tracing

Log level ảnh hưởng sự kiện xuất hiện trong logs, nhưng không tự thay đổi metrics/tracing sampling.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Log level | Lọc log events | Root INFO, package DEBUG |
| Metrics | Đếm/đo hành vi tổng thể | Request count, latency, error rate |
| Tracing sampling | Chọn traces/spans được ghi/xuất | Trace ratio 10% |
| Trace/log correlation | Liên kết log event với trace | Trace ID, Span ID trong MDC |
| Resource attributes | Định danh nguồn phát telemetry | service.name, environment, version |

Một request có thể không có trace trong backend do sampling nhưng log WARN/ERROR vẫn được ghi. Ngược lại, trace có thể tồn tại mà không có log DEBUG vì logger đang ở INFO.

Khi tracing integration đặt Trace ID/Span ID vào MDC, log pattern có thể hiển thị chúng. Việc có correlation fields không yêu cầu bật DEBUG. Có thể giữ root INFO và vẫn liên kết log events ở INFO, WARN, ERROR với trace.

Không ghi một dòng DEBUG cho từng request để suy ra request rate hoặc latency. Dùng Micrometer metrics cho số liệu tổng hợp, traces cho hành trình request được chọn, logs cho sự kiện cần diễn giải.

## 14. Production logging: chi tiết vừa đủ và an toàn

Một cấu hình production tốt thường:
- Giữ root logger ở INFO hoặc mức đã được vận hành thống nhất.
- Chỉ nâng DEBUG cho package/class cần thiết và trong thời gian ngắn.
- Giảm log noise framework có chọn lọc, không che giấu lỗi quan trọng.
- Dùng structured logging khi backend cần parse/search fields.
- Đưa Trace ID/Span ID vào log correlation nếu có tracing.
- Redact credentials, cookies, PII và raw payload.
- Đặt retention và access control cho log backend.
- Theo dõi log volume, ingestion errors, dropped events và disk usage.

### 14.1. Log volume là chi phí vận hành

Ví dụ một service ghi 500 dòng/giây, mỗi dòng trung bình 1 KB:

\[
500 \times 1\text{ KB} \times 86\,400 \approx 43.2\text{ GB/ngày}
\]

Đây là ước lượng thô trước compression, batching, indexing và retention. Nếu bật DEBUG làm số dòng tăng gấp 5, lượng dữ liệu có thể tăng đáng kể.

Cần cân nhắc chi phí truyền, index, lưu trữ, truy vấn và tác động CPU/I/O.

### 14.2. Redaction phải ở nguồn

Không ghi secrets rồi kỳ vọng backend sẽ luôn xóa chúng. Redact tại nơi tạo log và kiểm tra exception messages, headers, DTO toString(), SQL, structured fields và third-party library logs.

Không serialize toàn bộ request/response object trong DEBUG mặc định. Dùng allowlist fields và length limits.

## 15. Mẫu cấu hình theo environment

### 15.1. Local

```yaml
# application-local.yml
logging:
  level:
    root: INFO
    com.example: DEBUG
    org.springframework.web: INFO
    org.hibernate.SQL: DEBUG
```

### 15.2. Test

```yaml
# application-test.yml
logging:
  level:
    root: INFO
    com.example: INFO
    com.example.order: DEBUG
    org.springframework: WARN
```

### 15.3. Staging

```yaml
# application-staging.yml
logging:
  level:
    root: INFO
    com.example: INFO
    com.example.integration: DEBUG
    org.springframework: WARN
```

Staging có thể bật DEBUG cho integration package khi kiểm thử downstream, nhưng nên có lý do và thời hạn. Khi staging mô phỏng production traffic, giữ log levels gần production để đo đúng volume và hiệu năng.

### 15.4. Production

```yaml
# application-prod.yml
logging:
  level:
    root: INFO
    com.example: INFO
    org.springframework: WARN
    org.hibernate: WARN
```

Các mức trên là baseline tham khảo. Thay bằng logger names và mức độ đã được kiểm chứng với application version thực tế.

## 16. Troubleshooting log level theo environment

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| DEBUG không xuất hiện ở local | Profile chưa active hoặc package logger sai tên | Kiểm tra active profiles và logger name |
| Production vẫn có DEBUG | Environment/command line override hoặc Actuator runtime override | Kiểm tra effective logger level và property sources |
| Đã đổi YAML nhưng không tác dụng | File profile không nạp, sai profile hoặc native config chi phối | Kiểm tra config loading và logging system |
| Framework logs quá nhiều | Root/package level quá thấp | Đặt level riêng cho logger framework ồn |
| Không thấy INFO ở production | Root/package bị đặt WARN/ERROR | Kiểm tra hierarchy và effective level |
| Package không kế thừa root | Logger child có explicit level riêng | Đọc configured/effective level |
| Actuator đổi level nhưng restart mất | Runtime override không persistent | Cập nhật nguồn cấu hình lâu dài |
| Actuator trả 404 | Endpoint chưa expose hoặc management path/port khác | Kiểm tra exposure và base path |
| Actuator trả 401/403 | Authentication/authorization policy | Kiểm tra security chain/quyền operator |
| Chỉ một replica đổi level | Gọi endpoint vào một pod | Thực hiện theo quy trình cho từng instance |
| Env var không điều khiển logger class | Logger name không map đơn giản | Dùng YAML/config source hoặc Actuator |
| Log volume đột biến | DEBUG/TRACE quá rộng hoặc retry loop | Đối chiếu config và volume per logger |
| Log có dữ liệu nhạy cảm | Logging code/third-party logger không redact | Redact tại nguồn và giảm output |
| Trace ID không có trong logs | Tracing/MDC chưa cấu hình hoặc context mất | Kiểm tra integration và async propagation |
| Logs không đến backend | Appender/agent/collector pipeline lỗi | Kiểm tra shipper/collector riêng |

### Quy trình debug

1. Xác nhận environment/profile active.
2. Kiểm tra logger name và hierarchy.
3. Đọc effective level của root và logger cụ thể.
4. Kiểm tra cấu hình từ YAML, environment, system properties hay command line.
5. Kiểm tra Actuator runtime override.
6. Kiểm tra native Logback configuration nếu có.
7. Kiểm tra log output ở process/container trước khi điều tra shipper/backend.
8. Nếu log đã xuất khỏi app nhưng không thấy trong backend, kiểm tra pipeline vận chuyển và ingestion.
9. Sau điều tra, hoàn nguyên logger đã nâng level và xác nhận log volume bình thường.

## 17. Bài thực hành: cấu hình log level cho bốn môi trường

Mục tiêu là có một ứng dụng Spring Boot dùng cùng artifact nhưng chạy log levels khác nhau theo local, test, staging và prod.

### Chuẩn bị

- Spring Boot application có SLF4J/Logback.
- Một service class có logger.
- Các profile config riêng.
- Actuator nếu muốn thực hành runtime loggers endpoint.

Ví dụ class:

```java
package com.example.order;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    public void createOrder(String orderReference) {
        log.trace("Entering createOrder");
        log.debug("Validating order reference");
        log.info("Creating order");
        log.warn("Using fallback inventory source");
        log.error("Order creation failed");
    }
}
```

Đây là ví dụ minh họa level, không phải cách ghi log lỗi production hoàn chỉnh. Không đưa orderReference thật hoặc dữ liệu cá nhân vào log nếu chưa được phép.

### Bước 1 — Cấu hình baseline

Trong application.yml, đặt root INFO và package ứng dụng INFO. Chạy app không active profile tùy chỉnh; xác nhận INFO, WARN, ERROR hiển thị, DEBUG, TRACE bị lọc.

### Bước 2 — Kích hoạt local

Chạy với SPRING_PROFILES_ACTIVE=local. Xác nhận logger com.example ở DEBUG và logger SQL ở mức đã khai báo. Kiểm tra log framework được kiểm soát.

### Bước 3 — Chạy test

Kích hoạt profile test; xác nhận output đủ thông tin khi test fail nhưng không noisy. Chạy cùng một test và so sánh output với local.

### Bước 4 — Chạy staging

Kích hoạt staging; chỉ bật package integration cần kiểm thử. Ghi lại lý do vì sao logger đó được nâng mức.

### Bước 5 — Chạy production config trong lab

Kích hoạt prod; xác nhận root/package vẫn ở baseline. Không cần deploy production thật để thực hành.

### Bước 6 — Override bằng environment variable

Đặt APP_LOG_LEVEL=DEBUG nếu file cấu hình dùng placeholder tương ứng hoặc thử LOGGING_LEVEL_ROOT. Kiểm tra effective level để hiểu nguồn nào đã override.

### Bước 7 — Thử Actuator loggers

Expose loggers endpoint trong lab và đọc logger com.example.order. Đổi configuredLevel thành DEBUG, xác nhận output thay đổi, rồi gửi null hoặc hoàn nguyên về baseline để xóa runtime override.

### Bước 8 — Thử nhiều replicas

Chạy hai instance trong lab. Gọi endpoint vào một instance và xác nhận chỉ instance đó đổi nếu runtime override được đặt cục bộ.

### Bước 9 — Kiểm tra correlation và privacy

Nếu tracing được bật, kiểm tra Trace ID/Span ID trong log pattern. Xác nhận fields được redact và không có secret/token hoặc raw payload.

### Bước 10 — Hoàn nguyên và nghiệm thu

Trả mọi logger về level đã chọn cho environment. Xác nhận không còn DEBUG override ngoài ý muốn và log volume ổn định.

### Checklist nghiệm thu

| Điều cần chứng minh | Tiêu chí đạt |
| --- | --- |
| Level semantics | Giải thích được TRACE đến ERROR |
| Logger hierarchy | Hiểu root, package và class logger |
| Profiles | Chọn đúng file/config cho từng environment |
| Baseline | Cấu hình mặc định an toàn, dễ vận hành |
| Override | Xác định nguồn environment/system/command line |
| Logging groups | Biết gom logger và kiểm tra group support |
| Logback | Hiểu khi nào cần native logging configuration |
| Actuator | Đọc/đổi level runtime trong lab, biết hoàn nguyên |
| Security | Endpoint loggers được bảo vệ, dữ liệu nhạy cảm được redact |
| Observability | Phân biệt log level với metrics/tracing sampling |
| Replicas | Biết runtime override có thể chỉ tác động một instance |
| Cleanup | Hoàn nguyên DEBUG/TRACE sau điều tra |

## 18. Những nguyên tắc cần ghi nhớ

1. **Dùng baseline ổn định cho mọi environment.** Root INFO là điểm bắt đầu phổ biến; logger package/class mới được nâng khi có lý do.
2. **Profiles tách cấu hình theo deployment.** Dùng application-local.yml, application-test.yml, application-staging.yml, application-prod.yml hoặc YAML documents với on-profile.
3. **Logger hierarchy giúp bật chi tiết đúng phạm vi.** Root, package và class có thể có mức khác nhau; kiểm tra logger con có explicit level hay không.
4. **Environment variables và command-line arguments có thể override file.** Khi log level bất ngờ, tìm effective property source.
5. **Logging groups giảm công việc cấu hình nhiều package**, nhưng cần xác minh group có trong Spring Boot version đang dùng.
6. **Actuator loggers hỗ trợ điều tra runtime**, nhưng override thường chỉ tồn tại trong process và cần hoàn nguyên.
7. **Bảo vệ management endpoint.** Không mở quyền đổi log level cho người dùng công khai.
8. **DEBUG/TRACE có thể tăng log volume và rủi ro data leakage.** Chỉ bật logger cần thiết, có thời hạn và người chịu trách nhiệm.
9. **Log level không điều khiển metrics hay trace sampling.** Mỗi signal có pipeline riêng; Trace ID/Span ID correlation vẫn có thể xuất hiện ở INFO.
10. **Redact tại nguồn.** Không ghi secrets, tokens, cookies, PII hoặc raw payload rồi trông chờ backend loại bỏ.
11. **Hoàn nguyên sau sự cố.** Ghi nhận thay đổi, kiểm tra mọi replicas và khôi phục mức log chuẩn sau điều tra.

Cấu hình log level theo environment giúp Spring Boot cung cấp đủ thông tin trong lúc phát triển và kiểm thử, đồng thời duy trì log volume có thể kiểm soát trong production. Khi kết hợp profiles, logger hierarchy, externalized configuration và Actuator có bảo vệ, nhóm phát triển có thể điều chỉnh đúng vùng cần quan sát, giữ correlation với traces và metrics, và giảm rủi ro vận hành do logging quá chi tiết.

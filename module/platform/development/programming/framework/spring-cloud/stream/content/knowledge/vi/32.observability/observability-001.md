# Bật Actuator và kiểm tra sức khỏe binder

Spring Boot Actuator cung cấp các endpoint để theo dõi trạng thái ứng dụng đang chạy. Spring Cloud Stream bổ sung health indicator cho binder dưới tên **`binders`**, giúp quan sát trạng thái của các binder được sử dụng trong ứng dụng. Khi bật Actuator và cấu hình health endpoint phù hợp, đội vận hành có thể kiểm tra tổng trạng thái ứng dụng, xem chi tiết binder và phát hiện một số lỗi kết nối hoặc trạng thái xử lý của middleware.

Trong module `SPRING_CLOUD_STREAM`, ứng dụng thường chạy các function `Supplier`, `Function` hoặc `Consumer` thông qua binding kết nối Kafka, RabbitMQ hoặc Pulsar. Health indicator cung cấp thêm tín hiệu vận hành cho lớp binder. Tuy nhiên, health indicator phụ thuộc từng binder; không phải binder nào cũng cung cấp cùng mức thông tin hoặc cùng cách xác định trạng thái. Một endpoint `UP` cũng không chứng minh mọi message đều được giao nhận đúng, không có backlog hoặc mọi nghiệp vụ đang thành công.

## 1. Actuator và binder health indicator

Actuator là phần quản trị của Spring Boot. Endpoint `health` tổng hợp trạng thái từ các `HealthIndicator` và `HealthContributor` đang được đăng ký trong ApplicationContext. Spring Cloud Stream đăng ký health indicator tổng hợp cho binder với tên `binders`.

```text
HTTP request
    |
    v
/actuator/health
    |
    v
Spring Boot HealthEndpoint
    |
    +---- diskSpace / db / custom indicators
    |
    +---- binders
             |
             +---- Kafka binder (nếu có health indicator)
             +---- Rabbit binder (nếu có health indicator)
             +---- Pulsar binder (nếu có health indicator)
    |
    v
Overall application status: UP / DOWN / OUT_OF_SERVICE / UNKNOWN
```

Binder health indicator giúp trả lời câu hỏi ở tầng tích hợp: binder mà ứng dụng sử dụng có đang ở trạng thái khỏe theo cách triển khai của binder hay không? Nó bổ sung cho health indicator mặc định của Spring Boot, ví dụ `diskSpace` hoặc `db`.

Health indicator của binder được đăng ký dưới tên `binders`. Thuộc tính `management.health.binders.enabled` điều khiển việc bật/tắt nhóm này. Nếu không khai báo riêng, Spring Cloud Stream hiện đối chiếu với `management.health.defaults.enabled`, giá trị mặc định thường là `true`. Nên khai báo rõ trong cấu hình ứng dụng để người vận hành không phải dựa vào mặc định của release train.

## 2. Thêm dependency Actuator

Actuator cần được đưa vào ứng dụng bằng dependency `spring-boot-starter-actuator`. Nếu ứng dụng chưa có web server, cần thêm web dependency phù hợp để expose endpoint qua HTTP. Ứng dụng MVC thường dùng `spring-boot-starter-web`; ứng dụng reactive có thể dùng `spring-boot-starter-webflux`.

### Maven

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <!-- Chỉ thêm nếu ứng dụng chưa có web starter -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

### Gradle Kotlin DSL

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // Chỉ thêm nếu ứng dụng chưa có web starter
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

### Gradle Groovy DSL

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Chỉ thêm nếu ứng dụng chưa có web starter
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Không cần khai báo version riêng khi Spring Boot parent hoặc dependency management/BOM đang quản lý phiên bản. Hãy giữ Spring Boot, Spring Cloud release train và Spring Cloud Stream binder ở các phiên bản tương thích.

Nếu ứng dụng đã dùng web starter để cung cấp API nghiệp vụ, chỉ cần thêm Actuator. Nếu chỉ muốn expose endpoint qua JMX, có thể không cần web server; bài học này tập trung vào health endpoint HTTP để có thể dùng với monitoring và container probe.

## 3. Bật health indicator của binder

Spring Cloud Stream cung cấp thuộc tính:

```text
management.health.binders.enabled
```

Đặt `true` để bật health indicator cho binder. Đây là thuộc tính của Spring Boot health infrastructure, không nằm dưới `spring.cloud.stream`.

```yaml
management:
  health:
    binders:
      enabled: true
```

Nếu muốn tắt nhóm binder health indicator trên toàn ứng dụng:

```yaml
management:
  health:
    binders:
      enabled: false
```

Khi tắt indicator mặc định, các `HealthIndicator` tùy chỉnh do ứng dụng cung cấp vẫn có thể được Spring Boot phát hiện và đưa vào health endpoint. Chỉ tắt binder health khi đã có lý do vận hành rõ ràng hoặc có cơ chế kiểm tra thay thế.

Một số binder implementation không cung cấp health indicator. Trong trường hợp đó, việc bật `management.health.binders.enabled` không tự tạo ra phép kiểm tra kết nối giống nhau cho mọi middleware. Cần xem tài liệu của binder đang dùng và xác minh trạng thái thực tế bằng integration/monitoring phù hợp.

## 4. Expose endpoint `/actuator/health`

Spring Boot mặc định expose endpoint `health` qua HTTP. Các endpoint khác như `info`, `metrics`, `env` hoặc `beans` không nên được expose tùy tiện vì có thể tiết lộ thông tin nội bộ.

Cấu hình tối thiểu:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
```

Nếu muốn expose thêm `info`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Endpoint mặc định là:

```text
GET http://localhost:8080/actuator/health
```

Nếu ứng dụng thay đổi base path bằng `management.endpoints.web.base-path`, đường dẫn thực tế cũng thay đổi. Nếu dùng management port riêng, endpoint sẽ nằm trên port đó thay vì port HTTP nghiệp vụ.

## 5. Hiển thị chi tiết binder

Khi gọi `/actuator/health`, mặc định client thường chỉ nhận trạng thái tổng thể như `UP` hoặc `DOWN`. Để xem các component và chi tiết binder, cấu hình `show-details` và `show-components`.

Trong môi trường phát triển có thể dùng:

```yaml
management:
  endpoint:
    health:
      show-details: always
      show-components: always
```

Trong production nên giới hạn chi tiết cho người đã xác thực:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: ACTUATOR_ADMIN
```

Các giá trị thường dùng là `never`, `when-authorized` và `always`. Mặc định Spring Boot không hiển thị chi tiết. `always` làm thông tin chi tiết xuất hiện cho mọi người truy cập được endpoint; chỉ dùng trong môi trường nội bộ được bảo vệ hoặc trong local development.

Spring Cloud Stream mô tả việc đặt `management.endpoint.health.show-details` thành `ALWAYS` để xem thông tin binder. Với Spring Boot mới, `show-components` cũng kiểm soát việc hiển thị cấu trúc component; cấu hình cả hai giúp kết quả dễ quan sát. Kiểm tra property metadata theo phiên bản Spring Boot của dự án nếu dùng release cũ.

## 6. Cấu hình tổng hợp hoàn chỉnh

Ví dụ ứng dụng Spring Cloud Stream có một binder và muốn expose health endpoint:

```yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
  health:
    binders:
      enabled: true
```

Trong cấu hình này:

- `server.port` là port web server của ứng dụng.
- `exposure.include` chỉ expose `health` và `info` qua HTTP.
- `show-details` quyết định người được phép có thể xem thông tin chi tiết hay không.
- `show-components` quyết định cấu trúc các component có xuất hiện hay không.
- `management.health.binders.enabled` bật nhóm health indicator của binder.

Đây là cấu hình chung. Nếu ứng dụng có nhiều binder hoặc dùng Kafka Streams, kết quả chi tiết còn phụ thuộc binder implementation và cấu hình riêng của binder.

## 7. Kiểm tra health endpoint bằng HTTP

Sau khi chạy ứng dụng, gọi health endpoint:

```bash
curl -i http://localhost:8080/actuator/health
```

Khi có quyền xem chi tiết, kết quả có thể có cấu trúc tương tự:

```json
{
  "status": "UP",
  "components": {
    "binders": {
      "status": "UP",
      "components": {
        "kafka": {
          "status": "UP"
        }
      }
    },
    "diskSpace": {
      "status": "UP"
    }
  }
}
```

Tên binder con và các trường `details` phụ thuộc binder, phiên bản và cấu hình. Ví dụ trên chỉ minh họa cấu trúc tổng hợp; không phải mọi binder đều trả về đúng các trường này.

Nếu muốn kiểm tra component binder trực tiếp, có thể gọi:

```bash
curl -i http://localhost:8080/actuator/health/binders
```

Với một contributor lồng nhau, Spring Boot Health endpoint cũng hỗ trợ truy vấn component con theo đường dẫn, nếu contributor đó được expose và tên component phù hợp.

## 8. Hiểu ý nghĩa trạng thái health

Các trạng thái phổ biến:

| Trạng thái | Ý nghĩa tổng quát | Cách xử lý |
|---|---|---|
| `UP` | Indicator báo thành phần khỏe theo tiêu chí của nó | Tiếp tục theo dõi metrics và message flow |
| `DOWN` | Indicator phát hiện thành phần không khỏe | Kiểm tra broker, kết nối, binding, thread hoặc lỗi cấu hình |
| `OUT_OF_SERVICE` | Thành phần được đánh dấu không phục vụ | Kiểm tra maintenance, readiness hoặc trạng thái vận hành |
| `UNKNOWN` | Không xác định được trạng thái theo indicator/aggregator | Kiểm tra implementation, cấu hình và log |

Health endpoint tổng hợp status của nhiều indicator. Nếu binder báo `DOWN`, overall health có thể thành `DOWN` theo status aggregator. HTTP status mặc định thường là `503` cho `DOWN` và `OUT_OF_SERVICE`, trong khi `UP` trả `200`.

Không nên chỉ nhìn HTTP `200` rồi kết luận toàn bộ event pipeline hoạt động chính xác. Health indicator chỉ kiểm tra điều mà implementation của nó được thiết kế để kiểm tra; nó không chứng minh consumer đã xử lý hết backlog, không mất message hoặc không có lỗi nghiệp vụ.

## 9. Health indicator của binder là binder-specific

Spring Cloud Stream đăng ký nhóm `binders`, nhưng mỗi binder có thể triển khai health indicator khác nhau. Một số binder cung cấp kiểm tra trạng thái kết nối hoặc tài nguyên đã đăng ký; một số binder không cung cấp health indicator riêng.

| Binder | Cách đọc kết quả |
|---|---|
| Kafka Binder | Tùy implementation và các destination đã đăng ký; không suy ra mọi consumer group/partition đều ổn chỉ từ `UP` |
| Kafka Streams Binder | Có health indicator theo dõi trạng thái các stream thread và task |
| RabbitMQ Binder | Kiểm tra theo khả năng health indicator của phiên bản binder; có thể bổ sung Rabbit connection health riêng |
| Pulsar Binder | Kiểm tra theo khả năng health indicator của phiên bản binder; cần theo dõi thêm broker, topic, subscription và backlog |

Không giả định các binder có cùng tập trường `details`, cùng timeout hoặc cùng semantics `UP/DOWN`. Khi triển khai nhiều middleware, hãy kiểm tra tài liệu đúng phiên bản binder và bổ sung integration monitoring cho các tín hiệu quan trọng chưa được health indicator bao phủ.

## 10. Phân biệt binder health với health indicator của broker

Spring Boot có thể tự cấu hình health indicator cho một số công nghệ khi dependency tương ứng có mặt. Ví dụ RabbitMQ có thể có indicator tên `rabbit` thông qua Spring AMQP connection factory. Spring Cloud Stream có nhóm `binders` riêng.

Hai indicator không đồng nghĩa:

| Indicator | Phạm vi kiểm tra |
|---|---|
| `binders` | Trạng thái mà binder implementation báo cáo cho các binder trong Spring Cloud Stream |
| `rabbit` | Trạng thái RabbitMQ connection theo Spring Boot/Spring AMQP health indicator khi có điều kiện phù hợp |
| `db` | Khả năng lấy kết nối database theo DataSource health indicator |
| `diskSpace` | Dung lượng đĩa theo ngưỡng cấu hình |

Ví dụ `rabbit: UP` không chứng minh binding `orders-in-0` có queue đúng, routing key đúng, consumer đang nhận message hay DLQ đã được cấu hình. Ngược lại, `binders: UP` cũng không thay thế kiểm tra backlog và trạng thái queue trên RabbitMQ Management API.

## 11. Kiểm tra Kafka Streams Binder

Kafka Streams Binder có health indicator chuyên biệt để kiểm tra trạng thái các stream thread. Khi hiển thị chi tiết, kết quả có thể bao gồm:

- Tên stream thread.
- Thread state.
- Active task và partition đang được gán.
- Standby task và partition tương ứng.
- Thông tin được nhóm theo application ID nếu có nhiều Kafka Streams processor.

Các thread state thường gặp gồm:

| Thread state | Ý nghĩa |
|---|---|
| `CREATED` | Thread đã được tạo nhưng chưa chạy bình thường |
| `RUNNING` | Thread đang xử lý |
| `PARTITIONS_REVOKED` | Thread đang thu hồi partition trong quá trình rebalance |
| `PARTITIONS_ASSIGNED` | Thread đang nhận partition mới |
| `PENDING_SHUTDOWN` | Thread đang chờ dừng |
| `DEAD` | Thread đã dừng hoặc không còn hoạt động |

Theo tài liệu Kafka Streams Binder, health indicator báo `UP` khi tất cả Kafka Streams thread đã đăng ký ở trạng thái `RUNNING`. Trong lúc rebalance, thread có thể tạm thời ở trạng thái khác; hãy đọc chi tiết và log trước khi kết luận lỗi kéo dài.

Ví dụ cấu hình:

```yaml
management:
  health:
    binders:
      enabled: true
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
```

Nếu có nhiều Kafka Streams processor, chi tiết có thể được nhóm theo `applicationId`. Điều này giúp phân biệt topology nào có thread bị lỗi.

## 12. Lưu ý khi nhiều binder cùng nằm trên classpath

Một ứng dụng có thể khai báo nhiều binder dependency trên classpath nhưng chỉ sử dụng một số binder. Một số implementation vẫn đăng ký health indicator dù binder đó không được dùng. Nếu health indicator yêu cầu binder có destination đã đăng ký nhưng binder không có binding nào, nó có thể báo `DOWN` và làm overall health thành `DOWN`.

Ví dụ: ứng dụng có cả Kafka Binder và Kafka Streams Binder trên classpath nhưng chỉ khai báo binding Kafka Streams. Kafka Binder thường có thể báo `DOWN` do không có destination nào được đăng ký cho binder đó. Đây là tình huống cấu hình classpath không phản ánh binder thực sự được sử dụng.

Thứ tự xử lý:

1. Xác minh binder nào thực sự được dùng trong ứng dụng.
2. Gỡ dependency binder không sử dụng nếu không có lý do giữ lại.
3. Nếu cần giữ binder trên classpath cho một mục đích khác, xem cách disable health indicator trong environment riêng của binder.
4. Kiểm tra lại `/actuator/health` sau khi thay đổi.

Không tắt toàn bộ `management.health.binders.enabled` chỉ để che một binder không được dùng nếu các binder khác vẫn cần được giám sát.

## 13. Tắt health indicator cho một binder trong cấu hình multi-binder

Khi cấu hình nhiều binder qua `spring.cloud.stream.binders`, mỗi binder có thể có environment riêng. Spring Cloud Stream cho phép đặt `management.health.binders.enabled=false` trong environment của binder cụ thể để loại bỏ health indicator của binder đó.

Ví dụ minh họa:

```yaml
spring:
  cloud:
    stream:
      binders:
        unusedKafka:
          type: kafka
          environment:
            management:
              health:
                binders:
                  enabled: false
```

Chỉ dùng cách này khi binder `unusedKafka` không cần được giám sát qua binder health indicator. Nếu binder đang phục vụ binding production, việc tắt health indicator sẽ làm giảm khả năng quan sát. Hãy xác nhận tên binder và environment được áp dụng đúng trong cấu hình multi-binder thực tế.

Nếu binder không được sử dụng ở bất kỳ binding nào, gỡ dependency thường là cách đơn giản hơn. Nếu binder được dùng nhưng implementation không cung cấp health indicator, cần bổ sung giám sát phù hợp thay vì giả định property này tạo ra health check mới.

## 14. Liveness và readiness trong môi trường triển khai

Spring Boot có thể expose hai nhóm health probe:

- **Liveness:** ứng dụng còn sống và không cần bị restart để phục hồi hay không.
- **Readiness:** instance đã sẵn sàng nhận traffic hoặc công việc mới hay chưa.

Trong Kubernetes, các endpoint thường dùng là:

```text
/actuator/health/liveness
/actuator/health/readiness
```

Spring Boot tự bật probe groups khi phát hiện môi trường Kubernetes trong các cấu hình phù hợp. Có thể bật rõ ràng ở môi trường khác bằng:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
```

Liveness không nên phụ thuộc vào health check của broker bên ngoài. Nếu Kafka/RabbitMQ/Pulsar tạm thời mất kết nối mà liveness chuyển `DOWN`, Kubernetes có thể restart đồng loạt tất cả instance, tạo vòng lặp restart và làm tình hình nghiêm trọng hơn.

Readiness có thể bao gồm binder health nếu ứng dụng không thể xử lý công việc khi broker không sẵn sàng. Tuy nhiên, đây là quyết định vận hành: nếu broker dùng chung bị lỗi, tất cả instance có thể trở thành unready cùng lúc. Nếu ứng dụng có retry, buffer hoặc fallback, việc đưa binder vào readiness có thể không phù hợp.

## 15. Đưa binder health vào readiness group

Spring Boot không tự động đưa mọi external health indicator vào readiness group. Nếu muốn readiness phản ánh cả binder health, có thể cấu hình:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,binders
```

Sau đó kiểm tra:

```bash
curl -i http://localhost:8080/actuator/health/readiness
```

Chỉ thêm `binders` khi broker là dependency bắt buộc để instance nhận việc. Với stream processor, hãy đánh giá semantics cụ thể: instance có thể cần broker để consume/publish, nhưng một broker outage dùng chung có thể làm toàn bộ replica unready. Điều đó có thể đúng hoặc có thể làm giảm khả năng phục hồi của hệ thống tùy kiến trúc.

Không thêm `binders` vào liveness group. Liveness nên phản ánh lỗi nội tại của process mà restart có thể giải quyết, không phải lỗi tạm thời ở hệ thống bên ngoài.

## 16. Quản lý management port

Actuator có thể dùng cùng port với ứng dụng hoặc port riêng:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health,info
```

Khi cấu hình management port riêng, health endpoint nằm ở `http://localhost:8081/actuator/health`. Monitoring agent và Kubernetes probe phải gọi đúng port.

Management port riêng giúp tách luồng quản trị, nhưng health endpoint trên port riêng có thể thành công ngay cả khi web server chính không nhận được kết nối. Nếu dùng probe trên management port, cân nhắc cấu hình health group được expose thêm trên main server port theo khả năng của phiên bản Spring Boot, hoặc thiết kế probe kiểm tra đúng cổng phục vụ ứng dụng.

## 17. Bảo vệ Actuator endpoint

Health endpoint có thể tiết lộ tên broker, binder, application ID, thread, task hoặc thông tin lỗi. Không nên expose mọi Actuator endpoint ra Internet.

Các nguyên tắc:

- Chỉ expose `health` và endpoint thực sự cần thiết.
- Dùng `show-details: when-authorized` trong production.
- Giới hạn truy cập qua mạng nội bộ, firewall, service mesh hoặc Spring Security.
- Nếu có custom `SecurityFilterChain`, tự cấu hình quy tắc bảo vệ Actuator; Spring Boot security auto-configuration có thể lùi lại khi ứng dụng khai báo chain riêng.
- Không đưa credential, token, connection string hoặc payload nghiệp vụ vào health details.
- Nếu dùng `show-details: always`, chỉ bật trong môi trường đã được bảo vệ.

Ví dụ expose tối thiểu:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: ACTUATOR_ADMIN
```

Endpoint `health` thường được expose mặc định qua HTTP, nhưng vẫn cần kiểm tra security policy và đường mạng của môi trường triển khai.

## 18. Kiểm tra bằng curl và diễn giải kết quả

Quy trình kiểm tra cơ bản:

1. Khởi động ứng dụng với Actuator và binder health được bật.
2. Xác nhận port và base path của management endpoint.
3. Gọi `/actuator/health`.
4. Nếu có quyền, xem component `binders`.
5. Gọi `/actuator/health/binders` để xem nhóm binder.
6. Đối chiếu tên binder và trạng thái với log khởi động.
7. Nếu `DOWN`, kiểm tra indicator con và lỗi gốc trong log.
8. Khôi phục broker hoặc cấu hình rồi kiểm tra lại.

Ví dụ:

```bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/health/binders
```

Trên Windows PowerShell có thể dùng `curl.exe` để gọi chương trình curl thực:

```powershell
curl.exe -i http://localhost:8080/actuator/health
curl.exe -i http://localhost:8080/actuator/health/binders
```

Nếu trả `404`, kiểm tra Actuator dependency, web application, exposure include, base path và management port. Nếu trả `401` hoặc `403`, kiểm tra authentication/authorization. Nếu trả `503`, xem JSON health và log để tìm contributor báo `DOWN`.

## 19. Health indicator không thay thế metrics và message-flow monitoring

Health endpoint thường là ảnh chụp trạng thái tại thời điểm được gọi. Để vận hành Spring Cloud Stream, cần quan sát thêm metrics và trạng thái luồng message.

| Tín hiệu | Câu hỏi cần trả lời |
|---|---|
| Binder health | Binder có báo trạng thái khỏe không? |
| Consumer lag/backlog | Message đang chờ xử lý bao nhiêu? |
| Processing rate | Consumer xử lý được bao nhiêu message/giây? |
| Error rate | Bao nhiêu message hoặc lần xử lý bị lỗi? |
| Retry/DLQ | Có bao nhiêu message phải retry hoặc đi vào dead-letter? |
| Partition assignment | Consumer có nhận đủ partition cần thiết không? |
| Connection/reconnect | Binder có liên tục mất và tạo lại kết nối không? |
| End-to-end latency | Từ publish đến xử lý hoàn tất mất bao lâu? |

Actuator `metrics` có thể expose các Micrometer metrics đã được ứng dụng và binder ghi nhận. Nếu dùng Prometheus, thêm registry phù hợp và expose endpoint `prometheus` sau khi đã bảo vệ. Không giả định mọi binder cung cấp cùng metric names hoặc tags.

## 20. Kiểm thử binder health khi broker gặp sự cố

Một health indicator chỉ hữu ích khi đã biết nó phản ứng thế nào trong điều kiện bình thường và lỗi. Nên kiểm tra trên môi trường integration/staging:

| Kịch bản | Thao tác | Điều cần xác minh |
|---|---|---|
| Broker bình thường | Khởi động broker và ứng dụng | Binder health phản ánh trạng thái bình thường theo implementation |
| Broker không truy cập được khi startup | Dừng broker trước khi ứng dụng khởi động | Xác minh startup behavior, retry và health result |
| Mất kết nối khi runtime | Chặn network hoặc dừng broker | Quan sát health, log reconnect và thời gian phục hồi |
| Khôi phục broker | Khởi động lại broker | Xác minh binder phục hồi và health trở lại trạng thái khỏe |
| Binder không có indicator | Dùng binder implementation không cung cấp health check | Không kết luận `UP` nghĩa là broker đã được kiểm tra |
| Binder thừa trên classpath | Thêm binder dependency không được dùng | Kiểm tra có contributor báo `DOWN` do không có destination |
| Multi-binder | Chạy hai binder với cấu hình riêng | Xác minh từng binder được hiển thị và environment áp dụng đúng |
| Chi tiết bị ẩn | Dùng `show-details: never` | Endpoint chỉ trả trạng thái tổng thể |
| Không đủ quyền | Gọi endpoint bằng user không có role | Chi tiết được ẩn hoặc request bị từ chối theo security policy |
| Readiness khi broker down | Đưa `binders` vào readiness rồi dừng broker | Đánh giá có nên loại instance khỏi traffic hay không |

Không chỉ kiểm tra trường hợp broker bị dừng. Cần kiểm tra network timeout, credential hết hạn, DNS lỗi, TLS certificate, thiếu ACL và binder không đăng ký được destination để hiểu giới hạn của health indicator.

## 21. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `/actuator/health` trả `404` | Thiếu Actuator/web dependency, sai port/base path hoặc endpoint chưa expose | Kiểm tra dependency và management configuration |
| Chỉ thấy `{"status":"UP"}` | Chi tiết component bị ẩn | Cấu hình `show-details` và `show-components` phù hợp |
| Không thấy `binders` | Binder health bị disable hoặc binder không có indicator | Kiểm tra `management.health.binders.enabled` và implementation |
| `binders` báo `DOWN` dù binder đang chạy | Binder thừa trên classpath hoặc indicator không tìm thấy destination | Xác định binder thực sự dùng, gỡ dependency thừa hoặc cấu hình environment riêng |
| Kafka Streams health `DOWN` | Có stream thread không ở `RUNNING` | Xem thread state, task, rebalance và log |
| `rabbit` UP nhưng binding lỗi | Rabbit connection indicator không xác minh toàn bộ binding | Kiểm tra `binders`, queue, exchange, routing và consumer |
| Health vẫn UP nhưng backlog tăng | Indicator không đo throughput/backlog | Theo dõi consumer lag và processing metrics |
| Health endpoint lộ chi tiết | `show-details: always` hoặc security chưa giới hạn | Dùng `when-authorized`, firewall và role |
| Kubernetes restart liên tục khi broker lỗi | Liveness phụ thuộc binder health | Không đưa external binder health vào liveness |
| Tất cả pod unready khi broker dùng chung lỗi | Readiness group chứa `binders` | Đánh giá lại dependency và readiness policy |
| Health check timeout | Indicator hoặc broker request phản hồi chậm | Kiểm tra timeout, mạng và slow-indicator logs |

## 22. Quy trình triển khai production

1. Thêm `spring-boot-starter-actuator` và web dependency nếu cần expose HTTP.
2. Bật `management.health.binders.enabled: true`.
3. Expose endpoint tối thiểu, thường là `health` và có thể `info`.
4. Cấu hình `show-details`/`show-components` theo quyền truy cập.
5. Xác nhận binder implementation đang dùng có health indicator hay không.
6. Kiểm tra classpath để loại bỏ binder dependency không sử dụng.
7. Với multi-binder, kiểm tra environment và health contributor của từng binder.
8. Gọi `/actuator/health` và `/actuator/health/binders` trong staging.
9. Thử nghiệm broker outage, network interruption, credential/ACL failure và recovery.
10. Quyết định có đưa binder health vào readiness hay không; không đưa external dependency vào liveness.
11. Bảo vệ management port và endpoint bằng network policy/Spring Security.
12. Kết hợp health với metrics, consumer lag, retry/DLQ và end-to-end monitoring.

## 23. Tự kiểm tra

- [ ] Thêm được `spring-boot-starter-actuator` và web dependency phù hợp.
- [ ] Giải thích được vai trò của Actuator `health` endpoint.
- [ ] Bật được `management.health.binders.enabled`.
- [ ] Expose và gọi được `/actuator/health`.
- [ ] Cấu hình `show-details` và `show-components` phù hợp với môi trường.
- [ ] Giải thích được vì sao binder health indicator phụ thuộc implementation.
- [ ] Phân biệt `binders` với indicator riêng của RabbitMQ hoặc database.
- [ ] Nhận diện được trường hợp binder dependency thừa làm health báo `DOWN`.
- [ ] Đọc được health details của Kafka Streams thread/task.
- [ ] Phân biệt liveness với readiness và quyết định khi nào đưa binder vào readiness.
- [ ] Bảo vệ Actuator endpoint và management port.
- [ ] Kết hợp health endpoint với metrics, lag, retry và DLQ monitoring.
- [ ] Thiết kế được test khi broker mất kết nối và khi broker phục hồi.

## Kết luận

Để kiểm tra sức khỏe binder của Spring Cloud Stream, thêm Actuator, bật binder health indicator bằng `management.health.binders.enabled` và truy cập `/actuator/health`. Nhóm indicator được đăng ký dưới tên `binders`; muốn xem thông tin chi tiết cần cấu hình `show-details` và `show-components` cùng security phù hợp. Kết quả phụ thuộc binder implementation, vì vậy không phải Kafka, RabbitMQ và Pulsar đều cung cấp cùng một phép kiểm tra. Đặc biệt, cần kiểm tra binder thừa trên classpath, trạng thái Kafka Streams thread, readiness/liveness và sự khác biệt giữa binder health với broker connection health. Kết hợp Actuator với metrics, backlog, retry/DLQ và kiểm thử outage mới tạo được bức tranh vận hành đầy đủ.

## Tài liệu tham khảo

- Spring Cloud Stream 5.0.4 — Health Indicator: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/health-indicator.html
- Spring Cloud Stream 4.1.6 — Kafka Streams Binder Health Indicator: https://docs.spring.io/spring-cloud-stream/reference/4.1/kafka/kafka-streams-binder/health-indicator.html
- Spring Boot — Actuator Endpoints and Health Information: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot — Kubernetes Probes: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes

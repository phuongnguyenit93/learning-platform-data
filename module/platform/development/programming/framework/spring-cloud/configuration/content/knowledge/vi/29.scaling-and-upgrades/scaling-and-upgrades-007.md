# Chuyển cơ chế bootstrap cũ và hướng dẫn Actuator lỗi thời

Các ứng dụng Spring Cloud Config đời cũ thường dùng bootstrap context, file `bootstrap.yml` và dependency `spring-cloud-starter-bootstrap` để lấy cấu hình từ xa trước khi tạo application context chính. Từ Spring Boot 2.4, Config Data API trở thành cơ chế chuẩn để nạp cấu hình ngoài thông qua `spring.config.import`. Khi nâng cấp, cần chuyển đúng thứ tự nạp cấu hình, profile, retry và endpoint vận hành; nếu chỉ đổi file mà không kiểm tra property source, ứng dụng có thể nhận giá trị khác trước hoặc không còn refresh được.

Actuator cũng đã thay đổi đáng kể qua các thế hệ Spring Boot. Các hướng dẫn cũ dùng `/refresh`, `/bus/refresh`, `management.context-path`, `management.security.enabled` hoặc `endpoints.*` có thể không còn đúng với ứng dụng hiện đại. Cần xác định endpoint ID, base path, exposure và security theo phiên bản đang chạy, sau đó kiểm tra lại webhook, refresh từng instance và refresh toàn cụm.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích bootstrap context và lý do Spring Boot chuyển sang Config Data API.
- Nhận diện `bootstrap.yml`, `spring-cloud-starter-bootstrap` và các cờ bật legacy processing.
- Chuyển Config Client sang `spring.config.import=configserver:`.
- Chọn import bắt buộc hay `optional:` và cấu hình retry phù hợp.
- Kiểm tra lại application name, profile, label và thứ tự ưu tiên property source.
- Nhận biết custom bootstrap code hoặc integration chưa thể chuyển ngay.
- Chuyển các thuộc tính Actuator cũ sang namespace hiện đại.
- Phân biệt `/actuator/refresh`, `/actuator/busrefresh` và Config Server `/monitor`.
- Bảo vệ endpoint quản trị bằng authentication, authorization và network policy.
- Triển khai migration theo giai đoạn, kiểm chứng và rollback an toàn.

## 2. Bootstrap context cũ hoạt động thế nào?

Trong mô hình bootstrap truyền thống của Spring Cloud, ứng dụng có một bootstrap context được tạo trước application context chính. Bootstrap context đọc `bootstrap.yml`, thiết lập các nguồn cấu hình cần thiết và có thể gọi Config Server để lấy property source từ xa. Application context chính sau đó được tạo với bootstrap context làm parent theo cơ chế của Spring Cloud.

Một cấu hình cũ thường có dạng:

```yaml
# bootstrap.yml (legacy)
spring:
  application:
    name: orders
  cloud:
    config:
      uri: https://config.internal.example
      label: main
      fail-fast: true
```

Dependency `spring-cloud-starter-bootstrap` hoặc thuộc tính `spring.cloud.bootstrap.enabled=true` có thể bật cơ chế bootstrap trong các release hỗ trợ. Một số ứng dụng nâng cấp qua Spring Boot 2.4 còn dùng `spring.config.use-legacy-processing=true` như cầu nối tương thích với cách xử lý Config File cũ.

Bootstrap context từng giải quyết một nhu cầu quan trọng: lấy thông tin từ xa trước khi application context chính hoàn tất. Tuy nhiên, nó tạo ra một lifecycle riêng, quy tắc override đặc thù và nhiều điểm dễ gây nhầm lẫn khi kết hợp với các nguồn cấu hình khác.

## 3. Config Data API thay đổi điều gì?

Spring Boot 2.4 giới thiệu Config Data API để nạp file và nguồn cấu hình bên ngoài theo một quy trình thống nhất. Spring Cloud Config tích hợp qua import location có scheme `configserver:`.

Thay vì một bootstrap context riêng, ứng dụng khai báo rõ nguồn cấu hình cần import trong cấu hình cục bộ:

```yaml
# application.yml (Config Data API)
spring:
  application:
    name: orders
  config:
    import: "configserver:https://config.internal.example"
```

Khi xử lý Config Data, Spring Boot nhận diện `configserver:` và dùng Config Data loader của Spring Cloud Config để lấy cấu hình từ xa. Application name, active profiles và label được gửi theo cấu hình của Config Client.

Điểm khác biệt chính:

| Nội dung | Bootstrap truyền thống | Config Data API |
| --- | --- | --- |
| Điểm kích hoạt | Bootstrap context và `bootstrap.yml` | `spring.config.import` |
| Dependency bật cơ chế | Có thể cần `spring-cloud-starter-bootstrap` | Config Client starter tương thích với release train |
| Thời điểm nạp | Trong bootstrap phase trước application context | Trong Config Data processing trước khi tạo bean ứng dụng |
| Khai báo nguồn từ xa | `spring.cloud.config.uri` trong bootstrap config | Import location `configserver:` |
| Optional source | Cơ chế legacy/flag tùy release | Tiền tố `optional:` rõ ràng trong import |
| Quy tắc ưu tiên | Bootstrap parent context và các cờ override | Thứ tự Config Data import cùng quy tắc property source của Spring Boot/Config Server |
| Custom integration | Có thể dùng `BootstrapConfiguration` và `PropertySourceLocator` | Cần hỗ trợ Config Data hoặc một cơ chế tích hợp được tài liệu hóa |

Config Data API không chỉ đổi tên file. Nó thay đổi thời điểm và cơ chế nạp nguồn, vì vậy cần kiểm thử giá trị hiệu lực sau migration.

## 4. Chọn phiên bản tương thích trước khi chuyển

Trước khi sửa code, xác định chính xác:

- Spring Boot version đang chạy.
- Spring Cloud release train đang dùng.
- Spring Cloud Config Client/Server version.
- Các starter bổ sung như Eureka, Consul, Vault, Bus và Actuator.
- JDK version và các thư viện custom có tích hợp bootstrap.

Config Data API được hỗ trợ từ Spring Boot 2.4 và các release Spring Cloud tương thích. Spring Boot 3 yêu cầu Spring Cloud release train tương thích với dòng Boot 3 và các dependency Jakarta tương ứng. Không nâng riêng `spring-cloud-config-client` lên một version bất kỳ trong khi BOM của dự án đang quản lý một release train khác.

Quy trình chọn version:

1. Chọn Spring Boot version mục tiêu.
2. Tra compatibility matrix chính thức để chọn Spring Cloud release train tương ứng.
3. Dùng Spring Cloud BOM để quản lý các module Cloud cùng release train.
4. Kiểm tra compatibility của starter discovery, Bus, Vault và các integration khác.
5. Chạy compile và integration tests trên JDK mục tiêu.

Không coi việc ứng dụng compile thành công là bằng chứng bootstrap migration đã đúng. Một số khác biệt chỉ xuất hiện khi Config Data import chạy hoặc khi profile được kích hoạt.

## 5. Chuyển từ `bootstrap.yml` sang `application.yml`

Giả sử ứng dụng cũ dùng:

```yaml
# bootstrap.yml
spring:
  application:
    name: orders
  cloud:
    config:
      uri: https://config.internal.example
      label: release-2026.11
      fail-fast: true
```

Với Config Data API, chuyển thành:

```yaml
# application.yml
spring:
  application:
    name: orders
  config:
    import: "configserver:https://config.internal.example"
  cloud:
    config:
      label: release-2026.11
```

Trong ví dụ này, import là bắt buộc. Nếu Config Server không truy cập được hoặc không thể nạp nguồn cấu hình cần thiết, quá trình khởi động sẽ báo lỗi thay vì âm thầm chạy thiếu cấu hình.

Nếu URL được cấp qua môi trường triển khai, có thể truyền import location qua environment variable:

```text
SPRING_CONFIG_IMPORT=configserver:https://config.internal.example
```

Hoặc dùng placeholder được cung cấp từ nguồn cục bộ có sẵn trước Config Data processing. Không đặt duy nhất URL Config Server trong chính Config Server repository; client cần biết địa chỉ server trước khi có thể gọi server đó.

Sau khi chuyển, kiểm tra các thuộc tính legacy còn được dùng ở đâu. Không xóa `bootstrap.yml` ngay nếu custom integration hoặc ứng dụng khác vẫn cần nó; hãy xác nhận từng consumer trước.

## 6. Import bắt buộc và optional

Config Data API biểu diễn rõ ràng hành vi khi nguồn từ xa không khả dụng.

**Bắt buộc:**

```yaml
spring:
  config:
    import: "configserver:https://config.internal.example"
```

Ứng dụng không thể tiếp tục khởi động nếu nguồn cấu hình bắt buộc không nạp được. Dùng khi thiếu cấu hình từ xa có thể làm ứng dụng chạy sai hoặc không an toàn.

**Optional:**

```yaml
spring:
  config:
    import: "optional:configserver:https://config.internal.example"
```

Ứng dụng có thể tiếp tục khi Config Server không khả dụng. Chỉ dùng khi cấu hình cục bộ có fallback hợp lệ và đã được kiểm thử. Optional không có nghĩa cấu hình từ xa sẽ tự xuất hiện sau đó; cần cơ chế refresh hoặc restart phù hợp.

Không chuyển mọi ứng dụng sang `optional:` chỉ để pipeline không bị đỏ khi Config Server gặp sự cố. Quyết định này ảnh hưởng trực tiếp đến hành vi fail-fast và tính đúng đắn của cấu hình.

## 7. Cấu hình retry trong Config Data API

Trong bootstrap legacy, một số ứng dụng cấu hình retry bằng các thuộc tính `spring.cloud.config.retry.*` và `spring.cloud.config.fail-fast`. Với Config Data API, các tham số retry có thể được gắn trực tiếp vào import URI để Config Data loader biết cách thử lại ngay khi đang xử lý nguồn.

Ví dụ minh họa:

```yaml
spring:
  config:
    import: "configserver:https://config.internal.example?fail-fast=true&max-attempts=6&initial-interval=1000&multiplier=1.2&max-interval=5000"
```

Các tham số cần được kiểm tra theo phiên bản Spring Cloud Config đang dùng. Cơ chế retry có thể yêu cầu dependency Spring Retry và AOP theo hướng dẫn của release tương ứng. Đặt retry có giới hạn, khoảng chờ tăng dần và timeout tổng thể hợp lý.

Không retry vô hạn các lỗi không thể tự hồi phục như HTTP 401/403, hostname mismatch, certificate không tin cậy hoặc application/profile/label sai. Retry chỉ hữu ích với lỗi tạm thời như timeout hoặc connection reset.

## 8. Chuyển application name, profile và label

Config Server xác định cấu hình dựa trên application, profile và label. Các giá trị này phải được thiết lập trước khi Config Data import gọi server.

Ví dụ:

```yaml
spring:
  application:
    name: orders
  profiles:
    active: dev
  config:
    import: "configserver:https://config.internal.example"
  cloud:
    config:
      label: release-2026.11
```

Các điểm cần kiểm tra:

- `spring.application.name` khớp tên file/context trong Config repository.
- Active profile được gửi đúng và không bị environment variable của máy/CI ghi đè ngoài ý muốn.
- Label trỏ đến branch, tag hoặc commit mà Config Server có thể đọc.
- Nếu dùng profile group hoặc profile được kích hoạt từ cấu hình từ xa, kiểm tra luồng Config Data và profile activation theo phiên bản Spring Boot.
- Không giả định `bootstrap.yml` và `application.yml` có cùng thứ tự ưu tiên.

Profile-specific document trong Spring Boot hiện đại có thể dùng `spring.config.activate.on-profile` để điều kiện hóa tài liệu cấu hình. Không dùng cú pháp profile cũ trong các release đã loại bỏ hoặc thay đổi nó.

## 9. Kiểm tra lại thứ tự ưu tiên property source

Đây là một trong các rủi ro lớn nhất khi chuyển bootstrap sang Config Data.

Bootstrap truyền thống có parent context và các thuộc tính điều khiển override remote property source. Config Data API có quy tắc import riêng: nguồn được import được đưa vào thứ tự Config Data tại vị trí khai báo import, và các property source khác có thể override theo quy tắc của Spring Boot cùng cấu hình Config Server.

Ví dụ local config:

```yaml
spring:
  config:
    import: "configserver:https://config.internal.example"

payments:
  retry-count: 2
```

Remote config:

```yaml
payments:
  retry-count: 5
```

Không suy luận giá trị cuối cùng chỉ từ hai file trên. Cần kiểm tra thứ tự import, profile, các nguồn khác như environment variables và các cờ override remote được Config Server công bố.

Các thuộc tính như `spring.cloud.config.allowOverride`, `spring.cloud.config.overrideNone` và `spring.cloud.config.overrideSystemProperties` thuộc cơ chế điều khiển override của remote property source. Chúng cần được đặt ở phía remote theo hướng dẫn Spring Cloud Config; không đặt nhầm ở local client rồi kỳ vọng thay đổi quyền override của server.

Trước migration, ghi lại giá trị hiệu lực của các khóa quan trọng. Sau migration, chạy cùng bộ test với application/profile/label giống nhau và so sánh giá trị hiệu lực. Nếu có thay đổi, quyết định đó là chủ đích hay regression.

## 10. Gỡ legacy bootstrap đúng cách

Sau khi Config Data import đã hoạt động, kiểm tra và loại bỏ các thành phần legacy nếu không còn consumer phụ thuộc.

| Thành phần cũ | Việc cần làm khi migration |
| --- | --- |
| `spring-cloud-starter-bootstrap` | Gỡ dependency nếu không còn integration cần bootstrap context |
| `spring.cloud.bootstrap.enabled=true` | Bỏ cờ bật bootstrap legacy sau khi chuyển xong |
| `spring.config.use-legacy-processing=true` | Bỏ cờ tương thích Config File processing cũ khi không còn cần |
| `bootstrap.yml`/`bootstrap.properties` | Chuyển thuộc tính phù hợp sang `application.yml`, environment hoặc Config Data import |
| `BootstrapConfiguration` | Xác định integration còn cần hay đã có cách tích hợp Config Data mới |
| `PropertySourceLocator` tùy chỉnh | Kiểm tra hỗ trợ Config Data; không giả định locator legacy tự chạy trong pipeline mới |

Không xóa dependency bootstrap chỉ vì file `bootstrap.yml` đã được chuyển. Một thư viện khác có thể còn dựa vào bootstrap context. Kiểm tra dependency tree và tài liệu của từng integration, sau đó chạy test khởi động từ context sạch.

Nếu chưa thể chuyển một integration, có thể giữ legacy bootstrap như bước chuyển tiếp theo đúng tài liệu phiên bản. Tránh bật cả hai cơ chế cùng lúc theo cách khiến Config Server bị gọi hai lần hoặc property source bị nạp trùng.

## 11. Các integration tùy chỉnh cần rà soát riêng

Một số ứng dụng dùng bootstrap context để khởi tạo:

- Custom `PropertySourceLocator`.
- Custom `BootstrapConfiguration`.
- Secret manager client hoặc Vault integration cũ.
- Service discovery properties cần có trước Config Server lookup.
- Custom encryption/decryption hoặc property source post-processor.
- Shared library đăng ký bean trong bootstrap context.

Với mỗi integration, cần xác định:

1. Nó chạy ở bootstrap phase hay application context?
2. Nó cần cung cấp thuộc tính trước hay sau Config Data import?
3. Release mới có Config Data loader hoặc extension point thay thế không?
4. Nếu vẫn dùng bootstrap, dependency nào kích hoạt nó và có gây duplicate load không?
5. Có test khởi động và kiểm tra precedence cho cả profile thường lẫn profile production không?

Không chuyển một `PropertySourceLocator` sang `EnvironmentPostProcessor` một cách máy móc. Đây là các extension point khác nhau và có thời điểm chạy, lifecycle và contract riêng.

## 12. Nâng cấp các thuộc tính Actuator cũ

Spring Boot 2 thay đổi cấu trúc cấu hình Actuator. Các ví dụ cũ có thể dùng `endpoints.*`, `management.context-path` hoặc `management.security.enabled`. Ở các phiên bản hiện đại, dùng namespace `management.endpoints.*`, `management.endpoint.*` và cấu hình Spring Security riêng.

| Cấu hình cũ thường gặp | Cách hiện đại cần xem xét |
| --- | --- |
| `endpoints.health.enabled` | `management.endpoint.health.enabled` |
| `endpoints.refresh.enabled` | `management.endpoint.refresh.enabled` nếu endpoint có thuộc tính enabled tương ứng; đồng thời kiểm tra dependency và exposure |
| `management.context-path=/manage` | `management.endpoints.web.base-path=/manage` |
| `management.security.enabled=false` | Bỏ thuộc tính cũ; cấu hình `SecurityFilterChain` để bảo vệ management endpoints |
| `endpoints.*.sensitive` | Dùng exposure, authorization và cấu hình hiển thị detail của endpoint tương ứng |
| `endpoints.health.show-details` | `management.endpoint.health.show-details` |
| Chỉ định endpoint qua `endpoints.*` | `management.endpoints.web.exposure.include` và `management.endpoint.<id>.*` |

Không thay thế máy móc mọi thuộc tính cũ bằng một tên mới. Có thuộc tính đã bị loại bỏ, có thuộc tính chuyển namespace, và có hành vi được chuyển sang Spring Security. Kiểm tra configuration metadata và reference của đúng Spring Boot version.

## 13. Cấu hình Actuator hiện đại

Ví dụ expose các endpoint cần thiết cho vận hành:

```yaml
management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info,refresh
  endpoint:
    health:
      show-details: when-authorized
```

Nếu ứng dụng dùng Spring Cloud Bus và cần endpoint bus refresh, thêm endpoint ID tương ứng theo release:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh,busrefresh
```

Chỉ expose endpoint thực sự được dùng. Không dùng `include: "*"` trong production chỉ để làm cho endpoint mới hoạt động. Endpoint nhạy cảm như `env`, `configprops`, `heapdump`, `logfile` hoặc `shutdown` không nên mở rộng cho mọi client.

Exposure chỉ quyết định endpoint có được truy cập qua web hay không; nó không tự tạo authorization. Cần cấu hình security để giới hạn ai có quyền gọi refresh, bus refresh hoặc xem health detail.

## 14. Đường dẫn refresh và Bus đã thay đổi

Trong ứng dụng hiện đại, endpoint refresh của Spring Cloud Context thường được truy cập dưới Actuator base path:

```text
POST /actuator/refresh
```

Endpoint này làm mới cấu hình phía một ứng dụng client. Nếu management base path được đổi, ví dụ `/manage`, đường dẫn trở thành `/manage/refresh` trừ khi có path mapping khác.

Với Spring Cloud Bus, endpoint bus refresh thường có endpoint ID `busrefresh`:

```text
POST /actuator/busrefresh
```

Nó phát sự kiện qua broker để các instance liên quan xử lý refresh. Tên endpoint và URL có thể khác giữa release cũ/mới hoặc do `management.endpoints.web.path-mapping` tùy chỉnh. Hãy kiểm tra endpoint mappings thực tế của ứng dụng thay vì dựa vào bài hướng dẫn cũ.

Các đường dẫn cũ như `/refresh` hoặc `/bus/refresh` không nên được giả định còn hoạt động sau nâng cấp. Nếu hệ thống có API gateway hoặc webhook đang gọi đường dẫn cũ, cần cập nhật route và test end-to-end.

## 15. Phân biệt Config Server `/monitor` với Actuator refresh

Ba endpoint thường bị nhầm lẫn:

| Endpoint | Thành phần nhận | Mục đích |
| --- | --- | --- |
| `/actuator/refresh` | Một Config Client | Client tải lại cấu hình và refresh scope |
| `/actuator/busrefresh` | Một ứng dụng có Spring Cloud Bus | Phát refresh event để nhiều instance nhận qua broker |
| `/monitor` | Config Server có `spring-cloud-config-monitor` | Nhận webhook từ Git provider và phát thông báo thay đổi cấu hình |

`/monitor` là endpoint của Config Server monitor integration, không phải mặc định là `/actuator/monitor`. Khi chuyển Actuator base path, không tự đổi `/monitor` theo base path nếu phiên bản monitor không quy định như vậy.

Luồng webhook thường là Git provider gọi `/monitor`; Config Server xác định repository/path thay đổi và gửi refresh notification qua Bus hoặc cơ chế notifier được hỗ trợ. Client sau đó lấy lại cấu hình qua Config Server. Webhook accepted không đồng nghĩa mọi client đã áp dụng giá trị mới.

## 16. Bảo vệ endpoint quản trị bằng Spring Security

Các hướng dẫn cũ thường tắt bảo vệ Actuator bằng:

```yaml
management:
  security:
    enabled: false
```

Thuộc tính này không phải cách bảo vệ hiện đại và không nên được dùng trong ứng dụng mới. Hãy cấu hình Spring Security, tách quyền truy cập management endpoints khỏi API nghiệp vụ và giới hạn network access.

Ví dụ định hướng:

```java
@Bean
SecurityFilterChain managementSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/actuator/**")
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/actuator/health", "/actuator/health/**")
                .permitAll()
            .requestMatchers("/actuator/refresh", "/actuator/busrefresh")
                .hasRole("CONFIG_OPERATOR")
            .requestMatchers("/actuator/info")
                .hasAnyRole("CONFIG_OPERATOR", "MONITORING")
            .anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Đây là ví dụ cấu trúc authorization; cần thêm import, authentication provider và CSRF policy phù hợp. Với endpoint POST, không tắt CSRF toàn cục một cách tùy tiện. Nếu endpoint chỉ được gọi bởi service-to-service automation, chọn cơ chế xác thực phù hợp như mTLS hoặc OAuth2 client credentials và giới hạn network.

Nếu management server dùng port riêng qua `management.server.port`, cần bảo vệ listener và firewall riêng. Security matcher phải khớp base path và servlet context path thực tế.

## 17. Cập nhật health và thông tin Actuator

Các thuộc tính hiện đại thường được đặt dưới `management.endpoint.*`:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
```

Liveness/readiness probes có thể hữu ích cho deployment platform. Không để health detail tiết lộ hostname nội bộ, secret path hoặc credential. Health indicator cũng không nên khiến instance restart liên tục chỉ vì backend cấu hình tạm thời chậm, nếu restart làm giảm thêm khả năng phục vụ.

Đối với Config Server, health endpoint không nhất thiết kiểm tra mọi application/profile/label. Với backend quan trọng, bổ sung synthetic test bằng danh tính có quyền tối thiểu và kiểm tra một cấu hình không nhạy cảm.

## 18. Các thuộc tính Actuator và endpoint cần rà soát khi nâng cấp

| Mục | Câu hỏi cần trả lời |
| --- | --- |
| `management.endpoints.web.base-path` | Management base path hiện là `/actuator`, `/manage` hay path riêng? |
| `management.endpoints.web.exposure.include` | Endpoint nào thực sự cần được expose? |
| `management.endpoint.<id>.enabled` | Endpoint có được bật trong version hiện tại và dependency graph không? |
| `management.endpoint.health.show-details` | Ai được xem health detail và detail có nhạy cảm không? |
| `management.server.port` | Management endpoints dùng cùng port hay port riêng? |
| `management.endpoints.web.path-mapping` | Có remap endpoint ID sang URL khác không? |
| Spring Security | Ai được phép gọi refresh, busrefresh, monitor và xem info? |
| Reverse proxy/API gateway | Route cũ có được chuyển sang endpoint mới chưa? |
| CSRF/CORS | Request POST nội bộ có policy đúng và không mở rộng không cần thiết? |

Đừng dùng `/actuator/env` để xác minh migration trên production nếu chưa đánh giá rò rỉ. Trong test, có thể inject `Environment` và assert giá trị trực tiếp; nếu cần endpoint chẩn đoán, bảo vệ nó và giới hạn output.

## 19. Migration theo giai đoạn

Chuyển bootstrap và Actuator cùng lúc có thể làm khó xác định nguyên nhân nếu startup hoặc refresh thất bại. Nên chia migration thành các bước có thể kiểm chứng.

### Giai đoạn 1 — Inventory

- Liệt kê `bootstrap.yml`, `bootstrap.properties` và mọi `spring-cloud-starter-bootstrap`.
- Tìm `spring.cloud.bootstrap.enabled` và `spring.config.use-legacy-processing`.
- Liệt kê custom bootstrap configuration, `PropertySourceLocator` và third-party integration.
- Ghi lại Config Server URI, application name, profile, label, fail-fast và retry.
- Liệt kê Actuator endpoint và URL đang được webhook, gateway, monitoring gọi.
- Ghi nhận property source/value hiệu lực của các khóa quan trọng.

### Giai đoạn 2 — Chuẩn bị Config Data

- Nâng Spring Boot và Spring Cloud theo compatibility matrix.
- Thêm/cập nhật Config Client starter tương thích.
- Thêm `spring.config.import` vào cấu hình cục bộ.
- Chuyển application name, profile, label và URI cần thiết.
- Chọn required/optional và retry.
- Giữ bootstrap legacy trong branch migration nếu cần để so sánh, không bật hai cơ chế song song thiếu kiểm soát.

### Giai đoạn 3 — Kiểm thử startup và precedence

- Khởi động từ context sạch với profile `test`.
- Xác nhận Config Server được gọi đúng một lần theo luồng mong đợi.
- Kiểm tra application/profile/label request.
- So sánh giá trị hiệu lực trước và sau migration.
- Kiểm tra khi Config Server down, timeout, trả 401/403 và trả 404.
- Xác nhận các custom bootstrap integration đã có cách thay thế.

### Giai đoạn 4 — Chuyển Actuator

- Đổi các thuộc tính `endpoints.*` sang `management.*` phù hợp.
- Đặt base path và exposure rõ ràng.
- Cấu hình Spring Security cho endpoint quản trị.
- Cập nhật `/refresh`, `/bus/refresh` hoặc URL cũ sang path hiện hành.
- Giữ `/monitor` đúng ở Config Server nếu webhook integration sử dụng.
- Kiểm tra endpoint qua gateway và trực tiếp trong mạng nội bộ.

### Giai đoạn 5 — Canary và rollout

- Triển khai một instance hoặc một service canary.
- Kiểm tra startup, property values, refresh và Actuator security.
- So sánh revision và hành vi với instance cũ.
- Rollout theo nhóm, theo dõi lỗi startup, refresh failure và backend load.
- Chỉ gỡ dependency bootstrap và file cũ khi không còn consumer cần chúng.

## 20. Kiểm thử bắt buộc sau migration

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Config Server hoạt động | Client nạp đúng cấu hình từ application/profile/label |
| Config Server không hoạt động, import required | Startup thất bại rõ ràng sau retry có giới hạn |
| Config Server không hoạt động, import optional | Client chỉ tiếp tục nếu fallback được thiết kế và an toàn |
| Config Server trả 401/403 | Báo lỗi authentication/authorization; không retry vô hạn |
| Profile thay đổi | Client yêu cầu đúng profile và nhận đúng property source |
| Local/remote key trùng nhau | Giá trị hiệu lực tuân theo precedence đã xác minh |
| POST `/actuator/refresh` | Chỉ client mục tiêu refresh và endpoint yêu cầu quyền phù hợp |
| POST `/actuator/busrefresh` | Các instance có quyền và kết nối broker nhận event |
| Git webhook gọi `/monitor` | Config Server nhận webhook và phát thông báo theo cấu hình |
| User không có quyền gọi refresh | Nhận 401/403; không thể thay đổi cấu hình runtime |
| User không có quyền xem `/actuator/env` | Bị từ chối hoặc endpoint không được expose |
| Rollback về release trước | Cấu hình, endpoint và dependency vẫn tương thích với code được rollback |

Không chỉ kiểm tra HTTP status. Với refresh, kiểm tra `Environment`, bean refresh-scoped và hành vi nghiệp vụ. Với Bus, kiểm tra client nhận event và tải lại cấu hình, không chỉ kiểm tra request publish thành công.

## 21. Những lỗi thường gặp khi chuyển đổi

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Config Client không gọi Config Server | Thiếu `spring.config.import` hoặc thiếu Config Client dependency | Kiểm tra Config Data import và release train |
| `No spring.config.import property has been defined` | Import bắt buộc chưa được khai báo | Thêm `configserver:` hoặc `optional:configserver:` theo chính sách |
| Ứng dụng gọi Config Server hai lần | Legacy bootstrap và Config Data cùng hoạt động hoặc có nhiều import | Xác định nguồn nào kích hoạt từng request và loại cấu hình trùng |
| Giá trị remote khác trước migration | Thứ tự property source thay đổi | So sánh effective Environment và các cờ override remote |
| Profile-specific config không được nạp | Active profile/name/label sai hoặc profile activation khác | Kiểm tra request path và profile ở Config Server |
| Retry không hoạt động | Thuộc tính retry đặt sai phase hoặc thiếu dependency | Dùng tham số Config Data phù hợp release và thêm dependency được yêu cầu |
| `/refresh` trả 404 | Base path Actuator đã đổi hoặc endpoint chưa expose | Kiểm tra `/actuator/refresh`, base-path và endpoint exposure |
| `/actuator/refresh` trả 404 | Thiếu Spring Cloud Context hoặc endpoint bị disable | Kiểm tra dependency và endpoint enabled/exposure |
| `/bus/refresh` trả 404 | URL cũ không còn phù hợp | Kiểm tra endpoint ID `busrefresh` và path mapping hiện tại |
| `/monitor` trả 404 | Config Server thiếu monitor integration hoặc route bị đổi | Kiểm tra `spring-cloud-config-monitor` và Config Server route |
| Refresh trả 403 | Security rule hoặc CSRF policy chặn POST | Cấp quyền cho automation identity theo nguyên tắc tối thiểu |
| Health detail không hiển thị | `show-details` hoặc authorization chưa đúng | Dùng `when-authorized` và kiểm tra role của caller |
| Actuator lộ thông tin môi trường | Exposure quá rộng hoặc security chưa cấu hình | Thu hẹp exposure và bảo vệ endpoint nhạy cảm |

## 22. Rollback kế hoạch migration

Giữ một đường quay lại rõ ràng trong suốt canary và rollout:

1. Lưu artifact ứng dụng cũ, dependency lock/BOM và cấu hình cũ.
2. Lưu commit/tag Config repository tương ứng với phiên bản đang chạy.
3. Ghi lại endpoint path và security policy trước migration.
4. Nếu Config Data import lỗi, có thể rollback ứng dụng về artifact legacy trong thời gian bootstrap dependency và cấu hình cũ còn được giữ.
5. Nếu Actuator route mới lỗi, khôi phục gateway/security mapping tương thích với artifact rollback.
6. Không xóa `bootstrap.yml`, dependency bootstrap hoặc endpoint cũ trước khi rollback window kết thúc.
7. Sau rollback, xác minh startup, lấy cấu hình, refresh và quyền Actuator.

Không duy trì hai đường cấu hình lâu hơn cần thiết. Sau khi migration ổn định và hết rollback window, loại bỏ cờ legacy, dependency và file không còn sử dụng để tránh trạng thái vận hành mơ hồ.

## 23. Checklist trước khi hoàn tất nâng cấp

- [ ] Spring Boot, Spring Cloud và các starter dùng version tương thích.
- [ ] Config Client dùng Config Data import `configserver:` theo chuẩn hiện đại.
- [ ] Đã chọn rõ import required hay optional.
- [ ] Retry có giới hạn và phù hợp với Config Data loader của release.
- [ ] Application name, active profile và label được thiết lập trước khi import.
- [ ] Đã kiểm tra lại property source precedence và các remote override flags.
- [ ] Đã rà soát custom bootstrap configuration và third-party integration.
- [ ] Không còn bật đồng thời legacy bootstrap và Config Data ngoài chủ đích.
- [ ] `spring-cloud-starter-bootstrap` và `spring.config.use-legacy-processing` được gỡ khi không còn cần.
- [ ] Actuator dùng `management.endpoints.*` và `management.endpoint.*` phù hợp version.
- [ ] Base path, endpoint exposure và management port được tài liệu hóa.
- [ ] Refresh endpoint được kiểm tra ở path thực tế.
- [ ] Bus refresh endpoint được kiểm tra nếu ứng dụng dùng Bus.
- [ ] Config Server `/monitor` vẫn được route đúng cho webhook nếu cần.
- [ ] Spring Security giới hạn quyền gọi endpoint quản trị.
- [ ] `/env`, `/configprops` và endpoint nhạy cảm không bị expose rộng.
- [ ] Đã kiểm thử required/optional, profile, label, retry và precedence.
- [ ] Đã kiểm thử refresh từng client, bus refresh và webhook end-to-end.
- [ ] Có canary, rollback artifact và rollback window.
- [ ] Đã xóa cấu hình legacy sau khi migration hoàn tất và xác nhận không còn consumer.

## 24. Tài liệu tham khảo

- [Spring Cloud Config — Config Client and Config Data Import](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Actuator Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.security)
- [Spring Cloud Commons — Application Context Services and Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Cloud Bus — Configuration and Bus Endpoints](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/configuration.html)

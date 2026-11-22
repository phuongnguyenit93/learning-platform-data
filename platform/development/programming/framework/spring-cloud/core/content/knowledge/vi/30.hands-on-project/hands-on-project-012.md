# Chẩn đoán sự cố từ bằng chứng env, conditions, health và log

Khi một dịch vụ Spring Cloud bắt đầu trả lỗi sau khi triển khai cấu hình mới, câu hỏi đầu tiên thường là: lỗi nằm ở cấu hình, auto-configuration, dependency bên ngoài hay code xử lý request? Mỗi loại bằng chứng trả lời một phần khác nhau. Actuator giúp quan sát Environment, các điều kiện tạo bean, trạng thái health và mức log; log ứng dụng cho biết điều gì đã xảy ra trong một request cụ thể.

Bài thực hành này mô phỏng incident của **orders-service**. Sau khi một revision cấu hình production được rollout, các request tạo đơn hàng bắt đầu lỗi khi gọi Inventory. Readiness chuyển sang DOWN, trong khi liveness vẫn UP. Người học cần thu thập bằng chứng từ **/actuator/env**, **/actuator/configprops**, **/actuator/conditions**, **/actuator/health**, **/actuator/loggers** và log tập trung để xác định nguyên nhân.

Kết quả điều tra là một hostname sai trong cấu hình được lấy từ Spring Cloud Config. **conditions** xác nhận bean Inventory Client vẫn được tạo; **configprops** cho thấy giá trị đã bind; **health** báo dependency không truy cập được; log xác nhận lỗi DNS. Từ đó, nhóm vận hành sửa đúng nguồn cấu hình, rollout an toàn và xác minh từng replica.

Bài học thuộc chương **Thực hành tổng hợp** của module **SPRING_CLOUD_CORE**. Trọng tâm là cách kết hợp các abstraction Spring Cloud với khả năng quan sát của Spring Boot Actuator để đưa ra kết luận dựa trên bằng chứng, đồng thời bảo vệ dữ liệu vận hành và tránh gây thêm sự cố trong lúc chẩn đoán.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Lập timeline incident và xác định phạm vi ảnh hưởng theo service, instance, profile và config revision.
2. Phân biệt vai trò của **env**, **configprops**, **conditions**, **health** và **loggers**.
3. Truy ra giá trị property hiệu lực cùng PropertySource hoặc origin đã cung cấp giá trị đó.
4. So sánh giá trị trong Environment với giá trị đã bind vào **@ConfigurationProperties**.
5. Đọc điều kiện auto-configuration để xác nhận bean được tạo hoặc bị loại.
6. Đọc health component và readiness/liveness để phân biệt lỗi ứng dụng với lỗi dependency.
7. Dùng log, exception chain và correlation ID để xác minh giả thuyết.
8. Tạm thời tăng log level cho đúng package rồi khôi phục sau khi điều tra.
9. Phân biệt lỗi DNS, connection refused, timeout, TLS và HTTP authentication.
10. Xử lý sự khác nhau giữa các replica và các revision cấu hình.
11. Sửa nguồn cấu hình đúng nơi sở hữu và rollout có kiểm soát.
12. Giữ Actuator, log và dữ liệu cấu hình trong phạm vi truy cập được bảo vệ.

## 2. Kiến trúc của bài lab

### 2.1. Dịch vụ và dependency

Bài lab có ba thành phần:

- **orders-service**: nhận yêu cầu tạo đơn và gọi Inventory để kiểm tra tồn kho.
- **inventory-service**: cung cấp API tra cứu tồn kho và health endpoint.
- **Spring Cloud Config Server**: phân phối cấu hình theo application, profile và label.

**orders-service** có ba replica chạy profile **prod**. Mỗi replica lấy cấu hình theo cùng một config label trong lần rollout.

~~~mermaid
flowchart LR
    U[Client] --> O[Orders Service]
    O --> I[Inventory Service]
    O --> C[Spring Cloud Config Server]
    O --> A[Actuator]
    A --> E[env and configprops]
    A --> D[conditions]
    A --> H[health]
    A --> L[loggers]
    O --> G[Centralized Logs]
    G --> T[Incident Timeline]
~~~

### 2.2. Luồng cấu hình

**orders-service** có cấu hình mặc định an toàn trong artifact. Config Server cung cấp các giá trị riêng cho profile production. Spring Boot hợp nhất các PropertySource vào Environment; sau đó **@ConfigurationProperties** bind các giá trị cần thiết vào object có kiểu.

~~~mermaid
flowchart TD
    A[application.yml in artifact] --> E[Spring Environment]
    B[Config Server prod label] --> E
    C[Environment variables] --> E
    E --> D[PropertySource precedence]
    D --> P[InventoryProperties binding]
    P --> I[Inventory Client bean]
    I --> H[Inventory health check]
~~~

Một property xuất hiện trong Environment chưa chứng minh bean đã nhận giá trị đó. Ngược lại, bean có thể vẫn giữ giá trị cũ nếu cấu hình thay đổi sau khi bean đã được khởi tạo và lifecycle của bean không hỗ trợ refresh. Vì vậy, cần đối chiếu cả **env** lẫn **configprops**.

### 2.3. Các endpoint được dùng

| Endpoint | Bằng chứng chính | Câu hỏi cần trả lời |
| --- | --- | --- |
| **/actuator/env** | PropertySource và giá trị hiệu lực trong Environment | Giá trị đến từ nguồn nào? |
| **/actuator/configprops** | Object đã bind từ @ConfigurationProperties | Bean cấu hình đang giữ giá trị nào? |
| **/actuator/conditions** | Điều kiện auto-configuration và lý do match/non-match | Bean có được đăng ký không? |
| **/actuator/health** | Trạng thái ứng dụng và các component | Thành phần nào đang DOWN? |
| **/actuator/health/readiness** | Khả năng nhận traffic | Instance có nên nhận request không? |
| **/actuator/health/liveness** | Trạng thái nội tại của process/context | Có cần restart process không? |
| **/actuator/loggers** | Configured/effective log level | Có đủ log chi tiết để kiểm tra không? |
| Log tập trung | Request, exception và timeline | Điều gì đã xảy ra trong thực tế? |

Các endpoint chỉ có thể truy cập nếu dependency, access policy và exposure được cấu hình phù hợp. Spring Boot mặc định chỉ expose health qua HTTP; không nên mở tất cả endpoint chỉ để tiện điều tra.

## 3. Kịch bản incident

### 3.1. Thông báo từ hệ thống giám sát

Lúc 14:05 UTC, nhóm triển khai cập nhật config label **orders-prod-2026.11.18-42** và rollout **orders-service** version **2.8.1**.

Sau rollout:

- Tỷ lệ lỗi tạo đơn tăng từ dưới 0,2% lên 18%.
- Readiness của ba replica chuyển sang DOWN.
- Liveness của các replica vẫn UP.
- Database health vẫn UP.
- Inventory health chuyển sang DOWN.
- Log xuất hiện **UnknownHostException** khi gọi Inventory.
- **inventory-service** vẫn trả health UP khi được kiểm tra trực tiếp.

### 3.2. Timeline ban đầu

| Thời điểm UTC | Sự kiện |
| --- | --- |
| 13:55 | Bản phát hành orders-service:2.8.1 được kiểm thử ở staging |
| 14:05 | Config label production mới được promotion |
| 14:06 | Replica đầu tiên nhận traffic với config revision mới |
| 14:07 | Readiness của replica đầu tiên chuyển DOWN |
| 14:08 | Hai replica còn lại hoàn tất rollout và cũng chuyển DOWN |
| 14:09 | Alert báo lỗi gọi Inventory tăng cao |
| 14:12 | Nhóm vận hành bắt đầu thu thập bằng chứng |
| 14:24 | Xác định property endpoint có hostname sai |
| 14:31 | Config revision sửa lỗi được tạo và review |
| 14:38 | Rollout cấu hình đã sửa bắt đầu |
| 14:43 | Readiness của các replica trở lại UP |

Các mốc giờ trong bài là dữ liệu mô phỏng. Khi xử lý incident thật, phải dùng timestamp từ hệ thống triển khai, log collector và từng instance; kiểm tra timezone và clock skew trước khi ghép sự kiện.

### 3.3. Giả thuyết ban đầu

Nhóm trực vận hành ghi nhận bốn giả thuyết:

1. Inventory service đang ngừng hoạt động.
2. Discovery hoặc load balancer không tìm được instance Inventory.
3. Inventory Client không được auto-configure sau rollout.
4. Endpoint trong cấu hình của Orders bị sai.

Không chọn giả thuyết chỉ dựa trên alert. Mỗi giả thuyết cần một bằng chứng có thể xác nhận hoặc bác bỏ.

## 4. Chuẩn bị cấu hình và ứng dụng mẫu

### 4.1. Cấu hình mặc định

Trong **application.yml**, đặt cấu hình mặc định không phụ thuộc môi trường:

~~~yaml
spring:
  application:
    name: orders-service

app:
  inventory:
    enabled: true
    base-url: https://inventory.default.internal
    timeout: 1s

management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Cấu hình mặc định giúp local hoặc test có giá trị rõ ràng. Production có thể ghi đè endpoint bằng Config Server.

### 4.2. Cấu hình production trước khi xảy ra incident

Giả sử Config Server trả về:

~~~yaml
app:
  inventory:
    enabled: true
    base-url: https://inventroy.internal
    timeout: 800ms
~~~

Hostname **inventroy.internal** bị đảo vị trí chữ **o** và **r**. Hostname đúng phải là **inventory.internal**.

Trong bài lab, Config Server là nguồn sở hữu cấu hình production. Local **application.yml** chỉ chứa default. Việc chẩn đoán cần xác định property hiệu lực và nguồn đã cung cấp nó.

### 4.3. ConfigurationProperties

Ví dụ cấu hình có kiểu:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.inventory")
@Validated
public record InventoryProperties(
        boolean enabled,
        @NotBlank String baseUrl,
        @NotNull Duration timeout
) {
}
~~~

Đăng ký bằng **@ConfigurationPropertiesScan** hoặc **@EnableConfigurationProperties**. Khi đọc **/actuator/configprops**, tìm bean có prefix **app.inventory** và đối chiếu các giá trị đã bind.

Record constructor-bound phù hợp khi cấu hình được nạp lúc startup. Nếu cấu hình thay đổi sau startup, không giả định record tự được tạo lại hoặc rebind. Chọn refresh/restart theo lifecycle thực tế của client.

### 4.4. Bean được điều kiện hóa

Giả sử Inventory Client chỉ được tạo khi property bật:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.inventory",
        name = "enabled",
        havingValue = "true"
)
class InventoryClientConfiguration {

    @Bean
    InventoryClient inventoryClient(
            InventoryProperties properties,
            RestClient.Builder builder
    ) {
        return new InventoryClient(
                builder,
                properties.baseUrl(),
                properties.timeout()
        );
    }
}
~~~

Trong code dự án, **InventoryClient** là class do ứng dụng định nghĩa và có method **checkHealth()** dùng endpoint đã cấu hình. Điểm quan trọng của ví dụ là điều kiện tạo bean dựa trên **app.inventory.enabled**.

Nếu property là **false**, **InventoryClientConfiguration** không match và bean có thể không được đăng ký. Khi đó, **conditions** là bằng chứng cần kiểm tra.

### 4.5. Health indicator riêng cho Inventory

Để health endpoint có component **inventory**, ứng dụng đăng ký một HealthIndicator. Ví dụ dưới đây dùng API package của Spring Boot 4.x; với Spring Boot 3.x, package của Actuator health API khác, cần theo dependency BOM của dự án.

~~~java
package com.example.orders.health;

import com.example.orders.inventory.InventoryClient;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("inventory")
public class InventoryHealthIndicator implements HealthIndicator {

    private final ObjectProvider<InventoryClient> inventoryClientProvider;

    public InventoryHealthIndicator(
            ObjectProvider<InventoryClient> inventoryClientProvider) {
        this.inventoryClientProvider = inventoryClientProvider;
    }

    @Override
    public Health health() {
        InventoryClient inventoryClient =
                inventoryClientProvider.getIfAvailable();

        if (inventoryClient == null) {
            return Health.unknown()
                    .withDetail("reason", "inventory-client-not-configured")
                    .build();
        }

        try {
            inventoryClient.checkHealth();

            return Health.up()
                    .withDetail("dependency", "inventory")
                    .build();
        }
        catch (Exception exception) {
            return Health.down()
                    .withDetail(
                            "cause",
                            exception.getClass().getSimpleName()
                    )
                    .build();
        }
    }
}
~~~

Không đưa URL chứa credential, bearer token hoặc toàn bộ exception message vào health details. Health details có thể được thu thập bởi hệ thống giám sát và lưu lâu hơn log ngắn hạn.

### 4.6. Chọn readiness group

Nếu Orders không thể tạo đơn hợp lệ khi Inventory không truy cập được, có thể thêm indicator **inventory** vào readiness group:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db,inventory
~~~

Chỉ thêm dependency thật sự thiết yếu. Nếu ứng dụng có circuit breaker, fallback hoặc vẫn phục vụ được một phần nghiệp vụ khi Inventory ngừng hoạt động, cân nhắc không đưa Inventory vào readiness.

Không thêm health check dependency bên ngoài vào liveness. Nếu Inventory gặp sự cố mà liveness chuyển DOWN, nền tảng có thể restart hàng loạt replica và làm tình hình xấu hơn.

## 5. Bảo đảm có thể thu thập bằng chứng an toàn

### 5.1. Actuator dependency và exposure

Ứng dụng cần dependency Actuator tương ứng, thường là **spring-boot-starter-actuator**. Kiểm tra dependency tree và cấu hình của đúng Spring Boot release train nếu endpoint không tồn tại.

Trong môi trường điều tra được kiểm soát, cấu hình exposure có thể cho phép các endpoint cần thiết:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - env
          - configprops
          - conditions
          - loggers
~~~

Cấu hình trên chỉ minh họa danh sách endpoint phục vụ lab. Trong production, chỉ expose endpoint thực sự cần, qua management network/firewall và xác thực/phân quyền.

### 5.2. Quyền truy cập opt-in

Có thể dùng access policy theo hướng opt-in:

~~~yaml
management:
  endpoints:
    access:
      default: none
  endpoint:
    health:
      access: read-only
    env:
      access: read-only
    configprops:
      access: read-only
    conditions:
      access: read-only
    loggers:
      access: read-only
~~~

Khi cần thay log level qua POST, cấp write access tạm thời cho **loggers** theo chính sách vận hành và chỉ cho role được phép. Sau điều tra, trả endpoint về read-only hoặc access policy ban đầu.

Access và exposure là hai điều kiện riêng. Endpoint chỉ sẵn sàng qua HTTP khi được cho phép truy cập và được expose.

### 5.3. Sanitization của env và configprops

Giá trị trả về từ **env** và **configprops** có thể chứa password, token, secret hoặc private key. Spring Boot mặc định sanitize các giá trị nhạy cảm.

Có thể cho role vận hành đã xác thực xem giá trị không nhạy cảm:

~~~yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles: OPS
    configprops:
      show-values: when-authorized
      roles: OPS
~~~

Không đặt **show-values: always** cho production. Ví dụ trên chỉ cho role OPS đã xác thực xem giá trị trong cửa sổ điều tra; hãy dùng custom **SanitizingFunction** để tiếp tục che password, token, private key và các nguồn nhạy cảm. Nếu chưa có quy tắc sanitize đáng tin cậy, giữ **configprops.show-values: never** và xác minh property không nhạy cảm bằng một kênh quản trị khác.

### 5.4. Health details

Health component và details có thể bị ẩn theo cấu hình. Ví dụ:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      roles: OPS
      show-components: when-authorized
~~~

Nếu không có quyền xem details, vẫn có thể nhận được status tổng quát. Khi đó, dùng log và kiểm tra dependency từ môi trường triển khai để xác minh nguyên nhân.

### 5.5. Không bật toàn bộ Actuator

Không dùng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

chỉ để điều tra nhanh. Các endpoint như **beans**, **env**, **configprops**, **mappings**, **heapdump** hoặc **logfile** có thể tiết lộ thông tin vận hành nhạy cảm. Chọn endpoint theo câu hỏi cần trả lời.

## 6. Bắt đầu điều tra: xác định đúng instance

### 6.1. Ghi nhận phạm vi

Trước khi gọi endpoint, ghi lại:

- Service name và application version.
- Spring Boot version và Spring Cloud release train.
- Active profiles.
- Config Server label hoặc revision.
- Pod/instance ID.
- Namespace và cluster.
- Thời điểm triển khai.
- Thời điểm lỗi đầu tiên.
- Request/trace ID mẫu.
- Số replica bị ảnh hưởng.

### 6.2. Liệt kê replica

Với Kubernetes:

~~~bash
kubectl get pods -l app=orders-service -o wide
~~~

Ghi lại tên pod, IP, node và trạng thái. Không gom dữ liệu Actuator từ nhiều pod thành một bản ghi không có nhãn instance.

### 6.3. Thu thập log theo pod

~~~bash
kubectl logs pod/orders-service-abc123 -c app --since=30m
~~~

Lặp lại cho từng pod có ảnh hưởng. Nếu dùng centralized logging, lọc theo service, pod, container, khoảng thời gian và trace ID.

### 6.4. Kiểm tra revision cấu hình

Nếu ứng dụng phát hành config revision vào **/actuator/info** hoặc startup log, ghi lại revision của từng replica. Không tự thêm endpoint debug để trả toàn bộ Environment. Một revision ID không nhạy cảm đủ để đối chiếu với Config Server hoặc deployment record.

## 7. Đọc /actuator/env: giá trị đến từ đâu?

### 7.1. Câu hỏi của endpoint

**env** cho biết các PropertySource trong Spring Environment và giá trị resolve của property. Khi điều tra, cần tìm:

- Property có tồn tại không?
- PropertySource nào cung cấp nó?
- Có nguồn ưu tiên cao hơn ghi đè không?
- Profile nào đang active?
- Origin có trỏ về file hoặc config revision dự kiến không?

Ví dụ truy vấn một property:

~~~bash
curl -sS \
  -H "Authorization: Bearer $OPS_TOKEN" \
  "$ACTUATOR/actuator/env/app.inventory.base-url"
~~~

Tên biến **ACTUATOR** là management URL của đúng instance, không phải load balancer chung nếu mục tiêu là so sánh replica.

### 7.2. Bằng chứng trong incident

Kết quả rút gọn từ replica **orders-service-abc123**:

~~~json
{
  "property": {
    "source": "configserver:orders-service-prod.yml",
    "value": "https://inventroy.internal",
    "origin": "orders-service-prod.yml:18"
  },
  "activeProfiles": ["prod"]
}
~~~

Cấu trúc JSON ở đây là minh họa nội dung cần đọc. Response thực tế của Actuator có thể lồng trong **propertySources** và có metadata khác theo phiên bản.

Bằng chứng này cho biết Environment đang dùng hostname sai và nguồn là cấu hình production từ Config Server. Nó chưa chứng minh bean Inventory Client đã bind giá trị này; bước tiếp theo là **configprops**.

### 7.3. PropertySource precedence

Một key có thể xuất hiện trong nhiều nguồn:

| Nguồn | Giá trị ví dụ |
| --- | --- |
| Command-line argument | https://inventory-cli.internal |
| Environment variable | https://inventory-env.internal |
| Config Server | https://inventroy.internal |
| application.yml | https://inventory.default.internal |

Giá trị cuối cùng phụ thuộc thứ tự PropertySource thực tế, không phụ thuộc tên file trông có vẻ “production” hơn. Luôn đọc origin/source trong Environment.

Nếu một pod có giá trị đúng và pod khác có giá trị sai, so sánh active profiles, environment variables, config revision và thời điểm rollout trước khi kết luận.

### 7.4. Khi env không hiển thị giá trị

Nếu giá trị bị thay bằng **********, đây có thể là sanitization đúng chính sách. Không tắt sanitization trên toàn hệ thống chỉ để xem một property.

Có thể tiếp tục bằng:

- Source name và origin nếu được trả về.
- Giá trị đã bind nhưng không nhạy cảm.
- Config revision trong deployment record.
- Log đã redact.
- Xác minh trực tiếp trong Config Server bằng quyền truy cập được phê duyệt.

## 8. Đọc /actuator/configprops: bean đã bind gì?

### 8.1. Vai trò của configprops

**configprops** hiển thị các bean **@ConfigurationProperties** và giá trị đã bind vào object. Nó giúp phát hiện các trường hợp:

- Environment đúng nhưng bean nhận giá trị khác.
- Sai prefix hoặc tên property.
- Type conversion không như mong đợi.
- Bean đang giữ giá trị cũ.
- Bean chưa được đăng ký hoặc chưa được tạo.

Endpoint có thể chứa thông tin nhạy cảm và được sanitize. Không dùng output thô làm attachment trong ticket công khai.

### 8.2. Đối chiếu InventoryProperties

Kết quả rút gọn:

~~~json
{
  "bean": "app.inventory-com.example.orders.InventoryProperties",
  "prefix": "app.inventory",
  "properties": {
    "enabled": true,
    "baseUrl": "https://inventroy.internal",
    "timeout": "PT0.8S"
  }
}
~~~

Environment và bean đều cho cùng hostname sai. Điều đó làm giả thuyết “bean chưa bind config mới” ít có khả năng hơn. Bằng chứng hiện tại nghiêng về nội dung config source.

### 8.3. Khi env đúng nhưng configprops sai

Nếu **env** hiển thị giá trị mới nhưng **configprops** vẫn có giá trị cũ, kiểm tra:

1. Bean có constructor binding/record không?
2. Bean được khởi tạo trước khi nguồn cấu hình mới được nạp không?
3. Bean có nằm trong **@RefreshScope** không?
4. Có event refresh hoặc rebinding nào thực sự được kích hoạt không?
5. Property có được bind vào một prefix khác không?
6. Có bean khác hoặc custom binder giữ một snapshot riêng không?

Không giả định mọi bean tự cập nhật khi Environment thay đổi. Với bean immutable hoặc resource được tạo từ cấu hình, rolling restart thường dễ kiểm chứng hơn.

### 8.4. Kiểm tra kiểu dữ liệu

Ví dụ **timeout: 800ms** có thể được bind thành **Duration PT0.8S**. Nếu giá trị đã bind là **PT8S**, có thể nguồn cấu hình đang dùng **8000ms** hoặc một giá trị khác. Luôn so sánh giá trị typed với giá trị nguồn và đơn vị.

## 9. Đọc /actuator/conditions: bean có được tạo không?

### 9.1. Điều kiện auto-configuration

**conditions** hiển thị các condition đã được đánh giá trên configuration và auto-configuration class, cùng lý do match hoặc không match.

Endpoint trả lời câu hỏi như:

- **@ConditionalOnClass** có tìm thấy class cần thiết không?
- **@ConditionalOnProperty** có đúng giá trị không?
- Có bean khác khiến **@ConditionalOnMissingBean** không match không?
- Auto-configuration có bị loại do dependency hoặc property không?

Nó không thay thế **env** hoặc **configprops**: conditions cho biết quyết định điều kiện, còn hai endpoint kia cho biết giá trị cấu hình.

### 9.2. Bằng chứng trong incident

Kết quả rút gọn:

~~~text
InventoryClientConfiguration
  matched:
    @ConditionalOnProperty
    app.inventory.enabled=true
    matched expected value true

RestClientAutoConfiguration
  matched:
    RestClient.Builder class present
~~~

Bằng chứng cho thấy Inventory Client được đăng ký. Vì vậy, lỗi không phải do **app.inventory.enabled=false** hoặc thiếu auto-configuration cần thiết.

### 9.3. Khi condition không match

Ví dụ:

~~~text
InventoryClientConfiguration
  did not match:
    @ConditionalOnProperty
    app.inventory.enabled did not find property
~~~

Khi đó, kiểm tra **env** để tìm xem key bị thiếu, profile sai hay PropertySource không được nạp. Kiểm tra **configprops** và bean registry theo nhu cầu.

Nếu bean definition không được tạo lúc startup, POST **/actuator/refresh** không tự động tái chạy toàn bộ auto-configuration để thêm bean đã vắng mặt. Cần sửa nguồn và khởi động lại/rollout context theo thiết kế.

### 9.4. Điều kiện không match không luôn là lỗi

Một auto-configuration không match có thể là hành vi mong muốn. Ví dụ, module optional bị tắt, class không nằm trên classpath hoặc một bean do ứng dụng cung cấp đã thay thế auto-configuration mặc định.

Chỉ xem condition là nguyên nhân khi nó mâu thuẫn với yêu cầu nghiệp vụ và các bằng chứng khác.

### 9.5. Khi ứng dụng không khởi động

Nếu context không khởi động nên không thể gọi **/actuator/conditions**, dùng startup condition report:

~~~bash
java -jar orders-service.jar --debug
~~~

Hoặc bật DEBUG có phạm vi cho **ConditionEvaluationReportLoggingListener** trong một lần chạy chẩn đoán có kiểm soát. Không để DEBUG toàn ứng dụng trong production lâu dài.

## 10. Đọc /actuator/health: thành phần nào đang hỏng?

### 10.1. Health tổng thể và component

**health** trả status tổng thể và có thể trả component lồng nhau. Mức chi tiết phụ thuộc **management.endpoint.health.show-details**, **show-components** và quyền truy cập.

Trong incident, response rút gọn:

~~~json
{
  "status": "DOWN",
  "components": {
    "db": {
      "status": "UP"
    },
    "inventory": {
      "status": "DOWN",
      "details": {
        "cause": "UnknownHostException"
      }
    },
    "discoveryComposite": {
      "status": "UP"
    }
  }
}
~~~

Database và discovery đang UP; Inventory component DOWN. Điều này làm giả thuyết database hỏng hoặc toàn bộ discovery ngừng hoạt động ít có khả năng hơn.

### 10.2. Health không tự chỉ ra nguyên nhân đầy đủ

**DOWN** là trạng thái, không phải kết luận root cause. Một health indicator có thể chỉ trả exception type hoặc thông tin đã được che. Dùng log để xem exception chain và thời điểm phát sinh.

Một health check có thể kiểm tra DNS, TCP connect, HTTP status hoặc một business operation. Hãy đọc implementation của indicator để hiểu nó thật sự kiểm tra điều gì.

### 10.3. Readiness và liveness

- Liveness trả lời process/context còn ở trạng thái có thể tiếp tục chạy hay không.
- Readiness trả lời instance có nên nhận traffic hay không.

Trong incident này, Inventory là dependency thiết yếu của luồng tạo đơn, nên nhóm đã đưa **inventory** vào readiness group. Vì thế readiness DOWN trong khi liveness vẫn UP là hợp lý.

~~~bash
curl -sS -H "Authorization: Bearer $OPS_TOKEN" \
  "$ACTUATOR/actuator/health/readiness"

curl -sS -H "Authorization: Bearer $OPS_TOKEN" \
  "$ACTUATOR/actuator/health/liveness"
~~~

Nếu Inventory chỉ là dependency tùy chọn và có fallback, không nên đưa nó vào readiness chỉ vì health indicator đang DOWN. Đưa một dependency dùng chung vào readiness có thể khiến tất cả replica bị loại khỏi load balancer.

### 10.4. Health group là quyết định nghiệp vụ

Spring Boot không tự thêm mọi external health indicator vào readiness group. Ứng dụng chọn các indicator cần thiết:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db,inventory
~~~

Nếu service có thể phục vụ request khi Inventory không sẵn sàng, thay đổi nhóm readiness hoặc dùng circuit breaker/fallback phù hợp. Không dùng liveness để kiểm tra dependency bên ngoài.

### 10.5. Kiểm tra HTTP status

Theo status mapping mặc định, **DOWN** và **OUT_OF_SERVICE** thường ánh xạ sang HTTP 503; **UP** trả HTTP 200. Nếu dự án có custom **HttpCodeStatusMapper** hoặc status mapping riêng, kiểm tra cấu hình thực tế trước khi diễn giải status code.

## 11. Dùng /actuator/loggers: tăng log có giới hạn

### 11.1. Đọc configured và effective level

Endpoint **loggers** cho biết mức log được cấu hình trực tiếp và mức hiệu lực từ logging framework.

~~~bash
curl -sS -H "Authorization: Bearer $OPS_TOKEN" \
  "$ACTUATOR/actuator/loggers/com.example.orders.inventory"
~~~

Ví dụ:

~~~json
{
  "configuredLevel": "INFO",
  "effectiveLevel": "INFO"
}
~~~

### 11.2. Tăng DEBUG cho đúng package

Khi cần thêm bằng chứng, tăng log level cho package cụ thể thay vì root logger:

~~~bash
curl -sS -X POST \
  -H "Authorization: Bearer $OPS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":"DEBUG"}' \
  "$ACTUATOR/actuator/loggers/com.example.orders.inventory"
~~~

Chỉ bật trong khoảng thời gian ngắn, theo dõi dung lượng log và kiểm tra code không ghi secret ở DEBUG. Nếu POST trả 403, kiểm tra security rule và CSRF policy; không tắt CSRF rộng chỉ để vượt qua lỗi.

### 11.3. Khôi phục log level

Có thể đặt lại level ban đầu:

~~~bash
curl -sS -X POST \
  -H "Authorization: Bearer $OPS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":null}' \
  "$ACTUATOR/actuator/loggers/com.example.orders.inventory"
~~~

Giá trị **null** bỏ cấu hình riêng của logger để dùng mức kế thừa từ logging framework. Nếu ban đầu logger được cấu hình rõ ràng trong file, đặt lại mức ban đầu thay vì xóa override.

Runtime log level thay đổi không phải cấu hình bền vững. Nó có thể mất khi restart và cần được khôi phục ngay sau điều tra.

## 12. Đọc log theo timeline và exception chain

### 12.1. Log mẫu trong incident

~~~text
2026-11-18T14:07:12.221Z ERROR
service=orders-service
pod=orders-service-abc123
traceId=4f8c2d9a
logger=com.example.orders.inventory.InventoryClient
message="Inventory health request failed"

java.net.UnknownHostException: inventroy.internal
    at java.net.InetAddress.getAllByName(...)
    at ...
~~~

Log này cho biết client không phân giải được hostname. Nó không giống:

| Exception hoặc kết quả | Hướng điều tra |
| --- | --- |
| **UnknownHostException** | Hostname, DNS record, search domain, resolver |
| **ConnectException: Connection refused** | Host đã phân giải nhưng port không có listener hoặc bị reject |
| **SocketTimeoutException** | Network path, latency, server quá tải, timeout quá ngắn |
| **SSLHandshakeException** | Certificate, truststore, hostname verification, TLS protocol |
| HTTP 401/403 | Credential, token scope, service authorization |
| HTTP 404 | Path, API version, route hoặc resource |
| HTTP 5xx | Dependency nhận request nhưng lỗi khi xử lý |
| No instances available | Service discovery, registration, service ID, zone/metadata |

### 12.2. Tìm cùng một request

Ưu tiên trace ID hoặc correlation ID để nối log giữa Orders và Inventory. Nếu không có trace ID, dùng timestamp, request path, pod và request ID do gateway cấp.

Không chỉ tìm theo từ khóa **ERROR**. Cần đọc exception chain, log trước lỗi và log của lần retry tiếp theo để phân biệt lỗi gốc với lỗi phát sinh sau đó.

### 12.3. Đồng bộ thời gian

Kiểm tra timestamp ở:

- Container log.
- Node.
- Centralized log collector.
- Config Server.
- Inventory service.
- Deployment controller.

Nếu clock skew lớn, một request có thể trông như xảy ra trước khi config rollout. Dùng UTC trong incident timeline nếu có thể.

### 12.4. Không log toàn bộ request hoặc Environment

Tránh log Authorization header, cookie, password, token, request body có dữ liệu cá nhân hoặc toàn bộ **Environment**. Log chẩn đoán nên giữ correlation ID, dependency name, host đã được làm sạch, thời gian và exception type.

## 13. Ghép bằng chứng và loại trừ giả thuyết

### 13.1. Ma trận bằng chứng

| Giả thuyết | Bằng chứng cần tìm | Kết quả mô phỏng | Kết luận |
| --- | --- | --- | --- |
| Inventory service down | Health của Inventory trực tiếp, log phía Inventory | Inventory health UP | Chưa ủng hộ |
| Discovery lỗi | conditions, Discovery health, service instance list | Discovery health UP; client dùng direct URL | Ít khả năng |
| Inventory Client không được tạo | conditions, bean/configprops | Condition matched; configprops có bean | Bác bỏ |
| Endpoint cấu hình sai | env, configprops, log DNS | Hostname inventroy.internal | Được xác nhận |
| Network policy chặn | TCP test từ đúng pod/namespace, timeout/refused | DNS lookup thất bại trước khi mở kết nối | Không phải giả thuyết đầu tiên |
| Credential sai | HTTP 401/403 và auth logs | Không có HTTP response | Bác bỏ |

### 13.2. Root cause

Config revision production đã ghi sai hostname tại **app.inventory.base-url**. Environment lấy giá trị từ Config Server; **InventoryProperties** bind đúng giá trị sai; điều kiện tạo Inventory Client vẫn match; health check không phân giải được hostname; log xác nhận **UnknownHostException**.

Root cause là lỗi nội dung cấu hình production, không phải Spring Cloud Discovery hoặc lỗi khởi tạo bean.

### 13.3. Vì sao cần cả bốn loại endpoint?

- Chỉ xem health sẽ biết Inventory DOWN nhưng chưa biết cấu hình nào sai.
- Chỉ xem env sẽ thấy hostname nhưng chưa biết bean đã bind nó chưa.
- Chỉ xem configprops sẽ biết giá trị bean nhưng chưa biết auto-configuration có match không.
- Chỉ xem conditions sẽ biết bean có được tạo nhưng không chứng minh dependency có thể kết nối.
- Log xác nhận lỗi ở runtime và nối sự kiện với request cụ thể.

Kết luận vững chắc xuất hiện khi các bằng chứng độc lập hỗ trợ cùng một nguyên nhân.

## 14. Quy trình xử lý incident theo từng bước

### Bước 1 — Xác định blast radius

Ghi số replica, profile, version, config revision, vùng/cluster và tỷ lệ lỗi. Xác định lỗi ảnh hưởng toàn service hay một subset.

### Bước 2 — Ổn định lưu lượng

Nếu readiness đã được thiết kế phù hợp, instance lỗi có thể bị loại khỏi traffic. Kiểm tra còn replica healthy hay không. Nếu tất cả replica đều unready, đánh giá fallback hoặc rollback cấu hình trước khi thực hiện thao tác làm giảm thêm capacity.

### Bước 3 — Thu thập health

Lấy global health, readiness và liveness từ từng replica. So sánh component DOWN, status code và thời điểm chuyển trạng thái.

### Bước 4 — Kiểm tra conditions

Xác nhận các bean quan trọng có được tạo. Nếu một auto-configuration không match, đọc reason và quay lại kiểm tra property, classpath hoặc bean thay thế.

### Bước 5 — Kiểm tra env

Tìm property nghi vấn, active profile, PropertySource và origin. Đối chiếu config revision. Nếu value bị sanitize, không mở rộng quyền xem secret chỉ để có dữ liệu.

### Bước 6 — Kiểm tra configprops

Xác nhận bean đã bind giá trị mong đợi và đúng kiểu. Nếu env/configprops khác nhau, kiểm tra thời điểm binding, constructor binding, refresh scope và custom binding.

### Bước 7 — Đọc log và tăng log có giới hạn

Tìm trace ID và exception chain. Nếu cần, tăng DEBUG cho package hẹp rồi khôi phục. Không bật DEBUG cho root logger hoặc toàn bộ Spring framework khi chưa có lý do.

### Bước 8 — Xác minh dependency từ đúng nơi chạy

Nếu lỗi DNS, kiểm tra hostname từ pod/namespace bị ảnh hưởng. Nếu lỗi TCP, kiểm tra port và network policy. Nếu lỗi TLS, kiểm tra certificate chain và hostname. Nếu lỗi HTTP, kiểm tra status và authentication.

### Bước 9 — Sửa nguồn cấu hình

Sửa Config Server repository/label hoặc nguồn thực sự sở hữu property. Review thay đổi, xác nhận profile và property precedence. Không chỉ sửa Environment tạm thời trên một replica.

### Bước 10 — Rollout có kiểm soát

Promotion config revision đã sửa. Restart/rollout từng nhóm instance nếu client hoặc resource đọc property lúc startup. Chỉ dùng Spring Cloud refresh khi bean và resource được thiết kế hỗ trợ.

### Bước 11 — Xác minh sau khôi phục

Trên từng replica, kiểm tra:

- Config revision mới.
- env và origin của property.
- configprops đã bind đúng.
- Conditions vẫn match theo mong đợi.
- Inventory health UP.
- Readiness ACCEPTING_TRAFFIC.
- Log không còn lỗi DNS.
- Tỷ lệ lỗi tạo đơn trở về baseline.

### Bước 12 — Đóng cửa sổ chẩn đoán

Khôi phục log level. Thu hồi quyền truy cập tạm thời. Đóng exposure bổ sung nếu đã mở. Lưu timeline và bằng chứng đã redact vào incident record.

## 15. Chọn refresh hay restart khi sửa cấu hình?

### 15.1. Khi nào refresh có thể phù hợp?

Spring Cloud Context có thể hỗ trợ cập nhật Environment, rebind một số mutable **@ConfigurationProperties** và refresh bean thuộc **@RefreshScope**. Điều này chỉ phù hợp nếu toàn bộ dependency/resource có lifecycle được thiết kế để nhận thay đổi.

Ví dụ, một bean giữ URL trong target của **@RefreshScope** có thể được tạo lại sau refresh. Tuy nhiên, một HTTP client hoặc connection pool được tạo ngoài scope vẫn có thể giữ cấu hình cũ.

### 15.2. Khi nào nên restart?

Chọn rolling restart khi:

- Bean dùng constructor binding hoặc record.
- Điều kiện **@ConditionalOnProperty** quyết định bean có tồn tại hay không.
- Cần thay bean graph hoặc auto-configuration.
- Client/resource không hỗ trợ refresh an toàn.
- Cần bảo đảm tất cả replica dùng cùng một config revision.
- Không xác định được chính xác refresh lifecycle.

### 15.3. Refresh không tạo lại bean bị loại bởi condition

Nếu **app.inventory.enabled=false** khiến Inventory Client không được đăng ký khi startup, thay property thành true và gọi refresh không đồng nghĩa auto-configuration sẽ được chạy lại để tạo bean mới.

Điều kiện bean creation được đánh giá trong quá trình tạo context. Trong tình huống này, sửa cấu hình và restart/rollout là phương án có thể kiểm chứng.

### 15.4. Không dùng POST /actuator/env làm source of truth

Spring Cloud có thể bật POST **/actuator/env** để cập nhật Environment, rebind **@ConfigurationProperties** và log levels. Đây là thao tác runtime, không tự ghi lại Config Server hoặc Git repository.

Nếu sửa giá trị trực tiếp trên một instance, các replica khác có thể vẫn giữ giá trị cũ và restart sẽ làm mất override. Với cấu hình do Config Server quản lý, sửa nguồn đó rồi promotion revision mới.

## 16. Kiểm tra dependency từ pod

### 16.1. DNS

Từ đúng pod hoặc một debug container cùng network namespace, kiểm tra hostname:

~~~bash
getent hosts inventory.internal
~~~

Trong incident, kiểm tra hostname đang dùng:

~~~bash
getent hosts inventroy.internal
~~~

Nếu công cụ **getent** không có trong image, dùng một debug container được tổ chức cho phép hoặc một lệnh DNS phù hợp với runtime. Không thêm package vào production container chỉ để điều tra.

### 16.2. TCP và TLS

Sau khi DNS resolve được, kiểm tra kết nối TCP tới port đúng. Nếu dùng HTTPS, kiểm tra certificate chain và hostname verification. Không tắt TLS verification như một cách workaround.

### 16.3. HTTP

Gọi health endpoint của Inventory từ môi trường Orders với timeout ngắn. Dùng credential test hoặc workload identity được cấp đúng scope. Không in token vào terminal history hoặc log.

### 16.4. So sánh với service discovery

Nếu client dùng DiscoveryClient/load balancer thay vì direct URL, kiểm tra:

- Service ID.
- DiscoveryClient bean và conditions.
- Danh sách instance được trả về.
- Health/status metadata.
- Zone/region và load-balancer filters.
- Registration/heartbeat của Inventory.

Không kết luận discovery hỏng chỉ vì một HTTP call không thành công. Nếu client đang dùng direct URL, discovery có thể không tham gia request path.

## 17. Kiểm thử hồi quy sau khi sửa

### 17.1. Test property binding

Tạo test xác nhận cấu hình production được bind thành đúng URI và Duration. Ví dụ:

~~~java
@SpringBootTest
class InventoryPropertiesTest {

    @Autowired
    InventoryProperties properties;

    @Test
    void bindsExpectedInventoryConfiguration() {
        assertThat(properties.enabled()).isTrue();
        assertThat(properties.baseUrl().toString())
                .isEqualTo("https://inventory.internal");
        assertThat(properties.timeout())
                .isEqualTo(Duration.ofMillis(800));
    }
}
~~~

Test này nên chạy với config fixture dành riêng cho test, không đọc credential hoặc cấu hình production thật.

### 17.2. Test condition match

Dùng **ApplicationContextRunner** hoặc integration test phù hợp với auto-configuration để xác nhận:

- Khi **app.inventory.enabled=true**, Inventory Client được tạo.
- Khi **false**, bean không được tạo.
- Khi property bị thiếu, hành vi khớp policy đã thiết kế.

Không chỉ kiểm tra Environment; kiểm tra bean presence thực tế.

### 17.3. Test health indicator

Mock Inventory Client để tạo hai trường hợp:

- **checkHealth()** thành công: component **inventory** trả UP.
- **checkHealth()** ném lỗi: component trả DOWN và không đưa secret hoặc full URL vào details.

### 17.4. Test readiness policy

Nếu Inventory là dependency bắt buộc, xác nhận readiness group bao gồm indicator. Nếu có fallback, xác nhận readiness không bị hạ chỉ vì Inventory tạm thời lỗi.

Không gộp kiểm tra liveness và dependency health vào cùng một nhóm.

### 17.5. Test config revision qua rollout

Trong staging:

1. Deploy artifact digest đã kiểm thử.
2. Promotion config revision đúng.
3. Khởi động ít nhất hai replica.
4. Kiểm tra revision và origin trên từng replica.
5. Gọi thử luồng tạo đơn.
6. Xác nhận health/readiness và log.
7. Thực hiện rollback thử để bảo đảm config revision cũ có thể phục hồi.

## 18. Bài tập điều tra

### Bài tập 1 — Tìm property sai

Cho dữ liệu:

~~~text
env:
  app.inventory.base-url = https://inventroy.internal
  source = configserver:orders-service-prod.yml

configprops:
  baseUrl = https://inventroy.internal

health:
  inventory = DOWN

log:
  UnknownHostException: inventroy.internal
~~~

Hãy viết root cause trong hai câu, chỉ ra bằng chứng quyết định và nguồn cần sửa.

### Bài tập 2 — Bean không được tạo

Cho dữ liệu:

~~~text
env:
  app.inventory.enabled = false

conditions:
  InventoryClientConfiguration did not match
  reason: expected true but property was false

configprops:
  InventoryProperties exists; InventoryClient bean is absent
~~~

Giải thích vì sao InventoryProperties vẫn có thể xuất hiện trong configprops trong khi InventoryClient không được tạo. Với HealthIndicator dùng ObjectProvider như ví dụ, health component inventory sẽ trả UNKNOWN vì client chưa được cấu hình. Giải thích vì sao chỉ gọi refresh không đảm bảo tạo lại bean.

### Bài tập 3 — Environment mới, bean cũ

Cho dữ liệu:

~~~text
env:
  app.inventory.base-url = https://inventory-v2.internal

configprops:
  baseUrl = https://inventory-v1.internal

log:
  request still targets inventory-v1.internal
~~~

Liệt kê ít nhất ba nguyên nhân có thể và cách phân biệt constructor binding, **@Value** singleton, **@RefreshScope** và resource được tạo từ cấu hình.

### Bài tập 4 — Network policy

Cho dữ liệu:

~~~text
env:
  app.inventory.base-url = https://inventory.internal

configprops:
  baseUrl = https://inventory.internal

conditions:
  InventoryClientConfiguration matched

health:
  inventory = DOWN
  cause = SocketTimeoutException
~~~

Lập kế hoạch kiểm tra DNS, TCP, TLS, NetworkPolicy và thời gian phản hồi từ đúng pod.

### Bài tập 5 — Credential sai

Cho dữ liệu:

~~~text
health:
  inventory = DOWN
  cause = HttpClientErrorException$Unauthorized

log:
  HTTP 401 from inventory
~~~

Giải thích vì sao endpoint và DNS có thể đúng nhưng request vẫn thất bại. Đề xuất cách kiểm tra token scope và rotation mà không log secret.

### Bài tập 6 — Replica không đồng nhất

Replica A có config revision 42 và endpoint đúng. Replica B có revision 41 và endpoint cũ. Hãy xác định các bước kiểm tra rollout, Config Server label, active profile và thời điểm restart.

### Bài tập 7 — Conditions không match

Một auto-configuration không match vì class dependency không có trên classpath. Hãy phân biệt lỗi dependency/build với lỗi property trong Environment. Đề xuất kiểm tra dependency management và condition report.

### Bài tập 8 — Health DOWN nhưng liveness UP

Giải thích tại sao đây có thể là trạng thái mong muốn khi dependency nghiệp vụ lỗi. Nêu điều kiện để Inventory được thêm vào readiness và trường hợp nên để circuit breaker/fallback xử lý.

### Bài tập 9 — Log level tạm thời

Tăng DEBUG cho package **com.example.orders.inventory**, thu thập một request lỗi, sau đó reset về mức cũ. Viết checklist để bảo đảm không bật DEBUG root hoặc để lại cấu hình runtime.

### Bài tập 10 — Viết incident report

Tạo incident report gồm:

- Tác động.
- Timeline.
- Root cause.
- Bằng chứng env/configprops/conditions/health/log.
- Cách khôi phục.
- Kiểm thử sau khôi phục.
- Hành động ngăn tái diễn.
- Owner và deadline.

## 19. Runbook rút gọn

| Thứ tự | Việc cần làm | Bằng chứng cần lưu |
| --- | --- | --- |
| 1 | Xác định service, pod, profile, version, config revision | Incident metadata |
| 2 | Thu thập readiness/liveness từng replica | Health JSON và timestamp |
| 3 | Kiểm tra component DOWN | Health component details |
| 4 | Kiểm tra bean/auto-config | Conditions report |
| 5 | Kiểm tra property source và origin | Env property result đã redact |
| 6 | Kiểm tra typed binding | Configprops đã redact |
| 7 | Tìm request và exception | Trace ID, log lines |
| 8 | Tăng log có giới hạn nếu cần | Logger level trước/sau |
| 9 | Xác minh DNS/TCP/TLS/HTTP từ đúng pod | Kết quả probe |
| 10 | Sửa source of truth | Config commit/revision |
| 11 | Rollout và xác minh từng replica | Revision, health, smoke test |
| 12 | Khôi phục log/security policy | Logger level và endpoint access |

### 19.1. Mẫu ghi nhận bằng chứng

~~~text
Incident ID:
Service:
Application version:
Spring Boot version:
Spring Cloud release train:
Cluster / namespace:
Pod:
Active profiles:
Config revision:
Timestamp UTC:
Trace ID:

ENV:
Property:
Effective value (redacted if needed):
PropertySource:
Origin:

CONFIGPROPS:
Bean:
Prefix:
Bound value:
Type:

CONDITIONS:
Configuration class:
Matched / did not match:
Reason:

HEALTH:
Global status:
Readiness:
Liveness:
Failed component:
Details (sanitized):

LOG:
Logger:
Exception:
Root cause:
First seen:
Last seen:

CONCLUSION:
Confirmed cause:
Evidence:
Remediation:
Verification:
Rollback plan:
~~~

## 20. Checklist trước khi kết thúc incident

### Phạm vi và bằng chứng

- [ ] Đã xác định chính xác pod/instance và config revision.
- [ ] Đã ghi active profile và application version.
- [ ] Đã đọc health/readiness/liveness của từng replica.
- [ ] Đã đối chiếu env với configprops.
- [ ] Đã đọc conditions để xác nhận bean/auto-configuration.
- [ ] Đã ghép log bằng trace ID hoặc correlation ID.
- [ ] Đã xác minh dependency từ đúng network namespace.

### Kết luận và khôi phục

- [ ] Root cause được hỗ trợ bởi nhiều nguồn bằng chứng độc lập.
- [ ] Sửa đúng nguồn cấu hình sở hữu property.
- [ ] Config revision đã được review và ghi nhận.
- [ ] Rollout/restart phù hợp lifecycle bean và resource.
- [ ] Từng replica đã dùng revision đúng.
- [ ] Smoke test nghiệp vụ thành công.
- [ ] Health và readiness trở lại trạng thái mong đợi.
- [ ] Log không còn lỗi gốc.

### Bảo mật và vận hành

- [ ] Không lưu token, password hoặc private key trong incident attachment.
- [ ] env/configprops đã được redact.
- [ ] Health details không chứa dữ liệu nhạy cảm.
- [ ] DEBUG chỉ bật ở package cần thiết và đã được reset.
- [ ] Actuator exposure/access trở về policy chuẩn.
- [ ] Không để lại POST /actuator/env hoặc quyền ghi loggers ngoài yêu cầu.
- [ ] Readiness không kiểm tra external dependency tùy chọn.
- [ ] Liveness không phụ thuộc external service.
- [ ] Có action item và owner cho nguyên nhân gốc.

## 21. Ghi nhớ và nguồn tra cứu

- **env** cho biết property trong Environment và PropertySource; dùng origin để tìm nguồn sở hữu giá trị.
- **configprops** cho biết giá trị đã bind vào object có kiểu; nó giúp phát hiện khác biệt giữa Environment và bean.
- **conditions** cho biết auto-configuration hoặc configuration class match/non-match và lý do.
- **health** cho biết trạng thái component; DOWN là tín hiệu cần điều tra, không phải root cause.
- **readiness** quyết định instance có nên nhận traffic; **liveness** quyết định process có còn trạng thái nội tại hợp lệ.
- Không đưa dependency bên ngoài vào liveness; chỉ đưa vào readiness khi nghiệp vụ thực sự không thể phục vụ nếu dependency đó lỗi.
- **loggers** có thể xem configured/effective level và thay đổi runtime; chỉ bật DEBUG ở package hẹp, trong thời gian ngắn.
- Spring Boot mặc định chỉ expose health qua HTTP. Mở thêm endpoint phải đi kèm network isolation, authentication, authorization và sanitization.
- Giá trị env/configprops được sanitize mặc định; không bật show-values=always trong production.
- Nếu bean condition không match tại startup, refresh Environment không đảm bảo tạo lại bean definition. Cần chọn restart/rollout khi cấu trúc bean phải thay đổi.
- Khi sửa cấu hình từ Config Server, cập nhật source of truth và promotion revision; tránh override tạm thời chỉ trên một replica.
- Mọi kết luận phải gắn với instance, profile, version, config revision và timestamp cụ thể.

Tài liệu chính thức:

1. [Spring Boot 4.1 – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
2. [Spring Boot 4.1 – Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)
3. [Spring Boot 4.1 – Loggers Endpoint](https://docs.spring.io/spring-boot/reference/actuator/loggers.html)
4. [Spring Boot 4.1 – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
5. [Spring Boot 4.1 – SpringApplication and Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
6. [Spring Boot 4.1 – Health REST API](https://docs.spring.io/spring-boot/api/rest/actuator/health.html)
7. [Spring Cloud Commons – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
8. [Spring Cloud Config – Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
9. [Spring Cloud – Release train và tương thích Spring Boot](https://spring.io/projects/spring-cloud/)

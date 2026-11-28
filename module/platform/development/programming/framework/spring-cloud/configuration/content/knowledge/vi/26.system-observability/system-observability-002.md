# Phân biệt ứng dụng đang sống với cấu hình đã được nạp thành công

## 1. Một process đang chạy chưa chắc đã sẵn sàng phục vụ

Trong hệ thống Spring Cloud Config, ứng dụng Spring Boot có thể khởi động thành công về mặt JVM nhưng chưa có đủ cấu hình để xử lý nghiệp vụ. Ngược lại, một ứng dụng đã nạp và kiểm tra cấu hình hợp lệ có thể tiếp tục phục vụ bằng cấu hình hiện có dù Config Server tạm thời mất kết nối.

Vì vậy cần tách ba câu hỏi:

1. **Liveness**: process còn sống và có khả năng tiếp tục hoạt động không?
2. **Configuration state**: ứng dụng đã nạp được cấu hình cần thiết và xác nhận các giá trị hợp lệ chưa?
3. **Readiness**: instance có đủ điều kiện nhận traffic tại thời điểm này không?

Ba trạng thái có liên quan nhưng không đồng nghĩa. Nếu dùng một health check duy nhất để trả lời cả ba câu hỏi, hệ thống có thể restart hàng loạt khi Config Server gặp sự cố, hoặc đưa một instance thiếu cấu hình vào load balancer.

## 2. Liveness, readiness và startup probe

Spring Boot Actuator cung cấp các health group cho Kubernetes:

| Trạng thái/probe | Câu hỏi | Hành động của nền tảng |
|---|---|---|
| Liveness | Ứng dụng có còn chạy và tự tiến triển được không? | Nếu thất bại liên tục, nền tảng có thể restart container. |
| Readiness | Ứng dụng có thể nhận và xử lý traffic an toàn không? | Nếu thất bại, Pod bị loại khỏi Service endpoints cho đến khi sẵn sàng. |
| Startup | Ứng dụng đã hoàn thành khởi tạo ban đầu chưa? | Trong khi startup probe chưa thành công, liveness/readiness chưa được dùng để kết luận container cần restart hoặc nhận traffic. |

Liveness nên phản ánh tình trạng nội tại của process: event loop/thread pool có còn hoạt động, ứng dụng có bị deadlock hoặc mắc kẹt không. Nó không nên phụ thuộc trực tiếp vào Config Server, Consul, database, broker hay dịch vụ bên ngoài.

Readiness phản ánh khả năng phục vụ. Nếu ứng dụng bắt buộc phải có `orders.max-items` và `orders.timeout` hợp lệ trước khi xử lý request, readiness cần ở trạng thái chưa sẵn sàng cho đến khi cấu hình đó được nạp và validation thành công.

Startup probe dành cho ứng dụng khởi động lâu, chẳng hạn phải nạp cấu hình từ xa, tạo cache ban đầu hoặc khởi tạo tài nguyên. Nó giúp Kubernetes không kết luận liveness thất bại quá sớm trong thời gian khởi động được cho phép.

## 3. Vì sao không nên đưa Config Server vào liveness?

Giả sử 30 instance `order-service` đang hoạt động. Config Server mất kết nối trong 20 giây nhưng các instance vẫn giữ cấu hình hợp lệ trong Spring `Environment` và vẫn truy cập được database.

Nếu liveness gọi Config Server để kiểm tra:

1. Config Server mất kết nối.
2. Liveness của 30 instance cùng thất bại.
3. Kubernetes restart các container.
4. Các instance mới cùng bootstrap và gọi Config Server.
5. Config Server vừa phục hồi phải xử lý thêm một đợt request lớn.

Health check đã biến một sự cố phụ thuộc ngắn thành restart storm. Khi Config Server phục hồi, chính các lần restart do liveness tạo ra có thể tiếp tục làm quá tải hệ thống.

Với liveness, chỉ kiểm tra những điều kiện mà process có thể tự khắc phục bằng restart. Nếu Config Server hoặc Consul tạm thời unavailable nhưng ứng dụng vẫn có cấu hình hợp lệ, việc restart process thường không giải quyết được nguyên nhân.

## 4. Cấu hình đã được nạp thành công nghĩa là gì?

Không nên chỉ kiểm tra một cờ boolean kiểu `configLoaded=true`. Trạng thái cấu hình nên thể hiện ít nhất:

- Nguồn cấu hình đã được truy cập hoặc nguồn dự phòng đã được chọn.
- Các property bắt buộc đã tồn tại.
- Kiểu dữ liệu và miền giá trị đã được validation.
- Ứng dụng đang dùng application name, profile và label/revision dự kiến.
- Thời điểm nạp thành công gần nhất.
- Lần refresh gần nhất thành công hay thất bại.
- Nếu dùng fallback/last-known-good, ứng dụng đang ở chế độ nào và snapshot có còn được phép sử dụng không.

Ví dụ một snapshot trạng thái an toàn để quan sát:

```json
{
  "loaded": true,
  "valid": true,
  "source": "spring-cloud-config",
  "application": "order-service",
  "profiles": ["prod"],
  "label": "release-2026-11",
  "revision": "8b4c1f2",
  "loadedAt": "2026-11-27T09:30:00Z",
  "lastRefresh": "SUCCESS",
  "mode": "REMOTE"
}
```

Đây là metadata trạng thái, không phải nội dung property. Không đưa password, token, private key hoặc giá trị cấu hình nhạy cảm vào health response.

## 5. Config Data import bắt buộc và tùy chọn

Với Spring Boot Config Data, Config Client có thể khai báo nguồn Config Server bằng `spring.config.import`.

### Nguồn bắt buộc

```yaml
spring:
  config:
    import: "configserver:https://config.internal"
```

Khi import bắt buộc không thể được xử lý, quá trình khởi động có thể thất bại. Đây là lựa chọn phù hợp khi thiếu cấu hình trung tâm khiến ứng dụng không thể hoạt động an toàn.

Nếu ứng dụng không hoàn thành khởi động, Actuator server có thể chưa mở cổng HTTP để Kubernetes gọi health endpoint. Startup probe không thể làm cho một Config Data import bắt buộc thành công khi Config Server vẫn unavailable.

### Nguồn tùy chọn

```yaml
spring:
  config:
    import: "optional:configserver:https://config.internal"
```

`optional:` cho phép ứng dụng tiếp tục xử lý các nguồn cấu hình khác khi Config Server không sẵn sàng theo quy tắc Config Data. Nó không tự chứng minh ứng dụng đã có đủ property để chạy.

Nếu ứng dụng cần `orders.max-items` nhưng không có trong file local hoặc nguồn khác, việc import tùy chọn có thể khiến thiếu cấu hình chỉ được phát hiện ở bước binding/validation hoặc lúc nghiệp vụ sử dụng. Do đó, cần kiểm tra property bắt buộc trước khi readiness chuyển sang `UP`.

## 6. Validation giúp phân biệt “đã tải” với “đã dùng được”

Một phản hồi Config Server thành công chưa bảo đảm giá trị phù hợp với ứng dụng. YAML có thể hợp lệ nhưng thiếu khóa; một giá trị số có thể nằm ngoài miền cho phép; endpoint có thể trả nhầm profile hoặc label.

Dùng `@ConfigurationProperties` cùng Jakarta Bean Validation để kiểm tra cấu hình lúc bind:

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.time.Duration;

@Validated
@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(
        @NotNull Duration requestTimeout,
        @Min(1) int maxItemsPerRequest) {
}
```

Nếu `orders.request-timeout` thiếu hoặc `orders.max-items-per-request` nhỏ hơn 1, binding/validation phải báo lỗi theo cấu hình ứng dụng. Có thể đăng ký properties bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

Validation nên tập trung vào các giá trị ảnh hưởng đến việc phục vụ request: endpoint, timeout, giới hạn, mode, tên schema hoặc feature policy. Tránh kiểm tra bằng cách in toàn bộ Environment vì có thể làm lộ secret.

## 7. Theo dõi trạng thái cấu hình bằng health indicator riêng

Spring Boot cho phép tạo `HealthIndicator` tùy chỉnh. Với cấu hình từ xa, indicator nên đọc **trạng thái snapshot cục bộ** do thành phần nạp/validate cấu hình cập nhật, thay vì gọi Config Server mỗi lần Kubernetes hỏi readiness.

Ví dụ cấu trúc:

```java
import java.time.Instant;

public record ConfigSnapshot(
        boolean loaded,
        boolean valid,
        String revision,
        Instant loadedAt,
        String mode,
        String reasonCode) {
}
```

Health indicator:

```java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("configuration")
public class ConfigurationHealthIndicator implements HealthIndicator {

    private final ConfigState configState;

    public ConfigurationHealthIndicator(ConfigState configState) {
        this.configState = configState;
    }

    @Override
    public Health health() {
        ConfigSnapshot snapshot = configState.current();

        if (snapshot == null || !snapshot.loaded() || !snapshot.valid()) {
            return Health.down()
                    .withDetail("reason", snapshot == null
                            ? "not-loaded" : snapshot.reasonCode())
                    .build();
        }

        return Health.up()
                .withDetail("mode", snapshot.mode())
                .withDetail("revision", snapshot.revision())
                .withDetail("loadedAt", snapshot.loadedAt())
                .build();
    }
}
```

`ConfigState` là thành phần do ứng dụng quản lý, lưu snapshot mới nhất sau khi quá trình nạp và validation hoàn tất. Mã minh họa giả định `current()` trả snapshot an toàn khi nhiều thread cùng đọc; có thể dùng `AtomicReference<ConfigSnapshot>` để cập nhật snapshot nguyên tử.

Không đặt URL có credential, token, password, exception message chứa response body hoặc giá trị property vào `Health` details. Chỉ trả metadata đã được cho phép công khai.

## 8. Đưa configuration state vào readiness group

Ví dụ bật health probes và thêm health indicator `configuration` vào readiness:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      group:
        readiness:
          include: readinessState,configuration
```

Khi bật probes, Spring Boot cung cấp các nhóm `liveness` và `readiness`. Với `add-additional-paths: true`, các path `/livez` và `/readyz` có thể được expose trên cổng HTTP chính của ứng dụng, thuận tiện cho Kubernetes probe mà không cần đi qua management port riêng.

Ví dụ cấu hình liveness mặc định nên chỉ dựa vào trạng thái liveness của process. Readiness group bao gồm readiness state của Spring Boot và health indicator cấu hình. Nếu configuration indicator trả `DOWN`, readiness group không `UP`, vì thế instance không nhận traffic.

Không đưa `configServer` health indicator vào readiness một cách máy móc. Nếu Config Server mất kết nối sau khi ứng dụng đã nạp cấu hình hợp lệ, readiness không nhất thiết phải xuống. Chỉ đưa dependency vào readiness nếu instance thực sự không thể phục vụ request khi dependency đó unavailable.

## 9. Trạng thái cấu hình nên có nhiều mức

Trong production, một trạng thái nhị phân có thể không đủ. Có thể mô hình hóa các trạng thái:

| Trạng thái | Ý nghĩa | Readiness gợi ý |
|---|---|---|
| `NOT_LOADED` | Chưa nạp được nguồn cấu hình hoặc chưa hoàn thành bootstrap. | `DOWN` |
| `VALIDATING` | Đang kiểm tra property bắt buộc và miền giá trị. | `DOWN` |
| `READY_REMOTE` | Đã nạp và validate cấu hình remote hiện hành. | `UP` |
| `READY_FALLBACK` | Đang dùng cấu hình local/last-known-good được cho phép. | `UP` hoặc `DEGRADED` tùy policy |
| `REFRESH_FAILED_USING_OLD` | Lần refresh thất bại nhưng snapshot trước vẫn hợp lệ. | Có thể tiếp tục `UP`, đồng thời cảnh báo |
| `INVALID_NEW_CONFIG` | Cấu hình mới không qua validation. | Giữ snapshot cũ nếu rollback được; không áp dụng snapshot lỗi |
| `STALE_EXPIRED` | Snapshot cũ vượt quá tuổi tối đa được policy cho phép. | `DOWN` hoặc `OUT_OF_SERVICE` |

Readiness là quyết định nghiệp vụ/vận hành. Ví dụ một dịch vụ đọc catalog có thể tiếp tục với snapshot cấu hình cũ trong 15 phút; một dịch vụ xử lý quyền truy cập hoặc credential rotation có thể cần dừng nhận traffic ngay khi không xác nhận được policy mới.

Hãy xác định rõ freshness policy cho từng nhóm cấu hình. Không áp dụng một ngưỡng stale chung cho timeout, feature flag, authorization policy và secret.

## 10. Config Server down sau startup không đồng nghĩa config client chưa sẵn sàng

Giả sử `order-service` đã:

- Lấy cấu hình từ `main` hoặc tag release.
- Bind thành công `OrdersProperties`.
- Tạo các bean cần thiết.
- Kết nối database và dependency phục vụ request.

Sau đó Config Server mất kết nối. Ứng dụng vẫn có thể xử lý request bằng `Environment` đã nạp trong bộ nhớ. Nếu readiness được định nghĩa là “Config Server phải trả lời ngay tại mọi thời điểm”, toàn bộ instance có thể bị loại khỏi traffic dù chúng vẫn hoạt động đúng.

Chính sách phù hợp thường là:

- Readiness dựa vào snapshot cấu hình hiện tại có tồn tại và còn hợp lệ không.
- Theo dõi riêng khả năng kết nối Config Server và tuổi lần refresh thành công.
- Nếu snapshot vượt freshness limit hoặc thay đổi bảo mật bắt buộc chưa được áp dụng, chuyển readiness xuống theo policy.
- Khi Config Server phục hồi, refresh một cách có kiểm soát rồi xác nhận giá trị mới.

Điều này tách “khả năng phục vụ bằng cấu hình đã nạp” khỏi “khả năng lấy cấu hình mới ngay lúc này”. Hai chỉ số đều quan trọng nhưng phục vụ quyết định khác nhau.

## 11. Phân biệt health của Config Server và readiness của Config Client

Hai endpoint nằm ở hai tiến trình khác nhau:

| Endpoint | Trả lời câu hỏi |
|---|---|
| Config Server `/actuator/health` | Server có hoạt động và các thành phần mà health indicator của server kiểm tra có ổn không? |
| Config Client `/actuator/health/liveness` | Process client có còn sống không? |
| Config Client `/actuator/health/readiness` | Instance client có đủ điều kiện nhận traffic không? |
| Config Client custom `configuration` indicator | Cấu hình cục bộ đã nạp và validate thành công chưa? |

Config Server health `UP` không chứng minh một client đã lấy đúng application/profile/label. Tương tự, Config Server health `DOWN` không nhất thiết có nghĩa các client đã nạp cấu hình trước đó phải dừng phục vụ ngay lập tức.

Với Config Server dùng Git backend, có thể cấu hình health check repository riêng. Tuy nhiên, việc kiểm tra repository cũng có thể tạo request hoặc phụ thuộc cache. Hãy phân biệt health của server, health của Git backend và trạng thái config snapshot trong từng client.

## 12. Kiểm tra revision, profile và nguồn cấu hình

Một client có thể tải thành công nhưng nhận nhầm profile hoặc label. Ví dụ ứng dụng production vô tình active `dev`, hoặc label trỏ đến tag cũ.

Nên ghi nhận các metadata sau sau mỗi lần nạp:

- `spring.application.name`.
- Danh sách active profiles.
- Config Server URI/cluster identifier, không kèm credential.
- Label/branch/tag yêu cầu.
- Revision/commit SHA trả về nếu có.
- Thời điểm tải thành công và thời điểm refresh gần nhất.
- Chế độ `REMOTE`, `LOCAL_FALLBACK` hoặc `LAST_KNOWN_GOOD`.
- Kết quả validation và số lượng property bắt buộc đã kiểm tra.

Config Server Environment response có thể chứa `name`, `profiles`, `label`, `version`, `state` và `propertySources`. Ứng dụng có thể dùng metadata revision/label được nền tảng cung cấp để hiển thị trạng thái, nhưng không nên ghi toàn bộ property source vào log.

## 13. Cấu hình Kubernetes probes

Ví dụ Deployment:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 60
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
```

Các con số là ví dụ cho ứng dụng có startup tương đối dài. `failureThreshold × periodSeconds` xác định khoảng thời gian probe có thể thất bại trước khi Kubernetes áp dụng hành động tương ứng; cần tính cả timeout và thời gian khởi tạo thực tế.

Nếu ứng dụng không thể mở web server cho đến khi Config Data import bắt buộc thành công, startup probe không thể truy cập endpoint trong lúc đó. Khi ấy phải cấu hình retry/deadline ở Config Client và thời gian khởi động của container phù hợp. Probe không thay thế retry policy.

## 14. Xử lý refresh thất bại sau khi ứng dụng đã sẵn sàng

Khi Config Server có revision mới nhưng client refresh thất bại, cần tránh đánh đồng lỗi refresh với process chết.

Một quy trình an toàn:

1. Giữ snapshot cấu hình đang dùng nếu nó vẫn hợp lệ và chưa hết thời hạn cho phép.
2. Ghi nhận `lastRefresh=FAILED`, thời điểm, revision đang dùng và mã lỗi đã được lọc secret.
3. Phát cảnh báo nếu quá thời gian freshness policy.
4. Retry refresh có giới hạn, backoff và jitter; không broadcast liên tục.
5. Khi tải cấu hình mới, validate trước khi thay snapshot đang dùng.
6. Chỉ chuyển sang revision mới sau khi validation thành công và các bean/tài nguyên có thể áp dụng an toàn.
7. Nếu refresh thất bại hoặc cấu hình mới không hợp lệ, tiếp tục dùng snapshot cũ trong giới hạn policy hoặc chuyển readiness xuống.

Không mặc định rằng mọi cơ chế refresh của framework cung cấp transaction toàn cục hoặc rollback tự động cho mọi bean. Với ứng dụng cần bảo đảm mạnh, thiết kế bước validate và chuyển đổi cấu hình rõ ràng; một số thay đổi vẫn cần restart/rollout.

## 15. Không để health endpoint làm lộ cấu hình

Actuator `env`, `configprops` và health details có thể tiết lộ thông tin về property source, endpoint nội bộ hoặc cấu hình nhạy cảm nếu expose không đúng cách.

Khuyến nghị:

- Chỉ expose `health`, `info` và các endpoint thực sự cần.
- Không expose `env` hoặc `configprops` công khai.
- Dùng `show-details: when-authorized` nếu cần health detail.
- Trả revision, profile và timestamp đã được cho phép; không trả property value.
- Bảo vệ management endpoint bằng authentication/authorization và network policy.
- Không ghi response Config Server hoặc toàn bộ Spring `Environment` vào log.

Ví dụ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: when-authorized
```

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Process sống nhưng nhận request rồi lỗi thiếu property | Liveness chỉ kiểm tra JVM; chưa kiểm tra cấu hình bắt buộc. | Thêm binding/validation và configuration health indicator vào readiness. |
| Pod restart hàng loạt khi Config Server down | Liveness gọi Config Server hoặc dependency bên ngoài. | Chỉ dùng liveness cho trạng thái nội tại; theo dõi config availability riêng. |
| Optional import khiến app lên nhưng readiness vẫn UP dù thiếu property | Chưa có validation/config state indicator. | Đánh dấu chưa sẵn sàng đến khi property bắt buộc hợp lệ. |
| Config Server health UP nhưng client dùng profile sai | Health server không xác nhận request cụ thể của client. | Kiểm tra application/profile/label/revision trong client metadata. |
| Config Server down nhưng instance cũ vẫn phục vụ | Instance giữ snapshot trong memory. | Có thể hợp lệ; áp dụng freshness policy và theo dõi last successful load. |
| Refresh thất bại làm readiness DOWN ngay | Health gắn trực tiếp vào lần kết nối Config Server hiện tại. | Dựa vào snapshot đang dùng và policy stale; tách refresh health khỏi serving readiness. |
| Readiness UP dù config mới không hợp lệ | Health indicator chỉ kiểm tra đã tải, không kiểm tra validation. | Validate trước khi đánh dấu snapshot hợp lệ. |
| Health endpoint lộ nội dung cấu hình | Expose `env`, `configprops` hoặc health details quá rộng. | Giới hạn endpoint và lọc metadata. |
| Startup probe không giúp app khởi động | Config Data import bắt buộc fail trước khi web server mở cổng. | Cấu hình retry/deadline hoặc fallback có chủ ý; probe không thể sửa bootstrap failure. |

## 17. Checklist quan sát production

- [ ] Liveness không phụ thuộc trực tiếp Config Server, Consul, database hoặc broker.
- [ ] Startup probe có ngân sách thời gian tương thích với bootstrap/retry.
- [ ] Readiness chỉ chuyển UP sau khi cấu hình bắt buộc đã bind và validate.
- [ ] Optional import có fallback rõ ràng và validation cho property bắt buộc.
- [ ] Configuration state ghi nhận source, profile, label/revision và thời điểm nạp.
- [ ] Config Server availability và client config readiness được đo riêng.
- [ ] Refresh failure không tự động làm process restart nếu snapshot cũ còn hợp lệ.
- [ ] Có freshness policy riêng cho cấu hình thông thường, policy bảo mật và secret.
- [ ] Cấu hình mới được validate trước khi áp dụng vào bean/tài nguyên.
- [ ] Health endpoint không trả secret hoặc property values.
- [ ] Có alert cho missing config, invalid config, stale snapshot, refresh failure và sai revision.
- [ ] Có diễn tập Config Server unavailable lúc startup và sau startup.

## 18. Bài thực hành

### Bước 1: Tạo ứng dụng có cấu hình bắt buộc

Khai báo `OrdersProperties` với `requestTimeout` và `maxItemsPerRequest`, bật validation. Chạy ứng dụng khi Config Server hoạt động và khi thiếu một property.

**Kết quả cần đạt:** xác nhận ứng dụng không đánh dấu cấu hình hợp lệ nếu thiếu khóa bắt buộc.

### Bước 2: So sánh required và optional import

Tắt Config Server, chạy lần lượt `configserver:` và `optional:configserver:`. Quan sát startup behavior và xác minh optional không tự bổ sung giá trị còn thiếu.

**Kết quả cần đạt:** phân biệt import policy với config validation.

### Bước 3: Thêm configuration health indicator

Tạo `ConfigState` lưu `loaded`, `valid`, `revision`, `loadedAt` và `mode`. Tạo `HealthIndicator` đọc snapshot cục bộ, không gọi Config Server mỗi lần probe.

**Kết quả cần đạt:** readiness phản ánh cấu hình đã nạp và hợp lệ.

### Bước 4: Cấu hình health groups

Bật Actuator probes, thêm `configuration` vào readiness và giữ liveness chỉ dựa trên `livenessState`. Gọi `/actuator/health/liveness` và `/actuator/health/readiness`.

**Kết quả cần đạt:** khi config thiếu, readiness DOWN nhưng liveness vẫn UP.

### Bước 5: Mô phỏng outage sau startup

Khởi động với cấu hình hợp lệ, sau đó dừng Config Server. Kiểm tra instance vẫn phục vụ bằng snapshot hiện tại và theo dõi refresh failure riêng.

**Kết quả cần đạt:** tránh restart instance chỉ vì Config Server tạm thời unavailable.

### Bước 6: Mô phỏng cấu hình mới không hợp lệ

Đẩy một revision có giá trị ngoài miền validation. Thử refresh và xác minh ứng dụng không đánh dấu snapshot mới là hợp lệ; kiểm tra policy tiếp tục dùng snapshot cũ hoặc chuyển readiness xuống.

**Kết quả cần đạt:** phân biệt tải thành công với cấu hình hợp lệ và được áp dụng an toàn.

### Bước 7: Kiểm tra Kubernetes probes

Triển khai startup/readiness/liveness probes trong cluster lab. Tạm dừng Config Server và quan sát Pod có bị restart hàng loạt hay chỉ mất readiness theo policy.

**Kết quả cần đạt:** probe được dùng đúng mục đích và không tạo restart storm.

## 19. Tự kiểm tra

1. Liveness khác readiness ở câu hỏi nào?
2. Vì sao không nên gọi Config Server trong liveness probe?
3. Một process đang chạy có thể chưa sẵn sàng nhận traffic trong trường hợp nào?
4. `configserver:` khác `optional:configserver:` ra sao?
5. Vì sao optional import không bảo đảm cấu hình đã đầy đủ?
6. `@ConfigurationProperties` validation giúp phát hiện lỗi gì?
7. Configuration health indicator nên đọc trạng thái nào và vì sao không nên gọi remote server mỗi lần probe?
8. Khi Config Server down sau startup, khi nào instance vẫn có thể readiness UP?
9. Khi nào stale configuration phải làm readiness DOWN?
10. Config Server health khác Config Client readiness như thế nào?
11. Vì sao startup probe không giải quyết được lỗi Config Data import bắt buộc trước khi HTTP server mở cổng?
12. Cần theo dõi metadata nào để xác nhận đúng application/profile/label/revision?
13. Làm thế nào xử lý refresh thất bại mà không restart hàng loạt instance?
14. Vì sao health endpoint không nên trả property values hoặc secret?

Khi hoàn thành bài thực hành, người học có thể tách biệt process liveness, trạng thái nạp/validation cấu hình và readiness nhận traffic; thiết kế health indicator phản ánh snapshot cấu hình thực tế; đồng thời tránh restart storm khi Config Server tạm thời không sẵn sàng.

## Tài liệu tham khảo

- [Spring Boot – Actuator: Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): liveness, readiness, startup và health groups.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): Config Data import và nguồn cấu hình bên ngoài.
- [Spring Boot – Configuration Metadata and Validation](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation): bind và validate `@ConfigurationProperties`.
- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import, fail-fast và cấu hình client.
- [Kubernetes – Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/): hành vi kubelet khi probe thành công/thất bại.

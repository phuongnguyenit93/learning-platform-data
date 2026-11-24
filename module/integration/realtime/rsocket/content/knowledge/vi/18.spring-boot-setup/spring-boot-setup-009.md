# Quản lý cấu hình môi trường, địa chỉ dịch vụ và thông tin bí mật

Ứng dụng RSocket thường chạy ở nhiều môi trường như máy cá nhân, kiểm thử, staging và production. Mỗi môi trường có thể dùng địa chỉ server, cổng, transport, timeout, giới hạn tài nguyên và thông tin xác thực khác nhau. Nếu các giá trị này được ghi trực tiếp trong source code hoặc rải rác trong nhiều service, việc triển khai dễ sai cấu hình và có nguy cơ làm lộ thông tin bí mật.

Spring Boot cung cấp externalized configuration để tách cấu hình khỏi code. Ứng dụng đọc giá trị từ `application.yml`, profile, biến môi trường, system property, command line hoặc nguồn cấu hình ngoài. `@ConfigurationProperties` gom các giá trị liên quan thành một kiểu Java có thể kiểm tra và validate khi khởi động. Với RSocket, cách làm này giúp quản lý địa chỉ TCP/WebSocket, cấu hình server, endpoint của service khác, timeout và giới hạn payload một cách nhất quán.

## 1. Vì sao cần tách cấu hình khỏi source code?

Một ứng dụng realtime có thể giữ nhiều kết nối và stream trong thời gian dài. Thay đổi địa chỉ server hoặc credential thường là việc triển khai/vận hành, không phải thay đổi logic nghiệp vụ. Tách cấu hình giúp:

- Dùng cùng một artifact cho nhiều môi trường, chỉ thay đổi giá trị cấu hình.
- Đổi địa chỉ service mà không sửa và build lại code.
- Quản lý TCP hoặc WebSocket theo từng môi trường.
- Đặt timeout, giới hạn payload và concurrency theo năng lực hạ tầng.
- Lưu thông tin xác thực trong secret store hoặc nguồn được bảo vệ.
- Validate cấu hình sớm để ứng dụng thất bại ngay khi khởi động nếu endpoint sai hoặc thiếu trường bắt buộc.
- Kiểm tra và audit thay đổi cấu hình mà không phải đọc diff của logic nghiệp vụ.

Ví dụ, cùng một service `device-gateway` có thể chạy ở local với `localhost:7000`, ở staging với DNS nội bộ và ở production với địa chỉ service trong cluster. Handler `devices.status` và `DeviceService` không cần biết địa chỉ nào đang được sử dụng.

## 2. Các nguồn cấu hình của Spring Boot

Spring Boot tổng hợp cấu hình từ nhiều nguồn. Các nguồn có thứ tự ưu tiên; giá trị ở nguồn ưu tiên cao hơn có thể ghi đè giá trị ở nguồn thấp hơn. Trong vận hành, những nguồn thường dùng gồm:

| Nguồn | Ví dụ | Trường hợp sử dụng |
|---|---|---|
| File mặc định | `application.yml` | Giá trị chung, không nhạy cảm |
| File theo profile | `application-prod.yml` | Giá trị riêng cho production |
| File cấu hình ngoài | Thư mục `config/` hoặc file được import | Cấu hình do môi trường triển khai quản lý |
| Biến môi trường | `APP_RSOCKET_REMOTE_HOST` | Container, Kubernetes, CI/CD |
| System property | `-Dapp.rsocket.remote.port=7001` | Tham số JVM |
| Command-line argument | `--app.rsocket.remote.port=7001` | Override khi chạy ứng dụng |
| Config tree / secret mount | File trong `/run/secrets/` | Đưa secret vào container từ secret manager |

Một quy tắc vận hành hữu ích là đặt mặc định an toàn và không nhạy cảm trong `application.yml`; đặt giá trị khác biệt theo môi trường trong profile hoặc nguồn cấu hình ngoài; đưa credential vào secret store hoặc secret mount. Không lưu token, password hay private key trong file cấu hình được commit vào repository.

Các nguồn cấu hình có thể ghi đè nhau. Vì vậy, khi một endpoint không đúng như mong đợi, hãy kiểm tra profile đang hoạt động và nguồn override như environment variable, JVM argument hoặc command line. Không nên giả định giá trị trong `application.yml` luôn là giá trị cuối cùng.

## 3. Dùng profile cho local, test, staging và production

Profile cho phép chọn một nhóm cấu hình theo môi trường. Ví dụ, `application.yml` chứa giá trị mặc định:

```yaml
spring:
  application:
    name: device-gateway

app:
  rsocket:
    remote:
      transport: tcp
      host: localhost
      port: 7001
      connect-timeout: 3s
    limits:
      max-command-bytes: 262144
      max-concurrent-streams: 100
```

File `application-local.yml` có thể giữ endpoint trên máy cá nhân:

```yaml
app:
  rsocket:
    remote:
      host: localhost
      port: 7001
```

File `application-prod.yml` có thể chỉ định DNS của service production:

```yaml
app:
  rsocket:
    remote:
      host: rsocket-gateway.production.svc.cluster.local
      port: 7000
      connect-timeout: 2s
    limits:
      max-command-bytes: 131072
      max-concurrent-streams: 500
```

Kích hoạt profile bằng biến môi trường:

```powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar device-gateway.jar
```

Hoặc truyền khi chạy:

```bash
java -jar device-gateway.jar --spring.profiles.active=staging
```

Profile chỉ chọn cấu hình. Nó không tự tạo môi trường mạng, DNS hoặc credential tương ứng. Endpoint production chỉ hoạt động khi deployment cung cấp route mạng và quyền truy cập phù hợp.

## 4. Quản lý địa chỉ server RSocket

Địa chỉ cần cấu hình phụ thuộc vào vai trò của ứng dụng.

**Server listener** là địa chỉ/cổng mà tiến trình bind để nhận kết nối. Với TCP, ví dụ:

```yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7000
```

Với WebSocket, server thường được phục vụ qua web server và một mapping path:

```yaml
spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket

server:
  port: 8080
```

Các cấu hình trên là hai lựa chọn transport, không phải hai server tự động cùng chạy trên một cổng. Hãy chọn transport phù hợp và kiểm tra phiên bản Spring Boot cùng web stack đang sử dụng.

**Remote endpoint** là địa chỉ client dùng để kết nối đến server. Đây là cấu hình riêng của ứng dụng gọi đi, ví dụ `app.rsocket.remote.host` và `app.rsocket.remote.port`. Đừng nhầm địa chỉ bind với địa chỉ client cần gọi. Trong container, server có thể bind `0.0.0.0` để lắng nghe trên các interface; client thường kết nối qua DNS/service name, không dùng `0.0.0.0` làm địa chỉ đích.

Với Kubernetes hoặc nền tảng có service discovery, nên dùng DNS ổn định của service thay vì IP của một pod cụ thể. Pod có thể được thay thế hoặc đổi IP khi rollout; service name giúp client tiếp tục dùng cùng endpoint logic.

## 5. Cấu hình địa chỉ remote bằng `@ConfigurationProperties`

Không nên đọc từng biến môi trường bằng `System.getenv()` rải rác trong service. Hãy gom các giá trị liên quan thành một properties class có kiểu dữ liệu rõ ràng.

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.rsocket.remote")
public record RSocketRemoteProperties(
    @NotNull Transport transport,
    @NotBlank String host,
    @Min(1) @Max(65535) int port,
    Duration connectTimeout,
    URI websocketUri
) {
    public enum Transport {
        TCP,
        WEBSOCKET
    }
}
```

Đăng ký properties bằng `@ConfigurationPropertiesScan` trên lớp ứng dụng hoặc `@EnableConfigurationProperties(RSocketRemoteProperties.class)` trong lớp cấu hình:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DeviceGatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(DeviceGatewayApplication.class, args);
    }
}
```

Validation giúp ứng dụng từ chối cấu hình thiếu host, transport không hợp lệ hoặc port ngoài phạm vi ngay lúc khởi động. Nếu transport là WebSocket, có thể bổ sung kiểm tra điều kiện `websocketUri` bắt buộc bằng custom validator hoặc tách properties theo từng transport. Không để lỗi cấu hình chỉ xuất hiện khi request đầu tiên được gửi.

Các trường `Duration` được Spring Boot bind từ dạng dễ đọc như `3s`, `500ms` hoặc `1m`. Hãy chọn đơn vị và giới hạn rõ ràng, tránh dùng số nguyên không có đơn vị cho timeout.

## 6. Tạo RSocket client từ cấu hình

Service hoặc factory tạo client nên nhận properties qua constructor. Ví dụ dưới đây trả về `Mono<RSocketRequester>` để quá trình kết nối vẫn bất đồng bộ:

```java
import java.net.URI;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class RemoteRSocketConnector {
    private final RSocketRemoteProperties properties;

    public RemoteRSocketConnector(RSocketRemoteProperties properties) {
        this.properties = properties;
    }

    public Mono<RSocketRequester> connect() {
        RSocketRequester.Builder builder = RSocketRequester.builder();

        return switch (properties.transport()) {
            case TCP -> builder.connectTcp(
                properties.host(), properties.port());
            case WEBSOCKET -> builder.connectWebSocket(
                properties.websocketUri());
        };
    }
}
```

Ví dụ minh họa việc chọn transport theo cấu hình. Với WebSocket, `websocketUri` cần là URI đầy đủ, ví dụ `ws://host:port/rsocket` hoặc `wss://host/rsocket`, theo cách deployment expose endpoint. Với TCP, dùng host và port riêng. Nếu ứng dụng dùng TLS, credential hoặc setup metadata, hãy bổ sung cấu hình và cơ chế bảo mật phù hợp; không ghép token vào URI.

Trong ứng dụng thật, không gọi `connect()` cho từng request. Một component quản lý connection nên tạo, theo dõi `onClose()`, reconnect theo chính sách và dispose khi application dừng. Nếu nhiều caller cùng cần kết nối, hãy chia sẻ connection theo lifecycle owner thay vì mỗi caller tự tạo socket.

## 7. Biến môi trường và relaxed binding

Spring Boot hỗ trợ relaxed binding giữa tên property và biến môi trường. Quy tắc thường dùng là viết hoa, thay dấu chấm bằng dấu gạch dưới và bỏ dấu gạch ngang.

| Property | Environment variable |
|---|---|
| `app.rsocket.remote.host` | `APP_RSOCKET_REMOTE_HOST` |
| `app.rsocket.remote.port` | `APP_RSOCKET_REMOTE_PORT` |
| `app.rsocket.remote.connect-timeout` | `APP_RSOCKET_REMOTE_CONNECTTIMEOUT` |
| `app.rsocket.limits.max-command-bytes` | `APP_RSOCKET_LIMITS_MAXCOMMANDBYTES` |
| `spring.rsocket.server.port` | `SPRING_RSOCKET_SERVER_PORT` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |

Ví dụ PowerShell:

```powershell
$env:APP_RSOCKET_REMOTE_HOST = "rsocket-gateway.internal"
$env:APP_RSOCKET_REMOTE_PORT = "7000"
$env:APP_RSOCKET_REMOTE_CONNECTTIMEOUT = "2s"
$env:SPRING_PROFILES_ACTIVE = "staging"
```

Ví dụ Bash:

```bash
export APP_RSOCKET_REMOTE_HOST=rsocket-gateway.internal
export APP_RSOCKET_REMOTE_PORT=7000
export APP_RSOCKET_REMOTE_CONNECTTIMEOUT=2s
export SPRING_PROFILES_ACTIVE=staging
```

Tên biến môi trường cần tuân theo quy tắc binding của Spring Boot; không tự thêm dấu gạch ngang vào tên biến. Khi có nghi ngờ, kiểm tra binding trong test cấu hình hoặc tài liệu của phiên bản Spring Boot dự án đang dùng.

## 8. Đưa thông tin bí mật vào ứng dụng

Secret là dữ liệu cần được bảo vệ, ví dụ:

- Password hoặc token dùng để xác thực RSocket peer.
- Private key, certificate hoặc credential của hệ thống ngoài.
- API key của dịch vụ thanh toán, message broker hoặc thiết bị.
- Khóa mã hóa hoặc thông tin dùng để ký token.

Không đặt secret thật trong `application.yml`, `application-prod.yml`, Dockerfile, file `.env` được commit hoặc mã nguồn. Không đưa secret vào URL, route, DTO nghiệp vụ hoặc log. Dùng secret manager của nền tảng, Kubernetes Secret được mount có kiểm soát, Docker Secret hoặc hệ thống quản lý bí mật tương đương.

Với môi trường đơn giản, biến môi trường có thể là một cách inject secret:

```yaml
app:
  rsocket:
    auth:
      token: ${RSOCKET_AUTH_TOKEN}
```

Không đặt default token trong placeholder. Nếu credential là bắt buộc mà không được cung cấp, ứng dụng nên fail fast thay vì âm thầm dùng một giá trị rỗng hoặc giá trị phát triển.

Ví dụ PowerShell cho phiên chạy local:

```powershell
$env:RSOCKET_AUTH_TOKEN = "<secret-provided-outside-source-control>"
java -jar device-gateway.jar
```

Trong môi trường production, ưu tiên secret manager hoặc cơ chế inject secret của nền tảng. Biến môi trường có thể bị lộ qua cấu hình process, dump hoặc công cụ quản trị nếu quyền truy cập không được giới hạn.

## 9. Dùng config tree cho secret được mount thành file

Spring Boot hỗ trợ config tree để đọc mỗi file trong một thư mục như một property. Đây là cách phù hợp khi nền tảng mount secret thành file trong container.

Ví dụ cấu trúc:

```text
/run/secrets/
└── app.rsocket.auth.token
```

File `app.rsocket.auth.token` chứa token do secret manager hoặc nền tảng cấp. Khai báo import:

```yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
```

Tên file được dùng làm tên property, nên nội dung file được bind vào `app.rsocket.auth.token`. Nếu secret bắt buộc, hãy bỏ `optional:` để ứng dụng không khởi động khi thư mục hoặc file secret không có. Quyền đọc thư mục và file phải được giới hạn cho user chạy ứng dụng.

Config tree chỉ là cách nạp giá trị; nó không tự tạo, mã hóa hoặc xoay vòng secret. Việc cấp phát, cập nhật và thu hồi vẫn do secret manager hoặc nền tảng triển khai chịu trách nhiệm.

## 10. Bind secret vào cấu hình và sử dụng an toàn

Có thể bind token vào properties class riêng:

```java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.rsocket.auth")
public record RSocketAuthProperties(
    @NotBlank String token
) {}
```

Đăng ký class bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Service xác thực chỉ nên nhận secret qua dependency cần thiết; không truyền token qua các tầng không sử dụng nó.

Khi tạo setup metadata hoặc header xác thực, dùng định dạng đã thống nhất giữa hai peer và bảo vệ transport bằng TLS khi cần. Không ghi token ra log, exception message, metric label hoặc trace baggage. Tránh trả secret trong DTO response hoặc expose nó qua endpoint quản trị.

Các endpoint Actuator có thể hiển thị thông tin môi trường hoặc configuration tùy endpoint và cấu hình. Hạn chế quyền truy cập, không expose các endpoint nhạy cảm ra mạng công cộng và cấu hình masking phù hợp. Masking không thay thế việc không lưu secret ở nơi không an toàn.

## 11. Xoay vòng credential và cập nhật endpoint

Secret có vòng đời: được cấp, sử dụng, xoay vòng, thu hồi và hết hạn. Với RSocket connection dài hạn, thay đổi token trong secret store không nhất thiết tự cập nhật connection đã được thiết lập. Cần xác định cách client sử dụng credential mới.

Một quy trình rotation có thể gồm:

1. Cấp credential mới trong secret manager.
2. Cập nhật secret mount hoặc nguồn cấu hình của instance.
3. Tạo connection mới bằng credential mới trong khi credential cũ còn hiệu lực nếu chính sách cho phép overlap.
4. Kiểm tra kết nối mới hoạt động và chuyển request sang connection mới.
5. Drain rồi dispose connection cũ.
6. Thu hồi credential cũ sau khi các instance đã chuyển đổi.

Nếu credential bị thu hồi khẩn cấp, có thể phải đóng connection hiện tại và yêu cầu xác thực lại. Không ghi credential mới/cũ vào log khi điều tra.

Đổi địa chỉ remote cũng cần chính sách tương tự: tạo connection tới endpoint mới, kiểm tra health/handshake, chuyển traffic, rồi đóng connection cũ. Không thay đổi DNS hoặc config và giả định mọi connection TCP đang mở sẽ tự chuyển sang địa chỉ mới.

## 12. Timeout, giới hạn và cấu hình an toàn

Không chỉ địa chỉ và secret cần externalize. Các giới hạn vận hành cũng nên được cấu hình theo môi trường:

```yaml
app:
  rsocket:
    limits:
      max-command-bytes: 262144
      max-metadata-bytes: 16384
      max-concurrent-streams: 200
      connect-timeout: 3s
      request-timeout: 5s
```

Các giá trị là ví dụ, không phải mặc định phù hợp cho mọi hệ thống. Hãy validate giới hạn dương, chọn timeout theo latency mục tiêu và đặt giới hạn payload theo route. Không tăng max payload chỉ để khắc phục lỗi gửi dữ liệu lớn; cân nhắc application-level streaming/chunking.

Một cấu hình an toàn nên có:

- Timeout kết nối, request và stream phù hợp với từng loại tương tác.
- Giới hạn kích thước frame, payload, metadata và dữ liệu sau giải nén.
- Giới hạn số connection, stream, concurrency và queue.
- TLS và xác thực khi giao tiếp qua mạng không đáng tin cậy.
- DNS/service discovery ổn định thay vì địa chỉ IP ephemeral.
- Secret không có default và không được ghi log.
- Validation cấu hình ngay khi startup.

## 13. Những lỗi cấu hình thường gặp

- Hardcode `localhost` trong production; trong container, `localhost` thường trỏ về chính container hiện tại.
- Dùng IP của pod thay vì DNS/service name ổn định.
- Nhầm `0.0.0.0` là địa chỉ client có thể kết nối.
- Ghi token vào `application-prod.yml` hoặc commit file `.env`.
- Dùng cùng một credential cho local, staging và production.
- Đặt default secret trong placeholder khiến ứng dụng vẫn khởi động với credential không an toàn.
- Không biết environment variable nào đang ghi đè profile config.
- Đổi secret nhưng không tạo lại hoặc xác thực lại connection dài hạn.
- Thay endpoint nhưng vẫn gửi request qua connection cũ.
- Dùng `server.shutdown: graceful` và cho rằng nó tự drain mọi RSocket TCP listener tự tạo.
- Không validate port, timeout hoặc giới hạn payload khi khởi động.
- Expose Actuator environment/configuration endpoint mà không giới hạn quyền truy cập.

## 14. Kiểm thử và quan sát cấu hình

Kiểm thử cấu hình nên bao gồm:

1. Profile local/staging/production nạp đúng endpoint tương ứng.
2. Environment variable ghi đè giá trị trong file theo đúng quy tắc.
3. Port ngoài phạm vi hoặc host rỗng khiến startup thất bại.
4. Thiếu secret bắt buộc khiến startup thất bại rõ ràng.
5. Config tree đọc đúng secret file và không yêu cầu secret phải nằm trong source tree.
6. Client chọn đúng TCP hoặc WebSocket theo transport property.
7. Địa chỉ WebSocket có scheme và path phù hợp.
8. Rotation tạo connection mới, chuyển traffic và đóng connection cũ.
9. Endpoint sai hoặc DNS không phân giải được tạo lỗi có thể quan sát mà không log secret.

Có thể dùng `ApplicationContextRunner` hoặc `@SpringBootTest` để kiểm tra binding và validation của `@ConfigurationProperties`. Test không nên phụ thuộc vào secret production; dùng giá trị giả trong môi trường test. Kiểm thử kết nối thật có thể dùng server RSocket cục bộ hoặc test container với endpoint tách biệt.

Trong vận hành, theo dõi profile đang hoạt động, endpoint đã chuẩn hóa (không chứa credential), transport, thời gian kết nối, số lần reconnect, lỗi DNS/TLS/authentication và thời điểm credential được xoay vòng. Không ghi giá trị token hoặc toàn bộ environment vào log. Nếu cần hiển thị cấu hình, chỉ hiển thị trường không nhạy cảm và giới hạn quyền truy cập.

## 15. Quy tắc thiết kế

1. Để giá trị chung, không nhạy cảm trong `application.yml`; dùng profile và nguồn ngoài cho từng môi trường.
2. Dùng `@ConfigurationProperties` để gom cấu hình có kiểu dữ liệu và validate lúc startup.
3. Tách server bind address khỏi remote endpoint mà client sử dụng.
4. Dùng DNS/service name ổn định; tránh hardcode IP của instance hoặc pod.
5. Chọn TCP/WebSocket theo transport và cấu hình riêng endpoint tương ứng.
6. Đưa token, password và private key vào secret manager, secret mount hoặc nguồn inject được bảo vệ.
7. Không đặt default cho secret bắt buộc; fail fast khi thiếu credential.
8. Không log secret hoặc expose qua Actuator endpoint không được bảo vệ.
9. Có quy trình rotation credential và thay endpoint cho connection dài hạn.
10. Kiểm thử profile, override, validation, kết nối và rotation trong môi trường gần production.

Externalized configuration giúp một ứng dụng RSocket Spring Boot chạy cùng một bộ code ở nhiều môi trường, còn `@ConfigurationProperties` tạo ranh giới rõ ràng giữa cấu hình và logic. Khi địa chỉ service được quản lý bằng DNS/profile, secret được cấp từ nguồn an toàn và credential có quy trình rotation, hệ thống realtime có thể thay đổi môi trường triển khai mà không phải sửa nghiệp vụ hoặc làm lộ thông tin nhạy cảm.

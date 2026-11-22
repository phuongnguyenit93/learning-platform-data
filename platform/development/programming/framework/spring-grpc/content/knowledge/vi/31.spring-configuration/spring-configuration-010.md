# Profile local, test, staging và production

## Mục tiêu bài học

Trong **SPRING_GRPC**, cùng một service có thể chạy trên máy lập trình, trong integration test, ở staging và production. Mỗi môi trường có endpoint, certificate, secret, executor capacity, health policy và cách quan sát khác nhau. Nếu các giá trị này bị trộn trong code hoặc cấu hình mặc định, ứng dụng dễ gọi nhầm hệ thống, vô tình tắt TLS hoặc dùng cấu hình thử nghiệm khi triển khai thật.

Bài học tập trung vào **profile local, test, staging và production** trong Spring: hiểu Spring Profiles và thứ tự nạp cấu hình, tách giá trị theo môi trường, bind cấu hình thành kiểu dữ liệu có validation, áp dụng đúng cho gRPC server/channel, quản lý secret, kích hoạt profile khi deploy và kiểm thử để chắc chắn ứng dụng dùng đúng cấu hình.

Sau bài này, bạn có thể:

1. Giải thích cách Spring Boot kích hoạt profile và hợp nhất cấu hình.
2. Thiết kế cấu hình chung cùng các file application-local/test/staging/prod.
3. Dùng @Profile cho bean theo môi trường và @ConfigurationProperties cho cấu hình có kiểu.
4. Quản lý gRPC target, TLS, timeout, executor, health và reflection theo môi trường.
5. Phân biệt cấu hình được commit với secret được cấp từ runtime.
6. Kích hoạt và xác minh profile trong IDE, test, container và deployment.
7. Kiểm thử cấu hình từng profile và phát hiện cấu hình production không an toàn.

> **Phạm vi:** Ví dụ dùng Spring Boot, Spring gRPC và gRPC Java. Các khóa trong namespace app.grpc.* bên dưới là cấu hình do ứng dụng minh họa tự định nghĩa. Thuộc tính listener/transport thực tế phải dùng đúng tên và extension point của phiên bản Spring gRPC đang cài; không suy ra property của starter từ ví dụ này.

## 1. Vì sao cần profile?

Profile cho phép một ứng dụng dùng các cấu hình hoặc bean khác nhau theo môi trường. Các khác biệt phổ biến của dịch vụ gRPC:

| Thành phần | Local | Test | Staging | Production |
| --- | --- | --- | --- | --- |
| Downstream target | localhost hoặc service dev | In-process/fake/Testcontainer | Endpoint staging | Endpoint production/service discovery |
| TLS | Có thể plaintext trên loopback | In-process hoặc TLS test | TLS, thường gần cấu hình prod | TLS bắt buộc; mTLS theo trust boundary |
| Certificate/CA | Certificate test hoặc CA dev | Fixture test | Secret/certificate staging | Secret manager/PKI production |
| Executor | Nhỏ, dễ debug | Deterministic, giới hạn | Gần sizing production | Sizing theo tải và capacity |
| Health | Dễ kiểm tra local | Assert trạng thái | Probe như production | Readiness/liveness theo policy |
| Reflection | Có thể bật | Có thể bật cho test | Có kiểm soát | Tắt hoặc giới hạn mạnh |
| Logging | Chi tiết hơn | Thu thập assertion | Structured, redacted | Structured, redacted, sampling |
| Dependency | Mock hoặc dev instance | Fake/Testcontainer | Bản staging | Dịch vụ production |

Profile không nhất thiết là một bản build khác nhau. Thông thường cùng artifact được triển khai với profile và cấu hình runtime khác nhau. Điều này giúp kiểm thử đúng artifact sẽ chạy ở production.

## 2. Spring Boot nạp profile như thế nào?

Spring Boot nạp cấu hình nền từ application.properties hoặc application.yml, sau đó có thể nạp cấu hình profile-specific như application-local.yml hoặc application-prod.yml khi profile tương ứng được kích hoạt.

Ví dụ cấu trúc:

```text
src/main/resources/
  application.yml
  application-local.yml
  application-test.yml
  application-staging.yml
  application-prod.yml
```

Cấu hình chung nằm trong application.yml. File profile-specific ghi đè các giá trị chung khi profile được bật. Các nguồn cấu hình bên ngoài như environment variables, command-line arguments, mounted config hoặc secret provider có thể có độ ưu tiên cao hơn file trong artifact theo quy tắc Config Data/property source của Spring Boot.

Không nên sao chép toàn bộ application.yml sang từng profile. Chỉ đặt giá trị thực sự khác nhau vào file môi trường để tránh drift và khó review.

### 2.1. Kích hoạt profile

Có thể kích hoạt profile qua environment variable:

```bash
SPRING_PROFILES_ACTIVE=local
```

Hoặc command-line argument:

```bash
java -jar spring-grpc-service.jar --spring.profiles.active=staging
```

Trong IDE, cấu hình environment variable hoặc program argument của run configuration. Trong container/orchestrator, truyền profile qua deployment manifest hoặc environment injection. Không hardcode profile production trong source code.

Khi cần nhiều profile đồng thời, Spring có thể kích hoạt danh sách profile, ví dụ staging cùng một profile quan sát. Cần kiểm tra thứ tự và giá trị ghi đè vì profile được xử lý theo thứ tự khai báo.

### 2.2. Quy tắc đặt spring.profiles.active

Đặt spring.profiles.active ở nguồn cấu hình không gắn profile, chẳng hạn environment variable hoặc application.yml chung. Không đặt spring.profiles.active hoặc spring.profiles.include trong một file đã được kích hoạt theo profile; Spring Boot giới hạn các thuộc tính kích hoạt profile này ở tài liệu không profile-specific.

Nếu dùng profile group, khai báo group ở cấu hình nền để một tên môi trường có thể kích hoạt nhiều profile có liên quan. Chỉ dùng group khi nhóm profile có ý nghĩa rõ và đã được kiểm thử; tránh tạo chuỗi include khó dự đoán.

### 2.3. Cấu hình chung và cấu hình riêng

Ví dụ application.yml:

```yaml
spring:
  application:
    name: inventory-grpc

app:
  grpc:
    client:
      inventory:
        deadline: 2s
    observability:
      include-method: true
      include-request-id: true
    reflection:
      enabled: false
```

Các khóa app.grpc.* là cấu hình do ứng dụng định nghĩa trong bài học. Chúng chưa tự động thay đổi listener hay channel cho tới khi được bind và dùng trong code. Đặt deadline chung, logging policy và default an toàn ở đây; target, TLS material và capacity sẽ được override theo môi trường.

## 3. Bind cấu hình thành kiểu dữ liệu

Không nên đọc hàng chục giá trị bằng Environment.getProperty rải rác trong service. Dùng @ConfigurationProperties để gom cấu hình liên quan vào một object có kiểu và validation.

Ví dụ:

```java
@ConfigurationProperties(prefix = "app.grpc")
@Validated
public record GrpcApplicationProperties(
        @Valid Client client,
        @Valid Reflection reflection) {

    public record Client(
            @Valid Inventory inventory) {}

    public record Inventory(
            @NotBlank String target,
            @NotNull Duration deadline,
            @NotBlank String securityMode,
            String trustBundleLocation) {}

    public record Reflection(boolean enabled) {}
}
```

Đăng ký configuration properties bằng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties:

```java
@Configuration
@EnableConfigurationProperties(GrpcApplicationProperties.class)
class GrpcPropertiesConfiguration {
}
```

Có thể thêm validation theo security mode: nếu mode là tls thì trust bundle/credential reference phải tồn tại; nếu production bật plaintext thì context khởi động phải fail. Với record lồng nhau, dùng @Valid để validation tiếp tục xuống các field con. Đảm bảo dependency validation tương ứng có trong build.

Tên field và annotation cần khớp phiên bản Java/Spring Boot của dự án. Ví dụ trên minh họa cấu trúc; trong code thật, định nghĩa rõ allowed values cho securityMode, giới hạn deadline và validate URI/target theo policy.

### 3.1. Dùng @Profile cho bean theo môi trường

@Profile phù hợp khi implementation bean thực sự khác nhau:

```java
@Configuration
@Profile("local")
class LocalGrpcClientConfiguration {

    @Bean
    InventoryGateway inventoryGateway() {
        return new LocalInventoryGateway();
    }
}
```

Ví dụ khác là fake downstream client cho integration test hoặc adapter quan sát chỉ bật ở local. Không nên tạo một bản sao service implementation cho mỗi profile chỉ để thay endpoint; endpoint và timeout thường nên là configuration data, còn behavior nghiệp vụ giữ nhất quán.

Profile chỉ quyết định bean nào được tạo trong application context. Nó không tự bảo vệ network endpoint và không thay thế authentication/authorization.

## 4. Profile local

Local cần tối ưu cho vòng lặp phát triển nhanh, nhưng vẫn nên giữ các hành vi quan trọng gần production.

Ví dụ application-local.yml:

```yaml
app:
  grpc:
    client:
      inventory:
        target: dns:///localhost:9090
        deadline: 3s
        security-mode: plaintext
    reflection:
      enabled: true
```

Ở local, plaintext chỉ phù hợp khi kết nối loopback hoặc môi trường dev cô lập. Không dùng cùng file local làm cấu hình mặc định cho container hoặc cluster. Nếu phát triển tính năng TLS, nên có profile local-tls hoặc test certificate để tái hiện hostname verification và trust chain.

Các nguyên tắc local:

- Dùng target local/dev được kiểm soát.
- Không chứa production token, private key hoặc password.
- Reflection có thể bật để grpcurl khám phá service.
- Log có thể chi tiết hơn nhưng vẫn phải redact credential/payload.
- Executor nhỏ giúp thread dump và debug dễ đọc.
- Dependency thật nên là dev instance hoặc container riêng, không trỏ nhầm production.

## 5. Profile test

Test cần tính lặp lại, độc lập và không phụ thuộc dịch vụ bên ngoài không kiểm soát.

Ví dụ application-test.yml:

```yaml
app:
  grpc:
    client:
      inventory:
        deadline: 500ms
        security-mode: test
    reflection:
      enabled: true
```

Giá trị security-mode=test là lựa chọn nội bộ của ứng dụng trong ví dụ; nó có thể tương ứng in-process channel, test credential hoặc test fixture. Không đưa một giá trị custom như vậy vào gRPC builder nếu code chưa định nghĩa semantics.

Các lựa chọn kiểm thử:

- **Unit test:** mock gateway/repository; không cần mở gRPC listener.
- **In-process gRPC test:** dùng InProcessServerBuilder và InProcessChannelBuilder để kiểm tra service, interceptor, metadata và status mà không mở TCP port.
- **Transport integration test:** chạy server thật trên port ngẫu nhiên để kiểm tra HTTP/2, TLS, channel và server wiring.
- **Testcontainers:** dùng dependency thực như database hoặc broker khi behavior phụ thuộc vào integration đó.

Dùng @ActiveProfiles("test") trong Spring integration test để kích hoạt cấu hình test một cách tường minh. Nếu test dùng @DynamicPropertySource hoặc TestPropertyValues, nhớ rằng các giá trị này có thể override application-test.yml.

Không dùng chung credential production cho test. Certificate test nên được tạo riêng, có thời hạn phù hợp và không được tin bởi workload production.

## 6. Profile staging

Staging dùng để xác minh artifact và cấu hình gần production trước khi phát hành. Nó nên có topology, TLS, authentication, proxy và dependency tương tự production nhưng dùng endpoint và identity riêng.

Ví dụ application-staging.yml:

```yaml
app:
  grpc:
    client:
      inventory:
        target: dns:///inventory.staging.internal:443
        deadline: 2s
        security-mode: tls
        trust-bundle-location: file:/var/run/grpc-certs/staging-ca.pem
    reflection:
      enabled: false
```

Đường dẫn trust bundle là ví dụ mount từ runtime; file certificate không nên được nhúng vào image nếu lifecycle/rotation cần thay độc lập. Nếu dùng mTLS, client key/certificate được cấp từ secret manager hoặc volume bảo vệ và không nằm trong source control.

Staging nên kiểm tra:

- TLS chain, SAN, SNI và ALPN h2.
- Authentication/authorization thực tế.
- Deadline, retry và load balancing.
- Health Check/Watch, readiness và graceful shutdown.
- Reflection policy có đúng dự kiến không.
- Executor, queue và metrics dưới tải gần production.
- Log redaction và trace correlation.

Không bật reflection chỉ để tiện debug nếu production sẽ tắt; staging nên xác minh cả cấu hình tắt và quy trình khám phá bằng descriptor set khi cần.

## 7. Profile production

Production ưu tiên an toàn, khả năng vận hành và hành vi có thể dự đoán. Ví dụ application-prod.yml:

```yaml
app:
  grpc:
    client:
      inventory:
        target: dns:///inventory.internal:443
        deadline: 1500ms
        security-mode: tls
        trust-bundle-location: file:/var/run/grpc-certs/production-ca.pem
    reflection:
      enabled: false
```

Đây vẫn là cấu hình minh họa của app.grpc.*. Listener port, TLS server credentials, executor server và các property transport phải được cấu hình theo API/property thực tế của phiên bản Spring gRPC được dùng.

Production cần các điều kiện fail-fast:

- Target phải là endpoint được phê duyệt.
- TLS phải bật cho kết nối qua network không tin cậy.
- Trust roots và certificate/key reference phải tồn tại, đúng quyền truy cập và còn hiệu lực.
- Deadline phải hữu hạn và phù hợp latency budget.
- Executor/queue phải hữu hạn; không dùng pool vô hạn để che overload.
- Reflection tắt hoặc chỉ mở trong network/operator boundary đã được phê duyệt.
- Health/readiness phải phản ánh khả năng nhận traffic.
- Log/trace không chứa token, private key hoặc payload nhạy cảm.
- Không fallback âm thầm từ TLS sang plaintext khi certificate lỗi.

Profile production không phải một cơ chế bảo mật. Một người có thể vô tình bật thêm profile local hoặc override property qua environment/command line. Vì vậy, validation và deployment policy phải kiểm tra cấu hình cuối cùng trước khi nhận traffic.

## 8. Cấu hình gRPC server và client theo profile

### 8.1. Client channel

Channel nên được tạo từ cấu hình đã validate và được Spring quản lý lifecycle:

```java
@Bean(destroyMethod = "shutdown")
ManagedChannel inventoryChannel(
        GrpcApplicationProperties properties,
        ChannelCredentialsFactory credentialsFactory) {

    var config = properties.client().inventory();

    return Grpc.newChannelBuilder(
            config.target(),
            credentialsFactory.forMode(
                    config.securityMode(),
                    config.trustBundleLocation()))
            .build();
}
```

ChannelCredentialsFactory là abstraction do ứng dụng định nghĩa để tạo credential phù hợp, không phải class gRPC có sẵn. Trong implementation thật, nó cần phân biệt plaintext chỉ ở môi trường cho phép, TLS trust roots và mTLS key material. Không tạo channel mới cho từng RPC; channel là resource dùng chung và phải được shutdown khi context dừng.

Deadline thường được đặt trên stub/call theo request, dựa trên cấu hình chung:

```java
InventoryGrpc.InventoryBlockingStub stub =
        InventoryGrpc.newBlockingStub(inventoryChannel)
                .withDeadlineAfter(
                        properties.client().inventory()
                                .deadline().toMillis(),
                        TimeUnit.MILLISECONDS);
```

Trong code thực tế nên inject cấu hình client riêng vào factory tạo stub, và không dùng một deadline dài cho mọi method nếu SLA khác nhau.

### 8.2. Server listener

Server listener do Spring gRPC starter quản lý. Cấu hình server port, TLS credentials, executor và service registration qua property hoặc builder customization mà đúng phiên bản starter công bố.

Một số cấu hình là transport-level, một số là application-level:

| Cấu hình | Lớp sở hữu |
| --- | --- |
| Listen port, TLS key/certificate, client auth | gRPC server transport/factory |
| Server callback executor | gRPC ServerBuilder/transport |
| Business worker pool | Spring application executor |
| @GrpcService registration | Spring gRPC service integration |
| Health/reflection service | gRPC service registration |
| Client target, credentials, deadline | gRPC ManagedChannel/stub |
| Business feature toggle | Application configuration |

Không giả định server.ssl.* của servlet container tự cấu hình native gRPC listener. Tương tự, một bean Executor hoặc ServerInterceptor không tự được gắn vào gRPC server nếu chưa đăng ký qua extension point.

## 9. Secret và external configuration

Giữ cấu hình có thể review trong source control; cấp secret tại runtime:

| Dữ liệu | Cách quản lý |
| --- | --- |
| Target host, deadline, feature toggle | Config file/environment |
| CA public certificate | Config artifact hoặc mounted trust bundle đã xác minh |
| Server private key | Secret manager/secure volume |
| Client private key và certificate mTLS | Secret manager/secure volume |
| Bearer token/API credential | Secret provider hoặc workload identity |
| Password keystore | Secret manager, không commit |
| Profile activation | Deployment environment/argument |

Spring Boot hỗ trợ externalized configuration và config tree import cho secret được mount thành file. Có thể sử dụng config tree khi deployment platform cung cấp thư mục secret; kiểm tra tên file, quyền truy cập và property binding. Không in toàn bộ Environment hoặc Actuator env endpoint ra ngoài; endpoint cấu hình có thể tiết lộ dữ liệu nhạy cảm nếu không được bảo vệ.

Khi secret rotation, xác định liệu channel/server đang giữ TLS context cũ hay có hỗ trợ reload. Thay file không đồng nghĩa credential đã được nạp lại; có thể cần tạo channel mới hoặc rolling restart server theo quy trình an toàn.

## 10. Kích hoạt profile trong container và deployment

Trong Docker/Kubernetes hoặc nền tảng tương tự, profile nên được truyền từ deployment configuration:

```yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: production
```

Đoạn này là ví dụ cấu hình environment trong manifest, không phải file Spring application profile. Không đóng gói profile production thành giá trị mặc định trong Dockerfile nếu cùng image cần chạy qua nhiều môi trường.

Có thể override từng property bằng environment variable theo quy tắc relaxed binding của Spring Boot. Khi dùng nhiều nguồn cấu hình, ghi rõ nguồn nào có quyền ưu tiên. Tránh cùng một property xuất hiện ở ConfigMap, environment, command line và file profile với giá trị khác nhau mà không có quy ước.

Ở startup, log profile active và các cấu hình không nhạy cảm như target đã chuẩn hóa, TLS mode, deadline và reflection enabled. Không log certificate private material, password hoặc token. Nếu cấu hình production không đạt validation, ứng dụng nên fail startup thay vì tự chọn giá trị local mặc định.

## 11. Kiểm thử từng profile

Một chiến lược test tốt xác minh cả nội dung cấu hình lẫn hành vi sau khi Spring tạo bean/channel/server.

| Kiểm thử | Cách làm | Điều cần chứng minh |
| --- | --- | --- |
| Local context | Khởi tạo với profile local | Target local, reflection theo cấu hình dev |
| Test context | @ActiveProfiles("test") | Fake/in-process dependency và deadline test |
| Staging smoke test | Deploy artifact với profile staging | TLS, auth, health, downstream routing |
| Production config validation | Load production config trong test | Không plaintext, không thiếu trust bundle, reflection theo policy |
| Override precedence | Set environment/property override | Giá trị cuối cùng đúng nguồn ưu tiên |
| Secret missing | Bỏ trust bundle/credential bắt buộc | Startup fail-fast |
| Wrong hostname | Dùng test certificate SAN sai | TLS handshake/hostname verification thất bại |
| Channel lifecycle | Đóng Spring context | ManagedChannel shutdown đúng |
| Server lifecycle | Stop application | Health NOT_SERVING, server drain và shutdown |

Có thể dùng ApplicationContextRunner để kiểm tra configuration properties và bean condition mà không khởi động toàn bộ ứng dụng. Dùng @SpringBootTest khi cần xác minh server/channel wiring. Với staging, chạy smoke test qua endpoint thực tế sau deploy; không chỉ dựa vào test context.

### 11.1. Kiểm tra cấu hình cuối cùng

Kiểm tra các giá trị đã bind sau khi toàn bộ property sources được nạp:

- Active profiles.
- gRPC target và port.
- Security mode/TLS enabled.
- Trust bundle reference có tồn tại.
- Deadline và timeout.
- Executor max threads/queue capacity.
- Health/reflection policy.
- Các feature flag ảnh hưởng RPC behavior.

Không expose toàn bộ cấu hình qua endpoint công khai. Tạo startup summary đã lọc hoặc health diagnostic chỉ chứa trạng thái tối thiểu.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Ứng dụng local trỏ nhầm production | application.yml chứa endpoint môi trường thật | Đặt target local an toàn ở application-local.yml và kiểm tra startup summary |
| Staging chạy plaintext | Profile không được kích hoạt hoặc property bị override | Kiểm tra active profile và property source precedence; fail-fast nếu TLS tắt |
| Production không tìm thấy CA bundle | Secret mount sai path/quyền | Validate file reference và mount trước khi tạo channel |
| Profile-specific bean không xuất hiện | Profile active sai hoặc @Profile condition không khớp | Kiểm tra active profiles và context test |
| Test phụ thuộc dịch vụ dev | application-test không override target | Dùng in-process/fake/Testcontainer và assert bean config |
| Bean dùng giá trị cũ | Cấu hình được bind trước override hoặc custom factory cache sai | Kiểm tra property source order và lifecycle bean |
| Profile local vô tình bật ở production | Nhiều profile được active hoặc deployment override | Kiểm tra profile list và policy cho profile không được phép |
| Reflection lộ trên production | Default chung bật reflection hoặc override sai | Default false, validate production policy và kiểm tra listener |
| Channel vẫn dùng CA cũ sau rotation | TLS credential được nạp lúc channel tạo | Tạo channel mới hoặc dùng reload mechanism được hỗ trợ |
| HTTP server TLS bật nhưng gRPC listener plaintext | Cấu hình servlet và native gRPC bị nhầm | Cấu hình đúng gRPC server factory/transport |
| Executor không đổi theo profile | Bean executor không được conditional hoặc cấu hình | Bind pool settings và xác minh instance thực tế |
| Secret xuất hiện trong log | Dump Environment/exception/config object | Redact, log allowlist và bảo vệ actuator |

## 13. Bài tập thực hành

1. Tạo application.yml chứa cấu hình chung: deadline mặc định, observability và reflection mặc định tắt.
2. Tạo application-local.yml với target localhost, plaintext chỉ cho loopback và reflection bật.
3. Tạo application-test.yml dùng in-process/fake downstream và deadline ngắn.
4. Tạo application-staging.yml dùng DNS target staging, TLS trust bundle và reflection tắt.
5. Tạo application-prod.yml với TLS bắt buộc, trust bundle runtime, deadline hữu hạn và reflection tắt.
6. Bind app.grpc.* bằng @ConfigurationProperties, thêm validation cho target, deadline và security mode.
7. Dùng @Profile cho fake gateway/test adapter; giữ service nghiệp vụ dùng chung.
8. Chạy cùng artifact với từng profile và ghi startup summary đã redaction.
9. Viết test chứng minh production profile fail-fast nếu TLS/trust bundle không hợp lệ.
10. Kiểm tra Spring-managed gRPC listener thực sự dùng port/TLS/executor được cấu hình; không chỉ kiểm tra bean tồn tại.
11. Diễn tập CA rotation và xác minh channel mới sử dụng trust bundle mới.
12. Viết deployment runbook nêu profile activation, config source precedence, secret mount và rollback.

### Câu hỏi tự kiểm tra

- Spring Boot nạp application.yml và application-{profile}.yml theo nguyên tắc nào?
- Có thể kích hoạt profile bằng environment variable và command-line argument ra sao?
- Vì sao không nên đặt spring.profiles.active trong profile-specific document?
- @Profile khác @ConfigurationProperties như thế nào?
- Vì sao các ví dụ app.grpc.* cần được bind và wiring trước khi có tác dụng?
- Local và test khác nhau ở mục tiêu nào?
- Vì sao staging nên gần production về TLS, auth và health behavior?
- Profile production có phải security boundary không?
- Secret nào nên cấp qua runtime thay vì commit vào repository?
- Vì sao servlet server TLS không tự chứng minh native gRPC listener đã bật TLS?
- Làm thế nào test fail-fast khi production thiếu CA bundle?
- Khi rotate CA, tại sao có thể cần tạo channel mới hoặc restart server?

## Tài liệu tham khảo

- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): kích hoạt profile, profile-specific configuration và profile groups.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, precedence và config data.
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): bind cấu hình vào object có kiểu.
- [Spring Framework — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html): Environment và profile condition.
- [Spring Boot — Config Data Imports](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing): import external config và config tree.
- [gRPC — Authentication](https://grpc.io/docs/guides/auth/): TLS và credential cho gRPC.
- [gRPC Java — ManagedChannelBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html): cấu hình channel.
- [gRPC Java — ServerBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerBuilder.html): cấu hình server, executor và service.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): kiểm thử application context và cấu hình.
- [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html): readiness/liveness trong lifecycle.

**Kết quả mong đợi:** Người học tổ chức được profile local, test, staging và production cho Spring gRPC, hiểu cấu hình được hợp nhất và override như thế nào, bind/validate cấu hình có kiểu, cấp secret an toàn, kích hoạt đúng profile khi deploy, và kiểm thử để ngăn endpoint, TLS, reflection hoặc executor của môi trường này rò sang môi trường khác.

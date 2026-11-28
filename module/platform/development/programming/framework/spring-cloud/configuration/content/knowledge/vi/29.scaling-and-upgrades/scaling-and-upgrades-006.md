# Đánh giá thay đổi hành vi giữa các phiên bản Config Server và Client

Nâng cấp Spring Cloud Config không chỉ là thay số phiên bản dependency. Config Server và Config Client cùng tham gia một giao thức: client tạo request theo application/profile/label, server đọc repository và trả `Environment`, client hợp nhất property source vào Spring `Environment`, sau đó binding và refresh ảnh hưởng tới bean đang chạy. Một thay đổi ở bất kỳ bước nào cũng có thể làm ứng dụng đọc nhầm cấu hình, khởi động thất bại hoặc không còn áp dụng refresh như trước.

Vì vậy, trước khi nâng cấp cần đánh giá đồng thời **tương thích Spring Boot–Spring Cloud, cách nạp cấu hình, request/response giữa client và server, thứ tự ưu tiên, retry/failover, refresh, backend và bảo mật**. Bài này đưa ra khung so sánh có ví dụ các thay đổi hành vi quan trọng qua các thế hệ Spring Cloud Config.

## 1. Bắt đầu từ ma trận tương thích release train

Spring Cloud được phát hành theo release train. Không nên tự ghép một phiên bản Spring Cloud Config mới với bất kỳ phiên bản Spring Boot nào chỉ vì Maven/Gradle resolve dependency thành công. Hãy chọn release train phù hợp với thế hệ Spring Boot trước, sau đó dùng BOM của train để quản lý các module Spring Cloud.

Tại thời điểm biên soạn (27/11/2026), tài liệu Spring công bố các dòng chính sau:

| Spring Cloud release train | Spring Boot tương ứng | Spring Cloud Config trong train hiện hành |
| --- | --- | --- |
| 2026.0.x (Paddington) | 4.2.x | 5.1.x |
| 2025.1.x (Oakwood) | 4.0.x; 4.1.x từ 2025.1.2 | 5.0.x |
| 2025.0.x (Northfields) | 3.5.x | 4.3.x |
| 2024.0.x (Moorgate) | 3.4.x | 4.2.x |
| 2023.0.x (Leyton) | 3.2.x; 3.3.x từ 2023.0.2 | 4.1.x |
| 2022.0.x (Kilburn) | 3.0.x; 3.1.x từ 2022.0.3 | 4.0.x |

Spring Cloud 2026.0.0 được phát hành GA ngày 20/11/2026, dựa trên Spring Boot 4.2.0 và mang Spring Cloud Config 5.1.0. Bảng trên là định hướng theo release train; trước khi nâng cấp cần kiểm tra bản service release, trạng thái hỗ trợ và yêu cầu của từng module trong tài liệu chính thức.

### Dùng BOM thay vì quản lý version từng module

Ví dụ Maven:

```xml
<properties>
    <spring-boot.version>4.2.0</spring-boot.version>
    <spring-cloud.version>2026.0.0</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Ví dụ Gradle:

```kotlin
extra["springCloudVersion"] = "2026.0.0"

dependencies {
    implementation(platform(
        "org.springframework.cloud:spring-cloud-dependencies:${property("springCloudVersion")}"
    ))
    implementation("org.springframework.cloud:spring-cloud-config-server")
    implementation("org.springframework.cloud:spring-cloud-starter-config")
}
```

Các version minh họa phải được thay theo release train mục tiêu của dự án. Tránh override riêng `spring-cloud-config`, `spring-cloud-commons`, `spring-cloud-stream` hoặc Spring Framework nếu không có lý do tương thích đã được kiểm chứng.

## 2. Lập bản đồ hành vi trước khi so sánh version

Để so sánh hai phiên bản, trước hết ghi lại hành vi đang được sử dụng. Không phải ứng dụng nào cũng dùng hết các tính năng của Config Server/Client.

| Khu vực | Câu hỏi cần ghi nhận |
| --- | --- |
| Bootstrap/Config Data | Client dùng `bootstrap.yml` hay `spring.config.import`? Có bật legacy bootstrap không? |
| Request contract | Application, profile, label, nhiều label và URL được tạo thế nào? |
| Response contract | `Environment`, `propertySources`, `version`, `label` và tên source có được ứng dụng khác tiêu thụ không? |
| Precedence | Remote property source thắng local hay ngược lại? Có dùng override flags không? |
| Retry/failover | Bao nhiêu lần thử, backoff ra sao, khi nào chuyển Config Server URL khác? |
| Backend | Git, Vault, JDBC, composite hoặc backend khác; có dùng SSH, search path, clone cache không? |
| Refresh | Dùng `/actuator/refresh`, `busrefresh`, `@RefreshScope` hay rebind `@ConfigurationProperties`? |
| Security | Basic Auth, OAuth2, mTLS, SSH host key, encryption endpoint và Actuator policy? |
| Build/runtime | Có AOT/native image, profile activation, custom RestClient hoặc custom repository không? |

Ghi lại các giá trị thực tế theo application/profile/label đại diện. Đây là baseline để so sánh response và hành vi sau nâng cấp.

## 3. Thay đổi lớn: Config Data API và legacy bootstrap

Một thay đổi quan trọng trong hệ sinh thái Spring Boot là Config Data API được giới thiệu từ Spring Boot 2.4. Đây là cách mặc định hiện đại để Config Client kết nối Config Server.

### Config Data import

Ví dụ:

```yaml
spring:
  application:
    name: billing-api
  config:
    import: "configserver:https://config.internal:8888"
```

Nếu dùng `optional:`, ứng dụng có thể tiếp tục khi Config Server không truy cập được:

```yaml
spring:
  config:
    import: "optional:configserver:https://config.internal:8888"
```

Bỏ `optional:` để Config Client fail khi không nạp được Config Server. URL ghi trực tiếp trong import location có ưu tiên hơn `spring.cloud.config.uri`.

Config Data giải quyết cấu hình theo hai giai đoạn:

1. Nạp cấu hình với profile `default` để thu thập giá trị có thể kích hoạt thêm profile.
2. Sau khi xác định active profile, nạp cấu hình profile-specific.

Vì vậy, client có thể gọi Config Server nhiều lần khi khởi động. Đây là hành vi bình thường của Config Data, khác với mô hình cũ thường chỉ có một request bootstrap. Nhiều request hơn không nhất thiết là lỗi; chúng cho phép cấu hình từ server kích hoạt profile rồi tải phần cấu hình tương ứng.

### Legacy bootstrap

Ứng dụng cũ có thể tiếp tục dùng bootstrap bằng cách thêm `spring-cloud-starter-bootstrap` hoặc đặt `spring.cloud.bootstrap.enabled=true` qua system property/environment variable. Khi bật, client dùng `bootstrap.yml` hoặc environment để khai báo `spring.cloud.config.uri` và tải remote property source trong bootstrap context.

Hai cơ chế có lifecycle và thứ tự nạp khác nhau. Không bật legacy bootstrap đồng thời với Config Data import cho cùng một luồng Config Client nếu phiên bản không hỗ trợ kết hợp đó. Khi migration, chọn một cơ chế, chuyển URI/credential/profile/label và kiểm tra lại thứ tự property source.

| Hành vi | Legacy bootstrap | Config Data |
| --- | --- | --- |
| Kích hoạt | Starter/property bootstrap | `spring.config.import` |
| File bootstrap bắt buộc | Có khi dùng bootstrap config file | Không cần chỉ để import Config Server |
| Thời điểm nạp | Bootstrap context | Config Data phase |
| Profile activation từ remote config | Khả năng và lifecycle theo bootstrap | Nạp `default`, sau đó nạp active profile |
| Số request startup | Thường một lần trong luồng cơ bản | Có thể nhiều request theo profile resolution |
| Optional/fail-fast | Dựa trên bootstrap/fail-fast config | Tiền tố `optional:` điều khiển tính bắt buộc |

## 4. Thay đổi cách xử lý nhiều label từ Config Client 4.2.0

Một thay đổi cần kiểm tra khi nâng cấp client/server là cách gửi danh sách label.

Trước Spring Cloud Config 4.2.0, khi `spring.cloud.config.label` chứa danh sách phân tách bằng dấu phẩy, client thử từng label bằng các request riêng và dừng khi tìm được label phù hợp. Các label sau không nhất thiết được kết hợp trong một response.

Từ 4.2.0, nếu client đặt `spring.cloud.config.send-all-labels=true`, client gửi danh sách label trong một request. Để server trả về property source của tất cả label, Config Server cũng phải từ 4.2.0 trở lên. Thuộc tính `send-all-labels` mặc định là `false` để giữ hành vi tương thích cũ.

Ví dụ:

```yaml
spring:
  cloud:
    config:
      label: feature-billing,develop
      send-all-labels: true
```

Nếu bật `send-all-labels=true` nhưng server cũ hơn 4.2.0, server có thể coi chuỗi `feature-billing,develop` là một label duy nhất thay vì tách thành nhiều label. Điều này có thể dẫn tới không tìm thấy cấu hình hoặc response khác dự kiến.

Khi nâng cấp theo từng bước:

1. Giữ `send-all-labels=false` nếu server/client chưa đồng bộ khả năng.
2. Nâng server lên phiên bản hỗ trợ trước.
3. Kiểm thử response với danh sách label ở endpoint thật.
4. Nâng client và bật `send-all-labels` nếu cần một request kết hợp.
5. So sánh thứ tự property source khi nhiều label cùng chứa một key.

## 5. Thay đổi retry trong Config Client 5.1

Trong các phiên bản trước Spring Cloud Config 5.1, retry khi khởi động thường được kích hoạt bằng cách thêm Spring Retry vào classpath. Từ 5.1, Config Client dùng retry support của Spring Framework; Spring Retry không còn là cơ chế bắt buộc. Để giữ hành vi retry, cần bật rõ:

```yaml
spring:
  cloud:
    config:
      fail-fast: true
      retry:
        enabled: true
        max-attempts: 6
        initial-interval: 1s
        multiplier: 1.1
        max-interval: 2s
```

Giá trị mặc định hiện được tài liệu mô tả là 6 lần thử, gồm lần gọi ban đầu và tối đa 5 lần retry; backoff ban đầu 1000 ms, multiplier 1.1. Hãy cấu hình rõ theo SLO startup của ứng dụng, không phụ thuộc vào default khi nâng cấp.

Nếu `spring.config.import` nằm trong file profile-specific như `application-prod.yml`, cấu hình retry có thể cần đặt dưới dạng query parameter trên import location để có mặt đúng thời điểm Config Data xử lý location:

```properties
spring.config.import=configserver:https://config.internal:8888?fail-fast=true&max-attempts=10&max-interval=1500&multiplier=1.2&initial-interval=1100
```

Tài liệu hiện hành cũng đánh dấu `spring.cloud.config.retry.useRandomPolicy` là deprecated. Khi nâng cấp, kiểm tra cảnh báo deprecation và không tiếp tục dựa vào thuộc tính sắp bị loại bỏ.

## 6. Thay đổi failover khi khai báo nhiều Config Server URL

Client có thể dùng nhiều Config Server URL để tăng khả năng sẵn sàng:

```yaml
spring:
  cloud:
    config:
      uri: https://config-a.internal:8888,https://config-b.internal:8888
```

Theo tài liệu hiện hành, `spring.cloud.config.multiple-uri-strategy` mặc định là `always`: client thử các URL theo thứ tự cho đến khi một lần lấy cấu hình thành công. Nếu đặt `connection-timeout-only`, client chỉ failover khi Config Server không chạy hoặc kết nối timeout; các lỗi như HTTP 500 hoặc 401 không nhất thiết chuyển sang URL tiếp theo vì có thể là lỗi ứng dụng hoặc credential.

Điểm khác biệt quan trọng: khi khai báo nhiều URL bằng nhiều location trong `spring.config.import`, các location được xử lý theo thứ tự và location sau có ưu tiên cao hơn. `multiple-uri-strategy` không áp dụng cho trường hợp nhiều URL được khai báo dưới dạng các import location. Nếu `fail-fast=true`, client có thể dừng khi lần gọi đầu tiên thất bại; nếu `false`, client thử các location tiếp theo theo quy tắc Config Data.

Không chỉ kiểm tra URL còn sống. Hãy kiểm tra mỗi server có cùng repository, label và revision. Failover sang server đang phục vụ revision cũ có thể làm ứng dụng nhận cấu hình khác nhau tùy URL được chọn.

## 7. Đánh giá property source precedence sau nâng cấp

Một ứng dụng có thể chạy thành công nhưng nhận giá trị khác sau nâng cấp vì thứ tự property source thay đổi hoặc do chuyển từ bootstrap sang Config Data.

Với Config Data, imported configuration có độ ưu tiên cao hơn tài liệu khai báo import. Khi có nhiều location trong `spring.config.import`, location khai báo sau có độ ưu tiên cao hơn location trước. Các nguồn có ưu tiên cao của Spring Boot như command-line arguments, system properties và environment variables vẫn có thể ghi đè giá trị import.

Với legacy bootstrap, remote property source thường có ưu tiên cao hơn local config và mặc định không cho local override. Các cờ `spring.cloud.config.allow-override`, `override-none` và `override-system-properties` điều khiển cách cho phép override. Những cờ này phải được đặt trong remote property source; đặt `allow-override` trong local config không cấp quyền override remote source.

Ví dụ remote property source:

```yaml
spring:
  cloud:
    config:
      allow-override: true
      override-none: false
      override-system-properties: false
```

Không chuyển nguyên xi các cờ bootstrap sang Config Data mà không kiểm tra lại kết quả. Hãy viết test có cùng key trong remote config, `application.yml`, environment variable và command line; sau đó xác minh giá trị cuối cùng trong từng mô hình.

## 8. Kiểm tra response contract của Config Server

Config Server cung cấp cấu hình qua endpoint có dạng:

```text
/{application}/{profile}/{label}
```

Ví dụ:

```bash
curl -sS \
  https://config.internal:8888/billing-api/prod/release-2026
```

Khi nâng cấp, so sánh các trường response:

- `name`: application được phân giải.
- `profiles`: profile mà server xử lý.
- `label`: label/revision được chọn.
- `version`: revision backend nếu có.
- `propertySources`: tên, thứ tự và nội dung các property source.

Không chỉ so sánh giá trị cuối cùng. Tên và thứ tự property source cũng có thể ảnh hưởng chẩn đoán, audit hoặc custom client code. Nếu ứng dụng tự parse JSON response hoặc phụ thuộc vào tên source, hãy coi đó là contract cần test.

Trong Config Client mới, Config Data có thể thực hiện request `default` rồi request profile-specific. Hãy xác minh server xử lý đúng cả hai request, nhất là khi remote config có `spring.profiles.active` hoặc `spring.profiles.include`.

## 9. Thay đổi bảo mật và OAuth2 trong các dòng mới

Spring Cloud Config 2026.0.0 bổ sung hỗ trợ OAuth2 ở Config Client để client có thể ủy quyền truy cập Config Server qua access token. Tính năng này cần cấu hình OAuth2 client registration và dependency Spring Security OAuth2 Client theo tài liệu của release train; không giả định chỉ đặt `issuer-uri` ở client là đủ.

Ví dụ cấu hình khái quát:

```yaml
spring:
  cloud:
    config:
      uri: https://config.internal:8888
      oauth2:
        enabled: true
        client-registration-id: config-client
  security:
    oauth2:
      client:
        registration:
          config-client:
            client-id: ${CONFIG_CLIENT_ID}
            client-secret: ${CONFIG_CLIENT_SECRET}
            authorization-grant-type: client_credentials
        provider:
          config-client:
            token-uri: https://identity.internal/oauth/token
```

Client cần dependency `spring-boot-starter-oauth2-client` hoặc artifact tương ứng được tài liệu phiên bản yêu cầu. Credential phải được cấp từ secret manager; không ghi vào Git.

### Các lỗ hổng bảo mật cần đưa vào upgrade assessment

Ngày 19/11/2026, Spring công bố các advisory cho Spring Cloud Config:

| CVE | Vấn đề | Hành động |
| --- | --- | --- |
| CVE-2026-59435 | Backend Git/SVN URI có userinfo chứa credential có thể làm lộ credential trong tên property source của response | Không nhúng credential trong URI; dùng SSH key hoặc username/password property riêng và nâng lên bản đã sửa |
| CVE-2026-59436 | Một số cấu hình SSH property-based không kiểm tra host key đúng như mong đợi | Nâng lên bản đã sửa; rà soát `ignoreLocalSshSettings`, `hostKey`, `hostKeyAlgorithm` |
| CVE-2026-59437 | Cấu hình Git SSH property-based thiếu host key tường minh có thể vô hiệu hóa strict host key checking | Khai báo/pin host key và nâng lên bản đã sửa |

Spring liệt kê các dòng bị ảnh hưởng gồm Config 5.0.0–5.0.6, 4.3.0–4.3.5, 4.0.0–4.2.9 và 3.1.0–3.1.15. Các bản sửa tương ứng được công bố là 5.0.7, 4.3.6, 4.2.10 và 3.1.16; một số bản thuộc Enterprise Support. Hãy kiểm tra trang advisory để xác định đúng kênh phát hành và trạng thái hỗ trợ trước khi chọn bản vá.

Ví dụ Git HTTPS nên tách credential khỏi URI:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.internal/platform/config-repo.git
          username: ${CONFIG_GIT_USERNAME}
          password: ${CONFIG_GIT_PASSWORD}
```

Với SSH property-based, khi bật `ignoreLocalSshSettings=true`, cần khai báo host key/algorithm theo tài liệu và kiểm tra strict host key behavior. Không tắt xác minh host key để xử lý lỗi kết nối.

## 10. Những thay đổi đáng chú ý của Spring Cloud 2026.0.0

Tại thời điểm viết bài, 2026.0.0 (Paddington) là release train GA mới, dựa trên Spring Boot 4.2.0 và Spring Cloud Config 5.1.0. Một số điểm cần đánh giá:

- Spring Cloud Bus không còn là project độc lập trong release train này mà được tích hợp vào Spring Cloud Stream. Các tọa độ artifact Bus hiện có vẫn được giữ để giảm ảnh hưởng cho dự án đang phụ thuộc.
- Config Client bổ sung hỗ trợ OAuth2 để ủy quyền với Config Server.
- Config Server có thêm HTTP property path notifier.
- Git backend hỗ trợ Azure DevOps workload identity.
- Google Cloud Storage được bổ sung làm backend Config Server.
- Có thể lấy plain text và binary resource từ Config Server thông qua `ConfigResourceClient`.
- AWS S3 environment repository có thể dùng `S3Client` bean từ application context.
- `ConfigServerRestClientHolder` được public để ứng dụng/thư viện tái sử dụng RestClient dùng nạp cấu hình.

Không phải mọi thay đổi đều yêu cầu sửa code. Hãy phân loại thành API mới, behavior change, security fix, dependency change và chỉ cập nhật phần ứng dụng thực sự sử dụng. Đặc biệt, việc Bus được chuyển vị trí dự án không đồng nghĩa phải tự thay đổi mọi artifact hoặc topology; kiểm tra release notes và dependency tree trước khi sửa.

## 11. AOT và native image

Spring Cloud Config Client hỗ trợ Spring AOT transformation và GraalVM native image từ dòng 4.0. Tuy nhiên, Config First Bootstrap/legacy processing không được hỗ trợ trong AOT/native theo tài liệu hiện hành.

Các giới hạn cần kiểm tra:

- Dùng Config Data import thay cho legacy bootstrap khi chạy AOT/native.
- `@RefreshScope` không được hỗ trợ trong native image; đặt `spring.cloud.refresh.enabled=false`.
- Nguồn cấu hình mà client kết nối trong quá trình build AOT cần sẵn sàng theo yêu cầu của build.
- Giá trị ảnh hưởng tới bean creation phải nhất quán giữa build time và runtime.
- Startup native vẫn cần thời gian kết nối Config Server để nạp cấu hình; thời gian khởi động ứng dụng không chỉ là thời gian khởi tạo process.

Ví dụ:

```yaml
spring:
  config:
    import: "configserver:https://config.internal:8888"
  cloud:
    refresh:
      enabled: false
```

Nếu đang dùng native image, không lấy việc refresh thành công trên JVM làm bằng chứng native runtime có cùng khả năng.

## 12. Server và Client không nhất thiết nâng cấp cùng một thời điểm

Trong môi trường lớn, có thể triển khai nâng cấp theo nhiều giai đoạn. Nhưng trước khi tách thời điểm deploy, cần xác định tính tương thích giao thức giữa phiên bản client và server.

Một số tính năng yêu cầu cả hai phía hỗ trợ, ví dụ multi-label request từ Config Client 4.2.0 cần Config Server 4.2.0 trở lên để trả property source của nhiều label. Một client mới có thể gọi được server cũ ở chế độ tương thích mặc định, nhưng khi bật tính năng giao thức mới thì server cũ có thể không hiểu request.

Chiến lược nâng cấp an toàn:

1. Chọn cặp release train/Spring Boot hợp lệ và xác định phiên bản server/client mục tiêu.
2. Đọc release notes của cả Config Server, Config Client và Spring Cloud Commons/Stream liên quan.
3. Tắt hoặc giữ mặc định các tính năng giao thức mới cho tới khi toàn bộ server pool hỗ trợ.
4. Nâng server theo rolling deployment, kiểm tra response contract và backend.
5. Nâng một nhóm client canary, kiểm tra startup, precedence, retry và refresh.
6. Mở rộng client theo nhóm sau khi xác nhận không có behavior drift.
7. Bật tính năng mới có yêu cầu server/client đồng bộ sau cùng.

Thứ tự cụ thể có thể khác nếu migration yêu cầu server và client thay đổi đồng thời. Không áp dụng một quy tắc “luôn nâng server trước” cho mọi phiên bản; dựa vào compatibility note của tính năng đang bật.

## 13. Ma trận kiểm thử trước và sau nâng cấp

Tạo một bộ contract test chạy trên cả phiên bản hiện tại và phiên bản mục tiêu:

| Nhóm | Test case | Kết quả cần so sánh |
| --- | --- | --- |
| Startup | Config Data import, optional/mandatory | Startup success/failure đúng chính sách |
| Profile | Default profile, active profile, profile được remote kích hoạt | Request sequence và property source đúng |
| Label | Branch, tag, commit, danh sách label | Label/version và property source order |
| Precedence | Remote/local/env/system/command-line cùng key | Giá trị cuối cùng không đổi ngoài chủ đích |
| Retry | Config Server timeout, 401, 500, server unavailable | Số lần thử, backoff, failover và thời gian startup |
| Multi URL | Một server down, một server trả lỗi | URL được chọn theo multiple-uri-strategy |
| Backend | Git branch không tồn tại, remote offline, SSH key sai | Status, fallback, log và revision |
| Security | Basic, OAuth2, TLS, Git SSH host key | Authentication/authorization và không lộ credential |
| Encryption | `{cipher}` giải mã thành công/thất bại | Plaintext không xuất hiện trong log hoặc response sai |
| Refresh | `/actuator/refresh`, Bus event, `@RefreshScope` | Environment và bean lifecycle đúng |
| Native/AOT | Build và startup native nếu dùng | Hỗ trợ, thời gian nạp và cấu hình startup |
| Health | Config Client health indicator | Status, cache TTL và backend outage behavior |

Nên lưu response mẫu đã loại bỏ secret, metadata revision, log đã mask, metric latency và kết quả bean binding. So sánh có cấu trúc thay vì chỉ nhìn log khởi động.

## 14. Ví dụ contract test cho Config Server response

Một test HTTP có thể gọi endpoint đại diện trước và sau nâng cấp rồi so sánh các trường quan trọng. Pseudocode:

```java
record ConfigSnapshot(
        String name,
        List<String> profiles,
        String label,
        String version,
        Map<String, Object> effectiveProperties) {
}

void assertConfigContract(ConfigSnapshot actual,
                          ConfigSnapshot expected) {
    assertThat(actual.name()).isEqualTo(expected.name());
    assertThat(actual.profiles()).containsExactlyElementsOf(expected.profiles());
    assertThat(actual.label()).isEqualTo(expected.label());
    assertThat(actual.effectiveProperties())
            .containsAllEntriesOf(expected.effectiveProperties());
}
```

Đây là pseudocode minh họa; response JSON thật có cấu trúc `propertySources` và `version` tùy backend. Không so sánh ciphertext hoặc secret plaintext trong test report. Với Git backend, có thể cố định commit SHA để tránh branch di chuyển làm kết quả test khác nhau.

Ngoài response test, khởi động một Config Client mẫu với đúng phiên bản Boot/Cloud mục tiêu và xác minh bean `@ConfigurationProperties`. Điều này phát hiện lỗi mà chỉ gọi HTTP endpoint không thấy được, chẳng hạn thay đổi conversion, validation hoặc precedence.

## 15. Quy trình nâng cấp theo từng giai đoạn

### Giai đoạn A — Inventory và baseline

- Ghi phiên bản Spring Boot, Spring Cloud train, Config Server, Config Client và binder.
- Ghi cách dùng bootstrap/Config Data, URI, name, profile, label, retry, security và refresh.
- Chụp baseline response cho các application/profile/label quan trọng.
- Kiểm kê custom `EnvironmentRepository`, custom client interceptor, `RestTemplate`/`RestClient` và code parse response.

### Giai đoạn B — Đọc release notes và phân loại thay đổi

Phân loại mỗi thay đổi:

- **Breaking:** yêu cầu sửa cấu hình hoặc code.
- **Behavior change:** API vẫn chạy nhưng kết quả/thứ tự/timing thay đổi.
- **Deprecation:** còn hoạt động nhưng cần kế hoạch thay thế.
- **Security fix:** cần nâng cấp khẩn hoặc mitigation.
- **New feature:** chỉ bật sau khi server/client và quy trình vận hành hỗ trợ.

### Giai đoạn C — Compatibility test

- Chạy contract test với server mới/client cũ và server mới/client mới nếu rollout cần hỗ trợ chéo.
- Kiểm tra label, property source precedence, retry, failover và authentication.
- Test Git backend khi remote offline, SSH host key mismatch và repository chưa clone.
- Kiểm tra Bus và refresh event ở nhiều instance.

### Giai đoạn D — Canary và rollout

- Nâng Config Server theo nhóm nhỏ, quan sát latency, error rate và revision.
- Nâng client canary với một application/profile/label đại diện.
- So sánh giá trị cấu hình cuối cùng và bean binding.
- Mở rộng theo nhóm; giữ khả năng rollback về artifact và config revision đã biết.

### Giai đoạn E — Bật tính năng mới và dọn migration

- Bật multi-label request, OAuth2 client hoặc behavior mới sau khi đủ server/client.
- Xóa legacy bootstrap hoặc Spring Retry dependency nếu không còn dùng.
- Xóa property deprecated và custom compatibility code không còn cần.
- Cập nhật runbook, dependency catalog và ma trận version được hỗ trợ.

## 16. Rollback và tương thích cấu hình

Rollback binary không tự động rollback cấu hình. Nếu phiên bản mới đã đọc cấu hình có schema khác hoặc đã ghi giá trị mới vào backend, phiên bản cũ có thể không hiểu cấu hình đó.

Một quy trình rollback cần:

1. Ghi lại artifact version và Config Server label/revision trước rollout.
2. Duy trì cấu hình tương thích ngược trong giai đoạn chuyển tiếp.
3. Không xóa key cũ cho tới khi mọi client cũ đã được thay thế.
4. Khi rollback, khôi phục cả binary và config label nếu cần.
5. Xác minh startup, property precedence, bean binding và refresh trên phiên bản quay lại.

Với thay đổi schema cấu hình, có thể áp dụng mô hình expand–migrate–contract: thêm key mới mà vẫn giữ key cũ, triển khai code đọc được cả hai, chuyển nguồn ghi, sau đó mới xóa key cũ ở một release sau.

## 17. Checklist đánh giá nâng cấp

- [ ] Spring Boot và Spring Cloud release train nằm trong ma trận tương thích.
- [ ] Dùng BOM nhất quán, không override module ngẫu nhiên.
- [ ] Đã đọc release notes của Config Server, Config Client và train.
- [ ] Đã xác định Config Data hay legacy bootstrap.
- [ ] Đã kiểm tra số request startup và profile activation.
- [ ] Đã kiểm tra property source precedence và override flags.
- [ ] Đã kiểm tra label đơn/nhiều label và `send-all-labels`.
- [ ] Đã kiểm tra retry, backoff, fail-fast và multiple-uri-strategy.
- [ ] Đã kiểm tra response `Environment`, property source name/order, version và label.
- [ ] Đã kiểm tra Git/Vault/backend, cache, SSH host key và credential.
- [ ] Đã xử lý advisory bảo mật và nâng lên bản vá tương ứng.
- [ ] Đã kiểm tra OAuth2, Basic Auth, TLS và quyền theo application.
- [ ] Đã kiểm tra Actuator, refresh, Bus và lifecycle của bean.
- [ ] Đã kiểm tra AOT/native nếu có triển khai.
- [ ] Có contract test, canary, rollback binary và rollback config revision.
- [ ] Đã cập nhật runbook và ma trận version nội bộ.

## 18. Tài liệu tham khảo chính thức

- [Spring Cloud — Version compatibility](https://spring.io/projects/spring-cloud/): ma trận release train và Spring Boot.
- [Spring Cloud 2026.0.0 release announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/): Spring Boot 4.2.0, Config 5.1.0, OAuth2 client và các thay đổi train.
- [Spring Cloud Config Client reference](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data, bootstrap, retry, labels, multiple URLs, security và AOT.
- [Spring Cloud Context](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): bootstrap property source và remote override behavior.
- [Spring Cloud Config security advisory CVE-2026-59435](https://spring.io/security/cve-2026-59435/): lộ credential Git/SVN trong property source name.
- [Spring Cloud Config security advisory CVE-2026-59436](https://spring.io/security/cve-2026-59436/): xác minh SSH host key.
- [Spring Cloud Config security advisory CVE-2026-59437](https://spring.io/security/cve-2026-59437/): nguy cơ MITM khi dùng Git SSH.

Đánh giá nâng cấp Config Server và Config Client cần dựa trên hành vi quan sát được của cả hai phía. Ma trận tương thích giúp chọn bộ version hợp lệ; contract test xác nhận request, response, precedence và retry; kiểm thử backend, security và refresh phát hiện thay đổi ngoài giao thức. Nâng cấp theo giai đoạn, giữ cấu hình tương thích ngược và chuẩn bị rollback cả binary lẫn revision cấu hình sẽ giảm rủi ro khi thay đổi release train.

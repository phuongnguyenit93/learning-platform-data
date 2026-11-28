# Lỗi khởi động do optional, fail-fast, retry hoặc timeout

Spring Cloud Config Client thường lấy cấu hình remote trong giai đoạn khởi động ứng dụng. Nếu Config Server chưa sẵn sàng, mạng bị gián đoạn, xác thực thất bại hoặc backend Git không đọc được repository, quá trình nạp cấu hình có thể làm Spring Boot khởi động chậm hoặc thất bại.

Các tùy chọn `optional`, `fail-fast`, `retry` và `timeout` quyết định ứng dụng phản ứng thế nào trước những lỗi này. Chúng giải quyết các vấn đề khác nhau: `optional` cho phép bỏ qua một nguồn cấu hình không khả dụng theo cơ chế Config Data; `fail-fast` quyết định có dừng khởi động khi không lấy được cấu hình hay không trong các chế độ hỗ trợ; `retry` thử lại lỗi có thể phục hồi; `timeout` giới hạn thời gian chờ. Cấu hình sai có thể khiến ứng dụng khởi động bằng giá trị mặc định không an toàn hoặc chờ quá lâu trước khi báo lỗi.

## 1. Phân loại lỗi trước khi thay đổi cấu hình

Khi ứng dụng không khởi động được do Config Server, trước hết cần xác định lỗi xảy ra ở lớp nào:

| Lớp | Ví dụ lỗi | Dấu hiệu thường gặp |
|---|---|---|
| DNS/network | Không phân giải được hostname, connection refused, route bị chặn | Không thiết lập được TCP connection đến Config Server. |
| TLS | Certificate không tin cậy, hostname không khớp, handshake thất bại | Kết nối tới host được nhưng HTTPS handshake lỗi. |
| HTTP/authentication | `401`, `403`, token hết hạn hoặc credential sai | Config Server trả HTTP response nhưng từ chối caller. |
| Config Server | Server quá tải, lỗi xử lý request hoặc trả `5xx` | Endpoint có thể truy cập nhưng request thất bại. |
| Backend repository | Git server không truy cập được, credential Git sai, branch/label không tồn tại | Config Server nhận request nhưng không lấy được property source mong muốn. |
| Selector | Sai application name, profile hoặc label | Server trả cấu hình rỗng/không đúng phạm vi hoặc không tìm thấy tài liệu. |
| Nội dung cấu hình | YAML sai cú pháp, kiểu dữ liệu không hợp lệ, thiếu property bắt buộc | Remote response có thể được tải nhưng ứng dụng lỗi khi parse, bind hoặc validate. |

Không nên tăng retry hoặc timeout trước khi biết lỗi thuộc nhóm nào. Retry hữu ích với lỗi tạm thời; nó không sửa được sai mật khẩu, ACL, path, branch hoặc YAML.

## 2. Optional Config Data import

Với Config Data API, ứng dụng thường khai báo Config Server trong `spring.config.import`:

```yaml
spring:
  application:
    name: orders-service
  config:
    import: "configserver:http://config-server:8888"
```

Đây là import bắt buộc. Nếu Config Server không thể cung cấp nguồn cấu hình trong quá trình nạp Config Data, ứng dụng sẽ không khởi động thành công.

Thêm tiền tố `optional:` để cho phép ứng dụng tiếp tục khi nguồn Config Server không khả dụng:

```yaml
spring:
  config:
    import: "optional:configserver:http://config-server:8888"
```

`optional:` là quyết định về mức độ bắt buộc của nguồn cấu hình. Khi nguồn remote không thể được nạp theo điều kiện optional, Spring Boot có thể tiếp tục với các nguồn còn lại như file local, biến môi trường và system properties. Vì vậy, ứng dụng có thể chạy với giá trị mặc định hoặc giá trị cũ trong local config.

Chỉ dùng optional khi ứng dụng thực sự có thể hoạt động an toàn mà không có remote config. Nếu Config Server cung cấp database credential, OAuth issuer, endpoint thanh toán hoặc policy bảo mật bắt buộc, bỏ qua nguồn cấu hình có thể khiến ứng dụng chạy sai môi trường hoặc không an toàn.

Không nên hiểu `optional:` là “bỏ qua mọi lỗi”. Lỗi tải nguồn, lỗi parse nội dung, lỗi binding/validation và lỗi nghiệp vụ có thể có cách xử lý khác nhau tùy giai đoạn và phiên bản. Hãy kiểm thử riêng tình huống server không truy cập được, response sai định dạng và property bắt buộc bị thiếu.

## 3. Khi nào dùng fail-fast?

Fail-fast có nghĩa là dừng khởi động sớm nếu không lấy được cấu hình cần thiết. Đây thường là lựa chọn phù hợp khi remote config là dependency bắt buộc để ứng dụng hoạt động đúng.

Trong chế độ bootstrap cũ, có thể cấu hình:

```yaml
spring:
  cloud:
    config:
      uri: https://config.internal:8888
      fail-fast: true
```

Với bootstrap context, `spring.cloud.config.fail-fast=true` yêu cầu Config Client thất bại khi không thể kết nối/đọc cấu hình từ Config Server theo cơ chế của phiên bản đang dùng. Nếu để fail-fast tắt, client có thể tiếp tục khởi động mà không có remote property source, tùy cấu hình và lỗi.

Với Config Data API, import không có `optional:` đã mang ý nghĩa bắt buộc. Không nên sao chép nguyên xi giả định của bootstrap cũ sang Config Data. Hãy dùng `optional:` để biểu đạt rõ nguồn có được phép vắng mặt hay không; các query parameter của import có thể bật fail-fast cho retry như phần sau.

### Quyết định theo mức độ quan trọng của cấu hình

| Loại cấu hình | Chính sách thường phù hợp |
|---|---|
| Secret hoặc credential bắt buộc | Không optional; fail startup nếu không lấy được. |
| Database endpoint production | Không optional nếu thiếu endpoint khiến ứng dụng không thể phục vụ an toàn. |
| Feature flag không quan trọng, có default an toàn | Có thể optional nếu đã xác định rõ fallback. |
| Logging/tracing tùy chọn | Có thể dùng local default khi remote source tạm thời vắng mặt. |
| Cấu hình dùng chung ảnh hưởng nhiều service | Quyết định theo từng consumer; không mặc định cho phép tất cả client bỏ qua. |

Fail-fast giúp tránh trạng thái “khởi động xanh nhưng dùng cấu hình sai”. Đổi lại, hệ thống triển khai cần có retry/backoff và readiness/startup budget đủ để Config Server phục hồi trong thời gian cho phép.

## 4. Retry xử lý lỗi tạm thời

Retry cho phép Config Client thử lại khi Config Server tạm thời chưa sẵn sàng. Những trường hợp có thể phục hồi gồm:

- Config Server đang khởi động hoặc vừa restart.
- Network tạm thời mất kết nối hoặc connection reset.
- Reverse proxy/load balancer chưa có backend healthy.
- Config Server hoặc Git backend tạm thời trả lỗi `5xx`.
- Một lần request vượt timeout do tải tăng đột biến.

Retry nên có giới hạn và backoff tăng dần để không tạo thêm tải lên server đang gặp sự cố. Một chính sách thường dùng là exponential backoff: mỗi lần thử sau chờ lâu hơn lần trước, nhưng thời gian nghỉ không vượt mức tối đa.

Các lỗi như `401`, `403`, sai token, sai Git credential, sai application/profile/label hoặc YAML không hợp lệ thường cần sửa nguyên nhân. Thử lại liên tục chỉ kéo dài thời gian khởi động và làm log khó đọc. Tùy HTTP client và retry policy, một số lỗi vẫn có thể bị thử lại; nếu cần, cấu hình policy để phân biệt lỗi transient với lỗi permanent.

## 5. Bật retry với Config Data API

Với Config Data API, các tham số retry có thể được truyền trực tiếp trong URI `configserver:`. Ví dụ:

```yaml
spring:
  config:
    import: "configserver:https://config.internal:8888?fail-fast=true&max-attempts=8&initial-interval=1000&max-interval=5000&multiplier=1.5"
```

Ý nghĩa:

| Tham số | Ý nghĩa |
|---|---|
| `fail-fast=true` | Yêu cầu xử lý lỗi kết nối theo chế độ fail-fast để retry có thể áp dụng. |
| `max-attempts=8` | Giới hạn tổng số lần thử theo cách đếm của retry implementation. |
| `initial-interval=1000` | Khoảng nghỉ ban đầu, tính bằng mili giây. |
| `max-interval=5000` | Giới hạn khoảng nghỉ giữa các lần thử. |
| `multiplier=1.5` | Hệ số tăng khoảng nghỉ sau mỗi lần thử. |

Để retry hoạt động, dự án cần các dependency Spring Retry và Spring AOP theo hướng dẫn của release train đang dùng. Ví dụ Gradle:

```gradle
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-config'
    implementation 'org.springframework.retry:spring-retry'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

Giữ URI trong dấu nháy vì query string chứa ký tự `&`. Tên tham số và cách hỗ trợ retry phụ thuộc phiên bản Spring Cloud Config; xác minh với release train của dự án khi nâng cấp.

Với Config Data API, không nên chỉ đặt retry properties trong remote repository vì Config Client cần các tham số đó trước khi tải được remote configuration. Khai báo retry tại vị trí local/bootstrap phù hợp, hoặc dùng query parameter của import như ví dụ.

## 6. Retry trong bootstrap context cũ

Ứng dụng legacy sử dụng bootstrap context có thể cấu hình retry bằng các thuộc tính `spring.cloud.config.retry.*`:

```yaml
spring:
  cloud:
    config:
      uri: https://config.internal:8888
      fail-fast: true
      retry:
        max-attempts: 8
        initial-interval: 1000
        max-interval: 5000
        multiplier: 1.5
```

Đặt cấu hình này trong `bootstrap.yml` hoặc nguồn bootstrap local được nạp trước khi Config Client gọi Config Server. Thêm `spring-retry` và Spring AOP theo yêu cầu của phiên bản. Nếu retry config chỉ nằm trong remote Config Server thì nó không thể giúp lần kết nối đầu tiên, vì client chưa tải được nguồn chứa chính cấu hình retry đó.

Không trộn cấu hình bootstrap legacy với Config Data API mà không hiểu thứ tự khởi tạo. Nếu ứng dụng đang dùng `spring.config.import`, ưu tiên cấu hình retry theo cú pháp Config Data của phiên bản đó.

## 7. Tính toán ngân sách retry và thời gian khởi động

Tổng thời gian chờ không chỉ là tổng khoảng backoff. Mỗi lần thử còn tiêu tốn thời gian DNS, TCP connect, TLS handshake, HTTP request, Config Server xử lý và đọc backend Git.

Có thể ước lượng:

```text
Startup config budget
  = tổng thời gian các request
  + tổng thời gian backoff giữa các lần thử
  + thời gian parse/bind/validate cấu hình
  + phần thời gian khởi tạo ứng dụng còn lại
```

Ví dụ, nếu mỗi request có thể mất vài giây và retry nhiều lần, ứng dụng có thể vượt startup deadline của nền tảng trước khi hoàn tất. Cần đặt số lần thử, timeout và startup budget cùng nhau.

Một nguyên tắc thực tế:

- Đặt timeout mỗi request đủ dài cho độ trễ bình thường và tải cao hợp lý.
- Giới hạn retry để không chờ vô hạn.
- Dùng backoff để tránh request dồn dập.
- Bảo đảm startup probe/deployment timeout lớn hơn ngân sách khởi động dự kiến.
- Không tăng timeout đến mức che giấu server treo hoặc backend Git bị lỗi kéo dài.

Khi triển khai nhiều replica cùng lúc, thêm jitter nếu retry mechanism hỗ trợ để các instance không retry đồng thời. Điều này giảm nguy cơ thundering herd khi Config Server vừa phục hồi.

## 8. Phân biệt các lớp timeout

Không có một timeout duy nhất điều khiển toàn bộ quá trình lấy cấu hình:

| Lớp timeout | Phạm vi | Cần kiểm tra |
|---|---|---|
| DNS resolution | Phân giải hostname Config Server | DNS resolver, search domain, record và thời gian phản hồi. |
| TCP connect | Thiết lập socket đến host/port | Network policy, firewall, route và connect timeout của HTTP client. |
| TLS handshake | Thỏa thuận TLS và xác minh certificate | CA, truststore, hostname, certificate expiry và handshake timeout. |
| HTTP read/response | Chờ Config Server trả body | Read timeout, server processing, proxy timeout và Git backend latency. |
| Config Server backend | Config Server đọc Git/Vault/Consul hoặc backend khác | Backend timeout, repository availability, auth và server logs. |
| Orchestrator startup | Thời gian nền tảng chờ process/container sẵn sàng | Startup probe, readiness probe, deployment progress deadline. |

Config Client có các thuộc tính request timeout như `spring.cloud.config.request-connect-timeout` và `spring.cloud.config.request-read-timeout` trong các phiên bản hỗ trợ. Đơn vị thường là mili giây; xác minh tên và hỗ trợ chính xác theo phiên bản Config Client và HTTP transport đang dùng.

Ví dụ minh họa:

```yaml
spring:
  cloud:
    config:
      request-connect-timeout: 3000
      request-read-timeout: 10000
```

Nếu dùng custom HTTP client, load balancer hoặc service mesh, timeout có thể được đặt ở nhiều lớp. Cần tránh trường hợp proxy cắt request sau 5 giây trong khi client chờ 10 giây, hoặc retry bắt đầu trước khi request trước thực sự được kết thúc.

## 9. Optional và fallback an toàn

Nếu chọn optional, cần thiết kế fallback rõ ràng. Ví dụ một ứng dụng có thể cho phép thiếu cấu hình tracing nhưng không được phép thiếu database endpoint hoặc signing key.

Một cấu hình local có thể cung cấp default không nhạy cảm:

```yaml
app:
  observability:
    tracing-enabled: false
    sample-rate: 0.0
```

Nhưng không nên cung cấp credential giả hoặc endpoint production mặc định để ứng dụng “cứ chạy”. Với property bắt buộc, dùng validation khi startup:

```java
@Validated
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    @NotBlank
    private String endpoint;

    @NotBlank
    private String credentialReference;

    // getters and setters
}
```

Nếu remote config không đến và local fallback không có `endpoint` hoặc `credentialReference`, validation sẽ làm ứng dụng khởi động thất bại. Điều này giúp phát hiện optional source đã bị bỏ qua trong khi cấu hình thực sự là bắt buộc.

Với secret, ưu tiên lấy từ secret manager hoặc Vault. Không dùng chuỗi mặc định như `password: changeme` trong production. Fallback phải được đánh giá theo threat model và môi trường, không chỉ theo khả năng giúp process khởi động.

## 10. Config Server sẵn sàng nhưng backend Git chưa sẵn sàng

Một tình huống dễ nhầm là endpoint HTTP của Config Server đã mở cổng nhưng Git backend chưa clone/fetch được repository. Health check ở mức process có thể báo server đang chạy trong khi request cấu hình vẫn thất bại.

Các nguyên nhân thường gặp:

- Git server chưa sẵn sàng hoặc DNS chưa phân giải được.
- SSH key/token của Config Server hết hạn hoặc sai quyền.
- Branch/tag được client yêu cầu không tồn tại.
- Repository quá lớn, clone/fetch chậm hoặc mạng giữa Config Server và Git bị gián đoạn.
- Config Server dùng local clone cache cũ hoặc không thể cập nhật revision mới.

Khi điều tra, gọi đúng Environment endpoint với application/profile/label:

```bash
curl -i \
  -H "Authorization: Bearer ${CONFIG_SERVER_TOKEN}" \
  "https://config.internal:8888/orders-service/prod/release-stable"
```

Kiểm tra HTTP status, response `version` và danh sách `propertySources`. Chỉ thực hiện trong mạng quản trị; response có thể chứa dữ liệu nhạy cảm nên không paste nguyên văn vào ticket hoặc log công khai.

Nếu Config Server trả cấu hình cũ, đó có thể là lỗi fetch/cache/backend chứ không phải timeout ở Config Client. Kiểm tra log Config Server, repository revision và cơ chế refresh Git backend trước khi tăng retry phía client.

## 11. Phân biệt lỗi tạm thời và lỗi cần sửa

| Tình huống | Có nên retry? | Hành động chính |
|---|---|---|
| Config Server đang restart | Có, trong giới hạn | Backoff và chờ health/readiness phục hồi. |
| Connection reset hoặc timeout mạng ngắn | Có thể | Kiểm tra network và giới hạn số lần thử. |
| HTTP `502`, `503`, `504` | Có thể | Xác minh upstream đang phục hồi; tránh retry đồng loạt không giới hạn. |
| HTTP `401` hoặc `403` | Thường không | Sửa credential, token, role hoặc authorization. |
| Application/profile/label sai | Không | Sửa selector và xác nhận tài liệu tồn tại. |
| Git credential hoặc ACL sai | Không | Sửa quyền truy cập backend. |
| YAML sai cú pháp hoặc property type sai | Không | Sửa nội dung và chạy validation. |
| Property bắt buộc bị thiếu | Không | Bổ sung cấu hình hoặc điều chỉnh contract có review. |
| Config Server trả revision cũ | Retry đơn thuần không đủ | Kiểm tra fetch/cache/label và revision backend. |

Retry mặc định có thể không phân biệt hoàn hảo tất cả trường hợp. Với hệ thống quan trọng, cấu hình retry policy hoặc xử lý lỗi theo loại exception/status phù hợp; đồng thời ghi log nguyên nhân gốc để không nhầm lỗi permanent thành sự cố mạng tạm thời.

## 12. Readiness, liveness và startup probe

Các probe của nền tảng triển khai có vai trò khác nhau:

- **Startup probe:** cho phép ứng dụng có đủ thời gian hoàn thành quá trình khởi động ban đầu trước khi nền tảng bắt đầu đánh giá liveness/readiness theo chu kỳ thông thường.
- **Readiness probe:** quyết định instance có nhận traffic hay chưa. Nếu ứng dụng khởi động optional nhưng thiếu cấu hình bắt buộc, readiness cần phản ánh trạng thái chưa thể phục vụ an toàn.
- **Liveness probe:** phát hiện process bị kẹt hoặc không thể phục hồi. Không nên làm liveness phụ thuộc trực tiếp vào việc Config Server tạm thời mất kết nối nếu ứng dụng vẫn có thể chạy an toàn với cấu hình đã nạp.

Nếu liveness thất bại mỗi khi Config Server mất vài giây, orchestrator có thể restart hàng loạt instance, làm tăng tải và kéo dài outage. Ngược lại, nếu optional khiến ứng dụng khởi động bằng cấu hình thiếu mà readiness vẫn báo healthy, traffic có thể đi vào instance không hoạt động đúng.

Thiết kế probe theo khả năng phục vụ thực tế và chính sách fallback. Không dùng startup probe để che giấu lỗi credential hoặc repository cố định.

## 13. Quy trình chẩn đoán khi startup thất bại

Thực hiện theo thứ tự sau để tìm đúng nguyên nhân:

1. **Xác định cơ chế nạp:** ứng dụng dùng Config Data `spring.config.import` hay bootstrap context cũ?
2. **Xác định import policy:** Config Server là nguồn bắt buộc hay được phép optional?
3. **Đọc exception gốc:** phân biệt DNS, TCP, TLS, HTTP status, backend và parse/binding error.
4. **Kiểm tra selector:** `spring.application.name`, active profile và Config Server label có đúng không?
5. **Kiểm tra Config Server trực tiếp:** gọi Environment endpoint từ cùng network/runtime nếu có thể.
6. **Kiểm tra backend:** Config Server đã đọc được Git/Vault/Consul revision mong muốn chưa?
7. **Kiểm tra authentication:** token, Basic credential, mTLS certificate và quyền đọc.
8. **Đánh giá timeout:** request connect/read, proxy và backend có giới hạn nhất quán không?
9. **Đánh giá retry:** có dependency cần thiết, fail-fast phù hợp, số lần thử và backoff có nằm trong startup budget không?
10. **Xác minh fallback:** nếu optional, ứng dụng có đủ property bắt buộc và readiness có chặn traffic khi thiếu không?

Không tăng đồng thời timeout, retry và probe delay trước khi có bằng chứng. Thay đổi một nhóm tham số mỗi lần giúp xác định yếu tố thực sự giải quyết vấn đề.

## 14. Kiểm thử các kịch bản khởi động

Nên có test xác nhận chính sách startup trong những tình huống đại diện:

| Kịch bản | Cấu hình mong đợi | Assertion |
|---|---|---|
| Config Server sẵn sàng | Import bắt buộc | Ứng dụng khởi động và nhận remote property. |
| Config Server không truy cập được | Import bắt buộc | Startup thất bại sau ngân sách retry/timeout đã định. |
| Config Server không truy cập được | Import optional và fallback an toàn | Ứng dụng có thể khởi động; readiness phản ánh khả năng phục vụ. |
| Config Server phản hồi chậm | Retry và timeout có giới hạn | Startup hoàn tất trong deadline hoặc thất bại có chẩn đoán rõ. |
| Server trả `401`/`403` | Credential sai | Không retry vô hạn; log chỉ ra lỗi xác thực/phân quyền. |
| Application/profile/label sai | Selector không tồn tại | Ứng dụng phát hiện thiếu property bắt buộc hoặc response không đúng. |
| YAML remote không hợp lệ | Nội dung lỗi | Startup thất bại ở bước parse/validation, không bị nhầm thành lỗi mạng. |
| Git backend chưa sẵn sàng | Config Server có thể mở cổng nhưng chưa đọc được repository | Test xác nhận lỗi backend và thời gian phục hồi. |

Có thể dùng WireMock hoặc mock HTTP server để mô phỏng timeout, delay, `5xx`, `401`, `403` và response sai. Với integration test backend thật, dùng repository fixture cố định và không phụ thuộc branch đang được developer cập nhật.

Test retry nên xác nhận số request và thời gian tổng trong một biên cho phép, không assert timestamp chính xác đến mili giây. Test optional cần xác minh ứng dụng không chỉ khởi động mà còn không phục vụ traffic với cấu hình thiếu an toàn.

## 15. Ví dụ cấu hình theo hai chế độ

### Chế độ A: remote config bắt buộc

```yaml
spring:
  application:
    name: orders-service
  config:
    import: "configserver:https://config.internal:8888?fail-fast=true&max-attempts=8&initial-interval=1000&max-interval=5000&multiplier=1.5"
```

Phù hợp khi ứng dụng không thể hoạt động đúng nếu thiếu remote config. Cần có Spring Retry/AOP theo phiên bản, timeout hợp lý và startup budget đủ lớn.

### Chế độ B: remote config có thể vắng mặt

```yaml
spring:
  application:
    name: local-tool
  config:
    import: "optional:configserver:http://config-server:8888"
```

Phù hợp với công cụ hoặc workload có fallback local đã được xác nhận an toàn. Với production service, cần kiểm tra property bắt buộc và readiness trước khi nhận traffic.

Hai chế độ thể hiện hai quyết định vận hành khác nhau. Không nên bật optional chỉ để tránh pipeline deploy đỏ, và không nên tăng retry đến mức che giấu một Config Server hoặc backend bị cấu hình sai.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| App khởi động dù Config Server down nhưng sau đó lỗi database | Import optional và fallback thiếu property bắt buộc. | Bỏ optional hoặc thêm validation/readiness gate phù hợp. |
| App fail ngay dù Config Server chỉ chậm vài giây | Import bắt buộc nhưng chưa có retry hoặc timeout quá ngắn. | Cấu hình retry có giới hạn và timeout theo startup budget. |
| App chờ rất lâu rồi mới fail | Nhiều lần retry cộng request timeout và backoff quá lớn. | Tính tổng thời gian, giảm attempts hoặc timeout phù hợp. |
| Retry không hoạt động | Thiếu Spring Retry/AOP, sai cú pháp Config Data URI hoặc fail-fast chưa được bật theo chế độ cần thiết. | Kiểm tra dependency và cách khai báo theo release train. |
| `401`/`403` lặp lại nhiều lần | Retry đang áp dụng cho lỗi permanent. | Sửa credential/ACL và tinh chỉnh retry policy nếu cần. |
| Config Server health xanh nhưng client vẫn fail | Git/Vault/Consul backend chưa sẵn sàng hoặc selector sai. | Gọi Environment endpoint và kiểm tra log backend. |
| App dùng cấu hình cũ sau khi server phục hồi | Optional source bị bỏ qua lúc startup; client chưa fetch lại hoặc chưa restart/refresh. | Kích hoạt refresh/restart phù hợp và xác minh revision. |
| Kubernetes liên tục restart trong lúc Config Server outage | Liveness/readiness gắn sai với dependency tạm thời hoặc startup budget quá ngắn. | Tách startup/readiness/liveness theo khả năng phục vụ. |

## 17. Tổng kết

- `optional:configserver:` cho phép Config Data import vắng mặt theo chính sách optional; chỉ dùng khi fallback an toàn.
- Import không có `optional:` là nguồn bắt buộc; trong bootstrap legacy, `spring.cloud.config.fail-fast` điều khiển hành vi fail-fast theo cơ chế cũ.
- Retry giúp vượt qua lỗi tạm thời; cần Spring Retry/AOP và cấu hình số lần thử, backoff, fail-fast đúng với chế độ nạp.
- Với Config Data API, retry có thể khai báo qua query parameter của URI `configserver:`; với bootstrap legacy dùng `spring.cloud.config.retry.*` ở bootstrap local.
- Phân biệt DNS, TCP, TLS, HTTP, backend, selector và lỗi parse/binding trước khi thay đổi retry.
- Tính tổng startup budget từ request timeout, số lần thử, backoff và thời gian khởi tạo ứng dụng.
- Không retry vô hạn cho `401`, `403`, sai path/label hoặc YAML lỗi; sửa nguyên nhân gốc.
- Thiết kế startup, readiness và liveness để không nhận traffic với cấu hình thiếu an toàn và không restart hàng loạt khi dependency chỉ gián đoạn tạm thời.
- Kiểm thử cả server unavailable, delayed response, lỗi auth, selector sai, backend chưa sẵn sàng và fallback optional trước production.

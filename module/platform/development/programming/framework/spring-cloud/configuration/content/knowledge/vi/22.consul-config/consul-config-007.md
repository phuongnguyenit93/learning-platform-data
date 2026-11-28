# ACL token, kết nối an toàn và hành vi khi Consul lỗi

## 1. Ba lớp cần bảo vệ khi ứng dụng đọc cấu hình từ Consul

Spring Cloud Consul Config đọc dữ liệu từ Consul Key/Value Store và đưa các giá trị phù hợp vào Spring `Environment`. Trong môi trường production, ứng dụng cần chứng minh mình được phép đọc đúng vùng cấu hình, kết nối đến đúng Consul agent/server và có chính sách xử lý rõ ràng khi Consul không sẵn sàng.

Có ba lớp cần thiết kế cùng nhau:

1. **ACL token và policy** xác định ứng dụng được đọc những key nào trong Consul KV.
2. **TLS/mTLS** bảo vệ dữ liệu trên đường truyền và xác thực đầu bên kia; mTLS còn xác thực ứng dụng nếu Consul yêu cầu client certificate.
3. **Failure policy** xác định ứng dụng có được khởi động khi Consul lỗi hay phải dừng, retry bao lâu và xử lý thế nào nếu Consul mất kết nối sau khi ứng dụng đã chạy.

Một token hợp lệ không thay thế TLS. TLS thành công cũng không cấp quyền đọc KV. Và việc cho ứng dụng khởi động khi Consul lỗi không tự tạo ra cấu hình an toàn thay thế.

## 2. ACL của Consul hoạt động như thế nào?

Consul Access Control Lists (ACLs) kiểm soát quyền truy cập vào API, CLI, UI và các tài nguyên của Consul. Một ACL token gắn với một hoặc nhiều policy, role hoặc service identity. Khi ứng dụng gửi request đến Consul, token xác định những thao tác mà request được phép thực hiện.

Các khái niệm chính:

| Thành phần | Vai trò |
|---|---|
| ACL token | Credential mà client gửi khi gọi Consul API. SecretID là giá trị nhạy cảm cần giữ bí mật. |
| AccessorID | Định danh để quản trị, tra cứu hoặc thu hồi token; không dùng thay SecretID để xác thực request. |
| Policy | Tập các rule cấp hoặc từ chối quyền trên KV, service, node và tài nguyên khác. |
| Role | Nhóm nhiều policy để gán cho token theo vai trò. |
| Default policy | Quyết định hành vi khi không có rule nào khớp. Production nên dùng `deny`. |

ACL có thể được bật trên Consul bằng cấu hình agent. Ví dụ:

```hcl
acl {
  enabled        = true
  default_policy = "deny"
}
```

`default_policy = "deny"` tạo mô hình allowlist: chỉ thao tác được cấp rõ ràng mới được phép. Khi bật ACL trên một datacenter hiện có, phải lập kế hoạch bootstrap token, gán token cho agent, cấp policy cho ứng dụng và triển khai theo rolling sequence; không đổi default policy giữa lúc chưa chuẩn bị token cần thiết cho các agent.

## 3. Xác định đường dẫn KV mà ứng dụng cần đọc

Spring Cloud Consul Config mặc định dùng prefix `config` và context chung `application`. Tên ứng dụng thường lấy từ `spring.application.name`, còn profile lấy từ các profile đang active. Ví dụ với ứng dụng `order-service` chạy profile `prod`, các context phổ biến gồm:

```text
config/order-service,prod/
config/order-service/
config/application,prod/
config/application/
```

Context cụ thể phụ thuộc `spring.cloud.consul.config.prefix`, `default-context`, `name`, `profile-separator`, profile và format lưu trữ. Nếu dùng format `YAML` hoặc `PROPERTIES`, nội dung file được đặt trong một key con, mặc định tên key là `data`. Nếu dùng `FILES`, tên file có thể trở thành key riêng.

Trước khi tạo ACL policy, hãy xem các key thật trong Consul UI/API và ghi lại chính xác prefix ứng dụng cần đọc. Đừng sao chép policy mẫu khi hệ thống đã đổi prefix, separator hoặc format.

## 4. Tạo policy chỉ đọc cấu hình

Ví dụ ứng dụng `order-service` cần đọc cấu hình chung `application` và cấu hình riêng của chính nó. Policy có thể giới hạn quyền vào hai vùng context đó:

```hcl
# Shared configuration for all applications in this environment.
key_prefix "config/application" {
  policy = "read"
}

# Configuration owned by order-service.
key_prefix "config/order-service" {
  policy = "read"
}
```

`read` cho phép đọc KV trong prefix nhưng không sửa hoặc xóa dữ liệu. Ứng dụng chỉ đọc cấu hình không cần quyền `write`, `acl = "write"`, `operator`, `agent` hoặc quyền quản trị cluster.

Tạo policy bằng Consul CLI:

```bash
consul acl policy create \
  -name "order-service-config-read" \
  -description "Read shared and order-service configuration" \
  -rules @order-service-config-read.hcl
```

Nếu hệ thống bật `acl.enable_key_list_policy`, thao tác đọc đệ quy prefix có thể cần quyền `list` trên prefix. Kiểm tra cấu hình ACL của Consul và API mà phiên bản Spring Cloud Consul sử dụng; đừng cấp quyền rộng hơn chỉ để bỏ qua lỗi `permission denied`.

### Phạm vi quyền cần kiểm tra

| Tình huống | Policy cần cân nhắc |
|---|---|
| Chỉ đọc cấu hình riêng của một service | Prefix riêng của service và những context profile cần thiết. |
| Đọc thêm giá trị chung | Prefix context `application` tương ứng. |
| Dùng nhiều profile | Đảm bảo policy khớp các context có profile separator thực tế. |
| Dùng format `FILES` | Cấp quyền trên prefix chứa các file key tương ứng. |
| Cùng ứng dụng có cả Config và Discovery | Tách quyền đọc KV và quyền tra cứu service nếu có thể. |

Một policy đọc toàn bộ `config/` có thể giúp thử nghiệm nhanh nhưng thường quá rộng cho production: token của một dịch vụ có thể đọc cấu hình của các dịch vụ khác nếu tất cả cùng nằm dưới prefix đó.

## 5. Tạo token riêng cho workload

Sau khi tạo policy, cấp token cho workload:

```bash
consul acl token create \
  -description "order-service production config reader" \
  -policy-name "order-service-config-read"
```

Lưu `SecretID` do Consul trả về trong secret manager hoặc hệ thống cấp secret của nền tảng. Không commit SecretID vào Git, không ghi vào log và không đưa token vào URL. `AccessorID` có thể dùng để quản trị token, nhưng request cần SecretID.

Ưu tiên một token riêng cho từng service, môi trường hoặc workload. Nếu tất cả ứng dụng dùng chung một token, khi một ứng dụng bị xâm nhập sẽ khó giới hạn phạm vi ảnh hưởng và khó thu hồi quyền cho riêng ứng dụng đó.

### Cấu hình ACL token trong Spring Cloud Consul Config

Spring Cloud Consul có thuộc tính riêng cho token đọc cấu hình:

```yaml
spring:
  cloud:
    consul:
      config:
        acl-token: ${CONSUL_CONFIG_ACL_TOKEN}
```

`spring.cloud.consul.config.acl-token` được dùng cho các thao tác lấy KV và Config Watch. Cấp giá trị qua biến môi trường, Kubernetes Secret, Vault hoặc secret manager phù hợp. Không đặt token literal trong file `application.yml` được commit.

Nếu ứng dụng còn sử dụng Consul Service Discovery, cấu hình đó có thuộc tính token riêng:

```yaml
spring:
  cloud:
    consul:
      config:
        acl-token: ${CONSUL_CONFIG_ACL_TOKEN}
      discovery:
        acl-token: ${CONSUL_DISCOVERY_ACL_TOKEN}
```

Token đọc KV không tự động có quyền đọc service catalog. Tương tự, token discovery không tự động được quyền đọc cấu hình. Có thể dùng chung token nếu policy được thiết kế có chủ ý, nhưng tách token giúp giảm quyền và giới hạn tác động khi một credential bị lộ.

## 6. Kiểm tra token trước khi chạy ứng dụng

Khi gặp lỗi ACL, kiểm tra lần lượt:

1. Token có được cấp và chưa bị thu hồi/hết hạn không?
2. Ứng dụng có đang dùng đúng thuộc tính `spring.cloud.consul.config.acl-token` không?
3. Token có gắn policy đúng không?
4. Policy có cho `read` trên tất cả context mà ứng dụng yêu cầu không?
5. Prefix, profile separator, default context và format có trùng với đường dẫn KV thật không?
6. Consul agent có bật ACL và default policy phù hợp không?
7. Nếu dùng Config Watch, token có quyền đọc các prefix được watch không?

Có thể kiểm tra quyền bằng một request KV với token trong môi trường quản trị. Không dùng lệnh hiển thị token trên terminal dùng chung hoặc đưa token vào command history. Nếu cần xác minh token bằng CLI, dùng cơ chế nhập secret an toàn của môi trường và che output.

## 7. Kết nối HTTPS đến Consul Agent

Spring Cloud Consul mặc định kết nối Consul agent ở `localhost:8500` qua HTTP. Trong production, cấu hình endpoint HTTPS của agent và trust chain hợp lệ.

Ví dụ cấu hình kết nối:

```yaml
spring:
  cloud:
    consul:
      host: ${CONSUL_HOST}
      port: ${CONSUL_HTTPS_PORT:8501}
      scheme: https
      config:
        acl-token: ${CONSUL_CONFIG_ACL_TOKEN}
```

`scheme: https` chọn HTTP API qua TLS; cổng HTTPS thường được cấu hình là `8501`, nhưng phải dùng đúng cổng listener của Consul agent trong môi trường triển khai. Nếu không đặt scheme, client có thể sử dụng HTTP.

TLS bảo vệ dữ liệu trên đường truyền và giúp client xác thực server qua certificate chain/hostname. Không tắt xác minh certificate hoặc hostname để làm cho kết nối thử nghiệm thành công; hãy cài CA nội bộ đúng cách và dùng hostname khớp Subject Alternative Name của certificate.

## 8. Cấu hình certificate và keystore phía Spring Cloud Consul

Spring Cloud Consul cung cấp nhóm thuộc tính `spring.cloud.consul.tls.*` cho certificate và keystore. Các thuộc tính thường gặp gồm:

| Thuộc tính | Ý nghĩa |
|---|---|
| `spring.cloud.consul.tls.certificate-path` | Đường dẫn đến certificate file được cấu hình cho TLS. |
| `spring.cloud.consul.tls.certificate-password` | Mật khẩu mở certificate nếu định dạng cần mật khẩu. |
| `spring.cloud.consul.tls.key-store-instance-type` | Loại keystore, ví dụ `PKCS12`. |
| `spring.cloud.consul.tls.key-store-path` | Đường dẫn keystore chứa key/certificate material. |
| `spring.cloud.consul.tls.key-store-password` | Mật khẩu mở keystore. |

Ví dụ khung cấu hình với keystore PKCS12:

```yaml
spring:
  cloud:
    consul:
      host: ${CONSUL_HOST}
      port: 8501
      scheme: https
      tls:
        certificate-path: ${CONSUL_CERTIFICATE_PATH}
        certificate-password: ${CONSUL_CERTIFICATE_PASSWORD:}
        key-store-instance-type: PKCS12
        key-store-path: ${CONSUL_KEYSTORE_PATH}
        key-store-password: ${CONSUL_KEYSTORE_PASSWORD}
```

Đây là khung minh họa tên thuộc tính. Ý nghĩa certificate file, keystore và định dạng được hỗ trợ phụ thuộc phiên bản Spring Cloud Consul và HTTP client mà release train sử dụng. Hãy đối chiếu property appendix của đúng phiên bản, sau đó thử handshake với CA/certificate của Consul trước khi triển khai rộng. Không đưa keystore password hoặc private key vào repository.

Nếu Consul chỉ yêu cầu HTTPS server authentication, client cần trust CA đã ký server certificate. Nếu Consul yêu cầu client certificate, client còn phải cung cấp certificate/private key được CA mà agent tin cậy cấp. Hai trường hợp này khác nhau; có HTTPS không đồng nghĩa đã bật mTLS.

## 9. Phân biệt TLS cho HTTP API, agent RPC và service mesh

Consul có nhiều mặt phẳng giao tiếp. Cấu hình TLS của một mặt phẳng không tự động bảo vệ tất cả mặt phẳng khác.

| Kênh | Mục tiêu | Cơ chế cần kiểm tra |
|---|---|---|
| Spring Boot client → Consul HTTP API | Bảo vệ request KV/Discovery qua agent HTTP(S). | `spring.cloud.consul.scheme`, port, trust CA và client certificate nếu agent yêu cầu. |
| Consul agent ↔ agent RPC | Bảo vệ giao tiếp nội bộ giữa các node Consul. | `tls.internal_rpc`, CA, certificate, `verify_incoming`, `verify_outgoing`, hostname verification. |
| Service mesh traffic | Bảo vệ kết nối giữa workload/service qua proxy. | Mesh CA, service identity, mTLS và service intentions. |
| Gossip giữa agent | Bảo vệ thông tin membership/gossip. | Gossip encryption key, quản lý và luân chuyển key. |

Ví dụ agent Consul dùng TLS cho HTTPS listener và yêu cầu client certificate:

```hcl
addresses {
  https = "0.0.0.0"
}

ports {
  https = 8501
}

tls {
  https {
    ca_file                 = "/etc/consul/pki/ca.pem"
    cert_file               = "/etc/consul/pki/server.pem"
    key_file                = "/etc/consul/pki/server-key.pem"
    verify_incoming         = true
    verify_outgoing         = true
    verify_server_hostname  = true
  }
}
```

`verify_incoming = true` trên HTTPS listener yêu cầu client gửi certificate hợp lệ được CA tin cậy ký. Nếu chỉ cần mã hóa và xác thực server, mô hình có thể khác; quyết định phải thống nhất với cấu hình client. `verify_server_hostname` giúp xác minh certificate thuộc đúng hostname, giảm nguy cơ kết nối nhầm hoặc bị giả mạo.

TLS giữa Consul agents và TLS của service mesh là hai cơ chế riêng. Không coi việc client Spring Boot gọi được cổng `8501` là bằng chứng internal RPC hoặc traffic giữa các service đã được bảo vệ.

## 10. Luân chuyển ACL token và certificate

Không nên dùng một token lâu dài cho mọi ứng dụng. Khi token bị lộ, thay đổi quyền hoặc cần luân chuyển định kỳ, thực hiện theo quy trình có thể rollback:

1. Tạo policy đúng phạm vi và token mới.
2. Cấp SecretID mới qua secret manager/workload platform.
3. Triển khai token mới đến ứng dụng đích; nếu token được nạp ở giai đoạn Config Data/bootstrap, xác định có cần restart instance để token mới có hiệu lực.
4. Kiểm tra ứng dụng đọc được đúng context và Config Watch hoạt động.
5. Thu hồi token cũ sau khi xác nhận không còn workload hợp lệ sử dụng.
6. Kiểm tra audit log và xác nhận request cũ không còn được chấp nhận.

Khi luân chuyển certificate/CA:

1. Cấp certificate mới và chuẩn bị trust chain cho client/agent.
2. Triển khai CA mới vào trust store trong giai đoạn chuyển tiếp nếu có kế hoạch đổi CA.
3. Cài certificate mới lên server/agent và client tương ứng.
4. Kiểm tra TLS handshake, hostname và mTLS trước khi thu hồi certificate cũ.
5. Thu hồi certificate cũ, xóa private key không còn dùng và kiểm tra mọi instance đã nhận cấu hình mới.

Không thu hồi CA hoặc token cũ trước khi các instance cần thiết đã chuyển sang credential mới. Với key bị lộ, ưu tiên incident response và thu hồi khẩn cấp theo chính sách bảo mật.

## 11. Consul lỗi khi ứng dụng khởi động: fail-fast hay fallback?

Spring Cloud Consul Config có thể được dùng qua Spring Boot Config Data import hoặc bootstrap legacy. Cách khai báo nguồn cấu hình ảnh hưởng trực tiếp đến hành vi startup.

### Config Data import bắt buộc

```yaml
spring:
  config:
    import: "consul:"
```

Khi import không có `optional:`, Consul Config là nguồn bắt buộc. Nếu không thể tải cấu hình cần thiết, ứng dụng có thể thất bại khi khởi động. Cách này phù hợp khi thiếu cấu hình trung tâm khiến dịch vụ không thể chạy an toàn.

### Config Data import tùy chọn

```yaml
spring:
  config:
    import: "optional:consul:"
```

`optional:consul:` cho phép ứng dụng tiếp tục khởi động khi nguồn Consul không có sẵn theo quy tắc Config Data. Ứng dụng khi đó phải có cấu hình local/default hoặc nguồn khác đủ để hoạt động an toàn.

Không dùng optional như cách che giấu lỗi ACL hoặc TLS. Token sai, certificate không hợp lệ, hostname không khớp hoặc lỗi dữ liệu cấu hình cần được xử lý và kiểm tra theo hành vi của phiên bản đang dùng. Hãy thử riêng trường hợp Consul không chạy, key chưa tồn tại, token bị từ chối và TLS handshake thất bại.

### Bootstrap legacy và fail-fast

Với cấu hình legacy, có thuộc tính:

```yaml
spring:
  cloud:
    consul:
      config:
        fail-fast: true
```

`spring.cloud.consul.config.fail-fast` mặc định là `true` trong property reference hiện hành. Nếu đặt `false`, module có thể ghi warning và cho phép ứng dụng tiếp tục khi không đọc được Consul trong quá trình lấy cấu hình. Với `spring-cloud-starter-bootstrap` hoặc legacy bootstrap processing, thuộc tính cần được đặt ở `bootstrap.yml` để có hiệu lực đủ sớm.

Không nhầm `spring.cloud.consul.config.fail-fast` với `spring.cloud.consul.discovery.fail-fast`: một thuộc tính điều khiển việc lấy cấu hình, thuộc tính còn lại điều khiển đăng ký/Discovery.

## 12. Retry khi Consul tạm thời không sẵn sàng

Spring Cloud Consul có nhóm thuộc tính retry:

```yaml
spring:
  cloud:
    consul:
      retry:
        enabled: true
        initial-interval: 1000
        max-attempts: 6
        max-interval: 2000
        multiplier: 1.1
```

Các giá trị trên minh họa cấu hình backoff phổ biến trong property reference hiện hành:

- `enabled`: bật/tắt retry.
- `initial-interval`: khoảng chờ ban đầu, tính bằng millisecond.
- `max-attempts`: số lần thử tối đa.
- `max-interval`: giới hạn thời gian chờ giữa các lần thử.
- `multiplier`: hệ số tăng thời gian chờ theo cấp số nhân.

Retry phù hợp với lỗi tạm thời như Consul agent khởi động chậm hoặc mạng gián đoạn ngắn. Retry không sửa được token sai, policy thiếu quyền, certificate hết hạn hoặc hostname không khớp. Những lỗi cấu hình cố định sẽ tiếp tục thất bại cho đến khi được sửa.

Các release train cũ có thể yêu cầu thêm `spring-retry` và `spring-boot-starter-aop` để dùng retry; release mới có thể có cơ chế khác. Quản lý phiên bản theo Spring Cloud BOM và kiểm tra tài liệu đúng release train trước khi thêm dependency.

## 13. Config Watch khi ứng dụng đang chạy

Config Watch theo dõi các KV context đã nạp. Khi Consul báo index thay đổi, Spring Cloud Consul phát `RefreshEvent` để ứng dụng làm mới Environment và các bean hỗ trợ refresh.

Cấu hình ví dụ:

```yaml
spring:
  cloud:
    consul:
      config:
        watch:
          enabled: true
          delay: 1000
          wait-time: 55
```

Ý nghĩa:

- `watch.enabled`: bật/tắt Config Watch; mặc định `true` trong property reference hiện hành.
- `watch.delay`: thời gian chờ giữa các lần gọi watch, tính bằng millisecond; mặc định thường là `1000`.
- `watch.wait-time`: thời gian long-poll một truy vấn Consul, tính bằng giây; mặc định thường là `55` và cần nhỏ hơn timeout HTTP client tương ứng.

Watch sử dụng blocking query để giảm số request polling liên tục. Khi KV index thay đổi, client nhận biết context có thay đổi và phát refresh event. Những bean cần nhận giá trị mới vẫn phải được rebind hoặc dùng `@RefreshScope` theo đúng vòng đời.

## 14. Điều gì xảy ra nếu Consul mất kết nối sau khi ứng dụng đã chạy?

Khác với giai đoạn startup, lỗi Consul trong lúc watch thường không khiến toàn bộ JVM tự dừng. Config Watch tiếp tục thử ở chu kỳ sau và ghi log warning khi truy vấn thất bại. Các giá trị đã nạp vào Spring `Environment` vẫn nằm trong bộ nhớ; chúng không tự biến mất chỉ vì Consul tạm thời không truy cập được.

Hệ quả thường gặp:

- Ứng dụng vẫn xử lý request bằng cấu hình đã nạp trước đó nếu các dependency nghiệp vụ khác còn hoạt động.
- Thay đổi mới trong Consul chưa được phát hiện và chưa được refresh.
- Khi Consul hoạt động trở lại, watch có thể phát hiện index mới và gửi refresh event.
- Nếu ứng dụng restart trong lúc Consul vẫn lỗi, hành vi phụ thuộc import bắt buộc/tùy chọn và fail-fast policy.

Đây là lý do phải phân biệt khả năng tiếp tục chạy bằng cấu hình đang có với khả năng khởi động instance mới. Một cụm có thể còn instance cũ đang phục vụ trong khi autoscaler hoặc deployment không thể tạo instance mới vì Consul unavailable.

Không nên để ứng dụng tiếp tục vô thời hạn với cấu hình cũ nếu thay đổi mới liên quan đến thu hồi credential, giới hạn truy cập hoặc biện pháp bảo mật khẩn cấp. Cần có quy trình xử lý sự cố và quyết định rõ có cho phép tiếp tục phục vụ hay không.

## 15. Thiết kế fallback an toàn

Nếu môi trường cho phép khởi động khi Consul không có sẵn, cấu hình fallback phải đủ để ứng dụng hoạt động đúng và không làm giảm an toàn.

Ví dụ:

```yaml
spring:
  config:
    import: "optional:consul:"

orders:
  request-timeout: 3s
  max-items-per-request: 20
```

Các giá trị local này chỉ nên là default an toàn cho môi trường và nghiệp vụ được thiết kế trước. Không hardcode password production, API key, private key hoặc credential dự phòng vào file cấu hình đóng gói.

Với property bắt buộc, dùng validation để ứng dụng báo lỗi rõ ràng nếu không có giá trị hợp lệ:

```java
@Validated
@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(
        @NotNull Duration requestTimeout,
        @Min(1) int maxItemsPerRequest) {
}
```

Fallback cần được đánh giá theo từng loại cấu hình:

| Loại cấu hình | Fallback có thể chấp nhận? | Ghi chú |
|---|---|---|
| Timeout mặc định | Có thể | Chọn giá trị giới hạn an toàn, tránh request treo lâu. |
| Logging level | Thường có | Dùng mức mặc định đã được kiểm soát. |
| Feature flag ảnh hưởng dữ liệu | Cần đánh giá | Chọn trạng thái an toàn theo nghiệp vụ. |
| Database password/API key | Không dùng giá trị giả | Cần secret hợp lệ; nếu thiếu nên fail startup hoặc không nhận traffic. |
| Authorization policy/secret rotation | Không nên dùng bản cũ vô thời hạn | Cần xử lý theo incident response và chính sách bảo mật. |

## 16. Phân biệt Config lỗi và Service Discovery lỗi

Spring Cloud Consul cung cấp nhiều chức năng độc lập. Một ứng dụng có thể đọc được KV nhưng không tra cứu được service, hoặc đăng ký service thành công nhưng không lấy được cấu hình.

| Chức năng | Thuộc tính liên quan | Quyền ACL điển hình |
|---|---|---|
| Đọc cấu hình KV | `spring.cloud.consul.config.*` | `key_prefix` read trên các context cần thiết. |
| Config Watch | `spring.cloud.consul.config.watch.*` | Quyền đọc KV/watch trên context tương ứng. |
| Service Discovery | `spring.cloud.consul.discovery.*` | Quyền đọc service/node/catalog theo truy vấn. |
| Service Registration | `spring.cloud.consul.discovery.register` và các thuộc tính liên quan | Quyền ghi service/node cần thiết. |

Không cấp `service_prefix "" { policy = "write" }` chỉ để ứng dụng đọc cấu hình. Nếu ứng dụng không đăng ký service, có thể tắt auto-registration theo nhu cầu và chỉ giữ quyền KV cần thiết.

## 17. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| HTTP 403 hoặc `permission denied` khi đọc KV | Token thiếu `read` trên context hoặc token không được gửi. | Kiểm tra `config.acl-token`, policy prefix và đường dẫn KV thật. |
| Không có property nhưng request không báo lỗi | Context/key không tồn tại, sai prefix/profile/name hoặc policy lọc key. | Kiểm tra Consul KV path, `default-context`, `name`, separator và format. |
| 401/403 sau khi rotate token | Workload vẫn dùng SecretID cũ hoặc token mới chưa gắn policy. | Cấp token mới, rollout client và xác minh trước khi revoke token cũ. |
| TLS handshake failure | CA không được trust, certificate hết hạn, client cert thiếu hoặc certificate chain không đúng. | Kiểm tra trust chain, key store, certificate validity và cấu hình mTLS phía agent. |
| Hostname verification failure | Host kết nối không khớp SAN của certificate. | Dùng DNS name hợp lệ trong certificate hoặc cấp lại certificate đúng SAN. |
| 404 hoặc Config Data resource not found | Key/context chưa tồn tại, path sai hoặc import là bắt buộc. | Kiểm tra KV context và quyết định có dùng `optional:consul:` hay không. |
| Ứng dụng không khởi động khi Consul down | Import bắt buộc hoặc `fail-fast=true`. | Quyết định fail-fast hay fallback theo môi trường; không tắt fail-fast một cách đại trà. |
| Ứng dụng khởi động nhưng thiếu property | Optional/fail-fast false cho phép tiếp tục với cấu hình local chưa đầy đủ. | Bổ sung fallback an toàn và validation cho property bắt buộc. |
| Config Watch không refresh | Watch bị tắt, token không có quyền đọc, wait-time/timeout không phù hợp hoặc bean không hỗ trợ refresh. | Kiểm tra watch, ACL, log, Environment và `@RefreshScope`/rebind. |
| Config đọc được nhưng Discovery trả về rỗng | Discovery token thiếu quyền hoặc service chưa đăng ký/health check critical. | Kiểm tra `discovery.acl-token`, service policy và trạng thái health. |

Khi điều tra, không ghi token hoặc nội dung secret vào log. Ghi nhận mã lỗi, endpoint, context, profile, trạng thái TLS và tên policy liên quan để truy vết.

## 18. Checklist vận hành an toàn

- [ ] ACL được bật trên Consul và `default_policy` đặt thành `deny` theo chính sách production.
- [ ] Mỗi workload dùng token riêng hoặc token theo nhóm quyền được phê duyệt.
- [ ] Token Config chỉ có quyền đọc các KV prefix cần thiết.
- [ ] Token Discovery tách biệt nếu ứng dụng cần service catalog/registration.
- [ ] SecretID được cấp qua secret manager và không nằm trong Git, image hoặc log.
- [ ] Consul HTTP API dùng HTTPS với CA và hostname verification hợp lệ.
- [ ] mTLS được bật nếu yêu cầu client certificate; agent RPC và service mesh được đánh giá riêng.
- [ ] Certificate, ACL token và key có lịch luân chuyển, thu hồi và audit.
- [ ] Startup policy được chọn rõ: mandatory/fail-fast hay optional/fallback.
- [ ] Retry và Config Watch được cấu hình phù hợp với timeout và tải Consul.
- [ ] Property bắt buộc có validation; fallback không chứa credential giả hoặc secret cũ.
- [ ] Có dashboard/log cảnh báo cho lỗi ACL, TLS, watch và Consul availability.
- [ ] Có diễn tập Consul unavailable và token/certificate rotation.

## 19. Bài thực hành

### Bước 1: Bật ACL với default deny

Trong Consul dev cluster, bật ACL, tạo policy đọc KV cho prefix cấu hình thử nghiệm và tạo token riêng cho `order-service`.

**Kết quả cần đạt:** request không token bị từ chối và token hợp lệ chỉ đọc được prefix đã cấp.

### Bước 2: Kết nối Spring Cloud Consul Config bằng token

Thêm `spring-cloud-starter-consul-config`, cấu hình `spring.config.import=consul:` và truyền token qua biến môi trường `CONSUL_CONFIG_ACL_TOKEN`.

**Kết quả cần đạt:** ứng dụng đọc được context của nó và context chung; không có token literal trong repository.

### Bước 3: Thử token thiếu quyền

Tạo token chỉ có quyền đọc prefix khác, chạy ứng dụng và quan sát lỗi. Sau đó cập nhật policy đúng phạm vi.

**Kết quả cần đạt:** phân biệt lỗi token không hợp lệ với token hợp lệ nhưng thiếu quyền.

### Bước 4: Bật HTTPS

Cấu hình Consul HTTPS listener với certificate thử nghiệm, cấu hình client dùng `scheme: https`, đúng port và trust material. Thử certificate không đúng CA hoặc hostname sai trong môi trường lab.

**Kết quả cần đạt:** xác minh client chỉ kết nối khi certificate chain và hostname hợp lệ.

### Bước 5: So sánh fail-fast và optional import

Dừng Consul rồi chạy với `consul:`; ghi nhận ứng dụng có dừng hay không. Chạy lại với `optional:consul:` và fallback local đã chuẩn bị.

**Kết quả cần đạt:** hiểu quyết định startup ảnh hưởng thế nào khi nguồn cấu hình không sẵn sàng.

### Bước 6: Diễn tập outage sau startup

Khởi động ứng dụng khi Consul hoạt động, sau đó dừng Consul và thay đổi một KV key. Theo dõi log Config Watch, giá trị hiện hành trong ứng dụng và hành vi khi Consul hoạt động lại.

**Kết quả cần đạt:** hiểu runtime watch outage khác với lỗi bootstrap khi khởi động.

### Bước 7: Luân chuyển token

Tạo token mới gắn cùng policy, triển khai vào workload, xác minh Config Watch/Config Data hoạt động rồi thu hồi token cũ.

**Kết quả cần đạt:** thay credential mà không làm ứng dụng mất quyền truy cập ngoài kế hoạch.

## 20. Tự kiểm tra

1. ACL token, policy và role khác nhau như thế nào?
2. Vì sao production nên đặt Consul `default_policy` thành `deny`?
3. Token chỉ đọc cấu hình cần những quyền KV nào?
4. Vì sao nên tách `config.acl-token` và `discovery.acl-token`?
5. SecretID khác AccessorID ở điểm nào?
6. HTTPS và mTLS bảo vệ các thuộc tính nào của kết nối?
7. TLS giữa Spring Boot client với HTTP API khác gì TLS giữa Consul agents và service mesh?
8. `spring.config.import=consul:` khác `optional:consul:` như thế nào?
9. `spring.cloud.consul.config.fail-fast=false` ảnh hưởng giai đoạn nào?
10. Retry giải quyết được lỗi nào và không giải quyết được lỗi nào?
11. Config Watch phản ứng ra sao khi Consul mất kết nối sau khi ứng dụng đã khởi động?
12. Vì sao một ứng dụng đang chạy có thể tiếp tục dùng cấu hình cũ nhưng instance mới không khởi động được?
13. Cần xác minh những gì khi Consul trả 403, TLS handshake failure hoặc không tìm thấy KV context?
14. Quy trình luân chuyển token an toàn gồm những bước nào?

Khi hoàn thành bài thực hành, người học có thể cấp ACL token theo nguyên tắc quyền tối thiểu, thiết lập kết nối HTTPS/mTLS phù hợp, chọn chính sách fail-fast hoặc fallback có kiểm soát và vận hành ứng dụng an toàn khi Consul tạm thời không sẵn sàng.

## Tài liệu tham khảo

- [Spring Cloud Consul – Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html): ACL token, TLS, retry, Config Watch và các thuộc tính cấu hình.
- [Spring Cloud Consul – Distributed Configuration with Consul](https://docs.spring.io/spring-cloud-consul/reference/): Config Data import, fail-fast, Config Watch và retry.
- [HashiCorp Consul – ACL Policies](https://developer.hashicorp.com/consul/docs/secure/acl/policy): policy, `key_prefix`, quyền read/write/deny và scope token.
- [HashiCorp Consul – ACL Bootstrap](https://developer.hashicorp.com/consul/docs/secure/acl/bootstrap): bật ACL, default deny và bootstrap token.
- [HashiCorp Consul – Manage Agent mTLS Encryption](https://developer.hashicorp.com/consul/docs/secure/encryption/tls/mtls): CA, certificate, xác thực hai chiều và luân chuyển TLS.
- [HashiCorp Consul – TLS Configuration Parameters](https://developer.hashicorp.com/consul/docs/reference/agent/configuration-file/tls): `verify_incoming`, `verify_outgoing`, `verify_server_hostname` và TLS stanza.

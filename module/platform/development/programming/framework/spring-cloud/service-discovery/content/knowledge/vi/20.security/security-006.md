# Consul ACL token và quyền tối thiểu cho đăng ký hoặc truy vấn

Consul ACL (Access Control List) kiểm soát ai được đăng ký service, đọc danh sách service, cập nhật health check và quản trị cluster. Khi bật ACL, một ứng dụng Spring Cloud Consul cần gửi token có đúng quyền cho các thao tác mà nó thực hiện. Dùng một token quản trị cho mọi service sẽ khiến một lỗi lộ secret có thể ảnh hưởng toàn bộ Consul cluster.

Thiết kế an toàn bắt đầu bằng việc tách vai trò: service producer cần quyền đăng ký chính nó; service consumer cần quyền đọc những service nó được phép gọi; ứng dụng dùng TTL heartbeat cần thêm quyền cập nhật check; Consul Agent có token riêng cho hoạt động nội bộ. Spring Cloud Consul có thuộc tính token riêng cho Discovery và Consul Config, vì vậy không nên gộp các quyền này nếu không cần.

## 1. ACL bảo vệ những thao tác nào?

Consul ACL gắn policy với token. Khi client gọi Consul HTTP API hoặc Consul Agent API, Consul kiểm tra token và các rule liên quan tới resource.

Trong service discovery, các thao tác chính gồm:

| Thao tác | API thường dùng | Quyền ACL chính |
|---|---|---|
| Đăng ký service vào local agent/catalog | `PUT /v1/agent/service/register` | `service:write` cho tên service được đăng ký |
| Hủy đăng ký service | `PUT /v1/agent/service/deregister/:service_id` | `service:write` cho service tương ứng |
| Đăng ký check riêng qua Agent API | `PUT /v1/agent/check/register` | `node:write` và `service:write` |
| Đọc service trong Catalog | Catalog API | `service:read`; node rule có thể giới hạn node được trả về |
| Tra cứu service kèm health state | Health API `/v1/health/service/:name` | `service:read` và `node:read` cho dữ liệu discovery tương ứng |
| Gia hạn TTL check | `/v1/agent/check/pass/:check_id`, `warn`, `fail`, `update` | `node:write` và `service:write` |
| Tạo/sửa ACL policy hoặc token | ACL API/CLI | `acl:write` |

Quyền `service:write` cho phép cập nhật catalog của service. `service:read` cho phép đọc service. `node:read` cho phép đọc node metadata và là một phần của truy vấn discovery qua Health API. `node:write` cho phép cập nhật thông tin node và được yêu cầu bởi một số thao tác check trên Agent API, bao gồm TTL update.

Không cấp `acl:write`, `operator:write`, `key:write` hoặc quyền quản trị rộng cho ứng dụng chỉ cần đăng ký và tra cứu service.

## 2. Phân biệt các loại token trong Consul

Consul có nhiều token với vai trò khác nhau. Tên gọi gần nhau nhưng không thể thay thế tùy tiện:

| Token | Ai sử dụng? | Mục đích |
|---|---|---|
| Initial management token | Quản trị viên ACL | Tạo policy, token, role và thao tác quản trị ACL; có quyền rất rộng |
| Application/service token | Spring Boot service hoặc workload | Đăng ký service, gửi heartbeat hoặc đọc service theo policy được gắn |
| Agent token (`acl.tokens.agent`) | Consul Agent | Hoạt động nội bộ như đồng bộ node metadata và anti-entropy |
| Default token (`acl.tokens.default`) | Consul Agent cho request không có token cụ thể, gồm một số truy vấn DNS | Quyền mặc định của agent khi không có token riêng; nên giới hạn ở quyền cần thiết |
| Config-file service-registration token | Consul Agent đăng ký service/check khai báo trong file cấu hình agent | Cho phép agent đăng ký các service/check tĩnh từ file |
| Anonymous token | Request không gửi token | Quyền nhận được từ token anonymous; không nên biến token này thành quyền rộng |

Spring Cloud Consul `spring.cloud.consul.discovery.acl-token` là token mà integration Discovery dùng cho thao tác discovery/registration. Đây là application token, không phải `acl.tokens.agent` của Consul Agent.

Spring Cloud Consul `spring.cloud.consul.config.acl-token` là token riêng cho Consul Config khi đọc dữ liệu trong KV. Nếu ứng dụng không dùng Consul Config thì không cần cấp token KV chỉ vì nó dùng service discovery.

## 3. Bật ACL và bootstrap token quản trị

ACL phải được bật trên Consul servers và client agents. Ví dụ cấu hình trên Consul server:

```hcl
acl {
  enabled = true
  default_policy = "deny"
}
```

`default_policy = "deny"` là chính sách mặc định phía server cho thao tác không được policy cho phép. Bật `acl.enabled` trên client agents và cấu hình token cần thiết cho từng agent; không sao chép máy móc `default_policy` sang cấu hình client. Khi chuyển một cluster đang chạy từ ACL chưa bật sang ACL enforcement, cần có kế hoạch rollout và cấp token cho agent trước khi chuyển sang deny; nếu bật deny đột ngột, agent và service có thể mất quyền đồng bộ.

Bootstrap ACL trên một Consul server:

```bash
consul acl bootstrap
```

Consul trả về initial management token, trong đó `SecretID` là credential dùng để xác thực. Token này có quyền `global-management`, tức quyền không giới hạn trên resource/API. Chỉ quản trị viên ACL được phép giữ token này; không đặt nó trong `application.yml`, biến môi trường chung của mọi workload hoặc pipeline build.

Trong các ví dụ CLI tiếp theo, giả sử quản trị viên tạm thời cung cấp management token cho Consul CLI:

```bash
export CONSUL_HTTP_TOKEN="<INITIAL_MANAGEMENT_SECRET_ID>"
```

PowerShell:

```powershell
$env:CONSUL_HTTP_TOKEN = "<INITIAL_MANAGEMENT_SECRET_ID>"
```

Biến `CONSUL_HTTP_TOKEN` ở đây chỉ dành cho phiên quản trị CLI. Ứng dụng Spring Boot sẽ nhận service token riêng từ secret store hoặc environment injection. Không commit giá trị token thật vào Git.

## 4. Tạo policy chỉ cho phép đăng ký một service

Giả sử producer có service name `inventory-service` và chỉ cần đăng ký/hủy đăng ký chính service đó. Tạo file policy `inventory-register.hcl`:

```hcl
service "inventory-service" {
  policy = "write"
}
```

Policy này cấp `service:write` cho đúng service name. Nó không cấp quyền đọc mọi service, sửa KV, tạo token hay quản trị agent.

Đăng ký policy:

```bash
consul acl policy create \
  -name "inventory-register" \
  -description "Allow inventory-service registration" \
  -rules @inventory-register.hcl
```

Tạo token gắn policy:

```bash
consul acl token create \
  -description "Spring Cloud token for inventory-service registration" \
  -policy-name "inventory-register"
```

CLI trả về `AccessorID` và `SecretID`. Lưu `SecretID` vào secret manager; `AccessorID` hữu ích để quản trị, tra cứu và thu hồi token. Token registration-only này đủ cho thao tác service registration theo Agent Service Registration API. Nếu service cũng cần tự tra cứu service khác, hãy cấp thêm quyền read theo đúng phạm vi ở phần tiếp theo.

## 5. Tạo policy chỉ cho phép consumer truy vấn service

Consumer `order-service` cần tra cứu `inventory-service` và `payment-service`. Với Health API, chỉ cấp `service:read` có thể chưa đủ để nhận đầy đủ node/address; cần thêm `node:read` theo phạm vi mà consumer được phép thấy.

Ví dụ policy chỉ cho phép đọc hai service cụ thể:

```hcl
service "inventory-service" {
  policy = "read"
}

service "payment-service" {
  policy = "read"
}

node_prefix "" {
  policy = "read"
}
```

Nếu consumer được phép khám phá mọi service trong datacenter, có thể dùng `service_prefix ""` thay cho từng service rule:

```hcl
service_prefix "" {
  policy = "read"
}

node_prefix "" {
  policy = "read"
}
```

Không mở rộng sang `service_prefix ""` nếu consumer chỉ cần hai service. Quyền càng rộng thì phạm vi thông tin service/node mà token có thể đọc càng lớn.

Đăng ký policy và tạo token theo cùng quy trình:

```bash
consul acl policy create \
  -name "order-discovery-read" \
  -description "Allow order-service to discover approved upstreams" \
  -rules @order-discovery-read.hcl

consul acl token create \
  -description "Spring Cloud token for order-service discovery" \
  -policy-name "order-discovery-read"
```

Trong Consul Enterprise, nếu dùng namespace hoặc admin partition, policy và token còn phải được scope vào đúng namespace/partition. Rule ở namespace không thể tùy ý truy cập resource thuộc namespace khác.

## 6. Một service vừa đăng ký chính nó vừa gọi service khác

Trong thực tế, `inventory-service` có thể vừa đăng ký instance của chính nó, vừa gọi `pricing-service`. Khi đó policy cần quyền write cho service của nó và quyền read cho các service được phép gọi.

Ví dụ:

```hcl
service "inventory-service" {
  policy = "write"
}

service "pricing-service" {
  policy = "read"
}

node_prefix "" {
  policy = "read"
}
```

Nếu service cần khám phá nhiều service, thay các service read cụ thể bằng `service_prefix` phù hợp. Cấu trúc này tương tự ví dụ custom policy do HashiCorp công bố: service identity có quyền write cho chính nó và read cho các service/node mà nó cần khám phá.

HashiCorp cũng cung cấp templated policy `builtin/service`. Template này tự cấp `service:write`, `service:read` cho service được chỉ định và `node:read`; đây là lựa chọn được khuyến nghị cho các use case service discovery/service mesh phổ biến. Ví dụ tạo token cho `inventory-service`:

```bash
consul acl token create \
  -description "Service identity for inventory-service" \
  -templated-policy "builtin/service" \
  -var "name:inventory-service"
```

Template tiện lợi và ít sai sót, nhưng custom policy có thể hẹp hơn nếu ứng dụng chỉ cần đăng ký mà không cần đọc service khác. Chọn policy theo hành vi thật của workload, không theo việc template có sẵn.

## 7. Quyền bổ sung khi dùng TTL heartbeat

Đăng ký service có health check và cập nhật TTL check là hai thao tác khác nhau. Consul Agent API yêu cầu `node:write` và `service:write` cho các endpoint TTL check pass/warn/fail/update.

Nếu Spring Cloud Consul gửi TTL heartbeat trực tiếp bằng application token, token cần quyền write trên service tương ứng và node mà Consul Agent đang quản lý. Có thể bổ sung rule node cụ thể:

```hcl
service "inventory-service" {
  policy = "write"
}

node "consul-client-01" {
  policy = "write"
}
```

`consul-client-01` phải khớp chính xác tên node của Consul Agent nơi check được đăng ký. Không dùng `node_prefix "" { policy = "write" }` chỉ để làm TTL heartbeat chạy, vì điều đó cấp quyền ghi rộng trên mọi node.

Nếu cùng token còn cần truy vấn service khác, thêm `service:read` và `node:read` có phạm vi phù hợp. Nếu dùng HTTP health check do Consul Agent chủ động gọi, ứng dụng không cần gửi TTL heartbeat; không cấp thêm quyền TTL chỉ vì có HTTP check.

Phân biệt quyền application token với agent token: `acl.tokens.agent` được Consul Agent dùng cho hoạt động nội bộ và cần quyền ghi node của chính agent, cùng quyền đọc service cho anti-entropy. Không sao chép service token của Spring Boot vào cấu hình agent token.

## 8. Cấu hình token trong Spring Cloud Consul

Spring Cloud Consul 5.1.0 có thuộc tính riêng cho Discovery và Config:

| Property | Dùng cho |
|---|---|
| `spring.cloud.consul.discovery.acl-token` | Consul service registration, discovery query và các thao tác liên quan của Discovery integration |
| `spring.cloud.consul.config.acl-token` | Đọc Consul KV qua Consul Config |

Ví dụ ứng dụng vừa đăng ký `inventory-service`, vừa tra cứu `pricing-service`:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: ${CONSUL_HOST:localhost}
      port: ${CONSUL_PORT:8500}
      discovery:
        acl-token: ${CONSUL_DISCOVERY_TOKEN}
        register: true
        deregister: true
```

Trong môi trường TTL heartbeat, token trên còn phải có quyền `node:write` cho node tương ứng như phần trước. Nếu chỉ dùng HTTP health check, policy không cần thêm quyền TTL chỉ vì có health check.

Nếu ứng dụng dùng Consul Config để đọc key/value:

```yaml
spring:
  cloud:
    consul:
      config:
        acl-token: ${CONSUL_CONFIG_TOKEN}
```

Policy KV nên giới hạn đúng prefix mà ứng dụng đọc. Ví dụ nếu dữ liệu cấu hình nằm dưới `config/`, có thể dùng:

```hcl
key_prefix "config/" {
  policy = "read"
}
```

Không cấp `key_prefix "" { policy = "write" }` cho service chỉ cần đọc cấu hình. Nếu ứng dụng không dùng Consul Config, không cần `CONSUL_CONFIG_TOKEN`.

Biến `CONSUL_DISCOVERY_TOKEN` và `CONSUL_CONFIG_TOKEN` nên được inject từ Vault, Kubernetes Secret, secret manager của nền tảng hoặc cơ chế quản lý secret tương đương. Tên biến môi trường có thể map theo relaxed binding của Spring Boot, ví dụ `SPRING_CLOUD_CONSUL_DISCOVERY_ACL_TOKEN`, nhưng dùng secret reference giúp tách credential khỏi file cấu hình.

## 9. Consul Agent token khác application token

Consul Agent có các token riêng trong cấu hình agent. Ví dụ cấu trúc:

```hcl
acl {
  enabled = true
  default_policy = "deny"

  tokens {
    agent = "<AGENT_INTERNAL_TOKEN_SECRET_ID>"
    default = "<AGENT_DEFAULT_READ_TOKEN_SECRET_ID>"
  }
}
```

Agent token thường cần:

```hcl
node "consul-client-01" {
  policy = "write"
}

service_prefix "" {
  policy = "read"
}
```

Rule node write cho phép agent cập nhật node metadata và tagged addresses của chính nó. Service read cho phép agent đọc các service cần thiết trong quá trình anti-entropy. Nếu remote execution bị tắt (mặc định), không cần cấp quyền KV `_rexec` cho mục đích này.

Default token nên có quyền phù hợp với các request mặc định, ví dụ read service/node nếu agent phục vụ DNS discovery. Không dùng token quản trị làm default token. Nếu request có token tường minh, token đó được dùng cho request thay vì default/anonymous token.

`config_file_service_registration` là token khác, dùng khi Consul Agent đăng ký service/check khai báo trong file cấu hình agent. Đây không phải property `spring.cloud.consul.discovery.acl-token` của một Spring Boot application tự đăng ký qua Agent API.

## 10. Token quản trị và token ứng dụng phải tách biệt

Initial management token được gắn với `global-management`, có quyền rất rộng. Token này cần thiết để bootstrap ACL, tạo policy/token và xử lý tình huống quản trị, nhưng không nên xuất hiện trong runtime của microservice.

Quy trình phân quyền thông thường:

1. Quản trị viên dùng management token tạo policy và token.
2. Cấp application token theo service identity và nhiệm vụ của workload.
3. Gắn token vào Spring Cloud Consul qua secret injection.
4. Xác minh các API cần thiết hoạt động và các API ngoài phạm vi bị từ chối.
5. Lưu `AccessorID` để quản lý vòng đời; bảo vệ `SecretID` như password.
6. Thu hồi token khi service bị loại bỏ, credential nghi ngờ bị lộ hoặc workload không còn cần quyền.

Không đặt token thật trong Git, Docker image, log, ticket, chat, command line history hoặc Actuator environment endpoint. Tránh bật `/actuator/env` hay `/actuator/configprops` công khai vì có thể làm lộ property chứa token.

## 11. Truyền token khi gọi Consul HTTP API

Consul HTTP API nhận token qua header `X-Consul-Token`. Ví dụ truy vấn service health:

```bash
curl --header "X-Consul-Token: ${CONSUL_DISCOVERY_TOKEN}" \
  "http://127.0.0.1:8500/v1/health/service/inventory-service?passing=true"
```

PowerShell:

```powershell
$headers = @{ "X-Consul-Token" = $env:CONSUL_DISCOVERY_TOKEN }
Invoke-RestMethod -Headers $headers -Uri "http://127.0.0.1:8500/v1/health/service/inventory-service?passing=true"
```

Không đặt token vào query string, vì URL thường xuất hiện trong access log, proxy log và lịch sử shell. Dùng HTTPS/TLS để bảo vệ token khi truyền qua mạng; ACL xác thực và phân quyền request nhưng không tự mã hóa đường truyền.

## 12. Kiểm tra quyền đã cấp

Kiểm thử cả thao tác được phép và thao tác bị cấm. Không chỉ kiểm tra service registration thành công rồi kết luận policy đã tối thiểu.

| Bài kiểm tra | Token producer | Token consumer |
|---|---|---|
| Đăng ký `inventory-service` | Cho phép nếu có `service:write` | Từ chối nếu chỉ read |
| Đăng ký `payment-service` | Từ chối nếu policy chỉ write `inventory-service` | Từ chối nếu chỉ read |
| Đọc `inventory-service` | Tùy policy có `service:read` hay không | Cho phép nếu được cấp service/node read |
| Đọc service ngoài phạm vi | Từ chối nếu policy chỉ định service cụ thể | Từ chối nếu policy chỉ định service cụ thể |
| Ghi KV | Từ chối nếu không có key write | Từ chối nếu chỉ có service/node read |
| Tạo ACL token hoặc policy | Từ chối nếu không có `acl:write` | Từ chối nếu không có `acl:write` |
| Gửi TTL pass/warn/fail | Cần `node:write` và `service:write` cho check tương ứng | Thường không cần và nên bị từ chối |

Có thể xem policy gắn với token bằng lệnh ACL quản trị thích hợp. Khi debug, kiểm tra token thực tế mà Spring Cloud gửi, policy đang gắn, service name chính xác, node name, datacenter và namespace/partition nếu dùng Enterprise.

## 13. Lỗi ACL thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Spring Cloud Consul nhận HTTP 403 khi đăng ký | Token thiếu `service:write` cho service name hoặc token sai | Kiểm tra `spring.cloud.consul.discovery.acl-token` và policy của service |
| Registration thành công nhưng consumer không thấy instance | Token query thiếu `service:read` hoặc `node:read`; ACL lọc kết quả | Kiểm tra Health API bằng đúng token consumer và scope service/node |
| Catalog API đọc được nhưng Health API không trả endpoint | Thiếu `node:read` hoặc node rule giới hạn node | Bổ sung node read đúng phạm vi và kiểm tra node name |
| TTL heartbeat bị 403 | Token có service write nhưng thiếu `node:write` cho node chứa check | Cấp node write đúng một node, hoặc dùng mô hình health check khác |
| Consul Agent báo lỗi anti-entropy | `acl.tokens.agent` thiếu node write cho chính node hoặc service read | Sửa agent token riêng, không nâng quyền application token một cách tùy tiện |
| Consul Config không đọc được KV | `spring.cloud.consul.config.acl-token` thiếu key read hoặc sai prefix | Cấp `key_prefix` read đúng nơi chứa config |
| Local chạy được nhưng production bị 403 | Local đang dùng anonymous/ACL chưa enforcement hoặc token khác với production | Kiểm tra cấu hình ACL thật và token được inject ở runtime |
| Token hết hiệu lực sau rotation | Secret mới chưa được deploy đồng bộ hoặc token cũ đã bị revoke | Kiểm tra rollout và xác minh request bằng token mới trước khi revoke token cũ |

ACL có thể làm kết quả discovery trông giống như service không tồn tại vì API lọc những service/node mà token không được đọc. Khi consumer nhận danh sách rỗng, hãy kiểm tra quyền bằng token thực tế trước khi kết luận producer chưa đăng ký.

## 14. Quy trình xoay vòng và thu hồi token

Xoay vòng token không nên làm gián đoạn service discovery:

1. Tạo policy mới hoặc xác nhận policy hiện tại vẫn đúng.
2. Tạo token mới gắn với policy đó.
3. Lưu `SecretID` mới vào secret store.
4. Cập nhật workload để nhận token mới và restart/refresh theo cơ chế triển khai.
5. Xác minh registration, heartbeat và discovery bằng token mới.
6. Chờ các instance cũ không còn dùng token cũ.
7. Thu hồi token cũ bằng ACL token revoke khi chắc chắn không còn consumer sử dụng.
8. Kiểm tra audit/log và loại bỏ secret cũ khỏi nơi lưu trữ theo quy trình.

Không revoke token cũ trước khi các workload chuyển sang token mới. Nếu token bị lộ, có thể cần revoke khẩn cấp và chấp nhận tác động vận hành; sau đó tạo token mới với policy hẹp và kiểm tra registration/health lại.

## 15. Checklist least privilege

- [ ] ACL được bật trên Consul agents và `default_policy` phù hợp với chế độ enforcement.
- [ ] Management token chỉ dùng cho quản trị ACL, không được inject vào microservice.
- [ ] Mỗi workload có token riêng theo service identity và trách nhiệm.
- [ ] Producer chỉ có `service:write` cho service name của chính nó nếu chỉ cần đăng ký.
- [ ] Consumer có `service:read` và `node:read` cho các service/node nó được phép khám phá.
- [ ] Service vừa producer vừa consumer có write cho chính nó và read cho upstream cần gọi.
- [ ] TTL heartbeat chỉ được cấp `node:write` cho node chứa check cùng `service:write` tương ứng.
- [ ] Agent internal token (`acl.tokens.agent`) tách biệt với application token.
- [ ] `acl.tokens.default` không phải management token và có quyền đọc tối thiểu cần thiết cho DNS/default requests.
- [ ] Consul Config dùng token riêng với `key_prefix` read đúng phạm vi nếu ứng dụng thực sự dùng KV.
- [ ] SecretID được lưu trong secret manager, không commit hoặc log.
- [ ] Token được truyền qua HTTPS/TLS và header `X-Consul-Token` khi gọi HTTP API.
- [ ] Đã kiểm thử cả thao tác được phép và thao tác phải bị từ chối.
- [ ] Có quy trình rotation, revoke và xử lý token bị lộ.

## Tài liệu tham khảo

- [Spring Cloud Consul 5.1.0 — Common Application Properties (`discovery.acl-token`, `config.acl-token`)](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [HashiCorp Consul — Create Tokens for Service Registration](https://developer.hashicorp.com/consul/docs/secure/acl/token/service)
- [HashiCorp Consul — ACL Rules](https://developer.hashicorp.com/consul/docs/secure/acl/rule)
- [HashiCorp Consul — Create Tokens for Agent Registration](https://developer.hashicorp.com/consul/docs/secure/acl/token/agent)
- [HashiCorp Consul — ACL Bootstrap](https://developer.hashicorp.com/consul/docs/secure/acl/bootstrap)
- [HashiCorp Consul — Agent Service Registration API](https://developer.hashicorp.com/consul/api-docs/agent/service)
- [HashiCorp Consul — Agent Check API and TTL permissions](https://developer.hashicorp.com/consul/api-docs/agent/check)
- [HashiCorp Consul — ACL Agent Configuration](https://developer.hashicorp.com/consul/docs/reference/agent/configuration-file/acl)

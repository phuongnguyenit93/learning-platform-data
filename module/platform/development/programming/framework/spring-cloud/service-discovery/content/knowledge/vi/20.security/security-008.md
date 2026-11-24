# Quản lý thông tin xác thực bằng cấu hình bí mật bên ngoài

Ứng dụng Spring Cloud Service Discovery thường cần thông tin xác thực để kết nối registry, đăng ký instance, đọc danh sách service hoặc gọi API quản trị. Ví dụ: Consul ACL token, thông tin xác thực HTTP của Eureka, thông tin xác thực ZooKeeper hoặc thông tin đăng nhập tới một secret manager. Nếu đặt các giá trị này trực tiếp trong source code, application.yml được commit hoặc Docker image, bí mật có thể bị lộ qua Git, log, image layer, bản sao lưu và hệ thống CI/CD.

Cách triển khai an toàn là tách cấu hình thông thường khỏi secret, lưu secret trong hệ thống quản lý bí mật hoặc nguồn cấu hình được bảo vệ, rồi nạp chúng vào Spring Boot tại runtime. Bài học này tập trung vào credentials phục vụ Service Discovery trong Spring Cloud: cấp quyền đúng vai trò, nạp secret bên ngoài, xoay vòng thông tin xác thực và kiểm soát nơi secret xuất hiện.

## 1. Phân biệt cấu hình và secret

Cấu hình cho biết ứng dụng kết nối tới đâu và hoạt động như thế nào. Secret chứng minh ứng dụng có quyền truy cập.

| Loại dữ liệu | Ví dụ | Có thể commit vào Git? |
|---|---|---|
| Registry endpoint | registry.internal:8500 | Có thể, nếu không chứa thông tin nhạy cảm |
| Service name | inventory-service | Có thể |
| Port ứng dụng | 8081 | Có thể |
| Connect/read timeout | 2s, 3s | Có thể |
| Consul ACL token | Token có quyền đọc/đăng ký service | Không |
| Eureka username/password | Thông tin xác thực HTTP Basic | Không |
| ZooKeeper credential | Digest/SASL credential hoặc material xác thực | Không |
| TLS private key | Khóa riêng của client hoặc service | Không |
| Secret manager token | Token để lấy secret runtime | Không |

Một số giá trị nhìn giống cấu hình nhưng có thể chứa secret. Ví dụ URL có dạng user:password@host hoặc JDBC URL chứa password. Hãy phân loại theo nội dung thực tế, không chỉ dựa trên tên thuộc tính.

Không nên đặt secret trong source code, file application.yml được commit, Dockerfile, build argument, image layer, Git commit, pull request, pipeline log, metadata service, tên service, tag hoặc label. Không lưu secret trong log startup, exception message, Actuator endpoint hoặc tracing baggage.

Nếu secret đã được commit hoặc đưa vào log, xóa dòng khỏi phiên bản hiện tại chưa đủ. Cần thu hồi hoặc rotate secret vì các bản sao có thể vẫn tồn tại trong Git history, artifact, cache và log.

## 2. Các nguồn cung cấp secret bên ngoài

Tùy hạ tầng, ứng dụng có thể lấy secret từ:

- **Secret manager:** HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, Google Secret Manager hoặc hệ thống tương đương.
- **Orchestrator:** Kubernetes Secret được mount vào Pod hoặc secret integration của nền tảng container.
- **Container runtime:** Docker/Compose secrets được mount thành file chỉ đọc.
- **Máy ảo:** systemd credentials, file được bảo vệ quyền truy cập hoặc secret agent.
- **CI/CD:** secret store của pipeline dùng để cấp credential khi deploy, không in giá trị ra log.
- **Spring Boot externalized configuration:** environment variable, external properties file hoặc config tree được mount từ nguồn bảo mật.

Secret manager thường có lợi thế về audit, policy, rotation và kiểm soát truy cập tập trung. File mount hoặc environment variable có thể phù hợp với hệ thống nhỏ hơn, nhưng đội vận hành phải quản lý quyền file, phân phối, rotation và thu hồi.

Không có một nguồn secret duy nhất phù hợp với mọi môi trường. Hãy chọn theo khả năng kiểm soát truy cập, audit, rotation, độ sẵn sàng và cách workload chứng minh danh tính với nguồn cấp secret.

## 3. Nạp secret bằng Spring Boot Config Tree

Spring Boot hỗ trợ import cấu hình từ thư mục thông qua tiền tố `configtree:`. Mỗi file trong thư mục được xem như một property; tên file là property key và nội dung file là giá trị. Cách này phù hợp với secret được mount từ Docker, Kubernetes hoặc hệ thống quản lý credential của máy chủ.

Ví dụ cấu trúc thư mục:

```text
/run/secrets/
  discovery.consul.acl-token
  discovery.registry.username
  discovery.registry.password
```

File `discovery.consul.acl-token` chứa token, file username/password chứa thông tin xác thực tương ứng. Không ghi giá trị thật vào repository.

Trong `application.yml`, khai báo:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  application:
    name: inventory-service
  cloud:
    consul:
      host: consul.internal.example
      port: 8500
      discovery:
        register: true
        acl-token: ${discovery.consul.acl-token}
```

Trong ví dụ, Spring Boot nạp file từ thư mục và cung cấp property `discovery.consul.acl-token`. Placeholder chuyển giá trị đó vào thuộc tính token của Consul Discovery. Hãy xác minh tên thuộc tính provider-specific theo phiên bản Spring Cloud Consul mà dự án đang sử dụng.

Không dùng tiền tố `optional:` cho secret bắt buộc trong production nếu ứng dụng không thể hoạt động an toàn khi thiếu credential. Nếu import là bắt buộc, Spring Boot sẽ báo lỗi cấu hình khi thư mục hoặc property cần thiết không tồn tại. Trong môi trường local có thể dùng optional nếu có một phương án phát triển an toàn khác, nhưng không để ứng dụng production âm thầm chạy mà không có xác thực.

### Dùng external properties file

Có thể mount một file properties riêng:

```properties
discovery.consul.acl-token=VALUE_INJECTED_AT_RUNTIME
```

Sau đó import file từ vị trí được bảo vệ:

```yaml
spring:
  config:
    import: "file:/etc/inventory/secrets/discovery.properties"
```

Đường dẫn và quyền file phải được quản lý bởi hệ điều hành hoặc secret manager. File chỉ nên đọc được bởi user chạy ứng dụng và nhóm vận hành có thẩm quyền.

## 4. Ví dụ Consul ACL token

Consul có thể dùng ACL token để kiểm soát client được phép đăng ký, đọc catalog hoặc thực hiện thao tác quản trị. Token nên được cấp đúng policy cần thiết cho service.

Ví dụ cấu hình discovery:

```yaml
spring:
  application:
    name: inventory-service
  config:
    import: "configtree:/run/secrets/"
  cloud:
    consul:
      host: consul.internal.example
      port: 8500
      discovery:
        register: true
        acl-token: ${discovery.consul.acl-token}
```

Secret file được mount ở:

```text
/run/secrets/discovery.consul.acl-token
```

Không nên dùng một token quản trị toàn quyền cho mọi microservice. Tách policy theo vai trò:

- Provider chỉ có quyền đăng ký, cập nhật và hủy registration thuộc phạm vi được cấp.
- Consumer có quyền đọc service/catalog cần thiết.
- Công cụ vận hành có quyền quản trị cao hơn, được cấp cho nhóm người và workload riêng.
- Pipeline triển khai chỉ nhận quyền trong thời gian và phạm vi cần thiết.

Tên và phạm vi policy cụ thể phụ thuộc Consul ACL configuration. Cần kiểm tra quyền của token với thao tác thực tế: provider đăng ký được hay không, consumer đọc được service hay không, và token không có quyền ngoài dự kiến.

## 5. Eureka credentials và cấu hình HTTP client

Eureka client thường giao tiếp với Eureka Server qua HTTP endpoint. Nếu server bật xác thực, client phải cung cấp credential theo cơ chế được hỗ trợ bởi phiên bản Spring Cloud Netflix và cấu hình HTTP transport đang sử dụng.

Không có một thuộc tính username/password chung của Spring Cloud áp dụng cho mọi registry. Một số cấu hình Eureka có thể biểu diễn thông tin xác thực trong URL service endpoint, nhưng URL có user-info rất dễ bị ghi vào log, exception, actuator hoặc diagnostic output. Nếu phiên bản và transport yêu cầu cách này, phải lấy toàn bộ URL từ secret store, hạn chế quyền đọc cấu hình và che giá trị khi log. Ưu tiên cơ chế credential/HTTP client được hỗ trợ và có thể bảo vệ rõ ràng trong phiên bản dự án.

Ví dụ externalize endpoint khi hệ thống yêu cầu một URL đã chứa thông tin xác thực:

```yaml
eureka:
  client:
    service-url:
      defaultZone: ${discovery.eureka.service-url}
```

Secret file hoặc secret manager cung cấp property `discovery.eureka.service-url` tại runtime. Giá trị thực không được ghi trong application.yml hoặc Git. Đặt URL qua placeholder chỉ giải quyết việc tách secret khỏi source; nó không tự che URL khỏi log hay các endpoint chẩn đoán.

Nếu dùng HTTP Basic hoặc custom Client configuration, hãy xác minh cách truyền credential theo đúng phiên bản Eureka client. Tránh tự tạo interceptor hoặc transport không được kiểm soát rồi vô tình log header Authorization.

## 6. ZooKeeper authentication và ACL

ZooKeeper bảo vệ dữ liệu bằng ACL trên znode và cơ chế xác thực như digest hoặc SASL tùy cách triển khai. Spring Cloud Zookeeper sử dụng client/Curator để kết nối và thao tác registration. Credential phải được cấp cho đúng root path và thao tác cần thiết.

Ví dụ về cách tổ chức secret bên ngoài:

```text
/run/secrets/
  discovery.zookeeper.username
  discovery.zookeeper.password
```

Ứng dụng đọc các property đó rồi cấu hình cơ chế authentication mà Curator/ZooKeeper client của phiên bản đang dùng hỗ trợ. Tên thuộc tính Spring Cloud Zookeeper, cách thiết lập authentication scheme và ACL phụ thuộc phiên bản; không nên giả định chỉ cần đặt một property password là mọi znode tự động được bảo vệ.

Một số nguyên tắc:

- Provider cần quyền tạo và xóa registration trong root path được cấp.
- Consumer cần quyền đọc service registration.
- Không cấp quyền ghi/xóa toàn bộ cây ZooKeeper cho mọi ứng dụng.
- Không lưu digest password, SASL secret hoặc private key trong metadata service.
- Kiểm tra ACL trên znode sau khi registration được tạo, thay vì chỉ xác nhận kết nối session thành công.

Session ZooKeeper còn sống không có nghĩa credential được bảo vệ đúng. Xác thực kết nối và authorization trên từng znode là hai bước khác nhau.

## 7. Phân phối secret trên máy ảo

Trên VM, secret có thể được cấp bởi secret agent, systemd credentials hoặc file do hệ thống quản trị cấu hình tạo ra. Ví dụ file properties:

```text
/etc/inventory/secrets/discovery.properties
```

File cần có owner là user/group phù hợp và quyền đọc tối thiểu. Trên Linux có thể dùng quyền tương đương `0600` nếu chỉ user ứng dụng cần đọc. Không đặt file trong thư mục source code hoặc thư mục artifact được backup công khai.

Ví dụ import external file:

```yaml
spring:
  config:
    import: "file:/etc/inventory/secrets/discovery.properties"
```

Nếu dùng systemd, có thể cấp credential thông qua cơ chế credentials của systemd rồi cấu hình Spring Boot đọc từ thư mục credentials được runtime cung cấp. Không nên mặc định đường dẫn runtime giống nhau trên mọi phiên bản systemd; hãy dùng biến môi trường và đường dẫn mà service manager cung cấp.

EnvironmentFile có thể là phương án đơn giản, nhưng biến môi trường có thể xuất hiện trong process inspection, diagnostic dump hoặc công cụ quản trị. Với secret có giá trị cao, ưu tiên file credential với quyền truy cập chặt hoặc secret agent.

## 8. Phân phối secret trong Docker và Kubernetes

### Docker Compose secrets

Docker Compose có thể mount secret thành file trong container:

```yaml
services:
  inventory:
    image: example/inventory:1.0
    secrets:
      - source: consul_acl_token
        target: discovery.consul.acl-token

secrets:
  consul_acl_token:
    file: ./runtime-secrets/consul_acl_token
```

Trong container, file có thể xuất hiện tại `/run/secrets/discovery.consul.acl-token`. Cấu hình Spring Boot import thư mục:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
```

Cách lưu secret của Compose phụ thuộc chế độ triển khai và runtime. Không commit file nguồn `runtime-secrets/consul_acl_token` vào Git; bảo vệ file trên host và kiểm soát quyền người được phép deploy.

### Kubernetes Secret volume

Có thể mount một key của Kubernetes Secret thành file:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: inventory-discovery-credentials
  namespace: shop
type: Opaque
stringData:
  discovery.consul.acl-token: REPLACE_AT_DEPLOY_TIME
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: inventory
  template:
    metadata:
      labels:
        app: inventory
    spec:
      containers:
        - name: inventory
          image: example/inventory:1.0
          volumeMounts:
            - name: discovery-secrets
              mountPath: /run/secrets
              readOnly: true
      volumes:
        - name: discovery-secrets
          secret:
            secretName: inventory-discovery-credentials
```

Với key `discovery.consul.acl-token`, Kubernetes tạo file tương ứng trong thư mục mount; Spring Boot Config Tree có thể đọc property cùng tên. Ví dụ dùng placeholder:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  cloud:
    consul:
      discovery:
        acl-token: ${discovery.consul.acl-token}
```

Kubernetes Secret không tự động đồng nghĩa dữ liệu đã được mã hóa an toàn ở mọi nơi. Cần bật encryption at rest cho datastore theo cấu hình cluster, giới hạn RBAC, hạn chế quyền đọc Secret theo namespace/service account, bảo vệ backup và kiểm soát quyền truy cập node. Không đặt giá trị thật trong manifest được commit. Có thể để pipeline hoặc External Secrets/CSI integration tạo Secret từ secret manager.

## 9. Dùng Spring Cloud Vault hoặc secret manager

Spring Cloud Vault hỗ trợ nạp cấu hình từ Vault thông qua Spring Boot Config Data. Khi đã thêm dependency phù hợp và cấu hình xác thực an toàn, ứng dụng có thể import secret:

```yaml
spring:
  config:
    import: "vault://"
```

Vault path, mount, profile và property mapping cần cấu hình theo phiên bản Spring Cloud Vault và cách tổ chức secret của tổ chức. Token dùng để xác thực với Vault cũng là secret; không đặt token dài hạn trong application.yml. Ưu tiên workload identity, Kubernetes auth, AppRole hoặc cơ chế danh tính tương đương để workload lấy quyền truy cập tối thiểu.

Nếu dùng AWS Secrets Manager, Azure Key Vault hoặc Google Secret Manager, chọn integration được tổ chức hỗ trợ. Nguyên tắc vẫn giống nhau: ứng dụng xác thực với secret manager bằng danh tính workload, đọc đúng secret, hạn chế thời gian sống và không in giá trị ra log.

Không để secret manager trở thành một điểm phụ thuộc không được thiết kế. Xác định điều gì xảy ra khi secret manager tạm thời không truy cập được: ứng dụng đã chạy có giữ credential trong bộ nhớ hay không, startup mới có bị chặn không, cache có TTL bao lâu và có cơ chế khôi phục nào.

## 10. Tách quyền đăng ký và quyền truy vấn

Provider và consumer có nhu cầu quyền khác nhau. Nếu dùng chung một credential toàn quyền, một lỗi hoặc một workload bị xâm nhập có thể ảnh hưởng toàn bộ registry.

| Vai trò | Quyền cần thiết | Quyền nên tránh |
|---|---|---|
| Provider | Đăng ký/cập nhật/hủy instance của service được sở hữu | Xóa hoặc sửa registration của service khác |
| Consumer | Đọc service và instance cần gọi | Đăng ký giả service hoặc sửa catalog |
| Health checker | Đọc/kiểm tra endpoint theo cấu hình | Quyền quản trị registry không liên quan |
| Operator | Quản trị theo nhiệm vụ và audit | Dùng credential operator làm credential runtime |
| CI/CD | Cấp secret/deploy trong phạm vi pipeline | Dùng token runtime lâu dài cho mọi bước build |

Với Eureka, authorization thường được kiểm soát ở tầng server/proxy và HTTP authentication; với Consul, dùng ACL policy/token; với ZooKeeper, dùng authentication và ACL trên znode. Mô hình quyền khác nhau, nhưng nguyên tắc least privilege giống nhau.

Cũng cần phân biệt credential registry với danh tính service-to-service. Token cho phép consumer đọc Consul không tự động chứng minh consumer được phép gọi API thanh toán. Traffic nghiệp vụ vẫn cần TLS, authentication/authorization và policy riêng.

## 11. Rotation và thu hồi secret

Secret có thể bị lộ, hết hạn hoặc cần thay theo chính sách. Rotation nên được thực hiện có kế hoạch để tránh toàn bộ provider/consumer mất kết nối registry cùng lúc.

Quy trình tổng quát:

1. Tạo credential mới với quyền tương đương hoặc hẹp hơn credential cũ.
2. Lưu credential mới trong secret manager hoặc nguồn cấp secret.
3. Phân phối cho một nhóm nhỏ provider/consumer thử nghiệm.
4. Xác minh registration, heartbeat và lookup hoạt động với credential mới.
5. Triển khai dần tới các instance còn lại.
6. Kiểm tra không còn client sử dụng credential cũ.
7. Thu hồi credential cũ.
8. Theo dõi lỗi xác thực và audit sau rotation.

Không phải mọi client đều tự reload credential khi file mount thay đổi. Một số integration chỉ đọc cấu hình lúc khởi động hoặc tạo HTTP client một lần. Khi không có cơ chế refresh được hỗ trợ, hãy rolling restart có kiểm soát sau khi secret mới đã sẵn sàng.

Với token ngắn hạn, cần xử lý refresh trước thời điểm hết hạn, đồng bộ clock và lỗi khi secret manager tạm thời không truy cập được. Không retry vô hạn với token đã bị thu hồi; cần phân biệt lỗi xác thực với lỗi network.

## 12. Bảo vệ secret khỏi log và endpoint quản trị

Secret có thể bị lộ dù không nằm trong Git. Các nguồn rò rỉ phổ biến:

- Log cấu hình hoặc exception chứa URL có user-info.
- HTTP Authorization header bị log ở mức DEBUG.
- Actuator env/configprops hiển thị property nhạy cảm.
- Heap dump, thread dump, crash dump hoặc diagnostic bundle.
- CI/CD echo biến môi trường hoặc bật shell tracing.
- Container inspection, process arguments hoặc file system snapshot.
- Metadata hoặc tag trong registry chứa token.

Biện pháp giảm rủi ro:

- Không log giá trị secret; chỉ log tên property và trạng thái có/không có.
- Che URL và Authorization header trong HTTP logging.
- Giới hạn Actuator endpoint; không expose env/configprops ra mạng công khai.
- Không dùng `set -x`, `echo $SECRET` hoặc lệnh in biến bí mật trong pipeline.
- Hạn chế quyền truy cập heap dump và backup.
- Dùng secret riêng theo môi trường và workload.
- Có quy trình thu hồi/rotation khi phát hiện log hoặc artifact bị lộ.

Nếu cần debug, có thể ghi nhận token đã được nạp hay chưa bằng boolean hoặc fingerprint không thể đảo ngược theo quy trình được phê duyệt; không in token nguyên văn.

## 13. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Spring Boot báo thiếu placeholder | Secret file không mount hoặc property key sai | Kiểm tra tên file, mount path và config import |
| Consul trả 403 | Token hợp lệ nhưng thiếu policy | Kiểm tra ACL policy và quyền theo service |
| Consul trả 401 | Token thiếu, sai hoặc hết hạn | Kiểm tra nguồn secret và rotation |
| Eureka trả 401/403 | Credential hoặc authorization không khớp | Kiểm tra server security và cách cấu hình HTTP client |
| ZooKeeper báo AuthFailed | Authentication scheme/credential sai hoặc ACL không cho phép | Kiểm tra client auth và ACL trên znode |
| Kết nối registry timeout | DNS, routing, firewall hoặc TLS | Kiểm tra network trước khi rotate credential |
| Secret mới không có hiệu lực | Client chưa refresh hoặc chỉ đọc lúc startup | Xác minh cơ chế reload; rolling restart nếu cần |
| Ứng dụng chạy local nhưng lỗi trong container | Secret mount/path hoặc file permission khác | Kiểm tra mount read-only và user chạy container |
| Secret xuất hiện trong log | URL/header/config bị log | Giảm log, che dữ liệu và rotate secret đã lộ |

Phân biệt lỗi xác thực với lỗi kết nối. HTTP 401/403 hoặc ZooKeeper AuthFailed thường chỉ ra vấn đề credential/authorization; timeout và connection refused thường liên quan DNS, route, firewall, port hoặc server. Không thay token liên tục khi nguyên nhân là network.

## 14. Checklist trước khi triển khai

1. Cấu hình endpoint registry và service name không chứa secret.
2. Secret được lưu ngoài source code, Git và image.
3. Spring Boot nạp secret từ nguồn runtime được bảo vệ.
4. Secret bắt buộc không bị cấu hình optional ngoài ý muốn.
5. Provider và consumer có credential riêng theo vai trò.
6. Token/ACL chỉ cấp quyền tối thiểu.
7. Eureka/ZooKeeper/Consul dùng đúng cơ chế auth theo phiên bản.
8. TLS và trust material được quản lý riêng, không nhúng private key vào repository.
9. Secret không xuất hiện trong log, Actuator, metadata hoặc pipeline output.
10. Có quy trình rotation, refresh và revoke.
11. Có phương án khi secret manager hoặc config source tạm thời không truy cập được.
12. Kiểm tra xác thực thật từ từng workload sau deploy.
13. Audit việc đọc secret và thay đổi policy.
14. Có quy trình xử lý khi credential bị lộ.

Quản lý credentials bằng cấu hình bí mật bên ngoài giúp tách quyền truy cập registry khỏi mã nguồn và artifact triển khai. Spring Boot có thể nạp secret từ config tree, file mount hoặc secret manager; provider-specific integration chuyển giá trị đó thành credential cho Consul, Eureka hoặc ZooKeeper. Hiệu quả bảo mật phụ thuộc vào quyền tối thiểu, TLS, bảo vệ log, rotation và khả năng thu hồi — không chỉ ở việc đưa password ra khỏi application.yml.

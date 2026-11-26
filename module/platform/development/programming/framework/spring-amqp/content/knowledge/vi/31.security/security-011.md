# Cô lập management endpoint và cập nhật bản vá thư viện

Một hệ thống dùng **RabbitMQ và Spring AMQP** thường có hai nhóm giao tiếp rất khác nhau: **đường truyền message** để `RabbitTemplate` gửi và `@RabbitListener` nhận, và **đường quản trị/giám sát** để vận hành broker. Nếu đưa Management UI hoặc HTTP API ra Internet cùng ứng dụng, đối tượng không được phép có thể dò tìm cấu hình, xem trạng thái queue hoặc — khi có tài khoản đủ quyền — thay đổi topology, purge message hay đóng connection. Ngay cả khi đã chặn truy cập quản trị, việc để broker hoặc thư viện Java ở phiên bản có lỗ hổng cũng tạo rủi ro riêng.

Bài học thuộc chương **Bảo mật** của module **SPRING_AMQP**. Ta sẽ thực hành **cô lập management endpoint**, cấu hình TLS và quyền tối thiểu, phân biệt Management API, Prometheus metrics và Spring Boot Actuator, sau đó xây quy trình **kiểm kê – đánh giá – vá – kiểm thử – triển khai – giám sát** cho RabbitMQ, Erlang/OTP, Spring AMQP và các thư viện liên quan. Mục tiêu cuối cùng là bảo vệ quá trình định tuyến exchange/queue/binding, xác nhận giao nhận, retry, dead-letter và giao dịch của ứng dụng xử lý bất đồng bộ.

## 1. Nhận diện chính xác những endpoint cần bảo vệ

RabbitMQ có nhiều giao thức và cổng kết nối. Management UI/HTTP API **không phải** cổng dùng để gửi hoặc tiêu thụ AMQP message.

| Bề mặt | Cổng thường gặp | Ai cần truy cập? | Rủi ro khi mở rộng phạm vi |
|---|---:|---|---|
| AMQP 0-9-1 và AMQP 1.0 không TLS | `5672` | Ứng dụng producer/consumer nếu chính sách cho phép | Nghe lén/xâm nhập đường message khi thiếu TLS hoặc ACL |
| AMQP qua TLS | `5671` | Ứng dụng Spring AMQP được cấp quyền | Sai chứng chỉ, sai trust chain, tài khoản dùng chung |
| **RabbitMQ Management UI + HTTP API** | **`15672` (HTTP)** | Nhân viên vận hành và automation được phép | Lộ cấu hình, thao tác quản trị, thay đổi queue/exchange |
| Management qua HTTPS | **`15671`** *nếu cấu hình TLS listener* | Admin qua VPN/bastion/identity proxy | TLS không thay thế xác thực hoặc phân quyền |
| `rabbitmq_prometheus` metrics HTTP | **`15692`** khi plugin bật | Hệ thống monitoring/scraper | Lộ topology, số liệu vận hành và thông tin tài nguyên |
| Prometheus metrics qua TLS | `15691` khi cấu hình | Monitoring/scraper được phép | Chứng chỉ không hợp lệ hoặc lộ metrics |
| Erlang distribution / EPMD | Ví dụ `25672` / `4369` | Node RabbitMQ và công cụ nội bộ cần thiết | Lộ bề mặt clustering/điều khiển nội bộ |
| Spring Boot Actuator | Theo cổng quản lý ứng dụng, thường là HTTP app nếu chưa tách | Health-check/monitoring/ops | `/actuator/env`, `/actuator/heapdump` hoặc endpoint nhạy cảm nếu cấu hình sai |

Các cổng trên là **giá trị phổ biến**, không phải hằng số bắt buộc. RabbitMQ cho phép thay đổi listener port/interface; môi trường container, reverse proxy và Kubernetes Service cũng có thể ánh xạ cổng khác. Trước khi áp dụng firewall, luôn kiểm tra listener thực tế bằng `rabbitmq-diagnostics -s listeners`.

~~~mermaid
flowchart LR
    APP["Spring service"] -->|"AMQPS 5671"| BROKER["RabbitMQ broker"]
    OPS["Admin qua VPN / bastion"] -->|"HTTPS 15671"| MGT["Management UI + HTTP API"]
    OBS["Prometheus nội bộ"] -->|"Metrics 15692 hoặc TLS"| MET["Prometheus exporter"]
    BROKER --- MGT
    BROKER --- MET
    INTERNET["Internet không tin cậy"] -.->|"Chặn tại firewall / ingress"| MGT
    INTERNET -.->|"Chặn"| MET
~~~

**Điểm cần nhớ:** cùng một plugin `rabbitmq_management` cung cấp **giao diện web và HTTP API**. Chặn giao diện HTML nhưng để `/api/*` công khai không phải cô lập endpoint. Ngược lại, endpoint Prometheus thường chạy trên **cổng riêng**, nên chặn `15672` chưa có nghĩa `15692` đã được bảo vệ.

## 2. Mô hình đe dọa và nguyên tắc phòng thủ nhiều lớp

Giả sử một nhóm tấn công hoặc một máy nội bộ đã bị xâm nhập tìm thấy Management API. Tùy quyền của tài khoản bị lộ, họ có thể lấy metadata về virtual host, queue, connection, publish/consume từ một số tài nguyên hoặc phá rối luồng message thông qua những thao tác mà quyền đó cho phép. Dữ liệu riêng tư, số lượng backlog và quan hệ giữa dịch vụ đều có thể là thông tin nhạy cảm.

Không đặt toàn bộ an toàn vào một mật khẩu mạnh. Cần nhiều lớp phòng thủ:

1. **Giảm bề mặt:** nếu không cần Management API trong môi trường đó, cân nhắc tắt plugin; nếu cần, chỉ bật nơi có người vận hành/automation truy cập hợp lệ.
2. **Cô lập mạng:** chỉ cho phép nguồn quản trị tin cậy truy cập management listener; tách khỏi ingress public và mạng của khách hàng.
3. **Mã hóa truyền tải:** dùng HTTPS/TLS trực tiếp hoặc thông qua proxy quản trị bảo mật; kiểm tra chứng chỉ và hostname.
4. **Xác thực và phân quyền:** tài khoản riêng theo vai trò, vhost permissions và management tags phù hợp; không sử dụng tài khoản producer/consumer làm admin.
5. **Vá lỗi và kiểm kê:** broker, Erlang, plugin, Java runtime, Spring và thư viện đều cần vòng đời cập nhật.
6. **Quan sát và phản ứng:** thu thập access/error logs, giám sát login bất thường, thao tác quản trị, thay đổi topology và đột biến queue.

| Tình huống | Biện pháp phòng ngừa | Cách xác minh |
|---|---|---|
| `15672` bị publish trực tiếp ra Internet | Private subnet, firewall, không public LoadBalancer/Ingress | Kiểm tra từ một mạng không được phép: không kết nối được |
| Tài khoản admin bị lộ | Least privilege, secret rotation, SSO/proxy khi hỗ trợ, nhật ký truy cập | Kiểm tra danh sách người dùng và quyền; diễn tập thu hồi |
| HTTP plaintext trên mạng không tin cậy | HTTPS/TLS, VPN/bastion, xác minh certificate | Client chỉ dùng HTTPS; đường HTTP bị chặn theo policy |
| Prometheus endpoint ai cũng đọc được | Chỉ cho monitoring scrape; bật auth/TLS khi phù hợp | Test mạng bên ngoài monitoring không thấy metrics |
| Client Spring lỗi thời | BOM/lockfile, SCA scan, thử bản vá trong CI | Xem resolved dependency và báo cáo CVE |
| Broker/Erlang có bản vá mới | Theo dõi advisory và compatibility matrix, rollout có kiểm soát | Xác nhận phiên bản sau deploy, cluster health |
| Actor có quyền purge/delete queue | Không cấp quyền quản trị rộng cho ứng dụng | Login bằng tài khoản app không gọi được API nguy hiểm |

## 3. Cô lập Management UI và HTTP API ở lớp mạng

### 3.1. Chọn kiến trúc quản trị riêng

Một cấu hình production dễ kiểm soát:

~~~text
Internet
    |
    +--> Public API / business load balancer
    |          |
    |          +--> Spring application --> AMQPS --> RabbitMQ
    |
    +--X--> RabbitMQ Management UI / HTTP API

VPN / Zero Trust access / bastion
    |
    +--> Admin reverse proxy (MFA, audit, IP policy)
               |
               +--> Private RabbitMQ Management HTTPS

Prometheus private network --> Metrics endpoint
~~~

Nên đặt RabbitMQ trong **private subnet**, giới hạn traffic theo nguồn và cổng tại firewall/security group. Nếu dùng Kubernetes, tránh tạo `NodePort` hoặc `LoadBalancer` public cho management Service, trừ khi đây là thiết kế đặc biệt đã qua kiểm soát bảo mật. Bản thân một Service `ClusterIP` chỉ giới hạn cách publish Service ra bên ngoài; **các pod nội bộ vẫn có thể gọi nó** nếu NetworkPolicy không hạn chế.

Một cách chia luồng:

- Spring producers/consumers chỉ cần cổng AMQP (ưu tiên TLS), không cần HTTP API quản trị.
- Admin/bastion có thể gọi Management HTTPS, theo danh tính và thời gian được cấp quyền.
- Monitoring chỉ được scrape metrics cần thiết, dùng identity riêng.
- Cluster nodes cần các cổng nội bộ của RabbitMQ/Erlang; tuyệt đối không vô tình chặn traffic giữa các node khi cấu hình NetworkPolicy.

### 3.2. Giới hạn interface trong rabbitmq.conf

Với môi trường single-host hoặc khi quản trị qua SSH tunnel/bastion, có thể chỉ bind HTTP management vào loopback:

~~~ini
# rabbitmq.conf — phù hợp khi quản trị cục bộ / SSH tunnel
management.tcp.ip = 127.0.0.1
management.tcp.port = 15672
~~~

HTTP từ máy khác không truy cập trực tiếp được vào listener loopback. Khi cần quản trị từ mạng riêng qua TLS, cấu hình listener HTTPS với chứng chỉ:

~~~ini
# rabbitmq.conf — ví dụ một listener HTTPS quản trị nội bộ
management.ssl.port = 15671
management.ssl.ip = 10.10.20.15
management.ssl.cacertfile = /etc/rabbitmq/tls/ca.pem
management.ssl.certfile = /etc/rabbitmq/tls/server.pem
management.ssl.keyfile = /etc/rabbitmq/tls/server-key.pem

# Nếu vẫn giữ HTTP, chỉ cho localhost và chặn ở firewall.
management.tcp.ip = 127.0.0.1
management.tcp.port = 15672
~~~

IP `10.10.20.15` và đường dẫn chứng chỉ chỉ là **ví dụ**; phải thay theo interface và cách mount secret của hệ thống. Cấu hình HTTPS **không mặc nhiên khiến HTTP listener biến mất**. Sau khi sửa, kiểm tra lại cả HTTP lẫn HTTPS bằng `rabbitmq-diagnostics -s listeners` và quét cổng từ đúng những mạng tin cậy/không tin cậy.

Nếu triển khai bằng reverse proxy, phải bảo vệ **toàn bộ** UI và HTTP API, bao gồm những đường như `/api/queues`, `/api/connections` và các method có khả năng thay đổi trạng thái. Chỉ áp dụng CORS hay ẩn nút giao diện web không phải ACL đủ mạnh.

### 3.3. Kubernetes NetworkPolicy: chỉ mở đường cần thiết

Một minh họa có chọn lọc cho namespace `messaging`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: rabbitmq-allow-required-ingress
  namespace: messaging
spec:
  podSelector:
    matchLabels:
      app: rabbitmq
  policyTypes:
    - Ingress
  ingress:
    # Ứng dụng được phép mở kết nối AMQPS.
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: applications
          podSelector:
            matchLabels:
              rabbitmq-access: client
      ports:
        - protocol: TCP
          port: 5671
    # Cổng HTTPS management chỉ dành cho admin gateway nội bộ.
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: platform-admin
      ports:
        - protocol: TCP
          port: 15671
    # Metrics chỉ phục vụ Prometheus trong namespace giám sát.
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
      ports:
        - protocol: TCP
          port: 15692
    # Các RabbitMQ pod giao tiếp nội bộ trong cùng namespace.
    - from:
        - podSelector:
            matchLabels:
              app: rabbitmq
      ports:
        - protocol: TCP
          port: 25672
        - protocol: TCP
          port: 4369
~~~

**Đây là cấu hình tham khảo, không phải manifest production áp dụng nguyên xi**. Các nhãn `app`, namespace và cổng phải khớp với RabbitMQ Operator, Service và cấu hình thực tế; deployment có thể cần thêm cổng node-to-node, plugin và operator. NetworkPolicy cần **CNI hỗ trợ thực thi**; nếu môi trường không enforce policy, manifest chỉ tồn tại trên Kubernetes mà không chặn traffic. Các NetworkPolicy chọn cùng pod có quy tắc **allow cộng dồn**, nên một policy khác mở mọi ingress sẽ làm mất hiệu quả cô lập.

Trước khi áp dụng:

1. Kiểm kê traffic **trong cluster**, health probe và đường điều khiển của RabbitMQ Operator.
2. Dùng staging với namespace/label trùng production; chạy test cho producer, consumer, admin, Prometheus và giao tiếp node-to-node.
3. Xác minh nguồn **không được cấp phép** không đến được `15671`, `15672` hoặc `15692`.
4. Chỉ áp dụng production khi có kế hoạch rollback, dashboard tình trạng cluster và kênh truy cập khẩn cấp.

## 4. Xác thực và phân quyền: quản trị không dùng tài khoản ứng dụng

### 4.1. Management tag khác với vhost permission

RabbitMQ kiểm soát truy cập bằng **xác thực user**, **permissions trên virtual host** và **management user tags**. Một user có tag truy cập UI vẫn phải có quyền phù hợp trên tài nguyên/virtual host để thực hiện các thao tác tương ứng. Ngược lại, user dùng AMQP để publish/consume thường **không cần** bất kỳ management tag nào.

| Nhóm danh tính | Quyền cần thiết | Không nên cấp |
|---|---|---|
| `orders-producer` | Kết nối vhost riêng, `write` tới exchange được phép và quyền `configure/read` nếu nghiệp vụ thật sự cần | Tag `administrator`, quyền purge/delete hoặc toàn bộ vhost |
| `orders-consumer` | `read` queue đích, và các quyền tối thiểu cho ứng dụng | Quản trị user, thay policy, cấp quyền cho tài khoản khác |
| `metrics-scraper` | Chỉ quyền đọc metric hoặc `monitoring` phù hợp | Quyền admin, publish hoặc mutate queue nếu không cần |
| `operator` | Quyền quản trị cụ thể qua gateway bảo mật | Dùng chung credential với ứng dụng và automation |
| `deployment-automation` | Quyền `configure` đúng phạm vi topology được triển khai | Tài khoản toàn quyền tồn tại vĩnh viễn nếu có thể tách quyền |

Các tag thường gặp gồm `management`, `monitoring`, `policymaker` và `administrator`; mức quyền UI/API khác nhau. Đừng gán `administrator` chỉ để một chương trình gọi `/api/overview`. Hãy kiểm tra **cả tag và configure/write/read permission** sau khi tạo tài khoản.

Ví dụ kiểm tra bằng CLI trong môi trường được phép:

~~~bash
# Chạy trên node/management host đã được cấp phép.
rabbitmqctl list_users
rabbitmqctl list_vhosts
rabbitmqctl list_permissions -p orders
rabbitmqctl list_user_permissions orders-producer
~~~

Ví dụ cấp quyền tối thiểu (regex chỉ mang tính minh họa, cần kiểm tra cụ thể topology):

~~~bash
# User đã được tạo bằng quy trình quản lý secret của tổ chức.
# Không trao management tag cho tài khoản này.
rabbitmqctl set_permissions -p orders orders-producer \
  '^$' '^orders\.events\.x$' '^$'
~~~

Lệnh `set_permissions` có thứ tự **configure, write, read**. Ở ví dụ trên, producer chỉ được `write` vào exchange `orders.events.x` và không có quyền configure/read theo regex. Với ứng dụng cần `RabbitAdmin` tự khai báo exchange/queue/binding, phải cấp quyền configure tương ứng hoặc **tách tài khoản triển khai topology** khỏi tài khoản chạy message thông thường.

**Thận trọng:** permissions RabbitMQ là các regex theo **tên tài nguyên**, không phải một hệ thống IAM hiểu ý định nghiệp vụ. Một regex `.*` cấp quyền quá rộng. Với topic exchange, có thể cần thêm **topic permissions** để kiểm soát routing key; không chỉ dựa vào regex exchange.

### 4.2. Không sử dụng guest hay mật khẩu mặc định

RabbitMQ mặc định giới hạn user `guest` chỉ đăng nhập từ loopback. **Không đặt `loopback_users = none` để mở user guest từ xa** như một cách “sửa lỗi kết nối” trong production. Hãy tạo tài khoản riêng với secret ngẫu nhiên đủ mạnh, giới hạn vhost, xoay vòng secret và thu hồi tài khoản cũ. Tài khoản admin nên dùng cơ chế xác thực tập trung/proxy và MFA khi hạ tầng hỗ trợ.

Với ứng dụng Spring Boot, credentials cần đến từ secret manager, Kubernetes Secret có kiểm soát, workload identity hoặc biến môi trường bảo mật; không commit mật khẩu thật trong `application.yml`, Java source, Dockerfile hoặc CI logs.

Ví dụ ứng dụng dùng AMQPS và vhost riêng:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal.example
    port: 5671
    virtual-host: orders
    ssl:
      enabled: true
  # username/password nạp từ secret manager hoặc biến môi trường phù hợp.
~~~

Cần kiểm tra cấu hình TLS/trust store và hostname verification của phiên bản Spring Boot/Spring AMQP đang dùng; `ssl.enabled=true` **không tự chứng minh** CA được tin cậy đúng và hostname đã được xác minh theo chính sách của tổ chức.

## 5. Prometheus metrics và Spring Boot Actuator là hai bề mặt riêng

### 5.1. Endpoint Prometheus của RabbitMQ

Plugin `rabbitmq_prometheus` có cổng HTTP riêng, thường là `15692`. Không phải mọi hệ thống cần Management UI để scrape metrics; trong triển khai headless có thể sử dụng plugin Prometheus mà không public Management UI.

~~~ini
# rabbitmq.conf — chỉ ví dụ khi collector truy cập qua mạng riêng
prometheus.tcp.port = 15692
prometheus.tcp.ip = 10.10.20.15

# Bật HTTP authentication nếu cần theo chính sách triển khai:
prometheus.authentication.enabled = true
~~~

**Authentication của Prometheus endpoint là tùy chọn**, vì vậy đừng mặc định endpoint đã yêu cầu password. Dù bật auth, vẫn dùng firewall/NetworkPolicy để chỉ cho phép scraper tin cậy. TLS hoặc sidecar proxy phải được cấu hình nếu metrics đi qua mạng không tin cậy. Một đường metrics có thể tiết lộ tên queue, trạng thái cluster, tải và số liệu phục vụ suy luận nghiệp vụ.

### 5.2. Actuator thuộc Spring application, không phải RabbitMQ Management

Spring Boot Actuator thường có đường `/actuator/*` trên cổng HTTP của **ứng dụng**, không nằm trong RabbitMQ `15672`. Một service Spring có thể khóa được RabbitMQ Management nhưng vẫn vô tình public `/actuator/env` hoặc `/actuator/heapdump`.

Chỉ expose endpoint thực sự cần:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
  endpoint:
    health:
      show-details: never
~~~

Nếu không triển khai `micrometer-registry-prometheus` hoặc endpoint `prometheus` không có sẵn, bỏ nó khỏi danh sách. Với ứng dụng public, **không chỉ dựa vào danh sách include**: dùng Spring Security, network policy hoặc management port riêng khi có hỗ trợ. Health detail có thể cần giới hạn hiển thị cho probe; endpoint expose ra public không nên in địa chỉ nội bộ, tên queue, cấu hình DB hoặc thông tin môi trường nhạy cảm.

**Lưu ý quan trọng của Spring Boot:** nếu ứng dụng tự định nghĩa một `SecurityFilterChain`, auto-configuration bảo vệ Actuator có thể nhường quyền cho cấu hình bảo mật của bạn. Khi đó phải tự xây rule bảo vệ endpoints; không thể mặc định “có Spring Security dependency thì mọi endpoint nhạy cảm đã an toàn”.

## 6. Cập nhật bản vá: xác định đúng các lớp phụ thuộc

Lỗ hổng có thể nằm ở **broker**, **runtime Erlang**, **plugin**, **thư viện Java client**, **Spring Framework/Spring AMQP** hoặc **base image/JDK**. Vì thế nâng `spring-rabbit` mà không thay broker, hoặc nâng RabbitMQ mà giữ Java client lỗi thời, đều có thể để sót lỗ hổng.

| Thành phần cần kiểm kê | Ví dụ | Nguồn cập nhật |
|---|---|---|
| RabbitMQ Server | Binary hoặc OCI image `rabbitmq` | RabbitMQ release notes, security advisories và nhánh còn hỗ trợ |
| Erlang/OTP | Runtime mà RabbitMQ yêu cầu | Ma trận hỗ trợ RabbitMQ ↔ Erlang và bản vá Erlang |
| RabbitMQ plugins | `rabbitmq_management`, `rabbitmq_prometheus`, plugin ngoài | Phiên bản bundle theo server hoặc plugin vendor |
| Spring AMQP | `spring-rabbit`, `spring-amqp` | Spring AMQP release notes và BOM |
| AMQP 0-9-1 Java Client | `com.rabbitmq:amqp-client` | RabbitMQ Java Client release notes/advisories |
| AMQP 1.0 / Streams khi dùng | `spring-rabbitmq-client`, `spring-amqp-client`, `spring-rabbit-stream` và native client | Release notes và dependency graph tương ứng |
| Spring Boot/Framework | `spring-boot-starter-amqp`, Spring Framework, Spring Security | Spring BOM, Spring Security advisories |
| Serialization & HTTP | Jackson, các HTTP/Netty libraries nếu kéo theo thực tế | SCA, advisory từ các dự án và các bản vá |
| Runtime & nền tảng | JDK, base image OS, OpenSSL, ingress/proxy | Vendor advisories và image scanning |

**Bản vá thư viện cần dựa vào dependency được resolve**, không chỉ dependency khai báo trực tiếp. Một CVE có thể thuộc một JAR transitive khác với version trong `pom.xml`; việc thêm một version override thiếu kiểm soát có thể phá tương thích với Spring Boot BOM.

Khi đọc advisory, cần phân biệt **ảnh hưởng version nào**, **có khai thác được từ cấu hình hiện tại không**, **bản vá khả dụng**, **yêu cầu restart** và **đường nâng cấp hỗ trợ**. Không kết luận một hệ thống an toàn chỉ vì quét dependency không báo CVE: misconfiguration ở Management API có thể là rủi ro ngay cả khi toàn bộ package đều mới.

## 7. Quy trình quản lý bản vá cho Spring AMQP và Java Client

### 7.1. Kiểm kê những dependency đang chạy thật

Ví dụ Maven:

~~~bash
# Tìm dependency do Spring AMQP và RabbitMQ Java Client kéo vào.
mvn dependency:tree \
  -Dincludes=org.springframework.amqp:*,com.rabbitmq:amqp-client

# Kiểm tra resolved dependency và plugin/JDK của bản build.
mvn dependency:tree
~~~

Ví dụ Gradle:

~~~bash
# Xem version thực tế của amqp-client trên runtime classpath.
./gradlew dependencyInsight \
  --dependency amqp-client \
  --configuration runtimeClasspath

./gradlew dependencies --configuration runtimeClasspath
~~~

Các dòng trên là **lệnh tham khảo dành cho người học**, không phải script được thực thi trong bước tạo bài. Trong pipeline thật nên xuất thêm **SBOM** (ví dụ CycloneDX/SPDX) và lưu cùng artifact, vì việc quét một file source không chứng minh dependency thực tế trong image đã được vá.

Những dữ liệu cần lưu:

- Phiên bản `spring-boot`, `spring-rabbit`, `spring-amqp` và `amqp-client` được resolve.
- Phiên bản Java, base image và artifact/container digest.
- Các thư viện runtime như Jackson, Reactor, Netty, `spring-rabbit-stream` hoặc ProtonJ2 nếu ứng dụng dùng.
- Plugin và cấu hình broker liên quan đến tính năng messaging thật sự được bật.
- Mã advisory, mức độ nghiêm trọng, phạm vi ảnh hưởng và quyết định xử lý.

### 7.2. Ưu tiên BOM và bản vá được hỗ trợ

Với ứng dụng Spring Boot, thường nên quản lý phiên bản thông qua **Spring Boot dependency management/BOM** của một release được hỗ trợ. Khi cần cập nhật một dependency cụ thể, kiểm tra release notes và compatibility thay vì ghi cứng phiên bản lớn hơn vào mọi module.

Ví dụ nguyên tắc trong Maven:

~~~xml
<!-- Spring Boot BOM được dự án import/quản lý.
     Không hardcode spring-rabbit và amqp-client theo ý muốn
     nếu chưa đánh giá tương thích của Spring Boot/Spring AMQP. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Quy trình ra quyết định:

1. Xác định advisory có ảnh hưởng bản đang dùng hay không.
2. Tìm **bản vá trong nhánh còn được hỗ trợ** trước khi nâng major.
3. Kiểm tra Java/JDK và Spring Framework được release mục tiêu yêu cầu.
4. Cập nhật BOM/lockfile, chạy lại SCA trên **resolved dependency**.
5. Kiểm thử publish confirms/returns, listener ACK/NACK, retry/DLX, JSON converter và recovery.
6. Chạy canary trước khi rollout rộng; theo dõi lỗi và có tiêu chí rollback rõ ràng.

**Tránh dùng mỗi “build thành công” làm điều kiện kết thúc vá lỗi.** Một thay đổi version có thể biên dịch bình thường nhưng ảnh hưởng converter, exception classification, kết nối TLS, retry semantics hoặc cấu hình listener ở runtime.

### 7.3. Ví dụ test xác nhận ứng dụng vẫn đáng tin cậy sau vá

Một test tích hợp nên chứng minh:

- `RabbitTemplate` publish thành công nhận publisher confirm ACK khi exchange/binding hợp lệ.
- Publish với routing key không có đích vẫn được phát hiện qua **mandatory returns**, thay vì coi confirm ACK là message đã đến queue.
- `@RabbitListener` chỉ ACK sau khi transaction nghiệp vụ hoàn tất; lỗi khiến message đi theo retry/DLX đã thiết kế.
- Khi cắt connection giữa publish và confirm, ứng dụng **không xóa bản ghi outbox** chỉ vì timeout; retry cùng `eventId` có thể tạo duplicate và consumer phải phát hiện được.
- Khi consumer chết sau DB commit nhưng trước ACK, broker redeliver; bảng inbox/idempotency chặn tác dụng nghiệp vụ lặp.
- Sau nâng version, kết nối TLS vẫn kiểm tra trust chain và không dùng mode bỏ qua certificate validation.

Nếu sử dụng listener async `CompletableFuture`/`Mono` hoặc batch listener, thêm test riêng cho **completion muộn, exception trước Future và retry của batch**. Các đường này có thể đổi hành vi khi dependency/framework được nâng mà unit test thuần túy không phát hiện.

## 8. Bản vá RabbitMQ Server: không bỏ qua Erlang và chiến lược nâng cấp

RabbitMQ chạy trên **Erlang/OTP**. Các release RabbitMQ có ma trận Erlang hỗ trợ riêng; một version Erlang quá cũ hoặc quá mới so với release mục tiêu đều có thể gây lỗi khởi động, TLS, clustering hoặc hành vi khác. Khi cập nhật broker cần xem **RabbitMQ + Erlang + plugin + cấu hình + dữ liệu cluster** như một thay đổi có tính hệ thống.

### 8.1. Lập kế hoạch phiên bản an toàn

Trước khi chọn bản vá:

1. Xác định **RabbitMQ release series hiện tại**, phiên bản node và phiên bản Erlang/OTP bằng công cụ quản trị.
2. Đọc **RabbitMQ release notes**, security advisories và bảng **Erlang Version Requirements** của phiên bản đích.
3. Với nâng cấp khác release series, kiểm tra bảng **version upgradability** và feature flags. Không giả định có thể nhảy qua mọi nhánh bằng rolling upgrade.
4. Kiểm tra phiên bản của third-party plugins và các tooling/operator đang sử dụng.
5. Đánh giá queue types: classic, quorum, stream; kiểm tra replication, leader/quorum, queue sync và disk/memory alarms.
6. Lên kế hoạch backup, khôi phục, downtime window và rollback theo đúng khuyến nghị của đường nâng cấp.

Ví dụ các lệnh **kiểm tra, không thay đổi trạng thái**:

~~~bash
rabbitmq-diagnostics -s listeners
rabbitmqctl status
rabbitmqctl cluster_status
rabbitmqctl list_feature_flags
rabbitmq-plugins list -e
~~~

Các lệnh cần quyền quản trị trên node phù hợp. **Không đăng toàn bộ output** của `rabbitmqctl status` hoặc debug logs lên kênh công khai: chúng có thể chứa đường dẫn, tên node, metadata nội bộ hoặc thông tin vận hành.

### 8.2. Rolling upgrade theo đúng đường hỗ trợ

Trong cluster đủ điều kiện rolling upgrade, thao tác điển hình là:

~~~mermaid
flowchart TB
    PLAN["Chọn bản vá và xác minh compatibility"] --> BACKUP["Kiểm thử backup/restore và kiểm tra cluster"]
    BACKUP --> DRAIN["Dừng luồng vào node dự kiến nâng cấp"]
    DRAIN --> NODE["Nâng cấp một node + Erlang/plugin nếu cần"]
    NODE --> JOIN["Node khởi động, tái gia nhập, sync dữ liệu"]
    JOIN --> VERIFY{"Cluster healthy, không alarm?"}
    VERIFY -->|Có| MORE{"Còn node cần nâng?"}
    MORE -->|Có| DRAIN
    MORE -->|Không| FLAGS["Hoàn tất feature flags và giám sát"]
    VERIFY -->|Không| STOP["Dừng rollout, xử lý sự cố/rollback theo plan"]
~~~

Các bước vận hành cụ thể phải theo **tài liệu rolling upgrade cho đúng phiên bản**, không tự động giả định restart từng node là an toàn cho mọi topology. Một cluster nhỏ, thiếu replica hoặc đang mất quorum không thể được nâng “không downtime” chỉ nhờ restart tuần tự.

Với nâng minor/major, có thể tồn tại **thay đổi định dạng dữ liệu hoặc feature flags** khiến rollback bằng cách chạy lại binary cũ không an toàn. Backup/snapshot phải được thử restore; có trường hợp cần dùng chiến lược **blue/green hoặc migration** thay vì downgrade tại chỗ.

### 8.3. Trong lúc restart broker, message có thể được giao lại

Khi nâng node, client Spring AMQP có thể bị mất connection/channel. Với publisher confirms, lần gửi chưa nhận kết quả là **outcome không xác định**; với consumer, delivery chưa được broker ghi nhận ACK có thể **redeliver** sau recovery.

~~~text
Spring producer --publish e42--> RabbitMQ node
          X kết nối đóng trước confirm
          |
          +--> retry e42 từ outbox (cùng eventId)
                       |
                 Consumer có thể thấy e42 hai lần

Consumer xử lý e42 --DB COMMIT--> X mất kết nối trước ACK
          |
          +--> broker redeliver e42
                       |
                 Inbox unique eventId chặn xử lý lặp
~~~

Vì thế, bản vá broker an toàn phải đi cùng **publisher confirms + returns, durable queue/topology, outbox khi cần, idempotent consumer và retry hữu hạn**. Không coi một đợt reconnect thành công là bằng chứng không có message bị mất/trùng.

## 9. Kế hoạch vá lỗi xuyên lớp: từ phát hiện đến triển khai

Một quy trình vận hành có thể chia thành các bước sau:

| Bước | Đầu ra cần có | Điều kiện chấp nhận |
|---|---|---|
| 1. Phát hiện | Danh sách CVE/advisory, scan SBOM, image, broker và plugin | Chỉ rõ thành phần, version bị ảnh hưởng |
| 2. Đánh giá | Mức độ ảnh hưởng, reachable attack surface, phân loại dữ liệu | Có mức ưu tiên và người chịu trách nhiệm |
| 3. Giảm thiểu ngay | Khóa management ingress, thu hồi credential, giới hạn user, tắt tính năng không cần | Giảm rủi ro trước khi có thể restart/patch |
| 4. Chọn bản vá | Version đích, release notes, compatibility matrix, dependency BOM | Không phá vỡ yêu cầu Java/Erlang/cluster |
| 5. Kiểm thử | Test tích hợp, fault injection, permission/TLS và dữ liệu | Không mất tính đúng đắn ACK/retry/idempotency |
| 6. Triển khai | Canary, rolling/blue-green theo điều kiện cho phép | Cảnh báo/rollback triggers rõ ràng |
| 7. Xác minh | Version mới, listener ports, metrics, logs, CVE scan | Không còn đường public trái phép, luồng message khỏe |
| 8. Đóng vòng | Change record, SBOM mới, runbook, cập nhật inventory | Có bằng chứng kỹ thuật và người xác nhận |

### Lịch vá và ưu tiên

Không có một chu kỳ vá cố định phù hợp mọi tổ chức. Đối với lỗ hổng **đã bị khai thác tích cực**, ảnh hưởng thành phần Internet-facing hoặc có mức tác động nghiêm trọng, cần ưu tiên xử lý theo quy trình khẩn cấp của tổ chức. Những cập nhật bảo mật ít nghiêm trọng hơn vẫn phải có lịch đánh giá định kỳ.

Quan trọng là **tính đến thời gian chờ của doanh nghiệp**: một bản vá yêu cầu restart RabbitMQ cluster có thể cần maintenance window, nhưng không vì vậy mà bỏ qua biện pháp giảm thiểu tạm thời (hạn chế management exposure, đổi credential hoặc rule firewall).

### Rollback không chỉ là đổi lại tag image

Mọi kế hoạch rollback cần trả lời:

- Binary, Erlang và plugin cũ có đọc được dữ liệu/config sau upgrade hay không?
- Các feature flags và schema đã thay đổi chưa?
- Dữ liệu queue, quorum replicas và stream retention có thể bị ảnh hưởng khi di chuyển node không?
- Producer/consumer còn đang xử lý hoặc đang retry khi quay lại phiên bản cũ?
- Cơ chế khôi phục definitions, secrets, certificates và topology đã thử trên môi trường staging chưa?

Nếu không có đường downgrade hỗ trợ, chọn **roll-forward** hoặc phục hồi từ backup theo kế hoạch đã kiểm chứng thay vì rollback bừa trên cluster production.

## 10. Bộ kiểm thử bảo mật và độ tin cậy sau triển khai

Không nên chỉ kiểm tra “Management UI trả 200 cho admin”. Phải thử cả các nguồn **không được phép**, và xác minh đường message vẫn hoạt động khi một node broker restart.

| Kịch bản | Cách kiểm tra an toàn | Kết quả mong đợi |
|---|---|---|
| Nguồn Internet không được phép tới `15672` | Thử kết nối từ máy thử ngoài allowlist | Không truy cập được Management HTTP |
| Nguồn không được phép tới `15671` | Thử kết nối tới management HTTPS | Bị chặn ở lớp network/proxy |
| Admin qua gateway hợp lệ | Truy cập HTTPS bằng tài khoản được cấp quyền | Thành công với TLS và quy trình xác thực dự kiến |
| User ứng dụng mở Management UI | Đăng nhập bằng tài khoản producer/consumer | Không có management tag/quyền UI |
| User monitoring gọi API thay đổi queue | Chạy kiểm thử phân quyền trong môi trường thử nghiệm | Bị từ chối; không sửa topology |
| Prometheus scrape từ monitoring namespace | Gọi `/metrics` bằng identity monitor | Thành công, đúng xác thực/TLS nếu có cấu hình |
| Pod ứng dụng truy cập `15692` trái phép | Kiểm tra qua NetworkPolicy staging | Bị chặn; AMQPS ứng dụng vẫn hoạt động |
| Spring Actuator nhạy cảm | Kiểm tra `/actuator/env`, `/actuator/beans` từ mạng public | Không expose hoặc bị chặn/bảo vệ |
| TLS certificate sai hostname | Thử với trust config chuẩn, không bypass verification | Kết nối bị từ chối; không fallback plaintext |
| Publisher nhận ACK hợp lệ | Publish vào exchange/routing key đúng | Correlated confirm thành công; không có return |
| Publish không route được | Gửi vào routing key thử không có binding với `mandatory` | Nhận return; không đánh dấu publish thành công |
| Cắt connection trước confirm | Fault injection ở staging | Outbox giữ trạng thái cần gửi; retry cùng `eventId` |
| Consumer đã DB commit rồi mất ACK | Fault injection ở staging | Có thể redeliver; chỉ một tác dụng nghiệp vụ nhờ inbox |
| Nâng một node broker | Canary/rolling trong cluster thử | Node tái gia nhập, không mất quorum và không có alarm |
| Nâng Java client/Spring AMQP | Test tích hợp listener và converter | ACK/NACK, retry, DLQ, TLS và recovery không regression |
| Scan lại artifact mới | SCA trên resolved dependencies và image digest | Advisory mục tiêu được xử lý, không phát sinh lỗi mới không chấp nhận |

### 10.1. Thủ tục kiểm tra thực tế

Trên host RabbitMQ được phép:

~~~bash
# Danh sách port và interface thật sự được mở.
rabbitmq-diagnostics -s listeners

# Trạng thái node và cluster.
rabbitmqctl status
rabbitmqctl cluster_status

# Kiểm tra tài khoản và quyền.
rabbitmqctl list_users
rabbitmqctl list_permissions -p orders
~~~

Từ admin workstation được cấp quyền, thử URL HTTPS nội bộ bằng browser hoặc HTTP client. Từ một máy **ngoài allowlist** nhưng do tổ chức quản lý, thử kết nối có kiểm soát đến những cổng bị cấm; kết quả mong đợi là **không có đường truy cập**. Không quét tùy ý vào địa chỉ ngoài phạm vi được phép thử.

Đối với Kubernetes, cần kiểm tra đồng thời:

- Service có dùng `ClusterIP` hay vô tình tạo public `LoadBalancer`/`NodePort`?
- Ingress controller có route hostname công khai tới Management UI/API không?
- Các NetworkPolicy chọn pod có tạo một đường allow rộng ngoài ý muốn?
- Pod labels, namespace labels, ports có trùng policy và CNI có thực thi hay không?
- Cluster traffic giữa các RabbitMQ pods, RabbitMQ Operator và readiness probes có còn hoạt động?

### 10.2. Chỉ số và cảnh báo sau khi vá

Theo dõi những tín hiệu sau để biết bản vá có gây tác dụng phụ:

| Tín hiệu | Vì sao quan trọng |
|---|---|
| Broker version / Erlang version / plugin inventory | Xác minh tất cả node dùng release dự kiến |
| Connection errors, TLS handshake failures, authentication failures | Phát hiện client không tương thích hoặc truy cập trái phép |
| Số lần reconnect/channel close | Nhìn thấy gián đoạn do rollout và lỗi recovery |
| Queue `ready` và `unacked`, consumer count | Phát hiện backlog sau restart |
| Publisher confirms pending/timeout/NACK và returned messages | Phát hiện publish chưa rõ kết quả hoặc route sai |
| Redelivery, retry, DLQ depth | Phát hiện duplicate và poison message sau rollout |
| Disk/memory alarms, quorum status, stream replica health | Phát hiện cluster mất ổn định hoặc thiếu replica |
| Management API login/HTTP error và thay đổi topology | Phát hiện hoạt động vận hành bất thường |
| SCA findings và thời gian chưa vá | Đánh giá nợ bảo mật và SLA xử lý advisory |

Không gửi user/password, authorization header, cookie hoặc payload chứa thông tin cá nhân vào metrics/log aggregation. Log phải có retention và phân quyền riêng.

## 11. Kịch bản phản ứng khi Management API bị lộ

Giả sử kiểm tra an ninh phát hiện `https://rabbit-admin.example.com` đang public ngoài kế hoạch. Cách phản ứng phù hợp là **giảm khả năng truy cập ngay**, giữ bằng chứng và xác minh tác động nghiệp vụ:

1. **Xác nhận phạm vi:** endpoint nào public, do Service/Ingress/LB/firewall nào cấp quyền, có HTTP API hay metrics cùng bị lộ không.
2. **Chặn đường công khai:** thu hẹp network rules, tắt routing public hoặc đặt sau gateway được phép. Đảm bảo kênh admin khẩn cấp vẫn hoạt động.
3. **Thu hồi và xoay vòng credentials bị ảnh hưởng:** tách tài khoản app/admin, kiểm tra quyền và tokens; không vô hiệu hóa bừa service accounts đang xử lý message nếu chưa có kế hoạch.
4. **Bảo toàn log/bằng chứng:** thu thập access/auth logs và lịch sử thay đổi topology khi có, lưu ở nơi phân quyền.
5. **Kiểm tra hậu quả:** so sánh definitions, exchange/queue/binding, vhost permissions, policies, queue depth và dead-letter/parking messages với baseline.
6. **Vá phần mềm và config:** xử lý advisory tương ứng, triển khai thay đổi theo canary/rolling plan.
7. **Giám sát khôi phục:** kiểm tra publisher confirms, consumer ACK/redelivery, backlog, retry và outbox; phát hiện sai lệch dữ liệu bằng event ID.
8. **Đóng sự cố:** ghi postmortem, cập nhật quy trình kiểm tra ingress và cảnh báo khi một management Service bị đưa ra public.

Đừng tự động purge queue hoặc delete vhost như một bước “dọn dẹp” sau sự cố. Các thao tác này có thể xóa dữ liệu nghiệp vụ và làm mất đường phục hồi. Cần đánh giá nguyên nhân, bằng chứng và kế hoạch phục hồi trước khi thay đổi trạng thái broker.

## 12. Những hiểu lầm thường gặp

| Hiểu lầm | Điều đúng |
|---|---|
| “Đã bật mật khẩu nên Management UI public vẫn an toàn” | Xác thực chỉ là một lớp; cần cô lập mạng, TLS, quyền tối thiểu và patch |
| “UI bị chặn thì HTTP API cũng bị chặn” | Phải xác minh toàn bộ đường `/api/*` cùng listener |
| “Tắt `15672` là hết bề mặt giám sát” | Prometheus, HTTPS management, Actuator và node ports là bề mặt riêng |
| “Dùng HTTPS là không cần phân quyền” | TLS bảo vệ truyền tải, không thay thế identity và authorization |
| “User có quyền publish cần tag administrator” | Producer/consumer thường chỉ cần vhost permissions phù hợp |
| “Management tag đồng nghĩa quyền thao tác mọi queue” | User tags và configure/write/read permissions là những lớp khác nhau |
| “`guest` bị cấm từ xa thì chỉ cần bật `loopback_users = none`” | Mở default guest từ xa với thông tin đăng nhập phổ biến là rủi ro nghiêm trọng |
| “NetworkPolicy đã tồn tại nên chắc chắn chặn traffic” | CNI phải thực thi policy; mọi policy chọn pod được cộng dồn |
| “Chỉ broker mới cần patch” | Erlang, plugin, Spring, Java client, runtime và image đều có lỗ hổng |
| “Đổi version trong POM là đã vá thư viện” | Cần kiểm tra resolved dependency, BOM, artifact cuối và CVE scan |
| “Rolling restart không tạo duplicate” | Publish chưa confirm và delivery chưa ACK có thể lặp khi connection đóng |
| “Cập nhật image là có thể rollback image cũ bất kỳ lúc nào” | Upgrade path, feature flags và định dạng dữ liệu có thể khiến downgrade không an toàn |
| “Chỉ cần unit test qua mock RabbitTemplate” | Những lỗi TLS, confirm, redelivery, cluster và routing cần integration test |

## 13. Checklist bảo mật và cập nhật bản vá trước production

1. **Bề mặt mạng:** liệt kê tất cả listener thực tế; Management UI/API và metrics không public ngoài kế hoạch.
2. **Truy cập admin:** chỉ qua VPN/bastion/identity proxy hoặc private network có kiểm soát; bật TLS, kiểm certificate và audit.
3. **Tài khoản:** tách user ứng dụng, monitoring, automation và administrator; quản lý secrets và rotate.
4. **Quyền:** cấp đúng vhost, configure/write/read regex; không dùng `.*` rộng nếu không thật sự cần.
5. **Metrics/Actuator:** giới hạn nguồn scrape và Actuator endpoint; không lộ env, dump, config hay thông tin nhạy cảm.
6. **Kiểm kê phiên bản:** RabbitMQ, Erlang, plugins, Spring AMQP, Java client, JDK và base image có SBOM.
7. **Advisory:** đối chiếu phiên bản bị ảnh hưởng, bản vá hỗ trợ và độ khẩn cấp theo phạm vi reachable.
8. **Tương thích:** kiểm tra RabbitMQ↔Erlang, Spring Boot BOM và đường upgrade/feature flags.
9. **Thử nghiệm:** xác minh confirms/returns, retry/DLX, DB commit/ACK, duplicate, SSL và auth ở môi trường staging.
10. **Triển khai:** có canary/rolling plan, backup/restore đã kiểm chứng và tiêu chí dừng rollout.
11. **Sau triển khai:** xác minh tất cả node và JAR resolved đúng version, không còn management exposure trái phép.
12. **Quan sát:** đặt cảnh báo cho authentication failures, management access bất thường, confirm timeout, redelivery, DLQ và cluster alarms.

### Tài liệu chính thức để kiểm tra theo phiên bản

- [RabbitMQ — Management Plugin](https://www.rabbitmq.com/docs/management): UI/HTTP API, listener HTTP/HTTPS, tag và cấu hình.
- [RabbitMQ — Networking](https://www.rabbitmq.com/docs/networking): cổng AMQP, management, metrics và cluster.
- [RabbitMQ — Access Control](https://www.rabbitmq.com/docs/access-control): xác thực, vhost permissions và giới hạn user `guest`.
- [RabbitMQ — Prometheus Monitoring](https://www.rabbitmq.com/docs/prometheus): cổng metrics, authentication, TLS và tích hợp Prometheus.
- [RabbitMQ — Erlang Version Requirements](https://www.rabbitmq.com/docs/which-erlang): ma trận tương thích RabbitMQ/Erlang.
- [RabbitMQ — Upgrading](https://www.rabbitmq.com/docs/upgrade): chiến lược nâng cấp, đường hỗ trợ và lưu ý cluster.
- [RabbitMQ — Rolling Upgrade](https://www.rabbitmq.com/docs/rolling-upgrade): kiểm tra feature flags, từng node và phục hồi sau upgrade.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): các endpoint, exposure và bảo vệ bằng Spring Security.
- [Spring AMQP — Reference](https://docs.spring.io/spring-amqp/reference/): các API gửi/nhận, publisher confirms, listener và tính năng theo phiên bản.

**Kết luận:** Bảo vệ Spring AMQP không chỉ là đặt password cho RabbitMQ. Hãy **cô lập Management UI/HTTP API và metrics khỏi các mạng không cần truy cập**, giới hạn quyền theo tài khoản và vhost, kiểm soát TLS và Actuator của ứng dụng. Song song, duy trì chu trình **kiểm kê dependency – theo dõi advisory – cập nhật bản vá – kiểm thử kết nối/ACK/retry – rollout an toàn – xác minh lại** cho broker, Erlang và toàn bộ Java stack. Cách kết hợp phòng thủ nhiều lớp với quy trình vá có kiểm soát giúp hệ thống xử lý message vừa an toàn trước truy cập trái phép, vừa phục hồi đáng tin cậy khi nâng cấp hoặc gặp sự cố.

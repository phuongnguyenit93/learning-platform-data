# Xác thực RabbitMQ, virtual host và TLS

Một ứng dụng Spring Cloud Stream dùng RabbitMQ cần vượt qua ba lớp bảo vệ trước khi trao đổi message an toàn: xác thực danh tính kết nối, quyền truy cập trong virtual host và bảo vệ kênh truyền bằng TLS. Ba lớp này giải quyết các câu hỏi khác nhau:

- Authentication: client là ai? RabbitMQ xác minh username/password hoặc cơ chế xác thực khác.
- Virtual host và authorization: client được phép truy cập namespace nào, được khai báo hoặc sử dụng queue/exchange nào?
- TLS: dữ liệu đi qua mạng có được mã hóa và client có xác minh đúng máy chủ hay không? Với mutual TLS, broker còn có thể xác minh chứng thư client.

Kết nối TCP thành công chưa có nghĩa xác thực thành công. Xác thực thành công cũng chưa có nghĩa user được phép vào virtual host. Vào được virtual host vẫn chưa bảo đảm có quyền publish hoặc consume. Cuối cùng, AMQP connection có thể hoạt động nhưng chưa được mã hóa nếu TLS không được bật.

## 1. Ba lớp bảo vệ trong một kết nối AMQP

~~~mermaid
flowchart TD
    A["Spring Cloud Stream Rabbit Binder"] --> B["TLS handshake"]
    B --> C["Xác minh chứng thư máy chủ<br/>và tùy chọn chứng thư client"]
    C --> D["AMQP authentication<br/>username / password hoặc SASL"]
    D --> E["Chọn virtual host"]
    E --> F["Kiểm tra permissions<br/>configure / write / read"]
    F --> G["Declare / publish / consume"]
~~~

Trình tự trên là mô hình khái niệm. TLS handshake diễn ra trước khi thông điệp AMQP được trao đổi. Sau khi kênh được thiết lập, client xác thực với broker, chọn virtual host khi mở AMQP connection, rồi RabbitMQ kiểm tra quyền trên từng tài nguyên.

| Lớp | Cơ chế | Ví dụ lỗi |
|---|---|---|
| TLS | Chứng thư X.509, trust store, hostname verification | PKIX path building failed, certificate expired |
| Authentication | Username/password hoặc cơ chế SASL được broker hỗ trợ | ACCESS_REFUSED - Login was refused |
| Virtual host | Namespace được chọn khi mở connection | Vhost không tồn tại hoặc user không được phép truy cập |
| Authorization | Permission theo resource và operation | Access to exchange/queue refused |

## 2. Authentication: RabbitMQ xác minh client

RabbitMQ xác thực kết nối AMQP bằng authentication mechanism được broker cho phép. Cấu hình phổ biến nhất là username/password thông qua internal authentication backend. RabbitMQ cũng có thể dùng LDAP, HTTP hoặc plugin/backend khác; môi trường yêu cầu chứng thư client có thể dùng cơ chế X.509/SASL EXTERNAL khi broker được cấu hình tương ứng.

Ví dụ tạo tài khoản ứng dụng:

~~~bash
rabbitmqctl add_user orders-service 'REPLACE_WITH_SECRET'
rabbitmqctl change_password orders-service 'REPLACE_WITH_SECRET'
~~~

Trong môi trường thật, mật khẩu cần được cấp từ secret manager hoặc quy trình quản trị danh tính. Không đưa mật khẩu thật vào shell history, file YAML được commit hoặc log triển khai.

User ứng dụng nên là tài khoản riêng cho workload. Không dùng tài khoản quản trị để chạy consumer/producer. Tách tài khoản theo dịch vụ hoặc theo ranh giới tin cậy giúp thu hồi credential, điều tra và giới hạn quyền độc lập.

### 2.1. Tài khoản guest

RabbitMQ tạo sẵn user guest trong một số gói cài đặt mặc định. User này thường bị giới hạn chỉ kết nối từ loopback interface. Một ứng dụng chạy trên máy khác sẽ không thể dùng guest để kết nối từ xa theo mặc định.

Không mở rộng quyền truy cập từ xa cho guest để giải quyết lỗi kết nối. Hãy tạo user riêng, đặt mật khẩu mạnh và cấp quyền tối thiểu trên đúng virtual host.

### 2.2. Authentication không cấp quyền nghiệp vụ

Username/password hợp lệ chỉ xác minh danh tính. Sau khi xác thực, RabbitMQ vẫn kiểm tra:

- User có quyền truy cập virtual host được yêu cầu không?
- User có quyền khai báo exchange/queue cần thiết không?
- User có quyền publish vào exchange không?
- User có quyền consume từ queue không?

Vì vậy, lỗi ACCESS_REFUSED có thể xuất hiện sau khi login thành công. Hãy phân biệt lỗi authentication với lỗi vhost và permission bằng broker log và thông báo AMQP cụ thể.

## 3. Virtual host là namespace của RabbitMQ

Virtual host (vhost) là một namespace logic chứa exchange, queue, binding, policy và một số tài nguyên liên quan. Tên queue hoặc exchange trong hai vhost khác nhau có thể trùng nhau mà không xung đột.

Ví dụ:

~~~text
RabbitMQ cluster
  |
  +-- vhost: /orders
  |     +-- exchange: orders.events
  |     +-- queue: order-service
  |
  +-- vhost: /billing
        +-- exchange: orders.events
        +-- queue: order-service
~~~

Hai queue cùng tên order-service ở hai vhost là hai tài nguyên độc lập. Một client kết nối vào /orders không thể tự động nhìn thấy queue ở /billing.

Vhost hữu ích để:

- Tách môi trường hoặc miền nghiệp vụ.
- Giới hạn quyền truy cập của từng dịch vụ.
- Áp dụng policy, quota và cấu hình topology theo namespace.
- Tránh trùng tên tài nguyên giữa các workload.

Vhost không phải broker hoặc cluster độc lập. Các vhost trong cùng cluster vẫn chia sẻ hạ tầng broker, node, disk và năng lực xử lý; không dùng vhost thay cho ranh giới hạ tầng khi cần cách ly tài nguyên mạnh.

### 3.1. Tạo vhost và cấp quyền

Ví dụ tạo namespace cho dịch vụ đơn hàng:

~~~bash
rabbitmqctl add_vhost /orders
rabbitmqctl set_permissions -p /orders orders-service '.*' '.*' '.*'
~~~

Ví dụ giả định user orders-service đã được tạo ở bước trước. Lệnh set_permissions cấp quyền rộng trên mọi resource trong vhost để minh họa cú pháp. Không nên dùng .* cho cả ba permission trong production nếu ứng dụng chỉ cần một số queue/exchange cụ thể. Phần tiếp theo thu hẹp quyền bằng regular expression.

Tên vhost mặc định thường là /. Trong URI AMQP, dấu / là ký tự phân cách path nên vhost / được percent-encode thành %2F nếu cấu hình bằng URI. Khi dùng thuộc tính Spring Boot spring.rabbitmq.virtual-host, khai báo giá trị / trực tiếp.

### 3.2. Quyền truy cập vhost

Một user cần được cấp quyền trên vhost trước khi có thể sử dụng các tài nguyên trong đó. Có thể xem quyền bằng:

~~~bash
rabbitmqctl list_permissions -p /orders
rabbitmqctl list_user_permissions orders-service
~~~

Nếu user chưa có quyền trên vhost, broker từ chối mở AMQP connection tới vhost đó, dù username/password hợp lệ.

## 4. Ba loại permission: configure, write và read

RabbitMQ quản lý quyền theo ba regular expression gắn với từng user và vhost:

| Permission | Cho phép | Ví dụ thao tác |
|---|---|---|
| configure | Khai báo, thay đổi hoặc xóa resource | Declare/delete exchange hoặc queue |
| write | Ghi vào resource | Publish vào exchange; một số thao tác binding cần quyền trên resource liên quan |
| read | Đọc từ resource | Consume queue hoặc lấy message theo thao tác được phép |

RabbitMQ kiểm tra quyền trên resource bị tác động. Khi bind queue vào exchange, quyền cần thiết liên quan đến cả source exchange và destination queue; đừng suy luận rằng chỉ có quyền read trên queue là đủ cho mọi thao tác topology.

Ví dụ dịch vụ tiêu thụ queue do nền tảng đã tạo sẵn:

~~~bash
rabbitmqctl set_permissions -p /orders orders-consumer \
  '^$' '^$' '^orders\.submitted$'
~~~

Trong lệnh trên:

- configure là ^$: không khớp tên resource nào.
- write là ^$: không cho publish vào exchange.
- read là ^orders\.submitted$: chỉ cho đọc queue có tên chính xác orders.submitted.

Ví dụ dịch vụ chỉ publish vào exchange:

~~~bash
rabbitmqctl set_permissions -p /orders orders-publisher \
  '^$' '^orders\.events$' '^$'
~~~

Các biểu thức phải khớp đúng tên resource thực tế mà binder sử dụng. Nếu binder tự tạo queue có tên ghép từ destination và group, regex phải cho phép đúng tên đó.

### 4.1. Binder tự khai báo topology cần quyền gì?

Rabbit binder có thể tự khai báo exchange, queue và binding. Tùy topology, binder cần các quyền tương ứng để khai báo tài nguyên, publish và consume. Nếu user chỉ có read permission nhưng binder cố tạo queue, ứng dụng có thể kết nối thành công rồi thất bại khi khởi tạo binding.

Có hai cách triển khai:

1. Binder quản lý topology: cấp configure/write/read tối thiểu theo đúng resource mà binder phải tạo và sử dụng.
2. Nền tảng quản lý topology: quản trị viên tạo trước exchange, queue và binding; binder được cấu hình để không khai báo hoặc bind những thành phần đã được quản lý bên ngoài; user ứng dụng chỉ nhận quyền runtime cần thiết.

Không tắt khai báo topology một cách tùy tiện. Nếu binder không tạo queue hoặc binding, chúng phải tồn tại và trỏ đúng exchange/routing key trước khi consumer khởi động.

## 5. Cấu hình Spring Cloud Stream Rabbit binder

Rabbit binder sử dụng Spring AMQP và Spring Boot Rabbit connection properties. Với ứng dụng chỉ có một Rabbit binder, các thuộc tính kết nối thường đặt dưới spring.rabbitmq.*.

Ví dụ:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal
    port: 5672
    username: orders-service
    password: RABBITMQ_PASSWORD_FROM_SECRET
    virtual-host: /orders

  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-service
~~~

Trong ví dụ, binder kết nối tới rabbitmq.internal:5672, xác thực bằng user orders-service và mở vhost /orders. Binding processOrder-in-0 dùng destination orders.events và group order-service; binder ánh xạ chúng thành exchange/queue theo quy tắc của Rabbit binder.

Giá trị RABBITMQ_PASSWORD_FROM_SECRET là placeholder minh họa; khi triển khai hãy ánh xạ secret từ môi trường hoặc secret manager vào thuộc tính password. Không ghi mật khẩu thật vào application.yml.

### 5.1. Dùng nhiều Rabbit binder hoặc nhiều broker

Nếu ứng dụng có nhiều binder, mỗi binder có thể có environment riêng. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        rabbit-orders:
          type: rabbit
          defaultCandidate: false
          environment:
            spring:
              rabbitmq:
                host: orders-rabbit.internal
                port: 5672
                username: orders-service
                password: ORDERS_RABBIT_PASSWORD_FROM_SECRET
                virtual-host: /orders
        rabbit-audit:
          type: rabbit
          defaultCandidate: false
          environment:
            spring:
              rabbitmq:
                host: audit-rabbit.internal
                port: 5672
                username: audit-service
                password: AUDIT_RABBIT_PASSWORD_FROM_SECRET
                virtual-host: /audit
      bindings:
        processOrder-in-0:
          binder: rabbit-orders
          destination: orders.events
          group: order-service
        publishAudit-out-0:
          binder: rabbit-audit
          destination: audit.events
~~~

rabbit-orders và rabbit-audit là hai binder configuration name cùng có type rabbit, nhưng mỗi binder có host, credential và vhost riêng. Đặt defaultCandidate: false để chỉ binding tham chiếu tường minh mới chọn chúng.

Nếu dùng inheritEnvironment: false, hãy khai báo đầy đủ thuộc tính cần thiết trong binder environment và kiểm tra cách triển khai cấp placeholder/secret cho context riêng.

## 6. Cấu hình TLS cho kết nối AMQPS

TLS mã hóa dữ liệu trên đường truyền và cho phép client xác minh danh tính máy chủ bằng chứng thư. RabbitMQ thường cung cấp listener TLS trên cổng 5671, nhưng cổng thực tế phụ thuộc cấu hình broker.

Với TLS một chiều:

1. RabbitMQ trình chứng thư máy chủ.
2. Client kiểm tra chuỗi chứng thư dựa trên trust store.
3. Client xác minh hostname trong chứng thư khớp tên máy chủ kết nối.
4. Sau handshake, client thực hiện AMQP authentication bằng username/password.

Ví dụ Spring Boot Rabbit connection:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal
    port: 5671
    username: orders-service
    password: RABBITMQ_PASSWORD_FROM_SECRET
    virtual-host: /orders
    ssl:
      enabled: true
      trust-store: file:/run/secrets/rabbitmq-truststore.p12
      trust-store-password: RABBITMQ_TRUSTSTORE_PASSWORD_FROM_SECRET
      trust-store-type: PKCS12
      validate-server-certificate: true
      verify-hostname: true
~~~

trust-store chứa CA hoặc certificate chain mà client tin cậy để xác minh broker. validate-server-certificate và verify-hostname nên được bật trong production. Không tắt hostname verification chỉ để làm cho một kết nối test vượt qua.

Tên thuộc tính TLS cụ thể phụ thuộc Spring Boot/Spring AMQP version. Kiểm tra metadata cấu hình và tài liệu đúng phiên bản trong BOM dự án trước khi triển khai.

### 6.1. Dùng URI AMQPS

Spring AMQP cũng hỗ trợ cấu hình connection bằng URI. URI dùng scheme amqps để yêu cầu TLS:

~~~text
amqps://orders-service:ENCODED_PASSWORD@rabbitmq.internal:5671/%2Forders
~~~

Đây là ví dụ minh họa cú pháp. Ký tự đặc biệt trong username/password và vhost cần được percent-encode theo quy tắc URI. Vhost /orders trở thành %2Forders trong path.

Không đặt URI chứa mật khẩu thật trong source code hoặc log. Nếu cấu hình đồng thời URI và các thuộc tính host/port/user/password riêng lẻ, hãy kiểm tra precedence của phiên bản Spring Boot đang dùng; tránh để hai nguồn cấu hình mâu thuẫn.

## 7. Mutual TLS và chứng thư client

TLS một chiều xác minh broker với client. Mutual TLS (mTLS) bổ sung bước broker xác minh chứng thư client. Broker cần được cấu hình yêu cầu và tin cậy client certificate; chỉ đặt key store ở phía ứng dụng chưa đủ để bật mTLS.

Ví dụ cấu hình client key store:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal
    port: 5671
    username: orders-service
    password: RABBITMQ_PASSWORD_FROM_SECRET
    virtual-host: /orders
    ssl:
      enabled: true
      key-store: file:/run/secrets/orders-client.p12
      key-store-password: RABBITMQ_KEYSTORE_PASSWORD_FROM_SECRET
      key-store-type: PKCS12
      trust-store: file:/run/secrets/rabbitmq-truststore.p12
      trust-store-password: RABBITMQ_TRUSTSTORE_PASSWORD_FROM_SECRET
      trust-store-type: PKCS12
      validate-server-certificate: true
      verify-hostname: true
~~~

Trong mô hình này:

- Key store chứa private key và certificate của client.
- Trust store chứa CA/certificate dùng để xác minh RabbitMQ server.
- RabbitMQ server cần trust CA đã ký client certificate và cấu hình TLS listener yêu cầu peer certificate.
- Nếu muốn certificate thay thế username/password, broker phải bật authentication mechanism X.509/SASL EXTERNAL và ánh xạ certificate identity sang user RabbitMQ.

Nếu broker chỉ yêu cầu TLS client certificate để xác minh kênh nhưng vẫn dùng username/password cho AMQP authentication, cả hai lớp đều được áp dụng. mTLS không tự động cấp quyền vhost hoặc resource.

## 8. Tạo trust store và key store

Java client thường sử dụng JKS hoặc PKCS12. PKCS12 là định dạng trao đổi phổ biến cho certificate và private key.

Ví dụ nhập CA certificate vào trust store:

~~~bash
keytool -importcert \
  -alias rabbitmq-ca \
  -file rabbitmq-ca.pem \
  -keystore rabbitmq-truststore.p12 \
  -storetype PKCS12
~~~

Ví dụ kiểm tra nội dung trust store:

~~~bash
keytool -list \
  -keystore rabbitmq-truststore.p12 \
  -storetype PKCS12
~~~

Nếu dùng mTLS, key store phải chứa private key và certificate chain của client, không chỉ chứa CA certificate. Chứng thư client phải có mục đích sử dụng phù hợp và được CA mà broker tin cậy ký.

Không đặt password của key store/trust store trong script được commit. Trong container, mount file từ secret volume với quyền đọc hạn chế và truyền password qua secret environment hoặc cơ chế quản lý secret của nền tảng.

## 9. TLS phía RabbitMQ broker

Client chỉ kết nối TLS thành công khi RabbitMQ có listener TLS và certificate chain phù hợp. Một cấu hình broker cần xác định:

- Certificate và private key của server.
- CA certificate được tin cậy nếu xác minh client certificate.
- TLS listener port, thường là 5671.
- Phiên bản TLS và cipher suite được phép.
- Chính sách verify peer và yêu cầu client certificate.
- Authentication mechanism được phép sau TLS handshake.

Ví dụ cấu hình khái niệm trong rabbitmq.conf:

~~~ini
listeners.tcp = none
listeners.ssl.default = 5671

ssl_options.cacertfile = /etc/rabbitmq/tls/ca.pem
ssl_options.certfile   = /etc/rabbitmq/tls/server.pem
ssl_options.keyfile    = /etc/rabbitmq/tls/server-key.pem

ssl_options.verify = verify_peer
ssl_options.fail_if_no_peer_cert = true
~~~

Hai thuộc tính verify và fail_if_no_peer_cert trên yêu cầu broker xác minh chứng thư peer và từ chối client không cung cấp chứng thư. Đây là ví dụ mTLS; nếu chỉ cần TLS một chiều, cấu hình broker có thể không yêu cầu client certificate.

Không sao chép cấu hình TLS từ ví dụ vào production mà chưa đối chiếu chứng thư, CA, hostname, phiên bản RabbitMQ và chính sách bảo mật của tổ chức. Cấu hình TLS sai ở broker có thể làm toàn bộ client không kết nối được.

## 10. Authentication bằng certificate

RabbitMQ hỗ trợ xác thực X.509 thông qua SASL EXTERNAL khi plugin/backend và listener được cấu hình phù hợp. Certificate client được ánh xạ thành username theo chính sách của broker, thường dựa trên common name hoặc cơ chế mapping đã cấu hình.

Để dùng cơ chế này, cần:

1. Bật TLS listener và yêu cầu client certificate.
2. Cấu hình RabbitMQ tin cậy CA ký client certificate.
3. Bật authentication mechanism EXTERNAL ở broker và client.
4. Xác định quy tắc ánh xạ certificate identity sang RabbitMQ user.
5. Tạo user/identity tương ứng và cấp permission trên vhost.
6. Cấu hình client dùng certificate phù hợp và không gửi cơ chế password nếu không được yêu cầu.

Đây là cấu hình ở mức broker và client, không tự động xuất hiện chỉ vì spring.rabbitmq.ssl.enabled=true. Hãy xác minh cơ chế SASL mà Spring AMQP client và RabbitMQ deployment hỗ trợ trong phiên bản đang dùng.

## 11. Phân biệt lỗi authentication, vhost, permission và TLS

| Triệu chứng | Lớp có thể lỗi | Hướng kiểm tra |
|---|---|---|
| Connection refused | TCP/listener/network | Host, port, firewall, listener 5672/5671 |
| SSLHandshakeException | TLS handshake | Certificate chain, protocol, cipher, client certificate |
| PKIX path building failed | Trust store | CA/intermediate certificate và trust store path |
| No subject alternative DNS name matching | Hostname verification | Host kết nối phải khớp SAN trong server certificate |
| ACCESS_REFUSED - Login was refused | Authentication | Username, password, backend, mechanism |
| vhost not found | Virtual host | Vhost đã được tạo đúng tên chưa |
| access to vhost refused | Vhost authorization | User đã được cấp permission trên vhost chưa |
| access to exchange/queue refused | Resource authorization | configure/write/read regex có khớp resource không |
| Channel shutdown khi declare | Topology permission hoặc thuộc tính declare không tương thích | Quyền configure và topology hiện có |

Thứ tự điều tra hiệu quả:

1. Kiểm tra DNS, TCP và listener.
2. Nếu dùng TLS, xác minh handshake, trust chain và hostname.
3. Kiểm tra authentication mechanism và credential.
4. Kiểm tra vhost tồn tại và user có quyền truy cập.
5. Kiểm tra configure/write/read cho exchange và queue.
6. Kiểm tra binder đang dùng đúng host, vhost, user và TLS environment.

Không thay đổi permission thành .* ngay khi gặp ACCESS_REFUSED. Trước tiên hãy xác định resource và operation nào bị từ chối.

## 12. Kiểm tra bằng công cụ RabbitMQ và OpenSSL

Trên broker, quản trị viên có thể kiểm tra:

~~~bash
rabbitmqctl list_vhosts
rabbitmqctl list_users
rabbitmqctl list_permissions -p /orders
rabbitmqctl list_queues -p /orders name consumers messages_ready messages_unacknowledged
rabbitmqctl list_connections user vhost peer_host peer_port state
~~~

Các lệnh này yêu cầu quyền quản trị phù hợp trên node RabbitMQ. Không cấp quyền quản trị cho user ứng dụng chỉ để chạy lệnh chẩn đoán.

Kiểm tra TLS listener từ máy client:

~~~bash
openssl s_client \
  -connect rabbitmq.internal:5671 \
  -servername rabbitmq.internal \
  -showcerts \
  -verify_return_error
~~~

Nếu cần kiểm tra client certificate:

~~~bash
openssl s_client \
  -connect rabbitmq.internal:5671 \
  -servername rabbitmq.internal \
  -cert client-cert.pem \
  -key client-key.pem \
  -CAfile rabbitmq-ca.pem \
  -verify_return_error
~~~

Lệnh OpenSSL kiểm tra TLS handshake và certificate validation; nó không xác minh username/password AMQP, vhost hoặc resource permissions. Cần kiểm tra tiếp bằng AMQP client hoặc ứng dụng Spring Cloud Stream.

## 13. Kiểm thử kết nối và quyền theo từng vai trò

Nên có các tài khoản test đại diện cho producer, consumer và workload quản lý topology:

| Vai trò | Quyền mong đợi | Hành vi cần kiểm tra |
|---|---|---|
| Producer | Vào đúng vhost, write đúng exchange | Publish thành công; publish vào exchange khác bị từ chối |
| Consumer | Vào đúng vhost, read đúng queue | Consume thành công; đọc queue khác bị từ chối |
| Topology provisioner | Configure trên resource cần tạo; thêm write/read nếu cần | Declare exchange, queue, binding theo kế hoạch |
| Service runtime | Quyền nhỏ nhất để vận hành | Không thể tạo/xóa resource ngoài phạm vi |

Các tình huống kiểm thử:

1. Đúng credential và đúng vhost: kết nối thành công.
2. Sai password: authentication thất bại.
3. Đúng password nhưng user chưa có quyền vhost: mở connection bị từ chối.
4. User vào đúng vhost nhưng thiếu write: publish bị từ chối.
5. User thiếu read: consume bị từ chối.
6. User thiếu configure khi binder cần tạo queue: binding initialization thất bại.
7. TLS trust store thiếu CA: handshake thất bại.
8. Hostname không khớp certificate SAN: hostname verification thất bại.
9. TLS một chiều hoạt động nhưng broker yêu cầu mTLS: client không có certificate sẽ bị từ chối.
10. Certificate hết hạn hoặc bị thu hồi theo chính sách PKI: kết nối bị từ chối.

Không kiểm thử bằng cách đưa password sai vào log hoặc ghi lại URI đầy đủ. Test nên xác minh loại lỗi và trạng thái kết nối mà không in secret.

## 14. Triển khai trong container và Kubernetes

Với ứng dụng chạy trong container, nên mount certificate và trust store từ secret volume:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: order-consumer
spec:
  containers:
    - name: app
      image: example/order-consumer:latest
      env:
        - name: RABBITMQ_PASSWORD
          valueFrom:
            secretKeyRef:
              name: rabbitmq-orders
              key: password
        - name: RABBITMQ_TRUSTSTORE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: rabbitmq-orders-tls
              key: truststore-password
      volumeMounts:
        - name: rabbitmq-tls
          mountPath: /run/secrets
          readOnly: true
  volumes:
    - name: rabbitmq-tls
      secret:
        secretName: rabbitmq-orders-tls
~~~

Đây là manifest minh họa. Secret cần được tạo và quản lý qua quy trình an toàn; không commit nội dung Secret chứa credential thật vào Git. Cấp quyền đọc secret cho đúng service account và chỉ mount file cần thiết.

Khi xoay vòng certificate:

- Cấp chứng thư mới trước khi chứng thư cũ hết hạn.
- Cập nhật trust store để client tin CA mới trong giai đoạn chuyển tiếp.
- Cập nhật certificate phía broker theo quy trình rolling phù hợp.
- Khởi tạo lại hoặc refresh connection factory nếu client không tự reload certificate.
- Xác minh các connection mới đã dùng certificate mới.
- Thu hồi certificate cũ sau khi mọi client đã chuyển đổi.

Không giả định JVM tự nạp lại file trust store/key store đã mount khi file thay đổi. Khả năng reload phụ thuộc cách Spring AMQP/SSLContext được tạo và phiên bản thư viện.

## 15. Bảo mật vhost và permission trong môi trường nhiều dịch vụ

Một thiết kế có thể tách namespace theo miền nghiệp vụ:

~~~text
/orders
  orders.events
  orders.retry
  orders.dlq

/billing
  billing.commands
  billing.events
  billing.dlq

/notifications
  notifications.outbound
  notifications.dlq
~~~

Mỗi dịch vụ có user riêng:

- orders-consumer chỉ đọc queue đơn hàng.
- billing-publisher chỉ ghi exchange thanh toán.
- notification-worker chỉ đọc queue thông báo.
- Tài khoản provisioner dùng trong deployment pipeline để khai báo topology.

Tách user và vhost không thay thế việc giới hạn permission theo resource. Một user có quyền .* trên /orders vẫn có thể thao tác mọi queue/exchange trong vhost đó. Hãy chọn regex hẹp theo tên resource và chức năng.

Không cấp tag administrator, management hoặc monitoring cho user runtime nếu không cần truy cập Management UI/API. Tag quản trị và permission AMQP là hai cơ chế khác nhau; tag không thay thế configure/write/read trên vhost.

## 16. TLS và xác thực không thay thế lẫn nhau

Các trường hợp thường gặp:

| TLS | AMQP authentication | Kết quả |
|---|---|---|
| Tắt | Username/password | Kết nối có thể xác thực nhưng dữ liệu không được mã hóa trên đường truyền |
| Bật, xác minh server | Username/password | Kênh mã hóa và broker được client xác minh |
| Bật mTLS | Username/password | Kênh mã hóa, broker xác minh client certificate, sau đó xác thực AMQP bằng password |
| Bật mTLS + SASL EXTERNAL | Certificate identity | Broker có thể dùng certificate để xác thực user nếu cấu hình mapping/mechanism đầy đủ |

TLS không tự cấp quyền truy cập vhost. Username/password không mã hóa dữ liệu. Vhost không xác minh certificate. Permission không bảo vệ dữ liệu khỏi bị đọc trên đường truyền. Cần cấu hình đầy đủ từng lớp theo mô hình đe dọa của hệ thống.

## 17. Checklist trước khi đưa vào production

- [ ] Tạo user riêng cho từng workload; không dùng guest hoặc tài khoản quản trị.
- [ ] Tạo đúng virtual host và ghi rõ tên trong cấu hình binder.
- [ ] Cấp permission configure/write/read tối thiểu theo resource.
- [ ] Xác định binder có tự khai báo exchange, queue và binding hay topology được provision bên ngoài.
- [ ] Cấu hình host, port, username, password và virtual host trong đúng binder environment.
- [ ] Dùng secret manager hoặc secret volume để cấp credential.
- [ ] Bật TLS listener ở broker và spring.rabbitmq.ssl.enabled ở client.
- [ ] Cài trust store có CA phù hợp; giữ server certificate validation và hostname verification.
- [ ] Chỉ bật mTLS khi broker yêu cầu client certificate và trust chain đã được cấu hình.
- [ ] Nếu dùng SASL EXTERNAL, kiểm tra authentication mechanism và mapping certificate identity.
- [ ] Xác minh TLS protocol, cipher và certificate expiry theo chính sách PKI.
- [ ] Kiểm tra vhost, permission, queue consumer count và publish/consume thực tế.
- [ ] Kiểm thử sai password, thiếu permission, sai vhost, sai hostname và certificate hết hạn.
- [ ] Có kế hoạch xoay vòng credential/certificate và phục hồi kết nối.
- [ ] Không ghi secret, private key hoặc URI đầy đủ vào log.

## Tài liệu tham khảo chính thức

- [RabbitMQ Access Control](https://www.rabbitmq.com/docs/access-control): user, authentication backend, virtual host và resource permissions.
- [RabbitMQ Virtual Hosts](https://www.rabbitmq.com/docs/vhosts): namespace, tạo vhost và quyền truy cập.
- [RabbitMQ TLS Support](https://www.rabbitmq.com/docs/ssl): TLS listener, certificate, peer verification và client certificate.
- [RabbitMQ Networking](https://www.rabbitmq.com/docs/networking): port, listener và kết nối AMQP/TLS.
- [Spring Cloud Stream Rabbit Binder Reference](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html): Rabbit binder và cấu hình kết nối.
- [Spring Boot RabbitMQ Support](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): thuộc tính spring.rabbitmq.* và cấu hình SSL.
- [Spring AMQP Connection and Resource Management](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): ConnectionFactory và thiết lập kết nối AMQP.

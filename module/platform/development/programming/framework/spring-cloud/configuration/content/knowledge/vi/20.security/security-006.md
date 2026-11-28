# Quản lý token Git, mật khẩu broker và thông tin xác thực client

Spring Cloud Config tập trung cấu hình cho nhiều ứng dụng, nhưng để hoạt động an toàn, từng kết nối cần có thông tin xác thực riêng. Config Server phải đọc được Git repository; Config Server và các Config Client tham gia Spring Cloud Bus phải kết nối được message broker; Config Client phải được phép đọc cấu hình từ Config Server. Ba nhóm credential này phục vụ các ranh giới tin cậy khác nhau và cần được cấp, lưu trữ, luân chuyển độc lập.

Bài viết hướng dẫn cách quản lý token Git, mật khẩu RabbitMQ hoặc Kafka, thông tin xác thực giữa client và Config Server, cách đưa secret vào runtime, giới hạn quyền, bảo vệ đường truyền và xoay vòng credential. Các ví dụ dùng Git qua HTTPS, RabbitMQ và HTTP Basic để minh họa; môi trường thực tế có thể thay bằng SSH deploy key, Kafka ACL, OAuth2 gateway hoặc mTLS theo nền tảng.

## 1. Phân biệt ba nhóm thông tin xác thực

Không dùng một token hoặc mật khẩu cho tất cả kết nối. Mỗi credential nên có chủ sở hữu, phạm vi quyền và vòng đời riêng.

| Credential | Thành phần sử dụng | Mục đích | Quyền tối thiểu nên cấp |
| --- | --- | --- | --- |
| Git token hoặc deploy key | Config Server | Đọc repository cấu hình | Chỉ đọc repository cần thiết |
| Broker username/password hoặc client certificate | Config Server và các Config Client tham gia Bus | Publish/consume sự kiện Bus | Chỉ truy cập virtual host, topic hoặc resource cần thiết |
| Client credential hoặc certificate | Config Client | Xác thực khi gọi Config Server | Chỉ đọc application/profile được phép |
| Config Server credential tới Vault hoặc secret manager | Config Server | Đọc secret cấu hình | Chỉ đọc secret path được phân công |

Ví dụ, `orders-service` có thể đọc cấu hình qua Config Server bằng danh tính riêng; Config Server dùng một Git token để đọc repository và một danh tính khác để kết nối RabbitMQ. Git token không được gửi cho client. RabbitMQ password cũng không được dùng làm mật khẩu HTTP Basic của Config Server.

Tách credential giúp thu hồi một quyền mà không phải thay toàn bộ kết nối. Nếu token Git bị lộ, có thể thu hồi quyền đọc repository mà không phải đổi mật khẩu broker hoặc credential của các client.

## 2. Quản lý Git token cho Config Server

Git backend thường dùng HTTPS username/password hoặc SSH key để clone và fetch repository. Với Git provider yêu cầu personal access token (PAT), token thường được truyền ở vị trí password cùng username phù hợp với nhà cung cấp.

Ví dụ cấu hình Git backend:

~~~yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          default-label: main
          clone-on-start: true
          username: ${CONFIG_GIT_USERNAME}
          password: ${CONFIG_GIT_TOKEN}
~~~

Các placeholder trong ví dụ chỉ tham chiếu biến runtime; không đặt token thật trong file YAML được commit. Với PAT, chọn scope chỉ đọc nội dung repository cấu hình cần thiết. Nếu nhà cung cấp hỗ trợ deploy token hoặc project access token có phạm vi hẹp, ưu tiên danh tính dành riêng cho Config Server thay cho token cá nhân của một nhân viên.

Một số nguyên tắc:

- Tạo token riêng cho từng môi trường hoặc từng Config Server workload khi cần tách quyền.
- Chỉ cấp quyền đọc repository; không cấp quyền push, quản lý thành viên hoặc quản trị tổ chức.
- Đặt expiration phù hợp và có lịch nhắc rotate trước ngày hết hạn.
- Không nhúng token vào URL như `https://user:token@git.example.com/...`; URL có thể xuất hiện trong log, exception hoặc process diagnostics.
- Không truyền token qua tham số dòng lệnh nếu có thể tránh, vì command history và process list có thể làm lộ giá trị.
- Không ghi token vào Dockerfile, image layer, Git, log CI hoặc file cấu hình được chia sẻ.

Nếu dùng SSH deploy key, tạo key riêng cho repository và cấp read-only. Xác minh host key của Git server bằng known-hosts được quản lý; không tắt kiểm tra host key chỉ để bỏ qua lỗi kết nối. Private key và passphrase phải được cấp vào runtime Config Server qua secret manager hoặc secret volume.

## 3. Đưa Git credential vào runtime

Trong phát triển cục bộ, có thể dùng biến môi trường được thiết lập ngoài repository. Ví dụ PowerShell:

~~~powershell
$env:CONFIG_GIT_USERNAME = "config-reader"
$env:CONFIG_GIT_TOKEN = "<token-from-secret-store>"
java -jar config-server.jar
~~~

Đây chỉ là minh họa tên biến; tránh nhập token thật vào script lưu lâu dài hoặc chia sẻ terminal transcript. Biến môi trường cũng có thể được đọc bởi tiến trình cùng quyền hoặc xuất hiện trong diagnostics, vì vậy production nên ưu tiên secret manager hoặc cơ chế secret injection của nền tảng.

Với Kubernetes, dùng Secret và tham chiếu key vào container:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: config-server
spec:
  containers:
    - name: config-server
      image: example/config-server:1.0
      env:
        - name: CONFIG_GIT_USERNAME
          valueFrom:
            secretKeyRef:
              name: config-server-git
              key: username
        - name: CONFIG_GIT_TOKEN
          valueFrom:
            secretKeyRef:
              name: config-server-git
              key: token
~~~

Secret Kubernetes cần được bảo vệ bằng RBAC, encryption at rest trong control plane và giới hạn quyền đọc theo namespace/service account. Chỉ dùng Secret object không tự động bảo đảm bí mật nếu người dùng hoặc workload quá nhiều có thể đọc nó.

Với Docker Compose, có thể mount secret thành file read-only. Spring Boot không tự động chuyển mọi file trong Compose secrets thành biến môi trường; cần đọc file qua cơ chế phù hợp, chẳng hạn Config Data `configtree:` hoặc code tích hợp secret manager. Ví dụ:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Tên file trong thư mục secret có thể biểu diễn property key, ví dụ `spring.cloud.config.server.git.password`. Kiểm tra quyền đọc file và xác nhận Config Server đã bind đúng thuộc tính mà không in giá trị secret ra log.

## 4. Cấp quyền đọc Git repository theo nguyên tắc tối thiểu

Config Server thường chỉ cần fetch và đọc nội dung cấu hình. Không cấp quyền ghi cho credential này. Nếu repository chứa cấu hình của nhiều ứng dụng, cân nhắc tách repository theo miền sở hữu hoặc dùng cơ chế phân quyền ở Git provider để giảm phạm vi khi một token bị lộ.

Đối với GitHub/GitLab/Bitbucket hoặc Git server nội bộ, tên scope và cách tạo token khác nhau. Hãy chọn quyền tương đương read repository contents, không sao chép một danh sách scope chung cho mọi nhà cung cấp. Kiểm tra token bằng một lần clone/fetch từ môi trường kiểm thử với đúng repository cần đọc.

Nếu Config Server phục vụ nhiều repository, mỗi repository có thể cần credential riêng. Tránh cấu hình một token tổ chức có quyền đọc mọi repository chỉ vì tiện triển khai. Lưu ý rằng các thuộc tính credential đặt trong cấu hình server có thể được kế thừa hoặc áp dụng rộng hơn mong đợi; kiểm tra cấu hình repository cụ thể và log khi clone.

## 5. Quản lý username/password cho RabbitMQ

Spring Cloud Bus cần message broker để phân phối sự kiện refresh. Với RabbitMQ, Config Server và các Config Client tham gia Bus cần kết nối tới broker bằng username/password hoặc cơ chế xác thực tương ứng.

Ví dụ:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal
    port: 5671
    virtual-host: /config-bus
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    ssl:
      enabled: true
~~~

Port 5671 thường được dùng cho AMQPS; xác nhận listener và chứng thư TLS của broker theo cấu hình thực tế. Nếu dùng port không mã hóa trong mạng nội bộ, rủi ro nghe lén hoặc đánh cắp credential vẫn tồn tại; production nên bảo vệ đường truyền bằng TLS.

Không dùng tài khoản `guest` mặc định cho các service. Tạo tài khoản riêng cho Config Server và từng nhóm client, ví dụ:

- `config-server-bus`: publish event từ Config Server và nhận event nếu kiến trúc yêu cầu.
- `orders-service-bus`: tham gia Bus cho các instance đơn hàng.
- `payment-service-bus`: tham gia Bus cho các instance thanh toán.

Đặt các tài khoản trong virtual host chuyên biệt như `/config-bus`. Cấp quyền configure/write/read tối thiểu trên exchange, queue và binding mà Spring Cloud Bus cần. Tên resource và pattern cụ thể có thể phụ thuộc phiên bản Bus, binder và topology broker; kiểm tra topology thực tế trước khi khóa ACL quá chặt. Không cấp quyền quản trị broker cho tài khoản ứng dụng.

## 6. Cấu hình RabbitMQ và phân quyền

Tài khoản ứng dụng không nên là administrator. Quản trị viên broker tạo virtual host, user và quyền truy cập theo quy trình của nền tảng. Ví dụ các lệnh minh họa:

~~~bash
rabbitmqctl add_vhost /config-bus
rabbitmqctl add_user orders-service-bus '<password-from-secret-manager>'
rabbitmqctl set_permissions -p /config-bus orders-service-bus '<configure-pattern>' '<write-pattern>' '<read-pattern>'
~~~

Các pattern trong lệnh cần được xác định theo exchange/queue mà Bus thực sự sử dụng. Không dùng biểu thức rộng như `.*` cho mọi quyền trong production nếu chưa đánh giá phạm vi. Tài khoản tạo topology có thể cần quyền configure; nếu topology được tạo trước bởi operator, quyền configure có thể được giảm tùy cách triển khai.

Với nhiều service, dùng user riêng để có thể thu hồi hoặc rotate một service mà không làm gián đoạn toàn bộ Bus. Nếu nhiều replica của cùng một service dùng chung một user, sự cố credential có thể ảnh hưởng toàn bộ replica của service đó; có thể tách theo workload hoặc môi trường nếu cần audit chi tiết hơn.

Với Kafka, mô hình tương tự là dùng principal riêng, TLS/SASL phù hợp và ACL giới hạn topic/group. Không dùng chung một principal có quyền đọc/ghi mọi topic cho toàn bộ ứng dụng.

## 7. Bảo vệ thông tin xác thực của Config Client khi gọi Config Server

Config Client cần xác thực với Config Server nếu endpoint không cho phép truy cập ẩn danh. Với HTTP Basic, Config Server có thể cấu hình Spring Security và tài khoản service:

~~~yaml
spring:
  security:
    user:
      name: config-client
      password: ${CONFIG_CLIENT_PASSWORD}
~~~

Config Client khai báo credential riêng:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: "configserver:https://config.example.internal"
  cloud:
    config:
      username: ${CONFIG_SERVER_USERNAME}
      password: ${CONFIG_SERVER_PASSWORD}
~~~

Đây là ví dụ tối thiểu về xác thực. Trong môi trường nhiều ứng dụng, không nên dùng một username/password chung cho tất cả client nếu cần thu hồi và audit theo service. Tạo danh tính riêng cho `orders-service`, `payment-service` và các workload khác; áp dụng authorization policy để giới hạn application/profile mà mỗi danh tính được đọc.

HTTP Basic chỉ mã hóa credential khi được truyền qua TLS. Không gửi Basic credentials qua HTTP thuần, kể cả trong mạng riêng, trừ khi có một lớp mã hóa đường truyền tương đương đã được xác nhận.

Cấu hình username/password trên không tự tạo ra quyền đọc theo application. Spring Security mặc định có thể xác thực người gọi nhưng việc giới hạn từng client vào từng endpoint Config Server cần authorization rules, gateway policy hoặc một cơ chế cấp quyền tương ứng. Hãy kiểm tra cả xác thực lẫn phân quyền; xác thực thành công không có nghĩa caller được phép đọc mọi cấu hình.

## 8. Khi nào dùng mTLS hoặc OAuth2?

HTTP Basic có thể phù hợp cho hệ thống nhỏ hoặc mạng quản trị đơn giản nếu dùng TLS, secret injection và tài khoản riêng. Với hệ thống nhiều workload, có thể dùng các cơ chế danh tính mạnh hơn:

- **mTLS**: client và server xác thực chứng thư của nhau; certificate được cấp, gia hạn và thu hồi theo PKI của tổ chức.
- **OAuth2 client credentials**: workload lấy access token từ identity provider; gateway hoặc security configuration ở Config Server xác minh token và scope.
- **Workload identity**: nền tảng cấp danh tính cho pod/service mà không cần nhúng một password dài hạn vào image.

Không giả định chỉ thêm dependency OAuth2 vào Config Client sẽ tự cấu hình toàn bộ luồng xác thực với Config Server. Cần thiết kế resource server/gateway, token audience, scope, certificate trust và authorization policy tương ứng. Đối với mTLS, bảo vệ cả truststore/keystore và quy trình rotation chứng thư.

## 9. Tách credential giữa các môi trường và ứng dụng

Credential dev, staging và production nên độc lập. Không dùng cùng Git token, RabbitMQ password hoặc client password trên tất cả môi trường. Nếu secret dev bị lộ, phạm vi ảnh hưởng không nên lan sang production.

Một ma trận quyền đơn giản:

| Workload | Git read | RabbitMQ | Config Server |
| --- | --- | --- | --- |
| Config Server dev | Token chỉ đọc repo dev | User trên vhost dev | Endpoint nội bộ dev |
| Config Server prod | Token chỉ đọc repo production cần thiết | User trên vhost prod | Endpoint nội bộ prod |
| orders-service prod | Không cần Git token | User Bus của orders | Danh tính chỉ đọc cấu hình orders |
| payment-service prod | Không cần Git token | User Bus của payment | Danh tính chỉ đọc cấu hình payment |

Client không cần token Git chỉ để lấy cấu hình từ Config Server. Việc cấp Git token cho client mở rộng phạm vi truy cập repository và làm mất ý nghĩa của điểm phân phối tập trung.

Nếu một Config Server phục vụ nhiều ứng dụng, cần kiểm soát authorization theo application và profile. Nếu không thể triển khai phân quyền đủ chi tiết, cân nhắc tách Config Server hoặc repository theo miền tin cậy để giảm tác động khi một credential bị lộ.

## 10. Luân chuyển Git token

Token có thể hết hạn, bị thu hồi hoặc cần thay thế định kỳ. Quy trình rotation an toàn nên tránh khoảng thời gian Config Server mất quyền đọc repository.

1. Tạo token mới với cùng hoặc phạm vi quyền hẹp hơn token cũ.
2. Lưu token mới vào secret manager dưới một version mới.
3. Cập nhật secret reference của Config Server.
4. Rolling restart hoặc reload credential theo cơ chế đã kiểm chứng của Git backend và phiên bản ứng dụng.
5. Xác nhận Config Server clone/fetch được repository và trả đúng application/profile/label.
6. Theo dõi log Git backend và lỗi refresh trong một khoảng thời gian.
7. Thu hồi token cũ sau khi mọi replica đã dùng token mới.

Không giả định Git backend tự động đọc lại token khi secret manager đổi version. Nếu credential được bind lúc khởi động hoặc Git client giữ session/cache, cần triển khai lại Config Server theo cách an toàn. Với nhiều replica, cập nhật theo từng nhóm để duy trì khả năng phục vụ.

## 11. Luân chuyển mật khẩu broker

Broker password rotation cần phối hợp giữa broker và tất cả service tham gia Bus. Một cách ít gián đoạn là tạo user/password mới, cấp quyền tương đương, cập nhật từng workload rồi thu hồi user cũ.

1. Tạo broker user mới hoặc credential version mới.
2. Cấp quyền tối thiểu trên đúng virtual host và resource.
3. Cập nhật secret cho Config Server và các Config Client tham gia Bus.
4. Rolling restart hoặc tái kết nối các workload để chúng dùng credential mới.
5. Kiểm tra kết nối broker, queue/subscription và việc nhận/phát Bus event.
6. Xác nhận tất cả instance đã chuyển sang user mới.
7. Thu hồi user cũ và audit kết nối còn sót.

Không đổi password của một user đang được nhiều service dùng rồi kỳ vọng mọi connection hiện tại tự cập nhật. Connection đã mở có thể còn hoạt động đến khi bị đóng, trong khi lần reconnect tiếp theo thất bại. Theo dõi connection theo username và thời điểm để xác nhận rotation hoàn tất.

## 12. Luân chuyển credential Config Client

Khi client dùng HTTP Basic hoặc token để gọi Config Server, có thể tạo danh tính mới trong giai đoạn chuyển đổi:

1. Tạo user hoặc credential mới cho service.
2. Cấp quyền đọc đúng application/profile.
3. Cập nhật secret reference trong deployment của client.
4. Rolling restart client hoặc refresh cơ chế credential nếu ứng dụng hỗ trợ và đã được kiểm thử.
5. Kiểm tra client lấy được cấu hình và không còn request xác thực bằng credential cũ.
6. Thu hồi credential cũ.

Nếu dùng mTLS, cấp certificate mới, phân phối trust chain phù hợp, chuyển workload sang certificate mới rồi thu hồi certificate cũ sau khi các client đã chuyển xong. Theo dõi expiration để không chờ đến lúc chứng thư hết hạn mới xử lý.

## 13. Xử lý khi credential bị lộ

Nếu token Git, broker password hoặc client credential xuất hiện trong Git, log, ticket hoặc ảnh chụp màn hình, hãy coi credential đã bị lộ. Xóa dòng chứa secret khỏi file hiện tại không thu hồi được credential và không xóa bản sao trong Git history.

Quy trình phản ứng:

- Thu hồi hoặc disable credential bị lộ ngay khi có thể.
- Tạo credential thay thế với quyền tối thiểu.
- Cập nhật Config Server, client hoặc broker theo đúng nhóm bị ảnh hưởng.
- Kiểm tra audit log của Git provider, broker và Config Server để tìm truy cập bất thường.
- Xác định repository, artifact, log, cache và backup có thể chứa secret.
- Làm sạch lịch sử Git và bản sao theo quy trình incident response, nhưng vẫn coi secret cũ đã bị lộ cho đến khi bị thu hồi.
- Kiểm tra secret có bị dùng lại ở môi trường hoặc hệ thống khác hay không.
- Ghi nhận nguyên nhân, phạm vi ảnh hưởng và biện pháp ngăn tái diễn.

Không dán credential vào chat hoặc gửi qua email để nhờ kiểm tra. Dùng kênh secret sharing được tổ chức phê duyệt và không đưa giá trị thật vào báo cáo sự cố.

## 14. Bảo vệ log, Actuator và pipeline

Credential có thể bị lộ ngoài file cấu hình thông qua log, endpoint chẩn đoán hoặc pipeline. Cần rà soát toàn bộ đường đi của secret:

- Không log HTTP Authorization header, query string chứa token hoặc request body có plaintext.
- Không bật debug logging cho HTTP client, Git transport hoặc AMQP nếu logger có thể in credential.
- Sanitize Actuator `env` và `configprops`; chỉ expose trong mạng quản trị với xác thực và phân quyền.
- Không in toàn bộ environment variables trong CI job.
- Mask secret trong output của pipeline nhưng không coi masking là biện pháp lưu trữ.
- Giới hạn quyền đọc artifact, build log và crash dump.
- Không truyền secret dưới dạng command-line argument nếu có phương án secret file hoặc secret manager.
- Audit ai đã đọc hoặc thay đổi secret, khi nào và qua workload nào.

Đặc biệt, Config Server có thể trả cấu hình đã giải mã cho client. Hãy kiểm soát endpoint Environment theo application/profile và không để một tài khoản đọc cấu hình của service khác nếu không có lý do vận hành.

## 15. Kiểm tra kết nối mà không tiết lộ secret

Khi kiểm tra Git, không in URL có token hoặc bật trace chứa Authorization header. Xác nhận bằng log kết quả clone/fetch, HTTP status và revision đã đọc; nếu cần, dùng một lệnh kiểm tra từ môi trường đã nhận secret mà không echo biến.

Khi kiểm tra RabbitMQ, dùng health/connection metrics hoặc giao diện quản trị có phân quyền để xác nhận user, vhost và connection state. Không in password trong lệnh chẩn đoán. Kiểm tra Bus bằng cách phát một sự kiện thử nghiệm không nhạy cảm và xác nhận client nhận event.

Khi kiểm tra Config Server, gọi endpoint bằng cơ chế xác thực an toàn và kiểm tra status code cùng metadata. Không lưu response chứa secret đã giải mã vào artifact hoặc ticket. Kiểm tra authorization riêng cho từng client để bảo đảm một service không đọc được cấu hình ngoài phạm vi của nó.

Một checklist kiểm tra:

| Kiểm tra | Kết quả mong muốn |
| --- | --- |
| Config Server fetch Git | Chỉ đọc được repository được cấp quyền |
| Config Server kết nối broker | Dùng user riêng, vhost đúng và TLS |
| Config Client kết nối broker | Chỉ tham gia Bus của môi trường tương ứng |
| Config Client gọi Config Server | Xác thực thành công qua TLS |
| Client đọc application khác | Bị từ chối nếu không có quyền |
| Log và Actuator | Không tiết lộ token/password/plaintext |
| Rotation | Credential cũ không còn được sử dụng sau khi hoàn tất |

## 16. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Config Server không clone được Git | Token hết hạn, sai scope, sai username hoặc URL | Kiểm tra quyền read repository và credential version |
| Clone được trên máy dev nhưng lỗi trong container | Secret chưa được inject, file mount sai hoặc user không đọc được | Kiểm tra secret mount, permission và runtime property binding |
| Git trả 401/403 | Credential không hợp lệ hoặc không có quyền repository | Cấp token read-only đúng repository, không mở rộng quyền toàn tổ chức |
| Config Server không kết nối RabbitMQ | Sai host, port, TLS, vhost hoặc password | Kiểm tra broker listener, certificate và credential |
| Bus không nhận event | User thiếu read/write permission hoặc client không cùng broker | Kiểm tra topology, ACL và log kết nối |
| Config Client nhận 401 | Sai client credential hoặc server security policy | Kiểm tra danh tính client và cấu hình xác thực |
| Client nhận 403 | Xác thực thành công nhưng không được phép đọc application/profile | Kiểm tra authorization rule và phạm vi cấp quyền |
| Rotation làm gián đoạn kết nối | Cập nhật secret không đồng bộ hoặc connection cũ chưa reconnect | Dùng giai đoạn overlap và rolling restart |
| Secret xuất hiện trong log | HTTP/AMQP debug hoặc Actuator quá rộng | Tắt log nhạy cảm, rotate secret và audit truy cập |

Chẩn đoán theo từng ranh giới: Git backend, broker, client-to-server và secret injection. Không thay nhiều credential cùng lúc vì sẽ khó xác định nguồn lỗi. Mỗi lần thay đổi nên có một phép kiểm tra kết nối riêng và một bản ghi xác nhận credential version đang hoạt động.

## 17. Nguyên tắc vận hành

- Dùng Git token read-only hoặc deploy key riêng cho Config Server.
- Dùng broker identity riêng theo service hoặc nhóm workload; giới hạn virtual host, topic và quyền.
- Dùng client identity riêng để gọi Config Server và authorization theo application/profile.
- Không chia sẻ một credential giữa Git, broker và HTTP client.
- Cấp secret từ secret manager hoặc secret mechanism của nền tảng; không commit giá trị thật.
- Bảo vệ mọi kết nối bằng TLS; cân nhắc mTLS hoặc workload identity khi cần.
- Xoay vòng credential theo quy trình overlap, rollout, xác minh và thu hồi.
- Audit việc đọc, thay đổi và sử dụng credential.
- Không để log, Actuator, pipeline hoặc artifact lưu lại secret.
- Khi lộ credential, thu hồi và thay thế; xóa khỏi file hoặc Git history không đủ.

Quản lý credential tốt giúp Config Server đọc đúng nguồn cấu hình, các ứng dụng trao đổi Bus an toàn và Config Client chỉ nhận dữ liệu trong phạm vi được phép. Token Git, mật khẩu broker và thông tin xác thực client cần được cấp riêng, giới hạn quyền và luân chuyển độc lập. Khi secret được đưa vào runtime an toàn, kết nối được mã hóa, log được kiểm soát và từng lần rotation được xác minh, hệ thống cấu hình tập trung có thể vận hành nhất quán mà không biến một credential dùng chung thành điểm rủi ro cho toàn bộ ứng dụng.


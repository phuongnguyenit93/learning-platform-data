# Tách cấu hình môi trường và quản lý bí mật truy cập kho

Spring Session thường cần kết nối đến một kho dữ liệu dùng chung như Redis hoặc cơ sở dữ liệu quan hệ qua JDBC. Khi ứng dụng được triển khai ở máy cá nhân, môi trường kiểm thử, staging và production, thông tin kết nối và chính sách vận hành có thể khác nhau. Nếu để địa chỉ máy chủ, mật khẩu hoặc cấu hình môi trường lẫn trong mã nguồn, việc triển khai dễ sai và thông tin nhạy cảm có nguy cơ bị lộ.

Tách cấu hình môi trường giúp cùng một gói ứng dụng chạy được ở nhiều môi trường với các giá trị phù hợp. Quản lý bí mật truy cập kho giúp chỉ cấp credential cho tiến trình cần dùng, giới hạn quyền và thay đổi credential có kiểm soát. Hai việc này đặc biệt quan trọng khi nhiều instance Spring cùng truy cập một kho session.

## 1. Phân biệt cấu hình thông thường và bí mật

Không phải mọi cấu hình đều có cùng mức độ nhạy cảm. Trước khi chọn nơi lưu, hãy phân loại dữ liệu:

| Loại cấu hình | Ví dụ | Cách quản lý phù hợp |
| --- | --- | --- |
| Cấu hình chung | Thời hạn session, tên cookie, chế độ lưu | application.yml hoặc cấu hình dùng chung |
| Cấu hình theo môi trường | Host Redis, cổng database, namespace, bật TLS | Profile hoặc biến môi trường |
| Bí mật truy cập | Mật khẩu Redis, mật khẩu database, token | Secret store, file secret được mount hoặc biến môi trường được cấp an toàn |
| Cấu hình triển khai | Số replica, giới hạn tài nguyên, địa chỉ service | Hệ thống triển khai như Kubernetes hoặc nền tảng cloud |

Địa chỉ host và tên database thường không phải mật khẩu, nhưng vẫn có thể tiết lộ cấu trúc hạ tầng. Chỉ công khai chúng trong phạm vi cần thiết. Những giá trị như mật khẩu, access token, private key và credential phải được xem là bí mật.

Không đưa bí mật vào Git, Docker image, file YAML được commit, log, thông báo lỗi hoặc tài liệu hướng dẫn. Xóa một mật khẩu khỏi phiên bản mới của file không loại bỏ bản sao đã nằm trong lịch sử Git. Nếu credential đã bị commit hoặc gửi nhầm, hãy thu hồi và tạo credential mới trước khi xử lý lịch sử lưu trữ.

## 2. Dùng cấu hình chung và Spring Profiles

Spring Boot hỗ trợ nhiều nguồn cấu hình, trong đó có application.yml, file cấu hình theo profile, biến môi trường, tham số dòng lệnh và các nguồn cấu hình được import. Các nguồn này được hợp nhất theo thứ tự ưu tiên của Spring Boot. Giá trị từ nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị mặc định trong file cấu hình.

Một cách tổ chức dễ hiểu là:

- application.yml chứa thiết lập chung, không chứa mật khẩu.
- application-local.yml chứa các giá trị phục vụ máy phát triển.
- application-test.yml chứa thiết lập kiểm thử.
- application-staging.yml và application-prod.yml chứa các giá trị riêng của môi trường triển khai.
- Credential được đưa vào từ secret store hoặc nguồn bí mật do nền tảng triển khai cung cấp.

Ví dụ application.yml cho ứng dụng dùng Spring Session Redis:

~~~yaml
spring:
  session:
    timeout: 30m
    redis:
      namespace: ${APP_SESSION_NAMESPACE:spring:session:shop}
      flush-mode: on-save
      save-mode: on-set-attribute
  data:
    redis:
      timeout: 2s
      connect-timeout: 1s
~~~

File này chứa các giá trị chung. Namespace có thể được ghi đè theo môi trường. Các replica trong cùng một môi trường phải dùng cùng namespace để cùng đọc một tập session. Mỗi môi trường nên có namespace riêng để session của máy phát triển, staging và production không trộn lẫn.

Ví dụ application-local.yml:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
~~~

Ví dụ application-prod.yml:

~~~yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
  session:
    redis:
      namespace: ${APP_SESSION_NAMESPACE:spring:session:shop:prod}
~~~

Các placeholder như ${REDIS_HOST} yêu cầu giá trị được cung cấp từ môi trường hoặc nguồn cấu hình khác. Nếu biến bắt buộc không tồn tại, ứng dụng sẽ không khởi tạo được cấu hình cần thiết. Đây là hành vi hữu ích cho production vì thiếu credential cần được phát hiện ngay lúc khởi động. Với giá trị không nhạy cảm có thể có mặc định, ví dụ cổng Redis 6379; không đặt mật khẩu giả hoặc mật khẩu production làm giá trị mặc định.

Kích hoạt profile từ bên ngoài ứng dụng, chẳng hạn:

~~~bash
SPRING_PROFILES_ACTIVE=prod
~~~

Trong PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar app.jar
~~~

Không đặt spring.profiles.active bên trong file cấu hình riêng của profile như application-prod.yml. Profile được chọn từ môi trường chạy, tham số dòng lệnh hoặc nguồn cấu hình bên ngoài. Cách này giúp cùng một artifact được triển khai ở các môi trường khác nhau mà không phải đóng gói lại.

Tên và cú pháp một số thuộc tính có thể thay đổi giữa các phiên bản Spring Boot. Hãy đối chiếu cấu hình với phiên bản Boot mà dự án đang dùng, đặc biệt khi nâng cấp phiên bản lớn. Ví dụ trên sử dụng các thuộc tính Spring Boot phổ biến cho Redis và Spring Session; không nên sao chép nguyên cấu hình của phiên bản khác mà không kiểm tra metadata cấu hình tương ứng.

## 3. Cấu hình JDBC theo môi trường

Khi dùng Spring Session JDBC, thông tin kết nối cơ sở dữ liệu thuộc cấu hình DataSource. Các instance phải kết nối đến cùng database và schema của môi trường đó để cùng truy cập dữ liệu session.

Ví dụ phần cấu hình production:

~~~yaml
spring:
  datasource:
    url: ${SESSION_DB_URL}
    username: ${SESSION_DB_USERNAME}
    password: ${SESSION_DB_PASSWORD}
    hikari:
      maximum-pool-size: 20
      connection-timeout: 3000
  session:
    jdbc:
      initialize-schema: never
      table-name: SPRING_SESSION
    timeout: 30m
~~~

SESSION_DB_URL, SESSION_DB_USERNAME và SESSION_DB_PASSWORD được cung cấp từ môi trường hoặc secret manager. Giá trị pool và timeout phải được điều chỉnh theo số replica, tải thực tế và giới hạn kết nối của database. Ví dụ maximum-pool-size: 20 không phải con số phù hợp cho mọi hệ thống; nếu có 10 replica thì cấu hình này có thể cho phép tối đa khoảng 200 kết nối từ các pool ứng dụng.

Trong production, initialize-schema: never thường phù hợp khi schema được quản lý bằng quy trình migration riêng. Tài khoản chạy ứng dụng chỉ cần quyền thao tác trên các bảng session theo nhu cầu. Tài khoản migration có thể có quyền tạo hoặc thay đổi bảng, nhưng không nên dùng tài khoản quyền cao đó làm credential thường trực của mọi instance. Với môi trường thử nghiệm dùng database mới, có thể bật khởi tạo schema theo cách phù hợp với phiên bản Spring Boot và chiến lược kiểm thử.

Không dùng chung database production cho kiểm thử tự động. Mỗi môi trường cần database hoặc schema riêng, quyền truy cập riêng và chính sách lưu trữ riêng.

## 4. Cấp bí mật cho ứng dụng

Ứng dụng cần nhận credential lúc khởi chạy hoặc từ một cơ chế quản lý bí mật được tích hợp. Một số lựa chọn thường gặp:

### Biến môi trường

Nền tảng triển khai có thể cấp REDIS_PASSWORD hoặc SPRING_DATA_REDIS_PASSWORD cho tiến trình ứng dụng. Spring Boot hỗ trợ ánh xạ tên biến môi trường sang tên thuộc tính cấu hình.

Ví dụ khi chạy cục bộ, có thể đặt biến trong terminal trước khi khởi động:

~~~bash
export SPRING_DATA_REDIS_PASSWORD='password-from-local-secret-store'
export SPRING_PROFILES_ACTIVE=local
java -jar app.jar
~~~

Không ghi lệnh có chứa mật khẩu thật vào script được commit, lịch sử terminal dùng chung hoặc log CI. Trên máy phát triển, dùng kho bí mật cá nhân hoặc công cụ quản lý biến môi trường cục bộ. File .env nếu được dùng bởi công cụ phát triển phải nằm ngoài Git và chỉ chứa credential không có quyền truy cập production.

Biến môi trường thuận tiện nhưng có thể bị lộ qua dump tiến trình, công cụ chẩn đoán, cấu hình pipeline hoặc quyền truy cập máy chủ. Hãy giới hạn người và tiến trình có thể đọc môi trường, tránh in toàn bộ environment khi debug, và ưu tiên cơ chế secret file hoặc secret manager khi nền tảng hỗ trợ.

### File secret được mount

Spring Boot hỗ trợ import cấu hình dạng config tree. Mỗi file trong thư mục được mount đại diện cho một property; tên file là tên thuộc tính, nội dung file là giá trị.

Ví dụ cấu hình production:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Nếu thư mục /run/secrets/ có file spring.data.redis.password, Spring Boot đọc nội dung file đó thành thuộc tính spring.data.redis.password. Có thể mount thêm các file như spring.data.redis.username, spring.datasource.password hoặc spring.datasource.username. Đường dẫn import ở production nên là bắt buộc để ứng dụng không âm thầm chạy mà thiếu credential; chỉ dùng tiền tố optional: khi việc thiếu thư mục thực sự được chấp nhận, chẳng hạn một cấu hình phát triển cụ thể.

Quyền đọc file phải được giới hạn cho user chạy ứng dụng. Không mount toàn bộ thư mục secret vào container không cần dùng đến chúng. Không đưa nội dung secret vào image trong lúc build; mount secret khi chạy container để có thể thay đổi credential mà không cần tạo image mới.

### Secret manager và nền tảng điều phối

Trong hệ thống lớn, có thể lấy credential từ dịch vụ quản lý bí mật của cloud hoặc công cụ như Vault. Secret manager có thể hỗ trợ phân quyền, audit, phiên bản secret và luân chuyển credential. Ứng dụng hoặc nền tảng triển khai cần được cấp danh tính riêng để đọc đúng secret mà nó cần.

Với Kubernetes, thường tách:

- ConfigMap cho cấu hình không nhạy cảm như host, port, profile và namespace.
- Secret cho mật khẩu hoặc token.

Secret của Kubernetes được biểu diễn bằng dữ liệu mã hóa Base64 trong manifest/API; Base64 không phải mã hóa bảo mật. Cần bảo vệ quyền RBAC, bật mã hóa dữ liệu Secret ở etcd theo chính sách cụm, giới hạn quyền đọc, không commit manifest chứa giá trị bí mật và tránh cấp quyền list hoặc watch rộng cho tài khoản không cần thiết. Có thể mount Secret thành file hoặc đưa vào biến môi trường tùy cách triển khai.

Không nên để toàn bộ cấu hình trong một Secret chỉ vì thao tác triển khai thuận tiện. Phân loại rõ dữ liệu giúp kiểm soát quyền và thay đổi độc lập.

## 5. Giữ cấu hình nhất quán giữa các instance

Spring Session cho phép nhiều instance truy cập cùng một repository. Để điều đó hoạt động ổn định, mọi instance trong cùng cụm phải thống nhất các giá trị có ảnh hưởng đến việc tìm và diễn giải session:

- Cùng endpoint hoặc cùng cụm Redis/database.
- Cùng namespace Redis hoặc cùng database/schema và tên bảng JDBC.
- Cùng cách cấu hình cookie, tên cookie và phạm vi cookie.
- Cùng timeout session và cách lưu tương thích.
- Cùng khả năng tuần tự hóa và phiên bản dữ liệu mà các phiên bản ứng dụng đang chạy có thể đọc.

Các replica cần cùng credential hoặc danh tính có quyền tương đương để truy cập kho session. Không để mỗi replica trỏ đến một Redis riêng do biến môi trường bị cấu hình lệch. Trong một môi trường, nên cấp cấu hình từ cùng một nguồn chuẩn, ví dụ một ConfigMap và một Secret dùng cho toàn bộ Deployment.

Giữa các môi trường, cần tách riêng endpoint, credential và namespace. Ví dụ spring:session:shop:staging và spring:session:shop:prod giúp tránh đọc nhầm dữ liệu. Namespace không phải cơ chế phân quyền; vẫn cần ACL Redis hoặc quyền database để ngăn ứng dụng staging truy cập dữ liệu production.

Một lỗi cấu hình phổ biến là tạo nhiều replica nhưng chỉ một replica nhận được password mới, hoặc một số replica dùng namespace cũ. Kết quả có thể là lỗi xác thực xen kẽ, phiên lúc tìm thấy lúc không, hoặc người dùng bị đăng xuất không nhất quán. Khi thay đổi cấu hình, triển khai theo một quy trình đồng bộ và quan sát trạng thái của toàn bộ replica.

## 6. Giới hạn quyền truy cập kho session

Credential của ứng dụng chỉ nên có quyền cần thiết cho hoạt động session:

- Với Redis, tạo user riêng và dùng ACL để giới hạn key theo namespace và các lệnh cần thiết cho Spring Session. Cần kiểm thử bộ lệnh thực tế của phiên bản thư viện đang chạy trước khi áp dụng ACL quá chặt.
- Với JDBC, tạo database user riêng cho ứng dụng và giới hạn quyền trên các bảng session. Tách tài khoản migration có quyền DDL khỏi tài khoản runtime nếu quy trình triển khai cho phép.
- Không dùng tài khoản quản trị Redis, database owner hoặc root chỉ vì cấu hình ban đầu dễ hơn.
- Không dùng chung một credential giữa production và staging, hoặc giữa các ứng dụng độc lập.

Kết nối từ ứng dụng đến kho dữ liệu nên đi qua mạng riêng và dùng TLS khi hạ tầng hỗ trợ. Khi bật TLS, cấu hình trust store hoặc CA đúng cách và xác minh chứng thư máy chủ. Không tắt kiểm tra chứng thư để xử lý nhanh lỗi kết nối.

Session ID là dữ liệu nhạy cảm vì người có được một session ID hợp lệ có thể có khả năng sử dụng phiên của người khác. Không ghi cookie hoặc session ID vào log. Giới hạn quyền truy cập Redis và database, mã hóa đường truyền, bảo vệ backup và cân nhắc mã hóa dữ liệu session nếu yêu cầu bảo mật của hệ thống đòi hỏi. Cookie HttpOnly, Secure và SameSite hỗ trợ bảo vệ phía trình duyệt nhưng không thay thế việc bảo vệ kho session.

## 7. Luân chuyển credential an toàn

Mật khẩu có thể cần thay đổi định kỳ hoặc ngay khi nghi ngờ bị lộ. Luân chuyển credential trong hệ thống nhiều instance cần phối hợp giữa kho dữ liệu và ứng dụng.

Một quy trình an toàn thường gồm các bước:

1. Tạo credential mới với quyền tương đương và phạm vi tối thiểu cần thiết.
2. Nếu kho dữ liệu hỗ trợ nhiều credential đồng thời, giữ credential cũ hoạt động trong giai đoạn chuyển đổi.
3. Cập nhật Secret hoặc secret manager để cấp credential mới cho ứng dụng.
4. Triển khai lại hoặc refresh cấu hình theo cơ chế được hỗ trợ; không giả định mọi bean kết nối Redis hoặc connection pool tự nhận giá trị mới chỉ vì secret file đã đổi.
5. Xác nhận tất cả replica kết nối thành công, đọc và ghi session được, và không còn instance dùng credential cũ.
6. Thu hồi credential cũ sau khi xác nhận quá trình chuyển đổi hoàn tất.

Với JDBC, cần chú ý connection pool có thể giữ kết nối được xác thực bằng credential cũ. Cập nhật file cấu hình không nhất thiết làm mới các kết nối đang tồn tại. Với Redis, client cũng có thể cần tạo lại kết nối sau khi credential thay đổi. Cách thực hiện phụ thuộc thư viện client, nền tảng triển khai và cách ứng dụng quản lý vòng đời kết nối.

Nếu không thể duy trì hai credential cùng lúc, cần có kế hoạch bảo trì hoặc chuyển đổi có kiểm soát để tránh toàn bộ replica mất quyền truy cập đồng thời. Luôn thử quy trình luân chuyển ở staging và có phương án quay lại credential hợp lệ nếu bước triển khai mới thất bại. Khi credential đã bị lộ, ưu tiên thu hồi và giảm thời gian bị phơi nhiễm thay vì kéo dài thời gian chuyển đổi.

## 8. Kiểm thử cấu hình và xử lý lỗi

Kiểm thử cần chứng minh rằng ứng dụng nhận đúng cấu hình theo môi trường và nhiều instance dùng cùng kho session. Có thể tổ chức kiểm thử theo các lớp:

| Kiểm thử | Điều cần xác nhận |
| --- | --- |
| Kiểm thử cấu hình local | Ứng dụng dùng endpoint local và không cần credential production |
| Kiểm thử profile | Profile được chọn từ môi trường triển khai và giá trị ghi đè đúng |
| Kiểm thử thiếu secret | Ứng dụng thất bại rõ ràng khi thiếu credential bắt buộc |
| Kiểm thử sai credential | Lỗi xác thực được phát hiện và ghi log an toàn |
| Kiểm thử hai instance | Hai instance cùng đọc và cập nhật session trong một kho dùng chung |
| Kiểm thử phân tách môi trường | Staging không thể truy cập dữ liệu session production |
| Kiểm thử luân chuyển | Các replica chuyển sang credential mới mà không mất khả năng truy cập session ngoài dự kiến |

Với Redis hoặc database chạy bằng container cho kiểm thử tích hợp, nên tạo kho dữ liệu dùng riêng cho mỗi lần chạy và xóa sau khi kết thúc. Không dùng dữ liệu production để kiểm thử. Kiểm tra ít nhất luồng tạo session ở instance A và đọc lại bằng instance B với cùng cookie.

Khi kho session không truy cập được, Spring Session có thể không tải hoặc lưu được session trong quá trình xử lý yêu cầu. Cần đặt connect timeout, read timeout và connection pool hợp lý; theo dõi lỗi xác thực, số kết nối, độ trễ và tình trạng kho dữ liệu. Không tự động chuyển sang session trong bộ nhớ cục bộ khi Redis/JDBC lỗi nếu chưa thiết kế rõ cách đồng bộ, vì các instance có thể tạo ra những phiên khác nhau.

Thông báo lỗi và log nên cho biết loại lỗi, môi trường, instance và đích dịch vụ ở mức cần thiết để điều tra. Không in password, token, nội dung secret, cookie hoặc session ID. Các endpoint quản trị như Actuator env và configprops có thể chứa thông tin cấu hình; nếu bật, cần giới hạn quyền truy cập và bảo đảm giá trị nhạy cảm được che theo cấu hình phù hợp. Không mở endpoint chẩn đoán cấu hình ra Internet công khai.

## 9. Ví dụ triển khai trên Kubernetes

Một cách phân tách thường gặp là đưa host và namespace vào ConfigMap, credential vào Secret, sau đó mount hoặc inject vào Deployment. Ví dụ rút gọn sau minh họa cách tham chiếu; giá trị Secret thực tế phải được tạo từ secret manager hoặc quy trình bảo mật của cụm.

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: shop-session-config
data:
  SPRING_PROFILES_ACTIVE: "prod"
  REDIS_HOST: "redis-primary.internal"
  REDIS_PORT: "6379"
  APP_SESSION_NAMESPACE: "spring:session:shop:prod"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shop-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: shop-api
  template:
    metadata:
      labels:
        app: shop-api
    spec:
      containers:
        - name: app
          image: registry.example/shop-api:1.0.0
          envFrom:
            - configMapRef:
                name: shop-session-config
          env:
            - name: REDIS_USERNAME
              valueFrom:
                secretKeyRef:
                  name: shop-session-credentials
                  key: username
            - name: REDIS_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: shop-session-credentials
                  key: password
~~~

Trong ví dụ này, application-prod.yml dùng các placeholder ${REDIS_HOST}, ${REDIS_PORT}, ${REDIS_USERNAME} và ${REDIS_PASSWORD}. ConfigMap chứa cấu hình không nhạy cảm; Secret chứa username và password. Manifest minh họa cách tham chiếu Secret, không chứa giá trị bí mật thật. Trong quy trình triển khai thực tế, hạn chế quyền đọc Secret và cân nhắc mount dưới dạng file nếu muốn tránh đưa credential vào environment của tiến trình.

Khi thay đổi Secret được inject dưới dạng biến môi trường, các container đang chạy thường không tự nhận giá trị mới; cần tạo rollout để tiến trình mới nhận cấu hình mới. Nếu mount Secret thành file, nền tảng có thể cập nhật nội dung mount, nhưng ứng dụng vẫn phải hỗ trợ đọc lại và tái tạo kết nối. Không coi việc file thay đổi là bằng chứng credential mới đã được sử dụng.

## 10. Danh sách kiểm tra trước khi đưa vào production

- [ ] Profile production được chọn từ cấu hình triển khai.
- [ ] Không có mật khẩu hoặc token trong Git, image, log hay file cấu hình được commit.
- [ ] Host, namespace, timeout và TLS được cấu hình theo môi trường.
- [ ] Tất cả replica dùng cùng repository, namespace và cấu hình tương thích.
- [ ] Staging và production có credential, endpoint và vùng dữ liệu riêng.
- [ ] Tài khoản Redis/database có quyền tối thiểu cần thiết.
- [ ] Secret được cấp qua nguồn quản lý phù hợp, có phân quyền và audit.
- [ ] Kết nối được bảo vệ bằng TLS khi yêu cầu của hạ tầng đặt ra.
- [ ] Thiếu hoặc sai credential được phát hiện mà không làm lộ giá trị bí mật.
- [ ] Quy trình luân chuyển credential đã được thử nghiệm.
- [ ] Log và endpoint quản trị không làm lộ password, cookie hoặc session ID.
- [ ] Có cảnh báo cho lỗi kết nối, xác thực, độ trễ và dung lượng kho session.

Tách cấu hình môi trường giúp một artifact Spring chạy nhất quán ở nhiều nơi; quản lý secret đúng cách giới hạn rủi ro khi ứng dụng kết nối đến Redis hoặc JDBC. Với Spring Session, cần đặc biệt giữ cho các replica trong cùng môi trường dùng chung một kho và namespace, đồng thời tách credential và dữ liệu giữa các môi trường. Khi cấu hình, cấp quyền và luân chuyển secret đều được quản lý có chủ đích, session có thể được chia sẻ ổn định trong cụm mà không biến credential của kho dữ liệu thành một phần của mã nguồn.

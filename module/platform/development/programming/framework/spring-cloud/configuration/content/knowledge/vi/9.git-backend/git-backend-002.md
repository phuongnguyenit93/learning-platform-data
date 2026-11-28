# Xác thực kho riêng bằng token, khóa SSH và cấu hình bí mật bên ngoài

Spring Cloud Config Server thường đọc cấu hình từ một Git repository riêng tư. Để clone và fetch repository, Config Server phải xác thực với Git provider bằng một danh tính có quyền đọc. Thông tin này thuộc về kết nối giữa Config Server và Git; các ứng dụng Config Client không cần biết token hoặc khóa SSH dùng để đọc repository.

Có hai cách phổ biến để xác thực Git từ xa: HTTPS với username và access token, hoặc SSH với cặp khóa công khai/riêng. Dù chọn cách nào, thông tin xác thực phải được cấp cho Config Server từ một nguồn bí mật bên ngoài, chẳng hạn secret manager, secret của nền tảng triển khai hoặc file được mount an toàn. Không đưa token, mật khẩu hay private key vào Git repository cấu hình hoặc vào file application.yml được commit.

Bài học này tập trung vào xác thực kho riêng và vòng đời của thông tin xác thực trong môi trường vận hành. Nội dung cũng phân biệt bí mật dùng để truy cập Git với bí mật mà ứng dụng cuối cần đọc từ Config Server.

Sau bài học, bạn có thể:

- Chọn HTTPS token hoặc SSH deploy key cho Config Server.
- Cấu hình Git URI và credentials bằng các thuộc tính Spring Cloud Config Server.
- Nạp bí mật từ environment hoặc secret store mà không commit giá trị nhạy cảm.
- Giữ xác thực SSH an toàn bằng host key verification.
- Thiết kế quyền đọc tối thiểu, luân chuyển token/khóa và chẩn đoán lỗi xác thực.

## 1. Ai cần xác thực với Git?

Trong kiến trúc Spring Cloud Config có hai kết nối riêng:

1. **Config Server → Git provider:** Config Server clone hoặc fetch repository riêng để lấy file cấu hình. Đây là nơi cần Git token hoặc SSH private key.
2. **Config Client → Config Server:** ứng dụng Spring Boot gọi API của Config Server để nhận cấu hình. Nếu Config Server được bảo vệ, client cần cơ chế xác thực với Config Server, chẳng hạn HTTP Basic hoặc OAuth2 theo thiết kế triển khai.

Git credential không được chuyển tiếp đến Config Client. Client chỉ cần quyền đọc API cấu hình mà nó được phép truy cập. Không đặt Git token trong file cấu hình mà Config Server phân phối cho các ứng dụng.

~~~mermaid
flowchart LR
    G["Git provider / private repository"] <-->|"HTTPS token hoặc SSH key"| S["Spring Cloud Config Server"]
    S -->|"Environment API qua TLS và xác thực riêng"| C["Spring Boot Config Client"]
    V["Secret manager / platform secret"] -->|"Cấp credential runtime"| S
~~~

Ví dụ, repository có URI:

~~~text
https://git.example.com/platform/config-repo.git
~~~

Config Server cần token để đọc repository. Một ứng dụng như order-service chỉ gọi Config Server theo application/profile/label; nó không cần biết token Git là gì.

## 2. Chuẩn bị quyền truy cập tối thiểu

Nên tạo một danh tính riêng cho Config Server, ví dụ service account hoặc bot account chuyên đọc cấu hình. Không dùng token cá nhân của lập trình viên làm credential lâu dài cho production.

Danh tính đó chỉ cần quyền đọc repository. Tên quyền cụ thể phụ thuộc Git provider, nhưng nguyên tắc là:

- Chỉ cấp quyền đọc nội dung repository cần thiết.
- Giới hạn token vào đúng repository hoặc nhóm repository liên quan nếu provider hỗ trợ.
- Đặt thời hạn hết hạn và lịch luân chuyển.
- Không cấp quyền push, tạo branch, quản lý thành viên hoặc quản trị repository nếu Config Server chỉ clone/fetch.
- Dùng credential riêng cho development, staging và production khi các môi trường có ranh giới quyền khác nhau.

Nếu provider hỗ trợ deploy token hoặc deploy key chỉ đọc, đây thường là lựa chọn phù hợp cho một dịch vụ chỉ cần lấy cấu hình. Hãy kiểm tra chính sách của provider để bảo đảm quyền thực tế đúng với mục tiêu read-only.

## 3. HTTPS với username và access token

Với HTTPS, Spring Cloud Config Server hỗ trợ HTTP Basic authentication đến Git repository bằng hai thuộc tính riêng: username và password. Trong môi trường dùng personal access token hoặc deploy token, token thường được truyền ở trường password; username phải theo yêu cầu của Git provider.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          username: ${CONFIG_GIT_USERNAME}
          password: ${CONFIG_GIT_TOKEN}
          clone-on-start: true
~~~

Các giá trị CONFIG_GIT_USERNAME và CONFIG_GIT_TOKEN được cấp lúc chạy từ secret store hoặc môi trường triển khai. Trong repository ứng dụng chỉ lưu tên biến tham chiếu, không lưu giá trị token thực.

Không nhúng token trực tiếp vào URI như:

~~~text
https://username:token@git.example.com/platform/config-repo.git
~~~

Credential trong URL dễ xuất hiện trong log, exception, lịch sử lệnh, dashboard giám sát hoặc thông tin chẩn đoán. Tài liệu Spring Cloud Config hướng dẫn khai báo username và password thành thuộc tính riêng thay vì đặt trong URI.

Với Git provider dùng token, cần xác minh định dạng username theo loại token. Một số provider yêu cầu username của service account; một số loại deploy token dùng username do provider cấp. Không giả định mọi provider đều chấp nhận cùng một username.

### Cấu hình qua biến môi trường

Spring Boot hỗ trợ relaxed binding từ biến môi trường. Các thuộc tính Git tương ứng có thể được cấp bằng tên biến:

~~~text
SPRING_CLOUD_CONFIG_SERVER_GIT_URI
SPRING_CLOUD_CONFIG_SERVER_GIT_USERNAME
SPRING_CLOUD_CONFIG_SERVER_GIT_PASSWORD
~~~

Ví dụ, nền tảng triển khai inject CONFIG_GIT_TOKEN vào biến SPRING_CLOUD_CONFIG_SERVER_GIT_PASSWORD trước khi khởi chạy Config Server. Cần bảo đảm biến được cấp trong môi trường tiến trình, giới hạn quyền xem cấu hình triển khai và tránh in environment ra log.

### Cấu hình qua secret file

Một lựa chọn khác là mount secret thành file và dùng Spring Boot Config Data import kiểu configtree. Ví dụ:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          username: config-reader
          clone-on-start: true
~~~

Thư mục /run/secrets có thể chứa file với tên trùng property key:

~~~text
/run/secrets/
  spring.cloud.config.server.git.password
~~~

Nội dung file là token. Config tree đưa nội dung file thành property tương ứng để Spring Cloud Config Server sử dụng. Cách này hữu ích khi nền tảng container hoặc secret manager đã hỗ trợ mount secret dưới dạng file. Quyền đọc file phải giới hạn cho user chạy Config Server; không bake file secret vào image và không commit nó vào repository.

Với secret bắt buộc ở production, không nên dùng tiền tố optional cho configtree import nếu việc thiếu secret phải làm ứng dụng dừng khởi động.

## 4. SSH với deploy key

SSH sử dụng một cặp khóa:

- **Public key:** đăng ký tại Git provider dưới dạng deploy key hoặc khóa của service account, với quyền read-only nếu chỉ cần clone/fetch.
- **Private key:** chỉ đặt ở Config Server hoặc secret store cấp credential cho Config Server. Không commit private key, không gửi cho Config Client và không chia sẻ giữa người dùng.

Git URI có dạng SSH, ví dụ:

~~~text
git@git.example.com:platform/config-repo.git
~~~

Spring Cloud Config dùng JGit để truy cập repository. Theo mặc định, JGit có thể đọc SSH configuration trên filesystem của server, chẳng hạn ~/.ssh/known_hosts và cấu hình SSH hệ thống. Cách này có thể dùng trong máy chủ được quản lý ổn định. Trong container hoặc môi trường cloud, filesystem thường được quản lý khác; khi đó có thể cấu hình SSH bằng các thuộc tính của Spring Cloud Config.

Ví dụ cấu hình property-based SSH:

~~~yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: git@git.example.com:platform/config-repo.git
          ignore-local-ssh-settings: true
          private-key: ${CONFIG_GIT_PRIVATE_KEY}
          host-key: ${CONFIG_GIT_HOST_KEY}
          host-key-algorithm: ssh-ed25519
          strict-host-key-checking: true
          clone-on-start: true
~~~

Trong ví dụ:

- ignore-local-ssh-settings bật cấu hình SSH thông qua property thay vì lấy cấu hình SSH local.
- private-key chứa nội dung private key hợp lệ.
- host-key và host-key-algorithm xác định host key của Git server để kiểm tra danh tính máy chủ.
- strict-host-key-checking giữ việc xác minh host key ở trạng thái bật.
- clone-on-start yêu cầu Config Server clone repository lúc khởi động để phát hiện sớm URI hoặc credential không hợp lệ.

Khi ignore-local-ssh-settings=true và strict-host-key-checking=true, Config Server phải có host-key hoặc known-hosts-file để đối chiếu host key của Git server. Nếu không có thông tin để xác minh, Config Server sẽ không thể xác thực an toàn host key và có thể từ chối khởi động. Không đặt strict-host-key-checking=false chỉ để làm cho kết nối chạy được; tùy chọn đó chấp nhận host key bất kỳ và mở ra nguy cơ máy chủ trung gian giả mạo Git server.

Nếu dùng known-hosts-file, file known_hosts phải chứa khóa máy chủ tương ứng với hostname trong Git URI. Kiểm tra fingerprint của Git server qua kênh tin cậy trước khi đưa host key vào file. Đừng tự lấy một khóa chưa xác minh từ kết nối đang bị nghi ngờ.

### Định dạng private key

JGit và phiên bản Spring Cloud Config đang dùng có thể có yêu cầu cụ thể về định dạng private key. Tài liệu hiện hành có lưu ý trường hợp RSA key phải ở định dạng PEM mà JGit hỗ trợ; một private key bắt đầu bằng OPENSSH PRIVATE KEY có thể không được phiên bản thư viện tương ứng chấp nhận. Khi gặp lỗi private key invalid, hãy kiểm tra loại key, định dạng và phiên bản JGit/Spring Cloud Config trước khi thay đổi cấu hình.

Không đưa nội dung private key vào tài liệu, ticket hoặc log. Nếu private key có passphrase, hãy kiểm tra thuộc tính hỗ trợ của phiên bản Spring Cloud Config đang dùng và cấp passphrase từ secret store theo cùng nguyên tắc.

## 5. Nạp SSH key từ secret bên ngoài

Private key thường là nội dung nhiều dòng. Truyền trực tiếp qua biến môi trường có thể làm mất newline hoặc bị hệ thống triển khai escape sai. Nếu nền tảng hỗ trợ mount secret file, hãy ưu tiên cách cấp file hoặc configtree.

Ví dụ:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  cloud:
    config:
      server:
        git:
          uri: git@git.example.com:platform/config-repo.git
          ignore-local-ssh-settings: true
          host-key-algorithm: ssh-ed25519
          strict-host-key-checking: true
          clone-on-start: true
~~~

Thư mục secret có thể chứa:

~~~text
/run/secrets/
  spring.cloud.config.server.git.private-key
  spring.cloud.config.server.git.host-key
~~~

Nếu dùng host-key thay vì known-hosts-file, cần cung cấp đúng host key và thuật toán tương ứng. Nếu dùng known-hosts-file, cấu hình đường dẫn đến file đó và bảo đảm file chứa host key đã được xác minh. Private key phải có quyền file hạn chế, chỉ user chạy Config Server đọc được.

Một cách khác là nền tảng quản lý bí mật inject nội dung private key vào CONFIG_GIT_PRIVATE_KEY và host key vào CONFIG_GIT_HOST_KEY. Khi dùng cách này, phải bảo toàn toàn bộ newline của key; kiểm thử khởi động trong cùng cách đóng gói và triển khai thực tế.

## 6. Không nhầm Git credential với secret của ứng dụng

Có hai loại bí mật khác nhau trong hệ thống:

| Loại bí mật | Ai sử dụng? | Nơi quản lý |
|---|---|---|
| Git token hoặc SSH private key | Config Server để clone/fetch repository | Secret store của Config Server |
| Database password, API token của nghiệp vụ | Ứng dụng Config Client | Secret manager hoặc cơ chế mã hóa/phân phối phù hợp cho ứng dụng |
| Credential để gọi Config Server | Config Client | Secret store hoặc danh tính workload của client |
| Host key của Git server | Config Server để xác minh máy chủ SSH | Cấu hình SSH đáng tin cậy của Config Server |

Spring Cloud Config có thể mã hóa các giá trị cấu hình ứng dụng, ví dụ giá trị ciphertext có tiền tố {cipher}, để repository chứa dữ liệu đã mã hóa thay cho secret dạng rõ. Cơ chế này phục vụ bí mật được phân phối đến ứng dụng, chẳng hạn database password. Nó không thay thế việc bảo vệ Git token hoặc private key mà Config Server cần để đọc repository.

Khóa mã hóa/giải mã của Config Server cũng cần được quản lý riêng. Không lưu khóa giải mã cạnh ciphertext trong cùng Git repository. Nếu dùng secret manager, cần giới hạn ai có thể đọc, mã hóa khi lưu và khi truyền, đồng thời audit các lần truy cập.

## 7. Luân chuyển token và khóa SSH

Credential có thời hạn hoặc có thể bị lộ cần có quy trình thay thế rõ ràng. Không đợi đến khi token hết hạn mới phát hiện Config Server không thể đọc repository.

Một quy trình luân chuyển an toàn:

1. Tạo credential mới cho đúng service account, deploy token hoặc deploy key; cấp quyền đọc tối thiểu.
2. Đưa credential mới vào secret store dưới một phiên bản mới, giữ lại credential cũ trong thời gian chuyển đổi có kiểm soát.
3. Cập nhật secret được Config Server sử dụng và triển khai/restart các instance cần nhận giá trị mới. Biến môi trường và file secret đã được inject vào process không nhất thiết tự thay đổi khi secret store cập nhật.
4. Kiểm tra từng Config Server instance có thể clone hoặc fetch repository bằng credential mới. Nếu có nhiều replica, xác nhận tất cả đều nhận đúng secret version.
5. Sau khi các instance hoạt động ổn định, thu hồi token hoặc xóa deploy key cũ tại Git provider.
6. Ghi lại thời điểm thay đổi, owner, phạm vi quyền và thời hạn credential mới.

Nếu token hoặc private key bị lộ, thu hồi credential bị lộ ngay, kiểm tra log/audit để xác định phạm vi ảnh hưởng, tạo credential thay thế và xác minh Config Server đã kết nối lại. Không chỉ xóa secret khỏi file hoặc Git commit hiện tại; lịch sử Git, build log, artifact và log triển khai có thể vẫn chứa giá trị cũ.

Với SSH deploy key, có thể tạo cặp khóa mới và đăng ký public key mới trước khi thay private key trong secret store. Sau khi xác nhận kết nối bằng key mới, xóa public key cũ khỏi Git provider. Không chia sẻ một private key dùng chung cho nhiều hệ thống không liên quan.

## 8. Kiểm tra kết nối và xử lý lỗi

Có thể bật clone-on-start trong giai đoạn triển khai để Config Server thử clone repository ngay khi khởi động. Nếu URI, token hoặc SSH key sai, lỗi xuất hiện sớm thay vì đợi đến request cấu hình đầu tiên. Trong môi trường cần sẵn sàng cao, hãy kết hợp kiểm tra health của Git backend và giám sát lần fetch gần nhất.

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| HTTPS trả 401 | Username hoặc token sai, hết hạn hoặc sai loại token | Xác nhận username theo provider, secret version và thời hạn |
| HTTPS trả 403 | Danh tính hợp lệ nhưng thiếu quyền đọc repository | Kiểm tra repository scope, deploy token permission và policy |
| SSH báo publickey denied | Public key chưa đăng ký, private key không khớp hoặc user SSH sai | Đối chiếu URI, deploy key và fingerprint public key |
| SSH báo private key invalid | Key sai định dạng hoặc nội dung bị mất newline | Kiểm tra định dạng được JGit hỗ trợ và cách mount secret |
| SSH host key verification failed | Host key thay đổi hoặc known_hosts/hostKey sai | Xác minh fingerprint qua kênh tin cậy rồi cập nhật host key |
| Kết nối timeout hoặc DNS lỗi | Mạng, DNS, firewall, proxy hoặc route không đúng | Kiểm tra đường mạng từ chính Config Server đến Git provider |
| Config Server khởi động được nhưng request đầu tiên lỗi | Repository được clone lazy khi có request đầu tiên | Bật clone-on-start để phát hiện lỗi sớm |
| Một replica đọc được, replica khác không | Secret hoặc quyền mạng giữa các instance khác nhau | So sánh secret version, network policy và log từng instance |

Không bật log debug chứa HTTP Authorization header, token, private key hoặc toàn bộ environment để chẩn đoán. Khi cần chia sẻ log, hãy che giá trị nhạy cảm trước. Có thể log URI đã loại credentials, mã lỗi, tên repository, thời điểm fetch và danh tính service account ở mức không tiết lộ bí mật.

## 9. Checklist cấu hình production

Trước khi đưa Config Server kết nối repository riêng vào production, hãy xác nhận:

- Git URI dùng HTTPS hoặc SSH đúng endpoint; URI không chứa username/token.
- Credential thuộc service account hoặc deploy identity riêng, chỉ có quyền đọc cần thiết.
- Token có hạn sử dụng và có lịch rotation; SSH private key được giữ trong secret store.
- SSH host key verification được bật; host key hoặc known_hosts đã được xác minh.
- TLS certificate của Git server được kiểm tra; không tắt SSL validation để né lỗi certificate.
- Secret được inject lúc chạy, không nằm trong Git, image hoặc build artifact.
- Config Server có quyền đọc secret nhưng Config Client không có quyền đọc Git credential.
- Clone-on-start hoặc health check phù hợp giúp phát hiện lỗi repository sớm.
- Các instance Config Server dùng cùng revision secret và có quyền mạng nhất quán.
- Quy trình rotation, thu hồi và xử lý credential bị lộ đã được kiểm thử.

## 10. Tự kiểm tra

1. Vì sao Git token cần được cấp cho Config Server mà không cần gửi đến Config Client?
2. Khi dùng HTTPS, vì sao nên khai báo username và password riêng thay vì nhúng token vào Git URI?
3. Deploy key read-only khác SSH key cá nhân của lập trình viên ở mục đích và quyền sở hữu như thế nào?
4. Khi bật ignore-local-ssh-settings và strict-host-key-checking, Config Server cần hostKey hoặc knownHostsFile để làm gì?
5. Vì sao không nên tắt strict host key checking để khắc phục lỗi kết nối SSH?
6. Nếu cập nhật token trong secret manager, vì sao cần kiểm tra và triển khai lại các Config Server instance?
7. {cipher} trong repository cấu hình bảo vệ loại secret nào, và vì sao nó không thay thế Git credential?
8. Khi Config Server trả lỗi 403 từ Git provider, cần kiểm tra quyền nào trước khi tạo token mới?

Hãy triển khai thử trong môi trường development với một repository riêng chỉ chứa cấu hình giả lập. Tạo một service identity có quyền đọc, cấu hình Config Server lần lượt bằng HTTPS token và SSH deploy key, rồi bật clone-on-start để xác nhận mỗi cách xác thực hoạt động. Sau đó thay secret bằng một phiên bản mới, triển khai lại Config Server, xác minh fetch thành công và thu hồi credential cũ. Tuyệt đối không dùng token hoặc private key thật trong bài thực hành hoặc repository học tập.

## Tài liệu tham khảo

- [Spring Cloud Config — Git Backend: Authentication and SSH configuration](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html)
- [Spring Cloud Config — Server](https://docs.spring.io/spring-cloud-config/reference/server.html)
- [Spring Boot — Externalized Configuration and Configuration Trees](https://docs.spring.io/spring-boot/reference/features/external-config.html)


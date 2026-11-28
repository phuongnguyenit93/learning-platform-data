# Kết nối Git cục bộ, HTTPS và SSH

## 1. Git backend trong Spring Cloud Config

Spring Cloud Config Server cần một nguồn lưu trữ để đọc các file cấu hình mà Config Client yêu cầu. Git là lựa chọn phổ biến vì lưu được lịch sử thay đổi, hỗ trợ branch/tag/commit và kết hợp tốt với quy trình pull request, review, kiểm tra tự động và rollback.

Trong Config Server, thuộc tính `spring.cloud.config.server.git.uri` xác định repository mà server sẽ đọc. Cách viết URI phụ thuộc nơi repository nằm và giao thức truy cập:

- `file://` dùng repository nằm trên hệ thống tệp mà tiến trình Config Server có thể truy cập.
- `https://` dùng repository từ xa qua HTTPS, thường xác thực bằng username và token/password do Git server cấp.
- `ssh://` dùng repository từ xa qua SSH, thường xác thực bằng private key.

Config Server dùng JGit để làm việc với Git. Vì vậy, quyền truy cập phải được cấp cho tài khoản hệ điều hành hoặc container đang chạy Config Server, và cấu hình xác thực phải được cung cấp cho tiến trình đó. Việc developer clone được repository trên máy cá nhân không chứng minh rằng Config Server cũng có quyền đọc.

## 2. Kết nối repository cục bộ bằng file URI

Repository cục bộ phù hợp cho học tập, thử nghiệm hoặc một môi trường mà repository đã được mount sẵn vào máy chủ chạy Config Server. URI phải trỏ đến một Git repository hợp lệ trên chính filesystem mà tiến trình server nhìn thấy.

Ví dụ trên Linux:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: file:///opt/config-repo
          default-label: main
          clone-on-start: true
```

Ví dụ đường dẫn trên Windows có thể biểu diễn dưới dạng URI như `file:///C:/config-repo`; cần kiểm tra cách runtime và JGit diễn giải đường dẫn trên hệ điều hành đang triển khai. Với container Linux, đường dẫn phải là đường dẫn bên trong container, không phải đường dẫn trên máy host nếu chưa mount vào container.

Một số điểm cần kiểm tra:

- Đường dẫn là tuyệt đối và đúng cú pháp URI `file:///...`.
- Thư mục đã được khởi tạo thành Git repository và có commit/branch mà client yêu cầu.
- Tài khoản chạy Config Server có quyền đọc repository và các thư mục cha cần thiết.
- Nếu repository được mount từ volume, volume đã mount trước khi Config Server khởi động.
- `default-label` hoặc label client gửi phải tồn tại trong repository đó.

Ví dụ một repository thử nghiệm có thể được tạo và commit bằng Git CLI:

```bash
mkdir -p /opt/config-repo
cd /opt/config-repo
git init -b main
cat > application.yml <<'EOF'
platform:
  connect-timeout: 3s
EOF
git add application.yml
git commit -m "Add initial shared configuration"
```

Lệnh trên chỉ minh họa việc tạo repository. Trong môi trường thực tế, cần thiết lập danh tính Git cho tài khoản thực hiện commit và tuân theo quy trình quản lý mã nguồn của tổ chức.

### Local repository khác thư mục clone cache

Không nhầm `uri: file:///...` với thuộc tính `basedir`:

| Thuộc tính | Ý nghĩa |
|---|---|
| `spring.cloud.config.server.git.uri` | Địa chỉ repository nguồn mà Config Server đọc. Với `file://`, đó là repository trên filesystem; với HTTPS/SSH, đó là repository từ xa. |
| `spring.cloud.config.server.git.basedir` | Thư mục local nơi Config Server lưu bản clone/cache của repository từ xa. |

Ví dụ cấu hình `basedir` cho remote repository:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: ${CONFIG_REPO_URI}
          basedir: ${CONFIG_GIT_BASEDIR:/var/cache/config-server}
```

Thư mục `basedir` phải tồn tại hoặc có thể được tạo và phải cho phép tài khoản Config Server ghi. Với nhiều repository, server có thể tạo các thư mục clone con tương ứng. `basedir` không phải là đường dẫn mà client gửi lên và cũng không thay thế URI của repository nguồn.

Local backend thuận tiện khi phát triển, nhưng có giới hạn vận hành: repository chỉ sẵn sàng trên máy/volume mà Config Server truy cập được. Nếu chạy nhiều instance, mỗi instance có thể nhìn thấy filesystem hoặc bản repository khác nhau. Muốn chia sẻ dữ liệu giữa instance, phải thiết kế volume dùng chung hoặc đồng bộ Git rõ ràng; một thư mục local trên một container không tự được chia sẻ cho các container khác.

## 3. Kết nối repository từ xa bằng HTTPS

HTTPS thường phù hợp khi Git server cung cấp URL HTTPS và cơ chế token hoặc deploy credential. Ví dụ:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          username: ${CONFIG_GIT_USERNAME}
          password: ${CONFIG_GIT_TOKEN}
          default-label: main
          clone-on-start: true
          basedir: ${CONFIG_GIT_BASEDIR:/var/cache/config-server}
```

Trong cấu hình này:

- `uri` là URL HTTPS của repository.
- `username` là tên người dùng hoặc tên deploy identity theo yêu cầu của Git provider.
- `password` chứa token, deploy token hoặc credential tương ứng; nhiều Git provider không chấp nhận mật khẩu tài khoản thông thường cho thao tác Git qua HTTPS.
- `basedir` là nơi lưu bản clone local của repository từ xa.

Với repository public, có thể không cần `username` và `password`. Với repository private, hãy dùng token có phạm vi quyền tối thiểu, ưu tiên chỉ đọc. Không dùng token cá nhân có quyền quản trị nếu Config Server chỉ cần clone cấu hình.

Thông tin xác thực nên được cấp từ secret manager, secret của nền tảng container hoặc biến môi trường được quản lý. Không ghi token trực tiếp vào `application.yml`, Dockerfile, file compose được commit hoặc Git repository cấu hình mà chính Config Server phục vụ.

### TLS và chứng thư HTTPS

Nếu Git server dùng chứng thư do CA nội bộ cấp, JVM chạy Config Server phải tin cậy CA đó. Cấu hình truststore hoặc trust material theo chính sách của nền tảng Java đang triển khai. Không tắt kiểm tra chứng thư để khắc phục lỗi TLS; điều đó làm mất khả năng xác minh máy chủ và có thể khiến token bị gửi đến endpoint giả mạo.

Khi HTTPS thất bại, cần phân biệt lỗi DNS/kết nối, lỗi TLS/chứng thư, lỗi xác thực và lỗi quyền truy cập repository. Các lỗi này có nguyên nhân và cách xử lý khác nhau.

## 4. Kết nối repository từ xa bằng SSH

SSH thường được dùng khi tổ chức quản lý repository bằng deploy key hoặc SSH key. URI có dạng `ssh://` và xác định user, host, port (nếu khác mặc định) cùng đường dẫn repository.

Ví dụ cấu hình:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: ssh://git@git.example.com:22/platform/config-repo.git
          default-label: main
          clone-on-start: true
          private-key: ${CONFIG_GIT_PRIVATE_KEY}
          passphrase: ${CONFIG_GIT_KEY_PASSPHRASE:}
          strict-host-key-checking: true
          known-hosts-file: ${CONFIG_GIT_KNOWN_HOSTS_FILE}
```

`private-key` là nội dung private key mà JGit sử dụng để xác thực; không phải mặc nhiên là đường dẫn đến file key. Hãy kiểm tra cách bind secret và hỗ trợ key format của phiên bản Spring Cloud Config/JGit đang dùng. Nếu dùng cơ chế SSH mặc định của môi trường, phải bảo đảm key, SSH config và file `known_hosts` thuộc đúng tài khoản hệ điều hành chạy server.

`passphrase` cần thiết nếu private key được bảo vệ bằng passphrase. Nên lưu cả key và passphrase trong secret manager, hạn chế quyền đọc và không ghi chúng vào log.

### Xác minh host key

SSH cần xác minh máy chủ Git mà client đang kết nối. `known_hosts` lưu host key đã được xác minh. Khi bật strict host key checking, JGit phải có thông tin host key hợp lệ để đối chiếu. Hãy lấy fingerprint từ kênh đáng tin cậy của tổ chức hoặc nhà cung cấp Git, xác minh trước khi thêm vào `known_hosts`.

Không tắt host key checking chỉ để bỏ qua lỗi kết nối trong production. Nếu host key thay đổi hợp lệ do Git server thay máy hoặc luân chuyển key, hãy xác minh fingerprint mới qua kênh tin cậy rồi cập nhật `known_hosts` theo quy trình. Nếu host key thay đổi bất ngờ, cần xem đó là tín hiệu cần điều tra.

Các thuộc tính SSH chi tiết như `strict-host-key-checking`, `known-hosts-file`, `host-key`, `host-key-algorithm`, `private-key` và `ignore-local-ssh-settings` có thể khác nhau về hỗ trợ hoặc hành vi theo release train. Đối chiếu tài liệu đúng phiên bản đang triển khai trước khi áp dụng cấu hình nâng cao.

## 5. Chọn HTTPS hay SSH?

| Tiêu chí | HTTPS | SSH |
|---|---|---|
| Cách xác thực phổ biến | Username + token/deploy credential | Private key và có thể có passphrase |
| Quản lý secret | Token lưu trong secret manager | Private key, passphrase và `known_hosts` |
| Xác minh máy chủ | TLS certificate validation | SSH host key verification |
| Phù hợp khi | Git provider cấp token qua HTTPS, hạ tầng đã quản lý CA | Tổ chức chuẩn hóa deploy key hoặc SSH key |
| Điểm cần chú ý | Token scope, expiry, TLS trust | Key format, quyền file, host key và known_hosts |

Không có giao thức nào an toàn chỉ vì được chọn. An toàn phụ thuộc cách cấp credential, xác minh server, phân quyền repository, luân chuyển secret và giám sát truy cập. Hãy chọn giao thức phù hợp với tiêu chuẩn vận hành sẵn có của tổ chức.

## 6. Cấu hình Git backend đầy đủ cho một môi trường triển khai

Một cấu hình server có thể lấy các giá trị nhạy cảm từ môi trường:

```yaml
server:
  port: 8888

spring:
  application:
    name: config-server
  cloud:
    config:
      server:
        git:
          uri: ${CONFIG_REPO_URI}
          default-label: ${CONFIG_GIT_DEFAULT_LABEL:main}
          basedir: ${CONFIG_GIT_BASEDIR:/var/cache/config-server}
          clone-on-start: true
          search-paths:
            - '{application}'
            - common
```

Các biến như `CONFIG_REPO_URI`, `CONFIG_GIT_DEFAULT_LABEL` và `CONFIG_GIT_BASEDIR` được cấp khi triển khai. Với HTTPS, bổ sung username/token. Với SSH, bổ sung private key, passphrase khi cần và cấu hình host key verification. Không nên đặt đồng thời nhiều loại credential nếu không dùng đến; giữ cấu hình tối thiểu giúp giảm nhầm lẫn.

`clone-on-start: true` khiến Config Server thử truy cập repository khi khởi động. Cách này giúp phát hiện sớm lỗi URI, quyền đọc hoặc branch mặc định. Trong môi trường production, cần cân nhắc tác động khi Git tạm thời không sẵn sàng: server có thể không khởi động được nếu backend là điều kiện bắt buộc. Chính sách retry, timeout, readiness và phương án khôi phục cần được thiết kế cùng với cách triển khai.

## 7. Nguyên tắc bảo vệ credential và repository

Git repository cấu hình thường chứa thông tin nội bộ. Quyền đọc repository cũng là một quyền nhạy cảm vì client có thể nhận các giá trị mà Config Server trả về.

Áp dụng các nguyên tắc sau:

- Tạo service account hoặc deploy key riêng cho Config Server, chỉ cấp quyền đọc repository cần thiết.
- Dùng token có scope tối thiểu và thời hạn phù hợp; có quy trình gia hạn/luân chuyển trước khi hết hạn.
- Lưu token, private key và passphrase trong secret manager hoặc secret store của nền tảng.
- Không commit credential vào Git repository, file cấu hình mẫu, log, pipeline output hoặc image container.
- Giới hạn quyền đọc thư mục/volume local nếu dùng `file://`; tài khoản server chỉ cần quyền tối thiểu.
- Bật TLS certificate validation cho HTTPS và SSH host key verification cho SSH.
- Theo dõi lỗi xác thực, thay đổi host key, truy cập repository và hoạt động cấp/thu hồi credential.
- Khi credential bị lộ, thu hồi hoặc rotate tại Git provider, cập nhật secret của server và xác minh lại quyền truy cập.

Không chia sẻ cùng một token quản trị giữa Config Server và các developer. Tách credential theo môi trường (dev/staging/prod) giúp thu hồi và điều tra sự cố có phạm vi rõ hơn.

## 8. Kiểm tra kết nối sau khi cấu hình

Nên kiểm tra theo từng lớp thay vì chỉ nhìn trạng thái ứng dụng đã khởi động:

1. **URI**: xác nhận scheme là `file://`, `https://` hay `ssh://` đúng với cách truy cập đã chọn.
2. **Filesystem/network**: server nhìn thấy đường dẫn local hoặc kết nối được đến hostname/port của Git provider.
3. **Authentication**: token hoặc key hợp lệ và chưa hết hạn.
4. **Authorization**: service account có quyền đọc repository đúng.
5. **Host verification**: TLS certificate hoặc SSH host key được xác minh thành công.
6. **Git reference**: branch/tag/commit được chọn tồn tại trong repository.
7. **Config lookup**: application, profile và label trả về đúng property source.

Ví dụ gọi endpoint kiểm tra:

```text
GET http://localhost:8888/order-service/dev/main
```

Phản hồi `Environment` cho biết Config Server có tìm thấy file cấu hình theo application/profile/label hay không. Nếu kết nối Git thành công nhưng phản hồi thiếu property, hãy kiểm tra tên file và `search-paths`; không tiếp tục thay đổi credential khi lỗi thực chất nằm ở cấu trúc repository.

Khi kiểm tra repository remote, có thể dùng Git CLI dưới đúng tài khoản triển khai để kiểm tra DNS, mạng và quyền truy cập. Tuy nhiên, Git CLI và JGit có thể dùng cấu hình credential/SSH khác nhau; kết quả CLI thành công chưa chứng minh hoàn toàn Config Server đã được cấu hình đúng. Cần xác nhận thêm log của Config Server và endpoint thực tế.

## 9. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `file://` không mở được repository | URI sai, đường dẫn tương đối, volume chưa mount hoặc tài khoản server không có quyền. | Dùng URI tuyệt đối, kiểm tra filesystem trong đúng container/host và quyền đọc. |
| HTTPS trả về 401 | Token sai, hết hạn, username không đúng yêu cầu provider hoặc credential chưa được truyền vào process. | Xác minh token, scope, expiry và cách inject secret. |
| HTTPS trả về 403 | Danh tính xác thực được nhưng không có quyền đọc repository hoặc branch. | Cấp quyền read-only đúng repository. |
| Lỗi SSL handshake | JVM không tin cậy CA, chứng thư hết hạn hoặc hostname không khớp. | Cập nhật truststore/chứng thư và xác minh hostname. |
| SSH báo `Permission denied (publickey)` | Private key không khớp deploy key, key format không được hỗ trợ hoặc service account không đọc được key. | Kiểm tra key, passphrase, quyền secret và danh tính Git. |
| SSH báo host key verification failed | Host key chưa có trong `known_hosts` hoặc fingerprint đã thay đổi. | Xác minh fingerprint qua kênh tin cậy và cập nhật known_hosts. |
| Server không tìm thấy label | Branch/tag/commit không tồn tại hoặc default label sai. | Kiểm tra Git refs trong đúng repository và cấu hình label. |
| Clone thành công nhưng endpoint thiếu cấu hình | File sai tên, profile/application không khớp hoặc `search-paths` sai. | Gọi endpoint theo application/profile/label và kiểm tra property sources. |
| Lỗi khi server khởi động | `clone-on-start` phát hiện URI, auth, host verification hoặc branch không hợp lệ. | Đọc log nguyên nhân đầu tiên, kiểm tra từng lớp kết nối. |

Không đưa token, private key, passphrase hoặc toàn bộ URL có credential vào log khi chia sẻ lỗi. Hãy che dữ liệu nhạy cảm trước khi gửi log cho nhóm hỗ trợ.

## 10. Bài thực hành

### Bước 1: Dùng repository local

Tạo Git repository local có branch `main` và file `application.yml`. Cấu hình Config Server với URI `file:///...`, khởi động server và gọi endpoint cho một application/profile.

**Kết quả cần đạt:** phân biệt được đường dẫn repository local với thư mục clone cache và xác nhận quyền filesystem của server.

### Bước 2: Chuyển sang HTTPS

Tạo repository private trên Git provider, cấp token read-only và đưa username/token vào môi trường triển khai. Cấu hình URI HTTPS, khởi động lại server và kiểm tra endpoint.

**Kết quả cần đạt:** xác nhận token được cấp đúng, TLS được kiểm tra và Config Server đọc được repository private.

### Bước 3: Chuyển sang SSH

Tạo deploy key chỉ đọc, đăng ký public key ở Git provider, cấp private key qua secret store và cấu hình `known_hosts` sau khi xác minh fingerprint. Dùng URI `ssh://` và kiểm tra endpoint.

**Kết quả cần đạt:** xác nhận private key, passphrase (nếu có) và host key verification hoạt động.

### Bước 4: Kiểm tra lỗi có chủ đích

Thử dùng label không tồn tại, token sai trong môi trường thử nghiệm hoặc quyền filesystem bị giới hạn. Đọc log để phân biệt lỗi URI, authentication, authorization, host verification và lỗi tìm file.

**Kết quả cần đạt:** xác định đúng tầng gây lỗi và cách xử lý tương ứng.

### Bước 5: Chuẩn hóa triển khai

Đưa credential ra khỏi file cấu hình, giới hạn quyền service account, đặt `basedir` có thể ghi, bật `clone-on-start` khi phù hợp và ghi lại label/revision đã kiểm thử.

**Kết quả cần đạt:** có cấu hình Git backend có thể triển khai lặp lại và kiểm toán.

## 11. Tự kiểm tra

1. `spring.cloud.config.server.git.uri` khác `basedir` như thế nào?
2. Khi nào nên dùng repository local qua `file://`?
3. Vì sao repository local trong container phải được mount vào filesystem mà Config Server nhìn thấy?
4. Khi dùng HTTPS, `username` và `password` thường chứa thông tin gì với repository private?
5. `private-key` trong cấu hình SSH là nội dung key hay đường dẫn file?
6. `known_hosts` bảo vệ điều gì và vì sao cần xác minh fingerprint trước khi thêm host key?
7. Vì sao Git CLI truy cập thành công chưa chứng minh JGit trong Config Server đã cấu hình đúng?
8. Cần kiểm tra những lớp nào khi Config Server không đọc được repository?

Khi hoàn thành bài thực hành, người học có thể cấu hình Config Server đọc Git local, HTTPS hoặc SSH; quản lý credential an toàn; phân biệt repository nguồn với clone cache; và chẩn đoán sự cố theo đúng tầng kết nối.

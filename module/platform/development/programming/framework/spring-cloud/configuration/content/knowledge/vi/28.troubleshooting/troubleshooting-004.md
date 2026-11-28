# Lỗi clone hoặc fetch Git do token, SSH, proxy hay quyền thư mục

## 1. Hiểu đúng vị trí xảy ra lỗi

Khi dùng Git làm backend, Spring Cloud Config Server phải lấy repository từ xa và duy trì một working copy cục bộ. Việc clone/fetch này do Config Server thực hiện trong tiến trình Java, thông qua JGit. Nó không phải thao tác Git mà Config Client thực hiện trên máy của client.

Luồng cơ bản:

```mermaid
flowchart LR
    C[Config Client] -->|GET /application/profile/label| S[Config Server]
    S --> R{Working copy đã có?}
    R -->|Chưa| CL[Clone remote Git]
    R -->|Có| F[Fetch remote Git]
    CL --> D[Checkout label và đọc file cấu hình]
    F --> D
    D --> E[Trả Environment response]
    G[(Git provider)] <--> CL
    G <--> F
    S --> FS[(basedir / local filesystem)]
    CL --> FS
    F --> FS
```

Một lỗi clone/fetch có thể đến từ nhiều lớp:

- URI hoặc repository không đúng.
- Token/username hết hạn, thiếu scope hoặc không có quyền đọc.
- SSH private key không khớp, chưa được cấp quyền hoặc host key chưa được tin cậy.
- DNS, firewall, proxy hoặc TLS ngăn kết nối.
- Tài khoản chạy Config Server không đọc được key/known_hosts hoặc không ghi được thư mục làm việc.
- Disk đầy, volume chỉ đọc, home directory không tồn tại hoặc JGit không ghi được cấu hình local.
- Remote đã truy cập được nhưng branch/tag/label không tồn tại hoặc working copy cục bộ bị lệch.

Điều quan trọng là tìm đúng lớp lỗi trước khi thay credential, tắt kiểm tra TLS hoặc xóa working copy.

## 2. Phân biệt clone-on-start và lazy clone

Mặc định, Config Server clone remote repository khi có request cấu hình đầu tiên. Đây là *lazy clone*. Vì vậy, process Config Server có thể khởi động thành công dù Git URI sai, token hết hạn hoặc repository không truy cập được; lỗi chỉ xuất hiện khi client đầu tiên yêu cầu cấu hình.

Có thể yêu cầu clone ngay lúc server khởi động:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.internal/platform/config-repo.git
          clone-on-start: true
```

`clone-on-start: true` giúp phát hiện sớm lỗi URI, quyền và kết nối khi startup. Với nhiều repository, có thể bật theo repository tương ứng trong cấu hình `repos`.

| Chế độ | Khi nào phát hiện lỗi? | Tác động vận hành |
|---|---|---|
| Lazy clone (mặc định) | Khi request đầu tiên cần repository đó. | Server có thể `UP` nhưng endpoint cấu hình thất bại. |
| `clone-on-start: true` | Trong startup của Config Server. | Deployment thất bại sớm nếu repository bắt buộc không thể clone. |

Chọn chế độ dựa trên yêu cầu sẵn sàng. Với repository thiết yếu, clone-on-start giúp deployment không đưa server lên trạng thái tưởng như khỏe nhưng chưa đọc được cấu hình. Với repository chỉ được một số ứng dụng sử dụng, có thể cân nhắc lazy clone và kiểm tra health theo repository.

## 3. Kiểm tra đúng repository và URI trước khi kiểm tra credential

Đọc cấu hình runtime của Config Server và xác nhận:

- `spring.cloud.config.server.git.uri` trỏ đến đúng clone URL, không phải URL trang web của repository.
- Đúng giao thức: `https://` hoặc SSH như `git@host:group/repo.git`.
- Đúng organization/group, project và tên repository.
- Repository còn tồn tại và service account có quyền đọc.
- Nếu dùng `repos` hoặc pattern matching, application/profile request có khớp repository được chọn không.
- Nếu dùng placeholder `{application}` hoặc `{profile}`, giá trị được thay vào tạo thành URI hợp lệ.
- Nếu dùng `search-paths`, kiểm tra đường dẫn thư mục cấu hình sau khi clone; đây là lỗi tìm file sau clone, không phải lỗi xác thực Git.

Ví dụ URI HTTPS:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.internal/platform/config-repo.git
```

Ví dụ URI SSH:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: git@git.example.internal:platform/config-repo.git
```

Một số Git provider trả `404 Not Found` khi repository không tồn tại **hoặc** khi danh tính hiện tại không có quyền nhìn thấy repository. Không kết luận URI sai chỉ từ 404; đối chiếu quyền đọc bằng tài khoản dịch vụ.

## 4. HTTPS: kiểm tra username, token và quyền đọc repository

Spring Cloud Config Server hỗ trợ HTTP Basic authentication với hai thuộc tính riêng `username` và `password`:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.internal/platform/config-repo.git
          username: ${CONFIG_GIT_USERNAME}
          password: ${CONFIG_GIT_TOKEN}
```

Đối với Git provider dùng Personal Access Token (PAT), deploy token hoặc app password, cách đặt username/password phụ thuộc provider. Nhiều provider yêu cầu username tài khoản/bot và PAT ở vị trí password; một số provider cấp token có username riêng. Dùng đúng hướng dẫn của provider, không giả định mọi token đều dùng cùng một quy tắc.

Kiểm tra các điểm sau:

1. Token chưa hết hạn, chưa bị revoke và chưa bị rotate mà Config Server vẫn dùng giá trị cũ.
2. Token có quyền đọc repository/content; quyền quản trị hoặc ghi không cần thiết.
3. Token được cấp cho đúng organization/project/repository.
4. Nếu organization bật SSO/SAML, token đã được authorize cho organization đó.
5. Account/bot chưa bị khóa và repository không bị chuyển tên hoặc chuyển namespace.
6. Giá trị token được nạp vào tiến trình Config Server thực sự là bản mới; kiểm tra secret reference/version, không in token ra log.

Không nhúng credential vào URI dạng `https://user:token@host/repo.git`. URL có thể xuất hiện trong log, exception, process arguments hoặc Actuator metadata. Giữ URI sạch và cấp credential qua secret manager/environment injection.

### Phân biệt lỗi xác thực và lỗi quyền

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `401 Unauthorized` | Username/token thiếu, sai, hết hạn hoặc không được provider chấp nhận. | Xác minh credential và cách provider yêu cầu truyền PAT. |
| `403 Forbidden` | Đã xác định danh tính nhưng token thiếu quyền hoặc policy chặn. | Cấp đúng quyền read repository, kiểm tra SSO/organization policy. |
| `404 Not Found` | Sai URI hoặc provider ẩn repository không được phép truy cập. | Kiểm tra clone URL và quyền bằng đúng service account. |
| `Authentication is required` | JGit không nhận được credential hợp lệ. | Kiểm tra username/password binding và secret injection. |
| `not authorized`/`access denied` | Token không có quyền đọc repository hoặc branch bị bảo vệ theo policy. | Kiểm tra repo permission và policy phía provider. |

## 5. Không nhầm Git CLI credential helper với credential của JGit

Spring Cloud Config Server sử dụng JGit để truy cập Git. JGit chạy bên trong JVM và không nhất thiết dùng Git CLI, Git Credential Manager, `credential.helper`, shell profile hoặc thông tin đăng nhập của người đang mở terminal.

Do đó, lệnh `git clone` thành công trên máy developer chưa chứng minh Config Server clone được. Có thể hai môi trường khác nhau về:

- OS user/service account.
- `HOME`, thư mục `.ssh`, `.gitconfig` và credential store.
- Java trust store và proxy properties.
- File private key, known_hosts và quyền đọc file.
- Environment variables và secret version.
- Network route, DNS và firewall.

Hãy thử kiểm tra dưới đúng identity chạy Config Server. Lệnh Git CLI chỉ là phép thử bổ sung cho URI, DNS và quyền cơ bản; nó không mô phỏng hoàn toàn JGit transport hoặc SSH configuration của Spring Cloud Config.

Có thể dùng `git ls-remote` để xác nhận một danh tính có thể liệt kê refs từ remote:

```bash
git ls-remote https://git.example.internal/platform/config-repo.git HEAD
git ls-remote git@git.example.internal:platform/config-repo.git HEAD
```

Chỉ chạy lệnh tương ứng với giao thức đang cấu hình và dưới service identity. Với HTTPS, để credential helper đã được phê duyệt hoặc prompt an toàn cấp credential; không đưa PAT vào URL. Nếu `git ls-remote` thành công nhưng Config Server vẫn lỗi, tiếp tục kiểm tra JGit properties, Java trust store, SSH mode, proxy và filesystem.

## 6. SSH: private key, deploy key và known_hosts

Với SSH URI, JGit mặc định có thể sử dụng cấu hình SSH local như `~/.ssh/known_hosts` và `/etc/ssh/ssh_config`. Những file này được đọc theo môi trường của tiến trình Config Server, không phải theo tài khoản developer đang đăng nhập.

Ví dụ:

```text
git@git.example.internal:platform/config-repo.git
```

Kiểm tra:

- Public key tương ứng với private key đã được thêm vào Git provider dưới dạng deploy key hoặc key của service account.
- Deploy key được gắn đúng repository và được phép đọc.
- Private key nằm trong filesystem mà Config Server có thể đọc.
- Private key không bị lỗi định dạng, xuống dòng hoặc encoding khi mount từ secret.
- Hostname trong URI khớp entry trong `known_hosts`.
- SSH host key là fingerprint chính thức của Git provider.
- Nếu Git server dùng cổng SSH khác mặc định, entry known_hosts phải thể hiện đúng hostname/port.

### Cấu hình SSH bằng file hệ thống

Nếu dùng cấu hình local mặc định, bảo đảm tài khoản dịch vụ có:

```text
<service-home>/.ssh/id_ed25519
<service-home>/.ssh/known_hosts
```

Trên Linux, quyền phổ biến là thư mục `.ssh` chỉ chủ sở hữu truy cập (`700`) và private key chỉ chủ sở hữu đọc/ghi (`600`). Trên Windows, dùng ACL NTFS để giới hạn quyền đọc private key cho đúng service identity. Không copy private key vào home của tài khoản developer rồi giả định Windows/Linux service account sẽ dùng được.

### Cấu hình SSH bằng Spring properties

Trong môi trường container hoặc cloud, có thể cấu hình SSH trực tiếp bằng property. Bật `ignore-local-ssh-settings` ở cấp `spring.cloud.config.server.git`:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: git@git.example.internal:platform/config-repo.git
          ignore-local-ssh-settings: true
          private-key: ${CONFIG_GIT_PRIVATE_KEY}
          known-hosts-file: /etc/config-server/ssh/known_hosts
          strict-host-key-checking: true
```

`private-key` phải chứa private key hợp lệ. `known-hosts-file` phải chứa host key đã xác minh. Trong chế độ property-based, `strict-host-key-checking` mặc định là `true`; cần cung cấp `host-key` hoặc `known-hosts-file` để xác minh máy chủ.

Có thể cấu hình trực tiếp `host-key` cùng `host-key-algorithm` thay cho file known_hosts. Nếu đặt `host-key`, phải đặt thuật toán tương ứng.

**Không đặt `strict-host-key-checking: false` để chữa lỗi host key.** Giá trị `false` vô hiệu hóa việc xác minh host key hoàn toàn; kết nối có thể chấp nhận máy chủ giả mạo qua tấn công trung gian hoặc DNS spoofing. Hãy cập nhật known_hosts bằng fingerprint lấy từ kênh tin cậy.

`ignore-local-ssh-settings` là cấu hình cấp cao nhất của Git backend, không đặt bên trong một repository entry trong `repos`.

## 7. Chẩn đoán lỗi SSH thường gặp

| Thông báo | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `Permission denied (publickey)` | Private key không khớp, không được nạp hoặc public key chưa được cấp cho repo. | Kiểm tra key pair, deploy key, identity và file path. |
| `Host key verification failed` | Thiếu/sai entry known_hosts hoặc host key đã thay đổi. | Lấy fingerprint chính thức, xác minh rồi cập nhật known_hosts. |
| `No authentication methods available` | JGit không tìm thấy phương thức/credential SSH phù hợp. | Kiểm tra private key, cấu hình property/file và `preferred-authentications` nếu cần. |
| `invalid privatekey`/parse error | Key sai định dạng, bị cắt dòng hoặc encoding không đúng. | Mount file nguyên vẹn hoặc truyền multiline secret đúng cách. |
| `Connection timed out` trên cổng SSH | Firewall, route, DNS hoặc cổng SSH không truy cập được. | Kiểm tra egress, DNS, port và SSH bastion/proxy theo kiến trúc. |
| `Could not resolve hostname` | DNS sai hoặc hostname không được phân giải từ container/host. | Kiểm tra DNS resolver và hostname trong URI. |

Có thể dùng OpenSSH để kiểm tra kết nối từ cùng service identity:

```bash
ssh -T -o BatchMode=yes git@git.example.internal
```

Để kiểm tra verbose trong môi trường được kiểm soát:

```bash
ssh -vvv -T -o BatchMode=yes git@git.example.internal
```

Lệnh trên kiểm tra OpenSSH, không chứng minh JGit đang dùng cùng key/configuration. Nếu Spring Cloud Config dùng `ignore-local-ssh-settings: true`, phải kiểm tra các property `private-key`, `known-hosts-file` và `host-key` mà JVM thực sự nhận.

## 8. Proxy: cấu hình cho đúng protocol và từng repository

Config Server có thể truy cập Git backend qua HTTP hoặc HTTPS proxy. Cấu hình proxy thuộc từng repository; nếu dùng composite/multiple repository, phải cấu hình proxy cho mỗi backend cần đi qua proxy.

Ví dụ HTTPS proxy:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.internal/platform/config-repo.git
          proxy:
            https:
              host: proxy.corp.internal
              port: 3128
              username: ${GIT_PROXY_USERNAME}
              password: ${GIT_PROXY_PASSWORD}
              non-proxy-hosts: localhost|127.*|*.corp.internal
```

Các thuộc tính gồm `host`, `port`, `username`, `password` và `nonProxyHosts`. Có thể cấu hình `proxy.http` và `proxy.https` riêng nếu mạng dùng proxy khác nhau cho hai giao thức.

Kiểm tra theo thứ tự:

1. Config Server có phân giải được hostname proxy không?
2. Container/host có kết nối được cổng proxy không?
3. Proxy có yêu cầu authentication không? Lỗi `407 Proxy Authentication Required` thường chỉ ra credential proxy thiếu hoặc sai.
4. `nonProxyHosts` có vô tình đưa Git host vào danh sách bypass hoặc ngược lại không?
5. Proxy có cho phép HTTP CONNECT đến Git host và cổng HTTPS/SSH cần dùng không?
6. Proxy có thực hiện TLS inspection và thay certificate bằng CA nội bộ không?

Proxy của HTTP/HTTPS backend không tự động cấu hình đường đi SSH. Với SSH qua bastion hoặc proxy command, phải kiểm tra khả năng và cách cấu hình của SSH transport đang dùng; đừng giả định `proxy.https` áp dụng cho SSH.

## 9. TLS và certificate khi clone qua HTTPS

Các lỗi như `SSLHandshakeException`, `PKIX path building failed`, `unable to find valid certification path`, `certificate expired` hoặc hostname mismatch thường là vấn đề trust/certificate, không phải token.

Kiểm tra:

- Certificate Git server còn hạn và có đầy đủ intermediate chain.
- Hostname trong URI nằm trong Subject Alternative Name của certificate.
- JVM chạy Config Server tin cậy CA gốc/intermediate cần thiết.
- Nếu proxy TLS inspection, CA nội bộ đã được thêm vào trust store đúng của JVM.
- Đồng hồ host/container chính xác; clock skew có thể làm certificate bị coi là chưa hiệu lực hoặc hết hạn.
- Config Server đang dùng đúng trust store sau khi restart/rollout.

Không dùng `skip-ssl-validation: true` làm giải pháp production cho lỗi certificate. Thuộc tính này tắt kiểm tra certificate của Git server và khiến kết nối dễ bị giả mạo. Hãy cài CA đúng vào trust store và giữ validation bật.

## 10. Kiểm tra DNS, route, firewall và timeout

Nếu log báo connect timeout, connection refused hoặc unknown host, tách các kiểm tra mạng:

| Lớp | Câu hỏi | Dấu hiệu lỗi |
|---|---|---|
| DNS | Hostname Git/proxy có phân giải đúng IP từ runtime không? | `UnknownHostException`, `Could not resolve hostname`. |
| Routing | Container/host có route đến IP đích không? | Timeout, unreachable network. |
| Firewall/egress | Cổng HTTPS/SSH có được phép outbound không? | Connection timeout hoặc reset. |
| Proxy | Có cần proxy để ra ngoài không? | Timeout trực tiếp, 407 hoặc CONNECT bị từ chối. |
| Server listener | Git provider đang lắng nghe đúng cổng không? | Connection refused. |
| Timeout JGit | Thời gian kết nối có quá ngắn so với mạng không? | Timeout dù đường mạng cuối cùng có thể hoạt động. |

Config Server có thuộc tính `spring.cloud.config.server.git.timeout`, tính bằng giây, để cấu hình thời gian chờ lấy HTTP hoặc SSH connection. Giá trị mặc định trong tài liệu hiện hành là 5 giây.

Ví dụ:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          timeout: 15
```

Chỉ tăng timeout sau khi đã xác nhận route/proxy hoạt động và có lý do mạng chậm. Timeout dài không sửa được DNS sai, firewall chặn hoặc credential lỗi; nó chỉ làm request thất bại muộn hơn.

## 11. Quyền thư mục: basedir phải ghi được bởi service account

Với remote Git backend, Config Server clone repository vào local working copy. `spring.cloud.config.server.git.basedir` xác định nơi lưu bản clone. Nếu không cấu hình, server dùng thư mục tạm của hệ điều hành với prefix `config-repo-`; một số hệ điều hành hoặc container có thể dọn thư mục tạm, gây mất working copy.

Nên cấu hình một thư mục ổn định, nằm trên volume có quyền ghi:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          basedir: /var/lib/config-server/git-cache
```

Đảm bảo:

- Parent directory tồn tại và service user có quyền tạo thư mục con.
- Service user có quyền đọc, ghi và traverse (`x`) trên các thư mục cha.
- Filesystem không bị mount read-only.
- Còn đủ dung lượng và inode.
- Không có tiến trình khác dọn hoặc sửa working copy khi Config Server đang chạy.
- Không dùng thư mục world-writable hoặc chia sẻ không kiểm soát giữa các ứng dụng.
- Với nhiều Config Server instance, mỗi instance có working copy riêng hoặc có thiết kế shared filesystem được hỗ trợ; không để nhiều process cùng xóa/sửa một clone không có cơ chế phối hợp.

Trên Linux có thể kiểm tra:

```bash
id configsvc
namei -l /var/lib/config-server/git-cache
df -h /var/lib/config-server
df -i /var/lib/config-server
```

Kiểm tra khả năng ghi bằng đúng service account, không chỉ bằng tài khoản root:

```bash
sudo -u configsvc test -w /var/lib/config-server
```

Trên Windows, kiểm tra NTFS ACL của thư mục basedir và các thư mục cha, xác nhận identity chạy Windows Service có quyền Modify/Create files. Trên Kubernetes, kiểm tra `runAsUser`, `runAsGroup`, `fsGroup`, volume mount và `readOnlyRootFilesystem`.

## 12. Home directory và JGit config trong container

Một lỗi có thể xuất hiện dù `basedir` đã ghi được: JGit cần ghi cấu hình local trong home/XDG config directory. Ví dụ log:

```text
Cannot save config file 'FileBasedConfig[/.config/jgit/config]'
java.io.IOException: Creating directories for /.config/jgit failed
```

Đường dẫn `/.config/jgit` cho thấy tiến trình có thể không có home directory ghi được hoặc `XDG_CONFIG_HOME` đang trỏ đến vị trí không phù hợp.

Có hai cách xử lý theo tài liệu Spring Cloud Config:

1. Cấp cho service user một home directory có quyền ghi trong container.
2. Đặt `XDG_CONFIG_HOME` trỏ đến thư mục mà Java process có quyền ghi.

Ví dụ Dockerfile/container environment:

```dockerfile
ENV HOME=/home/configsvc
ENV XDG_CONFIG_HOME=/home/configsvc/.config
```

Đảm bảo thư mục thực sự tồn tại và owner/group khớp với UID/GID runtime. Không chỉ đặt biến môi trường mà bỏ qua quyền filesystem.

## 13. Phân biệt basedir permission với local file repository permission

Hai loại URI có cách sử dụng filesystem khác nhau:

| URI | Cách Config Server sử dụng | Quyền cần thiết |
|---|---|---|
| Remote HTTPS/SSH URI | Clone/fetch vào local `basedir`. | Quyền ghi basedir, home/XDG và đọc credential/key. |
| `file:/path/to/repo` | Mở trực tiếp repository local, không clone như remote Git. | Quyền traverse/read repository và `.git`; không cần quyền ghi remote repository cho thao tác đọc thông thường. |

Với `file:` URI, dùng đường dẫn cụ thể, không dùng symlink ở repository root hoặc `.git` để chuyển hướng sang vị trí khác. Spring Cloud Config hiện hành kiểm tra symlink/path nhằm giảm rủi ro filesystem và TOCTOU. Nếu dùng symlink trong một cấu hình cũ từng hoạt động, phiên bản mới có thể từ chối; hãy chuyển sang đường dẫn thực thay vì tìm cách bỏ qua kiểm tra.

## 14. Cache local, refresh-rate và tình huống fetch thất bại

Sau khi clone thành công, Config Server giữ local working copy. Nếu remote Git tạm thời unavailable, server có thể tiếp tục trả cấu hình từ bản local miễn là branch và file được yêu cầu còn tồn tại.

Thuộc tính `spring.cloud.config.server.git.refresh-rate` điều khiển tần suất fetch, tính bằng giây:

| Giá trị | Hành vi |
|---:|---|
| `0` (mặc định) | Fetch cập nhật mỗi khi có request cấu hình. |
| Số dương | Chỉ fetch khi đã qua khoảng thời gian refresh tối thiểu. |
| Số âm | Không refresh remote. |

Khi remote unavailable sau lần clone thành công, server tiếp tục phục vụ revision local cuối cùng. Điều này giúp availability nhưng có thể trả cấu hình stale. Khi server restart trong lúc remote vẫn down và lazy clone chưa có local copy, request cấu hình có thể thất bại.

Nếu local working copy bị thay đổi ngoài ý muốn hoặc dirty, `force-pull: true` có thể buộc server bỏ local modifications và reset working copy theo remote ở mỗi lần fetch. Chỉ bật khi chính sách yêu cầu local cache luôn phản ánh remote; thay đổi local sẽ bị loại bỏ.

Không xóa basedir khi Config Server đang xử lý request. Nếu cần dựng lại working copy bị hỏng:

1. Đưa instance khỏi traffic hoặc dừng Config Server theo kế hoạch.
2. Xác nhận remote Git hoạt động và credential hợp lệ.
3. Sao lưu log và metadata cần điều tra; không sao lưu secret ra nơi không được bảo vệ.
4. Xóa đúng thư mục clone/cache của repository bị lỗi theo quy trình vận hành.
5. Khởi động lại hoặc kích hoạt clone lại, rồi kiểm tra revision/label trả về.

## 15. Quy trình chẩn đoán có thứ tự

Khi nhận lỗi clone/fetch, đi theo các bước sau để tránh thay đổi nhiều biến cùng lúc.

### Bước 1: Xác định request và repository được chọn

Ghi nhận application, profile, label, thời điểm và URI repository mà Config Server đã chọn. Nếu dùng multiple repositories, kiểm tra pattern có chọn nhầm repository không.

### Bước 2: Đọc exception gốc trong log Config Server

Tìm nguyên nhân sâu nhất như HTTP 401/403/404, `UnknownHostException`, `ConnectException`, `SSLHandshakeException`, SSH host key error hoặc `AccessDeniedException`. Không chỉ dựa vào HTTP 500 trả về cho Config Client.

### Bước 3: Kiểm tra network từ runtime

Kiểm tra DNS, route, egress, proxy, port và TLS từ đúng host/container. Test từ laptop developer không đủ để kết luận runtime Config Server có cùng đường mạng.

### Bước 4: Kiểm tra credential theo giao thức

- HTTPS: username/token, scope, expiration, SSO và repository permission.
- SSH: private key, deploy key, host key, known_hosts, service home và SSH config mode.

### Bước 5: Kiểm tra filesystem

Kiểm tra basedir, home, XDG config path, UID/GID, quyền đọc/ghi, disk, inode, mount flags và file key.

### Bước 6: Kiểm tra clone/fetch state

Phân biệt chưa clone, fetch remote thất bại, local copy dirty, label checkout thất bại hoặc branch không tồn tại. Kiểm tra `refresh-rate` và `force-pull` nếu server đang dùng cache.

### Bước 7: Khắc phục một nguyên nhân rồi thử lại

Thay token, sửa known_hosts, cập nhật proxy/CA hoặc quyền thư mục theo nguyên nhân đã xác định. Dùng `clone-on-start` trong môi trường kiểm thử hoặc cửa sổ triển khai để xác nhận clone mới thành công.

## 16. Bảng triệu chứng và cách xử lý nhanh

| Triệu chứng/log | Lớp lỗi | Hướng xử lý ưu tiên |
|---|---|---|
| `Authentication is required` | HTTPS credential | Kiểm tra username/token, expiry và secret injection. |
| HTTP `401` | Token không hợp lệ | Cấp token mới, xác nhận provider-specific auth format. |
| HTTP `403` | Thiếu quyền | Cấp read-only repository permission, kiểm tra SSO/policy. |
| HTTP `404` | URI hoặc quyền bị ẩn | Xác minh clone URL và quyền bằng service account. |
| `Permission denied (publickey)` | SSH key | Kiểm tra private key, deploy key và identity. |
| `Host key verification failed` | SSH trust | Xác minh fingerprint và cập nhật known_hosts đúng hostname/port. |
| `PKIX path building failed` | TLS trust | Cài CA/intermediate vào trust store của JVM. |
| `No subject alternative DNS name` | Hostname mismatch | Dùng hostname đúng SAN hoặc cấp certificate phù hợp. |
| `407 Proxy Authentication Required` | Proxy auth | Cấu hình username/password của proxy. |
| `Connection timed out` | Network/proxy/firewall | Kiểm tra DNS, route, egress và timeout. |
| `AccessDeniedException` trên basedir | Filesystem permission | Sửa quyền cho service UID/GID trên parent và basedir. |
| `No space left on device` | Disk/inode | Giải phóng hoặc mở rộng volume, kiểm tra inode. |
| `/.config/jgit/config` không ghi được | HOME/XDG | Cấp writable HOME hoặc đặt `XDG_CONFIG_HOME`. |
| Clone được nhưng thiếu property | Checkout/search path/config naming | Kiểm tra label, branch, `search-paths` và tên file. |
| Fetch lỗi nhưng endpoint vẫn trả 200 | Local working copy/cache | Kiểm tra revision và `refresh-rate`; response có thể đang dùng dữ liệu cũ. |

## 17. Cấu hình mẫu cho HTTPS production

Ví dụ tổng hợp cho Git HTTPS qua proxy, có thư mục cache riêng và clone sớm:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.internal/platform/config-repo.git
          username: ${CONFIG_GIT_USERNAME}
          password: ${CONFIG_GIT_TOKEN}
          basedir: /var/lib/config-server/git-cache
          clone-on-start: true
          timeout: 15
          refresh-rate: 30
          proxy:
            https:
              host: ${GIT_PROXY_HOST}
              port: ${GIT_PROXY_PORT:3128}
              username: ${GIT_PROXY_USERNAME}
              password: ${GIT_PROXY_PASSWORD}
              non-proxy-hosts: localhost|127.*
```

Đây là ví dụ cấu trúc. Chỉ giữ phần proxy nếu môi trường thực sự cần proxy; token và password phải đến từ secret manager. CA của Git server/proxy phải được trust bởi JVM. `refresh-rate: 30` có nghĩa server không fetch remote cho mọi request; cần cân nhắc freshness và khả năng stale khi Git backend unavailable.

## 18. Bảo vệ credential và log khi troubleshooting

Clone/fetch lỗi thường khiến người vận hành muốn bật debug log hoặc in cấu hình. Cần tránh làm lộ credential trong lúc chẩn đoán:

- Không in `CONFIG_GIT_TOKEN`, proxy password hoặc private key.
- Không dùng URI có user/password/token nhúng trong URL.
- Không bật HTTP wire logging trong production nếu log có thể chứa Authorization header.
- Khi chia sẻ stack trace, loại bỏ URI có credential và thông tin nội bộ không cần thiết.
- Dùng token read-only, scope hẹp và riêng cho Config Server.
- Rotate token/private key nếu nghi ngờ đã bị ghi vào log hoặc ticket.
- Không tắt TLS certificate validation hoặc SSH host key verification để làm lỗi biến mất.
- Giới hạn quyền đọc của basedir, `.ssh`, keystore và file cấu hình runtime.

## 19. Bài thực hành

### Bước 1: Tạo Git repository test

Tạo một repository cấu hình riêng với `application.yml` và `orders-service.yml`. Cấp quyền read-only cho service account dùng bởi Config Server.

**Kết quả cần đạt:** xác nhận URI đúng và tài khoản dịch vụ có quyền đọc.

### Bước 2: Mô phỏng token sai

Đổi token test thành token hết hạn hoặc token không có quyền đọc. Bật `clone-on-start: true` trong môi trường lab và quan sát lỗi gốc.

**Kết quả cần đạt:** phân biệt lỗi authentication với lỗi authorization.

### Bước 3: Chuyển sang SSH

Tạo deploy key chỉ đọc, thêm public key vào repository, mount private key và known_hosts vào runtime. Bật property-based SSH config với `ignore-local-ssh-settings: true`.

**Kết quả cần đạt:** clone thành công khi key và host key đúng; thất bại an toàn khi host key không khớp.

### Bước 4: Mô phỏng proxy và TLS

Đặt Git backend sau HTTPS proxy trong môi trường lab. Thử sai proxy credential, sau đó thử CA chưa được trust.

**Kết quả cần đạt:** phân biệt lỗi 407 của proxy với TLS trust failure và biết vị trí cấu hình cần sửa.

### Bước 5: Mô phỏng lỗi basedir

Đặt basedir vào thư mục không cho service account ghi. Quan sát `AccessDeniedException`; cấp quyền đúng cho service user và thử lại.

**Kết quả cần đạt:** xác nhận quyền phải thuộc đúng identity chạy JVM.

### Bước 6: Mô phỏng Git outage sau clone

Clone thành công, sau đó chặn kết nối Git remote. Gọi Config Server và quan sát local working copy tiếp tục phục vụ revision cũ. Khôi phục Git và xác nhận fetch cập nhật thành công theo `refresh-rate`.

**Kết quả cần đạt:** phân biệt clone failure, fetch failure và dữ liệu stale từ cache local.

## 20. Tự kiểm tra

1. Vì sao Config Server có thể khởi động thành công dù Git repository không truy cập được?
2. `clone-on-start` thay đổi thời điểm phát hiện lỗi như thế nào?
3. Vì sao `git clone` thành công trên máy developer chưa chứng minh JGit của Config Server cũng thành công?
4. Token HTTPS cần những quyền gì và vì sao không nên nhúng token vào URI?
5. SSH private key và `known_hosts` có vai trò khác nhau như thế nào?
6. `ignore-local-ssh-settings` làm thay đổi cách JGit lấy SSH configuration ra sao?
7. Vì sao không nên đặt `strict-host-key-checking: false`?
8. Proxy HTTP/HTTPS được cấu hình ở đâu và vì sao phải cấu hình riêng cho từng repository?
9. Làm sao phân biệt lỗi TLS trust với lỗi token?
10. `basedir`, `HOME` và `XDG_CONFIG_HOME` ảnh hưởng đến clone/fetch như thế nào?
11. Vì sao Config Server có thể trả cấu hình cũ khi Git remote đang unavailable?
12. `refresh-rate` và `force-pull` giải quyết hai vấn đề khác nhau ra sao?
13. Khi nào cần dừng Config Server trước khi dựng lại working copy?
14. Những dữ liệu nào không được in ra log khi troubleshooting?

Khi hoàn thành bài thực hành, người học có thể phân loại lỗi clone/fetch theo authentication, SSH trust, proxy, TLS và filesystem; kiểm tra đúng identity chạy Config Server; khắc phục credential hoặc quyền thư mục có kiểm soát; đồng thời nhận biết khi server đang phục vụ từ local working copy cũ.

## Tài liệu tham khảo

- [Spring Cloud Config – Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html): URI, HTTP authentication, SSH key/known_hosts, timeout, clone-on-start, refresh-rate và force-pull.
- [Spring Cloud Config – Accessing Backends Through a Proxy](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/accessing-backends-through-a-proxy.html): cấu hình HTTP/HTTPS proxy theo repository.
- [Spring Cloud Config – Version Control Backend Filesystem Use](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/version-control-backend-filesystem-use.html): basedir, thư mục tạm, filesystem permission và local path hardening.
- [Git – git-ls-remote](https://git-scm.com/docs/git-ls-remote): kiểm tra khả năng liệt kê refs từ remote repository.
- [OpenSSH – ssh](https://man.openbsd.org/ssh): kiểm tra kết nối SSH và cấu hình client.

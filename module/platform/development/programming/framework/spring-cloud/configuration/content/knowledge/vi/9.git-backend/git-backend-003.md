# JGit, known_hosts và xử lý khóa máy chủ SSH

Spring Cloud Config Server thường đọc cấu hình từ một repository Git. Khi repository dùng SSH, Config Server phải thực hiện hai việc bảo mật riêng biệt: xác thực danh tính của server Git và xác thực danh tính của chính Config Server với Git server. Spring Cloud Config sử dụng JGit để làm việc với Git; vì vậy, kết nối SSH cần được cấu hình phù hợp với môi trường chạy Java và cơ chế SSH mà JGit sử dụng.

Hai loại khóa thường bị nhầm lẫn là **private key của client** và **host key của server**. Private key chứng minh Config Server có quyền đăng nhập vào repository. Host key cùng tệp `known_hosts` giúp Config Server xác minh nó đang kết nối đúng Git server, tránh bị chuyển hướng đến một máy chủ giả mạo. Cả hai đều cần được quản lý và xoay vòng có kiểm soát.

## 1. JGit trong Spring Cloud Config Server

JGit là thư viện Git được viết bằng Java. Git backend của Spring Cloud Config Server dùng JGit để truy cập repository, lấy các nhánh hoặc tag và đọc những file cấu hình cần thiết. Nhờ đó, Config Server có thể làm việc với Git từ trong tiến trình Java mà không phải dựa vào việc gọi trực tiếp lệnh `git` của hệ điều hành cho mỗi thao tác.

Một luồng đọc cấu hình điển hình:

1. Client yêu cầu cấu hình theo application, profile và label.
2. Config Server chuyển yêu cầu đến `EnvironmentRepository` dùng Git.
3. JGit truy cập repository từ xa qua HTTPS hoặc SSH, hoặc dùng bản clone cục bộ đã có.
4. Server đọc các tài liệu phù hợp với application/profile/label và xây dựng `Environment`.
5. Config Server trả về danh sách `PropertySource` cho client.

Khi backend dùng SSH, JGit cần biết địa chỉ server, cổng, danh tính người dùng, private key dùng để xác thực và cách xác minh host key. Các thiết lập này cần sẵn có trong môi trường chạy Config Server, chẳng hạn trong container hoặc pod.

Lệnh `ssh` hoặc `git` chạy thành công từ terminal của lập trình viên không chứng minh JGit trong Config Server đã được cấu hình đúng. Tiến trình Java có thể chạy bằng user khác, trong container khác, với thư mục home, SSH config, known_hosts và credential khác.

## 2. Phân biệt private key và host key

SSH dùng hai cặp khóa có mục đích khác nhau:

| Thành phần | Thuộc về ai? | Mục đích | Nơi lưu thường gặp |
|---|---|---|---|
| Client private key | Config Server hoặc tài khoản dịch vụ | Chứng minh client có quyền truy cập repository. | Secret manager hoặc secret mount chỉ đọc. |
| Client public key | Tài khoản dịch vụ trên Git server | Cho phép Git server xác thực client private key tương ứng. | Phần SSH public keys/deploy keys của Git server. |
| Server host key | Git server | Chứng minh máy chủ SSH là máy chủ có danh tính đã được tin cậy. | Tệp `known_hosts` ở phía Config Server. |

Khi Config Server kết nối Git server:

- Git server gửi host key để Config Server kiểm tra.
- Config Server so sánh host key nhận được với thông tin đã tin cậy trong `known_hosts` hoặc cấu hình host key được hỗ trợ.
- Sau khi xác minh máy chủ, Config Server dùng private key để chứng minh danh tính của client.
- Git server đối chiếu với public key đã đăng ký và quyết định có cấp quyền truy cập repository hay không.

Private key của client không thay thế host key của server. Tương tự, việc có host key hợp lệ trong `known_hosts` không cấp quyền đọc repository; nó chỉ xác minh đúng máy chủ đang được kết nối.

## 3. Tệp known_hosts

`known_hosts` là tệp ở phía client SSH, ghi lại host key của các máy chủ đã được xác minh. Một dòng thường có cấu trúc:

```text
hostname[,host-alias] key-type base64-encoded-host-public-key [comment]
```

Ví dụ minh họa:

```text
git.example.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleHostPublicKeyMaterial git-service
```

Khi SSH dùng cổng không mặc định, tên host thường được ghi kèm cổng trong dấu ngoặc vuông:

```text
[git.example.com]:2222 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleHostPublicKeyMaterial git-service
```

Giá trị public key trong ví dụ là dữ liệu giả để minh họa định dạng, không dùng làm khóa thật. Tệp thực tế cần chứa host key do đơn vị vận hành Git cung cấp hoặc đã được xác minh qua một kênh tin cậy.

Khi Config Server kết nối đến `git.example.com:2222`, bản ghi trong `known_hosts` phải khớp host và cổng mà SSH transport sử dụng. Nếu chỉ ghi `git.example.com` trong khi kết nối đến cổng khác, việc tra cứu host key có thể không khớp.

`known_hosts` có thể chứa nhiều máy chủ và nhiều thuật toán host key. Hãy chỉ lưu các host key cần thiết cho repository mà Config Server truy cập, đồng thời kiểm soát quyền ghi của tệp để tránh bị thay thế ngoài ý muốn.

## 4. Cấu hình Git SSH trong Config Server

Ví dụ dưới đây dùng SSH URI với cổng `2222`, client private key lấy từ biến môi trường và host key được xác minh qua tệp `known_hosts`:

```yaml
server:
  port: 8888

spring:
  cloud:
    config:
      server:
        git:
          uri: ssh://git@git.example.com:2222/platform/config-repo.git
          default-label: main
          clone-on-start: true
          ignore-local-ssh-settings: true
          private-key: ${CONFIG_GIT_PRIVATE_KEY}
          passphrase: ${CONFIG_GIT_KEY_PASSPHRASE:}
          known-hosts-file: /etc/config-server/ssh/known_hosts
          strict-host-key-checking: true
          timeout: 10
```

Ý nghĩa các thuộc tính chính:

| Thuộc tính | Vai trò |
|---|---|
| `uri` | Địa chỉ repository SSH; username và cổng được thể hiện trong URI. |
| `default-label` | Label mặc định khi client không gửi label riêng. |
| `clone-on-start` | Yêu cầu clone repository khi Config Server khởi động để phát hiện sớm lỗi kết nối. |
| `ignore-local-ssh-settings` | Bỏ qua SSH settings cục bộ và dùng các thuộc tính SSH được khai báo rõ cho Config Server. |
| `private-key` | Nội dung private key mà Config Server dùng để xác thực với Git server. |
| `passphrase` | Passphrase mở khóa private key nếu key được mã hóa. |
| `known-hosts-file` | Đường dẫn tệp chứa host key đã được tin cậy. |
| `strict-host-key-checking` | Yêu cầu xác minh host key và từ chối host chưa được tin cậy hoặc có khóa không khớp. |
| `timeout` | Thời gian chờ thao tác Git theo cấu hình của backend. |

Các thuộc tính SSH của Spring Cloud Config có thể thay đổi theo phiên bản Spring Cloud. Hãy kiểm tra reference documentation tương ứng với release train mà dự án đang dùng khi nâng cấp hoặc khi một thuộc tính không được bind như mong đợi.

Khi bật `ignore-local-ssh-settings`, hãy cung cấp rõ các thông tin SSH mà Config Server cần. Nếu dựa vào `~/.ssh/config` của user chạy tiến trình, cần hiểu rằng đường dẫn home và nội dung file đó phải tồn tại trong runtime. Tránh phụ thuộc ngầm vào cấu hình SSH của máy phát triển.

## 5. Đăng ký và cung cấp client key

Để Config Server đọc repository riêng tư, tạo một SSH key pair dành riêng cho dịch vụ. Public key được đăng ký dưới dạng deploy key hoặc SSH key của một tài khoản dịch vụ trên Git server. Cấp quyền đọc repository ở mức tối thiểu cần thiết.

Private key cần được lưu trong secret manager hoặc cơ chế quản lý bí mật của nền tảng triển khai. Khi đưa vào Config Server:

- Cung cấp qua secret mount hoặc biến môi trường được bảo vệ.
- Nếu dùng biến môi trường chứa PEM nhiều dòng, bảo toàn chính xác các dấu xuống dòng và định dạng của key.
- Nếu private key có passphrase, cung cấp passphrase qua một secret riêng.
- Không ghi private key vào `application.yml`, Docker image, source control hoặc log.
- Giới hạn quyền đọc secret cho đúng service account chạy Config Server.

Ví dụ cấu hình placeholder:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          private-key: ${CONFIG_GIT_PRIVATE_KEY}
          passphrase: ${CONFIG_GIT_KEY_PASSPHRASE:}
```

Đoạn cấu hình chỉ tham chiếu tên secret; giá trị thật phải được nền tảng cung cấp lúc chạy. Không đặt nội dung private key thật vào repository cấu hình.

Một key dành riêng cho Config Server giúp việc thu hồi và xoay vòng ít ảnh hưởng đến tài khoản cá nhân. Khi người phụ trách thay đổi, tổ chức có thể thay deploy key của service mà không phải chuyển giao private key cá nhân.

## 6. Xác minh host key trước khi đưa vào known_hosts

Host key là danh tính của SSH server. Khi tạo hoặc cập nhật `known_hosts`, cần xác minh fingerprint của host key qua kênh độc lập, chẳng hạn tài liệu bảo mật chính thức của nhà cung cấp Git hoặc xác nhận từ đội ngũ quản trị Git.

Có thể dùng `ssh-keyscan` để thu thập host key đang được máy chủ công bố:

```bash
ssh-keyscan -p 2222 -t ed25519 git.example.com > git-host-keys.candidate
ssh-keygen -lf git-host-keys.candidate
```

`ssh-keyscan` chỉ thu thập khóa được máy chủ trình bày tại thời điểm quét. Bản thân lệnh này không chứng minh khóa đó thuộc về Git server hợp lệ. Hãy so sánh fingerprint do `ssh-keygen -lf` hiển thị với fingerprint nhận được từ kênh tin cậy trước khi đưa bản ghi vào `known_hosts` được triển khai.

Quy trình an toàn:

1. Nhận fingerprint host key chính thức từ quản trị viên hoặc nhà cung cấp Git qua kênh độc lập.
2. Thu thập host key đang được endpoint SSH công bố.
3. Tính fingerprint của khóa đã thu thập.
4. So sánh từng thuật toán và fingerprint với thông tin đã xác minh.
5. Chỉ sau khi khớp mới đưa bản ghi vào tệp `known_hosts` dùng bởi Config Server.
6. Triển khai tệp và kiểm tra kết nối từ đúng runtime của Config Server.

Không sao chép kết quả `ssh-keyscan` thẳng vào production chỉ vì lệnh chạy thành công. Nếu kẻ tấn công kiểm soát đường mạng trong lúc quét, khóa thu thập được có thể là khóa của máy chủ giả mạo.

## 7. Strict host key checking

Strict host key checking buộc SSH kiểm tra host key của máy chủ với danh sách hoặc giá trị đã tin cậy. Khi bật kiểm tra nghiêm ngặt:

- Host mới chưa có trong `known_hosts` sẽ bị từ chối.
- Host gửi khóa khác với khóa đã lưu sẽ bị từ chối.
- Kết nối chỉ tiếp tục khi danh tính server khớp với thông tin đã tin cậy.

Trong môi trường production, hãy bật:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          strict-host-key-checking: true
          known-hosts-file: /etc/config-server/ssh/known_hosts
```

Không tắt strict checking chỉ để vượt qua lỗi `Host key verification failed`. Tắt kiểm tra có thể khiến Config Server chấp nhận máy chủ giả mạo và gửi thông tin xác thực SSH đến sai đích.

Nếu một môi trường thử nghiệm dùng host key tạm thời, hãy tạo một `known_hosts` riêng cho môi trường đó và quản lý vòng đời khóa như một phần của cấu hình môi trường. Không dùng một ngoại lệ kiểm tra host key không an toàn làm cấu hình mặc định cho mọi môi trường.

## 8. Xử lý khi host key thay đổi

Git server có thể thay host key khi thay máy chủ, thay nền tảng SSH, xoay vòng khóa định kỳ hoặc xử lý sự cố bảo mật. Nếu Config Server đang giữ host key cũ, JGit có thể từ chối kết nối với lỗi host key không khớp.

Không nên xóa bản ghi cũ và chấp nhận khóa mới ngay lập tức. Hãy xác minh việc thay khóa là thay đổi hợp lệ:

1. Nhận thông báo thay host key từ đội ngũ vận hành hoặc nhà cung cấp Git.
2. Lấy fingerprint mới qua kênh độc lập đã xác thực.
3. Thu thập khóa mới từ endpoint và so sánh fingerprint.
4. Chuẩn bị cập nhật `known_hosts`; trong giai đoạn chuyển đổi, chỉ giữ đồng thời khóa cũ và mới nếu đội vận hành xác nhận cả hai đang hợp lệ.
5. Triển khai tệp mới với quyền đọc phù hợp và kiểm tra từ Config Server.
6. Sau khi xác nhận toàn bộ client đã chuyển sang host key mới, loại bỏ khóa cũ theo lịch xoay vòng.

Nếu host key thay đổi bất ngờ và không có thông báo, hãy xem đây là tín hiệu cần điều tra. Có thể máy chủ đã được thay thế ngoài kế hoạch, DNS trỏ sai, kết nối đi qua proxy không mong muốn hoặc đang xảy ra tấn công trung gian.

## 9. Phân biệt lỗi host key và lỗi xác thực người dùng

SSH có thể thất bại ở nhiều giai đoạn. Phân biệt giai đoạn giúp tránh thay nhầm loại khóa:

| Triệu chứng | Nhóm lỗi | Việc cần kiểm tra |
|---|---|---|
| `UnknownHostKey` hoặc `Host key verification failed` | Xác minh server | Hostname, cổng, `known_hosts`, fingerprint và strict checking. |
| Host key changed hoặc mismatch | Xác minh server | Xác minh thay đổi từ đội quản trị Git; cập nhật bản ghi sau khi xác nhận. |
| `Auth fail` hoặc `Permission denied (publickey)` | Xác thực client | Private key, passphrase, public key đã đăng ký, SSH username và quyền repository. |
| `Connection refused` | Kết nối mạng | Cổng SSH, service SSH, firewall, network policy và URI. |
| DNS resolution failure hoặc timeout | Kết nối mạng | DNS trong container/pod, route, proxy và khả năng đi đến host/port. |
| Repository not found hoặc access denied sau khi SSH thành công | Quyền Git | Đường dẫn repository, namespace, deploy key và quyền đọc. |
| Không tìm thấy branch/tag | Label hoặc repository | `default-label`, label client gửi và tên branch/tag tồn tại trên remote. |

Lỗi host key xảy ra khi xác minh danh tính máy chủ. Lỗi `Permission denied (publickey)` thường xảy ra sau khi SSH đã tiếp cận server nhưng server không chấp nhận danh tính client. Thay `known_hosts` không sửa được private key sai; thay private key cũng không sửa được host key không tin cậy.

## 10. Chẩn đoán JGit từ môi trường chạy Config Server

Khi native OpenSSH hoạt động nhưng Config Server vẫn lỗi, kiểm tra các khác biệt sau:

1. **Runtime identity:** Config Server chạy dưới user nào? User đó có đọc được private key và `known_hosts` không?
2. **Đường dẫn:** đường dẫn trong cấu hình có tồn tại bên trong container hoặc pod không? Có bị mount nhầm hoặc mount rỗng không?
3. **SSH settings:** `ignore-local-ssh-settings` có đang bỏ qua cấu hình mà môi trường trước đó dựa vào không?
4. **Key format:** JGit và SSH transport của phiên bản đang dùng có hỗ trợ định dạng private key và thuật toán host key đã chọn không?
5. **Host/port:** URI có đúng hostname, username và cổng không? Bản ghi `known_hosts` có dùng đúng cú pháp cho cổng đó không?
6. **Network:** DNS, TLS ở các proxy trung gian, firewall và network policy có cho phép kết nối không?
7. **Git permissions:** public key đã được đăng ký đúng repository hoặc tổ chức chưa, và có quyền đọc không?
8. **Label:** branch, tag hoặc commit mà client yêu cầu có tồn tại trên remote không?

Có thể kiểm tra kết nối bằng một yêu cầu cấu hình cụ thể sau khi Config Server khởi động:

```bash
curl -i http://localhost:8888/orders-service/prod/main
```

Đọc HTTP status, response body và log cùng thời điểm. Nếu cần bật log JGit/SSH để chẩn đoán, chỉ bật trong thời gian ngắn ở môi trường phù hợp, giới hạn quyền truy cập log và bảo đảm không ghi lộ private key, passphrase hoặc token.

## 11. Quyền truy cập và triển khai secret

Trong môi trường production, nên mount private key và `known_hosts` dưới dạng secret hoặc file được quản lý bởi nền tảng. Một cấu trúc minh họa:

```text
/etc/config-server/ssh/
├── known_hosts
└── git-client-key
```

Các file cần được cấp quyền đọc cho service account của Config Server. Private key cần quyền hạn chế nhất có thể; `known_hosts` nên được mount chỉ đọc để tiến trình ứng dụng không thể tự ý thay host key tin cậy.

Một số nguyên tắc quản trị:

- Dùng deploy key riêng cho Config Server và chỉ cấp quyền đọc.
- Lưu private key và passphrase trong secret manager; xoay vòng theo chính sách của tổ chức.
- Quản lý `known_hosts` như một artifact cấu hình được review và version hóa.
- Xác minh fingerprint mới trước mỗi lần cập nhật host key.
- Không ghi key material vào Git, image, log hoặc biến môi trường có thể bị hiển thị rộng rãi.
- Theo dõi thời điểm hết hạn, thay đổi quyền hoặc thu hồi key.
- Khi thu hồi key, cập nhật secret và xác minh Config Server đã sử dụng key mới.

## 12. Tổng kết

- JGit là thư viện Java mà Git backend của Spring Cloud Config Server sử dụng để truy cập repository.
- Client private key xác thực Config Server với Git server; server host key xác minh danh tính Git server.
- `known_hosts` lưu host key đã được tin cậy; hostname và cổng phải khớp với URI SSH.
- `strict-host-key-checking: true` bảo vệ kết nối khỏi máy chủ giả mạo và khóa không khớp.
- Xác minh fingerprint qua kênh độc lập trước khi thêm hoặc thay host key; `ssh-keyscan` chỉ thu thập khóa, không xác minh tính xác thực của khóa.
- Quản lý private key, passphrase và known_hosts bằng secret/configuration management, quyền tối thiểu và quy trình xoay vòng.
- Khi chẩn đoán, phân biệt lỗi host key, lỗi private key, lỗi quyền repository, lỗi DNS/port và lỗi label; kiểm tra từ đúng runtime của Config Server.

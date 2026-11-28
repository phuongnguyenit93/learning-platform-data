# SSH key authentication trong quản lý truy cập đặc quyền

## 1. SSH key authentication là gì?

**SSH key authentication** là cơ chế client chứng minh khả năng sử dụng private key tương ứng với public key mà máy chủ chấp nhận cho một tài khoản. Trong một phiên SSH, client tạo chữ ký trên dữ liệu xác thực gắn với kết nối; máy chủ xác minh chữ ký bằng public key phù hợp.

Private key không cần được gửi tới máy chủ để đăng nhập. Public key có thể được cung cấp cho bên xác minh, nhưng quyền thêm hoặc thay public key được chấp nhận phải được kiểm soát: thay danh sách khóa tin cậy có thể thay đổi ai được đăng nhập.

Trong PAM, SSH key authentication thường xuất hiện ở:

- Quản trị viên truy cập máy chủ Linux hoặc thiết bị hỗ trợ SSH.
- Gateway dùng khóa được quản lý để mở phiên tới target.
- Workload thực hiện tác vụ quản trị tự động.
- Hệ thống cấp chứng thư SSH ngắn hạn sau khi xác thực và ủy quyền.

Mục tiêu không chỉ là “đăng nhập không nhập mật khẩu”. Cần biết khóa thuộc ai, được dùng ở đâu, vào tài khoản nào, có quyền gì, trong bao lâu và thu hồi bằng cách nào.

## 2. Ba loại khóa cần phân biệt

| Loại | Chủ thể sử dụng private key | Bên xác minh | Mục đích |
|---|---|---|---|
| User key | Client, agent hoặc gateway | SSH server | Xác thực client cho tài khoản ở đích |
| Host key | SSH server | SSH client | Xác minh danh tính máy chủ |
| Khóa của SSH CA | Dịch vụ ký được quản lý | Bên tin cậy CA tương ứng | Ký chứng thư cho user key hoặc host key theo phạm vi |

Ba loại khóa không thay thế nhau.

Một user key hợp lệ không chứng minh client đang kết nối đúng máy chủ. Một host key đáng tin không có nghĩa mọi người dùng đều được quyền đăng nhập. Việc tin cậy một CA cũng cần phân biệt CA cho user và CA cho host cùng phạm vi được chấp nhận.

**Public key** và **private key** là hai thành phần của một cặp khóa. Public key không phải mật khẩu; private key là vật liệu bí mật cần được bảo vệ. Fingerprint giúp nhận diện một khóa theo hàm băm nhưng không tự chứng minh owner hoặc thẩm quyền của khóa đó.

Trong tài liệu và cấu hình hệ điều hành, từ PAM đôi khi còn chỉ Pluggable Authentication Modules. Một tùy chọn liên quan cơ chế đó trong SSH server không tự đồng nghĩa với việc đã tích hợp một hệ thống Privileged Access Management có vault, JIT hoặc giám sát phiên.

## 3. Luồng xác thực ở mức khái niệm

~~~mermaid
sequenceDiagram
    participant C as SSH client
    participant A as Agent hoặc nơi giữ private key
    participant S as SSH server
    C->>S: Thiết lập kết nối và thương lượng SSH
    S-->>C: Chứng minh danh tính máy chủ bằng cơ chế host key
    C->>C: Kiểm tra trust của host key
    C->>S: Yêu cầu xác thực cho tài khoản bằng public key
    S->>S: Đối chiếu nguồn khóa và điều kiện được chấp nhận
    C->>A: Yêu cầu tạo chữ ký cho dữ liệu xác thực
    A-->>C: Chữ ký
    C->>S: Bằng chứng chữ ký gắn với kết nối
    S->>S: Xác minh chữ ký và policy tài khoản
    S-->>C: Kết quả xác thực
~~~

Sơ đồ giản lược; chi tiết trao đổi phụ thuộc SSH và cách triển khai. Những điểm cần giữ đúng là:

1. Client cần xác minh máy chủ theo trust đã được thiết lập.
2. Máy chủ chỉ chấp nhận khóa theo tài khoản và nguồn cấu hình hợp lệ.
3. Client chứng minh khả năng sử dụng private key bằng chữ ký.
4. Chữ ký được ràng buộc với dữ liệu của quá trình xác thực, không chỉ là một bằng chứng chung có thể dùng tùy ý cho mọi kết nối.
5. Sau xác thực còn các điều kiện tài khoản, phiên và quyền hiệu lực tại đích.

Không diễn giải cơ chế này thành “server yêu cầu client gửi private key” hoặc “server mã hóa mật khẩu bằng public key”. Đó không phải bản chất của xác thực public key trong SSH.

## 4. Xác thực thành công chưa đồng nghĩa có quyền phù hợp

Public key được chấp nhận cho tài khoản nào thì phiên sẽ chịu các quyền và điều kiện của tài khoản đó, cùng những ràng buộc mà hệ thống áp dụng.

Ví dụ, khóa của kỹ sư An được chấp nhận cho tài khoản diagnostics. Nếu tài khoản này có quyền nâng lên quản trị toàn bộ, tên diagnostics không tự tạo least privilege.

Cần đánh giá các lớp:

| Lớp | Câu hỏi |
|---|---|
| Danh tính người yêu cầu | Ai thực sự khởi tạo phiên? |
| Mapping tài khoản | Khóa hoặc chứng thư được chấp nhận cho tài khoản nào? |
| Điều kiện khóa | Có giới hạn nguồn, lệnh hoặc chức năng nào? |
| Quyền hệ điều hành | Tài khoản đọc, sửa và chạy được gì? |
| Nâng quyền | Có thể dùng sudo, công cụ quản trị hoặc cơ chế tương đương không? |
| Kết nối tiếp | Từ target có thể tới tài nguyên khác không? |
| Bằng chứng | Có liên kết được người dùng với phiên và thao tác không? |

Nếu nhiều người dùng chung một private key, server có thể chỉ biết khóa chung đã được sử dụng. Một comment cuối dòng public key không đủ để xác định cá nhân trong tình huống đó.

PAM cần giữ liên kết từ người yêu cầu riêng tới account tại đích, kể cả khi gateway dùng một khóa kỹ thuật chung theo giới hạn của nền tảng.

## 5. Public key được chấp nhận từ đâu?

### 5.1. Danh sách khóa gắn với tài khoản

Trong nhiều triển khai OpenSSH, một nguồn phổ biến là authorized_keys của tài khoản đích. Đường dẫn và cách xử lý phụ thuộc cấu hình máy chủ.

Tệp này thường chứa public key, tùy chọn giới hạn và comment. Nó không chứa private key cần dùng để đăng nhập.

Những quyền sau đều có ý nghĩa bảo mật:

- Thêm hoặc thay dòng public key.
- Sửa tùy chọn giới hạn trên một dòng.
- Sửa cấu hình nguồn authorized keys.
- Thay owner hoặc quyền ghi của thư mục và tệp liên quan.
- Thay hệ thống quản lý cấu hình đang phân phối khóa.

Một tài khoản chưa có quyền quản trị toàn bộ vẫn có thể tạo đường truy cập lâu dài nếu nó được sửa một nguồn khóa quan trọng.

### 5.2. Nguồn khóa tập trung hoặc động

Một số môi trường lấy khóa qua dịch vụ danh tính, công cụ quản lý cấu hình hoặc cơ chế tra cứu được SSH server hỗ trợ.

Cách này có thể hỗ trợ kiểm kê và vòng đời tập trung, nhưng cần đánh giá:

- Nguồn dữ liệu nào có thẩm quyền.
- Thành phần tra cứu chạy với quyền gì.
- Cách xác thực tới nguồn khóa.
- Cache và độ trễ cập nhật.
- Hành vi khi nguồn không hoạt động.
- Khả năng chấp nhận dữ liệu sai hoặc ngoài phạm vi.

“Quản lý tập trung” không tự bảo đảm thu hồi tức thời. Các bản sao, cache và máy chủ không đồng bộ vẫn có thể giữ khóa cũ.

### 5.3. Chứng thư SSH

Trong mô hình chứng thư, server có thể tin cậy một user CA và kiểm tra chứng thư của client theo cấu hình. Không nhất thiết phải phân phối từng public key người dùng tới từng target như mô hình khóa tĩnh.

Chứng thư SSH là một cấu trúc dùng trong hệ sinh thái SSH; không mặc nhiên là chứng thư X.509.

Việc chấp nhận cần xét CA, loại chứng thư, thời hạn, principal và các điều kiện được hỗ trợ. Chứng thư có chữ ký hợp lệ chưa đủ nếu principal không được phép vào tài khoản đang yêu cầu.

## 6. Bảo vệ private key

### 6.1. Private key là vật liệu bí mật

Không đưa private key vào:

- Repository mã nguồn.
- Ticket hoặc email hỗ trợ.
- Image máy ảo hoặc container dùng chung không có thiết kế phù hợp.
- Log, recording hoặc clipboard không cần thiết.
- Thư mục chia sẻ rộng.
- Một kho secret mà mọi người có thể tự lấy không qua policy.

Phải quản lý cả bản sao và backup. Xóa bản ở một laptop không chứng minh private key chưa còn trong backup, agent, máy build hoặc image cũ.

### 6.2. Passphrase bảo vệ tệp khóa khi lưu

Passphrase có thể mã hóa private key ở trạng thái lưu, giúp giảm rủi ro khi chỉ tệp khóa bị lấy mà bên lấy không có khả năng mở khóa.

Passphrase không được gửi tới target như một mật khẩu đăng nhập SSH. Server thường nhìn thấy bằng chứng chữ ký, không trực tiếp biết người dùng đã nhập passphrase ở client như thế nào.

Khi key đã được mở trong agent, người dùng có thể không cần nhập lại cho mỗi lần sử dụng. Vì vậy, không chỉ dựa vào việc “key có passphrase” để kết luận PAM đã nhận được bằng chứng MFA mới cho từng phiên.

### 6.3. Agent và phần cứng giữ khóa

Agent có thể giữ khóa hoặc cung cấp khả năng ký để client không phải trực tiếp xử lý private key mỗi lần. Thiết bị phần cứng có thể giữ private key không xuất ra và thực hiện thao tác ký theo thiết kế.

Cần đánh giá:

- Ai được gọi khả năng ký.
- Có yêu cầu hiện diện hoặc xác minh người dùng không.
- Khả năng ký còn dùng được trong bao lâu.
- Endpoint bị kiểm soát có thể yêu cầu ký gì.
- Cách khóa, thu hồi và phục hồi khi mất thiết bị.

Một thao tác chạm chứng minh tương tác không tự tương đương với xác minh người dùng bằng PIN hoặc sinh trắc học. Cần kiểm tra đặc tính thực tế của authenticator và cách hệ thống sử dụng.

## 7. Host key: bảo vệ việc dùng user key đúng đích

Client cần có cơ sở tin cậy để nhận diện server. Cơ sở đó có thể là host key đã được phân phối qua kênh phù hợp, host certificate từ CA được tin cậy hoặc một quy trình quản trị khác theo nền tảng.

Nếu client bỏ xác minh host key để hết cảnh báo, nó có thể kết nối nhầm máy chủ. Xác thực user key không thay bước xác minh này.

Một số điểm vận hành cần làm rõ:

- Hostname và endpoint có tương ứng đúng tài nguyên không?
- Khi máy chủ thay host key, ai xác nhận thay đổi?
- Host key có bị sao chép giữa nhiều máy ngoài ý định không?
- Tập trust trên client hoặc gateway được cập nhật thế nào?
- Cụm hoặc endpoint động sử dụng host key hay host certificate ra sao?

Thu thập host key từ đường mạng, chẳng hạn bằng một công cụ lấy key, không tự chứng minh key đó thuộc máy chủ hợp lệ. Vẫn cần đối chiếu với nguồn tin cậy.

Không xử lý cảnh báo thay host key bằng cách tự động xóa trust cũ rồi tin mọi key mới. Thay đổi hợp lệ và dấu hiệu kết nối sai đích cần được phân biệt trước khi cập nhật.

## 8. Minh họa thao tác trong môi trường lab

Các lệnh sau minh họa quy trình trên một client tương thích. Không thực thi chúng trên production chỉ từ ví dụ; hostname và tài khoản là dữ liệu giả định.

### 8.1. Tạo cặp khóa riêng cho lab

~~~bash
ssh-keygen -t ed25519 \
  -f ~/.ssh/pam_lab_ed25519 \
  -C "alice:pam-lab"
~~~

Ví dụ chọn một loại khóa để minh họa. Loại khóa và thuật toán được phép phải phù hợp policy, khả năng của client, server và thiết bị giữ khóa trong môi trường thực tế.

Nếu dùng tệp private key, công cụ có thể yêu cầu passphrase khi tạo. Không đặt passphrase vào command line hoặc script hiển thị trong log.

Hai tệp thông thường được tạo theo tên minh họa:

~~~text
~/.ssh/pam_lab_ed25519       → private key
~/.ssh/pam_lab_ed25519.pub   → public key
~~~

Không tạo đè lên một cặp khóa đang sử dụng. Nếu công cụ báo tệp đã tồn tại, cần xác định owner và mục đích trước khi quyết định.

### 8.2. Ghi nhận fingerprint

~~~bash
ssh-keygen -lf ~/.ssh/pam_lab_ed25519.pub
~~~

Ghi nhận fingerprint cùng owner, mục đích và target được phép. Comment do người tạo đặt có ích cho quản lý nhưng không phải bằng chứng danh tính đáng tin tự thân.

### 8.3. Đăng ký public key qua quy trình được phép

Chỉ đưa public key vào nguồn được server chấp nhận theo quy trình quản trị. Không gửi private key để người quản trị “cài giúp”.

Nếu sử dụng authorized_keys trên một hệ Unix phù hợp, cần bảo đảm owner và quyền truy cập của home, thư mục .ssh và tệp liên quan đáp ứng yêu cầu server. Các giá trị 700 cho thư mục .ssh và 600 cho authorized_keys thường được dùng trong một cấu hình cơ bản, nhưng ACL, filesystem, cấu hình và nền tảng có thể làm thay đổi cách đánh giá.

Không sao chép thao tác chmod hoặc chown một cách máy móc lên thư mục đang phục vụ cơ chế quản lý khác.

### 8.4. Kết nối bằng khóa chỉ định

Giả định trust của host đã được thiết lập qua quy trình phù hợp:

~~~bash
ssh \
  -i ~/.ssh/pam_lab_ed25519 \
  -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes \
  diagnostics@app-a.lab.example
~~~

Ví dụ dùng tùy chọn của OpenSSH client tương ứng:

- Chỉ định identity giúp kiểm soát khóa dự kiến dùng cho phiên.
- IdentitiesOnly giúp tránh thử không giới hạn các identity khác chỉ vì agent đang có chúng, theo cách client xử lý các identity được cấu hình.
- StrictHostKeyChecking=yes yêu cầu việc kiểm tra trust của host được đáp ứng; nếu chưa có trust phù hợp, phải thiết lập đúng trước khi tiếp tục.

Lệnh minh họa xác thực, không chứng minh tài khoản diagnostics đã có quyền hẹp hoặc phiên đã đi qua PAM.

## 9. Giới hạn một khóa bằng tùy chọn tại server

Trong OpenSSH có hỗ trợ các tùy chọn tương ứng, một dòng authorized_keys có thể giới hạn nguồn hoặc buộc thực thi một lệnh.

Ví dụ ý định:

~~~text
restrict,from="192.0.2.10",command="/usr/local/sbin/pam-diagnostics-wrapper" ssh-ed25519 <PUBLIC_KEY_BASE64> alice:pam-lab
~~~

Đây là dòng minh họa có placeholder, không phải dữ liệu để cài trực tiếp. Địa chỉ 192.0.2.10 dùng cho tài liệu.

Các thành phần thể hiện:

- Chỉ chấp nhận nguồn phù hợp điều kiện from.
- Áp dụng tập hạn chế của restrict trên phiên bản hỗ trợ.
- Buộc chạy wrapper quản trị thay vì cho chọn lệnh tùy ý qua cơ chế này.

Cần hiểu các giới hạn:

1. Nguồn mà target nhìn thấy có thể là gateway hoặc địa chỉ sau NAT.
2. restrict giới hạn các tính năng của SSH theo semantics được hỗ trợ, không tự tạo một sandbox cho mọi chương trình chạy tại đích.
3. Việc hạn chế pseudo-terminal có thể làm một luồng tương tác không hoạt động như dự kiến.
4. Wrapper phải do bên có thẩm quyền quản lý và không cho người dùng sửa tùy ý.
5. Không được lấy nguyên nội dung SSH_ORIGINAL_COMMAND rồi thực thi như một lệnh shell không kiểm tra.
6. Các tác vụ mà wrapper gọi vẫn chịu quyền của tài khoản và có thể có đường thoát nếu thiết kế không phù hợp.

Forced command có thể hữu ích cho tác vụ cố định, nhưng không tự tương đương với JEA đầy đủ. Cần kiểm chứng thao tác, tham số, dữ liệu đầu vào và các khả năng gián tiếp của công cụ được phép.

## 10. Agent forwarding và điểm trung chuyển

### 10.1. Agent forwarding mở khả năng yêu cầu ký

Trong agent forwarding, remote host có thể tiếp cận khả năng ký của agent theo cơ chế được chuyển tiếp. Private key không nhất thiết được sao chép sang remote host, nhưng một host bị kiểm soát có thể lợi dụng khả năng yêu cầu ký trong phạm vi agent cho phép.

Vì vậy, “private key chưa rời laptop” chưa đủ để kết luận không có rủi ro sử dụng khóa từ xa.

Cần xem xét nhu cầu thực sự, điều kiện ký, giới hạn thời gian và mức tin cậy của host trung gian. Không bật forwarding theo thói quen cho mọi phiên.

### 10.2. Jump host không tự là PAM gateway

Một jump host có thể chỉ chuyển lưu lượng tới target. Ví dụ, một luồng ProxyJump có thể tạo kết nối SSH tới đích với lớp mã hóa giữa client và target bên trong đường trung chuyển.

Trong mô hình đó, host trung gian không mặc nhiên thấy nội dung lệnh ở phiên đích để ghi nhận đầy đủ. Log kết nối tại jump host khác với recording của một gateway thực sự môi giới hoặc chấm dứt giao thức theo thiết kế.

Ngoài ra, dùng jump host không tự yêu cầu agent forwarding. Cần hiểu cơ chế client trước khi mở thêm khả năng ký trên host trung gian.

### 10.3. Target trở thành điểm đi tiếp

Khi người dùng đã có shell tại A, họ có thể tạo kết nối tới B nếu chương trình, credential, quyền và mạng cho phép. Chặn một loại forwarding của SSH chưa chắc chặn mọi kết nối do chương trình ở A khởi tạo.

Cần kết hợp:

- Quyền hẹp và tác vụ được phép tại A.
- Kiểm soát egress của A và ingress của B.
- Giảm credential hoặc token có thể sử dụng từ A.
- Hạn chế kênh bổ sung theo nhu cầu.
- Bằng chứng cho hoạt động kết nối tiếp trong phạm vi hệ thống hỗ trợ.

## 11. Tích hợp khóa SSH vào PAM

### 11.1. Người dùng giữ khóa

Người dùng có thể giữ private key và được PAM hoặc hệ thống cấp quyền cho phép sử dụng trong một phạm vi.

Ưu điểm có thể là phù hợp client và cơ chế hiện hữu. Đổi lại, cần quản lý bản sao, đăng ký khóa, thiết bị, thu hồi và các đường sử dụng ngoài PAM.

Nếu cùng public key được cài trực tiếp trên nhiều target, việc chỉ khóa tài khoản tại cổng PAM có thể chưa ngăn đăng nhập SSH trực tiếp.

### 11.2. Gateway giữ khóa hoặc gọi khả năng ký

Người dùng xác thực với PAM bằng danh tính cá nhân. Gateway dùng private key từ vault hoặc cơ chế ký được quản lý để mở phiên.

Cần bảo vệ:

- Quyền lấy hoặc sử dụng khóa của gateway.
- Mapping người dùng, target và tài khoản.
- Các bản tạm, cache hoặc bộ nhớ chứa vật liệu liên quan.
- Phạm vi mạng từ gateway.
- Bằng chứng phiên và account hiệu lực tại đích.

Không tiết lộ private key cho người dùng có thể giảm một đường phơi lộ, nhưng gateway vẫn là thành phần đặc quyền và cần giới hạn quyền tương ứng.

### 11.3. Cấp khả năng truy cập tạm thời

JIT có thể được thực hiện bằng:

- Thêm public key tạm thời vào nguồn được quản lý.
- Trả public key từ nguồn động trong cửa sổ hợp lệ.
- Cấp chứng thư SSH ngắn hạn.
- Chỉ cho gateway sử dụng khóa khi có grant hợp lệ.
- Kết hợp các cơ chế trên với quyền tại đích.

Mỗi cách có semantics thu hồi khác nhau. Không dùng một nhãn JIT để suy rằng mọi credential, cache và phiên đều hết hiệu lực cùng lúc.

## 12. Chứng thư SSH ngắn hạn và SSH CA

### 12.1. Điều được ký và điều được phép

Một user certificate gắn public key với các thuộc tính như principal, thời hạn và điều kiện theo khả năng hệ thống. Server cần tin cậy CA phù hợp và kiểm tra mapping tới tài khoản được yêu cầu.

Principal không tự là quyền hệ điều hành. Nó là một phần của quá trình xác định chứng thư được phép dùng ở đâu; quyền hiệu lực còn do account và policy tại đích quyết định.

Dịch vụ ký phải kiểm tra chủ thể, public key, phạm vi, entitlement và cửa sổ trước khi phát chứng thư. Nếu cho người dùng tự chọn mọi principal hoặc thời hạn, CA có thể trở thành nguồn cấp quyền ngoài phạm vi.

### 12.2. Giảm phân phối khóa tĩnh nhưng tăng trọng tâm vào CA

CA có thể giảm công việc cài từng user key lên nhiều target, nhưng private key CA có khả năng ký ra nhiều chứng thư được tin cậy trong phạm vi tương ứng.

Cần kiểm soát:

- Ai được yêu cầu ký và ký cho loại chủ thể nào.
- Khóa CA được giữ và sử dụng ở đâu.
- Phạm vi server tin cậy CA đó.
- Thời hạn tối đa và điều kiện được phép.
- Log phát hành và khả năng đối chiếu với yêu cầu PAM.
- Rotation CA, khoảng chuyển tiếp và xử lý CA bị ảnh hưởng.

Có thể tách CA theo môi trường hoặc loại chứng thư khi phù hợp thiết kế. Số lượng CA không tự phản ánh mức an toàn nếu quyền tin cậy vẫn quá rộng.

### 12.3. Hết hạn và thu hồi

Hết hạn chứng thư thường ảnh hưởng việc xác thực mới theo kiểm tra của server. Nó không tự bảo đảm một shell đang chạy bị kết thúc đúng thời điểm hết hạn.

Một số triển khai có cơ chế danh sách thu hồi khóa hoặc chứng thư, chẳng hạn KRL trong OpenSSH khi được cấu hình. Hiệu lực phụ thuộc phân phối, cấu hình và thời điểm kiểm tra; không được coi là thông điệp tự động kết thúc mọi phiên hiện hữu.

Cần có kế hoạch riêng cho cấp mới, chứng thư đã phát hành và phiên đang hoạt động.

## 13. Kiểm kê, rotation và thu hồi khóa

### 13.1. Hồ sơ tối thiểu

Một khóa hoặc khả năng ký cần liên kết được với:

| Nhóm | Thông tin |
|---|---|
| Định danh | Fingerprint, loại khóa và ID quản lý |
| Owner | Cá nhân, workload hoặc thành phần kỹ thuật |
| Mục đích | Tác vụ và môi trường |
| Phạm vi | Target, tài khoản và nguồn chấp nhận |
| Lưu giữ | Thiết bị, vault, agent hoặc dịch vụ ký |
| Vòng đời | Ngày tạo, thay đổi và thời hạn theo thiết kế |
| Quyền | Role, forced command và điều kiện liên quan |
| Dependency | Automation, consumer và bản sao cần xử lý |
| Bằng chứng | Đăng ký, sử dụng, rotation và thu hồi |

Nếu không biết public key nằm ở đâu, thu hồi khi private key bị lộ sẽ khó xác nhận đầy đủ.

### 13.2. Rotation có kiểm soát

Một trình tự minh họa cho khóa dùng bởi consumer là:

1. Xác định các đích và consumer chịu ảnh hưởng.
2. Tạo cặp khóa mới trong môi trường giữ khóa phù hợp.
3. Đăng ký public key mới trong phạm vi được phép.
4. Cập nhật consumer dùng khóa mới.
5. Kiểm chứng kết nối và quyền bằng khóa mới.
6. Gỡ chấp nhận khóa cũ theo kế hoạch.
7. Xác minh khóa cũ không còn mở được kết nối mới.
8. Xử lý bản sao, cache và hồ sơ liên quan.

Khoảng chấp nhận đồng thời hai khóa cần có mục đích và thời hạn, không để trở thành tồn đọng vô hạn. Nếu khóa cũ đang bị nghi lộ, trình tự và mức ưu tiên có thể khác theo tình huống ứng phó.

### 13.3. Thu hồi không chỉ xóa private key ở nguồn

Tùy kiến trúc, có thể phải:

- Gỡ public key khỏi mọi nguồn chấp nhận trong phạm vi.
- Vô hiệu mapping hoặc entitlement liên quan.
- Chặn cấp chứng thư hoặc ký mới.
- Phân phối dữ liệu thu hồi được hỗ trợ.
- Xử lý agent và khả năng ký còn hoạt động.
- Hạn chế đường trực tiếp.
- Kết thúc phiên theo thẩm quyền.
- Xác minh kết quả và phần chưa được kiểm tra.

Xóa private key khỏi một laptop không làm public key biến mất khỏi target. Gỡ public key khỏi target cũng chưa chứng minh mọi phiên đã đăng nhập bằng khóa đó đều dừng.

## 14. Ví dụ xuyên suốt: chẩn đoán một máy chủ production

### 14.1. Bối cảnh

An cần chẩn đoán app-prod-a trong 30 phút. An không cần sửa cấu hình hoặc truy cập app-prod-b.

Tổ chức có PAM, gateway, nguồn credential được quản lý và role chẩn đoán tại đích đã kiểm chứng.

### 14.2. Luồng được cấp

1. An xác thực bằng danh tính riêng và đáp ứng MFA theo policy.
2. PAM kiểm tra entitlement, target, role, phê duyệt và cửa sổ.
3. Gateway nhận quyền mở đúng phiên.
4. Gateway xác minh host của app-prod-a.
5. Gateway dùng khóa hoặc chứng thư trong phạm vi được cấp.
6. Target chấp nhận tài khoản chẩn đoán với các giới hạn thực tế.
7. Log liên kết An, yêu cầu, fingerprint hoặc định danh chứng thư, account và session.

MFA tại PAM và SSH key authentication tới target có vai trò khác nhau. Server tại đích có thể chỉ nhìn thấy tài khoản kỹ thuật và khóa của gateway, nên liên kết của PAM là bằng chứng quan trọng cho trách nhiệm cá nhân.

### 14.3. Các đường cần kiểm tra

- An có thể SSH trực tiếp bằng một key cũ không?
- Gateway có dùng cùng key trên nhiều tài khoản quá rộng không?
- Có thể sử dụng key hoặc chứng thư cho app-prod-b không?
- Tài khoản chẩn đoán có thể nâng quyền ngoài mục tiêu không?
- Agent forwarding hoặc chương trình tại đích có mở đường đi tiếp không?
- Phiên và tác vụ tại đích được xử lý thế nào khi hết hạn?

Một luồng hợp lệ thành công chưa trả lời các câu hỏi về đường đi vòng.

### 14.4. Kết thúc

Hết cửa sổ, hệ thống ngừng cấp mới và xử lý phiên theo policy. Credential hoặc chứng thư được xử lý theo vòng đời riêng.

Nếu đã ngắt tương tác tại gateway nhưng chưa xác minh trạng thái tác vụ ở target, báo cáo phải giữ rõ phần đó. Không ghi “đã thu hồi toàn bộ” chỉ vì chứng thư đã hết hạn.

## 15. Chẩn đoán lỗi xác thực

### 15.1. Phân loại trước khi sửa

| Biểu hiện | Nhóm nguyên nhân cần xem xét |
|---|---|
| Không kết nối được | DNS, routing, firewall, cổng hoặc dịch vụ |
| Cảnh báo host key | Endpoint thay đổi, trust chưa đúng hoặc nguy cơ kết nối sai đích |
| Không dùng được private key | Quyền tệp, định dạng, passphrase, agent hoặc thiết bị |
| Server không chấp nhận public key | Sai account, nguồn khóa, tùy chọn, quyền tệp hoặc policy |
| Chứng thư bị từ chối | CA, principal, thời hạn, loại chứng thư hoặc điều kiện |
| Quá nhiều lần thử identity | Client thử các khóa không dự kiến trước khi tới khóa phù hợp |
| Xác thực thành công nhưng không mở được tác vụ | Policy account, shell, forced command hoặc quyền tại đích |
| Qua PAM được nhưng đi đường khác cũng được | Có đường ngoài phạm vi cần xử lý |

Trong lab hoặc phạm vi được phép, log chi tiết của client và log server có thể giúp đối chiếu. Khi chia sẻ log, cần kiểm tra hostname, tài khoản, đường dẫn, định danh và dữ liệu nhạy cảm liên quan.

Không gửi private key cho người hỗ trợ để họ tái hiện lỗi. Có thể kiểm tra fingerprint public key và dữ liệu cần thiết mà không trao secret.

### 15.2. Những sửa đổi không nên làm theo phản xạ

Không tắt kiểm tra host key, mở quyền ghi rộng cho thư mục .ssh hoặc cho phép mọi nguồn chỉ để vượt một lỗi chưa hiểu.

Cũng không bật lại phương thức yếu hơn hoặc mở đăng nhập đặc quyền trực tiếp mà không đi qua quy trình thay đổi phù hợp. Trước hết cần xác định lỗi thuộc kết nối, trust, xác thực hay quyền.

## 16. Kiểm chứng và bằng chứng vận hành

| Tình huống | Kết quả cần xác nhận |
|---|---|
| Đúng key, đúng account và đúng nguồn | Chỉ thực hiện được phạm vi hợp lệ |
| Key hợp lệ nhưng sai account | Không đăng nhập chỉ nhờ cùng khóa tồn tại ở nơi khác |
| Key đã bị gỡ khỏi nguồn chấp nhận | Không mở kết nối mới trong phạm vi đã cập nhật |
| Máy chủ thay host key chưa được xác nhận | Client không tự bỏ kiểm tra trust |
| Nguồn tra cứu khóa không hoạt động | Hành vi theo policy, cache và giới hạn đã thiết kế |
| Chứng thư từ CA khác | Không được chấp nhận như CA đã tin cậy |
| Chứng thư có principal ngoài phạm vi | Không mở tài khoản trái mapping |
| Chứng thư hết hạn | Không xác thực mới theo semantics của server |
| Key hoặc chứng thư bị thu hồi | Dữ liệu thu hồi đã được áp dụng tại điểm kiểm tra |
| Forwarding hoặc tác vụ ngoài nhu cầu | Bị giới hạn tại các lớp đã định |
| Gateway ngắt phiên | Kết quả tại đích được theo dõi riêng |
| Rotation cho automation | Consumer dùng key mới, key cũ không còn được chấp nhận trong phạm vi |

Bằng chứng nên liên kết request ID, danh tính người yêu cầu hoặc workload, target, account, fingerprint hoặc định danh chứng thư, thời điểm và kết quả phiên.

Không lưu private key, passphrase hoặc token đầy đủ vào hồ sơ. Fingerprint có ích để đối chiếu, nhưng một fingerprint riêng lẻ không thể thay nguồn log và chuỗi liên kết đáng tin.

Chỉ số có thể theo dõi gồm số key chưa có owner, key được chấp nhận ngoài phạm vi PAM, credential dùng chung quá rộng, rotation chưa hoàn tất và target chưa nhận dữ liệu thu hồi. Phạm vi kiểm kê phải rõ; tỷ lệ trong nhóm máy đã quản lý không tự đại diện cho toàn bộ hạ tầng.

## 17. Bài tập áp dụng

Một đội dùng cùng private key cho mọi kỹ sư, đặt public key vào tài khoản quản trị trên nhiều máy. Key được lưu trong một thư mục chia sẻ. Người dùng đi qua jump host, còn target vẫn nhận SSH trực tiếp từ VPN. Đội cho rằng có passphrase và log jump host nên đã có MFA và ghi nhận đầy đủ. Khi một kỹ sư nghỉ việc, đội xóa bản key trên laptop của người đó.

Hãy phân tích:

1. Danh tính cá nhân bị mất ở những điểm nào?
2. Passphrase tại client đã và chưa chứng minh điều gì với PAM và server?
3. Jump host có thực sự quan sát được nội dung phiên đích không?
4. Những nguồn chấp nhận và bản sao key nào cần được kiểm kê?
5. Vì sao xóa một bản private key chưa đủ thu hồi?
6. Làm thế nào chuyển sang quyền hẹp, credential được quản lý hoặc chứng thư ngắn hạn?
7. Cần kiểm chứng riêng điều gì cho kết nối mới và phiên đang mở?

Một phương án hợp lý cần làm rõ owner, phạm vi key, trust của host, quyền tại đích và vòng đời phiên. Kết quả đạt yêu cầu khi có thể chứng minh ai được truy cập, bằng khả năng ký nào, tới đúng tài nguyên nào và việc thu hồi thực sự đạt tới đâu.

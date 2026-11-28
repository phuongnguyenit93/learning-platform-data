# sudo policy

## 1. Mục tiêu và phạm vi

`sudo` cho phép một danh tính đã được xác thực thực hiện một lệnh dưới danh tính khác, thường là `root`, theo chính sách được cấu hình. Trong quản trị quyền truy cập đặc biệt, giá trị của `sudo` không nằm ở việc “chạy được lệnh quản trị”, mà ở khả năng giới hạn **ai được làm việc gì, trên máy nào, dưới danh tính nào, với điều kiện gì và để lại bằng chứng nào**.

Sau bài này, bạn có thể:

- Chuyển một nhu cầu vận hành thành quy tắc `sudoers` có phạm vi hẹp.
- Phân tích cả đường dẫn lệnh, tham số và những file mà lệnh đặc quyền sử dụng.
- Phân biệt xác thực người dùng, quyền thực thi và thời hạn cấp quyền.
- Kiểm tra cú pháp, kiểm thử quyền hiệu lực và chuẩn bị thu hồi quyền an toàn.
- Kết nối sự kiện `sudo` với ticket, phiên truy cập và bằng chứng phục vụ kiểm toán.

Chương “Linux PAM” thuộc module Privileged Access Management. Không nhầm phạm vi này với Linux **Pluggable Authentication Modules**, cũng thường viết tắt là PAM. `sudo` có thể tích hợp với cơ chế xác thực PAM của hệ điều hành, nhưng chính sách cho phép lệnh trong bài này chủ yếu được diễn đạt bằng `sudoers`. Xác thực thành công không tự động đồng nghĩa với được phép chạy mọi lệnh.

Các ví dụ giả định môi trường Linux có `sudo`, `visudo` và `systemd`. Đường dẫn binary, cấu hình ghi log và nguồn chính sách có thể khác giữa các hệ thống. Ví dụ là tài liệu thiết kế và thực hành trong lab; không phải lệnh đã được thực thi trên máy đích.

## 2. Từ yêu cầu nghiệp vụ đến ranh giới đặc quyền

Một yêu cầu như “cho đội vận hành quyền sudo để xử lý sự cố” chưa đủ để thiết kế chính sách. Cần làm rõ thao tác nào thực sự đòi hỏi đặc quyền.

Ví dụ nhu cầu hợp lệ:

> Thành viên nhóm vận hành Orders được khởi động lại đúng dịch vụ orders-api trên máy production đã được phê duyệt, bằng tài khoản cá nhân, sau khi xác thực và có ticket thay đổi.

Phân rã yêu cầu:

| Thành phần | Quyết định cần thể hiện |
| --- | --- |
| Chủ thể | Tài khoản cá nhân thuộc nhóm `orders-ops` |
| Phạm vi tài sản | Máy Orders production đã được đưa vào danh sách quản lý |
| Thao tác | Chỉ restart `orders-api.service` |
| Danh tính đích | `root`, vì systemd system service cần quyền quản trị |
| Xác thực | Yêu cầu mật khẩu theo chính sách xác thực của hệ thống |
| Thời hạn | Membership hoặc entitlement được cấp và thu hồi theo quy trình |
| Bằng chứng | Người thực hiện, máy, lệnh, thời điểm, kết quả và ticket liên quan |

Không chuyển yêu cầu trên thành quyền `sudo ALL` chỉ vì người vận hành có thể gặp tình huống chưa dự kiến. Nhu cầu khẩn cấp cần một luồng break-glass riêng, có phê duyệt và hậu kiểm.

Một quy tắc tốt cần thỏa cả hai điều kiện:

1. Cho phép hoàn thành đúng tác vụ.
2. Không trao thêm đường đi để sửa dữ liệu, thực thi chương trình hoặc thay đổi cấu hình ngoài tác vụ đó.

Điều kiện thứ hai thường khó hơn việc viết cú pháp.

## 3. Những thành phần chính của sudoers

Dạng khái quát của một user specification:

```sudoers
user_list host_list = (runas_list) tags: command_list
```

Ví dụ đơn giản:

```sudoers
alice orders-prod-01 = (root) PASSWD: /usr/bin/systemctl restart orders-api.service
```

Diễn giải:

- `alice`: danh tính gọi `sudo`.
- `orders-prod-01`: máy mà quy tắc có hiệu lực, theo cách `sudo` xác định hostname trên hệ thống đó.
- `(root)`: danh tính chạy lệnh, không phải người gọi.
- `PASSWD:`: lệnh thuộc diện yêu cầu xác thực; cơ chế cache và các ngoại lệ vẫn phải xem cùng cấu hình hiệu lực.
- Phần cuối: đường dẫn chương trình và danh sách tham số được phép.

Dấu `%` thường dùng để chỉ nhóm hệ điều hành:

```sudoers
%orders-ops orders-prod-01 = (root) PASSWD: /usr/bin/systemctl restart orders-api.service
```

Quy tắc dùng nhóm giúp quản lý quyền qua vòng đời danh tính. Tuy nhiên, nếu nhóm chứa tài khoản không còn làm việc, nhóm lồng ngoài ý muốn hoặc membership không được cập nhật kịp thời, chính sách vẫn trao quyền cho sai người.

### 3.1. Alias giúp biểu đạt ý định

```sudoers
User_Alias ORDERS_OPERATORS = %orders-ops
Cmnd_Alias ORDERS_RESTART = /usr/bin/systemctl restart orders-api.service

ORDERS_OPERATORS orders-prod-01 = (root) PASSWD: ORDERS_RESTART
```

Alias là tên đại diện cho một tập hợp, không phải một lớp cách ly bảo mật mới. Một alias có tên `SAFE_COMMANDS` nhưng chứa trình thông dịch hoặc shell vẫn có thể trao quyền rất rộng.

Khi alias được dùng chung giữa nhiều file hoặc nguồn chính sách, thay đổi alias có thể ảnh hưởng nhiều nhóm người dùng. Review phải xem cả nơi khai báo và nơi tham chiếu.

### 3.2. Runas phải bám nhu cầu

`(root)` giới hạn danh tính đích vào root trong quy tắc đó. Nếu tác vụ chỉ cần chạy dưới tài khoản dịch vụ, hãy đánh giá việc dùng tài khoản dịch vụ thay vì root.

Ví dụ một chương trình báo cáo nội bộ đã được kiểm soát:

```sudoers
%orders-report orders-prod-01 = (orders-report) PASSWD: /usr/local/libexec/orders-report
```

Ví dụ này chỉ phù hợp nếu chương trình thực sự được thiết kế an toàn: không thực thi lệnh tùy ý, không nhận đường dẫn tùy ý, không nạp mã từ nơi người gọi ghi được và không làm lộ dữ liệu ngoài phạm vi báo cáo.

Một service account có thể đọc secret, truy cập cơ sở dữ liệu hoặc gọi API nhạy cảm. Chạy dưới tài khoản dịch vụ vẫn là một hành động đặc quyền cần kiểm soát và ghi nhận.

### 3.3. Host matching không thay thế quản lý triển khai

Trên hạ tầng lớn, policy có thể đến từ file cục bộ, cấu hình tập trung hoặc dịch vụ danh tính. Việc có tên host trong một dòng không chứng minh file đã được triển khai đúng máy.

Cần xác minh cách host được nhận diện, cách phân phối chính sách và quyền hiệu lực trên máy thực tế. Không tự giả định hostname ngắn, FQDN và alias DNS luôn được xử lý giống nhau.

## 4. Phân biệt đường dẫn lệnh và tham số

Giới hạn binary chưa chắc đã giới hạn tác vụ.

Hai quy tắc sau có phạm vi rất khác:

```sudoers
%orders-ops orders-prod-01 = (root) /usr/bin/systemctl
```

```sudoers
%orders-ops orders-prod-01 = (root) /usr/bin/systemctl restart orders-api.service
```

Trong cách khai báo thông thường, khi chỉ nêu đường dẫn lệnh mà không chỉ định tham số, người dùng có thể truyền tham số tùy ý cho lệnh đó. Với `systemctl`, điều này rộng hơn rất nhiều so với restart một service.

Quy tắc thứ hai mô tả một chuỗi tham số cụ thể. Cần kiểm tra nó bằng đúng phiên bản `sudo` và cách policy được phân phối trong môi trường của bạn.

Các nguyên tắc thực hành:

- Xác nhận đường dẫn thực của binary trên máy được quản lý.
- Dùng đường dẫn tuyệt đối trong policy và trong ca kiểm thử.
- Liệt kê các tổ hợp lệnh, tham số được phê duyệt một cách rõ ràng.
- Không dùng wildcard chỉ để giảm số dòng cấu hình.
- Khi cần lệnh không có tham số, `sudoers` hỗ trợ đối số rỗng `""`; cần phân biệt nó với việc không khai báo phần tham số.

Ví dụ cú pháp giới hạn một chương trình không nhận đối số:

```sudoers
%orders-report orders-prod-01 = (orders-report) /usr/local/libexec/orders-health ""
```

Lệnh minh họa này vẫn phải được kiểm tra về hành vi nội bộ và quyền sở hữu file.

### 4.1. Wildcard dễ mở rộng phạm vi ngoài dự kiến

Một mẫu như `/usr/bin/systemctl restart *` cho phép lựa chọn nhiều service, thay vì chỉ service thuộc trách nhiệm của nhóm. Với nhiều loại lệnh khác, wildcard trong phần tham số còn có thể khớp khoảng trắng hoặc nhiều đối số theo cách người viết policy không dự kiến.

Không suy luận rằng wildcard trong policy hoạt động giống chính xác cách shell phân tách từng đối số. Hãy thiết kế bộ kiểm thử cho toàn bộ command line.

Nếu môi trường dùng biểu thức chính quy hoặc tính năng khớp nâng cao, phải xác nhận phiên bản và ngữ nghĩa trước khi dùng. Một biểu thức nhìn có vẻ chặt vẫn có thể sai ở cách neo đầu/cuối hoặc cách xử lý đối số.

### 4.2. Không xây allowlist rộng rồi vá bằng denylist

Mẫu tư duy “cho mọi lệnh, trừ vài lệnh nguy hiểm” khó kiểm soát. Nhiều chương trình có thể gọi chương trình khác, sửa file cấu hình hoặc thực hiện tác vụ tương đương bằng một đường dẫn khác.

Nên bắt đầu từ tập thao tác cần cho công việc và thêm từng thao tác đã đánh giá. Không coi một dòng phủ định là biện pháp thu hồi đầy đủ cho các quyền rộng đã được cấp từ nguồn khác.

## 5. Đánh giá quyền thực tế của lệnh được cho phép

Một allowlist chỉ đáng tin khi chương trình và các đầu vào có thể ảnh hưởng đến chương trình đều được kiểm soát.

### 5.1. Shell, trình thông dịch và công cụ tương tác

Cấp quyền chạy shell dưới root gần như trao một môi trường thực thi root. Trình thông dịch, trình soạn thảo, công cụ có khả năng chạy subcommand hoặc nạp plugin cũng có thể đem lại phạm vi tương tự.

Một công cụ “chỉ để xem” có thể gọi pager. Pager hoặc editor có thể cung cấp chức năng mở file khác hay chạy lệnh. Vì thế, việc binary có vẻ mang tính đọc không đủ để kết luận quyền là read-only.

Đánh giá tối thiểu:

- Có shell escape hoặc chức năng gọi chương trình ngoài không?
- Có nạp cấu hình từ thư mục người dùng không?
- Có hỗ trợ plugin hoặc script không?
- Có ghi file tùy ý hoặc thay đổi đường dẫn output không?
- Có làm lộ secret qua output hoặc thông báo lỗi không?

Không coi các tùy chọn như `NOEXEC` là sandbox hoàn chỉnh. Chúng có giới hạn triển khai và không thay thế thiết kế phạm vi lệnh.

### 5.2. Một lệnh restart vẫn có thể dẫn đến thực thi mã đặc quyền

Giả sử người dùng chỉ được restart `orders-api.service`, nhưng lại có thể sửa một trong các thành phần sau:

- Unit file hoặc systemd drop-in.
- Script được `ExecStart` gọi.
- File môi trường có giá trị được dùng để chọn executable hoặc module.
- Binary, thư viện hay plugin được service nạp.
- Thư mục cha có thể bị thay thế hoặc chỉnh sửa theo cách ảnh hưởng đến đường dẫn.

Khi service khởi động lại, nội dung bị sửa có thể được thực thi dưới danh tính của service, thậm chí root nếu service cấu hình như vậy.

Do đó, review policy phải kiểm tra chuỗi phụ thuộc của thao tác. Chỉ kiểm tra owner của `/usr/bin/systemctl` là chưa đủ.

```text
Người vận hành
    |
    | sudo: chỉ restart orders-api
    v
systemctl -> unit/drop-in -> script/binary -> cấu hình và dependency
                              |
                              v
                   Danh tính thực thi của service
```

Câu hỏi quyết định là: **người được cấp quyền có kiểm soát được thứ mà lệnh đặc quyền sẽ tin và sử dụng không?**

### 5.3. Wrapper không tự nhiên trở thành an toàn

Khi một tác vụ cần logic phức tạp, có thể xây một wrapper hẹp thay vì cho phép một công cụ quản trị đa năng. Wrapper cần:

- Có owner và quy trình phát hành được quản lý.
- Từ chối đối số ngoài tập cho phép.
- Dùng đường dẫn cố định cho chương trình được gọi.
- Không ghép đầu vào thành câu lệnh shell.
- Không tin file cấu hình hoặc thư mục do người gọi ghi được.
- Xử lý symlink, file tạm và lỗi theo thiết kế an toàn.
- Ghi nhận kết quả mà không để lộ secret.

Nếu wrapper chỉ chuyển nguyên chuỗi người dùng nhập vào shell dưới root, nó không làm hẹp quyền.

## 6. Một chính sách mẫu cho thao tác restart

Giả định:

- Máy đã được xác minh có host matching là `orders-prod-01`.
- Thành viên `orders-ops` dùng tài khoản cá nhân.
- Đường dẫn `systemctl` trên máy là `/usr/bin/systemctl`.
- Service, drop-in, chương trình thực thi và dependency đã được review quyền sở hữu.
- Yêu cầu là restart đúng `orders-api.service`.
- Membership được quản lý theo thời hạn bên ngoài file sudoers.

Nội dung minh họa cho `/etc/sudoers.d/orders-ops`:

```sudoers
User_Alias ORDERS_OPERATORS = %orders-ops
Cmnd_Alias ORDERS_RESTART = /usr/bin/systemctl restart orders-api.service

Defaults:ORDERS_OPERATORS timestamp_timeout=0

ORDERS_OPERATORS orders-prod-01 = (root) PASSWD: ORDERS_RESTART
```

Ý nghĩa của lựa chọn:

- Nhóm giúp gom những người có cùng nhu cầu vận hành.
- Host giới hạn nơi áp dụng theo cơ chế matching đã xác minh.
- Danh tính đích là root, không phải một danh sách tài khoản tùy ý.
- Lệnh và tham số được liệt kê cụ thể.
- `PASSWD` đặt yêu cầu xác thực cho command specification này.
- `timestamp_timeout=0` yêu cầu xác thực lại cho mỗi lần gọi cần xác thực, thay vì dựa vào khoảng cache thông thường.

`Defaults:ORDERS_OPERATORS` áp dụng theo người dùng thuộc alias; nó có thể ảnh hưởng cả những lần gọi sudo khác của cùng người dùng, không chỉ alias lệnh restart. Phải đánh giá ảnh hưởng khi hợp nhất với cấu hình hiện tại.

Mẫu này không tự:

- Kiểm tra ticket đã được duyệt.
- Đảm bảo danh tính đã dùng MFA.
- Tự hết hạn membership của người vận hành.
- Ghi đầy đủ mọi hoạt động trong một phiên tương tác.
- Loại bỏ quyền rộng đã tồn tại từ một nhóm hoặc nguồn policy khác.

Những yêu cầu đó cần cơ chế tương ứng và kiểm thử tích hợp.

## 7. Môi trường thực thi, xác thực và automation

### 7.1. Môi trường là một phần của ranh giới tin cậy

Các biến môi trường có thể ảnh hưởng đến việc chọn executable, nạp thư viện, chọn cấu hình hoặc hành vi của chương trình. Trong baseline phù hợp, thường cần xem xét:

| Cấu hình/cơ chế | Mục đích | Điều cần lưu ý |
| --- | --- | --- |
| `env_reset` | Giảm môi trường được truyền sang lệnh đặc quyền | Không tự bảo vệ mọi ứng dụng khỏi cấu hình do người dùng kiểm soát |
| `secure_path` | Dùng PATH do quản trị viên xác định | Không làm script gọi đường dẫn tùy ý trở nên an toàn |
| `env_keep` | Giữ lại biến thực sự cần thiết | Mỗi biến giữ lại cần có lý do và đánh giá tác động |
| `SETENV` | Cho phép điều khiển môi trường ở phạm vi được cấp | Có thể làm rộng quyền; không bật theo thói quen |
| `use_pty` | Chạy lệnh qua pseudo-terminal trong các trường hợp phù hợp | Không đồng nghĩa đã có lưu trữ I/O hoặc session recording hoàn chỉnh |

Không sao chép một khối `Defaults` toàn cục vào production mà chưa xem baseline hiện tại và tác động đến automation. Một thay đổi bảo mật đúng về ý định vẫn có thể làm hỏng luồng vận hành nếu không kiểm thử.

### 7.2. PASSWD, NOPASSWD và cache xác thực

`PASSWD` và `NOPASSWD` điều khiển yêu cầu xác thực trong chính sách; chúng không quyết định lệnh được cấp rộng hay hẹp. Một lệnh cực rộng với `PASSWD` vẫn là quyền cực rộng sau khi người dùng xác thực.

Mặc định thông thường, sudo xác thực người gọi bằng thông tin xác thực của người gọi. Các tùy chọn hệ thống có thể thay đổi hành vi này, vì vậy cần xác nhận cấu hình thực tế thay vì giả định đang nhập mật khẩu root.

`NOPASSWD` có thể cần cho một tác vụ tự động được thiết kế rõ ràng. Khi dùng, cần tối thiểu:

- Danh tính automation riêng với owner cụ thể.
- Lệnh và tham số hẹp.
- Credential hoặc cơ chế định danh được quản lý, luân chuyển và thu hồi.
- Không có đường đăng nhập tùy ý ngoài nhu cầu automation.
- Log và cảnh báo cho hành vi khác với baseline.

Không giải quyết lỗi một job tự động bằng cách thêm `NOPASSWD: ALL`.

### 7.3. Non-interactive không phải phép thử quyền độc lập

`sudo -n` yêu cầu không hỏi mật khẩu. Một lệnh có thể được policy cho phép nhưng vẫn thất bại với `-n` vì cần xác thực và không có credential cache phù hợp.

Vì vậy phải phân biệt:

- Policy không cấp quyền cho command line đó.
- Policy cấp quyền nhưng yêu cầu xác thực.
- Xác thực thất bại.
- Lệnh đã được sudo chạy nhưng bản thân lệnh trả lỗi.

Mỗi loại lỗi có hướng xử lý khác nhau.

## 8. Triển khai và kiểm tra cú pháp

Sử dụng `visudo` để chỉnh sửa và kiểm tra cấu hình sudoers. Không dùng editor thông thường để thay file production rồi hy vọng sudo sẽ đọc được.

Quy trình triển khai nên có:

1. Ticket mô tả tác vụ, nhóm được cấp và tài sản trong phạm vi.
2. Review nội dung policy và các dependency của lệnh.
3. Kiểm tra cú pháp trước khi cài đặt.
4. Triển khai qua cơ chế quản lý cấu hình có lịch sử thay đổi.
5. Kiểm tra cấu hình tổng hợp trên máy đích.
6. Kiểm thử bằng danh tính đại diện.
7. Lưu bằng chứng, giám sát và theo dõi thời hạn thu hồi.

Trong lab, quản trị viên đã có quyền bootstrap có thể dùng:

```bash
visudo -f /root/orders-ops.sudoers
visudo -cf /root/orders-ops.sudoers
install -o root -g root -m 0440 /root/orders-ops.sudoers /etc/sudoers.d/orders-ops
visudo -c
```

Đây là các bước dành cho tài khoản quản trị có sẵn quyền phù hợp, không phải những lệnh được trao cho nhóm `orders-ops`. File mẫu tự khai báo các alias mà nó dùng để có thể kiểm tra độc lập trong ví dụ.

Cần chú ý:

- Một file riêng parse thành công chưa chứng minh cấu hình tổng hợp hợp lệ.
- Cần xác nhận file chính có include thư mục tương ứng và tên file được cơ chế include xử lý.
- Tránh tên fragment chứa dấu chấm hoặc hậu tố backup trong cơ chế `includedir` thông thường, vì các tên như vậy có thể bị bỏ qua.
- Owner và permission phải phù hợp yêu cầu của bản phân phối và chính sách hệ thống.
- Chính sách từ LDAP/SSSD hoặc nguồn tập trung khác không được kiểm tra đầy đủ chỉ bằng việc đọc một fragment cục bộ.
- Trước thay đổi có thể ảnh hưởng quyền quản trị, chuẩn bị kênh khôi phục đã được kiểm soát và xác minh.

Không đóng kênh quản trị hiện tại trước khi kiểm thử thành công bằng một phiên mới. Kênh khôi phục vẫn phải có owner, kiểm soát truy cập và log; không tạo một tài khoản root dùng chung không kiểm toán để làm đường dự phòng.

## 9. Kiểm thử quyền hiệu lực

Kiểm tra cú pháp trả lời “file có được phân tích hợp lệ không”. Kiểm thử quyền hiệu lực trả lời “danh tính này thực sự có thể làm gì trên máy này”.

### 9.1. Kiểm tra từ tài khoản được cấp

Trong một phiên mới của người dùng đại diện:

```bash
id
sudo -l
```

`id` giúp kiểm tra nhóm mà phiên hiện tại đang thấy. Thay đổi membership ở nguồn danh tính có thể chưa xuất hiện trong phiên cũ hoặc trong cache của hệ thống.

`sudo -l` giúp xem quyền được policy hiệu lực công bố cho người dùng trên máy đó. Nếu kết quả vẫn có một quy tắc rộng như quyền chạy mọi lệnh, fragment hẹp mới thêm chưa tạo ra least privilege.

Một quản trị viên được phép kiểm tra thay người dùng có thể dùng:

```bash
sudo -l -U alice
```

Lệnh này cần quyền phù hợp. Không yêu cầu người dùng tự có đặc quyền kiểm tra tùy ý các tài khoản khác.

### 9.2. Ma trận ca kiểm thử

| Ca kiểm thử | Kết quả mong đợi | Mục đích |
| --- | --- | --- |
| Thành viên hợp lệ chạy đúng lệnh restart đã cấp | Được phép sau xác thực cần thiết | Xác nhận happy path |
| Thành viên hợp lệ yêu cầu restart service khác | Bị từ chối | Kiểm tra phạm vi service |
| Thành viên hợp lệ thêm service thứ hai vào command line | Bị từ chối | Kiểm tra giới hạn tham số |
| Thành viên hợp lệ yêu cầu chạy shell dưới root | Bị từ chối nếu không có grant khác | Phát hiện quyền rộng còn sót |
| Người ngoài nhóm yêu cầu cùng lệnh | Bị từ chối | Kiểm tra chủ thể |
| Người đã bị thu hồi, trong phiên mới và sau xử lý cache theo thiết kế | Bị từ chối | Xác nhận thu hồi |
| Người dùng trên máy ngoài phạm vi | Không nhận grant này | Kiểm tra host và triển khai |
| Lệnh bị sudo từ chối | Có bằng chứng phù hợp trong log | Kiểm tra quan sát sự kiện |

Có thể dùng chế độ list để kiểm tra một command line mà chưa thực thi nó:

```bash
sudo -l -- /usr/bin/systemctl restart orders-api.service
sudo -l -- /usr/bin/systemctl restart sshd.service
sudo -l -- /usr/bin/systemctl restart orders-api.service sshd.service
```

Chế độ list hữu ích cho kiểm tra policy, nhưng chưa thay thế việc thực thi trong lab: nó không chứng minh service restart thành công hoặc log runtime đầy đủ.

Chỉ thực thi ca restart trên lab hoặc trong thay đổi đã được phê duyệt, vì restart có thể làm gián đoạn dịch vụ:

```bash
sudo -k
sudo -- /usr/bin/systemctl restart orders-api.service
```

`sudo -k` làm mất hiệu lực timestamp xác thực trong phạm vi mà lệnh đó tác động theo cấu hình. Nó không thu hồi membership, không xóa grant trong policy và không kết thúc một tiến trình đặc quyền đang chạy.

Sau ca kiểm thử, kiểm tra trạng thái dịch vụ bằng cơ chế quan sát đã được cấp sẵn. Không thêm quyền quản trị đa năng chỉ để tiện xem kết quả.

### 9.3. Phân biệt lỗi lệnh với lỗi cấp quyền

Nếu sudo cho phép gọi `systemctl` nhưng service không tồn tại, đó có thể là lỗi vận hành của lệnh. Nếu người dùng không thuộc nhóm mà phiên nhìn thấy, đó có thể là vấn đề membership hoặc cache. Nếu command line không khớp policy, cần xem đường dẫn và tham số.

Không sửa policy rộng hơn trước khi biết lớp nào gây lỗi. Thu thập thông báo đã loại bỏ dữ liệu nhạy cảm, quyền hiệu lực, danh tính phiên và sự kiện log tương ứng.

## 10. Kết nối với JIT và quy trình phê duyệt

Một file sudoers cố định thường mô tả quyền theo cấu hình hiện tại; nó không tự vận hành toàn bộ quy trình Just-in-Time.

Một luồng JIT có thể tổ chức như sau:

```text
Yêu cầu có ticket
    -> Phê duyệt đúng người và phạm vi
    -> Cấp entitlement/membership có thời hạn
    -> Làm mới phiên hoặc nhận quyền theo cơ chế đã thiết kế
    -> Thực hiện lệnh sudo được giới hạn
    -> Hết hạn và thu hồi entitlement
    -> Xác minh quyền hiệu lực, đối chiếu log
```

Các điểm phải quyết định rõ:

- Thời hạn bắt đầu từ lúc duyệt hay lúc người dùng kích hoạt?
- Khi hết hạn, membership và cache được xử lý thế nào?
- Phiên cũ có còn giữ thông tin nhóm hay không?
- Nếu workflow cấp quyền thành công nhưng bước ghi audit thất bại thì xử lý ra sao?
- Ai chịu trách nhiệm khi việc thu hồi bị lỗi?
- Một tiến trình đặc quyền đã chạy sẽ được xử lý thế nào?

Rút một quy tắc hoặc xóa membership chủ yếu ảnh hưởng các quyết định cấp quyền tiếp theo. Nó không tự dừng shell, service, job hoặc tiến trình đã được khởi tạo. Vì vậy, tránh cấp shell root nếu nhu cầu chỉ là một thao tác ngắn.

MFA, phê duyệt ticket và command allowlist là các lớp có chức năng khác nhau. Không coi một lớp đã có là bằng chứng rằng các lớp còn lại cũng đã được thực thi.

## 11. Ghi log và bằng chứng kiểm toán

Để tái dựng một hoạt động đặc quyền, cần nối được tối thiểu:

- Danh tính gốc và nguồn xác thực.
- Máy đích, thời điểm và thông tin phiên thích hợp.
- Danh tính đích được dùng để chạy lệnh.
- Command line được yêu cầu.
- Quyết định cho phép hoặc từ chối.
- Kết quả thực thi khi hệ thống thu thập được.
- Ticket/phê duyệt và entitlement đã cấp.
- Phiên bản policy có hiệu lực tại thời điểm đó.

Không giả định log cục bộ luôn ghi đầy đủ exit status hoặc mọi subcommand của chương trình. Cấu hình ghi log, phiên bản và cơ chế thu thập quyết định loại bằng chứng sẵn có. Nếu cần thông tin cụ thể, phải cấu hình và kiểm thử sự kiện đó.

Tùy nền tảng, log có thể đến journal, cơ chế syslog hoặc dịch vụ log tập trung. Xác định nơi nhận log bằng cấu hình thực tế; không mặc định mọi bản Linux đều dùng cùng một file.

### 11.1. Log lệnh khác với log phiên

Một sự kiện cho biết người dùng được chạy shell không cho biết đầy đủ mọi việc họ đã làm bên trong shell. Tương tự, một lệnh có thể gọi chương trình khác mà command log ban đầu không mô tả hết.

Nếu rủi ro yêu cầu I/O logging hoặc session recording, phải thiết kế thêm:

- Loại input/output cần ghi.
- Cách liên kết bản ghi với sự kiện sudo.
- Truyền và lưu trữ log ngoài máy đích.
- Quyền đọc bản ghi, thời hạn lưu và khả năng chống sửa.
- Ảnh hưởng khi nơi nhận log không khả dụng.
- Bảo vệ mật khẩu, token và dữ liệu nhạy cảm có thể xuất hiện trong bản ghi.

Không truyền secret qua tham số lệnh để “tiện tự động hóa”; command line có thể xuất hiện trong log và các cơ chế quan sát tiến trình.

### 11.2. Bằng chứng review định kỳ

Một lần review nên đối chiếu:

| Nguồn | Câu hỏi |
| --- | --- |
| Policy đang có hiệu lực | Quyền nào đang được trao? |
| Danh sách nhóm/entitlement | Ai thực sự nhận được quyền? |
| Lịch sử sử dụng | Quyền có được dùng và có dùng đúng mục đích không? |
| Danh mục tài sản | Host, service và owner còn đúng không? |
| Ticket và ngoại lệ | Lý do cấp quyền còn hiệu lực không? |
| Kết quả thu hồi | Quyền đã hết hạn có thực sự mất hiệu lực không? |

“Không thấy dùng trong log” chỉ là một tín hiệu để điều tra hoặc thu hẹp quyền. Trước khi kết luận, cần biết nguồn log có đầy đủ và còn trong thời hạn lưu hay không.

## 12. Những lỗi thiết kế thường gặp

### 12.1. Cấp toàn quyền qua nhóm vận hành chung

Người dùng vừa thuộc `orders-ops`, vừa thuộc một nhóm quản trị có quyền sudo rộng. Dù policy Orders rất hẹp, quyền hiệu lực vẫn có thể rộng.

Cách xử lý: kiểm kê mọi nguồn cấp quyền và kiểm tra `sudo -l` trên danh tính đại diện. Tách vai trò vận hành ứng dụng khỏi vai trò quản trị nền tảng.

### 12.2. Cấp quyền sửa script rồi cho chạy script bằng sudo

Allowlist chỉ có một đường dẫn, nhưng người được cấp quyền sửa được nội dung script hoặc thư mục chứa nó.

Cách xử lý: kiểm soát owner, permission và chuỗi thư mục; phân tách người phát triển, người phê duyệt và danh tính thực thi phù hợp với rủi ro.

### 12.3. Cho phép công cụ đọc có editor hoặc pager

Người viết policy cho rằng “xem log” chắc chắn là read-only. Chương trình thực tế có thể gọi thành phần tương tác với quyền kế thừa.

Cách xử lý: xem đầy đủ hành vi chương trình, chế độ chạy và dữ liệu nó có thể truy cập. Ưu tiên nền tảng log tập trung với phân quyền đọc hoặc giao diện hẹp đã được đánh giá.

### 12.4. Sửa lỗi automation bằng NOPASSWD quá rộng

Job thất bại vì không có terminal hoặc không thể nhập mật khẩu. Người vận hành thêm quyền chạy mọi lệnh không cần xác thực.

Cách xử lý: xác định tác vụ máy thực sự cần; dùng danh tính automation riêng, phạm vi lệnh hẹp và cơ chế credential phù hợp.

### 12.5. Policy đúng nhưng không được include

Fragment có tên không được cơ chế include nạp, file chính không có include tương ứng hoặc cấu hình được triển khai nhầm host.

Cách xử lý: kiểm tra cả cấu hình tổng hợp và quyền hiệu lực trên đúng máy, không chỉ nhìn file trong repository.

### 12.6. Tưởng thu hồi membership là kết thúc mọi đặc quyền

Người dùng bị xóa khỏi nhóm nhưng phiên cũ còn giữ thông tin nhóm hoặc một tiến trình đặc quyền đã chạy vẫn tiếp tục hoạt động.

Cách xử lý: thiết kế rõ việc làm mới danh tính, xử lý cache, phiên và tiến trình; kiểm thử thu hồi như một ca bắt buộc.

### 12.7. Chỉ review cú pháp

`visudo` báo hợp lệ nhưng lệnh được cho phép có thể thực thi mã do người dùng kiểm soát.

Cách xử lý: review cả ngữ nghĩa của lệnh và dependency. Cú pháp hợp lệ là điều kiện cần, không phải bằng chứng quyền đã tối thiểu.

## 13. Bài thực hành: quyền restart có thời hạn

### Bối cảnh

Nhóm Orders có mười kỹ sư. Chỉ hai người trực ca được restart `orders-api.service` trên một máy lab mô phỏng production. Quyền được cấp trong hai giờ theo ticket và không bao gồm sửa unit, thay binary hoặc quản trị service khác.

### Công việc

1. Viết yêu cầu cấp quyền dưới dạng chủ thể, tài sản, thao tác, danh tính đích, xác thực, thời hạn và bằng chứng.
2. Xác minh đường dẫn `systemctl`, cách host matching hoạt động và nguồn policy trên máy lab.
3. Kiểm tra owner và quyền ghi của unit, drop-in, executable, script và dependency của service.
4. Soạn fragment sudoers hẹp, dùng nhóm và alias dễ review.
5. Kiểm tra cú pháp file riêng và cấu hình tổng hợp.
6. Kiểm tra quyền hiệu lực bằng một tài khoản trực ca và một tài khoản ngoài ca.
7. Chạy ma trận kiểm thử trong lab, bao gồm tham số thêm và service ngoài phạm vi.
8. Thu hồi quyền sau thời hạn, tạo phiên mới theo thiết kế và xác minh bị từ chối.
9. Đối chiếu sự kiện cấp, sử dụng và thu hồi với cùng ticket.
10. Ghi lại ảnh hưởng của phiên cũ và cách hệ thống xử lý tiến trình đã chạy.

### Tiêu chí hoàn thành

- Người trực ca thực hiện được đúng thao tác cần thiết.
- Người ngoài ca không nhận được quyền từ grant này.
- Không có quyền rộng khác làm vô hiệu giới hạn vừa thiết kế.
- Người vận hành không thể sửa dependency để biến restart thành thực thi nội dung ngoài phạm vi.
- Có bằng chứng cho phép, từ chối và thu hồi.
- Policy hợp lệ trong cấu hình tổng hợp và có phương án khôi phục đã kiểm soát.
- Người review có thể giải thích vì sao từng lệnh và từng tham số được cấp.

## 14. Tự kiểm tra

**Vì sao `PASSWD: ALL` không đáp ứng least privilege?**

Vì xác thực chỉ kiểm tra điều kiện được thực hiện quyền. Sau khi vượt qua điều kiện đó, tập thao tác vẫn là toàn bộ lệnh mà quy tắc cấp.

**Vì sao chỉ kiểm tra fragment sudoers là chưa đủ?**

Vì quyền hiệu lực có thể đến từ nhiều file, nhiều nhóm hoặc nguồn policy tập trung. Fragment cũng có thể không được include trên máy đích.

**Một lệnh restart service có thể nguy hiểm khi nào?**

Khi người được cấp quyền có thể ảnh hưởng đến unit, script, binary, cấu hình hoặc dependency mà service tin và sử dụng khi khởi động.

**Tại sao `sudo -n` thất bại chưa chứng minh policy từ chối lệnh?**

Vì lệnh có thể được cho phép nhưng cần xác thực, trong khi chế độ non-interactive không được hỏi mật khẩu.

**Thu hồi quyền sudo có tự dừng tiến trình đã chạy không?**

Không. Cần cơ chế quản lý phiên và tiến trình riêng nếu yêu cầu thu hồi bao gồm cả hoạt động đã được khởi tạo.

**Dấu hiệu nào cho thấy chính sách thực sự vận hành được?**

Một người đúng vai trò hoàn thành được tác vụ; người, host và tham số ngoài phạm vi bị từ chối; dependency được bảo vệ; quyền hết hạn thực sự bị thu hồi; và chuỗi sự kiện có thể được tái dựng bằng bằng chứng.

## 15. Kết luận

Thiết kế sudo policy bắt đầu từ tác vụ vận hành cụ thể và kết thúc ở quyền hiệu lực đã được kiểm chứng. Cần giới hạn danh tính, máy, runas, lệnh và tham số; đồng thời kiểm soát những đầu vào mà lệnh đặc quyền sử dụng.

Trong chương trình PAM, sudo policy là một lớp thực thi least privilege. Nó cần phối hợp với quản lý tài khoản cá nhân, entitlement có thời hạn, quản lý credential, giám sát phiên, log tập trung và review định kỳ để quyền đặc biệt vừa đủ dùng, có thể truy vết và có thể thu hồi.

# sudoers review

## Mục tiêu bài học

Rà soát sudoers là xác định **ai có thể thực hiện thao tác gì, trên máy nào, dưới danh tính nào và theo điều kiện nào** thông qua sudo. Đọc một dòng có chữ `NOPASSWD` hoặc thấy cấu hình không có `ALL` chưa đủ để kết luận quyền an toàn. Cần đối chiếu toàn bộ chính sách hiệu lực với quyền thực tế mà lệnh, tham số, file phụ thuộc và môi trường thực thi mang lại.

Trong quản lý truy cập đặc quyền, sudoers review giúp phát hiện quyền quản trị tồn dư, giới hạn công việc được phép, gắn quyền với người chịu trách nhiệm, hỗ trợ truy cập có thời hạn và giữ bằng chứng cho kiểm toán. Ví dụ xuyên suốt bài học là một nhóm trực vận hành chỉ cần khởi động lại đúng một dịch vụ báo cáo trên hai máy production.

Sau bài học, người học có thể:

- Phân tích một mục cấp quyền theo user/group, host, Runas, command, arguments, tag và Defaults.
- Tìm các quyền rộng, quyền chồng lấn và đường leo thang gián tiếp.
- Đề xuất chính sách ít quyền hơn mà vẫn đáp ứng công việc.
- Kiểm chứng cú pháp, quyền hiệu lực, các trường hợp phải bị từ chối và dấu vết sử dụng.
- Lập hồ sơ phê duyệt, triển khai, thu hồi và tái kiểm tra.

Tên chương “Linux PAM” ở đây chỉ nội dung quản lý đặc quyền trên Linux trong module Privileged Access Management. Cơ chế Linux-PAM dùng cho xác thực, account và session có liên quan nhưng là một lớp khác. Một cấu hình xác thực tốt không tự làm cho quyền sudo quá rộng trở nên an toàn.

## 1. Cần rà soát quyền hiệu lực, không chỉ file vừa chỉnh

Một người có thể nhận quyền từ user trực tiếp, nhiều nhóm, nhiều file include hoặc hệ thống chính sách tập trung. Quyền hiệu lực phải được xét trong tổ hợp đó.

~~~text
Danh tính và nhóm thực tế
          |
          v
Nguồn chính sách sudo được cấu hình
          |
          v
Host + Runas + command + arguments + tags + Defaults
          |
          v
Lệnh được phép chạy
          |
          v
File phụ thuộc, môi trường và khả năng thoát ra lệnh khác
          |
          v
Đặc quyền thực tế người dùng có thể đạt được
~~~

Một dòng cấp quyền hẹp không bù được một dòng rộng còn tồn tại ở nơi khác. Ví dụ, thêm quyền chỉ restart một service cho Alice không có tác dụng giảm quyền nếu Alice vẫn thuộc nhóm được chạy mọi lệnh với root.

Trước mỗi review, chốt phạm vi: các máy cần xét, tài khoản và nhóm, nguồn policy, tác vụ nghiệp vụ, thời hạn và người phê duyệt. Nếu không thu thập được chính sách từ một nguồn đang được sử dụng, ghi rõ phần chưa xác minh; không kết luận rằng toàn bộ quyền đã được rà soát.

## 2. Đọc một dòng sudoers theo đúng thành phần

Dạng đơn giản thường gặp:

~~~sudoers
user_or_group host = (runas_user:runas_group) tags: command arguments
~~~

Ví dụ:

~~~sudoers
%report-oncall report-01 = (root) PASSWD: /usr/bin/systemctl restart acme-report.service
~~~

Ý nghĩa của từng phần:

| Thành phần | Ý nghĩa trong ví dụ | Câu hỏi review |
|---|---|---|
| `%report-oncall` | Thành viên nhóm report-oncall | Danh sách thực tế gồm ai? Ai được thêm thành viên? |
| `report-01` | Máy áp dụng quy tắc | Tên host có khớp cách sudo nhận diện máy không? |
| `(root)` | Danh tính đích là root | Công việc có cần root không? Có quyền Runas khác chồng lên không? |
| `PASSWD:` | Yêu cầu xác thực theo chính sách sudo hiệu lực | Xác thực bằng gì, cache bao lâu, có Defaults thay đổi ý nghĩa không? |
| Đường dẫn lệnh | Chương trình được phép | File và thư mục cha có được bảo vệ không? |
| Tham số | Thao tác và service cụ thể | Có thể thay đối tượng, thêm tùy chọn hoặc làm lệnh chạy chương trình khác không? |

Ví dụ dùng đường dẫn và tên máy minh họa. Trước khi đưa vào hệ thống thật, xác minh executable, phiên bản sudo, cơ chế nhận diện host và cách phân giải nhóm trên chính máy đích.

### 2.1. User và group

Các dạng cần chú ý:

~~~sudoers
alice ALL = (root) /usr/bin/id
%linux-ops ALL = (ALL:ALL) ALL
~~~

Dòng thứ hai cho phép nhóm linux-ops chạy mọi lệnh dưới mọi user và group đích được chỉ định. Đây là quyền quản trị rất rộng, không chỉ là khả năng chạy vài thao tác vận hành.

Khi review group, cần biết cả thành viên trực tiếp, nhóm lồng nhau nếu hệ thống danh tính có hỗ trợ, người quản trị membership và thời gian đồng bộ. Đầu ra `getent group` đơn lẻ không phải lúc nào cũng thể hiện đầy đủ membership được tính từ danh bạ tập trung. Kết hợp dữ liệu danh tính có thẩm quyền với kết quả `id` và phiên đăng nhập thực của tài khoản.

Không dùng tài khoản quản trị chia sẻ để thay cho định danh cá nhân. Nếu nhiều người cùng dùng một account, log sudo chỉ cho biết account đó đã thực hiện lệnh; việc quy trách nhiệm cho từng người cần thêm cơ chế định danh đầu vào.

### 2.2. Host

`ALL` ở vị trí host nghĩa là quy tắc có thể áp dụng trên mọi host mà policy đó được sử dụng. Nó không tự đồng nghĩa với mọi command.

Dùng host cụ thể hoặc Host_Alias giúp diễn đạt phạm vi rõ hơn, nhưng cần kiểm tra thực tế trên từng máy. Các thiết lập liên quan hostname, FQDN, DNS và cách phân phối policy có thể làm một quy tắc không khớp hoặc khớp rộng hơn dự kiến.

Một file bị copy sang máy ngoài phạm vi vẫn có thể cấp quyền nếu trường host là `ALL`. Review cả điều kiện trong policy lẫn phạm vi mà công cụ quản lý cấu hình phân phối file.

### 2.3. Runas

`(root)` giới hạn user đích về root. `(appsvc)` cho phép chạy dưới appsvc. `(ALL)` mở rộng user đích; `(ALL:ALL)` còn cho phép chọn group đích rộng hơn.

Nếu không ghi Runas, cấu hình thông thường dùng user đích mặc định là root; cần xem thiết lập `runas_default` hiệu lực trước khi kết luận. Không xem việc bỏ ngoặc Runas là một cách giảm đặc quyền.

Chạy với appsvc không nhất thiết ít rủi ro: appsvc có thể đọc secret, ghi dữ liệu sản xuất hoặc gọi dịch vụ hạ tầng khác. Đánh giá quyền của danh tính đích theo tài sản mà nó truy cập được.

### 2.4. Command và arguments

Hai quy tắc sau khác nhau đáng kể:

~~~sudoers
alice ALL = (root) /usr/bin/systemctl
alice ALL = (root) /usr/bin/systemctl restart acme-report.service
~~~

Trong dạng thông thường, khai báo đường dẫn command mà **không chỉ định arguments** cho phép command chạy với bất kỳ arguments nào. Vì vậy dòng đầu không có nghĩa là chỉ được gọi systemctl không tham số.

Muốn cho phép đúng một executable chạy **không có arguments**, sudoers có cú pháp chuỗi arguments rỗng:

~~~sudoers
alice ALL = (root) /usr/local/libexec/acme-report-healthcheck ""
~~~

Khi sử dụng, người dùng gọi executable không kèm tham số; `""` ở đây là cú pháp của policy. Quy tắc này chỉ có ích nếu bản thân chương trình đã được rà soát và người dùng không thể thay đổi nó hoặc các đầu vào khiến nó thực thi hành vi đặc quyền ngoài ý muốn.

Sudoers khớp command và arguments theo cú pháp chính sách của sudo, không hiểu ý định nghiệp vụ của người viết. Wildcard trong arguments có thể khớp cả khoảng trắng và phần arguments bổ sung. Không suy ra rằng `*` chỉ đại diện cho đúng một tên file hoặc một tham số shell.

~~~sudoers
alice ALL = (root) /usr/bin/systemctl *
alice ALL = (root) /usr/bin/cat /var/log/acme/*
~~~

Dòng thứ nhất mở nhiều chức năng hơn restart. Dòng thứ hai cần phân tích cách arguments được khớp, khả năng thêm đường dẫn và khả năng truy cập dữ liệu khác. Với glob, không dùng trực giác từ tên file để thay cho thử nghiệm cụ thể.

Một số phiên bản sudo hỗ trợ biểu thức chính quy trong policy. Chỉ dùng khi tài liệu và kiểm thử của phiên bản được triển khai xác nhận cú pháp; không copy regex từ môi trường mới sang toàn bộ fleet rồi mặc định rằng nó có hiệu lực giống nhau.

## 3. Thu thập baseline theo cách không thực thi tác vụ đặc quyền

Lệnh trong phần này là ví dụ cho reviewer đã được cấp quyền phù hợp. Một số thao tác đọc policy hoặc xem quyền của người khác cần quyền quản trị. Không bổ sung quyền sudo rộng chỉ để chạy checklist review.

### 3.1. Xác định phiên bản, danh tính và quyền được liệt kê

~~~bash
sudo -V
id
id alice
getent group report-oncall
sudo -l
sudo -ll
~~~

`sudo -V` cung cấp thông tin phiên bản; mức chi tiết có thể khác theo quyền người gọi và bản đóng gói. `sudo -l` liệt kê quyền của người đang thực hiện; `-ll` yêu cầu dạng dài khi được hỗ trợ.

Reviewer đủ thẩm quyền có thể xem policy của user khác:

~~~bash
sudo -ll -U alice
~~~

Không xem output của root hoặc reviewer là bằng chứng cho quyền của Alice nếu chưa kiểm tra đúng danh tính. Với danh tính tập trung, cần kiểm tra cả tình trạng membership và phiên đăng nhập đang dùng; thay đổi nhóm có thể chưa được phản ánh như dự kiến trong phiên cũ.

Khi đọc kết quả, thu thập:

- Danh sách Defaults đang áp dụng và các quy tắc command được liệt kê.
- Các user/group đích mà user có thể chọn.
- Những quyền rộng phát sinh từ nhóm phụ hoặc policy tập trung.
- Chênh lệch giữa quyền đã được phê duyệt và quyền hệ thống thực sự trả về.

### 3.2. Xác định đầy đủ nguồn chính sách

Một hệ thống thường có `/etc/sudoers` và các file trong `/etc/sudoers.d/`, nhưng sudo cũng có thể sử dụng nguồn policy khác theo cấu hình triển khai. Nếu có LDAP, SSSD hoặc cơ chế tập trung, phải lấy chính sách tương ứng từ nguồn đó.

Với policy file, theo dấu các chỉ thị include. `#include` và `#includedir` trong sudoers có ý nghĩa đặc biệt, không phải comment thông thường. Một số phiên bản cũng hỗ trợ dạng `@include` và `@includedir`.

Đối với includedir, cần lưu ý quy tắc chọn file và sắp xếp:

- Thứ tự xử lý là theo tên file, không phải một phép sắp xếp số theo ý người quản trị.
- Tên chứa dấu chấm hoặc kết thúc bằng dấu `~` thường bị bỏ qua theo cơ chế includedir của sudo.
- File tồn tại trên đĩa chưa chắc đã được nạp; file được nạp chưa chắc là nguồn cuối cùng áp dụng cho user.
- Include lồng nhau có thể bổ sung quyền mà reviewer bỏ sót nếu chỉ nhìn một thư mục.

Một file tên `70-acme-report.conf` có thể bị bỏ qua trong includedir do có dấu chấm. Chọn tên phù hợp với cơ chế nạp, rồi xác minh qua công cụ trên máy đích; không dựa vào việc file “trông giống cấu hình”.

Chạy kiểm tra cú pháp policy file bằng visudo, với quyền đọc cần thiết:

~~~bash
visudo -c
~~~

Khi kiểm tra riêng một candidate:

~~~bash
visudo -cf /path/to/candidate
~~~

Kiểm tra riêng một file không thay thế việc kiểm tra toàn bộ policy sau khi kết hợp include, alias và Defaults. Đồng thời, visudo không chứng minh nội dung chính sách tập trung từ nguồn khác đã được kiểm toán đầy đủ.

### 3.3. Kiểm tra bảo vệ file

Với quyền phù hợp, kiểm tra metadata và đường dẫn:

~~~bash
stat -c '%U:%G %a %n' /etc/sudoers /etc/sudoers.d
ls -ld /etc /etc/sudoers.d
namei -l /usr/bin/systemctl
~~~

Kiểm tra cả owner, mode, ACL và thư mục cha. Nếu người được cấp quyền có thể thay executable, script, symlink hay một thư mục chứa chúng, giới hạn command có thể bị vô hiệu hóa.

Không áp dụng chmod/chown hàng loạt chỉ vì một checklist đưa ra con số “chuẩn”. Đối chiếu yêu cầu của sudo, bản phân phối và hệ thống quản lý cấu hình; ghi nhận khác biệt và sửa bằng một thay đổi được kiểm soát.

## 4. Những mẫu cấu hình cần phân tích kỹ

### 4.1. ALL ở nhiều vị trí

~~~sudoers
%operations ALL = (ALL:ALL) NOPASSWD: ALL
~~~

Đọc đầy đủ: mọi thành viên operations có thể dùng policy này trên mọi host phù hợp, chạy mọi command dưới các user/group đích và không cần xác thực cho những command đó theo tag NOPASSWD.

Nếu nhóm thực sự là đội quản trị toàn quyền, có thể vẫn có nhu cầu nghiệp vụ. Khi đó review tập trung vào membership, phê duyệt, cơ chế kích hoạt có thời hạn, định danh cá nhân, logging và thu hồi. Không gắn nhãn “an toàn” chỉ vì tên nhóm là operations.

Nếu nhóm chỉ cần restart một dịch vụ, cấu hình này vượt xa nhiệm vụ và phải được thu hẹp.

### 4.2. NOPASSWD và cache xác thực

`NOPASSWD` bỏ yêu cầu password cho command được tag đó áp dụng; nó không có nghĩa command tự bị giới hạn hay được giám sát tốt hơn. Với tài khoản tương tác, cần giải thích tại sao yêu cầu xác thực bị bỏ.

`PASSWD` cũng không đồng nghĩa với việc luôn phải nhập lại password trên mỗi lệnh. Timestamp cache và các Defaults hiệu lực có thể cho phép dùng lại kết quả xác thực. Nếu yêu cầu là xác thực mỗi lần, phải kiểm tra thiết lập cache và quy trình vận hành tương ứng.

Theo cấu hình thông thường, sudo xác thực người gọi, không phải yêu cầu password của root. Các tùy chọn như `rootpw`, `targetpw` hoặc `runaspw` có thể thay đổi hành vi; cần đọc cấu hình thực tế.

Với automation, NOPASSWD có thể là lựa chọn có chủ đích khi không có phiên tương tác. Điều kiện review là danh tính máy rõ ràng, phạm vi command chặt, secret được bảo vệ, chủ sở hữu và log phù hợp. Không lưu password người trong script để cố đáp ứng yêu cầu xác thực.

### 4.3. Tag, thứ tự và nhiều quy tắc cùng khớp

Tag có thể được kế thừa trong danh sách command cho đến khi tag đối nghịch xuất hiện. Ví dụ:

~~~sudoers
alice ALL = (root) NOPASSWD: /usr/bin/id, PASSWD: /usr/bin/systemctl restart acme-report.service
~~~

Không đọc PASSWD hay NOPASSWD như một thuộc tính chung của cả file. Phải đọc phạm vi áp dụng của từng tag và các quy tắc khác cùng khớp.

Không có nguyên tắc chung “dòng cụ thể nhất luôn thắng”. Thứ tự nạp và quy tắc cùng khớp có thể ảnh hưởng kết quả, đặc biệt với tag hoặc việc cấp và loại trừ command. Một rule hẹp được thêm sau hoặc trước rule rộng không phải bằng chứng rằng quyền rộng đã bị thu hồi.

Sử dụng `sudo -l` cho user thực và kiểm tra các lời gọi cụ thể. Nếu quyền rộng vẫn xuất hiện, phải tìm nguồn và loại bỏ hoặc điều chỉnh tại nguồn đó.

### 4.4. Denylist không thay thế allowlist

~~~sudoers
alice ALL = (root) ALL, !/bin/sh
~~~

Cấu hình này vẫn có thể cho phép những shell khác, interpreter, editor hoặc chương trình thực thi command. Nó không tạo ra một tập quyền “mọi thứ trừ shell” đủ chặt để bảo vệ root.

Cho phép mọi lệnh rồi cấm một vài executable dễ bỏ sót đường tương đương. Review nên bắt đầu từ các thao tác cần thiết và allowlist cụ thể. Không coi một dấu `!` là ranh giới chống leo thang khi tập quyền nền vẫn rất rộng.

### 4.5. Alias giúp tổ chức, không tự giảm đặc quyền

~~~sudoers
User_Alias REPORT_ONCALL = %report-oncall
Host_Alias REPORT_PROD = report-01, report-02
Cmnd_Alias REPORT_RESTART = /usr/bin/systemctl restart acme-report.service
REPORT_ONCALL REPORT_PROD = (root) PASSWD: REPORT_RESTART
~~~

Alias làm policy dễ đọc hơn, nhưng phải mở rộng nội dung từng alias khi review. Một alias đặt tên READ_ONLY có thể vẫn chứa command ghi file hoặc chương trình có shell escape.

Theo dõi người sở hữu alias, những rule sử dụng nó và tác động lan truyền khi thay đổi. Thêm một command vào alias dùng chung có thể cấp quyền cho nhiều nhóm và host ngoài mục tiêu của yêu cầu thay đổi hiện tại.

## 5. Lệnh được phép có thể trở thành đường leo thang

Câu hỏi trung tâm là: **sau khi lệnh chạy với danh tính đích, người gọi còn điều khiển được điều gì?**

| Nhóm lệnh hoặc khả năng | Rủi ro cần kiểm tra | Hướng thu hẹp |
|---|---|---|
| Shell, interpreter, trình thực thi mã | Thực thi chương trình tùy ý với quyền đích | Tránh cấp nếu chỉ cần một thao tác nghiệp vụ cụ thể |
| Editor và pager tương tác | Shell escape, mở hoặc ghi file khác | Dùng cách xem không tương tác; nếu phải sửa, giới hạn quy trình và đường dẫn |
| Công cụ copy, ghi, giải nén | Thay file cấu hình, executable, khóa hoặc startup file | Giới hạn đối tượng, bảo vệ đường dẫn và kiểm tra tính năng thực thi phụ |
| Service manager | Chạy mã từ unit, script và cấu hình phụ thuộc | Chỉ cho thao tác cần thiết; bảo vệ toàn bộ dependency |
| Package manager hoặc công cụ cài đặt | Hook và script cài đặt chạy với quyền cao | Chuyển về quy trình triển khai có kiểm soát |
| Công cụ backup, đồng bộ, tìm kiếm | Thực thi helper, đọc secret hoặc ghi vào nơi đặc quyền | Rà soát options và đầu vào; không chỉ tên command |

Một lệnh có vẻ chỉ “xem dữ liệu” vẫn có thể gọi pager. Một công cụ xử lý văn bản có thể chạy chương trình khác. Một chương trình backup có thể đọc dữ liệu mà người dùng bình thường không được phép xem. Không đánh giá mức quyền bằng tên executable.

### 5.1. Chuỗi phụ thuộc của một service

Ngay cả quy tắc exact restart một service cũng có thể dẫn đến thực thi mã do người gọi kiểm soát:

~~~text
Quyền sudo restart service
              |
              v
systemd đọc unit và cấu hình
              |
              v
Unit gọi executable / script / interpreter
              |
              v
Mã hoặc đầu vào do user có quyền ghi
              |
              v
Mã chạy dưới danh tính service, có thể là root
~~~

Cần rà soát:

- Unit file, drop-in và symlink liên quan có bị user được cấp quyền sửa được không.
- Executable, script, module được nạp và thư mục cha có được bảo vệ không.
- EnvironmentFile, configuration, plugin hoặc hook có ảnh hưởng đến thực thi mã không.
- Dịch vụ chạy dưới user nào và có capabilities hoặc quyền dữ liệu gì.
- Việc restart có ảnh hưởng availability, gây mất tác vụ hoặc kích hoạt hành vi đặc biệt không.

Nếu report-oncall ghi được script mà một service root sẽ chạy khi restart, giới hạn arguments của systemctl không giải quyết được đường leo thang đó. Phải sửa quyền file hoặc thiết kế service trước khi chấp nhận policy.

### 5.2. Môi trường thực thi

Rà soát `SETENV`, `env_reset`, `env_keep`, `env_check`, `env_delete` và `secure_path` khi có trong cấu hình.

`SETENV` có thể cho phép người gọi tác động tới môi trường vượt ra ngoài kiểm tra thông thường của sudo. Rủi ro cụ thể tùy chương trình đích: biến môi trường có thể ảnh hưởng đường dẫn module, file cấu hình, helper hoặc hành vi của interpreter.

`secure_path` hỗ trợ kiểm soát PATH mà command nhận được, nhưng không chứng minh chương trình hoàn toàn không nạp mã hoặc cấu hình từ nơi user ghi được. `env_reset` cũng phải được xét cùng danh sách biến được giữ lại và cách lệnh xử lý chúng.

Với script wrapper, không dùng `eval`, không ghép chuỗi user thành command shell, dùng executable với đường dẫn rõ ràng và xác thực tất cả đầu vào. Một wrapper do người gọi sửa được hoặc truyền tùy ý command vào trong thì không tạo ra ranh giới hữu ích.

### 5.3. NOEXEC và digest

`NOEXEC` có thể hạn chế một số lần thực thi chương trình con trong các môi trường và chương trình được hỗ trợ. Nó không phải một sandbox tổng quát và không chặn việc chương trình đích tự đọc, ghi hoặc thay đổi tài nguyên đặc quyền. Không lấy NOEXEC làm cơ sở duy nhất để cấp quyền editor, interpreter hay công cụ có khả năng quản trị rộng.

Digest của command có thể hỗ trợ kiểm tra nội dung executable, nhưng cần quản lý việc thay phiên bản, đường dẫn và các điều kiện thực thi. Digest của executable không bao phủ tự động script, plugin, cấu hình hoặc helper mà nó sử dụng. Vẫn phải kiểm tra quyền ghi và dependency.

## 6. Một quy trình review có đầu ra rõ ràng

### Bước 1 — Lập bảng nhu cầu

Ví dụ yêu cầu đã được xác nhận:

| Thuộc tính | Nhu cầu |
|---|---|
| Người sử dụng | Thành viên report-oncall đã phê duyệt |
| Tài sản | report-01 và report-02 |
| Tác vụ | Restart acme-report.service khi xử lý sự cố |
| Danh tính đích | Root để thao tác system service |
| Ngoài phạm vi | Shell root, sửa unit, restart service khác, thay package |
| Thời hạn | Theo lịch trực và cơ chế kích hoạt được phê duyệt |
| Bằng chứng | Danh tính cá nhân, ticket, thời điểm, host, lệnh, kết quả kiểm tra |

Nếu yêu cầu nghiệp vụ chỉ là xem trạng thái, kiểm tra trước xem user thường đã làm được chưa. Không cấp sudo cho một thao tác không cần đặc quyền.

### Bước 2 — Lập bảng quyền hiện tại

Với mỗi grant, ghi nguồn policy, đối tượng được nhận, host, Runas, command/arguments, tag/Defaults và chủ sở hữu nghiệp vụ.

Đối chiếu với yêu cầu: quyền nào cần giữ, cần thu hẹp hoặc cần thu hồi. Ghi cả các grant không còn owner và các tài khoản đã nghỉ việc nhưng vẫn nằm trong nhóm.

### Bước 3 — Phân tích đường gián tiếp

Không dừng ở command line. Với từng quyền giữ lại, xác minh dependency, quyền ghi, secrets và khả năng chạy code khác. Khi không đủ bằng chứng để kết luận một command an toàn, ghi rõ giả định chưa kiểm tra và phần việc phải hoàn thành.

### Bước 4 — Thiết kế policy đề xuất

Ví dụ sau minh họa policy file cho đúng nhu cầu restart:

~~~sudoers
User_Alias REPORT_ONCALL = %report-oncall
Host_Alias REPORT_PROD = report-01, report-02
Cmnd_Alias REPORT_RESTART = /usr/bin/systemctl restart acme-report.service

Defaults:%report-oncall env_reset
Defaults:%report-oncall timestamp_timeout=0

REPORT_ONCALL REPORT_PROD = (root) PASSWD: REPORT_RESTART
~~~

Chỉ đưa ví dụ vào sử dụng sau khi kiểm tra:

- Hostname và đường dẫn systemctl đúng trên các máy.
- Không có alias trùng tên hoặc grant khác khiến quyền vẫn rộng.
- Các Defaults hiệu lực không làm sai yêu cầu xác thực.
- Unit và dependency đã được bảo vệ.
- Hành vi xác thực thực tế phù hợp với cơ chế đăng nhập và PAM của hệ thống.

`timestamp_timeout=0` nhằm tránh tái sử dụng timestamp theo cách thông thường cho các lần xác thực. Nó không tạo thêm MFA, không tự liên kết ticket và không thay thế kiểm thử hành vi của cấu hình xác thực hiện hành.

Cấu hình này cũng chưa tự thực hiện Just-in-Time. Nếu nhóm tồn tại thường trực và luôn có thành viên, quyền vẫn có thể thường trực. Để có JIT, cần hệ thống kích hoạt và thu hồi membership hoặc grant theo phê duyệt, có thời hạn, có xác minh hiệu lực sau khi đóng cửa sổ truy cập.

### Bước 5 — Kiểm tra cú pháp và quyền hiệu lực

Kiểm tra candidate rồi toàn bộ policy bằng visudo. Sau đó, trên môi trường kiểm thử tương đương, dùng chính user thuộc nhóm được giao và xem `sudo -ll`.

Cần phân biệt hai kiểm tra:

- **Syntax PASS:** sudo hiểu cấu hình.
- **Authorization PASS:** quyền được cấp và bị từ chối đúng thiết kế.

Cả hai chưa thay thế kiểm tra hành vi thực của chương trình và dependency.

### Bước 6 — Triển khai, quan sát và thu hồi

Triển khai qua cơ chế quản lý cấu hình có owner và lịch sử thay đổi. Xác minh trên từng nhóm máy thay vì chỉ xem kết quả pipeline phân phối file.

Sau triển khai, kiểm tra quyền của người được cấp, một người ngoài phạm vi, đường thu hồi và dấu vết trên hệ thống log. Có kế hoạch quay lại baseline đã xác nhận nếu policy làm gián đoạn vận hành hoặc cấp sai quyền.

Không đóng toàn bộ phiên quản trị đã được xác minh trước khi kiểm tra xong đường truy cập cần thiết. Phiên dự phòng phải nằm trong quy trình truy cập được phê duyệt và được đóng sau khi hoàn tất, tránh trở thành một kênh đặc quyền tồn dư.

## 7. Ma trận kiểm thử: cả cho phép và từ chối

Với policy mẫu, các kỳ vọng tối thiểu là:

| Trường hợp | Kỳ vọng | Ý nghĩa |
|---|---|---|
| User hợp lệ, report-01, root, restart đúng service | Được cấp quyền | Tác vụ cần thiết hoạt động |
| User hợp lệ, report-02, root, cùng thao tác | Được cấp quyền | Phạm vi hai host đúng |
| User hợp lệ, restart service khác | Từ chối | Không thay được đối tượng |
| User hợp lệ, stop hoặc edit đúng service | Từ chối | Không mở rộng động từ |
| User hợp lệ, gọi systemctl không arguments | Từ chối | Không có quyền command quá rộng |
| User hợp lệ, thêm tùy chọn ngoài policy | Từ chối | Arguments không bị mở rộng |
| User hợp lệ, yêu cầu shell root | Từ chối | Không có grant shell khác |
| User hợp lệ, chọn Runas user khác | Từ chối | Giới hạn danh tính đích |
| User ngoài nhóm, cùng command | Từ chối | Membership đúng |
| User trên host ngoài phạm vi | Từ chối theo policy này | Không có cấp quyền ngoài tài sản |
| User sau thu hồi quyền và xác minh danh tính mới | Từ chối | Cơ chế thu hồi có tác dụng |

Nếu tài khoản thử nghiệm có quyền quản trị khác, một trường hợp “phải từ chối” có thể vẫn được phép bởi grant đó. Đây là phát hiện về quyền hiệu lực, không phải lý do bỏ qua kiểm tra.

### 7.1. Kiểm tra được phép mà chưa chạy lệnh

Trong phiên của người cần kiểm tra, dùng chế độ liệt kê với command:

~~~bash
sudo -l -u root -- /usr/bin/systemctl restart acme-report.service
sudo -l -u root -- /usr/bin/systemctl restart other.service
sudo -l -u root -- /usr/bin/systemctl stop acme-report.service
sudo -l -u root -- /usr/bin/systemctl
sudo -l -u root -- /bin/sh
~~~

Đây là các yêu cầu kiểm tra quyền, không phải yêu cầu thực thi restart hoặc shell. Đọc kết quả và mã thoát; không mặc định mọi thông báo lỗi đều chứng minh policy deny. Lỗi xác thực, lỗi danh tính hoặc không liên hệ được policy source cần được phân loại riêng.

Các đường dẫn và command trong negative test phải phù hợp với môi trường kiểm thử. Nếu executable không tồn tại, kết quả thất bại không đủ chứng minh quy tắc phân quyền đã chặn đúng.

### 7.2. Kiểm tra hành vi trong môi trường được phép

Chỉ thực thi thao tác thay đổi trạng thái trên lab hoặc trong cửa sổ vận hành đã được phê duyệt. Ví dụ sau thực sự restart service:

~~~bash
sudo -u root -- /usr/bin/systemctl restart acme-report.service
~~~

Trước khi chạy cần biết tác động và cách xác nhận phục hồi. Kiểm tra dịch vụ hoạt động trở lại bằng tín hiệu nghiệp vụ phù hợp, không chỉ mã thoát của systemctl.

Không chạy shell root để “xem có được không” trên production khi có thể kiểm tra quyền bằng chế độ liệt kê. Không biến negative test thành hành động thay đổi cấu hình hoặc truy cập dữ liệu thật ngoài phạm vi.

Nếu cần kiểm tra lại xác thực, `sudo -k` có thể vô hiệu timestamp của người dùng trước lượt thử tiếp theo. Thao tác này liên quan cache xác thực, không phải thu hồi grant; sau `sudo -k`, user vẫn được quyền nếu policy còn cho phép.

## 8. Xác thực, JIT và ghi bằng chứng là các lớp riêng

Một review tốt trả lời được ba câu hỏi tách biệt:

1. **Người gọi có được xác thực phù hợp không?**
2. **Người đó có được phép thực hiện đúng tác vụ vào thời điểm này không?**
3. **Sau đó có bằng chứng đủ để giải thích ai đã làm gì không?**

MFA ở cổng SSH hoặc bastion không tự chứng minh từng lệnh sudo cần MFA. `PASSWD` không tự chứng minh người dùng đang dùng một yếu tố xác thực mới. Ghi rõ mô hình thực tế, các lớp đã triển khai và phần nào còn thiếu.

JIT cần có điểm bắt đầu, thời hạn, owner phê duyệt và cơ chế thu hồi được kiểm tra. Sau khi bỏ membership, cần xác minh phiên mới, độ trễ cache của hệ thống danh tính và kết quả policy trên máy đích.

Thu hồi quyền khởi chạy lệnh mới không tự dừng tiến trình đặc quyền đã chạy hoặc xóa secret đã bị đọc. Với tình huống nghi ngờ lạm dụng, phải kết hợp xử lý tiến trình, phiên đang mở và credential liên quan theo quy trình ứng phó sự cố.

### 8.1. Nội dung log cần xác minh

Tùy nền tảng, sudo có thể ghi qua syslog, journal, file riêng hoặc đích log tập trung. Không giả định mọi Linux đều lưu ở cùng một file.

Bằng chứng nên giúp liên hệ:

- User gốc, user/group đích, host và thời điểm.
- TTY hoặc ngữ cảnh phiên nếu có.
- Command và arguments được yêu cầu.
- Sự kiện được phép, bị từ chối và lỗi xác thực.
- Ticket, cửa sổ truy cập và thay đổi policy liên quan.
- Kết quả tác vụ từ service hoặc hệ thống giám sát tương ứng.

Log sudo về việc command được gọi không tự chứng minh tác vụ nghiệp vụ thành công. Dùng thêm mã thoát khi hệ thống thu thập, log service và kiểm tra chức năng để xác nhận kết quả.

I/O logging hoặc session recording có thể bổ sung bằng chứng khi được hỗ trợ và cấu hình. Nhưng dữ liệu nhập/xuất có thể chứa secret hoặc thông tin nhạy cảm. Xác định người được xem, thời hạn lưu và biện pháp bảo vệ trước khi bật diện rộng.

Không xem log trên chính host là đủ nếu người được cấp quyền có thể sửa hoặc xóa chúng. Đánh giá chuyển log ra hệ thống tập trung, đồng bộ thời gian và quyền truy cập bằng chứng. Không cần bật tất cả tính năng logging để kết luận review có giá trị; cần chứng minh cấu hình đã chọn đáp ứng yêu cầu truy vết.

## 9. Các lỗi thường gặp và cách khắc phục

| Nhận định hoặc lỗi | Vì sao chưa đủ | Cách xử lý |
|---|---|---|
| “File không có NOPASSWD nên an toàn” | Vẫn có thể chạy mọi lệnh hoặc dùng cache xác thực | Xem cả command, Runas, Defaults và quyền chồng lấn |
| “Chỉ cho systemctl nên hẹp” | Không ghi arguments thường cho phép mọi arguments | Chốt thao tác và service cụ thể |
| “Đã thêm rule hẹp” | Grant rộng từ nhóm khác vẫn còn | Kiểm tra toàn bộ quyền hiệu lực và sửa tại nguồn |
| “Chỉ được restart nên không chiếm root” | User có thể sửa mã mà service root sẽ chạy | Rà soát dependency và quyền ghi |
| “Visudo PASS nên policy đúng” | Visudo chủ yếu kiểm tra cú pháp | Kiểm thử quyền và hành vi theo ma trận |
| “Đã bỏ khỏi nhóm nên thu hồi xong” | Cache, phiên hoặc tiến trình đang chạy có thể còn ảnh hưởng | Kiểm tra hội tụ policy và xử lý trạng thái tồn dư |
| “Có NOEXEC nên cấp editor được” | NOEXEC không ngăn mọi hành vi đặc quyền | Giới hạn công cụ, đối tượng và quy trình |
| “Có log command nên biết toàn bộ việc xảy ra” | Command có thể sinh thêm hành vi; log có thể bị sửa | Đối chiếu log đích, session và dữ liệu tập trung |
| “Policy ở file .conf chắc đã được nạp” | Includedir có quy tắc bỏ qua tên file | Kiểm tra cơ chế nạp và quyền thực tế |

Lỗi vận hành phổ biến khác là sửa trực tiếp file sinh bởi công cụ quản lý cấu hình. Bản sửa có thể bị ghi đè ở lần đồng bộ tiếp theo. Khắc phục ở nguồn quản lý và chứng minh máy đích đã nhận đúng phiên bản.

Nếu policy đến từ hệ thống tập trung nhưng host còn một grant local rộng, chỉnh riêng policy tập trung sẽ không thu hẹp hết quyền. Báo cáo cả hai nguồn và kiểm chứng lại sau khi xử lý.

## 10. Hồ sơ review mẫu

Một finding nên liên hệ được bằng chứng kỹ thuật với nhu cầu và hành động khắc phục:

~~~text
Finding: SUDO-REPORT-001
Phạm vi: report-01, report-02
Đối tượng: nhóm report-oncall
Nhu cầu: restart acme-report.service trong ca trực đã phê duyệt

Hiện trạng:
- Có grant cho phép mọi arguments của /usr/bin/systemctl với root.
- Cần xác minh các grant nhận từ nhóm khác.
- Cần kiểm tra unit, executable và EnvironmentFile trước khi chấp nhận.

Tác động:
- Thành viên có thể thực hiện thao tác quản lý service ngoài nhu cầu.
- Nếu sửa được dependency của một service root, có thể thực thi mã với root.

Đề xuất:
- Giới hạn đúng restart acme-report.service trên hai host.
- Loại bỏ grant rộng tại nguồn.
- Bảo vệ dependency và xác minh bằng ma trận kiểm thử.
- Gắn membership với lịch trực và thời hạn được phê duyệt.

Bằng chứng đóng:
- Baseline và policy mới theo định danh phiên bản.
- Kết quả visudo và sudo -ll của user mục tiêu.
- Kết quả positive/negative test, không chỉ ảnh chụp file.
- Sự kiện log tương ứng.
- Owner chấp nhận, thời điểm triển khai và kiểm tra thu hồi.
~~~

Không đóng finding chỉ vì pull request đã merge hoặc file mới đã xuất hiện trên host. Điều kiện đóng phải chứng minh quyền hiệu lực đã thay đổi đúng và tác vụ cần thiết vẫn hoạt động.

Một bảng review theo từng grant có thể gồm:

| Trường | Nội dung cần giữ |
|---|---|
| Policy source | File/include hoặc đối tượng policy tập trung |
| Principal | User/group, nguồn membership và owner |
| Host scope | Tài sản thực tế và điều kiện khớp |
| Runas | User/group đích |
| Command scope | Executable, arguments và dependency |
| Authentication | Tag, cache và cơ chế xác thực hiệu lực |
| Lifecycle | Phê duyệt, thời hạn, kích hoạt và thu hồi |
| Evidence | Kết quả kiểm tra, log, phiên bản và thời điểm |
| Disposition | Giữ, thu hẹp, thu hồi hoặc chấp nhận có lý do |

## 11. Bài tập thực hành

### Tình huống

Một nhóm trực ca chỉ cần restart dịch vụ báo cáo trên report-01. Chính sách hiện tại:

~~~sudoers
%report-oncall ALL = (ALL:ALL) NOPASSWD: /usr/bin/systemctl
alice ALL = (root) /bin/bash
~~~

Alice là thành viên report-oncall. Service báo cáo chạy với root, còn script được service gọi lại nằm trong thư mục mà nhóm report-oncall được ghi.

### Yêu cầu phân tích

1. Liệt kê các quyền vượt nhu cầu, gồm host, Runas, arguments và xác thực.
2. Giải thích tại sao thêm một dòng exact restart không đủ thu hẹp quyền của Alice.
3. Xác định điều kiện về script và thư mục cần sửa trước khi duyệt policy mới.
4. Đề xuất policy tối thiểu cho đúng tác vụ, xác định owner và thời hạn.
5. Lập ít nhất một positive test và các negative test cho host, service, động từ, Runas và shell.
6. Mô tả bằng chứng cần có để xác nhận thu hồi quyền sau ca trực.

### Gợi ý đối chiếu

Dòng đầu rộng ở cả host, Runas, group đích và arguments. NOPASSWD bỏ yêu cầu xác thực của command đó theo tag hiệu lực. Dòng shell riêng của Alice vẫn tạo một đường root độc lập.

Cần xử lý grant shell và grant systemctl rộng tại nguồn, rồi mới đánh giá chính sách hẹp. Đồng thời phải bảo vệ script, thư mục cha và các đầu vào thực thi của service. Nếu đường dependency vẫn ghi được, một quyền restart đúng service vẫn có thể mở đường chạy mã với root.

Một phương án chỉ được chấp nhận sau khi policy tổng hợp cho kết quả đúng, service hoạt động trong lượt thử được phép, log truy vết được và việc thu hồi thực sự ngăn được yêu cầu đặc quyền mới.

## 12. Câu hỏi tự kiểm tra

- Trong một rule, ba chữ ALL ở vị trí user/host, Runas và command có ý nghĩa giống nhau không?
- Không ghi arguments sau executable khác gì so với khai báo arguments rỗng `""`?
- Vì sao PASSWD không tự chứng minh người dùng phải nhập lại password mỗi lần?
- Reviewer cần kiểm tra gì khi sudoers chỉ cấp quyền restart một service?
- Vì sao một rule cụ thể không tự thu hồi grant rộng từ nhóm khác?
- Visudo PASS, sudo -l PASS và tác vụ nghiệp vụ PASS xác nhận những điều khác nhau nào?
- Làm sao chứng minh thu hồi quyền có hiệu lực khi danh tính và policy có cache?
- Bằng chứng nào cho thấy log phản ánh người dùng cá nhân thay vì một account chia sẻ?

Kết quả mong đợi của sudoers review là một tập quyền giải thích được: đúng người, đúng tài sản, đúng danh tính đích, đúng tác vụ và đúng thời điểm, với các đường gián tiếp đã được kiểm tra và bằng chứng đủ để xác nhận cả việc sử dụng lẫn thu hồi.

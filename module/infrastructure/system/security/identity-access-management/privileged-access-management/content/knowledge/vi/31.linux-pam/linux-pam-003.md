# Root login restriction — Hạn chế đăng nhập trực tiếp bằng root

## 1. Mục tiêu và phạm vi

Hạn chế đăng nhập bằng root là kiểm soát đường đi vào quyền quản trị cao nhất của máy Linux. Trong quản trị truy cập đặc quyền (Privileged Access Management — PAM), mục tiêu là xác định được người hoặc hệ thống yêu cầu quyền, chỉ cấp quyền cần thiết trong thời gian phù hợp, và giữ được bằng chứng sử dụng quyền đó.

Sau bài học, bạn có thể:

- Phân biệt chặn root qua SSH, khóa mật khẩu root, hạn chế đăng nhập console và kiểm soát chuyển sang root.
- Thiết kế luồng quản trị bằng tài khoản định danh, quyền nâng có kiểm soát và cơ chế khẩn cấp.
- Áp dụng chính sách SSH theo từng giai đoạn, kiểm tra cấu hình hiệu lực và thử kết nối mới.
- Nhận diện các phụ thuộc như backup, automation, bastion và cloud console trước khi thay đổi.
- Thu thập bằng chứng cho kiểm toán và xử lý sai lệch cấu hình.

Các ví dụ hướng đến máy Linux chạy OpenSSH và, ở phần quản lý dịch vụ, systemd. Tên dịch vụ, đường dẫn chương trình, tích hợp định danh và PAM stack có thể khác giữa các bản phân phối. Những lệnh thay đổi cấu hình trong bài là thao tác thực hành cho máy lab hoặc kế hoạch thay đổi đã được tổ chức cho phép; không phải một script chạy hàng loạt.

Ở đây cần phân biệt hai nghĩa của chữ PAM:

- **Privileged Access Management** là chương trình quản trị quyền đặc biệt của toàn bộ module.
- **Linux-PAM** là cơ chế Pluggable Authentication Modules mà các chương trình như login, su hoặc sshd có thể tích hợp.

Linux-PAM có thể thực thi một phần chính sách, nhưng không tự cung cấp đầy đủ phê duyệt JIT, quản lý vault, ghi phiên và kiểm toán cho tổ chức.

## 2. Root là một danh tính và cũng là một mức quyền

Tài khoản root thường có UID 0 trong không gian định danh của hệ điều hành. Khi đánh giá rủi ro, không chỉ tìm chuỗi tên người dùng root: một tài khoản có tên khác nhưng mang UID 0 cũng cần được giải trình. Trên hệ thống có container hoặc user namespace, UID bên trong một môi trường không nhất thiết tương đương với quyền root trên host; cần ghi rõ phạm vi kiểm tra.

Kiểm soát root login tập trung vào việc một chủ thể bắt đầu phiên hoặc yêu cầu thực thi bằng danh tính root. Nó không có nghĩa là mọi tiến trình UID 0 đều phải biến mất. Một số thành phần hệ thống vẫn cần quyền cao để khởi động hoặc thực hiện chức năng được thiết kế.

Ví dụ, có ba tình huống khác nhau:

1. Minh dùng khóa SSH chung để đăng nhập thẳng thành root.
2. Minh đăng nhập bằng tài khoản cá nhân, sau đó được phép chạy một tác vụ quản trị qua sudo.
3. Một dịch vụ hệ thống chạy dưới UID 0 khi máy khởi động.

Chặn tình huống thứ nhất không tự động loại bỏ tình huống thứ hai hoặc thứ ba. Việc đánh giá quyền của dịch vụ và phạm vi sudo vẫn phải thực hiện riêng.

### Vì sao hạn chế đăng nhập trực tiếp?

Khi nhiều người dùng cùng root và cùng một credential, máy đích khó trả lời người nào thực hiện thay đổi. Một bản ghi “root đã đăng nhập” chỉ xác nhận tài khoản đích. Muốn quy trách nhiệm, cần liên kết danh tính nguồn, phiên truy cập, phê duyệt và hành động.

Hạn chế root login tạo một điểm kiểm soát trước khi có quyền cao. Tài khoản cá nhân có thể chịu chính sách vòng đời, xác thực mạnh và thu hồi riêng; bước nâng quyền có thể gắn với tác vụ, máy chủ, thời hạn và lý do. Lợi ích này chỉ đạt được khi không thay root chung bằng một tài khoản admin chung có quyền không giới hạn.

## 3. Lập bản đồ mọi đường vào quyền root

Một cấu hình SSH chỉ kiểm soát các kết nối đi qua đúng SSH daemon đó. Hệ thống còn có thể có serial console, console của hypervisor, cơ chế cứu hộ, công cụ quản lý tập trung hoặc một SSH daemon khác.

| Đường truy cập | Điểm kiểm soát cần xem | Điều cần chứng minh |
|---|---|---|
| SSH trực tiếp bằng root | Cấu hình hiệu lực của từng sshd | Kết nối mới tới đúng listener bị từ chối theo chính sách |
| SSH bằng người dùng rồi sudo | Danh tính nguồn và chính sách sudo | Chỉ người được cấp quyền mới thực hiện tác vụ cho phép |
| Chuyển tài khoản bằng su | PAM stack của su và chính sách tổ chức | Việc chuyển tài khoản không trở thành đường dùng mật khẩu root chung |
| Console vật lý hoặc serial | Chương trình login, PAM stack, quyền truy cập console | Đường này có xác thực và chủ sở hữu rõ ràng |
| Cloud hoặc hypervisor console | IAM ở lớp quản lý, quyền mở console và quy trình cứu hộ | Có thể quy trách nhiệm cả thao tác ngoài SSH |
| Backup, deploy, orchestration | Danh tính máy, credential, quyền lệnh | Có phương án thay thế trước khi chặn root |
| Rescue hoặc boot từ môi trường khác | Bảo vệ nền tảng, ổ đĩa và quy trình khẩn cấp | Rủi ro ngoài hệ điều hành đang chạy được kiểm soát |

Một luồng quản trị mong muốn có thể được mô tả như sau:

~~~mermaid
flowchart LR
    A[Người dùng định danh] --> B[Xác thực qua điểm truy cập quản trị]
    B --> C[Tài khoản cá nhân trên Linux]
    C --> D{Có quyền cho tác vụ và thời hạn này?}
    D -->|Có| E[Thực thi quyền cần thiết]
    D -->|Không| F[Từ chối và ghi nhận]
    E --> G[Đối soát phê duyệt và bằng chứng phiên]
~~~

Bastion hoặc cổng PAM không tự bảo đảm rằng host đích chỉ nhận truy cập qua nó. Nếu còn một đường mạng trực tiếp và credential khác, người dùng vẫn có thể bỏ qua điểm kiểm soát. Cần kiểm tra cả đường mạng lẫn cơ chế xác thực tại host.

## 4. Xây dựng chính sách trước khi chỉnh cấu hình

Một chính sách thực dụng nên trả lời được các câu hỏi sau:

- Người vận hành thông thường có được đăng nhập trực tiếp bằng root qua SSH không?
- Sau khi đăng nhập bằng tài khoản cá nhân, họ được làm gì và trong bao lâu?
- Automation nào đang yêu cầu root và ai chịu trách nhiệm chuyển đổi?
- Khi hệ thống định danh hoặc cổng PAM gặp sự cố, ai có thể dùng đường khẩn cấp?
- Bằng chứng nào được lưu, lưu ở đâu và ai được xem?
- Ngoại lệ có ngày hết hạn và kế hoạch đóng hay chưa?

Ví dụ chính sách cho một nhóm máy ứng dụng:

> Phiên quản trị thường lệ bắt đầu bằng tài khoản cá nhân. SSH trực tiếp bằng root bị chặn. Quyền đặc biệt được cấp theo tác vụ và thời hạn. Truy cập cứu hộ đi qua console được bảo vệ bằng IAM riêng, có phê duyệt, ghi nhận và rà soát sau sử dụng.

Đây là thiết kế mẫu, không phải yêu cầu rằng mọi hệ thống đều dùng cùng một công cụ. Với máy độc lập, quy trình có thể đơn giản hơn; với hạ tầng nhạy cảm, cần liên kết phê duyệt, JIT, vault và giám sát phiên.

Không dùng câu “root đã bị khóa” làm mô tả chính sách. Hãy ghi rõ “SSH trực tiếp bằng root bị từ chối trên listener nào”, “mật khẩu root có trạng thái gì” và “đường cứu hộ nào còn được phép”.

## 5. Kiểm soát SSH: PermitRootLogin

Cấu hình cốt lõi cho chính sách chặn root qua OpenSSH là:

~~~text
PermitRootLogin no
~~~

Ý nghĩa cần nhớ:

| Giá trị | Hành vi liên quan đến root |
|---|---|
| yes | Cho phép root đăng nhập nếu vượt qua các kiểm tra khác |
| prohibit-password | Chặn password và keyboard-interactive cho root; vẫn có thể cho phép khóa công khai |
| forced-commands-only | Chỉ cho phép xác thực khóa công khai với lệnh cưỡng bức được quy định |
| no | Không cho root đăng nhập qua SSH |

Các giá trị và phạm vi này được mô tả trong [tài liệu PermitRootLogin của OpenSSH](https://man.openbsd.org/sshd_config.5#PermitRootLogin).

Vì vậy, prohibit-password không đáp ứng một yêu cầu “cấm SSH trực tiếp bằng root”. Một khóa riêng cũ, một cơ chế phân phối khóa hoặc chứng thư SSH còn được tin cậy có thể tiếp tục là đường xác thực nếu chính sách máy cho phép.

Không suy rằng đổi PasswordAuthentication thành no là đủ cho root restriction. Đây là một lựa chọn phương thức xác thực, có thể ảnh hưởng tất cả người dùng trong phạm vi cấu hình. Chính sách đăng nhập root nên được thể hiện trực tiếp bằng PermitRootLogin và được kiểm tra theo ngữ cảnh.

### Cấu hình trên đĩa và cấu hình hiệu lực

Trước khi sửa, cần xác định daemon đang dùng file nào, có Include nào và có khối Match nào áp dụng. Không chỉ tìm thấy một dòng rồi kết luận.

OpenSSH thường dùng giá trị gặp đầu tiên cho một tùy chọn; các khối Match áp dụng theo ngữ cảnh có thể thay đổi kết quả so với phần toàn cục. Vì vậy, không dựa vào quy tắc “thêm dòng cuối để ghi đè”. Xem [quy tắc cấu hình](https://man.openbsd.org/sshd_config.5#DESCRIPTION) và [Match](https://man.openbsd.org/sshd_config.5#Match).

Một số lỗi triển khai thường gặp:

- Sửa file mặc định trong khi dịch vụ được chạy với một file cấu hình khác.
- Thêm một file drop-in nhưng file đó không được Include.
- Đặt cấu hình vào vị trí đang thuộc một khối Match ngoài dự kiến.
- Kiểm tra kết quả toàn cục nhưng bỏ sót ngoại lệ theo địa chỉ nguồn.
- Chỉ kiểm tra cổng 22 trong khi còn listener quản trị khác.
- Đổi file thủ công rồi bị công cụ cấu hình hoặc quá trình tạo máy ghi lại.

Cần sửa ở nguồn quản lý cấu hình của hệ thống và kiểm tra trạng thái thực tế sau khi triển khai.

## 6. Kiểm tra trước thay đổi

### 6.1. Xác minh đường quản trị thay thế

Tạo hoặc cấp tài khoản định danh qua cơ chế quản lý được tổ chức sử dụng. Sau đó thử từ một kết nối mới, không chỉ từ phiên root đang mở:

~~~bash
ssh alice@linux-lab.example
id
sudo -l
~~~

Lệnh sudo -l giúp xem quyền được cấp cho tài khoản. Nếu chính sách lab cho phép thực thi id với quyền root, có thể kiểm tra:

~~~bash
sudo /usr/bin/id -u
~~~

Kết quả 0 xác nhận lệnh đó chạy với effective UID 0. Nó không chứng minh tài khoản chỉ có quyền tối thiểu hoặc mọi thao tác nâng quyền đều được ghi đầy đủ. Đừng thêm quyền ALL chỉ để làm cho bài kiểm thử thành công; hãy chọn một tác vụ kiểm tra vốn được chính sách cho phép.

Với quyền JIT, cần kiểm tra cả trường hợp trước khi được cấp, trong thời gian được cấp và sau khi thu hồi. Với MFA hoặc xác thực qua bastion, thử đúng luồng mà người vận hành thực sự sử dụng.

### 6.2. Kiểm kê danh tính và trạng thái mật khẩu

Các lệnh chỉ đọc sau hữu ích trên một máy lab Linux:

~~~bash
getent passwd root

getent passwd | awk -F: '$3 == 0 { print $1 ":" $3 ":" $6 ":" $7 }'

sudo passwd -S root
~~~

Câu lệnh awk chỉ in tên, UID, home và shell của những bản ghi UID 0 mà getent trả về. Với hệ thống định danh không hỗ trợ liệt kê đầy đủ, kết quả này chỉ là một phần kiểm kê; cần đối soát nguồn quản lý danh tính.

Không xuất toàn bộ /etc/shadow vào ticket hoặc log thu thập bằng chứng. Mục tiêu là biết trạng thái kiểm soát, không phát tán hash mật khẩu.

### 6.3. Kiểm kê phụ thuộc vận hành

Lập danh sách các job có dạng root@host, công cụ quản lý cấu hình, tác vụ sao lưu và kênh hỗ trợ. Mỗi phụ thuộc cần có chủ sở hữu, phương án thay thế và lần chạy kiểm thử.

Một job backup đang thành công không phải lý do đủ để giữ root SSH vô thời hạn. Ngược lại, chặn ngay mà chưa biết nó phục hồi dữ liệu thế nào có thể tạo sự cố. Cần chuyển sang danh tính máy và phạm vi quyền phù hợp, kiểm tra cả backup lẫn restore rồi mới đóng đường cũ.

### 6.4. Chuẩn bị phương án khôi phục

Giữ một phiên quản trị hợp lệ trong lúc thay đổi, đồng thời xác minh đường console hoặc cứu hộ độc lập. Một tab terminal đang mở không thay thế được phương án khôi phục: nó có thể mất khi mạng đứt, phiên hết hạn hoặc quyền sudo hết hiệu lực.

Trước khi chặn SSH root, cần biết ai có quyền truy cập đường khẩn cấp, có lấy được credential cần thiết không và bằng chứng nào sẽ được ghi khi sử dụng.

## 7. Quy trình thay đổi SSH có kiểm soát

### Bước 1: Chọn máy thử và ghi nhận trạng thái ban đầu

Bắt đầu bằng máy lab hoặc một máy canary đại diện. Ghi lại định danh máy, listener, file cấu hình thực tế, nguồn cấu hình, người thực hiện và mã thay đổi.

Với hệ thống systemd, có thể xem thuộc tính dịch vụ để hỗ trợ xác định cách khởi chạy:

~~~bash
systemctl show -p FragmentPath -p ExecStart sshd.service
~~~

Nếu bản phân phối dùng tên ssh.service, dùng tên đó thay thế. Tên unit hoặc đường dẫn minh họa không phải bằng chứng rằng mọi Linux đều giống nhau.

Sao lưu các file cấu hình thực sự sẽ sửa theo quy trình của tổ chức, bao gồm drop-in liên quan. Giới hạn quyền truy cập bản sao. Không gom private key của máy chủ vào bộ bằng chứng thay đổi nếu không có nhu cầu quản lý khóa tương ứng.

### Bước 2: Chỉnh đúng nguồn cấu hình

Ở phần toàn cục phù hợp của cấu hình được daemon sử dụng, đặt:

~~~text
PermitRootLogin no
~~~

Nếu hệ thống được quản lý bằng configuration management hoặc image template, triển khai thay đổi ở nguồn đó. Việc sửa tay chỉ có thể là giải pháp tạm thời có theo dõi; nếu không sửa nguồn, các lần tái tạo hoặc đồng bộ tiếp theo có thể mở lại truy cập root.

Không ghép thêm thay đổi MFA, mật khẩu, cổng SSH và PAM stack vào cùng một thử nghiệm chỉ để “hardening toàn bộ”. Thay đổi có phạm vi rõ giúp xác định chính xác nguyên nhân khi kiểm thử thất bại.

### Bước 3: Kiểm tra cú pháp

Ví dụ với đường dẫn thường gặp:

~~~bash
sudo /usr/sbin/sshd -t -f /etc/ssh/sshd_config
~~~

Không có thông báo và mã thoát 0 là kết quả thành công thông thường. Nếu có lỗi, dừng việc áp dụng và sửa cấu hình. Đừng reload rồi mới tìm lỗi.

### Bước 4: Kiểm tra cấu hình hiệu lực theo kết nối

~~~bash
sudo /usr/sbin/sshd -T -f /etc/ssh/sshd_config \
  -C user=root,host=bastion.example,addr=192.0.2.10,laddr=192.0.2.20,lport=22
~~~

Ở đây:

- addr là địa chỉ nguồn mà máy đích nhìn thấy.
- host là tên nguồn đã phân giải dùng cho ngữ cảnh kiểm tra, không phải tên máy đích.
- laddr và lport là địa chỉ và cổng cục bộ của listener.
- Các địa chỉ 192.0.2.x và tên example chỉ dùng minh họa; cần thay bằng ngữ cảnh triển khai.

Tìm giá trị permitrootlogin trong kết quả; kỳ vọng là no cho mọi ngữ cảnh cần chặn. Lặp lại cho những nguồn, listener hoặc điều kiện Match liên quan. Khi kết nối qua bastion, máy đích có thể nhìn thấy IP của bastion thay vì IP laptop.

Tùy chọn -t kiểm tra cấu hình và khóa máy chủ; -T xuất cấu hình hiệu lực, còn -C cung cấp ngữ cảnh để xét Match. Đây là kiểm tra bằng cấu hình trên đĩa, chưa chứng minh daemon đang chạy đã nạp thay đổi. Xem [hướng dẫn dòng lệnh sshd](https://github.com/openssh/openssh-portable/blob/master/sshd.8).

### Bước 5: Nạp lại dịch vụ phù hợp

Sau khi các kiểm tra trên đạt, dùng cơ chế reload được unit của hệ thống hỗ trợ. Ví dụ, chọn đúng một trong hai tên dịch vụ thường gặp:

~~~bash
sudo systemctl reload sshd.service
~~~

hoặc:

~~~bash
sudo systemctl reload ssh.service
~~~

Kiểm tra kết quả và trạng thái dịch vụ. Nếu unit không hỗ trợ reload, thực hiện phương án đã kiểm thử cho bản phân phối đó trong kế hoạch thay đổi, thay vì tùy tiện thay reload bằng restart trên máy đang truy cập từ xa.

Giữ phiên cũ cho tới khi kết nối quản trị mới đã thành công. Phiên cũ còn hoạt động không phải dấu hiệu thất bại của chính sách: hạn chế đăng nhập mới không tự thu hồi mọi phiên đã tồn tại.

## 8. Kiểm thử hành vi bằng kết nối mới

Cần cả kiểm thử dương tính và âm tính. Chỉ thấy root bị từ chối chưa đủ nếu cùng lúc mọi người dùng hợp lệ cũng bị chặn.

### 8.1. Kiểm thử tài khoản cá nhân

Từ máy kiểm thử, tạo kết nối mới, tránh dùng lại kết nối SSH multiplexing đã có:

~~~bash
ssh -o ControlMaster=no -o ControlPath=none alice@linux-lab.example
~~~

Xác minh danh tính, tác vụ quản trị được phép và log. Nếu hệ thống có bước phê duyệt, đi qua bước đó như vận hành thật. Không dùng một tài khoản thử có quyền đặc biệt hơn mọi tài khoản sản xuất rồi coi đó là kiểm tra đại diện.

### 8.2. Kiểm thử root qua SSH

Trên lab có khóa root thử nghiệm đã được biết là hợp lệ trước thay đổi, có thể dùng:

~~~bash
ssh -o ControlMaster=no -o ControlPath=none \
  -o BatchMode=yes -o ConnectTimeout=5 \
  -o IdentitiesOnly=yes -i ~/.ssh/pam_lab_root \
  root@linux-lab.example true
~~~

Kỳ vọng sau thay đổi là không thực thi được true bằng root. Chỉ dùng khóa lab được cấp cho bài kiểm thử; không tạo đường root mới trên production để tiện kiểm tra.

Một lần thất bại với khóa sai không chứng minh root restriction hoạt động. Phải kết hợp cấu hình hiệu lực, kết quả nạp lại, kết nối đúng listener và log máy đích. Cũng cần phân biệt lỗi mạng, host key, cơ chế xác thực và lỗi chính sách tài khoản. Thông báo Permission denied ở client có thể không đủ để xác định nguyên nhân.

Khi cần kiểm tra phương thức password hoặc keyboard-interactive, thực hiện số lần thử được kiểm soát theo kế hoạch, tránh gây khóa tài khoản hoặc kích hoạt phản ứng tự động ngoài dự kiến. Không ghi mật khẩu vào dòng lệnh, ticket hay bản chụp màn hình.

### 8.3. Ma trận chấp nhận

| Tình huống | Kết quả mong đợi |
|---|---|
| Tài khoản cá nhân hợp lệ vào đúng kênh quản trị | Đăng nhập thành công |
| Người dùng được cấp đúng quyền thực hiện tác vụ | Thành công và có bằng chứng liên kết |
| Người dùng không có quyền thực hiện tác vụ đó | Bị từ chối |
| Root mở kết nối SSH mới tới listener trong phạm vi | Bị từ chối |
| Job đã chuyển đổi khỏi root trực tiếp | Chạy đúng chức năng và đúng danh tính mới |
| Đường khẩn cấp được kiểm tra theo quy trình | Dùng được khi được cấp phép và có log |
| Cấu hình được đồng bộ hoặc máy được tái tạo | Chính sách tiếp tục có hiệu lực |

Không đóng thay đổi chỉ bằng một ảnh chụp dòng PermitRootLogin no. Ma trận trên kiểm tra cả tác dụng bảo mật và khả năng vận hành.

## 9. Khóa mật khẩu root có phạm vi khác

Lệnh sau khóa mật khẩu của root:

~~~bash
sudo passwd -l root
~~~

Theo [tài liệu passwd của shadow-utils](https://www.man7.org/linux/man-pages/man1/passwd.1.html), khóa mật khẩu không đồng nghĩa vô hiệu hóa toàn bộ tài khoản; một token khác như khóa SSH vẫn có thể là đường đăng nhập. Hành vi thực tế còn phụ thuộc dịch vụ và chính sách account của hệ thống.

Vì vậy, trạng thái mật khẩu L không thay thế PermitRootLogin no và kiểm thử kết nối. Nó cũng không phải một cơ chế tổng quát để ngăn mọi lệnh được sudo cấp chạy dưới root.

Trước khi khóa mật khẩu root, cần kiểm tra tác động tới console, quy trình cứu hộ và công cụ vận hành đang dùng mật khẩu đó. Một máy đã có root password bị khóa theo thiết kế có thể không cần thao tác thêm.

Tránh các cách làm sau:

- Dùng passwd -d để “vô hiệu hóa root”: thao tác này xóa mật khẩu, khác với khóa mật khẩu.
- Cho root hết hạn tài khoản trên toàn hệ thống mà chưa hiểu ảnh hưởng đến kiểm tra account của từng dịch vụ.
- Đổi shell root sang nologin rồi coi như đã giải quyết mọi đường có UID 0.
- Xóa hoặc đổi UID của root nhằm đạt một tiêu chí kiểm tra.

Root là thành phần nền tảng của nhiều quy trình hệ thống. Chặn một loại đăng nhập nên được thực thi tại đúng loại truy cập, có kiểm tra ảnh hưởng và phương án phục hồi.

## 10. Console, su và Linux-PAM

### Console là một bề mặt riêng

Chính sách SSH không áp dụng trực tiếp cho đăng nhập qua console. Một máy có root SSH bị chặn vẫn có thể cho phép root tại console nếu chương trình login và PAM stack tương ứng cho phép.

Linux-PAM có module pam_securetty dùng để giới hạn root theo thiết bị terminal. Cơ chế chỉ có ý nghĩa nếu ứng dụng gọi module và truyền thông tin terminal phù hợp; một file /etc/securetty không tự tạo chính sách toàn máy. Xem [tài liệu pam_securetty](https://www.man7.org/linux/man-pages/man8/pam_securetty.8.html).

Không làm rỗng /etc/securetty rồi tuyên bố mọi root login đã bị chặn. Cần đánh giá PAM stack thực tế, khả năng áp dụng của module và những console mà hệ thống cho phép. Cloud console có thể bổ sung cơ chế tiếp cận khác ở lớp nền tảng; phải kiểm tra end-to-end.

### su và sudo không chịu cùng một chính sách với SSH

Sau khi vào máy bằng tài khoản cá nhân, người dùng có thể yêu cầu chuyển danh tính hoặc nâng quyền. PermitRootLogin no không phải một quy tắc cấm su hoặc sudo.

Trong một thiết kế có trách nhiệm giải trình:

- Ưu tiên quyền theo tác vụ được cấp cho danh tính cá nhân.
- Hạn chế việc phân phối mật khẩu root chung cho người vận hành.
- Quản lý các chính sách su và sudo ở nguồn cấu hình được kiểm soát.
- Rà soát các quyền có thể mở shell hoặc sửa cơ chế cấp quyền.

Nếu mọi người có sudo không giới hạn và thường xuyên mở root shell dài hạn, hệ thống vẫn cần kiểm soát vòng đời và giám sát phù hợp. Chặn root SSH cải thiện điểm vào, nhưng không tự đạt least privilege.

Không chỉnh một PAM stack chung để từ chối mọi yêu cầu có đích root mà chưa phân tích từng ứng dụng sử dụng stack đó. Một thay đổi tưởng chỉ áp dụng cho login có thể làm hỏng nâng quyền hoặc quy trình phục hồi. Không tắt UsePAM chỉ để tránh một lỗi đăng nhập: làm vậy có thể thay đổi các kiểm tra account, session hoặc MFA đang được thiết kế.

## 11. Automation và ngoại lệ có giới hạn

Một trường hợp phổ biến là công cụ backup đăng nhập root bằng khóa SSH. Trước khi chặn, nhóm vận hành phải xác định chức năng thật sự cần quyền gì: đọc file hạn chế, tạo snapshot, hay phục hồi vào thư mục hệ thống.

Phương án chuyển đổi có thể là tài khoản dịch vụ riêng, credential được quản lý trong vault hoặc chứng thư ngắn hạn, kết hợp quyền cho tác vụ cụ thể. Quyền phải đủ cho cả kiểm thử khôi phục, không chỉ đủ để job hằng ngày báo xanh.

Nếu một hệ thống cũ chưa thể chuyển đổi ngay, ngoại lệ cần có:

| Trường quản lý | Ví dụ nội dung phải xác định |
|---|---|
| Lý do | Phụ thuộc kỹ thuật nào chưa thay thế được |
| Chủ sở hữu | Nhóm chịu trách nhiệm chức năng và rủi ro |
| Phạm vi | Những máy, nguồn kết nối và danh tính nào |
| Kiểm soát bù | Giới hạn mạng, lệnh, credential và giám sát |
| Thời hạn | Ngày hết hạn và mốc kiểm tra lại |
| Đóng ngoại lệ | Kế hoạch, tiêu chí và người nghiệm thu |

forced-commands-only là một chế độ hạn chế đặc thù, không tương đương cấm root SSH. Lệnh cưỡng bức vẫn chạy với quyền của tài khoản đích; việc đánh giá wrapper, đầu vào và các kênh kết nối khác là một thiết kế cần kiểm thử riêng. Không dùng tên một chế độ như bằng chứng rằng giải pháp đã tối thiểu hóa mọi quyền.

Với break-glass, nên ưu tiên một đường được chuẩn bị trước, độc lập với thành phần có thể hỏng. Không giữ một khóa root không rõ chủ sở hữu làm “dự phòng”. Credential khẩn cấp phải có quy trình lấy, cảnh báo sử dụng, thu hồi hoặc luân chuyển sau dùng và rà soát sự kiện.

## 12. Giám sát, bằng chứng và phát hiện sai lệch

Mỗi thay đổi cần để lại đủ thông tin để người khác tái kiểm tra mà không cần nhận credential bí mật.

Một hồ sơ bằng chứng hữu ích gồm:

- Danh sách máy, listener và phiên bản cấu hình trong phạm vi.
- Kết quả kiểm tra cú pháp và cấu hình hiệu lực theo những ngữ cảnh quan trọng.
- Kết quả nạp cấu hình, thời điểm thực hiện và người thực hiện.
- Kết quả kiểm thử tài khoản hợp lệ, root bị chặn và tác vụ nâng quyền.
- Tình trạng phụ thuộc automation và đường khẩn cấp.
- Ngoại lệ còn hiệu lực, chủ sở hữu và ngày kết thúc.

Tùy hệ thống, sự kiện xác thực có thể nằm trong journal, /var/log/auth.log hoặc /var/log/secure. Ví dụ khi dịch vụ được ghi log vào journal dưới unit sshd:

~~~bash
sudo journalctl -u sshd.service --since "15 minutes ago" --no-pager
~~~

Dùng đúng unit và thời gian thực tế; không coi lệnh không có kết quả là chứng minh không có sự kiện. Một số bản phân phối hoặc cấu hình gửi log tới nơi khác.

Khi điều tra, ghép thời gian, máy đích, địa chỉ nguồn, tài khoản đích, danh tính nguồn ở cổng PAM và mã phiên hoặc mã yêu cầu. Log sudo cho thấy có yêu cầu thực thi quyền; shell history không phải nhật ký kiểm toán đáng tin cậy và cũng không thay thế ghi phiên.

Các tín hiệu nên xem xét theo môi trường:

1. Có xác thực SSH root thành công tại máy vốn phải chặn.
2. Cấu hình hiệu lực chuyển khỏi giá trị chính sách.
3. Xuất hiện tài khoản UID 0 chưa được phê duyệt.
4. Có thay đổi nguồn tin cậy của credential quản trị ngoài kế hoạch.
5. Credential break-glass được sử dụng nhưng không có sự kiện quản lý tương ứng.

Nhiều lần root SSH thất bại từ một nguồn lạ cần được phân tích cùng các dữ kiện khác. Không kết luận đã bị chiếm máy chỉ từ tên root trong một dòng log thất bại; cũng không bỏ qua một lần thành công chỉ vì phần lớn lần thử bị chặn.

Máy đã bị chiếm quyền root có thể bị sửa cấu hình hoặc log cục bộ. Chuyển log ra hệ thống tập trung và bảo vệ quyền quản trị cấu hình giúp giữ thêm bằng chứng, nhưng không biến root restriction thành cơ chế chống mọi hành vi sau xâm nhập.

## 13. Chẩn đoán và khôi phục

| Triệu chứng | Hướng kiểm tra |
|---|---|
| File có PermitRootLogin no nhưng root vẫn vào được | Đúng máy, listener, daemon, file cấu hình, Match và trạng thái reload chưa |
| Root “vẫn dùng được” trong terminal cũ | Đó là phiên cũ hay một kết nối SSH mới; có đang chuyển quyền bằng sudo không |
| Tài khoản cá nhân cũng không vào được | Log xác thực, trạng thái danh tính, key, MFA, PAM và thay đổi ngoài phạm vi |
| Cấu hình đúng rồi tự quay lại | Công cụ đồng bộ, image, cloud initialization hoặc script khởi tạo |
| Backup thất bại sau thay đổi | Job có còn dùng root trực tiếp; danh tính và quyền thay thế đã được kiểm thử chưa |
| Khóa mật khẩu rồi khóa SSH vẫn hoạt động | Phân biệt password token với cơ chế đăng nhập và kiểm tra account thực tế |
| Console không dùng được trong sự cố | Kiểm tra IAM lớp nền tảng, credential cứu hộ và PAM/login của đường console |

Nếu cần rollback, dùng phiên hoặc đường cứu hộ đã chuẩn bị để phục hồi đúng các file cấu hình của thay đổi. Kiểm tra cú pháp trước khi nạp lại và kiểm thử kết nối sau đó. Nếu dùng configuration management, hoàn tác ở nguồn quản lý để trạng thái không bị đẩy ngược trở lại.

Không lấy PermitRootLogin yes làm phản xạ khôi phục cho mọi lỗi. Ví dụ, tài khoản cá nhân thiếu khóa không có nghĩa là yêu cầu mở root SSH toàn mạng. Cần xác định lỗi và thực hiện phương án khôi phục đã chuẩn bị. Nếu buộc phải kích hoạt ngoại lệ khẩn cấp, ghi phạm vi, thời hạn và kiểm tra việc đóng ngoại lệ sau xử lý.

Giữ bằng chứng thay đổi lỗi và rollback để tìm nguyên nhân. Chỉ xóa dấu vết lỗi khỏi ticket sẽ làm lần triển khai tiếp theo khó an toàn hơn.

## 14. Tình huống vận hành: thay thế root SSH trong nhóm máy ứng dụng

Một nhóm có 20 máy Linux. Nhân sự dùng khóa SSH chung của root. Job backup đêm cũng dùng khóa đó. Nhóm muốn bật PermitRootLogin no ngay trên toàn bộ máy.

Vấn đề không chỉ nằm ở cấu hình SSH. Credential chung đang phục vụ cả người và máy; nếu đổi chính sách đồng loạt, job có thể hỏng và người vận hành có thể mất đường sửa.

Một kế hoạch hợp lý:

1. Tách danh tính con người và job backup; xác định rõ chủ sở hữu của từng đường truy cập.
2. Cấp tài khoản cá nhân, xác thực theo chính sách và quyền cho tác vụ vận hành cần thiết.
3. Tạo phương án backup dùng danh tính máy riêng, kiểm thử backup và restore trên máy đại diện.
4. Xác minh console được bảo vệ và người trực ca có thể dùng quy trình khẩn cấp.
5. Chặn root SSH trên một canary, thử ma trận chấp nhận và theo dõi job phụ thuộc.
6. Mở rộng theo từng nhóm máy, ghi nhận kết quả từng máy.
7. Thu hồi credential chung không còn cần thiết theo quy trình quản lý khóa.
8. Cập nhật cấu hình gốc, giám sát drift và đóng mọi ngoại lệ tạm.

Thành công của kế hoạch được đo bằng đường truy cập thực tế, chức năng vận hành và bằng chứng danh tính. Một tỷ lệ “20/20 file đã sửa” chưa mô tả đầy đủ kết quả.

## 15. Bài thực hành và tiêu chí tự đánh giá

Dùng một VM có OpenSSH, một tài khoản quản trị cá nhân và quyền truy cập console. Không dùng môi trường duy nhất mà bạn không có cách khôi phục.

### Nhiệm vụ

1. Ghi lại các đường có thể dẫn tới root trên VM, bao gồm SSH, sudo, su và console.
2. Đọc trạng thái mật khẩu root mà không thu thập hash; liệt kê các bản ghi UID 0 nhìn thấy được.
3. Xác minh tài khoản cá nhân đăng nhập và thực hiện đúng tác vụ được phép.
4. Xác định file cấu hình và ngữ cảnh Match liên quan; ghi lại trạng thái ban đầu.
5. Đặt chính sách chặn root SSH, kiểm tra cú pháp và cấu hình hiệu lực.
6. Nạp thay đổi bằng cơ chế của VM, sau đó thử bằng các kết nối mới.
7. Ghi kết quả dương tính, âm tính, log tương ứng và các giới hạn của kiểm thử.
8. Thực hành rollback theo kế hoạch rồi áp dụng lại chính sách nếu đó là mục tiêu cuối của lab.

### Câu hỏi kiểm tra hiểu biết

**Root password bị khóa nhưng chính sách SSH là prohibit-password. Có đủ bằng chứng rằng root SSH bị cấm chưa?**

Chưa. Phải xem những phương thức khác còn được phép, cấu hình account và hành vi thực tế. Hai kiểm soát này không diễn đạt cùng một yêu cầu với PermitRootLogin no.

**Root không mở được phiên SSH mới nhưng sudo id -u trả về 0. Có mâu thuẫn không?**

Không. Một kiểm soát chặn đăng nhập trực tiếp, còn phép thử kia thể hiện một lệnh được cấp quyền thực thi dưới root. Cần đánh giá phạm vi sudo riêng.

**Vì sao một lần root đăng nhập thất bại chưa đủ cho nghiệm thu?**

Có thể đã dùng sai key, sai listener hoặc không đến được máy đích. Cần kiểm tra ngữ cảnh, trạng thái áp dụng và log; đồng thời xác minh người dùng hợp lệ vẫn làm việc được.

**Tại sao vẫn cần break-glass khi đã có tài khoản cá nhân và MFA?**

Hệ thống định danh, MFA hoặc đường mạng quản trị có thể gặp sự cố. Đường khẩn cấp được chuẩn bị giúp phục hồi mà vẫn giữ chủ sở hữu, giới hạn sử dụng và bằng chứng.

### Điều kiện hoàn thành bài thực hành

Bạn có thể giải thích chính xác đường nào bị chặn, đường nào còn được phép và lý do. Cấu hình hiệu lực đáp ứng chính sách trên các listener trong phạm vi; kiểm thử mới cho thấy root trực tiếp bị từ chối, tài khoản hợp lệ hoạt động và quyền nâng tuân theo yêu cầu. Các phụ thuộc có chủ sở hữu, đường khôi phục đã được kiểm tra và bằng chứng không chứa credential bí mật.


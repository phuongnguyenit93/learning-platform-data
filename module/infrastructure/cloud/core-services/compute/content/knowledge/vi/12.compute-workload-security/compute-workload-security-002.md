# Giảm bề mặt tấn công bằng baseline hệ điều hành tối thiểu

Máy ảo thường được tạo từ một image hệ điều hành có sẵn nhiều package, service, tài khoản và công cụ quản trị. Mỗi thành phần được cài đặt hoặc bật lên có thể tạo thêm mã cần vá, cổng mạng cần bảo vệ, quyền cần kiểm soát và khả năng bị khai thác. Một máy chủ chạy ứng dụng web không nhất thiết cần trình biên dịch, máy chủ in, dịch vụ chia sẻ file hay nhiều daemon quản trị khác.

**Baseline hệ điều hành tối thiểu** là tập hợp cấu hình và thành phần nền được phê duyệt để máy chỉ có những chức năng cần thiết cho workload, đồng thời vẫn đáp ứng yêu cầu vận hành, giám sát và bảo mật. Baseline giúp giảm bề mặt tấn công, tạo ra máy chủ nhất quán và làm cho việc kiểm tra tuân thủ có thể tự động hóa.

Trong module compute, baseline cần được xem xét cùng image máy ảo, cấu hình mạng, danh tính workload, triển khai ứng dụng và quy trình vá lỗi. Một hệ điều hành được harden tốt vẫn có thể bị xâm nhập nếu ứng dụng có lỗ hổng, secret bị lộ hoặc security group mở quá rộng. Vì vậy, baseline là một lớp trong kiến trúc bảo vệ nhiều lớp.

## 1. Bề mặt tấn công của hệ điều hành

Bề mặt tấn công là tổng hợp những điểm mà người dùng, ứng dụng hoặc tác nhân bên ngoài có thể tương tác với hệ thống và có khả năng gây ảnh hưởng. Trên máy ảo, các điểm này có thể gồm:

- Dịch vụ mạng đang lắng nghe như SSH, RDP, web server, database hoặc agent quản trị.
- Package, thư viện, kernel module và runtime có lỗ hổng đã biết.
- Tài khoản, nhóm, quyền sudo/Administrator, khóa SSH và cơ chế xác thực.
- Giao diện quản trị, API cục bộ, socket và scheduled task.
- Cấu hình firewall, route, DNS và các kênh kết nối từ mạng khác.
- Công cụ build, compiler, package manager, shell và script có thể bị lạm dụng sau khi xâm nhập.
- Log, file tạm, cache, credential và dữ liệu nhạy cảm trên đĩa.

Mỗi thành phần bổ sung làm tăng chi phí cập nhật và kiểm soát. Một daemon không cần thiết có thể chứa lỗ hổng, chạy bằng quyền cao hoặc mở một cổng mạng mà đội vận hành không biết. Một compiler cài trên production có thể giúp kẻ tấn công biên dịch công cụ ngay trên máy. Một tài khoản dùng chung khiến việc xác định ai đã thực hiện thao tác trở nên khó khăn.

Giảm bề mặt tấn công không có nghĩa là xóa mọi thành phần. Máy vẫn cần những chức năng tối thiểu để boot, quản trị, lấy cấu hình, ghi log, giám sát, bảo vệ endpoint và phục vụ ứng dụng. Nếu loại bỏ một agent hoặc thư viện mà workload phụ thuộc, máy có thể mất khả năng quan sát hoặc ngừng hoạt động. Mục tiêu là giữ đúng thành phần có nhu cầu rõ ràng, có chủ sở hữu và có cách cập nhật.

## 2. Nguyên tắc thiết kế baseline tối thiểu

Một baseline tốt thường dựa trên các nguyên tắc sau:

1. **Least functionality:** chỉ cài và bật chức năng cần thiết cho workload.
2. **Least privilege:** tiến trình và người vận hành chỉ có quyền cần cho nhiệm vụ.
3. **Secure by default:** cấu hình mặc định hạn chế truy cập; mở quyền hoặc dịch vụ theo yêu cầu được phê duyệt.
4. **Patchable:** hệ điều hành, package và agent có nguồn cập nhật tin cậy và vòng đời hỗ trợ rõ ràng.
5. **Observable:** trạng thái cấu hình, log, metric và sự kiện bảo mật có thể thu thập.
6. **Reproducible:** baseline được mô tả bằng mã hoặc chính sách có phiên bản, có thể dùng để tạo lại máy.
7. **Recoverable:** có cách khôi phục khi thay đổi hardening làm máy không boot, không truy cập được hoặc ứng dụng không hoạt động.

Baseline nên phân biệt ba lớp:

| Lớp | Phạm vi | Ví dụ |
|---|---|---|
| Nền tảng chung | Áp dụng cho mọi máy thuộc image family | Bản vá, tài khoản mặc định, đồng bộ thời gian, audit, firewall mặc định |
| Profile workload | Áp dụng theo vai trò của máy | Web/API, worker, database, bastion, máy xử lý batch |
| Ngoại lệ có kiểm soát | Điều chỉnh cần thiết do ứng dụng hoặc hệ thống cũ | Module kernel đặc thù, cổng legacy, package tương thích |

Không nên duy trì một baseline duy nhất cho mọi loại máy nếu workload có yêu cầu khác nhau. Ví dụ, máy database cần công cụ sao lưu và giám sát lưu trữ; máy web edge có thể cần reverse proxy; máy worker nội bộ có thể không cần bất kỳ cổng inbound nào. Có thể dùng một nền tảng chung rồi mở rộng bằng profile chuyên biệt.

## 3. Chọn hệ điều hành và image nguồn phù hợp

Giảm bề mặt tấn công bắt đầu từ lựa chọn image. Ưu tiên image chính thức hoặc image nội bộ đã được kiểm duyệt, có nguồn gốc và chữ ký hoặc cơ chế xác minh phù hợp. Hệ điều hành phải còn trong thời gian hỗ trợ bảo mật, tương thích với ứng dụng và có quy trình cập nhật được tổ chức duy trì.

Với Linux, có thể cân nhắc image cloud tối ưu hoặc bản cài đặt tối thiểu của một distribution được hỗ trợ. Với Windows Server, cân nhắc Server Core khi ứng dụng tương thích và không cần giao diện đồ họa đầy đủ. Chọn bản tối thiểu giúp giảm package và service, nhưng cần kiểm tra agent, runtime, driver và công cụ quản trị có hỗ trợ hay không.

Các tiêu chí chọn image:

- Nhà cung cấp và nguồn phát hành đáng tin cậy; có tài liệu về cách cập nhật.
- Phiên bản hệ điều hành còn được hỗ trợ trong toàn bộ vòng đời dự kiến.
- Có bản vá bảo mật định kỳ và thông báo lỗ hổng rõ ràng.
- Tương thích với loại instance, driver, guest agent và công cụ giám sát.
- Có thể kiểm tra package inventory, chữ ký và trạng thái cấu hình.
- Không chứa dữ liệu, tài khoản, SSH host key, token hoặc trạng thái riêng của máy build.

Không chọn image chỉ vì dung lượng nhỏ nhất. Một image không có agent quản trị hoặc không nhận được bản vá có thể làm tăng rủi ro vận hành. Hãy đánh giá tổng thể chi phí hỗ trợ, khả năng quan sát, thời gian boot và mức độ tương thích của workload.

## 4. Kiểm kê và loại bỏ thành phần không cần thiết

Trước khi harden, hãy kiểm kê package, service, cổng lắng nghe, tài khoản và tác vụ tự động. Cần biết thành phần nào được hệ điều hành yêu cầu, thành phần nào do image builder thêm và thành phần nào được ứng dụng cài trong quá trình triển khai.

Trên Linux, có thể dùng các lệnh kiểm tra như:

```bash
# Liet ke package tren Debian/Ubuntu
dpkg-query -W -f='${binary:Package}\t${Version}\n'

# Liet ke service dang chay
systemctl --type=service --state=running

# Liet ke service duoc cau hinh enable
systemctl list-unit-files --type=service --state=enabled

# Xem cac cong dang lang nghe
sudo ss -lntup
```

Trên hệ thống dùng RPM, có thể kiểm kê package bằng `rpm -qa`. Tên lệnh và cách quản lý service thay đổi theo distribution. Trên Windows, có thể kiểm tra service và phần mềm đã cài bằng PowerShell:

```powershell
Get-Service | Sort-Object Status, Name
Get-ItemProperty `
  'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*', `
  'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' `
  -ErrorAction SilentlyContinue |
  Select-Object DisplayName, DisplayVersion, Publisher
```

Lệnh kiểm kê registry trên chỉ là ví dụ cho phần mềm đăng ký trong các uninstall key; một số ứng dụng portable hoặc package quản lý theo cách khác có thể không xuất hiện. Với fleet lớn, nên dùng công cụ inventory/endpoint management để có dữ liệu nhất quán.

Với từng thành phần, hãy trả lời:

- Workload hoặc đội nào cần thành phần này?
- Thành phần có lắng nghe mạng hoặc chạy với quyền cao không?
- Có lỗ hổng, vòng đời hỗ trợ hoặc bản vá nào cần theo dõi không?
- Có thể thay thế bằng dịch vụ quản lý bên ngoài hoặc agent dùng chung không?
- Nếu tắt hoặc gỡ, có ảnh hưởng boot, quản trị, logging, backup hay recovery không?

Chỉ gỡ package hoặc disable service sau khi đã xác nhận dependency. Không tắt ngẫu nhiên các service hệ thống chỉ vì tên không quen thuộc. Một số dịch vụ hỗ trợ DNS, network configuration, time sync, storage, guest agent hoặc bảo vệ endpoint có thể cần thiết để máy vận hành an toàn.

## 5. Giảm dịch vụ mạng và cổng lắng nghe

Mỗi service lắng nghe trên mạng là một điểm cần bảo vệ. Baseline nên quy định rõ máy nào được phép mở cổng nào và từ nguồn nào. Mặc định không cần inbound từ mạng khác thì không mở cổng inbound; nếu cần, giới hạn nguồn theo security group, NSG, firewall hoặc dải quản trị phù hợp.

Trên Linux, sau khi kiểm kê bằng `ss -lntup`, đối chiếu từng socket với service và workload. Nếu không cần FTP, Telnet, server in, RPC cũ hoặc dịch vụ chia sẻ file, hãy loại bỏ hoặc tắt theo hướng dẫn của distribution. Không dùng Telnet để quản trị từ xa vì thông tin xác thực và dữ liệu có thể truyền không mã hóa.

Với SSH, một cấu hình baseline thường cân nhắc:

```text
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
AllowGroups cloud-ops
X11Forwarding no
```

Đây là ví dụ định hướng, không phải cấu hình dùng nguyên trạng cho mọi môi trường. Trước khi tắt xác thực bằng mật khẩu, phải xác nhận tài khoản quản trị có khóa hoặc phương thức đăng nhập thay thế hoạt động, quyền file khóa đúng và có kênh console/management để khôi phục. Hãy kiểm tra cú pháp bằng `sshd -t`, mở một phiên quản trị mới để thử, rồi mới reload service. Không đóng phiên đang hoạt động cho đến khi xác minh đường truy cập mới.

Với Windows, hạn chế RDP vào mạng quản trị hoặc dịch vụ truy cập riêng; không phơi cổng RDP trực tiếp ra Internet. Dùng xác thực mạnh, Network Level Authentication khi phù hợp, Windows Firewall và cơ chế quản trị có kiểm soát. Nếu workload không cần RDP, không bật remote desktop chỉ để thuận tiện.

Firewall trong guest OS và firewall ở cloud bổ sung cho nhau. Security group/NSG kiểm soát lưu lượng ở lớp mạng cloud; host firewall kiểm soát thêm ở máy. Nên dùng cả hai lớp theo mô hình defense in depth, đồng thời tránh rule xung đột khiến đội vận hành mất quyền truy cập hợp lệ.

## 6. Bảo vệ tài khoản và quyền quản trị

Tài khoản mặc định, tài khoản không còn chủ sở hữu và quyền quản trị quá rộng làm tăng nguy cơ chiếm quyền. Baseline cần có quy tắc về tài khoản cục bộ, nhóm quản trị, sudo, quyền file và xác thực.

Các thực hành thường dùng:

- Tạo tài khoản quản trị cá nhân hoặc định danh riêng để có thể truy vết; tránh dùng chung một tài khoản cho cả nhóm.
- Dùng tài khoản service riêng cho ứng dụng, không chạy mọi workload bằng `root` hoặc `LocalSystem` nếu không cần.
- Cấp quyền qua nhóm được quản lý tập trung và loại bỏ quyền khi người dùng chuyển vai trò hoặc rời tổ chức.
- Yêu cầu xác thực mạnh và MFA ở lớp truy cập quản trị hoặc hệ thống identity-aware access.
- Hạn chế đăng nhập trực tiếp bằng root/Administrator; dùng cơ chế nâng quyền có kiểm soát và ghi log.
- Đặt quyền file cấu hình, khóa riêng, thư mục dữ liệu và socket theo nguyên tắc tối thiểu.
- Rà soát tài khoản không sử dụng, khóa hoặc vô hiệu hóa theo chính sách.

Trên Linux, cần kiểm tra `/etc/passwd`, `/etc/shadow`, nhóm sudo và quyền của các file nhạy cảm. Trên Windows, rà soát local Administrators, service account, quyền đăng nhập tương tác và quyền chạy service. Không xóa tài khoản hệ thống tùy tiện vì package hoặc service có thể phụ thuộc vào chúng.

Quyền quản trị cloud và quyền đăng nhập vào guest OS là hai lớp riêng. Người có quyền tạo VM không nhất thiết cần quyền root bên trong máy; ngược lại, quyền SSH vào máy không nên tự động cấp quyền sửa VPC, security group hoặc IAM. Quản lý hai lớp bằng vai trò và audit riêng.

## 7. Hardening kernel và cơ chế bảo vệ hệ điều hành

Kernel là thành phần đặc quyền quản lý tiến trình, bộ nhớ, thiết bị và mạng. Baseline cần sử dụng kernel được nhà cung cấp hệ điều hành hỗ trợ, cài bản vá bảo mật và hạn chế module hoặc tính năng không cần thiết theo profile đã kiểm thử.

Các biện pháp có thể gồm:

- Cập nhật kernel và thư viện hệ thống từ repository tin cậy, có xác minh chữ ký package.
- Hạn chế module kernel không dùng theo hướng dẫn của distribution và workload.
- Dùng SELinux hoặc AppArmor trên Linux khi ứng dụng và image hỗ trợ; duy trì policy phù hợp thay vì tắt cơ chế vì một lỗi quyền.
- Bật các tính năng bảo vệ bộ nhớ và thực thi do hệ điều hành hỗ trợ, chẳng hạn ASLR, NX/DEP và cơ chế kiểm soát ứng dụng phù hợp.
- Bật Secure Boot hoặc vTPM nếu loại instance, image và quy trình boot hỗ trợ, đồng thời kiểm tra khả năng cập nhật kernel/driver.
- Bật audit cho hành động quản trị, thay đổi cấu hình và sự kiện bảo mật cần thiết.
- Trên Windows, duy trì Microsoft Defender Antivirus/Endpoint Protection, Windows Firewall, UAC và các chính sách bảo vệ được tổ chức phê duyệt.

Không bật hoặc tắt một tính năng kernel chỉ dựa trên danh sách hardening chung. Một module có thể cần cho storage, network, filesystem hoặc agent. Một policy SELinux/AppArmor quá chặt có thể làm ứng dụng không khởi động; cần kiểm tra log từ chối và viết policy hẹp theo hành vi hợp lệ thay vì chuyển toàn bộ hệ thống sang chế độ tắt bảo vệ.

## 8. Cấu hình hệ thống, đồng bộ thời gian và audit

Baseline cần kiểm soát các cấu hình ảnh hưởng đến xác thực, log và điều tra sự cố. Thời gian hệ thống sai có thể làm lỗi TLS, xác thực token, đối chiếu log và phân tích sự kiện. Máy cần đồng bộ thời gian với nguồn tin cậy được tổ chức hoặc nền tảng hỗ trợ.

Những cấu hình cần quản lý gồm:

- Time synchronization và timezone chuẩn cho môi trường vận hành.
- DNS resolver và search domain theo mạng của workload.
- Hostname, machine ID và danh tính agent được tạo riêng cho từng instance.
- Audit log cho đăng nhập, nâng quyền, thay đổi tài khoản, service và cấu hình bảo mật.
- Log hệ thống được chuyển tới nơi lưu trữ tập trung có kiểm soát truy cập và thời gian lưu phù hợp.
- Giới hạn quyền đọc log và bảo vệ log khỏi bị sửa hoặc xóa bởi tài khoản ứng dụng.
- Chính sách log rotation và dung lượng đĩa để log không làm đầy filesystem.

Không đưa private key, token, password hoặc dữ liệu nhạy cảm vào log. Nếu log có dữ liệu nghiệp vụ hoặc thông tin cá nhân, cần áp dụng chính sách lọc, phân quyền và lưu giữ tương ứng.

## 9. Cập nhật bảo mật và quản lý package

Một baseline tối thiểu phải có quy trình cập nhật. Giảm số package giúp giảm số thành phần cần vá, nhưng không loại bỏ nhu cầu cập nhật kernel, runtime, agent và thư viện vẫn được sử dụng.

Quy trình cập nhật nên xác định:

1. Nguồn package/repository được phép và cách xác minh chữ ký.
2. Chu kỳ kiểm tra bản vá định kỳ và cơ chế xử lý khẩn cấp cho lỗ hổng nghiêm trọng.
3. Cách đánh giá ảnh hưởng của bản vá với ứng dụng, driver và agent.
4. Cách thử nghiệm trên image hoặc nhóm máy canary trước khi rollout.
5. Cách reboot hoặc áp dụng live patch nếu được hỗ trợ, cùng điều kiện xác nhận kernel đang chạy đã được cập nhật.
6. Cách theo dõi máy chưa vá, máy không còn được hỗ trợ và ngoại lệ quá hạn.

Không chỉ cập nhật image rồi cho rằng toàn bộ fleet đã được vá. Máy đang chạy từ image cũ vẫn giữ package cũ cho đến khi được patch tại chỗ hoặc thay thế bằng instance mới. Mô hình immutable infrastructure thường tạo image mới đã vá rồi rollout thay thế máy theo từng đợt; các workload cần duy trì lâu có thể dùng patch management để xử lý fleet hiện tại.

Tránh thêm repository không rõ nguồn hoặc tải package trực tiếp từ URL không được xác minh. Ghi nhận inventory và phiên bản để có thể biết máy nào chịu ảnh hưởng khi một package xuất hiện lỗ hổng.

## 10. Baseline theo vai trò workload

Một baseline chung cần được mở rộng theo vai trò máy. Ví dụ:

| Vai trò | Thành phần cần thiết có thể có | Thành phần thường có thể loại bỏ nếu không dùng |
|---|---|---|
| Web/API server | OS, runtime ứng dụng, web proxy nếu cần, monitoring, endpoint protection, log agent | Compiler, desktop GUI, print service, file sharing, công cụ quản trị không dùng |
| Worker/batch | Runtime, queue client, monitoring, log agent, cơ chế checkpoint | Inbound listener không cần thiết, web server, desktop GUI |
| Database server | Database engine, storage tools, backup/monitoring agent, endpoint protection | Runtime ứng dụng không liên quan, compiler và dịch vụ chia sẻ không cần thiết |
| Bastion/management host | Công cụ truy cập quản trị được phê duyệt, audit, endpoint protection | Ứng dụng nghiệp vụ, package build, dịch vụ public không cần thiết |
| Máy xử lý dữ liệu | Runtime/driver tính toán, thư viện cần thiết, monitoring và quản lý dữ liệu | Dịch vụ mạng không liên quan, package thử nghiệm không được phê duyệt |

Đây là gợi ý phân loại, không phải danh sách gỡ cài đặt cố định. Ví dụ, một số agent cần inbound listener nội bộ hoặc database cần compiler extension trong một quy trình cụ thể. Mọi ngoại lệ cần có lý do và kiểm thử.

## 11. Mã hóa đĩa và bảo vệ dữ liệu cục bộ

Baseline hệ điều hành cần xác định cách bảo vệ dữ liệu trên volume boot và data volume. Mã hóa at-rest giúp giảm rủi ro khi snapshot, volume hoặc thiết bị lưu trữ bị truy cập trái phép ngoài luồng quản lý bình thường. Dùng cơ chế mã hóa do cloud provider hoặc guest OS hỗ trợ, quản lý khóa qua dịch vụ KMS/Key Vault tương ứng và giới hạn quyền sử dụng khóa.

Các điểm cần xem xét:

- Volume boot có chứa file cấu hình, log hoặc dữ liệu nhạy cảm không?
- Data volume có mã hóa mặc định hay cần bật rõ ràng?
- Snapshot và backup có kế thừa mã hóa không, hay cần cấu hình riêng?
- Ai có quyền tạo snapshot, copy volume, export image hoặc giải mã dữ liệu?
- Cách khôi phục khi key bị disable, xoay vòng hoặc quyền truy cập thay đổi?
- Có dữ liệu tạm, swap, crash dump hoặc file core chứa thông tin nhạy cảm không?

Mã hóa không thay thế quyền truy cập filesystem, kiểm soát snapshot, backup hay xóa dữ liệu. Khóa mã hóa cũng là tài sản quan trọng; nếu quyền KMS quá rộng hoặc key material bị lộ, dữ liệu vẫn có thể bị truy cập.

## 12. Tự động hóa baseline trong golden image và lúc boot

Baseline nên được áp dụng tự động trong pipeline tạo image và kiểm tra lại khi máy khởi động. Có thể dùng Packer, image builder của cloud, Ansible, Chef, Puppet, cloud-init hoặc công cụ quản lý cấu hình tương đương. Cần tránh nhiều công cụ cùng ghi đè một cấu hình mà không có thứ tự hoặc chủ sở hữu rõ ràng.

Một pipeline điển hình:

1. Chọn image nguồn đã phê duyệt và cố định phiên bản.
2. Cài bản vá và package tối thiểu từ repository tin cậy.
3. Áp dụng baseline OS chung và profile workload.
4. Tắt service, cổng và tính năng không cần thiết sau khi xác nhận dependency.
5. Cấu hình tài khoản, quyền, firewall, audit, time sync và endpoint protection.
6. Quét lỗ hổng và kiểm tra cấu hình tự động.
7. Khởi tạo máy thử từ image để xác nhận boot, quản trị, logging và ứng dụng mẫu.
8. Phát hành image version mới cùng báo cáo kiểm tra.

Ví dụ cấu trúc dữ liệu baseline có thể được quản lý trong repository:

```yaml
baseline:
  id: linux-compute-baseline
  version: "2.1"
  os_family: linux
  controls:
    automatic_security_updates: true
    root_ssh_login: false
    password_ssh_login: false
    host_firewall: enabled
    time_sync: required
    audit_logging: required
    endpoint_protection: required
  workload_profile: api-server
```

Đây là ví dụ mô tả chính sách, không phải schema chuẩn của một công cụ cụ thể. Pipeline cần ánh xạ từng control thành cấu hình và phép kiểm tra có thể thực thi. Không nên chỉ ghi `host_firewall: enabled` mà không kiểm tra rule thực tế, trạng thái service và khả năng kết nối cần thiết.

Không nhúng secret vào image. Tài khoản, SSH host key, machine ID và agent identity phải được tạo mới khi clone; secret của workload được cấp lúc chạy bằng danh tính có quyền tối thiểu. Cấu hình riêng theo môi trường được truyền qua bootstrap hoặc hệ thống quản lý cấu hình.

## 13. Kiểm tra baseline và phát hiện cấu hình lệch chuẩn

Một baseline chỉ có giá trị nếu có thể kiểm tra. Nên chuyển các yêu cầu thành control có kết quả rõ ràng: pass, fail, not applicable hoặc exception. Ví dụ, “SSH an toàn” quá mơ hồ; có thể chuyển thành kiểm tra `PermitRootLogin` bị tắt, chỉ nhóm quản trị được phép đăng nhập và password authentication được bật/tắt theo profile đã phê duyệt.

Các cách kiểm tra thường dùng:

- Security benchmark hoặc compliance scanner phù hợp với hệ điều hành.
- Inventory package và vulnerability scanner.
- Kiểm tra service enabled/running và cổng lắng nghe.
- Kiểm tra quyền file, tài khoản, nhóm quản trị và chính sách xác thực.
- Kiểm tra firewall, audit, logging, time sync và endpoint protection.
- Configuration management hoặc agent phát hiện drift giữa trạng thái thực tế và baseline.
- Cloud security posture management hoặc hệ thống quản trị fleet nếu tổ chức sử dụng.

Có thể tham chiếu CIS Benchmarks, Microsoft Security Baselines hoặc tiêu chuẩn nội bộ được phê duyệt. Chọn đúng phiên bản hệ điều hành và profile. Không áp dụng toàn bộ benchmark một cách máy móc: một số control có thể không phù hợp với cloud guest, agent hoặc ứng dụng. Ghi nhận ngoại lệ có lý do, người phê duyệt, biện pháp bù trừ và ngày hết hạn.

**Configuration drift** xảy ra khi máy đang chạy khác baseline do thao tác thủ công, script triển khai, cập nhật package hoặc thay đổi ứng dụng. Có thể phát hiện drift bằng cách so sánh cấu hình định kỳ hoặc dùng agent kiểm tra liên tục. Với thay đổi bảo mật quan trọng, cần cảnh báo sớm và có quy trình sửa tự động hoặc tạo ticket xử lý.

## 14. Kiểm thử thay đổi hardening trước khi rollout

Một thay đổi bảo mật có thể làm ứng dụng mất khả năng truy cập file, mở cổng hoặc gọi dịch vụ phụ thuộc. Vì vậy, baseline cần được kiểm thử trên workload đại diện trước khi áp dụng rộng.

Quy trình kiểm thử nên gồm:

1. Tạo image hoặc instance thử nghiệm từ phiên bản baseline mới.
2. Chạy kiểm tra boot, đăng nhập quản trị, guest agent, monitoring và log.
3. Cài hoặc triển khai ứng dụng mẫu đúng profile.
4. Kiểm tra kết nối tới DNS, secret provider, database, queue và endpoint cần thiết.
5. Chạy health check và smoke test chức năng.
6. Quét lỗ hổng và kiểm tra các control bắt buộc.
7. Kiểm thử reboot, shutdown, backup/restore và khả năng truy cập khi sự cố.
8. Rollout canary, theo dõi metric và mở rộng theo từng nhóm máy.

Nên kiểm tra cả trường hợp vận hành bình thường và tình huống phục hồi. Ví dụ, firewall mới có thể cho phép request từ load balancer nhưng chặn agent gửi log tới endpoint quản trị. Nếu chỉ kiểm thử API, lỗi quan sát này có thể bị bỏ sót.

Khi hardening làm máy không thể truy cập, cần có kênh recovery đã kiểm thử như serial console, cloud console, management agent hoặc khả năng tạo lại máy từ image trước. Với fleet immutable, rollback thường là triển khai lại từ image version đã biết là tốt, sau khi xác nhận dữ liệu ứng dụng được lưu ở volume hoặc dịch vụ phù hợp.

## 15. Ví dụ baseline tối thiểu cho API server Linux

Giả sử một API Java chạy trên Linux trong private subnet. Máy chỉ nhận request từ load balancer, truy cập database nội bộ, lấy secret từ secret manager và gửi log/metric tới dịch vụ quan sát.

Baseline có thể được thiết kế như sau:

| Hạng mục | Cấu hình mục tiêu | Cách xác minh |
|---|---|---|
| Image | Linux LTS còn hỗ trợ, image đã được phê duyệt | Kiểm tra image ID, phiên bản OS và nguồn phát hành |
| Package | OS package, Java runtime và agent cần thiết | Đối chiếu package inventory với allowlist |
| Service | Chỉ bật network, time sync, guest agent, logging, security agent và service ứng dụng cần thiết | `systemctl` và inventory service |
| Network | Không có public IP; chỉ nhận cổng API từ load balancer | Cloud security group/NSG và `ss -lntup` |
| SSH | Không cho root login; xác thực theo phương thức quản trị được phê duyệt | Kiểm tra cấu hình SSH và thử đăng nhập qua kênh quản trị |
| Identity | Tài khoản quản trị cá nhân, user `orders` cho ứng dụng | Kiểm tra nhóm, sudo và quyền file |
| Host firewall | Chỉ cho phép luồng quản trị và ứng dụng đã xác định | Kiểm tra rule firewall và smoke test kết nối |
| Kernel/security | Bản vá, SELinux/AppArmor theo profile, audit | Scanner và kiểm tra trạng thái policy |
| Logging | Log hệ thống và ứng dụng gửi tập trung | Kiểm tra log event từ instance thử |
| Storage | Boot/data volume mã hóa; quyền thư mục hạn chế | Kiểm tra encryption metadata và permission |

Một ví dụ kiểm tra nhanh trên Linux sau khi build:

```bash
cat /etc/os-release
systemctl --type=service --state=running
sudo ss -lntup
sudo sshd -t
sudo systemctl is-active systemd-timesyncd
sudo aa-status 2>/dev/null || sudo getenforce
```

Các lệnh chỉ mang tính minh họa và có thể cần điều chỉnh theo distribution. `systemd-timesyncd` không có trên mọi bản phân phối; một số hệ thống dùng chrony hoặc dịch vụ thời gian khác. `aa-status` dành cho AppArmor, còn `getenforce` dành cho SELinux. Kết quả “không tìm thấy lệnh” không tự chứng minh hệ thống không có cơ chế bảo vệ; cần biết profile đang dùng.

Vì API chỉ nhận traffic từ load balancer, security group của máy chỉ cho phép cổng ứng dụng từ security group nguồn tương ứng. Máy không cần public IP. Outbound chỉ mở các đích cần thiết như database, secret provider, repository cập nhật và dịch vụ logging. Việc quản trị đi qua VPN hoặc hệ thống truy cập riêng, có audit và xác thực mạnh.

## 16. Những lỗi thường gặp khi tối giản hệ điều hành

- **Gỡ package theo cảm tính:** có thể làm mất dependency của ứng dụng hoặc agent. Kiểm kê và kiểm thử trước khi gỡ.
- **Tắt dịch vụ hệ thống không rõ chức năng:** máy có thể mất DNS, network, time sync, storage hoặc guest management. Xác minh vai trò trước khi thay đổi.
- **Tắt firewall để xử lý lỗi kết nối:** làm rộng bề mặt tấn công. Kiểm tra rule và route rồi mở đúng luồng cần thiết.
- **Tắt SELinux/AppArmor vì ứng dụng bị từ chối:** bỏ một lớp bảo vệ quan trọng. Đọc audit log và điều chỉnh policy hẹp.
- **Tắt password SSH trước khi chuẩn bị phương thức khác:** có thể tự khóa quyền quản trị. Kiểm thử phiên mới và giữ kênh recovery.
- **Dùng một baseline cho mọi workload:** có thể thiếu agent hoặc quyền cần thiết, hoặc giữ package thừa. Dùng profile theo vai trò.
- **Chỉ harden image mới:** máy đang chạy vẫn có thể lệch chuẩn hoặc chứa lỗ hổng. Kết hợp patching và drift detection cho fleet.
- **Áp dụng benchmark không kiểm thử:** một số control không tương thích với ứng dụng hoặc cloud agent. Chạy thử và quản lý ngoại lệ.
- **Không có rollback:** một thay đổi sai có thể khiến cả nhóm máy không truy cập được. Giữ image version tốt và kênh recovery.

## 17. Checklist baseline hệ điều hành tối thiểu

- [ ] Image có nguồn tin cậy, phiên bản OS còn được hỗ trợ và có quy trình vá lỗi.
- [ ] Package inventory được đối chiếu với danh sách thành phần cần thiết.
- [ ] Service và cổng lắng nghe được kiểm kê; dịch vụ không cần thiết được loại bỏ hoặc tắt có kiểm soát.
- [ ] Tài khoản mặc định, quyền quản trị và tài khoản service được rà soát.
- [ ] Truy cập SSH/RDP được giới hạn qua kênh quản trị an toàn và xác thực mạnh.
- [ ] Host firewall và cloud network policy chỉ cho phép luồng cần thiết.
- [ ] Kernel, SELinux/AppArmor hoặc cơ chế bảo vệ Windows được cấu hình theo profile đã kiểm thử.
- [ ] Audit, log tập trung, time sync và endpoint protection hoạt động.
- [ ] Boot volume, data volume, snapshot và backup được bảo vệ bằng mã hóa phù hợp.
- [ ] Secret và danh tính riêng của máy được cấp lúc chạy, không nhúng trong image.
- [ ] Baseline được quản lý phiên bản, tự động kiểm tra và phát hiện configuration drift.
- [ ] Workload mẫu vượt qua smoke test, health check, reboot và recovery test.
- [ ] Ngoại lệ có lý do, người phê duyệt, biện pháp bù trừ và ngày hết hạn.

Baseline hệ điều hành tối thiểu giúp máy ảo chỉ chạy những thành phần cần thiết, giảm số điểm có thể bị khai thác và làm cho trạng thái bảo mật dễ kiểm tra hơn. Khi baseline được phân theo vai trò workload, tự động hóa trong image pipeline, kiểm thử trước rollout và duy trì trên toàn fleet, tổ chức có thể giảm rủi ro mà vẫn giữ khả năng quản trị và phục hồi hệ thống.

# Xây dựng baseline cấu hình và quản lý bản vá

Máy chủ cloud thường được tạo từ image hệ điều hành, sau đó cài runtime, agent giám sát, công cụ bảo mật và ứng dụng. Nếu mỗi máy được cấu hình thủ công, các máy trong cùng một nhóm có thể khác nhau về phiên bản package, tài khoản, firewall, chính sách SSH, logging và bản vá. Sự khác biệt này làm tăng nguy cơ bảo mật, khiến việc xử lý sự cố khó dự đoán và làm cho fleet máy chủ khó quản lý.

**Baseline cấu hình** là tập hợp trạng thái chuẩn đã được phê duyệt cho một loại hệ điều hành hoặc nhóm workload. **Quản lý bản vá (patch management)** là quy trình xác định, kiểm thử, triển khai và xác minh các bản cập nhật cho hệ điều hành, kernel, thư viện và thành phần phần mềm. Hai hoạt động bổ trợ cho nhau: baseline xác định cấu hình mong muốn; patch management giữ nền tảng đó được cập nhật và giảm lỗ hổng theo thời gian.

Bài học này thuộc chương **Bảo trì hệ điều hành và máy chủ** của module **CLOUD_CORE_SERVICES_COMPUTE**. Module giúp người học tìm hiểu các mô hình năng lực tính toán trên đám mây, từ máy ảo, container đến serverless; cách chọn CPU, bộ nhớ, mạng và cấu hình bảo mật; triển khai ứng dụng, mở rộng tải, bảo đảm tính sẵn sàng và tối ưu chi phí vận hành. Trong bối cảnh đó, baseline và bản vá là nền tảng để duy trì máy chủ nhất quán, an toàn, dễ mở rộng và có thể khôi phục.

## 1. Baseline cấu hình là gì?

### 1.1. Khái niệm và mục tiêu

**Configuration baseline** là trạng thái cấu hình chuẩn được xác định cho một hệ thống, một nhóm máy hoặc một vai trò máy chủ. Baseline mô tả các thiết lập cần có, các thiết lập bị cấm, phiên bản phần mềm được chấp nhận và cách kiểm tra trạng thái tuân thủ.

Ví dụ, baseline cho Linux VM chạy API có thể quy định:

- Dùng một bản phân phối và phiên bản hệ điều hành còn được nhà cung cấp hỗ trợ.
- Chỉ cài các package cần thiết cho vai trò API.
- Tài khoản quản trị cá nhân dùng SSH key hoặc cơ chế xác thực tập trung.
- Không cho phép đăng nhập SSH trực tiếp bằng tài khoản root.
- Firewall chỉ mở cổng phục vụ ứng dụng và quản trị từ nguồn tin cậy.
- Đồng bộ thời gian với nguồn được phê duyệt.
- Bật logging, monitoring, endpoint protection và backup agent phù hợp.
- Cài bản vá bảo mật theo thời hạn đã định.
- Cấu hình mã hóa, quyền file và chính sách audit theo mức độ nhạy cảm của workload.

Baseline giúp nhiều máy cùng vai trò có hành vi nhất quán. Khi một máy mới được tạo, hệ thống có thể áp dụng baseline tự động thay vì phụ thuộc vào thao tác thủ công.

### 1.2. Baseline không phải một image cố định

Một golden image có thể chứa phần lớn cấu hình nền tảng, nhưng baseline rộng hơn image. Baseline còn bao gồm:

- Cấu hình lúc khởi động và thông tin được cấp từ metadata.
- Chính sách IAM, firewall, security group và network.
- Cấu hình runtime theo môi trường.
- Phiên bản package và bản vá được chấp nhận.
- Cấu hình agent, logging, monitoring và backup.
- Quy tắc kiểm tra, ngoại lệ và bằng chứng tuân thủ.

Image là một cách đóng gói và phân phối trạng thái ban đầu. Configuration management, policy engine và công cụ compliance giúp duy trì trạng thái đó sau khi máy được tạo.

### 1.3. Baseline theo vai trò và mức độ quan trọng

Không nên áp dụng một bộ cấu hình giống hệt cho mọi máy. Máy chủ database, web, worker, bastion và máy build có bề mặt tấn công, yêu cầu hiệu năng và thành phần khác nhau.

| Vai trò | Thành phần thường cần | Điểm cần chú ý |
|---|---|---|
| Web/API | Runtime ứng dụng, reverse proxy, logging agent | Chỉ mở cổng cần thiết; giới hạn quyền tiến trình |
| Database | Database engine, backup agent, monitoring | Bảo vệ dữ liệu, mã hóa, audit và cửa sổ bảo trì |
| Worker/batch | Runtime job, queue client, telemetry | Có thể thay thế hoặc tạo lại; quản lý quyền truy cập dữ liệu |
| Bastion/management | Công cụ truy cập quản trị, audit | Xác thực mạnh, giới hạn nguồn, ghi nhận phiên |
| Build runner | Toolchain, cache, agent CI | Cô lập job, làm sạch workspace, quản lý secret |
| GPU host | Driver, runtime GPU, device plugin/agent | Tương thích driver, kernel, accelerator và workload |

Có thể tạo một baseline nền tảng chung rồi mở rộng theo vai trò. Các khác biệt phải được khai báo rõ, có chủ sở hữu và lý do.

## 2. Xây dựng nội dung baseline

### 2.1. Hệ điều hành và vòng đời hỗ trợ

Bắt đầu bằng việc chọn hệ điều hành và phiên bản còn trong thời gian hỗ trợ của nhà cung cấp. Cần xác định:

- Phiên bản chính, phiên bản phụ và kiến trúc CPU.
- Thời điểm kết thúc hỗ trợ tiêu chuẩn và hỗ trợ mở rộng nếu có.
- Kernel đang dùng và chính sách cập nhật kernel.
- Nguồn package repository được phép.
- Cơ chế nhận bản vá bảo mật và bản cập nhật quan trọng.
- Quy trình nâng cấp major version.

Không nên chọn hệ điều hành chỉ vì image có sẵn hoặc máy khởi động được. Một phiên bản hết hỗ trợ có thể không còn nhận bản vá bảo mật thông thường, khiến rủi ro tăng theo thời gian.

### 2.2. Package và dịch vụ

Baseline nên quy định danh sách package tối thiểu, package bắt buộc và package không được cài. Gỡ các dịch vụ không cần thiết giúp giảm bề mặt tấn công và đơn giản hóa vận hành.

Ví dụ:

- Chỉ cài runtime và thư viện ứng dụng cần thiết.
- Không cài compiler hoặc công cụ debug trên production nếu không có nhu cầu vận hành rõ ràng.
- Tắt hoặc gỡ dịch vụ không dùng như daemon thử nghiệm, server mẫu hoặc dịch vụ mạng dư thừa.
- Khóa phiên bản các thành phần có yêu cầu tương thích.
- Ghi nhận nguồn package và chữ ký repository.
- Có quy trình cập nhật cho cả package hệ điều hành và package ứng dụng.

Không nên gỡ package một cách máy móc. Một package có thể là dependency của agent bảo mật, cloud-init hoặc dịch vụ hệ thống. Trước khi thay đổi, cần kiểm tra dependency và thử trên image thử nghiệm.

### 2.3. Tài khoản, xác thực và quyền

Một baseline máy chủ cần xác định rõ ai có thể đăng nhập và được phép làm gì.

Các nguyên tắc thường dùng:

- Dùng tài khoản cá nhân hoặc danh tính tập trung thay cho tài khoản dùng chung.
- Cấp quyền tối thiểu theo vai trò.
- Hạn chế quyền sudo/administrator và ghi audit khi nâng quyền.
- Không lưu mật khẩu, private key hoặc token trong image.
- Dùng SSH key, certificate, MFA hoặc cơ chế xác thực được tổ chức phê duyệt.
- Vô hiệu hóa tài khoản mặc định không cần thiết sau khi xác minh không ảnh hưởng dịch vụ.
- Có quy trình thu hồi quyền khi nhân sự hoặc workload kết thúc.

Với Linux, cần xem xét quyền của file cấu hình SSH, sudoers, tài khoản hệ thống và shell login. Với Windows, cần quản lý nhóm local administrators, Windows LAPS hoặc cơ chế quản lý mật khẩu quản trị được tổ chức hỗ trợ.

### 2.4. SSH và truy cập quản trị

Đối với máy Linux, baseline có thể quy định:

- Không cho phép root đăng nhập trực tiếp qua SSH.
- Chỉ cho phép phương thức xác thực đã phê duyệt.
- Hạn chế nguồn mạng truy cập SSH.
- Giới hạn nhóm hoặc tài khoản được phép đăng nhập.
- Ghi log xác thực và theo dõi đăng nhập bất thường.

Ví dụ cấu hình OpenSSH minh họa:

~~~text
PermitRootLogin no
PubkeyAuthentication yes
PasswordAuthentication no
AllowGroups ops-admins
~~~

Đây là ví dụ cần điều chỉnh theo cơ chế truy cập thực tế. Trước khi tắt password authentication, phải xác minh key hoặc cơ chế truy cập thay thế hoạt động, có tài khoản dự phòng theo quy định và có console ngoài băng. Kiểm tra cú pháp bằng công cụ của phiên bản OpenSSH đang dùng, sau đó reload dịch vụ trong một phiên thay đổi có kiểm soát. Không khóa đường quản trị đang hoạt động khi chưa có phương án khôi phục.

Với Windows, baseline nên quy định Remote Desktop có được bật hay không, nguồn truy cập được phép, Network Level Authentication, chính sách tài khoản và cơ chế quản trị từ xa. Không mở RDP trực tiếp ra Internet nếu không có kiến trúc bảo vệ đã được phê duyệt.

### 2.5. Firewall và cấu hình mạng

Firewall trên host là một lớp bảo vệ bổ sung cho security group, network ACL và firewall dịch vụ cloud.

Baseline nên xác định:

- Cổng inbound cần thiết theo vai trò.
- Lưu lượng outbound được phép.
- Nguồn quản trị và nguồn health check.
- Chính sách mặc định khi không có rule phù hợp.
- Logging cho lưu lượng bị từ chối ở mức đủ dùng.
- Cách quản lý IPv4 và IPv6 nhất quán.

Không nên mở rộng firewall theo cách “cho phép tất cả để ứng dụng chạy”. Nếu ứng dụng không hoạt động, cần xác định port, protocol, source, destination và đường đi trước khi thêm rule. Cấu hình firewall cũng phải được kiểm tra sau reboot và sau khi agent quản lý mạng áp dụng lại policy.

### 2.6. Thời gian, logging và giám sát

Thời gian hệ thống sai có thể làm hỏng xác thực, certificate, log correlation và điều tra sự cố. Baseline nên quy định nguồn đồng bộ thời gian, timezone chuẩn và cách theo dõi clock drift.

Logging cần bao gồm các sự kiện phù hợp như:

- Đăng nhập thành công/thất bại và nâng quyền.
- Thay đổi tài khoản, nhóm và chính sách.
- Thay đổi cấu hình mạng, firewall và dịch vụ.
- Lỗi kernel, filesystem và dịch vụ quan trọng.
- Kết quả cài bản vá và reboot.

Log cần được chuyển tới nơi lưu trữ tập trung, giới hạn quyền truy cập và áp dụng retention phù hợp. Không ghi secret, token hoặc dữ liệu nhạy cảm không cần thiết vào log.

Monitoring tối thiểu nên theo dõi CPU, memory, disk usage, filesystem, network, trạng thái dịch vụ, tuổi bản vá và agent bảo mật. Alert phải có ngưỡng và người nhận rõ ràng; quá nhiều cảnh báo không hành động được sẽ làm giảm khả năng phát hiện sự cố.

### 2.7. Mã hóa và bảo vệ dữ liệu

Baseline có thể quy định:

- Mã hóa boot disk và data disk theo chính sách.
- Dùng khóa được quản lý phù hợp với yêu cầu của workload.
- Hạn chế quyền truy cập snapshot và backup.
- Bảo vệ dữ liệu tạm và file cấu hình có secret.
- Dùng giao thức mã hóa phù hợp khi truyền dữ liệu.
- Xóa hoặc làm sạch dữ liệu theo quy trình khi tái sử dụng host hoặc volume.

Mã hóa disk không thay thế quyền file, quản lý secret hoặc kiểm soát truy cập ứng dụng. Cần kết hợp các lớp bảo vệ phù hợp với dữ liệu thực tế.

## 3. Hardening và tiêu chuẩn cấu hình

### 3.1. Hardening là gì?

**System hardening** là quá trình giảm bề mặt tấn công và giới hạn khả năng khai thác bằng cách cấu hình hệ điều hành và dịch vụ an toàn hơn.

Một quy trình hardening có thể bao gồm:

1. Loại bỏ package, dịch vụ và cổng không cần thiết.
2. Thiết lập xác thực mạnh và quyền tối thiểu.
3. Cấu hình firewall, audit và logging.
4. Bảo vệ file hệ thống, secret và dữ liệu.
5. Áp dụng cấu hình kernel và hệ thống phù hợp.
6. Cài agent bảo mật và giám sát.
7. Kiểm tra lại ứng dụng để bảo đảm hardening không làm hỏng chức năng.

Hardening cần cân bằng bảo mật và khả năng vận hành. Một thiết lập quá chặt có thể làm agent không hoạt động, ứng dụng không bind được port hoặc công cụ backup mất quyền. Vì vậy, thay đổi phải được kiểm thử theo vai trò máy chủ.

### 3.2. Dùng benchmark làm điểm khởi đầu

Các tổ chức có thể tham khảo CIS Benchmarks, DISA STIG hoặc hướng dẫn hardening của nhà cung cấp hệ điều hành và cloud. Những bộ chuẩn này cung cấp khuyến nghị kiểm soát cấu hình theo nền tảng và mức độ bảo vệ.

Cần lưu ý:

- Chọn đúng phiên bản hệ điều hành và profile.
- Xem từng khuyến nghị có phù hợp với workload hay không.
- Phân biệt kiểm soát bắt buộc, khuyến nghị và ngoại lệ.
- Kiểm tra tác động đến ứng dụng, hiệu năng và agent.
- Ghi nhận phiên bản benchmark và ngày đánh giá.
- Không áp dụng toàn bộ cấu hình tự động mà không xem xét dependency.

Benchmark là điểm tham chiếu để xây dựng baseline. Chính sách cuối cùng cần được phê duyệt theo rủi ro và yêu cầu của môi trường.

### 3.3. Ngoại lệ có kiểm soát

Một số workload cần cấu hình khác baseline, ví dụ database yêu cầu kernel parameter riêng hoặc agent cũ chưa hỗ trợ phiên bản TLS mới. Ngoại lệ cần có:

- Hệ thống và thiết lập được miễn trừ.
- Lý do kỹ thuật và rủi ro còn lại.
- Biện pháp bù trừ.
- Người phê duyệt và chủ sở hữu.
- Thời hạn xem xét lại hoặc ngày hết hạn.
- Bằng chứng kiểm tra.

Không nên tạo ngoại lệ vô thời hạn hoặc dùng một ngoại lệ chung cho cả fleet khi chỉ một workload có nhu cầu.

## 4. Baseline dưới dạng mã và tự động hóa

### 4.1. Infrastructure as Code và configuration management

Có thể mô tả hạ tầng bằng IaC và cấu hình bên trong host bằng công cụ quản lý cấu hình. Hai lớp bổ sung cho nhau:

- **IaC:** tạo VM, NIC, disk, IAM, security group và metadata.
- **Image pipeline:** tạo image nền đã được cập nhật và harden.
- **Configuration management:** áp dụng package, service, file, user và policy trong guest OS.
- **Policy/compliance:** kiểm tra trạng thái thực tế so với baseline.

Khi cấu hình được lưu trong version control, thay đổi có thể được review, kiểm thử và truy vết. Cần tránh lưu secret trực tiếp trong repository hoặc image.

### 4.2. Ví dụ Ansible cho Linux

Playbook sau minh họa cách khai báo một số thiết lập cơ bản trên hệ Debian/Ubuntu. Danh sách package và dịch vụ cần điều chỉnh theo vai trò và bản phân phối:

~~~yaml
- name: Apply a basic Linux host baseline
  hosts: api_hosts
  become: true
  tasks:
    - name: Install required baseline packages
      ansible.builtin.apt:
        name:
          - chrony
          - unattended-upgrades
          - auditd
        state: present
        update_cache: true
        cache_valid_time: 3600

    - name: Ensure time synchronization is enabled
      ansible.builtin.service:
        name: chrony
        state: started
        enabled: true

    - name: Ensure audit service is enabled
      ansible.builtin.service:
        name: auditd
        state: started
        enabled: true

    - name: Set a managed SSH policy
      ansible.builtin.copy:
        dest: /etc/ssh/sshd_config.d/60-host-baseline.conf
        owner: root
        group: root
        mode: "0600"
        content: |
          PermitRootLogin no
          PubkeyAuthentication yes
      notify:
        - Validate SSH configuration
        - Reload SSH service

  handlers:
    - name: Validate SSH configuration
      ansible.builtin.command: sshd -t
      changed_when: false

    - name: Reload SSH service
      ansible.builtin.service:
        name: ssh
        state: reloaded
~~~

Ví dụ cần được kiểm tra theo phiên bản Ansible, cấu trúc include của OpenSSH và tên service của bản phân phối. Trên một số hệ thống service có tên **sshd** thay vì **ssh**. Việc cấu hình xác thực key phải đi cùng quy trình cấp key hoặc danh tính tập trung; playbook không thay thế kiểm tra truy cập trước khi reload.

Ansible module có tính khai báo giúp chạy lại nhiều lần mà không tạo thay đổi không cần thiết khi trạng thái đã đúng. Tuy vậy, không phải mọi command tùy ý đều idempotent. Với lệnh shell/command, cần định nghĩa điều kiện kiểm tra hoặc dùng module chuyên dụng.

### 4.3. Ví dụ kiểm tra baseline trên Linux

Một số lệnh giúp thu thập trạng thái:

~~~bash
# Hệ điều hành và kernel
cat /etc/os-release
uname -r

# Package có thể nâng cấp trên Debian/Ubuntu
apt list --upgradable

# Cập nhật bảo mật có sẵn trên hệ thống dùng DNF
dnf updateinfo list --security

# Dịch vụ lỗi và log lỗi trong lần boot hiện tại
systemctl --failed
journalctl -p err -b

# Socket đang lắng nghe
ss -lntup

# Kiểm tra thời gian
timedatectl status
~~~

Các lệnh package manager khác nhau giữa bản phân phối. Kết quả chỉ phản ánh repository đang được cấu hình và metadata đã cập nhật. Cần đồng bộ package index trước khi lập kế hoạch patch và xác minh nguồn repository được tin cậy.

### 4.4. Kiểm tra baseline trên Windows

Với Windows Server, baseline có thể được triển khai bằng Group Policy, Local Security Policy, Desired State Configuration, công cụ quản lý endpoint hoặc nền tảng patch management.

Một số lệnh kiểm tra:

~~~powershell
# Thông tin hệ điều hành
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsBuildNumber

# Các hotfix đã cài
Get-HotFix | Sort-Object InstalledOn -Descending

# Trạng thái dịch vụ
Get-Service -Name EventLog | Select-Object Name, Status

# Firewall profile
Get-NetFirewallProfile

# Trạng thái Microsoft Defender nếu có
Get-MpComputerStatus
~~~

Không phải mọi lệnh hoặc thuộc tính đều có trên mọi phiên bản Windows Server hoặc mọi image. Kết quả cần được đối chiếu với baseline và agent quản lý đang dùng. Việc triển khai chính sách nên được kiểm tra trong OU hoặc nhóm máy thử nghiệm trước khi áp dụng rộng.

## 5. Golden image và vòng đời máy chủ

### 5.1. Golden image là gì?

**Golden image** là image máy chủ đã được chuẩn hóa, kiểm tra và phê duyệt để dùng làm nguồn tạo VM. Image thường bao gồm:

- Hệ điều hành và bản vá tại thời điểm build.
- Package nền tảng cần thiết.
- Cấu hình hardening cơ bản.
- Agent giám sát, bảo mật và quản lý.
- Certificate hoặc trust store công khai cần thiết.
- Metadata phiên bản image và thông tin build.

Không nhúng credential, private key, token hoặc dữ liệu riêng của một máy vào golden image. Các thông tin đó phải được cấp lúc triển khai qua secret manager hoặc cơ chế danh tính phù hợp.

### 5.2. Pipeline tạo image

Một pipeline image có thể gồm:

~~~mermaid
flowchart TD
    SRC["Base image từ nguồn tin cậy"]
    PATCH["Cài bản vá và package được phê duyệt"]
    HARDEN["Áp dụng baseline và hardening"]
    TEST["Kiểm thử chức năng, bảo mật và compliance"]
    SCAN["Quét lỗ hổng và kiểm tra artifact"]
    APPROVE["Review và phê duyệt"]
    PUBLISH["Publish image có version"]
    DEPLOY["Tạo VM theo từng nhóm workload"]
    SRC --> PATCH --> HARDEN --> TEST --> SCAN --> APPROVE --> PUBLISH --> DEPLOY
~~~

Pipeline nên cố định phiên bản base image, package và toolchain để có thể tái tạo kết quả. Mỗi image cần metadata như build ID, source, ngày tạo, phiên bản baseline và danh sách package (SBOM nếu quy trình hỗ trợ).

Image chỉ nên được publish sau khi các kiểm tra bắt buộc đạt. Nếu có lỗi, pipeline phải lưu log và dừng ở bước phù hợp.

### 5.3. Immutable infrastructure

Với mô hình **immutable infrastructure**, khi cần thay đổi nền tảng hoặc cập nhật lớn, đội ngũ tạo image mới rồi thay VM cũ bằng VM mới. Cách này giúp trạng thái máy dễ tái lập và giảm cấu hình thủ công tích lũy.

Không phải mọi máy đều có thể thay thế ngay. Database, stateful workload hoặc hệ thống có thiết bị gắn trực tiếp cần kế hoạch migration, backup, replication và cutover riêng. Có thể dùng rolling replacement hoặc blue/green để giảm gián đoạn.

### 5.4. Configuration drift

**Configuration drift** là sự khác biệt giữa trạng thái thực tế của máy và baseline mong muốn. Drift có thể xuất hiện khi:

- Người vận hành sửa file trực tiếp trên host.
- Package được cài thủ công.
- Agent thay đổi cấu hình.
- Một script bootstrap chạy không nhất quán.
- Máy không nhận được cấu hình mới.
- Ngoại lệ tạm thời không được gỡ bỏ.

Cần phát hiện drift bằng cách định kỳ so sánh trạng thái thực tế với cấu hình khai báo. Với thiết lập quan trọng, có thể tự động khắc phục; với thay đổi có rủi ro, nên tạo cảnh báo và yêu cầu review trước khi sửa.

## 6. Quản lý bản vá là gì?

### 6.1. Phạm vi patch management

Patch management không chỉ là chạy lệnh cập nhật hệ điều hành. Phạm vi có thể gồm:

- Kernel và bootloader.
- Package hệ điều hành và thư viện dùng chung.
- OpenSSH, OpenSSL, web server và middleware.
- Runtime Java, .NET, Python, Node.js hoặc Go toolchain.
- Agent bảo mật, monitoring và backup.
- Firmware hoặc driver nếu nền tảng cho phép quản lý.
- Container base image và dependency được đóng gói trong image.

Với VM, đội vận hành thường chịu trách nhiệm nhiều hơn đối với guest OS. Với container, cần cập nhật base image và rebuild image ứng dụng. Với dịch vụ managed hoặc serverless, nhà cung cấp có thể quản lý host và runtime nền, nhưng người dùng vẫn phải cập nhật dependency, runtime version và mã ứng dụng trong phạm vi trách nhiệm của mình.

### 6.2. Phân loại bản cập nhật

| Loại cập nhật | Mục tiêu | Ví dụ |
|---|---|---|
| Security patch | Khắc phục lỗ hổng bảo mật | CVE trong kernel hoặc thư viện |
| Critical update | Sửa lỗi nghiêm trọng ảnh hưởng hệ thống | Lỗi có thể gây crash hoặc mất dữ liệu |
| Bug fix | Sửa lỗi chức năng | Lỗi filesystem hoặc network stack |
| Feature update | Bổ sung tính năng | Nâng cấp phiên bản thành phần |
| Driver/firmware | Cập nhật tương tác phần cứng | NIC, storage hoặc GPU driver |
| Runtime/dependency | Cập nhật nền tảng ứng dụng | JVM, .NET, OpenSSL hoặc package npm |

Không phải mọi bản cập nhật đều có cùng rủi ro. Security patch có thể cần triển khai khẩn cấp; feature update thường cần kiểm thử tương thích và kế hoạch nâng cấp riêng.

### 6.3. Lỗ hổng và mức độ ưu tiên

Không nên ưu tiên patch chỉ dựa vào điểm CVSS. Cần kết hợp:

- Mức độ nghiêm trọng của lỗ hổng.
- Có exploit đang được khai thác ngoài thực tế hay không.
- Máy có thể truy cập từ Internet hoặc mạng không tin cậy không.
- Thành phần bị ảnh hưởng có thực sự được cài và sử dụng không.
- Quyền mà tiến trình có thể đạt được nếu bị khai thác.
- Mức độ nhạy cảm của dữ liệu và vai trò máy chủ.
- Khả năng giảm thiểu tạm thời.
- Mức độ phức tạp và rủi ro của bản cập nhật.

Một lỗ hổng có điểm số trung bình nhưng đang bị khai thác trên máy chủ public-facing có thể cần xử lý trước một lỗ hổng điểm cao nhưng không thể tiếp cận trong môi trường hiện tại.

Có thể dùng các nguồn như thông báo bảo mật của nhà cung cấp, cơ sở dữ liệu CVE, CISA Known Exploited Vulnerabilities (KEV) và công cụ vulnerability management. Cần ghi lại ngày đánh giá vì trạng thái khai thác và mức độ phơi nhiễm có thể thay đổi.

### 6.4. Xác định SLA cho bản vá

Tổ chức nên định nghĩa thời hạn khắc phục theo mức rủi ro và phân loại workload. Ví dụ chính sách minh họa:

| Mức ưu tiên | Điều kiện điển hình | Mục tiêu xử lý minh họa |
|---|---|---|
| Khẩn cấp | Lỗ hổng đang bị khai thác, ảnh hưởng tài sản quan trọng hoặc public-facing | Đánh giá ngay, triển khai biện pháp giảm thiểu và patch theo quy trình khẩn cấp |
| Cao | Lỗ hổng nghiêm trọng có khả năng khai thác thực tế | Trong vài ngày theo SLA tổ chức |
| Trung bình | Rủi ro giới hạn hoặc cần điều kiện khai thác cụ thể | Trong chu kỳ bảo trì đã định |
| Thấp | Ảnh hưởng nhỏ, ít phơi nhiễm | Theo lịch cập nhật định kỳ |

Các khoảng thời gian cụ thể phải do tổ chức phê duyệt theo yêu cầu pháp lý, mức độ quan trọng và năng lực vận hành. Bảng trên không phải SLA áp dụng chung cho mọi hệ thống.

## 7. Quy trình quản lý bản vá đầu cuối

### 7.1. Bước 1: Inventory và xác định phạm vi

Cần biết máy nào tồn tại, thuộc nhóm nào, chạy hệ điều hành nào và ai chịu trách nhiệm.

Inventory nên ghi nhận:

- Instance ID, hostname, account/project và region/zone.
- Hệ điều hành, phiên bản, kernel và kiến trúc.
- Vai trò workload, môi trường và mức độ quan trọng.
- Chủ sở hữu kỹ thuật và nhóm vận hành.
- Nguồn package repository và patch policy.
- Trạng thái agent, backup, monitoring và quản lý cấu hình.
- Thời điểm patch gần nhất và trạng thái reboot cần thiết.

Máy không có owner hoặc không có inventory dễ bị bỏ sót khỏi chu kỳ cập nhật. Cần xử lý cả máy tạm, máy autoscaling, máy trong nhóm khôi phục và node bị cô lập.

### 7.2. Bước 2: Đánh giá bản vá

Thu thập thông báo của nhà cung cấp, danh sách package bị ảnh hưởng và advisory bảo mật. Xác định máy nào thực sự cần cập nhật, dependency nào có thể bị thay đổi và có yêu cầu reboot hay không.

Không nên triển khai một bản vá chỉ vì package manager hiển thị bản mới. Cần kiểm tra repository, chữ ký, nguồn phát hành, phiên bản mục tiêu và compatibility note.

### 7.3. Bước 3: Kiểm thử trong môi trường đại diện

Triển khai trước trên môi trường development hoặc staging có cấu hình gần production. Kiểm tra:

- Ứng dụng khởi động và health check.
- Kết nối database, queue, storage và dịch vụ phụ thuộc.
- Logging, monitoring, backup và agent bảo mật.
- Hiệu năng, CPU, memory và I/O.
- Kernel module, driver và thiết bị tăng tốc nếu có.
- Khả năng reboot, tự phục hồi và rollback.

Với workload quan trọng, nên dùng test tự động và dữ liệu đại diện. Kiểm tra chỉ bằng việc package cài thành công là chưa đủ.

### 7.4. Bước 4: Lập kế hoạch triển khai

Xác định:

- Nhóm máy và thứ tự rollout.
- Cửa sổ bảo trì và người trực.
- Dịch vụ cần drain hoặc chuyển traffic.
- Replica/capacity còn lại trong lúc patch.
- Snapshot, backup hoặc image thay thế.
- Yêu cầu reboot.
- Health check và ngưỡng dừng rollout.
- Phương án khôi phục nếu bản vá gây lỗi.

Không patch đồng thời toàn bộ node trong một cluster nếu việc đó làm mất quorum hoặc không còn đủ capacity phục vụ tải. Với database cluster, cần tuân theo thứ tự và cơ chế failover của hệ quản trị.

### 7.5. Bước 5: Triển khai theo ring hoặc canary

Có thể chia fleet thành các vòng:

1. **Ring 0:** máy thử nghiệm và staging.
2. **Ring 1:** một nhóm nhỏ máy production ít rủi ro.
3. **Ring 2:** một phần fleet đại diện cho nhiều zone hoặc nhóm workload.
4. **Ring 3:** phần còn lại sau khi các vòng trước đạt yêu cầu.

Theo dõi lỗi, latency, throughput, reboot, health check và cảnh báo bảo mật sau từng vòng. Nếu một ngưỡng bị vượt, dừng rollout và điều tra trước khi tiếp tục.

~~~mermaid
flowchart TD
    TEST["Staging / test"]
    CANARY["Canary production"]
    RING2["Ring 2: nhóm đại diện"]
    FLEET["Ring 3: toàn fleet còn lại"]
    CHECK{"Health check đạt?"}
    STOP["Dừng rollout, điều tra và khôi phục"]
    DONE["Xác minh và đóng đợt patch"]

    TEST --> CHECK
    CHECK -->|Đạt| CANARY
    CHECK -->|Không đạt| STOP
    CANARY --> CHECK2{"Canary ổn định?"}
    CHECK2 -->|Đạt| RING2
    CHECK2 -->|Không đạt| STOP
    RING2 --> CHECK3{"Ring 2 đạt?"}
    CHECK3 -->|Đạt| FLEET
    CHECK3 -->|Không đạt| STOP
    FLEET --> DONE
~~~

Sơ đồ minh họa nguyên tắc rollout. Thực tế cần xác định health check và ngưỡng dừng theo từng workload; không nên chỉ dựa vào trạng thái package manager.

### 7.6. Bước 6: Reboot và xác minh sau cập nhật

Một số bản vá chỉ có hiệu lực sau khi khởi động lại, đặc biệt là kernel, thư viện hệ thống được tiến trình giữ trong bộ nhớ hoặc driver. Cần phân biệt:

- Package đã cài nhưng kernel đang chạy chưa đổi.
- Có dịch vụ cần restart để nạp thư viện mới.
- Có yêu cầu reboot toàn máy.
- Có cơ chế live patch được hỗ trợ cho một số thành phần.

Sau cập nhật, xác minh phiên bản package, kernel đang chạy, trạng thái dịch vụ, agent và health check ứng dụng. Trên Linux có thể kiểm tra kernel bằng lệnh **uname -r**; trên Windows có thể kiểm tra build và lịch sử hotfix theo công cụ quản trị.

Không coi “reboot thành công” là kết quả cuối. Cần xác nhận máy đã đăng ký lại với load balancer, cluster hoặc autoscaling group, và ứng dụng đã sẵn sàng nhận traffic.

### 7.7. Bước 7: Đối soát và lưu bằng chứng

Sau mỗi đợt patch, ghi nhận:

- Danh sách máy thành công, thất bại, đang chờ và ngoại lệ.
- Package/version trước và sau.
- Thời gian bắt đầu, kết thúc và reboot.
- Kết quả health check.
- Lỗi phát sinh và cách xử lý.
- Người thực hiện hoặc automation run ID.
- Bằng chứng compliance và liên kết ticket/change record.

Máy thất bại phải có owner và hạn xử lý. Không nên loại khỏi báo cáo chỉ vì nó không phản hồi hoặc đang tắt; cần xác định trạng thái và xử lý theo quy trình.

## 8. Triển khai bản vá trên Linux

### 8.1. Debian và Ubuntu

Quy trình thủ công phổ biến gồm cập nhật package index, xem các bản cập nhật rồi cài đặt theo chính sách:

~~~bash
sudo apt-get update
apt list --upgradable
sudo apt-get upgrade
~~~

Trên hệ thống production, cần kiểm tra kỹ thay đổi trước khi xác nhận. **apt-get upgrade** không thực hiện mọi thay đổi có thể cần thiết như thay package hoặc loại bỏ package; **full-upgrade** có thể thay đổi dependency và gỡ package để đáp ứng nâng cấp. Không chạy lệnh nâng cấp rộng trên fleet production mà không có kế hoạch kiểm thử, backup và rollout.

Có thể xem package nào cần cập nhật và kiểm tra lịch sử cài đặt để đối soát. Tên log và công cụ phụ thuộc phiên bản Debian/Ubuntu.

### 8.2. RHEL, Rocky Linux, AlmaLinux và Fedora Server

Các hệ thống dùng DNF có thể xem advisory bảo mật và cập nhật:

~~~bash
sudo dnf check-update
sudo dnf updateinfo list --security
sudo dnf upgrade --security
~~~

Khả năng lọc theo security advisory và hành vi lệnh phụ thuộc phiên bản DNF, repository và plugin. Với hệ thống yêu cầu kiểm soát thay đổi, cần xem transaction trước, kiểm tra package bị thay thế và ghi nhận kết quả.

### 8.3. Kiểm tra reboot cần thiết

Một số bản phân phối cung cấp công cụ nhận biết reboot cần thiết; cách kiểm tra không giống nhau. Trên Ubuntu có thể có file đánh dấu reboot, trong khi hệ thống khác dùng package hoặc agent riêng. Không nên chỉ dựa vào một file kiểm tra chung cho mọi bản phân phối.

Sau patch kernel, nếu chưa reboot, máy có thể vẫn chạy kernel cũ. Điều này cần được thể hiện trong compliance report, kể cả khi package mới đã được cài.

### 8.4. Live kernel patching

Một số nhà cung cấp và bản phân phối hỗ trợ live patching cho một tập con bản vá kernel. Cơ chế này thay đổi một số phần mã kernel đang chạy mà không cần reboot ngay.

Live patching giúp giảm gián đoạn nhưng có giới hạn:

- Không phải mọi bản vá kernel đều hỗ trợ live patch.
- Có thể cần subscription, agent hoặc cấu hình riêng.
- Một số thay đổi vẫn yêu cầu reboot.
- Kernel và module phải nằm trong ma trận hỗ trợ.
- Cần kiểm tra trạng thái patch đã được áp dụng thực sự.

Live patch không thay thế chu kỳ reboot định kỳ, kiểm thử và cập nhật đầy đủ theo hướng dẫn của nhà cung cấp.

## 9. Triển khai bản vá trên Windows Server

### 9.1. Nguồn cập nhật và chính sách

Windows Server có thể nhận bản cập nhật qua Windows Update, Windows Server Update Services (WSUS), Microsoft Configuration Manager hoặc dịch vụ quản lý cập nhật cloud. Cần chọn một nguồn quản lý nhất quán để tránh nhiều hệ thống cùng điều khiển trạng thái cập nhật.

Baseline nên xác định:

- Kênh cập nhật và nhóm máy nhận bản vá.
- Phân loại cập nhật được phép.
- Thời điểm tải và cài đặt.
- Hành vi restart và thời hạn restart.
- Chính sách trì hoãn hoặc tạm dừng.
- Cách ghi log và báo cáo compliance.

### 9.2. Cài đặt và reboot

Với Windows Server, cần kiểm thử bản cập nhật trên nhóm máy đại diện trước. Một số cập nhật có thể yêu cầu restart và ảnh hưởng dịch vụ đang chạy.

Trước khi patch:

- Kiểm tra backup và khả năng restore.
- Drain node khỏi load balancer hoặc cluster nếu cần.
- Xác minh replication và quorum.
- Kiểm tra dung lượng disk và trạng thái Windows Update.
- Thông báo cửa sổ bảo trì cho người phụ trách.

Sau khi cài:

- Xác minh hotfix/build đã được áp dụng.
- Kiểm tra trạng thái pending reboot.
- Xác nhận service và event log.
- Kiểm tra endpoint protection và monitoring agent.
- Đưa máy trở lại cluster hoặc load balancer sau health check.

### 9.3. Công cụ kiểm tra

Ví dụ PowerShell để xem các hotfix đã cài:

~~~powershell
Get-HotFix | Sort-Object InstalledOn -Descending
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsBuildNumber
Get-Service -Name EventLog | Select-Object Name, Status
~~~

**Get-HotFix** không nhất thiết phản ánh mọi thành phần hoặc mọi loại cập nhật theo cách đầy đủ. Nên dùng thêm báo cáo từ hệ thống quản lý patch và Windows Update history để xác minh trạng thái thực tế.

## 10. Patch management cho container và serverless

### 10.1. Container image

Container image chứa user space và dependency của ứng dụng. Khi base image hoặc package có lỗ hổng, cần:

1. Cập nhật base image lên phiên bản được hỗ trợ.
2. Cập nhật dependency theo lockfile và compatibility.
3. Build lại image từ pipeline tin cậy.
4. Quét lỗ hổng và tạo SBOM nếu quy trình hỗ trợ.
5. Chạy test chức năng, tích hợp và bảo mật.
6. Ký và publish image mới.
7. Rollout pod theo canary hoặc rolling update.
8. Xác minh workload thực tế đang chạy digest mới.

Không nên chỉ cập nhật package bên trong container đang chạy. Khi pod được tạo lại, thay đổi thủ công có thể mất và image cũ vẫn tồn tại trong registry. Cần rebuild và redeploy artifact đã được kiểm tra.

### 10.2. Host của container

Với Kubernetes hoặc nền tảng container tự quản lý, vẫn cần patch node OS, kernel, container runtime, CNI, CSI, device plugin và agent. Việc cập nhật image ứng dụng không cập nhật host.

Quy trình patch node thường gồm cordon, drain theo chính sách disruption budget, cập nhật hoặc thay node, xác minh node Ready rồi mới mở lại scheduling. Cần kiểm tra workload stateful, local storage và giới hạn disruption trước khi drain.

Với dịch vụ Kubernetes managed, nhà cung cấp có thể quản lý một số thành phần control plane hoặc node image tùy dịch vụ. Đội ngũ vẫn phải theo dõi phiên bản hỗ trợ, lịch nâng cấp và trách nhiệm patch được công bố.

### 10.3. Serverless và dịch vụ managed

Nhà cung cấp thường chịu trách nhiệm patch host và một phần runtime nền. Người dùng vẫn chịu trách nhiệm cập nhật:

- Runtime version mà ứng dụng sử dụng.
- Thư viện và dependency trong package.
- Layer, extension hoặc custom runtime.
- Container image nếu dùng serverless container.
- Mã ứng dụng và cấu hình bảo mật.

Cần theo dõi thông báo deprecation của runtime và chuyển sang phiên bản còn được hỗ trợ trước hạn. Managed không có nghĩa mọi dependency ứng dụng tự được cập nhật.

## 11. Lập lịch, bảo trì và giảm gián đoạn

### 11.1. Maintenance window

Maintenance window là khoảng thời gian được xác định để thực hiện cập nhật có thể ảnh hưởng dịch vụ. Cửa sổ cần dựa trên mức độ quan trọng, traffic, phụ thuộc và khả năng phục hồi.

Một kế hoạch bảo trì nên nêu:

- Thời gian bắt đầu/kết thúc.
- Hệ thống và nhóm máy bị ảnh hưởng.
- Người phụ trách và kênh liên lạc.
- Dịch vụ cần drain hoặc failover.
- Các bước patch, reboot và kiểm tra.
- Ngưỡng dừng và tiêu chí hoàn tất.
- Phương án khôi phục.

Cửa sổ bảo trì không thay thế rollout an toàn. Nếu có thể, hãy cập nhật từng node hoặc nhóm nhỏ trong khi phần còn lại tiếp tục phục vụ.

### 11.2. Rolling update

Với fleet nhiều máy, rolling update cập nhật từng nhóm nhỏ thay vì dừng toàn bộ cùng lúc. Cần giữ đủ capacity trong suốt quá trình và bảo đảm số replica khỏe mạnh đáp ứng tải.

Với Kubernetes, có thể kết hợp rolling update, readiness probe, PodDisruptionBudget và node drain. Với VM scale set hoặc autoscaling group, có thể thay từng instance bằng image mới theo batch. Cấu hình cụ thể phụ thuộc nền tảng.

### 11.3. Quorum và stateful service

Database cluster, hệ thống queue hoặc control plane có thể cần quorum. Patch quá nhiều node cùng lúc có thể làm mất quorum và gây gián đoạn hoặc mất khả năng ghi.

Cần tuân theo thứ tự cập nhật được sản phẩm hỗ trợ, xác minh replica lag, trạng thái leader/follower và khả năng failover. Không drain hoặc reboot node chỉ dựa trên số lượng replica danh nghĩa; phải xác nhận các replica còn lại thực sự khỏe mạnh.

## 12. Rollback và phục hồi sau patch

### 12.1. Rollback không phải lúc nào cũng đơn giản

Không phải bản vá nào cũng có thể gỡ bỏ an toàn. Package có thể thay đổi schema, format dữ liệu, cấu trúc kernel hoặc state của ứng dụng. Gỡ package mới có thể không khôi phục được trạng thái trước đó.

Trước khi patch, xác định phương án phục hồi phù hợp:

- Snapshot hoặc backup có thể restore.
- Image cũ đã được giữ và còn tương thích.
- VM mới có thể thay thế VM bị lỗi.
- Có thể chuyển traffic về nhóm máy chưa patch.
- Database có thể phục hồi hoặc failover theo quy trình đã thử.
- Có thể khôi phục cấu hình và secret liên quan.

### 12.2. Ưu tiên thay thế máy từ image đã biết

Với stateless VM, thường dễ tạo instance mới từ image đã được phê duyệt hơn là gỡ hàng loạt package để quay lại trạng thái cũ. Có thể triển khai image mới vào nhóm canary, giữ image cũ trong thời gian quan sát và chuyển traffic khi health check đạt.

Với stateful workload, phải tách vòng đời compute khỏi dữ liệu. Restore snapshot hoặc backup cần tuân theo quy trình ứng dụng và xác minh tính toàn vẹn trước khi đưa traffic trở lại.

### 12.3. Rollback và bảo mật

Nếu bản vá sửa một lỗ hổng đang bị khai thác, quay lại phiên bản dễ bị tổn thương có thể tái mở rủi ro. Nếu cần rollback vì lỗi tương thích, phải có biện pháp giảm thiểu tạm thời, giới hạn exposure và thời hạn khắc phục rõ ràng.

Rollback là phương án phục hồi dịch vụ; nó không tự chứng minh hệ thống trở lại trạng thái an toàn. Cần đánh giá cả chức năng và rủi ro bảo mật sau khi quay lui.

## 13. Đo lường compliance và hiệu quả patch

### 13.1. Chỉ số nên theo dõi

| Chỉ số | Ý nghĩa |
|---|---|
| Patch compliance rate | Tỷ lệ máy đáp ứng chính sách bản vá |
| Missing critical patches | Số máy còn thiếu bản vá quan trọng |
| Mean time to patch | Thời gian trung bình từ khi bản vá được phát hành/đánh giá đến khi áp dụng |
| Reboot compliance | Tỷ lệ máy đã reboot khi bản vá yêu cầu |
| Failed patch rate | Tỷ lệ lần cập nhật thất bại |
| Configuration drift | Số máy lệch baseline |
| Unsupported OS count | Số máy chạy hệ điều hành hết hỗ trợ |
| Exception age | Thời gian ngoại lệ còn hiệu lực |
| Image age | Tuổi của image đang được dùng để tạo máy |
| Coverage | Tỷ lệ máy có inventory, agent và báo cáo đầy đủ |

Không nên chỉ báo cáo tỷ lệ patch tổng. Cần tách theo mức độ nghiêm trọng, vai trò, môi trường, hệ điều hành và nhóm chủ sở hữu. Một tỷ lệ chung cao có thể che giấu một số máy production quan trọng chưa được cập nhật.

### 13.2. Máy ngoại tuyến và máy tạm thời

Máy đang dừng, bị cô lập hoặc chỉ chạy theo job có thể không nhận bản vá trong chu kỳ thông thường. Cần chính sách cho:

- Máy khởi động lại theo lịch và tự patch trước khi nhận traffic.
- Node autoscaling được tạo từ image mới.
- Máy tạm thời có vòng đời ngắn.
- Máy bị mất kết nối với hệ thống quản lý.
- Máy trong môi trường khôi phục hoặc disaster recovery.

Với fleet autoscaling, cách bền vững là cập nhật image và template triển khai để instance mới luôn dùng nền tảng đã được vá. Đồng thời cần thay thế dần instance cũ đang chạy.

### 13.3. Báo cáo và bằng chứng

Một báo cáo patch tốt cần trả lời:

- Có bao nhiêu máy trong phạm vi?
- Bao nhiêu máy đã cập nhật và reboot thành công?
- Máy nào còn thiếu bản vá quan trọng?
- Vì sao các máy còn lại chưa cập nhật?
- Ai sở hữu ngoại lệ và khi nào hết hạn?
- Đợt patch có gây lỗi hoặc ảnh hưởng SLA không?
- Có bằng chứng kiểm thử và khôi phục không?

Dữ liệu cần lấy từ inventory, patch manager, agent và hệ thống giám sát. Tránh đánh dấu compliance chỉ dựa trên việc automation job kết thúc với exit code 0.

## 14. Ví dụ quy trình cho một fleet VM

Một dịch vụ API chạy trên 30 VM ở nhiều zone. Nhóm vận hành dùng một golden image và configuration management để giữ baseline. Mỗi tháng, nhà cung cấp hệ điều hành phát hành bản cập nhật bảo mật.

Quy trình:

1. Inventory xác định 30 VM, phiên bản OS, zone, owner và image hiện tại.
2. Nhóm đánh giá advisory, xác định package bị ảnh hưởng và mức ưu tiên.
3. Pipeline tạo image mới từ base image tin cậy, cài patch, áp dụng hardening và chạy scan.
4. Image mới được triển khai lên staging; test API, database, logging và monitoring.
5. Một VM canary ở production được thay bằng instance từ image mới.
6. Theo dõi error rate, latency, CPU, memory và health check.
7. Nếu ổn định, thay từng batch nhỏ ở các zone, bảo đảm đủ replica phục vụ.
8. Sau mỗi batch, xác minh version package, kernel, agent và đăng ký load balancer.
9. Cuối đợt, đối soát 30 VM, xử lý máy thất bại và cập nhật báo cáo compliance.
10. Giữ image cũ và phương án rollback trong thời hạn đã định; sau đó thu hồi image hết hạn theo chính sách.

Vì API stateless, nhóm có thể thay máy theo rolling replacement. Nếu đây là database, cần thêm kế hoạch replication, quorum, backup và thứ tự patch riêng.

## 15. Những sai lầm thường gặp

**Dùng một baseline cho mọi vai trò.** Database, bastion và web server có yêu cầu khác nhau. Cần baseline nền tảng kết hợp profile theo vai trò.

**Tạo image một lần rồi dùng mãi.** Golden image cũng lỗi thời. Cần version, ngày tạo, lịch rebuild và kiểm tra image đang được dùng.

**Cài patch trực tiếp trên từng máy mà không ghi nhận.** Fleet sẽ lệch trạng thái và khó tái tạo. Nên dùng pipeline hoặc patch manager có báo cáo.

**Tắt dịch vụ hoặc harden theo checklist mà không kiểm thử.** Có thể làm hỏng ứng dụng, agent hoặc truy cập quản trị. Test theo vai trò và có phương án phục hồi.

**Coi package đã cập nhật là kernel đã cập nhật.** Kernel mới có thể chưa được sử dụng cho tới khi reboot, trừ trường hợp live patch được hỗ trợ và xác minh.

**Patch toàn bộ fleet cùng lúc.** Sự cố từ bản vá có thể ảnh hưởng mọi replica. Dùng ring, canary và capacity dự phòng.

**Chỉ dựa vào CVSS.** Mức ưu tiên còn phụ thuộc exploit thực tế, exposure, vai trò máy và dữ liệu được bảo vệ.

**Quên patch container base image và dependency.** Host được vá nhưng image ứng dụng vẫn có thể chứa thư viện dễ bị khai thác.

**Cho rằng dịch vụ managed tự cập nhật mọi thứ.** Nhà cung cấp quản lý host theo hợp đồng dịch vụ; dependency và runtime ứng dụng vẫn có thể thuộc trách nhiệm khách hàng.

**Rollback mà không đánh giá lại bảo mật.** Phiên bản cũ có thể tái mở lỗ hổng. Cần biện pháp bù trừ và thời hạn xử lý.

**Đánh dấu thành công khi automation job kết thúc.** Cần kiểm tra version, reboot, service health và trạng thái thực tế của máy.

## 16. Checklist xây dựng baseline và quản lý bản vá

### Baseline

- [ ] Chọn hệ điều hành, phiên bản và kiến trúc còn được hỗ trợ.
- [ ] Xác định baseline nền tảng và profile theo vai trò.
- [ ] Chuẩn hóa package, service và nguồn repository.
- [ ] Quản lý tài khoản, xác thực, quyền sudo/administrator và secret.
- [ ] Cấu hình SSH/RDP và đường truy cập quản trị an toàn.
- [ ] Xác định firewall, network, DNS và đồng bộ thời gian.
- [ ] Bật logging, audit, monitoring, backup và agent bảo mật.
- [ ] Quy định mã hóa, quyền file và retention dữ liệu.
- [ ] Tham khảo benchmark phù hợp và ghi nhận ngoại lệ có thời hạn.
- [ ] Lưu cấu hình trong version control và kiểm tra drift.

### Golden image và tự động hóa

- [ ] Dùng base image từ nguồn tin cậy.
- [ ] Cài patch và package theo phiên bản được phê duyệt.
- [ ] Áp dụng hardening và kiểm thử theo vai trò.
- [ ] Quét lỗ hổng, kiểm tra artifact và lưu metadata/SBOM.
- [ ] Không nhúng credential hoặc dữ liệu riêng vào image.
- [ ] Version hóa image và cập nhật launch template/IaC.
- [ ] Có quy trình thay thế instance cũ bằng image mới.

### Patch management

- [ ] Có inventory đầy đủ và owner cho từng máy.
- [ ] Theo dõi advisory, CVE, exploit và mức exposure.
- [ ] Xác định SLA theo rủi ro và mức quan trọng.
- [ ] Kiểm thử patch trên staging hoặc nhóm đại diện.
- [ ] Lập maintenance window, capacity và thứ tự rollout.
- [ ] Dùng canary/ring và ngưỡng dừng.
- [ ] Xác minh yêu cầu reboot hoặc live patch.
- [ ] Kiểm tra service, agent, health check và hiệu năng sau patch.
- [ ] Có backup, image cũ hoặc phương án khôi phục đã thử.
- [ ] Đối soát máy thành công, thất bại và ngoại lệ.
- [ ] Báo cáo compliance và thời gian xử lý theo mức rủi ro.

## 17. Ghi nhớ

- **Baseline** xác định cấu hình chuẩn đã được phê duyệt cho một hệ điều hành hoặc vai trò workload.
- **Hardening** giảm bề mặt tấn công bằng cách giới hạn package, dịch vụ, quyền và luồng mạng.
- **Golden image** đóng gói trạng thái ban đầu; baseline còn được duy trì bằng configuration management và policy.
- **Configuration drift** là chênh lệch giữa trạng thái thực tế và trạng thái mong muốn; cần phát hiện và xử lý có kiểm soát.
- **Patch management** gồm inventory, đánh giá, kiểm thử, rollout, reboot, xác minh và báo cáo.
- Ưu tiên bản vá dựa trên mức nghiêm trọng, exploit, exposure và vai trò tài sản.
- Triển khai theo ring/canary giúp giới hạn ảnh hưởng khi bản vá gây lỗi.
- Kernel patch có thể yêu cầu reboot; live patch chỉ áp dụng cho phần được nhà cung cấp hỗ trợ.
- Container cần rebuild và redeploy image; host và node vẫn có chu kỳ patch riêng.
- Rollback phải xét cả khả năng phục hồi và rủi ro bảo mật khi quay về phiên bản cũ.
- Compliance cần dựa trên trạng thái máy thực tế, không chỉ exit code của automation.

## Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Configuration baseline | Tập hợp cấu hình chuẩn được phê duyệt cho hệ thống hoặc vai trò máy chủ. |
| Hardening | Giảm bề mặt tấn công bằng cách cấu hình hệ điều hành và dịch vụ an toàn hơn. |
| Patch management | Quy trình đánh giá, kiểm thử, triển khai và xác minh bản cập nhật. |
| Golden image | Image máy chủ đã được chuẩn hóa và phê duyệt để tạo VM. |
| Configuration drift | Sự khác biệt giữa trạng thái thực tế và baseline mong muốn. |
| CVE | Common Vulnerabilities and Exposures, mã định danh công khai cho lỗ hổng. |
| CVSS | Common Vulnerability Scoring System, hệ thống chấm điểm mức độ nghiêm trọng lỗ hổng. |
| KEV | Known Exploited Vulnerabilities, danh mục lỗ hổng đã được ghi nhận bị khai thác. |
| CIS Benchmark | Bộ khuyến nghị cấu hình an toàn theo nền tảng và phiên bản. |
| SBOM | Software Bill of Materials, danh mục thành phần phần mềm trong artifact. |
| Maintenance window | Khoảng thời gian được phê duyệt để thực hiện bảo trì. |
| Canary deployment | Triển khai thay đổi lên một nhóm nhỏ trước khi mở rộng. |
| Rolling update | Cập nhật lần lượt từng nhóm instance hoặc node để duy trì dịch vụ. |
| Live kernel patching | Áp dụng một số bản vá kernel đang chạy mà không reboot ngay. |
| Immutable infrastructure | Mô hình thay thế máy bằng artifact mới thay vì chỉnh sửa lâu dài tại chỗ. |
| Compliance | Mức độ đáp ứng baseline, chính sách và yêu cầu kiểm soát. |
| Reboot pending | Trạng thái đã cài bản cập nhật nhưng cần khởi động lại để hoàn tất áp dụng. |

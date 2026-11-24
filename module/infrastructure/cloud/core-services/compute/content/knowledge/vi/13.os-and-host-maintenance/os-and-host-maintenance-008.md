# Xác minh sức khỏe và phục hồi sau đợt cập nhật lỗi

Cập nhật hệ điều hành, kernel, driver hoặc thư viện nền giúp máy chủ nhận bản vá bảo mật và cải thiện độ ổn định. Tuy nhiên, một gói cài đặt kết thúc với mã thoát thành công chưa chứng minh máy chủ vẫn khỏe mạnh. Dịch vụ có thể không khởi động lại, kernel mới có thể không tương thích với driver, phân vùng có thể đầy, kết nối mạng có thể thay đổi hoặc ứng dụng có thể phát sinh lỗi chỉ xuất hiện dưới tải thực tế.

Trong môi trường điện toán đám mây, một máy chủ lỗi còn có thể ảnh hưởng tới nhóm autoscaling, cụm container, cân bằng tải và các dịch vụ phụ thuộc. Vì vậy, cần kiểm tra theo nhiều lớp, so sánh với trạng thái trước cập nhật, dừng rollout khi có dấu hiệu bất thường và chuẩn bị phương án phục hồi đã được kiểm thử.

Bài học này trình bày cách xác minh sức khỏe máy chủ sau cập nhật và cách chọn biện pháp phục hồi phù hợp. Sau bài học, bạn có thể:

- Lập baseline và xác định các chỉ số cần kiểm tra trước/sau cập nhật.
- Kiểm tra trạng thái cloud instance, hệ điều hành, kernel, dịch vụ, mạng, lưu trữ và ứng dụng.
- Phân biệt lỗi cài gói, lỗi khởi động, lỗi driver và lỗi chỉ xuất hiện dưới tải.
- Quyết định tiếp tục, tạm dừng, rollback hoặc thay thế máy.
- Phục hồi bằng kernel cũ, gói phần mềm, snapshot, backup hoặc image đã biết là tốt.
- Ghi nhận kết quả, xác minh sau phục hồi và đưa máy trở lại phục vụ an toàn.

## 1. Vì sao cần xác minh sau cập nhật?

Một đợt cập nhật có thể thay đổi nhiều thành phần liên quan:

- Kernel và module kernel, ảnh hưởng driver mạng, lưu trữ, GPU và thiết bị ảo.
- Thư viện hệ thống như glibc, OpenSSL hoặc runtime mà ứng dụng sử dụng.
- Dịch vụ nền, cấu hình systemd, agent giám sát, agent bảo mật và bộ quản lý cấu hình.
- Firmware hoặc driver được cung cấp thông qua image hay gói của nhà cung cấp.
- Thành phần khởi động như initramfs, bootloader và cấu hình mount.

Các lỗi có thể xuất hiện ngay khi cài đặt, trong lần reboot tiếp theo hoặc chỉ khi ứng dụng nhận lưu lượng. Ví dụ, dịch vụ vẫn ở trạng thái active nhưng không mở đúng cổng; máy vẫn ping được nhưng DNS không phân giải; filesystem chỉ đọc sau lỗi I/O; hoặc driver GPU mới khiến tiến trình suy luận không khởi tạo được.

Do đó, cần phân biệt ba trạng thái:

1. **Cài đặt hoàn tất:** trình quản lý gói và công cụ cập nhật không báo lỗi chưa xử lý.
2. **Máy chủ khỏe mạnh:** máy khởi động ổn định, tài nguyên và dịch vụ nền hoạt động đúng.
3. **Workload khỏe mạnh:** ứng dụng đáp ứng kiểm tra chức năng, SLO và tải đại diện.

Chỉ trạng thái thứ ba mới cho phép kết luận máy đã sẵn sàng quay lại phục vụ đầy đủ.

## 2. Chuẩn bị baseline trước khi cập nhật

Baseline là tập thông tin mô tả trạng thái bình thường trước thay đổi. Không có baseline, đội vận hành khó phân biệt lỗi mới phát sinh với vấn đề đã tồn tại.

Trước khi cập nhật, nên ghi lại:

- Phiên bản hệ điều hành, kernel, gói quan trọng, driver và runtime.
- Thời gian hoạt động, trạng thái reboot cần thiết, dịch vụ đang chạy và dịch vụ đang lỗi.
- CPU, bộ nhớ, swap, dung lượng filesystem, inode và tình trạng I/O.
- Địa chỉ IP, route, DNS, firewall, security group và cổng dịch vụ đang lắng nghe.
- Log lỗi gần nhất, cảnh báo giám sát, tỷ lệ lỗi, độ trễ và thông lượng ứng dụng.
- Trạng thái cụm, load balancer, replica, hàng đợi và các dependency.
- Snapshot hoặc backup gần nhất, thời gian phục hồi dự kiến và người chịu trách nhiệm.

Một số lệnh Linux hữu ích:

~~~bash
date -Is
hostnamectl
uname -a
uptime
systemctl --failed
df -h
df -i
free -h
ip addr
ip route
ss -lntup
~~~

Để lưu thông tin vào thư mục ghi nhận của một lần bảo trì, có thể chạy các lệnh và đưa kết quả vào hệ thống quản lý thay đổi hoặc kho log được kiểm soát. Không nên chỉ lưu baseline trên chính ổ đĩa có thể bị lỗi hoặc bị thay thế.

### Xác định phạm vi và mức độ ảnh hưởng

Trước khi bắt đầu, hãy biết máy thuộc nhóm nào và vai trò của nó:

- Máy độc lập hay một node trong cụm?
- Máy có nhận traffic trực tiếp hay thông qua load balancer?
- Có stateful data, volume cục bộ hoặc hàng đợi chưa xử lý không?
- Có node dự phòng và đủ capacity để chịu tải khi rút máy khỏi cụm không?
- Có phụ thuộc vào kernel module, GPU, storage driver hoặc agent đặc thù không?

Với dịch vụ quan trọng, nên thử cập nhật trên môi trường staging hoặc một nhóm canary trước. Rollout theo từng đợt nhỏ giúp phát hiện lỗi trước khi toàn bộ fleet cùng bị ảnh hưởng.

## 3. Quy trình xác minh sức khỏe theo từng lớp

Nên kiểm tra từ lớp hạ tầng tới ứng dụng. Một lớp hoạt động không bảo đảm lớp phía trên cũng khỏe mạnh.

### Lớp 1: Hạ tầng và trạng thái instance

Trong console hoặc API của nhà cung cấp đám mây, xác minh:

- Instance đang ở trạng thái running và không có sự kiện host maintenance hoặc lỗi phần cứng ảo.
- System status check và instance status check đều đạt nếu nền tảng cung cấp hai loại kiểm tra này.
- Boot volume và data volume đã attach đúng, không có cảnh báo dung lượng hoặc lỗi I/O.
- Network interface, địa chỉ IP, route và security group vẫn đúng.
- Load balancer hoặc health check của nền tảng nhận diện instance theo trạng thái dự kiến.

Nếu console báo instance running nhưng không thể kết nối, hãy kiểm tra cả serial console, boot diagnostics hoặc rescue console mà nhà cung cấp hỗ trợ. Trạng thái running chỉ cho biết máy ảo đã được cấp phát và bật; nó không chứng minh hệ điều hành đã boot xong.

### Lớp 2: Hệ điều hành và kernel

Kiểm tra kernel đang chạy, thời gian boot, lỗi kernel và trạng thái reboot:

~~~bash
uname -r
uptime -s
who -b
sudo journalctl -b -p err
sudo dmesg --level=err,warn
~~~

So sánh kernel đang chạy với kernel dự kiến sau cập nhật. Nếu gói kernel mới đã cài nhưng máy chưa reboot, **uname -r** vẫn hiển thị kernel cũ. Nếu đã reboot nhưng máy rơi về kernel cũ, cần kiểm tra bootloader, initramfs, cấu hình GRUB và log khởi động.

Trên Ubuntu/Debian, file sau có thể cho biết hệ thống yêu cầu reboot:

~~~bash
test -f /var/run/reboot-required && cat /var/run/reboot-required
~~~

Trên một số hệ thống dựa trên RHEL, công cụ thuộc gói dnf-utils hoặc dnf-plugins-core có thể cung cấp kiểm tra package/process cần restart, ví dụ:

~~~bash
sudo needs-restarting -r
~~~

Lệnh và gói hỗ trợ phụ thuộc phiên bản phân phối. Hãy kiểm tra tài liệu của hệ điều hành đang dùng.

### Lớp 3: Dịch vụ và tiến trình

Liệt kê các unit lỗi và kiểm tra những dịch vụ quan trọng:

~~~bash
systemctl --failed
systemctl status sshd
systemctl status orders-api
journalctl -u orders-api -b --no-pager -n 200
~~~

Tên service có thể là **ssh** thay vì **sshd** tùy bản phân phối. Với mỗi dịch vụ, xác minh:

- Unit có active và ổn định hay liên tục restart?
- Process có đúng phiên bản và tham số khởi chạy không?
- Socket có lắng nghe đúng địa chỉ và cổng không?
- File cấu hình có được đọc thành công và quyền truy cập còn đúng không?
- Dependency như database, DNS, message broker và secret manager có kết nối được không?

Trạng thái **active (running)** chỉ là một tín hiệu. Cần kết hợp log, socket và kiểm tra chức năng của dịch vụ.

### Lớp 4: CPU, bộ nhớ và lưu trữ

Sau cập nhật, một tiến trình có thể rò rỉ bộ nhớ, CPU tăng cao hoặc filesystem đầy do log, cache hay file tạm. Kiểm tra:

~~~bash
free -h
vmstat 1 5
df -h
df -i
lsblk
findmnt
sudo journalctl -k -b | grep -Ei 'oom|I/O error|read-only|filesystem|nvme|scsi'
~~~

Các dấu hiệu cần chú ý:

- Bộ nhớ khả dụng giảm mạnh hoặc hệ thống liên tục dùng swap.
- OOM killer kết thúc tiến trình quan trọng.
- Filesystem hoặc inode gần đầy.
- Filesystem bị mount read-only ngoài dự kiến.
- Kernel ghi nhận lỗi I/O, timeout hoặc reset thiết bị.
- Độ trễ đọc/ghi tăng rõ rệt so với baseline.

Không nên chỉ nhìn phần trăm CPU hoặc RAM. Một máy có CPU thấp nhưng bị nghẽn I/O hoặc chờ network vẫn có thể làm ứng dụng chậm.

### Lớp 5: Mạng và phân giải tên

Kiểm tra địa chỉ, route, DNS và cổng lắng nghe:

~~~bash
ip addr
ip route
getent hosts database.internal
resolvectl status
ss -lntup
~~~

**resolvectl** không có trên mọi bản phân phối; có thể kiểm tra resolver trong **/etc/resolv.conf** hoặc công cụ tương ứng. Từ máy cần kiểm tra, thử kết nối tới dependency bằng đúng giao thức và cổng. Ví dụ:

~~~bash
curl -fsS --max-time 5 http://127.0.0.1:8080/health
nc -vz database.internal 5432
~~~

Không kết luận mạng tốt chỉ vì ping thành công. ICMP có thể bị chặn hoặc được cho phép trong khi TCP, TLS, DNS hay route tới dịch vụ thật gặp lỗi.

### Lớp 6: Ứng dụng và dependency

Kiểm tra health endpoint, smoke test và một số giao dịch đại diện. Nên xác minh:

- Ứng dụng trả mã trạng thái đúng và phản hồi trong giới hạn thời gian.
- Đăng nhập, truy vấn hoặc thao tác nghiệp vụ quan trọng vẫn hoạt động.
- Kết nối database, cache, queue, object storage và dịch vụ ngoài còn thành công.
- Không có lỗi tăng bất thường trong log hoặc trace.
- Phiên bản runtime, thư viện native và driver mà ứng dụng nạp đúng như dự kiến.

Với ứng dụng có nhiều replica, hãy kiểm tra từng instance và cả kết quả tổng thể qua load balancer. Một endpoint chung có thể trả thành công nhờ các node khỏe mạnh khác dù một node vừa cập nhật đang lỗi.

### Lớp 7: Bảo mật và agent quản trị

Xác minh agent giám sát, endpoint protection, log forwarding, backup agent và công cụ quản lý cấu hình vẫn hoạt động. Kiểm tra:

- Agent đã kết nối lại control plane và gửi heartbeat.
- Chính sách firewall, SELinux/AppArmor và quyền file không bị thay đổi ngoài dự kiến.
- Audit log tiếp tục được ghi và chuyển tới nơi lưu trữ.
- Không có tài khoản, SSH key, service hoặc cổng mới xuất hiện ngoài kế hoạch.
- Bản vá bảo mật dự kiến đã được cài và phiên bản đang chạy đúng.

## 4. Đánh giá chỉ số trước và sau cập nhật

Một lần kiểm tra tại một thời điểm có thể bỏ sót vấn đề. Hãy quan sát máy trong một khoảng thời gian phù hợp với chu kỳ tải của workload.

| Nhóm chỉ số | Điều cần so sánh | Dấu hiệu bất thường |
|---|---|---|
| Availability | Tỷ lệ health check thành công, số instance ready | Node liên tục bị loại khỏi pool |
| Error rate | HTTP 5xx, lỗi ứng dụng, lỗi kết nối | Tăng so với baseline hoặc SLO |
| Latency | p50, p95, p99 | Độ trễ tăng dù thông lượng không đổi |
| Saturation | CPU, memory, swap, I/O, network | Tài nguyên chạm ngưỡng hoặc hàng đợi tăng |
| Stability | Restart count, kernel error, OOM | Process restart hoặc kernel warning lặp lại |
| Dependencies | DB pool, DNS, queue lag, storage error | Timeout hoặc retry tăng |
| Security telemetry | Agent heartbeat, audit events, policy state | Mất log hoặc agent không còn báo cáo |

Không dùng một ngưỡng chung cho mọi máy. Ngưỡng cần dựa trên SLO, đặc điểm tải và baseline. Ví dụ, CPU 85% có thể bình thường với batch worker nhưng nguy hiểm với dịch vụ tương tác vốn đã có độ trễ cao.

Một quy tắc quyết định đơn giản:

- **Tiếp tục rollout:** tất cả kiểm tra quan trọng đạt, chỉ số nằm trong SLO và không có xu hướng xấu.
- **Tạm dừng rollout:** một kiểm tra chưa rõ, chỉ số xấu đi hoặc có lỗi mới nhưng chưa xác định phạm vi.
- **Rollback hoặc thay máy:** lỗi ảnh hưởng dịch vụ, có dấu hiệu mất dữ liệu, boot thất bại hoặc không thể khôi phục trong thời gian cho phép.

## 5. Xác minh trình quản lý gói sau cập nhật

Trình quản lý gói có thể báo lỗi một phần, dependency chưa được cấu hình hoặc giao dịch cài đặt bị gián đoạn. Cần kiểm tra theo hệ điều hành.

### Ubuntu và Debian

~~~bash
sudo dpkg --audit
sudo apt-get check
sudo apt list --upgradable
~~~

**dpkg --audit** giúp phát hiện package ở trạng thái cài đặt chưa hoàn chỉnh; **apt-get check** kiểm tra dependency. Nếu có package cấu hình dở dang, hãy đọc log và xác định nguyên nhân trước khi chạy lệnh sửa chữa. Không chạy tự động các lệnh sửa dependency trên toàn bộ fleet khi chưa thử nghiệm.

Log thường nằm trong:

~~~text
/var/log/apt/history.log
/var/log/apt/term.log
/var/log/dpkg.log
~~~

### RHEL, Rocky Linux, AlmaLinux và Fedora

~~~bash
sudo dnf check
sudo dnf history
sudo rpm -qa --last | head -n 20
~~~

Có thể xem chi tiết một giao dịch:

~~~bash
sudo dnf history info <transaction-id>
~~~

DNF history có thể hỗ trợ undo hoặc rollback một số giao dịch, nhưng không phải mọi thay đổi đều có thể đảo ngược an toàn. Gói đã bị xóa khỏi repository, scriptlet có side effect, dữ liệu đã được chuyển đổi hoặc thay đổi ngoài trình quản lý gói có thể khiến thao tác undo không đầy đủ. Cần đọc giao dịch, xác định dependency và thử trên môi trường tương tự trước khi áp dụng.

## 6. Phục hồi khi cập nhật gây lỗi

Chọn phương án theo lớp bị lỗi và mức độ ảnh hưởng. Không có một lệnh rollback phù hợp cho mọi trường hợp.

### Trường hợp A: Máy vẫn boot, lỗi ở một dịch vụ

1. Giữ máy ngoài load balancer hoặc giảm traffic tới máy.
2. Kiểm tra log của service, dependency và cấu hình.
3. Xác định package hoặc thay đổi vừa gây lỗi.
4. Khôi phục cấu hình hoặc phiên bản package đã biết là tốt theo quy trình của hệ điều hành.
5. Restart đúng service và chạy smoke test.
6. Chỉ đưa máy trở lại pool khi readiness và chỉ số đều đạt.

Nếu lỗi do cấu hình, ưu tiên khôi phục bản cấu hình có version control hoặc backup. Nếu lỗi do package, kiểm tra phiên bản trước đó còn trong repository hoặc cache và dependency có tương thích không. Tránh downgrade thư viện nền tùy tiện vì có thể làm hỏng các package khác.

### Trường hợp B: Kernel mới không boot hoặc driver không hoạt động

Nhiều bản phân phối giữ lại kernel cũ trong bootloader. Nếu kernel mới không khởi động hoặc module quan trọng không nạp được:

1. Dùng serial console hoặc boot diagnostics để xem lỗi.
2. Nếu có thể, chọn kernel cũ đã biết là tốt từ menu bootloader.
3. Xác minh máy hoạt động trên kernel cũ, driver và filesystem ổn định.
4. Thu thập log và giữ lại kernel mới để điều tra; không xóa vội kernel cũ.
5. Tạo image hoặc cập nhật khác đã kiểm thử rồi mới thử lại.

Trên một số máy ảo, console hoặc boot menu không được hiển thị như máy vật lý. Cần biết trước cách truy cập rescue mode, detach boot volume hoặc khởi động từ image cứu hộ của nhà cung cấp. Nếu dùng Secure Boot, module kernel ngoài cây có thể cần ký đúng khóa.

### Trường hợp C: Máy không truy cập được sau reboot

Không nên liên tục reboot vì có thể làm mất bằng chứng hoặc khiến trạng thái xấu hơn. Thực hiện theo thứ tự:

1. Kiểm tra trạng thái instance và system checks trên cloud console.
2. Mở serial console hoặc boot log nếu có.
3. Xác định máy dừng ở bootloader, initramfs, mount filesystem hay dịch vụ mạng.
4. Nếu có thể, vào rescue mode để kiểm tra boot volume, filesystem, fstab, initramfs và log.
5. Nếu không thể sửa nhanh, khôi phục boot volume từ snapshot hoặc tạo máy thay thế từ image đã biết là tốt.
6. Attach dữ liệu bền vững theo quy trình, xác minh quyền sở hữu và tính nhất quán trước khi mở traffic.

Trước khi detach hoặc attach volume, cần tuân thủ quy trình của nền tảng và bảo đảm filesystem không còn được mount ghi ở máy cũ. Với filesystem hoặc database có trạng thái đang ghi, cần quy trình shutdown hoặc snapshot nhất quán.

### Trường hợp D: Máy khỏe nhưng ứng dụng suy giảm

Nếu OS và dịch vụ nền đều ổn nhưng ứng dụng có lỗi, hãy kiểm tra tương thích runtime, native library, TLS, database driver, agent sidecar và dependency từ xa. Có thể rollback riêng artifact ứng dụng nếu thay đổi OS không phải nguyên nhân. Nếu nhiều node cùng lỗi sau cập nhật thư viện chung, dừng rollout và cân nhắc thay nhóm máy từ image trước cập nhật.

## 7. Các phương án phục hồi và giới hạn

| Phương án | Dùng khi | Ưu điểm | Giới hạn/rủi ro |
|---|---|---|---|
| Restart service | Tiến trình lỗi nhưng OS khỏe | Nhanh, ít thay đổi | Không sửa được lỗi cấu hình hoặc dependency |
| Khôi phục cấu hình | File cấu hình bị thay đổi sai | Có thể hoàn tác chính xác nếu có bản chuẩn | Cần biết cấu hình nào thay đổi và kiểm tra secret |
| Downgrade package | Gói mới gây lỗi và phiên bản cũ còn khả dụng | Phạm vi thay đổi có thể nhỏ | Dependency và script cài đặt có thể không đảo ngược |
| Boot kernel cũ | Kernel mới hoặc module mới lỗi | Có thể khôi phục khả năng boot nhanh | Không giải quyết lỗi ở user space; kernel cũ có thể thiếu bản vá |
| Snapshot/restore volume | Boot volume hoặc filesystem hỏng | Khôi phục trạng thái volume tại thời điểm snapshot | Có thể mất dữ liệu phát sinh sau snapshot; tính nhất quán cần được xác minh |
| Backup/restore dữ liệu | Dữ liệu bị mất hoặc hỏng | Có thể khôi phục dữ liệu theo điểm thời gian | RTO/RPO phụ thuộc backup và quy trình restore |
| Replace instance từ image tốt | Máy không boot hoặc drift nghiêm trọng | Tái tạo nhanh, trạng thái dễ kiểm soát | Cần capacity, dữ liệu ngoài máy và cấu hình được quản lý |
| Rebuild fleet theo rolling | Lỗi ảnh hưởng nhiều node | Đưa toàn nhóm về trạng thái chuẩn | Cần điều phối, giám sát và capacity dự phòng |

### Snapshot không thay thế backup

Snapshot của boot volume có thể giúp quay lại trạng thái trước cập nhật, nhưng không nhất thiết là bản backup đầy đủ. Snapshot có thể chỉ phản ánh một thời điểm crash-consistent; ứng dụng đang ghi dữ liệu có thể cần freeze filesystem hoặc cơ chế quiesce để có snapshot nhất quán. Snapshot cùng vùng hoặc cùng tài khoản cũng có thể không bảo vệ trước sự cố diện rộng hay xóa nhầm.

Với database và dữ liệu nghiệp vụ, hãy dùng backup theo chính sách, kiểm tra khả năng restore và xác định RPO (mức mất dữ liệu tối đa chấp nhận được) cùng RTO (thời gian phục hồi mục tiêu). Snapshot và backup cần có retention, quyền truy cập và bản sao ở phạm vi lỗi độc lập khi yêu cầu dịch vụ đòi hỏi.

## 8. Quy trình phục hồi có kiểm soát

Một quy trình chuẩn có thể chia thành các giai đoạn:

~~~mermaid
flowchart TD
    A["Phát hiện lỗi sau cập nhật"] --> B["Cô lập node khỏi traffic"]
    B --> C["Thu thập log, trạng thái và phạm vi ảnh hưởng"]
    C --> D{"Máy còn boot và truy cập được?"}
    D -- "Có" --> E["Kiểm tra OS, package, service, network và app"]
    D -- "Không" --> F["Console / rescue mode / boot volume"]
    E --> G{"Có thể sửa an toàn trong RTO?"}
    F --> H{"Có thể phục hồi boot hoặc volume?"}
    G -- "Có" --> I["Sửa cấu hình, service hoặc rollback package/kernel"]
    G -- "Không" --> J["Replace từ image tốt và attach dữ liệu"]
    H -- "Có" --> I
    H -- "Không" --> J
    I --> K["Chạy health check và smoke test"]
    J --> K
    K --> L{"Đạt SLO và dữ liệu nhất quán?"}
    L -- "Không" --> M["Giữ cô lập, tiếp tục phục hồi/escalate"]
    L -- "Có" --> N["Đưa node trở lại pool có kiểm soát"]
    N --> O["Theo dõi sau phục hồi và ghi nhận"]
~~~

Các bước nên được thực hiện theo thứ tự:

1. **Cô lập:** đánh dấu node unhealthy, dừng nhận traffic mới và bảo vệ dữ liệu.
2. **Đánh giá:** xác định thời điểm lỗi, thay đổi vừa triển khai, số node bị ảnh hưởng và phạm vi dịch vụ.
3. **Bảo toàn bằng chứng:** lưu log, console output, package transaction, kernel version và metrics.
4. **Chọn phương án:** sửa tại chỗ, boot kernel cũ, restore volume, restore dữ liệu hoặc replace instance.
5. **Xác minh:** chạy lại các kiểm tra ở mọi lớp và smoke test nghiệp vụ.
6. **Đưa trở lại phục vụ:** chỉ tăng traffic khi node đạt điều kiện; bắt đầu với một phần nhỏ nếu phù hợp.
7. **Theo dõi:** quan sát trong cửa sổ đủ dài, kiểm tra lỗi tái diễn và ghi nhận kết quả.

## 9. Cập nhật theo canary và rolling để giảm phạm vi lỗi

Với fleet nhiều máy, không nên cập nhật tất cả node cùng lúc nếu workload yêu cầu tính sẵn sàng. Một cách tiếp cận phổ biến:

1. Cập nhật một máy thử nghiệm hoặc nhóm canary đại diện.
2. Chờ reboot nếu cần, xác minh đầy đủ OS và workload.
3. Theo dõi qua một chu kỳ tải đại diện.
4. Nếu đạt tiêu chí, cập nhật một batch nhỏ tiếp theo.
5. Duy trì đủ số node ready và capacity để chịu tải.
6. Dừng ngay rollout nếu xuất hiện lỗi mới, latency tăng hoặc health check thất bại.

Ví dụ, cụm có 10 node và cần tối thiểu 8 node khỏe mạnh. Không nên đưa 3 node ra bảo trì cùng lúc nếu chưa có capacity thay thế. Có thể cập nhật từng node hoặc từng cặp, chờ node mới ready trước khi tiếp tục. Số node mỗi batch phải dựa trên tải thực, khả năng autoscaling và thời gian khởi động.

Với Kubernetes, việc drain node cần xem xét PodDisruptionBudget, workload có local storage, daemonset và thời gian graceful termination. Lệnh drain có thể di chuyển workload nhưng không tự bảo đảm ứng dụng có đủ capacity hoặc dữ liệu cục bộ đã được bảo vệ. Với VM scale set hoặc autoscaling group, có thể thay instance theo cơ chế instance refresh nếu image mới đã được kiểm thử.

## 10. Ví dụ thực tế: cập nhật kernel làm API không khởi động

Giả sử một nhóm chạy API đặt hàng trên 6 VM sau load balancer. Sau khi cập nhật kernel và reboot một VM, health check thất bại. Các VM còn lại vẫn hoạt động.

**Bước 1: Cô lập node lỗi.** Load balancer đánh dấu VM không healthy; nhóm xác nhận 5 VM còn lại đủ năng lực phục vụ và tạm dừng batch rollout.

**Bước 2: Kiểm tra hạ tầng.** Console cho thấy VM đang running nhưng instance status check không đạt. Nhóm mở serial console và thấy boot dừng sau khi nạp initramfs.

**Bước 3: Kiểm tra kernel.** Log cho thấy module storage driver không được nạp đúng với kernel mới. Nhóm không tiếp tục reboot lặp lại; họ dùng boot menu hoặc rescue console để chọn kernel trước đó.

**Bước 4: Xác minh trên kernel cũ.** VM boot thành công, volume được mount đúng, filesystem không ở chế độ read-only. Nhóm kiểm tra dịch vụ, cổng 8080, kết nối database và health endpoint.

**Bước 5: Đưa node trở lại.** Sau smoke test và một khoảng quan sát, VM được đưa vào load balancer với lưu lượng giới hạn rồi trở lại pool nếu các chỉ số đạt.

**Bước 6: Điều tra và sửa image.** Nhóm lưu log, package transaction và phiên bản kernel; xác định driver tương thích, thử trên staging rồi tạo image mới. Các VM còn lại chỉ được cập nhật sau khi canary mới vượt qua kiểm tra.

Ví dụ này cho thấy cần kiểm tra cả khả năng boot, driver, volume và ứng dụng. Trạng thái instance running hoặc lệnh cài đặt thành công không đủ để kết luận bản cập nhật an toàn.

## 11. Runbook và thông tin cần ghi nhận

Mỗi lần phục hồi nên tạo một bản ghi có thể kiểm tra lại:

| Trường thông tin | Nội dung cần ghi |
|---|---|
| Incident/change ID | Mã sự cố hoặc thay đổi liên quan |
| Host/instance | Tên máy, instance ID, vùng và vai trò |
| Thời điểm | Bắt đầu cập nhật, reboot, phát hiện lỗi, phục hồi và hoàn tất |
| Phiên bản | OS, kernel, package, driver và image trước/sau |
| Triệu chứng | Health check, log, lỗi người dùng và chỉ số bất thường |
| Phạm vi ảnh hưởng | Số node, dịch vụ, người dùng và dữ liệu bị ảnh hưởng |
| Hành động | Cô lập, rollback, restore, replace và người thực hiện |
| Kết quả kiểm tra | OS, service, network, application, security telemetry |
| Dữ liệu | Snapshot/backup được dùng, thời điểm và kết quả xác minh |
| Quyết định | Tiếp tục rollout, dừng, rollback hoặc đóng sự cố |

Không ghi private key, mật khẩu, token hoặc dữ liệu nhạy cảm vào runbook. Khi cần lưu log để điều tra, kiểm soát quyền đọc, thời hạn lưu và nơi lưu độc lập với máy lỗi.

Sau sự cố, tổ chức nên thực hiện post-incident review: xác định nguyên nhân gốc, vì sao canary hoặc kiểm tra trước phát hành không phát hiện được, thời gian phát hiện/phục hồi và hành động ngăn tái diễn. Cập nhật runbook, tiêu chí health check, image build hoặc quy trình rollout dựa trên kết quả.

## 12. Những sai lầm thường gặp

1. **Chỉ kiểm tra mã thoát của trình quản lý gói:** gói cài xong nhưng dịch vụ hoặc driver vẫn có thể lỗi.
2. **Không so sánh baseline:** dễ bỏ sót latency tăng, memory leak hoặc log lỗi mới.
3. **Reboot liên tục khi máy không lên:** có thể làm mất bằng chứng và không giải quyết nguyên nhân.
4. **Downgrade hàng loạt khi chưa xác định package:** có thể gây thêm xung đột dependency.
5. **Restore snapshot mà không kiểm tra tính nhất quán:** có thể đưa dữ liệu đang ghi về trạng thái không đồng bộ.
6. **Đưa node trở lại traffic quá sớm:** lỗi có thể chỉ xuất hiện khi nhận tải thật.
7. **Cập nhật toàn fleet cùng lúc:** làm tăng blast radius và loại bỏ năng lực dự phòng.
8. **Xóa kernel cũ hoặc image tốt quá sớm:** mất đường phục hồi khi kernel mới không boot.
9. **Bỏ qua agent bảo mật và giám sát:** máy có thể phục vụ ứng dụng nhưng không còn được quan sát hoặc bảo vệ.
10. **Không ghi nhận phiên bản và hành động:** khiến việc tái hiện và khắc phục sự cố sau đó khó khăn.

## 13. Checklist sau mỗi đợt cập nhật

- [ ] Giao dịch cập nhật không còn package ở trạng thái lỗi hoặc cấu hình dở dang.
- [ ] Kernel và driver đang chạy đúng phiên bản dự kiến.
- [ ] Máy boot ổn định và cloud status checks đạt.
- [ ] Không có kernel error, OOM hoặc lỗi I/O mới chưa giải thích được.
- [ ] Filesystem, inode, memory, CPU và I/O nằm trong giới hạn bình thường.
- [ ] Route, DNS, firewall và cổng dịch vụ hoạt động đúng.
- [ ] Các systemd unit quan trọng active và không restart liên tục.
- [ ] Ứng dụng, dependency và smoke test nghiệp vụ đạt.
- [ ] Latency, error rate và throughput nằm trong SLO.
- [ ] Agent giám sát, bảo mật, backup và log forwarding gửi heartbeat.
- [ ] Snapshot/backup và phương án rollback còn khả dụng.
- [ ] Node chỉ được đưa lại vào traffic sau khi qua kiểm tra và cửa sổ quan sát.
- [ ] Kết quả, phiên bản và hành động được ghi vào change/incident record.

## 14. Bài tập vận dụng

Một cụm có 12 VM chạy dịch vụ xử lý thanh toán. Mỗi VM được cập nhật kernel và thư viện TLS trong cùng một đợt. Sau reboot, 2 VM không qua health check, 1 VM có p95 latency tăng gấp đôi, còn 9 VM khác bình thường. Cụm cần duy trì ít nhất 9 VM ready.

1. Nhóm cần thực hiện hành động đầu tiên nào để giữ dịch vụ ổn định?
2. Hãy liệt kê các lớp kiểm tra cần thực hiện trên hai VM không healthy.
3. Với VM có latency tăng, cần thu thập những chỉ số nào để phân biệt CPU, memory, I/O, network và lỗi TLS?
4. Nếu kernel mới không boot trên hai VM, hãy đề xuất đường phục hồi và các điều kiện trước khi đưa chúng trở lại pool.
5. Vì sao nhóm nên dừng rollout trên 9 VM còn lại cho tới khi hiểu rõ nguyên nhân?

Gợi ý: cô lập hai VM lỗi và đánh giá capacity còn lại trước khi làm thêm thay đổi. Kiểm tra cloud status, boot log, kernel/module, filesystem, service, network và application. Với VM latency cao, so sánh p50/p95/p99, error rate, CPU, memory, swap, I/O wait, network retransmit và log TLS với baseline. Nếu kernel mới không boot, dùng kernel cũ hoặc rescue/restore theo quy trình, xác minh đầy đủ rồi mới đưa lại vào pool. Dừng rollout để tránh mở rộng phạm vi ảnh hưởng khi nguyên nhân có thể nằm trong kernel hoặc thư viện chung.

## Kết luận

Xác minh sau cập nhật cần đi từ hạ tầng, hệ điều hành, kernel, dịch vụ, tài nguyên, mạng, ứng dụng tới agent bảo mật và giám sát. Baseline cùng SLO giúp phát hiện thay đổi bất thường; canary và rollout theo batch giới hạn phạm vi lỗi. Khi có sự cố, hãy cô lập node, bảo toàn bằng chứng, chọn đúng phương án phục hồi và chỉ đưa máy trở lại phục vụ sau khi kiểm tra sức khỏe cùng dữ liệu đều đạt. Snapshot, backup, kernel cũ và image tốt là các lớp phục hồi bổ sung, mỗi lớp có giới hạn riêng cần được kiểm thử trước.

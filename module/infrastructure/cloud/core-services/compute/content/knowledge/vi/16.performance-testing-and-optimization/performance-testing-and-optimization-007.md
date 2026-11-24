# Tối ưu cấu hình hệ điều hành và giới hạn file descriptor

Một workload có thể gặp lỗi kết nối, không mở được file, không nhận thêm request hoặc tăng độ trễ dù CPU và RAM vẫn còn dư. Một nguyên nhân thường bị bỏ sót là tiến trình đã dùng hết **file descriptor (FD)** hoặc chạm giới hạn tài nguyên của hệ điều hành. Trên Linux, socket mạng, file, pipe, thiết bị và nhiều đối tượng I/O đều được tiến trình truy cập thông qua file descriptor. Nếu giới hạn quá thấp, ứng dụng có thể trả lỗi `Too many open files`, không tạo được kết nối mới hoặc không ghi được log.

Tối ưu hệ điều hành cần bắt đầu từ số liệu của workload. Tăng giới hạn FD, thay đổi kernel parameter hay điều chỉnh hàng đợi mạng chỉ có ích khi đã xác định được nút thắt tương ứng. Một cấu hình áp dụng đồng loạt có thể làm tăng mức tiêu thụ bộ nhớ kernel, che giấu rò rỉ tài nguyên hoặc khiến hệ thống khó phục hồi khi tải tăng.

## 1. File descriptor là gì?

Trên Unix/Linux, file descriptor là một số nguyên không âm mà tiến trình dùng để tham chiếu tới một đối tượng I/O đang mở. Các FD mặc định thường gồm:

- `0`: standard input (`stdin`).
- `1`: standard output (`stdout`).
- `2`: standard error (`stderr`).

Khi ứng dụng mở file, tạo socket, pipe, event descriptor hoặc một số đối tượng kernel khác, hệ điều hành cấp một FD cho tiến trình. Ví dụ, một API server có thể dùng FD cho socket lắng nghe, mỗi kết nối client, file log, file cấu hình, kết nối database, pipe giữa tiến trình và file tạm.

FD là tham chiếu ở cấp tiến trình tới một open file description hoặc đối tượng kernel liên quan. Nhiều FD có thể tham chiếu cùng một open file description khi dùng `dup()` hoặc sau khi fork. Vì vậy, số FD không nhất thiết bằng số file vật lý duy nhất đang mở.

Đối với server xử lý nhiều kết nối đồng thời, socket thường chiếm phần đáng kể trong số FD. Nếu một request mở thêm file hoặc kết nối tới nhiều dịch vụ phụ thuộc, số FD có thể tăng theo concurrency. Một tiến trình còn nhiều CPU nhưng hết FD vẫn có thể không nhận được kết nối mới.

## 2. Phân biệt giới hạn FD theo tiến trình và toàn hệ thống

Linux có nhiều lớp giới hạn liên quan đến FD. Hai lớp cần phân biệt trước tiên là giới hạn của từng tiến trình và giới hạn file handle toàn hệ thống.

| Giới hạn | Phạm vi | Cách xem thường dùng |
|---|---|---|
| `RLIMIT_NOFILE` | Mỗi tiến trình | `ulimit -n`, `prlimit`, `/proc/PID/limits` |
| `fs.nr_open` | Trần tối đa cho số FD một tiến trình có thể cấp phát | `/proc/sys/fs/nr_open` |
| `fs.file-max` | Giới hạn file handle được cấp phát trên toàn hệ thống | `/proc/sys/fs/file-max` |
| `file-nr` | Số liệu file handle hiện tại của kernel | `/proc/sys/fs/file-nr` |

`RLIMIT_NOFILE` có hai giá trị:

- **Soft limit:** giới hạn đang được áp dụng cho tiến trình. Tiến trình có thể tự nâng soft limit đến hard limit nếu có quyền phù hợp.
- **Hard limit:** mức tối đa mà tiến trình không có quyền đặc biệt được phép nâng soft limit tới.

`fs.nr_open` đặt trần kernel cho giới hạn FD trên mỗi tiến trình. Việc đặt `RLIMIT_NOFILE` cao hơn `fs.nr_open` không tạo ra khả năng mở thêm FD. `fs.file-max` là giới hạn file handle toàn hệ thống; tăng `RLIMIT_NOFILE` của một service không tự động tăng giới hạn này.

Một tiến trình có thể chạm `RLIMIT_NOFILE` trong khi hệ thống còn nhiều file handle. Ngược lại, nhiều tiến trình có thể cùng tiêu thụ tài nguyên và làm hệ thống chạm `file-max` dù mỗi tiến trình chưa đạt giới hạn riêng.

## 3. Nhận biết lỗi cạn file descriptor

Ứng dụng có thể biểu hiện nhiều cách khi không mở được FD mới:

- Linux trả lỗi `EMFILE` (`Too many open files`) khi tiến trình chạm giới hạn FD riêng.
- Linux trả lỗi `ENFILE` khi giới hạn file handle toàn hệ thống bị chạm.
- Server không accept được socket mới hoặc không mở được kết nối tới database/cache.
- Ứng dụng không thể mở file log, file tạm hoặc file cấu hình trong lúc hoạt động.
- Log có lỗi `accept4`, `socket`, `open`, `pipe` hoặc `epoll_create` thất bại.
- Số kết nối đang mở tăng liên tục, nhưng không giảm tương ứng sau khi request kết thúc.

Không nên suy luận chỉ từ thông báo lỗi ở tầng ứng dụng. Ví dụ, `Connection refused` thường liên quan đến việc không có tiến trình lắng nghe hoặc firewall chủ động từ chối; nó không đồng nghĩa với cạn FD. Hãy đối chiếu errno, log runtime, số FD hiện tại và giới hạn thực tế.

## 4. Kiểm tra FD đang dùng của tiến trình

Trên Linux, mỗi tiến trình có thư mục `/proc/PID/fd` chứa symbolic link tới các đối tượng mà nó đang mở. Số entry trong thư mục là số FD đang được tiến trình giữ tại thời điểm kiểm tra.

Ví dụ:

```bash
# Xem gioi han cua tien trinh
cat /proc/1234/limits | grep -i 'open files'

# Dem so FD dang mo
find /proc/1234/fd -maxdepth 1 -type l | wc -l

# Liet ke cac doi tuong dang duoc mo
sudo ls -l /proc/1234/fd | head -n 40

# Xem cac loai FD va socket
sudo lsof -nP -p 1234
```

Thay `1234` bằng PID thực tế. `lsof` có thể tạo lượng output lớn với tiến trình nhiều kết nối; nên lọc theo PID hoặc loại đối tượng. Việc đọc `/proc` cũng có thể bị hạn chế bởi quyền, namespace hoặc cấu hình bảo mật.

Để xem số FD theo loại, có thể dùng:

```bash
sudo lsof -nP -p 1234 | awk 'NR>1 {count[$5]++} END {for (type in count) print type, count[type]}'
```

Lệnh trên nhóm theo trường type trong output của `lsof`; định dạng cột có thể khác theo phiên bản và locale. Với điều tra chính xác, dùng tùy chọn output dạng field của `lsof` hoặc phân tích `/proc/PID/fd` kết hợp socket table.

Để xem tiến trình nào đang dùng nhiều FD, có thể kiểm tra nhiều PID trong khoảng thời gian có kiểm soát. Không nên chỉ chụp một mẫu; hãy ghi lại count theo thời gian để phát hiện xu hướng tăng không giảm.

## 5. Kiểm tra giới hạn FD hiện tại

Trong shell:

```bash
ulimit -Sn
ulimit -Hn
ulimit -n
```

`-S` hiển thị soft limit, `-H` hiển thị hard limit. `ulimit -n` thường hiển thị soft limit của shell hiện tại. Các giá trị này chỉ phản ánh shell và tiến trình con được tạo từ shell đó; chúng không nhất thiết là giới hạn của service đã chạy dưới systemd, container runtime hoặc một session khác.

Kiểm tra trực tiếp tiến trình:

```bash
cat /proc/1234/limits
prlimit --pid 1234 --nofile
```

Đây là nguồn đáng tin hơn khi chẩn đoán một process cụ thể. Nếu `ulimit -n` trong terminal có giá trị lớn nhưng `/proc/PID/limits` của service có giá trị nhỏ, service được khởi chạy trong một context có giới hạn khác.

## 6. Kiểm tra giới hạn file handle toàn hệ thống

Kernel cung cấp các số liệu trong `/proc/sys/fs`:

```bash
cat /proc/sys/fs/file-max
cat /proc/sys/fs/file-nr
cat /proc/sys/fs/nr_open
```

- `file-max` là ngưỡng file handle toàn hệ thống.
- `file-nr` chứa số file handle đã cấp phát, số slot rảnh trong pool và giới hạn tối đa. Trên kernel Linux hiện đại, trường giữa thường bằng 0 vì file handle được cấp phát động; hãy đọc tài liệu kernel tương ứng với phiên bản đang chạy.
- `nr_open` là trần giới hạn FD tối đa cho một tiến trình.

Nếu `file-nr` tiến sát `file-max` và kernel log ghi nhận lỗi `ENFILE`, cần xem tổng số FD của các tiến trình, số socket, mount và hoạt động hệ thống. Không tăng `file-max` chỉ vì con số cao; file handle và cấu trúc kernel vẫn tiêu thụ bộ nhớ. Hãy xác định workload nào tạo ra nhu cầu và kiểm tra có leak hay không.

## 7. Ước lượng nhu cầu FD cho workload

Giới hạn FD nên được chọn từ số tài nguyên mở đồng thời ở tải đỉnh, cộng phần dự phòng hợp lý. Một API server có thể cần:

- FD cho listener và socket client đang kết nối.
- FD cho outbound connection tới database, cache, message broker và HTTP dependency.
- File log, file cấu hình, certificate và file tạm.
- Pipe, eventfd, epoll, inotify hoặc descriptor phục vụ runtime.
- FD do agent giám sát, profiler hoặc thư viện tạo thêm trong cùng process.

Có thể dùng mô hình ước lượng:

\[
FD_{peak} \approx FD_{base} + C_{in} + C_{out} + F_{runtime} + F_{temporary}
\]

Trong đó:

- `FD_base` là FD cố định khi service khởi động.
- `C_in` là số kết nối inbound đồng thời do tiến trình trực tiếp giữ.
- `C_out` là số kết nối outbound đồng thời.
- `F_runtime` là FD cho runtime, log, pipe, event loop và agent.
- `F_temporary` là nhu cầu đỉnh cho file tạm hoặc tác vụ ngắn hạn.

Đây là mô hình gần đúng. Một proxy hoặc load balancer có thể giữ nhiều socket cho mỗi request; một connection pool dùng lại socket nên số FD không tăng theo tổng request; một thư viện có thể mở nhiều file cùng lúc. Hãy đo FD thực tế ở tải đại diện rồi cộng headroom cho burst, rollout và tình huống phục hồi.

Ví dụ, service có 80 FD nền, tối đa 1.500 kết nối inbound, 250 kết nối outbound và 120 FD runtime/tạm thời. Nhu cầu ước lượng là 1.950 FD. Với headroom 50%, có thể bắt đầu kiểm thử ở mức khoảng 3.000 FD. Giá trị cuối cùng phải dựa trên đo kiểm và giới hạn nền tảng; không lấy ví dụ này làm mặc định cho mọi API.

## 8. Điều chỉnh giới hạn FD cho service systemd

Với service Linux do systemd quản lý, nên đặt giới hạn ngay trong unit thay vì chỉ thay đổi `ulimit` của terminal.

Ví dụ unit file:

```ini
[Unit]
Description=Orders API
After=network-online.target
Wants=network-online.target

[Service]
User=orders
Group=orders
ExecStart=/usr/bin/java -jar /srv/orders/orders-api.jar
Restart=on-failure
RestartSec=5s
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

`LimitNOFILE=` thiết lập `RLIMIT_NOFILE` cho tiến trình service. Giá trị `65536` chỉ là ví dụ minh họa; hãy thay bằng mức đã sizing. Sau khi sửa unit:

```bash
sudo systemctl daemon-reload
sudo systemctl restart orders-api.service
sudo systemctl show orders-api.service -p LimitNOFILE
```

Việc restart làm tiến trình được tạo lại với giới hạn mới. Xác minh trực tiếp bằng `/proc/PID/limits` của PID mới. `systemctl show` cho biết cấu hình systemd đang áp dụng, còn `/proc/PID/limits` phản ánh giới hạn của tiến trình thực tế.

Có thể cấu hình mặc định cho service manager qua `DefaultLimitNOFILE=` trong cấu hình systemd manager, nhưng thay đổi mặc định ảnh hưởng nhiều service và cần đánh giá phạm vi. Với một workload cụ thể, giới hạn riêng trong unit thường dễ kiểm soát và kiểm thử hơn.

## 9. Vai trò của PAM limits và ulimit

File `/etc/security/limits.conf` hoặc các file trong `/etc/security/limits.d/` có thể đặt giới hạn cho user/group trong các session được PAM xử lý thông qua `pam_limits`. Ví dụ:

```text
orders soft nofile 32768
orders hard nofile 65536
```

Điều này hữu ích với login session hoặc một số cách khởi chạy ứng dụng qua PAM. Tuy nhiên, service systemd hệ thống thường không lấy giới hạn từ `limits.conf` như một login shell. Không nên chỉnh file này rồi cho rằng service đã nhận giá trị mới.

`ulimit -n 65536` trong shell chỉ thay đổi giới hạn của shell và các tiến trình con được tạo sau đó, trong phạm vi hard limit cho phép. Nó không thay đổi giới hạn của process đã chạy, cũng không thay đổi giới hạn toàn hệ thống. Sau mọi thay đổi, xác minh đúng PID và đúng service.

## 10. Điều chỉnh các giới hạn kernel liên quan

Một số sysctl có liên quan tới FD hoặc năng lực mạng:

| Tham số | Vai trò | Khi nào cần xem xét |
|---|---|---|
| `fs.file-max` | Giới hạn file handle toàn hệ thống | Có bằng chứng hệ thống chạm ngưỡng và đã xác định nhu cầu hợp lệ |
| `fs.nr_open` | Trần `RLIMIT_NOFILE` cho mỗi tiến trình | Service cần hard limit cao hơn giá trị hiện tại và kernel cho phép |
| `net.core.somaxconn` | Trần backlog của socket listen | Có dấu hiệu listen queue overflow và ứng dụng có khả năng accept nhanh hơn |
| `net.ipv4.ip_local_port_range` | Dải ephemeral port nguồn cho kết nối IPv4 | Host tạo nhiều outbound connection và cạn port nguồn |
| `net.core.netdev_max_backlog` | Hàng đợi packet khi kernel nhận nhanh hơn tốc độ xử lý | Có softnet backlog drop và đã kiểm tra CPU/driver/NIC |

Không tăng mọi tham số cùng lúc. Thay đổi từng giá trị, ghi lại baseline, đo trước/sau và giữ khả năng rollback. Các giới hạn mạng có thể phụ thuộc kernel, driver, loại instance và cấu hình của nhà cung cấp cloud.

### Xem và thay đổi sysctl

Đọc giá trị hiện tại:

```bash
sysctl fs.file-max
sysctl fs.nr_open
sysctl net.core.somaxconn
sysctl net.ipv4.ip_local_port_range
```

Thay đổi tạm thời đến lần reboot hoặc khi bị ghi đè:

```bash
sudo sysctl -w fs.file-max=2097152
```

Giá trị trên chỉ minh họa, không phải khuyến nghị phổ quát. Để duy trì qua reboot, quản lý cấu hình trong file riêng dưới `/etc/sysctl.d/`, ví dụ:

```text
# /etc/sysctl.d/90-compute-workload.conf
fs.file-max = 2097152
```

Nạp cấu hình:

```bash
sudo sysctl --system
```

Trong môi trường production, thay đổi sysctl nên được quản lý bằng configuration management hoặc image pipeline, có review và kiểm thử. Không chỉnh trực tiếp nhiều tham số trên từng máy theo cách thủ công vì fleet dễ lệch cấu hình.

## 11. Tối ưu backlog và kết nối mạng

Với server TCP, có một số hàng đợi liên quan đến việc thiết lập kết nối. `net.core.somaxconn` giới hạn listen backlog mà kernel cho phép; ứng dụng cũng truyền backlog khi gọi `listen()`. Giá trị hiệu dụng phụ thuộc cả hai. Hàng đợi SYN và hàng đợi accept có vai trò khác nhau; tăng `somaxconn` không tự sửa được ứng dụng accept chậm hoặc CPU quá tải.

Khi nghi ngờ backlog:

```bash
ss -lnt
netstat -s | grep -Ei 'listen|overflow|drop'
```

Tùy hệ thống, `ss -lnt` hiển thị số kết nối đang nằm trong hàng đợi và giới hạn backlog cho socket listen. Tìm các counter listen overflow/drop trong thống kê TCP. Nếu backlog thường xuyên đầy, kiểm tra số worker, thời gian xử lý callback accept, CPU, scheduler và tải burst trước khi tăng giới hạn.

Một vấn đề khác là cạn ephemeral port khi một máy tạo rất nhiều kết nối outbound tới cùng đích. TIME_WAIT và kết nối ngắn hạn có thể làm port nguồn bị sử dụng trong thời gian nhất định. Kiểm tra:

```bash
cat /proc/sys/net/ipv4/ip_local_port_range
ss -s
ss -tan state time-wait | wc -l
```

Giải pháp thường hiệu quả là tái sử dụng kết nối thông qua connection pool/keep-alive, giảm tạo kết nối ngắn hạn, điều chỉnh concurrency và xem xét port range sau khi kiểm tra route/NAT. Không bật các tùy chọn TCP cũ hoặc giảm thời gian TIME_WAIT một cách máy móc; chúng có thể gây lỗi kết nối hoặc ảnh hưởng an toàn giao thức.

## 12. Cấu hình file descriptor trong container

Container trên Linux vẫn dùng giới hạn tiến trình/cgroup và kernel của host. `ulimit` trong container thường được runtime thiết lập khi tạo container. Tăng giới hạn bên trong shell sau khi ứng dụng đã khởi động không thay đổi giới hạn của tiến trình chính.

Với Docker, có thể cấu hình `nofile` khi tạo container, ví dụ:

```bash
docker run --ulimit nofile=65536:65536 my-orders-api:1.0
```

Đây là cú pháp minh họa; kiểm tra Docker daemon, runtime và hard limit của host trước khi dùng. Trong Docker Compose, cấu hình tương ứng có thể được khai báo ở `ulimits` tùy phiên bản Compose.

Với Kubernetes, cách cấu hình `RLIMIT_NOFILE` phụ thuộc container runtime và cấu hình node. Kubernetes API không cung cấp một trường `nofile` portable ở Pod spec như CPU/memory requests/limits. Nếu cần thay đổi, phải quản lý runtime/node hoặc image entrypoint theo cơ chế được nền tảng hỗ trợ và xác minh từ trong process. Không giả định `ulimit` ở shell debug giống với giới hạn của tiến trình PID 1 trong container.

## 13. Windows: handle không đồng nhất với Unix file descriptor

Windows dùng **handle** để tham chiếu tới file, socket, process, thread, event và nhiều đối tượng kernel khác. Khái niệm này có chức năng tương tự ở mức quản lý tài nguyên nhưng không phải cùng một cơ chế với POSIX file descriptor. Windows không có `ulimit -n` hoặc `RLIMIT_NOFILE` theo cách Linux sử dụng.

Để kiểm tra process handle count, có thể dùng PowerShell:

```powershell
Get-Process |
  Sort-Object Handles -Descending |
  Select-Object -First 20 ProcessName, Id, Handles, WorkingSet64
```

`Handles` là số handle mà process đang giữ; nó không phải số socket hoặc file đang mở riêng. Công cụ Sysinternals Handle hoặc Process Explorer có thể giúp xác định loại đối tượng mà tiến trình đang giữ. Với socket, kiểm tra `Get-NetTCPConnection`, counter mạng và log ứng dụng.

Nếu ứng dụng Windows dùng C runtime có giao diện kiểu POSIX, runtime có thể có giới hạn file stream riêng, chẳng hạn `_setmaxstdio`; giới hạn này không phải giới hạn handle toàn hệ điều hành. Chẩn đoán cần phân biệt handle leak, socket exhaustion, file sharing/locking và giới hạn của runtime.

## 14. Tìm và xử lý FD leak

FD leak xảy ra khi ứng dụng mở file/socket nhưng không đóng sau khi hoàn tất. Số FD tăng dần theo thời gian, cuối cùng chạm giới hạn. Một số nguyên nhân:

- Không đóng file hoặc stream trong nhánh lỗi/exception.
- Tạo HTTP client hoặc database connection mới cho mỗi request thay vì dùng pool.
- Socket không được đóng khi timeout hoặc request bị hủy.
- Watcher, pipe, file tạm hoặc descriptor trong thư viện native bị giữ lại.
- Thread hoặc task nền giữ tham chiếu tới resource lâu hơn dự kiến.
- Retry tạo thêm kết nối nhưng không giải phóng kết nối thất bại.

Quy trình tìm leak:

1. Theo dõi FD count theo PID trong thời gian tải ổn định.
2. Phân loại FD tăng: socket, file, pipe, event, inotify hoặc loại khác.
3. Đối chiếu với số request đồng thời, số connection pool và số file log.
4. Kiểm tra code path thành công, exception, timeout và cancellation có đóng resource không.
5. Dùng profiler, runtime diagnostic hoặc công cụ quan sát syscall trong môi trường thử nghiệm.
6. Chạy soak test sau khi sửa và xác nhận FD count ổn định khi tải tăng/giảm.

Trong Java, ưu tiên try-with-resources cho `InputStream`, `OutputStream`, `Socket`, `FileChannel` và các resource có `close()`. Dùng HTTP client và database pool được quản lý vòng đời rõ ràng. Đối với native code, kiểm tra mọi đường thoát sau `open()`, `socket()`, `accept()` hoặc `pipe()` đều gọi `close()` đúng lúc.

Tăng giới hạn có thể giúp service chịu được burst lớn hơn, nhưng nếu FD count tăng không giới hạn thì chỉ trì hoãn lần lỗi tiếp theo. Cần sửa leak trước khi xem việc tăng limit là giải pháp lâu dài.

## 15. Những cấu hình hệ điều hành khác cần tối ưu theo số liệu

Ngoài FD, một số tham số hệ điều hành có thể ảnh hưởng hiệu năng compute. Chỉ thay đổi khi metric hoặc bài tải chứng minh đúng nút thắt:

| Khu vực | Thông số/khả năng | Dấu hiệu cần điều tra | Rủi ro khi chỉnh sai |
|---|---|---|---|
| CPU/scheduler | CPU quota, affinity, cgroup CPU weight | CPU throttling, run queue dài, latency tăng | Giảm fairness hoặc giới hạn CPU không cần thiết |
| Memory | `vm.swappiness`, dirty page/writeback, cgroup memory | Swap pressure, writeback stall, memory PSI | Tăng I/O hoặc OOM nếu giảm headroom |
| File system | Mount option, inode capacity, file handle | I/O latency, inode exhaustion, metadata workload | Thay đổi durability hoặc semantics |
| Network | Backlog, ephemeral port range, queue và NIC limits | Listen overflow, port exhaustion, packet drop | Tăng memory kernel hoặc che giấu app bottleneck |
| I/O scheduler | Scheduler và queue depth theo loại block device | I/O wait và storage latency | Tăng latency ở workload khác |

Trên máy ảo cloud, một số điều khiển phần cứng hoặc scheduler nằm ngoài quyền của guest OS. Không nên cố thay đổi CPU frequency governor, interrupt affinity hoặc driver parameter nếu nền tảng không hỗ trợ hoặc nhà cung cấp khuyến cáo không chỉnh. Hãy bắt đầu từ metric mà guest có thể quan sát và giới hạn instance/service được công bố.

### Ví dụ về `vm.swappiness`

`vm.swappiness` ảnh hưởng xu hướng kernel đưa anonymous memory ra swap so với thu hồi page cache. Nó không phải tỷ lệ RAM sẽ bị swap và không có một giá trị tối ưu cho mọi ứng dụng. Với workload nhạy latency, cần quan sát swap I/O và PSI trước khi thay đổi; tắt swap hoặc đặt giá trị cực thấp có thể làm OOM xuất hiện sớm hơn.

### Ví dụ về writeback

Các tham số dirty page ảnh hưởng thời điểm kernel bắt đầu và mức độ ghi dữ liệu bẩn xuống storage. Tăng ngưỡng có thể gom nhiều ghi hơn nhưng cũng làm writeback burst lớn và tăng rủi ro khi máy mất điện nếu durability không được ứng dụng bảo đảm. Hãy dùng metric storage latency, dirty pages và writeback behavior; không điều chỉnh chỉ để tăng benchmark tuần tự.

## 16. Quy trình tuning có kiểm soát

Một quy trình tuning tốt giúp chứng minh thay đổi cải thiện workload và không làm xấu hệ thống khác:

1. **Đặt mục tiêu:** xác định SLO như request latency p95/p99, throughput, error rate và giới hạn tài nguyên.
2. **Đo baseline:** thu thập FD count, OOM/ENFILE/EMFILE, CPU, memory, I/O, network, backlog và connection metrics.
3. **Tìm bottleneck:** xác định process hoặc kernel subsystem nào đang chạm giới hạn.
4. **Ước lượng nhu cầu:** tính FD/concurrency/queue ở peak và headroom cần thiết.
5. **Thay đổi một nhóm nhỏ:** ưu tiên service-specific setting trước thay đổi toàn host.
6. **Chạy load test:** dùng cùng workload, dữ liệu và thời gian đo trước/sau.
7. **Theo dõi tác dụng phụ:** kernel memory, latency, error, socket state, log và khả năng phục hồi.
8. **Rollout từng nhóm:** canary trước, sau đó mở rộng nếu kết quả đạt.
9. **Ghi lại và rollback:** quản lý cấu hình trong mã, lưu giá trị cũ và quy trình quay lại.

Không tối ưu dựa trên một lần benchmark ngắn. Nên chạy cả tải ổn định, burst, soak test và tình huống restart/scale để phát hiện rò rỉ hoặc giới hạn chỉ xuất hiện sau thời gian dài.

## 17. Ví dụ: API server hết FD khi tải tăng

Một API server Linux chạy dưới systemd. Ở tải bình thường, process giữ khoảng 4.000 FD. Trong đợt traffic cao, log xuất hiện `accept4: Too many open files`; CPU chỉ khoảng 45%, RAM còn nhiều.

Quy trình điều tra:

1. Xác định PID service và đọc `/proc/PID/limits` để biết soft/hard `Max open files`.
2. Đếm `/proc/PID/fd` và xem FD theo loại bằng `lsof`.
3. Kiểm tra socket: số kết nối ESTABLISHED, CLOSE_WAIT, TIME_WAIT và listener backlog.
4. Đối chiếu FD count với số kết nối inbound, pool outbound và tải request.
5. Xem log ứng dụng có socket/file không được đóng hoặc retry tạo connection mới không.
6. Xác minh giới hạn systemd, `fs.nr_open` và `fs.file-max`.
7. Nếu nhu cầu hợp lệ vượt soft limit, tăng `LimitNOFILE` theo sizing và kiểm thử; nếu FD tăng không giảm, sửa leak/pooling trước.
8. Chạy lại burst và soak test, xác nhận FD count ổn định, không có EMFILE/ENFILE và latency đạt SLO.

Ví dụ, nếu process giữ 4.000 FD ở tải thường và đo được 18.000 FD ở peak, có thể cần giới hạn cao hơn 18.000 cộng headroom. Mức 65.536 thường được dùng làm giá trị cấu hình trong một số môi trường nhưng không phải chuẩn bắt buộc. Phải xem giới hạn instance, số service trên host và memory kernel trước khi chọn.

## 18. Những sai lầm thường gặp

- **Chỉ tăng `ulimit -n` trong SSH:** service systemd đang chạy không nhận giá trị đó. Đặt giới hạn đúng trong unit hoặc runtime.
- **Nhầm `RLIMIT_NOFILE` với `fs.file-max`:** một giới hạn ở cấp process, một giới hạn toàn hệ thống. Kiểm tra cả hai.
- **Tăng FD lên hàng triệu mà không sizing:** kernel cần bộ nhớ cho cấu trúc và workload có thể giữ nhiều tài nguyên hơn. Đo nhu cầu và headroom.
- **Tăng `somaxconn` để sửa mọi lỗi kết nối:** backlog không giải quyết được FD leak, CPU quá tải hoặc ứng dụng accept chậm.
- **Chỉ xem số FD hiện tại:** một snapshot không phát hiện leak tăng dần. Theo dõi theo thời gian và tải.
- **Tăng swap hoặc giảm swappiness theo công thức chung:** có thể làm latency/OOM xấu hơn. Điều chỉnh theo working set và SLO.
- **Chỉnh nhiều sysctl cùng lúc:** khó xác định thay đổi nào tạo tác động. Thay từng nhóm và đo lại.
- **Bỏ qua container runtime:** giới hạn của process trong container có thể khác shell trên host. Kiểm tra PID thực tế và cấu hình runtime.
- **Nhầm Windows handle với Unix FD:** Windows không dùng `RLIMIT_NOFILE`; chẩn đoán theo handle, socket và giới hạn runtime tương ứng.

## 19. Checklist tối ưu hệ điều hành và FD

- [ ] Đã đo FD count của process tại tải thường, peak và sau khi giảm tải.
- [ ] Đã xác định soft/hard `RLIMIT_NOFILE` của đúng PID.
- [ ] Đã kiểm tra `fs.nr_open`, `fs.file-max` và `/proc/sys/fs/file-nr`.
- [ ] Đã phân loại FD theo socket, file, pipe và descriptor runtime.
- [ ] Đã loại trừ FD leak và xác minh resource được đóng ở mọi nhánh lỗi.
- [ ] Đã sizing giới hạn theo peak concurrency và headroom.
- [ ] Service systemd/container nhận đúng giới hạn sau khi restart/redeploy.
- [ ] Backlog, ephemeral port và network queue chỉ được chỉnh khi có metric chứng minh.
- [ ] Các sysctl được quản lý bằng cấu hình có phiên bản và có rollback.
- [ ] Đã kiểm thử burst, steady-state và soak test sau thay đổi.
- [ ] Đã theo dõi kernel memory, latency, throughput, error và OOM sau tuning.
- [ ] Với Windows, đã phân biệt handle count, socket và giới hạn runtime thay vì dùng khái niệm `ulimit` của Linux.

Tối ưu cấu hình hệ điều hành và giới hạn file descriptor giúp workload tận dụng tài nguyên ổn định hơn khi concurrency tăng. Khi hiểu các lớp giới hạn, đo đúng tiến trình, xử lý FD leak và thay đổi sysctl theo bằng chứng, đội vận hành có thể tránh lỗi `Too many open files`, giảm nghẽn I/O và giữ hiệu năng compute trong giới hạn dự kiến.

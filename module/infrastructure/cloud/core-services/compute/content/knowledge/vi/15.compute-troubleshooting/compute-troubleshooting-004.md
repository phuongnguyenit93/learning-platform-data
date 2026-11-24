# CPU cao: phân biệt tải thật, vòng lặp lỗi và tranh chấp tài nguyên

CPU cao là một trong những dấu hiệu phổ biến nhất khi máy chủ hoặc ứng dụng gặp vấn đề hiệu năng. Tuy nhiên, con số CPU 90–100% không tự giải thích nguyên nhân. Máy có thể đang xử lý lượng yêu cầu tăng đột biến một cách bình thường; một tiến trình có thể lặp lại thao tác lỗi và tiêu thụ CPU vô ích; hoặc workload phải tranh chấp CPU với VM/container khác nên ứng dụng chậm dù năng lực tính toán được cấp không thay đổi.

Chẩn đoán đúng cần kết hợp mức sử dụng CPU, số tiến trình đang chạy, độ trễ ứng dụng, log lỗi, giới hạn tài nguyên và chỉ số từ hypervisor hoặc nền tảng container. Mục tiêu là xác định **CPU đang được dùng để làm công việc hữu ích, bị tiêu hao bởi lỗi, hay workload đang phải chờ được cấp CPU**.

Bài học thuộc module **CLOUD_CORE_SERVICES_COMPUTE**, trong chương **Chẩn đoán sự cố compute**. Nội dung hướng dẫn phân biệt tải thật, vòng lặp lỗi và tranh chấp tài nguyên; thu thập bằng chứng trên Linux, Windows, VM và container; khoanh vùng tiến trình; sau đó chọn biện pháp khắc phục phù hợp.

## 1. CPU cao không đồng nghĩa với ứng dụng bị lỗi

CPU utilization thể hiện tỷ lệ thời gian CPU thực thi công việc trong một khoảng đo. Nếu một máy có nhiều lõi, cách hiển thị phần trăm có thể khác nhau giữa công cụ:

- Một số công cụ hiển thị mức sử dụng tổng hợp của toàn máy, 100% tương ứng toàn bộ năng lực CPU được đo.
- Một số công cụ hiển thị mức sử dụng theo một lõi, vì vậy tiến trình đơn luồng có thể đạt 100% dù máy nhiều lõi vẫn còn năng lực.
- Trong VM/container, phần trăm có thể được tính theo vCPU được cấp hoặc theo quota/limit, không nhất thiết theo toàn bộ CPU vật lý của host.

Ví dụ, một VM có 8 vCPU chạy CPU 75% có thể đang xử lý tải bình thường. Một VM chỉ có 1 vCPU chạy 100% trong thời gian dài có thể cần thêm năng lực hoặc tối ưu ứng dụng. Một container bị giới hạn ở 0,5 CPU có thể báo CPU 100% theo quota dù host vật lý còn nhiều CPU nhàn rỗi.

Vì vậy, cần xem CPU cùng với:

- Throughput: số request, message hoặc tác vụ hoàn tất mỗi giây.
- Latency: thời gian phản hồi trung bình và các percentile như p95/p99.
- Error rate: tỷ lệ request hoặc job thất bại.
- Queue depth: lượng công việc đang chờ.
- CPU time theo tiến trình, thread và trạng thái user/system.
- Run queue, CPU pressure, steal time hoặc CPU throttling.
- Thời điểm triển khai, scale, thay đổi cấu hình hoặc sự cố phụ thuộc.

CPU cao đi cùng throughput tăng và latency ổn định có thể là tải thật. CPU cao đi cùng throughput giảm, lỗi tăng hoặc độ trễ tăng mạnh thường cần điều tra sâu hơn.

## 2. Ba nhóm nguyên nhân cần phân biệt

| Nhóm nguyên nhân | Dấu hiệu thường gặp | Câu hỏi chẩn đoán |
|---|---|---|
| Tải thực (legitimate workload) | CPU tăng cùng request/job, throughput tăng; các tiến trình chính làm việc đúng dự kiến | Nhu cầu có tăng thật không? Tài nguyên có đủ cho tải đỉnh không? |
| Vòng lặp lỗi (error/retry loop) | CPU tăng nhưng công việc hữu ích không tăng; log lặp lỗi, retry dày, crash/restart hoặc số lần gọi bất thường | Tiến trình đang lặp thao tác nào? Vì sao không thoát hoặc backoff? |
| Tranh chấp tài nguyên (resource contention) | CPU trong guest có thể cao hoặc không; run queue, steal, CPU ready, throttling hoặc scheduling delay tăng | Workload có đang phải chờ CPU vật lý hoặc bị giới hạn quota không? |

Ba nhóm này có thể cùng xuất hiện. Ví dụ, tải thật tăng làm một dịch vụ quá tải; dịch vụ retry liên tục khiến CPU tiếp tục tăng; đồng thời VM chạy trên host đông workload nên bị tranh chấp CPU. Chẩn đoán cần tìm nguyên nhân gốc và mối quan hệ thời gian, không ép mọi sự cố vào một nhãn duy nhất.

## 3. Hiểu đúng các chỉ số CPU và hệ thống

### 3.1. User time và system time

CPU time thường được chia thành:

- **User time:** thời gian CPU chạy mã ứng dụng ở user mode.
- **System time:** thời gian CPU chạy kernel thay mặt tiến trình, ví dụ xử lý system call, network stack, filesystem hoặc driver.
- **Idle:** thời gian CPU không thực thi công việc.
- **I/O wait:** thời gian CPU idle trong khi hệ thống có thao tác I/O đang chờ hoàn tất; đây không phải phần CPU đang thực thi lệnh.
- **Steal:** thời gian VM muốn chạy nhưng hypervisor đang cấp CPU vật lý cho workload khác.

User time cao có thể phản ánh tính toán thật, vòng lặp ứng dụng hoặc thuật toán kém hiệu quả. System time cao có thể liên quan đến nhiều system call, network packet, context switch, filesystem hoặc driver. I/O wait cao thường gợi ý cần kiểm tra storage; không nên coi I/O wait là bằng chứng CPU bị bão hòa.

### 3.2. Run queue và load average

Run queue là số tác vụ sẵn sàng chạy nhưng đang chờ CPU. Nếu số tác vụ runnable liên tục lớn hơn năng lực CPU, thời gian chờ lập lịch có thể tăng.

Trên Linux, load average là trung bình số tác vụ đang chạy hoặc không thể ngắt (uninterruptible sleep) trong các khoảng 1, 5 và 15 phút. Nó không phải phần trăm CPU. Load average cao có thể do CPU bận, nhưng cũng có thể tăng khi nhiều tiến trình chờ I/O ở trạng thái D.

Hãy so sánh load average với số CPU logic, run queue, CPU utilization và trạng thái tiến trình. Một load average bằng 8 có ý nghĩa khác trên máy 2 vCPU so với máy 32 vCPU.

### 3.3. Context switch và thread

Context switch xảy ra khi CPU chuyển từ thread/process này sang thread/process khác. Mức context switch tăng có thể bình thường khi hệ thống có nhiều kết nối hoặc thread; nhưng quá nhiều thread ngắn hạn, lock contention hoặc busy polling có thể tạo overhead.

Một ứng dụng nhiều thread không nhất thiết chạy nhanh hơn. Nếu số thread vượt xa năng lực CPU, hệ thống có thể tiêu tốn thời gian vào lập lịch, đồng bộ và chuyển ngữ cảnh thay vì hoàn tất công việc.

### 3.4. CPU pressure

Linux Pressure Stall Information (PSI) cung cấp thông tin về thời gian tác vụ bị stall vì thiếu CPU, bộ nhớ hoặc I/O. CPU PSI tăng cho thấy có workload bị chậm do phải chờ CPU, kể cả khi mức sử dụng trung bình chưa luôn đạt 100%.

Trong container, PSI có thể giúp phân biệt host CPU còn rảnh với nhóm workload bị giới hạn hoặc tranh chấp. Cần kiểm tra PSI ở đúng phạm vi host/cgroup và đối chiếu với quota, request và limit.

## 4. Quy trình chẩn đoán tổng quát

Khi nhận cảnh báo CPU cao, không nên lập tức reboot hoặc tăng vCPU. Hãy đi theo quy trình:

1. **Xác nhận phạm vi:** một VM, một container, một node hay toàn bộ fleet?
2. **Xác nhận thời gian:** CPU tăng đột ngột hay tăng dần? Bắt đầu trùng với deploy, cron job, scale hoặc thay đổi traffic nào?
3. **Đo mức sử dụng:** xem tổng thể và theo từng lõi, tiến trình, thread.
4. **Đối chiếu workload:** request rate, queue depth, batch schedule, throughput và latency.
5. **Tìm tiến trình tiêu thụ CPU:** xác định process/thread đứng đầu và hành vi của nó.
6. **Kiểm tra lỗi:** log, exception, retry, restart, timeout và outbound call.
7. **Kiểm tra giới hạn/tranh chấp:** quota, throttling, steal, CPU ready, run queue, host utilization.
8. **Thử giả thuyết:** thay đổi một yếu tố có kiểm soát hoặc tái hiện trong môi trường thử nghiệm.
9. **Khắc phục và xác minh:** theo dõi CPU cùng latency, throughput và error rate sau thay đổi.

~~~mermaid
flowchart TD
    A["Cảnh báo CPU cao"] --> B["Xác định phạm vi và thời điểm"]
    B --> C["Đo CPU theo host, process và thread"]
    C --> D{"Throughput / công việc hữu ích có tăng?"}
    D -- "Có" --> E["Kiểm tra tải thực và capacity"]
    D -- "Không" --> F["Kiểm tra log, retry và restart"]
    F --> G{"Có vòng lặp lỗi hoặc hoạt động lặp?"}
    G -- "Có" --> H["Khoanh vùng lỗi và dừng retry vô hạn"]
    G -- "Không" --> I["Kiểm tra run queue, steal, ready và throttling"]
    I --> J["Xác định tranh chấp hoặc giới hạn CPU"]
    E --> K["Tối ưu / scale / điều chỉnh concurrency"]
    H --> L["Sửa nguyên nhân, backoff và circuit breaker"]
    J --> M["Right-size / điều chỉnh quota / placement"]
    K --> N["Đo lại latency, throughput, error rate"]
    L --> N
    M --> N
~~~

## 5. Thu thập bằng chứng trên Linux

Nên thu thập một mẫu đủ dài để thấy xu hướng, thay vì chỉ chạy một lệnh đúng lúc cảnh báo. Các công cụ dưới đây thường có trong gói procps, sysstat hoặc perf tùy distro.

### 5.1. Xem CPU tổng thể và theo từng lõi

~~~bash
# Xem số CPU logic và topology
nproc
lscpu

# Xem CPU, load average và tiến trình theo thời gian
top

# Theo dõi từng CPU mỗi giây
mpstat -P ALL 1

# Xem run queue, blocked process, context switch và CPU
vmstat 1
~~~

Trong top hoặc mpstat, hãy xem riêng user, system, idle, iowait và steal. Nếu một lõi gần 100% nhưng các lõi khác nhàn rỗi, workload có thể bị giới hạn bởi một thread hoặc một luồng xử lý tuần tự.

vmstat thường hiển thị các cột như r (runnable), b (blocked), cs (context switches) và us/sy/id/wa/st. Cần đọc header của phiên bản đang dùng vì định dạng có thể khác.

### 5.2. Xác định tiến trình và thread

~~~bash
# Sắp xếp tiến trình theo CPU
ps -eo pid,ppid,comm,%cpu,%mem,etime --sort=-%cpu | head -20

# Theo dõi CPU theo process mỗi giây
pidstat -u 1

# Xem thread của một process
top -H -p <PID>

# Theo dõi CPU theo thread của một process
pidstat -t -p <PID> 1
~~~

%CPU trong ps có thể phản ánh mức sử dụng trung bình trong vòng đời tiến trình, không phải một phép đo tức thời giống mọi công cụ. Dùng top, pidstat hoặc telemetry theo thời gian để xác nhận.

### 5.3. Kiểm tra system call và profiling

Nếu tiến trình dùng nhiều system time, có thể quan sát system call hoặc profile stack trong một khoảng ngắn:

~~~bash
# Quan sát tóm tắt system call của process
sudo strace -c -p <PID>

# Xem các hàm đang tiêu thụ CPU nếu perf được hỗ trợ
sudo perf top -p <PID>

# Thu profile trong một khoảng thời gian ngắn
sudo perf record -F 99 -p <PID> -g -- sleep 30
sudo perf report
~~~

Profiling có overhead và có thể cần quyền đặc biệt hoặc kernel hỗ trợ. Chỉ bật trên phạm vi và thời gian cần thiết, tránh thu thập dữ liệu nhạy cảm trong môi trường production khi chưa có kiểm soát phù hợp.

## 6. Phân biệt tải thực trên Linux

Tải thật thường có mối tương quan hợp lý giữa lượng công việc đầu vào và lượng công việc hoàn tất.

Các dấu hiệu:

- Request rate hoặc message rate tăng cùng CPU.
- Throughput tăng hoặc duy trì ở mức cao dự kiến.
- CPU time tập trung ở tiến trình ứng dụng chính.
- Log lỗi không tăng bất thường.
- Retry rate và restart rate ổn định.
- Latency có thể tăng khi gần giới hạn capacity nhưng không xuất hiện vòng lặp lỗi.
- Sau khi tải giảm, CPU giảm theo.

Ví dụ, worker mã hóa video có thể dùng gần 100% CPU trong khi xử lý một batch lớn. Nếu số video hoàn tất mỗi phút tăng tương ứng và không có lỗi, đây có thể là hoạt động bình thường.

### 6.1. Kiểm tra tính song song

Nếu một tiến trình dùng 100% của một lõi trên máy 16 vCPU, hãy kiểm tra:

- Công việc có bản chất tuần tự không?
- Có lock hoặc mutex khiến thread khác phải chờ không?
- Thread pool có bị cấu hình quá nhỏ không?
- Một partition hoặc shard có tập trung toàn bộ công việc không?
- Có thể chia nhỏ công việc mà không phá vỡ thứ tự hoặc tính nhất quán không?

Tăng số vCPU không nhất thiết giúp một đoạn mã đơn luồng chạy nhanh hơn. Cần profile để tìm điểm nghẽn trước khi thay đổi kích thước VM.

### 6.2. Dự báo capacity

Nếu tải thật tăng ổn định, hãy so sánh năng lực hiện tại với nhu cầu:

- CPU utilization theo giờ/ngày và mức đỉnh.
- p95/p99 latency và SLO.
- Throughput trên mỗi vCPU.
- Số request hoặc job đồng thời.
- Headroom dành cho deploy, failover và đột biến.

Có thể scale-out nhiều replica cho ứng dụng stateless, hoặc scale-up VM khi workload cần bộ nhớ/CPU lớn hơn. Cần kiểm tra bottleneck ở database, network và storage trước khi tăng compute.

## 7. Nhận diện vòng lặp lỗi và retry storm

Vòng lặp lỗi xảy ra khi ứng dụng liên tục thực hiện một thao tác thất bại nhưng vẫn thử lại quá nhanh hoặc không giới hạn. CPU bị tiêu thụ bởi việc tạo request, serialize dữ liệu, xử lý exception, ghi log và lặp lại cùng một công việc.

Ví dụ:

- Một service gọi API phụ thuộc bị timeout rồi retry ngay lập tức.
- Worker nhận message lỗi, xử lý thất bại và nhận lại message ngay.
- Một tiến trình đọc file cấu hình lỗi trong vòng lặp không có sleep.
- Service restart liên tục do cấu hình sai, mỗi lần khởi động lại thực hiện bootstrap nặng.
- Client không nhận được response nên gửi lại request, trong khi server vẫn đang xử lý request cũ.

### 7.1. Dấu hiệu trong metric và log

- CPU tăng nhưng throughput thành công không tăng hoặc giảm.
- Error rate, timeout, retry count hoặc dead-letter count tăng.
- Log có cùng stack trace hoặc thông báo lỗi lặp lại với tần suất cao.
- Số request outbound tới một dependency tăng bất thường.
- Tiến trình liên tục restart hoặc tạo thread/task mới.
- Context switch, network syscall hoặc log I/O tăng mạnh.
- Queue depth không giảm dù worker CPU cao.

Không nên kết luận chỉ từ số lượng log. Một hệ thống tải lớn có thể ghi nhiều log hợp lệ; cần nhóm theo loại lỗi, endpoint, dependency và correlation ID để thấy mẫu lặp.

### 7.2. Kiểm tra retry policy

Retry nên có:

- Giới hạn số lần thử hoặc tổng thời gian thử.
- Exponential backoff để khoảng chờ tăng dần.
- Jitter để các client không retry đồng thời.
- Phân loại lỗi retry được và lỗi không thể khắc phục bằng retry.
- Circuit breaker để tạm ngừng gọi dependency đang lỗi.
- Dead-letter queue hoặc hàng đợi xử lý lỗi sau số lần thử tối đa.
- Idempotency để tránh hiệu ứng phụ khi request/job được thực hiện lặp.

Retry không có giới hạn có thể biến một lỗi nhỏ ở dependency thành sự cố toàn hệ thống.

### 7.3. Ví dụ retry có backoff

~~~python
import random
import time

MAX_ATTEMPTS = 5
BASE_DELAY_SECONDS = 0.5
MAX_DELAY_SECONDS = 8.0

def call_dependency_with_retry():
    for attempt in range(MAX_ATTEMPTS):
        try:
            return call_dependency()
        except TransientDependencyError:
            if attempt == MAX_ATTEMPTS - 1:
                raise

            delay = min(
                MAX_DELAY_SECONDS,
                BASE_DELAY_SECONDS * (2 ** attempt),
            )
            delay = random.uniform(0, delay)
            time.sleep(delay)
~~~

Đây là ví dụ minh họa cho lỗi tạm thời. Không nên retry mọi exception; lỗi xác thực, dữ liệu không hợp lệ hoặc quyền bị từ chối thường cần sửa cấu hình thay vì thử lại liên tục. Trong ứng dụng bất đồng bộ hoặc có nhiều request đồng thời, cần dùng retry policy không chặn thread và kết hợp circuit breaker.

### 7.4. Phân biệt vòng lặp CPU và vòng lặp I/O

Một retry loop có thể tiêu thụ CPU trong lúc tạo request và xử lý lỗi, nhưng cũng có thể chờ I/O. Nếu CPU không cao nhưng latency và queue depth tăng, lỗi có thể nằm ở dependency hoặc network. Nếu CPU cao và system time tăng, hãy xem số system call, socket, logging và context switch.

## 8. Nhận diện tranh chấp CPU trong VM

Trong VM, vCPU là tài nguyên logic được hypervisor lập lịch lên CPU vật lý. VM có 8 vCPU không đồng nghĩa nó luôn được dành riêng 8 core vật lý. Khi host có nhiều VM cùng muốn chạy, hypervisor phải phân phối thời gian CPU.

### 8.1. CPU steal trong guest Linux

CPU steal là thời gian VM có thể chạy nhưng chưa được hypervisor cấp CPU vật lý. Trên Linux, có thể quan sát cột st trong top, mpstat hoặc công cụ tương ứng.

Dấu hiệu đáng chú ý:

- CPU steal tăng cùng thời điểm latency tăng.
- Guest có runnable process nhưng throughput giảm.
- CPU utilization trong guest không giải thích hết thời gian chờ.
- Nhiều VM trên cùng host hoặc nhóm instance có hiện tượng tương tự.

Steal time thường gợi ý tranh chấp ở lớp host hoặc lịch cấp CPU, nhưng cần đối chiếu với metric provider và workload. Không phải mọi cloud đều cung cấp cùng mức độ chi tiết về host placement.

### 8.2. CPU ready và scheduling delay

Một số hypervisor cung cấp chỉ số CPU ready hoặc thời gian vCPU chờ được lập lịch. CPU ready cao kéo dài cho thấy VM muốn chạy nhưng chưa được cấp CPU vật lý. Tên metric, đơn vị và cách tính phụ thuộc nền tảng; cần xem tài liệu hypervisor/provider trước khi so sánh ngưỡng.

Nếu VM có nhiều vCPU hơn nhu cầu thực, việc lập lịch nhóm vCPU lớn có thể tăng độ phức tạp hoặc gây chờ trong một số hypervisor. Hãy right-size số vCPU thay vì mặc định càng nhiều càng tốt.

### 8.3. Noisy neighbor

Noisy neighbor xảy ra khi workload khác trên cùng host hoặc cùng hạ tầng chia sẻ tiêu thụ tài nguyên làm ảnh hưởng VM của bạn. Ngoài CPU, có thể có tranh chấp cache, memory bandwidth, storage và network.

Nếu chỉ một VM gặp vấn đề, cần kiểm tra cấu hình và workload của VM trước. Nếu nhiều VM cùng nhóm hoặc cùng thời điểm có CPU ready/steal cao, hãy thu thập instance ID, vùng, thời gian và metric để làm việc với cloud provider hoặc chuyển workload theo chính sách placement được hỗ trợ.

### 8.4. Biện pháp khắc phục

- Chọn instance family phù hợp với nhu cầu CPU liên tục hoặc burst.
- Right-size vCPU theo số liệu, tránh cấp quá lớn hoặc quá nhỏ.
- Dùng dedicated host/dedicated instance nếu yêu cầu cô lập và chi phí cho phép.
- Di chuyển hoặc tái tạo VM sang host/placement khác khi provider hỗ trợ.
- Tách workload batch nặng khỏi dịch vụ nhạy độ trễ.
- Giữ capacity headroom trong cluster để giảm tranh chấp khi failover.

Không nên kết luận cloud provider có lỗi chỉ từ một lần CPU steal ngắn. Hãy xác nhận xu hướng và ảnh hưởng tới SLO trước khi mở yêu cầu hỗ trợ.

## 9. Nhận diện CPU throttling trong container

Container có thể bị giới hạn CPU bằng quota hoặc CPU limit. Khi container sử dụng hết quota trong một chu kỳ, các thread có thể bị throttled cho đến chu kỳ tiếp theo. Host có thể còn CPU rảnh nhưng container vẫn bị chậm.

### 9.1. Kubernetes requests và limits

- **CPU request:** lượng CPU được scheduler dùng để đặt Pod và thể hiện mức tài nguyên được yêu cầu.
- **CPU limit:** giới hạn CPU tối đa mà container được phép tiêu thụ theo cơ chế runtime/cgroup.

Nếu CPU limit quá thấp, container có thể bị throttling dưới tải. Nếu request quá thấp, scheduler có thể đặt quá nhiều Pod lên cùng node, dẫn đến tranh chấp khi các workload đồng thời tăng tải.

Ví dụ:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "1"
    memory: "1Gi"
~~~

Trong ví dụ, container yêu cầu 0,5 CPU và có thể dùng tối đa 1 CPU theo giới hạn khai báo. 500m tương đương nửa CPU theo đơn vị Kubernetes. Đây không phải cam kết rằng container luôn được cấp 0,5 core vật lý riêng biệt.

### 9.2. Kiểm tra cgroup v2

Trên Linux sử dụng cgroup v2, cpu.stat trong cgroup có thể cho biết thời gian và số lần throttling. Đường dẫn thực tế phụ thuộc runtime và cách mount cgroup:

~~~bash
# Xem cgroup của shell hiện tại
cat /proc/self/cgroup

# Tìm cpu.stat trong cgroup tương ứng
cat /sys/fs/cgroup/cpu.stat
~~~

Các trường như nr_periods, nr_throttled và throttled_usec có thể giúp xác định container bị giới hạn thường xuyên hay không. Cần đọc file tại cgroup của container/Pod mục tiêu; file ở root cgroup có thể phản ánh tổng của nhiều workload.

### 9.3. Kiểm tra trên Kubernetes

~~~bash
# Xem CPU và memory hiện tại nếu metrics-server hỗ trợ
kubectl top pod -n <namespace>
kubectl top node

# Xem cấu hình requests/limits và trạng thái Pod
kubectl describe pod <pod-name> -n <namespace>

# Xem sự kiện và log container
kubectl get events -n <namespace> --sort-by=.lastTimestamp
kubectl logs <pod-name> -n <namespace> --all-containers
~~~

kubectl top hiển thị mức sử dụng tài nguyên, nhưng không phải lúc nào cũng cho biết trực tiếp số lần CPU throttling. Hãy kết hợp metric từ cAdvisor/Prometheus hoặc hệ thống giám sát cluster để xem throttling, CPU pressure và thời gian chờ.

### 9.4. Cách xử lý throttling

- Tăng CPU limit nếu workload thực sự cần thêm CPU và node có capacity.
- Điều chỉnh request để scheduler đặt Pod hợp lý hơn.
- Tối ưu concurrency và thread pool để tránh tạo quá nhiều thread.
- Scale-out nếu ứng dụng có thể phân tán tải.
- Dùng node pool phù hợp cho workload CPU-intensive.
- Kiểm tra quota cấp namespace và quota của cluster.

Tăng limit mà không xem capacity node có thể làm nhiều Pod cùng cạnh tranh CPU và khiến toàn node quá tải. Cần xem cả request, limit, node allocatable và tải của những Pod khác.

## 10. Chẩn đoán trên Windows Server

Windows có thể hiển thị CPU theo tổng thể, logical processor và từng process. Task Manager phù hợp để quan sát nhanh; Performance Monitor (PerfMon) giúp ghi lại xu hướng và phân tích theo counter.

### 10.1. Các counter nên theo dõi

| Counter | Ý nghĩa |
|---|---|
| Processor(_Total)\\% Processor Time | Mức sử dụng CPU tổng thể |
| Processor(*)\\% Processor Time | Mức sử dụng theo logical processor |
| System\\Processor Queue Length | Số thread chờ CPU |
| System\\Context Switches/sec | Số lần chuyển ngữ cảnh mỗi giây |
| Process(*)\\% Processor Time | CPU time theo tiến trình |
| Process(*)\\Thread Count | Số thread theo tiến trình |
| Process(*)\\ID Process | Ánh xạ instance counter với PID |

Counter name có thể được bản địa hóa theo ngôn ngữ Windows. Cần chọn đúng counter trên máy mục tiêu và diễn giải theo số logical processor.

### 10.2. Thu thập nhanh bằng PowerShell

~~~powershell
# Xem process tiêu thụ CPU cao theo tổng CPU time
Get-Process |
  Sort-Object CPU -Descending |
  Select-Object -First 15 Id, ProcessName, CPU, Threads

# Xem mức sử dụng CPU tổng thể theo thời gian
Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 1 -MaxSamples 10

# Xem processor queue và context switch
Get-Counter '\System\Processor Queue Length', '\System\Context Switches/sec' -SampleInterval 1 -MaxSamples 10

# Xem tiến trình và thời gian CPU
Get-CimInstance Win32_PerfFormattedData_PerfProc_Process |
  Sort-Object PercentProcessorTime -Descending |
  Select-Object -First 15 Name, IDProcess, PercentProcessorTime, ThreadCount
~~~

Get-Process hiển thị CPU time tích lũy theo tiến trình, không phải phần trăm tức thời. Get-Counter cung cấp mẫu theo khoảng thời gian. Một số tên counter có thể khác trên Windows không dùng giao diện tiếng Anh.

### 10.3. Tìm vòng lặp lỗi trên Windows

Đối chiếu process CPU cao với:

- Event Viewer: Application, System và các log của service.
- Windows Service restart và recovery action.
- IIS request queue, application pool recycle và failed request tracing nếu dùng IIS.
- .NET runtime exception, thread pool và garbage collection.
- Windows Update, antivirus scan hoặc backup job chạy đúng thời điểm.

Một antivirus scan hoặc Windows Update có thể tạo tải CPU thật trong maintenance window. Hãy xác minh lịch tác vụ và tác động trước khi kết luận đó là vòng lặp lỗi.

## 11. Phân biệt CPU cao do ứng dụng với CPU cao do tác vụ nền

Không phải tiến trình CPU cao nào cũng thuộc ứng dụng nghiệp vụ. Các tác vụ nền có thể gồm:

- Antivirus/EDR scan.
- Backup, compression hoặc deduplication.
- Log rotation và log shipping.
- Package update hoặc Windows Update.
- Vulnerability scan.
- Indexing hoặc file system scan.
- Agent inventory và configuration management.
- Batch job hoặc cron/scheduled task.

Hãy xem process name, command line, parent process, service owner và lịch chạy. Nếu một agent bảo mật chiếm CPU kéo dài, không nên tắt agent ngay; cần kiểm tra policy, phiên bản, scan scope và hướng dẫn nhà cung cấp.

## 12. Tìm nguyên nhân ở cấp ứng dụng

Khi đã xác định process chính, cần tìm hoạt động cụ thể tiêu thụ CPU:

- Hot loop hoặc thuật toán có độ phức tạp tăng nhanh theo kích thước dữ liệu.
- JSON/XML serialization quá nhiều.
- Regex có backtracking lớn hoặc biểu thức không giới hạn.
- Compression, encryption hoặc hashing trên payload lớn.
- Garbage collection hoặc memory allocation quá thường xuyên.
- Lock contention khiến thread liên tục thử lại.
- Logging đồng bộ quá nhiều.
- Polling liên tục thay vì chờ event.
- Cache miss hoặc truy vấn lặp lại.
- Retry storm tới dịch vụ phụ thuộc.

### 12.1. Dùng profiler thay vì đoán

Profiler giúp xác định hàm hoặc stack tiêu thụ CPU. Công cụ tùy runtime:

- Java: Java Flight Recorder (JFR), Java Mission Control hoặc async-profiler.
- .NET: dotnet-counters, dotnet-trace, PerfView hoặc profiler tương thích.
- Node.js: CPU profile của V8/Inspector.
- Python: cProfile, py-spy hoặc profiler phù hợp.
- Native Linux: perf, eBPF profiler hoặc công cụ tương đương.

Profiler nên chạy trên khoảng thời gian có đại diện cho sự cố. So sánh profile khi tải bình thường và khi CPU cao để tìm phần tăng bất thường. Chú ý overhead, quyền truy cập và dữ liệu nhạy cảm.

### 12.2. Phân tích theo thread

Nếu một process có CPU cao, hãy xem thread nào tiêu thụ CPU:

- Một thread 100% có thể chỉ ra vòng lặp đơn luồng.
- Nhiều thread 100% có thể phản ánh tải song song hoặc retry đồng thời.
- Nhiều thread hoạt động nhưng throughput thấp có thể là lock contention hoặc busy waiting.
- Thread pool tăng liên tục có thể chỉ ra task không hoàn tất hoặc concurrency không giới hạn.

Chỉ tăng số thread khi biết bottleneck là thiếu song song. Với workload CPU-bound, số worker đồng thời nên được cân nhắc theo số CPU khả dụng và giới hạn container.

## 13. Ma trận chẩn đoán nhanh

| Quan sát | Giả thuyết ưu tiên | Bằng chứng cần lấy |
|---|---|---|
| CPU tăng, request rate và throughput tăng tương ứng | Tải thực | Request metrics, CPU theo process, latency |
| CPU tăng, throughput giảm, lỗi/retry tăng | Vòng lặp lỗi hoặc dependency lỗi | Log nhóm theo lỗi, retry count, outbound request |
| CPU guest thấp nhưng latency cao, steal/ready tăng | Tranh chấp host/VM | Hypervisor CPU ready, guest steal, host metrics |
| Container đạt limit, throttled time tăng | CPU quota quá thấp hoặc concurrency cao | cgroup cpu.stat, container limit, node capacity |
| Một lõi 100%, các lõi khác rảnh | Luồng xử lý tuần tự hoặc hot thread | Per-core metric, thread profile, lock |
| System time và context switch cao | Kernel/network/driver hoặc quá nhiều thread | mpstat, pidstat, perf, network metrics |
| Load average cao, iowait cao, CPU idle còn | Tác vụ chờ I/O | vmstat, storage latency, process state D |
| CPU tăng theo lịch cố định | Batch hoặc tác vụ nền | Cron/task scheduler, backup, scan, update |

Ma trận chỉ giúp ưu tiên giả thuyết. Cần xác nhận bằng dữ liệu và thử nghiệm trước khi thay đổi cấu hình.

## 14. Biện pháp khắc phục theo nguyên nhân

### 14.1. Nếu là tải thật

- Scale-out thêm replica nếu ứng dụng stateless và bottleneck có thể phân tán.
- Scale-up VM hoặc container khi workload cần thêm CPU liên tục.
- Tối ưu thuật toán, truy vấn, serialization và cache.
- Điều chỉnh concurrency để tận dụng CPU mà không tạo quá nhiều thread.
- Dùng queue để làm phẳng tải đỉnh cho workload bất đồng bộ.
- Tách batch workload khỏi API nhạy độ trễ.
- Đặt autoscaling dựa trên metric phù hợp, kết hợp latency/queue depth thay vì chỉ CPU.

### 14.2. Nếu là vòng lặp lỗi

- Sửa lỗi gốc trong code hoặc cấu hình dependency.
- Giới hạn retry, thêm exponential backoff và jitter.
- Dùng circuit breaker để ngừng gọi dependency đang lỗi.
- Đưa message lỗi sang dead-letter queue sau số lần thử phù hợp.
- Bảo đảm idempotency cho thao tác có thể được thực hiện lại.
- Giảm log lặp bằng rate limit hoặc log sampling, nhưng vẫn giữ metric và dấu vết cần điều tra.
- Dừng rollout hoặc rollback phiên bản vừa triển khai nếu có bằng chứng lỗi liên quan.

### 14.3. Nếu là tranh chấp hoặc throttling

- Right-size vCPU, request và limit theo số liệu.
- Chuyển workload sang node/instance phù hợp hơn.
- Tách workload CPU-intensive và workload nhạy latency.
- Điều chỉnh placement hoặc dùng dedicated capacity nếu yêu cầu cô lập.
- Giữ headroom cho failover và đợt tải tăng.
- Trao đổi với provider khi CPU ready/steal bất thường kéo dài và có bằng chứng.

### 14.4. Nếu do tác vụ nền

- Dời lịch scan, backup hoặc batch ra khỏi giờ cao điểm nếu chính sách cho phép.
- Giới hạn concurrency và CPU của agent khi nhà cung cấp hỗ trợ.
- Cập nhật agent nếu phiên bản hiện tại có lỗi đã được xác nhận.
- Phân tách lịch bảo trì khỏi thời gian xử lý tải cao.
- Không vô hiệu hóa công cụ bảo mật hoặc backup nếu chưa có phương án thay thế được phê duyệt.

## 15. Ví dụ thực tế: API CPU 95% nhưng throughput giảm

Một API catalog chạy trên VM 4 vCPU. Sau một lần triển khai, CPU tăng từ 45% lên 95%, p95 latency tăng gấp bốn lần và throughput thành công giảm. Số request đầu vào không tăng đáng kể.

Nhóm vận hành thu thập:

1. mpstat cho thấy user time tăng mạnh, steal time thấp.
2. pidstat cho thấy process API là tiến trình tiêu thụ CPU chính.
3. Log cho thấy nhiều request gọi dịch vụ inventory bị timeout.
4. Metric outbound cho thấy số lần gọi inventory tăng nhiều lần trên mỗi request catalog.
5. Profile ứng dụng cho thấy phần lớn CPU nằm trong vòng lặp retry và serialize exception.

Nhóm xác định bản triển khai mới đã thay đổi retry policy: khi inventory timeout, API retry ngay nhiều lần trong cùng request. Điều này làm CPU tăng dù số request đầu vào không đổi, trong khi throughput thành công giảm.

Biện pháp xử lý:

- Tạm rollback phiên bản mới để khôi phục dịch vụ.
- Sửa retry policy với giới hạn số lần, backoff và jitter.
- Thêm circuit breaker cho inventory.
- Giới hạn deadline tổng của request.
- Thêm metric retry theo dependency và cảnh báo khi retry/request vượt ngưỡng.
- Kiểm thử lại dưới điều kiện inventory timeout trước khi triển khai.

Nếu chỉ tăng VM từ 4 lên 8 vCPU, vòng lặp retry vẫn tồn tại và có thể tiêu thụ gấp đôi CPU. Tăng compute không thay thế việc sửa nguyên nhân trong ứng dụng.

## 16. Ví dụ thực tế: VM CPU thấp nhưng ứng dụng vẫn chậm

Một VM có 8 vCPU, CPU utilization trong guest chỉ khoảng 35%, nhưng p99 latency tăng mạnh vào giờ cao điểm. mpstat cho thấy steal time tăng; hypervisor dashboard cho thấy CPU ready cao trong cùng khoảng thời gian. Nhiều VM khác trên cùng nhóm host cũng bị ảnh hưởng.

Nhóm vận hành kiểm tra:

- Không có thay đổi đáng kể về request rate.
- Process profile không có hot loop hoặc retry bất thường.
- Guest có runnable thread chờ CPU.
- CPU ready tăng đồng thời với latency.

Giả thuyết phù hợp là VM bị tranh chấp CPU ở lớp host. Nhóm lưu timestamp, instance ID và metric rồi chuyển VM theo cơ chế placement được provider hỗ trợ. Sau khi chuyển, steal/ready giảm và latency trở lại mức bình thường.

Trường hợp này cho thấy CPU utilization thấp trong guest không loại trừ việc VM đang chờ CPU vật lý.

## 17. Xây dựng cảnh báo hữu ích

Một cảnh báo chỉ dựa trên CPU > 80% trong 5 phút có thể tạo nhiều false positive, nhất là với batch job hoặc workload được thiết kế để tận dụng CPU.

Nên kết hợp:

- CPU utilization kéo dài.
- p95/p99 latency hoặc SLO burn rate.
- Error rate và retry rate.
- Queue depth hoặc request backlog.
- CPU throttling/steal/ready/pressure.
- Số replica và capacity còn lại.

Ví dụ, cảnh báo có thể kích hoạt khi CPU cao liên tục **và** latency vượt SLO hoặc queue depth tăng. Với batch job, có thể dùng thời gian hoàn thành và tiến độ thay cho HTTP latency.

Ngưỡng phải được hiệu chỉnh theo workload, baseline và mục tiêu dịch vụ. Không áp dụng một ngưỡng chung cho mọi VM.

## 18. Những sai lầm thường gặp

- **Chỉ nhìn CPU tổng:** bỏ qua một lõi hoặc thread đang bão hòa.
- **Coi load average là CPU percentage:** load average còn bao gồm tác vụ chờ I/O không thể ngắt.
- **Coi iowait là CPU đang bận:** iowait thường là thời gian CPU idle chờ I/O.
- **Tăng vCPU ngay khi CPU cao:** có thể che dấu retry loop hoặc bug ứng dụng.
- **Nhầm CPU thấp với không có tranh chấp:** VM có thể chờ CPU ở hypervisor hoặc bị throttling.
- **Không xem log và throughput:** bỏ qua vòng lặp lỗi làm CPU tăng nhưng công việc hữu ích giảm.
- **Retry không backoff:** tạo retry storm và làm dependency càng quá tải.
- **Tăng thread vô hạn:** tăng context switch, lock contention và scheduling overhead.
- **Tăng container limit mà quên capacity node:** có thể làm node quá tải và ảnh hưởng Pod khác.
- **Tắt agent để giảm CPU:** có thể làm mất bảo vệ, backup hoặc giám sát.
- **Chỉ đo một thời điểm:** bỏ lỡ lịch batch, đợt tải và tương quan với deploy.
- **Không đo lại sau khắc phục:** không chứng minh được nguyên nhân đã được loại bỏ.

## 19. Checklist xử lý sự cố CPU cao

Khi nhận cảnh báo, hãy xác nhận lần lượt:

- [ ] Phạm vi là host, VM, container, node hay toàn fleet?
- [ ] CPU tăng từ thời điểm nào và có trùng deploy, scale hoặc tác vụ định kỳ?
- [ ] Mức sử dụng theo từng lõi, process và thread là bao nhiêu?
- [ ] User, system, idle, iowait và steal thay đổi thế nào?
- [ ] Run queue, load average và CPU pressure có tăng không?
- [ ] Throughput, latency, error rate, retry rate và queue depth thay đổi ra sao?
- [ ] Có log lỗi lặp, restart loop hoặc outbound call bất thường không?
- [ ] VM có CPU ready/steal cao hoặc container có throttling không?
- [ ] Agent nền, backup, antivirus hoặc update có đang chạy không?
- [ ] Đã profile process và xác định hot function/thread chưa?
- [ ] Biện pháp khắc phục có xử lý đúng nguyên nhân không?
- [ ] Sau thay đổi, CPU, latency, throughput và error rate đã trở lại baseline chưa?

## 20. Ghi nhớ

CPU cao có thể là dấu hiệu của tải thật, vòng lặp lỗi hoặc tranh chấp tài nguyên. Tải thật thường đi cùng công việc hữu ích tăng; vòng lặp lỗi thường đi cùng retry, exception hoặc restart bất thường; tranh chấp thể hiện qua run queue, CPU steal/ready, pressure hoặc throttling.

Hãy đo theo host, process và thread; đối chiếu với throughput, latency, error rate và queue depth; kiểm tra log và giới hạn của VM/container; sau đó profile để tìm nguyên nhân cụ thể. Chỉ scale khi workload thực sự cần thêm năng lực. Với vòng lặp lỗi, sửa retry và logic ứng dụng; với tranh chấp, điều chỉnh quota, placement hoặc loại compute. Luôn xác minh kết quả bằng metric sau khắc phục để bảo đảm dịch vụ cải thiện chứ không chỉ làm con số CPU thay đổi.

# 21.1 Thiết kế bộ dữ liệu nền gồm thông tin VM, GC log và JFR theo ngân sách tài nguyên

> **Phạm vi:** Java 21, HotSpot JVM, môi trường service chạy dài hạn trên máy ảo, container hoặc Kubernetes. Bộ dữ liệu nền là tập bằng chứng **được thu có kế hoạch trước sự cố**, đủ để đối chiếu trạng thái JVM, GC và các hoạt động quan trọng trong JFR với triệu chứng người dùng. Thiết kế phải vừa **có dữ liệu trước–trong–sau sự cố**, vừa **không vượt ngân sách CPU, độ trễ, RAM, đĩa, I/O/network và retention**. Không phải cứ ghi càng nhiều thì khả năng chẩn đoán càng tốt.

## 1. Đầu ra phải đạt

Một cấu hình nền tốt cần trả lời được sáu câu hỏi:

1. **JVM nào đang chạy?** JDK vendor/build, phiên bản ứng dụng, GC/heap flags, PID và thời gian khởi động, instance/container/pod, giới hạn CPU/RAM.
2. **GC có ảnh hưởng độ trễ không?** GC log với UTC + uptime, GC ID, pauses, heap trước/sau và thông tin collector cần thiết.
3. **Điều gì xảy ra cùng thời điểm?** JFR có ring buffer/disk recording, event settings đã kiểm chứng, đủ CPU/threads/GC/locks/I/O theo yêu cầu chẩn đoán thường gặp.
4. **Dữ liệu giữ được bao lâu?** Có giới hạn dung lượng, tốc độ ghi đã đo, cửa sổ thời gian thực tế dưới tải đỉnh và trigger dump trước khi rotate mất.
5. **Chi phí là bao nhiêu?** Overhead theo workload, peak disk usage gồm cả file export, quota trong container, băng thông shipping và chi phí bản sao.
6. **Ai được xem và khi nào xóa?** Có phân loại dữ liệu, ACL, mã hóa, checksum, owner, retention và quy trình bàn giao.

Đừng nhầm **đã bật JFR** với **đã giữ được file điều tra**, hoặc **đã có GC logs** với **đã có đủ phút trước một alert**. Cần diễn tập đường đi đầy đủ: startup → ghi dữ liệu → xuất dữ liệu → mở/đọc được → bảo toàn và xóa đúng hạn.

## 2. Thiết kế ba tầng theo chi phí

| Tầng | Nội dung | Tần suất/điều kiện | Rủi ro chính |
| --- | --- | --- | --- |
| A — inventory theo phiên JVM | VM.version, VM.flags, VM.command_line khi được phép, VM.uptime, app build, pod UID, container limits | Khi startup/restart và khi config đổi | Rò rỉ secrets trong arguments, sai định danh sau restart |
| B1 — GC log | Unified logging về GC/pauses, UTC+uptime, có file rotation | Liên tục, mức vừa đủ | Ghi quá nhiều khi GC storm, rotation xóa dữ liệu trước incident |
| B2 — JFR mặc định | Recording dùng default.jfc, disk=true, maxage/maxsize hữu hạn | Liên tục trong ngân sách | Retention thực ngắn hơn yêu cầu, repository đầy hoặc mất khi pod chết |
| C — thu chẩn đoán nâng cao | JFR profile/custom config, chi tiết lock/I/O, thread dumps, logging debug | Cửa sổ ngắn khi đã có giả thuyết và cho phép | Overhead, STW/disk/CPU, dữ liệu lớn hoặc nhạy cảm |

Tầng A, B1 và B2 là **bộ dữ liệu nền** của bài này. Tầng C chỉ là chiến lược mở rộng, không được tự động bật toàn bộ trên mọi replica.

**Không nên đưa vào baseline không giới hạn:** heap dump, class histogram, NMT detail, full thread dump vài giây/lần, JFR path-to-GC-roots hay Heap Statistics. Những thao tác này phục vụ mục đích khác và có thể tốn CPU, heap, I/O hoặc gây pause đáng kể.

## 3. Thiết kế định danh và trục thời gian chung

Mỗi artifact phải được nối về **một JVM instance cụ thể**, không chỉ một tên service.

| Thuộc tính | Dữ liệu cần giữ | Giá trị |
| --- | --- | --- |
| Service/environment | name, deployment, namespace, app build/image digest | Biết nhóm ứng dụng và phiên bản |
| Instance | hostname, pod UID/container ID, JVM PID và startup timestamp | PID có thể trùng ở nhiều pod hoặc được tái sử dụng |
| VM | vendor, Java 21 build, VM name, GC, Xms/Xmx, JFR config | Giải thích khác biệt giữa các lần deploy |
| Resource limits | cgroup CPU quota, CPU throttling, memory limit, volume quota | Diễn giải CPU/RSS và khả năng giữ log |
| Time | UTC timestamp, JVM uptime, timezone, NTP skew, sampling bucket | Ghép request latency/GC/JFR không lệch đồng hồ |
| Artifact | type, source, start/end UTC, path, size, checksum, owner, TTL | Bảo vệ và truy vết dữ liệu |

JFR event có timestamp tuyệt đối; unified logging có thể in UTC và uptime; monitoring đôi khi dùng bucket 10 giây hoặc 1 phút. **Không tuyên bố nhân quả ở độ chính xác mili giây khi clock skew hoặc metric resolution không cho phép.**

Ví dụ giả định: ba pod đều chạy JVM với PID bằng 1. Chỉ dùng PID để ghép GC log và JFR là **sai**; phải thêm pod UID/instance và JVM startup time. Sau rolling restart cần một record inventory mới, ngay cả nếu image/app version không đổi.

### 3.1. Mẫu manifest dễ triển khai

~~~yaml
schema: java21-diagnostics-baseline/v1
service: catalog-api
environment: production
instance: catalog-api-pod-example
pod_uid: example-uid
jvm_start_utc: "2026-10-29T09:20:00Z"
jvm_pid: 1
jdk_version: "21.0.x"
jdk_vendor: "capture-actual-value"
gc: "verify-from-VM-flags"
jfr_setting: default
gc_log_pattern: "/srv/diag/gc-%p.log"
jfr_retention: "maxage=30m,maxsize=128m"
clock: "UTC; NTP offset must be checked"
artifacts:
  - kind: vm-flags
    file: vm-flags.txt
    checksum: "compute-after-write"
  - kind: gc-log
    file: gc-1.log
    checksum: "compute-after-write"
  - kind: jfr-incident
    file: incident-window.jfr
    checksum: "compute-after-write"
~~~

Đây là **schema minh họa**, chưa phải dữ liệu đã thu. Khi triển khai, điền giá trị thực, không gửi placeholder rồi tuyên bố đã hoàn thành thu thập.

## 4. Tầng A — VM metadata: ít lần thu nhưng phải đủ bối cảnh

### 4.1. Bộ lệnh Java 21

Với JVM chạy trên host hoặc container mà operator có quyền attach, xác minh PID thật. Các lệnh mẫu:

~~~bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> VM.uptime
jcmd <PID> VM.flags
jcmd <PID> VM.command_line
jcmd <PID> VM.info
~~~

Giải thích:

- **VM.version:** thông tin phiên bản HotSpot/JDK đích; không nhầm với lệnh java -version của máy operator có thể chạy JDK khác.
- **VM.uptime:** số giây sống của JVM; ghép với mốc khởi động từ orchestrator/monitoring.
- **VM.flags:** giá trị flags runtime, gồm heap/GC và các biến cấu hình có thể tác động footprint, pause, JFR.
- **VM.command_line:** startup arguments, có thể chứa đường dẫn app, flags và cấu hình quan trọng.
- **VM.info:** thông tin JVM/environment/status rộng hơn, hữu ích khi cần phân tích sự cố nhưng có thể dài.
- **jcmd -l:** tìm PID trong namespace quan sát được, không phải cơ chế định danh bền vững.

**Bảo mật đặc biệt:** VM.command_line và VM.system_properties có thể chứa token, password, proxy, hostname, cấu hình kết nối nội bộ. Không lưu thẳng vào ticket/Git/chat công khai. Cần tách **raw artifact phân quyền hẹp** và **bản đã che bí mật** dùng khi chia sẻ.

Một snapshot mỗi lần khởi động/restart hoặc thay đổi cấu hình là đủ để làm **inventory**. Không có ích khi thu VM.info mỗi giây; muốn thấy biến động CPU/heap thì dùng metrics/JFR.

### 4.2. Thu mẫu và kiểm tra file

Ví dụ shell Linux, người thao tác đã xác minh PID và có quyền:

~~~bash
umask 077
TARGET_PID=12345
EVIDENCE_DIR="$HOME/java-diagnostics"
mkdir -p "$EVIDENCE_DIR"
chmod 700 "$EVIDENCE_DIR"

date -u +"%Y-%m-%dT%H:%M:%SZ" > "$EVIDENCE_DIR/captured-utc.txt"
jcmd "$TARGET_PID" VM.version > "$EVIDENCE_DIR/vm-version.txt"
jcmd "$TARGET_PID" VM.uptime > "$EVIDENCE_DIR/vm-uptime.txt"
jcmd "$TARGET_PID" VM.flags > "$EVIDENCE_DIR/vm-flags.txt"
~~~

**12345 là PID giả định**, không sao chép vào production. Kiểm tra mã thoát của từng jcmd, kích thước và quyền file: shell redirect vẫn có thể tạo file rỗng khi attach lỗi. Thu app build/image digest/CPU quota từ deployment inventory được cấp quyền, không suy ra từ tên PID.

Không lưu secrets chỉ vì nhu cầu "đầy đủ". Nếu cần giữ startup command line, áp dụng access control và redaction riêng; không tự động đính kèm raw vào hệ thống ticket.

## 5. Tầng B1 — GC unified logging: chọn thông tin và rotation

### 5.1. GC logs bổ sung gì cho JFR?

GC log là chuỗi sự kiện theo collector: GC ID, pha, pause, heap trước/sau, nguyên nhân khi có và thông tin JVM logging configuration. JFR cho timeline nhiều nhóm CPU/GC/threads/locks/I/O; **GC logs thường giàu chi tiết collector hơn**. Cả hai cần UTC/uptime và JVM identity để so với request latency.

**GC duration không luôn bằng STW pause.** Collector có pha concurrent; không cộng một GC duration với các pause phase nằm bên trong thành hai lần dừng. Khi báo p99 bị ảnh hưởng, căn chính xác các **GC pause intervals**, không chỉ GC count.

### 5.2. Cú pháp khởi động Java 21 có giới hạn đĩa

Giả sử /srv/diag là filesystem được account JVM ghi được:

~~~bash
java \
  -Xlog:gc*,safepoint:file=/srv/diag/gc-%p.log:utctime,uptime,level,tags:filecount=4,filesize=20M \
  -jar app.jar
~~~

- **gc* và safepoint**: cấu hình tag selectors theo mức mặc định; lượng sự kiện tùy collector/workload.
- **utctime,uptime**: cho phép đối chiếu với JFR UTC và xác định vị trí theo thời gian sống của JVM.
- **level,tags**: biết mức log và loại event, tránh mất bối cảnh khi parse.
- **%p**: gắn PID vào tên log; **không phải unique ID giữa nhiều container**. Nếu dùng volume chung, phân vùng theo pod/instance hoặc file naming/manifest riêng.
- **filecount=4,filesize=20M**: ngân sách sơ bộ khoảng **80 MiB** log/instance cùng headroom. Rotation thường có chi phí và sai số; kiểm tra file thực sau test.

GC storm có thể làm log ghi nhanh gấp nhiều lần. Vì vậy **rotation kiểm soát dung lượng, không bảo đảm số giờ retention**. Nếu output ở mức debug/trace hoặc file shipper nhân bản dữ liệu, chi phí lớn hơn.

### 5.3. Đo thực tế trước khi áp dụng đại trà

~~~bash
jcmd <PID> VM.log list
ls -lh /srv/diag
df -h /srv/diag
df -i /srv/diag
~~~

Nếu cú pháp VM.log tùy build cần xác minh, chạy jcmd <PID> help VM.log. Theo dõi bytes written trong một đoạn tải điển hình rồi tính:

~~~text
rate_mib_per_hour = measured_log_mib / measured_hours
expected_retention_hours ≈ configured_rotation_mib / rate_mib_per_hour

Ví dụ: 80 MiB rotation, 10 MiB/giờ = khoảng 8 giờ ở rate đo.
Khi incident làm rate thành 40 MiB/giờ, khoảng lưu còn 2 giờ.
~~~

Đây là **ước lượng**, không phải cam kết chính xác. Ưu tiên đo tốc độ **giờ cao điểm** để chọn rotation. Nếu cần giữ lâu hơn trước alert, ship GC log sớm tới kho đủ bảo mật và dùng retention riêng, thay vì tăng filecount vô giới hạn.

Trong JVM đang chạy, jcmd VM.log có thể điều chỉnh một số output/tag khi được phép, nhưng **không phục hồi các log chưa ghi trong quá khứ**. Nâng mức debug tạm thời phải có TTL, owner và rollback.

## 6. Tầng B2 — JFR continuous theo cấu hình low-overhead

### 6.1. Default khác profile ra sao?

Oracle JDK 21 cung cấp default.jfc và profile.jfc. **default.jfc** được đề xuất để ghi liên tục, có overhead **thường dưới 1%** theo tài liệu Oracle (không phải mức bảo đảm cho mọi workload). **profile.jfc** bật nhiều loại dữ liệu hơn, phù hợp điều tra ngắn, nhưng tiêu thụ CPU/đĩa hơn.

| Cấu hình | Nên dùng | Giới hạn cần ghi nhớ |
| --- | --- | --- |
| default | Baseline liên tục để tìm cửa sổ sự cố | Không mặc định chứa tất cả event và mọi stack; threshold/sampling có thể bỏ các thao tác ngắn |
| profile | Đợt profiling ngắn khi cần hot methods hoặc contention chi tiết hơn | Event rate/overhead cao hơn; phải xác định điểm dừng |
| Custom .jfc | Một giả thuyết cụ thể cần thêm event hoặc threshold thấp | Phải test overhead và giữ bản config để giải thích kết quả |

**Không bật Heap Statistics hoặc path-to-gc-roots trong baseline theo thói quen.** Chúng phục vụ điều tra memory leak nhưng có thể gây thêm GC hoặc thu thập tốn thời gian, làm nhiễu latency mà hệ thống đang đo.

### 6.2. Khởi động JFR trên JVM cùng GC logs

~~~bash
java \
  -Xlog:gc*,safepoint:file=/srv/diag/gc-%p.log:utctime,uptime,level,tags:filecount=4,filesize=20M \
  -XX:StartFlightRecording=name=baseline,settings=default,disk=true,maxage=30m,maxsize=128m \
  -jar app.jar
~~~

Giải thích cờ JFR:

- **name=baseline**: định danh recording dùng khi JFR.check hoặc JFR.dump.
- **settings=default**: áp dụng default.jfc; không có nghĩa tất cả event đều được bật.
- **disk=true**: dùng disk repository để giữ recording data; repository path có thể mặc định ở temp của hệ điều hành. Kiểm tra bằng cấu hình thực tế.
- **maxage=30m**: giới hạn thời gian muốn giữ dữ liệu ghi trên đĩa, trong điều kiện còn đủ dung lượng.
- **maxsize=128m**: giới hạn lượng recording data giữ lại; JFR lưu theo chunk và có ràng buộc minimum chunk size. Đây không phải giới hạn **tổng đĩa gồm file dump xuất ra, GC logs, log ứng dụng và temporary files**.

**Cửa sổ thực tế có thể nhỏ hơn 30 phút** khi dữ liệu ghi nhanh và maxsize đạt ngưỡng trước maxage. Phải đo bytes/giờ và kiểm tra start/end của file dump thật. Nếu JFR ring đã xoay mất phần sự cố, không thể tái tạo các event đó sau này.

### 6.3. Kiểm chứng và bảo toàn khi alert

~~~bash
jcmd <PID> JFR.check
jcmd <PID> JFR.check verbose=true
jcmd <PID> JFR.configure
~~~

Kiểm tra recording name, thời gian, event settings/threshold, disk/maxage/maxsize và repository path. Tài khoản chạy jcmd phải có quyền attach; PID trong container khác PID trên host.

Khi incident vừa xảy ra, ghi dump **trước khi ring bị rotate**:

~~~bash
jcmd <PID> JFR.dump name=baseline \
  filename=/srv/diag/incident-20261029T101500Z.jfr
~~~

Tên file mang timestamp **giả định**, phải thay bằng tên duy nhất đúng thời điểm. File dump được tạo trong **filesystem của JVM đích** và có thể chiếm dung lượng tương đương một recording lớn **bên cạnh** các chunk đang có. JFR.dump không dừng recording nền, nhưng ghi file vẫn dùng I/O và cần headroom.

Sau khi xuất file:

~~~bash
jfr summary /srv/diag/incident-20261029T101500Z.jfr
jfr metadata --events jdk.GarbageCollection,jdk.CPULoad \
  /srv/diag/incident-20261029T101500Z.jfr
~~~

jfr summary xác minh recording interval/event counts của **toàn file**, chưa tự lọc đúng một phút p99 cao. Dùng JDK Mission Control hoặc API jdk.jfr.consumer để phân tích interval. Nếu event không xuất hiện, kiểm tra cấu hình, threshold, sampling, duration, retention và có đúng JVM trước khi kết luận không xảy ra vấn đề.

### 6.4. Mở rộng trong cửa sổ ngắn

Khi cần nhiều execution samples, stack/lock/I/O details hơn và đã kiểm tra chi phí:

~~~bash
jcmd <PID> JFR.start name=incident-profile \
  settings=profile disk=true duration=3m \
  filename=/srv/diag/incident-profile.jfr
~~~

**Đây là một phiên điều tra có thời hạn**, không thay thế cấu hình nền. Kiểm tra bằng JFR.check và xác nhận recording profile đã dừng đúng lúc, recording baseline vẫn còn. Nếu xuất thêm một file trong khi đang chạy:

~~~bash
jcmd <PID> JFR.dump name=incident-profile \
  filename=/srv/diag/incident-profile-partial.jfr
~~~

Tính cả **profile recording, file export, baseline ring và GC logs** khi kiểm tra disk budget. Không dựa vào một con số overhead cố định vì các event có thể được thu cùng lúc dưới cấu hình hiệu lực; thử tải theo toàn bộ tổ hợp vận hành.

## 7. Ngân sách tài nguyên có thể tính và kiểm tra được

### 7.1. Mô hình dung lượng

~~~text
PerJVM_LocalBudget =
    GC_log_rotation
  + JFR_repository
  + concurrent_JFR_exports
  + incident_profile_files
  + VM_metadata
  + other_local_logs/temp
  + safety_headroom

FleetBudget = Σ PerJVM_LocalBudget across replicas and nodes

GC_retention_hours ≈ GC_rotation_bytes / observed_GC_bytes_per_hour

JFR_retention_hours ≈ min(
    configured_maxage_hours,
    maxsize_bytes / observed_JFR_bytes_per_hour
)
~~~

Đây là công thức **ước lượng**: event rate tăng khi incident, JFR chunking/temporary files có độ hạt, compression/copy tạo thêm đỉnh, và các giới hạn storage/container có thể khác filesystem của host.

### 7.2. Ví dụ định lượng, không phải cấu hình mặc định

Giả sử 4 replica, mỗi pod có diagnostics volume 1 GiB, app logs ở volume khác; cho mỗi pod:

| Khoản | Dự trù |
| --- | ---: |
| GC logs: 4 × 20 MiB | 80 MiB |
| JFR continuous repository | 128 MiB |
| Một JFR incident dump đồng thời | 128 MiB |
| VM snapshots + manifest | 5 MiB |
| Temporary/metadata/khác | 20 MiB |
| Safety headroom | 128 MiB |
| **Tổng** | **489 MiB/pod** |

Phép tính: **80 + 128 + 128 + 5 + 20 + 128 = 489 MiB/pod**. Với 4 replica, tổng phần dành riêng khoảng **1.956 MiB (~1,91 GiB)** trên các volume, chưa tính bộ nhớ đĩa của app hoặc incident profile vượt kế hoạch.

Nếu cùng lúc lưu **ba** file JFR dump thay vì một, phải cộng thêm dung lượng thực của hai bản nữa; không thể chỉ dựa vào maxsize=128m của ring. Nếu nhiều pod dùng chung PVC, giới hạn theo **PVC/node** chứ không chỉ chia đều theo pod.

Phương án chống lấp đầy: alert khi volume qua ngưỡng đã thống nhất; giới hạn số dump đồng thời, cooldown để tránh alert flapping, hạn chế profile khi thiếu chỗ, ship bằng kênh an toàn và xác minh checksum trước khi xóa bản nguồn.

### 7.3. CPU, latency và RAM

Tài liệu Oracle ghi default.jfc **thường** có overhead thấp, nhưng tổng chi phí của VM snapshots, GC logging, JFR event sampling, exporter, checksum, encryption, compression và shipping phụ thuộc ứng dụng.

Thử A/B hoặc canary theo cùng JDK build, GC flags, CPU quota, request load, dataset và warmup:

1. **A:** ứng dụng và monitoring hiện có, không thêm dữ liệu nền.
2. **B:** bật VM inventory startup + GC logs có rotation.
3. **C:** thêm JFR default continuous.
4. **D:** bật profile/custom recording ngắn để xác định ngân sách escalation.
5. Lặp ở giờ bình thường và tải đỉnh, giữ đầy đủ số lần đo và độ phân tán.

So throughput, p95/p99 latency, error rate, CPU-seconds/request, JVM RSS/cgroup memory, CPU throttling, GC pauses, bytes/s local disk, network ship throughput và disk high-water. Chỉ công bố overhead đã **đo trong workload tương đương**; không mặc định mức <1% tài liệu thành cam kết SLO.

**RAM:** JFR có các local/global buffers ngoài việc giữ chunk trên đĩa; maxsize/maxage không giới hạn toàn bộ native memory overhead. Chỉ đổi các tham số JFR.configure như memorysize/stackdepth khi có bằng chứng và hiểu ràng buộc initialization của JVM.

### 7.4. Retention thực tế và ngoại lệ vận hành

- GC storm làm bytes/giờ tăng, log rotate nhanh hơn.
- Default ring maxage 30 phút nhưng maxsize 128 MiB có thể chỉ giữ vài phút nếu recording event rate cao.
- Container bị OOMKilled/evicted có thể làm mất JFR repository ở ephemeral filesystem trước khi operator kịp dump.
- Một file dump output có thể làm đầy volume dù ring còn trong maxsize.
- Khi copy ra kho tập trung, bandwidth và queue của shipper có giới hạn; không để queue/logging backlog tiêu thụ vô hạn disk.
- Nếu nhiều service chia một volume, phải có quota theo tenant và mức ưu tiên cho log phục vụ ứng dụng.
- Ghi lại **actual earliest retained event timestamp** trong mỗi lần diễn tập; con số maxage đơn thuần chưa chứng minh retention.

## 8. Runbook khởi động, xác nhận và ship

### 8.1. Chuẩn bị filesystem

Ví dụ account JVM là app, môi trường Linux:

~~~bash
sudo install -d -o app -g app -m 0700 /srv/diag
sudo -u app test -w /srv/diag
df -h /srv/diag
df -i /srv/diag
~~~

Đường dẫn, account, owner và volume cần thay theo thực tế. Thư mục nên riêng, có quota, không nằm ở public web root hay repository source code.

### 8.2. Cấu hình startup minh họa toàn bộ tầng B

~~~bash
java -Xms512m -Xmx2g \
  -Xlog:gc*,safepoint:file=/srv/diag/gc-%p.log:utctime,uptime,level,tags:filecount=4,filesize=20M \
  -XX:StartFlightRecording=name=baseline,settings=default,disk=true,maxage=30m,maxsize=128m \
  -jar app.jar
~~~

**-Xms512m / -Xmx2g chỉ là ví dụ**; service container có thể có memory limit nhỏ hơn heap + metaspace + stacks + buffers, vì vậy phải tính lại. Vùng repository JFR có thể mặc định ở tmp: cần xác minh bằng lệnh JFR.configure và cấu hình lưu trữ theo policy; không suy rằng mọi dữ liệu JFR nằm trong /srv/diag.

### 8.3. Acceptance test bắt buộc

~~~bash
jcmd <PID> VM.version
jcmd <PID> VM.flags
jcmd <PID> VM.uptime
jcmd <PID> VM.log list
jcmd <PID> JFR.check verbose=true
jcmd <PID> JFR.configure
~~~

Chỉ PASS khi:
- PID và JVM instance được xác thực;
- GC log có dòng với UTC/uptime và rotation hoạt động;
- JFR.check hiển thị recording baseline chạy, đúng settings;
- có thể xuất một JFR dump **thực** và mở bằng jfr summary;
- các artifact có timestamp, owner, checksum và nơi nhận;
- disk/CPU overhead trong ngân sách đo được;
- không lộ secrets ở nơi chia sẻ rộng.

Lệnh jcmd redirect có thể tạo file rỗng dù attach lỗi; kiểm tra cả exit code và nội dung. Trong container, jcmd từ host có thể không thấy JVM vì PID namespace/user; công cụ trong JDK image có thể không sẵn nếu image tối giản.

## 9. Thu thập khi có sự cố: ưu tiên giữ dữ liệu sắp mất

Một quy trình ngắn cho incident:

1. **Đóng dấu triệu chứng**: UTC start/end, p95/p99/error rate, endpoint, traffic, pod/host, độ phân giải metrics và clock skew.
2. **Đúng JVM**: xác nhận version/PID/startup/GC flags, không trộn replica.
3. **Dump JFR ring ngay** nếu retention còn chứa symptom; dùng tên file duy nhất và filesystem của JVM đích.
4. **Giữ GC logs** chứa cùng khoảng, gồm các file đã rotate; đừng xóa file đang ghi.
5. **Lưu VM metadata/manifest** và checksum sau khi artifact đã hoàn thành, copy an toàn ra nơi nhận.
6. **Đối chiếu cùng timeline** giữa GC pauses, JFR events và APM/trace; kiểm tra request critical path thay vì cộng duration của các thread song song.
7. **Escalate có điều kiện**: khi evidence thiếu, bật profile hoặc logs chi tiết cho vài phút sau khi có ngân sách và người chịu trách nhiệm. Không thể tạo dữ liệu quá khứ chưa được ghi.
8. **Quay lại baseline**; lưu hoặc xóa dữ liệu theo retention, ghi rõ khoảng thiếu/đã mất.

Nếu alert đến trễ hơn retention ring, phải đánh dấu **evidence unavailable** thay vì khẳng định JVM không có event bất thường.

### 9.1. Trích cửa sổ lịch sử còn tồn tại

Java 21 cho phép JFR.dump begin/end với thời gian xác định. Ví dụ timestamp UTC:

~~~bash
jcmd <PID> JFR.dump name=baseline \
  begin=2026-10-29T10:14:30Z end=2026-10-29T10:17:00Z \
  filename=/srv/diag/incident-window.jfr
~~~

Tên recording/path/timestamp đều là **mẫu** cần thay. Nếu một event dài bắt đầu trước window, trích xuất chunks rồi lọc event theo start/end có thể cần giữ recording gốc rộng hơn. Dump không thể khôi phục segment đã bị maxsize/maxage xoay mất.

## 10. Lab Java 21 xác minh ba lớp

Chương trình lab độc lập dưới đây chạy khoảng 20 giây, liên tục tạo mảng nhỏ để có workload thử nghiệm. Nó **không bảo đảm** JFR có mọi loại event hoặc GC xảy ra đúng số lần, nhưng giúp kiểm tra pipeline end-to-end.

Tạo file **BaselineCaptureLab.java**:

~~~java
public final class BaselineCaptureLab {
    private static volatile byte[] lastBlock;

    public static void main(String[] args) throws Exception {
        int seconds = args.length == 1 ? Integer.parseInt(args[0]) : 20;
        if (seconds < 1 || seconds > 120) {
            throw new IllegalArgumentException("seconds must be 1..120");
        }
        System.out.println("BASELINE LAB START");
        long finish = System.nanoTime() + seconds * 1_000_000_000L;
        while (System.nanoTime() < finish) {
            lastBlock = new byte[256 * 1024];
            lastBlock[0] = 1;
            Thread.sleep(50);
        }
        System.out.println("BASELINE LAB DONE");
    }
}
~~~

Dùng JDK 21 trong một thư mục thực hành có quyền ghi:

~~~bash
mkdir -p ./diag-lab
javac BaselineCaptureLab.java
java -Xms32m -Xmx128m \
  -Xlog:gc*,safepoint:file=./diag-lab/gc-%p.log:utctime,uptime,level,tags:filecount=3,filesize=10M \
  -XX:StartFlightRecording=name=baseline,settings=default,disk=true,maxage=5m,maxsize=64m,dumponexit=true,filename=./diag-lab/baseline-lab.jfr \
  BaselineCaptureLab 20
~~~

**Stdout do chương trình tự in**, không gồm thông báo JFR/JVM:

~~~text
BASELINE LAB START
BASELINE LAB DONE
~~~

Trong lúc còn sống, từ terminal khác cùng host/user:

~~~bash
jcmd -l
jcmd <LAB_PID> VM.version
jcmd <LAB_PID> VM.flags
jcmd <LAB_PID> VM.log list
jcmd <LAB_PID> JFR.check verbose=true
~~~

Sau khi chương trình kết thúc bình thường, nhờ dumponexit=true recording được dump thành file basename đã chỉ định (nếu filesystem writable). Kiểm tra:

~~~bash
ls -lh ./diag-lab/
jfr summary ./diag-lab/baseline-lab.jfr
jfr print --events jdk.GarbageCollection,jdk.CPULoad \
  ./diag-lab/baseline-lab.jfr
~~~

Không có stdout cố định cho lệnh jfr: event count và runtime timestamps khác theo máy. **GC có thể không xuất hiện** dù cấu hình chính xác, vì app ngắn và heap vẫn đủ; không coi điều đó là bằng chứng thiếu logger. Điều cần chứng minh là file tồn tại, interval đúng, settings có event đã bật và mở được.

Thử thêm hai lượt với tải tương tự: một lượt settings=profile; một lượt tăng allocation rate hoặc thay GC log rotation. Đo bytes/s, overhead và retention thực tế thay vì sao chép tham số 64m/10M của lab vào production.

## 11. Bảo mật và vòng đời dữ liệu

| Artifact | Rủi ro | Biện pháp |
| --- | --- | --- |
| VM.command_line, VM.system_properties | Mật khẩu, token, DB URL, proxy credential | Hạn chế thu, raw encrypted, redacted copy, least privilege |
| VM.version, VM.flags, inventory | Cấu hình hệ thống, đường dẫn và topology | Access theo vai trò, không công khai nội bộ |
| GC logs | Kích thước heap, GC tuning, thời gian ứng dụng | Rotation, ACL, nơi lưu riêng, xóa đúng policy |
| JFR | Method/class/thread names, call stacks, host/path/network info, event fields | Kho riêng, encryption khi lưu/truyền, audit/TTL |
| Manifest và checksum | Thông tin pod/instance và vị trí artifact | Phân loại và quyền xem tương ứng |

Thiết kế **hai tầng retention**: local ring giữ dữ liệu gần nhất, giới hạn để bảo vệ dịch vụ; khi có incident mới xuất sang kho an toàn được kiểm soát, lưu lâu hơn theo **chính sách** (không có TTL mặc định 7 ngày do Java quy định). Sau copy cần kiểm tra size, checksum ở nguồn/đích, đọc được bằng công cụ phù hợp và ghi người bàn giao.

Không gửi raw JFR/VM properties lên GitHub, ticket công khai, pastebin hoặc chat không được duyệt. Không xóa file gốc trong khi JVM đang ghi hoặc trước khi bản ở nơi nhận được kiểm chứng; khi hết hạn thì xóa/thu hồi theo policy.

## 12. QA và chỉ số giám sát của chính pipeline chẩn đoán

Một pipeline không đạt chỉ vì startup không có lỗi. Cần kiểm tra:

| Check | PASS khi | FAIL thì làm gì |
| --- | --- | --- |
| JVM identity | Có vendor/build, PID/startup, pod UID, app version nhất quán | Sửa manifest/metadata collection |
| GC logging | Đã có file, UTC/uptime, rotation đúng, output nằm trên volume dự kiến | Kiểm tra cờ -Xlog, quyền JVM, collector |
| JFR availability | JFR.check có baseline và settings đúng | Kiểm tra startup flag, JDK, quyền, disk |
| JFR recoverability | Dump được, jfr summary mở được, file phủ symptom window | Tăng ring phù hợp ngân sách hoặc dump sớm |
| Disk and quotas | Có cả ring + dump + headroom, không dùng chung volume quan trọng vô kiểm soát | Giảm recording/exports, đổi volume/quota |
| Latency overhead | p95/p99, throughput, CPU và RSS trong ngưỡng đã đo | Giảm event/log detail, thu ngắn hơn |
| Security | Raw không nằm trên public storage; ACL/checksum/retention kiểm chứng | Cô lập, redact, revoke và báo incident |
| Timeline | UTC/uptime có thể ghép với metrics trong sai số được ghi | Kiểm tra NTP/timezone và collector delays |

Theo dõi **tuổi event cũ nhất còn giữ, GC log bytes/hour, JFR write bytes/hour, JFR dump failures, volume used%, shipping backlog, collector CPU, latency overhead, NTP offset**. Kiểm tra lại budget sau mỗi thay đổi JDK build, GC, .jfc, log verbosity, container limits, storage, traffic hoặc số replica.

## 13. Lỗi thiết kế phổ biến

| Sai lầm | Tác hại | Cách sửa |
| --- | --- | --- |
| Chỉ bật JFR khi incident đã kết thúc | Mất quá khứ | Default ring liên tục, dump ngay sau alert |
| Coi maxage=30m luôn giữ 30 phút | maxsize có thể loại dữ liệu trước đó | Đo peak JFR rate và earliest-event time |
| Chỉ tính maxsize JFR, bỏ qua file export | Dump làm đầy volume | Dành chỗ cho repository + dump + profile + headroom |
| Coi GC rotation 80 MiB là 8 giờ cố định | GC storm xoay nhanh hơn | Đo giờ bình thường và tải đỉnh |
| Dùng profile liên tục ở mọi replica | Overhead/I/O lớn | Default baseline, profile có TTL |
| Đặt GC/JFR trên volume app data quan trọng | Quota đầy ảnh hưởng service | Volume riêng và cảnh báo |
| Không lưu JVM start time | PID bị tái sử dụng | Gắn instance/pod + PID + startup UTC |
| VM flags/args đưa thẳng vào ticket | Lộ secrets | Tách raw và redacted |
| Không kiểm tra file thực mở được | Thu được file hỏng/rỗng | JFR summary, checksum, readback |
| Dữ liệu JFR vắng event | Nhầm không có vấn đề | Kiểm tra thresholds, .jfc, sampling |
| Tăng log debug không có lịch tắt | Giảm retention và tác động latency | Escalation có owner và rollback |
| Cộng JFR duration nhiều thread | Thổi phồng request downtime | Cùng time window, critical path và interval overlap |

## 14. Checklist triển khai

**Trước production**
- [ ] Có câu hỏi chẩn đoán cho từng tín hiệu.
- [ ] Chọn đúng JDK 21 build, collector, Xms/Xmx, instance identity và NTP.
- [ ] VM inventory một lần mỗi phiên, có phương án xử lý secrets.
- [ ] GC log UTC+uptime, rotation và bytes/hour được đo thực.
- [ ] JFR default disk recording với maxage/maxsize có giới hạn.
- [ ] Ngân sách CPU, RAM, disk+export headroom, ship/network và retention theo số replica.
- [ ] Policy phân quyền, retention, checksum và owner.

**Sau deploy**
- [ ] VM.version/flags/u​​ptime đúng JVM.
- [ ] GC log xuất file, rotation có ý nghĩa, timestamp khớp UTC.
- [ ] JFR.check verbose=true xác nhận baseline và settings.
- [ ] Thử JFR.dump thật, jfr summary mở được và xác nhận khoảng retained.
- [ ] Alert quota/dump failures/collector backlog đã cấu hình.

**Khi incident**
- [ ] Ghi symptom window, request p99/throughput, host/pod và clock uncertainty.
- [ ] Dump ring JFR trước khi bị xoay mất; giữ GC logs cùng window.
- [ ] Gắn VM snapshot/manifest, version, checksum và ACL.
- [ ] Chỉ nâng mức profile/logs với duration/owner/budget có kiểm soát.
- [ ] Báo cáo interval thiếu dữ liệu, quay về baseline và lưu/xóa theo TTL.

## 15. Bài tập tự đánh giá

1. Một pod có GC log 80 MiB, JFR ring 128 MiB, một dump 128 MiB và headroom 128 MiB. Nếu thêm một profile 180 MiB, tối thiểu phải tính bao nhiêu dung lượng? Còn thiếu khoản gì?
2. GC logs 80 MiB ghi 10 MiB/giờ lúc thường, 40 MiB/giờ lúc GC storm. Retention hai trường hợp xấp xỉ bao nhiêu, và vì sao không cố định?
3. JFR maxage 30m nhưng maxsize 128m; khi event rate là 32 MiB/phút thì dữ liệu thực còn gần bao nhiêu phút? Thay đổi nào an toàn hơn tăng maxsize vô hạn?
4. Ba pod cùng PID=1, sau rolling restart lại xuất hiện PID=1. Thiết kế artifact key tránh trộn các recording.
5. Nếu alert 10:20 và dump 10:22, nhưng vòng JFR chỉ giữ 10:18 trở đi, bạn có thể đưa kết luận về 10:10 không? Viết mức độ tin cậy.
6. Nêu vì sao VM.system_properties không được tự động dán vào ticket và cách cấp quyền raw vs redacted.
7. Lập thí nghiệm A/B đo tổng overhead GC logging + JFR default ở workload 100, 500 và 1000 req/s; chọn metrics và ngưỡng dừng.
8. Thiết kế trigger lưu JFR khi p99 vượt SLO nhưng có cooldown, quota và giới hạn số bản để tránh alert flapping làm đầy đĩa.

**Tiêu chí hoàn thành:** đọc được ba lớp VM info/GC log/JFR; tính được ngân sách và retention; kiểm chứng thực tế trên JDK 21; biết cách giữ bản ghi trước sự cố, bảo vệ dữ liệu và nâng mức an toàn.

## 16. Tài liệu gốc Java 21

- [Oracle JDK 21 — jcmd: VM.version, VM.flags, VM.info, VM.log, JFR.start, JFR.dump, JFR.check](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — java: unified logging -Xlog, -XX:StartFlightRecording](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Oracle JDK 21 — Flight Recorder Configurations: default.jfc, profile.jfc và overhead](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html)
- [Oracle JDK 21 — jfr: summary, metadata, print](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle JDK 21 — Diagnostic Tools: VM inventory và công cụ chẩn đoán](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)

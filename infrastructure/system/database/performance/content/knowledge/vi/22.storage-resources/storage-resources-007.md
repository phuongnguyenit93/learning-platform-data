# Giới hạn tài nguyên của máy ảo, container và dịch vụ cơ sở dữ liệu

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt tài nguyên nhìn thấy bên trong máy ảo hoặc container với tài nguyên thực sự được cấp và giới hạn bởi hạ tầng.
- Giải thích CPU quota, CPU throttling, memory limit, OOM kill, giới hạn IOPS/throughput và network bandwidth.
- Nhận biết khác biệt giữa request và limit trong Kubernetes cũng như các giới hạn của dịch vụ cơ sở dữ liệu được quản lý.
- Đọc số liệu ở nhiều lớp để xác định nút thắt đến từ database, cgroup, hypervisor, node hay storage service.
- Lập ngân sách CPU, bộ nhớ, kết nối và I/O phù hợp với workload cơ sở dữ liệu.
- Thiết kế benchmark và điều chỉnh cấu hình database trong phạm vi tài nguyên thực sự được cấp.

## 1. Vì sao giới hạn tài nguyên ảo hóa ảnh hưởng đến hiệu năng database?

Một hệ quản trị cơ sở dữ liệu có thể chạy trên máy chủ vật lý, máy ảo, container hoặc dịch vụ cloud được quản lý. Trong các môi trường này, tài nguyên mà database nhìn thấy không nhất thiết là toàn bộ tài nguyên vật lý. CPU, RAM, dung lượng lưu trữ, IOPS, băng thông và số kết nối có thể bị giới hạn ở một hoặc nhiều lớp.

Ví dụ, máy chủ vật lý có 64 CPU logic và 256 GiB RAM, nhưng một VM chỉ được cấp 8 vCPU và 32 GiB RAM. Bên trong VM, database lại chạy trong container có quota 4 CPU và memory limit 16 GiB. Dịch vụ storage gắn với VM có thể tiếp tục giới hạn ở 6.000 IOPS và 200 MiB/s. Database phải hoạt động trong giao của các giới hạn đó.

Trong module DATABASE_PERFORMANCE, phân tích execution plan và tối ưu SQL chỉ giải quyết một phần vấn đề. Một truy vấn có kế hoạch tốt vẫn có thể chậm nếu container bị CPU throttling, bị memory pressure, storage chạm trần IOPS hoặc dịch vụ database đang ở tier giới hạn thấp.

Nguyên tắc điều tra là đo tài nguyên ở đúng lớp. Số CPU trong `lscpu`, RAM mà hệ điều hành báo, CPU usage của container và quota của cgroup có thể mô tả những khía cạnh khác nhau. Không lấy một con số đơn lẻ để kết luận database được quyền dùng toàn bộ tài nguyên đó.

## 2. Các lớp tài nguyên trong môi trường ảo hóa

Một kiến trúc phổ biến có thể gồm:

```text
Ứng dụng và database process
            |
            v
Container / cgroup limits
            |
            v
Guest operating system
            |
            v
Virtual machine (vCPU, vRAM, virtual disk, vNIC)
            |
            v
Hypervisor / host scheduler
            |
            v
Physical CPU, RAM, storage và network
            |
            v
Cloud service quotas / shared infrastructure
```

Không phải hệ thống nào cũng có đủ các lớp hoặc theo đúng thứ tự này. Managed database có thể che guest OS và container khỏi người dùng; Kubernetes có thể chạy container trực tiếp trên node hoặc trong VM.

Ở mỗi lớp, cần hỏi:

- Tài nguyên nào được cấp cố định, tài nguyên nào chỉ là mức chia sẻ?
- Giới hạn là hard limit, soft limit, reservation hay quota theo thời gian?
- Có cơ chế burst tạm thời không? Nếu có, burst kéo dài bao lâu và điều kiện phục hồi là gì?
- Metric nào cho biết tài nguyên đang bị giới hạn?
- Ai có quyền thay đổi giới hạn: nhóm ứng dụng, nền tảng, cloud provider hay DBA?

## 3. CPU trong máy ảo: vCPU không đồng nghĩa với một lõi vật lý riêng

vCPU là CPU ảo mà guest OS nhìn thấy. Hypervisor lập lịch vCPU lên các CPU vật lý hoặc logical processor của host. Tùy nền tảng, nhiều VM có thể chia sẻ cùng CPU vật lý và mức overcommit có thể thay đổi theo tải.

Điều này tạo ra một số tình huống:

- VM nhìn thấy 8 vCPU nhưng không phải lúc nào cũng được chạy đồng thời trên 8 lõi vật lý riêng.
- Khi host bận, vCPU có thể phải chờ hypervisor cấp thời gian CPU.
- VM lớn với nhiều vCPU có thể gặp khó khăn trong việc được lập lịch đủ CPU đồng thời, tùy kiến trúc và mức overcommit.
- CPU ready time hoặc steal time tăng có thể cho thấy guest muốn chạy nhưng hypervisor chưa cấp CPU.

### CPU ready và steal time

Trong một số nền tảng, CPU ready phản ánh thời gian VM sẵn sàng chạy nhưng phải chờ CPU vật lý. Trong Linux guest, steal time là thời gian CPU ảo bị hypervisor lấy lại để chạy VM khác. Tên metric và cách tính phụ thuộc hypervisor và công cụ giám sát.

Nếu database báo CPU usage không cao nhưng query latency tăng, hãy kiểm tra steal/ready time, CPU pressure ở host và mức overcommit. CPU utilization thấp bên trong guest không loại trừ việc VM đang chờ được lập lịch.

### NUMA và topology

Máy chủ nhiều socket thường có kiến trúc NUMA, trong đó mỗi CPU socket có vùng bộ nhớ cục bộ với độ trễ truy cập khác nhau. VM lớn hoặc cấu hình vNUMA không phù hợp có thể làm truy cập bộ nhớ chéo node tăng độ trễ.

Database sử dụng buffer pool lớn và nhiều worker có thể nhạy với memory locality. Cần xem topology mà hypervisor trình bày cho VM, cách vCPU và RAM được bố trí, cùng hướng dẫn của nền tảng. Không nên tự pin CPU hoặc thay NUMA policy khi chưa hiểu cấu hình host.

## 4. CPU quota và throttling trong container

Container thường dùng Linux cgroups để giới hạn và phân phối tài nguyên. CPU limit thường được triển khai bằng quota theo một khoảng thời gian, trong khi CPU weight/shares quyết định mức ưu tiên tương đối khi nhiều container tranh chấp CPU.

Trong cgroup v2, file `cpu.max` có dạng:

```text
quota period
```

Ví dụ:

```text
150000 100000
```

Điều này cho phép container dùng tổng cộng 150.000 microsecond CPU trong mỗi chu kỳ 100.000 microsecond, tương đương quota trung bình 1,5 CPU trong chu kỳ đó. Đây là giới hạn tổng thời gian CPU, không phải một CPU vật lý riêng.

Nếu workload cần CPU liên tục vượt quota, kernel có thể throttle container cho đến chu kỳ tiếp theo. Truy vấn có thể chạy nhanh trong một phần chu kỳ rồi bị tạm dừng, tạo dao động latency ngay cả khi CPU usage trung bình trông không quá cao.

### Phân biệt CPU request, weight và limit

- **Request/reservation:** mức tài nguyên dùng để lập lịch hoặc phân chia công bằng, tùy nền tảng.
- **CPU weight/shares:** trọng số tương đối khi các nhóm cùng tranh chấp CPU; không phải mức CPU tối đa cố định.
- **CPU quota/limit:** giới hạn tổng thời gian CPU có thể dùng trong một khoảng.

Trong Kubernetes, CPU request giúp scheduler chọn node và ảnh hưởng trọng số chia sẻ khi tranh chấp. CPU limit được thực thi bằng quota trên Linux trong cấu hình phổ biến. Một container có request 2 CPU và limit 4 CPU có thể dùng vượt 2 CPU khi có tài nguyên và được phép, nhưng sẽ bị giới hạn ở 4 CPU.

### Dấu hiệu throttling

Trên cgroup v2, `cpu.stat` có thể chứa các bộ đếm như `nr_periods`, `nr_throttled` và `throttled_usec`. Tỷ lệ chu kỳ bị throttle và thời gian throttle tăng cùng query latency là dấu hiệu cần điều tra.

Không chỉ xem CPU percent. Hãy đối chiếu:

- CPU usage của process database và toàn container.
- CPU quota/period và tỷ lệ throttled.
- CPU pressure stall information (PSI) nếu kernel hỗ trợ.
- CPU ready/steal ở VM và mức bận của node.
- Số worker song song, connection và concurrency của truy vấn.

## 5. Bộ nhớ trong VM và container

Database thường dùng RAM cho buffer pool/shared buffers, cache trang, session, sort/hash workspace, execution plan, background worker và các cấu trúc nội bộ khác. Container hoặc VM còn cần bộ nhớ cho kernel, agent giám sát, sidecar, filesystem cache và các process phụ.

Memory limit của container là giới hạn mà kernel dùng để kiểm soát lượng bộ nhớ cgroup có thể sử dụng. Khi cgroup tiến gần giới hạn, reclaim có thể tăng; nếu không thể thu hồi đủ, kernel có thể kích hoạt OOM kill và kết thúc một process trong cgroup.

### Memory request và memory limit

Trong Kubernetes:

- Memory request là lượng bộ nhớ scheduler dùng khi đặt Pod lên node.
- Memory limit là mức tối đa được áp dụng cho container theo cơ chế kernel.
- Nếu container vượt memory limit, nó có thể bị OOM killed; trạng thái thường thấy là `OOMKilled`.
- Node cũng có thể chịu memory pressure và eviction Pod theo QoS, priority và chính sách kubelet.

Khác với CPU, memory limit không đơn giản throttle để container chậm lại. Khi không thể cấp phát thêm, process có thể bị OOM kill. Vì vậy, đặt memory limit quá sát nhu cầu có thể gây restart database hoặc làm gián đoạn workload.

### cgroup v2 memory metrics

Các file thường hữu ích gồm:

- `memory.current`: bộ nhớ hiện đang được tính cho cgroup.
- `memory.max`: hard limit, nếu được cấu hình.
- `memory.high`: ngưỡng áp lực mềm có thể kích hoạt reclaim/throttling theo cơ chế memory controller.
- `memory.events`: các sự kiện như high, max, oom và oom_kill.
- `memory.stat`: phân tách một số loại bộ nhớ như anonymous, file cache và kernel memory theo phiên bản.

Trên cgroup v1, tên file và cách tổ chức khác. Đường dẫn cgroup phụ thuộc runtime, namespace và cách hệ thống mount controller.

### OOM kill và database

OOM kill có thể kết thúc database process, worker hoặc sidecar tùy mức độ và chính sách kernel. Nếu process chính của database bị giết, hệ thống có thể phải recovery khi khởi động lại. Nếu một worker bị giết, truy vấn hoặc tác vụ nền có thể thất bại.

Điều tra OOM cần xem cả event trong cgroup, kernel log, container status, memory usage theo process và thời điểm database restart. Chỉ nhìn RSS của process chính có thể bỏ sót page cache, memory của worker hoặc các process khác trong cùng cgroup.

## 6. Lập ngân sách bộ nhớ cho database trong container

Không nên cấp toàn bộ memory limit cho buffer pool hoặc shared buffers. Database cần headroom cho các phần bộ nhớ ngoài vùng cache chính và cho biến động theo concurrency.

Một mô hình ngân sách khái quát:

```text
Memory limit của container
  = vùng bộ nhớ database dùng chung
  + bộ nhớ theo session/connection
  + bộ nhớ sort/hash của truy vấn đồng thời
  + background worker và process phụ
  + filesystem/kernel/sidecar overhead
  + headroom an toàn
```

Ví dụ minh họa container có limit 16 GiB. DBA có thể dành 9 GiB cho vùng cache database, dự trù 2 GiB cho session và operator đồng thời, 1 GiB cho process phụ và hệ điều hành trong container, còn 4 GiB làm headroom cho dao động. Các con số thực tế phải được đo theo engine, phiên bản, workload và cách tính memory của cgroup.

### Bộ nhớ theo connection và operator

Một số cấu hình bộ nhớ áp dụng theo từng connection, từng operator hoặc từng worker, không phải một vùng duy nhất cho toàn database.

Ví dụ PostgreSQL:

- `shared_buffers` là vùng shared buffer.
- `work_mem` áp dụng cho từng thao tác sort/hash có liên quan; một truy vấn có thể có nhiều operator và parallel worker.
- `maintenance_work_mem` dùng cho một số thao tác bảo trì như tạo index hoặc vacuum ở các trường hợp tương ứng.
- Mỗi backend process và extension có overhead riêng.

Ví dụ MySQL InnoDB:

- `innodb_buffer_pool_size` là vùng cache chính cho dữ liệu và index.
- Mỗi connection có thể có buffer và cấu trúc riêng.
- Sort/join/read buffers có thể được cấp theo nhu cầu của statement/session.

Ví dụ SQL Server:

- Buffer pool và memory clerks dùng bộ nhớ theo các nhóm khác nhau.
- Query memory grant cho sort/hash phụ thuộc plan, cardinality và concurrency.
- Max server memory giới hạn phần SQL Server quản lý, nhưng cần chừa bộ nhớ cho OS và process khác.

Vì vậy, không thể lấy memory limit chia cho `max_connections` rồi coi kết quả là ngân sách đầy đủ cho mỗi session. Hãy đo peak concurrent connections, query operators đồng thời, memory grant, worker count và process overhead.

### Connection pool cũng là một phần của ngân sách

Đặt `max_connections` quá cao có thể làm tăng process/thread overhead và số thao tác đồng thời tranh chấp CPU, RAM, lock và I/O. Connection pool ở ứng dụng nên giới hạn tổng số connection phù hợp với capacity database, không nhân mỗi instance ứng dụng một pool lớn mà không tính tổng.

Ví dụ có 10 instance ứng dụng, mỗi instance pool tối đa 100 connection sẽ tạo khả năng 1.000 connection đến database. Nếu database chỉ được sizing cho 200 session hoạt động, connection pool có thể làm tăng memory pressure và scheduling overhead.

## 7. Giới hạn storage: dung lượng, IOPS và throughput

Storage có nhiều giới hạn độc lập:

- **Capacity:** tổng dung lượng có thể sử dụng.
- **IOPS:** số thao tác đọc/ghi mỗi giây.
- **Throughput/bandwidth:** số byte có thể truyền mỗi giây.
- **Latency:** thời gian hoàn thành một thao tác I/O.
- **Queue depth:** số thao tác đang chờ hoặc đang được xử lý.
- **Burst credits:** khả năng vượt mức baseline trong thời gian giới hạn ở một số loại volume.

IOPS cao không bảo đảm throughput cao nếu mỗi thao tác rất nhỏ; throughput cao cũng không bảo đảm latency thấp nếu queue sâu hoặc workload random I/O.

### Ví dụ giới hạn volume

Giả sử volume được cấu hình tối đa 5.000 IOPS và 200 MiB/s. Database ghi các page nhỏ ngẫu nhiên có thể chạm giới hạn IOPS trước khi đạt 200 MiB/s. Một luồng backup tuần tự có thể chạm giới hạn throughput trong khi IOPS vẫn còn dư.

Nếu storage có burst credits, workload ngắn có thể chạy nhanh hơn baseline. Khi credits cạn, throughput hoặc IOPS giảm về mức nền. Benchmark ngắn có thể chỉ đo giai đoạn burst.

### Queue và latency

Khi offered I/O vượt khả năng xử lý, queue tăng. Latency p95/p99 thường tăng trước khi throughput giảm rõ rệt. Đối với database, log flush latency và random read latency có thể quan trọng hơn throughput tuần tự trung bình.

Đo riêng volume chứa:

- Transaction log/WAL/redo.
- Data file và index.
- Temporary file, tempdb hoặc tablespace tạm.
- Backup và archive.

Nếu các loại I/O cùng dùng một volume, chúng có thể cạnh tranh băng thông và IOPS. Tách volume có thể giúp cô lập workload trong một số nền tảng, nhưng chỉ khi storage backend thực sự cung cấp giới hạn hoặc tài nguyên độc lập.

## 8. Giới hạn I/O của container và Kubernetes

Linux cgroups có thể điều khiển I/O block device theo trọng số hoặc giới hạn băng thông/IOPS, tùy phiên bản kernel, controller và thiết bị.

Trong cgroup v2:

- `io.weight` đặt trọng số tương đối khi tranh chấp I/O.
- `io.max` có thể giới hạn `rbps`, `wbps`, `riops` và `wiops` cho thiết bị được chỉ định.
- `io.stat` cung cấp số liệu I/O theo thiết bị và cgroup.

Ví dụ một cấu hình `io.max` có thể giới hạn bytes/s hoặc IOPS cho một device. Không áp dụng một con số chung cho mọi container; phải xác định device major:minor, storage driver và tác động đến volume thực tế.

Kubernetes có thể quản lý ephemeral storage request/limit để kiểm soát dung lượng dữ liệu tạm trên node, nhưng điều này không đồng nghĩa với giới hạn IOPS của persistent volume. Persistent volume performance còn phụ thuộc StorageClass, CSI driver, cloud disk tier và chính sách provider.

Container có thể thấy filesystem path như `/var/lib/postgresql/data`, nhưng đường dẫn đó có thể nằm trên overlay filesystem, network block volume hoặc một tầng storage ảo. Hãy xác định thiết bị và lớp backend thực sự.

## 9. Network limits và database

Database qua mạng cần băng thông, packet rate và latency ổn định. Các giới hạn có thể xuất hiện ở:

- vNIC của VM hoặc virtual switch.
- Container network, CNI hoặc service mesh sidecar.
- Node bandwidth và network policy.
- Cloud instance network cap hoặc burst bandwidth.
- Managed database endpoint, proxy và giới hạn kết nối.
- Cross-zone/cross-region traffic.

Network bottleneck ảnh hưởng truy vấn trả nhiều dữ liệu, replication, backup, bulk load và ứng dụng có nhiều round trip.

Ví dụ, một truy vấn trả 500 MiB dữ liệu có thể bị giới hạn bởi network throughput dù database hoàn tất xử lý nhanh. Ngược lại, truy vấn nhỏ nhưng có hàng trăm round trip nhạy với latency hơn băng thông.

Cần đo bytes/s, packets/s, retransmission, RTT, connection reset và network queue ở cả phía ứng dụng lẫn database. Khi dùng TLS hoặc compression, CPU có thể trở thành nút thắt bổ sung.

## 10. Giới hạn của dịch vụ cơ sở dữ liệu được quản lý

Managed database thường trừu tượng hóa VM, container, filesystem và storage backend. Người dùng có thể không nhìn thấy cgroup hoặc hypervisor metrics, nhưng vẫn bị giới hạn bởi service tier và quota.

Những giới hạn phổ biến:

- vCPU hoặc mức CPU được chia sẻ theo tier.
- RAM hoặc memory class.
- Dung lượng storage tối đa và cách scale storage.
- IOPS/throughput baseline hoặc mức provisioned.
- Burst credits và cơ chế autoscaling.
- Số connection tối đa, session hoặc worker.
- Giới hạn transaction log, backup, replication hoặc read replica.
- Network throughput và giới hạn egress.
- Quota theo tài khoản, region, project hoặc subscription.

Tier cao hơn có thể tăng CPU/RAM, IOPS hoặc giới hạn connection, nhưng không nhất thiết tăng mọi tài nguyên theo cùng tỷ lệ. Một dịch vụ có thể bị giới hạn bởi IOPS dù CPU còn thấp, hoặc bị giới hạn connection dù RAM còn dư.

### Autoscaling không đồng nghĩa với tài nguyên vô hạn

Một số dịch vụ tự tăng storage hoặc compute theo tải; một số chỉ scale khi người dùng đổi tier. Autoscaling có thể có độ trễ, ngưỡng, mức tối đa và chi phí. Khi điều tra, hãy xác định:

- Metric nào kích hoạt scale?
- Thời gian từ khi vượt ngưỡng đến khi có tài nguyên mới?
- Có giới hạn tối đa hoặc quota vùng không?
- Storage tăng có kéo theo IOPS/throughput tăng không?
- Việc scale có gây failover, restart hoặc thay đổi endpoint không?

Không giả định autoscaling đã diễn ra chỉ vì workload tăng. Xác nhận bằng metric và event của dịch vụ.

## 11. Kubernetes: requests, limits và QoS

Kubernetes dùng resource requests và limits trong cấu hình container. Các giá trị này có ý nghĩa khác nhau đối với scheduler và runtime.

| Resource | Request | Limit | Hành vi khi vượt hoặc thiếu tài nguyên |
| --- | --- | --- | --- |
| CPU | Hỗ trợ scheduler đặt Pod và trọng số chia sẻ | Cgroup quota giới hạn CPU time trong cấu hình Linux phổ biến | Container có thể bị throttle |
| Memory | Scheduler tính phần cần đặt chỗ | Cgroup memory limit | Có thể OOM kill container khi không thể cấp phát thêm |
| Ephemeral storage | Hỗ trợ scheduler tính nhu cầu local ephemeral storage | Kubelet có thể eviction khi vượt ngưỡng/limit theo cấu hình | Pod có thể bị eviction |

QoS class được xác định từ requests/limits của các container trong Pod:

- **Guaranteed:** các container có CPU và memory request bằng limit, với điều kiện cấu hình theo quy tắc Kubernetes.
- **Burstable:** có request/limit nhưng không đáp ứng điều kiện Guaranteed.
- **BestEffort:** không khai báo CPU/memory request và limit.

QoS ảnh hưởng thứ tự ưu tiên eviction khi node chịu memory pressure, nhưng không thay thế việc sizing container đúng. Pod Guaranteed vẫn có thể bị ảnh hưởng bởi giới hạn CPU quota hoặc các giới hạn khác.

### Quan sát Pod

Các lệnh đọc trạng thái thường dùng:

```bash
kubectl describe pod <pod-name> -n <namespace>
kubectl top pod <pod-name> -n <namespace> --containers
kubectl get events -n <namespace> --sort-by=.lastTimestamp
```

`kubectl top` phụ thuộc Metrics Server và thường cung cấp CPU/RAM usage gần thời điểm hiện tại, không thay thế lịch sử throttling, OOM hoặc I/O. `describe` và events giúp tìm restart reason, OOMKilled, eviction và cấu hình request/limit.

Để biết quota thực tế, cần quan sát cgroup trong container hoặc metric của node/runtime. Không suy ra CPU limit chỉ từ CPU usage.

## 12. Quan sát cgroup và hệ điều hành

Trên Linux cgroup v2, một số file thường được đọc để điều tra:

```bash
# CPU quota và thống kê throttling
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat

# Bộ nhớ và sự kiện giới hạn
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events

# I/O theo thiết bị
cat /sys/fs/cgroup/io.stat

# Áp lực tài nguyên ở cấp hệ thống
cat /proc/pressure/cpu
cat /proc/pressure/memory
cat /proc/pressure/io
```

Đây là ví dụ đường dẫn cgroup v2 khi process nằm ở root cgroup. Trong container thực tế, đường dẫn có thể nằm dưới một thư mục con hoặc mount namespace khác. Cgroup v1 dùng controller và file khác.

PSI (Pressure Stall Information) đo thời gian tác vụ bị stall do CPU, memory hoặc I/O contention. PSI giúp nhận diện áp lực ngay cả khi utilization trung bình chưa đạt 100%. Kernel và cấu hình cần hỗ trợ PSI.

### Phân biệt process metrics và cgroup metrics

- RSS của database process không nhất thiết bằng toàn bộ memory.current của container.
- CPU của process không bao gồm mọi hoạt động kernel hoặc sidecar trong cgroup.
- I/O của process có thể không phản ánh đầy đủ writeback hoặc I/O do kernel thực hiện thay mặt cgroup.
- Filesystem cache có thể được tính vào cgroup memory tùy cơ chế kernel.

Để điều tra OOM hoặc throttling, cgroup metrics thường quan trọng hơn việc chỉ xem process đơn lẻ.

## 13. Kết hợp database metrics với platform metrics

Không nên chỉ dùng dashboard database hoặc dashboard hạ tầng riêng lẻ. Hãy ghép chúng theo cùng cửa sổ thời gian và cùng workload.

| Triệu chứng ở database | Metric nền tảng cần đối chiếu | Hướng điều tra |
| --- | --- | --- |
| Query CPU time tăng, throughput giảm | CPU quota, throttled time, CPU PSI, VM steal | CPU limit hoặc host scheduling contention |
| Query latency tăng, process bị restart | memory.current, memory.events, OOMKilled, node memory pressure | Memory limit hoặc node pressure |
| Commit latency tăng | Log volume IOPS/latency, storage queue, service tier | Log flush hoặc storage throttling |
| Sequential scan chậm | Data volume throughput, bandwidth cap, queue depth | Storage bandwidth hoặc shared volume contention |
| Sort/hash spill tăng | Memory limit, memory pressure, query memory grant, temp volume | Thiếu memory headroom hoặc temp I/O chậm |
| Replication lag tăng | Network throughput/RTT, CPU và I/O replica | Giới hạn network hoặc replica resource |
| Connection wait tăng | Connection quota, pool size, CPU/memory per session | Quá nhiều session hoặc giới hạn dịch vụ |

Ví dụ, nếu p95 query latency tăng đúng lúc `nr_throttled` và `throttled_usec` tăng nhanh, có thể container đã chạm CPU quota. Nếu cùng lúc CPU host còn dư, tăng CPU limit hoặc điều chỉnh request có thể đáng thử; nhưng cần xác nhận quota thực tế và quyền phân bổ trên node.

Nếu commit latency tăng trong khi CPU và throttling ổn định, hãy kiểm tra log I/O latency, IOPS cap, queue depth và service events trước khi tối ưu SQL.

## 14. Tác động đến cấu hình database

Các tham số database phải được đặt trong ngân sách tài nguyên thực tế.

### CPU và parallelism

Database có thể tạo parallel worker cho query, index build, vacuum hoặc background task. Nếu container chỉ có quota 2 CPU nhưng query plan khởi chạy nhiều worker, các worker cạnh tranh cùng quota và có thể làm latency xấu hơn.

Kiểm tra giới hạn worker, parallelism, connection concurrency và CPU quota cùng lúc. Tăng số worker không tạo thêm CPU; nó chỉ chia sẻ cùng ngân sách.

### Memory và buffer pool

Buffer pool quá lớn có thể đẩy process khác hoặc kernel vào memory pressure. Buffer pool quá nhỏ có thể tăng physical reads. Tìm điểm cân bằng dựa trên memory limit, page cache, connection count và query memory.

Với PostgreSQL, cân nhắc `shared_buffers`, `work_mem`, `maintenance_work_mem` và số backend/parallel worker. Với MySQL, cân nhắc `innodb_buffer_pool_size` cùng memory theo connection. Với SQL Server, cân nhắc `max server memory` và memory grant. Luôn chừa headroom cho hệ điều hành và agent.

### Connection pool

Giới hạn tổng connection từ tất cả instance ứng dụng. Nếu mỗi instance có pool riêng, tính tổng số connection tối đa, session memory, worker và transaction đồng thời. Khi phù hợp, dùng pooler/proxy để giới hạn backend connection và tách client connection khỏi database session.

### Storage và checkpoint

Điều chỉnh checkpoint, flush, log file và temp storage theo IOPS/throughput được cấp. Tăng tốc độ background write quá cao có thể làm storage queue đầy; quá thấp có thể để backlog tích tụ. Cần theo dõi latency và khả năng drain thay vì chỉ tăng tham số.

## 15. Ví dụ tổng hợp: database bị giới hạn trong Kubernetes

Giả sử một Pod database có cấu hình:

```yaml
resources:
  requests:
    cpu: "2"
    memory: "8Gi"
  limits:
    cpu: "3"
    memory: "12Gi"
```

Node có 32 CPU logic và 128 GiB RAM, nhưng container chỉ có CPU limit 3 CPU và memory limit 12 GiB. Database không thể dùng toàn bộ tài nguyên node.

Dashboard cho thấy:

- CPU usage thường quanh 2,8–3 CPU.
- `cpu.stat` ghi nhận throttled periods tăng.
- Query p95 tăng trong giờ cao điểm.
- Memory.current đạt 11,7 GiB và memory.events ghi nhận `high` tăng, nhưng chưa có `oom_kill`.
- Storage volume có latency ổn định và còn IOPS.

Giả thuyết ban đầu là CPU quota và memory pressure, không phải storage. Các bước kiểm tra:

1. Xác nhận quota/period và tỷ lệ throttling theo cửa sổ thời gian.
2. Xem query fingerprint nào dùng CPU cao và actual plan có scan hoặc sort lớn không.
3. Kiểm tra parallel worker và tổng connection từ các ứng dụng.
4. Xem memory.stat để biết anonymous memory hay file cache đang chiếm nhiều.
5. Thử giảm concurrency hoặc tối ưu truy vấn trước; nếu workload thực sự cần thêm CPU, đánh giá tăng limit và request cùng khả năng node.
6. Benchmark lại p95/p99, throughput, throttling và memory peak.

Không kết luận chỉ từ việc usage gần 3 CPU. Cần xác nhận throttling, workload và các metric khác. Nếu node không đủ capacity hoặc scheduler không thể đặt Pod phù hợp, tăng limit có thể không đem lại tài nguyên thực tế.

## 16. Thiết kế benchmark trong môi trường có giới hạn

Benchmark phải chạy dưới cùng giới hạn tài nguyên mà workload production sẽ gặp. Nếu chạy trực tiếp trên host không có quota rồi triển khai vào container có limit, kết quả không đại diện.

Quy trình:

1. **Ghi lại cấu hình:** VM vCPU/RAM, container requests/limits, cgroup version, storage tier, IOPS/throughput, network cap và service tier.
2. **Chuẩn bị dữ liệu:** kích thước bảng, index, phân bố khóa, row width và dữ liệu cache đại diện.
3. **Chạy warm-up:** để buffer pool, connection pool và cache đạt trạng thái tương tự vận hành.
4. **Tăng tải theo bậc:** thay đổi concurrency hoặc offered load theo các bước, không nhảy ngay lên mức cực đại.
5. **Đo sustained load:** đủ lâu để thấy throttling, memory pressure, I/O cap hoặc burst credits.
6. **Lấy metric hai phía:** query latency/throughput cùng cgroup, VM, storage và network.
7. **Xác định điểm bão hòa:** nơi throughput không tăng tương ứng nhưng p95/p99, queue hoặc throttling tăng.
8. **Thay một yếu tố mỗi lần:** CPU limit, memory, batch size, index hoặc storage tier.
9. **Kiểm tra tính đúng:** số transaction commit, lỗi, OOM, restart và replication lag.
10. **Báo cáo cấu hình giới hạn:** nêu rõ kết quả đạt được trong đúng quota và tier.

Không chạy benchmark cạnh tranh với workload sản xuất trên cùng storage hoặc node nếu chưa có cửa sổ và kiểm soát phù hợp. Nhiều bài test cùng lúc có thể làm sai kết quả và ảnh hưởng người dùng.

## 17. Chẩn đoán theo triệu chứng

| Triệu chứng | Khả năng cần kiểm tra trước | Bằng chứng nên thu thập |
| --- | --- | --- |
| CPU usage đạt limit, query p99 tăng | CPU quota/throttling | `cpu.max`, `cpu.stat`, CPU PSI, query CPU time |
| CPU guest thấp nhưng VM chậm | Hypervisor scheduling/steal | steal time, CPU ready, host contention |
| Database restart bất thường | OOM hoặc node eviction | container status, `memory.events`, kernel log, node events |
| Sort/hash spill tăng | Memory budget quá thấp hoặc query grant không đủ | memory.current, memory.events, plan spill, work_mem/grant |
| Commit chậm, log flush wait tăng | Storage log IOPS/latency cap | log volume latency, queue, IOPS, service metrics |
| Scan lớn chậm | Storage throughput cap | bytes/s, read latency, queue depth, volume tier |
| Replication hoặc backup chậm | Network cap hoặc replica resource | RTT, bandwidth, retransmit, replica CPU/I/O |
| Connection timeout | Max connections, pool, service quota | active sessions, pool wait, provider connection limit |

Triệu chứng có thể có nhiều nguyên nhân đồng thời. Ví dụ CPU throttling làm query lâu hơn, kéo dài transaction và gián tiếp tăng lock wait. Cần xây timeline chung giữa database và platform metrics.

## 18. Các giới hạn và rủi ro khi tăng tài nguyên

Tăng quota có thể giải quyết nút thắt nhưng cũng có thể chuyển bottleneck sang lớp khác hoặc tạo chi phí mới.

- Tăng vCPU có thể làm storage trở thành giới hạn tiếp theo.
- Tăng memory limit mà không tăng memory request có thể làm scheduler đặt quá nhiều Pod lên node.
- Tăng memory limit nhưng không điều chỉnh database memory budget có thể không thay đổi buffer pool.
- Tăng CPU limit trên node đã quá tải có thể không đem lại CPU thực và làm tranh chấp nặng hơn.
- Tăng IOPS có thể tăng chi phí cloud; query vẫn chậm nếu CPU hoặc lock mới là nút thắt.
- Tăng max connections có thể tăng memory và scheduling overhead.
- Tăng network tier có thể không giúp truy vấn nếu bottleneck nằm ở query execution.

Trước khi scale, xác định metric nào đang chạm giới hạn và liệu workload có thể giảm công việc bằng index, projection, batching, cache hoặc query rewrite hay không.

## 19. Những sai lầm thường gặp

- **Dùng số CPU host làm quota database.** VM và container có thể chỉ được cấp một phần tài nguyên.
- **Nhầm CPU request với CPU limit.** Request hỗ trợ scheduling/weight; limit mới tạo quota cứng trong cấu hình phổ biến.
- **Chỉ nhìn CPU utilization trung bình.** Throttling và PSI có thể gây latency dù average không đạt 100%.
- **Cấp toàn bộ memory limit cho buffer pool.** Session, sort/hash, kernel, sidecar và page cache cũng cần bộ nhớ.
- **Tăng max_connections để xử lý queue.** Nhiều session hơn có thể làm CPU và RAM bão hòa nhanh hơn.
- **Cho rằng OOM chỉ xảy ra khi process RSS vượt limit.** Cgroup tính nhiều loại memory và có thể kill process trong nhóm.
- **Đồng nhất ephemeral storage với persistent volume IOPS.** Hai loại tài nguyên có quota và cơ chế khác nhau.
- **Chỉ đo throughput storage.** IOPS, latency, queue depth và burst credits cũng quan trọng.
- **Giả định managed database không có giới hạn OS.** Service tier vẫn có quota CPU, RAM, I/O, network và connection.
- **Tăng limit mà không kiểm tra node capacity.** Scheduler và hạ tầng có thể không cấp được tài nguyên tương ứng.
- **Benchmark trên host rồi triển khai vào container.** Hai môi trường có quota khác nhau nên kết quả không tương đương.
- **Chỉ xem dashboard database.** Cần liên hệ với cgroup, VM, storage, network và provider metrics.

## 20. Danh sách kiểm tra trước khi tối ưu tài nguyên

- [ ] Đã xác định các lớp vật lý, VM, container và managed service đang áp dụng.
- [ ] Đã ghi CPU request/limit, quota, weight và số vCPU thực tế.
- [ ] Đã theo dõi CPU throttling, PSI và VM steal/ready nếu có.
- [ ] Đã ghi memory request/limit, memory.current, memory.events và OOM history.
- [ ] Ngân sách database chừa headroom cho connection, worker, kernel và sidecar.
- [ ] Đã tính tổng connection pool từ mọi instance ứng dụng.
- [ ] Đã ghi storage capacity, IOPS, throughput, latency và burst policy.
- [ ] Đã phân biệt volume chứa log, data, temp và backup.
- [ ] Đã kiểm tra network bandwidth, RTT và replication traffic.
- [ ] Đã xác định service tier, quota và điều kiện autoscaling.
- [ ] Execution plan và database waits được đối chiếu với platform metrics.
- [ ] Benchmark chạy dưới cùng giới hạn tài nguyên với môi trường mục tiêu.
- [ ] Đã đo sustained throughput, p95/p99 và các sự kiện throttle/OOM/I/O cap.
- [ ] Có kế hoạch scale hoặc giảm tải dựa trên nút thắt đã xác nhận.

## Kết luận

Máy ảo, container và dịch vụ cơ sở dữ liệu được quản lý có thể giới hạn CPU, bộ nhớ, I/O, mạng và số kết nối ở nhiều lớp. vCPU không bảo đảm CPU vật lý riêng; CPU quota có thể throttle; memory limit có thể dẫn đến OOM kill; storage tier có thể giới hạn IOPS hoặc throughput; managed service có thể áp dụng quota mà người dùng không nhìn thấy ở cấp hệ điều hành. Hãy đối chiếu execution plan và database waits với cgroup, VM, storage, network và service metrics. Lập ngân sách cho buffer pool, session và query workspace trong memory limit, benchmark dưới đúng quota và xác định điểm bão hòa bằng throughput cùng p95/p99. Chỉ tăng tài nguyên sau khi đã xác nhận lớp giới hạn thực sự gây ra nút thắt.

# Đánh giá giới hạn phần cứng, capacity và khả năng quan sát tại biên

## Mục tiêu bài học

Hệ thống điện toán biên (edge computing) đặt năng lực xử lý gần thiết bị, người dùng hoặc nguồn dữ liệu để giảm độ trễ, tiết kiệm băng thông và duy trì một phần chức năng khi kết nối cloud không ổn định. Tuy nhiên, node biên thường có giới hạn vật lý chặt hơn máy chủ trung tâm: CPU và bộ nhớ nhỏ, storage có dung lượng và độ bền ghi hữu hạn, network chập chờn, nguồn điện và làm mát không đồng đều, phần cứng có nhiều thế hệ và kiến trúc khác nhau.

Capacity tại biên vì vậy phải được đánh giá theo từng site, từng loại thiết bị và điều kiện vận hành thực tế. Khả năng quan sát cũng cần hoạt động khi đường truyền về cloud bị gián đoạn: node phải thu thập và lưu telemetry cục bộ, ưu tiên dữ liệu quan trọng, đồng bộ lại có kiểm soát và cho phép phân biệt một thiết bị mất kết nối với một thiết bị đã hỏng.

Sau bài học này, bạn có thể:

- Lập danh mục giới hạn CPU, GPU/NPU, RAM, storage, network, power và thermal của node biên.
- Đo hiệu năng bền vững trong điều kiện nhiệt độ và tải thực tế.
- Ước lượng capacity theo site, giờ cao điểm, failure domain và chế độ offline.
- Tính headroom cho dự phòng, buffer dữ liệu và telemetry.
- Phân loại workload cần chạy tại biên, tại gateway và trên cloud.
- Thiết kế observability local-first với metrics, logs, traces và store-and-forward.
- Xử lý clock drift, network partition, telemetry backlog và thiết bị không đồng bộ.
- Theo dõi sức khỏe fleet, cấu hình, phiên bản và mức sử dụng tài nguyên.
- Kiểm thử tình huống mất mạng, mất nguồn, quá nhiệt, đầy storage và hỏng node.

## 1. Vì sao đánh giá capacity tại biên khác cloud?

Cloud region thường có nhiều máy chủ đồng nhất, nguồn điện và làm mát được quản lý tập trung, network băng thông cao và hệ thống monitoring liên tục. Ở biên, tài nguyên có thể nằm trong cửa hàng, nhà máy, trạm viễn thông, phương tiện, bệnh viện hoặc tủ thiết bị ngoài trời. Mỗi site có điều kiện khác nhau.

Các đặc điểm thường gặp:

- Phần cứng có nhiều thế hệ CPU, kiến trúc và accelerator.
- Thiết bị có giới hạn công suất điện, nhiệt độ và khả năng làm mát.
- RAM và storage nhỏ hơn, đôi khi dùng flash có giới hạn endurance.
- Network về cloud có độ trễ cao, băng thông hạn chế hoặc mất kết nối.
- Thiết bị có thể chạy offline trong một khoảng thời gian.
- Việc thay thế, reboot hoặc truy cập vật lý cần nhân sự tại site.
- Dữ liệu có thể nhạy cảm và phải được xử lý tại chỗ.
- Telemetry phải được lưu cục bộ khi uplink không khả dụng.

Do đó, một cấu hình chạy tốt trong phòng lab có thể không đáp ứng được khi triển khai hàng trăm site. Đánh giá cần kết hợp benchmark phần cứng, đo tải thật, điều kiện môi trường và khả năng phục hồi khi mất kết nối.

### 1.1. Các lớp tài nguyên tại biên

Một site có thể gồm:

- **Endpoint:** camera, cảm biến, thiết bị IoT hoặc máy công nghiệp tạo dữ liệu.
- **Edge gateway:** thu thập, lọc, chuyển đổi giao thức và xử lý nhẹ.
- **Edge server:** chạy container, inference, stream processing hoặc ứng dụng tại site.
- **Site network:** switch, router, Wi-Fi, 5G hoặc kết nối chuyên dụng.
- **Cloud control plane:** quản lý cấu hình, fleet, model, policy và telemetry tập trung.

Không phải mọi site đều có đủ các lớp này. Một thiết bị gateway có thể vừa thu thập dữ liệu vừa chạy ứng dụng; một nhà máy có thể có nhiều edge server và một cụm local cluster.

~~~mermaid
flowchart LR
    E["Sensors / cameras / machines"] --> G["Edge gateway"]
    G --> N["Site network"]
    N --> S["Edge compute nodes"]
    S --> L["Local storage / local services"]
    S --> C["Cloud control plane"]
    L --> C
    C --> M["Fleet management and analytics"]
~~~

Thiết kế phải xác định rõ thành phần nào tiếp tục hoạt động khi đường nối từ site tới cloud bị mất. Nếu gateway chỉ forward mọi request lên cloud, nó chưa cung cấp khả năng vận hành offline cho ứng dụng phụ thuộc cloud.

## 2. Lập danh mục phần cứng trước khi sizing

Bước đầu tiên là inventory chính xác phần cứng tại từng site. Không dùng tên model chung hoặc thông số quảng cáo làm dữ liệu duy nhất.

Các trường inventory nên có:

| Nhóm | Thông tin cần ghi |
|---|---|
| Thiết bị | Manufacturer, model, serial/asset ID, site và vị trí |
| CPU | Architecture, model, core/thread, frequency, instruction set |
| RAM | Dung lượng, loại, băng thông và khả năng nâng cấp |
| GPU/NPU | Model, VRAM/on-chip memory, driver và runtime |
| Storage | Loại media, dung lượng, IOPS/throughput, endurance |
| Network | NIC, link speed, Wi-Fi/5G, latency và packet loss |
| Power | Nguồn cấp, mức tiêu thụ, UPS và thời gian lưu điện |
| Thermal | Dải nhiệt độ vận hành, cooling, sensor và throttling limit |
| OS/runtime | OS image, kernel, container runtime, accelerator runtime |
| Lifecycle | Firmware, warranty, support status và lịch thay thế |

Gắn inventory với site ID và hardware revision. Hai node có cùng tên model nhưng khác RAM, SSD, firmware hoặc NIC có thể có capacity khác nhau.

### 2.1. Phân nhóm phần cứng

Có thể phân nhóm node thành các hardware profile để lập kế hoạch và triển khai:

- Gateway tiết kiệm điện, CPU/RAM nhỏ.
- Edge server general-purpose.
- Node có GPU/NPU cho computer vision hoặc inference.
- Node storage-intensive cho buffering và local retention.
- Node ruggedized cho môi trường nhiệt độ, rung hoặc bụi cao.

Profile cần mô tả cả năng lực lẫn giới hạn. Không đưa workload GPU lên node chỉ vì node có accelerator; phải kiểm tra driver, runtime, model format, memory và throughput thực tế.

### 2.2. Theo dõi độ không đồng nhất

Fleet có thể chứa node cùng loại nhưng khác phiên bản firmware hoặc runtime. Hãy ghi nhận:

- Hardware profile và revision.
- BIOS/UEFI và firmware version.
- OS/kernel và container runtime version.
- GPU/NPU driver và inference runtime.
- Image digest của ứng dụng.
- Cấu hình CPU governor, power mode và thermal policy.

Nếu cùng một workload có latency khác nhau giữa các node, metadata này giúp xác định khác biệt do phần cứng, phiên bản phần mềm hay điều kiện môi trường.

## 3. Đánh giá giới hạn CPU

CPU tại biên có thể bị giới hạn bởi số core, kiến trúc, xung nhịp, cache, memory bandwidth, công suất điện và nhiệt độ. Chỉ đếm core không phản ánh đầy đủ năng lực.

Các yếu tố cần kiểm tra:

- Số core vật lý và logical thread.
- Kiến trúc x86-64 hoặc Arm và instruction set.
- Hiệu năng single-thread và multi-thread.
- Cache L1/L2/L3 và memory bandwidth.
- CPU frequency scaling và power governor.
- Thermal throttling khi chạy tải liên tục.
- CPU quota nếu ứng dụng chạy trong container.
- Mức tranh chấp với OS, agent, telemetry và workload khác.

### 3.1. Benchmark theo workload thật

Dùng workload đại diện thay vì chỉ dựa vào benchmark tổng quát. Ví dụ:

- Decode video theo số luồng camera.
- Parse và lọc message từ cảm biến.
- Chạy inference trên model thực tế.
- Mã hóa, nén hoặc chuyển đổi dữ liệu.
- Xử lý stream với kích thước batch tương đương production.

Đo throughput, p50/p95/p99 latency, CPU utilization, run queue và throttling. Chạy đủ lâu để quan sát nhiệt độ ổn định; benchmark ngắn có thể chỉ đo hiệu năng turbo trong vài phút đầu.

### 3.2. Hiệu năng bền vững và thermal throttling

Thiết bị fanless hoặc đặt trong tủ kín có thể giảm xung nhịp khi nhiệt độ tăng. Công suất CPU ở trạng thái turbo không nhất thiết duy trì được trong cả ca vận hành.

Nên đo:

- Nhiệt độ CPU và ambient temperature.
- Tần số thực tế trong suốt bài test.
- Thời gian và tỷ lệ throttling.
- Throughput khi thiết bị đã nóng ổn định.
- Hiệu năng khi các thành phần khác như GPU, SSD và NIC cùng hoạt động.

Capacity planning nên dùng hiệu năng bền vững trong điều kiện môi trường xấu nhưng vẫn nằm trong dải vận hành được hỗ trợ. Không sizing theo peak ngắn hạn rồi kỳ vọng node luôn duy trì mức đó.

### 3.3. CPU headroom

Không nên phân bổ toàn bộ CPU cho ứng dụng nghiệp vụ. Node cần tài nguyên cho:

- OS và system services.
- Container runtime hoặc orchestration agent.
- Security, inventory và device management agent.
- Telemetry collector.
- Network stack và protocol gateway.
- Buffering, compression và background update.

Một cách ước lượng:

~~~text
CPU budget cho workload =
  CPU capacity bền vững
  - OS và system services
  - security/management agents
  - observability
  - dự phòng cho burst và recovery
~~~

Đo phần overhead của agent trên node đại diện. Một telemetry collector có thể tiêu thụ CPU đáng kể khi uplink phục hồi và phải gửi backlog lớn.

## 4. GPU, NPU và accelerator

Edge AI thường dùng GPU rời, GPU tích hợp hoặc NPU chuyên dụng. Năng lực accelerator không thể so sánh chỉ bằng số TOPS được quảng cáo.

Cần kiểm tra:

- Model accelerator và precision được hỗ trợ.
- VRAM hoặc on-chip memory.
- Memory bandwidth và tốc độ truyền giữa host/device.
- Driver, firmware và inference runtime.
- Hỗ trợ framework và model operator.
- Batch size và concurrency thực tế.
- Power draw và thermal envelope.
- Khả năng chạy nhiều model đồng thời.
- Hành vi khi accelerator reset hoặc mất thiết bị.

### 4.1. Benchmark inference

Đo trên model đã quantize hoặc compile đúng như production. Ghi lại:

- Requests hoặc frames per second.
- p50/p95/p99 inference latency.
- Accelerator utilization và memory usage.
- CPU utilization cho preprocessing/postprocessing.
- Thời gian load model.
- Throughput khi nhiều camera hoặc stream đồng thời.
- Hiệu năng sau nhiều giờ chạy liên tục.

Một NPU có throughput cao nhưng thiếu operator được model sử dụng có thể buộc một phần graph chạy trên CPU. Kết quả thực tế thấp hơn nhiều so với thông số lý thuyết.

### 4.2. Phân bổ model theo node

Nếu nhiều ứng dụng cùng dùng accelerator, cần scheduler hoặc resource manager biết giới hạn device. Tránh để nhiều process cùng cấp phát toàn bộ VRAM hoặc memory pool dẫn tới OOM.

Có thể:

- Chạy một model server chia sẻ accelerator.
- Phân vùng accelerator nếu phần cứng/runtime hỗ trợ.
- Đặt concurrency và batch limit.
- Ưu tiên inference quan trọng theo SLO.
- Chuyển workload ít ưu tiên sang cloud khi có kết nối.

## 5. Đánh giá RAM và memory pressure

RAM tại biên thường nhỏ và không dễ nâng cấp sau khi triển khai. Memory cần cho ứng dụng, model, cache, runtime, OS, telemetry buffer và các process hỗ trợ.

Lập ngân sách:

~~~text
RAM tổng cần thiết =
  OS và system services
  + runtime/container overhead
  + application working set
  + model/accelerator staging buffers
  + cache và queue buffers
  + observability/security agents
  + safety headroom
~~~

Không dùng tổng memory của process ở trạng thái idle để sizing. Đo working set ở peak, khi cache nóng, khi batch lớn và khi network reconnect.

### 5.1. Memory pressure và OOM

Dấu hiệu memory pressure:

- Available memory giảm liên tục.
- Swap hoặc zram hoạt động mạnh.
- Major page fault tăng.
- Process bị OOM kill.
- Container restart hoặc ứng dụng giảm throughput.
- Kernel reclaim làm latency tăng.

Swap có thể giúp hấp thụ burst nhỏ, nhưng trên thiết bị edge có storage flash và latency nghiêm ngặt, swap nặng có thể làm tăng I/O và giảm tuổi thọ storage. Không coi swap là phần RAM thay thế trong capacity plan.

### 5.2. Giới hạn container

Khi chạy container, đặt memory request/limit hoặc cgroup limit phù hợp. Nếu limit thấp hơn peak working set, process có thể bị OOM kill ngay cả khi host vẫn còn RAM dành cho workload khác.

Với Java, tính cả heap, metaspace, thread stacks, direct buffers, code cache và native libraries. Với inference runtime, tính memory của model, tensor, preprocessing và driver.

### 5.3. Headroom cho reconnect

Khi mạng trở lại, node có thể đồng thời:

- Gửi backlog telemetry.
- Đồng bộ cấu hình và inventory.
- Tải model hoặc image mới.
- Xử lý event tồn đọng.
- Khởi tạo kết nối tới cloud service.

Những hoạt động này tạo memory burst. Capacity plan cần kiểm tra tình huống reconnect, không chỉ tải bình thường khi uplink ổn định.

## 6. Storage, endurance và local buffering

Storage tại biên có thể là eMMC, SD card, SATA SSD, NVMe hoặc network-attached volume. Các loại này khác nhau về throughput, latency, endurance, power-loss behavior và khả năng thay thế.

Cần đánh giá:

- Dung lượng usable sau OS, partition và reserved space.
- Sequential/random read-write throughput.
- IOPS và tail latency.
- Endurance/TBW hoặc giới hạn ghi theo nhà sản xuất.
- Wear level và media error.
- Power-loss protection nếu có.
- Filesystem và journaling behavior.
- Khả năng thay ổ và phục hồi sau hỏng.
- Nhiệt độ vận hành và ảnh hưởng tới hiệu năng.

### 6.1. Ước lượng dung lượng offline buffer

Giả sử node tạo dữ liệu với tốc độ trung bình R bytes/second và cần lưu trong thời gian mất kết nối T seconds. Dung lượng buffer tối thiểu theo mô hình đơn giản:

~~~text
Buffer bytes = R * T * safetyFactor
~~~

Nếu có nhiều loại dữ liệu, tính riêng theo retention và mức ưu tiên. Ví dụ telemetry metric có thể được aggregate hoặc drop có kiểm soát, còn event nghiệp vụ cần được giữ đầy đủ.

Cần tính thêm:

- Metadata và index.
- Compression ratio thực tế.
- Filesystem overhead và reserved space.
- Burst rate thay vì chỉ average rate.
- Retry khi gửi backlog.
- Dung lượng cần cho image/model update.
- Log và crash dump.
- Headroom để hệ thống không chạm 100% disk.

### 6.2. Storage endurance

Nếu node ghi liên tục telemetry, video clip, queue spool và log, lượng ghi có thể làm hao mòn flash.

Ước lượng daily writes:

~~~text
Daily writes =
  average write throughput * seconds per day
~~~

So sánh lượng ghi theo ngày/năm với endurance của thiết bị, có tính write amplification và workload thực tế. Giảm ghi không cần thiết bằng cách:

- Batch và buffer write.
- Dùng log rotation.
- Aggregate metric trước khi persist.
- Đặt retention cho dữ liệu tạm.
- Không ghi log debug liên tục.
- Chuyển dữ liệu dài hạn lên storage bền vững khi có kết nối.

Không xóa dữ liệu chưa được xác nhận gửi thành công. Store-and-forward cần trạng thái delivery hoặc sequence/ack rõ ràng.

### 6.3. Phân vùng dữ liệu

Tách dung lượng theo mục đích:

- OS và system update.
- Container image và model cache.
- Application state.
- Queue/offline spool.
- Logs, metrics và traces.
- Temporary files và crash dump.

Đặt quota hoặc giới hạn cho từng nhóm để log không chiếm hết dung lượng dành cho queue nghiệp vụ. Dành vùng dự phòng cho update/rollback image nếu thiết bị cần giữ cả phiên bản hiện tại và phiên bản trước.

## 7. Network và khả năng vận hành offline

Edge network có thể gồm Ethernet, Wi-Fi, cellular, private APN, satellite hoặc kết nối công nghiệp. Băng thông và độ ổn định có thể thay đổi theo site, thời gian và môi trường.

Các giới hạn cần đo:

- Uplink/downlink throughput.
- RTT và p95/p99 latency.
- Packet loss, jitter và reconnect frequency.
- NAT, firewall và proxy behavior.
- DNS resolution time.
- MTU và fragmentation.
- Chi phí data transfer.
- Giới hạn connection và API rate.
- Thời gian mất kết nối liên tục dài nhất.

### 7.1. Phân loại luồng dữ liệu

Không phải dữ liệu nào cũng cần gửi ngay về cloud. Phân loại theo mục đích:

| Loại dữ liệu | Chính sách tại biên |
|---|---|
| Điều khiển an toàn/critical | Xử lý local, không phụ thuộc cloud round trip |
| Event nghiệp vụ quan trọng | Persist, retry và xác nhận delivery |
| Telemetry vận hành | Aggregate, buffer và gửi theo batch |
| Video/raw sensor data | Lọc hoặc chỉ gửi clip/segment cần thiết |
| Debug/verbose logs | Sampling, quota và retention ngắn |
| Model/config update | Kiểm tra chữ ký, version và tải theo cửa sổ phù hợp |

Thiết kế phải giữ được chức năng cần thiết khi cloud không truy cập được. Không để control loop có yêu cầu thời gian thực phụ thuộc vào một API ở region xa.

### 7.2. Store-and-forward

Store-and-forward cho phép node ghi dữ liệu vào spool cục bộ khi uplink gián đoạn, rồi gửi lại khi kết nối phục hồi.

Một luồng cơ bản:

1. Producer tạo record có ID/sequence ổn định.
2. Edge service ghi record bền vững vào local spool.
3. Worker gửi record lên cloud theo batch.
4. Cloud xác nhận record đã được nhận hoặc commit.
5. Edge chỉ đánh dấu hoàn tất sau acknowledgment tương ứng.
6. Cleanup record theo retention sau khi xác nhận.

Nếu kết nối bị ngắt sau khi cloud đã commit nhưng trước khi edge nhận ack, record có thể được gửi lại. Cloud consumer cần idempotency theo event ID hoặc sequence.

### 7.3. Backpressure và giới hạn buffer

Nếu uplink trở lại nhưng tốc độ gửi backlog lớn hơn khả năng xử lý của cloud, backlog có thể không giảm. Đặt giới hạn:

- Maximum spool bytes.
- Maximum record age.
- Maximum upload concurrency.
- Maximum bandwidth cho replay.
- Ưu tiên event critical.
- Chính sách drop/aggregate cho telemetry ít quan trọng.
- Cảnh báo khi buffer đạt các ngưỡng 60%, 80% và 95% hoặc ngưỡng phù hợp.

Khi buffer gần đầy, giảm dữ liệu không thiết yếu trước. Không âm thầm loại bỏ event quan trọng; phải có metric và audit cho mọi quyết định drop.

## 8. Capacity planning theo site

Sizing ở biên nên tính theo từng site, không chỉ theo tổng fleet. Một site có 20 camera và uplink yếu khác với site có 4 camera nhưng inference model lớn.

### 8.1. Tính throughput cần phục vụ

Giả sử một node xử lý bền vững được P units/second khi vẫn đáp ứng SLO. Tải peak của site là L units/second.

Số node active tối thiểu:

~~~text
N_active = ceil(L / P)
~~~

Đây là ước lượng đơn giản. Cần điều chỉnh theo concurrency, workload mix, resource bottleneck và hiệu năng giảm khi nhiều node cùng chia sẻ network/storage.

Nếu cần chịu lỗi một node mà không giảm throughput dưới SLO, capacity còn lại sau khi mất node phải đủ phục vụ tải. Với node đồng nhất:

~~~text
N_total >= N_active + 1
~~~

Nếu node khác cấu hình, dùng năng lực đo được của từng node thay vì đếm số máy.

### 8.2. Tính headroom

Headroom là phần capacity còn trống để hấp thụ burst, reconnect, failover và tăng trưởng. Không nên chạy node ở mức 95-100% CPU/RAM liên tục rồi kỳ vọng có thể phục hồi khi một node khác mất.

Xác định headroom theo:

- Mức tăng tải ngắn hạn.
- Thời gian cần để khởi động node thay thế.
- Khả năng chuyển workload giữa node.
- Tải nền của system agent và telemetry.
- Nhiệt độ môi trường cao.
- Dung lượng buffer khi offline.
- Mức sai số của benchmark.

Một node có 30% CPU free nhưng đã hết RAM hoặc storage vẫn không có headroom hữu ích. Theo dõi từng tài nguyên riêng và xác định resource bottleneck.

### 8.3. Ví dụ capacity tại một site

Giả sử site có 18 camera, mỗi camera tạo 12 frame/second cần inference. Benchmark cho thấy một edge node xử lý bền vững 90 frame/second trong điều kiện nhiệt độ cao mà vẫn đạt latency mục tiêu.

~~~text
Peak workload = 18 * 12 = 216 frames/second
N_active = ceil(216 / 90) = 3 nodes
N_total for N-1 node failure = 4 nodes
~~~

Bốn node là điểm khởi đầu cho yêu cầu chịu lỗi một node theo mô hình này. Cần xác minh network, storage, GPU memory, power và khả năng phân phối stream. Nếu một node lỗi khiến camera stream không thể chuyển sang node khác, thêm compute chưa đủ; cần thiết kế routing và failover.

### 8.4. Tính capacity khi offline

Nếu cloud unavailable, site cần biết những workload nào tiếp tục chạy và trong bao lâu.

Xác định:

- Workload bắt buộc chạy local.
- Workload có thể giảm chất lượng hoặc sampling.
- Workload có thể tạm dừng.
- Dung lượng queue/spool cần thiết.
- Model/config version được cache tại chỗ.
- Thời gian offline mục tiêu.
- Điều kiện an toàn khi local storage gần đầy.

Không giả định node có thể offline vô hạn. Nếu retention cần 72 giờ nhưng dung lượng spool chỉ giữ được 8 giờ, hệ thống phải có policy degraded mode hoặc local alert trước khi hết dung lượng.

## 9. Phân bổ workload giữa endpoint, gateway, edge server và cloud

Một cách tối ưu capacity là đặt mỗi tác vụ ở lớp phù hợp.

| Lớp | Workload phù hợp | Ràng buộc |
|---|---|---|
| Endpoint | Filtering đơn giản, sampling, control loop nhỏ | CPU/RAM/energy rất hạn chế |
| Gateway | Protocol conversion, aggregation, local queue, device auth | Network interface và storage giới hạn |
| Edge server | Inference, stream processing, local API, cache | Compute/GPU, cooling và site operations |
| Cloud | Fleet analytics, training, global coordination, long-term storage | Network latency, data transfer và connectivity |

Có thể xử lý dữ liệu theo pipeline: lọc ở endpoint, aggregate tại gateway, inference tại edge server và tổng hợp dài hạn ở cloud.

Tránh gửi toàn bộ raw data lên cloud nếu mục tiêu là giảm bandwidth hoặc bảo vệ dữ liệu. Tuy nhiên, giữ quá nhiều logic tại edge làm tăng số phiên bản phần mềm, khó rollout và khó debug. Chọn ranh giới theo latency, privacy, offline requirement và chi phí vận hành.

## 10. Quan sát tại biên: local-first observability

Observability tại edge phải hoạt động ngay cả khi cloud không truy cập được. Nếu mọi metric, log và trace chỉ được gửi trực tiếp về cloud, operator sẽ mất khả năng quan sát đúng lúc site gặp network partition.

Một kiến trúc thường có:

- Application phát metrics, logs và traces.
- Local collector nhận telemetry từ các process trên node.
- Local buffer giữ dữ liệu khi uplink mất.
- Site gateway hoặc aggregator gom dữ liệu từ nhiều node.
- Remote collector/cloud backend nhận dữ liệu khi kết nối phục hồi.
- Fleet management tổng hợp health và trạng thái phiên bản.

~~~mermaid
flowchart LR
    A["Apps and devices"] --> C["Local telemetry collector"]
    C --> B["Persistent local buffer"]
    B --> G["Site gateway / aggregator"]
    G -->|Connected| R["Cloud observability backend"]
    G -->|Disconnected| Q["Retain and retry"]
    Q --> G
    R --> F["Fleet dashboards and alerts"]
~~~

Local observability cần có dashboard hoặc diagnostic endpoint tại site để kỹ thuật viên có thể kiểm tra node khi không có internet. Nếu site không có người vận hành thường trực, local buffer và heartbeat khi kết nối trở lại càng quan trọng.

## 11. Metrics tại edge

Metrics cần trả lời ba nhóm câu hỏi:

1. Node và phần cứng có khỏe không?
2. Workload có đáp ứng SLO không?
3. Site có đủ capacity và khả năng đồng bộ không?

Các metric nên có:

| Nhóm | Metric ví dụ |
|---|---|
| CPU | utilization, load, run queue, frequency, throttling |
| Memory | available, working set, swap, OOM count |
| Accelerator | utilization, memory, temperature, inference latency |
| Storage | free bytes, write throughput, I/O latency, wear level |
| Network | throughput, RTT, loss, reconnects, DNS failures |
| Thermal/power | CPU temperature, device temperature, power draw, UPS state |
| Application | request rate, error rate, p95/p99 latency, queue depth |
| Offline buffer | spool bytes, oldest record age, pending count, drop count |
| Fleet | heartbeat age, software version, config drift, update status |
| Telemetry | collector queue, export failures, dropped telemetry |

### 11.1. Metric labels và cardinality

Node ID, site ID và hardware profile có thể cần để lọc dashboard. Tuy nhiên, không gắn mọi event ID, serial number hoặc request ID làm label metric có cardinality cao.

Một cách tổ chức:

- Metric label ổn định: site group, hardware profile, application, version và zone.
- Node identity: lưu trong resource attributes hoặc inventory backend.
- Event/request ID: lưu trong log và trace.
- Fleet aggregation: tổng hợp theo site và profile trước khi gửi cloud.

Nếu có hàng chục nghìn node, metric mỗi node có thể tạo lượng time series lớn. Cần sampling, aggregation và retention phù hợp với chi phí backend.

### 11.2. Baseline theo hardware profile

Không áp một ngưỡng CPU hoặc temperature cho mọi node. Một gateway low-power có baseline khác edge server GPU.

Thiết lập baseline theo profile và môi trường:

- CPU utilization bình thường theo workload.
- Nhiệt độ ổn định và ngưỡng throttling.
- Memory working set.
- Disk wear và tốc độ tăng dung lượng.
- Network RTT và loss bình thường tại site.
- Thời gian khởi động và model load.

Phát hiện bất thường nên so sánh node với nhóm tương đương, đồng thời giữ ngưỡng tuyệt đối cho điều kiện nguy hiểm như disk full hoặc nhiệt độ vượt giới hạn thiết bị.

## 12. Logs và traces khi kết nối không ổn định

Logs và traces thường lớn hơn metrics. Nếu giữ tất cả trong local storage, buffer có thể đầy nhanh.

### 12.1. Logging

Thiết kế logging tại edge nên có:

- Structured logs với timestamp, site ID, node ID và correlation ID.
- Mức log theo môi trường và workload.
- Rotation theo dung lượng và thời gian.
- Quota riêng cho từng ứng dụng.
- Sampling hoặc rate limit cho lỗi lặp.
- Mask dữ liệu nhạy cảm.
- Local retention và upload policy.
- Audit log không bị loại bỏ theo policy thông thường.

Khi uplink mất, log quan trọng cần được giữ lại. Debug log có thể bị giảm hoặc drop theo ngưỡng, nhưng hành động đó phải được ghi nhận bằng metric để operator biết dữ liệu quan sát đã bị suy giảm.

### 12.2. Distributed tracing

Một request có thể đi qua endpoint, gateway, edge server và cloud. Trace context giúp liên kết các span qua nhiều lớp.

Nếu site offline, span có thể được lưu trong local buffer và export sau. Thời gian export muộn không nên làm thay đổi timestamp gốc của span. Cần giữ trace ID, span ID và parent context khi chuyển qua queue hoặc protocol.

Không phải mọi event đều cần trace đầy đủ. Sampling theo loại request, lỗi và mức ưu tiên giúp kiểm soát storage và network.

### 12.3. Tương quan log, metric và trace

Dùng cùng correlation/trace ID ở các thành phần liên quan để điều tra request lỗi. Không dùng ID ngẫu nhiên làm metric label; ID thuộc log/trace.

Khi thiết bị mất đồng bộ thời gian, correlation ID và sequence number giúp ghép sự kiện tốt hơn timestamp đơn lẻ.

## 13. Clock drift và timestamp tại edge

Node biên có thể mất NTP/PTP hoặc không có nguồn thời gian chính xác khi offline. Clock drift làm timestamp giữa các node lệch nhau, ảnh hưởng thứ tự event, trace và điều tra sự cố.

Các biện pháp:

- Đồng bộ thời gian khi có kết nối.
- Dùng nguồn thời gian nội bộ tại site nếu cần.
- Ghi cả wall-clock timestamp và monotonic duration trong process.
- Giữ sequence number hoặc logical counter cho event.
- Ghi trạng thái đồng bộ và độ lệch ước lượng.
- Không dựa hoàn toàn vào timestamp để deduplicate hoặc sắp xếp event.
- Xử lý event đến trễ khi đồng bộ lại.

Với hệ thống phân tán, timestamp từ hai node không nhất thiết xác định chính xác thứ tự nhân quả. Dùng sequence, version hoặc protocol ordering khi thứ tự nghiệp vụ quan trọng.

## 14. Buffer telemetry và store-and-forward

Local collector cần buffer telemetry để không mất toàn bộ dữ liệu khi cloud unavailable. Buffer có thể nằm trong memory hoặc persistent storage.

Memory buffer nhanh nhưng mất khi process/node restart. Persistent buffer bền hơn nhưng tiêu thụ disk và có thể ảnh hưởng storage endurance.

### 14.1. Ưu tiên dữ liệu

Một chính sách ưu tiên có thể là:

1. Security/audit và event vận hành quan trọng.
2. Error logs và health transitions.
3. Metrics SLO và capacity.
4. Traces được chọn mẫu.
5. Debug logs và telemetry chi tiết ít ưu tiên.

Khi buffer đầy, loại dữ liệu ưu tiên thấp trước theo policy. Không xóa audit hoặc event nghiệp vụ quan trọng nếu chưa có phương án lưu trữ khác.

### 14.2. Bounded queue

Buffer phải có giới hạn rõ:

- Maximum bytes.
- Maximum age.
- Maximum record count.
- Disk quota.
- Export concurrency.
- Retry backoff.
- Drop policy.
- Alert threshold.

Nếu queue không giới hạn, một site offline dài ngày có thể làm đầy disk và khiến ứng dụng nghiệp vụ dừng. Nếu queue quá nhỏ, telemetry sẽ mất ngay khi uplink chập chờn.

### 14.3. Reconnect storm

Khi kết nối trở lại, hàng trăm node có thể cùng gửi telemetry backlog và tải model/config. Điều này có thể làm nghẽn uplink site, cloud ingestion hoặc API control plane.

Giảm rủi ro bằng cách:

- Jitter thời điểm reconnect và export.
- Giới hạn bandwidth/concurrency theo node và site.
- Ưu tiên dữ liệu quan trọng và dữ liệu mới.
- Gửi batch có kích thước giới hạn.
- Dùng backoff khi cloud trả throttling.
- Tách telemetry export khỏi traffic điều khiển.
- Theo dõi backlog age và tốc độ drain.

Không xả toàn bộ backlog nhanh nhất có thể nếu nó làm ảnh hưởng traffic nghiệp vụ hiện tại.

## 15. Fleet health và khả năng quan sát từ xa

Một hệ thống edge cần quản lý hàng nghìn thiết bị ở nhiều site. Dashboard fleet nên cho biết node nào online, node nào stale, node nào degraded và node nào có nguy cơ mất capacity.

Các trạng thái vận hành có thể gồm:

- **Healthy:** heartbeat mới, resource trong ngưỡng, workload ready.
- **Degraded:** vẫn phục vụ nhưng có resource pressure, thermal throttling hoặc telemetry loss.
- **Disconnected:** không nhận heartbeat trong ngưỡng; chưa thể kết luận thiết bị đã hỏng.
- **Unhealthy:** có tín hiệu lỗi cục bộ rõ ràng hoặc workload không phục vụ.
- **Maintenance:** node đang được bảo trì hoặc nâng cấp có kế hoạch.
- **Quarantined:** node bị cách ly vì lỗi bảo mật hoặc cấu hình.

Phân biệt disconnected và unhealthy rất quan trọng. Một node offline có thể vẫn đang chạy ứng dụng tại site; cloud control plane chỉ không quan sát được nó.

### 15.1. Heartbeat và last-seen

Heartbeat nên có:

- Node ID và site ID.
- Boot ID hoặc execution generation.
- Timestamp và sequence number.
- Application/runtime version.
- Health summary.
- Resource summary.
- Connectivity state.

Dùng heartbeat interval và timeout phù hợp với network thực tế. Nếu đặt timeout quá ngắn, cellular jitter có thể làm fleet dashboard báo false offline. Nếu quá dài, phát hiện sự cố chậm.

### 15.2. Configuration drift

Theo dõi cấu hình mong muốn và cấu hình thực tế:

- OS/kernel/firmware version.
- Container image digest.
- Runtime và driver version.
- Model/config version.
- Network policy và certificate expiry.
- Resource limit và service state.

Một node có thể online nhưng chạy cấu hình cũ hoặc policy bảo mật không còn hợp lệ. Fleet health cần phản ánh cả connectivity lẫn configuration compliance.

## 16. Security và quyền riêng tư của telemetry

Edge thường xử lý dữ liệu từ camera, thiết bị công nghiệp, cảm biến hoặc hệ thống nghiệp vụ. Telemetry có thể chứa payload, vị trí, định danh thiết bị hoặc thông tin người dùng.

Nguyên tắc:

- Thu thập tối thiểu dữ liệu cần cho vận hành.
- Mask hoặc loại bỏ payload nhạy cảm khỏi logs.
- Mã hóa buffer và telemetry khi lưu/truyền.
- Dùng device identity/certificate riêng cho từng node.
- Rotate credential khi có kết nối và có cơ chế xử lý khi certificate sắp hết hạn offline.
- Giới hạn quyền đọc telemetry theo site/tenant.
- Ghi audit cho remote command và thay đổi cấu hình.
- Xác minh integrity của agent, image và firmware.
- Không để telemetry endpoint mở rộng quyền điều khiển node.
- Có chính sách retention và xóa dữ liệu theo yêu cầu.

Khi offline, certificate có thể hết hạn trước khi node kết nối lại. Cần có kế hoạch bootstrap/re-enrollment an toàn và thời gian grace được thiết kế rõ; không tắt xác thực để khắc phục kết nối.

## 17. Capacity và observability cho cập nhật phần mềm tại biên

Cập nhật ứng dụng, container image, model và firmware cũng tiêu thụ capacity.

Một đợt update có thể cần:

- Download image/model mới.
- Lưu đồng thời bản hiện tại và bản mới.
- Verify chữ ký và checksum.
- Giải nén và tạo container.
- Chạy canary/health check.
- Giữ bản cũ để rollback.
- Gửi update status về control plane.

Nếu storage gần đầy hoặc uplink yếu, update có thể làm gián đoạn workload. Thiết kế rollout theo site ring hoặc batch, có giới hạn bandwidth và thời gian cập nhật.

### 17.1. Rollout theo ring

Một chiến lược:

1. Test trên lab hardware.
2. Canary một số node đại diện cho từng hardware profile.
3. Rollout tới một nhóm site nhỏ.
4. Theo dõi health, resource, latency và telemetry loss.
5. Mở rộng theo ring khi đạt tiêu chí.
6. Dừng rollout khi lỗi tập trung vào profile hoặc region.
7. Rollback theo digest/config version đã xác minh.

Không triển khai đồng thời toàn bộ fleet nếu chưa biết image mới có tương thích mọi kiến trúc, driver và giới hạn storage hay không.

## 18. Quy trình đánh giá capacity và observability

Một quy trình thực tế có thể chia thành các bước:

### Bước 1: Lập inventory

- Nhóm node theo hardware profile và site.
- Ghi CPU, accelerator, RAM, storage, network, power và thermal.
- Ghi OS, kernel, firmware, runtime và model version.
- Xác định node hết support hoặc khó thay thế.

### Bước 2: Xác định workload và SLO

- Throughput peak và average.
- p95/p99 latency.
- Availability khi mất cloud.
- Offline duration cần hỗ trợ.
- Data retention và recovery requirement.
- Workload ưu tiên và thứ tự degraded mode.

### Bước 3: Benchmark bền vững

- Chạy workload đại diện trong điều kiện nhiệt độ thực tế.
- Đo CPU/GPU/RAM/storage/network đồng thời.
- Đo tail latency và thermal throttling.
- Kiểm tra nhiều workload tranh chấp.
- Đo hiệu năng sau khi cache nóng và khi reconnect.

### Bước 4: Tính capacity theo site

- Tính node active theo throughput bền vững.
- Cộng capacity dự phòng cho failure domain.
- Tính RAM và disk buffer theo offline duration.
- Tính power/cooling và uplink.
- Xác minh khả năng chuyển workload khi một node mất.

### Bước 5: Thiết kế observability

- Local collector và local diagnostic.
- Persistent buffer có quota.
- Metrics theo hardware profile.
- Logs/traces có sampling và privacy control.
- Heartbeat, sequence và clock drift.
- Store-and-forward và reconnect throttling.

### Bước 6: Đặt ngưỡng và runbook

- Ngưỡng degraded, warning và critical.
- Owner theo site và fleet.
- Hành động khi disk, thermal hoặc buffer gần đầy.
- Quy trình offline recovery và remote support.
- Tiêu chí dừng rollout hoặc chuyển degraded mode.

### Bước 7: Kiểm thử và cập nhật

- Fault injection trong môi trường kiểm thử.
- Đo lại sau thay đổi firmware/model.
- Cập nhật capacity model theo số liệu fleet.
- Xem lại headroom khi workload hoặc data rate tăng.

## 19. Kiểm thử điều kiện xấu tại biên

Capacity và observability phải được kiểm thử trong điều kiện gần với thực tế, bao gồm:

| Kịch bản | Điều cần xác minh |
|---|---|
| Uplink mất 8-24 giờ | Workload local tiếp tục; spool không vượt quota |
| Network jitter/loss cao | Retry/backoff không tạo reconnect storm |
| Nhiệt độ môi trường cao | Throughput bền vững vẫn đáp ứng SLO |
| CPU/GPU throttling | Alert phát hiện; workload degrade theo policy |
| RAM gần đầy | OOM không làm mất toàn bộ dịch vụ |
| Storage gần đầy | Buffer có quota; log không chiếm disk nghiệp vụ |
| SSD wear/error | Có cảnh báo và phương án thay thế |
| Mất nguồn đột ngột | Queue/checkpoint nhất quán sau reboot |
| Một edge node hỏng | Workload được chuyển hoặc giảm tải có kiểm soát |
| Cloud ingestion throttling | Backlog drain theo rate limit |
| Clock drift | Event vẫn có sequence/correlation để điều tra |
| Update giữa lúc offline | Node không cài bản chưa verify hoặc mất rollback |

Mỗi bài test cần ghi kết quả, phiên bản phần cứng/phần mềm, điều kiện môi trường và thời gian phục hồi. Không chỉ kiểm tra node có reboot được; cần xác nhận dữ liệu, workload và telemetry vẫn nhất quán.

## 20. Các lỗi thường gặp

**Sizing theo thông số CPU/GPU quảng cáo:** hiệu năng có thể giảm khi thiết bị nóng hoặc model không dùng hết accelerator. Benchmark workload thật trong điều kiện bền vững.

**Chỉ đo CPU utilization:** RAM, storage, network hoặc thermal có thể là bottleneck. Theo dõi từng resource và latency.

**Không tính agent overhead:** telemetry, security và management agent cạnh tranh tài nguyên với workload. Đo cả khi đầy đủ agent.

**Không tính reconnect burst:** backlog export và update cùng lúc làm node quá tải. Giới hạn concurrency và bandwidth.

**Dùng local disk làm nơi lưu duy nhất:** thiết bị hỏng hoặc mất nguồn có thể làm mất dữ liệu. Persist và replicate dữ liệu quan trọng theo yêu cầu.

**Không đặt quota cho spool/log:** offline dài ngày làm đầy disk. Dùng bounded buffer và retention.

**Drop telemetry không có metric:** mất khả năng biết dữ liệu quan sát đã bị mất. Theo dõi dropped records và buffer utilization.

**Dùng timestamp làm thứ tự duy nhất:** clock drift làm sai thứ tự event. Dùng sequence, logical version và trace context.

**Coi disconnected là failed:** network partition không chứng minh node đã dừng. Phân biệt last-seen, local health và maintenance state.

**Áp một threshold cho mọi hardware:** node low-power và GPU server có baseline khác nhau. Dùng profile-specific baseline.

**Update toàn fleet cùng lúc:** lỗi image hoặc driver có thể ảnh hưởng mọi site. Dùng ring rollout và canary theo profile.

**Không kiểm tra power và cooling:** node có thể restart hoặc throttle trong môi trường thực tế. Đưa power/thermal vào capacity plan.

## 21. Checklist đánh giá phần cứng, capacity và observability tại biên

- [ ] Inventory có model, revision, CPU, RAM, accelerator, storage, network, power và thermal.
- [ ] Hardware profile được phân loại và gắn với site/node identity.
- [ ] Benchmark dùng workload thật và chạy đủ lâu để đo hiệu năng bền vững.
- [ ] Có dữ liệu CPU/GPU utilization, throttling và nhiệt độ.
- [ ] RAM budget tính cả OS, runtime, app, model, buffer và agent.
- [ ] Storage plan tính dung lượng, throughput, endurance và power-loss behavior.
- [ ] Offline spool có quota, retention, priority và drop policy rõ.
- [ ] Network plan đo throughput, latency, loss, reconnect và chi phí.
- [ ] Capacity được tính theo peak load và throughput bền vững tại từng site.
- [ ] Có headroom cho node failure, burst và reconnect.
- [ ] Workload critical có chế độ local/offline phù hợp.
- [ ] Có local collector và persistent store-and-forward buffer.
- [ ] Metrics có baseline theo hardware profile và cardinality được kiểm soát.
- [ ] Logs/traces có sampling, rotation, privacy và local retention.
- [ ] Heartbeat phân biệt disconnected với unhealthy.
- [ ] Clock drift, sequence number và trace context được xử lý.
- [ ] Fleet dashboard theo dõi version, config drift và last-seen.
- [ ] Remote update có signature verification, canary, ring rollout và rollback.
- [ ] Có alert cho thermal, disk, memory, buffer, network và telemetry drops.
- [ ] Đã kiểm thử offline, reconnect storm, mất nguồn, quá nhiệt và node failure.
- [ ] Runbook có owner theo site và tiêu chí chuyển degraded mode.

Đánh giá compute tại biên cần kết hợp giới hạn vật lý, tải thực tế và điều kiện môi trường của từng site. Capacity phải dựa trên hiệu năng bền vững, headroom cho lỗi và dung lượng cần giữ khi offline; observability phải có collector và buffer cục bộ để tiếp tục hoạt động khi cloud không truy cập được. Theo dõi thermal, storage endurance, network, clock drift và telemetry backlog theo hardware profile giúp phát hiện suy giảm sớm, giữ workload thiết yếu tại chỗ và đồng bộ dữ liệu trở lại cloud một cách có kiểm soát.

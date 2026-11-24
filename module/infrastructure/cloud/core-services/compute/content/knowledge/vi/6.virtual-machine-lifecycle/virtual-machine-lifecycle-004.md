# Thay đổi CPU, bộ nhớ và loại máy trong vòng đời workload

Nhu cầu tài nguyên của một ứng dụng thay đổi theo lượng người dùng, dữ liệu, phiên bản phần mềm và chu kỳ nghiệp vụ. Một máy ảo đủ dùng khi mới triển khai có thể trở nên quá tải sau vài tháng; ngược lại, máy được cấp quá lớn để dự phòng có thể gây lãng phí trong thời gian dài. Vì vậy, lựa chọn CPU, RAM và machine type cần được xem là quyết định có thể đánh giá và điều chỉnh trong suốt vòng đời workload.

Thay đổi cấu hình máy ảo thường được gọi là **resize** hoặc **vertical scaling**. Tùy nền tảng và loại máy, thao tác có thể diễn ra khi máy đang chạy, cần khởi động lại, cần dừng máy hoặc phải tạo máy mới rồi chuyển workload sang. Bài học này trình bày cách chọn phương án phù hợp, chuẩn bị trạng thái ứng dụng, thực hiện thay đổi có kiểm soát và xác minh sau khi resize.

## 1. Vì sao phải thay đổi cấu hình trong vòng đời workload?

Cấu hình ban đầu thường dựa trên dự báo. Khi hệ thống đi vào vận hành, số liệu thực tế cho thấy nhu cầu CPU, bộ nhớ, mạng và lưu trữ khác với giả định ban đầu.

Các lý do phổ biến:

- **Tăng tải:** số request, người dùng đồng thời hoặc dữ liệu tăng khiến CPU hay RAM trở thành nút thắt.
- **Thay đổi ứng dụng:** phiên bản mới có thể tăng số worker, heap, cache hoặc yêu cầu xử lý.
- **Thay đổi chu kỳ nghiệp vụ:** cuối tháng, mùa cao điểm hoặc chiến dịch có thể tạo tải đột biến.
- **Tối ưu chi phí:** máy thường xuyên nhàn rỗi có thể được giảm kích thước để tiết kiệm.
- **Thay đổi loại workload:** một dịch vụ API có thể chuyển sang xử lý dữ liệu, cache hoặc tác vụ tính toán chuyên sâu.
- **Yêu cầu phần cứng mới:** ứng dụng cần CPU thế hệ mới, nhiều RAM hơn, mạng nhanh hơn, GPU hoặc thiết bị lưu trữ khác.
- **Khả năng sẵn sàng:** cần cấu hình máy phù hợp với mô hình dự phòng, failover và thời gian phục hồi.

Không nên resize chỉ vì một chỉ số tăng trong vài phút. Cần xem xu hướng, thời gian duy trì, độ trễ, throughput, lỗi và các tài nguyên liên quan để xác định đúng nguyên nhân.

## 2. Resize và vertical scaling là gì?

Vertical scaling là thay đổi lượng tài nguyên của một máy hoặc node, thường bằng cách chọn machine type lớn hơn hoặc nhỏ hơn. Ví dụ:

- Tăng từ 2 lên 4 vCPU khi workload bị giới hạn CPU.
- Tăng từ 8 lên 16 GiB RAM khi working set không còn vừa bộ nhớ.
- Chuyển sang family memory optimized khi ứng dụng cần tỷ lệ RAM/vCPU cao.
- Chọn loại máy có băng thông mạng hoặc giới hạn I/O cao hơn khi máy hiện tại bị nghẽn ở các giới hạn đó.
- Giảm từ 8 xuống 4 vCPU và từ 32 xuống 16 GiB RAM khi mức sử dụng thấp ổn định.

Cần phân biệt ba cách mở rộng:

| Cách thay đổi | Mô tả | Khi phù hợp | Tác động cần tính đến |
|---|---|---|---|
| Scale up | Tăng tài nguyên của một máy | Workload khó chia nhỏ, cần RAM lớn hoặc hiệu năng cao trên một node | Chi phí máy lớn, giới hạn tối đa, có thể cần restart |
| Scale down | Giảm tài nguyên của một máy | Máy đang cấp thừa tài nguyên trong thời gian dài | Có thể thiếu headroom sau khi giảm; cần theo dõi đỉnh tải |
| Scale out/in | Thêm hoặc bớt số máy | Workload stateless hoặc có thể phân vùng | Cần load balancing, điều phối, đồng bộ trạng thái và autoscaling |

Scale up và scale down thay đổi năng lực của từng máy. Scale out và scale in thay đổi số lượng máy. Hai hướng có thể kết hợp: một nhóm node vừa đủ lớn, vừa có khả năng tăng giảm số node theo tải.

### Không phải mọi thay đổi đều là tăng CPU và RAM

Machine type thường là một gói tài nguyên. Khi đổi loại máy, ngoài số vCPU và RAM, các thông số sau cũng có thể thay đổi:

- Thế hệ CPU, kiến trúc x86-64 hoặc Arm và đặc tính hiệu năng đơn luồng.
- Tỷ lệ CPU/RAM và topology NUMA.
- Băng thông mạng, số gói tin mỗi giây và số hàng đợi mạng.
- Giới hạn IOPS và throughput của lưu trữ gắn với máy.
- Số lượng hoặc khả năng sử dụng ổ đĩa cục bộ.
- GPU, accelerator hoặc khả năng phân vùng thiết bị.
- Giới hạn số volume, card mạng hoặc thiết bị ngoại vi.
- Khả năng dùng live migration, hibernation, confidential computing hoặc các tính năng nền tảng khác.

Do đó, không thể chỉ so số vCPU trước và sau. Cần so toàn bộ đặc tính của machine type.

## 3. Các cơ chế thay đổi CPU và bộ nhớ

### Thay đổi nóng (hot-add/hot-remove)

Một số nền tảng hỗ trợ bổ sung hoặc loại bỏ CPU và/hoặc RAM khi máy ảo đang chạy. Cơ chế này thường được gọi là hot-plug hoặc hot-add/hot-remove.

Để sử dụng được, cần đồng thời đáp ứng:

- Hypervisor và loại máy hỗ trợ thay đổi nóng.
- Hệ điều hành khách nhận diện và đưa tài nguyên mới vào sử dụng.
- Kernel, driver và cấu hình boot cho phép hotplug.
- Ứng dụng hoặc runtime có thể nhận biết thay đổi tài nguyên.
- Nền tảng không yêu cầu restart cho loại thay đổi cụ thể đó.

Một số hệ điều hành có thể nhận diện CPU mới nhưng ứng dụng vẫn giữ thread pool theo số CPU lúc khởi động. Tương tự, hệ điều hành có thể nhận RAM mới nhưng JVM hoặc ứng dụng đã cấu hình heap cố định không tự động tăng giới hạn bộ nhớ.

Hot-add không đồng nghĩa mọi thay đổi đều không gián đoạn. Tính năng và giới hạn khác nhau theo nhà cung cấp, hypervisor, loại máy, hệ điều hành và cấu hình. Phải kiểm tra tài liệu đúng SKU trước khi lên kế hoạch.

### Thay đổi cần khởi động lại

Một số thao tác resize được thực hiện bằng cách dừng hoặc khởi động lại máy. Hệ thống có thể thay đổi tài nguyên được gán ở lớp hypervisor rồi boot lại hệ điều hành với cấu hình mới.

Tác động có thể gồm:

- Dịch vụ tạm ngừng nhận request.
- TCP connection và session hiện tại bị ngắt.
- Cache trong RAM mất và cần warm-up.
- Tiến trình phải khởi động lại.
- Địa chỉ IP, vị trí host hoặc trạng thái thiết bị có thể thay đổi theo nền tảng và cấu hình.
- Máy có thể phải chờ dung lượng phần cứng ở cụm đích.

Nếu ứng dụng chạy trên một máy đơn, cần có cửa sổ bảo trì hoặc phương án chuyển tải sang node khác trước khi dừng máy.

### Dừng máy rồi đổi machine type

Nhiều nền tảng yêu cầu VM ở trạng thái stopped/deallocated trước khi thay đổi một số thuộc tính máy. Dừng máy giúp nền tảng giải phóng tài nguyên đang cấp và gán cấu hình mới khi khởi động lại.

Cần phân biệt trạng thái dừng:

- Reboot: khởi động lại hệ điều hành; có thể vẫn giữ cùng host hoặc cùng tài nguyên tùy nền tảng.
- Stop/start: dừng máy rồi cấp lại tài nguyên khi khởi động; có thể thay đổi host và địa chỉ IP công cộng nếu không dùng IP tĩnh.
- Deallocate: giải phóng dung lượng compute khỏi cụm; có thể cần cấp phát lại khi start.
- Suspend/hibernate: lưu trạng thái theo cơ chế riêng của nền tảng; không phải lúc nào cũng tương thích với thay đổi machine type.

Tên trạng thái và ý nghĩa cụ thể khác nhau giữa các nhà cung cấp. Trước khi thao tác, xác định rõ lệnh đang dùng là restart, stop hay deallocate và dữ liệu nào bị ảnh hưởng.

### Thay thế máy bằng cấu hình mới

Khi không thể resize trực tiếp, cần kiến trúc mới hoặc thay đổi kiến trúc CPU, có thể tạo một VM mới từ image phù hợp rồi chuyển workload.

Mô hình này thường được gọi là replace, blue-green hoặc migration. Nó cho phép kiểm thử máy mới trước khi chuyển traffic, nhưng cần quản lý dữ liệu, địa chỉ mạng, danh tính máy, chứng thư, session và phụ thuộc ứng dụng.

Đối với hệ thống stateful, cần có cách đồng bộ dữ liệu hoặc chuyển quyền sở hữu dữ liệu để tránh mất hoặc ghi trùng.

## 4. Khi nào nên tăng CPU?

CPU thường là nút thắt khi workload cần nhiều phép tính hơn khả năng xử lý hiện tại. Một số dấu hiệu:

- CPU utilization duy trì cao trong thời gian có tải.
- Run queue hoặc số tiến trình chờ CPU tăng.
- Độ trễ p95/p99 tăng khi concurrency tăng.
- Throughput không tăng dù số request đến tăng.
- CPU throttling hoặc quota CPU bị chạm trong môi trường container.
- Batch job hoàn thành chậm hơn mục tiêu.

CPU cao không phải lúc nào cũng có nghĩa cần thêm vCPU. Có thể ứng dụng đang lặp vô hạn, có lock contention, xử lý quá nhiều dữ liệu, retry liên tục hoặc dùng thuật toán kém hiệu quả. Cần profiling trước khi resize.

### Tăng số vCPU

Tăng vCPU có thể giúp khi ứng dụng thực sự có thể chạy song song. Ví dụ, một dịch vụ xử lý độc lập nhiều request hoặc một worker pool có thể sử dụng thêm lõi.

Tuy nhiên, một luồng xử lý tuần tự không nhất thiết nhanh hơn khi thêm vCPU. Các yếu tố khác như xung nhịp, IPC, cache, NUMA và giới hạn CPU của nền tảng cũng ảnh hưởng.

### Đổi sang family compute optimized

Nếu workload thường xuyên bị giới hạn CPU trong khi RAM còn dư, family compute optimized có thể là lựa chọn đáng thử. So sánh cả hiệu năng đơn luồng và đa luồng, thế hệ CPU, kiến trúc và giá theo đơn vị công việc.

Không mặc định compute optimized luôn nhanh hơn cho mọi tác vụ. Một workload phụ thuộc bộ nhớ hoặc I/O có thể không cải thiện khi chuyển family.

### Kiểm tra ứng dụng sau khi tăng CPU

Sau resize, kiểm tra:

- Số CPU hệ điều hành nhận diện.
- Số worker, thread pool và connection pool của ứng dụng.
- CPU affinity hoặc cpuset nếu có.
- Giới hạn cgroup, container request/limit và quota.
- JVM hoặc runtime có cập nhật số CPU khả dụng không.
- Throughput và độ trễ có cải thiện tương xứng không.

Một số runtime xác định số lõi khả dụng lúc khởi động. Nếu thay đổi CPU mà không restart ứng dụng, cấu hình thread pool có thể không thay đổi.

## 5. Khi nào nên tăng RAM?

RAM thường là nút thắt khi working set của workload vượt quá bộ nhớ khả dụng hoặc ứng dụng cần cache lớn hơn để đạt mục tiêu độ trễ.

Dấu hiệu có thể gặp:

- Available memory thấp kéo dài.
- Swap-in/swap-out tăng.
- Major page fault hoặc memory pressure tăng.
- Tiến trình bị OOM kill hoặc container có trạng thái OOMKilled.
- Garbage collection xảy ra thường xuyên hoặc pause kéo dài.
- Cache eviction tăng và tỷ lệ cache hit giảm.
- Độ trễ tăng khi kích thước dataset hoặc concurrency tăng.

Cần phân biệt thiếu RAM với memory leak. Nếu tiến trình giữ bộ nhớ tăng liên tục dù tải không tăng, tăng RAM có thể chỉ trì hoãn sự cố. Hãy điều tra object retention, native memory, cache không giới hạn và buffer trước khi tăng máy.

### Tăng dung lượng RAM

Tăng RAM phù hợp khi working set hợp lệ và có nhu cầu giữ dữ liệu trong bộ nhớ. Cần ước lượng mức đỉnh, gồm hệ điều hành, runtime, cache, buffer, thread stack, agent và headroom.

Với JVM, tăng RAM máy không tự động tăng **-Xmx**. Cần đánh giá lại heap tối đa và chừa chỗ cho metaspace, direct buffer, native memory, thread stack, JIT và agent.

Với container, tăng RAM máy không tự động tăng memory limit của pod/container. Request và limit cần được điều chỉnh theo chính sách scheduler và mức sử dụng thực tế.

### Đổi sang family memory optimized

Nếu ứng dụng cần nhiều RAM trên mỗi vCPU, memory optimized có thể giảm việc cấp thừa CPU. Cần kiểm tra tỷ lệ RAM/vCPU, băng thông bộ nhớ, NUMA, CPU generation, mạng và giới hạn I/O của dòng máy.

### Kiểm tra sau khi tăng RAM

Sau resize, xác minh:

- Hệ điều hành nhận đủ dung lượng RAM mới.
- RAM mới được đưa vào vùng online và có thể cấp phát.
- Swap và memory pressure giảm.
- Heap, cache hoặc giới hạn ứng dụng đã được điều chỉnh đúng.
- Container limit và scheduler resource request phù hợp.
- Throughput, latency và tỷ lệ OOM cải thiện.
- Chi phí tăng có tương xứng với lợi ích hay không.

## 6. Chọn machine type mới theo workload

Trước khi đổi machine type, lập bảng so sánh giữa cấu hình hiện tại và cấu hình ứng viên.

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| CPU | Có bao nhiêu vCPU? CPU thế hệ nào? x86-64 hay Arm? Hiệu năng đơn luồng/đa luồng ra sao? |
| RAM | Dung lượng bao nhiêu? Tỷ lệ RAM/vCPU phù hợp không? Có giới hạn hot-add không? |
| Mạng | Băng thông, PPS, độ trễ và số interface có thay đổi không? |
| Lưu trữ | Giới hạn IOPS/throughput ở cấp VM có thay đổi không? Có ổ local/ephemeral không? |
| GPU/accelerator | Có cần thiết bị tăng tốc không? Driver và framework có tương thích không? |
| NUMA | Số node và cách phân bố vCPU/RAM có ảnh hưởng workload không? |
| Khả năng sẵn sàng | Có live migration, restart hoặc resize tại chỗ không? |
| Vùng và quota | Loại máy có sẵn ở region/zone cần triển khai không? |
| Chi phí | Giá compute, disk, network, license và reservation thay đổi thế nào? |

### Kiến trúc CPU có thể thay đổi

Chuyển từ x86-64 sang Arm có thể giảm chi phí hoặc tăng hiệu quả cho workload tương thích, nhưng không phải lúc nào cũng là thao tác resize trực tiếp. Cần xác minh image, kernel, driver, binary, thư viện native, agent bảo mật và license có hỗ trợ kiến trúc mới không.

Nếu ứng dụng có binary chỉ dành cho một kiến trúc, thường phải build lại hoặc dùng image khác. Với workload quan trọng, nên tạo máy mới trên kiến trúc đích, chạy kiểm thử và chuyển traffic theo từng bước.

### Thay đổi GPU hoặc accelerator

Machine type có GPU có thể có yêu cầu riêng về driver, runtime, firmware và vùng triển khai. Khi chuyển từ máy không GPU sang máy GPU, cần kiểm tra hệ điều hành nhận thiết bị, framework thấy đúng GPU và workload thực sự sử dụng được thiết bị.

Khi giảm hoặc bỏ GPU, xác minh ứng dụng không còn phụ thuộc CUDA/ROCm hoặc thư viện thiết bị. Một số image và service có thể không khởi động nếu driver hoặc thiết bị không còn hiện diện.

### Kiểm tra ổ đĩa cục bộ và dữ liệu tạm

Một số machine type có local SSD/NVMe hoặc ephemeral disk. Khi đổi loại máy, số lượng, dung lượng hoặc vòng đời của các ổ này có thể thay đổi. Dữ liệu trên ổ cục bộ có thể mất khi stop, deallocate, thay host hoặc thay máy tùy nền tảng.

Trước khi resize, phân loại dữ liệu:

- Dữ liệu bền vững cần giữ qua vòng đời máy.
- Cache có thể tạo lại.
- Dữ liệu tạm có thể bỏ.
- Log hoặc file checkpoint cần được chuyển sang lưu trữ bền vững.

Không dựa vào ổ local làm bản sao duy nhất của dữ liệu quan trọng.

## 7. Quy trình đánh giá trước khi resize

### Bước 1: xác định mục tiêu thay đổi

Ghi rõ vấn đề cần giải quyết và kết quả mong muốn. Ví dụ: giảm p95 dưới một ngưỡng, tránh OOM, rút ngắn batch job hoặc giảm chi phí hàng tháng.

Nếu không xác định được chỉ số thành công, rất khó đánh giá resize có hiệu quả hay không.

### Bước 2: thu thập số liệu nền

Thu thập metric trong một khoảng thời gian đại diện cho tải bình thường và cao điểm:

- CPU utilization, run queue và throttling.
- RAM available, working set, RSS, swap và OOM.
- IOPS, throughput, queue depth và latency của disk.
- Network throughput, PPS, retransmission và packet drop.
- Request rate, concurrency, p95/p99, error rate.
- Chi phí và mức sử dụng theo giờ.

Ghi nhận thời điểm batch, backup, deployment và tác vụ định kỳ để tránh nhầm một đỉnh tải ngắn với nhu cầu liên tục.

### Bước 3: xác định nút thắt thật

Nếu CPU cao nhưng throughput không tăng, hãy profile ứng dụng và kiểm tra lock, retry, thread contention. Nếu RAM cao, phân biệt working set hợp lệ với leak. Nếu độ trễ tăng nhưng CPU và RAM còn dư, kiểm tra disk, network, dependency bên ngoài và giới hạn dịch vụ.

Chỉ resize thành phần có liên quan đến nút thắt. Tăng CPU không sửa được ổ đĩa chậm; tăng RAM không giải quyết được packet loss.

### Bước 4: chọn một hoặc nhiều cấu hình ứng viên

So sánh machine type theo workload và các giới hạn đi kèm. Có thể thử một cấu hình lớn hơn trong cùng family trước khi đổi family. Với workload đặc thù, thử một máy memory optimized hoặc compute optimized để xem hiệu năng trên mỗi đơn vị chi phí.

### Bước 5: kiểm tra điều kiện nền tảng

Xác minh loại máy có sẵn ở region/zone, quota còn đủ và reservation/capacity có đáp ứng không. Kiểm tra yêu cầu dừng máy, khả năng live resize, license, kiến trúc CPU, local disk và tính năng bảo mật.

### Bước 6: lập kế hoạch thay đổi và rollback

Xác định thời điểm, người chịu trách nhiệm, thứ tự thao tác, health check và tiêu chí dừng. Ghi lại machine type hiện tại, cấu hình ứng dụng, địa chỉ mạng, volume, metadata và cách quay về cấu hình cũ.

### Bước 7: thực hiện trên môi trường thử nghiệm hoặc một node trước

Nếu có cluster, thử trên một node hoặc một nhóm nhỏ. Kiểm tra ứng dụng, hiệu năng và các phụ thuộc trước khi áp dụng cho toàn bộ hệ thống.

## 8. Chuẩn bị ứng dụng và dữ liệu trước khi dừng máy

Resize có thể làm máy khởi động lại hoặc thay host. Trước thao tác cần xác định trạng thái ứng dụng.

### Workload stateless

Với dịch vụ stateless, có thể drain node khỏi load balancer, chờ request đang xử lý hoàn tất, sau đó resize và đưa node trở lại. Cần có health check để chỉ nhận traffic khi ứng dụng sẵn sàng.

### Workload stateful

Với cơ sở dữ liệu, queue hoặc dịch vụ giữ trạng thái trong bộ nhớ, cần kế hoạch cụ thể:

- Xác định replica hoặc node dự phòng.
- Kiểm tra replication lag và trạng thái đồng bộ.
- Chuyển primary/leader nếu kiến trúc hỗ trợ.
- Dừng ghi hoặc quiesce workload khi cần.
- Tạo backup hoặc snapshot nhất quán.
- Đảm bảo dữ liệu trên local disk đã được chuyển hoặc có thể khôi phục.
- Kiểm tra quy trình khởi động và phục hồi sau restart.

Snapshot đĩa khi ứng dụng vẫn đang ghi có thể chỉ nhất quán ở mức crash-consistent. Với cơ sở dữ liệu, cần cơ chế backup hoặc quiesce phù hợp để bảo đảm tính nhất quán ứng dụng.

### Kết nối và phiên người dùng

Restart có thể làm mất TCP connection, session trong bộ nhớ và tác vụ đang chạy. Dịch vụ nên hỗ trợ retry có kiểm soát, session externalization hoặc graceful shutdown. Nếu request có side effect, cần idempotency để tránh xử lý trùng khi client retry.

### Kiểm tra backup và khả năng phục hồi

Backup chỉ hữu ích nếu có thể khôi phục. Trước thay đổi có rủi ro, xác minh thời điểm backup, phạm vi dữ liệu, quyền truy cập, khóa mã hóa và thời gian phục hồi. Không coi snapshot là thay thế hoàn toàn cho backup ứng dụng nếu dữ liệu có yêu cầu nhất quán cao.

## 9. Thực hiện resize tại chỗ

Tên thao tác trong console, CLI hoặc API khác nhau theo nhà cung cấp. Quy trình khái quát:

1. Ghi nhận cấu hình hiện tại và image/version đang dùng.
2. Kiểm tra snapshot/backup, dữ liệu local và trạng thái ứng dụng.
3. Drain traffic hoặc chuyển workload sang node khác nếu cần.
4. Dừng hoặc restart máy theo yêu cầu của loại resize.
5. Chọn machine type mới và xác nhận thay đổi.
6. Khởi động máy.
7. Xác minh hệ điều hành nhận đúng CPU, RAM và thiết bị.
8. Kiểm tra volume, network, driver và agent.
9. Khởi động ứng dụng, chờ health check đạt.
10. Đưa máy trở lại phục vụ traffic và theo dõi metric.

Không thực hiện nhiều thay đổi phần cứng cùng lúc nếu chưa có baseline. Nếu vừa đổi CPU family, RAM, network và storage, sẽ khó xác định thay đổi nào tạo ra kết quả tốt hoặc gây lỗi.

### Kiểm tra Linux sau resize

Các lệnh sau có thể hỗ trợ xác minh tài nguyên hệ điều hành nhận diện:

~~~sh
lscpu
nproc
free -h
cat /proc/meminfo
lsblk
ip -brief address
dmesg --level=err,warn
~~~

Có thể kiểm tra thiết bị và topology bổ sung bằng:

~~~sh
lscpu -e
numactl --hardware
df -h
systemctl --failed
~~~

Không phải mọi image đều có numactl. Kết quả lscpu và free phản ánh góc nhìn của hệ điều hành khách; nên đối chiếu với thông tin máy do nền tảng cung cấp.

### Kiểm tra Windows sau resize

PowerShell có thể xem cấu hình hệ điều hành nhận diện:

~~~powershell
Get-CimInstance Win32_ComputerSystem |
  Select-Object NumberOfLogicalProcessors, TotalPhysicalMemory

Get-CimInstance Win32_Processor |
  Select-Object Name, NumberOfCores, NumberOfLogicalProcessors

Get-CimInstance Win32_OperatingSystem |
  Select-Object TotalVisibleMemorySize, FreePhysicalMemory
~~~

Đối chiếu kết quả với cấu hình VM và theo dõi Event Viewer để phát hiện lỗi driver, thiết bị hoặc khởi động dịch vụ.

## 10. Thay thế máy bằng cấu hình mới

Khi resize tại chỗ không được hỗ trợ hoặc cần thay đổi kiến trúc lớn, có thể tạo máy mới.

Một quy trình blue-green đơn giản:

~~~mermaid
flowchart TD
    A["Đo tải và chọn machine type mới"] --> B["Tạo VM mới từ image đã kiểm thử"]
    B --> C["Gắn cấu hình, danh tính và quyền phù hợp"]
    C --> D["Đồng bộ dữ liệu hoặc tham gia cluster"]
    D --> E["Smoke test và benchmark"]
    E --> F{"Health check đạt?"}
    F -- "Không" --> G["Giữ traffic ở máy cũ và điều tra"]
    F -- "Đạt" --> H["Chuyển traffic từng phần"]
    H --> I["Theo dõi lỗi, latency và throughput"]
    I --> J{"Ổn định?"}
    J -- "Không" --> K["Chuyển traffic về máy cũ"]
    J -- "Đạt" --> L["Hoàn tất chuyển đổi và retire máy cũ"]
~~~

### Các thành phần cần chuyển

- Image hoặc hệ điều hành tương thích.
- Volume dữ liệu bền vững và filesystem.
- Cấu hình network, firewall/security group và route.
- Identity, role, service account và quyền truy cập.
- Secret, certificate và cấu hình runtime.
- Monitoring, logging, backup và security agent.
- DNS, load balancer, service discovery và endpoint.
- License hoặc activation gắn với phần cứng/instance nếu có.

Không sao chép machine identity, host key hoặc chứng thư riêng của máy cũ sang máy mới nếu điều đó tạo ra định danh trùng. Hãy dùng quy trình cấp danh tính mới và đăng ký lại agent.

### Đồng bộ dữ liệu và chuyển traffic

Tùy workload, có thể dùng replication, snapshot, backup/restore hoặc đồng bộ ở cấp ứng dụng. Với cơ sở dữ liệu, cần xác định thời điểm cutover, replication lag và cách tránh ghi đồng thời vào hai primary.

Chuyển traffic theo từng bước giúp phát hiện vấn đề sớm. Có thể bắt đầu với một phần nhỏ request, theo dõi error rate và latency, rồi tăng dần khi hệ thống ổn định.

## 11. Kiểm tra sau resize

Sau khi thay đổi, cần xác minh cả tài nguyên và kết quả ứng dụng.

| Nhóm | Chỉ số hoặc kiểm tra | Kết quả mong đợi |
|---|---|---|
| CPU | vCPU nhận diện, utilization, run queue, throttling | Tài nguyên mới được nhận đúng; CPU bottleneck giảm nếu đó là nguyên nhân |
| RAM | RAM khả dụng, working set, swap, OOM, heap | Không có áp lực bộ nhớ mới; ứng dụng sử dụng được dung lượng phù hợp |
| Storage | IOPS, throughput, latency, mount và filesystem | Volume hoạt động đúng, không mất dữ liệu hoặc giảm hiệu năng bất ngờ |
| Network | IP, route, DNS, throughput, packet loss | Kết nối nội bộ và bên ngoài hoạt động |
| Ứng dụng | Health check, error rate, p95/p99, throughput | SLO được đáp ứng |
| Bảo mật | Identity, role, agent, certificate, policy | Quyền và kiểm soát bảo mật vẫn đúng |
| Chi phí | Giá máy, disk, network, reservation | Chi phí thực tế nằm trong mục tiêu |

Theo dõi sau resize đủ lâu để bao phủ chu kỳ tải đại diện. Một phép thử ngay sau boot có thể chưa phản ánh cache warm-up, batch job, giờ cao điểm hoặc memory leak.

### Dấu hiệu cần rollback

- Máy không boot hoặc driver không nhận thiết bị.
- Ứng dụng không khởi động hoặc health check thất bại.
- Latency hoặc error rate xấu đi đáng kể.
- Network hoặc storage throughput thấp hơn trước.
- OOM, crash hoặc lỗi kernel xuất hiện.
- Không thể đạt SLO sau thời gian ổn định đã định.
- Chi phí tăng vượt lợi ích dự kiến.

Nếu rollback là đổi lại machine type cũ, cần xác minh dung lượng máy cũ còn khả dụng và quota/reservation vẫn phù hợp. Nếu đã chuyển sang máy mới, giữ máy cũ trong thời gian xác nhận để có thể chuyển traffic trở lại.

## 12. Autoscaling và thay đổi cấu hình định kỳ

Không phải mọi biến động tải đều cần resize thủ công. Nếu workload thay đổi theo giờ hoặc theo mùa, autoscaling có thể điều chỉnh số node hoặc số instance.

### Vertical scaling thủ công

Phù hợp khi:

- Tải tăng trưởng dài hạn và có thể dự báo.
- Cấu hình máy hiện tại không còn đủ.
- Thay đổi ít xảy ra và có thể lên lịch bảo trì.
- Workload khó chia nhỏ hoặc cần một node lớn.

### Vertical Pod Autoscaler và node autoscaling

Trong Kubernetes, Vertical Pod Autoscaler (VPA) có thể đề xuất hoặc điều chỉnh CPU/memory request của pod theo metric và policy. Một số chế độ cập nhật có thể yêu cầu pod restart. Node autoscaler có thể tăng hoặc giảm số node khi pod không được schedule hoặc node dư thừa.

Cần phân biệt:

- VPA điều chỉnh request/limit theo chính sách; nó không tự biến một node thành loại phần cứng khác trong mọi môi trường.
- Cluster/node autoscaler thay đổi số node hoặc node pool.
- Thay machine type của node thường liên quan đến tạo node mới và drain node cũ.
- Pod có stateful storage hoặc local data cần kế hoạch chuyển đổi riêng.

### Autoscaling theo workload

Với dịch vụ stateless, scale out thường phản ứng nhanh và giảm nhu cầu dừng máy. Với workload stateful, scale out có thể khó hơn vì dữ liệu, partition và leader phải được điều phối.

Nếu một máy đơn cần RAM lớn hơn mức tối đa của family hiện tại, vertical scaling hoặc sharding dữ liệu có thể là hướng phù hợp. Nếu request độc lập và có thể phân phối, scale out có thể tăng khả năng phục vụ với độ sẵn sàng tốt hơn.

### Rightsizing định kỳ

Lên lịch xem xét cấu hình theo tháng hoặc sau thay đổi lớn. So sánh mức sử dụng p50/p95/p99, đỉnh tải, headroom, chi phí và SLO. Không tự động giảm máy chỉ dựa trên CPU trung bình thấp vì RAM, I/O, đỉnh tải và yêu cầu phục hồi cũng cần được tính.

## 13. Tác động đến tính sẵn sàng và khả năng phục hồi

Resize có thể tạo ra một điểm gián đoạn. Với dịch vụ quan trọng, không nên phụ thuộc vào một máy duy nhất nếu cần duy trì tính sẵn sàng trong lúc thay đổi cấu hình.

Các cách giảm tác động:

- Dùng nhiều instance sau load balancer.
- Drain một node tại một thời điểm.
- Có health check và readiness check.
- Dùng replica cho dữ liệu hoặc dịch vụ stateful.
- Giữ capacity dự phòng đủ để nhận tải khi một node dừng.
- Thực hiện theo từng availability zone nếu kiến trúc yêu cầu.
- Kiểm tra quota và khả năng cấp máy trước khi bắt đầu.
- Có kế hoạch rollback và thời gian quan sát rõ ràng.

Với cụm nhiều node, resize lần lượt giúp giảm rủi ro nhưng có thể kéo dài thời gian thay đổi. Cần cân bằng tốc độ rollout với headroom còn lại. Nếu mỗi node đều chạy gần hết công suất, drain một node có thể làm các node còn lại quá tải.

### Capacity reservation và quota

Một loại máy mới có thể không còn đủ dung lượng ở zone mong muốn. Quota GPU, vCPU hoặc số instance cũng có thể giới hạn khả năng tạo máy. Trước khi resize production, kiểm tra quota, reservation và dung lượng khả dụng ở mọi vùng cần dùng.

Không nên xóa máy cũ ngay sau khi máy mới boot thành công. Giữ phương án dự phòng đến khi workload vượt qua thời gian xác nhận và dữ liệu đã được kiểm tra.

## 14. Chi phí và hiệu quả sau khi thay đổi

Giá máy lớn hơn thường tăng theo giờ, nhưng tổng chi phí trên mỗi đơn vị công việc có thể giảm nếu workload hoàn thành nhanh hơn hoặc cần ít node hơn.

Hãy tính:

- Giá compute theo machine type và thời gian chạy.
- Disk, snapshot, IOPS và throughput bổ sung.
- Lưu lượng mạng và chi phí liên vùng.
- License hệ điều hành hoặc phần mềm.
- Reservation hoặc cam kết sử dụng.
- Chi phí dự phòng cho HA và capacity.
- Chi phí vận hành do restart, migration hoặc quản lý nhiều node.

Một cách so sánh là:

\[
Cost\ per\ unit = \frac{Total\ operating\ cost}{Completed\ work\ units}
\]

Đơn vị công việc có thể là request, bản ghi, job, giao dịch hoặc giờ xử lý hữu ích.

Ví dụ, máy A xử lý 1.000 request/giây với chi phí 1 đơn vị tiền/giờ; máy B xử lý 2.500 request/giây với chi phí 2 đơn vị tiền/giờ. Nếu cả hai đáp ứng cùng SLO, chi phí trên mỗi request của B có thể thấp hơn dù giá mỗi giờ cao hơn. Cần tính từ số liệu thực tế và cùng mức lỗi/độ trễ.

### Tránh scale down quá mức

Giảm kích thước máy có thể tiết kiệm chi phí nhưng làm mất headroom cho burst, batch, failover và warm-up. Trước khi giảm, kiểm tra tải đỉnh, sự kiện mùa vụ, khả năng tăng máy trở lại và thời gian cấp phát. Một cấu hình nhỏ hơn chỉ phù hợp nếu vẫn đáp ứng SLO trong các kịch bản đã xác định.

## 15. Khác biệt triển khai giữa các nền tảng

Các nhà cung cấp dùng tên và quy trình khác nhau. Ví dụ tổng quát:

| Nền tảng | Cách thay đổi thường gặp | Điểm cần kiểm tra |
|---|---|---|
| AWS EC2 | Chọn instance type khác; nhiều trường hợp cần stop instance trước khi đổi | Loại instance hỗ trợ, instance store, ENI, kiến trúc, trạng thái stop/start và quota |
| Microsoft Azure | Resize VM sang VM size khác; có thể cần restart hoặc deallocate khi không đủ capacity tại host | VM size khả dụng trong cluster, disk/ephemeral disk, accelerated networking và quota |
| Google Cloud Compute Engine | Thay machine type; thường yêu cầu VM ở trạng thái stopped đối với thay đổi machine type | Machine family, CPU platform, local SSD, GPU, vùng và quota |

Bảng này chỉ mô tả hướng chung. Hành vi chính xác thay đổi theo loại máy, region, hệ điều hành và tính năng. Trước khi thao tác production, phải xác minh quy trình hiện hành của SKU cụ thể.

Một số nền tảng có thể hỗ trợ tăng CPU/RAM trực tuyến trong những giới hạn nhất định; các tính năng đó không áp dụng cho mọi machine type. Cần phân biệt thay đổi nóng tài nguyên với thay đổi machine type hoàn chỉnh.

## 16. Ví dụ: tăng cấu hình cho dịch vụ API

Một dịch vụ API chạy trên VM có 4 vCPU và 16 GiB RAM. Sau khi lượng request tăng, nhóm vận hành thấy:

- CPU p95 duy trì trên 85% trong giờ cao điểm.
- Run queue tăng khi concurrency tăng.
- RAM available vẫn còn khoảng 5 GiB.
- Disk latency và network packet loss bình thường.
- Độ trễ p99 vượt SLO trong các đợt tải lớn.

Nhóm profiling cho thấy phần xử lý request có thể chạy song song và thread pool đã đạt giới hạn CPU. Nhóm thử machine type 8 vCPU/32 GiB trong môi trường staging. Kết quả cho thấy throughput tăng và p99 giảm, nhưng cần kiểm tra chi phí và mức sử dụng RAM mới.

Kế hoạch triển khai production:

1. Tạo node mới với image và cấu hình 8 vCPU/32 GiB.
2. Đăng ký node vào load balancer ở trạng thái chưa nhận traffic.
3. Chạy smoke test và tải thử.
4. Chuyển một phần traffic sang node mới.
5. Theo dõi CPU, RAM, p95/p99, error rate và chi phí.
6. Tăng dần traffic nếu kết quả ổn định.
7. Drain và retire node cũ sau khi xác minh.

Nếu ứng dụng chỉ sử dụng một luồng CPU hoặc database phía sau mới là nút thắt, tăng vCPU có thể không cải thiện. Ví dụ này chỉ ra rằng resize cần dựa trên profiling và kiểm chứng ở tải đại diện.

## 17. Checklist trước và sau khi resize

### Trước khi thay đổi

- [ ] Đã xác định mục tiêu và chỉ số thành công.
- [ ] Đã thu thập metric CPU, RAM, network, storage và ứng dụng.
- [ ] Đã xác định đúng nút thắt thay vì chỉ dựa trên một metric.
- [ ] Đã so sánh toàn bộ machine type, không chỉ số vCPU.
- [ ] Đã kiểm tra kiến trúc CPU, driver, GPU và phần mềm tương thích.
- [ ] Đã kiểm tra local/ephemeral disk và phân loại dữ liệu.
- [ ] Đã xác minh quota, reservation và capacity ở region/zone.
- [ ] Đã kiểm tra resize có cần stop, restart hoặc deallocate không.
- [ ] Đã drain traffic và chuẩn bị replica nếu cần.
- [ ] Đã xác minh backup/snapshot và phương án phục hồi.
- [ ] Đã ghi lại cấu hình cũ, địa chỉ mạng, volume và quyền.
- [ ] Đã có tiêu chí dừng và rollback.

### Sau khi thay đổi

- [ ] Hệ điều hành nhận diện đúng CPU, RAM và thiết bị.
- [ ] Ứng dụng, driver, agent và service khởi động thành công.
- [ ] Volume, filesystem, network, DNS và security policy hoạt động.
- [ ] Heap, thread pool, container request/limit và cache được điều chỉnh phù hợp.
- [ ] Health check, error rate, latency và throughput đạt mục tiêu.
- [ ] Không xuất hiện OOM, kernel error, packet loss hoặc storage regression.
- [ ] Đã theo dõi qua chu kỳ tải đại diện.
- [ ] Chi phí trên mỗi đơn vị công việc nằm trong mục tiêu.
- [ ] Đã cập nhật inventory, manifest hoặc tài liệu cấu hình.
- [ ] Máy cũ chỉ được retire sau khi phương án mới ổn định.

## Kết luận

Thay đổi CPU, RAM và machine type là hoạt động bình thường trong vòng đời workload. Quyết định resize cần dựa trên metric và profiling, đồng thời xem xét toàn bộ tài nguyên đi kèm machine type. Trước khi thay đổi, phải hiểu cơ chế hot-add, restart, stop/deallocate hoặc thay thế máy; chuẩn bị dữ liệu, kết nối, backup và rollback. Sau resize, xác minh tài nguyên ở hệ điều hành, điều chỉnh runtime và giới hạn ứng dụng, rồi theo dõi SLO và chi phí. Với workload quan trọng, rollout từng node hoặc dùng blue-green giúp giảm gián đoạn và giữ khả năng quay lại cấu hình ổn định.

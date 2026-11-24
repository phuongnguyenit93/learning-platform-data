# Liên kết nhiều GPU và truyền dữ liệu giữa các máy

## 1. Vì sao liên kết GPU quan trọng?

Một GPU hiện đại có thể thực hiện hàng nghìn phép tính song song, nhưng hiệu năng của một hệ thống AI hoặc HPC không chỉ phụ thuộc vào tốc độ tính toán của từng GPU. Khi mô hình hoặc dữ liệu lớn hơn bộ nhớ của một GPU, workload phải chia công việc cho nhiều GPU. Các GPU cần trao đổi tensor, activation, gradient, tham số hoặc kết quả trung gian. Nếu đường truyền dữ liệu chậm, GPU sẽ phải chờ và năng lực tính toán đắt tiền bị bỏ trống.

Liên kết GPU có hai phạm vi chính. Trong một máy chủ, GPU giao tiếp qua các kết nối như PCI Express (PCIe), NVLink hoặc fabric chuyển mạch như NVSwitch. Giữa nhiều máy chủ, dữ liệu đi qua card mạng tốc độ cao, switch và fabric mạng; một số nền tảng hỗ trợ RDMA và GPUDirect RDMA để giảm các bước sao chép qua CPU. Mỗi đường truyền có băng thông, độ trễ, topology và giới hạn riêng.

Thiết kế tốt cần trả lời ba câu hỏi: dữ liệu phải đi từ đâu đến đâu; đường truyền nào sẽ mang dữ liệu; và việc truyền có thể diễn ra đồng thời với tính toán hay không. Việc chọn GPU, máy chủ, card mạng, switch, thư viện giao tiếp và cách phân chia mô hình phải được xem xét cùng nhau.

Sau bài học, người học có thể:

- Phân biệt các đường truyền giữa GPU trong cùng máy chủ và giữa các máy chủ.
- Đọc topology CPU, PCIe, GPU, NIC và switch để dự đoán nút thắt giao tiếp.
- Hiểu vai trò của peer-to-peer, RDMA, GPUDirect RDMA và collective communication.
- Chọn chiến lược phân tán dữ liệu hoặc mô hình phù hợp với mẫu giao tiếp.
- Đo băng thông, độ trễ, mức sử dụng liên kết và tỷ lệ chồng lấp truyền dữ liệu với tính toán.
- Thiết kế cluster GPU trên cloud có xét đến khả năng mở rộng, độ tin cậy, bảo mật và chi phí.

## 2. Các lớp kết nối trong hệ thống nhiều GPU

### 2.1. Bộ nhớ GPU và bộ nhớ máy chủ

GPU có bộ nhớ riêng, thường là HBM hoặc GDDR tùy loại thiết bị. CPU truy cập bộ nhớ hệ thống (host memory), còn GPU truy cập bộ nhớ thiết bị (device memory). Dữ liệu huấn luyện thường bắt đầu ở storage, được đọc vào RAM của máy chủ, sau đó chuyển sang bộ nhớ GPU. Trong quá trình huấn luyện, các GPU cũng trao đổi dữ liệu với nhau.

Một lần truyền dữ liệu có thể đi qua nhiều lớp:

```text
Storage / Dataset
      |
      v
Host memory (RAM)
      |
      | PCIe hoặc đường I/O được nền tảng hỗ trợ
      v
GPU 0 memory <------> GPU 1 memory
      |                    |
      +------ GPU fabric ---+

GPU memory -- NIC / RDMA fabric -- NIC -- GPU memory
                    (nhiều máy chủ)
```

Đường đi thực tế phụ thuộc máy chủ và nền tảng. Nếu không có cơ chế truyền trực tiếp phù hợp, dữ liệu từ GPU này sang GPU khác hoặc sang máy khác có thể phải đi qua host memory và CPU. Các bước trung gian làm tăng độ trễ, tiêu thụ băng thông PCIe và tạo thêm áp lực lên bộ nhớ máy chủ.

### 2.2. PCI Express (PCIe)

PCIe là bus tốc độ cao dùng để kết nối CPU với GPU, NIC, thiết bị lưu trữ và các thiết bị mở rộng khác. Liên kết PCIe có các thế hệ và độ rộng lane khác nhau, ví dụ x8 hoặc x16. Băng thông thực tế phụ thuộc thế hệ, số lane, cấu hình root complex, switch PCIe và mức tranh chấp giữa các thiết bị.

PCIe thường là đường truyền quan trọng cho việc nạp dữ liệu từ RAM sang GPU và cho giao tiếp giữa GPU với NIC. Một GPU có thể được kết nối trực tiếp vào root complex của CPU; một số GPU khác đi qua PCIe switch. Nếu nhiều GPU hoặc NIC cùng chia sẻ một uplink, tổng lưu lượng có thể bị giới hạn ở đoạn dùng chung đó.

PCIe cũng có thể hỗ trợ peer-to-peer (P2P), cho phép một thiết bị truy cập bộ nhớ của thiết bị khác mà không cần CPU sao chép dữ liệu qua RAM trong mọi trường hợp. Khả năng P2P phụ thuộc phần cứng, firmware, driver, IOMMU, cấu hình BIOS và topology. Không nên giả định mọi cặp GPU đều có đường P2P hiệu quả.

### 2.3. NVLink và NVSwitch

NVLink là công nghệ liên kết tốc độ cao giữa các GPU hoặc giữa GPU và CPU được hỗ trợ trên một số nền tảng. So với việc chỉ dựa vào PCIe, NVLink có thể cung cấp băng thông liên GPU cao hơn và độ trễ phù hợp hơn cho các mẫu giao tiếp dày đặc. Các GPU có thể trao đổi tensor hoặc tham số qua liên kết này khi hệ thống, driver và thư viện cho phép.

NVSwitch là fabric chuyển mạch giúp kết nối nhiều GPU qua các liên kết NVLink. Thay vì chỉ có các kết nối trực tiếp hạn chế giữa một số cặp GPU, fabric có thể tạo đường giao tiếp rộng hơn giữa nhiều GPU trong cùng hệ thống. Điều này đặc biệt hữu ích cho tensor parallelism hoặc các workload cần trao đổi dữ liệu thường xuyên giữa nhiều GPU.

NVLink và NVSwitch không phải tính năng mặc định của mọi máy chủ GPU. Cần kiểm tra số lượng GPU được kết nối, topology, băng thông hai chiều, thế hệ liên kết và khả năng hỗ trợ của nền tảng. Một máy chủ có nhiều GPU nhưng kết nối chỉ qua PCIe có đặc tính giao tiếp khác với một hệ thống có fabric NVLink/NVSwitch đầy đủ.

### 2.4. Topology GPU trong một máy chủ

Topology mô tả các thiết bị được nối với nhau và các đường đi giữa chúng. Trong một máy chủ nhiều GPU, topology có thể bao gồm:

- Một hoặc nhiều socket CPU và các NUMA node.
- PCIe root complex và PCIe switch.
- GPU, NIC và thiết bị lưu trữ tốc độ cao.
- Các liên kết GPU-to-GPU như NVLink.
- Các uplink chung mà nhiều thiết bị cùng sử dụng.

Hai GPU có thể nằm gần cùng một PCIe switch và giao tiếp nhanh; một cặp GPU khác có thể phải đi qua nhiều switch hoặc qua liên kết giữa các socket CPU. Vì vậy, số lượng GPU không đủ để mô tả khả năng giao tiếp của node.

Khi khảo sát máy chủ, hãy xem sơ đồ topology do nhà cung cấp cung cấp và dùng công cụ của hệ thống để kiểm tra đường kết nối thực tế. Ví dụ, trên một số hệ thống NVIDIA, `nvidia-smi topo -m` hiển thị quan hệ topology giữa GPU, CPU và NIC. Kết quả phụ thuộc driver và phần cứng; cần đọc tài liệu của nền tảng để diễn giải chính xác các ký hiệu.

### 2.5. NUMA và vị trí CPU/NIC

Trong máy chủ nhiều socket, bộ nhớ RAM và các thiết bị PCIe thường gắn gần một NUMA node cụ thể. CPU ở socket này có thể truy cập RAM hoặc thiết bị gắn với socket kia qua liên kết liên socket, làm tăng độ trễ và sử dụng băng thông kết nối giữa các socket.

Đối với workload GPU, vị trí của tiến trình CPU, vùng host memory, GPU và NIC có thể ảnh hưởng đáng kể đến tốc độ truyền. Một NIC đặt gần GPU theo topology có thể giảm các bước đi vòng qua socket khác. Data loader hoặc tiến trình điều phối đặt sai NUMA node có thể khiến đường truyền bị chậm dù GPU và NIC đều có thông số danh nghĩa cao.

Hãy gắn CPU affinity và memory affinity phù hợp khi workload nhạy với NUMA. Đồng thời kiểm tra cách scheduler cấp CPU và RAM cho container hoặc VM; việc giới hạn CPU không đúng có thể vô tình đẩy luồng điều khiển và buffer sang NUMA node xa thiết bị.

## 3. Kết nối GPU giữa nhiều máy chủ

### 3.1. Fabric mạng cho cluster GPU

Khi số GPU vượt quá khả năng của một máy chủ, cluster cần kết nối các node qua mạng. Mỗi node thường có một hoặc nhiều NIC tốc độ cao, kết nối đến switch và fabric mạng. Các lựa chọn phổ biến trong trung tâm dữ liệu hiệu năng cao gồm InfiniBand và Ethernet tốc độ cao, trong đó RoCE (RDMA over Converged Ethernet) cho phép sử dụng RDMA trên hạ tầng Ethernet được cấu hình phù hợp.

Không nên đánh giá mạng chỉ qua tốc độ cổng NIC ghi trên thông số. Băng thông ứng dụng còn phụ thuộc số NIC, số rail, oversubscription của switch, topology spine-leaf, số hop, MTU, congestion control, đường đi qua PCIe và khả năng xử lý của CPU. Một cluster có NIC rất nhanh nhưng uplink switch bị oversubscribe vẫn có thể đạt throughput thấp khi nhiều node truyền đồng thời.

### 3.2. RDMA là gì?

Remote Direct Memory Access (RDMA) cho phép một máy chủ truy cập vùng bộ nhớ đã đăng ký của máy chủ khác qua NIC và fabric hỗ trợ RDMA. Mục tiêu là giảm sự tham gia của CPU và số lần sao chép dữ liệu trong đường truyền. RDMA thường có độ trễ thấp và khả năng truyền dữ liệu cao, phù hợp với collective communication trong huấn luyện phân tán.

RDMA yêu cầu đăng ký (register) vùng bộ nhớ, tạo queue pair hoặc cơ chế giao tiếp tương ứng, quản lý completion và đồng bộ đúng cách. Đây là một mô hình giao tiếp có yêu cầu vận hành cao hơn socket TCP thông thường. Cấu hình sai NIC, subnet, MTU, congestion control, driver hoặc quyền truy cập bộ nhớ có thể làm kết nối thất bại hoặc suy giảm hiệu năng.

RDMA không có nghĩa là dữ liệu luôn đi trực tiếp từ VRAM của GPU sang VRAM của GPU khác. Nếu chỉ có RDMA thông thường, ứng dụng có thể vẫn phải sao chép dữ liệu từ GPU sang host memory trước khi NIC truyền đi, rồi sao chép từ host memory sang GPU ở node đích.

### 3.3. GPUDirect RDMA

GPUDirect RDMA là nhóm cơ chế cho phép thiết bị mạng được hỗ trợ truy cập trực tiếp vùng nhớ GPU, giảm nhu cầu staging qua host memory. Khi cả GPU, NIC, driver, kernel, nền tảng I/O và thư viện truyền thông đều tương thích, dữ liệu có thể đi từ bộ nhớ GPU ở node nguồn đến NIC, qua fabric, rồi được ghi vào bộ nhớ GPU ở node đích với ít bước trung gian hơn.

Lợi ích tiềm năng là giảm độ trễ, giảm tải CPU và giảm áp lực lên băng thông bộ nhớ host/PCIe. Tuy nhiên, khả năng này phụ thuộc chặt vào tổ hợp phần cứng và phần mềm. Không phải mọi VM, instance cloud, NIC ảo, hypervisor hoặc cấu hình IOMMU đều cho phép GPUDirect RDMA. Một số môi trường yêu cầu driver, kernel module, thư viện và cấu hình cụ thể.

Khi chọn dịch vụ cloud, hãy xác minh rõ GPU và NIC có hỗ trợ GPUDirect RDMA hay không, cách thiết bị được expose vào VM/container, giới hạn bảo mật và cách kiểm thử. Nếu không có đường truyền trực tiếp, ứng dụng vẫn có thể chạy qua host staging, nhưng hiệu năng và mức tiêu thụ CPU có thể khác đáng kể.

### 3.4. So sánh các đường truyền

| Đường truyền | Phạm vi | Đặc điểm | Điểm cần kiểm tra |
|---|---|---|---|
| Host RAM ↔ GPU qua PCIe | Trong một node | Đường phổ biến để nạp dữ liệu và trao đổi với thiết bị | PCIe generation/lane, NUMA, switch và băng thông chia sẻ |
| GPU ↔ GPU qua PCIe P2P | Trong một node | Có thể truyền trực tiếp giữa thiết bị nếu topology hỗ trợ | P2P capability, driver, IOMMU và đường đi thực tế |
| GPU ↔ GPU qua NVLink/NVSwitch | Trong một node | Liên kết GPU tốc độ cao, phù hợp giao tiếp dày đặc | Thế hệ, topology, số GPU được kết nối và băng thông thực |
| Host RAM ↔ Host RAM qua Ethernet/TCP | Giữa các node | Phổ biến, dễ tích hợp nhưng có thể tăng tải CPU và copy | NIC, TCP stack, CPU, congestion và số hop |
| Host memory qua RDMA | Giữa các node | Giảm overhead CPU và copy trong giao tiếp mạng | NIC/fabric RDMA, memory registration, MTU và congestion control |
| GPU memory qua GPUDirect RDMA | Giữa các node | Có thể giảm staging qua host memory | Tương thích GPU/NIC/driver/hypervisor và cấu hình cloud |

## 4. Các yếu tố quyết định hiệu năng truyền dữ liệu

### 4.1. Băng thông và độ trễ

**Băng thông** cho biết lượng dữ liệu có thể truyền trong một đơn vị thời gian, thường biểu diễn bằng GB/s hoặc Gb/s. **Độ trễ** là thời gian cần để một thao tác giao tiếp hoàn tất hoặc để dữ liệu bắt đầu đến đích, thường đo bằng microsecond hoặc millisecond tùy đường truyền và kích thước dữ liệu.

Một đường truyền có băng thông lớn vẫn có thể không phù hợp với hàng triệu thông điệp rất nhỏ nếu độ trễ mỗi lần gửi cao. Ngược lại, một đường truyền có độ trễ thấp nhưng băng thông hạn chế có thể không hiệu quả khi trao đổi tensor lớn. Cần biết workload thiên về nhiều thông điệp nhỏ, ít thông điệp lớn hay kết hợp cả hai.

Thời gian truyền có thể ước lượng đơn giản bằng:

\[
T_{transfer} \approx T_{startup} + \frac{S}{B_{effective}}
\]

Trong đó:

- \(T_{startup}\) là phần thời gian cố định cho khởi tạo, đồng bộ và gửi nhận.
- \(S\) là kích thước dữ liệu.
- \(B_{effective}\) là băng thông hữu ích đo được của ứng dụng.

Đây là mô hình gần đúng. Thời gian thực tế còn phụ thuộc queueing, congestion, số bước copy, đồng bộ CPU/GPU, giao thức và số luồng truyền đồng thời.

### 4.2. Băng thông danh nghĩa và băng thông hữu ích

Băng thông danh nghĩa của PCIe, NVLink hoặc NIC là giới hạn lý thuyết theo cấu hình liên kết. Băng thông hữu ích thấp hơn do overhead giao thức, mã hóa, packet header, điều khiển luồng, tranh chấp, đồng bộ và cách triển khai phần mềm.

Để đánh giá đúng, đo throughput ở cả cấp liên kết và cấp ứng dụng. Một bài benchmark copy lớn có thể cho thấy giới hạn băng thông; một bài benchmark collective với nhiều GPU sẽ phản ánh thêm chi phí đồng bộ, thuật toán và topology.

### 4.3. Kích thước thông điệp và batching

Thông điệp nhỏ chịu ảnh hưởng nhiều từ độ trễ khởi tạo. Gộp nhiều tensor nhỏ thành một buffer lớn có thể giảm số lần gửi và tăng hiệu quả băng thông. Tuy nhiên, gộp quá nhiều làm tăng bộ nhớ tạm và có thể trì hoãn thời điểm dữ liệu sẵn sàng để truyền.

Kích thước bucket trong huấn luyện phân tán là một ví dụ về trade-off này. Bucket lớn giảm overhead cho mỗi lần giao tiếp, nhưng có thể khiến gradient phải chờ lâu hơn trước khi bắt đầu truyền. Bucket nhỏ bắt đầu truyền sớm nhưng tạo nhiều thao tác giao tiếp hơn. Cần điều chỉnh dựa trên tốc độ tính toán, kích thước gradient và topology.

### 4.4. Pinned memory và host staging

Pinned memory là vùng RAM của máy chủ được khóa để hệ điều hành không di chuyển hoặc hoán đổi trang trong lúc thiết bị thực hiện DMA. Nó thường giúp truyền dữ liệu host-to-device hoặc device-to-host hiệu quả và hỗ trợ truyền bất đồng bộ.

Pinned memory không nên được cấp phát vô hạn. Quá nhiều vùng RAM bị pin có thể làm giảm khả năng quản lý bộ nhớ của hệ điều hành. Data loader cần tái sử dụng buffer, chọn số worker hợp lý và đo xem CPU có theo kịp tốc độ nạp GPU hay không.

Host staging xảy ra khi dữ liệu được sao chép qua RAM máy chủ trước khi đến GPU đích hoặc NIC. Đây là đường fallback phổ biến khi không có P2P hoặc GPUDirect RDMA. Nếu phải dùng staging, hãy xem xét số lần copy, kích thước buffer, pinned memory và khả năng chồng lấp các bước copy với tính toán.

### 4.5. Truyền bất đồng bộ và overlap

CUDA streams hoặc cơ chế tương đương cho phép xếp lịch copy và kernel theo các luồng công việc khác nhau. Khi thiết bị và thư viện hỗ trợ, ứng dụng có thể truyền dữ liệu của batch tiếp theo trong lúc GPU đang tính toán batch hiện tại.

Overlap chỉ hiệu quả khi có đủ tài nguyên và đồng bộ đúng. Nếu hai thao tác tranh chấp cùng một liên kết PCIe hoặc cùng băng thông bộ nhớ, chạy đồng thời có thể không nhanh hơn chạy tuần tự. Cần dùng event hoặc primitive đồng bộ phù hợp để tránh kernel đọc buffer trước khi truyền hoàn tất hoặc buffer bị ghi đè quá sớm.

## 5. Collective communication giữa nhiều GPU

### 5.1. Collective là gì?

Collective communication là thao tác giao tiếp mà một nhóm tiến trình hoặc GPU cùng tham gia theo một quy tắc. Các thư viện như NVIDIA Collective Communications Library (NCCL) cung cấp các primitive tối ưu cho GPU và có thể sử dụng nhiều loại liên kết trong node hoặc giữa các node.

Các thao tác thường gặp:

- **Broadcast:** một tiến trình gửi dữ liệu cho tất cả tiến trình còn lại.
- **Reduce:** kết hợp dữ liệu từ nhiều tiến trình bằng phép toán như sum, max hoặc min và trả kết quả về một tiến trình đích.
- **All-reduce:** kết hợp dữ liệu từ tất cả tiến trình rồi phân phối kết quả tổng hợp cho tất cả.
- **All-gather:** thu thập các phần dữ liệu từ mọi tiến trình và tạo bản ghép đầy đủ trên mỗi tiến trình.
- **Reduce-scatter:** thực hiện phép reduce rồi chia kết quả thành các phần, mỗi tiến trình nhận một phần.
- **All-to-all:** mỗi tiến trình gửi một phần dữ liệu riêng đến từng tiến trình khác và nhận các phần tương ứng.

Collective phải được gọi theo thứ tự tương thích trên các tiến trình tham gia. Nếu một tiến trình bỏ qua thao tác hoặc gọi sai thứ tự, các tiến trình khác có thể chờ vô hạn hoặc gặp lỗi timeout.

### 5.2. All-reduce và đồng bộ gradient

Trong data parallel training, mỗi GPU xử lý một phần mini-batch và tính gradient cho bản sao mô hình của nó. Để các bản sao giữ cùng tham số, gradient cần được tổng hợp giữa các GPU. All-reduce thường được dùng để cộng gradient từ các GPU rồi phân phối kết quả tổng hợp cho tất cả.

Ví dụ với bốn GPU:

```text
GPU 0: gradient g0 ----+
GPU 1: gradient g1 ----+---- All-reduce (SUM) ----> g0+g1+g2+g3
GPU 2: gradient g2 ----+                         trên mỗi GPU
GPU 3: gradient g3 ----+
```

Nếu gradient lớn, all-reduce có thể chiếm phần đáng kể thời gian mỗi bước huấn luyện. Khi compute trên mỗi batch nhanh hơn nhưng thời gian đồng bộ không giảm, hiệu suất mở rộng từ nhiều GPU có thể thấp.

### 5.3. Ring và tree collective

Ring all-reduce tổ chức các tiến trình thành một vòng. Dữ liệu được chia thành các chunk và luân chuyển qua các bước reduce-scatter và all-gather. Cách tổ chức này có thể tận dụng băng thông tốt khi dữ liệu lớn và đường truyền tương đối đồng đều, nhưng số bước tăng theo số tiến trình.

Tree-based collective tổ chức tiến trình thành cấu trúc cây. Cách này có thể giảm số bước giao tiếp cho một số trường hợp và phù hợp với thông điệp nhỏ hoặc topology nhất định. Đổi lại, các nút trung gian có thể trở thành điểm tập trung lưu lượng.

Thư viện giao tiếp thường chọn thuật toán theo kích thước dữ liệu, số GPU, topology và cấu hình. Không có thuật toán tối ưu cho mọi cluster. Khi benchmark, cần thử các kích thước thông điệp và số GPU đại diện cho workload thật.

### 5.4. Giao tiếp phân cấp (hierarchical communication)

Một cluster GPU thường có nhiều cấp liên kết: GPU trong cùng node có thể giao tiếp qua NVLink/NVSwitch hoặc PCIe; các node giao tiếp qua NIC và fabric mạng. Collective phân cấp tận dụng liên kết nhanh trong node để tổng hợp hoặc chia dữ liệu cục bộ, sau đó trao đổi kết quả giữa các node, rồi phân phối lại trong node.

Ví dụ, với một nhóm GPU trên mỗi máy chủ, hệ thống có thể reduce dữ liệu cục bộ trước khi thực hiện trao đổi liên node. Cách này giảm số luồng mạng đi ra khỏi node và khai thác tốt topology. Tuy nhiên, hiệu quả phụ thuộc thư viện, cấu hình NIC, số GPU mỗi node và cách phân bổ rank.

### 5.5. Point-to-point và communication pattern

Không phải mọi workload đều dùng collective. Một số mô hình cần gửi tensor trực tiếp từ một GPU hoặc tiến trình đến một GPU khác (send/receive). Point-to-point phù hợp với pipeline parallelism, trao đổi activation giữa các stage hoặc giao tiếp có cấu trúc thưa.

Khi thiết kế, cần xác định ai gửi, ai nhận, kích thước dữ liệu, thời điểm gửi, cách đồng bộ và hành vi khi một tiến trình chậm. Một mẫu giao tiếp không cân bằng có thể khiến một số GPU luôn bận còn GPU khác phải chờ.

## 6. Chia mô hình và dữ liệu trên nhiều GPU

### 6.1. Data parallelism

Data parallelism tạo một bản sao mô hình trên mỗi GPU hoặc nhóm GPU. Mỗi bản sao xử lý một phần dữ liệu khác nhau, sau đó đồng bộ gradient hoặc trạng thái cần thiết. Mô hình này thường dễ triển khai khi toàn bộ mô hình vừa bộ nhớ một GPU.

Giao tiếp chủ yếu là all-reduce gradient hoặc các thao tác đồng bộ tương đương. Tăng số GPU giúp tăng tổng batch hoặc giảm thời gian xử lý dữ liệu, nhưng đồng thời làm tăng chi phí đồng bộ. Khi batch nhỏ hoặc mô hình nhẹ, giao tiếp có thể chiếm tỷ lệ lớn.

### 6.2. Tensor parallelism

Tensor parallelism chia các tensor hoặc phép toán lớn thành các phần được xử lý trên nhiều GPU. Ví dụ, một phép nhân ma trận có thể được chia theo chiều hàng hoặc cột. Các GPU phải trao đổi kết quả trung gian, activation hoặc phần tensor cần thiết để tiếp tục lớp tiếp theo.

Vì giao tiếp có thể diễn ra thường xuyên giữa các lớp, tensor parallelism nhạy với độ trễ và băng thông liên kết. Thông thường, nên đặt các GPU tham gia cùng một nhóm tensor parallel trên node có kết nối GPU-to-GPU nhanh nếu topology cho phép. Nếu phải đi qua mạng giữa các node, cần đánh giá kỹ chi phí truyền và khả năng overlap.

### 6.3. Pipeline parallelism

Pipeline parallelism chia mô hình thành các stage, mỗi stage chạy trên một GPU hoặc nhóm GPU. Activation được gửi từ stage trước sang stage sau; gradient truyền ngược theo chiều ngược lại trong quá trình backpropagation.

Giao tiếp chủ yếu là point-to-point giữa các stage lân cận. Việc chia stage không đều khiến một số GPU hoàn thành sớm và chờ stage chậm nhất. Pipeline có thể giảm yêu cầu bộ nhớ trên mỗi GPU nhưng tạo ra bubble (thời gian rỗi) và cần điều chỉnh số micro-batch để cân bằng.

### 6.4. Sharding tham số và optimizer state

Với mô hình lớn, tham số, gradient hoặc optimizer state có thể được chia giữa các GPU thay vì giữ bản sao đầy đủ ở mỗi GPU. Các phương pháp như sharded data parallel hoặc ZeRO giảm bộ nhớ cần trên mỗi GPU bằng cách phân tán trạng thái. Khi tính toán cần một phần dữ liệu, hệ thống có thể all-gather hoặc reduce-scatter để tập hợp và phân phối các phần cần thiết.

Sharding giảm áp lực bộ nhớ nhưng làm tăng giao tiếp và yêu cầu đồng bộ. Việc chọn kích thước shard, thời điểm prefetch, thứ tự all-gather/reduce-scatter và overlap với compute ảnh hưởng trực tiếp đến hiệu năng.

### 6.5. Expert parallelism và all-to-all

Mixture of Experts (MoE) định tuyến token đến các expert khác nhau. Nếu expert được đặt trên nhiều GPU, token cần được gửi đến GPU chứa expert tương ứng và kết quả được gửi về. Mẫu giao tiếp này có thể tạo nhiều lưu lượng all-to-all, không chỉ một luồng all-reduce đồng đều.

MoE nhạy với phân bố token, tải giữa các expert, congestion và khả năng định tuyến. Nếu một số expert nhận quá nhiều token, các GPU chứa expert đó trở thành nút thắt. Cần theo dõi phân bố token, dung lượng buffer, số lần drop/capacity overflow và lưu lượng giữa node.

### 6.6. Ghép chiến lược với topology

| Chiến lược | Mẫu giao tiếp chính | Ưu tiên topology |
|---|---|---|
| Data parallel | All-reduce gradient hoặc đồng bộ trạng thái | Băng thông collective tốt trong node và giữa node |
| Tensor parallel | Nhiều lần trao đổi tensor/activation | Độ trễ thấp và băng thông GPU-to-GPU cao; ưu tiên nhóm GPU gần nhau |
| Pipeline parallel | Send/receive activation và gradient giữa stage | Đường truyền ổn định giữa các stage, phân chia stage cân bằng |
| Sharded data parallel | Reduce-scatter, all-gather và đồng bộ shard | Băng thông tốt, khả năng overlap và bộ nhớ đệm đủ |
| Expert parallel | All-to-all token và kết quả | Fabric liên node có thông lượng cao, kiểm soát congestion và cân bằng tải |

Một hệ thống có thể kết hợp nhiều chiến lược. Ví dụ, các GPU trong một node chạy tensor parallel, còn các node chạy data parallel. Khi đó, topology và thuật toán collective cần hiểu được cấu trúc phân cấp của nhóm GPU.

## 7. Thiết kế cluster GPU trên cloud

### 7.1. Chọn cấu hình node và GPU

Bắt đầu từ yêu cầu bộ nhớ GPU, năng lực tính toán, số GPU cần liên kết và mẫu giao tiếp. Một node có nhiều GPU không mặc nhiên tốt hơn nhiều node nhỏ; quyết định phụ thuộc vào việc workload cần trao đổi dữ liệu nhiều trong cùng máy hay có thể giao tiếp qua mạng.

Khi chọn loại instance hoặc máy chủ, kiểm tra:

- Số GPU trên node, dung lượng và băng thông bộ nhớ của từng GPU.
- GPU fabric: PCIe, NVLink, NVSwitch hoặc kết nối khác.
- Số NIC, tốc độ cổng, khả năng RDMA và GPUDirect RDMA.
- Topology CPU, NUMA, PCIe root complex và vị trí NIC so với GPU.
- Băng thông mạng giữa node, số rail và oversubscription của fabric.
- Khả năng cấp phát đồng thời đủ số node và GPU trong cùng vùng triển khai.
- Driver, CUDA/runtime, firmware, thư viện collective và image hệ điều hành được hỗ trợ.

Không chỉ dựa vào thông số tối đa của một GPU. Hãy kiểm tra băng thông thực tế của toàn đường truyền từ GPU nguồn đến GPU đích, gồm cả PCIe, NIC, switch và liên kết giữa các node.

### 7.2. Placement và nhóm máy chủ

Các node của một job phân tán cần được đặt sao cho đường truyền giữa chúng có hiệu năng ổn định. Nhiều nền tảng cloud có khái niệm placement group, cluster placement hoặc nhóm node gần nhau để giảm số hop và tăng tính dự đoán của mạng. Tên gọi và cam kết khác nhau theo nhà cung cấp.

Đối với job nhạy với giao tiếp, hãy kiểm tra:

- Các node có nằm trong cùng fabric hoặc miền mạng hiệu năng cao không?
- Có bị giới hạn bởi vùng khả dụng, rack hoặc fault domain không?
- Placement có bảo đảm topology hay chỉ là nỗ lực tốt nhất (best effort)?
- Có thể cấp phát toàn bộ node cùng lúc hay cluster phải khởi động từng phần?
- Khi một node lỗi, scheduler có thể thay node trong cùng nhóm phần cứng không?

Placement gần nhau có thể giảm độ trễ, nhưng có thể làm giảm phạm vi phân tán lỗi. Cần cân bằng yêu cầu hiệu năng với khả năng chịu lỗi của job. Với huấn luyện kéo dài nhiều ngày, checkpoint và khả năng khởi động lại thường quan trọng hơn việc tối ưu một vài microsecond trong một phép truyền đơn lẻ.

### 7.3. Cấu hình mạng và RDMA

Khi dùng RDMA hoặc RoCE, phải kiểm tra tính nhất quán trên toàn cluster: NIC, driver, firmware, subnet, MTU, routing, congestion control và thư viện truyền thông. Một node cấu hình khác biệt có thể khiến collective bị chậm hoặc không khởi tạo được.

Nếu sử dụng nhiều NIC hoặc nhiều rail, xác minh cách thư viện phân bổ lưu lượng qua từng rail. Kiểm tra băng thông thực tế theo cả một luồng và nhiều luồng đồng thời. Một NIC đơn lẻ có thể đạt thông lượng tốt trong benchmark nhỏ nhưng trở thành nút thắt khi tất cả GPU cùng gửi dữ liệu.

Không mở rộng mạng hiệu năng cao ra ngoài phạm vi cần thiết. Giới hạn quyền truy cập subnet, nhóm bảo mật và endpoint quản trị; tách traffic điều khiển khỏi traffic dữ liệu khi kiến trúc hỗ trợ. Kiểm tra yêu cầu mã hóa của dữ liệu và tác động hiệu năng của cơ chế bảo vệ được chọn.

### 7.4. Container, scheduler và thư viện giao tiếp

Workload GPU có thể chạy trong container để đóng gói runtime, thư viện và phụ thuộc. Tuy nhiên, container cần truy cập đúng GPU, NIC và driver được host cung cấp. Cần thống nhất phiên bản driver, CUDA/runtime, NCCL hoặc thư viện tương đương, framework và image giữa các node.

Scheduler phải cấp phát GPU theo đơn vị phù hợp, bảo đảm các tiến trình trong cùng job có rank và device mapping nhất quán. Với multi-node, cần cấu hình master address, port, rank, world size và interface mạng được dùng. Một tiến trình bị thiếu GPU hoặc chọn sai NIC có thể làm toàn bộ job lỗi hoặc giảm hiệu năng.

Khi chạy trong Kubernetes hoặc nền tảng điều phối khác, kiểm tra device plugin, resource request/limit, topology manager, node affinity, network plugin và cách expose RDMA device. Không nên giả định khai báo GPU resource tự động cấu hình được GPUDirect RDMA hoặc fabric hiệu năng cao.

## 8. Ví dụ giao tiếp phân tán với PyTorch

Ví dụ dưới đây minh họa một phép all-reduce đơn giản bằng `torch.distributed` với backend NCCL. Khi chạy thực tế, mỗi tiến trình thường được gán một GPU; biến môi trường do công cụ khởi chạy phân tán cung cấp rank và world size.

```python
import os
import torch
import torch.distributed as dist

def main():
    local_rank = int(os.environ["LOCAL_RANK"])
    torch.cuda.set_device(local_rank)

    dist.init_process_group(backend="nccl")

    value = torch.tensor(
        [float(dist.get_rank() + 1)],
        device=f"cuda:{local_rank}",
    )

    # Tổng hợp giá trị trên tất cả tiến trình và phân phối kết quả.
    dist.all_reduce(value, op=dist.ReduceOp.SUM)
    print(f"rank={dist.get_rank()}, result={value.item()}")

    dist.destroy_process_group()

if __name__ == "__main__":
    main()
```

Nếu có bốn tiến trình với giá trị ban đầu lần lượt là 1, 2, 3 và 4, kết quả sau all-reduce SUM là 10 trên mỗi tiến trình. Ví dụ chỉ minh họa collective; môi trường thực tế cần khởi chạy tiến trình trên các node, cấu hình rank/world size, interface mạng, quyền truy cập GPU và thư viện tương thích.

Có thể dùng `torchrun` hoặc bộ điều phối tương đương để khởi chạy. Cú pháp và biến môi trường cần theo phiên bản framework và cách triển khai cluster. Không nên sao chép một lệnh khởi chạy từ môi trường khác mà chưa xác minh interface mạng và ánh xạ GPU.

## 9. Quy trình thiết kế và tối ưu giao tiếp

### Bước 1: Mô tả mẫu giao tiếp của workload

Ghi lại loại dữ liệu được trao đổi, kích thước tensor, tần suất, số GPU tham gia, số node, hướng truyền và thời điểm cần đồng bộ. Phân biệt giao tiếp dày đặc như all-reduce với giao tiếp thưa hoặc không đều như all-to-all. Đo tỷ lệ thời gian tính toán và thời gian chờ giao tiếp ở baseline.

### Bước 2: Lập bản đồ topology

Thu thập sơ đồ GPU, CPU, NUMA, PCIe, NVLink/NVSwitch, NIC và switch mạng. Xác định cặp GPU nào có đường P2P, GPU nào chia sẻ PCIe uplink, NIC nào gần GPU nào và các điểm oversubscription. Lưu cấu hình theo loại node để so sánh khi cluster được cấp phát lại.

### Bước 3: Chọn chiến lược phân tán

Chọn data, tensor, pipeline, sharded hoặc expert parallelism theo kích thước mô hình, bộ nhớ GPU và mẫu giao tiếp. Có thể ghép chiến lược theo cấp: tensor parallel trong node, data parallel giữa node. Kiểm tra xem chiến lược đó có khớp topology và số GPU thực tế không.

### Bước 4: Kiểm tra đường truyền và thư viện

Xác minh PCIe P2P, NVLink/NVSwitch, RDMA và GPUDirect RDMA được hỗ trợ trên cấu hình cụ thể. Đồng bộ driver, firmware, runtime và thư viện collective. Xác định fallback khi đường truyền trực tiếp không khả dụng.

### Bước 5: Benchmark từng lớp

Đo copy host-to-device, device-to-host, GPU-to-GPU trong node, NIC-to-NIC giữa node và collective ở nhiều kích thước thông điệp. So sánh một node với nhiều node, một luồng với nhiều luồng, và đo theo cả chiều gửi/nhận. Dùng công cụ benchmark phù hợp như CUDA sample, NCCL tests hoặc benchmark của nhà cung cấp; ghi lại phiên bản và cấu hình.

### Bước 6: Tối ưu overlap và cân bằng tải

Điều chỉnh bucket, số micro-batch, số worker data loader, pinned memory, stream và thời điểm đồng bộ. Theo dõi GPU idle time, network utilization và thời gian chờ collective. Nếu một GPU hoặc stage chậm hơn, tìm nguyên nhân từ phân bổ dữ liệu, topology, nhiệt độ, giới hạn công suất hoặc tranh chấp mạng.

### Bước 7: Kiểm tra ở quy mô production

Chạy thử với số node, số GPU, batch size, kích thước mô hình và thời lượng gần production. Đo khi nhiều job cùng chia sẻ fabric. Kiểm tra checkpoint, node failure, restart và thời gian khôi phục. Ghi lại throughput hữu ích, không chỉ băng thông truyền thô.

## 10. Đo lường và chẩn đoán

### 10.1. Chỉ số cần theo dõi

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| GPU | GPU utilization, memory utilization, memory bandwidth, power, temperature | Xác định GPU có đang tính toán hay bị chờ dữ liệu |
| Liên kết trong node | PCIe throughput, NVLink throughput, P2P bandwidth, transfer latency | Xác định đường truyền giữa GPU và host có bị giới hạn không |
| Mạng liên node | NIC throughput, packet drops, retransmission, RDMA errors, congestion | Xác định fabric có nghẽn hoặc có lỗi cấu hình không |
| Collective | Thời gian all-reduce/all-gather/all-to-all, kích thước dữ liệu, số rank | Đánh giá chi phí giao tiếp thực tế của framework |
| Framework | Step time, data loading time, compute time, communication wait, overlap ratio | Xác định giao tiếp chiếm bao nhiêu thời gian của một bước |
| Cluster | Node health, job restart, checkpoint duration, queue time | Đánh giá khả năng vận hành ở quy mô lớn |

### 10.2. Đọc kết quả benchmark

Benchmark cần đo nhiều kích thước dữ liệu. Với thông điệp nhỏ, độ trễ và overhead khởi tạo thường chi phối. Với thông điệp lớn, băng thông hữu ích và congestion thường quan trọng hơn. Chạy benchmark trên từng cặp GPU hoặc từng node trước khi chạy collective toàn cluster để xác định lớp nào đang giới hạn.

Đo cả thời gian một chiều và hai chiều khi có thể. Một liên kết có thể có băng thông tổng hai chiều khác với băng thông mỗi chiều. Đọc kỹ đơn vị: Gb/s (gigabit mỗi giây) khác GB/s (gigabyte mỗi giây), với 8 bit bằng 1 byte trước khi xét overhead.

Không so sánh kết quả benchmark nếu khác phiên bản driver, runtime, thư viện, số GPU, số node, topology, kích thước thông điệp hoặc cấu hình mạng. Ghi lại các thông tin này cùng kết quả để lần đo sau có thể tái lập.

### 10.3. Một số dấu hiệu thường gặp

- GPU utilization thấp trong lúc all-reduce kéo dài: có thể bị giới hạn bởi mạng, liên kết GPU hoặc đồng bộ tiến trình.
- Một node chậm hơn các node còn lại: kiểm tra NIC, driver, PCIe topology, CPU affinity, nhiệt độ và trạng thái phần cứng.
- Throughput tốt ở một node nhưng giảm mạnh khi thêm node: kiểm tra fabric, oversubscription, collective algorithm và số rail.
- Truyền host-to-device chậm: kiểm tra pinned memory, PCIe, NUMA và data loader.
- RDMA không khởi tạo: kiểm tra NIC được expose, driver, firmware, subnet, MTU, quyền thiết bị và cấu hình thư viện.
- Collective bị treo: kiểm tra rank/world size, thứ tự collective, lỗi tiến trình, timeout và log của mọi node.
- Hiệu năng giảm khi chạy nhiều job: kiểm tra tranh chấp NIC, switch, PCIe, CPU và chính sách chia sẻ tài nguyên.

## 11. Độ tin cậy và khả năng phục hồi

Một job phân tán phụ thuộc vào nhiều GPU, node, NIC và switch. Chỉ cần một thành phần bị lỗi hoặc một tiến trình bị treo, collective có thể không hoàn tất và toàn bộ job phải chờ. Vì vậy, hệ thống cần theo dõi sức khỏe thiết bị, phát hiện tiến trình mất kết nối và có kế hoạch khôi phục.

Các biện pháp nên cân nhắc:

- Kiểm tra GPU, ECC error, nhiệt độ, công suất và trạng thái NIC trước khi nhận job.
- Dùng health check và timeout cho tiến trình giao tiếp; ghi log có rank, node và thời điểm.
- Lưu checkpoint định kỳ, gồm trạng thái mô hình, optimizer, scheduler và tiến độ dữ liệu khi cần.
- Thiết kế quy trình restart toàn job hoặc khởi tạo lại nhóm tiến trình khi một rank lỗi.
- Xác định rõ job có thể co giãn số worker hay phải khởi động lại với world size cố định.
- Kiểm thử node failure, mất kết nối, switch maintenance và khôi phục từ checkpoint.
- Theo dõi tuổi thọ job, tỷ lệ restart và thời gian từ lỗi đến khi tiếp tục huấn luyện.

Không phải mọi framework đều hỗ trợ elastic training cho mọi kiểu parallelism. Một số mô hình cần khởi động lại toàn bộ nhóm GPU để bảo đảm trạng thái nhất quán. Cần xác minh giới hạn framework và kiểm thử quy trình khôi phục thay vì giả định scheduler tự động thay node là đủ.

## 12. Bảo mật khi truyền dữ liệu GPU

Giao tiếp tốc độ cao vẫn cần bảo vệ dữ liệu và ranh giới giữa các workload. RDMA và GPUDirect RDMA giảm overhead truyền dữ liệu, nhưng không thay thế cơ chế xác thực, phân quyền và phân đoạn mạng. Cần bảo đảm chỉ tiến trình được phép mới có thể đăng ký hoặc truy cập vùng nhớ liên quan.

Các điểm kiểm soát:

- Phân tách project, tenant, node pool và mạng quản trị với mạng dữ liệu huấn luyện.
- Cấp quyền GPU/NIC theo job; không expose thiết bị đặc quyền cho container không tin cậy.
- Giới hạn quyền truy cập RDMA device, memory registration và endpoint mạng.
- Mã hóa dữ liệu khi truyền nếu yêu cầu bảo mật hoặc chính sách dữ liệu bắt buộc; đo tác động hiệu năng của cơ chế mã hóa.
- Bảo vệ checkpoint, dataset, log và model artifact bằng IAM và mã hóa phù hợp.
- Ghi audit log cho việc cấp phát GPU, thay đổi network policy và truy cập dữ liệu.
- Cập nhật driver, firmware, kernel và thư viện giao tiếp theo quy trình kiểm thử.

Trong môi trường đa tenant, cần xác minh cách nhà cung cấp cloud cô lập GPU memory, NIC và RDMA resources giữa VM hoặc container. Chỉ sử dụng tính năng chia sẻ GPU hoặc fabric khi mô hình cô lập và giới hạn tài nguyên đáp ứng yêu cầu của workload.

## 13. Chi phí và hiệu quả mở rộng

Cluster nhiều GPU có thể tăng throughput, nhưng chi phí tăng theo GPU, node, mạng, storage, license phần mềm và thời gian vận hành. Khi giao tiếp trở thành nút thắt, thêm GPU có thể làm chi phí tăng nhanh hơn tốc độ hoàn thành công việc.

Các khoản cần tính gồm:

- Giá GPU và máy chủ, thời gian node được giữ và chi phí capacity reservation nếu có.
- NIC tốc độ cao, fabric, placement group hoặc dịch vụ mạng chuyên dụng.
- Storage dataset, checkpoint, cache và lưu lượng truyền dữ liệu.
- Phí truyền dữ liệu giữa vùng hoặc ra ngoài cloud nếu có.
- Phần mềm, framework, license, quan sát và hỗ trợ kỹ thuật.
- Thời gian GPU nhàn rỗi do chờ collective, data loader hoặc node chậm.
- Chi phí checkpoint, restart và job thất bại.

Đánh giá hiệu quả mở rộng bằng throughput trên mỗi GPU, thời gian hoàn thành một epoch hoặc một tác vụ, chi phí trên một triệu token/ảnh/mẫu xử lý và mức sử dụng GPU thực tế. So sánh cấu hình một node nhiều GPU với nhiều node ít GPU bằng workload giống nhau. Cấu hình có nhiều GPU hơn chưa chắc có hiệu quả chi phí tốt hơn nếu mạng liên node chậm.

Một cách nhìn đơn giản:

\[
Efficiency_{scaling} = \frac{Throughput_{N\ GPUs}}{N \times Throughput_{1\ GPU}}
\]

Giá trị gần 1 cho thấy throughput tăng gần tuyến tính theo số GPU; giá trị thấp hơn cho thấy chi phí giao tiếp, đồng bộ hoặc phân bổ tài nguyên đang làm giảm hiệu quả. Đây là chỉ số tham khảo; cần so sánh trong cùng điều kiện và xét cả batch size, chất lượng hội tụ hoặc độ chính xác kết quả.

## 14. Ví dụ kiến trúc

### Ví dụ 1: Huấn luyện data parallel trên nhiều node

Một nhóm cần huấn luyện mô hình có thể vừa bộ nhớ một GPU. Mỗi GPU xử lý một mini-batch khác nhau và đồng bộ gradient bằng all-reduce.

**Thiết kế:** mỗi node có nhiều GPU; trong node sử dụng NVLink/NVSwitch hoặc PCIe P2P theo topology. Giữa node dùng NIC tốc độ cao và RDMA nếu nền tảng hỗ trợ. Collective được tổ chức phân cấp để tận dụng liên kết nội bộ trước khi truyền qua fabric mạng. Dùng checkpoint định kỳ để giảm thiệt hại khi node lỗi.

**Điểm cần đo:** thời gian all-reduce, băng thông NIC, GPU idle time, step time và scaling efficiency khi tăng số node.

### Ví dụ 2: Tensor parallel cho mô hình lớn

Một mô hình ngôn ngữ có lớp tuyến tính lớn cần chia tensor trên nhiều GPU. Mỗi lớp có thể trao đổi activation hoặc kết quả trung gian nhiều lần.

**Thiết kế:** ưu tiên đặt các GPU trong cùng tensor-parallel group trên một node có GPU fabric băng thông cao. Nếu phải chia group qua nhiều node, dùng cluster có fabric RDMA phù hợp và benchmark ở kích thước batch/sequence thực tế. Có thể kết hợp pipeline parallel giữa các node để giảm giao tiếp trực tiếp giữa mọi GPU.

**Điểm cần đo:** latency của collective, băng thông GPU-to-GPU, thời gian forward/backward, memory pressure và tỷ lệ overlap.

### Ví dụ 3: MoE với expert parallelism

Một mô hình MoE định tuyến token đến các expert nằm trên nhiều GPU. Dữ liệu token được phân phối bằng all-to-all và kết quả được gom lại.

**Thiết kế:** phân bố expert để cân bằng tải và hạn chế lưu lượng đi qua các node xa. Dùng fabric có thông lượng cao, theo dõi congestion và phân bố token. Điều chỉnh capacity factor, batch và routing để tránh một số expert nhận quá nhiều token.

**Điểm cần đo:** all-to-all time, bytes sent/received theo rank, token imbalance, dropped token và thời gian chờ do node chậm.

## 15. Sai lầm thường gặp

- **Chỉ so sánh số GPU:** bỏ qua topology, NIC, switch, NUMA và băng thông liên kết thực tế.
- **Đồng nhất PCIe với NVLink:** hai công nghệ có đặc tính và băng thông khác nhau; cần đọc topology của hệ thống.
- **Cho rằng RDMA luôn truyền trực tiếp từ GPU:** RDMA có thể vẫn dùng host staging nếu không có GPUDirect RDMA hoặc cấu hình tương thích.
- **Chỉ benchmark một cặp GPU:** kết quả đơn luồng không phản ánh congestion khi toàn cluster truyền đồng thời.
- **Chọn parallelism không khớp workload:** tensor parallel có thể tạo giao tiếp quá dày trên mạng liên node; pipeline parallel có thể tạo bubble nếu chia stage lệch.
- **Bỏ qua NUMA và NIC affinity:** tiến trình CPU và buffer đặt xa thiết bị có thể làm giảm throughput.
- **Tối ưu thông điệp mà không đo:** bucket quá lớn hoặc quá nhỏ đều có thể giảm hiệu năng.
- **Không kiểm tra thứ tự collective:** một rank gọi sai thứ tự có thể khiến các rank còn lại bị treo.
- **Cho rằng thêm node luôn tăng tốc:** fabric, storage hoặc scheduler có thể trở thành nút thắt.
- **Không chuẩn bị checkpoint:** lỗi một node có thể làm mất toàn bộ tiến độ của job dài.
- **Mở quyền RDMA/GPU quá rộng:** tăng nguy cơ truy cập thiết bị hoặc bộ nhớ ngoài phạm vi job.

## 16. Checklist trước khi triển khai cluster nhiều GPU

- [ ] Đã xác định mẫu giao tiếp, kích thước tensor, tần suất và số GPU tham gia.
- [ ] Đã kiểm tra topology GPU, CPU, NUMA, PCIe, NVLink/NVSwitch và NIC.
- [ ] Đã xác minh P2P, RDMA và GPUDirect RDMA trên đúng cấu hình cloud.
- [ ] Đã chọn fabric mạng, số NIC/rail và placement phù hợp với job.
- [ ] Đã chọn data, tensor, pipeline, sharded hoặc expert parallelism theo workload.
- [ ] Đã đồng bộ driver, firmware, CUDA/runtime, framework và thư viện collective.
- [ ] Đã cấu hình rank, world size, GPU mapping và network interface nhất quán.
- [ ] Đã benchmark copy, P2P, RDMA và collective ở nhiều kích thước thông điệp.
- [ ] Đã đo step time, GPU idle time, communication wait và scaling efficiency.
- [ ] Đã tối ưu pinned memory, NUMA affinity, batching và overlap khi có lợi.
- [ ] Đã kiểm thử node failure, timeout, restart và khôi phục từ checkpoint.
- [ ] Đã giới hạn quyền GPU/NIC/RDMA và bảo vệ dữ liệu, model, checkpoint.
- [ ] Đã tính chi phí GPU, node, fabric, storage, egress và thời gian nhàn rỗi.

## 17. Kết luận

Hiệu năng của hệ thống nhiều GPU phụ thuộc vào toàn bộ đường đi của dữ liệu. Trong một node, PCIe, P2P, NVLink và NVSwitch quyết định cách GPU trao đổi với CPU, RAM và GPU khác. Giữa các node, NIC, switch fabric, RDMA và GPUDirect RDMA quyết định độ trễ, băng thông và overhead của giao tiếp phân tán.

Hãy bắt đầu từ mẫu giao tiếp của workload, đọc topology thực tế, chọn chiến lược phân tán phù hợp và benchmark từng lớp trước khi mở rộng cluster. Tối ưu collective, NUMA, pinned memory và overlap có thể cải thiện mức sử dụng GPU; checkpoint, giám sát và kiểm soát quyền truy cập giúp job ổn định và an toàn. Quyết định cuối cùng cần cân bằng throughput hữu ích, khả năng phục hồi và chi phí trên toàn cluster.

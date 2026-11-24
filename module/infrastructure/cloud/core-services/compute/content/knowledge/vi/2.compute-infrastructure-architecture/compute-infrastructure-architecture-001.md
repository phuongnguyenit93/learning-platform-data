# Máy chủ vật lý, hypervisor và cơ chế ảo hóa máy chủ

Máy chủ vật lý là nền tảng phần cứng cung cấp năng lực tính toán, bộ nhớ, lưu trữ và kết nối mạng cho ứng dụng. Trong môi trường đám mây, một máy chủ vật lý thường không chạy trực tiếp một ứng dụng duy nhất. Thay vào đó, một lớp phần mềm gọi là **hypervisor** có thể chia sẻ tài nguyên của máy chủ cho nhiều máy ảo (virtual machine – VM). Mỗi VM có hệ điều hành, CPU ảo, bộ nhớ ảo, thiết bị lưu trữ và giao diện mạng riêng.

Ảo hóa máy chủ là một trong những nền tảng quan trọng giúp nhà cung cấp cloud gom tài nguyên từ nhiều máy chủ, cấp phát theo nhu cầu, cô lập workload và di chuyển máy ảo khi bảo trì. Hiểu được phần cứng vật lý và cách hypervisor quản lý tài nguyên giúp kỹ sư lựa chọn cấu hình VM, chẩn đoán hiệu năng, thiết kế tính sẵn sàng và đánh giá chi phí.

Bài học tập trung vào ba nội dung liên kết với nhau:

- **Máy chủ vật lý:** các thành phần CPU, RAM, lưu trữ, mạng, firmware và cách chúng ảnh hưởng đến workload.
- **Hypervisor:** lớp điều khiển tạo và vận hành máy ảo, phân phối tài nguyên và cô lập các VM.
- **Ảo hóa máy chủ:** cơ chế biến tài nguyên vật lý thành tài nguyên ảo, bao gồm CPU, bộ nhớ, lưu trữ và mạng.

## 1. Máy chủ vật lý trong hạ tầng cloud

Máy chủ vật lý (physical server hoặc bare-metal server) là một máy tính chuyên dụng được thiết kế để hoạt động liên tục trong trung tâm dữ liệu. Máy thường được lắp trong rack, kết nối với nguồn điện dự phòng, hệ thống làm mát, mạng nội bộ và hệ thống giám sát tập trung.

Máy chủ có thể chạy trực tiếp hệ điều hành và ứng dụng. Mô hình này thường được gọi là bare metal khi workload sử dụng máy vật lý mà không chạy qua lớp hypervisor của người dùng. Trong môi trường ảo hóa, máy chủ vật lý trở thành **host** (máy chủ chủ), còn các VM chạy bên trên được gọi là **guest** (máy khách).

### 1.1. Các thành phần phần cứng chính

| Thành phần | Vai trò | Ảnh hưởng đến workload |
|---|---|---|
| CPU và socket | Thực thi lệnh, điều phối luồng xử lý | Số lõi, xung nhịp, cache và kiến trúc ảnh hưởng năng lực tính toán |
| RAM | Lưu dữ liệu và mã đang được xử lý | Dung lượng, băng thông, độ trễ và cấu trúc NUMA ảnh hưởng ứng dụng |
| Storage | Lưu hệ điều hành, dữ liệu và image VM | IOPS, thông lượng, độ trễ, độ bền và khả năng chịu lỗi |
| NIC (Network Interface Card) | Kết nối máy chủ với mạng | Băng thông, số hàng đợi, offload và độ trễ ảnh hưởng truyền dữ liệu |
| Mainboard và chipset | Kết nối CPU, RAM, thiết bị ngoại vi | Số khe mở rộng, làn PCIe và hỗ trợ thiết bị |
| PSU và hệ thống làm mát | Cung cấp điện và duy trì nhiệt độ | Ảnh hưởng độ ổn định và khả năng vận hành liên tục |
| BMC | Quản trị phần cứng độc lập với hệ điều hành host | Cho phép theo dõi cảm biến, bật/tắt nguồn và truy cập console từ xa |
| HBA/RAID controller | Kết nối hoặc quản lý thiết bị lưu trữ | Ảnh hưởng đường đi I/O, tính dự phòng và cách trình bày volume |

CPU thường được mô tả bằng socket, core và thread. Socket là vị trí lắp bộ xử lý; mỗi CPU có nhiều core; một số CPU hỗ trợ nhiều hardware thread trên mỗi core thông qua công nghệ SMT. Số thread logic không đồng nghĩa với số core vật lý và cũng không bảo đảm hiệu năng tăng theo cùng tỷ lệ. Khi lập kế hoạch dung lượng, cần xem cả kiến trúc CPU, xung nhịp, cache, giới hạn điện năng và loại workload.

RAM thường được lắp theo các kênh bộ nhớ gắn với từng socket CPU. Cấu hình đúng số kênh và đúng vị trí DIMM có thể cải thiện băng thông. Máy chủ nhiều socket thường có kiến trúc **NUMA** (Non-Uniform Memory Access): mỗi socket có vùng bộ nhớ cục bộ truy cập nhanh hơn vùng bộ nhớ gắn với socket khác. Workload nhạy với độ trễ bộ nhớ có thể giảm hiệu năng nếu CPU thường xuyên truy cập RAM từ NUMA node xa.

Lưu trữ trong máy chủ có thể là SSD SATA, NVMe, HDD hoặc thiết bị kết nối qua SAN. RAID có thể tăng khả năng chịu lỗi hoặc hiệu năng tùy cấp RAID, nhưng RAID không thay thế backup. Một hệ thống lưu trữ còn phải xem xét controller, cache, đường kết nối, firmware, nguồn điện và cơ chế nhân bản.

NIC có thể hỗ trợ nhiều hàng đợi nhận/gửi, checksum offload, segmentation offload và SR-IOV. Các tính năng này giúp giảm tải CPU hoặc tăng khả năng chia sẻ thiết bị, nhưng hiệu quả phụ thuộc driver, firmware, hypervisor và cấu hình mạng.

### 1.2. Firmware, khởi động và quản trị ngoài băng

Firmware của máy chủ khởi tạo phần cứng trước khi hệ điều hành hoặc hypervisor khởi động. BIOS/UEFI cung cấp cấu hình khởi động, Secure Boot và một số tùy chọn bảo mật. Với máy chủ hỗ trợ ảo hóa, firmware cần bật các tính năng phần cứng tương ứng, chẳng hạn Intel VT-x hoặc AMD-V cho CPU virtualization; VT-d hoặc AMD-Vi cho I/O memory management.

BMC (Baseboard Management Controller) hoạt động độc lập với hệ điều hành chính. Quản trị viên có thể dùng giao diện quản trị ngoài băng (out-of-band management) để xem trạng thái nguồn, nhiệt độ, quạt, log phần cứng, gắn ảnh cài đặt từ xa hoặc khởi động lại host khi hệ điều hành bị treo. Vì BMC có quyền kiểm soát mạnh đối với máy chủ, giao diện này cần nằm trong mạng quản trị riêng, dùng xác thực mạnh và được cập nhật firmware.

### 1.3. Đặc tính vật lý ảnh hưởng đến năng lực

Thông số ghi trên nhãn phần cứng chưa đủ để kết luận một host có thể chạy bao nhiêu VM. Hiệu năng thực tế còn phụ thuộc:

- Mức sử dụng CPU đồng thời và mức tranh chấp giữa các workload.
- Dung lượng RAM khả dụng sau khi trừ phần dành cho hypervisor và hệ thống quản trị.
- Băng thông RAM, NUMA placement và tỷ lệ truy cập bộ nhớ từ xa.
- Độ trễ và thông lượng của thiết bị lưu trữ, cũng như mức tranh chấp I/O giữa các VM.
- Băng thông NIC, số hàng đợi, giới hạn switch và đường truyền phía trên.
- Giới hạn nhiệt, điện năng và chính sách điều chỉnh xung nhịp của CPU.

Một host có nhiều core nhưng lưu trữ chậm có thể chạy tốt các dịch vụ tính toán thuần CPU nhưng kém phù hợp với nhiều cơ sở dữ liệu cùng hoạt động. Tương tự, host có RAM lớn nhưng băng thông mạng thấp có thể không đáp ứng workload truyền dữ liệu lớn.

## 2. Từ máy vật lý đến máy ảo

Nếu cài trực tiếp một hệ điều hành lên mỗi máy vật lý, một phần tài nguyên có thể bị bỏ trống khi ứng dụng không dùng hết công suất. Mỗi ứng dụng cũng có thể cần phiên bản hệ điều hành, thư viện hoặc cấu hình riêng, làm tăng số máy phải mua, cấp điện, làm mát và bảo trì.

Ảo hóa giải quyết một phần vấn đề bằng cách tạo nhiều môi trường máy tính logic trên cùng một host. Hypervisor quản lý quyền sử dụng CPU, RAM, thiết bị lưu trữ và mạng của các VM. Mỗi VM nhìn thấy một tập phần cứng ảo mà hệ điều hành guest có thể sử dụng như một máy tính riêng.

Ví dụ, một máy chủ vật lý có 16 core và 32 hardware thread cùng 256 GiB RAM có thể chạy nhiều VM. Mỗi VM được cấu hình một số vCPU và dung lượng RAM nhất định. Tổng cấu hình vCPU được cấp cho các VM có thể lớn hơn số thread logic vật lý nếu nhà vận hành chấp nhận overcommit và workload không sử dụng tối đa CPU cùng lúc. Tổng RAM cấp phát cũng có thể được quản lý theo chính sách riêng, nhưng không thể giả định rằng mọi VM đều có thể sử dụng đủ RAM đồng thời nếu host không có dung lượng thực hoặc cơ chế thu hồi an toàn.

Ảo hóa tạo ra sự linh hoạt trong cấp phát, nhưng không tạo thêm tài nguyên vật lý. Khi nhiều VM cùng tranh chấp một tài nguyên, hiệu năng có thể giảm. Do đó, cần phân biệt **tài nguyên được cấu hình cho VM** với **năng lực vật lý thực sự có thể cung cấp tại cùng thời điểm**.

## 3. Hypervisor là gì?

**Hypervisor** (còn gọi là virtual machine monitor – VMM) là phần mềm hoặc lớp hệ thống quản lý máy ảo. Nó tạo môi trường thực thi cho guest, phân phối tài nguyên phần cứng và kiểm soát truy cập giữa các VM.

Các nhiệm vụ chính của hypervisor gồm:

1. Tạo, khởi động, tạm dừng, tiếp tục và tắt VM.
2. Cấp vCPU, ánh xạ bộ nhớ guest và quản lý truy cập thiết bị ảo.
3. Lập lịch sử dụng CPU vật lý giữa các vCPU.
4. Cung cấp thiết bị lưu trữ và giao diện mạng ảo.
5. Áp dụng ranh giới cô lập giữa các VM.
6. Theo dõi tài nguyên, hỗ trợ snapshot, migration hoặc HA tùy nền tảng.

Hypervisor là thành phần nền tảng của nhiều dịch vụ VM trên cloud. Người dùng cloud thường thao tác qua API hoặc giao diện quản trị để tạo VM; phía nhà cung cấp chịu trách nhiệm quản lý host, hypervisor, mạng và lưu trữ nền.

## 4. Hypervisor Type 1 và Type 2

Hypervisor thường được chia thành hai nhóm theo vị trí trong kiến trúc hệ thống.

### 4.1. Type 1 – bare-metal hypervisor

Type 1 chạy trực tiếp trên phần cứng máy chủ hoặc trên một lớp nền tảng rất mỏng được thiết kế cho ảo hóa. Nó kiểm soát tài nguyên host và cung cấp môi trường chạy VM. Hệ thống quản trị có thể chạy trong một management domain hoặc thành phần riêng tùy kiến trúc sản phẩm.

Các ví dụ phổ biến gồm VMware ESXi, Microsoft Hyper-V khi triển khai theo kiến trúc hypervisor của nó và Xen. KVM trên Linux cũng là nền tảng ảo hóa kiểu Type 1 về mặt kiến trúc: module KVM trong kernel Linux cung cấp khả năng hypervisor, còn các tiến trình user space như QEMU và công cụ quản trị hỗ trợ thiết bị và vòng đời VM.

Type 1 thường được dùng trong trung tâm dữ liệu và môi trường cloud vì có thể tối ưu cho quản lý host, hiệu năng, cô lập và vận hành tập trung.

### 4.2. Type 2 – hosted hypervisor

Type 2 chạy như một ứng dụng trên hệ điều hành chủ (host operating system). Hệ điều hành chủ quản lý thiết bị vật lý và cung cấp dịch vụ nền; hypervisor dùng các dịch vụ đó để tạo VM.

Ví dụ gồm Oracle VirtualBox và VMware Workstation. Mô hình này thuận tiện cho máy tính cá nhân, phòng lab, học tập, kiểm thử hệ điều hành hoặc chạy môi trường phát triển. Tuy nhiên, nó thêm một lớp phụ thuộc vào hệ điều hành chủ và không thường là lựa chọn chính cho hạ tầng cloud quy mô lớn.

### 4.3. So sánh hai loại

| Tiêu chí | Type 1 | Type 2 |
|---|---|---|
| Vị trí chạy | Trực tiếp trên host phần cứng hoặc lớp nền ảo hóa chuyên dụng | Ứng dụng chạy trên hệ điều hành chủ |
| Mục đích thường gặp | Trung tâm dữ liệu, cloud, máy chủ doanh nghiệp | Desktop, lab, phát triển và kiểm thử |
| Quản trị | Thường tích hợp nền tảng quản lý host/cluster | Thường do người dùng quản lý trên máy cá nhân |
| Phụ thuộc | Phụ thuộc hỗ trợ phần cứng và hệ sinh thái hypervisor | Phụ thuộc cả hệ điều hành chủ và hypervisor |
| Hiệu năng | Có thể giảm lớp trung gian và tối ưu cho workload máy chủ | Có thêm lớp hệ điều hành chủ; hiệu năng phụ thuộc máy và ứng dụng |

Không nên kết luận Type 1 luôn nhanh hơn Type 2 trong mọi tình huống. Kết quả phụ thuộc phiên bản, driver, workload, cấu hình và phần cứng. Điểm khác biệt quan trọng là vị trí của hypervisor trong kiến trúc và mục tiêu vận hành của từng loại.

## 5. Các thành phần trong kiến trúc ảo hóa

Một hệ thống ảo hóa trong trung tâm dữ liệu thường có các lớp sau:

~~~mermaid
flowchart TB
    subgraph VM["Máy ảo (guest)"]
        GOS["Hệ điều hành guest"]
        APP["Ứng dụng và thư viện"]
        VDEV["vCPU · RAM ảo · đĩa ảo · NIC ảo"]
        GOS --> APP
        GOS --- VDEV
    end
    HYP["Hypervisor / Virtual Machine Monitor"]
    HOST["Máy chủ vật lý: CPU · RAM · PCIe · NIC · Storage"]
    MGMT["Nền tảng quản trị và điều phối"]
    NET["Switch ảo / mạng vật lý"]
    STORE["Datastore / SAN / NVMe / Block Storage"]
    VM --> HYP
    HYP --> HOST
    MGMT --> HYP
    HYP --> NET
    HYP --> STORE
~~~

**Host** là máy vật lý cung cấp tài nguyên. **Guest** là hệ điều hành chạy trong VM. **Virtual hardware** là tập thiết bị mà guest nhìn thấy, ví dụ bộ xử lý ảo, bộ điều khiển đĩa và card mạng ảo. **Datastore** là nơi lưu file đĩa VM và các thành phần cấu hình. **Management plane** là lớp quản trị dùng để tạo, phân quyền, giám sát và điều phối VM.

Trong môi trường có nhiều host, nền tảng quản lý cluster có thể phân bổ VM lên các host, cân bằng tải, thực hiện migration và khởi động lại VM khi host gặp lỗi. Lớp quản trị có thể tách biệt khỏi đường dữ liệu của VM; vì vậy, sự cố management plane không nhất thiết làm VM đang chạy dừng ngay lập tức, nhưng có thể khiến việc điều khiển và khôi phục trở nên khó khăn.

## 6. Cơ chế ảo hóa CPU

Guest OS cần tưởng rằng mình có CPU riêng. Hypervisor cung cấp một hoặc nhiều **vCPU** cho VM và ánh xạ các vCPU đó lên các CPU thread vật lý khi chúng được lập lịch chạy.

### 6.1. vCPU và pCPU

- **pCPU** thường chỉ core hoặc hardware thread vật lý mà hypervisor có thể lập lịch.
- **vCPU** là CPU logic được trình bày cho một VM.
- **vCPU scheduling** là quá trình hypervisor chọn vCPU nào được chạy trên CPU vật lý tại một thời điểm.

Nếu một VM có 4 vCPU, điều đó không nhất thiết có nghĩa VM được dành riêng 4 core vật lý trong mọi thời điểm. Tùy nền tảng, vCPU có thể chia sẻ thời gian CPU với VM khác. Khi host quá tải, vCPU phải chờ lượt và độ trễ ứng dụng tăng.

### 6.2. Hardware-assisted virtualization

Các bộ xử lý hiện đại hỗ trợ phần mở rộng ảo hóa như Intel VT-x và AMD-V. Những tính năng này cung cấp chế độ thực thi và cơ chế chuyển quyền điều khiển cần thiết để hypervisor chạy guest một cách hiệu quả và an toàn.

Khi guest thực hiện thao tác nhạy cảm, phần cứng và hypervisor phối hợp để kiểm soát thao tác đó. Hypervisor có thể can thiệp khi guest truy cập tài nguyên cần quản lý hoặc khi xảy ra một sự kiện ảo hóa. Nhờ hỗ trợ phần cứng, nhiều thao tác không cần mô phỏng hoàn toàn bằng phần mềm.

### 6.3. CPU overcommit và tranh chấp

CPU overcommit xảy ra khi tổng số vCPU được cấp cho các VM lớn hơn số CPU vật lý có thể chạy đồng thời. Đây là kỹ thuật phổ biến vì nhiều workload có thời gian nhàn rỗi hoặc không sử dụng hết CPU cùng lúc. Tuy nhiên, tỷ lệ overcommit an toàn phụ thuộc đặc tính workload, yêu cầu độ trễ và mức sử dụng đỉnh.

Các dấu hiệu tranh chấp CPU gồm:

- CPU ready hoặc thời gian vCPU chờ được lập lịch tăng.
- Độ trễ ứng dụng tăng dù mức sử dụng CPU trong guest không luôn đạt 100%.
- Thời gian hoàn thành job biến động khi các VM khác tăng tải.
- Host có mức sử dụng CPU cao kéo dài.

Không nên đặt một tỷ lệ overcommit cố định cho mọi host. Workload xử lý batch có thể chấp nhận chờ CPU hơn API thời gian thực. Với workload nhạy độ trễ, có thể dùng reservation, giới hạn, affinity hoặc dedicated host nếu nền tảng hỗ trợ và yêu cầu đủ rõ ràng.

### 6.4. Topology CPU và NUMA

VM lớn chạy trên host nhiều socket cần được bố trí vCPU và RAM phù hợp với NUMA. Nếu một VM có nhiều vCPU hơn năng lực của một NUMA node, hypervisor có thể phải phân bổ tài nguyên qua nhiều node. Điều này không phải lúc nào cũng gây vấn đề, nhưng có thể làm tăng độ trễ truy cập bộ nhớ.

Khi cấp phát VM hiệu năng cao, hãy kiểm tra số socket ảo, số core mỗi socket, NUMA topology mà guest nhìn thấy và chính sách pinning nếu cần. Không nên tự ý pin mọi vCPU vào core vật lý khi chưa đo, vì pinning cứng có thể làm giảm khả năng lập lịch tổng thể.

## 7. Cơ chế ảo hóa bộ nhớ

Guest OS quản lý không gian địa chỉ bộ nhớ của chính nó. Hypervisor phải ánh xạ địa chỉ mà guest sử dụng tới vị trí bộ nhớ thực trên host. Cơ chế ánh xạ hai tầng này thường được hỗ trợ bởi phần cứng như Intel EPT (Extended Page Tables) hoặc AMD NPT (Nested Page Tables).

### 7.1. Bộ nhớ cấu hình cho VM

Khi tạo VM, quản trị viên đặt dung lượng RAM ảo, chẳng hạn 8 GiB. Guest OS nhìn thấy lượng RAM đó và tự quản lý việc cấp phát cho tiến trình. Hypervisor chịu trách nhiệm bảo đảm các trang bộ nhớ của guest được ánh xạ vào bộ nhớ host theo chính sách nền tảng.

Tổng RAM cấu hình cho VM có thể nhỏ hơn, bằng hoặc lớn hơn RAM vật lý khả dụng tùy nền tảng và chính sách overcommit. Nhưng nếu nhiều VM đồng thời cần toàn bộ RAM đã cấu hình, host có thể chịu áp lực bộ nhớ và phải thu hồi, nén hoặc swap trang nhớ. Những cơ chế này có thể làm tăng độ trễ đáng kể.

### 7.2. Memory overcommit và các cơ chế quản lý

Một số hypervisor hỗ trợ các kỹ thuật như ballooning, memory compression, page sharing hoặc swap để quản lý áp lực bộ nhớ. Balloon driver trong guest có thể phối hợp với hypervisor để thu hồi một phần bộ nhớ từ VM khi host cần tài nguyên. Khả năng và hành vi cụ thể phụ thuộc hypervisor, guest tools và cấu hình.

Các kỹ thuật thu hồi giúp tận dụng RAM tốt hơn nhưng không thay thế việc lập kế hoạch dung lượng. Khi host thường xuyên swap hoặc guest liên tục bị thu hồi bộ nhớ, hiệu năng có thể giảm. Với workload cần độ trễ ổn định, nên giữ headroom RAM và theo dõi mức sử dụng thực tế.

### 7.3. Huge pages và NUMA memory

Huge pages dùng kích thước trang bộ nhớ lớn hơn trang cơ bản để giảm chi phí quản lý bảng trang và TLB miss trong một số workload. Chúng có thể hữu ích với cơ sở dữ liệu hoặc ứng dụng xử lý bộ nhớ lớn, nhưng yêu cầu cấu hình phù hợp và có thể làm giảm tính linh hoạt khi cấp phát.

NUMA memory placement cũng quan trọng: vCPU và vùng RAM của VM nên được đặt gần nhau khi workload nhạy độ trễ. Theo dõi NUMA locality và remote memory access trong các hệ thống cần hiệu năng cao.

## 8. Ảo hóa lưu trữ

VM thường nhìn thấy một hoặc nhiều đĩa ảo. Hypervisor ánh xạ thao tác đọc/ghi của guest tới file đĩa ảo, volume trên datastore hoặc thiết bị lưu trữ được gán trực tiếp.

### 8.1. Đĩa ảo và datastore

Đĩa ảo có thể được lưu dưới dạng file trên filesystem hoặc volume do nền tảng lưu trữ quản lý. Một số định dạng thường gặp là VMDK, VHDX, QCOW2 và RAW. Mỗi định dạng có tính năng và hiệu năng khác nhau, vì vậy cần theo tài liệu của nền tảng.

Datastore có thể nằm trên:

- SSD hoặc NVMe cục bộ trong host.
- SAN qua Fibre Channel hoặc iSCSI.
- NFS hoặc hệ thống file chia sẻ.
- Hệ thống lưu trữ phân tán hoặc dịch vụ block storage của cloud.

Lưu trữ cục bộ có thể cho độ trễ thấp, nhưng cần thiết kế cách di chuyển hoặc khôi phục VM nếu host hỏng. Shared storage giúp nhiều host truy cập cùng datastore, hỗ trợ một số kịch bản migration và HA, nhưng cần dự phòng đường mạng, controller và hệ thống lưu trữ.

### 8.2. Thin provisioning và thick provisioning

Với **thick provisioning**, dung lượng lưu trữ được dành trước theo chính sách của nền tảng. Với **thin provisioning**, đĩa ảo có thể khai báo dung lượng logic lớn nhưng chỉ tiêu thụ dung lượng vật lý khi dữ liệu được ghi.

Thin provisioning tăng hiệu quả sử dụng dung lượng, nhưng có nguy cơ datastore cạn chỗ nếu tổng dung lượng logic cấp phát vượt xa dung lượng vật lý. Cần giám sát cả dung lượng đã cấp phát, dung lượng thực dùng và tốc độ tăng dữ liệu. Thick provisioning dễ dự đoán dung lượng hơn trong một số trường hợp nhưng có thể giữ chỗ chưa dùng đến.

### 8.3. I/O, cache và snapshot

Hiệu năng lưu trữ phụ thuộc độ trễ, IOPS, thông lượng, kích thước I/O, queue depth và mức tranh chấp. Một VM có thể bị chậm vì nhiều VM khác đang đọc ghi trên cùng datastore. Khi chẩn đoán, cần đo cả phía guest, hypervisor và storage backend.

Snapshot lưu lại trạng thái đĩa tại một thời điểm theo cơ chế của hypervisor. Snapshot hữu ích trước một thay đổi ngắn hạn hoặc để tạo điểm quay lui, nhưng thường tạo chuỗi phụ thuộc và tăng chi phí I/O/dung lượng khi tồn tại lâu. Snapshot không thay thế backup: snapshot có thể cùng nằm trên hệ thống lưu trữ với VM và cùng bị ảnh hưởng khi datastore gặp sự cố.

Backup cần có bản sao độc lập, chính sách lưu giữ, mã hóa, kiểm soát truy cập và kiểm thử khôi phục. Với ứng dụng có cơ sở dữ liệu, cần phối hợp snapshot hoặc backup theo cách bảo đảm tính nhất quán của dữ liệu.

## 9. Ảo hóa mạng

Hypervisor cung cấp NIC ảo cho VM và kết nối chúng tới switch ảo. Switch ảo có thể kết nối các VM trên cùng host, uplink ra switch vật lý hoặc tham gia vào mạng overlay do nền tảng SDN quản lý.

### 9.1. NIC ảo và switch ảo

Một VM có thể có nhiều NIC ảo, mỗi NIC gắn với một mạng hoặc VLAN khác nhau. Switch ảo xử lý việc chuyển frame giữa VM và uplink. Quản trị viên có thể cấu hình port group, VLAN tagging, chính sách bảo mật, giới hạn băng thông và theo dõi lưu lượng.

Mạng cần được chia vùng theo chức năng và mức độ tin cậy, ví dụ:

- Mạng quản trị hypervisor và BMC.
- Mạng lưu lượng ứng dụng của VM.
- Mạng lưu trữ hoặc migration.
- Mạng backup và giám sát.

Không nên để giao diện quản trị hypervisor hoặc BMC truy cập trực tiếp từ mạng người dùng thông thường.

### 9.2. Overlay network và SDN

Trong môi trường cloud nhiều tenant, VLAN truyền thống có thể không đủ linh hoạt hoặc có giới hạn về số lượng mạng logic. Overlay network tạo mạng ảo trên hạ tầng IP vật lý bằng cách đóng gói gói tin trong một giao thức overlay, chẳng hạn VXLAN. Software-defined networking (SDN) cho phép điều khiển chính sách mạng bằng phần mềm và API.

Overlay giúp tách mạng logic khỏi topology vật lý, nhưng thêm overhead đóng gói và yêu cầu MTU, routing, tunnel endpoint được cấu hình đúng. Khi debug, cần phân biệt lỗi ở mạng guest, switch ảo, overlay và mạng vật lý.

### 9.3. Thiết bị mạng tăng tốc

Một số host hỗ trợ SR-IOV để chia chức năng của một NIC vật lý thành các virtual function có thể gán cho VM. Cách này giảm một phần xử lý qua switch ảo và có thể cải thiện thông lượng hoặc độ trễ. Đổi lại, một số tính năng di chuyển VM, kiểm soát lưu lượng hoặc quan sát mạng có thể bị giới hạn tùy thiết bị và hypervisor.

Passthrough thiết bị PCIe cho phép VM truy cập trực tiếp một thiết bị vật lý thông qua cơ chế IOMMU. Cách này hữu ích với GPU, NIC hoặc thiết bị chuyên dụng, nhưng làm giảm khả năng chia sẻ thiết bị và có thể hạn chế live migration. Cần kiểm tra nhóm IOMMU, firmware, driver và hỗ trợ của nền tảng.

## 10. Cô lập và bảo mật giữa các VM

Một mục tiêu quan trọng của ảo hóa là ngăn VM này truy cập trái phép bộ nhớ, CPU hoặc thiết bị của VM khác. Hypervisor kiểm soát việc ánh xạ bộ nhớ, lập lịch CPU và truy cập thiết bị. Tuy vậy, ảo hóa không loại bỏ mọi rủi ro bảo mật.

### 10.1. Ranh giới tin cậy

Các vùng cần bảo vệ gồm:

- **Guest VM:** hệ điều hành, ứng dụng, tài khoản và dữ liệu bên trong VM.
- **Hypervisor host:** kernel hoặc lớp hypervisor, driver và dịch vụ quản trị.
- **Management plane:** API, giao diện điều khiển, tài khoản quản trị và hệ thống điều phối.
- **Firmware/BMC:** firmware máy chủ và giao diện quản trị ngoài băng.
- **Mạng và lưu trữ:** switch ảo, mạng vật lý, datastore, backup và đường truyền migration.

Nếu tài khoản quản trị hypervisor bị chiếm quyền, kẻ tấn công có thể ảnh hưởng nhiều VM trên host. Vì vậy, management plane là tài sản có mức độ nhạy cảm cao.

### 10.2. Biện pháp bảo vệ

1. Cập nhật hypervisor, firmware, driver và guest tools theo quy trình kiểm soát thay đổi.
2. Dùng MFA cho tài khoản quản trị; phân quyền RBAC theo vai trò và áp dụng nguyên tắc đặc quyền tối thiểu.
3. Tách mạng quản trị, BMC, lưu trữ, migration và mạng ứng dụng.
4. Bật Secure Boot hoặc các cơ chế kiểm tra tính toàn vẹn khi nền tảng hỗ trợ.
5. Giới hạn quyền truy cập datastore, image VM, snapshot và backup.
6. Mã hóa dữ liệu VM và đường truyền nhạy cảm; quản lý khóa riêng và luân chuyển theo chính sách.
7. Ghi log hoạt động quản trị, theo dõi đăng nhập bất thường và cảnh báo thay đổi cấu hình.
8. Dùng template VM đã được vá, giảm dịch vụ không cần thiết và quản lý secret an toàn trong guest.

### 10.3. Rủi ro đặc thù của ảo hóa

**VM escape** là tình huống lỗ hổng trong hypervisor hoặc thiết bị ảo cho phép mã từ guest vượt khỏi ranh giới VM và ảnh hưởng host. Đây là rủi ro nghiêm trọng nhưng không phải hành vi bình thường của ảo hóa. Giảm rủi ro bằng cách vá lỗi, hạn chế thiết bị ảo không cần thiết, giảm quyền của thành phần quản trị và theo dõi cảnh báo bảo mật.

**Noisy neighbor** là hiện tượng workload trên cùng host tranh chấp CPU, RAM, I/O hoặc mạng làm ảnh hưởng VM khác. Đây vừa là vấn đề hiệu năng vừa có thể ảnh hưởng cam kết dịch vụ. Reservation, limit, QoS, placement policy và dedicated host là những công cụ có thể dùng tùy nền tảng.

**Side-channel** là nhóm tấn công khai thác thông tin gián tiếp từ hành vi phần cứng như cache hoặc thực thi suy đoán. Rủi ro và biện pháp giảm thiểu phụ thuộc CPU, firmware, hypervisor và hướng dẫn của nhà cung cấp. Không nên tự ý tắt các cơ chế giảm thiểu bảo mật chỉ để tăng hiệu năng.

## 11. Vòng đời và vận hành máy ảo

VM có vòng đời tương tự máy tính: tạo, cấu hình, khởi động, vận hành, cập nhật, sao lưu, di chuyển và hủy. Trong hạ tầng lớn, những bước này thường được tự động hóa bằng template, API và hệ thống điều phối.

### 11.1. Tạo VM từ image hoặc template

Image là nguồn dùng để tạo đĩa khởi động hoặc hệ điều hành cho VM. Template thường là một image đã chuẩn hóa kèm cấu hình cơ bản. Trước khi dùng template rộng rãi, cần:

- Cài bản vá hệ điều hành và gói cần thiết.
- Loại bỏ khóa, token, mật khẩu và định danh máy đã dùng trong quá trình tạo image.
- Cấu hình agent quản trị, giám sát và logging.
- Chuẩn hóa tài khoản, SSH, firewall và chính sách cập nhật.
- Dùng cơ chế first boot hoặc cloud-init để đặt hostname, khóa SSH và cấu hình instance riêng.

Không nên nhân bản nguyên một máy đã đăng ký danh tính duy nhất mà không reset machine ID, host key hoặc thông tin agent phù hợp. Mỗi VM cần danh tính riêng.

### 11.2. Khởi động, tắt và dừng mềm

Guest OS cần được yêu cầu tắt đúng cách để ghi dữ liệu và đóng dịch vụ. Tắt nguồn cưỡng bức tương đương ngắt điện và có thể làm hỏng dữ liệu đang ghi. Với dịch vụ quan trọng, hãy chuẩn bị quy trình dừng mềm: ngừng nhận yêu cầu, hoàn tất giao dịch đang chạy, flush dữ liệu và đóng kết nối trước khi tắt VM.

### 11.3. Live migration

Live migration chuyển VM đang chạy từ host này sang host khác với thời gian gián đoạn rất ngắn theo khả năng nền tảng. Một số hệ thống sao chép bộ nhớ của VM sang host đích trong khi VM tiếp tục chạy; các trang thay đổi được gửi lại cho đến khi có thể chuyển quyền thực thi.

Điều kiện thường cần xem xét:

- Host nguồn và đích có CPU tương thích hoặc cấu hình tương thích migration.
- Mạng migration đủ băng thông và được bảo vệ.
- Host đích có đủ CPU, RAM và thiết bị phù hợp.
- Datastore được chia sẻ hoặc có cơ chế chuyển đĩa tương ứng.
- Thiết bị passthrough, GPU, SR-IOV hoặc cấu hình đặc biệt có thể hạn chế migration.

Live migration hữu ích khi bảo trì host, cân bằng tải hoặc di chuyển VM trong cluster. Nó không phải backup và không thay thế thiết kế HA.

### 11.4. High availability và cluster

Cluster ảo hóa gồm nhiều host được quản lý như một nhóm. Khi một host gặp lỗi, nền tảng HA có thể khởi động lại VM trên host khác nếu còn đủ tài nguyên và dữ liệu cần thiết vẫn truy cập được.

Để HA hoạt động, cần:

- Nhiều host trong các miền lỗi phù hợp.
- Dung lượng dự phòng để chạy workload của host bị lỗi.
- Datastore hoặc bản sao dữ liệu có thể truy cập từ host đích.
- Mạng quản trị và cơ chế quorum/heartbeat đủ tin cậy.
- Chính sách restart, ưu tiên workload và giám sát rõ ràng.

HA thường khởi động lại VM sau sự cố nên có thể gây gián đoạn. Nó khác với fault tolerance hoặc replication ở cấp ứng dụng. Hãy xác định RTO và RPO, sau đó kiểm thử tình huống mất host, mất storage hoặc mất kết nối mạng.

## 12. Cấp phát tài nguyên và quản lý dung lượng

Khi tạo VM, cần cấu hình vCPU, RAM, đĩa, NIC và các giới hạn liên quan. Cấu hình ban đầu nên dựa trên số liệu của ứng dụng hoặc kiểm thử đại diện, sau đó điều chỉnh theo quan sát thực tế.

| Tài nguyên | Cần ước lượng | Chỉ số nên theo dõi |
|---|---|---|
| vCPU | Mức song song, tải trung bình và đỉnh, yêu cầu độ trễ | CPU utilization, CPU ready/steal, run queue |
| RAM | Working set, cache, đỉnh bộ nhớ và headroom | Guest memory, host memory pressure, ballooning, swap |
| Storage | Dung lượng, tăng trưởng, IOPS và thông lượng | Read/write latency, IOPS, queue depth, datastore capacity |
| Network | Lưu lượng vào/ra, kết nối đồng thời, độ trễ | Throughput, packet drop, error, retransmission |
| GPU/PCIe | Loại thiết bị, bộ nhớ thiết bị và mức sử dụng | GPU utilization, VRAM, PCIe throughput |

### 12.1. Reservation, limit và share

Tùy hypervisor, tài nguyên có thể được điều khiển bằng các khái niệm như:

- **Reservation:** lượng tài nguyên tối thiểu được bảo đảm cho VM khi tranh chấp.
- **Limit:** mức sử dụng tối đa mà VM được phép tiêu thụ.
- **Share/weight:** trọng số ưu tiên tương đối khi nhiều VM tranh chấp tài nguyên.

Tên gọi và hành vi chính xác khác nhau giữa các nền tảng. Reservation quá cao có thể làm giảm khả năng đặt VM mới; limit quá thấp có thể gây nghẽn dù host còn tài nguyên; share chỉ có ý nghĩa khi xảy ra tranh chấp.

### 12.2. Right-sizing

Right-sizing là điều chỉnh kích thước VM theo nhu cầu quan sát được. VM cấp quá nhiều CPU/RAM làm lãng phí dung lượng và có thể khiến việc đặt VM khó hơn. VM quá nhỏ gây throttling, swap, timeout hoặc lỗi hết bộ nhớ.

Nên thu thập số liệu trong một khoảng thời gian bao phủ chu kỳ tải, bao gồm cả đỉnh theo ngày, tuần hoặc mùa vụ. Không giảm cấu hình chỉ dựa trên một khoảng thời gian nhàn rỗi ngắn. Với workload quan trọng, giữ headroom cho đột biến và failover.

## 13. Ví dụ cấu hình VM trên KVM/libvirt

KVM là cơ chế ảo hóa trong kernel Linux; QEMU cung cấp tiến trình máy ảo và mô phỏng/thiết bị ảo; libvirt cung cấp lớp quản trị thống nhất cho vòng đời VM. Tùy bản phân phối và cấu hình, tên package, service và đường dẫn có thể khác nhau.

Một VM Linux đơn giản có thể được định nghĩa bằng domain XML. Ví dụ dưới đây minh họa 4 vCPU, 8 GiB RAM, đĩa virtio và NIC virtio gắn vào một mạng ảo tên default:

~~~xml
<domain type='kvm'>
  <name>app-vm-01</name>
  <memory unit='GiB'>8</memory>
  <vcpu placement='static'>4</vcpu>
  <os>
    <type arch='x86_64' machine='q35'>hvm</type>
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/>
    <apic/>
  </features>
  <cpu mode='host-model'/>
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='/var/lib/libvirt/images/app-vm-01.qcow2'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>
    <console type='pty'/>
  </devices>
</domain>
~~~

XML trên là ví dụ học tập. Nó giả định file đĩa đã tồn tại và mạng default đã được cấu hình. Khi triển khai thật, cần bổ sung chính sách bảo mật, firmware phù hợp, cấu hình console, giới hạn tài nguyên, backup, logging và mạng đúng với môi trường.

Một số lệnh quản trị thường dùng:

~~~bash
# Xác nhận host có hỗ trợ tăng tốc ảo hóa CPU
egrep -c '(vmx|svm)' /proc/cpuinfo

# Liệt kê các VM đã được libvirt quản lý
virsh list --all

# Xem cấu hình của một VM
virsh dumpxml app-vm-01

# Khởi động VM
virsh start app-vm-01

# Yêu cầu guest tắt mềm
virsh shutdown app-vm-01

# Xem thông tin và trạng thái VM
virsh dominfo app-vm-01
~~~

Các lệnh cần chạy với quyền phù hợp trên host Linux có KVM/libvirt. Lệnh kiểm tra vmx hoặc svm chỉ cho biết CPU flag có thể được nhìn thấy; cần kiểm tra thêm BIOS/UEFI, module kernel, quyền truy cập và cấu hình hypervisor trước khi kết luận host sẵn sàng chạy VM.

## 14. Tình huống thực tế: hợp nhất nhiều máy chủ ứng dụng

Một doanh nghiệp có 12 máy chủ vật lý cũ, mỗi máy chạy một dịch vụ nội bộ. Phần lớn máy chỉ sử dụng CPU ở mức thấp, nhưng mỗi dịch vụ cần một phiên bản hệ điều hành hoặc cấu hình riêng. Nhóm hạ tầng muốn giảm số máy phải vận hành và chuẩn hóa việc cấp phát.

Nhóm có thể khảo sát CPU, RAM, lưu trữ, mạng và đặc tính tải của từng dịch vụ, sau đó chọn một nhóm host ảo hóa có đủ năng lực và dự phòng. Các dịch vụ được chuyển thành VM với cấu hình vCPU/RAM theo số liệu đo. VM được đặt trên datastore phù hợp; mạng được tách theo nhóm ứng dụng; template hệ điều hành được chuẩn hóa; hệ thống quản trị tập trung theo dõi trạng thái host và VM.

Một cách lập kế hoạch minh họa:

| Hạng mục | Cách đánh giá |
|---|---|
| Năng lực host | Đo tải CPU đỉnh, RAM working set và tốc độ I/O của các dịch vụ |
| Số lượng host | Tính đủ năng lực khi một host bảo trì hoặc gặp lỗi |
| Cấu hình VM | Cấp vCPU/RAM theo mức sử dụng, cộng headroom theo SLO |
| Lưu trữ | Phân loại dữ liệu theo độ trễ, IOPS, dung lượng và yêu cầu backup |
| Mạng | Tách mạng quản trị, VM, storage và migration |
| Bảo mật | RBAC, MFA, bản vá, quản lý image và phân vùng mạng |
| Vận hành | Template, giám sát, backup, migration và quy trình phục hồi |

Giả sử một host lỗi, cluster HA cần có đủ tài nguyên dự phòng để khởi động lại các VM ưu tiên trên host còn lại. Nếu thiết kế chỉ vừa đủ chạy ở trạng thái bình thường, sự cố một host có thể làm các VM còn lại không có nơi khởi động. Vì vậy, dung lượng dự phòng là một phần của thiết kế HA, không phải tài nguyên dư thừa có thể bỏ qua.

Sau khi hợp nhất, doanh nghiệp có thể giảm số thiết bị vật lý, điện năng và công sức quản trị. Tuy nhiên, mật độ VM cao làm tăng mức độ ảnh hưởng khi một host hoặc datastore gặp lỗi. Cần thiết kế failure domain, sao lưu độc lập và kiểm thử khôi phục trước khi đưa workload quan trọng vào vận hành.

## 15. Khi nào nên dùng bare metal thay vì VM?

Ảo hóa phù hợp với nhiều workload, nhưng không phải lúc nào cũng là lựa chọn tối ưu. Bare-metal server có thể phù hợp khi:

- Workload cần hiệu năng ổn định và mức độ trễ rất thấp.
- Ứng dụng cần truy cập trực tiếp thiết bị phần cứng hoặc driver đặc biệt.
- Có yêu cầu cấp phép phần mềm gắn với core/socket hoặc phần cứng cụ thể.
- Workload cần toàn bộ tài nguyên của máy và không cần chia sẻ với tenant khác.
- Hệ thống yêu cầu đặc tính I/O hoặc GPU mà lớp ảo hóa hiện tại không hỗ trợ đầy đủ.

Bare metal vẫn cần quản lý hệ điều hành, bản vá, mạng, lưu trữ, backup và tính sẵn sàng. Không có hypervisor cũng không có nghĩa hệ thống tự động nhanh hơn: kết quả phụ thuộc workload, driver, cấu hình firmware và cách đo.

## 16. Mối quan hệ giữa VM, container và serverless

VM ảo hóa phần cứng để mỗi guest có môi trường hệ điều hành riêng. Container đóng gói ứng dụng và phụ thuộc nhưng thường chia sẻ kernel của hệ điều hành host. Serverless chuyển phần lớn công việc quản lý hạ tầng và cấp phát thực thi sang nền tảng, thường kích hoạt theo sự kiện hoặc theo nhu cầu.

Ba mô hình có thể cùng tồn tại trong một hệ thống:

| Mô hình | Lớp được trừu tượng hóa | Đơn vị triển khai | Trách nhiệm hạ tầng thường gặp |
|---|---|---|---|
| VM | Phần cứng máy tính | Máy ảo có guest OS | Quản lý guest OS và ứng dụng; nhà cung cấp có thể quản lý host/hypervisor |
| Container | Môi trường chạy ứng dụng ở mức hệ điều hành | Image/container | Quản lý image, cấu hình runtime và nền tảng điều phối |
| Serverless | Hạ tầng thực thi và điều phối | Function, job hoặc ứng dụng | Tập trung vào mã, cấu hình, quyền và giới hạn dịch vụ |

Container thường có thể chạy bên trong VM. Nhà cung cấp cloud có thể dùng VM làm ranh giới cô lập cho tenant, rồi chạy container hoặc workload serverless bên trong lớp compute đó. Vì vậy, hiểu máy chủ vật lý và hypervisor giúp giải thích lớp hạ tầng bên dưới nhiều dịch vụ cloud hiện đại.

## 17. Quy trình đánh giá một nền tảng ảo hóa

Khi lựa chọn hoặc rà soát nền tảng ảo hóa, có thể dùng quy trình sau:

1. **Khảo sát phần cứng:** CPU, RAM, NUMA, NIC, storage, firmware, nguồn và làm mát.
2. **Xác định workload:** số VM, vCPU, RAM, I/O, mạng, GPU và yêu cầu độ trễ.
3. **Chọn hypervisor:** đánh giá hỗ trợ phần cứng, guest OS, công cụ quản trị, API và mô hình cấp phép.
4. **Thiết kế tài nguyên:** xác định reservation, limit, overcommit, headroom và chính sách placement.
5. **Thiết kế lưu trữ và mạng:** datastore, backup, VLAN/overlay, mạng quản trị và đường migration.
6. **Thiết kế bảo mật:** RBAC, MFA, patching, Secure Boot, phân vùng mạng và quản lý secret.
7. **Thiết kế tính sẵn sàng:** cluster, failure domain, quorum, HA, backup và mục tiêu RPO/RTO.
8. **Kiểm thử:** đo hiệu năng, tranh chấp tài nguyên, live migration, mất host và khôi phục dữ liệu.
9. **Theo dõi chi phí:** tính chi phí host, license, điện, làm mát, lưu trữ, mạng và công sức vận hành.

Đánh giá phải dựa trên workload đại diện và kết quả kiểm thử. Một hypervisor có nhiều tính năng nhưng không phù hợp với phần cứng, kỹ năng vận hành hoặc mô hình chi phí của tổ chức vẫn có thể là lựa chọn kém.

## 18. Những sai lầm thường gặp

- **Đồng nhất vCPU với core vật lý:** vCPU là tài nguyên logic được hypervisor lập lịch, có thể phải chờ CPU vật lý.
- **Overcommit quá mức:** tổng nhu cầu đỉnh vượt năng lực host, gây tăng độ trễ hoặc thiếu tài nguyên khi failover.
- **Bỏ qua NUMA:** VM lớn có thể chịu độ trễ truy cập RAM cao nếu CPU và bộ nhớ bố trí không phù hợp.
- **Coi snapshot là backup:** snapshot cùng datastore có thể mất theo sự cố storage và không thay thế bản sao độc lập.
- **Chỉ dựa vào dung lượng đĩa logic:** thin provisioning có thể làm datastore cạn dung lượng vật lý.
- **Để mạng quản trị chung với mạng ứng dụng:** làm tăng phạm vi tấn công vào hypervisor và BMC.
- **Cho rằng live migration giải quyết HA:** migration hỗ trợ bảo trì và cân bằng tải; HA xử lý tình huống lỗi host theo cơ chế riêng.
- **Cấp phát VM theo cảm tính:** cấu hình quá lớn lãng phí dung lượng, cấu hình quá nhỏ làm giảm hiệu năng.
- **Không kiểm thử phục hồi:** có backup hoặc cluster chưa chứng minh được rằng dịch vụ sẽ khôi phục trong RTO/RPO yêu cầu.

## 19. Ghi nhớ

Máy chủ vật lý cung cấp năng lực CPU, RAM, lưu trữ và mạng. Hypervisor biến một phần năng lực đó thành tài nguyên ảo để nhiều VM có thể chạy độc lập trên cùng host. Các cơ chế ảo hóa CPU, bộ nhớ, lưu trữ và mạng giúp phân phối tài nguyên, nhưng vẫn chịu giới hạn của phần cứng và có thể phát sinh tranh chấp.

Khi thiết kế hạ tầng cloud compute, cần hiểu topology phần cứng, chọn hypervisor phù hợp, cấp phát VM theo số liệu, bảo vệ management plane, giám sát tài nguyên và thiết kế HA/backup đúng mục tiêu. Ảo hóa giúp tăng tính linh hoạt và hiệu quả sử dụng phần cứng; hiệu quả thực tế phụ thuộc vào cách lập kế hoạch, vận hành và kiểm chứng hệ thống.

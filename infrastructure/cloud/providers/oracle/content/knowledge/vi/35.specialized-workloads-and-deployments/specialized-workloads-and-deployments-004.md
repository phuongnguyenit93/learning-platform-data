# HPC, cluster networking và yêu cầu độ trễ thấp

## 1. Bài toán: nhiều máy chỉ hữu ích khi phối hợp đủ nhanh

High Performance Computing (HPC) dùng tài nguyên tính toán song song để xử lý những bài toán lớn như mô phỏng khí động học, mô phỏng phân tử, tối ưu thiết kế hoặc huấn luyện mô hình. Khi công việc được chia cho nhiều máy, thời gian hoàn thành còn phụ thuộc vào trao đổi dữ liệu, đồng bộ tiến trình và đọc ghi kết quả.

Trong chương **Workload và triển khai chuyên biệt** của Oracle Cloud Infrastructure (OCI), mục tiêu của bài này là thiết kế một cụm HPC có đường truyền phù hợp với ứng dụng, triển khai trong phạm vi IAM được kiểm soát, rồi đo hiệu năng và chi phí bằng dữ liệu thực nghiệm. Người vận hành cần trả lời được:

- Ứng dụng cần nhiều CPU, nhiều bộ nhớ, GPU hay kết nối giữa các node?
- Khi nào mạng VCN thông thường đáp ứng được, khi nào cần RDMA cluster networking?
- Làm sao xác nhận ứng dụng đang dùng đúng đường truyền?
- Cụm phục hồi như thế nào khi một node lỗi?
- Mở rộng đến bao nhiêu node thì có lợi cho mục tiêu thời gian và ngân sách?

HPC cũng có workload chạy tốt trên một máy lớn. Việc chuyển từ một node sang nhiều node phải xuất phát từ giới hạn bộ nhớ, thời hạn hoàn thành hoặc hiệu năng đã đo.

### Kiến thức cần có

Người học nên biết tenancy, compartment, IAM policy, VCN, subnet, NSG, Compute instance, Object Storage và Monitoring. Với phần thực hành, cần hiểu Linux cơ bản và có môi trường đã cài Slurm cùng một bộ MPI tương thích trên các node.

**Node** là máy tham gia cụm. **MPI rank** là một tiến trình trong ứng dụng MPI. Một node có thể chạy nhiều rank; mỗi rank có thể tiếp tục dùng nhiều thread hoặc một GPU. Số node, số rank và số core là ba đại lượng khác nhau.

## 2. Phân loại workload trước khi chọn hạ tầng

| Dạng công việc | Mẫu trao đổi | Điểm cần ưu tiên |
| --- | --- | --- |
| Nhiều lần mô phỏng độc lập | Các job gần như không liên lạc khi chạy | Giá mỗi kết quả, thời gian chờ, khả năng mở rộng hàng đợi |
| MPI liên kết chặt | Trao đổi dữ liệu biên và đồng bộ lặp lại | Độ trễ, biến động độ trễ, băng thông giữa node |
| Phân tích dùng bộ nhớ lớn | Giữ tập dữ liệu lớn trong RAM | Dung lượng và băng thông bộ nhớ; so sánh scale-up với scale-out |
| Huấn luyện GPU phân tán | Đồng bộ gradient hoặc trạng thái mô hình | Collective communication, kết nối GPU và mạng giữa các node |
| Xử lý nặng I/O | Đọc tập dữ liệu lớn, nhiều file nhỏ hoặc checkpoint lớn | Thông lượng lưu trữ, metadata, locality và thời gian staging |

Ví dụ, 1.000 phép mô phỏng Monte Carlo độc lập thường có thể được chia thành nhiều job riêng. Mỗi job nạp dữ liệu một lần, tính toán rồi ghi kết quả. Ngược lại, một solver chia miền tính toán cho nhiều rank có thể trao đổi vùng biên ở mọi bước thời gian. Cùng dùng hàng trăm core nhưng hai ứng dụng tạo áp lực mạng rất khác nhau.

Với workload liên kết lỏng, một instance pool thông thường kết hợp bộ lập lịch có thể phù hợp. Với workload liên kết chặt, cần đánh giá RDMA và cách đặt các node trong cùng cụm. Hướng dẫn [HPC trên OCI](https://docs.oracle.com/en-us/iaas/Content/Compute/References/high-performance-compute.htm) giới thiệu hạ tầng bare metal và cluster networking cho nhóm bài toán này.

Một workload có thể đổi nút thắt theo quy mô. Solver chạy bốn node có thể bị giới hạn bởi tính toán, nhưng khi lên 32 node, phần công việc mỗi rank nhỏ hơn và đồng bộ trở thành chi phí chính.

## 3. Hiểu đúng độ trễ, băng thông và hiệu quả mở rộng

### 3.1. Mô hình thời gian một lần trao đổi

Một mô hình đơn giản cho thông điệp kích thước m byte:

~~~text
T_message ≈ alpha + m / B_effective

alpha       : chi phí khởi tạo và độ trễ của đường truyền
B_effective : băng thông ứng dụng thực sự đạt được
~~~

Thông điệp nhỏ thường nhạy với alpha; thông điệp lớn nhạy với băng thông. Băng thông danh nghĩa của NIC chỉ là một giới hạn phần cứng. Băng thông thực tế còn phụ thuộc vào giao thức, topology, bộ nhớ, kích thước thông điệp, số luồng và thư viện truyền thông.

Giả sử một bước của ứng dụng có 2.000 lần trao đổi tuần tự nằm trên đường tới hạn. Nếu mỗi lần giảm được 15 microsecond, mức giảm lý tưởng là:

~~~text
2.000 × 15 microsecond = 30 millisecond mỗi bước
10.000 bước × 30 millisecond = 300 giây
~~~

Đây là phép tính minh họa. Các thông điệp chạy đồng thời hoặc chồng lấp với tính toán không cộng tuyến tính theo cách này.

### 3.2. Độ trễ đuôi và node chậm

Trong một bước có barrier hoặc collective, nhiều rank phải đợi rank hoàn tất cuối cùng. Vì vậy, p95, p99 và các lần tăng đột biến có thể tác động đến thời gian chạy nhiều hơn độ trễ trung bình.

Cần phân biệt:

- **One-way latency**: thời gian đi một chiều theo phương pháp đo cụ thể.
- **Round-trip time**: thời gian khứ hồi.
- **MPI latency**: kết quả do benchmark MPI định nghĩa; có benchmark dùng nửa thời gian ping-pong.
- **Iteration time**: thời gian của một vòng tính toán, gồm cả tính toán và trao đổi.
- **End-to-end time**: từ lúc gửi job đến khi kết quả sẵn sàng.

Không so sánh các giá trị mang cùng đơn vị microsecond nếu phương pháp đo khác nhau. Ping ICMP qua địa chỉ VCN không chứng minh độ trễ của đường dữ liệu RDMA.

### 3.3. Giới hạn của việc thêm node

Với bài toán cố định, có thể dùng mô hình:

~~~text
T(n) ≈ T_serial + T_parallel / n + T_communication(n) + T_io(n)
~~~

Phần tuần tự đặt ra giới hạn theo định luật Amdahl. Nếu 5% công việc hoàn toàn tuần tự, tốc độ tăng tối đa lý tưởng chỉ tiến tới 20 lần khi số tài nguyên tăng rất lớn, ngay cả trước khi tính chi phí truyền thông.

Hai kiểu phép đo thường dùng:

- **Strong scaling**: giữ nguyên bài toán, tăng tài nguyên; đo mức giảm thời gian.
- **Weak scaling**: tăng bài toán theo tài nguyên để giữ lượng việc mỗi tài nguyên gần cố định; đo khả năng giữ thời gian ổn định.

Với các node đồng nhất và cấu hình mỗi node giữ nguyên:

~~~text
Speedup(n)    = T(1) / T(n)
Efficiency(n) = Speedup(n) / n
~~~

Nếu bài toán không vừa một node, dùng cấu hình nhỏ nhất chạy được làm baseline và chuẩn hóa theo tỷ lệ tài nguyên so với baseline đó. Không tự tạo số liệu một node để điền vào công thức.

## 4. RDMA và các đường mạng trong OCI

### 4.1. RDMA giải quyết chi phí nào?

Remote Direct Memory Access (RDMA) cho phép truyền dữ liệu đến hoặc từ vùng bộ nhớ đã được đăng ký với phần cứng mạng. Với phần cứng và thư viện phù hợp, cơ chế này giảm sự tham gia của CPU và giảm chi phí xử lý giao thức so với đường truyền socket thông thường.

RDMA vẫn cần cấp phát tài nguyên, đăng ký bộ nhớ, điều khiển truy cập và xử lý hoàn tất. Ứng dụng chỉ hưởng lợi khi MPI hoặc thư viện truyền thông thực sự chọn transport tương ứng.

Trong kiến trúc HPC tham chiếu của Oracle, cluster interconnect dùng RoCEv2, tức RDMA over Converged Ethernet phiên bản 2. RoCEv2 chạy trên nền Ethernet; không đồng nghĩa với fabric InfiniBand dù có chung nhiều khái niệm trong hệ sinh thái RDMA. Xem [kiến trúc triển khai HPC trên OCI](https://docs.oracle.com/en/solutions/deploy-hpc-on-oci/index.html).

### 4.2. Tách đường quản trị, đường dữ liệu HPC và đường lưu trữ

Có thể nhìn cụm qua ba loại lưu lượng:

| Loại lưu lượng | Ví dụ | Điều cần xác minh |
| --- | --- | --- |
| Quản trị và điều phối | Đăng nhập, Slurm, DNS, phân phối cấu hình | VCN, NSG, route, firewall hệ điều hành |
| Dữ liệu giữa các rank | MPI, trao đổi vùng biên, collective | RDMA fabric, thiết bị, authentication và transport |
| Dữ liệu lưu trữ | Input, output, checkpoint, đọc file dùng chung | Giao thức và đường mạng thực tế của hệ lưu trữ |

Một kết nối đến được bằng địa chỉ VCN chưa đủ xác nhận RDMA hoạt động. Tạo thêm VNIC hoặc mở rộng subnet cũng không tự tạo một RDMA network group.

Tương tự, NSG và security list kiểm soát các luồng VCN trong phạm vi của chúng. Chúng không thay thế cơ chế xác thực và cấu hình RDMA do OCI yêu cầu. Thiết kế chính sách truy cập phải xem xét cả tài nguyên cloud, đường quản trị và phần mềm trong máy.

Một hệ lưu trữ song song có thể có thiết kế mạng riêng. Không mặc định mọi thao tác đọc ghi đều đi qua RDMA chỉ vì các compute node có RDMA.

### 4.3. Độ trễ thấp có điều kiện

Oracle mô tả cluster networking có độ trễ có thể xuống mức một chữ số microsecond giữa các node bare metal được đặt gần nhau. Đây là mô tả khả năng của hạ tầng; không phải cam kết cho mọi lần gọi MPI hoặc toàn bộ vòng tính toán của ứng dụng. Xem [Compute Clusters](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/compute-clusters.htm).

Thông số băng thông, số NIC và khả năng hỗ trợ phụ thuộc shape. Khi lập kế hoạch, kiểm tra danh sách shape, image, region và availability domain (AD) đang hỗ trợ mô hình cụm đã chọn. Không lấy thông số của một thế hệ CPU hoặc GPU để áp dụng cho toàn bộ OCI.

## 5. Chọn tài nguyên quản lý cụm phù hợp

OCI có hai mô hình chính để quản lý nhóm node trong RDMA network group:

| Tiêu chí | Cluster network với instance pool | Compute cluster |
| --- | --- | --- |
| Cách quản lý | Quản lý tập node đồng nhất qua instance pool | Quản lý từng instance trong nhóm |
| Điểm xuất phát | Instance configuration và kích thước nhóm | Tạo nhóm RDMA rỗng rồi tạo instance tham gia |
| Phù hợp | Cấu hình đồng nhất, vòng đời theo nhóm | Cần kiểm soát vòng đời từng node |
| Điều cần giữ rõ | Quan hệ cluster network, pool và cấu hình node | Tư cách thành viên cụm và tương thích của từng node |

Mô hình instance pool được mô tả trong [Cluster Networks with Instance Pools](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/managingclusternetworks.htm). Quy trình tạo compute cluster bắt đầu bằng nhóm RDMA rỗng như tài liệu [Creating a Compute Cluster](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/create-compute-cluster.htm).

Compute cluster cho phép các loại instance được hỗ trợ khác nhau trong cùng nhóm. Tuy nhiên, một job MPI thường dễ vận hành và dễ dự đoán hơn khi các node đồng nhất. Node chậm, khác bộ lệnh hoặc khác thư viện có thể làm cả job chậm hoặc không chạy được.

Cần phân biệt thêm:

- **VCN/subnet** cung cấp kết nối mạng cloud; cùng subnet không có nghĩa là cùng RDMA cluster.
- **Instance pool thông thường** quản lý một nhóm instance; bản thân nó không đảm bảo RDMA.
- **Slurm cluster** là tập tài nguyên do bộ lập lịch quản lý; nó có thể bao gồm nhiều nhóm hạ tầng.
- **Compute cluster của OCI** là tài nguyên hạ tầng; nó không tự cài Slurm hoặc phân phối ứng dụng.
- **Cluster placement group** là một cơ chế placement riêng. Phải kiểm tra khả năng và điều kiện hỗ trợ cụ thể; không dùng tên này như từ đồng nghĩa của compute cluster.

Nhóm RDMA được đặt trong AD được hỗ trợ. Chọn cùng AD mới là điều kiện về vị trí; vẫn phải tạo đúng tài nguyên nhóm và đưa node vào nhóm theo quy trình phù hợp.

## 6. Kiến trúc tham chiếu cho một cụm HPC nhỏ

Giả sử nhóm kỹ thuật cần chạy solver MPI trên 2–8 node, nạp input từ Object Storage và lưu checkpoint để chạy tiếp sau sự cố.

~~~mermaid
flowchart TB
    USER["Người dùng và CI"]
    ACCESS["Kênh truy cập quản trị được kiểm soát"]
    OBJ["Object Storage: input, checkpoint, output"]
    OBS["Monitoring / Logging"]

    USER --> ACCESS

    subgraph VCN["VCN: các node dùng private IP"]
        HEAD["Login / Slurm controller"]
        FS["Hệ file dùng chung"]
        subgraph AD["Một availability domain"]
            subgraph RDMA["Nhóm RDMA trên OCI"]
                N1["Compute node 1"]
                N2["Compute node 2"]
                NN["Compute node n"]
                N1 <-->|"MPI qua RDMA"| N2
                N2 <-->|"MPI qua RDMA"| NN
            end
        end
    end

    ACCESS --> HEAD
    HEAD -->|"Điều phối qua VCN"| N1
    HEAD -->|"Điều phối qua VCN"| N2
    HEAD -->|"Điều phối qua VCN"| NN
    N1 -->|"I/O theo thiết kế lưu trữ"| FS
    N2 -->|"I/O theo thiết kế lưu trữ"| FS
    NN -->|"I/O theo thiết kế lưu trữ"| FS
    FS -->|"Staging và sao lưu"| OBJ
    N1 -.-> OBS
    N2 -.-> OBS
    NN -.-> OBS
~~~

Đây là sơ đồ logic. Một kênh truy cập quản trị có thể được thực hiện bằng OCI Bastion hoặc kết nối riêng phù hợp. Cụm thực tế cần thiết kế route, endpoint và quyền truy cập tương ứng.

Phân vai các thành phần:

- **Login node** nhận mã nguồn, biên dịch hoặc gửi job. Công việc tính toán dài chạy trên compute node theo allocation.
- **Slurm controller** quản lý hàng đợi, trạng thái node và cấp phát tài nguyên.
- **Compute node** chạy MPI rank, có image và thư viện đã chuẩn hóa.
- **Lưu trữ dùng chung** cung cấp đường dẫn ứng dụng cần chia sẻ; chọn giải pháp theo thông lượng và semantics.
- **Object Storage** giữ input có phiên bản, checkpoint đã hoàn tất và output cần lưu.
- **Monitoring/Logging** tập hợp tình trạng phần cứng, trạng thái job và lỗi ứng dụng.

Lab nhỏ có thể đặt login và controller trên cùng một máy. Với môi trường quan trọng, đánh giá riêng khả năng phục hồi của controller, nơi lưu trạng thái scheduler và cơ chế truy cập quản trị.

Nếu dữ liệu đầu vào đến từ Oracle Database, nên xác định một snapshot hoặc bản xuất nhất quán cho job. Cho hàng nghìn rank cùng truy vấn cơ sở dữ liệu trong vòng lặp tính toán có thể biến tầng dữ liệu thành nút thắt và làm thí nghiệm khó tái lập.

## 7. Chuẩn bị IAM, capacity và kết nối

### 7.1. Phạm vi quyền và trách nhiệm

Compartment giúp tổ chức tài nguyên và áp dụng quyền. Mức tách phù hợp có thể là một compartment cho hạ tầng HPC và một compartment cho dữ liệu dùng chung.

| Chủ thể | Phạm vi trách nhiệm đề xuất |
| --- | --- |
| Nhóm quản trị mạng | VCN, subnet, NSG, route và các gateway cần thiết |
| Nhóm triển khai HPC | Tạo nhóm cụm, instance configuration, node và tài nguyên liên quan trong phạm vi được giao |
| Người chạy job | Đăng nhập theo quyền hệ điều hành, gửi job và truy cập bộ dữ liệu được phép |
| Instance principal | Đọc input, ghi output hoặc phát metrics theo policy cụ thể |
| Nhóm vận hành | Quan sát, drain node, thay node lỗi và kiểm soát chi phí |

Quyền tạo compute cluster không tự cấp mọi quyền cần cho instance, subnet, image hoặc volume. Người triển khai phải có đủ quyền đối với từng dependency. Quyền IAM trên OCI cũng không tự tạo tài khoản Linux hay quyền gửi job Slurm.

Với chương trình trên node gọi OCI API, có thể dùng instance principal cùng dynamic group và policy có phạm vi hẹp. Cấu hình ứng dụng hoặc OCI SDK/CLI phải chủ động dùng cơ chế xác thực này; chỉ tạo dynamic group chưa đủ làm mã tự nhận quyền.

### 7.2. Limit, quota và capacity là ba kiểm tra khác nhau

- **Service limit**: mức tài nguyên tenancy được phép sử dụng theo loại và phạm vi.
- **Compartment quota**: ràng buộc nội bộ có thể giới hạn phần tài nguyên một compartment được dùng.
- **Physical capacity**: phần cứng thực tế đang có tại AD và placement yêu cầu.

Tăng service limit không tạo thêm phần cứng tại chỗ. Có capacity cho một node cũng không chứng minh có thể cấp đủ toàn bộ số node của job. Kiểm tra hạn mức đang áp dụng trong tenancy theo [Limits by Service](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/default.htm).

Trước một đợt chạy lớn, xác nhận shape, số node, AD, thời điểm, điều kiện cung cấp capacity và phương án khi không cấp đủ. Nếu định dùng capacity reservation, phải kiểm tra mô hình cụm và shape đó có hỗ trợ theo cách dự kiến hay không.

### 7.3. Kết nối ra ngoài và dịch vụ OCI

Các compute node nên có đường truy cập cần thiết đến repository hoặc kho artifact, DNS, nguồn thời gian, lưu trữ và dịch vụ phát metrics. Cấu hình đường đi theo endpoint thực tế:

- Service Gateway có thể phục vụ truy cập riêng đến các dịch vụ Oracle được hỗ trợ trong phạm vi cấu hình.
- Repository công cộng cần một đường egress phù hợp hoặc mirror nội bộ.
- Máy có private IP vẫn cần route và quyền egress đúng; private subnet không tự cung cấp kết nối ra ngoài.
- Luồng scheduler, remote launch và lưu trữ phải được cho phép theo cấu hình phần mềm đã chọn.

Ghi lại ma trận nguồn, đích, giao thức và mục đích. Không mở toàn bộ lưu lượng từ Internet chỉ để vượt qua một lỗi khởi chạy MPI.

## 8. Quy trình tạo cụm và đưa node vào phục vụ

### 8.1. Chọn shape và image thành một bộ tương thích

Đánh giá số core thực sự sử dụng, bộ nhớ cho mỗi rank, local NVMe nếu có, số GPU, NIC RDMA và topology. Đối chiếu [Compute Shapes](https://docs.oracle.com/en-us/iaas/Content/Compute/References/computeshapes.htm) với danh sách shape hỗ trợ của đúng mô hình cụm.

Image cần phù hợp kernel, driver mạng, driver GPU nếu sử dụng, MPI và các plugin OCI. Lưu image OCID, phiên bản package và checksum của executable. Image có tên “HPC” vẫn cần được kiểm tra với shape và bộ phần mềm cụ thể.

Khi chọn số rank, đọc topology thực tế của máy; không coi mọi logical CPU đều tương đương một core vật lý hoặc dùng một công thức OCPU/vCPU cho mọi kiến trúc.

### 8.2. Tạo nhóm hạ tầng và node

Một trình tự triển khai có thể tái lập:

1. Chuẩn bị compartment, policy, subnet, NSG, lưu trữ và đường egress.
2. Chọn một AD hỗ trợ shape và mô hình cụm.
3. Nếu dùng cluster network với instance pool, chuẩn bị instance configuration tương thích và kích thước pool.
4. Nếu dùng compute cluster, tạo nhóm rồi tạo instance với tư cách thành viên nhóm đó.
5. Áp dụng image, cấu hình agent và phiên bản phần mềm thống nhất.
6. Cấu hình hostname, DNS, tài khoản, thời gian hệ thống, đường dẫn và mount.
7. Đăng ký node với Slurm; giữ node ngoài hàng đợi phục vụ cho đến khi kiểm tra xong.
8. Kiểm tra hai node trước, sau đó mở rộng và kiểm tra lại các cặp hoặc nhóm đại diện.

Các thuộc tính tạo nhóm, placement và instance configuration phải tuân theo [Creating a Cluster Network with Instance Pools](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/create-cluster-network.htm). Quy trình chọn compute cluster trong một luồng tạo instance thông thường không được dùng thay cho quy trình tạo cluster network với pool.

Có thể dùng Terraform và OCI Resource Manager hoặc bộ khởi tạo HPC được duy trì để tự động hóa. Cần cố định phiên bản và đọc kế hoạch thay đổi trước khi áp dụng. Cấu hình cloud được tạo xong chỉ là một mốc; ứng dụng còn cần bootstrap thành công và vượt qua kiểm tra runtime.

### 8.3. Xác thực và cấu hình RDMA

Hai plugin thường gặp là:

- **Compute HPC RDMA Authentication**: duy trì xác thực và cấu hình liên quan của RDMA.
- **Compute HPC RDMA Auto-Configuration**: tự động cấu hình phần cứng/giao diện theo khả năng hỗ trợ.

Theo [hướng dẫn plugin HPC của Oracle Cloud Agent](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/transitioning-to-hpc-plugin.htm), quá trình chuyển từ các package HPC cũ cần thực hiện đúng thứ tự và có thể gây gián đoạn. Không chạy thao tác chuyển đổi đó trong lúc workload đang hoạt động.

Ngoài trạng thái mong muốn ENABLED, kiểm tra plugin thực sự chạy, thiết bị RDMA có trạng thái phù hợp và các node trao đổi được. Với custom image, cần đặc biệt tránh để cơ chế cấu hình cũ và mới cùng tranh quyền quản lý giao diện.

## 9. Tối ưu topology CPU, bộ nhớ, GPU và thư viện

Trong workload liên kết chặt, topology bên trong node cũng quan trọng như mạng giữa node.

### 9.1. CPU và NUMA

Một node có thể gồm nhiều NUMA domain. Rank chạy trên một socket nhưng truy cập RAM ở socket khác phải chịu thêm chi phí. Đặt rank và thread có chủ đích giúp giảm di chuyển tiến trình và truy cập bộ nhớ xa.

Điểm bắt đầu hợp lý là thử số rank mỗi node, số thread mỗi rank và CPU binding theo các cấu hình có kiểm soát. Ghi cấu hình SMT và tổng số core đã cấp. Tránh oversubscription ngoài chủ đích vì nó có thể làm kết quả truyền thông biến động mạnh.

### 9.2. GPU và kết nối nội bộ

Ứng dụng GPU phân tán còn phụ thuộc CPU–GPU, GPU–GPU, GPU–NIC và thư viện collective. Một thiết bị RDMA hoạt động chưa đủ chứng minh luồng trao đổi GPU đã dùng đường tối ưu.

Chọn số rank theo mô hình của ứng dụng, thường gắn với cách phân GPU cho tiến trình. Theo dõi thời gian chờ collective và bộ nạp dữ liệu; GPU utilization thấp có thể do mạng, I/O hoặc chênh lệch công việc.

### 9.3. MPI và transport phải khớp nhau

Một số lệnh quan sát trên Linux, nếu công cụ tương ứng đã được cài:

~~~bash
hostname
lscpu
numactl --hardware
ip -br address
rdma link show
ibv_devinfo
ulimit -l
mpirun --version
ompi_info --param pml all
ucx_info -d
~~~

Các lệnh MPI/UCX ở đây áp dụng cho môi trường dùng Open MPI và UCX. Với Intel MPI hoặc thư viện khác, dùng công cụ của bộ tương ứng.

Hỗ trợ RoCE trong Open MPI hiện hành sử dụng UCX. Kiểm tra đúng phiên bản được cài và thành phần đã build theo [tài liệu InfiniBand/RoCE của Open MPI](https://docs.open-mpi.org/en/main/tuning-apps/networking/ib-and-roce.html). UCX có nhiều transport, gồm cả TCP; chỉ thấy UCX tồn tại chưa chứng minh phiên chạy đã chọn RDMA.

Bằng chứng nên kết hợp thông tin thiết bị, log lựa chọn transport, benchmark liên node và hoạt động RDMA tương ứng. Không sao chép cứng tên NIC, GID index, MTU hay cấu hình thư viện từ một shape khác.

## 10. Thiết kế dữ liệu và checkpoint

### 10.1. Chọn tầng lưu trữ theo kiểu truy cập

| Tầng | Vai trò có thể phù hợp | Câu hỏi cần trả lời |
| --- | --- | --- |
| RAM | Trạng thái nóng khi tính toán | Dữ liệu mỗi rank có vừa không, có bị swap không? |
| Local NVMe nếu shape có | Scratch, dữ liệu tạm, cache | Nếu mất node, phần nào phải tạo lại? |
| Hệ file dùng chung | Executable, thư mục làm việc, file các rank cùng đọc | Thông lượng, metadata và semantics có phù hợp không? |
| Object Storage | Input có phiên bản, checkpoint đã đóng gói, kết quả | Ứng dụng staging và xác minh dữ liệu như thế nào? |
| Block Volume | Thành phần lưu trữ hoặc dữ liệu của node theo thiết kế | Kiểu attach, filesystem và cơ chế truy cập đồng thời có hợp lệ không? |

Không dùng một filesystem thông thường trên volume chia sẻ cho nhiều máy cùng ghi nếu không có filesystem và cơ chế phối hợp hỗ trợ. Object Storage cung cấp giao diện object; ứng dụng cần POSIX phải có bước staging hoặc lớp tích hợp được đánh giá riêng.

Nhiều file nhỏ có thể bị giới hạn bởi metadata dù tổng số byte nhỏ. Đọc chung một file lớn, chia shard hay gom output là quyết định ở cấp ứng dụng, cần được benchmark cùng cấu hình lưu trữ.

Dữ liệu local NVMe bị xóa khi terminate instance theo [Terminating an Instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/terminatinginstance.htm). Vì thế, checkpoint duy nhất không được chỉ nằm trên node cần thay thế.

### 10.2. Checkpoint phải khôi phục được

Một checkpoint hữu ích cần có:

- Trạng thái ứng dụng nhất quán giữa các rank.
- Thông tin bước tính, số rank hoặc điều kiện thay đổi decomposition.
- Phiên bản input, executable và cấu hình.
- Kiểm tra tính toàn vẹn.
- Dấu hiệu hoàn tất được ghi sau khi mọi thành phần cần thiết đã lưu thành công.
- Một lần thử restart thực tế.

Nếu checkpoint gồm nhiều object, chỉ công bố manifest “hoàn tất” sau khi đã xác nhận đủ thành phần. Khi phục hồi, bỏ qua tập đang ghi dở.

Giả sử checkpoint tổng cộng 256 GiB và lưu trữ đạt thông lượng tổng hợp 4 GiB/s:

~~~text
Thời gian truyền tối thiểu ≈ 256 / 4 = 64 giây
~~~

Thực tế còn có serialize, metadata, đồng bộ và xác minh. Nếu mất 64 giây mỗi chu kỳ 1.800 giây tính toán, tỷ lệ thời gian checkpoint trong chu kỳ đầy đủ xấp xỉ:

~~~text
64 / (1.800 + 64) ≈ 3,4%
~~~

Chu kỳ ngắn giảm lượng tính toán bị mất nhưng tăng I/O. Chu kỳ dài có tác động ngược lại. Quyết định dựa trên kích thước trạng thái, thời gian chạy, lịch sử sự cố và khả năng đáp ứng của lưu trữ khi cả cụm checkpoint cùng lúc.

## 11. Thực hành: kiểm tra MPI trên hai node bằng Slurm

Mục tiêu phần này là xác nhận tiến trình chạy trên hai node và thực hiện collective đúng. Đây là kiểm tra chức năng, chưa phải phép đo RDMA hoặc benchmark hiệu năng.

### 11.1. Điều kiện của lab

- Đã có ít nhất hai compute node trong nhóm hạ tầng dự kiến.
- Slurm đã quản lý được cả hai node.
- Open MPI dùng được với Slurm và có cùng phiên bản/thư viện trên node chạy.
- Người dùng có quyền gửi job vào partition phù hợp.
- Thư mục làm việc nằm trên filesystem được mount cùng đường dẫn ở các node.
- Các lệnh dưới đây chạy trên Linux của cụm, không chạy trong PowerShell của máy cá nhân.

Nếu môi trường sử dụng module hệ thống, nạp module compiler/MPI đã được quản trị viên chỉ định trước khi biên dịch và nạp cùng môi trường trong batch job. Không trộn mpicc của một MPI với mpirun của MPI khác.

### 11.2. Tạo chương trình kiểm tra

Lưu đoạn sau thành mpi-check.c trong thư mục làm việc dùng chung:

~~~c
#include <mpi.h>
#include <stdio.h>

int main(int argc, char **argv) {
    int rank, size, name_len;
    char host[MPI_MAX_PROCESSOR_NAME];

    MPI_Init(&argc, &argv);
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &size);
    MPI_Get_processor_name(host, &name_len);

    long long local = (long long)rank + 1;
    long long total = 0;

    MPI_Allreduce(&local, &total, 1, MPI_LONG_LONG_INT,
                  MPI_SUM, MPI_COMM_WORLD);

    long long expected = (long long)size * (size + 1LL) / 2;
    int ok = (total == expected);

    printf("rank=%d size=%d host=%.*s sum=%lld expected=%lld ok=%d\n",
           rank, size, name_len, host, total, expected, ok);
    fflush(stdout);

    MPI_Finalize();
    return ok ? 0 : 1;
}
~~~

Biên dịch:

~~~bash
mpicc -O2 -Wall -Wextra mpi-check.c -o mpi-check
~~~

Chương trình cộng các giá trị từ 1 đến số rank bằng MPI_Allreduce. Với bốn rank, tổng mong đợi là 10. Thứ tự các dòng in ra không được bảo đảm.

### 11.3. Gửi job có allocation rõ ràng

Lưu batch script dưới tên mpi-check.sbatch:

~~~bash
#!/usr/bin/env bash
#SBATCH --job-name=mpi-check
#SBATCH --nodes=2
#SBATCH --ntasks=4
#SBATCH --ntasks-per-node=2
#SBATCH --cpus-per-task=1
#SBATCH --time=00:05:00
#SBATCH --output=mpi-check-%j.out

set -euo pipefail

# Nap lai module compiler/MPI tai day neu he thong yeu cau.
cd "$SLURM_SUBMIT_DIR"

echo "job=$SLURM_JOB_ID nodes=$SLURM_JOB_NODELIST"
mpirun ./mpi-check
~~~

Chọn partition thực tế khi gửi:

~~~bash
sbatch --partition=<ten-partition-thuc-te> mpi-check.sbatch
squeue --user="$USER"
~~~

Thay placeholder trước khi thực thi. Với Open MPI tương thích Slurm, mpirun lấy node và số task từ allocation; không cần thêm hostfile. Cơ chế này được giải thích tại [Launching with Slurm](https://docs.open-mpi.org/en/main/launching-apps/slurm.html). Nếu dùng cơ chế direct launch bằng srun, phải kiểm tra PMI/PMIx và hướng dẫn của bộ MPI đang dùng.

Tiêu chí đạt:

1. Job được cấp hai node đúng partition.
2. Có bốn rank thuộc cùng một MPI world với size bằng 4.
3. Log ghi nhận hai hostname dự kiến.
4. Mỗi rank có sum bằng 10 và ok bằng 1.
5. Job kết thúc thành công.

Nếu chỉ thấy một hostname hoặc mỗi tiến trình đều có size bằng 1, cần kiểm tra launcher và tích hợp scheduler trước khi đánh giá mạng.

### 11.4. Chứng minh RDMA bằng phép đo riêng

Sau khi kiểm tra chức năng đạt, chạy benchmark liên node trong allocation phù hợp. Có thể dùng bộ benchmark MPI như OSU Micro-Benchmarks hoặc Intel MPI Benchmarks nếu đã được cài và phù hợp với MPI đang dùng.

Bằng chứng RDMA gồm nhiều lớp:

- Các tiến trình đo thực sự chạy ở hai node khác nhau.
- Transport được lựa chọn tương ứng thiết bị RDMA dự kiến.
- Giao diện RDMA có hoạt động phù hợp trong cửa sổ đo.
- Kết quả latency/bandwidth ổn định và có thể lặp lại theo baseline.
- Ứng dụng thực tế cải thiện theo mục tiêu đã đặt.

Dòng log “job thành công”, ping nhanh hoặc tốc độ iperf qua VCN chỉ trả lời những câu hỏi hẹp hơn. Một benchmark thông điệp rất nhỏ cũng có thể tạo quá ít byte để biểu hiện rõ trên biểu đồ metrics lấy mẫu thưa; khi đó cần dựa thêm vào công cụ tại node và log transport.

## 12. Xây dựng phép đo hiệu năng có thể so sánh

### 12.1. Ghi đủ bối cảnh mỗi lần đo

Mỗi kết quả cần gắn với region/AD, loại nhóm cụm, shape, image, kernel, driver, MPI/UCX, số node, số rank, số thread, CPU binding, phiên bản input và executable.

Giữ nguyên những yếu tố không thuộc biến đang khảo sát. Ví dụ, khi đo strong scaling, không đồng thời đổi shape, thuật toán solver và filesystem rồi quy mọi cải thiện cho RDMA.

Tách các khoảng thời gian:

~~~text
T_total =
    T_queue
  + T_provision
  + T_bootstrap
  + T_stage_in
  + T_compute
  + T_stage_out
~~~

Tối ưu T_compute có thể chưa giảm T_total nếu cụm cần rất lâu để cấp phát hoặc dữ liệu đầu vào phải tải lại mỗi lần.

### 12.2. Đo từ thành phần đến ứng dụng

| Phép đo | Câu hỏi chính | Giới hạn diễn giải |
| --- | --- | --- |
| Ping-pong thông điệp nhỏ | Độ trễ liên node theo benchmark là bao nhiêu? | Không đại diện mọi collective |
| Bandwidth thông điệp lớn | Có khai thác được đường truyền không? | Không mô tả overhead thông điệp nhỏ |
| Allreduce/Alltoall theo nhiều rank | Đồng bộ tăng chi phí thế nào khi mở rộng? | Phụ thuộc thuật toán và kích thước dữ liệu |
| Benchmark I/O | Staging, checkpoint hoặc metadata có bị nghẽn? | Phải khớp mẫu truy cập của ứng dụng |
| Solver hoặc training thật | Thời gian và kết quả có đạt yêu cầu? | Cần kiểm soát phiên bản và tính đúng đắn |

Chạy warm-up, sau đó lặp phép đo và lưu phân bố. Khi báo p99, cần có đủ số mẫu và mô tả cách thu thập; p99 từ vài lần chạy không phải kết luận đáng tin cậy.

Chọn thêm các cặp node hoặc nhóm node đại diện. Một cặp nhanh không đảm bảo cả cụm không có straggler. Ghi lại thời gian tính toán và truyền thông theo rank khi profiler hỗ trợ.

### 12.3. Ví dụ strong scaling và node-hour

Bảng sau là **dữ liệu giả định để minh họa cách tính**, không phải benchmark OCI:

| Node đồng nhất | Thời gian tính toán, phút | Speedup so với một node | Hiệu suất | Node-hour |
| --- | --- | --- | --- | --- |
| 1 | 120 | 1,00 | 100% | 2,00 |
| 2 | 68 | 1,76 | 88,2% | 2,27 |
| 4 | 40 | 3,00 | 75,0% | 2,67 |
| 8 | 32 | 3,75 | 46,9% | 4,27 |

Từ bốn lên tám node, thời gian giảm tám phút nhưng node-hour tăng khoảng 60%. Nếu thời hạn là 45 phút và bỏ qua overhead, bốn node đáp ứng với lượng tài nguyên thấp hơn. Nếu thời hạn là 35 phút, tám node có thể là lựa chọn cần thiết.

Cần cộng staging, khởi tạo và chi phí các thành phần khác trước khi đưa ra quyết định vận hành. Nếu baseline một node dùng hết bộ nhớ và bị swap, kết quả speedup có thể gây hiểu nhầm; phải kiểm tra điều kiện đo.

## 13. Giám sát từ phần cứng đến job

Giám sát HPC cần ghép ba góc nhìn: tình trạng node, hành vi truyền thông và tiến độ ứng dụng.

| Lớp quan sát | Tín hiệu cần thu | Mục đích |
| --- | --- | --- |
| CPU/bộ nhớ | Utilization, RAM, swap, NUMA, iowait | Phân biệt tính toán, thiếu RAM và chờ I/O |
| RDMA | Lưu lượng, trạng thái link, lỗi liên quan thiết bị | Phát hiện đường truyền lỗi hoặc bất thường giữa node |
| GPU nếu có | Utilization, memory, lỗi phần cứng | Tìm GPU nhàn rỗi và straggler |
| Scheduler | Pending reason, node state, queue time, allocation | Phân biệt thiếu capacity với node không sẵn sàng |
| Ứng dụng | Iteration time, tỷ lệ hội tụ, thời gian collective | Kiểm tra tiến độ có thực sự tăng không |
| Lưu trữ | Thông lượng, latency, metadata, thời gian checkpoint | Xác định nghẽn I/O và nguy cơ mất tiến độ |

OCI cung cấp các namespace HPC như rdma_infrastructure_health và gpu_infrastructure_health. Ví dụ, RdmaTxBytes/RdmaRxBytes phản ánh byte trên giao diện RDMA; RdmaLinkSpeedFault là tín hiệu lỗi, không phải số đo latency. Phải đọc semantics, unit và dimension trước khi xây truy vấn theo [High Performance Computing Metrics](https://docs.oracle.com/en-us/iaas/Content/Compute/References/high-performance-computing-metrics.htm).

Không dùng trung bình toàn cụm làm tín hiệu duy nhất: một node lỗi có thể bị che bởi phần còn lại. Nên có khả năng xem theo instance và thiết bị, đồng thời liên hệ cửa sổ thời gian với job ID. Metrics lấy mẫu theo giây hoặc phút cũng không thay thế benchmark đo ở mức microsecond.

Plugin monitoring, IAM và đường đi đến endpoint phải được cấu hình đầy đủ. Metrics phát vào customer namespace có thể phát sinh chi phí theo chính sách dịch vụ. Khi thiếu metrics, kiểm tra cả đường phát dữ liệu trước khi kết luận node không hoạt động.

Các cảnh báo hữu ích gắn với hành động cụ thể: node có lỗi link thì ngừng nhận job mới; iteration time tăng kéo dài thì thu profiler; checkpoint không hoàn tất thì giữ lại bản hợp lệ trước đó và điều tra lưu trữ.

## 14. Chẩn đoán lỗi theo thứ tự có bằng chứng

| Triệu chứng | Giả thuyết cần kiểm tra trước | Bước quan sát phù hợp |
| --- | --- | --- |
| Không tạo đủ node | Limit, quota, shape/AD không phù hợp hoặc thiếu capacity | Lifecycle, lỗi API và số lượng node thực tế |
| Node không vào hàng đợi | Bootstrap, mount, DNS hoặc Slurm chưa sẵn sàng | Log khởi tạo, node state và cấu hình scheduler |
| MPI không khởi chạy | Launcher, môi trường, quyền file hoặc kết nối điều phối | Chạy lab nhỏ, so sánh PATH và thư viện |
| MPI chạy nhưng chậm | TCP fallback, binding, NUMA, I/O hoặc mất cân bằng | Log transport, profiler và benchmark thành phần |
| Chỉ một số node chậm | Lỗi thiết bị, cấu hình lệch, local disk hoặc tác vụ cạnh tranh | So sánh node tốt/xấu với cùng phép đo |
| Collective tăng đột biến | Straggler, nghẽn mạng, CPU scheduling hoặc checkpoint | Timeline theo rank và các sự kiện cùng thời điểm |
| Hiệu năng giảm sau cập nhật | Kernel, driver, MPI, image hoặc cấu hình đã đổi | Đối chiếu manifest phiên bản và baseline |
| Job mất tiến độ sau thay node | Checkpoint không đầy đủ hoặc chỉ nằm trên scratch | Kiểm tra manifest và thử restart bản đã xác minh |

Quy trình điều tra nên thu hẹp theo lớp:

1. Xác nhận job có đúng tài nguyên, node và tư cách thành viên cụm.
2. Xác nhận thiết bị, driver, plugin và xác thực RDMA.
3. Xác nhận MPI runtime cùng transport được lựa chọn.
4. So sánh benchmark hai node với baseline.
5. Kiểm tra collective, CPU binding và NUMA.
6. Kiểm tra I/O và đặc tính ứng dụng.

Chỉ thay một nhóm biến có liên quan mỗi lần. Nếu vừa thay MTU, driver, MPI và số rank, một lần chạy nhanh hơn sẽ không cho biết nguyên nhân.

Trước khi thay node hoặc cập nhật phần mềm, thu log và đưa node ra khỏi luồng nhận job mới. Không dùng việc tắt firewall hay vô hiệu hóa authentication làm cấu hình lâu dài để xử lý sự cố.

## 15. Độ sẵn sàng và phục hồi của workload liên kết chặt

### 15.1. Placement gần nhau và phạm vi lỗi

Tập trung node trong một AD phục vụ mục tiêu latency, nhưng tạo phụ thuộc vào phạm vi hạ tầng đó. Không thiết kế một job MPI liên kết chặt trải qua nhiều region rồi kỳ vọng giữ độ trễ RDMA nội cụm.

Một job MPI thông thường có thể phải kết thúc khi mất một rank. Khả năng tiếp tục chạy khi thành viên lỗi phụ thuộc vào thư viện, ứng dụng và thiết kế chịu lỗi cụ thể; nhiều máy không tự mang lại tính sẵn sàng cho một lần chạy.

Phương án thực tế thường là giữ dữ liệu bền vững, checkpoint nhất quán và có khả năng tạo lại cụm. Với yêu cầu phục hồi ngoài AD/region, cần sao chép dữ liệu theo khả năng của dịch vụ được chọn và đánh giá thời gian cấp lại capacity ở đích.

### 15.2. Thay node và thay đổi quy mô theo scheduler

Một chu trình thay node có kiểm soát:

~~~text
Phát hiện lỗi
    -> Ngừng cấp job mới cho node
    -> Chờ job hoàn tất hoặc checkpoint/cancel theo chính sách
    -> Lưu log và xác nhận checkpoint bền vững
    -> Thay node
    -> Kiểm tra phần cứng, mạng và MPI
    -> Đưa node trở lại hàng đợi
    -> Khôi phục hoặc gửi lại job
~~~

Không giảm trực tiếp số instance đang chạy rank mà không phối hợp với Slurm. Khi tăng node, chỉ đánh dấu sẵn sàng sau khi image, mount, agent, MPI và scheduler đã đồng nhất.

Với cluster network dùng pool, thao tác resize cần tuân theo mô hình tài nguyên của OCI và được ghép với vòng đời node trong scheduler. Xem [Resizing a Cluster Network with Instance Pools](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/resize-cluster-network.htm). Đổi kích thước pool không tự bảo đảm một job MPI đang chạy có thể thay đổi số rank.

### 15.3. RTO và RPO phải có số đo

RTO gồm thời gian phát hiện lỗi, quyết định phục hồi, cấp capacity, cấu hình node, tải checkpoint và chạy tiếp. RPO của tiến độ tính toán phụ thuộc vào checkpoint hợp lệ gần nhất.

Ví dụ, checkpoint mỗi 30 phút không tự bảo đảm chỉ mất tối đa 30 phút nếu bản gần nhất còn đang ghi hoặc chưa sao chép đến nơi phục hồi. Cần đo cả thời gian xuất bản checkpoint và thử nghiệm restart.

Trạng thái Slurm controller, cấu hình hàng đợi, tài khoản và phần mềm cũng phải có đường phục hồi. Một tập compute node có thể tạo lại nhưng thiếu scheduler state hoặc license vẫn chưa tạo thành môi trường vận hành được.

## 16. Kiểm soát chi phí theo kết quả hoàn thành

### 16.1. Tính đủ vòng đời tài nguyên

Một mô hình dự toán:

~~~text
Chi phí mỗi job =
    tổng(node-hour của từng loại node × đơn giá tương ứng)
  + phần chi phí controller/login phân bổ
  + lưu trữ và thao tác dữ liệu
  + truyền dữ liệu thuộc diện tính phí
  + license phần mềm
  + logging/monitoring và dịch vụ liên quan
~~~

Thời gian node được cấp phát có thể lớn hơn thời gian solver chạy. Bao gồm cả chờ staging, bootstrap, thời gian rảnh và các lần chạy lại. Với nhiều job, so sánh tổng chi phí chia cho số kết quả hoàn thành đạt yêu cầu.

Dùng đơn giá hiện hành theo region, shape và hợp đồng thực tế khi lập ngân sách. Không coi việc stop mọi loại bare metal hoặc thành phần lưu trữ là chắc chắn dừng toàn bộ phí; phải kiểm tra quy tắc tính phí của từng tài nguyên.

### 16.2. Mở rộng theo hàng đợi, thu hồi theo trạng thái công việc

Một cơ chế mở rộng hữu ích cần biết số job đang đợi, tài nguyên mỗi job, thời hạn, giới hạn node và thời gian khởi tạo. CPU utilization thấp đơn độc là tín hiệu không đủ: job có thể đang đợi I/O hoặc collective.

Khi thu hồi, đánh dấu node không nhận job mới, chờ allocation kết thúc, xác minh kết quả/checkpoint rồi mới giải phóng. Quy định rõ ai được phép hủy job, trường hợp nào cần giữ node để điều tra và thời gian rảnh tối đa được chấp nhận.

Đặt nhãn chủ sở hữu, dự án, môi trường và thời hạn sử dụng cho tài nguyên. Job log nên liên kết được với cấu hình cụm và cửa sổ cấp phát để phân bổ chi phí.

### 16.3. Budget là cảnh báo, không phải công tắc dừng

OCI Budgets đặt ngưỡng mềm và phát cảnh báo; không tự ngăn tài nguyên tiếp tục phát sinh phí. Xem [Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm).

Nếu cần hành động tự động, phải thiết kế cơ chế riêng có kiểm soát: giới hạn quy mô, thời hạn tài nguyên, kiểm tra trạng thái job, checkpoint và quy trình thu hồi. Không dùng một cảnh báo chi phí đến trễ làm cơ chế duy nhất bảo vệ ngân sách của cụm lớn.

Sau một đợt thực hành, kiểm kê cả compute node, head node, boot/block volume, filesystem, object, bản sao lưu và thành phần mạng có tính phí. Chỉ xóa dữ liệu sau khi xác minh kết quả cần giữ đã được lưu đúng nơi.

## 17. Hồ sơ bàn giao một cụm HPC có thể vận hành

Một lần triển khai có thể bàn giao khi có đủ bằng chứng sau:

| Nhóm bằng chứng | Nội dung cần lưu |
| --- | --- |
| Phù hợp workload | Mẫu trao đổi, nhu cầu RAM/GPU/I/O và lý do chọn số node |
| Hạ tầng OCI | Compartment, AD, shape, mô hình cụm, image và thành viên thực tế |
| Quyền và kết nối | Phân vai IAM, tài khoản Linux, đường quản trị, egress và truy cập dữ liệu |
| Runtime | Phiên bản driver/MPI, kiểm tra plugin, thiết bị và transport được sử dụng |
| Chức năng | MPI chạy trên đúng các node, collective trả kết quả đúng |
| Hiệu năng | Benchmark có bối cảnh, strong/weak scaling phù hợp và biến động giữa lần chạy |
| Dữ liệu | Input có phiên bản, checkpoint hoàn tất và kết quả thử restart |
| Vận hành | Cảnh báo, quy trình drain/thay node và phương án khi thiếu capacity |
| Chi phí | Ước tính cho toàn vòng đời, ngưỡng mở rộng và cơ chế thu hồi |

Ngưỡng chấp nhận phải xuất phát từ ứng dụng. Ví dụ, một solver có thể yêu cầu hoàn thành trong 45 phút, checkpoint dưới hai phút và restart được từ bản gần nhất. Một workload khác có thể ưu tiên số kết quả trên mỗi đơn vị chi phí. Đặt ngưỡng trước khi đo giúp lựa chọn cấu hình dựa trên mục tiêu kiểm chứng được.

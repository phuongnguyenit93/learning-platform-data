# Machine families, machine types và cấu hình máy tùy chỉnh trong Compute Engine

> **Chương:** Compute Engine  
> **Bài học:** Machine families, machine types và cấu hình máy tùy chỉnh  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. Thông qua các tình huống triển khai, người học cần biết chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành, theo dõi độ tin cậy và chi phí. Trong Compute Engine, một quyết định có tác động trực tiếp đến tất cả mục tiêu đó là **chọn loại máy ảo (VM)**.

Một ứng dụng Java cần nhiều RAM nhưng CPU ít khác với máy chủ tính toán khoa học cần CPU mạnh; API có lưu lượng đều khác với batch có thể bị gián đoạn; workload AI cần GPU khác với hệ thống cần dung lượng SSD lớn và IOPS cao. Chọn machine type không chỉ là “có bao nhiêu vCPU và GB RAM”, mà còn liên quan **kiến trúc CPU, hiệu năng mạng/đĩa, tính khả dụng theo zone, khả năng mở rộng và chi phí trọn vòng đời**.

Bài này tập trung vào **machine family**, **machine series**, **predefined machine type** và **custom machine type**, với các ví dụ trên Google Cloud Console và Google Cloud CLI (`gcloud`). Các tên project, VM và số liệu tải trong bài là giả định; kiểm tra tính sẵn có theo region/zone và tài liệu hiện hành khi triển khai thật.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích hệ phân cấp **machine family → machine series → machine type → instance**.
2. Phân biệt các hướng tối ưu: **general-purpose/cost-optimized**, **compute-optimized**, **memory-optimized**, **storage-optimized**, **accelerator-optimized** và các series hướng mạng.
3. Đọc tên kiểu máy như `e2-standard-4`, `n2-highmem-8` và `e2-custom-4-12288`, hiểu ý nghĩa vCPU/RAM mà không suy sai mọi dòng đều có cùng tỷ lệ.
4. Chọn **predefined** hay **custom** dựa trên nhu cầu đo được, giới hạn phần cứng và chi phí.
5. Nhận ra các ràng buộc custom machine types: series hỗ trợ, số vCPU hợp lệ, RAM tối thiểu/tối đa, bước điều chỉnh và **extended memory**.
6. Dùng CLI để liệt kê/kiểm tra loại máy, tạo VM thử nghiệm và thay đổi machine type đúng quy trình.
7. Đánh giá lựa chọn CPU architecture, boot image, disk, networking, GPU, quota, zone capacity, bản quyền phần mềm và security.
8. Thiết kế thử nghiệm **right-sizing**, đánh giá độ tin cậy, availability và tổng chi phí trước khi áp vào production.

## 2. Bốn cấp độ tên gọi thường bị nhầm

| Cấp độ | Nghĩa | Ví dụ minh họa |
|---|---|---|
| **Machine family** | Nhóm định hướng theo kiểu tải và mục tiêu hiệu năng | General-purpose, memory-optimized, accelerator-optimized |
| **Machine series** | Một dòng phần cứng/cấu hình cụ thể trong một family | E2, N2, N2D, N4, C4, M4, G4 |
| **Machine type** | Kết hợp CPU/RAM và đặc tính tài nguyên cụ thể trong series | `e2-standard-4`, `n2-highmem-8` |
| **VM instance** | Máy ảo đang được tạo/vận hành trong project và zone | `orders-api-01` chạy kiểu `e2-standard-4` |

Một **machine series** có thể hỗ trợ nhiều kiểu máy định sẵn; một số series hỗ trợ thêm **custom machine type**. Tên series tự nó không phải cấu hình VM đầy đủ.

~~~mermaid
flowchart TD
    F["Machine families<br/>Theo mục tiêu workload"]
    F --> G["General-purpose"]
    F --> C["Compute-optimized"]
    F --> M["Memory-optimized"]
    F --> A["Accelerator-optimized"]
    F --> S["Storage-optimized"]
    G --> E2["Series E2"]
    G --> N2["Series N2"]
    G --> N4["Series N4"]
    E2 --> P["Predefined: e2-standard-4"]
    E2 --> U["Custom: e2-custom-4-12288"]
    P --> VM1["VM instance: web-01"]
    U --> VM2["VM instance: worker-01"]
~~~

Sơ đồ tập trung vào **nguyên tắc phân cấp** và chỉ hiển thị một phần danh mục; Google Cloud thường xuyên bổ sung/chỉnh sửa series, generation và khả năng triển khai theo zone.

### 2.1. Machine family không đồng nghĩa CPU vendor

Các series có thể sử dụng CPU Intel, AMD hoặc Arm do Google thiết kế/hợp tác, tùy thế hệ. Ví dụ:

- `N2` thường thuộc nhóm x86 Intel; `N2D` thuộc x86 AMD.
- `N4` và `N4D` có nền tảng khác nhau; `N4A` dùng Google Axion dựa trên Arm.
- `C4A`, `T2A` cũng là những ví dụ Arm theo generation và phân khúc khác nhau.
- Một số dòng tối ưu GPU có CPU đi kèm khác nhau tùy series và cấu hình.

**Không chọn theo một chữ cái trong tên để suy ra ISA.** Luôn tra **architecture (`x86_64` hay `arm64`)**, CPU platform và sự hỗ trợ image/phần mềm cho series đang định dùng.

### 2.2. vCPU không nhất thiết là một lõi vật lý độc lập

Trong nhiều VM x86, một **vCPU** tương ứng với một hardware thread; hệ số tương quan với lõi vật lý tùy nền tảng và chính sách SMT của dòng máy. Hiệu năng thực tế còn phụ thuộc xung nhịp, vi kiến trúc, cache, NUMA, overcommit hoặc mô hình chia sẻ CPU. Một VM `4 vCPU` ở series A không được mặc định có thông lượng bằng VM `4 vCPU` ở series B.

Đặc biệt, VM **shared-core** cung cấp mức CPU được chia sẻ/burst theo đặc tính loại máy, khác với cách đánh giá một VM dedicated-vCPU thông thường.

## 3. Những nhóm workload và machine families

Dưới đây là cách nhìn theo **mục tiêu thiết kế**. Tên và cách phân loại series có thể thay đổi theo thế hệ; tra bảng comparison của Google Cloud khi chọn SKU.

| Family / định hướng | Workload thường phù hợp | Ví dụ series | Đánh đổi chính |
|---|---|---|---|
| **General-purpose** | Web/API, ứng dụng Java thông thường, middleware, dev/test, nhiều dịch vụ đa năng | E2, N2/N2D, N4/N4D/N4A, một số dòng C3/C4 | Cân bằng CPU, RAM, mạng và giá; khác biệt lớn giữa generation |
| **Cost-optimized / tiết kiệm** | Tải nhỏ, ít yêu cầu CPU, ứng dụng thực hành | E2, E2 shared-core | Chi phí thấp cho bài toán phù hợp; phải kiểm tra hiệu năng ổn định/burst |
| **Compute-optimized** | Tải CPU cao, tính toán kỹ thuật, HPC cần thông lượng | C2/C2D, H3/H4D theo tính năng | Hiệu năng CPU cao; tỷ lệ RAM, mạng và phần cứng theo series |
| **Memory-optimized** | In-memory database, bộ nhớ cache lớn, SAP/ứng dụng cần RAM cao | M1/M2/M3/M4, một số series chuyên dụng mới | Chi phí RAM lớn, ít linh hoạt; ràng buộc phần mềm/zone |
| **Storage-optimized** | I/O ngẫu nhiên cao, dữ liệu nóng, hệ thống phụ thuộc ổ cục bộ | Z3 và các series Z chuyên dụng | Nhiều local storage; cần chiến lược dữ liệu bền vững/replication |
| **Accelerator-optimized** | ML training/inference, rendering hoặc tác vụ GPU | G2/G4, A2/A3/A4 và các series hỗ trợ mới | GPU/VRAM, driver, quota, capacity và chi phí cao |
| **Network-optimized / cấu hình mạng chuyên biệt** | Data plane yêu cầu throughput/latency mạng cao | C4N, một số dòng memory/network đặc thù | Ràng buộc topology, vùng triển khai và giá |

**Ghi chú:** Cùng chữ “C” nhưng **C2** và **C4** có thể xuất hiện trong nhóm khác nhau trong bảng phân loại thế hệ mới. Hãy bắt đầu từ **workload profile và thông số chính thức**, không gán vĩnh viễn cả họ chữ C là compute-optimized.

### 3.1. General-purpose: điểm xuất phát cho phần lớn hệ thống

Nếu chưa có benchmark, general-purpose thường là nơi hợp lý để bắt đầu:

- **E2:** hướng hiệu quả chi phí; phù hợp dev/test, web service nhỏ hoặc tải vừa nếu độ trễ/hiệu năng được kiểm chứng.
- **N2/N2D:** general-purpose dựa trên x86, hỗ trợ predefined và custom trong các giới hạn cụ thể.
- **N4/N4D/N4A:** thế hệ mới trong nhóm general-purpose; khi chọn cần xét CPU vendor/architecture, series availability và hệ sinh thái hình ảnh máy.
- **T2A/T2D:** các dòng Tau theo CPU/ISA nhất định, thích hợp khi workload chạy được trên phần cứng tương ứng; không được suy luận có mọi tùy chọn custom.

Ví dụ REST API Java có 250 request/giây không tự động “cần C4 vì nhiều request”. Nếu CPU thực tế chỉ 25%, RAM 70% và thời gian chờ chủ yếu nằm ở Cloud SQL, việc tăng CPU đơn thuần có thể không cải thiện p95 latency.

### 3.2. Compute-optimized

Khi ứng dụng **bị giới hạn CPU** (CPU-bound) và lợi ích đo được khi tăng sức mạnh xử lý đơn luồng/đa luồng, đánh giá compute-optimized như các dòng C2/C2D hoặc HPC series theo khả năng hiện hành.

Ví dụ: batch xử lý ảnh, chạy mô phỏng khoa học, compile nặng hoặc tính toán số học liên tục. Cần kiểm tra:

- Hiệu năng **single-thread** và **multi-thread**.
- Bộ nhớ/cache trên mỗi vCPU, đặc điểm NUMA, băng thông RAM.
- Kích thước instance có sẵn tại zone.
- Chỉ số **thời gian xử lý trên một đơn vị công việc**, thay vì chỉ CPU utilization.

### 3.3. Memory-optimized

Dùng khi RAM là nút thắt chính, chẳng hạn database trong bộ nhớ, hệ thống phân tích dữ liệu lớn hoặc ứng dụng được cấp phép theo số core nhưng cần RAM cao. Trước khi chọn dòng M lớn:

1. Xác nhận working set thực tế, page faults, swap và khả năng cache của ứng dụng.
2. Xem có thể xử lý bằng tối ưu query/index, tách dữ liệu hoặc cache tier không.
3. So sánh **custom with extended memory** trên series N hỗ trợ với **memory-optimized predefined** nếu chi phí và kích thước cho phép.
4. Xác minh các ràng buộc software licensing, OS image, zone availability và kế hoạch HA.

Nhiều RAM **không thay** chiến lược backup, replication và recovery của database.

### 3.4. Accelerator-optimized

Workload ML có thể cần GPU để đạt throughput hoặc latency mục tiêu. Các dòng G/A hỗ trợ tổ hợp CPU, RAM, GPU và local storage riêng; trong nhiều trường hợp **số GPU là một thành phần cố định của machine type**.

Trước khi chọn:

- Cần GPU loại gì, bao nhiêu **VRAM**, độ chính xác tính toán và bộ công cụ CUDA/driver nào?
- Là training, inference trực tuyến hay batch có thể ngắt?
- Có cần high-speed networking giữa nhiều node GPU không?
- Có quota và capacity tại zone dự kiến không?
- Có thể dùng **Vertex AI** hoặc dịch vụ managed để giảm gánh nặng vận hành không?

Không mặc định GPU là tùy chọn gắn vào mọi machine type. Các họ accelerator có cách cấu hình khác nhau; thậm chí máy N1 gắn GPU và G2 custom có quy tắc riêng.

### 3.5. Storage-optimized và giới hạn của local SSD

Dòng storage-optimized có thể cung cấp dung lượng/hiệu năng lưu trữ cục bộ lớn, phù hợp database hoặc pipeline có yêu cầu IOPS cao. Tuy nhiên **Local SSD** không nên được coi là bản sao bền vững duy nhất. Dữ liệu có thể bị mất trong các sự kiện dừng/xóa/tái tạo hoặc thay đổi vòng đời theo đặc tính sản phẩm.

Đối với dữ liệu không được mất, thiết kế **Persistent Disk/Hyperdisk**, replication, snapshot và backup phù hợp. Băng thông/IOPS còn bị giới hạn bởi cả **machine type**, loại/size đĩa và cấu hình; mua disk tốc độ cao không đồng nghĩa VM nào cũng đạt thông số tối đa của disk.

## 4. Đọc predefined machine types

### 4.1. Quy tắc đặt tên phổ biến

Một số machine series sử dụng dạng:

~~~text
<series>-<ratio/profile>-<vCPU count>
~~~

Ví dụ:

| Machine type | Cách hiểu | Lưu ý |
|---|---|---|
| `e2-standard-2` | Series E2, profile standard, 2 vCPU | RAM theo profile E2 standard |
| `e2-standard-4` | E2, standard, 4 vCPU | Ví dụ general-purpose |
| `n2-highmem-8` | N2, tỷ lệ RAM/vCPU cao, 8 vCPU | Phù hợp workload thiên RAM |
| `n2-highcpu-8` | N2, tỷ lệ RAM/vCPU thấp, 8 vCPU | Cần kiểm tra RAM thực tế |
| `e2-micro` | E2 shared-core nhỏ | Không đọc `micro` là số vCPU cố định |

Nhiều series mới có naming convention khác, gồm biến thể CPU, local SSD, GPU hoặc cấu hình chuyên dụng. **Luôn dùng `gcloud compute machine-types describe` hoặc trang tài liệu để đọc đúng `guestCpus` và `memoryMb`**, không “tính nhẩm” từ tên dòng chưa biết.

### 4.2. Standard, highmem, highcpu là tỷ lệ khác nhau

So với một máy `standard` có cùng số vCPU:

- `highmem` thường có **nhiều RAM/vCPU** hơn.
- `highcpu` thường có **ít RAM/vCPU** hơn.
- `standard` thường chọn tỷ lệ cân bằng của series.

Nhưng tỷ lệ cụ thể **khác theo series/generation**. Đừng lấy tỷ lệ `n2-highmem` để suy RAM của `c4-highmem`.

### 4.3. Predefined phù hợp khi nào?

**Ưu điểm:**

- Cấu hình đã định nghĩa, dễ chuẩn hóa cho instance template, managed instance group (MIG) và runbook.
- Thuận tiện so sánh giá và giới hạn tài nguyên.
- Phù hợp khi tỷ lệ vCPU/RAM gần nhu cầu workload thực tế.

**Giới hạn:**

- Có thể cấp dư RAM hoặc vCPU nếu ứng dụng có tỷ lệ tài nguyên khác profile.
- Loại lớn hơn đôi khi tăng cả CPU lẫn RAM trong khi chỉ thiếu một yếu tố.
- Cấu hình không có tại tất cả zone hoặc không còn đủ capacity.

Không chọn custom chỉ để “tối ưu” một chênh lệch nhỏ; trước tiên hãy đo chi phí và rủi ro duy trì cấu hình khác chuẩn.

## 5. Custom machine types: vì sao và khi nào dùng?

**Custom machine type** cho phép chọn số vCPU và lượng RAM trong **giới hạn được series cho phép**, thay vì chọn một profile predefined có tỷ lệ cố định.

Giả sử ứng dụng Java có:

- CPU thường 30–45%, đỉnh 75% trên máy 4 vCPU.
- RAM dùng ổn định khoảng 9–10 GiB, đặt mục tiêu cần 12 GiB.
- Predefined gần nhất theo profile đang xem có quá nhiều RAM hoặc không khớp tỷ lệ yêu cầu.

Một ứng viên là:

~~~text
e2-custom-4-12288
│  │      │ └── 12,288 MB (12 GiB theo cách gọi Compute Engine)
│  │      └──── 4 vCPU
│  └─────────── custom machine type
└────────────── E2 machine series
~~~

Đây là **cấu hình hợp lệ theo giới hạn E2 hiện hành**: 4 vCPU, 12 GiB RAM, bằng 3 GiB/vCPU và số MB chia hết cho 256. Tuy nhiên **hợp lệ không đồng nghĩa tối ưu**. Phải so sánh với predefined `e2-standard-4`, `e2-highmem-4` và các series khác, xét hiệu năng/giá thực.

### 5.1. Không phải series nào cũng hỗ trợ custom

Tài liệu Compute Engine hiện hành liệt kê custom general-purpose tại một số series:

| Machine series | Custom general-purpose? | Điểm cần nhớ |
|---|---|---|
| **E2** | Có | Cấu hình `e2-custom-*`, không có extended memory |
| **N1** | Có | Tên custom bắt đầu `custom-*`, không có tiền tố `n1-` |
| **N2 / N2D** | Có | Giới hạn vCPU/RAM theo series; hỗ trợ extended memory |
| **N4 / N4D / N4A** | Có | Giới hạn số vCPU khác nhau; hỗ trợ extended memory |
| **G2** | Có theo quy tắc GPU đặc biệt | Cấu hình vCPU/RAM phụ thuộc số GPU; không xem như N-series custom thông thường |
| **Các series khác** | Không tự suy có hỗ trợ | Kiểm tra danh sách custom types chính thức từng thời điểm |

**Cảnh báo:** các series N4A/Arm và N4D/AMD không có cùng danh sách số vCPU hợp lệ chỉ vì đều bắt đầu bằng `N4`.

### 5.2. Ví dụ về ràng buộc vCPU/RAM

Bảng dưới nhằm minh họa cách đọc giới hạn chính thức; **cần xác minh lại tại thời điểm triển khai** vì series có thể thay đổi.

| Series | Số vCPU ví dụ được hỗ trợ cho custom | RAM chuẩn trên mỗi vCPU, trong giới hạn minh họa | Extended memory |
|---|---|---|---|
| **E2** | 2, 4, …, 32 | 0,5–8 GiB/vCPU | Không |
| **N2** | 2–32 theo bước 2; mức lớn hơn theo bước hỗ trợ | 0,5–8 GiB/vCPU | Có |
| **N2D** | 2, 4, 8, 16, 32, 48, 64, 80, 96 | 0,5–8 GiB/vCPU | Có |
| **N4** | 2–80, bội số 2 | 2–8 GiB/vCPU | Có |
| **N4D** | 2, 4, 8, 16, 32, 48, 64, 80, 96 | 0,5–8 GiB/vCPU | Có |
| **N4A** | 1–64, tùy cấu hình cho phép | 2–8 GiB/vCPU | Có |
| **N1** | 1 hoặc số chẵn phù hợp, đến 96 | Tỷ lệ riêng của N1 | Có |

Cần kiểm tra **số vCPU tối đa, bước số vCPU, RAM trên mỗi vCPU, tổng RAM tối đa và mức tăng RAM theo MB**. Với nhiều custom series general-purpose, RAM được chọn theo bước **256 MB** trong biểu diễn tên machine type.

**Quy đổi khi dùng CLI:** trong tài liệu Compute Engine, tên machine type sử dụng đơn vị `MB`/`GB` lịch sử nhưng với các ví dụ thông dụng **1 GB = 1.024 MB**; ví dụ `12 GiB = 12.288 MB`. Không lấy 12 GB thập phân = 12.000 MB để điền vào chuỗi custom và mong hợp lệ.

### 5.3. Extended memory

Khi ứng dụng cần RAM vượt tỷ lệ mặc định tối đa của series, một số loại custom có tùy chọn **extended memory**.

Ví dụ:

~~~text
n2-custom-2-20480-ext
│  │      │  │     └── mở rộng RAM theo giới hạn series
│  │      │  └──────── 20 GiB (20.480 MB)
│  │      └─────────── 2 vCPU
│  └────────────────── custom
└───────────────────── N2
~~~

Nếu giới hạn RAM mặc định `8 GiB/vCPU`, hai vCPU có trần chuẩn `16 GiB`; 20 GiB vượt trần nên cần đuôi `-ext`. Extended memory có **đơn giá/phụ phí** và các quy tắc giảm giá riêng. Nhiều predefined types, E2 custom và G2 custom **không** hỗ trợ extended memory.

Đối với ứng dụng bị ràng buộc **bản quyền theo số vCPU** (chẳng hạn một số bản quyền thương mại), extended memory có thể hữu ích nếu cho phép giữ ít vCPU trong khi tăng RAM; nhưng phải tính đầy đủ license, phụ phí RAM và performance.

### 5.4. Custom không cho phép cấu hình mọi thứ tùy ý

Custom machine type **chỉ giải quyết một số thông số phần cứng được cho phép**. Nó không đồng nghĩa bạn có thể tự chọn bất cứ:

- CPU vendor/model/ISA nào, bất kể series.
- Số GPU bất kỳ hoặc dung lượng VRAM tùy ý.
- Dung lượng Local SSD và interface mạng bất kỳ.
- Loại disk, networking queue hoặc throughput vượt các giới hạn của machine series.
- Region/zone không có phần cứng tương ứng.
- Bất kỳ tổ hợp OS image, architecture và CPU platform nào.

Thậm chí một custom type hợp lệ về vCPU và RAM vẫn có thể **không tạo được VM** vì quota, capacity, organization policy, image không tương thích hoặc cấu hình disk/GPU.

## 6. Quy trình chọn machine type dựa trên tải thật

### 6.1. Đặt câu hỏi trước khi chọn SKU

1. **Workload là gì?** API Java, batch, database, cache, render GPU hay hệ thống HPC?
2. **Ràng buộc cứng nào?** CPU architecture, kernel/driver, license, GPU/Local SSD, memory footprint, p99 latency?
3. **Tải trung bình và đỉnh?** CPU, RAM, QPS, request concurrency, disk IOPS, throughput, network throughput?
4. **Có thể mở rộng ngang?** Nhiều VM với MIG, load balancer và autoscaling hay cần một máy lớn?
5. **Ràng buộc vận hành?** Zone, backup, SLO, RTO/RPO, failover, maintenance?
6. **Mức chi phí chấp nhận được?** On-demand, commitments, Spot cho batch, chi phí đĩa/mạng/license?

### 6.2. Bảng chọn ứng viên

| Workload giả định | Đặc tính quan trọng | Bước chọn ban đầu | Cần xác minh |
|---|---|---|---|
| REST API Java thông thường | CPU/RAM cân bằng, stateless | E2/N2/N4 predefined | p95/p99 latency, heap/GC, Cloud SQL connection pool |
| Worker Java heap lớn | 4 vCPU đủ nhưng thiếu RAM | Highmem hoặc custom N/E phù hợp | OOM, GC pauses, RAM sử dụng thực tế |
| Data processing CPU-bound | CPU liên tục cao, RAM vừa | Compute-optimized hoặc general-purpose thế hệ mới | Throughput trên mỗi đơn vị giá |
| Cache in-memory | RAM rất lớn, độ trễ thấp | Memory-optimized hoặc custom extended memory | Mức tiêu thụ RAM, HA, data durability |
| Batch không quan trọng thời gian hoàn tất tuyệt đối | Có thể checkpoint/retry | Series phổ thông + Spot VM | Preemption, tính idempotent, mất local data |
| ML inference | Cần GPU/VRAM theo model | G/A accelerator series hoặc Vertex AI | VRAM, GPU utilization, thời gian cold start |
| Database cần IOPS lớn | I/O bound, latency cao | Machine series có disk throughput phù hợp | Hyperdisk/PD, replication, IOPS bottleneck |
| Hệ thống x86 cũ | App/driver/license chỉ chạy x86 | Intel/AMD series tương thích | Image, kernel, driver, license |
| Microservice trên container | Có thể dùng serverless | So sánh Cloud Run với VM | Chi phí vận hành, thời gian scale, workload constraints |

**Nhớ:** yêu cầu “chạy Java” không đủ để chọn machine series. Java đa nền tảng nhưng native library, JDK distribution, container image và agent có thể phụ thuộc kiến trúc. Workload Java dùng JNI chỉ build x86_64 sẽ không tự chạy trên Arm.

### 6.3. Đọc metric cho right-sizing

| Metric | Dấu hiệu | Tác động lựa chọn |
|---|---|---|
| CPU utilization trung bình và p95 | CPU cao kéo dài, queue dài | Tăng CPU, đổi series có CPU tốt hơn hoặc scale ngang |
| Memory used, page faults, swap, OOM | RAM thiếu hoặc pressure cao | Tăng RAM, profile highmem/custom, tối ưu heap |
| Disk IOPS/throughput/latency | Đĩa là nút thắt, CPU không cao | Cân nhắc loại disk và giới hạn machine type |
| Network throughput/packet loss | NIC hoặc route làm nghẽn | Chọn series/network tier phù hợp, tối ưu kiến trúc |
| p95/p99 application latency | Người dùng chịu tác động dù CPU trung bình thấp | Xem GC, DB, lock contention, cache, cold start |
| Request/concurrency và peak-hour | Tải đỉnh ngắn nhưng lớn | MIG/autoscaling hoặc dịch vụ managed |
| Uptime và thời gian nhàn rỗi | VM không có workload nhưng vẫn chạy | Lịch tắt dev/test, Spot cho batch hoặc serverless |

**Cloud Monitoring** có sẵn một số metric hạ tầng; các metric RAM, process/JVM, disk chi tiết có thể cần **Ops Agent** hoặc ứng dụng phát metric. Nếu không có số liệu RAM, đừng kết luận VM bị thiếu hoặc dư RAM từ mỗi CPU chart.

### 6.4. Benchmark theo cùng điều kiện

Một phép so sánh có giá trị nên giữ ổn định:

- Mã nguồn, JDK/container version, dataset, request pattern và tỉ lệ read/write.
- Loại database, kích thước pool, latency mạng, image và region.
- Loại disk, disk size và cấu hình IOPS/throughput nếu đánh giá CPU.
- Cách warm-up JVM, thời lượng test và tải đủ lâu để bộc lộ GC/swap.
- SLO cần đạt, ví dụ p95 latency dưới 200 ms ở 500 RPS, không chỉ tổng số request.

So sánh ít nhất **2–3 ứng viên**: predefined nhỏ hơn, predefined đủ tải và custom/series khác. Với CPU architecture khác, rebuild/retest toàn bộ native dependencies.

## 7. Kiểm tra machine types bằng Google Cloud Console

Trong Google Cloud Console, chọn đúng project rồi vào **Compute Engine → VM instances → Create instance**.

### 7.1. Các bước chọn cấu hình

1. Xác nhận **project ID**, **region** và **zone**.
2. Trong **Machine configuration**, chọn family và series theo workload.
3. Chọn **machine type** định sẵn hoặc `Custom` nếu series hỗ trợ.
4. Với custom, nhập số vCPU và RAM; Console thường hiển thị giới hạn và ước tính giá.
5. Kiểm tra loại kiến trúc x86/Arm, image OS, disk và network settings.
6. Chọn **service account** được phân quyền tối thiểu, cấu hình access scopes/Identity theo cơ chế phù hợp.
7. Chọn subnet, internal/external IP và firewall ingress theo đúng chính sách môi trường.
8. Xem **estimated cost**, quota/capacity và cấu hình billing.
9. Với sandbox, chỉ tạo VM nếu đã có quyền và dự toán phù hợp; kiểm tra và xóa tài nguyên sau khi thực hành.

**Không mặc định bật external IP hoặc mở SSH/HTTP ra Internet** chỉ để thử một machine type. Có thể dùng VM không có external IP, IAP/OS Login và Cloud NAT khi phù hợp. Cần nhớ VM, disks, IP và logs có thể có chi phí dù chỉ chạy thử.

## 8. Dùng Google Cloud CLI để khám phá cấu hình

Những lệnh dưới đây **chỉ đọc** và có thể chạy trong Cloud Shell hoặc môi trường đã cấu hình `gcloud`:

~~~bash
# Xác minh danh tính và project mặc định.
gcloud auth list
gcloud config get-value project

# Xem các machine types thực tế tại zone được phép.
gcloud compute machine-types list \
  --project=PROJECT_ID \
  --zones=asia-southeast1-a

# Quan sát một machine type định sẵn.
gcloud compute machine-types describe e2-standard-4 \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --format="yaml(name,guestCpus,memoryMb,description)"

# Xem VM đã có và machine type đang dùng.
gcloud compute instances list \
  --project=PROJECT_ID \
  --format="table(name,zone,machineType,status)"
~~~

Thay `PROJECT_ID` bằng project sandbox đã được phép. `asia-southeast1-a` là zone minh họa; **đừng suy mọi series có đủ capacity tại zone này**. Nếu tên không xuất hiện trong danh sách, kiểm tra zone/series/permission, và dùng tài liệu hoặc bảng so sánh machine family khi cần.

### 8.1. Diễn giải kết quả `describe`

Giả sử output có:

~~~yaml
name: e2-standard-4
guestCpus: 4
memoryMb: 16384
~~~

Đây là ví dụ về cách đọc **4 vCPU và 16.384 MB (16 GiB)**, không phải bảo đảm mọi machine type `standard-4` luôn có 16 GiB. Từ CLI cũng có thể đọc các thuộc tính khác về memory, architecture và cấu hình của series nếu API trình bày chúng.

## 9. Tạo VM predefined và custom trong sandbox

**Các lệnh phần này thay đổi tài nguyên cloud và có thể phát sinh phí.** Chúng phục vụ minh họa và chỉ nên chạy trên project được cấp quyền. Để chạy thực tế cần Compute Engine API bật, billing hợp lệ, quyền IAM cần thiết, quota/capacity tại zone, VPC/subnet và image thích hợp.

### 9.1. Ví dụ tạo predefined type

~~~bash
gcloud compute instances create lab-predefined \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --machine-type=e2-standard-4 \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=30GB \
  --subnet=SUBNET_NAME \
  --no-address
~~~

`--no-address` minh họa VM **không có external IPv4**. Quyền quản trị VM vẫn cần IAM và đường truy cập an toàn (ví dụ IAP/OS Login theo cấu hình); một VM không có public IP có thể không cài được package từ Internet nếu chưa có outbound phù hợp.

### 9.2. Ví dụ tạo custom E2: 4 vCPU, 12 GiB RAM

~~~bash
gcloud compute instances create lab-custom \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --machine-type=e2-custom-4-12288 \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=30GB \
  --subnet=SUBNET_NAME \
  --no-address
~~~

Định dạng:

~~~text
e2-custom-<NUMBER_OF_VCPUS>-<MEMORY_MB>
~~~

Giá trị `12288` là 12 × 1024 MB; tỉ lệ 3 GiB RAM/vCPU nằm trong giới hạn E2 custom tiêu biểu. Nếu đổi thành một tỉ lệ ngoài giới hạn, API từ chối trước khi VM chạy.

### 9.3. Dạng cờ `--custom-cpu` / `--custom-memory`

Cùng ý tưởng có thể mô tả bằng:

~~~bash
gcloud compute instances create lab-custom-alt \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --custom-cpu=4 \
  --custom-memory=12GB \
  --custom-vm-type=e2 \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --subnet=SUBNET_NAME \
  --no-address
~~~

Theo quy ước của Compute Engine, `12GB` trong ngữ cảnh custom CLI tương ứng khoảng 12 GiB. **Không** dùng đồng thời cờ `--machine-type` và tập custom flags cho cùng một VM mà chưa kiểm tra quy tắc của CLI.

### 9.4. Ví dụ extended memory N2

~~~bash
# Ví dụ nêu cách diễn đạt, chỉ chạy khi zone/capacity cho phép.
gcloud compute instances create lab-extmem \
  --project=PROJECT_ID \
  --zone=ZONE \
  --machine-type=n2-custom-2-20480-ext \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --subnet=SUBNET_NAME \
  --no-address
~~~

Hai vCPU N2 cùng 20 GiB RAM là ví dụ có **extended memory**. Phần RAM vượt tỷ lệ chuẩn có cơ chế tính giá và chiết khấu riêng; xác minh cấu hình giá trước khi chạy.

### 9.5. Đọc lại instance

~~~bash
gcloud compute instances describe lab-custom \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --format="yaml(name,machineType,status,disks,networkInterfaces)"
~~~

Khi làm lab có tài nguyên thật, thu hồi VM và kiểm tra **disk, static IP, snapshot, reservation** còn tồn tại nếu không còn cần. Xóa VM không tự đảm bảo mọi tài nguyên liên quan đã được xóa hoặc ngừng tính phí.

## 10. Đổi machine type của VM hiện có

### 10.1. Đổi cấu hình không phải thao tác live resize mặc định

Đối với nhiều VM thường, bạn phải **dừng VM đến trạng thái `TERMINATED`**, thay machine type rồi khởi động lại. Cần bảo đảm có **maintenance window**, backup/snapshot phù hợp và kế hoạch rollback.

~~~mermaid
flowchart LR
    A["Đo và quyết định resize"] --> B["Kiểm tra support, quota, capacity, disk, snapshot"]
    B --> C["Dừng VM (TERMINATED)"]
    C --> D["set-machine-type"]
    D --> E["Khởi động VM"]
    E --> F["Smoke test + benchmark"]
    F --> G{"Đạt SLO?"}
    G -->|Có| H["Theo dõi, cập nhật tài liệu và chi phí"]
    G -->|Không| I["Rollback hoặc chuyển workload theo phương án đã duyệt"]
~~~

Lệnh minh họa:

~~~bash
# 1. Thao tác có tác động: dừng VM.
gcloud compute instances stop VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE

# 2. Chỉ khi VM đã dừng và phép chuyển được hỗ trợ.
gcloud compute instances set-machine-type VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE \
  --machine-type=e2-custom-4-12288

# 3. Khởi động và kiểm tra.
gcloud compute instances start VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE
~~~

**Không dùng lệnh trên trực tiếp cho production trước khi đánh giá ràng buộc.** Một số cấu hình **không hỗ trợ quy trình đổi in-place**, ví dụ có Local SSD, VM thuộc MIG, bare metal, đổi giữa các generation/một số kiến trúc, accelerator-specific hoặc có thay đổi network interface; khi đó có thể cần **tạo VM mới/migrate workload**. Google Cloud có hướng dẫn riêng cho trường hợp thay generation, chuyển kiến trúc CPU và điều chỉnh GPU.

### 10.2. Các bẫy khi resize

| Thay đổi / trạng thái | Rủi ro | Biện pháp |
|---|---|---|
| Dừng VM đang xử lý đơn hàng | Downtime nếu không có bản sao dự phòng | Thiết kế MIG/load balancer hoặc bảo trì có kế hoạch |
| Machine type mới thiếu capacity tại zone | VM có thể không khởi động lại như mong muốn | Kiểm tra zone, quota, reservation và phương án rollback |
| Dùng **ephemeral external IP** | IP có thể thay khi dừng/khởi động | Nếu cần IP cố định, reserve static IP và cập nhật DNS/cấu hình |
| Có **Local SSD** | Rủi ro dữ liệu và thường không hỗ trợ đổi trực tiếp | Backup/migrate theo hướng dẫn riêng |
| VM trong **Managed Instance Group** | MIG có thể tự tạo lại VM, ghi đè thay đổi | Sửa **instance template** và rolling update theo MIG |
| Đổi x86 ↔ Arm | Image, binary, agent, driver có thể không chạy | Build/test và migrate sang VM mới nếu cần |
| Chuyển thế hệ không hỗ trợ in-place | `set-machine-type` thất bại hoặc không khả dụng | Move workload to a new VM theo tài liệu |
| Đổi RAM/vCPU thiếu cân bằng | OOM, GC, throttling, throughput xấu đi | Benchmark trước và theo dõi sau |
| Dừng VM để giảm chi phí | Disk, IP/reservation và tài nguyên phụ còn tính phí | Kiểm tra Billing theo từng SKU |

**Persistent Disk/Hyperdisk** giữ dữ liệu qua nhiều thao tác dừng VM thông thường, nhưng không thay cho backup/snapshot. Đừng chỉ dựa vào khả năng tái khởi động khi cần phục hồi sau xóa nhầm dữ liệu hoặc lỗi ứng dụng.

## 11. Quota, capacity, region/zone và tương thích

### 11.1. Quota không phải capacity

- **Quota:** giới hạn tài nguyên mà project/region được phép sử dụng. Có thể yêu cầu điều chỉnh khi doanh nghiệp có nhu cầu hợp lệ.
- **Capacity:** phần cứng **thực sự còn khả dụng** tại zone vào thời điểm tạo/khởi động VM. Quota còn dư **không đảm bảo** đủ capacity.
- **Availability:** một machine series có thể hỗ trợ ở region nhưng không phải mọi zone/loại cấu hình.
- **Reservation:** công cụ dự trữ năng lực cho cấu hình phù hợp khi được hỗ trợ; có chi phí, ràng buộc và quy tắc tiêu thụ riêng.

Ví dụ dự kiến triển khai 30 VM cấu hình lớn vào một zone: ngay cả khi quota 100 vCPU còn dư, yêu cầu vẫn có thể lỗi do thiếu capacity. Với workload mission-critical, cần phân phối theo zone, kiểm tra reservation và kế hoạch khôi phục.

### 11.2. Kiến trúc CPU và software ecosystem

| Yêu cầu | Cách xác minh |
|---|---|
| OS image | Có image tương thích series/ISA và driver chưa? |
| Container image | Có image `linux/amd64` hoặc `linux/arm64` tương ứng? |
| JDK/JVM | JDK distribution và native components hỗ trợ kiến trúc mục tiêu? |
| JNI/native library | Có build được với architecture tương ứng không? |
| Monitoring/security agent | Ops Agent, EDR, backup agent và plugin có hỗ trợ? |
| License | Tính theo vCPU/socket/architecture ra sao? |
| Network/disk | Throughput và giới hạn hỗ trợ cho machine series cụ thể? |

**Không chuyển từ N2 x86 sang N4A Arm chỉ bằng việc đổi tên machine type** nếu ứng dụng chưa được kiểm thử. Khi khác architecture, thường cần tạo image mới, pipeline build cho ISA mới và migration theo tài liệu.

### 11.3. Không lẫn machine type với tài nguyên khác

Một VM còn phụ thuộc vào:

- **Boot disk** và data disks: Persistent Disk/Hyperdisk/Local SSD với đặc tính khác nhau.
- **VPC network, subnet, internal/external IP, firewall, routes, Cloud NAT:** quyết định kết nối.
- **Service account, IAM, OS Login, Shielded VM, Secure Boot** theo hỗ trợ: quyết định danh tính và tư thế bảo mật.
- **Managed instance group (MIG), load balancer, health checks:** mở rộng và độ tin cậy.
- **Cloud Monitoring/Logging/Ops Agent:** quan sát tài nguyên và ứng dụng.

Chọn machine type đúng nhưng thiếu route ra database, IAM hoặc firewall vẫn khiến hệ thống thất bại.

## 12. Chi phí: tối ưu theo kết quả và tổng chi phí sở hữu

### 12.1. Các nguồn chi phí Compute Engine

| Thành phần | Giá hình thành từ đâu? | Lưu ý |
|---|---|---|
| VM predefined | Machine series/type, thời gian sử dụng và mô hình provisioning | Giá thay đổi theo zone/region và license |
| VM custom | vCPU và RAM theo cấu hình custom và thời gian sử dụng | Có **custom premium**, kiểm tra giá hiện hành |
| Extended memory | RAM vượt tỷ lệ chuẩn của series | Có phụ phí, quy tắc giảm giá riêng |
| Disk / snapshots | Loại, dung lượng, IOPS/throughput theo sản phẩm | Có thể tính phí khi VM dừng |
| Network / IP / Load Balancer | Egress, external IP, NAT, LB theo cấu hình | Không nằm hết trong giá vCPU |
| License | OS và phần mềm thương mại | Cần xét theo vCPU/VM/architecture |
| Logging, monitoring, backup | Dữ liệu ingest/retention, snapshot và vận hành | Đặt budget và cảnh báo phù hợp |
| Vận hành/độ tin cậy | Công sức patch, HA, backup, sự cố | Giá thấp không đồng nghĩa TCO thấp |

Theo tài liệu cấu hình custom hiện hành, custom machine types có **phụ phí on-demand** so với loại predefined tương đương; **đừng giả định custom luôn rẻ hơn** chỉ vì RAM ít hơn. Giá chính xác và chiết khấu có thể thay đổi; dùng **Google Cloud Pricing Calculator** và báo giá theo khu vực/kỳ sử dụng.

### 12.2. SUD, CUD và Spot

- **Sustained use discounts (SUD):** tự động áp dụng cho **những series/tài nguyên đủ điều kiện**, không phải mọi máy ảo thế hệ mới hoặc mọi GPU.
- **Committed use discounts (CUD):** cam kết sử dụng tài nguyên/chi tiêu theo loại chương trình trong thời hạn quy định; khả năng bao phủ series/custom/extended memory khác nhau.
- **Spot VM:** tiết kiệm đáng kể cho workload chịu được việc VM bị thu hồi bất cứ lúc nào; nên có retry, checkpoint, queue và khả năng phục hồi.
- **Reservations:** để xử lý rủi ro capacity cho cấu hình quan trọng, có cơ chế tính chi phí riêng; không nhầm với cam kết chiết khấu.
- **Scheduling:** dev/test có thể dừng khi không dùng, nhưng tiếp tục trả phí disk/IP và các tài nguyên liên quan.

**Không cộng tùy tiện mọi loại giảm giá.** Điều kiện áp dụng, loại SKU, commitment và mô hình provisioning có thể loại trừ lẫn nhau.

### 12.3. Ví dụ so sánh chi phí không dùng đơn giá giả

Giả sử một API Java đang chạy trên `e2-highmem-4` nhưng thực tế chỉ cần 12 GiB RAM. Hai lựa chọn:

| Phương án | Giả định | Điểm phải đo |
|---|---|---|
| Giữ predefined highmem | Không phải điều chỉnh máy, dung lượng RAM dư | TCO hiện tại, p95 latency, quyền lợi giảm giá |
| Chuyển `e2-custom-4-12288` | Giảm RAM cấp phát, có premium custom | Giá custom thực tế, downtime đổi VM, hiệu năng JVM |
| Chuyển sang series mới | Có thể hiệu quả hiệu năng/giá hơn | Architecture, code compatibility, zone, disk/network và migration |

Công thức đánh giá:

~~~text
Tổng chi phí tháng ≈
  Chi phí VM compute (vCPU/RAM, thời gian, pricing model)
+ Chi phí disk, snapshots và backups
+ Chi phí network egress/NAT/IP/load balancer
+ Chi phí logging/monitoring/license
+ Công vận hành và rủi ro downtime
- Các khoản giảm giá đủ điều kiện được áp dụng thực tế
~~~

So sánh đúng bằng **chi phí trên mỗi 1.000 request đạt SLO**, **chi phí một job thành công**, hoặc **chi phí trên mỗi GB dữ liệu xử lý**, thay vì chỉ nhìn giá mỗi giờ VM.

## 13. Case study: chọn VM cho hệ thống Orders API Java

### 13.1. Bối cảnh

Đội phát triển triển khai API Java trên Compute Engine với Cloud SQL PostgreSQL, ảnh đơn hàng trên Cloud Storage và Pub/Sub cho sự kiện. API chạy stateless sau load balancer, cần **p95 latency dưới 200 ms** ở tải đỉnh được kiểm thử. Hạ tầng được quản lý qua project, IAM, VPC, pipeline và Cloud Monitoring.

Thông số quan sát giả định tại tải thực tế:

| Metric | Kết quả giả định |
|---|---|
| VM hiện tại | `e2-standard-8` |
| CPU trung bình/đỉnh | 20% / 46% |
| RAM sử dụng thường xuyên | 10–11 GiB |
| JVM heap | 8 GiB |
| p95 latency | 150 ms |
| Dữ liệu quan trọng | Cloud SQL và Cloud Storage, không lưu vào local disk |
| Lưu lượng | Đỉnh tăng ~3 lần trong đợt khuyến mãi |

### 13.2. Ứng viên và giả thuyết

- **A: `e2-standard-8`:** giữ cấu hình, ít thay đổi, nhưng CPU đang dư.
- **B: `e2-custom-4-12288`:** thử giảm vCPU xuống 4 và giữ RAM 12 GiB để kiểm tra hiệu quả chi phí.
- **C: `n2-highmem-4` hoặc series mới tương thích:** so sánh latency/throughput và chi phí sau giảm giá.

Không chọn B ngay lập tức: đỉnh CPU trong điều kiện cũ là 46% của **8 vCPU**; giảm còn 4 vCPU có thể khiến CPU gần saturate, thay đổi GC time và p99 latency. Cần **load test**, bao gồm burst, warm-up, phân phối tải trên MIG và lỗi Cloud SQL.

### 13.3. Phương án triển khai an toàn

~~~mermaid
flowchart LR
    U["Người dùng"] --> LB["HTTP(S) Load Balancer"]
    LB --> MIG["Managed Instance Group<br/>Orders API instances"]
    MIG --> SQL["Cloud SQL: PostgreSQL"]
    MIG --> OBJ["Cloud Storage"]
    MIG --> PUB["Pub/Sub"]
    MON["Cloud Monitoring/Logging"] -. "Metric và logs" .-> MIG
    CICD["CI/CD + Instance Template"] --> MIG
~~~

1. Tạo **instance template mới** với candidate machine type.
2. Tạo nhóm thử hoặc canary trong sandbox/nhóm riêng có cùng cấu hình ứng dụng.
3. Chạy benchmark CPU, heap/GC, Cloud SQL connections, p95/p99, failover và network throughput.
4. Nếu kết quả đạt, **rolling update** MIG theo chính sách an toàn; không sửa tay từng VM trong MIG.
5. Theo dõi lỗi, timeouts, độ trễ và chi phí theo SKU ít nhất qua chu kỳ tải đại diện.
6. Nếu SLO xấu hơn hoặc capacity không đủ, rollback về template đã xác minh.

Đối với hệ thống có thể triển khai theo container, cũng nên **so sánh Cloud Run hoặc GKE** ở cấp kiến trúc, nhưng đổi nền tảng là quyết định riêng cần đánh giá tính năng, công vận hành, bảo mật và tổng chi phí.

## 14. Sự cố phổ biến khi chọn hoặc đổi machine type

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `Invalid machine type` | Sai tên series, số vCPU hoặc RAM step/ratio | Đối chiếu docs custom và CLI `machine-types list` |
| Không thấy series ở zone | Chưa hỗ trợ hoặc không sẵn tại zone | So danh mục zone khác và yêu cầu kiến trúc |
| `ZONE_RESOURCE_POOL_EXHAUSTED` hoặc lỗi capacity | Thiếu phần cứng có sẵn | Thử zone/type khác, reservation, thay kế hoạch triển khai |
| Quota exceeded | Project/region không đủ quota | Kiểm tra quotas, điều chỉnh theo quy trình |
| VM không chạy sau đổi type | Loại mới thiếu capacity hoặc image/driver không tương thích | Rollback type cũ, kiểm tra logs và phương án migrate |
| Type mới `-ext` không hợp lệ | Series không hỗ trợ extended memory hoặc vượt giới hạn | Dùng N-series hỗ trợ, chọn tỷ lệ hợp lệ |
| Java API chậm dù CPU thấp | DB, GC, IO, network, lock hoặc concurrency bottleneck | Xem application tracing, heap, Cloud SQL |
| Dùng Arm rồi container không khởi động | Image/native dependency x86 | Build multi-arch/arm64 và kiểm thử |
| Đổi máy trong MIG nhưng cấu hình trở lại | MIG quản lý instance qua template | Sửa template và rolling update |
| Đĩa nhanh nhưng IOPS thấp | Machine type giới hạn throughput/IOPS | Kiểm tra cả machine/disk limits |
| VM dừng mà billing vẫn phát sinh | Persistent disks, static IP, snapshots, reservation | Kiểm tra Billing theo SKU |
| Chọn Spot cho API thiết yếu | VM bị preempt bất ngờ | Dùng standard VMs/HA phù hợp hoặc chỉ Spot cho workload chịu lỗi |
| Trông đợi mở rộng dọc tự động | Thay vCPU/RAM thường cần stop hoặc thay template | Thiết kế horizontal scaling/MIG nếu cần |

## 15. Bài tập thực hành và câu hỏi tự đánh giá

### 15.1. Bài tập A — Đọc machine type

Một công ty có ba cấu hình:

~~~text
A: e2-standard-4
B: n2-highmem-8
C: e2-custom-4-12288
~~~

Hãy xác định:

1. Cấu hình nào là predefined, cấu hình nào là custom?
2. C có bao nhiêu vCPU và GiB RAM?
3. Vì sao không thể suy số RAM chính xác của B chỉ bằng phép nhân theo tỷ lệ E2?
4. A và C có chắc cùng hiệu năng khi chạy chung một phiên bản JDK không? Giải thích.
5. Những metric nào cần lấy trước khi chọn C làm máy production?

**Gợi ý:** A/B predefined, C custom; C có 4 vCPU và 12 GiB. Tỷ lệ highmem và nền tảng CPU phụ thuộc series; so workload và metric thay vì suy theo tên.

### 15.2. Bài tập B — Chọn type cho workload khác nhau

| Hệ thống | Tình huống | Hãy đề xuất |
|---|---|---|
| Web API | CPU vừa, RAM 12 GiB, có thể scale ngang | Predefined nào? Custom nào? Vì sao? |
| Batch video | Có thể retry và không yêu cầu hoàn tất ngay | Series nào, Spot có hợp không? |
| Cache in-memory | RAM rất lớn, CPU vừa | Highmem/custom-ext/memory family đánh đổi ra sao? |
| AI inference | Model cần GPU/VRAM theo yêu cầu | Vì sao chọn A/G hoặc Vertex AI thay vì E2? |
| Java legacy | Chứa thư viện JNI x86_64 | Có chọn Arm ngay được không? |
| SQL-heavy API | CPU thấp, p99 cao do DB query | Có nên tăng vCPU trước khi tối ưu query không? |

Trình bày **giả định**, cách đo và yếu tố làm phương án thay đổi. Không có đáp án cố định chỉ dựa trên một tên series.

### 15.3. Bài tập C — Chọn custom hợp lệ

Đánh giá các chuỗi machine type giả định:

1. `e2-custom-4-12288`
2. `e2-custom-3-12288`
3. `n2-custom-2-20480`
4. `n2-custom-2-20480-ext`
5. `n4-custom-4-16384`

**Gợi ý đối chiếu theo tài liệu hiện hành:**

- **(1)** Hợp lệ theo giới hạn custom E2 thông dụng.
- **(2)** Không hợp lệ: E2 custom yêu cầu số vCPU chẵn theo giới hạn hiện hành.
- **(3)** Không hợp lệ ở RAM chuẩn vì 20 GiB trên 2 vCPU vượt ngưỡng 8 GiB/vCPU.
- **(4)** Hợp lệ theo thiết kế extended memory N2, với điều kiện các giới hạn khác và zone/capacity phù hợp.
- **(5)** Hợp lệ về tỷ lệ 4 vCPU/16 GiB RAM của N4, vẫn cần kiểm tra khả dụng theo zone và hỗ trợ thời điểm tạo.

### 15.4. Bài tập D — Quy trình đổi type của một VM production

Một VM xử lý đơn hàng đang dùng `e2-standard-8`, có Persistent Disk, external IPv4 cấp tạm và được điều khiển bằng MIG. Đội muốn đổi sang `e2-custom-4-12288` để giảm chi phí.

Hãy trả lời:

1. Tại sao không nên gọi `gcloud compute instances set-machine-type` lên VM trong MIG?
2. Thao tác nào phải chuẩn bị để đổi instance template và rolling update?
3. Có rủi ro gì với ephemeral external IP?
4. Cần kiểm tra gì trước khi giảm vCPU một nửa?
5. Nếu type mới không đủ capacity, rollback nên được chuẩn bị như thế nào?
6. Sau khi rollout, cần theo dõi các metric nào để kết luận thực sự tiết kiệm?

**Gợi ý:** Cập nhật template/MIG theo chiến lược rolling, có khả năng rollback, đừng sửa tay VM do MIG quản lý. Xác minh SLO bằng tải thực; external IP của instance không phải thiết kế ổn định cho hệ thống đặt sau load balancer.

## 16. Checklist khi chọn machine type cho production

- [ ] Đã phân biệt machine family, series, type và instance.
- [ ] Đã nhận diện workload CPU-bound, memory-bound, IO-bound, GPU-bound hay chờ mạng/DB.
- [ ] Đã đo CPU, RAM, disk, network, p95/p99 latency và tải đỉnh đại diện.
- [ ] Đã kiểm tra architecture x86/Arm, OS image, JDK, native libraries, agents và bản quyền.
- [ ] Đã tra machine series **có tại zone** và dự kiến quota/capacity.
- [ ] Với custom, đã kiểm tra **vCPU step, RAM ratio, memory increment, extended memory** và giá.
- [ ] Đã kiểm tra giới hạn throughput/IOPS giữa machine type và Persistent Disk/Hyperdisk/Local SSD.
- [ ] Đã so sánh 2–3 candidate bằng benchmark và chi phí **trên đơn vị công việc đạt SLO**.
- [ ] Đã phân biệt predefined/custom với Spot, SUD, CUD và reservation.
- [ ] Đã bảo vệ VM bằng IAM, service account tối thiểu, VPC/firewall, OS hardening và patching.
- [ ] Đã có backup/snapshot, health checks, rollback, kế hoạch migration hoặc MIG rolling update.
- [ ] Đã giám sát Billing, logging, network egress, disks và tài nguyên còn tính phí khi VM dừng.
- [ ] Đã chọn cách triển khai đáp ứng độ tin cậy, chi phí và năng lực vận hành của đội.

## 17. Tài liệu chính thức và nguồn kiểm chứng

Danh mục series, tỷ lệ tài nguyên, giá và khả năng đổi type thay đổi theo thế hệ. Hãy xem tài liệu Google Cloud hiện hành trước khi chọn VM thật:

- [Machine families resource and comparison guide](https://docs.cloud.google.com/compute/docs/machine-resource)
- [General-purpose machine family](https://docs.cloud.google.com/compute/docs/general-purpose-machines)
- [Compute-optimized machine family](https://docs.cloud.google.com/compute/docs/compute-optimized-machines)
- [Memory-optimized machine family](https://docs.cloud.google.com/compute/docs/memory-optimized-machines)
- [Accelerator-optimized machine family](https://docs.cloud.google.com/compute/docs/accelerator-optimized-machines)
- [Create a VM with a custom machine type](https://docs.cloud.google.com/compute/docs/instances/creating-instance-with-custom-machine-type)
- [Edit the machine type of a compute instance](https://docs.cloud.google.com/compute/docs/instances/changing-machine-type-of-stopped-instance)
- [Troubleshoot resource availability errors](https://docs.cloud.google.com/compute/docs/troubleshooting/troubleshooting-resource-availability)
- [Spot VMs](https://docs.cloud.google.com/compute/docs/instances/spot)
- [Sustained use discounts](https://docs.cloud.google.com/compute/docs/sustained-use-discounts)
- [Compute Engine instance pricing](https://cloud.google.com/compute/vm-instance-pricing)
- [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator)

**Điểm cần nhớ:** Hãy bắt đầu từ **workload thực và SLO**, chọn **family** theo nút thắt, chọn **series** theo kiến trúc/khả năng hỗ trợ, rồi chọn **predefined hoặc custom machine type** để cân bằng vCPU–RAM–IO với chi phí. Một custom type hợp lệ không mặc nhiên rẻ hoặc nhanh hơn. Quyết định tốt chỉ được xác nhận khi **benchmark, quota/capacity, khả năng vận hành, bảo mật và chi phí toàn hệ thống** đều đáp ứng yêu cầu.

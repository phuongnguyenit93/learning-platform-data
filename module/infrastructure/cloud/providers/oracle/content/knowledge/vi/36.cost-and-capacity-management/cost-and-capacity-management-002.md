# OCPU, vCPU và so sánh đơn vị tính giá giữa các dịch vụ

Trong chương **Chi phí và quản lý năng lực** của Oracle Cloud Infrastructure (OCI), hiểu đơn vị tính giá là bước nối giữa cấu hình kỹ thuật và ngân sách. Một ứng dụng chạy trên Compute, một cơ sở dữ liệu Oracle được quản lý và một hàm xử lý sự kiện có thể cùng dùng CPU, nhưng hóa đơn của chúng được đo bằng những đại lượng khác nhau.

Bài học này thuộc phạm vi **CLOUD_PROVIDERS_ORACLE**. Tình huống xuyên suốt là một nhóm triển khai ứng dụng trên OCI, cần chọn tài nguyên cho ứng dụng và cơ sở dữ liệu, đồng thời duy trì hiệu năng, tính sẵn sàng và khả năng đối chiếu chi phí theo compartment. Các khái niệm tenancy, IAM và VCN chỉ đóng vai trò bối cảnh; trọng tâm ở đây là đọc đúng cấu hình, đơn vị đo và phạm vi giá.

Sau bài học, bạn có thể:

- Phân biệt OCPU, vCPU, ECPU và lượng sử dụng tích lũy theo thời gian.
- Quy đổi số CPU theo đúng dòng shape thay vì áp dụng một tỷ lệ cho toàn bộ OCI.
- Lập phép tính cho Compute Flex, cơ sở dữ liệu, Functions và các tài nguyên đi kèm.
- So sánh các phương án theo tổng chi phí để đáp ứng cùng yêu cầu công việc.

> Các quy tắc sản phẩm trong bài được đối chiếu với tài liệu Oracle ngày **21/11/2026**. Tất cả đơn giá số trong ví dụ là **giá giả định để học cách tính**, tính bằng USD, chưa xét thuế, chiết khấu hay hạn mức miễn phí. Khi lập dự toán thật, lấy đúng SKU, mô hình triển khai và điều kiện thương mại đang áp dụng.

## 1. Phân biệt số CPU và đơn vị thanh toán

### 1.1. Core, luồng và vCPU

Một lõi vật lý thực hiện các chỉ thị của chương trình. Với cơ chế đa luồng đồng thời như SMT, một lõi có thể cung cấp nhiều luồng thực thi phần cứng. Hệ điều hành hoặc máy ảo nhìn thấy các bộ xử lý logic tương ứng với cấu hình được cấp.

**vCPU** là đơn vị CPU ảo. Trong các dòng Compute OCI được xét ở bảng dưới, nó gắn với luồng thực thi hoặc lõi theo thiết kế bộ xử lý. Số vCPU giúp mô tả cấu hình, nhưng chưa mô tả đầy đủ năng lực: thế hệ CPU, tốc độ xử lý từng lõi, cache, RAM và giới hạn I/O đều ảnh hưởng kết quả.

Hai luồng trên một lõi chia sẻ tài nguyên của lõi đó. Vì vậy, tăng số luồng hiển thị không có nghĩa hiệu năng ứng dụng tăng tuyến tính.

### 1.2. OCPU phải được đọc theo dòng shape

**OCPU**, viết tắt của Oracle CPU, là đơn vị cấp phát và tính giá CPU được nhiều dịch vụ OCI sử dụng. Theo [tài liệu Compute Shapes](https://docs.oracle.com/en-us/iaas/Content/Compute/References/computeshapes.htm), quy tắc của các dòng Compute sau là:

| Dòng Compute | Tài nguyên tương ứng với 1 OCPU | Số vCPU tương ứng |
| --- | --- | ---: |
| x86 dùng AMD hoặc Intel | 1 lõi vật lý với 2 luồng | 2 |
| Arm Ampere A1 | 1 lõi Arm | 1 |
| Arm Ampere A2, A4 | 2 lõi Arm | 2 |

Do đó, câu “1 OCPU luôn bằng 2 vCPU” thiếu phạm vi áp dụng. Câu “mọi shape Arm đều có 1 OCPU bằng 1 vCPU” cũng sai. Khi gặp một shape mới, hãy xem định nghĩa của chính dòng đó.

Ví dụ quy đổi **số lượng CPU**, chưa phải quy đổi hiệu năng:

```text
VM x86:  2 OCPU × 2 = 4 vCPU
VM A1:   4 OCPU × 1 = 4 vCPU
VM A2:   2 OCPU × 2 = 4 vCPU
```

Cả ba cấu hình có cùng số vCPU theo các quy tắc trên. Chúng vẫn cần được đo với cùng tải ứng dụng trước khi kết luận về năng lực phục vụ.

### 1.3. ECPU là một mô hình đo riêng

Trong Autonomous Database, **ECPU** là thước đo tài nguyên tính toán được trừu tượng hóa từ nhóm máy chủ compute và storage. Nó không xác định trực tiếp một số lõi vật lý cố định. Tài liệu hiện hành dùng ECPU cho việc tạo hoặc clone Autonomous Database mới; OCPU là metric cũ còn có thể xuất hiện ở hệ thống hiện hữu. Xem [Compute Models in Autonomous AI Database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-compute-models.html).

Không suy luận rằng tên cùng có chữ “CPU” thì số lượng của chúng có thể thay thế trực tiếp:

```text
4 vCPU Compute ≠ mặc nhiên 4 ECPU Database
2 OCPU Compute ≠ mặc nhiên cùng chi phí với 2 OCPU Database
```

Một số tài liệu chuyển đổi Autonomous Database minh họa cấu hình 4 OCPU cũ bằng cấu hình 16 ECPU có mức chi phí gần tương ứng. Đây là cách định cỡ trong bối cảnh chuyển đổi và giá của dịch vụ đó, không phải định luật phần cứng “1 OCPU = 4 ECPU” cho mọi dịch vụ. Xem [Autonomous Database ECPU FAQ](https://www.oracle.com/a/ocom/docs/autonomous-database-ecpu-faq.pdf).

## 2. Đọc một dòng giá bằng ba câu hỏi

Trước khi tính tiền, xác định đủ ba điều:

1. **Mua tài nguyên nào?** Ví dụ CPU của VM, bộ nhớ VM, phần mềm database hoặc dung lượng volume.
2. **Mỗi đơn vị là gì?** Ví dụ OCPU-giờ, GB RAM-giờ, ECPU-giờ hoặc 10.000 request.
3. **Số lượng được đo theo cách nào?** Ví dụ cấu hình được cấp, tài nguyên thực sự tiêu thụ theo cơ chế dịch vụ, dung lượng được cấp phát hay số request đủ điều kiện tính phí.

Một phép tính chỉ hợp lệ khi đơn vị của số lượng và đơn giá khớp nhau:

```text
Chi phí = Lượng sử dụng tính phí × Đơn giá tương ứng

OCPU-giờ × USD / OCPU-giờ = USD
GB-giờ   × USD / GB-giờ   = USD
ECPU-giờ × USD / ECPU-giờ = USD
```

Nếu có nhiều SKU hoặc nhiều khoảng cấu hình, cộng các thành phần:

```text
C_total = Σ (Q_i × P_i)
```

Trong đó `Q_i` là lượng sử dụng của dòng phí `i`, còn `P_i` là đơn giá của chính dòng đó. Công thức cơ bản chưa bao gồm các quy tắc bậc thang, phần miễn phí, cam kết và thuế; những yếu tố đó cần được áp dụng theo từng dòng.

### 2.1. OCPU-giờ không phải số OCPU tại một thời điểm

Một VM có 3 OCPU được tính phí trong 8 giờ tạo ra:

```text
Q_cpu = 3 × 8 = 24 OCPU-giờ
```

Một nhóm ba VM, mỗi VM 1 OCPU chạy 8 giờ cũng tạo ra 24 OCPU-giờ. Tuy cùng đại lượng CPU tích lũy, hai phương án có thể khác RAM, ổ đĩa, băng thông, khả năng phân tải và mức chịu lỗi.

Với nhiều khoảng cấu hình:

```text
Q_cpu = Σ (Số OCPU được tính phí trong khoảng k × Số giờ của khoảng k)
```

Cần phân biệt hai loại số liệu:

| Số liệu | Câu hỏi được trả lời |
| --- | --- |
| Số OCPU hoặc GB RAM cấu hình | Tại thời điểm đó hệ thống được cấp bao nhiêu tài nguyên? |
| OCPU-giờ hoặc GB-giờ | Trong cả kỳ đã tích lũy bao nhiêu tài nguyên tính phí? |
| CPU utilization | Tài nguyên CPU được dùng bận đến mức nào? |
| Request thành công, thời gian hoàn thành | Tài nguyên đã tạo ra kết quả công việc gì? |

Với VM Standard Flex đang chạy, CPU nhàn rỗi không làm phép tính chuyển thành “giá × phần trăm CPU sử dụng”. CPU utilization hữu ích để định cỡ lại, còn CPU và RAM cấu hình là các thành phần của mô hình giá Flex. Xem [Compute FAQ](https://www.oracle.com/cloud/compute/faq/).

### 2.2. Giá so sánh theo vCPU và giá được lập hóa đơn

Oracle có thể hiển thị cả cột **Comparison price (/vCPU)** và **Unit price** để hỗ trợ so sánh. Phải đọc kèm cột **Unit** của dòng hàng; cột so sánh không tạo thêm một khoản phí thứ hai. Xem [OCI Price List](https://www.oracle.com/cloud/price-list/).

Nếu một OCPU của shape đang xét tương ứng `k` vCPU, phần giá CPU chuẩn hóa là:

```text
P_vcpu_comparison = P_ocpu / k

C_cpu = OCPU × giờ × P_ocpu
      = vCPU × giờ × P_vcpu_comparison
```

Ví dụ giả định cho x86:

```text
P_ocpu = 0,04 USD/OCPU-giờ
k      = 2
P_vcpu_comparison = 0,02 USD/vCPU-giờ

2 OCPU × 10 giờ × 0,04 = 0,80 USD
4 vCPU × 10 giờ × 0,02 = 0,80 USD
```

Hai cách tính mô tả cùng phần CPU. Không cộng `0,80 + 0,80`, và không nhân số OCPU với giá theo vCPU.

## 3. Mỗi dịch vụ có một tập đơn vị tính phí

Bảng dưới là bản đồ để đọc dự toán. Một tài nguyên có thể tạo nhiều dòng phí, và mô hình của dịch vụ cụ thể quyết định dòng nào xuất hiện.

| Dịch vụ hoặc thành phần | Đơn vị cần tìm trên bảng giá | Phần cần ghép thêm khi so sánh |
| --- | --- | --- |
| Compute Standard Flex | OCPU-giờ và GB RAM-giờ | Boot volume, block volume, hệ điều hành hoặc phần mềm có phí |
| Base Database Service | OCPU-giờ hoặc ECPU-giờ tùy mô hình | Thành phần hạ tầng/phần mềm của SKU, storage, backup |
| Autonomous Database theo ECPU | ECPU-giờ | Database storage, backup và tính năng được sử dụng |
| OKE | Cluster-giờ nếu thuộc loại có phí; tài nguyên worker | Compute, RAM, storage, load balancer; phí virtual node nếu dùng |
| OCI Functions | Lượt gọi và GB bộ nhớ-giây | Các dịch vụ phụ trợ và tính năng bổ sung nếu bật |
| Block Volume | GB dung lượng-tháng và VPU/GB-tháng | Backup và hiệu năng được cấu hình |
| Object Storage | GB-tháng và đơn vị request | Truy xuất dữ liệu theo storage tier, truyền dữ liệu khi áp dụng |
| Flexible Load Balancer | Load balancer-giờ và Mbps-giờ | Các dòng truyền dữ liệu mạng có liên quan |

Các metric storage, mạng và cluster có thể tra tại [OCI Price List](https://www.oracle.com/cloud/price-list/). Mô hình database, Functions và worker được giải thích riêng trong những phần tiếp theo.

Điểm thực hành là **giá CPU của một dịch vụ không đại diện cho toàn bộ giá của dịch vụ đó**. Muốn so sánh Compute với database được quản lý, phải thống nhất cả những việc cần thực hiện: lưu trữ, backup, vận hành phần mềm, bảo trì và yêu cầu phục hồi.

## 4. Tính chi phí Compute Flex từ CPU và RAM

### 4.1. Công thức cho cấu hình không đổi

Giả sử VM đang xét có hai dòng tính phí CPU và RAM:

```text
C_vm = H × (N_ocpu × P_ocpu + M_gb × P_memory)
```

Trong đó:

- `H`: số giờ VM được tính phí trong kỳ.
- `N_ocpu`: số OCPU đã cấu hình.
- `M_gb`: dung lượng RAM tính bằng GB theo đơn vị của dịch vụ.
- `P_ocpu`: USD/OCPU-giờ.
- `P_memory`: USD/GB-giờ.

Đối với nhiều VM có cùng cấu hình và lịch chạy, nhân kết quả với số VM. Với các VM khác nhau, tính từng VM rồi cộng.

### 4.2. Cùng 4 vCPU, 16 GB RAM

Giả định tháng có 30 ngày, mỗi VM chạy cả tháng:

```text
H = 30 × 24 = 720 giờ
```

Bảng này chỉ xét **CPU và RAM**, dùng hoàn toàn giá giả định:

| Phương án | OCPU | vCPU | RAM | Giá CPU, USD/OCPU-giờ | Giá RAM, USD/GB-giờ |
| --- | ---: | ---: | ---: | ---: | ---: |
| VM x86 | 2 | 4 | 16 GB | 0,040 | 0,0030 |
| VM Arm A1 | 4 | 4 | 16 GB | 0,025 | 0,0025 |
| VM Arm A2 | 2 | 4 | 16 GB | 0,035 | 0,0025 |

Phép tính:

```text
x86:
  CPU + RAM mỗi giờ = 2 × 0,040 + 16 × 0,0030 = 0,128 USD
  720 giờ           = 92,16 USD

Arm A1:
  CPU + RAM mỗi giờ = 4 × 0,025 + 16 × 0,0025 = 0,140 USD
  720 giờ           = 100,80 USD

Arm A2:
  CPU + RAM mỗi giờ = 2 × 0,035 + 16 × 0,0025 = 0,110 USD
  720 giờ           = 79,20 USD
```

Trong bộ số giả định này, A1 có giá mỗi OCPU thấp hơn x86 nhưng tổng CPU và RAM cao hơn. Nguyên nhân là số OCPU cần dùng và phần RAM khác nhau. Kết quả chỉ minh họa cách chuẩn hóa; nó không mô tả giá thương mại hay xếp hạng các dòng CPU thật.

Cũng chưa thể kết luận A2 là lựa chọn phù hợp nhất cho ứng dụng. Cần kiểm tra image Arm, JDK, thư viện native, container image, tác nhân giám sát và tải thực tế. Một cấu hình rẻ theo giờ nhưng không chạy được phần mềm hoặc cần nhiều instance hơn có thể làm phương án mất lợi thế.

### 4.3. Cấu hình thay đổi giữa tháng

Giả sử một VM x86 dùng các mức giá của ví dụ trên:

| Khoảng | OCPU | RAM | Giờ tính phí |
| --- | ---: | ---: | ---: |
| Tải thông thường | 2 | 16 GB | 600 |
| Tải cao | 4 | 32 GB | 120 |

Khi đó:

```text
Q_cpu    = 2 × 600 + 4 × 120   = 1.680 OCPU-giờ
Q_memory = 16 × 600 + 32 × 120 = 13.440 GB-giờ

C_cpu    = 1.680 × 0,040 = 67,20 USD
C_memory = 13.440 × 0,003 = 40,32 USD
C_vm     = 107,52 USD
```

Đây là phép cộng theo thời gian, không phải lấy cấu hình lớn nhất nhân toàn tháng, cũng không phải lấy giá trị trung bình CPU utilization để thay thế số OCPU.

### 4.4. Lịch chạy, trạng thái dừng và các tài nguyên còn tồn tại

Với Standard Compute, thao tác stop đúng qua OCI có thể dừng phí compute, nhưng không tự xóa các volume còn lưu dữ liệu. Quy tắc khi dừng phụ thuộc dòng shape; Dense I/O, GPU, HPC và một số loại khác có ngoại lệ. Chỉ tắt máy từ bên trong hệ điều hành cũng không thay thế thao tác stop qua Console hoặc API. Xem [Resource Billing for Stopped Instances](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/resource-billing-stopped-instances.htm).

Vì thế, trong bảng dự toán cần có lịch riêng:

```text
CPU/RAM của VM lab:     số giờ tính phí theo lịch chạy
Boot/block volume:     thời gian volume còn được giữ lại
Backup:                thời gian và dung lượng được lưu
Load balancer:         thời gian dịch vụ còn tồn tại theo mô hình phí
```

Không dùng một biến “giờ chạy ứng dụng” cho mọi dòng tài nguyên.

## 5. Đọc OCPU và ECPU của dịch vụ cơ sở dữ liệu

### 5.1. Tách đúng sản phẩm và mô hình triển khai

Ba lựa chọn sau có thể cùng phục vụ ứng dụng dùng Oracle Database nhưng khác phạm vi chi phí:

| Lựa chọn | Cần đưa vào phép tính |
| --- | --- |
| Tự cài database trên Compute | VM, RAM, storage, backup, phần mềm được sử dụng và công vận hành |
| Base Database Service | Metric OCPU/ECPU của đúng shape, edition, mô hình license, storage và backup |
| Autonomous Database | Metric ECPU hoặc metric cũ của instance hiện hữu, workload type, storage, backup, tính năng bổ sung |

Do đó, so sánh “2 OCPU VM” với “2 OCPU database” chỉ bằng giá CPU sẽ bỏ sót phạm vi dịch vụ.

### 5.2. Base Database không chỉ có một metric CPU

Bảng giá Base Database hiện có cả mô hình ECPU và OCPU. Với mô hình ECPU trên standard x86, bảng giá liệt kê riêng thành phần **Base Database Compute Infrastructure** và các SKU phần mềm theo edition hoặc BYOL. Vì vậy cần đọc đủ các dòng áp dụng cho cấu hình, thay vì lấy một giá ECPU duy nhất làm tổng. Xem [Base Database Service Pricing](https://www.oracle.com/database/base-database-service/pricing/) và [Service Descriptions của Oracle](https://www.oracle.com/contracts/docs/paas_iaas_universal_credits_3940775.pdf?download=false).

Mẫu tính cho một phương án ECPU có các thành phần riêng:

```text
C_base_db = Q_infrastructure_ecpu_h × P_infrastructure
          + Q_database_ecpu_h × P_selected_edition_or_byol
          + C_database_storage
          + C_backup
          + C_other_applicable_components
```

Không mặc định `Q_infrastructure_ecpu_h` luôn bằng `Q_database_ecpu_h`; điền theo cấu hình và quy tắc đo của dịch vụ. Tương tự, nếu một SKU đã gộp thành phần hạ tầng hoặc phần mềm, không cộng lại thành phần đó lần thứ hai.

**License Included** và **Bring Your Own License (BYOL)** cũng là hai lựa chọn khác nhau. BYOL yêu cầu quyền sử dụng license phù hợp; đây không phải một mã giảm giá có thể chọn cho mọi hệ thống. Bài toán chi phí cần giữ lại thông tin edition và mô hình license cùng với số CPU. Xem [Base Database Service FAQ](https://www.oracle.com/database/base-database-service/faq/).

### 5.3. Autonomous Database: base compute và tài nguyên tăng thêm

Với mô hình ECPU, cần xét cả compute và storage; compute tăng thêm do autoscaling được tính phí, và backup storage là thành phần riêng ngoài database storage. Xem [Autonomous Database Billing Summary](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-database-billing-overview.html).

Một mô hình dự toán theo khoảng thời gian là:

```text
C_autonomous = Σ (ECPU_billable_k × H_k × P_ecpu_k)
             + C_database_storage
             + C_backup_storage
             + C_other_applicable_features
```

Nếu số ECPU tính phí trong một khoảng đã bao gồm phần autoscaling, không cộng phần tăng thêm lần nữa.

Ví dụ chỉ để tính lượng compute, giả sử báo cáo cho biết tổng ECPU tính phí tương đương:

```text
4 ECPU trong 650 giờ
8 ECPU trong 70 giờ

Q_ecpu = 4 × 650 + 8 × 70 = 3.160 ECPU-giờ
```

Bạn lấy `3.160 ECPU-giờ` nhân giá đúng workload và license model, rồi cộng storage, backup và các thành phần áp dụng. Không quy đổi sang vCPU Compute để áp giá VM.

### 5.4. Cùng tên đơn vị chưa đủ để gộp giá

Hai dòng đều ghi ECPU-giờ nhưng thuộc hai sản phẩm khác nhau vẫn có thể khác:

- Thành phần tài nguyên được tính trong SKU.
- Workload type và tính năng có trong dịch vụ.
- Quyền sử dụng phần mềm và mô hình license.
- Cách autoscaling và tài nguyên nền được đo.

Chỉ cộng lượng sử dụng trước khi nhân giá nếu các dòng thực sự dùng cùng đơn giá và điều kiện áp dụng. Trong những trường hợp khác, tính chi phí từng dòng rồi mới cộng tiền.

## 6. OKE và Functions: đơn vị của ứng dụng khác đơn vị của VM

### 6.1. OKE với managed worker nodes

Managed nodes của OKE chạy trên Compute trong tenancy; người dùng trả tiền cho các instance thực thi ứng dụng. Virtual nodes có mô hình cấp tài nguyên khác, ở cấp pod. Xem [Comparing Virtual Nodes with Managed Nodes](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengcomparingvirtualwithmanagednodes_topic.htm).

Với một cụm dùng managed nodes, có thể lập khung:

```text
C_oke = C_cluster_if_applicable
      + Σ C_worker_compute_and_memory
      + C_worker_boot_volumes
      + C_persistent_storage
      + C_load_balancing
      + C_other_services
```

Một pod yêu cầu ít CPU không tự làm số OCPU của node đã chạy giảm xuống. Ví dụ, bạn vẫn phải đưa toàn bộ ba node được cấp vào dự toán dù tại thời điểm đo ứng dụng chỉ chiếm một phần tài nguyên của chúng. Muốn giảm chi phí nền, cần có thay đổi làm giảm tài nguyên tính phí thật sự, chẳng hạn điều chỉnh cấu hình hoặc số node khi đáp ứng được yêu cầu vận hành.

Khi dùng virtual nodes, lập dự toán theo các dòng tài nguyên pod và phí virtual node tương ứng; không lấy nguyên công thức managed node để áp dụng. Cũng không cộng lại một managed VM giả định nếu phương án thực tế không có tài nguyên đó.

### 6.2. Functions dùng lượt gọi và GB bộ nhớ-giây

OCI Functions tính phần thực thi theo bộ nhớ và thời gian, cùng thành phần lượt gọi. Tính năng provisioned concurrency còn có quy tắc phí riêng. Xem phần pricing tại [OCI Functions](https://www.oracle.com/cloud/cloud-native/functions/).

Đối với ví dụ chỉ xét lượt gọi thông thường, không dùng provisioned concurrency:

```text
Q_execution = Σ (Memory_GB_j × Billable_duration_seconds_j)

C_functions = N_billable_invocations × P_invocation
            + Q_execution × P_gb_second
```

Thời gian tính phí phải dùng đúng quy tắc đo và làm tròn của dịch vụ. Khi áp dụng phần miễn phí, phải xác định lượng còn được miễn trong kỳ trước khi tính lượng chịu phí.

Giả định toàn bộ lượng sử dụng sau đây đều chịu phí, không áp dụng miễn phí:

```text
N = 1.000.000 lượt gọi
Bộ nhớ mỗi lượt = 0,5 GB
Thời gian tính phí mỗi lượt = 0,2 giây

P_invocation = 0,0000003 USD/lượt gọi
P_gb_second  = 0,00002 USD/GB-giây
```

Ta có:

```text
Q_execution = 1.000.000 × 0,5 × 0,2 = 100.000 GB-giây

C_invocation = 1.000.000 × 0,0000003 = 0,30 USD
C_execution  = 100.000 × 0,00002    = 2,00 USD
C_functions  = 2,30 USD
```

Không thể lấy `100.000 GB-giây` so trực tiếp với giá `USD/OCPU-giờ`. Muốn so với một VM chạy lâu dài, cần dùng cùng lưu lượng, yêu cầu độ trễ, số lần gọi lại, thời gian khởi động và những dịch vụ phụ trợ cần thiết.

Một thay đổi bộ nhớ cũng cần xét thời gian: tăng từ `0,5 GB × 0,2 giây` lên `1 GB × 0,1 giây` giữ nguyên tích bộ nhớ-thời gian trong mô hình đơn giản. Nếu tăng RAM mà thời gian không giảm tương ứng, phần thực thi có thể đắt hơn.

## 7. Storage và mạng làm thay đổi kết quả so sánh CPU

### 7.1. Block Volume có dung lượng và hiệu năng

Block Volume có phần dung lượng và phần hiệu năng theo VPU trên mỗi GB. VPU là **Volume Performance Unit**, không phải CPU của VM. Các mức hiệu năng được giải thích trong [Block Volume Performance](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/blockvolumeperformance.htm).

Nếu đơn giá hiệu năng lấy theo **một VPU trên mỗi GB-tháng**, công thức minh họa cho volume giữ nguyên cả tháng là:

```text
C_volume = D_gb × P_capacity_gb_month
         + D_gb × VPU_per_gb × P_one_vpu_gb_month
```

Giả định:

```text
D_gb = 500 GB
VPU_per_gb = 10
P_capacity_gb_month = 0,03 USD/GB-tháng
P_one_vpu_gb_month  = 0,002 USD/(VPU/GB-tháng)

C_capacity    = 500 × 0,03       = 15 USD
C_performance = 500 × 10 × 0,002 = 10 USD
C_volume      = 25 USD/tháng
```

Nếu bảng giá đã thể hiện giá tổng cho mức 10 VPU/GB, dùng giá của mức đó; không nhân thêm 10 lần nữa. Tên đơn vị và cách trình bày mức giá phải được đọc cùng nhau.

Volume được cấp 500 GB không tự chuyển thành hóa đơn 80 GB chỉ vì dữ liệu đang chiếm 80 GB trong filesystem. Với tài nguyên tồn tại một phần tháng, dùng cách phân bổ thời gian của dịch vụ. Bảng giá Block Volume mô tả việc phân bổ theo số giây của tháng, với thời lượng tối thiểu tương ứng. Xem [ghi chú Storage trong OCI Price List](https://www.oracle.com/cloud/price-list/).

### 7.2. GB-tháng, request và băng thông không phải cùng đại lượng

Khi gặp các đơn vị sau, hãy tách chúng thành những dòng riêng:

| Đơn vị | Đại lượng được mô tả | Lỗi dễ gặp |
| --- | --- | --- |
| GB RAM-giờ | Bộ nhớ cấp cho quá trình tính toán theo thời gian | Nhầm với dung lượng ổ đĩa |
| GB dung lượng-tháng | Lưu trữ trong một khoảng thời gian | Dùng số giờ chạy VM cho volume còn tồn tại cả tháng |
| GB truyền đi | Lượng dữ liệu đi qua tuyến tính phí | Nhầm với dung lượng dữ liệu đang lưu |
| Mbps-giờ | Năng lực băng thông tính theo thời gian | Nhầm Mbps với GB hoặc MB/s |
| Giá trên 10.000 request | Một khối số lượng request | Lấy tổng request nhân thẳng giá của cả khối |

Ví dụ số học: nếu đơn giá là `P` USD cho 10.000 request, thì 5.000.000 request tương ứng `500 × P` trước khi xét các quy tắc tính phí khác.

GB và GiB cũng khác nhau về hệ đơn vị. Khi xuất cấu hình hoặc lập bảng tính, giữ nguyên đơn vị mà dịch vụ cung cấp và chuyển đổi có chủ đích nếu cần; tránh gắn cùng nhãn “GB” cho các số liệu đến từ hai hệ khác nhau.

## 8. So sánh theo kết quả công việc và tính sẵn sàng

### 8.1. Giá theo giờ chỉ là một góc nhìn

Giả sử đo cùng một tác vụ batch với cùng dữ liệu đầu vào, kiểm tra đầu ra giống nhau và chỉ xét CPU cộng RAM:

| Phương án giả định | Chi phí mỗi giờ | Thời gian hoàn thành | Chi phí một lần chạy |
| --- | ---: | ---: | ---: |
| A | 0,128 USD | 4 giờ | 0,512 USD |
| B | 0,140 USD | 3 giờ | 0,420 USD |

B đắt hơn theo giờ nhưng rẻ hơn cho một lần hoàn thành tác vụ. Kết luận này dựa trên kết quả đo giả định; không suy ra trực tiếp từ số vCPU hoặc tên kiến trúc.

Với API, một metric hữu ích là:

```text
Chi phí trên một triệu request thành công
  = Chi phí trong cửa sổ đo
    / Số request thành công trong cửa sổ đo
    × 1.000.000
```

Chỉ so sánh những cửa sổ đáp ứng cùng tiêu chí độ trễ và tỷ lệ lỗi. Một phương án bỏ nhiều request hoặc làm tăng độ trễ quá mức không đáp ứng cùng yêu cầu, dù số tiền chia cho tổng request gửi vào có vẻ thấp.

Đối với ứng dụng Java, giữ nhất quán phiên bản JDK, cấu hình heap, khoảng làm nóng JVM, dữ liệu kiểm thử và đường đi tới database. Nếu một phương án bị nghẽn disk hoặc database còn phương án kia không bị, cần ghi rõ nguyên nhân thay vì gán toàn bộ khác biệt cho OCPU.

### 8.2. Tính đủ tài nguyên dự phòng

Giả sử ứng dụng cần hai VM x86 của ví dụ ở phần 4 để đáp ứng phương án triển khai đã chọn:

```text
CPU và RAM cho hai VM = 2 × 92,16 = 184,32 USD/30 ngày
```

Cần cộng boot volume của từng VM, storage dùng chung, load balancer và các tài nguyên liên quan. Đây vẫn chưa phải tổng hóa đơn của toàn ứng dụng.

Đồng thời, hai VM không tự chứng minh hệ thống chịu được mất một VM. Nếu mỗi VM chỉ chịu được 60% tải cực đại thì hai VM đáp ứng tải khi cùng hoạt động, nhưng một VM còn lại sẽ quá tải khi VM kia gặp sự cố. Dự toán phải xuất phát từ năng lực cần còn lại sau sự cố đã chọn, không chỉ từ tổng số OCPU lúc bình thường.

Các khía cạnh sau nên được giữ nhất quán giữa các phương án so sánh:

- Lưu lượng mục tiêu và độ trễ chấp nhận được.
- Số instance hoặc node, cách phân bố và năng lực dự phòng.
- Dung lượng dữ liệu, backup và mục tiêu phục hồi.
- Thời gian hoạt động, tải nền và khoảng tăng tải.
- Phần công việc vận hành mà nhóm phải đảm nhiệm.

## 9. Quy trình lập bảng so sánh có thể đối chiếu

### Bước 1: Cố định yêu cầu công việc

Viết một mô tả ngắn, chẳng hạn: “API Java cần duy trì 300 request/giây, p95 dưới 250 ms; dữ liệu 200 GB; tiếp tục hoạt động khi một VM ứng dụng ngừng phục vụ”. Đây là đầu vào để định cỡ và đo thử, chưa phải bằng chứng một cấu hình cụ thể đáp ứng yêu cầu.

### Bước 2: Ghi lại cấu hình và thời gian

Với từng phương án, ghi shape, kiến trúc, OCPU/vCPU hoặc ECPU, RAM, số bản sao, khoảng chạy và những lần thay đổi cấu hình. Không chỉ ghi một con số “CPU = 4”.

### Bước 3: Lập một dòng cho từng thành phần giá

Mẫu bảng làm việc:

| Thành phần | Định danh cần giữ | Lượng sử dụng | Đơn giá | Thành tiền |
| --- | --- | --- | --- | --- |
| CPU ứng dụng | Shape, SKU, compartment | OCPU-giờ | USD/OCPU-giờ | `Q × P` |
| RAM ứng dụng | SKU RAM tương ứng | GB-giờ | USD/GB-giờ | `Q × P` |
| Database | Sản phẩm, metric, edition, license | ECPU-giờ hoặc OCPU-giờ | Giá đúng SKU | `Q × P` |
| Dung lượng | Loại tài nguyên, storage tier | GB-tháng | USD/GB-tháng | Theo lượng tính phí |
| Hiệu năng volume | Mức VPU và SKU | VPU × GB-tháng | Giá đơn vị tương ứng | Theo mức đã chọn |
| Các dòng còn lại | Cluster, LB, request, network... | Đơn vị riêng | Giá riêng | Tính riêng rồi cộng |

Mỗi dòng cũng nên giữ nguồn giá, ngày lấy giá, loại tiền và cách áp dụng ưu đãi. Khi dịch vụ đã gộp một thành phần vào SKU khác, ghi chú việc gộp để tránh đếm hai lần.

### Bước 4: Tính cả phương án tải nền và tải cao

Chia kỳ dự toán thành các khoảng thay đổi tài nguyên thay vì mặc định cấu hình lớn nhất chạy cả tháng. Giữ riêng dự phòng phục hồi, khoảng overlap khi triển khai phiên bản mới và tài nguyên còn lưu sau khi ứng dụng dừng nếu chúng có trong thiết kế.

### Bước 5: Đối chiếu với dữ liệu sử dụng

Trong một tenancy được cấp quyền đọc billing phù hợp, dùng Cost Analysis hoặc cost report để đối chiếu sản phẩm, SKU, khoảng thời gian, compartment và lượng sử dụng. Tài liệu [Compute Models của Autonomous Database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-compute-models.html) minh họa cách liên hệ các SKU database với thông tin chi phí và lượng sử dụng.

Nếu dự toán và dữ liệu thực khác nhau, lần lượt kiểm tra:

1. Đơn vị có khớp với đơn giá không?
2. Đã tính đủ số instance, số giờ và các lần scale chưa?
3. Có storage, backup hoặc thành phần dịch vụ nào bị bỏ sót không?
4. Có phần giá đã gộp bị tính hai lần không?
5. Có ưu đãi, mức giá hợp đồng, độ trễ báo cáo hoặc ranh giới múi giờ làm hai khoảng so sánh khác nhau không?

Sử dụng cùng khoảng thời gian và loại tiền khi đối chiếu. Không coi một số tiền đang hiển thị trong cửa sổ chưa hoàn tất là toàn bộ hóa đơn cuối kỳ.

### Bước 6: Xác minh khả năng cấp phát

Dự toán thấp chưa bảo đảm triển khai được. Số OCPU cần thiết phải nằm trong service limit, quota áp dụng và khả năng cung cấp shape tại vị trí triển khai. Đơn vị tính giá giúp tính tiền; các ràng buộc năng lực quyết định cấu hình đó có khả dụng khi cần hay không. Hãy giữ phương án shape thay thế có kết quả đo và dự toán riêng khi thiết kế yêu cầu điều này.

## 10. Những lỗi cần nhận ra khi đọc một dự toán

| Nhận định hoặc phép tính | Cách sửa |
| --- | --- |
| “Arm nào cũng 1 OCPU = 1 vCPU” | Tra dòng shape: A1 khác A2/A4 |
| “Có 4 vCPU nên hiệu năng chắc chắn bằng nhau” | Đo cùng workload, dữ liệu và yêu cầu chất lượng |
| Nhân số OCPU với cột giá so sánh theo vCPU | Dùng giá OCPU hoặc quy đổi cả số lượng lẫn giá |
| Cộng cả giá so sánh và giá OCPU | Chỉ tính một lần cho cùng phần CPU |
| Chỉ tính CPU cho VM Flex | Cộng RAM và các tài nguyên phụ thuộc |
| Dùng CPU utilization để giảm trực tiếp hóa đơn VM | Dùng số liệu này để quyết định định cỡ lại |
| Dùng quy tắc 4:1 ECPU cho mọi sản phẩm | Tra metric và hướng dẫn của chính dịch vụ |
| Chọn BYOL chỉ vì giá hiển thị thấp hơn | Kiểm tra mô hình license và quyền sử dụng phù hợp |
| Giả định stop ứng dụng làm mọi chi phí về 0 | Xét trạng thái OCI và từng tài nguyên còn tồn tại |
| So một VM đơn lẻ với một hệ thống có dự phòng | Đồng nhất yêu cầu tính sẵn sàng và phục hồi |

Khi hoàn thành một bảng so sánh, bạn cần giải thích được mỗi dòng: **tài nguyên nào được cấp, lượng nào được đo, đơn giá nào áp dụng và phần công việc nào nhận lại**. Từ đó, quyết định chi phí có thể được kiểm tra bằng cấu hình và dữ liệu sử dụng thay vì chỉ dựa vào một con số “giá mỗi CPU”.

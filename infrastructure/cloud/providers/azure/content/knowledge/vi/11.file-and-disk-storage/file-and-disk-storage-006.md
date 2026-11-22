# Managed disk và lựa chọn loại đĩa cho máy ảo

Khi triển khai một Azure Virtual Machine (VM), bạn không chỉ chọn số vCPU và RAM. Hiệu năng, độ bền và chi phí của ổ đĩa quyết định thời gian khởi động hệ điều hành, tốc độ đọc/ghi cơ sở dữ liệu, khả năng xử lý log và thời gian phục hồi khi máy ảo gặp sự cố. Một VM mạnh nhưng dùng loại đĩa không phù hợp vẫn có thể chậm; ngược lại, mua đĩa rất nhanh mà VM không đủ khả năng xử lý I/O chỉ làm tăng chi phí.

**Azure Managed Disks** là dịch vụ cung cấp các đĩa khối (block storage) cho Azure VMs. Azure quản lý hạ tầng lưu trữ bên dưới, còn người vận hành lựa chọn loại đĩa, dung lượng, đặc tính hiệu năng, khả năng dự phòng, bảo mật và cách gắn đĩa vào VM. Bài học tập trung vào **cách hiểu managed disk và chọn loại đĩa đúng cho máy ảo**, không chỉ là thao tác tạo một tài nguyên Disk.

Bài này thuộc chương **Lưu trữ tệp và đĩa** trong module **CLOUD_PROVIDERS_AZURE**. Module tìm hiểu Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, tính toán, lưu trữ, dữ liệu, triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng. Managed disk kết nối phần **compute** và **storage**: lựa chọn đúng giúp cân bằng tốc độ ứng dụng, mức sẵn sàng, sao lưu/phục hồi và ngân sách.

Sau bài học, bạn có thể:

- Phân biệt managed disk, OS disk, data disk, temporary disk và ephemeral OS disk.
- So sánh Standard HDD, Standard SSD, Premium SSD, Premium SSD v2 và Ultra Disk.
- Tính nhu cầu IOPS, throughput và đánh giá latency theo workload.
- Hiểu giới hạn hiệu năng ở cả **đĩa** và **VM**, tác động của host caching và bursting.
- Chọn loại đĩa cho web server, file server, batch, database và workload hiệu năng cao.
- Xem xét availability zones, redundancy, snapshot, backup, encryption và quản trị vòng đời.
- Tạo/kiểm tra managed disk bằng Azure Portal hoặc Azure CLI, gắn với VM lab khi được phép.

## 1. Managed disk là gì?

Trong mô hình Azure Managed Disks, bạn tạo một tài nguyên đĩa với các thuộc tính như:

- **Location** (region), và đôi khi **Availability Zone** theo thiết kế.
- **SKU/loại đĩa**, ví dụ Standard SSD hoặc Premium SSD.
- **Size** tính theo GiB cùng các giới hạn hiệu năng tương ứng.
- **Redundancy** và các tùy chọn về bảo mật, mã hóa được hỗ trợ.
- **Trạng thái sử dụng**: chưa gắn, đã gắn vào VM hoặc đang được thao tác theo vòng đời.

Azure tự quản lý việc bố trí block storage bên dưới. Bạn **không** phải tạo và quản lý một storage account chỉ để lưu từng virtual hard disk (VHD) như mô hình unmanaged disks cũ. Trong Azure Resource Manager, managed disk là tài nguyên có ID riêng, có thể quản lý quyền, tag, cost và vòng đời độc lập với VM.

~~~text
Azure subscription
└── Resource group: rg-app-prod
    ├── Virtual machine: vm-app-01
    │   ├── OS disk: disk-app-os
    │   └── Data disk: disk-app-data-01
    │
    ├── Managed disk: disk-app-os       (đã gắn vào VM)
    ├── Managed disk: disk-app-data-01  (đã gắn vào VM)
    └── Managed disk: disk-backup-test  (chưa gắn)
~~~

Sơ đồ chỉ mô tả quan hệ logic. Disk là tài nguyên quản lý riêng, không nhất thiết nằm "bên trong" VM hay cùng resource group với VM trong mọi kịch bản hợp lệ. Cần kiểm tra giới hạn và điều kiện region/zone khi gắn.

**Điểm quan trọng:** managed disk **khác Azure Files và Azure Blob Storage**. Managed disk là thiết bị lưu trữ khối phục vụ VM hoặc các cấu hình được hỗ trợ; Azure Files cung cấp file share theo giao thức file; Blob Storage cung cấp object API. Không dùng managed disk như một "ổ mạng chung" cho nhiều máy tùy ý nếu chưa thiết kế shared disk và cơ chế clustering phù hợp.

## 2. OS disk, data disk, temporary disk và ephemeral OS disk

Một VM có thể có nhiều loại lưu trữ với ý nghĩa rất khác nhau.

| Thành phần | Dùng để làm gì? | Dữ liệu có bền vững không? | Lưu ý |
|---|---|---|---|
| **Managed OS disk** | Chứa hệ điều hành khởi động VM | Có, theo đặc tính managed disk | Cần backup và chọn SKU phù hợp |
| **Managed data disk** | Chứa dữ liệu ứng dụng, database, log, file riêng | Có, theo đặc tính managed disk | Có thể gắn/tháo theo điều kiện hỗ trợ; cần format/mount ở guest OS |
| **Temporary/local disk** | Lưu file tạm, scratch, swap/pagefile hoặc cache tái tạo được | **Không có bảo đảm giữ lại dữ liệu** | Có thể mất dữ liệu khi redeploy, maintenance hoặc vòng đời host |
| **Ephemeral OS disk** | OS disk nằm trên lưu trữ cục bộ của host để phục vụ VM có thể tái tạo nhanh | **Không** dùng để giữ trạng thái OS lâu dài | Chỉ hỗ trợ trên VM size/cấu hình phù hợp |

### Managed OS disk

Đây là ổ cài Windows/Linux dùng để khởi động máy ảo. Với VM thông thường, OS disk là managed disk, dữ liệu OS tồn tại ngoài bộ nhớ RAM và không biến mất chỉ vì bạn restart VM. Việc **xóa VM** có thể xóa hoặc giữ OS disk tùy cấu hình **delete option**; luôn xác minh chính sách vòng đời khi tạo/xóa máy.

Không xem OS disk là nơi duy nhất lưu dữ liệu quan trọng. Với ứng dụng cần khôi phục độc lập, thường nên đặt database hoặc dữ liệu nghiệp vụ trên **data disks** và có backup đúng cách.

### Data disk

Data disk là đĩa bổ sung được VM nhìn thấy như thiết bị block. Trong guest OS, bạn có thể cần tạo partition, filesystem, mount point hoặc volume. Ví dụ:

~~~text
VM Linux
  /                    → managed OS disk
  /var/lib/myapp       → managed data disk
  /mnt/scratch         → temporary disk (không dùng lưu dữ liệu bền vững)
~~~

Một managed data disk mới tạo thường chưa có filesystem. **Gắn disk trong Azure không tự làm xuất hiện một thư mục dữ liệu đã được format và mount** trong Linux/Windows.

### Temporary disk

Nhiều VM size có **temporary storage** gắn với host, có thể hiển thị ở vị trí khác nhau tùy hệ điều hành và cấu hình. Đây **không phải managed disk**. Dữ liệu ở đó có thể bị mất trong một số sự kiện bảo trì, di chuyển hoặc thay host, nên chỉ dùng cho dữ liệu tái tạo được.

Không đặt database chính, bản backup duy nhất, khóa bảo mật hoặc file nghiệp vụ không thể tái tạo trên temporary disk. Ngoài ra, một số VM size không có temporary disk; không thiết kế ứng dụng phụ thuộc mặc định vào sự tồn tại của nó.

### Ephemeral OS disk

**Ephemeral OS disk** đặt dữ liệu hệ điều hành lên lưu trữ cục bộ của VM host theo cấu hình được hỗ trợ, nhằm phục vụ workload **stateless** có thể tạo lại nhanh, như một số nhóm scale-out. Nó khác temporary data disk, dù cùng dựa trên lưu trữ cục bộ trong một số mô hình.

Ephemeral OS disk **không thích hợp** nếu bạn kỳ vọng giữ thay đổi hệ điều hành sau mọi sự kiện host hoặc muốn thực hiện các hoạt động backup/snapshot như managed OS disk truyền thống. Trước khi sử dụng, xác minh VM size, image, caching/placement, dung lượng và giới hạn tính năng hiện hành.

## 3. Năm lựa chọn managed disk phổ biến

Azure cung cấp nhiều loại đĩa. Tên SKU, khả năng hỗ trợ và giá có thể thay đổi theo region, VM size và thời điểm; bảng sau mô tả **vai trò thiết kế**, không phải bảng benchmark cố định.

| Loại đĩa | Đặc trưng tổng quát | Workload thường phù hợp | Điểm cần kiểm tra |
|---|---|---|---|
| **Standard HDD** | Chi phí lưu trữ thấp, độ trễ và thông lượng khó ổn định hơn SSD | Dữ liệu ít truy cập, batch nhẹ, dev/test không nhạy với I/O | Không phù hợp ứng dụng cần độ trễ thấp; availability/SKU |
| **Standard SSD** | SSD cơ bản, thường ổn định hơn HDD cho workload vừa/nhẹ | Web nhỏ, dev/test, ứng dụng doanh nghiệp tải thấp-vừa | Hiệu năng theo kích thước/tier; giới hạn VM |
| **Premium SSD** | SSD hiệu năng cao cho production, nhiều size/performance tier | Web/API production, application server, database vừa | Quy tắc hiệu năng, host caching, bursting theo điều kiện |
| **Premium SSD v2** | Cấu hình dung lượng và IOPS/throughput linh hoạt hơn | Database hoặc workload cần điều chỉnh hiệu năng không hoàn toàn theo dung lượng | **Data disk**, không dùng làm OS disk; giới hạn VM/region/zone và caching |
| **Ultra Disk** | IOPS/throughput cao, hướng tới độ trễ rất thấp và workload chuyên biệt | Database giao dịch rất lớn, hệ thống I/O chuyên sâu | **Data disk**, không dùng làm OS disk; hỗ trợ VM/region/zone, hạn chế khác |

### Standard HDD: ưu tiên chi phí, chấp nhận chậm

Standard HDD phù hợp khi dữ liệu không cần đọc ghi liên tục, truy cập ngẫu nhiên ít, throughput không quá khắt khe. Ví dụ: VM lab chạy tác vụ nhỏ hoặc dữ liệu ít truy cập. Nhưng chi phí thấp trên mỗi GiB **không đồng nghĩa** chi phí hệ thống thấp: nếu batch chạy lâu hơn hoặc phải tăng số VM để bù I/O, tổng chi phí có thể tăng.

### Standard SSD: điểm khởi đầu cân bằng

Standard SSD thường là lựa chọn hợp lý cho môi trường thử nghiệm thực tế, máy chủ ứng dụng ít I/O hoặc workload chưa xác định đủ để đầu tư vào Premium. Hãy theo dõi metric trước khi nâng cấp.

### Premium SSD: lựa chọn production phổ biến

Premium SSD thường phù hợp khi ứng dụng cần IOPS và latency tốt hơn, đồng thời bạn muốn kiểu quản trị quen thuộc. Hiệu năng phụ thuộc **disk size/performance tier** và điều kiện hỗ trợ. Bạn có thể trả tiền cho dung lượng/tier cao hơn để có mức IOPS/throughput thích hợp, nhưng VM vẫn phải hỗ trợ cấp hiệu năng tương ứng.

### Premium SSD v2: tách quyết định hiệu năng và dung lượng

Premium SSD v2 cho phép lựa chọn **size**, **provisioned IOPS** và **provisioned throughput** theo các dải được hỗ trợ; thường phù hợp khi bạn muốn giữ dung lượng vừa phải nhưng cần nhiều IOPS. Có baseline và giới hạn theo size/tài nguyên; không được cấu hình tùy ý vượt mọi giới hạn.

**Không dùng Premium SSD v2 cho OS disk.** Đây là loại **data disk**. Khả năng hỗ trợ host caching, snapshot, backup, redundancy, VM family và Availability Zone phải được kiểm tra riêng; không sao chép cấu hình từ Premium SSD thông thường.

### Ultra Disk: workload chuyên dụng

Ultra Disk hướng tới nhu cầu hiệu năng cao và độ trễ thấp, nhưng yêu cầu VM được hỗ trợ, khu vực/zone phù hợp và cấu hình riêng. Bạn có thể đặt IOPS/throughput theo giới hạn của từng size. **Ultra Disk chỉ là data disk**, không dùng làm OS disk, và không nên xem mọi tính năng backup/caching/redundancy giống Premium SSD.

Nếu workload chỉ là website đọc file tĩnh hoặc máy chủ tác vụ nhẹ, Ultra Disk gần như chắc chắn không phải lựa chọn đầu tiên nên đánh giá.

## 4. Không chọn đĩa chỉ theo GiB: IOPS, throughput và latency

Ba chỉ số cần đo:

1. **IOPS (I/O operations per second):** số thao tác đọc/ghi mỗi giây.
2. **Throughput:** lượng dữ liệu truyền mỗi giây, thường diễn đạt bằng MB/s hoặc MiB/s.
3. **Latency:** thời gian hoàn thành một thao tác I/O, thường tính bằng ms. Với giao dịch tương tác, độ trễ ở các phân vị p95/p99 quan trọng hơn chỉ trung bình.

**IOPS cao** hữu ích cho nhiều yêu cầu I/O nhỏ, ví dụ database OLTP. **Throughput cao** hữu ích cho dòng dữ liệu lớn, ví dụ đọc file tuần tự hoặc batch. Latency cho biết mỗi I/O chậm thế nào và ảnh hưởng trực tiếp tới phản hồi ứng dụng.

### Ví dụ tính đơn giản

Giả sử ứng dụng có **6.000 IOPS** với kích thước I/O trung bình **16 KiB**. Throughput lý thuyết:

~~~text
6.000 I/O/s × 16 KiB/I/O = 96.000 KiB/s
96.000 / 1.024 = 93,75 MiB/s
~~~

Nếu workload tăng lên **12.000 IOPS** với cùng kích thước I/O, throughput sẽ xấp xỉ **187,5 MiB/s**. Vì thế khi chọn đĩa, bạn phải đáp ứng **đồng thời** số thao tác và số byte mỗi giây.

Ví dụ ngược: workload cần **150 MiB/s** với kích thước I/O trung bình **16 KiB**:

~~~text
150 MiB/s × 1.024 KiB/MiB ÷ 16 KiB/I/O
= 9.600 IOPS
~~~

Các công thức trên giúp **ước lượng sơ bộ**, không phải cam kết benchmark. I/O thực gồm đọc/ghi khác nhau, random/sequential, queue depth, caching và giới hạn application/filesystem. Khi so sánh với tài liệu Azure dùng **MB/s**, hãy chú ý khác biệt giữa MB (thập phân) và MiB (nhị phân).

### Đọc workload profile trước khi mua

| Câu hỏi | Ý nghĩa |
|---|---|
| IOPS giờ cao điểm và p95/p99 là bao nhiêu? | Đánh giá nhu cầu thực thay vì trung bình ngày |
| Kích thước I/O điển hình? | Quy đổi IOPS sang throughput |
| Read/Write ratio? | Xác định lợi ích của cache và đặc tính ghi |
| Random hay sequential? | Ảnh hưởng latency và throughput |
| Dữ liệu cần giữ bao lâu? | Chọn dung lượng, backup và lifecycle |
| Ứng dụng có chịu được throttling/latency tăng? | Cân nhắc reserve headroom và burst |
| Bao nhiêu thời gian cần xử lý sau khi lỗi disk/VM? | Quyết định backup, redundancy và DR |

Không dùng chỉ số tổng lưu trữ (ví dụ 200 GiB đang dùng) để suy ra ứng dụng cần đĩa nhanh. **Dung lượng** và **mức I/O** là hai chiều khác nhau.

## 5. Đĩa nhanh đến đâu còn phụ thuộc vào VM

Mỗi VM size có giới hạn về số data disks gắn được, **maximum uncached disk IOPS/throughput** và đôi khi các giới hạn về cached I/O, network hoặc khả năng hỗ trợ Premium/Ultra. Đĩa có khả năng 20.000 IOPS không tự làm VM đạt 20.000 IOPS nếu VM bị giới hạn ở mức thấp hơn.

~~~text
Application
    |
Guest OS / filesystem / driver
    |
Azure VM size (IOPS/throughput limits)
    |
Host cache (nếu bật và được hỗ trợ)
    |
Managed disk (size/SKU/performance limits)
    |
Azure storage backend
~~~

Hiệu năng quan sát là kết quả của **đường đi đầu-cuối**, bị chi phối bởi nút thắt. Có thể mô hình hóa sơ bộ:

~~~text
IOPS thực tế ≲ min(
    IOPS mà ứng dụng/OS tạo được,
    giới hạn IOPS phù hợp của VM,
    giới hạn IOPS hiệu dụng của đĩa
)

Throughput thực tế ≲ min(
    throughput của ứng dụng/OS,
    giới hạn throughput phù hợp của VM,
    throughput hiệu dụng của đĩa
)
~~~

Đây là cách nghĩ để tìm bottleneck, không phải công thức mô tả toàn bộ cache và scheduling. Với nhiều disk, giới hạn tổng của VM vẫn tồn tại; không thể cộng vô hạn IOPS các đĩa để vượt trần VM.

### Ví dụ chọn cấu hình

Giả sử cơ sở dữ liệu cần **10.000 IOPS**, khoảng **160 MiB/s**, dung lượng hữu dụng 500 GiB. Bạn nên:

1. Chọn VM family/size có khả năng chạy database và **uncached** disk throughput/IOPS vượt yêu cầu, có headroom.
2. Chọn data disk SKU/size có thể cung cấp IOPS và throughput tương ứng.
3. Xác minh hỗ trợ region/zone và caching cho cặp VM–disk.
4. Đo thực tế với workload đại diện, không chỉ bài test sequential I/O.
5. Theo dõi khi tăng số người dùng hoặc thay đổi query/index.

Không có một câu trả lời SKU duy nhất từ ba số liệu trên nếu chưa biết workload, latency SLO, bản phân phối I/O, VM compatibility và giá tại region.

## 6. Host caching, bursting và striping

### Host caching

Một số cấu hình disk/VM hỗ trợ **host caching** (ví dụ None, ReadOnly hoặc ReadWrite theo loại đĩa và vị trí OS/data disk). Cache có thể cải thiện một số workload đọc nhưng phải xét đặc tính ghi và tính nhất quán dữ liệu.

- **ReadOnly** có thể giúp workload đọc lặp lại khi được hỗ trợ.
- **ReadWrite** không phù hợp với mọi dạng ghi và hệ thống có yêu cầu dữ liệu chặt; luôn kiểm tra khuyến nghị của ứng dụng/database và Azure.
- **None** là lựa chọn không sử dụng host caching cho disk đó; có thể được yêu cầu ở một số workload hoặc disk type.

Premium SSD v2 và Ultra Disk có những hạn chế liên quan host caching; **không suy luận** rằng các chế độ cache của Premium SSD thông thường đều áp dụng cho chúng.

Một database có thể khuyến nghị cache khác nhau cho OS disk, data files và transaction log. Hãy theo tài liệu của engine và loại disk đang chạy.

### Bursting

Một số disk SKU/size hỗ trợ **disk bursting** để xử lý các đợt I/O tăng ngắn hạn. Có các cơ chế theo credit hoặc theo cấu hình/on-demand tùy dòng sản phẩm. Bursting không bảo đảm một mức IOPS cao liên tục.

Ví dụ, VM khởi động hoặc cập nhật package trong vài phút có thể cần I/O tăng ngắn, nhưng database giao dịch tải cao **suốt ngày** nên được sizing theo năng lực bền vững thay vì dựa vào burst.

### Striping / ghép nhiều data disks

Với workload có nhu cầu thông lượng/IOPS cao, bạn có thể dùng **Storage Spaces** trên Windows hoặc **LVM/RAID theo thiết kế được hỗ trợ** trên Linux để kết hợp nhiều data disks thành volume. Tuy nhiên:

- VM vẫn có giới hạn tổng IOPS/throughput và số disk.
- Hiệu năng còn phụ thuộc kích thước stripe, queue depth và mẫu I/O.
- Backup/snapshot ứng dụng cần xử lý nhất quán trên toàn bộ volume.
- Cần có quy trình mở rộng/khôi phục volume tránh mất dữ liệu.

Đừng coi striping là giải pháp mặc định trước khi đánh giá Premium SSD v2, Ultra Disk hoặc một VM size phù hợp hơn.

## 7. Quyết định loại đĩa theo workload

### Máy chủ web/API

Web server thường đọc executable, thư viện và ghi một lượng log nhỏ. Nếu dịch vụ thật sự **stateless**, dữ liệu quan trọng nên đặt ở database/storage được quản lý, không nằm duy nhất trên OS disk.

- Dev/test hoặc lượng I/O thấp: **Standard SSD** là điểm khởi đầu để đo.
- Production cần khởi động nhanh, phản hồi ổn định và nhiều I/O hơn: cân nhắc **Premium SSD** nếu đo đạc cho thấy cần.
- Không bắt đầu bằng Ultra Disk chỉ vì ứng dụng có nhiều request HTTP; nhiều bottleneck có thể nằm ở CPU, network hoặc database.

### Database giao dịch (OLTP)

Database thường có nhiều I/O nhỏ và nhạy latency. Tách data và log khi cần quản trị, khôi phục và tuning hiệu năng:

- **Premium SSD**: điểm xuất phát thường gặp cho cơ sở dữ liệu vừa.
- **Premium SSD v2**: đáng đánh giá nếu cần IOPS/throughput cấu hình linh hoạt.
- **Ultra Disk**: chỉ cho trường hợp hiệu năng/latency đặc biệt cao, sau khi xác nhận VM/region hỗ trợ.

Phải xét read/write ratio, transaction log và cơ chế checkpoint, không chọn disk theo IOPS tổng lý thuyết.

### File server hoặc dịch vụ xử lý tệp

Nếu chỉ cần một ổ cho dữ liệu ứng dụng trong VM, Standard SSD hoặc Premium SSD có thể đủ. Nếu nhu cầu là **nhiều VM truy cập cùng file share bằng SMB**, xem xét **Azure Files** hoặc giải pháp file sharing được hỗ trợ trước khi dùng shared managed disk.

### Batch, xử lý dữ liệu và scratch

Batch lớn có thể ưu tiên throughput tuần tự hơn IOPS. Dữ liệu có thể tái tạo đôi khi dùng temporary storage/ephemeral strategy phù hợp, nhưng input và output quan trọng phải được lưu bền vững. Với batch có checkpoint quan trọng, nên dùng managed disk hoặc object storage/backup tương ứng.

### Hệ thống cần hàng nghìn IOPS

Không tự động chọn Ultra. Đầu tiên đo nhu cầu, chọn VM size tương thích, kiểm tra Premium SSD v2/Premium SSD có đủ hay không và so chi phí tổng cùng HA/backup.

## 8. Bảng quyết định ngắn theo tiêu chí

| Nếu ưu tiên | Ứng viên nên đánh giá trước | Lý do |
|---|---|---|
| Chi phí thấp, I/O ít và không nhạy latency | Standard HDD | Hạ tầng lưu trữ rẻ hơn, đổi lại trải nghiệm I/O |
| Giá/hiệu năng cân bằng cho dev/test hoặc app nhẹ | Standard SSD | Ít phức tạp, phù hợp nhiều workload cơ bản |
| Production với độ trễ/IOPS ổn định hơn | Premium SSD | Lựa chọn quen thuộc với khả năng quản trị rộng |
| Tăng IOPS mà không phải tăng dung lượng theo các bậc truyền thống | Premium SSD v2 | Điều chỉnh hiệu năng độc lập hơn |
| Database rất lớn, độ trễ đặc biệt thấp, I/O cực cao | Ultra Disk | Thiết kế hiệu năng chuyên sâu, yêu cầu tương thích riêng |
| OS disk cho VM truyền thống | Standard SSD hoặc Premium SSD theo VM/workload | Premium SSD v2 và Ultra Disk không dành cho OS disk |
| Scratch có thể mất và tái tạo | Temporary/local storage khi VM có hỗ trợ | Không được coi là persistent managed disk |

**Lưu ý:** bảng là hướng dẫn **shortlist**, không thay thế đối chiếu tài liệu SKU và đo benchmark. Một số loại đĩa có giới hạn về hỗ trợ backup, snapshot, caching, ZRS, bursting, zone và kích thước VM. Phải kiểm tra tại thời điểm triển khai.

## 9. Availability Zones, redundancy và khả năng phục hồi

Managed disk là tài nguyên lưu trữ trong một **region** Azure. Một số loại/region hỗ trợ **LRS (locally redundant storage)** và **ZRS (zone-redundant storage)** trong cấu hình phù hợp.

### LRS và ZRS

- **LRS:** các bản sao dữ liệu được duy trì theo mô hình redundancy trong phạm vi khu vực lưu trữ tại một vùng lỗi phù hợp với dịch vụ.
- **ZRS:** sao chép đồng bộ qua các Availability Zones trong region được hỗ trợ, nhằm cải thiện khả năng chịu lỗi ở mức zone đối với các loại managed disk hỗ trợ.

**ZRS không đồng nghĩa sao chép xuyên region.** Nếu mục tiêu là phục hồi trước sự cố toàn bộ region, cần thiết kế backup/replication/DR ở mức ứng dụng hoặc dịch vụ, ví dụ Azure Site Recovery hay giải pháp riêng cho cơ sở dữ liệu.

### Chọn zone cho VM và disk

Một VM đặt tại **zone 1** phải dùng các đĩa phù hợp với quy tắc vùng đặt tài nguyên và loại disk. Một số disk được pin theo zone; một số cấu hình ZRS có đặc tính khác. Không giả định có thể gắn disk từ bất kỳ zone/region nào vào mọi VM.

Trước khi tạo VM:

1. Xác nhận loại disk và VM size có hỗ trợ trong region/zone.
2. Chọn redundancy dựa trên rủi ro lỗi zone và ngân sách.
3. Dùng Availability Sets/Zones hoặc scale-out phù hợp để xử lý lỗi compute.
4. Thiết kế backup/restore nếu dữ liệu có giá trị.
5. Kiểm tra quyền, encryption và khả năng attach/move theo hỗ trợ hiện hành.

### Disk durability không thay backup

Một managed disk có redundancy tốt vẫn có thể chứa dữ liệu bị **xóa nhầm, mã hóa bởi ransomware hoặc ghi sai từ ứng dụng**. Các lỗi logic có thể được ghi đồng bộ lên bản sao của storage. Backup có retention, phục hồi đã kiểm thử và chính sách bảo vệ khỏi xóa vẫn rất cần thiết.

## 10. Snapshot, Azure Backup và Disaster Recovery

### Snapshot

Snapshot là bản chụp trạng thái disk tại một thời điểm theo cách dịch vụ hỗ trợ. Nó có thể giúp sao chép, kiểm thử hoặc phục hồi disk. Tuy nhiên:

- Snapshot không mặc nhiên là **application-consistent** cho một database đang hoạt động.
- Nếu workload có nhiều disk, cần xử lý sự nhất quán giữa chúng.
- Snapshot cần retention, kiểm soát truy cập và quản lý chi phí.
- Các loại disk có thể khác nhau về cách hỗ trợ snapshot và API.

### Azure Backup

**Azure Backup** cho Azure VM giúp định nghĩa chính sách bảo vệ và khôi phục theo khả năng của VM/disks, không chỉ là thao tác lưu một file sao chép thủ công. Khi thiết kế, xác định:

- RPO/RTO và thời hạn lưu bản backup.
- Backup toàn VM hay workload/database cần chính sách riêng.
- Phạm vi disk được đưa vào hoặc loại trừ, consistency và những hạn chế SKU.
- Encryption keys, RBAC và thao tác khôi phục khi region hoặc tài khoản có sự cố.

**Không giả định** tất cả disk SKU có cùng tính năng backup hoặc giá. Đối chiếu ma trận hỗ trợ của Azure Backup với loại VM, disk và region đang dùng.

### Region failover

Để giảm rủi ro sự cố toàn region, xem xét kiến trúc multi-region, Azure Site Recovery cho workload được hỗ trợ hoặc cơ chế replication do hệ thống dữ liệu cung cấp. Các giải pháp có RPO/RTO và ràng buộc khác nhau; **không coi một disk snapshot LRS là giải pháp DR đa region hoàn chỉnh**.

Một bài kiểm thử DR thực tế phải xác nhận VM khởi động, dữ liệu nhất quán, dịch vụ kết nối được và ứng dụng xử lý giao dịch thành công.

## 11. Bảo mật và mã hóa managed disk

### Server-side encryption at rest

Azure Managed Disks được mã hóa khi lưu trữ theo cơ chế **server-side encryption (SSE)** của nền tảng. Bạn có thể sử dụng khóa do Microsoft quản lý theo thiết lập mặc định hoặc đánh giá **customer-managed keys (CMK)** qua **Disk Encryption Set** nếu yêu cầu bảo mật/chính sách.

Với CMK, phải thiết kế:

- Quyền truy cập khóa và identity/permission cần thiết.
- Tính khả dụng của Azure Key Vault hoặc Managed HSM theo mô hình hỗ trợ.
- Quy trình rotation, phục hồi và xử lý khi khóa bị vô hiệu hóa/xóa.
- Khu vực tài nguyên, subscription và những điều kiện tương thích của disk SKU.

**SSE/CMK không thay thế Azure RBAC hoặc backup.** Một người có quyền xóa disk vẫn có thể gây gián đoạn dù dữ liệu được mã hóa.

### Encryption at host và mã hóa trong guest

Azure còn cung cấp những khả năng như **encryption at host** hoặc các cơ chế mã hóa trong guest OS theo workload và cấu hình hỗ trợ. **Azure Disk Encryption (ADE)** với BitLocker/dm-crypt là một chủ đề khác với SSE; không áp dụng đồng thời một cách máy móc hoặc cho rằng mọi VM/disk đều tương thích.

Hãy chọn phương án theo chính sách, khả năng dịch vụ và vòng đời khóa. Cần kiểm tra cả **OS disk, data disk, snapshot, backup và vùng khôi phục**.

### Phân quyền và quản trị

Disk có thể được quản lý bằng Azure RBAC ở phạm vi subscription, resource group hoặc tài nguyên riêng. Chỉ nhóm vận hành được phê duyệt mới có quyền tạo, attach/detach, export, snapshot hoặc xóa disk. Đặc biệt, quyền xuất disk/snapshot có thể dẫn tới rủi ro truy cập dữ liệu: cần kiểm soát như những thao tác nhạy cảm.

Với dữ liệu quan trọng, xem xét Azure Policy, resource lock phù hợp, tagging, Activity Log và cảnh báo thay đổi cấu hình. **CanNotDelete lock** giúp ngăn xóa nhầm ở management plane nhưng không chặn việc ghi sai dữ liệu bên trong guest OS.

## 12. Quản trị vòng đời: create, attach, resize, detach và delete

Một managed disk có thể tồn tại **độc lập** với VM. Tài nguyên disk có thể vẫn phát sinh chi phí nếu bạn đã detach khỏi VM mà chưa xóa.

### Tạo và gắn

Để dùng data disk trong VM, quy trình thường là:

1. Tạo managed disk có kích thước/SKU phù hợp.
2. Gắn (attach) disk vào VM với vị trí và cách cache được hỗ trợ.
3. Vào guest OS để nhận diện thiết bị mới.
4. Với disk mới chưa có dữ liệu: partition/format/mount theo hệ điều hành.
5. Cấu hình persistent mount, phân quyền filesystem và monitoring.

**Phân biệt tuyệt đối disk mới với disk chứa dữ liệu:** lệnh format sẽ phá hủy dữ liệu hiện có. Khi attach disk đã chứa dữ liệu, cần **mount và kiểm tra filesystem**, không format lại.

### Resize

Managed disk có thể hỗ trợ tăng dung lượng theo những điều kiện riêng về loại đĩa, trạng thái VM và kích thước. Sau khi tăng size ở Azure, bạn có thể còn phải **mở rộng partition/filesystem** trong guest OS. Không xem thao tác đổi dung lượng Azure là tương đương ứng dụng ngay lập tức có thêm không gian sử dụng.

Không mặc định resize xuống kích thước nhỏ hơn được hỗ trợ. Với một số thao tác/sản phẩm, tăng size hoặc thay đổi SKU có thể cần VM deallocate, thay đổi cấu hình và kế hoạch bảo trì; cần đối chiếu tài liệu đúng loại disk.

### Detach và delete

Khi gỡ data disk khỏi VM, hãy dừng ứng dụng ghi, unmount đúng cách, kiểm tra filesystem rồi detach. Đừng gỡ một volume đang giữ transaction database mà không có quy trình nhất quán. Sau detach, disk là tài nguyên còn tồn tại và **tiếp tục có thể bị tính phí**.

Khi xóa VM, kiểm tra **delete option** của OS disk, data disks và network resources. Đừng suy luận rằng xóa VM luôn xóa mọi disk, hoặc giữ mọi disk. Kiểm tra trước khi xác nhận bất kỳ thao tác xóa production nào.

## 13. Quản lý disk bằng Azure Portal

Ví dụ tạo data disk trong subscription lab:

1. Mở [Azure Portal](https://portal.azure.com/), chọn đúng subscription và resource group.
2. Tìm **Disks** rồi chọn **Create**.
3. Nhập tên như **disk-lab-data-01**, region và Availability Zone phù hợp.
4. Chọn loại đĩa: ví dụ **Standard SSD** cho bài lab nhẹ.
5. Chọn kích thước cần thiết; lưu ý **kích thước provisioned** có thể là cơ sở tính giá, không chỉ dung lượng đã ghi.
6. Xác định source type là tạo đĩa mới rỗng hoặc theo nguồn dữ liệu phù hợp nếu yêu cầu.
7. Kiểm tra redundancy và encryption settings được hỗ trợ.
8. Xem bảng giá dự kiến, policy và bấm tạo disk.

Nếu cần gắn với VM lab, vào VM → **Disks** → thêm data disk có sẵn → chọn caching hỗ trợ → lưu. Đăng nhập guest OS để xem và chuẩn bị volume nếu disk mới. Không tiến hành format trên VM chứa dữ liệu quan trọng.

### Quan sát thông số disk

Trong trang Disks, kiểm tra:

- **SKU**, dung lượng và zone/region.
- **Managed by** (VM được gắn) hoặc trạng thái unattached.
- Các tham số hiệu năng như IOPS/throughput khi loại disk hỗ trợ hiển thị/chỉnh.
- Encryption, tags, resource ID, quyền truy cập và chi phí.
- Snapshot/backup nếu tính năng tương ứng đã được cấu hình.

Azure Portal có thể thay đổi tên mục, giới hạn và tùy chọn theo SKU/region. Nếu một option không xuất hiện, không nên tự kết luận tất cả loại disk đều hỗ trợ nhưng Portal bị lỗi; hãy kiểm tra tài liệu hỗ trợ.

## 14. Azure CLI: tạo và kiểm tra managed disk

Phần này tạo **một data disk rỗng riêng biệt**, không cần tạo VM. Nó phù hợp để học tài nguyên disk và tránh tác động lên filesystem production. Tuy nhiên, **disk có thể tính phí ngay cả khi chưa gắn VM**, vì vậy cần dọn sau bài thực hành.

Ví dụ dùng **Bash trong Azure Cloud Shell**. Với Windows PowerShell, biến và cú pháp nối dòng khác; nếu dùng PowerShell, chuyển các lệnh cho phù hợp.

### Bước 1: đăng nhập và chọn subscription

~~~bash
az login
az account list --output table
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --output table

RG="rg-managed-disk-lab"
REGION="southeastasia"
DISK="disk-lab-data-01"
~~~

Thay **SUBSCRIPTION_ID** bằng subscription lab được phép, không chạy trên subscription production. Nếu Cloud Shell đã có session đăng nhập thì vẫn phải kiểm tra subscription đang chọn.

### Bước 2: tạo resource group riêng

~~~bash
az group create \
  --name "$RG" \
  --location "$REGION" \
  --tags environment=learning purpose=managed-disk-lab
~~~

### Bước 3: tạo Standard SSD data disk

~~~bash
az disk create \
  --resource-group "$RG" \
  --name "$DISK" \
  --location "$REGION" \
  --size-gb 32 \
  --sku StandardSSD_LRS \
  --tags environment=learning purpose=managed-disk-lab
~~~

Ví dụ chọn **32 GiB** và Standard SSD LRS để đơn giản hóa bài tập. Đây không phải khuyến nghị mặc định cho production. Nếu subscription/region không cho phép SKU hoặc bị Azure Policy chặn, hãy làm theo chính sách thay vì tự chuyển sang SKU đắt hơn.

### Bước 4: xem disk được tạo

~~~bash
az disk show \
  --resource-group "$RG" \
  --name "$DISK" \
  --query "{name:name,sku:sku.name,sizeGiB:diskSizeGB,state:diskState,location:location,id:id}" \
  --output json

az disk list \
  --resource-group "$RG" \
  --output table
~~~

Kiểm tra **sku.name**, **diskSizeGB**, **diskState** và **id**. Disk mới chưa gắn thường ở trạng thái tương ứng với tài nguyên chưa attach. Cột/trạng thái chính xác phụ thuộc tài nguyên và phiên bản API.

### Bước 5: kiểm tra các SKU trước khi nâng cấp

Trước khi dùng Premium SSD v2 hoặc Ultra, xác nhận VM size, region, Availability Zone, quota và tính năng tương thích. Azure CLI có lệnh liệt kê SKU/VM size và tài nguyên liên quan, nhưng **không coi riêng một tên SKU trong kết quả liệt kê là bằng chứng có thể attach vào VM cụ thể**.

Bạn cũng cần xác định **workload metrics**, vì đĩa càng đắt chưa chắc làm ứng dụng nhanh hơn.

### Bước 6: xóa tài nguyên lab

Sau khi xác nhận disk chưa gắn VM và resource group chỉ chứa dữ liệu thử nghiệm:

~~~bash
az disk delete \
  --resource-group "$RG" \
  --name "$DISK" \
  --yes

az group delete \
  --name "$RG" \
  --yes

az group exists --name "$RG"
~~~

Giá trị **false** sau khi hoàn tất cho biết resource group không còn theo ARM. Theo dõi Cost Management vì dữ liệu hóa đơn có thể cập nhật trễ.

**Không chạy lệnh xóa** nếu đang dùng resource group có tài nguyên người khác hoặc đĩa đã attach vào VM thật. Nếu một disk đang được gắn, trước tiên cần làm theo quy trình ngừng I/O, detach và bảo toàn dữ liệu.

## 15. Gắn data disk vào VM và chuẩn bị trong guest OS

Nếu bạn có một **VM lab riêng**, có thể làm thêm phần attach. Đây là bài nâng cao tùy chọn vì tạo VM làm phát sinh chi phí compute và sai sót khi format có thể xóa dữ liệu.

### Gắn disk bằng Azure CLI

Ví dụ VM và disk đã tồn tại trong lab, cùng các điều kiện region/zone tương thích:

~~~bash
az vm disk attach \
  --resource-group <LAB_RESOURCE_GROUP> \
  --vm-name <LAB_VM_NAME> \
  --name <EXISTING_LAB_DATA_DISK_NAME>
~~~

Chỉ thay placeholder sau khi xác nhận đây là **data disk trống của lab**, không phải OS disk hoặc disk chứa dữ liệu người dùng. Một số loại disk hoặc VM size yêu cầu cấu hình bổ sung; không cố attach nếu không tương thích.

### Linux: kiểm tra thiết bị trước khi format

Trên Linux, kiểm tra ổ và filesystem:

~~~bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,UUID
lsblk -f
~~~

Địa chỉ thiết bị có thể thay đổi giữa VM types, kernel và quá trình khởi động. **Không được giả định data disk luôn là /dev/sdc** hoặc tên tiếp theo sau OS disk. Đối chiếu size, serial/LUN và tài liệu VM trước khi thao tác.

Nếu disk hoàn toàn mới, người vận hành có thể tạo filesystem và mount bằng công cụ OS phù hợp. Việc format như **mkfs** hoặc **Format-Volume** có khả năng phá dữ liệu; bài này không cung cấp một lệnh format hard-coded để tránh format nhầm ổ. Với disk đã có dữ liệu, chỉ mount sau khi kiểm tra filesystem.

Để mount bền vững, Linux thường dùng **UUID trong /etc/fstab** thay vì tên thiết bị có thể thay đổi. Kiểm tra cấu hình mount cẩn thận để VM vẫn khởi động khi disk tạm vắng mặt hoặc có lỗi.

### Windows: kiểm tra trong Disk Management

Với Windows VM, xem **Disk Management** hoặc PowerShell Get-Disk/Get-Volume để xác định disk theo size, trạng thái và số thứ tự. Nếu hoàn toàn là disk mới, có thể cần Initialize Disk, tạo volume, format và chọn drive letter. **Không initialize/format một đĩa đã chứa dữ liệu**.

### Tháo đĩa

Trước khi detach: dừng ghi dữ liệu, đóng ứng dụng, unmount/offline volume phù hợp, rồi dùng Portal hoặc Azure CLI để detach theo quy trình. Đảm bảo application backup và restore đã được kiểm tra nếu disk quan trọng.

## 16. Quan sát và chẩn đoán hiệu năng đĩa

Khi ứng dụng chậm, hãy quan sát **cả Azure metrics và guest OS**:

| Tín hiệu | Giải thích |
|---|---|
| Disk Read/Write Operations | Số I/O đọc/ghi theo thời gian |
| Disk Read/Write Bytes | Dữ liệu đọc/ghi, giúp ước lượng throughput |
| Disk latency | Thời gian phản hồi I/O khi metric/OS cung cấp |
| Disk queue length / I/O wait | Tác vụ bị dồn hoặc chờ disk |
| Disk bandwidth/IOPS consumed percentage | Đánh giá có gần mức giới hạn VM/disk không, khi metric hỗ trợ |
| Throttled I/O / giới hạn VM | Có dấu hiệu vượt giới hạn hiệu năng hay không |
| CPU/RAM/cache | Tránh nhầm nghẽn compute/memory với disk |

Azure Monitor có các metric theo VM và disk được hỗ trợ; tên cụ thể có thể thay đổi theo loại tài nguyên/SKU. Guest OS cung cấp thông tin bổ sung, ví dụ **iostat**, **sar**, **perfmon**, **Get-Counter** và monitoring của database.

### Quy trình khi database có latency cao

1. Xác nhận lỗi nằm ở request nào và thời điểm nào; thu thập latency p95/p99.
2. Đo IOPS, throughput, queue depth, read/write ratio.
3. Kiểm tra VM có chạm trần uncached/cached disk IOPS/throughput không.
4. Kiểm tra disk SKU/size/performance setting có chạm trần không.
5. Kiểm tra host caching, filesystem, driver, database queries/index.
6. Nếu cần nâng cấp, chọn thay đổi ít rủi ro nhất và chuẩn bị kế hoạch rollback.
7. Benchmark lại với workload đại diện để xác minh hiệu quả và chi phí.

**Disk queue cao không luôn chứng minh disk SKU yếu.** Nó có thể do query thiếu index, ứng dụng phát hành I/O không hiệu quả hoặc VM không đủ CPU/RAM.

## 17. Bài toán lựa chọn đĩa: ba tình huống

### Tình huống A: cổng nội bộ nhỏ

Một VM chạy API, lưu rất ít dữ liệu cục bộ, database được tách sang dịch vụ khác. Dung lượng OS 64 GiB, I/O thấp, ưu tiên chi phí.

**Ứng viên:** Standard SSD OS disk. Cần xem thời gian khởi động, latency thực tế, backup và chỉ nâng lên Premium nếu metric/SLAs cho thấy Standard SSD không đạt.

### Tình huống B: database VM với 700 GiB dữ liệu

Ứng dụng cần 8.000 IOPS, khoảng 120 MiB/s tại giờ cao điểm, chú trọng latency. Dữ liệu không nên để chung OS disk.

**Ứng viên:** Premium SSD data disk hoặc Premium SSD v2 nếu được VM/region hỗ trợ. Chọn VM size có IOPS/throughput dư. Tách data/log và caching theo khuyến nghị của database engine. Bổ sung backup/restore và thiết kế availability.

**Không kết luận** Premium SSD v2 chắc chắn rẻ hoặc nhanh hơn nếu chưa có bảng giá, giới hạn và workload benchmark.

### Tình huống C: hệ thống phân tích dữ liệu rất lớn

Tác vụ cần đọc/ghi tuần tự lớn theo đợt, dung lượng nhiều TB; latency của giao dịch đơn lẻ không phải yếu tố quyết định.

**Ứng viên:** chọn theo throughput và tổng giá, có thể cần nhiều data disks hoặc lưu input/output ở Blob Storage. Ultra Disk chỉ phù hợp khi dữ liệu đo được chứng minh yêu cầu đặc biệt. Nên cân nhắc chuyển workload sang dịch vụ phân tích có managed storage nếu giảm được vận hành VM.

### Mẫu bảng so sánh trước khi quyết định

| Thuộc tính | Phương án 1 | Phương án 2 |
|---|---|---|
| Disk SKU và size | Standard/Premium theo báo giá | Premium SSD v2/Ultra nếu được hỗ trợ |
| VM size và giới hạn I/O | Kiểm tra cụ thể | Kiểm tra cụ thể |
| IOPS sustained | >= nhu cầu + headroom | >= nhu cầu + headroom |
| Throughput sustained | >= nhu cầu + headroom | >= nhu cầu + headroom |
| Latency p95/p99 | Theo benchmark | Theo benchmark |
| Availability/redundancy | LRS/ZRS theo hỗ trợ | LRS/ZRS theo hỗ trợ |
| Backup/restore | Được hỗ trợ và thử nghiệm | Được hỗ trợ và thử nghiệm |
| Chi phí hàng tháng | Đĩa + snapshot + backup + VM | Đĩa + hiệu năng provisioned + backup + VM |

Làm **benchmark trên hệ thống thử nghiệm** với I/O giống production trước khi mua cấu hình lớn. Một benchmark có block size lớn chạy sequential không mô phỏng chính xác database 8 KiB random writes.

## 18. Chi phí: không chỉ tiền dung lượng

Managed disk thường phát sinh chi phí dựa trên loại disk, dung lượng provisioned và các tham số hiệu năng theo mô hình SKU. Với một số loại disk, IOPS/throughput provisioned là yếu tố tính giá riêng. Ngoài ra có thể có chi phí snapshot, backup, redundancy hoặc các giao dịch theo chính sách dịch vụ.

### Những khoản dễ bị bỏ quên

- Data disk **unattached** vẫn tồn tại và có thể tiếp tục tính phí.
- Snapshot cũ, disk copy và test restore chưa dọn.
- Disk provisioned quá lớn chỉ để đạt IOPS/throughput cao, dù dữ liệu thực ít.
- Premium SSD v2/Ultra được cấu hình IOPS/throughput cao hơn nhu cầu dài hạn.
- VM size lớn chỉ để đạt disk throughput nhưng CPU/RAM không được sử dụng.
- Chi phí replication, backup và phục hồi khác region.
- Chi phí duy trì máy dự phòng, license/phần mềm và công cụ giám sát.

### Quy trình tối ưu

1. Đặt **tag** cho owner, environment và purpose.
2. Dùng Azure Cost Management để xem disk/VM cost theo resource group.
3. So nhu cầu thực với giới hạn disk và VM, xác định phần dự phòng hợp lý.
4. Cân nhắc điều chỉnh SKU/performance có kiểm soát sau khi benchmark.
5. Xem danh sách disk không gắn VM và snapshot hết vòng đời.
6. Đặt cảnh báo ngân sách, nhưng nhớ budget alert **không tự dừng phát sinh phí**.
7. Kiểm tra chi phí sau mỗi lần thử nghiệm và dọn tài nguyên lab.

## 19. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thể chọn Premium SSD v2 hoặc Ultra | VM size, region, zone, SKU hoặc cấu hình không hỗ trợ | Đối chiếu ma trận hỗ trợ; chọn VM/SKU/zone phù hợp |
| Đĩa mới gắn nhưng không thấy trong file explorer | Chưa initialize/partition/format/mount ở guest OS | Kiểm tra Disk Management/lsblk; chỉ format disk chắc chắn mới |
| Đĩa hiển thị nhưng ứng dụng không ghi được | Permission filesystem, mount read-only hoặc disk full | Kiểm tra OS logs, filesystem, quyền và dung lượng |
| Mua đĩa nhiều IOPS nhưng VM vẫn chậm | Chạm giới hạn IOPS/throughput của VM hoặc nút thắt app | Đo cả VM/disk metrics và benchmark ứng dụng |
| Latency database cao dù IOPS chưa chạm trần | Query/index, queue, caching, network hoặc độ trễ I/O | Đo p95/p99, queue và kiểm tra engine |
| Disk không attach vào VM khác zone | Khác region/zone hoặc kiểu disk không cho attach như vậy | Xác nhận tính tương thích và phương án snapshot/copy/DR |
| Thay đổi disk size nhưng filesystem chưa tăng | Guest partition/filesystem chưa được mở rộng | Dùng quy trình resize guest OS có backup |
| Xóa VM nhưng còn disk bị tính tiền | Delete option đã giữ disk hoặc disk không tự xóa | Kiểm tra unattached disk và chính sách giữ dữ liệu trước khi dọn |
| Disk đã detach nhưng thao tác xóa thất bại | Disk vẫn có trạng thái/resource dependency hoặc quyền RBAC | Kiểm tra managedBy/diskState và role |
| VM restart nhưng dữ liệu scratch biến mất | Đã lưu lên temporary disk/ephemeral OS storage | Chuyển dữ liệu bền vững sang managed disk hoặc managed service |
| Backup không thành công với disk SKU mới | Tính năng chưa hỗ trợ hoặc cấu hình không đáp ứng điều kiện | Đối chiếu ma trận Azure Backup và disk support |
| Dữ liệu được mã hóa nhưng mất khả năng truy cập | Vấn đề CMK/Key Vault permissions hoặc khóa bị vô hiệu hóa | Kiểm tra key availability, DES, identity và khôi phục khóa |
| Có LRS/ZRS mà vẫn mất dữ liệu logic | Xóa/ghi đè nhầm được lưu lại trên replicas | Cấu hình backup/retention và thử restore |

Khi báo lỗi, thu thập **VM size, disk SKU, disk resource ID, zone/region, IOPS/throughput, metrics, OS logs và thay đổi gần nhất**. Không đưa credential/secret vào ticket hoặc log.

## 20. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập 1: chọn loại đĩa

Với ba workload dưới đây, lập bảng đề xuất disk SKU và lý do:

1. Web server nội bộ, OS 64 GiB, 500 IOPS, dữ liệu nằm trong Azure SQL Database.
2. VM chạy database giao dịch 800 GiB, 12.000 IOPS giờ cao điểm, average I/O 16 KiB, cần latency thấp.
3. Máy xử lý video batch đọc và ghi hàng trăm GiB theo đợt, phần lớn dữ liệu có thể tái tạo.

Với workload 2, tính throughput sơ bộ:

~~~text
12.000 I/O/s × 16 KiB/I/O = 192.000 KiB/s
192.000 / 1.024 = 187,5 MiB/s
~~~

Sau đó kiểm tra **VM max uncached IOPS/throughput**, yêu cầu latency, region/zone và chi phí trước khi chốt SKU.

### Bài tập 2: thiết kế an toàn

Một VM chứa database cần backup hằng ngày, có khả năng khôi phục khi xóa nhầm dữ liệu và phục hồi trong thời hạn do doanh nghiệp quy định. Hãy xác định:

- OS disk và data disk cần tách như thế nào?
- Snapshot/backup nào tạo được điểm phục hồi đúng yêu cầu?
- Làm sao kiểm tra transaction consistency và thử restore?
- Có cần region dự phòng không? Nếu có, RPO/RTO nào phù hợp?
- Ai được phép export/delete disk và thay đổi encryption key?

### Câu hỏi tự kiểm tra

1. Managed disk khác temporary disk ở điểm nào?
2. Vì sao Premium SSD v2 và Ultra Disk không nên được chọn làm OS disk?
3. IOPS, throughput và latency liên hệ với nhau như thế nào?
4. Nếu disk hỗ trợ nhiều IOPS nhưng VM không đủ uncached throughput, chuyện gì xảy ra?
5. Khi nào host caching giúp ích và vì sao phải thận trọng với database?
6. Disk bursting có thể thay thế việc sizing cho tải liên tục không?
7. Vì sao ZRS không thay kế hoạch DR đa region?
8. Snapshot của một disk database đang chạy có luôn application-consistent không?
9. Azure Disk Encryption có giống SSE/CMK mặc định không?
10. Vì sao tách disk khỏi VM không đồng nghĩa ngừng tính phí?
11. Khi data disk mới không xuất hiện như một thư mục trong Linux, bước nào còn thiếu?
12. Bạn sẽ chọn Standard SSD, Premium SSD hay Ultra khi chưa có số liệu tải? Vì sao?

## 21. Checklist trước production

- [ ] Có workload profile: capacity, IOPS, throughput, read/write ratio, block size và latency SLO.
- [ ] Đã xác nhận VM size hỗ trợ disk SKU, số lượng disk, region/zone và giới hạn I/O.
- [ ] OS disk, data disk và temporary storage được dùng đúng chức năng.
- [ ] Disk size/tier và IOPS/throughput có headroom phù hợp, không chỉ dựa vào burst.
- [ ] Host caching phù hợp với hướng dẫn workload và loại disk.
- [ ] Có kế hoạch backup, retention, restore test và DR theo RPO/RTO.
- [ ] LRS/ZRS và Availability Zones được chọn theo tính năng hỗ trợ, không nhầm với cross-region replication.
- [ ] SSE/CMK, quyền quản lý khóa, RBAC và audit đáp ứng chính sách.
- [ ] Disk deletion options, tags, owner và quy trình cleanup được xác định.
- [ ] Giám sát cả VM-level và disk-level limits; có cảnh báo latency và disk space.
- [ ] Đã thử tăng dung lượng/mount/restore trên môi trường không quan trọng.
- [ ] Đã tính chi phí disk, VM, snapshots, backup và tài nguyên không gắn VM.

## 22. Tài liệu tham khảo

- [Introduction to Azure managed disks](https://learn.microsoft.com/azure/virtual-machines/managed-disks-overview) — mô hình managed disk, SKU và tính năng.
- [Select a disk type for Azure IaaS VMs](https://learn.microsoft.com/azure/virtual-machines/disks-types) — Standard HDD/SSD, Premium SSD, Premium SSD v2 và Ultra Disk.
- [Azure VM disk performance](https://learn.microsoft.com/azure/virtual-machines/disks-performance) — cách đánh giá IOPS, throughput và VM/disk limits.
- [Disk caching for Azure virtual machines](https://learn.microsoft.com/azure/virtual-machines/premium-storage-performance#disk-caching) — caching và các lưu ý hiệu năng.
- [Azure managed disk encryption](https://learn.microsoft.com/azure/virtual-machines/disk-encryption) — mã hóa và quản lý khóa.
- [Azure Backup for Azure virtual machines](https://learn.microsoft.com/azure/backup/backup-azure-vms-introduction) — backup và phục hồi VM.
- [Azure CLI: az disk](https://learn.microsoft.com/cli/azure/disk) — tạo, đọc, cập nhật và xóa disk.
- [Azure CLI: az vm disk](https://learn.microsoft.com/cli/azure/vm/disk) — attach/detach và quản lý VM data disks.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — ước tính chi phí disk/VM ở region đã chọn.

**Kết luận:** Lựa chọn managed disk cho Azure VM phải xuất phát từ **kiểu I/O, giới hạn VM, yêu cầu latency, mục tiêu phục hồi và tổng chi phí**, không chỉ dung lượng hoặc tên SKU. Với phần lớn ứng dụng, hãy đo trước trên Standard SSD/Premium SSD; chỉ chuyển sang Premium SSD v2/Ultra khi workload và khả năng hỗ trợ thật sự đòi hỏi. Dù dùng loại disk nào, lưu dữ liệu quan trọng trên nơi bền vững, cấu hình backup/restore, giới hạn quyền thao tác và thường xuyên kiểm tra khả năng phục hồi.

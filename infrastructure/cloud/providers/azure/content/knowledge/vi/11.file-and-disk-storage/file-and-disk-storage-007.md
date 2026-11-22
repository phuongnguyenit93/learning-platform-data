# OS disk, data disk và temporary disk

## 1. Tại sao phải phân biệt ba loại đĩa trên Azure VM?

Khi triển khai máy ảo (Virtual Machine, VM) trên Microsoft Azure, người học thường nhìn thấy nhiều ổ đĩa trong hệ điều hành. Trên Windows có thể có ổ **C:** và **D:**; trên Linux có thiết bị chứa phân vùng gốc **/**, một hoặc nhiều thiết bị dữ liệu, cùng một vùng lưu trữ tạm. Chúng không giống nhau về mục đích, khả năng lưu dữ liệu, cách quản lý và chi phí.

Một nhầm lẫn nguy hiểm là lưu database hoặc file người dùng trên **temporary disk**, sau đó thực hiện thao tác khiến VM chuyển sang host khác và mất dữ liệu. Một nhầm lẫn khác là nghĩ rằng tắt VM sẽ xóa mọi dữ liệu trên **data disk**. Hiểu vòng đời lưu trữ là điều kiện cần trước khi triển khai ứng dụng có trạng thái.

Bài học thuộc phần **Lưu trữ tệp và đĩa** trong hệ sinh thái Azure, liên hệ trực tiếp đến vận hành VM, mạng, dữ liệu, bảo mật, giám sát và kiểm soát chi phí. Sau bài học, bạn có thể:

1. Phân biệt **OS disk**, **data disk** và **temporary disk** về chức năng và độ bền dữ liệu.
2. Hiểu **managed disk** và sự khác biệt giữa OS disk thông thường với **ephemeral OS disk**.
3. Chọn SKU, dung lượng và hiệu năng đĩa theo đặc tính ứng dụng.
4. Gắn data disk vào VM rồi khởi tạo, phân vùng, định dạng và mount đúng cách trên Linux/Windows.
5. Xác định chỗ nào được phép lưu cache, swap, file trung gian và chỗ nào bắt buộc có backup.
6. Giải thích dữ liệu còn hay mất khi reboot, stop/deallocate, resize, redeploy hoặc xóa VM.
7. Áp dụng các nguyên tắc backup, mã hóa, phân quyền, giám sát và quản lý chi phí.

## 2. Nhìn toàn cảnh cấu trúc đĩa của một máy ảo

Azure VM kết hợp năng lực tính toán với các tài nguyên lưu trữ khác nhau. Trong cấu hình phổ biến, **OS disk** và **data disk** là các Azure Managed Disk; **temporary disk** thường là bộ nhớ cục bộ của host chạy VM, nếu VM size được chọn có cung cấp.

~~~mermaid
flowchart TB
    VM[Azure Virtual Machine]
    VM --> OS[OS disk: hệ điều hành và boot]
    VM --> D1[Data disk 0: dữ liệu ứng dụng]
    VM --> D2[Data disk 1: dữ liệu bổ sung]
    VM --> T[Temporary / local disk: dữ liệu có thể mất]
    OS --> MD[Managed Disk storage]
    D1 --> MD
    D2 --> MD
    T --> HOST[Local storage trên host]
~~~

Sơ đồ là mô hình khái niệm. Một VM có thể không có temporary disk; một số VM còn hỗ trợ **ephemeral OS disk** lưu hệ điều hành trên vùng local phù hợp thay vì dùng một OS managed disk bền vững riêng. Cách ánh xạ thiết bị thành tên ổ trong Windows hoặc Linux cũng phụ thuộc VM size, controller, image và cấu hình khách.

### 2.1. Bảng so sánh nhanh

| Tiêu chí | OS disk thông thường | Data disk thông thường | Temporary disk |
|---|---|---|---|
| Vai trò | Chứa hệ điều hành, file boot, công cụ hệ thống | Chứa dữ liệu hoặc ứng dụng cần tồn tại lâu dài | Chứa dữ liệu tạm, có thể tái tạo |
| Nguồn lưu trữ điển hình | Azure Managed Disk | Azure Managed Disk | Bộ nhớ local của host VM |
| Dữ liệu khi VM stop/deallocate | Thường vẫn còn nếu disk không bị xóa | Thường vẫn còn nếu disk không bị xóa | Không được bảo đảm, có thể mất |
| Dữ liệu khi chuyển VM sang host khác | Managed disk thường được gắn lại | Managed disk thường được gắn lại | Có thể bị thay thế hoặc xóa |
| Có thể quản lý như disk Azure độc lập | Có, với OS managed disk | Có | Không như một managed disk thông thường |
| Phù hợp cho | Hệ điều hành, cấu hình VM | Database, ứng dụng có trạng thái, tệp lâu dài | Cache, scratch, temp files, dữ liệu tái tạo được |
| Backup | Nên dùng Azure Backup/giải pháp phù hợp | Nên backup theo yêu cầu RPO/RTO | Không coi đây là nơi chứa dữ liệu cần backup để phục hồi |
| Chi phí | Có thể phát sinh chi phí managed disk | Có chi phí theo SKU/dung lượng/đặc tính | Thường gắn với VM size, không phải đĩa managed tính riêng |

**Quy tắc nhớ:** dữ liệu **không được phép mất** phải nằm ở một giải pháp lưu trữ bền vững có backup và khả năng phục hồi phù hợp. Đừng dựa vào tên ổ như **D:** hoặc **/dev/sdb** để quyết định dữ liệu có bền vững hay không.

## 3. OS disk: đĩa khởi động hệ điều hành

**OS disk (operating system disk)** chứa hệ điều hành cần thiết để máy ảo khởi động. Nó thường được tạo khi bạn triển khai VM từ image Windows hoặc Linux.

Các thành phần có thể nằm trên OS disk:

- Bootloader, hệ thống file gốc và các thành phần hệ điều hành.
- Cấu hình dịch vụ, package, agent và file thiết lập của máy.
- Trên Windows, thường chứa phân vùng hệ thống **C:**.
- Trên Linux, thường chứa hệ thống file **/** và các phân vùng boot thích hợp.

Khi bạn cài phần mềm trực tiếp lên máy ảo mà không chọn vị trí khác, dữ liệu có thể được ghi lên OS disk. Ví dụ, log ứng dụng hoặc thư mục upload đặt dưới phân vùng hệ điều hành có thể làm đầy ổ, khiến hệ điều hành hoặc ứng dụng hoạt động không ổn định.

### 3.1. OS managed disk là tài nguyên lưu trữ bền vững

Trong mô hình managed disk phổ biến, OS disk được lưu trên hạ tầng Azure Disk Storage chứ không phụ thuộc vào bộ nhớ tạm của một host tính toán duy nhất. Khi VM bị dừng và giải phóng tài nguyên tính toán, OS managed disk **không tự mất dữ liệu** chỉ vì VM deallocate, miễn disk không bị xóa bởi thao tác hoặc chính sách quản lý.

Điều này **không** có nghĩa OS disk tự động là backup. Lỡ xóa file, ghi đè cấu hình, bị mã độc mã hóa hoặc xóa nhầm managed disk vẫn có thể gây mất dữ liệu. Cần cơ chế backup/khôi phục độc lập.

### 3.2. Một VM thường có một OS disk

Một VM đang hoạt động có một OS disk dùng để boot. Khi thay OS disk, tạo VM từ disk đã có hoặc thực hiện tác vụ khôi phục, cần tuân theo giới hạn trạng thái VM, cấu hình hệ điều hành và loại image. Không được coi việc thay đĩa boot như thao tác tháo một ổ USB đang chạy.

### 3.3. OS disk có cần chứa dữ liệu ứng dụng?

Về kỹ thuật, ứng dụng vẫn có thể ghi dữ liệu lên phân vùng OS. Tuy nhiên, với hệ thống vận hành lâu dài nên cân nhắc tách **data disk** hoặc dịch vụ lưu trữ chuyên dụng vì:

- Dễ theo dõi dung lượng hệ điều hành và dung lượng dữ liệu riêng.
- Giảm nguy cơ hệ điều hành hết chỗ vì log, file upload hoặc database.
- Hỗ trợ quy trình sao lưu và quản lý vòng đời dữ liệu rõ ràng.
- Dễ thay thế, tái tạo hoặc nâng cấp máy ảo mà không phụ thuộc toàn bộ dữ liệu vào disk boot.

Dù vậy, không nên tách mọi thư mục một cách máy móc. Hệ thống đơn giản có thể sử dụng OS disk với backup phù hợp; quyết định phải dựa trên RPO/RTO, lưu lượng, chi phí và mức phức tạp chấp nhận được.

## 4. Cẩn thận: ephemeral OS disk không phải OS managed disk thông thường

Azure hỗ trợ **ephemeral OS disk** trên các VM size và cấu hình đủ điều kiện. Nó đặt OS disk lên vùng lưu trữ local phù hợp của máy chủ thay vì tạo một OS managed disk bền vững riêng theo mô hình truyền thống.

Tính chất đáng chú ý:

- Có thể giúp nhanh hơn ở một số quy trình tạo hoặc tái tạo VM, đặc biệt với workload **stateless**.
- Hệ điều hành được xem là **có thể tái tạo từ image**; dữ liệu ghi trên OS disk không được coi là bền vững qua các sự kiện vòng đời nhất định như reimage, deallocate hoặc thay host.
- Phù hợp với một số VM Scale Sets, pool xử lý tạm, worker hoặc môi trường mà việc dựng máy mới là bình thường.
- Không phù hợp nếu chỉ có một bản dữ liệu quan trọng nằm trên OS disk.
- Khả năng hỗ trợ và kích thước phụ thuộc VM size, chỗ chứa local OS disk, image và những giới hạn Azure hiện hành.

**Ephemeral OS disk khác temporary disk.** Cả hai có thể dùng storage local, nhưng một loại làm **đĩa boot hệ điều hành**, loại còn lại làm **vùng lưu dữ liệu tạm**. Chúng có vai trò và chính sách vòng đời khác nhau.

Khi thiết kế một máy ảo có trạng thái, hãy xác nhận cụ thể OS disk đang là **managed OS disk bền vững** hay **ephemeral OS disk**. Không suy luận chỉ từ tên ổ xuất hiện trong hệ điều hành.

## 5. Data disk: không gian lưu trữ bền vững cho ứng dụng

**Data disk** là đĩa bổ sung được gắn vào VM để lưu file, database, log, dữ liệu ứng dụng hoặc những nội dung cần quản lý độc lập với hệ điều hành.

Một Azure Managed Data Disk có thể:

- Được tạo riêng rồi gắn vào VM.
- Được gắn hoặc tháo theo quy trình hỗ trợ, không nhất thiết có cùng vòng đời xóa như VM.
- Có dung lượng, SKU, đặc điểm hiệu năng và chế độ cache riêng.
- Được phân vùng và định dạng bằng hệ điều hành khách.
- Được backup hoặc snapshot theo chính sách ứng dụng.

Số lượng data disk tối đa và tổng thông lượng/IOPS của VM phụ thuộc vào kích thước VM, bus/controller và hạ tầng được hỗ trợ. Không giả định muốn gắn bao nhiêu đĩa cũng được.

### 5.1. Data disk mới thường chưa sẵn sàng lưu file

Khi bạn gắn một managed disk **mới tinh** vào VM, hệ điều hành có thể nhìn thấy thiết bị nhưng chưa có partition, filesystem hoặc drive letter/mount point.

Vì vậy, cần thực hiện:

1. Xác định đúng thiết bị mới.
2. Khởi tạo partition table khi cần.
3. Tạo partition và filesystem theo hệ điều hành.
4. Mount hoặc cấp drive letter.
5. Kiểm tra quyền truy cập và tính ổn định sau reboot.
6. Cấu hình theo dõi dung lượng, hiệu năng và backup.

**Nếu gắn một disk đã có dữ liệu, tuyệt đối không format lại.** Chỉ kiểm tra filesystem và mount theo cấu hình phù hợp. Việc format sẽ ghi đè cấu trúc lưu trữ cũ và có thể gây mất dữ liệu.

### 5.2. Logical Unit Number (LUN)

Trong mô hình dùng SCSI, mỗi data disk gắn vào VM thường được chỉ định một **LUN**, ví dụ 0, 1, 2. Azure sử dụng LUN để phân biệt các disk được gắn. LUN không phải thứ tự ổ đĩa **C:**, **D:**, **E:** của Windows; cũng không đồng nghĩa chắc chắn với tên thiết bị **/dev/sdc** hay **/dev/sdd** trên Linux.

Một số VM thế hệ mới dùng NVMe cho đường dữ liệu, nên cách nhận diện thiết bị có thể khác mô hình SCSI truyền thống. Khi làm việc với hệ thống thật, hãy đối chiếu **Azure disk resource ID/LUN, dung lượng, serial và thông tin hệ điều hành** thay vì tin vào một ký tự tên thiết bị.

## 6. Temporary disk: vùng nhớ cục bộ có thể bị mất dữ liệu

**Temporary disk**, còn được gọi trong một số tài liệu là **resource disk** hoặc **local temporary storage**, là vùng lưu trữ gắn với máy chủ vật lý đang chạy VM. Nó có thể có tốc độ tốt cho một số workload nhưng **không được đảm bảo dữ liệu lâu dài**.

Trên nhiều VM Windows, temporary disk thường có ký tự ổ **D:** và có thể được dùng để chứa pagefile. Trên một số image Linux, vùng này có thể được mount ở **/mnt**, **/mnt/resource** hoặc vị trí khác. Một số VM family cung cấp local NVMe, một số VM size không có temporary disk. Vì vậy, ký tự ổ và mount point chỉ là dấu hiệu tham khảo.

Những loại dữ liệu **có thể** đặt trên temporary disk nếu ứng dụng chịu được việc mất hoàn toàn:

- Cache có thể dựng lại từ nguồn bền vững.
- File scratch phục vụ quá trình xử lý ngắn hạn.
- File download tạm trong khi chuyển đổi dữ liệu.
- Dữ liệu trung gian của batch job có thể chạy lại.
- Một số loại swap/pagefile theo cấu hình hệ điều hành và hướng dẫn VM image.

Những loại dữ liệu **không nên** đặt duy nhất trên temporary disk:

- Database chính hoặc transaction log quan trọng.
- File upload của người dùng chưa được ghi bền vững ở nơi khác.
- Secret, private key, chứng thư hoặc cấu hình không thể tái tạo.
- Bản backup duy nhất của hệ thống.
- Thông tin phiên quan trọng không có cơ chế đồng bộ/khôi phục.
- Những file cần tồn tại sau khi VM chuyển host hoặc được tái tạo.

**Nguyên tắc vận hành:** mỗi lần ghi dữ liệu xuống temporary disk, tự hỏi “nếu toàn bộ vùng này biến mất ngay bây giờ, ứng dụng còn hoạt động và khôi phục đúng được không?”. Nếu câu trả lời là **không**, nơi lưu trữ đó không phù hợp.

## 7. Điều gì xảy ra với dữ liệu khi VM đổi trạng thái?

Không phải mọi thao tác vòng đời VM đều có hậu quả giống nhau. Bảng sau mô tả **nguyên tắc thiết kế an toàn**, không phải cam kết các bytes luôn giữ nguyên trong mọi trường hợp.

| Tình huống | OS managed disk thông thường | Managed data disk | Temporary disk |
|---|---|---|---|
| Reboot bên trong hệ điều hành | Thông thường được giữ | Thông thường được giữ | Có thể vẫn còn trong nhiều trường hợp, **không được dựa vào đó** |
| Stop/deallocate VM | Còn nếu không bị xóa | Còn nếu không bị xóa | Có thể bị mất/khởi tạo lại |
| Resize VM | Managed disk vẫn là tài nguyên độc lập nếu không bị xóa | Managed disk vẫn là tài nguyên độc lập nếu không bị xóa | Có thể mất khi thay host |
| Redeploy sang host khác | Gắn lại hoặc phục hồi theo cơ chế quản lý | Gắn lại theo cơ chế quản lý | Có thể mất hoàn toàn |
| Host maintenance/failure | Phụ thuộc cơ chế lưu trữ và khả năng phục hồi | Phụ thuộc cơ chế lưu trữ và khả năng phục hồi | Không có bảo đảm giữ lại nội dung |
| Xóa VM | Phụ thuộc **delete option** và thao tác xóa disk | Phụ thuộc **delete option** và thao tác xóa disk | Không tồn tại như disk độc lập để giữ lại |

**Không được mặc định “xóa VM thì managed disk chắc chắn còn”.** Azure VM có thuộc tính **delete option** cho OS disk và các data disk: chẳng hạn xóa cùng VM hoặc detach/giữ lại theo cấu hình. Hãy kiểm tra trước khi xóa để tránh mất dữ liệu hoặc tạo tài nguyên mồ côi gây chi phí.

Đối với **ephemeral OS disk**, vòng đời khác OS managed disk. Nó được thiết kế để khởi tạo lại từ image khi xảy ra những sự kiện tương ứng; không nên dựa vào thay đổi trên OS disk này như dữ liệu lâu dài.

### 7.1. Stop và deallocate không giống nhau về chi phí VM

Một lệnh tắt máy từ trong guest OS có thể không đồng nghĩa tài nguyên tính toán Azure đã được **deallocated**. Khi cần dừng tính phí compute, phải xác nhận trạng thái VM thực tế trong Azure. Dù compute đã deallocate, **managed disks và một số tài nguyên liên quan vẫn có thể phát sinh chi phí**.

Đừng thử làm mất dữ liệu temporary disk trên hệ thống thật để “kiểm chứng”; chỉ thực hiện trong lab riêng và với dữ liệu giả có thể xóa.

## 8. Chọn loại Azure Managed Disk

Managed disks có nhiều SKU được thiết kế cho yêu cầu độ trễ, IOPS, thông lượng và chi phí khác nhau.

| Nhóm đĩa | Đặc trưng tổng quát | Nhu cầu điển hình |
|---|---|---|
| **Standard HDD** | Chi phí thấp hơn, hiệu năng thấp hơn, lưu trữ dạng HDD | Tải nhẹ, ít truy cập, môi trường không nhạy độ trễ |
| **Standard SSD** | SSD cân bằng chi phí và hiệu năng | Ứng dụng phổ thông, môi trường dev/test |
| **Premium SSD** | SSD cho workload yêu cầu hiệu năng cao hơn, mức hiệu năng theo cấu hình/dung lượng | Máy chủ ứng dụng, database, sản xuất |
| **Premium SSD v2** | Đặt dung lượng và mức hiệu năng độc lập hơn trong phạm vi hỗ trợ | Data disk có yêu cầu IOPS/throughput linh hoạt |
| **Ultra Disk** | Cấu hình hiệu năng cao trong phạm vi tính năng/SKU hỗ trợ | Workload rất nhạy hiệu năng I/O |

Tùy loại SKU, không phải disk nào cũng được sử dụng làm **OS disk**. Ví dụ, các lựa chọn như **Premium SSD v2** hoặc **Ultra Disk** được định hướng cho data disk, với yêu cầu hỗ trợ theo region/VM size; không nên chọn chúng làm đĩa boot khi sản phẩm không hỗ trợ.

Thông số thực tế cần xác minh từ tài liệu sản phẩm và lựa chọn ở thời điểm triển khai:

- Dung lượng tối thiểu, tối đa, bước tăng dung lượng.
- IOPS và throughput được cấp theo size/SKU hoặc mức cấu hình.
- Khả năng bursting.
- Mức độ hỗ trợ Availability Zones, redundancy và shared disk.
- Hỗ trợ host caching, snapshots, backup, encryption và online resize.
- Giới hạn tổng I/O của VM size đang sử dụng.

### 8.1. Hiệu năng không chỉ do mỗi đĩa

Thông lượng ứng dụng bị giới hạn bởi **cả disk lẫn VM**. Ví dụ, data disk có thể có mức IOPS tiềm năng cao, nhưng VM size hoặc bus/controller không đủ khả năng đưa hết lượng I/O đó đến disk.

Cần đo:

1. IOPS từ workload thực tế.
2. Kích thước request đọc/ghi trung bình.
3. Throughput theo MB/s.
4. Độ trễ ở phía ứng dụng và hệ điều hành.
5. Giới hạn disk và giới hạn uncached/cached throughput của VM.
6. Mức CPU và hàng đợi I/O của workload.

Không chọn Premium/Ultra chỉ theo dung lượng file. Một database nhỏ có thể cần IOPS lớn, còn kho file lớn nhưng ít truy cập có thể phù hợp SKU tiết kiệm hơn.

### 8.2. Disk caching

Một số Azure managed disk và VM size hỗ trợ **host caching** như **None**, **ReadOnly** hoặc **ReadWrite**, tùy tổ hợp disk/SKU và loại workload.

- **ReadOnly** có thể giúp một số workload có dữ liệu đọc lặp lại.
- **ReadWrite** cần hiểu rõ yêu cầu nhất quán dữ liệu và hướng dẫn của ứng dụng.
- **None** có thể phù hợp với một số workload ghi nhiều hoặc khi đặc tính dịch vụ yêu cầu.

Không bật caching theo cảm tính cho database. Chế độ hỗ trợ, bộ nhớ cache và khuyến nghị có thể khác giữa OS disk, data disk và các loại SKU. Hãy đối chiếu với hướng dẫn của hệ điều hành, engine dữ liệu và dịch vụ Azure đang dùng.

## 9. Chọn nơi lưu dữ liệu theo tính chất workload

| Dữ liệu | Vị trí gợi ý | Lý do |
|---|---|---|
| Hệ điều hành Windows/Linux | OS disk | Đĩa boot và cấu hình hệ thống |
| Database chạy trong VM | Managed data disk có cấu hình phù hợp | Bền vững, quản lý dung lượng/IOPS và backup độc lập |
| File người dùng cần giữ lâu dài | Managed data disk hoặc Azure Blob/Files tùy ứng dụng | Có thể backup, phân quyền và phục hồi |
| File cache hình ảnh có thể dựng lại | Temporary disk khi VM có hỗ trợ | Tận dụng vùng lưu trữ local, không cần giữ |
| Tệp xử lý trung gian | Temporary disk nếu mất có thể chạy lại | Giảm lệ thuộc vào lưu trữ bền vững cho scratch |
| Log dùng để điều tra và tuân thủ | Managed disk và/hoặc gửi đến hệ thống log tập trung | Không để mất bằng chứng khi VM thay host |
| Bản sao lưu | Azure Backup, Recovery Services vault hoặc giải pháp phù hợp | Tách khỏi vòng đời disk sản xuất |
| Dữ liệu cần dùng từ nhiều VM | Azure Files, Blob, database dịch vụ hoặc shared disk theo điều kiện hỗ trợ | Một data disk thông thường không mặc nhiên là file share đa VM |

**Shared disk** là một tính năng chuyên biệt của những managed disk/SKU hỗ trợ dùng chung ở tầng block cho các hệ thống cluster thích hợp. Việc nhiều máy nhìn thấy cùng một disk **không** tự tạo cơ chế file sharing an toàn. Cần filesystem/cluster manager hỗ trợ chia sẻ hoặc dịch vụ lưu trữ được thiết kế cho nhiều client.

## 10. Ví dụ thiết kế: ứng dụng Java chạy trên Linux VM

Giả sử đội phát triển triển khai một API Java lên Azure Linux VM. API xử lý tệp tải lên, tạo ảnh thumbnail và ghi log.

**Thiết kế ban đầu chưa tốt:**

- Ứng dụng và dữ liệu đều ghi vào partition OS.
- Tệp upload trước khi xử lý được ghi vào temporary disk nhưng chưa có bản bền vững.
- Log chỉ nằm ở temporary disk, nên mất khi VM được redeploy.
- Không có backup data disk hoặc thử phục hồi.

**Thiết kế cải thiện:**

| Thành phần | Nơi lưu trữ | Chính sách |
|---|---|---|
| OS, package và runtime Java | OS managed disk | Cập nhật image và backup theo yêu cầu |
| Cấu hình ứng dụng cần giữ | Hệ thống cấu hình an toàn, có thể kết hợp disk phù hợp | Quản lý cấu hình/version và quyền truy cập |
| Dữ liệu nội bộ cần bền vững | Managed data disk mount tại /data | Backup, monitoring, hạn mức dung lượng |
| File upload người dùng | Azure Blob Storage hoặc Managed Disk theo thiết kế | Đảm bảo ghi bền vững trước khi trả thành công |
| File thumbnail cache | Temporary/local storage | Cho phép xóa và tái tạo từ nguồn gốc |
| Log quan trọng | Azure Monitor/Log Analytics hoặc giải pháp tập trung | Gửi ra ngoài VM để phục vụ điều tra |
| Secret | Azure Key Vault/managed identity nếu phù hợp | Không hardcode hoặc cất duy nhất trên temporary disk |

Hệ thống có thể chuyển sang App Service, containers hoặc các dịch vụ dữ liệu managed về sau, nhưng nguyên tắc **phân biệt bền vững và tạm thời** vẫn không thay đổi.

## 11. Quan sát cấu hình đĩa bằng Azure Portal

Quy trình kiểm tra một Azure VM:

1. Đăng nhập Azure Portal với quyền đọc VM, disk và resource group.
2. Mở **Virtual machines**, chọn VM cần kiểm tra.
3. Vào phần **Disks**.
4. Xác định **OS disk** và danh sách **Data disks**, disk resource, kích thước, SKU và trạng thái đính kèm.
5. Xem **LUN**, host caching và những thiết lập có thể tùy chỉnh.
6. Kiểm tra các lựa chọn vòng đời **Delete with VM / Detach** nếu có.
7. Với tài nguyên disk riêng, xem region, zone, loại SKU, dung lượng và các thuộc tính liên quan.
8. Đối chiếu kết quả với những volume/drive xuất hiện **bên trong VM**.

Temporary disk có thể được nhìn thấy trong hệ điều hành mà **không xuất hiện như một data managed disk độc lập** trong danh sách Azure managed disks. Đây là dấu hiệu quan trọng để tránh format hoặc backup nhầm.

Hãy xác minh VM image/size thực tế hỗ trợ local temporary storage và cách hệ điều hành mount vùng này; không dựa vào giả định mọi Windows VM có D: hoặc mọi Linux VM có /mnt/resource.

## 12. Xem OS disk và data disk bằng Azure CLI

Ví dụ dùng Azure CLI để truy vấn thuộc tính disk của VM đã có. Những lệnh dưới đây **không tự chạy trong bài học**; khi thực hành thay thông tin resource group và VM cho đúng môi trường có quyền.

~~~bash
az login
az account set --subscription "<subscription-id>"

az vm show \
  --resource-group rg-vm-storage-lab \
  --name vm-app-01 \
  --query "storageProfile.{osDisk:osDisk,dataDisks:dataDisks}" \
  --output json
~~~

Thông tin **storageProfile.osDisk** và **storageProfile.dataDisks** cho biết những disk được VM cấu hình. Với managed disk, thường có **managedDisk.id**, **diskSizeGB**, **caching**, cùng các thuộc tính khác tùy cấu hình.

Xem danh sách managed disks thuộc resource group:

~~~bash
az disk list \
  --resource-group rg-vm-storage-lab \
  --query "[].{name:name,sizeGB:diskSizeGB,sku:sku.name,state:diskState,managedBy:managedBy}" \
  --output table
~~~

Xem một data disk cụ thể:

~~~bash
az disk show \
  --resource-group rg-vm-storage-lab \
  --name disk-appdata-01 \
  --query "{name:name,sizeGB:diskSizeGB,sku:sku.name,state:diskState,managedBy:managedBy}" \
  --output json
~~~

**Lưu ý:** data disk được gắn vào VM có thể hiện trạng thái attached và tham chiếu đến VM quản lý. Nhưng từ dữ liệu disk metadata không thể kết luận filesystem bên trong đã được mount, có file gì hoặc ứng dụng có đang sử dụng disk hay không. Muốn biết, phải kiểm tra hệ điều hành guest.

## 13. Tạo và gắn managed data disk bằng Azure CLI

Giả sử bạn có sẵn VM **vm-app-01** trong resource group **rg-vm-storage-lab**. Tạo data disk mới dung lượng 64 GiB với SKU Standard SSD:

~~~bash
az disk create \
  --resource-group rg-vm-storage-lab \
  --name disk-appdata-01 \
  --size-gb 64 \
  --sku StandardSSD_LRS
~~~

Gắn disk vào VM:

~~~bash
az vm disk attach \
  --resource-group rg-vm-storage-lab \
  --vm-name vm-app-01 \
  --name disk-appdata-01 \
  --lun 0
~~~

Kiểm tra lại:

~~~bash
az vm show \
  --resource-group rg-vm-storage-lab \
  --name vm-app-01 \
  --query "storageProfile.dataDisks[].{name:name,lun:lun,sizeGB:diskSizeGB,managedDisk:managedDisk.id}" \
  --output table
~~~

**Điều kiện trước khi chạy:**

- Resource group, VM, khu vực địa lý và disk SKU phải phù hợp với cấu hình được Azure hỗ trợ.
- VM size còn LUN và năng lực I/O cho data disk mới.
- LUN 0 chưa được sử dụng.
- Người thực hiện có quyền thích hợp để tạo disk và thay đổi VM.
- Cấu hình disk và zone phải tương thích với VM.
- Đã hiểu chi phí phát sinh khi tạo managed disk.

Sau lệnh attach, hệ điều hành vẫn có thể thấy một **raw disk** chưa sử dụng được. Cần thực hiện các bước ở Linux hoặc Windows bên dưới.

**Không** dùng ví dụ này để gắn vào VM production rồi format khi chưa được phê duyệt và chưa xác định đích danh disk mới.

## 14. Chuẩn bị data disk trên Linux một cách an toàn

Linux có thể thấy disk theo tên thiết bị như **/dev/sdc**, **/dev/sdd** hoặc **/dev/nvme...**, tùy image và bus. Tên thiết bị **không phải ID cố định tuyệt đối**.

### 14.1. Nhận diện đúng disk

Trong VM Linux, kiểm tra các block devices:

~~~bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,MODEL
sudo blkid
findmnt /
findmnt /data
~~~

So sánh kích thước, tên thiết bị, filesystem và thông tin từ Azure Portal/CLI. Nếu có alias thiết bị ổn định do Azure image cung cấp, cũng nên kiểm tra nó. Trên một số hệ thống SCSI, thư mục **/dev/disk/azure/** có thể chứa liên kết theo LUN; trên hệ NVMe cách biểu diễn có thể khác.

**Dừng lại nếu không chắc thiết bị nào là disk mới.** Không format một thiết bị chỉ vì nó tên **/dev/sdc** trong hướng dẫn.

### 14.2. Tạo filesystem trên disk mới thực sự rỗng

Ví dụ giả sử quản trị viên đã xác minh một thiết bị mới hoàn toàn không chứa dữ liệu. Thay placeholder bằng thiết bị được xác định chắc chắn:

~~~bash
# CHI CHAY TREN DATA DISK MOI DA XAC MINH KHONG CO DU LIEU
sudo mkfs.ext4 /dev/<confirmed-new-data-device>

sudo mkdir -p /data
sudo mount /dev/<confirmed-new-data-device> /data

findmnt /data
df -h /data
~~~

Trong tình huống cần partition table, hãy tạo partition trước bằng công cụ thích hợp và format **partition** đã tạo, không format nhầm toàn bộ thiết bị. Ví dụ trên minh họa filesystem trực tiếp trên block device để dễ hiểu; môi trường vận hành thực tế có thể chọn GPT, LVM, RAID hoặc các giải pháp quản lý volume khác.

**Cảnh báo mất dữ liệu:** lệnh **mkfs.ext4** tạo filesystem và có thể phá hủy cấu trúc dữ liệu đang có. Không copy nguyên lệnh nếu chưa xác minh disk mới, tình trạng dữ liệu, LUN và đường dẫn thiết bị.

### 14.3. Mount tự động sau reboot

Chỉ mount thủ công có thể khiến volume không được gắn lại sau reboot. Trên Linux, thường dùng **/etc/fstab** với filesystem UUID:

~~~bash
sudo blkid /dev/<confirmed-new-data-device>
~~~

Một dòng ví dụ trong **/etc/fstab**:

~~~text
UUID=<uuid-from-blkid> /data ext4 defaults,nofail 0 2
~~~

Thay UUID thật của filesystem và kiểm tra cấu hình trước khi reboot. Dùng UUID ổn định hơn so với cố định **/dev/sdc**, vì tên thiết bị có thể đổi sau thao tác hạ tầng.

Sau khi lưu file, thử kiểm tra mount:

~~~bash
sudo mount -a
findmnt /data
df -h /data
~~~

Nếu cấu hình filesystem hoặc mount option sai, máy có thể gặp vấn đề khi khởi động; vì vậy chỉ sửa **/etc/fstab** khi hiểu đường dẫn, UUID và chế độ phục hồi. **nofail** có thể cho phép máy khởi động dù volume không sẵn sàng, nhưng ứng dụng phụ thuộc dữ liệu vẫn phải có kiểm tra riêng để tránh ghi nhầm lên thư mục rỗng của OS disk.

### 14.4. Phân quyền và tổ chức thư mục

Sau khi mount, tạo thư mục ứng dụng và thiết lập owner/quyền truy cập phù hợp:

~~~bash
sudo mkdir -p /data/app
sudo ls -ld /data /data/app
~~~

Không dùng **chmod 777** như giải pháp mặc định. Thiết lập user/group cần thiết cho process ứng dụng, cân nhắc ACL và chính sách bảo mật trong VM.

## 15. Chuẩn bị data disk trên Windows

Trên Windows VM, dùng **Disk Management** hoặc PowerShell để xác định disk mới.

### 15.1. Kiểm tra disk đang có

Mở PowerShell với quyền phù hợp:

~~~powershell
Get-Disk | Format-Table Number, FriendlyName, OperationalStatus, PartitionStyle, Size
Get-Volume | Format-Table DriveLetter, FileSystemLabel, FileSystem, Size
~~~

So sánh disk number, dung lượng và trạng thái với data disk vừa attach. Một disk mới có thể ở trạng thái **RAW** hoặc **Offline** tùy môi trường. Không coi **Disk 1** hay **D:** luôn là data disk vừa tạo.

### 15.2. Khởi tạo disk mới

Chỉ khi đã xác nhận rõ **disk number** thuộc data disk mới, chưa có dữ liệu và không phải OS/temporary disk, có thể thực hiện:

~~~powershell
# Thay N bang so disk moi da xac minh; khong chay neu disk co du lieu.
Initialize-Disk -Number N -PartitionStyle GPT

$partition = New-Partition -DiskNumber N -UseMaximumSize -AssignDriveLetter
$partition | Format-Volume -FileSystem NTFS -NewFileSystemLabel AppData
~~~

Các lệnh này có thể thay đổi metadata của disk. Không chạy trong production nếu không có phê duyệt, backup và xác nhận chính xác disk cần thao tác. Nếu disk đã chứa NTFS/ReFS hoặc dữ liệu ứng dụng, cần mount/assign drive letter theo quy trình mà **không initialize/format lại**.

Sau khi có volume mới, ứng dụng có thể dùng thư mục như **E:\\AppData** hoặc một đường dẫn được chọn. Không giả định E: luôn có sẵn; Windows có thể tự cấp drive letter khác.

### 15.3. Không dùng nhầm ổ D:

Ở nhiều Azure Windows VM, ổ D: thường là **temporary disk**, có thể chứa pagefile hoặc thư mục tạm. Nếu quản trị viên format hoặc chuyển database vào D: vì nghĩ đó là managed data disk, rủi ro mất dữ liệu rất lớn.

Hãy xác nhận disk backing thông qua Portal, Disk Management và thông tin Azure VM trước khi chọn ổ lưu dữ liệu quan trọng.

## 16. Temporary disk trên Linux và Windows: sử dụng đúng

### 16.1. Linux

Một số Linux VM image tự mount resource disk vào **/mnt** hoặc **/mnt/resource**. Trước khi sử dụng, hãy kiểm tra:

~~~bash
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT
findmnt /mnt
findmnt /mnt/resource
df -h
~~~

Nếu không có temporary disk, các đường dẫn đó có thể không tồn tại hoặc chỉ là thư mục trên OS disk. Đừng tạo cache ở một đường dẫn rồi mặc định nó tự động nằm trên local temporary storage.

Ví dụ ứng dụng đặt dữ liệu cache tại vùng local tạm đã được xác minh:

~~~text
/tmp/job-cache
/mnt/resource/app-cache
~~~

Đây chỉ là ví dụ; vị trí đúng phụ thuộc image và cấu hình. Ứng dụng phải có bước tạo lại thư mục cache, kiểm tra quyền và xử lý trường hợp vùng local không có sẵn.

### 16.2. Windows

Trên một số Azure Windows VM, temporary storage xuất hiện dưới ổ **D:**. Nhưng đó **không phải quy tắc áp dụng cho mọi VM**; drive letter và volume có thể được cấu hình khác.

Kiểm tra qua Disk Management/PowerShell, tài liệu VM size và thông tin thiết bị. Không xóa pagefile hoặc đổi cách phân vùng ổ tạm khi chưa hiểu ảnh hưởng tới hệ điều hành.

### 16.3. Thiết kế ứng dụng chịu được mất cache

Một luồng an toàn:

1. Lưu dữ liệu gốc ở managed disk hoặc dịch vụ bền vững, ví dụ Blob Storage.
2. Ghi bản sao/thumbnail cache vào vùng tạm.
3. Khi truy cập cache, kiểm tra xem tệp còn tồn tại không.
4. Nếu cache mất, tái tạo từ nguồn gốc.
5. Dùng timeout và giới hạn dung lượng để cache không làm đầy ổ local.
6. Không trả thành công với một file upload quan trọng nếu file mới chỉ tồn tại ở temporary disk.

Vùng local có thể nhanh, nhưng mục tiêu chính của nó là **dữ liệu có thể tái tạo**, không phải nơi lưu trữ lâu dài.

## 17. Mở rộng dung lượng và điều chỉnh data disk

Khi dung lượng managed disk không đủ, có thể cần tăng kích thước disk hoặc bổ sung disk mới.

Quy trình tổng quát:

1. Kiểm tra **dung lượng đã cấp** ở Azure và **dung lượng filesystem** trong guest.
2. Đo tốc độ tăng dữ liệu và xác định mức dung lượng mới phù hợp.
3. Xác nhận SKU/VM size, giới hạn và điều kiện online resize.
4. Sao lưu/kiểm tra khả năng khôi phục trước thao tác có rủi ro.
5. Cập nhật kích thước managed disk theo quy trình hỗ trợ.
6. Mở rộng partition/filesystem trong Linux hoặc Windows khi cần.
7. Xác minh ứng dụng vẫn truy cập được dữ liệu và chỉ số I/O sau thay đổi.

Ví dụ Azure CLI cập nhật dung lượng một managed data disk theo điều kiện được hỗ trợ:

~~~bash
az disk update \
  --resource-group rg-vm-storage-lab \
  --name disk-appdata-01 \
  --size-gb 128
~~~

**Lệnh này không tự bảo đảm filesystem trong guest sẽ tăng dung lượng.** Hệ điều hành có thể cần mở rộng partition và filesystem bằng công cụ riêng. Không suy luận có thể giảm kích thước managed disk trực tiếp như tăng kích thước; quy trình thu nhỏ thường đòi hỏi giải pháp di chuyển/khôi phục dữ liệu và có nhiều giới hạn.

Nếu cần thay đổi loại disk, IOPS, throughput hoặc caching, hãy kiểm tra khả năng cập nhật, yêu cầu dừng VM và ảnh hưởng ứng dụng theo từng SKU.

## 18. Tháo data disk, thay VM và chính sách xóa

Một lợi ích của managed data disk là vòng đời của disk có thể được quản lý độc lập với VM nếu cấu hình và thao tác cho phép.

**Quy trình tháo an toàn:**

1. Thông báo hoặc ngừng workload đang ghi vào disk.
2. Flush dữ liệu, dừng dịch vụ và unmount filesystem trên Linux hoặc đưa volume offline an toàn trên Windows khi thích hợp.
3. Kiểm tra disk không còn được dùng bởi process.
4. Thực hiện detach trong Azure.
5. Xác minh disk ở trạng thái phù hợp và dữ liệu vẫn tồn tại.
6. Nếu cần, attach disk vào VM khác tương thích rồi mount **không format lại**.

Ví dụ lệnh detach ở phía Azure:

~~~bash
az vm disk detach \
  --resource-group rg-vm-storage-lab \
  --vm-name vm-app-01 \
  --name disk-appdata-01
~~~

**Không dùng detach làm cách thay thế thao tác unmount an toàn của hệ điều hành.** Tháo block device khi database đang ghi có thể gây corruption. Một số cấu hình yêu cầu dừng VM hoặc các bước bổ sung.

Khi xóa VM, cần xem cấu hình **delete option** cho OS/data disks. Nếu là **Delete**, disk có thể bị xóa cùng VM theo chính sách đó. Nếu là **Detach**, disk có thể được giữ lại và tiếp tục phát sinh chi phí. Trước khi xóa tài nguyên, ghi rõ disk nào cần bảo tồn, disk nào có thể xóa và backup đã được kiểm tra.

## 19. Backup, snapshot và phục hồi dữ liệu

**Bền vững không đồng nghĩa có bản sao lưu có thể phục hồi.** Managed Disk cung cấp lưu trữ bền vững theo tính năng dịch vụ, nhưng không tự bảo vệ trước mọi lỗi logic, xóa nhầm, ransomware hay hỏng dữ liệu do ứng dụng.

### 19.1. Snapshot

**Snapshot** ghi nhận một trạng thái point-in-time của disk theo cơ chế snapshot được hỗ trợ. Có thể dùng cho một số bài toán lưu trạng thái trước thay đổi hoặc tạo disk phục hồi.

Ví dụ Azure CLI tạo snapshot từ một managed disk:

~~~bash
az snapshot create \
  --resource-group rg-vm-storage-lab \
  --name snap-appdata-before-update \
  --source disk-appdata-01
~~~

Snapshot là một tài nguyên Azure có chi phí và vòng đời riêng. Một snapshot tạo khi ứng dụng đang ghi có thể chỉ cung cấp mức nhất quán tương đương **crash-consistent** tùy tình huống, không mặc nhiên bảo đảm transaction-consistent cho database.

### 19.2. Azure Backup

Với VM/disk quan trọng, nên cân nhắc **Azure Backup** và chính sách backup phù hợp. Các thành phần cần xác định:

- Mục tiêu khôi phục: **RPO** và **RTO**.
- Phạm vi sao lưu: cả VM, OS disk, những data disk nào.
- Tần suất backup, thời hạn lưu và vị trí lưu.
- Mức nhất quán dữ liệu của ứng dụng.
- Mã hóa và quyền truy cập vào bản backup.
- Khả năng phục hồi thử nghiệm định kỳ.

Những hệ cơ sở dữ liệu có thể cần cơ chế backup ứng dụng chuyên dụng hoặc phối hợp quiesce/transaction log để đạt nhất quán. Đừng mặc định snapshot block device thay thế backup logic hoặc backup có hiểu biết về transaction.

### 19.3. Kịch bản mất host

Giả sử VM phải redeploy sang host khác:

- Azure managed data disk thường tiếp tục tồn tại và có thể được gắn lại theo cấu hình.
- Temporary disk có thể trống hoặc được tạo mới.
- Ứng dụng phải khôi phục cache và dữ liệu tạm từ nguồn bền vững.
- Nếu OS disk dùng ephemeral OS, hệ điều hành có thể được dựng lại theo image.
- Backup và quy trình DR vẫn cần để xử lý lỗi logic hoặc trường hợp phạm vi ảnh hưởng rộng hơn.

## 20. Bảo mật OS disk và data disk

### 20.1. Mã hóa dữ liệu lưu trữ

Azure Managed Disks thường được **mã hóa khi lưu trữ (encryption at rest)** bằng cơ chế server-side encryption của Azure, với khóa do nền tảng quản lý theo mặc định. Tùy nhu cầu tuân thủ và tính năng hỗ trợ, tổ chức có thể xem xét khóa do khách hàng quản lý (customer-managed keys) thông qua những cấu hình được hỗ trợ như Disk Encryption Set.

Mã hóa lưu trữ không thay thế:

- TLS khi dữ liệu truyền qua mạng.
- Bảo vệ credential của ứng dụng và người quản trị.
- Phân quyền trên filesystem/volume.
- Quản lý backup và khả năng phục hồi.
- Kiểm soát dữ liệu trong bộ nhớ, bộ đệm hay vùng local temporary storage.

Một số môi trường cần kiểm tra thêm **encryption at host** theo khả năng hỗ trợ của VM và yêu cầu bảo mật; không được mặc định mọi VM đều có cấu hình giống nhau.

### 20.2. Azure RBAC và quyền trong hệ điều hành

Có quyền quản lý disk Azure qua Portal/API là **quyền control plane**. Quyền đọc các file trong volume bên trong guest chịu kiểm soát của tài khoản hệ điều hành, filesystem permission và cơ chế truy cập ứng dụng.

Nên:

- Cấp vai trò Azure RBAC với phạm vi hẹp nhất để tạo, gắn và xóa disk.
- Sử dụng Microsoft Entra ID, MFA và Privileged Identity Management (PIM) khi phù hợp cho quyền quản trị nhạy cảm.
- Dùng quyền user/group và ACL đúng trong Linux/Windows.
- Giữ secret ở dịch vụ quản lý bí mật thích hợp; tránh lưu duy nhất trên temporary disk.
- Ghi nhận thay đổi VM/disk bằng Azure Activity Log và theo dõi trong hệ điều hành.

### 20.3. Xóa disk an toàn

Với dữ liệu nhạy cảm, việc xóa phải tuân theo chính sách vòng đời và kiểm soát dữ liệu của tổ chức. Tránh thực hiện các thao tác phá hủy như format hoặc delete chỉ dựa vào tên ổ. Kiểm tra đúng disk resource ID, scope và owner trước khi phê duyệt.

## 21. Khả dụng, vùng triển khai và các giới hạn của disk

Managed disk là tài nguyên Azure có SKU, vùng địa lý và ràng buộc khả dụng cụ thể. Khi thiết kế HA/DR:

- Chọn disk SKU có cơ chế redundancy phù hợp khi dịch vụ hỗ trợ, ví dụ LRS/ZRS theo SKU và region.
- Kiểm tra disk và VM có tương thích với availability zone đã chọn không.
- Không giả định disk ở một zone có thể gắn trực tiếp vào VM ở zone bất kỳ.
- Sử dụng replication hoặc cơ chế DR ở tầng ứng dụng/dịch vụ cho mục tiêu đa zone/đa region nếu yêu cầu.
- Kiểm thử khả năng dựng lại VM và khôi phục data disk/ứng dụng từ backup hoặc image.
- Với ephemeral OS và temporary disk, lập kế hoạch tái tạo trạng thái thay vì cố giữ dữ liệu cục bộ.

**Availability Zone redundancy** của một loại disk và **backup đa region** là hai vấn đề khác nhau. Một cơ chế tăng khả dụng trong một region không thay thế kế hoạch phục hồi khi mất cả region hoặc bị xóa nhầm dữ liệu.

## 22. Giám sát hiệu năng và dung lượng disk

Để vận hành ổn định, cần kết hợp metric của Azure và giám sát trong hệ điều hành khách.

| Nhóm chỉ số | Nội dung cần theo dõi | Mục tiêu |
|---|---|---|
| Disk read/write operations | Số thao tác I/O theo thời gian | Nhận diện nhu cầu IOPS |
| Disk read/write bytes | Lưu lượng đọc/ghi theo thời gian | Đánh giá throughput |
| Latency/queue depth | Độ trễ I/O và độ sâu hàng đợi nếu có thể đo | Phát hiện nghẽn disk hoặc VM |
| Disk IOPS/throughput limits | Mức giới hạn theo disk/VM SKU | Biết tài nguyên nào đang thành nút cổ chai |
| Filesystem usage | Phần trăm dung lượng đã dùng và inode nếu phù hợp | Phòng hết chỗ gây ngừng ứng dụng |
| Application errors | Timeout, fsync/IO error, lỗi ghi file | Liên hệ I/O với lỗi nghiệp vụ |
| Backup status | Lần backup gần nhất, lỗi và khả năng restore | Bảo đảm dữ liệu có phương án phục hồi |

Azure Monitor có thể cung cấp metric về VM/disk. Các chỉ số **dung lượng filesystem** trong guest thường cần Azure Monitor Agent, guest metrics hoặc công cụ theo dõi hệ điều hành phù hợp; không phải mọi chỉ số đều có sẵn chỉ từ tài nguyên managed disk.

Trên Linux:

~~~bash
df -h
lsblk -f
iostat -xz 1
~~~

Lệnh **iostat** yêu cầu công cụ tương ứng, thường thuộc gói sysstat, đã được cài. Trên Windows có thể dùng Performance Monitor, Resource Monitor hoặc các công cụ quan sát I/O tương ứng.

Khi thấy ứng dụng chậm, hãy kiểm tra đồng thời CPU, RAM, VM I/O limits, disk IOPS, host caching và độ trễ backend trước khi kết luận cần nâng một loại disk đắt tiền hơn.

## 23. Kiểm soát chi phí lưu trữ đĩa

Các yếu tố có thể ảnh hưởng chi phí bao gồm:

1. **Managed disk SKU**: Standard HDD, Standard SSD, Premium SSD, Premium SSD v2 hoặc loại khác.
2. **Dung lượng được cấp**: không nên suy luận lúc nào cũng tính đúng bằng số bytes đã dùng trong filesystem.
3. **Hiệu năng được cấu hình**: một số SKU có giá liên quan đến IOPS/throughput đặt trước.
4. **Snapshot và backup**: tài nguyên lưu trữ bản sao, retention và khả năng truyền dữ liệu có thể tính phí riêng.
5. **Redundancy**: lựa chọn LRS/ZRS và giới hạn regional/SKU.
6. **Disk bỏ quên**: disk được detach nhưng chưa xóa có thể tiếp tục tính phí.
7. **VM size**: local temporary disk thường gắn với gói compute; VM có local storage lớn có thể đi kèm mức giá VM tương ứng.
8. **Monitoring và log**: metric/diagnostic data gửi tới dịch vụ lưu trữ hoặc phân tích có chi phí.

Khi VM bị deallocate, chi phí compute có thể ngừng theo điều kiện tính phí, nhưng managed disk độc lập vẫn tồn tại và có thể tiếp tục tính tiền. Khi lập ngân sách, kiểm tra Azure Pricing Calculator và Cost Management theo SKU/region thực tế.

Một phương pháp tiết kiệm là tách workload:

- OS disk đủ dùng cho hệ điều hành.
- Data disk phù hợp IOPS thực tế, tránh chọn SKU cao không cần thiết.
- Cache tái tạo được dùng temporary/local storage nếu VM hỗ trợ và phù hợp.
- Các file chia sẻ lớn hoặc dữ liệu không cần block-level access có thể phù hợp Blob/Files hơn.
- Xóa disk/snapshot thử nghiệm sau khi xác nhận không còn phụ thuộc và có quyền xóa.

**Không xóa disk chỉ vì trạng thái Unattached**. Cần xác minh nó có đang là disk phục hồi, bản sao lưu thủ công hoặc tài nguyên được giữ có chủ ý hay không.

## 24. Các lỗi vận hành thường gặp

### 24.1. Thấy ổ D: và mặc định là managed data disk

Trên một số Windows VM, D: là temporary disk. Hãy kiểm tra metadata disk trong Azure và hệ điều hành. Dữ liệu quan trọng không được lưu duy nhất ở nơi có thể mất khi host thay đổi.

### 24.2. Gắn disk thành công nhưng không thấy ổ trong Explorer

Disk có thể chưa được initialize, partition, format hoặc gán drive letter. Xem Disk Management/Get-Disk trước khi thao tác. Nếu disk chứa dữ liệu cũ, **không initialize/format lại**.

### 24.3. Linux đã mount /data nhưng reboot xong mất đường dẫn

Kiểm tra **/etc/fstab**, UUID, filesystem type, thời điểm disk xuất hiện và trạng thái mount. Tránh dựa vào tên thiết bị **/dev/sdc** vì có thể thay đổi.

### 24.4. VM hết dung lượng OS disk dù data disk còn trống

Ứng dụng hoặc log có thể tiếp tục ghi vào **/** hoặc **C:**. Kiểm tra đường dẫn lưu dữ liệu thực tế, mount point và quyền ghi. Có thể cần di chuyển dữ liệu hoặc cấu hình log rotation.

### 24.5. Tăng disk size ở Azure nhưng hệ điều hành chưa thấy tăng

Disk resource đã được mở rộng nhưng partition/filesystem chưa được mở rộng tương ứng. Kiểm tra điều kiện resize, rescanning của guest và công cụ filesystem. Không thực hiện thay đổi phân vùng nếu chưa có backup và kế hoạch rollback.

### 24.6. Database bị mất sau khi VM deallocate/redeploy

Rất có thể dữ liệu trước đó nằm trên temporary disk, ephemeral OS disk hoặc đường dẫn không đúng. Phải xác nhận nơi lưu thật, kiểm tra backup và điều tra log/timeline; không định dạng hoặc ghi thêm lên disk trước khi đánh giá khả năng phục hồi.

### 24.7. VM bị xóa và data disk cũng bị xóa

Kiểm tra **delete option** của từng disk. “Managed” không đồng nghĩa “được giữ lại khi xóa VM”. Thiết lập chính sách xóa theo nhu cầu vận hành và xác nhận backup trước thao tác.

### 24.8. Disk có IOPS cao nhưng ứng dụng vẫn chậm

Có thể VM size đạt giới hạn throughput, hệ thống file/đội I/O chưa tối ưu, ứng dụng chặn đồng bộ hoặc caching không phù hợp. Đo từ phía VM, disk, guest và ứng dụng để tìm giới hạn thật.

### 24.9. Snapshot có nhưng restore không nhất quán database

Snapshot block-level không mặc nhiên là application-consistent. Cần giải pháp backup phù hợp với database, kiểm tra log/transaction và diễn tập khôi phục.

### 24.10. Disk tách khỏi VM vẫn phát sinh phí

Detach chỉ bỏ liên kết với VM, không tự xóa disk. Kiểm tra disk cần lưu giữ hay có thể xóa theo quy trình quản trị tài nguyên.

## 25. Bài thực hành có kiểm soát: ba loại đĩa

**Bối cảnh:** bạn có một Azure Linux VM thử nghiệm và quyền quản lý disk phù hợp. Mục tiêu là quan sát OS disk, tạo data disk mới, xác định temporary disk nếu VM size có hỗ trợ, rồi kiểm tra dữ liệu nằm đúng nơi.

**Điều kiện an toàn:**

- Chỉ thực hiện trong resource group lab, có giới hạn ngân sách.
- Không thực hiện format/xóa đối với VM/disk production.
- Xác nhận danh tính disk bằng Portal/CLI và hệ điều hành trước mọi lệnh có thể ghi đè.
- Nếu VM size không có temporary disk, đánh dấu phần kiểm tra này là **không áp dụng**, không tự tạo giả định.

### Phần A — Kiểm kê

1. Mở VM trong Azure Portal và xác định OS disk, data disk đang có, SKU và delete option.
2. Chạy truy vấn **az vm show** ở mục 12 hoặc xem tương đương trong Portal.
3. Trong Linux, dùng **lsblk** để xác định filesystem chứa **/**.
4. Ghi lại dung lượng đĩa OS, filesystem và mức sử dụng trước khi thực hành.

### Phần B — Gắn data disk mới

1. Tạo managed disk mới dung lượng nhỏ phù hợp ngân sách bằng lệnh ở mục 13.
2. Gắn vào VM với LUN chưa dùng.
3. Trong guest, chạy **lsblk** và **blkid**; đối chiếu với disk vừa attach.
4. Chỉ nếu chắc đây là disk mới rỗng: tạo filesystem, mount tại **/data** và kiểm tra.
5. Tạo một file thử nghiệm bên dưới **/data**, ví dụ **/data/lab-check.txt**.
6. Lấy UUID và cấu hình mount bền vững sau reboot theo hướng dẫn ở mục 14.

### Phần C — Temporary disk

1. Kiểm tra VM size có local temporary storage không.
2. Xác minh vùng mount/volume bằng công cụ của hệ điều hành.
3. Nếu có, đặt một file cache **không quan trọng** vào vùng tạm.
4. Ghi lại vì sao file đó **không** được coi là dữ liệu lâu dài.
5. **Không cần cố tình redeploy/deallocate** để làm mất file; có thể mô phỏng ứng dụng bị mất cache bằng cách xóa chính file cache thử nghiệm rồi tái tạo.

### Phần D — Kiểm tra lại và dọn dẹp

1. Reboot VM theo kế hoạch lab và xác minh filesystem **/data** vẫn mount, file thử nghiệm còn.
2. Kiểm tra log/dữ liệu ứng dụng không ghi nhầm lên OS disk do /data chưa mount.
3. Xác nhận đường dẫn temporary được thiết kế chịu mất dữ liệu.
4. Nếu cần kiểm tra backup, dùng snapshot/backup phù hợp trong lab và lưu ý về tính nhất quán.
5. Dừng dịch vụ dùng disk, unmount và detach data disk **an toàn** trước khi xóa tài nguyên thử nghiệm, nếu được phê duyệt.
6. Xóa snapshot/disk lab không còn cần sau khi xác nhận không có phụ thuộc, kiểm tra chi phí trong Cost Management.

**Kết quả mong đợi:** bạn chỉ ra được đâu là OS managed disk, đâu là managed data disk, đâu là local temporary disk (nếu có), giải thích được khả năng tồn tại của dữ liệu và biết cách mount ổ data mà không gây mất dữ liệu.

## 26. Checklist đưa VM có data disk vào production

- [ ] Đã xác nhận OS disk là managed hay ephemeral và hiểu hệ quả vòng đời.
- [ ] Dữ liệu quan trọng không chỉ tồn tại trên temporary disk.
- [ ] Data disk SKU, dung lượng, IOPS và throughput đáp ứng workload.
- [ ] VM size hỗ trợ số data disk, bus/controller và tổng I/O dự kiến.
- [ ] Data disk được gắn bằng LUN phù hợp và nhận diện bằng thông tin ổn định.
- [ ] Đã kiểm tra filesystem, partition, mount và quyền file trong guest.
- [ ] Không format disk hiện có dữ liệu.
- [ ] Mount Linux dùng UUID hoặc cơ chế ổn định phù hợp; Windows volume được xác minh.
- [ ] Có giám sát filesystem usage, I/O, application errors và backup status.
- [ ] Có backup theo RPO/RTO và đã thực hành restore.
- [ ] Kiểm tra encryption at rest, Azure RBAC, quyền OS và secret.
- [ ] Xác định rõ delete option khi xóa VM và disk lifecycle.
- [ ] Có kế hoạch zone/DR phù hợp và không nhầm redundancy với backup.
- [ ] Đã dự trù chi phí managed disk, snapshot, backup và disk mồ côi.

## 27. Câu hỏi tự kiểm tra

1. OS disk có vai trò gì khác data disk? Vì sao cần quan tâm đến loại OS disk?
2. Managed OS disk thông thường và ephemeral OS disk khác nhau ở điểm nào?
3. Temporary disk của một số VM Windows thường có ký tự ổ nào? Vì sao không thể dựa vào chữ cái đó để chọn nơi lưu database?
4. Khi stop/deallocate VM, điều gì thường xảy ra với dữ liệu trên managed data disk? Temporary disk có bảo đảm tương tự không?
5. Vì sao data disk vừa attach vào VM có thể chưa xuất hiện như một ổ file có thể ghi?
6. Tại sao trước khi chạy mkfs hoặc Initialize-Disk phải xác định chính xác thiết bị?
7. LUN 0 có đồng nghĩa với /dev/sdc trên mọi Linux VM không?
8. Đã tăng kích thước managed disk trong Azure thì filesystem trong guest đã tự động tăng chưa?
9. Khi xóa VM, dữ liệu managed disk có chắc chắn được giữ lại không?
10. Snapshot managed disk có mặc nhiên bảo đảm database-consistent backup không?
11. Nếu cache thumbnail bị mất sau host maintenance, ứng dụng nên ứng xử như thế nào?
12. Bạn sẽ kiểm tra những metric và cấu hình nào khi disk có IOPS công bố cao nhưng API Java vẫn chậm?

## 28. Tổng kết

Trong Azure Virtual Machines, **OS disk** chủ yếu phục vụ khởi động và vận hành hệ điều hành; **data disk** chứa dữ liệu ứng dụng cần được quản lý, bảo vệ và sao lưu; **temporary disk** là nơi lưu dữ liệu cục bộ **có thể bị mất** khi hạ tầng thay đổi. OS disk thông thường và data disk thường là Azure Managed Disks bền vững theo chính sách lưu trữ, trong khi **ephemeral OS disk** là trường hợp đặc biệt dành cho những hệ thống có thể tái tạo.

Khi vận hành, hãy **xác định đúng loại disk trước khi format**, gắn và mount data disk với định danh ổn định, không lưu dữ liệu quan trọng trên temporary disk, lựa chọn SKU theo nhu cầu thực tế và thiết lập backup/restore cùng chính sách xóa rõ ràng. Kết hợp Azure RBAC, giám sát hệ điều hành, Azure Monitor và Cost Management để vận hành đĩa an toàn, có khả năng phục hồi và kiểm soát được chi phí.

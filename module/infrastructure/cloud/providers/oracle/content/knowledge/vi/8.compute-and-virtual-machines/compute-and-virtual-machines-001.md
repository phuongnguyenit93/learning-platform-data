# Lựa chọn VM, bare metal và họ compute shape

## Mục tiêu bài học

Trong Oracle Cloud Infrastructure (OCI), chọn Compute instance là chọn một môi trường chạy ứng dụng với giới hạn tài nguyên và đặc điểm vận hành cụ thể. Hai instance cùng số CPU và RAM vẫn có thể khác nhau về kiến trúc bộ xử lý, hiệu năng mạng, loại lưu trữ và khả năng thay đổi cấu hình.

Bài học thuộc chương **Compute và máy chủ ảo** của module **CLOUD_PROVIDERS_ORACLE**. Sau bài này, bạn có thể:

- Phân biệt virtual machine (VM) và bare metal để chọn môi trường phù hợp với workload.
- Đọc tên shape, phân biệt họ shape với cấu hình CPU/RAM của một instance.
- Kiểm tra tương thích CPU, hệ điều hành, image và phần mềm trước khi triển khai.
- Đề xuất cấu hình ban đầu, đo bằng workload đại diện và điều chỉnh dựa trên kết quả.
- Đặt lựa chọn Compute trong bối cảnh compartment, IAM, VCN, giám sát, chi phí và tính sẵn sàng của hệ thống OCI.

Các tên shape xuất hiện trong bài dùng để minh họa cách đọc. Shape, giới hạn, giá và khả năng cung cấp thực tế cần được kiểm tra tại region, availability domain và tenancy triển khai.

## 1. Instance và shape giải quyết hai câu hỏi khác nhau

**Instance** là tài nguyên Compute được tạo ra để chạy hệ điều hành và ứng dụng. **Shape** mô tả cấu hình phần cứng hoặc tập giới hạn tài nguyên mà instance có thể sử dụng.

Khi thiết kế một instance, cần trả lời ít nhất các câu hỏi sau:

| Thành phần | Câu hỏi cần trả lời | Ảnh hưởng chính |
| --- | --- | --- |
| Loại instance | VM hay bare metal? | Mức chia sẻ máy vật lý, quy mô cấp phát, mô hình vận hành |
| Họ shape | Standard, DenseIO, GPU hay họ chuyên dụng khác? | Đặc tính CPU, lưu trữ cục bộ, tăng tốc và mạng |
| Cấu hình shape | CPU, RAM và các giới hạn liên quan là bao nhiêu? | Năng lực xử lý và mức tài nguyên cấp phát |
| Kiến trúc CPU | x86-64 hay Arm? | Khả năng chạy image, binary, thư viện và container |
| Image | Hệ điều hành và phiên bản nào? | Khả năng khởi động, hỗ trợ phần mềm và bảo trì |
| Vị trí và mạng | Region, availability domain, subnet nào? | Độ trễ, tính sẵn sàng, đường truy cập và khả năng cấp phát |
| Lưu trữ | Boot volume, block volume hay NVMe cục bộ? | Dung lượng, độ bền dữ liệu, IOPS và độ trễ |

Chọn shape không tự giải quyết toàn bộ thiết kế. Ví dụ, một VM mạnh vẫn không truy cập được cơ sở dữ liệu nếu route, security rules hoặc quyền liên quan chưa đúng. Tương tự, nhiều CPU không bù được một block volume đang giới hạn throughput.

## 2. VM và bare metal

### 2.1. Virtual machine: linh hoạt ở quy mô từng máy ảo

VM chạy trong môi trường ảo hóa trên máy chủ vật lý của nhà cung cấp. Bạn quản trị hệ điều hành khách, cài phần mềm và triển khai ứng dụng; OCI quản lý hạ tầng vật lý cùng lớp ảo hóa của dịch vụ.

VM phù hợp với nhiều workload thông dụng: API backend, ứng dụng Java, worker xử lý bất đồng bộ, môi trường phát triển và các dịch vụ có thể chia thành nhiều instance nhỏ.

Các lợi ích thường gặp:

- Bắt đầu với lượng tài nguyên vừa phải thay vì cấp phát cả máy vật lý.
- Có nhiều lựa chọn cấu hình, trong đó một số shape cho phép điều chỉnh CPU và RAM.
- Dễ xây dựng nhóm instance có cùng cấu hình để phân phối tải.
- Có thể giảm phạm vi ảnh hưởng của lỗi ứng dụng bằng cách tách thành nhiều instance.

Ảo hóa không đồng nghĩa với việc hiệu năng luôn thiếu ổn định. Cũng không nên mặc định mọi workload đều cần bare metal để đạt tốc độ tốt. Cần đo ứng dụng trên shape ứng viên và xem cả CPU, bộ nhớ, mạng, lưu trữ, độ trễ lẫn giới hạn của dịch vụ phụ thuộc.

### 2.2. Bare metal: cấp phát một máy chủ vật lý chuyên dụng

Bare metal cấp phát một máy chủ vật lý cho instance của bạn, không có lớp hypervisor của dịch vụ Compute nằm giữa hệ điều hành instance và phần cứng như ở VM. Bạn vẫn sử dụng các cơ chế OCI liên quan đến IAM, mạng và quản lý tài nguyên; đây không phải việc tự quản trị trung tâm dữ liệu.

Bare metal đáng cân nhắc khi workload có yêu cầu rõ ràng như:

- Cần đặc tính phần cứng hoặc môi trường thực thi mà shape VM ứng viên không đáp ứng.
- Cần quy mô tài nguyên của cả máy chủ và có khả năng sử dụng hiệu quả quy mô đó.
- Chạy tác vụ tính toán hoặc I/O đặc thù đã được đo và xác nhận phù hợp với shape bare metal cụ thể.
- Có yêu cầu phần mềm hoặc điều kiện cấp phép cần xem xét theo cấu hình máy chủ vật lý.

Các ràng buộc cần tính đến:

- Đơn vị cấp phát thường lớn hơn, nên một ứng dụng nhỏ có thể để thừa nhiều tài nguyên.
- Không thể giả định có thể điều chỉnh CPU/RAM theo bước nhỏ như một flexible VM shape.
- Nếu một máy chứa nhiều workload, sự cố hoặc bảo trì trên máy đó có phạm vi ảnh hưởng lớn.
- Khả năng cung cấp shape tại vị trí cần triển khai vẫn phải được kiểm tra.

**Bare metal không tự tạo tính sẵn sàng cao.** Một ứng dụng chỉ có một bare metal instance vẫn phụ thuộc vào một máy chủ. Thiết kế nhiều bản sao, phân bố lỗi và phục hồi dữ liệu vẫn cần thực hiện riêng.

### 2.3. So sánh để ra quyết định

| Tiêu chí | VM | Bare metal |
| --- | --- | --- |
| Đơn vị cấp phát | Máy ảo với cấu hình theo shape | Máy chủ vật lý chuyên dụng theo shape |
| Workload nhỏ hoặc thay đổi nhiều | Thường thuận tiện để bắt đầu và điều chỉnh | Có nguy cơ cấp phát dư lớn |
| Tùy chọn CPU/RAM | Có shape cố định và shape linh hoạt | Phụ thuộc cấu hình phần cứng của shape |
| Yêu cầu phần cứng chuyên biệt | Phải kiểm tra khả năng của từng VM shape | Có thể phù hợp nếu shape cung cấp đúng phần cứng |
| Cách kiểm chứng hiệu năng | Benchmark ứng dụng trên shape ứng viên | Benchmark ứng dụng trên shape ứng viên |
| Tính sẵn sàng | Cần nhiều bản sao và thiết kế phục hồi | Cần nhiều bản sao và thiết kế phục hồi |
| Trách nhiệm hệ điều hành | Người dùng quản trị | Người dùng quản trị |

Nếu yêu cầu chỉ là “chạy một API Java có thể mở rộng ngang”, VM là ứng viên hợp lý để đánh giá đầu tiên. Chuyển sang bare metal cần có lý do từ yêu cầu hoặc số liệu, không chỉ từ tên gọi.

## 3. Đọc tên shape và hiểu họ Compute

### 3.1. Tên shape là dấu hiệu để tra cứu cấu hình

Hai ví dụ về cấu trúc tên là `VM.Standard.E4.Flex` và `BM.Standard.E4.128`.

- `VM` hoặc `BM` thể hiện loại instance.
- `Standard` gợi ý họ phục vụ nhu cầu tính toán đa dụng.
- Phần như `E4` định danh dòng hoặc thế hệ nền tảng; cần xem thông số của đúng shape để biết bộ xử lý và khả năng hỗ trợ.
- `Flex` cho biết shape có cấu hình linh hoạt trong các giới hạn được hỗ trợ.
- Một hậu tố số có ý nghĩa theo quy ước của shape đó; không áp dụng một cách giải mã chung cho mọi họ.

Không nên viết logic tự động hóa chỉ dựa vào việc tách tên shape để suy ra toàn bộ CPU, RAM và băng thông. Nguồn quyết định là thông tin shape do OCI cung cấp tại môi trường đích.

### 3.2. Các họ shape và kiểu workload

| Họ hoặc nhóm shape | Đặc điểm cần xem | Workload có thể phù hợp | Điểm phải kiểm tra |
| --- | --- | --- | --- |
| Standard | Cân bằng tài nguyên cho tính toán đa dụng | Backend, worker, ứng dụng doanh nghiệp | CPU, tỷ lệ RAM/CPU, mạng và khả năng mở rộng |
| DenseIO | Có lưu trữ NVMe cục bộ trên các shape hỗ trợ | Xử lý dữ liệu có I/O cục bộ lớn, scratch space, cache | Vòng đời dữ liệu, dung lượng và cơ chế phục hồi |
| GPU | Có bộ tăng tốc GPU | Huấn luyện hoặc suy luận mô hình, xử lý đồ họa | Loại GPU, VRAM, driver, framework và nguồn cung |
| Optimized hoặc HPC | Nhấn mạnh đặc tính tính toán, độ trễ hoặc kết nối tùy shape | Mô phỏng, tính toán khoa học, workload nhạy với hiệu năng | Hiệu năng từng luồng, mạng cụm và yêu cầu triển khai |

Bảng này là cách nhóm nhu cầu, không phải danh mục shape đầy đủ. Không phải họ nào cũng có cả VM lẫn bare metal, và không phải shape nào trong một nhóm cũng có cùng khả năng mạng hoặc lưu trữ.

Tên họ chỉ giúp lập danh sách ứng viên. Chẳng hạn, một ứng dụng đọc nhiều dữ liệu không mặc nhiên cần DenseIO: nếu dữ liệu nằm trên một dịch vụ từ xa và độ trễ chủ yếu ở truy vấn, NVMe cục bộ có thể không cải thiện nút thắt đó.

### 3.3. Fixed shape và flexible shape

**Fixed shape** cung cấp một cấu hình xác định. **Flexible shape** cho phép chọn CPU và RAM trong phạm vi và tỷ lệ được hỗ trợ.

Ví dụ, hai workload có thể cần cấu hình khác nhau:

- Worker tính toán: sử dụng CPU cao nhưng nhu cầu RAM vừa phải.
- Dịch vụ dùng cache: cần nhiều RAM hơn trên mỗi đơn vị CPU.

Flexible shape giúp điều chỉnh theo nhu cầu này, nhưng không có nghĩa CPU và RAM được chọn tùy ý. Cần kiểm tra mức tối thiểu, tối đa, tỷ lệ RAM/CPU và các giới hạn tài nguyên đi kèm. Khả năng mạng hoặc giới hạn I/O có thể phụ thuộc cấu hình được cấp phát.

Khả năng đổi shape của một instance đang tồn tại còn phụ thuộc loại instance, shape nguồn/đích, image và các cấu hình liên quan. Hãy lập kế hoạch gián đoạn hoặc thay thế instance; không mặc định đổi cấu hình luôn diễn ra trực tiếp khi ứng dụng đang chạy.

## 4. CPU: số lượng chưa đủ để kết luận hiệu năng

### 4.1. Phân biệt OCPU, vCPU và khả năng xử lý ứng dụng

OCI sử dụng OCPU trong nhiều cấu hình Compute. Quan hệ giữa OCPU, lõi vật lý và vCPU phụ thuộc kiến trúc cùng định nghĩa của shape. Với nhiều shape x86 có SMT, một OCPU tương ứng một lõi vật lý với hai luồng thực thi; với các shape Arm như Ampere A1, quan hệ luồng thực thi khác với mô hình đó. Phải đọc thông số của shape trước khi quy đổi hoặc so sánh báo giá.

Ví dụ, câu “hai bên đều có 4 CPU” chưa đủ để kết luận tương đương, vì có thể đang so sánh:

- 4 vCPU với 4 OCPU.
- Bộ xử lý khác thế hệ và hiệu năng từng luồng khác nhau.
- Workload nhiều luồng với workload chủ yếu chạy một luồng.
- CPU mạnh nhưng giới hạn mạng hoặc lưu trữ thấp hơn nhu cầu.

Khi so sánh, ghi rõ đơn vị tài nguyên và đo công việc hoàn thành: request/giây tại một mức độ trễ, thời gian xử lý một batch, hoặc số tác vụ thành công trong một giờ.

### 4.2. Kiến trúc x86-64 và Arm

Ứng dụng Java có tính di động ở mức bytecode, nhưng toàn bộ gói triển khai không nhất thiết độc lập kiến trúc CPU.

Trước khi chọn Arm thay cho x86-64 hoặc ngược lại, kiểm tra:

- Image hệ điều hành có hỗ trợ kiến trúc của shape hay không.
- Bản phân phối JDK có build đúng kiến trúc.
- Có dùng JNI, native library, agent giám sát hoặc chương trình phụ trợ chứa binary theo kiến trúc hay không.
- Container image có manifest và các lớp tương ứng với `linux/amd64` hoặc `linux/arm64` hay không.
- Công cụ backup, bảo mật và phần mềm thương mại có hỗ trợ tổ hợp triển khai đó hay không.

Container không tự xóa khác biệt kiến trúc. Một image chỉ chứa binary `amd64` không mặc nhiên chạy trực tiếp trên máy Arm.

Ví dụ, API Java thuần có thể dễ chuyển hơn một dịch vụ xử lý tài liệu gọi thêm thư viện native. Cả hai vẫn cần chạy kiểm thử chức năng và đo hiệu năng trên kiến trúc đích.

## 5. Bộ nhớ, lưu trữ và mạng có thể quyết định shape

### 5.1. RAM phải dành cho toàn bộ tiến trình

Đối với một ứng dụng JVM, không nên đặt heap bằng toàn bộ RAM của instance. Ngoài Java heap còn có metaspace, thread stack, direct buffer, bộ nhớ native, page cache của hệ điều hành và các agent vận hành.

Một cách lập ngân sách ban đầu:

```text
RAM cần thiết
  = heap theo workload
  + bộ nhớ ngoài heap và native
  + hệ điều hành và agent
  + khoảng dự phòng cho biến động
```

Đây là mô hình ước lượng, không phải công thức cho một tỷ lệ cố định. Hãy quan sát mức sử dụng thực, GC, swap và các sự kiện thiếu bộ nhớ khi chạy workload đại diện. CPU trung bình thấp không có nghĩa có thể giảm RAM an toàn.

### 5.2. Boot volume, block volume và NVMe cục bộ

| Loại lưu trữ | Vai trò thường gặp | Điều cần nhớ khi chọn Compute |
| --- | --- | --- |
| Boot volume | Hệ điều hành và nội dung khởi động | Dung lượng, hiệu năng và chính sách giữ/xóa volume cần cấu hình riêng |
| Block volume | Dữ liệu hoặc filesystem gắn vào instance | Hiệu năng còn phụ thuộc cấu hình volume, đường kết nối và giới hạn phía instance |
| NVMe cục bộ | Scratch space, cache hoặc dữ liệu có cơ chế sao chép/phục hồi phù hợp | Gắn với máy chủ và vòng đời instance; không mặc định bền vững như block volume |

Có NVMe cục bộ không đồng nghĩa dữ liệu tự được backup. Trước khi dùng cho dữ liệu quan trọng, phải hiểu những thao tác nào có thể làm mất dữ liệu và cách phục hồi khi instance hoặc máy chủ gặp sự cố.

Một thiết kế xử lý batch có thể đặt file trung gian lên NVMe và lưu kết quả cuối vào nơi lưu trữ bền vững. Ngược lại, đặt bản dữ liệu duy nhất lên ổ cục bộ rồi chỉ dựa vào sức mạnh của bare metal là một thiếu sót về phục hồi.

### 5.3. Băng thông và đường đi của dữ liệu

Một backend có CPU còn dư nhưng request chậm có thể đang chờ mạng hoặc dịch vụ phụ thuộc. Khi chọn shape, cần xem:

- Giới hạn băng thông mạng của shape và cấu hình đang chọn.
- Đường truyền đến cơ sở dữ liệu, object storage hoặc hệ thống bên ngoài.
- Độ trễ, số kết nối đồng thời và mức dữ liệu trên mỗi request.
- Giới hạn của load balancer, dịch vụ lưu trữ và các thành phần liên quan.

Tăng CPU có thể giúp ở một số cấu hình, nhưng không thay thế việc xác định nút thắt. VCN, subnet, route và security rules phải được thiết kế cùng với Compute để ứng dụng có đường giao tiếp phù hợp.

## 6. Quy trình chọn shape theo workload

### Bước 1: Viết yêu cầu bằng hành vi ứng dụng

Thay vì bắt đầu bằng “cần một máy lớn”, hãy ghi rõ:

- Workload phục vụ request, xử lý batch, chạy GPU hay cung cấp dịch vụ có trạng thái.
- Lưu lượng bình thường và cao điểm; độ trễ hoặc thời gian hoàn thành mong muốn.
- Bộ nhớ làm việc, dung lượng dữ liệu và yêu cầu I/O.
- Kiến trúc CPU và phần mềm bắt buộc.
- Yêu cầu khôi phục khi một instance không còn hoạt động.

### Bước 2: Chọn VM hoặc bare metal và họ shape ứng viên

Dùng yêu cầu để loại bỏ phương án không tương thích trước. Nếu ứng dụng không cần phần cứng đặc thù và có thể chia tải, đánh giá VM đa dụng là một điểm khởi đầu thực tế. Nếu cần GPU hoặc NVMe cục bộ, kiểm tra đúng họ shape cung cấp tài nguyên đó.

Không xem việc “sử dụng hết cả máy” là mục tiêu độc lập. Mục tiêu là đáp ứng yêu cầu ứng dụng với chi phí và công sức vận hành phù hợp.

### Bước 3: Kiểm tra khả năng triển khai

Trước khi chốt cấu hình, xác nhận tại môi trường đích:

- Shape khả dụng trong region và availability domain cần dùng.
- Image tương thích với shape và kiến trúc CPU.
- Service limits của tenancy và compartment quotas còn đủ, nếu có áp dụng.
- IAM policy cho phép tạo Compute cùng các tài nguyên mạng, volume liên quan.
- Hệ thống có khả năng cấp phát tài nguyên thực tế tại thời điểm tạo instance.

Có quota hoặc service limit còn dư không bảo đảm luôn có capacity. Phương án triển khai nên xác định trước shape hoặc vị trí thay thế đã được kiểm chứng tương thích.

### Bước 4: Benchmark với cùng điều kiện

Dùng cùng dữ liệu, phiên bản ứng dụng, cấu hình phù hợp và cách phát tải. Với JVM, dành thời gian warm-up trước khi lấy kết quả để giảm ảnh hưởng của quá trình khởi động và JIT.

Ghi ít nhất:

| Nhóm | Chỉ số gợi ý | Dùng để phân biệt |
| --- | --- | --- |
| Ứng dụng | Throughput, tỷ lệ lỗi, p95/p99 latency | Cấu hình có đáp ứng mục tiêu hay không |
| CPU | Mức sử dụng, hàng đợi chạy, luồng bận | Thiếu năng lực CPU hay xử lý tuần tự |
| Bộ nhớ | RAM khả dụng, GC, swap, OOM | Thiếu RAM, áp lực heap hoặc native memory |
| Lưu trữ | Độ trễ I/O, IOPS, throughput | Giới hạn ở ổ đĩa hoặc đường kết nối |
| Mạng | Throughput, lỗi, thời gian chờ dịch vụ phụ thuộc | Giới hạn mạng hoặc phụ thuộc bên ngoài |

Đừng kết luận từ một lần chạy ngắn. Đo ở tải bình thường, cao điểm và giai đoạn đủ dài để quan sát GC, cache cùng hành vi nền của ứng dụng.

### Bước 5: So sánh chi phí cho cùng mức dịch vụ

So sánh các phương án khi chúng cùng đáp ứng mục tiêu về độ trễ, throughput và tính sẵn sàng. Một instance có đơn giá thấp hơn nhưng cần nhiều bản sao hơn có thể dẫn đến kết quả khác ở cấp hệ thống.

Chi phí cần tính gồm Compute, volume, backup, mạng và các dịch vụ đi kèm. Nếu có phần mềm thương mại hoặc cơ sở dữ liệu tự quản trị, điều kiện cấp phép cũng cần được đánh giá riêng; không suy ra chỉ từ số CPU ghi trên tên shape.

Các ưu đãi hoặc tài nguyên miễn phí, nếu có áp dụng, không thay thế việc kiểm tra giới hạn, capacity và yêu cầu ứng dụng. Bài này không đặt một mức giá hay danh sách ưu đãi làm mặc định.

## 7. Ví dụ: chọn cấu hình cho API Java truy cập cơ sở dữ liệu Oracle

### 7.1. Bối cảnh

Một nhóm triển khai API Java trên OCI. API truy cập một dịch vụ cơ sở dữ liệu Oracle được triển khai riêng. Mục tiêu minh họa:

- Phục vụ 300 request/giây tại thời điểm cao điểm.
- p95 latency không vượt 250 ms với bộ request thử nghiệm.
- Có thể tiếp tục phục vụ khi một instance ứng dụng gặp sự cố, trong giới hạn tải đã thiết kế.
- Theo dõi được chi phí theo compartment hoặc tag mà tổ chức quy định.

Các con số này là giả định của bài tập, không phải cam kết hiệu năng của OCI.

### 7.2. Lập danh sách phương án

Phương án đầu tiên là nhiều Standard VM phía sau load balancer. Nhóm chọn một kiến trúc CPU mà toàn bộ JDK, container và agent đều hỗ trợ, rồi kiểm tra cấu hình CPU/RAM bằng tải đại diện.

Bare metal chỉ trở thành ứng viên khi có dữ liệu cho thấy mô hình nhiều VM không đáp ứng một yêu cầu cụ thể hoặc cả máy vật lý mang lại kết quả phù hợp hơn. DenseIO cũng không được chọn chỉ vì hệ thống có cơ sở dữ liệu: dữ liệu ở dịch vụ cơ sở dữ liệu riêng, nên ổ NVMe cục bộ của máy ứng dụng chưa chắc là tài nguyên cần thiết.

Nhóm cần đo connection pool, thời gian truy vấn và độ trễ mạng tới cơ sở dữ liệu. Nếu request chủ yếu chờ truy vấn, tăng CPU của máy ứng dụng có thể không giải quyết vấn đề.

### 7.3. Đọc kết quả đo giả định

Bảng dưới chỉ minh họa cách diễn giải; các phương án không đại diện cho shape thương mại cụ thể. Các chỉ số được đo cùng workload trong giai đoạn ổn định.

| Phương án | CPU | RAM khả dụng | p95 | Quan sát bổ sung | Quyết định tiếp theo |
| --- | --- | --- | --- | --- | --- |
| A | Cao kéo dài | Còn đủ | 340 ms | Luồng xử lý bận, thời gian chờ DB thấp | Thử tăng CPU hoặc phân tải qua thêm instance |
| B | Vừa phải | Gần cạn | 310 ms | GC dày, có áp lực bộ nhớ | Kiểm tra cấp phát, heap và nhu cầu RAM |
| C | Thấp | Còn đủ | 420 ms | Phần lớn thời gian ở truy vấn DB | Phân tích truy vấn, pool và dịch vụ DB |
| D | Còn dự phòng | Còn dự phòng | 220 ms | Tỷ lệ lỗi trong mục tiêu | Đánh giá tiếp chi phí và thử tình huống lỗi |

D chưa đủ để kết luận cấu hình cuối cùng. Nhóm còn phải thử khi mất một instance, kiểm tra khả năng chịu tải của các instance còn lại và xem dịch vụ phụ thuộc có chịu được số kết nối phát sinh hay không.

### 7.4. Gắn quyết định Compute vào vận hành OCI

Sau khi chọn được cấu hình đáp ứng yêu cầu, lưu lại các quyết định triển khai:

- Compartment quản lý tài nguyên và policy cho nhóm vận hành.
- Subnet, đường truy cập, security rules và kết nối đến cơ sở dữ liệu.
- Cấu hình ứng dụng, image và kiến trúc CPU để có thể tạo lại instance nhất quán.
- Metrics, log và cảnh báo phục vụ phát hiện thiếu tài nguyên hoặc lỗi ứng dụng.
- Cách phân bố instance theo fault domain hoặc availability domain khi khả dụng và phù hợp với yêu cầu.
- Cách quản lý dữ liệu, backup và phục hồi; không giữ trạng thái quan trọng chỉ trong bộ nhớ của một instance ứng dụng.

Khi tự động hóa, khai báo shape và cấu hình liên quan thành tham số rõ ràng. Không tự thay đổi kiến trúc CPU khi thử một shape dự phòng nếu bộ phần mềm chưa được kiểm chứng tương thích.

## 8. Thực hành: thu thập dữ liệu trước khi đổi shape

Bài thực hành không yêu cầu tạo tài nguyên mới. Nếu đã có một máy Linux thử nghiệm mà bạn có quyền sử dụng, có thể thu thập thông tin bằng các lệnh đọc sau; một số công cụ cần được cài sẵn:

```bash
# Kiến trúc và CPU mà hệ điều hành nhìn thấy
uname -m
lscpu

# RAM, swap và các thiết bị lưu trữ
free -h
lsblk
df -h

# Lấy mẫu trạng thái CPU, bộ nhớ và I/O trong một khoảng ngắn
vmstat 1 10
```

Các lệnh này chỉ cung cấp góc nhìn từ hệ điều hành. Chúng không xác nhận đầy đủ service limits, quota, giá, capacity, loại tính phí hoặc toàn bộ thông số shape của OCI. Kết hợp với thông tin instance trong OCI và metrics ứng dụng để diễn giải đúng.

Trong môi trường ảo hóa, số CPU mà hệ điều hành nhìn thấy cũng không phải bằng chứng đủ để suy ra toàn bộ phần cứng máy chủ vật lý. Với `vmstat`, lưu ý mẫu đầu có thể biểu diễn trung bình từ khi khởi động; các mẫu tiếp theo mới phản ánh từng khoảng lấy mẫu.

Hoàn thành phiếu quyết định sau với dữ liệu thử nghiệm của bạn:

| Nội dung | Kết quả cần ghi |
| --- | --- |
| Workload và mục tiêu | Loại tác vụ, lưu lượng, độ trễ, tỷ lệ lỗi chấp nhận |
| Loại instance | VM hoặc bare metal, kèm lý do |
| Shape ứng viên | Tên đầy đủ, kiến trúc, CPU, RAM và tài nguyên đặc thù |
| Tương thích | Image, JDK, container, native library, agent |
| Ràng buộc triển khai | Region, availability domain, limits/quota, quyền và capacity |
| Kết quả đo | Throughput, latency, CPU, RAM, I/O, mạng |
| Chi phí và vận hành | Các tài nguyên tính phí liên quan, cách giám sát và tạo lại instance |
| Phục hồi | Hành vi khi mất một instance và nơi lưu dữ liệu bền vững |
| Quyết định | Giữ, tăng, giảm hoặc đổi ứng viên; nêu bằng chứng |

## 9. Những lỗi thường gặp

| Nhận định sai | Vì sao dễ gây chọn sai | Cách xử lý |
| --- | --- | --- |
| “Bare metal luôn nhanh và rẻ hơn VM” | Kết quả phụ thuộc workload, shape và mức sử dụng cả máy | Benchmark cùng mức dịch vụ và tính tổng chi phí |
| “Cùng số CPU thì hiệu năng bằng nhau” | Có thể khác đơn vị OCPU/vCPU, kiến trúc và thế hệ | Chuẩn hóa đơn vị rồi đo ứng dụng |
| “Java chạy ở đâu cũng giống nhau” | JDK, JNI, agent và binary đi kèm có thể phụ thuộc CPU | Kiểm tra toàn bộ gói triển khai trên kiến trúc đích |
| “Flexible nghĩa là cấu hình tùy ý” | CPU/RAM và tài nguyên đi kèm có giới hạn | Kiểm tra phạm vi hợp lệ của shape |
| “DenseIO thay cho thiết kế backup” | Ổ cục bộ có rủi ro gắn với vòng đời máy | Thiết kế sao chép, lưu bền vững và phục hồi |
| “CPU thấp thì có thể giảm cấu hình” | RAM, mạng hoặc I/O vẫn có thể đang là nút thắt | Đọc đồng thời chỉ số ứng dụng và hệ thống |
| “Một máy rất lớn đáp ứng luôn yêu cầu sẵn sàng” | Vẫn còn phụ thuộc vào một instance | Thiết kế nhiều bản sao và thử tình huống lỗi |
| “Còn quota thì chắc chắn tạo được máy” | Quota khác khả năng cung cấp phần cứng thực tế | Kiểm tra capacity và chuẩn bị phương án tương thích |

## 10. Tự kiểm tra

1. API Java thuần bytecode có chắc chuyển sang Arm chỉ bằng cách đổi shape không? Cần kiểm tra thêm những thành phần nào?
2. Một instance có CPU thấp nhưng p95 cao và thời gian chờ truy vấn lớn. Bạn sẽ thu thập thêm bằng chứng gì trước khi tăng CPU?
3. Khi nào NVMe cục bộ mang lại lợi ích rõ ràng, và dữ liệu trên đó cần được bảo vệ bằng cách nào?
4. Vì sao một bare metal instance lớn chưa đáp ứng yêu cầu tiếp tục phục vụ khi một máy hỏng?
5. Bạn cần ghi những thông tin nào để so sánh hai shape có đơn vị CPU khác nhau một cách có ý nghĩa?
6. Nếu shape phù hợp hết capacity tại vị trí triển khai, các phương án thay thế cần giữ những điều kiện tương thích nào?

Một quyết định chọn Compute có cơ sở phải nối được ba phần: **yêu cầu workload**, **đặc tính và ràng buộc của shape**, **kết quả đo cùng phương án vận hành**. Phiếu quyết định ở phần thực hành là đầu ra để trao đổi cấu hình với nhóm phát triển, vận hành và người quản lý chi phí.

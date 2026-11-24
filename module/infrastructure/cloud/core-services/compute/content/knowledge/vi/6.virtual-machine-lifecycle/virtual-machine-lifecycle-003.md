# Phân biệt stop, deallocate và hibernate giữa các mô hình dịch vụ

Khi một máy ảo không còn cần xử lý tải, đội vận hành có thể tắt máy để giảm chi phí, giải phóng năng lực tính toán hoặc giữ trạng thái để tiếp tục công việc sau đó. Tuy nhiên, các thao tác **stop**, **deallocate** và **hibernate** không có cùng ý nghĩa. Chúng khác nhau ở việc hệ điều hành có được tắt đúng quy trình hay không, năng lực CPU/RAM trên host có được giữ lại hay không, dữ liệu trong bộ nhớ có được lưu và khôi phục hay không, cũng như loại chi phí còn phát sinh.

Đối với **CLOUD_CORE_SERVICES_COMPUTE**, hiểu đúng vòng đời máy ảo giúp lựa chọn cách tạm ngừng workload, quản lý tài nguyên, bảo đảm dữ liệu và tối ưu chi phí vận hành. Cùng một từ như Stop có thể dẫn đến trạng thái và cách tính phí khác nhau giữa các nhà cung cấp. Vì vậy, cần đọc trạng thái thực tế của máy và chính sách của dịch vụ thay vì chỉ dựa vào tên nút bấm.

## 1. Vòng đời của một máy ảo

Một máy ảo thường đi qua các trạng thái như tạo mới, khởi động, đang chạy, tạm dừng, dừng, giải phóng năng lực hoặc bị xóa. Tên trạng thái và cách chuyển đổi phụ thuộc nền tảng.

Các hành động thường gặp:

- **Start:** yêu cầu nền tảng khởi động máy ảo và cấp năng lực tính toán.
- **Stop:** dừng hệ điều hành hoặc yêu cầu control plane dừng máy. Ý nghĩa về việc giữ hay giải phóng host có thể khác nhau.
- **Deallocate:** giải phóng năng lực tính toán đã cấp cho máy ảo, trong khi đối tượng máy và một số tài nguyên gắn kèm vẫn tồn tại.
- **Hibernate:** lưu nội dung bộ nhớ và trạng thái cần thiết vào vùng lưu trữ được nền tảng hỗ trợ, sau đó dừng năng lực tính toán để có thể khôi phục phiên làm việc.
- **Restart/Reboot:** khởi động lại hệ điều hành trong cùng vòng đời máy; không tương đương với việc tạo máy mới.
- **Delete/Terminate:** xóa đối tượng máy ảo. Việc ổ đĩa, IP và tài nguyên liên quan có bị xóa theo hay không phụ thuộc chính sách và cấu hình xóa cùng máy.

Có thể hình dung các chuyển đổi chính như sau:

~~~mermaid
stateDiagram-v2
    [*] --> Stopped: Tạo máy / chưa chạy
    Stopped --> Running: Start
    Running --> Stopped: Stop
    Running --> Deallocated: Deallocate
    Deallocated --> Running: Start / Allocate
    Running --> Hibernated: Hibernate
    Hibernated --> Running: Resume
    Running --> Deleted: Delete / Terminate
    Stopped --> Deleted: Delete
    Deallocated --> Deleted: Delete
    Hibernated --> Deleted: Delete
~~~

Sơ đồ là mô hình khái niệm. Một số nền tảng gộp Stop với deallocate; một số nền tảng dùng Suspend thay cho thuật ngữ Hibernate; một số dịch vụ không hỗ trợ trạng thái ngủ đông.

## 2. Stop: dừng máy hoặc dừng hệ điều hành

Stop thường được hiểu là yêu cầu máy ảo ngừng chạy. Tuy nhiên, cần phân biệt hai cách thực hiện:

1. **Shutdown từ bên trong guest OS:** người quản trị hoặc hệ điều hành yêu cầu tắt máy theo quy trình của Linux/Windows. Dịch vụ có cơ hội hoàn tất thao tác, đóng file và ghi dữ liệu.
2. **Stop từ control plane:** người dùng gọi API, CLI hoặc giao diện quản lý của nhà cung cấp để dừng máy. Nền tảng có thể thực hiện shutdown guest, sau đó giữ hoặc giải phóng năng lực host theo định nghĩa của dịch vụ.

Hai thao tác này có thể tạo ra trạng thái hiển thị giống nhau nhưng khác về phân bổ tài nguyên và tính phí.

### 2.1. Stop có giữ năng lực tính toán

Một số nền tảng có trạng thái máy đã tắt hệ điều hành nhưng vẫn giữ máy được phân bổ trên host. Trong trường hợp này:

- Máy không thực thi workload và CPU không được ứng dụng sử dụng.
- Năng lực tính toán hoặc slot trên host vẫn được giữ cho máy.
- Máy có thể khởi động lại nhanh hơn hoặc giữ một số ràng buộc phân bổ.
- Nhà cung cấp có thể tiếp tục tính phí compute vì năng lực vẫn được dành riêng.
- Ổ đĩa, IP, snapshot và các tài nguyên liên quan tiếp tục có chính sách tính phí riêng.

Azure minh họa rõ sự khác nhau giữa trạng thái **Stopped** (máy đã tắt trong guest nhưng còn được cấp phát) và **Stopped (deallocated)** (đã giải phóng năng lực host). Tắt hệ điều hành từ bên trong máy không tự động bảo đảm máy được deallocate.

### 2.2. Stop theo cách nền tảng giải phóng compute

Ở một số dịch vụ, thao tác Stop từ control plane đưa máy sang trạng thái ngừng chạy và giải phóng năng lực compute. Ví dụ, EC2 của AWS có trạng thái Stopped sau khi dừng instance; các khoản dùng compute của instance dừng, trong khi EBS volume và những tài nguyên khác vẫn có thể phát sinh phí.

Google Compute Engine cũng có trạng thái Stopped: máy không còn sử dụng vCPU/RAM như khi chạy, nhưng persistent disk và tài nguyên được giữ lại vẫn có thể được tính phí. Các chi tiết như địa chỉ IP tạm thời và local storage phụ thuộc loại tài nguyên.

Điều quan trọng là kiểm tra trạng thái cuối cùng và bảng giá của dịch vụ. Không nên suy ra một máy đã ngừng tính phí chỉ từ việc hệ điều hành không còn phản hồi.

### 2.3. Khi nào nên dùng Stop?

Stop phù hợp khi:

- Cần tắt ứng dụng theo quy trình để bảo trì hoặc kiểm tra.
- Cần dừng tạm một máy trong khoảng thời gian ngắn.
- Muốn giữ đối tượng máy và ổ đĩa để khởi động lại sau đó.
- Không cần giữ nội dung RAM của các tiến trình đang chạy.
- Dịch vụ cung cấp trạng thái Stop với mức chi phí và thời gian khởi động phù hợp.

Trước khi Stop, nên drain request, dừng nhận tác vụ mới, hoàn tất hoặc lưu checkpoint của job, flush dữ liệu và xác minh dịch vụ đã shutdown đúng cách.

## 3. Deallocate: giải phóng năng lực host

**Deallocate** là hành động yêu cầu nền tảng giải phóng năng lực tính toán đã dành cho máy ảo. Trong khi Stop có thể chỉ dừng guest OS, Deallocate nói rõ rằng CPU/RAM trên host không còn được giữ riêng cho máy đó.

Thông thường, sau deallocate:

- Máy ảo không chạy và không có vCPU/RAM được cấp trên host.
- Nền tảng có thể dùng năng lực vừa giải phóng cho workload khác.
- Đối tượng máy ảo và ổ đĩa bền vững có thể vẫn tồn tại.
- Chi phí compute thường dừng trong thời gian deallocated.
- Chi phí cho disk, snapshot, IP tĩnh, license hoặc tài nguyên liên quan có thể tiếp tục.
- Khi start lại, nền tảng cần tìm năng lực phù hợp; máy có thể được đặt trên host khác.

Deallocate không đồng nghĩa với Delete. Máy đã deallocate vẫn có thể được start lại nếu cấu hình và quota còn phù hợp.

### 3.1. Tài nguyên nào được giữ lại?

| Thành phần | Sau deallocate thường như thế nào? | Điều cần xác minh |
| --- | --- | --- |
| Đối tượng máy ảo | Vẫn tồn tại | Trạng thái, cấu hình và quyền quản lý |
| vCPU/RAM trên host | Được giải phóng | Thời điểm hoàn tất deallocate |
| OS disk và data disk bền vững | Thường được giữ | Chính sách xóa cùng máy và phí lưu trữ |
| Local/ephemeral disk | Có thể mất dữ liệu | Cam kết của loại máy và loại đĩa |
| Private IP | Thường được giữ trong cùng mạng ảo | Chính sách địa chỉ của nền tảng |
| Public IP động | Có thể được giải phóng | Cần IP tĩnh nếu địa chỉ phải ổn định |
| IP tĩnh hoặc tài nguyên đặt trước | Có thể vẫn được giữ và tính phí | Phí giữ địa chỉ và phạm vi gắn kết |
| Snapshot, backup, disk encryption key | Theo vòng đời riêng | Chính sách lưu giữ và quyền truy cập |

Không có một quy tắc chung áp dụng cho mọi nhà cung cấp và mọi loại disk. Trước khi deallocate, cần phân biệt dữ liệu trên persistent disk với dữ liệu tạm nằm trên local SSD, temporary disk hoặc RAM.

### 3.2. Khi nào nên dùng Deallocate?

Deallocate phù hợp khi:

- Máy phát triển, kiểm thử hoặc môi trường demo không cần chạy ngoài giờ.
- Workload có thể dừng và khởi động lại mà không cần giữ trạng thái tiến trình.
- Cần giải phóng compute để giảm chi phí trong thời gian nhàn rỗi.
- Có thể chấp nhận thời gian chờ cấp phát lại khi khởi động.
- Dữ liệu cần giữ đã nằm trên storage bền vững hoặc đã được sao lưu.

Deallocate đặc biệt hữu ích cho workload có lịch chạy rõ ràng, chẳng hạn môi trường kiểm thử chỉ hoạt động trong giờ làm việc. Với workload cần phản hồi tức thời hoặc phải giữ kết nối liên tục, cần tính đến thời gian cấp phát lại và khởi động dịch vụ.

## 4. Hibernate: lưu trạng thái bộ nhớ để tiếp tục

**Hibernate** là cơ chế lưu nội dung RAM và trạng thái cần thiết của máy vào vùng lưu trữ được hỗ trợ, sau đó dừng máy. Khi resume, nền tảng khôi phục trạng thái đã lưu để hệ điều hành và tiến trình có thể tiếp tục từ phiên trước.

Hibernate khác với Stop hoặc Deallocate thông thường ở chỗ mục tiêu là giữ trạng thái bộ nhớ:

- Nội dung RAM được ghi vào storage hoặc vùng lưu trữ do nền tảng quản lý.
- Năng lực CPU/RAM trên host thường được giải phóng trong lúc máy ngủ đông.
- Khi resume, nền tảng nạp lại trạng thái bộ nhớ đã lưu.
- Ổ đĩa và vùng lưu trạng thái hibernate tiếp tục chiếm dung lượng và có thể bị tính phí.
- Việc khôi phục phụ thuộc hỗ trợ của loại máy, hệ điều hành, kích thước RAM và cấu hình disk.

Hibernate thường có thời gian quay lại nhanh hơn việc khởi động mới và nạp lại ứng dụng từ đầu, nhưng không đảm bảo resume luôn thành công hoặc mọi kết nối bên ngoài vẫn còn hiệu lực.

### 4.1. Hibernate lưu gì và không bảo đảm điều gì?

Hibernate thường nhằm lưu trạng thái hệ điều hành và bộ nhớ tiến trình tại thời điểm ngủ đông. Tuy nhiên, nó không thay thế backup dữ liệu ứng dụng:

- Dữ liệu đã ghi bền vững trên disk tiếp tục tuân theo cơ chế lưu trữ của disk.
- Dữ liệu chỉ nằm trong RAM có thể được giữ trong snapshot hibernate, nhưng khả năng khôi phục phụ thuộc nền tảng và tính toàn vẹn của snapshot.
- Kết nối TCP, phiên đăng nhập từ xa, lease, token và trạng thái phía dịch vụ khác có thể hết hạn trong lúc máy ngủ.
- Dữ liệu trên ephemeral storage vẫn có rủi ro theo vòng đời của tài nguyên đó.
- Các thao tác đang ghi dữ liệu hoặc giao dịch dở dang cần được ứng dụng xử lý an toàn trước khi hibernate.

Sau khi resume, ứng dụng nên kiểm tra lại kết nối database, message broker, DNS, token và các dependency có thời hạn. Hệ thống phân tán cần có khả năng reconnect và phục hồi phiên làm việc.

### 4.2. Điều kiện và giới hạn hỗ trợ

Hibernate thường chỉ được hỗ trợ trên một tập hợp loại máy, hệ điều hành và cấu hình cụ thể. Các điều kiện có thể gồm:

- Loại instance hoặc VM size phải hỗ trợ hibernate.
- Hệ điều hành và kernel/agent phải tương thích.
- OS disk hoặc vùng lưu trạng thái phải có đủ dung lượng và đáp ứng yêu cầu mã hóa.
- Kích thước RAM không vượt giới hạn của dịch vụ.
- Có thể cần bật tùy chọn hibernate ngay khi tạo máy.
- Một số cấu hình GPU, local disk, confidential computing hoặc thiết bị đặc biệt có thể không được hỗ trợ.
- Có thể có giới hạn thời gian lưu trạng thái hoặc số lần resume.

Nếu hibernate thất bại, nền tảng có thể không lưu được trạng thái bộ nhớ. Cần có phương án fallback sang shutdown/deallocate bình thường và khôi phục ứng dụng từ dữ liệu bền vững.

## 5. So sánh Stop, Deallocate và Hibernate

| Tiêu chí | Stop | Deallocate | Hibernate |
| --- | --- | --- | --- |
| Guest OS | Được tắt hoặc dừng theo cách của nền tảng | Thường được shutdown trước khi giải phóng host | Lưu trạng thái bộ nhớ theo cơ chế hibernate |
| CPU/RAM trên host | Có thể còn được giữ hoặc được giải phóng tùy dịch vụ | Được giải phóng | Thường được giải phóng |
| Nội dung RAM | Không được bảo đảm giữ lại | Không giữ trạng thái RAM | Được lưu để khôi phục nếu thành công |
| Khởi động lại | Boot hệ điều hành từ đầu | Cấp phát host rồi boot từ đầu | Resume từ trạng thái đã lưu |
| Disk bền vững | Thường giữ | Thường giữ | Giữ disk và vùng lưu trạng thái hibernate |
| Local/ephemeral data | Tùy nền tảng và loại disk | Có thể mất | Phụ thuộc loại disk và cách hibernate |
| Chi phí compute | Phụ thuộc việc giữ hay giải phóng host | Thường dừng | Thường dừng khi đã vào trạng thái hibernate |
| Chi phí storage/IP | Có thể tiếp tục | Có thể tiếp tục | Có thể tiếp tục, thêm dung lượng trạng thái hibernate |
| Trường hợp phù hợp | Dừng ngắn, không cần giữ RAM | Tạm ngừng dài hơn để tiết kiệm compute | Cần tiếp tục phiên làm việc đang mở |

Điểm khác biệt quan trọng nhất là **Deallocate giải phóng năng lực host**, còn **Hibernate lưu trạng thái RAM để resume**. Stop là thuật ngữ dễ gây nhầm nhất vì ý nghĩa của nó phụ thuộc hành động được gọi từ guest OS hay control plane và cách nhà cung cấp triển khai.

## 6. Cách các nhà cung cấp thể hiện trạng thái

Các nền tảng lớn có cách đặt tên và tính phí khác nhau. Bảng sau chỉ mô tả cách hiểu phổ biến; chi tiết có thể thay đổi theo loại máy, vùng, hệ điều hành và chính sách sản phẩm.

| Khái niệm | AWS EC2 | Microsoft Azure VM | Google Compute Engine |
| --- | --- | --- | --- |
| Dừng thông thường | Stop instance đưa instance sang trạng thái Stopped; compute usage của instance dừng | Có trạng thái Stopped còn allocated nếu shutdown từ guest; compute có thể tiếp tục bị tính phí | Stop VM đưa máy về trạng thái Stopped; vCPU/RAM không còn chạy |
| Giải phóng compute | Stop instance thường giải phóng năng lực host; không có thao tác riêng tên Deallocate phổ biến như Azure | Deallocate giải phóng năng lực host và dừng phí compute | Stop giải phóng năng lực compute; không dùng thuật ngữ Deallocate phổ biến |
| Giữ trạng thái RAM | EC2 hỗ trợ Stop with hibernation với loại instance và cấu hình đủ điều kiện | Azure hỗ trợ Hibernate trên các VM size và cấu hình được hỗ trợ | Suspend/resume là cơ chế gần tương đương để lưu trạng thái bộ nhớ; phạm vi hỗ trợ và phí khác hibernate |
| Tài nguyên còn phí | EBS, địa chỉ IP và tài nguyên liên quan theo chính sách | Managed disk, IP tĩnh và tài nguyên liên quan theo chính sách | Persistent disk, IP tĩnh và tài nguyên liên quan theo chính sách |

Một vài lưu ý khi đọc bảng:

- AWS EC2 có thể dừng instance mà không giữ RAM; nếu bật hibernation và instance đủ điều kiện, nội dung RAM được lưu trên EBS root volume trước khi instance chuyển sang trạng thái dừng.
- Azure phân biệt shutdown trong guest với deallocate ở control plane. Nút Stop trong portal/API có thể thực hiện deallocation tùy thao tác; cần xem trạng thái hiển thị là Stopped hay Stopped (deallocated).
- Google Compute Engine sử dụng Suspend/Resume để lưu trạng thái máy trong khi dừng cấp CPU. Đây là khái niệm gần với hibernate, nhưng cách tính phí bộ nhớ lưu trạng thái, giới hạn và điều kiện hỗ trợ cần kiểm tra theo tài liệu của loại VM.

Không nên chuyển một quy trình từ nhà cung cấp này sang nhà cung cấp khác chỉ bằng cách thay tên API. Hãy xác minh trạng thái sau thao tác, loại tài nguyên được giữ, thời điểm ngừng compute billing và điều kiện resume của nền tảng đích.

## 7. Khác biệt giữa IaaS, nền tảng quản lý và container/serverless

Các thao tác trên chủ yếu mô tả vòng đời máy ảo trong IaaS. Khi chuyển sang dịch vụ quản lý cao hơn, người dùng thường điều khiển workload hoặc replica thay vì trực tiếp điều khiển host.

### 7.1. IaaS: người dùng quản lý máy ảo

Trong IaaS, đội vận hành thường quyết định khi nào start, stop, deallocate hoặc hibernate máy. Người dùng quản lý guest OS, disk, agent, ứng dụng và quy trình shutdown.

Các quyết định cần cân nhắc:

- Máy có cần giữ RAM để tiếp tục một phiên xử lý hay không?
- Disk nào cần giữ và disk nào là dữ liệu tạm?
- IP hoặc network identity có phải duy trì sau khi deallocate không?
- Có cần host capacity sẵn sàng để đáp ứng thời gian khởi động không?
- Ứng dụng có thể khôi phục từ checkpoint hoặc queue thay vì hibernate không?

### 7.2. Managed instance group và autoscaling

Với managed instance group, autoscaling group hoặc dịch vụ quản lý nhóm máy, nền tảng có thể thay thế hoặc xóa instance theo chính sách. Scale-in thường kết thúc một máy và không giữ trạng thái RAM của nó.

Nếu workload cần tiếp tục sau khi một instance bị thay thế, ứng dụng nên lưu trạng thái vào database, object storage, queue hoặc checkpoint bên ngoài. Hibernate một instance không phải chiến lược mặc định cho autoscaling vì scheduler cần quyền thay thế máy và phân bổ workload linh hoạt.

### 7.3. Container và Kubernetes

Container thường không có thao tác deallocate hoặc hibernate theo nghĩa máy ảo:

- Dừng container/pod thường kết thúc tiến trình và giải phóng tài nguyên node.
- Khi tạo container mới từ image, tiến trình bắt đầu lại; trạng thái RAM cũ không tự động được khôi phục.
- Persistent volume có thể giữ dữ liệu nếu được cấu hình đúng; filesystem tạm của container có thể mất.
- Kubernetes có thể scale workload về zero replica, nhưng điều đó không nhất thiết giải phóng node nếu node vẫn được giữ trong cluster.
- Cluster autoscaler có thể thu nhỏ node pool sau khi pod đã được dời hoặc kết thúc, tùy cấu hình.

Nếu cần tiếp tục công việc, ứng dụng container nên hỗ trợ checkpoint, graceful termination và phục hồi từ storage bền vững.

### 7.4. PaaS và serverless

Ở PaaS hoặc serverless, nhà cung cấp quản lý máy chủ nền. Người dùng thường điều khiển số instance, số replica, mức concurrency, lịch chạy hoặc scale-to-zero.

Scale-to-zero nghĩa là không còn instance ứng dụng đang phục vụ trong một khoảng thời gian; nó không đồng nghĩa với Hibernate một máy ảo cụ thể. Runtime có thể được khởi tạo lại ở lần gọi tiếp theo, và bộ nhớ tiến trình trước đó không được bảo đảm tồn tại. Một số nền tảng có thể giữ môi trường thực thi ấm trong thời gian ngắn, nhưng ứng dụng không nên dựa vào điều đó để lưu trạng thái nghiệp vụ.

## 8. Ảnh hưởng đến chi phí

Tắt máy không có nghĩa toàn bộ chi phí của máy bằng không. Khi compute dừng, các tài nguyên còn tồn tại vẫn có thể bị tính phí.

Các thành phần cần xem:

| Thành phần | Khi máy ngừng compute |
| --- | --- |
| vCPU/RAM instance | Thường ngừng tính phí khi deallocate hoặc ở trạng thái stopped theo mô hình của nhà cung cấp |
| OS disk và data disk | Thường vẫn tính phí theo dung lượng/cấp hiệu năng |
| Snapshot và backup | Tiếp tục tính phí theo dung lượng, thời gian lưu và loại dịch vụ |
| Public IP tĩnh | Có thể vẫn tính phí khi không gắn hoặc khi giữ tài nguyên |
| License phần mềm | Có thể tính theo giờ, theo core hoặc theo thỏa thuận riêng |
| NAT, load balancer, gateway và dịch vụ quản lý | Có vòng đời và cách tính phí riêng |
| Hibernate state | Có thể dùng dung lượng lưu trữ bổ sung hoặc có khoản phí riêng |

Một cách ước lượng đơn giản:

\[
\text{Chi phí khi dừng} =
\text{Disk} + \text{Snapshot} + \text{IP} +
\text{License} + \text{Tài nguyên liên quan}
\]

Chi phí compute tiết kiệm được phụ thuộc thời lượng deallocate, giá máy theo giờ, thời gian khởi động lại và chi phí vận hành lịch tự động. Với một máy chỉ tắt vài phút, khoản tiết kiệm có thể nhỏ so với độ trễ và công sức khởi động. Với môi trường phát triển tắt qua đêm hoặc cuối tuần, deallocate thường có lợi hơn.

Hibernate có thể tiết kiệm compute nhưng tăng chi phí lưu trạng thái RAM. Nếu dung lượng RAM lớn và thời gian ngủ ngắn, cần so sánh chi phí lưu trạng thái với lợi ích rút ngắn thời gian khôi phục.

## 9. Bảo vệ dữ liệu trước khi dừng hoặc ngủ đông

Trước khi chuyển trạng thái, cần phân loại dữ liệu theo nơi lưu:

- **Dữ liệu bền vững:** database hoặc file trên persistent disk, object storage và dịch vụ lưu trữ có cam kết độ bền.
- **Dữ liệu tạm:** cache, temporary filesystem, local ephemeral disk và dữ liệu trong RAM.
- **Trạng thái tiến trình:** bộ nhớ heap, stack, file descriptor, lock, socket và phiên làm việc.

Stop hoặc deallocate thông thường không bảo đảm giữ trạng thái tiến trình. Hibernate có thể lưu RAM, nhưng vẫn cần bảo đảm ứng dụng không ở giữa một giao dịch chưa hoàn tất và các dependency có thể reconnect.

Quy trình an toàn trước khi dừng:

1. Ngừng nhận request hoặc tác vụ mới.
2. Drain load balancer và queue theo thời gian cho phép.
3. Hoàn tất giao dịch hoặc ghi checkpoint cho job dài.
4. Flush dữ liệu và đóng file theo quy trình của ứng dụng.
5. Ghi lại trạng thái vận hành cần thiết vào nơi bền vững.
6. Thực hiện shutdown hoặc hibernate đúng cách.
7. Xác minh trạng thái cuối cùng từ control plane.

Với workload cơ sở dữ liệu, cần dùng quy trình shutdown được hỗ trợ bởi hệ quản trị cơ sở dữ liệu. Không nên cưỡng bức tắt máy trong lúc đang ghi dữ liệu trừ khi đã đánh giá khả năng phục hồi và chấp nhận rủi ro.

## 10. Quy trình chọn hành động theo workload

| Nhu cầu | Hành động thường phù hợp | Lý do |
| --- | --- | --- |
| Bảo trì ngắn, cần shutdown sạch | Stop | Dừng hệ điều hành theo quy trình |
| Máy dev/test nhàn rỗi nhiều giờ | Deallocate hoặc Stop có giải phóng compute | Tiết kiệm chi phí host khi không cần chạy |
| Ứng dụng cần tiếp tục phiên làm việc trong RAM | Hibernate nếu được hỗ trợ | Khôi phục trạng thái tiến trình |
| Worker xử lý batch có checkpoint | Deallocate sau khi lưu checkpoint | Có thể khởi động worker khác và tiếp tục từ dữ liệu bền vững |
| Web/API stateless trong nhóm autoscaling | Scale-in/terminate theo chính sách | Có thể tạo instance thay thế khi tải tăng |
| Container có trạng thái nghiệp vụ | Graceful termination và lưu trạng thái bên ngoài | Container mới không khôi phục RAM của container cũ |
| Serverless ít request | Scale-to-zero theo chính sách nền tảng | Không cần quản lý vòng đời VM |

Quyết định cuối cùng cần xét thời gian ngừng, RTO, RPO, độ bền dữ liệu, yêu cầu latency và tổng chi phí.

## 11. Ví dụ: tạm ngừng môi trường kiểm thử ngoài giờ

Một nhóm phát triển có máy ảo chạy môi trường kiểm thử tích hợp. Máy chỉ được dùng trong giờ làm việc, có OS disk và data disk lưu cấu hình cùng dữ liệu kiểm thử. Các log quan trọng được đẩy sang hệ thống tập trung.

Nhóm thiết kế lịch tắt như sau:

1. Trước giờ dừng, pipeline thông báo cho người dùng và ngừng nhận bài kiểm thử mới.
2. Worker hoàn tất job đang chạy hoặc ghi checkpoint vào storage bền vững.
3. Ứng dụng đóng kết nối database và shutdown hệ điều hành sạch.
4. Automation gọi thao tác deallocate và xác minh máy ở trạng thái đã giải phóng compute.
5. OS disk và data disk tiếp tục được giữ; IP tĩnh được giữ nếu cần truy cập bằng địa chỉ cố định.
6. Trước giờ làm việc, automation start máy, kiểm tra agent, disk, network và health endpoint.
7. Nếu máy không sẵn sàng trong thời hạn quy định, hệ thống gửi cảnh báo và chuyển sang quy trình xử lý.

Nhóm không cần hibernate vì ứng dụng có thể khởi động lại từ trạng thái lưu bền vững. Nếu máy có phiên phân tích dài cần giữ tiến trình và thời gian khởi tạo lại rất lớn, nhóm có thể đánh giá hibernate trên loại máy hỗ trợ, sau khi kiểm thử tính toàn vẹn và chi phí lưu RAM.

## 12. Tự động hóa stop, deallocate và hibernate

Lịch tự động giúp tránh để máy nhàn rỗi chạy liên tục, nhưng phải có cơ chế bảo vệ workload.

Một workflow có thể gồm:

~~~mermaid
flowchart TD
    A["Đến thời điểm tắt theo lịch"] --> B{"Máy có workload đang chạy?"}
    B -- "Có" --> C["Drain request và dừng nhận job"]
    C --> D["Hoàn tất job hoặc ghi checkpoint"]
    D --> E{"Cần giữ trạng thái RAM?"}
    B -- "Không" --> E
    E -- "Có" --> F{"VM có hỗ trợ hibernate?"}
    F -- "Có" --> G["Hibernate và xác minh trạng thái"]
    F -- "Không" --> H["Shutdown/Deallocate theo phương án phục hồi"]
    E -- "Không" --> H
    G --> I["Theo dõi trạng thái và chi phí"]
    H --> I
~~~

Các điểm kiểm soát cần có:

- Chỉ xử lý máy thuộc nhóm được phép tự động dừng.
- Loại trừ máy đang phục vụ production hoặc đang chạy job không thể gián đoạn.
- Dùng tag/label hoặc lịch được quản lý để xác định chủ sở hữu và khung giờ.
- Ghi log hành động, trạng thái trước/sau và kết quả xác minh.
- Có timeout cho drain và shutdown; khi quá hạn, áp dụng chính sách fallback đã phê duyệt.
- Tránh hai automation cùng thao tác một máy tại một thời điểm.
- Kiểm tra máy có tự khởi động lại bởi autoscaling, policy hoặc lịch khác hay không.
- Có cơ chế cảnh báo nếu start hoặc resume thất bại.

Không nên dùng lịch deallocate đơn giản cho máy có vai trò điều phối, quorum, database primary hoặc workload có yêu cầu sẵn sàng liên tục nếu chưa thiết kế cơ chế chuyển vai trò.

## 13. Các sai lầm thường gặp

- Cho rằng shutdown trong guest OS luôn giải phóng compute.
- Nhầm Deallocate với Delete và xóa nhầm tài nguyên cần giữ.
- Nghĩ rằng stop/deallocate giữ nguyên dữ liệu trên mọi loại disk.
- Không kiểm tra IP động có bị giải phóng sau khi dừng máy hay không.
- Giả định hibernate bảo đảm mọi kết nối và phiên làm việc bên ngoài tiếp tục.
- Không kiểm tra điều kiện hỗ trợ hibernate của VM size, OS và disk.
- Chỉ tính phần tiết kiệm compute mà quên disk, IP, snapshot, license và dịch vụ liên quan.
- Tự động tắt máy khi job vẫn đang ghi dữ liệu hoặc đang giữ vai trò quan trọng.
- Không kiểm thử quy trình start/resume và phục hồi trước khi đưa lịch vào production.
- Dùng scale-to-zero của container/serverless như thể đó là hibernate của một VM.

## 14. Nguyên tắc vận hành

1. **Đọc trạng thái thật:** xác minh trạng thái từ control plane sau mỗi thao tác.
2. **Tách Stop khỏi Deallocate:** xác định rõ máy còn giữ năng lực host hay đã giải phóng.
3. **Dùng Hibernate có điều kiện:** chỉ bật khi nền tảng, loại máy và hệ điều hành hỗ trợ, đồng thời đã kiểm thử resume.
4. **Giữ dữ liệu bền vững:** lưu dữ liệu nghiệp vụ và checkpoint ngoài RAM, đặc biệt với workload có thể bị thay thế.
5. **Tính đủ chi phí:** compute, disk, snapshot, IP, license và tài nguyên phụ trợ.
6. **Thiết kế phục hồi:** kiểm tra reconnect, health check, start/resume và phương án fallback.
7. **Tự động hóa có bảo vệ:** drain workload, kiểm tra vai trò, ghi log và giới hạn phạm vi máy được phép dừng.
8. **Tôn trọng mô hình dịch vụ:** IaaS cho phép quản lý vòng đời VM; container và serverless thường yêu cầu lưu trạng thái ở tầng ứng dụng.

Stop, deallocate và hibernate là ba cách quản lý trạng thái máy với mục tiêu khác nhau. Chọn đúng thao tác đòi hỏi hiểu năng lực host có được giữ hay không, dữ liệu nào còn tồn tại, chi phí nào tiếp tục và ứng dụng sẽ phục hồi ra sao. Khi các yếu tố này được đưa vào quy trình vận hành, đội kỹ thuật có thể tiết kiệm compute mà vẫn bảo đảm dữ liệu, khả năng phục hồi và trải nghiệm dịch vụ.

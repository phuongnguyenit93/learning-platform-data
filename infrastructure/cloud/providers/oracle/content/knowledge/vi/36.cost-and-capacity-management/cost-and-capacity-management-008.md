# Cloud Advisor và phát hiện tài nguyên sử dụng kém hiệu quả

## 1. Mục tiêu bài học

Trong chương **Chi phí và quản lý năng lực** của module Oracle Cloud Infrastructure (OCI), Cloud Advisor giúp tìm những tài nguyên đáng được điều tra để giảm lãng phí. Tuy nhiên, CPU thấp, volume không gắn hoặc một khoản tiết kiệm ước tính chưa đủ để quyết định thu nhỏ hay xóa tài nguyên.

Bài học này hướng dẫn cách đặt khuyến nghị vào đúng tenancy, compartment và workload; kiểm chứng bằng số liệu giám sát; thực hiện thay đổi có kiểm soát; rồi đối chiếu hiệu quả thực tế. Phạm vi bao gồm Compute, lưu trữ và các workload cơ sở dữ liệu Oracle, gắn với IAM, tính sẵn sàng và khả năng tự động hóa.

Sau bài học, bạn có thể:

- Phân biệt dấu hiệu sử dụng thấp với phần năng lực thực sự có thể cắt giảm.
- Kiểm tra quyền truy cập và chất lượng dữ liệu trước khi đánh giá khuyến nghị.
- Chọn phương án xử lý theo từng loại tài nguyên và yêu cầu của ứng dụng.
- Lập kế hoạch thực hiện, quay lui và đo mức tiết kiệm.
- Dùng OCI CLI để thu thập khuyến nghị phục vụ danh sách công việc tối ưu hóa.

## 2. Vai trò của Cloud Advisor

Cloud Advisor phân tích tài nguyên OCI và đưa ra khuyến nghị về chi phí, hiệu năng và tính sẵn sàng. Dịch vụ quét hằng ngày, tổng hợp dữ liệu từ các region đã đăng ký về home region của tenancy. Kết quả vì thế phụ thuộc dữ liệu quan sát và có độ trễ. Xem [About Cloud Advisor](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Concepts/cloudadvisoroverview.htm).

Hãy xem mỗi khuyến nghị là **một giả thuyết vận hành có bằng chứng ban đầu**. Ví dụ, một VM có thể dùng cấu hình nhỏ hơn. Người vận hành cần xác minh ứng dụng chạy trên đó, tải đỉnh, lịch batch và yêu cầu chịu lỗi trước khi chốt cấu hình đích.

Một quy trình tối ưu hóa cần lần lượt trả lời:

1. **Tài nguyên nào đáng điều tra?** Dùng Cloud Advisor để thu hẹp danh sách.
2. **Mức sử dụng thấp có đại diện cho nhu cầu thật không?** Dùng telemetry và bối cảnh nghiệp vụ để giải thích.
3. **Thay đổi nào khả thi và đem lại lợi ích?** Đánh giá phụ thuộc, khả năng phục hồi và chi phí.
4. **Kết quả có đạt yêu cầu không?** Đo lại cả dịch vụ và khoản chi sau thay đổi.

### 2.1. Phân công công việc giữa các công cụ

| Công cụ hoặc dữ liệu | Câu hỏi cần giải quyết | Cách dùng trong quy trình |
|---|---|---|
| Cloud Advisor | Cơ hội tối ưu nào cần điều tra? | Tạo danh sách ứng viên |
| Monitoring và số liệu ứng dụng | Workload dùng năng lực như thế nào? | Kiểm chứng CPU, RAM, mạng, I/O, latency và lỗi |
| Cost Analysis, dữ liệu sử dụng và hóa đơn | Phạm vi tài nguyên đang phát sinh khoản chi nào? | Đối chiếu ước tính với chi phí thực tế |
| Budget và cảnh báo ngân sách | Chi tiêu có vượt mức dự kiến không? | Bổ sung mức độ khẩn cấp cho việc điều tra |
| Service limits và compartment quotas | Việc cấp phát có nằm trong giới hạn cho phép không? | Kiểm tra điều kiện thay đổi và mở rộng trở lại |
| Audit, lịch sử triển khai và IaC | Ai thay đổi gì, cấu hình mong muốn nằm ở đâu? | Truy vết và giữ cấu hình sau tối ưu nhất quán |

Hạn mức cấp phát và sức chứa phần cứng khả dụng cần được kiểm tra riêng. Một compartment còn quota chưa chứng minh shape cần dùng đang có sẵn ở vị trí triển khai.

## 3. Mức sử dụng thấp chưa đồng nghĩa với lãng phí

**Underutilized** mô tả mức sử dụng thấp so với năng lực đã cấp trong một khoảng quan sát. **Overprovisioned** mô tả cấu hình vượt nhu cầu đã được xác minh. Hai nhận định thường liên quan nhưng cần thêm bằng chứng để đi từ nhận định thứ nhất sang thứ hai.

Một node chỉ dùng 8% CPU có thể phải tiếp nhận toàn bộ tải khi node khác hỏng. Một VM nhàn rỗi giữa tháng có thể chạy đối soát vào cuối tháng. Ngược lại, môi trường thử nghiệm đã hết vòng đời và không còn phục vụ công việc nào là ứng viên thu hồi rõ hơn.

Các khuyến nghị chi phí của Cloud Advisor có thể liên quan tới Compute hoặc cơ sở dữ liệu dư năng lực, block/boot volume không gắn, load balancer dư băng thông tối thiểu và bucket thiếu lifecycle rule. Phạm vi hỗ trợ cần đối chiếu với tài nguyên hiện tại. Xem [Cost Management Recommendations](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Concepts/recommendations-costmanagement.htm).

Khi điều tra, nên phân biệt các dạng sau:

| Dạng cần điều tra | Ví dụ | Bằng chứng bổ sung | Phương án có thể phù hợp |
|---|---|---|---|
| Cấp thừa năng lực | VM nhiều CPU hoặc RAM hơn nhu cầu | Tải đỉnh, bộ nhớ, mạng, yêu cầu ứng dụng | Giảm từng bước trong phạm vi hỗ trợ |
| Tài nguyên hết vòng đời | Volume còn lại sau thử nghiệm | Chủ sở hữu, dữ liệu, phụ thuộc, thời hạn giữ lại | Thu hồi sau khi xác minh |
| Lịch hoạt động chưa phù hợp | Môi trường kiểm thử chỉ dùng giờ hành chính | Tác vụ nền, múi giờ người dùng, thời gian khởi động | Đánh giá lịch chạy và phần chi phí vẫn tồn tại |
| Cách lưu trữ chưa phù hợp | Dữ liệu cũ ít được đọc | Tần suất truy cập, thời gian khôi phục, retention | Thiết kế vòng đời dữ liệu |
| Quan sát chưa đầy đủ | VM thiếu số liệu RAM | Agent, plugin, kết nối Monitoring | Khôi phục telemetry trước |
| Dự phòng có chủ đích | Node chờ failover | Yêu cầu chịu lỗi và kết quả diễn tập | Giữ năng lực có lý do, hẹn đánh giá lại |

Bảng này là khung điều tra vận hành, không phải cam kết rằng Cloud Advisor tự phát hiện hoặc tự xử lý mọi ví dụ trong bảng.

## 4. Kiểm tra phạm vi, IAM và dữ liệu đầu vào

### 4.1. Nhận diện đúng tài nguyên

Dùng OCID làm định danh chính. Tên hiển thị giúp đọc nhưng có thể trùng hoặc bị đổi. Một phiếu điều tra nên ghi:

- Tenancy, compartment, region và OCID tài nguyên.
- Availability domain hoặc fault domain khi liên quan tới năng lực và chịu lỗi.
- Ứng dụng, môi trường, chủ sở hữu kỹ thuật và đơn vị chịu chi phí.
- Loại khuyến nghị, thời điểm lấy dữ liệu và khoảng quan sát.
- Cấu hình hiện tại, cấu hình đề xuất và thay đổi gần đây.

Nếu chỉ nhìn được một compartment, kết luận cũng chỉ có giá trị trong phạm vi đó. Với nhiều tenancy, ghi rõ tenancy đang phân tích và tenancy sở hữu tài nguyên cần thay đổi.

### 4.2. Thiết kế quyền xem và quyền thực hiện

Resource family IAM của Cloud Advisor là **optimizer-api-family**. Việc dùng Advisor và sửa tài nguyên đích cần quyền phù hợp; quyền truy cập Advisor không thay thế quyền thay đổi Compute, storage hoặc database. Xem [Required IAM policies](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Tasks/implementing-iam-policies.htm).

Có thể phân trách nhiệm như sau:

| Vai trò trong quy trình | Trách nhiệm | Phạm vi quyền nên thiết kế |
|---|---|---|
| Người phân tích | Đọc khuyến nghị, số liệu và chi phí | Đủ đọc dữ liệu trong phạm vi được giao |
| Chủ ứng dụng | Giải thích nhu cầu và chấp nhận kết quả | Đọc số liệu ứng dụng, xác nhận mục tiêu dịch vụ |
| Người vận hành | Thực hiện thay đổi đã thống nhất | Quyền sửa đúng dịch vụ và compartment |
| Quản trị IAM | Quản lý policy, xử lý thiếu quyền | Quyền theo trách nhiệm quản trị của tổ chức |

Đây là mô hình phân công được đề xuất cho bài học, không phải bộ role mà Cloud Advisor tự tạo.

Metadata mở rộng có thể được kiểm soát bằng **optimizer-resource-metadata**. Thông báo **No access** cần được xử lý như vấn đề quyền truy cập. Xem [Additional Required Permissions](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Concepts/additional_required_permissions.htm).

### 4.3. Thiếu metric khác với mức dùng bằng 0

Với metric Compute do agent phát, cần Oracle Cloud Agent và plugin **Compute Instance Monitoring** đang hoạt động. Có thể kiểm tra dữ liệu trong namespace **oci_computeagent**. VM cần kết nối tới Monitoring; tài liệu Oracle hướng dẫn dùng service gateway cho trường hợp subnet riêng không dùng public IP. Xem [Enabling Monitoring for Compute Instances](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/enablingmonitoring.htm).

Trước khi đọc một đường trung bình, hãy kiểm tra:

1. Có điểm dữ liệu trong những giờ workload thực sự chạy không?
2. Khoảng trống có trùng bảo trì, reboot hoặc agent ngừng hoạt động không?
3. Số liệu đang tổng hợp cho một instance hay cả nhóm ứng dụng?
4. Múi giờ và khoảng thời gian có bao phủ batch, cuối tuần, cuối tháng không?
5. Có vừa chuyển tải, đổi cấu hình hoặc triển khai phiên bản mới không?

Một biểu đồ ít điểm dữ liệu có thể tạo cảm giác yên tâm sai. Nếu chưa đủ quan sát, kết quả phù hợp là tiếp tục thu thập bằng chứng.

## 5. Đọc khuyến nghị thành một quyết định có cơ sở

### 5.1. Phân biệt recommendation và resource action

Recommendation mô tả loại cơ hội cải thiện; resource action gắn khuyến nghị với tài nguyên cụ thể. CLI cung cấp nhóm lệnh để liệt kê các resource action. Xem [resource-action-summary list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/optimizer/resource-action-summary/list.html).

Một loại đề xuất có thể liên quan đến nhiều tài nguyên. Vì vậy, hãy đánh giá từng tài nguyên trước khi chọn thực hiện hàng loạt.

| Thông tin cần đọc | Câu hỏi đánh giá |
|---|---|
| Loại khuyến nghị | Dấu hiệu nào được phát hiện và hành động nào được đề xuất? |
| Tài nguyên đích | OCID có khớp tài nguyên mà chủ ứng dụng xác nhận không? |
| Khoảng quan sát | Dữ liệu có bao phủ chu kỳ kinh doanh cần thiết không? |
| Cấu hình hiện tại và đề xuất | CPU, RAM, mạng, VNIC hoặc giới hạn nào thay đổi? |
| Tiết kiệm ước tính | Đơn vị tiền, phạm vi và kỳ tính là gì? Có chồng lặp không? |
| Phụ thuộc | Có instance pool, backup, IaC, database hoặc kế hoạch DR liên quan không? |
| Tính khả thi | Đủ quyền, capacity, thời gian bảo trì và phương án quay lui chưa? |

### 5.2. Trung bình, P95 và tải đỉnh

Các profile Compute của Cloud Advisor có lựa chọn Average hoặc P95, cùng mức Conservative, Standard và Aggressive. Việc đánh giá còn liên quan RAM, mạng và số VNIC hỗ trợ; không nên dùng một ngưỡng CPU chung cho mọi trường hợp. Xem [Profile Descriptions](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Tasks/cloudadvisor-customizing-profiles.htm).

**Average** giúp nhìn tải nền nhưng có thể che đỉnh ngắn. **P95** mô tả mức mà khoảng 95% mẫu không vượt quá trong tập quan sát. Vẫn còn phần mẫu phía trên, nên P95 thấp chưa loại trừ một đỉnh quan trọng.

Ví dụ tự xây dựng: máy đối soát chạy 20 phút mỗi đêm và gần như nhàn rỗi thời gian còn lại. Trung bình ngày thấp nhưng yêu cầu hoàn thành job là 25 phút. Giảm cấu hình khiến job chạy 40 phút sẽ vi phạm yêu cầu dù trung bình CPU cả ngày vẫn thấp.

Chọn cửa sổ theo chu kỳ công việc:

- Ứng dụng có chu kỳ tuần cần quan sát cả ngày làm việc và cuối tuần.
- Hệ thống kế toán cần dữ liệu kỳ đóng sổ.
- Dịch vụ phục vụ chiến dịch cần tải sự kiện hoặc kiểm thử tương đương.
- Hệ thống vừa triển khai cần thêm bằng chứng trước khi ngoại suy dài hạn.

Nếu điều chỉnh profile hoặc override, kết quả áp dụng ở lần Cloud Advisor chạy tiếp theo. Nên lưu lý do điều chỉnh và lịch xem lại. Xem [Cloud Advisor settings](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Tasks/cloudadvisor-cloud_advisor_settings.htm).

### 5.3. Phân biệt cơ hội và tiết kiệm đã đạt

Cloud Advisor đưa ra ước tính tiết kiệm cho các khuyến nghị phù hợp; không phải đề xuất nào cũng có giá trị này. Thiếu ước tính chưa chứng minh lợi ích bằng 0. Xem [How Cost Savings Estimates Are Calculated](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Concepts/recommendations-costmanagement.htm).

Nên tách ba mức trong báo cáo:

- **Cơ hội được phát hiện:** có ứng viên và ước tính ban đầu.
- **Cơ hội đã xác minh:** đã kiểm tra nhu cầu, phụ thuộc và phương án.
- **Tiết kiệm đã kiểm chứng:** thay đổi hoàn tất, có dữ liệu sau thay đổi để đối chiếu.

Nếu hai đề xuất là phương án thay thế của cùng tài nguyên, chỉ tính phương án đã chọn. Không cộng khoản tiết kiệm xóa VM với khoản tiết kiệm giảm cấu hình chính VM đó.

## 6. Đánh giá theo loại tài nguyên

### 6.1. Compute: xét cả ứng dụng và khả năng chịu lỗi

CPU thấp có thể đi cùng RAM cao hoặc nghẽn I/O. Với ứng dụng Java, hãy kiểm tra heap, off-heap, RSS, GC, swap và tiến trình phụ. Giữ nguyên heap tối đa trong khi giảm RAM của VM có thể làm máy thiếu bộ nhớ.

| Chiều đánh giá | Bằng chứng cần xem | Rủi ro nếu bỏ qua |
|---|---|---|
| CPU | Tải nền, P95, đỉnh và thời gian batch | Hàng đợi tăng hoặc batch trễ |
| RAM | RAM toàn máy, heap, off-heap, GC, OOM | Tiến trình bị dừng hoặc latency tăng |
| Mạng/VNIC | Throughput và số VNIC thực tế | Cấu hình đích không đáp ứng kết nối |
| Storage I/O | IOPS, throughput và latency | CPU thấp nhưng ứng dụng đang chờ I/O |
| Ứng dụng | Latency, lỗi, throughput, deadline | Hạ tầng nhìn ổn nhưng dịch vụ không đạt |
| Chịu lỗi | Năng lực khi mất một node | Hệ thống thiếu tải khi xảy ra sự cố |
| Nguồn triển khai | IaC, instance configuration, JVM | Lần triển khai sau tạo lại cấu hình không phù hợp |

Đổi shape có thể thay CPU, RAM, băng thông và số VNIC hỗ trợ. Với instance đang chạy, tài liệu mô tả thao tác đổi shape có reboot; cần kiểm tra image tương thích, giới hạn và capacity đích. Xem [Changing the Shape of an Instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/resizinginstances.htm).

Trình tự thực hiện nên gồm:

1. Chốt cấu hình gốc và tiêu chí ứng dụng phải đạt.
2. Thử cấu hình đích với tải đại diện.
3. Chọn một node hoặc nhóm nhỏ làm bước đầu.
4. Điều phối lưu lượng và cửa sổ bảo trì.
5. Thay đổi, kiểm tra khởi động và sức khỏe dịch vụ.
6. Theo dõi qua tải đỉnh trước khi nhân rộng.
7. Cập nhật IaC hoặc cấu hình dùng để tạo các node tiếp theo.

Ghi lại shape cũ chưa đủ bảo đảm quay lui. Cần chuẩn bị thời gian phục hồi, điều kiện lấy lại năng lực và cách xử lý nếu thao tác khôi phục không thực hiện được ngay.

### 6.2. Block/boot volume không gắn: xác minh dữ liệu

Không gắn chỉ mô tả attachment hiện tại. Volume có thể chứa dữ liệu cần phục hồi, phục vụ điều tra hoặc chờ gắn lại sau migration.

Trước khi thu hồi, cần làm rõ:

- Chủ sở hữu dữ liệu và ứng dụng từng sử dụng volume.
- Kế hoạch gắn lại, phục hồi hoặc migration đang diễn ra.
- Yêu cầu giữ lại theo hợp đồng, kiểm toán và quy trình nội bộ.
- Bản sao cần thiết, khả năng phục hồi và chi phí giữ bản sao.
- Thời điểm có thể xóa cùng người chịu trách nhiệm xác nhận.

Có thể tổ chức luồng **xác minh chủ sở hữu → xác nhận dữ liệu → thống nhất thời điểm → thu hồi → đối chiếu chi phí còn lại**. Thời gian chờ do tổ chức quyết định theo mức quan trọng và yêu cầu dữ liệu.

Không tìm được chủ sở hữu là vấn đề quản trị cần xử lý. Việc chưa ai phản hồi chưa phải bằng chứng dữ liệu không còn giá trị.

### 6.3. Object Storage: lifecycle theo cách dùng dữ liệu

Object Lifecycle Management có thể chuyển lớp lưu trữ hoặc xóa đối tượng theo rule. Việc thực thi cần quyền dành cho dịch vụ Object Storage, ngoài quyền của người cấu hình. Xem [Object Storage Object Lifecycle Management](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usinglifecyclepolicies.htm).

Khi nhận cơ hội liên quan lifecycle, hãy phân loại dữ liệu:

| Nhóm dữ liệu giả định | Điều cần xác minh | Hướng đánh giá |
|---|---|---|
| Log mới | Thời gian tra cứu thường xuyên | Giữ khả năng truy cập phù hợp giai đoạn điều tra |
| Log lịch sử | Có chấp nhận chờ khôi phục không? | Đánh giá lớp lưu trữ theo mục tiêu phục hồi |
| Báo cáo có thể tạo lại | Nguồn tái tạo, thời gian và chi phí | So sánh giữ bản sao với tái tạo |
| Hồ sơ cần lưu giữ | Được phép chuyển lớp hoặc xóa khi nào? | Bám yêu cầu retention đã xác nhận |

Trước khi áp rule, kiểm tra prefix, object version, phạm vi đối tượng và ràng buộc giữ lại. Với rule xóa, tắt rule về sau không tự khôi phục dữ liệu đã mất. Nên thử trên dữ liệu phát triển và tập đối tượng nhỏ trước khi áp dụng rộng.

Khi tính lợi ích, xét cả chi phí đọc/khôi phục, điều kiện thời gian lưu tối thiểu của lớp đích và thời gian khôi phục cần thiết. Một phương án giảm tiền lưu trữ nhưng không đáp ứng yêu cầu phục hồi vẫn chưa phù hợp.

### 6.4. Cơ sở dữ liệu Oracle: theo đúng loại dịch vụ

Trước hết xác định loại triển khai, mô hình CPU, tùy chọn tự mở rộng, cách tính phí và thao tác scale được hỗ trợ. Không áp một quy đổi OCPU/ECPU hoặc một quy trình giảm CPU chung cho mọi dịch vụ.

Phối hợp với DBA để xác minh:

- CPU thấp có do chờ lock, I/O hoặc dịch vụ bên ngoài không?
- ETL, backup, báo cáo, đóng sổ có nằm ngoài khoảng quan sát không?
- Giảm năng lực ảnh hưởng concurrency, truy vấn và batch window ra sao?
- Standby, mục tiêu phục hồi và yêu cầu chịu lỗi còn được đáp ứng không?
- Storage, backup và giấy phép theo hợp đồng ảnh hưởng tổng chi phí thế nào?

Sau thay đổi, tỷ lệ CPU có thể tăng vì dùng ít năng lực hơn. Cần đánh giá mức tăng đó cùng thời gian đáp ứng, lỗi, concurrency và khả năng xử lý các đợt tải quan trọng.

### 6.5. Load balancer: xét tải sự kiện

Với cơ hội giảm băng thông tối thiểu, hãy xem giờ cao điểm và các sự kiện như phát hành, tải tệp lớn, khuyến mại. Một tuần bình thường có thể chưa đại diện.

Xác nhận mức tối thiểu, mức tối đa và giới hạn của cấu hình đang dùng. Sau thay đổi, theo dõi latency, lỗi load balancer/backend, kết nối và băng thông. Phương án chỉ đạt yêu cầu khi backend và trải nghiệm người dùng vẫn ổn định.

## 7. Ưu tiên và quản lý vòng đời khuyến nghị

### 7.1. Xếp thứ tự theo lợi ích có thể thực hiện

| Chiều đánh giá | Ưu tiên cao hơn khi | Điều làm giảm độ sẵn sàng |
|---|---|---|
| Lợi ích | Loại bỏ được khoản chi đáng kể | Chỉ đổi nơi phân bổ chi phí |
| Độ tin cậy | Đủ telemetry, chủ ứng dụng xác nhận | Thiếu tải đỉnh, kiến trúc đang đổi |
| Phạm vi tác động | Có thể giới hạn ảnh hưởng | Liên quan dữ liệu hoặc dịch vụ dùng chung |
| Khả năng phục hồi | Đã thử quay lui, đủ thời gian | Capacity chưa rõ, thao tác khó đảo ngược |

Không nhất thiết gộp thành một điểm. Bảng có chủ sở hữu, lợi ích, bằng chứng và lý do chưa thực hiện thường giúp ra quyết định rõ hơn.

### 7.2. Gắn trạng thái với hồ sơ công việc

CLI hỗ trợ các giá trị **PENDING**, **IMPLEMENTED**, **POSTPONED**, **DISMISSED**. Xem [recommendation-summary list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/optimizer/recommendation-summary/list.html).

Trong quy trình của nhóm, nên gắn trạng thái với bằng chứng:

| Trạng thái | Hồ sơ nên đi kèm |
|---|---|
| Pending | Người điều tra, dữ liệu còn thiếu, ngày xử lý tiếp |
| Implemented | Thay đổi thực tế, kết quả cấu hình, dịch vụ và chi phí |
| Postponed | Lý do hoãn, mốc xem lại, điều kiện tiếp tục |
| Dismissed | Lý do không áp dụng, người xác nhận, điều kiện đánh giá lại |

Oracle lưu ý Implemented cũng có thể xuất hiện khi khuyến nghị hết phù hợp do mức sử dụng thay đổi. Vì vậy, trạng thái này chưa đủ chứng minh đội vận hành đã tạo ra tiết kiệm. Xem [Cloud Advisor Concepts](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Concepts/cloudadvisoroverview.htm).

Ví dụ, VM dự phòng đã vượt qua kiểm thử failover có thể được giữ nguyên. Hồ sơ cần ghi yêu cầu chịu lỗi mà nó đáp ứng và khi nào cần xem xét lại.

### 7.3. Luồng quyết định đề xuất

~~~mermaid
flowchart TD
    A[Nhận khuyến nghị] --> B[Xác định tài nguyên và chủ sở hữu]
    B --> C{Đủ dữ liệu và bối cảnh?}
    C -- Chưa --> D[Bổ sung telemetry và hẹn đánh giá]
    C -- Có --> E{Có phần năng lực có thể giảm?}
    E -- Chưa có bằng chứng --> F[Ghi lý do giữ và điều kiện xem lại]
    E -- Có --> G[Đánh giá phụ thuộc và phương án phục hồi]
    G --> H{Sẵn sàng thực hiện?}
    H -- Chưa --> I[Hoàn thiện phương án hoặc hoãn]
    H -- Có --> J[Thực hiện trên phạm vi nhỏ]
    J --> K{Đạt mục tiêu dịch vụ?}
    K -- Không --> L[Quay lui và phân tích nguyên nhân]
    K -- Có --> M[Đo chi phí và cập nhật nguồn triển khai]
~~~

## 8. Thực hành trên OCI Console

Đầu ra là một bản đánh giá cho một tài nguyên. Có thể hoàn thành phần đọc và phân tích trước khi có cửa sổ thay đổi hạ tầng.

### Bước 1: Chọn phạm vi

Chọn tenancy và compartment được cấp quyền, ưu tiên môi trường học tập có chủ sở hữu rõ ràng. Ghi region tài nguyên và ngày quan sát. Chuẩn bị quyền đọc khuyến nghị, metric và chi phí cần thiết.

### Bước 2: Mở danh sách

Vào **Governance & Administration → Cloud Advisor → Recommendations**, hoặc tìm Cloud Advisor trong Console. Lọc theo Category, Service, Status; nếu có bộ lọc Tenancy, xác nhận tenancy đích. Xem [Listing Recommendations](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Tasks/list-recommendations.htm).

Bắt đầu với Cost management và một loại tài nguyên quen thuộc. Kiểm tra bộ lọc trước khi kết luận không có cơ hội tối ưu.

### Bước 3: Ghi nhận ứng viên

Ghi OCID, tên, compartment, region, cấu hình và đề xuất hiển thị. Xác nhận chủ sở hữu. Nếu OCID hoặc chủ ứng dụng không khớp, cần làm rõ trước khi thực hiện.

### Bước 4: Thu thập bằng chứng

Đặt metric hạ tầng và số liệu ứng dụng trong cùng khoảng thời gian. Với Compute, xem CPU, RAM, mạng và I/O liên quan; bổ sung latency, lỗi và lịch batch.

Nếu thiếu dữ liệu, ghi rõ cách bổ sung và mốc xem lại. Một tuần giữa tháng có thể chưa đủ để chốt cấu hình cho workload đóng sổ.

### Bước 5: Viết phương án

Mô tả cấu hình đích hoặc tài nguyên thu hồi, phạm vi ảnh hưởng, khả năng gián đoạn, điều kiện quay lui và người thực hiện. Với IaC, xác định thay đổi ở nguồn cấu hình.

Cloud Advisor có fix-it flow cho những khuyến nghị được hỗ trợ; các trường hợp khác thực hiện theo quy trình của dịch vụ đích. Kiểm tra tập tài nguyên được chọn trước thao tác. Xem [Implementing Cloud Advisor Recommendations](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Tasks/implementing_cloud_advisor_recommendations.htm).

### Bước 6: Kiểm chứng

Sau thay đổi, xác nhận cấu hình thực tế, sức khỏe ứng dụng và dữ liệu chi phí khi cập nhật. Với thao tác bất đồng bộ, kiểm tra work request, lỗi và log. Xem [Managing Work Requests](https://docs.oracle.com/en-us/iaas/Content/CloudAdvisor/Tasks/work-requests.htm).

Quyết định cuối có thể là thực hiện, thu thập thêm dữ liệu hoặc giữ cấu hình có lý do. Nếu chưa có khuyến nghị phù hợp, ghi phạm vi, bộ lọc, quyền và telemetry đã kiểm tra; không cần tạo tài nguyên tính phí chỉ để làm xuất hiện đề xuất.

## 9. Thu thập khuyến nghị bằng OCI CLI

Cloud Advisor dùng nhóm lệnh **oci optimizer**. Ví dụ dưới chạy trong PowerShell, giả định CLI đã cấu hình xác thực và có IAM phù hợp. Các lệnh chỉ đọc dữ liệu; thay placeholder bằng thông tin thật.

### 9.1. Liệt kê khuyến nghị trong một compartment

~~~powershell
$advisorRegion = '<home-region-identifier>'
$targetCompartmentOcid = '<compartment-ocid>'

$advisorScopeArgs = @(
    '--region', $advisorRegion,
    '--compartment-id', $targetCompartmentOcid,
    '--compartment-id-in-subtree', 'false',
    '--all'
)

oci optimizer recommendation-summary list @advisorScopeArgs --status PENDING
~~~

Ví dụ dùng subtree bằng false để giữ phạm vi ở compartment chỉ định. Tùy chọn **--all** lấy đủ trang. Nếu duyệt cây từ root, dùng tenancy OCID và kiểm tra điều kiện subtree trong [CLI reference](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/optimizer/recommendation-summary/list.html).

Dùng region phục vụ dữ liệu Advisor của tenancy khi gọi CLI; ghi riêng region của tài nguyên trong hồ sơ. Nơi tổng hợp khuyến nghị và nơi chạy tài nguyên là hai thông tin cần phân biệt.

### 9.2. Lấy các resource action

Lấy recommendation ID từ kết quả trước:

~~~powershell
$selectedRecommendationOcid = '<recommendation-ocid>'

$resourceActionArgs = $advisorScopeArgs + @(
    '--recommendation-id', $selectedRecommendationOcid,
    '--include-resource-metadata', 'true',
    '--status', 'PENDING'
)

oci optimizer resource-action-summary list @resourceActionArgs
~~~

Yêu cầu metadata bổ sung không bỏ qua IAM; quyền vẫn quyết định dữ liệu được trả về. Xem [resource-action-summary list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/optimizer/resource-action-summary/list.html).

Đọc một resource action cụ thể:

~~~powershell
$selectedResourceActionOcid = '<resource-action-ocid>'

$resourceActionDetailArgs = @(
    '--region', $advisorRegion,
    '--resource-action-id', $selectedResourceActionOcid,
    '--include-resource-metadata', 'true'
)

oci optimizer resource-action get @resourceActionDetailArgs
~~~

**--resource-action-id** nhận OCID của resource action, không nhận OCID VM hoặc volume. Xem [resource-action get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/optimizer/resource-action/get.html).

### 9.3. Tự động hóa danh sách điều tra

Một tác vụ thu thập định kỳ có thể:

1. Đọc đủ trang trong phạm vi được cấp quyền.
2. Chuẩn hóa khóa theo tenancy, tài nguyên và loại khuyến nghị.
3. Lưu thời điểm quan sát và ghép dữ liệu chủ sở hữu, môi trường.
4. Loại bản ghi trùng; nhóm các phương án loại trừ nhau.
5. Cập nhật công việc hiện có thay vì tạo mới mỗi lần quét.
6. Theo dõi ứng viên mới, ứng viên đã xử lý và ứng viên cần xem lại.

Ví dụ dưới là **bản ghi nội bộ minh họa**, không phải schema API Oracle:

~~~json
{
  "resourceOcid": "<resource-ocid>",
  "recommendationOcid": "<recommendation-ocid>",
  "resourceActionOcid": "<resource-action-ocid>",
  "owner": "payments-platform",
  "environment": "staging",
  "decision": "collect-more-evidence",
  "reason": "Chưa có số liệu của đợt kiểm thử cuối tháng",
  "estimatedMonthlySavings": null,
  "currency": null,
  "changeReference": null
}
~~~

Giá trị null biểu thị chưa xác định. Thay bằng 0 dễ gây hiểu nhầm rằng đã tính và không có lợi ích.

Khi mở rộng sang tự động thực hiện, cần đánh giá lại tài nguyên ngay trước hành động, giới hạn tập đủ điều kiện, kiểm soát số thay đổi đồng thời và dừng khi chỉ số dịch vụ xấu đi. Với thao tác xóa dữ liệu, phải có kết luận rõ về quyền sở hữu và yêu cầu giữ lại.

## 10. Ví dụ xuyên suốt: giảm cấu hình VM Java

Toàn bộ số liệu và mức giá sau đây là **giả định để luyện cách đánh giá**, không phải giá OCI hoặc ngưỡng mặc định Cloud Advisor.

Một ứng dụng staging dùng VM 8 OCPU, 64 GB RAM. Nhóm dự kiến thử 4 OCPU, 32 GB RAM. Số liệu đã thu thập qua chu kỳ kiểm thử đại diện:

| Bằng chứng giả định | Quan sát | Ý nghĩa ban đầu |
|---|---|---|
| CPU trung bình | 6% | Nhu cầu nền thấp |
| CPU P95 | 12% | Phần lớn mẫu CPU thấp |
| CPU đỉnh khi batch | 45% | Cần kiểm tra deadline batch |
| RAM toàn máy cao nhất | 18 GB | Có thể thử giảm RAM với biên phù hợp |
| JVM heap tối đa | 12 GB | Cần RAM cho off-heap, OS và tiến trình khác |
| Latency p95 | 120 ms | Mốc ứng dụng trước thay đổi |
| Thời hạn batch | 30 phút | Ràng buộc phải giữ |

Chưa thể lấy CPU trung bình 6% để kết luận giảm được tám lần năng lực. Phép thử cần xác minh latency, lỗi và batch window trên cấu hình đích.

Nếu giả định cùng kiến trúc, cùng tải và năng lực CPU tăng gần tuyến tính theo OCPU:

~~~text
CPU trung bình dự kiến ≈ 6% × 8 / 4 = 12%
CPU P95 dự kiến       ≈ 12% × 8 / 4 = 24%
CPU đỉnh dự kiến      ≈ 45% × 8 / 4 = 90%
~~~

Đây là mô hình sàng lọc gần đúng do người vận hành đặt ra. Đỉnh dự kiến 90% cho thấy cần kiểm tra batch kỹ dù tải nền thấp. Thời gian thực còn phụ thuộc I/O, mức song song, scheduler và GC.

Phương án thử nên gồm:

- Lưu cấu hình VM, JVM và nguồn triển khai hiện tại.
- Thử tải và batch đại diện trên cấu hình đích.
- Chọn thời gian bảo trì phù hợp khả năng reboot.
- Đặt tiêu chí quay lui, ví dụ batch vượt 30 phút hoặc latency vượt mục tiêu đã thống nhất.
- Theo dõi qua chu kỳ tải quan trọng rồi cập nhật IaC khi chấp nhận kết quả.

Giả sử chi phí giả định trước thay đổi là 240 đơn vị tiền/tháng cho Compute, 30 cho storage. Sau thay đổi, Compute là 150, storage giữ nguyên:

~~~text
Tổng trước thay đổi = 240 + 30 = 270
Tổng sau thay đổi   = 150 + 30 = 180
Tiết kiệm dự kiến   = 270 - 180 = 90
Tỷ lệ trên tổng    = 90 / 270 × 100% ≈ 33,3%
~~~

Giảm một nửa OCPU không mặc nhiên giảm một nửa tổng chi phí. Ví dụ cũng chưa tính công kiểm thử, triển khai và ảnh hưởng của cam kết thanh toán.

Nếu 4 OCPU không đạt batch window, nhóm có thể thử mức trung gian được shape hỗ trợ, tối ưu tác vụ hoặc giữ cấu hình có lý do. Kết quả cần là quyết định có bằng chứng, không phải bắt buộc thu nhỏ.

## 11. Kiểm chứng hiệu quả sau thay đổi

### 11.1. Chọn đường cơ sở có thể so sánh

So sánh trước/sau cần xét số ngày, mức tải và thay đổi khác. Tổng chi phí có thể tăng khi số giao dịch tăng, dù chi phí mỗi giao dịch đã giảm.

Một cách đối chiếu:

~~~text
Tiết kiệm đã chuẩn hóa
  = Chi phí đường cơ sở quy đổi về mức tải và thời gian sau thay đổi
    - Chi phí thực tế sau thay đổi trên cùng phạm vi

Chi phí mỗi 1.000 giao dịch
  = Chi phí của phạm vi được chọn / Số giao dịch thành công × 1.000
~~~

Phải giữ cách chọn phạm vi chi phí và cách đếm giao dịch nhất quán. Với batch, có thể đo chi phí mỗi lần hoàn tất hoặc mỗi đơn vị dữ liệu xử lý, đồng thời giữ yêu cầu thời gian hoàn thành.

### 11.2. Tách giảm sử dụng khỏi giảm tiền phải trả

Giảm mức dùng có thể giải phóng năng lực nhưng chưa làm tổng tiền phải trả giảm tương ứng nếu còn cam kết, phần cố định hoặc điều kiện giá theo hợp đồng.

Nên báo cáo riêng:

- Năng lực hoặc mức sử dụng đã giảm.
- Chi phí sử dụng đã giảm theo dữ liệu đo.
- Ảnh hưởng tới tiền thực trả hoặc khả năng tận dụng phần cam kết.
- Chi phí thực hiện và chi phí duy trì phát sinh.

Cách báo cáo này tránh biến toàn bộ ước tính của Advisor thành tiền đã tiết kiệm trên hóa đơn.

### 11.3. Điều kiện hoàn tất công việc

Một lần tối ưu được coi là hoàn tất trong quy trình của nhóm khi:

- Cấu hình thực tế khớp phương án được chấp nhận.
- Chỉ số ứng dụng đạt mục tiêu qua tải đại diện.
- Chi phí đã được đối chiếu trên phạm vi nhất quán.
- Nguồn IaC hoặc cấu hình triển khai đã cập nhật.
- Bằng chứng thực hiện, người chịu trách nhiệm và điều kiện xem lại đã lưu.

Với quyết định giữ nguyên, đầu ra là lý do được kiểm chứng cùng mốc đánh giá lại. Giữ năng lực dự phòng cần thiết cũng là kết quả quản lý năng lực hợp lệ.

## 12. Tình huống thường gặp

| Hiện tượng | Khả năng cần kiểm tra | Hành động tiếp theo |
|---|---|---|
| Không có khuyến nghị | Bộ lọc, quyền, phạm vi, loại tài nguyên, dữ liệu chưa đủ | Xác minh từng điều kiện và ghi phạm vi |
| Không thấy metadata | Quyền hoặc cột chưa hiển thị | Kiểm tra trước khi kết luận thiếu dữ liệu |
| CPU thấp nhưng latency cao | Chờ I/O, lock, GC, dịch vụ bên ngoài | Điều tra điểm nghẽn trước khi giảm năng lực |
| Volume không gắn còn dữ liệu cần giữ | DR, migration hoặc retention | Xác nhận chủ sở hữu và phương án dữ liệu |
| Thay đổi xong nhưng dashboard chưa cập nhật | Chu kỳ quét và đồng bộ | Đối chiếu cấu hình thực, xem lại sau lần quét |
| Cấu hình cũ xuất hiện trở lại | IaC, instance pool hoặc pipeline | Cập nhật nguồn triển khai |
| Tổng tiết kiệm dự tính quá lớn | Đếm trùng, cộng phương án thay thế, trộn kỳ tính | Chuẩn hóa và chọn một phương án cho mỗi phần chi phí |
| Khó mở rộng trở lại | Capacity hoặc giới hạn chưa chuẩn bị | Hoàn thiện kế hoạch năng lực và phục hồi |

## 13. Những điểm cần ghi nhớ

Cloud Advisor giúp tìm ứng viên tối ưu trong OCI. Quyết định cần chủ sở hữu, telemetry đại diện và mục tiêu dịch vụ rõ ràng. Mức dùng thấp phải được giải thích cùng dự phòng, tác vụ định kỳ, giá trị dữ liệu và khả năng mở rộng trở lại.

Quy trình hiệu quả nối liền **phát hiện → xác minh → thực hiện có kiểm soát → đo kết quả**. Chỉ ghi nhận tiết kiệm đã đạt khi có bằng chứng về thay đổi và chi phí; giữ nguồn cấu hình nhất quán để lợi ích tiếp tục tồn tại sau các lần triển khai tiếp theo.

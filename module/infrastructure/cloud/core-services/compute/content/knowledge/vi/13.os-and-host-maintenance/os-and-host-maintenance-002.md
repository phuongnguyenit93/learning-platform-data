# Lập lịch bảo trì theo mức độ quan trọng của workload

## 1. Vì sao phải lập lịch bảo trì theo workload?

Hệ thống compute cần được cập nhật hệ điều hành, kernel, firmware, hypervisor, driver, runtime và agent để sửa lỗi, vá lỗ hổng, duy trì khả năng tương thích và bảo đảm hiệu năng. Tuy nhiên, khởi động lại một máy chủ API stateless khác hoàn toàn với khởi động lại database primary, node GPU đang chạy một job huấn luyện nhiều ngày hoặc máy điều khiển của hệ thống sản xuất liên tục.

Nếu áp dụng cùng một lịch bảo trì cho mọi workload, tổ chức có thể gây gián đoạn dịch vụ quan trọng, làm mất tiến độ xử lý, phá vỡ quorum hoặc vượt quá mục tiêu khôi phục. Ngược lại, trì hoãn bảo trì quá lâu làm tăng rủi ro bảo mật, lỗi phần cứng và chi phí vận hành. Cách tiếp cận phù hợp là phân loại workload theo mức độ quan trọng, xác định tác động của từng loại bảo trì, rồi chọn thời điểm, chiến lược triển khai và phương án khôi phục tương ứng.

Trong cloud, bảo trì còn có nhiều lớp. Nhà cung cấp có thể bảo trì host vật lý hoặc hypervisor; đội vận hành quản lý hệ điều hành khách, container host, runtime và ứng dụng. Một số sự kiện có thể live-migrate workload; một số yêu cầu reboot hoặc thay host. Dịch vụ serverless giảm trách nhiệm quản lý host nhưng vẫn cần cập nhật runtime, dependency, function package và image do đội phát triển kiểm soát.

Sau bài học, người học có thể:

- Phân loại workload theo mức độ quan trọng và tác động kinh doanh.
- Dùng SLO, RTO, RPO, dependency và thời gian phục hồi để xác định cửa sổ bảo trì.
- Phân biệt bảo trì host, hypervisor, guest OS, container host, runtime và ứng dụng.
- Chọn rolling, canary, blue/green, live migration, failover hoặc checkpoint theo workload.
- Lập lịch bảo trì cho VM, Kubernetes, database, GPU/HPC và serverless.
- Kiểm soát capacity, phê duyệt, thông báo, giám sát và rollback trước/sau mỗi đợt.

## 2. Nguyên tắc lập lịch bảo trì

### 2.1. Mức độ quan trọng phải phản ánh tác động thực tế

Mức độ quan trọng (workload criticality) cho biết hậu quả nếu workload bị gián đoạn, suy giảm hiệu năng hoặc mất dữ liệu. Không nên chỉ dựa vào tên hệ thống hay chức danh chủ sở hữu. Cần đánh giá tác động đến khách hàng, doanh thu, an toàn, tuân thủ, vận hành nội bộ và các dịch vụ phụ thuộc.

Một ứng dụng nội bộ có thể rất quan trọng nếu nó điều khiển quy trình sản xuất. Một dịch vụ công khai có thể chịu được bảo trì ngắn nếu có nhiều replica và chuyển traffic tự động. Vì vậy, criticality là thuộc tính của workload trong bối cảnh kiến trúc và hoạt động kinh doanh, không chỉ là nhãn của máy chủ.

### 2.2. Bảo trì có kế hoạch và bảo trì khẩn cấp

**Bảo trì có kế hoạch** gồm cập nhật định kỳ, nâng cấp phiên bản, thay firmware, đổi cấu hình hoặc thay host theo lịch. Các hoạt động này có thể được chuẩn bị bằng thử nghiệm, thông báo, capacity dự phòng và runbook.

**Bảo trì khẩn cấp** xử lý lỗ hổng đang bị khai thác, lỗi nghiêm trọng, nguy cơ mất dữ liệu hoặc sự cố phần cứng. Có thể phải rút ngắn thời gian thông báo và phê duyệt, nhưng vẫn cần người chịu trách nhiệm, đánh giá tác động, ghi nhận quyết định và kế hoạch khôi phục. Không nên dùng nhãn khẩn cấp để bỏ qua kiểm soát cho những thay đổi có thể lên lịch bình thường.

### 2.3. Không gom mọi loại bảo trì vào một cửa sổ

Một workload có thể cần các cửa sổ riêng cho:

- Cập nhật bảo mật không cần reboot.
- Cập nhật kernel hoặc driver yêu cầu reboot.
- Nâng cấp hệ điều hành hoặc runtime có thay đổi tương thích.
- Bảo trì host/hypervisor do nhà cung cấp thông báo.
- Thay đổi mạng, storage hoặc firmware có thể ảnh hưởng nhiều máy.
- Kiểm thử khôi phục, failover và diễn tập DR.

Mỗi loại có phạm vi ảnh hưởng và thời gian cần thiết khác nhau. Một bản vá thư viện trong container image có thể phát hành theo pipeline ứng dụng; cập nhật kernel trên database host có thể cần chuyển vai trò primary trước khi reboot.

### 2.4. Tính cả thời gian chuẩn bị và xác minh

Cửa sổ bảo trì không chỉ là thời gian thực hiện lệnh cập nhật. Cần dành thời gian kiểm tra trước, sao lưu hoặc checkpoint, drain traffic, thực hiện thay đổi, chờ hệ thống ổn định và xác nhận dịch vụ đáp ứng SLO. Nếu cửa sổ chỉ đủ thời gian reboot mà không có thời gian kiểm tra sau reboot, lịch bảo trì chưa hoàn chỉnh.

## 3. Phân tầng mức độ quan trọng của workload

### 3.1. Một mô hình phân tầng tham khảo

Tổ chức có thể dùng bốn tầng dưới đây rồi điều chỉnh theo ngành và chính sách nội bộ:

| Tầng | Đặc điểm | Ví dụ | Cách tiếp cận bảo trì |
|---|---|---|---|
| Tier 0 – Tối quan trọng | Gián đoạn có thể gây hậu quả nghiêm trọng, ảnh hưởng an toàn, giao dịch cốt lõi hoặc nhiều dịch vụ khác | Control plane trọng yếu, hệ thống thanh toán lõi, điều khiển sản xuất, dịch vụ định danh trung tâm | Bảo trì theo cụm nhỏ, failover đã thử nghiệm, phê duyệt chặt, có phương án khôi phục và người trực |
| Tier 1 – Quan trọng cao | Gián đoạn ảnh hưởng lớn đến khách hàng hoặc hoạt động kinh doanh, chỉ chấp nhận thời gian ngắn | API chính, database giao dịch, nền tảng đơn hàng, dịch vụ xác thực khách hàng | Rolling/canary, dự phòng đa vùng hoặc nhiều replica, cửa sổ ngoài giờ cao điểm |
| Tier 2 – Quan trọng trung bình | Có thể chấp nhận gián đoạn giới hạn hoặc xử lý chậm trong một khoảng thời gian | Báo cáo nội bộ, worker batch, hệ thống hỗ trợ | Lên lịch theo nhóm, drain hoặc pause job, thông báo trước, khôi phục theo runbook |
| Tier 3 – Linh hoạt | Có thể dừng và chạy lại, dữ liệu dễ tái tạo hoặc không phục vụ nghiệp vụ trực tiếp | Dev/test, sandbox, runner tạm thời, môi trường thử nghiệm | Bảo trì tự động theo lịch chung, ưu tiên chi phí và tốc độ cập nhật |

Đây là mô hình phân loại tham khảo, không phải chuẩn bắt buộc. Một workload có thể được xếp tầng khác nhau theo thời điểm, khu vực hoặc mùa cao điểm. Ví dụ, hệ thống bán hàng có thể cần mức bảo vệ cao hơn trong chiến dịch lớn so với ngày thường.

### 3.2. Xác định criticality bằng các yếu tố

Khi phân tầng, hãy đánh giá ít nhất:

1. **Business impact:** mất dịch vụ ảnh hưởng khách hàng, doanh thu, sản xuất hoặc nghĩa vụ hợp đồng đến mức nào?
2. **SLO/availability target:** dịch vụ cần sẵn sàng bao nhiêu và ngân sách lỗi còn lại ra sao?
3. **RTO:** thời gian tối đa chấp nhận để khôi phục dịch vụ sau gián đoạn.
4. **RPO:** lượng dữ liệu tối đa có thể mất, biểu diễn bằng khoảng thời gian hoặc điểm khôi phục.
5. **Data criticality:** dữ liệu có thể tái tạo hay cần bảo toàn tuyệt đối?
6. **Dependency:** workload có phải nền tảng dùng chung cho nhiều dịch vụ khác không?
7. **Recovery complexity:** có thể tự động failover hay cần thao tác thủ công, đối soát dữ liệu?
8. **Security exposure:** mức độ phơi bày Internet, quyền truy cập và mức độ nghiêm trọng của lỗ hổng cần vá.
9. **Maintenance duration:** cập nhật cần bao lâu, có reboot hay migration không?
10. **Capacity headroom:** hệ thống có đủ tài nguyên để chạy khi một node hoặc một vùng đang bảo trì không?

### 3.3. SLO, RTO và RPO có vai trò khác nhau

SLO mô tả mục tiêu chất lượng dịch vụ trong hoạt động bình thường, ví dụ tỷ lệ request thành công hoặc latency p99. RTO mô tả thời gian tối đa để khôi phục sau sự cố. RPO mô tả mức dữ liệu có thể mất khi phục hồi. Các chỉ số này bổ sung cho nhau.

Một dịch vụ có thể có SLO availability cao nhưng vẫn chấp nhận RTO dài cho một môi trường DR lạnh. Ngược lại, một hệ thống batch có thể không yêu cầu availability liên tục nhưng cần RPO rất thấp để tránh chạy lại nhiều giờ dữ liệu. Lịch bảo trì phải tôn trọng cả khả năng gián đoạn lẫn khả năng bảo toàn trạng thái.

### 3.4. Ma trận ưu tiên bảo trì

| Criticality | Mức độ khẩn cấp của thay đổi | Hướng xử lý |
|---|---|---|
| Tier 0/1 | Lỗ hổng đang bị khai thác hoặc rủi ro an toàn nghiêm trọng | Kích hoạt quy trình khẩn cấp; giảm phạm vi thay đổi, triển khai theo nhóm nhỏ, có người trực và xác minh ngay |
| Tier 0/1 | Bản vá định kỳ, không có khai thác khẩn cấp | Thử nghiệm trước, đặt cửa sổ được phê duyệt, bảo đảm failover/capacity và kiểm soát từng bước |
| Tier 2 | Bản vá bảo mật hoặc nâng cấp định kỳ | Gom theo nhóm dịch vụ, thông báo trước và dùng rolling nếu có thể |
| Tier 3 | Cập nhật thường xuyên | Tự động hóa theo lịch, tái tạo từ image chuẩn và theo dõi kết quả |

Criticality không phải lý do để trì hoãn vô thời hạn bản vá nghiêm trọng. Với Tier 0/1, cần đầu tư cơ chế HA, môi trường thử nghiệm và tự động hóa để có thể cập nhật nhanh với rủi ro gián đoạn thấp.

## 4. Phân loại hoạt động bảo trì

### 4.1. Bảo trì host và hypervisor

Nhà cung cấp cloud có thể thông báo sự kiện bảo trì máy chủ vật lý, hypervisor, NIC hoặc hạ tầng lưu trữ. Tùy dịch vụ, nhà cung cấp có thể live-migrate VM, yêu cầu reboot, lên lịch thay host hoặc dừng instance trong một khoảng thời gian.

Đội vận hành cần kiểm tra loại sự kiện, phạm vi máy bị ảnh hưởng, deadline, hành vi mặc định và lựa chọn hoãn hoặc tự khởi động lại nếu có. Không giả định mọi dịch vụ đều hỗ trợ live migration hoặc mọi lần migration đều không ảnh hưởng latency. Một số workload nhạy thời gian, dùng GPU passthrough, thiết bị local hoặc cấu hình đặc biệt có thể có giới hạn khác.

### 4.2. Bảo trì guest operating system

Guest OS là hệ điều hành bên trong VM. Công việc thường gồm cập nhật package, kernel, thư viện hệ thống, agent giám sát, agent bảo mật, cấu hình SSH/RDP và chứng thư. Cập nhật kernel hoặc thành phần nền tảng có thể yêu cầu reboot.

Đội vận hành kiểm soát image, repository, lịch vá, chính sách reboot và kiểm tra sau cập nhật. Với VM stateless, thay máy bằng image mới có thể dễ kiểm soát hơn sửa trực tiếp tại chỗ. Với VM stateful, cần xác định rõ dữ liệu, volume, địa chỉ mạng và trạng thái ứng dụng trước khi thay thế.

### 4.3. Bảo trì container host và Kubernetes node

Node Kubernetes có thể cần cập nhật hệ điều hành, kernel, container runtime, kubelet, CNI, CSI hoặc GPU driver. Trước khi bảo trì, node thường được cordon để không nhận pod mới, sau đó drain để di chuyển workload sang node khác. Cần xem xét PodDisruptionBudget (PDB), replica, local storage, DaemonSet và capacity còn lại.

PDB có thể ngăn drain nếu việc evict pod vượt quá số disruption cho phép. Đây là cơ chế bảo vệ availability; không nên bỏ qua PDB chỉ để hoàn thành bảo trì nhanh. Hãy tăng replica hoặc bổ sung capacity, điều chỉnh lịch, hoặc phối hợp với chủ workload trước khi thực hiện.

### 4.4. Bảo trì database và hệ thống stateful

Database có thể có primary/replica, quorum, transaction log, replication lag và quy trình failover. Bảo trì cần bảo đảm bản sao đủ đồng bộ trước khi chuyển vai trò. Cập nhật lần lượt replica rồi failover có kiểm soát thường giảm gián đoạn, nhưng trình tự cụ thể phụ thuộc database engine và hướng dẫn của nhà cung cấp.

Với cluster có quorum, không được reboot quá nhiều node cùng lúc. Cần xác định số node tối thiểu để duy trì quorum, trạng thái replication, khả năng khôi phục và tác động của việc mất một fault domain. Snapshot không thay thế backup đã kiểm thử restore.

### 4.5. Bảo trì GPU/HPC và job dài hạn

Node GPU hoặc HPC có thể chạy job huấn luyện, mô phỏng hoặc phân tích kéo dài nhiều giờ đến nhiều ngày. Reboot giữa job có thể làm mất tiến độ lớn nếu chưa checkpoint. Lịch bảo trì cần phối hợp scheduler, hàng đợi job, thời gian hoàn tất dự kiến, khả năng checkpoint và dung lượng node thay thế.

Có thể đánh dấu node không nhận job mới, chờ job đang chạy hoàn tất, yêu cầu checkpoint rồi drain node. Với workload không hỗ trợ checkpoint hoặc thời gian chạy rất dài, cần một cửa sổ riêng và trao đổi trước với chủ sở hữu workload. Kiểm tra driver, CUDA/runtime, firmware và thư viện sau khi cập nhật vì sai lệch phiên bản có thể làm job không khởi động được.

### 4.6. Bảo trì serverless

Nhà cung cấp quản lý host và phần lớn hệ điều hành nền của dịch vụ serverless. Đội ứng dụng vẫn chịu trách nhiệm cho runtime version, dependency, function package, container image, cấu hình memory/CPU, concurrency, trigger và quyền IAM.

Khi runtime bị deprecate hoặc cần nâng cấp, hãy thử trên alias, stage hoặc traffic nhỏ trước; đo lỗi, latency và cold start; sau đó chuyển traffic dần. Với function xử lý sự kiện, kiểm tra retry, idempotency và dead-letter queue để tránh xử lý trùng hoặc mất sự kiện trong lúc cập nhật.

## 5. Chọn cửa sổ bảo trì

### 5.1. Dựa trên nhịp hoạt động của workload

Không mặc định mọi hệ thống nên bảo trì lúc nửa đêm. Cần phân tích lưu lượng theo giờ, ngày trong tuần, múi giờ người dùng, lịch batch, lịch đối soát, thời điểm backup và các đợt cao điểm kinh doanh. Dịch vụ toàn cầu có thể không có giờ thấp điểm chung; khi đó dùng rolling theo vùng hoặc theo cụm.

Đối với hệ thống nội bộ, cửa sổ có thể được chọn theo lịch làm việc của bộ phận phụ thuộc. Với hệ thống sản xuất liên tục, cần phối hợp với lịch vận hành tại hiện trường và thời gian bàn giao ca. Với hệ thống tài chính, cần tránh khoảng thời gian chốt sổ hoặc đối soát.

### 5.2. Xác định độ dài cửa sổ

Thời lượng cần tính cả:

- Thời gian chuẩn bị, kiểm tra backup/checkpoint và xác nhận người trực.
- Thời gian drain, failover hoặc chuyển traffic.
- Thời gian cài đặt, reboot, live migration hoặc thay node.
- Thời gian chờ agent, volume, network và dịch vụ phụ trợ sẵn sàng.
- Thời gian smoke test, kiểm tra SLO và quan sát sau thay đổi.
- Khoảng dự phòng để rollback hoặc khôi phục.

Nếu một đợt bảo trì thường mất 30 phút nhưng hệ thống cần 20 phút để xác minh và 30 phút dự phòng, cửa sổ 30 phút là không đủ. Không nên lên lịch sát giới hạn chỉ vì thời gian thực hiện lệnh thường ngắn.

### 5.3. Lịch bảo trì theo tầng

Ví dụ lịch tham khảo:

| Tầng | Cửa sổ tham khảo | Chiến lược | Điều kiện bắt đầu |
|---|---|---|---|
| Tier 0 | Cửa sổ riêng được chủ dịch vụ và vận hành phê duyệt; có thể chia nhiều đợt | Canary, rolling theo fault domain, failover | Replica/quorum khỏe, capacity dự phòng, người trực và rollback sẵn sàng |
| Tier 1 | Ngoài giờ cao điểm theo vùng người dùng | Rolling hoặc blue/green | SLO ổn định, backend dự phòng healthy, kiểm tra traffic shift |
| Tier 2 | Cửa sổ bảo trì định kỳ theo tuần/tháng | Nhóm nhỏ, drain và thay thế | Batch đã dừng hoặc chuyển lịch, backup hoàn tất |
| Tier 3 | Lịch tự động cố định, có thể ngoài giờ làm việc | Rebuild từ image hoặc cập nhật theo nhóm | Tài nguyên có thể tái tạo, kết quả được kiểm tra tự động |

Thời gian cụ thể phải dựa trên dữ liệu vận hành và cam kết với người dùng. Bảng này không thay thế quy trình change management của tổ chức.

### 5.4. Múi giờ, thông báo và freeze period

Lịch phải ghi rõ múi giờ, ví dụ `Asia/Ho_Chi_Minh` hoặc UTC, để tránh nhầm lẫn khi đội vận hành ở nhiều khu vực. Thông báo nên nêu phạm vi, dịch vụ, thời gian bắt đầu/kết thúc dự kiến, tác động có thể xảy ra, đầu mối liên hệ và phương án xử lý nếu vượt cửa sổ.

Freeze period là khoảng thời gian hạn chế thay đổi, chẳng hạn ngày lễ, chiến dịch bán hàng hoặc kỳ chốt sổ. Freeze không nên ngăn vá khẩn cấp khi rủi ro bảo mật hoặc an toàn đủ lớn; cần quy trình ngoại lệ và phê duyệt phù hợp.

## 6. Đánh giá rủi ro trước khi lập lịch

### 6.1. Rủi ro của thay đổi

Đánh giá từng thay đổi theo:

- Mức độ ảnh hưởng nếu thay đổi thất bại.
- Xác suất lỗi dựa trên lịch sử, độ phức tạp và độ mới của phiên bản.
- Số lượng node, vùng và workload bị tác động.
- Khả năng rollback hoặc thay thế nhanh.
- Mức độ tương thích với ứng dụng, driver, agent và dịch vụ phụ thuộc.
- Khả năng quan sát để phát hiện lỗi sớm.

Không chỉ dựa vào điểm CVSS hoặc nhãn severity để xếp lịch bản vá. Cần kết hợp mức độ khai thác thực tế, mức phơi bày, quyền mà lỗ hổng cho phép và giá trị tài sản bị ảnh hưởng. Lỗ hổng đang bị khai thác trên máy public-facing có thể cần xử lý nhanh hơn một lỗ hổng ít khả năng tiếp cận trong môi trường cô lập.

### 6.2. Capacity headroom

Rolling maintenance làm giảm số node sẵn sàng trong một khoảng thời gian. Trước khi drain một node, tính xem các node còn lại có đủ CPU, RAM, GPU, storage IOPS và network throughput để nhận workload hay không. Cũng cần tính quota cloud, giới hạn IP, load balancer target, database connection và capacity ở vùng dự phòng.

Nếu cluster chỉ vừa đủ tải ở trạng thái bình thường, không thể mặc định có thể bảo trì một node mà không ảnh hưởng dịch vụ. Có thể cần scale out tạm thời, giảm tải, hoãn batch hoặc chia bảo trì thành nhiều đợt nhỏ.

### 6.3. Dependency và phạm vi ảnh hưởng

Một host có thể chạy nhiều workload khác nhau. Một thay đổi ở DNS, IAM, network, storage driver hoặc hypervisor có thể ảnh hưởng rộng hơn một VM. Lập bản đồ dependency để xác định dịch vụ nào cần kiểm tra cùng lúc và tránh bảo trì các thành phần có chung fault domain trong một đợt.

### 6.4. Quyết định go/no-go

Trước khi bắt đầu, người chịu trách nhiệm cần xác nhận:

- Bản vá hoặc phiên bản đã được thử nghiệm ở môi trường phù hợp.
- Backup, snapshot hoặc checkpoint có thể sử dụng và đã kiểm tra trạng thái.
- Replica, quorum và capacity đạt điều kiện.
- Chủ workload và người trực đã sẵn sàng.
- Dashboard, cảnh báo và runbook đang hoạt động.
- Có tiêu chí dừng rollout và điều kiện rollback rõ ràng.

Nếu một điều kiện bắt buộc chưa đạt, hoãn hoặc thay đổi phạm vi. Với bảo trì khẩn cấp, ghi rõ rủi ro chấp nhận và biện pháp bù trừ.

## 7. Chiến lược triển khai bảo trì

### 7.1. In-place maintenance

In-place maintenance cập nhật trực tiếp hệ điều hành hoặc phần mềm trên máy hiện tại. Cách này phù hợp khi dữ liệu và cấu hình gắn với máy, hoặc khi việc thay thế khó thực hiện. Cần có backup, kiểm tra package, reboot plan và khả năng khôi phục phiên bản trước.

Rủi ro là drift giữa các máy, lỗi cập nhật khó tái tạo và rollback phức tạp. Với fleet lớn, cần tự động hóa và chia nhóm thay vì cập nhật thủ công hàng loạt.

### 7.2. Rolling maintenance

Rolling maintenance cập nhật từng node hoặc từng nhóm nhỏ trong khi phần còn lại tiếp tục phục vụ. Trình tự điển hình:

1. Chọn một node hoặc một phần nhỏ làm canary.
2. Drain traffic/job và xác nhận workload đã chuyển đi.
3. Cập nhật, reboot hoặc thay node.
4. Chờ health check và kiểm tra metric.
5. Chỉ tiếp tục node tiếp theo khi canary ổn định.
6. Lặp lại theo fault domain để tránh mất quá nhiều capacity cùng lúc.

Rolling giảm phạm vi ảnh hưởng tại một thời điểm nhưng cần đủ capacity và cơ chế phân tán workload. Nếu các node cùng nằm trong một rack, zone hoặc host group có dependency chung, cần tránh bảo trì đồng thời cả nhóm.

### 7.3. Canary deployment

Canary triển khai thay đổi lên một tỷ lệ nhỏ node hoặc traffic trước. Quan sát error rate, latency, CPU, memory, restart, log và các chỉ số nghiệp vụ. Nếu không có dấu hiệu bất thường trong khoảng quan sát được xác định trước, tăng dần tỷ lệ.

Canary đặc biệt hữu ích cho kernel, driver, agent bảo mật, runtime và image mới. Chọn canary đại diện cho cấu hình thật: loại instance, vùng, kiến trúc CPU, GPU, storage và nhóm workload. Một canary chỉ chạy ứng dụng đơn giản có thể không phát hiện lỗi tương thích trên workload đặc thù.

### 7.4. Blue/green hoặc immutable replacement

Blue/green tạo một nhóm máy mới với image hoặc phiên bản đã cập nhật, kiểm thử nhóm mới rồi chuyển traffic từ nhóm cũ sang nhóm mới. Immutable replacement thay thế máy cũ bằng máy mới thay vì sửa đổi lâu dài tại chỗ.

Ưu điểm là dễ quay lại nhóm cũ khi dữ liệu và trạng thái cho phép. Hạn chế là cần capacity tạm thời, đồng bộ dữ liệu, quản lý địa chỉ và xử lý thay đổi schema. Với stateful workload, không thể chỉ chuyển traffic nếu dữ liệu chưa được replicate hoặc ứng dụng chưa tương thích hai phiên bản.

### 7.5. Live migration và host maintenance

Live migration chuyển VM đang chạy sang host khác với gián đoạn tối thiểu trong điều kiện nền tảng hỗ trợ. Tuy nhiên, có thể có độ trễ tăng, pause ngắn hoặc giới hạn với thiết bị passthrough, local disk, GPU và cấu hình đặc biệt.

Nếu nhà cung cấp yêu cầu reboot hoặc stop/start, hãy xem đó là một sự kiện có khả năng gây gián đoạn. Kiểm tra chính sách tự động, thời hạn sự kiện và khả năng tự chọn thời điểm. Workload criticality quyết định cần failover, scale-out hay cửa sổ dừng dịch vụ.

### 7.6. Drain, pause và checkpoint

Drain ngừng nhận workload mới trên node và chuyển hoặc hoàn tất workload đang chạy. Với worker queue, có thể ngừng consumer mới và chờ queue xử lý hết. Với HPC/GPU, scheduler có thể đánh dấu node không nhận job mới và yêu cầu checkpoint. Với container, dùng cordon/drain; với load balancer, dùng connection draining để chờ request hiện tại hoàn tất.

Checkpoint cần lưu đủ trạng thái để tiếp tục hoặc khởi động lại: model/optimizer state, vị trí dữ liệu, tiến độ batch, cấu hình và phiên bản phần mềm. Phải kiểm tra khả năng đọc checkpoint bằng phiên bản mới trước khi dựa vào nó để bảo vệ job dài hạn.

## 8. Quy trình bảo trì theo từng loại compute

### 8.1. VM stateless sau load balancer

Với API hoặc web server stateless có nhiều instance:

1. Xác nhận số backend healthy và capacity còn lại.
2. Đưa instance ra khỏi target group hoặc bật connection draining.
3. Chờ request đang xử lý hoàn tất theo timeout.
4. Cập nhật OS hoặc thay instance bằng image mới.
5. Chờ agent, network, application và readiness check.
6. Đưa instance trở lại pool, theo dõi error rate và latency.
7. Tiếp tục instance tiếp theo.

Nếu autoscaling group hoặc managed instance group quản lý fleet, có thể dùng instance refresh hoặc cơ chế tương đương. Cần cấu hình minimum healthy capacity, maximum surge và health check đúng để tránh thay quá nhiều instance cùng lúc.

### 8.2. VM stateful

Với VM chứa database, file service hoặc ứng dụng lưu state cục bộ, trước tiên xác định dữ liệu nằm trên boot disk, data volume, local disk hay dịch vụ ngoài. Lập backup/snapshot nhất quán, xác minh replica và kế hoạch failover. Có thể cần chuyển vai trò, tháo volume hoặc thay máy trong khi giữ volume bền vững.

Không reboot hoặc replace chỉ dựa trên việc VM đã được đưa khỏi load balancer. Workload có thể vẫn nhận traffic nội bộ hoặc đang thực hiện transaction. Phải có bước dừng ứng dụng hoặc chuyển vai trò theo đúng hướng dẫn của hệ thống.

### 8.3. Kubernetes node

Một quy trình cơ bản có thể dùng `kubectl`:

```bash
# Ngăn scheduler đặt pod mới lên node
kubectl cordon node-01

# Evict workload theo chính sách disruption hiện tại
kubectl drain node-01 --ignore-daemonsets --timeout=10m

# Sau bảo trì và xác minh node khỏe
kubectl uncordon node-01
```

Trước khi chạy `drain`, kiểm tra PDB, replica, pod không do controller quản lý, DaemonSet, local PV, `emptyDir`, topology spread và capacity của node còn lại. Lệnh có thể bị chặn khi PDB không cho phép disruption. Không tự động thêm cờ bỏ qua kiểm soát hoặc xóa dữ liệu local chỉ để ép drain thành công.

Sau khi cập nhật OS, container runtime, kubelet hoặc driver, kiểm tra node `Ready`, CNI/CSI, DNS, GPU device plugin, log và khả năng schedule pod. Thử một workload đại diện trước khi tiếp tục node tiếp theo.

### 8.4. Database primary/replica

Với database có replication, một trình tự tham khảo là:

1. Kiểm tra backup, replication lag, quorum và khả năng phục hồi.
2. Cập nhật replica theo từng node, giữ đủ số bản sao khỏe.
3. Kiểm thử truy vấn, replication và khả năng nhận vai trò primary.
4. Thực hiện failover có kiểm soát theo runbook.
5. Cập nhật node primary cũ khi nó đã trở thành replica hoặc được tháo khỏi cụm.
6. Xác nhận topology, consistency, backup và ứng dụng kết nối bình thường.

Trình tự này chỉ là mẫu. Cơ chế rolling upgrade, failover và tương thích phiên bản khác nhau giữa database engine. Không tự ý thay đổi thứ tự hoặc bỏ bước kiểm tra quorum theo hướng dẫn của sản phẩm.

### 8.5. GPU/HPC cluster

Đánh dấu node không nhận job mới; xem danh sách job đang chạy và thời gian dự kiến hoàn tất. Nếu scheduler hỗ trợ, yêu cầu job checkpoint hoặc requeue. Chỉ drain khi job đã hoàn tất hoặc trạng thái đã được lưu an toàn. Sau bảo trì, chạy kiểm tra GPU health, ECC, driver, CUDA/runtime, network fabric và storage mount.

Với job phân tán nhiều node, phải xem toàn bộ job group. Reboot một node có thể làm hỏng job trên các node còn lại nếu framework không hỗ trợ elastic recovery. Lịch bảo trì nên phối hợp với queue policy, reservation và thời gian sử dụng cụm.

### 8.6. Serverless và managed runtime

Nhà cung cấp chịu trách nhiệm host OS và phần lớn patch nền. Đội ứng dụng vẫn cần theo dõi thông báo runtime deprecation, cập nhật dependency, build image mới và triển khai function theo alias/stage. Kiểm tra concurrency, event retry, idempotency, cold start, permission và quan sát log sau chuyển đổi.

Nếu runtime được nhà cung cấp tự động cập nhật theo lịch, cần đọc chính sách tương thích và thời hạn. Có thể chọn thời điểm nâng cấp nếu dịch vụ hỗ trợ; nếu không, cần kiểm thử sớm trên môi trường tương đương và chuẩn bị bản phát hành tương thích.

## 9. Tự động hóa lịch bảo trì

### 9.1. Lịch tập trung và metadata workload

Mỗi workload nên có metadata tối thiểu:

- Owner kỹ thuật và owner nghiệp vụ.
- Tier criticality và môi trường.
- SLO, RTO, RPO và dependency quan trọng.
- Múi giờ, maintenance window và freeze period.
- Loại tài nguyên: VM, node pool, database, GPU cluster hoặc serverless.
- Cách drain, failover, checkpoint và rollback.
- Kênh thông báo, người phê duyệt và người trực.

Lịch tập trung giúp phát hiện các đợt bảo trì trùng nhau, ví dụ nhiều database cùng phụ thuộc một cụm mạng hoặc nhiều node trong cùng fault domain bị lên lịch reboot đồng thời.

### 9.2. Patch ring

Chia fleet thành các ring:

| Ring | Phạm vi | Mục đích |
|---|---|---|
| Ring 0 – Lab | Môi trường thử nghiệm và máy đại diện | Phát hiện lỗi cài đặt, boot, driver và tương thích |
| Ring 1 – Canary | Một nhóm nhỏ workload ít rủi ro hoặc node đại diện | Kiểm chứng trên cấu hình gần production |
| Ring 2 – Early production | Một phần nhỏ production theo vùng/nhóm | Xác nhận hành vi thật dưới tải thực tế |
| Ring 3 – Broad rollout | Phần còn lại của fleet | Hoàn tất cập nhật khi các chỉ số ổn định |

Không nên để canary chỉ gồm máy ít đặc điểm. Chọn đại diện cho các họ instance, kiến trúc CPU, GPU, storage driver và vùng triển khai cần bảo vệ.

### 9.3. Policy và automation guardrail

Hệ thống tự động có thể kiểm tra trước khi chạy:

- Workload có maintenance window hợp lệ không?
- Tier có yêu cầu approval hoặc người trực không?
- Node có đủ replica và capacity để drain không?
- Có backup/checkpoint mới và kiểm tra được không?
- Có sự kiện khác đang bảo trì cùng fault domain không?
- Bản vá có nằm trong danh sách đã kiểm thử không?
- Có thể rollback hoặc thay node nếu health check thất bại không?

Nếu điều kiện không đạt, automation nên dừng và báo lý do thay vì cố tiếp tục. Với thay đổi khẩn cấp, dùng luồng ngoại lệ có ghi nhận quyết định và người chịu trách nhiệm.

### 9.4. Ví dụ lịch YAML

Ví dụ cấu trúc dữ liệu lịch bảo trì nội bộ:

```yaml
workload: orders-api
criticality: tier-1
owner: platform-orders
timezone: Asia/Ho_Chi_Minh
maintenance:
  type: guest-os-patch
  window:
    day: Sunday
    start: "01:00"
    duration_minutes: 120
  strategy: rolling
  max_unavailable: 1
  prechecks:
    - healthy_capacity
    - backup_status
    - on_call_confirmed
  stop_conditions:
    - error_rate_above_slo
    - p99_latency_above_threshold
  rollback: replace_with_previous_image
```

Đây là schema minh họa, không phải định dạng chuẩn của nhà cung cấp cloud. Trong thực tế, cần bổ sung quy tắc phê duyệt, lịch blackout, mã thay đổi, nhóm tài nguyên, tiêu chí health check và cách xử lý khi không thể hoàn thành trong cửa sổ.

## 10. Giám sát trong và sau bảo trì

### 10.1. Chỉ số kỹ thuật

Theo dõi ít nhất:

- Availability, error rate, request success và latency p50/p95/p99.
- CPU, memory, disk I/O, network throughput và packet drop.
- Số replica healthy, pod availability, node Ready và target health.
- Database replication lag, quorum, connection, transaction error và backup status.
- GPU health, job completion, checkpoint status và scheduler queue.
- Restart count, boot duration, agent heartbeat và lỗi package/runtime.

### 10.2. Chỉ số nghiệp vụ

Một hệ thống có thể vượt qua health check kỹ thuật nhưng vẫn lỗi nghiệp vụ. Sau bảo trì, kiểm tra số giao dịch thành công, backlog queue, đơn hàng xử lý, dữ liệu đồng bộ, kết quả batch và khả năng người dùng hoàn tất thao tác chính.

Với database, chạy truy vấn kiểm tra dữ liệu và replication. Với worker, kiểm tra queue không tăng bất thường. Với hệ thống thanh toán, xác minh giao dịch thử và đối soát theo quy trình được phép.

### 10.3. Thời gian quan sát sau thay đổi

Không dừng giám sát ngay khi máy boot thành công. Một số lỗi chỉ xuất hiện khi tải tăng, cache lạnh, job tiếp theo chạy hoặc batch bắt đầu. Đặt observation period theo đặc tính workload và SLO; có người chịu trách nhiệm theo dõi và tiêu chí kết thúc rõ ràng.

### 10.4. Tiêu chí dừng rollout

Ví dụ điều kiện dừng:

- Error rate vượt ngưỡng trong thời gian xác định.
- p95/p99 latency vượt SLO hoặc tăng bất thường so với baseline.
- Replica mất đồng bộ, quorum không an toàn hoặc backup/checkpoint thất bại.
- Node không trở lại trạng thái healthy trong thời hạn.
- CPU, memory, I/O hoặc network của phần còn lại vượt headroom an toàn.
- Job GPU/HPC không khôi phục hoặc driver/runtime không tương thích.

Ngưỡng cần được xác định trước dựa trên dữ liệu thực tế. Khi điều kiện dừng xảy ra, dừng rollout tiếp theo, bảo toàn log và trạng thái, sau đó quyết định rollback hoặc tiếp tục có kiểm soát.

## 11. Rollback và khôi phục

### 11.1. Xác định rollback trước khi bắt đầu

Rollback có thể là quay lại image cũ, khôi phục package, chuyển traffic về nhóm blue, failback database hoặc phục hồi từ checkpoint. Một số bản vá kernel có thể gỡ được; một số thay đổi firmware hoặc schema không dễ đảo ngược. Cần ghi rõ bước nào có thể rollback tự động và bước nào cần restore hoặc xử lý thủ công.

### 11.2. Backup không đồng nghĩa snapshot

Snapshot thường ghi lại trạng thái volume tại một thời điểm, nhưng tính nhất quán ứng dụng phụ thuộc cách tạo snapshot. Với database hoặc hệ thống nhiều volume, cần cơ chế quiesce, checkpoint hoặc backup nhất quán theo ứng dụng. Kiểm tra restore trước khi dựa vào backup làm phương án khôi phục.

### 11.3. Khi nào nên rollback, khi nào nên tiếp tục?

Nếu lỗi ảnh hưởng trực tiếp đến SLO, dữ liệu hoặc bảo mật và chưa xác định được nguyên nhân, rollback có thể giảm rủi ro. Nếu lỗi chỉ là cảnh báo không ảnh hưởng dịch vụ, có thể tiếp tục điều tra trong phạm vi canary. Quyết định phải dựa trên stop condition đã thống nhất, không dựa vào áp lực hoàn thành lịch.

Với database, rollback binary có thể không tương thích với schema đã nâng cấp. Với serverless, phiên bản function cũ có thể không tương thích với dữ liệu mới. Với container, image cũ có thể không đọc được format dữ liệu mới. Vì vậy, cần thiết kế tương thích ngược và chiến lược expand-and-contract khi thay đổi schema hoặc format.

### 11.4. Hoàn tất và hậu kiểm

Sau bảo trì, cập nhật trạng thái node, phiên bản, thời gian thực hiện, kết quả kiểm tra, sự cố phát sinh và hành động còn lại. Nếu cửa sổ bị vượt, thông báo cho chủ workload và người dùng theo quy trình. Ghi nhận thời gian thực tế để cải thiện dự toán cho lần sau.

## 12. Ví dụ lập lịch theo workload

### Ví dụ 1: API Tier 1 chạy trên VM stateless

Một API thương mại chạy trên nhiều VM sau load balancer, có SLO availability cao và tải thấp hơn vào một số khung giờ. Mỗi VM có thể thay thế từ image chuẩn.

**Lịch và chiến lược:** triển khai canary trước, sau đó rolling theo từng vùng. Đưa từng VM ra khỏi target group, chờ connection drain, thay bằng image đã vá và kiểm tra readiness. Giữ đủ minimum healthy capacity và không bảo trì đồng thời các VM thuộc cùng fault domain.

**Điều kiện go/no-go:** target healthy, error rate và p99 latency ổn định, autoscaling có quota và người trực xác nhận. Dừng rollout nếu lỗi tăng hoặc capacity còn lại vượt ngưỡng sử dụng an toàn.

### Ví dụ 2: Database Tier 0 có primary và replica

Database phục vụ giao dịch cốt lõi, yêu cầu RPO thấp và có replica ở fault domain khác. Reboot primary trực tiếp có thể gây gián đoạn và rủi ro failover.

**Lịch và chiến lược:** chọn cửa sổ riêng, xác minh backup và replication lag, cập nhật replica từng node, kiểm tra khả năng promote, failover có kiểm soát rồi bảo trì primary cũ khi đã ở vai trò replica. Theo dõi transaction error, consistency, quorum và thời gian phục hồi.

**Điều kiện go/no-go:** đủ replica khỏe, replication đồng bộ, backup có thể phục hồi, ứng dụng hỗ trợ chuyển endpoint và đội database trực. Nếu replication lag vượt ngưỡng, hoãn failover hoặc dừng rollout.

### Ví dụ 3: GPU/HPC cluster Tier 2 với job dài hạn

Cluster GPU chạy các job huấn luyện và mô phỏng kéo dài. Mỗi job có thể mất nhiều giờ để khởi động lại và tiêu thụ tài nguyên đắt tiền.

**Lịch và chiến lược:** dùng scheduler để ngừng nhận job mới trên nhóm node sắp bảo trì; chờ job ngắn hoàn tất, yêu cầu checkpoint cho job dài và requeue theo chính sách. Bảo trì theo node group nhỏ, kiểm tra driver, runtime, fabric và benchmark job đại diện trước khi mở lại queue.

**Điều kiện go/no-go:** checkpoint đã xác minh, job không còn chạy trên node, node thay thế đủ capacity, driver/runtime tương thích và chủ workload đồng ý lịch.

### Ví dụ 4: Serverless Tier 1 cần nâng runtime

Function xử lý đơn hàng dùng runtime sắp hết hỗ trợ. Nhà cung cấp quản lý host nhưng đội ứng dụng phải nâng runtime và dependency.

**Lịch và chiến lược:** build phiên bản mới, chạy unit/integration test, triển khai lên alias thử nghiệm, chuyển một phần traffic, quan sát error rate, duration, cold start và dead-letter queue, rồi chuyển toàn bộ traffic. Giữ phiên bản cũ để rollback trong giới hạn tương thích dữ liệu.

**Điều kiện go/no-go:** invocation thành công, IAM không đổi ngoài dự kiến, event được xử lý idempotent, retry và DLQ hoạt động, latency nằm trong SLO.

## 13. Những sai lầm thường gặp

- **Dùng cùng một cửa sổ cho mọi workload:** bỏ qua nhịp kinh doanh, dependency và khả năng phục hồi khác nhau.
- **Xếp hạng chỉ theo tên hệ thống:** không đánh giá business impact, SLO, RTO, RPO và dữ liệu.
- **Coi Tier 0 là lý do không vá:** workload quan trọng cần cơ chế triển khai an toàn để vẫn cập nhật kịp thời.
- **Bảo trì nhiều node cùng fault domain:** có thể làm mất quorum hoặc toàn bộ capacity dự phòng.
- **Drain mà không kiểm tra PDB/local storage:** có thể chặn thao tác hoặc làm mất dữ liệu tạm cần thiết.
- **Reboot node GPU khi job đang chạy:** có thể mất tiến độ nếu không checkpoint hoặc requeue.
- **Tin rằng live migration luôn không gián đoạn:** một số workload và thiết bị có giới hạn hoặc pause ngắn.
- **Chỉ kiểm tra máy boot thành công:** bỏ sót lỗi ứng dụng, replication, dữ liệu và nghiệp vụ.
- **Không tính capacity headroom:** workload còn lại có thể quá tải trong khi một phần cluster bảo trì.
- **Không thử restore:** backup hoặc snapshot có thể không phục hồi được trạng thái ứng dụng cần thiết.
- **Không có stop condition:** rollout tiếp tục dù error rate hoặc latency đã vượt ngưỡng.
- **Không ghi lại kết quả:** lần bảo trì tiếp theo lặp lại cùng sai sót và ước lượng thời gian thiếu chính xác.

## 14. Checklist trước, trong và sau bảo trì

### Trước bảo trì

- [ ] Đã xác định owner, tier criticality, SLO, RTO và RPO.
- [ ] Đã xác định loại bảo trì: host, hypervisor, guest OS, container host, driver hay runtime.
- [ ] Đã chọn cửa sổ theo tải, batch, múi giờ, freeze period và thông báo người dùng.
- [ ] Đã kiểm tra dependency, fault domain, quorum và capacity headroom.
- [ ] Đã thử bản vá/image/runtime trên môi trường phù hợp.
- [ ] Đã xác minh backup, snapshot hoặc checkpoint và khả năng restore.
- [ ] Đã có runbook, người phê duyệt, người trực, go/no-go và stop condition.
- [ ] Đã xác định cách drain, failover, live migration hoặc thay node.
- [ ] Đã xác định rollback, giới hạn thời gian và đường liên hệ khi vượt cửa sổ.

### Trong bảo trì

- [ ] Thực hiện theo canary hoặc batch size đã phê duyệt.
- [ ] Drain traffic/job trước khi reboot hoặc thay node.
- [ ] Theo dõi health, error rate, latency, replication và capacity.
- [ ] Dừng rollout khi chạm stop condition.
- [ ] Ghi lại phiên bản, node, thời điểm và kết quả từng bước.

### Sau bảo trì

- [ ] Xác minh node/VM/pod/function healthy và đúng phiên bản.
- [ ] Kiểm tra SLO kỹ thuật và chỉ số nghiệp vụ.
- [ ] Xác minh replica, quorum, queue, dữ liệu và checkpoint.
- [ ] Theo dõi đủ observation period.
- [ ] Thu hồi quyền tạm, đóng cửa sổ truy cập và dọn tài nguyên tạm.
- [ ] Cập nhật inventory, lịch bảo trì, ticket và runbook.
- [ ] Ghi nhận bài học và thời lượng thực tế.

## 15. Kết luận

Lập lịch bảo trì theo mức độ quan trọng của workload bắt đầu từ tác động kinh doanh, SLO, RTO, RPO, dependency và khả năng phục hồi. Tier 0/1 cần thử nghiệm, capacity dự phòng, rollout nhỏ, failover và người trực; Tier 2 có thể gom theo cửa sổ định kỳ; Tier 3 thường phù hợp với tự động hóa và tái tạo từ image.

Hãy phân biệt bảo trì host/hypervisor với guest OS, container host và runtime do đội ứng dụng quản lý. Chọn rolling, canary, blue/green, live migration, drain hoặc checkpoint theo loại compute và trạng thái dữ liệu. Một đợt bảo trì chỉ hoàn tất khi dịch vụ đã được xác minh về kỹ thuật lẫn nghiệp vụ, các chỉ số ổn định trong thời gian quan sát và kết quả được ghi lại để cải thiện lịch tiếp theo.
